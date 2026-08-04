"""Unit tests for `on_agent_pill_click` (D-BB1 / D-BB2).

The /agents buttons are enabled by `project_manager.agent_button_state`, which
is a separate authority from `_validate_agent_preconditions` and can render a
button that the click callback then refuses. When that happens the reason must
reach `agent_select_error` — the /agents layout already renders it — rather
than being swallowed into a silent no-op.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

from dash import no_update

from spec4 import project_manager as pm
from spec4.callbacks import on_agent_pill_click


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeCtx:
    """Stand-in for dash.ctx carrying only the pattern-matching triggered id."""

    def __init__(self, agent: str) -> None:
        self.triggered_id = {"type": "agent-pill", "agent": agent}


def _click(agent: str, session: dict[str, Any]) -> Any:
    with patch("spec4.callbacks.ctx", _FakeCtx(agent)):
        return on_agent_pill_click([1], session)


def _stale_mock_project(tmp_path: Any) -> str:
    """Project whose mock predates the current vision and AI features.

    This is the state that renders Designer as `needs_update` on /agents.
    """
    v0 = tmp_path / ".spec4" / "v0"
    (v0 / "design").mkdir(parents=True)
    (v0 / "vision.json").write_text("{}")
    (v0 / "ai_features.json").write_text("{}")
    (v0 / "design" / "mock.html").write_text("<html></html>")
    (v0 / "design" / "manifest.json").write_text("{}")
    (v0 / "stack.json").write_text("{}")
    time.sleep(0.05)
    (v0 / "ai_features.json").write_text("{}")  # now newer than the mock
    return str(tmp_path)


def _session(working_dir: str) -> dict[str, Any]:
    return {
        "working_dir": working_dir,
        "phase": "agent_select",
        "vision_statement": {"x": 1},
        "stack_statement": {"y": 1},
        "agent_select_error": None,
    }


# ---------------------------------------------------------------------------
# D-BB1 — StackAdvisor is reachable with a stale mock
# ---------------------------------------------------------------------------


class TestStackAdvisorReachable:
    def test_button_and_click_agree(self, tmp_path: Any) -> None:
        """The reported bug: button rendered enabled, click did nothing."""
        d = _stale_mock_project(tmp_path)
        session = _session(d)

        assert pm.agent_button_state(d, "stack_advisor", session) == (
            pm.AGENT_BTN_NEEDS_UPDATE
        ), "precondition for the regression: the button renders enabled"

        new_session, pathname = _click("stack_advisor", session)

        assert pathname == "/chat"
        assert new_session["active_agent"] == "stack_advisor"
        assert new_session["agent_select_error"] is None

    def test_designer_still_reachable(self, tmp_path: Any) -> None:
        """Designer was never gated; narrowing the gate must not change it."""
        d = _stale_mock_project(tmp_path)
        new_session, pathname = _click("designer", _session(d))

        assert pathname == "/design"
        assert new_session["phase"] == "designer"


# ---------------------------------------------------------------------------
# D-BB2 — blocked clicks report a reason
# ---------------------------------------------------------------------------


class TestBlockedClickSurfacesError:
    def test_phaser_stale_mock_sets_error(self, tmp_path: Any) -> None:
        d = _stale_mock_project(tmp_path)
        new_session, pathname = _click("phaser", _session(d))

        assert pathname is no_update, "a blocked click must not navigate"
        assert new_session["agent_select_error"]
        assert "out of date" in new_session["agent_select_error"]

    def test_missing_vision_sets_error(self, tmp_path: Any) -> None:
        session = _session(str(tmp_path))
        session["vision_statement"] = None

        new_session, pathname = _click("agentifier", session)

        assert pathname is no_update
        assert "vision statement" in new_session["agent_select_error"]

    def test_error_clears_on_successful_navigation(self, tmp_path: Any) -> None:
        session = _session(str(tmp_path))
        session["agent_select_error"] = "previous error"

        new_session, pathname = _click("brainstormer", session)

        assert pathname == "/chat"
        assert new_session["agent_select_error"] is None

    def test_no_click_is_still_a_no_op(self, tmp_path: Any) -> None:
        """Callback fires on layout mount with n_clicks 0 — must not set an
        error before the user has clicked anything."""
        with patch("spec4.callbacks.ctx", _FakeCtx("phaser")):
            result = on_agent_pill_click([0], _session(str(tmp_path)))

        assert result == (no_update, no_update)


# ---------------------------------------------------------------------------
# Guard against re-divergence
# ---------------------------------------------------------------------------


class TestNoEnabledButtonIsRefused:
    def test_every_enabled_button_navigates(self, tmp_path: Any) -> None:
        """Any agent whose /agents button is not `not_ready` must be clickable.

        This is the invariant the reported bug violated. It is asserted rather
        than structurally enforced — `agent_button_state` consulting the
        preconditions directly is D-BB3, deferred.
        """
        d = _stale_mock_project(tmp_path)
        session = _session(d)
        agents = (
            "code_scanner",
            "brainstormer",
            "agentifier",
            "designer",
            "stack_advisor",
            "phaser",
            "deployer",
        )
        refused = []
        for agent in agents:
            state = pm.agent_button_state(d, agent, session)
            if state == pm.AGENT_BTN_NOT_READY:
                continue
            _new_session, pathname = _click(agent, session)
            if pathname is no_update:
                refused.append(agent)

        assert not refused, (
            f"enabled buttons whose click was refused: {refused}"
        )
