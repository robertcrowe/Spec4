"""Tests for Scout graph-contract edge persistence (D-EP).

Covers all four boundaries the spec document identifies:

D-EP1 — _candidates_to_dicts / _candidates_from_dicts serialisation round-trip.
D-EP2 — _build_ai_features: candidate is authoritative; spec-drafter echo can't
         clobber composed_under / requires.
D-EP3 — _reselection_pool_from_features: rehydrates edges from persisted ai_features.
D-EP4 — _ai_features_for_phaser / _feature_relationship_lines: edges surfaced in
         the Phaser prompt, including dangling-persists-raw and revision
         cross-partition.
"""

from __future__ import annotations

from typing import Any


from spec4.agentifier.agentifier import (
    _build_ai_features,
    _candidates_from_dicts,
    _candidates_to_dicts,
    _reselection_pool_from_features,
)
from spec4.agentifier.scout import Candidate
from spec4.agents._utils import _ai_features_for_phaser, _feature_relationship_lines

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _c(
    name: str,
    *,
    composed_under: str = "",
    requires: list[str] | None = None,
    scope: str = "feature",
    desc: str = "Does a thing.",
) -> Candidate:
    return Candidate(
        name=name,
        linked_vision_features=[],
        scope=scope,
        rough_description=desc,
        composed_under=composed_under,
        requires=list(requires or []),
    )


