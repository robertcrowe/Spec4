"""Tier Analyst sub-agent for Agentifier.

Takes one AI-opportunity candidate and the tier pattern library, then
recommends the cheapest tier that works.  The prompt is deliberately
convergent and skeptical — defaulting downward unless escalation is
clearly justified.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from spec4.agentifier.pattern_loader import (
    MechanismPattern,
    TierPattern,
    load_patterns,
)
from spec4.agentifier.scout import Candidate
from spec4.agentifier.subagents import validate_dataclass_input
from spec4.llm import complete_stream

TIER_ANALYST_SYSTEM_PROMPT = """\
You are the Tier Analyst for Agentifier. Your job is to recommend the CHEAPEST
appropriate tier from the AI-integration ladder for a given candidate feature.

Your default posture is: "the simpler solution probably works." You are
convergent and skeptical. Only escalate when the cheaper tier's "When it doesn't"
section is unambiguously triggered by this specific candidate.

**Framing rule — candidate names are not evidence.**
The candidate's name and description often use aspirational language ("smart",
"intelligent", "optimized", "personalized", "predictive", "automated",
"engine", "AI-powered"). These words are NOT evidence for a higher tier. Strip
them and reason only from what the feature must concretely do — what are the
actual inputs, and what computation produces the output? A candidate named with
"prediction" or "intelligence" may, in mechanism, be arithmetic, a lookup
table, or a threshold check. Evaluate the mechanism, not the marketing.

**Framing rule — data scale and freshness are not evidence.**
A feature is not more complex because its backing data is large, changes
frequently, or "can't fit in a prompt." `deterministic` includes querying a live
database, key-value store, or external API by an exact identifier (e.g. a
barcode, SKU, ISBN, or row ID) and returning the matching record — the catalog's
size, update frequency, and churn are handled by the datastore and do NOT change
the tier. `deterministic` does not mean a static, hardcoded, or in-prompt table;
an exact-key lookup against a live, frequently-updated backend is still
`deterministic`. Escalating to `embeddings` or `rag` requires that the *input* be
matched *semantically* (fuzzy names, natural-language meaning, long-tailed
variation) or that the answer be *generated* by grounding on retrieved
*unstructured* content — not merely that a structured record be fetched by key.
An exact identifier mapped to a structured record is `deterministic` no matter how
large or fresh the backing store.

**Framing rule — operational benefits are not evidence.**
Testability, debuggability, observability, caching, validation of intermediate
results, and the cost of splitting work are engineering choices, not tier
drivers — they do NOT justify escalating a tier. In particular, do not escalate
`single_call` to `chained_calls` merely because splitting would make steps easier
to test, inspect, or cache: those are the chained_calls "When it works" bullets,
but its "When it doesn't" and "Over-engineering signs" govern the tier. If a
single structured-output call would reliably produce all the needed fields, the
tier is `single_call`. Deterministic computation belongs in application code, not
in the chain — a step that aggregates, calculates, parses, formats, or looks up
is plain code, not an LLM call. A feature that computes metrics deterministically
and then makes ONE LLM call to generate a report, summary, or suggestions is
`single_call` with deterministic preprocessing, NOT `chained_calls`. Escalate to
`chained_calls` only when a later LLM call's input genuinely depends on an
earlier LLM call's output — a true sequential LLM-to-LLM dependency that one
structured-output call cannot reliably produce. If you recommend `chained_calls`,
name the specific LLM steps and the earlier LLM output each later step consumes;
if you cannot, the answer is `single_call`. Reason only from what the feature as
described must do — do not invent reflection, critique, or validation loops the
candidate does not state.

**Framing rule — mechanisms are not tiers.**
The items below are implementation MECHANISMS. A mechanism is a choice about
HOW a tier is built; it lives INSIDE whatever tier the task itself requires and
NEVER moves a candidate up the ladder:
{mechanism_context}

Apply these absorptions before considering any escalation:
- Running the SAME task over many independent items concurrently is
  parallel_fanout inside the base tier. "Sweep 80 contracts", "score every open
  PR", "process each file" is the single-item tier (usually single_call) fanned
  out over the batch — it is NOT orchestrated_subagents. Orchestration requires
  HETEROGENEOUS specialist roles whose outputs a coordinator must synthesize,
  not one prompt repeated N times with a mechanical merge. Volume and
  concurrency are throughput properties, never tier evidence.
