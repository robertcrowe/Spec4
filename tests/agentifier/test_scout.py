"""Tests for the Scout sub-agent."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from spec4.agentifier.scout import (
    ScoutAgent,
    ScoutInput,
    ScoutOutcome,
    ScoutOutput,
    _build_scout_system_prompt,
    _format_scout_revision_block,
    _parse_candidates,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_LLM_CONFIG = {"model": "gpt-4o-mini", "api_key": "sk-test"}

_SAMPLE_VISION: dict[str, Any] = {
    "vision_statement": {
        "name": "FoodieApp",
        "vision": {
            "purpose": "A restaurant discovery app with AI recommendations.",
            "key_features_mvp": [
                {"AI_Recommendations": {"description": "Personalized suggestions"}},
                {"User_Reviews": {"description": "Verified user reviews"}},
                {"Smart_Search": {"description": "Natural language search"}},
            ],
        },
    }
}

_SAMPLE_CANDIDATES_JSON = json.dumps(
    [
        {
            "name": "personalized_recommendations",
            "linked_vision_features": ["AI_Recommendations"],
            "scope": "feature",
            "rough_description": "AI-driven restaurant recommendations.",
        },
        {
            "name": "smart_search",
            "linked_vision_features": ["Smart_Search"],
            "scope": "sub_feature",
            "rough_description": "Natural language restaurant search using embeddings.",
        },
        {
            "name": "review_sentiment_analysis",
            "linked_vision_features": ["User_Reviews"],
            "scope": "sub_feature",
            "rough_description": "Classify review sentiment for better ranking.",
        },
    ]
)


def _make_mock_response(content: str) -> Any:
    """Iterator of text deltas, the shape complete_stream yields."""
    return iter([content])


# ---------------------------------------------------------------------------
# _parse_candidates
# ---------------------------------------------------------------------------


class TestParseCandidates:
    def test_parses_valid_json_array(self) -> None:
        candidates, outcome = _parse_candidates(_SAMPLE_CANDIDATES_JSON)
        assert len(candidates) == 3
        assert candidates[0].name == "personalized_recommendations"
        assert candidates[1].scope == "sub_feature"
        assert outcome is ScoutOutcome.OK

    def test_invalid_json_is_unreadable(self) -> None:
        candidates, outcome = _parse_candidates("not json at all")
        assert candidates == []
        assert outcome is ScoutOutcome.UNREADABLE

    def test_non_array_json_is_unreadable(self) -> None:
        candidates, outcome = _parse_candidates('{"key": "value"}')
        assert candidates == []
        assert outcome is ScoutOutcome.UNREADABLE

    def test_valid_empty_array_is_empty_not_unreadable(self) -> None:
        candidates, outcome = _parse_candidates("[]")
        assert candidates == []
        assert outcome is ScoutOutcome.EMPTY

    def test_array_of_nameless_items_is_empty(self) -> None:
        # A well-formed array that yields no usable candidates is a genuine
        # empty, not a parse failure.
        data = json.dumps([{"scope": "feature"}, {"rough_description": "x"}])
        candidates, outcome = _parse_candidates(data)
        assert candidates == []
        assert outcome is ScoutOutcome.EMPTY

    def test_skips_items_without_name(self) -> None:
        data = json.dumps([{"scope": "feature"}, {"name": "valid", "scope": "feature"}])
        candidates, outcome = _parse_candidates(data)
        assert len(candidates) == 1
        assert candidates[0].name == "valid"
        assert outcome is ScoutOutcome.OK

    def test_fills_defaults_for_missing_fields(self) -> None:
        data = json.dumps([{"name": "minimal"}])
        candidates, _outcome = _parse_candidates(data)
        assert len(candidates) == 1
        assert candidates[0].linked_vision_features == []
        assert candidates[0].scope == "feature"
        assert candidates[0].rough_description == ""

    def test_extracts_json_array_from_fenced_or_prefixed_response(self) -> None:
        wrapped = "Here are the candidates:\n" + _SAMPLE_CANDIDATES_JSON + "\nEnd."
        candidates, outcome = _parse_candidates(wrapped)
        assert len(candidates) == 3
        assert outcome is ScoutOutcome.OK

    def test_candidate_fields_are_strings(self) -> None:
        candidates, _outcome = _parse_candidates(_SAMPLE_CANDIDATES_JSON)
        for c in candidates:
            assert isinstance(c.name, str)
            assert isinstance(c.scope, str)
            assert isinstance(c.rough_description, str)
            assert isinstance(c.linked_vision_features, list)

    def test_edge_fields_default_empty_when_absent(self) -> None:
        # Scout surfaces nodes only; edges stay at their Candidate defaults —
        # the Linker populates composed_under / requires downstream.
        candidates, _outcome = _parse_candidates(_SAMPLE_CANDIDATES_JSON)
        for c in candidates:
            assert c.composed_under == ""
            assert c.requires == []

    def test_edges_are_not_parsed_from_scout_output(self) -> None:
        # Even when a model response carries edge fields (against instructions),
        # Scout ignores them — edge inference is the Linker's job.
        data = json.dumps(
            [
                {"name": "producer", "scope": "feature", "rough_description": "p"},
                {
                    "name": "consumer",
                    "scope": "feature",
                    "rough_description": "c",
                    "requires": ["producer"],
                    "composed_under": "producer",
                },
            ]
        )
        candidates, outcome = _parse_candidates(data)
        assert outcome is ScoutOutcome.OK
        by_name = {c.name: c for c in candidates}
        assert by_name["consumer"].requires == []
        assert by_name["consumer"].composed_under == ""


# ---------------------------------------------------------------------------
# ScoutAgent.run
# ---------------------------------------------------------------------------


class TestScoutAgentRun:
    def _make_input(self, code_review: Any = None) -> ScoutInput:
        return ScoutInput(
            vision=_SAMPLE_VISION,
            llm_config=_LLM_CONFIG,
            code_review=code_review,
        )

    def test_returns_scout_output(self) -> None:
        import asyncio
        mock_response = _make_mock_response(_SAMPLE_CANDIDATES_JSON)
        with patch(
            "spec4.agentifier.scout.complete_stream", return_value=mock_response
        ):
            output = asyncio.run(ScoutAgent().run(self._make_input()))
        assert isinstance(output, ScoutOutput)
        assert len(output.candidates) == 3

    def test_passes_vision_content_to_llm(self) -> None:
        mock_response = _make_mock_response("[]")
        with patch(
            "spec4.agentifier.scout.complete_stream", return_value=mock_response
        ) as mock_llm:
            import asyncio
            asyncio.run(ScoutAgent().run(self._make_input()))

        call_kwargs = mock_llm.call_args[1]
        messages = call_kwargs["messages"]
        user_content = messages[1]["content"]
        assert "FoodieApp" in user_content

    def test_passes_code_review_when_provided(self) -> None:
        code_review = {"is_software_project": True, "languages": []}
        mock_response = _make_mock_response("[]")
        with patch(
            "spec4.agentifier.scout.complete_stream", return_value=mock_response
        ) as mock_llm:
            import asyncio
            asyncio.run(ScoutAgent().run(self._make_input(code_review=code_review)))

        call_kwargs = mock_llm.call_args[1]
        messages = call_kwargs["messages"]
        user_content = messages[1]["content"]
        assert "code review" in user_content.lower()

    def test_omits_code_review_block_when_none(self) -> None:
        mock_response = _make_mock_response("[]")
        with patch(
            "spec4.agentifier.scout.complete_stream", return_value=mock_response
        ) as mock_llm:
            import asyncio
            asyncio.run(ScoutAgent().run(self._make_input(code_review=None)))

        call_kwargs = mock_llm.call_args[1]
        messages = call_kwargs["messages"]
        user_content = messages[1]["content"]
        assert "Code review" not in user_content

    def test_returns_empty_candidates_on_unparseable_response(self) -> None:
        import asyncio
        mock_response = _make_mock_response("I cannot find any candidates.")
        with patch(
            "spec4.agentifier.scout.complete_stream", return_value=mock_response
        ):
            output = asyncio.run(ScoutAgent().run(self._make_input()))
        assert output.candidates == []
        assert output.outcome is ScoutOutcome.UNREADABLE

    def test_genuine_empty_array_reports_empty_outcome(self) -> None:
        import asyncio
        mock_response = _make_mock_response("[]")
        with patch(
            "spec4.agentifier.scout.complete_stream", return_value=mock_response
        ):
            output = asyncio.run(ScoutAgent().run(self._make_input()))
        assert output.candidates == []
        assert output.outcome is ScoutOutcome.EMPTY

    def test_uses_streamed_transport(self) -> None:
        """The response is drained internally via complete_stream, which owns
        stream=True and the stall timeout — run() must not override either."""
        mock_response = _make_mock_response("[]")
        with patch(
            "spec4.agentifier.scout.complete_stream", return_value=mock_response
        ) as mock_llm:
            import asyncio
            asyncio.run(ScoutAgent().run(self._make_input()))

        call_kwargs = mock_llm.call_args[1]
        assert "stream" not in call_kwargs
        assert "timeout" not in call_kwargs

    def test_system_prompt_is_first_message(self) -> None:
        mock_response = _make_mock_response("[]")
        with patch(
            "spec4.agentifier.scout.complete_stream", return_value=mock_response
        ) as mock_llm:
            import asyncio
            asyncio.run(ScoutAgent().run(self._make_input()))

        call_kwargs = mock_llm.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert "DIVERGENT" in messages[0]["content"]

    def test_agent_name_is_scout(self) -> None:
        agent = ScoutAgent()
        assert agent.name == "scout"

    def test_validates_input_type(self) -> None:
        import asyncio
        with pytest.raises(TypeError):
            asyncio.run(ScoutAgent().run("not a ScoutInput"))  # type: ignore[arg-type]

    def test_uses_api_key_from_llm_config(self) -> None:
        mock_response = _make_mock_response("[]")
        with patch(
            "spec4.agentifier.scout.complete_stream", return_value=mock_response
        ) as mock_llm:
            import asyncio
            asyncio.run(ScoutAgent().run(self._make_input()))

        call_kwargs = mock_llm.call_args[1]
        assert call_kwargs["llm_config"]["api_key"] == "sk-test"

    def test_passes_api_base_when_present(self) -> None:
        llm_config = {**_LLM_CONFIG, "api_base": "https://example.com/v1"}
        scout_input = ScoutInput(vision=_SAMPLE_VISION, llm_config=llm_config)
        mock_response = _make_mock_response("[]")
        with patch(
            "spec4.agentifier.scout.complete_stream", return_value=mock_response
        ) as mock_llm:
            import asyncio
            asyncio.run(ScoutAgent().run(scout_input))

        call_kwargs = mock_llm.call_args[1]
        assert call_kwargs["llm_config"]["api_base"] == "https://example.com/v1"


# ---------------------------------------------------------------------------
# Revision mode — system prompt + revision block
# ---------------------------------------------------------------------------

_SAMPLE_REVISION = {
    "goal": "Add a returns/RMA flow.",
    "changes": {
        "added": ["Returns_Portal"],
        "modified": ["Order_Tracking"],
        "removed": ["Legacy_Coupons"],
    },
    "existing_ai_features": [
        {"name": "expiry_prediction", "linked_vision_features": ["Expiry_Tracking"]},
        {"name": "shopping_list_parse", "linked_vision_features": []},
    ],
}


class TestBuildScoutSystemPrompt:
    def test_base_only_when_greenfield(self) -> None:
        prompt = _build_scout_system_prompt(False, False)
        assert "DIVERGENT" in prompt
        assert "Brownfield mode" not in prompt
        assert "Revision mode" not in prompt

    def test_brownfield_addendum(self) -> None:
        prompt = _build_scout_system_prompt(True, False)
        assert "Brownfield mode" in prompt
        assert "Revision mode" not in prompt

    def test_revision_addendum(self) -> None:
        prompt = _build_scout_system_prompt(False, True)
        assert "Revision mode" in prompt
        assert "do not re-survey" in prompt.lower() or "not to re-survey" in prompt.lower()

    def test_brownfield_and_revision_compose(self) -> None:
        prompt = _build_scout_system_prompt(True, True)
        # both addenda present; base precedes brownfield precedes revision
        assert "Brownfield mode" in prompt
        assert "Revision mode" in prompt
        assert prompt.index("Brownfield mode") < prompt.index("Revision mode")


class TestFormatScoutRevisionBlock:
    def test_includes_goal_and_changes(self) -> None:
        block = _format_scout_revision_block(_SAMPLE_REVISION)
        assert "Add a returns/RMA flow." in block
        assert "Returns_Portal" in block
        assert "Order_Tracking" in block
        assert "Legacy_Coupons" in block

    def test_lists_existing_features_with_links(self) -> None:
        block = _format_scout_revision_block(_SAMPLE_REVISION)
        assert "expiry_prediction" in block
        assert "Expiry_Tracking" in block
        assert "shopping_list_parse" in block
        assert "do not re-surface" in block.lower()

    def test_handles_empty_change_arrays(self) -> None:
        block = _format_scout_revision_block(
            {"goal": "", "changes": {}, "existing_ai_features": []}
        )
        assert "(none)" in block
        assert "(none recorded)" in block


class TestScoutAgentRevisionWiring:
    def _input(self, revision: Any) -> ScoutInput:
        return ScoutInput(
            vision=_SAMPLE_VISION,
            llm_config=_LLM_CONFIG,
            code_review={"is_software_project": True},
            revision=revision,
        )

    def test_revision_injects_block_and_addendum(self) -> None:
        import asyncio
        mock_response = _make_mock_response("[]")
        with patch(
            "spec4.agentifier.scout.complete_stream", return_value=mock_response
        ) as mock_llm:
            asyncio.run(ScoutAgent().run(self._input(_SAMPLE_REVISION)))
        messages = mock_llm.call_args[1]["messages"]
        assert "Revision mode" in messages[0]["content"]
        assert "REVISION MODE" in messages[1]["content"]
        assert "Returns_Portal" in messages[1]["content"]

    def test_no_revision_block_when_none(self) -> None:
        import asyncio
        mock_response = _make_mock_response("[]")
        with patch(
            "spec4.agentifier.scout.complete_stream", return_value=mock_response
        ) as mock_llm:
            asyncio.run(ScoutAgent().run(self._input(None)))
        messages = mock_llm.call_args[1]["messages"]
        assert "Revision mode" not in messages[0]["content"]
        assert "REVISION MODE" not in messages[1]["content"]

# ---------------------------------------------------------------------------
# on_chunk receipt hook (D-PH9)
# ---------------------------------------------------------------------------


class TestOnChunk:
    def test_on_chunk_receives_every_delta(self) -> None:
        import asyncio

        deltas = ["[", '{"name": "a"},', '{"name": "b"}', "]"]
        seen: list[str] = []
        inp = ScoutInput(
            vision=_SAMPLE_VISION,
            llm_config=_LLM_CONFIG,
            on_chunk=seen.append,
        )
        with patch(
            "spec4.agentifier.scout.complete_stream",
            side_effect=lambda **kw: iter(deltas),
        ):
            output = asyncio.run(ScoutAgent().run(inp))
        assert seen == deltas
        assert len(output.candidates) == 2

    def test_on_chunk_default_none_drains_silently(self) -> None:
        import asyncio

        inp = ScoutInput(vision=_SAMPLE_VISION, llm_config=_LLM_CONFIG)
        assert inp.on_chunk is None
        with patch(
            "spec4.agentifier.scout.complete_stream",
            side_effect=lambda **kw: iter([_SAMPLE_CANDIDATES_JSON]),
        ):
            output = asyncio.run(ScoutAgent().run(inp))
        assert len(output.candidates) == 3


class TestBrownfieldIsToldNotInferred:
    """Scout's mode comes from the developer's answer, never from a scan.

    Regression: `brownfield = input.code_review is not None` meant that running
    CodeScanner over a greenfield skeleton put Scout into brownfield mode, where
    it looks for existing workflows each candidate would replace — of which a
    greenfield project has none. The review is still useful context; it just
    does not decide the mode.
    """

    def _input(self, **kwargs: Any) -> ScoutInput:
        return ScoutInput(vision=_SAMPLE_VISION, llm_config=_LLM_CONFIG, **kwargs)

    def test_defaults_to_greenfield(self) -> None:
        assert self._input().brownfield is False

    def test_a_code_review_does_not_flip_the_mode(self) -> None:
        assert self._input(code_review={"is_software_project": True}).brownfield is False

    def _system_prompt(self, scout_input: ScoutInput) -> str:
        import asyncio

        captured: list[str] = []

        def _completion(**kwargs: Any) -> Any:
            captured.append(kwargs["messages"][0]["content"])
            return _make_mock_response("[]")

        with patch("spec4.agentifier.scout.complete_stream", side_effect=_completion):
            asyncio.run(ScoutAgent().run(scout_input))
        return captured[0]

    def test_greenfield_scan_gets_the_base_prompt(self) -> None:
        prompt = self._system_prompt(
            self._input(code_review={"is_software_project": True}, brownfield=False)
        )
        assert prompt == _build_scout_system_prompt(False, False)

    def test_brownfield_gets_the_addendum_even_without_a_review(self) -> None:
        """The answer stands on its own — a scan is not a precondition."""
        prompt = self._system_prompt(self._input(code_review=None, brownfield=True))
        assert prompt == _build_scout_system_prompt(True, False)
