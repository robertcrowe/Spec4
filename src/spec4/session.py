from __future__ import annotations

import os
import pathlib
from collections.abc import Generator
from typing import Any

from spec4 import project_manager
from spec4.agents import brainstormer, code_scanner, deployer, phaser, stack_advisor
from spec4.app_constants import (
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
        "specmem": None,
        "phase": "landing",
        "provider": None,
        "model": None,
        "api_key": None,
        "available_models": None,
        "tavily_api_key": None,
        "setup_error": None,
        "agent_select_error": None,
        "llm_config": None,
        "messages": [],
        "active_agent": "brainstormer",
        "code_scanner_state": STATE_IN_PROGRESS,
        "code_scanner_messages": [],
        "code_review": None,
        "brainstormer_state": STATE_IN_PROGRESS,
        "brainstormer_messages": [],
        "vision_statement": None,
        "stack_advisor_messages": [],
        "stack_advisor_state": STATE_IN_PROGRESS,
        "stack_statement": None,
        "phaser_state": None,
        "phaser_messages": [],
        "phases": [],
        "deployer_state": STATE_IN_PROGRESS,
        "deployer_messages": [],
        "_warn_existing_content": False,
        "_dir_has_content": False,
        "_initial_turn_done": False,
        "_stream_id": None,
    }


# ---------------------------------------------------------------------------
# Working directory loader
# ---------------------------------------------------------------------------


def _load_working_dir(path: str, session: dict[str, Any]) -> dict[str, Any]:
    """Build a session dict for the given working directory, loading .spec4/ artifacts."""  # noqa: E501
    session = {
        **session,
        "working_dir": path,
        "browser_path": path,
        "phase": "setup",
        "available_models": None,
        "model": None,
        "llm_config": None,
        "setup_error": None,
        "vision_statement": None,
        "brainstormer_state": STATE_IN_PROGRESS,
        "stack_statement": None,
        "stack_advisor_state": STATE_IN_PROGRESS,
        "phases": [],
        "phaser_state": None,
        "code_review": None,
        "code_scanner_state": STATE_IN_PROGRESS,
        "specmem": None,
        "deployer_state": STATE_IN_PROGRESS,
        "_warn_existing_content": False,
    }
    try:
        artifacts = project_manager.load_spec4_artifacts(path)
    except Exception:
        artifacts = {}
    if artifacts.get("vision"):
        session["vision_statement"] = artifacts["vision"]
        session["brainstormer_state"] = STATE_VISION_COMPLETE
    if artifacts.get("stack"):
        session["stack_statement"] = artifacts["stack"]
        session["stack_advisor_state"] = STATE_STACK_COMPLETE
    if artifacts.get("phases"):
        session["phases"] = artifacts["phases"]
        session["phaser_state"] = STATE_PHASES_COMPLETE
    if artifacts.get("code_review"):
        session["code_review"] = artifacts["code_review"]
        session["code_scanner_state"] = STATE_REVIEW_COMPLETE
    deployment_plan = project_manager.load_deployment_plan(path)
    if deployment_plan:
        session["deployer_state"] = STATE_DEPLOYER_COMPLETE
    specmem = project_manager.read_specmem(path)
    if specmem:
        session["specmem"] = specmem
    root = pathlib.Path(path)
    try:
        has_content = any(
            not item.name.startswith(".") for item in root.iterdir()
        )
    except Exception:
        has_content = False
    session["_warn_existing_content"] = has_content and not artifacts.get("code_review")
    session["_dir_has_content"] = has_content
    return session


# ---------------------------------------------------------------------------
# Agent execution helpers
# ---------------------------------------------------------------------------


def _validate_agent_preconditions(agent: str, session: dict[str, Any]) -> str | None:
    """Return an error message if agent prerequisites are missing, else None."""
    has_vision = session.get("vision_statement") is not None
    has_stack = session.get("stack_statement") is not None
    has_phases = bool(session.get("phases"))
    if agent in ("stack_advisor", "phaser") and not has_vision:
        return "Requires a vision statement. Load or generate a vision.json first."
    if agent == "phaser" and not has_stack:
        return "Requires a stack spec. Load or generate a stack.json first."
    if agent == "deployer" and not has_phases:
        return "Requires phases. Run Phaser first to generate the development phases."
    return None


_DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"


def _get_agent_gen(
    user_input: str | None, session: dict[str, Any]
) -> Generator[str, None, None]:
    """Return the generator for one agent turn without starting it."""
    llm_config = session["llm_config"]
    active = session["active_agent"]

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
            f"has_specmem={session.get('specmem') is not None} "
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


def _persist_artifacts(session: dict[str, Any]) -> None:
    working_dir = session.get("working_dir")
    if not working_dir:
        return
    if session.get("code_scanner_state") == STATE_REVIEW_COMPLETE and session.get(
        "code_review"
    ):
        project_manager.save_code_review(working_dir, session["code_review"])
    needs_specmem = False
    if session.get("brainstormer_state") == STATE_VISION_COMPLETE and session.get(
        "vision_statement"
    ):
        project_manager.save_vision(working_dir, session["vision_statement"])
        needs_specmem = True
    if session.get("stack_advisor_state") == STATE_STACK_COMPLETE and session.get(
        "stack_statement"
    ):
        project_manager.save_stack(working_dir, session["stack_statement"])
        needs_specmem = True
    if session.get("phaser_state") == STATE_PHASES_COMPLETE and session.get("phases"):
        project_manager.save_phases(working_dir, session["phases"])
        needs_specmem = True
    if session.get("deployer_state") == STATE_DEPLOYER_COMPLETE:
        messages = session.get("deployer_messages") or []
        md = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "assistant"),
            "",
        )
        if md:
            project_manager.save_deployment_plan(working_dir, md)
    if needs_specmem:
        project_manager.update_specmem_planning_state(working_dir, session)
