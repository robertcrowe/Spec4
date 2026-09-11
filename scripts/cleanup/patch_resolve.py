"""Check 4 (§60.3): where each rewritten patch target lands.

    uv run python patch_resolve.py REPO MAPPING.json [--side new|old]

--side new (default, at C): targets ending in the batch's NEW names.
--side old (before the substitution, at P): targets ending in its OLD names.

Two forms are found in REPO's tracked .py files:
  path    a string constant "spec4.a.b.NAME" -- patch("…") and friends;
  object  patch.object(X, "NAME", …) -- X resolved statically through the file's
          imports to a dotted module path.
For each target, in the current tree, both conditions must hold:
  (1) the target is the renamed function itself: getattr(module, NAME) is a function
      whose __name__ is NAME, not a module (a shadow flip would make it one);
  (2) the module the target names is one that calls it: it reads NAME as a global
      inside a function body, so the patch lands where a call looks the name up.
Also reported per target: whether that module defines NAME or re-exports it, its call
sites (function@line), and every other spec4 module that calls NAME -- a caller the test
might reach instead. Exits non-zero on any FAIL or unresolvable target.
"""

import ast
import importlib
import inspect
import json
import pathlib
import subprocess
import sys
import types


def resolve(path: str) -> object:
    parts = path.split(".")
    for i in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:i]))
        except ImportError:
            continue
        for attr in parts[i:]:
            obj = getattr(obj, attr)
        return obj
    raise ImportError(path)


def call_sites(tree: ast.AST, name: str) -> list[str]:
    """Function bodies in `tree` that read `name` as a global (not a parameter)."""
    out = []
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = {
                a.arg for a in fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs
            }
            if name in params:
                continue
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Name)
                    and node.id == name
                    and isinstance(node.ctx, ast.Load)
                ):
                    out.append(f"{fn.name}@{node.lineno}")
    return sorted(set(out), key=lambda s: int(s.rsplit("@", 1)[1]))


