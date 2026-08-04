"""Deployer re-entry seeds the existing plan content (no 'paste it' loop)."""
from __future__ import annotations

from unittest.mock import patch

from spec4.agents import deployer


def test_reentry_seed_embeds_existing_plan():
    session = {
        "deployer_messages": [],
        "working_dir": "/tmp/proj",
        "_deployer_plan_existed": True,
        "stack_statement": None,
        "phases": [],
        "code_review": {},
        "ai_features": None,
    }
    with patch.object(
        deployer.project_manager, "load_deployment_plan",
        return_value="# Deploy\n## Deployment Steps\nUse Cloud Run.",
    ), patch.object(deployer.llm, "build_system_prompt", return_value=""), \
       patch.object(deployer.llm, "stream_turn", return_value=iter(())):
        list(deployer.run(None, session, {"model": "x"}))
    seed = session["deployer_messages"][0]["content"]
    # The actual plan text is in the seed, and the model is told not to ask for a paste.
    assert "Use Cloud Run." in seed
    assert "deployment-plan.md" in seed
    assert "do NOT ask the developer to paste" in seed


def test_reentry_seed_handles_missing_file_gracefully():
    session = {
        "deployer_messages": [],
        "working_dir": "/tmp/proj",
        "_deployer_plan_existed": True,
        "stack_statement": None,
        "phases": [],
        "code_review": {},
        "ai_features": None,
    }
    # Flag says a plan existed but the file can't be read now → no crash, no block.
    with (
        patch.object(  # noqa: E501
            deployer.project_manager, "load_deployment_plan", return_value=None
        ),
        patch.object(deployer.llm, "build_system_prompt", return_value=""),
        patch.object(deployer.llm, "stream_turn", return_value=iter(())),
    ):
        list(deployer.run(None, session, {"model": "x"}))
    seed = session["deployer_messages"][0]["content"]
    assert "1. Keep the existing plan as-is" in seed  # still offers the options
