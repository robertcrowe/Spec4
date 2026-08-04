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

    def test_hidden_once_the_panel_is_submitted(self) -> None:
        """D-TA6: the button lives on the panel, so it goes when the panel does
        — and the callback refuses mid-stream anyway."""
        from spec4.layouts._chat import _breadth_panel

        assert _breadth_panel(self._panel_session(_stream_id="abc")) is None
        assert (
            _breadth_panel(self._panel_session(agentifier_breadth_chosen=True))
            is None
        )
