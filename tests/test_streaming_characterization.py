"""The three process-global state containers, transition by transition.

Cleanup Phase 3 moves ``streaming._STREAMS``, ``llm._USAGE_RECORDS`` and
``callbacks.designer._MOCK_BUFFERS`` out of module scope. This module is the
proof that the move preserved behaviour: it drives each container through
its lifecycle with a generator the test controls chunk by chunk, and asserts
the *contents* of the container at every transition, not just the sequence.

Characterization, not specification. Where the current behaviour is odd it
is asserted as it is and recorded in ``CLEANUP_INVENTORY.md``.

Timing is controlled with ``threading.Event``s: a generator yields a chunk
then blocks until the test releases the next one, and ``_wait_until`` spins
on a predicate with a bound, so no assertion depends on a sleep.
"""

from __future__ import annotations

import json
import pathlib
import threading
import time
from collections.abc import Callable, Generator, Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from dash import no_update

from spec4 import llm, project_manager, streaming
from spec4.callbacks import designer as dmod
from spec4.callbacks import on_stream_poll
from spec4.session import _default_session
from spec4.streaming import _format_error

_CFG = {"model": "gpt-4o-mini", "api_key": "sk-test"}

_USAGE_RECORD_KEYS = {
    "timestamp",
    "agent",
    "model",
    "provider",
    "effort",
    "streamed",
    "duration_s",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cached_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "computed_cost_usd",
    "usage_missing",
    "error",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_containers() -> Iterator[None]:
    """Every test starts and ends with the three containers empty."""
    streaming._STREAMS.clear()
    llm.drain_usage_records()
    dmod._MOCK_BUFFERS.clear()
    yield
    for entry in dmod._MOCK_BUFFERS.values():
        stop = entry.get("stop")
        if stop is not None:
            stop.set()
    streaming._STREAMS.clear()
    llm.drain_usage_records()
    dmod._MOCK_BUFFERS.clear()


def _wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "timed out waiting for a transition"
        time.sleep(0.005)


class _Gated:
    """A generator that yields one chunk per ``release()`` call."""

    def __init__(self, chunks: list[str], raise_after: BaseException | None = None):
        self.chunks = chunks
        self.raise_after = raise_after
        self.gates = [threading.Event() for _ in chunks]
        self.finish = threading.Event()
        self.yielded = 0

    def release(self, n: int) -> None:
        self.gates[n].set()

    def gen(self) -> Generator[str, None, None]:
        for gate, chunk in zip(self.gates, self.chunks):
            gate.wait(5.0)
            self.yielded += 1
            yield chunk
        self.finish.wait(5.0)
        if self.raise_after is not None:
            raise self.raise_after


def _delta(text: str | None, finish: str | None = None) -> SimpleNamespace:
    choice = SimpleNamespace(
        delta=SimpleNamespace(content=text, tool_calls=None), finish_reason=finish
    )
    return SimpleNamespace(choices=[choice], usage=None, _hidden_params={})


def _usage_chunk(prompt: int = 120, completion: int = 30) -> SimpleNamespace:
    usage = SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        prompt_tokens_details=None,
    )
    return SimpleNamespace(choices=[], usage=usage, _hidden_params={})


# ---------------------------------------------------------------------------
# _STREAMS
# ---------------------------------------------------------------------------


