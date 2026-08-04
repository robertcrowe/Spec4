"""Unit tests for the assembly-time requires reconciler (D-RC series).

Synthetic nodes mirror the calibrated D-RI shapes: the analyzer/validator
inversion (an edge recorded in the feedback direction), the supported build
edge, and the conflicting/mutual shapes the reconciler must never touch.
Signal-mechanics coverage (S1/S1b/S2/S3 internals) lives with the probe's
tests in ``evals/phaser/test_requires_inversion.py``, which import the same
core; these tests cover the *reconciliation* semantics — what flips, what
doesn't, ordering, cycle reversion, and the record contract.
"""

from __future__ import annotations

from typing import Any

from spec4.agentifier.requires_reconciler import (
    build_production_map,
    reconcile_requires,
)


def _node(
    name: str,
    *,
    requires: list[str] | None = None,
    trigger: str = "",
    inputs: list[dict[str, Any]] | None = None,
    outputs_primary: str = "",
    linked: list[str] | None = None,
    kind: str = "feature",
) -> dict[str, Any]:
    slugged = name.lower().replace(" ", "_")
    return {
        "id": slugged,
        "name": name,
        "kind": kind,
        "requires": requires or [],
        "linked_vision_features": linked or [],
        "invocation": {"trigger": trigger, "mode": "synchronous"},
        "inputs": inputs or [],
        "outputs": {"primary": outputs_primary, "format": "JSON", "schema_notes": None},
    }


def _requires_of(features: list[dict[str, Any]], name: str) -> list[str]:
    for f in features:
        if f["name"] == name:
            return list(f.get("requires") or [])
    raise AssertionError(f"node {name!r} not found")


# --- the flip: analyzer/validator inversion shape ------------------------------


def _inversion_pair() -> list[dict[str, Any]]:
    """Builder requires analyzer, but the analyzer consumes the builder (S1)."""
    builder = _node(
        "slide_content_synthesis",
        requires=["deck_tone_alignment"],
        trigger="completion of all specialist analysis chains",
        inputs=[{"name": "analysis_bundle", "description": "specialist analyses"}],
        outputs_primary="a complete slide-by-slide investor pitch deck",
    )
    analyzer = _node(
        "deck_tone_alignment",
        trigger="on demand",
        inputs=[
            {
                "name": "assembled_deck",
                "description": "the deck from slide_content_synthesis",
            }
        ],
        outputs_primary="a tone and voice consistency assessment",
    )
    return [builder, analyzer]


def test_inversion_edge_flips_and_is_recorded() -> None:
    features = _inversion_pair()
    records = reconcile_requires(features, None)
    # Edge now points in the build direction: analyzer requires builder.
    assert _requires_of(features, "slide_content_synthesis") == []
    assert _requires_of(features, "deck_tone_alignment") == ["slide_content_synthesis"]
    # Record keys the *declared* (pre-flip) edge (D-RC1 C).
    assert records == [
        {
            "from": "slide_content_synthesis",
            "to": "deck_tone_alignment",
            "direction": "flipped",
            "signals": ["S1 inputs name 'slide_content_synthesis'"],
        }
    ]


def test_flip_does_not_duplicate_existing_reverse_edge() -> None:
    features = _inversion_pair()
    features[1]["requires"] = ["slide_content_synthesis"]  # reverse already declared
    reconcile_requires(features, None)
    assert _requires_of(features, "deck_tone_alignment") == ["slide_content_synthesis"]


# --- edges the reconciler must never touch -------------------------------------


def test_supported_edge_untouched() -> None:
    research = _node(
        "market_research_synthesis",
        trigger="on founder idea submission",
        inputs=[{"name": "founder_idea", "description": "the raw idea"}],
        outputs_primary="a market landscape brief",
    )
    narrative = _node(
        "narrative_arc_generation",
        requires=["market_research_synthesis"],
        trigger="after specialist chains complete",
        inputs=[{"name": "market_research_output", "description": "the brief"}],
        outputs_primary="a narrative arc",
    )
    features = [research, narrative]
    records = reconcile_requires(features, None)
    assert records == []
    assert _requires_of(features, "narrative_arc_generation") == [
        "market_research_synthesis"
    ]


def test_conflicting_edge_untouched() -> None:
    a = _node(
        "draft_generation",
        requires=["style_review"],
        trigger="on demand",
        inputs=[{"name": "style_notes", "description": "notes from style_review"}],
        outputs_primary="a draft document",
    )
    b = _node(
        "style_review",
        trigger="on demand",
        inputs=[{"name": "draft_text", "description": "text from draft_generation"}],
        outputs_primary="style review notes",
    )
    features = [a, b]
    records = reconcile_requires(features, None)
    assert records == []
    assert _requires_of(features, "draft_generation") == ["style_review"]


def test_no_evidence_edge_untouched() -> None:
    a = _node("alpha_step", requires=["beta_step"], outputs_primary="alpha artifact")
    b = _node("beta_step", outputs_primary="beta artifact")
    features = [a, b]
    records = reconcile_requires(features, None)
    assert records == []
    assert _requires_of(features, "alpha_step") == ["beta_step"]


