"""D-AT1/D-AT3: the breadth-selection turn's contribution to the chars counter.

The turn yields tier-analysis progress text and then opens the orchestrator
stream. `_stream_suppressing_json` publishes a cumulative received-character
total that the counter prefers over the displayed message length, so without a
seed the counter would drop to zero at the handover. These tests drive the real
turn and check the published total against what the turn actually yielded.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from spec4.agentifier import agentifier
from spec4.agentifier.linker import LinkerOutcome, LinkerOutput
from spec4.agentifier.scout import Candidate, ScoutOutput
from spec4.agentifier.tier_analyst import TierAnalystOutput
from spec4.app_constants import STATE_IN_PROGRESS

from .test_agentifier_orchestrator import (
    _LLM_CONFIG,
    _SAMPLE_VISION,
    collect,
    mock_litellm_stream,
)

_CANDIDATES = [
    Candidate(
        name="smart_search",
        linked_vision_features=["search"],
        scope="feature",
        rough_description="Semantic search over product catalog.",
    ),
    Candidate(
        name="review_classifier",
        linked_vision_features=["reviews"],
        scope="sub_feature",
        rough_description="Classify review sentiment.",
    ),
]

_ANALYSIS = TierAnalystOutput(
    recommended_tier="single_call",
    rationale="One call handles the bounded extraction task.",
    risks_of_going_higher=["Unnecessary complexity."],
    risks_of_going_lower=["Deterministic approach misses edge cases."],
    borderline=False,
    borderline_seams=[],
    compared_to_next_tier_down="Embeddings would lose generation.",
)

_BRIEFING = "Here is your tier briefing for the selected features."


def _session() -> dict[str, Any]:
    return {
        "phase": "chat",
        "active_agent": "agentifier",
        "working_dir": None,
        "vision_statement": _SAMPLE_VISION,
        "code_review": None,
        "agentifier_state": STATE_IN_PROGRESS,
        "agentifier_messages": [],
        "agentifier_candidates": None,
        "agentifier_analyses": None,
        "ai_catalog": None,
        "agentifier_stale_acknowledged": {},
        "agentifier_artifact_msg_count": None,
        "tavily_api_key": None,
        "llm_config": _LLM_CONFIG,
    }


def _run_breadth_turn(session: dict[str, Any]) -> str:
    """Surface candidates, select them all, run the breadth-selection turn."""
    with (
        patch(
            "spec4.agentifier.agentifier._call_scout",
            return_value=ScoutOutput(candidates=_CANDIDATES),
        ),
        # The Linker now genuinely drains its stream (it used to fail on the
        # non-streaming mock without consuming it), so it must be patched out
        # or it would eat the briefing iterator before the turn under test.
        patch(
            "spec4.agentifier.agentifier._call_linker",
            return_value=LinkerOutput(overlay={}, outcome=LinkerOutcome.EMPTY),
        ),
        patch(
            "spec4.agentifier.agentifier._call_tier_analyst",
            return_value=_ANALYSIS,
        ),
        mock_litellm_stream(_BRIEFING),
    ):
        collect(agentifier.run(None, session, _LLM_CONFIG))
        pool = session.get("agentifier_scout_pool") or []
        session["agentifier_breadth_selection"] = [c["name"] for c in pool]
        return collect(agentifier.run("select", session, _LLM_CONFIG))


class TestBreadthTurnSeedsTheCounter:
    def test_published_total_covers_the_whole_turn(self) -> None:
        session = _session()
        out = _run_breadth_turn(session)

        # Everything the turn yielded: progress text plus the streamed briefing.
        assert session["_stream_received_chars"] == len(out)

    def test_progress_text_is_counted_not_discarded(self) -> None:
        """Without the seed the total would be the briefing alone."""
        session = _session()
        _run_breadth_turn(session)

        assert session["_stream_received_chars"] > len(_BRIEFING)

    def test_total_reflects_every_analysed_candidate(self) -> None:
        """Each candidate contributes one progress line, so a larger selection
        must seed a larger total."""
        session = _session()
        _run_breadth_turn(session)
        both = session["_stream_received_chars"]

        one_session = _session()
        with (
            patch(
                "spec4.agentifier.agentifier._call_scout",
                return_value=ScoutOutput(candidates=_CANDIDATES),
            ),
            patch(
                "spec4.agentifier.agentifier._call_linker",
                return_value=LinkerOutput(overlay={}, outcome=LinkerOutcome.EMPTY),
            ),
            patch(
                "spec4.agentifier.agentifier._call_tier_analyst",
                return_value=_ANALYSIS,
            ),
            mock_litellm_stream(_BRIEFING),
        ):
            collect(agentifier.run(None, one_session, _LLM_CONFIG))
            one_session["agentifier_breadth_selection"] = ["smart_search"]
            collect(agentifier.run("select", one_session, _LLM_CONFIG))

        assert both > one_session["_stream_received_chars"]

    def test_counter_does_not_dip_below_the_progress_text(self) -> None:
        """The regression D-AT3 prevents: at the moment the stream opens the
        published total must already account for what is on screen."""
        session = _session()
        seen: list[int] = []
        real = agentifier._stream_suppressing_json

        def spy(chunks: Any, sess: Any = None, seed: int = 0) -> Any:
            seen.append(seed)
            return real(chunks, sess, seed)

        with patch.object(agentifier, "_stream_suppressing_json", spy):
            out = _run_breadth_turn(session)

        assert seen and seen[0] > 0
        assert seen[0] == len(out) - len(_BRIEFING)


class TestTierAnalystDrainContinuity:
    """Phase-5 continuity: each per-candidate TierAnalyst drain continues the
    turn's running count and folds its total back, so the published counter
    interleaves progress-line jumps with live drain growth and never dips."""

    def test_counter_climbs_across_candidate_drains_without_dipping(self) -> None:
        session = _session()
        published: list[int] = []

        class _Spy(dict):
            def __setitem__(self, key: str, value: Any) -> None:
                if key == "_stream_received_chars":
                    published.append(value)
                super().__setitem__(key, value)

        spy = _Spy(session)
        tier_json = (
            '{"recommended_tier": "single_call", "rationale": "r",'
            ' "risks_of_going_higher": [], "risks_of_going_lower": [],'
            ' "borderline": false, "borderline_seams": [],'
            ' "compared_to_next_tier_down": "c"}'
        )

        def _fake_tier(_cand: Any, _cfg: Any, _review: Any, on_chunk: Any = None):
            if on_chunk is not None:
                for piece in (tier_json[:40], tier_json[40:]):
                    on_chunk(piece)
            return _ANALYSIS

        with (
            patch(
                "spec4.agentifier.agentifier._call_scout",
                return_value=ScoutOutput(candidates=_CANDIDATES),
            ),
            patch(
                "spec4.agentifier.agentifier._call_linker",
                return_value=LinkerOutput(overlay={}, outcome=LinkerOutcome.EMPTY),
            ),
            patch(
                "spec4.agentifier.agentifier._call_tier_analyst",
                side_effect=_fake_tier,
            ),
            mock_litellm_stream(_BRIEFING),
        ):
            collect(agentifier.run(None, spy, _LLM_CONFIG))
            pool = spy.get("agentifier_scout_pool") or []
            spy["agentifier_breadth_selection"] = [c["name"] for c in pool]
            published.clear()
            out = collect(agentifier.run("select", spy, _LLM_CONFIG))

        # Two candidates -> two drains, each contributing the fake deltas on
        # top of the progress lines; the orchestrator briefing follows.
        assert published == sorted(published), "counter dipped mid-turn"
        assert spy["_stream_received_chars"] == len(out) + 2 * len(tier_json)
