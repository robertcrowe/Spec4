"""Unit tests for the Layer-1 phantom-link checker (dev tooling)."""

from __future__ import annotations

from typing import Any

import pytest

from phantom_link_check import (  # noqa: E402  (evals/ is a script dir, not a package)
    _normalize,
    check_phantom_links,
    format_phantom_report,
    phantom_link_summary,
)
from spec4.agentifier.scout import Candidate


def _vision(feature_entries: list[Any]) -> dict[str, Any]:
    """Canonical envelope: vision_statement.vision.key_features_mvp."""
    return {"vision_statement": {"vision": {"key_features_mvp": feature_entries}}}


def _feat(name: str) -> dict[str, Any]:
    return {name: {"description": f"{name} desc", "example": "ex"}}


# --- exact / phantom / empty -------------------------------------------------


def test_all_links_exact_are_clean() -> None:
    vision = _vision([_feat("AI_Recs"), _feat("User_Reviews")])
    cands = [Candidate("rec_engine", ["AI_Recs"], "feature", "d")]
    reports = check_phantom_links(cands, vision)
    assert reports[0].phantom_links == []
    assert reports[0].near_miss_links == []
    assert reports[0].has_phantom is False


def test_invented_feature_is_phantom() -> None:
    vision = _vision([_feat("AI_Recs")])
    cands = [Candidate("x", ["AI_Recs", "Ghost_Feature"], "feature", "d")]
    reports = check_phantom_links(cands, vision)
    assert reports[0].phantom_links == ["Ghost_Feature"]
    assert reports[0].has_phantom is True


def test_empty_links_never_phantom() -> None:
    # Cross-cutting concern / Pass-2 adjacent candidate: empty links are expected.
    vision = _vision([_feat("AI_Recs")])
    cands = [Candidate("content_moderation", [], "cross_feature", "d")]
    reports = check_phantom_links(cands, vision)
    assert reports[0].phantom_links == []
    assert reports[0].near_miss_links == []


def test_no_features_in_vision_makes_any_link_phantom() -> None:
    vision = _vision([])
    cands = [Candidate("x", ["Anything"], "feature", "d")]
    reports = check_phantom_links(cands, vision)
    assert reports[0].phantom_links == ["Anything"]


# --- near-miss (formatting drift, not confabulation) -------------------------


@pytest.mark.parametrize("emitted", ["ai_recs", "AI Recs", "AI-Recs", "  AI_Recs  "])
def test_near_miss_case_and_separator_drift(emitted: str) -> None:
    vision = _vision([_feat("AI_Recs")])
    cands = [Candidate("x", [emitted], "feature", "d")]
    reports = check_phantom_links(cands, vision)
    assert reports[0].phantom_links == []
    assert reports[0].near_miss_links == [(emitted, ["AI_Recs"])]
    assert reports[0].has_near_miss is True


def test_exact_match_preferred_over_near_miss() -> None:
    vision = _vision([_feat("AI_Recs")])
    cands = [Candidate("x", ["AI_Recs"], "feature", "d")]
    reports = check_phantom_links(cands, vision)
    assert reports[0].near_miss_links == []


def test_phantom_and_near_miss_can_coexist() -> None:
    vision = _vision([_feat("AI_Recs")])
    cands = [Candidate("x", ["ai recs", "Nope"], "feature", "d")]
    reports = check_phantom_links(cands, vision)
    assert reports[0].phantom_links == ["Nope"]
    assert reports[0].near_miss_links == [("ai recs", ["AI_Recs"])]
    assert reports[0].has_phantom is True
    assert reports[0].has_near_miss is True


# --- input shapes ------------------------------------------------------------


def test_accepts_dict_candidates() -> None:
    vision = _vision([_feat("AI_Recs")])
    cands = [{"name": "x", "linked_vision_features": ["AI_Recs", "Ghost"]}]
    reports = check_phantom_links(cands, vision)
    assert reports[0].candidate_name == "x"
    assert reports[0].phantom_links == ["Ghost"]


