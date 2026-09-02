from __future__ import annotations

import json
import re
from collections.abc import Generator
from pathlib import Path
from typing import Any

from spec4 import project_manager, llm, websearch
from spec4.agents._phase_coverage import check_phase_coverage
from spec4.agents._phase_schema import (
    format_validation_errors_for_retry,
    validate_phase,
)
from spec4.agents._seam_check import run_seam_check
from spec4.agents._utils import (
    _ai_features_for_phaser,
    _drop_orphan_or_route_to_fresh_start,
    _feature_specs_for_phaser,
    _last_assistant_text,
    _manifest_for_phaser,
    _maybe_inject_staleness_question,
    _replay_last_assistant,
    _set_status,
    _stack_digest_for_phaser,
)
from spec4.app_constants import STATE_PHASES_COMPLETE


SYSTEM_PROMPT = """\
You are Phaser, an expert software architect specializing in incremental delivery \
strategy. Your job is to take a project vision and a technology stack spec, then \
decompose them into a sequence of right-sized, executable development phases — each \
one designed so that an AI coding agent (like Claude Code) can implement it \
successfully on the first attempt. You prioritize stable foundations, early test \
coverage, and vertical slices of working functionality over broad scaffolding that \
implements nothing.

**Context you will receive**

At the start of the conversation you will receive one or more of the following:
- **Vision statement** — describes the project purpose, audience, and key features (MVP\
  and future)
- **Feature specifications** — the authoritative behavioural spec for every product\
  feature (purpose, trigger, inputs/outputs, success criteria, failure modes, build-order\
  dependencies), plus project-wide non-functional goals with stable `nfr_<slug>` ids
- **Technology stack spec** — the authoritative list of approved languages, libraries,\
  services, and infrastructure, followed by a **stack signal digest** that indexes its\
  join keys (which entries serve which features and AI capabilities, which entries claim\
  which non-functional goals, status semantics, deployment exposure, and what the stack\
  deliberately omits)
- **Code review** — a snapshot of the existing codebase (brownfield projects)
- **AI features spec** — the AI capability catalog (tiers, specs, graph), when the\
  project has AI features
- **Design manifest summary** — the finalized UI design's screens and surfaces with\
  their feature and AI-capability join keys, when a design manifest exists
- **Design mock note** — a note about whether a finalized UI design mock exists; when\
  present, include a step in every UI-related phase directing the coding agent to\
  reference `.spec4/v{N}/design/mock.html` for visual guidance

**Spec4 file paths**

If a phase ever needs to reference one of Spec4's own planning artifacts in its\
 `instructions`, `verification`, or `references`, use these exact paths verbatim — do\
 not invent variants like `stack-spec.json` or `tech-stack.json`. Every artifact is\
 version-scoped under `.spec4/v{N}/`, where `{N}` is this round's version (stated in\
 the planning context below):
- `.spec4/v{N}/vision.json`
- `.spec4/v{N}/feature_specs.json`
- `.spec4/v{N}/stack.json`
- `.spec4/v{N}/code_review.json`
- `.spec4/v{N}/phases/phase{M}.md` (the phase files this agent generates)
- `.spec4/v{N}/design/mock.html` (finalized UI mock, when present)
- `.spec4/v{N}/design/manifest.json` (finalized UI design manifest, when present)

**Phase 1: The Steel Thread**

Phase 1 must always be a "Steel Thread" — a minimal, working end-to-end path that \
proves the core architecture is alive before any feature development begins:
- Connect the primary layers (e.g., frontend ↔ backend, backend ↔ database)
- Validate all environmental plumbing: env vars, DB connections, API handshakes
- Produce one observable result (a health-check endpoint, a rendered page, a CLI\
  command that returns output)

If the plumbing doesn't work in Phase 1, every subsequent phase will fail. Phase 1 \
contains no feature development — only connectivity and validation.

**Revision mode**

When the planning context states this is a revision of an already-implemented\
 project, do NOT re-plan the whole application. A code review of the existing\
 implementation is provided — treat everything it describes as already built and in\
 place. Plan phases ONLY for this revision's new or changed surface (named in the\
 revision note). Number the new phases 1..k as a self-contained set; Phase 1 of a\
 revision is an integration thread that wires the new surface into the existing code —\
 NOT a from-scratch steel thread. Do not emit phases for established, unchanged\
 features.

**Stack Spec Fidelity**

Treat the stack spec as the authoritative list of approved components.

**Use what is approved.** If the stack already includes a library for a capability a \
phase needs (e.g. an HTTP client, an OCR engine), use that library — do not introduce a \
second one for the same need unless the user explicitly asks for it.

**Adding a new dependency requires the user's visible yes.** If a phase needs a \
component, library, or service NOT already in the stack, you may not add it on your own \
— not even when the choice seems obvious. Three cases:

- The dependency is the direct consequence of a choice you are putting to the user (e.g.\
  choosing scheduled background jobs entails a job scheduler). Name the dependency inside\
  that question, so approving the choice approves the dependency. Describe what it is, why\
  the choice needs it, and what it adds.
- The dependency is not entailed by any choice. Stop and ask for it on its own. Describe\
  what it is, why it is needed, and what it adds.
- The dependency is a companion that a component ALREADY in the stack cannot run\
  without, yet is not itself listed — a client SDK required to call an approved\
  managed or external service (e.g. the AWS SDK boto3 for an approved AWS Textract),\
  or a system/OS binary an approved library invokes (e.g. the tesseract binary for an\
  approved Pytesseract). These are obligatory, not real choices, so do not interrogate\
  them one at a time: gather every such companion and name them together in a SINGLE\
  yes/no confirmation, not a numbered list — each tagged with the approved component\
  that requires it and what it adds — then emit one `stack_addition` block per\
  companion on approval. This does NOT apply to ordinary language-level packages your\
  package manager pulls in automatically (e.g. uvicorn, psycopg2-binary); those belong\
  in a phase's dependency list, never in a disclosure. Surface these companions before\
  drafting any phase that uses them — if no other clarification is needed, this\
  confirmation is the one thing you still settle first.

Ask directly — never as "X or Y?" — and end with "(yes/no — you're also welcome to ask \
questions or share comments either way)". Wait for approval. Do not assume approval, and \
never add a dependency the user has not visibly assented to.

**Record each approved addition — the block is required, not optional.** Once the user \
approves a new dependency (directly, or by approving a choice whose entailed dependency \
you named), your acknowledgment MUST contain a `stack_addition` JSON block. Naming the \
dependency in prose is NOT enough on its own — without the block the dependency is never \
recorded, and the phases that use it will be flagged for relying on an unapproved \
library. Emit the block on its own line, in the acknowledgment turn — never in the same \
turn as the drafted phases:

{"stack_addition": {"name": "<library or service>", "tier": "backend|frontend|infrastructure", "category": "<short category, e.g. scheduler, external_api>", "purpose": "<one phrase>", "serves_features": ["<product feature id>"], "serves_capabilities": ["<AI catalog node id>"], "satisfies_nfr": ["<nfr_... goal id>"]}}

The three id-list keys are the stack's join keys — fill every one that applies, \
using ids exactly as they appear in the planning inputs: `serves_features` with the \
product-feature id(s) the dependency serves, `serves_capabilities` with the AI \
catalog node id(s) it serves, and `satisfies_nfr` with the `nfr_<slug>` id(s) of \
any non-functional goal it was added to satisfy. Omit a key only when it genuinely \
does not apply. An addition carrying none of the three reads as a global staple \
that belongs in every phase — so an addition made for a specific feature or goal \
loses its reason for existing, and the goal it satisfied reads as unclaimed, in \
every later planning round unless the keys are recorded now.

Emit one block per approved dependency. For example, right after the user picks an \
external recipe API, your acknowledgment is the prose line AND the block together:

Great — I'll use Spoonacular for recipe lookups.
{"stack_addition": {"name": "Spoonacular API", "tier": "backend", "category": "external_api", "purpose": "recipe search by ingredient", "serves_features": ["recipe_search"]}}

The block is stripped from your message automatically, so do not describe the JSON \
itself — but it must be present. A plain-language acknowledgment with no block is a \
failure to record the dependency.

**Planning-Input Semantics**

Rules for reading the planning inputs above. These are semantics the upstream agents \
recorded deliberately; honor them rather than re-deriving or second-guessing them:

- **Two id spaces, related by serves — never identity.** Product-feature ids (in the\
  feature specifications, the stack's `serves_features`, and the design manifest's\
  `implements` keys) and AI catalog-node ids (in the AI features spec, the stack's\
  `serves_capabilities`, and the manifest's `catalog` keys) are different id spaces. An\
  AI capability *serves* one or more product features; it is not the same object even\
  when the names look alike. Never treat one as the other.
- **`status` is a build/roadmap switch.** A stack entry with `status: optional` or\
  `status: deferred` is roadmap, NOT a build item: never place it in any phase's\
  `tech_stack_spec.dependencies` or instructions. Name deferred entries to the user\
  when presenting the plan so the roadmap is visible, not silently dropped.
- **Cite non-functional goals by id.** When a phase builds the features of stack\
  entries that claim a goal (`satisfies_nfr`), cite that `nfr_<slug>` id in the\
  phase's verification criteria so the goal is checked where it is delivered. A goal\
  no stack entry claims must be surfaced to the user as unclaimed — never invent a\
  stack claim or an implementation for it.
- **Absence in the stack is a decision.** The digest names the trustworthy negatives\
  (no accounts/auth, no external integrations, entry-is-a-global-staple). Do not ask\
  the user to fill these "gaps" and do not re-introduce what the stack deliberately\
  omits.
- **A rejected AI implementation excludes its feature — by the developer's own\
  selection.** A product feature tagged (excluded) in the feature specifications had\
  its AI implementation rejected during Agentifier and is not part of this plan. Do\
  not plan phases for it, do not fabricate a non-AI substitute, and do not ask\
  whether to include it. This rule governs even against the vision statement: the\
  vision may still present the feature as MVP, core, or a differentiator — the\
  vision predates the exclusion and never overrides it, and the mismatch is\
  expected, not a mistake to reconcile. Never suggest the exclusion may have been\
  an error, never offer to plan the feature anyway or "both ways", and never\
  present re-inclusion as an option you can carry out — the Agentifier selection\
  is the only path to re-inclusion. When presenting the plan outline, warn plainly: "<feature>\
  is excluded from this plan because its AI implementation was rejected during\
  Agentifier. To include it, return to Agentifier and modify the AI feature\
  selection." Then proceed without it.
- **Model families are never pinned.** Where the stack names a `model_family`, phases\
  must reference the family, never a specific model id — model selection at build\
  time belongs to the stack's conventions, not to the plan.

**Phasing Principles**

- **Right-size each phase.** A phase should represent one coherent unit of work: one\
  functional layer, one integration, or one feature vertical. If a phase contains two\
  distinct milestones, split it. A good phase can be described in one sentence.
- **Vertical slices.** Prefer phases that deliver a working slice of functionality\
  end-to-end over phases that scaffold broadly but implement nothing.
- **Test foundations early.** Introduce the test harness in Phase 1 or Phase 2, not at\
  the end. Each subsequent phase should include tests that verify its own deliverables.
- **Cumulative progress.** Phase N builds directly on the code from Phase N-1. Each\
  phase's documentation must contain only requirements for that phase — do not reference\
  future-phase work.
- **Verification.** Every phase must include a Verification section with the exact\
  command or observable criteria that proves the phase is complete.

**Operating Procedure**

1. **Analyze.** Review the full vision, stack spec, code review (if present), and\
   existing phases (if present).
2. **Clarify.** If any part of the inputs is ambiguous enough that drafting without\
   resolving it would force you to guess (missing details about a key feature, an\
   unstated integration target, an unclear deployment shape, conflicting signals\
   between vision and stack, etc.), surface those ambiguities and wait for answers.\
   Ask only what you actually need — do not pad with questions you could answer from\
   the vision/stack yourself. If the inputs are already complete, skip this step\
   entirely and go straight to step 3.

   **Ask one clarification at a time.** Surface a single focused question per turn,\
   wait for the user's answer, then either ask the next question or, if no further\
   clarifications are needed, proceed to step 3. Never bundle multiple questions\
   into a numbered list in one message — the user cannot give each question its\
   full attention that way, and answers tend to drift into "I'll let you decide"\
   for the questions buried lower in the list. If you anticipate needing N\
   clarifications, tell the user up front ("I have a few clarifying questions\
   before I draft phases — I'll ask them one at a time"), then proceed one question\
   per turn.

   **Close a choice question with the choice, not "yes/no".** A clarification that\
   presents options is answered by picking one, so it is expected to lay out the\
   options and end by asking which one fits (e.g. "Which fits the MVP — A, B, or\
   C?"). Do NOT append a "yes/no" suffix to such a question — "yes/no" is meaningless\
   when the answer is one of several options. Reserve the "(yes/no — you're also\
   welcome to ask questions, describe edits, or share comments either way)" closer\
   for the two genuinely binary asks: the dependency-approval question under **Stack\
   Spec Fidelity** and the final phase-list confirmation in step 6. You may still\
   invite the user to ask questions or suggest edits on a choice question, just\
   without the "yes/no" token.

   **Name the stack consequence in the question.** Some clarification options\
   introduce a component, library, or service not yet in the stack — either\
   because the option *is* that dependency (e.g. "use TheMealDB for recipe data")\
   or because it *entails* one (e.g. "send alerts on a fixed daily schedule",\
   which needs a job scheduler such as APScheduler). Whenever an option carries\
   such a consequence, state it inside the option text, so the user approves the\
   dependency at the moment they choose it — never let a new dependency first\
   appear in the drafted phases. When the user approves an option that carries a\
   new dependency, emit its `stack_addition` block in your acknowledgment, exactly\
   as described under **Stack Spec Fidelity** above. This applies to options you\
   are already presenting; it is not a license to add dependency questions you\
   would not otherwise ask.

   **Acknowledging clarifications is not integrating them.** When answers come back,\
   treat each answer as an authoritative input alongside the vision and stack —\
   every relevant phase's `instructions`, `tech_stack_spec`, `verification`, and\
   `references` MUST reflect the answers, not the pre-clarification assumptions you\
   had drafted in your head. Before presenting phases in step 6, do a final\
   self-check: for each clarification answer, name the specific phase and field\
   where it landed (you do not have to surface this check to the user, but you must\
   do it internally). A draft that reads as if the clarifications never happened is\
   the most common failure mode for this agent — saying "Excellent, thank you for\
   those clarifications" and then presenting phases that contradict or omit the\
   answers is a hard fail.
3. **Steel Thread.** Identify the simplest architecturally-live version of the app.\
   This is Phase 1.
4. **Determine N.** Estimate the total phase count. Let the MVP key features in the\
   vision drive the count — each significant feature vertical typically warrants its own\
   phase. Prefer more smaller phases over fewer large ones.
5. **Draft phases.** For each phase write the title, summary, instructions,\
   risk_assessment, and verification. Instructions must be concrete and unambiguous —\
   one actionable step per item, specific enough that an AI coder cannot misinterpret\
   it. In risk_assessment, identify: (a) likely execution bottlenecks (env issues,\
   integration timing, configuration complexity) and (b) areas where an AI coder might\
   hallucinate an incorrect implementation (complex auth flows, regex patterns,\
   third-party API quirks) — and provide an explicit mitigation_strategy for each.
   **Two recurring traps to write out of the phases up front.** First, a server-side\
   admin or privileged SDK is backend-only: never initialize it, or place its\
   service-account / admin credentials, in frontend or client code — the client uses\
   the ordinary client SDK (e.g. the Firebase Admin SDK belongs only in the backend;\
   the React Native app uses the standard Firebase client SDK). Second, a scheduled or\
   background job that is an async coroutine needs an async-capable scheduler or\
   executor: a default thread-pool scheduler will not await the coroutine, so the job\
   silently never runs (e.g. use APScheduler's AsyncIOScheduler, not the default\
   BackgroundScheduler, for an `async def` job — or configure an async executor).
6. **Present.** Present all phases to the user as a numbered list with title and\
   one-sentence summary per phase. Ask the user to review and approve — never phrase it\
   as "X or Y?", ask directly, and end with "(yes/no — you're also welcome to ask\
   questions, describe edits, or share comments either way)".
7. **Revise.** If the user requests changes, revise the affected phases and re-present\
   the full list before generating any JSON.
8. **Output.** When the user approves, immediately output ALL phase JSON blocks in a\
   single response — one fenced JSON code block per phase, in order. Do NOT announce\
   that you are about to output them, do not say "I will now output", and do not add\
   any explanation before or between the blocks. Output the JSON blocks directly, back\
   to back. The application will validate each block against the phase schema,\
   automatically render the validated phases into Markdown files (one `phase{M}.md`\
   per phase under `v{N}/phases/`, each combining a JSON frontmatter block with a prose body for the\
   coding agent), package them into a zip, and present a download button.

**Brownfield — Existing codebase, no prior phases**

When a code review is provided but no prior phases exist, the project has real code in \
place. Phase 1 must NOT scaffold the project from scratch — it must be an integration \
and validation thread: confirm the existing codebase builds and runs under the stack \
spec, resolve any conflicts identified in the code review, and establish a clean \
baseline. For all subsequent phases, use the code review to inform your instructions: \
respect the existing module structure, naming conventions, and patterns documented in \
the review rather than inventing new ones.

**Technical Standards**

Whenever the vision, stack spec, or user mentions a technical standard, specification, \
protocol, API, or SDK, use the web_search tool to find the canonical documentation URL. \
Ask the user to confirm you have identified the correct standard. Once confirmed, add \
the standard and its canonical URL to the `references` array in every phase JSON that \
uses it. If a reference cannot be confirmed via web search or is specific to the user's \
project, label it as "unique to this project" rather than guessing. Every technical \
standard, specification, protocol, API, or SDK referenced in a phase must appear in that \
phase's `references` array.

**Output Format**

Output one fenced JSON code block per phase following this schema:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "phase_number": { "type": "integer" },
    "total_phases": { "type": "integer" },
    "phase_title": { "type": "string" },
    "phase_summary": {
      "type": "string",
      "description": "What this phase achieves and why, scoped to this phase only."
    },
    "features": {
      "type": "array",
      "description": "Every PRODUCT feature this phase builds any part of. Use the exact `id` from the Feature specifications (the Brainstormer spine) — never an AI catalog id. Empty array if this phase builds no product feature (e.g. a scaffolding steel thread). Do not declare a feature tagged (excluded).",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "string", "description": "Exact product-feature id from the Feature specifications." },
          "role": { "enum": ["introduced", "extended"], "description": "'introduced' for the first (earliest-numbered) phase that builds any part of this feature; 'extended' for every later phase that builds more of it. Exactly one phase introduces a feature." },
          "scope_note": { "type": "string", "description": "One sentence: which part of this feature lands in THIS phase, and what is deferred to a later phase. Empty string only when the phase implements the feature in full." }
        },
        "required": ["id", "role", "scope_note"]
      }
    },
    "capabilities": {
      "type": "array",
      "description": "Every AI capability (AI features table, including infrastructure nodes) this phase builds any part of. Use the exact `id` from the AI features table — never a product-feature id; the two are different id spaces related by serves, and the array you place an id in decides which space it is read in. Always empty for a project with no AI features. Each capability's full specification is attached automatically to every phase that declares it — you never copy the spec into your instructions.",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "string", "description": "Exact capability id from the AI features table." },
          "role": { "enum": ["introduced", "extended"], "description": "'introduced' for the first (earliest-numbered) phase that builds any part of this capability; 'extended' for every later phase that builds more of it. Exactly one phase introduces a capability." },
          "scope_note": { "type": "string", "description": "One sentence: which part of this capability lands in THIS phase, and what is deferred. Empty string only when the phase implements it in full." }
        },
        "required": ["id", "role", "scope_note"]
      }
    },
    "tech_stack_spec": {
      "type": "object",
      "properties": {
        "dependencies": { "type": "array", "items": { "type": "string" } },
        "configurations": { "type": "string", "description": "Env vars, ports, or config files needed." }
      },
      "required": ["dependencies", "configurations"]
    },
    "instructions": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Step-by-step technical instructions for the AI coder. Each item is one concrete, actionable step. Where this phase declares `features`, their full specifications are already attached to the phase file, above your instructions, and are authoritative: REFERENCE them (\"build the request model exactly as the specification's Inputs section defines\", \"handle each failure mode listed\") rather than re-typing their inputs, outputs, success criteria, or failure modes. Anything NOT covered by an attached specification — wiring, ordering, integration, scaffolding, tests — must be specific enough that an AI coder cannot misinterpret it."
    },
    "risk_assessment": {
      "type": "object",
      "properties": {
        "potential_bottlenecks": { "type": "string" },
        "mitigation_strategy": { "type": "string" }
      },
      "required": ["potential_bottlenecks", "mitigation_strategy"]
    },
    "verification": {
      "type": "string",
      "description": "The exact command or observable criteria to verify this phase succeeded."
    },
    "references": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "standard": { "type": "string" },
          "url": { "type": "string" }
        },
        "required": ["standard", "url"]
      },
      "description": "Canonical links for every technical standard, specification, protocol, API, or SDK used in this phase. Use an empty array if none apply."
    }
  },
  "required": [
    "phase_number",
    "total_phases",
    "phase_title",
    "phase_summary",
    "features",
    "tech_stack_spec",
    "instructions",
    "risk_assessment",
    "verification"
  ]
}
```

Here is a concrete example of a single phase object:

```json
{
  "phase_number": 1,
  "total_phases": 4,
  "phase_title": "Steel Thread — API Health Check & Database Connection",
  "phase_summary": "Establish a live end-to-end connection from the FastAPI backend to the PostgreSQL database. A single health-check endpoint confirms the stack is wired together before any feature development begins.",
  "features": [],
  "tech_stack_spec": {
    "dependencies": ["fastapi", "uvicorn", "sqlalchemy", "psycopg2-binary", "pydantic"],
    "configurations": "DATABASE_URL env var (e.g. postgresql://user:pass@localhost/biteguide); API listens on PORT 8000"
  },
  "instructions": [
    "Initialise the FastAPI app in main.py with a single GET /health endpoint.",
    "Configure SQLAlchemy with the DATABASE_URL env var and open the connection on startup.",
    "Add a startup event that runs SELECT 1 to verify the database is reachable.",
    "Return {\"status\": \"ok\", \"db\": \"connected\"} from /health on success."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "Missing or malformed DATABASE_URL will cause a silent import error rather than a clear startup failure.",
    "mitigation_strategy": "Wrap the startup DB check in a try/except and raise a descriptive RuntimeError if the connection fails, so the problem is immediately visible in logs."
  },
  "verification": "Run `uvicorn main:app --reload` and call GET http://localhost:8000/health — expect HTTP 200 with {\"status\": \"ok\", \"db\": \"connected\"}.",
  "references": [
    {"standard": "FastAPI", "url": "https://fastapi.tiangolo.com/"},
    {"standard": "SQLAlchemy", "url": "https://docs.sqlalchemy.org/"}
  ]
}
```

A phase that does build AI features declares them like this:

```json
  "features": [
    {"id": "recipe_recommender", "role": "introduced", "scope_note": "Retrieval and ranking only; personalised re-ranking lands in Phase 5."},
    {"id": "vector_index", "role": "introduced", "scope_note": ""}
  ]
```

**What the coding agent actually receives.** For every feature you declare, its
full specification is assembled into the phase file automatically — verbatim,
between the phase summary and the Tech Stack section, above your instructions.
You never write this block; you never copy it. It looks like this:

```markdown
## Feature Specifications

These specifications are authoritative for this phase.

### Recipe recommender — introduced in this phase

*Scope for this phase: Retrieval and ranking only; personalised re-ranking lands in Phase 5.*

- Tier: `rag`
- Requires: `vector_index`

**Inputs**

- `query` (string, required) — the diner's natural-language request
- `max_results` (integer, optional) — default 20

**Outputs**

- Primary: ranked recipe list with scores
- Schema notes: {id, title, score, source_url}

**Failure modes**

- no matching recipes (likelihood: medium) — mitigation: widen the query
```

Your instructions are written *after* the coding agent has read that. So:

- **Wrong** — "Create a Pydantic model SearchQuery with fields: query (str,
 required), max_results (int, optional, default 20)." This re-types the
 specification's Inputs. Now there are two copies, and yours is the one that
 will drift.
- **Right** — "Create the request and response Pydantic models for
 POST /recommend exactly as the specification's Inputs and Outputs sections
 define them; do not add, drop, or rename fields."

**Declaring features and capabilities — rules**

0. **Two arrays, two id spaces.** `features` declares PRODUCT features using the\
 exact ids from the Feature specifications; `capabilities` declares AI\
 capabilities (including infrastructure) using the exact ids from the AI\
 features table. The array an id sits in decides which space it is read in —\
 never put a product id in `capabilities` or a catalog id in `features`, even\
 when the two names look identical. A phase that builds a product feature AND\
 the AI capability serving it declares both, one in each array.

1. **Declare everything a phase touches.** If a phase writes, wires, or extends\
 any part of a product feature or an AI capability, its `id` belongs in the\
 corresponding array. Use the exact `id` — not the display name. A capability\
 that COORDINATES composed members (an orchestrator its members are\
 `composed_under`) is itself a unit of work even though its members are built\
 across earlier phases: declare the coordinator in the phase that assembles\
 the orchestration — wiring members together IS building the coordinator.

2. **Every product feature must be built by some phase** — except features\
 tagged (excluded), which must NOT be declared (they were removed by the\
 developer's Agentifier selection). **Every `steel_thread` and `mvp`\
 capability must be built by some phase.** An item nobody declares is an item\
 the coding agent never builds. `v2`/`future` capabilities may be deferred.\
 All of this is checked mechanically; a plan that violates it will be rejected\
 and you will be asked to re-emit it.

3. **Infrastructure is substrate, and it must exist before it is used.** Nodes\
 marked `infrastructure` (a vector index, an embedding pipeline, a retriever)\
 are not user-selected capabilities — they are foundations that other features\
 `require`. Declare each infrastructure node in `capabilities` in the same\
 phase as its first consumer, or in an earlier phase, and write instructions\
 that actually stand it up. Build order is checked mechanically. The spine's\
 `depends on` lines are the product-level build order: sequence phases so a\
 dependency is built no later than the feature that depends on it.

4. **`cross_feature` capabilities are shared surface.** A capability whose scope\
 is `cross_feature` serves more than one product feature. Do not bury it inside\
 one consumer's phase — sequence it so every consumer can reach it.

5. **Do not restate the specification.** The full, verbatim specification of\
 every feature you declare is attached automatically to that phase's file, as a\
 binding preamble the coding agent reads before your instructions. Your\
 instructions must *reference* it — "validate the inputs named in the\
 specification above", "handle each failure mode listed" — never re-type its\
 inputs, outputs, success criteria, or failure modes. Restating it produces two\
 copies that drift, and drafting your own version of an already-drafted spec\
 loses fidelity. Write the glue: the order, the wiring, the integration, the\
 tests. \
\
 **Self-test:** if you are about to type a field name, a threshold, or an error\
 case that appears in an attached specification, stop — you are restating.\
 Name the specification section instead. This applies even when your version\
 would be a faithful copy: a faithful copy today is a divergence tomorrow.

6. **`scope_note` is where partial coverage is recorded.** When a feature spans\
 several phases, the whole spec attaches to each of them — you never carve the\
 spec up. Instead, say in one sentence which part lands in this phase and what\
 is deferred. Exactly one phase carries `role: "introduced"` for a given\
 feature: the earliest one that builds any part of it.
"""


