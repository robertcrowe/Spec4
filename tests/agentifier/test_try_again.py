"""D-TA: the breadth panel's "Try Again" — discard the pool and redraw Scout.

Three properties matter and are tested separately:

* the reset is *complete* — no Agentifier session key survives a restart, in
  particular the revision block, which would otherwise carry a prior round's
  framing into a draw that no longer qualifies as a revision;
* the reset is *session-only* — every ai_features.json on disk, in the current
  round and in every implemented predecessor, is byte-identical afterwards;
* the redraw takes the fresh-start route, so a revision round re-derives its
  revision block from disk instead of re-opening the reselection panel.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from typing import Any
from unittest.mock import patch

from dash import no_update

from spec4.agentifier import agentifier
from spec4.agentifier.agentifier import (
    _RESTART_DEFAULTS,
    _RESTART_POP,
    reset_agentifier_flow,
)
from spec4.agentifier.scout import Candidate, ScoutOutput
from spec4.agentifier.tier_analyst import TierAnalystOutput
from spec4.app_constants import STATE_AGENTIFIER_COMPLETE, STATE_IN_PROGRESS
from spec4.callbacks import on_breadth_try_again
from spec4.session import _default_session, _persist_artifacts

from .test_agentifier_orchestrator import (
    _LLM_CONFIG,
    _SAMPLE_VISION,
    collect,
    mock_litellm_stream,
)

_MODULE = pathlib.Path(agentifier.__file__)

_CANDIDATE = Candidate(
    name="smart_search",
    linked_vision_features=["search"],
    scope="feature",
    rough_description="Semantic search over product catalog.",
)

_ANALYSIS = TierAnalystOutput(
    recommended_tier="single_call",
    rationale="One call handles the bounded extraction task.",
    risks_of_going_higher=["Unnecessary complexity."],
    risks_of_going_lower=["Deterministic approach misses edge cases."],
    borderline=False,
    borderline_seams=[],
    compared_to_next_tier_down="Embeddings would lose generation.",
)


# ---------------------------------------------------------------------------
# D-TA1 — the reset is complete, and stays complete
# ---------------------------------------------------------------------------


class TestResetCompleteness:
    def test_every_session_key_is_accounted_for(self) -> None:
        """Drift guard. A new agentifier_* key must join one of the two
        collections or be an explicit exclusion — otherwise it silently
        survives a restart, which is how the revision block was left behind."""
        used = set(re.findall(r'"(agentifier_[a-z_]+)"', _MODULE.read_text()))
        covered = set(_RESTART_DEFAULTS) | set(_RESTART_POP) | {"agentifier_state"}
        assert used - covered == set()

    def test_no_dead_entries(self) -> None:
        used = set(re.findall(r'"(agentifier_[a-z_]+)"', _MODULE.read_text()))
        listed = (set(_RESTART_DEFAULTS) | set(_RESTART_POP)) - {"ai_catalog"}
        assert listed - used == set()

    def test_defaults_match_the_session_defaults(self) -> None:
        """Restored values must be the documented session shape, not guesses."""
        defaults = _default_session()
        shared = set(_RESTART_DEFAULTS) & set(defaults)
        assert shared, "sanity: the two should overlap substantially"
        for key in sorted(shared):
            assert _RESTART_DEFAULTS[key] == defaults[key], key

    def test_the_two_collections_are_disjoint(self) -> None:
        assert set(_RESTART_DEFAULTS) & set(_RESTART_POP) == set()

    def test_revision_block_is_cleared(self) -> None:
        session: dict[str, Any] = {
            "agentifier_revision": True,
            "agentifier_revision_version": 2,
            "agentifier_revision_prior_version": 1,
            "agentifier_revision_delta": {"goal": "x"},
            "agentifier_revision_cross_cutting": {"security": {}},
            "agentifier_carried_forward": [{"name": "old"}],
        }
        reset_agentifier_flow(session)
        for key in (
            "agentifier_revision",
            "agentifier_revision_version",
            "agentifier_revision_prior_version",
            "agentifier_revision_delta",
            "agentifier_revision_cross_cutting",
            "agentifier_carried_forward",
        ):
            assert key not in session, key

    def test_reselection_state_is_abandoned(self) -> None:
        session: dict[str, Any] = {
            "agentifier_reselection": True,
            "agentifier_preserved_features": {"a": {"name": "a"}},
            "agentifier_preserved_selected": [{"name": "a"}],
            "agentifier_breadth_selection": ["a"],
        }
        reset_agentifier_flow(session)
        assert "agentifier_reselection" not in session
        assert "agentifier_preserved_features" not in session
        assert "agentifier_preserved_selected" not in session
        assert session["agentifier_breadth_selection"] is None

    def test_completion_state_is_demoted(self) -> None:
        session: dict[str, Any] = {"agentifier_state": STATE_AGENTIFIER_COMPLETE}
        reset_agentifier_flow(session)
        assert session["agentifier_state"] == STATE_IN_PROGRESS

    def test_ai_features_is_left_in_place(self) -> None:
        """Session and disk stay consistent while the redraw runs."""
        features = {"ai_features": [{"name": "kept"}]}
        session: dict[str, Any] = {"ai_features": features}
        reset_agentifier_flow(session)
        assert session["ai_features"] == features

    def test_mutable_defaults_are_not_shared_between_sessions(self) -> None:
        a: dict[str, Any] = {}
        b: dict[str, Any] = {}
        reset_agentifier_flow(a)
        reset_agentifier_flow(b)
        a["agentifier_messages"].append({"role": "user", "content": "x"})
        a["agentifier_cross_cutting_decisions"]["security"] = {}
        assert b["agentifier_messages"] == []
        assert b["agentifier_cross_cutting_decisions"] == {}


# ---------------------------------------------------------------------------
# The reset touches no artifact on disk
# ---------------------------------------------------------------------------


def _digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project(tmp_path: Any) -> tuple[str, pathlib.Path, pathlib.Path]:
    """A project with an implemented v0 and an in-progress v1, both carrying
    their own ai_features.json."""
    v0 = tmp_path / ".spec4" / "v0"
    v1 = tmp_path / ".spec4" / "v1"
    v0.mkdir(parents=True)
    v1.mkdir(parents=True)
    (v0 / "IMPLEMENTED").write_text("")
    (v0 / "ai_features.json").write_text(
        json.dumps({"ai_features": [{"name": "shipped"}]}, indent=2)
    )
    (v1 / "ai_features.json").write_text(
        json.dumps({"ai_features": [{"name": "in_progress"}]}, indent=2)
    )
    return str(tmp_path), v0 / "ai_features.json", v1 / "ai_features.json"


class TestDiskIsUntouched:
    def test_reset_does_not_alter_any_ai_features(self, tmp_path: Any) -> None:
        wd, prior, current = _project(tmp_path)
        before = (_digest(prior), _digest(current))

        session: dict[str, Any] = {
            "working_dir": wd,
            "agentifier_state": STATE_AGENTIFIER_COMPLETE,
            "ai_features": {"ai_features": [{"name": "in_progress"}]},
        }
        reset_agentifier_flow(session)

        assert prior.exists() and current.exists()
        assert (_digest(prior), _digest(current)) == before

    def test_persist_after_reset_writes_nothing(self, tmp_path: Any) -> None:
        """The retention guarantee: _persist_artifacts writes ai_features.json
        only under STATE_AGENTIFIER_COMPLETE, which the reset demotes."""
        wd, prior, current = _project(tmp_path)
        before = (_digest(prior), _digest(current))

        session: dict[str, Any] = {
            "working_dir": wd,
            "phase_version": 1,
            "agentifier_state": STATE_AGENTIFIER_COMPLETE,
            "ai_features": {"ai_features": [{"name": "replacement"}]},
        }
        reset_agentifier_flow(session)
        _persist_artifacts(session)

        assert (_digest(prior), _digest(current)) == before

    def test_implemented_round_survives_a_full_try_again(self, tmp_path: Any) -> None:
        wd, prior, _current = _project(tmp_path)
        before = _digest(prior)

        session = _session(working_dir=wd)
        session["agentifier_scout_pool"] = [{"name": "old"}]
        with _mocked_draw():
            on_breadth_try_again(1, session)

        assert _digest(prior) == before


# ---------------------------------------------------------------------------
# D-TA2/D-TA3 — the callback
# ---------------------------------------------------------------------------


def _session(**overrides: Any) -> dict[str, Any]:
    session = _default_session()
    session.update(
        {
            "phase": "chat",
            "active_agent": "agentifier",
            "vision_statement": _SAMPLE_VISION,
            "llm_config": _LLM_CONFIG,
            "messages": [{"role": "assistant", "content": "panel"}],
        }
    )
    session.update(overrides)
    return session


def _mocked_draw() -> Any:
    class _Ctx:
        def __enter__(self) -> None:
            self._patches = [
                patch(
                    "spec4.agentifier.agentifier._call_scout",
                    return_value=ScoutOutput(candidates=[_CANDIDATE]),
                ),
                patch(
                    "spec4.agentifier.agentifier._call_tier_analyst",
                    return_value=_ANALYSIS,
                ),
                mock_litellm_stream("Hello!"),
            ]
            for p in self._patches:
                p.start()

        def __exit__(self, *exc: Any) -> None:
            for p in reversed(self._patches):
                p.stop()

    return _Ctx()


class TestCallback:
    def test_no_click_is_a_no_op(self) -> None:
        assert on_breadth_try_again(0, _session()) == (no_update, no_update)

    def test_refuses_while_a_stream_is_running(self) -> None:
        result = on_breadth_try_again(1, _session(_stream_id="abc"))
        assert result == (no_update, no_update)

    def test_starts_a_stream_and_records_the_action(self) -> None:
        session = _session()
        session["agentifier_scout_pool"] = [{"name": "old"}]
        with _mocked_draw():
            store, max_intervals = on_breadth_try_again(1, session)

        assert store["_stream_id"]
        assert max_intervals == -1
        assert store["messages"][-2]["role"] == "user"
        assert "Try Again" in store["messages"][-2]["content"]
        assert store["messages"][-1] == {"role": "assistant", "content": ""}

    def test_prior_transcript_is_preserved(self) -> None:
        session = _session()
        with _mocked_draw():
            store, _ = on_breadth_try_again(1, session)
        assert store["messages"][0] == {"role": "assistant", "content": "panel"}

    def test_pool_is_discarded_before_the_redraw(self) -> None:
        """The reset must land before the generator is handed to streaming —
        _run_catalog_phase only re-runs Scout when the cached pool is gone."""
        session = _session()
        session["agentifier_scout_pool"] = [{"name": "old"}]
        session["agentifier_breadth_groups"] = [{"name": "old"}]
        seen: dict[str, Any] = {}

        def fake_start(gen: Any, sess: Any) -> str:
            seen.update(
                {
                    "pool": sess.get("agentifier_scout_pool"),
                    "groups": sess.get("agentifier_breadth_groups"),
                    "messages": list(sess.get("agentifier_messages") or []),
                    "state": sess.get("agentifier_state"),
                }
            )
            return "stream-1"

        with patch("spec4.callbacks.streaming.start", fake_start):
            store, _ = on_breadth_try_again(1, session)

        assert seen["pool"] is None
        assert seen["groups"] is None
        assert seen["messages"] == []
        assert seen["state"] == STATE_IN_PROGRESS
        assert store["_stream_id"] == "stream-1"


# ---------------------------------------------------------------------------
# D-TA7 — guided redraw: the note survives the reset and reaches Scout
# ---------------------------------------------------------------------------

_OLD_POOL = [
    {"name": "support_chatbot", "rough_description": "Answers tickets."},
    {"name": "smart_search", "rough_description": "Semantic search."},
]


class TestGuidedRedraw:
    def _run(self, session: dict[str, Any], note: Any) -> dict[str, Any]:
        with _mocked_draw():
            store, _ = on_breadth_try_again(1, session, note)
        return store

    def test_note_survives_the_reset_with_the_rejected_set(self) -> None:
        session = _session(agentifier_scout_pool=list(_OLD_POOL))
        store = self._run(session, "  Far fewer — only what the MVP needs.  ")
        guidance = store["agentifier_retry_guidance"]
        assert guidance["notes"] == ["Far fewer — only what the MVP needs."]
        assert [c["name"] for c in guidance["previous_candidates"]] == [
            "support_chatbot",
            "smart_search",
        ]
        assert guidance["previous_candidates"][0]["rough_description"] == (
            "Answers tickets."
        )

    def test_user_bubble_quotes_the_note(self) -> None:
        store = self._run(_session(), "Drop the chatbot.\nKeep search.")
        content = store["messages"][-2]["content"]
        assert content.startswith("Try Again — draw a new set of candidates.")
        assert "> Drop the chatbot." in content
        assert "> Keep search." in content

    def test_blank_note_is_the_plain_redraw(self) -> None:
        """No notes → Scout's prompt is untouched (see
        test_plain_redraw_passes_no_guidance), but the redraw is still logged."""
        for blank in (None, "", "   "):
            store = self._run(_session(agentifier_scout_pool=list(_OLD_POOL)), blank)
            guidance = store["agentifier_retry_guidance"]
            assert guidance["notes"] == []
            assert [e["note"] for e in guidance["history"]] == [None]
            assert (
                store["messages"][-2]["content"]
                == "Try Again — draw a new set of candidates."
            )

    def test_every_click_is_one_history_event(self) -> None:
        session = _session(agentifier_scout_pool=list(_OLD_POOL))
        first = self._run(session, "Fewer, simpler.")
        first["agentifier_scout_pool"] = [{"name": "second_draw", "rough_description": ""}]
        first["_stream_id"] = None
        second = self._run(first, "")
        second["agentifier_scout_pool"] = [{"name": "third_draw", "rough_description": ""}]
        second["_stream_id"] = None
        third = self._run(second, "Drop third_draw.")
        history = third["agentifier_retry_guidance"]["history"]
        assert [e["note"] for e in history] == ["Fewer, simpler.", None, "Drop third_draw."]
        assert [[c["name"] for c in e["rejected_candidates"]] for e in history] == [
            ["support_chatbot", "smart_search"],
            ["second_draw"],
            ["third_draw"],
        ]
        assert all(e["requested_at"].endswith("+00:00") for e in history)
        assert len({e["requested_at"] for e in history}) == 3

    def test_notes_accumulate_across_retries(self) -> None:
        session = _session(agentifier_scout_pool=list(_OLD_POOL))
        first = self._run(session, "Fewer, simpler.")
        # The redraw produced a new pool the developer is now rejecting too.
        first["agentifier_scout_pool"] = [{"name": "second_draw", "rough_description": ""}]
        first["_stream_id"] = None
        second = self._run(first, "Even fewer — max 3.")
        guidance = second["agentifier_retry_guidance"]
        assert guidance["notes"] == ["Fewer, simpler.", "Even fewer — max 3."]
        assert [c["name"] for c in guidance["previous_candidates"]] == ["second_draw"]

    def test_blank_note_keeps_prior_notes_and_refreshes_the_set(self) -> None:
        session = _session(agentifier_scout_pool=list(_OLD_POOL))
        first = self._run(session, "Fewer, simpler.")
        first["agentifier_scout_pool"] = [{"name": "second_draw", "rough_description": ""}]
        first["_stream_id"] = None
        second = self._run(first, "")
        guidance = second["agentifier_retry_guidance"]
        assert guidance["notes"] == ["Fewer, simpler."]
        assert [c["name"] for c in guidance["previous_candidates"]] == ["second_draw"]

    def test_guidance_reaches_scout(self) -> None:
        session = _session(agentifier_scout_pool=list(_OLD_POOL))
        with (
            patch(
                "spec4.agentifier.agentifier._call_scout",
                return_value=ScoutOutput(candidates=[_CANDIDATE]),
            ) as scout,
            patch(
                "spec4.agentifier.agentifier._call_tier_analyst",
                return_value=_ANALYSIS,
            ),
            mock_litellm_stream("Hello!"),
            patch("spec4.callbacks.streaming.start", return_value="stream-1"),
        ):
            store, _ = on_breadth_try_again(1, session, "Fewer, simpler.")
            collect(agentifier.run(None, store, _LLM_CONFIG))

        guidance = scout.call_args.kwargs["guidance"]
        assert guidance["notes"] == ["Fewer, simpler."]
        assert [c["name"] for c in guidance["previous_candidates"]] == [
            "support_chatbot",
            "smart_search",
        ]

    def test_plain_redraw_passes_no_guidance(self) -> None:
        session = _session(agentifier_scout_pool=list(_OLD_POOL))
        with (
            patch(
                "spec4.agentifier.agentifier._call_scout",
                return_value=ScoutOutput(candidates=[_CANDIDATE]),
            ) as scout,
            patch(
                "spec4.agentifier.agentifier._call_tier_analyst",
                return_value=_ANALYSIS,
            ),
            mock_litellm_stream("Hello!"),
            patch("spec4.callbacks.streaming.start", return_value="stream-1"),
        ):
            store, _ = on_breadth_try_again(1, session, "")
            collect(agentifier.run(None, store, _LLM_CONFIG))
        assert scout.call_args.kwargs["guidance"] is None

    def test_scout_banner_names_the_latest_note(self) -> None:
        session = _session(agentifier_scout_pool=list(_OLD_POOL))
        with (
            patch(
                "spec4.agentifier.agentifier._call_scout",
                return_value=ScoutOutput(candidates=[_CANDIDATE]),
            ),
            patch(
                "spec4.agentifier.agentifier._call_tier_analyst",
                return_value=_ANALYSIS,
            ),
            mock_litellm_stream("Hello!"),
            patch("spec4.callbacks.streaming.start", return_value="stream-1"),
        ):
            store, _ = on_breadth_try_again(1, session, "Fewer, simpler.")
            out = collect(agentifier.run(None, store, _LLM_CONFIG))
        assert "Applying your guidance: _Fewer, simpler._" in out

    def test_guidance_reaches_the_tier_analyst_after_continue(self) -> None:
        session = _session(agentifier_scout_pool=list(_OLD_POOL))
        with (
            patch(
                "spec4.agentifier.agentifier._call_scout",
                return_value=ScoutOutput(candidates=[_CANDIDATE]),
            ),
            patch(
                "spec4.agentifier.agentifier._call_tier_analyst",
                return_value=_ANALYSIS,
            ) as tier,
            mock_litellm_stream("Hello!"),
            patch("spec4.callbacks.streaming.start", return_value="stream-1"),
        ):
            store, _ = on_breadth_try_again(1, session, "Keep it simple.")
            collect(agentifier.run(None, store, _LLM_CONFIG))
            store["agentifier_breadth_selection"] = [_CANDIDATE.name]
            collect(agentifier.run("select", store, _LLM_CONFIG))
        assert tier.call_args.kwargs["guidance"] == ["Keep it simple."]

    def test_a_stale_input_rediscovery_starts_clean(self) -> None:
        """The notes referred to a draw that no longer exists."""
        session: dict[str, Any] = {
            "agentifier_retry_guidance": {"notes": ["x"], "previous_candidates": []}
        }
        reset_agentifier_flow(session)
        assert session["agentifier_retry_guidance"] is None


# ---------------------------------------------------------------------------
# D-TA7 — the redraw log lands in ai_features.json as discovery_guidance
# ---------------------------------------------------------------------------


def _event(note: str | None, stamp: str, *names: str) -> dict[str, Any]:
    return {
        "requested_at": stamp,
        "note": note,
        "rejected_candidates": [{"name": n, "rough_description": ""} for n in names],
    }


class TestDiscoveryGuidanceArtifact:
    def _complete(self, session: dict[str, Any]) -> dict[str, Any]:
        session.setdefault("agentifier_messages", [])
        session["ai_features"] = {
            "ai_features": [],
            "cross_cutting": {},
            "explicitly_rejected": [],
            "references": [],
            "consolidation": [],
            "reconciliation": [],
        }
        with mock_litellm_stream("done"):
            collect(agentifier._complete_agentifier(session))
        return session["ai_features"]

    def test_history_is_written_in_order(self, tmp_path: Any) -> None:
        session = _session(working_dir=str(tmp_path))
        session["agentifier_retry_guidance"] = {
            "notes": ["Fewer.", "Drop b."],
            "previous_candidates": [],
            "history": [_event("Fewer.", "t1", "a", "b"), _event(None, "t2", "b"), _event("Drop b.", "t3", "b")],
        }
        out = self._complete(session)
        assert [e["note"] for e in out["discovery_guidance"]] == ["Fewer.", None, "Drop b."]
        assert out["discovery_guidance"][0]["rejected_candidates"][1]["name"] == "b"

    def test_no_redraw_writes_an_empty_list(self, tmp_path: Any) -> None:
        session = _session(working_dir=str(tmp_path))
        assert self._complete(session)["discovery_guidance"] == []

    def test_merges_with_the_round_on_disk_without_duplicates(
        self, tmp_path: Any
    ) -> None:
        """A re-completion (reselection after a reload, stale rediscovery)
        keeps the earlier events and adds only the new ones."""
        v0 = tmp_path / ".spec4" / "v0"
        v0.mkdir(parents=True)
        (v0 / "ai_features.json").write_text(
            json.dumps({"ai_features": [], "discovery_guidance": [_event("Old.", "t0", "x")]})
        )
        session = _session(working_dir=str(tmp_path), phase_version=0)
        session["agentifier_retry_guidance"] = {
            "notes": ["New."],
            "previous_candidates": [],
            "history": [_event("Old.", "t0", "x"), _event("New.", "t1", "y")],
        }
        out = self._complete(session)
        assert [(e["requested_at"], e["note"]) for e in out["discovery_guidance"]] == [
            ("t0", "Old."),
            ("t1", "New."),
        ]

    def test_reload_without_a_redraw_keeps_the_disk_log(self, tmp_path: Any) -> None:
        v0 = tmp_path / ".spec4" / "v0"
        v0.mkdir(parents=True)
        (v0 / "ai_features.json").write_text(
            json.dumps({"ai_features": [], "discovery_guidance": [_event("Old.", "t0", "x")]})
        )
        session = _session(working_dir=str(tmp_path), phase_version=0)
        session["agentifier_retry_guidance"] = None
        out = self._complete(session)
        assert [e["note"] for e in out["discovery_guidance"]] == ["Old."]

    def test_end_to_end_try_again_lands_in_the_artifact(self, tmp_path: Any) -> None:
        session = _session(working_dir=str(tmp_path), phase_version=0)
        session["agentifier_scout_pool"] = list(_OLD_POOL)
        with (
            patch(
                "spec4.agentifier.agentifier._call_scout",
                return_value=ScoutOutput(candidates=[_CANDIDATE]),
            ),
            patch(
                "spec4.agentifier.agentifier._call_tier_analyst",
                return_value=_ANALYSIS,
            ),
            mock_litellm_stream("Hello!"),
            patch("spec4.callbacks.streaming.start", return_value="stream-1"),
        ):
            store, _ = on_breadth_try_again(1, session, "Far fewer.")
            collect(agentifier.run(None, store, _LLM_CONFIG))
            # Zero selection completes the flow immediately.
            store["agentifier_breadth_selection"] = []
            collect(agentifier.run("select", store, _LLM_CONFIG))
        log = store["ai_features"]["discovery_guidance"]
        assert [e["note"] for e in log] == ["Far fewer."]
        assert [c["name"] for c in log[0]["rejected_candidates"]] == [
            "support_chatbot",
            "smart_search",
        ]


# ---------------------------------------------------------------------------
# The redraw takes the fresh-start route
# ---------------------------------------------------------------------------


class TestRedrawRunsScout:
    def test_scout_runs_again(self) -> None:
        session = _session()
        session["agentifier_scout_pool"] = [{"name": "old"}]
        session["agentifier_messages"] = [{"role": "assistant", "content": "old"}]
        reset_agentifier_flow(session)

        with (
            patch(
                "spec4.agentifier.agentifier._call_scout",
                return_value=ScoutOutput(candidates=[_CANDIDATE]),
            ) as scout,
            patch(
                "spec4.agentifier.agentifier._call_tier_analyst",
                return_value=_ANALYSIS,
            ),
            mock_litellm_stream("Hello!"),
        ):
            collect(agentifier.run(None, session, _LLM_CONFIG))

        scout.assert_called_once()

    def test_a_new_pool_replaces_the_old_one(self) -> None:
        session = _session()
        session["agentifier_scout_pool"] = [{"name": "stale_candidate"}]
        session["agentifier_messages"] = [{"role": "assistant", "content": "old"}]
        reset_agentifier_flow(session)

        with (
            patch(
                "spec4.agentifier.agentifier._call_scout",
                return_value=ScoutOutput(candidates=[_CANDIDATE]),
            ),
            patch(
                "spec4.agentifier.agentifier._call_tier_analyst",
                return_value=_ANALYSIS,
            ),
            mock_litellm_stream("Hello!"),
        ):
            collect(agentifier.run(None, session, _LLM_CONFIG))

        names = [c["name"] for c in session["agentifier_scout_pool"]]
        assert names == [_CANDIDATE.name]
        assert "stale_candidate" not in names

    def test_replay_does_not_short_circuit_the_redraw(self) -> None:
        """_run_catalog_phase replays the last assistant turn when messages
        survive, which would swallow the redraw entirely."""
        session = _session()
        session["agentifier_messages"] = [
            {"role": "assistant", "content": "previous panel intro"}
        ]
        reset_agentifier_flow(session)
        assert session["agentifier_messages"] == []


# ---------------------------------------------------------------------------
# Revision rounds
# ---------------------------------------------------------------------------


class TestRevisionRound:
    def _revision_project(self, tmp_path: Any) -> str:
        v0 = tmp_path / ".spec4" / "v0"
        v0.mkdir(parents=True)
        (v0 / "IMPLEMENTED").write_text("")
        (v0 / "ai_features.json").write_text(
            json.dumps({"ai_features": [{"name": "shipped", "tier": "single_call"}]})
        )
        return str(tmp_path)

    def _revision_vision(self) -> dict[str, Any]:
        vision = json.loads(json.dumps(_SAMPLE_VISION))
        vision["vision_statement"]["revision_history"] = [
            {"goal": "Add export", "changes": {"added": ["export"]}}
        ]
        return vision

    def test_revision_block_is_re_derived_from_disk(self, tmp_path: Any) -> None:
        """The requirement: a Try Again inside a revision round draws a new
        candidate set while remaining a revision round."""
        session = _session(
            working_dir=self._revision_project(tmp_path),
            vision_statement=self._revision_vision(),
        )
        # A stale revision block from the round being abandoned.
        session["agentifier_revision"] = True
        session["agentifier_revision_delta"] = {"goal": "SUPERSEDED"}
        session["agentifier_carried_forward"] = [{"name": "superseded"}]

        reset_agentifier_flow(session)
        assert "agentifier_revision_delta" not in session

        with (
            patch(
                "spec4.agentifier.agentifier._call_scout",
                return_value=ScoutOutput(candidates=[_CANDIDATE]),
            ),
            patch(
                "spec4.agentifier.agentifier._call_tier_analyst",
                return_value=_ANALYSIS,
            ),
            mock_litellm_stream("Hello!"),
        ):
            collect(agentifier.run(None, session, _LLM_CONFIG))

        assert session.get("agentifier_revision") is True
        assert session["agentifier_revision_delta"]["goal"] == "Add export"
        assert [f["name"] for f in session["agentifier_carried_forward"]] == [
            "shipped"
        ]

    def test_scout_is_told_it_is_a_revision(self, tmp_path: Any) -> None:
        session = _session(
            working_dir=self._revision_project(tmp_path),
            vision_statement=self._revision_vision(),
        )
        reset_agentifier_flow(session)

        with (
            patch(
                "spec4.agentifier.agentifier._call_scout",
                return_value=ScoutOutput(candidates=[_CANDIDATE]),
            ) as scout,
            patch(
                "spec4.agentifier.agentifier._call_tier_analyst",
                return_value=_ANALYSIS,
            ),
            mock_litellm_stream("Hello!"),
        ):
            collect(agentifier.run(None, session, _LLM_CONFIG))

        assert scout.call_args.kwargs.get("revision") is not None


# ---------------------------------------------------------------------------
# D-TA5/D-TA6 — the button appears on the panel, and only there
# ---------------------------------------------------------------------------


def _ids(node: Any, acc: list[Any] | None = None) -> list[Any]:
    acc = [] if acc is None else acc
    if isinstance(node, list | tuple):
        for item in node:
            _ids(item, acc)
        return acc
    node_id = getattr(node, "id", None)
    if node_id is not None:
        acc.append(node_id)
    children = getattr(node, "children", None)
    if children is not None and not isinstance(children, str):
        _ids(children, acc)
    return acc


class TestPanelButton:
    def _panel_session(self, **overrides: Any) -> dict[str, Any]:
        session = _session()
        session["agentifier_breadth_groups"] = [
            {"name": "smart_search", "description": "Semantic search."}
        ]
        session["agentifier_scout_pool"] = [
            {
                "name": "smart_search",
                "rough_description": "Semantic search.",
                "scope": "feature",
                "linked_vision_features": ["search"],
            }
        ]
        session.update(overrides)
        return session

    def test_panel_offers_try_again(self) -> None:
        from spec4.layouts._chat import _breadth_panel

        ids = _ids(_breadth_panel(self._panel_session()))
        assert "btn-breadth-try-again" in ids
        assert "btn-breadth-submit" in ids

    def test_panel_offers_the_guidance_box(self) -> None:
        """D-TA7: the note box sits with Try Again, on the panel only."""
        from spec4.layouts._chat import _breadth_panel

        panel = _breadth_panel(self._panel_session())
        ids = _ids(panel)
        assert "breadth-retry-input" in ids
        assert ids.index("btn-breadth-submit") < ids.index("breadth-retry-input")
        assert ids.index("breadth-retry-input") < ids.index("btn-breadth-try-again")

    def test_try_again_stretches_to_the_field_height(self) -> None:
        """Like Send next to chat-input: the button and the textarea share a
        flex row that stretches its items, so the button spans the field's
        full height (the stretch rule itself lives in v3.css)."""
        from dash import html

        from spec4.layouts._chat import _breadth_panel

        panel = _breadth_panel(self._panel_session())

        def find_parent(node: Any) -> Any:
            children = getattr(node, "children", None)
            if isinstance(children, list | tuple):
                for child in children:
                    if getattr(child, "id", None) == "btn-breadth-try-again":
                        return node
                    found = find_parent(child)
                    if found is not None:
                        return found
            return None

        row = find_parent(panel)
        assert isinstance(row, html.Div)
        assert row.style["display"] == "flex"
        assert row.style["alignItems"] == "stretch"
        field = row.children[0]
        assert field.id == "breadth-retry-input"
        assert field.style["flex"] == "1"

    def test_submit_button_reads_next_step(self) -> None:
        from spec4.layouts._chat import _breadth_panel

        panel = _breadth_panel(self._panel_session())

        def find(node: Any) -> Any:
            if getattr(node, "id", None) == "btn-breadth-submit":
                return node
            children = getattr(node, "children", None)
            if isinstance(children, list | tuple):
                for child in children:
                    found = find(child)
                    if found is not None:
                        return found
            return None

        assert find(panel).children == "Next Step"

    def test_hidden_once_the_panel_is_submitted(self) -> None:
        """D-TA6: the button lives on the panel, so it goes when the panel does
        — and the callback refuses mid-stream anyway."""
        from spec4.layouts._chat import _breadth_panel

        assert _breadth_panel(self._panel_session(_stream_id="abc")) is None
        assert (
            _breadth_panel(self._panel_session(agentifier_breadth_chosen=True))
            is None
        )
