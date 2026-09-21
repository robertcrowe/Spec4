"""``token_count_text``: the chars counter under the chat input.

Before the first reply character a model that reasons first shows its thinking
count in place of a counter stuck at 0; once reply text arrives the received
count takes over whatever the thinking count did.
"""

from __future__ import annotations

from typing import Any

from spec4.layouts._chat_actions import token_count_text
from spec4.session import default_session


def _session(**extra: Any) -> dict[str, Any]:
    session = {**default_session(), "active_agent": "brainstormer", "_stream_id": "s"}
    session.update(extra)
    return session


class TestThinkingBeforeTheFirstReplyCharacter:
    def test_thinking_shows_while_nothing_has_been_received(self) -> None:
        session = _session(_stream_received_chars=0, _stream_thinking_chars=350)
        assert token_count_text(session) == "Thinking — 350 chars"

    def test_received_text_takes_over_even_while_thinking_continues(self) -> None:
        session = _session(_stream_received_chars=12, _stream_thinking_chars=350)
        assert token_count_text(session) == "Chars received: 12"

    def test_no_thinking_keeps_the_zero_counter(self) -> None:
        session = _session(_stream_received_chars=0, _stream_thinking_chars=0)
        assert token_count_text(session) == "Chars received: 0"
        session = _session(_stream_received_chars=0, _stream_thinking_chars=None)
        assert token_count_text(session) == "Chars received: 0"

    def test_no_stream_and_nothing_received_shows_nothing(self) -> None:
        session = _session(
            _stream_id=None, _stream_received_chars=0, _stream_thinking_chars=350
        )
        assert token_count_text(session) == ""
