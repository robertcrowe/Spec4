"""The regression floor, in both halves
(cleanup-complete:CLEANUP_INVENTORY.md 50.3, 50.5(a)).

    uv run python scripts/cleanup/floor_check.py [COLLECTED.txt]

COLLECTED.txt holds node ids, one per line, as `pytest --collect-only -q` prints them.
Without it, the check runs that collection itself from the repo root.

The floor is data/floor.json. Tier A is the seven whole-file entries, with every node id
they collect, and the named tier-A and ordering node ids. Tier B is the node ids of the
protected classes. Every whole-file entry must collect something, and every named node
id must still collect, as itself or in a parametrised form `id[...]`. Exit 1 on any
failure. The expected counts are printed beside the actual ones; they are not the test.
"""

import collections
import json
import pathlib
import subprocess
import sys

FLOOR = json.loads((pathlib.Path(__file__).parent / "data" / "floor.json").read_text())


def collected() -> list[str]:
    if len(sys.argv) > 1:
        return pathlib.Path(sys.argv[1]).read_text().splitlines()
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
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
        capture_output=True,
        text=True,
        cwd=root,
    ).stdout
    return [line for line in out.splitlines() if "::" in line]


def main() -> int:
    coll = collected()
    byfile = collections.Counter(n.split("::")[0] for n in coll)
    present = set(coll)
    whole = FLOOR["whole_file"]
    named, tier_b = set(FLOOR["tier_a_named"]), set(FLOOR["tier_b"])
    expect = FLOOR["expect"]

    def collects(nid: str) -> bool:
        return nid in present or any(c.startswith(nid + "[") for c in coll)

    fail = [f"whole-file entry collects nothing: {f}" for f in whole if byfile[f] == 0]
    fail += [
        f"node id no longer collects: {nid}"
        for nid in sorted(named | tier_b)
        if not collects(nid)
    ]
    wf = sum(byfile[f] for f in whole)
    print(
        f"whole-file entries   : {wf} node ids across {len(whole)} files "
        f"(expect {expect['whole_file_ids']})"
    )
    print(
        f"tier-A + ordering    : {len(named)} node ids (expect "
        f"{expect['tier_a_named']})"
    )
    print(f"tier-B               : {len(tier_b)} node ids (expect {expect['tier_b']})")
    print(
        f"floor total          : {wf + len(named) + len(tier_b)} (expect "
        f"{expect['total']})"
    )
    print(f"FAILURES             : {len(fail)}")
    for x in fail:
        print("   !", x)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
