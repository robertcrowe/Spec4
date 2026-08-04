"""D-SC60/D-SC62: the StackAdvisor chat token counter.

StackAdvisor's artifact turn streams through ``_stream_suppressing_json``, which
yields nothing once it sees the leading fence. The counter's displayed-character
fallback therefore reads 0 for the entire draw, so the suppression chokepoint
publishes a cumulative received-character total instead — the same remedy D-PH9
applied to the phaser validation-retry drain.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from spec4.agents._utils import _stream_suppressing_json
from spec4.layouts._chat import (
    _TOKEN_COUNTER_AGENTS,
    _streamed_token_count,
    _token_count_text,
)


def _chunks(*parts: str) -> Generator[str, None, None]:
    yield from parts


class TestCounterGate:
    """D-SC62: the counter renders for stack_advisor, and only for the gated
    agents."""

    def test_stack_advisor_is_gated_on(self) -> None:
        assert "stack_advisor" in _TOKEN_COUNTER_AGENTS

    def test_prior_agents_still_gated_on(self) -> None:
        assert "phaser" in _TOKEN_COUNTER_AGENTS
        assert "deployer" in _TOKEN_COUNTER_AGENTS

    def test_agentifier_is_gated_on(self) -> None:
        # D-AT1 supersedes D-SC62(a), which had explicitly left agentifier out.
        assert "agentifier" in _TOKEN_COUNTER_AGENTS

    def test_code_scanner_is_gated_on(self) -> None:
        # D-SC-P1 supersedes D-SC62(a), which had left code_scanner out.
        assert "code_scanner" in _TOKEN_COUNTER_AGENTS

    def test_scope_is_every_chat_agent(self) -> None:
        # Brainstormer was the last chat agent left out; it suppresses JSON on
        # the vision-finalize turn exactly as StackAdvisor does, so it had the
        # D-SC60 blind draw with no counter at all. Designer stays out: it is
        # not a chat agent and carries its own counter in the designer layout.
        assert set(_TOKEN_COUNTER_AGENTS) == {
            "code_scanner",
            "brainstormer",
            "agentifier",
            "stack_advisor",
            "phaser",
            "deployer",
        }

    def test_renders_published_total_for_stack_advisor(self) -> None:
        session: dict[str, Any] = {
            "active_agent": "stack_advisor",
            "_stream_id": "abc",
            "messages": [{"role": "assistant", "content": ""}],
            "_stream_received_chars": 8291,
        }
        assert _token_count_text(session) == "Chars received: 8291"

    def test_silent_for_ungated_agent(self) -> None:
        session: dict[str, Any] = {
            "active_agent": "designer",
            "_stream_id": "abc",
            "_stream_received_chars": 8291,
        }
        assert _token_count_text(session) == ""

    def test_silent_when_idle_with_no_receipt(self) -> None:
        session: dict[str, Any] = {
            "active_agent": "stack_advisor",
            "messages": [{"role": "assistant", "content": ""}],
        }
        assert _token_count_text(session) == ""


class TestSuppressedStreamPublishesReceipt:
    """D-SC60: the suppressed artifact stream is exactly the case the
    displayed-character fallback cannot serve."""

    def test_suppressed_stream_yields_nothing_but_still_counts(self) -> None:
        session: dict[str, Any] = {}
        out = list(
            _stream_suppressing_json(
                _chunks("```json\n", '{"stack": ', '"value"}', "\n```"),
                session,
            )
        )
        assert out == []
        assert session["_stream_received_chars"] == 30

    def test_counter_climbs_during_suppression(self) -> None:
        # The suppressed stream yields nothing, so the consumer cannot observe
        # progress; watch from the producer side instead, sampling the published
        # total as each chunk is handed over.
        session: dict[str, Any] = {"messages": [{"role": "assistant", "content": ""}]}
        seen: list[int] = []

        def watched() -> Generator[str, None, None]:
            for part in ("```", "aaaa", "bbbbbb"):
                seen.append(session.get("_stream_received_chars", -1))
                yield part

        assert list(_stream_suppressing_json(watched(), session)) == []
        assert seen == [0, 3, 7]
        assert session["_stream_received_chars"] == 13

    def test_fallback_would_have_read_zero(self) -> None:
        # The defect this lever fixes: with no published total, the counter
        # reads the frozen visible message and reports nothing received.
        session: dict[str, Any] = {
            "messages": [{"role": "assistant", "content": ""}],
            "_stream_received_chars": None,
        }
        assert _streamed_token_count(session) == 0

    def test_visible_stream_also_counts(self) -> None:
        session: dict[str, Any] = {}
        out = list(_stream_suppressing_json(_chunks("Hello ", "there"), session))
        assert "".join(out) == "Hello there"
        assert session["_stream_received_chars"] == 11

    def test_turn_seeded_at_zero_clearing_a_stale_total(self) -> None:
        # A prior turn's total must not be read as this turn's progress.
        session: dict[str, Any] = {"_stream_received_chars": 99999}
        assert list(_stream_suppressing_json(_chunks(), session)) == []
        assert session["_stream_received_chars"] == 0

    def test_empty_chunks_do_not_advance_counter(self) -> None:
        session: dict[str, Any] = {}
        list(_stream_suppressing_json(_chunks("```", "", "", "ab"), session))
        assert session["_stream_received_chars"] == 5

    def test_no_session_leaves_behaviour_unchanged(self) -> None:
        # D-SC60(b): the optional-session path. Every production caller now
        # passes one (brainstormer was the last holdout), but the default must
        # keep working for a caller that only wants the suppression.
        out = list(_stream_suppressing_json(_chunks("Hello ", "there")))
        assert "".join(out) == "Hello there"
        suppressed = list(_stream_suppressing_json(_chunks("```json\n", "{}")))
        assert suppressed == []
