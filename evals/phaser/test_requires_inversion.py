"""Unit tests for the requires-inversion probe (dev tooling, D-RI series).

Synthetic nodes model the two confirmed Decksmith inversion shapes, the
Haggler non-inversion shape, and the D-RI8/9/10 matcher mechanics. Real-draw
calibration happens against saved draw directories, not here.
"""

from __future__ import annotations

from typing import Any

from requires_inversion import (  # noqa: E402  (evals/ is a script dir, not a package)
    CONFLICTING,
    INVERSION,
    NO_EVIDENCE,
    SUPPORTED,
    _stem_prefix_match,
    _tokens,
    build_production_map,
    classify_draw,
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


def _draw(
    nodes: list[dict[str, Any]],
    specs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "ai_features": {"ai_features": nodes},
        "feature_specs": {"features": specs} if specs else None,
        "stack": None, "manifest": None, "phases": [],
    }


def _classes(draw: dict[str, Any]) -> dict[tuple[str, str], str]:
    res = classify_draw(draw)
    return {(e["consumer"], e["producer"]): e["class"] for e in res["edges"]}


# --- the two Decksmith inversion shapes ---------------------------------------


def test_s2_fallback_gate_inversion() -> None:
    """Tone-alignment shape: trigger names the product feature, not the node.

    No feature_specs -> S2 runs on the selectivity gate; deck_build is linked
    by one node, so the bridge counts.
    """
    synthesis = _node(
        "slide_content_synthesis",
        requires=["deck_tone_and_voice_alignment"],  # declared backwards
        trigger="completion of all specialist analysis chains",
        inputs=[{"name": "analysis_bundle", "description": "specialist analyses"}],
        outputs_primary="a complete, slide-by-slide pitch deck",
        linked=["deck_build"],
    )
    tone = _node(
        "deck_tone_and_voice_alignment",
        trigger="after deck_build completes",
        inputs=[{"name": "deck_content", "description": "the assembled deck"}],
        outputs_primary="a tone and voice consistency assessment",
    )
    cls = _classes(_draw([synthesis, tone]))
    assert cls[("slide_content_synthesis", "deck_tone_and_voice_alignment")] == INVERSION


def test_s3_reverse_lean_annotated_not_inverted() -> None:
    """Reverse-dominant S3 alone is a lean, not an INVERSION (D-RI11)."""
    model = _node(
        "financial_model_generation",
        requires=["growth_assumption_validation"],  # declared backwards
        trigger="on request from the founder workspace",
        inputs=[{"name": "company_metrics",
                 "description": "historical metrics and assumption plausibility notes"}],
        outputs_primary="financial projections with growth assumption schedule",
    )
    validation = _node(
        "growth_assumption_validation",
        trigger="when projections are ready",
        inputs=[{
            "name": "growth_assumptions",
            "description": "growth assumptions from financial projections",
        }],
        outputs_primary="a plausibility check on assumption schedules",
    )
    res = classify_draw(_draw([model, validation]))
    (edge,) = res["edges"]
    assert edge["class"] == NO_EVIDENCE
    assert any("reverse lean" in n for n in edge["notes"])


# --- the Haggler non-inversion shape ------------------------------------------


def test_supported_edge_stays_supported() -> None:
    interp = _node(
        "negotiation_protocol_interpretation",
        trigger="when a negotiation session opens",
        inputs=[{"name": "protocol_document", "description": "the raw protocol"}],
        outputs_primary="a structured negotiation protocol interpretation",
    )
    buyer = _node(
        "buyer_assistant_negotiation",
        requires=["negotiation_protocol_interpretation"],  # genuine dependency
        trigger="after negotiation_protocol_interpretation produces the ruleset",
        inputs=[{
            "name": "protocol_interpretation",
            "description": "structured negotiation protocol interpretation",
        }],
        outputs_primary="buyer-side negotiation moves",
    )
    cls = _classes(_draw([interp, buyer]))
    assert cls[("buyer_assistant_negotiation",
                "negotiation_protocol_interpretation")] == SUPPORTED


# --- D-RI8: S2 selectivity gate and production map ----------------------------


def test_s2_gate_silences_saturated_vision_feature() -> None:
    """A vision feature linked by 3 nodes carries no directional information."""
    a = _node("alpha", requires=["beta"], trigger="after deck_build completes",
              linked=["deck_build"])
    b = _node("beta", trigger="after deck_build completes", linked=["deck_build"])
    c = _node("gamma", trigger="on schedule", linked=["deck_build"])
    res = classify_draw(_draw([a, b, c]))
    (edge,) = res["edges"]
    assert edge["class"] == NO_EVIDENCE
    assert edge["fwd"] == [] and edge["rev"] == []


def test_s2_production_map_beats_saturation() -> None:
    """With feature_specs, the producer resolves even when membership saturates."""
    spec = {
        "id": "deck_build",
        "purpose": "generate a complete investor pitch deck",
        "outputs": {"primary": "a complete slide-by-slide investor pitch deck"},
    }
    synthesis = _node(
        "slide_content_synthesis",
        requires=["deck_tone_and_voice_alignment"],
        trigger="completion of all specialist analysis chains",
        inputs=[{"name": "analysis_bundle", "description": "specialist analyses"}],
        outputs_primary="a complete slide-by-slide investor pitch deck",
        linked=["Deck_Build"],
    )
    tone = _node(
        "deck_tone_and_voice_alignment",
        trigger="after deck_build completes",
        inputs=[{"name": "deck_content", "description": "the assembled deck"}],
        outputs_primary="a tone and voice consistency assessment",
        linked=["Deck_Build"],  # membership saturated: both nodes link it
    )
    draw = _draw([synthesis, tone], specs=[spec])
    pm = build_production_map(draw)
    assert pm == {"deck_build": "slide_content_synthesis"}
    cls = _classes(draw)
    assert cls[("slide_content_synthesis", "deck_tone_and_voice_alignment")] == INVERSION


def test_production_map_ambiguous_gets_no_entry() -> None:
    """Two linked nodes with equal-overlap outputs -> conservative no producer."""
    spec = {
        "id": "deck_build",
        "purpose": "generate the investor pitch deck",
        "outputs": {"primary": "a complete investor pitch deck"},
    }
    a = _node("a_maker", outputs_primary="a complete investor pitch deck",
              linked=["deck_build"])
    b = _node("b_maker", outputs_primary="a complete investor pitch deck",
              linked=["deck_build"])
    pm = build_production_map(_draw([a, b], specs=[spec]))
    assert pm == {}


# --- D-RI9: input-name stems ---------------------------------------------------


def test_s1b_input_stem_supports_declared_direction() -> None:
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
    cls = _classes(_draw([research, narrative]))
    assert cls[("narrative_arc_generation", "market_research_synthesis")] == SUPPORTED


def test_stem_prefix_match_mechanics() -> None:
    assert _stem_prefix_match("market_research_output", "market_research_synthesis")
    assert _stem_prefix_match("financial_modeling_output", "financial_model_generation")
    assert not _stem_prefix_match("output", "market_research_synthesis")
    assert not _stem_prefix_match("question", "question_intent_classification")
    assert not _stem_prefix_match("deck_content", "slide_content_synthesis")


# --- D-RI10: asymmetry mechanics ----------------------------------------------


def test_s3_mutual_near_tie_yields_no_direction() -> None:
    """Both directions overlap heavily (revision loop) -> no directional S3."""
    a = _node(
        "builder",
        requires=["auditor"],
        trigger="on request",
        inputs=[{"name": "audit_findings",
                 "description": "coverage gaps ranked findings remediation plan"}],
        outputs_primary="assembled artifact bundle with manifest inventory ledger",
    )
    b = _node(
        "auditor",
        trigger="on request",
        inputs=[{"name": "artifact_bundle",
                 "description": "assembled artifact bundle manifest inventory ledger"}],
        outputs_primary="coverage gaps ranked findings remediation plan",
    )
    res = classify_draw(_draw([a, b]))
    (edge,) = res["edges"]
    assert edge["class"] == NO_EVIDENCE
    assert any("mutual" in n for n in edge["notes"])


def test_s3_below_floor_annotated_not_classified() -> None:
    a = _node(
        "alpha", requires=["beta"], trigger="on user action",
        inputs=[{"name": "widget_config", "description": "widget settings"}],
        outputs_primary="a rendered widget",
    )
    b = _node(
        "beta", trigger="on schedule",
        inputs=[{"name": "widget_stream", "description": "incoming stream"}],
        outputs_primary="a digest email",
    )
    res = classify_draw(_draw([a, b]))
    (edge,) = res["edges"]
    assert edge["class"] == NO_EVIDENCE
    assert any("below floor" in n for n in edge["notes"])


def test_conflicting_when_both_directions_fire() -> None:
    a = _node(
        "a_step", requires=["b_step"], trigger="after b_step completes",
        outputs_primary="the a artifact",
    )
    b = _node(
        "b_step", trigger="after a_step completes",
        outputs_primary="the b artifact",
    )
    cls = _classes(_draw([a, b]))
    assert cls[("a_step", "b_step")] == CONFLICTING


# --- edge universe (D-RI2) and resolution --------------------------------------


def test_infra_edges_skipped_and_counted() -> None:
    feat = _node(
        "retrieval_answering", requires=["Vector Index"], trigger="on user question",
        inputs=[{"name": "question", "description": "the user question"}],
        outputs_primary="an answer",
    )
    infra = _node("Vector Index", kind="infrastructure")
    res = classify_draw(_draw([feat, infra]))
    assert res["edges"] == []
    assert res["skipped_infra"] == 1


def test_unresolved_endpoint_surfaced() -> None:
    feat = _node("solo", requires=["ghost_node"])
    res = classify_draw(_draw([feat]))
    assert res["edges"] == []
    assert res["unresolved"] == [("solo", "ghost_node")]


def test_requires_resolves_via_slug_fallback() -> None:
    producer = _node("Fancy Producer", outputs_primary="the fancy artifact")
    consumer = _node(
        "consumer_node",
        requires=["fancy_producer"],  # slug form, not the display name
        trigger="after Fancy Producer completes",
        inputs=[{"name": "fancy_artifact", "description": "the fancy artifact"}],
    )
    cls = _classes(_draw([producer, consumer]))
    assert cls[("consumer_node", "Fancy Producer")] == SUPPORTED


# --- tokenizer -----------------------------------------------------------------


def test_tokens_stopword_and_suffix_norm() -> None:
    assert "content" not in _tokens("deck_content")
    assert "deck" in _tokens("deck_content")
    assert _tokens("growth projections") == _tokens("growth projection")
    assert _tokens("financial modeling") == _tokens("financial model")


def test_s2_participation_mention_does_not_fire() -> None:
    """'Called by deck_build' is participation, not consumption (D-RI8)."""
    spec = {
        "id": "deck_build",
        "purpose": "generate a complete investor pitch deck",
        "outputs": {"primary": "a complete slide-by-slide investor pitch deck"},
    }
    synthesis = _node(
        "slide_content_synthesis",
        requires=["specialist_stage"],
        trigger="completion of all specialist chains",
        outputs_primary="a complete slide-by-slide investor pitch deck",
        linked=["Deck_Build"],
    )
    specialist = _node(
        "specialist_stage",
        trigger="Called by Deck_Build orchestrator when this phase is reached",
        outputs_primary="a specialist analysis brief",
        linked=["Deck_Build"],
    )
    res = classify_draw(_draw([synthesis, specialist], specs=[spec]))
    (edge,) = res["edges"]
    assert edge["rev"] == []  # specialist mentions deck_build but consumes nothing


def test_s1_participation_trigger_does_not_fire() -> None:
    """A member's trigger naming its invoking coordinator is not consumption."""
    coord = _node(
        "thread_summarization",
        requires=["action_item_extraction"],  # coordinator consumes member
        trigger="user selects a thread and requests a summary",
        inputs=[{"name": "email_thread", "description": "the raw thread"}],
        outputs_primary="a structured thread summary",
    )
    member = _node(
        "action_item_extraction",
        trigger="Called by Thread_Summarization during summary generation",
        inputs=[{"name": "parsed_messages", "description": "parsed messages"}],
        outputs_primary="extracted action items with owners",
    )
    res = classify_draw(_draw([coord, member]))
    (edge,) = res["edges"]
    assert edge["rev"] == []  # participation mention must not invert


def test_s3_zero_counter_classifies_inversion() -> None:
    """Reverse S3 with zero forward overlap classifies alone (D-RI12)."""
    qa = _node(
        "policy_qa",
        requires=["answer_confidence_scoring"],  # declared backwards
        trigger="employee submits a question",
        inputs=[{"name": "question", "description": "the employee question"}],
        outputs_primary="a grounded answer with a source citation to the policy section",
    )
    scoring = _node(
        "answer_confidence_scoring",
        trigger="before the answer is presented",
        inputs=[{"name": "candidate_answer",
                 "description": "grounded answer with source citation to the policy section"}],
        outputs_primary="a confidence assessment",
    )
    cls = _classes(_draw([qa, scoring]))
    assert cls[("policy_qa", "answer_confidence_scoring")] == INVERSION
