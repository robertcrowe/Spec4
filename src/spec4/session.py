from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

from spec4 import llm, llm_selection, project_manager
from spec4.agents import brainstormer, code_scanner, deployer, phaser, stack_advisor
from spec4.app_constants import (
    FF_PROMPT,
    STATE_AGENTIFIER_COMPLETE,
    STATE_DEPLOYER_COMPLETE,
    STATE_IN_PROGRESS,
    STATE_PHASES_COMPLETE,
    STATE_REVIEW_COMPLETE,
    STATE_STACK_COMPLETE,
    STATE_VISION_COMPLETE,
)


# ---------------------------------------------------------------------------
# Default session state
# ---------------------------------------------------------------------------


def _default_session() -> dict[str, Any]:
    return {
        "working_dir": None,
        "browser_path": None,
        "phase": "landing",
        "provider": None,
        "model": None,
        "api_key": None,
        "available_models": None,
        "search_provider": None,
        "search_api_key": None,
        "setup_error": None,
        "agent_select_error": None,
        "llm_config": None,
        # Per-agent model overrides, keyed by the seven user-facing agent names
        # only (app_constants.AGENT_KEYS). An agent with no entry runs on
        # `llm_config` above, resolved fresh each turn by `llm_selection.resolve`,
        # so it follows the default if the default later changes. Sub-agents
        # never appear here: they inherit whatever their parent resolved.
        "agent_llm": {},
        # Agent -> True once the developer has answered "default or pick" for
        # it. Separate from `agent_llm` because the two are cleared on
        # different events: a new project re-asks while keeping the previous
        # choice to offer back.
        "agent_llm_asked": {},
        # Connect failure text for the open per-agent gate. Transient like
        # `setup_error` — never preserved, cleared when a gate opens.
        "agent_llm_error": None,
        # The override being assembled in an open gate: {"agent", "provider",
        # "api_key", "available_models", "model"}. Singular because only one
        # gate can be open at a time, which is also why the gate's components
        # need no per-agent ids. Never committed — Continue turns it into an
        # `agent_llm` entry and clears it — so a half-built draft can never be
        # resolved into a call.
        "agent_llm_draft": None,
        # The Designer draw that failed, held across the page rebuild that
        # opening the model picker causes. The wizard's own stores are
        # memory-scoped and are re-created by that rebuild, so without this the
        # error panel, the preference text and the screenshots are all gone by
        # the time a model has been chosen. Consumed and cleared by
        # `designer_layout`; transient like `agent_llm_error`, so it is not in
        # `_PRESERVED_SETUP_KEYS` — it belongs to one draw, not to the
        # connection.
        "_designer_failed_draw": None,
        "messages": [],
        "active_agent": "brainstormer",
        "code_scanner_state": STATE_IN_PROGRESS,
        "code_scanner_messages": [],
        "code_review": None,
        "brainstormer_state": STATE_IN_PROGRESS,
        "brainstormer_messages": [],
        "vision_statement": None,
        "feature_specs": None,
        "agentifier_state": STATE_IN_PROGRESS,
        "agentifier_messages": [],
        "agentifier_scout_pool": None,
        "agentifier_breadth_chosen": False,
        "agentifier_breadth_groups": None,
        "agentifier_breadth_intro": None,
        "agentifier_breadth_selection": None,
        "agentifier_explicitly_rejected": None,
        "agentifier_candidates": None,
        "agentifier_analyses": None,
        "ai_catalog": None,
        "agentifier_catalog_done": False,
        "agentifier_spec_index": 0,
        "agentifier_spec_results": [],
        "agentifier_spec_done": False,
        "agentifier_cross_cutting_analysis": None,
        "agentifier_cross_cutting_topics": [],
        "agentifier_cross_cutting_index": 0,
        "agentifier_cross_cutting_decisions": {},
        "agentifier_cross_cutting_done": False,
        "agentifier_priority_done": False,
        "ai_features": None,
        "agentifier_stale_acknowledged": {},
        "stack_advisor_messages": [],
        "stack_advisor_state": STATE_IN_PROGRESS,
        "stack_statement": None,
        "phaser_state": None,
        "phaser_messages": [],
        "phases": [],
        "phase_version": None,
        "deployer_state": STATE_IN_PROGRESS,
        "deployer_messages": [],
        "brainstormer_stale_acknowledged": {},
        "stack_advisor_stale_acknowledged": {},
        "phaser_stale_acknowledged": {},
        "deployer_stale_acknowledged": {},
        "designer_stale_acknowledged": {},
        # D-PM1: unanswered until the developer says whether this directory
        # holds a project we are modifying. Session-scoped on purpose — it is
        # never written to disk, so a restart asks again.
        "project_mode": None,
        "_prior_app_name": None,
        "_initial_turn_done": False,
        "_stream_id": None,
        # D-ER1: set by the poll when a turn dies on a provider error, which is
        # what puts the Try Again panel in the chat. Cleared by every turn start.
        "_stream_error": None,
        # One-line status shown under the chat input while a stream runs.
        # Seeded per-agent at turn start, overwritten by agents as stages
        # progress, cleared by the poll when the stream finalises.
        "_stream_status": None,
    }


