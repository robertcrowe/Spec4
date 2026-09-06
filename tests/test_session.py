import json
import pathlib
from typing import Any
from unittest.mock import patch

import pytest

from spec4.app_constants import (
    PHASE_ROOT,
    STATE_DEPLOYER_COMPLETE,
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
    _reset_for_new_project,
    _run_agent_blocking,
)


class TestDefaultSession:
    def test_has_all_expected_keys(self) -> None:
        session = _default_session()
        required = [
            "working_dir",
            "browser_path",
            "phase",
            "provider",
            "model",
            "api_key",
            "available_models",
            "search_provider",
            "search_api_key",
            "setup_error",
            "agent_select_error",
            "llm_config",
            "messages",
            "active_agent",
            "code_scanner_state",
            "code_scanner_messages",
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
            "project_mode",
            "_initial_turn_done",
        ]
        for key in required:
            assert key in session, f"Missing key: {key}"

    def test_phase_is_the_unresolved_root(self) -> None:
        """A session that has never navigated names no screen.

        The router turns this into the project view or the directory picker;
        until it does, `render_page` draws an empty container, which is what
        keeps an intermediate screen off the page.
        """
        assert _default_session()["phase"] == PHASE_ROOT
        assert PHASE_ROOT != "landing"

    def test_no_directory_error_is_carried(self) -> None:
        assert _default_session()["dir_error"] is None

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

    def test_routes_to_code_scanner(self) -> None:
        session = self._session("code_scanner")
        with patch(
            "spec4.session.code_scanner.run", return_value=iter(["review"])
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
            "phase_version": 0,
            "brainstormer_state": STATE_IN_PROGRESS,
            "vision_statement": None,
            "stack_advisor_state": STATE_IN_PROGRESS,
            "stack_statement": None,
            "phaser_state": None,
            "phases": [],
            "code_scanner_state": STATE_IN_PROGRESS,
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
        mock_pm.save_vision.assert_called_once_with("/some/dir", vision, 0)

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
        mock_pm.save_stack.assert_called_once_with("/some/dir", stack, 0)

    def test_saves_phases_when_complete(self) -> None:
        phases = [{"phase_number": 1}]
        session = self._base_session(
            phaser_state=STATE_PHASES_COMPLETE, phases=phases, phase_version=2
        )
        with patch("spec4.session.project_manager") as mock_pm:
            _persist_artifacts(session)
        mock_pm.save_phases.assert_called_once_with(
            "/some/dir",
            phases,
            2,
            {
                "ai_features": None,
                "feature_specs": None,
                "stack": None,
                "manifest": mock_pm.load_design_manifest.return_value,
            },
        )

    def test_saves_phases_defaults_to_v0_without_version(self) -> None:
        phases = [{"phase_number": 1}]
        session = self._base_session(
            phaser_state=STATE_PHASES_COMPLETE, phases=phases, phase_version=0
        )
        with patch("spec4.session.project_manager") as mock_pm:
            _persist_artifacts(session)
        mock_pm.save_phases.assert_called_once_with(
            "/some/dir",
            phases,
            0,
            {
                "ai_features": None,
                "feature_specs": None,
                "stack": None,
                "manifest": mock_pm.load_design_manifest.return_value,
            },
        )

    def test_pins_v0_on_first_write_without_code_review(self) -> None:
        """When phase_version is None and no code_review, resolve pins v0."""
        vision = {"name": "App"}
        session = self._base_session(
            brainstormer_state=STATE_VISION_COMPLETE,
            vision_statement=vision,
            phase_version=None,
            code_review=None,
        )
        with patch("spec4.session.project_manager") as mock_pm:
            mock_pm.resolve_phase_version.return_value = (0, True)
            _persist_artifacts(session)
        assert session["phase_version"] == 0
        mock_pm.save_vision.assert_called_once_with("/some/dir", vision, 0)

    def test_saves_code_review_and_pins_v1(self) -> None:
        """When phase_version is None and code_review exists, resolve pins v1."""
        review: dict[str, Any] = {"schema_version": 1}
        session = self._base_session(
            code_scanner_state=STATE_REVIEW_COMPLETE,
            code_review=review,
            phase_version=None,
        )
        with patch("spec4.session.project_manager") as mock_pm:
            mock_pm.resolve_phase_version.return_value = (1, False)
            _persist_artifacts(session)
        assert session["phase_version"] == 1
        mock_pm.save_code_review.assert_called_once_with("/some/dir", review, 1)

    def test_saves_code_review_when_complete(self) -> None:
        review: dict[str, Any] = {"code_review": {}}
        session = self._base_session(
            code_scanner_state=STATE_REVIEW_COMPLETE, code_review=review
        )
        with patch("spec4.session.project_manager") as mock_pm:
            _persist_artifacts(session)
        mock_pm.save_code_review.assert_called_once_with("/some/dir", review, 0)

    def test_does_not_save_deployment_plan_without_markdown(self) -> None:
        """A returning user lands in Deployer with deployer_state=COMPLETE
        (lifted by _load_working_dir from disk presence) but no
        _deployer_plan_markdown. After any chat turn, _persist_artifacts must
        NOT overwrite the on-disk plan with a stray assistant message."""
        session = self._base_session(
            deployer_state=STATE_DEPLOYER_COMPLETE,
            _deployer_plan_markdown=None,
            deployer_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "Hi! Which coding agent…"},
            ],
        )
        with patch("spec4.session.project_manager") as mock_pm:
            _persist_artifacts(session)
        mock_pm.save_deployment_plan.assert_not_called()

    def test_does_not_save_when_markdown_lacks_deployment_steps(self) -> None:
        """Belt-and-suspenders: even if _deployer_plan_markdown is somehow set
        without the required header, refuse to save."""
        session = self._base_session(
            deployer_state=STATE_DEPLOYER_COMPLETE,
            _deployer_plan_markdown="No, keep the existing plan.",
        )
        with patch("spec4.session.project_manager") as mock_pm:
            _persist_artifacts(session)
        mock_pm.save_deployment_plan.assert_not_called()

    def test_saves_deployment_plan_when_markdown_set(self) -> None:
        plan = "# Deployment Plan\n\n## Deployment Steps\n\n### 1. Build\n…"
        session = self._base_session(
            deployer_state=STATE_DEPLOYER_COMPLETE,
            _deployer_plan_markdown=plan,
        )
        with patch("spec4.session.project_manager") as mock_pm:
            _persist_artifacts(session)
        mock_pm.save_deployment_plan.assert_called_once_with("/some/dir", plan, 0)

    def test_clears_markdown_and_marks_existed_after_save(self) -> None:
        plan = "# Deployment Plan\n\n## Deployment Steps\n\n…"
        session = self._base_session(
            deployer_state=STATE_DEPLOYER_COMPLETE,
            _deployer_plan_markdown=plan,
            _deployer_plan_existed=False,
        )
        with patch("spec4.session.project_manager"):
            _persist_artifacts(session)
        # Subsequent generations must trigger the confirmation flow.
        assert session["_deployer_plan_existed"] is True
        # Don't re-save the same content on the next persist tick.
        assert session["_deployer_plan_markdown"] is None

    def test_saves_readme_to_project_root_when_staged(self) -> None:
        readme = "# My App\n\nOverview.\n\n## Install\n\n`pip install .`\n"
        session = self._base_session(
            deployer_state=STATE_DEPLOYER_COMPLETE,
            _deployer_plan_markdown=None,
            _deployer_readme_markdown=readme,
        )
        with patch("spec4.session.project_manager") as mock_pm:
            _persist_artifacts(session)
        mock_pm.save_readme.assert_called_once_with("/some/dir", readme)
        # Cleared so it is not re-written on the next persist tick.
        assert session["_deployer_readme_markdown"] is None

    def test_does_not_save_readme_when_blank(self) -> None:
        session = self._base_session(
            deployer_state=STATE_DEPLOYER_COMPLETE,
            _deployer_readme_markdown="   \n  ",
        )
        with patch("spec4.session.project_manager") as mock_pm:
            _persist_artifacts(session)
        mock_pm.save_readme.assert_not_called()

    def test_does_not_save_readme_when_unstaged(self) -> None:
        session = self._base_session(
            deployer_state=STATE_DEPLOYER_COMPLETE,
            _deployer_plan_markdown=None,
        )
        with patch("spec4.session.project_manager") as mock_pm:
            _persist_artifacts(session)
        mock_pm.save_readme.assert_not_called()


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

    def test_project_mode_starts_unanswered(self, tmp_path: pathlib.Path) -> None:
        session = _load_working_dir(str(tmp_path), self._base_session())
        assert session["project_mode"] is None

    def test_picking_a_directory_reopens_the_question(
        self, tmp_path: pathlib.Path
    ) -> None:
        """D-PM1: an answer belongs to the directory it was given for."""
        prior = self._base_session()
        prior["project_mode"] = "existing"
        session = _load_working_dir(str(tmp_path), prior)
        assert session["project_mode"] is None

    def test_code_review_still_loads(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / "app.py").write_text("x = 1")
        v0_dir = tmp_path / ".spec4" / "v0"
        v0_dir.mkdir(parents=True)
        (v0_dir / "code_review.json").write_text(
            json.dumps({"code_review": {"is_software_project": True}})
        )
        session = _load_working_dir(str(tmp_path), self._base_session())
        assert session["code_scanner_state"] == STATE_REVIEW_COMPLETE
        # ...and does not answer the question on the developer's behalf: a
        # code review can legitimately exist for a greenfield skeleton.
        assert session["project_mode"] is None

    def test_loads_vision_artifact(self, tmp_path: pathlib.Path) -> None:
        vision = {"vision_statement": {"name": "App"}}
        v0_dir = tmp_path / ".spec4" / "v0"
        v0_dir.mkdir(parents=True)
        (v0_dir / "vision.json").write_text(json.dumps(vision))
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

    def test_preserves_llm_config_when_set(self, tmp_path: pathlib.Path) -> None:
        # A developer who has already chosen provider+model and picks a
        # different working directory should not be sent back through the
        # setup screen — _load_working_dir must preserve the LLM connection.
        s = self._base_session()
        s["model"] = "gpt-4o"
        s["available_models"] = ["gpt-4o", "gpt-4o-mini"]
        s["llm_config"] = {"model": "gpt-4o", "api_key": "sk-test"}
        s["tavily_api_key"] = "tvly-test"
        session = _load_working_dir(str(tmp_path), s)
        assert session["model"] == "gpt-4o"
        assert session["available_models"] == ["gpt-4o", "gpt-4o-mini"]
        assert session["llm_config"] == {"model": "gpt-4o", "api_key": "sk-test"}
        assert session["tavily_api_key"] == "tvly-test"

    def test_does_not_invent_llm_config_when_absent(
        self, tmp_path: pathlib.Path
    ) -> None:
        # First-time user: still routed through /setup because llm_config is
        # None. _load_working_dir must not synthesize one.
        session = _load_working_dir(str(tmp_path), self._base_session())
        assert session["llm_config"] is None
        assert session["model"] is None
        assert session["available_models"] is None

    def test_clears_previous_project_state(self, tmp_path: pathlib.Path) -> None:
        # Switching directories starts work on a different project. Previous
        # chat history, agent message logs, active-agent selection, and UI
        # display flags must NOT bleed into the new project — only the LLM
        # connection is preserved.
        prior = self._base_session()
        prior.update(
            {
                "working_dir": "/old/project",
                "active_agent": "deployer",
                "messages": [{"role": "user", "content": "old ui chat"}],
                "brainstormer_messages": [{"role": "user", "content": "old"}],
                "stack_advisor_messages": [{"role": "user", "content": "old"}],
                "phaser_messages": [{"role": "user", "content": "old"}],
                "code_scanner_messages": [{"role": "user", "content": "old"}],
                "deployer_messages": [{"role": "user", "content": "old"}],
                "_initial_turn_done": True,
                "_display_override": "stale override",
                "_stream_id": "abc-123",
                "agent_select_error": "previous error",
                "_deployer_plan_markdown": "# Old plan",
                "_deployer_pending_plan": True,
            }
        )
        session = _load_working_dir(str(tmp_path), prior)
        assert session["working_dir"] == str(tmp_path)
        assert session["messages"] == []
        assert session["brainstormer_messages"] == []
        assert session["stack_advisor_messages"] == []
        assert session["phaser_messages"] == []
        assert session["code_scanner_messages"] == []
        assert session["deployer_messages"] == []
        assert session["active_agent"] == "brainstormer"
        assert session["_initial_turn_done"] is False
        assert session.get("_display_override") in (None, "")
        assert session.get("_stream_id") is None
        assert session.get("agent_select_error") in (None, "")
        assert session.get("_deployer_plan_markdown") in (None, "")
        assert session.get("_deployer_pending_plan") in (None, False)


