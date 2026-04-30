from collections.abc import Iterable
from typing import Any
from unittest.mock import MagicMock, patch

from spec4.agents import brainstormer, phaser, reviewer, stack_advisor
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
        "specmem": None,
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
        "reviewer_messages": [],
        "reviewer_state": STATE_IN_PROGRESS,
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
            '{"type": "object", "title": "stack", "required": ["stack"], '
            '"properties": {"language": {"type": "string", "description": "Python"}}}\n'
            "```"
        )
        with mock_litellm_stream(stack_response):
            collect(
                stack_advisor.run("Yes, finalize it", session, session["llm_config"])
            )
        assert session["stack_advisor_state"] == STATE_STACK_COMPLETE
        assert session["stack_statement"]["title"] == "stack"

    def test_re_entry_does_not_call_llm(self) -> None:
        session = make_session(
            active_agent="stack_advisor",
            vision_statement={"name": "App", "vision": "v"},
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

    def test_reentry_replays_last_assistant_message(self) -> None:
        session = make_session(
            brainstormer_messages=[
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "Existing response"},
            ]
        )
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "Existing response" in output

    def test_reentry_no_assistant_message_yields_nothing(self) -> None:
        session = make_session(
            brainstormer_messages=[{"role": "user", "content": "hi"}]
        )
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert output == ""

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

    def test_specmem_seed_calls_llm(self) -> None:
        session = make_session(
            specmem="# Notes\nSome project notes",
            vision_statement=None,
            code_review=None,
        )
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [make_stream_chunk("Ok"), make_stream_chunk("", finish_reason="stop")]
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

    def test_extract_stack_json_with_title_stack(self) -> None:
        from spec4.agents.stack_advisor import _extract_stack_json

        text = '```json\n{"title": "stack", "properties": {}}\n```'
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

    def test_reentry_no_assistant_message_yields_nothing(self) -> None:
        session = make_session(
            active_agent="stack_advisor",
            vision_statement={"name": "App", "vision": "v"},
        )
        session["stack_advisor_messages"] = [{"role": "user", "content": "hi"}]
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(stack_advisor.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert output == ""

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

    def test_specmem_seed_calls_llm(self) -> None:
        session = make_session(
            active_agent="stack_advisor",
            vision_statement={"name": "App", "vision": "v"},
            specmem="# Notes\nDetails",
            stack_statement=None,
            code_review=None,
        )
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [make_stream_chunk("Ok"), make_stream_chunk("", finish_reason="stop")]
            )
            collect(stack_advisor.run(None, session, session["llm_config"]))
        mock_llm.assert_called_once()


# ---------------------------------------------------------------------------
# Reviewer tests
# ---------------------------------------------------------------------------


class TestReviewer:
    def test_no_working_dir_yields_warning(self) -> None:
        session = make_session(working_dir=None)
        output = collect(reviewer.run(None, session, session["llm_config"]))
        assert (
            "working directory" in output.lower()
            or "no project directory" in output.lower()
        )

    def test_no_working_dir_does_not_call_llm(self) -> None:
        session = make_session(working_dir=None)
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            collect(reviewer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()

    def test_reentry_replays_last_assistant_message(self) -> None:
        session = make_session(
            reviewer_messages=[
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "Reviewer response"},
            ]
        )
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(reviewer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "Reviewer response" in output

    def test_reentry_no_assistant_yields_nothing(self) -> None:
        session = make_session(reviewer_messages=[{"role": "user", "content": "hi"}])
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(reviewer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert output == ""

    def test_user_input_calls_llm(self) -> None:
        session = make_session(reviewer_messages=[{"role": "user", "content": "seed"}])
        with mock_litellm_stream("Here is my review."):
            output = collect(reviewer.run("Looks good", session, session["llm_config"]))
        assert "Here is my review." in output

    def test_review_json_sets_state_complete(self) -> None:
        session = make_session(reviewer_messages=[{"role": "user", "content": "seed"}])
        review_response = '```json\n{"code_review": {"is_software_project": true}}\n```'
        with mock_litellm_stream(review_response):
            collect(reviewer.run("Confirm", session, session["llm_config"]))
        assert session["reviewer_state"] == STATE_REVIEW_COMPLETE
        assert session["code_review"] == {"code_review": {"is_software_project": True}}

    def test_non_review_response_stays_in_progress(self) -> None:
        session = make_session(reviewer_messages=[{"role": "user", "content": "seed"}])
        with mock_litellm_stream("Tell me about section 1."):
            collect(reviewer.run("Go on", session, session["llm_config"]))
        assert session["reviewer_state"] == STATE_IN_PROGRESS
        assert session["code_review"] is None

    def test_extract_review_json_valid(self) -> None:
        from spec4.agents.reviewer import _extract_review_json

        text = '```json\n{"code_review": {"is_software_project": true}}\n```'
        assert _extract_review_json(text) == {
            "code_review": {"is_software_project": True}
        }

    def test_extract_review_json_no_code_review_key_returns_none(self) -> None:
        from spec4.agents.reviewer import _extract_review_json

        assert _extract_review_json('```json\n{"name": "App"}\n```') is None

    def test_extract_review_json_invalid_json_returns_none(self) -> None:
        from spec4.agents.reviewer import _extract_review_json

        assert _extract_review_json("```json\n{bad}\n```") is None

    def test_initialises_reviewer_messages_if_missing(self) -> None:
        session = make_session(reviewer_messages=[{"role": "user", "content": "seed"}])
        del session["reviewer_messages"]
        with mock_litellm_stream("Ok"):
            collect(reviewer.run("Hi", session, session["llm_config"]))
        assert "reviewer_messages" in session


# ---------------------------------------------------------------------------
# _gather_project_context tests
# ---------------------------------------------------------------------------


class TestGatherProjectContext:
    def test_empty_dir_reports_empty(self, tmp_path: Any) -> None:
        from spec4.agents.reviewer import _gather_project_context

        result = _gather_project_context(str(tmp_path))
        assert "empty" in result.lower()

    def test_source_files_appear_in_tree(self, tmp_path: Any) -> None:
        from spec4.agents.reviewer import _gather_project_context

        (tmp_path / "main.py").write_text("print('hello')")
        result = _gather_project_context(str(tmp_path))
        assert "main.py" in result

    def test_git_dir_is_skipped(self, tmp_path: Any) -> None:
        from spec4.agents.reviewer import _gather_project_context

        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]")
        result = _gather_project_context(str(tmp_path))
        assert "config" not in result

    def test_readme_content_included(self, tmp_path: Any) -> None:
        from spec4.agents.reviewer import _gather_project_context

        (tmp_path / "README.md").write_text("# My Project\nA cool app.")
        result = _gather_project_context(str(tmp_path))
        assert "My Project" in result

    def test_source_file_sample_included(self, tmp_path: Any) -> None:
        from spec4.agents.reviewer import _gather_project_context

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

    def test_reentry_no_assistant_yields_nothing(self) -> None:
        session = make_session(phaser_messages=[{"role": "user", "content": "hi"}])
        with patch("spec4.tavily_mcp.litellm.completion") as mock_llm:
            output = collect(phaser.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert output == ""

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
