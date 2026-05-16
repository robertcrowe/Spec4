from __future__ import annotations

import json
import re
from collections.abc import Generator
from pathlib import Path
from typing import Any

from spec4 import project_manager, tavily_mcp
from spec4.agents._phase_schema import (
    format_validation_errors_for_retry,
    validate_phase,
)
from spec4.agents._utils import (
    _drop_orphan_or_route_to_fresh_start,
    _last_assistant_text,
    _maybe_inject_staleness_question,
    _replay_last_assistant,
)
from spec4.app_constants import STATE_PHASES_COMPLETE


SYSTEM_PROMPT = """\
You are Phaser, an expert software architect specializing in incremental delivery\
strategy. Your job is to take a project vision and a technology stack spec, then\
decompose them into a sequence of right-sized, executable development phases — each\
one designed so that an AI coding agent (like Claude Code) can implement it\
successfully on the first attempt. You prioritize stable foundations, early test\
coverage, and vertical slices of working functionality over broad scaffolding that\
implements nothing.

**Context you will receive**

At the start of the conversation you will receive one or more of the following:
- **Vision statement** — describes the project purpose, audience, and key features (MVP\
  and future)
- **Technology stack spec** — the authoritative list of approved languages, libraries,\
  services, and infrastructure
- **Code review** — a snapshot of the existing codebase (brownfield projects)
- **Existing phases** — phases already planned or completed (brownfield updates)
- **Design mock note** — a note about whether a finalized UI design mock exists; when\
  present, include a step in every UI-related phase directing the coding agent to\
  reference `.spec4/design/mock.html` for visual guidance

**Spec4 file paths**

If a phase ever needs to reference one of Spec4's own planning artifacts in its\
 `instructions`, `verification`, or `references`, use these exact paths verbatim — do\
 not invent variants like `stack-spec.json` or `tech-stack.json`:
- `.spec4/vision.json`
- `.spec4/stack.json`
- `.spec4/code_review.json`
- `.spec4/phases/phase{N}.md` (the phase files this agent generates)
- `.spec4/design/mock.html` (finalized UI mock, when present)

**Phase 1: The Steel Thread**

Phase 1 must always be a "Steel Thread" — a minimal, working end-to-end path that\
proves the core architecture is alive before any feature development begins:
- Connect the primary layers (e.g., frontend ↔ backend, backend ↔ database)
- Validate all environmental plumbing: env vars, DB connections, API handshakes
- Produce one observable result (a health-check endpoint, a rendered page, a CLI\
  command that returns output)

If the plumbing doesn't work in Phase 1, every subsequent phase will fail. Phase 1\
contains no feature development — only connectivity and validation.

**Stack Spec Fidelity**

Treat the stack spec as the authoritative list of approved components. If any phase\
requires a component, library, or service NOT already defined in the stack spec, stop\
and ask the user for explicit confirmation before including it. Describe what it is, why\
it is needed, and what it adds. Ask directly — never as "X or Y?" — and end with\
"(yes/no — you're also welcome to ask questions or share comments either way)". Wait\
for approval. Do not assume approval.

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
   automatically render the validated phases into Markdown files (one `phase{N}.md`\
   per phase, each combining a JSON frontmatter block with a prose body for the\
   coding agent), package them into a zip, and present a download button.

**Brownfield — Existing phases**

When a set of existing phases is provided, those phases represent work already planned\
or completed. Do NOT re-plan or repeat them. Analyze the updated vision and stack to\
determine what new functionality is needed beyond what the existing phases cover, then\
plan only the additional phases required. Number new phases starting from the last\
existing phase number + 1; set `total_phases` to the combined count (existing + new).

**Brownfield — Existing codebase, no prior phases**

When a code review is provided but no prior phases exist, the project has real code in\
place. Phase 1 must NOT scaffold the project from scratch — it must be an integration\
and validation thread: confirm the existing codebase builds and runs under the stack\
spec, resolve any conflicts identified in the code review, and establish a clean\
baseline. For all subsequent phases, use the code review to inform your instructions:\
respect the existing module structure, naming conventions, and patterns documented in\
the review rather than inventing new ones.

**Technical Standards**

Whenever the vision, stack spec, or user mentions a technical standard, specification,\
protocol, API, or SDK, use the web_search tool to find the canonical documentation URL.\
Ask the user to confirm you have identified the correct standard. Once confirmed, add\
the standard and its canonical URL to the `references` array in every phase JSON that\
uses it. If a reference cannot be confirmed via web search or is specific to the user's\
project, label it as "unique to this project" rather than guessing. Every technical\
standard, specification, protocol, API, or SDK referenced in a phase must appear in that\
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
      "description": "Step-by-step technical instructions for the AI coder. Each item is one concrete, actionable step — specific enough that an AI coder cannot misinterpret it."
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
"""


def _load_phaser_design_note(design_dir: Path) -> str:
    """Return a note about the UI design mock for inclusion in the Phaser seed."""
    mock_path = design_dir / "mock.html"
    if mock_path.exists() and mock_path.read_text(encoding="utf-8").strip():
        return (
            "A finalized UI design mock is available at .spec4/design/mock.html. "
            "Direct the coding agent to reference this file during implementation "
            "to match the intended visual design."
        )
    return (
        "No UI design mock was produced. UI design decisions are left to the "
        "developer's discretion."
    )


