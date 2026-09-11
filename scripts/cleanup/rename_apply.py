"""Forward rename (§60.2), token-aware.

    uv run python scripts/cleanup/rename_apply.py ROOT MAPPING.json REPORT.json


MAPPING.json is [[old, new], ...]. Rewrites every word-boundary occurrence of `old` in
every tracked text file under ROOT except:
  * CLEANUP_INVENTORY.md (the record);
  * tests/golden/ and tests/snapshots/ (frozen data -- a hit is reported, never edited);
  * a module-path component: the module part of `from X import`, any `import X` line,
    or a dotted string component followed by '.', or a sys.modules / import_module key;
  * the seven §50.3 whole-file entries, where only the import binding changes, as
    `new as old` (§54.7: import lines alone; bodies keep reading the local alias).
A whole-file entry that reaches `old` any other way (attribute, string) is reported
as BLOCKED and left untouched -- §54.7 cannot be met there, which is a stop.

This is the one tool here that writes src/ and tests/ and keeps the change, so it has
no restore to verify. Instead:
  * it refuses to run unless ROOT's `git status --porcelain` is empty, so the rename is
    the tree's only change and `git checkout -- .` undoes it exactly;
  * every new text is computed before anything is written;
  * each write is read back and its sha256 compared with the bytes intended. A failure
    rolls back every file already written, and the rollback is itself checked by
    sha256 and a clean tree (exit 3 if it cannot be verified).
REPORT.json (changed files, skips, frozen hits, blocked sites) must be outside ROOT.
"""

import ast
import hashlib
import io
import json
import pathlib
import re
import signal
import subprocess
import sys
import tokenize


def refuse(msg: str) -> None:
    print(f"REFUSED: {msg}", file=sys.stderr)
    sys.exit(2)


if len(sys.argv) != 4:
    refuse("usage: rename_apply.py ROOT MAPPING.json REPORT.json")
ROOT = pathlib.Path(sys.argv[1]).resolve()
MAP = [tuple(x) for x in json.load(open(sys.argv[2]))]
REPORT = pathlib.Path(sys.argv[3]).resolve()
if REPORT.is_relative_to(ROOT):
    refuse(f"{REPORT} is inside {ROOT}; the report must not land in the tree")


def status() -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


if dirty := status():
    refuse(f"{ROOT} is not clean; the rename must be the tree's only change:\n{dirty}")
WHOLE = {
    "tests/test_app_import_smoke.py",
    "tests/test_layout_contract.py",
    "tests/test_project_manager_golden.py",
    "tests/test_renderer_goldens.py",
    "tests/test_streaming_characterization.py",
    "tests/test_callback_co_presence.py",
    "tests/test_import_layering.py",
}
FROZEN = ("tests/golden/", "tests/snapshots/")


def tok(n):
    return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])")


def module_exists(dotted):
    if not dotted.startswith("spec4"):
        return False
    base = ROOT / "src" / pathlib.Path(*dotted.split("."))
    return base.with_suffix(".py").exists() or (base / "__init__.py").exists()


