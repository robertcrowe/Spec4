"""Tests for Agentifier revision mode (pure logic + wiring, no live LLM).

Revision mode scopes a new round to the vision delta: already-built AI features
are carried forward silently, Scout is informed of the delta, and every feature
in the snapshot is stamped with a deterministic ``introduced_in_version``.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

from spec4.agentifier import agentifier
from spec4.agentifier.agentifier import (
    _build_seed_message,
    _merge_revision_snapshot,
    _removed_feature_heads_up,
    _revision_delta,
)
from spec4.agentifier.scout import Candidate
from spec4.agentifier.tier_analyst import TierAnalystOutput


def _collect(gen) -> str:
    return "".join(gen)


# ---------------------------------------------------------------------------
# _revision_delta
# ---------------------------------------------------------------------------


class TestRevisionDelta:
    def test_returns_last_history_entry(self) -> None:
        vision = {
            "vision_statement": {
                "name": "X",
                "revision_history": [
                    {"version": 1, "goal": "first"},
                    {"version": 2, "goal": "second"},
                ],
            }
        }
        assert _revision_delta(vision) == {"version": 2, "goal": "second"}

    def test_none_for_greenfield(self) -> None:
        assert _revision_delta({"vision_statement": {"name": "X"}}) is None

    def test_none_for_empty_history(self) -> None:
        assert _revision_delta({"vision_statement": {"revision_history": []}}) is None

    def test_none_for_non_dict_or_missing(self) -> None:
        assert _revision_delta(None) is None
        assert _revision_delta({}) is None
        assert _revision_delta({"vision_statement": None}) is None


# ---------------------------------------------------------------------------
# _merge_revision_snapshot
# ---------------------------------------------------------------------------


class TestMergeRevisionSnapshot:
    def test_carried_first_then_new(self) -> None:
        carried = [{"name": "built_a", "introduced_in_version": 0}]
        new = [{"name": "new_b"}]
        out = _merge_revision_snapshot(carried, new, current_version=1, prior_version=0)
        assert [f["name"] for f in out] == ["built_a", "new_b"]

    def test_new_features_stamped_with_current_version(self) -> None:
        out = _merge_revision_snapshot([], [{"name": "n"}], 3, 2)
        assert out[0]["introduced_in_version"] == 3

    def test_carried_keeps_existing_stamp(self) -> None:
        carried = [{"name": "old", "introduced_in_version": 1}]
        out = _merge_revision_snapshot(carried, [], current_version=2, prior_version=1)
        assert out[0]["introduced_in_version"] == 1

    def test_carried_backfilled_when_missing(self) -> None:
        carried = [{"name": "legacy"}]  # predates the marker
        out = _merge_revision_snapshot(carried, [], current_version=2, prior_version=1)
        assert out[0]["introduced_in_version"] == 1

    def test_carried_wins_on_name_collision(self) -> None:
        carried = [{"name": "dup", "introduced_in_version": 0, "tier": "rag"}]
        new = [{"name": "dup", "tier": "single_call"}]
        out = _merge_revision_snapshot(carried, new, current_version=1, prior_version=0)
        assert len(out) == 1
        assert out[0]["tier"] == "rag"  # built entry kept, not the new duplicate
        assert out[0]["introduced_in_version"] == 0

    def test_does_not_mutate_inputs(self) -> None:
        carried = [{"name": "c"}]
        new = [{"name": "n"}]
        _merge_revision_snapshot(carried, new, 1, 0)
        assert "introduced_in_version" not in carried[0]
        assert "introduced_in_version" not in new[0]


# ---------------------------------------------------------------------------
# _removed_feature_heads_up
# ---------------------------------------------------------------------------


class TestRemovedFeatureHeadsUp:
    def test_note_when_built_feature_links_removed(self) -> None:
        carried = [
            {"name": "coupon_ranker", "linked_vision_features": ["Legacy_Coupons"]},
        ]
        delta = {"changes": {"removed": ["Legacy_Coupons"]}}
        note = _removed_feature_heads_up(carried, delta)
        assert "coupon_ranker" in note
        assert "Legacy_Coupons" in note
        assert "carried forward" in note.lower()

    def test_empty_when_nothing_removed(self) -> None:
        carried = [{"name": "a", "linked_vision_features": ["F"]}]
        assert _removed_feature_heads_up(carried, {"changes": {"removed": []}}) == ""
        assert _removed_feature_heads_up(carried, None) == ""

    def test_empty_when_no_overlap(self) -> None:
        carried = [{"name": "a", "linked_vision_features": ["Kept"]}]
        delta = {"changes": {"removed": ["Gone"]}}
        assert _removed_feature_heads_up(carried, delta) == ""


# ---------------------------------------------------------------------------
# _build_seed_message — brownfield suppression in revision mode
# ---------------------------------------------------------------------------


def _one_candidate() -> tuple[list[Candidate], list[TierAnalystOutput]]:
    cand = [
        Candidate(
            name="returns_triage",
            linked_vision_features=["Returns_Portal"],
            scope="feature",
            rough_description="x",
        )
    ]
    analysis = [
        TierAnalystOutput(
            recommended_tier="single_call",
            rationale="r",
            risks_of_going_higher=[],
            risks_of_going_lower=[],
            borderline=False,
            borderline_seams=[],
            compared_to_next_tier_down="",
        )
    ]
    return cand, analysis


class TestSeedMessageRevision:
    def test_revision_suppresses_brownfield_question(self) -> None:
        cand, analysis = _one_candidate()
        seed = _build_seed_message(
            cand, analysis, brownfield=True, revision_goal="Add returns."
        )
        assert "adding AI features for the first time" not in seed
        assert "REVISION round" in seed
        assert "Add returns." in seed

    def test_brownfield_question_kept_without_revision(self) -> None:
        cand, analysis = _one_candidate()
        seed = _build_seed_message(cand, analysis, brownfield=True)
        assert "adding AI features for the first time" in seed

    def test_greenfield_has_no_mode_note(self) -> None:
        cand, analysis = _one_candidate()
        seed = _build_seed_message(cand, analysis)
        assert "BROWNFIELD" not in seed
        assert "REVISION" not in seed


# ---------------------------------------------------------------------------
# _complete_agentifier — revision finalisation (carry-forward + stamp + cc)
# ---------------------------------------------------------------------------


def _revision_session(new_feats: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "agentifier_messages": [],
        "ai_features": {"ai_features": list(new_feats), "cross_cutting": {}},
        "agentifier_cross_cutting_decisions": {"provider_strategy": "new_decision"},
        "agentifier_revision": True,
        "agentifier_carried_forward": [
            {"name": "expiry_prediction", "phase_priority": "mvp",
             "introduced_in_version": 0,
             "linked_vision_features": ["Legacy_Coupons"]},
        ],
        "agentifier_revision_version": 1,
        "agentifier_revision_prior_version": 0,
        "agentifier_revision_delta": {"changes": {"removed": ["Legacy_Coupons"]}},
        "agentifier_revision_cross_cutting": {"prompt_versioning": "old_decision"},
    }


class TestCompleteAgentifierRevision:
    def test_carried_forward_merged_and_stamped(self) -> None:
        session = _revision_session([{"name": "returns_triage"}])
        out = _collect(agentifier._complete_agentifier(session))
        feats = session["ai_features"]["ai_features"]
        names = [f["name"] for f in feats]
        assert names == ["expiry_prediction", "returns_triage"]  # built first
        stamps = {f["name"]: f["introduced_in_version"] for f in feats}
        assert stamps == {"expiry_prediction": 0, "returns_triage": 1}
        # heads-up surfaced because a built feature links a removed product feature
        assert "expiry_prediction" in out and "Heads-up" in out

    def test_cross_cutting_prior_preserved_and_overridden(self) -> None:
        session = _revision_session([{"name": "n"}])
        _collect(agentifier._complete_agentifier(session))
        cc = session["ai_features"]["cross_cutting"]
        assert cc["prompt_versioning"] == "old_decision"  # prior preserved
        assert cc["provider_strategy"] == "new_decision"  # this round's decision

    def test_zero_new_keeps_only_carried_forward(self) -> None:
        session = _revision_session([])
        _collect(agentifier._complete_agentifier(session))
        feats = session["ai_features"]["ai_features"]
        assert [f["name"] for f in feats] == ["expiry_prediction"]

    def test_revision_state_cleared(self) -> None:
        session = _revision_session([{"name": "n"}])
        _collect(agentifier._complete_agentifier(session))
        for key in (
            "agentifier_revision",
            "agentifier_carried_forward",
            "agentifier_revision_version",
            "agentifier_revision_prior_version",
            "agentifier_revision_delta",
            "agentifier_revision_cross_cutting",
        ):
            assert key not in session
        assert session["agentifier_state"] == agentifier.STATE_AGENTIFIER_COMPLETE

    def test_non_revision_unaffected(self) -> None:
        session = {
            "agentifier_messages": [],
            "ai_features": {"ai_features": [{"name": "a"}], "cross_cutting": {}},
            "agentifier_cross_cutting_decisions": {"x": "y"},
        }
        _collect(agentifier._complete_agentifier(session))
        feats = session["ai_features"]["ai_features"]
        assert [f["name"] for f in feats] == ["a"]
        assert "introduced_in_version" not in feats[0]
        assert session["ai_features"]["cross_cutting"] == {"x": "y"}


# ---------------------------------------------------------------------------
# Fresh-start detection + Scout wiring
# ---------------------------------------------------------------------------

_PRIOR_AI = {
    "ai_features": [
        {"name": "expiry_prediction", "linked_vision_features": ["Expiry_Tracking"]},
    ],
    "cross_cutting": {"prompt_versioning": "decided"},
}

_REVISION_VISION = {
    "vision_statement": {
        "name": "ShelfLife",
        "revision_history": [
            {
                "version": 1,
                "goal": "Add returns flow.",
                "changes": {"added": ["Returns_Portal"], "modified": [], "removed": []},
            }
        ],
    }
}


class TestFreshStartRevisionDetection:
    def _session(self, vision: dict[str, Any]) -> dict[str, Any]:
        return {
            "agentifier_messages": [],
            "working_dir": "/tmp/proj",
            "vision_statement": vision,
            "code_review": {"is_software_project": True},
        }

    def test_detects_revision_and_informs_scout(self) -> None:
        session = self._session(_REVISION_VISION)
        with patch.object(
            agentifier, "_call_scout", side_effect=RuntimeError("stop")
        ) as mock_scout, patch.object(
            agentifier.project_manager,
            "load_prior_ai_features",
            return_value=_PRIOR_AI,
        ), patch.object(
            agentifier.project_manager, "resolve_phase_version", return_value=(1, False)
        ), patch.object(
            agentifier.project_manager, "latest_implemented_version", return_value=0
        ):
            _collect(agentifier._run_catalog_phase(None, session, {"model": "x"}))

        assert session["agentifier_revision"] is True
        assert session["agentifier_revision_version"] == 1
        assert session["agentifier_revision_prior_version"] == 0
        assert [f["name"] for f in session["agentifier_carried_forward"]] == [
            "expiry_prediction"
        ]
        assert session["agentifier_revision_cross_cutting"] == {
            "prompt_versioning": "decided"
        }
        rev = mock_scout.call_args.kwargs["revision"]
        assert rev is not None
        assert rev["goal"] == "Add returns flow."
        assert rev["existing_ai_features"][0]["name"] == "expiry_prediction"

    def test_greenfield_no_revision_scout_none(self) -> None:
        session = self._session({"vision_statement": {"name": "Fresh"}})
        with patch.object(
            agentifier, "_call_scout", side_effect=RuntimeError("stop")
        ) as mock_scout, patch.object(
            agentifier.project_manager, "load_prior_ai_features", return_value=None
        ):
            _collect(agentifier._run_catalog_phase(None, session, {"model": "x"}))
        assert "agentifier_revision" not in session
        assert mock_scout.call_args.kwargs["revision"] is None

    def test_zero_prior_ai_features_still_revision(self) -> None:
        # A revision that adds the first AI features onto a previously AI-free
        # project (prior round had zero AI features) is still a revision: the
        # trigger is the implemented predecessor, not a prior AI surface. The
        # new features must still be stamped with introduced_in_version, so the
        # revision flow runs with an empty carried-forward set and Scout is
        # informed of the delta.
        session = self._session(_REVISION_VISION)
        with patch.object(
            agentifier, "_call_scout", side_effect=RuntimeError("stop")
        ) as mock_scout, patch.object(
            agentifier.project_manager, "load_prior_ai_features", return_value=None
        ), patch.object(
            agentifier.project_manager, "resolve_phase_version", return_value=(1, False)
        ), patch.object(
            agentifier.project_manager, "latest_implemented_version", return_value=0
        ):
            _collect(agentifier._run_catalog_phase(None, session, {"model": "x"}))
        assert session["agentifier_revision"] is True
        assert session["agentifier_revision_version"] == 1
        assert session["agentifier_revision_prior_version"] == 0
        assert session["agentifier_carried_forward"] == []
        rev = mock_scout.call_args.kwargs["revision"]
        assert rev is not None
        assert rev["goal"] == "Add returns flow."
        assert rev["existing_ai_features"] == []


# ---------------------------------------------------------------------------
# Revision + Scout-returns-zero-new — carry forward, don't bail as greenfield
# ---------------------------------------------------------------------------


class TestRevisionScoutZeroNew:
    def _session(self, vision: dict[str, Any]) -> dict[str, Any]:
        return {
            "agentifier_messages": [],
            "working_dir": "/tmp/proj",
            "vision_statement": vision,
            "code_review": {"is_software_project": True},
        }

    def test_zero_new_candidates_finalises_carried_forward(self) -> None:
        # A presentation-only revision (e.g. trash-talk → toast) introduces no
        # new AI surface, so Scout legitimately returns zero candidates. The
        # established AI surface must still be carried forward and the round
        # finalised — NOT bailed as if greenfield (which would leave the prior
        # ai_features unre-affirmed and staleness uncleared).
        from spec4.agentifier.scout import ScoutOutput

        session = self._session(_REVISION_VISION)
        with patch.object(
            agentifier, "_call_scout", return_value=ScoutOutput(candidates=[])
        ), patch.object(
            agentifier.project_manager, "load_prior_ai_features", return_value=_PRIOR_AI
        ), patch.object(
            agentifier.project_manager, "resolve_phase_version", return_value=(1, False)
        ), patch.object(
            agentifier.project_manager, "latest_implemented_version", return_value=0
        ):
            out = _collect(agentifier._run_catalog_phase(None, session, {"model": "x"}))

        # carried-forward surface preserved; greenfield bail NOT taken
        assert [f["name"] for f in session["ai_features"]["ai_features"]] == [
            "expiry_prediction"
        ]
        assert session["agentifier_state"] == agentifier.STATE_AGENTIFIER_COMPLETE
        assert "did not find any AI-integration opportunities" not in out
        assert "carried forward unchanged" in out
        # completion flags set so a later re-entry routes through _handle_reentry
        assert session["agentifier_catalog_done"] is True
        assert session["agentifier_priority_done"] is True

    def test_non_revision_zero_completes_empty(self) -> None:
        from spec4.agentifier.scout import ScoutOutput

        session = self._session({"vision_statement": {"name": "Fresh"}})
        with patch.object(
            agentifier, "_call_scout", return_value=ScoutOutput(candidates=[])
        ), patch.object(
            agentifier.project_manager, "load_prior_ai_features", return_value=None
        ):
            out = _collect(agentifier._run_catalog_phase(None, session, {"model": "x"}))
        assert "did not find any AI-integration opportunities" in out
        assert "agentifier_revision" not in session
        # Greenfield no-AI vision still finalises so the developer reaches the
        # completion state (and its Continue button) rather than being stranded;
        # the empty catalog table is not shown.
        assert session["agentifier_state"] == agentifier.STATE_AGENTIFIER_COMPLETE
        assert session["ai_features"]["ai_features"] == []
        assert "AI Feature Catalog — Complete" not in out