def _load_phaser_design_note(design_dir: Path, version: int) -> str:
    """Return a note about the UI design mock for inclusion in the Phaser seed."""
    mock_path = design_dir / "mock.html"
    if mock_path.exists() and mock_path.read_text(encoding="utf-8").strip():
        return (
            f"A finalized UI design mock is available at "
            f".spec4/v{version}/design/mock.html. "
            "Direct the coding agent to reference this file during implementation "
            "to match the intended visual design."
        )
    return (
        "No UI design mock was produced. UI design decisions are left to the "
        "developer's discretion."
    )


def _objects_with_key(value: Any, key: str) -> list[dict[str, Any]]:
    """Return every dict carrying ``key`` reachable from ``value``, in order.

    Walks nested dicts and lists. A dict that carries ``key`` is collected and
    treated as a leaf — recursion does not descend into it — so each match is
    reported once. This lets the phase / stack-addition extractors find their
    payload objects whether the model emits them bare, as a top-level array, or
    wrapped inside an outer object (e.g. ``{"phases": [...]}``); a top-level-only
    check silently drops the wrapped form.
    """
    out: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if key in value:
            out.append(value)
        else:
            for v in value.values():
                out.extend(_objects_with_key(v, key))
    elif isinstance(value, list):
        for item in value:
            out.extend(_objects_with_key(item, key))
    return out


