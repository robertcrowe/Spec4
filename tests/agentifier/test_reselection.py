"""Tests for Agentifier re-entry / re-selection (pure logic, no live LLM)."""
from __future__ import annotations

from unittest.mock import patch

from spec4.agentifier import agentifier
from spec4.agentifier.agentifier import _reselection_pool_from_features
from spec4.app_constants import STATE_AGENTIFIER_COMPLETE, STATE_IN_PROGRESS


def _collect(gen):
    return "".join(gen)


_AI_FEATURES = {
    "ai_features": [
        {"id": "a", "name": "alpha", "tier": "rag", "phase_priority": "mvp",
         "scope": "feature", "rough_description": "alpha desc",
         "linked_vision_features": ["v1"]},
        {"id": "b", "name": "beta", "tier": "single_call", "phase_priority": "mvp",
         "scope": "feature", "rough_description": "beta desc"},
    ],
    "explicitly_rejected": [
        {"name": "gamma", "rough_description": "gamma desc", "band": "balanced",
         "reason": "deselected_by_user"},
    ],
    "cross_cutting": {},
}


class TestReselectionPool:
    def test_pool_is_selected_then_rejected(self):
        pool = _reselection_pool_from_features(_AI_FEATURES)
        assert [c.name for c in pool] == ["alpha", "beta", "gamma"]

    def test_selected_carries_fields_rejected_minimal(self):
        pool = _reselection_pool_from_features(_AI_FEATURES)
        alpha = pool[0]
        assert alpha.linked_vision_features == ["v1"]
        assert alpha.rough_description == "alpha desc"
        gamma = pool[2]
        assert gamma.rough_description == "gamma desc"
        assert gamma.linked_vision_features == []

    def test_dedup_by_name(self):
        feats = {
            "ai_features": [{"name": "dup", "rough_description": "x"}],
            "explicitly_rejected": [{"name": "dup", "rough_description": "y"}],
        }
        pool = _reselection_pool_from_features(feats)
        assert [c.name for c in pool] == ["dup"]

    def test_empty(self):
        assert _reselection_pool_from_features({}) == []


class TestHandleReentryNotStale:
    def test_opens_reselection_panel_with_prechecks(self):
        session = {"working_dir": "/tmp/proj", "ai_features": _AI_FEATURES,
                   "agentifier_messages": [{"role": "assistant", "content": "old"}],
                   "agentifier_state": STATE_AGENTIFIER_COMPLETE,
                   "agentifier_catalog_done": True, "agentifier_spec_done": True,
                   "agentifier_cross_cutting_done": True, "agentifier_priority_done": True}
        with patch.object(agentifier.project_manager, "detect_stale_inputs",
                          return_value={}):
            out = _collect(agentifier._handle_reentry(None, session, {"model": "x"}))
        # intro surfaced
        assert "Revising your AI features" in out
        # completion state demoted so the Continue/Download buttons stop rendering
        # against the pre-revision ai_features until the flow re-completes
        assert session["agentifier_state"] == STATE_IN_PROGRESS
        # previously-selected pre-checked, full pool available
        assert session["agentifier_breadth_selection"] == ["alpha", "beta"]
        assert [c["name"] for c in session["agentifier_scout_pool"]] == [
            "alpha", "beta", "gamma"
        ]
        # re-selection armed; panel pending; messages cleared so the panel shows
        assert session["agentifier_reselection"] is True
        assert session["agentifier_breadth_chosen"] is False
        assert session["agentifier_messages"] == []
        # done-flags reset so dispatch routes back into the catalog phase
        assert session["agentifier_catalog_done"] is False
        assert session["agentifier_spec_done"] is False
        # preserved entries kept verbatim for the merge
        assert set(session["agentifier_preserved_features"]) == {"alpha", "beta"}


