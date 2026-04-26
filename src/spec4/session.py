from __future__ import annotations

import pathlib
from typing import Any

from spec4 import project_manager, providers, tavily_mcp  # noqa: F401 — providers kept for symmetry
from spec4.agents import brainstormer, phaser, reviewer, stack_advisor


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
        "reviewer_state": "in_progress",
        "reviewer_messages": [],
        "code_review": None,
        "brainstormer_state": "in_progress",
        "brainstormer_messages": [],
        "vision_statement": None,
        "stack_advisor_messages": [],
        "stack_advisor_state": "in_progress",
        "stack_statement": None,
        "phaser_state": None,
        "phaser_messages": [],
        "phases": [],
        "_warn_existing_content": False,
        "_dir_has_content": False,
        "_initial_turn_done": False,
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
        "brainstormer_state": "in_progress",
        "stack_statement": None,
        "stack_advisor_state": "in_progress",
        "phases": [],
        "phaser_state": None,
        "code_review": None,
        "reviewer_state": "in_progress",
        "specmem": None,
        "_warn_existing_content": False,
    }
    try:
        artifacts = project_manager.load_spec4_artifacts(path)
    except Exception:
        artifacts = {}
    if artifacts.get("vision"):
        session["vision_statement"] = artifacts["vision"]
        session["brainstormer_state"] = "vision_complete"
    if artifacts.get("stack"):
        session["stack_statement"] = artifacts["stack"]
        session["stack_advisor_state"] = "stack_complete"
    if artifacts.get("phases"):
        session["phases"] = artifacts["phases"]
        session["phaser_state"] = "phases_complete"
    if artifacts.get("code_review"):
        session["code_review"] = artifacts["code_review"]
        session["reviewer_state"] = "review_complete"
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


def _run_agent_blocking(user_input: str | None, session: dict[str, Any]) -> str:
    """Run one agent turn synchronously, returning the full response text."""
    llm_config = session["llm_config"]
    active = session["active_agent"]

    if active == "reviewer":
        gen = reviewer.run(user_input, session, llm_config)
    elif active == "brainstormer":
        gen = brainstormer.run(user_input, session, llm_config)
    elif active == "stack_advisor":
        gen = stack_advisor.run(user_input, session, llm_config)
    else:
        gen = phaser.run(user_input, session, llm_config)

    return "".join(gen)


def _persist_artifacts(session: dict[str, Any]) -> None:
    working_dir = session.get("working_dir")
    if not working_dir:
        return
    if session.get("reviewer_state") == "review_complete" and session.get(
        "code_review"
    ):
        project_manager.save_code_review(working_dir, session["code_review"])
    if session.get("brainstormer_state") == "vision_complete" and session.get(
        "vision_statement"
    ):
        project_manager.save_vision(working_dir, session["vision_statement"])
        project_manager.update_specmem_planning_state(working_dir, session)
    if session.get("stack_advisor_state") == "stack_complete" and session.get(
        "stack_statement"
    ):
        project_manager.save_stack(working_dir, session["stack_statement"])
        project_manager.update_specmem_planning_state(working_dir, session)
    if session.get("phaser_state") == "phases_complete" and session.get("phases"):
        project_manager.save_phases(working_dir, session["phases"])
        project_manager.update_specmem_planning_state(working_dir, session)
