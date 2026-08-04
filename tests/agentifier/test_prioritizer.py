"""Tests for the Prioritizer sub-agent.

The Prioritizer assigns ``phase_priority`` over the closed AI-feature set,
emitting a priority *overlay*, which a deterministic pass then repairs against
the graph the Linker wired (D-PP7). These cover overlay parsing (the OK / EMPTY /
UNREADABLE outcomes and the single reparse), the authoritative overlay merge,
the three normalization rules, and the agent's request shape.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock, patch

from spec4.agentifier.prioritizer import (
    DEFAULT_PRIORITY,
    PrioritizerAgent,
    PrioritizerInput,
    PrioritizerOutcome,
    PrioritizerOutput,
    _parse_overlay,
    apply_overlay,
    normalize_priorities,
)

_LLM_CONFIG = {"model": "test-model", "api_key": "sk-test"}


def _feature(
    name: str,
    priority: str | None = "mvp",
    composed_under: str = "",
    requires: list[str] | None = None,
    **kw: Any,
) -> dict[str, Any]:
    f: dict[str, Any] = {
        "name": name,
        "tier": "single_call",
        "rough_description": f"{name} description.",
        "linked_vision_features": [],
        "composed_under": composed_under,
        "requires": list(requires or []),
    }
    if priority is not None:
        f["phase_priority"] = priority
    f.update(kw)
    return f


def _make_mock_response(content: str) -> MagicMock:
    response = MagicMock()
    response.choices[0].message.content = content
    return response


def _priorities(features: list[dict[str, Any]]) -> dict[str, str]:
    return {f["name"]: f["phase_priority"] for f in features}


# ---------------------------------------------------------------------------
# _parse_overlay
# ---------------------------------------------------------------------------


class TestParseOverlay:
    def test_valid_object_is_ok(self) -> None:
        raw = json.dumps({"a": "steel_thread", "b": "mvp"})
        overlay, outcome = _parse_overlay(raw)
        assert outcome is PrioritizerOutcome.OK
        assert overlay == {"a": "steel_thread", "b": "mvp"}

    def test_object_embedded_in_prose_is_extracted(self) -> None:
        raw = 'Here you go:\n```json\n{"a": "v2"}\n```\nDone.'
        overlay, outcome = _parse_overlay(raw)
        assert outcome is PrioritizerOutcome.OK
        assert overlay == {"a": "v2"}

    def test_off_enum_values_are_dropped(self) -> None:
        raw = json.dumps({"a": "p0", "b": "future"})
        overlay, outcome = _parse_overlay(raw)
        assert outcome is PrioritizerOutcome.OK
        assert overlay == {"b": "future"}

    def test_readable_object_with_no_valid_value_is_empty(self) -> None:
        raw = json.dumps({"a": "p0", "b": 3})
        overlay, outcome = _parse_overlay(raw)
        assert outcome is PrioritizerOutcome.EMPTY
        assert overlay == {}

    def test_empty_object_is_empty(self) -> None:
        overlay, outcome = _parse_overlay("{}")
        assert outcome is PrioritizerOutcome.EMPTY
        assert overlay == {}

    def test_unparseable_is_unreadable(self) -> None:
        overlay, outcome = _parse_overlay("no json here at all")
        assert outcome is PrioritizerOutcome.UNREADABLE
        assert overlay == {}

    def test_json_array_is_unreadable(self) -> None:
        _, outcome = _parse_overlay("[1, 2, 3]")
        assert outcome is PrioritizerOutcome.UNREADABLE


# ---------------------------------------------------------------------------
# Rule 1 — invalid degrades to mvp
# ---------------------------------------------------------------------------


class TestRuleOneDefaults:
    def test_missing_priority_degrades_to_mvp(self) -> None:
        feats = [_feature("a", priority=None)]
        normalize_priorities(feats)
        assert feats[0]["phase_priority"] == DEFAULT_PRIORITY

    def test_off_enum_priority_degrades_to_mvp(self) -> None:
        feats = [_feature("a", priority="p0")]
        normalize_priorities(feats)
        assert feats[0]["phase_priority"] == DEFAULT_PRIORITY

    def test_non_string_priority_degrades_to_mvp(self) -> None:
        feats = [_feature("a", priority=None)]
        feats[0]["phase_priority"] = 3
        normalize_priorities(feats)
        assert feats[0]["phase_priority"] == DEFAULT_PRIORITY

    def test_valid_priority_untouched(self) -> None:
        feats = [_feature("a", priority="future")]
        normalize_priorities(feats)
        assert feats[0]["phase_priority"] == "future"


# ---------------------------------------------------------------------------
# Rule 2 — requires-monotonicity (promote the producer)
# ---------------------------------------------------------------------------


class TestRuleTwoRequires:
    def test_producer_promoted_to_consumer_priority(self) -> None:
        feats = [
            _feature("producer", "mvp"),
            _feature("consumer", "steel_thread", requires=["producer"]),
        ]
        normalize_priorities(feats)
        assert _priorities(feats)["producer"] == "steel_thread"

    def test_consumer_never_demoted(self) -> None:
        feats = [
            _feature("producer", "future"),
            _feature("consumer", "steel_thread", requires=["producer"]),
        ]
        normalize_priorities(feats)
        assert _priorities(feats)["consumer"] == "steel_thread"

    def test_producer_earlier_than_consumer_is_left_alone(self) -> None:
        feats = [
            _feature("producer", "steel_thread"),
            _feature("consumer", "mvp", requires=["producer"]),
        ]
        normalize_priorities(feats)
        assert _priorities(feats) == {
            "producer": "steel_thread",
            "consumer": "mvp",
        }

    def test_promotion_runs_to_fixpoint_along_a_chain(self) -> None:
        # c -> b -> a; only c is steel_thread, so the whole chain comes forward.
        feats = [
            _feature("a", "future"),
            _feature("b", "v2", requires=["a"]),
            _feature("c", "steel_thread", requires=["b"]),
        ]
        normalize_priorities(feats)
        assert _priorities(feats) == {
            "a": "steel_thread",
            "b": "steel_thread",
            "c": "steel_thread",
        }

    def test_dangling_requires_target_is_ignored(self) -> None:
        feats = [_feature("consumer", "steel_thread", requires=["ghost"])]
        normalize_priorities(feats)
        assert _priorities(feats)["consumer"] == "steel_thread"

    def test_diamond_promotes_shared_producer_once(self) -> None:
        feats = [
            _feature("base", "v2"),
            _feature("left", "steel_thread", requires=["base"]),
            _feature("right", "mvp", requires=["base"]),
        ]
        normalize_priorities(feats)
        assert _priorities(feats)["base"] == "steel_thread"


# ---------------------------------------------------------------------------
# Rule 3(iv) — coordinator sits at its second-earliest member
# ---------------------------------------------------------------------------


class TestRuleThreeCoordinator:
    def test_head_placed_at_second_earliest_member(self) -> None:
        # The observed corpus shape: an mvp head over a steel_thread member is
        # CORRECT and must not move.
        feats = [
            _feature("pipeline", "mvp"),
            _feature("parsing", "steel_thread", composed_under="pipeline"),
            _feature("summarize", "mvp", composed_under="pipeline"),
            _feature("digest", "mvp", composed_under="pipeline"),
        ]
        normalize_priorities(feats)
        assert _priorities(feats)["pipeline"] == "mvp"

    def test_head_scheduled_too_early_is_demoted(self) -> None:
        feats = [
            _feature("head", "steel_thread"),
            _feature("m1", "steel_thread", composed_under="head"),
            _feature("m2", "v2", composed_under="head"),
        ]
        normalize_priorities(feats)
        assert _priorities(feats)["head"] == "v2"

    def test_head_scheduled_too_late_is_promoted(self) -> None:
        feats = [
            _feature("head", "future"),
            _feature("m1", "steel_thread", composed_under="head"),
            _feature("m2", "mvp", composed_under="head"),
        ]
        normalize_priorities(feats)
        assert _priorities(feats)["head"] == "mvp"

    def test_single_member_group_leaves_head_alone(self) -> None:
        # panel_closure derives no head below two members.
        feats = [
            _feature("head", "future"),
            _feature("only", "steel_thread", composed_under="head"),
        ]
        normalize_priorities(feats)
        assert _priorities(feats)["head"] == "future"

    def test_unmaterialised_head_label_is_ignored(self) -> None:
        feats = [
            _feature("m1", "steel_thread", composed_under="ghost_head"),
            _feature("m2", "mvp", composed_under="ghost_head"),
        ]
        normalize_priorities(feats)
        assert _priorities(feats) == {"m1": "steel_thread", "m2": "mvp"}

    def test_members_keep_their_own_priorities(self) -> None:
        feats = [
            _feature("head", "steel_thread"),
            _feature("m1", "steel_thread", composed_under="head"),
            _feature("m2", "v2", composed_under="head"),
        ]
        normalize_priorities(feats)
        assert _priorities(feats)["m1"] == "steel_thread"
        assert _priorities(feats)["m2"] == "v2"


# ---------------------------------------------------------------------------
# Rule precedence and convergence
# ---------------------------------------------------------------------------


class TestPrecedenceAndConvergence:
    def test_requires_wins_over_coordinator_placement(self) -> None:
        # Rule 3 would place `head` at v2 (its 2nd member), but a steel_thread
        # consumer requires it. A requires edge is a hard build dependency.
        feats = [
            _feature("head", "mvp"),
            _feature("m1", "steel_thread", composed_under="head"),
            _feature("m2", "v2", composed_under="head"),
            _feature("consumer", "steel_thread", requires=["head"]),
        ]
        normalize_priorities(feats)
        assert _priorities(feats)["head"] == "steel_thread"

    def test_normalization_terminates_on_adversarial_graph(self) -> None:
        feats = [
            _feature("head", "future"),
            _feature("m1", "steel_thread", composed_under="head"),
            _feature("m2", "future", composed_under="head", requires=["head"]),
            _feature("c", "steel_thread", requires=["head"]),
        ]
        normalize_priorities(feats)  # must not hang
        # No unbuildable edge survives: every producer is no later than its
        # consumer.
        prio = _priorities(feats)
        rank = {"steel_thread": 0, "mvp": 1, "v2": 2, "future": 3}
        for f in feats:
            for p in f["requires"]:
                if p in prio:
                    assert rank[prio[p]] <= rank[prio[f["name"]]]

    def test_every_feature_ends_with_a_valid_priority(self) -> None:
        feats = [_feature("a", priority=None), _feature("b", priority="nonsense")]
        normalize_priorities(feats)
        for f in feats:
            assert f["phase_priority"] in ("steel_thread", "mvp", "v2", "future")


# ---------------------------------------------------------------------------
# Carried-forward features are frozen (D-PP11)
# ---------------------------------------------------------------------------


class TestCarriedForwardFrozen:
    def test_carried_producer_is_never_promoted(self) -> None:
        feats = [
            _feature("built", "future"),
            _feature("new", "steel_thread", requires=["built"]),
        ]
        normalize_priorities(feats, frozenset({"built"}))
        assert _priorities(feats)["built"] == "future"
        assert _priorities(feats)["new"] == "steel_thread"

    def test_carried_head_is_never_repositioned(self) -> None:
        feats = [
            _feature("built_head", "future"),
            _feature("m1", "steel_thread", composed_under="built_head"),
            _feature("m2", "mvp", composed_under="built_head"),
        ]
        normalize_priorities(feats, frozenset({"built_head"}))
        assert _priorities(feats)["built_head"] == "future"

    def test_carried_invalid_priority_is_not_degraded(self) -> None:
        feats = [_feature("built", priority=None)]
        normalize_priorities(feats, frozenset({"built"}))
        assert "phase_priority" not in feats[0]

    def test_carried_member_counts_toward_group_size(self) -> None:
        # `built` is already implemented and ranks below every priority, so the
        # group's SECOND member is `m1` — the head arrives when `m1` does.
        feats = [
            _feature("head", "future"),
            _feature("built", "mvp", composed_under="head"),
            _feature("m1", "v2", composed_under="head"),
        ]
        normalize_priorities(feats, frozenset({"built"}))
        assert _priorities(feats)["head"] == "v2"
        assert _priorities(feats)["built"] == "mvp"

    def test_group_of_only_carried_members_clamps_to_first_phase(self) -> None:
        # Both members already built ⇒ nothing blocks the head; it cannot be
        # scheduled earlier than the first phase.
        feats = [
            _feature("head", "future"),
            _feature("b1", "mvp", composed_under="head"),
            _feature("b2", "mvp", composed_under="head"),
        ]
        normalize_priorities(feats, frozenset({"b1", "b2"}))
        assert _priorities(feats)["head"] == "steel_thread"

    def test_single_live_member_leaves_head_alone(self) -> None:
        feats = [
            _feature("head", "future"),
            _feature("m1", "steel_thread", composed_under="head"),
        ]
        normalize_priorities(feats, frozenset())
        assert _priorities(feats)["head"] == "future"


# ---------------------------------------------------------------------------
# apply_overlay
# ---------------------------------------------------------------------------


class TestApplyOverlay:
    def test_overlay_is_authoritative(self) -> None:
        feats = [_feature("a", "future"), _feature("b", "steel_thread")]
        apply_overlay(feats, {"a": "steel_thread", "b": "mvp"})
        assert _priorities(feats) == {"a": "steel_thread", "b": "mvp"}

    def test_omitted_feature_defaults_to_mvp(self) -> None:
        feats = [_feature("a", "future"), _feature("b", "v2")]
        apply_overlay(feats, {"a": "steel_thread"})
        assert _priorities(feats)["b"] == DEFAULT_PRIORITY

    def test_empty_overlay_gives_all_mvp(self) -> None:
        feats = [_feature("a", "future"), _feature("b", "v2")]
        apply_overlay(feats, {})
        assert set(_priorities(feats).values()) == {DEFAULT_PRIORITY}

    def test_carried_feature_keeps_its_value(self) -> None:
        feats = [_feature("built", "v2"), _feature("new", "mvp")]
        apply_overlay(feats, {"built": "steel_thread"}, frozenset({"built"}))
        assert _priorities(feats)["built"] == "v2"

    def test_normalization_runs_after_merge(self) -> None:
        feats = [
            _feature("producer", "mvp"),
            _feature("consumer", "mvp", requires=["producer"]),
        ]
        apply_overlay(feats, {"consumer": "steel_thread", "producer": "v2"})
        assert _priorities(feats)["producer"] == "steel_thread"

    def test_returns_the_same_list_object(self) -> None:
        feats = [_feature("a")]
        assert apply_overlay(feats, {"a": "mvp"}) is feats


# ---------------------------------------------------------------------------
# PrioritizerAgent.run
# ---------------------------------------------------------------------------


class TestPrioritizerAgentRun:
    def _input(self) -> PrioritizerInput:
        return PrioritizerInput(
            features=[_feature("producer"), _feature("consumer")],
            vision_purpose="A project.",
            llm_config=_LLM_CONFIG,
        )

    def test_ok_path_returns_overlay(self) -> None:
        raw = json.dumps({"producer": "steel_thread", "consumer": "mvp"})
        with patch(
            "spec4.agentifier.prioritizer.complete",
            return_value=_make_mock_response(raw),
        ):
            out = asyncio.run(PrioritizerAgent().run(self._input()))
        assert isinstance(out, PrioritizerOutput)
        assert out.outcome is PrioritizerOutcome.OK
        assert out.overlay == {"producer": "steel_thread", "consumer": "mvp"}

    def test_reparse_once_on_unreadable_then_ok(self) -> None:
        good = json.dumps({"producer": "mvp"})
        responses = [_make_mock_response("garbage"), _make_mock_response(good)]
        with patch(
            "spec4.agentifier.prioritizer.complete",
            side_effect=responses,
        ) as mock_llm:
            out = asyncio.run(PrioritizerAgent().run(self._input()))
        assert mock_llm.call_count == 2
        assert out.outcome is PrioritizerOutcome.OK

    def test_unreadable_after_reparse_gives_up(self) -> None:
        responses = [_make_mock_response("garbage"), _make_mock_response("still bad")]
        with patch(
            "spec4.agentifier.prioritizer.complete",
            side_effect=responses,
        ) as mock_llm:
            out = asyncio.run(PrioritizerAgent().run(self._input()))
        assert mock_llm.call_count == 2
        assert out.outcome is PrioritizerOutcome.UNREADABLE

    def test_empty_overlay_is_not_retried(self) -> None:
        with patch(
            "spec4.agentifier.prioritizer.complete",
            return_value=_make_mock_response("{}"),
        ) as mock_llm:
            out = asyncio.run(PrioritizerAgent().run(self._input()))
        assert mock_llm.call_count == 1
        assert out.outcome is PrioritizerOutcome.EMPTY

    def test_prompt_carries_edges_and_carried_context(self) -> None:
        pi = PrioritizerInput(
            features=[
                _feature("head"),
                _feature("member", composed_under="head", requires=["built"]),
            ],
            vision_purpose="Ship a thing.",
            llm_config=_LLM_CONFIG,
            carried_forward=[_feature("built")],
        )
        with patch(
            "spec4.agentifier.prioritizer.complete",
            return_value=_make_mock_response(json.dumps({"head": "mvp"})),
        ) as mock_llm:
            asyncio.run(PrioritizerAgent().run(pi))
        user_msg = mock_llm.call_args.kwargs["messages"][1]["content"]
        assert "Ship a thing." in user_msg
        assert "composed_under: head" in user_msg
        assert "requires: built" in user_msg
        assert "ALREADY BUILT" in user_msg
        assert "built" in user_msg


# ---------------------------------------------------------------------------
# Orchestrator integration — _begin_priority_phase
# ---------------------------------------------------------------------------


def _session(features: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    session: dict[str, Any] = {
        "agentifier_messages": [],
        "ai_features": {"ai_features": features},
        "vision_statement": {"vision": {"purpose": "Ship a thing."}},
    }
    session.update(kw)
    return session


class TestBeginPriorityPhase:
    def _run(self, session: dict[str, Any]) -> str:
        from spec4.agentifier.agentifier import _begin_priority_phase

        return "".join(_begin_priority_phase(session, _LLM_CONFIG))

    def test_overlay_lands_on_the_feature_set(self, stub_prioritizer: Any) -> None:
        stub_prioritizer.side_effect = None
        stub_prioritizer.return_value = PrioritizerOutput(
            overlay={"a": "steel_thread", "b": "mvp"}, outcome=PrioritizerOutcome.OK
        )
        session = _session([_feature("a"), _feature("b")])
        self._run(session)
        feats = session["ai_features"]["ai_features"]
        assert _priorities(feats) == {"a": "steel_thread", "b": "mvp"}

    def test_normalization_runs_on_the_overlay(self, stub_prioritizer: Any) -> None:
        stub_prioritizer.side_effect = None
        stub_prioritizer.return_value = PrioritizerOutput(
            overlay={"producer": "v2", "consumer": "steel_thread"},
            outcome=PrioritizerOutcome.OK,
        )
        session = _session(
            [_feature("producer"), _feature("consumer", requires=["producer"])]
        )
        self._run(session)
        feats = session["ai_features"]["ai_features"]
        assert _priorities(feats)["producer"] == "steel_thread"

    def test_draw_failure_degrades_to_mvp_with_a_banner(
        self, stub_prioritizer: Any
    ) -> None:
        stub_prioritizer.side_effect = RuntimeError("boom")
        session = _session([_feature("a"), _feature("b")])
        out = self._run(session)
        assert "Priority analysis unavailable" in out
        feats = session["ai_features"]["ai_features"]
        assert set(_priorities(feats).values()) == {DEFAULT_PRIORITY}

    def test_unreadable_outcome_shows_the_banner(self, stub_prioritizer: Any) -> None:
        stub_prioritizer.side_effect = None
        stub_prioritizer.return_value = PrioritizerOutput(
            overlay={}, outcome=PrioritizerOutcome.UNREADABLE
        )
        session = _session([_feature("a")])
        assert "Priority analysis unavailable" in self._run(session)

    def test_ok_outcome_shows_no_banner(self, stub_prioritizer: Any) -> None:
        session = _session([_feature("a")])
        out = self._run(session)
        assert "Priority analysis unavailable" not in out
        assert "### Phase priority" in out

    def test_carried_forward_names_are_passed_and_frozen(
        self, stub_prioritizer: Any
    ) -> None:
        stub_prioritizer.side_effect = None
        stub_prioritizer.return_value = PrioritizerOutput(
            overlay={"new": "steel_thread"}, outcome=PrioritizerOutcome.OK
        )
        session = _session(
            [_feature("new", requires=["built"])],
            agentifier_carried_forward=[_feature("built", "future")],
        )
        self._run(session)
        # `built` is already implemented, so the steel_thread consumer does not
        # promote it — and it never enters this round's feature list.
        assert stub_prioritizer.call_args.args[3][0]["name"] == "built"
        feats = session["ai_features"]["ai_features"]
        assert _priorities(feats) == {"new": "steel_thread"}

    def test_empty_feature_set_short_circuits(self) -> None:
        session = _session([])
        session["agentifier_messages"] = []
        out = self._run(session)
        assert "Priority analysis unavailable" not in out

# ---------------------------------------------------------------------------
# The priority checkpoint — one table, one turn (D-PP9 B)
# ---------------------------------------------------------------------------


class TestParsePriorityEdits:
    def _parse(self, text: str, names: set[str] | None = None) -> Any:
        from spec4.agentifier.agentifier import _parse_priority_edits

        return _parse_priority_edits(text, names or {"alpha", "beta"})

    def test_colon_form(self) -> None:
        assert self._parse("alpha: steel_thread").assignments == {
            "alpha": "steel_thread"
        }

    def test_arrow_and_equals_forms(self) -> None:
        assert self._parse("alpha -> v2").assignments == {"alpha": "v2"}
        assert self._parse("alpha = future").assignments == {"alpha": "future"}

    def test_multiple_lines(self) -> None:
        edits = self._parse("alpha: steel_thread\nbeta: v2")
        assert edits.assignments == {"alpha": "steel_thread", "beta": "v2"}

    def test_semicolon_separated(self) -> None:
        edits = self._parse("alpha: mvp; beta: future")
        assert edits.assignments == {"alpha": "mvp", "beta": "future"}

    def test_spaced_and_hyphenated_values_normalise(self) -> None:
        # The display writes `steel_thread`; people type what they read.
        assert self._parse("alpha: steel thread").assignments == {
            "alpha": "steel_thread"
        }
        assert self._parse("alpha: Steel-Thread").assignments == {
            "alpha": "steel_thread"
        }

    def test_bullets_and_bold_are_tolerated(self) -> None:
        edits = self._parse("- **alpha**: `mvp`")
        assert edits.assignments == {"alpha": "mvp"}

    def test_unknown_feature_is_reported_not_applied(self) -> None:
        edits = self._parse("ghost: mvp")
        assert edits.assignments == {}
        assert edits.unknown_names == ["ghost"]
        assert edits.saw_pair

    def test_bad_value_is_reported(self) -> None:
        edits = self._parse("alpha: p0")
        assert edits.assignments == {}
        assert edits.bad_values == [("alpha", "p0")]
        assert edits.saw_pair

    def test_valid_edit_alongside_a_bad_one(self) -> None:
        edits = self._parse("alpha: mvp\nghost: v2")
        assert edits.assignments == {"alpha": "mvp"}
        assert edits.unknown_names == ["ghost"]

    def test_prose_has_no_pair(self) -> None:
        edits = self._parse("no, defer that one please")
        assert not edits.saw_pair

    def test_bare_affirmative_has_no_pair(self) -> None:
        assert not self._parse("yes").saw_pair


class TestRunPriorityPhase:
    def _run(self, session: dict[str, Any], text: str | None) -> str:
        from spec4.agentifier.agentifier import _run_priority_phase

        return "".join(_run_priority_phase(text, session, _LLM_CONFIG))

    def _session_with(self, features: list[dict[str, Any]]) -> dict[str, Any]:
        s = _session(features)
        s["agentifier_messages"] = [{"role": "assistant", "content": "table"}]
        return s

    def test_affirmative_completes_the_phase(self) -> None:
        session = self._session_with([_feature("alpha")])
        self._run(session, "yes")
        assert session.get("agentifier_priority_done") is True

    def test_edit_is_applied_and_phase_stays_open(self) -> None:
        session = self._session_with([_feature("alpha", "mvp")])
        self._run(session, "alpha: v2")
        feats = session["ai_features"]["ai_features"]
        assert _priorities(feats)["alpha"] == "v2"
        assert not session.get("agentifier_priority_done")

    def test_unrecognised_reply_never_advances_and_says_so(self) -> None:
        # Defect 2: the old walk swallowed this and moved on.
        session = self._session_with([_feature("alpha", "mvp")])
        out = self._run(session, "no, defer that one")
        assert "couldn't read that" in out
        assert not session.get("agentifier_priority_done")
        assert _priorities(session["ai_features"]["ai_features"])["alpha"] == "mvp"

    def test_edit_wins_over_affirmative_prefix_collision(self) -> None:
        # `_is_spec_confirmed` matches on a prefix: "next_step..." starts with
        # "next". Reading edits first is what stops that ending the phase.
        session = self._session_with([_feature("next_step_planner", "mvp")])
        self._run(session, "next_step_planner: v2")
        assert not session.get("agentifier_priority_done")
        feats = session["ai_features"]["ai_features"]
        assert _priorities(feats)["next_step_planner"] == "v2"

    def test_edit_triggers_renormalization(self) -> None:
        session = self._session_with(
            [
                _feature("producer", "mvp"),
                _feature("consumer", "mvp", requires=["producer"]),
            ]
        )
        out = self._run(session, "consumer: steel_thread")
        feats = session["ai_features"]["ai_features"]
        assert _priorities(feats)["producer"] == "steel_thread"
        assert "Adjusted" in out
        assert "`producer`" in out

    def test_unchanged_features_are_not_reported_as_adjusted(self) -> None:
        session = self._session_with([_feature("alpha", "mvp"), _feature("beta", "mvp")])
        out = self._run(session, "alpha: v2")
        assert "Adjusted" not in out
        assert "Updated" in out

    def test_unknown_name_is_surfaced(self) -> None:
        session = self._session_with([_feature("alpha", "mvp")])
        out = self._run(session, "ghost: v2")
        assert "No such feature" in out
        assert not session.get("agentifier_priority_done")

    def test_bad_value_is_surfaced(self) -> None:
        session = self._session_with([_feature("alpha", "mvp")])
        out = self._run(session, "alpha: p0")
        assert "Not a priority" in out
        assert _priorities(session["ai_features"]["ai_features"])["alpha"] == "mvp"

    def test_none_input_replays(self) -> None:
        session = self._session_with([_feature("alpha")])
        assert "table" in self._run(session, None)

    def test_carried_features_are_not_moved_by_renormalization(self) -> None:
        session = self._session_with([_feature("new", "mvp", requires=["built"])])
        session["agentifier_carried_forward"] = [_feature("built", "future")]
        self._run(session, "new: steel_thread")
        assert _priorities(session["ai_features"]["ai_features"]) == {
            "new": "steel_thread"
        }


class TestFormatPriorityTable:
    def _table(self, features: list[dict[str, Any]]) -> str:
        from spec4.agentifier.agentifier import _format_priority_table

        return _format_priority_table(features)

    def test_rows_are_ordered_by_priority(self) -> None:
        out = self._table(
            [_feature("late", "future"), _feature("early", "steel_thread")]
        )
        assert out.index("**early**") < out.index("**late**")

    def test_steel_thread_is_summarised(self) -> None:
        out = self._table([_feature("a", "steel_thread"), _feature("b", "mvp")])
        assert "Steel thread" in out
        assert "`a`" in out

    def test_empty_steel_thread_is_called_out(self) -> None:
        out = self._table([_feature("a", "mvp")])
        assert "nothing assigned yet" in out

    def test_group_column_appears_only_when_grouped(self) -> None:
        flat = self._table([_feature("a", "mvp")])
        assert "Part of" not in flat
        grouped = self._table(
            [_feature("head", "mvp"), _feature("m", "mvp", composed_under="head")]
        )
        assert "Part of" in grouped

    def test_no_deferral_nag(self) -> None:
        # The old walk pressed the developer on every v2/future. It shouldn't.
        out = self._table([_feature("a", "future")])
        assert "never ship" not in out

    def test_example_names_a_feature_not_already_in_the_thread(self) -> None:
        out = self._table([_feature("a", "steel_thread"), _feature("b", "mvp")])
        assert "b: steel_thread" in out

    def test_empty_feature_list_does_not_raise(self) -> None:
        assert "feature_name: steel_thread" in self._table([])

# ---------------------------------------------------------------------------
# D-PP14 — vision MVP commitments reach the prompt
# ---------------------------------------------------------------------------


def _vision(entries: Any) -> dict[str, Any]:
    return {"vision_statement": {"vision": {"key_features_mvp": entries}}}


class TestVisionMvpFeatureNames:
    def _names(self, vision: dict[str, Any]) -> list[str]:
        from spec4.agentifier.agentifier import _vision_mvp_feature_names

        return _vision_mvp_feature_names(vision)

    def test_single_key_mapping_is_the_brainstormer_shape(self) -> None:
        vision = _vision([{"Order_Help_Chat": {"description": "…"}}, {"Account_Orders": {}}])
        assert self._names(vision) == ["Order_Help_Chat", "Account_Orders"]

    def test_plain_strings_and_named_mappings(self) -> None:
        assert self._names(_vision(["Plain", {"name": "Named"}])) == ["Plain", "Named"]

    def test_unrecognised_entries_are_skipped_not_fatal(self) -> None:
        assert self._names(_vision([7, {"a": 1, "b": 2}, "Good"])) == ["Good"]

    def test_missing_or_malformed_vision_gives_empty(self) -> None:
        assert self._names({}) == []
        assert self._names(_vision("not a list")) == []
        assert self._names({"vision_statement": {"vision": {}}}) == []


class TestMvpMarking:
    def _block(self, features: list[dict[str, Any]], committed: list[str]) -> str:
        from spec4.agentifier.prioritizer import _format_features_block

        return _format_features_block(features, [], "purpose", committed)

    def _feature_lines(self, features: list[dict[str, Any]], committed: list[str]) -> str:
        # The preamble mentions "[MVP]" literally; only the rows carry the mark.
        block = self._block(features, committed)
        return "\n".join(ln for ln in block.splitlines() if ln.startswith("- "))

    def test_committed_top_level_feature_is_marked(self) -> None:
        f = _feature("writeup", linked_vision_features=["findings_writeup"], scope="feature")
        assert "writeup [MVP]" in self._block([f], ["findings_writeup"])

    def test_cross_feature_scope_is_marked(self) -> None:
        f = _feature("x", linked_vision_features=["cap"], scope="cross_feature")
        assert "x [MVP]" in self._block([f], ["cap"])

    def test_sub_feature_is_never_marked(self) -> None:
        # linked_vision_features is provenance, not commitment: every member of a
        # decomposed capability traces back to the same vision entry.
        f = _feature("member", linked_vision_features=["investigation"], scope="sub_feature")
        assert "[MVP]" not in self._feature_lines([f], ["investigation"])

    def test_unlinked_feature_is_not_marked(self) -> None:
        f = _feature("extra", linked_vision_features=["something_else"], scope="feature")
        assert "[MVP]" not in self._feature_lines([f], ["investigation"])

    def test_preamble_lists_committed_capabilities(self) -> None:
        out = self._block([_feature("a", scope="feature")], ["cap_one", "cap_two"])
        assert "part of the first release" in out
        assert "cap_one, cap_two" in out

    def test_no_commitments_means_no_preamble_and_no_marks(self) -> None:
        out = self._block([_feature("a", linked_vision_features=["cap"], scope="feature")], [])
        assert "part of the first release" not in out
        assert "[MVP]" not in out

    def test_agent_passes_commitments_into_the_prompt(self) -> None:
        pi = PrioritizerInput(
            features=[_feature("writeup", linked_vision_features=["fw"], scope="feature")],
            vision_purpose="Ship it.",
            llm_config=_LLM_CONFIG,
            mvp_vision_features=["fw"],
        )
        with patch(
            "spec4.agentifier.prioritizer.complete",
            return_value=_make_mock_response(json.dumps({"writeup": "mvp"})),
        ) as mock_llm:
            asyncio.run(PrioritizerAgent().run(pi))
        user_msg = mock_llm.call_args.kwargs["messages"][1]["content"]
        assert "writeup [MVP]" in user_msg

    def test_commitments_default_to_empty(self) -> None:
        pi = PrioritizerInput(features=[], vision_purpose="", llm_config=_LLM_CONFIG)
        assert pi.mvp_vision_features == []