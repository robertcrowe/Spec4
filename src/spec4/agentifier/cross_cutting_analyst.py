"""Cross-Cutting Analyst sub-agent.

Reasons across the full ai_features list and produces system-level recommendations
for the cross-cutting concerns the feature set actually raises (provider strategy,
tool-protocol strategy, prompt versioning). StreamingSubAgent — yields JSON chunks;
the orchestrator buffers, extracts the JSON block, and presents each topic
conversationally.

Supports both full-analysis (the warranted topic subset) and single-topic revision.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from spec4.agentifier.pattern_loader import MechanismPattern
from spec4.agentifier.spec_drafter import _TIER_ORDER
from spec4.agentifier.subagents import validate_dataclass_input
from spec4.llm import acomplete

CROSS_CUTTING_TOPICS = (
    "provider_strategy",
    "tool_protocol_strategy",
    "prompt_versioning",
)

# Topics offered but not required — the user may skip them in the review walk.
SKIPPABLE_TOPICS = frozenset({"prompt_versioning"})


def _needs_provider(features: list[dict[str, Any]]) -> bool:
    """Any feature above ``deterministic`` calls a model — generative or an
    embedding model — and therefore needs a provider capability decision."""
    return any(_TIER_ORDER.get(f.get("tier"), 3) >= 2 for f in features)


def _has_prompts(features: list[dict[str, Any]]) -> bool:
    """Generative tiers (``single_call`` and up) have a prompt to version;
    ``deterministic`` and ``embeddings`` features do not."""
    return any(_TIER_ORDER.get(f.get("tier"), 3) >= 3 for f in features)


def _has_tool_access(features: list[dict[str, Any]]) -> bool:
    """Any feature declaring tool capabilities raises the tool-protocol decision."""
    return any(
        (f.get("tool_access") or {}).get("capabilities_needed") for f in features
    )


def warranted_topics(features: list[dict[str, Any]]) -> list[str]:
    """The cross-cutting topics this feature set actually raises, in walk order.

    ``provider_strategy`` and ``tool_protocol_strategy`` are required when their
    predicate holds; ``prompt_versioning`` is offered (skippable). A feature set
    that raises none (e.g. all ``deterministic``, no tools) yields ``[]`` and the
    cross-cutting step is skipped entirely.
    """
    topics: list[str] = []
    if _needs_provider(features):
        topics.append("provider_strategy")
    if _has_tool_access(features):
        topics.append("tool_protocol_strategy")
    if _has_prompts(features):
        topics.append("prompt_versioning")
    return topics


# ---------------------------------------------------------------------------
# Input type
# ---------------------------------------------------------------------------


@dataclass
class CrossCuttingInput:
    """Input to CrossCuttingAnalyst.stream()."""

    ai_features: list[dict[str, Any]]
    """Per-feature specs from the spec-drafting phase."""

    mechanism_patterns: list[MechanismPattern]
    """Full mechanism pattern library (from load_patterns)."""

    llm_config: dict[str, Any]
    """LiteLLM config: model, api_key, optional api_base."""

    topic: str | None = field(default=None)
    """None → analyse ``topics`` (or all survivors); set for single-topic revision."""

    topics: list[str] | None = field(default=None)
    """Warranted subset for full analysis; defaults to all survivor topics."""

    revision_instruction: str | None = field(default=None)
    """User's revision request when topic is set."""

    prior_decisions: dict[str, Any] = field(default_factory=dict)
    """Previously accepted decisions, supplied for single-topic revision context."""

    code_review: dict[str, Any] | None = field(default=None)
    """Optional brownfield code review — used to bias toward reuse of existing AI infra."""


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------


def _mechanism_context(mechanisms: list[MechanismPattern]) -> str:
    lines = ["Available mechanism patterns (cite by exact name in cited_patterns):"]
    for m in mechanisms:
        first_sentence = m.description.split("\n")[0].strip()[:180]
        lines.append(f"- **{m.name}**: {first_sentence}")
    return "\n".join(lines)


