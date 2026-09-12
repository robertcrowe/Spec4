"""Helpers shared by the per-agent test files.

Moved unchanged from ``tests/test_agents.py`` by Phase 8's D9 split
(``PHASE8_RECORD.md`` §25).
"""

from collections.abc import Iterable
from typing import Any
from unittest.mock import patch
from spec4.app_constants import STATE_IN_PROGRESS
from tests._chunks import make_stream_chunk


def make_session(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "phase": "chat",
        "active_agent": "brainstormer",
        "working_dir": None,
        "code_review": None,
        "brainstormer_state": STATE_IN_PROGRESS,
        "brainstormer_messages": [],
        "vision_statement": None,
        "stack_advisor_messages": [],
        "stack_advisor_state": STATE_IN_PROGRESS,
        "stack_statement": None,
        "phaser_messages": [],
        "phaser_state": None,
        "phases": [],
        "code_scanner_messages": [],
        "code_scanner_state": STATE_IN_PROGRESS,
        "llm_config": {"model": "gpt-4o-mini", "api_key": "sk-test"},
        "tavily_api_key": None,
        "project_mode": None,
    }
    defaults.update(overrides)
    return dict(defaults)


def collect(gen: Iterable[str]) -> str:
    return "".join(gen)


def mock_litellm_stream(text: str) -> Any:
    """Return a context that mocks litellm.completion to stream the given text."""
    chunks = [make_stream_chunk(c) for c in text]
    chunks.append(make_stream_chunk("", finish_reason="stop"))
    mock_response = iter(chunks)
    return patch("spec4.llm.litellm.completion", return_value=mock_response)


def _reply_sequence(*replies: str) -> tuple[Any, list[dict[str, Any]]]:
    """A litellm.completion stand-in that serves one reply per call.

    The last reply repeats for any further calls, so a downstream helper making
    its own completion calls (feature_speccer, tool loops) cannot exhaust it and
    turn a behavioural assertion into an IndexError.
    """
    seqs = [list(_chunkify_stream(r)) for r in replies]
    calls: list[dict[str, Any]] = []

    def fake_completion(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return iter(seqs.pop(0) if len(seqs) > 1 else seqs[0])

    return fake_completion, calls


def _chunkify_stream(text: str) -> Iterable[Any]:
    """Helper: turn text into per-character mock chunks plus a stop sentinel."""
    chunks = [make_stream_chunk(c) for c in text]
    chunks.append(make_stream_chunk("", finish_reason="stop"))
    return chunks


def _phaser_revision_vision(
    added: list[str] | None = None,
    modified: list[str] | None = None,
    removed: list[str] | None = None,
    goal: str = "",
) -> dict[str, Any]:
    """Session-form vision envelope carrying a single revision_history entry."""
    entry = {
        "version": 1,
        "based_on_version": 0,
        "goal": goal,
        "changes": {
            "added": added or [],
            "modified": modified or [],
            "removed": removed or [],
        },
        "rationale": "",
    }
    return {"vision_statement": {"name": "App", "revision_history": [entry]}}
