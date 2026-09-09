"""Phaser -- decomposes a vision and a stack spec into executable phases.

The agent turn loop lives here: the seed messages (fresh, revision, resumed,
post-code-review), the stack-addition and validation retry protocol, the seam
check and coverage advisories, and ``run`` itself.

Cleanup Phase 4e turned this module into a package and moved the three
self-contained concerns into siblings, one module each:

* :mod:`spec4.agents.phaser._prompt` -- the frozen ``SYSTEM_PROMPT``.
* :mod:`spec4.agents.phaser._phase_extract` -- the JSON walk, the phase and
  stack-addition extractors, the truncation and completeness checks, and the
  Markdown display renderer.
* :mod:`spec4.agents.phaser._revision` -- the design-mock note and the
  revision delta with its phase-scoping note.

The import path ``spec4.agents.phaser`` is unchanged, and every name the split
moved is re-exported below, so no importer changed when the code moved --
import from here or from the owning module, both resolve to the same object.
``__all__`` is load-bearing rather than decorative: ``[tool.mypy] strict``
implies ``no_implicit_reexport``, so without it a re-exported name could not be
imported from this module at all. ``validate_phase`` is listed there for the
same reason: it was an attribute of the pre-split module, it is now used only
by the sibling that took the code needing it, and the re-export keeps the
attribute surface whole.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any, cast

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

from spec4.agents.phaser._phase_extract import (
    _appears_truncated,
    _extract_and_strip_stack_additions,
    _extract_and_validate_phases,
    _extract_phases,
    _format_phases_for_display,
    _objects_with_key,
    _phase_completeness_failure,
)
from spec4.agents.phaser._prompt import SYSTEM_PROMPT
from spec4.agents.phaser._revision import (
    _load_phaser_design_note,
    build_revision_note,
    revision_delta,
)

__all__ = [
    "_appears_truncated",
    "build_revision_note",
    "_extract_and_strip_stack_additions",
    "_extract_and_validate_phases",
    "_extract_phases",
    "_format_phases_for_display",
    "_load_phaser_design_note",
    "_objects_with_key",
    "_phase_completeness_failure",
    "revision_delta",
    "run",
    "SYSTEM_PROMPT",
    "validate_phase",
]


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
        _brownfield = project_manager.session_is_brownfield(session)
        if _wd:
            target_version, _ = project_manager.resolve_phase_version(_wd, _brownfield)
        else:
            target_version = 1 if _brownfield else 0
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
            _load_phaser_design_note(design_dir, target_version) if design_dir else ""
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
            # is_revision implies delta is not None (see its definition).
            extra_block = (
                f"{extra_block}{build_revision_note(cast(dict[str, Any], delta))}\n\n"
            )
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
        seed = f"{round_block}{vision_block}{spine_block}{stack_block}{extra_block}{ai_features_block}{manifest_block}{design_note_block}{instruction}"
        messages.append({"role": "user", "content": seed})
    else:
        messages.append({"role": "user", "content": user_input})

    search_cfg = websearch.from_session(session)
    system = llm.build_system_prompt(SYSTEM_PROMPT, search_cfg)

    pre_len = len(messages)
    yield from llm.stream_turn(
        system,
        messages,
        llm_config,
        search_cfg,
        agent_name="phaser",
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

    last_text = (
        cleaned_per_msg[-1] if cleaned_per_msg else _last_assistant_text(messages)
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
            failures = failures + [
                (
                    None,
                    [
                        "the response appears truncated at the model's output "
                        "limit — it ends inside an unterminated JSON object, so "
                        "the final phase block(s) are missing. Re-emitting the "
                        "same content will hit the same limit; emit more compact "
                        "phases (shorter instructions, fewer steps per phase)."
                    ],
                )
            ]
        print(
            "[agent-gen] phaser: validation failures (attempt 1): "
            + " | ".join(f"phase {n}: {'; '.join(errs)}" for n, errs in failures),
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
        phases, failures = _extract_and_validate_phases(_last_assistant_text(messages))
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
                failures = failures + [
                    (
                        None,
                        [
                            "the response appears truncated at the model's "
                            "output limit — it ends inside an unterminated JSON "
                            "object, so the final phase block(s) are missing. "
                            "Re-emitting the same content will hit the same "
                            "limit; emit more compact phases (shorter "
                            "instructions, fewer steps per phase)."
                        ],
                    )
                ]
            print(
                "[agent-gen] phaser: validation failures (after retry): "
                + " | ".join(f"phase {n}: {'; '.join(errs)}" for n, errs in failures),
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
            _more = f"\n(plus {len(_bullets) - 10} more)" if len(_bullets) > 10 else ""
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
            "your chosen coding agent.\n\n" + _format_phases_for_display(phases)
        )
        session["phaser_state"] = STATE_PHASES_COMPLETE
        session["phases"] = phases
        session["phase_version"] = target_version
        session["phaser_stale_acknowledged"] = {}
        # The artifact stamp every agent writes on its completing turn: "the
        # last message is the artifact". The cost card keys off it so a Modify
        # run shows the card once, at the end, not after every step.
        session["phaser_artifact_msg_count"] = len(messages)
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
