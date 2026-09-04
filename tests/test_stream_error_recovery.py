"""D-ER1 — recovery after a turn dies on a provider error.

An overloaded provider (``InternalServerError … Overloaded``) kills the
generator mid-stream. ``streaming.start`` catches it, writes the formatted
exception into the assistant bubble, and marks the stream done — but the agent
never reached its state transition, so nothing in the chat changes state and
the user is left with an error message and no control to click. These tests
pin the three pieces that close that gap: the failure flag on the stream entry,
the poll lifting it onto the session, and the Try Again panel plus the callback
that replays the dead turn.
"""

from __future__ import annotations

import time
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

from dash import no_update

from spec4 import streaming
from spec4.callbacks import (
    _switch_agent,
    on_chat_retry,
    on_chat_submit,
    on_fast_forward,
    on_init_turn,
    on_stream_poll,
)
from spec4.layouts._chat import _chat_layout, _retry_panel
from spec4.session import _default_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ids(node: Any, acc: list[Any] | None = None) -> list[Any]:
    acc = [] if acc is None else acc
    if isinstance(node, (list, tuple)):
        for item in node:
            _ids(item, acc)
        return acc
    node_id = getattr(node, "id", None)
    if node_id is not None:
        acc.append(node_id)
    children = getattr(node, "children", None)
    if children is not None and not isinstance(children, str):
        _ids(children, acc)
    return acc


def _boom() -> Generator[str, None, None]:
    yield "partial output"
    raise RuntimeError("litellm.InternalServerError: AnthropicError - Overloaded")


def _clean() -> Generator[str, None, None]:
    yield "all good"


def _await_done(stream_id: str) -> dict[str, Any]:
    """Wait for start()'s daemon thread. Bounded so a hang fails loudly."""
    for _ in range(500):
        entry = streaming.get(stream_id)
        assert entry is not None
        if entry["done"]:
            return entry
        time.sleep(0.005)
    raise AssertionError("stream never finished")


def _session(**overrides: Any) -> dict[str, Any]:
    s = _default_session()
    s["active_agent"] = "code_scanner"
    s["llm_config"] = {"model": "claude-opus-5", "api_key": "sk-test"}
    s.update(overrides)
    # A turn only starts once the per-agent model gate has been answered.
    # Applied after the overrides so it follows whichever agent is active.
    s["agent_llm_asked"] = {
        **(s.get("agent_llm_asked") or {}),
        s["active_agent"]: True,
    }
    return s


# ---------------------------------------------------------------------------
# streaming.start — the failure flag
# ---------------------------------------------------------------------------


class TestStreamEntryRecordsFailure:
    def test_exception_sets_error_flag(self) -> None:
        sid = streaming.start(_boom(), _default_session())
        entry = _await_done(sid)
        assert entry["error"] is True, (
            "a generator that raised must mark the entry; the poll has no other "
            "way to distinguish an error bubble from ordinary assistant text"
        )

    def test_formatted_error_still_reaches_the_text(self) -> None:
        """The flag is additive — the existing error-text behaviour is unchanged."""
        sid = streaming.start(_boom(), _default_session())
        entry = _await_done(sid)
        assert entry["text"].startswith("partial output")
        assert "**Error: RuntimeError**" in entry["text"]

    def test_clean_run_leaves_error_false(self) -> None:
        sid = streaming.start(_clean(), _default_session())
        entry = _await_done(sid)
        assert entry["error"] is False

    def test_flag_present_from_the_start(self) -> None:
        """Absent-key access would work via .get, but the entry shape is public
        (tests and the poll both read it) — keep it explicit."""
        sid = streaming.start(_clean(), _default_session())
        entry = streaming.get(sid)
        assert entry is not None
        assert "error" in entry


# ---------------------------------------------------------------------------
# on_stream_poll — lifting the flag onto the session
# ---------------------------------------------------------------------------


