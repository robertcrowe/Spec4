import json
import pathlib
from typing import Any
from unittest.mock import patch

import pytest

from spec4.app_constants import (
    STATE_IN_PROGRESS,
    STATE_PHASES_COMPLETE,
    STATE_REVIEW_COMPLETE,
    STATE_STACK_COMPLETE,
    STATE_VISION_COMPLETE,
)
from spec4.session import (
    _default_session,
    _load_working_dir,
    _persist_artifacts,
    _run_agent_blocking,
)


class TestDefaultSession:
    def test_has_all_expected_keys(self) -> None:
        session = _default_session()
        required = [
            "working_dir",
            "browser_path",
            "specmem",
            "phase",
            "provider",
            "model",
            "api_key",
            "available_models",
            "tavily_api_key",
            "setup_error",
            "agent_select_error",
            "llm_config",
            "messages",
            "active_agent",
            "reviewer_state",
            "reviewer_messages",
            "code_review",
            "brainstormer_state",
            "brainstormer_messages",
            "vision_statement",
            "stack_advisor_messages",
            "stack_advisor_state",
            "stack_statement",
            "phaser_state",
            "phaser_messages",
            "phases",
            "_warn_existing_content",
            "_dir_has_content",
            "_initial_turn_done",
        ]
        for key in required:
            assert key in session, f"Missing key: {key}"

    def test_phase_is_landing(self) -> None:
        assert _default_session()["phase"] == "landing"

    def test_active_agent_is_brainstormer(self) -> None:
        assert _default_session()["active_agent"] == "brainstormer"

    def test_messages_is_empty_list(self) -> None:
        assert _default_session()["messages"] == []

    def test_phases_is_empty_list(self) -> None:
        assert _default_session()["phases"] == []

    def test_working_dir_is_none(self) -> None:
        assert _default_session()["working_dir"] is None

    def test_returns_fresh_dict_each_call(self) -> None:
        s1 = _default_session()
        s2 = _default_session()
        s1["messages"].append("x")
        assert s2["messages"] == []


class TestRunAgentBlocking:
    def _session(self, agent: str) -> dict[str, Any]:
        return {
            "active_agent": agent,
            "llm_config": {"model": "gpt-4o", "api_key": "sk-test"},
        }

    def test_routes_to_brainstormer(self) -> None:
        session = self._session("brainstormer")
        with patch(
            "spec4.session.brainstormer.run", return_value=iter(["hello"])
        ) as mock_run:
            result = _run_agent_blocking("hi", session)
        mock_run.assert_called_once()
        assert result == "hello"

    def test_routes_to_reviewer(self) -> None:
        session = self._session("reviewer")
        with patch(
            "spec4.session.reviewer.run", return_value=iter(["review"])
        ) as mock_run:
            _run_agent_blocking("hi", session)
        mock_run.assert_called_once()

    def test_routes_to_stack_advisor(self) -> None:
        session = self._session("stack_advisor")
        with patch(
            "spec4.session.stack_advisor.run", return_value=iter(["stack"])
        ) as mock_run:
            _run_agent_blocking("hi", session)
        mock_run.assert_called_once()

    def test_routes_to_phaser(self) -> None:
        session = self._session("phaser")
        with patch(
            "spec4.session.phaser.run", return_value=iter(["phase"])
        ) as mock_run:
            _run_agent_blocking("hi", session)
        mock_run.assert_called_once()

    def test_raises_for_unknown_agent(self) -> None:
        session = self._session("nonexistent_agent")
        with pytest.raises(ValueError, match="Unknown agent"):
            _run_agent_blocking("hi", session)

    def test_joins_generator_chunks(self) -> None:
        session = self._session("brainstormer")
        with patch(
            "spec4.session.brainstormer.run", return_value=iter(["he", "ll", "o"])
        ):
            assert _run_agent_blocking("hi", session) == "hello"

    def test_passes_llm_config_to_agent(self) -> None:
        session = self._session("brainstormer")
        with patch("spec4.session.brainstormer.run", return_value=iter([])) as mock_run:
            _run_agent_blocking("hi", session)
        _, call_args, _ = mock_run.mock_calls[0]
        assert call_args[2] == {"model": "gpt-4o", "api_key": "sk-test"}