def _extract_phases(text: str) -> list[dict[str, Any]]:
    """Extract all JSON phase objects from fenced code blocks in the LLM response."""
    phases: list[dict[str, Any]] = []
    for match in re.finditer(r"```json\s*(.*?)\s*```", text, re.DOTALL):
        try:
            data: dict[str, Any] = json.loads(match.group(1))
            if "phase_number" in data:
                phases.append(data)
        except json.JSONDecodeError:
            pass
    return phases


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
    empty extracted list means the assistant said something other than
    phase JSON (the conversation is still in progress) — no retry needed.
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


def _format_phases_for_display(phases: list[dict[str, Any]]) -> str:
    """Render every phase as Markdown for the in-chat display."""
    return "\n\n---\n\n".join(
        project_manager.render_phase_markdown(p) for p in phases
    )


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
        existing_phases = session.get("phases") or []
        code_review = session.get("code_review")

        working_dir = session.get("working_dir")
        design_dir = Path(working_dir) / ".spec4" / "design" if working_dir else None
        design_note = _load_phaser_design_note(design_dir) if design_dir else ""
        design_note_block = f"{design_note}\n\n" if design_note else ""

        vision_block = (
            f"Here is the project vision statement:\n\n```json\n{json.dumps(vision, indent=2)}\n```\n\n"
            if vision
            else ""
        )
        stack_block = (
            f"Here is the technology stack spec:\n\n```json\n{json.dumps(stack, indent=2)}\n```\n\n"
            if stack
            else ""
        )

        if existing_phases:
            phases_json = "\n\n".join(
                f"```json\n{json.dumps(p, indent=2)}\n```" for p in existing_phases
            )
            extra_block = (
                f"The following phases have already been planned (treat as completed work — "
                f"do not re-plan them):\n\n{phases_json}\n\n"
            )
            instruction = (
                "Please introduce yourself as Phaser, then analyze the updated vision and stack "
                "and generate only the new phases needed to implement the changes, numbered from "
                "where the existing phases leave off."
            )
        elif code_review:
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

        seed = (
            f"{vision_block}{stack_block}{extra_block}{design_note_block}{instruction}"
        )
        messages.append({"role": "user", "content": seed})
    else:
        messages.append({"role": "user", "content": user_input})

    tavily_api_key = session.get("tavily_api_key")
    system = tavily_mcp.build_system_prompt(SYSTEM_PROMPT, tavily_api_key)

    yield from tavily_mcp.stream_turn(
        system, messages, llm_config, tavily_api_key, agent_name="phaser"
    )

    phases, failures = _extract_and_validate_phases(_last_assistant_text(messages))
    if phases and failures:
        # JSON was emitted but at least one phase failed schema validation.
        # Retry once with the specific errors surfaced back to the model. On
        # providers that support it, force json_object mode so the retry
        # response is pure JSON rather than a prose-wrapped re-explanation.
        retry_user_msg = format_validation_errors_for_retry(failures)
        messages.append({"role": "user", "content": retry_user_msg})
        response_format: dict[str, Any] | None = None
        if tavily_mcp.supports_response_format(llm_config.get("model", "")):
            response_format = {"type": "json_object"}
        # Drain the retry stream silently — its body is raw or fenced JSON
        # the user should never see. stream_turn still mutates messages to
        # record the assistant reply.
        for _chunk in tavily_mcp.stream_turn(
            system,
            messages,
            llm_config,
            tavily_api_key,
            agent_name="phaser",
            response_format=response_format,
        ):
            pass
        phases, failures = _extract_and_validate_phases(
            _last_assistant_text(messages)
        )
        if failures:
            # Retry also failed. Drop the synthesized correction exchange so
            # the chat history does not carry a dead-end "validation failed"
            # turn, surface a brief recoverable message in place of the bad
            # JSON, and leave phaser_state untouched so the user can re-
            # engage by chatting further.
            if (
                len(messages) >= 2
                and messages[-2].get("role") == "user"
                and messages[-2].get("content") == retry_user_msg
            ):
                del messages[-2:]
            fallback = (
                "I tried to emit the structured phases but they didn't pass "
                "validation. Please point me to the phase or section to "
                "correct, or reply 'try again' and I'll re-emit them."
            )
            if messages and messages[-1].get("role") == "assistant":
                messages[-1]["content"] = fallback
            else:
                messages.append({"role": "assistant", "content": fallback})
            session["_display_override"] = fallback
            return

    if phases and not failures:
        session["phaser_state"] = STATE_PHASES_COMPLETE
        session["phases"] = phases
        session["phaser_stale_acknowledged"] = {}
        display = (
            "**Your phases are ready.** Each phase is a structured prompt you will hand "
            "to your AI coding agent — one at a time, in order. The next step, "
            "**Deployer**, will show you exactly how to load and use these phases with "
            "your chosen coding agent.\n\n"
            + _format_phases_for_display(phases)
        )
        messages[-1]["content"] = display
        session["_display_override"] = display
