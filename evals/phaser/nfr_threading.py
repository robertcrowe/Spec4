"""Phase-set probe: NFR threading (D-PH0d).

Dev tooling under ``evals/``. Never wired into the pipeline.

Reads a saved draw directory and follows each non-functional goal along the
route it is meant to travel (vision -> stack rationale -> phase checks):

**[1] DERIVED GOALS** — the ``nfr_<slug>`` ids derived from
``feature_specs.nfr_goals`` by the D-SC2 rule. These are the authoritative id
set; everything else is compared against it.

**[2] STACK CLAIMS** — every id appearing in any stack entry's
``satisfies_nfr``. Claims matching a derived id are CLAIMED; claims matching
none are UNKNOWN (a model-coined id — the D-SC39-style drift signal). Derived
goals no stack entry claims are ORPHANED. An orphan is reported honestly and
is *not* a defect in this probe's eyes: the downstream planner must surface
unclaimed goals, never invent a stack claim for them.

**[3] PHASE THREADING** — for each derived goal, whether its ``nfr_<slug>`` id
string appears anywhere in any phase (build text, verification, risk,
configurations). Pre-round expectation: goals are claimed on the stack side
and threaded 0/N into phases, because nothing consumes the backlink yet.
This is an exact id-string scan, not a semantic one: a phase that satisfies a
goal in prose without citing the id reports NOT THREADED, which is precisely
the legibility gap the Phaser round exists to close.

Usage::

    python3 nfr_threading.py <draw_dir>
"""

from __future__ import annotations

import sys

from _load import (
    derived_nfr_ids,
    load_draw,
    phase_full_text,
    phase_rendered_body,
    stack_entries,
)


def report(draw_dir: str) -> None:
    draw = load_draw(draw_dir)
    print(f"nfr_threading: {draw_dir}")

    derived = derived_nfr_ids(draw)
    print(f"\n[1] DERIVED GOALS ({len(derived)})")
    if not derived:
        print("  UNMEASURABLE — no feature_specs.json nfr_goals in draw")
        return
    for nid, goal in derived.items():
        print(f"  {nid}")
        print(f"    \"{goal}\"")

    print("\n[2] STACK CLAIMS (satisfies_nfr)")
    if not draw.get("stack"):
        print("  UNMEASURABLE — no stack.json in draw")
        claimed: set[str] = set()
    else:
        claims: dict[str, list[str]] = {}
        for e in stack_entries(draw):
            for nid in e["entry"].get("satisfies_nfr") or []:
                claims.setdefault(str(nid), []).append(e["name"])
        claimed = {nid for nid in claims if nid in derived}
        for nid, entries in sorted(claims.items()):
            tag = "CLAIMED" if nid in derived else "UNKNOWN (matches no derived goal)"
            print(f"  {tag}  {nid}")
            print(f"    by: {', '.join(sorted(set(entries)))}")
        orphans = [nid for nid in derived if nid not in claims]
        for nid in orphans:
            print(f"  ORPHANED  {nid} (no stack entry claims it)")
        print(
            f"  claimed {len(claimed)}/{len(derived)}; "
            f"orphaned {len(orphans)}; "
            f"unknown claims {sum(1 for n in claims if n not in derived)}"
        )

    print("\n[3] PHASE THREADING (exact nfr_<slug> id-string scan)")
    if not draw["phases"]:
        print("  UNMEASURABLE — no phase files in draw")
        return
    threaded = 0
    for nid in derived:
        fm_hit = sorted({
            p["phase_number"]
            for p in draw["phases"]
            if isinstance(p.get("phase_number"), int)
            and nid in phase_full_text(p)
        })
        rendered_hit = sorted({
            p["phase_number"]
            for p in draw["phases"]
            if isinstance(p.get("phase_number"), int)
            and p["phase_number"] not in fm_hit
            and nid in phase_rendered_body(p)
        })
        status = "CLAIMED" if nid in claimed else "ORPHANED"
        if fm_hit or rendered_hit:
            surfaces = []
            if fm_hit:
                surfaces.append(f"frontmatter {fm_hit}")
            if rendered_hit:
                surfaces.append(f"rendered {rendered_hit}")
            print(f"  THREADED      {nid} -> {'; '.join(surfaces)} [{status}]")
            threaded += 1
        else:
            print(f"  NOT THREADED  {nid} [{status}]")
    print(f"  threading: {threaded}/{len(derived)} goals reachable in phases")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    report(sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())