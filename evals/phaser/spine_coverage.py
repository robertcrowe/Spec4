"""Phase-set probe: spine coverage and stack attachment (D-PH0c).

Dev tooling under ``evals/``. Never wired into the pipeline.

Reads a saved draw directory (``feature_specs.json`` + ``ai_features.json`` +
``stack.json`` + generated phases) and reports three things:

**[1] PRODUCT PRESENCE** — every product feature in ``feature_specs.json``
(the Brainstormer spine; all are MVP by construction) is declared by some
phase's ``features[]``. Declarations are resolved dual-space (D-PH0b):
AMBIGUOUS ids (present in both the product and capability sets) count as
declared with an annotation, never silently assigned. A draw whose phases
declare only capability-space ids reports every product feature NOT DECLARED —
that gap *is* the pre-round baseline.

**[2] CAPABILITY PRESENCE** — every ``steel_thread``/``mvp`` catalog node
(features and infrastructure) is declared by some phase. The offline twin of
the in-pipeline ``check_phase_coverage`` presence rule.

**[3] STACK ATTACHMENT** — for each stack entry carrying ``serves_features``:
does the entry's name appear in the build text (``tech_stack_spec.dependencies``
+ ``instructions``) of at least one phase that declares a served feature?
Baseline libraries (no ``serves_features``) are reported separately, with a
misattribution flag when a baseline library's name appears in exactly one
feature-declaring phase — a global staple should not read as feature-specific.
The name join is a blunt lexical match (see ``_load.name_matches``); treat
ABSENT rows as leads, not verdicts.

Usage::

    python3 spine_coverage.py <draw_dir>
"""

from __future__ import annotations

import sys
from typing import Any

from _load import (
    AMBIGUOUS,
    CAPABILITY,
    PRODUCT,
    capability_ids,
    catalog_nodes,
    declarations,
    load_draw,
    name_matches,
    phase_build_text,
    phase_rendered_body,
    product_features,
    stack_entries,
)

ENFORCED_PRIORITIES = ("steel_thread", "mvp")


def _declared_ids(decls: list[dict[str, Any]], spaces: tuple[str, ...]) -> set[str]:
    return {d["id"] for d in decls if d["space"] in spaces}


