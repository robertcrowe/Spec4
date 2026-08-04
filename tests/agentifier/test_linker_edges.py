"""Tests for the Linker graph-contract edge integrity pass (contract §6).

These exercise ``_normalize_edges`` directly on synthetic candidate lists, so
the graph rules are covered without going through JSON parsing or an LLM. The
contract's guiding stance is that every violation degrades safely — nothing is
rejected — so each rule here asserts a specific safe degradation.
"""

from __future__ import annotations

from spec4.agentifier.linker import _normalize_edges
from spec4.agentifier.scout import Candidate


def _candidate(
    name: str,
    *,
    scope: str = "feature",
    composed_under: str = "",
    requires: list[str] | None = None,
) -> Candidate:
    return Candidate(
        name=name,
        linked_vision_features=[],
        scope=scope,
        rough_description="",
        composed_under=composed_under,
        requires=list(requires or []),
    )


def _by_name(candidates: list[Candidate]) -> dict[str, Candidate]:
    return {c.name: c for c in candidates}


# ---------------------------------------------------------------------------
# composed_under
# ---------------------------------------------------------------------------


class TestComposedUnder:
    def test_head_present_group_keeps_membership(self) -> None:
        cs = [
            _candidate("orch"),
            _candidate("a", composed_under="orch"),
            _candidate("b", composed_under="orch"),
        ]
        _normalize_edges(cs)
        by = _by_name(cs)
        assert by["a"].composed_under == "orch"
        assert by["b"].composed_under == "orch"

    def test_head_present_head_is_feature_members_sub_feature(self) -> None:
        # The head (referenced, no composed_under) normalizes to feature; the
        # members normalize to sub_feature even if emitted as feature.
        cs = [
            _candidate("orch", scope="sub_feature"),
            _candidate("a", composed_under="orch", scope="feature"),
        ]
        _normalize_edges(cs)
        by = _by_name(cs)
        assert by["orch"].scope == "feature"
        assert by["a"].scope == "sub_feature"

    def test_head_absent_group_of_two_is_kept_for_synthesis(self) -> None:
        # >=2 members sharing a name no candidate carries: a synthesizable
        # head-absent coordinator, so the edge is preserved for the Composer.
        cs = [
            _candidate("x", composed_under="coord"),
            _candidate("y", composed_under="coord"),
        ]
        _normalize_edges(cs)
        by = _by_name(cs)
        assert by["x"].composed_under == "coord"
        assert by["y"].composed_under == "coord"

    def test_singleton_dangler_degrades_to_flat(self) -> None:
        # A single member of a name no candidate carries: degrade to flat.
        cs = [_candidate("solo", composed_under="ghost")]
        _normalize_edges(cs)
        assert cs[0].composed_under == ""

    def test_singleton_under_present_head_is_valid(self) -> None:
        # One member is fine when the head is actually emitted.
        cs = [_candidate("head"), _candidate("only", composed_under="head")]
        _normalize_edges(cs)
        assert _by_name(cs)["only"].composed_under == "head"

    def test_self_composed_under_is_cleared(self) -> None:
        cs = [_candidate("self", composed_under="self")]
        _normalize_edges(cs)
        assert cs[0].composed_under == ""

    def test_nested_coordinator_stays_sub_feature(self) -> None:
        # A coordinator that itself composes under a higher one is a member;
        # composed_under wins over the head->feature rule.
        cs = [
            _candidate("top"),
            _candidate("mid", composed_under="top"),
            _candidate("leaf", composed_under="mid"),
        ]
        _normalize_edges(cs)
        by = _by_name(cs)
        assert by["top"].scope == "feature"
        assert by["mid"].scope == "sub_feature"
        assert by["mid"].composed_under == "top"
        assert by["leaf"].scope == "sub_feature"

    def test_degraded_singleton_leaves_scope_for_the_heir(self) -> None:
        # Degrading to flat clears only the edge; promoting the member's scope
        # is the scope-normalization heir's job, not the parser's.
        cs = [_candidate("solo", scope="sub_feature", composed_under="ghost")]
        _normalize_edges(cs)
        assert cs[0].composed_under == ""
        assert cs[0].scope == "sub_feature"


# ---------------------------------------------------------------------------
# requires
# ---------------------------------------------------------------------------


