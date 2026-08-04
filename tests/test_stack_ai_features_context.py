"""Unit tests for ``_ai_features_for_stack`` — the AI-features context block
StackAdvisor receives.

This is the tier-agnostic per-feature stack-driving projection (D-SA1(c)) plus
the required-infrastructure section (D-SA2). It replaced a tier-histogram +
boolean-hint summary that carried two proven defects, both retired here by
deleting the hint layer (D-SA3(a)):

* DEFECT-1 — a phantom "LLM-backed" instruction emitted on catalogs with zero
  generative features, because infrastructure nodes' sentinel tier defaulted to
  the ``single_call`` order.
* DEFECT-2 — an embeddings feature's vector substrate never surfaced, because
  the vector-store hint gated above the ``embeddings`` tier (the D-PS5b
  mechanism).

These are pure rendering assertions; whether the live model then frames the
stack correctly is an in-app behavioral draw, not asserted here.
"""

from __future__ import annotations

from typing import Any

from spec4.agents._utils import _ai_features_for_stack

_PHANTOM = "provider/client library"
_NEW_TAG = "NEW this revision"
_INFRA_HEAD = "Required infrastructure"


def _spec(*features: dict[str, Any]) -> dict[str, Any]:
    return {"ai_features": list(features), "cross_cutting": {}}


def _infra(name: str) -> dict[str, Any]:
    return {"name": name, "kind": "infrastructure", "tier": "infrastructure"}


# --- no phantom LLM instruction (DEFECT-1 retired) --------------------------


def test_embeddings_with_infra_omits_phantom_llm_line() -> None:
    out = _ai_features_for_stack(
        _spec(
            {"name": "emb", "tier": "embeddings", "requires": ["vector_index"]},
            _infra("vector_index"),
        )
    )
    assert _PHANTOM not in out


def test_deterministic_only_omits_phantom_llm_line() -> None:
    out = _ai_features_for_stack(_spec({"name": "clf", "tier": "deterministic"}))
    assert _PHANTOM not in out


# --- per-feature projection is tier-agnostic (D-SA1(c)) ---------------------


def test_deterministic_feature_surfaces_knowledge_source() -> None:
    out = _ai_features_for_stack(
        _spec(
            {
                "name": "digest",
                "tier": "deterministic",
                "invocation": {"mode": "scheduled"},
                "knowledge_sources": [
                    {"name": "orders_db", "type": "relational_db"}
                ],
            }
        )
    )
    assert "knowledge source: orders_db (relational_db)" in out
    assert "invocation: scheduled" in out


def test_feature_surfaces_tool_access_detail() -> None:
    out = _ai_features_for_stack(
        _spec(
            {
                "name": "agent",
                "tier": "tool_agent",
                "tool_access": {
                    "capabilities_needed": [
                        {
                            "purpose": "flight search",
                            "source": "existing_third_party_mcp",
                            "protocol": "mcp",
                            "mcp_server": "flights.example",
                        }
                    ]
                },
            }
        )
    )
    assert "tool access: flight search" in out
    assert "protocol=mcp" in out
    assert "server=flights.example" in out


def test_feature_surfaces_mechanisms() -> None:
    out = _ai_features_for_stack(
        _spec(
            {
                "name": "search",
                "tier": "rag",
                "mechanisms": [{"name": "retrieval_reranking"}],
            }
        )
    )
    assert "mechanisms: retrieval_reranking" in out


# --- required-infrastructure section (D-SA2, DEFECT-2 retired) --------------


def test_infra_section_surfaces_vector_substrate() -> None:
    out = _ai_features_for_stack(
        _spec(
            {
                "name": "emb",
                "tier": "embeddings",
                "requires": ["embedding_pipeline", "vector_index"],
            },
            _infra("embedding_pipeline"),
            _infra("vector_index"),
        )
    )
    assert _INFRA_HEAD in out
    assert "vector_index" in out
    assert "embedding_pipeline" in out


def test_infra_section_maps_consumers() -> None:
    out = _ai_features_for_stack(
        _spec(
            {"name": "emb", "tier": "embeddings", "requires": ["vector_index"]},
            _infra("vector_index"),
        )
    )
    assert "vector_index — required by: emb" in out


def test_no_infra_section_when_no_infra_nodes() -> None:
    out = _ai_features_for_stack(_spec({"name": "gen", "tier": "single_call"}))
    assert _INFRA_HEAD not in out


# --- newly-introduced-this-revision tagging ---------------------------------


def test_newly_introduced_tagged_in_revision() -> None:
    out = _ai_features_for_stack(
        _spec(
            {"name": "talk", "tier": "single_call", "introduced_in_version": 1},
            {"name": "sig", "tier": "deterministic", "introduced_in_version": 1},
        ),
        current_version=1,
    )
    assert f"**talk** (single_call) — {_NEW_TAG}" in out
    assert f"**sig** (deterministic) — {_NEW_TAG}" in out
    assert "not yet implemented in the carried-forward stack" in out.lower()