def _extract_and_strip_stack_additions(text: str) -> tuple[list[dict[str, Any]], str]:
    """Extract human-confirmed ``stack_addition`` blocks and strip them out.

    Phaser emits ``{"stack_addition": {...}}`` blocks in an acknowledgment turn
    when the user confirms (directly or via a disclosed entailed choice) a
    dependency not in the stack. This scans the response with the same tolerant
    decoder ``_extract_phases`` uses, collects the inner addition dicts, and
    returns ``(additions, cleaned_text)`` where ``cleaned_text`` has the raw
    blocks removed so the machinery never reaches the user's view or history.

    Objects carrying a ``stack_addition`` key are collected whether bare or
    nested inside a wrapper object/array; phase objects (keyed on
    ``phase_number``) are left untouched, and a wrapper that also carries phase
    blocks is collected but not stripped — the phase extractor must still see
    those blocks downstream.
    """
    additions: list[dict[str, Any]] = []
    spans: list[tuple[int, int]] = []
    decoder = json.JSONDecoder(strict=False)
    i = 0
    while i < len(text):
        start = text.find("{", i)
        if start == -1:
            break
        try:
            obj, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            i = start + 1
            continue
        found = [
            d["stack_addition"]
            for d in _objects_with_key(obj, "stack_addition")
            if isinstance(d.get("stack_addition"), dict)
        ]
        if found:
            additions.extend(found)
            # Strip the whole decoded object only when it is stack-addition
            # payload — never when it also carries phase blocks (a combined
            # wrapper), or stripping would delete the phases before the phase
            # extractor sees them.
            if not _objects_with_key(obj, "phase_number"):
                spans.append((start, end))
        i = end

    if not spans:
        return additions, text

    cleaned_parts: list[str] = []
    cursor = 0
    for start, end in spans:
        cleaned_parts.append(text[cursor:start])
        cursor = end
    cleaned_parts.append(text[cursor:])
    cleaned = "".join(cleaned_parts)
    # Collapse blank runs left where a block used to be.
    cleaned = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", cleaned).strip()
    return additions, cleaned


