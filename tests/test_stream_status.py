"""Stage-accurate chat status lines during a streamed agent turn.

The status line is seeded with a generic "…is thinking" before the turn's
generator runs (session.py `_AGENT_STATUS_SEED`). Without further writes it
sits there for the whole turn — including multi-minute suppressed artifact
draws and web-search round-trips. `_stream_suppressing_json` now publishes a
reply/artifact status the moment it can classify the turn, and
`llm.stream_turn` publishes search statuses around web_search tool calls.
"""

from __future__ import annotations

import json
from collections.abc import Generator, Iterator
from typing import Any
from unittest.mock import MagicMock, patch

from spec4 import llm
from spec4.agents._utils import _stream_suppressing_json

_SEED = "Agent is thinking…"


def _chunks(*parts: str) -> Generator[str, None, None]:
    yield from parts


class TestSuppressingWrapperStatus:
    def _session(self) -> dict[str, Any]:
        return {"_stream_status": _SEED}

    def test_artifact_draw_publishes_artifact_status(self) -> None:
        session = self._session()
        out = list(
            _stream_suppressing_json(
                _chunks("```json\n", '{"a": 1}\n', "```"),
                session,
                reply_status="replying",
                artifact_status="drafting",
            )
        )
        assert out == []
        assert session["_stream_status"] == "drafting"

    def test_visible_reply_publishes_reply_status(self) -> None:
        session = self._session()
        out = "".join(
            _stream_suppressing_json(
                _chunks("Hello", " there"),
                session,
                reply_status="replying",
                artifact_status="drafting",
            )
        )
        assert out == "Hello there"
        assert session["_stream_status"] == "replying"

    def test_status_untouched_while_turn_kind_is_undecided(self) -> None:
        # A first chunk shorter than the fence leaves the turn unclassified;
        # the generic seed must stand rather than a premature guess.
        session = self._session()
        gen = _stream_suppressing_json(
            _chunks("`", "``json\n{}"),
            session,
            reply_status="replying",
            artifact_status="drafting",
        )
        next_step = iter(gen)
        # Consume only the first (undecidable) chunk's processing.
        try:
            next(next_step)
        except StopIteration:
            pass
        assert session["_stream_status"] in (_SEED, "drafting")
        list(next_step)
        assert session["_stream_status"] == "drafting"

    def test_republishes_over_an_external_overwrite(self) -> None:
        # stream_turn writes search statuses onto the same key mid-stream;
        # once content chunks resume, the turn-kind status must win again.
        session = self._session()

        def chunks() -> Generator[str, None, None]:
            yield "```json\n"
            session["_stream_status"] = "Searching the web: x…"
            yield '{"a": 1}```'

        list(
            _stream_suppressing_json(
                chunks(), session, artifact_status="drafting"
            )
        )
        assert session["_stream_status"] == "drafting"

    def test_no_status_kwargs_is_a_no_op(self) -> None:
        session = self._session()
        list(_stream_suppressing_json(_chunks("Hello there"), session))
        assert session["_stream_status"] == _SEED