def _poll_with_entry(entry: dict[str, Any]) -> Any:
    session = _session(
        _stream_id="aaaabbbb-0000-0000-0000-000000000000",
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": ""},
        ],
    )
    with (
        patch("spec4.callbacks.streaming.get", return_value=entry),
        patch("spec4.callbacks._persist_artifacts"),
    ):
        return on_stream_poll(1, session)


class TestPollPropagatesFailure:
    def test_failed_stream_sets_session_flag(self) -> None:
        agent_sess = _session()
        updated, max_intervals = _poll_with_entry(
            {
                "text": "**Error: InternalServerError**",
                "done": True,
                "session": agent_sess,
                "error": True,
            }
        )
        assert updated["_stream_error"] is True
        assert updated["_stream_id"] is None
        assert max_intervals == 0

    def test_clean_stream_clears_the_flag(self) -> None:
        """A successful turn retires an earlier failure — otherwise the panel
        would linger over a turn that worked."""
        agent_sess = _session(_stream_error=True)
        updated, _ = _poll_with_entry(
            {
                "text": "done",
                "done": True,
                "session": agent_sess,
                "error": False,
            }
        )
        assert updated["_stream_error"] is None

    def test_entry_without_error_key_is_treated_as_clean(self) -> None:
        """Backwards compatibility with entries built before the flag existed."""
        updated, _ = _poll_with_entry(
            {"text": "done", "done": True, "session": _session()}
        )
        assert updated["_stream_error"] is None

    def test_mid_stream_poll_does_not_set_the_flag(self) -> None:
        """Only the done branch decides; an in-flight turn may still succeed."""
        updated, _ = _poll_with_entry(
            {
                "text": "streaming…",
                "done": False,
                "session": _session(),
                "error": False,
            }
        )
        assert updated is not no_update
        assert updated.get("_stream_error") is None


class TestEmptyTurnBackstop:
    """D-ER2 — a finished turn with nothing to show is a failed turn.

    Observed live: a CodeScanner finalize whose artifact reply was suppressed on
    its way to the screen and then failed to parse returned without yielding and
    without setting a display override. The chat rendered a blank bubble with no
    controls under it, and the poll had no reason to think anything was wrong.
    """

    def test_empty_assistant_turn_gets_a_notice(self) -> None:
        updated, _ = _poll_with_entry(
            {"text": "", "done": True, "session": _session(), "error": False}
        )
        assert updated["messages"][-1]["content"].strip()
        assert "without producing a response" in updated["messages"][-1]["content"]

    def test_empty_assistant_turn_enables_retry(self) -> None:
        updated, _ = _poll_with_entry(
            {"text": "", "done": True, "session": _session(), "error": False}
        )
        assert updated["_stream_error"] is True
        assert _retry_panel(updated) is not None

    def test_whitespace_only_counts_as_empty(self) -> None:
        updated, _ = _poll_with_entry(
            {"text": "  \n\n ", "done": True, "session": _session(), "error": False}
        )
        assert "without producing a response" in updated["messages"][-1]["content"]

    def test_a_turn_with_output_is_untouched(self) -> None:
        updated, _ = _poll_with_entry(
            {
                "text": "Here is the review.",
                "done": True,
                "session": _session(),
                "error": False,
            }
        )
        assert updated["messages"][-1]["content"] == "Here is the review."
        assert updated["_stream_error"] is None

    def test_a_display_override_satisfies_the_check(self) -> None:
        """Artifact turns yield nothing by design and substitute the rendered
        artifact — that is a complete turn, not an empty one."""
        agent_sess = _session(_display_override="## Code Review\n\nAll good.")
        updated, _ = _poll_with_entry(
            {"text": "", "done": True, "session": agent_sess, "error": False}
        )
        assert updated["messages"][-1]["content"] == "## Code Review\n\nAll good."
        assert updated["_stream_error"] is None

    def test_mid_stream_emptiness_is_not_a_failure(self) -> None:
        """An in-flight turn has not produced its output yet."""
        updated, _ = _poll_with_entry(
            {"text": "", "done": False, "session": _session(), "error": False}
        )
        assert updated is no_update or not updated.get("_stream_error")


