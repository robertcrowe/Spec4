"""Unit tests for the deterministic infrastructure expansion pass.

Exercises ``expand_infrastructure`` in isolation with a synthetic registry map
so the logic is independent of the tier-pattern YAML (that wiring is covered by
``test_infra_registry.py``). Covers the ratified behaviours: registry-driven
injection (D-I2), dedup by component id (D-I3), infra as a source node (no
upstream ``requires``), the ``kind``/priority markers (D-I5/D-I6), losslessness,
idempotency, and the revision stamp.
"""

from __future__ import annotations

from typing import Any

from spec4.agentifier.infra_expander import (
    INFRA_KIND,
    INFRA_PRIORITY,
    INFRA_TIER,
    expand_infrastructure,
)

# A synthetic registry mirroring the shared-component shape of the real one.
REG: dict[str, list[str]] = {
    "deterministic": [],
    "single_call": [],
    "embeddings": ["embedding_pipeline", "vector_index"],
    "rag": ["chunking_pipeline", "retriever", "embedding_pipeline", "vector_index"],
    "tool_agent": ["tool_execution_harness"],
}


def _feat(name: str, tier: str, requires: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "tier": tier,
        "requires": list(requires or []),
        "kind": "feature",
        "phase_priority": "mvp",
    }


def _infra(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [f for f in features if f.get("kind") == INFRA_KIND]


def _by_name(features: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {f["name"]: f for f in features}


class TestNoInjection:
    def test_empty_tiers_inject_nothing(self) -> None:
        feats = [_feat("rules", "deterministic"), _feat("classify", "single_call")]
        out = expand_infrastructure(feats, REG)
        assert _infra(out) == []
        # Features are returned unchanged (no spurious edges).
        assert _by_name(out)["rules"]["requires"] == []

    def test_unknown_tier_ignored(self) -> None:
        out = expand_infrastructure([_feat("mystery", "not_a_tier")], REG)
        assert _infra(out) == []

    def test_empty_feature_set(self) -> None:
        assert expand_infrastructure([], REG) == []


class TestInjection:
    def test_embeddings_injects_both_components(self) -> None:
        out = expand_infrastructure([_feat("search", "embeddings")], REG)
        names = {f["name"] for f in _infra(out)}
        assert names == {"embedding_pipeline", "vector_index"}

    def test_injected_node_markers(self) -> None:
        out = expand_infrastructure([_feat("search", "embeddings")], REG)
        node = _by_name(out)["vector_index"]
        assert node["kind"] == INFRA_KIND
        assert node["tier"] == INFRA_TIER
        assert node["phase_priority"] == INFRA_PRIORITY
        assert node["composed_under"] == ""
        assert node["tier_analysis"] == {}
        assert node["id"] == "vector_index"

    def test_downstream_edge_on_feature(self) -> None:
        out = expand_infrastructure([_feat("search", "embeddings")], REG)
        reqs = _by_name(out)["search"]["requires"]
        assert "embedding_pipeline" in reqs
        assert "vector_index" in reqs


class TestDedup:
    def test_shared_components_collapse_by_id(self) -> None:
        feats = [_feat("search", "embeddings"), _feat("answer", "rag")]
        out = expand_infrastructure(feats, REG)
        names = [f["name"] for f in _infra(out)]
        # Each component appears exactly once despite two triggering features.
        assert sorted(names) == [
            "chunking_pipeline",
            "embedding_pipeline",
            "retriever",
            "vector_index",
        ]
        assert len(names) == len(set(names))

    def test_new_infra_sorted_by_id(self) -> None:
        feats = [_feat("answer", "rag")]
        out = expand_infrastructure(feats, REG)
        ids = [f["id"] for f in _infra(out)]
        assert ids == sorted(ids)


class TestInfraIsSourceNode:
    def test_infra_requires_is_empty(self) -> None:
        feats = [_feat("search", "embeddings", requires=["article_extraction"])]
        out = expand_infrastructure(feats, REG)
        for node in _infra(out):
            assert node["requires"] == []

    def test_no_edge_back_to_producer(self) -> None:
        # Even when the triggering feature has producers, no infra->producer edge
        # is drawn — infra is a pure source.
        feats = [
            _feat("search", "embeddings", requires=["articles"]),
            _feat("answer", "rag", requires=["notes"]),
        ]
        out = expand_infrastructure(feats, REG)
        for node in _infra(out):
            assert node["requires"] == []

    def test_no_cycle_when_producer_is_a_trigger(self) -> None:
        # A triggering feature whose producer is itself a triggering feature is
        # exactly the shape that used to close a 2-cycle. As a source node, infra
        # takes no upstream, so no cycle can form.
        feats = [
            _feat("search", "embeddings", requires=["answer"]),
            _feat("answer", "embeddings", requires=[]),
        ]
        out = expand_infrastructure(feats, REG)
        for node in _infra(out):
            assert node["requires"] == []

    def test_lossless_original_requires_kept(self) -> None:
        feats = [_feat("search", "embeddings", requires=["articles"])]
        out = expand_infrastructure(feats, REG)
        reqs = _by_name(out)["search"]["requires"]
        # Original producer is retained alongside the new substrate edges.
        assert "articles" in reqs
        assert reqs[0] == "articles"


class TestIdempotency:
    def test_rerun_is_stable(self) -> None:
        feats = [_feat("search", "embeddings", requires=["articles"])]
        once = expand_infrastructure(feats, REG)
        twice = expand_infrastructure(once, REG)
        assert len(once) == len(twice)
        assert len(_infra(twice)) == 2
        # No duplicated downstream edges on the feature.
        reqs = _by_name(twice)["search"]["requires"]
        assert reqs.count("vector_index") == 1

    def test_carried_infra_not_reinjected(self) -> None:
        # A feature set that already carries an infrastructure node (revision).
        carried = expand_infrastructure([_feat("search", "embeddings")], REG)
        again = expand_infrastructure(carried, REG)
        names = [f["name"] for f in _infra(again)]
        assert names.count("vector_index") == 1
        assert names.count("embedding_pipeline") == 1


class TestRevisionStamp:
    def test_new_infra_stamped(self) -> None:
        out = expand_infrastructure(
            [_feat("search", "embeddings")], REG, introduced_in_version=3
        )
        for node in _infra(out):
            assert node["introduced_in_version"] == 3

    def test_no_stamp_when_greenfield(self) -> None:
        out = expand_infrastructure([_feat("search", "embeddings")], REG)
        for node in _infra(out):
            assert "introduced_in_version" not in node