class TestStreamsRegistry:
    def test_a_clean_stream_from_start_to_eviction(self) -> None:
        session: dict[str, Any] = {"active_agent": "brainstormer"}
        gated = _Gated(["a", "b"])
        stream_id = streaming.start(gated.gen(), session)

        # Inserted before the worker yields anything.
        assert set(streaming._STREAMS) == {stream_id}
        entry = streaming._STREAMS[stream_id]
        assert entry == {
            "text": "",
            "done": False,
            "session": session,
            "error": False,
            "finalised": False,
        }
        assert entry["session"] is session
        assert streaming.get(stream_id) is entry

        gated.release(0)
        _wait_until(lambda: entry["text"] == "a")
        assert entry["done"] is False
        gated.release(1)
        _wait_until(lambda: entry["text"] == "ab")
        assert entry["done"] is False

        gated.finish.set()
        _wait_until(lambda: entry["done"])
        assert entry == {
            "text": "ab",
            "done": True,
            "session": session,
            "error": False,
            "finalised": False,
        }

        # Finalisation is claimed once; the entry stays until the next start().
        assert streaming.claim_finalise(stream_id) is True
        assert entry["finalised"] is True
        assert streaming.claim_finalise(stream_id) is False
        assert streaming.claim_finalise("missing") is False
        assert set(streaming._STREAMS) == {stream_id}

        # The next start() evicts every done entry.
        second = streaming.start(iter(()), {})
        assert set(streaming._STREAMS) == {second}
        _wait_until(lambda: streaming._STREAMS[second]["done"])
        assert streaming._STREAMS[second]["text"] == ""

    def test_a_live_stream_is_not_evicted_by_a_new_start(self) -> None:
        gated = _Gated(["x"])
        first = streaming.start(gated.gen(), {})
        second = streaming.start(iter(()), {})
        assert set(streaming._STREAMS) == {first, second}
        gated.release(0)
        gated.finish.set()
        _wait_until(lambda: streaming._STREAMS[first]["done"])

    def test_pop_removes_and_returns_the_entry(self) -> None:
        stream_id = streaming.start(iter(()), {"k": 1})
        _wait_until(lambda: streaming._STREAMS[stream_id]["done"])
        entry = streaming.pop(stream_id)
        assert entry is not None
        assert entry["session"] == {"k": 1}
        assert streaming._STREAMS == {}
        assert streaming.pop(stream_id) is None
        assert streaming.get(stream_id) is None

    def test_a_json_bodied_exception_is_formatted_onto_the_text(self) -> None:
        body = json.dumps(
            {"error": {"message": "Rate limited", "code": 429, "status": "BUSY"}}
        )
        exc = RuntimeError(f"litellm.RateLimitError: Foo - b'{body}'")
        gated = _Gated(["partial"], raise_after=exc)
        stream_id = streaming.start(gated.gen(), {})
        entry = streaming._STREAMS[stream_id]
        gated.release(0)
        _wait_until(lambda: entry["text"] == "partial")
        assert entry["error"] is False
        gated.finish.set()
        _wait_until(lambda: entry["done"])
        assert entry["text"] == "partial" + _format_error(exc)
        assert entry["error"] is True
        assert (
            entry["text"]
            == "partial**Error: RuntimeError** (HTTP 429 · BUSY)\n\nRate limited"
            "\n\n- Source: Foo"
        )

    def test_a_plain_exception_is_formatted_onto_the_text(self) -> None:
        exc = RuntimeError("boom")
        gated = _Gated([], raise_after=exc)
        stream_id = streaming.start(gated.gen(), {})
        gated.finish.set()
        _wait_until(lambda: streaming._STREAMS[stream_id]["done"])
        entry = streaming._STREAMS[stream_id]
        assert entry["text"] == "**Error: RuntimeError**\n\nboom"
        assert entry["error"] is True

    def test_agent_mutations_reach_the_poll_through_the_shared_session(self) -> None:
        session: dict[str, Any] = {}

        def gen() -> Generator[str, None, None]:
            session["_stream_status"] = "Searching the web"
            session["_stream_received_chars"] = 12
            yield "t"

        stream_id = streaming.start(gen(), session)
        entry = streaming._STREAMS[stream_id]
        _wait_until(lambda: entry["done"])
        assert entry["session"]["_stream_status"] == "Searching the web"
        assert entry["session"]["_stream_received_chars"] == 12


# ---------------------------------------------------------------------------
# _USAGE_RECORDS, through the real poll done-branch
# ---------------------------------------------------------------------------


