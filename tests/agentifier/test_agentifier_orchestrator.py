"""Tests for the Agentifier orchestrator agent."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from unittest.mock import MagicMock, patch

from spec4.agentifier import agentifier
from spec4.agentifier.scout import Candidate, ScoutOutcome, ScoutOutput
from spec4.agentifier.tier_analyst import TierAnalystOutput
from spec4.app_constants import STATE_AGENTIFIER_COMPLETE, STATE_IN_PROGRESS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LLM_CONFIG = {"model": "gpt-4o-mini", "api_key": "sk-test"}

_SAMPLE_VISION: dict[str, Any] = {
    "vision_statement": {
        "name": "TestApp",
        "vision": {"purpose": "A test application."},
    }
}

_CANDIDATE_A = Candidate(
    name="smart_search",
    linked_vision_features=["search"],
    scope="feature",
    rough_description="Semantic search over product catalog.",
)
_CANDIDATE_B = Candidate(
    name="review_classifier",
    linked_vision_features=["reviews"],
    scope="sub_feature",
    rough_description="Classify review sentiment.",
)

_ANALYSIS_A = TierAnalystOutput(
    recommended_tier="embeddings",
    rationale="Semantic similarity search fits embeddings tier.",
    risks_of_going_higher=["Unnecessary LLM cost."],
    risks_of_going_lower=["Misses synonyms and paraphrases."],
    borderline=False,
    borderline_seams=[],
    compared_to_next_tier_down=(
        "Deterministic keyword search would miss natural-language queries."
    ),
)
_ANALYSIS_B = TierAnalystOutput(
    recommended_tier="single_call",
    rationale="One-shot classification of a bounded input.",
    risks_of_going_higher=["Over-engineering for simple classification."],
    risks_of_going_lower=["Rule-based approach can't handle nuanced sentiment."],
    borderline=True,
    borderline_seams=["if review text > 4000 tokens, consider rag for context"],
    compared_to_next_tier_down=(
        "Embeddings classifier loses nuance that short prose captures well."
    ),
)

_BORDERLINE_ANALYSIS = TierAnalystOutput(
    recommended_tier="single_call",
    rationale="One call handles the bounded extraction task.",
    risks_of_going_higher=["Unnecessary complexity."],
    risks_of_going_lower=["Deterministic approach misses edge cases."],
    borderline=True,
    borderline_seams=["if input length > 5000 tokens, escalate to rag"],
    compared_to_next_tier_down=(
        "Embeddings would lose the generation capability needed here."
    ),
)


def make_session(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "phase": "chat",
        "active_agent": "agentifier",
        "working_dir": None,
        "vision_statement": _SAMPLE_VISION,
        "code_review": None,
        "agentifier_state": STATE_IN_PROGRESS,
        "agentifier_messages": [],
        "agentifier_candidates": None,
        "agentifier_analyses": None,
        "ai_catalog": None,
        "agentifier_stale_acknowledged": {},
        "agentifier_artifact_msg_count": None,
        "tavily_api_key": None,
        "llm_config": _LLM_CONFIG,
    }
    defaults.update(overrides)
    return defaults


def collect(gen: Iterable[str]) -> str:
    return "".join(gen)


def drive_panel(session: dict[str, Any], names: list[str] | None = None) -> str:
    """Drive a fresh start through the breadth panel.

    Every non-empty pool now shows the breadth panel, so a single ``run(None)``
    only surfaces candidates and waits. This helper runs that turn, selects
    ``names`` (every surfaced candidate if None), then runs the breadth-selection
    turn — as a developer choosing features would — so candidates, analyses, and
    the seed message are produced. Call it inside the test's mock context.
    """
    out = collect(agentifier.run(None, session, _LLM_CONFIG))
    pool = session.get("agentifier_scout_pool") or []
    session["agentifier_breadth_selection"] = (
        [c["name"] for c in pool] if names is None else list(names)
    )
    out += collect(agentifier.run("select", session, _LLM_CONFIG))
    return out


def make_stream_chunk(content: str, finish_reason: str | None = None) -> MagicMock:
    chunk = MagicMock()
    chunk.choices[0].delta.content = content
    chunk.choices[0].delta.tool_calls = None
    chunk.choices[0].finish_reason = finish_reason
    return chunk


def mock_litellm_stream(text: str) -> Any:
    chunks = [make_stream_chunk(c) for c in text]
    chunks.append(make_stream_chunk("", finish_reason="stop"))
    return patch(
        "spec4.llm.litellm.completion", return_value=iter(chunks)
    )


# ---------------------------------------------------------------------------
# Fresh start — sub-agent dispatch
# ---------------------------------------------------------------------------


class TestFreshStart:
    def _mock_sub_agents(
        self,
        candidates: list[Candidate] | None = None,
        analyses: list[TierAnalystOutput] | None = None,
    ) -> tuple[Any, Any]:
        if candidates is None:
            candidates = [_CANDIDATE_A]
        if analyses is None:
            analyses = [_ANALYSIS_A]
        mock_scout = patch(
            "spec4.agentifier.agentifier._call_scout",
            return_value=ScoutOutput(candidates=candidates),
        )
        mock_analyst = patch(
            "spec4.agentifier.agentifier._call_tier_analyst",
            return_value=analyses[0],
        )
        return mock_scout, mock_analyst

    def test_calls_scout_on_fresh_start(self) -> None:
        session = make_session()
        mock_scout, mock_analyst = self._mock_sub_agents()
        with mock_scout as ms, mock_analyst, mock_litellm_stream("Hello!"):
            collect(agentifier.run(None, session, _LLM_CONFIG))
        ms.assert_called_once()

    def test_passes_vision_to_scout(self) -> None:
        session = make_session()
        mock_scout, mock_analyst = self._mock_sub_agents()
        with mock_scout as ms, mock_analyst, mock_litellm_stream("Hello!"):
            collect(agentifier.run(None, session, _LLM_CONFIG))
        call_args = ms.call_args
        assert call_args[0][0] == _SAMPLE_VISION

    def test_passes_code_review_to_scout(self) -> None:
        code_review = {"is_software_project": True}
        session = make_session(code_review=code_review)
        mock_scout, mock_analyst = self._mock_sub_agents()
        with mock_scout as ms, mock_analyst, mock_litellm_stream("Hello!"):
            collect(agentifier.run(None, session, _LLM_CONFIG))
        call_args = ms.call_args
        assert call_args[0][1] == code_review

    def test_calls_tier_analyst_for_each_candidate(self) -> None:
        session = make_session()
        candidates = [_CANDIDATE_A, _CANDIDATE_B]
        analyses = [_ANALYSIS_A, _ANALYSIS_B]
        with patch(
            "spec4.agentifier.agentifier._call_scout",
            return_value=ScoutOutput(candidates=candidates),
        ), patch(
            "spec4.agentifier.agentifier._call_tier_analyst",
            side_effect=analyses,
        ) as mock_analyst, mock_litellm_stream("Hello!"):
            drive_panel(session)
        assert mock_analyst.call_count == 2

    def test_stores_candidates_in_session(self) -> None:
        session = make_session()
        mock_scout, mock_analyst = self._mock_sub_agents()
        with mock_scout, mock_analyst, mock_litellm_stream("Hello!"):
            drive_panel(session)
        assert session["agentifier_candidates"] is not None
        assert len(session["agentifier_candidates"]) == 1
        assert session["agentifier_candidates"][0]["name"] == "smart_search"

    def test_stores_analyses_in_session(self) -> None:
        session = make_session()
        mock_scout, mock_analyst = self._mock_sub_agents()
        with mock_scout, mock_analyst, mock_litellm_stream("Hello!"):
            drive_panel(session)
        assert session["agentifier_analyses"] is not None
        assert session["agentifier_analyses"][0]["recommended_tier"] == "embeddings"

    def test_seed_message_contains_candidate_name(self) -> None:
        session = make_session()
        mock_scout, mock_analyst = self._mock_sub_agents()
        with mock_scout, mock_analyst, mock_litellm_stream("Hello!"):
            drive_panel(session)
        msgs = session["agentifier_messages"]
        first_user = next(m for m in msgs if m["role"] == "user")
        assert "smart_search" in first_user["content"]

    def test_seed_message_contains_recommended_tier(self) -> None:
        session = make_session()
        mock_scout, mock_analyst = self._mock_sub_agents()
        with mock_scout, mock_analyst, mock_litellm_stream("Hello!"):
            drive_panel(session)
        msgs = session["agentifier_messages"]
        first_user = next(m for m in msgs if m["role"] == "user")
        assert "embeddings" in first_user["content"]

    def test_seed_message_surfaces_borderline_seams(self) -> None:
        session = make_session()
        with patch(
            "spec4.agentifier.agentifier._call_scout",
            return_value=ScoutOutput(candidates=[_CANDIDATE_A]),
        ), patch(
            "spec4.agentifier.agentifier._call_tier_analyst",
            return_value=_BORDERLINE_ANALYSIS,
        ), mock_litellm_stream("Hello!"):
            drive_panel(session)
        msgs = session["agentifier_messages"]
        first_user = next(m for m in msgs if m["role"] == "user")
        assert "escalate to rag" in first_user["content"]

    def test_seed_message_includes_compared_to_next_tier_down(self) -> None:
        session = make_session()
        mock_scout, mock_analyst = self._mock_sub_agents()
        with mock_scout, mock_analyst, mock_litellm_stream("Hello!"):
            drive_panel(session)
        msgs = session["agentifier_messages"]
        first_user = next(m for m in msgs if m["role"] == "user")
        assert "Deterministic keyword search would miss" in first_user["content"]

    def test_no_vision_returns_error_message_without_llm_call(self) -> None:
        session = make_session(vision_statement=None)
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(agentifier.run(None, session, _LLM_CONFIG))
        mock_llm.assert_not_called()
        assert "brainstormer" in output.lower() or "vision" in output.lower()

    def test_empty_candidates_returns_message_without_llm_call(self) -> None:
        session = make_session()
        with patch(
            "spec4.agentifier.agentifier._call_scout",
            return_value=ScoutOutput(candidates=[]),
        ), patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(agentifier.run(None, session, _LLM_CONFIG))
        mock_llm.assert_not_called()
        assert output != ""

    def test_unreadable_scout_output_asks_to_retry_not_deterministic(self) -> None:
        # A soft parse failure must surface as a retry, NOT be reported as a
        # deterministic-core vision.
        session = make_session()
        with patch(
            "spec4.agentifier.agentifier._call_scout",
            return_value=ScoutOutput(
                candidates=[], outcome=ScoutOutcome.UNREADABLE
            ),
        ), patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(agentifier.run(None, session, _LLM_CONFIG))
        mock_llm.assert_not_called()
        assert "try again" in output.lower()
        assert "deterministic" not in output.lower()


# ---------------------------------------------------------------------------
# Re-entry (prior conversation exists)
# ---------------------------------------------------------------------------


class TestReentry:
    def test_replays_last_assistant_message_on_reentry(self) -> None:
        prior_reply = "Here is candidate 1: smart_search…"
        session = make_session(
            agentifier_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": prior_reply},
            ]
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(agentifier.run(None, session, _LLM_CONFIG))
        mock_llm.assert_not_called()
        assert output == prior_reply

    def test_does_not_call_scout_on_reentry(self) -> None:
        session = make_session(
            agentifier_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "prior response"},
            ]
        )
        with patch(
            "spec4.agentifier.agentifier._call_scout"
        ) as mock_scout, patch("spec4.llm.litellm.completion"):
            collect(agentifier.run(None, session, _LLM_CONFIG))
        mock_scout.assert_not_called()


# ---------------------------------------------------------------------------
# Orphan-trailing-user recovery
# ---------------------------------------------------------------------------


class TestOrphanRecovery:
    def test_cleans_orphan_trailing_user_and_re_runs_sub_agents(self) -> None:
        """If the LLM crashed after the seed was appended (leaving a trailing
        user message), the orchestrator should clear it and re-use the stored
        candidates without calling Scout again."""
        session = make_session(
            agentifier_messages=[{"role": "user", "content": "orphan seed"}],
            agentifier_candidates=[
                {
                    "name": "smart_search",
                    "linked_vision_features": ["search"],
                    "scope": "feature",
                    "rough_description": "Search.",
                }
            ],
            agentifier_analyses=[
                {
                    "recommended_tier": "embeddings",
                    "rationale": "Good fit.",
                    "risks_of_going_higher": [],
                    "risks_of_going_lower": [],
                    "borderline": False,
                    "borderline_seams": [],
                    "compared_to_next_tier_down": "Keyword search misses synonyms.",
                }
            ],
        )
        with patch(
            "spec4.agentifier.agentifier._call_scout"
        ) as mock_scout, mock_litellm_stream("Recovery response"):
            collect(agentifier.run(None, session, _LLM_CONFIG))
        mock_scout.assert_not_called()

    def test_user_reply_on_empty_msgs_re_seeds_and_calls_llm(self) -> None:
        """If an orphan-clean left msgs empty and user_input was provided,
        the orchestrator re-seeds from session candidates and calls LLM."""
        session = make_session(
            agentifier_messages=[{"role": "user", "content": "orphan"}],
            agentifier_candidates=[
                {
                    "name": "smart_search",
                    "linked_vision_features": [],
                    "scope": "feature",
                    "rough_description": "Search.",
                }
            ],
            agentifier_analyses=[
                {
                    "recommended_tier": "embeddings",
                    "rationale": "Good fit.",
                    "risks_of_going_higher": [],
                    "risks_of_going_lower": [],
                    "borderline": False,
                    "borderline_seams": [],
                    "compared_to_next_tier_down": "Keyword misses synonyms.",
                }
            ],
        )
        with patch(
            "spec4.agentifier.agentifier._call_scout"
        ) as mock_scout, mock_litellm_stream("Re-seed response"):
            collect(agentifier.run(None, session, _LLM_CONFIG))
        mock_scout.assert_not_called()


# ---------------------------------------------------------------------------
# Conversation and catalog extraction
# ---------------------------------------------------------------------------


class TestConversation:
    def test_user_input_appended_to_messages(self) -> None:
        session = make_session(
            agentifier_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "first response"},
            ]
        )
        with mock_litellm_stream("Second response"):
            collect(agentifier.run("I choose option 1", session, _LLM_CONFIG))
        msgs = session["agentifier_messages"]
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert any("I choose option 1" in m["content"] for m in user_msgs)

    def test_llm_response_appended_to_messages(self) -> None:
        session = make_session(
            agentifier_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "first response"},
            ]
        )
        with mock_litellm_stream("Great choice! Moving on."):
            collect(agentifier.run("yes", session, _LLM_CONFIG))
        msgs = session["agentifier_messages"]
        last_assistant = next(
            m["content"] for m in reversed(msgs) if m["role"] == "assistant"
        )
        assert "Great choice!" in last_assistant

    def test_catalog_json_sets_catalog_done(self) -> None:
        # Phase 4: extracting the catalog JSON transitions to spec-drafting phase
        # (agentifier_catalog_done=True), not directly to STATE_AGENTIFIER_COMPLETE.
        # STATE_AGENTIFIER_COMPLETE is only set after all per-feature specs are drafted.
        catalog_json = (
            '```json\n{"ai_catalog": [{"name": "smart_search", "scope": "feature",'
            ' "rough_description": "Search.", "tier_recommendation": "embeddings",'
            ' "tier_decision": "embeddings", "tier_decision_rationale": ""}]}\n```'
        )
        session = make_session(
            agentifier_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "First recommendation"},
            ]
        )
        with mock_litellm_stream(catalog_json):
            collect(agentifier.run("yes, finalize it", session, _LLM_CONFIG))
        assert session["agentifier_catalog_done"] is True
        # spec index reset ready for Phase 2
        assert session["agentifier_spec_index"] == 0

    def test_catalog_json_saved_to_session(self) -> None:
        catalog_json = (
            '```json\n{"ai_catalog": [{"name": "smart_search", "scope": "feature",'
            ' "rough_description": "Search.", "tier_recommendation": "embeddings",'
            ' "tier_decision": "embeddings", "tier_decision_rationale": ""}]}\n```'
        )
        session = make_session(
            agentifier_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "First recommendation"},
            ]
        )
        with mock_litellm_stream(catalog_json):
            collect(agentifier.run("yes", session, _LLM_CONFIG))
        assert session["ai_catalog"] is not None
        assert "ai_catalog" in session["ai_catalog"]

    def test_non_catalog_response_stays_in_progress(self) -> None:
        session = make_session(
            agentifier_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "first recommendation"},
            ]
        )
        with mock_litellm_stream("What tier do you prefer?"):
            collect(agentifier.run("I prefer option 2", session, _LLM_CONFIG))
        assert session.get("agentifier_state") != STATE_AGENTIFIER_COMPLETE
        assert session.get("ai_catalog") is None

    def test_catalog_display_override_is_set(self) -> None:
        catalog_json = (
            '```json\n{"ai_catalog": [{"name": "smart_search", "scope": "feature",'
            ' "rough_description": "Search.", "tier_recommendation": "embeddings",'
            ' "tier_decision": "embeddings", "tier_decision_rationale": ""}]}\n```'
        )
        session = make_session(
            agentifier_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "first recommendation"},
            ]
        )
        with mock_litellm_stream(catalog_json):
            collect(agentifier.run("yes", session, _LLM_CONFIG))
        assert session.get("_display_override") is not None
        assert "AI Integration Catalog" in session["_display_override"]

    def test_catalog_display_includes_tier_decision(self) -> None:
        catalog_json = (
            '```json\n{"ai_catalog": [{"name": "smart_search", "scope": "feature",'
            ' "rough_description": "Search.", "tier_recommendation": "embeddings",'
            ' "tier_decision": "rag",'
            ' "tier_decision_rationale": "We need grounding."}]}\n```'
        )
        session = make_session(
            agentifier_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "first recommendation"},
            ]
        )
        with mock_litellm_stream(catalog_json):
            collect(agentifier.run("yes", session, _LLM_CONFIG))
        display = session["_display_override"]
        assert "rag" in display
        assert "(mismatch)" in display  # the marker, now a word (phase 7)

    def test_catalog_done_sets_spec_index_to_zero(self) -> None:
        # Phase 4: after catalog extraction, spec_index is reset to 0 so the
        # spec-drafting phase starts at the first feature.
        catalog_json = (
            '```json\n{"ai_catalog": [{"name": "s", "scope": "feature",'
            ' "rough_description": "S.", "tier_recommendation": "embeddings",'
            ' "tier_decision": "embeddings", "tier_decision_rationale": ""}]}\n```'
        )
        session = make_session(
            agentifier_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "rec"},
            ]
        )
        with mock_litellm_stream(catalog_json):
            collect(agentifier.run("yes", session, _LLM_CONFIG))
        assert session["agentifier_catalog_done"] is True
        assert session["agentifier_spec_index"] == 0
        assert session["agentifier_spec_results"] == []


# ---------------------------------------------------------------------------
# Override recording (tier_decision ≠ tier_recommendation)
# ---------------------------------------------------------------------------


class TestOverrideRecording:
    def test_catalog_records_user_decision_when_it_differs_from_recommendation(
        self,
    ) -> None:
        catalog_json = (
            '```json\n{"ai_catalog": [{"name": "smart_search", "scope": "feature",'
            ' "rough_description": "Search.", "tier_recommendation": "embeddings",'
            ' "tier_decision": "rag",'
            ' "tier_decision_rationale": "We need grounding."}]}\n```'
        )
        session = make_session(
            agentifier_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "first recommendation"},
            ]
        )
        with mock_litellm_stream(catalog_json):
            collect(agentifier.run("yes", session, _LLM_CONFIG))
        catalog = session["ai_catalog"]["ai_catalog"]
        entry = catalog[0]
        assert entry["tier_decision"] == "rag"
        assert entry["tier_recommendation"] == "embeddings"
        assert entry["tier_decision_rationale"] == "We need grounding."

    def test_catalog_empty_rationale_when_decision_matches_recommendation(self) -> None:
        catalog_json = (
            '```json\n{"ai_catalog": [{"name": "smart_search", "scope": "feature",'
            ' "rough_description": "Search.", "tier_recommendation": "embeddings",'
            ' "tier_decision": "embeddings", "tier_decision_rationale": ""}]}\n```'
        )
        session = make_session(
            agentifier_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "first recommendation"},
            ]
        )
        with mock_litellm_stream(catalog_json):
            collect(agentifier.run("yes", session, _LLM_CONFIG))
        catalog = session["ai_catalog"]["ai_catalog"]
        assert catalog[0]["tier_decision_rationale"] == ""


# ---------------------------------------------------------------------------
# _build_seed_message
# ---------------------------------------------------------------------------


class TestBuildSeedMessage:
    def test_includes_all_candidate_names(self) -> None:
        candidates = [_CANDIDATE_A, _CANDIDATE_B]
        analyses = [_ANALYSIS_A, _ANALYSIS_B]
        msg = agentifier._build_seed_message(candidates, analyses)
        assert "smart_search" in msg
        assert "review_classifier" in msg

    def test_includes_compared_to_next_tier_down(self) -> None:
        msg = agentifier._build_seed_message([_CANDIDATE_A], [_ANALYSIS_A])
        assert "Deterministic keyword search would miss" in msg

    def test_includes_borderline_seams_when_borderline(self) -> None:
        msg = agentifier._build_seed_message([_CANDIDATE_A], [_ANALYSIS_B])
        assert "4000 tokens" in msg

    def test_does_not_include_borderline_marker_when_false(self) -> None:
        msg = agentifier._build_seed_message([_CANDIDATE_A], [_ANALYSIS_A])
        assert "Borderline: NO" in msg

    def test_includes_system_note_header(self) -> None:
        msg = agentifier._build_seed_message([_CANDIDATE_A], [_ANALYSIS_A])
        assert "Spec4 system note" in msg

    def test_candidate_count_in_header(self) -> None:
        candidates = [_CANDIDATE_A, _CANDIDATE_B]
        analyses = [_ANALYSIS_A, _ANALYSIS_B]
        msg = agentifier._build_seed_message(candidates, analyses)
        assert "2 AI opportunity candidate" in msg

    def test_seed_includes_existing_workflow_line(self) -> None:
        brownfield = Candidate(
            name="smart_search",
            linked_vision_features=["search"],
            scope="feature",
            rough_description="LLM-powered search.",
            linked_existing_workflow="keyword-based SQL LIKE search in views.py",
        )
        msg = agentifier._build_seed_message([brownfield], [_ANALYSIS_A])
        assert "Existing implementation this would replace: keyword-based SQL LIKE search in views.py" in msg
        # Greenfield candidates (default "") never emit the line.
        msg_green = agentifier._build_seed_message([_CANDIDATE_A], [_ANALYSIS_A])
        assert "Existing implementation this would replace" not in msg_green

    def test_orchestrator_system_prompt_has_linked_existing_workflow(self) -> None:
        # The catalog exemplar carries the field so brownfield provenance stays
        # visible in the developer-facing catalog (downstream never trusts the
        # LLM echo — it joins from candidates).
        assert "linked_existing_workflow" in agentifier.ORCHESTRATOR_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# _build_seed_message — graph placement (composed_under / requires context)
# ---------------------------------------------------------------------------


class TestGraphPlacement:
    @staticmethod
    def _an(tier: str = "single_call") -> TierAnalystOutput:
        return TierAnalystOutput(
            recommended_tier=tier,
            rationale="(rationale)",
            risks_of_going_higher=[],
            risks_of_going_lower=[],
            borderline=False,
            borderline_seams=[],
            compared_to_next_tier_down="",
        )

    def _graph(self) -> tuple[list[Candidate], list[TierAnalystOutput]]:
        coord = Candidate(
            name="orchestrator",
            linked_vision_features=["f"],
            scope="feature",
            rough_description="Coordinates the pipeline.",
        )
        m1 = Candidate(
            name="member_one",
            linked_vision_features=["f"],
            scope="sub_feature",
            rough_description="First step.",
            composed_under="orchestrator",
        )
        m2 = Candidate(
            name="member_two",
            linked_vision_features=["f"],
            scope="sub_feature",
            rough_description="Second step.",
            composed_under="orchestrator",
            requires=["member_one"],
        )
        cands = [coord, m1, m2]
        return cands, [self._an() for _ in cands]

    def test_coordinator_lists_its_members(self) -> None:
        cands, analyses = self._graph()
        msg = agentifier._build_seed_message(cands, analyses)
        assert "Coordinates 2 sub-features: `member_one`, `member_two`." in msg

    def test_member_names_its_coordinator(self) -> None:
        cands, analyses = self._graph()
        msg = agentifier._build_seed_message(cands, analyses)
        assert "A sub-feature of `orchestrator`." in msg

    def test_requires_and_reverse_requires(self) -> None:
        cands, analyses = self._graph()
        msg = agentifier._build_seed_message(cands, analyses)
        assert "Uses the output of: `member_one`." in msg
        assert "Its output feeds: `member_two`." in msg

    def test_references_absent_from_reviewed_set_are_trimmed(self) -> None:
        orphan = Candidate(
            name="orphan",
            linked_vision_features=["f"],
            scope="sub_feature",
            rough_description="Points at a dropped coordinator and producer.",
            composed_under="ghost_coordinator",
            requires=["ghost_producer"],
        )
        msg = agentifier._build_seed_message([orphan], [self._an()])
        assert "ghost_coordinator" not in msg
        assert "ghost_producer" not in msg
        assert "A sub-feature of" not in msg
        assert "Uses the output of" not in msg

    def test_single_member_coordinator_is_singular(self) -> None:
        coord = Candidate(
            name="solo_coord",
            linked_vision_features=["f"],
            scope="feature",
            rough_description="Has one member.",
        )
        member = Candidate(
            name="lone_member",
            linked_vision_features=["f"],
            scope="sub_feature",
            rough_description="Only member.",
            composed_under="solo_coord",
        )
        msg = agentifier._build_seed_message([coord, member], [self._an(), self._an()])
        assert "Coordinates 1 sub-feature: `lone_member`." in msg


# ---------------------------------------------------------------------------
# _analyses_to_dicts — embeds candidate name for join-by-name downstream
# ---------------------------------------------------------------------------


class TestAnalysesToDicts:
    def test_each_dict_contains_name(self) -> None:
        result = agentifier._analyses_to_dicts(
            [_ANALYSIS_A, _ANALYSIS_B], [_CANDIDATE_A, _CANDIDATE_B]
        )
        assert result[0]["name"] == "smart_search"
        assert result[1]["name"] == "review_classifier"

    def test_name_matches_parallel_candidate(self) -> None:
        result = agentifier._analyses_to_dicts([_ANALYSIS_A], [_CANDIDATE_A])
        assert result[0]["name"] == _CANDIDATE_A.name

    def test_existing_analysis_fields_preserved(self) -> None:
        result = agentifier._analyses_to_dicts([_ANALYSIS_A], [_CANDIDATE_A])
        a = result[0]
        assert a["recommended_tier"] == "embeddings"
        assert a["rationale"] == "Semantic similarity search fits embeddings tier."
        assert a["borderline"] is False
        assert a["risks_of_going_higher"] == ["Unnecessary LLM cost."]


# ---------------------------------------------------------------------------
# _build_ai_features — tier_analysis persistence and tier_decision_rationale guard
# ---------------------------------------------------------------------------


class TestBuildAiFeatures:
    def _entry(self, name: str, **overrides: Any) -> dict[str, Any]:
        return {
            "name": name,
            "scope": "feature",
            "tier_decision": "embeddings",
            "tier_recommendation": "embeddings",
            "tier_decision_rationale": "",
            "rough_description": f"{name} description.",
            **overrides,
        }

    def _candidate_dict(self, name: str) -> dict[str, Any]:
        return {
            "name": name,
            "linked_vision_features": ["f1"],
            "scope": "feature",
            "rough_description": f"{name} description.",
            "linked_existing_workflow": "",
        }

    def _analysis_dict(self, name: str, tier: str = "embeddings") -> dict[str, Any]:
        return {
            "name": name,
            "recommended_tier": tier,
            "rationale": f"{name} rationale.",
            "compared_to_next_tier_down": "Keyword search misses synonyms.",
            "borderline": False,
            "borderline_seams": [],
            "risks_of_going_higher": ["Cost."],
            "risks_of_going_lower": ["Quality loss."],
        }

    def test_matched_feature_gets_populated_tier_analysis(self) -> None:
        entries = [self._entry("smart_search")]
        candidates = [self._candidate_dict("smart_search")]
        analyses = [self._analysis_dict("smart_search")]
        features = agentifier._build_ai_features(entries, [], candidates, analyses)
        ta = features[0]["tier_analysis"]
        assert ta["recommended_tier"] == "embeddings"
        assert ta["rationale"] == "smart_search rationale."
        assert ta["compared_to_next_tier_down"] == "Keyword search misses synonyms."
        assert ta["borderline"] is False
        assert ta["risks_of_going_higher"] == ["Cost."]
        assert ta["risks_of_going_lower"] == ["Quality loss."]

    def test_unmatched_feature_gets_empty_tier_analysis(self) -> None:
        entries = [self._entry("unmatched_feature")]
        candidates = [self._candidate_dict("unmatched_feature")]
        # No analyses_data → no match possible
        features = agentifier._build_ai_features(entries, [], candidates, [])
        assert features[0]["tier_analysis"] == {}

    def test_tier_decision_rationale_unchanged(self) -> None:
        # Adding tier_analysis must not touch tier_decision_rationale.
        entries = [self._entry("smart_search", tier_decision_rationale="User override.")]
        candidates = [self._candidate_dict("smart_search")]
        analyses = [self._analysis_dict("smart_search")]
        features = agentifier._build_ai_features(entries, [], candidates, analyses)
        assert features[0]["tier_decision_rationale"] == "User override."

    def test_analyses_data_none_treated_as_empty(self) -> None:
        entries = [self._entry("smart_search")]
        candidates = [self._candidate_dict("smart_search")]
        features = agentifier._build_ai_features(entries, [], candidates, None)
        assert features[0]["tier_analysis"] == {}

    def test_spec_update_does_not_clobber_tier_analysis(self) -> None:
        # Simulate a spec dict that (hypothetically) contains a tier_analysis key —
        # the feature.update(spec) line runs before we assign tier_analysis, so our
        # assignment always wins.  This test guards that ordering.
        entries = [self._entry("smart_search")]
        candidates = [self._candidate_dict("smart_search")]
        analyses = [self._analysis_dict("smart_search")]
        # Inject a spec result that contains a conflicting tier_analysis value.
        spec_with_conflict = [{"tier_analysis": "STALE"}]
        features = agentifier._build_ai_features(
            entries, spec_with_conflict, candidates, analyses
        )
        ta = features[0]["tier_analysis"]
        assert isinstance(ta, dict), "tier_analysis was overwritten by spec update"
        assert "rationale" in ta, "tier_analysis content missing after spec update"

    def test_multiple_features_each_matched_independently(self) -> None:
        entries = [self._entry("alpha"), self._entry("beta")]
        candidates = [self._candidate_dict("alpha"), self._candidate_dict("beta")]
        analyses = [
            self._analysis_dict("alpha", tier="single_call"),
            self._analysis_dict("beta", tier="rag"),
        ]
        features = agentifier._build_ai_features(entries, [], candidates, analyses)
        assert features[0]["tier_analysis"]["recommended_tier"] == "single_call"
        assert features[1]["tier_analysis"]["recommended_tier"] == "rag"

    def test_enriched_candidate_description_preferred_over_catalog_entry(self) -> None:
        # Candidate carries Composer-enriched text; catalog entry has plain text.
        entry = self._entry("barcode_lookup", **{"rough_description": "Plain catalog description."})
        candidate = {
            "name": "barcode_lookup",
            "linked_vision_features": ["inventory"],
            "scope": "feature",
            "rough_description": "ENRICHED: Plain catalog description. Enables nutrition lookup.",
            "linked_existing_workflow": "",
        }
        features = agentifier._build_ai_features([entry], [], [candidate])
        assert features[0]["rough_description"] == "ENRICHED: Plain catalog description. Enables nutrition lookup."

    def test_falls_back_to_catalog_entry_when_no_candidate_match(self) -> None:
        # Name not in candidates_by_name → catalog entry's rough_description used.
        entry = self._entry("orphan_feature", **{"rough_description": "Entry fallback text."})
        features = agentifier._build_ai_features([entry], [], [])
        assert features[0]["rough_description"] == "Entry fallback text."

    def test_rough_description_set_after_spec_update(self) -> None:
        # Spec drafter output that contains rough_description must not clobber the
        # enriched candidate value — because we assign after feature.update(spec).
        entry = self._entry("smart_search", **{"rough_description": "Plain."})
        candidate = {
            "name": "smart_search",
            "linked_vision_features": ["search"],
            "scope": "feature",
            "rough_description": "ENRICHED by composer.",
            "linked_existing_workflow": "",
        }
        spec_with_desc = [{"rough_description": "Spec rewrote this."}]
        features = agentifier._build_ai_features([entry], spec_with_desc, [candidate])
        assert features[0]["rough_description"] == "ENRICHED by composer."

    def test_tier_decision_rationale_not_changed_by_description_fix(self) -> None:
        entry = self._entry("smart_search", tier_decision_rationale="Override reason.")
        candidate = {
            "name": "smart_search",
            "linked_vision_features": [],
            "scope": "feature",
            "rough_description": "Enriched text.",
            "linked_existing_workflow": "",
        }
        features = agentifier._build_ai_features([entry], [], [candidate])
        assert features[0]["tier_decision_rationale"] == "Override reason."
        assert features[0]["rough_description"] == "Enriched text."

    def test_linked_existing_workflow_carried_into_features(self) -> None:
        entry = self._entry("smart_search")
        candidate = self._candidate_dict("smart_search")
        candidate["linked_existing_workflow"] = "regex classifier in views.py"
        features = agentifier._build_ai_features([entry], [], [candidate])
        assert features[0]["linked_existing_workflow"] == "regex classifier in views.py"
        # Unmatched entry degrades to "" rather than dropping the key.
        orphan = agentifier._build_ai_features([self._entry("orphan")], [], [])
        assert orphan[0]["linked_existing_workflow"] == ""

    def test_spec_echo_cannot_clobber_linked_existing_workflow(self) -> None:
        # The candidate is authoritative — assigned after feature.update(spec).
        entry = self._entry("smart_search")
        candidate = self._candidate_dict("smart_search")
        candidate["linked_existing_workflow"] = "regex classifier in views.py"
        spec_with_echo = [{"linked_existing_workflow": "HALLUCINATED"}]
        features = agentifier._build_ai_features([entry], spec_with_echo, [candidate])
        assert features[0]["linked_existing_workflow"] == "regex classifier in views.py"


# ---------------------------------------------------------------------------
# Approaches overview (shown once after Scout→Composer)
# ---------------------------------------------------------------------------


class TestApproachesOverview:
    def _candidate(self, name: str) -> Candidate:
        return Candidate(
            name=name,
            linked_vision_features=["f"],
            scope="feature",
            rough_description=f"{name} description.",
        )

    def test_small_pool_yields_overview(self) -> None:
        session = make_session()
        with patch(
            "spec4.agentifier.agentifier._call_scout",
            return_value=ScoutOutput(candidates=[_CANDIDATE_A]),
        ), patch(
            "spec4.agentifier.agentifier._call_tier_analyst",
            return_value=_ANALYSIS_A,
        ), mock_litellm_stream("Hello!"):
            output = collect(agentifier.run(None, session, _LLM_CONFIG))
        assert agentifier._APPROACHES_OVERVIEW in output

    def test_large_pool_prepends_overview_to_breadth_intro(self) -> None:
        session = make_session()
        candidates = [self._candidate(f"cand_{i}") for i in range(4)]
        with patch(
            "spec4.agentifier.agentifier._call_scout",
            return_value=ScoutOutput(candidates=candidates),
        ), mock_litellm_stream("Hello!"):
            output = collect(agentifier.run(None, session, _LLM_CONFIG))
        # Stored intro is replayed when the developer re-enters the breadth step,
        # so the overview must live inside it — and lead the streamed intro.
        assert (
            agentifier._APPROACHES_OVERVIEW in session["agentifier_breadth_intro"]
        )
        assert agentifier._APPROACHES_OVERVIEW in output

    def test_overview_uses_approaches_not_tier_wording(self) -> None:
        # User-facing copy says "approaches"; the word "tier" must not leak in.
        assert "approach" in agentifier._APPROACHES_OVERVIEW.lower()
        assert "tier" not in agentifier._APPROACHES_OVERVIEW.lower()

# ---------------------------------------------------------------------------
# D-AT-P3 — an unreadable catalog block
# ---------------------------------------------------------------------------


def _reply_sequence(*replies: str) -> tuple[Any, list[dict[str, Any]]]:
    """litellm.completion stand-in serving one reply per call.

    The last reply repeats for any further calls so a downstream helper making
    its own completion calls cannot exhaust it and turn a behavioural assertion
    into an IndexError.
    """
    seqs: list[list[MagicMock]] = []
    for text in replies:
        chunks = [make_stream_chunk(c) for c in text]
        chunks.append(make_stream_chunk("", finish_reason="stop"))
        seqs.append(chunks)
    calls: list[dict[str, Any]] = []

    def fake_completion(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return iter(seqs.pop(0) if len(seqs) > 1 else seqs[0])

    return fake_completion, calls


class TestUnparseableCatalog:
    """The D-SC-P3 fix applied to the Agentifier catalog phase.

    The symptom here differs from the other agents'. The catch-all display
    override at the end of the catalog phase falls back to the raw assistant
    text, so an unreadable catalog block used to land in the chat as a wall of
    broken JSON — with `agentifier_catalog_done` still False and no way forward.
    """

    _TRUNCATED = '```json\n{"ai_catalog": [{"name": "smart_sear'
    _VALID = (
        '```json\n{"ai_catalog": [{"name": "smart_search", "scope": "feature",'
        ' "rough_description": "Search.", "tier_recommendation": "embeddings",'
        ' "tier_decision": "embeddings", "tier_decision_rationale": ""}]}\n```'
    )

    def _session(self) -> dict[str, Any]:
        return make_session(
            agentifier_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "First recommendation"},
            ]
        )

    def _run(self, *replies: str) -> tuple[dict[str, Any], str, list[Any]]:
        session = self._session()
        fake_completion, calls = _reply_sequence(*replies)
        with patch(
            "spec4.llm.litellm.completion", side_effect=fake_completion
        ):
            output = collect(agentifier.run("yes, finalize it", session, _LLM_CONFIG))
        return session, output, calls

    def test_truncated_block_is_re_asked(self) -> None:
        session, _, calls = self._run(self._TRUNCATED, self._VALID)
        assert len(calls) == 2, "the unreadable catalog must trigger one re-ask"
        assert session["agentifier_catalog_done"] is True
        assert session["ai_catalog"] is not None

    def test_broken_json_never_reaches_the_screen(self) -> None:
        """The specific regression: the catch-all override used to display the
        raw reply, so the developer saw the wreckage."""
        session, _, _ = self._run(self._TRUNCATED, self._TRUNCATED)
        override = session.get("_display_override")
        assert override
        assert "ai_catalog" not in override
        assert "```json" not in override

    def test_turn_never_ends_silently(self) -> None:
        session, output, _ = self._run(self._TRUNCATED, self._TRUNCATED)
        assert output.strip(), "the turn yielded nothing visible"
        last = session["agentifier_messages"][-1]
        assert last["role"] == "assistant"
        assert last["content"] == session["_display_override"]

    def test_failed_reask_leaves_no_dead_end_user_turn(self) -> None:
        session, _, _ = self._run(self._TRUNCATED, self._TRUNCATED)
        assert not [
            m
            for m in session["agentifier_messages"]
            if m["role"] == "user" and "could not be read" in m["content"]
        ]

    def test_phase_is_not_advanced_when_both_attempts_fail(self) -> None:
        session, _, _ = self._run(self._TRUNCATED, self._TRUNCATED)
        assert session.get("agentifier_catalog_done") is not True
        assert session.get("ai_catalog") is None

    def test_ordinary_prose_reply_is_left_alone(self) -> None:
        session = self._session()
        with mock_litellm_stream("What tier do you prefer?") as llm:
            output = collect(agentifier.run("I prefer option 2", session, _LLM_CONFIG))
        assert llm.call_count == 1, "a prose reply must not trigger a re-ask"
        assert "What tier" in output
        assert session.get("ai_catalog") is None


class TestSeedMessageBrownfieldMode:
    """The orchestrator's opening note follows the developer's answer.

    Same regression as Scout's: `session.get("code_review") is not None` made
    the orchestrator open a greenfield conversation with "This is a BROWNFIELD
    project" and ask whether the developer was extending existing AI features.
    """

    def _seed(self, session: dict[str, Any]) -> str:
        from spec4.agentifier.agentifier import _build_seed_message
        from spec4 import project_manager

        return _build_seed_message(
            [],
            [],
            brownfield=project_manager.session_is_brownfield(session),
        )

    def test_greenfield_with_a_scan_says_nothing_about_brownfield(self) -> None:
        seed = self._seed(
            {"project_mode": "new", "code_review": {"summary": "scanned skeleton"}}
        )
        assert "BROWNFIELD" not in seed

    def test_existing_project_is_announced_as_brownfield(self) -> None:
        seed = self._seed({"project_mode": "existing", "code_review": {"summary": "x"}})
        assert "BROWNFIELD" in seed

    def test_brownfield_needs_no_scan_to_be_announced(self) -> None:
        seed = self._seed({"project_mode": "existing", "code_review": None})
        assert "BROWNFIELD" in seed
