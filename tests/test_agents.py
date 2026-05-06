from collections.abc import Iterable
from typing import Any
from unittest.mock import MagicMock, patch

from spec4.agents import brainstormer, code_scanner, deployer, phaser, stack_advisor
from spec4.app_constants import (
    STATE_IN_PROGRESS,
    STATE_PHASES_COMPLETE,
    STATE_REVIEW_COMPLETE,
    STATE_STACK_COMPLETE,
    STATE_VISION_COMPLETE,
)


def make_session(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "phase": "chat",
        "active_agent": "brainstormer",
        "working_dir": None,
        "code_review": None,
        "brainstormer_state": STATE_IN_PROGRESS,
        "brainstormer_messages": [],
        "vision_statement": None,
        "stack_advisor_messages": [],
        "stack_advisor_state": STATE_IN_PROGRESS,
        "stack_statement": None,
        "phaser_messages": [],
        "phaser_state": None,
        "phases": [],
        "code_scanner_messages": [],
        "code_scanner_state": STATE_IN_PROGRESS,
        "llm_config": {"model": "gpt-4o-mini", "api_key": "sk-test"},
        "tavily_api_key": None,
        "_warn_existing_content": False,
        "_dir_has_content": False,
    }
    defaults.update(overrides)
    return dict(defaults)


def collect(gen: Iterable[str]) -> str:
    return "".join(gen)


def make_stream_chunk(content: str, finish_reason: str | None = None) -> MagicMock:
    chunk = MagicMock()
    chunk.choices[0].delta.content = content
    chunk.choices[0].delta.tool_calls = None
    chunk.choices[0].finish_reason = finish_reason
    return chunk


def mock_litellm_stream(text: str) -> Any:
    """Return a context that mocks litellm.completion to stream the given text."""
    chunks = [make_stream_chunk(c) for c in text]
    chunks.append(make_stream_chunk("", finish_reason="stop"))
    mock_response = iter(chunks)
    return patch("spec4.tavily_mcp.litellm.completion", return_value=mock_response)


# ---------------------------------------------------------------------------
# Brainstormer tests
# ---------------------------------------------------------------------------


class TestBrainstormer:
    def test_opening_asks_for_idea(self) -> None:
        session = make_session()
        output = collect(brainstormer.run(None, session, session["llm_config"]))
        assert (
            "project" in output.lower()
            or "idea" in output.lower()
            or "brainstorm" in output.lower()
        )

    def test_opening_does_not_call_llm(self) -> None:
        session = make_session()
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()

    def test_user_input_streams_llm_output(self) -> None:
        session = make_session()
        with mock_litellm_stream("Great idea! Let me ask some questions."):
            output = collect(
                brainstormer.run(
                    "I want to build a todo app", session, session["llm_config"]
                )
            )
        assert "Great idea!" in output

    def test_conversation_history_accumulated(self) -> None:
        session = make_session()
        with mock_litellm_stream("Interesting!"):
            collect(
                brainstormer.run("I want a todo app", session, session["llm_config"])
            )

        assert len(session["brainstormer_messages"]) == 2
        assert session["brainstormer_messages"][0] == {
            "role": "user",
            "content": "I want a todo app",
        }
        assert session["brainstormer_messages"][1]["role"] == "assistant"
        assert "Interesting!" in session["brainstormer_messages"][1]["content"]

    def test_vision_json_sets_state_complete(self) -> None:
        session = make_session()
        vision_response = (
            "Great vision!\n\n```json\n"
            '{"vision_statement": {"name": "TodoApp", "vision": "A simple task manager"}}\n'  # noqa: E501
            "```"
        )
        with mock_litellm_stream(vision_response):
            collect(
                brainstormer.run("Yes, finalize it", session, session["llm_config"])
            )

        assert session["brainstormer_state"] == STATE_VISION_COMPLETE
        assert session["vision_statement"] == {
            "vision_statement": {"name": "TodoApp", "vision": "A simple task manager"}
        }

    def test_non_vision_response_stays_in_progress(self) -> None:
        session = make_session()
        with mock_litellm_stream("What type of users will use this app?"):
            collect(
                brainstormer.run("I want a todo app", session, session["llm_config"])
            )

        assert session["brainstormer_state"] == STATE_IN_PROGRESS
        assert session["vision_statement"] is None

    def test_llm_called_with_system_prompt_and_user_message(self) -> None:
        session = make_session()
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [
                    make_stream_chunk("Response"),
                    make_stream_chunk("", finish_reason="stop"),
                ]
            )
            collect(brainstormer.run("My idea", session, session["llm_config"]))

        call_kwargs = mock_llm.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1] == {"role": "user", "content": "My idea"}

    def test_llm_called_with_full_history_on_second_turn(self) -> None:
        session = make_session(
            brainstormer_messages=[
                {"role": "user", "content": "first message"},
                {"role": "assistant", "content": "first response"},
            ]
        )
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [
                    make_stream_chunk("Second response"),
                    make_stream_chunk("", finish_reason="stop"),
                ]
            )
            collect(brainstormer.run("second message", session, session["llm_config"]))

        call_kwargs = mock_llm.call_args[1]
        messages = call_kwargs["messages"]
        # system + 2 prior + new user = 4 messages
        assert len(messages) == 4
        assert messages[-1] == {"role": "user", "content": "second message"}

    def test_initialises_brainstormer_messages_if_missing(self) -> None:
        session = make_session()
        del session["brainstormer_messages"]
        with mock_litellm_stream("Hello!"):
            collect(brainstormer.run("An idea", session, session["llm_config"]))
        assert "brainstormer_messages" in session


