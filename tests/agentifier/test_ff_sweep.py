"""D-AF series — Fast Forward sweep for the Python-paced Agentifier phases.

The spec and cross-cutting phases are Python loops (one feature / one topic
per user turn), so the FF sweep cannot be an LLM behaviour: the loop itself
must recognise the request. Ratified semantics:

* D-AF1: detection is an exact string match against ``FF_PROMPT`` — typed
  and button-clicked requests stay equivalent, and the check runs BEFORE the
  pending/revision branches so a press can never be read as a revision
  instruction for the current item.
* D-AF2: the spec sweep drafts every remaining feature in one turn (same N
  subagent calls, unpaced) then presents one comprehensive review. Revisions
  route deterministically as ``feature_name: instruction`` lines; anything
  unmatched re-prompts with the valid names and changes nothing (atomic).
* D-AF3: the cross-cutting sweep records the already-computed analysis for
  every remaining topic and presents one review. Skippable topics are
  accepted, not skipped — skipping is a user prerogative.
* D-AF4: items confirmed before the sweep are locked: shown read-only in the
  review, not revisable.
"""

import json
from typing import Any
from unittest.mock import patch

from spec4.agentifier.agentifier import (
    _run_cross_cutting_phase,
    _run_spec_phase,
)
from spec4.app_constants import FF_PROMPT


def _collect(gen: Any) -> str:
    return "".join(gen)


def _fake_stream(calls: list[Any], payload_for: Any) -> Any:
    """Fake _registry.stream capturing input objects and yielding fenced JSON."""

    def _stream(name: str, input_obj: Any) -> Any:
        calls.append((name, input_obj))

        async def _gen() -> Any:
            yield "```json\n" + json.dumps(payload_for(name, input_obj)) + "\n```"

        return _gen()

    return _stream


# ---------------------------------------------------------------------------
# Spec phase
# ---------------------------------------------------------------------------


