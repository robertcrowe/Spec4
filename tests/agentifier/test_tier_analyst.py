"""Tests for the Tier Analyst sub-agent."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import patch

import pytest

from spec4.agentifier.pattern_loader import TierPattern, load_patterns
from spec4.agentifier.scout import Candidate
from spec4.agentifier.tier_analyst import (
    TIER_ANALYST_SYSTEM_PROMPT,
    TierAnalystAgent,
    TierAnalystInput,
    TierAnalystOutput,
    _build_mechanism_absorption_list,
    _build_tier_descriptions,
    _parse_output,
)

_ALL_MECHANISM_NAMES = (
    "human_in_the_loop",
    "mcp",
    "parallel_fanout",
    "reflection",
    "retrieval_reranking",
    "structured_outputs",
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_LLM_CONFIG = {"model": "gpt-4o-mini", "api_key": "sk-test"}

_CANDIDATE = Candidate(
    name="smart_search",
    linked_vision_features=["search"],
    scope="sub_feature",
    rough_description="Natural language search using semantic embeddings.",
)

_SAMPLE_TIER_OUTPUT = {
    "recommended_tier": "embeddings",
    "rationale": "The task is semantic similarity search over a fixed corpus.",
    "risks_of_going_higher": ["Unnecessary LLM inference cost on every query."],
    "risks_of_going_lower": ["Keyword search misses paraphrases and synonyms."],
    "borderline": False,
    "borderline_seams": [],
    "compared_to_next_tier_down": (
        "Going with deterministic keyword search would miss paraphrase queries "
        "and synonyms, leading to poor recall on natural-language inputs."
    ),
}


def _make_mock_response(content: str) -> Any:
    """Iterator of text deltas, the shape complete_stream yields."""
    return iter([content])


def _make_tier_input(
    candidate: Candidate = _CANDIDATE,
    tier_patterns: list[TierPattern] | None = None,
) -> TierAnalystInput:
    if tier_patterns is None:
        tier_patterns, _ = load_patterns()
    return TierAnalystInput(
        candidate=candidate,
        llm_config=_LLM_CONFIG,
        tier_patterns=tier_patterns,
    )


# ---------------------------------------------------------------------------
# Guided redraw (D-TA7) — the developer's notes reach the tier review
# ---------------------------------------------------------------------------


class TestGuidance:
    def _user_content(self, guidance: list[str] | None) -> str:
        import asyncio

        kwargs: dict[str, Any] = {}
        if guidance is not None:
            kwargs["guidance"] = guidance
        inp = TierAnalystInput(
            candidate=_CANDIDATE, llm_config=_LLM_CONFIG, **kwargs
        )
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=_make_mock_response(json.dumps(_SAMPLE_TIER_OUTPUT)),
        ) as mock_llm:
            asyncio.run(TierAnalystAgent().run(inp))
        return mock_llm.call_args[1]["messages"][1]["content"]

    def test_defaults_to_empty(self) -> None:
        assert _make_tier_input().guidance == []

    def test_notes_are_listed(self) -> None:
        content = self._user_content(["Keep it simple.", "No agents."])
        assert "Developer guidance" in content
        assert "- Keep it simple." in content
        assert "- No agents." in content

    def test_no_guidance_leaves_the_prompt_byte_identical(self) -> None:
        assert self._user_content(None) == self._user_content([])
        assert "Developer guidance" not in self._user_content([" "])


# ---------------------------------------------------------------------------
# TIER_ANALYST_SYSTEM_PROMPT content guards
# ---------------------------------------------------------------------------


class TestTierAnalystPromptContent:
    """Lightweight guards that the two anti-over-engineering rules are present.

    These are substring checks only — they do NOT invoke a real LLM.
    Their purpose is to catch silent loss of the framing-strip or
    burden-of-proof language in a future refactor.
    """

    def test_framing_rules_present(self) -> None:
        """All four "X is not evidence" framing rules must survive refactors."""
        p = TIER_ANALYST_SYSTEM_PROMPT
        # Framing-strip rule about aspirational language.
        assert "Framing rule" in p
        assert "names are not evidence" in p
        assert "smart" in p
        assert "intelligent" in p
        assert "Evaluate the mechanism" in p
        # Data-scale / freshness framing rule (+ static-table clarification).
        assert "data scale and freshness are not evidence" in p
        assert "exact identifier" in p
        assert "datastore" in p
        assert "do NOT change" in p
        assert "does not mean a static" in p
        # Operability framing rule.
        assert "operational benefits are not evidence" in p
        assert "single_call" in p
        assert "deterministic preprocessing" in p
        assert "earlier LLM call" in p
        assert "do not invent" in p
        # Mechanisms-are-not-tiers framing rule (tier absorption).
        assert "mechanisms are not tiers" in p
        assert "NEVER moves a candidate up the ladder" in p
        assert "NOT orchestrated_subagents" in p
        assert "never changes the tier" in p
        assert "retrieval_reranking inside rag" in p
        assert "your output remains a tier only" in p

    def test_burden_of_proof_rule_present(self) -> None:
        """Burden-of-proof escalation rule + its input-property clarification."""
        p = TIER_ANALYST_SYSTEM_PROMPT
        assert "Burden of proof" in p
        assert "name a specific concrete input" in p
        assert "cannot name such an" in p
        # Balancing sentence for under-engineering.
        assert "Under-engineering signs" in p
        assert "tier that works, not the cheapest tier" in p
        # The escalation reason must be a property of the input itself.
        assert "property of the *input itself*" in p
        assert "never justify escalation" in p

    def test_prompt_format_succeeds_and_new_rules_brace_free(self) -> None:
        """TIER_ANALYST_SYSTEM_PROMPT.format() must succeed and new passages must be brace-free."""
        import re
        rendered = TIER_ANALYST_SYSTEM_PROMPT.format(
            tier_descriptions="PLACEHOLDER",
            mechanism_context="MECH_PLACEHOLDER",
        )
        assert "PLACEHOLDER" in rendered
        assert "MECH_PLACEHOLDER" in rendered
        # New framing rule paragraph
        idx1 = rendered.index("data scale and freshness are not evidence")
        para1 = rendered[idx1:idx1 + 900]
        assert not re.search(r"[{}]", para1)
        # Burden-of-proof clarification sentence
        idx2 = rendered.index("property of the *input itself*")
        sent2 = rendered[idx2:idx2 + 300]
        assert not re.search(r"[{}]", sent2)
        # Mechanisms-are-not-tiers rule: everything from the rule heading to
        # the end of the absorption list must be brace-free once the
        # placeholder value has been substituted in.
        idx3 = rendered.index("mechanisms are not tiers")
        para3 = rendered[idx3:idx3 + 2400]
        assert not re.search(r"[{}]", para3)


# ---------------------------------------------------------------------------
# _build_tier_descriptions
# ---------------------------------------------------------------------------


class TestBuildTierDescriptions:
    def test_includes_all_tiers(self) -> None:
        tiers, _ = load_patterns()
        desc = _build_tier_descriptions(tiers)
        for tier in tiers:
            assert tier.name in desc

    def test_ordered_by_tier_order(self) -> None:
        tiers, _ = load_patterns()
        desc = _build_tier_descriptions(tiers)
        # Search for the bold header format used by _build_tier_descriptions
        header_positions = [
            desc.index(f"**{t.tier_order}. {t.name}**")
            for t in sorted(tiers, key=lambda t: t.tier_order)
        ]
        assert header_positions == sorted(header_positions)

    def test_includes_when_works_and_when_doesnt(self) -> None:
        tiers, _ = load_patterns()
        desc = _build_tier_descriptions(tiers)
        assert "When it works" in desc
        assert "When it doesn't" in desc


# ---------------------------------------------------------------------------
# _build_mechanism_absorption_list
# ---------------------------------------------------------------------------


class TestBuildMechanismAbsorptionList:
    def test_includes_all_mechanism_names(self) -> None:
        _, mechanisms = load_patterns()
        block = _build_mechanism_absorption_list(mechanisms)
        assert len(mechanisms) == len(_ALL_MECHANISM_NAMES)
        for m in mechanisms:
            assert m.name in block

    def test_descriptions_are_trimmed(self) -> None:
        _, mechanisms = load_patterns()
        block = _build_mechanism_absorption_list(mechanisms)
        for line in block.splitlines():
            # One compact line per mechanism — never a full pattern body.
            assert len(line) < 260

    def test_empty_list_returns_empty_string(self) -> None:
        assert _build_mechanism_absorption_list([]) == ""


# ---------------------------------------------------------------------------
# _parse_output
# ---------------------------------------------------------------------------


class TestParseOutput:
    def test_parses_valid_json_object(self) -> None:
        valid_tiers = ["deterministic", "embeddings", "single_call"]
        result = _parse_output(json.dumps(_SAMPLE_TIER_OUTPUT), valid_tiers)
        assert result["recommended_tier"] == "embeddings"

    def test_returns_empty_dict_on_invalid_json(self) -> None:
        result = _parse_output("not json", ["deterministic"])
        assert result == {}

    def test_extracts_json_from_surrounding_text(self) -> None:
        text = "Here is my analysis:\n" + json.dumps(_SAMPLE_TIER_OUTPUT) + "\nDone."
        result = _parse_output(text, ["embeddings"])
        assert result.get("recommended_tier") == "embeddings"


# ---------------------------------------------------------------------------
# TierAnalystAgent.run
# ---------------------------------------------------------------------------


class TestTierAnalystAgentRun:
    def test_returns_tier_analyst_output(self) -> None:
        mock_response = _make_mock_response(json.dumps(_SAMPLE_TIER_OUTPUT))
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=mock_response,
        ):
            output = asyncio.run(TierAnalystAgent().run(_make_tier_input()))
        assert isinstance(output, TierAnalystOutput)

    def test_recommended_tier_is_valid(self) -> None:
        mock_response = _make_mock_response(json.dumps(_SAMPLE_TIER_OUTPUT))
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=mock_response,
        ):
            output = asyncio.run(TierAnalystAgent().run(_make_tier_input()))
        tiers, _ = load_patterns()
        valid_names = {t.name for t in tiers}
        assert output.recommended_tier in valid_names

    def test_loads_patterns_when_not_provided(self) -> None:
        """Tier Analyst loads patterns from the library if tier_patterns is empty."""
        input_no_patterns = TierAnalystInput(
            candidate=_CANDIDATE,
            llm_config=_LLM_CONFIG,
            tier_patterns=[],
        )
        mock_response = _make_mock_response(json.dumps(_SAMPLE_TIER_OUTPUT))
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=mock_response,
        ) as mock_llm:
            asyncio.run(TierAnalystAgent().run(input_no_patterns))

        call_kwargs = mock_llm.call_args[1]
        system = call_kwargs["messages"][0]["content"]
        # All nine tier names should appear in the system prompt
        for name in (
            "deterministic", "embeddings", "single_call", "rag", "tool_agent",
            "chained_calls", "planning_agent", "orchestrated_subagents",
            "multi_agent_collaboration",
        ):
            assert name in system

    def test_lazy_loads_mechanisms_when_not_provided(self) -> None:
        """Callers that predate mechanism_patterns still get the library —
        production, run_tier_eval, and the mechanism probe all measure the
        same prompt."""
        input_no_mechanisms = TierAnalystInput(
            candidate=_CANDIDATE,
            llm_config=_LLM_CONFIG,
            tier_patterns=[],
        )
        mock_response = _make_mock_response(json.dumps(_SAMPLE_TIER_OUTPUT))
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=mock_response,
        ) as mock_llm:
            asyncio.run(TierAnalystAgent().run(input_no_mechanisms))

        system = mock_llm.call_args[1]["messages"][0]["content"]
        for name in _ALL_MECHANISM_NAMES:
            assert name in system

    def test_injects_mechanism_patterns_into_system_prompt(self) -> None:
        _, mechanisms = load_patterns()
        tiers, _ = load_patterns()
        input_obj = TierAnalystInput(
            candidate=_CANDIDATE,
            llm_config=_LLM_CONFIG,
            tier_patterns=tiers,
            mechanism_patterns=mechanisms,
        )
        mock_response = _make_mock_response(json.dumps(_SAMPLE_TIER_OUTPUT))
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=mock_response,
        ) as mock_llm:
            asyncio.run(TierAnalystAgent().run(input_obj))

        system = mock_llm.call_args[1]["messages"][0]["content"]
        for name in _ALL_MECHANISM_NAMES:
            assert name in system
        assert "mechanisms are not tiers" in system

    def test_output_schema_stays_tier_only(self) -> None:
        """The mechanism context informs the tier decision; the Required-output
        JSON block must not grow a mechanisms key."""
        required = TIER_ANALYST_SYSTEM_PROMPT[
            TIER_ANALYST_SYSTEM_PROMPT.index("Required output") :
        ]
        assert '"recommended_tier"' in required
        assert '"mechanisms"' not in required

    def test_injects_tier_patterns_into_system_prompt(self) -> None:
        tiers, _ = load_patterns()
        input_obj = _make_tier_input(tier_patterns=tiers)
        mock_response = _make_mock_response(json.dumps(_SAMPLE_TIER_OUTPUT))
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=mock_response,
        ) as mock_llm:
            asyncio.run(TierAnalystAgent().run(input_obj))

        call_kwargs = mock_llm.call_args[1]
        system = call_kwargs["messages"][0]["content"]
        assert "deterministic" in system
        assert "multi_agent_collaboration" in system

    def test_passes_candidate_name_to_user_message(self) -> None:
        mock_response = _make_mock_response(json.dumps(_SAMPLE_TIER_OUTPUT))
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=mock_response,
        ) as mock_llm:
            asyncio.run(TierAnalystAgent().run(_make_tier_input()))

        call_kwargs = mock_llm.call_args[1]
        user_content = call_kwargs["messages"][1]["content"]
        assert "smart_search" in user_content

    def test_candidate_text_includes_linked_existing_workflow_when_set(self) -> None:
        brownfield = Candidate(
            name="smart_search",
            linked_vision_features=["search"],
            scope="sub_feature",
            rough_description="Natural language search using semantic embeddings.",
            linked_existing_workflow="keyword-based SQL LIKE search in views.py",
        )
        mock_response = _make_mock_response(json.dumps(_SAMPLE_TIER_OUTPUT))
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=mock_response,
        ) as mock_llm:
            asyncio.run(TierAnalystAgent().run(_make_tier_input(candidate=brownfield)))

        user_content = mock_llm.call_args[1]["messages"][1]["content"]
        assert "linked_existing_workflow" in user_content
        assert "keyword-based SQL LIKE search in views.py" in user_content

    def test_candidate_text_omits_key_when_empty(self) -> None:
        # Greenfield candidates (default "") keep the prompt byte-identical:
        # no empty-string key to spend attention on.
        mock_response = _make_mock_response(json.dumps(_SAMPLE_TIER_OUTPUT))
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=mock_response,
        ) as mock_llm:
            asyncio.run(TierAnalystAgent().run(_make_tier_input()))

        user_content = mock_llm.call_args[1]["messages"][1]["content"]
        assert "linked_existing_workflow" not in user_content

    def test_borderline_false_empties_seams(self) -> None:
        output_data = {
            **_SAMPLE_TIER_OUTPUT, "borderline": False, "borderline_seams": ["seam"]
        }
        mock_response = _make_mock_response(json.dumps(output_data))
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=mock_response,
        ):
            output = asyncio.run(TierAnalystAgent().run(_make_tier_input()))
        assert output.borderline is False
        assert output.borderline_seams == []

    def test_borderline_true_preserves_seams(self) -> None:
        output_data = {
            **_SAMPLE_TIER_OUTPUT,
            "recommended_tier": "single_call",
            "borderline": True,
            "borderline_seams": ["if input > 5000 tokens, escalate to rag"],
        }
        mock_response = _make_mock_response(json.dumps(output_data))
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=mock_response,
        ):
            output = asyncio.run(TierAnalystAgent().run(_make_tier_input()))
        assert output.borderline is True
        assert len(output.borderline_seams) == 1

    def test_invalid_recommended_tier_falls_back_to_first(self) -> None:
        output_data = {**_SAMPLE_TIER_OUTPUT, "recommended_tier": "made_up_tier"}
        mock_response = _make_mock_response(json.dumps(output_data))
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=mock_response,
        ):
            output = asyncio.run(TierAnalystAgent().run(_make_tier_input()))
        assert output.recommended_tier == "deterministic"

    def test_passes_agent_name(self) -> None:
        mock_response = _make_mock_response(json.dumps(_SAMPLE_TIER_OUTPUT))
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=mock_response,
        ) as mock_llm:
            asyncio.run(TierAnalystAgent().run(_make_tier_input()))

        call_kwargs = mock_llm.call_args[1]
        # The agent identifies itself to complete() via agent_name.
        assert call_kwargs.get("agent_name") == "tier_analyst"

    def test_uses_streamed_transport(self) -> None:
        """The response is drained internally via complete_stream, which owns
        stream=True and the stall timeout — run() must not override either."""
        mock_response = _make_mock_response(json.dumps(_SAMPLE_TIER_OUTPUT))
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=mock_response,
        ) as mock_llm:
            asyncio.run(TierAnalystAgent().run(_make_tier_input()))

        call_kwargs = mock_llm.call_args[1]
        assert "stream" not in call_kwargs
        assert "timeout" not in call_kwargs

    def test_agent_name_is_tier_analyst(self) -> None:
        assert TierAnalystAgent().name == "tier_analyst"

    def test_validates_input_type(self) -> None:
        with pytest.raises(TypeError):
            asyncio.run(TierAnalystAgent().run("not a TierAnalystInput"))  # type: ignore[arg-type]

    def test_output_has_all_required_fields(self) -> None:
        mock_response = _make_mock_response(json.dumps(_SAMPLE_TIER_OUTPUT))
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=mock_response,
        ):
            output = asyncio.run(TierAnalystAgent().run(_make_tier_input()))
        assert isinstance(output.recommended_tier, str)
        assert isinstance(output.rationale, str)
        assert isinstance(output.risks_of_going_higher, list)
        assert isinstance(output.risks_of_going_lower, list)
        assert isinstance(output.borderline, bool)
        assert isinstance(output.borderline_seams, list)
        assert isinstance(output.compared_to_next_tier_down, str)

    def test_compared_to_next_tier_down_is_populated(self) -> None:
        mock_response = _make_mock_response(json.dumps(_SAMPLE_TIER_OUTPUT))
        with patch(
            "spec4.agentifier.tier_analyst.complete_stream",
            return_value=mock_response,
        ):
            output = asyncio.run(TierAnalystAgent().run(_make_tier_input()))
        assert output.compared_to_next_tier_down != ""
