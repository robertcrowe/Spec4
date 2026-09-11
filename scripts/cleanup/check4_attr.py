"""Check 4 for module-attribute targets (7n, amendment 2).

    uv run python scripts/cleanup/check4_attr.py REPO MODULE:FUNC NAME TARGET...

A patch string names MOD.NAME, where the production function FUNC reaches NAME either as
an attribute of a module object it holds (`X.NAME`) or by an in-function
`from MOD import NAME`. For each TARGET:
  (1) it resolves to a function named NAME, not a module;
  (2) the module it names is the one FUNC resolves NAME through -- the very module
      object bound to X in FUNC's module, or the module of FUNC's in-body import.
Each TARGET is located in tests/ as a string constant (file:line).
"""

import ast
import importlib
import inspect
import pathlib
import subprocess
import sys
import textwrap
import types


def resolve(path: str) -> object:
    """Import the longest module prefix of `path`, then walk the rest as attributes.

    patch_resolve.resolve, copied: each tool here is one file, because an import of a
    sibling reads to deptry as a missing dependency.
    """
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


repo = pathlib.Path(sys.argv[1])
modname, funcname = sys.argv[2].split(":")
name, targets = sys.argv[3], sys.argv[4:]
mod = importlib.import_module(modname)
func = getattr(mod, funcname)
tree = ast.parse(textwrap.dedent(inspect.getsource(func)))

via: dict[str, str] = {}
for node in ast.walk(tree):
    if (
        isinstance(node, ast.Attribute)
        and node.attr == name
        and isinstance(node.value, ast.Name)
    ):
        bound = getattr(mod, node.value.id, None)
        if isinstance(bound, types.ModuleType):
            row = node.lineno + func.__code__.co_firstlineno - 1
            via.setdefault(
                bound.__name__,
                f"{funcname} reads {node.value.id}.{name}@{row}, "
                f"{node.value.id} being {modname}'s binding of {bound.__name__}",
            )
    if (
        isinstance(node, ast.ImportFrom)
        and node.module
        and any(a.name == name for a in node.names)
    ):
        via.setdefault(
            node.module,
            f"{funcname} does `from {node.module} import {name}` in its body "
            f"@{node.lineno + func.__code__.co_firstlineno - 1}",
        )

files = subprocess.run(
    ["git", "-C", str(repo), "ls-files", "tests/*.py"],
    capture_output=True,
    text=True,
    check=True,
).stdout.split()
where: dict[str, list[str]] = {t: [] for t in targets}
for f in files:
    for node in ast.walk(ast.parse((repo / f).read_text())):
        if isinstance(node, ast.Constant) and node.value in where:
            where[node.value].append(f"{f}:{node.lineno}")

fails = 0
for t in targets:
    obj, pmod = resolve(t), resolve(t.rsplit(".", 1)[0])
    ok1 = (
        inspect.isfunction(obj)
        and obj.__name__ == name
        and not isinstance(obj, types.ModuleType)
    )
    key = pmod.__name__ if isinstance(pmod, types.ModuleType) else None
    ok2 = key in via
    verdict = "PASS" if ok1 and ok2 and where[t] else "FAIL"
    fails += verdict == "FAIL"
    print(f"{verdict} {t!r} at {', '.join(where[t]) or 'NOT FOUND IN tests/'}")
    if ok1:
        c1 = f"function {obj.__qualname__} defined in {obj.__module__}"
    else:
        c1 = f"NOT the function {name}"
    c2 = via.get(key, f"the module {key} is NOT how {funcname} resolves {name}")
    print(f"     (1) {c1}  (2) {c2}")
print(f"targets: {len(targets)}; FAIL: {fails}")
sys.exit(1 if fails else 0)