files = subprocess.run(
    ["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True
).stdout.split()
# Names that are also a submodule's name: any occurrence followed by '.' names the
# module (`_round_tree.ROUND_ARTIFACTS` in a docstring), in code, string or comment.
SHADOW = {
    old
    for old, _ in MAP
    if any(
        f.startswith("src/spec4/") and pathlib.PurePath(f).stem == old for f in files
    )
}
report = {
    "changed": {},
    "module_path_skips": [],
    "frozen_hits": [],
    "whole_alias": [],
    "blocked": [],
}


def string_spans(text):
    spans = []
    for t in tokenize.generate_tokens(io.StringIO(text).readline):
        if t.type == tokenize.STRING or tokenize.tok_name[t.type] == "FSTRING_MIDDLE":
            spans.append((t.start, t.end))
    return spans


def in_span(spans, row, col):
    return any(s <= (row, col) < e for s, e in spans)


def substitute(p, text):
    lines = text.split("\n")
    spans = string_spans(text) if p.endswith(".py") else []
    tree = ast.parse(text) if p.endswith(".py") else None
    modkeys = set()
    if tree is not None:
        for n in ast.walk(tree):
            if (
                isinstance(n, ast.Subscript)
                and ast.unparse(n.value) == "sys.modules"
                and isinstance(n.slice, ast.Constant)
            ):
                modkeys.add(n.slice.lineno)
            if isinstance(n, ast.Call) and ast.unparse(n.func) in (
                "importlib.import_module",
                "import_module",
            ):
                modkeys.add(n.lineno)
    for i, line in enumerate(lines):
        row = i + 1
        for old, new in MAP:
            if old not in line:
                continue
            out, last = [], 0
            for m in tok(old).finditer(line):
                a, b = m.start(), m.end()
                skip = old in SHADOW and line[b : b + 1] == "."
                if not skip and p.endswith(".py"):
                    fm = re.match(r"^\s*from\s+([.\w]+)\s+import\b", line)
                    if (fm and fm.start(1) <= a < fm.end(1)) or re.match(
                        r"^\s*import\s", line
                    ):
                        skip = True
                    elif in_span(spans, row, a):
                        run = re.search(r"[\w.]*$", line[:a]).group(0) + old
                        if line[b : b + 1] == "." and module_exists(run):
                            skip = True
                        elif row in modkeys and module_exists(run):
                            skip = True
                if skip:
                    report["module_path_skips"].append((p, row, old))
                    continue
                out.append(line[last:a])
                out.append(new)
                last = b
            if out:
                out.append(line[last:])
                line = "".join(out)
        lines[i] = line
    return "\n".join(lines)


def alias_imports(p, text):
    tree = ast.parse(text)
    edits = []
    imported = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            for al in n.names:
                for old, new in MAP:
                    if al.name == old:
                        edits.append(
                            (
                                al.lineno,
                                al.col_offset,
                                al.end_lineno,
                                al.end_col_offset,
                                f"{new} as {al.asname or old}",
                            )
                        )
                        imported[al.asname or old] = old
    # anything else reaching `old` in this file blocks §54.7
    docs = set()
    for n in ast.walk(tree):
        if (
            isinstance(
                n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            )
            and n.body
            and isinstance(n.body[0], ast.Expr)
            and isinstance(n.body[0].value, ast.Constant)
            and isinstance(n.body[0].value.value, str)
        ):
            docs.update(range(n.body[0].lineno, n.body[0].end_lineno + 1))
    for n in ast.walk(tree):
        for old, _ in MAP:
            if isinstance(n, ast.Attribute) and n.attr == old:
                report["blocked"].append((p, n.lineno, old, "attribute"))
            elif (
                isinstance(n, ast.Constant)
                and isinstance(n.value, str)
                and tok(old).search(n.value)
                and n.lineno not in docs
            ):
                report["blocked"].append((p, n.lineno, old, "string"))
            elif isinstance(n, ast.Name) and n.id == old and old not in imported:
                report["blocked"].append(
                    (p, n.lineno, old, "name not bound by an import")
                )
    if any(b[0] == p for b in report["blocked"]):
        return text
    lines = text.split("\n")
    for l1, c1, l2, c2, rep in sorted(edits, reverse=True):
        assert l1 == l2
        s = lines[l1 - 1]
        lines[l1 - 1] = s[:c1] + rep + s[c2:]
        report["whole_alias"].append((p, l1, rep))
    return "\n".join(lines)


pending: dict[str, tuple[bytes, bytes]] = {}  # path -> (bytes before, bytes after)
for p in files:
    fp = ROOT / p
    if p == "CLEANUP_INVENTORY.md" or p.startswith(".spec4/") or not fp.is_file():
        continue  # the record, and Rule 2: nothing under .spec4/ is ever written
    raw = fp.read_bytes()
    if b"\0" in raw[:8192]:
        continue
    text = raw.decode()
    if not any(tok(o).search(text) for o, _ in MAP):
        continue
    if p.startswith(FROZEN):
        for o, _ in MAP:
            for m in tok(o).finditer(text):
                report["frozen_hits"].append((p, text.count("\n", 0, m.start()) + 1, o))
        continue
    new_text = alias_imports(p, text) if p in WHOLE else substitute(p, text)
    if new_text != text:
        pending[p] = (raw, new_text.encode())
        report["changed"][p] = sum(
            1 for a, b in zip(text.split("\n"), new_text.split("\n")) if a != b
        )


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _exit(signum, frame):
    raise SystemExit(128 + signum)


# Every new text is computed above, before the first write, so a failure while reading
# or parsing leaves the tree untouched. A failure during the writes rolls back what was
# written, and the rollback is verified by sha256 and by a clean tree.
signal.signal(signal.SIGTERM, _exit)
signal.signal(signal.SIGHUP, _exit)
written: list[str] = []
try:
    for p, (_, new_bytes) in pending.items():
        (ROOT / p).write_bytes(new_bytes)
        written.append(p)
        if sha((ROOT / p).read_bytes()) != sha(new_bytes):
            raise OSError(f"{p}: the bytes on disk are not the bytes written")
except BaseException:
    for p in written:
        (ROOT / p).write_bytes(pending[p][0])
    ok = all(sha((ROOT / p).read_bytes()) == sha(pending[p][0]) for p in written)
    ok = ok and not status()
    print(
        f"ROLLED BACK {len(written)} file(s); verified by sha256 and a clean tree: "
        f"{ok}",
        file=sys.stderr,
    )
    if not ok:
        sys.exit(3)
    raise

json.dump(report, open(REPORT, "w"), indent=1)
print(
    f"files changed: {len(report['changed'])}, lines changed: "
    f"{sum(report['changed'].values())}"
)
print(
    f"whole-file alias edits: {len(report['whole_alias'])} in "
    f"{len({w[0] for w in report['whole_alias']})} files"
)
print(f"module-path occurrences left alone: {len(report['module_path_skips'])}")
print(f"frozen-data hits: {report['frozen_hits'] or 'none'}")
print(f"BLOCKED (§54.7 cannot be met): {report['blocked'] or 'none'}")
sys.exit(1 if report["blocked"] else 0)
