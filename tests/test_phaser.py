"""Tests for :mod:`spec4.agents.phaser`: its turns, its phase schema and markdown,
and the feature surface it is given.

Split out of ``tests/test_agents.py`` by source module, with every class unchanged
(Phase 8, D9: ``PHASE8_RECORD.md`` §25).
"""

from typing import Any
from unittest.mock import MagicMock, patch
from spec4.agents import phaser
from spec4.agents._feature_context import ai_features_for_phaser
from spec4.app_constants import STATE_PHASES_COMPLETE
from tests._chunks import make_stream_chunk
from tests._agent_helpers import (
    _chunkify_stream,
    _phaser_revision_vision,
    collect,
    make_session,
    mock_litellm_stream,
)


# ---------------------------------------------------------------------------
# Phaser tests
# ---------------------------------------------------------------------------


class TestPhaser:
    def test_extract_phases_finds_phase_objects(self) -> None:
        from spec4.agents.phaser import _extract_phases

        text = '```json\n{"phase_number": 1, "phase_title": "Steel Thread"}\n```'
        phases = _extract_phases(text)
        assert len(phases) == 1 and phases[0]["phase_number"] == 1

    def test_extract_phases_ignores_non_phase_json(self) -> None:
        from spec4.agents.phaser import _extract_phases

        assert _extract_phases('```json\n{"name": "App"}\n```') == []

    def test_extract_phases_ignores_invalid_json(self) -> None:
        from spec4.agents.phaser import _extract_phases

        assert _extract_phases("```json\n{bad json}\n```") == []

    def test_extract_phases_finds_multiple_phases(self) -> None:
        from spec4.agents.phaser import _extract_phases

        text = (
            '```json\n{"phase_number": 1, "phase_title": "A"}\n```\n'
            '```json\n{"phase_number": 2, "phase_title": "B"}\n```'
        )
        assert len(_extract_phases(text)) == 2

    def test_extract_phases_tolerates_literal_newlines_in_strings(self) -> None:
        from spec4.agents.phaser import _extract_phases

        # Use actual newlines inside the JSON string values — the pathology
        # that strict json.loads rejects with "Invalid control character".
        block = (
            "```json\n"
            + """{
  "phase_number": 1,
  "phase_title": "Steel Thread",
  "verification": "1. Run pytest
2. Check coverage
3. Confirm CI green",
  "risk_assessment": {"potential_bottlenecks": "1. Missing env vars
2. Port conflicts", "mitigation_strategy": "Validate at startup."}
}"""
            + "\n```"
        )
        phases = _extract_phases(block)
        assert len(phases) == 1
        assert "\n" in phases[0]["verification"]

    def test_extract_phases_tolerates_trailing_extra_brace(self) -> None:
        from spec4.agents.phaser import _extract_phases

        # The real pathology: model appends an extra } after the object,
        # which causes strict json.loads to raise "Extra data".
        block = '```json\n{"phase_number": 2, "phase_title": "Integration"}\n}\n```'
        phases = _extract_phases(block)
        assert len(phases) == 1

    def test_extract_phases_recovers_real_world_multiblock(self) -> None:
        from spec4.agents.phaser import _extract_phases

        # Two blocks each with both pathologies: literal newlines AND trailing }.
        block1 = (
            "```json\n"
            + """{
  "phase_number": 1,
  "phase_title": "Phase One",
  "verification": "1. Run tests
2. Check logs"
}
}"""
            + "\n```"
        )
        block2 = (
            "```json\n"
            + """{
  "phase_number": 2,
  "phase_title": "Phase Two",
  "verification": "1. Deploy
2. Smoke test"
}
}"""
            + "\n```"
        )
        phases = _extract_phases(block1 + "\n\n" + block2)
        assert len(phases) == 2
        assert phases[0]["phase_number"] == 1
        assert phases[1]["phase_number"] == 2

    def test_extract_phases_tolerates_nested_code_fence(self) -> None:
        from spec4.agents.phaser import _extract_phases

        # A phase whose instructions contain a fenced ```bash block inside
        # a string value. A ```json-fence regex would prematurely terminate.
        block = (
            "```json\n"
            '{"phase_number": 1, "phase_title": "Setup", '
            '"instructions": "Run:\\n```bash\\nuv sync\\n```\\nThen start."}\n'
            "```"
        )
        phases = _extract_phases(block)
        assert len(phases) == 1

    def test_extract_phases_unwraps_phases_object(self) -> None:
        from spec4.agents.phaser import _extract_phases

        # The reported pathology: the model wraps its phase blocks in an outer
        # object instead of emitting one block per phase. A top-level-only check
        # parses this to zero phases and dead-ends the "try again" loop.
        text = (
            '```json\n{"phases": ['
            '{"phase_number": 1, "phase_title": "A"}, '
            '{"phase_number": 2, "phase_title": "B"}'
            "]}\n```"
        )
        phases = _extract_phases(text)
        assert [p["phase_number"] for p in phases] == [1, 2]

    def test_extract_phases_unwraps_nested_wrapper(self) -> None:
        from spec4.agents.phaser import _extract_phases

        text = (
            '```json\n{"plan": {"phases": ['
            '{"phase_number": 1, "phase_title": "A"}, '
            '{"phase_number": 2, "phase_title": "B"}, '
            '{"phase_number": 3, "phase_title": "C"}'
            "]}}\n```"
        )
        phases = _extract_phases(text)
        assert [p["phase_number"] for p in phases] == [1, 2, 3]

    def test_run_surfaces_fallback_on_unparseable_generation(self) -> None:
        from spec4.agents import phaser
        from spec4.app_constants import STATE_PHASES_COMPLETE

        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        # JSON-ish text with phase_number markers but truncated/garbage object
        # that the tolerant extractor still cannot parse into a valid phase.
        garbage = '```json\n{"phase_number": 1, "phase_title": "Broken",\n'

        with mock_litellm_stream(garbage):
            collect(phaser.run("Go", session, session["llm_config"]))

        assert session.get("phaser_state") != STATE_PHASES_COMPLETE
        assert not session.get("phases")
        assert session.get("_display_override") is not None
        assert "try again" in session["_display_override"].lower()

    def test_run_conversational_turn_leaves_display_override_unset(self) -> None:
        from spec4.agents import phaser

        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        # Pure conversational response — no JSON markers at all.
        with mock_litellm_stream("Sounds good, I'll wait for your approval."):
            collect(phaser.run("Tell me more.", session, session["llm_config"]))

        assert session.get("_display_override") is None

    def test_opening_seeds_vision_and_stack(self) -> None:
        vision = {"name": "App", "vision": "desc"}
        stack = {"stack_spec": {"languages": ["Python"]}}
        session = make_session(vision_statement=vision, stack_statement=stack)
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [
                    make_stream_chunk("Phases"),
                    make_stream_chunk("", finish_reason="stop"),
                ]
            )
            collect(phaser.run(None, session, session["llm_config"]))
        sent = mock_llm.call_args[1]["messages"]
        user_content = " ".join(m["content"] for m in sent if m["role"] == "user")
        assert "App" in user_content and "Python" in user_content

    def test_phases_json_sets_state_complete(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        phase_response = (
            '```json\n{"phase_number": 1, "phase_title": "Steel Thread", '
            '"total_phases": 1, "phase_summary": "Boot the stack.", '
            '"features": [], "capabilities": [], '
            '"tech_stack_spec": '
            '{"dependencies": ["fastapi"], "configurations": "PORT=8000"}, '
            '"instructions": ["Create main.py with GET /health."], '
            '"risk_assessment": '
            '{"potential_bottlenecks": "Missing env vars.", '
            '"mitigation_strategy": "Validate at startup."}, '
            '"verification": "Run pytest.", "references": []}\n```'
        )
        with mock_litellm_stream(phase_response):
            collect(phaser.run("Approve", session, session["llm_config"]))
        assert session["phaser_state"] == STATE_PHASES_COMPLETE
        assert len(session["phases"]) == 1
        # The artifact stamp the other agents write on their completing turn,
        # read by the cost card: the phases are the last message.
        assert session["phaser_artifact_msg_count"] == len(session["phaser_messages"])

    def test_non_phase_response_stays_incomplete(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        with mock_litellm_stream("Here is a text description."):
            collect(phaser.run("Go ahead", session, session["llm_config"]))
        assert session["phaser_state"] is None
        assert session["phases"] == []

    def test_reentry_replays_last_assistant_message(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "Phaser response"},
            ]
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(phaser.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "Phaser response" in output

    def test_reentry_drops_orphan_user_and_reseeds(self) -> None:
        # Orphan user from a failed previous init must be dropped so Phaser
        # can re-seed and call the LLM again rather than stalling.
        session = make_session(phaser_messages=[{"role": "user", "content": "hi"}])
        with mock_litellm_stream("Phaser back online."):
            output = collect(phaser.run(None, session, session["llm_config"]))
        assert "Phaser" in output
        roles = [m["role"] for m in session["phaser_messages"]]
        assert roles == ["user", "assistant"]

    def test_user_input_appended_to_messages(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "Draft phases"},
            ]
        )
        with mock_litellm_stream("Updated"):
            collect(phaser.run("Looks good", session, session["llm_config"]))
        assert session["phaser_messages"][-2] == {
            "role": "user",
            "content": "Looks good",
        }

    def test_initialises_phaser_messages_if_missing(self) -> None:
        session = make_session(vision_statement={"name": "App"}, stack_statement=None)
        del session["phaser_messages"]
        with mock_litellm_stream("Ok"):
            collect(phaser.run(None, session, session["llm_config"]))
        assert "phaser_messages" in session

    def test_user_approval_after_failed_outline_reseeds_vision_and_stack(
        self,
    ) -> None:
        # User's reported scenario: Phaser presents an outline, user types
        # "approved", but Phaser responds with the "I'm ready to help — please
        # share your project info" greeting instead of emitting phase JSON.
        # Root cause: turn 1's stream raised after the seed was appended but
        # before the assistant reply could be committed; phaser_messages =
        # [seed_orphan]. On turn 2 the orphan was dropped, leaving the LLM
        # with just ["approved"] and no vision/stack context. Recovery must
        # re-seed so the LLM has the full context again.
        vision = {"name": "KingMe", "vision": "checkers game"}
        stack = {"stack_spec": {"languages": ["Python"]}}
        session = make_session(
            vision_statement=vision,
            stack_statement=stack,
            phaser_messages=[
                {"role": "user", "content": "<seed content from failed turn 1>"},
            ],
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [
                    make_stream_chunk("Here is the outline..."),
                    make_stream_chunk("", finish_reason="stop"),
                ]
            )
            collect(phaser.run("approved", session, session["llm_config"]))

        sent = mock_llm.call_args[1]["messages"]
        user_content = " ".join(
            m["content"]
            for m in sent
            if m["role"] == "user" and isinstance(m["content"], str)
        )
        # The re-seeded user message must include vision/stack so the LLM
        # produces a phase outline rather than the "I'm ready to help"
        # contextless greeting.
        assert "KingMe" in user_content
        assert "Python" in user_content
        # The user's "approved" reply is discarded — it was a response to UI
        # text the agent never actually committed to phaser_messages. Assert on
        # message identity, not substring: the re-seeded context legitimately
        # contains the word (e.g. the stack digest's "approved-components
        # list"), but no user message may BE the stray reply.
        assert all(m["content"] != "approved" for m in sent if m["role"] == "user")


