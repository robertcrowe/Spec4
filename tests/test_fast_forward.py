"""Fast Forward buttons for StackAdvisor, Agentifier, Phaser, and Deployer.

One button per conversational agent, always enabled, injecting the
developer's proven sweep prompt
verbatim as a user message — byte-identical to typing it, in both the display
transcript and the agent history, so draws made with the button remain
shape-comparable with draws made by typing the prompt. No markers, no
classification, no conditional greying: the review turn at the end is the
safety mechanism, as validated across live draws.
"""

from typing import Any
from unittest.mock import patch

from spec4.callbacks import FF_PROMPT, on_fast_forward, on_ff_info
from spec4.layouts._chat import _chat_action_buttons


def _find_component(component: Any, comp_id: str) -> Any:
    """Depth-first search for a dash component with the given id."""
    if getattr(component, "id", None) == comp_id:
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        found = _find_component(child, comp_id)
        if found is not None:
            return found
    return None


class TestFastForwardPrompt:
    def test_prompt_is_the_validated_sweep_instruction(self) -> None:
        assert FF_PROMPT == (
            "For this and all of the remaining topics please create a "
            "comprehensive set of recommendations, which I will review and "
            "potentially modify as a whole before finalizing."
        )


FF_AGENTS = ("stack_advisor", "agentifier", "phaser", "deployer")

# Minimal extra session state each agent needs for the FF button to render
# pre-complete. Agentifier gates on the breadth panel having completed.
FF_PRECONDITIONS: dict[str, dict[str, Any]] = {
    "stack_advisor": {},
    "agentifier": {"agentifier_breadth_chosen": True},
    "phaser": {},
    "deployer": {},
}


def _pre_complete_session(agent: str) -> dict[str, Any]:
    return {"active_agent": agent, **FF_PRECONDITIONS[agent]}


def _complete_session(agent: str) -> dict[str, Any]:
    from spec4.app_constants import (
        STATE_AGENTIFIER_COMPLETE,
        STATE_DEPLOYER_COMPLETE,
        STATE_STACK_COMPLETE,
    )

    completion: dict[str, dict[str, Any]] = {
        "stack_advisor": {"stack_advisor_state": STATE_STACK_COMPLETE},
        "agentifier": {"agentifier_state": STATE_AGENTIFIER_COMPLETE},
        "phaser": {"phases": [{"phase": 1}]},
        "deployer": {"deployer_state": STATE_DEPLOYER_COMPLETE},
    }
    return {"active_agent": agent, **completion[agent]}


class TestFastForwardButton:
    def test_button_present_and_enabled_pre_complete(self) -> None:
        for agent in FF_AGENTS:
            div = _chat_action_buttons(_pre_complete_session(agent))
            btn = _find_component(div, "btn-chat-fast-forward")
            assert btn is not None, agent
            assert not getattr(btn, "disabled", False), agent

    def test_button_absent_when_agent_complete(self) -> None:
        for agent in FF_AGENTS:
            div = _chat_action_buttons(_complete_session(agent))
            assert _find_component(div, "btn-chat-fast-forward") is None, agent

    def test_button_absent_for_non_ff_agents(self) -> None:
        for agent in ("brainstormer", "code_scanner"):
            div = _chat_action_buttons({"active_agent": agent})
            assert _find_component(div, "btn-chat-fast-forward") is None, agent


