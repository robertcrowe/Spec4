"""Grouping probe over saved Scout+Linker draws (dev tooling).

No LLM. Measures how the Linker and Composer GROUP a draw's surfaced candidates:
how many are coordinators, how many are members composed under a coordinator, and
how many are left standalone — the direct read on whether the anti-fragmentation
grouping is working. Reads a saved draw dir (``vision.json`` + ``ai_features.json``),
reuses the fan-out baseline for candidates-per-vision-feature context, and reports
the grouping structure per draw plus a summary across draws.

Roles (per surfaced candidate, from its ``composed_under`` edge):

  * coordinator — referenced by at least one member; not itself a member.
  * member      — its ``composed_under`` resolves to a coordinator in the draw.
  * chain       — both a member and a coordinator (a nested/mid-chain node).
  * standalone  — neither a member nor referenced.
  * dangling    — ``composed_under`` names a coordinator absent from the surfaced
                  set (edges are persisted raw; danglers are not trimmed).

Run from ``evals/scout/`` so sibling modules import:

    python grouping_baseline.py <draw_dir> [<draw_dir> ...]

where each dir holds ``vision.json`` + ``ai_features.json``.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fanout_baseline import (  # noqa: E402 (evals/ is a script dir, not a package)
    surfaced_candidates,
    vision_feature_names,
)
from scout_granularity import Fanout, feature_fanout, format_fanout  # noqa: E402

COORDINATOR = "coordinator"
MEMBER = "member"
CHAIN = "chain"
STANDALONE = "standalone"
DANGLING = "dangling"


@dataclass
class Grouping:
    """Per-draw roles plus the coordinator → members structure."""

    role: dict[str, str]  # candidate name -> role
    groups: dict[str, list[str]] = field(default_factory=dict)  # coordinator -> members
    dangling: list[tuple[str, str]] = field(default_factory=list)  # (member, named parent)

    def tally(self) -> dict[str, int]:
        return dict(Counter(self.role.values()))


def classify(cands: list[dict[str, Any]]) -> Grouping:
    """Assign each surfaced candidate a grouping role from its ``composed_under``.

    ``cands`` must already exclude injected infrastructure (see
    :func:`fanout_baseline.surfaced_candidates`).
    """
    by_name = {c.get("name", ""): c for c in cands}
    coordinators = {
        c["composed_under"]
        for c in cands
        if c.get("composed_under") and c["composed_under"] in by_name
    }
    grp = Grouping(role={})
    for c in cands:
        name = c.get("name", "")
        parent = c.get("composed_under") or ""
        if parent:
            if parent not in by_name:
                grp.role[name] = DANGLING
                grp.dangling.append((name, parent))
                continue
            grp.groups.setdefault(parent, []).append(name)
            grp.role[name] = CHAIN if name in coordinators else MEMBER
        else:
            grp.role[name] = COORDINATOR if name in coordinators else STANDALONE
    return grp


def grouping_for_draw(
    vision: dict[str, Any], features: list[dict[str, Any]]
) -> tuple[Fanout, Grouping]:
    """Fan-out (candidates per vision feature) and grouping for one saved draw."""
    names = vision_feature_names(vision)
    surfaced = surfaced_candidates(features)
    covered = [list(c.get("linked_vision_features", []) or []) for c in surfaced]
    return feature_fanout(names, covered, n_runs=1), classify(surfaced)


# --------------------------------------------------------------------------- #
# Loading (trivial; kept local so the probe stands alone)
# --------------------------------------------------------------------------- #
def _load(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())


def _features_list(raw: Any) -> list[dict[str, Any]]:
    return raw.get("ai_features", []) if isinstance(raw, dict) else raw


def _find_draw(directory: Path) -> tuple[Path, Path] | None:
    vision = directory / "vision.json"
    features = directory / "ai_features.json"
    if vision.exists() and features.exists():
        return vision, features
    return None


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _draw_report(label: str, fo: Fanout, grp: Grouping) -> str:
    tally = "  ".join(f"{k}={v}" for k, v in sorted(grp.tally().items()))
    lines = [f"  {label}", format_fanout(fo), f"    roles: {tally}"]
    if grp.groups:
        lines.append(f"    groups ({len(grp.groups)} coordinator(s)):")
        for coord in sorted(grp.groups):
            members = ", ".join(m for m in grp.groups[coord] if m)
            lines.append(f"      {coord}: {members}")
    if grp.dangling:
        lines.append(f"    dangling composed_under ({len(grp.dangling)}):")
        lines.append(
            "\n".join(f"      {m} -> {p} (missing)" for m, p in grp.dangling)
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Grouping probe over saved Scout+Linker draws "
        "(each dir must hold vision.json + ai_features.json)."
    )
    parser.add_argument(
        "draw_dirs",
        nargs="+",
        help="One or more draw directories; the dir name is used as the label.",
    )
    args = parser.parse_args(argv)

    rows: list[tuple[str, Fanout, Grouping]] = []
    print("Grouping structure — Linker/Composer coordination (offline, no LLM)\n")
    for d in args.draw_dirs:
        directory = Path(d)
        found = _find_draw(directory)
        if found is None:
            print(f"  {directory.name}: missing vision.json or ai_features.json — skipped\n")
            continue
        vision = _load(found[0])
        features = _features_list(_load(found[1]))
        fo, grp = grouping_for_draw(vision, features)
        rows.append((directory.name, fo, grp))
        print(_draw_report(directory.name, fo, grp))
        print()

    if rows:
        print("  Summary")
        header = (
            f"    {'draw':<16}{'feat':>5}{'coord':>7}{'member':>8}"
            f"{'chain':>7}{'standalone':>12}{'dangling':>10}"
        )
        print(header)
        for label, fo, grp in rows:
            t = grp.tally()
            print(
                f"    {label:<16}{len(fo.per_feature):>5}{t.get(COORDINATOR, 0):>7}"
                f"{t.get(MEMBER, 0):>8}{t.get(CHAIN, 0):>7}"
                f"{t.get(STANDALONE, 0):>12}{t.get(DANGLING, 0):>10}"
            )
        print(
            "\n    coord+member > 0 ⇒ grouping fired; all-standalone on a fragmented "
            "draw ⇒ the Linker under-grouped; dangling > 0 ⇒ a composed_under edge "
            "names a coordinator that isn't in the surfaced set."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
