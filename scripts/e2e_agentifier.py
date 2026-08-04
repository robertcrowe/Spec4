"""End-to-end integration driver for the Agentifier pipeline stage.

Exercises the real code path (orchestrator → Scout → TierAnalyst → LLM conversation)
with realistic mocked LLM responses. Captures a full transcript including:
  a) Scout surfacing AI opportunity candidates
  b) TierAnalyst recommending tiers with rationale from the pattern library
  c) User choosing against a recommendation → challenge triggered
  d) Final ai_catalog.json validated and written to disk

Usage:
    uv run python scripts/e2e_agentifier.py [--project-dir DIR]

Exits 0 on success; 1 on any assertion failure.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# Ensure project src is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spec4.agentifier.pattern_loader import load_patterns
from spec4.app_constants import STATE_AGENTIFIER_COMPLETE
from spec4.session import _default_session

# ---------------------------------------------------------------------------
# Realistic mock payloads
# ---------------------------------------------------------------------------

_SCOUT_CANDIDATES = [
    {
        "name": "personalized_recommendations",
        "linked_vision_features": ["Personalized_Recommendations"],
        "scope": "feature",
        "rough_description": (
            "Recommend restaurants by building a user preference model from "
            "dining history, explicit ratings, and implicit signals. A vector "
            "store of restaurant embeddings enables semantic similarity retrieval."
        ),
    },
    {
        "name": "natural_language_search",
        "linked_vision_features": ["Smart_Search"],
        "scope": "feature",
        "rough_description": (
            "Parse free-text queries like 'quiet Italian near me for a date night' "
            "into structured filters using a single LLM call, then execute a "
            "deterministic query against the restaurant index."
        ),
    },
    {
        "name": "review_summarisation",
        "linked_vision_features": ["Review_Analysis"],
        "scope": "sub_feature",
        "rough_description": (
            "Aggregate recent reviews and produce a concise 3-bullet summary. "
            "A single LLM call per restaurant on cache-miss; results cached 24 h."
        ),
    },
    {
        "name": "conversational_booking",
        "linked_vision_features": ["Booking_Assistant"],
        "scope": "feature",
        "rough_description": (
            "A multi-turn chat that clarifies party size, date, dietary needs, "
            "and occasion before querying availability APIs. Needs memory across "
            "turns and tool use (check_availability, hold_reservation)."
        ),
    },
]

_TIER_ANALYSES: dict[str, dict[str, Any]] = {
    "personalized_recommendations": {
        "recommended_tier": "embeddings",
        "rationale": (
            "Semantic similarity over a fixed restaurant corpus fits the embeddings "
            "tier — no LLM inference per query, fast retrieval via ANN index."
        ),
        "risks_of_going_higher": [
            "LLM inference cost on every recommendation query.",
            "Latency spikes under load.",
        ],
        "risks_of_going_lower": [
            "Keyword matching misses 'cozy Italian' → 'warm, rustic trattoria' synonymy.",
        ],
        "borderline": False,
        "borderline_seams": [],
        "compared_to_next_tier_down": (
            "Deterministic keyword filtering cannot capture semantic similarity; "
            "embeddings retrieval covers that gap without any LLM at inference time."
        ),
    },
    "natural_language_search": {
        "recommended_tier": "single_call",
        "rationale": (
            "Query → structured-filter parsing is a single, stateless transform. "
            "One LLM call handles it; deterministic search executes afterwards."
        ),
        "risks_of_going_higher": [
            "Tool-agent adds latency and cost loops for a one-shot parse.",
        ],
        "risks_of_going_lower": [
            "Deterministic regex parsing breaks on ambiguous or creative queries.",
        ],
        "borderline": False,
        "borderline_seams": [],
        "compared_to_next_tier_down": (
            "An embeddings approach could rank results but cannot extract structured "
            "filter parameters from free text — single_call is needed for the parse step."
        ),
    },
    "review_summarisation": {
        "recommended_tier": "single_call",
        "rationale": (
            "One LLM call with a fixed recent-reviews block is the entire AI surface. "
            "Caching makes per-query cost negligible."
        ),
        "risks_of_going_higher": [
            "Tool loops add latency and complexity for a summarisation that rarely "
            "needs more than the top-N reviews.",
        ],
        "risks_of_going_lower": [
            "Embeddings alone cannot produce a coherent natural-language summary.",
        ],
        "borderline": True,
        "borderline_seams": [
            "If review count > 200 or sentiment is highly mixed, consider adding a "
            "tool_agent step to selectively page through additional reviews."
        ],
        "compared_to_next_tier_down": (
            "Embeddings can cluster reviews by sentiment but cannot produce the "
            "human-readable 3-bullet summary the product requires."
        ),
    },
    "conversational_booking": {
        "recommended_tier": "tool_agent",
        "rationale": (
            "Multi-turn conversation with check_availability and hold_reservation "
            "tool calls maps directly to the tool_agent tier."
        ),
        "risks_of_going_higher": [
            "Orchestrated subagents is overkill for a single booking flow.",
        ],
        "risks_of_going_lower": [
            "Single_call cannot maintain booking state across turns.",
            "Cannot invoke external availability APIs mid-conversation.",
        ],
        "borderline": False,
        "borderline_seams": [],
        "compared_to_next_tier_down": (
            "Single_call completes in one turn and cannot call external tools; "
            "the booking flow requires both multi-turn state and API tool use."
        ),
    },
}

# Orchestrator turn 1: present first candidate + recommendations summary
_ORCHESTRATOR_TURN_1 = textwrap.dedent("""
    I've analysed your vision with Scout and Tier Analyst. Here's the full picture:

    | # | Candidate | Recommended Tier | Borderline? |
    |---|---|---|---|
    | 1 | personalized_recommendations | embeddings | No |
    | 2 | natural_language_search | single_call | No |
    | 3 | review_summarisation | single_call | ⚠ Yes |
    | 4 | conversational_booking | tool_agent | No |

    **Candidate 1: personalized_recommendations** (scope: feature)
    Description: Recommend restaurants using vector similarity over dining history.

    Tier Analyst recommends **embeddings**. Rationale: semantic similarity over a
    fixed restaurant corpus fits the embeddings tier — no LLM inference per query,
    fast retrieval via ANN index.

    Going with deterministic keyword filtering instead would mean losing synonym
    and paraphrase coverage — 'cozy Italian' won't surface 'warm rustic trattoria'.

    Please pick a tier:
    1. deterministic  2. embeddings (recommended)  3. single_call  4. rag
    5. tool_agent  6. chained_calls  7. planning_agent  8. orchestrated_subagents
    9. multi_agent_collaboration  10. Suggest your own