class TestStalenessQuestion:
    """When an upstream artifact is updated after a downstream agent has
    completed, re-entering that agent must surface a revision question rather
    than silently replaying the now-outdated prior response."""

    def _setup_stale(
        self, tmp_path: Any, output_name: str, input_name: str
    ) -> None:
        """Create output_name with old mtime and input_name with newer mtime."""
        import os
        spec4 = tmp_path / ".spec4"
        spec4.mkdir(parents=True, exist_ok=True)
        for name, mtime in [(output_name, 1_000.0), (input_name, 2_000.0)]:
            p = spec4 / name
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
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(
                stack_advisor.run(None, session, session["llm_config"])
            )
        # No LLM call — the question is statically yielded.
        mock_llm.assert_not_called()
        assert "updated" in output.lower() or "revise" in output.lower()
        # Session is marked acknowledged at the current vision mtime.
        ack = session["stack_advisor_stale_acknowledged"]
        assert ack.get("vision") == 2_000.0

    def test_replay_path_runs_when_no_staleness(self, tmp_path: Any) -> None:
        # Output is newer than input → not stale → replay branch fires.
        import os
        spec4 = tmp_path / ".spec4"
        spec4.mkdir()
        (spec4 / "vision.json").write_text("{}")
        os.utime(spec4 / "vision.json", (1_000.0, 1_000.0))
        (spec4 / "stack.json").write_text("{}")
        os.utime(spec4 / "stack.json", (2_000.0, 2_000.0))

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
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(
                stack_advisor.run(None, session, session["llm_config"])
            )
        mock_llm.assert_not_called()
        assert "Final stack JSON output." in output

    def test_acknowledged_at_same_mtime_does_not_reask(
        self, tmp_path: Any
    ) -> None:
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
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(
                stack_advisor.run(None, session, session["llm_config"])
            )
        mock_llm.assert_not_called()
        # Replay branch fires — last assistant message comes back.
        assert "Last assistant message." in output

    def test_input_updated_again_triggers_reask(self, tmp_path: Any) -> None:
        # Acknowledged at 2_000.0, but vision has since been updated to 3_000.0.
        import os
        spec4 = tmp_path / ".spec4"
        spec4.mkdir()
        (spec4 / "stack.json").write_text("{}")
        os.utime(spec4 / "stack.json", (1_000.0, 1_000.0))
        (spec4 / "vision.json").write_text("{}")
        os.utime(spec4 / "vision.json", (3_000.0, 3_000.0))

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
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(
                stack_advisor.run(None, session, session["llm_config"])
            )
        mock_llm.assert_not_called()
        # Re-asks because the mtime moved.
        assert "revise" in output.lower() or "updated" in output.lower()
        assert session["stack_advisor_stale_acknowledged"]["vision"] == 3_000.0