- A validation, critique-and-revise, or check-then-retry loop that the
  candidate STATES is the reflection mechanism at the base tier — it is not
  evidence for chained_calls, planning_agent, or any higher tier. (And per the
  rule above, if the candidate does not state such a loop, do not invent one.)
- A human approval, confirmation, or review step that the candidate STATES is
  human_in_the_loop at the base tier. An approval gate changes
  decision_authority, never the tier.
- HOW external data or tools are reached — an MCP server versus a direct
  API/SDK call — is the mcp mechanism and never changes the tier. Fetching
  records from an external service by exact key or query ("collect PRs from
  GitHub") is a lookup plus at most one LLM step, not an agent team.
- Reranking retrieved candidates is retrieval_reranking inside rag. It refines
  the rag tier; it does not make the feature more than rag.
- Emitting typed or schema-constrained JSON is structured_outputs, available at
  every tier. Needing machine-readable output is never evidence for
  chained_calls or above.
If stripping the mechanism away leaves work one tier can do, recommend that
tier: the mechanism is an implementation note for later phases, not your
recommendation — your output remains a tier only.

The tier ladder (from cheapest/simplest to most complex):
{tier_descriptions}

Evaluation process:
1. Start at `deterministic`. Could this be a lookup table, formula, regex,
   finite state machine, sort, threshold, or classical algorithm? If yes,
   recommend `deterministic`. **Burden of proof:** before recommending any tier
   above deterministic, you must name a specific concrete input that a
   deterministic implementation would provably get wrong or could not produce —
   state it in one sentence in your rationale. That concrete reason must be
   a property of the *input itself* — it is fuzzy, semantic, ambiguous,
   natural-language, or unstructured — not a property of the backing data
   store such as its size, freshness, or update frequency, which a database
   or API lookup handles and which never justify escalation.
   If you cannot name such an input, the correct recommendation is `deterministic`. Consult the
   deterministic pattern's "Over-engineering signs": date math, parsing
   structured formats, arithmetic, sorting, and threshold logic are
   deterministic regardless of how the candidate is named. Equally, do not
   under-engineer: if the deterministic pattern's "Under-engineering signs" are
   triggered (semantics rather than syntax, long-tailed fuzzy inputs,
   "understand what the user meant"), escalate. The standard is the cheapest
   tier that works, not the cheapest tier.
2. Move up ONE tier at a time. Only escalate if the current tier's "When it
   doesn't" bullets are clearly triggered by this candidate's description. If
   the only escalation pressure is batch volume/concurrency, a stated
   validation loop, a stated approval step, tool/data plumbing, or output
   formatting, that pressure is a mechanism (see the framing rule above) — stay
   at the base tier.
3. Stop at the first tier where the "When it works" bullets are satisfied.
4. If you stop at a tier that is adjacent to the tier below (the recommendation
   is defensible but the candidate sits near the edge), set borderline=true and
   name the specific seams to watch.

Required output — valid JSON, no other text:
{{
  "recommended_tier": "<exact tier name from the ladder>",
  "rationale": "<one paragraph grounded in the pattern's when_works and when_doesnt content>",
  "risks_of_going_higher": ["<specific named risk if user picks a more complex tier>"],
  "risks_of_going_lower": ["<specific named risk if user picks a simpler tier>"],
  "borderline": <true or false>,
  "borderline_seams": ["<seam to watch — only when borderline=true, else empty array>"],
  "compared_to_next_tier_down": "<1–2 sentences: what the next-cheaper tier would lose for this candidate — required for any recommendation above deterministic>"
}}

Rules:
- `recommended_tier` must be the exact name of one of the nine tiers.
- `borderline_seams` must be an empty array when `borderline` is false.
- `compared_to_next_tier_down` is required when the recommendation is anything
  above `deterministic`; for `deterministic` it may be an empty string.
- Do not include any text outside the JSON object.
"""

_VALID_TIERS = (
    "deterministic",
    "embeddings",
    "single_call",
    "rag",
    "tool_agent",
    "chained_calls",
    "planning_agent",
    "orchestrated_subagents",
    "multi_agent_collaboration",
)


@dataclass
class TierAnalystInput:
    candidate: Candidate
    llm_config: dict[str, Any]
    tier_patterns: list[TierPattern] = field(default_factory=list)
    code_review: dict[str, Any] | None = field(default=None)
    mechanism_patterns: list[MechanismPattern] = field(default_factory=list)
    # Developer guidance from a guided redraw of the breadth panel (the notes
    # typed into "Tell me what to change" before Try Again). Scout is the
    # primary consumer; it reaches here so "keep it simple" also weighs on the
    # tier recommendation for the survivors. Empty for an un-guided run, in
    # which case the prompt is byte-identical to before.
    guidance: list[str] = field(default_factory=list)
    # Receipt-counter hook (D-PH9): called with each streamed text delta as it
    # arrives, so the orchestrator can publish liveness while the response is
    # drained internally. ``None`` drains silently (the prior behavior).
    on_chunk: Callable[[str], None] | None = field(default=None)


@dataclass
class TierAnalystOutput:
    recommended_tier: str
    rationale: str
    risks_of_going_higher: list[str]
    risks_of_going_lower: list[str]
    borderline: bool
    borderline_seams: list[str]
    compared_to_next_tier_down: str


_AI_INFRA_KEYWORDS = frozenset({
    "openai", "anthropic", "langchain", "llamaindex", "llama_index",
    "pinecone", "weaviate", "chroma", "chromadb", "qdrant", "milvus",
    "cohere", "gemini", "mistral", "huggingface", "transformers",
    "semantic_kernel", "autogen", "crewai", "haystack", "instructor",
    "litellm", "guidance", "outlines", "marvin", "pydantic_ai",
    "faiss", "pgvector", "sentence_transformers", "sentence-transformers",
    "ollama", "groq", "vllm", "together", "fireworks", "replicate",
    "openrouter", "bedrock",
})


def _existing_ai_context(code_review: dict[str, Any]) -> str:
    """Return a compact summary of existing AI/ML infrastructure from code_review.

    Prefers the scanner's first-class ``ai_capabilities`` section (detected at
    scan time by the model that read the code); the dependency/framework
    keyword scan is retained as a fallback and appended alongside — old
    artifacts and reviews without the section still surface what they can.
    """
    cr = code_review.get("code_review", code_review) if isinstance(code_review, dict) else {}
    found: list[str] = []
    cap_lines: list[str] = []
    for c in cr.get("ai_capabilities") or []:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        line = f"- {c['name']}"
        if c.get("kind"):
            line += f" [{c['kind']}]"
        if c.get("description"):
            line += f": {c['description']}"
        if c.get("location"):
            line += f" ({c['location']})"
        cap_lines.append(line)
    if cap_lines:
        found.append("Existing AI capabilities in the codebase:\n" + "\n".join(cap_lines))
    deps = cr.get("dependencies") or []
    ai_deps = [
        d.get("name", "") for d in deps
        if isinstance(d, dict) and any(kw in d.get("name", "").lower() for kw in _AI_INFRA_KEYWORDS)
    ]
    if ai_deps:
        found.append("AI/LLM dependencies already in place: " + ", ".join(ai_deps))
    frameworks = cr.get("frameworks") or []
    ai_fw = [
        f.get("name", "") for f in frameworks
        if isinstance(f, dict) and any(kw in f.get("name", "").lower() for kw in _AI_INFRA_KEYWORDS)
    ]
    if ai_fw:
        found.append("AI/LLM frameworks already in use: " + ", ".join(ai_fw))
    return "\n".join(found)


def _build_tier_descriptions(tiers: list[TierPattern]) -> str:
    """Build a concise per-tier summary for injection into the system prompt."""
    lines: list[str] = []
    for tier in sorted(tiers, key=lambda t: t.tier_order):
        lines.append(f"\n**{tier.tier_order}. {tier.name}**")
        # Trim description to first 200 chars to keep the prompt manageable
        desc = tier.description.strip()
        if len(desc) > 200:
            desc = desc[:200].rstrip() + "…"
        lines.append(desc)
        works = tier.when_works[:3]
        lines.append("When it works: " + "; ".join(works))
        doesnt = tier.when_doesnt[:2]
        lines.append("When it doesn't: " + "; ".join(doesnt))
    return "\n".join(lines)


def _build_mechanism_absorption_list(mechanisms: list[MechanismPattern]) -> str:
    """One line per mechanism for the 'mechanisms are not tiers' framing rule.

    Deliberately compact — name plus a trimmed description — because the Tier
    Analyst only needs to recognise a mechanism well enough NOT to escalate for
    it; the Spec Drafter carries the full pattern content.
    """
    lines: list[str] = []
    for m in mechanisms:
        summary = " ".join(m.description.split())
        if len(summary) > 200:
            summary = summary[:200].rstrip() + "…"
        lines.append(f"- **{m.name}**: {summary}")
    return "\n".join(lines)


def _parse_output(raw: str, valid_tier_names: list[str]) -> dict[str, Any]:
    """Extract and parse the JSON tier-recommendation from the LLM response."""
    for attempt in (raw.strip(), _extract_json_object(raw)):
        if attempt is None:
            continue
        try:
            data = json.loads(attempt)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and "recommended_tier" in data:
            return data
    return {}


def _extract_json_object(text: str) -> str | None:
    """Return the first top-level JSON object found in text, or None."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group() if match else None