def _spec_session(
    n: int = 3,
    spec_index: int = 0,
    results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    names = ["alpha_feat", "beta_feat", "gamma_feat"][:n]
    return {
        "agentifier_messages": [],
        "agentifier_catalog_done": True,
        "ai_catalog": {
            "ai_catalog": [
                {"name": nm, "recommended_tier": "single_call"} for nm in names
            ]
        },
        "agentifier_spec_index": spec_index,
        "agentifier_spec_results": list(results or []),
        "agentifier_candidates": [],
        "agentifier_analyses": [],
    }


def _spec_payload(name: str, input_obj: Any) -> dict[str, Any]:
    return {"purpose": f"spec for {input_obj.catalog_entry['name']}"}


LLM = {"model": "test", "api_key": "k"}


class TestSpecPhaseFFSweep:
    def test_ff_while_pending_sweeps_instead_of_revising(self) -> None:
        session = _spec_session(results=[{"purpose": "spec for alpha_feat"}])
        calls: list[Any] = []
        with patch(
            "spec4.agentifier.agentifier._registry.stream",
            side_effect=_fake_stream(calls, _spec_payload),
        ):
            out = _collect(_run_spec_phase(FF_PROMPT, session, LLM))
        # The pending draft for alpha is kept; only beta and gamma are drafted.
        drafted = [c[1].catalog_entry["name"] for c in calls]
        assert drafted == ["beta_feat", "gamma_feat"]
        assert all(c[1].revision_instruction is None for c in calls)
        assert "Revising" not in out
        assert session["agentifier_spec_ff_review"] is True
        for nm in ("alpha_feat", "beta_feat", "gamma_feat"):
            assert nm in out

    def test_ff_at_fresh_start_drafts_all(self) -> None:
        session = _spec_session()
        calls: list[Any] = []
        with patch(
            "spec4.agentifier.agentifier._registry.stream",
            side_effect=_fake_stream(calls, _spec_payload),
        ):
            _collect(_run_spec_phase(FF_PROMPT, session, LLM))
        assert [c[1].catalog_entry["name"] for c in calls] == [
            "alpha_feat",
            "beta_feat",
            "gamma_feat",
        ]
        results = session["agentifier_spec_results"]
        assert len(results) == 3 and all(results)

    def test_ff_mid_loop_locks_confirmed_specs(self) -> None:
        # alpha confirmed earlier (spec_index=1): shown read-only, not re-drafted.
        session = _spec_session(
            spec_index=1, results=[{"purpose": "spec for alpha_feat"}]
        )
        calls: list[Any] = []
        with patch(
            "spec4.agentifier.agentifier._registry.stream",
            side_effect=_fake_stream(calls, _spec_payload),
        ):
            out = _collect(_run_spec_phase(FF_PROMPT, session, LLM))
        assert [c[1].catalog_entry["name"] for c in calls] == [
            "beta_feat",
            "gamma_feat",
        ]
        assert session["agentifier_spec_ff_locked"] == 1
        assert "locked" in out.lower()
        assert "alpha_feat" in out  # read-only context still displayed

    def _review_session(self, locked: int = 0) -> dict[str, Any]:
        session = _spec_session(
            spec_index=locked,
            results=[
                {"purpose": "spec for alpha_feat"},
                {"purpose": "spec for beta_feat"},
                {"purpose": "spec for gamma_feat"},
            ],
        )
        session["agentifier_spec_ff_review"] = True
        session["agentifier_spec_ff_locked"] = locked
        return session

    def test_review_confirm_finalizes(self) -> None:
        session = self._review_session()

        def _fake_finalize(sess: Any, llm: Any) -> Any:
            sess["_finalized"] = True
            yield "finalized"

        with patch(
            "spec4.agentifier.agentifier._finalize_specs",
            side_effect=_fake_finalize,
        ):
            out = _collect(_run_spec_phase("yes", session, LLM))
        assert session["_finalized"] is True
        assert session["agentifier_spec_ff_review"] is False
        assert session["agentifier_spec_index"] == 3
        assert "finalized" in out

    def test_review_revision_routed_by_feature_name(self) -> None:
        session = self._review_session()
        calls: list[Any] = []
        with patch(
            "spec4.agentifier.agentifier._registry.stream",
            side_effect=_fake_stream(calls, _spec_payload),
        ):
            _collect(_run_spec_phase("beta_feat: tighten the scope", session, LLM))
        assert len(calls) == 1
        assert calls[0][1].catalog_entry["name"] == "beta_feat"
        assert calls[0][1].revision_instruction == "tighten the scope"
        assert session["agentifier_spec_ff_review"] is True  # still reviewing

    def test_review_unknown_name_reprompts_atomically(self) -> None:
        session = self._review_session()
        calls: list[Any] = []
        with patch(
            "spec4.agentifier.agentifier._registry.stream",
            side_effect=_fake_stream(calls, _spec_payload),
        ):
            out = _collect(
                _run_spec_phase(
                    "beta_feat: fine\nzzz_feat: nope", session, LLM
                )
            )
        assert calls == []  # atomic: the valid line is not applied either
        assert "zzz_feat" in out
        assert "beta_feat" in out  # valid names listed for guidance

    def test_review_locked_name_rejected(self) -> None:
        session = self._review_session(locked=1)
        calls: list[Any] = []
        with patch(
            "spec4.agentifier.agentifier._registry.stream",
            side_effect=_fake_stream(calls, _spec_payload),
        ):
            out = _collect(_run_spec_phase("alpha_feat: change it", session, LLM))
        assert calls == []
        assert "locked" in out.lower()

    def test_review_freeform_input_reprompts_without_guessing(self) -> None:
        session = self._review_session()
        calls: list[Any] = []
        with patch(
            "spec4.agentifier.agentifier._registry.stream",
            side_effect=_fake_stream(calls, _spec_payload),
        ):
            out = _collect(_run_spec_phase("make them all better", session, LLM))
        assert calls == []
        assert "feature_name: instruction" in out


# ---------------------------------------------------------------------------
# Cross-cutting phase
# ---------------------------------------------------------------------------


def _cc_session(index: int = 0) -> dict[str, Any]:
    topics = ["provider_strategy", "prompt_versioning", "tool_protocol_strategy"]
    analysis = {
        t: {"recommendation": f"rec {t}", "rationale": f"why {t}"} for t in topics
    }
    return {
        "agentifier_messages": [],
        "agentifier_catalog_done": True,
        "agentifier_spec_done": True,
        "ai_features": {"ai_features": [{"name": "alpha_feat"}]},
        "agentifier_cross_cutting_topics": topics,
        "agentifier_cross_cutting_analysis": analysis,
        "agentifier_cross_cutting_index": index,
        "agentifier_cross_cutting_decisions": {},
    }


def _cc_payload(name: str, input_obj: Any) -> dict[str, Any]:
    topic = getattr(input_obj, "topic", None)
    if topic:
        return {topic: {"recommendation": f"revised {topic}", "rationale": "r"}}
    return {
        t: {"recommendation": f"rec {t}", "rationale": "r"}
        for t in getattr(input_obj, "topics", [])
    }


class TestCrossCuttingFFSweep:
    def test_ff_records_all_remaining_and_reviews(self) -> None:
        session = _cc_session()
        out = _collect(_run_cross_cutting_phase(FF_PROMPT, session, LLM))
        decisions = session["agentifier_cross_cutting_decisions"]
        assert set(decisions) == {
            "provider_strategy",
            "prompt_versioning",
            "tool_protocol_strategy",
        }
        assert session.get("agentifier_cross_cutting_done") is not True
        assert session["agentifier_cross_cutting_ff_review"] is True
        for t in decisions:
            assert t in out

    def test_skippable_topic_accepted_not_skipped(self) -> None:
        session = _cc_session()
        _collect(_run_cross_cutting_phase(FF_PROMPT, session, LLM))
        decision = session["agentifier_cross_cutting_decisions"]["prompt_versioning"]
        assert decision.get("recommendation") == "rec prompt_versioning"

    def test_ff_mid_loop_locks_decided_topics(self) -> None:
        session = _cc_session(index=1)
        session["agentifier_cross_cutting_decisions"] = {
            "provider_strategy": {"recommendation": "already decided"}
        }
        out = _collect(_run_cross_cutting_phase(FF_PROMPT, session, LLM))
        # The earlier decision survives untouched; the rest adopt the analysis.
        decisions = session["agentifier_cross_cutting_decisions"]
        assert decisions["provider_strategy"] == {"recommendation": "already decided"}
        assert session["agentifier_cc_ff_locked"] == 1
        assert "locked" in out.lower()

    def _review_session(self, locked: int = 0) -> dict[str, Any]:
        session = _cc_session(index=locked)
        decisions = {
            t: dict(session["agentifier_cross_cutting_analysis"][t])
            for t in session["agentifier_cross_cutting_topics"]
        }
        session["agentifier_cross_cutting_decisions"] = decisions
        session["agentifier_cross_cutting_ff_review"] = True
        session["agentifier_cc_ff_locked"] = locked
        return session

    def test_review_confirm_begins_priority(self) -> None:
        session = self._review_session()

        def _fake_priority(sess: Any, llm: Any) -> Any:
            sess["_priority_begun"] = True
            yield "priority"

        with patch(
            "spec4.agentifier.agentifier._begin_priority_phase",
            side_effect=_fake_priority,
        ):
            out = _collect(_run_cross_cutting_phase("yes", session, LLM))
        assert session["_priority_begun"] is True
        assert session["agentifier_cross_cutting_done"] is True
        assert session["agentifier_cross_cutting_ff_review"] is False
        assert "priority" in out

    def test_review_revision_reruns_named_topic(self) -> None:
        session = self._review_session()
        calls: list[Any] = []
        with patch(
            "spec4.agentifier.agentifier._registry.stream",
            side_effect=_fake_stream(calls, _cc_payload),
        ):
            _collect(
                _run_cross_cutting_phase(
                    "tool_protocol_strategy: add tracing", session, LLM
                )
            )
        assert len(calls) == 1
        assert calls[0][1].topic == "tool_protocol_strategy"
        assert calls[0][1].revision_instruction == "add tracing"
        decision = session["agentifier_cross_cutting_decisions"]["tool_protocol_strategy"]
        assert decision.get("recommendation") == "revised tool_protocol_strategy"
        assert session["agentifier_cross_cutting_ff_review"] is True

    def test_review_skip_line_skips_skippable_topic(self) -> None:
        session = self._review_session()
        _collect(_run_cross_cutting_phase("prompt_versioning: skip", session, LLM))
        assert session["agentifier_cross_cutting_decisions"]["prompt_versioning"] == {}

    def test_review_locked_topic_rejected(self) -> None:
        session = self._review_session(locked=1)
        calls: list[Any] = []
        with patch(
            "spec4.agentifier.agentifier._registry.stream",
            side_effect=_fake_stream(calls, _cc_payload),
        ):
            out = _collect(
                _run_cross_cutting_phase(
                    "provider_strategy: redo", session, LLM
                )
            )
        assert calls == []
        assert "locked" in out.lower()


class TestFFPromptSingleSource:
    def test_callbacks_reexports_app_constants_value(self) -> None:
        from spec4.callbacks import FF_PROMPT as cb_prompt

        assert cb_prompt is FF_PROMPT


# ---------------------------------------------------------------------------
# D-AF5/6/7 — mid-sweep failure handling, retry, diagnosability
# ---------------------------------------------------------------------------


def _flaky_stream(calls: list[Any], fail_names: dict[str, int]) -> Any:
    """Fake stream failing extraction `fail_names[name]` times per feature."""
    seen: dict[str, int] = {}

    def _stream(name: str, input_obj: Any) -> Any:
        feat = input_obj.catalog_entry["name"]
        calls.append(feat)
        seen[feat] = seen.get(feat, 0) + 1

        async def _gen() -> Any:
            if seen[feat] <= fail_names.get(feat, 0):
                yield "```json\n{\"purpose\": \"truncated and never clo"
            else:
                yield "```json\n" + json.dumps({"purpose": f"spec for {feat}"}) + "\n```"

        return _gen()

    return _stream


class TestSweepFailureHandling:
    def test_retry_once_recovers_transient_failure(self) -> None:
        """D-AF6: one bad draft output is retried and the sweep completes."""
        session = _spec_session()
        calls: list[str] = []
        with patch(
            "spec4.agentifier.agentifier._registry.stream",
            side_effect=_flaky_stream(calls, {"beta_feat": 1}),
        ):
            out = _collect(_run_spec_phase(FF_PROMPT, session, LLM))
        assert calls.count("beta_feat") == 2  # first attempt + one retry
        assert calls.count("alpha_feat") == 1
        assert calls.count("gamma_feat") == 1
        results = session["agentifier_spec_results"]
        assert len(results) == 3 and all(results)
        assert session["agentifier_spec_ff_review"] is True
        assert "Comprehensive spec review" in out

    def test_persistent_failure_pauses_with_partial_review(self) -> None:
        """D-AF5: a spec failing both attempts pauses the sweep coherently."""
        session = _spec_session()
        calls: list[str] = []
        with patch(
            "spec4.agentifier.agentifier._registry.stream",
            side_effect=_flaky_stream(calls, {"beta_feat": 99}),
        ):
            out = _collect(_run_spec_phase(FF_PROMPT, session, LLM))
        assert calls.count("beta_feat") == 2  # two attempts, then pause
        assert "gamma_feat" not in [c for c in calls]  # sweep stopped
        assert session["agentifier_spec_ff_review"] is True
        assert "Fast Forward" in out  # resume guidance
        assert "not yet drafted" in out  # undrafted stubs in partial review
        # msgs invariant restored: turn ends on an assistant message
        assert session["agentifier_messages"][-1]["role"] == "assistant"

    def test_ff_press_resumes_after_pause(self) -> None:
        """D-AF5: pressing FF again re-attempts the failed spec, keeps drafts."""
        session = _spec_session()
        with patch(
            "spec4.agentifier.agentifier._registry.stream",
            side_effect=_flaky_stream([], {"beta_feat": 99}),
        ):
            _collect(_run_spec_phase(FF_PROMPT, session, LLM))
        calls2: list[str] = []
        with patch(
            "spec4.agentifier.agentifier._registry.stream",
            side_effect=_flaky_stream(calls2, {}),
        ):
            _collect(_run_spec_phase(FF_PROMPT, session, LLM))
        assert calls2 == ["beta_feat", "gamma_feat"]  # alpha kept, no re-draft
        results = session["agentifier_spec_results"]
        assert len(results) == 3 and all(results)

    def test_loop_path_failure_appends_error_to_messages(self) -> None:
        """D-AF5: the one-at-a-time path no longer leaves a trailing user turn."""
        session = _spec_session()
        with patch(
            "spec4.agentifier.agentifier._registry.stream",
            side_effect=_flaky_stream([], {"alpha_feat": 99}),
        ):
            _collect(_run_spec_phase("yes", session, LLM))
        msgs = session["agentifier_messages"]
        assert msgs[-1]["role"] == "assistant"
        assert "alpha_feat" in msgs[-1]["content"]

    def test_failure_dump_written_in_dev_mode(self, tmp_path: Any) -> None:
        """D-AF7: the full raw output of a failed extraction is persisted."""
        session = _spec_session()
        session["working_dir"] = str(tmp_path)
        with patch("spec4.agentifier.agentifier._DEV_MODE", True), patch(
            "spec4.agentifier.agentifier._registry.stream",
            side_effect=_flaky_stream([], {"beta_feat": 99}),
        ):
            _collect(_run_spec_phase(FF_PROMPT, session, LLM))
        failures = list((tmp_path / ".spec4" / "failures").glob("spec_drafter_beta_feat_*.txt"))
        assert len(failures) == 2  # both failed attempts dumped in full
        content = failures[0].read_text(encoding="utf-8")
        assert "truncated and never clo" in content

    def test_no_failure_dump_outside_dev_mode(self, tmp_path: Any) -> None:
        session = _spec_session()
        session["working_dir"] = str(tmp_path)
        with patch("spec4.agentifier.agentifier._DEV_MODE", False), patch(
            "spec4.agentifier.agentifier._registry.stream",
            side_effect=_flaky_stream([], {"beta_feat": 99}),
        ):
            _collect(_run_spec_phase(FF_PROMPT, session, LLM))
        assert not (tmp_path / ".spec4" / "failures").exists()