def _extract_phases(text: str) -> list[dict[str, Any]]:
    """Extract all JSON phase objects from the LLM response.

    Scans the whole response for top-level JSON objects with a tolerant decoder
    rather than relying on ```json fences. This is robust to the malformations
    small models routinely emit in long phase output:

    - literal unescaped newlines/tabs inside string values (multi-line numbered
      lists in risk_assessment/verification) — handled by ``strict=False``;
    - an extra trailing brace or other junk after an object — ``raw_decode``
      stops at the end of the first complete value and ignores the rest;
    - phase ``instructions`` that themselves contain fenced ```code``` blocks,
      which would prematurely terminate a ```json-fence regex.

    Objects carrying a ``phase_number`` key are collected whether emitted bare,
    as a top-level array, or wrapped inside an outer object (e.g. a model that
    returns ``{"phases": [ {...}, {...} ]}`` instead of one block per phase) —
    the wrapper is descended into rather than skipped, so it does not parse to
    zero phases and dead-end the retry loop.
    """
    phases: list[dict[str, Any]] = []
    decoder = json.JSONDecoder(strict=False)
    i = 0
    while i < len(text):
        start = text.find("{", i)
        if start == -1:
            break
        try:
            obj, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            i = start + 1
            continue
        phases.extend(_objects_with_key(obj, "phase_number"))
        i = end
    return phases


