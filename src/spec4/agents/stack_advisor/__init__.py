"""StackAdvisor -- guides the developer through technology stack selection.

The agent turn loop lives here: the four seed messages (fresh, existing-stack,
revision, post-code-review), the artifact re-ask protocol, and ``run`` itself.

Cleanup Phase 4d turned this module into a package and moved the three
self-contained concerns into siblings, one module each:

* :mod:`spec4.agents.stack_advisor._prompt` -- the frozen ``SYSTEM_PROMPT``.
* :mod:`spec4.agents.stack_advisor._stack_shape` -- the revision delta and its
  note, the shape normalisation, and the JSON extraction.
* :mod:`spec4.agents.stack_advisor._render` -- ``_format_stack_as_text`` and
  the helpers it renders through.

The import path ``spec4.agents.stack_advisor`` is unchanged. Phase 4j then
moved every importer onto the owning module and dropped the re-exports
nothing reached through here, so what is listed below is exactly the set some
importer outside the owning module still needs. ``__all__`` is
load-bearing rather than decorative: ``[tool.mypy] strict`` implies
``no_implicit_reexport``, so without it a re-exported name could not be
imported from this module at all.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

from spec4 import project_manager, llm, websearch
from spec4.agents._feature_context import ai_features_for_stack, feature_specs_for_stack
from spec4.agents._reask import (
    abandon_reask,
    artifact_fallback,
    artifact_reask_prompt,
    artifact_reask_status,
    reask_for_artifact,
    stream_suppressing_json,
    suppressed_as_artifact,
)
from spec4.agents._stack_context import (
    design_manifest_for_stack,
    load_design_manifest,
)
from spec4.agents._turn_flow import (
    drop_orphan_or_route_to_fresh_start,
    last_assistant_text,
    maybe_inject_resume_summary,
    maybe_inject_staleness_question,
    replay_last_assistant,
)
from spec4.app_constants import STATE_STACK_COMPLETE

from spec4.agents.stack_advisor._prompt import SYSTEM_PROMPT
from spec4.agents.stack_advisor._render import _format_stack_as_text
from spec4.agents.stack_advisor._stack_shape import (
    _extract_stack_json,
    _normalise_stack_shape,
    build_revision_note,
    revision_delta,
)

__all__ = [
    "build_revision_note",
    "_extract_stack_json",
    "_format_stack_as_text",
    "_normalise_stack_shape",
    "revision_delta",
    "run",
    "SYSTEM_PROMPT",
]


def run(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Stack Advisor — guides the user through technology stack selection.

    Yields text chunks consumed by streaming.start().
    Mutates `session` to track conversation state and stack output.
    """
    if "stack_advisor_messages" not in session:
        session["stack_advisor_messages"] = []

    messages = session["stack_advisor_messages"]
    user_input = drop_orphan_or_route_to_fresh_start(messages, user_input)

    if user_input is None:
        if messages:
            stale_q = maybe_inject_staleness_question(
                session, "stack_advisor", messages
            )
            if stale_q is not None:
                yield stale_q
                return
            if not maybe_inject_resume_summary(
                session, "stack_advisor", messages, STATE_STACK_COMPLETE
            ):
                yield from replay_last_assistant(messages)
                return
            # Resume summary injected — fall through to LLM call.
        else:
            # Seed with available context, then call LLM
            messages.append({"role": "user", "content": _stack_seed_message(session)})
    else:
        messages.append({"role": "user", "content": user_input})

    search_cfg = websearch.from_session(session)
    system = llm.build_system_prompt(SYSTEM_PROMPT, search_cfg)

    yield from stream_suppressing_json(
        llm.stream_turn(
            system,
            messages,
            llm_config,
            search_cfg,
            agent_name="stack_advisor",
            session=session,
        ),
        session,
        reply_status="StackAdvisor is replying…",
        artifact_status=(
            "Drafting the stack specification — this can take a few minutes…"
        ),
    )

    raw_reply = last_assistant_text(messages)
    stack_spec = _extract_stack_json(raw_reply)
    if stack_spec is None and suppressed_as_artifact(raw_reply):
        # D-SA-P3 (the D-SC-P3 fix, applied here): `_extract_stack_json` returns
        # None both for "no JSON here, still conversing" and for "the artifact
        # block came back unreadable". The two look identical from here but are
        # not: a reply opening with a fence was suppressed on its way to the
        # screen, so the unreadable case ends the turn with an empty bubble, no
        # STACK_COMPLETE, and no stack.json — the developer sees the finalize
        # step do nothing at all. Re-ask once, and if that fails too, say so.
        correction = artifact_reask_prompt("stack specification")
        yield from reask_for_artifact(
            system=system,
            msgs=messages,
            llm_config=llm_config,
            search_config=search_cfg,
            agent_name="stack_advisor",
            correction=correction,
            status_line=artifact_reask_status("stack specification"),
            session=session,
            seed=len(raw_reply),
        )
        stack_spec = _extract_stack_json(last_assistant_text(messages))
        if stack_spec is None:
            abandon_reask(
                messages,
                correction,
                artifact_fallback("stack recommendation"),
                session,
            )
    if stack_spec:
        # D-SC18a: render BEFORE committing any session state. The COMPLETE flag
        # is the sole gate on save_stack (session.py), so setting it ahead of work
        # that can throw persists the output of a turn that crashed — a formatter
        # AttributeError on a schema-deviant `libraries` wrote a never-rendered
        # stack.json to disk, three attempts running, each looking like a failure
        # to the developer and a success to the pipeline.
        _stack_commit(session, messages, stack_spec)


