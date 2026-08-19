"""Tests for _drain_stream — the silent drain with D-PH9 receipt publishing.

The helper accumulates internally-consumed stream deltas into a string while
publishing a cumulative character total to session["_stream_received_chars"]
(the key the chat poll reads). Covers accumulation, eager seeding (stale
overwrite), monotonic publishes, the session=None no-op, the returned
(text, total) pair, and the optional TTFT log line.
"""

from __future__ import annotations

from typing import Any

import pytest

from spec4.agents._utils import _drain_stream


def test_accumulates_and_returns_total() -> None:
    session: dict[str, Any] = {}
    text, total = _drain_stream(iter(["ab", "cd", "e"]), session=session)
    assert text == "abcde"
    assert total == 5
    assert session["_stream_received_chars"] == 5


def test_seed_offsets_total() -> None:
    session: dict[str, Any] = {}
    text, total = _drain_stream(iter(["abc"]), session=session, seed=100)
    assert text == "abc"
    assert total == 103
    assert session["_stream_received_chars"] == 103


def test_seed_published_eagerly_overwriting_stale_value() -> None:
    """The seed lands before the first chunk so a stale prior-turn total is
    overwritten the moment the drain opens — even for an empty stream."""
    session: dict[str, Any] = {"_stream_received_chars": 99999}
    _drain_stream(iter([]), session=session, seed=7)
    assert session["_stream_received_chars"] == 7


def test_publishes_monotonically_per_chunk() -> None:
    published: list[int] = []

    class _Spy(dict):
        def __setitem__(self, key: str, value: int) -> None:
            if key == "_stream_received_chars":
                published.append(value)
            super().__setitem__(key, value)

    _drain_stream(iter(["aa", "bbb"]), session=_Spy(), seed=10)
    assert published == [10, 12, 15]
    assert published == sorted(published)


def test_session_none_is_a_no_op_drain() -> None:
    text, total = _drain_stream(iter(["x", "yz"]))
    assert (text, total) == ("xyz", 3)


def test_empty_chunks_skipped() -> None:
    session: dict[str, Any] = {}
    text, total = _drain_stream(iter(["", "a", ""]), session=session)
    assert text == "a"
    assert total == 1


def test_ttft_label_logs_once(capsys: pytest.CaptureFixture[str]) -> None:
    _drain_stream(iter(["a", "b", "c"]), ttft_label="spec_drafter")
    out = capsys.readouterr().out
    assert out.count("[llm-ttft] spec_drafter:") == 1


def test_no_ttft_log_without_label(capsys: pytest.CaptureFixture[str]) -> None:
    _drain_stream(iter(["a"]))
    assert "[llm-ttft]" not in capsys.readouterr().out
