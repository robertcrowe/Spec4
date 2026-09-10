"""Characterisation of the requires-inversion arms that only `evals/` reached.

Phase 6z (CLEANUP_INVENTORY.md §51.6). Fifteen statements in
``spec4.agentifier.requires_reconciler`` and one in ``spec4.agents.brainstormer``
had their only coverage in the repo from ``evals/phaser/test_requires_inversion.py``,
which left the default suite when Phase 6a added ``testpaths = ["tests"]``. The
logic is the D-RI signal classification — the thing that decides whether a
declared ``requires`` edge points the wrong way — and it was unguarded by any
test the gate runs.

One test per arm, named for the arm. These are characterisation tests: they pin
what the code does today, so a `src`-touching phase cannot change it silently.
"""

from __future__ import annotations

from typing import Any

from spec4.agentifier.requires_reconciler import (
    PROD_FLOOR,
    PROD_MARGIN,
    S3_DOMINANCE,
    S3_FLOOR,
    _norm_chunk,
    _stem_prefix_match,
    build_production_map,
    classify_edge,
)
from spec4.agents.brainstormer import _feature_names


def _node(
    name: str,
    *,
    inputs: list[dict[str, str]] | None = None,
    primary: str = "",
    trigger: str = "",
    linked: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": name.lower().replace(" ", "_"),
        "name": name,
        "kind": "feature",
        "invocation": {"trigger": trigger},
        "inputs": inputs or [],
        "outputs": {"primary": primary},
        "linked_vision_features": linked or [],
    }


# ---------------------------------------------------------------------------
# _norm_chunk — the deliberately minimal stemming
# ---------------------------------------------------------------------------


class TestStemming:
    def test_trailing_ing_is_stripped_above_five_characters(self) -> None:
        assert _norm_chunk("modeling") == "model"

    def test_trailing_s_is_stripped_above_three_characters(self) -> None:
        assert _norm_chunk("assumptions") == "assumption"

    def test_both_strips_apply_in_order(self) -> None:
        # "ing" first, then the "s" rule sees the shortened chunk.
        assert _norm_chunk("ratings") == "rating"

    def test_short_chunks_are_left_alone(self) -> None:
        assert _norm_chunk("ads") == "ads"
        assert _norm_chunk("sing") == "sing"


# ---------------------------------------------------------------------------
# _stem_prefix_match — D-RI13's stem-length guard
# ---------------------------------------------------------------------------


class TestStemLengthGuard:
    def test_a_single_chunk_stem_never_matches(self) -> None:
        """D-RI13: "question" matching any question_* node is coincidence."""
        assert _stem_prefix_match("question", "question_router") is False

    def test_a_short_two_chunk_stem_never_matches(self) -> None:
        """Under six characters of stem, still coincidence-prone."""
        assert _stem_prefix_match("a b", "a b c") is False

    def test_a_long_enough_stem_matches_as_a_prefix(self) -> None:
        assert _stem_prefix_match("ruleset summary", "ruleset summary builder") is True


# ---------------------------------------------------------------------------
# build_production_map — the floor and the margin tie-break
# ---------------------------------------------------------------------------


class TestProducerMarginTieBreak:
    def _specs(self, fid: str, artifact: str) -> Any:
        return [{"id": fid, "name": fid, "outputs": {"primary": artifact}}]

    def test_a_close_runner_up_names_no_producer(self) -> None:
        """Two candidates within PROD_MARGIN: the map declines to choose."""
        shared = "alpha beta gamma delta epsilon"
        a = _node("A", primary=shared, linked=["feat"])
        b = _node("B", primary=shared, linked=["feat"])
        out = build_production_map(self._specs("feat", shared), [a, b])
        assert out is not None and "feat" not in out

    def test_a_clear_leader_names_the_producer(self) -> None:
        rich = "alpha beta gamma delta epsilon zeta eta theta"
        a = _node("A", primary=rich, linked=["feat"])
        b = _node("B", primary="alpha", linked=["feat"])
        out = build_production_map(self._specs("feat", rich), [a, b])
        assert out is not None and out.get("feat") == "a"

    def test_overlap_below_the_floor_names_no_producer(self) -> None:
        a = _node("A", primary="alpha beta", linked=["feat"])
        out = build_production_map(self._specs("feat", "alpha beta"), [a])
        assert out is not None and "feat" not in out

    def test_no_specs_yields_no_map_at_all(self) -> None:
        assert build_production_map([], [_node("A")]) is None

    def test_the_constants_are_the_documented_ones(self) -> None:
        assert (PROD_FLOOR, PROD_MARGIN) == (3, 2)


