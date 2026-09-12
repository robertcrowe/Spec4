"""The move petition (§1.4): tests moved between files, and nothing else.

    uv run python scripts/cleanup/move_check.py BASE_DIR NEW_DIR MAP.json

Ruled at Phase 8's D9 (cleanup-complete:PHASE8_RECORD.md §19.1). BASE_DIR and NEW_DIR
are two trees, such as a `git archive` export and the working tree, each holding
`tests/`, `src/` and `scripts/cleanup/`. MAP.json names, for each source file, where
its moved top-level nodes went:

    {"tests/test_agents.py": {"TestBrainstormer": "tests/test_brainstormer.py", ...}}

A node the map does not name stays in its source file. Four checks, and exit 1 if any
fails:

  1. Collection. `pytest --collect-only -q` runs in each tree, importing that tree's
     own `src/`. Every BASE node id must be collected in NEW exactly once, at its
     mapped file, with the same class and function names and any parametrised
     suffix. No NEW id may be unaccounted for.
  2. Byte-identity. Every top-level node of each source file, moved or staying, must
     have a source segment in NEW that is byte-identical to BASE's, decorators
     included. The files' headers (imports, docstring) are not compared: they are
     regenerated.
  3. The floor. NEW's `floor.json` must equal BASE's with exactly the node ids of
     moved classes rewritten old -> new, nothing else changed. NEW's own
     `floor_check.py` must then pass on NEW's collection.
  4. Nothing else. Every `tests/` file that is neither a source nor a destination
     must be byte-identical, and every file new in NEW must be a destination.
"""

from __future__ import annotations

import ast
import json
import os
import pathlib
import subprocess
import sys
import tempfile

BASE = pathlib.Path(sys.argv[1]).resolve()
NEW = pathlib.Path(sys.argv[2]).resolve()
MAP: dict[str, dict[str, str]] = json.loads(pathlib.Path(sys.argv[3]).read_text())
FLOOR = pathlib.Path("scripts/cleanup/data/floor.json")
failures: list[str] = []


def verdict(label: str, problems: list[str]) -> None:
    print(f"check {label}: {'PASS' if not problems else 'FAIL'}")
    for p in problems[:20]:
        print(f"    {p}")
    if len(problems) > 20:
        print(f"    ... and {len(problems) - 20} more")
    if problems:
        failures.append(label)


def destination(file: str, name: str) -> str:
    return MAP.get(file, {}).get(name, file)


def moved_id(node_id: str) -> str:
    file, _, rest = node_id.partition("::")
    top = rest.split("::")[0].split("[")[0]
    return f"{destination(file, top)}::{rest}"


def collect(tree: pathlib.Path) -> list[str]:
    env = dict(os.environ, PYTHONPATH=str(tree / "src"))
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=tree,
        env=env,
        capture_output=True,
        text=True,
    )
    ids = [ln for ln in out.stdout.splitlines() if "::" in ln]
    if out.returncode != 0:
        errors = [ln for ln in out.stdout.splitlines() if "ERROR" in ln][:5]
        ids.append(f"<collection exit {out.returncode}: {errors}>")
    return ids


UNPARSEABLE = "<unparseable>"


def segments(path: pathlib.Path) -> dict[str, str]:
    """Each top-level node's source, by name; a file that does not parse says so."""
    src = path.read_text()
    lines = src.splitlines(keepends=True)
    out = {}
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return {UNPARSEABLE: f"line {exc.lineno}: {exc.msg}"}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = n.name
        elif isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
            name = n.targets[0].id
        else:
            continue
        start = min([n.lineno] + [d.lineno for d in getattr(n, "decorator_list", [])])
        out[name] = "".join(lines[start - 1 : n.end_lineno])
    return out


# 1. Collection
base_ids, new_ids = collect(BASE), collect(NEW)
problems = [i for i in base_ids + new_ids if i.startswith("<collection")]
expected = [moved_id(i) for i in base_ids if not i.startswith("<")]
seen: dict[str, int] = {}
for i in new_ids:
    seen[i] = seen.get(i, 0) + 1
