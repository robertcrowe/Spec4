"""CodeScanner -- analyses an existing project directory and drafts a code review.

The agent turn loop lives here: the seed messages that open a fresh or an
update scan, the extract-and-validate step that turns a streamed reply into a
schema-checked ``code_review`` artifact, and ``run`` itself.

Cleanup Phase 4c turned this module into a package and moved the three
self-contained concerns into siblings, one module each:

* :mod:`spec4.agents.code_scanner._scan` -- the repo walk, the project-context
  block the seeds carry, and the size budgets that bound both.
* :mod:`spec4.agents.code_scanner._prompt` -- the frozen ``SYSTEM_PROMPT``.
* :mod:`spec4.agents.code_scanner._review_render` --
  ``_format_review_as_text`` and its section renderers.

The import path ``spec4.agents.code_scanner`` is unchanged. Phase 4j then
moved every importer onto the owning module and dropped the re-exports
nothing reached through here, so what is listed below is exactly the set some
importer outside the owning module still needs. ``__all__`` is
load-bearing rather than decorative: ``[tool.mypy] strict`` implies
``no_implicit_reexport``, so without it a re-exported name could not be
imported from this module at all.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Generator
from typing import Any

from spec4 import llm, websearch
from spec4.agents._code_review_schema import (
    format_validation_errors_for_retry,
    validate_code_review,
)
from spec4.agents._reask import (
    abandon_reask,
    reask_for_artifact,
    stream_suppressing_json,
    suppressed_as_artifact,
)
from spec4.agents._turn_flow import (
    drop_orphan_or_route_to_fresh_start,
    extract_json_block,
    last_assistant_text,
    maybe_inject_resume_summary,
    replay_last_assistant,
)
from spec4.app_constants import STATE_REVIEW_COMPLETE

from spec4.agents.code_scanner._prompt import SYSTEM_PROMPT
from spec4.agents.code_scanner._review_render import _format_review_as_text
from spec4.agents.code_scanner._scan import (
    _approx_tokens,
    _collect_files,
    _gather_project_context,
)

__all__ = [
    "_approx_tokens",
    "_build_fresh_scan_seed",
    "_build_update_scan_seed",
    "_collect_files",
    "_extract_and_validate_review",
    "_extract_review_json",
    "_format_review_as_text",
    "_gather_project_context",
    "run",
    "SYSTEM_PROMPT",
]


def _extract_review_json(text: str) -> dict[str, Any] | None:
    data = extract_json_block(text)
    return data if data is not None and "code_review" in data else None


def _extract_and_validate_review(
    text: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Extract and validate the JSON code review from text.

    Tries a fenced ```json``` block first (the standard prompt-driven path),
    then falls back to parsing the whole stripped body as raw JSON (the
    shape produced by `response_format={"type": "json_object"}` on the
    retry turn).

    Three outcomes:
    - `(review, [])`     — JSON parsed and validated cleanly.
    - `(None, errors)`   — JSON parsed but failed schema validation;
                          caller should surface `errors` back to the LLM
                          and retry once.
    - `(None, [])`       — no JSON found at all; the agent is still in
                          conversation, no retry needed.
    """
    data = extract_json_block(text)
    if data is None:
        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                data = parsed
    if data is None:
        return None, []
    if "code_review" not in data:
        return None, ["<root>: extracted JSON block is missing the 'code_review' key"]
    errors = validate_code_review(data)
    if errors:
        return None, errors
    return data, []


def _build_fresh_scan_seed(
    working_dir: str, all_files: list[pathlib.Path] | None = None
) -> str:
    context = _gather_project_context(working_dir, all_files)
    return (
        "Please introduce yourself as CodeScanner, then analyze this project "
        "directory and produce the full draft review in one shot as described in "
        "your operating instructions.\n\n"
        f"{context}"
    )


