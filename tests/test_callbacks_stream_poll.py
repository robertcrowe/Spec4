"""Unit tests for on_stream_poll stale-clobber fix and _breadth_panel value seeding."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from dash import no_update

from spec4.callbacks import on_stream_poll
from spec4.layouts._chat import (
    _breadth_panel,
    _chat_layout,
    _streamed_token_count,
)
from spec4.session import _default_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_with_stream(**overrides: Any) -> dict[str, Any]:
    s = _default_session()
    s["_stream_id"] = "aaaabbbb-0000-0000-0000-000000000000"
    s["messages"] = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": ""},
    ]
    s.update(overrides)
    return s


def _fake_stream_entry(text: str = "hello", done: bool = True) -> dict[str, Any]:
    agent_sess = _default_session()
    agent_sess["_display_override"] = None
    return {"text": text, "done": done, "session": agent_sess}


# ---------------------------------------------------------------------------
# on_stream_poll — missing-entry path
# ---------------------------------------------------------------------------


class TestStreamPollMissingEntry:
    def test_missing_entry_returns_no_update(self) -> None:
        """Entry missing means another poll already finalised — must not clobber."""
        session = _session_with_stream()

        with (
            patch("spec4.callbacks.streaming.get", return_value=None),
            patch("spec4.callbacks.streaming.pop") as mock_pop,
        ):
            result = on_stream_poll(1, session)

        assert result[0] is no_update, (
            "stale poll with missing stream entry must return no_update, "
            "not rebuild from stale session snapshot"
        )
        assert result[1] == 0
        mock_pop.assert_not_called()

    def test_missing_entry_does_not_return_session_dict(self) -> None:
        """Confirm the return value is not a dict (i.e. not a stale session rebuild)."""
        session = _session_with_stream()
        with patch("spec4.callbacks.streaming.get", return_value=None):
            result = on_stream_poll(1, session)
        assert not isinstance(result[0], dict), (
            "no_update sentinel must be returned, not a session dict"
        )

    def test_no_stream_id_returns_no_update_early(self) -> None:
        """Early-out when _stream_id is None/missing — existing behaviour."""
        session = _default_session()
        session["_stream_id"] = None
        with patch("spec4.callbacks.streaming.get") as mock_get:
            result = on_stream_poll(1, session)
        mock_get.assert_not_called()
        assert result[0] is no_update
        assert result[1] == 0


# ---------------------------------------------------------------------------
# on_stream_poll — pop-returns-None path (two polls race to done branch)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# on_stream_poll — normal done-branch (regression)
# ---------------------------------------------------------------------------


class TestStreamPollNormalDone:
    def test_normal_done_merges_agent_session(self) -> None:
        """Successful done branch must still merge the agent-mutated session."""
        session = _session_with_stream()
        agent_sess = _default_session()
        agent_sess["vision_statement"] = {"name": "TestApp"}
        agent_sess["_display_override"] = None
        done_entry = {"text": "final answer", "done": True, "session": agent_sess}

        with (
            patch("spec4.callbacks.streaming.get", return_value=done_entry),
            patch("spec4.callbacks._persist_artifacts", return_value=None),
        ):
            result = on_stream_poll(1, session)

        merged = result[0]
        assert isinstance(merged, dict), "done branch must return a merged session dict"
        assert merged.get("_stream_id") is None
        assert merged.get("vision_statement") == {"name": "TestApp"}
        assert result[1] == 0

    def test_normal_done_applies_display_override(self) -> None:
        """_display_override replaces the last chat message in the done branch."""
        session = _session_with_stream()
        agent_sess = _default_session()
        agent_sess["_display_override"] = "Override text from agent"
        done_entry = {"text": "raw stream text", "done": True, "session": agent_sess}

        with (
            patch("spec4.callbacks.streaming.get", return_value=done_entry),
            patch("spec4.callbacks._persist_artifacts", return_value=None),
        ):
            result = on_stream_poll(1, session)

        merged = result[0]
        assert isinstance(merged, dict)
        msgs = merged.get("messages", [])
        assert msgs[-1]["content"] == "Override text from agent"


# ---------------------------------------------------------------------------
# on_stream_poll — idempotent done-branch finalisation
# ---------------------------------------------------------------------------


class TestStreamPollDoneFinalisation:
    def test_done_branch_does_not_pop(self) -> None:
        """Done branch must read via get(), not pop() — eviction is now in start()."""
        session = _session_with_stream()
        done_entry = _fake_stream_entry("result text", done=True)

        with (
            patch("spec4.callbacks.streaming.get", return_value=done_entry),
            patch("spec4.callbacks._persist_artifacts", return_value=None),
            patch("spec4.callbacks.streaming.pop") as mock_pop,
        ):
            result = on_stream_poll(1, session)

        mock_pop.assert_not_called()
        assert isinstance(result[0], dict)
        assert result[0]["_stream_id"] is None
        assert result[1] == 0

    def test_two_done_polls_return_identical_terminal_store(self) -> None:
        """Two racing done-branch polls must produce byte-identical terminal stores."""
        agent_sess = _default_session()
        agent_sess["vision_statement"] = {"name": "TestApp"}
        agent_sess["_display_override"] = None
        done_entry = {"text": "final text", "done": True, "session": agent_sess}

        with (
            patch("spec4.callbacks.streaming.get", return_value=done_entry),
            patch("spec4.callbacks._persist_artifacts", return_value=None),
        ):
            result_a = on_stream_poll(1, _session_with_stream())
            result_b = on_stream_poll(1, _session_with_stream())

        assert isinstance(result_a[0], dict)
        assert isinstance(result_b[0], dict)
        assert result_a[0]["_stream_id"] is None
        assert result_b[0]["_stream_id"] is None
        assert result_a[0]["vision_statement"] == {"name": "TestApp"}
        assert result_b[0]["vision_statement"] == {"name": "TestApp"}
        assert result_a[0] == result_b[0], (
            "two racing done-branch polls must return identical terminal stores"
        )

    def test_persist_failure_still_finalises(self) -> None:
        """A persistence failure must never strand the chat (progress bar stuck)."""
        session = _session_with_stream()
        done_entry = _fake_stream_entry("text", done=True)

        with (
            patch("spec4.callbacks.streaming.get", return_value=done_entry),
            patch(
                "spec4.callbacks._persist_artifacts",
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = on_stream_poll(1, session)

        assert isinstance(result[0], dict), (
            "persist failure must not propagate — done branch must still return "
            "the terminal session"
        )
        assert result[0]["_stream_id"] is None


# ---------------------------------------------------------------------------
# _breadth_panel — CheckboxGroup value seeding
# ---------------------------------------------------------------------------


class TestBreadthPanelValueSeeding:
    def _make_session_with_groups(
        self, selection: list[str] | None = None
    ) -> dict[str, Any]:
        s = _default_session()
        s["agentifier_breadth_groups"] = [
            {"name": "feat_a", "description": "Feature A."},
            {"name": "feat_b", "description": "Feature B."},
        ]
        # Panel closure seeds the checkbox value from the pool; in production the
        # scout pool is always set alongside the groups. These candidates are
        # edge-free, so closure resolves each selection to itself.
        s["agentifier_scout_pool"] = [
            {"name": "feat_a"},
            {"name": "feat_b"},
        ]
        s["agentifier_breadth_chosen"] = False
        s["agentifier_breadth_selection"] = selection
        return s

    def _find_checkbox_group(self, component: Any) -> Any:
        """Walk the component tree to find the dmc.CheckboxGroup."""
        import dash_mantine_components as dmc
        if isinstance(component, dmc.CheckboxGroup):
            return component
        children = getattr(component, "children", None) or []
        if not isinstance(children, list):
            children = [children]
        for child in children:
            found = self._find_checkbox_group(child)
            if found is not None:
                return found
        return None

    def test_value_reflects_persisted_selection(self) -> None:
        session = self._make_session_with_groups(selection=["feat_a"])
        panel = _breadth_panel(session)
        assert panel is not None
        cg = self._find_checkbox_group(panel)
        assert cg is not None
        assert cg.value == ["feat_a"]

    def test_value_is_empty_when_selection_is_none(self) -> None:
        session = self._make_session_with_groups(selection=None)
        panel = _breadth_panel(session)
        assert panel is not None
        cg = self._find_checkbox_group(panel)
        assert cg is not None
        assert cg.value == []

    def test_value_is_empty_when_selection_is_empty_list(self) -> None:
        session = self._make_session_with_groups(selection=[])
        panel = _breadth_panel(session)
        assert panel is not None
        cg = self._find_checkbox_group(panel)
        assert cg is not None
        assert cg.value == []

    def test_panel_hidden_when_breadth_chosen(self) -> None:
        session = self._make_session_with_groups(selection=["feat_a"])
        session["agentifier_breadth_chosen"] = True
        assert _breadth_panel(session) is None

    def test_panel_hidden_when_no_groups(self) -> None:
        session = _default_session()
        assert _breadth_panel(session) is None

    def test_panel_hidden_when_streaming(self) -> None:
        # Clicking Continue starts a stream (sets _stream_id) before the backend
        # flips agentifier_breadth_chosen mid-stream. The panel must hide at once
        # rather than linger until that flag propagates on the next poll.
        session = self._make_session_with_groups(selection=["feat_a"])
        session["_stream_id"] = "sid-abc"
        assert _breadth_panel(session) is None

    def test_panel_is_dmc_paper_with_chat_bubble_class(self) -> None:
        """Fix 1: active panel must be a dmc.Paper with className chat-bubble-assistant."""  # noqa: E501
        import dash_mantine_components as dmc
        session = self._make_session_with_groups(selection=None)
        panel = _breadth_panel(session)
        assert panel is not None
        assert isinstance(panel, dmc.Paper), (
            "_breadth_panel must return a dmc.Paper, not an html.Div"
        )
        assert panel.className == "chat-bubble-assistant"

    def test_paper_still_contains_checkbox_group(self) -> None:
        """Existing recursive walker must still find the CheckboxGroup through Paper."""
        session = self._make_session_with_groups(selection=["feat_a"])
        panel = _breadth_panel(session)
        assert panel is not None
        cg = self._find_checkbox_group(panel)
        assert cg is not None, (
            "CheckboxGroup must be reachable through the Paper wrapper"
        )
        assert cg.value == ["feat_a"]


# ---------------------------------------------------------------------------
# _breadth_panel — checkbox text styling
# ---------------------------------------------------------------------------


class TestBreadthPanelCheckboxStyling:
    """Feature name and description read as ordinary chat text.

    Same colour (inherited from the .chat-bubble-assistant wrapper) and same
    size (md) as the surrounding chat. The name is bolded via <strong>; the
    description stays at normal weight.
    """

    def _checkboxes(self) -> list[Any]:
        session = _default_session()
        session["agentifier_breadth_groups"] = [
            {"name": "feat_a", "description": "Feature A."},
            {"name": "feat_b", "description": "Feature B."},
        ]
        session["agentifier_scout_pool"] = [{"name": "feat_a"}, {"name": "feat_b"}]
        session["agentifier_breadth_chosen"] = False
        session["agentifier_breadth_selection"] = None
        panel = _breadth_panel(session)
        assert panel is not None
        cg = TestBreadthPanelValueSeeding()._find_checkbox_group(panel)
        assert cg is not None
        return list(cg.children)

    def test_label_is_bolded_feature_name(self) -> None:
        from dash import html

        for cb, name in zip(self._checkboxes(), ["feat_a", "feat_b"]):
            assert isinstance(cb.label, html.Strong), (
                "feature name must be wrapped in <strong>"
            )
            assert cb.label.children == name

    def test_description_is_the_plain_candidate_description(self) -> None:
        for cb, desc in zip(self._checkboxes(), ["Feature A.", "Feature B."]):
            assert cb.description == desc

    def test_label_and_description_match_chat_text(self) -> None:
        for cb in self._checkboxes():
            for slot in ("label", "description"):
                assert cb.styles[slot]["fontSize"] == "var(--mantine-font-size-md)"
                assert cb.styles[slot]["color"] == "inherit", (
                    f"{slot} must inherit the chat bubble's text colour"
                )

    def test_description_is_normal_weight(self) -> None:
        for cb in self._checkboxes():
            assert cb.styles["description"]["fontWeight"] == 400, (
                "description must not inherit the label's bold weight"
            )

    def test_label_carries_no_inline_font_weight(self) -> None:
        """Weight belongs to <strong>, not to the label style slot."""
        for cb in self._checkboxes():
            assert "fontWeight" not in cb.styles["label"]


# ---------------------------------------------------------------------------
# _chat_layout — Fix 2: input row visibility tied to breadth panel
# ---------------------------------------------------------------------------


def _make_active_breadth_session() -> dict[str, Any]:
    s = _default_session()
    s["agentifier_breadth_groups"] = [
        {"name": "feat_a", "description": "Feature A."},
    ]
    s["agentifier_breadth_chosen"] = False
    s["agentifier_breadth_selection"] = None
    return s


def _find_component(root: Any, predicate: Any) -> Any:
    """Recursive tree walk; returns first component where predicate(c) is True."""
    if predicate(root):
        return root
    children = getattr(root, "children", None) or []
    if not isinstance(children, list):
        children = [children]
    for child in children:
        found = _find_component(child, predicate)
        if found is not None:
            return found
    return None


class TestChatLayoutInputVisibility:
    def _find_input_row(self, layout: Any) -> Any:
        """Find the html.Div that directly contains chat-input Textarea."""
        from dash import html
        import dash_mantine_components as dmc

        def _is_input_row(c: Any) -> bool:
            if not isinstance(c, html.Div):
                return False
            children = c.children or []
            if not isinstance(children, list):
                return False
            return any(
                isinstance(ch, dmc.Textarea) and getattr(ch, "id", None) == "chat-input"
                for ch in children
            )

        return _find_component(layout, _is_input_row)

    def test_input_row_hidden_when_breadth_active(self) -> None:
        session = _make_active_breadth_session()
        layout = _chat_layout(session)
        row = self._find_input_row(layout)
        assert row is not None, "input row must still be in the tree (mounted)"
        assert row.style["display"] == "none", (
            "input row must be hidden (display:none) while breadth panel is active"
        )

    def test_chat_input_present_when_breadth_active(self) -> None:
        """Textarea must be mounted even when hidden — State reference must be valid."""
        import dash_mantine_components as dmc
        session = _make_active_breadth_session()
        layout = _chat_layout(session)
        def _is_chat_input(c: Any) -> bool:
            return (
                isinstance(c, dmc.Textarea) and getattr(c, "id", None) == "chat-input"
            )

        textarea = _find_component(layout, _is_chat_input)
        assert textarea is not None, "chat-input Textarea must be present in the tree"

    def test_input_row_visible_when_breadth_inactive(self) -> None:
        session = _default_session()
        layout = _chat_layout(session)
        row = self._find_input_row(layout)
        assert row is not None
        assert row.style["display"] == "flex", (
            "input row must be flex when no breadth panel is active"
        )

    def test_input_row_visible_when_breadth_chosen(self) -> None:
        session = _make_active_breadth_session()
        session["agentifier_breadth_chosen"] = True
        layout = _chat_layout(session)
        row = self._find_input_row(layout)
        assert row is not None
        assert row.style["display"] == "flex"


# ---------------------------------------------------------------------------
# on_stream_poll — D-PH9 received-char counter threading
# ---------------------------------------------------------------------------


class TestStreamPollReceivedCounter:
    """The cumulative received-char scalar the phaser drain publishes is
    surfaced mid-stream and cleared on finalisation."""

    def test_not_done_threads_received_scalar(self) -> None:
        session = _session_with_stream()
        session["messages"][-1] = {"role": "assistant", "content": "frozen"}
        agent_sess = _default_session()
        agent_sess["_stream_received_chars"] = 51234
        entry = {"text": "frozen", "done": False, "session": agent_sess}

        with patch("spec4.callbacks.streaming.get", return_value=entry):
            result = on_stream_poll(1, session)

        assert result[0] is not no_update
        assert result[0]["_stream_received_chars"] == 51234

    def test_not_done_rerenders_when_only_scalar_advances(self) -> None:
        # Displayed text is unchanged (the drain yields nothing), but the
        # received scalar advanced — the poll must still return an update so
        # the counter re-renders rather than short-circuiting on text==prev.
        session = _session_with_stream()
        session["messages"][-1] = {"role": "assistant", "content": "frozen"}
        session["_stream_received_chars"] = 50000
        agent_sess = _default_session()
        agent_sess["_stream_received_chars"] = 50120
        entry = {"text": "frozen", "done": False, "session": agent_sess}

        with patch("spec4.callbacks.streaming.get", return_value=entry):
            result = on_stream_poll(1, session)

        assert result[0] is not no_update
        assert result[0]["_stream_received_chars"] == 50120

    def test_not_done_no_update_when_nothing_advances(self) -> None:
        # Neither the displayed text nor the scalar changed — short-circuit.
        session = _session_with_stream()
        session["messages"][-1] = {"role": "assistant", "content": "frozen"}
        session["_stream_received_chars"] = 50000
        agent_sess = _default_session()
        agent_sess["_stream_received_chars"] = 50000
        entry = {"text": "frozen", "done": False, "session": agent_sess}

        with patch("spec4.callbacks.streaming.get", return_value=entry):
            result = on_stream_poll(1, session)

        assert result[0] is no_update

    def test_done_clears_received_scalar(self) -> None:
        session = _session_with_stream()
        agent_sess = _default_session()
        agent_sess["_display_override"] = None
        agent_sess["_stream_received_chars"] = 99999
        entry = {"text": "final", "done": True, "session": agent_sess}

        with patch("spec4.callbacks.streaming.get", return_value=entry):
            result = on_stream_poll(1, session)

        assert result[0]["_stream_received_chars"] is None


class TestStreamedTokenCounter:
    """D-PH9: _streamed_token_count prefers the published received total, and
    otherwise falls back to the in-flight assistant message length."""

    def test_prefers_received_scalar(self) -> None:
        session = {
            "messages": [{"role": "assistant", "content": "short"}],
            "_stream_received_chars": 4321,
        }
        assert _streamed_token_count(session) == 4321

    def test_falls_back_to_message_length_when_scalar_none(self) -> None:
        session = {
            "messages": [{"role": "assistant", "content": "abcde"}],
            "_stream_received_chars": None,
        }
        assert _streamed_token_count(session) == 5

    def test_falls_back_when_scalar_absent(self) -> None:
        session = {"messages": [{"role": "assistant", "content": "abc"}]}
        assert _streamed_token_count(session) == 3