# Setup keys preserved across "Start New Project" — these represent the
# developer's LLM connection, which is independent of any specific project.
_PRESERVED_SETUP_KEYS: tuple[str, ...] = (
    "provider",
    "api_key",
    "model",
    "available_models",
    "llm_config",
    # Per-agent overrides are connection config too: a developer who switches
    # project keeps the models they chose. `agent_llm_asked` is deliberately
    # absent, so the new project re-asks per agent — with the carried-forward
    # override offered back as the primary answer.
    "agent_llm",
    "search_provider",
    "search_api_key",
    # Pre-Exa sessions stored the search key here. Preserved so a session
    # carried across an upgrade keeps web search working (websearch.from_session
    # reads it as a fallback) rather than silently losing it on a project switch.
    "tavily_api_key",
)


def _reset_for_new_project(session: dict[str, Any]) -> dict[str, Any]:
    """Build a fresh-default session preserving only the LLM setup keys.

    Used by the "Start New Project" action in Deployer. Clears every
    project-specific field (working_dir, all agent messages/states/artifacts,
    chat display messages, the deployer plan flags, staleness acknowledgements,
    resume snapshots, etc.) so the agents page renders with empty checkboxes,
    while leaving the developer's provider/model/web-search configuration in place
    so they don't have to redo the setup screen.
    """
    fresh = _default_session()
    for key in _PRESERVED_SETUP_KEYS:
        fresh[key] = session.get(key)
    return fresh


# ---------------------------------------------------------------------------
# Working directory loader
# ---------------------------------------------------------------------------