def import_bindings(tree: ast.AST) -> dict[str, str]:
    """Local name -> dotted path, for the file's imports (module-level and nested)."""
    b = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    b[a.asname] = a.name
                else:
                    b.setdefault(a.name.split(".")[0], a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                b[a.asname or a.name] = f"{node.module}.{a.name}"
    return b


def dotted(expr: ast.AST, bindings: dict[str, str]) -> str | None:
    if isinstance(expr, ast.Name):
        return bindings.get(expr.id)
    if isinstance(expr, ast.Attribute):
        base = dotted(expr.value, bindings)
        return f"{base}.{expr.attr}" if base else None
    return None


def is_patch_object(call: ast.Call) -> bool:
    f = call.func
    return (
        isinstance(f, ast.Attribute)
        and f.attr == "object"
        and (
            (isinstance(f.value, ast.Name) and f.value.id == "patch")
            or (isinstance(f.value, ast.Attribute) and f.value.attr == "patch")
        )
    )


def is_setattr(call: ast.Call) -> bool:
    """Check 4's third form: `monkeypatch.setattr(X, "name", …)` and bare `setattr`."""
    f = call.func
    return (isinstance(f, ast.Attribute) and f.attr == "setattr") or (
        isinstance(f, ast.Name) and f.id == "setattr"
    )


def main() -> int:
    repo = pathlib.Path(sys.argv[1])
    mapping = json.load(open(sys.argv[2]))
    side = sys.argv[sys.argv.index("--side") + 1] if "--side" in sys.argv else "new"
    names = {o if side == "old" else n for o, n in mapping}
    files = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "*.py"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    # --base REV (new side): keep only targets on lines the batch changed against REV,
    # so a same-named function elsewhere (a clash) is not mistaken for a rewritten
    # target.
    changed = None
    if "--base" in sys.argv:
        import re

        diff = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "diff",
                "-U0",
                sys.argv[sys.argv.index("--base") + 1],
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        changed, cur = set(), None
        for line in diff.splitlines():
            if line.startswith("+++ "):
                cur = line[6:]
            elif line.startswith("@@"):
                m = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", line)
                start, count = int(m[1]), int(m[2]) if m[2] is not None else 1
                changed.update((cur, n) for n in range(start, start + count))
    src_trees = {
        f: ast.parse((repo / f).read_text())
        for f in files
        if f.startswith("src/spec4/")
    }

    targets = []  # (file, line, form, module_path, name)
    fourth = []  # getattr/hasattr/delattr and __dict__ access with a batch name
    for f in files:
        try:
            tree = ast.parse((repo / f).read_text())
        except SyntaxError:
            continue
        bindings = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                s = node.value
                if (
                    s.startswith("spec4.")
                    and " " not in s
                    and s.rsplit(".", 1)[-1] in names
                ):
                    targets.append(
                        (
                            f,
                            node.lineno,
                            "path",
                            s.rsplit(".", 1)[0],
                            s.rsplit(".", 1)[-1],
                        )
                    )
            elif (
                isinstance(node, ast.Call)
                and (is_patch_object(node) or is_setattr(node))
                and len(node.args) >= 2
            ):
                a1 = node.args[1]
                if isinstance(a1, ast.Constant) and a1.value in names:
                    bindings = (
                        bindings if bindings is not None else import_bindings(tree)
                    )
                    form = "object" if is_patch_object(node) else "setattr"
                    # keyed to the string's own line: a wrapped call starts a line
                    # earlier
                    targets.append(
                        (f, a1.lineno, form, dotted(node.args[0], bindings), a1.value)
                    )
            # a possible fourth form -- reported, not judged, so none passes unseen
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("getattr", "hasattr", "delattr")
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in names
            ):
                fourth.append(
                    f"{f}:{node.args[1].lineno} {node.func.id}(…, "
                    f"{node.args[1].value!r})"
                )
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "__dict__"
                and isinstance(node.slice, ast.Constant)
                and node.slice.value in names
            ):
                fourth.append(f"{f}:{node.lineno} __dict__[{node.slice.value!r}]")

    fails = 0
    if changed is not None:
        targets = [t for t in targets if (t[0], t[1]) in changed]
    for f, line, form, mod_path, name in sorted(targets):
        where = f"{f}:{line} [{form}] {mod_path}.{name}"
        if mod_path is None:
            print(
                f"FAIL {where}: patch.object target not statically resolvable -- "
                "check by hand"
            )
            fails += 1
            continue
        try:
            mod = resolve(mod_path)
            obj = getattr(mod, name)
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {where}: does not resolve ({type(e).__name__}: {e})")
            fails += 1
            continue
        ok1 = inspect.isfunction(obj) and obj.__name__ == name
        ok_mod = isinstance(mod, types.ModuleType)
        mod_file = (
            pathlib.Path(inspect.getsourcefile(mod)).resolve() if ok_mod else None
        )
        rel = str(mod_file.relative_to(repo.resolve())) if mod_file else "?"
        sites = call_sites(src_trees[rel], name) if rel in src_trees else []
        definer = getattr(obj, "__module__", "?")
        role = (
            "defines it"
            if definer == getattr(mod, "__name__", None)
            else f"re-exports it from {definer}"
        )
        others = {
            m: s
            for m, t in src_trees.items()
            if m != rel and (s := call_sites(t, name))
        }
        verdict = "PASS" if ok1 and ok_mod and sites else "FAIL"
        fails += verdict == "FAIL"
        c1 = (
            f"function {obj.__qualname__}"
            if ok1
            else f"NOT the function: {type(obj).__name__}"
        )
        c2 = (
            f"calls it at {', '.join(sites)}"
            if sites
            else "NO call site -- the patch lands where no call looks"
        )
        print(f"{verdict} {where}\n     (1) {c1}  (2) {rel} {role}; {c2}")
        if others:
            print(f"     other callers: {others}")
    for x in fourth:
        print(f"NOTE possible fourth form, not judged: {x}")
    print(
        f"targets ending in a batch name ({side} side): {len(targets)}; FAIL: "
        f"{fails}; fourth-form candidates: {len(fourth)}"
    )
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
