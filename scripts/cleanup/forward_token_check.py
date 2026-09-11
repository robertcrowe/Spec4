"""Token-level forward check: every change from BASE to the working tree is old -> new.

    python scripts/cleanup/forward_token_check.py REPO BASE MAPPING.json

The §60.2 rename check reverse-substitutes new -> old on both sides, so it cannot see
an occurrence of a new name that already existed at BASE -- a clash such as a
same-named public function in another module. This check diffs token streams hunk by
hunk (`git diff -U0 BASE`, CLEANUP_INVENTORY.md excluded): every replaced run must be
the batch's old names mapped positionally to their new names. Everything else is
printed with its line numbers:
  layout  -- insert/delete of only `(`, `)` or `,` (ruff's re-wrap and magic comma);
  OTHER   -- anything else: an insert, a delete, or a replace that is not old -> new.
Exits non-zero when any OTHER is found.
"""

import difflib
import json
import re
import subprocess
import sys

TOKEN = re.compile(r"\w+|[^\w\s]")
LAYOUT = {"(", ")", ","}


def hunks(repo: str, base: str):
    out = subprocess.run(
        [
            "git",
            "-C",
            repo,
            "diff",
            "-U0",
            "--no-color",
            base,
            "--",
            ".",
            ":!CLEANUP_INVENTORY.md",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    f, h, found = None, None, []
    for line in out.splitlines():
        if line.startswith("+++ "):
            f = line[6:]
        elif line.startswith("--- "):
            continue
        elif line.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            h = {"file": f, "old": int(m[1]), "new": int(m[2]), "a": [], "b": []}
            found.append(h)  # filled below; handed out only once complete
        elif h is not None and line.startswith("-"):
            h["a"].append(line[1:])
        elif h is not None and line.startswith("+"):
            h["b"].append(line[1:])
    return found


def main() -> int:
    repo, base, mapping = sys.argv[1], sys.argv[2], dict(json.load(open(sys.argv[3])))
    n_h = n_sub = n_layout = n_alias = n_other = 0
    for h in hunks(repo, base):
        n_h += 1
        a, b = TOKEN.findall("\n".join(h["a"])), TOKEN.findall("\n".join(h["b"]))
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, a, b, autojunk=False
        ).get_opcodes():
            if op == "equal":
                continue
            ra, rb = a[i1:i2], b[j1:j2]
            if (
                op == "replace"
                and len(ra) == len(rb)
                and all(mapping.get(x) == y for x, y in zip(ra, rb))
            ):
                n_sub += len(ra)
                continue
            if op in ("insert", "delete") and set(ra + rb) <= LAYOUT:
                n_layout += 1
                print(f"layout {h['file']}:-{h['old']}/+{h['new']}: {op} {ra or rb}")
                continue
            # ruff re-wrap around a substituted name: equal once ( ) , are set aside
            sa, sb = (
                [x for x in ra if x not in LAYOUT],
                [x for x in rb if x not in LAYOUT],
            )
            if (
                op == "replace"
                and sa
                and len(sa) == len(sb)
                and all(mapping.get(x) == y for x, y in zip(sa, sb))
            ):
                n_sub += len(sa)
                n_layout += 1
                print(
                    f"layout {h['file']}:-{h['old']}/+{h['new']}: re-wrap around "
                    f"{' '.join(sb)!r}"
                )
                continue
            # §54.7 re-binding `new as old` in a whole-file entry: an insert of `new as`
            # pairs, each followed in b by the old name it re-binds
            if (
                op == "insert"
                and len(sb) % 2 == 0
                and sb
                and all(
                    sb[k + 1] == "as" and sb[k] in mapping.values()
                    for k in range(0, len(sb), 2)
                )
            ):
                n_alias += 1
                print(
                    f"§54.7  {h['file']}:-{h['old']}/+{h['new']}: re-bound "
                    f"{' '.join(sb)!r} (import alias)"
                )
                continue
            n_other += 1
            print(
                f"OTHER  {h['file']}:-{h['old']}/+{h['new']}: {op} {' '.join(ra)!r} "
                f"-> {' '.join(rb)!r}"
            )
    print(
        f"hunks {n_h}; old->new token substitutions {n_sub}; layout {n_layout}; §54.7 "
        f"aliases {n_alias}; OTHER {n_other}"
    )
    return 1 if n_other else 0


if __name__ == "__main__":
    sys.exit(main())
