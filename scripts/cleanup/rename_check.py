"""The §60.2 rename check.

    python scripts/cleanup/rename_check.py REPO BASE MAPPING.json [COMMIT]

BASE is compared with COMMIT, or with REPO's working tree when COMMIT is not given.
MAPPING.json is [[old, new], ...]. Both sides are copied to a temporary directory and
get the same treatment, then `diff -ru` must be empty:
  1. the reverse substitution new -> old, word-boundary, over every text file except
     CLEANUP_INVENTORY.md (applied to BASE too, so a token `new` that already existed
     before the rename cancels instead of showing as a false diff);
  2. alias fold: `X as X` -> `X` (undoes §54.7's `new as old` import form);
  3. `ruff format` with skip-magic-trailing-comma, so a line the rename let ruff join
     or split compares by content, not by layout.
A non-empty diff means the commit did more than rename. REPO itself is only read.
"""

import io
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

REPO, BASE, MAPF = sys.argv[1], sys.argv[2], sys.argv[3]
COMMIT = sys.argv[4] if len(sys.argv) > 4 else None
MAP = [tuple(x) for x in json.load(open(MAPF))]
_VENV_RUFF = pathlib.Path(REPO) / ".venv" / "bin" / "ruff"
RUFF = str(_VENV_RUFF.resolve()) if _VENV_RUFF.exists() else shutil.which("ruff")
if RUFF is None:
    sys.exit("rename check: no ruff found, in the repo's .venv or on PATH")


def export(rev, dest):
    dest.mkdir()
    data = subprocess.run(
        ["git", "-C", REPO, "archive", rev], capture_output=True, check=True
    ).stdout
    tarfile.open(fileobj=io.BytesIO(data)).extractall(dest, filter="data")


def copy_worktree(dest):
    dest.mkdir()
    names = subprocess.run(
        ["git", "-C", REPO, "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\n")
    for n in filter(None, names):
        src = pathlib.Path(REPO) / n
        if src.is_file():
            (dest / n).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / n)


def tok(n):
    return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])")


def normalise(root):
    for f in root.rglob("*"):
        if not f.is_file() or f.name == "CLEANUP_INVENTORY.md":
            continue
        raw = f.read_bytes()
        if b"\0" in raw[:8192]:
            continue
        t = raw.decode()
        u = t
        for old, new in MAP:
            u = tok(new).sub(old, u)
        if f.suffix == ".py":
            u = re.sub(r"\b([A-Za-z_]\w*) as \1\b", r"\1", u)
        if u != t:
            f.write_text(u)
    subprocess.run(
        [RUFF, "format", "--quiet", "--no-cache", "--config"]
        + ["format.skip-magic-trailing-comma = true", str(root)],
        cwd=root,
        capture_output=True,
    )


work = pathlib.Path(tempfile.mkdtemp(prefix="rcheck_"))
A, B = work / "base", work / "cand"
try:
    export(BASE, A)
    if COMMIT:
        export(COMMIT, B)
    else:
        copy_worktree(B)
    normalise(A)
    normalise(B)
    d = subprocess.run(
        ["diff", "-ru", "--exclude=CLEANUP_INVENTORY.md", "--exclude=__pycache__"]
        + ["--exclude=.ruff_cache", str(A), str(B)],
        capture_output=True,
        text=True,
    ).stdout
finally:
    shutil.rmtree(work)
empty = "rename check: EMPTY -- the change is identifier substitution alone"
print(d.replace(str(A), "base").replace(str(B), "cand") or empty)
sys.exit(1 if d else 0)