# ---------------------------------------------------------------------------
# Every turn start clears the flag
# ---------------------------------------------------------------------------


class TestTurnStartsClearTheFlag:
    def test_init_turn_clears(self) -> None:
        session = _session(_stream_error=True)
        with (
            patch("spec4.callbacks._get_agent_gen", return_value=iter(["x"])),
            patch("spec4.callbacks.streaming.start", return_value="sid"),
        ):
            updated, _ = on_init_turn(1, session)
        assert updated["_stream_error"] is None

    def test_chat_submit_clears(self) -> None:
        session = _session(
            _stream_error=True,
            messages=[{"role": "assistant", "content": "**Error: X**"}],
        )
        with (
            patch("spec4.callbacks._get_agent_gen", return_value=iter(["x"])),
            patch("spec4.callbacks.streaming.start", return_value="sid"),
        ):
            updated, cleared_input, max_intervals = on_chat_submit(
                1, 0, "try again please", session
            )
        assert updated["_stream_error"] is None
        assert cleared_input == ""
        assert max_intervals == -1

    def test_fast_forward_clears(self) -> None:
        session = _session(
            active_agent="stack_advisor",
            _stream_error=True,
            messages=[{"role": "assistant", "content": "Topic 1?"}],
        )
        with (
            patch("spec4.callbacks._get_agent_gen", return_value=iter(["x"])),
            patch("spec4.callbacks.streaming.start", return_value="sid"),
        ):
            updated, _ = on_fast_forward(1, session)
        assert updated["_stream_error"] is None

    def test_agent_switch_clears(self) -> None:
        """A failure belongs to the turn that produced it, not to the next agent."""
        switched = _switch_agent(_session(_stream_error=True), "brainstormer")
        assert switched["_stream_error"] is None

    def test_default_session_starts_clean(self) -> None:
        assert _default_session()["_stream_error"] is None


# ---------------------------------------------------------------------------
# _retry_panel — the visible affordance
# ---------------------------------------------------------------------------


def _failed_session(**overrides: Any) -> dict[str, Any]:
    """A finalised failed turn: flag set, no live stream, error bubble on screen."""
    return _session(
        _stream_error=True,
        messages=[{"role": "assistant", "content": "**Error: Overloaded**"}],
        **overrides,
    )


class TestRetryPanel:
    def test_absent_without_a_failure(self) -> None:
        assert _retry_panel(_session()) is None

    def test_absent_mid_stream(self) -> None:
        """The progress bar owns that space; the turn may still succeed."""
        assert _retry_panel(_failed_session(_stream_id="live")) is None

    def test_offers_the_retry_button(self) -> None:
        panel = _retry_panel(_failed_session())
        assert panel is not None
        assert "btn-chat-retry" in _ids(panel)

    def test_explains_what_happened(self) -> None:
        rendered = str(_retry_panel(_failed_session()))
        assert "didn't complete" in rendered
        assert "Nothing already saved is lost." in rendered

    def test_absent_when_the_transcript_was_cleared(self) -> None:
        """A flag that outlived its turn renders nothing — every restart path
        (agent switch, re-scan, skip-into-agent) empties `messages`."""
        assert _retry_panel(_session(_stream_error=True, messages=[])) is None

    def test_absent_when_the_last_turn_is_the_users(self) -> None:
        """Nothing to replace: the failed assistant bubble is gone."""
        assert (
            _retry_panel(
                _session(
                    _stream_error=True,
                    messages=[{"role": "user", "content": "hi"}],
                )
            )
            is None
        )

    def test_reaches_the_chat_layout(self) -> None:
        ids = _ids(_chat_layout(_failed_session()))
        assert "btn-chat-retry" in ids

    def test_layout_is_unchanged_without_a_failure(self) -> None:
        ids = _ids(_chat_layout(_session()))
        assert "btn-chat-retry" not in ids
        # The ordinary chat furniture is untouched either way.
        assert "chat-input" in ids
        assert "chat-progress-container" in ids