# ---------------------------------------------------------------------------
# classify_edge — the S3 overlap arms
# ---------------------------------------------------------------------------


_SHARED = "alpha beta gamma delta epsilon zeta"


class TestS3OverlapArms:
    def test_forward_dominant_overlap_is_recorded_on_the_forward_side(self) -> None:
        consumer = _node("C", inputs=[{"name": "in", "description": _SHARED}])
        producer = _node("P", primary=_SHARED)
        verdict = classify_edge(consumer, producer, None, {})
        assert any("S3 dominant overlap" in s for s in _texts(verdict))

    def test_reverse_dominant_with_forward_signals_is_recorded_not_dropped(
        self,
    ) -> None:
        """D-RI11: reverse S3 rides along when the reverse side has signals."""
        consumer = _node("C", primary=_SHARED)
        producer = _node(
            "P",
            inputs=[{"name": "in", "description": _SHARED}],
            trigger="after C completes",
        )
        verdict = classify_edge(consumer, producer, None, {})
        assert any("S3 dominant overlap" in s for s in _texts(verdict))

    def test_reverse_with_zero_forward_counter_classifies_alone(self) -> None:
        """D-RI12: nothing at all flows the declared way, so reverse stands."""
        consumer = _node("C", primary=_SHARED)
        producer = _node("P", inputs=[{"name": "in", "description": _SHARED}])
        verdict = classify_edge(consumer, producer, None, {})
        assert any("S3 reverse with zero counter" in s for s in _texts(verdict))

    def test_reverse_lean_with_some_forward_flow_is_uncorroborated(self) -> None:
        """The arm that classifies nothing: a lean, recorded as a note only."""
        consumer = _node(
            "C", primary=_SHARED, inputs=[{"name": "x", "description": "alpha"}]
        )
        producer = _node(
            "P", primary="alpha", inputs=[{"name": "y", "description": _SHARED}]
        )
        verdict = classify_edge(consumer, producer, None, {})
        texts = _texts(verdict)
        assert any("uncorroborated, not classified" in s for s in texts)

    def test_the_constants_are_the_documented_ones(self) -> None:
        assert (S3_FLOOR, S3_DOMINANCE) == (4, 2)


# ---------------------------------------------------------------------------
# S1 / S2 trigger matching
# ---------------------------------------------------------------------------


class TestTriggerMatching:
    def test_s1_fires_when_the_trigger_awaits_the_producer_by_name(self) -> None:
        consumer = _node("C", trigger="after Ruleset Builder completes")
        producer = _node("Ruleset Builder", primary="ruleset")
        verdict = classify_edge(consumer, producer, None, {})
        assert any("S1 trigger awaits" in s for s in _texts(verdict))

    def test_s2_selective_vision_feature_fires_under_the_link_cap(self) -> None:
        """The prod_map-less fallback: the vision feature must be selective."""
        consumer = _node("C", trigger="once payment reconciliation is complete")
        producer = _node("P", primary="ledger", linked=["payment reconciliation"])
        verdict = classify_edge(consumer, producer, None, {"payment_reconciliation": 1})
        assert any("(selective)" in s for s in _texts(verdict))

    def test_s2_is_skipped_when_the_vision_feature_is_too_widely_linked(self) -> None:
        consumer = _node("C", trigger="once payment reconciliation is complete")
        producer = _node("P", primary="ledger", linked=["payment reconciliation"])
        verdict = classify_edge(
            consumer, producer, None, {"payment_reconciliation": 99}
        )
        assert not any("(selective)" in s for s in _texts(verdict))


# ---------------------------------------------------------------------------
# brainstormer._feature_names
# ---------------------------------------------------------------------------


class TestFeatureNamesGuards:
    def test_a_non_dict_vision_statement_yields_no_names(self) -> None:
        assert _feature_names({"vision_statement": "not a dict"}) == []

    def test_a_non_dict_vision_yields_no_names(self) -> None:
        assert _feature_names("not a dict") == []


def _texts(verdict: Any) -> list[str]:
    """Every string in whatever shape classify_edge returns."""
    out: list[str] = []

    def walk(x: Any) -> None:
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple, set)):
            for v in x:
                walk(v)

    walk(verdict)
    return out
