"""Adding a feature in Agentifier marks downstream stale AND re-seeds its content."""
from __future__ import annotations

import time
from pathlib import Path

from spec4 import project_manager as pm
from spec4.agents import _utils


def _make_project(tmp_path: Path) -> str:
    v0 = tmp_path / ".spec4" / "v0"
    (v0 / "phases").mkdir(parents=True)
    # Downstream outputs written first (older)
    (v0 / "stack.json").write_text("{}")
    (v0 / "phases" / "phase1.md").write_text("x")
    (v0 / "deployment-plan.md").write_text("x")
    time.sleep(0.05)
    # ai_features.json updated last (newest) — simulates adding a feature
    (v0 / "ai_features.json").write_text("{}")
    return str(tmp_path)


def test_ai_features_change_flags_all_downstream(tmp_path):
    d = _make_project(tmp_path)
    for agent in ("stack_advisor", "phaser", "deployer"):
        stale = pm.detect_stale_inputs(d, agent)
        assert "AI features" in stale, f"{agent} did not flag AI features"


def test_revision_context_includes_ai_features(tmp_path):
    session = {
        "working_dir": str(tmp_path),
        "ai_features": {"ai_features": [{"name": "shopping_list_generation",
                                         "tier": "deterministic"}]},
    }
    ctx = _utils._build_revision_context(session, ["AI features"])
    assert "Updated AI features spec" in ctx
    assert "shopping_list_generation" in ctx


def test_revision_context_skips_ai_features_when_not_stale(tmp_path):
    session = {"working_dir": str(tmp_path),
               "ai_features": {"ai_features": [{"name": "x"}]}}
    ctx = _utils._build_revision_context(session, ["vision"])
    assert "Updated AI features spec" not in ctx


# --- D-DS15: designer mock staleness + downstream hard-block ------------------

from spec4.session import _validate_agent_preconditions  # noqa: E402


def _designer_project(tmp_path: Path, newer: str | None) -> str:
    v0 = tmp_path / ".spec4" / "v0"
    (v0 / "design").mkdir(parents=True)
    (v0 / "vision.json").write_text("{}")
    (v0 / "ai_features.json").write_text("{}")
    (v0 / "design" / "mock.html").write_text("<html></html>")  # newest initially
    if newer:
        time.sleep(0.05)
        (v0 / newer).write_text("{}")  # now newer than the mock -> stale
    return str(tmp_path)


def test_designer_flags_ai_features_change(tmp_path):
    d = _designer_project(tmp_path, "ai_features.json")
    assert "AI features" in pm.detect_stale_inputs(d, "designer")


def test_designer_flags_vision_change(tmp_path):
    d = _designer_project(tmp_path, "vision.json")
    assert "vision" in pm.detect_stale_inputs(d, "designer")


def test_designer_fresh_when_mock_newest(tmp_path):
    d = _designer_project(tmp_path, None)
    assert pm.detect_stale_inputs(d, "designer") == {}


def test_stale_mock_blocks_phaser(tmp_path):
    d = _designer_project(tmp_path, "ai_features.json")
    session = {
        "working_dir": d,
        "vision_statement": {"x": 1},
        "stack_statement": {"y": 1},
    }
    msg = _validate_agent_preconditions("phaser", session)
    assert msg and "out of date" in msg


def test_stale_mock_allows_stack_advisor(tmp_path):
    """D-SC5c: StackAdvisor consumes the design *manifest*, not the mock, so a
    stale mock must not block it. Gating it here also diverged from
    `agent_button_state`, which renders it as an enabled `needs_update` button
    (D-BB1)."""
    d = _designer_project(tmp_path, "ai_features.json")
    session = {
        "working_dir": d,
        "vision_statement": {"x": 1},
        "stack_statement": {"y": 1},
    }
    assert _validate_agent_preconditions("stack_advisor", session) is None


def test_fresh_mock_allows_downstream(tmp_path):
    d = _designer_project(tmp_path, None)
    session = {
        "working_dir": d,
        "vision_statement": {"x": 1},
        "stack_statement": {"y": 1},
    }
    for agent in ("stack_advisor", "phaser"):
        assert _validate_agent_preconditions(agent, session) is None