# ---------------------------------------------------------------------------
# on_chat_retry — replaying the dead turn
# ---------------------------------------------------------------------------


class TestRetryReplaysTheTurn:
    def test_opening_turn_retries_with_no_user_input(self) -> None:
        """The CodeScanner scan is an opening turn — there is no user message to
        re-send, so the agent must be re-entered exactly as the init turn does."""
        session = _session(
            _stream_error=True,
            messages=[{"role": "assistant", "content": "**Error: Overloaded**"}],
        )
        with (
            patch(
                "spec4.callbacks._get_agent_gen", return_value=iter(["x"])
            ) as mock_gen,
            patch("spec4.callbacks.streaming.start", return_value="sid"),
        ):
            updated, max_intervals = on_chat_retry(1, session)
        assert mock_gen.call_args[0][0] is None
        assert updated["messages"] == [{"role": "assistant", "content": ""}]
        assert updated["_stream_id"] == "sid"
        assert updated["_stream_error"] is None
        assert max_intervals == -1

    def test_user_turn_is_re_sent_verbatim(self) -> None:
        session = _session(
            _stream_error=True,
            messages=[
                {"role": "assistant", "content": "Which framework?"},
                {"role": "user", "content": "Use Dash"},
                {"role": "assistant", "content": "**Error: Overloaded**"},
            ],
        )
        with (
            patch(
                "spec4.callbacks._get_agent_gen", return_value=iter(["x"])
            ) as mock_gen,
            patch("spec4.callbacks.streaming.start", return_value="sid"),
        ):
            updated, _ = on_chat_retry(1, session)
        assert mock_gen.call_args[0][0] == "Use Dash"
        # The user turn stays where it was; only the error bubble is replaced.
        assert updated["messages"][-2] == {"role": "user", "content": "Use Dash"}
        assert updated["messages"][-1] == {"role": "assistant", "content": ""}
        assert len(updated["messages"]) == 3

    def test_error_bubble_is_dropped(self) -> None:
        """The retry streams into a fresh bubble — the stale error text must not
        stay in the transcript above it."""
        session = _session(
            _stream_error=True,
            messages=[{"role": "assistant", "content": "**Error: Overloaded**"}],
        )
        with (
            patch("spec4.callbacks._get_agent_gen", return_value=iter(["x"])),
            patch("spec4.callbacks.streaming.start", return_value="sid"),
        ):
            updated, _ = on_chat_retry(1, session)
        assert not any(
            "**Error:" in m["content"] for m in updated["messages"]
        )

    def test_noop_without_click(self) -> None:
        session = _session(_stream_error=True)
        with patch("spec4.callbacks._get_agent_gen") as mock_gen:
            result = on_chat_retry(None, session)
        mock_gen.assert_not_called()
        assert result == (no_update, no_update)

    def test_noop_while_a_stream_is_in_flight(self) -> None:
        """Turn-integrity guard, matching every other turn starter."""
        session = _session(_stream_error=True, _stream_id="live")
        with patch("spec4.callbacks._get_agent_gen") as mock_gen:
            result = on_chat_retry(1, session)
        mock_gen.assert_not_called()
        assert result == (no_update, no_update)

    def test_survives_an_empty_transcript(self) -> None:
        """Defensive: the flag can only be set by a finished turn, but the
        callback must not index into an empty list if one ever reaches it."""
        session = _session(_stream_error=True, messages=[])
        with (
            patch(
                "spec4.callbacks._get_agent_gen", return_value=iter(["x"])
            ) as mock_gen,
            patch("spec4.callbacks.streaming.start", return_value="sid"),
        ):
            updated, _ = on_chat_retry(1, session)
        assert mock_gen.call_args[0][0] is None
        assert updated["messages"] == [{"role": "assistant", "content": ""}]


# ---------------------------------------------------------------------------
# Wiring — the button is actually connected
# ---------------------------------------------------------------------------