# ---------------------------------------------------------------------------
# _load_phaser_design_note (phaser)
# ---------------------------------------------------------------------------


class TestLoadPhaserDesignNote:
    def test_returns_mock_reference_when_mock_exists(self, tmp_path: Any) -> None:
        from spec4.agents.phaser import _load_phaser_design_note

        (tmp_path / "mock.html").write_text("<!DOCTYPE html><html></html>")
        result = _load_phaser_design_note(tmp_path, 0)
        assert "mock.html" in result

    def test_mock_reference_under_500_chars(self, tmp_path: Any) -> None:
        from spec4.agents.phaser import _load_phaser_design_note

        (tmp_path / "mock.html").write_text("<html/>")
        assert len(_load_phaser_design_note(tmp_path, 0)) < 500

    def test_returns_no_mock_note_when_absent(self, tmp_path: Any) -> None:
        from spec4.agents.phaser import _load_phaser_design_note

        result = _load_phaser_design_note(tmp_path, 0)
        assert "no ui design mock" in result.lower()

    def test_returns_no_mock_note_when_file_empty(self, tmp_path: Any) -> None:
        from spec4.agents.phaser import _load_phaser_design_note

        (tmp_path / "mock.html").write_text("  \n  ")
        result = _load_phaser_design_note(tmp_path, 0)
        assert "no ui design mock" in result.lower()