def test_infra_and_unresolved_and_self_edges_skipped() -> None:
    f = _node(
        "retrieval_answering",
        requires=["vector_index", "nonexistent_thing", "retrieval_answering"],
        outputs_primary="an answer",
    )
    infra = _node("vector_index", kind="infrastructure", outputs_primary="an index")
    features = [f, infra]
    records = reconcile_requires(features, None)
    assert records == []
    assert _requires_of(features, "retrieval_answering") == [
        "vector_index",
        "nonexistent_thing",
        "retrieval_answering",
    ]


def test_empty_features_no_records() -> None:
    assert reconcile_requires([], None) == []


# --- cycle reversion (D-RC2 a / D-RC7 A) ---------------------------------------


def test_cycle_creating_flip_reverted_and_recorded() -> None:
    # Declared: builder -> analyzer (inversion candidate), plus an untouched
    # NO-EVIDENCE path builder -> mid -> analyzer. Flipping the candidate
    # (analyzer requires builder) closes analyzer -> builder -> mid -> analyzer.
    builder, analyzer = _inversion_pair()
    builder["requires"] = ["deck_tone_alignment", "mid_step"]
    mid = _node(
        "mid_step",
        requires=["deck_tone_alignment"],
        outputs_primary="an intermediate artifact",
    )
    features = [builder, analyzer, mid]
    records = reconcile_requires(features, None)
    assert records == [
        {
            "from": "slide_content_synthesis",
            "to": "deck_tone_alignment",
            "direction": "reverted-cycle",
            "signals": ["S1 inputs name 'slide_content_synthesis'"],
        }
    ]
    # Graph byte-identical to the declared state.
    assert _requires_of(features, "slide_content_synthesis") == [
        "deck_tone_alignment",
        "mid_step",
    ]
    assert _requires_of(features, "deck_tone_alignment") == []
    assert _requires_of(features, "mid_step") == ["deck_tone_alignment"]


def test_flips_apply_in_sorted_order() -> None:
    # Two independent inversions; records come back sorted by (from, to)
    # regardless of node list order (D-RC7 A determinism).
    b1, a1 = _inversion_pair()
    b2 = _node(
        "zeta_composer",
        requires=["zeta_checker"],
        trigger="on demand",
        inputs=[{"name": "raw_material", "description": "raw input"}],
        outputs_primary="a composed zeta artifact",
    )
    a2 = _node(
        "zeta_checker",
        trigger="on demand",
        inputs=[{"name": "composed_output", "description": "from zeta_composer"}],
        outputs_primary="a zeta compliance assessment",
    )
    features = [b2, a2, b1, a1]  # deliberately unsorted
    records = reconcile_requires(features, None)
    assert [(r["from"], r["to"]) for r in records] == [
        ("slide_content_synthesis", "deck_tone_alignment"),
        ("zeta_composer", "zeta_checker"),
    ]
    assert all(r["direction"] == "flipped" for r in records)


# --- production map (D-RC3 A) --------------------------------------------------


def test_production_map_reshaped_signature() -> None:
    spec = {
        "id": "deck_build",
        "outputs": {"primary": "a complete slide-by-slide investor pitch deck"},
    }
    maker = _node(
        "slide_content_synthesis",
        outputs_primary="a complete slide-by-slide investor pitch deck",
        linked=["Deck_Build"],
    )
    other = _node(
        "deck_tone_alignment",
        outputs_primary="a tone and voice consistency assessment",
        linked=["Deck_Build"],
    )
    assert build_production_map([spec], [maker, other]) == {
        "deck_build": "slide_content_synthesis"
    }
    assert build_production_map([], [maker, other]) is None


def test_s2_production_map_drives_flip_with_feature_specs() -> None:
    # The calibrated Decksmith shape: membership saturates (both nodes link
    # Deck_Build) so the fallback gate is silent, but the production map
    # resolves the producer and S2 fires in reverse -> flip.
    builder = _node(
        "slide_content_synthesis",
        requires=["deck_tone_alignment"],
        trigger="completion of all specialist analysis chains",
        inputs=[{"name": "analysis_bundle", "description": "specialist analyses"}],
        outputs_primary="a complete slide-by-slide investor pitch deck",
        linked=["Deck_Build"],
    )
    analyzer = _node(
        "deck_tone_alignment",
        trigger="after deck_build completes",
        inputs=[{"name": "deck_content", "description": "the assembled deck"}],
        outputs_primary="a tone and voice consistency assessment",
        linked=["Deck_Build"],
    )
    feature_specs = {
        "features": [
            {
                "id": "deck_build",
                "outputs": {
                    "primary": "a complete slide-by-slide investor pitch deck"
                },
            }
        ]
    }
    features = [builder, analyzer]
    records = reconcile_requires(features, feature_specs)
    assert len(records) == 1
    assert records[0]["direction"] == "flipped"
    assert records[0]["signals"] == [
        "S2 trigger awaits completion of produced feature 'deck_build'"
    ]
    assert _requires_of(features, "deck_tone_alignment") == ["slide_content_synthesis"]
    assert _requires_of(features, "slide_content_synthesis") == []