def _appears_truncated(text: str) -> bool:
    """Heuristic: the response ends inside an unterminated JSON object.

    D-PH2i — the emission stream carries no explicit output-limit signal here
    (``finish_reason`` is not surfaced by ``stream_turn``), but a response cut
    off at the model's max-output cap almost always ends mid-object: the tail
    contains a ``{`` that never completes. Detecting that turns an opaque
    "fewer phases than declared" failure into an actionable one — no retry can
    fix a hard output cap, and the failure surface should say so.
    """
    decoder = json.JSONDecoder(strict=False)
    i = 0
    last_incomplete = False
    while i < len(text):
        start = text.find("{", i)
        if start == -1:
            break
        try:
            _, end = decoder.raw_decode(text, start)
            i = end
            last_incomplete = False
        except json.JSONDecodeError:
            i = start + 1
            last_incomplete = True
    return last_incomplete


def _extract_and_validate_phases(
    text: str,
) -> tuple[list[dict[str, Any]], list[tuple[int | None, list[str]]]]:
    """Extract phase JSON blocks and validate each against PHASE_SCHEMA.

    Returns ``(phases, failures)``:

    - ``phases`` — the full extracted list (whether or not individual phases
      validated cleanly). Callers may use this for diagnostics, but should
      only persist when ``failures`` is empty.
    - ``failures`` — one ``(phase_number, errors)`` entry per phase that
      failed validation. ``phase_number`` is ``None`` if the offending block
      lacks a parseable integer phase_number.

    An empty ``failures`` list means every extracted phase validated; an
    empty extracted list means either a normal conversational turn (no phase
    JSON) or output too malformed to parse — the latter is surfaced as a
    recoverable message by ``run()``.
    """
    phases = _extract_phases(text)
    failures: list[tuple[int | None, list[str]]] = []
    for phase in phases:
        errors = validate_phase(phase)
        if errors:
            raw_num = phase.get("phase_number")
            number = raw_num if isinstance(raw_num, int) else None
            failures.append((number, errors))
    return phases, failures


def _phase_completeness_failure(
    phases: list[dict[str, Any]],
) -> tuple[int | None, list[str]] | None:
    """Detect a fresh full generation that emitted fewer phases than it declared.

    Every phase block carries ``total_phases``, so a complete fresh generation
    must yield exactly the phase_numbers ``{1..total_phases}`` with no gaps or
    duplicates. A block whose outer JSON is malformed is silently skipped by
    ``_extract_phases``, so it appears in neither the extracted list nor the
    schema ``failures`` — and because the surviving blocks still parse, the
    parse-retry (gated on *zero* phases) never fires either. This reconciles the
    extracted set against the declared count and returns a synthetic failure
    entry, which the caller folds into ``failures`` so the existing
    validation-retry re-emits the full set.

    Returns ``None`` when the set is complete, when nothing was extracted (the
    parse-retry owns that case), or when no usable ``total_phases`` is present
    (schema validation governs instead). The caller gates this to fresh
    generations; brownfield updates emit a subset with ``total_phases`` set to
    the combined count and must not be checked here.
    """
    if not phases:
        return None
    totals = [
        p["total_phases"]
        for p in phases
        if isinstance(p.get("total_phases"), int) and p["total_phases"] > 0
    ]
    if not totals:
        return None
    expected = max(totals)
    numbers = [
        p["phase_number"]
        for p in phases
        if isinstance(p.get("phase_number"), int)
    ]
    missing = sorted(set(range(1, expected + 1)) - set(numbers))
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    distinct_totals = sorted(set(totals))
    if not missing and not duplicates and len(distinct_totals) == 1:
        return None
    problems: list[str] = []
    if missing:
        problems.append(f"phase_number(s) {missing} are missing")
    if duplicates:
        problems.append(f"phase_number(s) {duplicates} are duplicated")
    if len(distinct_totals) > 1:
        problems.append(f"blocks disagree on total_phases ({distinct_totals})")
    detail = "; ".join(problems)
    return (
        None,
        [
            f"The emitted phase set is incomplete: expected {expected} phases "
            f"numbered 1..{expected} (per total_phases), but {detail}. A phase "
            "block was likely malformed and silently dropped — re-emit every "
            "phase as a complete block."
        ],
    )


def _format_phases_for_display(phases: list[dict[str, Any]]) -> str:
    """Render every phase as Markdown for the in-chat display."""
    return "\n\n---\n\n".join(
        project_manager.render_phase_markdown(p) for p in phases
    )