def _catalog_from_features(ai_features: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct a minimal ai_catalog dict from ai_features for compatibility."""
    entries = [
        {
            "name": f.get("name", ""),
            "scope": f.get("scope", "feature"),
            "rough_description": f.get("rough_description", ""),
            "tier_recommendation": f.get("tier_recommendation", ""),
            "tier_decision": f.get("tier", ""),
            "tier_decision_rationale": f.get("tier_decision_rationale", ""),
        }
        for f in (ai_features.get("ai_features") or [])
    ]
    return {"ai_catalog": entries}


def _load_working_dir(path: str, session: dict[str, Any]) -> dict[str, Any]:
    """Build a session dict for the given working directory, loading .spec4/ artifacts.

    Selecting a working directory in the browser starts work on a (potentially
    different) project, so every project-specific field is cleared — chat
    history, all `{agent}_messages` LLM logs, agent states, artifacts, the
    Deployer plan flags, staleness acknowledgements, resume snapshots, the
    active agent selection, and UI display flags. Only the developer's LLM
    connection (`_PRESERVED_SETUP_KEYS`: provider/model/api_key/available_models/
    llm_config plus the web-search provider and key) is carried over, so a
    configured developer who
    picks a different directory isn't sent back through /setup. Callers route
    to /setup or /agents based on the resulting llm_config.
    """
    session = _reset_for_new_project(session)
    session.update(
        {
            "working_dir": path,
            "browser_path": path,
            "phase": "setup",
            "code_scanner_resumed": False,
            "brainstormer_resumed": False,
            "stack_advisor_resumed": False,
            "deployer_resumed": False,
            "code_scanner_artifact_msg_count": None,
            "brainstormer_artifact_msg_count": None,
            "stack_advisor_artifact_msg_count": None,
            "deployer_artifact_msg_count": None,
            "agentifier_scout_pool": None,
            "agentifier_breadth_chosen": False,
            "agentifier_breadth_groups": None,
            "agentifier_breadth_intro": None,
            "agentifier_breadth_selection": None,
            "agentifier_explicitly_rejected": None,
            "agentifier_candidates": None,
            "agentifier_analyses": None,
            "agentifier_catalog_done": False,
            "agentifier_spec_index": 0,
            "agentifier_spec_results": [],
            "agentifier_spec_done": False,
            "agentifier_cross_cutting_analysis": None,
            "agentifier_cross_cutting_topics": [],
            "agentifier_cross_cutting_index": 0,
            "agentifier_cross_cutting_decisions": {},
            "agentifier_cross_cutting_done": False,
            "agentifier_priority_done": False,
            "ai_features": None,
        }
    )
    try:
        artifacts = project_manager.load_spec4_artifacts(path)
    except Exception:
        artifacts = {}
    # A pending brownfield round (the highest .spec4/v{N}/ holds an IMPLEMENTED
    # marker, so the active round is v{N+1}) starts blank on technical artifacts.
    # The prior round's vision/stack/phases/code_review/ai_features/deployment
    # plan are completed plans, superseded by the fresh CodeScanner review the
    # new round is Required to produce first; hydrating them as active/COMPLETE
    # would let the persist funnel copy stale v{N} content into v{N+1} and would
    # pin phase_version to the old round. Only the prior product name is carried,
    # as read-only reference for the agent-select prompt; phase_version stays
    # None so the funnel resolves the new round's version.
    new_round = project_manager.brownfield_new_round_pending(path)
    if new_round:
        session["_prior_app_name"] = (artifacts.get("vision") or {}).get("name")
        artifacts = {}
    if artifacts.get("vision"):
        session["vision_statement"] = artifacts["vision"]
        session["brainstormer_state"] = STATE_VISION_COMPLETE
    if artifacts.get("feature_specs"):
        session["feature_specs"] = artifacts["feature_specs"]
    if artifacts.get("stack"):
        session["stack_statement"] = artifacts["stack"]
        session["stack_advisor_state"] = STATE_STACK_COMPLETE
    if artifacts.get("phases"):
        session["phases"] = artifacts["phases"]
        session["phase_version"] = artifacts.get("phase_version")
        session["phaser_state"] = STATE_PHASES_COMPLETE
    if artifacts.get("code_review"):
        session["code_review"] = artifacts["code_review"]
        session["code_scanner_state"] = STATE_REVIEW_COMPLETE
    ai_features = None if new_round else project_manager.load_ai_features(path)
    if ai_features:
        session["ai_features"] = ai_features
        session["ai_catalog"] = _catalog_from_features(ai_features)
        session["agentifier_state"] = STATE_AGENTIFIER_COMPLETE
        session["agentifier_catalog_done"] = True
        session["agentifier_breadth_chosen"] = True
        session["agentifier_spec_done"] = True
        session["agentifier_cross_cutting_done"] = True
        session["agentifier_priority_done"] = True
    elif not new_round:
        ai_catalog = project_manager.load_ai_catalog(path)
        if ai_catalog:
            session["ai_catalog"] = ai_catalog
            session["agentifier_catalog_done"] = True
            # spec drafting not yet complete — keep STATE_IN_PROGRESS
    deployment_plan = (
        None if new_round else project_manager.load_deployment_plan(path)
    )
    if deployment_plan:
        session["deployer_state"] = STATE_DEPLOYER_COMPLETE
    session["_deployer_plan_existed"] = bool(deployment_plan)
    session["_deployer_plan_markdown"] = None
    session["_deployer_pending_plan"] = False
    session["_deployer_pending_readme"] = False
    session["_deployer_generating_readme"] = False
    session["_deployer_readme_markdown"] = None
    # D-PM1: picking a directory re-opens the question. `_reset_for_new_project`
    # above already restored the default, but state it here too so the intent
    # survives a future refactor of that helper. Whether the directory is
    # occupied is read from disk at render time (project_manager.
    # directory_has_content) rather than cached here, so it cannot go stale
    # against a directory the developer edits mid-session.
    session["project_mode"] = None
    return session


# ---------------------------------------------------------------------------
# Agent execution helpers
# ---------------------------------------------------------------------------


def _validate_agent_preconditions(agent: str, session: dict[str, Any]) -> str | None:
    """Return an error message if agent prerequisites are missing, else None."""
    has_vision = session.get("vision_statement") is not None
    has_stack = session.get("stack_statement") is not None
    has_phases = bool(session.get("phases"))
    _vision_required = ("agentifier", "stack_advisor", "phaser", "designer")
    if agent in _vision_required and not has_vision:
        return (
            "Requires a vision statement. "
            "Please use Brainstormer to create a vision first."
        )
    if agent == "phaser" and not has_stack:
        return "Requires a stack spec. Load or generate a stack.json first."
    if agent == "deployer" and not has_phases:
        return "Requires phases. Run Phaser first to generate the development phases."
    # Phaser hands the mock to the coding agent, so a mock that predates the
    # current vision/AI features would be baked into the phases. StackAdvisor is
    # deliberately *not* gated here: per D-SC5c it consumes Designer's
    # `manifest.json`, not the visual mock, and a purely visual change cannot
    # invalidate a stack choice. Gating it here also diverged from
    # `agent_button_state`, which renders StackAdvisor as an enabled
    # `needs_update` button — the click was silently refused (D-BB1).
    if agent == "phaser":
        wd = session.get("working_dir")
        if wd and project_manager.detect_stale_inputs(wd, "designer"):
            return (
                "The UI mock is out of date — the vision or AI features changed "
                "after it was generated. Regenerate the Designer mock first."
            )
    return None


_DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"


# Opening message for the chat status line, per agent. Deliberately generic —
# it covers the provider prefill before the first stage-specific status lands.
_AGENT_STATUS_SEED: dict[str, str] = {
    "code_scanner": "CodeScanner is examining your codebase…",
    "brainstormer": "Brainstormer is thinking…",
    "agentifier": "Agentifier is working…",
    "stack_advisor": "StackAdvisor is thinking…",
    "phaser": "Phaser is planning your development phases…",
    "deployer": "Deployer is preparing your deployment plan…",
}


def _get_agent_gen(
    user_input: str | None, session: dict[str, Any]
) -> Generator[str, None, None]:
    """Return the generator for one agent turn without starting it.

    The single point where an agent's model is decided. ``llm_selection.resolve``
    picks the agent's own override or the session default, and the result is
    handed to ``run()`` — which threads it down to every sub-agent unchanged.
    That is why a per-agent choice needs no sub-agent to know about it, and why
    the Agentifier's Fast Forward sweeps can run N sub-agent calls back to back
    without an interactive step landing inside one.
    """
    active = session["active_agent"]
    llm_config = llm_selection.resolve(session, active)

    # Seed the status line before the generator runs: every stream-starting
    # callback spreads this session into the store after calling here, so the
    # seed shows the moment the turn begins — agents then overwrite it with
    # stage-specific text on the same (live) dict as they work.
    session["_stream_status"] = _AGENT_STATUS_SEED.get(active, "Working…")

    if _DEV_MODE:
        agent_msgs = session.get(f"{active}_messages") or []
        ui = "None" if user_input is None else f"str(len={len(user_input)})"
        cfg = llm_config or {}
        print(
            f"[agent-gen] active={active!r} user_input={ui} "
            f"{active}_messages_len={len(agent_msgs)} "
            f"has_vision={session.get('vision_statement') is not None} "
            f"has_stack={session.get('stack_statement') is not None} "
            f"has_phases={bool(session.get('phases'))} "
            f"has_code_review={session.get('code_review') is not None} "
            f"llm_config_model={cfg.get('model')!r} "
            f"api_key_set={bool(cfg.get('api_key'))}",
            flush=True,
        )

    if active == "code_scanner":
        gen: Generator[str, None, None] = code_scanner.run(
            user_input, session, llm_config
        )
    elif active == "brainstormer":
        gen = brainstormer.run(user_input, session, llm_config)
    elif active == "agentifier":
        from spec4.agentifier.agentifier import run as _agentifier_run
        gen = _agentifier_run(user_input, session, llm_config)
    elif active == "stack_advisor":
        gen = stack_advisor.run(user_input, session, llm_config)
    elif active == "phaser":
        gen = phaser.run(user_input, session, llm_config)
    elif active == "deployer":
        gen = deployer.run(user_input, session, llm_config)
    else:
        raise ValueError(f"Unknown agent: {active!r}")

    if not _DEV_MODE:
        return gen
    return _trace_gen(active, gen)


def _trace_gen(
    label: str, gen: Generator[str, None, None]
) -> Generator[str, None, None]:
    """Wrap an agent generator with first-yield / first-chunk / completion logging."""
    print(f"[agent-gen] {label}: iteration starting", flush=True)
    yielded = 0
    try:
        for chunk in gen:
            yielded += 1
            if yielded == 1:
                preview = chunk[:80]
                print(
                    f"[agent-gen] {label}: first chunk "
                    f"(len={len(chunk)}): {preview!r}",
                    flush=True,
                )
            yield chunk
    finally:
        print(f"[agent-gen] {label}: iteration ended (yielded={yielded})", flush=True)


def _run_agent_blocking(user_input: str | None, session: dict[str, Any]) -> str:
    """Run one agent turn synchronously, returning the full response text."""
    return "".join(_get_agent_gen(user_input, session))


def _turn_was_fast_forward(session: dict[str, Any]) -> bool:
    """Whether the turn being persisted was started by the Fast Forward button.

    Fast Forward has no session flag of its own: the button appends the
    ``FF_PROMPT`` text as the user message and streams the reply. So the turn
    is FF exactly when the most recent user message is that prompt.
    """
    messages = session.get("messages") or []
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return bool(msg.get("content") == FF_PROMPT)
    return False


def _summarize_turn_usage(
    agent: Any, records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Token readout for one finished turn, from its per-call usage records.

    ``{"agent", "input", "output", "calls", "missing"}`` for the chat row's
    token element: summed provider-reported input/output tokens over the
    turn's calls (a turn can make several — tool rounds, re-asks, sub-agents),
    ``calls`` counting every call and ``missing`` those that returned no
    usage. Pure and JSON-serialisable for the session store.

    A turn with no records still returns a summary, with ``calls`` zero, rather
    than None. Both clear the previous turn's numbers, but the zero summary
    says so on screen instead of rendering nothing — and rendering nothing is
    exactly what a broken capture path looks like, which is how a double-drain
    regression once hid in plain sight. Absent ``_turn_usage`` (no turn has
    finished yet) remains the only silent state.
    """
    summary: dict[str, Any] = {
        "agent": agent,
        "input": 0,
        "output": 0,
        "calls": 0,
        "missing": 0,
    }
    for rec in records:
        summary["calls"] += 1
        if rec.get("usage_missing"):
            summary["missing"] += 1
        for src, dst in (("prompt_tokens", "input"), ("completion_tokens", "output")):
            value = rec.get(src)
            if isinstance(value, int) and not isinstance(value, bool):
                summary[dst] += value
    return summary


def _persist_artifacts(session: dict[str, Any]) -> None:
    working_dir = session.get("working_dir")
    if not working_dir:
        return
    # Resolve the active version once at flow start and pin it in the session.
    # The first agent to persist an artifact fixes the version for the round;
    # every artifact below is then written under .spec4/v{version}/. A returning
    # user loads phase_version from the latest round; starting a new round resets
    # it to None (separate start-page flow), which re-resolves to max+1 here.
    if session.get("phase_version") is None:
        version, _ = project_manager.resolve_phase_version(
            working_dir, project_manager.session_is_brownfield(session)
        )
        session["phase_version"] = version
    version = session["phase_version"]
    # LLM usage for the turn that just finished. Flushed here, after the pin,
    # so the first turn of a new round lands under the new version. Isolated
    # from the artifact saves below: a usage write failure must never cost a
    # vision or stack save, and vice versa.
    usage_records = llm.drain_usage_records()
    try:
        project_manager.save_usage(
            working_dir,
            usage_records,
            version,
            fast_forward=_turn_was_fast_forward(session),
        )
    except Exception as exc:
        print(f"[usage] save failed ({type(exc).__name__}: {exc})", flush=True)
    # The finished turn's token readout for the chat row (layouts._chat
    # renders it next to the chars counter once the stream has completed).
    # Replaced every turn, cleared when the turn made no call.
    session["_turn_usage"] = _summarize_turn_usage(
        session.get("active_agent"), usage_records
    )
    if session.get("code_scanner_state") == STATE_REVIEW_COMPLETE and session.get(
        "code_review"
    ):
        project_manager.save_code_review(working_dir, session["code_review"], version)
    if session.get("brainstormer_state") == STATE_VISION_COMPLETE and session.get(
        "vision_statement"
    ):
        project_manager.save_vision(working_dir, session["vision_statement"], version)
    if session.get("brainstormer_state") == STATE_VISION_COMPLETE and session.get(
        "feature_specs"
    ):
        project_manager.save_feature_specs(
            working_dir, session["feature_specs"], version
        )
    if session.get("agentifier_catalog_done") and session.get("ai_catalog"):
        project_manager.save_ai_catalog(working_dir, session["ai_catalog"], version)
    if session.get("agentifier_state") == STATE_AGENTIFIER_COMPLETE and session.get(
        "ai_features"
    ):
        project_manager.save_ai_features(working_dir, session["ai_features"], version)
    if session.get("stack_advisor_state") == STATE_STACK_COMPLETE and session.get(
        "stack_statement"
    ):
        project_manager.save_stack(working_dir, session["stack_statement"], version)
    if session.get("phaser_state") == STATE_PHASES_COMPLETE and session.get("phases"):
        project_manager.save_phases(
            working_dir,
            session["phases"],
            version,
            {
                "ai_features": session.get("ai_features"),
                # D-PH3/D-PH4: the render-time stack routing and NFR threading
                # joins read these; absent keys render nothing (older sessions).
                "feature_specs": session.get("feature_specs"),
                "stack": session.get("stack_statement"),
                # D-PH5: the per-phase UI-surface attach reads the finalized
                # design manifest; None (no design round) renders nothing.
                "manifest": project_manager.load_design_manifest(
                    working_dir, version
                ),
            },
        )
    if session.get("deployer_state") == STATE_DEPLOYER_COMPLETE:
        # Only save when the agent has explicitly produced a fresh plan in this
        # session. _deployer_plan_markdown is set by deployer.run() the moment a
        # response containing "## Deployment Steps" arrives, and only after the
        # confirmation prompt (when an existing plan is on disk) has been
        # resolved with an affirmative reply. This prevents a returning user
        # whose deployer_state was lifted to COMPLETE by _load_working_dir from
        # silently overwriting the on-disk plan with whatever the last assistant
        # message happens to be (a greeting, a "no" acknowledgement, etc).
        md = session.get("_deployer_plan_markdown") or ""
        if md and "## Deployment Steps" in md:
            project_manager.save_deployment_plan(working_dir, md, version)
            session["_deployer_plan_existed"] = True
            session["_deployer_plan_markdown"] = None
        # README is a project-root artifact (not version-scoped). It is staged
        # only after the deployment plan is complete, when the developer accepts
        # the README offer and the model authors it in a follow-up turn.
        readme_md = session.get("_deployer_readme_markdown") or ""
        if readme_md.strip():
            project_manager.save_readme(working_dir, readme_md)
            session["_deployer_readme_markdown"] = None
