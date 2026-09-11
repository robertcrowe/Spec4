"""§60.3 rename petition and §54.7 golden petition, checked mechanically.

    uv run python scripts/cleanup/petition_check.py REPO BASE MAPPING.json

REPO's working tree is the candidate; BASE is the pre-rename commit; MAPPING.json is
[[old, new], ...]. The net is data/floor.json.

Whole-file entries (§54.7): (1) every changed line is inside an import statement;
  (2) tests/golden/ and tests/snapshots/ byte-identical; (3) the file's node ids
  collect unchanged.
Tier-B classes and tier-A node ids (§60.3): (1) the file's reverse-substitution diff
  is empty inside the net entry; (2) every assertion in the file is token-identical
  under the substitution; (3) the off-limits check (floor_check.py) passes for every
  other entry.
"""

import ast
import io
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import tokenize

HERE = pathlib.Path(__file__).resolve().parent
REPO = pathlib.Path(sys.argv[1]).resolve()
BASE = sys.argv[2]
MAP = [tuple(x) for x in json.load(open(sys.argv[3]))]
_VENV_RUFF = REPO / ".venv" / "bin" / "ruff"
RUFF = str(_VENV_RUFF) if _VENV_RUFF.exists() else shutil.which("ruff") or "ruff"
FLOOR = json.loads((HERE / "data" / "floor.json").read_text())
WHOLE = FLOOR["whole_file"]
# file -> its protected class names (tier B), and file -> its named node ids (tier A,
# the ordering ids included). floor.json keeps the whole-file entries out of both.
TIERB: dict[str, set[str]] = {}
for _nid in FLOOR["tier_b"]:
    _f, _, _rest = _nid.partition("::")
    TIERB.setdefault(_f, set()).add(_rest.partition("::")[0])
TIERA: dict[str, set[str]] = {}
for _nid in FLOOR["tier_a_named"]:
    _f, _, _rest = _nid.partition("::")
    TIERA.setdefault(_f, set()).add(_rest)
DEFS = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
SKIP = {
    tokenize.NL,
    tokenize.NEWLINE,
    tokenize.COMMENT,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.ENDMARKER,
}


def git(*a):
    return subprocess.run(
        ["git", "-C", str(REPO), *a], capture_output=True, text=True
    ).stdout


def base_text(p):
    r = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{BASE}:{p}"], capture_output=True, text=True
    )
    return r.stdout if r.returncode == 0 else None


def tok(n):
    return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])")


def rev(t):
    for old, new in MAP:
        t = tok(new).sub(old, t)
    return t


def norm(t):
    t = re.sub(r"\b([A-Za-z_]\w*) as \1\b", r"\1", rev(t))
    r = subprocess.run(
        [RUFF, "format", "--no-cache", "--config"]
        + ["format.skip-magic-trailing-comma = true", "-"],
        input=t,
        capture_output=True,
        text=True,
    )
    return r.stdout if r.returncode == 0 else "<ruff failed>" + r.stderr


def hunks(p):
    out = []
    for line in git("diff", "-U0", BASE, "--", p).splitlines():
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if m:
            out.append((int(m[1]), int(m[2] or 1), int(m[3]), int(m[4] or 1)))
    return out


def import_rows(text):
    rows = set()
    for n in ast.walk(ast.parse(text)):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            rows.update(range(n.lineno, n.end_lineno + 1))
    return rows


def net_ranges(p, text):
    t = ast.parse(text)
    out = {}
    for c in t.body:
        if isinstance(c, ast.ClassDef) and c.name in TIERB.get(p, ()):
            out["tierB:" + c.name] = (c.lineno, c.end_lineno)
    for nid in TIERA.get(p, ()):
        body, node = t.body, None
        for part in nid.split("::"):
            node = next(
                (n for n in body if isinstance(n, DEFS) and n.name == part), None
            )
            if node is None:
                break
            body = getattr(node, "body", [])
        if node is not None:
            decorators = [x.lineno for x in getattr(node, "decorator_list", [])]
            out["tierA:" + nid] = (min([node.lineno, *decorators]), node.end_lineno)
    return out


def assertions(text):
    out = []
    t = ast.parse(text)
    nodes = [
        n
        for n in ast.walk(t)
        if isinstance(n, ast.Assert)
        or (
            isinstance(n, ast.Call)
            and (getattr(n.func, "attr", None) or getattr(n.func, "id", "")).startswith(
                "assert"
            )
        )
    ]
    for n in sorted(nodes, key=lambda n: (n.lineno, n.col_offset)):
        seg = rev(ast.get_source_segment(text, n))
        try:
            out.append(
                [
                    (x.type, x.string)
                    for x in tokenize.generate_tokens(io.StringIO(seg).readline)
                    if x.type not in SKIP
                ]
            )
        except (tokenize.TokenError, IndentationError):
            out.append(re.sub(r"\s+", "", seg))
    return out


