"""Unit tests for ``_feature_specs_for_stack`` — the product-feature spine block
StackAdvisor receives (D-SC1 / D-SC6 / D-SC7).

The spine is StackAdvisor's *base* input: one behavioural block per MVP feature,
AI and non-AI alike, so non-AI features stop being handled only by unattributed
defaults. The AI catalog is enrichment on the AI subset, so a feature that also
exists as an AI-catalog node is tagged ``(AI)`` (D-SC7 — the product signal comes
from this direct, de-duped spine, not from per-node ``vision_grounding``).
``entities`` are surfaced as an advisory data model (D-SC6), never a deterministic
store mapping.

Pure rendering assertions; whether the live model then frames the stack correctly
is an in-app behavioural draw, not asserted here.
"""

from __future__ import annotations

from typing import Any

from spec4.agents._utils import _feature_specs_for_stack, slug

_HEAD = "Feature specifications (from Brainstormer)"
_VOCAB = "Domain vocabulary"


def _specs(*features: dict[str, Any], nfr: list[str] | None = None) -> dict[str, Any]:
    return {"features": list(features), "nfr_goals": nfr or []}


def _catalog(*served_ids: str) -> dict[str, Any]:
    """AI catalog whose nodes *serve* the given product ids via vision_grounding.

    An AI node's own id is a capability-surface id (e.g. ``x_capability``) — never
    the product-feature id it serves. The serves relation is the join key, so the
    fixture mirrors that: each node has a distinct surface id and points at the
    product feature it serves through ``vision_grounding.served_features``.
    """
    return {
        "ai_features": [
            {
                "id": f"{fid}_capability",
                "name": f"{fid}_capability",
                "tier": "single_call",
                "vision_grounding": {"served_features": [{"id": fid, "name": fid}]},
            }
            for fid in served_ids
        ]
    }


def _feature(fid: str, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"id": fid, "purpose": f"purpose of {fid}"}
    base.update(extra)
    return base


# --- empty / absent --------------------------------------------------------


def test_no_specs_returns_empty() -> None:
    assert _feature_specs_for_stack(None) == ""
    assert _feature_specs_for_stack({"features": []}) == ""


# --- every feature is rendered (AI and non-AI) -----------------------------


def test_both_ai_and_non_ai_features_rendered() -> None:
    out = _feature_specs_for_stack(
        _specs(_feature("semantic_search"), _feature("saved_items")),
        _catalog("semantic_search"),
    )
    assert _HEAD in out
    assert "`semantic_search`" in out
    assert "`saved_items`" in out
    assert "purpose of saved_items" in out


# --- AI subset is tagged, non-AI is not (join by serves relation) ----------


def test_ai_feature_tagged_non_ai_untagged() -> None:
    out = _feature_specs_for_stack(
        _specs(_feature("semantic_search"), _feature("saved_items")),
        _catalog("semantic_search"),
    )
    assert "`semantic_search` (AI)" in out
    assert "`saved_items` (AI)" not in out
    assert "`saved_items`" in out


def test_identity_without_serves_relation_does_not_tag() -> None:
    # regression: a node whose *own id* equals the product id but which serves it
    # via NO vision_grounding must not tag — the join is the serves relation, not
    # identity (an AI node's id is a capability surface id, never a product id).
    catalog = {
        "ai_features": [
            {"id": "saved_items", "name": "saved_items", "tier": "single_call"}
        ]
    }
    out = _feature_specs_for_stack(_specs(_feature("saved_items")), catalog)
    assert "`saved_items` (AI)" not in out


def test_no_catalog_tags_nothing() -> None:
    out = _feature_specs_for_stack(_specs(_feature("saved_items")), None)
    # the header explains the (AI) tag, so assert on the feature heading itself
    assert "`saved_items` (AI)" not in out


def test_infra_catalog_nodes_never_tag() -> None:
    # even an infra node that names a served feature must not tag it
    catalog = {
        "ai_features": [
            {
                "id": "vector_index",
                "name": "vector_index",
                "kind": "infrastructure",
                "vision_grounding": {"served_features": [{"id": "saved_items"}]},
            }
        ]
    }
    out = _feature_specs_for_stack(_specs(_feature("saved_items")), catalog)
    assert "`saved_items` (AI)" not in out


# --- dependencies (chain signal, distinct from AI requires DAG) ------------


