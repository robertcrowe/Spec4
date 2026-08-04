"""Change B — relocated cross-cutting concerns.

observability / eval_cadence / feedback_loop / safety_policy are owned natively by
StackAdvisor (logging/observability tooling) and Deployer (runtime monitoring, eval
cadence, feedback, safety). The cross-cutting analyst no longer produces them, so the
AI-feature context readers must not surface them even if a stale artifact still carries
the keys.

provider_strategy remains in the StackAdvisor reader, which is where the provider
decision is still open. The Deployer reader no longer surfaces it (D-DE7a): by then
the stack's ratified ``providers`` block is authoritative (D-PH6 A'), and rendering
the catalog recommendation alongside it would give one decision two owners.
"""

from spec4.agents._utils import _ai_features_for_deployer, _ai_features_for_stack
from spec4.agents.deployer import SYSTEM_PROMPT as DEPLOYER_PROMPT
from spec4.agents.stack_advisor import SYSTEM_PROMPT as STACK_PROMPT

# A feature set whose cross_cutting block still carries the (now-relocated) keys,
# simulating a stale ai_features.json from before Change A.
_AI_FEATURES = {
    "ai_features": [
        {"name": "f", "tier": "rag", "purpose": "p", "mechanisms": []},
    ],
    "cross_cutting": {
        "provider_strategy": {
            "recommendation": "frontier capability tier",
            "rationale": "",
            "cited_patterns": [],
        },
        "observability": {
            "recommendation": "OBS_LEAK", "rationale": "", "cited_patterns": [],
        },
        "eval_cadence": {
            "recommendation": "EVAL_LEAK", "rationale": "", "cited_patterns": [],
        },
        "safety_policy": {
            "recommendation": "SAFETY_LEAK", "rationale": "", "cited_patterns": [],
        },
        "feedback_loop": {
            "recommendation": "FEEDBACK_LEAK", "rationale": "", "cited_patterns": [],
        },
    },
}

_RELOCATED_LEAKS = ("OBS_LEAK", "EVAL_LEAK", "SAFETY_LEAK", "FEEDBACK_LEAK")


class TestStackContextDropsRelocatedKeys:
    def test_provider_strategy_kept(self) -> None:
        out = _ai_features_for_stack(_AI_FEATURES)
        assert "Provider strategy" in out
        assert "frontier capability tier" in out

    def test_relocated_keys_not_surfaced(self) -> None:
        out = _ai_features_for_stack(_AI_FEATURES)
        for leak in _RELOCATED_LEAKS:
            assert leak not in out


class TestDeployerContextDropsRelocatedKeys:
    def test_catalog_provider_recommendation_not_surfaced(self) -> None:
        """Superseded by the stack's ratified providers (D-DE7a)."""
        out = _ai_features_for_deployer(_AI_FEATURES)
        assert "Provider strategy" not in out
        assert "frontier capability tier" not in out

    def test_relocated_keys_not_surfaced(self) -> None:
        out = _ai_features_for_deployer(_AI_FEATURES)
        for leak in _RELOCATED_LEAKS:
            assert leak not in out


class TestStackAdvisorOwnsObservability:
    def test_logging_observability_is_required_area(self) -> None:
        low = STACK_PROMPT.lower()
        assert "observability" in low
        assert "required functional area" in low

    def test_ai_aware_model_signals(self) -> None:
        low = STACK_PROMPT.lower()
        assert "token usage" in low
        assert "latency" in low


class TestDeployerOwnsEvalFeedbackSafety:
    def test_model_observability_covered(self) -> None:
        assert "model observability" in DEPLOYER_PROMPT.lower()

    def test_eval_feedback_safety_covered(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "evaluation cadence" in low
        assert "feedback loop" in low
        assert "guardrail" in low
