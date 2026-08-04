"""Unit tests for the mechanism-probe scorer (pure, no LLM calls)."""

from __future__ import annotations

from typing import Any

from mechanism_scoring import (  # noqa: E402  (evals/ is a script dir)
    _tier_delta,
    aggregate,
    format_overall,
    format_vision_score,
    score_vision,
)


def _entry(
    name: str,
    linked: list[str],
    tier: str = "single_call",
    mechanisms: list[str] | None = None,
    kind: str = "feature",
) -> dict[str, Any]:
    return {
        "name": name,
        "kind": kind,
        "linked_vision_features": linked,
        "tier": tier,
        "mechanisms": [
            {"name": m, "rationale": "", "configuration": {}}
            for m in (mechanisms or [])
        ],
    }


def _expectations(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "project": "proj",
        "target_mechanism": "structured_outputs",
        "target_mechanism_valid_on": ["capture"],
        "expectations": [
            {
                "vision_feature": "capture",
                "mechanisms_required": ["structured_outputs"],
                "mechanisms_forbidden": [],
                "expected_tiers": ["single_call"],
            },
            {
                "vision_feature": "note",
                "mechanisms_required": [],
                "mechanisms_forbidden": ["structured_outputs"],
                "expected_tiers": ["single_call"],
            },
        ],
    }
    base.update(overrides)
    return base


class TestJoin:
    def test_join_is_by_slug_not_exact_name(self) -> None:
        doc = {
            "ai_features": [
                _entry("x", ["Capture"], mechanisms=["structured_outputs"])
            ]
        }
        score = score_vision(_expectations(), doc)
        capture = score.features[0]
        assert capture.covered
        assert capture.required_hit == ["structured_outputs"]

    def test_uncovered_feature_excluded_from_recall_denominator(self) -> None:
        score = score_vision(_expectations(), {"ai_features": []})
        assert [f.vision_feature for f in score.uncovered] == ["capture", "note"]
        assert score.required_total == 0  # not silently counted as misses

    def test_required_satisfied_by_any_one_linked_entry(self) -> None:
        doc = {
            "ai_features": [
                _entry("a", ["capture"], mechanisms=[]),
                _entry("b", ["capture"], mechanisms=["structured_outputs"]),
            ]
        }
        score = score_vision(_expectations(), doc)
        assert score.features[0].required_hit == ["structured_outputs"]
        assert score.features[0].required_miss == []


class TestMechanismChecks:
    def test_required_miss_recorded(self) -> None:
        doc = {"ai_features": [_entry("a", ["capture"], mechanisms=[])]}
        score = score_vision(_expectations(), doc)
        assert score.features[0].required_miss == ["structured_outputs"]
        assert score.required_hits == 0
        assert score.required_total == 1

    def test_forbidden_violation_names_the_entry(self) -> None:
        doc = {
            "ai_features": [
                _entry("noter", ["note"], mechanisms=["structured_outputs"])
            ]
        }
        score = score_vision(_expectations(), doc)
        assert score.features[1].forbidden_violations == [
            ("structured_outputs", "noter")
        ]

    def test_target_spam_on_unlinked_entry(self) -> None:
        doc = {
            "ai_features": [
                _entry("stray", ["elsewhere"], mechanisms=["structured_outputs"])
            ]
        }
        score = score_vision(_expectations(), doc)
        assert score.spam == [("structured_outputs", "stray")]

    def test_target_on_valid_feature_is_not_spam(self) -> None:
        doc = {
            "ai_features": [
                _entry("ok", ["capture"], mechanisms=["structured_outputs"])
            ]
        }
        assert score_vision(_expectations(), doc).spam == []

    def test_bare_string_mechanisms_are_tolerated(self) -> None:
        doc = {
            "ai_features": [
                {
                    "name": "a",
                    "kind": "feature",
                    "linked_vision_features": ["capture"],
                    "tier": "single_call",
                    "mechanisms": ["structured_outputs"],
                }
            ]
        }
        score = score_vision(_expectations(), doc)
        assert score.features[0].required_hit == ["structured_outputs"]


