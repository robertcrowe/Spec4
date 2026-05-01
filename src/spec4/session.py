from __future__ import annotations

import pathlib
from collections.abc import Generator
from typing import Any

from spec4 import project_manager
from spec4.agents import brainstormer, code_scanner, phaser, stack_advisor
from spec4.app_constants import (
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
    specmem = project_manager.read_specmem(path)
    if specmem:
        session["specmem"] = specmem
    root = pathlib.Path(path)
    try:
        has_content = any(
            True for item in root.iterdir() if not item.name.startswith(".")
        )
    except Exception:
        has_content = False
    session["_warn_existing_content"] = has_content and not artifacts.get("code_review")
    session["_dir_has_content"] = has_content
    return session


# ---------------------------------------------------------------------------
# Agent execution helpers
# ---------------------------------------------------------------------------


def _get_agent_gen(
    user_input: str | None, session: dict[str, Any]
) -> Generator[str, None, None]:
    """Return the generator for one agent turn without starting it."""
    llm_config = session["llm_config"]
    active = session["active_agent"]

    if active == "code_scanner":
        return code_scanner.run(user_input, session, llm_config)
    elif active == "brainstormer":
        return brainstormer.run(user_input, session, llm_config)
    elif active == "stack_advisor":
        return stack_advisor.run(user_input, session, llm_config)
    elif active == "phaser":
        return phaser.run(user_input, session, llm_config)
    else:
        raise ValueError(f"Unknown agent: {active!r}")


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
    if needs_specmem:
        project_manager.update_specmem_planning_state(working_dir, session)
