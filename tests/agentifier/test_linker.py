"""Tests for the Linker sub-agent.

The Linker wires the graph contract (``composed_under`` / ``requires``) over the
closed candidate set Scout surfaced, emitting an edge *overlay*. These cover
overlay parsing (including the OK / EMPTY / UNREADABLE outcomes and the single
reparse), the authoritative overlay merge, and the agent's request shape. The
relocated edge-integrity pass (``_normalize_edges``) is covered separately in
``test_linker_edges.py``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import patch

from spec4.agentifier.linker import (
    EdgeOverlay,
    LinkerAgent,
    LinkerInput,
    LinkerOutcome,
    LinkerOutput,
    _extract_json_object,
    _format_candidates_block,
    _parse_overlay,
    apply_overlay,
)
from spec4.agentifier.scout import Candidate

_LLM_CONFIG = {"model": "gpt-4o-mini", "api_key": "sk-test"}


def _candidate(
    name: str,
    *,
    scope: str = "feature",
    rough_description: str = "",
    composed_under: str = "",
    requires: list[str] | None = None,
) -> Candidate:
    return Candidate(
        name=name,
        linked_vision_features=[],
        scope=scope,
        rough_description=rough_description,
        composed_under=composed_under,
        requires=list(requires or []),
    )


def _make_mock_response(content: str) -> Any:
    """Iterator of text deltas, the shape complete_stream yields."""
    return iter([content])


# ---------------------------------------------------------------------------
# _parse_overlay
# ---------------------------------------------------------------------------


class TestParseOverlay:
    def test_parses_edges_and_reports_ok(self) -> None:
        raw = json.dumps(
            {
                "consumer": {"composed_under": "", "requires": ["producer"]},
                "member": {"composed_under": "coord", "requires": []},
            }
        )
        overlay, outcome = _parse_overlay(raw)
        assert outcome is LinkerOutcome.OK
        assert overlay["consumer"].requires == ["producer"]
        assert overlay["member"].composed_under == "coord"

    def test_readable_but_no_edges_is_empty(self) -> None:
        raw = json.dumps({"a": {"composed_under": "", "requires": []}})
        overlay, outcome = _parse_overlay(raw)
        assert outcome is LinkerOutcome.EMPTY
        assert "a" in overlay

    def test_empty_object_is_empty(self) -> None:
        overlay, outcome = _parse_overlay("{}")
        assert outcome is LinkerOutcome.EMPTY
        assert overlay == {}

    def test_unparseable_is_unreadable(self) -> None:
        overlay, outcome = _parse_overlay("not json at all")
        assert outcome is LinkerOutcome.UNREADABLE
        assert overlay == {}

    def test_extracts_object_from_prefixed_response(self) -> None:
        raw = 'Here is the overlay:\n{"c": {"requires": ["p"]}}\nDone.'
        overlay, outcome = _parse_overlay(raw)
        assert outcome is LinkerOutcome.OK
        assert overlay["c"].requires == ["p"]

    def test_requires_entries_coerced_to_strings(self) -> None:
        raw = json.dumps({"c": {"requires": [123]}})
        overlay, _outcome = _parse_overlay(raw)
        assert overlay["c"].requires == ["123"]

    def test_non_dict_edge_values_skipped(self) -> None:
        raw = json.dumps({"good": {"requires": ["p"]}, "bad": "nope"})
        overlay, outcome = _parse_overlay(raw)
        assert outcome is LinkerOutcome.OK
        assert "bad" not in overlay
        assert overlay["good"].requires == ["p"]

    def test_missing_fields_default(self) -> None:
        raw = json.dumps({"c": {"requires": ["p"]}})
        overlay, _outcome = _parse_overlay(raw)
        assert overlay["c"].composed_under == ""

    def test_json_array_is_not_an_overlay(self) -> None:
        # The overlay is an object; a bare array is not a valid overlay.
        overlay, outcome = _parse_overlay("[1, 2, 3]")
        assert outcome is LinkerOutcome.UNREADABLE
        assert overlay == {}


class TestExtractJsonObject:
    def test_finds_object(self) -> None:
        assert _extract_json_object('x {"a": 1} y') == '{"a": 1}'

    def test_none_when_absent(self) -> None:
        assert _extract_json_object("no object here") is None


# ---------------------------------------------------------------------------
# apply_overlay — authoritative merge + normalisation
# ---------------------------------------------------------------------------


class TestApplyOverlay:
    def test_applies_edges_to_matching_candidates(self) -> None:
        cands = [_candidate("producer"), _candidate("consumer")]
        overlay = {"consumer": EdgeOverlay(requires=["producer"])}
        apply_overlay(cands, overlay)
        by = {c.name: c for c in cands}
        assert by["consumer"].requires == ["producer"]

    def test_omitted_candidate_is_set_edgeless(self) -> None:
        # A candidate the Linker omits is authoritatively cleared — a stray
        # upstream edge must not survive.
        cands = [
            _candidate("a", composed_under="ghost", requires=["b"]),
            _candidate("b"),
        ]
        apply_overlay(cands, {"b": EdgeOverlay(requires=["a"])})
        by = {c.name: c for c in cands}
        assert by["a"].composed_under == ""
        assert by["a"].requires == []
        assert by["b"].requires == ["a"]

    def test_two_producer_requires_both_survive(self) -> None:
        # The OrderTool shape: the answer feature consumes two producers.
        cands = [
            _candidate("interpret"),
            _candidate("context"),
            _candidate("answer"),
        ]
        overlay = {"answer": EdgeOverlay(requires=["interpret", "context"])}
        apply_overlay(cands, overlay)
        by = {c.name: c for c in cands}
        assert sorted(by["answer"].requires) == ["context", "interpret"]

    def test_dangling_requires_dropped_by_normalisation(self) -> None:
        cands = [_candidate("a")]
        apply_overlay(cands, {"a": EdgeOverlay(requires=["nonexistent"])})
        assert cands[0].requires == []

    def test_members_normalise_to_sub_feature(self) -> None:
        cands = [_candidate("coord"), _candidate("m1"), _candidate("m2")]
        overlay = {
            "m1": EdgeOverlay(composed_under="coord"),
            "m2": EdgeOverlay(composed_under="coord"),
        }
        apply_overlay(cands, overlay)
        by = {c.name: c for c in cands}
        assert by["m1"].scope == "sub_feature"
        assert by["m2"].scope == "sub_feature"

    def test_empty_overlay_leaves_all_edgeless(self) -> None:
        cands = [_candidate("a"), _candidate("b")]
        apply_overlay(cands, {})
        assert all(not c.composed_under and not c.requires for c in cands)


# ---------------------------------------------------------------------------
# _format_candidates_block
# ---------------------------------------------------------------------------


class TestFormatCandidatesBlock:
    def test_includes_purpose_names_descriptions(self) -> None:
        block = _format_candidates_block(
            [_candidate("feat_one", rough_description="does a thing")],
            "A helpful project.",
        )
        assert "A helpful project." in block
        assert "feat_one" in block
        assert "does a thing" in block

    def test_no_purpose_line_when_absent(self) -> None:
        block = _format_candidates_block([_candidate("x")], "")
        assert "Project purpose:" not in block

    def test_exposes_linked_vision_features(self) -> None:
        # D-CF7a: the shared-vision-feature fingerprint must be visible to the
        # Linker so it can group fragments; an empty list renders a placeholder.
        block = _format_candidates_block(
            [
                _candidate("feat_one", rough_description="does a thing"),
                Candidate(
                    name="feat_two",
                    linked_vision_features=["policy_answers", "source_links"],
                    scope="feature",
                    rough_description="answers questions",
                ),
            ],
            "A project.",
        )
        assert "vision: policy_answers, source_links" in block
        assert "vision: —" in block


# ---------------------------------------------------------------------------
# LinkerAgent.run
# ---------------------------------------------------------------------------


class TestLinkerAgentRun:
    def _input(self) -> LinkerInput:
        return LinkerInput(
            candidates=[_candidate("producer"), _candidate("consumer")],
            vision_purpose="A project.",
            llm_config=_LLM_CONFIG,
        )

    def test_ok_path_returns_overlay(self) -> None:
        raw = json.dumps({"consumer": {"requires": ["producer"]}})
        with patch(
            "spec4.agentifier.linker.complete_stream",
            return_value=_make_mock_response(raw),
        ):
            out = asyncio.run(LinkerAgent().run(self._input()))
        assert isinstance(out, LinkerOutput)
        assert out.outcome is LinkerOutcome.OK
        assert out.overlay["consumer"].requires == ["producer"]

    def test_reparse_once_on_unreadable_then_ok(self) -> None:
        good = json.dumps({"consumer": {"requires": ["producer"]}})
        responses = [_make_mock_response("garbage"), _make_mock_response(good)]
        with patch(
            "spec4.agentifier.linker.complete_stream",
            side_effect=responses,
        ) as mock_llm:
            out = asyncio.run(LinkerAgent().run(self._input()))
        assert mock_llm.call_count == 2
        assert out.outcome is LinkerOutcome.OK

    def test_unreadable_after_reparse_gives_up(self) -> None:
        responses = [_make_mock_response("garbage"), _make_mock_response("still bad")]
        with patch(
            "spec4.agentifier.linker.complete_stream",
            side_effect=responses,
        ) as mock_llm:
            out = asyncio.run(LinkerAgent().run(self._input()))
        assert mock_llm.call_count == 2
        assert out.outcome is LinkerOutcome.UNREADABLE
        assert out.overlay == {}

    def test_empty_overlay_is_not_retried(self) -> None:
        # A readable-but-empty overlay is a legitimate flat result — one draw.
        with patch(
            "spec4.agentifier.linker.complete_stream",
            return_value=_make_mock_response("{}"),
        ) as mock_llm:
            out = asyncio.run(LinkerAgent().run(self._input()))
        assert mock_llm.call_count == 1
        assert out.outcome is LinkerOutcome.EMPTY

    def test_request_uses_linker_agent_name_and_system_prompt(self) -> None:
        with patch(
            "spec4.agentifier.linker.complete_stream",
            return_value=_make_mock_response("{}"),
        ) as mock_llm:
            asyncio.run(LinkerAgent().run(self._input()))
        call_kwargs = mock_llm.call_args[1]
        assert call_kwargs["agent_name"] == "linker"
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert "Linker" in messages[0]["content"]
        assert "producer" in messages[1]["content"]