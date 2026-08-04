"""Streaming end-to-end integration tests.

Verifies that:
1. SpecDrafterAgent.stream() is a real async generator that yields multiple chunks.
2. The async→sync bridge _iter_async_gen() delivers all chunks in order.
3. The registry delivers SpecDrafter chunks through SubAgentRegistry.stream().
4. The orchestrator drives spec drafting per-feature with visible phase transitions.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from spec4.agentifier.agentifier import _iter_async_gen
from spec4.agentifier.pattern_loader import load_patterns
from spec4.agentifier.spec_drafter import SpecDrafterAgent, SpecDrafterInput
from spec4.agentifier.subagents import SubAgentRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LLM_CONFIG = {"model": "gpt-4o-mini", "api_key": "sk-test"}

_SAMPLE_SPEC_JSON = {
    "purpose": "Test purpose",
    "invocation": {"trigger": "user action", "mode": "synchronous"},
    "inputs": [],
    "outputs": {"primary": "result", "format": "JSON", "schema_notes": None},
    "decision_authority": "autonomous",
    "success_criteria": ["Works"],
    "failure_modes": [],
    "escalation": "Log and return empty",
    "eval_approach": {"offline": "golden set", "online": "metrics", "ground_truth": "labels"},
    "budgets": {"cost_per_call": "$0.001", "p95_latency": "500ms"},
    "privacy_safety": ["No PII"],
    "phase_priority": "mvp",
    "mechanisms": [],
    "references": [],
}

_SPEC_TEXT = "```json\n" + json.dumps(_SAMPLE_SPEC_JSON) + "\n```"
_WORDS = _SPEC_TEXT.split()


def _make_streaming_mock(words: list[str]) -> Any:
    """Return an acompletion coroutine that yields one chunk per word."""

    async def _acompletion(**kwargs: Any) -> Any:
        async def _gen() -> Any:
            for word in words:
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = word + " "
                yield chunk

        return _gen()

    return _acompletion


def _make_spec_input() -> SpecDrafterInput:
    tiers, mechanisms = load_patterns()
    return SpecDrafterInput(
        catalog_entry={
            "name": "test_feature",
            "tier_decision": "single_call",
            "scope": "feature",
            "rough_description": "A test feature",
        },
        llm_config=_LLM_CONFIG,
        tier_patterns=tiers,
        mechanism_patterns=mechanisms,
    )


# ---------------------------------------------------------------------------
# SpecDrafterAgent streaming protocol
# ---------------------------------------------------------------------------


class TestSpecDrafterStreaming:
    """Confirms SpecDrafterAgent.stream() is a true async generator."""

    def test_stream_is_async_generator(self) -> None:
        import inspect
        agent = SpecDrafterAgent()
        inp = _make_spec_input()

        async def _check() -> None:
            with patch(
                "spec4.agentifier.spec_drafter.acomplete",
                new=_make_streaming_mock(_WORDS),
            ):
                gen = agent.stream(inp)
                assert inspect.isasyncgen(gen)

        asyncio.run(_check())

    def test_yields_multiple_chunks_not_one_blob(self) -> None:
        chunks: list[str] = []

        async def _drain() -> None:
            with patch(
                "spec4.agentifier.spec_drafter.acomplete",
                new=_make_streaming_mock(_WORDS),
            ):
                async for chunk in SpecDrafterAgent().stream(_make_spec_input()):
                    chunks.append(chunk)

        asyncio.run(_drain())
        assert len(chunks) > 3, f"Expected >3 chunks, got {len(chunks)}"

    def test_chunks_concatenate_to_full_text(self) -> None:
        chunks: list[str] = []

        async def _drain() -> None:
            with patch(
                "spec4.agentifier.spec_drafter.acomplete",
                new=_make_streaming_mock(_WORDS),
            ):
                async for chunk in SpecDrafterAgent().stream(_make_spec_input()):
                    chunks.append(chunk)

        asyncio.run(_drain())
        full = "".join(chunks)
        assert "purpose" in full
        assert "mvp" in full

    def test_empty_delta_not_yielded(self) -> None:
        """Chunks with empty/None content are not yielded."""

        async def _acompletion(**kwargs: Any) -> Any:
            async def _gen() -> Any:
                for content in ["hello", None, "", "world", None]:
                    chunk = MagicMock()
                    chunk.choices = [MagicMock()]
                    chunk.choices[0].delta.content = content
                    yield chunk

            return _gen()

        chunks: list[str] = []

        async def _drain() -> None:
            with patch("spec4.agentifier.spec_drafter.acomplete", new=_acompletion):
                async for chunk in SpecDrafterAgent().stream(_make_spec_input()):
                    chunks.append(chunk)

        asyncio.run(_drain())
        assert all(c for c in chunks)  # no empty strings


# ---------------------------------------------------------------------------
# _iter_async_gen bridge
# ---------------------------------------------------------------------------


class TestIterAsyncGenBridge:
    def test_delivers_all_chunks_in_order(self) -> None:
        async def _gen() -> Any:
            for i in range(5):
                yield str(i)

        result = list(_iter_async_gen(_gen()))
        assert result == ["0", "1", "2", "3", "4"]

    def test_empty_generator(self) -> None:
        async def _gen() -> Any:
            return
            yield  # make it an async generator

        result = list(_iter_async_gen(_gen()))
        assert result == []

    def test_single_chunk(self) -> None:
        async def _gen() -> Any:
            yield "only"

        result = list(_iter_async_gen(_gen()))
        assert result == ["only"]

    def test_propagates_exception(self) -> None:
        async def _gen() -> Any:
            yield "ok"
            raise ValueError("test error")

        chunks: list[str] = []
        with pytest.raises(ValueError, match="test error"):
            for c in _iter_async_gen(_gen()):
                chunks.append(c)
        assert chunks == ["ok"]

    def test_large_chunk_count(self) -> None:
        N = 200

        async def _gen() -> Any:
            for i in range(N):
                yield str(i)

        result = list(_iter_async_gen(_gen()))
        assert len(result) == N
        assert result[0] == "0"
        assert result[-1] == str(N - 1)


# ---------------------------------------------------------------------------
# SubAgentRegistry streaming
# ---------------------------------------------------------------------------


class TestRegistryStreaming:
    def test_registry_delivers_spec_drafter_chunks(self) -> None:
        registry = SubAgentRegistry()
        registry.register(SpecDrafterAgent())
        chunks: list[str] = []

        async def _drain() -> None:
            with patch(
                "spec4.agentifier.spec_drafter.acomplete",
                new=_make_streaming_mock(["chunk1", "chunk2", "chunk3"]),
            ):
                async for c in registry.stream("spec_drafter", _make_spec_input()):
                    chunks.append(c)

        asyncio.run(_drain())
        assert len(chunks) == 3

    def test_registry_wraps_spec_drafter_errors(self) -> None:
        from spec4.agentifier.subagents import SubAgentError

        registry = SubAgentRegistry()
        registry.register(SpecDrafterAgent())

        async def _boom(**kwargs: Any) -> Any:
            raise RuntimeError("LLM unavailable")

        async def _drain() -> None:
            with patch("spec4.agentifier.spec_drafter.acomplete", new=_boom):
                async for _ in registry.stream("spec_drafter", _make_spec_input()):
                    pass

        with pytest.raises(SubAgentError):
            asyncio.run(_drain())


# ---------------------------------------------------------------------------
# Orchestrator feature-by-feature progression
# ---------------------------------------------------------------------------


class TestOrchestratorSpecPhase:
    """End-to-end: orchestrator drives spec drafting per feature."""

    def _make_session(self) -> dict[str, Any]:
        from spec4.session import _default_session

        session = _default_session()
        session["working_dir"] = "/tmp/spec4-e2e-project"
        session["vision_statement"] = {"vision_statement": {"name": "TestApp"}}
        session["llm_config"] = _LLM_CONFIG
        session["active_agent"] = "agentifier"
        session["ai_catalog"] = {
            "ai_catalog": [
                {
                    "name": "feature_a",
                    "scope": "feature",
                    "rough_description": "First feature",
                    "tier_recommendation": "single_call",
                    "tier_decision": "single_call",
                    "tier_decision_rationale": "",
                },
                {
                    "name": "feature_b",
                    "scope": "sub_feature",
                    "rough_description": "Second feature",
                    "tier_recommendation": "embeddings",
                    "tier_decision": "embeddings",
                    "tier_decision_rationale": "",
                },
            ]
        }
        session["agentifier_catalog_done"] = True
        session["agentifier_spec_index"] = 0
        session["agentifier_spec_results"] = []
        return session

    def _spec_mock(self) -> Any:
        text = "```json\n" + json.dumps(_SAMPLE_SPEC_JSON) + "\n```"
        words = text.split()
        return _make_streaming_mock(words)

    def test_first_user_input_triggers_spec_draft(self) -> None:
        session = self._make_session()

        with patch("litellm.acompletion", new=self._spec_mock()):
            from spec4.agentifier.agentifier import run as agentifier_run

            chunks = list(agentifier_run("yes", session, _LLM_CONFIG))

        combined = "".join(chunks)
        assert "feature_a" in combined or "Drafting" in combined

    def test_spec_results_populated_after_draft(self) -> None:
        session = self._make_session()

        with patch("litellm.acompletion", new=self._spec_mock()):
            from spec4.agentifier.agentifier import run as agentifier_run

            list(agentifier_run("yes", session, _LLM_CONFIG))

        spec_results = session.get("agentifier_spec_results") or []
        assert len(spec_results) >= 1
        assert spec_results[0].get("purpose") is not None

    def test_confirmation_advances_to_next_feature(self) -> None:
        session = self._make_session()

        with patch("litellm.acompletion", new=self._spec_mock()):
            from spec4.agentifier.agentifier import run as agentifier_run

            # Draft feature_a
            list(agentifier_run("yes", session, _LLM_CONFIG))
            assert session["agentifier_spec_index"] == 0

            # Confirm feature_a → advance to feature_b
            list(agentifier_run("yes", session, _LLM_CONFIG))
            assert session["agentifier_spec_index"] == 1

    def test_all_specs_confirmed_sets_spec_done(self) -> None:
        """After all per-feature specs confirmed, agentifier_spec_done is set."""
        session = self._make_session()
        # Provide a cross-cutting mock response too
        cc_json = {t: {"recommendation": "rec", "rationale": "rat", "cited_patterns": []} for t in [
            "provider_strategy", "tool_protocol_strategy", "prompt_versioning",
        ]}

        with patch("litellm.acompletion", new=self._spec_mock()):
            from spec4.agentifier.agentifier import run as agentifier_run

            with patch(
                "spec4.agentifier.agentifier._extract_cross_cutting_analysis",
                return_value=cc_json,
            ):
                list(agentifier_run("yes", session, _LLM_CONFIG))  # draft A
                list(agentifier_run("yes", session, _LLM_CONFIG))  # confirm A, draft B
                list(agentifier_run("yes", session, _LLM_CONFIG))  # confirm B → spec done

        assert session.get("agentifier_spec_done") is True
        assert session.get("ai_features") is not None
        assert len(session["ai_features"].get("ai_features", [])) == 2

    def test_ai_features_has_correct_schema_keys(self) -> None:
        """Per-feature schema keys are correct after spec phase completes."""
        session = self._make_session()
        cc_json = {t: {"recommendation": "rec", "rationale": "rat", "cited_patterns": []} for t in [
            "provider_strategy", "tool_protocol_strategy", "prompt_versioning",
        ]}

        with patch("litellm.acompletion", new=self._spec_mock()):
            from spec4.agentifier.agentifier import run as agentifier_run

            with patch(
                "spec4.agentifier.agentifier._extract_cross_cutting_analysis",
                return_value=cc_json,
            ):
                list(agentifier_run("yes", session, _LLM_CONFIG))
                list(agentifier_run("yes", session, _LLM_CONFIG))
                list(agentifier_run("yes", session, _LLM_CONFIG))

        features = session["ai_features"].get("ai_features", [])
        assert len(features) == 2
        for f in features:
            assert "id" in f
            assert "name" in f
            assert "tier" in f
            assert "purpose" in f

    def test_revision_instruction_reruns_spec_drafter(self) -> None:
        session = self._make_session()
        call_count = [0]
        original_mock = self._spec_mock()

        async def _counting_mock(**kwargs: Any) -> Any:
            call_count[0] += 1
            return await original_mock(**kwargs)

        with patch("litellm.acompletion", new=_counting_mock):
            from spec4.agentifier.agentifier import run as agentifier_run

            list(agentifier_run("yes", session, _LLM_CONFIG))  # first draft
            initial_calls = call_count[0]
            list(agentifier_run("change phase_priority to steel_thread", session, _LLM_CONFIG))

        assert call_count[0] > initial_calls  # spec drafter called again


# ---------------------------------------------------------------------------
# Cross-cutting phase
# ---------------------------------------------------------------------------

_CC_TOPICS = (
    "provider_strategy", "prompt_versioning",
)

_CC_ANALYSIS = {
    t: {"recommendation": f"rec_{t}", "rationale": "rat", "cited_patterns": []}
    for t in _CC_TOPICS
}


def _make_cc_session() -> dict[str, Any]:
    """Session already past the spec phase, ready for cross-cutting."""
    from spec4.session import _default_session

    session = _default_session()
    session["working_dir"] = "/tmp/spec4-cc-test"
    session["llm_config"] = _LLM_CONFIG
    session["active_agent"] = "agentifier"
    session["agentifier_catalog_done"] = True
    session["agentifier_spec_done"] = True
    session["ai_catalog"] = {
        "ai_catalog": [
            {"name": "fa", "scope": "feature", "rough_description": "desc",
             "tier_recommendation": "single_call", "tier_decision": "single_call",
             "tier_decision_rationale": ""},
        ]
    }
    session["ai_features"] = {
        "ai_features": [{"id": "fa", "name": "fa", "tier": "single_call", "purpose": "p",
                         "phase_priority": "mvp"}],
        "cross_cutting": {},
        "explicitly_rejected": [],
        "references": [],
    }
    session["agentifier_cross_cutting_topics"] = list(_CC_TOPICS)
    session["agentifier_cross_cutting_analysis"] = _CC_ANALYSIS
    session["agentifier_cross_cutting_index"] = 0
    session["agentifier_cross_cutting_decisions"] = {}
    session["agentifier_messages"] = [{"role": "assistant", "content": "first topic"}]
    return session


class TestOrchestratorCrossCuttingPhase:
    def test_confirm_advances_topic_index(self) -> None:
        session = _make_cc_session()
        from spec4.agentifier.agentifier import run as agentifier_run

        list(agentifier_run("yes", session, _LLM_CONFIG))

        assert session["agentifier_cross_cutting_index"] == 1

    def test_confirm_records_decision(self) -> None:
        session = _make_cc_session()
        from spec4.agentifier.agentifier import run as agentifier_run

        list(agentifier_run("yes", session, _LLM_CONFIG))

        decisions = session.get("agentifier_cross_cutting_decisions") or {}
        assert "provider_strategy" in decisions

    def test_confirming_all_topics_sets_cc_done(self) -> None:
        session = _make_cc_session()
        from spec4.agentifier.agentifier import run as agentifier_run

        for _ in _CC_TOPICS:
            list(agentifier_run("yes", session, _LLM_CONFIG))

        assert session.get("agentifier_cross_cutting_done") is True

    def test_revision_does_not_advance_index(self) -> None:
        session = _make_cc_session()
        from spec4.agentifier.agentifier import run as agentifier_run

        cc_revised = {"provider_strategy": {"recommendation": "revised", "rationale": "new", "cited_patterns": []}}
        cc_text = "```json\n" + json.dumps(cc_revised) + "\n```"
        with patch(
            "spec4.agentifier.agentifier._extract_cross_cutting_analysis",
            return_value=cc_revised,
        ):
            with patch("litellm.acompletion", new=_make_streaming_mock(cc_text.split())):
                list(agentifier_run("add opentelemetry", session, _LLM_CONFIG))

        assert session["agentifier_cross_cutting_index"] == 0

    def test_replay_on_none_input(self) -> None:
        session = _make_cc_session()
        from spec4.agentifier.agentifier import run as agentifier_run

        chunks = list(agentifier_run(None, session, _LLM_CONFIG))
        assert "".join(chunks) != ""

    def test_skip_prompt_versioning_records_empty_and_advances(self) -> None:
        session = _make_cc_session()
        session["agentifier_cross_cutting_topics"] = ["prompt_versioning"]
        session["agentifier_cross_cutting_analysis"] = {
            "prompt_versioning": {
                "recommendation": "r", "rationale": "x", "cited_patterns": [],
            }
        }
        session["agentifier_cross_cutting_index"] = 0
        from spec4.agentifier.agentifier import run as agentifier_run

        list(agentifier_run("skip", session, _LLM_CONFIG))

        decisions = session.get("agentifier_cross_cutting_decisions") or {}
        assert decisions.get("prompt_versioning") == {}
        assert session.get("agentifier_cross_cutting_done") is True

    def test_skip_not_honored_for_required_topic(self) -> None:
        session = _make_cc_session()  # topics = (provider_strategy, prompt_versioning)
        from spec4.agentifier.agentifier import run as agentifier_run

        revised = {
            "provider_strategy": {
                "recommendation": "rev", "rationale": "x", "cited_patterns": [],
            }
        }
        cc_text = "```json\n" + json.dumps(revised) + "\n```"
        with patch(
            "spec4.agentifier.agentifier._extract_cross_cutting_analysis",
            return_value=revised,
        ):
            with patch("litellm.acompletion", new=_make_streaming_mock(cc_text.split())):
                list(agentifier_run("skip", session, _LLM_CONFIG))

        # "skip" on a required topic is treated as a revision, not an advance.
        assert session["agentifier_cross_cutting_index"] == 0

    def test_no_warranted_topics_skips_cross_cutting(self) -> None:
        session = _make_cc_session()
        session["ai_features"]["ai_features"] = [
            {"id": "d", "name": "d", "tier": "deterministic", "purpose": "p",
             "phase_priority": "mvp"},
        ]
        session["agentifier_cross_cutting_topics"] = []
        session["agentifier_cross_cutting_analysis"] = None
        from spec4.agentifier.agentifier import run as agentifier_run

        list(agentifier_run("yes", session, _LLM_CONFIG))

        assert session.get("agentifier_cross_cutting_done") is True
        assert (session.get("agentifier_cross_cutting_decisions") or {}) == {}


# ---------------------------------------------------------------------------
# Full pipeline integration: Spec → Cross-cutting → Priority → Complete
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """End-to-end: spec phase → cross-cutting → priority tagging → STATE_AGENTIFIER_COMPLETE."""

    def _make_full_session(self) -> dict[str, Any]:
        from spec4.session import _default_session

        session = _default_session()
        session["working_dir"] = "/tmp/spec4-full-pipeline"
        session["llm_config"] = _LLM_CONFIG
        session["active_agent"] = "agentifier"
        session["vision_statement"] = {"vision_statement": {"name": "TestApp"}}
        session["ai_catalog"] = {
            "ai_catalog": [
                {
                    "name": "feature_x",
                    "scope": "feature",
                    "rough_description": "Test feature",
                    "tier_recommendation": "single_call",
                    "tier_decision": "single_call",
                    "tier_decision_rationale": "",
                }
            ]
        }
        session["agentifier_catalog_done"] = True
        session["agentifier_spec_index"] = 0
        session["agentifier_spec_results"] = []
        return session

    @staticmethod
    def _spec_words() -> list[str]:
        return ("```json\n" + json.dumps(_SAMPLE_SPEC_JSON) + "\n```").split()

    def test_full_pipeline_reaches_complete_state(self) -> None:
        session = self._make_full_session()
        from spec4.agentifier.agentifier import run as agentifier_run
        from spec4.app_constants import STATE_AGENTIFIER_COMPLETE

        with patch("litellm.acompletion", new=_make_streaming_mock(self._spec_words())):
            with patch(
                "spec4.agentifier.agentifier._extract_cross_cutting_analysis",
                return_value=_CC_ANALYSIS,
            ):
                list(agentifier_run("yes", session, _LLM_CONFIG))  # draft feature_x

        # Confirm spec → triggers cross-cutting (analyst already mocked via _extract)
        with patch(
            "spec4.agentifier.agentifier._extract_cross_cutting_analysis",
            return_value=_CC_ANALYSIS,
        ):
            with patch("litellm.acompletion", new=_make_streaming_mock(self._spec_words())):
                list(agentifier_run("yes", session, _LLM_CONFIG))  # confirm spec → cc

        assert session.get("agentifier_spec_done") is True

        # Confirm all 7 cross-cutting topics
        for _ in _CC_TOPICS:
            list(agentifier_run("yes", session, _LLM_CONFIG))

        assert session.get("agentifier_cross_cutting_done") is True

        # Confirm phase priority for feature_x
        list(agentifier_run("yes", session, _LLM_CONFIG))

        assert session.get("agentifier_state") == STATE_AGENTIFIER_COMPLETE
        assert session.get("agentifier_priority_done") is True

    def test_final_ai_features_has_cross_cutting_block(self) -> None:
        session = self._make_full_session()
        from spec4.agentifier.agentifier import run as agentifier_run

        with patch("litellm.acompletion", new=_make_streaming_mock(self._spec_words())):
            with patch(
                "spec4.agentifier.agentifier._extract_cross_cutting_analysis",
                return_value=_CC_ANALYSIS,
            ):
                list(agentifier_run("yes", session, _LLM_CONFIG))  # draft

        with patch(
            "spec4.agentifier.agentifier._extract_cross_cutting_analysis",
            return_value=_CC_ANALYSIS,
        ):
            with patch("litellm.acompletion", new=_make_streaming_mock(self._spec_words())):
                list(agentifier_run("yes", session, _LLM_CONFIG))  # confirm → cc

        for _ in _CC_TOPICS:
            list(agentifier_run("yes", session, _LLM_CONFIG))

        list(agentifier_run("yes", session, _LLM_CONFIG))  # priority confirm

        ai_features = session.get("ai_features") or {}
        cross_cutting = ai_features.get("cross_cutting") or {}
        assert len(cross_cutting) == len(_CC_TOPICS)
        for t in _CC_TOPICS:
            assert t in cross_cutting
