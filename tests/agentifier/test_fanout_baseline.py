"""Unit tests for the offline fan-out baseline driver."""

from __future__ import annotations

from fanout_baseline import (  # noqa: E402 (evals/ is a script dir, not a package)
    fanout_for_draw,
    surfaced_candidates,
    vision_feature_names,
)

_VISION = {
    "vision_statement": {
        "vision": {
            "key_features_mvp": [
                {"catchup": {"description": "..."}},
                {"reply": {"description": "..."}},
            ]
        }
    }
}


def _feat(fid, kind="feature", links=None):
    return {"id": fid, "kind": kind, "linked_vision_features": links or []}


def test_vision_feature_names_reads_mvp_keys():
    assert vision_feature_names(_VISION) == ["catchup", "reply"]


def test_infrastructure_is_excluded_from_candidates():
    feats = [_feat("a"), _feat("harness", kind="infrastructure")]
    assert [c["id"] for c in surfaced_candidates(feats)] == ["a"]


def test_fanout_counts_fragmentation():
    # 3 candidates map to "catchup" (fragmentation), 1 to "reply".
    feats = [
        _feat("catchup", links=["catchup"]),
        _feat("decision_extraction", links=["catchup"]),
        _feat("question_id", links=["catchup"]),
        _feat("reply", links=["reply"]),
        _feat("harness", kind="infrastructure", links=[]),
    ]
    fo = fanout_for_draw(_VISION, feats)
    assert fo.per_feature == {"catchup": 3, "reply": 1}
    assert fo.n_candidate_instances == 4  # infra excluded
    assert fo.max_fanout == ("catchup", 3.0)
    assert fo.mean_fanout == 2.0  # (3 + 1) / 2 features
    assert fo.unlinked_instances == 0


def test_multi_link_candidate_counts_once_per_feature():
    feats = [_feat("whole", links=["catchup", "reply"])]
    fo = fanout_for_draw(_VISION, feats)
    assert fo.per_feature == {"catchup": 1, "reply": 1}


def test_candidate_linking_no_stated_feature_is_unlinked():
    feats = [_feat("adjacent", links=["some_enhancement"])]
    fo = fanout_for_draw(_VISION, feats)
    assert fo.unlinked_instances == 1
    assert fo.per_feature == {"catchup": 0, "reply": 0}