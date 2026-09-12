"""Phase-file assembly and parsing: the Markdown-with-JSON-frontmatter format
the coding agent reads and Spec4 round-trips through.

Split out of :mod:`spec4.project_manager` in cleanup Phase 4b; that module
re-exports every name defined here, so both import paths resolve to the same
object.
"""

from __future__ import annotations

import json
import re
from typing import Any

from spec4.design_manifest import (
    surface_detail_lines,
    surfaces_for_declarations,
)
from spec4.stack_routing import (
    baseline_library_names,
    entries_for_declarations,
    nfr_threads,
)
from spec4.feature_specs import (
    PHASE_EXCLUDED_CROSS_CUTTING,
    PHASE_SPEC_FIELDS,
    PHASER_PRODUCT_SPEC_FIELDS,
    render_cross_cutting,
    render_feature_block,
    spec_index,
)


# Phase artifacts are stored as Markdown-with-frontmatter so the coding agent
# consumes them as natural prose, while Spec4 retains a machine-readable copy
# of the full phase object inside the frontmatter for round-trip. The
# frontmatter payload is plain JSON (a YAML superset, so this remains
# compatible with any frontmatter-aware tooling) — no extra YAML dep required.
_PHASE_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# ---------------------------------------------------------------------------
# Phase Markdown serialization
# ---------------------------------------------------------------------------


def _phase_spec_preamble(
    phase: dict[str, Any], context: dict[str, Any] | None
) -> list[str]:
    """Render the binding spec preamble for the features this phase builds.

    The phase file is the *sole* deliverable to the coding agent — it never sees
    ``ai_features.json`` — so the Spec Drafter's output has to reach the build
    through here or not at all. Assembly is deterministic and verbatim: Phaser
    sequences and writes the glue, code attaches the specs, and no model
    re-drafts an already-drafted spec.

    A **preamble**, not an appendix: the coding agent must read what a feature's
    inputs and failure modes are before it reads step 3 of the instructions, and
    a preamble reads as binding where an appendix reads as optional.

    The whole spec attaches at *every* phase that touches the feature — the spec
    describes the finished feature and has no principled cut into "the phase-2
    half". A phase's partial coverage is stated in Phaser's ``scope_note``, never
    by slicing the spec. Duplication across files is cheap; a dangling
    cross-phase reference would break the self-containment that makes each phase
    handable to the coder alone.

    Specs are resolved from ``context["ai_features"]`` at render time rather than
    frozen into the phase dict, so they are stored once and cannot drift from the
    catalog. ``context`` is a bundle (D-PS11) so later consumers — a StackAdvisor
    stack↔feature linkage, say — can be added without re-breaking every caller.
    Returns ``[]`` when the phase declares no features or no catalog is supplied.
    """
    feature_decls, capability_decls = _phase_declarations(phase)
    if not feature_decls and not capability_decls:
        return []

    ai_index = spec_index((context or {}).get("ai_features"))
    product_index = _product_spec_index(context)
    declared_feature_ids = {str(d.get("id")) for d in feature_decls if d.get("id")}
    declared_capability_ids = {
        str(d.get("id")) for d in capability_decls if d.get("id")
    }

    product_blocks = _product_feature_blocks(feature_decls, product_index)
    surface_blocks = _ui_surface_blocks(
        context, declared_feature_ids, declared_capability_ids
    )
    ai_blocks = _ai_capability_blocks(capability_decls, ai_index, declared_feature_ids)

    if not product_blocks and not surface_blocks and not ai_blocks:
        return []

    lines = [
        "## Feature Specifications",
        "",
        "These specifications are authoritative for this phase. Implement to "
        "them; the instructions below tell you how and in what order.",
        "",
        *product_blocks,
        *surface_blocks,
        *ai_blocks,
    ]
    # Project-wide AI decisions, rendered only where AI capabilities are
    # actually being built (D-PH5 gate — cross-cutting is catalog-level
    # guidance and has no place in a product-only phase). `provider_strategy`
    # is excluded — StackAdvisor's `tech_stack_spec` above is the ratified
    # stack authority and must not be contradicted here.
    if ai_blocks:
        lines.extend(
            render_cross_cutting(
                (context or {}).get("ai_features", {}).get("cross_cutting"),
                exclude=PHASE_EXCLUDED_CROSS_CUTTING,
            )
        )
    return lines