class TestUsageRecords:
    def _stream_session(self, tmp_path: pathlib.Path) -> dict[str, Any]:
        session = _default_session()
        session.update(
            {
                "working_dir": str(tmp_path),
                "active_agent": "brainstormer",
                "llm_config": _CFG,
                "messages": [
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": ""},
                ],
            }
        )
        return session

    def test_a_turn_records_once_and_the_poll_drains_once(
        self, tmp_path: pathlib.Path
    ) -> None:
        session = self._stream_session(tmp_path)
        chunks = [_delta("hel"), _delta("lo", "stop"), _usage_chunk()]

        def turn() -> Generator[str, None, None]:
            with patch("spec4.llm.litellm.completion", return_value=iter(chunks)):
                yield from llm.stream_turn(
                    "sys",
                    [{"role": "user", "content": "hi"}],
                    _CFG,
                    None,
                    agent_name="brainstormer",
                )

        stream_id = streaming.start(turn(), session)
        session["_stream_id"] = stream_id
        entry = streaming._STREAMS[stream_id]
        _wait_until(lambda: entry["done"])
        assert entry["text"] == "hello"

        # Recorded by the worker, not yet drained.
        records = list(llm._USAGE_RECORDS)
        assert len(records) == 1
        record = records[0]
        assert set(record) == _USAGE_RECORD_KEYS
        assert record["agent"] == "brainstormer"
        assert record["model"] == "gpt-4o-mini"
        assert record["provider"] == "openai"
        assert record["effort"] == "default"
        assert record["streamed"] is True
        assert record["prompt_tokens"] == 120
        assert record["completion_tokens"] == 30
        assert record["total_tokens"] == 150
        assert record["usage_missing"] is False
        assert record["error"] is None

        # First done-poll: claims finalisation, drains the sink, writes usage.json.
        store, interval = on_stream_poll(1, session)
        assert interval == 0
        assert llm._USAGE_RECORDS == []
        assert store["_stream_id"] is None
        assert store["_stream_error"] is None
        assert store["_initial_turn_done"] is True
        assert store["messages"][-1] == {"role": "assistant", "content": "hello"}
        assert store["_turn_usage"] == {
            "agent": "brainstormer",
            "input": 120,
            "output": 30,
            "calls": 1,
            "missing": 0,
        }
        # A greenfield project with no rounds on disk pins round 0 (v0 is the
        # "nothing existed before Spec4" round); brownfield would pin 1.
        assert store["phase_version"] == 0
        usage_path = project_manager.get_version_dir(tmp_path, 0) / "usage.json"
        assert usage_path.exists()
        first_bytes = usage_path.read_bytes()
        assert json.loads(first_bytes)["agents"]["brainstormer"]["calls"] == 1

        # The entry is read, not popped, and stays finalised.
        assert entry["finalised"] is True
        assert set(streaming._STREAMS) == {stream_id}

        # Second done-poll: same terminal store, nothing drained, nothing rewritten.
        again, interval2 = on_stream_poll(2, session)
        assert interval2 == 0
        assert again == store
        assert llm._USAGE_RECORDS == []
        assert usage_path.read_bytes() == first_bytes

    def test_drain_on_an_empty_sink_returns_an_empty_list(self) -> None:
        assert llm.drain_usage_records() == []
        assert llm._USAGE_RECORDS == []

    def test_a_call_with_no_usage_is_still_recorded(self) -> None:
        llm._record_usage(
            agent_name="phaser",
            kwargs={"model": "gpt-4o-mini"},
            response=None,
            usage=None,
            streamed=False,
            started_at="2026-09-08T00:00:00+00:00",
            start_mono=time.monotonic(),
            error="boom",
        )
        assert len(llm._USAGE_RECORDS) == 1
        record = llm._USAGE_RECORDS[0]
        assert record["usage_missing"] is True
        assert record["prompt_tokens"] is None
        assert record["computed_cost_usd"] is None
        assert record["error"] == "boom"
        assert record["streamed"] is False
        assert llm.drain_usage_records() == [record]
        assert llm._USAGE_RECORDS == []

    def test_an_error_stream_still_finalises_with_the_retry_flag(
        self, tmp_path: pathlib.Path
    ) -> None:
        session = self._stream_session(tmp_path)
        gated = _Gated(["half"], raise_after=RuntimeError("boom"))
        stream_id = streaming.start(gated.gen(), session)
        session["_stream_id"] = stream_id
        gated.release(0)
        gated.finish.set()
        _wait_until(lambda: streaming._STREAMS[stream_id]["done"])
        store, interval = on_stream_poll(1, session)
        assert interval == 0
        assert store["_stream_error"] is True
        assert store["messages"][-1]["content"].startswith(
            "half**Error: RuntimeError**"
        )
        assert store["_turn_usage"]["calls"] == 0
        assert llm._USAGE_RECORDS == []