class TestResumeSummary:
    """When the user navigates back to an in-progress agent after a break,
    replaying the last assistant message verbatim drops them into a
    mid-thought sentence with no surrounding context. Instead, the first
    re-entry per session-store lifetime should inject a synthetic user
    message asking the LLM for a recap-then-continue."""

    def _in_progress_session(self, agent: str, **overrides: Any) -> dict[str, Any]:
        msgs_key = f"{agent}_messages"
        return make_session(
            active_agent=agent,
            **{
                msgs_key: [
                    {"role": "user", "content": "earlier turn"},
                    {
                        "role": "assistant",
                        "content": (
                            "Good. Now I understand how Vercel handles env "
                            "variables. For a React + Vite SPA you likely won't "
                            "need many secrets at this stage..."
                        ),
                    },
                ],
                **overrides,
            },
        )

    def test_deployer_first_reentry_calls_llm_for_recap(self) -> None:
        session = self._in_progress_session(
            "deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            stack_statement={"name": "App"},
        )
        with mock_litellm_stream(
            "**Recap:** We've discussed deployment to Vercel. **Next:** "
            "what monitoring would you like?"
        ):
            output = collect(deployer.run(None, session, session["llm_config"]))

        assert "Recap" in output
        assert session["deployer_resumed"] is True
        # The synthetic user prompt is now in the message log, followed by the
        # LLM's recap reply.
        msgs = session["deployer_messages"]
        assert msgs[-2]["role"] == "user"
        assert "resuming this session" in msgs[-2]["content"]
        assert msgs[-1]["role"] == "assistant"
        assert "Recap" in msgs[-1]["content"]

    def test_second_reentry_replays_without_calling_llm(self) -> None:
        session = self._in_progress_session(
            "deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            deployer_resumed=True,
        )
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(deployer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        # The original last assistant message comes back via replay.
        assert "Vercel" in output

    def test_completed_agent_replays_artifact_not_recap(self) -> None:
        # Brainstormer is done — the last assistant turn is the
        # formatted-vision text, not a mid-thought question. Replay is right.
        session = self._in_progress_session(
            "brainstormer",
            brainstormer_state=STATE_VISION_COMPLETE,
            vision_statement={"name": "App"},
        )
        # Overwrite the last assistant content with a finished-artifact display
        # and snapshot the message count to match (this is what the agent does
        # when it writes the artifact).
        session["brainstormer_messages"][-1]["content"] = "**Vision:** App\n\n…"
        session["brainstormer_artifact_msg_count"] = len(
            session["brainstormer_messages"]
        )
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(
                brainstormer.run(None, session, session["llm_config"])
            )
        mock_llm.assert_not_called()
        assert "Vision" in output
        assert session.get("brainstormer_resumed") is not True

    def test_completed_agent_in_revision_mode_does_recap(self) -> None:
        # Brainstormer finished earlier, the user has chatted further past the
        # artifact (e.g., asking for revisions). The last message is now a
        # mid-thought question — so the recap should fire even though the
        # agent's *_state is STATE_*_COMPLETE.
        session = self._in_progress_session(
            "brainstormer",
            brainstormer_state=STATE_VISION_COMPLETE,
            vision_statement={"name": "App"},
        )
        # Snapshot is older than the current message count, simulating
        # post-artifact revision turns.
        session["brainstormer_artifact_msg_count"] = 0
        with mock_litellm_stream(
            "**Recap:** We finalized your vision for App. **Next:** which "
            "section would you like to refine?"
        ):
            output = collect(
                brainstormer.run(None, session, session["llm_config"])
            )
        assert "Recap" in output
        assert session["brainstormer_resumed"] is True

    def test_empty_messages_skips_recap_branch(self) -> None:
        # Fresh start — the static greeting branch must run, not the
        # recap branch (which requires non-empty msgs).
        session = make_session(active_agent="brainstormer")
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(
                brainstormer.run(None, session, session["llm_config"])
            )
        mock_llm.assert_not_called()
        assert "Brainstormer" in output
        assert session.get("brainstormer_resumed") is not True

    def test_staleness_takes_precedence_over_recap(self, tmp_path: Any) -> None:
        # Both staleness AND a fresh resume condition are present; the
        # staleness question must fire first (it's more important).
        import os
        spec4 = tmp_path / ".spec4"
        spec4.mkdir()
        for name, mtime in [("stack.json", 1_000.0), ("vision.json", 2_000.0)]:
            p = spec4 / name
            p.write_text("{}", encoding="utf-8")
            os.utime(p, (mtime, mtime))
        session = self._in_progress_session(
            "stack_advisor",
            working_dir=str(tmp_path),
            vision_statement={"name": "App"},
            stack_statement={"name": "App"},
        )
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(
                stack_advisor.run(None, session, session["llm_config"])
            )
        mock_llm.assert_not_called()
        assert "revise" in output.lower() or "updated" in output.lower()
        # Resume flag is NOT set — recap path didn't fire.
        assert session.get("stack_advisor_resumed") is not True


class TestOrphanTurnRecovery:
    """An LLM error mid-stream leaves the agent's history with a trailing user
    turn and no assistant followup. The next entry must recover, not stall."""

    def test_init_turn_recovers_when_history_ends_with_user(self) -> None:
        # Brownfield init: an earlier vision-update prompt was appended to
        # brainstormer_messages but the LLM call that followed raised, so the
        # message log is now [user_only].
        session = make_session(
            vision_statement={"summary": "existing"},
            brainstormer_messages=[
                {
                    "role": "user",
                    "content": "I have an existing vision statement...",
                }
            ],
        )
        with mock_litellm_stream("Hi! Let's review your existing vision."):
            output = collect(
                brainstormer.run(None, session, session["llm_config"])
            )

        # The agent must have produced output (didn't silently return zero
        # chunks via a stale-replay path).
        assert "existing vision" in output.lower()
        # And history ends correctly with the new assistant turn.
        assert session["brainstormer_messages"][-1]["role"] == "assistant"

    def test_user_submit_after_failure_drops_orphan_then_appends(self) -> None:
        # Same orphan setup, but now the user submits a new message.
        session = make_session(
            brainstormer_messages=[
                {"role": "user", "content": "earlier orphan"},
            ]
        )
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [
                    make_stream_chunk("ok"),
                    make_stream_chunk("", finish_reason="stop"),
                ]
            )
            collect(
                brainstormer.run("new message", session, session["llm_config"])
            )

        # The LLM must NOT receive two consecutive user messages — the orphan
        # gets dropped before the new user turn is appended.
        sent = mock_llm.call_args[1]["messages"]
        non_system = [m for m in sent if m["role"] != "system"]
        assert non_system == [{"role": "user", "content": "new message"}]


