"""The agentifier generators' documented session writes, driven from their own entry.

7q3's contract check found, for four generators, documented keys that the suite never
saw change under the generator's own traced entry (CLEANUP_INVENTORY.md 79.3). The
tests reached those paths only through ``run``, or their writes left a value equal to
the one already there. The set was re-derived at Phase 8 with
``scripts/cleanup/contract_check.py``, and it is the same 31 keys (PHASE8_RECORD.md 8g).

Each test drives one documented path from the generator itself. It records every key
that changed at any yield against the session the generator was given, so a key written
and then popped inside the turn still counts. The start values differ from what the
path writes, so a write is seen even where the path writes a default. Each test asserts
that its path's keys were written, named literally rather than read from the collections
that write them, and pairs that with one key the path must not write.
``contract_check.py`` checks the converse over the whole suite: that nothing a
generator writes goes undocumented.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

from spec4.agentifier import agentifier
from spec4.agentifier._seed import candidates_to_dicts
from spec4.agentifier.agentifier import (
    _RESTART_DEFAULTS,
    _RESTART_POP,
    finalize_specs,
    handle_reentry,
    reselection_pool_from_features,
    run_catalog_phase,
    run_cross_cutting_phase,
)
from spec4.agentifier.cross_cutting_analyst import warranted_topics
from spec4.agentifier.scout import Candidate, ScoutOutput
from spec4.app_constants import STATE_AGENTIFIER_COMPLETE
from spec4.session import default_session

from .test_agentifier_orchestrator import (
    _LLM_CONFIG,
    _SAMPLE_VISION,
    mock_litellm_stream,
)


def _changed(start: dict[str, Any], now: dict[str, Any]) -> set[str]:
    return {
        key
        for key in start.keys() | now.keys()
        if key not in start or key not in now or start[key] != now[key]
    }


def _written(gen: Iterator[str], session: dict[str, Any]) -> set[str]:
    """Every key changed at any yield, and at the end, against the starting session."""
    start = copy.deepcopy(session)
    written: set[str] = set()
    for _ in gen:
        written |= _changed(start, session)
    return written | _changed(start, session)


_ANALYSIS = {
    "provider_strategy": {
        "recommendation": "one provider behind a thin client",
        "rationale": "r",
        "cited_patterns": [],
    },
    "prompt_versioning": {
        "recommendation": "prompts live in the repo",
        "rationale": "r",
        "cited_patterns": [],
    },
}

# A generative feature: it warrants provider_strategy and prompt_versioning.
_FEATURE = {
    "id": "alpha",
    "name": "alpha",
    "tier": "single_call",
    "phase_priority": "mvp",
    "purpose": "p",
    "rough_description": "alpha",
}


def _analyst_replies(text: str) -> Any:
    """The Cross-Cutting Analyst's stream, replaced by ``text`` in small chunks."""

    def _stream(_name: str, _input: Any) -> Any:
        async def _gen() -> Any:
            for i in range(0, len(text), 16):
                yield text[i : i + 16]

        return _gen()

    return patch.object(agentifier._registry, "stream", side_effect=_stream)


class TestHandleReentryContract:
    def test_the_stale_path_resets_every_restart_key(self) -> None:
        """With stale inputs, the reset writes every restart default and pops every
        restart key, and ``ai_features`` stays for the redraw to replace."""
        session = default_session()
        session["working_dir"] = "/tmp/spec4-contract"
        session["agentifier_state"] = STATE_AGENTIFIER_COMPLETE
        session["ai_features"] = {"ai_features": [dict(_FEATURE)]}
        for key in (*_RESTART_DEFAULTS, *_RESTART_POP):
            session[key] = f"left from an earlier round: {key}"
        kept = session["ai_features"]

        def _fake_catalog(_ui: Any, _s: Any, _cfg: Any) -> Iterator[str]:
            yield "rediscovering"

        with (
            patch.object(
                agentifier.project_manager,
                "detect_stale_inputs",
                return_value={"vision": 1.0},
            ),
            patch.object(agentifier, "run_catalog_phase", side_effect=_fake_catalog),
        ):
            written = _written(handle_reentry(None, session, _LLM_CONFIG), session)

        never_seen = {
            "agentifier_artifact_msg_count",
            "agentifier_carried_forward",
            "agentifier_cc_ff_locked",
            "agentifier_compositions",
            "agentifier_cross_cutting_ff_review",
            "agentifier_preserved_selected",
            "agentifier_revision",
            "agentifier_revision_cross_cutting",
            "agentifier_revision_delta",
            "agentifier_revision_prior_version",
            "agentifier_revision_version",
            "agentifier_spec_ff_locked",
            "agentifier_spec_ff_review",
        }
        assert never_seen <= written
        assert never_seen.isdisjoint(session)
        assert session["agentifier_messages"] == []
        assert session["agentifier_stale_acknowledged"] == {"vision": 1.0}
        assert "ai_features" not in written
        assert session["ai_features"] is kept


