"""Tests for the breadth-panel selection closure (Panel closure lever).

Exercise ``close_selection`` directly on synthetic candidate pools, so the two
ratified rules — requires-closure (R) and the coordinator toggle (C) — and their
fixpoint interaction are covered without an LLM, JSON, or the Dash surfaces.
"""

from __future__ import annotations

from spec4.agentifier.panel_closure import (
    ClosureResult,
    close_selection,
    pool_from_dicts,
)
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


# ---------------------------------------------------------------------------
# baseline
# ---------------------------------------------------------------------------


class TestBaseline:
    def test_empty_intent_selects_nothing(self) -> None:
        pool = [_candidate("a"), _candidate("b")]
        assert close_selection(pool, []).selected == set()

    def test_standalone_selection_passes_through(self) -> None:
        pool = [_candidate("a"), _candidate("b")]
        res = close_selection(pool, ["a"])
        assert res.selected == {"a"}
        assert res.required_producers == set()
        assert res.locked == set()

    def test_intent_names_absent_from_pool_are_ignored(self) -> None:
        pool = [_candidate("a")]
        assert close_selection(pool, ["a", "ghost"]).selected == {"a"}

    def test_idempotent_on_closed_set(self) -> None:
        # Closing an already-closed selection is a no-op — the backstop the
        # backend relies on when re-closing the panel's submitted value.
        pool = [
            _candidate("consumer", requires=["producer"]),
            _candidate("producer"),
            _candidate("m1", composed_under="coord"),
            _candidate("m2", composed_under="coord"),
            _candidate("coord"),
        ]
        once = close_selection(pool, ["consumer", "m1", "m2"]).selected
        twice = close_selection(pool, list(once)).selected
        assert once == twice


# ---------------------------------------------------------------------------
# requires-closure (R)
# ---------------------------------------------------------------------------


class TestRequires:
    def test_selected_dependent_pulls_in_producer_locked(self) -> None:
        pool = [_candidate("consumer", requires=["producer"]), _candidate("producer")]
        res = close_selection(pool, ["consumer"])
        assert res.selected == {"consumer", "producer"}
        assert "producer" in res.required_producers
        assert "producer" in res.locked

    def test_transitive_chain_pulls_the_whole_line(self) -> None:
        pool = [
            _candidate("c", requires=["b"]),
            _candidate("b", requires=["a"]),
            _candidate("a"),
        ]
        res = close_selection(pool, ["c"])
        assert res.selected == {"a", "b", "c"}
        assert res.required_producers == {"a", "b"}

    def test_producer_locked_even_when_user_also_picked_it(self) -> None:
        # A producer the developer independently picked is still locked while a
        # dependent needs it (so the panel disables it).
        pool = [_candidate("consumer", requires=["producer"]), _candidate("producer")]
        res = close_selection(pool, ["consumer", "producer"])
        assert res.selected == {"consumer", "producer"}
        assert "producer" in res.locked

    def test_producer_not_locked_without_a_selected_dependent(self) -> None:
        pool = [_candidate("consumer", requires=["producer"]), _candidate("producer")]
        res = close_selection(pool, ["producer"])
        assert res.selected == {"producer"}
        assert res.required_producers == set()

    def test_dangling_requires_target_is_skipped(self) -> None:
        pool = [_candidate("consumer", requires=["ghost"])]
        res = close_selection(pool, ["consumer"])
        assert res.selected == {"consumer"}
        assert res.required_producers == set()


# ---------------------------------------------------------------------------
# coordinator toggle (C)
# ---------------------------------------------------------------------------


def _grouped_pool() -> list[Candidate]:
    return [
        _candidate("coord"),
        _candidate("m1", scope="sub_feature", composed_under="coord"),
        _candidate("m2", scope="sub_feature", composed_under="coord"),
        _candidate("m3", scope="sub_feature", composed_under="coord"),
        _candidate("solo"),
    ]


class TestCoordinator:
    def test_two_members_turn_the_coordinator_on(self) -> None:
        res = close_selection(_grouped_pool(), ["m1", "m2"])
        assert "coord" in res.selected
        assert res.selected == {"m1", "m2", "coord"}

    def test_one_member_leaves_the_coordinator_off(self) -> None:
        res = close_selection(_grouped_pool(), ["m1"])
        assert "coord" not in res.selected
        assert res.selected == {"m1"}

    def test_coordinator_on_does_not_pull_unselected_members_in(self) -> None:
        # Optionality: turning the coordinator on adds only the coordinator, not
        # m3, which the developer left unchecked.
        res = close_selection(_grouped_pool(), ["m1", "m2"])
        assert "m3" not in res.selected

    def test_coordinator_is_never_seeded_from_intent(self) -> None:
        # Checking the coordinator directly with < 2 members does not turn it on.
        res = close_selection(_grouped_pool(), ["coord", "m1"])
        assert "coord" not in res.selected
        assert res.selected == {"m1"}

    def test_all_coordinators_are_locked(self) -> None:
        res = close_selection(_grouped_pool(), ["m1", "m2"])
        assert "coord" in res.coordinators
        assert "coord" in res.locked