# ---------------------------------------------------------------------------
# _MOCK_BUFFERS
# ---------------------------------------------------------------------------

_HTML = "<!DOCTYPE html><html><body>ok</body></html>"


class TestMockBuffers:
    def _start(
        self,
        monkeypatch: Any,
        tmp_path: pathlib.Path | None,
        gated: _Gated,
        store: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        monkeypatch.setattr(
            dmod, "generate_mock_streaming", lambda *a, **kw: gated.gen()
        )
        new_store, buffer, disabled = dmod._start_gen(
            store or {},
            str(tmp_path) if tmp_path else None,
            "m",
            "key",
            None,
            False,
            session={"phase_version": 1},
        )
        assert disabled is False
        assert buffer == {"tokens": 0, "progress": 0, "error": None}
        return new_store

    def test_a_generation_from_start_to_acknowledged_delivery(
        self, monkeypatch: Any, tmp_path: pathlib.Path
    ) -> None:
        project_manager.ensure_version_dir(tmp_path, 1)
        gated = _Gated(["<!DOCTYPE html>", "<html><body>ok</body></html>__DONE__"])
        store = self._start(monkeypatch, tmp_path, gated)
        gen_id = store["_gen_id"]

        assert set(dmod._MOCK_BUFFERS) == {gen_id}
        entry = dmod._MOCK_BUFFERS[gen_id]
        assert set(entry) == {"done", "stop", "text", "expected_chars"}
        assert entry["done"] is False
        assert isinstance(entry["stop"], threading.Event)
        assert not entry["stop"].is_set()
        assert entry["text"] == ""
        assert entry["expected_chars"] == dmod._DEFAULT_EXPECTED_CHARS
        assert store["step"] == 5
        assert store["mock_html"] == ""

        # Mid-stream: text accumulates, the poll reports progress and nothing else.
        gated.release(0)
        _wait_until(lambda: entry["text"] == "<!DOCTYPE html>")
        buf, new_store, disabled = dmod.on_mock_stream_poll(1, store)
        assert new_store is no_update
        assert disabled is no_update
        assert buf["tokens"] == len("<!DOCTYPE html>")
        # Integer percent of the expected size, so a short stream reads 0%.
        assert buf["progress"] == min(
            99, len("<!DOCTYPE html>") * 100 // dmod._DEFAULT_EXPECTED_CHARS
        )
        assert buf["progress"] == 0
        assert buf["error"] is None
        assert "final_html" not in entry

        # Completion: the worker extracts, saves, and sets final_html.
        gated.release(1)
        gated.finish.set()
        _wait_until(lambda: entry.get("done") is True)
        assert entry["final_html"] == _HTML
        assert "__DONE__" in entry["text"]
        saved = project_manager.get_version_dir(tmp_path, 1) / "design" / "mock.html"
        assert saved.read_text() == _HTML

        # First delivery tick at step 5: payload out, buffer kept, counter at 1.
        buf, new_store, disabled = dmod.on_mock_stream_poll(2, store)
        assert disabled is no_update
        assert entry["delivered"] == 1
        assert set(dmod._MOCK_BUFFERS) == {gen_id}
        assert new_store["step"] == 6
        assert new_store["mock_html"] == _HTML
        assert new_store["_gen_id"] == gen_id
        assert buf == {
            "tokens": len(_HTML),
            "progress": 100,
            "error": None,
            "complete": new_store,
        }

        # Second unacknowledged tick: identical payload, counter at 2.
        buf2, new_store2, _ = dmod.on_mock_stream_poll(3, store)
        assert new_store2 == new_store
        assert buf2 == buf
        assert entry["delivered"] == 2

        # Acknowledgement (store moved off step 5): buffer popped, interval off.
        buf3, new_store3, disabled3 = dmod.on_mock_stream_poll(4, new_store)
        assert new_store3 is no_update
        assert disabled3 is True
        assert buf3 == {"tokens": len(_HTML), "progress": 100, "error": None}
        assert dmod._MOCK_BUFFERS == {}

        # A poll for a gone buffer is a no-op that stops the interval.
        assert dmod.on_mock_stream_poll(5, new_store) == (no_update, no_update, True)

    def test_an_error_sentinel_pops_the_buffer(
        self, monkeypatch: Any, tmp_path: pathlib.Path
    ) -> None:
        gated = _Gated(["__GENERATION_ERROR__: bad"])
        store = self._start(monkeypatch, None, gated)
        gen_id = store["_gen_id"]
        gated.release(0)
        gated.finish.set()
        _wait_until(lambda: dmod._MOCK_BUFFERS[gen_id].get("done") is True)
        buf, new_store, disabled = dmod.on_mock_stream_poll(1, store)
        assert buf == {"error": "bad"}
        assert new_store is no_update
        assert disabled is True
        assert dmod._MOCK_BUFFERS == {}

    def test_no_html_document_becomes_an_error_sentinel(
        self, monkeypatch: Any, tmp_path: pathlib.Path
    ) -> None:
        gated = _Gated(["not html at all__DONE__"])
        store = self._start(monkeypatch, None, gated)
        gen_id = store["_gen_id"]
        gated.release(0)
        gated.finish.set()
        _wait_until(lambda: dmod._MOCK_BUFFERS[gen_id].get("done") is True)
        entry = dmod._MOCK_BUFFERS[gen_id]
        assert "final_html" not in entry
        assert "__GENERATION_ERROR__:" in entry["text"]
        buf, _, disabled = dmod.on_mock_stream_poll(1, store)
        assert buf["error"].startswith("The model did not return a valid HTML")
        assert disabled is True
        assert dmod._MOCK_BUFFERS == {}

    def test_a_stopped_stream_without_a_sentinel_is_dropped(
        self, monkeypatch: Any
    ) -> None:
        gated = _Gated(["<html>"])
        store = self._start(monkeypatch, None, gated)
        gen_id = store["_gen_id"]
        gated.release(0)
        gated.finish.set()
        _wait_until(lambda: dmod._MOCK_BUFFERS[gen_id].get("done") is True)
        entry = dmod._MOCK_BUFFERS[gen_id]
        assert "final_html" not in entry
        assert dmod.on_mock_stream_poll(1, store) == (no_update, no_update, True)
        assert dmod._MOCK_BUFFERS == {}

    def test_a_new_generation_stops_and_drops_the_previous_one(
        self, monkeypatch: Any
    ) -> None:
        first = _Gated(["<html>"])
        store = self._start(monkeypatch, None, first)
        old_id = store["_gen_id"]
        old_entry = dmod._MOCK_BUFFERS[old_id]

        second = _Gated([])
        store2 = self._start(monkeypatch, None, second, store=store)
        new_id = store2["_gen_id"]
        assert new_id != old_id
        assert set(dmod._MOCK_BUFFERS) == {new_id}
        assert old_entry["stop"].is_set()

        # The orphaned worker still finishes but writes nothing back.
        first.release(0)
        first.finish.set()
        _wait_until(lambda: first.yielded == 1)
        second.finish.set()
        _wait_until(lambda: dmod._MOCK_BUFFERS[new_id].get("done") is True)
        assert old_id not in dmod._MOCK_BUFFERS
        assert store2["step"] == 5

    def test_the_runaway_valve_reports_the_saved_mock(self, monkeypatch: Any) -> None:
        gated = _Gated([_HTML + "__DONE__"])
        store = self._start(monkeypatch, None, gated)
        gen_id = store["_gen_id"]
        gated.release(0)
        gated.finish.set()
        _wait_until(lambda: dmod._MOCK_BUFFERS[gen_id].get("done") is True)
        dmod._MOCK_BUFFERS[gen_id]["delivered"] = dmod._MAX_DELIVERY_TICKS
        buf, new_store, disabled = dmod.on_mock_stream_poll(1, store)
        assert "Refresh the page" in buf["error"]
        assert new_store is no_update
        assert disabled is True
        assert dmod._MOCK_BUFFERS == {}