# ---------------------------------------------------------------------------
# Stack Advisor tests
# ---------------------------------------------------------------------------


class TestStackAdvisor:
    def test_opening_calls_llm(self) -> None:
        vision = {"name": "TodoApp", "vision": "A simple task manager"}
        session = make_session(active_agent="stack_advisor", vision_statement=vision)
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
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
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [make_stream_chunk("Ok"), make_stream_chunk("", finish_reason="stop")]
            )
            collect(stack_advisor.run(None, session, session["llm_config"]))
        call_kwargs = mock_llm.call_args[1]
        messages = call_kwargs["messages"]
        assert any("TodoApp" in m["content"] for m in messages)

    def test_opening_no_vision_still_calls_llm(self) -> None:
        session = make_session(active_agent="stack_advisor", vision_statement=None)
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
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
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(stack_advisor.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "Which language do you prefer?" in output

    def test_llm_called_with_system_prompt(self) -> None:
        session = make_session(
            active_agent="stack_advisor",
            vision_statement={"name": "App", "vision": "v"},
        )
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [make_stream_chunk("Ok"), make_stream_chunk("", finish_reason="stop")]
            )
            collect(stack_advisor.run("Python", session, session["llm_config"]))
        call_kwargs = mock_llm.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"


# ---------------------------------------------------------------------------
# Brainstormer branch tests
# ---------------------------------------------------------------------------