# ---------------------------------------------------------------------------
# Phase schema validation
# ---------------------------------------------------------------------------


def _valid_phase(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "phase_number": 1,
        "total_phases": 1,
        "phase_title": "Steel Thread",
        "phase_summary": "Boot the stack end-to-end.",
        # A scaffolding steel thread declares nothing; both arrays are required
        # but legitimately empty (D-PH2). Coverage checks no-op without a
        # catalog or a spine.
        "features": [],
        "capabilities": [],
        "tech_stack_spec": {
            "dependencies": ["fastapi"],
            "configurations": "PORT=8000",
        },
        "instructions": ["Create main.py with GET /health."],
        "risk_assessment": {
            "potential_bottlenecks": "Missing env vars.",
            "mitigation_strategy": "Validate at startup.",
        },
        "verification": "Run pytest.",
        "references": [],
    }
    base.update(overrides)
    return base


def _phase_block(phase: dict[str, Any]) -> str:
    import json as _json

    return "```json\n" + _json.dumps(phase) + "\n```"


class TestPhaseSchema:
    def test_accepts_valid_phase(self) -> None:
        from spec4.agents._phase_schema import validate_phase

        assert validate_phase(_valid_phase()) == []

    def test_rejects_missing_required(self) -> None:
        from spec4.agents._phase_schema import validate_phase

        phase = _valid_phase()
        del phase["phase_summary"]
        errors = validate_phase(phase)
        assert any("phase_summary" in e for e in errors)

    def test_rejects_empty_instructions(self) -> None:
        from spec4.agents._phase_schema import validate_phase

        errors = validate_phase(_valid_phase(instructions=[]))
        assert any("instructions" in e for e in errors)

    def test_rejects_reference_missing_url(self) -> None:
        from spec4.agents._phase_schema import validate_phase

        errors = validate_phase(_valid_phase(references=[{"standard": "FastAPI"}]))
        assert any("url" in e for e in errors)

    def test_rejects_custom_top_level_key(self) -> None:
        from spec4.agents._phase_schema import validate_phase

        errors = validate_phase(_valid_phase(vision_statement="v"))
        assert any("vision_statement" in e for e in errors)


# ---------------------------------------------------------------------------
# Phaser validation + retry flow
# ---------------------------------------------------------------------------