class TestFinalizeSpecsContract:
    def test_a_warranted_topic_draws_and_stores_the_analysis(self) -> None:
        """A re-selection whose features warrant topics: the draw writes the
        received-character counter, the stored analysis resets the cursor a
        previous round left behind, and the re-selection state is popped."""
        feature = dict(_FEATURE)
        session = default_session()
        session.update(
            {
                "agentifier_messages": [],
                "agentifier_reselection": True,
                "agentifier_preserved_features": {"alpha": feature},
                "agentifier_preserved_selected": [feature],
                "ai_catalog": {"ai_catalog": []},
                "agentifier_spec_results": [],
                "agentifier_candidates": [],
                "agentifier_analyses": [],
                "_stream_received_chars": 0,
                # Where the previous round's walk stopped.
                "agentifier_cross_cutting_index": 2,
                "agentifier_cross_cutting_decisions": {"provider_strategy": {}},
            }
        )
        topics = warranted_topics([feature])
        analysis = {t: _ANALYSIS[t] for t in topics}
        with _analyst_replies(json.dumps(analysis)):
            written = _written(finalize_specs(session, _LLM_CONFIG), session)

        assert {
            "_stream_received_chars",
            "agentifier_cross_cutting_analysis",
            "agentifier_cross_cutting_decisions",
            "agentifier_cross_cutting_index",
            "agentifier_cross_cutting_topics",
            "agentifier_preserved_features",
        } <= written
        assert session["agentifier_cross_cutting_topics"] == topics
        assert session["agentifier_cross_cutting_analysis"] == analysis
        assert session["agentifier_cross_cutting_index"] == 0
        assert session["agentifier_cross_cutting_decisions"] == {}
        assert session["_stream_received_chars"] > 0
        assert "agentifier_preserved_features" not in session
        assert "agentifier_cross_cutting_done" not in written


class TestCrossCuttingPhaseContract:
    def test_the_reload_rerun_stores_the_warranted_topics(self) -> None:
        """A reply with no stored analysis (a reload lost it) re-runs the analyst
        and stores the topics the feature set warrants."""
        feature = dict(_FEATURE)
        session = default_session()
        session.update(
            {
                "agentifier_messages": [],
                "agentifier_spec_done": True,
                "ai_features": {"ai_features": [feature], "cross_cutting": {}},
                "agentifier_cross_cutting_analysis": None,
                "agentifier_cross_cutting_topics": [],
            }
        )
        topics = warranted_topics([feature])
        analysis = {t: _ANALYSIS[t] for t in topics}
        with _analyst_replies(json.dumps(analysis)):
            written = _written(
                run_cross_cutting_phase("yes", session, _LLM_CONFIG), session
            )

        assert "agentifier_cross_cutting_topics" in written
        assert session["agentifier_cross_cutting_topics"] == topics
        assert session["agentifier_cross_cutting_analysis"] == analysis
        assert "agentifier_cross_cutting_done" not in written


class TestCatalogPhaseContract:
    def test_a_fresh_start_writes_the_breadth_question(self) -> None:
        """Scout, then the breadth question: the pool, the groups, the intro, a
        fresh nonce, the compositions, and a panel not yet chosen."""
        session = default_session()
        session["vision_statement"] = _SAMPLE_VISION
        # A panel an earlier draw left chosen: the fresh start must re-open it.
        session["agentifier_breadth_chosen"] = True
        candidate = Candidate(
            name="smart_search",
            linked_vision_features=["search"],
            scope="feature",
            rough_description="Semantic search over product catalog.",
        )
        with (
            patch(
                "spec4.agentifier.agentifier._call_scout",
                return_value=ScoutOutput(candidates=[candidate]),
            ),
            mock_litellm_stream("Hello!"),
        ):
            written = _written(run_catalog_phase(None, session, _LLM_CONFIG), session)

        assert {
            "agentifier_breadth_chosen",
            "agentifier_breadth_groups",
            "agentifier_breadth_intro",
            "agentifier_breadth_nonce",
            "agentifier_compositions",
            "agentifier_scout_pool",
        } <= written
        assert [c["name"] for c in session["agentifier_scout_pool"]] == [candidate.name]
        assert session["agentifier_breadth_chosen"] is False
        assert "ai_catalog" not in written

    def test_a_reselection_that_adds_nothing_writes_the_catalog(self) -> None:
        """Every preserved feature kept, none added: the selection's keys and the
        reply's are written, and the turn hands off to ``finalize_specs``."""
        feature = dict(_FEATURE, tier="deterministic")
        session = default_session()
        session.update(
            {
                "agentifier_reselection": True,
                "agentifier_preserved_features": {"alpha": feature},
                "agentifier_scout_pool": candidates_to_dicts(
                    reselection_pool_from_features({"ai_features": [feature]})
                ),
                "agentifier_breadth_selection": ["alpha"],
                "agentifier_breadth_chosen": False,
                # A spec walk an earlier round left part-way.
                "agentifier_spec_index": 3,
                "agentifier_spec_results": [{"purpose": "earlier"}],
            }
        )
        written = _written(run_catalog_phase("select", session, _LLM_CONFIG), session)

        assert {
            "agentifier_explicitly_rejected",
            "agentifier_preserved_selected",
            "agentifier_spec_index",
            "agentifier_spec_results",
            "ai_catalog",
        } <= written
        assert session["ai_catalog"] == {"ai_catalog": []}
        assert session["agentifier_spec_index"] == 0
        assert session["agentifier_spec_results"] == []
        assert [f["name"] for f in session["ai_features"]["ai_features"]] == ["alpha"]
        assert "agentifier_breadth_intro" not in written