class TierAnalystAgent:
    """Request/response sub-agent that recommends a tier for one AI candidate."""

    name = "tier_analyst"

    async def run(self, input: TierAnalystInput) -> TierAnalystOutput:  # noqa: A002
        validate_dataclass_input(input, TierAnalystInput)

        tier_patterns = input.tier_patterns or []
        mechanism_patterns = input.mechanism_patterns or []
        if not tier_patterns or not mechanism_patterns:
            loaded_tiers, loaded_mechanisms = load_patterns()
            tier_patterns = tier_patterns or loaded_tiers
            mechanism_patterns = mechanism_patterns or loaded_mechanisms

        valid_names = [t.name for t in tier_patterns]
        tier_descriptions = _build_tier_descriptions(tier_patterns)
        system = TIER_ANALYST_SYSTEM_PROMPT.format(
            tier_descriptions=tier_descriptions,
            mechanism_context=_build_mechanism_absorption_list(mechanism_patterns),
        )

        candidate = input.candidate
        candidate_payload: dict[str, Any] = {
            "name": candidate.name,
            "linked_vision_features": candidate.linked_vision_features,
            "scope": candidate.scope,
            "rough_description": candidate.rough_description,
        }
        # Conditional so greenfield prompts stay byte-identical.
        if candidate.linked_existing_workflow:
            candidate_payload["linked_existing_workflow"] = candidate.linked_existing_workflow
        candidate_text = json.dumps(candidate_payload, indent=2)

        ai_hint = _existing_ai_context(input.code_review) if input.code_review else ""
        brownfield_note = (
            f"\n\n**Existing AI infrastructure (bias toward reuse):**\n{ai_hint}"
            if ai_hint else ""
        )
        notes = [str(n).strip() for n in (input.guidance or []) if str(n).strip()]
        guidance_note = (
            "\n\n**Developer guidance (from the redraw request — weigh toward "
            "simpler tiers where it applies):**\n"
            + "\n".join(f"- {n}" for n in notes)
            if notes
            else ""
        )
        user_content = (
            f"Candidate:\n```json\n{candidate_text}\n```"
            f"{brownfield_note}{guidance_note}\n\n"
            "Recommend the cheapest appropriate tier from the ladder above."
        )

        llm_config = input.llm_config
        buf: list[str] = []
        for delta in complete_stream(
            llm_config=llm_config,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            agent_name="tier_analyst",
        ):
            buf.append(delta)
            if input.on_chunk is not None:
                input.on_chunk(delta)
        raw = "".join(buf).strip()
        data = _parse_output(raw, valid_names)

        # Normalise recommended_tier to a known value
        recommended = str(data.get("recommended_tier", "")).strip()
        if recommended not in valid_names:
            recommended = valid_names[0] if valid_names else "deterministic"

        borderline = bool(data.get("borderline", False))
        seams: list[str] = list(data.get("borderline_seams") or [])
        if not borderline:
            seams = []

        return TierAnalystOutput(
            recommended_tier=recommended,
            rationale=str(data.get("rationale", "")),
            risks_of_going_higher=list(data.get("risks_of_going_higher") or []),
            risks_of_going_lower=list(data.get("risks_of_going_lower") or []),
            borderline=borderline,
            borderline_seams=seams,
            compared_to_next_tier_down=str(data.get("compared_to_next_tier_down", "")),
        )
