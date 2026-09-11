"""7o's rule, checked: strip the annotations from both sides, and nothing may remain.

    python scripts/cleanup/strip_check.py BASE_REV ROOT

Every .py file under ROOT/src whose text differs from BASE_REV's is parsed on both
sides, and annotation material is erased before the two are compared:
- every argument and return annotation;
- every AnnAssign's annotation (the statement is kept, so a dataclass field stays a
  field);
- PEP 695 type parameters;
- `if TYPE_CHECKING:` blocks, which never execute;
- the TYPE_CHECKING name in a `from typing import`.
Anything else that differs is a runtime change and is printed as unparsed code. Exit 1
on any residue. Layout-blind: ast, not text.
"""

import ast
import difflib
import pathlib
import subprocess
import sys


class Strip(ast.NodeTransformer):
    def _fn(self, node):
        node.returns = None
        if hasattr(node, "type_params"):
            node.type_params = []
        a = node.args
        for arg in [
            *a.posonlyargs,
            *a.args,
            *a.kwonlyargs,
            *(x for x in (a.vararg, a.kwarg) if x),
        ]:
            arg.annotation = None
        self.generic_visit(node)
        return node

    visit_FunctionDef = _fn
    visit_AsyncFunctionDef = _fn

    def visit_AnnAssign(self, node):
        node.annotation = ast.Constant(value="<annotation>")
        self.generic_visit(node)
        return node

    def visit_If(self, node):
        t = node.test
        if (isinstance(t, ast.Name) and t.id == "TYPE_CHECKING") or (
            isinstance(t, ast.Attribute) and t.attr == "TYPE_CHECKING"
        ):
            return [self.visit(n) for n in node.orelse] or None
        self.generic_visit(node)
        return node

    def visit_ImportFrom(self, node):
        if node.module == "typing":
            node.names = [a for a in node.names if a.name != "TYPE_CHECKING"]
            if not node.names:
                return None
        return node


def stripped(src: str) -> ast.Module:
    return ast.fix_missing_locations(Strip().visit(ast.parse(src)))


base, root = sys.argv[1], pathlib.Path(sys.argv[2])
changed = residue = 0
for p in sorted((root / "src").rglob("*.py")):
    rel = p.relative_to(root).as_posix()
    new = p.read_text()
    old = subprocess.run(
        ["git", "show", f"{base}:{rel}"], capture_output=True, text=True
    )
    if old.returncode != 0:
        print(f"NEW FILE (residue): {rel}")
        residue += 1
        continue
    if old.stdout == new:
        continue
    changed += 1
    a, b = stripped(old.stdout), stripped(new)
    if ast.dump(a) == ast.dump(b):
        print(f"  empty after strip: {rel}")
        continue
    residue += 1
    print(f"RESIDUE: {rel}")
    for line in difflib.unified_diff(
        ast.unparse(a).splitlines(),
        ast.unparse(b).splitlines(),
        "base (stripped)",
        "new (stripped)",
        lineterm="",
        n=1,
    ):
        print("    " + line)
print(f"files changed: {changed}; files with residue: {residue}")
sys.exit(1 if residue else 0)