class TestBrainstormerBranches:
    def test_extract_vision_json_valid(self) -> None:
        from spec4.agents.brainstormer import _extract_vision_json

        text = '```json\n{"vision_statement": {"name": "App", "vision": "desc"}}\n```'
        assert _extract_vision_json(text) == {
            "vision_statement": {"name": "App", "vision": "desc"}
        }

    def test_extract_vision_json_invalid_json_returns_none(self) -> None:
        from spec4.agents.brainstormer import _extract_vision_json

        assert _extract_vision_json("```json\n{invalid}\n```") is None

    def test_extract_vision_json_no_block_returns_none(self) -> None:
        from spec4.agents.brainstormer import _extract_vision_json

        assert _extract_vision_json("no json here") is None

    def test_format_vision_handles_string_features(self) -> None:
        # Real LLMs sometimes emit features as bare strings rather than the
        # canonical {Name: {description, example}} shape — this used to crash
        # with `'str' object has no attribute 'items'` and surface raw JSON
        # plus an AttributeError to the user.
        from spec4.agents.brainstormer import _format_vision_as_text

        vision = {
            "vision_statement": {
                "name": "Chrome & Carbon",
                "vision": {
                    "purpose": "demo",
                    "key_features_mvp": ["AI Recommendations", "User Reviews"],
                    "future_enhancements": ["Predictive AI"],
                },
            }
        }
        out = _format_vision_as_text(vision)
        assert "AI Recommendations" in out
        assert "User Reviews" in out
        assert "Continue to Designer" in out

    def test_format_vision_handles_flat_named_features(self) -> None:
        from spec4.agents.brainstormer import _format_vision_as_text

        vision = {
            "vision_statement": {
                "name": "App",
                "vision": {
                    "key_features_mvp": [
                        {"name": "AI Recs", "description": "Personalized suggestions"},
                    ],
                },
            }
        }
        out = _format_vision_as_text(vision)
        assert "AI Recs" in out
        assert "Personalized suggestions" in out

    def test_run_uses_fallback_display_when_format_raises(self) -> None:
        # Even with a hardened formatter, an unexpected schema shape must not
        # leak raw JSON to the chat. The agent's run() wraps the formatter in
        # try/except and falls back to a minimal display that still includes
        # the project name and the transition message.
        session = make_session(
            brainstormer_messages=[
                {"role": "user", "content": "ready"},
                {
                    "role": "assistant",
                    "content": (
                        '```json\n'
                        '{"vision_statement": {"name": "App", "vision": "desc"}}\n'
                        '```'
                    ),
                },
            ],
            brainstormer_resumed=True,
        )
        with patch(
            "spec4.agents.brainstormer._format_vision_as_text",
            side_effect=AttributeError("'str' object has no attribute 'items'"),
        ):
            with mock_litellm_stream(
                '```json\n'
                '{"vision_statement": {"name": "App", "vision": "desc"}}\n'
                '```'
            ):
                collect(
                    brainstormer.run("yes", session, session["llm_config"])
                )
        override = session.get("_display_override")
        assert override is not None
        assert "App" in override
        assert "Continue to Designer" in override
        # The agent still records vision_statement and flips state to complete.
        assert session["brainstormer_state"] == STATE_VISION_COMPLETE
        assert session["vision_statement"] == {
            "vision_statement": {"name": "App", "vision": "desc"}
        }

    def test_reentry_replays_last_assistant_message(self) -> None:
        session = make_session(
            brainstormer_resumed=True,
            brainstormer_messages=[
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "Existing response"},
            ],
        )
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "Existing response" in output

    def test_reentry_drops_orphan_user_and_falls_through(self) -> None:
        # An interrupted previous turn left a user message orphaned in history.
        # Re-entry must drop it and proceed to the fresh-start greeting (no
        # vision/code_review/specmem in this session), not silently yield zero
        # chunks.
        session = make_session(
            brainstormer_messages=[{"role": "user", "content": "hi"}]
        )
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert output != ""
        assert session["brainstormer_messages"] == []

    def test_preloaded_vision_calls_llm(self) -> None:
        vision = {"name": "MyApp", "vision": "desc"}
        session = make_session(vision_statement=vision)
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [
                    make_stream_chunk("Summary"),
                    make_stream_chunk("", finish_reason="stop"),
                ]
            )
            output = collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_called_once()
        assert "Summary" in output

    def test_preloaded_vision_seed_contains_vision_name(self) -> None:
        vision = {"name": "MyApp", "vision": "desc"}
        session = make_session(vision_statement=vision)
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [make_stream_chunk("Ok"), make_stream_chunk("", finish_reason="stop")]
            )
            collect(brainstormer.run(None, session, session["llm_config"]))
        sent_messages = mock_llm.call_args[1]["messages"]
        assert any(
            "MyApp" in m["content"] for m in sent_messages if m["role"] != "system"
        )

    def test_code_review_seed_calls_llm(self) -> None:
        review = {"code_review": {"is_software_project": True}}
        session = make_session(code_review=review, vision_statement=None)
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [
                    make_stream_chunk("Review"),
                    make_stream_chunk("", finish_reason="stop"),
                ]
            )
            collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_called_once()