def _build_update_scan_seed(
    working_dir: str,
    prior_review: dict[str, Any],
    all_files: list[pathlib.Path] | None = None,
) -> str:
    context = _gather_project_context(working_dir, all_files)
    prior_json = json.dumps(prior_review, indent=2)
    return (
        "Please introduce yourself as CodeScanner. The user has asked you to "
        "re-scan this project, which already has a prior code review on disk.\n\n"
        "**Update mode instructions:**\n"
        "- Compare the latest project evidence below against the prior review.\n"
        "- Produce a structured **update** focusing only on what has changed: new "
        "dependencies, removed dependencies, version bumps, new commands or "
        "entrypoints, new files in the directory map, shifts in coding style, "
        "newly resolved or newly introduced incomplete/dead code, etc.\n"
        "- Present the changes as a readable summary grouped under the same "
        "section names used in the prior review. Mark each item explicitly as "
        "Added / Removed / Changed.\n"
        '- After presenting the changes, ask: "Anything to correct? Reply '
        "'looks good' to merge and finalize.\"\n"
        "- When the user confirms, emit a complete updated `code_review` JSON block "
        "(schema_version 1) reflecting the merged state. The block must be "
        "complete — not a diff — so downstream agents always see the full review.\n\n"
        "**Prior code review on disk:**\n\n"
        f"```json\n{prior_json}\n```\n\n"
        "**Latest project evidence (fresh scan):**\n\n"
        f"{context}"
    )