class TestLoadWorkingDirNewRound:
    """A pending brownfield round (the highest .spec4/v{N}/ holds an IMPLEMENTED
    marker, so the active round is v{N+1}) starts blank on technical artifacts.

    The prior round's vision/stack/phases/code_review are completed plans,
    superseded by the fresh CodeScanner review the new round is Required to
    produce first. Hydrating them as active/COMPLETE would let the persist
    funnel copy stale v{N} content into v{N+1} and pin phase_version to the old
    round. Only the prior product name is carried, as read-only reference.
    """

    def _base_session(self) -> dict[str, Any]:
        s = _default_session()
        s["provider"] = "openai"
        s["api_key"] = "sk-test"
        return s

    def _implemented_v0(self, tmp_path: pathlib.Path) -> None:
        v0 = tmp_path / ".spec4" / "v0"
        (v0 / "phases").mkdir(parents=True)
        (v0 / "vision.json").write_text(json.dumps({"name": "ShelfLife"}))
        (v0 / "stack.json").write_text(json.dumps({"libraries": {}}))
        (v0 / "code_review.json").write_text(
            json.dumps({"code_review": {"is_software_project": True}})
        )
        (v0 / "phases" / "phase1.md").write_text(
            '---\n{"phase_number": 1, "title": "P1"}\n---\n\n# Phase 1\n'
        )
        (v0 / "IMPLEMENTED").write_text("")

    def test_does_not_hydrate_prior_artifacts(
        self, tmp_path: pathlib.Path
    ) -> None:
        self._implemented_v0(tmp_path)
        session = _load_working_dir(str(tmp_path), self._base_session())
        assert session["vision_statement"] is None
        assert session["stack_statement"] is None
        assert session["phases"] == []
        assert session["code_review"] is None
        assert session["brainstormer_state"] == STATE_IN_PROGRESS
        assert session["stack_advisor_state"] == STATE_IN_PROGRESS
        assert session["code_scanner_state"] == STATE_IN_PROGRESS

    def test_leaves_phase_version_none(self, tmp_path: pathlib.Path) -> None:
        # phase_version None lets the persist funnel resolve the new round's
        # version (max + 1) rather than overwriting the implemented round.
        self._implemented_v0(tmp_path)
        session = _load_working_dir(str(tmp_path), self._base_session())
        assert session["phase_version"] is None

    def test_stashes_prior_app_name(self, tmp_path: pathlib.Path) -> None:
        self._implemented_v0(tmp_path)
        session = _load_working_dir(str(tmp_path), self._base_session())
        assert session["_prior_app_name"] == "ShelfLife"

    def test_in_progress_round_still_hydrates(
        self, tmp_path: pathlib.Path
    ) -> None:
        # No IMPLEMENTED marker: the highest round is in progress and must still
        # load for resume — the new-round guard must not fire here.
        v0 = tmp_path / ".spec4" / "v0"
        v0.mkdir(parents=True)
        (v0 / "vision.json").write_text(json.dumps({"name": "ShelfLife"}))
        session = _load_working_dir(str(tmp_path), self._base_session())
        assert session["vision_statement"] == {"name": "ShelfLife"}
        assert session["brainstormer_state"] == STATE_VISION_COMPLETE
        assert session.get("_prior_app_name") is None