problems += [
    f"not collected at its new place: {e}" for e in expected if seen.get(e, 0) == 0
]
problems += [f"collected {n} times: {i}" for i, n in seen.items() if n > 1]
problems += [
    f"unaccounted for: {i}"
    for i in set(new_ids) - set(expected)
    if not i.startswith("<")
]
print(f"collected: BASE {len(base_ids)}, NEW {len(new_ids)}")
verdict("1 (collection)", problems)

# 2. Byte-identity
problems = []
dest_files = {d for m in MAP.values() for d in m.values()}
new_segments = {
    f: segments(NEW / f) for f in dest_files | set(MAP) if (NEW / f).exists()
}
problems += [
    f"{f}: does not parse ({segs[UNPARSEABLE]})"
    for f, segs in sorted(new_segments.items())
    if UNPARSEABLE in segs
]
checked = 0
for src_file in MAP:
    base_segments = segments(BASE / src_file)
    if UNPARSEABLE in base_segments:
        problems.append(f"BASE {src_file}: does not parse")
        continue
    for name, seg in base_segments.items():
        where = destination(src_file, name)
        checked += 1
        if UNPARSEABLE in new_segments.get(where, {}):
            continue
        got = new_segments.get(where, {}).get(name)
        if got is None:
            problems.append(f"{name}: not found in {where}")
        elif got != seg:
            problems.append(f"{name}: not byte-identical in {where}")
print(f"top-level nodes compared: {checked}")
verdict("2 (byte-identity)", problems)

# 3. The floor: floor.json rewritten by exactly the moves, then NEW's own floor check,
# run on NEW's collection (it would otherwise ask git for the root, which an export
# does not have).
problems = []
base_floor = json.loads((BASE / FLOOR).read_text())
new_floor = json.loads((NEW / FLOOR).read_text())
want = {
    k: (
        [moved_id(i) if isinstance(i, str) and "::" in i else i for i in v]
        if isinstance(v, list)
        else v
    )
    for k, v in base_floor.items()
}
rewritten = sum(
    1
    for v in base_floor.values()
    if isinstance(v, list)
    for i in v
    if isinstance(i, str) and "::" in i and moved_id(i) != i
)
for k in sorted(set(want) | set(new_floor)):
    if want.get(k) != new_floor.get(k):
        problems.append(f"floor.json[{k!r}] is not BASE's with the moved ids rewritten")
with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
    fh.write("\n".join(i for i in new_ids if not i.startswith("<")) + "\n")
check = subprocess.run(
    [sys.executable, str(NEW / "scripts/cleanup/floor_check.py"), fh.name],
    cwd=NEW,
    capture_output=True,
    text=True,
)
os.unlink(fh.name)
tail = [
    ln for ln in check.stdout.splitlines() if ln.startswith(("floor total", "FAILURES"))
]
print(f"floor ids rewritten old -> new: {rewritten}; NEW's floor_check: {tail}")
if check.returncode != 0:
    problems.append(f"floor_check.py exit {check.returncode}")
verdict("3 (the floor)", problems)

# 4. Nothing else
problems = []
touched = set(MAP) | dest_files
base_tests = {
    p.relative_to(BASE).as_posix()
    for p in (BASE / "tests").rglob("*")
    if p.is_file() and "__pycache__" not in p.parts
}
new_tests = {
    p.relative_to(NEW).as_posix()
    for p in (NEW / "tests").rglob("*")
    if p.is_file() and "__pycache__" not in p.parts
}
problems += [
    f"new file that is no destination: {f}"
    for f in sorted(new_tests - base_tests - dest_files)
]
problems += [f"file gone: {f}" for f in sorted(base_tests - new_tests)]
for f in sorted((base_tests & new_tests) - touched):
    if (BASE / f).read_bytes() != (NEW / f).read_bytes():
        problems.append(f"changed but not in the map: {f}")
print(f"other tests/ files compared: {len((base_tests & new_tests) - touched)}")
verdict("4 (nothing else)", problems)

print(f"MOVE PETITION: {'PASS' if not failures else 'FAIL ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
