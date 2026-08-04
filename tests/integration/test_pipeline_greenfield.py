"""Greenfield pipeline integration test.

Runs the full pipeline from vision through to deployment plan with mocked LLM
calls, verifying that:
- Artifacts flow correctly between agents via session state.
- Downstream agents (StackAdvisor, Phaser, Deployer) consume ai_features when present.
- The full Agentifier flow (catalog → specs → cross-cutting → priority) completes.
- Backward compatibility: agents work without ai_features present.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from spec4.session import _default_session

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_LLM_CONFIG = {"model": "gpt-4o-mini", "api_key": "sk-test"}

_VISION = {
    "vision_statement": {
        "name": "QuickBite",
        "description": "AI-powered restaurant discovery app",
        "features": ["smart_search", "review_summary", "booking"],
        "audience": "urban diners",
    }
}

_CODE_REVIEW: dict[str, Any] = {}  # greenfield: no code review

_STACK = {
    "stack_spec": {
        "name": "QuickBite",
        "languages": ["Python", "TypeScript"],
        "deployment": {"platforms": ["Web app"], "hosting": "Cloud"},
        "libraries": {"backend": [{"name": "FastAPI", "purpose": "API framework"}]},
    }
}

_PHASE = {
    "phase_number": 1,
    "phase_title": "Steel Thread",
    "total_phases": 3,
    "summary": "Minimal end-to-end connectivity.",
    "tech_stack_spec": {"configurations": []},
    "instructions": ["Set up FastAPI", "Connect frontend"],
    "risk_assessment": [],
    "verification": "Run `make test` and confirm health-check passes.",
    "references": [],
}

_AI_CATALOG = {
    "ai_catalog": [
        {
            "name": "smart_search",
            "scope": "feature",
            "rough_description": "Natural language restaurant search.",
            "tier_recommendation": "single_call",
            "tier_decision": "single_call",
            "tier_decision_rationale": "",
        }
    ]
}

_AI_SPEC = {
    "purpose": "Enable natural language restaurant search.",
    "invocation": {"trigger": "user query", "mode": "synchronous"},
    "inputs": [{"name": "query", "type": "string", "description": "search text", "required": True}],
    "outputs": {"primary": "restaurant list", "format": "JSON array", "schema_notes": None},
    "decision_authority": "autonomous",
    "success_criteria": ["Returns relevant results"],
    "failure_modes": [],
    "escalation": "Return empty results",
    "eval_approach": {"offline": "golden set", "online": "CTR", "ground_truth": "human labels"},
    "budgets": {"cost_per_call": "$0.002", "p95_latency": "800ms"},
    "privacy_safety": ["No PII stored"],
    "phase_priority": "mvp",
    "mechanisms": [],
    "references": [],
}

_CC_ANALYSIS = {
    t: {"recommendation": f"recommendation for {t}", "rationale": "rationale", "cited_patterns": []}
    for t in [
        "provider_strategy", "tool_protocol_strategy", "prompt_versioning",
    ]
}


def _make_sync_mock(obj: Any) -> Any:
    """Return a mock litellm.completion response yielding obj as JSON."""
    text = json.dumps(obj) if not isinstance(obj, str) else obj
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = text
    return response


def _make_streaming_mock(obj: Any) -> Any:
    """Return a mock acompletion that yields obj JSON as word chunks."""
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


def _make_stream_turn_mock(text: str) -> Any:
    """Mock llm.stream_turn to yield chunks and append an assistant message."""
    words = text.split()

    def _stream_turn(system: Any, messages: list[Any], *args: Any, **kwargs: Any) -> Any:
        content = " ".join(words)
        messages.append({"role": "assistant", "content": content})
        return iter(words)

    return _stream_turn


# ---------------------------------------------------------------------------
# Test: session defaults include Agentifier fields
# ---------------------------------------------------------------------------


class TestGreenFieldSessionDefaults:
    def test_agentifier_fields_present(self) -> None:
        session = _default_session()
        assert "agentifier_spec_done" in session
        assert "agentifier_cross_cutting_done" in session
        assert "agentifier_priority_done" in session
        assert session["agentifier_cross_cutting_done"] is False
        assert session["agentifier_priority_done"] is False

    def test_ai_features_none_by_default(self) -> None:
        session = _default_session()
        assert session["ai_features"] is None


# ---------------------------------------------------------------------------
# Test: downstream agents work without ai_features (backward compatibility)
# ---------------------------------------------------------------------------


class TestDownstreamBackwardCompatibility:
    """Verify downstream agents do not break when ai_features is absent."""

    def _base_session(self) -> dict[str, Any]:
        session = _default_session()
        session["llm_config"] = _LLM_CONFIG
        session["vision_statement"] = _VISION
        session["stack_statement"] = _STACK
        return session

    def test_stack_advisor_no_ai_features(self) -> None:
        from spec4.agents.stack_advisor import run as stack_run
        from spec4.app_constants import STATE_STACK_COMPLETE

        session = self._base_session()
        stack_text = "```json\n" + json.dumps(_STACK) + "\n```"
        mock_stream = _make_stream_turn_mock(stack_text)
        with patch("spec4.agents.stack_advisor.llm.stream_turn", side_effect=mock_stream):
            list(stack_run(None, session, _LLM_CONFIG))
        # JSON output is suppressed in chat; state and artifact must still be set
        assert session["stack_advisor_state"] == STATE_STACK_COMPLETE

    def test_phaser_no_ai_features(self) -> None:
        from spec4.agents.phaser import run as phaser_run

        session = self._base_session()
        phase_text = "```json\n" + json.dumps(_PHASE) + "\n```"
        mock_stream = _make_stream_turn_mock(phase_text)
        with patch("spec4.agents.phaser.llm.stream_turn", side_effect=mock_stream):
            chunks = list(phaser_run(None, session, _LLM_CONFIG))
        assert len(chunks) > 0

    def test_deployer_no_ai_features(self) -> None:
        from spec4.agents.deployer import run as deployer_run

        session = self._base_session()
        session["phases"] = [_PHASE]
        session["_deployer_readme_optin_done"] = True
        mock_stream = _make_stream_turn_mock("Hello I am Deployer")
        with patch("spec4.agents.deployer.llm.stream_turn", side_effect=mock_stream):
            chunks = list(deployer_run(None, session, _LLM_CONFIG))
        assert len(chunks) > 0


# ---------------------------------------------------------------------------
# Test: downstream agents consume ai_features context
# ---------------------------------------------------------------------------


class TestDownstreamAiFeaturesConsumption:
    """Verify ai_features context is injected into downstream agent seeds."""

    def _session_with_ai_features(self) -> dict[str, Any]:
        session = _default_session()
        session["llm_config"] = _LLM_CONFIG
        session["vision_statement"] = _VISION
        session["stack_statement"] = _STACK
        session["ai_features"] = {
            "ai_features": [
                {
                    "id": "smart_search",
                    "name": "smart_search",
                    "tier": "rag",
                    "purpose": "Natural language restaurant search",
                    "phase_priority": "mvp",
                    "mechanisms": [{"name": "retrieval_reranking", "rationale": "improve relevance"}],
                }
            ],
            "cross_cutting": _CC_ANALYSIS,
            "explicitly_rejected": [],
            "references": [],
        }
        return session

    def test_stack_advisor_seed_contains_ai_features_note(self) -> None:
        from spec4.agents.stack_advisor import run as stack_run

        session = self._session_with_ai_features()
        captured_seeds: list[str] = []

        def _mock_stream(system: Any, messages: list[Any], *args: Any, **kwargs: Any) -> Any:
            captured_seeds.append(messages[0]["content"])
            messages.append({"role": "assistant", "content": "stack response"})
            return iter(["stack", "response"])

        with patch("spec4.agents.stack_advisor.llm.stream_turn", side_effect=_mock_stream):
            list(stack_run(None, session, _LLM_CONFIG))

        assert captured_seeds
        seed = captured_seeds[0]
        assert "rag" in seed or "AI features" in seed or "retrieval" in seed

    def test_phaser_seed_contains_phase_priority(self) -> None:
        from spec4.agents.phaser import run as phaser_run

        session = self._session_with_ai_features()
        captured_seeds: list[str] = []

        def _mock_stream(system: Any, messages: list[Any], *args: Any, **kwargs: Any) -> Any:
            captured_seeds.append(messages[0]["content"])
            phase_text = "```json\n" + json.dumps(_PHASE) + "\n```"
            messages.append({"role": "assistant", "content": phase_text})
            return iter(["phase", "text"])

        with patch("spec4.agents.phaser.llm.stream_turn", side_effect=_mock_stream):
            list(phaser_run(None, session, _LLM_CONFIG))

        assert captured_seeds
        seed = captured_seeds[0]
        assert "phase_priority" in seed or "mvp" in seed or "smart_search" in seed

    def test_deployer_seed_contains_ai_features_context(self) -> None:
        from spec4.agents.deployer import run as deployer_run

        session = self._session_with_ai_features()
        session["phases"] = [_PHASE]
        # Bypass the greenfield README opt-in gate (a standalone first turn) so the
        # opening builds the seed this call; the opt-in is covered by unit tests.
        session["_deployer_readme_optin_done"] = True
        captured_seeds: list[str] = []

        def _mock_stream(system: Any, messages: list[Any], *args: Any, **kwargs: Any) -> Any:
            captured_seeds.append(messages[0]["content"])
            messages.append({"role": "assistant", "content": "deployer response"})
            return iter(["deployer", "response"])

        with patch("spec4.agents.deployer.llm.stream_turn", side_effect=_mock_stream):
            list(deployer_run(None, session, _LLM_CONFIG))

        assert captured_seeds
        seed = captured_seeds[0]
        # Observability/eval/feedback/safety are now owned by Deployer's prompt steps;
        # the seed carries AI-feature deployment context (tiers, provider tier).
        assert "AI features spec" in seed or "AI feature tiers" in seed


# ---------------------------------------------------------------------------
# Test: Agentifier greenfield full flow
# ---------------------------------------------------------------------------


class TestAgentifierGreenfield:
    def _make_session(self) -> dict[str, Any]:
        session = _default_session()
        session["working_dir"] = "/tmp/spec4-integration-greenfield"
        session["llm_config"] = _LLM_CONFIG
        session["active_agent"] = "agentifier"
        session["vision_statement"] = _VISION
        session["ai_catalog"] = _AI_CATALOG
        session["agentifier_catalog_done"] = True
        session["agentifier_spec_index"] = 0
        session["agentifier_spec_results"] = []
        return session

    def test_spec_phase_populates_ai_features(self) -> None:
        from spec4.agentifier.agentifier import run as agentifier_run

        session = self._make_session()

        with patch("litellm.acompletion", new=_make_streaming_mock(_AI_SPEC)):
            with patch(
                "spec4.agentifier.agentifier._extract_cross_cutting_analysis",
                return_value=_CC_ANALYSIS,
            ):
                list(agentifier_run("yes", session, _LLM_CONFIG))  # draft
                list(agentifier_run("yes", session, _LLM_CONFIG))  # confirm → cross-cutting

        assert session.get("agentifier_spec_done") is True
        assert session["ai_features"] is not None
        features = session["ai_features"].get("ai_features", [])
        assert len(features) == 1
        assert features[0]["name"] == "smart_search"

    def test_full_agentifier_pipeline_completes(self) -> None:
        from spec4.agentifier.agentifier import run as agentifier_run
        from spec4.app_constants import STATE_AGENTIFIER_COMPLETE

        session = self._make_session()
        _cc_topics = (
            "provider_strategy", "prompt_versioning",
        )

        with patch("litellm.acompletion", new=_make_streaming_mock(_AI_SPEC)):
            with patch(
                "spec4.agentifier.agentifier._extract_cross_cutting_analysis",
                return_value=_CC_ANALYSIS,
            ):
                list(agentifier_run("yes", session, _LLM_CONFIG))  # draft
                list(agentifier_run("yes", session, _LLM_CONFIG))  # confirm → cross-cutting

        for _ in _cc_topics:
            list(agentifier_run("yes", session, _LLM_CONFIG))

        list(agentifier_run("yes", session, _LLM_CONFIG))  # priority confirm

        assert session.get("agentifier_state") == STATE_AGENTIFIER_COMPLETE
        ai_features = session["ai_features"]
        assert ai_features is not None
        assert len(ai_features.get("cross_cutting", {})) == 2

    def test_ai_features_json_schema_complete(self) -> None:
        from spec4.agentifier.agentifier import run as agentifier_run

        session = self._make_session()
        _cc_topics = (
            "provider_strategy", "prompt_versioning",
        )

        with patch("litellm.acompletion", new=_make_streaming_mock(_AI_SPEC)):
            with patch(
                "spec4.agentifier.agentifier._extract_cross_cutting_analysis",
                return_value=_CC_ANALYSIS,
            ):
                list(agentifier_run("yes", session, _LLM_CONFIG))
                list(agentifier_run("yes", session, _LLM_CONFIG))

        for _ in _cc_topics:
            list(agentifier_run("yes", session, _LLM_CONFIG))

        list(agentifier_run("yes", session, _LLM_CONFIG))

        af = session["ai_features"]
        assert "ai_features" in af
        assert "cross_cutting" in af
        assert "explicitly_rejected" in af
        assert "references" in af
        for f in af["ai_features"]:
            assert "id" in f
            assert "name" in f
            assert "tier" in f
