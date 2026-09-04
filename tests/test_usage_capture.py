"""Per-call LLM usage capture, the round's usage.json, and the usage report.

Covers:
- llm: every streamed call asks for the usage chunk, consumes it (even when it
  arrives with empty choices), and records agent/model/provider/tokens/cost.
- llm: missing usage is recorded (nulls + usage_missing) and warned about,
  never dropped; a mid-stream failure is recorded too; capture never raises.
- llm: non-streaming and async paths record the same shape.
- designer: the mock draw is captured under agent "designer".
- project_manager.save_usage: schema, read-modify-write append, rollups and
  totals derived from history, atomic write, fast-forward note.
- staleness: usage.json is declared a non-artifact and moves no agent state.
- session._persist_artifacts: flushes the sink under the pinned version.
- usage_report: the per-agent table.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from spec4 import llm, project_manager, usage_report
from spec4.agents.designer import generate_mock_streaming
from spec4.app_constants import FF_PROMPT, STATE_VISION_COMPLETE
from spec4.layouts._chat import _turn_token_text
from spec4.session import _default_session, _persist_artifacts

_CFG = {"model": "gpt-4o-mini", "api_key": "sk-test"}


@pytest.fixture(autouse=True)
def _clean_sink() -> Any:
    llm.drain_usage_records()
    yield
    llm.drain_usage_records()


def _delta(text: str | None, finish: str | None = None) -> SimpleNamespace:
    choice = SimpleNamespace(
        delta=SimpleNamespace(content=text, tool_calls=None), finish_reason=finish
    )
    return SimpleNamespace(choices=[choice], usage=None, _hidden_params={})


def _usage(
    prompt: int = 120,
    completion: int = 30,
    *,
    cached: int | None = None,
    creation: int | None = None,
    read: int | None = None,
) -> SimpleNamespace:
    details = (
        SimpleNamespace(cached_tokens=cached, cache_creation_tokens=None)
        if cached is not None
        else None
    )
    usage = SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        prompt_tokens_details=details,
    )
    if creation is not None:
        usage.cache_creation_input_tokens = creation
    if read is not None:
        usage.cache_read_input_tokens = read
    return usage


def _usage_chunk(usage: Any, with_choice: bool = False) -> SimpleNamespace:
    """LiteLLM's include_usage chunk: usually choiceless, sometimes an empty delta."""
    choices = [_delta(None).choices[0]] if with_choice else []
    return SimpleNamespace(choices=choices, usage=usage, _hidden_params={})


def _only_record() -> dict[str, Any]:
    records = llm.drain_usage_records()
    assert len(records) == 1, records
    return records[0]


# ---------------------------------------------------------------------------
# Streaming capture
# ---------------------------------------------------------------------------