def test_carried_forward_feature_not_tagged_new() -> None:
    out = _ai_features_for_stack(
        _spec({"name": "old", "tier": "single_call", "introduced_in_version": 0}),
        current_version=1,
    )
    assert _NEW_TAG not in out


def test_only_current_version_features_tagged() -> None:
    out = _ai_features_for_stack(
        _spec(
            {"name": "old", "tier": "single_call", "introduced_in_version": 0},
            {"name": "new", "tier": "single_call", "introduced_in_version": 1},
        ),
        current_version=1,
    )
    assert f"**new** (single_call) — {_NEW_TAG}" in out
    assert f"**old** (single_call) — {_NEW_TAG}" not in out


def test_greenfield_version_zero_tags_nothing_new() -> None:
    out = _ai_features_for_stack(
        _spec({"name": "gen", "tier": "single_call", "introduced_in_version": 0}),
        current_version=0,
    )
    assert _NEW_TAG not in out


def test_no_version_tags_nothing_new() -> None:
    out = _ai_features_for_stack(
        _spec({"name": "gen", "tier": "single_call", "introduced_in_version": 1})
    )
    assert _NEW_TAG not in out


# --- preserved contracts ----------------------------------------------------


def test_provider_strategy_still_surfaced() -> None:
    spec = _spec({"name": "f", "tier": "rag"})
    spec["cross_cutting"] = {
        "provider_strategy": {"recommendation": "frontier capability tier"}
    }
    out = _ai_features_for_stack(spec)
    assert "Provider strategy" in out
    assert "frontier capability tier" in out


def test_empty_features_returns_empty_string() -> None:
    assert _ai_features_for_stack(_spec(), current_version=1) == ""


# --- cross-cutting strategy surfacing (prompt_versioning, tool_protocol) -----


def test_tool_protocol_strategy_surfaced() -> None:
    spec = _spec({"name": "f", "tier": "tool_agent"})
    spec["cross_cutting"] = {
        "tool_protocol_strategy": {"recommendation": "MCP for lookup, direct for X"}
    }
    out = _ai_features_for_stack(spec)
    assert "Tool protocol strategy" in out
    assert "MCP for lookup" in out


def test_prompt_versioning_surfaced() -> None:
    spec = _spec({"name": "f", "tier": "single_call"})
    spec["cross_cutting"] = {
        "prompt_versioning": {"recommendation": "semver per-feature prompts"}
    }
    out = _ai_features_for_stack(spec)
    assert "Prompt versioning" in out
    assert "semver per-feature prompts" in out


def test_cross_cutting_strategies_absent_when_not_provided() -> None:
    out = _ai_features_for_stack(_spec({"name": "f", "tier": "single_call"}))
    assert "Tool protocol strategy" not in out
    assert "Prompt versioning" not in out


# --- D-SC14: the joins the linkage rules condition on are on the wire --------
#
# The prompt tells the model to tag entries with the product feature id a
# capability serves, and fires the capability lane on ``cross_feature``. Neither
# fact was rendered, so the model inferred the mapping from name similarity —
# and a catalog node id reached ``serves_features`` in place of a product id.


def _grounded(node_id: str, *served: str, **extra: Any) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": node_id,
        "name": node_id,
        "tier": "single_call",
        "vision_grounding": {
            "served_features": [{"id": s, "name": s} for s in served]
        },
    }
    node.update(extra)
    return node


def test_scope_is_rendered_on_the_node() -> None:
    out = _ai_features_for_stack(
        _spec({"name": "cap", "tier": "rag", "scope": "cross_feature"})
    )
    assert "scope: cross_feature" in out


def test_scope_omitted_when_absent() -> None:
    out = _ai_features_for_stack(_spec({"name": "cap", "tier": "rag"}))
    assert "(rag)" in out
    assert "scope:" not in out


def test_sub_feature_scope_rendered() -> None:
    out = _ai_features_for_stack(
        _spec({"name": "cap", "tier": "embeddings", "scope": "sub_feature"})
    )
    assert "scope: sub_feature" in out


def test_served_product_feature_is_rendered() -> None:
    out = _ai_features_for_stack(
        _spec(
            _grounded(
                "adaptive_investigation_orchestration", "adaptive_investigation"
            )
        )
    )
    assert "serves product feature(s): adaptive_investigation" in out


def test_capability_id_never_stands_in_for_the_served_product_id() -> None:
    """The node id and the id it serves are different id spaces — both render."""
    out = _ai_features_for_stack(
        _spec(_grounded("findings_narrative_synthesis", "findings_write_up"))
    )
    assert "**findings_narrative_synthesis**" in out
    assert "serves product feature(s): findings_write_up" in out