def _phase_declarations(
    phase: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The phase's two declaration arrays, product features and capabilities."""
    # D-PH2/D-PH5a: two declaration arrays, two spec altitudes, each attached
    # from its own source. `features[]` attaches the Brainstormer behavioural
    # spec (what the product feature is and when it is done); `capabilities[]`
    # attaches the Agentifier implementation spec (how the AI capability is
    # built at its tier). Never merged: a phase building a feature AND the
    # capability serving it gets both blocks, the serves-relation stated on
    # the capability side. The legacy `or features` fallback keeps pre-D-PH2
    # sets rendering (AI ids lived in features[] then); either lookup simply
    # misses for ids from the other era's space.
    feature_decls = [d for d in (phase.get("features") or []) if isinstance(d, dict)]
    # Era detection is KEY PRESENCE, not truthiness: a new-schema phase with
    # an empty `capabilities` array declares no capabilities — falling back to
    # `features[]` there would read product ids against the AI catalog and
    # resurrect the collision misread the two-array schema exists to kill.
    legacy = "capabilities" not in phase
    capability_decls = [
        d
        for d in (
            (phase.get("features") if legacy else phase.get("capabilities")) or []
        )
        if isinstance(d, dict)
    ]
    return feature_decls, capability_decls


def _product_spec_index(context: dict[str, Any] | None) -> dict[str, Any]:
    """Product feature specs from ``context``, keyed by id."""
    product_index = {
        str(f["id"]): f
        for f in (((context or {}).get("feature_specs") or {}).get("features") or [])
        if isinstance(f, dict) and f.get("id")
    }
    return product_index


def _decl_heading(name: str, altitude: str, decl: dict[str, Any]) -> list[str]:
    role = str(decl.get("role") or "").strip()
    heading = f"### {name} — {altitude}"
    if role:
        heading += f" — {role} in this phase"
    lines = [heading, ""]
    scope_note = str(decl.get("scope_note") or "").strip()
    if scope_note:
        lines.append(f"*Scope for this phase: {scope_note}*")
        lines.append("")
    return lines


def _product_feature_blocks(
    feature_decls: list[dict[str, Any]], product_index: dict[str, Any]
) -> list[str]:
    """Product feature blocks (D-PH5a), one per resolvable declaration."""
    product_blocks: list[str] = []
    for decl in feature_decls:
        feature = product_index.get(str(decl.get("id") or ""))
        if feature is None:
            continue  # unknown/legacy id: coverage owns validation
        name = feature.get("name") or decl.get("id")
        product_blocks.extend(_decl_heading(str(name), "product feature", decl))
        product_blocks.extend(
            render_feature_block(
                feature, fields=PHASER_PRODUCT_SPEC_FIELDS, include_graph=False
            )
        )
        deps = [
            str(d).strip()
            for d in (feature.get("dependencies") or [])
            if str(d).strip()
        ]
        if deps:
            product_blocks.append(
                f"- depends on: {', '.join(deps)} (build these no later than "
                f"`{decl.get('id')}`)"
            )
        entities = [
            str(e) for e in (feature.get("entities") or []) if isinstance(e, str)
        ]
        if entities:
            product_blocks.append(f"- entities: {', '.join(entities)}")
        product_blocks.append("")
    return product_blocks


def _ui_surface_blocks(
    context: dict[str, Any] | None,
    declared_feature_ids: set[str],
    declared_capability_ids: set[str],
) -> list[str]:
    """UI surfaces block (D-PH5b/c), grouped by realized catalog surface."""
    surface_blocks: list[str] = []
    attached = surfaces_for_declarations(
        (context or {}).get("manifest"),
        declared_feature_ids,
        declared_capability_ids,
    )
    if attached:
        surface_blocks.append("### UI surfaces for this phase (from the design)")
        surface_blocks.append("")
        by_catalog: dict[str, list[dict[str, Any]]] = {}
        plain: list[dict[str, Any]] = []
        for rec in attached:
            cid = str(rec["surface"].get("catalog_surface_id") or "")
            if cid:
                by_catalog.setdefault(cid, []).append(rec)
            else:
                plain.append(rec)
        for rec in plain:
            surface_blocks.extend(surface_detail_lines(rec["surface"]))
        for cid, recs in by_catalog.items():
            surface_blocks.append(
                f"The following surface(s) realize the AI capability `{cid}` "
                "— one unit of work; the surfaces are views onto it:"
            )
            for rec in recs:
                surface_blocks.extend(surface_detail_lines(rec["surface"]))
        surface_blocks.append("")
    return surface_blocks


def _ai_capability_blocks(
    capability_decls: list[dict[str, Any]],
    ai_index: dict[str, Any],
    declared_feature_ids: set[str],
) -> list[str]:
    """AI capability blocks at the existing altitude, serves-relation stated."""
    ai_blocks: list[str] = []
    for decl in capability_decls:
        feature = ai_index.get(str(decl.get("id") or ""))
        if feature is None:
            continue  # unknown id: _phase_coverage fails the set before here
        name = feature.get("name") or decl.get("id")
        ai_blocks.extend(_decl_heading(str(name), "AI capability", decl))
        grounding = feature.get("vision_grounding") or {}
        served = sorted(
            {
                str(sf.get("id"))
                for sf in (grounding.get("served_features") or [])
                if isinstance(sf, dict) and sf.get("id")
            }
            & declared_feature_ids
        )
        if served:
            ai_blocks.append(
                "Serves product feature(s): "
                + ", ".join(f"`{s}`" for s in served)
                + " (specified above)."
            )
            ai_blocks.append("")
        ai_blocks.extend(render_feature_block(feature, fields=PHASE_SPEC_FIELDS))
    return ai_blocks


def _declared_ids(phase: dict[str, Any], key: str) -> set[str]:
    """Ids a phase declares in one array (two-array schema, D-PH2a)."""
    return {
        str(d.get("id"))
        for d in (phase.get(key) or [])
        if isinstance(d, dict) and d.get("id")
    }


def _phase_stack_lines(
    phase: dict[str, Any], context: dict[str, Any] | None
) -> list[str]:
    """Deterministic stack routing for one phase's Tech Stack section (D-PH3).

    Renders the serving entries whose ``serves_features`` /
    ``serves_capabilities`` intersect this phase's declarations (each key
    against its own array), then the project-wide baseline staples that render
    in every phase. Renderer-added body only — the frontmatter stays the
    model's artifact verbatim. Returns ``[]`` when the context carries no
    stack (older sessions), so a stack-less render is unchanged.
    """
    stack = (context or {}).get("stack")
    if not stack:
        return []
    routed = entries_for_declarations(
        stack,
        _declared_ids(phase, "features"),
        _declared_ids(phase, "capabilities"),
    )
    baseline = baseline_library_names(stack)
    if not routed and not baseline:
        return []
    lines: list[str] = []
    if routed:
        lines.append(
            "**Approved stack for this phase's declared work** "
            "(deterministic, from the stack spec):"
        )
        lines.append("")
        for rec in routed:
            label = rec["label"]
            if rec["section"] and rec["section"] not in label:
                label = f"{label} ({rec['section']})"
            served = ", ".join(f"`{m}`" for m in rec["matched"])
            purpose = str(rec["entry"].get("purpose") or "").strip()
            detail = f": {purpose}" if purpose else ""
            lines.append(f"- {label}{detail} — serves {served}")
        lines.append("")
    if baseline:
        lines.append("**Project-wide stack** (applies to every phase):")
        lines.append("")
        lines.extend(f"- {name}" for name in baseline)
        lines.append("")
    return lines


def _phase_nfr_lines(
    phase: dict[str, Any], context: dict[str, Any] | None
) -> list[str]:
    """Deterministic NFR threading for one phase's Verification section (D-PH4).

    A claimed goal threads into every phase whose declarations intersect the
    claiming entries' served ids; a goal claimed only by global entries (no
    serves keys) threads into the final phase as project-wide acceptance.
    Orphaned goals never appear. Returns ``[]`` when nothing threads here.
    """
    stack = (context or {}).get("stack")
    specs = (context or {}).get("feature_specs")
    if not stack or not specs:
        return []
    features = _declared_ids(phase, "features")
    capabilities = _declared_ids(phase, "capabilities")
    number = phase.get("phase_number")
    total = phase.get("total_phases")
    is_final = isinstance(number, int) and isinstance(total, int) and number == total
    hits: list[str] = []
    for thread in nfr_threads(stack, specs):
        if thread["global"]:
            if not is_final:
                continue
            scope = "project-wide acceptance"
        else:
            matched = (thread["serves_features"] & features) | (
                thread["serves_capabilities"] & capabilities
            )
            if not matched:
                continue
            scope = "delivered by " + ", ".join(thread["claimers"])
        hits.append(f"- `{thread['nfr_id']}`: {thread['goal']} — {scope}")
    if not hits:
        return []
    return [
        "",
        "**Non-functional acceptance** (deterministic, from the stack spec):",
        "",
        *hits,
        "",
    ]


def render_phase_markdown(
    phase: dict[str, Any], context: dict[str, Any] | None = None
) -> str:
    """Render a phase dict as Markdown with JSON frontmatter.

    Frontmatter carries the canonical structured payload (full round-trip);
    the body renders the same fields as prose for the coding agent, plus the
    verbatim spec preamble resolved from ``context`` (see
    ``_phase_spec_preamble``). ``context`` defaults to ``None``, which renders
    exactly as before — the round-trip through ``parse_phase_markdown`` reads
    only the frontmatter, so a spec-less render loses nothing.
    """
    frontmatter = json.dumps(phase, indent=2, ensure_ascii=False)

    number = phase.get("phase_number", "?")
    total = phase.get("total_phases", "?")
    title = phase.get("phase_title", "")
    summary = phase.get("phase_summary", "")
    tech = phase.get("tech_stack_spec") or {}
    deps = tech.get("dependencies") or []
    configs = tech.get("configurations") or ""
    instructions = phase.get("instructions") or []
    risk = phase.get("risk_assessment") or {}
    bottlenecks = risk.get("potential_bottlenecks", "")
    mitigation = risk.get("mitigation_strategy", "")
    verification = phase.get("verification", "")
    references = phase.get("references") or []

    lines: list[str] = [
        "---",
        frontmatter,
        "---",
        "",
        f"# Phase {number} of {total}: {title}".rstrip(": "),
        "",
        summary,
        "",
    ]
    lines.extend(_phase_spec_preamble(phase, context))
    _render_tech_stack_section(phase, context, deps, configs, lines)
    _render_instructions_section(instructions, lines)
    _render_risk_section(bottlenecks, mitigation, lines)
    _render_verification_section(phase, context, verification, lines)
    _render_references_section(references, lines)

    return "\n".join(lines).rstrip() + "\n"


def _render_tech_stack_section(
    phase: dict[str, Any],
    context: dict[str, Any] | None,
    deps: Any,
    configs: Any,
    lines: list[str],
) -> None:
    """The ``## Tech Stack`` section: dependencies, configurations, stack routing."""
    lines.extend(
        [
            "## Tech Stack",
            "",
        ]
    )
    if deps:
        lines.append("**Dependencies:**")
        lines.append("")
        lines.extend(f"- {d}" for d in deps)
        lines.append("")
    if configs:
        lines.append(f"**Configurations:** {configs}")
        lines.append("")
    lines.extend(_phase_stack_lines(phase, context))


def _render_instructions_section(instructions: Any, lines: list[str]) -> None:
    """The ``## Instructions`` numbered list."""
    lines.append("## Instructions")
    lines.append("")
    for idx, step in enumerate(instructions, start=1):
        lines.append(f"{idx}. {step}")
    lines.append("")


def _render_risk_section(bottlenecks: Any, mitigation: Any, lines: list[str]) -> None:
    """The ``## Risk Assessment`` section."""
    lines.append("## Risk Assessment")
    lines.append("")
    if bottlenecks:
        lines.append("**Potential bottlenecks:**")
        lines.append("")
        lines.append(bottlenecks)
        lines.append("")
    if mitigation:
        lines.append("**Mitigation strategy:**")
        lines.append("")
        lines.append(mitigation)
        lines.append("")


def _render_verification_section(
    phase: dict[str, Any],
    context: dict[str, Any] | None,
    verification: Any,
    lines: list[str],
) -> None:
    """The ``## Verification`` section and the NFR lines that follow it."""
    lines.append("## Verification")
    lines.append("")
    lines.append(verification)
    lines.extend(_phase_nfr_lines(phase, context))
    lines.append("")


def _render_references_section(references: Any, lines: list[str]) -> None:
    """The ``## References`` section."""
    if references:
        lines.append("## References")
        lines.append("")
        for ref in references:
            standard = ref.get("standard", "")
            url = ref.get("url", "")
            if standard and url:
                lines.append(f"- [{standard}]({url})")
            elif standard:
                lines.append(f"- {standard}")
        lines.append("")


def parse_phase_markdown(text: str) -> dict[str, Any] | None:
    """Parse a phase Markdown file back into its structured dict.

    Reads only the JSON frontmatter — the prose body is a deterministic
    rendering of the same fields, so re-parsing it would be redundant and
    error-prone. Returns None when no frontmatter is present or it is not
    valid JSON.
    """
    match = _PHASE_FRONTMATTER_RE.match(text)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