# ---------------------------------------------------------------------------
# single-member head (not a coordinator)
# ---------------------------------------------------------------------------


class TestSingleMemberHead:
    """A head coordinating only one member is a normal, selectable candidate —
    not a derived coordinator (regression for the tier-09 peer-negotiation shape,
    where buyer_assistant/supplier_assistant each coordinate a single member and
    must remain directly selectable)."""

    def _peer_pool(self) -> list[Candidate]:
        return [
            _candidate("buyer_assistant"),
            _candidate("requirement_interp", composed_under="buyer_assistant"),
            _candidate("supplier_assistant"),
            _candidate("pricing_interp", composed_under="supplier_assistant"),
            _candidate("negotiation_strategy"),
        ]

    def test_single_member_head_is_not_a_coordinator(self) -> None:
        res = close_selection(self._peer_pool(), [])
        assert res.coordinators == set()

    def test_single_member_head_is_selectable_and_unlocked(self) -> None:
        res = close_selection(self._peer_pool(), ["buyer_assistant"])
        assert res.selected == {"buyer_assistant"}
        assert "buyer_assistant" not in res.locked

    def test_both_peers_selectable_together(self) -> None:
        res = close_selection(
            self._peer_pool(), ["buyer_assistant", "supplier_assistant"]
        )
        assert res.selected == {"buyer_assistant", "supplier_assistant"}
        assert res.locked == set()

    def test_lone_member_selectable_independently(self) -> None:
        res = close_selection(self._peer_pool(), ["requirement_interp"])
        assert res.selected == {"requirement_interp"}
        assert res.coordinators == set()

    def test_head_with_two_members_is_still_a_coordinator(self) -> None:
        pool = [
            _candidate("coord"),
            _candidate("m1", composed_under="coord"),
            _candidate("m2", composed_under="coord"),
        ]
        assert "coord" in close_selection(pool, []).coordinators


# ---------------------------------------------------------------------------
# R x C interaction (fixpoint)
# ---------------------------------------------------------------------------


class TestInteraction:
    def test_required_producer_that_is_a_member_flips_its_coordinator_on(self) -> None:
        # Selecting the consumer pulls in producer p2 (a member of coord); with
        # m1 also selected, coord now has two members and turns on.
        pool = [
            _candidate("consumer", requires=["p2"]),
            _candidate("coord"),
            _candidate("m1", composed_under="coord"),
            _candidate("p2", composed_under="coord"),
        ]
        res = close_selection(pool, ["consumer", "m1"])
        assert res.selected == {"consumer", "m1", "p2", "coord"}
        assert "p2" in res.required_producers

    def test_derived_coordinator_that_is_a_member_flips_a_higher_one(self) -> None:
        # inner turns on from its two members; inner is itself a member of outer,
        # and with sib also selected, outer has two members and turns on too.
        pool = [
            _candidate("outer"),
            _candidate("inner", composed_under="outer"),
            _candidate("sib", composed_under="outer"),
            _candidate("a", composed_under="inner"),
            _candidate("b", composed_under="inner"),
        ]
        res = close_selection(pool, ["a", "b", "sib"])
        assert "inner" in res.selected
        assert "outer" in res.selected

    def test_required_coordinator_stays_on_below_two_members(self) -> None:
        # A dependent that requires a coordinator's output holds it on even
        # though only one of its members is selected (data-dependency wins over
        # the >= 2-member rule).
        pool = [
            _candidate("consumer", requires=["coord"]),
            _candidate("coord"),
            _candidate("m1", composed_under="coord"),
            _candidate("m2", composed_under="coord"),
        ]
        res = close_selection(pool, ["consumer", "m1"])
        assert "coord" in res.selected
        assert "coord" in res.required_producers


# ---------------------------------------------------------------------------
# ClosureResult / pool_from_dicts
# ---------------------------------------------------------------------------


class TestResultAndReconstruction:
    def test_locked_unions_producers_and_coordinators(self) -> None:
        res = ClosureResult(
            selected={"x"},
            required_producers={"p"},
            coordinators={"c"},
        )
        assert res.locked == {"p", "c"}

    def test_pool_from_dicts_reads_edges(self) -> None:
        pool = pool_from_dicts(
            [
                {"name": "consumer", "requires": ["producer"]},
                {"name": "producer"},
                {"name": "m1", "composed_under": "coord"},
                {"name": "", "requires": ["x"]},  # nameless: dropped
            ]
        )
        by = {c.name: c for c in pool}
        assert set(by) == {"consumer", "producer", "m1"}
        assert by["consumer"].requires == ["producer"]
        assert by["m1"].composed_under == "coord"

    def test_pool_from_dicts_output_closes(self) -> None:
        pool = pool_from_dicts(
            [
                {"name": "consumer", "requires": ["producer"]},
                {"name": "producer"},
            ]
        )
        assert close_selection(pool, ["consumer"]).selected == {"consumer", "producer"}