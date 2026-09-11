"""Append a report section to the record verbatim, and prove nothing else moved.

    append_section.py FILE SECTION.md      append SECTION to FILE
    append_section.py --guard BASE FILE    audit FILE's diff against BASE

Append: the existing bytes of FILE are never rewritten. The section goes on the end
exactly as written; the only byte this script may add is the one blank-line separator
when the section does not already begin with one. It aborts rather than repair
anything it did not write: a FILE not ending in a newline, a section not ending in one,
or a section holding a run of blank lines (fix the section, not the record).
Afterwards it re-reads FILE and checks the old content is a byte-for-byte prefix.

Guard: lists every hunk of `git diff -U0 BASE -- FILE` that deletes lines, and exits
non-zero if any deleted line is blank or whitespace-only -- whitespace the ruled edits
never touch -- so a commit cannot carry it unnoticed.
"""

import hashlib
import pathlib
import re
import subprocess
import sys


def append(file: str, section: str) -> int:
    path = pathlib.Path(file)
    before = path.read_bytes()
    text = pathlib.Path(section).read_bytes()
    if not before.endswith(b"\n"):
        sys.exit(f"ABORT: {file} does not end in a newline; not repairing it")
    if not text.endswith(b"\n"):
        sys.exit(f"ABORT: {section} does not end in a newline")
    # A run of blank lines in the prose is refused; inside a fenced block it is
    # verbatim output (a diff's whitespace-only context lines) and is kept as is.
    # Each block becomes one placeholder line, not nothing: removing it outright
    # would join the blank line before a fence to the blank line after it.
    prose = re.sub(rb"(?ms)^```.*?^```[^\n]*$", b"<fenced block>", text)
    if re.search(rb"\n[ \t]*\n[ \t]*\n", prose):
        sys.exit(
            f"ABORT: {section} holds a run of blank lines outside a code fence; fix "
            "the section"
        )
    sep = b"" if text.startswith(b"\n") else b"\n"
    with path.open("ab") as fh:
        fh.write(sep + text)
    after = path.read_bytes()
    if not after.startswith(before) or len(after) != len(before) + len(sep) + len(text):
        sys.exit(
            "ABORT: the existing content is not a byte-for-byte prefix of the result"
        )
    digest = hashlib.sha256(before).hexdigest()[:12]
    print(
        f"appended {len(sep) + len(text)} bytes; prior {len(before)} bytes unchanged "
        f"(sha256 {digest}, verified as prefix)"
    )
    return 0


def guard(base: str, file: str) -> int:
    diff = subprocess.run(
        ["git", "diff", "-U0", base, "--", file],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    hunks, cur = [], None
    for line in diff.splitlines():
        if line.startswith("@@"):
            cur = [line, []]
            hunks.append(cur)
        elif cur and line.startswith("-") and not line.startswith("---"):
            cur[1].append(line[1:])
    bad = 0
    for head, dels in hunks:
        if not dels:
            continue
        blank = [d for d in dels if not d.strip()]
        bad += len(blank)
        flag = f"  ABORT: {len(blank)} blank line(s) deleted" if blank else ""
        print(f"{head.split('@@')[1].strip()}: {len(dels)} deleted{flag}")
        for d in dels:
            print(f"    - {d[:100]}")
    deleting = sum(1 for _, dels in hunks if dels)
    print(f"hunks deleting lines: {deleting}; blank deletions: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.argv[1] == "--guard":
        sys.exit(guard(sys.argv[2], sys.argv[3]))
    sys.exit(append(sys.argv[1], sys.argv[2]))
