"""Spec Drafter sub-agent: elaborates a tier-aware implementation spec per feature.

StreamingSubAgent — yields text chunks of a structured JSON spec.
The orchestrator collects the full text, extracts the JSON block, and formats
a human-readable Markdown display for the chat window.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from spec4.agentifier.grounding import render_grounding_for_prompt
from spec4.agentifier.pattern_loader import MechanismPattern, TierPattern
from spec4.agentifier.subagents import validate_dataclass_input
from spec4.llm import acomplete

# Maps tier name → position on the ladder (1 = cheapest).
_TIER_ORDER: dict[str, int] = {
    "deterministic": 1,
    "embeddings": 2,
    "single_call": 3,
    "rag": 4,
    "tool_agent": 5,
    "chained_calls": 6,
    "planning_agent": 7,
    "orchestrated_subagents": 8,
    "multi_agent_collaboration": 9,
}


# ---------------------------------------------------------------------------
# Input / output types
# ---------------------------------------------------------------------------


@dataclass
class SpecDrafterInput:
    """Input to SpecDrafterAgent.stream()."""

    catalog_entry: dict[str, Any]
    """One entry from the ai_catalog — name, scope, tier_decision, rationale."""

    llm_config: dict[str, Any]
    """LiteLLM config: model, api_key, optional api_base."""

    tier_patterns: list[TierPattern]
    """Full tier pattern library (from load_patterns)."""

    mechanism_patterns: list[MechanismPattern]
    """Full mechanism pattern library (from load_patterns)."""

    revision_instruction: str | None = field(default=None)
    """Non-None when the user asked to revise a previously drafted spec."""

    vision_grounding: dict[str, Any] | None = field(default=None)
    """Product features this AI feature serves, from Brainstormer's confirmed
    ``feature_specs`` (D-AC1 B). When present, its ``served_features`` are
    rendered into the user content as authoritative behavioral context so the
    spec is authored against real inputs/outputs/success-criteria rather than the
    one-line ``rough_description``. ``None`` (or empty) leaves the prompt
    unchanged — legitimate for cross-cutting features that serve no named
    product feature."""

    linked_existing_workflow: str = field(default="")
    """The existing manual/rule-based implementation this feature replaces or
    augments — Scout's per-candidate capture, joined to the catalog entry by
    name by the orchestrator (the candidate is authoritative — D-EP). Empty
    for greenfield candidates; leaves the prompt byte-identical."""

    existing_ai_context: str = field(default="")
    """Compact summary of AI/ML infrastructure already in the codebase, from
    ``tier_analyst._existing_ai_context(code_review)``, precomputed by the
    orchestrator (the vision_grounding precedent — the agent never sees the
    raw code_review). Empty for greenfield runs; leaves the prompt
    byte-identical."""


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

_BASE_FIELD_BLOCK = """\
  "purpose": "string — one sentence: why this feature exists and what problem it solves",
  "invocation": {
    "trigger": "string — what event or call triggers this feature (user action, API call, schedule, etc.)",
    "mode": "synchronous | asynchronous | scheduled | streaming"
  },
  "inputs": [
    { "name": "string", "type": "string", "description": "string", "required": true }
  ],
  "outputs": {
    "primary": "string — human description of what the feature produces",
    "format": "string — e.g. JSON object, plain text, structured list",
    "schema_notes": "string — key shape notes or null"
  },
  "decision_authority": "autonomous | confirm | suggest",
  "success_criteria": ["string — measurable signal that the feature is working"],
  "failure_modes": [
    { "mode": "string", "likelihood": "low | medium | high", "mitigation": "string" }
  ],
  "escalation": "string — what happens on failure: fallback, alert, human review, etc.",
  "eval_approach": {
    "offline": "string — how to test before deployment",
    "online": "string — how to monitor in production",
    "ground_truth": "string — how to obtain labels / golden examples"
  },
  "budgets": {
    "cost_per_call": "string — target cost per invocation, e.g. '$0.002'",
    "p95_latency": "string — target p95 latency, e.g. '800ms'"
  },
  "privacy_safety": ["string — PII handling, content filtering, output safety notes"],
  "mechanisms": [
    { "name": "string — mechanism pattern name", "rationale": "string", "configuration": {} }
  ],
  "references": ["string — canonical doc, paper, or standard; include URL when known"]"""

_KNOWLEDGE_SOURCES_FIELD = """\
  "knowledge_sources": [
    {
      "name": "string — data source name",
      "type": "vector_store | relational_db | document_store | api | file_system | other",
      "content_description": "string — what information it contains",
      "update_frequency": "string — e.g. 'real-time', 'daily', 'static'"
    }
  ],"""

_TOOL_ACCESS_FIELD = """\
  "tool_access": {
    "capabilities_needed": [
      {
        "purpose": "string — what the tool call achieves",
        "source": "existing_third_party_mcp | existing_third_party_non_mcp | to_build_internal — DEFAULT to existing_third_party_mcp: GitHub, web search, browsers, filesystems, and databases all have maintained MCP servers. Choose to_build_internal ONLY when you can name why no existing server fits, and say why in rationale",
        "mcp_server": "string or null — MCP server name/URL if applicable",
        "protocol": "mcp | direct | sdk_wrapped",
        "rationale": "string — why this source/protocol was chosen; for to_build_internal, name the existing server you rejected and why"
      }
    ]
  },"""

_TOPOLOGY_FIELD = """\
  "topology": {
    "coordinator_role": "string — what the coordinator LLM does",
    "subagents": [
      {
        "name": "string",
        "role": "string — what this sub-agent specialises in",
        "input": "string — what it receives",
        "output": "string — what it produces"
      }
    ],
    "communication_pattern": "sequential | parallel | adaptive",
    "synthesis_approach": "string — how coordinator merges sub-agent outputs"
  },"""


def _tier_extra_fields(tier_order: int) -> str:
    """Return the tier-conditional field block for the JSON schema."""
    parts: list[str] = []
    if tier_order >= 4:
        parts.append(_KNOWLEDGE_SOURCES_FIELD)
    if tier_order >= 5:
        parts.append(_TOOL_ACCESS_FIELD)
    if tier_order >= 8:
        parts.append(_TOPOLOGY_FIELD)
    return "\n".join(parts)


def _mechanism_context(mechanisms: list[MechanismPattern]) -> str:
    """Render the full mechanism library: description plus all four sign lists.

    References and frontmatter are excluded — they are provenance, not
    decision content. Returns "" for an empty library so the surrounding
    prompt carries no dangling header.
    """
    if not mechanisms:
        return ""
    lines = [
        "**Mechanism pattern library** (use zero or more) — the only valid "
        'candidates for the "mechanisms" field. Read each pattern\'s signs '
        "before deciding:",
    ]
    for m in mechanisms:
        lines.append(f"\n### {m.name}")
        lines.append(m.description.strip())
        lines.append("\nWhen it works:")
        lines.extend(f"- {b}" for b in m.when_works)
        lines.append("When it doesn't:")
        lines.extend(f"- {b}" for b in m.when_doesnt)
        lines.append("Over-engineering signs:")
        lines.extend(f"- {b}" for b in m.over_engineering_signs)
        lines.append("Under-engineering signs:")
        lines.extend(f"- {b}" for b in m.under_engineering_signs)
    return "\n".join(lines)


def _build_system_prompt(
    tier_name: str,
    tier_order: int,
    tier_pattern: TierPattern | None,
    mechanism_patterns: list[MechanismPattern],
) -> str:
    tier_desc = tier_pattern.description if tier_pattern else f"The {tier_name} tier."
    extra = _tier_extra_fields(tier_order)
    mech_block = _mechanism_context(mechanism_patterns)
    # Cross-wire the mcp mechanism to the tool_access schema block. Only tiers
    # that carry tool_access (>= tool_agent) may mention it — lower-tier
    # prompts must stay free of the literal (schema discipline, test-guarded).
    mcp_agreement = ""
    if tier_order >= 5:
        mcp_agreement = """
