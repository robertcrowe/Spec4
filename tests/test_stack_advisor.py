"""Tests for :mod:`spec4.agents.stack_advisor`, and the design manifest it reads.

Split out of ``tests/test_agents.py`` by source module, with every class unchanged
(Phase 8, D9: ``PHASE8_RECORD.md`` §25).
"""

from typing import Any
from unittest.mock import patch
from spec4.agents import stack_advisor
from spec4.app_constants import STATE_STACK_COMPLETE
from tests._chunks import make_stream_chunk
from tests._agent_helpers import (
    _reply_sequence,
    collect,
    make_session,
    mock_litellm_stream,
)


class TestStalenessQuestion:
    """When an upstream artifact is updated after a downstream agent has
    completed, re-entering that agent must surface a revision question rather
    than silently replaying the now-outdated prior response."""

    def _setup_stale(self, tmp_path: Any, output_name: str, input_name: str) -> None:
        """Create output_name with old mtime and input_name with newer mtime."""
        import os

        v0 = tmp_path / ".spec4" / "v0"
        v0.mkdir(parents=True, exist_ok=True)
        for name, mtime in [(output_name, 1_000.0), (input_name, 2_000.0)]:
            p = v0 / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("{}", encoding="utf-8")
            os.utime(p, (mtime, mtime))

    def test_stack_reentry_asks_revision_question_when_vision_newer(
        self, tmp_path: Any
    ) -> None:
        self._setup_stale(tmp_path, "stack.json", "vision.json")
        session = make_session(
            active_agent="stack_advisor",
            working_dir=str(tmp_path),
            vision_statement={"name": "App", "vision": "updated"},
            stack_statement={"name": "App", "languages": ["Python"]},
            stack_advisor_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "Final stack JSON…"},
            ],
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(stack_advisor.run(None, session, session["llm_config"]))
        # No LLM call — the question is statically yielded.
        mock_llm.assert_not_called()
        assert "updated" in output.lower() or "revise" in output.lower()
        # Session is marked acknowledged at the current vision mtime.
        ack = session["stack_advisor_stale_acknowledged"]
        assert ack.get("vision") == 2_000.0

    def test_replay_path_runs_when_no_staleness(self, tmp_path: Any) -> None:
        # Output is newer than input → not stale → replay branch fires.
        import os

        v0 = tmp_path / ".spec4" / "v0"
        v0.mkdir(parents=True, exist_ok=True)
        (v0 / "vision.json").write_text("{}")
        os.utime(v0 / "vision.json", (1_000.0, 1_000.0))
        (v0 / "stack.json").write_text("{}")
        os.utime(v0 / "stack.json", (2_000.0, 2_000.0))

        session = make_session(
            active_agent="stack_advisor",
            working_dir=str(tmp_path),
            vision_statement={"name": "App"},
            stack_statement={"name": "App"},
            stack_advisor_resumed=True,
            stack_advisor_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "Final stack JSON output."},
            ],
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(stack_advisor.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "Final stack JSON output." in output

    def test_acknowledged_at_same_mtime_does_not_reask(self, tmp_path: Any) -> None:
        self._setup_stale(tmp_path, "stack.json", "vision.json")
        session = make_session(
            active_agent="stack_advisor",
            working_dir=str(tmp_path),
            vision_statement={"name": "App"},
            stack_statement={"name": "App"},
            stack_advisor_resumed=True,
            stack_advisor_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "Last assistant message."},
            ],
            stack_advisor_stale_acknowledged={"vision": 2_000.0},
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(stack_advisor.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        # Replay branch fires — last assistant message comes back.
        assert "Last assistant message." in output

    def test_input_updated_again_triggers_reask(self, tmp_path: Any) -> None:
        # Acknowledged at 2_000.0, but vision has since been updated to 3_000.0.
        import os

        v0 = tmp_path / ".spec4" / "v0"
        v0.mkdir(parents=True, exist_ok=True)
        (v0 / "stack.json").write_text("{}")
        os.utime(v0 / "stack.json", (1_000.0, 1_000.0))
        (v0 / "vision.json").write_text("{}")
        os.utime(v0 / "vision.json", (3_000.0, 3_000.0))

        session = make_session(
            active_agent="stack_advisor",
            working_dir=str(tmp_path),
            vision_statement={"name": "App"},
            stack_statement={"name": "App"},
            stack_advisor_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "Old final stack."},
            ],
            stack_advisor_stale_acknowledged={"vision": 2_000.0},
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(stack_advisor.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        # Re-asks because the mtime moved.
        assert "revise" in output.lower() or "updated" in output.lower()
        assert session["stack_advisor_stale_acknowledged"]["vision"] == 3_000.0


# ---------------------------------------------------------------------------
# Stack Advisor tests
# ---------------------------------------------------------------------------


class TestStackAdvisor:
    def test_opening_calls_llm(self) -> None:
        vision = {"name": "TodoApp", "vision": "A simple task manager"}
        session = make_session(active_agent="stack_advisor", vision_statement=vision)
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [
                    make_stream_chunk("What language?"),
                    make_stream_chunk("", finish_reason="stop"),
                ]
            )
            collect(stack_advisor.run(None, session, session["llm_config"]))
        mock_llm.assert_called_once()

    def test_opening_includes_vision_in_messages(self) -> None:
        vision = {"name": "TodoApp", "vision": "A simple task manager"}
        session = make_session(active_agent="stack_advisor", vision_statement=vision)
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [make_stream_chunk("Ok"), make_stream_chunk("", finish_reason="stop")]
            )
            collect(stack_advisor.run(None, session, session["llm_config"]))
        call_kwargs = mock_llm.call_args[1]
        messages = call_kwargs["messages"]
        assert any("TodoApp" in m["content"] for m in messages)

    def test_opening_no_vision_still_calls_llm(self) -> None:
        session = make_session(active_agent="stack_advisor", vision_statement=None)
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [make_stream_chunk("Ok"), make_stream_chunk("", finish_reason="stop")]
            )
            collect(stack_advisor.run(None, session, session["llm_config"]))
        mock_llm.assert_called_once()

    def test_user_input_streams_llm_output(self) -> None:
        vision = {"name": "App", "vision": "desc"}
        session = make_session(active_agent="stack_advisor", vision_statement=vision)
        with mock_litellm_stream("Python is a great choice."):
            output = collect(
                stack_advisor.run(
                    "I want to use Python", session, session["llm_config"]
                )
            )
        assert "Python is a great choice." in output

    def test_conversation_history_accumulated(self) -> None:
        session = make_session(
            active_agent="stack_advisor",
            vision_statement={"name": "App", "vision": "v"},
        )
        with mock_litellm_stream("Great!"):
            collect(stack_advisor.run(None, session, session["llm_config"]))
        assert len(session["stack_advisor_messages"]) == 2
        assert session["stack_advisor_messages"][0]["role"] == "user"
        assert session["stack_advisor_messages"][1] == {
            "role": "assistant",
            "content": "Great!",
        }

    def test_stack_spec_json_sets_state_complete(self) -> None:
        session = make_session(
            active_agent="stack_advisor",
            vision_statement={"name": "App", "vision": "v"},
        )
        stack_response = (
            "Here is your stack spec!\n\n```json\n"
            '{"stack_spec": {"name": "App", "languages": ["Python"]}}\n'
            "```"
        )
        with mock_litellm_stream(stack_response):
            collect(
                stack_advisor.run("Yes, finalize it", session, session["llm_config"])
            )
        assert session["stack_advisor_state"] == STATE_STACK_COMPLETE
        assert session["stack_statement"]["stack_spec"]["name"] == "App"

    def test_re_entry_does_not_call_llm(self) -> None:
        session = make_session(
            active_agent="stack_advisor",
            vision_statement={"name": "App", "vision": "v"},
            stack_advisor_resumed=True,
        )
        session["stack_advisor_messages"] = [
            {"role": "user", "content": "seed"},
            {"role": "assistant", "content": "Which language do you prefer?"},
        ]
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(stack_advisor.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "Which language do you prefer?" in output

    def test_llm_called_with_system_prompt(self) -> None:
        session = make_session(
            active_agent="stack_advisor",
            vision_statement={"name": "App", "vision": "v"},
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [make_stream_chunk("Ok"), make_stream_chunk("", finish_reason="stop")]
            )
            collect(stack_advisor.run("Python", session, session["llm_config"]))
        call_kwargs = mock_llm.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"


# ---------------------------------------------------------------------------
# StackAdvisor revision mode
# ---------------------------------------------------------------------------


def _stack_revision_vision(
    added: list[str] | None = None,
    modified: list[str] | None = None,
    removed: list[str] | None = None,
    goal: str = "",
) -> dict[str, Any]:
    """Session-form vision envelope carrying a single revision_history entry."""
    entry = {
        "version": 1,
        "based_on_version": 0,
        "goal": goal,
        "changes": {
            "added": added or [],
            "modified": modified or [],
            "removed": removed or [],
        },
        "rationale": "",
    }
    return {"vision_statement": {"name": "App", "revision_history": [entry]}}


class TestStackAdvisorRevisionMode:
    """Revision mode: when a prior implemented stack exists and the vision carries
    a revision delta, StackAdvisor carries the established stack forward as the
    baseline and scopes recommendations to the delta rather than re-deciding the
    whole stack. The reader/note helpers are deterministic (no LLM)."""

    # ----- revision_delta -----

    def test_delta_none_for_greenfield_vision(self) -> None:
        assert (
            stack_advisor.revision_delta({"vision_statement": {"name": "Fresh"}})
            is None
        )

    def test_delta_none_for_empty_or_missing(self) -> None:
        assert stack_advisor.revision_delta(None) is None
        assert stack_advisor.revision_delta({}) is None
        assert (
            stack_advisor.revision_delta({"vision_statement": {"revision_history": []}})
            is None
        )
        # Non-enveloped (inner-form) vision is not revision mode.
        assert stack_advisor.revision_delta({"name": "App"}) is None

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
        delta = stack_advisor.revision_delta(vision)
        assert delta is not None
        assert delta["goal"] == "Add returns"
        assert delta["changes"]["added"] == ["Returns"]

    def test_delta_non_dict_last_entry_is_none(self) -> None:
        vision = {"vision_statement": {"revision_history": ["not a dict"]}}
        assert stack_advisor.revision_delta(vision) is None

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
        note = stack_advisor.build_revision_note(delta)
        assert note.startswith("[") and note.endswith("]")
        assert "Add billing" in note
        assert "Subscriptions" in note
        assert "Checkout" in note
        assert "Free Tier" in note
        # Scoping intent is explicit.
        assert "Preserve the established stack" in note

    def test_note_omits_goal_when_blank(self) -> None:
        note = stack_advisor.build_revision_note(
            {"goal": "", "changes": {"added": ["X"], "modified": [], "removed": []}}
        )
        assert "Goal:" not in note
        assert "added features (X)" in note

    def test_note_empty_changes_still_preserves(self) -> None:
        # Degenerate delta (no feature changes) → still a valid carry-forward note.
        note = stack_advisor.build_revision_note({"changes": {}})
        assert "Preserve the established stack" in note
        assert "Recommend only the incremental" not in note

    def test_note_missing_changes_key(self) -> None:
        note = stack_advisor.build_revision_note({"goal": "g"})
        assert "Goal: g" in note
        assert note.endswith("]")

    # ----- seed selection -----

    def _implement_prior_stack(self, wd: str, stack: dict[str, Any]) -> None:
        from spec4 import project_manager

        project_manager.save_stack(wd, stack, 0)
        project_manager.get_version_dir(wd, 0).joinpath("IMPLEMENTED").write_text("")

    def test_revision_seed_used_when_prior_stack_and_delta_exist(
        self, tmp_path: Any
    ) -> None:
        wd = str(tmp_path)
        self._implement_prior_stack(
            wd,
            {
                "stack_spec": {
                    "name": "App",
                    "libraries": {"backend": [{"name": "FastAPI", "purpose": "API"}]},
                }
            },
        )
        session = make_session(
            active_agent="stack_advisor",
            working_dir=wd,
            code_review={"code_review": {}},
            vision_statement=_stack_revision_vision(
                added=["Subscriptions"], goal="Add billing"
            ),
        )
        with mock_litellm_stream("Carrying forward your stack."):
            collect(stack_advisor.run(None, session, session["llm_config"]))
        seed = session["stack_advisor_messages"][0]["content"]
        assert "REVISION mode" in seed
        assert "FastAPI" in seed  # established stack carried forward
        assert "Subscriptions" in seed  # delta scoping note
        assert "Add billing" in seed

    def test_prior_stack_without_delta_is_not_revision(self, tmp_path: Any) -> None:
        # Implemented prior stack exists, but the vision has no revision delta —
        # falls through to the brownfield code-review branch, not revision mode.
        wd = str(tmp_path)
        self._implement_prior_stack(wd, {"stack_spec": {"name": "App"}})
        session = make_session(
            active_agent="stack_advisor",
            working_dir=wd,
            code_review={"code_review": {}},
            vision_statement={"vision_statement": {"name": "App"}},
        )
        with mock_litellm_stream("ok"):
            collect(stack_advisor.run(None, session, session["llm_config"]))
        seed = session["stack_advisor_messages"][0]["content"]
        assert "REVISION mode" not in seed

    def test_delta_without_prior_stack_is_not_revision(self) -> None:
        # Vision carries a delta but no prior implemented stack on disk
        # (working_dir is None) — not revision mode.
        session = make_session(
            active_agent="stack_advisor",
            working_dir=None,
            vision_statement=_stack_revision_vision(added=["Returns"]),
        )
        with mock_litellm_stream("ok"):
            collect(stack_advisor.run(None, session, session["llm_config"]))
        seed = session["stack_advisor_messages"][0]["content"]
        assert "REVISION mode" not in seed


# ---------------------------------------------------------------------------
# Stack Advisor branch tests
# ---------------------------------------------------------------------------


class TestStackAdvisorBranches:
    def test_initialises_messages_if_missing(self) -> None:
        session = make_session(
            active_agent="stack_advisor",
            vision_statement={"name": "App", "vision": "v"},
        )
        del session["stack_advisor_messages"]
        with mock_litellm_stream("Hello"):
            collect(stack_advisor.run(None, session, session["llm_config"]))
        assert "stack_advisor_messages" in session

    def test_reentry_drops_orphan_user_and_reseeds(self) -> None:
        # Orphan user from a failed previous brownfield init must be dropped
        # so the seed-with-vision flow re-runs cleanly.
        session = make_session(
            active_agent="stack_advisor",
            vision_statement={"name": "App", "vision": "v"},
        )
        session["stack_advisor_messages"] = [{"role": "user", "content": "hi"}]
        with mock_litellm_stream("Reviewing the vision now."):
            output = collect(stack_advisor.run(None, session, session["llm_config"]))
        assert "Reviewing" in output
        # Final history must be a clean user-then-assistant pair.
        roles = [m["role"] for m in session["stack_advisor_messages"]]
        assert roles == ["user", "assistant"]

    def test_existing_stack_seed_contains_stack_info(self) -> None:
        vision = {"name": "App", "vision": "v"}
        stack = {"stack_spec": {"languages": ["Python"]}}
        session = make_session(
            active_agent="stack_advisor", vision_statement=vision, stack_statement=stack
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [make_stream_chunk("Ok"), make_stream_chunk("", finish_reason="stop")]
            )
            collect(stack_advisor.run(None, session, session["llm_config"]))
        sent = mock_llm.call_args[1]["messages"]
        assert any("Python" in m["content"] for m in sent if m["role"] != "system")

    def test_code_review_seed_calls_llm(self) -> None:
        review = {"code_review": {"languages": ["Python"]}}
        session = make_session(
            active_agent="stack_advisor",
            vision_statement={"name": "App", "vision": "v"},
            code_review=review,
            stack_statement=None,
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [make_stream_chunk("Ok"), make_stream_chunk("", finish_reason="stop")]
            )
            collect(stack_advisor.run(None, session, session["llm_config"]))
        mock_llm.assert_called_once()


# ---------------------------------------------------------------------------
# _load_design_manifest (stack_advisor)
# ---------------------------------------------------------------------------


class TestLoadDesignManifest:
    """StackAdvisor reads Designer's manifest, never the visual mock (D-SC5c)."""

    def test_returns_none_when_absent(self, tmp_path: Any) -> None:
        from spec4.agents._stack_context import load_design_manifest

        assert load_design_manifest(tmp_path) is None
        assert load_design_manifest(None) is None

    def test_returns_none_when_malformed(self, tmp_path: Any) -> None:
        from spec4.agents._stack_context import load_design_manifest

        (tmp_path / "manifest.json").write_text("{not json")
        assert load_design_manifest(tmp_path) is None

    def test_reads_manifest(self, tmp_path: Any) -> None:
        from spec4.agents._stack_context import load_design_manifest

        (tmp_path / "manifest.json").write_text('{"name": "X"}')
        assert load_design_manifest(tmp_path) == {"name": "X"}

    def test_mock_is_never_read(self, tmp_path: Any) -> None:
        # the mock is the coding agent's reference, handed on by path; a stack
        # choice must not depend on its markup, and must not pull it into context
        from spec4.agents._stack_context import load_design_manifest

        (tmp_path / "mock.html").write_text("<html>marker-should-not-appear</html>")
        assert load_design_manifest(tmp_path) is None


class TestStackAdvisorUnparseableArtifact:
    """D-SA-P3: the D-SC-P3 fix applied to StackAdvisor.

    `_extract_stack_json` returns None both for "still conversing" and for "the
    artifact block came back unreadable". When the reply opened with a fence it
    was suppressed on its way to the screen, so the second case used to end the
    turn with an empty bubble, no STACK_COMPLETE, and no stack.json.
    """

    _TRUNCATED = '```json\n{"stack_spec": {"name": "App", "langua'
    _VALID = '```json\n{"stack_spec": {"name": "App", "languages": ["Python"]}}\n```'

    def _session(self) -> dict[str, Any]:
        session = make_session(
            active_agent="stack_advisor",
            vision_statement={"name": "App", "vision": "v"},
        )
        session["stack_advisor_messages"] = [
            {"role": "user", "content": "seed"},
            {"role": "assistant", "content": "Which language do you prefer?"},
        ]
        return session

    def _run(self, *replies: str) -> tuple[dict[str, Any], str, list[Any]]:
        session = self._session()
        fake_completion, calls = _reply_sequence(*replies)
        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            output = collect(
                stack_advisor.run("looks good", session, session["llm_config"])
            )
        return session, output, calls

    def test_truncated_block_is_re_asked(self) -> None:
        session, _, calls = self._run(self._TRUNCATED, self._VALID)
        assert len(calls) == 2, "the unreadable artifact must trigger one re-ask"
        assert session["stack_advisor_state"] == STATE_STACK_COMPLETE
        assert session["stack_statement"]["stack_spec"]["name"] == "App"

    def test_reask_message_asks_for_a_fenced_block(self) -> None:
        """The extractor reads a fence, so the re-ask must demand one — asking
        for bare JSON would only move the failure."""
        session, _, _ = self._run(self._TRUNCATED, self._VALID)
        reask = [
            m
            for m in session["stack_advisor_messages"]
            if m["role"] == "user" and "could not be read" in m["content"]
        ]
        assert len(reask) == 1
        assert "fenced" in reask[0]["content"]

    def test_turn_never_ends_silently(self) -> None:
        session, output, _ = self._run(self._TRUNCATED, self._TRUNCATED)
        assert session["_display_override"]
        assert output.strip(), "the turn yielded nothing visible"
        last = session["stack_advisor_messages"][-1]
        assert last["role"] == "assistant"
        assert last["content"] == session["_display_override"]

    def test_failed_reask_leaves_no_dead_end_user_turn(self) -> None:
        session, _, _ = self._run(self._TRUNCATED, self._TRUNCATED)
        assert not [
            m
            for m in session["stack_advisor_messages"]
            if m["role"] == "user" and "could not be read" in m["content"]
        ]

    def test_state_is_not_advanced_when_both_attempts_fail(self) -> None:
        session, _, _ = self._run(self._TRUNCATED, self._TRUNCATED)
        assert session["stack_advisor_state"] != STATE_STACK_COMPLETE
        assert session.get("stack_statement") is None

    def test_ordinary_prose_reply_is_left_alone(self) -> None:
        session = self._session()
        with mock_litellm_stream("Which database are you leaning towards?") as llm:
            output = collect(
                stack_advisor.run("one question first", session, session["llm_config"])
            )
        assert llm.call_count == 1, "a prose reply must not trigger a re-ask"
        assert "Which database" in output
        assert session["stack_advisor_state"] != STATE_STACK_COMPLETE
