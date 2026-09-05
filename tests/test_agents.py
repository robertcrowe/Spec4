from collections.abc import Iterable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from spec4.agents import brainstormer, code_scanner, deployer, phaser, stack_advisor
from spec4.agents._utils import _ai_features_for_phaser, _suppressed_as_artifact
from spec4.app_constants import (
    STATE_DEPLOYER_COMPLETE,
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
        "project_mode": None,
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
    return patch("spec4.llm.litellm.completion", return_value=mock_response)


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
        with patch("spec4.llm.litellm.completion") as mock_llm:
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
        with patch("spec4.llm.litellm.completion") as mock_llm:
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
        with patch("spec4.llm.litellm.completion") as mock_llm:
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
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(
                stack_advisor.run(None, session, session["llm_config"])
            )
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
        with patch("spec4.llm.litellm.completion") as mock_llm:
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
        with patch("spec4.llm.litellm.completion") as mock_llm:
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
        with patch("spec4.llm.litellm.completion") as mock_llm:
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
        v0 = tmp_path / ".spec4" / "v0"
        v0.mkdir(parents=True, exist_ok=True)
        for name, mtime in [("stack.json", 1_000.0), ("vision.json", 2_000.0)]:
            p = v0 / name
            p.write_text("{}", encoding="utf-8")
            os.utime(p, (mtime, mtime))
        session = self._in_progress_session(
            "stack_advisor",
            working_dir=str(tmp_path),
            vision_statement={"name": "App"},
            stack_statement={"name": "App"},
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
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

    def test_user_submit_after_failure_routes_to_fresh_start(self) -> None:
        # The previous turn failed before the assistant reply could be
        # committed, leaving phaser_messages = [seed_orphan]. The user's new
        # message is a reply to UI text the agent never actually committed —
        # if we just dropped the orphan and appended the new message, the LLM
        # would be called with that reply alone, stripped of all seed context,
        # and would hallucinate an "I'm ready to help — please share your
        # project info" greeting. The recovery instead routes through the
        # fresh-start branch so the LLM gets the seed (or the static greeting
        # for greenfield projects with no vision/code_review).
        session = make_session(
            brainstormer_messages=[
                {"role": "user", "content": "earlier orphan"},
            ]
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(
                brainstormer.run("new message", session, session["llm_config"])
            )

        # No vision and no code review → fresh-start branch yields a static
        # greeting and does NOT call the LLM. The user's "new message" reply
        # is silently discarded since it was responding to nothing real.
        mock_llm.assert_not_called()
        assert "Brainstormer" in output

    def test_user_submit_after_failure_reseeds_brownfield_context(self) -> None:
        # Same orphan setup but with a vision_statement present (brownfield
        # revision mode). Recovery must re-seed the brownfield context rather
        # than calling the LLM with just the new user reply.
        vision = {"vision_statement": {"name": "CheckersApp"}}
        session = make_session(
            vision_statement=vision,
            brainstormer_messages=[
                {"role": "user", "content": "earlier orphan"},
            ],
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [
                    make_stream_chunk("Welcome back"),
                    make_stream_chunk("", finish_reason="stop"),
                ]
            )
            collect(
                brainstormer.run("new message", session, session["llm_config"])
            )

        sent = mock_llm.call_args[1]["messages"]
        user_content = " ".join(
            m["content"] for m in sent
            if m["role"] == "user" and isinstance(m["content"], str)
        )
        # The brownfield re-seed must include the existing vision so the
        # LLM has context, not just the user's "new message" reply alone.
        assert "CheckersApp" in user_content
        assert "new message" not in user_content


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
    return {
        "vision_statement": {"name": "App", "revision_history": [entry]}
    }


class TestStackAdvisorRevisionMode:
    """Revision mode: when a prior implemented stack exists and the vision carries
    a revision delta, StackAdvisor carries the established stack forward as the
    baseline and scopes recommendations to the delta rather than re-deciding the
    whole stack. The reader/note helpers are deterministic (no LLM)."""

    # ----- revision_delta -----

    def test_delta_none_for_greenfield_vision(self) -> None:
        assert stack_advisor.revision_delta(
            {"vision_statement": {"name": "Fresh"}}
        ) is None

    def test_delta_none_for_empty_or_missing(self) -> None:
        assert stack_advisor.revision_delta(None) is None
        assert stack_advisor.revision_delta({}) is None
        assert stack_advisor.revision_delta(
            {"vision_statement": {"revision_history": []}}
        ) is None
        # Non-enveloped (inner-form) vision is not revision mode.
        assert stack_advisor.revision_delta({"name": "App"}) is None

    def test_delta_returns_last_history_entry(self) -> None:
        vision = {
            "vision_statement": {
                "revision_history": [
                    {"version": 0, "goal": "first"},
                    {"version": 1, "goal": "Add returns",
                     "changes": {"added": ["Returns"]}},
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
            wd, {"stack_spec": {"name": "App", "libraries": {"backend": [
                {"name": "FastAPI", "purpose": "API"}]}}}
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

    def test_prior_stack_without_delta_is_not_revision(
        self, tmp_path: Any
    ) -> None:
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
# Brainstormer branch tests
# ---------------------------------------------------------------------------


class TestBrainstormerBranches:
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
        assert "Continue to Agentifier" in out

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

    def test_format_vision_handles_string_monetization(self) -> None:
        # Real LLMs sometimes emit `monetization` as a bare string rather than
        # the canonical {current, future_options} dict — this used to crash with
        # `'str' object has no attribute 'get'` and drop to the minimal fallback
        # display.
        from spec4.agents.brainstormer import _format_vision_as_text

        vision = {
            "vision_statement": {
                "name": "App",
                "vision": {
                    "purpose": "demo",
                    "monetization": "Free with optional donations",
                },
            }
        }
        out = _format_vision_as_text(vision)
        assert "Monetization" in out
        assert "Free with optional donations" in out

    def test_transition_includes_review_offer(self) -> None:
        from spec4.agents.brainstormer import _VISION_TRANSITION

        assert "Would you like to review the current vision?" in _VISION_TRANSITION

    def test_yes_after_review_offer_shows_vision(self) -> None:
        # Answering the review offer with a bare "yes" in the completed state
        # re-renders the stored vision deterministically — no LLM round-trip —
        # using the lighter review footer (not the transition with its offer, so
        # a follow-up "yes" can't re-loop).
        vision = {
            "vision_statement": {
                "name": "Checkers",
                "vision": {"purpose": "play checkers online"},
            }
        }
        session = make_session(
            brainstormer_state=STATE_VISION_COMPLETE,
            vision_statement=vision,
            brainstormer_messages=[
                {"role": "user", "content": "done"},
                {
                    "role": "assistant",
                    "content": (
                        "**Vision Statement: Checkers**\n\n...\n\n"
                        "Would you like to review the current vision? (yes/no)"
                    ),
                },
            ],
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            out = collect(brainstormer.run("yes", session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "Checkers" in out
        assert "play checkers online" in out
        assert "That's the current vision" in out
        assert "Would you like to review the current vision?" not in out
        assert "Continue to Agentifier" in out
        # Deterministic render leaves the LLM log and state untouched.
        assert session["brainstormer_messages"][-1]["content"].endswith("(yes/no)")
        assert session["brainstormer_state"] == STATE_VISION_COMPLETE

    def test_y_shortform_shows_review(self) -> None:
        vision = {
            "vision_statement": {"name": "App", "vision": {"purpose": "x"}}
        }
        session = make_session(
            brainstormer_state=STATE_VISION_COMPLETE,
            vision_statement=vision,
            brainstormer_messages=[
                {
                    "role": "assistant",
                    "content": "Would you like to review the current vision? (yes/no)",
                },
            ],
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            out = collect(brainstormer.run("  Y ", session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "App" in out

    def test_yes_confirming_revision_is_not_review(self) -> None:
        # A "yes" that confirms a pending revision — where the latest assistant
        # turn is a proposal, not the review offer — must reach the LLM, not be
        # hijacked into a review render.
        vision = {
            "vision_statement": {"name": "App", "vision": {"purpose": "x"}}
        }
        session = make_session(
            brainstormer_state=STATE_VISION_COMPLETE,
            vision_statement=vision,
            brainstormer_messages=[
                {"role": "user", "content": "rename it to Foo"},
                {
                    "role": "assistant",
                    "content": "Got it — shall I rename the project to Foo?",
                },
            ],
        )
        with mock_litellm_stream("Updating the name now."):
            out = collect(brainstormer.run("yes", session, session["llm_config"]))
        assert "Updating the name now." in out
        assert "That's the current vision" not in out

    def test_question_after_offer_reaches_llm(self) -> None:
        # A non-affirmative reply to the offer (e.g. a question) is not a review
        # request and falls through to the LLM.
        vision = {
            "vision_statement": {"name": "App", "vision": {"purpose": "x"}}
        }
        session = make_session(
            brainstormer_state=STATE_VISION_COMPLETE,
            vision_statement=vision,
            brainstormer_messages=[
                {
                    "role": "assistant",
                    "content": "Would you like to review the current vision? (yes/no)",
                },
            ],
        )
        with mock_litellm_stream("Here is an answer."):
            out = collect(
                brainstormer.run(
                    "what are the features?", session, session["llm_config"]
                )
            )
        assert "Here is an answer." in out

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
        assert "Continue to Agentifier" in override
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
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "Existing response" in output

    def test_reentry_drops_orphan_user_and_falls_through(self) -> None:
        # An interrupted previous turn left a user message orphaned in history.
        # Re-entry must drop it and proceed to the fresh-start greeting (no
        # vision/code_review in this session), not silently yield zero
        # chunks.
        session = make_session(
            brainstormer_messages=[{"role": "user", "content": "hi"}]
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert output != ""
        assert session["brainstormer_messages"] == []

    def test_preloaded_vision_calls_llm(self) -> None:
        vision = {"name": "MyApp", "vision": "desc"}
        session = make_session(vision_statement=vision)
        with patch("spec4.llm.litellm.completion") as mock_llm:
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
        with patch("spec4.llm.litellm.completion") as mock_llm:
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
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [
                    make_stream_chunk("Review"),
                    make_stream_chunk("", finish_reason="stop"),
                ]
            )
            collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_called_once()


class TestBrainstormerRevisionMode:
    """Revision mode: when a prior implemented vision exists, Brainstormer scopes
    to the revision delta and the round's delta is folded into an accumulating
    ``revision_history`` deterministically (code owns the version integers)."""

    FENCE = "```json\n{}\n```"

    def _emit(self, vision_statement: dict, revision: object) -> Any:
        from json import dumps

        payload = {"vision_statement": vision_statement}
        if revision is not None:
            payload["revision"] = revision
        text = self.FENCE.format(dumps(payload))
        return iter(
            [make_stream_chunk(text), make_stream_chunk("", finish_reason="stop")]
        )

    def _implement(self, project_manager, wd: str, version: int, vision: dict) -> None:
        project_manager.save_vision(wd, vision, version)
        project_manager.get_version_dir(wd, version).joinpath(
            "IMPLEMENTED"
        ).write_text("")

    # ----- pure merge -----

    def test_stamp_normalizes_block(self) -> None:
        from spec4.agents.brainstormer import _stamp_revision_block

        out = _stamp_revision_block(
            {"goal": "g", "changes": {"added": ["X"]}, "rationale": "r"}, 2, 1
        )
        assert out == {
            "version": 2,
            "based_on_version": 1,
            "goal": "g",
            "changes": {"added": ["X"], "modified": [], "removed": []},
            "rationale": "r",
        }

    def test_apply_first_revision_empty_base(self) -> None:
        from spec4.agents.brainstormer import _apply_revision_history

        emitted = {"vision_statement": {"name": "A"}, "revision": {"goal": "g"}}
        prior = {"vision_statement": {"name": "A"}}  # no prior history
        out = _apply_revision_history(emitted, prior, None, 1, 0)
        hist = out["vision_statement"]["revision_history"]
        assert len(hist) == 1
        assert hist[0]["version"] == 1 and hist[0]["based_on_version"] == 0
        assert "revision" not in out

    def test_apply_accumulates_on_prior_history(self) -> None:
        from spec4.agents.brainstormer import _apply_revision_history

        prior = {
            "vision_statement": {
                "name": "A",
                "revision_history": [{"version": 1, "based_on_version": 0}],
            }
        }
        emitted = {"vision_statement": {"name": "A"}, "revision": {"goal": "g2"}}
        out = _apply_revision_history(emitted, prior, None, 2, 1)
        hist = out["vision_statement"]["revision_history"]
        assert [e["version"] for e in hist] == [1, 2]

    def test_apply_missing_block_preserves_prior_history(self) -> None:
        from spec4.agents.brainstormer import _apply_revision_history

        prior = {
            "vision_statement": {
                "revision_history": [{"version": 1, "based_on_version": 0}]
            }
        }
        emitted = {"vision_statement": {"name": "A"}}  # model emitted no revision
        out = _apply_revision_history(emitted, prior, None, 2, 1)
        # No new entry, but prior lineage is never dropped.
        hist = out["vision_statement"]["revision_history"]
        assert [e["version"] for e in hist] == [1]

    def test_apply_reentry_recovers_current_round_entry(self) -> None:
        from spec4.agents.brainstormer import _apply_revision_history

        prior = {"vision_statement": {"revision_history": []}}
        # The current session vision already carries this round's (v1) entry.
        current = {
            "vision_statement": {
                "revision_history": [{"version": 1, "based_on_version": 0, "goal": "g"}]
            }
        }
        emitted = {"vision_statement": {"name": "A"}}  # re-edit, no fresh block
        out = _apply_revision_history(emitted, prior, current, 1, 0)
        hist = out["vision_statement"]["revision_history"]
        assert len(hist) == 1 and hist[0]["goal"] == "g"

    # ----- seed selection + end-to-end -----

    def test_revision_seed_used_when_prior_vision_exists(
        self, tmp_path: Any
    ) -> None:
        from spec4 import project_manager

        wd = str(tmp_path)
        self._implement(
            project_manager, wd, 0, {"vision_statement": {"name": "Checkers"}}
        )
        project_manager.save_code_review(wd, {"code_review": {}}, 1)
        session = make_session(
            working_dir=wd, code_review={"code_review": {}}, vision_statement=None
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = self._emit({"name": "Checkers"}, None)
            collect(brainstormer.run(None, session, session["llm_config"]))
        seed = session["brainstormer_messages"][0]["content"]
        assert "REVISION mode" in seed
        assert "Checkers" in seed and "read-only" in seed

    def test_revision_round_merges_history_end_to_end(self, tmp_path: Any) -> None:
        from spec4 import project_manager

        wd = str(tmp_path)
        self._implement(
            project_manager, wd, 0, {"vision_statement": {"name": "Checkers"}}
        )
        project_manager.save_code_review(wd, {"code_review": {}}, 1)
        session = make_session(
            working_dir=wd, code_review={"code_review": {}}, vision_statement=None
        )
        rev = {
            "goal": "Add online play",
            "changes": {"added": ["Online Multiplayer"], "modified": [], "removed": []},
            "rationale": "users asked",
        }
        new_vs = {
            "name": "Checkers",
            "key_features_mvp": [{"Online Multiplayer": {"description": "remote"}}],
        }
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = self._emit(new_vs, rev)
            collect(brainstormer.run(None, session, session["llm_config"]))
        hist = session["vision_statement"]["vision_statement"]["revision_history"]
        assert len(hist) == 1
        assert hist[0]["version"] == 1 and hist[0]["based_on_version"] == 0
        assert hist[0]["changes"]["added"] == ["Online Multiplayer"]
        assert "revision" not in session["vision_statement"]

    def test_greenfield_gets_no_revision_history(self, tmp_path: Any) -> None:
        # No implemented round -> not revision mode -> history untouched.
        session = make_session(working_dir=str(tmp_path), vision_statement=None)
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = self._emit({"name": "Fresh"}, None)
            collect(brainstormer.run("done", session, session["llm_config"]))
        vs = session["vision_statement"]["vision_statement"]
        assert "revision_history" not in vs


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
        with patch("spec4.llm.litellm.completion") as mock_llm:
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
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(code_scanner.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "CodeScanner response" in output

    def test_reentry_drops_orphan_user_and_falls_through(self) -> None:
        # No working_dir set in the default session, so after the orphan is
        # dropped the agent yields its "select a directory" notice rather
        # than getting stuck on a malformed history.
        session = make_session(
            code_scanner_messages=[{"role": "user", "content": "hi"}]
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(code_scanner.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "directory" in output.lower()
        assert session["code_scanner_messages"] == []

    def test_user_input_calls_llm(self) -> None:
        session = make_session(
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        with mock_litellm_stream("Here is my review."):
            output = collect(
                code_scanner.run("Looks good", session, session["llm_config"])
            )
        assert "Here is my review." in output

    def test_review_json_sets_state_complete(self) -> None:
        session = make_session(
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        review_response = (
            '```json\n{"code_review": {"schema_version": 1, '
            '"is_software_project": true}}\n```'
        )
        with mock_litellm_stream(review_response):
            collect(code_scanner.run("Confirm", session, session["llm_config"]))
        assert session["code_scanner_state"] == STATE_REVIEW_COMPLETE
        assert session["code_review"] == {
            "code_review": {"schema_version": 1, "is_software_project": True}
        }

    def test_non_review_response_stays_in_progress(self) -> None:
        session = make_session(
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
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
        session = make_session(
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        del session["code_scanner_messages"]
        with mock_litellm_stream("Ok"):
            collect(code_scanner.run("Hi", session, session["llm_config"]))
        assert "code_scanner_messages" in session

    def test_brownfield_display_shows_existing_review_without_llm(self) -> None:
        review = {
            "code_review": {"is_software_project": True, "project_type": "CLI tool"}
        }
        session = make_session(
            code_review=review,
            code_scanner_state=STATE_REVIEW_COMPLETE,
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(code_scanner.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "Code Review Complete" in output
        assert "CLI tool" in output
        assert session["code_scanner_artifact_msg_count"] == len(
            session["code_scanner_messages"]
        )

    def test_brownfield_display_heals_stale_persisted_content(self) -> None:
        # Simulate a session persisted from before _format_review_as_text was
        # fixed: msgs already has the synthetic pair but the assistant content
        # was generated from notes-as-string (single-char bullets).
        review = {"code_review": {"notes": "Directory is flat"}}
        stale_content = (
            "**Code Review Complete**\n\n"
            "**Notable Observations:**\n- D\n- i\n"
        )
        session = make_session(
            code_review=review,
            code_scanner_state=STATE_REVIEW_COMPLETE,
            code_scanner_artifact_msg_count=2,
            code_scanner_messages=[
                {"role": "user", "content": "[Spec4: displaying existing code review]"},
                {"role": "assistant", "content": stale_content},
            ],
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(code_scanner.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "- Directory is flat" in output
        assert "- D\n" not in output

    def test_brownfield_display_replay_on_reentry(self) -> None:
        review = {
            "code_review": {"is_software_project": True, "project_type": "web app"}
        }
        session = make_session(
            code_review=review,
            code_scanner_state=STATE_REVIEW_COMPLETE,
        )
        # First init: brownfield display
        with patch("spec4.llm.litellm.completion"):
            collect(code_scanner.run(None, session, session["llm_config"]))
        # Second init: replay (no LLM call)
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output2 = collect(code_scanner.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "Code Review Complete" in output2

    def test_format_review_notes_as_string_renders_as_single_bullet(self) -> None:
        from spec4.agents.code_scanner import _format_review_as_text

        review = {"code_review": {"notes": "Directory is flat, no CI found"}}
        result = _format_review_as_text(review)
        assert "- Directory is flat, no CI found" in result
        assert "- D\n" not in result

    def test_format_review_langs_as_string_renders_correctly(self) -> None:
        from spec4.agents.code_scanner import _format_review_as_text

        review = {"code_review": {"languages": "Python", "frameworks": []}}
        result = _format_review_as_text(review)
        assert "Python" in result
        assert "- P\n" not in result

    def test_format_review_renders_schema_v1_fields(self) -> None:
        from spec4.agents.code_scanner import _format_review_as_text

        review = {
            "code_review": {
                "schema_version": 1,
                "is_software_project": True,
                "project_type": "web application",
                "existing_self_description": {
                    "text": "A planning tool.",
                    "source": "README.md",
                },
                "architecture": {
                    "summary": "Layered Dash app.",
                    "pattern": "layered",
                    "inferred_from": "src/spec4/app.py",
                },
                "languages": [{"name": "Python", "source": "pyproject.toml"}],
                "frameworks": [{"name": "Dash", "source": "pyproject.toml"}],
                "runtime_versions": {"python": ">=3.12"},
                "build_system": {"tool": "uv", "manifest": "pyproject.toml"},
                "dependencies": [
                    {"name": "dash", "purpose": "Web UI", "source": "pyproject.toml"}
                ],
                "commands": {"test": "make test", "lint": "make lint"},
                "entrypoints": {
                    "main": "src/spec4/app.py",
                    "wsgi_app": "spec4.app:server",
                },
                "directory_map": [
                    {"path": "src/spec4/agents/", "role": "pipeline agents"}
                ],
                "ui_summary": {
                    "has_ui": True,
                    "kind": "spa",
                    "framework": "Dash",
                },
                "coding_style": {
                    "linter": {"value": "ruff", "source": "pyproject.toml"},
                    "naming_conventions": {
                        "functions": {
                            "value": "snake_case",
                            "inferred_from": "src/spec4/session.py",
                        }
                    },
                },
                "notes": {
                    "test_coverage": {"has_tests": True, "framework": "pytest"},
                    "ci_cd": {"present": False},
                    "change_risks": [
                        {
                            "area": "session",
                            "risk": "shared mutation",
                            "mitigation_hint": "use {**session, key: val}",
                        }
                    ],
                    "other_notes": ["py.typed marker present"],
                },
            }
        }
        out = _format_review_as_text(review)
        assert "**Project Type:** web application" in out
        assert "**Existing self-description:** A planning tool." in out
        assert "_(from README.md)_" in out
        assert "layered" in out
        assert "Python (source: pyproject.toml)" in out
        assert "Dash (source: pyproject.toml)" in out
        assert "python: >=3.12" in out
        assert "uv (pyproject.toml)" in out
        assert "dash" in out and "Web UI" in out
        assert "test: `make test`" in out
        assert "main: `src/spec4/app.py`" in out
        assert "wsgi app: `spec4.app:server`" in out
        assert "`src/spec4/agents/`" in out and "pipeline agents" in out
        assert "spa" in out and "Dash" in out
        assert "ruff" in out
        assert "snake_case" in out
        assert "**Test Coverage:**" in out and "pytest" in out
        assert "**CI/CD:** none detected" in out
        assert "**Change Risks:**" in out
        assert "Mitigation: use {**session, key: val}" in out
        assert "py.typed marker present" in out
        assert "Continue to Brainstormer" in out

    def test_format_review_renders_empty_project(self) -> None:
        from spec4.agents.code_scanner import _format_review_as_text

        review = {
            "code_review": {
                "schema_version": 1,
                "is_software_project": False,
                "summary": "Directory is empty.",
            }
        }
        out = _format_review_as_text(review)
        assert "Code Review Complete" in out
        assert "Directory is empty." in out
        assert "Brainstormer" in out

    def test_format_review_renders_protocols_implemented(self) -> None:
        from spec4.agents.code_scanner import _format_review_as_text

        review = {
            "code_review": {
                "is_software_project": True,
                "protocols_implemented": [
                    {
                        "name": "A2A Protocol",
                        "version": "1.0",
                        "location": "arrg/a2a/",
                        "source": "README.md",
                    },
                    {
                        "name": "MCP",
                        "version": "2025-11-25",
                        "location": "arrg/mcp/",
                        "source": "arrg/mcp/server.py",
                    },
                ],
            }
        }
        out = _format_review_as_text(review)
        assert "**Protocols Implemented:**" in out
        assert "A2A Protocol v1.0" in out
        assert "`arrg/a2a/`" in out
        assert "MCP v2025-11-25" in out
        assert "`arrg/mcp/`" in out
        # Absent → heading omitted.
        bare = {"code_review": {"is_software_project": True, "project_type": "CLI"}}
        assert "**Protocols Implemented:**" not in _format_review_as_text(bare)

    def test_format_review_renders_ai_capabilities(self) -> None:
        from spec4.agents.code_scanner import _format_review_as_text

        review = {
            "code_review": {
                "is_software_project": True,
                "ai_capabilities": [
                    {
                        "name": "anthropic",
                        "kind": "llm_api",
                        "description": "Claude client drafting replies",
                        "location": "src/app/ai/reply_drafter.py",
                        "source": "pyproject.toml",
                    },
                    {"name": "chromadb"},
                ],
            }
        }
        out = _format_review_as_text(review)
        assert "**AI Capabilities:**" in out
        assert "anthropic [llm_api]" in out
        assert "Claude client drafting replies" in out
        assert "`src/app/ai/reply_drafter.py`" in out
        assert "- chromadb" in out
        # Absent → heading omitted.
        bare = {"code_review": {"is_software_project": True, "project_type": "CLI"}}
        assert "**AI Capabilities:**" not in _format_review_as_text(bare)

    def test_system_prompt_documents_ai_capabilities(self) -> None:
        from spec4.agents.code_scanner import SYSTEM_PROMPT

        # All three prompt surfaces: the JSON exemplar / field-rule bullet
        # (schema key) and the draft-section list (display name).
        assert "ai_capabilities" in SYSTEM_PROMPT
        assert "AI Capabilities" in SYSTEM_PROMPT
        assert "agent_framework" in SYSTEM_PROMPT

    def test_format_review_renders_persistence(self) -> None:
        from spec4.agents.code_scanner import _format_review_as_text

        review = {
            "code_review": {
                "is_software_project": True,
                "persistence": {
                    "databases": [
                        {"engine": "PostgreSQL", "role": "primary"},
                        {"engine": "Redis", "role": "cache"},
                    ],
                    "orm": {"name": "SQLAlchemy", "source": "pyproject.toml"},
                    "migration_tool": {"name": "Alembic"},
                    "migrations_path": "migrations/",
                },
            }
        }
        out = _format_review_as_text(review)
        assert "**Persistence:**" in out
        assert "PostgreSQL (primary)" in out
        assert "Redis (cache)" in out
        assert "ORM: SQLAlchemy" in out
        assert "migrations: Alembic" in out
        assert "`migrations/`" in out
        # Absent → heading omitted.
        bare = {"code_review": {"is_software_project": True, "project_type": "CLI"}}
        assert "**Persistence:**" not in _format_review_as_text(bare)

    def test_format_review_renders_env_vars(self) -> None:
        from spec4.agents.code_scanner import _format_review_as_text

        review = {
            "code_review": {
                "is_software_project": True,
                "env_vars": [
                    {
                        "name": "DATABASE_URL",
                        "purpose": "Postgres connection string",
                        "required": True,
                    },
                    {"name": "DASH_DEBUG", "required": False},
                    {"name": "API_KEY"},
                ],
            }
        }
        out = _format_review_as_text(review)
        assert "**Environment Variables:**" in out
        assert "`DATABASE_URL`" in out and "(required)" in out
        assert "Postgres connection string" in out
        assert "`DASH_DEBUG`" in out and "(optional)" in out
        assert "`API_KEY`" in out

    def test_format_review_env_vars_never_leak_values(self) -> None:
        """Even if a malformed entry slips a value in, the renderer ignores it."""
        from spec4.agents.code_scanner import _format_review_as_text

        review = {
            "code_review": {
                "is_software_project": True,
                "env_vars": [{"name": "SECRET_KEY", "value": "leaked-secret"}],
            }
        }
        out = _format_review_as_text(review)
        assert "`SECRET_KEY`" in out
        assert "leaked-secret" not in out

    def test_format_review_renders_deployment(self) -> None:
        from spec4.agents.code_scanner import _format_review_as_text

        review = {
            "code_review": {
                "is_software_project": True,
                "deployment": {
                    "containerization": {
                        "tool": "docker",
                        "dockerfile_path": "Dockerfile",
                        "base_image": "python:3.12-slim",
                    },
                    "paas": {"platform": "fly.io", "config_path": "fly.toml"},
                    "iac": {"tool": "terraform", "path": "infra/"},
                },
            }
        }
        out = _format_review_as_text(review)
        assert "**Deployment:**" in out
        assert "docker" in out
        assert "`Dockerfile`" in out
        assert "base: `python:3.12-slim`" in out
        assert "PaaS: fly.io" in out
        assert "`fly.toml`" in out
        assert "IaC: terraform" in out
        assert "`infra/`" in out
        # Absent → heading omitted.
        bare = {"code_review": {"is_software_project": True}}
        assert "**Deployment:**" not in _format_review_as_text(bare)

    def test_format_review_renders_api_surface(self) -> None:
        from spec4.agents.code_scanner import _format_review_as_text

        review = {
            "code_review": {
                "is_software_project": True,
                "api_surface": [
                    {
                        "protocol": "http",
                        "path_or_method": "GET /users/:id",
                        "handler": "users.get_user",
                    },
                    {
                        "protocol": "grpc",
                        "path_or_method": "UserService.GetUser",
                        "summary": "Fetch a user by ID",
                    },
                ],
            }
        }
        out = _format_review_as_text(review)
        assert "**API Surface:**" in out
        assert "[http]" in out and "GET /users/:id" in out
        assert "users.get_user" in out
        assert "[grpc]" in out and "UserService.GetUser" in out
        assert "Fetch a user by ID" in out

    def test_format_review_renders_auth(self) -> None:
        from spec4.agents.code_scanner import _format_review_as_text

        review = {
            "code_review": {
                "is_software_project": True,
                "auth": {
                    "model": "oauth",
                    "provider": "Auth0",
                    "library": "authlib",
                },
            }
        }
        out = _format_review_as_text(review)
        assert "**Authentication:**" in out
        assert "oauth" in out
        assert "Auth0" in out
        assert "authlib" in out
        # Absent → heading omitted.
        bare = {"code_review": {"is_software_project": True}}
        assert "**Authentication:**" not in _format_review_as_text(bare)

    def test_format_review_test_coverage_summary_preferred_over_lists(self) -> None:
        from spec4.agents.code_scanner import _format_review_as_text

        review = {
            "code_review": {
                "is_software_project": True,
                "notes": {
                    "test_coverage": {
                        "has_tests": True,
                        "framework": "pytest",
                        "coverage_summary": "10 modules covered; UI layer uncovered",
                        "covered_modules": ["should_be_ignored"],
                    }
                },
            }
        }
        out = _format_review_as_text(review)
        assert "10 modules covered; UI layer uncovered" in out
        assert "should_be_ignored" not in out

    def test_format_review_ui_summary_has_ui_false_shows_none(self) -> None:
        from spec4.agents.code_scanner import _format_review_as_text

        review = {
            "code_review": {
                "is_software_project": True,
                "ui_summary": {"has_ui": False, "kind": "none"},
            }
        }
        out = _format_review_as_text(review)
        assert "**UI:** none" in out

    def test_update_mode_seeds_with_prior_review(self) -> None:
        from spec4.agents.code_scanner import _build_update_scan_seed

        prior = {"code_review": {"is_software_project": True, "project_type": "CLI"}}
        seed = _build_update_scan_seed("/tmp/does-not-matter", prior)
        assert "Update mode instructions" in seed
        assert "Prior code review on disk" in seed
        assert "project_type" in seed
        assert "Added / Removed / Changed" in seed

    def test_rescan_enters_update_mode_when_review_exists(self) -> None:
        # Simulate the state immediately after on_rescan_project: prior review
        # is kept in session but state and msgs are reset.
        review = {"code_review": {"is_software_project": True, "project_type": "web"}}
        session = make_session(
            code_review=review,
            code_scanner_state=STATE_IN_PROGRESS,
            code_scanner_messages=[],
            working_dir="/tmp/not-real-but-not-empty",
        )
        with mock_litellm_stream("(LLM update response)"):
            collect(code_scanner.run(None, session, session["llm_config"]))
        seed = session["code_scanner_messages"][0]["content"]
        assert "Update mode" in seed
        assert "Prior code review on disk" in seed


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

    def test_readme_content_included_under_labeled_section(self, tmp_path: Any) -> None:
        from spec4.agents.code_scanner import _gather_project_context

        (tmp_path / "README.md").write_text("# My Project\n\nA cool app.\n")
        result = _gather_project_context(str(tmp_path))
        assert "### README Excerpt" in result
        assert "My Project" in result

    def test_source_file_sample_included(self, tmp_path: Any) -> None:
        from spec4.agents.code_scanner import _gather_project_context

        (tmp_path / "app.py").write_text("def main():\n    pass\n")
        result = _gather_project_context(str(tmp_path))
        assert "def main" in result

    def test_ci_workflow_files_detected(self, tmp_path: Any) -> None:
        from spec4.agents.code_scanner import _gather_project_context

        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: CI\non: push\n")
        # need at least one non-CI file or _gather returns the empty placeholder
        (tmp_path / "main.py").write_text("print('x')")
        result = _gather_project_context(str(tmp_path))
        assert "### CI / Workflow Files" in result
        assert "ci.yml" in result

    def test_dockerfile_detected_as_deployment_signal(self, tmp_path: Any) -> None:
        from spec4.agents.code_scanner import _gather_project_context

        (tmp_path / "Dockerfile").write_text("FROM python:3.12\n")
        (tmp_path / "main.py").write_text("print('x')")
        result = _gather_project_context(str(tmp_path))
        assert "### Deployment Signals" in result
        assert "Dockerfile" in result

    def test_terraform_directory_detected_as_deployment_signal(
        self, tmp_path: Any
    ) -> None:
        from spec4.agents.code_scanner import _gather_project_context

        tf_dir = tmp_path / "terraform"
        tf_dir.mkdir()
        (tf_dir / "main.tf").write_text('resource "null_resource" "x" {}\n')
        (tmp_path / "main.py").write_text("print('x')")
        result = _gather_project_context(str(tmp_path))
        assert "Terraform configuration detected" in result

    def test_entrypoint_files_prioritized_in_source_samples(
        self, tmp_path: Any
    ) -> None:
        from spec4.agents.code_scanner import _gather_project_context

        # Create many alphabetically-earlier files so plain-alpha ordering
        # would push 'main.py' past the 8-file priority cutoff.
        for i in range(10):
            (tmp_path / f"a_aux_{i}.py").write_text(f"# helper {i}\n")
        (tmp_path / "main.py").write_text("def main():\n    pass\n")
        result = _gather_project_context(str(tmp_path))
        # main.py should be sampled (and labeled as an entrypoint candidate)
        assert "main.py" in result
        assert "entrypoint candidate" in result


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
        block = '```json\n' + """{
  "phase_number": 1,
  "phase_title": "Steel Thread",
  "verification": "1. Run pytest
2. Check coverage
3. Confirm CI green",
  "risk_assessment": {"potential_bottlenecks": "1. Missing env vars
2. Port conflicts", "mitigation_strategy": "Validate at startup."}
}""" + '\n```'
        phases = _extract_phases(block)
        assert len(phases) == 1
        assert "\n" in phases[0]["verification"]

    def test_extract_phases_tolerates_trailing_extra_brace(self) -> None:
        from spec4.agents.phaser import _extract_phases

        # The real pathology: model appends an extra } after the object,
        # which causes strict json.loads to raise "Extra data".
        block = (
            '```json\n'
            '{"phase_number": 2, "phase_title": "Integration"}\n'
            '}\n'
            '```'
        )
        phases = _extract_phases(block)
        assert len(phases) == 1

    def test_extract_phases_recovers_real_world_multiblock(self) -> None:
        from spec4.agents.phaser import _extract_phases

        # Two blocks each with both pathologies: literal newlines AND trailing }.
        block1 = '```json\n' + """{
  "phase_number": 1,
  "phase_title": "Phase One",
  "verification": "1. Run tests
2. Check logs"
}
}""" + '\n```'
        block2 = '```json\n' + """{
  "phase_number": 2,
  "phase_title": "Phase Two",
  "verification": "1. Deploy
2. Smoke test"
}
}""" + '\n```'
        phases = _extract_phases(block1 + "\n\n" + block2)
        assert len(phases) == 2
        assert phases[0]["phase_number"] == 1
        assert phases[1]["phase_number"] == 2

    def test_extract_phases_tolerates_nested_code_fence(self) -> None:
        from spec4.agents.phaser import _extract_phases

        # A phase whose instructions contain a fenced ```bash block inside
        # a string value. A ```json-fence regex would prematurely terminate.
        block = (
            '```json\n'
            '{"phase_number": 1, "phase_title": "Setup", '
            '"instructions": "Run:\\n```bash\\nuv sync\\n```\\nThen start."}\n'
            '```'
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
            ']}\n```'
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
            ']}}\n```'
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
            m["content"] for m in sent
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
        assert all(
            m["content"] != "approved" for m in sent if m["role"] == "user"
        )


# ---------------------------------------------------------------------------
# _load_design_manifest (stack_advisor)
# ---------------------------------------------------------------------------


class TestLoadDesignManifest:
    """StackAdvisor reads Designer's manifest, never the visual mock (D-SC5c)."""

    def test_returns_none_when_absent(self, tmp_path: Any) -> None:
        from spec4.agents._utils import _load_design_manifest

        assert _load_design_manifest(tmp_path) is None
        assert _load_design_manifest(None) is None

    def test_returns_none_when_malformed(self, tmp_path: Any) -> None:
        from spec4.agents._utils import _load_design_manifest

        (tmp_path / "manifest.json").write_text("{not json")
        assert _load_design_manifest(tmp_path) is None

    def test_reads_manifest(self, tmp_path: Any) -> None:
        from spec4.agents._utils import _load_design_manifest

        (tmp_path / "manifest.json").write_text('{"name": "X"}')
        assert _load_design_manifest(tmp_path) == {"name": "X"}

    def test_mock_is_never_read(self, tmp_path: Any) -> None:
        # the mock is the coding agent's reference, handed on by path; a stack
        # choice must not depend on its markup, and must not pull it into context
        from spec4.agents._utils import _load_design_manifest

        (tmp_path / "mock.html").write_text("<html>marker-should-not-appear</html>")
        assert _load_design_manifest(tmp_path) is None


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
# Deployer return-with-existing-plan behavior
# ---------------------------------------------------------------------------


class TestDeployerExistingInfra:
    """Deployer pulls deployment-relevant code_review fields into its seed
    so it can reference existing infra rather than re-deciding from scratch."""

    def test_build_existing_infra_block_emits_only_present_fields(self) -> None:
        from spec4.agents.deployer import _build_existing_infra_block

        code_review = {
            "code_review": {
                "is_software_project": True,
                "deployment": {
                    "containerization": {
                        "tool": "docker",
                        "dockerfile_path": "Dockerfile",
                    },
                },
                "env_vars": [{"name": "DATABASE_URL", "required": True}],
                # persistence and auth absent
            }
        }
        block = _build_existing_infra_block(code_review)
        assert "deployment-relevant excerpt" in block
        # Inspect the JSON body, not the prose instructions (which mention
        # the field names by reference).
        json_body = block.split("```json", 1)[1].split("```", 1)[0]
        assert '"deployment"' in json_body
        assert '"env_vars"' in json_body
        assert "DATABASE_URL" in json_body
        assert '"persistence"' not in json_body
        assert '"auth"' not in json_body
        # Names-only reminder lives in the prose.
        assert "values live in the developer" in block.lower()

    def test_build_existing_infra_block_empty_when_nothing_relevant(self) -> None:
        from spec4.agents.deployer import _build_existing_infra_block

        # Code review present but no deployment-relevant blocks.
        cr = {
            "code_review": {
                "is_software_project": True,
                "project_type": "CLI tool",
                "languages": [{"name": "Python"}],
            }
        }
        assert _build_existing_infra_block(cr) == ""

    def test_build_existing_infra_block_empty_when_no_review(self) -> None:
        from spec4.agents.deployer import _build_existing_infra_block

        assert _build_existing_infra_block({}) == ""

    def test_build_existing_infra_block_accepts_unwrapped_form(self) -> None:
        """Works whether code_review is wrapped in the LLM envelope or not."""
        from spec4.agents.deployer import _build_existing_infra_block

        unwrapped = {
            "is_software_project": True,
            "auth": {"model": "jwt", "library": "authlib"},
        }
        block = _build_existing_infra_block(unwrapped)
        assert "auth" in block
        assert "jwt" in block

    def test_fresh_start_seed_includes_infra_excerpt_when_present(self) -> None:
        session = make_session(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            _deployer_readme_optin_done=True,
            code_review={
                "code_review": {
                    "is_software_project": True,
                    "deployment": {
                        "containerization": {
                            "tool": "docker",
                            "dockerfile_path": "Dockerfile",
                        },
                    },
                    "env_vars": [{"name": "API_KEY", "required": True}],
                }
            },
        )
        with mock_litellm_stream("Hi! I'm Deployer."):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        assert "deployment-relevant excerpt" in seed
        assert "API_KEY" in seed
        assert "Dockerfile" in seed

    def test_fresh_start_seed_omits_infra_excerpt_when_review_lacks_fields(
        self,
    ) -> None:
        session = make_session(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            _deployer_readme_optin_done=True,
            code_review={
                "code_review": {
                    "is_software_project": True,
                    "project_type": "library",
                }
            },
        )
        with mock_litellm_stream("Hi! I'm Deployer."):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        assert "deployment-relevant excerpt" not in seed


class TestDeployerExistingPlanGuard:
    """A deployment-plan.md on disk must not be replaced silently when the
    user returns — including in a fresh browser with no in-memory state."""

    def _returning_session(self, **overrides: Any) -> dict[str, Any]:
        # Mirrors what session._load_working_dir produces when an on-disk
        # deployment-plan.md is detected: state is COMPLETE, the "existed"
        # flag is True, the in-memory plan markdown is None, no chat history.
        defaults: dict[str, Any] = dict(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            stack_statement={"name": "App"},
            deployer_state=STATE_DEPLOYER_COMPLETE,
            deployer_messages=[],
            _deployer_plan_existed=True,
            _deployer_plan_markdown=None,
            _deployer_pending_plan=False,
        )
        defaults.update(overrides)
        return make_session(**defaults)

    def test_fresh_start_seed_acknowledges_existing_plan(self, tmp_path) -> None:
        # The agent's first turn must inform the developer that an existing
        # plan was found and ask how they want to proceed, rather than the
        # generic "which coding agent are you using" intro. Mirror what
        # _load_working_dir produces: a working_dir with an on-disk plan, and
        # the _deployer_plan_existed flag set from having detected it.
        from spec4 import project_manager

        plan = "# Existing Deployment Plan\n\n## Steps\n\nDeploy the thing."
        project_manager.save_deployment_plan(str(tmp_path), plan, 0)
        session = self._returning_session(working_dir=str(tmp_path), phase_version=0)
        with mock_litellm_stream("Hi! I see you have an existing plan…"):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        assert "existing" in seed.lower() or "previous session" in seed.lower()
        assert "deployment-plan.md" in seed
        # The seed offers concrete options to the user.
        assert "1." in seed and "2." in seed and "3." in seed
        # The loaded plan's contents are embedded so the agent need not ask the
        # developer to paste the file (the re-entry seed behavior).
        assert "Existing Deployment Plan" in seed

    def test_fresh_start_seed_unchanged_when_no_existing_plan(self) -> None:
        # Greenfield: the agent uses its original intro, asking which coding
        # agent the developer plans to use.
        session = make_session(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            _deployer_plan_existed=False,
            _deployer_readme_optin_done=True,
        )
        with mock_litellm_stream("Hi! I'm Deployer."):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        assert "coding agent" in seed.lower()
        # And does NOT mention an existing on-disk plan.
        assert "deployment-plan.md" not in seed

    def test_no_reply_clears_pending_markdown(self) -> None:
        # The previous turn produced a candidate plan; user replies "no".
        session = self._returning_session(
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {
                    "role": "assistant",
                    "content": "## Deployment Steps … replace? (yes/no)",
                },
            ],
            _deployer_plan_markdown="# Plan\n\n## Deployment Steps\n…",
            _deployer_pending_plan=True,
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(
                deployer.run("no, keep it", session, session["llm_config"])
            )
        # No LLM call — the agent short-circuits with the keep_msg.
        mock_llm.assert_not_called()
        assert "kept" in output.lower() or "existing" in output.lower()
        # Critical: the staged markdown is cleared so _persist_artifacts
        # cannot save it on a subsequent turn.
        assert session["_deployer_plan_markdown"] is None
        assert session["_deployer_pending_plan"] is False

    def test_yes_reply_preserves_markdown_for_persist(self) -> None:
        plan = "# Plan\n\n## Deployment Steps\n\n### 1. Build\n…"
        session = self._returning_session(
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {
                    "role": "assistant",
                    "content": plan + "\n\n…replace? (yes/no)",
                },
            ],
            _deployer_plan_markdown=plan,
            _deployer_pending_plan=True,
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            collect(deployer.run("yes", session, session["llm_config"]))
        mock_llm.assert_not_called()
        # Markdown is still set so _persist_artifacts can write it.
        assert session["_deployer_plan_markdown"] == plan
        assert session["deployer_state"] == STATE_DEPLOYER_COMPLETE
        assert session["_deployer_pending_plan"] is False

    def test_new_plan_on_returning_user_triggers_confirmation(self) -> None:
        # Returning user with existing plan; chat history has built up and
        # the LLM now produces a fresh plan. The confirmation prompt must
        # fire — the new plan must NOT be persisted before approval.
        session = self._returning_session(
            deployer_messages=[
                {"role": "user", "content": "let's revise the plan"},
                {"role": "assistant", "content": "OK, what changes?"},
                {"role": "user", "content": "use Cloud Run instead"},
            ],
        )
        new_plan = (
            "# Deployment Plan\n\n## Target\n- **Provider:** GCP\n\n"
            "## Deployment Steps\n\n### 1. Build image\n…"
        )
        with mock_litellm_stream(new_plan):
            collect(deployer.run("use Cloud Run instead", session,
                                 session["llm_config"]))
        assert session["_deployer_plan_markdown"] == new_plan
        assert session["_deployer_pending_plan"] is True
        # State was already COMPLETE on entry but the agent does not "re-set"
        # it — the affirmative branch on the next turn is what locks in the
        # save.
        last_assistant = session["deployer_messages"][-1]["content"]
        assert "yes" in last_assistant.lower() and "no" in last_assistant.lower()


# ---------------------------------------------------------------------------
# code_review JSON Schema tests
# ---------------------------------------------------------------------------


class TestCodeReviewSchemaValidation:
    """Direct tests of the validate_code_review() schema check."""

    def test_minimal_valid_review_passes(self) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        data = {"code_review": {"schema_version": 1, "is_software_project": True}}
        assert validate_code_review(data) == []

    def test_empty_project_review_passes(self) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        data = {
            "code_review": {
                "schema_version": 1,
                "is_software_project": False,
                "summary": "Directory contained only a CNAME file.",
            }
        }
        assert validate_code_review(data) == []

    def test_valid_ui_kind_enum_passes(self) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        for kind in ("spa", "mpa", "mobile", "desktop", "tui", "none"):
            data = {
                "code_review": {
                    "schema_version": 1,
                    "is_software_project": True,
                    "ui_summary": {"has_ui": kind != "none", "kind": kind},
                }
            }
            assert validate_code_review(data) == [], f"kind={kind} should pass"

    def test_protocols_implemented_entry_validates(self) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        data = {
            "code_review": {
                "schema_version": 1,
                "is_software_project": True,
                "protocols_implemented": [
                    {
                        "name": "MCP",
                        "version": "2025-11-25",
                        "location": "arrg/mcp/",
                        "source": "README.md",
                    }
                ],
            }
        }
        assert validate_code_review(data) == []

    def test_persistence_block_validates(self) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        data = {
            "code_review": {
                "schema_version": 1,
                "is_software_project": True,
                "persistence": {
                    "databases": [
                        {
                            "engine": "PostgreSQL",
                            "name": "app",
                            "role": "primary",
                            "source": "docker-compose.yml",
                        },
                        {"engine": "Redis", "role": "cache"},
                    ],
                    "orm": {"name": "SQLAlchemy", "source": "pyproject.toml"},
                    "migration_tool": {"name": "Alembic", "source": "pyproject.toml"},
                    "migrations_path": "migrations/",
                },
            }
        }
        assert validate_code_review(data) == []

    def test_env_vars_block_validates(self) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        data = {
            "code_review": {
                "schema_version": 1,
                "is_software_project": True,
                "env_vars": [
                    {
                        "name": "DATABASE_URL",
                        "purpose": "Primary Postgres connection string",
                        "required": True,
                        "source": "src/spec4/db.py",
                    },
                    {"name": "DASH_DEBUG", "purpose": "Enable Dash hot reload"},
                ],
            }
        }
        assert validate_code_review(data) == []

    def test_deployment_block_validates(self) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        data = {
            "code_review": {
                "schema_version": 1,
                "is_software_project": True,
                "deployment": {
                    "containerization": {
                        "tool": "docker",
                        "dockerfile_path": "Dockerfile",
                        "compose_path": "docker-compose.yml",
                        "base_image": "python:3.12-slim",
                        "source": "Dockerfile",
                    },
                    "orchestration": {
                        "tool": "kubernetes",
                        "manifests_path": "k8s/",
                        "source": "k8s/deployment.yaml",
                    },
                    "paas": {
                        "platform": "fly.io",
                        "config_path": "fly.toml",
                        "source": "fly.toml",
                    },
                    "iac": {
                        "tool": "terraform",
                        "path": "infra/",
                        "source": "infra/main.tf",
                    },
                },
            }
        }
        assert validate_code_review(data) == []

    def test_api_surface_block_validates(self) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        data = {
            "code_review": {
                "schema_version": 1,
                "is_software_project": True,
                "api_surface": [
                    {
                        "protocol": "http",
                        "path_or_method": "GET /users/:id",
                        "handler": "users.get_user",
                        "source": "src/app/routes.py",
                    },
                    {
                        "protocol": "grpc",
                        "path_or_method": "UserService.GetUser",
                        "summary": "Fetch a user by ID",
                    },
                    {
                        "protocol": "websocket",
                        "path_or_method": "/ws/stream",
                    },
                ],
            }
        }
        assert validate_code_review(data) == []

    def test_auth_block_validates(self) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        models = (
            "session", "jwt", "oauth", "sso",
            "api_key", "basic", "mtls", "none", "other",
        )
        for model in models:
            data = {
                "code_review": {
                    "schema_version": 1,
                    "is_software_project": True,
                    "auth": {
                        "model": model,
                        "provider": "Auth0" if model in ("oauth", "sso") else "",
                        "library": "authlib",
                        "source": "src/app/auth.py",
                    },
                }
            }
            assert validate_code_review(data) == [], f"auth.model={model} should pass"

    def test_full_realistic_review_passes(self) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        data = {
            "code_review": {
                "schema_version": 1,
                "is_software_project": True,
                "project_type": "web application — Dash SPA",
                "existing_self_description": {
                    "text": "Spec4 is an AI-assisted project planner.",
                    "source": "README.md",
                },
                "architecture": {
                    "summary": "layered Dash app",
                    "pattern": "MVC-ish",
                    "inferred_from": "src/spec4/app.py",
                },
                "languages": [{"name": "Python", "source": "pyproject.toml"}],
                "frameworks": [{"name": "Dash", "source": "pyproject.toml"}],
                "protocols_implemented": [
                    {"name": "MCP", "version": "2025-11-25", "location": "src/spec4/"}
                ],
                "runtime_versions": {"python": ">=3.12"},
                "build_system": {
                    "tool": "uv",
                    "manifest": "pyproject.toml",
                    "build_backend": "uv_build",
                },
                "dependencies": [
                    {"name": "dash", "purpose": "Web UI", "source": "pyproject.toml"}
                ],
                "commands": {
                    "test": "uv run pytest",
                    "lint": "uv run ruff check src/ tests/",
                    "typecheck": "uv run mypy src/",
                    "run": "uv run python src/spec4/app.py",
                },
                "entrypoints": {
                    "main": "src/spec4/app.py",
                    "wsgi_app": "src/spec4/app.py:server",
                    "cli_script": "spec4 = spec4.app:main",
                },
                "directory_map": [
                    {"path": "src/spec4/agents/", "role": "pipeline LLM agents"}
                ],
                "ui_summary": {
                    "has_ui": True,
                    "kind": "spa",
                    "framework": "Dash + Mantine",
                    "styling": "Mantine + custom CSS",
                    "entry_files": ["src/spec4/app.py"],
                },
                "coding_style": {
                    "linter": {"value": "ruff", "source": "pyproject.toml"},
                    "line_length": {"value": 88, "source": "pyproject.toml"},
                    "indentation": "4 spaces",
                    "naming_conventions": {
                        "functions": {
                            "value": "snake_case",
                            "inferred_from": "src/spec4/session.py",
                        }
                    },
                },
                "persistence": {
                    "databases": [
                        {
                            "engine": "PostgreSQL",
                            "role": "primary",
                            "source": "fly.toml",
                        },
                    ],
                    "orm": {"name": "SQLAlchemy", "source": "pyproject.toml"},
                    "migration_tool": {"name": "Alembic", "source": "pyproject.toml"},
                    "migrations_path": "migrations/",
                },
                "env_vars": [
                    {
                        "name": "DATABASE_URL",
                        "purpose": "Postgres connection string",
                        "required": True,
                        "source": "fly.toml",
                    },
                ],
                "deployment": {
                    "containerization": {
                        "tool": "docker",
                        "dockerfile_path": "Dockerfile",
                        "base_image": "python:3.12-slim",
                        "source": "Dockerfile",
                    },
                    "paas": {
                        "platform": "fly.io",
                        "config_path": "fly.toml",
                        "source": "fly.toml",
                    },
                },
                "api_surface": [
                    {
                        "protocol": "http",
                        "path_or_method": "POST /api/agent/run",
                        "handler": "spec4.app.run_agent",
                        "source": "src/spec4/app.py",
                    },
                ],
                "auth": {
                    "model": "api_key",
                    "library": "custom",
                    "inferred_from": "src/spec4/providers.py",
                },
                "notes": {
                    "test_coverage": {
                        "has_tests": True,
                        "framework": "pytest",
                        "coverage_summary": "broad coverage of agents and utils",
                    },
                    "ci_cd": {"present": False, "type": None, "path": None},
                    "other_notes": ["py.typed marker present"],
                },
            }
        }
        assert validate_code_review(data) == []

    def test_ai_capabilities_block_validates(self) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        data = {
            "code_review": {
                "schema_version": 1,
                "is_software_project": True,
                "ai_capabilities": [
                    {
                        "name": "anthropic",
                        "kind": "llm_api",
                        "description": "Claude client drafting support replies",
                        "location": "src/app/ai/reply_drafter.py",
                        "source": "pyproject.toml",
                    },
                    {
                        "name": "chromadb",
                        "kind": "vector_store",
                        "description": "Vector store of embedded help articles",
                        "location": "src/app/ai/retrieval.py",
                        "inferred_from": "src/app/ai/retrieval.py",
                    },
                ],
            }
        }
        assert validate_code_review(data) == []

    def test_retry_message_lists_ai_capability_kinds(self) -> None:
        from spec4.agents._code_review_schema import (
            format_validation_errors_for_retry,
        )

        msg = format_validation_errors_for_retry(["x"])
        assert "ai_capabilities" in msg
        assert "agent_framework" in msg

    # --- Failure cases, grouped by the jsonschema mechanism each exercises ---
    # Each parametrize case is one section asserting the SAME schema feature
    # (closed shape / required / enum / const), so coverage is preserved while
    # the method count collapses.

    @pytest.mark.parametrize(
        "section, value, bad_key",
        [
            (
                "commands",
                {"test": "pytest", "run_dashboard": "arrg dashboard"},
                "run_dashboard",
            ),
            (
                "entrypoints",
                {"main": "spec4/app.py", "mcp_server": "arrg/server.py"},
                "mcp_server",
            ),
            ("notes", {"miscellaneous_thoughts": ["..."]}, "miscellaneous_thoughts"),
            ("persistence", {"cache_layer": "Redis"}, "cache_layer"),
            ("deployment", {"edge_cdn": "cloudflare"}, "edge_cdn"),
            # env_vars `value` and auth `secret_value` are security boundaries:
            # the closed shape forbids leaking secret values into the artifact.
            (
                "env_vars",
                [{"name": "DATABASE_URL", "value": "postgres://leaked"}],
                "value",
            ),
            ("auth", {"model": "jwt", "secret_value": "super-secret"}, "secret_value"),
            (
                "ai_capabilities",
                [{"name": "openai", "vendor": "OpenAI"}],
                "vendor",
            ),
        ],
    )
    def test_closed_shape_rejects_custom_key(
        self, section: str, value: Any, bad_key: str
    ) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        data = {
            "code_review": {
                "schema_version": 1,
                "is_software_project": True,
                section: value,
            }
        }
        errors = validate_code_review(data)
        assert any(section in e and bad_key in e for e in errors)

    @pytest.mark.parametrize(
        "section, value, needle",
        [
            (
                "protocols_implemented",
                [{"location": "arrg/mcp/"}],
                "protocols_implemented",
            ),
            (
                "persistence",
                {"databases": [{"name": "app", "role": "primary"}]},
                "engine",
            ),
            ("env_vars", [{"purpose": "Stripe secret"}], "name"),
            ("api_surface", [{"protocol": "http"}], "path_or_method"),
            ("ai_capabilities", [{"kind": "llm_api"}], "name"),
        ],
    )
    def test_missing_required_field_fails(
        self, section: str, value: Any, needle: str
    ) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        data = {
            "code_review": {
                "schema_version": 1,
                "is_software_project": True,
                section: value,
            }
        }
        errors = validate_code_review(data)
        assert any(needle in e for e in errors)

    @pytest.mark.parametrize(
        "section, value, needles",
        [
            (
                "ui_summary",
                {"has_ui": True, "kind": "streamlit_dashboard"},
                ("ui_summary", "kind"),
            ),
            (
                "api_surface",
                [{"protocol": "soap", "path_or_method": "GetUser"}],
                ("api_surface", "protocol"),
            ),
            ("auth", {"model": "magic_link"}, ("auth", "model")),
            (
                "ai_capabilities",
                [{"name": "openai", "kind": "chatbot"}],
                ("ai_capabilities", "kind"),
            ),
        ],
    )
    def test_enum_violation_fails(
        self, section: str, value: Any, needles: tuple[str, str]
    ) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        data = {
            "code_review": {
                "schema_version": 1,
                "is_software_project": True,
                section: value,
            }
        }
        errors = validate_code_review(data)
        assert any(all(n in e for n in needles) for e in errors)

    @pytest.mark.parametrize(
        "review",
        [
            {"is_software_project": True},  # schema_version missing
            {"schema_version": 2, "is_software_project": True},  # wrong const
        ],
    )
    def test_schema_version_constraint_fails(self, review: dict[str, Any]) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        errors = validate_code_review({"code_review": review})
        assert any("schema_version" in e for e in errors)


# ---------------------------------------------------------------------------
# CodeScanner validation + retry flow
# ---------------------------------------------------------------------------


class TestCodeScannerValidationRetry:
    """Integration tests for the validate-and-retry behavior in run()."""

    def _valid_review_text(self) -> str:
        return (
            '```json\n{"code_review": {"schema_version": 1, '
            '"is_software_project": true}}\n```'
        )

    def _invalid_review_text(self) -> str:
        # Missing schema_version → fails validation.
        return '```json\n{"code_review": {"is_software_project": true}}\n```'

    def test_valid_review_does_not_retry(self) -> None:
        session = make_session(
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        with mock_litellm_stream(self._valid_review_text()) as mock_llm:
            collect(code_scanner.run("Confirm", session, session["llm_config"]))
        # One completion call total — no retry.
        assert mock_llm.call_count == 1
        assert session["code_scanner_state"] == STATE_REVIEW_COMPLETE

    def test_invalid_review_triggers_retry_with_corrective_message(self) -> None:
        # First LLM call returns invalid JSON; second returns valid JSON.
        # The retry user message must appear in msgs and reference the error.
        session = make_session(
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        chunk_seqs = [
            list(_chunkify_stream(self._invalid_review_text())),
            list(_chunkify_stream(self._valid_review_text())),
        ]

        def fake_completion(**kwargs: Any) -> Any:
            return iter(chunk_seqs.pop(0))

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            collect(code_scanner.run("Confirm", session, session["llm_config"]))

        msgs = session["code_scanner_messages"]
        # Synthesized retry user message present, mentioning validation.
        retry_msgs = [
            m for m in msgs
            if m["role"] == "user" and "failed schema validation" in m["content"]
        ]
        assert len(retry_msgs) == 1
        # Final review committed.
        assert session["code_scanner_state"] == STATE_REVIEW_COMPLETE
        assert session["code_review"]["code_review"]["schema_version"] == 1

    def test_retry_drained_silently_not_yielded(self) -> None:
        # The retry stream's body (raw or fenced JSON) must not be yielded
        # to the user. The original suppression already swallows fenced JSON;
        # here we verify the retry pass adds nothing to the visible output.
        session = make_session(
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        chunk_seqs = [
            list(_chunkify_stream(self._invalid_review_text())),
            list(_chunkify_stream(self._valid_review_text())),
        ]

        def fake_completion(**kwargs: Any) -> Any:
            return iter(chunk_seqs.pop(0))

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            output = collect(
                code_scanner.run("Confirm", session, session["llm_config"])
            )
        # The visible output should not contain the raw JSON of either turn.
        assert "schema_version" not in output
        assert "```json" not in output

    def test_retry_failure_recovers_and_emits_fallback(self) -> None:
        # Both turns emit invalid JSON; the agent should drop the retry
        # exchange and surface a brief recoverable error.
        session = make_session(
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        chunk_seqs = [
            list(_chunkify_stream(self._invalid_review_text())),
            list(_chunkify_stream(self._invalid_review_text())),
        ]

        def fake_completion(**kwargs: Any) -> Any:
            return iter(chunk_seqs.pop(0))

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            collect(code_scanner.run("Confirm", session, session["llm_config"]))

        # No completed state; no review committed.
        assert session["code_scanner_state"] != STATE_REVIEW_COMPLETE
        # Retry exchange dropped — no leftover "failed schema validation"
        # user message clutters the conversation.
        retry_user = [
            m for m in session["code_scanner_messages"]
            if m["role"] == "user" and "failed schema validation" in m["content"]
        ]
        assert retry_user == []
        # Fallback assistant message in place of the bad JSON.
        last = session["code_scanner_messages"][-1]
        assert last["role"] == "assistant"
        assert "validation" in last["content"].lower()

    def test_retry_uses_response_format_when_supported(self) -> None:
        session = make_session(
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        chunk_seqs = [
            list(_chunkify_stream(self._invalid_review_text())),
            list(_chunkify_stream(self._valid_review_text())),
        ]
        call_kwargs: list[dict[str, Any]] = []

        def fake_completion(**kwargs: Any) -> Any:
            call_kwargs.append(kwargs)
            return iter(chunk_seqs.pop(0))

        with patch(
            "spec4.llm.litellm.completion", side_effect=fake_completion
        ), patch(
            "spec4.llm.litellm.get_supported_openai_params",
            return_value=["temperature", "response_format"],
        ):
            collect(code_scanner.run("Confirm", session, session["llm_config"]))

        # First call: no response_format. Second call: response_format set.
        assert "response_format" not in call_kwargs[0]
        assert call_kwargs[1]["response_format"] == {"type": "json_object"}

    def test_retry_skips_response_format_when_unsupported(self) -> None:
        session = make_session(
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        chunk_seqs = [
            list(_chunkify_stream(self._invalid_review_text())),
            list(_chunkify_stream(self._valid_review_text())),
        ]
        call_kwargs: list[dict[str, Any]] = []

        def fake_completion(**kwargs: Any) -> Any:
            call_kwargs.append(kwargs)
            return iter(chunk_seqs.pop(0))

        with patch(
            "spec4.llm.litellm.completion", side_effect=fake_completion
        ), patch(
            "spec4.llm.litellm.get_supported_openai_params",
            return_value=["temperature"],  # no response_format
        ):
            collect(code_scanner.run("Confirm", session, session["llm_config"]))

        assert "response_format" not in call_kwargs[0]
        assert "response_format" not in call_kwargs[1]

    def test_retry_accepts_raw_json_response(self) -> None:
        # When response_format is in effect, the retry body is raw JSON
        # without a ```json fence. _extract_and_validate_review must
        # still pick it up.
        session = make_session(
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )
        raw_valid = (
            '{"code_review": {"schema_version": 1, "is_software_project": true}}'
        )
        chunk_seqs = [
            list(_chunkify_stream(self._invalid_review_text())),
            list(_chunkify_stream(raw_valid)),
        ]

        def fake_completion(**kwargs: Any) -> Any:
            return iter(chunk_seqs.pop(0))

        with patch(
            "spec4.llm.litellm.completion", side_effect=fake_completion
        ), patch(
            "spec4.llm.litellm.get_supported_openai_params",
            return_value=["response_format"],
        ):
            collect(code_scanner.run("Confirm", session, session["llm_config"]))

        assert session["code_scanner_state"] == STATE_REVIEW_COMPLETE
        assert session["code_review"]["code_review"]["schema_version"] == 1


class TestCodeScannerUnparseableArtifact:
    """D-SC-P3: a finalize reply that was suppressed but cannot be parsed.

    ``_extract_and_validate_review`` reports "no JSON, still conversing" both
    when the model genuinely replied in prose and when it emitted an artifact
    block that came back malformed or truncated. The two are not the same: a
    reply opening with a fence was swallowed whole by ``_stream_suppressing_json``
    on its way to the screen, so the second case ends the turn with an empty
    bubble, no state change and no ``code_review.json`` — observed live as
    "it finalized and then nothing happened". It must fail into the retry path.
    """

    def _truncated_review_text(self) -> str:
        # Opens with a fence (so it is suppressed) but never closes it — the
        # fenced-block regex cannot match, and the body does not start with '{'.
        return '```json\n{"code_review": {"schema_version": 1, "is_soft'

    def _valid_review_text(self) -> str:
        return (
            '```json\n{"code_review": {"schema_version": 1, '
            '"is_software_project": true}}\n```'
        )

    def _session(self) -> dict[str, Any]:
        return make_session(
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ]
        )

    def _run(self, *replies: str) -> tuple[dict[str, Any], str]:
        session = self._session()
        chunk_seqs = [list(_chunkify_stream(r)) for r in replies]

        def fake_completion(**kwargs: Any) -> Any:
            return iter(chunk_seqs.pop(0))

        with patch(
            "spec4.llm.litellm.completion", side_effect=fake_completion
        ):
            output = collect(
                code_scanner.run("looks good", session, session["llm_config"])
            )
        return session, output

    def test_truncated_block_is_retried(self) -> None:
        session, _ = self._run(
            self._truncated_review_text(), self._valid_review_text()
        )
        assert session["code_scanner_state"] == STATE_REVIEW_COMPLETE
        assert session["code_review"]["code_review"]["schema_version"] == 1

    def test_retry_message_names_the_parse_failure(self) -> None:
        session, _ = self._run(
            self._truncated_review_text(), self._valid_review_text()
        )
        retry_msgs = [
            m
            for m in session["code_scanner_messages"]
            if m["role"] == "user" and "could not be parsed" in m["content"]
        ]
        assert len(retry_msgs) == 1

    def test_turn_never_ends_silently(self) -> None:
        """The failure this fixes: both attempts unusable used to leave an empty
        bubble. Now the turn ends with something on screen."""
        session, output = self._run(
            self._truncated_review_text(), self._truncated_review_text()
        )
        assert session["_display_override"]
        last = session["code_scanner_messages"][-1]
        assert last["role"] == "assistant"
        assert last["content"] == session["_display_override"]
        assert output.strip(), "the turn yielded nothing visible"

    def test_state_is_not_advanced_when_both_attempts_fail(self) -> None:
        session, _ = self._run(
            self._truncated_review_text(), self._truncated_review_text()
        )
        assert session["code_scanner_state"] != STATE_REVIEW_COMPLETE
        assert session.get("code_review") is None

    def test_ordinary_prose_reply_is_left_alone(self) -> None:
        """The guard keys on the fence, not on the absence of a review — a
        conversational turn must not be turned into a retry."""
        session = self._session()
        with mock_litellm_stream("Which parts should I look at again?") as mock_llm:
            output = collect(
                code_scanner.run("one question first", session, session["llm_config"])
            )
        assert mock_llm.call_count == 1, "a prose reply must not trigger a retry"
        assert "Which parts" in output
        assert session["code_scanner_state"] != STATE_REVIEW_COMPLETE

    def test_unfenced_garbage_is_left_alone(self) -> None:
        """Nothing was suppressed, so the developer saw the reply — there is no
        silent failure to recover from."""
        session = self._session()
        with mock_litellm_stream("code_review: not really json") as mock_llm:
            collect(code_scanner.run("looks good", session, session["llm_config"]))
        assert mock_llm.call_count == 1


class TestSuppressedAsArtifact:
    """The shared predicate behind both the suppression and the D-SC-P3 guard."""

    def test_fence_at_the_start(self) -> None:
        assert _suppressed_as_artifact("```json\n{}") is True

    def test_leading_whitespace_is_ignored(self) -> None:
        assert _suppressed_as_artifact("\n\n  ```json\n{}") is True

    def test_bare_fence_counts(self) -> None:
        """Suppression does not check the language tag, so neither does this."""
        assert _suppressed_as_artifact("```\n{}") is True

    def test_prose_does_not_count(self) -> None:
        assert _suppressed_as_artifact("Here is the review:\n```json\n{}") is False

    def test_empty_does_not_count(self) -> None:
        assert _suppressed_as_artifact("") is False


def _reply_sequence(*replies: str) -> tuple[Any, list[dict[str, Any]]]:
    """A litellm.completion stand-in that serves one reply per call.

    The last reply repeats for any further calls, so a downstream helper making
    its own completion calls (feature_speccer, tool loops) cannot exhaust it and
    turn a behavioural assertion into an IndexError.
    """
    seqs = [list(_chunkify_stream(r)) for r in replies]
    calls: list[dict[str, Any]] = []

    def fake_completion(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return iter(seqs.pop(0) if len(seqs) > 1 else seqs[0])

    return fake_completion, calls


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
        with patch(
            "spec4.llm.litellm.completion", side_effect=fake_completion
        ):
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


class TestBrainstormerUnparseableArtifact:
    """D-BR-P3: the D-SC-P3 fix applied to Brainstormer."""

    _TRUNCATED = '```json\n{"vision_statement": {"name": "TodoApp", "vis'
    _VALID = (
        '```json\n{"vision_statement": {"name": "TodoApp", '
        '"vision": "A simple task manager"}}\n```'
    )

    def _session(self) -> dict[str, Any]:
        session = make_session()
        session["brainstormer_messages"] = [
            {"role": "user", "content": "I want a todo app"},
            {"role": "assistant", "content": "Who is it for?"},
        ]
        return session

    def _run(self, *replies: str) -> tuple[dict[str, Any], str, list[Any]]:
        session = self._session()
        fake_completion, calls = _reply_sequence(*replies)
        with patch(
            "spec4.llm.litellm.completion", side_effect=fake_completion
        ):
            output = collect(
                brainstormer.run("looks good", session, session["llm_config"])
            )
        return session, output, calls

    def test_truncated_block_is_re_asked(self) -> None:
        session, _, calls = self._run(self._TRUNCATED, self._VALID)
        assert len(calls) >= 2, "the unreadable artifact must trigger one re-ask"
        assert session["brainstormer_state"] == STATE_VISION_COMPLETE
        assert session["vision_statement"]["vision_statement"]["name"] == "TodoApp"

    def test_turn_never_ends_silently(self) -> None:
        session, output, _ = self._run(self._TRUNCATED, self._TRUNCATED)
        assert session["_display_override"]
        assert output.strip(), "the turn yielded nothing visible"
        last = session["brainstormer_messages"][-1]
        assert last["role"] == "assistant"
        assert last["content"] == session["_display_override"]

    def test_failed_reask_leaves_no_dead_end_user_turn(self) -> None:
        session, _, _ = self._run(self._TRUNCATED, self._TRUNCATED)
        assert not [
            m
            for m in session["brainstormer_messages"]
            if m["role"] == "user" and "could not be read" in m["content"]
        ]

    def test_state_is_not_advanced_when_both_attempts_fail(self) -> None:
        session, _, _ = self._run(self._TRUNCATED, self._TRUNCATED)
        assert session["brainstormer_state"] != STATE_VISION_COMPLETE
        assert session.get("vision_statement") is None

    def test_ordinary_prose_reply_is_left_alone(self) -> None:
        session = self._session()
        with mock_litellm_stream("What type of users will use this app?") as llm:
            output = collect(
                brainstormer.run("not yet", session, session["llm_config"])
            )
        assert llm.call_count == 1, "a prose reply must not trigger a re-ask"
        assert "What type of users" in output
        assert session["brainstormer_state"] != STATE_VISION_COMPLETE


def _chunkify_stream(text: str) -> Iterable[MagicMock]:
    """Helper: turn text into per-character mock chunks plus a stop sentinel."""
    chunks = [make_stream_chunk(c) for c in text]
    chunks.append(make_stream_chunk("", finish_reason="stop"))
    return chunks


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

        errors = validate_phase(
            _valid_phase(references=[{"standard": "FastAPI"}])
        )
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
        with mock_litellm_stream(text) as mock_llm, patch(
            "spec4.agents.phaser.run_seam_check", return_value=""
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

        with patch(
            "spec4.llm.litellm.completion", side_effect=fake_completion
        ), patch(
            "spec4.llm.litellm.get_supported_openai_params",
            return_value=["temperature", "response_format"],
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

        with patch(
            "spec4.llm.litellm.completion", side_effect=fake_completion
        ), patch("spec4.llm.search", return_value="results"):
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

        with patch(
            "spec4.llm.litellm.completion", side_effect=fake_completion
        ):
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
        complete = _phase_block(
            self._phase(1, 2, phase_title="First")
        ) + _phase_block(self._phase(2, 2, phase_title="Second"))
        chunk_seqs = [
            list(_chunkify_stream(incomplete)),
            list(_chunkify_stream(complete)),
        ]

        def fake_completion(**kwargs: Any) -> Any:
            return iter(chunk_seqs.pop(0))

        with patch(
            "spec4.llm.litellm.completion", side_effect=fake_completion
        ):
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
        with mock_litellm_stream(text), patch(
            "spec4.agents.phaser.run_seam_check", return_value=""
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
        p2 = self._phase(
            2, 2, instructions=["Do the thing.", f"touch {marker}"]
        )
        text = _phase_block(self._phase(1, 2)) + _phase_block(p2)
        with mock_litellm_stream(text), patch(
            "spec4.agents.phaser.run_seam_check", return_value=""
        ):
            collect(phaser.run("Approve", session, session["llm_config"]))

        last = max(session["phases"], key=lambda p: p["phase_number"])
        assert sum(1 for s in last["instructions"] if marker in s) == 1


# ---------------------------------------------------------------------------
# Phaser revision mode
# ---------------------------------------------------------------------------


def _phaser_revision_vision(
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


class TestPhaserRevisionMode:
    """Revision mode: when a prior round is implemented and the vision carries a
    delta, Phaser scopes the plan to the delta and renumbers 1..k (Route A). The
    reader/note helpers are deterministic (no LLM). Phaser carries no prior
    artifact forward — the gate is a plain implemented-predecessor probe."""

    # ----- revision_delta -----

    def test_delta_none_for_greenfield_vision(self) -> None:
        assert phaser.revision_delta(
            {"vision_statement": {"name": "Fresh"}}
        ) is None

    def test_delta_none_for_empty_or_missing(self) -> None:
        assert phaser.revision_delta(None) is None
        assert phaser.revision_delta({}) is None
        assert phaser.revision_delta(
            {"vision_statement": {"revision_history": []}}
        ) is None
        # Non-enveloped (inner-form) vision is not revision mode.
        assert phaser.revision_delta({"name": "App"}) is None

    def test_delta_returns_last_history_entry(self) -> None:
        vision = {
            "vision_statement": {
                "revision_history": [
                    {"version": 0, "goal": "first"},
                    {"version": 1, "goal": "Add returns",
                     "changes": {"added": ["Returns"]}},
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

    def test_prior_round_without_delta_is_not_revision(
        self, tmp_path: Any
    ) -> None:
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
                {"name": "search", "tier": "rag", "phase_priority": "mvp",
                 "purpose": "find", "introduced_in_version": 0},
                {"name": "summarize", "tier": "single_call",
                 "phase_priority": "mvp", "purpose": "tldr",
                 "introduced_in_version": 1},
            ]
        }

    def test_none_version_is_unchanged_greenfield_output(self) -> None:
        out = _ai_features_for_phaser(self._features())
        assert "AI features spec (from Agentifier)" in out
        assert "search" in out and "summarize" in out
        assert "Already-implemented AI features" not in out

    def test_empty_features_returns_empty(self) -> None:
        assert _ai_features_for_phaser({"ai_features": []}, revision_version=1) == ""

    def test_revision_partitions_by_introduced_in_version(self) -> None:
        out = _ai_features_for_phaser(self._features(), revision_version=1)
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
        out = _ai_features_for_phaser(feats, revision_version=1)
        assert "Already-implemented AI features" in out
        assert "New/changed AI features for this revision" not in out
        assert "| Feature | Tier |" not in out

    def test_missing_introduced_in_version_treated_as_established(self) -> None:
        # Defensive: a feature without the stamp is not re-phased.
        feats = {"ai_features": [{"name": "legacy", "tier": "rag"}]}
        out = _ai_features_for_phaser(feats, revision_version=1)
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


class TestDeployerRevisionMode:
    """Revision mode: when a prior round is implemented and the vision carries a
    delta, Deployer carries the prior deployment plan forward as the baseline and
    scopes the update to the delta (whole-system-scoped — the ai_features context
    stays whole, no introduced_in_version partition). The reader/note helpers are
    deterministic (no LLM). The gate is an implemented-predecessor probe and is NOT
    gated on the prior plan loading (the prior round may have skipped Deployer)."""

    # ----- revision_delta -----

    def test_delta_none_for_greenfield_vision(self) -> None:
        assert deployer.revision_delta(
            {"vision_statement": {"name": "Fresh"}}
        ) is None

    def test_delta_none_for_empty_or_missing(self) -> None:
        assert deployer.revision_delta(None) is None
        assert deployer.revision_delta({}) is None
        assert deployer.revision_delta(
            {"vision_statement": {"revision_history": []}}
        ) is None
        # Non-enveloped (inner-form) vision is not revision mode.
        assert deployer.revision_delta({"name": "App"}) is None

    def test_delta_returns_last_history_entry(self) -> None:
        vision = {
            "vision_statement": {
                "revision_history": [
                    {"version": 0, "goal": "first"},
                    {"version": 1, "goal": "Add billing",
                     "changes": {"added": ["Subscriptions"]}},
                ]
            }
        }
        delta = deployer.revision_delta(vision)
        assert delta is not None
        assert delta["goal"] == "Add billing"
        assert delta["changes"]["added"] == ["Subscriptions"]

    def test_delta_non_dict_last_entry_is_none(self) -> None:
        vision = {"vision_statement": {"revision_history": ["not a dict"]}}
        assert deployer.revision_delta(vision) is None

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
        note = deployer.build_revision_note(delta)
        assert note.startswith("[") and note.endswith("]")
        assert "Add billing" in note
        assert "Subscriptions" in note
        assert "Checkout" in note
        assert "Free Tier" in note
        # Deployment-scoping intent is explicit.
        assert "already provisioned and in place" in note
        assert "do not re-ask settled deployment decisions" in note

    def test_note_omits_goal_when_blank(self) -> None:
        note = deployer.build_revision_note(
            {"goal": "", "changes": {"added": ["X"], "modified": [], "removed": []}}
        )
        assert "Goal:" not in note
        assert "added features (X)" in note

    def test_note_empty_changes_still_preserves(self) -> None:
        # Degenerate delta (no feature changes) → still a valid scoping note.
        note = deployer.build_revision_note({"changes": {}})
        assert "already provisioned and in place" in note
        assert "Update the deployment plan only for" not in note

    def test_note_missing_changes_key(self) -> None:
        note = deployer.build_revision_note({"goal": "g"})
        assert "Goal: g" in note
        assert note.endswith("]")

    # ----- seed selection -----

    def _implement_prior_round(self, wd: str, *, with_plan: bool = True) -> None:
        from spec4 import project_manager

        project_manager.save_phases(
            wd, [{"phase_number": 1, "phase_title": "Steel"}], 0
        )
        if with_plan:
            project_manager.save_deployment_plan(
                wd, "# Deployment Plan\n\n## Target\n\n- **Provider:** Fly.io\n", 0
            )
        project_manager.get_version_dir(wd, 0).joinpath("IMPLEMENTED").write_text("")

    def test_revision_seed_carries_prior_plan_and_scopes_delta(
        self, tmp_path: Any
    ) -> None:
        wd = str(tmp_path)
        self._implement_prior_round(wd, with_plan=True)
        session = make_session(
            active_agent="deployer",
            working_dir=wd,
            phase_version=1,
            phases=[{"phase_number": 1, "phase_title": "Integration"}],
            stack_statement={"name": "App"},
            vision_statement=_phaser_revision_vision(
                added=["Subscriptions"], goal="Add billing"
            ),
            _deployer_plan_existed=False,
        )
        with mock_litellm_stream("Carrying forward your deployment."):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        # Operates in revision mode, scoped to the delta.
        assert "REVISION mode" in seed
        assert "Subscriptions" in seed
        assert "Add billing" in seed
        assert "already provisioned and in place" in seed
        # Carries the prior implemented plan forward as the baseline.
        assert "established baseline" in seed
        assert "Provider:** Fly.io" in seed
        assert "carrying forward from the baseline above" in seed
        # Not the generic greenfield intro.
        assert (
            "then begin by asking which AI coding agent" not in seed
        )

    def test_revision_seed_without_prior_plan_skipped_predecessor(
        self, tmp_path: Any
    ) -> None:
        # Prior round implemented but Deployer was skipped (no deployment-plan.md):
        # still revision mode, no baseline block, graceful intro.
        wd = str(tmp_path)
        self._implement_prior_round(wd, with_plan=False)
        session = make_session(
            active_agent="deployer",
            working_dir=wd,
            phase_version=1,
            phases=[{"phase_number": 1, "phase_title": "Integration"}],
            stack_statement={"name": "App"},
            vision_statement=_phaser_revision_vision(
                added=["Subscriptions"], goal="Add billing"
            ),
            _deployer_plan_existed=False,
        )
        with mock_litellm_stream("Revision, no baseline."):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        assert "REVISION mode" in seed
        assert "Subscriptions" in seed
        # No prior-plan baseline block.
        assert "established baseline" not in seed
        assert "carrying forward from the baseline above" not in seed
        # Graceful no-baseline intro instead.
        assert "note that this is a revision of an already-deployed project" in seed

    def test_revision_seed_keeps_ai_features_whole(self, tmp_path: Any) -> None:
        # D3: _ai_features_for_deployer stays whole in revision mode — no
        # introduced_in_version partition into new-vs-established buckets.
        wd = str(tmp_path)
        self._implement_prior_round(wd, with_plan=True)
        ai_features = {
            "ai_features": [
                {"name": "Summarizer", "tier": "rag",
                 "introduced_in_version": 0},
                {"name": "Agent", "tier": "tool_agent",
                 "introduced_in_version": 1},
            ],
            "cross_cutting": {
                "provider_strategy": {"recommendation": "Use one provider"}
            },
        }
        session = make_session(
            active_agent="deployer",
            working_dir=wd,
            phase_version=1,
            phases=[{"phase_number": 1, "phase_title": "Integration"}],
            stack_statement={"name": "App"},
            ai_features=ai_features,
            vision_statement=_phaser_revision_vision(
                added=["Agent"], goal="Add an agent"
            ),
            _deployer_plan_existed=False,
        )
        with mock_litellm_stream("Whole AI context."):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        # The whole deployment-context block is present...
        assert "AI features spec — deployment context" in seed
        # ...and it is NOT partitioned the way _ai_features_for_phaser would.
        assert "do NOT create phases" not in seed
        assert "Already-implemented AI features" not in seed

    def test_prior_round_without_delta_is_not_revision(
        self, tmp_path: Any
    ) -> None:
        # Implemented prior round exists, but the vision has no revision delta —
        # falls through to the fresh greenfield seed, not revision mode.
        wd = str(tmp_path)
        self._implement_prior_round(wd, with_plan=True)
        session = make_session(
            active_agent="deployer",
            working_dir=wd,
            phase_version=1,
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            stack_statement={"name": "App"},
            vision_statement={"vision_statement": {"name": "App"}},
            _deployer_plan_existed=False,
            _deployer_readme_optin_done=True,
        )
        with mock_litellm_stream("Fresh plan."):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        assert "REVISION mode" not in seed
        assert "asking which AI coding agent" in seed

    def test_delta_without_implemented_round_is_not_revision(
        self, tmp_path: Any
    ) -> None:
        # Vision carries a revision delta but no prior round is IMPLEMENTED →
        # not revision mode (fresh greenfield seed).
        wd = str(tmp_path)
        session = make_session(
            active_agent="deployer",
            working_dir=wd,
            phase_version=0,
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            stack_statement={"name": "App"},
            vision_statement=_phaser_revision_vision(
                added=["Subscriptions"], goal="Add billing"
            ),
            _deployer_plan_existed=False,
            _deployer_readme_optin_done=True,
        )
        with mock_litellm_stream("Greenfield plan."):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        assert "REVISION mode" not in seed
        assert "asking which AI coding agent" in seed


class TestDeployerReadme:
    """Deployer offers a comprehensive project README after the deployment plan
    is finalized; on acceptance it authors the README and stages it for the
    project root (not .spec4). build_readme_request scaffolds the authoring turn;
    the offer/accept/decline flow mirrors the existing replace-confirmation."""

    # --- build_readme_request --------------------------------------------

    def test_build_request_fresh(self) -> None:
        req = deployer.build_readme_request(None, None)
        low = req.lower()
        assert "readme" in low
        assert "install" in low
        assert "usage" in low or "use the application" in low
        assert "vision" in low
        assert "output the readme directly" in low
        # No baseline block and no revision note in the greenfield case.
        assert "already exists" not in low
        assert "revision round" not in low

    def test_build_request_with_existing_baseline(self) -> None:
        req = deployer.build_readme_request("# Existing\n\nBody.\n", None)
        assert "already exists at the project root" in req
        assert "# Existing" in req
        assert "update it in place" in req

    def test_build_request_with_delta_names_changes(self) -> None:
        delta = {
            "changes": {
                "added": ["Export to PDF"],
                "modified": ["Login"],
                "removed": [],
            }
        }
        req = deployer.build_readme_request(None, delta)
        assert "revision round" in req.lower()
        assert "Export to PDF" in req
        assert "Login" in req

    # --- offer placement --------------------------------------------------

    def test_offer_appended_on_no_prior_plan_finalization(self) -> None:
        session = make_session(
            active_agent="deployer",
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": "ready to finalize?"},
            ],
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            _deployer_plan_existed=False,
        )
        plan = (
            "# Deployment Plan\n\n## Target\n- **Provider:** Fly.io\n\n"
            "## Deployment Steps\n\n### 1. Build\n…"
        )
        with mock_litellm_stream(plan):
            collect(deployer.run("yes, looks good", session, session["llm_config"]))
        assert session["_deployer_pending_readme"] is True
        assert "README" in session["deployer_messages"][-1]["content"]
        assert session["deployer_state"] == STATE_DEPLOYER_COMPLETE
        # The plan itself is still staged for persistence, unchanged.
        assert session["_deployer_plan_markdown"] == plan

    def test_offer_appended_after_replace_confirmation_accepted(self) -> None:
        plan = "# Plan\n\n## Deployment Steps\n\n### 1. Build\n…"
        session = make_session(
            active_agent="deployer",
            deployer_state=STATE_DEPLOYER_COMPLETE,
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": plan + "\n\n…replace? (yes/no)"},
            ],
            _deployer_plan_existed=True,
            _deployer_plan_markdown=plan,
            _deployer_pending_plan=True,
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(deployer.run("yes", session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert session["_deployer_pending_readme"] is True
        assert "README" in output
        assert session["_deployer_plan_markdown"] == plan

    # --- accept / decline -------------------------------------------------

    def test_accept_generates_and_stages_readme(self) -> None:
        session = make_session(
            active_agent="deployer",
            working_dir=None,
            deployer_state=STATE_DEPLOYER_COMPLETE,
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": "plan…readme? (yes/no)"},
            ],
            _deployer_pending_readme=True,
        )
        readme = "# My App\n\nA great app.\n\n## Install\n\n`pip install .`\n"
        with mock_litellm_stream(readme):
            collect(deployer.run("yes please", session, session["llm_config"]))
        assert session["_deployer_readme_markdown"] == readme
        assert session.get("_deployer_generating_readme") is False
        assert session["_deployer_pending_readme"] is False
        # The authoring instruction was injected as the user turn.
        user_msgs = [
            m["content"] for m in session["deployer_messages"] if m["role"] == "user"
        ]
        assert any("comprehensive project README" in c for c in user_msgs)

    def test_accept_uses_existing_readme_as_baseline(self, tmp_path: Any) -> None:
        from spec4 import project_manager

        project_manager.save_readme(str(tmp_path), "# Old README\n\nOld content.\n")
        session = make_session(
            active_agent="deployer",
            working_dir=str(tmp_path),
            deployer_state=STATE_DEPLOYER_COMPLETE,
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": "readme? (yes/no)"},
            ],
            _deployer_pending_readme=True,
        )
        with mock_litellm_stream("# New README\n"):
            collect(deployer.run("yes", session, session["llm_config"]))
        seed = next(
            m["content"]
            for m in session["deployer_messages"]
            if m["role"] == "user" and "comprehensive project README" in m["content"]
        )
        assert "Old README" in seed
        assert "update it in place" in seed

    def test_decline_skips_readme_no_llm_call(self) -> None:
        session = make_session(
            active_agent="deployer",
            deployer_state=STATE_DEPLOYER_COMPLETE,
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": "plan…" + deployer._README_OFFER},
            ],
            _deployer_pending_readme=True,
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(deployer.run("no thanks", session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "README" in output
        assert session["_deployer_pending_readme"] is False
        assert session.get("_deployer_readme_markdown") in (None, "")
        assert not session.get("_deployer_generating_readme")


class TestDeployerReadmeUpfrontOptin:
    """Greenfield asks the README opt-in up front (a standalone, prominent turn
    before any plan work) and auto-authors the README after the plan when
    accepted — replacing the old offer buried at the bottom of the plan."""

    # --- the up-front gate ------------------------------------------------

    def test_optin_asked_first_on_greenfield_open(self) -> None:
        session = make_session(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            _deployer_plan_existed=False,
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(deployer.run(None, session, session["llm_config"]))
        # Deterministic gate: no LLM call, and the opening seed is not built yet.
        mock_llm.assert_not_called()
        assert "README" in output
        assert session["_deployer_pending_readme_optin"] is True
        assert session["_deployer_readme_optin_done"] is True
        assert session["deployer_messages"] == []

    def test_optin_accept_records_choice_and_opens(self) -> None:
        session = make_session(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            _deployer_plan_existed=False,
            _deployer_readme_optin_done=True,
            _deployer_pending_readme_optin=True,
        )
        with mock_litellm_stream("Which coding agent are you using?"):
            collect(deployer.run("yes please", session, session["llm_config"]))
        assert session["_deployer_readme_requested"] is True
        assert session["_deployer_pending_readme_optin"] is False
        # The opt-in Q&A never enters the LLM history; the first message is the
        # coding-agent opening seed, and the bare "yes" is absent.
        assert session["deployer_messages"][0]["role"] == "user"
        assert "coding agent" in session["deployer_messages"][0]["content"].lower()
        assert all(
            "yes please" not in m["content"] for m in session["deployer_messages"]
        )

    def test_optin_decline_records_choice_and_opens(self) -> None:
        session = make_session(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            _deployer_plan_existed=False,
            _deployer_readme_optin_done=True,
            _deployer_pending_readme_optin=True,
        )
        with mock_litellm_stream("Which coding agent are you using?"):
            collect(deployer.run("no thanks", session, session["llm_config"]))
        assert session["_deployer_readme_requested"] is False
        assert session["_deployer_pending_readme_optin"] is False
        assert "coding agent" in session["deployer_messages"][0]["content"].lower()

    def test_optin_ambiguous_reasks_without_llm(self) -> None:
        session = make_session(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            _deployer_plan_existed=False,
            _deployer_readme_optin_done=True,
            _deployer_pending_readme_optin=True,
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(
                deployer.run("what's a README?", session, session["llm_config"])
            )
        mock_llm.assert_not_called()
        assert "README" in output
        # Still pending — the gate persists until a clear yes/no, and no choice
        # is recorded yet.
        assert session["_deployer_pending_readme_optin"] is True
        assert "_deployer_readme_requested" not in session
        assert session["deployer_messages"] == []

    # --- auto-author / skip after the plan --------------------------------

    def test_optin_yes_autoauthors_readme_after_plan(self) -> None:
        session = make_session(
            active_agent="deployer",
            working_dir=None,
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": "ready to finalize?"},
            ],
            _deployer_plan_existed=False,
            _deployer_readme_optin_done=True,
            _deployer_readme_requested=True,
        )
        plan = (
            "# Deployment Plan\n\n## Target\n- **Provider:** Fly.io\n\n"
            "## Deployment Steps\n\n### 1. Build\n…"
        )
        readme = "# My App\n\nA great app.\n\n## Install\n\n`pip install .`\n"
        plan_chunks = [make_stream_chunk(c) for c in plan]
        plan_chunks.append(make_stream_chunk("", finish_reason="stop"))
        readme_chunks = [make_stream_chunk(c) for c in readme]
        readme_chunks.append(make_stream_chunk("", finish_reason="stop"))
        with patch(
            "spec4.llm.litellm.completion",
            side_effect=[iter(plan_chunks), iter(readme_chunks)],
        ) as mock_llm:
            output = collect(deployer.run("looks good", session, session["llm_config"]))
        # Exactly two LLM calls: the plan, then the README authored from it.
        assert mock_llm.call_count == 2
        assert session["_deployer_plan_markdown"] == plan
        assert session["_deployer_readme_markdown"] == readme
        # No trailing offer / pending flag — the decision was made up front — and
        # the request flag is consumed so a later plan turn won't re-author.
        assert not session.get("_deployer_pending_readme")
        assert deployer._README_OFFER not in output
        assert session["_deployer_readme_requested"] is False
        # The authoring instruction was injected as a user turn, and both the
        # plan and the freshly-authored README appear in the turn's output.
        assert any(
            "comprehensive project README" in m["content"]
            for m in session["deployer_messages"]
            if m["role"] == "user"
        )
        assert "Deployment Steps" in output
        assert "My App" in output
        assert session["deployer_state"] == STATE_DEPLOYER_COMPLETE

    def test_optin_no_skips_readme_after_plan(self) -> None:
        session = make_session(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": "ready to finalize?"},
            ],
            _deployer_plan_existed=False,
            _deployer_readme_optin_done=True,
            _deployer_readme_requested=False,
        )
        plan = "# Plan\n\n## Deployment Steps\n\n### 1. Build\n…"
        plan_chunks = [make_stream_chunk(c) for c in plan]
        plan_chunks.append(make_stream_chunk("", finish_reason="stop"))
        with patch(
            "spec4.llm.litellm.completion",
            side_effect=[iter(plan_chunks)],
        ) as mock_llm:
            output = collect(deployer.run("looks good", session, session["llm_config"]))
        # Exactly one LLM call (the plan) — no README authoring call.
        assert mock_llm.call_count == 1
        assert session["_deployer_plan_markdown"] == plan
        assert session.get("_deployer_readme_markdown") in (None, "")
        # No README authored, no trailing offer, no pending flag.
        assert not session.get("_deployer_pending_readme")
        assert deployer._README_OFFER not in output
        assert not any(
            "comprehensive project README" in m["content"]
            for m in session["deployer_messages"]
            if m["role"] == "user"
        )
        assert session["deployer_state"] == STATE_DEPLOYER_COMPLETE


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
        out = _ai_features_for_phaser(catalog)
        assert long_purpose in out

    def test_spec_body_reaches_phaser(self) -> None:
        out = _ai_features_for_phaser(self._catalog())
        assert "user asks" in out
        assert "`question`" in out
        assert "cites a source" in out
        assert "no hits" in out

    def test_tier_analysis_reaches_phaser(self) -> None:
        out = _ai_features_for_phaser(self._catalog())
        assert "needs private corpus grounding" in out
        assert "single_call hallucinates" in out

    def test_ids_are_surfaced_as_the_join_key(self) -> None:
        out = _ai_features_for_phaser(self._catalog())
        assert "`rag_answerer`" in out
        assert "exact key to use in each phase's `features` array" in out

    def test_infrastructure_guidance_is_present(self) -> None:
        out = _ai_features_for_phaser(self._catalog())
        assert "infrastructure" in out
        assert "same phase as its first consumer or earlier" in out

    def test_cross_feature_guidance_is_present(self) -> None:
        out = _ai_features_for_phaser(self._catalog())
        assert "shared surface" in out

    def test_cross_cutting_reaches_phaser_including_provider_strategy(self) -> None:
        # Phaser sees provider_strategy; the phase files deliberately do not.
        out = _ai_features_for_phaser(self._catalog())
        assert "a strong general model" in out
        assert "pin prompts per release" in out

    def test_rejected_candidates_are_named(self) -> None:
        out = _ai_features_for_phaser(self._catalog())
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

        return patch(
            "spec4.llm.litellm.completion", side_effect=fake_completion
        )

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
        with mock_litellm_stream(self._covered()), patch(
            "spec4.agents.phaser.run_seam_check", return_value=""
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
        with self._two_turn_stream(bad, self._covered()), patch(
            "spec4.agents.phaser.run_seam_check", return_value=""
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
        with self._two_turn_stream(bad, self._covered()), patch(
            "spec4.agents.phaser.run_seam_check", return_value=""
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
        catalog["ai_features"].append({
            "id": "summarizer",
            "name": "Summarizer",
            "kind": "feature",
            "tier": "single_call",
            "phase_priority": "v2",
            "requires": [],
        })
        session["ai_features"] = catalog
        with mock_litellm_stream(self._covered()), patch(
            "spec4.agents.phaser.run_seam_check", return_value=""
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
        with mock_litellm_stream(_phase_block(_valid_phase())), patch(
            "spec4.agents.phaser.run_seam_check", return_value=""
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
