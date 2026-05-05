from __future__ import annotations

from typing import Any

from spec4.agents._utils import _drop_orphan_trailing_user


class TestDropOrphanTrailingUser:
    def test_empty_list_no_op(self) -> None:
        msgs: list[dict[str, Any]] = []
        assert _drop_orphan_trailing_user(msgs) == 0
        assert msgs == []

    def test_well_formed_history_unchanged(self) -> None:
        msgs = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
        ]
        original = list(msgs)
        assert _drop_orphan_trailing_user(msgs) == 0
        assert msgs == original

    def test_drops_single_orphan_user(self) -> None:
        msgs = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2 (failed before reply)"},
        ]
        assert _drop_orphan_trailing_user(msgs) == 1
        assert msgs == [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
        ]

    def test_drops_user_only_history(self) -> None:
        msgs = [{"role": "user", "content": "first try, failed"}]
        assert _drop_orphan_trailing_user(msgs) == 1
        assert msgs == []

    def test_drops_trailing_tool_and_user_chain(self) -> None:
        # If a tool-call response was appended but the next assistant never
        # arrived, both the tool message and the assistant-with-tool-call
        # turn (which has role=assistant but is followed by tool/user only)
        # need to be considered. We only pop non-assistant trailing entries.
        msgs = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
            {"role": "tool", "tool_call_id": "x", "content": "tool result"},
        ]
        assert _drop_orphan_trailing_user(msgs) == 2
        assert msgs == [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
        ]

    def test_keeps_empty_assistant_turn(self) -> None:
        # An empty assistant turn is still well-formed and must NOT be dropped.
        msgs = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": ""},
        ]
        assert _drop_orphan_trailing_user(msgs) == 0
        assert msgs[-1]["role"] == "assistant"