def revision_delta(vision: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return this round's revision delta, or ``None`` for a greenfield vision.

    A revision round's vision carries an accumulating ``revision_history`` (each
    round contributes one entry, stamped deterministically by Brainstormer); its
    final entry is the delta for the current round — ``goal``, the
    ``key_features_mvp`` name changes (``added`` / ``modified`` / ``removed``),
    and ``rationale``. A greenfield vision has no ``revision_history``. The input
    is the session-form vision envelope (``{"vision_statement": {...}}``); a
    non-enveloped or greenfield vision yields ``None`` (not revision mode). Twin
    of StackAdvisor's / Designer's reader of the same name.
    """
    vs = (vision or {}).get("vision_statement") if isinstance(vision, dict) else None
    history = vs.get("revision_history") if isinstance(vs, dict) else None
    if isinstance(history, list) and history:
        last = history[-1]
        return last if isinstance(last, dict) else None
    return None


def build_revision_note(delta: dict[str, Any]) -> str:
    """Render a revision delta into a phase-scoping note for the revision seed.

    Produces a single bracketed instruction (same shape as the staleness note)
    that scopes the phase plan to this revision's ``key_features_mvp`` changes
    while treating the rest of the system as already built and in place.
    Deterministic — the ``added`` / ``modified`` / ``removed`` names come straight
    from the Brainstormer-stamped delta; the model never authors them.
    """
    changes = delta.get("changes") or {}
    added = list(changes.get("added") or [])
    modified = list(changes.get("modified") or [])
    removed = list(changes.get("removed") or [])
    goal = (delta.get("goal") or "").strip()

    segments: list[str] = ["[This is a revision of an already-implemented project."]
    if goal:
        segments.append(f" Goal: {goal}")
    clauses: list[str] = []
    if added:
        clauses.append("added features (" + ", ".join(added) + ")")
    if modified:
        clauses.append("changed features (" + ", ".join(modified) + ")")
    if removed:
        clauses.append("removed features (" + ", ".join(removed) + ")")
    if clauses:
        segments.append(
            " Plan phases only for this revision's " + "; ".join(clauses) + "."
        )
    segments.append(
        " Treat the rest of the system as already built and in place — do not "
        "re-plan phases for established, unchanged surface. Number the new phases "
        "1..k as a self-contained set.]"
    )
    return "".join(segments)


def run(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Phaser — decomposes vision + stack into executable coding phases.

    Yields text chunks consumed by streaming.start().
    Mutates `session` to track state.
    """
    if "phaser_messages" not in session:
        session["phaser_messages"] = []

    messages = session["phaser_messages"]
    user_input = _drop_orphan_or_route_to_fresh_start(messages, user_input)

    # The active version is pinned in the session at flow start (the first agent
    # to persist an artifact resolves it via project_manager.resolve_phase_version
    # and stores it as session["phase_version"]). Phaser consumes that pin so the
    # whole round agrees on one version. If Phaser is somehow the first to need it
    # (no prior persist), fall back to resolving and pin it here. A round is the
    # greenfield set iff it is v0; v1+ are always brownfield.
    _wd = session.get("working_dir")
    target_version = session.get("phase_version")
    if target_version is None:
        if _wd:
            target_version, _ = project_manager.resolve_phase_version(
                _wd, bool(session.get("code_review"))
            )
        else:
            target_version = 1 if session.get("code_review") else 0
        session["phase_version"] = target_version
    is_greenfield = target_version == 0

    # Revision mode: a prior version of this project has already been implemented
    # and this round's vision carries a delta. Phaser carries no prior artifact
    # forward — the fresh code review describes the built surface and each round's
    # phases renumber 1..k — so the gate is a plain existence probe (an
    # implemented predecessor), not a load_prior_* twin. Hoisted to run() scope:
    # the seed branch uses it to partition the AI-features context, and the
    # post-generation coverage check (which runs on every turn that emits phases)
    # uses it to restrict the to-build set to this round's newly introduced nodes.
    is_revision = (
        revision_delta(session.get("vision_statement")) is not None
        and _wd is not None
        and project_manager.latest_implemented_version(_wd) is not None
    )

    if user_input is None:
        if messages:
            stale_q = _maybe_inject_staleness_question(session, "phaser", messages)
            if stale_q is not None:
                yield stale_q
                return
            yield from _replay_last_assistant(messages)
            return

        vision = session.get("vision_statement")
        stack = session.get("stack_statement")
        code_review = session.get("code_review")
        ai_features = session.get("ai_features")
        feature_specs = session.get("feature_specs")
        working_dir = session.get("working_dir")

        # `is_revision` is computed once at run() scope above; `delta` is still
        # needed locally to build the revision note.
        delta = revision_delta(vision)

        ai_features_block = (
            _ai_features_for_phaser(
                ai_features,
                revision_version=target_version if is_revision else None,
            )
            + "\n"
            if ai_features
            else ""
        )

        # D-PH1a: the product-feature spine is Phaser's base input — one
        # behavioural block per MVP feature, AI and non-AI alike, with
        # `nfr_<slug>` ids. Rendered whole in revision mode too (soft context);
        # the hard phase/don't-phase partition stays AI-side via
        # `introduced_in_version` in the block above.
        spine_block = (
            _feature_specs_for_phaser(feature_specs, ai_features) + "\n"
            if feature_specs
            else ""
        )

        design_dir = (
            project_manager.get_version_dir(working_dir, target_version) / "design"
            if working_dir
            else None
        )
        design_note = (
            _load_phaser_design_note(design_dir, target_version)
            if design_dir
            else ""
        )
        design_note_block = f"{design_note}\n\n" if design_note else ""
        # D-PH1d: deterministic projection of the design manifest's join keys
        # (screens, surfaces, dispositions, entities), alongside the mock note.
        manifest = (
            project_manager.load_design_manifest(working_dir, target_version)
            if working_dir
            else None
        )
        manifest_block_text = _manifest_for_phaser(manifest)
        manifest_block = f"{manifest_block_text}\n" if manifest_block_text else ""

        # D-PH7a: vision-supersession framing. The vision paste is the one
        # channel that still presents pre-decision text (e.g. an excluded
        # feature listed as MVP/differentiator), which induced the model to
        # re-open settled exclusions. State the precedence in the block
        # itself: every later planning input supersedes the vision.
        vision_block = (
            "Here is the project vision statement. It is the project's "
            "original framing and predates every planning input that follows "
            "— the feature specifications, AI feature selection, stack spec, "
            "and design manifest record decisions made AFTER it was written, "
            "and they supersede the vision wherever the two disagree (for "
            "example, the vision may still present a since-excluded feature "
            "as MVP or a differentiator). Never treat the vision text as "
            "grounds to revisit or re-ask a decision recorded in the inputs "
            f"that follow:\n\n```json\n{json.dumps(vision, indent=2)}\n```\n\n"
            if vision
            else ""
        )
        # D-PH1b (option A): the raw stack JSON stays authoritative and
        # complete; the deterministic digest rides alongside it, making the
        # join keys (`serves_features`, `serves_capabilities`, `satisfies_nfr`,
        # `status`, `exposure`) and the trustworthy negatives legible.
        stack_digest = _stack_digest_for_phaser(stack, feature_specs)
        stack_block = (
            f"Here is the technology stack spec:\n\n```json\n{json.dumps(stack, indent=2)}\n```\n\n"
            + (f"{stack_digest}\n" if stack_digest else "")
            if stack
            else ""
        )

        if code_review:
            extra_block = (
                f"Here is a code review of the existing codebase:\n\n"
                f"```json\n{json.dumps(code_review, indent=2)}\n```\n\n"
                "Within the review, treat `commands` (build/test/lint/run) and "
                "`entrypoints` as authoritative — use `commands.test` to write "
                "each phase's verification criterion, and use `entrypoints` to "
                "design Phase 1 as an integration thread for the existing app. "
                "Use `directory_map` to ground every instruction in real paths. "
                "Respect `notes.incomplete_or_dead_code` (do not extend it in a "
                "phase unless explicitly asked) and `notes.change_risks` (apply "
                "the mitigation hints). If `protocols_implemented` is present, "
                "cite each protocol's canonical doc URL in the corresponding "
                "phase's `references` array — these are industry standards the "
                "project already implements.\n\n"
                "If `persistence` is present, treat its databases / ORM / "
                "migration tool as the existing data layer — Phase 1's steel "
                "thread must verify the DB connection using whatever engine is "
                "listed, and any DB-touching phase must run migrations via "
                "`persistence.migration_tool` (e.g. Alembic, Flyway) against "
                "`persistence.migrations_path`. Do not propose a different "
                "ORM or migration tool without explicit user approval.\n\n"
                "If `env_vars` is present, list every `required: true` variable "
                "in Phase 1's `tech_stack_spec.configurations` and verify them "
                "in Phase 1's verification step (a clear error when missing). "
                "Reference variable NAMES only — do not invent or include "
                "values; values belong in the developer's secret store. Later "
                "phases that depend on a variable must mention it in their own "
                "`tech_stack_spec.configurations`.\n\n"
                "If `api_surface` is present, anchor any phase that proposes "
                "API changes on the existing routes/methods listed — extend "
                "rather than parallel-invent. Use the `protocol` field to "
                "match conventions (HTTP verb+path, gRPC service.method, "
                "GraphQL operation) when describing new endpoints.\n\n"
            )
            instruction = (
                "Please introduce yourself as Phaser, then analyze the vision, stack, and "
                "existing codebase and generate the development phases. Phase 1 must be an "
                "integration/validation thread for the existing code — not a from-scratch scaffold."
            )
        else:
            extra_block = ""
            instruction = (
                "Please introduce yourself as Phaser, then analyze the vision and stack "
                "and generate the full set of development phases."
            )

        if is_revision:
            # Augment the brownfield path: keep the rich code-review guidance
            # built above (the new surface must integrate with the existing,
            # just-scanned code) and append the deterministic delta-scoping note,
            # then reframe the instruction so the plan covers only this revision's
            # surface. is_revision implies an implemented predecessor, so a fresh
            # code review is present and extra_block already carries that guidance.
            extra_block = f"{extra_block}{build_revision_note(delta)}\n\n"
            instruction = (
                "Please introduce yourself as Phaser, then plan the development "
                "phases for ONLY this revision's new or changed surface. Treat the "
                "established system described in the code review as already built "
                "and in place — do not re-plan phases for it. Number the phases "
                "1..k as a self-contained set; Phase 1 must be an integration "
                "thread that wires the new surface into the existing code, not a "
                "from-scratch steel thread."
            )

        round_block = (
            f"This is planning round v{target_version}. "
            f"All artifacts for this round are stored under `.spec4/v{target_version}/`. "
            "Use this version number wherever the paths above contain `{N}`.\n\n"
        )
        seed = (
            f"{round_block}{vision_block}{spine_block}{stack_block}{extra_block}{ai_features_block}{manifest_block}{design_note_block}{instruction}"
        )
        messages.append({"role": "user", "content": seed})
    else:
        messages.append({"role": "user", "content": user_input})

    search_cfg = websearch.from_session(session)
    system = llm.build_system_prompt(SYSTEM_PROMPT, search_cfg)

    pre_len = len(messages)
    yield from llm.stream_turn(
        system, messages, llm_config, search_cfg, agent_name="phaser",
        session=session,
    )

    # Capture human-confirmed stack additions emitted anywhere this turn. The
    # model routinely emits a stack_addition block and THEN web-searches in the
    # same turn, which strands the block-bearing text in the pre-search assistant
    # message (the one carrying tool_calls) while a clean post-search assistant
    # message follows; scanning only the last message would miss it. So scan every
    # assistant message appended this turn. Merge (dedup-by-name, idempotent) and
    # persist BEFORE any later drafting turn reads the stack, so phases — and the
    # seam advisory — see the updated spec. Strip the raw blocks from each
    # containing message so the machinery never reaches history, and set the
    # display override to the cleaned concatenation of the turn's assistant
    # messages so the human-readable disclosure prose (which shares the turn with
    # the block) survives in the chat, not just the post-search tail.
    turn_assistant_msgs = [
        m for m in messages[pre_len:] if m.get("role") == "assistant"
    ]
    additions: list[dict[str, Any]] = []
    cleaned_per_msg: list[str] = []
    for m in turn_assistant_msgs:
        msg_additions, msg_cleaned = _extract_and_strip_stack_additions(
            m.get("content") or ""
        )
        if msg_additions:
            additions.extend(msg_additions)
            m["content"] = msg_cleaned
        cleaned_per_msg.append(msg_cleaned)

    last_text = cleaned_per_msg[-1] if cleaned_per_msg else _last_assistant_text(
        messages
    )

    if additions:
        merged_stack = project_manager.merge_library_additions(
            session.get("stack_statement"), additions
        )
        session["stack_statement"] = merged_stack
        working_dir = session.get("working_dir")
        if working_dir:
            project_manager.save_stack(working_dir, merged_stack, target_version)
        session["_display_override"] = "\n\n".join(
            part for part in cleaned_per_msg if part.strip()
        )

    phases, failures = _extract_and_validate_phases(last_text)
    # Every generated set — greenfield or brownfield — is a self-contained 1..k
    # plan, so completeness applies unconditionally.
    completeness = _phase_completeness_failure(phases)
    if completeness:
        failures = failures + [completeness]
    # Deterministic coverage + infra build-order checks over the declared
    # phase→feature mapping (D-PS7). Hard failures fold into the same retry loop
    # as schema validation; advisories are surfaced with the ready phases below.
    # Only run when the set is schema-clean — a phase missing `features` entirely
    # would otherwise produce a confusing second complaint on top of the first.
    coverage_advisories: list[str] = []
    if phases and not failures:
        coverage_failures, coverage_advisories = check_phase_coverage(
            phases,
            session.get("ai_features"),
            feature_specs=session.get("feature_specs"),
            revision_version=target_version if is_revision else None,
        )
        failures = failures + coverage_failures
    if phases and failures:
        if _appears_truncated(_last_assistant_text(messages)):
            failures = failures + [(
                None,
                [
                    "the response appears truncated at the model's output "
                    "limit — it ends inside an unterminated JSON object, so "
                    "the final phase block(s) are missing. Re-emitting the "
                    "same content will hit the same limit; emit more compact "
                    "phases (shorter instructions, fewer steps per phase)."
                ],
            )]
        print(
            "[agent-gen] phaser: validation failures (attempt 1): "
            + " | ".join(
                f"phase {n}: {'; '.join(errs)}" for n, errs in failures
            ),
            flush=True,
        )
        # JSON was emitted but at least one phase failed schema validation.
        # Retry once with the specific errors surfaced back to the model. On
        # providers that support it, force json_object mode so the retry
        # response is pure JSON rather than a prose-wrapped re-explanation.
        retry_user_msg = format_validation_errors_for_retry(failures)
        messages.append({"role": "user", "content": retry_user_msg})
        response_format: dict[str, Any] | None = None
        if llm.supports_response_format(llm_config.get("model", "")):
            response_format = {"type": "json_object"}
        # D-PH2l: the retry is invisible by design (its body is raw JSON),
        # which previously read as a frozen stream for the ~minutes it runs.
        # Yield a one-line status so the user sees the pipeline is working;
        # it is display-only — the success path's rendered-phases override or
        # the failure path's fallback message replaces the visible text, and
        # the message history records only what stream_turn appends.
        status_line = (
            "\n\n_Validating phase structure — re-emitting with "
            "corrections. This can take a few minutes…_\n"
        )
        yield status_line
        _set_status(
            session,
            "Validating phase structure — re-emitting with corrections…",
        )
        # Drain the retry stream — its body is raw or fenced JSON the user
        # should never see, so the content itself is swallowed. stream_turn
        # still mutates messages to record the assistant reply. D-PH9: the
        # retry yields no visible text, so the displayed-character token
        # counter would otherwise freeze here for minutes. Publish a
        # cumulative received-character total instead — attempt-1 text +
        # status line + every retry chunk — onto the shared session dict (the
        # same object the poll reads as stream["session"]), which the poll
        # threads into the counter so it climbs with real receipt. This
        # replaces the D-PH7c heartbeat dots, which measured insufficient (a
        # dot is one displayed char, not a signal of the chunk it stood in
        # for).
        _received = len(_last_assistant_text(messages)) + len(status_line)
        session["_stream_received_chars"] = _received
        for _chunk in llm.stream_turn(
            system,
            messages,
            llm_config,
            search_cfg,
            agent_name="phaser",
            response_format=response_format,
            session=session,
        ):
            if _chunk:
                _received += len(_chunk)
                session["_stream_received_chars"] = _received
        phases, failures = _extract_and_validate_phases(
            _last_assistant_text(messages)
        )
        completeness = _phase_completeness_failure(phases)
        if completeness:
            failures = failures + [completeness]
        if phases and not failures:
            coverage_failures, coverage_advisories = check_phase_coverage(
                phases,
                session.get("ai_features"),
                feature_specs=session.get("feature_specs"),
                revision_version=target_version if is_revision else None,
            )
            failures = failures + coverage_failures
        if failures:
            # Retry also failed. Drop the synthesized correction exchange so
            # the chat history does not carry a dead-end "validation failed"
            # turn, surface a recoverable message in place of the bad JSON,
            # and leave phaser_state untouched so the user can re-engage by
            # chatting further. D-PH2i: the message carries the failure
            # specifics — the user can act on them, and because this text
            # becomes the assistant message the model re-reads, a later "try
            # again" turn sees what went wrong instead of regenerating blind.
            if _appears_truncated(_last_assistant_text(messages)):
                failures = failures + [(
                    None,
                    [
                        "the response appears truncated at the model's "
                        "output limit — it ends inside an unterminated JSON "
                        "object, so the final phase block(s) are missing. "
                        "Re-emitting the same content will hit the same "
                        "limit; emit more compact phases (shorter "
                        "instructions, fewer steps per phase)."
                    ],
                )]
            print(
                "[agent-gen] phaser: validation failures (after retry): "
                + " | ".join(
                    f"phase {n}: {'; '.join(errs)}" for n, errs in failures
                ),
                flush=True,
            )
            if (
                len(messages) >= 2
                and messages[-2].get("role") == "user"
                and messages[-2].get("content") == retry_user_msg
            ):
                del messages[-2:]
            _bullets = [
                f"- Phase {n if n is not None else '(unattributed)'}: {err}"
                for n, errs in failures
                for err in errs
            ]
            _shown = "\n".join(_bullets[:10])
            _more = (
                f"\n(plus {len(_bullets) - 10} more)"
                if len(_bullets) > 10
                else ""
            )
            fallback = (
                "I tried to emit the structured phases but they didn't pass "
                "validation. The specific failures were:\n\n"
                f"{_shown}{_more}\n\n"
                "Please point me to the phase or section to correct, or "
                "reply 'try again' and I'll re-emit them with these fixes."
            )
            if messages and messages[-1].get("role") == "assistant":
                messages[-1]["content"] = fallback
            else:
                messages.append({"role": "assistant", "content": fallback})
            session["_display_override"] = fallback
            return

    if phases and not failures:
        # Append the set-completion marker to the highest-numbered phase so the
        # coding agent touches .spec4/v{N}/IMPLEMENTED after finishing the set —
        # that marker is how re-entry detects which set is implemented. Idempotent
        # (reload round-trips the instruction through the frontmatter).
        _last_phase = max(phases, key=lambda p: p.get("phase_number", 0))
        _marker_path = f".spec4/v{target_version}/IMPLEMENTED"
        _instrs = _last_phase.get("instructions")
        if isinstance(_instrs, list) and not any(
            isinstance(s, str) and _marker_path in s for s in _instrs
        ):
            _instrs.append(
                "After this phase is complete and all verification passes, create "
                "the set-completion marker so Spec4 can detect this phase set is "
                f"implemented: `touch {_marker_path}`"
            )
        # D-SC18a: render before committing state — the COMPLETE flag gates the
        # save in session.py, so a formatter failure after it persists the output
        # of a crashed turn. See the stack_advisor note for the observed case.
        display = (
            "**Your phases are ready.** Each phase is a structured prompt you will hand "
            "to your AI coding agent — one at a time, in order. The next step, "
            "**Deployer**, will show you exactly how to load and use these phases with "
            "your chosen coding agent.\n\n"
            + _format_phases_for_display(phases)
        )
        session["phaser_state"] = STATE_PHASES_COMPLETE
        session["phases"] = phases
        session["phase_version"] = target_version
        session["phaser_stale_acknowledged"] = {}
        # Deferred features are legitimate (v2/future) but worth naming, so the
        # developer sees what the plan does not build. Never blocks.
        if coverage_advisories:
            display = (
                display
                + "\n\n---\n\n**Not built by these phases:**\n\n"
                + "\n".join(f"- {a}" for a in coverage_advisories)
            )
        # Advisory cross-phase seam check (Phase-0): log + surface only, never
        # blocks or retries. Run only on the greenfield (v0) set — a brownfield
        # round is an intentional delta whose partial graph would false-positive.
        if is_greenfield:
            advisory = run_seam_check(
                phases, session.get("ai_features"), llm_config, session
            )
            if advisory:
                display = display + "\n\n---\n\n" + advisory
        messages[-1]["content"] = display
        session["_display_override"] = display
    elif not phases and ("```json" in last_text or '"phase_number"' in last_text):
        # A generation attempt produced JSON-ish text that even tolerant
        # extraction could not parse into any phase (severely malformed output).
        # Surface a recoverable message instead of silently leaving raw JSON on
        # screen with no state change and no path forward. Genuine conversational
        # turns (no phase-JSON markers) fall through untouched, as before.
        fallback = (
            "I generated the phases but couldn't parse them into the required "
            "structure. Reply 'try again' and I'll re-emit them."
        )
        if messages and messages[-1].get("role") == "assistant":
            messages[-1]["content"] = fallback
        else:
            messages.append({"role": "assistant", "content": fallback})
        session["_display_override"] = fallback