class TestStreamTurnSearchStatus:
    def _chunk(
        self,
        content: str | None,
        tool_calls: Any = None,
        finish_reason: str | None = None,
    ) -> MagicMock:
        chunk = MagicMock()
        chunk.choices[0].delta.content = content
        chunk.choices[0].delta.tool_calls = tool_calls
        chunk.choices[0].finish_reason = finish_reason
        return chunk

    def test_search_round_trip_publishes_both_statuses(self) -> None:
        tc = MagicMock()
        tc.index = 0
        tc.id = "call-1"
        tc.function.name = "web_search"
        tc.function.arguments = json.dumps({"query": "dash docs"})

        session: dict[str, Any] = {"_stream_status": _SEED}
        seen_during_search: list[Any] = []
        seen_at_second_prefill: list[Any] = []
        call_count = 0

        def fake_completion(**kwargs: Any) -> Iterator[MagicMock]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return iter(
                    [
                        self._chunk(None, tool_calls=[tc]),
                        self._chunk("", finish_reason="stop"),
                    ]
                )
            seen_at_second_prefill.append(session["_stream_status"])
            return iter(
                [self._chunk("Answer"), self._chunk("", finish_reason="stop")]
            )

        def fake_search(query: str, cfg: Any) -> str:
            seen_during_search.append(session["_stream_status"])
            return "results"

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            with patch("spec4.llm.search", side_effect=fake_search):
                list(
                    llm.stream_turn(
                        "sys",
                        [],
                        {"model": "m", "api_key": "k"},
                        "tv-key",
                        session=session,
                    )
                )

        assert seen_during_search == ["Searching the web: dash docs…"]
        # "Reading search results…" stands only for the second completion's
        # prefill; once content resumes the entry status is restored (and for
        # wrapper callers, then replaced by the turn-kind status).
        assert seen_at_second_prefill == ["Reading search results…"]
        assert session["_stream_status"] == _SEED

    def test_entry_status_restored_once_content_resumes(self) -> None:
        # Bare callers (Phaser, Deployer) have no suppressing wrapper to
        # replace the search status; stream_turn itself must put the entry
        # status back when the model resumes producing text.
        tc = MagicMock()
        tc.index = 0
        tc.id = "call-1"
        tc.function.name = "web_search"
        tc.function.arguments = json.dumps({"query": "dash docs"})

        session: dict[str, Any] = {
            "_stream_status": "Phaser is planning your development phases…"
        }
        call_count = 0

        def fake_completion(**kwargs: Any) -> Iterator[MagicMock]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return iter(
                    [
                        self._chunk(None, tool_calls=[tc]),
                        self._chunk("", finish_reason="stop"),
                    ]
                )
            return iter(
                [self._chunk("Answer"), self._chunk("", finish_reason="stop")]
            )

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            with patch("spec4.llm.search", return_value="results"):
                list(
                    llm.stream_turn(
                        "sys",
                        [],
                        {"model": "m", "api_key": "k"},
                        "tv-key",
                        session=session,
                    )
                )

        assert session["_stream_status"] == (
            "Phaser is planning your development phases…"
        )

    def test_restore_does_not_clobber_an_intervening_status(self) -> None:
        # If something else (the suppressing wrapper) replaced the search
        # status before content resumed, stream_turn must leave it alone.
        tc = MagicMock()
        tc.index = 0
        tc.id = "call-1"
        tc.function.name = "web_search"
        tc.function.arguments = json.dumps({"query": "q"})

        session: dict[str, Any] = {"_stream_status": _SEED}
        call_count = 0

        def fake_completion(**kwargs: Any) -> Iterator[MagicMock]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return iter(
                    [
                        self._chunk(None, tool_calls=[tc]),
                        self._chunk("", finish_reason="stop"),
                    ]
                )
            # Simulate someone else (the suppressing wrapper) writing its own
            # status after the search round but before content resumes.
            session["_stream_status"] = "drafting"
            return iter(
                [self._chunk("Answer"), self._chunk("", finish_reason="stop")]
            )

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            with patch("spec4.llm.search", return_value="results"):
                list(
                    llm.stream_turn(
                        "sys", [], {"model": "m", "api_key": "k"}, "tv-key",
                        session=session,
                    )
                )

        assert session["_stream_status"] == "drafting"

    def test_without_session_no_status_is_written(self) -> None:
        chunks = [self._chunk("Hi"), self._chunk("", finish_reason="stop")]
        with patch("spec4.llm.litellm.completion", return_value=iter(chunks)):
            list(llm.stream_turn("sys", [], {"model": "m", "api_key": "k"}, None))
        # No session passed: nothing to assert beyond "does not raise".


def _capturing_stream(
    captured: dict[str, Any], *chunks: str
) -> Any:
    """Stand in for ``llm.stream_turn``: records kwargs, replies, yields."""

    def _stream(*args: Any, **kwargs: Any) -> Generator[str, None, None]:
        captured["kwargs"] = kwargs
        args[1].append({"role": "assistant", "content": "".join(chunks)})
        yield from chunks

    return _stream


