"""Phase-set probe: design-manifest surface attach (D-PH5e).

Dev tooling under ``evals/``. Never wired into the pipeline.

Reads a saved draw directory (``manifest.json`` + generated phases) and
follows each surface to its phase landing under the D-PH5 attach rule — a
surface reaches a phase when its ``implements_feature_ids`` intersect the
phase's declared product features OR its ``catalog_surface_id`` is among the
phase's declared capabilities:

* ``ATTACHED`` — the surface's name appears in a target phase (surface-tagged:
  ``frontmatter`` = model-authored mention, ``rendered`` = code-attached
  preamble; post-D-PH5 hits are expected ``rendered``).
* ``NOT ATTACHED`` — target phases exist but none mentions the surface.
* ``NO TARGET`` — the surface's feature/capability is declared by no phase
  (e.g. an excluded feature's surface: correct by design, reported honestly).
* ``SEED-ONLY`` — disposition-2 scaffolding (no implements, no catalog id):
  never attached per-phase by design.

Also reports catalog dedup: surfaces sharing a ``catalog_surface_id`` should
land grouped in the same phases (one unit of work, several views).

Usage::

    python3 manifest_attach.py <draw_dir>
"""

from __future__ import annotations

import sys

from _load import (
    AMBIGUOUS,
    CAPABILITY,
    PRODUCT,
    declarations,
    load_draw,
    name_matches,
    phase_build_text,
    phase_rendered_body,
)


def report(draw_dir: str) -> None:
    draw = load_draw(draw_dir)
    manifest = draw.get("manifest")
    print(f"manifest_attach: {draw_dir}")
    if not manifest or not (manifest.get("surfaces") or []):
        print("  UNMEASURABLE — no manifest.json (or no surfaces) in draw")
        return
    if not draw["phases"]:
        print("  UNMEASURABLE — no phase files in draw")
        return

    decls = declarations(draw)
    feature_phases: dict[str, set[int]] = {}
    capability_phases: dict[str, set[int]] = {}
    for d in decls:
        if not isinstance(d["phase"], int):
            continue
        if d["space"] in (PRODUCT, AMBIGUOUS):
            feature_phases.setdefault(d["id"], set()).add(d["phase"])
        if d["space"] in (CAPABILITY, AMBIGUOUS):
            capability_phases.setdefault(d["id"], set()).add(d["phase"])

    attached = not_attached = 0
    catalog_landings: dict[str, list[tuple[str, tuple[int, ...]]]] = {}
    for surface in manifest["surfaces"]:
        if not isinstance(surface, dict):
            continue
        name = str(surface.get("name") or "surface")
        implements = [
            str(x) for x in (surface.get("implements_feature_ids") or []) if x
        ]
        catalog = str(surface.get("catalog_surface_id") or "")
        if not implements and not catalog:
            print(f"  SEED-ONLY     {name} (scaffolding — by design)")
            continue
        targets: set[int] = set()
        for fid in implements:
            targets |= feature_phases.get(fid, set())
        if catalog:
            targets |= capability_phases.get(catalog, set())
        if not targets:
            keys = ", ".join(implements + ([f"catalog:{catalog}"] if catalog else []))
            print(f"  NO TARGET     {name} (no phase declares {keys})")
            continue
        fm_hit = sorted(
            n
            for n in targets
            for p in draw["phases"]
            if p.get("phase_number") == n
            and name_matches(name, phase_build_text(p))
        )
        rendered_hit = sorted(
            n
            for n in targets
            for p in draw["phases"]
            if p.get("phase_number") == n
            and n not in fm_hit
            and name_matches(name, phase_rendered_body(p))
        )
        if fm_hit or rendered_hit:
            surfaces_txt = []
            if fm_hit:
                surfaces_txt.append(f"frontmatter {fm_hit}")
            if rendered_hit:
                surfaces_txt.append(f"rendered {rendered_hit}")
            print(f"  ATTACHED      {name} ({'; '.join(surfaces_txt)})")
            attached += 1
            if catalog:
                catalog_landings.setdefault(catalog, []).append(
                    (name, tuple(sorted(set(fm_hit) | set(rendered_hit))))
                )
        else:
            print(
                f"  NOT ATTACHED  {name} (target phases {sorted(targets)} "
                "do not mention it)"
            )
            not_attached += 1

    print(f"  attach: {attached} attached, {not_attached} not attached")
    for cid, landings in catalog_landings.items():
        if len(landings) > 1:
            phase_sets = {phases for _, phases in landings}
            status = "grouped" if len(phase_sets) == 1 else "SPLIT"
            names = ", ".join(n for n, _ in landings)
            print(f"  catalog `{cid}`: {len(landings)} surfaces ({names}) — {status}")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    report(sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())