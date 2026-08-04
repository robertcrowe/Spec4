"""Tests for ``spec4.stack_routing`` — the deterministic D-PH3/D-PH4 joins.

Routing: serving entries attach to phases whose declarations intersect their
served ids (each serves key against its own array); roadmap-status entries
never route; entries serving only undeclared (e.g. excluded) features route
nowhere. Baseline: no-serves libraries render everywhere. Threading: claimed
goals target the claiming entries' served ids; global-only claims target the
final phase; orphans and unknown claims are omitted.
"""

from __future__ import annotations

from typing import Any

from spec4.stack_routing import (
    baseline_library_names,
    derived_nfr_ids,
    entries_for_declarations,
    nfr_threads,
    stack_signal_entries,
)


def _stack(**spec: Any) -> dict[str, Any]:
    return {"stack_spec": spec}


class TestEntriesForDeclarations:
    def test_feature_and_capability_keys_match_their_own_arrays(self) -> None:
        stack = _stack(
            libraries=[
                {"name": "FormLib", "serves_features": ["fare_lookup"]},
                {"name": "AgentLib", "serves_capabilities": ["orchestrator"]},
            ]
        )
        routed = entries_for_declarations(stack, {"fare_lookup"}, {"orchestrator"})
        assert [r["label"] for r in routed] == ["FormLib", "AgentLib"]
        assert routed[0]["matched"] == ["fare_lookup"]
        # a capability id in the feature set must NOT match a serves_capabilities
        routed = entries_for_declarations(stack, {"orchestrator"}, set())
        assert routed == []

    def test_union_across_both_keys_dedupes_matched_ids(self) -> None:
        stack = _stack(
            libraries=[
                {
                    "name": "Both",
                    "serves_features": ["f1"],
                    "serves_capabilities": ["c1"],
                }
            ]
        )
        routed = entries_for_declarations(stack, {"f1"}, {"c1"})
        assert routed[0]["matched"] == ["c1", "f1"]

    def test_roadmap_status_never_routes(self) -> None:
        stack = _stack(
            libraries=[
                {
                    "name": "Playwright",
                    "status": "deferred",
                    "serves_features": ["fare_lookup"],
                }
            ]
        )
        assert entries_for_declarations(stack, {"fare_lookup"}, set()) == []

    def test_entry_serving_only_undeclared_features_routes_nowhere(self) -> None:
        # The excluded disposition for free: an excluded feature is never
        # declared, so the intersection is empty.
        stack = _stack(
            persistence={
                "primary_store": {
                    "collections": [
                        {
                            "name": "draft_replies",
                            "serves_features": ["suggested_replies"],
                        }
                    ]
                }
            }
        )
        assert entries_for_declarations(stack, {"thread_summarization"}, set()) == []

    def test_absent_stack_routes_nothing(self) -> None:
        assert entries_for_declarations(None, {"f"}, set()) == []
        assert entries_for_declarations({}, {"f"}, set()) == []


class TestBaselineLibraries:
    def test_no_serves_libraries_only(self) -> None:
        stack = _stack(
            libraries=[
                {"name": "FastAPI"},
                {"name": "FormLib", "serves_features": ["f"]},
                {"name": "Playwright", "status": "deferred"},
            ],
            persistence={"primary_store": {"satisfies_nfr": ["nfr_x"]}},
        )
        assert baseline_library_names(stack) == ["FastAPI"]

    def test_dict_of_tiers_shape_supported(self) -> None:
        stack = _stack(
            libraries={
                "backend": [{"name": "FastAPI"}],
                "frontend": [{"name": "React"}],
            }
        )
        assert baseline_library_names(stack) == ["FastAPI", "React"]