class TestTierChecks:
    def test_delta_zero_inside_set(self) -> None:
        assert _tier_delta("single_call", ["single_call", "rag"]) == 0

    def test_delta_positive_above_set(self) -> None:
        assert _tier_delta("orchestrated_subagents", ["single_call"]) == 5

    def test_delta_negative_below_set(self) -> None:
        assert _tier_delta("deterministic", ["single_call", "rag"]) == -2

    def test_gap_inside_the_set_range_is_not_zero(self) -> None:
        # embeddings (2) sits between deterministic (1) and single_call (3)
        # but is NOT in the set — nearest distance, never 0.
        assert _tier_delta("embeddings", ["deterministic", "single_call"]) == 1

    def test_only_the_highest_ordinal_linked_entry_is_checked(self) -> None:
        """Scout decomposition must not read as deflation: children of a
        chained pipeline are legitimately cheaper than the feature overall."""
        exps = _expectations()
        exps["expectations"][0]["expected_tiers"] = ["chained_calls"]
        doc = {
            "ai_features": [
                _entry("stage_a", ["capture"], tier="single_call"),
                _entry("pipeline", ["capture"], tier="chained_calls"),
                _entry("stage_b", ["capture"], tier="single_call"),
            ]
        }
        score = score_vision(exps, doc)
        assert score.features[0].tier_checks == [
            ("pipeline", "chained_calls", 0)
        ]

    def test_max_entry_inflation_still_scores(self) -> None:
        doc = {
            "ai_features": [
                _entry("a", ["capture"], tier="single_call"),
                _entry("boss", ["capture"], tier="orchestrated_subagents"),
            ]
        }
        score = score_vision(_expectations(), doc)
        assert score.features[0].tier_checks == [
            ("boss", "orchestrated_subagents", 5)
        ]

    def test_infrastructure_entries_exempt_from_tier_check(self) -> None:
        doc = {
            "ai_features": [
                _entry("a", ["capture"], mechanisms=["structured_outputs"]),
                _entry(
                    "vector_store",
                    ["capture"],
                    tier="rag",
                    kind="infrastructure",
                ),
            ]
        }
        score = score_vision(_expectations(), doc)
        assert [name for name, _, _ in score.features[0].tier_checks] == ["a"]


class TestCoverageOptional:
    def _optional_expectations(self) -> dict[str, Any]:
        exps = _expectations()
        exps["expectations"][1]["coverage_optional"] = True
        return exps

    def test_declined_optional_feature_is_not_a_coverage_miss(self) -> None:
        doc = {
            "ai_features": [
                _entry("a", ["capture"], mechanisms=["structured_outputs"])
            ]
        }
        agg = aggregate([score_vision(self._optional_expectations(), doc)])
        assert agg["coverage"] == (1, 1)  # 'note' excluded, not counted missed

    def test_surfaced_optional_feature_is_still_fully_checked(self) -> None:
        doc = {
            "ai_features": [
                _entry("noter", ["note"], mechanisms=["structured_outputs"])
            ]
        }
        score = score_vision(self._optional_expectations(), doc)
        assert score.features[1].forbidden_violations == [
            ("structured_outputs", "noter")
        ]

    def test_formatting_distinguishes_declined_from_missed(self) -> None:
        score = score_vision(self._optional_expectations(), {"ai_features": []})
        text = format_vision_score(score)
        assert "capture: UNCOVERED" in text
        assert "note: not surfaced (coverage-optional" in text