def _feature_digest(features: list[dict[str, Any]]) -> str:
    lines = [f"Project AI features ({len(features)}):"]
    for f in features:
        name = f.get("name", "")
        tier = f.get("tier", "")
        purpose = (f.get("purpose") or f.get("rough_description") or "")[:120]
        mechs = [
            (m.get("name", "") if isinstance(m, dict) else str(m))
            for m in (f.get("mechanisms") or [])
        ]
        tool_access = f.get("tool_access") or {}
        protocols: list[str] = []
        if isinstance(tool_access, dict):
            for cap in tool_access.get("capabilities_needed") or []:
                if isinstance(cap, dict) and cap.get("protocol"):
                    protocols.append(cap["protocol"])
        attrs: list[str] = [f"tier: {tier}"]
        if mechs:
            attrs.append(f"mechanisms: {', '.join(mechs)}")
        if protocols:
            attrs.append(f"tool protocols: {', '.join(sorted(set(protocols)))}")
        lines.append(f"- **{name}** ({'; '.join(attrs)}): {purpose}")
    return "\n".join(lines)


_TOPIC_CONCERNS: dict[str, str] = {
    "provider_strategy": (
        "provider_strategy — the model capability/power tier the features require; "
        "named models are allowed only as capability anchors (power references), "
        "never as vendor picks; provider/product selection and commercial "
        "cost/reliability tradeoffs are deferred to the downstream stack-selection "
        "phase"
    ),
    "tool_protocol_strategy": (
        "tool_protocol_strategy — for every tool capability across features:\n"
        "   - **Consumption**: reuse an existing MCP server when one exists rather "
        "than reimplementing.\n"
        "   - **Exposure**: build an MCP server only when a capability will have "
        "multiple consumers.\n"
        "   - **Direct call**: when a capability has exactly one consumer in the "
        "same codebase, a direct call is correct.\n"
        "   Apply the mcp pattern's build-vs-reuse distinction per capability, not "
        "globally."
    ),
    "prompt_versioning": (
        "prompt_versioning — tracking, pinning, and rolling back prompts per feature"
    ),
}

_TOPIC_SCHEMA_FRAGMENTS: dict[str, str] = {
    "provider_strategy": """\
  "provider_strategy": {
    "recommendation": "string — the model capability/power tier the features require; you MAY anchor to a named model purely as a power reference (e.g. 'capabilities comparable to <model>'), but do NOT select a provider/vendor or weigh commercial cost/reliability tradeoffs — provider and product selection is the downstream stack-selection phase",
    "rationale": "string",
    "cited_patterns": []
  }""",
    "tool_protocol_strategy": """\
  "tool_protocol_strategy": {
    "recommendation": "string — for each tool capability across features: MCP vs direct call, and build vs reuse",
    "rationale": "string — explicitly apply consumption-vs-exposure from the mcp pattern",
    "cited_patterns": ["mcp"]
  }""",
    "prompt_versioning": """\
  "prompt_versioning": {
    "recommendation": "string — strategy for tracking and pinning prompt versions per feature",
    "rationale": "string",
    "cited_patterns": []
  }""",
}


def _schema_for(topics: list[str]) -> str:
    """Assemble the JSON output schema for exactly the given topics."""
    return "{\n" + ",\n".join(_TOPIC_SCHEMA_FRAGMENTS[t] for t in topics) + "\n}"


_PROVIDER_LANE_RULE = """\
**Framing rule — capability requirement vs vendor selection (provider_strategy).**
For provider_strategy, state the *capability level* the features require — the
power tier of model needed, the fallback posture, and where a smaller or cheaper
model suffices versus where a frontier model is warranted. You MAY anchor a
capability level to a named model purely as a power reference (e.g. "a model with
capabilities comparable to Opus 4.8"): naming a model to communicate HOW MUCH
capability is required is in-lane. You MUST NOT select a provider or vendor,
recommend one commercial product over another, or weigh
cost/pricing/reliability/contractual tradeoffs between providers — choosing the
actual provider, product, and commercial terms is the downstream stack-selection
phase's responsibility, not yours. Describe the capability; leave procurement to
the stack phase."""