class TestPersistArtifacts:
    def _base_session(self, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "working_dir": "/some/dir",
            "brainstormer_state": STATE_IN_PROGRESS,
            "vision_statement": None,
            "stack_advisor_state": STATE_IN_PROGRESS,
            "stack_statement": None,
            "phaser_state": None,
            "phases": [],
            "reviewer_state": STATE_IN_PROGRESS,
            "code_review": None,
        }
        base.update(overrides)
        return base

    def test_no_working_dir_is_noop(self) -> None:
        session = self._base_session(working_dir=None)
        with patch("spec4.session.project_manager") as mock_pm:
            _persist_artifacts(session)
        mock_pm.save_vision.assert_not_called()
        mock_pm.save_stack.assert_not_called()
        mock_pm.save_phases.assert_not_called()
        mock_pm.save_code_review.assert_not_called()

    def test_saves_vision_when_complete(self) -> None:
        vision = {"name": "App"}
        session = self._base_session(
            brainstormer_state=STATE_VISION_COMPLETE, vision_statement=vision
        )
        with patch("spec4.session.project_manager") as mock_pm:
            _persist_artifacts(session)
        mock_pm.save_vision.assert_called_once_with("/some/dir", vision)

    def test_does_not_save_vision_when_state_in_progress(self) -> None:
        session = self._base_session(
            brainstormer_state=STATE_IN_PROGRESS, vision_statement={"name": "App"}
        )
        with patch("spec4.session.project_manager") as mock_pm:
            _persist_artifacts(session)
        mock_pm.save_vision.assert_not_called()

    def test_saves_stack_when_complete(self) -> None:
        stack = {"language": "Python"}
        session = self._base_session(
            stack_advisor_state=STATE_STACK_COMPLETE, stack_statement=stack
        )
        with patch("spec4.session.project_manager") as mock_pm:
            _persist_artifacts(session)
        mock_pm.save_stack.assert_called_once_with("/some/dir", stack)

    def test_saves_phases_when_complete(self) -> None:
        phases = [{"phase_number": 1}]
        session = self._base_session(phaser_state=STATE_PHASES_COMPLETE, phases=phases)
        with patch("spec4.session.project_manager") as mock_pm:
            _persist_artifacts(session)
        mock_pm.save_phases.assert_called_once_with("/some/dir", phases)

    def test_saves_code_review_when_complete(self) -> None:
        review: dict[str, Any] = {"code_review": {}}
        session = self._base_session(
            reviewer_state=STATE_REVIEW_COMPLETE, code_review=review
        )
        with patch("spec4.session.project_manager") as mock_pm:
            _persist_artifacts(session)
        mock_pm.save_code_review.assert_called_once_with("/some/dir", review)

    def test_updates_specmem_after_saving_vision(self) -> None:
        vision = {"name": "App"}
        session = self._base_session(
            brainstormer_state=STATE_VISION_COMPLETE, vision_statement=vision
        )
        with patch("spec4.session.project_manager") as mock_pm:
            _persist_artifacts(session)
        mock_pm.update_specmem_planning_state.assert_called()


class TestLoadWorkingDir:
    def _base_session(self) -> dict[str, Any]:
        s = _default_session()
        s["provider"] = "openai"
        s["api_key"] = "sk-test"
        return s

    def test_sets_working_dir_and_phase(self, tmp_path: pathlib.Path) -> None:
        session = _load_working_dir(str(tmp_path), self._base_session())
        assert session["working_dir"] == str(tmp_path)
        assert session["phase"] == "setup"

    def test_empty_dir_has_no_content_flags(self, tmp_path: pathlib.Path) -> None:
        session = _load_working_dir(str(tmp_path), self._base_session())
        assert session["_dir_has_content"] is False
        assert session["_warn_existing_content"] is False

    def test_dir_with_file_sets_content_flags(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / "app.py").write_text("x = 1")
        session = _load_working_dir(str(tmp_path), self._base_session())
        assert session["_dir_has_content"] is True
        assert session["_warn_existing_content"] is True

    def test_dir_with_code_review_suppresses_warn(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / "app.py").write_text("x = 1")
        spec4_dir = tmp_path / ".spec4"
        spec4_dir.mkdir()
        (spec4_dir / "code_review.json").write_text(
            json.dumps({"code_review": {"is_software_project": True}})
        )
        session = _load_working_dir(str(tmp_path), self._base_session())
        assert session["_warn_existing_content"] is False
        assert session["reviewer_state"] == STATE_REVIEW_COMPLETE

    def test_loads_vision_artifact(self, tmp_path: pathlib.Path) -> None:
        vision = {"vision_statement": {"name": "App"}}
        spec4_dir = tmp_path / ".spec4"
        spec4_dir.mkdir()
        (spec4_dir / "vision.json").write_text(json.dumps(vision))
        session = _load_working_dir(str(tmp_path), self._base_session())
        assert session["vision_statement"] == vision
        assert session["brainstormer_state"] == STATE_VISION_COMPLETE

    def test_artifact_exception_is_handled(self, tmp_path: pathlib.Path) -> None:
        with patch(
            "spec4.session.project_manager.load_spec4_artifacts",
            side_effect=OSError("disk error"),
        ):
            session = _load_working_dir(str(tmp_path), self._base_session())
        assert session["vision_statement"] is None
        assert session["brainstormer_state"] == STATE_IN_PROGRESS