6. "mechanisms" and "tool_access" must agree: when any capability in
   tool_access.capabilities_needed has source "existing_third_party_mcp" or
   protocol "mcp", the mcp mechanism MUST also appear in "mechanisms" with a
   reuse-over-rebuild rationale — and an mcp entry in "mechanisms" requires a
   matching capability in tool_access.
"""

    system = f"""\
You are Spec Drafter, embedded in Spec4's Agentifier pipeline.

Given one accepted AI feature and its confirmed tier, you produce a complete
implementation spec. The spec is consumed directly by engineers and coding
agents — it must be specific, concrete, and implementation-ready.

When the user content includes "Product features this AI feature serves", those
come from the confirmed product vision and are AUTHORITATIVE behavioral context.
Author the spec so it serves that behavior: keep purpose, inputs, outputs, and
success_criteria consistent with the product features it serves rather than
re-deriving or contradicting them. Your job is to specify HOW this AI feature is
built at its tier — not to restate or second-guess WHAT the product does.

When the user content includes "Existing implementation this replaces" or
"Existing AI infrastructure", this is a brownfield feature: spec the delta
against what already exists. Reuse the AI stack already installed — clients,
stores, frameworks — rather than introducing parallel tooling, and reference
the existing components by name in the spec where they fit.

**Confirmed tier: {tier_name}** (position {tier_order}/9 on the ladder)

Tier description:
{tier_desc}

{mech_block}

**Output rules:**
1. Output ONLY a single ```json … ``` fenced block — no prose before or after.
2. Use null only when you genuinely have no basis for a value; prefer a concrete
   placeholder or question mark with a comment over an empty string.