class TestResetForNewProject:
    """The "Start New Project" action in Deployer must clear every
    project-specific field but keep the developer's LLM configuration so
    they aren't forced back through the provider/model/Tavily wizard."""

    def _configured_session(self) -> dict[str, Any]:
        return {
            **_default_session(),
            "working_dir": "/old/project",
            "browser_path": "/old/project",
            "phase": "chat",
            "provider": "openai",
            "api_key": "sk-test",
            "model": "gpt-4o",
            "available_models": ["gpt-4o", "gpt-4o-mini"],
            "llm_config": {"model": "gpt-4o", "api_key": "sk-test"},
            "tavily_api_key": "tvly-test",
            "active_agent": "deployer",
            "vision_statement": {"name": "OldApp"},
            "stack_statement": {"language": "Python"},
            "phases": [{"phase_number": 1, "phase_title": "Bootstrap"}],
            "code_review": {"summary": "ok"},
            "brainstormer_state": STATE_VISION_COMPLETE,
            "stack_advisor_state": STATE_STACK_COMPLETE,
            "phaser_state": STATE_PHASES_COMPLETE,
            "code_scanner_state": STATE_REVIEW_COMPLETE,
            "deployer_state": "deployer_complete",
            "brainstormer_messages": [{"role": "user", "content": "old"}],
            "stack_advisor_messages": [{"role": "user", "content": "old"}],
            "phaser_messages": [{"role": "user", "content": "old"}],
            "code_scanner_messages": [{"role": "user", "content": "old"}],
            "deployer_messages": [{"role": "user", "content": "old"}],
            "messages": [{"role": "user", "content": "ui display"}],
            "_deployer_plan_existed": True,
            "_deployer_plan_markdown": "# Old plan…",
            "_deployer_pending_plan": False,
            "deployer_stale_acknowledged": {"phases": 1.0},
            "brainstormer_resumed": True,
        }

    def test_preserves_llm_setup(self) -> None:
        fresh = _reset_for_new_project(self._configured_session())
        assert fresh["provider"] == "openai"
        assert fresh["api_key"] == "sk-test"
        assert fresh["model"] == "gpt-4o"
        assert fresh["available_models"] == ["gpt-4o", "gpt-4o-mini"]
        assert fresh["llm_config"] == {"model": "gpt-4o", "api_key": "sk-test"}
        assert fresh["tavily_api_key"] == "tvly-test"

    def test_clears_working_dir(self) -> None:
        fresh = _reset_for_new_project(self._configured_session())
        assert fresh["working_dir"] is None
        assert fresh["browser_path"] is None

    def test_clears_artifacts(self) -> None:
        fresh = _reset_for_new_project(self._configured_session())
        assert fresh["vision_statement"] is None
        assert fresh["stack_statement"] is None
        assert fresh["phases"] == []
        assert fresh["code_review"] is None

    def test_clears_agent_states(self) -> None:
        # Agent-select-page checkboxes are driven by these fields. Resetting
        # them is the whole point of "Start New Project".
        fresh = _reset_for_new_project(self._configured_session())
        assert fresh["brainstormer_state"] == STATE_IN_PROGRESS
        assert fresh["stack_advisor_state"] == STATE_IN_PROGRESS
        assert fresh["phaser_state"] is None
        assert fresh["code_scanner_state"] == STATE_IN_PROGRESS
        assert fresh["deployer_state"] == STATE_IN_PROGRESS

    def test_clears_message_logs(self) -> None:
        fresh = _reset_for_new_project(self._configured_session())
        assert fresh["brainstormer_messages"] == []
        assert fresh["stack_advisor_messages"] == []
        assert fresh["phaser_messages"] == []
        assert fresh["code_scanner_messages"] == []
        assert fresh["deployer_messages"] == []
        assert fresh["messages"] == []

    def test_clears_deployer_plan_state(self) -> None:
        # Critical: the new project must NOT inherit the previous plan's
        # "_deployer_plan_existed" flag, or the next plan generated would be
        # treated as a replacement and gated behind the confirmation prompt.
        fresh = _reset_for_new_project(self._configured_session())
        assert fresh.get("_deployer_plan_existed") in (None, False)
        assert fresh.get("_deployer_plan_markdown") in (None, "")
        assert fresh.get("_deployer_pending_plan") in (None, False)

    def test_clears_resume_and_staleness_state(self) -> None:
        fresh = _reset_for_new_project(self._configured_session())
        assert fresh["deployer_stale_acknowledged"] == {}
        assert fresh.get("brainstormer_resumed") in (None, False)

    def test_handles_empty_session(self) -> None:
        # A defensively-called reset on an empty session shouldn't crash.
        fresh = _reset_for_new_project({})
        assert fresh["provider"] is None
        assert fresh["api_key"] is None
        assert fresh["llm_config"] is None
        assert fresh["working_dir"] is None