# ---------------------------------------------------------------------------
# Stack Advisor branch tests
# ---------------------------------------------------------------------------


class TestStackAdvisorBranches:
    def test_extract_stack_json_with_stack_spec_key(self) -> None:
        from spec4.agents.stack_advisor import _extract_stack_json

        text = '```json\n{"stack_spec": {"languages": ["Python"]}}\n```'
        result = _extract_stack_json(text)
        assert result is not None and "stack_spec" in result

    def test_extract_stack_json_with_stack_key(self) -> None:
        from spec4.agents.stack_advisor import _extract_stack_json

        text = '```json\n{"stack": {"languages": ["Python"]}}\n```'
        assert _extract_stack_json(text) is not None

    def test_extract_stack_json_no_stack_key_returns_none(self) -> None:
        from spec4.agents.stack_advisor import _extract_stack_json

        assert _extract_stack_json('```json\n{"name": "App"}\n```') is None

    def test_extract_stack_json_invalid_json_returns_none(self) -> None:
        from spec4.agents.stack_advisor import _extract_stack_json

        assert _extract_stack_json("```json\n{invalid}\n```") is None

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
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
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
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [make_stream_chunk("Ok"), make_stream_chunk("", finish_reason="stop")]
            )
            collect(stack_advisor.run(None, session, session["llm_config"]))
        mock_llm.assert_called_once()


# ---------------------------------------------------------------------------
# CodeScanner tests
# ---------------------------------------------------------------------------