class TestCallbackWiring:
    @staticmethod
    def _refs(spec: Any) -> set[tuple[str, str]]:
        items = spec if isinstance(spec, list) else [spec]
        return {
            (d["id"], d["property"])
            for d in items
            if isinstance(d, dict) and "id" in d and "property" in d
        }

    def test_retry_button_drives_a_callback(self) -> None:
        # Server callbacks registered with the module-level ``@callback`` land in
        # Dash's global registry, not on ``app._callback_list`` (which holds only
        # the clientside ones bound directly to the app object).
        from dash._callback import GLOBAL_CALLBACK_LIST

        import spec4.callbacks  # noqa: F401  (import registers the callbacks)

        triggers = {
            ref
            for entry in GLOBAL_CALLBACK_LIST
            for ref in self._refs(entry.get("inputs"))
        }
        assert ("btn-chat-retry", "n_clicks") in triggers, (
            "the Try Again button must be wired; an unwired id renders as a "
            "dead control, which is the failure mode this work removes"
        )


class TestRetryWithADifferentModel:
    """The second door out of a failed turn.

    Try Again re-runs the same step on the same model — right for an overload,
    useless for an unreachable provider or a rejected key. This button opens the
    per-agent model picker instead; the retry itself stays a separate click, so
    an expensive step is never re-spent by merely choosing a model.
    """

    def _failed(self, **overrides: Any) -> dict[str, Any]:
        """A failed Phaser turn with the user message still above it.

        `_failed_session` pins its own transcript; this one needs the preceding
        user message so the retry has something to re-send.
        """
        return _session(
            active_agent="phaser",
            _stream_error=True,
            _initial_turn_done=True,
            messages=[
                {"role": "user", "content": "plan it"},
                {"role": "assistant", "content": "**Error:** unreachable"},
            ],
            **overrides,
        )

    def test_the_panel_offers_both_doors(self) -> None:
        rendered = _ids(_retry_panel(self._failed()))
        assert "btn-chat-retry" in rendered
        assert "btn-chat-retry-model" in rendered

    def test_neither_button_appears_mid_stream(self) -> None:
        assert _retry_panel(self._failed(_stream_id="live")) is None

    def test_the_copy_no_longer_promises_a_retry_will_work(self) -> None:
        """A developer facing an unreachable provider must not be told twice
        that the failure is "usually temporary"."""
        rendered = str(_retry_panel(self._failed()))
        assert "fail the same way every time" in rendered

    def test_clicking_opens_the_picker_for_the_active_agent(self) -> None:
        from spec4.callbacks import on_chat_retry_model

        updated = on_chat_retry_model(1, self._failed())
        assert updated["agent_llm_draft"]["agent"] == "phaser"

    def test_clicking_writes_no_override_yet(self) -> None:
        """Opening the picker must not commit anything on its own."""
        from spec4.callbacks import on_chat_retry_model

        assert on_chat_retry_model(1, self._failed())["agent_llm"] == {}

    def test_refused_while_a_stream_is_in_flight(self) -> None:
        from spec4.callbacks import on_chat_retry_model

        assert on_chat_retry_model(1, self._failed(_stream_id="live")) is no_update

    def test_noop_without_click(self) -> None:
        from spec4.callbacks import on_chat_retry_model

        assert on_chat_retry_model(None, self._failed()) is no_update

    def _choose(
        self, session: dict[str, Any], *, tool_support: bool | None = True
    ) -> tuple[dict[str, Any], Any]:
        """Walk a retry-originated picker to Continue."""
        from spec4 import providers
        from spec4.callbacks import (
            on_chat_retry_model,
            on_gate_connect,
            on_gate_continue,
        )

        opened = on_chat_retry_model(1, session)
        with patch.object(providers, "list_models", return_value=(["gpt-5"], "")):
            opened, _ = on_gate_connect(1, "OpenAI", "sk-new", opened, {})
        with patch(
            "spec4.llm_selection.probe_image_support", return_value=True
        ), patch(
            "spec4.llm_selection.probe_tool_support", return_value=tool_support
        ), patch(
            "spec4.callbacks._get_agent_gen", return_value=iter(["x"])
        ) as gen, patch(
            "spec4.callbacks.streaming.start", return_value="sid"
        ):
            answered, poll = on_gate_continue(1, "gpt-5", opened)
        return {"session": answered, "poll": poll, "gen": gen}, answered

    def test_choosing_a_model_re_runs_the_step_at_once(self) -> None:
        """The contract that replaced the two-step flow.

        This assertion is the inverse of the one it grew out of: choosing a
        model used to *leave the panel standing* for a second click, and now
        closes it and starts the turn.
        """
        result, answered = self._choose(self._failed())
        assert answered["_stream_id"] == "sid"
        assert result["poll"] == -1
        assert answered["_stream_error"] is None
        assert _retry_panel(answered) is None

    def test_the_re_run_re_sends_the_original_message(self) -> None:
        result, _ = self._choose(self._failed())
        assert result["gen"].call_args[0][0] == "plan it"

    def test_the_re_run_uses_the_newly_chosen_model(self) -> None:
        from spec4 import llm_selection

        result, _ = self._choose(self._failed())
        used = llm_selection.resolve(result["gen"].call_args[0][1], "phaser")
        assert used["model"] == "gpt-5"

    def test_the_failed_bubble_is_replaced(self) -> None:
        _, answered = self._choose(self._failed())
        assert answered["messages"][-1] == {"role": "assistant", "content": ""}
        assert answered["messages"][0]["content"] == "plan it"

    def test_a_tool_less_model_is_refused_and_nothing_runs(self) -> None:
        """The one place a probe blocks — the call would be spent unasked."""
        _, answered = self._choose(self._failed(), tool_support=False)
        assert answered["agent_llm"] == {}
        assert answered["agent_llm_draft"]["retry"] is True
        assert answered.get("_stream_id") is None
        assert "no tool support" in answered["agent_llm_error"]
        assert "Try Again" in answered["agent_llm_error"]

    def test_an_unknown_tool_probe_does_not_refuse(self) -> None:
        """`None` is unknown, not a negative — the standing rule."""
        _, answered = self._choose(self._failed(), tool_support=None)
        assert answered["agent_llm"]["phaser"]["model"] == "gpt-5"
        assert answered["_stream_id"] == "sid"

    def test_a_pick_from_the_chip_neither_refuses_nor_runs(self) -> None:
        """Only a retry-originated picker auto-runs or blocks."""
        from spec4 import providers
        from spec4.callbacks import on_gate_chip, on_gate_connect, on_gate_continue

        opened = on_gate_chip(1, self._failed())
        with patch.object(providers, "list_models", return_value=(["gpt-5"], "")):
            opened, _ = on_gate_connect(1, "OpenAI", "sk-new", opened, {})
        with patch(
            "spec4.llm_selection.probe_image_support", return_value=True
        ), patch("spec4.llm_selection.probe_tool_support", return_value=False):
            answered, poll = on_gate_continue(1, "gpt-5", opened)
        assert answered["agent_llm"]["phaser"]["model"] == "gpt-5"
        assert answered.get("_stream_id") is None
        assert poll is no_update
        assert _retry_panel(answered) is not None

    def test_the_retry_then_runs_on_the_new_model(self) -> None:
        from spec4 import llm_selection
        from spec4.callbacks import on_chat_retry

        session = self._failed(
            agent_llm={
                "phaser": {
                    "provider": "openai",
                    "model": "gpt-5",
                    "llm_config": {"model": "gpt-5", "api_key": "sk-new"},
                }
            }
        )
        with patch(
            "spec4.callbacks._get_agent_gen", return_value=iter(["x"])
        ) as gen, patch("spec4.callbacks.streaming.start", return_value="sid"):
            on_chat_retry(1, session)
        assert gen.call_args[0][0] == "plan it"
        assert llm_selection.resolve(gen.call_args[0][1], "phaser")["model"] == "gpt-5"