def report(draw_dir: str) -> None:
    draw = load_draw(draw_dir)
    decls = declarations(draw)
    phases = draw["phases"]
    print(f"spine_coverage: {draw_dir}")
    print(f"  phases: {len(phases)}, declarations: {len(decls)}")

    ambiguous = sorted({d["id"] for d in decls if d["space"] == AMBIGUOUS})
    unresolved = sorted({d["id"] for d in decls if d["space"] == "UNRESOLVED"})
    if ambiguous:
        print(f"  AMBIGUOUS ids (both spaces): {', '.join(ambiguous)}")
    if unresolved:
        print(f"  UNRESOLVED ids (neither space): {', '.join(unresolved)}")

    # --- [1] product presence ------------------------------------------------
    print("\n[1] PRODUCT PRESENCE (Brainstormer spine)")
    feats = product_features(draw)
    if not feats:
        print("  UNMEASURABLE — no feature_specs.json in draw")
    else:
        declared_product = _declared_ids(decls, (PRODUCT, AMBIGUOUS))
        covered = 0
        for f in feats:
            fid = str(f.get("id") or "")
            if fid in declared_product:
                note = " (ambiguous id)" if fid in ambiguous else ""
                print(f"  DECLARED     {fid}{note}")
                covered += 1
            else:
                print(f"  NOT DECLARED {fid}")
        print(f"  product coverage: {covered}/{len(feats)}")

    # --- [2] capability presence --------------------------------------------
    print("\n[2] CAPABILITY PRESENCE (AI catalog, steel_thread/mvp)")
    nodes = [
        n
        for n in catalog_nodes(draw)
        if str(n.get("phase_priority") or "") in ENFORCED_PRIORITIES
    ]
    if not capability_ids(draw):
        print("  UNMEASURABLE — empty AI catalog (no-AI draw)")
    elif not nodes:
        print("  no steel_thread/mvp nodes to check")
    else:
        declared_cap = _declared_ids(decls, (CAPABILITY, AMBIGUOUS))
        covered = 0
        for n in nodes:
            nid = str(n.get("id") or "")
            kind = "infra" if n.get("kind") == "infrastructure" else "feature"
            if nid in declared_cap:
                note = " (ambiguous id)" if nid in ambiguous else ""
                print(f"  DECLARED     {nid} [{kind}]{note}")
                covered += 1
            else:
                print(f"  NOT DECLARED {nid} [{kind}]")
        print(f"  capability coverage: {covered}/{len(nodes)}")

    # --- [3] stack attachment -----------------------------------------------
    print("\n[3] STACK ATTACHMENT (serves_features -> declaring phases;")
    print("    blunt lexical name join - ABSENT rows are leads, not verdicts)")
    if not draw.get("stack"):
        print("  UNMEASURABLE — no stack.json in draw")
        return

    # phase number -> product-space ids it declares
    by_phase: dict[int, set[str]] = {}
    for d in decls:
        if d["space"] in (PRODUCT, AMBIGUOUS) and isinstance(d["phase"], int):
            by_phase.setdefault(d["phase"], set()).add(d["id"])

    serving = [e for e in stack_entries(draw) if e["entry"].get("serves_features")]
    attached = 0
    for e in serving:
        served = [str(s) for s in e["entry"]["serves_features"] if s]
        target_phases = sorted(
            n for n, ids in by_phase.items() if any(s in ids for s in served)
        )
        if not target_phases:
            print(
                f"  FEATURE-UNDECLARED {e['label']} "
                f"(serves {', '.join(served)}; no phase declares them)"
            )
            continue
        fm_hit: list[int] = []
        rendered_hit: list[int] = []
        for n in target_phases:
            for p in phases:
                if p.get("phase_number") != n:
                    continue
                if name_matches(e["name"], phase_build_text(p)):
                    fm_hit.append(n)
                elif name_matches(e["name"], phase_rendered_body(p)):
                    rendered_hit.append(n)
        if fm_hit or rendered_hit:
            surfaces = []
            if fm_hit:
                surfaces.append(f"frontmatter {sorted(set(fm_hit))}")
            if rendered_hit:
                surfaces.append(f"rendered {sorted(set(rendered_hit))}")
            print(
                f"  PRESENT  {e['label']} ({'; '.join(surfaces)}) "
                f"(serves {', '.join(served)})"
            )
            attached += 1
        else:
            print(
                f"  ABSENT   {e['label']} (serves {', '.join(served)}; "
                f"declaring phases {target_phases} do not mention it)"
            )
    if serving:
        print(f"  attachment: {attached}/{len(serving)} serving entries present")
    else:
        print("  no stack entries carry serves_features")

    # baseline libraries (global staples): misattribution flag
    libs = (draw["stack"].get("libraries") or []) if draw.get("stack") else []
    baseline = [
        lib for lib in libs
        if isinstance(lib, dict)
        and lib.get("name")
        and not lib.get("serves_features")
    ]
    if baseline:
        print(f"\n  baseline libraries (no serves_features): {len(baseline)}")
        feature_phases = set(by_phase) | {
            d["phase"]
            for d in decls
            if d["space"] in (CAPABILITY, AMBIGUOUS) and isinstance(d["phase"], int)
        }
        for lib in baseline:
            hit = sorted({
                p["phase_number"]
                for p in phases
                if isinstance(p.get("phase_number"), int)
                and name_matches(str(lib["name"]), phase_build_text(p))
            })
            flag = (
                "  <- appears in exactly one feature-declaring phase"
                if len(hit) == 1 and hit[0] in feature_phases
                else ""
            )
            print(f"    {lib['name']}: phases {hit or '[]'}{flag}")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    report(sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())