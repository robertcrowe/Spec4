"""7p's check: a constant named for a magic value is that value, and nothing else moved.

    python scripts/cleanup/inline_check.py BASE_REV ROOT [REL_PATH...]

For each .py file (the paths given, or every one under ROOT/src and ROOT/scripts)
whose text differs from BASE_REV's:
1. collect the module-level assignments `NAME = <literal>` that the new side adds,
   where NAME is not bound at module level in BASE and is never rebound anywhere in
   the module;
2. replace every load of such a name with its literal, and remove those assignments;
3. require the result's AST to equal BASE's.

Comments are not in the AST, so a `# noqa` is invisible to the check by construction,
and so is layout: a wrapped line, parentheses, or an implicitly concatenated string.
Exit 1 on any residue, printed as unparsed code.
"""

import ast
import difflib
import pathlib
import subprocess
import sys


def module_bound(tree: ast.Module) -> set[str]:
    out = set()
    for n in tree.body:
        targets = (
            n.targets
            if isinstance(n, ast.Assign)
            else [n.target]
            if isinstance(n, ast.AnnAssign)
            else []
        )
        out |= {t.id for t in targets if isinstance(t, ast.Name)}
    return out


class Inline(ast.NodeTransformer):
    def __init__(self, consts: dict) -> None:
        self.consts = consts
        self.count = 0

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load) and node.id in self.consts:
            self.count += 1
            return ast.copy_location(ast.Constant(self.consts[node.id]), node)
        return node


def check(rel: str, base_src: str, new_src: str) -> bool:
    base, new = ast.parse(base_src), ast.parse(new_src)
    old_names = module_bound(base)
    consts, body = {}, []
    for n in new.body:
        if (
            isinstance(n, ast.Assign)
            and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Name)
            and isinstance(n.value, ast.Constant)
            and n.targets[0].id not in old_names
        ):
            consts[n.targets[0].id] = n.value.value
            continue
        body.append(n)
    stores = {
        x.id
        for x in ast.walk(ast.Module(body=body, type_ignores=[]))
        if isinstance(x, ast.Name) and isinstance(x.ctx, (ast.Store, ast.Del))
    }
    rebound = sorted(set(consts) & stores)
    if rebound:
        print(f"RESIDUE: {rel}: added constant(s) rebound in the module: {rebound}")
        return False
    new.body = body
    tr = Inline(consts)
    new = tr.visit(new)
    label = ", ".join(f"{k} = {v!r}" for k, v in consts.items()) or "no constants added"
    if ast.dump(base) == ast.dump(new):
        print(
            f"  identical after inlining: {rel}  [{label}; {tr.count} load(s) inlined]"
        )
        return True
    print(f"RESIDUE: {rel}  [{label}]")
    for line in difflib.unified_diff(
        ast.unparse(base).splitlines(),
        ast.unparse(new).splitlines(),
        "base",
        "new (inlined)",
        lineterm="",
        n=1,
    ):
        print("    " + line)
    return False


base, root = sys.argv[1], pathlib.Path(sys.argv[2])
paths = sys.argv[3:] or [
    p.relative_to(root).as_posix()
    for d in ("src", "scripts")
    for p in sorted((root / d).rglob("*.py"))
]
changed = bad = 0
for rel in paths:
    new_src = (root / rel).read_text()
    old = subprocess.run(
        ["git", "show", f"{base}:{rel}"], capture_output=True, text=True
    )
    if old.returncode != 0 or old.stdout == new_src:
        continue
    changed += 1
    bad += not check(rel, old.stdout, new_src)
print(f"files changed: {changed}; files with residue: {bad}")
sys.exit(1 if bad else 0)
