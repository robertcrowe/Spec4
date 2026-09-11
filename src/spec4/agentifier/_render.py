"""Agentifier renderers, priority parsing, and the revision snapshot.

Cleanup Phase 4i moved the pure edges of ``agentifier.py`` here: every
``_format_*`` renderer, ``build_ai_features``, the deterministic priority-edit
reader, and the revision-snapshot helpers.

Every function derives its result from its arguments -- no session write, no
yield, no I/O -- and nothing here imports ``spec4.agentifier.agentifier``, so
this module is a leaf. Names are re-exported from ``agentifier`` under the
same spelling; ``tests/test_renderer_goldens.py`` pins two of them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from spec4.agentifier.composer import Composition
from spec4.agentifier.cross_cutting_analyst import SKIPPABLE_TOPICS
from spec4.agentifier.grounding import build_grounding
from spec4.agentifier.prioritizer import PRIORITIES
from spec4.agents._feature_context import slug

__all__ = [
    "PriorityEdits",
    "_CATALOG_SPEC_PROMPT",
    "_FEATURES_COMPLETE_TRANSITION",
    "_PRIORITY_EDIT_RE",
    "_VALID_PRIORITIES",
    "build_ai_features",
    "_format_ai_features_complete",
    "format_catalog_as_text",
    "_format_composition_summary",
    "_format_cross_cutting_topic",
    "_format_priority_repairs",
    "format_priority_table",
    "format_spec_as_text",
    "parse_priority_edits",
    "merge_revision_snapshot",
    "removed_feature_heads_up",
    "revision_delta",
]


def _format_composition_summary(compositions: list[Composition]) -> str:
    """Render a short composition summary — coordinators and their members.

    Nothing is merged; members are kept beneath their coordinator. A synthesized
    head (Scout did not emit one) is tagged so the reader can tell it apart.
    """
    n_groups = len(compositions)
    n_members = sum(len(c.members) for c in compositions)
    header = (
        f"### Composer — {n_members} sub-feature"
        f"{'' if n_members == 1 else 's'} grouped under {n_groups} "
        f"coordinator{'' if n_groups == 1 else 's'}\n"
    )
    lines = [header]
    for comp in compositions:
        members_str = ", ".join(f"`{m}`" for m in comp.members)
        tag = " *(synthesized)*" if comp.synthesized else ""
        lines.append(f"- **`{comp.coordinator}`**{tag} coordinates {members_str}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 1 -- Catalog display
# ---------------------------------------------------------------------------

_CATALOG_SPEC_PROMPT = (
    "---\n\n"
    "Tier decisions locked. Reply **yes** to begin drafting per-feature specs, "
    "or ask to revise any catalog entry first."
)


def format_catalog_as_text(catalog: dict[str, Any]) -> str:
    """Render ai_catalog to a readable Markdown display with spec-phase prompt."""
    entries: list[dict[str, Any]] = catalog.get("ai_catalog") or []
    lines: list[str] = ["**AI Integration Catalog**\n"]
    lines.append("| # | Feature | Recommended | Decided | Notes |")
    lines.append("| --- | --- | --- | --- | --- |")
    for i, entry in enumerate(entries, 1):
        name = entry.get("name", "")
        rec = entry.get("tier_recommendation", "")
        dec = entry.get("tier_decision", "")
        rationale = entry.get("tier_decision_rationale", "") or ""
        note = rationale[:60] + "…" if len(rationale) > 60 else rationale
        match_marker = "" if dec == rec else " (mismatch)"
        lines.append(f"| {i} | {name} | {rec} | {dec}{match_marker} | {note} |")
    lines.append("")
    lines.append(_CATALOG_SPEC_PROMPT)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 2 -- Spec display and ai_features assembly
# ---------------------------------------------------------------------------


def format_spec_as_text(
    entry: dict[str, Any],
    spec: dict[str, Any],
    index: int,
    total: int,
) -> str:
    """Render one feature spec as readable Markdown."""
    name = entry.get("name", "")
    tier = entry.get("tier_decision") or entry.get("tier", "")
    lines: list[str] = [
        f"### Feature {index + 1}/{total}: `{name}` — tier: **{tier}**\n"
    ]

    _spec_field(spec, lines, "Purpose", "purpose")
    _spec_field(spec, lines, "Invocation", "invocation")
    _spec_field(spec, lines, "Inputs", "inputs")
    _spec_field(spec, lines, "Outputs", "outputs")
    _spec_field(spec, lines, "Decision authority", "decision_authority")
    _spec_field(spec, lines, "Success criteria", "success_criteria")
    _spec_field(spec, lines, "Failure modes", "failure_modes")
    _spec_field(spec, lines, "Escalation", "escalation")
    _spec_field(spec, lines, "Eval approach", "eval_approach")
    _spec_field(spec, lines, "Budgets", "budgets")
    _spec_field(spec, lines, "Privacy / safety", "privacy_safety")
    # Phase priority is deliberately absent: it is assigned by the Prioritizer
    # (D-PP2), which runs after spec review. Showing it here would display a
    # value nobody has set yet.
    # Tier-specific
    _spec_field(spec, lines, "Knowledge sources", "knowledge_sources")
    _spec_field(spec, lines, "Tool access", "tool_access")
    _spec_field(spec, lines, "Topology", "topology")
    _render_spec_mechanisms(spec, lines)
    _render_spec_references(spec, lines)
    return "\n".join(lines)


def _spec_field(  # noqa: C901, PLR0912  # four-way dispatch on JSON value shape; each branch is that shape's rendering
    spec: dict[str, Any], lines: list[str], label: str, key: str
) -> None:
    """Render one spec field under ``label``, per the shape of its value."""
    val = spec.get(key)
    if val is None:
        return
    if isinstance(val, list):
        if not val:
            return
        lines.append(f"**{label}:**")
        for item in val:
            if isinstance(item, dict):
                lines.append("- " + ", ".join(f"{k}: {v}" for k, v in item.items()))
            else:
                lines.append(f"- {item}")
        lines.append("")
    elif isinstance(val, dict):
        if not val:
            return
        lines.append(f"**{label}:**")
        for k, v in val.items():
            if isinstance(v, list):
                if v:
                    lines.append(f"- {k}: " + "; ".join(str(i) for i in v))
            elif v:
                lines.append(f"- {k}: {v}")
        lines.append("")
    else:
        lines.append(f"**{label}:** {val}\n")


def _render_spec_mechanisms(spec: dict[str, Any], lines: list[str]) -> None:
    """The ``mechanisms`` block."""
    mechanisms = spec.get("mechanisms") or []
    if mechanisms:
        lines.append("**Mechanisms:**")
        for m in mechanisms:
            if isinstance(m, dict):
                mname = m.get("name", "")
                mrationale = m.get("rationale", "")
                lines.append(f"- **{mname}**: {mrationale}")
            else:
                lines.append(f"- {m}")
        lines.append("")


def _render_spec_references(spec: dict[str, Any], lines: list[str]) -> None:
    """The ``references`` block."""
    references = spec.get("references") or []
    if references:
        lines.append("**References:**")
        for r in references:
            lines.append(f"- {r}")
        lines.append("")


def build_ai_features(
    catalog_entries: list[dict[str, Any]],
    spec_results: list[dict[str, Any]],
    candidates_data: list[dict[str, Any]],
    analyses_data: list[dict[str, Any]] | None = None,
    feature_specs: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Merge catalog entries + spec results into ai_features schema.

    When ``feature_specs`` is supplied, each node also carries a
    ``vision_grounding`` block (D-AC1 B): the Brainstormer product-feature specs
    it serves, resolved from the candidate's ``linked_vision_features`` by the
    canonical ``slug()`` join. Absent/empty grounding leaves the key off.
    """
    candidates_by_name = {c["name"]: c for c in candidates_data}
    analysis_by_name = {a["name"]: a for a in (analyses_data or []) if a.get("name")}
    features: list[dict[str, Any]] = []
    for i, entry in enumerate(catalog_entries):
        name = entry.get("name", "")
        spec = spec_results[i] if i < len(spec_results) else {}
        cand = candidates_by_name.get(name, {})
        feature: dict[str, Any] = {
            "id": slug(name) if name else f"feature_{i}",
            "name": name,
            "linked_vision_features": cand.get("linked_vision_features", []),
            "scope": entry.get("scope", "feature"),
            "tier": entry.get("tier_decision", "single_call"),
            "tier_recommendation": entry.get("tier_recommendation", ""),
            "tier_decision_rationale": entry.get("tier_decision_rationale", ""),
            "rough_description": entry.get("rough_description", ""),
        }
        feature.update(spec)  # merge spec drafter output
        # Candidate is the authoritative source for rough_description: it carries
        # Composer-enriched text that the catalog agent may have reverted.
        # Falls back to the entry value, then to whatever spec supplied.
        feature["rough_description"] = (
            cand.get("rough_description")
            or entry.get("rough_description", "")
            or feature.get("rough_description", "")
        )
        # Scout graph contract (D-EP): the candidate is authoritative for the
        # edges too — re-assert them after the spec merge so a spec drafter that
        # echoes these keys cannot clobber the Composer-set values. Persisted raw
        # (D-EP2 option A): referential trimming of dangling edges is deferred.
        feature["composed_under"] = cand.get("composed_under", "")
        feature["requires"] = list(cand.get("requires") or [])
        # Brownfield linkage (candidate-authoritative, like the edges): without
        # this, reselection_pool_from_features' read of the key is always ""
        # and re-selection rounds silently lose the replaced-workflow context.
        feature["linked_existing_workflow"] = cand.get("linked_existing_workflow", "")
        # Node classification (D-I5): selectable features are explicitly
        # "feature"; tier-derived substrate is stamped "infrastructure" by the
        # expansion pass. Makes the distinction explicit rather than by absence.
        feature["kind"] = cand.get("kind", "feature")
        # Vision grounding (D-AC1 B): the product-feature specs this AI feature
        # serves, joined from the candidate's linked_vision_features. Attached
        # after the spec merge so a Spec Drafter that echoes the key cannot
        # clobber it. Gated on feature_specs actually being present so the
        # safety-net path (no specs) attaches nothing rather than tagging every
        # node with noise-only unresolved links; when specs exist, an all-missed
        # node keeps its unresolved_links as a genuine mis-link signal.
        if (feature_specs or {}).get("features"):
            grounding = build_grounding(
                feature_specs, cand.get("linked_vision_features") or []
            )
            if grounding:
                feature["vision_grounding"] = grounding
        a = analysis_by_name.get(name, {})
        feature["tier_analysis"] = (
            {
                "recommended_tier": a.get("recommended_tier", ""),
                "rationale": a.get("rationale", ""),
                "compared_to_next_tier_down": a.get("compared_to_next_tier_down", ""),
                "borderline": a.get("borderline", False),
                "borderline_seams": a.get("borderline_seams", []),
                "risks_of_going_higher": a.get("risks_of_going_higher", []),
                "risks_of_going_lower": a.get("risks_of_going_lower", []),
            }
            if a
            else {}
        )
        features.append(feature)
    return features