def _build_system_prompt(
    mechanisms: list[MechanismPattern],
    topics: list[str],
) -> str:
    mech_block = _mechanism_context(mechanisms)
    if len(topics) == 1:
        task_line = (
            f"Revise the **{topics[0]}** decision only. Output a single JSON "
            "object with a key for that topic."
        )
    else:
        task_line = (
            f"Analyse these {len(topics)} cross-cutting concerns and output a JSON "
            "object with a key per topic."
        )
    concern_lines = "\n".join(
        f"{i}. {_TOPIC_CONCERNS[t]}" for i, t in enumerate(topics, 1)
    )
    lane_rule = f"\n{_PROVIDER_LANE_RULE}\n" if "provider_strategy" in topics else ""
    schema = _schema_for(topics)

    return f"""\
You are Cross-Cutting Analyst, embedded in Spec4's Agentifier pipeline.

You reason ACROSS all AI features in the project to surface system-level decisions
that should be standardised. You are READ-ONLY on per-feature specs: you analyse them
but never modify them.

{mech_block}

**Task:** {task_line}

**Cross-cutting concerns to analyse:**
{concern_lines}
{lane_rule}
**Output rules:**
1. Output ONLY a single ```json ... ``` fenced block — no prose before or after.
2. Recommendations must be SPECIFIC to this project's features — no generic boilerplate.
3. cited_patterns must name actual patterns from the library above (exact names), or be an empty list.
4. Recommendations must be actionable: name the approach, tool, or standard.

Required output schema:
```json
{schema}
```
"""


def _existing_ai_infra_block(code_review: dict[str, Any]) -> str:
    """Extract existing AI/ML infra for cross-cutting bias-toward-reuse guidance."""
    from spec4.agentifier.tier_analyst import _existing_ai_context
    hint = _existing_ai_context(code_review)
    if not hint:
        return ""
    return (
        "\n**Existing AI infrastructure (bias toward reuse over new tooling):**\n"
        + hint
        + "\nWhen making cross-cutting recommendations, prefer tools already in use over introducing new ones.\n"
    )


def _build_user_content(input_obj: CrossCuttingInput) -> str:
    parts = [_feature_digest(input_obj.ai_features), ""]
    if input_obj.code_review:
        infra = _existing_ai_infra_block(input_obj.code_review)
        if infra:
            parts.append(infra)
    if input_obj.topic and input_obj.revision_instruction:
        prior = (input_obj.prior_decisions or {}).get(input_obj.topic, {})
        if prior.get("recommendation"):
            parts.append(f"Previous recommendation for **{input_obj.topic}**: {prior['recommendation']}")
        parts.append(f"**Revision request:** {input_obj.revision_instruction}")
        parts.append(f"Please revise the **{input_obj.topic}** recommendation accordingly.")
    else:
        parts.append("Please produce cross-cutting recommendations for the requested topics.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class CrossCuttingAnalyst:
    """StreamingSubAgent: yields JSON chunks of the cross-cutting analysis."""

    name = "cross_cutting_analyst"

    async def stream(self, input: CrossCuttingInput) -> AsyncIterator[str]:  # noqa: A002
        validate_dataclass_input(input, CrossCuttingInput)
        if input.topic is not None:
            topics = [input.topic]
        else:
            topics = input.topics or list(CROSS_CUTTING_TOPICS)
        system = _build_system_prompt(input.mechanism_patterns, topics)
        user_content = _build_user_content(input)
        llm_config = input.llm_config
        response = await acomplete(
            llm_config=llm_config,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            agent_name="cross_cutting_analyst",
            stream=True,
        )
        async for chunk in response:
            delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            if delta:
                yield delta