class TestCodeScanner:
    def test_no_working_dir_yields_warning(self) -> None:
        session = make_session(working_dir=None)
        output = collect(code_scanner.run(None, session, session["llm_config"]))
        assert (
            "working directory" in output.lower()
            or "no project directory" in output.lower()
        )

    def test_no_working_dir_does_not_call_llm(self) -> None:
        session = make_session(working_dir=None)
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            collect(code_scanner.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()

    def test_reentry_replays_last_assistant_message(self) -> None:
        session = make_session(
            code_scanner_resumed=True,
            code_scanner_messages=[
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "CodeScanner response"},
            ],
        )
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(code_scanner.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "CodeScanner response" in output

    def test_reentry_drops_orphan_user_and_falls_through(self) -> None:
        # No working_dir set in the default session, so after the orphan is
        # dropped the agent yields its "select a directory" notice rather
        # than getting stuck on a malformed history.
        session = make_session(code_scanner_messages=[{"role": "user", "content": "hi"}])
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(code_scanner.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "directory" in output.lower()
        assert session["code_scanner_messages"] == []

    def test_user_input_calls_llm(self) -> None:
        session = make_session(code_scanner_messages=[{"role": "user", "content": "seed"}])
        with mock_litellm_stream("Here is my review."):
            output = collect(code_scanner.run("Looks good", session, session["llm_config"]))
        assert "Here is my review." in output

    def test_review_json_sets_state_complete(self) -> None:
        session = make_session(code_scanner_messages=[{"role": "user", "content": "seed"}])
        review_response = '```json\n{"code_review": {"is_software_project": true}}\n```'
        with mock_litellm_stream(review_response):
            collect(code_scanner.run("Confirm", session, session["llm_config"]))
        assert session["code_scanner_state"] == STATE_REVIEW_COMPLETE
        assert session["code_review"] == {"code_review": {"is_software_project": True}}

    def test_non_review_response_stays_in_progress(self) -> None:
        session = make_session(code_scanner_messages=[{"role": "user", "content": "seed"}])
        with mock_litellm_stream("Tell me about section 1."):
            collect(code_scanner.run("Go on", session, session["llm_config"]))
        assert session["code_scanner_state"] == STATE_IN_PROGRESS
        assert session["code_review"] is None

    def test_extract_review_json_valid(self) -> None:
        from spec4.agents.code_scanner import _extract_review_json

        text = '```json\n{"code_review": {"is_software_project": true}}\n```'
        assert _extract_review_json(text) == {
            "code_review": {"is_software_project": True}
        }

    def test_extract_review_json_no_code_review_key_returns_none(self) -> None:
        from spec4.agents.code_scanner import _extract_review_json

        assert _extract_review_json('```json\n{"name": "App"}\n```') is None

    def test_extract_review_json_invalid_json_returns_none(self) -> None:
        from spec4.agents.code_scanner import _extract_review_json

        assert _extract_review_json("```json\n{bad}\n```") is None

    def test_initialises_code_scanner_messages_if_missing(self) -> None:
        session = make_session(code_scanner_messages=[{"role": "user", "content": "seed"}])
        del session["code_scanner_messages"]
        with mock_litellm_stream("Ok"):
            collect(code_scanner.run("Hi", session, session["llm_config"]))
        assert "code_scanner_messages" in session


# ---------------------------------------------------------------------------
# _gather_project_context tests
# ---------------------------------------------------------------------------


class TestGatherProjectContext:
    def test_empty_dir_reports_empty(self, tmp_path: Any) -> None:
        from spec4.agents.code_scanner import _gather_project_context

        result = _gather_project_context(str(tmp_path))
        assert "empty" in result.lower()

    def test_source_files_appear_in_tree(self, tmp_path: Any) -> None:
        from spec4.agents.code_scanner import _gather_project_context

        (tmp_path / "main.py").write_text("print('hello')")
        result = _gather_project_context(str(tmp_path))
        assert "main.py" in result

    def test_git_dir_is_skipped(self, tmp_path: Any) -> None:
        from spec4.agents.code_scanner import _gather_project_context

        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]")
        result = _gather_project_context(str(tmp_path))
        assert "config" not in result

    def test_readme_content_included(self, tmp_path: Any) -> None:
        from spec4.agents.code_scanner import _gather_project_context

        (tmp_path / "README.md").write_text("# My Project\nA cool app.")
        result = _gather_project_context(str(tmp_path))
        assert "My Project" in result

    def test_source_file_sample_included(self, tmp_path: Any) -> None:
        from spec4.agents.code_scanner import _gather_project_context

        (tmp_path / "app.py").write_text("def main():\n    pass\n")
        result = _gather_project_context(str(tmp_path))
        assert "def main" in result


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

    def test_opening_seeds_vision_and_stack(self) -> None:
        vision = {"name": "App", "vision": "desc"}
        stack = {"stack_spec": {"languages": ["Python"]}}
        session = make_session(vision_statement=vision, stack_statement=stack)
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
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
        session = make_session(phaser_messages=[{"role": "user", "content": "seed"}])
        phase_response = (
            '```json\n{"phase_number": 1, "phase_title": "Steel Thread", '
            '"total_phases": 1, "vision_statement": "v", "tech_stack_spec": '
            '{"dependencies": [], "configurations": ""}, "instructions": [], '
            '"risk_assessment": {"potential_bottlenecks": "", "mitigation_strategy": ""}, '  # noqa: E501
            '"verification": "run tests", "references": []}\n```'
        )
        with mock_litellm_stream(phase_response):
            collect(phaser.run("Approve", session, session["llm_config"]))
        assert session["phaser_state"] == STATE_PHASES_COMPLETE
        assert len(session["phases"]) == 1

    def test_non_phase_response_stays_incomplete(self) -> None:
        session = make_session(phaser_messages=[{"role": "user", "content": "seed"}])
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
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
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


# ---------------------------------------------------------------------------
# _load_design_context (stack_advisor)
# ---------------------------------------------------------------------------


class TestLoadDesignContext:
    def test_returns_empty_when_no_mock(self, tmp_path: Any) -> None:
        from spec4.agents.stack_advisor import _load_design_context

        assert _load_design_context(tmp_path) == ""

    def test_returns_empty_when_dir_has_no_mock_html(self, tmp_path: Any) -> None:
        from spec4.agents.stack_advisor import _load_design_context

        (tmp_path / "session.json").write_text("{}")
        assert _load_design_context(tmp_path) == ""

    def test_returns_context_string_when_mock_exists(self, tmp_path: Any) -> None:
        from spec4.agents.stack_advisor import _load_design_context

        html = "<!DOCTYPE html><html></html>"
        (tmp_path / "mock.html").write_text(html)
        result = _load_design_context(tmp_path)
        assert html in result

    def test_context_string_mentions_designer_agent(self, tmp_path: Any) -> None:
        from spec4.agents.stack_advisor import _load_design_context

        (tmp_path / "mock.html").write_text("<html/>")
        result = _load_design_context(tmp_path)
        assert "Designer" in result

    def test_context_string_mentions_frontend_rendering(self, tmp_path: Any) -> None:
        from spec4.agents.stack_advisor import _load_design_context

        (tmp_path / "mock.html").write_text("<html/>")
        result = _load_design_context(tmp_path)
        assert "frontend" in result.lower() or "rendering" in result.lower()


# ---------------------------------------------------------------------------
# _load_phaser_design_note (phaser)
# ---------------------------------------------------------------------------


class TestLoadPhaserDesignNote:
    def test_returns_mock_reference_when_mock_exists(self, tmp_path: Any) -> None:
        from spec4.agents.phaser import _load_phaser_design_note

        (tmp_path / "mock.html").write_text("<!DOCTYPE html><html></html>")
        result = _load_phaser_design_note(tmp_path)
        assert "mock.html" in result

    def test_mock_reference_under_500_chars(self, tmp_path: Any) -> None:
        from spec4.agents.phaser import _load_phaser_design_note

        (tmp_path / "mock.html").write_text("<html/>")
        assert len(_load_phaser_design_note(tmp_path)) < 500

    def test_returns_no_mock_note_when_absent(self, tmp_path: Any) -> None:
        from spec4.agents.phaser import _load_phaser_design_note

        result = _load_phaser_design_note(tmp_path)
        assert "no ui design mock" in result.lower()

    def test_returns_no_mock_note_when_file_empty(self, tmp_path: Any) -> None:
        from spec4.agents.phaser import _load_phaser_design_note

        (tmp_path / "mock.html").write_text("  \n  ")
        result = _load_phaser_design_note(tmp_path)
        assert "no ui design mock" in result.lower()

    def test_mock_note_mentions_coding_agent(self, tmp_path: Any) -> None:
        from spec4.agents.phaser import _load_phaser_design_note

        (tmp_path / "mock.html").write_text("<html/>")
        result = _load_phaser_design_note(tmp_path)
        assert "coding agent" in result.lower() or "implementat" in result.lower()

    def test_no_mock_note_mentions_discretion(self, tmp_path: Any) -> None:
        from spec4.agents.phaser import _load_phaser_design_note

        result = _load_phaser_design_note(tmp_path)
        assert "discretion" in result.lower()