class TestHandleReentryStale:
    def test_vision_newer_resets_and_rediscovers(self):
        session = {"working_dir": "/tmp/proj", "ai_features": _AI_FEATURES,
                   "agentifier_messages": [{"role": "assistant", "content": "old"}],
                   "agentifier_state": STATE_AGENTIFIER_COMPLETE,
                   "agentifier_catalog_done": True, "agentifier_spec_done": True,
                   "agentifier_cross_cutting_done": True, "agentifier_priority_done": True,
                   "agentifier_reselection": True}

        def _fake_catalog(_ui, _s, _cfg):
            yield "rediscovering"

        with patch.object(agentifier.project_manager, "detect_stale_inputs",
                          return_value={"vision": 123.0}), \
             patch.object(agentifier, "_run_catalog_phase", side_effect=_fake_catalog):
            out = _collect(agentifier._handle_reentry(None, session, {"model": "x"}))
        assert out == "rediscovering"
        # full reset for a fresh discovery
        assert session["agentifier_catalog_done"] is False
        assert session["agentifier_spec_done"] is False
        assert session["agentifier_messages"] == []
        assert "agentifier_reselection" not in session
        assert session["agentifier_stale_acknowledged"] == {"vision": 123.0}
        # completion state demoted for the rediscovery re-run as well
        assert session["agentifier_state"] == STATE_IN_PROGRESS

    def test_stale_reentry_clears_candidate_pool(self):
        # The forced re-discovery only re-runs Scout + revision detection when
        # agentifier_candidates is None. A leaked (often empty) pool from the
        # prior round would silently skip it. Assert the stale branch nulls the
        # cached candidates AND analyses *before* _run_catalog_phase is invoked.
        session = {"working_dir": "/tmp/proj", "ai_features": _AI_FEATURES,
                   "agentifier_messages": [{"role": "assistant", "content": "old"}],
                   "agentifier_catalog_done": True, "agentifier_spec_done": True,
                   "agentifier_cross_cutting_done": True, "agentifier_priority_done": True,
                   "agentifier_candidates": [], "agentifier_analyses": []}
        captured: dict[str, object] = {}

        def _fake_catalog(_ui, s, _cfg):
            captured["candidates"] = s.get("agentifier_candidates")
            captured["analyses"] = s.get("agentifier_analyses")
            yield "rediscovering"

        with patch.object(agentifier.project_manager, "detect_stale_inputs",
                          return_value={"vision": 123.0}), \
             patch.object(agentifier, "_run_catalog_phase", side_effect=_fake_catalog):
            _collect(agentifier._handle_reentry(None, session, {"model": "x"}))
        assert captured["candidates"] is None
        assert captured["analyses"] is None


class TestFinalizeMergePreserved:
    def test_preserved_prepended_and_flags_cleared(self):
        session = {
            "agentifier_messages": [],
            "agentifier_reselection": True,
            "agentifier_preserved_selected": [
                {"id": "alpha", "name": "alpha", "tier": "rag"}
            ],
            "ai_catalog": {"ai_catalog": [
                {"name": "new_feat", "scope": "feature",
                 "tier_decision": "single_call", "rough_description": "n"}
            ]},
            "agentifier_spec_results": [{"purpose": "p"}],
            "agentifier_candidates": [{"name": "new_feat", "linked_vision_features": []}],
            "agentifier_analyses": [],
        }
        # Stub the cross-cutting machinery so _finalize_specs returns right after
        # assembling (and storing) ai_features.
        with patch.object(agentifier, "load_patterns", return_value=([], [])), \
             patch.object(agentifier._registry, "stream",
                          side_effect=RuntimeError("stop after assembly")):
            _collect(agentifier._finalize_specs(session, {"model": "x"}))
        names = [f["name"] for f in session["ai_features"]["ai_features"]]
        assert names == ["alpha", "new_feat"]  # preserved first, then new
        # re-selection state cleared once assembled
        assert "agentifier_reselection" not in session
        assert "agentifier_preserved_selected" not in session
