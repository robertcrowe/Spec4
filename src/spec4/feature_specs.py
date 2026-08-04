"""Shared, agent-agnostic rendering of Agentifier's per-feature specs.

Agentifier's Spec Drafter produces a rich implementation spec per AI feature
(purpose, invocation, inputs, outputs, success criteria, failure modes, …) and
``_build_ai_features`` merges the whole spec onto each catalog node. Several
consumers need to render that spec faithfully:

* ``agents/_utils.py`` — the per-agent context serializers (Phaser today;
  StackAdvisor and Designer on their own levers).
* ``project_manager.render_phase_markdown`` — the phase-file spec preamble the
  coding agent actually reads.

This module is the single renderer for all of them. It is a **leaf**: it imports
nothing from ``spec4.agents`` or ``spec4.project_manager``, because
``agents/_utils.py`` already imports ``project_manager`` and the reverse edge
would close an import cycle. Keep it that way.

Rendering is deterministic and lossless — fields are emitted verbatim, never
paraphrased (see the "deterministic lossless assembly over LLM re-work"
principle). Callers select *which* fields to render; they never rewrite them.

Infrastructure nodes (``kind: infrastructure``) are injected by
``infra_expander`` *after* the Spec Drafter runs, so they carry no spec body at
all — only ``rough_description``. They render as a labelled substrate entry
rather than an empty spec.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from spec4.agentifier.infra_expander import INFRA_KIND
from spec4.agentifier.pattern_loader import load_patterns

__all__ = [
    "ALL_SPEC_FIELDS",
    "DESIGNER_SPEC_FIELDS",
    "PHASE_EXCLUDED_CROSS_CUTTING",
    "PHASE_EXCLUDED_SPEC_FIELDS",
    "PHASE_SPEC_FIELDS",
    "PHASER_PRODUCT_SPEC_FIELDS",
    "STACK_SPEC_FIELDS",
    "render_feature_block",
    "render_cross_cutting",
    "spec_index",
]


# Canonical render order. A superset of every Spec Drafter field, including the
# tier-conditional blocks (knowledge_sources / tool_access / topology) that only
# appear on higher-tier features. Absent keys are skipped silently.
ALL_SPEC_FIELDS: tuple[str, ...] = (
    "purpose",
    "invocation",
    "inputs",
    "outputs",
    "decision_authority",
    "knowledge_sources",
    "tool_access",
    "topology",
    "mechanisms",
    "success_criteria",
    "failure_modes",
    "escalation",
    "eval_approach",
    "budgets",
    "privacy_safety",
    "references",
)

# D-PS13: fields the Spec Drafter writes for the *developer*, not the coding
# agent, and which must not appear in a phase file's binding preamble.
#
# The Spec Drafter runs before StackAdvisor and cannot know the chosen stack —
# an ordering forced by the dependency (the stack is picked from the tier
# distribution). So `budgets` and `eval_approach` routinely name vendors and
# per-call prices from a provider that was never selected. Observed on a live
# draw: a spec priced OpenAI's `text-embedding-3-small` and proposed comparing it
# against Cohere, while the ratified stack ran `sentence-transformers` locally at
# zero per-call cost. Rendered under "These specifications are authoritative",
# that hands the coder a second, contradictory source of stack truth — the exact
# harm `PHASE_EXCLUDED_CROSS_CUTTING` guards against, arriving through a
# different field.
#
# Both remain in Phaser's own context (it sequences with cost and eval in mind);
# only the coder-facing render drops them.
PHASE_EXCLUDED_SPEC_FIELDS: tuple[str, ...] = ("budgets", "eval_approach")

# The field selection for phase-file preambles.
PHASE_SPEC_FIELDS: tuple[str, ...] = tuple(
    f for f in ALL_SPEC_FIELDS if f not in PHASE_EXCLUDED_SPEC_FIELDS
)

# DR1: the field selection for Designer's per-feature block. Designer needs the
# behavioural substance that shapes a surface — what the feature does, when it
# fires, what the user provides, what it returns, and what "good"/"failed" look
# like (the latter drives success and empty/error states) — and nothing else.
# The catalog-only fields (mechanisms / topology / tool_access / budgets / …) are
# absent from vision-level feature specs anyway; naming the subset keeps the
# block focused rather than relying on absence.
DESIGNER_SPEC_FIELDS: tuple[str, ...] = (
    "purpose",
    "invocation",
    "inputs",
    "outputs",
    "success_criteria",
    "failure_modes",
)

# D-SC1: the field selection for StackAdvisor's per-feature spine block. Stack
# choices are driven by what a feature consumes and produces and by what
# "good"/"failed" mean for it — inputs/outputs signal integration and storage
# needs, invocation signals the trigger (a scheduled feature wants a scheduler),
# and success/failure phrase reliability guarantees the stack must make possible.
# The list coincides with DESIGNER_SPEC_FIELDS today because vision-level feature
# specs carry only these behavioural fields; naming a distinct subset keeps the
# stack rationale explicit and lets the two diverge later. ``dependencies`` and
# ``entities`` are rendered by the projection directly (they have no field
# renderer), not through this subset.
STACK_SPEC_FIELDS: tuple[str, ...] = (
    "purpose",
    "invocation",
    "inputs",
    "outputs",
    "success_criteria",
    "failure_modes",
)

# D-PH1: the field selection for Phaser's product-feature spine block. Phaser
# turns behaviour into phase content, so it needs the full behavioural surface:
# purpose/invocation anchor the feature preamble and sequencing, inputs/outputs
# anchor concrete instructions, and success_criteria / failure_modes are the raw
# material for phase verification and risk sections. The list coincides with
# STACK_SPEC_FIELDS today because vision-level feature specs carry only these
# behavioural fields; naming a distinct subset keeps each consumer's rationale
# explicit and lets them diverge later (same reasoning as D-SC1 above).
# ``dependencies`` and ``entities`` are rendered by the projection directly.
PHASER_PRODUCT_SPEC_FIELDS: tuple[str, ...] = (
    "purpose",
    "invocation",
    "inputs",
    "outputs",
    "success_criteria",
    "failure_modes",
)

# D-PS6(A'): `provider_strategy` is deliberately provider-agnostic (the analyst
# is told vendor selection belongs to the downstream stack phase). Phase files
# already carry StackAdvisor's *ratified* `tech_stack_spec`, so rendering both
# hands the coding agent two sources of stack truth with nothing marking which
# supersedes which. Excluded from phase files only — Phaser still sees it.
PHASE_EXCLUDED_CROSS_CUTTING: tuple[str, ...] = ("provider_strategy",)


def _clean(value: Any) -> str:
    """Collapse a scalar to a trimmed string; empty for None/blank."""
    if value is None or isinstance(value, (dict, list)):
        return ""
    text = str(value).strip()
    return "" if text.lower() in ("", "none", "null") else text


def _bullets(items: Any) -> list[str]:
    """Render a list of scalars as markdown bullets."""
    if not isinstance(items, list):
        return []
    return [f"- {_clean(i)}" for i in items if _clean(i)]


def _render_purpose(value: Any) -> list[str]:
    text = _clean(value)
    return [text, ""] if text else []


def _render_invocation(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    trigger = _clean(value.get("trigger"))
    mode = _clean(value.get("mode"))
    if not trigger and not mode:
        return []
    lines = ["**Invocation**", ""]
    if trigger:
        lines.append(f"- Trigger: {trigger}")
    if mode:
        lines.append(f"- Mode: {mode}")
    lines.append("")
    return lines


def _render_inputs(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        return []
    lines = ["**Inputs**", ""]
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name")) or "(unnamed)"
        type_ = _clean(item.get("type"))
        desc = _clean(item.get("description"))
        required = item.get("required")
        flag = "required" if required else "optional"
        head = f"- `{name}`"
        if type_:
            head += f" ({type_}, {flag})"
        else:
            head += f" ({flag})"
        if desc:
            head += f" — {desc}"
        lines.append(head)
    lines.append("")
    return lines if len(lines) > 2 else []


def _render_outputs(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    primary = _clean(value.get("primary"))
    fmt = _clean(value.get("format"))
    notes = _clean(value.get("schema_notes"))
    if not (primary or fmt or notes):
        return []
    lines = ["**Outputs**", ""]
    if primary:
        lines.append(f"- Primary: {primary}")
    if fmt:
        lines.append(f"- Format: {fmt}")
    if notes:
        lines.append(f"- Schema notes: {notes}")
    lines.append("")
    return lines


def _render_decision_authority(value: Any) -> list[str]:
    text = _clean(value)
    return [f"**Decision authority:** {text}", ""] if text else []


def _render_escalation(value: Any) -> list[str]:
    text = _clean(value)
    return [f"**Escalation on failure:** {text}", ""] if text else []


def _render_success_criteria(value: Any) -> list[str]:
    body = _bullets(value)
    return ["**Success criteria**", "", *body, ""] if body else []


def _render_privacy_safety(value: Any) -> list[str]:
    body = _bullets(value)
    return ["**Privacy & safety**", "", *body, ""] if body else []


def _render_references(value: Any) -> list[str]:
    body = _bullets(value)
    return ["**References**", "", *body, ""] if body else []


def _render_failure_modes(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        return []
    lines = ["**Failure modes**", ""]
    for item in value:
        if not isinstance(item, dict):
            continue
        mode = _clean(item.get("mode"))
        if not mode:
            continue
        likelihood = _clean(item.get("likelihood"))
        mitigation = _clean(item.get("mitigation"))
        head = f"- {mode}"
        if likelihood:
            head += f" (likelihood: {likelihood})"
        if mitigation:
            head += f" — mitigation: {mitigation}"
        lines.append(head)
    lines.append("")
    return lines if len(lines) > 2 else []


def _render_eval_approach(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    pairs = [
        ("Offline", _clean(value.get("offline"))),
        ("Online", _clean(value.get("online"))),
        ("Ground truth", _clean(value.get("ground_truth"))),
    ]
    body = [f"- {label}: {text}" for label, text in pairs if text]
    return ["**Eval approach**", "", *body, ""] if body else []


def _render_budgets(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    pairs = [
        ("Cost per call", _clean(value.get("cost_per_call"))),
        ("p95 latency", _clean(value.get("p95_latency"))),
    ]
    body = [f"- {label}: {text}" for label, text in pairs if text]
    return ["**Budgets**", "", *body, ""] if body else []


@lru_cache(maxsize=1)
def _mechanism_definitions() -> dict[str, str]:
    """Canonical one-line definition per mechanism, from the pattern library.

    The rendered spec is the only channel through which a mechanism decision
    reaches Phaser and the coding agent — neither ever sees the pattern
    library, so the name alone would rely on the reader's own idea of what
    "reflection" means (and the library exists precisely because those ideas
    drift). Loaded lazily and cached; a library that fails to load degrades
    to no definitions rather than an unrenderable phase file.
    """
    try:
        _, mechanisms = load_patterns()
    except Exception:
        return {}
    definitions: dict[str, str] = {}
    for m in mechanisms:
        summary = " ".join(m.description.split())
        if len(summary) > 200:
            summary = summary[:200].rstrip() + "…"
        definitions[m.name] = summary
    return definitions


def _render_mechanisms(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        return []
    lines = ["**Mechanisms**", ""]
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        if not name:
            continue
        rationale = _clean(item.get("rationale"))
        head = f"- `{name}`"
        if rationale:
            head += f" — {rationale}"
        lines.append(head)
        # Glossary line: the library's canonical definition, so the instance
        # rationale/configuration are read against what the mechanism IS.
        definition = _mechanism_definitions().get(name)
        if definition:
            lines.append(f"  - definition: {definition}")
        config = item.get("configuration")
        if isinstance(config, dict) and config:
            for key, val in config.items():
                detail = _clean(val)
                if detail:
                    lines.append(f"  - {key}: {detail}")
    lines.append("")
    return lines if len(lines) > 2 else []


def _render_knowledge_sources(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        return []
    lines = ["**Knowledge sources**", ""]
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        if not name:
            continue
        type_ = _clean(item.get("type"))
        content = _clean(item.get("content_description"))
        freq = _clean(item.get("update_frequency"))
        head = f"- `{name}`"
        if type_:
            head += f" ({type_})"
        if content:
            head += f" — {content}"
        if freq:
            head += f" [updates: {freq}]"
        lines.append(head)
    lines.append("")
    return lines if len(lines) > 2 else []


def _render_tool_access(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    caps = value.get("capabilities_needed")
    if not isinstance(caps, list) or not caps:
        return []
    lines = ["**Tool access**", ""]
    for item in caps:
        if not isinstance(item, dict):
            continue
        purpose = _clean(item.get("purpose"))
        if not purpose:
            continue
        source = _clean(item.get("source"))
        protocol = _clean(item.get("protocol"))
        server = _clean(item.get("mcp_server"))
        rationale = _clean(item.get("rationale"))
        head = f"- {purpose}"
        bits = [b for b in (source, protocol) if b]
        if bits:
            head += f" ({', '.join(bits)})"
        lines.append(head)
        if server:
            lines.append(f"  - MCP server: {server}")
        if rationale:
            lines.append(f"  - Rationale: {rationale}")
    lines.append("")
    return lines if len(lines) > 2 else []


def _render_topology(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    lines: list[str] = []
    role = _clean(value.get("coordinator_role"))
    pattern = _clean(value.get("communication_pattern"))
    synthesis = _clean(value.get("synthesis_approach"))
    subagents = value.get("subagents")
    if role:
        lines.append(f"- Coordinator role: {role}")
    if pattern:
        lines.append(f"- Communication pattern: {pattern}")
    if synthesis:
        lines.append(f"- Synthesis: {synthesis}")
    if isinstance(subagents, list):
        for item in subagents:
            if not isinstance(item, dict):
                continue
            name = _clean(item.get("name"))
            if not name:
                continue
            role_ = _clean(item.get("role"))
            in_ = _clean(item.get("input"))
            out = _clean(item.get("output"))
            head = f"- Sub-agent `{name}`"
            if role_:
                head += f" — {role_}"
            lines.append(head)
            if in_:
                lines.append(f"  - Input: {in_}")
            if out:
                lines.append(f"  - Output: {out}")
    return ["**Topology**", "", *lines, ""] if lines else []


_FIELD_RENDERERS = {
    "purpose": _render_purpose,
    "invocation": _render_invocation,
    "inputs": _render_inputs,
    "outputs": _render_outputs,
    "decision_authority": _render_decision_authority,
    "knowledge_sources": _render_knowledge_sources,
    "tool_access": _render_tool_access,
    "topology": _render_topology,
    "mechanisms": _render_mechanisms,
    "success_criteria": _render_success_criteria,
    "failure_modes": _render_failure_modes,
    "escalation": _render_escalation,
    "eval_approach": _render_eval_approach,
    "budgets": _render_budgets,
    "privacy_safety": _render_privacy_safety,
    "references": _render_references,
}


def _render_graph_lines(feature: dict[str, Any]) -> list[str]:
    """Tier / scope / priority / edge context for one node."""
    lines: list[str] = []
    tier = _clean(feature.get("tier"))
    if tier:
        lines.append(f"- Tier: `{tier}`")
    scope = _clean(feature.get("scope"))
    if scope == "cross_feature":
        lines.append(
            "- Scope: `cross_feature` — spans more than one vision feature; "
            "it is shared surface, not the private concern of any single "
            "consumer."
        )
    elif scope:
        lines.append(f"- Scope: `{scope}`")
    priority = _clean(feature.get("phase_priority"))
    if priority:
        lines.append(f"- Phase priority: `{priority}`")
    parent = _clean(feature.get("composed_under"))
    if parent:
        lines.append(f"- Composed under: `{parent}`")
    requires = [_clean(r) for r in (feature.get("requires") or [])]
    requires = [r for r in requires if r]
    if requires:
        lines.append(f"- Requires: {', '.join(f'`{r}`' for r in requires)}")

    analysis = feature.get("tier_analysis")
    if isinstance(analysis, dict):
        rationale = _clean(analysis.get("rationale"))
        if rationale:
            lines.append(f"- Tier rationale: {rationale}")
        cheaper = _clean(analysis.get("compared_to_next_tier_down"))
        if cheaper:
            lines.append(f"- Next-cheaper tier would lose: {cheaper}")
        if analysis.get("borderline"):
            seams = [_clean(s) for s in (analysis.get("borderline_seams") or [])]
            seams = [s for s in seams if s]
            if seams:
                lines.append(f"- Borderline — seams to watch: {'; '.join(seams)}")
            else:
                lines.append("- Borderline tier call.")
    decision = _clean(feature.get("tier_decision_rationale"))
    if decision:
        lines.append(f"- Tier decision (developer): {decision}")
    return lines


def _render_infra_block(feature: dict[str, Any]) -> list[str]:
    """Infrastructure nodes carry no spec body — label them as substrate.

    ``infra_expander`` injects these after the Spec Drafter has run, so an empty
    spec here is expected, not a defect. Rendering ``rough_description`` under an
    explicit label is deliberate (D-PS5(A)): the coding agent must actually stand
    this substrate up, and hiding it would be worse than a thin entry.
    """
    lines = [
        "*Enabling infrastructure — shared substrate that other features in this "
        "build require. It is not a user-selected capability and has no drafted "
        "spec; stand it up before anything that requires it.*",
        "",
    ]
    desc = _clean(feature.get("rough_description"))
    if desc:
        lines.extend([desc, ""])
    graph = _render_graph_lines(feature)
    if graph:
        lines.extend([*graph, ""])
    return lines


def render_feature_block(
    feature: dict[str, Any],
    *,
    fields: tuple[str, ...] = ALL_SPEC_FIELDS,
    include_graph: bool = True,
) -> list[str]:
    """Render one catalog node's spec as markdown lines (no heading).

    ``fields`` selects which Spec Drafter fields to emit, in canonical order —
    consumers with narrower needs (Designer) pass a subset; Phaser passes the
    default superset. Absent fields are skipped. Nothing is paraphrased.
    """
    if feature.get("kind") == INFRA_KIND:
        return _render_infra_block(feature)

    lines: list[str] = []
    if include_graph:
        graph = _render_graph_lines(feature)
        if graph:
            lines.extend([*graph, ""])
    for name in fields:
        renderer = _FIELD_RENDERERS.get(name)
        if renderer is None:
            continue
        if name not in feature:
            continue
        lines.extend(renderer(feature[name]))
    if not lines:
        desc = _clean(feature.get("rough_description"))
        if desc:
            lines.extend([desc, ""])
    return lines


def render_cross_cutting(
    cross: dict[str, Any] | None,
    *,
    exclude: tuple[str, ...] = (),
) -> list[str]:
    """Render the cross-cutting analyst's decisions as markdown lines.

    ``exclude`` drops named decisions; phase files pass
    ``PHASE_EXCLUDED_CROSS_CUTTING`` so ``provider_strategy`` never sits beside
    StackAdvisor's ratified stack (D-PS6(A')).
    """
    if not isinstance(cross, dict) or not cross:
        return []
    lines: list[str] = []
    for key in sorted(cross):
        if key in exclude:
            continue
        entry = cross[key]
        if not isinstance(entry, dict):
            continue
        rec = _clean(entry.get("recommendation"))
        if not rec:
            continue
        label = key.replace("_", " ").capitalize()
        lines.append(f"- **{label}:** {rec}")
        rationale = _clean(entry.get("rationale"))
        if rationale:
            lines.append(f"  - Rationale: {rationale}")
    if not lines:
        return []
    return ["**Cross-cutting decisions (project-wide):**", "", *lines, ""]


def spec_index(ai_features: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Index catalog nodes by ``id`` — the stable join key.

    ``id`` is the slug ``_build_ai_features`` derives and the key the phase
    ``features[]`` declaration uses. Nodes lacking an id are skipped.
    """
    nodes = (ai_features or {}).get("ai_features") or []
    return {
        node["id"]: node
        for node in nodes
        if isinstance(node, dict) and _clean(node.get("id"))
    }