class TestPhaserValidationRetry:
    def _invalid_phase_text(self) -> str:
        # Missing required phase_summary AND empty instructions.
        return _phase_block(
            {
                "phase_number": 1,
                "total_phases": 1,
                "phase_title": "Bad",
                "tech_stack_spec": {"dependencies": [], "configurations": ""},
                "instructions": [],
                "risk_assessment": {
                    "potential_bottlenecks": "x",
                    "mitigation_strategy": "y",
                },
                "verification": "v",
            }
        )

    def test_valid_phase_does_not_retry(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        text = _phase_block(_valid_phase())
        # Patch run_seam_check so its advisory extraction call doesn't inflate
        # the litellm.completion call_count (it is a separate code path tested
        # in tests/test_seam_check.py).
        with (
            mock_litellm_stream(text) as mock_llm,
            patch("spec4.agents.phaser.run_seam_check", return_value=""),
        ):
            collect(phaser.run("Approve", session, session["llm_config"]))
        assert mock_llm.call_count == 1
        assert session["phaser_state"] == STATE_PHASES_COMPLETE
        assert len(session["phases"]) == 1

    def test_invalid_phase_triggers_retry(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        chunk_seqs = [
            list(_chunkify_stream(self._invalid_phase_text())),
            list(_chunkify_stream(_phase_block(_valid_phase()))),
        ]

        def fake_completion(**kwargs: Any) -> Any:
            return iter(chunk_seqs.pop(0))

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            collect(phaser.run("Approve", session, session["llm_config"]))

        retry_msgs = [
            m
            for m in session["phaser_messages"]
            if m["role"] == "user" and "failed schema validation" in m["content"]
        ]
        assert len(retry_msgs) == 1
        assert session["phaser_state"] == STATE_PHASES_COMPLETE

    def test_retry_failure_drops_exchange_and_emits_fallback(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        chunk_seqs = [
            list(_chunkify_stream(self._invalid_phase_text())),
            list(_chunkify_stream(self._invalid_phase_text())),
        ]

        def fake_completion(**kwargs: Any) -> Any:
            return iter(chunk_seqs.pop(0))

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            collect(phaser.run("Approve", session, session["llm_config"]))

        assert session["phaser_state"] != STATE_PHASES_COMPLETE
        retry_user = [
            m
            for m in session["phaser_messages"]
            if m["role"] == "user" and "failed schema validation" in m["content"]
        ]
        assert retry_user == []
        last = session["phaser_messages"][-1]
        assert last["role"] == "assistant"
        assert "validation" in last["content"].lower()

    def test_retry_uses_response_format_when_supported(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        chunk_seqs = [
            list(_chunkify_stream(self._invalid_phase_text())),
            list(_chunkify_stream(_phase_block(_valid_phase()))),
        ]
        call_kwargs: list[dict[str, Any]] = []

        def fake_completion(**kwargs: Any) -> Any:
            call_kwargs.append(kwargs)
            return iter(chunk_seqs.pop(0))

        with (
            patch("spec4.llm.litellm.completion", side_effect=fake_completion),
            patch(
                "spec4.llm.litellm.get_supported_openai_params",
                return_value=["temperature", "response_format"],
            ),
        ):
            collect(phaser.run("Approve", session, session["llm_config"]))

        assert "response_format" not in call_kwargs[0]
        assert call_kwargs[1]["response_format"] == {"type": "json_object"}

    def test_display_override_is_rendered_markdown(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        text = _phase_block(_valid_phase())
        with mock_litellm_stream(text):
            collect(phaser.run("Approve", session, session["llm_config"]))
        display = session.get("_display_override") or ""
        # The display should be human-prose Markdown with frontmatter, not
        # raw streamed JSON.
        assert "# Phase 1 of 1: Steel Thread" in display
        assert "## Instructions" in display
        assert "## Verification" in display


# ---------------------------------------------------------------------------
# Stack-addition capture across an in-turn web search (multi-message turn)
# ---------------------------------------------------------------------------


class TestPhaserStackAdditionCaptureAcrossTurn:
    """A stack_addition block emitted before an in-turn web search must still be
    captured. stream_turn strands the block in the pre-search assistant message
    (the one carrying tool_calls) and appends a clean post-search message after
    the tool result; scanning only the last message misses it, so the capture
    scans every assistant message appended this turn.
    """

    def _session(self) -> dict[str, Any]:
        return make_session(
            tavily_api_key="tv-key",
            stack_statement={
                "stack_spec": {"libraries": {"backend": [{"name": "Pytesseract"}]}}
            },
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ],
        )

    def _addition_block(self) -> str:
        import json as _json

        return _json.dumps(
            {
                "stack_addition": {
                    "name": "Tesseract OCR",
                    "tier": "backend",
                    "category": "system_binary",
                    "purpose": "OCR engine invoked by Pytesseract",
                }
            }
        )

    def _search_tool_chunk(self) -> MagicMock:
        import json as _json

        tc = MagicMock()
        tc.index = 0
        tc.id = "call-1"
        tc.function.name = "web_search"
        tc.function.arguments = _json.dumps({"query": "tesseract docs"})
        chunk = MagicMock()
        chunk.choices[0].delta.content = None
        chunk.choices[0].delta.tool_calls = [tc]
        chunk.choices[0].finish_reason = None
        return chunk

    def test_block_before_search_is_captured_stripped_and_concatenated(self) -> None:
        session = self._session()
        pre_search = (
            "These companions are obligatory but not themselves listed in the "
            "stack:\n\n" + self._addition_block() + "\n\nNow let me search for "
            "the canonical documentation."
        )
        post_search = "Confirmed — I have recorded the Tesseract binary."

        call_count = 0

        def fake_completion(**kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Pre-search round: block-bearing text, then a tool call.
                return iter(
                    list(_chunkify_stream(pre_search))[:-1]
                    + [
                        self._search_tool_chunk(),
                        make_stream_chunk("", finish_reason="stop"),
                    ]
                )
            # Post-search round: clean acknowledgment prose, no block.
            return iter(_chunkify_stream(post_search))

        with (
            patch("spec4.llm.litellm.completion", side_effect=fake_completion),
            patch("spec4.llm.search", return_value="results"),
        ):
            collect(phaser.run("Approve", session, session["llm_config"]))

        # 1. The addition reaches the stack — the defect this fix closes: in a
        #    search turn the block was previously never merged.
        backend = session["stack_statement"]["stack_spec"]["libraries"]["backend"]
        names = [lib["name"] for lib in backend]
        assert "Tesseract OCR" in names
        assert "Pytesseract" in names

        # 2. The raw block is stripped from the pre-search message in history,
        #    while its disclosure prose survives.
        assistant_texts = [
            m["content"]
            for m in session["phaser_messages"]
            if m.get("role") == "assistant" and m.get("content")
        ]
        joined = "\n".join(assistant_texts)
        assert "stack_addition" not in joined
        assert "obligatory" in joined

        # 3. The display override is the cleaned concatenation across the turn:
        #    pre-search disclosure prose AND post-search acknowledgment, block-free.
        override = session["_display_override"]
        assert "obligatory" in override
        assert "recorded the Tesseract binary" in override
        assert "stack_addition" not in override

    def test_block_without_search_still_captured_as_before(self) -> None:
        session = self._session()
        text = "Recording the companion:\n\n" + self._addition_block() + "\n\nDone."
        with mock_litellm_stream(text):
            collect(phaser.run("Approve", session, session["llm_config"]))

        backend = session["stack_statement"]["stack_spec"]["libraries"]["backend"]
        assert "Tesseract OCR" in [lib["name"] for lib in backend]
        override = session["_display_override"]
        assert "stack_addition" not in override
        assert "Recording the companion" in override
        assert "Done." in override


# ---------------------------------------------------------------------------
# Fresh-generation phase completeness (silent-drop guard)
# ---------------------------------------------------------------------------


class TestPhaseCompleteness:
    """Extracted phases must equal {1..total_phases} on a fresh generation.

    Guards the silent-drop path where _extract_phases skips a malformed block,
    leaving fewer phases than declared without tripping either retry gate.
    """

    @staticmethod
    def _phase(n: int, total: int, **ov: Any) -> dict[str, Any]:
        return _valid_phase(phase_number=n, total_phases=total, **ov)

    # --- pure helper ---

    def test_complete_set_passes(self) -> None:
        from spec4.agents.phaser import _phase_completeness_failure

        phases = [self._phase(1, 3), self._phase(2, 3), self._phase(3, 3)]
        assert _phase_completeness_failure(phases) is None

    def test_missing_phase_flagged(self) -> None:
        from spec4.agents.phaser import _phase_completeness_failure

        failure = _phase_completeness_failure([self._phase(1, 3), self._phase(2, 3)])
        assert failure is not None
        number, errors = failure
        assert number is None
        assert "incomplete" in errors[0]
        assert "[3]" in errors[0]

    def test_duplicate_phase_flagged(self) -> None:
        from spec4.agents.phaser import _phase_completeness_failure

        phases = [
            self._phase(1, 3),
            self._phase(2, 3),
            self._phase(3, 3),
            self._phase(3, 3),
        ]
        failure = _phase_completeness_failure(phases)
        assert failure is not None
        assert "duplicated" in failure[1][0]

    def test_disagreeing_total_phases_flagged(self) -> None:
        from spec4.agents.phaser import _phase_completeness_failure

        failure = _phase_completeness_failure([self._phase(1, 3), self._phase(2, 2)])
        assert failure is not None
        assert "disagree on total_phases" in failure[1][0]

    def test_empty_and_untyped_return_none(self) -> None:
        from spec4.agents.phaser import _phase_completeness_failure

        assert _phase_completeness_failure([]) is None
        assert _phase_completeness_failure([{"phase_number": 1}]) is None

    def test_single_phase_complete_passes(self) -> None:
        from spec4.agents.phaser import _phase_completeness_failure

        assert _phase_completeness_failure([self._phase(1, 1)]) is None

    # --- integration: gated retry routing ---

    def test_fresh_incomplete_set_triggers_retry_then_completes(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        incomplete = _phase_block(self._phase(1, 3)) + _phase_block(self._phase(2, 3))
        complete = (
            _phase_block(self._phase(1, 3, phase_title="Steel Thread"))
            + _phase_block(self._phase(2, 3, phase_title="Auth"))
            + _phase_block(self._phase(3, 3, phase_title="Inventory"))
        )
        chunk_seqs = [
            list(_chunkify_stream(incomplete)),
            list(_chunkify_stream(complete)),
        ]

        def fake_completion(**kwargs: Any) -> Any:
            return iter(chunk_seqs.pop(0))

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            collect(phaser.run("Approve", session, session["llm_config"]))

        retry_msgs = [
            m
            for m in session["phaser_messages"]
            if m["role"] == "user" and "incomplete" in m["content"]
        ]
        assert len(retry_msgs) == 1
        assert session["phaser_state"] == STATE_PHASES_COMPLETE
        assert len(session["phases"]) == 3

    def test_completeness_applies_with_prior_phases(self) -> None:
        # The completeness check is no longer gated on a fresh generation —
        # every version is a self-contained 1..k set, so an incomplete emission
        # triggers a retry even when prior phases are present in the session.
        session = make_session(
            phases=[self._phase(1, 2), self._phase(2, 2)],
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ],
        )
        incomplete = _phase_block(self._phase(2, 2, phase_title="Only second"))
        complete = _phase_block(self._phase(1, 2, phase_title="First")) + _phase_block(
            self._phase(2, 2, phase_title="Second")
        )
        chunk_seqs = [
            list(_chunkify_stream(incomplete)),
            list(_chunkify_stream(complete)),
        ]

        def fake_completion(**kwargs: Any) -> Any:
            return iter(chunk_seqs.pop(0))

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            collect(phaser.run("Approve", session, session["llm_config"]))

        retry_msgs = [
            m
            for m in session["phaser_messages"]
            if m["role"] == "user" and "incomplete" in m["content"]
        ]
        assert len(retry_msgs) == 1
        assert session["phaser_state"] == STATE_PHASES_COMPLETE
        assert len(session["phases"]) == 2


# ---------------------------------------------------------------------------
# IMPLEMENTED set-completion marker injection
# ---------------------------------------------------------------------------


class TestPhaserImplementedMarker:
    @staticmethod
    def _phase(n: int, total: int, **ov: Any) -> dict[str, Any]:
        return _valid_phase(phase_number=n, total_phases=total, **ov)

    def test_marker_appended_to_last_phase_only(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        text = _phase_block(self._phase(1, 2)) + _phase_block(self._phase(2, 2))
        with (
            mock_litellm_stream(text),
            patch("spec4.agents.phaser.run_seam_check", return_value=""),
        ):
            collect(phaser.run("Approve", session, session["llm_config"]))

        # No working_dir + no code review => greenfield v0.
        assert session["phase_version"] == 0
        phases = session["phases"]
        last = max(phases, key=lambda p: p["phase_number"])
        first = min(phases, key=lambda p: p["phase_number"])
        marker = ".spec4/v0/IMPLEMENTED"
        assert any(marker in s for s in last["instructions"])
        assert not any(marker in s for s in first["instructions"])

    def test_marker_not_duplicated_when_already_present(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        marker = ".spec4/v0/IMPLEMENTED"
        p2 = self._phase(2, 2, instructions=["Do the thing.", f"touch {marker}"])
        text = _phase_block(self._phase(1, 2)) + _phase_block(p2)
        with (
            mock_litellm_stream(text),
            patch("spec4.agents.phaser.run_seam_check", return_value=""),
        ):
            collect(phaser.run("Approve", session, session["llm_config"]))

        last = max(session["phases"], key=lambda p: p["phase_number"])
        assert sum(1 for s in last["instructions"] if marker in s) == 1


# ---------------------------------------------------------------------------
# Phaser revision mode
# ---------------------------------------------------------------------------


class TestPhaserRevisionMode:
    """Revision mode: when a prior round is implemented and the vision carries a
    delta, Phaser scopes the plan to the delta and renumbers 1..k (Route A). The
    reader/note helpers are deterministic (no LLM). Phaser carries no prior
    artifact forward — the gate is a plain implemented-predecessor probe."""

    # ----- revision_delta -----

    def test_delta_none_for_greenfield_vision(self) -> None:
        assert phaser.revision_delta({"vision_statement": {"name": "Fresh"}}) is None

    def test_delta_none_for_empty_or_missing(self) -> None:
        assert phaser.revision_delta(None) is None
        assert phaser.revision_delta({}) is None
        assert (
            phaser.revision_delta({"vision_statement": {"revision_history": []}})
            is None
        )
        # Non-enveloped (inner-form) vision is not revision mode.
        assert phaser.revision_delta({"name": "App"}) is None

    def test_delta_returns_last_history_entry(self) -> None:
        vision = {
            "vision_statement": {
                "revision_history": [
                    {"version": 0, "goal": "first"},
                    {
                        "version": 1,
                        "goal": "Add returns",
                        "changes": {"added": ["Returns"]},
                    },
                ]
            }
        }
        delta = phaser.revision_delta(vision)
        assert delta is not None
        assert delta["goal"] == "Add returns"
        assert delta["changes"]["added"] == ["Returns"]

    def test_delta_non_dict_last_entry_is_none(self) -> None:
        vision = {"vision_statement": {"revision_history": ["not a dict"]}}
        assert phaser.revision_delta(vision) is None

    # ----- build_revision_note -----

    def test_note_includes_all_change_buckets_and_goal(self) -> None:
        delta = {
            "goal": "Add billing",
            "changes": {
                "added": ["Subscriptions"],
                "modified": ["Checkout"],
                "removed": ["Free Tier"],
            },
        }
        note = phaser.build_revision_note(delta)
        assert note.startswith("[") and note.endswith("]")
        assert "Add billing" in note
        assert "Subscriptions" in note
        assert "Checkout" in note
        assert "Free Tier" in note
        # Scoping intent is explicit.
        assert "already built and in place" in note
        assert "1..k" in note

    def test_note_omits_goal_when_blank(self) -> None:
        note = phaser.build_revision_note(
            {"goal": "", "changes": {"added": ["X"], "modified": [], "removed": []}}
        )
        assert "Goal:" not in note
        assert "added features (X)" in note

    def test_note_empty_changes_still_preserves(self) -> None:
        # Degenerate delta (no feature changes) → still a valid scoping note.
        note = phaser.build_revision_note({"changes": {}})
        assert "already built and in place" in note
        assert "Plan phases only for this revision's" not in note

    def test_note_missing_changes_key(self) -> None:
        note = phaser.build_revision_note({"goal": "g"})
        assert "Goal: g" in note
        assert note.endswith("]")

    # ----- seed selection -----

    def _implement_prior_round(self, wd: str) -> None:
        from spec4 import project_manager

        project_manager.save_phases(
            wd, [{"phase_number": 1, "phase_title": "Steel"}], 0
        )
        project_manager.get_version_dir(wd, 0).joinpath("IMPLEMENTED").write_text("")

    def test_revision_seed_used_when_prior_round_and_delta_exist(
        self, tmp_path: Any
    ) -> None:
        wd = str(tmp_path)
        self._implement_prior_round(wd)
        session = make_session(
            active_agent="phaser",
            working_dir=wd,
            code_review={"code_review": {"project_type": "web"}},
            vision_statement=_phaser_revision_vision(
                added=["Subscriptions"], goal="Add billing"
            ),
            stack_statement={"name": "App"},
        )
        with mock_litellm_stream("Planning the delta phases."):
            collect(phaser.run(None, session, session["llm_config"]))
        seed = session["phaser_messages"][0]["content"]
        # Targets the new round (v1) and operates in revision mode.
        assert "planning round v1" in seed
        assert "Subscriptions" in seed  # delta scoping note
        assert "Add billing" in seed
        assert "already built and in place" in seed
        # Instruction is reframed away from the full-set brownfield/greenfield text.
        assert "ONLY this revision's new or changed surface" in seed
        assert "generate the full set of development phases" not in seed

    def test_prior_round_without_delta_is_not_revision(self, tmp_path: Any) -> None:
        # Implemented prior round exists, but the vision has no revision delta —
        # falls through to the brownfield code-review branch, not revision mode.
        wd = str(tmp_path)
        self._implement_prior_round(wd)
        session = make_session(
            active_agent="phaser",
            working_dir=wd,
            code_review={"code_review": {"project_type": "web"}},
            vision_statement={"name": "App", "vision": "v"},
            stack_statement={"name": "App"},
        )
        with mock_litellm_stream("Brownfield plan."):
            collect(phaser.run(None, session, session["llm_config"]))
        seed = session["phaser_messages"][0]["content"]
        assert "already built and in place" not in seed
        assert "integration/validation thread for the existing code" in seed

    def test_delta_without_implemented_round_is_not_revision(
        self, tmp_path: Any
    ) -> None:
        # Vision carries a revision delta but no prior round is IMPLEMENTED →
        # not revision mode (greenfield seed, full set).
        wd = str(tmp_path)
        session = make_session(
            active_agent="phaser",
            working_dir=wd,
            vision_statement=_phaser_revision_vision(
                added=["Subscriptions"], goal="Add billing"
            ),
            stack_statement={"name": "App"},
        )
        with mock_litellm_stream("Greenfield plan."):
            collect(phaser.run(None, session, session["llm_config"]))
        seed = session["phaser_messages"][0]["content"]
        assert "already built and in place" not in seed
        assert "generate the full set of development phases" in seed


class TestAiFeaturesForPhaserRevision:
    """_ai_features_for_phaser partitions by introduced_in_version in revision
    mode; with revision_version=None the output is unchanged (greenfield)."""

    def _features(self) -> dict[str, Any]:
        return {
            "ai_features": [
                {
                    "name": "search",
                    "tier": "rag",
                    "phase_priority": "mvp",
                    "purpose": "find",
                    "introduced_in_version": 0,
                },
                {
                    "name": "summarize",
                    "tier": "single_call",
                    "phase_priority": "mvp",
                    "purpose": "tldr",
                    "introduced_in_version": 1,
                },
            ]
        }

    def test_none_version_is_unchanged_greenfield_output(self) -> None:
        out = ai_features_for_phaser(self._features())
        assert "AI features spec (from Agentifier)" in out
        assert "search" in out and "summarize" in out
        assert "Already-implemented AI features" not in out

    def test_empty_features_returns_empty(self) -> None:
        assert ai_features_for_phaser({"ai_features": []}, revision_version=1) == ""

    def test_revision_partitions_by_introduced_in_version(self) -> None:
        out = ai_features_for_phaser(self._features(), revision_version=1)
        # New feature is in the to-phase table; old feature is established context.
        assert "New/changed AI features for this revision" in out
        assert "Already-implemented AI features" in out
        assert "do NOT create phases" in out
        # The established context line names the v0 feature, not the v1 one.
        established_line = next(
            ln for ln in out.splitlines() if "Already-implemented" in ln
        )
        assert "search" in established_line
        assert "summarize" not in established_line
        # The to-phase table names the v1 feature, not the v0 one.
        table_region = out.split("New/changed AI features for this revision")[1]
        assert "| summarize |" in table_region
        assert "| search |" not in table_region

    def test_revision_with_no_new_ai_features_is_context_only(self) -> None:
        # All features predate this round → established context, no to-phase table.
        feats = {
            "ai_features": [
                {"name": "search", "tier": "rag", "introduced_in_version": 0},
            ]
        }
        out = ai_features_for_phaser(feats, revision_version=1)
        assert "Already-implemented AI features" in out
        assert "New/changed AI features for this revision" not in out
        assert "| Feature | Tier |" not in out

    def test_missing_introduced_in_version_treated_as_established(self) -> None:
        # Defensive: a feature without the stamp is not re-phased.
        feats = {"ai_features": [{"name": "legacy", "tier": "rag"}]}
        out = ai_features_for_phaser(feats, revision_version=1)
        assert "Already-implemented AI features" in out
        assert "New/changed AI features for this revision" not in out


# ---------------------------------------------------------------------------
# Phase Markdown serialization round-trip
# ---------------------------------------------------------------------------


class TestPhaseMarkdownRoundTrip:
    def test_render_includes_all_sections(self) -> None:
        from spec4 import project_manager

        md = project_manager.render_phase_markdown(_valid_phase())
        assert md.startswith("---\n")
        assert "# Phase 1 of 1: Steel Thread" in md
        assert "Boot the stack end-to-end." in md
        assert "## Tech Stack" in md
        assert "- fastapi" in md
        assert "**Configurations:** PORT=8000" in md
        assert "## Instructions" in md
        assert "1. Create main.py with GET /health." in md
        assert "## Risk Assessment" in md
        assert "Missing env vars." in md
        assert "Validate at startup." in md
        assert "## Verification" in md
        assert "Run pytest." in md

    def test_renders_references_as_links(self) -> None:
        from spec4 import project_manager

        phase = _valid_phase(
            references=[{"standard": "FastAPI", "url": "https://fastapi.tiangolo.com"}]
        )
        md = project_manager.render_phase_markdown(phase)
        assert "## References" in md
        assert "[FastAPI](https://fastapi.tiangolo.com)" in md

    def test_round_trip_via_parse(self) -> None:
        from spec4 import project_manager

        phase = _valid_phase(
            references=[{"standard": "Pydantic", "url": "https://docs.pydantic.dev"}]
        )
        md = project_manager.render_phase_markdown(phase)
        parsed = project_manager.parse_phase_markdown(md)
        assert parsed == phase

    def test_parse_returns_none_without_frontmatter(self) -> None:
        from spec4 import project_manager

        assert project_manager.parse_phase_markdown("# Just a heading\n") is None

    def test_parse_returns_none_for_bad_frontmatter_json(self) -> None:
        from spec4 import project_manager

        assert (
            project_manager.parse_phase_markdown("---\n{not json}\n---\n\nbody\n")
            is None
        )


class TestAiFeaturesForPhaserFullSurface:
    """D-PS3(B): Phaser receives the entire Agentifier surface, not a summary.

    Phaser authors the per-phase `features[]` declaration and the `scope_note`
    that records partial coverage — it cannot curate what it was never shown.
    """

    def _catalog(self) -> dict[str, Any]:
        return {
            "ai_features": [
                {
                    "id": "vector_index",
                    "name": "vector_index",
                    "kind": "infrastructure",
                    "tier": "infrastructure",
                    "phase_priority": "steel_thread",
                    "requires": [],
                    "rough_description": "Enabling infrastructure (vector index).",
                },
                {
                    "id": "rag_answerer",
                    "name": "RAG Answerer",
                    "kind": "feature",
                    "tier": "rag",
                    "scope": "cross_feature",
                    "phase_priority": "mvp",
                    "requires": ["vector_index"],
                    "purpose": "Answer questions grounded in the indexed corpus.",
                    "invocation": {"trigger": "user asks", "mode": "synchronous"},
                    "inputs": [
                        {
                            "name": "question",
                            "type": "string",
                            "description": "the query",
                            "required": True,
                        }
                    ],
                    "outputs": {"primary": "answer", "format": "JSON"},
                    "success_criteria": ["cites a source"],
                    "failure_modes": [
                        {"mode": "no hits", "likelihood": "low", "mitigation": "caveat"}
                    ],
                    "tier_analysis": {
                        "rationale": "needs private corpus grounding",
                        "compared_to_next_tier_down": "single_call hallucinates",
                        "borderline": False,
                    },
                },
            ],
            "cross_cutting": {
                "provider_strategy": {"recommendation": "a strong general model"},
                "prompt_versioning": {"recommendation": "pin prompts per release"},
            },
            "explicitly_rejected": [{"name": "Voice mode"}],
        }

    def test_full_purpose_is_not_truncated(self) -> None:
        catalog = self._catalog()
        long_purpose = "P" * 200
        catalog["ai_features"][1]["purpose"] = long_purpose
        out = ai_features_for_phaser(catalog)
        assert long_purpose in out

    def test_spec_body_reaches_phaser(self) -> None:
        out = ai_features_for_phaser(self._catalog())
        assert "user asks" in out
        assert "`question`" in out
        assert "cites a source" in out
        assert "no hits" in out

    def test_tier_analysis_reaches_phaser(self) -> None:
        out = ai_features_for_phaser(self._catalog())
        assert "needs private corpus grounding" in out
        assert "single_call hallucinates" in out

    def test_ids_are_surfaced_as_the_join_key(self) -> None:
        out = ai_features_for_phaser(self._catalog())
        assert "`rag_answerer`" in out
        assert "exact key to use in each phase's `features` array" in out

    def test_infrastructure_guidance_is_present(self) -> None:
        out = ai_features_for_phaser(self._catalog())
        assert "infrastructure" in out
        assert "same phase as its first consumer or earlier" in out

    def test_cross_feature_guidance_is_present(self) -> None:
        out = ai_features_for_phaser(self._catalog())
        assert "shared surface" in out

    def test_cross_cutting_reaches_phaser_including_provider_strategy(self) -> None:
        # Phaser sees provider_strategy; the phase files deliberately do not.
        out = ai_features_for_phaser(self._catalog())
        assert "a strong general model" in out
        assert "pin prompts per release" in out

    def test_rejected_candidates_are_named(self) -> None:
        out = ai_features_for_phaser(self._catalog())
        assert "Voice mode" in out
        assert "do NOT plan phases for these" in out


class TestPhaserCoverageEnforcement:
    """Coverage + infra ordering failures fold into the existing retry loop."""

    @staticmethod
    def _catalog() -> dict[str, Any]:
        return {
            "ai_features": [
                {
                    "id": "vector_index",
                    "name": "vector_index",
                    "kind": "infrastructure",
                    "tier": "infrastructure",
                    "phase_priority": "steel_thread",
                    "requires": [],
                },
                {
                    "id": "rag_answerer",
                    "name": "RAG Answerer",
                    "kind": "feature",
                    "tier": "rag",
                    "phase_priority": "mvp",
                    "requires": ["vector_index"],
                    "purpose": "Answer questions.",
                },
            ]
        }

    @staticmethod
    def _decl(fid: str) -> dict[str, Any]:
        return {"id": fid, "role": "introduced", "scope_note": ""}

    @staticmethod
    def _two_turn_stream(first: str, second: str) -> Any:
        """Patch litellm so the first turn fails coverage and the retry passes."""
        chunk_seqs = [
            list(_chunkify_stream(first)),
            list(_chunkify_stream(second)),
        ]

        def fake_completion(**kwargs: Any) -> Any:
            return iter(chunk_seqs.pop(0))

        return patch("spec4.llm.litellm.completion", side_effect=fake_completion)

    def _covered(self) -> str:
        return _phase_block(
            _valid_phase(
                phase_number=1,
                total_phases=1,
                capabilities=[self._decl("vector_index"), self._decl("rag_answerer")],
            )
        )

    def test_complete_coverage_completes_the_set(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        session["ai_features"] = self._catalog()
        with (
            mock_litellm_stream(self._covered()),
            patch("spec4.agents.phaser.run_seam_check", return_value=""),
        ):
            collect(phaser.run("Approve", session, session["llm_config"]))
        assert session["phaser_state"] == STATE_PHASES_COMPLETE

    def test_missing_mvp_feature_triggers_retry_then_completes(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        session["ai_features"] = self._catalog()
        bad = _phase_block(
            _valid_phase(
                phase_number=1,
                total_phases=1,
                capabilities=[self._decl("vector_index")],
            )
        )
        with (
            self._two_turn_stream(bad, self._covered()),
            patch("spec4.agents.phaser.run_seam_check", return_value=""),
        ):
            collect(phaser.run("Approve", session, session["llm_config"]))
        assert session["phaser_state"] == STATE_PHASES_COMPLETE
        retry = [m for m in session["phaser_messages"] if m["role"] == "user"]
        assert any("RAG Answerer" in m["content"] for m in retry)

    def test_infra_after_consumer_triggers_retry(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        session["ai_features"] = self._catalog()
        bad = _phase_block(
            _valid_phase(
                phase_number=1,
                total_phases=2,
                capabilities=[self._decl("rag_answerer")],
            )
        ) + _phase_block(
            _valid_phase(
                phase_number=2,
                total_phases=2,
                capabilities=[self._decl("vector_index")],
            )
        )
        with (
            self._two_turn_stream(bad, self._covered()),
            patch("spec4.agents.phaser.run_seam_check", return_value=""),
        ):
            collect(phaser.run("Approve", session, session["llm_config"]))
        retry = [m for m in session["phaser_messages"] if m["role"] == "user"]
        assert any("not stood up until phase 2" in m["content"] for m in retry)

    def test_deferred_feature_is_surfaced_as_advisory(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        catalog = self._catalog()
        catalog["ai_features"].append(
            {
                "id": "summarizer",
                "name": "Summarizer",
                "kind": "feature",
                "tier": "single_call",
                "phase_priority": "v2",
                "requires": [],
            }
        )
        session["ai_features"] = catalog
        with (
            mock_litellm_stream(self._covered()),
            patch("spec4.agents.phaser.run_seam_check", return_value=""),
        ):
            collect(phaser.run("Approve", session, session["llm_config"]))
        assert session["phaser_state"] == STATE_PHASES_COMPLETE
        assert "Not built by these phases" in session["_display_override"]
        assert "Summarizer" in session["_display_override"]

    def test_no_catalog_leaves_coverage_inert(self) -> None:
        session = make_session(
            phaser_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        with (
            mock_litellm_stream(_phase_block(_valid_phase())),
            patch("spec4.agents.phaser.run_seam_check", return_value=""),
        ):
            collect(phaser.run("Approve", session, session["llm_config"]))
        assert session["phaser_state"] == STATE_PHASES_COMPLETE


class TestPhaserSpecReferenceDirective:
    """D-PS14(a): the prompt must not simultaneously demand self-containment.

    The `instructions` field description originally read "specific enough that an
    AI coder cannot misinterpret it" — sitting inside the JSON schema, adjacent to
    where the model emits `instructions`, and directly incentivising the model to
    restate the attached spec. The "do not restate" rule sat ~40 lines later, in
    prose. On a live draw the local schema text won: inputs were re-typed and the
    output schema drifted (a field renamed, another dropped).
    """

    def test_instructions_description_directs_reference_not_restatement(self) -> None:
        from spec4.agents.phaser import SYSTEM_PROMPT

        assert "REFERENCE them" in SYSTEM_PROMPT
        # The unconditional self-containment demand is gone...
        assert (
            "one concrete, actionable step — specific enough that an AI coder"
            not in SYSTEM_PROMPT
        )
        # ...but survives, correctly scoped, for content no spec covers.
        assert "NOT covered by an attached specification" in SYSTEM_PROMPT

    def test_prompt_shows_the_rendered_preamble(self) -> None:
        from spec4.agents.phaser import SYSTEM_PROMPT

        # Phaser never sees a phase file; it cannot reference an artifact it
        # cannot picture.
        assert "## Feature Specifications" in SYSTEM_PROMPT
        assert "What the coding agent actually receives" in SYSTEM_PROMPT

    def test_prompt_contrasts_a_restating_and_a_referencing_instruction(self) -> None:
        from spec4.agents.phaser import SYSTEM_PROMPT

        assert "This re-types the" in SYSTEM_PROMPT
        assert "do not add, drop, or rename fields" in SYSTEM_PROMPT

    def test_rule_five_carries_a_mechanical_self_test(self) -> None:
        from spec4.agents.phaser import SYSTEM_PROMPT

        assert "Self-test:" in SYSTEM_PROMPT
        assert "a faithful copy today is a divergence tomorrow" in SYSTEM_PROMPT