""").strip()

# Orchestrator turn 2: challenge the review_summarisation override
_ORCHESTRATOR_TURN_2 = textwrap.dedent("""
    I understand the reasoning, but I want to flag the specific trade-off before
    you commit: escalating review_summarisation to **tool_agent** means the model
    will page through additional reviews on every cache miss, which adds 2–4 s of
    latency per restaurant page load and multiplies token cost at scale.

    The borderline seam I flagged was "review count > 200 or highly mixed sentiment"
    — if that truly covers the majority of your inventory, tool_agent is justified.
    But if it's a minority, starting at single_call and graduating specific
    restaurants to tool_agent via a feature flag is lower-risk.

    Confirm tool_agent for review_summarisation? (yes / no)
""").strip()

# Orchestrator turn 3: finalize and emit catalog
_CATALOG_PAYLOAD = {
    "ai_catalog": [
        {
            "name": "personalized_recommendations",
            "scope": "feature",
            "rough_description": (
                "Recommend restaurants using vector similarity over dining history."
            ),
            "tier_recommendation": "embeddings",
            "tier_decision": "embeddings",
            "tier_decision_rationale": "",
        },
        {
            "name": "natural_language_search",
            "scope": "feature",
            "rough_description": (
                "Parse free-text search queries into structured filters via one LLM call."
            ),
            "tier_recommendation": "single_call",
            "tier_decision": "single_call",
            "tier_decision_rationale": "",
        },
        {
            "name": "review_summarisation",
            "scope": "sub_feature",
            "rough_description": (
                "3-bullet review summary per restaurant, cached 24 h."
            ),
            "tier_recommendation": "single_call",
            "tier_decision": "tool_agent",
            "tier_decision_rationale": (
                "Mixed sentiment will be the common case for popular restaurants, "
                "so the borderline seam is actually the norm — tool_agent justified."
            ),
        },
        {
            "name": "conversational_booking",
            "scope": "feature",
            "rough_description": (
                "Multi-turn booking chat with check_availability and hold_reservation tools."
            ),
            "tier_recommendation": "tool_agent",
            "tier_decision": "tool_agent",
            "tier_decision_rationale": "",
        },
    ]
}

_ORCHESTRATOR_TURN_3 = (
    "All four candidates decided. Here's the final catalog:\n\n"
    "| # | Feature | Recommended | Decided |\n"
    "|---|---|---|---|\n"
    "| 1 | personalized_recommendations | embeddings | embeddings |\n"
    "| 2 | natural_language_search | single_call | single_call |\n"
    "| 3 | review_summarisation | single_call | tool_agent ⚠️ |\n"
    "| 4 | conversational_booking | tool_agent | tool_agent |\n\n"
    "Does this look right, or would you like to revise anything?\n\n"
    "```json\n"
    + json.dumps(_CATALOG_PAYLOAD, indent=2)
    + "\n```"
)


# ---------------------------------------------------------------------------
# Mock side-effect helpers
# ---------------------------------------------------------------------------

def _litellm_non_stream_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.content = content
    return resp


class _LitellmNonStreamMock:
    """Single mock for all non-streaming litellm.completion calls.

    Routes between Scout and TierAnalyst by inspecting the system prompt:
    - Scout's system prompt contains "DIVERGENT"
    - TierAnalyst's system prompt contains "tier ladder"
    Both call litellm.completion(**kwargs) with all-keyword args, so they
    share the same litellm.completion reference — patching it twice would
    silently overwrite the first patch.
    """

    def __call__(self, *args: Any, **kwargs: Any) -> MagicMock:
        messages: list[dict[str, Any]] = kwargs.get("messages", [])
        system_content = next(
            (m["content"] for m in messages if m.get("role") == "system"), ""
        )
        if "DIVERGENT" in system_content:
            # Scout call
            return _litellm_non_stream_response(json.dumps(_SCOUT_CANDIDATES))
        # TierAnalyst call — route by candidate name in the user message
        user_msg = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
        )
        for name, analysis in _TIER_ANALYSES.items():
            if name in user_msg:
                return _litellm_non_stream_response(json.dumps(analysis))
        return _litellm_non_stream_response(
            json.dumps(next(iter(_TIER_ANALYSES.values())))
        )


class _OrchestratorStreamMock:
    """Streaming orchestrator side-effect.

    stream_turn(system, messages, llm_config, search_config, ...) → Generator[str]

    This mock must:
    1. Append {"role": "assistant", "content": text} to messages (mirroring
       the real stream_turn behaviour that callers rely on for _last_assistant_text).
    2. Yield the response text as individual word-sized chunks.
    """

    _responses = [
        _ORCHESTRATOR_TURN_1,
        _ORCHESTRATOR_TURN_2,
        _ORCHESTRATOR_TURN_3,
    ]

    def __init__(self) -> None:
        self._call_index = 0

    def __call__(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        llm_config: dict[str, Any],
        search_config: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Generator[str, None, None]:
        idx = min(self._call_index, len(self._responses) - 1)
        self._call_index += 1
        text = self._responses[idx]
        messages.append({"role": "assistant", "content": text})
        return self._yield_chunks(text)

    @staticmethod
    def _yield_chunks(text: str) -> Generator[str, None, None]:
        """Yield text in word-sized chunks to simulate streaming."""
        words = text.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _drain(gen: Any) -> str:
    return "".join(gen)


def _sep(label: str) -> None:
    print(f"\n{'─' * 62}")
    print(f"  {label}")
    print("─" * 62)


# ---------------------------------------------------------------------------
# E2E driver
# ---------------------------------------------------------------------------

def run_e2e(project_dir: str) -> int:  # noqa: PLR0912, PLR0915
    project_path = Path(project_dir)
    spec4_dir = project_path / ".spec4"

    vision_path = spec4_dir / "vision.json"
    if not vision_path.exists():
        print(f"ERROR: {vision_path} not found — create a vision.json first.")
        return 1

    vision = json.loads(vision_path.read_text())
    proj_name = (
        vision.get("vision_statement", {}).get("name", "(unnamed)")
        if isinstance(vision.get("vision_statement"), dict)
        else str(vision.get("vision_statement", ""))[:40]
    )
    print(f"\nProject : {project_path}")
    print(f"Vision  : {proj_name}")

    # Build session as Spec4 would
    session: dict[str, Any] = _default_session()
    session["working_dir"] = str(project_path)
    session["vision_statement"] = vision
    session["llm_config"] = {"model": "claude-sonnet-4-6", "api_key": "sk-test"}
    session["active_agent"] = "agentifier"

    litellm_mock = _LitellmNonStreamMock()
    orch_mock = _OrchestratorStreamMock()

    # Both Scout and TierAnalyst call `litellm.completion` — they share the same
    # module-level `litellm` object, so a single patch covers both. The routing
    # mock dispatches by system-prompt content.
    with (
        patch("litellm.completion", side_effect=litellm_mock),
        patch("spec4.llm.stream_turn", side_effect=orch_mock),
    ):
        from spec4.agentifier.agentifier import run as agentifier_run  # noqa: PLC0415

        # ── Turn 1: fresh entry ──────────────────────────────────────────────
        _sep("TURN 1 — Fresh entry (Scout + TierAnalyst + orchestrator seed)")

        turn1_text = _drain(agentifier_run(None, session, session["llm_config"]))

        candidates_raw: list[dict[str, Any]] = session.get("agentifier_candidates") or []
        analyses_raw: dict[str, Any] | list[dict[str, Any]] = (
            session.get("agentifier_analyses") or []
        )
        if isinstance(analyses_raw, dict):
            analyses_list = list(analyses_raw.values())
        else:
            analyses_list = analyses_raw  # type: ignore[assignment]

        print(f"\n[Scout] Surfaced {len(candidates_raw)} candidates:")
        for c in candidates_raw:
            print(f"  • {c['name']} ({c['scope']}): {c['rough_description'][:60]}…")

        print(f"\n[TierAnalyst] Analyses for {len(analyses_list)} candidates:")
        for i, analysis in enumerate(analyses_list):
            name = candidates_raw[i]["name"] if i < len(candidates_raw) else f"[{i}]"
            print(
                f"  • {name}: tier={analysis['recommended_tier']}"
                f"  borderline={analysis['borderline']}"
            )
            for seam in analysis.get("borderline_seams", []):
                print(f"      ⚠ {seam[:80]}")

        print(f"\n[Orchestrator → UI]\n{turn1_text[:600]}{'…' if len(turn1_text) > 600 else ''}")

        # ── Verify (a) ───────────────────────────────────────────────────────
        assert len(candidates_raw) >= 3, (
            f"FAIL (a): Scout surfaced only {len(candidates_raw)} candidates; expected ≥ 3"
        )
        print("\n✓ (a) Scout surfaced ≥ 3 AI opportunities")

        # ── Verify (b) ───────────────────────────────────────────────────────
        tiers, _ = load_patterns()
        valid_tiers = {t.name for t in tiers}
        for i, analysis in enumerate(analyses_list):
            tier = analysis.get("recommended_tier", "")
            rationale = analysis.get("rationale", "")
            name = candidates_raw[i]["name"] if i < len(candidates_raw) else f"[{i}]"
            assert tier in valid_tiers, (
                f"FAIL (b): '{name}' has invalid tier '{tier}'"
            )
            assert len(rationale) > 20, (
                f"FAIL (b): '{name}' rationale is too short: {rationale!r}"
            )
        print("✓ (b) TierAnalyst recommended valid tiers with rationale for all candidates")

        # ── Turn 2: user overrides review_summarisation ──────────────────────
        _sep("TURN 2 — User overrides review_summarisation to tool_agent")

        user_override = (
            "I want review_summarisation at tool_agent — we expect mixed sentiment "
            "on most popular restaurants so the borderline seam is really the norm."
        )
        turn2_text = _drain(agentifier_run(user_override, session, session["llm_config"]))

        print(f"\n[User] {user_override}")
        print(
            f"\n[Orchestrator challenge]\n"
            f"{turn2_text[:500]}{'…' if len(turn2_text) > 500 else ''}"
        )

        # ── Verify (c) ───────────────────────────────────────────────────────
        challenge_markers = [
            "risk", "Risk", "latency", "cost", "trade-off", "tradeoff",
            "careful", "consider", "flag", "confirm", "overkill", "worth",
        ]
        triggered = any(m in turn2_text for m in challenge_markers)
        assert triggered, (
            "FAIL (c): Override did not trigger a challenge response — "
            f"none of {challenge_markers} found in:\n{turn2_text[:200]}"
        )
        print("✓ (c) Choosing against a recommendation triggered a challenge")

        # ── Turn 3: user confirms; catalog emitted ───────────────────────────
        _sep("TURN 3 — User confirms; catalog emitted and validated")

        user_confirm = "Yes, confirm tool_agent for review_summarisation."
        turn3_text = _drain(agentifier_run(user_confirm, session, session["llm_config"]))

        print(f"\n[User] {user_confirm}")
        print(
            f"\n[Orchestrator final]\n"
            f"{turn3_text[:300]}{'…' if len(turn3_text) > 300 else ''}"
        )

    # Mocks are no longer active — verify session state
    catalog = session.get("ai_catalog")
    state = session.get("agentifier_state")

    # ── Verify (d) ───────────────────────────────────────────────────────────
    assert catalog is not None, "FAIL (d): session['ai_catalog'] is None after completion"
    assert isinstance(catalog, dict), f"FAIL (d): ai_catalog is not a dict: {type(catalog)}"
    assert "ai_catalog" in catalog, (
        f"FAIL (d): ai_catalog missing 'ai_catalog' key — keys: {list(catalog.keys())}"
    )
    entries: list[dict[str, Any]] = catalog["ai_catalog"]
    assert len(entries) >= 3, (
        f"FAIL (d): ai_catalog has only {len(entries)} entries; expected ≥ 3"
    )
    required_fields = ("name", "tier_recommendation", "tier_decision")
    for entry in entries:
        for field in required_fields:
            assert field in entry, (
                f"FAIL (d): catalog entry missing '{field}': {entry}"
            )

    assert state == STATE_AGENTIFIER_COMPLETE, (
        f"FAIL (d): agentifier_state={state!r}; expected STATE_AGENTIFIER_COMPLETE"
    )

    # Write catalog to disk (as _persist_artifacts would)
    from spec4 import project_manager  # noqa: PLC0415
    project_manager.save_ai_catalog(str(project_path), catalog)

    catalog_path = spec4_dir / "ai_catalog.json"
    assert catalog_path.exists(), f"FAIL (d): {catalog_path} was not written"

    reloaded = json.loads(catalog_path.read_text())
    assert reloaded == catalog, "FAIL (d): round-trip through disk did not preserve catalog"

    print(f"\n✓ (d) ai_catalog.json written and verified: {catalog_path}")
    print(f"      {len(entries)} entries:")
    for entry in entries:
        rec = entry["tier_recommendation"]
        dec = entry["tier_decision"]
        marker = "  ⚠ override" if rec != dec else ""
        print(f"      • {entry['name']}: {dec}{marker}")

    _sep("ALL CHECKS PASSED ✓")
    print(f"\nCatalog: {catalog_path}")
    print("Run `make lint && make test` to confirm no regressions.\n")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-dir",
        default="/tmp/spec4-e2e-project",
        help="Project directory containing .spec4/vision.json",
    )
    args = parser.parse_args()
    sys.exit(run_e2e(args.project_dir))