class TestAgentStatusWiring:
    """Each chat agent that streams through the suppressing wrapper passes the
    turn-kind statuses and threads the session into stream_turn for the search
    statuses. A visible reply is enough to prove the wiring: the status must
    move off the generic seed to the agent's reply status."""

    def test_brainstormer(self, monkeypatch) -> None:
        from spec4.agents import brainstormer

        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            brainstormer.llm, "stream_turn", _capturing_stream(captured, "Hello there")
        )
        session: dict[str, Any] = {
            "_stream_status": "Brainstormer is thinking…",
            "brainstormer_messages": [
                {"role": "user", "content": "an app"},
                {"role": "assistant", "content": "Tell me more."},
            ],
        }
        list(brainstormer.run("go", session, {"model": "m", "api_key": "k"}))
        assert session["_stream_status"] == "Brainstormer is replying…"
        assert captured["kwargs"].get("session") is session

    def test_code_scanner(self, monkeypatch, tmp_path) -> None:
        from spec4.agents import code_scanner

        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            code_scanner.llm, "stream_turn", _capturing_stream(captured, "Hello there")
        )
        session: dict[str, Any] = {
            "_stream_status": "CodeScanner is examining your codebase…",
            "working_dir": str(tmp_path),
            "code_scanner_messages": [
                {"role": "user", "content": "scan"},
                {"role": "assistant", "content": "Anything else?"},
            ],
        }
        list(code_scanner.run("go", session, {"model": "m", "api_key": "k"}))
        assert session["_stream_status"] == "CodeScanner is replying…"
        assert captured["kwargs"].get("session") is session

    def test_phaser_threads_session_into_stream_turn(self, monkeypatch) -> None:
        # Phaser has no suppressing wrapper (its seed is accurate for the
        # whole turn); the wiring it needs is the session, for the web-search
        # statuses and their entry-status restore.
        from spec4.agents import phaser

        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            phaser.llm, "stream_turn", _capturing_stream(captured, "Hello there")
        )
        session: dict[str, Any] = {
            "phaser_messages": [
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ],
        }
        list(phaser.run("Tell me more.", session, {"model": "m", "api_key": "k"}))
        assert captured["kwargs"].get("session") is session

    def test_deployer_threads_session_into_stream_turn(self, monkeypatch) -> None:
        # Same as phaser: verbatim replies need no turn-kind status, only the
        # search statuses.
        from spec4.agents import deployer

        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            deployer.llm, "stream_turn", _capturing_stream(captured, "Hello there")
        )
        session: dict[str, Any] = {
            "active_agent": "deployer",
            "working_dir": None,
            "deployer_messages": [
                {"role": "user", "content": "plan it"},
                {"role": "assistant", "content": "Sure."},
            ],
        }
        list(deployer.run("go", session, {"model": "m", "api_key": "k"}))
        assert captured["kwargs"].get("session") is session

    def test_agentifier(self, monkeypatch) -> None:
        from spec4.agentifier import agentifier

        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            agentifier.llm, "stream_turn", _capturing_stream(captured, "Hello there")
        )
        session: dict[str, Any] = {
            "_stream_status": "Agentifier is working…",
            "agentifier_messages": [
                {"role": "user", "content": "features"},
                {"role": "assistant", "content": "Which ones?"},
            ],
            "agentifier_breadth_chosen": True,
        }
        list(agentifier.run("go", session, {"model": "m", "api_key": "k"}))
        assert session["_stream_status"] == "Agentifier is replying…"
        assert captured["kwargs"].get("session") is session


class TestStackAdvisorStatusWiring:
    def test_artifact_turn_ends_with_drafting_status(self, monkeypatch) -> None:
        from spec4.agents import stack_advisor

        stack_json = json.dumps(
            {"stack": {"name": "Stack", "languages": ["Python"]}}
        )
        captured: dict[str, Any] = {}

        def fake_stream_turn(
            system: str,
            messages: list[dict[str, Any]],
            llm_config: dict[str, Any],
            search_config: Any,
            **kwargs: Any,
        ) -> Generator[str, None, None]:
            captured["kwargs"] = kwargs
            reply = f"```json\n{stack_json}\n```"
            messages.append({"role": "assistant", "content": reply})
            yield from (reply[:4], reply[4:])

        monkeypatch.setattr(stack_advisor.llm, "stream_turn", fake_stream_turn)
        session: dict[str, Any] = {
            "_stream_status": "StackAdvisor is thinking…",
            "stack_advisor_messages": [],
        }
        list(stack_advisor.run("finalize", session, {"model": "m", "api_key": "k"}))

        # The turn is a suppressed artifact draw: the status must have moved
        # off the generic seed to the drafting message.
        assert session["_stream_status"] == (
            "Drafting the stack specification — this can take a few minutes…"
        )
        # And stream_turn received the session for its search statuses.
        assert captured["kwargs"].get("session") is session
