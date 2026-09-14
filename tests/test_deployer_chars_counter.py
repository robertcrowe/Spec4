"""The Deployer chars counter.

Deployer was gated on in ``_TOKEN_COUNTER_AGENTS`` but published no total, so it
ran on ``streamed_token_count``'s displayed-message fallback. That fallback is
only accurate while a turn is a single stream yielding exactly what the visible
assistant message holds — and the README beat is neither: the README is drained,
not shown, so its characters never reach the visible message and the fallback
would stand still for the whole authoring draw. On the greenfield path that draw
is a second ``stream_turn`` after the plan's, in the same turn.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from spec4.agents import deployer
from spec4.agents._reask import stream_counting
from spec4.app_constants import STATE_DEPLOYER_COMPLETE
from spec4.layouts._chat import streamed_token_count, token_count_text

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
    """The pass-through counterpart to ``stream_suppressing_json``."""

    def test_yields_chunks_unchanged_and_counts(self) -> None:
        session: dict[str, Any] = {}
        out = list(stream_counting(iter(("Hello ", "there")), session))
        assert "".join(out) == "Hello there"
        assert session["_stream_received_chars"] == 11

    def test_returns_the_total_for_seeding_the_next_stream(self) -> None:
        # `received = yield from _stream_counting(...)` is how Deployer carries
        # the first stream's total into the second one's seed.
        session: dict[str, Any] = {}
        captured: list[int] = []

        def _consume() -> Any:
            captured.append((yield from stream_counting(iter(("abc", "de")), session)))

        list(_consume())
        assert captured == [5]

    def test_seed_offsets_the_total(self) -> None:
        session: dict[str, Any] = {}
        list(stream_counting(iter(("abc",)), session, seed=100))
        assert session["_stream_received_chars"] == 103

    def test_turn_seeded_before_the_first_chunk(self) -> None:
        # A prior turn's total must not be read as this turn's progress.
        session: dict[str, Any] = {"_stream_received_chars": 99999}
        list(stream_counting(iter(()), session))
        assert session["_stream_received_chars"] == 0

    def test_empty_chunks_do_not_advance_counter(self) -> None:
        session: dict[str, Any] = {}
        list(stream_counting(iter(("ab", "", "", "c")), session))
        assert session["_stream_received_chars"] == 3


class TestDeployerPublishesReceipt:
    def test_plain_turn_publishes_a_total(self) -> None:
        session = _session()
        with (
            patch.object(deployer.llm, "build_system_prompt", return_value=""),
            patch.object(
                deployer.llm, "stream_turn", _fake_stream("How ", "about GCP?")
            ),
        ):
            out = list(deployer.run("go", session, {"model": "x"}))
        assert "".join(out) == "How about GCP?"
        assert session["_stream_received_chars"] == 14
        assert token_count_text(session) == "Chars received: 14"


class TestReadmeBeatStaysMonotonic:
    """The regression: two streams and a yielded note inside one turn."""

    def _run(
        self,
        session: dict[str, Any],
        seen: list[int],
        draws: tuple[str, ...] = (_PLAN, _README),
        reply: str = "go",
    ) -> list[str]:
        replies = iter(draws)

        def _stream(*args: Any, **kwargs: Any) -> Any:
            inner = _fake_stream(next(replies))(*args, **kwargs)

            def _watched() -> Any:
                for chunk in inner:
                    yield chunk
                    seen.append(session["_stream_received_chars"])

            return _watched()

        with (
            patch.object(deployer.llm, "build_system_prompt", return_value=""),
            patch.object(deployer.llm, "stream_turn", _stream),
        ):
            return list(deployer.run(reply, session, {"model": "x"}))

    def test_counter_never_goes_backwards_across_the_two_streams(self) -> None:
        session = _session(
            _deployer_readme_optin_done=True,
            _deployer_readme_requested=True,
        )
        seen: list[int] = []
        out = self._run(session, seen)

        # The beat really did run: the plan, then the written-line. The README
        # was authored into history but never yielded.
        joined = "".join(out)
        assert joined == _PLAN + "\n\n---\n\n" + deployer._README_WRITTEN
        assert _README not in joined
        assert session["deployer_state"] == STATE_DEPLOYER_COMPLETE
        assert session["_deployer_readme_markdown"] == _README

        total = len(_PLAN) + len(_README)
        assert seen == sorted(seen), f"counter went backwards: {seen}"
        # The drain published as it went: the last reading is the full total,
        # past anything the plan alone accounts for.
        assert seen[-1] == total
        assert session["_stream_received_chars"] == total

    def test_counter_climbs_through_the_opt_in_later_drain(self) -> None:
        # Opting in later, the README draw is the turn's only stream, and it is
        # drained: the counter still climbs to the README's length.
        session = _session(
            deployer_state=STATE_DEPLOYER_COMPLETE,
            _deployer_pending_readme=True,
        )
        seen: list[int] = []
        out = self._run(session, seen, draws=(_README,), reply="yes")

        assert "".join(out) == deployer._README_WRITTEN
        assert session["_deployer_readme_markdown"] == _README
        assert seen == sorted(seen), f"counter went backwards: {seen}"
        assert seen[-1] == len(_README)
        assert session["_stream_received_chars"] == len(_README)

    def test_fallback_would_have_dipped(self) -> None:
        # The defect: with no published total the counter reads the visible
        # message, which the second stream replaces with a much shorter one.
        session: dict[str, Any] = {
            "active_agent": "deployer",
            "_stream_received_chars": None,
            "messages": [{"role": "assistant", "content": "ab"}],
        }
        assert streamed_token_count(session) == 2
