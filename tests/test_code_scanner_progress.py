"""D-SC-P1: CodeScanner progress feedback.

Covers:
- The directory walk is narrated instead of running silently.
- The chars counter is gated on for code_scanner and rendered in the bar.
- The published char total is seeded with the pre-stream progress text and
  keeps climbing through the silent validation-retry drain.
- The progress bar renders while a scan is in flight.
"""

from __future__ import annotations

import pathlib
from typing import Any
from unittest.mock import patch

import dash_mantine_components as dmc

from spec4.agents import code_scanner
from spec4.app_constants import STATE_IN_PROGRESS, STATE_REVIEW_COMPLETE
from spec4.layouts._chat import (
    _TOKEN_COUNTER_AGENTS,
    _chat_action_buttons,
    _chat_layout,
    _token_count_text,
)


def _make_project(tmp_path: pathlib.Path) -> str:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    (tmp_path / "README.md").write_text("# X\n\nA thing.\n")
    (tmp_path / "main.py").write_text("print('hi')\n")
    skipped = tmp_path / "node_modules" / "dep"
    skipped.mkdir(parents=True, exist_ok=True)
    (skipped / "index.js").write_text("module.exports = {}\n")
    return str(tmp_path)


def _session(working_dir: str) -> dict[str, Any]:
    return {
        "active_agent": "code_scanner",
        "working_dir": working_dir,
        "code_scanner_messages": [],
        "code_scanner_state": STATE_IN_PROGRESS,
    }


def _fake_stream(*chunks: str) -> Any:
    def _stream(*args: Any, **kwargs: Any) -> Any:
        msgs = args[1]

        def _gen() -> Any:
            for c in chunks:
                yield c

        text = "".join(chunks)
        msgs.append({"role": "assistant", "content": text})
        return _gen()

    return _stream


# ---------------------------------------------------------------------------
# _collect_files — the walk, split out so run() can report on it
# ---------------------------------------------------------------------------


class TestCollectFiles:
    def test_returns_project_files(self, tmp_path: pathlib.Path) -> None:
        root = pathlib.Path(_make_project(tmp_path))
        names = {p.name for p in code_scanner._collect_files(root)}
        assert {"pyproject.toml", "README.md", "main.py"} <= names

    def test_skips_vendored_directories(self, tmp_path: pathlib.Path) -> None:
        root = pathlib.Path(_make_project(tmp_path))
        rels = {
            str(p.relative_to(root)) for p in code_scanner._collect_files(root)
        }
        assert not any(r.startswith("node_modules") for r in rels)

    def test_empty_directory_returns_empty_list(
        self, tmp_path: pathlib.Path
    ) -> None:
        assert code_scanner._collect_files(tmp_path) == []

    def test_context_accepts_a_precomputed_walk(
        self, tmp_path: pathlib.Path
    ) -> None:
        # run() walks the tree itself to report the count, then hands the
        # result to the formatter — the tree must not be walked twice.
        root = pathlib.Path(_make_project(tmp_path))
        files = code_scanner._collect_files(root)
        with patch.object(
            code_scanner, "_collect_files", side_effect=AssertionError("re-walked")
        ):
            context = code_scanner._gather_project_context(str(root), files)
        assert "pyproject.toml" in context

    def test_context_still_walks_when_not_supplied(
        self, tmp_path: pathlib.Path
    ) -> None:
        root = _make_project(tmp_path)
        assert "pyproject.toml" in code_scanner._gather_project_context(root)


# ---------------------------------------------------------------------------
# run() — the scan is narrated
# ---------------------------------------------------------------------------