class TestStreamCapture:
    def test_requests_usage_chunk_and_records_it(self) -> None:
        chunks = [_delta("a"), _delta("b", "stop"), _usage_chunk(_usage())]
        with patch(
            "spec4.llm.litellm.completion", return_value=iter(chunks)
        ) as mock_llm:
            out = list(
                llm.complete_stream(llm_config=_CFG, messages=[], agent_name="scout")
            )
        assert out == ["a", "b"]
        assert mock_llm.call_args[1]["stream_options"] == {"include_usage": True}
        rec = _only_record()
        assert rec["agent"] == "scout"
        assert rec["model"] == "gpt-4o-mini"
        assert rec["provider"] == "openai"
        assert rec["streamed"] is True
        counts = (rec["prompt_tokens"], rec["completion_tokens"], rec["total_tokens"])
        assert counts == (120, 30, 150)
        assert rec["usage_missing"] is False
        assert rec["error"] is None
        assert rec["timestamp"].endswith("+00:00")
        assert isinstance(rec["duration_s"], float)
        assert isinstance(rec["computed_cost_usd"], float)
        assert rec["computed_cost_usd"] > 0

    def test_choiceless_usage_chunk_is_not_yielded_to_consumers(self) -> None:
        chunks = [_delta("x", "stop"), _usage_chunk(_usage())]
        with patch("spec4.llm.litellm.completion", return_value=iter(chunks)):
            raw = list(
                llm.stream_completion(
                    agent_name="designer", model="gpt-4o-mini", messages=[]
                )
            )
        assert len(raw) == 1
        assert raw[0].choices[0].delta.content == "x"
        assert _only_record()["prompt_tokens"] == 120

    def test_usage_chunk_with_empty_choice_is_still_captured(self) -> None:
        chunks = [_delta("x", "stop"), _usage_chunk(_usage(), with_choice=True)]
        with patch("spec4.llm.litellm.completion", return_value=iter(chunks)):
            out = list(llm.complete_stream(llm_config=_CFG, messages=[]))
        assert out == ["x"]
        assert _only_record()["completion_tokens"] == 30

    def test_cache_fields_recorded_when_present(self) -> None:
        usage = _usage(cached=100, creation=40, read=100)
        chunks = [_delta("x", "stop"), _usage_chunk(usage)]
        with patch("spec4.llm.litellm.completion", return_value=iter(chunks)):
            list(llm.complete_stream(llm_config=_CFG, messages=[]))
        rec = _only_record()
        assert rec["cached_tokens"] == 100
        assert rec["cache_creation_input_tokens"] == 40
        assert rec["cache_read_input_tokens"] == 100

    def test_cache_fields_null_when_absent(self) -> None:
        chunks = [_delta("x", "stop"), _usage_chunk(_usage())]
        with patch("spec4.llm.litellm.completion", return_value=iter(chunks)):
            list(llm.complete_stream(llm_config=_CFG, messages=[]))
        rec = _only_record()
        assert rec["cached_tokens"] is None
        assert rec["cache_creation_input_tokens"] is None
        assert rec["cache_read_input_tokens"] is None

    def test_missing_usage_is_recorded_and_warned(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        chunks = [_delta("x", "stop")]
        with caplog.at_level(logging.WARNING, logger="spec4.llm"):
            with patch("spec4.llm.litellm.completion", return_value=iter(chunks)):
                out = list(
                    llm.complete_stream(
                        llm_config=_CFG, messages=[], agent_name="linker"
                    )
                )
        assert out == ["x"]
        rec = _only_record()
        assert rec["usage_missing"] is True
        assert rec["prompt_tokens"] is None
        assert rec["completion_tokens"] is None
        assert rec["total_tokens"] is None
        assert rec["computed_cost_usd"] is None
        assert rec["agent"] == "linker"
        assert "provider=openai" in caplog.text
        assert "model=gpt-4o-mini" in caplog.text

    def test_zero_zero_usage_counts_as_missing(self) -> None:
        chunks = [_delta("x", "stop"), _usage_chunk(_usage(0, 0))]
        with patch("spec4.llm.litellm.completion", return_value=iter(chunks)):
            list(llm.complete_stream(llm_config=_CFG, messages=[]))
        rec = _only_record()
        assert rec["usage_missing"] is True
        assert rec["prompt_tokens"] is None

    def test_hidden_params_usage_is_the_fallback(self) -> None:
        last = _delta("x", "stop")
        last._hidden_params = {"usage": _usage(7, 3)}
        with patch("spec4.llm.litellm.completion", return_value=iter([last])):
            list(llm.complete_stream(llm_config=_CFG, messages=[]))
        rec = _only_record()
        assert (rec["prompt_tokens"], rec["completion_tokens"]) == (7, 3)

    def test_mid_stream_error_is_recorded_and_propagates(self) -> None:
        def _chunks() -> Any:
            yield _delta("partial")
            raise TimeoutError("stall")

        with patch("spec4.llm.litellm.completion", return_value=_chunks()):
            with pytest.raises(TimeoutError):
                list(llm.complete_stream(llm_config=_CFG, messages=[]))
        rec = _only_record()
        assert rec["usage_missing"] is True
        assert rec["error"] == "TimeoutError"

    def test_abandoned_stream_is_recorded(self) -> None:
        chunks = [_delta("a"), _delta("b"), _delta("c", "stop"), _usage_chunk(_usage())]
        with patch("spec4.llm.litellm.completion", return_value=iter(chunks)):
            gen = llm.complete_stream(llm_config=_CFG, messages=[])
            assert next(gen) == "a"
            gen.close()
        rec = _only_record()
        assert rec["usage_missing"] is True
        assert rec["error"] == "abandoned"

    def test_request_time_failure_leaves_no_record(self) -> None:
        with patch("spec4.llm.litellm.completion", side_effect=RuntimeError("401")):
            with pytest.raises(RuntimeError):
                list(llm.complete_stream(llm_config=_CFG, messages=[]))
        assert llm.drain_usage_records() == []

    def test_magicmock_chunks_never_look_like_usage(self) -> None:
        chunk = MagicMock()
        chunk.choices[0].delta.content = "hi"
        with patch("spec4.llm.litellm.completion", return_value=iter([chunk])):
            out = list(llm.complete_stream(llm_config=_CFG, messages=[]))
        assert out == ["hi"]
        assert _only_record()["usage_missing"] is True

    def test_capture_failure_never_breaks_the_stream(self) -> None:
        chunks = [_delta("x", "stop"), _usage_chunk(_usage())]
        with (
            patch("spec4.llm.litellm.completion", return_value=iter(chunks)),
            patch("spec4.llm._usage_fields", side_effect=RuntimeError("boom")),
        ):
            out = list(llm.complete_stream(llm_config=_CFG, messages=[]))
        assert out == ["x"]
        assert llm.drain_usage_records() == []

    def test_unmapped_model_records_tokens_with_null_cost(self) -> None:
        cfg = {
            "model": "openai/Qwen/Qwen3-235B-A22B-Instruct-2507",
            "api_key": "k",
            "api_base": "https://api.tokenfactory.nebius.com/v1/",
        }
        chunks = [_delta("x", "stop"), _usage_chunk(_usage())]
        with patch("spec4.llm.litellm.completion", return_value=iter(chunks)):
            list(llm.complete_stream(llm_config=cfg, messages=[]))
        rec = _only_record()
        assert rec["provider"] == "openai"
        assert rec["prompt_tokens"] == 120
        assert rec["computed_cost_usd"] is None
        assert rec["usage_missing"] is False


class TestStreamTurnCapture:
    def test_survives_choiceless_usage_chunk_and_records_each_round(self) -> None:
        chunks = [_delta("hello", "stop"), _usage_chunk(_usage())]
        with patch(
            "spec4.llm.litellm.completion", return_value=iter(chunks)
        ) as mock_llm:
            msgs: list[dict[str, Any]] = [{"role": "user", "content": "hi"}]
            out = list(llm.stream_turn("sys", msgs, _CFG, None, agent_name="phaser"))
        assert out == ["hello"]
        assert msgs[-1] == {"role": "assistant", "content": "hello"}
        assert mock_llm.call_args[1]["stream_options"] == {"include_usage": True}
        rec = _only_record()
        assert rec["agent"] == "phaser"
        assert rec["prompt_tokens"] == 120


# ---------------------------------------------------------------------------
# Non-streaming and async
# ---------------------------------------------------------------------------


class TestNonStreamCapture:
    def test_reads_response_usage_and_hidden_cost(self) -> None:
        resp = SimpleNamespace(
            usage=_usage(50, 10), _hidden_params={"response_cost": 0.00123}
        )
        with patch("spec4.llm.litellm.completion", return_value=resp):
            llm.complete(llm_config=_CFG, messages=[], agent_name="tier_analyst")
        rec = _only_record()
        assert rec["streamed"] is False
        assert rec["agent"] == "tier_analyst"
        assert (rec["prompt_tokens"], rec["completion_tokens"]) == (50, 10)
        assert rec["computed_cost_usd"] == 0.00123

    def test_hidden_cost_absent_and_unmapped_model_gives_null(self) -> None:
        resp = SimpleNamespace(usage=_usage(50, 10), _hidden_params={})
        cfg = {"model": "openai/not-a-real-model", "api_key": "k"}
        with patch("spec4.llm.litellm.completion", return_value=resp):
            llm.complete(llm_config=cfg, messages=[])
        rec = _only_record()
        assert rec["prompt_tokens"] == 50
        assert rec["computed_cost_usd"] is None

    def test_cost_calculator_exception_gives_null_not_error(self) -> None:
        resp = SimpleNamespace(usage=_usage(50, 10), _hidden_params={})
        with (
            patch("spec4.llm.litellm.completion", return_value=resp),
            patch(
                "spec4.llm.litellm.completion_cost",
                side_effect=RuntimeError("cost map unavailable"),
            ),
        ):
            llm.complete(llm_config=_CFG, messages=[], agent_name="tier_analyst")
        rec = _only_record()
        assert rec["usage_missing"] is False
        assert rec["prompt_tokens"] == 50
        assert rec["computed_cost_usd"] is None

    def test_no_stream_options_on_non_streaming_call(self) -> None:
        resp = SimpleNamespace(usage=_usage(), _hidden_params={})
        with patch("spec4.llm.litellm.completion", return_value=resp) as mock_llm:
            llm.complete(llm_config=_CFG, messages=[])
        assert "stream_options" not in mock_llm.call_args[1]

    def test_async_stream_is_wrapped_and_recorded(self) -> None:
        async def _chunks() -> Any:
            yield _delta("a")
            yield _delta("b", "stop")
            yield _usage_chunk(_usage(9, 4))

        async def _run() -> list[str]:
            async def fake(**kwargs: Any) -> Any:
                assert kwargs["stream_options"] == {"include_usage": True}
                return _chunks()

            with patch("spec4.llm.litellm.acompletion", side_effect=fake):
                response = await llm.acomplete(
                    llm_config=_CFG, messages=[], agent_name="spec_drafter", stream=True
                )
                got: list[str] = []
                async for chunk in response:
                    got.append(chunk.choices[0].delta.content)
                return got

        assert asyncio.run(_run()) == ["a", "b"]
        rec = _only_record()
        assert rec["agent"] == "spec_drafter"
        assert (rec["prompt_tokens"], rec["completion_tokens"]) == (9, 4)


# ---------------------------------------------------------------------------
# Designer
# ---------------------------------------------------------------------------


class TestDesignerCapture:
    def test_mock_draw_is_recorded_as_designer(self) -> None:
        chunks = [_delta("<html></html>", "stop"), _usage_chunk(_usage(300, 900))]
        session: Any = {
            "step": 5,
            "preference_text": "",
            "screenshots": [],
            "mock_html": "",
            "finalized": False,
        }
        with patch(
            "spec4.llm.litellm.completion", return_value=iter(chunks)
        ) as mock_llm:
            out = list(generate_mock_streaming(session, "gpt-4o-mini", "k", [], True))
        assert out[-1] == "__DONE__"
        assert mock_llm.call_args[1]["stream_options"] == {"include_usage": True}
        rec = _only_record()
        assert rec["agent"] == "designer"
        assert rec["completion_tokens"] == 900


# ---------------------------------------------------------------------------
# usage.json writer: schema, append, rollups, atomicity
# ---------------------------------------------------------------------------


def _call(
    agent: str,
    model: str = "gpt-4o-mini",
    provider: str | None = "openai",
    prompt: int | None = 100,
    completion: int | None = 20,
    cost: float | None = 0.001,
    cached: int | None = None,
    read: int | None = None,
    missing: bool = False,
) -> dict[str, Any]:
    return {
        "timestamp": "2026-09-02T00:00:00+00:00",
        "agent": agent,
        "model": model,
        "provider": provider,
        "streamed": True,
        "duration_s": 1.0,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": None if prompt is None else prompt + (completion or 0),
        "cached_tokens": cached,
        "cache_creation_input_tokens": None,
        "cache_read_input_tokens": read,
        "computed_cost_usd": cost,
        "usage_missing": missing,
        "error": None,
    }


def _usage_path(root: Path, version: int = 0) -> Path:
    return root / ".spec4" / f"v{version}" / "usage.json"


class TestSaveUsageSchema:
    def test_top_level_shape(self, tmp_path: Path) -> None:
        project_manager.save_usage(tmp_path, [_call("brainstormer")], 2)
        data = json.loads(_usage_path(tmp_path, 2).read_text())
        assert list(data) == [
            "schema_version",
            "spec4_version",
            "litellm_version",
            "round",
            "created_at",
            "updated_at",
            "notes",
            "agents",
            "totals",
        ]
        assert data["schema_version"] == "1"
        assert data["round"] == "v2"
        assert data["litellm_version"] == "1.82.0"
        assert data["spec4_version"]
        assert data["created_at"].endswith("+00:00")
        assert data["updated_at"].endswith("+00:00")
        assert data["notes"] == {
            "tokens_are_ground_truth": True,
            "computed_cost_source": (
                "litellm response_cost (community cost map; may lag provider "
                "price sheets)"
            ),
            "fast_forward": None,
        }

    def test_agent_block_and_totals(self, tmp_path: Path) -> None:
        project_manager.save_usage(tmp_path, [_call("brainstormer")], 0)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        agent = data["agents"]["brainstormer"]
        assert agent["calls"] == 1
        assert (agent["input_tokens"], agent["output_tokens"]) == (100, 20)
        assert agent["total_tokens"] == 120
        assert agent["cached_input_tokens"] is None
        assert agent["computed_cost_usd"] == 0.001
        assert agent["models"] == [{"model": "gpt-4o-mini", "provider": "openai"}]
        assert agent["history"][0]["agent"] == "brainstormer"
        assert data["totals"] == {
            "calls": 1,
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "cached_input_tokens": None,
            "computed_cost_usd": 0.001,
        }

    def test_empty_records_write_nothing(self, tmp_path: Path) -> None:
        project_manager.save_usage(tmp_path, [], 0)
        assert not (tmp_path / ".spec4").exists()

    def test_sub_agents_roll_into_their_planning_agent(self, tmp_path: Path) -> None:
        records = [
            _call("agentifier"),
            _call("scout"),
            _call("spec_drafter"),
            _call("feature_speccer"),
            _call("phaser_seam"),
        ]
        project_manager.save_usage(tmp_path, records, 0)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        assert set(data["agents"]) == {"agentifier", "brainstormer", "phaser"}
        assert data["agents"]["agentifier"]["calls"] == 3
        assert [h["agent"] for h in data["agents"]["agentifier"]["history"]] == [
            "agentifier",
            "scout",
            "spec_drafter",
        ]
        assert data["totals"]["calls"] == 5


class TestSaveUsageReadModifyWrite:
    def test_second_run_on_another_model_appends_history(
        self, tmp_path: Path
    ) -> None:
        project_manager.save_usage(
            tmp_path, [_call("phaser", "gpt-4o-mini", "openai", 100, 20, 0.001)], 0
        )
        first = project_manager.load_usage(tmp_path, 0)
        assert first is not None
        project_manager.save_usage(
            tmp_path,
            [_call("phaser", "claude-sonnet-4-5-20250929", "anthropic", 300, 50, 0.01)],
            0,
        )
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        agent = data["agents"]["phaser"]
        assert [h["model"] for h in agent["history"]] == [
            "gpt-4o-mini",
            "claude-sonnet-4-5-20250929",
        ]
        assert agent["models"] == [
            {"model": "gpt-4o-mini", "provider": "openai"},
            {"model": "claude-sonnet-4-5-20250929", "provider": "anthropic"},
        ]
        assert agent["calls"] == 2
        assert (agent["input_tokens"], agent["output_tokens"]) == (400, 70)
        assert agent["computed_cost_usd"] == 0.011
        assert data["totals"]["input_tokens"] == 400
        assert data["created_at"] == first["created_at"]
        assert data["updated_at"] >= first["updated_at"]

    def test_prior_session_file_is_extended_by_a_real_turn_on_another_model(
        self, tmp_path: Path
    ) -> None:
        # A usage.json exactly as an earlier session (different provider)
        # would have left it: one phaser call on an OpenAI model.
        path = _usage_path(tmp_path)
        path.parent.mkdir(parents=True)
        prior_call = _call("phaser", "gpt-4o-mini", "openai", 100, 20, 0.001)
        prior = {
            "schema_version": "1",
            "spec4_version": "0.9.0",
            "litellm_version": "1.80.0",
            "round": "v0",
            "created_at": "2026-08-30T10:00:00+00:00",
            "updated_at": "2026-08-30T10:05:00+00:00",
            "notes": {
                "tokens_are_ground_truth": True,
                "computed_cost_source": "x",
                "fast_forward": False,
            },
            "agents": {"phaser": {**project_manager.summarize_usage([prior_call]),
                                  "history": [prior_call]}},
            "totals": project_manager.usage_totals(
                {"phaser": project_manager.summarize_usage([prior_call])}
            ),
        }
        path.write_text(json.dumps(prior, indent=2))

        # This session: the same agent re-run on Anthropic, through the real
        # capture -> sink -> persist funnel path.
        session = {**_default_session(), "working_dir": str(tmp_path)}
        anthropic_cfg = {"model": "claude-sonnet-4-5-20250929", "api_key": "k"}
        _stream_one("phaser", 300, 50, cfg=anthropic_cfg)
        _persist_artifacts(session)

        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        agent = data["agents"]["phaser"]
        assert [h["model"] for h in agent["history"]] == [
            "gpt-4o-mini",
            "claude-sonnet-4-5-20250929",
        ]
        assert agent["history"][0] == prior_call
        assert agent["models"] == [
            {"model": "gpt-4o-mini", "provider": "openai"},
            {"model": "claude-sonnet-4-5-20250929", "provider": "anthropic"},
        ]
        assert agent["calls"] == 2
        assert (agent["input_tokens"], agent["output_tokens"]) == (400, 70)
        assert data["totals"]["total_tokens"] == 470
        assert data["created_at"] == "2026-08-30T10:00:00+00:00"
        assert data["updated_at"] > "2026-08-30T10:05:00+00:00"
        assert data["litellm_version"] == "1.82.0"

    def test_rollups_are_recomputed_from_history_not_trusted(
        self, tmp_path: Path
    ) -> None:
        project_manager.save_usage(tmp_path, [_call("deployer")], 0)
        path = _usage_path(tmp_path)
        data = json.loads(path.read_text())
        data["agents"]["deployer"]["input_tokens"] = 999_999  # hand-edited drift
        data["totals"]["calls"] = 42
        path.write_text(json.dumps(data))
        project_manager.save_usage(tmp_path, [_call("deployer")], 0)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        assert data["agents"]["deployer"]["input_tokens"] == 200
        assert data["totals"]["calls"] == 2

    def test_missing_usage_counted_not_summed(self, tmp_path: Path) -> None:
        records = [
            _call("deployer"),
            _call("deployer", prompt=None, completion=None, cost=None, missing=True),
        ]
        project_manager.save_usage(tmp_path, records, 0)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        agent = data["agents"]["deployer"]
        assert agent["calls"] == 2
        assert agent["calls_missing_usage"] == 1
        assert agent["input_tokens"] == 100
        assert agent["computed_cost_usd"] == 0.001

    def test_cached_and_cost_stay_null_when_never_reported(
        self, tmp_path: Path
    ) -> None:
        project_manager.save_usage(tmp_path, [_call("deployer", cost=None)], 0)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        assert data["agents"]["deployer"]["cached_input_tokens"] is None
        assert data["agents"]["deployer"]["computed_cost_usd"] is None
        assert data["totals"]["cached_input_tokens"] is None
        assert data["totals"]["computed_cost_usd"] is None

    def test_cached_sums_openai_and_anthropic_shapes(self, tmp_path: Path) -> None:
        records = [_call("phaser", cached=50), _call("phaser", read=25)]
        project_manager.save_usage(tmp_path, records, 0)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        assert data["agents"]["phaser"]["cached_input_tokens"] == 75
        assert data["totals"]["cached_input_tokens"] == 75

    def test_unreadable_existing_file_starts_fresh_without_raising(
        self, tmp_path: Path
    ) -> None:
        path = _usage_path(tmp_path)
        path.parent.mkdir(parents=True)
        path.write_text("{not json")
        project_manager.save_usage(tmp_path, [_call("phaser")], 0)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        assert data["totals"]["calls"] == 1


class TestSaveUsageFastForwardNote:
    def test_true_is_sticky(self, tmp_path: Path) -> None:
        project_manager.save_usage(tmp_path, [_call("phaser")], 0, fast_forward=True)
        project_manager.save_usage(tmp_path, [_call("phaser")], 0, fast_forward=False)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        assert data["notes"]["fast_forward"] is True

    def test_false_only_fills_unknown(self, tmp_path: Path) -> None:
        project_manager.save_usage(tmp_path, [_call("phaser")], 0, fast_forward=False)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        assert data["notes"]["fast_forward"] is False
        project_manager.save_usage(tmp_path, [_call("phaser")], 0, fast_forward=True)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        assert data["notes"]["fast_forward"] is True

    def test_none_leaves_note_alone(self, tmp_path: Path) -> None:
        project_manager.save_usage(tmp_path, [_call("designer")], 0)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        assert data["notes"]["fast_forward"] is None
        project_manager.save_usage(tmp_path, [_call("phaser")], 0, fast_forward=True)
        project_manager.save_usage(tmp_path, [_call("designer")], 0)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        assert data["notes"]["fast_forward"] is True


class TestSaveUsageAtomicity:
    def test_failed_write_leaves_original_intact_and_no_temp_file(
        self, tmp_path: Path
    ) -> None:
        project_manager.save_usage(tmp_path, [_call("phaser")], 0)
        path = _usage_path(tmp_path)
        before = path.read_text()
        with patch("spec4.project_manager.os.replace", side_effect=OSError("boom")):
            with pytest.raises(OSError):
                project_manager.save_usage(tmp_path, [_call("phaser")], 0)
        assert path.read_text() == before
        assert [p.name for p in path.parent.iterdir()] == ["usage.json"]

    def test_partial_content_write_never_reaches_the_file(
        self, tmp_path: Path
    ) -> None:
        project_manager.save_usage(tmp_path, [_call("phaser")], 0)
        path = _usage_path(tmp_path)
        before = path.read_text()
        real_fdopen = os.fdopen

        def _broken_fdopen(fd: int, *args: Any, **kwargs: Any) -> Any:
            fh = real_fdopen(fd, *args, **kwargs)
            original_write = fh.write

            def _write(text: str) -> int:
                original_write(text[: len(text) // 2])
                raise OSError("disk full")

            fh.write = _write  # type: ignore[method-assign]
            return fh

        with patch("spec4.project_manager.os.fdopen", side_effect=_broken_fdopen):
            with pytest.raises(OSError):
                project_manager.save_usage(tmp_path, [_call("phaser")], 0)
        assert path.read_text() == before
        assert json.loads(path.read_text())["totals"]["calls"] == 1
        assert [p.name for p in path.parent.iterdir()] == ["usage.json"]


# ---------------------------------------------------------------------------
# Staleness isolation
# ---------------------------------------------------------------------------


_AGENTS = (
    "brainstormer",
    "agentifier",
    "designer",
    "stack_advisor",
    "phaser",
    "deployer",
    "code_scanner",
)


class TestUsageIsNotAnArtifact:
    def test_declared_exclusion_is_honoured_by_the_graph(self) -> None:
        assert "usage.json" in project_manager._NON_ARTIFACT_FILES
        for output_rel, inputs in project_manager._STALE_DEPENDENCIES.values():
            assert output_rel not in project_manager._NON_ARTIFACT_FILES
            for _, rel in inputs:
                assert rel not in project_manager._NON_ARTIFACT_FILES
        for rel in project_manager._PIPELINE_ARTIFACT_ORDER:
            assert rel not in project_manager._NON_ARTIFACT_FILES
        for rels in project_manager._REQUIRED_INPUTS.values():
            for rel in rels:
                assert rel not in project_manager._NON_ARTIFACT_FILES

    def test_writing_usage_moves_no_agent_state(self, tmp_path: Path) -> None:
        project_manager.save_vision(tmp_path, {"app_name": "x"}, 0)
        project_manager.save_stack(tmp_path, {"stack": []}, 0)
        session = {**_default_session(), "working_dir": str(tmp_path)}
        before_btn = {
            a: project_manager.agent_button_state(tmp_path, a, session) for a in _AGENTS
        }
        before_stale = {
            a: project_manager.detect_stale_inputs(tmp_path, a) for a in _AGENTS
        }
        project_manager.save_usage(tmp_path, [_call("stack_advisor")], 0)
        # Modify it again later (a newer mtime than every artifact).
        os.utime(_usage_path(tmp_path), None)
        project_manager.save_usage(tmp_path, [_call("phaser")], 0)
        after_btn = {
            a: project_manager.agent_button_state(tmp_path, a, session) for a in _AGENTS
        }
        after_stale = {
            a: project_manager.detect_stale_inputs(tmp_path, a) for a in _AGENTS
        }
        assert after_btn == before_btn
        assert after_stale == before_stale
        assert all(v == {} for v in after_stale.values())


# ---------------------------------------------------------------------------
# Persist funnel
# ---------------------------------------------------------------------------


def _stream_one(
    agent: str,
    prompt: int = 11,
    completion: int = 5,
    cfg: dict[str, Any] | None = None,
) -> None:
    chunks = [_delta("x", "stop"), _usage_chunk(_usage(prompt, completion))]
    with patch("spec4.llm.litellm.completion", return_value=iter(chunks)):
        list(
            llm.complete_stream(
                llm_config=cfg or _CFG, messages=[], agent_name=agent
            )
        )


class TestPersistFlush:
    def test_persist_artifacts_flushes_under_pinned_version(
        self, tmp_path: Path
    ) -> None:
        _stream_one("scout")
        session = {**_default_session(), "working_dir": str(tmp_path)}
        _persist_artifacts(session)
        assert session["phase_version"] == 0
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        assert data["agents"]["agentifier"]["history"][0]["agent"] == "scout"
        assert data["agents"]["agentifier"]["input_tokens"] == 11
        assert data["notes"]["fast_forward"] is False
        assert llm.drain_usage_records() == []

    def test_fast_forward_turn_is_noted(self, tmp_path: Path) -> None:
        _stream_one("phaser")
        session = {
            **_default_session(),
            "working_dir": str(tmp_path),
            "messages": [
                {"role": "user", "content": FF_PROMPT},
                {"role": "assistant", "content": "done"},
            ],
        }
        _persist_artifacts(session)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        assert data["notes"]["fast_forward"] is True

    def test_every_turn_writes_not_only_round_end(self, tmp_path: Path) -> None:
        session = {**_default_session(), "working_dir": str(tmp_path)}
        _stream_one("brainstormer")
        _persist_artifacts(session)
        _stream_one("stack_advisor")
        _persist_artifacts(session)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        assert set(data["agents"]) == {"brainstormer", "stack_advisor"}
        assert data["totals"]["calls"] == 2

    def test_usage_write_failure_does_not_block_artifacts(
        self, tmp_path: Path
    ) -> None:
        _stream_one("brainstormer")
        session = {
            **_default_session(),
            "working_dir": str(tmp_path),
            "brainstormer_state": STATE_VISION_COMPLETE,
            "vision_statement": {"app_name": "x"},
        }
        with patch(
            "spec4.project_manager.save_usage", side_effect=OSError("disk full")
        ):
            _persist_artifacts(session)
        assert (tmp_path / ".spec4" / "v0" / "vision.json").exists()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


class TestUsageReport:
    def test_table_has_a_row_per_agent_and_totals(self, tmp_path: Path) -> None:
        records = [
            _call("brainstormer", cached=40),
            _call("phaser", "claude-sonnet-4-5-20250929", "anthropic", 300, 50, 0.01),
            _call("phaser", prompt=None, completion=None, cost=None, missing=True),
        ]
        project_manager.save_usage(tmp_path, records, 0)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        table = usage_report.render_usage_table(data)
        lines = table.splitlines()
        assert lines[0].startswith("Round v0")
        assert lines[1].split() == [
            "agent",
            "calls",
            "input",
            "output",
            "cached",
            "models",
            "cost_usd",
        ]
        brainstormer = next(ln for ln in lines if ln.startswith("brainstormer"))
        assert brainstormer.split()[:5] == ["brainstormer", "1", "100", "20", "40"]
        assert "gpt-4o-mini (openai)" in brainstormer
        phaser = next(ln for ln in lines if ln.startswith("phaser"))
        assert phaser.split()[:5] == ["phaser", "2", "300", "50", "-"]
        assert "claude-sonnet-4-5-20250929 (anthropic)" in phaser
        total = next(ln for ln in lines if ln.startswith("TOTAL"))
        assert total.split()[:5] == ["TOTAL", "3", "400", "70", "40"]
        assert total.split()[-1] == "0.0110"
        assert "1 call(s) returned no usage" in table

    def test_main_prints_latest_round_by_default(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        project_manager.save_usage(tmp_path, [_call("phaser")], 0)
        project_manager.save_usage(tmp_path, [_call("deployer")], 1)
        assert usage_report.main([str(tmp_path)]) == 0
        out = capsys.readouterr().out
        assert "Round v1" in out
        assert "deployer" in out
        assert usage_report.main([str(tmp_path), "--round", "0"]) == 0
        assert "Round v0" in capsys.readouterr().out

    def test_main_reports_missing_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert usage_report.main([str(tmp_path)]) == 1
        assert "No .spec4/v*/ round" in capsys.readouterr().err
        (tmp_path / ".spec4" / "v0").mkdir(parents=True)
        assert usage_report.main([str(tmp_path)]) == 1
        assert "No readable usage.json" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# A real agent turn: missing usage never breaks the run
# ---------------------------------------------------------------------------


class TestAgentRunWithMissingUsage:
    def test_brainstormer_turn_completes_and_is_recorded(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from spec4.agents import brainstormer

        chunks = [_delta("Who "), _delta("is it "), _delta("for?", "stop")]
        session = {**_default_session(), "active_agent": "brainstormer"}
        with (
            caplog.at_level(logging.WARNING, logger="spec4.llm"),
            patch.object(brainstormer.llm, "build_system_prompt", return_value=""),
            patch("spec4.llm.litellm.completion", return_value=iter(chunks)),
        ):
            out = list(brainstormer.run("go", session, {"model": "gpt-4o-mini"}))
        assert "".join(out) == "Who is it for?"
        rec = _only_record()
        assert rec["agent"] == "brainstormer"
        assert rec["usage_missing"] is True
        assert rec["prompt_tokens"] is None
        assert "LLM usage missing for agent=brainstormer" in caplog.text


# ---------------------------------------------------------------------------
# Chat row: the finished turn's token readout next to the chars counter
# ---------------------------------------------------------------------------


def _row_ids_and_texts(session: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    from spec4.layouts._chat import _chat_action_buttons

    ids: list[str] = []
    texts: dict[str, Any] = {}

    def walk(node: Any) -> None:
        if isinstance(node, list | tuple):
            for item in node:
                walk(item)
            return
        node_id = getattr(node, "id", None)
        if isinstance(node_id, str):
            ids.append(node_id)
            texts[node_id] = getattr(node, "children", None)
        children = getattr(node, "children", None)
        if children is not None:
            walk(children)

    walk(_chat_action_buttons(session))
    return ids, texts


_USAGE_PHASER = {
    "agent": "phaser",
    "input": 4180,
    "output": 312,
    "calls": 1,
    "missing": 0,
}


class TestTurnTokenReadout:
    def test_persist_records_the_turn_usage(self, tmp_path: Path) -> None:
        session = {
            **_default_session(),
            "working_dir": str(tmp_path),
            "active_agent": "brainstormer",
        }
        _stream_one("brainstormer", 4180, 312)
        _stream_one("feature_speccer", 900, 40)
        _persist_artifacts(session)
        assert session["_turn_usage"] == {
            "agent": "brainstormer",
            "input": 5080,
            "output": 352,
            "calls": 2,
            "missing": 0,
        }
        # A turn that made no call clears the previous numbers, and says so
        # rather than rendering nothing — a blank row reads as a broken counter.
        _persist_artifacts(session)
        assert session["_turn_usage"] == {
            "agent": "brainstormer",
            "input": 0,
            "output": 0,
            "calls": 0,
            "missing": 0,
        }
        assert _turn_token_text(session) == "no calls recorded"

    def test_persist_counts_missing_usage(self, tmp_path: Path) -> None:
        from spec4.session import _summarize_turn_usage

        summary = _summarize_turn_usage(
            "phaser",
            [
                _call("phaser", prompt=4180, completion=312),
                _call("phaser", prompt=None, completion=None, missing=True),
            ],
        )
        assert summary == {
            "agent": "phaser",
            "input": 4180,
            "output": 312,
            "calls": 2,
            "missing": 1,
        }

    def test_chars_counter_text_is_unchanged(self) -> None:
        from spec4.layouts._chat import _token_count_text

        session = {
            **_default_session(),
            "active_agent": "phaser",
            "_stream_received_chars": 8291,
            "_turn_usage": _USAGE_PHASER,
        }
        assert _token_count_text(session) == "Chars received: 8291"
        assert _token_count_text({**session, "_stream_id": "abc"}) == (
            "Chars received: 8291"
        )

    def test_readout_text_states(self) -> None:
        from spec4.layouts._chat import _turn_token_text

        base = {**_default_session(), "active_agent": "phaser"}
        usage = _USAGE_PHASER
        assert _turn_token_text({**base, "_turn_usage": usage}) == (
            "Tokens: 4,180 in / 312 out"
        )
        # Nothing while the stream is live — never estimated from characters.
        assert _turn_token_text({**base, "_turn_usage": usage, "_stream_id": "x"}) == ""
        # Nothing before any turn has finished.
        assert _turn_token_text(base) == ""
        # Nothing for a different agent's turn.
        assert _turn_token_text({**base, "active_agent": "deployer",
                                 "_turn_usage": usage}) == ""
        # All calls missing usage: a marker, not blank or zero.
        assert _turn_token_text(
            {**base, "_turn_usage": {**usage, "input": 0, "output": 0, "missing": 1}}
        ) == "no token count"
        # Some calls missing: the counted part, flagged.
        assert _turn_token_text(
            {**base, "_turn_usage": {**usage, "calls": 2, "missing": 1}}
        ) == "Tokens: 4,180 in / 312 out (partial)"

    def test_row_places_readout_right_after_the_counter_once_done(self) -> None:
        session = {
            **_default_session(),
            "active_agent": "phaser",
            "phaser_state": "in_progress",
            "_stream_received_chars": 8291,
            "messages": [{"role": "assistant", "content": "x" * 8291}],
            "_turn_usage": _USAGE_PHASER,
        }
        ids, texts = _row_ids_and_texts(session)
        assert ids.index("chat-turn-tokens") == ids.index("chat-token-count") + 1
        assert texts["chat-token-count"] == "Chars received: 8291"
        assert texts["chat-turn-tokens"] == "Tokens: 4,180 in / 312 out"

    def test_row_has_no_readout_while_streaming(self) -> None:
        session = {
            **_default_session(),
            "active_agent": "phaser",
            "_stream_id": "abc",
            "_stream_received_chars": 512,
            "messages": [{"role": "assistant", "content": ""}],
            "_turn_usage": _USAGE_PHASER,
        }
        ids, texts = _row_ids_and_texts(session)
        assert "chat-turn-tokens" not in ids
        assert texts["chat-token-count"] == "Chars received: 512"
        assert ids.index("chat-elapsed") == ids.index("chat-token-count") + 1

    def test_row_shows_marker_when_usage_was_missing(self) -> None:
        session = {
            **_default_session(),
            "active_agent": "phaser",
            "_stream_received_chars": 8291,
            "messages": [{"role": "assistant", "content": "x"}],
            "_turn_usage": {**_USAGE_PHASER, "input": 0, "output": 0, "missing": 1},
        }
        ids, texts = _row_ids_and_texts(session)
        assert texts["chat-turn-tokens"] == "no token count"


class TestFinalisationRunsOnce:
    """A second poll into the done branch must not wipe the turn's readout.

    The done branch is re-entrant by design — entries are evicted at the next
    ``start()`` rather than popped, so racing polls both reach it and were
    assumed to return a byte-identical store. `_persist_artifacts` broke that
    assumption: it drains the process-global usage sink, so the second run found
    it empty, set `_turn_usage` to None, and the chat row lost its token numbers
    while the chars counter beside them stayed. Observed on a finished
    Brainstormer turn.
    """

    def _finished_stream(self, tmp_path: Any) -> tuple[dict[str, Any], str]:
        from spec4 import streaming

        session = {
            **_default_session(),
            "active_agent": "brainstormer",
            "working_dir": str(tmp_path),
            "llm_config": {"model": "gpt-4o-mini"},
            "messages": [{"role": "assistant", "content": ""}],
            "brainstormer_state": "vision_complete",
            "vision_statement": {"app_name": "x"},
        }
        llm.drain_usage_records()

        def gen() -> Any:
            yield "hello"
            llm._record_usage(
                agent_name="brainstormer",
                kwargs={"model": "gpt-4o-mini"},
                response=None,
                usage=_usage(4180, 312),
                streamed=True,
                started_at="2026-01-01T00:00:00+00:00",
                start_mono=0.0,
            )

        stream_id = streaming.start(gen(), session)
        for _ in range(200):
            entry = streaming.get(stream_id)
            if entry and entry["done"]:
                break
            time.sleep(0.01)
        return {**session, "_stream_id": stream_id}, stream_id

    def test_racing_polls_return_the_same_readout(self, tmp_path: Any) -> None:
        from spec4.callbacks import on_stream_poll

        live, _ = self._finished_stream(tmp_path)
        stores = [on_stream_poll(n, live)[0] for n in (1, 2, 3)]
        usages = [s["_turn_usage"] for s in stores]
        assert usages[0] == {
            "agent": "brainstormer",
            "input": 4180,
            "output": 312,
            "calls": 1,
            "missing": 0,
        }
        assert usages[0] == usages[1] == usages[2]
        assert all(_turn_token_text(s) == "Tokens: 4,180 in / 312 out" for s in stores)

    def test_the_claim_is_granted_exactly_once(self, tmp_path: Any) -> None:
        from spec4 import streaming

        _, stream_id = self._finished_stream(tmp_path)
        assert streaming.claim_finalise(stream_id) is True
        assert streaming.claim_finalise(stream_id) is False
        assert streaming.claim_finalise(stream_id) is False

    def test_an_unknown_stream_is_never_claimable(self) -> None:
        from spec4 import streaming

        assert streaming.claim_finalise("no-such-stream") is False

    def test_artifacts_are_written_once_not_per_poll(self, tmp_path: Any) -> None:
        from spec4.callbacks import on_stream_poll

        live, _ = self._finished_stream(tmp_path)
        with patch("spec4.callbacks._persist_artifacts") as persist:
            for n in (1, 2, 3):
                on_stream_poll(n, live)
        assert persist.call_count == 1


class TestNoCallsMarker:
    """A finished turn always says something, never nothing.

    Three silences used to look identical on screen — a turn that made no
    calls, a turn whose capture path broke, and a turn that never ran. Only the
    last one should render nothing, and it is the only one distinguishable
    without a marker (no `_turn_usage` key at all).
    """

    def _row(self, session: dict[str, Any]) -> str:
        return _turn_token_text(session)

    def test_zero_calls_shows_the_marker(self) -> None:
        session = {
            **_default_session(),
            "active_agent": "phaser",
            "_turn_usage": {
                "agent": "phaser",
                "input": 0,
                "output": 0,
                "calls": 0,
                "missing": 0,
            },
        }
        assert self._row(session) == "no calls recorded"

    def test_it_is_distinct_from_the_missing_usage_marker(self) -> None:
        base = {**_default_session(), "active_agent": "phaser"}
        no_calls = {
            **base,
            "_turn_usage": {
                "agent": "phaser",
                "input": 0,
                "output": 0,
                "calls": 0,
                "missing": 0,
            },
        }
        no_usage = {
            **base,
            "_turn_usage": {
                "agent": "phaser",
                "input": 0,
                "output": 0,
                "calls": 2,
                "missing": 2,
            },
        }
        assert self._row(no_calls) != self._row(no_usage)
        assert self._row(no_usage) == "no token count"

    def test_a_turn_that_never_ran_still_shows_nothing(self) -> None:
        """The one legitimate silence: no turn has finished for this agent."""
        session = {**_default_session(), "active_agent": "phaser"}
        assert "_turn_usage" not in session
        assert self._row(session) == ""

    def test_another_agents_summary_still_shows_nothing(self) -> None:
        session = {
            **_default_session(),
            "active_agent": "phaser",
            "_turn_usage": {
                "agent": "brainstormer",
                "input": 0,
                "output": 0,
                "calls": 0,
                "missing": 0,
            },
        }
        assert self._row(session) == ""

    def test_the_marker_reaches_the_chat_row(self) -> None:
        session = {
            **_default_session(),
            "active_agent": "phaser",
            "phaser_state": "in_progress",
            "_stream_received_chars": 8291,
            "messages": [{"role": "assistant", "content": "x" * 8291}],
            "_turn_usage": {
                "agent": "phaser",
                "input": 0,
                "output": 0,
                "calls": 0,
                "missing": 0,
            },
        }
        ids, texts = _row_ids_and_texts(session)
        assert texts["chat-turn-tokens"] == "no calls recorded"
        assert ids.index("chat-turn-tokens") == ids.index("chat-token-count") + 1

    def test_the_summariser_never_returns_none(self) -> None:
        from spec4.session import _summarize_turn_usage

        assert _summarize_turn_usage("phaser", []) == {
            "agent": "phaser",
            "input": 0,
            "output": 0,
            "calls": 0,
            "missing": 0,
        }
