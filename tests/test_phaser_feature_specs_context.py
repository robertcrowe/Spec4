"""Unit tests for ``_feature_specs_for_phaser`` — the product-feature spine
block Phaser receives (D-PH1a option B, D-PH1c).

The spine is Phaser's *base* input: one behavioural block per MVP feature, AI
and non-AI alike, so every feature the phases must build — including every
feature of a no-AI app — reaches Phaser as structure rather than vision prose.
The AI catalog stays enrichment on the AI subset, so a feature an AI node
*serves* (via ``vision_grounding``, id join only) is tagged ``(AI)``.
``nfr_goals`` render with stable ``nfr_<slug>`` ids and the D-PH1c citation
rule (cite in verification; never invent a claim for an unclaimed goal).

Pure rendering assertions; whether the live model then phases correctly is an
in-app behavioural draw, not asserted here.
"""

from __future__ import annotations

from typing import Any

from spec4.agents._utils import _feature_specs_for_phaser, slug

_HEAD = "Feature specifications (from Brainstormer)"
_VOCAB = "Domain vocabulary"


def _specs(*features: dict[str, Any], nfr: list[str] | None = None) -> dict[str, Any]:
    return {"features": list(features), "nfr_goals": nfr or []}


def _catalog(*served_ids: str) -> dict[str, Any]:
    """AI catalog whose nodes *serve* the given product ids via vision_grounding."""
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
    assert _feature_specs_for_phaser(None) == ""
    assert _feature_specs_for_phaser({}) == ""
    assert _feature_specs_for_phaser({"features": []}) == ""


# --- base rendering --------------------------------------------------------


def test_every_feature_renders_with_id_and_behavioural_fields() -> None:
    out = _feature_specs_for_phaser(
        _specs(
            _feature(
                "fare_lookup",
                success_criteria=["fare matches the table"],
                failure_modes=[{"mode": "stale table", "likelihood": "low"}],
            ),
            _feature("trip_history"),
        )
    )
    assert _HEAD in out
    assert "id: `fare_lookup`" in out
    assert "id: `trip_history`" in out
    assert "fare matches the table" in out
    assert "stale table" in out


def test_phaser_framing_names_verification_and_risk_roles() -> None:
    out = _feature_specs_for_phaser(_specs(_feature("a")))
    assert "verification raw material" in out
    assert "risk-assessment raw material" in out


def test_non_ai_feature_untagged_without_catalog() -> None:
    # Assert on the header line, not the whole output — the framing prose
    # legitimately mentions "(AI)" when explaining the tag.
    out = _feature_specs_for_phaser(_specs(_feature("fare_lookup")))
    header = next(line for line in out.splitlines() if line.startswith("###"))
    assert "(AI)" not in header


def test_served_feature_tagged_ai_via_grounding_join() -> None:
    out = _feature_specs_for_phaser(
        _specs(_feature("thread_summarization"), _feature("plain_feature")),
        _catalog("thread_summarization"),
    )
    head, _, tail = out.partition("`plain_feature`")
    assert "(AI)" in head  # the served feature's header is tagged
    assert "(AI)" not in tail  # the unserved one is not


def test_infra_nodes_do_not_tag_features() -> None:
    catalog = {
        "ai_features": [
            {
                "id": "vector_index",
                "kind": "infrastructure",
                "vision_grounding": {"served_features": [{"id": "fare_lookup"}]},
            }
        ]
    }
    out = _feature_specs_for_phaser(_specs(_feature("fare_lookup")), catalog)
    header = next(line for line in out.splitlines() if line.startswith("###"))
    assert "(AI)" not in header


# --- dependencies / entities -----------------------------------------------


def test_dependencies_render_with_build_order_framing() -> None:
    out = _feature_specs_for_phaser(
        _specs(_feature("trip_history", dependencies=["fare_lookup"]))
    )
    assert "depends on: fare_lookup" in out
    assert "no later than `trip_history`" in out


def test_entities_deduplicate_into_shared_vocabulary() -> None:
    out = _feature_specs_for_phaser(
        _specs(
            _feature("a", entities=["Zone", "Fare Table"]),
            _feature("b", entities=["Zone", "Saved Trip"]),
        )
    )
    assert _VOCAB in out
    vocab_line = next(line for line in out.splitlines() if _VOCAB in line)
    assert vocab_line.count("Zone") == 1
    assert "Fare Table" in vocab_line and "Saved Trip" in vocab_line


# --- nfr goals (D-PH1c) ----------------------------------------------------


def test_nfr_goals_render_with_stable_ids_and_citation_rule() -> None:
    goal = "Fare lookups complete quickly."
    out = _feature_specs_for_phaser(_specs(_feature("a"), nfr=[goal]))
    assert f"`nfr_{slug(goal)}`: {goal}" in out
    assert "verification criteria" in out
    assert "never invent a stack claim" in out


def test_no_nfr_block_when_goals_absent() -> None:
    out = _feature_specs_for_phaser(_specs(_feature("a")))
    assert "Non-functional goals" not in out

# --- excluded features (D-PH1i) --------------------------------------------


def _catalog_with_rejection(*rejected_names: str) -> dict[str, Any]:
    return {"ai_features": [], "explicitly_rejected": [
        {"name": n, "reason": "closure_coordinator_off"} for n in rejected_names
    ]}


def test_rejected_unserved_spine_feature_tagged_excluded() -> None:
    out = _feature_specs_for_phaser(
        _specs(_feature("suggested_replies_in_three_tones")),
        _catalog_with_rejection("suggested_replies_in_three_tones"),
    )
    header = next(line for line in out.splitlines() if line.startswith("###"))
    assert "excluded — AI implementation rejected at the Agentifier panel" in header
    assert "revisit the Agentifier selection" in header


def test_rejected_member_name_does_not_tag_spine_features() -> None:
    # Deselected sub-capabilities match no spine id and must not tag anything.
    out = _feature_specs_for_phaser(
        _specs(_feature("thread_summarization")),
        _catalog_with_rejection("context_aware_reply_generation"),
    )
    assert "excluded" not in out.split("**", 2)[2]  # nothing after the header


def test_served_feature_never_tagged_excluded() -> None:
    # A feature an AI node serves is AI-backed even if a same-named entry is
    # in the rejected list; the serves-join wins.
    catalog = _catalog("thread_summarization")
    catalog["explicitly_rejected"] = [{"name": "thread_summarization"}]
    out = _feature_specs_for_phaser(_specs(_feature("thread_summarization")), catalog)
    header = next(line for line in out.splitlines() if line.startswith("###"))
    assert "(AI)" in header
    assert "excluded" not in header


def test_header_states_the_excluded_exception() -> None:
    out = _feature_specs_for_phaser(
        _specs(_feature("a")), _catalog_with_rejection("a")
    )
    assert "except any feature tagged (excluded)" in out