def test_bare_string_feature_shape() -> None:
    vision = _vision(["BareStringFeature", _feat("AI_Recs")])
    cands = [Candidate("x", ["BareStringFeature"], "feature", "d")]
    reports = check_phantom_links(cands, vision)
    assert reports[0].phantom_links == []


def test_flat_key_features_fallback_shape() -> None:
    # vision_statement.key_features_mvp (no inner "vision") is also supported.
    vision = {"vision_statement": {"key_features_mvp": [_feat("AI_Recs")]}}
    cands = [Candidate("x", ["AI_Recs", "Ghost"], "feature", "d")]
    reports = check_phantom_links(cands, vision)
    assert reports[0].phantom_links == ["Ghost"]


def test_probe_shape_top_level_key_features() -> None:
    # The shape run_scout_probe.py feeds Scout: bare inner dict, features at top.
    vision = {
        "purpose": "p",
        "key_features_mvp": [_feat("represented_negotiation"), _feat("deal_approval")],
    }
    cands = [
        Candidate("negotiator", ["represented_negotiation"], "feature", "grounded"),
        Candidate("invented", ["Payment_Escrow"], "feature", "phantom"),
    ]
    reports = check_phantom_links(cands, vision)
    assert reports[0].phantom_links == []            # real feature, clean
    assert reports[1].phantom_links == ["Payment_Escrow"]


def test_pipeline_shape_nested_vision() -> None:
    # The shape the pipeline hands Scout: {"name":..., "vision": {key_features_mvp}}.
    vision = {"name": "X", "vision": {"key_features_mvp": [_feat("AI_Recs")]}}
    cands = [Candidate("x", ["AI_Recs", "Ghost"], "feature", "d")]
    reports = check_phantom_links(cands, vision)
    assert reports[0].phantom_links == ["Ghost"]


# --- summary aggregation -----------------------------------------------------


def test_summary_counts_and_rate() -> None:
    vision = _vision([_feat("AI_Recs"), _feat("User_Reviews")])
    cands = [
        Candidate("clean", ["AI_Recs"], "feature", "d"),          # clean
        Candidate("phantom", ["Ghost"], "feature", "d"),          # phantom
        Candidate("nearmiss", ["ai_recs"], "feature", "d"),       # near-miss only
        Candidate("adjacent", [], "cross_feature", "d"),          # empty (out of scope)
    ]
    reports = check_phantom_links(cands, vision)
    s = phantom_link_summary(reports)
    assert s["candidates"] == 4
    assert s["candidates_with_links"] == 3
    assert s["fully_clean"] == 1
    assert s["phantom_flagged"] == 1
    assert s["near_miss_flagged"] == 1
    assert s["total_phantom_links"] == 1
    assert s["total_near_miss_links"] == 1
    assert s["phantom_rate"] == pytest.approx(1 / 3)


def test_summary_empty_input() -> None:
    s = phantom_link_summary([])
    assert s["candidates"] == 0
    assert s["phantom_rate"] == 0.0


# --- helpers -----------------------------------------------------------------


def test_normalize() -> None:
    assert _normalize("AI_Recs") == "ai recs"
    assert _normalize("AI  Recs") == "ai recs"
    assert _normalize("--AI--Recs--") == "ai recs"
    assert _normalize("") == ""


def test_format_report_mentions_flagged_only() -> None:
    vision = _vision([_feat("AI_Recs")])
    cands = [
        Candidate("clean", ["AI_Recs"], "feature", "d"),
        Candidate("bad", ["Ghost"], "feature", "d"),
    ]
    out = format_phantom_report(check_phantom_links(cands, vision))
    assert "bad" in out and "Ghost" in out
    # the clean candidate must not appear as a per-candidate detail line
    assert "- clean:" not in out