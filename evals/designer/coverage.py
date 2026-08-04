"""Designer-context coverage probe over saved draws (dev tooling).

No LLM. Measures whether the *user-facing substance* of a draw's AI catalog
actually reaches the Designer — the input side of the Designer lever. The mock
itself is generative and not cheaply measurable, but the note the distiller
hands to Designer is deterministic, so this probe reads that note and reports
how completely it carries the surfaces Designer must build.

It reads a saved draw dir (``vision.json`` + ``ai_features.json``), runs the
real ``_ai_features_for_designer`` projection, and reports, per draw:

  * surfaces        — top-level ``scope == "feature"`` non-infrastructure nodes
                      (the user-facing surfaces Designer must design).
  * in_note         — of those, how many appear in the distiller note.
  * with_io         — surfaces carrying both inputs and a primary output (enough
                      to design a real form + result, not just a label).
  * vision_linked   — surfaces tied to at least one vision feature.
  * nested_members  — non-infra sub_features nested under a surface vs. dropped.
  * vision_features — vision key_features_mvp, split into those served by some
                      AI surface vs. those with none (which the prompt, not the
                      catalog, must cover as non-AI user-facing features).

Run with the package importable (from the repo root):

    uv run python evals/designer/coverage.py <draw_dir> [<draw_dir> ...]

where each dir holds ``vision.json`` + ``ai_features.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spec4.agents._utils import _ai_features_for_designer

_INFRA = "infrastructure"


def _is_infra(f: dict[str, Any]) -> bool:
    return f.get("tier") == _INFRA or f.get("kind") == _INFRA


def _vision_feature_names(vision: dict[str, Any]) -> list[str]:
    """Pull key_features_mvp names from a vision, tolerating envelope shapes."""
    vs = vision.get("vision_statement", vision)
    block = vs.get("vision", vs) if isinstance(vs, dict) else {}
    feats = block.get("key_features_mvp") or []
    names: list[str] = []
    for entry in feats:
        if isinstance(entry, dict):
            # {"policy_answers": {...}} single-key shape, or {"name": "..."}.
            if "name" in entry and isinstance(entry["name"], str):
                names.append(entry["name"])
            elif len(entry) == 1:
                names.append(next(iter(entry)))
        elif isinstance(entry, str):
            names.append(entry)
    return names


@dataclass
class DrawReport:
    name: str
    surfaces: int
    in_note: int
    with_io: int
    vision_linked: int
    members_total: int
    members_nested: int
    vision_features: int
    vision_served: int
    unserved_features: list[str]


def analyse(draw_dir: Path) -> DrawReport:
    vision = json.loads((draw_dir / "vision.json").read_text(encoding="utf-8"))
    catalog = json.loads((draw_dir / "ai_features.json").read_text(encoding="utf-8"))
    features: list[dict[str, Any]] = catalog.get("ai_features") or []

    surfaces = [
        f for f in features if f.get("scope") == "feature" and not _is_infra(f)
    ]
    surface_names = {f.get("name", "") for f in surfaces}
    note = _ai_features_for_designer(catalog)

    in_note = sum(1 for f in surfaces if f"### `{f.get('name', '')}`" in note)
    with_io = sum(
        1
        for f in surfaces
        if (f.get("inputs") or [])
        and isinstance(f.get("outputs"), dict)
        and (f["outputs"].get("primary"))
    )
    vision_linked = sum(1 for f in surfaces if f.get("linked_vision_features"))

    members = [
        f
        for f in features
        if f.get("scope") == "sub_feature" and not _is_infra(f)
    ]
    members_nested = sum(
        1 for m in members if (m.get("composed_under") or "") in surface_names
    )

    served: set[str] = set()
    for f in surfaces:
        served.update(f.get("linked_vision_features") or [])
    vfeats = _vision_feature_names(vision)
    unserved = [v for v in vfeats if v not in served]

    return DrawReport(
        name=draw_dir.name,
        surfaces=len(surfaces),
        in_note=in_note,
        with_io=with_io,
        vision_linked=vision_linked,
        members_total=len(members),
        members_nested=members_nested,
        vision_features=len(vfeats),
        vision_served=len(vfeats) - len(unserved),
        unserved_features=unserved,
    )


def _pct(n: int, d: int) -> str:
    return f"{(100 * n / d):.0f}%" if d else "n/a"


def format_report(r: DrawReport) -> str:
    lines = [
        f"=== {r.name} ===",
        f"  surfaces (user-facing features):  {r.surfaces}",
        f"  reached Designer note:            {r.in_note}/{r.surfaces} "
        f"({_pct(r.in_note, r.surfaces)})",
        f"  with inputs + output (designable):{r.with_io}/{r.surfaces} "
        f"({_pct(r.with_io, r.surfaces)})",
        f"  tied to a vision feature:         {r.vision_linked}/{r.surfaces} "
        f"({_pct(r.vision_linked, r.surfaces)})",
        f"  sub_features nested vs dropped:   {r.members_nested}/{r.members_total} "
        f"nested",
        f"  vision features served by AI:     {r.vision_served}/{r.vision_features}",
    ]
    if r.unserved_features:
        lines.append(
            "  non-AI vision features (prompt must cover): "
            + ", ".join(r.unserved_features)
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "draw_dirs",
        nargs="+",
        type=Path,
        help="draw dir(s), each holding vision.json + ai_features.json",
    )
    args = parser.parse_args(argv)

    reports: list[DrawReport] = []
    for d in args.draw_dirs:
        if not (d / "ai_features.json").exists():
            print(f"skip {d}: no ai_features.json", file=sys.stderr)
            continue
        r = analyse(d)
        reports.append(r)
        print(format_report(r))
        print()

    if len(reports) > 1:
        tot_s = sum(r.surfaces for r in reports)
        tot_n = sum(r.in_note for r in reports)
        tot_io = sum(r.with_io for r in reports)
        tot_l = sum(r.vision_linked for r in reports)
        print("=== summary across draws ===")
        print(f"  surfaces:                {tot_s}")
        print(f"  reached note:            {tot_n}/{tot_s} ({_pct(tot_n, tot_s)})")
        print(f"  designable (I/O):        {tot_io}/{tot_s} ({_pct(tot_io, tot_s)})")
        print(f"  vision-linked:           {tot_l}/{tot_s} ({_pct(tot_l, tot_s)})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())