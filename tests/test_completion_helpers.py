"""Tests for the completion helpers in llm.

Covers:
- complete() — non-streaming helper: kwarg assembly, credential plumbing
- acomplete() — async helper: same, plus error propagation
- stream_turn() — errors propagate unchanged
- No temperature is ever sent, on any path, by any helper
- Per-sub-agent integration: each passes agent_name and credentials
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm.exceptions import BadRequestError as LiteLLMBadRequestError

from spec4.llm import (
    LLM_STREAM_TIMEOUT,
    acomplete,
    complete,
    complete_stream,
    stream_turn,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LLM_CONFIG = {"model": "gpt-4o-mini", "api_key": "sk-test"}
_LLM_CONFIG_WITH_BASE = {**_LLM_CONFIG, "api_base": "https://custom.example.com/v1"}


def _make_response(content: str = "ok") -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.content = content
    return resp


def _temp_worded_exc() -> LiteLLMBadRequestError:
    return LiteLLMBadRequestError(
        message="`temperature` is deprecated for this model.",
        model="claude-opus-4-8",
        llm_provider="anthropic",
    )


def _auth_exc() -> LiteLLMBadRequestError:
    return LiteLLMBadRequestError(
        message="Invalid API key provided.",
        model="gpt-4o",
        llm_provider="openai",
    )


# ---------------------------------------------------------------------------
# complete() — non-streaming helper
# ---------------------------------------------------------------------------


class TestCompleteHelper:
    def test_never_sends_temperature(self) -> None:
        mock_resp = _make_response()
        with patch(
            "spec4.llm.litellm.completion", return_value=mock_resp
        ) as mock_llm:
            complete(llm_config=_LLM_CONFIG, messages=[], agent_name="tier_analyst")
        assert "temperature" not in mock_llm.call_args[1]

    def test_llm_config_temperature_is_not_forwarded(self) -> None:
        mock_resp = _make_response()
        with patch(
            "spec4.llm.litellm.completion", return_value=mock_resp
        ) as mock_llm:
            complete(
                llm_config={**_LLM_CONFIG, "temperature": 0.9},
                messages=[],
                agent_name="tier_analyst",
            )
        assert "temperature" not in mock_llm.call_args[1]

    def test_no_retry_on_temperature_worded_error(self) -> None:
        """With no temperature sent, there is nothing to retry — errors surface."""
        with patch(
            "spec4.llm.litellm.completion",
            side_effect=_temp_worded_exc(),
        ) as mock_llm:
            with pytest.raises(LiteLLMBadRequestError):
                complete(
                    llm_config=_LLM_CONFIG, messages=[], agent_name="tier_analyst"
                )
        assert mock_llm.call_count == 1

    def test_error_propagates(self) -> None:
        with patch(
            "spec4.llm.litellm.completion",
            side_effect=_auth_exc(),
        ) as mock_llm:
            with pytest.raises(LiteLLMBadRequestError):
                complete(
                    llm_config=_LLM_CONFIG, messages=[], agent_name="tier_analyst"
                )
        assert mock_llm.call_count == 1

    def test_propagates_api_key(self) -> None:
        mock_resp = _make_response()
        with patch(
            "spec4.llm.litellm.completion", return_value=mock_resp
        ) as mock_llm:
            complete(llm_config=_LLM_CONFIG, messages=[])
        assert mock_llm.call_args[1].get("api_key") == "sk-test"

    def test_propagates_api_base(self) -> None:
        mock_resp = _make_response()
        with patch(
            "spec4.llm.litellm.completion", return_value=mock_resp
        ) as mock_llm:
            complete(llm_config=_LLM_CONFIG_WITH_BASE, messages=[])
        assert (
            mock_llm.call_args[1].get("api_base") == "https://custom.example.com/v1"
        )

    def test_aws_keys_forwarded(self) -> None:
        llm_config = {
            "model": "bedrock/claude",
            "aws_access_key_id": "AKID",
            "aws_secret_access_key": "SECRET",
            "aws_region_name": "us-east-1",
            "aws_session_token": "TOKEN",
        }
        mock_resp = _make_response()
        with patch(
            "spec4.llm.litellm.completion", return_value=mock_resp
        ) as mock_llm:
            complete(llm_config=llm_config, messages=[])
        kw = mock_llm.call_args[1]
        assert kw.get("aws_access_key_id") == "AKID"
        assert kw.get("aws_secret_access_key") == "SECRET"
        assert kw.get("aws_region_name") == "us-east-1"
        assert kw.get("aws_session_token") == "TOKEN"

    def test_extra_kwargs_forwarded(self) -> None:
        mock_resp = _make_response()
        with patch(
            "spec4.llm.litellm.completion", return_value=mock_resp
        ) as mock_llm:
            complete(llm_config=_LLM_CONFIG, messages=[], stream=False)
        assert mock_llm.call_args[1].get("stream") is False


# ---------------------------------------------------------------------------
# complete_stream() — streamed one-shot helper
# ---------------------------------------------------------------------------


def _delta_chunk(text: str | None) -> MagicMock:
    chunk = MagicMock()
    chunk.choices[0].delta.content = text
    return chunk


def _choiceless_chunk() -> MagicMock:
    chunk = MagicMock()
    chunk.choices = []
    return chunk


class TestCompleteStream:
    def test_yields_deltas_in_order(self) -> None:
        chunks = [_delta_chunk("a"), _delta_chunk("b"), _delta_chunk("c")]
        with patch("spec4.llm.litellm.completion", return_value=iter(chunks)):
            out = list(
                complete_stream(
                    llm_config=_LLM_CONFIG, messages=[], agent_name="scout"
                )
            )
        assert out == ["a", "b", "c"]

    def test_skips_empty_and_choiceless_chunks(self) -> None:
        chunks = [
            _choiceless_chunk(),
            _delta_chunk(None),
            _delta_chunk(""),
            _delta_chunk("x"),
        ]
        with patch("spec4.llm.litellm.completion", return_value=iter(chunks)):
            out = list(complete_stream(llm_config=_LLM_CONFIG, messages=[]))
        assert out == ["x"]

    def test_sends_stream_true_and_default_timeout(self) -> None:
        with patch(
            "spec4.llm.litellm.completion", return_value=iter([])
        ) as mock_llm:
            list(complete_stream(llm_config=_LLM_CONFIG, messages=[]))
        kw = mock_llm.call_args[1]
        assert kw.get("stream") is True
        assert kw.get("timeout") is LLM_STREAM_TIMEOUT

    def test_timeout_override(self) -> None:
        with patch(
            "spec4.llm.litellm.completion", return_value=iter([])
        ) as mock_llm:
            list(complete_stream(llm_config=_LLM_CONFIG, messages=[], timeout=5.0))
        assert mock_llm.call_args[1].get("timeout") == 5.0

    def test_never_sends_temperature(self) -> None:
        with patch(
            "spec4.llm.litellm.completion", return_value=iter([])
        ) as mock_llm:
            list(
                complete_stream(
                    llm_config={**_LLM_CONFIG, "temperature": 0.9}, messages=[]
                )
            )
        assert "temperature" not in mock_llm.call_args[1]

    def test_response_format_forwarded(self) -> None:
        fmt = {"type": "json_object"}
        with patch(
            "spec4.llm.litellm.completion", return_value=iter([])
        ) as mock_llm:
            list(
                complete_stream(
                    llm_config=_LLM_CONFIG, messages=[], response_format=fmt
                )
            )
        assert mock_llm.call_args[1].get("response_format") == fmt

    def test_credentials_forwarded(self) -> None:
        llm_config = {
            "model": "bedrock/claude",
            "aws_access_key_id": "AKID",
            "aws_secret_access_key": "SECRET",
            "aws_region_name": "us-east-1",
            "aws_session_token": "TOKEN",
            "api_base": "https://custom.example.com/v1",
        }
        with patch(
            "spec4.llm.litellm.completion", return_value=iter([])
        ) as mock_llm:
            list(complete_stream(llm_config=llm_config, messages=[]))
        kw = mock_llm.call_args[1]
        assert kw.get("aws_access_key_id") == "AKID"
        assert kw.get("aws_secret_access_key") == "SECRET"
        assert kw.get("aws_region_name") == "us-east-1"
        assert kw.get("aws_session_token") == "TOKEN"
        assert kw.get("api_base") == "https://custom.example.com/v1"

    def test_error_propagates(self) -> None:
        with patch("spec4.llm.litellm.completion", side_effect=_auth_exc()):
            with pytest.raises(LiteLLMBadRequestError):
                list(complete_stream(llm_config=_LLM_CONFIG, messages=[]))

    def test_mid_stream_error_propagates(self) -> None:
        def _chunks() -> Any:
            yield _delta_chunk("partial")
            raise TimeoutError("stall")

        with patch("spec4.llm.litellm.completion", return_value=_chunks()):
            received: list[str] = []
            with pytest.raises(TimeoutError):
                for delta in complete_stream(llm_config=_LLM_CONFIG, messages=[]):
                    received.append(delta)
        assert received == ["partial"]

    def test_ttft_logged_once(self, capsys: pytest.CaptureFixture[str]) -> None:
        chunks = [_delta_chunk("a"), _delta_chunk("b")]
        with patch("spec4.llm.litellm.completion", return_value=iter(chunks)):
            list(
                complete_stream(
                    llm_config=_LLM_CONFIG, messages=[], agent_name="scout"
                )
            )
        out = capsys.readouterr().out
        assert out.count("[llm-ttft] scout:") == 1


# ---------------------------------------------------------------------------
# acomplete() — async helper
# ---------------------------------------------------------------------------


class TestAcomplete:
    def test_never_sends_temperature(self) -> None:
        mock_resp = MagicMock()

        async def _run() -> None:
            with patch(
                "spec4.llm.litellm.acompletion",
                new=AsyncMock(return_value=mock_resp),
            ) as mock_llm:
                await acomplete(
                    llm_config=_LLM_CONFIG, messages=[], agent_name="spec_drafter"
                )
            assert "temperature" not in mock_llm.call_args[1]

        asyncio.run(_run())

    def test_llm_config_temperature_is_not_forwarded(self) -> None:
        mock_resp = MagicMock()

        async def _run() -> None:
            with patch(
                "spec4.llm.litellm.acompletion",
                new=AsyncMock(return_value=mock_resp),
            ) as mock_llm:
                await acomplete(
                    llm_config={**_LLM_CONFIG, "temperature": 0.9},
                    messages=[],
                    agent_name="spec_drafter",
                )
            assert "temperature" not in mock_llm.call_args[1]

        asyncio.run(_run())

    def test_no_retry_on_temperature_worded_error(self) -> None:
        async def _run() -> None:
            with patch(
                "spec4.llm.litellm.acompletion",
                new=AsyncMock(side_effect=_temp_worded_exc()),
            ) as mock_llm:
                with pytest.raises(LiteLLMBadRequestError):
                    await acomplete(
                        llm_config=_LLM_CONFIG,
                        messages=[],
                        agent_name="spec_drafter",
                    )
            assert mock_llm.call_count == 1

        asyncio.run(_run())

    def test_error_propagates(self) -> None:
        async def _run() -> None:
            with patch(
                "spec4.llm.litellm.acompletion",
                new=AsyncMock(side_effect=_auth_exc()),
            ) as mock_llm:
                with pytest.raises(LiteLLMBadRequestError):
                    await acomplete(
                        llm_config=_LLM_CONFIG,
                        messages=[],
                        agent_name="spec_drafter",
                    )
            assert mock_llm.call_count == 1

        asyncio.run(_run())

    def test_propagates_api_key(self) -> None:
        mock_resp = MagicMock()

        async def _run() -> None:
            with patch(
                "spec4.llm.litellm.acompletion",
                new=AsyncMock(return_value=mock_resp),
            ) as mock_llm:
                await acomplete(llm_config=_LLM_CONFIG, messages=[])
            assert mock_llm.call_args[1].get("api_key") == "sk-test"

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# stream_turn() — error propagation
# ---------------------------------------------------------------------------


class TestStreamTurnErrors:
    def test_no_retry_on_temperature_worded_error(self) -> None:
        call_count = 0

        def _completion(**kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            raise _temp_worded_exc()

        with patch("spec4.llm.litellm.completion", side_effect=_completion):
            with pytest.raises(LiteLLMBadRequestError):
                list(
                    stream_turn(
                        "sys", [], _LLM_CONFIG, None, agent_name="code_scanner"
                    )
                )
        assert call_count == 1

    def test_error_propagates_from_stream(self) -> None:
        with patch(
            "spec4.llm.litellm.completion",
            side_effect=_auth_exc(),
        ):
            with pytest.raises(LiteLLMBadRequestError):
                list(
                    stream_turn(
                        "sys", [], _LLM_CONFIG, None, agent_name="code_scanner"
                    )
                )


# ---------------------------------------------------------------------------
# Per-sub-agent: agent_name and credentials flow through
# ---------------------------------------------------------------------------


class TestSubAgentPassesAgentName:
    """Each sub-agent identifies itself via agent_name and forwards credentials."""

    def test_scout_passes_agent_name(self) -> None:
        from spec4.agentifier.scout import ScoutAgent, ScoutInput

        vision: dict[str, Any] = {
            "vision_statement": {"name": "X", "vision": {"key_features_mvp": []}}
        }
        inp = ScoutInput(vision=vision, llm_config=_LLM_CONFIG)
        with patch(
            "spec4.agentifier.scout.complete_stream", return_value=iter(["[]"])
        ) as mock_fn:
            asyncio.run(ScoutAgent().run(inp))
        assert mock_fn.call_args[1].get("agent_name") == "scout"

    def test_tier_analyst_passes_agent_name(self) -> None:
        from spec4.agentifier.scout import Candidate
        from spec4.agentifier.tier_analyst import TierAnalystAgent, TierAnalystInput

        cand = Candidate(
            name="x",
            linked_vision_features=[],
            scope="feature",
            rough_description="y",
        )
        inp = TierAnalystInput(candidate=cand, llm_config=_LLM_CONFIG)
        tier_json = json.dumps(
            {
                "recommended_tier": "deterministic",
                "rationale": "test",
                "risks_of_going_higher": [],
                "risks_of_going_lower": [],
                "borderline": False,
                "borderline_seams": [],
                "compared_to_next_tier_down": "",
            }
        )
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=iter([tier_json]),
        ) as mock_fn:
            asyncio.run(TierAnalystAgent().run(inp))
        assert mock_fn.call_args[1].get("agent_name") == "tier_analyst"

    def test_spec_drafter_passes_agent_name(self) -> None:
        from spec4.agentifier.pattern_loader import load_patterns
        from spec4.agentifier.spec_drafter import SpecDrafterAgent, SpecDrafterInput

        tiers, mechs = load_patterns()
        inp = SpecDrafterInput(
            catalog_entry={"tier_decision": "single_call", "name": "x"},
            llm_config=_LLM_CONFIG,
            tier_patterns=tiers,
            mechanism_patterns=mechs,
        )
        captured: list[dict[str, Any]] = []

        async def _mock_acomplete(**kwargs: Any) -> Any:
            captured.append(kwargs)

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = "x"
                yield c

            return _gen()

        async def _run() -> None:
            with patch(
                "spec4.agentifier.spec_drafter.acomplete", new=_mock_acomplete
            ):
                async for _ in SpecDrafterAgent().stream(inp):
                    pass

        asyncio.run(_run())
        assert captured[0].get("agent_name") == "spec_drafter"
        assert captured[0]["llm_config"]["api_key"] == "sk-test"

    def test_cross_cutting_analyst_passes_agent_name(self) -> None:
        from spec4.agentifier.cross_cutting_analyst import (
            CrossCuttingAnalyst,
            CrossCuttingInput,
        )
        from spec4.agentifier.pattern_loader import load_patterns

        _, mechs = load_patterns()
        inp = CrossCuttingInput(
            ai_features=[], mechanism_patterns=mechs, llm_config=_LLM_CONFIG
        )
        captured: list[dict[str, Any]] = []

        async def _mock_acomplete(**kwargs: Any) -> Any:
            captured.append(kwargs)

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = "x"
                yield c

            return _gen()

        async def _run() -> None:
            with patch(
                "spec4.agentifier.cross_cutting_analyst.acomplete",
                new=_mock_acomplete,
            ):
                async for _ in CrossCuttingAnalyst().stream(inp):
                    pass

        asyncio.run(_run())
        assert captured[0].get("agent_name") == "cross_cutting_analyst"
        assert captured[0]["llm_config"]["api_key"] == "sk-test"
