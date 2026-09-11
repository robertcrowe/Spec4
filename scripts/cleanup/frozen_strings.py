"""Frozen strings (Rule 4, 7q1): a module's string constants, before and after.

    python scripts/cleanup/frozen_strings.py BASE_REV [PATH]

PATH defaults to agentifier.py, the module 7q split. Run from the repo root.

Every str Constant in the module, the literal parts of f-strings included, is counted,
and docstrings (a body's leading string expression) are left out. The SET must be
identical: no prompt, status, label or display fragment may appear or disappear. COUNT
changes are listed, because a shared step legitimately collapses duplicated labels.
Exit 1 if the sets differ.
"""

import ast
import collections
import subprocess
import sys


def strings(src: str) -> collections.Counter:
    tree = ast.parse(src)
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(body, list)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docs.add(id(body[0].value))
    return collections.Counter(
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and id(n) not in docs
    )


base = sys.argv[1]
path = sys.argv[2] if len(sys.argv) > 2 else "src/spec4/agentifier/agentifier.py"
old = strings(
    subprocess.run(
        ["git", "show", f"{base}:{path}"], capture_output=True, text=True, check=True
    ).stdout
)
new = strings(open(path).read())
gone, added = sorted(set(old) - set(new)), sorted(set(new) - set(old))
counts = sorted((s, old[s], new[s]) for s in set(old) & set(new) if old[s] != new[s])
print(
    f"{path}: string constants {sum(old.values())} -> {sum(new.values())}; distinct "
    f"{len(old)} -> {len(new)}"
)
print(f"  gone: {len(gone)}; added: {len(added)}; count changes: {len(counts)}")
for s in gone:
    print(f"  GONE  {s[:90]!r}")
for s in added:
    print(f"  ADDED {s[:90]!r}")
for s, a, b in counts:
    print(f"  COUNT {a} -> {b}  {s[:80]!r}")
sys.exit(1 if gone or added else 0)
