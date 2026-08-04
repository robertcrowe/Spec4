"""Tests for the Spec Drafter sub-agent."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from spec4.agentifier.pattern_loader import load_patterns
from spec4.agentifier.agentifier import _is_spec_confirmed
from spec4.agentifier.spec_drafter import (
    SpecDrafterAgent,
    SpecDrafterInput,
    _build_system_prompt,
    _tier_extra_fields,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_LLM_CONFIG = {"model": "gpt-4o-mini", "api_key": "sk-test"}

_SAMPLE_SPEC = {
    "purpose": "Enable natural language restaurant search.",
    "invocation": {"trigger": "User submits a search query", "mode": "synchronous"},
    "inputs": [{"name": "query", "type": "string", "description": "Search text", "required": True}],
    "outputs": {"primary": "Restaurant list", "format": "JSON array", "schema_notes": None},
    "decision_authority": "autonomous",
    "success_criteria": ["Top result matches user intent 85% of the time"],
    "failure_modes": [{"mode": "Model hallucination", "likelihood": "low", "mitigation": "Filter"}],
    "escalation": "Return empty results and log",
    "eval_approach": {"offline": "Golden eval set", "online": "Click-through rate", "ground_truth": "Human labels"},
    "budgets": {"cost_per_call": "$0.002", "p95_latency": "800ms"},
    "privacy_safety": ["No PII stored"],
    "phase_priority": "mvp",
    "mechanisms": [],
    "references": ["Anthropic Building Effective Agents"],
}


def _make_async_response(text: str) -> Any:
    """Return a mock coroutine that yields chunks when called as acompletion."""
    chunks = text.split()

    async def _acompletion_mock(**kwargs: Any) -> Any:
        async def _gen() -> Any:
            for word in chunks:
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = word + " "
                yield chunk

        return _gen()

    return _acompletion_mock


def _make_json_response(spec: dict[str, Any]) -> Any:
    text = "```json\n" + json.dumps(spec) + "\n```"
    return _make_async_response(text)


def _make_input(
    tier: str = "single_call",
    revision: str | None = None,
) -> SpecDrafterInput:
    tiers, mechanisms = load_patterns()
    return SpecDrafterInput(
        catalog_entry={
            "name": "smart_search",
            "scope": "feature",
            "rough_description": "Natural language restaurant search.",
            "tier_decision": tier,
            "tier_recommendation": tier,
            "tier_decision_rationale": "",
        },
        llm_config=_LLM_CONFIG,
        tier_patterns=tiers,
        mechanism_patterns=mechanisms,
        revision_instruction=revision,
    )


async def _drain(agent_input: SpecDrafterInput) -> list[str]:
    chunks: list[str] = []
    async for chunk in SpecDrafterAgent().stream(agent_input):
        chunks.append(chunk)
    return chunks


# ---------------------------------------------------------------------------
# _tier_extra_fields
# ---------------------------------------------------------------------------


class TestTierExtraFields:
    def test_single_call_has_no_extra_fields(self) -> None:
        result = _tier_extra_fields(3)  # single_call = order 3
        assert "knowledge_sources" not in result
        assert "tool_access" not in result
        assert "topology" not in result

    def test_rag_has_knowledge_sources(self) -> None:
        result = _tier_extra_fields(4)  # rag = order 4
        assert "knowledge_sources" in result
        assert "tool_access" not in result

    def test_tool_agent_has_tool_access(self) -> None:
        result = _tier_extra_fields(5)  # tool_agent = order 5
        assert "knowledge_sources" in result
        assert "tool_access" in result
        assert "topology" not in result

    def test_orchestrated_subagents_has_topology(self) -> None:
        result = _tier_extra_fields(8)  # orchestrated_subagents = order 8
        assert "knowledge_sources" in result
        assert "tool_access" in result
        assert "topology" in result

    def test_multi_agent_collaboration_has_topology(self) -> None:
        result = _tier_extra_fields(9)
        assert "topology" in result


# ---------------------------------------------------------------------------
# _build_system_prompt — tier-aware field sets (the 4 required tests)
# ---------------------------------------------------------------------------


class TestSystemPromptTierAwareness:
    """The 4 required tier-aware field tests."""

    def _get_prompt(self, tier: str) -> str:
        tiers, mechanisms = load_patterns()
        tier_order = {
            "deterministic": 1, "embeddings": 2, "single_call": 3, "rag": 4,
            "tool_agent": 5, "chained_calls": 6, "planning_agent": 7,
            "orchestrated_subagents": 8, "multi_agent_collaboration": 9,
        }.get(tier, 3)
        tier_pattern = next((t for t in tiers if t.name == tier), None)
        return _build_system_prompt(tier, tier_order, tier_pattern, mechanisms)

    def test_single_call_spec_has_no_tools(self) -> None:
        prompt = self._get_prompt("single_call")
        assert "tool_access" not in prompt

    def test_tool_agent_spec_has_tool_access(self) -> None:
        prompt = self._get_prompt("tool_agent")
        assert "tool_access" in prompt

    def test_orchestrated_subagents_spec_has_topology(self) -> None:
        prompt = self._get_prompt("orchestrated_subagents")
        assert "topology" in prompt

    def test_mechanisms_optional_per_feature(self) -> None:
        prompt = self._get_prompt("single_call")
        # Mechanisms section should exist but be marked optional
        assert "mechanisms" in prompt
        assert "OPTIONAL" in prompt or "zero or more" in prompt


# ---------------------------------------------------------------------------
# _build_system_prompt — mechanism pattern library content
# ---------------------------------------------------------------------------


class TestSystemPromptMechanismLibrary:
    """The full pattern content (description + all four sign lists) reaches the
    prompt, with the selection protocol that gates inclusion on a cited
    "When it works" match and vetoes on over-engineering signs."""

    def _prompt(self, mechanisms: list[Any]) -> str:
        tiers, _ = load_patterns()
        tier_pattern = next(t for t in tiers if t.name == "single_call")
        return _build_system_prompt("single_call", 3, tier_pattern, mechanisms)

    def test_includes_all_names_and_all_sections(self) -> None:
        _, mechanisms = load_patterns()
        prompt = self._prompt(mechanisms)
        for m in mechanisms:
            assert m.name in prompt
        assert "When it works" in prompt
        assert "When it doesn't" in prompt
        assert "Over-engineering signs" in prompt
        assert "Under-engineering signs" in prompt

    def test_full_bullet_content_present_not_just_summaries(self) -> None:
        """A sign bullet from deep inside a pattern proves the whole body is
        rendered, not a truncated slice."""
        _, mechanisms = load_patterns()
        prompt = self._prompt(mechanisms)
        reflection = next(m for m in mechanisms if m.name == "reflection")
        assert reflection.when_works[0] in prompt
        assert reflection.over_engineering_signs[0] in prompt

    def test_empty_mechanism_list_tolerated(self) -> None:
        prompt = self._prompt([])
        # No dangling library header, but the schema field and its optionality
        # rule remain.
        assert "Mechanism pattern library" not in prompt
        assert "mechanisms" in prompt
        assert "OPTIONAL" in prompt

    def test_selection_protocol_present(self) -> None:
        _, mechanisms = load_patterns()
        prompt = self._prompt(mechanisms)
        assert "MUST cite" in prompt
        assert "VETO" in prompt
        assert "zero mechanisms is correct" in prompt

    def test_full_library_does_not_leak_tier_fields(self) -> None:
        """Guards the single_call negative invariant against future pattern-file
        edits now that whole .md bodies are injected."""
        _, mechanisms = load_patterns()
        prompt = self._prompt(mechanisms)
        assert "tool_access" not in prompt
        assert "topology" not in prompt

    def test_sharpened_guardrails_present(self) -> None:
        _, mechanisms = load_patterns()
        prompt = self._prompt(mechanisms)
        # Reranking needs a real corpus, with the one-document case called out.
        assert "thousands of documents" in prompt
        assert "is not a corpus" in prompt
        # MCP consumption defaults to reuse for the named capability families.
        assert "reuse-over-rebuild" in prompt
        # UI-facing warnings/flags are displayed, not parsed — no schema.
        assert "displayed, not parsed" in prompt
        assert "code reads this field?" in prompt

    def test_tool_access_source_defaults_to_existing_mcp_server(self) -> None:
        """The tool_access schema itself biases source selection toward reuse —
        the agreement rule only fires if the model picks the mcp source, so
        the default has to live where the choice is made."""
        tiers, mechanisms = load_patterns()
        tool_tier = next(t for t in tiers if t.name == "tool_agent")
        prompt = _build_system_prompt("tool_agent", 5, tool_tier, mechanisms)
        assert "DEFAULT to existing_third_party_mcp" in prompt
        assert "name the existing server you rejected" in prompt

    def test_mcp_tool_access_agreement_rule_is_tier_conditional(self) -> None:
        """Tiers that carry tool_access get the agreement rule wiring the mcp
        mechanism to the capability source; lower tiers must not mention
        tool_access at all."""
        tiers, mechanisms = load_patterns()
        tool_tier = next(t for t in tiers if t.name == "tool_agent")
        prompt = _build_system_prompt("tool_agent", 5, tool_tier, mechanisms)
        assert '"mechanisms" and "tool_access" must agree' in prompt
        assert "existing_third_party_mcp" in prompt
        assert "must agree" not in self._prompt(mechanisms)  # single_call


# ---------------------------------------------------------------------------
# SpecDrafterAgent — LLM call behaviour
# ---------------------------------------------------------------------------


class TestSpecDrafterAgentLlmCalls:
    def test_returns_async_generator(self) -> None:
        import inspect
        tiers, mechanisms = load_patterns()
        agent = SpecDrafterAgent()
        inp = _make_input()

        async def _check() -> None:
            with patch(
                "spec4.agentifier.spec_drafter.acomplete",
                new=_make_json_response(_SAMPLE_SPEC),
            ):
                gen = agent.stream(inp)
                assert inspect.isasyncgen(gen)
                async for _ in gen:
                    break

        asyncio.run(_check())

    def test_yields_multiple_chunks(self) -> None:
        with patch(
            "spec4.agentifier.spec_drafter.acomplete",
            new=_make_json_response(_SAMPLE_SPEC),
        ):
            chunks = asyncio.run(_drain(_make_input()))
        assert len(chunks) > 1

    def test_agent_name_is_spec_drafter(self) -> None:
        assert SpecDrafterAgent().name == "spec_drafter"

    def test_validates_input_type(self) -> None:
        with pytest.raises(TypeError):
            asyncio.run(_drain("not a SpecDrafterInput"))  # type: ignore[arg-type]

    def test_passes_tier_to_system_prompt(self) -> None:
        calls: list[dict[str, Any]] = []

        async def _capture(**kwargs: Any) -> Any:
            calls.append(kwargs)

            async def _gen() -> Any:
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = "```json\n{}\n```"
                yield chunk

            return _gen()

        async def _run() -> None:
            with patch(
                "spec4.agentifier.spec_drafter.acomplete",
                new=_capture,
            ):
                async for _ in SpecDrafterAgent().stream(_make_input("tool_agent")):
                    pass

        asyncio.run(_run())
        system = calls[0]["messages"][0]["content"]
        assert "tool_agent" in system

    def test_passes_agent_name(self) -> None:
        captured: list[dict[str, Any]] = []

        async def _cap(**kwargs: Any) -> Any:
            captured.append(kwargs)

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = '```json\n{"purpose":"x"}\n```'
                yield c

            return _gen()

        with patch("spec4.agentifier.spec_drafter.acomplete", new=_cap):
            asyncio.run(_drain(_make_input()))

        # The agent identifies itself to acomplete() via agent_name.
        assert captured[0].get("agent_name") == "spec_drafter"

    def test_uses_streaming_call(self) -> None:
        captured: list[dict[str, Any]] = []

        async def _cap(**kwargs: Any) -> Any:
            captured.append(kwargs)

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = "x"
                yield c

            return _gen()

        with patch("spec4.agentifier.spec_drafter.acomplete", new=_cap):
            asyncio.run(_drain(_make_input()))

        assert captured[0].get("stream") is True

    def test_passes_api_key(self) -> None:
        captured: list[dict[str, Any]] = []

        async def _cap(**kwargs: Any) -> Any:
            captured.append(kwargs)

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = "x"
                yield c

            return _gen()

        with patch("spec4.agentifier.spec_drafter.acomplete", new=_cap):
            asyncio.run(_drain(_make_input()))

        assert captured[0]["llm_config"]["api_key"] == "sk-test"

    def test_passes_api_base_when_present(self) -> None:
        tiers, mechanisms = load_patterns()
        inp = SpecDrafterInput(
            catalog_entry={"tier_decision": "single_call", "name": "x"},
            llm_config={**_LLM_CONFIG, "api_base": "https://custom.example.com/v1"},
            tier_patterns=tiers,
            mechanism_patterns=mechanisms,
        )
        captured: list[dict[str, Any]] = []

        async def _cap(**kwargs: Any) -> Any:
            captured.append(kwargs)

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = "x"
                yield c

            return _gen()

        with patch("spec4.agentifier.spec_drafter.acomplete", new=_cap):
            asyncio.run(_drain(inp))

        assert captured[0]["llm_config"]["api_base"] == "https://custom.example.com/v1"

    def test_revision_instruction_in_user_message(self) -> None:
        captured: list[dict[str, Any]] = []

        async def _cap(**kwargs: Any) -> Any:
            captured.append(kwargs)

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = '```json\n{"purpose":"y"}\n```'
                yield c

            return _gen()

        with patch("spec4.agentifier.spec_drafter.acomplete", new=_cap):
            asyncio.run(_drain(_make_input("single_call", revision="Change phase_priority to steel_thread")))

        user_msg = captured[0]["messages"][1]["content"]
        assert "Change phase_priority" in user_msg

    def test_no_revision_when_none(self) -> None:
        captured: list[dict[str, Any]] = []

        async def _cap(**kwargs: Any) -> Any:
            captured.append(kwargs)

            async def _gen() -> Any:
                c = MagicMock()
                c.choices = [MagicMock()]
                c.choices[0].delta.content = "x"
                yield c

            return _gen()

        with patch("spec4.agentifier.spec_drafter.acomplete", new=_cap):
            asyncio.run(_drain(_make_input()))

        user_msg = captured[0]["messages"][1]["content"]
        assert "Revision instruction" not in user_msg


# ---------------------------------------------------------------------------
# _is_spec_confirmed
# ---------------------------------------------------------------------------


class TestIsSpecConfirmed:
    @pytest.mark.parametrize(
        "text",
        ["yes", "Yes", "YES", "y", "ok", "okay", "lgtm", "looks good",
         "good", "next", "continue", "confirm", "done", "approved"],
    )
    def test_affirmative_words(self, text: str) -> None:
        assert _is_spec_confirmed(text) is True

    @pytest.mark.parametrize(
        "text",
        ["no", "change the phase_priority", "actually revise the inputs",
         "what does tool_agent mean", ""],
    )
    def test_non_affirmative(self, text: str) -> None:
        assert _is_spec_confirmed(text) is False

    def test_yes_with_trailing_punctuation(self) -> None:
        assert _is_spec_confirmed("yes!") is True
        assert _is_spec_confirmed("yes.") is True

    def test_yes_as_prefix_of_longer_word(self) -> None:
        # "yesterday" should NOT be confirmed
        assert _is_spec_confirmed("yesterday was fine") is False
