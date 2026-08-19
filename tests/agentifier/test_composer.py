"""Tests for the Composer sub-agent (replaces the Consolidator).

Covers edge-based grouping, head-present pass-through, headless synthesis (with a
synthetic fixture, since the live corpus never produced a headless group),
present-flat fallback on synthesis failure, C9 description enrichment, and the
zero-LLM-call property when every group has a head.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

from spec4.agentifier.composer import (
    ComposerAgent,
    ComposerInput,
    _enrich_descriptions,
    _group_by_composed_under,
)
from spec4.agentifier.scout import Candidate

_VISION: dict[str, Any] = {"vision_statement": {"vision": {"key_features_mvp": []}}}
_LLM_CONFIG: dict[str, Any] = {"provider": "test", "model": "test"}


def _c(
    name: str,
    *,
    scope: str = "feature",
    features: list[str] | None = None,
    composed_under: str = "",
    requires: list[str] | None = None,
    desc: str = "Does a thing.",
) -> Candidate:
    return Candidate(
        name=name,
        linked_vision_features=features or [],
        scope=scope,
        rough_description=desc,
        composed_under=composed_under,
        requires=list(requires or []),
    )


def _mock_response(text: str) -> Any:
    """Iterator of text deltas, the shape complete_stream yields."""
    return iter([text])


def _run(candidates: list[Candidate]) -> Any:
    return asyncio.run(
        ComposerAgent().run(
            ComposerInput(candidates=candidates, vision=_VISION, llm_config=_LLM_CONFIG)
        )
    )


def _by_name(cands: list[Candidate]) -> dict[str, Candidate]:
    return {c.name: c for c in cands}


# ---------------------------------------------------------------------------
# head-present groups (the measured norm) — no LLM, nothing dropped
# ---------------------------------------------------------------------------


class TestHeadPresent:
    def test_head_present_group_passes_through_without_llm(self) -> None:
        cands = [
            _c("orch", features=["deck"]),
            _c("member_a", scope="sub_feature", features=["deck"], composed_under="orch"),
            _c("member_b", scope="sub_feature", features=["deck"], composed_under="orch"),
        ]
        with patch("spec4.agentifier.composer.complete_stream") as mock_complete:
            out = _run(cands)
        mock_complete.assert_not_called()  # deterministic when heads are present
        assert len(out.candidates) == 3
        assert out.n_synthesized == 0
        assert len(out.compositions) == 1
        assert out.compositions[0].head_present is True
        assert out.compositions[0].coordinator == "orch"

    def test_single_member_head_present_records_no_composition(self) -> None:
        # C-series: a single-member head-present group is not a coordination.
        # Both candidates pass through untouched and no Composition is recorded.
        cands = [
            _c("orch", features=["deck"], desc="Runs the show."),
            _c("member_a", scope="sub_feature", features=["deck"], composed_under="orch"),
        ]
        with patch("spec4.agentifier.composer.complete_stream") as mock_complete:
            out = _run(cands)
        mock_complete.assert_not_called()
        assert out.compositions == []
        assert out.n_synthesized == 0
        assert len(out.candidates) == 2
        by = _by_name(out.candidates)
        assert "Coordinates" not in by["orch"].rough_description
        assert "Part of the orch capability." not in by["member_a"].rough_description

    def test_standalone_scope_is_derived_from_vision_span(self) -> None:
        # Fork A: the Composer derives scope from the finalized graph, not from
        # Scout's input. A standalone spanning >1 vision feature is cross_feature;
        # one feature (or none) is a plain feature. Input scope is ignored.
        cands = [
            _c("solo", features=["deck"], scope="cross_feature"),
            _c("shared", features=["deck", "revise"], scope="feature"),
        ]
        with patch("spec4.agentifier.composer.complete_stream") as mock_complete:
            out = _run(cands)
        mock_complete.assert_not_called()
        assert out.n_synthesized == 0
        assert out.compositions == []
        by = _by_name(out.candidates)
        assert by["solo"].scope == "feature"
        assert by["shared"].scope == "cross_feature"
        assert by["shared"].composed_under == ""


# ---------------------------------------------------------------------------
# headless synthesis — the C4 path, exercised by a synthetic fixture
# ---------------------------------------------------------------------------


class TestHeadlessSynthesis:
    def _headless_fixture(self) -> list[Candidate]:
        # A coordinated group whose coined coordinator ("pipeline") Scout did not
        # emit — exactly the head-absent case the live corpus never produced.
        return [
            _c("stage_one", scope="sub_feature", features=["prod"], composed_under="pipeline"),
            _c(
                "stage_two",
                scope="sub_feature",
                features=["prod"],
                composed_under="pipeline",
                requires=["stage_one"],
            ),
        ]

    def test_headless_group_gets_synthesized_head(self) -> None:
        with patch(
            "spec4.agentifier.composer.complete_stream",
            return_value=_mock_response("Runs the two-stage production pipeline."),
        ) as mock_complete:
            out = _run(self._headless_fixture())
        mock_complete.assert_called_once()  # one generative act
        assert out.n_synthesized == 1
        by = _by_name(out.candidates)
        assert "pipeline" in by  # head was synthesized and inserted
        head = by["pipeline"]
        assert head.scope == "feature"
        assert head.composed_under == ""
        assert "prod" in head.linked_vision_features  # vision-grounded via union

    def test_synthesized_head_inserted_before_its_members(self) -> None:
        with patch(
            "spec4.agentifier.composer.complete_stream",
            return_value=_mock_response("A production pipeline."),
        ):
            out = _run(self._headless_fixture())
        order = [c.name for c in out.candidates]
        assert order.index("pipeline") < order.index("stage_one")

    def test_synthesis_failure_presents_flat(self) -> None:
        # complete raising → group detaches, members stand alone, nothing lost.
        with patch("spec4.agentifier.composer.complete_stream", side_effect=RuntimeError("boom")):
            out = _run(self._headless_fixture())
        assert out.n_synthesized == 0
        by = _by_name(out.candidates)
        assert "pipeline" not in by  # no head synthesized
        assert by["stage_one"].composed_under == ""  # detached
        assert by["stage_one"].scope == "feature"  # promoted to standalone
        assert len(out.candidates) == 2  # nothing dropped

    def test_empty_synthesis_text_presents_flat(self) -> None:
        with patch(
            "spec4.agentifier.composer.complete_stream", return_value=_mock_response("   ")
        ):
            out = _run(self._headless_fixture())
        assert out.n_synthesized == 0
        assert "pipeline" not in _by_name(out.candidates)


# ---------------------------------------------------------------------------
# C9 — surfacing relationships in descriptions
# ---------------------------------------------------------------------------


class TestEnrichment:
    def test_member_gets_membership_sentence(self) -> None:
        # A genuine (>=2-member) coordinator: each member is labelled.
        cands = [
            _c("orch"),
            _c("m", scope="sub_feature", composed_under="orch", desc="Extracts data."),
            _c("m2", scope="sub_feature", composed_under="orch"),
        ]
        out = _run(cands)
        assert "Part of the orch capability." in _by_name(out.candidates)["m"].rough_description

    def test_head_gets_coordinates_sentence(self) -> None:
        cands = [
            _c("orch", desc="Runs the show."),
            _c("m1", scope="sub_feature", composed_under="orch"),
            _c("m2", scope="sub_feature", composed_under="orch"),
        ]
        out = _run(cands)
        head_desc = _by_name(out.candidates)["orch"].rough_description
        assert "Coordinates m1, m2." in head_desc

    def test_single_member_group_gets_no_coordinator_prose(self) -> None:
        # C-series: a single-member group is a normal candidate plus a normal
        # member. Neither the "Coordinates" nor the "Part of" sentence is emitted.
        cands = [
            _c("orch", desc="Runs the show."),
            _c("m", scope="sub_feature", composed_under="orch", desc="Extracts data."),
        ]
        out = _run(cands)
        by = _by_name(out.candidates)
        assert "Coordinates" not in by["orch"].rough_description
        assert "Part of the orch capability." not in by["m"].rough_description

    def test_requires_gets_depends_on_sentence(self) -> None:
        cands = [
            _c("producer"),
            _c("consumer", requires=["producer"], desc="Uses the output."),
        ]
        out = _run(cands)
        assert "Depends on producer." in _by_name(out.candidates)["consumer"].rough_description

    def test_enrichment_is_idempotent(self) -> None:
        # Running the enrichment twice must not double any sentence. Uses a
        # genuine >=2-member coordinator so the membership sentence is emitted.
        cands = [
            _c("orch"),
            _c("m", scope="sub_feature", composed_under="orch", desc="Extracts data."),
            _c("m2", scope="sub_feature", composed_under="orch"),
        ]
        members_by_label, _ = _group_by_composed_under(cands)
        _enrich_descriptions(cands, members_by_label)
        first = _by_name(cands)["m"].rough_description
        _enrich_descriptions(cands, members_by_label)
        assert _by_name(cands)["m"].rough_description == first
        assert first.count("Part of the orch capability.") == 1


# ---------------------------------------------------------------------------
# misc / robustness
# ---------------------------------------------------------------------------


class TestRobustness:
    def test_empty_input(self) -> None:
        out = _run([])
        assert out.candidates == []
        assert out.n_synthesized == 0

    def test_orphan_sub_feature_promoted_to_feature(self) -> None:
        # A sub_feature composing under nothing is the _apply_merges heir's job:
        # promote it to a standalone feature.
        cands = [_c("orphan", scope="sub_feature")]
        out = _run(cands)
        assert _by_name(out.candidates)["orphan"].scope == "feature"
        assert _by_name(out.candidates)["orphan"].composed_under == ""

    def test_genuine_member_keeps_sub_feature(self) -> None:
        cands = [
            _c("orch"),
            _c("m", scope="sub_feature", composed_under="orch"),
        ]
        out = _run(cands)
        assert _by_name(out.candidates)["m"].scope == "sub_feature"

    def test_nothing_is_ever_dropped(self) -> None:
        cands = [
            _c("orch"),
            _c("m1", scope="sub_feature", composed_under="orch"),
            _c("m2", scope="sub_feature", composed_under="orch"),
            _c("solo"),
            _c("shared", scope="cross_feature"),
        ]
        out = _run(cands)
        for original in cands:
            assert original.name in {c.name for c in out.candidates}