class TestOnFastForward:
    def _session(self, **extra: Any) -> dict[str, Any]:
        return {
            "active_agent": "stack_advisor",
            "llm_config": {"model": "gpt-4o", "api_key": "sk-test"},
            "messages": [{"role": "assistant", "content": "Topic 1?"}],
            **extra,
        }

    def test_click_injects_prompt_verbatim(self) -> None:
        session = self._session()
        with patch(
            "spec4.session.stack_advisor.run", return_value=iter(["ok"])
        ) as mock_run, patch(
            "spec4.callbacks.streaming.start", return_value="sid"
        ):
            new_session, _ = on_fast_forward(1, session)
        # Agent history and display transcript both receive the exact prompt.
        _, call_args, _ = mock_run.mock_calls[0]
        assert call_args[0] == FF_PROMPT
        user_msgs = [m for m in new_session["messages"] if m["role"] == "user"]
        assert user_msgs[-1]["content"] == FF_PROMPT

    def test_click_starts_stream(self) -> None:
        session = self._session()
        with patch(
            "spec4.session.stack_advisor.run", return_value=iter(["ok"])
        ), patch("spec4.callbacks.streaming.start", return_value="sid"):
            new_session, max_intervals = on_fast_forward(1, session)
        assert new_session["_stream_id"] == "sid"
        assert max_intervals == -1

    def test_noop_without_click(self) -> None:
        session = self._session()
        with patch("spec4.session.stack_advisor.run") as mock_run:
            on_fast_forward(0, session)
        mock_run.assert_not_called()

    def test_noop_while_stream_in_flight(self) -> None:
        """Turn-integrity guard: a click during an active stream does nothing."""
        session = self._session(_stream_id="live")
        with patch("spec4.session.stack_advisor.run") as mock_run:
            on_fast_forward(1, session)
        mock_run.assert_not_called()


class TestAgentifierGate:
    """FF appears for Agentifier only after the breadth panel completes."""

    def test_hidden_before_panel_appears(self) -> None:
        div = _chat_action_buttons({"active_agent": "agentifier"})
        assert _find_component(div, "btn-chat-fast-forward") is None

    def test_hidden_while_panel_pending(self) -> None:
        div = _chat_action_buttons(
            {
                "active_agent": "agentifier",
                "agentifier_breadth_groups": [{"id": "x", "name": "X"}],
                "agentifier_breadth_chosen": False,
            }
        )
        assert _find_component(div, "btn-chat-fast-forward") is None

    def test_shown_after_panel_submitted(self) -> None:
        div = _chat_action_buttons(
            {"active_agent": "agentifier", "agentifier_breadth_chosen": True}
        )
        assert _find_component(div, "btn-chat-fast-forward") is not None

    def test_shown_on_resume_past_catalog(self) -> None:
        """A reloaded session that skips the panel still gets the button."""
        div = _chat_action_buttons(
            {"active_agent": "agentifier", "agentifier_catalog_done": True}
        )
        assert _find_component(div, "btn-chat-fast-forward") is not None


class TestFastForwardInfo:
    """The (i) icon and its explanatory dialog, per agent."""

    def test_info_icon_and_modal_present_pre_complete(self) -> None:
        for agent in FF_AGENTS:
            div = _chat_action_buttons(_pre_complete_session(agent))
            assert _find_component(div, "btn-ff-info") is not None, agent
            modal = _find_component(div, "ff-info-modal")
            assert modal is not None, agent
            assert modal.opened is False, agent

    def test_modal_text_names_agent_and_explains_review(self) -> None:
        """The dialog names the active agent and tells the user they
        review the full recommendation set before finalizing."""
        labels = {
            "stack_advisor": "StackAdvisor",
            "agentifier": "Agentifier",
            "phaser": "Phaser",
            "deployer": "Deployer",
        }
        for agent, label in labels.items():
            modal = _find_component(
                _chat_action_buttons(_pre_complete_session(agent)), "ff-info-modal"
            )
            text = str(getattr(modal, "children", ""))
            assert label in text, agent
            assert "review" in text.lower(), agent
            assert "recommendation" in text.lower(), agent

    def test_icon_and_modal_absent_when_agent_complete(self) -> None:
        for agent in FF_AGENTS:
            div = _chat_action_buttons(_complete_session(agent))
            assert _find_component(div, "btn-ff-info") is None, agent
            assert _find_component(div, "ff-info-modal") is None, agent

    def test_icon_absent_for_non_ff_agents(self) -> None:
        for agent in ("brainstormer", "code_scanner"):
            div = _chat_action_buttons({"active_agent": agent})
            assert _find_component(div, "btn-ff-info") is None, agent

    def test_click_opens_modal(self) -> None:
        assert on_ff_info(1) is True

    def test_no_click_is_noop(self) -> None:
        from dash import no_update

        assert on_ff_info(0) is no_update