def _feat(name: str, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": name,
        "rough_description": f"{name} desc",
        "scope": "feature",
        "linked_vision_features": [],
        "linked_existing_workflow": "",
        "composed_under": "",
        "requires": [],
        "tier": "single_call",
        "tier_recommendation": "",
        "tier_decision_rationale": "",
        "phase_priority": "mvp",
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# D-EP1: serialisation round-trip
# ---------------------------------------------------------------------------


class TestSerializationRoundTrip:
    def test_standalone_candidate_survives(self) -> None:
        c = _c("solo")
        [d] = _candidates_to_dicts([c])
        [back] = _candidates_from_dicts([d])
        assert back.composed_under == ""
        assert back.requires == []

    def test_composed_under_survives(self) -> None:
        c = _c("member", composed_under="orch")
        [d] = _candidates_to_dicts([c])
        [back] = _candidates_from_dicts([d])
        assert back.composed_under == "orch"

    def test_requires_list_survives(self) -> None:
        c = _c("consumer", requires=["producer_a", "producer_b"])
        [d] = _candidates_to_dicts([c])
        [back] = _candidates_from_dicts([d])
        assert back.requires == ["producer_a", "producer_b"]

    def test_both_edges_survive_together(self) -> None:
        c = _c("stage_two", composed_under="pipeline", requires=["stage_one"])
        [d] = _candidates_to_dicts([c])
        [back] = _candidates_from_dicts([d])
        assert back.composed_under == "pipeline"
        assert back.requires == ["stage_one"]

    def test_multiple_candidates_edges_survive(self) -> None:
        cands = [
            _c("orch"),
            _c("m1", composed_under="orch"),
            _c("m2", composed_under="orch", requires=["m1"]),
        ]
        dicts = _candidates_to_dicts(cands)
        backs = _candidates_from_dicts(dicts)
        by = {c.name: c for c in backs}
        assert by["orch"].composed_under == ""
        assert by["m1"].composed_under == "orch"
        assert by["m2"].composed_under == "orch"
        assert by["m2"].requires == ["m1"]

    def test_missing_edge_keys_default_to_empty(self) -> None:
        # Legacy dict without the new keys — should not raise and defaults empty.
        d = {
            "name": "legacy",
            "linked_vision_features": [],
            "scope": "feature",
            "rough_description": "old",
            "linked_existing_workflow": "",
        }
        [back] = _candidates_from_dicts([d])
        assert back.composed_under == ""
        assert back.requires == []


# ---------------------------------------------------------------------------
# D-EP2: _build_ai_features — candidate authority over edges
# ---------------------------------------------------------------------------


def _make_entry(name: str, **kw: Any) -> dict[str, Any]:
    base = {
        "name": name,
        "rough_description": "",
        "scope": "feature",
        "linked_vision_features": [],
        "linked_existing_workflow": "",
        "tier": "single_call",
        "tier_decision": "single_call",
        "tier_recommendation": "",
        "tier_decision_rationale": "",
        "phase_priority": "mvp",
    }
    base.update(kw)
    return base


class TestBuildAiFeaturesEdgeAuthority:
    def test_composed_under_from_candidate_not_spec(self) -> None:
        entry = _make_entry("member")
        cand = {
            "name": "member",
            "linked_vision_features": [],
            "scope": "sub_feature",
            "rough_description": "desc",
            "linked_existing_workflow": "",
            "composed_under": "orch",
            "requires": [],
        }
        spec = [{"composed_under": "WRONG_FROM_SPEC"}]
        [feat] = _build_ai_features([entry], spec, [cand])
        assert feat["composed_under"] == "orch"

    def test_requires_from_candidate_not_spec(self) -> None:
        entry = _make_entry("consumer")
        cand = {
            "name": "consumer",
            "linked_vision_features": [],
            "scope": "feature",
            "rough_description": "desc",
            "linked_existing_workflow": "",
            "composed_under": "",
            "requires": ["producer"],
        }
        spec = [{"requires": ["WRONG"]}]
        [feat] = _build_ai_features([entry], spec, [cand])
        assert feat["requires"] == ["producer"]

    def test_edges_empty_when_candidate_has_none(self) -> None:
        entry = _make_entry("plain")
        cand = {
            "name": "plain",
            "linked_vision_features": [],
            "scope": "feature",
            "rough_description": "desc",
            "linked_existing_workflow": "",
            "composed_under": "",
            "requires": [],
        }
        [feat] = _build_ai_features([entry], [], [cand])
        assert feat["composed_under"] == ""
        assert feat["requires"] == []

    def test_edges_survive_with_no_matching_candidate(self) -> None:
        # Entry with no candidate — edges default to empty (no crash).
        entry = _make_entry("orphan")
        [feat] = _build_ai_features([entry], [], [])
        assert feat.get("composed_under", "") == ""
        assert feat.get("requires", []) == []


# ---------------------------------------------------------------------------
# D-EP3: _reselection_pool_from_features rehydrates edges
# ---------------------------------------------------------------------------


class TestReselectionPoolRehydration:
    def _af(self, features: list[dict[str, Any]]) -> dict[str, Any]:
        return {"ai_features": features, "explicitly_rejected": []}

    def test_composed_under_rehydrated(self) -> None:
        af = self._af([_feat("member", composed_under="orch")])
        pool = _reselection_pool_from_features(af)
        assert pool[0].composed_under == "orch"

    def test_requires_rehydrated(self) -> None:
        af = self._af([_feat("consumer", requires=["producer"])])
        pool = _reselection_pool_from_features(af)
        assert pool[0].requires == ["producer"]

    def test_missing_edge_keys_default_empty_in_pool(self) -> None:
        feat = {
            "name": "old",
            "rough_description": "desc",
            "scope": "feature",
            "linked_vision_features": [],
            "linked_existing_workflow": "",
        }
        pool = _reselection_pool_from_features({"ai_features": [feat], "explicitly_rejected": []})
        assert pool[0].composed_under == ""
        assert pool[0].requires == []

    def test_both_edges_rehydrated_for_multiple_features(self) -> None:
        af = self._af([
            _feat("orch"),
            _feat("m1", composed_under="orch"),
            _feat("m2", composed_under="orch", requires=["m1"]),
        ])
        pool = _reselection_pool_from_features(af)
        by = {c.name: c for c in pool}
        assert by["orch"].composed_under == ""
        assert by["m1"].composed_under == "orch"
        assert by["m2"].requires == ["m1"]


# ---------------------------------------------------------------------------
# D-EP4: _feature_relationship_lines and _ai_features_for_phaser
# ---------------------------------------------------------------------------


class TestFeatureRelationshipLines:
    def test_empty_when_no_edges(self) -> None:
        feats = [_feat("a"), _feat("b")]
        assert _feature_relationship_lines(feats) == []

    def test_composed_under_group_rendered(self) -> None:
        feats = [_feat("orch"), _feat("m1", composed_under="orch"), _feat("m2", composed_under="orch")]
        lines = _feature_relationship_lines(feats)
        block = "\n".join(lines)
        assert "composed_under" in block
        assert "orch" in block
        assert "m1" in block
        assert "m2" in block

    def test_requires_edge_rendered(self) -> None:
        feats = [_feat("producer"), _feat("consumer", requires=["producer"])]
        lines = _feature_relationship_lines(feats)
        block = "\n".join(lines)
        assert "requires" in block
        assert "consumer" in block
        assert "producer" in block

    def test_dangling_composed_under_persisted_raw(self) -> None:
        # An edge pointing at a coordinator not in the feature list is rendered
        # verbatim (D-EP2 option A: no trimming at persistence time).
        feats = [_feat("orphan", composed_under="missing_coordinator")]
        lines = _feature_relationship_lines(feats)
        block = "\n".join(lines)
        assert "missing_coordinator" in block

    def test_multiple_coordinators_sorted(self) -> None:
        feats = [
            _feat("z_member", composed_under="z_coord"),
            _feat("a_member", composed_under="a_coord"),
        ]
        lines = _feature_relationship_lines(feats)
        block = "\n".join(lines)
        assert block.index("a_coord") < block.index("z_coord")


class TestAiFeaturesForPhaserRelationships:
    def _af(self, features: list[dict[str, Any]]) -> dict[str, Any]:
        return {"ai_features": features}

    def test_no_block_when_no_edges(self) -> None:
        af = self._af([_feat("a"), _feat("b")])
        result = _ai_features_for_phaser(af)
        assert "graph contract" not in result.lower()
        assert "composed_under" not in result

    def test_block_present_when_edges_exist(self) -> None:
        af = self._af([
            _feat("orch"),
            _feat("m", composed_under="orch"),
        ])
        result = _ai_features_for_phaser(af)
        assert "Feature relationships" in result
        assert "composed_under" in result
        assert "orch" in result

    def test_revision_cross_partition_uses_all_features(self) -> None:
        # With a revision version, ``features`` is partitioned so only the
        # to-phase slice is listed above. The relationships block must still
        # cover the *whole* feature set (all_feats), including features with
        # phase_implemented < revision_version that were moved to ``established``.
        feats = [
            _feat("orch"),
            _feat("m1", composed_under="orch", **{"phase_implemented": 1}),
            _feat("m2", composed_under="orch", **{"phase_priority": "mvp"}),
        ]
        af = self._af(feats)
        result = _ai_features_for_phaser(af, revision_version=2)
        # Both members must appear in the relationships block regardless of partition.
        assert "m1" in result
        assert "m2" in result