# ---------------------------------------------------------------------------
# Revision mode — pure helpers (deterministic; no LLM)
# ---------------------------------------------------------------------------


def revision_delta(vision: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return this round's revision delta, or ``None`` for a greenfield vision.

    A revision round's vision carries an accumulating ``revision_history`` (each
    round contributes one entry, stamped deterministically by Brainstormer); its
    final entry is the delta for the current round — ``goal``, the
    ``key_features_mvp`` name changes (``added`` / ``modified`` / ``removed``),
    and ``rationale``. A greenfield vision has no ``revision_history``.
    """
    vs = (vision or {}).get("vision_statement") if isinstance(vision, dict) else None
    history = vs.get("revision_history") if isinstance(vs, dict) else None
    if isinstance(history, list) and history:
        last = history[-1]
        return last if isinstance(last, dict) else None
    return None


def merge_revision_snapshot(
    carried_forward: list[dict[str, Any]],
    new_features: list[dict[str, Any]],
    current_version: int,
    prior_version: int,
) -> list[dict[str, Any]]:
    """Assemble a revision round's complete feature snapshot with provenance.

    Returns the carried-forward implemented features (kept verbatim aside from a
    backfilled ``introduced_in_version``) followed by this round's newly selected
    features. Code owns ``introduced_in_version`` — the model never authors it:

    - new features → ``current_version`` (this planning round).
    - carried-forward → their existing ``introduced_in_version``; backfilled to
      ``prior_version`` when a feature predates the marker (e.g. greenfield
      features built before this field existed).

    Carried-forward names win on collision: if Scout re-surfaces an already-built
    feature as a "new" candidate despite the delta-informed scoping, the built
    entry is kept and the duplicate dropped — never double-listed or downgraded.
    """
    carried_names = {f.get("name") for f in carried_forward if f.get("name")}
    out: list[dict[str, Any]] = []
    for f in carried_forward:
        g = dict(f)
        if g.get("introduced_in_version") is None:
            g["introduced_in_version"] = prior_version
        out.append(g)
    for f in new_features:
        if f.get("name") in carried_names:
            continue
        g = dict(f)
        g["introduced_in_version"] = current_version
        out.append(g)
    return out


def removed_feature_heads_up(
    carried_forward: list[dict[str, Any]],
    delta: dict[str, Any] | None,
) -> str:
    """Informational note (no action) when a built feature is linked to a feature
    this revision removed.

    Carried-forward features are NEVER auto-dropped — the code is already built,
    and deprecation/removal is downstream coding work, out of scope for
    Agentifier discovery. This surfaces the situation so the developer stays in
    control. Returns ``""`` when nothing applies.
    """
    removed = set((delta or {}).get("changes", {}).get("removed") or [])
    if not removed:
        return ""
    hits: list[str] = []
    for f in carried_forward:
        linked = set(f.get("linked_vision_features") or [])
        overlap = linked & removed
        if overlap:
            hits.append(
                f"- **{f.get('name', '')}** (built for: {', '.join(sorted(overlap))})"
            )
    if not hits:
        return ""
    return (
        "\n\n> **Heads-up:** these already-built AI features are linked to "
        "product features you removed this revision. They are carried forward "
        "unchanged — removing the underlying code is a separate, manual step:\n"
        + "\n".join(hits)
        + "\n"
    )


_FEATURES_COMPLETE_TRANSITION = (
    "---\n\n"
    "Your AI feature catalog is complete. "
    "Click **Download ai_features.json** below, "
    "or use the pipeline pills to continue."
)


def _format_ai_features_complete(ai_features: dict[str, Any]) -> str:
    """Render a summary display for completed ai_features."""
    entries = ai_features.get("ai_features") or []
    lines = ["**AI Feature Catalog — Complete**\n"]
    lines.append("| # | Feature | Tier | Phase Priority |")
    lines.append("| --- | --- | --- | --- |")
    for i, f in enumerate(entries, 1):
        name = f.get("name", "")
        tier = f.get("tier", "")
        priority = f.get("phase_priority", "—")
        lines.append(f"| {i} | {name} | {tier} | {priority} |")
    lines.append("")
    lines.append(_FEATURES_COMPLETE_TRANSITION)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cross-cutting display
# ---------------------------------------------------------------------------


def _format_cross_cutting_topic(
    topic: str,
    index: int,
    analysis: dict[str, Any],
    total: int,
    include_prompt: bool = True,
) -> str:
    """Render one cross-cutting topic recommendation for review."""
    data = analysis.get(topic) or {}
    rec = data.get("recommendation", "")
    rationale = data.get("rationale", "")
    patterns = data.get("cited_patterns") or []

    lines = [
        f"### Cross-cutting decision {index + 1}/{total}: **{topic}**\n",
        f"**Recommendation:** {rec}\n",
        f"**Rationale:** {rationale}\n",
    ]
    if patterns:
        lines.append(f"**Patterns cited:** {', '.join(patterns)}\n")
    if not include_prompt:
        return "\n".join(lines)
    if topic in SKIPPABLE_TOPICS:
        lines.append(
            "---\nReply **yes** to accept, **skip** if this isn't needed, "
            "or describe what to change."
        )
    else:
        lines.append(
            "---\nReply **yes** to accept this recommendation, "
            "or describe what to change."
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase priority helpers
# ---------------------------------------------------------------------------

_VALID_PRIORITIES = PRIORITIES

#: `name: priority` — also accepts `=`, `->` and `→`, with an optional bullet.
_PRIORITY_EDIT_RE = re.compile(
    r"^\s*(?:[-*•]\s*)?(?:\*\*)?([A-Za-z0-9_][A-Za-z0-9_.\-]*)(?:\*\*)?"
    r"\s*(?::|=|->|→)\s*(?:\*\*|`)?([A-Za-z0-9_ \-]+?)(?:\*\*|`)?\s*$"
)


@dataclass
class PriorityEdits:
    """The result of reading one free-text reply at the priority checkpoint."""

    assignments: dict[str, str] = field(default_factory=dict)
    unknown_names: list[str] = field(default_factory=list)
    bad_values: list[tuple[str, str]] = field(default_factory=list)

    @property
    def saw_pair(self) -> bool:
        """True when the reply contained anything shaped like an assignment.

        Distinguishes "the user tried to edit and got it wrong" from "the user
        said something else entirely". Only the latter may be read as a
        confirmation.
        """
        return bool(self.assignments or self.unknown_names or self.bad_values)


def parse_priority_edits(text: str, valid_names: set[str]) -> PriorityEdits:
    """Read ``name: priority`` assignments out of a free-text reply.

    Deterministic — no LLM turn. Values are normalised for whitespace and
    hyphens, so ``steel thread`` and ``steel-thread`` both reach
    ``steel_thread``: the display writes the underscore form, but people type
    what they read.
    """
    edits = PriorityEdits()
    for segment in re.split(r"[\n;]+", text):
        if not segment.strip():
            continue
        match = _PRIORITY_EDIT_RE.match(segment)
        if not match:
            continue
        name, raw_value = match.group(1), match.group(2)
        value = re.sub(r"[\s\-]+", "_", raw_value.strip().lower())
        if value not in _VALID_PRIORITIES:
            edits.bad_values.append((name, raw_value.strip()))
        elif name not in valid_names:
            edits.unknown_names.append(name)
        else:
            edits.assignments[name] = value
    return edits


def format_priority_table(features: list[dict[str, Any]]) -> str:
    """Render the whole feature set as one priority table.

    Priority is a property of the *set* — which features form the thinnest
    end-to-end path, what ships first, what waits — so the checkpoint shows the
    set. A per-feature walk hid the distribution until it was too late to see it.
    """
    rank = {p: i for i, p in enumerate(_VALID_PRIORITIES)}
    ordered = sorted(
        enumerate(features),
        key=lambda t: (rank.get(t[1].get("phase_priority") or "mvp", 1), t[0]),
    )
    grouped = any(f.get("composed_under") for f in features)

    header = "| Priority | Feature | Tier | Requires |"
    divider = "|---|---|---|---|"
    if grouped:
        header = "| Priority | Feature | Tier | Part of | Requires |"
        divider = "|---|---|---|---|---|"

    lines = ["### Phase priority\n", header, divider]
    for _, f in ordered:
        priority = f.get("phase_priority") or "mvp"
        requires = ", ".join(f.get("requires") or []) or "—"
        row = [f"`{priority}`", f"**{f.get('name', '')}**", f.get("tier", ""), requires]
        if grouped:
            row.insert(3, f.get("composed_under") or "—")
        lines.append("| " + " | ".join(row) + " |")

    thread = [
        f.get("name", "") for f in features if f.get("phase_priority") == "steel_thread"
    ]
    lines.append("")
    if thread:
        lines.append(
            "**Steel thread** — built first, end to end: "
            + ", ".join(f"`{n}`" for n in thread)
        )
    else:
        lines.append("**Steel thread** — nothing assigned yet.")

    deferred = [
        f.get("name", "")
        for f in features
        if f.get("phase_priority") in ("v2", "future")
    ]
    if deferred:
        lines.append(f"**Deferred past the first release:** {len(deferred)}.")

    # Name a feature that is not already in the thread, so the example does not
    # read as a no-op. Falls back safely on an empty or all-steel_thread set.
    example = next(
        (
            f.get("name", "")
            for f in features
            if f.get("phase_priority") != "steel_thread"
        ),
        features[0].get("name", "feature_name") if features else "feature_name",
    )
    lines.append(
        "\n---\nReply **yes** to accept, or reassign any number of features, one per line:\n\n"
        "```\n"
        f"{example}: steel_thread\n"
        "another_feature: v2\n"
        "```\n\n"
        "Values: `steel_thread` / `mvp` / `v2` / `future`. "
        "I'll re-check the build order after each change."
    )
    return "\n".join(lines)


def _format_priority_repairs(
    before: dict[str, str],
    after: dict[str, str],
    requested: dict[str, str],
) -> list[str]:
    """Describe every priority the normalization pass moved on its own.

    A feature the developer set explicitly is only reported when normalization
    overrode them — otherwise the echo is noise.
    """
    notes: list[str] = []
    for name, new_value in after.items():
        old_value = before.get(name)
        if old_value == new_value:
            continue
        if name in requested and requested[name] == new_value:
            continue  # exactly what was asked for
        reason = (
            "overriding your change, to keep the build order valid"
            if name in requested
            else "to keep the build order valid"
        )
        notes.append(f"- `{name}`: {old_value} → **{new_value}** ({reason})")
    return notes