def test_multiple_served_features_all_rendered() -> None:
    out = _ai_features_for_stack(
        _spec(_grounded("cap", "deck_build", "targeted_revision"))
    )
    assert "serves product feature(s): deck_build, targeted_revision" in out


def test_served_ids_deduped_preserving_order() -> None:
    node = _grounded("cap", "b", "a")
    node["vision_grounding"]["served_features"].append({"id": "b", "name": "b"})
    out = _ai_features_for_stack(_spec(node))
    assert "serves product feature(s): b, a" in out


def test_ungrounded_node_renders_no_serves_line() -> None:
    """Cross-cutting nodes ground nothing — absence must stay silent, not empty."""
    out = _ai_features_for_stack(_spec({"name": "cap", "tier": "single_call"}))
    assert "serves product feature(s)" not in out


def test_infra_node_renders_no_serves_line() -> None:
    out = _ai_features_for_stack(_spec(_infra("vector_index")))
    assert "serves product feature(s)" not in out


def test_malformed_served_entries_are_skipped() -> None:
    node: dict[str, Any] = {
        "id": "cap",
        "name": "cap",
        "tier": "single_call",
        "vision_grounding": {
            "served_features": ["not_a_dict", {"name": "no_id"}, {"id": "ok"}]
        },
    }
    out = _ai_features_for_stack(_spec(node))
    assert "serves product feature(s): ok" in out


def test_scope_and_new_revision_tag_coexist() -> None:
    out = _ai_features_for_stack(
        _spec(
            {
                "name": "cap",
                "tier": "rag",
                "scope": "feature",
                "introduced_in_version": 2,
            }
        ),
        current_version=2,
    )
    assert "scope: feature)" in out
    assert _NEW_TAG in out


# --- D-SC55a: the rejection list reaches StackAdvisor ------------------------
#
# StackAdvisor could not see `explicitly_rejected`; `_ai_features_for_phaser` has
# always rendered it. The asymmetry ran exactly the wrong way -- StackAdvisor is
# where the provider decision is MADE, and Phaser only inherits it as
# authoritative. Both validated draws paid for it: Threadline provisioned an
# OpenAI primary and an Anthropic fallback for the deselected
# `suggested_replies_in_three_tones`, and Ragmeister rebuilt the deselected
# `policy_gap_identification` as a sub-agent with its own table.


def _rejected(*names: str) -> dict[str, Any]:
    spec = _spec({"name": "Thread_Summarization", "id": "thread_summarization",
                  "kind": "feature", "tier": "chained_calls"})
    spec["explicitly_rejected"] = [
        {"name": n, "rough_description": "deselected in the panel"} for n in names
    ]
    return spec


def test_rejected_candidates_reach_stackadvisor() -> None:
    out = _ai_features_for_stack(_rejected("Suggested_Replies_in_Three_Tones"))
    assert "Suggested_Replies_in_Three_Tones" in out
    assert "Explicitly rejected by the developer" in out


def test_rejected_block_forbids_provisioning_a_mechanism() -> None:
    """The instruction must name the decision StackAdvisor actually makes.

    Phaser's wording ("do NOT plan phases for these") says nothing about provider
    selection, which is why the shared helper is parametrised rather than reused
    verbatim.
    """
    out = _ai_features_for_stack(_rejected("Policy_Gap_Identification"))
    assert "provider capability" in out
    assert "infrastructure entry" in out
    assert "plan phases" not in out


def test_rejected_block_preserves_the_spine_features_ordinary_stack() -> None:
    """D-SC56's other half: honouring the deselection must not strip the feature.

    `source_citations` is a Ragmeister spine feature with no catalog node that
    correctly carries stores, an API and a UI and no provider. A rejected AI
    feature whose name IS an MVP spine feature must land the same way.
    """
    out = _ai_features_for_stack(_rejected("Suggested_Replies_in_Three_Tones"))
    assert "ordinary stack" in out
    assert "not built with" in out


def test_no_rejected_block_when_nothing_was_deselected() -> None:
    out = _ai_features_for_stack(_spec(
        {"name": "Thread_Summarization", "id": "thread_summarization",
         "kind": "feature", "tier": "chained_calls"}
    ))
    assert "Explicitly rejected" not in out


def test_phaser_wording_is_unchanged_by_the_stack_variant() -> None:
    """The default consumer must still be Phaser's, untouched."""
    from spec4.agents._utils import _explicitly_rejected_lines
    lines = _explicitly_rejected_lines(_rejected("Reply_Tone_Matching"))
    assert any("do NOT plan phases for these" in ln for ln in lines)
    assert not any("provider capability" in ln for ln in lines)
