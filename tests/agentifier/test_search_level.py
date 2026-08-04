"""Tests for Scout parsing, breadth-panel helpers, and orchestrator breadth."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from spec4.agentifier.scout import (
    Candidate,
    _parse_candidates,
)
from spec4.agentifier.agentifier import (
    _breadth_candidates,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LLM_CONFIG = {"model": "gpt-4o-mini", "api_key": "sk-test"}

_SAMPLE_VISION: dict[str, Any] = {
    "vision_statement": {"name": "ShelfLife", "features": ["search", "discovery"]}
}


def _make_candidates(n: int) -> list[Candidate]:
    return [
        Candidate(
            name=f"feature_{i}",
            linked_vision_features=[],
            scope="feature",
            rough_description=f"Feature {i}",
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# _parse_candidates preserves input order (new assertion per spec)
# ---------------------------------------------------------------------------


class TestParseCandidatesPreservesOrder:
    def test_order_matches_llm_array_order(self) -> None:
        names = ["alpha", "beta", "gamma", "delta"]
        data = json.dumps([
            {"name": n, "linked_vision_features": [], "scope": "feature",
             "rough_description": f"desc {n}", "linked_existing_workflow": ""}
            for n in names
        ])
        candidates, _ = _parse_candidates(data)
        assert [c.name for c in candidates] == names

    def test_reversed_array_preserved_reversed(self) -> None:
        names = ["z_last", "m_middle", "a_first"]
        data = json.dumps([
            {"name": n, "linked_vision_features": [], "scope": "feature",
             "rough_description": "", "linked_existing_workflow": ""}
            for n in names
        ])
        candidates, _ = _parse_candidates(data)
        assert [c.name for c in candidates] == names

    def test_single_item_order_preserved(self) -> None:
        data = json.dumps([{"name": "only_one", "linked_vision_features": [],
                            "scope": "feature", "rough_description": "", "linked_existing_workflow": ""}])
        candidates, _ = _parse_candidates(data)
        assert candidates[0].name == "only_one"


# ---------------------------------------------------------------------------
# Scout system prompt — ordering
# ---------------------------------------------------------------------------


class TestScoutSystemPromptOrdering:
    def test_ranking_instruction_removed_from_scout_prompt(self) -> None:
        from spec4.agentifier.scout import SCOUT_SYSTEM_PROMPT
        # Ordering is not Scout's job — must not be in the prompt.
        assert "priority order" not in SCOUT_SYSTEM_PROMPT.lower()
        assert "Return candidates in priority order" not in SCOUT_SYSTEM_PROMPT

    def test_scout_prompt_says_any_order_and_drops_ranker(self) -> None:
        from spec4.agentifier.scout import SCOUT_SYSTEM_PROMPT
        # Ranker is gone; Scout should just return candidates in any order.
        assert "any order" in SCOUT_SYSTEM_PROMPT.lower()
        assert "ranker" not in SCOUT_SYSTEM_PROMPT.lower()

    def test_prompt_still_contains_divergent_mandate(self) -> None:
        from spec4.agentifier.scout import SCOUT_SYSTEM_PROMPT
        assert "DIVERGENT" in SCOUT_SYSTEM_PROMPT or "divergent" in SCOUT_SYSTEM_PROMPT.lower()


# ---------------------------------------------------------------------------
# Orchestrator breadth sub-state (integration)
# ---------------------------------------------------------------------------


def _make_mock_scout(n: int) -> Any:
    from spec4.agentifier.scout import ScoutOutput
    candidates = _make_candidates(n)
    return patch(
        "spec4.agentifier.agentifier._call_scout",
        return_value=ScoutOutput(candidates=candidates),
    )


def _make_mock_composer() -> Any:
    from spec4.agentifier.composer import ComposerOutput
    def _noop(candidates: Any, vision: Any, llm_config: Any) -> Any:
        return ComposerOutput(candidates=candidates)
    return patch(
        "spec4.agentifier.agentifier._call_composer",
        side_effect=_noop,
    )


def _make_mock_linker() -> Any:
    # The Linker draws once between Scout and Composer; mock it at the helper
    # level (like Scout/Composer/Analyst) so the deterministic path to the panel
    # makes no real model call. Empty overlay = no edges (a flat pool).
    from spec4.agentifier.linker import LinkerOutcome, LinkerOutput
    return patch(
        "spec4.agentifier.agentifier._call_linker",
        return_value=LinkerOutput(overlay={}, outcome=LinkerOutcome.EMPTY),
    )


def _make_mock_analyst(n: int) -> Any:
    from spec4.agentifier.tier_analyst import TierAnalystOutput
    analysis = TierAnalystOutput(
        recommended_tier="single_call",
        rationale="Simple call.",
        risks_of_going_higher=[],
        risks_of_going_lower=[],
        borderline=False,
        borderline_seams=[],
        compared_to_next_tier_down="",
    )
    return patch(
        "spec4.agentifier.agentifier._call_tier_analyst",
        return_value=analysis,
    )


def _mock_litellm_stream(text: str) -> Any:
    from unittest.mock import MagicMock as _MM
    chunk = _MM()
    chunk.choices[0].delta.content = text
    chunk.choices[0].delta.tool_calls = None
    chunk.choices[0].finish_reason = None
    stop = _MM()
    stop.choices[0].delta.content = ""
    stop.choices[0].delta.tool_calls = None
    stop.choices[0].finish_reason = "stop"
    return patch("spec4.llm.litellm.completion", return_value=iter([chunk, stop]))


def _make_session_for_breadth() -> dict[str, Any]:
    from spec4.session import _default_session
    session = _default_session()
    session["vision_statement"] = _SAMPLE_VISION
    session["llm_config"] = _LLM_CONFIG
    session["active_agent"] = "agentifier"
    return session


class TestOrchestratorBreadthSubState:
    def test_large_pool_shows_breadth_panel_not_llm(self) -> None:
        """With a multi-candidate pool, fresh start yields breadth intro, no LLM call."""
        session = _make_session_for_breadth()

        with _make_mock_scout(10), _make_mock_composer(), _make_mock_linker(), \
                _make_mock_analyst(10), \
                patch("spec4.llm.litellm.completion") as mock_llm:
            from spec4.agentifier.agentifier import run as agentifier_run
            output = "".join(agentifier_run(None, session, _LLM_CONFIG))

        mock_llm.assert_not_called()
        assert session.get("agentifier_breadth_chosen") is False
        assert session.get("agentifier_scout_pool") is not None
        assert len(session["agentifier_scout_pool"]) == 10
        assert session.get("agentifier_breadth_groups") is not None
        assert "features to include" in output.lower()

    def test_small_pool_shows_breadth_panel_too(self) -> None:
        """With a small pool (3 candidates) the breadth panel shows as well: the pool
        is cached, no candidates are analysed yet, and no LLM call is made
        (previously the small pool skipped the panel and auto-included every
        candidate)."""
        session = _make_session_for_breadth()

        with _make_mock_scout(3), _make_mock_composer(), _make_mock_linker(), \
                _make_mock_analyst(3), \
                patch("spec4.llm.litellm.completion") as mock_llm:
            from spec4.agentifier.agentifier import run as agentifier_run
            output = "".join(agentifier_run(None, session, _LLM_CONFIG))

        mock_llm.assert_not_called()
        assert session.get("agentifier_breadth_chosen") is False
        assert session.get("agentifier_scout_pool") is not None
        assert len(session["agentifier_scout_pool"]) == 3
        assert session.get("agentifier_candidates") is None
        assert "features to include" in output.lower()

    def test_breadth_selection_honored_and_calls_llm(self) -> None:
        """After breadth panel, submitting a selection calls TierAnalyst on selected."""
        session = _make_session_for_breadth()
        pool_dicts = [
            {"name": f"f{i}", "linked_vision_features": [], "scope": "feature",
             "rough_description": f"desc {i}", "linked_existing_workflow": ""}
            for i in range(20)
        ]
        session["agentifier_scout_pool"] = pool_dicts
        session["agentifier_breadth_chosen"] = False
        session["agentifier_breadth_intro"] = "Select features"
        session["agentifier_breadth_selection"] = ["f0", "f5", "f10"]

        with _make_mock_analyst(3), _mock_litellm_stream("Welcome!"):
            from spec4.agentifier.agentifier import run as agentifier_run
            list(agentifier_run("Selected 3 features: f0, f5, f10", session, _LLM_CONFIG))

        assert session.get("agentifier_breadth_chosen") is True
        assert len(session["agentifier_candidates"]) == 3
        names = [c["name"] for c in session["agentifier_candidates"]]
        assert names == ["f0", "f5", "f10"]

    def test_breadth_non_contiguous_selection_honored(self) -> None:
        """Selecting non-adjacent candidates by name is honored exactly."""
        session = _make_session_for_breadth()
        session["agentifier_scout_pool"] = [
            {"name": f"f{i}", "linked_vision_features": [], "scope": "feature",
             "rough_description": f"desc {i}", "linked_existing_workflow": ""}
            for i in range(10)
        ]
        session["agentifier_breadth_chosen"] = False
        session["agentifier_breadth_selection"] = ["f1", "f7"]

        with _make_mock_analyst(2), _mock_litellm_stream("Hi!"):
            from spec4.agentifier.agentifier import run as agentifier_run
            list(agentifier_run("Selected 2", session, _LLM_CONFIG))

        names = [c["name"] for c in session["agentifier_candidates"]]
        assert names == ["f1", "f7"]

    def test_breadth_selection_populates_rejected(self) -> None:
        """Unselected candidates appear in explicitly_rejected (no band tag)."""
        session = _make_session_for_breadth()
        pool_dicts = [
            {"name": f"f{i}", "linked_vision_features": [], "scope": "feature",
             "rough_description": f"desc {i}", "linked_existing_workflow": ""}
            for i in range(10)
        ]
        session["agentifier_scout_pool"] = pool_dicts
        session["agentifier_breadth_chosen"] = False
        session["agentifier_breadth_selection"] = ["f0"]

        with _make_mock_analyst(1), _mock_litellm_stream("Hi!"):
            from spec4.agentifier.agentifier import run as agentifier_run
            list(agentifier_run("Selected 1", session, _LLM_CONFIG))

        rejected = session.get("agentifier_explicitly_rejected") or []
        assert len(rejected) == 9
        rejected_names = {r["name"] for r in rejected}
        assert "f0" not in rejected_names
        for r in rejected:
            assert r["reason"] == "deselected_by_user"
            assert "band" not in r

    def test_zero_selection_marks_complete_with_empty_features(self) -> None:
        """Selecting nothing marks agentifier complete with empty ai_features."""
        session = _make_session_for_breadth()
        session["agentifier_scout_pool"] = [
            {"name": f"f{i}", "linked_vision_features": [], "scope": "feature",
             "rough_description": "", "linked_existing_workflow": ""}
            for i in range(5)
        ]
        session["agentifier_breadth_chosen"] = False
        session["agentifier_breadth_selection"] = []

        with patch("spec4.agentifier.agentifier._call_tier_analyst") as mock_ta, \
                patch("spec4.llm.litellm.completion") as mock_llm:
            from spec4.agentifier.agentifier import run as agentifier_run
            list(agentifier_run("Selected no features.", session, _LLM_CONFIG))

        mock_ta.assert_not_called()
        mock_llm.assert_not_called()
        assert session.get("agentifier_breadth_chosen") is True
        ai_features = session.get("ai_features") or {}
        assert ai_features.get("ai_features") == []

    def test_zero_selection_populates_explicitly_rejected(self) -> None:
        """Selecting nothing lists all candidates in explicitly_rejected."""
        session = _make_session_for_breadth()
        session["agentifier_scout_pool"] = [
            {"name": f"f{i}", "linked_vision_features": [], "scope": "feature",
             "rough_description": "", "linked_existing_workflow": ""}
            for i in range(5)
        ]
        session["agentifier_breadth_chosen"] = False
        session["agentifier_breadth_selection"] = []

        with patch("spec4.agentifier.agentifier._call_tier_analyst"), \
                patch("spec4.llm.litellm.completion"):
            from spec4.agentifier.agentifier import run as agentifier_run
            list(agentifier_run("Selected no features.", session, _LLM_CONFIG))

        rejected = session.get("agentifier_explicitly_rejected") or []
        assert len(rejected) == 5
        for r in rejected:
            assert r["reason"] == "deselected_by_user"

    def test_replay_pending_breadth_intro_on_none_input(self) -> None:
        """If breadth selection is pending and user_input=None, intro is replayed."""
        session = _make_session_for_breadth()
        session["agentifier_scout_pool"] = [
            {"name": f"f{i}", "linked_vision_features": [], "scope": "feature",
             "rough_description": "", "linked_existing_workflow": ""}
            for i in range(10)
        ]
        session["agentifier_breadth_chosen"] = False
        session["agentifier_breadth_intro"] = "Breadth intro text"

        with patch("spec4.llm.litellm.completion") as mock_llm:
            from spec4.agentifier.agentifier import run as agentifier_run
            output = "".join(agentifier_run(None, session, _LLM_CONFIG))

        mock_llm.assert_not_called()
        assert "Breadth intro text" in output

    def test_tier_analyst_not_called_until_breadth_answered(self) -> None:
        """TierAnalyst is NOT called during the Scout/breadth-intro turn."""
        session = _make_session_for_breadth()

        with _make_mock_scout(10), _make_mock_composer(), _make_mock_linker(), \
                patch("spec4.agentifier.agentifier._call_tier_analyst") as mock_ta:
            from spec4.agentifier.agentifier import run as agentifier_run
            list(agentifier_run(None, session, _LLM_CONFIG))

        mock_ta.assert_not_called()

    def test_scout_not_called_on_breadth_selection_turn(self) -> None:
        """Scout is NOT called again when user submits breadth selection."""
        session = _make_session_for_breadth()
        session["agentifier_scout_pool"] = [
            {"name": f"f{i}", "linked_vision_features": [], "scope": "feature",
             "rough_description": "", "linked_existing_workflow": ""}
            for i in range(10)
        ]
        session["agentifier_breadth_chosen"] = False
        session["agentifier_breadth_selection"] = ["f0", "f1", "f2"]

        with patch("spec4.agentifier.agentifier._call_scout") as mock_scout, \
                _make_mock_analyst(3), _mock_litellm_stream("Hi!"):
            from spec4.agentifier.agentifier import run as agentifier_run
            list(agentifier_run("Selected 3", session, _LLM_CONFIG))

        mock_scout.assert_not_called()

    def test_display_override_set_to_breadth_intro(self) -> None:
        """On the Scout turn, _display_override = breadth intro (clears progress)."""
        session = _make_session_for_breadth()

        with _make_mock_scout(10), _make_mock_composer(), _make_mock_linker():
            from spec4.agentifier.agentifier import run as agentifier_run
            list(agentifier_run(None, session, _LLM_CONFIG))

        override = session.get("_display_override")
        assert override is not None
        assert override == session.get("agentifier_breadth_intro")


# ---------------------------------------------------------------------------
# _breadth_candidates
# ---------------------------------------------------------------------------


class TestBreadthCandidates:
    def test_flattens_pool_in_order(self) -> None:
        pool = _make_candidates(5)
        result = _breadth_candidates(pool)
        assert [i["name"] for i in result] == [c.name for c in pool]

    def test_item_shape(self) -> None:
        pool = _make_candidates(3)
        for item in _breadth_candidates(pool):
            assert "name" in item
            assert "description" in item

    def test_empty_pool(self) -> None:
        assert _breadth_candidates([]) == []

    def test_all_candidates_present(self) -> None:
        pool = _make_candidates(38)
        result = _breadth_candidates(pool)
        assert len(result) == len(pool)
        assert {i["name"] for i in result} == {c.name for c in pool}


# ---------------------------------------------------------------------------
# _finalize_specs — explicitly_rejected sourced from session
# ---------------------------------------------------------------------------


_CROSS_CUTTING_TOPICS_NAMES = (
    "observability", "prompt_versioning", "feedback_loop", "safety_policy",
    "provider_strategy", "eval_cadence", "tool_protocol_strategy",
)


class TestFinalizeSpecsExplicitlyRejected:
    """Verify explicitly_rejected is sourced from session, not hardcoded []."""

    def _run_finalize(self, rejected_list: list | None) -> dict:
        """Invoke _finalize_specs with a minimal session and return ai_features."""
        import json as _json
        from unittest.mock import patch
        from spec4.agentifier.agentifier import _finalize_specs
        from spec4.session import _default_session

        session = _default_session()
        session["agentifier_messages"] = []
        session["agentifier_compositions"] = []
        session["ai_catalog"] = {"ai_catalog": []}
        session["agentifier_candidates"] = []
        session["agentifier_analyses"] = []
        session["agentifier_spec_results"] = []
        if rejected_list is not None:
            session["agentifier_explicitly_rejected"] = rejected_list
        session["llm_config"] = _LLM_CONFIG

        _full = {
            t: {"recommendation": "x", "rationale": "y", "cited_patterns": []}
            for t in _CROSS_CUTTING_TOPICS_NAMES
        }

        async def _fake_stream(*a: Any, **kw: Any) -> Any:
            async def _gen() -> Any:
                yield "```json\n" + _json.dumps(_full) + "\n```"
            return _gen()

        with patch("spec4.agentifier.cross_cutting_analyst.acomplete", new=_fake_stream):
            list(_finalize_specs(session, _LLM_CONFIG))
        return session.get("ai_features") or {}

    def test_rejected_list_propagated_to_artifact(self) -> None:
        rejected_entry = {
            "name": "feat_b",
            "rough_description": "desc b",
            "reason": "deselected_by_user",
        }
        ai_features = self._run_finalize([rejected_entry])
        assert ai_features.get("explicitly_rejected") == [rejected_entry]

    def test_none_session_key_yields_empty_list(self) -> None:
        ai_features = self._run_finalize(None)
        assert ai_features.get("explicitly_rejected") == []