3. "mechanisms" is OPTIONAL and empty by default — zero mechanisms is correct
   for most features. For each library pattern above, apply this protocol:
   a. INCLUDE a mechanism only when at least one of its "When it works" bullets
      is matched by a fact STATED in the feature description or the product
      features it serves — never by an imagined future need. The rationale you
      write MUST cite the matching bullet and the stated fact.
   b. VETO: if any of the pattern's "Over-engineering signs" describes this
      feature, do NOT include it — the veto wins even when a "When it works"
      bullet also matches.
   c. The "Under-engineering signs" are your checklist for what the feature is
      missing: if one clearly describes this feature as specified, that is a
      valid inclusion reason — cite it in the rationale.
   d. Guardrails for the common misuses:
      - structured_outputs: only when downstream CODE parses the output. Prose,
        digests, explanations, or chat replies read by a human get no schema —
        and a warning, flag, badge, or suggestion shown to a user in the UI is
        displayed, not parsed, so it gets no schema either. Ask "which line of
        code reads this field?" — if the answer is a screen, not code, leave
        this mechanism out.
      - retrieval_reranking: only when the corpus is thousands of documents or
        more AND first-stage retrieval returns many plausible candidates with
        poor ordering. A single handbook, manual, or policy document — however
        long — is not a corpus; exact-key lookups and simple fuzzy matching
        never get a reranker.
      - human_in_the_loop: only where mistakes are costly, irreversible, or
        regulated AND the review volume is humanly feasible. High-volume
        reversible actions and periodic informational outputs get no gate.
      - mcp: GitHub, web search, browsers, filesystems, and databases all have
        maintained MCP servers. When this feature consumes any such external
        capability, include mcp with a reuse-over-rebuild rationale unless you
        can name why no existing server can serve it. Expose your own
        capability over MCP only when it has multiple consumers.
      - parallel_fanout: when the feature processes many independent items and
        latency or per-item focus matters — the rationale must name the
        independent unit of work.
      - reflection: when the feature states a validate/critique/retry loop or
        has an external checker (tests, schema, validator) to ground one — not
        by default.
4. All required fields must be present. Omitting a required field or inventing
   a non-schema key will break downstream processing.
5. "decision_authority": choose "autonomous" only if the system acts without
   showing the result to a human first; "confirm" if a human must approve;
   "suggest" if the system presents an option the user can accept or ignore.
{mcp_agreement}
**Required JSON schema for {tier_name}:**

```json
{{
{_BASE_FIELD_BLOCK}
{extra}
}}
```
"""
    return system


def _build_user_content(input_obj: SpecDrafterInput, tier_name: str) -> str:
    entry = input_obj.catalog_entry
    name = entry.get("name", "")
    scope = entry.get("scope", "feature")
    desc = entry.get("rough_description", "")
    rationale = entry.get("tier_decision_rationale", "")

    lines = [
        f"Feature: **{name}** (scope: {scope})",
        f"Rough description: {desc}",
        f"Decided tier: **{tier_name}**",
    ]
    if rationale:
        lines.append(f"Tier decision rationale: {rationale}")
    grounding_block = render_grounding_for_prompt(input_obj.vision_grounding)
    if grounding_block:
        lines.append("")
        lines.append(grounding_block)
    if input_obj.linked_existing_workflow:
        lines.append(
            "\n**Existing implementation this replaces:** "
            f"{input_obj.linked_existing_workflow}"
        )
    if input_obj.existing_ai_context:
        lines.append(
            "\n**Existing AI infrastructure (bias toward reuse):**\n"
            f"{input_obj.existing_ai_context}"
        )
    if input_obj.revision_instruction:
        lines.append(
            f"\n**Revision instruction from developer:** {input_obj.revision_instruction}\n"
            "Revise the spec accordingly while keeping all required fields."
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class SpecDrafterAgent:
    """StreamingSubAgent: yields chunks of the structured spec JSON.

    Each call to stream() makes one streaming LLM call. The caller collects
    all chunks, then extracts the JSON block via _extract_json_block().
    """

    name = "spec_drafter"

    async def stream(self, input: SpecDrafterInput) -> AsyncIterator[str]:  # noqa: A002
        validate_dataclass_input(input, SpecDrafterInput)

        entry = input.catalog_entry
        tier_name: str = (
            entry.get("tier_decision") or entry.get("tier") or "single_call"
        )
        tier_order = _TIER_ORDER.get(tier_name, 3)

        tier_pattern = next(
            (t for t in input.tier_patterns if t.name == tier_name), None
        )

        system_prompt = _build_system_prompt(
            tier_name, tier_order, tier_pattern, input.mechanism_patterns
        )
        user_content = _build_user_content(input, tier_name)

        llm_config = input.llm_config
        response = await acomplete(
            llm_config=llm_config,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            agent_name="spec_drafter",
            stream=True,
        )
        async for chunk in response:
            delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            if delta:
                yield delta