class TestScanIsNarrated:
    def test_first_chunk_arrives_before_the_walk(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The intro must be yielded before the (slow) walk, not after it."""
        root = _make_project(tmp_path)
        session = _session(root)
        seen: list[str] = []

        def _slow_walk(path: pathlib.Path) -> list[pathlib.Path]:
            # Anything already yielded got to the user before the walk ran.
            assert seen, "nothing was yielded before the directory walk"
            return []

        with patch.object(code_scanner, "_collect_files", _slow_walk):
            with patch.object(
                code_scanner.llm, "stream_turn", _fake_stream("draft")
            ):
                for chunk in code_scanner.run(None, session, {"model": "m"}):
                    seen.append(chunk)

    def test_narration_names_the_directory(self, tmp_path: pathlib.Path) -> None:
        root = _make_project(tmp_path)
        session = _session(root)
        with patch.object(
            code_scanner.llm, "stream_turn", _fake_stream("draft")
        ):
            out = "".join(code_scanner.run(None, session, {"model": "m"}))
        assert "Scanning" in out
        assert root in out

    def test_narration_reports_the_file_count(
        self, tmp_path: pathlib.Path
    ) -> None:
        root = _make_project(tmp_path)
        n = len(code_scanner._collect_files(pathlib.Path(root)))
        session = _session(root)
        with patch.object(
            code_scanner.llm, "stream_turn", _fake_stream("draft")
        ):
            out = "".join(code_scanner.run(None, session, {"model": "m"}))
        assert f"**{n}** files" in out

    def test_narration_closes_before_the_llm_text(
        self, tmp_path: pathlib.Path
    ) -> None:
        root = _make_project(tmp_path)
        session = _session(root)
        with patch.object(
            code_scanner.llm, "stream_turn", _fake_stream("DRAFT-BODY")
        ):
            out = "".join(code_scanner.run(None, session, {"model": "m"}))
        assert out.index("Scan complete") < out.index("DRAFT-BODY")

    def test_rescan_says_rescanning(self, tmp_path: pathlib.Path) -> None:
        root = _make_project(tmp_path)
        session = _session(root)
        session["code_review"] = {"code_review": {"schema_version": 1}}
        with patch.object(
            code_scanner.llm, "stream_turn", _fake_stream("draft")
        ):
            out = "".join(code_scanner.run(None, session, {"model": "m"}))
        assert "Re-scanning" in out

    def test_narration_is_absent_on_conversation_turns(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Only the seeded scan turn narrates; follow-up replies must not."""
        root = _make_project(tmp_path)
        session = _session(root)
        session["code_scanner_messages"] = [
            {"role": "user", "content": "seed"},
            {"role": "assistant", "content": "draft"},
        ]
        with patch.object(
            code_scanner.llm, "stream_turn", _fake_stream("reply")
        ):
            out = "".join(
                code_scanner.run("fix the UI section", session, {"model": "m"})
            )
        assert "Scanning" not in out
        assert out == "reply"

    def test_no_working_dir_still_short_circuits(self) -> None:
        session: dict[str, Any] = {
            "active_agent": "code_scanner",
            "code_scanner_messages": [],
        }
        out = "".join(code_scanner.run(None, session, {"model": "m"}))
        assert "No project directory" in out
        assert "Scanning" not in out


# ---------------------------------------------------------------------------
# The published chars total
# ---------------------------------------------------------------------------


class TestCharsTotal:
    def test_total_covers_the_whole_turn(self, tmp_path: pathlib.Path) -> None:
        root = _make_project(tmp_path)
        session = _session(root)
        with patch.object(
            code_scanner.llm, "stream_turn", _fake_stream("abc", "defg")
        ):
            out = "".join(code_scanner.run(None, session, {"model": "m"}))
        # Narration + every streamed chunk, not just the LLM's output.
        assert session["_stream_received_chars"] == len(out)

    def test_total_exceeds_the_llm_output_alone(
        self, tmp_path: pathlib.Path
    ) -> None:
        root = _make_project(tmp_path)
        session = _session(root)
        with patch.object(
            code_scanner.llm, "stream_turn", _fake_stream("draft")
        ):
            list(code_scanner.run(None, session, {"model": "m"}))
        assert session["_stream_received_chars"] > len("draft")

    def test_total_is_monotonic_across_the_handover(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The counter must never drop when the LLM stream opens."""
        root = _make_project(tmp_path)
        session = _session(root)
        seen: list[int] = []
        with patch.object(
            code_scanner.llm, "stream_turn", _fake_stream("a", "b", "c")
        ):
            for _ in code_scanner.run(None, session, {"model": "m"}):
                seen.append(session.get("_stream_received_chars") or 0)
        assert seen == sorted(seen)

    def test_total_climbs_through_the_retry_drain(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The retry yields nothing visible; the counter must still advance."""
        root = _make_project(tmp_path)
        session = _session(root)
        bad = '```json\n{"code_review": {"schema_version": 1}}\n```'
        good = (
            '{"code_review": {"schema_version": 1, '
            '"is_software_project": false, "summary": "empty"}}'
        )
        calls: list[int] = []
        totals: list[int] = []

        def _stream(*args: Any, **kwargs: Any) -> Any:
            msgs = args[1]
            calls.append(1)
            body = bad if len(calls) == 1 else good
            msgs.append({"role": "assistant", "content": body})

            def _gen() -> Any:
                for i in range(0, len(body), 10):
                    if len(calls) > 1:
                        totals.append(session.get("_stream_received_chars") or 0)
                    yield body[i : i + 10]

            return _gen()

        with patch.object(code_scanner.llm, "stream_turn", _stream):
            with patch.object(
                code_scanner.llm, "supports_response_format", lambda m: False
            ):
                list(code_scanner.run(None, session, {"model": "m"}))

        assert len(calls) == 2, "the invalid review should have triggered one retry"
        assert len(totals) > 1
        assert totals == sorted(totals)
        assert totals[-1] > totals[0], "counter froze during the retry drain"


# ---------------------------------------------------------------------------
# Layout — counter and progress bar
# ---------------------------------------------------------------------------


def _progress_display(session: dict[str, Any]) -> str:
    layout = _chat_layout(session)
    container = next(
        c
        for c in layout.children
        if getattr(c, "id", None) == "chat-progress-container"
    )
    return str(container.style["display"])


def _bar_children(session: dict[str, Any]) -> list[Any]:
    bar = _chat_action_buttons(session)
    children = getattr(bar, "children", None) or []
    if not children:
        return []
    return list(children[1].children)


class TestLayout:
    def test_code_scanner_is_gated_on(self) -> None:
        assert "code_scanner" in _TOKEN_COUNTER_AGENTS

    def test_label_is_chars_received(self) -> None:
        session = {
            "active_agent": "code_scanner",
            "_stream_id": "abc",
            "_stream_received_chars": 4210,
            "messages": [{"role": "assistant", "content": ""}],
        }
        assert _token_count_text(session) == "Chars received: 4210"

    def test_progress_bar_shows_while_scanning(self) -> None:
        session = {
            "active_agent": "code_scanner",
            "code_scanner_state": STATE_IN_PROGRESS,
            "_stream_id": "abc",
            "messages": [{"role": "assistant", "content": ""}],
        }
        assert _progress_display(session) == "block"

    def test_progress_bar_hidden_when_idle(self) -> None:
        session = {
            "active_agent": "code_scanner",
            "code_scanner_state": STATE_REVIEW_COMPLETE,
            "messages": [{"role": "assistant", "content": "done"}],
        }
        assert _progress_display(session) == "none"

    def test_counter_renders_while_scanning(self) -> None:
        session = {
            "active_agent": "code_scanner",
            "code_scanner_state": STATE_IN_PROGRESS,
            "_stream_id": "abc",
            "_stream_received_chars": 512,
            "messages": [{"role": "assistant", "content": ""}],
        }
        texts = [
            c
            for c in _bar_children(session)
            if getattr(c, "id", "") == "chat-token-count"
        ]
        assert len(texts) == 1
        assert texts[0].children == "Chars received: 512"

    def test_scanning_bar_carries_only_the_two_readouts(self) -> None:
        session = {
            "active_agent": "code_scanner",
            "code_scanner_state": STATE_IN_PROGRESS,
            "_stream_id": "abc",
            "_stream_received_chars": 512,
            "messages": [{"role": "assistant", "content": ""}],
        }
        children = _bar_children(session)
        assert [getattr(c, "id", "") for c in children] == [
            "chat-token-count",
            "chat-elapsed",
        ]
        assert all(isinstance(c, dmc.Text) for c in children)

    def test_no_empty_bar_before_the_scan_starts(self) -> None:
        """No stream and no chars yet — the bar must stay absent, not empty."""
        session = {
            "active_agent": "code_scanner",
            "code_scanner_state": STATE_IN_PROGRESS,
            "messages": [],
        }
        assert _bar_children(session) == []

    def test_complete_state_keeps_its_buttons_and_gains_the_counter(self) -> None:
        session = {
            "active_agent": "code_scanner",
            "code_scanner_state": STATE_REVIEW_COMPLETE,
            "_stream_received_chars": 9001,
            "messages": [{"role": "assistant", "content": "done"}],
        }
        ids = [getattr(c, "id", "") for c in _bar_children(session)]
        assert ids == [
            "chat-token-count",
            "chat-elapsed",
            "btn-dl-review",
            "btn-rescan-project",
            "btn-review-to-brainstormer",
        ]

    def test_elapsed_sits_beside_the_counter_in_the_action_row(self) -> None:
        """It moved out of the progress container to share the readout row."""
        session = {
            "active_agent": "code_scanner",
            "code_scanner_state": STATE_IN_PROGRESS,
            "_stream_id": "abc",
            "messages": [{"role": "assistant", "content": ""}],
        }
        ids = [getattr(c, "id", "") for c in _bar_children(session)]
        assert ids.index("chat-elapsed") == ids.index("chat-token-count") + 1

        layout = _chat_layout(session)
        container = next(
            c
            for c in layout.children
            if getattr(c, "id", None) == "chat-progress-container"
        )
        assert "chat-elapsed" not in [
            getattr(c, "id", None) for c in container.children
        ]

    def test_the_two_readouts_are_styled_alike(self) -> None:
        session = {
            "active_agent": "code_scanner",
            "code_scanner_state": STATE_IN_PROGRESS,
            "_stream_id": "abc",
            "_stream_received_chars": 512,
            "messages": [{"role": "assistant", "content": ""}],
        }
        by_id = {getattr(c, "id", ""): c for c in _bar_children(session)}
        counter, elapsed = by_id["chat-token-count"], by_id["chat-elapsed"]
        assert elapsed.size == counter.size
        assert elapsed.c == counter.c

    def test_elapsed_readout_starts_empty(self) -> None:
        """The server cannot tick; the client owns the text for the stream."""
        session = {
            "active_agent": "code_scanner",
            "_stream_id": "abc",
            "messages": [{"role": "assistant", "content": ""}],
        }
        elapsed = next(
            c
            for c in _bar_children(session)
            if getattr(c, "id", None) == "chat-elapsed"
        )
        assert elapsed.children == ""

    def test_elapsed_renders_even_when_the_agent_has_no_buttons(self) -> None:
        """Pre-panel Agentifier contributes nothing to the row (D-AT5), but a
        live stream still needs somewhere to show its elapsed time."""
        session = {
            "active_agent": "agentifier",
            "_stream_id": "abc",
            "messages": [{"role": "assistant", "content": ""}],
        }
        ids = [getattr(c, "id", "") for c in _bar_children(session)]
        assert ids == ["chat-elapsed"]

    def test_no_row_when_idle_and_buttonless(self) -> None:
        session = {"active_agent": "agentifier", "messages": []}
        assert _bar_children(session) == []

    def test_exactly_one_counter_per_bar(self) -> None:
        for state in (STATE_IN_PROGRESS, STATE_REVIEW_COMPLETE):
            session = {
                "active_agent": "code_scanner",
                "code_scanner_state": state,
                "_stream_id": "abc",
                "_stream_received_chars": 12,
                "messages": [{"role": "assistant", "content": ""}],
            }
            ids = [getattr(c, "id", "") for c in _bar_children(session)]
            assert ids.count("chat-token-count") == 1


# ---------------------------------------------------------------------------
# D-SC-P2 — naming the wait
# ---------------------------------------------------------------------------


class TestApproxTokens:
    def test_four_chars_per_token(self) -> None:
        assert code_scanner._approx_tokens("x" * 400) == 100

    def test_empty_string(self) -> None:
        assert code_scanner._approx_tokens("") == 0


class TestWaitIsNamed:
    def _narration(self, tmp_path: pathlib.Path, llm_config: dict[str, Any]) -> str:
        root = _make_project(tmp_path)
        session = _session(root)
        with patch.object(
            code_scanner.llm, "stream_turn", _fake_stream("BODY")
        ):
            out = "".join(code_scanner.run(None, session, llm_config))
        return out[: out.index("BODY")]

    def test_names_the_model(self, tmp_path: pathlib.Path) -> None:
        out = self._narration(tmp_path, {"model": "claude-opus-5"})
        assert "`claude-opus-5`" in out

    def test_falls_back_when_no_model_configured(
        self, tmp_path: pathlib.Path
    ) -> None:
        out = self._narration(tmp_path, {})
        assert "the configured model" in out

    def test_reports_the_request_size(self, tmp_path: pathlib.Path) -> None:
        root = _make_project(tmp_path)
        files = code_scanner._collect_files(pathlib.Path(root))
        seed = code_scanner._build_fresh_scan_seed(root, files)
        system = code_scanner.llm.build_system_prompt(
            code_scanner.SYSTEM_PROMPT, None
        )
        expected = code_scanner._approx_tokens(system) + code_scanner._approx_tokens(
            seed
        )
        out = self._narration(tmp_path, {"model": "m"})
        assert f"~{expected:,} tokens" in out

    def test_size_covers_the_system_prompt_not_just_the_seed(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The system prompt is the larger half of the request — it must count."""
        root = _make_project(tmp_path)
        files = code_scanner._collect_files(pathlib.Path(root))
        seed_only = code_scanner._approx_tokens(
            code_scanner._build_fresh_scan_seed(root, files)
        )
        out = self._narration(tmp_path, {"model": "m"})
        assert f"~{seed_only:,} tokens" not in out

    def test_sets_the_expectation_of_a_wait(self, tmp_path: pathlib.Path) -> None:
        out = self._narration(tmp_path, {"model": "m"})
        assert "Waiting for the first response" in out


class TestElapsedTicker:
    """The ticker is client-side; assert it is wired, not what it renders."""

    def _app(self) -> Any:
        from spec4.app import app

        return app

    def _walk_ids(self, component: Any, out: list[Any]) -> None:
        if hasattr(component, "id"):
            out.append(component.id)
        children = getattr(component, "children", None)
        if isinstance(children, (list, tuple)):
            for child in children:
                self._walk_ids(child, out)
        elif children is not None:
            self._walk_ids(children, out)

    def test_start_timestamp_store_exists(self) -> None:
        ids: list[Any] = []
        self._walk_ids(self._app().layout, ids)
        assert "stream-start-ts" in ids

    def _ticker(self) -> dict[str, Any]:
        return next(
            c
            for c in self._app()._callback_list
            if str(c.get("output")) == "stream-start-ts.data"
        )

    @staticmethod
    def _refs(spec: Any) -> set[tuple[str, str]]:
        return {(d["id"], d["property"]) for d in (spec or [])}

    def test_ticker_is_clientside(self) -> None:
        assert self._ticker().get("clientside_function")

    def test_ticker_is_driven_by_the_poll_interval(self) -> None:
        assert ("stream-poll-interval", "n_intervals") in self._refs(
            self._ticker().get("inputs")
        )

    def test_ticker_repaints_after_every_render(self) -> None:
        # Each re-render recreates chat-elapsed with the server's empty text.
        assert ("_last_render", "data") in self._refs(self._ticker().get("inputs"))

    def test_ticker_reads_the_session_without_depending_on_it(self) -> None:
        # As an Input, every session change would re-fire it; State is correct.
        cb = self._ticker()
        assert ("session", "data") in self._refs(cb.get("state"))
        assert ("session", "data") not in self._refs(cb.get("inputs"))