def _stack_seed_message(session: dict[str, Any]) -> str:
    """The whole seed message for a fresh StackAdvisor turn."""
    vision = session.get("vision_statement")
    stack = session.get("stack_statement")
    code_review = session.get("code_review")
    ai_features = session.get("ai_features")
    working_dir = session.get("working_dir")
    current_version = (
        project_manager.active_version(working_dir, session) if working_dir else None
    )
    ai_features_block = (
        ai_features_for_stack(ai_features, current_version) + "\n"
        if ai_features
        else ""
    )
    feature_specs = session.get("feature_specs")
    spine_block = (
        feature_specs_for_stack(feature_specs, ai_features) + "\n\n"
        if feature_specs
        else ""
    )

    design_dir = (
        project_manager.get_version_dir(working_dir, current_version) / "design"
        if working_dir and current_version is not None
        else None
    )
    design_ctx = design_manifest_for_stack(load_design_manifest(design_dir))
    design_block = f"{design_ctx}\n\n" if design_ctx else ""

    vision_block = (
        f"Here is my project vision statement:\n\n```json\n{json.dumps(vision, indent=2)}\n```\n\n"
        if vision
        else ""
    )
    code_review_block = (
        f"For context, here is a code review of the existing project:\n\n"
        f"```json\n{json.dumps(code_review, indent=2)}\n```\n\n"
        "Within the review, treat `runtime_versions`, `languages`, "
        "`frameworks`, `dependencies`, `protocols_implemented`, "
        "`build_system`, and `commands.deploy` as authoritative facts. "
        "`protocols_implemented` are industry standards already wired "
        "in — treat them as constraints when proposing changes. The "
        "`notes` block is typed observations — pay particular "
        "attention to `notes.change_risks` when proposing technology "
        "swaps.\n\n"
        "**Important:** If any stack choices proposed during our conversation conflict with "
        "the existing technologies above (different language, incompatible framework, etc.), "
        "proactively warn me about the conflict, explain the implications (migration effort, "
        "incompatibility risks), and offer concrete options: keep existing tech, migrate to "
        "new choice, or a hybrid approach.\n\n"
        if code_review
        else ""
    )

    prior_stack = project_manager.load_prior_stack(working_dir) if working_dir else None
    delta = revision_delta(vision)

    if stack:
        seed = (
            f"{vision_block}"
            f"{spine_block}"
            f"{design_block}"
            f"{code_review_block}"
            f"{ai_features_block}"
            f"I also have an existing stack spec:\n\n"
            f"```json\n{json.dumps(stack, indent=2)}\n```\n\n"
            "Please introduce yourself as StackAdvisor and briefly summarize the existing "
            "stack spec. Then ask me: would I like to **continue refining this existing "
            "stack**, or would I prefer to **start with a completely new stack** from "
            "scratch? Wait for my answer before proceeding."
        )
    elif prior_stack is not None and delta is not None:
        # Revision mode: a previous version of this project has been
        # implemented. Carry the established stack forward as the
        # baseline and scope recommendations to this revision's vision
        # delta rather than re-deciding the whole stack from scratch.
        seed = (
            f"{vision_block}"
            f"{spine_block}"
            f"{design_block}"
            f"{code_review_block}"
            f"{ai_features_block}"
            "I am starting a REVISION round on an existing, already-implemented "
            "version of this project. Operate in REVISION mode.\n\n"
            "Here is the established stack spec from the previous implemented "
            "version, to carry forward as the baseline:\n\n"
            f"```json\n{json.dumps(prior_stack, indent=2)}\n```\n\n"
            f"{build_revision_note(delta)}\n\n"
            "Please introduce yourself as StackAdvisor, briefly confirm the "
            "established stack you are carrying forward, then guide me through "
            "only the incremental stack changes this revision's new or changed "
            "features require. Do not re-decide the established stack or re-run "
            "the full topic sequence."
        )
    elif code_review:
        seed = (
            f"{vision_block}"
            f"{spine_block}"
            f"{design_block}"
            f"{code_review_block}"
            f"{ai_features_block}"
            "Please introduce yourself as StackAdvisor. Briefly describe what you understand "
            "about the project's existing technology from the code review, then offer me two "
            "options: (1) you draft an initial stack spec based on what you found for me to "
            "review and refine, or (2) we start fresh and you guide me through the usual "
            "stack selection questions. Ask me which I'd prefer."
        )
    else:
        seed = (
            f"{vision_block}"
            f"{spine_block}"
            f"{design_block}"
            f"{ai_features_block}"
            "Please introduce yourself as StackAdvisor, greet the user, and begin guiding "
            "me through the technology stack selection."
        )
    return seed


def _stack_commit(
    session: dict[str, Any], messages: list[dict[str, Any]], stack_spec: dict[str, Any]
) -> None:
    """Render first, then commit the stack to the session (D-SC18a)."""
    display = _format_stack_as_text(stack_spec)
    session["stack_advisor_state"] = STATE_STACK_COMPLETE
    session["stack_statement"] = stack_spec
    session["stack_advisor_stale_acknowledged"] = {}
    messages[-1]["content"] = display
    session["_display_override"] = display
    session["stack_advisor_artifact_msg_count"] = len(messages)