class TestRequires:
    def test_dangling_requires_dropped(self) -> None:
        cs = [_candidate("c", requires=["nonexistent"])]
        _normalize_edges(cs)
        assert cs[0].requires == []

    def test_self_requires_dropped(self) -> None:
        cs = [_candidate("c", requires=["c"])]
        _normalize_edges(cs)
        assert cs[0].requires == []

    def test_valid_requires_to_emitted_candidate_kept(self) -> None:
        cs = [_candidate("producer"), _candidate("consumer", requires=["producer"])]
        _normalize_edges(cs)
        assert _by_name(cs)["consumer"].requires == ["producer"]

    def test_requires_to_synthesizable_coordinator_kept(self) -> None:
        # A requires target may resolve to a synthesizable head-absent
        # coordinator (>=2 members, no matching candidate).
        cs = [
            _candidate("p", composed_under="grp"),
            _candidate("q", composed_under="grp"),
            _candidate("consumer", requires=["grp"]),
        ]
        _normalize_edges(cs)
        assert _by_name(cs)["consumer"].requires == ["grp"]

    def test_requires_to_singleton_dangler_label_is_dropped(self) -> None:
        # The label degrades to flat (only one member), so it is not a valid
        # synthesizable target and the requires edge is dropped.
        cs = [
            _candidate("p", composed_under="grp"),
            _candidate("consumer", requires=["grp"]),
        ]
        _normalize_edges(cs)
        assert _by_name(cs)["consumer"].requires == []

    def test_duplicate_requires_deduplicated(self) -> None:
        cs = [_candidate("p"), _candidate("c", requires=["p", "p"])]
        _normalize_edges(cs)
        assert _by_name(cs)["c"].requires == ["p"]

    def test_mixed_valid_and_invalid_requires(self) -> None:
        cs = [
            _candidate("p", composed_under="grp"),
            _candidate("q", composed_under="grp"),
            _candidate("consumer", requires=["consumer", "p", "nope", "grp"]),
        ]
        _normalize_edges(cs)
        assert _by_name(cs)["consumer"].requires == ["p", "grp"]


# ---------------------------------------------------------------------------
# requires cycles
# ---------------------------------------------------------------------------


class TestRequiresCycles:
    def test_two_node_cycle_broken(self) -> None:
        cs = [_candidate("m", requires=["n"]), _candidate("n", requires=["m"])]
        _normalize_edges(cs)
        total = sum(len(c.requires) for c in cs)
        assert total == 1  # exactly one back-edge dropped

    def test_three_node_cycle_broken(self) -> None:
        cs = [
            _candidate("a", requires=["b"]),
            _candidate("b", requires=["c"]),
            _candidate("c", requires=["a"]),
        ]
        _normalize_edges(cs)
        total = sum(len(c.requires) for c in cs)
        assert total == 2

    def test_self_loop_removed_before_cycle_pass(self) -> None:
        cs = [_candidate("a", requires=["a"])]
        _normalize_edges(cs)
        assert cs[0].requires == []

    def test_dag_without_cycles_untouched(self) -> None:
        cs = [
            _candidate("a", requires=["b", "c"]),
            _candidate("b", requires=["c"]),
            _candidate("c"),
        ]
        _normalize_edges(cs)
        by = _by_name(cs)
        assert by["a"].requires == ["b", "c"]
        assert by["b"].requires == ["c"]

    def test_diamond_is_not_a_cycle(self) -> None:
        # a -> b, a -> c, b -> d, c -> d is a DAG; nothing should be dropped.
        cs = [
            _candidate("a", requires=["b", "c"]),
            _candidate("b", requires=["d"]),
            _candidate("c", requires=["d"]),
            _candidate("d"),
        ]
        _normalize_edges(cs)
        total = sum(len(c.requires) for c in cs)
        assert total == 4


# ---------------------------------------------------------------------------
# backward-compatibility / no-op
# ---------------------------------------------------------------------------


class TestBackwardCompatible:
    def test_no_edges_leaves_scope_untouched(self) -> None:
        cs = [_candidate("plain", scope="feature"), _candidate("other", scope="cross_feature")]
        _normalize_edges(cs)
        by = _by_name(cs)
        assert by["plain"].scope == "feature"
        assert by["other"].scope == "cross_feature"

    def test_empty_list_is_noop(self) -> None:
        cs: list[Candidate] = []
        assert _normalize_edges(cs) == []

    def test_returns_same_list_object(self) -> None:
        cs = [_candidate("a")]
        assert _normalize_edges(cs) is cs