def test_dependencies_rendered() -> None:
    out = _feature_specs_for_stack(
        _specs(_feature("report", dependencies=["orders", "customers"])),
        None,
    )
    assert "depends on: orders, customers" in out


def test_no_dependencies_line_when_absent() -> None:
    out = _feature_specs_for_stack(_specs(_feature("saved_items")), None)
    assert "depends on:" not in out


# --- entities as advisory data model (D-SC6), de-duped ---------------------


def test_entities_surface_as_domain_vocabulary() -> None:
    out = _feature_specs_for_stack(
        _specs(
            _feature("saved_items", entities=["SavedItem", "Tag"]),
            _feature("export", entities=["SavedItem", "Report"]),
        ),
        None,
    )
    assert _VOCAB in out
    # union, de-duped, order preserved
    assert "SavedItem, Tag, Report" in out
    # persistence signal framing present, mechanism left to StackAdvisor
    assert "persistence signal" in out


def test_no_vocabulary_block_without_entities() -> None:
    out = _feature_specs_for_stack(_specs(_feature("saved_items")), None)
    assert _VOCAB not in out


# --- behavioural fields flow through render_feature_block ------------------


def test_behavioural_fields_rendered() -> None:
    out = _feature_specs_for_stack(
        _specs(
            _feature(
                "saved_items",
                invocation={"trigger": "user taps save"},
                outputs={"primary": "a persisted item", "format": "record"},
                success_criteria=["the item survives a restart"],
            )
        ),
        None,
    )
    assert "user taps save" in out
    assert "the item survives a restart" in out


# --- non-functional goals keyed by nfr_<slug> (D-SC2) ----------------------

_NFR_HEAD = "Non-functional goals (project-wide)"


def test_nfr_goals_rendered_with_slug_keys() -> None:
    goals = [
        "Saved data persists reliably across app sessions and device restarts.",
        "Fare lookups complete quickly.",
    ]
    out = _feature_specs_for_stack(_specs(_feature("saved_items"), nfr=goals), None)
    assert _NFR_HEAD in out
    for g in goals:
        key = f"nfr_{slug(g.strip())}"
        # the exact key the probe derives must appear, alongside the goal text
        assert f"`{key}`: {g}" in out


def test_nfr_key_uses_shared_slug_derivation() -> None:
    goal = "Results return in sub-second time, every time!"
    out = _feature_specs_for_stack(_specs(_feature("x"), nfr=[goal]), None)
    assert f"`nfr_{slug(goal)}`" in out


def test_no_nfr_block_when_absent() -> None:
    out = _feature_specs_for_stack(_specs(_feature("saved_items")), None)
    assert _NFR_HEAD not in out


def test_nfr_block_present_even_with_no_ai() -> None:
    # no-AI path: nfr goals still render (they drive non-AI stacks too)
    out = _feature_specs_for_stack(
        _specs(_feature("fare_lookup"), nfr=["The fare table is accurate."]),
        {"ai_features": []},
    )
    assert _NFR_HEAD in out
    assert "`fare_lookup` (AI)" not in out


# --- D-SC14: the product ids the linkage rules name are on the wire ----------


def test_product_feature_id_is_rendered_in_header() -> None:
    out = _feature_specs_for_stack(
        _specs({"id": "adaptive_investigation", "name": "Adaptive_Investigation"}), {}
    )
    assert "id: `adaptive_investigation`" in out


def test_id_rendered_alongside_ai_tag() -> None:
    out = _feature_specs_for_stack(
        _specs({"id": "findings_write_up", "name": "Findings_Write_Up"}),
        _catalog("findings_write_up"),
    )
    assert "### `Findings_Write_Up` — id: `findings_write_up` (AI)" in out


def test_id_rendered_for_non_ai_feature() -> None:
    out = _feature_specs_for_stack(
        _specs({"id": "fare_lookup", "name": "Fare_Lookup"}), {}
    )
    assert "### `Fare_Lookup` — id: `fare_lookup`" in out
    # "(AI)" appears in the block preamble prose; assert on the header line.
    assert "### `Fare_Lookup` — id: `fare_lookup` (AI)" not in out


def test_missing_id_renders_name_only_without_dangling_label() -> None:
    out = _feature_specs_for_stack(_specs({"name": "Nameless"}), {})
    assert "### `Nameless`" in out
    assert "id: ``" not in out
    assert "— id:" not in out
