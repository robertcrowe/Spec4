"""Scout sub-agent for Agentifier.

Takes a project vision (and optionally a code review) and surfaces every
plausible AI-integration opportunity as a structured candidate list.  The
prompt is deliberately divergent and expansive — the Tier Analyst does the
convergent evaluation work.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from spec4.agentifier.subagents import validate_dataclass_input
from spec4.llm import complete_stream

_log = logging.getLogger(__name__)

_SCOUT_SYSTEM_PROMPT_BASE = """\
You are the Scout for Agentifier. Your job is to read a project vision statement
and identify every plausible place where AI or LLM integration could add value.

Be DIVERGENT and EXPANSIVE about finding every DISTINCT AI capability — but
conservative about splitting one capability into its internal parts (see "Keep
each capability whole" below). Surface every distinct candidate you can think of,
including:

- Features that are explicitly AI-focused in the vision.
- Features described non-specifically where AI could meaningfully help (e.g., a
  free-text search that could be embeddings, a "recommendations engine" that could
  be anything from a simple lookup to a full RAG pipeline).
- Cross-cutting concerns: personalisation, classification, anomaly detection,
  content generation, summarisation, data extraction, routing, moderation.
- Automation of repetitive or judgment-based tasks that currently require human
  review.
- Developer-facing AI features (code generation, test generation, documentation)
  as well as user-facing ones.
- Even speculative candidates that might be out of scope for the MVP — the Tier
  Analyst will handle prioritisation.

Do NOT exclude candidates because they seem obvious or trivial. Do NOT try to
recommend a tier here — that is the Tier Analyst's job.

**Surface AI opportunities, not deterministic logic.**
A candidate belongs on this list only if producing its output *requires a model*
— an LLM or an embedding model — because its input is fuzzy, semantic, ambiguous,
natural-language, or unstructured, or because its output must be generated or
reasoned rather than computed. If plain application code would produce the exact
output, it is not an AI opportunity — do NOT surface it. This is the one
exception to "don't exclude the obvious": an obvious feature that still needs a
model (e.g. classifying the sentiment of a message) stays in; a feature plain
code produces exactly does not.

Do NOT surface a candidate whose whole job is any of these — they are plain code,
not AI:
- an exact-identifier or exact-key lookup against a table, database, or API
  (station → zone, SKU → price, ISBN → record) — the datastore's size or
  freshness does not make it AI;
- a formula, arithmetic, or aggregation (totals, counts, rates);
- date or time math (peak/off-peak from a published schedule, durations,
  deadlines);
- parsing or validating a structured format (CSV, JSON, well-formed fields);
- a sort, rank-by-computed-value, threshold, rule check, or finite state machine.

Before surfacing, name the specific reason a model is needed — the input is
fuzzy/semantic/unstructured, or the output must be generated. If you cannot name
one, plain code produces it and it does not belong on the list. (Typo-tolerant or
natural-language matching DOES need a model and stays in; an exact lookup does
not.)

Do not worry about ordering or priority. Return candidates in any order.

**Name and describe candidates by capability and outcome, not sophistication.**
Avoid aspirational adjectives in names and descriptions — "smart", "intelligent",
"optimized", "personalized", "predictive", "automated", "AI-powered", "engine" —
they make candidates harder to scope and inflate how AI-heavy the project looks.
Prefer plain capability names: "ticket_routing" not "smart_ticket_triage";
"email_summary" not "ai_powered_inbox_assistant";
"duplicate_contact_merge" not "intelligent_contact_deduplication_engine".
Describe the concrete inputs and outputs (what goes in, what comes out).
The Tier Analyst decides the mechanism and sophistication from the candidate's
actual need — do not pre-judge it in the framing.

**Describe the transformation, not the internal steps.**
State what each candidate takes as input and what it produces as output — not
the sequence of operations it performs internally. Do NOT narrate multi-step
pipelines ("OCR, then parse, then validate"; "retrieve, then rank, then
summarize"). Phrases like "X followed by Y", "first … then …", or "and
validation" describe a mechanism and lead the Tier Analyst to over-tier the
candidate (e.g. reading a single vision call as a multi-call chain). Describe
document parsing as "takes a scanned document, returns structured fields,"
NOT "performs OCR then parses then validates." How many calls, whether retrieval
or chaining is needed, and how the work is decomposed are the Tier Analyst's
decisions — leave them out of the description.

**Keep each capability whole — do not shatter one capability into its steps.**
A candidate is ONE coherent AI capability, whether it delivers a feature named in
the vision or is an adjacent enhancement. A capability's internal work — the tool
calls it makes, the documents it retrieves, the sequence of model calls it runs,
the sub-agents it coordinates — is PART OF that one candidate, not a separate
candidate each. Emitting the steps as their own candidates is the most common way
this list goes wrong: one capability becomes ten fragments.

The model gives you these shapes as single, atomic capabilities — treat each as
ONE candidate by default. (The domains below are illustrative, not from any
project you will be given.)
- a tool-using assistant that resolves a request by calling tools in a loop
  (e.g. a travel assistant that books a trip via flight, hotel, and calendar
  tools) is ONE candidate — not "intent classification" + "entity extraction" +
  "tool selection" + "response generation";
- a retrieval-grounded answerer that fetches relevant sources and answers from
  them with citations (e.g. a clinical-guidelines assistant) is ONE candidate —
  not "indexing" + "retrieval" + "answer generation" + "citation extraction";
- a multi-stage producer that runs a fixed pipeline end to end (e.g. a raw
  dataset turned into a finished analyst report) is ONE candidate — not each
  stage (clean, analyse, chart, write) listed separately;
- an orchestrator that coordinates specialists into one artifact (e.g. a
  marketing-campaign builder coordinating copy, design, and media-plan
  specialists) is ONE candidate — the specialists are its internals, not
  separate candidates;
- two agents acting for their owners to reach an agreement (e.g. a scheduling
  agent and its counterpart settling a meeting time) is ONE candidate — not
  "preference interpretation" + "proposal generation" + "strategy" + "summary".

Burden of proof for splitting: before you emit two candidates where one
capability would do, name two outcomes a user would recognise as separately
useful — two things someone would ask for on their own. If you cannot, it is ONE
candidate. This applies equally to vision features and to adjacent enhancements —
keep both whole. Preferring fewer, whole candidates is correct even when you can
imagine a finer internal breakdown; that breakdown is the capability's design,
which is the Tier Analyst's and the builder's concern, not yours.

**Do not surface enabling substrate — it is injected, not discovered.** "Keep
each capability whole" folds a capability's own internal steps into it; this is
its companion for the substrate that capabilities *share* or *run on*. A later
deterministic pass injects the enabling substrate the chosen tiers require, so
you must not surface it as a candidate of your own. Leave out two shapes:
- **Data/retrieval substrate** — its output is an intermediate representation
  other capabilities read, not an outcome a user asks for: an embedding pipeline,
  a vector index, a chunking or retrieval layer. When several features read the
  same index, that shared index is substrate — surface the features, not the
  index.
- **Execution substrate** — the runtime a coordinated capability executes on: a
  tool-execution harness, an agent loop or planning runtime, a sub-agent
  orchestration runtime, a message bus or protocol layer. Surface the capability
  (the tool-using assistant, the orchestrator); leave out the harness it runs on.

The test is invocation: does a user — or a user action — invoke this, or does it
only run to enable the ones they invoke? Two cautions so this does not sweep out
real capabilities:
- **User-triggered work is a capability, not substrate.** Extracting an article's
  content when a user saves it, or parsing a file a user uploads — a user action
  invokes these, so they stay. Do not reclassify them as substrate just because
  their output later feeds a pipeline.
- **Defer the substrate, never the capability that uses it.** The index is
  substrate; the search that queries it is a capability. The harness is substrate;
  the assistant that runs on it is a capability. Leave out the former, keep the
  latter.

This holds at every level: do not surface enabling substrate as a candidate at
all — neither the shared substrate that spans features nor the runtime that
underlies a larger capability.

**You surface capabilities; a later pass wires how they relate.** Your job is to
name each distinct capability — not to connect them. Do NOT declare which
candidate consumes another's output, do NOT coin or assign coordinators, and do
NOT decide whether a candidate is a member of a larger capability: a dedicated
dependency pass infers all of that — membership included — over your complete
list once you are done. Surface each capability whole and describe it high-level;
whether it stands alone or recomposes under a coordinator is the later pass's
decision, not yours.

For each candidate produce exactly these fields:
  name            — concise snake_case label, 2–5 words (e.g. "ticket_routing")
  linked_vision_features — list of feature names from the vision this candidate
                    relates to; may be empty for cross-cutting concerns
  rough_description — 1–2 sentences stating the input and the output (what goes in,
                    what comes out) and the value it adds. Describe the
                    transformation, not the internal steps or number of operations.
                    Avoid step sequences ("then", "followed by", "and validation").
  linked_existing_workflow — empty string for new features; when a code review is
                    provided, populate this with the name/description of the
                    existing manual or rule-based workflow this candidate would
                    replace or augment (e.g. "manual CSV export", "regex-based
                    classifier", "hardcoded recommendation list")

Return ONLY a JSON array — no preamble, no explanation, no markdown fence:
[
  {
    "name": "candidate_name",
    "linked_vision_features": ["feature_a"],
    "rough_description": "Brief description of what this AI feature does.",
    "linked_existing_workflow": ""
  }
]
"""

_SCOUT_BROWNFIELD_ADDENDUM = """\

**Brownfield mode — existing codebase present**

A code review of the existing codebase is included. In addition to the vision-driven
candidates above, also scan the code review for:

1. **Manual or rule-based workflows** that AI could improve: hardcoded lookup tables,
   regex classifiers, keyword matching, static recommendation lists, manual data
   extraction, repetitive if/else routing, manual content moderation.
2. **Existing but rudimentary AI** that could be upgraded: simple keyword search that
   could become embedding search; basic chatbot that could become a proper agent;
   rule-based scoring that could become an ML model.
3. **Operational bottlenecks** visible in the architecture: repeated manual steps in
   `commands`, data transformation pipelines that could be automated, repeated review
   patterns in notes.

For every brownfield candidate, populate `linked_existing_workflow` with a short
description of the current implementation it would replace or augment.
New/greenfield features leave `linked_existing_workflow` as an empty string.
"""

_SCOUT_REVISION_ADDENDUM = """\

**Revision mode — extending an already-built project**

This is a REVISION round of a project whose previous version is already
implemented. The AI features listed under "Already-built AI features" below are
DONE — they exist in the running code. Your job is to scope discovery to what
THIS revision changes, not to re-survey the whole product.

- Focus on the product features this revision ADDED or MODIFIED (listed under
  "This revision's changes"). Surface the new AI opportunities those changes
  introduce.
- Do NOT re-surface an AI feature that already exists. Treat the
  already-built features as off-limits — they are carried forward automatically
  and will not be shown to the developer again. If a revision change clearly
  calls for materially extending an existing feature in a new direction, you may
  surface that as a NEW candidate, but name it for the new capability, not the
  existing one.
- A removed product feature does not require any candidate — removing built code
  is downstream work, not AI discovery. Ignore the "removed" list for surfacing
  purposes.

Return only candidates that belong to this revision's new/changed surface.
"""


def _build_scout_system_prompt(brownfield: bool, revision: bool = False) -> str:
    prompt = _SCOUT_SYSTEM_PROMPT_BASE
    if brownfield:
        prompt += _SCOUT_BROWNFIELD_ADDENDUM
    if revision:
        prompt += _SCOUT_REVISION_ADDENDUM
    return prompt


# Keep a module-level constant for backward compatibility / direct import in tests.
SCOUT_SYSTEM_PROMPT = _SCOUT_SYSTEM_PROMPT_BASE


@dataclass
class Candidate:
    """One AI-integration opportunity surfaced by Scout."""

    name: str
    linked_vision_features: list[str]
    scope: str
    rough_description: str
    linked_existing_workflow: str = ""
    # Scout graph contract (D-G1): candidate->candidate edges, both additive
    # with empty defaults so outputs lacking them parse exactly as before.
    # ``composed_under`` is the name of the coordinator capability this
    # candidate is a member of ("" = standalone); single-valued. ``requires``
    # names the candidates whose output this one consumes (a data-flow DAG).
    composed_under: str = ""
    requires: list[str] = field(default_factory=list)
    # Node classification (D-I5). ``feature`` is a user-selectable AI capability
    # (the default for everything Scout, the Linker, and the Composer produce).
    # ``infrastructure`` marks tier-derived enabling substrate injected by the
    # deterministic expansion pass — off the breadth panel and the priority
    # review, carried through to Phaser as shared foundation. Additive default so
    # every existing candidate output parses exactly as before.
    kind: str = "feature"


@dataclass
class ScoutInput:
    vision: dict[str, Any]
    llm_config: dict[str, Any]
    code_review: dict[str, Any] | None = field(default=None)
    # Revision mode: this round extends an already-implemented version. Carries
    # this round's vision delta (added/modified/removed feature names + goal) and
    # the AI features already built, so Scout scopes to the changed surface and
    # does not re-surface existing AI features. ``None`` for a greenfield run.
    revision: dict[str, Any] | None = field(default=None)
    # Receipt-counter hook (D-PH9): called with each streamed text delta as it
    # arrives, so the orchestrator can publish liveness while the response is
    # drained internally. ``None`` drains silently (the prior behavior).
    on_chunk: Callable[[str], None] | None = field(default=None)


class ScoutOutcome(str, Enum):
    """Why Scout's candidate list came out the way it did.

    Distinguishes a genuine zero (a valid, empty candidate array) from a soft
    parse failure (no readable JSON array in the model's response). Both used to
    collapse to an empty list, which led the orchestrator to report an
    unreadable response as a deterministic-core vision.
    """

    OK = "ok"  # >= 1 candidate parsed
    EMPTY = "empty"  # valid JSON array, but no usable candidates (genuine zero)
    UNREADABLE = "unreadable"  # no valid JSON array could be parsed (soft failure)


@dataclass
class ScoutOutput:
    candidates: list[Candidate]
    outcome: ScoutOutcome = ScoutOutcome.OK


def _parse_candidates(raw: str) -> tuple[list[Candidate], ScoutOutcome]:
    """Extract and parse the JSON candidates array from the LLM response.

    Returns the parsed candidates together with a :class:`ScoutOutcome` that
    records why the list is empty when it is: ``EMPTY`` for a valid but empty
    array (a genuine zero), ``UNREADABLE`` when no JSON array could be parsed.
    """
    # Try the raw text first (LLM may return bare JSON without a fence).
    for attempt in (raw.strip(), _extract_json_array(raw)):
        if attempt is None:
            continue
        try:
            data = json.loads(attempt)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, list):
            continue
        results: list[Candidate] = []
        for item in data:
            if not isinstance(item, dict) or "name" not in item:
                continue
            results.append(
                Candidate(
                    name=str(item.get("name", "")),
                    linked_vision_features=list(item.get("linked_vision_features") or []),
                    scope=str(item.get("scope", "feature")),
                    rough_description=str(item.get("rough_description", "")),
                    linked_existing_workflow=str(item.get("linked_existing_workflow") or ""),
                )
            )
        # Scout surfaces nodes only; the Linker wires edges over the closed set
        # (composed_under / requires stay at their empty Candidate defaults here).
        return results, (ScoutOutcome.OK if results else ScoutOutcome.EMPTY)
    return [], ScoutOutcome.UNREADABLE


def _extract_json_array(text: str) -> str | None:
    """Return the first top-level JSON array found in text, or None."""
    match = re.search(r"\[.*\]", text, re.DOTALL)
    return match.group() if match else None


def _format_scout_revision_block(revision: dict[str, Any]) -> str:
    """Render the revision delta + already-built AI features for Scout's prompt.

    ``revision`` carries the vision delta (``added`` / ``modified`` / ``removed``
    ``key_features_mvp`` names and the revision ``goal``) and
    ``existing_ai_features`` (name + linked_vision_features of each already-built
    feature). Joined here as informing context — Scout uses it to scope to the
    changed surface, not as a brittle name-exact filter.
    """
    changes = revision.get("changes") or {}
    added = list(changes.get("added") or [])
    modified = list(changes.get("modified") or [])
    removed = list(changes.get("removed") or [])
    existing = revision.get("existing_ai_features") or []

    lines = ["\n\n--- REVISION MODE ---"]
    goal = revision.get("goal") or ""
    if goal:
        lines.append(f"Goal of this revision: {goal}")
    lines.append("\nThis revision's changes to the product (key_features_mvp):")
    lines.append(f"- Added: {', '.join(added) if added else '(none)'}")
    lines.append(f"- Modified: {', '.join(modified) if modified else '(none)'}")
    lines.append(f"- Removed: {', '.join(removed) if removed else '(none)'}")

    if existing:
        lines.append("\nAlready-built AI features (DONE — do not re-surface these):")
        for f in existing:
            name = f.get("name", "")
            linked = ", ".join(f.get("linked_vision_features") or [])
            suffix = f" (for: {linked})" if linked else ""
            lines.append(f"- {name}{suffix}")
    else:
        lines.append("\nAlready-built AI features: (none recorded)")

    lines.append(
        "\nSurface only the AI opportunities introduced by the added/modified "
        "features above. Do not re-surface an already-built feature."
    )
    return "\n".join(lines)


class ScoutAgent:
    """Request/response sub-agent that identifies AI opportunity candidates."""

    name = "scout"

    async def run(self, input: ScoutInput) -> ScoutOutput:  # noqa: A002
        validate_dataclass_input(input, ScoutInput)

        brownfield = input.code_review is not None
        revision = input.revision
        system_prompt = _build_scout_system_prompt(
            brownfield, revision is not None
        )

        vision_text = json.dumps(input.vision, indent=2)
        code_review_block = (
            f"\n\nCode review of existing project:\n```json\n"
            f"{json.dumps(input.code_review, indent=2)}\n```"
            if input.code_review
            else ""
        )
        revision_block = (
            _format_scout_revision_block(revision) if revision else ""
        )

        user_content = (
            f"Here is the project vision statement:\n\n```json\n{vision_text}\n```"
            f"{code_review_block}"
            f"{revision_block}"
            "\n\nIdentify all AI opportunity candidates."
        )

        llm_config = input.llm_config
        buf: list[str] = []
        for delta in complete_stream(
            llm_config=llm_config,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            agent_name="scout",
        ):
            buf.append(delta)
            if input.on_chunk is not None:
                input.on_chunk(delta)
        raw = "".join(buf).strip()
        candidates, outcome = _parse_candidates(raw)
        return ScoutOutput(candidates=candidates, outcome=outcome)