def collect(root, path, pythonpath):
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"]
        + ["-p", "no:cacheprovider", path],
        cwd=root,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": pythonpath, "PATH": "/usr/bin:/bin"},
    )
    return {line for line in r.stdout.splitlines() if "::" in line}


def segment(text, key):
    """The net entry named by `key` ("tierA:Class::test" or "tierB:Class"), dedented.

    Check 1 is taken over the net entry itself -- the listed class or node -- because
    in a tier-B or tier-A file the rest of the file is not net. Any other hunk in the
    file is the allowed-and-reported kind (or a batch's documented exception),
    reported apart.
    """
    body, node = ast.parse(text).body, None
    for part in key.split(":", 1)[1].split("::"):
        node = next(n for n in body if isinstance(n, DEFS) and n.name == part)
        body = getattr(node, "body", [])
    decorators = [x.lineno for x in getattr(node, "decorator_list", [])]
    start = min([node.lineno, *decorators])
    lines = text.splitlines()[start - 1 : node.end_lineno]
    return textwrap.dedent("\n".join(lines)) + "\n"


def check(work: pathlib.Path) -> int:
    changed = [p for p in git("diff", "--name-only", BASE).split() if p.endswith(".py")]
    base_dir = work / "base"
    base_dir.mkdir()
    archive = subprocess.run(
        ["git", "-C", str(REPO), "archive", BASE], capture_output=True
    ).stdout
    tarfile.open(fileobj=io.BytesIO(archive)).extractall(base_dir, filter="data")
    fails, report = [], []
    golden = git("diff", "--stat", BASE, "--", "tests/golden/", "tests/snapshots/")
    golden = golden.strip()
    for p in changed:
        b, c = base_text(p), (REPO / p).read_text()
        if p in WHOLE:
            bi, ci = import_rows(b), import_rows(c)
            hs = hunks(p)
            bad = [
                f"-{row}"
                for (os_, ol, _ns, _nl) in hs
                for row in range(os_, os_ + ol)
                if ol and row not in bi
            ] + [
                f"+{row}"
                for (_os, _ol, ns, nl) in hs
                for row in range(ns, ns + nl)
                if nl and row not in ci
            ]
            same_ids = collect(base_dir, p, str(base_dir / "src")) == collect(
                REPO, p, str(REPO / "src")
            )
            ok = [not bad, not golden, same_ids]
            report.append(
                f"§54.7  {p}: (1) import lines alone "
                f"{'PASS' if ok[0] else 'FAIL ' + ','.join(bad[:8])}"
                f"  (2) goldens identical {'PASS' if ok[1] else 'FAIL'}"
                f"  (3) node ids {'PASS' if ok[2] else 'FAIL'}"
            )
            if not all(ok):
                fails.append(p)
            continue
        if not p.startswith("tests/"):
            continue
        rng = net_ranges(p, c)
        hit = sorted(
            {
                k
                for (_os, _ol, ns, nl) in hunks(p)
                for k, (a, z) in rng.items()
                if ns <= z and ns + max(nl, 1) - 1 >= a
            }
        )
        if not hit:
            continue
        ok1 = all(norm(segment(b, k)) == norm(segment(c, k)) for k in hit)
        ok2 = assertions(b) == assertions(c)
        whole_file_clean = norm(b) == norm(c)
        report.append(
            f"§60.3  {p} [{'; '.join(hit)}]: (1) reverse diff empty inside the net "
            f"entry {'PASS' if ok1 else 'FAIL'}"
            f"  (2) assertions identical under substitution {'PASS' if ok2 else 'FAIL'}"
            + (
                ""
                if whole_file_clean
                else "  [the file also carries a non-substitution hunk OUTSIDE its net "
                "entries: allowed-and-reported / exception]"
            )
        )
        if not (ok1 and ok2):
            fails.append(p)
    # (3) for everything else: the floor still collects, and no net entry outside the
    # footprint moved
    ids = collect(REPO, "tests", str(REPO / "src"))
    collected = work / "collected_candidate.txt"
    collected.write_text("\n".join(sorted(ids)) + "\n")
    fl = subprocess.run(
        [sys.executable, str(HERE / "floor_check.py"), str(collected)],
        capture_output=True,
        text=True,
    )
    floor_line = fl.stdout.strip().splitlines()[-1] if fl.stdout else fl.stderr
    report.append("off-limits (floor): " + floor_line)
    report.append(f"net files in the diff: whole={[p for p in changed if p in WHOLE]}")
    if fl.returncode:
        fails.append("floor")
    print("\n".join(report))
    print("PETITION:", "PASS" if not fails else f"FAIL {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    _work = pathlib.Path(tempfile.mkdtemp(prefix="petition_"))
    try:
        _rc = check(_work)
    finally:
        shutil.rmtree(_work)
    sys.exit(_rc)
