"""The Deployer chars counter.

Deployer was gated on in ``_TOKEN_COUNTER_AGENTS`` but published no total, so it
ran on ``_streamed_token_count``'s displayed-message fallback. That fallback is
only accurate while a turn is a single stream yielding exactly what the visible
assistant message holds — and the greenfield README beat is neither: it yields
an authoring note between two ``stream_turn`` calls, and the second call starts
a fresh assistant message, so the counter dropped back to near zero mid-turn.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from spec4.agents import deployer
from spec4.agents._utils import _stream_counting
from spec4.app_constants import STATE_DEPLOYER_COMPLETE
from spec4.layouts._chat import _streamed_token_count, _token_count_text

_PLAN = "# Deploy\n\n## Deployment Steps\n\nUse Cloud Run.\n"
_README = "# Project\n\nA thing that does things.\n"


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
        "active_agent": "deployer",
        "deployer_messages": [
            {"role": "user", "content": "plan it"},
            {"role": "assistant", "content": "Sure."},
        ],
        "working_dir": None,
    }
    session.update(extra)
    return session


class TestStreamCounting:
    """The pass-through counterpart to ``_stream_suppressing_json``."""

    def test_yields_chunks_unchanged_and_counts(self) -> None:
        session: dict[str, Any] = {}
        out = list(_stream_counting(iter(("Hello ", "there")), session))
        assert "".join(out) == "Hello there"
        assert session["_stream_received_chars"] == 11

    def test_returns_the_total_for_seeding_the_next_stream(self) -> None:
        # `received = yield from _stream_counting(...)` is how Deployer carries
        # the first stream's total into the second one's seed.
        session: dict[str, Any] = {}
        captured: list[int] = []

        def _consume() -> Any:
            captured.append(
                (yield from _stream_counting(iter(("abc", "de")), session))
            )

        list(_consume())
        assert captured == [5]

    def test_seed_offsets_the_total(self) -> None:
        session: dict[str, Any] = {}
        list(_stream_counting(iter(("abc",)), session, seed=100))
        assert session["_stream_received_chars"] == 103

    def test_turn_seeded_before_the_first_chunk(self) -> None:
        # A prior turn's total must not be read as this turn's progress.
        session: dict[str, Any] = {"_stream_received_chars": 99999}
        list(_stream_counting(iter(()), session))
        assert session["_stream_received_chars"] == 0

    def test_empty_chunks_do_not_advance_counter(self) -> None:
        session: dict[str, Any] = {}
        list(_stream_counting(iter(("ab", "", "", "c")), session))
        assert session["_stream_received_chars"] == 3


class TestDeployerPublishesReceipt:
    def test_plain_turn_publishes_a_total(self) -> None:
        session = _session()
        with (
            patch.object(
                deployer.llm, "build_system_prompt", return_value=""
            ),
            patch.object(
                deployer.llm, "stream_turn", _fake_stream("How ", "about GCP?")
            ),
        ):
            out = list(deployer.run("go", session, {"model": "x"}))
        assert "".join(out) == "How about GCP?"
        assert session["_stream_received_chars"] == 14
        assert _token_count_text(session) == "Chars received: 14"


class TestReadmeBeatStaysMonotonic:
    """The regression: two streams and a yielded note inside one turn."""

    def _run(self, session: dict[str, Any], seen: list[int]) -> list[str]:
        replies = iter((_PLAN, _README))

        def _stream(*args: Any, **kwargs: Any) -> Any:
            inner = _fake_stream(next(replies))(*args, **kwargs)

            def _watched() -> Any:
                for chunk in inner:
                    yield chunk
                    seen.append(session["_stream_received_chars"])

            return _watched()

        with (
            patch.object(
                deployer.llm, "build_system_prompt", return_value=""
            ),
            patch.object(deployer.llm, "stream_turn", _stream),
        ):
            return list(deployer.run("go", session, {"model": "x"}))

    def test_counter_never_goes_backwards_across_the_two_streams(self) -> None:
        session = _session(
            _deployer_readme_optin_done=True,
            _deployer_readme_requested=True,
        )
        seen: list[int] = []
        out = self._run(session, seen)

        # The beat really did run: plan, note, README.
        assert deployer._README_AUTHORING_NOTE in "".join(out)
        assert session["deployer_state"] == STATE_DEPLOYER_COMPLETE
        assert session["_deployer_readme_markdown"] == _README

        assert seen == sorted(seen), f"counter went backwards: {seen}"
        assert session["_stream_received_chars"] == (
            len(_PLAN) + len(deployer._README_AUTHORING_NOTE) + len(_README)
        )

    def test_fallback_would_have_dipped(self) -> None:
        # The defect: with no published total the counter reads the visible
        # message, which the second stream replaces with a much shorter one.
        session: dict[str, Any] = {
            "active_agent": "deployer",
            "_stream_received_chars": None,
            "messages": [{"role": "assistant", "content": "ab"}],
        }
        assert _streamed_token_count(session) == 2
