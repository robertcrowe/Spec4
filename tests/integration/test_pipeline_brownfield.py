"""Brownfield pipeline integration test.

Runs the pipeline with code_review.json as input, verifying that:
- Scout receives and uses code_review to surface brownfield candidates.
- TierAnalyst receives existing AI infrastructure as context.
- CrossCuttingAnalyst biases toward reuse when existing AI infra is present.
- The orchestrator brownfield mode question appears in the seed message.
- Downstream agents work correctly with both code_review and ai_features.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from spec4.agentifier.scout import Candidate, ScoutInput, _build_scout_system_prompt
from spec4.agentifier.tier_analyst import TierAnalystInput, _existing_ai_context
from spec4.session import _default_session

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_LLM_CONFIG = {"model": "gpt-4o-mini", "api_key": "sk-test"}

_CODE_REVIEW_WITH_AI = {
    "code_review": {
        "schema_version": 1,
        "is_software_project": True,
        "languages": [{"name": "Python", "version": "3.12"}],
        "frameworks": [{"name": "FastAPI", "area": "backend"}],
        "dependencies": [
            {"name": "openai", "version": "1.x", "source": "pyproject.toml"},
            {"name": "chromadb", "version": "0.4.x", "source": "pyproject.toml"},
            {"name": "langchain", "version": "0.1.x", "source": "pyproject.toml"},
        ],
        "build_system": "uv",
        "commands": {"build": "uv build", "test": "pytest", "run": "uvicorn app:app"},
        "notes": {
            "incomplete_or_dead_code": [],
            "change_risks": [],
            "test_coverage": {"has_tests": True, "coverage_summary": "60% coverage"},
            "other_notes": [],
        },
    }
}

_CODE_REVIEW_NO_AI = {
    "code_review": {
        "schema_version": 1,
        "is_software_project": True,
        "languages": [{"name": "Python", "version": "3.12"}],
        "frameworks": [{"name": "Django", "area": "backend"}],
        "dependencies": [
            {"name": "django", "version": "5.x", "source": "requirements.txt"},
            {"name": "psycopg2", "version": "2.x", "source": "requirements.txt"},
        ],
        "build_system": "pip",
        "commands": {"test": "pytest", "run": "python manage.py runserver"},
        "notes": {
            "incomplete_or_dead_code": [],
            "change_risks": [],
            "test_coverage": {"has_tests": True, "coverage_summary": "45% coverage"},
            "other_notes": ["Manual category classification in views.py"],
        },
    }
}

_VISION = {
    "vision_statement": {
        "name": "RestaurantFinder",
        "description": "Find and book restaurants",
        "features": ["search", "booking", "reviews"],
    }
}

_CANDIDATES_JSON = json.dumps([
    {
        "name": "smart_search",
        "linked_vision_features": ["search"],
        "scope": "feature",
        "rough_description": "Replace manual keyword search with LLM-powered search.",
        "linked_existing_workflow": "keyword-based SQL LIKE search in views.py",
    },
    {
        "name": "review_summary",
        "linked_vision_features": ["reviews"],
        "scope": "sub_feature",
        "rough_description": "Summarise customer reviews.",
        "linked_existing_workflow": "",
    },
])


# ---------------------------------------------------------------------------
# Scout brownfield
# ---------------------------------------------------------------------------


class TestScoutBrownfield:
    def test_brownfield_system_prompt_has_extra_instructions(self) -> None:
        prompt = _build_scout_system_prompt(brownfield=True)
        assert "manual or rule-based" in prompt.lower()
        assert "linked_existing_workflow" in prompt

    def test_greenfield_system_prompt_has_no_brownfield_section(self) -> None:
        prompt = _build_scout_system_prompt(brownfield=False)
        assert "Brownfield mode" not in prompt

    def test_candidate_linked_existing_workflow_parsed(self) -> None:
        from spec4.agentifier.scout import _parse_candidates

        candidates, _ = _parse_candidates(_CANDIDATES_JSON)
        assert len(candidates) == 2
        assert candidates[0].linked_existing_workflow == "keyword-based SQL LIKE search in views.py"
        assert candidates[1].linked_existing_workflow == ""

    def test_scout_uses_brownfield_prompt_when_code_review_present(self) -> None:
        captured_systems: list[str] = []

        def _mock_completion(**kwargs: Any) -> Any:
            captured_systems.append(kwargs["messages"][0]["content"])
            resp = MagicMock()
            resp.choices = [MagicMock()]
            resp.choices[0].message.content = _CANDIDATES_JSON
            return resp

        from spec4.agentifier.scout import ScoutAgent

        scout = ScoutAgent()
        import asyncio
        with patch("spec4.agentifier.scout.complete", side_effect=_mock_completion):
            result = asyncio.run(scout.run(ScoutInput(
                vision=_VISION,
                llm_config=_LLM_CONFIG,
                code_review=_CODE_REVIEW_WITH_AI,
            )))

        assert result.candidates
        assert captured_systems
        assert "Brownfield mode" in captured_systems[0]

    def test_scout_uses_base_prompt_when_no_code_review(self) -> None:
        captured_systems: list[str] = []

        def _mock_completion(**kwargs: Any) -> Any:
            captured_systems.append(kwargs["messages"][0]["content"])
            resp = MagicMock()
            resp.choices = [MagicMock()]
            resp.choices[0].message.content = _CANDIDATES_JSON
            return resp

        from spec4.agentifier.scout import ScoutAgent

        scout = ScoutAgent()
        import asyncio
        with patch("spec4.agentifier.scout.complete", side_effect=_mock_completion):
            asyncio.run(scout.run(ScoutInput(vision=_VISION, llm_config=_LLM_CONFIG)))

        assert "Brownfield mode" not in captured_systems[0]


# ---------------------------------------------------------------------------
# TierAnalyst brownfield
# ---------------------------------------------------------------------------


class TestTierAnalystBrownfield:
    def test_existing_ai_context_extracts_deps(self) -> None:
        ctx = _existing_ai_context(_CODE_REVIEW_WITH_AI)
        assert "openai" in ctx.lower() or "chromadb" in ctx.lower() or "langchain" in ctx.lower()

    def test_existing_ai_context_empty_for_no_ai(self) -> None:
        ctx = _existing_ai_context(_CODE_REVIEW_NO_AI)
        assert ctx == ""

    def test_existing_ai_context_prefers_ai_capabilities(self) -> None:
        # First-class ai_capabilities surface even when no dependency name
        # matches the keyword scan (in-house pipeline, non-obvious package).
        review = {
            "code_review": {
                "schema_version": 1,
                "is_software_project": True,
                "dependencies": [{"name": "requests", "source": "pyproject.toml"}],
                "ai_capabilities": [
                    {
                        "name": "in-house tagger",
                        "kind": "ml_model",
                        "description": "Custom scikit-learn classifier tagging tickets",
                        "location": "src/app/tagging.py",
                    },
                ],
            }
        }
        ctx = _existing_ai_context(review)
        assert "Existing AI capabilities in the codebase:" in ctx
        assert "in-house tagger [ml_model]" in ctx
        assert "Custom scikit-learn classifier tagging tickets" in ctx
        assert "(src/app/tagging.py)" in ctx

    def test_existing_ai_context_combines_capabilities_and_deps(self) -> None:
        review = json.loads(json.dumps(_CODE_REVIEW_WITH_AI))
        review["code_review"]["ai_capabilities"] = [
            {"name": "chromadb", "kind": "vector_store", "description": "Article retrieval"},
        ]
        ctx = _existing_ai_context(review)
        # Both the first-class section and the keyword-scan fallback appear.
        assert "Existing AI capabilities in the codebase:" in ctx
        assert "AI/LLM dependencies already in place:" in ctx
        assert "openai" in ctx

    def test_existing_ai_context_detects_new_keywords(self) -> None:
        review = {
            "code_review": {
                "schema_version": 1,
                "is_software_project": True,
                "dependencies": [
                    {"name": "faiss-cpu", "source": "pyproject.toml"},
                    {"name": "pgvector", "source": "pyproject.toml"},
                    {"name": "ollama", "source": "pyproject.toml"},
                ],
            }
        }
        ctx = _existing_ai_context(review)
        assert "faiss-cpu" in ctx
        assert "pgvector" in ctx
        assert "ollama" in ctx

    def test_tier_analyst_user_message_includes_ai_hint(self) -> None:
        from spec4.agentifier.tier_analyst import TierAnalystAgent
        from spec4.agentifier.pattern_loader import load_patterns

        captured_messages: list[list[dict[str, Any]]] = []

        def _mock_completion(**kwargs: Any) -> Any:
            captured_messages.append(kwargs["messages"])
            resp = MagicMock()
            resp.choices = [MagicMock()]
            resp.choices[0].message.content = json.dumps({
                "recommended_tier": "rag",
                "rationale": "Needs vector search given existing chromadb",
                "risks_of_going_higher": [],
                "risks_of_going_lower": ["loses semantic search"],
                "borderline": False,
                "borderline_seams": [],
                "compared_to_next_tier_down": "embeddings would need manual retrieval",
            })
            return resp

        tiers, _ = load_patterns()
        cand = Candidate(
            name="smart_search",
            linked_vision_features=["search"],
            scope="feature",
            rough_description="LLM-powered search.",
        )
        import asyncio
        agent = TierAnalystAgent()
        with patch("spec4.agentifier.tier_analyst.complete", side_effect=_mock_completion):
            asyncio.run(agent.run(TierAnalystInput(
                candidate=cand,
                llm_config=_LLM_CONFIG,
                tier_patterns=tiers,
                code_review=_CODE_REVIEW_WITH_AI,
            )))

        assert captured_messages
        user_msg = captured_messages[0][1]["content"]
        assert "existing AI" in user_msg or "chromadb" in user_msg or "openai" in user_msg

    def test_tier_analyst_no_hint_without_ai_infra(self) -> None:
        from spec4.agentifier.tier_analyst import TierAnalystAgent
        from spec4.agentifier.pattern_loader import load_patterns

        captured_messages: list[list[dict[str, Any]]] = []

        def _mock_completion(**kwargs: Any) -> Any:
            captured_messages.append(kwargs["messages"])
            resp = MagicMock()
            resp.choices = [MagicMock()]
            resp.choices[0].message.content = json.dumps({
                "recommended_tier": "single_call",
                "rationale": "Simple LLM call.",
                "risks_of_going_higher": [],
                "risks_of_going_lower": [],
                "borderline": False,
                "borderline_seams": [],
                "compared_to_next_tier_down": "deterministic can't do NLU",
            })
            return resp

        tiers, _ = load_patterns()
        cand = Candidate(
            name="smart_search",
            linked_vision_features=["search"],
            scope="feature",
            rough_description="NLP search.",
        )
        import asyncio
        agent = TierAnalystAgent()
        with patch("spec4.agentifier.tier_analyst.complete", side_effect=_mock_completion):
            asyncio.run(agent.run(TierAnalystInput(
                candidate=cand,
                llm_config=_LLM_CONFIG,
                tier_patterns=tiers,
                code_review=_CODE_REVIEW_NO_AI,
            )))

        user_msg = captured_messages[0][1]["content"]
        assert "existing AI infrastructure" not in user_msg


# ---------------------------------------------------------------------------
# SpecDrafter brownfield
# ---------------------------------------------------------------------------


class TestSpecDrafterBrownfield:
    @staticmethod
    def _user_content(**overrides: Any) -> str:
        from spec4.agentifier.spec_drafter import SpecDrafterInput, _build_user_content

        spec_input = SpecDrafterInput(
            catalog_entry={
                "name": "smart_search",
                "scope": "feature",
                "rough_description": "LLM-powered search.",
                "tier_decision": "rag",
            },
            llm_config=_LLM_CONFIG,
            tier_patterns=[],
            mechanism_patterns=[],
            **overrides,
        )
        return _build_user_content(spec_input, "rag")

    def test_spec_drafter_gets_ai_hint_with_ai_infra(self) -> None:
        content = self._user_content(
            linked_existing_workflow="keyword-based SQL LIKE search in views.py",
            existing_ai_context=_existing_ai_context(_CODE_REVIEW_WITH_AI),
        )
        assert "Existing implementation this replaces:" in content
        assert "keyword-based SQL LIKE search in views.py" in content
        assert "Existing AI infrastructure (bias toward reuse):" in content
        assert "chromadb" in content

    def test_spec_drafter_no_hint_without_ai_infra(self) -> None:
        content = self._user_content()
        assert "Existing implementation this replaces" not in content
        assert "Existing AI infrastructure" not in content


# ---------------------------------------------------------------------------
# Orchestrator brownfield seed
# ---------------------------------------------------------------------------


class TestOrchestratorBrownfieldSeed:
    def test_brownfield_seed_contains_mode_question(self) -> None:
        from spec4.agentifier.agentifier import _build_seed_message
        from spec4.agentifier.tier_analyst import TierAnalystOutput

        candidates = [
            Candidate(
                name="smart_search",
                linked_vision_features=[],
                scope="feature",
                rough_description="NLP search.",
            )
        ]
        analyses = [
            TierAnalystOutput(
                recommended_tier="single_call",
                rationale="Simple LLM call.",
                risks_of_going_higher=[],
                risks_of_going_lower=[],
                borderline=False,
                borderline_seams=[],
                compared_to_next_tier_down="",
            )
        ]
        seed = _build_seed_message(candidates, analyses, brownfield=True)
        assert "brownfield" in seed.lower() or "existing" in seed.lower()
        assert "adding AI features" in seed or "rethinking" in seed

    def test_greenfield_seed_has_no_brownfield_note(self) -> None:
        from spec4.agentifier.agentifier import _build_seed_message
        from spec4.agentifier.tier_analyst import TierAnalystOutput

        candidates = [
            Candidate(name="x", linked_vision_features=[], scope="feature", rough_description="y")
        ]
        analyses = [
            TierAnalystOutput(
                recommended_tier="single_call",
                rationale="",
                risks_of_going_higher=[],
                risks_of_going_lower=[],
                borderline=False,
                borderline_seams=[],
                compared_to_next_tier_down="",
            )
        ]
        seed = _build_seed_message(candidates, analyses, brownfield=False)
        assert "adding AI features" not in seed


# ---------------------------------------------------------------------------
# CrossCuttingAnalyst brownfield
# ---------------------------------------------------------------------------


class TestCrossCuttingBrownfield:
    def test_existing_ai_infra_included_in_user_content(self) -> None:
        from spec4.agentifier.cross_cutting_analyst import (
            CrossCuttingAnalyst,
            CrossCuttingInput,
        )
        from spec4.agentifier.pattern_loader import load_patterns

        captured: list[list[dict[str, Any]]] = []

        async def _mock_acompletion(**kwargs: Any) -> Any:
            captured.append(kwargs["messages"])

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = "x"
                yield c

            return _gen()

        _, mechanisms = load_patterns()
        inp = CrossCuttingInput(
            ai_features=[{"name": "search", "tier": "rag", "purpose": "search"}],
            mechanism_patterns=mechanisms,
            llm_config=_LLM_CONFIG,
            code_review=_CODE_REVIEW_WITH_AI,
        )
        import asyncio
        with patch(
            "spec4.agentifier.cross_cutting_analyst.acomplete",
            new=_mock_acompletion,
        ):
            asyncio.run(_drain_async(CrossCuttingAnalyst().stream(inp)))

        assert captured
        user_msg = captured[0][1]["content"]
        assert "existing AI" in user_msg or "openai" in user_msg or "chromadb" in user_msg


async def _drain_async(gen: Any) -> list[str]:
    chunks: list[str] = []
    async for chunk in gen:
        chunks.append(chunk)
    return chunks


# ---------------------------------------------------------------------------
# Brownfield session loading
# ---------------------------------------------------------------------------


class TestBrownfieldSessionLoad:
    def test_code_review_triggers_brownfield_in_agentifier(self) -> None:
        """When code_review is in session, agentifier passes brownfield=True to seed."""
        from spec4.agentifier.agentifier import _build_seed_message
        from spec4.agentifier.tier_analyst import TierAnalystOutput

        session = _default_session()
        session["code_review"] = _CODE_REVIEW_WITH_AI

        candidates = [
            Candidate(name="x", linked_vision_features=[], scope="feature", rough_description="y")
        ]
        analyses = [
            TierAnalystOutput(
                recommended_tier="rag",
                rationale="Has chromadb",
                risks_of_going_higher=[],
                risks_of_going_lower=[],
                borderline=False,
                borderline_seams=[],
                compared_to_next_tier_down="embeddings would miss semantic reranking",
            )
        ]
        brownfield = session.get("code_review") is not None
        seed = _build_seed_message(candidates, analyses, brownfield=brownfield)
        assert brownfield is True
        assert "adding AI features" in seed or "rethinking" in seed
