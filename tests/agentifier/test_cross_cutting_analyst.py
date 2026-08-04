"""Tests for the Cross-Cutting Analyst sub-agent."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from spec4.agentifier.cross_cutting_analyst import (
    CROSS_CUTTING_TOPICS,
    CrossCuttingAnalyst,
    CrossCuttingInput,
    _build_system_prompt,
    _feature_digest,
)
from spec4.agentifier.pattern_loader import load_patterns

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_LLM_CONFIG = {"model": "gpt-4o-mini", "api_key": "sk-test"}

_SAMPLE_FEATURES = [
    {
        "name": "smart_search",
        "tier": "single_call",
        "purpose": "Natural language restaurant search",
        "mechanisms": [],
        "tool_access": None,
    },
    {
        "name": "review_summariser",
        "tier": "rag",
        "purpose": "Summarise customer reviews from vector store",
        "mechanisms": [{"name": "retrieval_reranking", "rationale": "Improve relevance"}],
        "tool_access": None,
    },
    {
        "name": "booking_agent",
        "tier": "tool_agent",
        "purpose": "Book restaurants via API",
        "mechanisms": [],
        "tool_access": {
            "capabilities_needed": [
                {
                    "purpose": "Call booking API",
                    "source": "existing_third_party_non_mcp",
                    "mcp_server": None,
                    "protocol": "direct",
                    "rationale": "Single consumer, no MCP needed",
                }
            ]
        },
    },
]

_FULL_ANALYSIS = {t: {"recommendation": f"rec for {t}", "rationale": "rationale", "cited_patterns": []} for t in CROSS_CUTTING_TOPICS}
_FULL_ANALYSIS["tool_protocol_strategy"]["cited_patterns"] = ["mcp"]

_SINGLE_TOPIC_REVISION = {
    "topic": "provider_strategy",
    "recommendation": "Revised provider strategy recommendation",
    "rationale": "Revised rationale",
    "cited_patterns": [],
}


def _make_streaming_mock(obj: dict[str, Any]) -> Any:
    text = "```json\n" + json.dumps(obj) + "\n```"
    words = text.split()

    async def _acompletion(**kwargs: Any) -> Any:
        async def _gen() -> Any:
            for w in words:
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = w + " "
                yield chunk

        return _gen()

    return _acompletion


def _make_input(
    topic: str | None = None,
    revision: str | None = None,
) -> CrossCuttingInput:
    _, mechanisms = load_patterns()
    return CrossCuttingInput(
        ai_features=_SAMPLE_FEATURES,
        mechanism_patterns=mechanisms,
        llm_config=_LLM_CONFIG,
        topic=topic,
        revision_instruction=revision,
    )


async def _drain(agent_input: CrossCuttingInput) -> list[str]:
    chunks: list[str] = []
    async for chunk in CrossCuttingAnalyst().stream(agent_input):
        chunks.append(chunk)
    return chunks


# ---------------------------------------------------------------------------
# CROSS_CUTTING_TOPICS
# ---------------------------------------------------------------------------


class TestCrossCuttingTopics:
    def test_has_three_topics(self) -> None:
        assert len(CROSS_CUTTING_TOPICS) == 3

    def test_survivor_topics_present(self) -> None:
        survivors = {
            "provider_strategy",
            "tool_protocol_strategy",
            "prompt_versioning",
        }
        assert survivors == set(CROSS_CUTTING_TOPICS)


# ---------------------------------------------------------------------------
# _build_system_prompt
# ---------------------------------------------------------------------------


class TestSystemPromptContent:
    def _full_prompt(self) -> str:
        _, mechanisms = load_patterns()
        return _build_system_prompt(mechanisms, list(CROSS_CUTTING_TOPICS))

    def _single_prompt(self, topic: str) -> str:
        _, mechanisms = load_patterns()
        return _build_system_prompt(mechanisms, [topic])

    def test_full_prompt_core_content(self) -> None:
        _, mechanisms = load_patterns()
        prompt = _build_system_prompt(mechanisms, list(CROSS_CUTTING_TOPICS))
        lower = prompt.lower()
        # Every topic and every mechanism name appears.
        for t in CROSS_CUTTING_TOPICS:
            assert t in prompt
        for m in mechanisms:
            assert m.name in prompt
        # MCP pattern, build-vs-reuse, and consumption/exposure framing.
        assert "mcp" in prompt
        assert "reuse" in lower or "build" in lower
        assert "consumption" in lower or "consumer" in lower
        # JSON-only output instruction.
        assert "json" in lower
        assert "no prose" in lower or "only" in lower

    def test_single_topic_prompt(self) -> None:
        names = self._single_prompt("provider_strategy")
        assert "provider_strategy" in names
        revision = self._single_prompt("prompt_versioning")
        assert "Revise" in revision or "revision" in revision.lower()

    def test_provider_strategy_lane_rules(self) -> None:
        full = self._full_prompt().lower()
        # Capability anchor is allowed…
        assert "capability" in full
        assert "power reference" in full or "comparable to" in full
        # …but vendor selection is forbidden (the stack-selection lane).
        assert "stack-selection" in full
        assert "not select a provider" in full  # matches "MUST NOT select a provider"
        # The lane rule is also present in the single-topic prompt.
        assert "stack-selection" in self._single_prompt("provider_strategy").lower()


# ---------------------------------------------------------------------------
# _feature_digest
# ---------------------------------------------------------------------------


class TestFeatureDigest:
    def test_includes_all_feature_names(self) -> None:
        digest = _feature_digest(_SAMPLE_FEATURES)
        for f in _SAMPLE_FEATURES:
            assert f["name"] in digest

    def test_includes_tier(self) -> None:
        digest = _feature_digest(_SAMPLE_FEATURES)
        assert "single_call" in digest
        assert "tool_agent" in digest

    def test_includes_mechanism_name(self) -> None:
        digest = _feature_digest(_SAMPLE_FEATURES)
        assert "retrieval_reranking" in digest

    def test_includes_tool_protocol(self) -> None:
        digest = _feature_digest(_SAMPLE_FEATURES)
        assert "direct" in digest


# ---------------------------------------------------------------------------
# CrossCuttingAnalyst LLM calls
# ---------------------------------------------------------------------------


class TestCrossCuttingAnalystLlmCalls:
    def test_agent_name_is_correct(self) -> None:
        assert CrossCuttingAnalyst().name == "cross_cutting_analyst"

    def test_returns_async_generator(self) -> None:
        import inspect

        inp = _make_input()

        async def _check() -> None:
            with patch(
                "spec4.agentifier.cross_cutting_analyst.acomplete",
                new=_make_streaming_mock(_FULL_ANALYSIS),
            ):
                gen = CrossCuttingAnalyst().stream(inp)
                assert inspect.isasyncgen(gen)

        asyncio.run(_check())

    def test_yields_multiple_chunks(self) -> None:
        with patch(
            "spec4.agentifier.cross_cutting_analyst.acomplete",
            new=_make_streaming_mock(_FULL_ANALYSIS),
        ):
            chunks = asyncio.run(_drain(_make_input()))
        assert len(chunks) > 1

    def test_passes_agent_name(self) -> None:
        captured: list[dict[str, Any]] = []

        async def _cap(**kwargs: Any) -> Any:
            captured.append(kwargs)

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = "x"
                yield c

            return _gen()

        with patch("spec4.agentifier.cross_cutting_analyst.acomplete", new=_cap):
            asyncio.run(_drain(_make_input()))

        # The agent identifies itself to acomplete() via agent_name.
        assert captured[0].get("agent_name") == "cross_cutting_analyst"

    def test_stream_flag_set(self) -> None:
        captured: list[dict[str, Any]] = []

        async def _cap(**kwargs: Any) -> Any:
            captured.append(kwargs)

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = "x"
                yield c

            return _gen()

        with patch("spec4.agentifier.cross_cutting_analyst.acomplete", new=_cap):
            asyncio.run(_drain(_make_input()))

        assert captured[0].get("stream") is True

    def test_passes_api_key(self) -> None:
        captured: list[dict[str, Any]] = []

        async def _cap(**kwargs: Any) -> Any:
            captured.append(kwargs)

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = "x"
                yield c

            return _gen()

        with patch("spec4.agentifier.cross_cutting_analyst.acomplete", new=_cap):
            asyncio.run(_drain(_make_input()))

        assert captured[0]["llm_config"]["api_key"] == "sk-test"

    def test_passes_api_base_when_present(self) -> None:
        _, mechanisms = load_patterns()
        inp = CrossCuttingInput(
            ai_features=_SAMPLE_FEATURES,
            mechanism_patterns=mechanisms,
            llm_config={**_LLM_CONFIG, "api_base": "https://custom.example.com/v1"},
        )
        captured: list[dict[str, Any]] = []

        async def _cap(**kwargs: Any) -> Any:
            captured.append(kwargs)

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = "x"
                yield c

            return _gen()

        with patch("spec4.agentifier.cross_cutting_analyst.acomplete", new=_cap):
            asyncio.run(_drain(inp))

        assert captured[0]["llm_config"]["api_base"] == "https://custom.example.com/v1"

    def test_validates_input_type(self) -> None:
        with pytest.raises(TypeError):
            asyncio.run(_drain("not a CrossCuttingInput"))  # type: ignore[arg-type]

    def test_system_message_in_call(self) -> None:
        captured: list[dict[str, Any]] = []

        async def _cap(**kwargs: Any) -> Any:
            captured.append(kwargs)

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = "x"
                yield c

            return _gen()

        with patch("spec4.agentifier.cross_cutting_analyst.acomplete", new=_cap):
            asyncio.run(_drain(_make_input()))

        messages = captured[0]["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"


# ---------------------------------------------------------------------------
# Single-topic revision
# ---------------------------------------------------------------------------


class TestSingleTopicRevision:
    def test_revision_instruction_in_user_message(self) -> None:
        captured: list[dict[str, Any]] = []

        async def _cap(**kwargs: Any) -> Any:
            captured.append(kwargs)

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = "x"
                yield c

            return _gen()

        inp = _make_input(topic="provider_strategy", revision="Anchor to a frontier-tier model")
        with patch("spec4.agentifier.cross_cutting_analyst.acomplete", new=_cap):
            asyncio.run(_drain(inp))

        user_msg = captured[0]["messages"][1]["content"]
        assert "frontier-tier" in user_msg

    def test_single_topic_in_system_prompt(self) -> None:
        captured: list[dict[str, Any]] = []

        async def _cap(**kwargs: Any) -> Any:
            captured.append(kwargs)

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = "x"
                yield c

            return _gen()

        inp = _make_input(topic="provider_strategy")
        with patch("spec4.agentifier.cross_cutting_analyst.acomplete", new=_cap):
            asyncio.run(_drain(inp))

        system = captured[0]["messages"][0]["content"]
        assert "provider_strategy" in system
        assert "Revise" in system or "revision" in system.lower()

    def test_prior_decision_in_user_message_when_set(self) -> None:
        captured: list[dict[str, Any]] = []

        async def _cap(**kwargs: Any) -> Any:
            captured.append(kwargs)

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = "x"
                yield c

            return _gen()

        _, mechanisms = load_patterns()
        inp = CrossCuttingInput(
            ai_features=_SAMPLE_FEATURES,
            mechanism_patterns=mechanisms,
            llm_config=_LLM_CONFIG,
            topic="provider_strategy",
            revision_instruction="Bump the tier",
            prior_decisions={"provider_strategy": {"recommendation": "Use a small model"}},
        )
        with patch("spec4.agentifier.cross_cutting_analyst.acomplete", new=_cap):
            asyncio.run(_drain(inp))

        user_msg = captured[0]["messages"][1]["content"]
        assert "small model" in user_msg


# ---------------------------------------------------------------------------
# _extract_cross_cutting_analysis (via agentifier module)
# ---------------------------------------------------------------------------


class TestExtractCrossCuttingAnalysis:
    def test_extracts_full_analysis(self) -> None:
        from spec4.agentifier.agentifier import _extract_cross_cutting_analysis

        text = "```json\n" + json.dumps(_FULL_ANALYSIS) + "\n```"
        result = _extract_cross_cutting_analysis(text)
        assert result is not None
        for t in CROSS_CUTTING_TOPICS:
            assert t in result

    def test_extracts_single_topic(self) -> None:
        from spec4.agentifier.agentifier import _extract_cross_cutting_analysis

        text = "```json\n" + json.dumps(_SINGLE_TOPIC_REVISION) + "\n```"
        result = _extract_cross_cutting_analysis(text)
        assert result is not None
        assert "provider_strategy" in result
        assert result["provider_strategy"]["recommendation"] == "Revised provider strategy recommendation"

    def test_returns_none_for_empty_text(self) -> None:
        from spec4.agentifier.agentifier import _extract_cross_cutting_analysis

        assert _extract_cross_cutting_analysis("") is None

    def test_returns_none_for_unrelated_json(self) -> None:
        from spec4.agentifier.agentifier import _extract_cross_cutting_analysis

        text = '```json\n{"foo": "bar"}\n```'
        assert _extract_cross_cutting_analysis(text) is None


# ---------------------------------------------------------------------------
# Topic gating
# ---------------------------------------------------------------------------


class TestWarrantedTopics:
    def test_deterministic_only_yields_nothing(self) -> None:
        from spec4.agentifier.cross_cutting_analyst import warranted_topics

        assert warranted_topics([{"tier": "deterministic"}]) == []

    def test_embeddings_yields_provider_only(self) -> None:
        from spec4.agentifier.cross_cutting_analyst import warranted_topics

        # Embeddings need a provider but have no generative prompt to version.
        assert warranted_topics([{"tier": "embeddings"}]) == ["provider_strategy"]

    def test_single_call_yields_provider_and_prompt(self) -> None:
        from spec4.agentifier.cross_cutting_analyst import warranted_topics

        assert warranted_topics([{"tier": "single_call"}]) == [
            "provider_strategy",
            "prompt_versioning",
        ]

    def test_tool_access_adds_tool_protocol(self) -> None:
        from spec4.agentifier.cross_cutting_analyst import warranted_topics

        feature = {
            "tier": "tool_agent",
            "tool_access": {"capabilities_needed": [{"purpose": "call api"}]},
        }
        assert warranted_topics([feature]) == [
            "provider_strategy",
            "tool_protocol_strategy",
            "prompt_versioning",
        ]

    def test_unknown_tier_defaults_to_generative(self) -> None:
        from spec4.agentifier.cross_cutting_analyst import warranted_topics

        # Unknown tier defaults to single_call (3): provider + prompt offered.
        assert warranted_topics([{"tier": "???"}]) == [
            "provider_strategy",
            "prompt_versioning",
        ]

    def test_prompt_versioning_is_the_only_skippable(self) -> None:
        from spec4.agentifier.cross_cutting_analyst import SKIPPABLE_TOPICS

        assert set(SKIPPABLE_TOPICS) == {"prompt_versioning"}