def run(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """CodeScanner — analyzes the project directory and creates a structured code review.

    Yields text chunks consumed by streaming.start().
    Mutates `session` to track conversation state and review output.
    """
    if "code_scanner_messages" not in session:
        session["code_scanner_messages"] = []

    msgs = session["code_scanner_messages"]
    user_input = drop_orphan_or_route_to_fresh_start(msgs, user_input)
    # D-SC-P1: characters yielded as scan-progress text before the LLM stream
    # opens. Seeded into the chars counter below so it stays monotonic across
    # the scan-to-analysis handover instead of resetting to zero.
    pre_stream_chars = 0

    # Hoisted above the branch so the scan narration can size the request it is
    # about to make (D-SC-P2). Both are pure string work — no I/O.
    search_cfg = websearch.from_session(session)
    system = llm.build_system_prompt(SYSTEM_PROMPT, search_cfg)

    if user_input is None:
        if msgs:
            if (
                session.get("code_scanner_state") == STATE_REVIEW_COMPLETE
                and session.get("code_scanner_artifact_msg_count") == len(msgs)
                and session.get("code_review") is not None
            ):
                display = _format_review_as_text(session["code_review"])
                msgs[-1]["content"] = display
                session["_display_override"] = display
                yield display
                return
            if not maybe_inject_resume_summary(
                session, "code_scanner", msgs, STATE_REVIEW_COMPLETE
            ):
                yield from replay_last_assistant(msgs)
                return
        else:
            existing_review = session.get("code_review")
            if (
                existing_review is not None
                and session.get("code_scanner_state") == STATE_REVIEW_COMPLETE
            ):
                display = _format_review_as_text(existing_review)
                msgs.append(
                    {
                        "role": "user",
                        "content": "[Spec4: displaying existing code review]",
                    }
                )
                msgs.append({"role": "assistant", "content": display})
                session["code_scanner_artifact_msg_count"] = len(msgs)
                session["_display_override"] = display
                yield display
                return

            working_dir = session.get("working_dir")
            if not working_dir:
                yield (
                    "I'm the **CodeScanner**. I analyze your project directory to "
                    "understand the existing codebase.\n\n"
                    "No project directory has been selected. Please go back and "
                    "select a working directory first."
                )
                return

            # D-SC-P1: the directory walk and the sample reads that follow it
            # run for seconds on a large tree, and until now yielded nothing —
            # the user watched an empty bubble with no indication the agent was
            # working. Narrate the two phases as they happen. This text is
            # display-only: on the artifact turn `_display_override` replaces
            # the visible message wholesale, and the message history records
            # only what `stream_turn` appends.
            mode = "Re-scanning" if existing_review is not None else "Scanning"
            intro_line = f"**{mode}** `{working_dir}`…\n\n"
            pre_stream_chars += len(intro_line)
            yield intro_line

            all_files = _collect_files(pathlib.Path(working_dir))
            n = len(all_files)
            count_line = (
                f"- Indexed **{n}** file{'' if n == 1 else 's'} — reading "
                "manifests, README, and source samples…\n"
            )
            pre_stream_chars += len(count_line)
            yield count_line

            if existing_review is not None:
                seed = _build_update_scan_seed(working_dir, existing_review, all_files)
            else:
                seed = _build_fresh_scan_seed(working_dir, all_files)
            msgs.append({"role": "user", "content": seed})

            # D-SC-P2: what follows is a single completion call, and the wait
            # before its first token is dominated by prefill over this request.
            # Nothing runs locally in that window, so name the size and the
            # model rather than leaving "analyzing…" to imply local work.
            approx = _approx_tokens(system) + _approx_tokens(seed)
            model = llm_config.get("model") or "the configured model"
            done_line = (
                f"\nScan complete — sent ~{approx:,} tokens to "
                f"`{model}`.\n\n"
                "_Waiting for the first response. Large projects can take a "
                "couple of minutes before text starts appearing._\n\n---\n\n"
            )
            pre_stream_chars += len(done_line)
            yield done_line
    else:
        msgs.append({"role": "user", "content": user_input})

    yield from stream_suppressing_json(
        llm.stream_turn(
            system,
            msgs,
            llm_config,
            search_cfg,
            agent_name="code_scanner",
            session=session,
        ),
        session,
        seed=pre_stream_chars,
        reply_status="CodeScanner is replying…",
        artifact_status=("Drafting the code review — this can take a few minutes…"),
    )

    raw_reply = last_assistant_text(msgs)
    review, errors = _extract_and_validate_review(raw_reply)
    if review is None and not errors and suppressed_as_artifact(raw_reply):
        # D-SC-P3: `(None, [])` normally means "no JSON here, still conversing"
        # — and that is a legitimate turn, because the reply was shown to the
        # developer. It means something else entirely when the reply opened with
        # a fence: the whole response was suppressed on its way to the screen, so
        # a finalize turn whose block is malformed or truncated before its
        # closing fence ends with nothing displayed, no state change, and no
        # code_review.json — an empty bubble and no controls, which is what the
        # developer sees as "it finalized and then nothing happened". Fail it
        # into the retry path below instead, which already knows how to re-ask
        # for the artifact and how to explain itself if the re-ask fails too.
        errors = [
            "<root>: the fenced JSON block could not be parsed — it was "
            "malformed, or truncated before its closing fence"
        ]
    if review is None and errors:
        # JSON was emitted but failed schema validation. Retry once,
        # surfacing the specific errors back to the model. On providers
        # that support it, force json_object mode so the retry response
        # is pure JSON instead of prose-wrapped re-explanation.
        retry_user_msg = format_validation_errors_for_retry(errors)
        response_format: dict[str, Any] | None = None
        if llm.supports_response_format(llm_config.get("model", "")):
            response_format = {"type": "json_object"}
        # The re-ask drains silently — its body is raw or fenced JSON the user
        # should never see — while publishing the running char total so the
        # counter does not freeze for its duration (D-SC-P1 / D-PH9).
        yield from reask_for_artifact(
            system=system,
            msgs=msgs,
            llm_config=llm_config,
            search_config=search_cfg,
            agent_name="code_scanner",
            correction=retry_user_msg,
            status_line=(
                "\n\n_The structured review needs a correction pass — re-emitting…_\n"
            ),
            response_format=response_format,
            session=session,
            seed=pre_stream_chars + len(last_assistant_text(msgs)),
        )
        review, _ = _extract_and_validate_review(last_assistant_text(msgs))
        if review is None:
            # Retry failed too. Drop the synthesized correction exchange so the
            # chat history does not carry a dead-end user turn, surface a brief
            # recoverable message in place of the bad JSON, and leave
            # code_scanner_state untouched so the user can re-engage by chatting.
            abandon_reask(
                msgs,
                retry_user_msg,
                "I tried to emit the structured review but it didn't pass "
                "validation. Please point me to the section to correct, "
                "or reply 'try again' and I'll re-emit it.",
                session,
            )

    if review:
        # D-SC18a: render before committing state — the COMPLETE flag gates the
        # save in session.py, so a formatter failure after it persists the output
        # of a crashed turn. See the stack_advisor note for the observed case.
        display = _format_review_as_text(review)
        session["code_scanner_state"] = STATE_REVIEW_COMPLETE
        session["code_review"] = review
        msgs[-1]["content"] = display
        session["_display_override"] = display
        session["code_scanner_artifact_msg_count"] = len(msgs)