class TestMultiLinkedEntries:
    """Composer coordinators link to several vision features and carry no
    single feature's ground truth: forbidden checks take the intersection of
    the linked features' lists, tier checks the union of their expected
    tiers."""

    def test_mechanism_allowed_by_a_sibling_is_not_a_violation(self) -> None:
        # 'capture' permits structured_outputs, 'note' forbids it — a
        # coordinator serving both may carry it for capture's sake.
        doc = {
            "ai_features": [
                _entry(
                    "pipeline",
                    ["capture", "note"],
                    mechanisms=["structured_outputs"],
                )
            ]
        }
        score = score_vision(_expectations(), doc)
        assert score.features[1].forbidden_violations == []
        # And it still satisfies capture's requirement.
        assert score.features[0].required_hit == ["structured_outputs"]

    def test_mechanism_forbidden_by_all_linked_features_still_violates(self) -> None:
        exps = _expectations()
        exps["expectations"][0]["mechanisms_forbidden"] = ["mcp"]
        exps["expectations"][1]["mechanisms_forbidden"] = ["mcp"]
        doc = {
            "ai_features": [
                _entry("pipeline", ["capture", "note"], mechanisms=["mcp"])
            ]
        }
        score = score_vision(exps, doc)
        assert score.features[0].forbidden_violations == [("mcp", "pipeline")]
        assert score.features[1].forbidden_violations == [("mcp", "pipeline")]

    def test_coordinator_tier_checked_against_union(self) -> None:
        exps = _expectations()
        exps["expectations"][0]["expected_tiers"] = ["chained_calls"]
        exps["expectations"][1]["expected_tiers"] = ["single_call"]
        doc = {
            "ai_features": [
                _entry("boss", ["capture", "note"], tier="chained_calls")
            ]
        }
        score = score_vision(exps, doc)
        # In the union for both features — no fake +3 against 'note'.
        assert score.features[0].tier_checks == [("boss", "chained_calls", 0)]
        assert score.features[1].tier_checks == [("boss", "chained_calls", 0)]

    def test_coordinator_above_the_union_still_reads_as_inflation(self) -> None:
        exps = _expectations()
        exps["expectations"][0]["expected_tiers"] = ["chained_calls"]
        exps["expectations"][1]["expected_tiers"] = ["single_call"]
        doc = {
            "ai_features": [
                _entry("boss", ["capture", "note"], tier="orchestrated_subagents")
            ]
        }
        score = score_vision(exps, doc)
        # +2 over chained_calls (union max) for both — real signal survives.
        for fs in score.features:
            assert fs.tier_checks == [("boss", "orchestrated_subagents", 2)]


class TestVisionWide:
    def test_control_flags_every_instance_and_the_budget(self) -> None:
        exps = _expectations(
            target_mechanism=None,
            target_mechanism_valid_on=[],
            vision_wide={
                "mechanisms_forbidden_everywhere": ["reflection", "mcp"],
                "max_total_mechanism_instances": 0,
            },
        )
        doc = {
            "ai_features": [
                _entry("a", ["capture"], mechanisms=["reflection"]),
                _entry("b", ["elsewhere"], mechanisms=["mcp"]),
            ]
        }
        score = score_vision(exps, doc)
        assert sorted(score.wide_violations) == [
            ("mcp", "b"),
            ("reflection", "a"),
        ]
        assert score.total_mechanism_instances == 2
        assert score.over_budget


class TestAggregate:
    def test_controls_are_kept_out_of_probe_metrics(self) -> None:
        probe = score_vision(
            _expectations(),
            {
                "ai_features": [
                    _entry("a", ["capture"], mechanisms=["structured_outputs"]),
                    _entry("n", ["note"]),
                ]
            },
        )
        control = score_vision(
            _expectations(
                target_mechanism=None,
                target_mechanism_valid_on=[],
                vision_wide={"mechanisms_forbidden_everywhere": ["mcp"]},
            ),
            {"ai_features": [_entry("c", ["capture"], mechanisms=["mcp"])]},
        )
        agg = aggregate([probe, control])
        assert agg["required_recall"] == (1, 1)
        assert agg["forbidden_violations"] == 0
        assert agg["control_mechanism_instances"] == 1
        assert agg["control_wide_violations"] == 1

    def test_formatting_smoke(self) -> None:
        score = score_vision(_expectations(), {"ai_features": []})
        text = format_vision_score(score)
        assert "UNCOVERED" in text
        overall = format_overall(aggregate([score]))
        assert "Required-mechanism recall" in overall