class TestNfrThreads:
    _SPECS = {
        "features": [],
        "nfr_goals": ["Lookups are fast.", "Works offline.", "Orphan goal."],
    }

    def test_served_claim_targets_served_ids(self) -> None:
        stack = _stack(
            libraries=[
                {
                    "name": "FormLib",
                    "serves_features": ["fare_lookup"],
                    "satisfies_nfr": ["nfr_lookups_are_fast_"],
                }
            ]
        )
        threads = nfr_threads(stack, self._SPECS)
        assert len(threads) == 1
        t = threads[0]
        assert t["nfr_id"] == "nfr_lookups_are_fast_"
        assert t["serves_features"] == {"fare_lookup"}
        assert t["global"] is False
        assert t["claimers"] == ["FormLib"]

    def test_global_only_claim_is_marked_global(self) -> None:
        stack = _stack(
            libraries=[{"name": "PWA", "satisfies_nfr": ["nfr_works_offline_"]}]
        )
        threads = nfr_threads(stack, self._SPECS)
        assert threads[0]["global"] is True

    def test_mixed_claimers_union_serves_and_not_global(self) -> None:
        stack = _stack(
            libraries=[
                {"name": "PWA", "satisfies_nfr": ["nfr_works_offline_"]},
                {
                    "name": "CacheColl",
                    "serves_features": ["fare_lookup"],
                    "satisfies_nfr": ["nfr_works_offline_"],
                },
            ]
        )
        t = nfr_threads(stack, self._SPECS)[0]
        assert t["global"] is False
        assert t["serves_features"] == {"fare_lookup"}
        assert t["claimers"] == ["CacheColl", "PWA"]

    def test_orphans_and_unknown_claims_omitted(self) -> None:
        stack = _stack(
            libraries=[{"name": "Lib", "satisfies_nfr": ["nfr_made_up"]}]
        )
        assert nfr_threads(stack, self._SPECS) == []

    def test_no_specs_threads_nothing(self) -> None:
        stack = _stack(libraries=[{"name": "Lib", "satisfies_nfr": ["nfr_x"]}])
        assert nfr_threads(stack, None) == []


class TestWalkerOwnership:
    def test_unnamed_provider_capability_labeled_with_tier(self) -> None:
        stack = _stack(
            providers={
                "OpenAI": {
                    "capabilities": [
                        {"tier": "single_call", "serves_capabilities": ["x"]}
                    ]
                }
            }
        )
        recs = stack_signal_entries(stack)
        assert recs[0]["label"] == "OpenAI [single_call]"
        assert recs[0]["section"] == "providers"


class TestDerivedNfrIds:
    """The D-SC2 id derivation, shared so a goal has one id pipeline-wide."""

    def test_every_goal_gets_a_slug_id(self) -> None:
        specs = {"nfr_goals": ["Answers are fast.", "Works offline"]}
        assert derived_nfr_ids(specs) == {
            "nfr_answers_are_fast_": "Answers are fast.",
            "nfr_works_offline": "Works offline",
        }

    def test_source_order_is_preserved(self) -> None:
        specs = {"nfr_goals": ["Zebra", "Apple", "Mango"]}
        assert list(derived_nfr_ids(specs).values()) == ["Zebra", "Apple", "Mango"]

    def test_blank_and_non_string_goals_are_skipped(self) -> None:
        specs = {"nfr_goals": ["Real goal", "   ", None, 7, ""]}
        assert list(derived_nfr_ids(specs).values()) == ["Real goal"]

    def test_absent_specs_derive_nothing(self) -> None:
        assert derived_nfr_ids(None) == {}
        assert derived_nfr_ids({}) == {}

    def test_returns_orphans_too_unlike_nfr_threads(self) -> None:
        """The shared derivation is claim-agnostic; filtering is the caller's."""
        specs = {"nfr_goals": ["Claimed goal", "Orphan goal"]}
        stack = _stack(
            libraries=[{"name": "Lib", "satisfies_nfr": ["nfr_claimed_goal"]}]
        )
        assert len(derived_nfr_ids(specs)) == 2
        assert [t["nfr_id"] for t in nfr_threads(stack, specs)] == ["nfr_claimed_goal"]
