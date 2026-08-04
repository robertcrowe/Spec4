"""The Brainstormer chars counter.

Brainstormer was the last chat agent with no counter at all: it was absent from
``_TOKEN_COUNTER_AGENTS``, *and* it was the one caller that passed no ``session``
into ``_stream_suppressing_json``. Its vision-finalize turn suppresses the
artifact on its way to the screen exactly as StackAdvisor's does (D-SC60), so
the developer watched a multi-minute draw with no feedback whatsoever.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from spec4.agents import brainstormer
from spec4.app_constants import STATE_VISION_COMPLETE
from spec4.layouts._chat import (
    _TOKEN_COUNTER_AGENTS,
    _chat_action_buttons,
    _token_count_text,
)


def _counter_texts(rendered: Any) -> list[str]:
    """Collect the text of every counter component in a rendered button bar."""
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, list | tuple):
            for item in node:
                walk(item)
            return
        children = getattr(node, "children", None)
        if getattr(node, "id", None) == "chat-token-count":
            found.append(children if isinstance(children, str) else "")
        if children is not None:
            walk(children)

    walk(rendered)
    return found


def _fake_stream(*chunks: str) -> Any:
    """Stand in for ``llm.stream_turn``: records the reply, yields it."""

    def _stream(*args: Any, **kwargs: Any) -> Any:
        msgs = args[1]

        def _gen() -> Any:
            yield from chunks

        msgs.append({"role": "assistant", "content": "".join(chunks)})
        return _gen()

    return _stream


def _session(**extra: Any) -> dict[str, Any]:
    session: dict[str, Any] = {
        "active_agent": "brainstormer",
        "brainstormer_messages": [
            {"role": "user", "content": "an app"},
            {"role": "assistant", "content": "Tell me more."},
        ],
    }
    session.update(extra)
    return session


class TestCounterGate:
    def test_brainstormer_is_gated_on(self) -> None:
        assert "brainstormer" in _TOKEN_COUNTER_AGENTS

    def test_renders_published_total(self) -> None:
        session = _session(_stream_id="abc", _stream_received_chars=1234)
        assert _token_count_text(session) == "Chars received: 1234"


class TestCounterReachesTheLayout:
    """Being in ``_TOKEN_COUNTER_AGENTS`` only makes ``_token_count_text``
    return something — the branch has to render a component to show it. The
    Brainstormer branch had no button bar at all before the vision landed, so
    the counter had nowhere to appear."""

    def test_mid_conversation_turn_shows_the_counter(self) -> None:
        session = _session(_stream_id="abc", _stream_received_chars=5150)
        assert _counter_texts(_chat_action_buttons(session)) == [
            "Chars received: 5150"
        ]

    def test_complete_state_shows_the_counter(self) -> None:
        session = _session(
            brainstormer_state=STATE_VISION_COMPLETE,
            _stream_received_chars=1234,
        )
        assert _counter_texts(_chat_action_buttons(session)) == [
            "Chars received: 1234"
        ]

    def test_bare_before_the_first_chunk(self) -> None:
        # No stream and no count: the bar would be an empty row under a divider.
        assert _counter_texts(_chat_action_buttons(_session())) == []
        assert _chat_action_buttons(_session()).children is None

    def test_exactly_one_counter_per_bar(self) -> None:
        """Duplicate ids in one layout are a Dash error, not a cosmetic issue."""
        for overrides in (
            {"_stream_id": "abc"},
            {"brainstormer_state": STATE_VISION_COMPLETE},
        ):
            session = _session(_stream_received_chars=9, **overrides)
            assert len(_counter_texts(_chat_action_buttons(session))) == 1

    def test_completion_buttons_survive(self) -> None:
        session = _session(
            brainstormer_state=STATE_VISION_COMPLETE,
            _stream_received_chars=1234,
        )
        ids: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, list | tuple):
                for item in node:
                    walk(item)
                return
            if getattr(node, "id", None):
                ids.append(node.id)
            children = getattr(node, "children", None)
            if children is not None:
                walk(children)

        walk(_chat_action_buttons(session))
        assert "btn-dl-vision" in ids
        assert "btn-brainstormer-to-designer" in ids
        assert "btn-brainstormer-to-agentifier" in ids


class TestSuppressedVisionTurnPublishesReceipt:
    """The finalize turn yields nothing, so the displayed-character fallback
    reads 0 for its whole duration — the case the published total exists for."""

    _VISION = (
        '```json\n{"vision_statement": {"vision": {"purpose": "x"}}}\n```'
    )

    def _run(self, session: dict[str, Any], *chunks: str) -> list[str]:
        with (
            patch.object(
                brainstormer.llm, "build_system_prompt", return_value=""
            ),
            patch.object(
                brainstormer.llm, "stream_turn", _fake_stream(*chunks)
            ),
        ):
            return list(brainstormer.run("go", session, {"model": "x"}))

    def test_suppressed_turn_still_counts(self) -> None:
        session = _session()
        out = self._run(session, self._VISION)
        assert out == []  # nothing reached the screen…
        assert session["_stream_received_chars"] == len(self._VISION)  # …but counted

    def test_conversational_turn_counts_too(self) -> None:
        session = _session()
        out = self._run(session, "Who ", "is it ", "for?")
        assert "".join(out) == "Who is it for?"
        assert session["_stream_received_chars"] == 14

    def test_turn_seeded_at_zero_clearing_a_stale_total(self) -> None:
        session = _session(_stream_received_chars=99999)
        self._run(session, "hi")
        assert session["_stream_received_chars"] == 2


class TestReaskKeepsCounterMonotonic:
    """D-BR-P3's re-ask drains a second reply without yielding it. Seeding the
    drain with the first reply's length stops the counter falling back to zero
    partway through the turn."""

    # Opens with a fence, so it is suppressed and `_suppressed_as_artifact` is
    # true, but carries no usable vision — the exact re-ask trigger.
    _BAD = '```json\n{"not_a_vision": true}\n```'
    _WORSE = '```json\n{"still_not": true}\n```'

    def test_reask_drain_continues_from_the_first_reply(self) -> None:
        session = _session()
        replies = iter((self._BAD, self._WORSE))

        def _stream(*args: Any, **kwargs: Any) -> Any:
            return _fake_stream(next(replies))(*args, **kwargs)

        with (
            patch.object(
                brainstormer.llm, "build_system_prompt", return_value=""
            ),
            patch.object(brainstormer.llm, "stream_turn", _stream),
        ):
            out = list(brainstormer.run("go", session, {"model": "x"}))

        # The re-ask status line is the only thing the developer sees.
        assert "".join(out).strip()
        # Total spans both replies plus the status line — never dips back to
        # the second reply's length alone.
        assert session["_stream_received_chars"] > len(self._BAD) + len(self._WORSE)
