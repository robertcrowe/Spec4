"""Tests for :mod:`spec4.agents.code_scanner`, its project context and its review
schema.

Split out of ``tests/test_agents.py`` by source module, with every class unchanged
(Phase 8, D9: ``PHASE8_RECORD.md`` §25).
"""

from typing import Any
from unittest.mock import patch
import pytest
from spec4.agents import code_scanner
from spec4.app_constants import STATE_IN_PROGRESS, STATE_REVIEW_COMPLETE
from tests._agent_helpers import (
    _chunkify_stream,
    collect,
    make_session,
    mock_litellm_stream,
)


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
        from spec4.agents.code_scanner import extract_review_json

        text = '```json\n{"code_review": {"is_software_project": true}}\n```'
        assert extract_review_json(text) == {
            "code_review": {"is_software_project": True}
        }

    def test_extract_review_json_no_code_review_key_returns_none(self) -> None:
        from spec4.agents.code_scanner import extract_review_json

        assert extract_review_json('```json\n{"name": "App"}\n```') is None

    def test_extract_review_json_invalid_json_returns_none(self) -> None:
        from spec4.agents.code_scanner import extract_review_json

        assert extract_review_json("```json\n{bad}\n```") is None

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
        # Simulate a session persisted from before format_review_as_text was
        # fixed: msgs already has the synthetic pair but the assistant content
        # was generated from notes-as-string (single-char bullets).
        review = {"code_review": {"notes": "Directory is flat"}}
        stale_content = (
            "**Code Review Complete**\n\n**Notable Observations:**\n- D\n- i\n"
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
        from spec4.agents.code_scanner import format_review_as_text

        review = {"code_review": {"notes": "Directory is flat, no CI found"}}
        result = format_review_as_text(review)
        assert "- Directory is flat, no CI found" in result
        assert "- D\n" not in result

    def test_format_review_langs_as_string_renders_correctly(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

        review = {"code_review": {"languages": "Python", "frameworks": []}}
        result = format_review_as_text(review)
        assert "Python" in result
        assert "- P\n" not in result

    def test_format_review_renders_schema_v1_fields(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

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
        out = format_review_as_text(review)
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
        from spec4.agents.code_scanner import format_review_as_text

        review = {
            "code_review": {
                "schema_version": 1,
                "is_software_project": False,
                "summary": "Directory is empty.",
            }
        }
        out = format_review_as_text(review)
        assert "Code Review Complete" in out
        assert "Directory is empty." in out
        assert "Brainstormer" in out

    def test_format_review_renders_protocols_implemented(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

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
        out = format_review_as_text(review)
        assert "**Protocols Implemented:**" in out
        assert "A2A Protocol v1.0" in out
        assert "`arrg/a2a/`" in out
        assert "MCP v2025-11-25" in out
        assert "`arrg/mcp/`" in out
        # Absent → heading omitted.
        bare = {"code_review": {"is_software_project": True, "project_type": "CLI"}}
        assert "**Protocols Implemented:**" not in format_review_as_text(bare)

    def test_format_review_renders_ai_capabilities(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

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
        out = format_review_as_text(review)
        assert "**AI Capabilities:**" in out
        assert "anthropic [llm_api]" in out
        assert "Claude client drafting replies" in out
        assert "`src/app/ai/reply_drafter.py`" in out
        assert "- chromadb" in out
        # Absent → heading omitted.
        bare = {"code_review": {"is_software_project": True, "project_type": "CLI"}}
        assert "**AI Capabilities:**" not in format_review_as_text(bare)

    def test_system_prompt_documents_ai_capabilities(self) -> None:
        from spec4.agents.code_scanner import SYSTEM_PROMPT

        # All three prompt surfaces: the JSON exemplar / field-rule bullet
        # (schema key) and the draft-section list (display name).
        assert "ai_capabilities" in SYSTEM_PROMPT
        assert "AI Capabilities" in SYSTEM_PROMPT
        assert "agent_framework" in SYSTEM_PROMPT

    def test_format_review_renders_persistence(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

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
        out = format_review_as_text(review)
        assert "**Persistence:**" in out
        assert "PostgreSQL (primary)" in out
        assert "Redis (cache)" in out
        assert "ORM: SQLAlchemy" in out
        assert "migrations: Alembic" in out
        assert "`migrations/`" in out
        # Absent → heading omitted.
        bare = {"code_review": {"is_software_project": True, "project_type": "CLI"}}
        assert "**Persistence:**" not in format_review_as_text(bare)

    def test_format_review_renders_env_vars(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

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
        out = format_review_as_text(review)
        assert "**Environment Variables:**" in out
        assert "`DATABASE_URL`" in out and "(required)" in out
        assert "Postgres connection string" in out
        assert "`DASH_DEBUG`" in out and "(optional)" in out
        assert "`API_KEY`" in out

    def test_format_review_env_vars_never_leak_values(self) -> None:
        """Even if a malformed entry slips a value in, the renderer ignores it."""
        from spec4.agents.code_scanner import format_review_as_text

        review = {
            "code_review": {
                "is_software_project": True,
                "env_vars": [{"name": "SECRET_KEY", "value": "leaked-secret"}],
            }
        }
        out = format_review_as_text(review)
        assert "`SECRET_KEY`" in out
        assert "leaked-secret" not in out

    def test_format_review_renders_deployment(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

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
        out = format_review_as_text(review)
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
        assert "**Deployment:**" not in format_review_as_text(bare)

    def test_format_review_renders_api_surface(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

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
        out = format_review_as_text(review)
        assert "**API Surface:**" in out
        assert "[http]" in out and "GET /users/:id" in out
        assert "users.get_user" in out
        assert "[grpc]" in out and "UserService.GetUser" in out
        assert "Fetch a user by ID" in out

    def test_format_review_renders_auth(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

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
        out = format_review_as_text(review)
        assert "**Authentication:**" in out
        assert "oauth" in out
        assert "Auth0" in out
        assert "authlib" in out
        # Absent → heading omitted.
        bare = {"code_review": {"is_software_project": True}}
        assert "**Authentication:**" not in format_review_as_text(bare)

    def test_format_review_test_coverage_summary_preferred_over_lists(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

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
        out = format_review_as_text(review)
        assert "10 modules covered; UI layer uncovered" in out
        assert "should_be_ignored" not in out

    def test_format_review_ui_summary_has_ui_false_shows_none(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

        review = {
            "code_review": {
                "is_software_project": True,
                "ui_summary": {"has_ui": False, "kind": "none"},
            }
        }
        out = format_review_as_text(review)
        assert "**UI:** none" in out

    def test_update_mode_seeds_with_prior_review(self) -> None:
        from spec4.agents.code_scanner import build_update_scan_seed

        prior = {"code_review": {"is_software_project": True, "project_type": "CLI"}}
        seed = build_update_scan_seed("/tmp/does-not-matter", prior)
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
# gather_project_context tests
# ---------------------------------------------------------------------------


class TestGatherProjectContext:
    def test_empty_dir_reports_empty(self, tmp_path: Any) -> None:
        from spec4.agents.code_scanner import gather_project_context

        result = gather_project_context(str(tmp_path))
        assert "empty" in result.lower()

    def test_source_files_appear_in_tree(self, tmp_path: Any) -> None:
        from spec4.agents.code_scanner import gather_project_context

        (tmp_path / "main.py").write_text("print('hello')")
        result = gather_project_context(str(tmp_path))
        assert "main.py" in result

    def test_git_dir_is_skipped(self, tmp_path: Any) -> None:
        from spec4.agents.code_scanner import gather_project_context

        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]")
        result = gather_project_context(str(tmp_path))
        assert "config" not in result

    def test_readme_content_included_under_labeled_section(self, tmp_path: Any) -> None:
        from spec4.agents.code_scanner import gather_project_context

        (tmp_path / "README.md").write_text("# My Project\n\nA cool app.\n")
        result = gather_project_context(str(tmp_path))
        assert "### README Excerpt" in result
        assert "My Project" in result

    def test_source_file_sample_included(self, tmp_path: Any) -> None:
        from spec4.agents.code_scanner import gather_project_context

        (tmp_path / "app.py").write_text("def main():\n    pass\n")
        result = gather_project_context(str(tmp_path))
        assert "def main" in result

    def test_ci_workflow_files_detected(self, tmp_path: Any) -> None:
        from spec4.agents.code_scanner import gather_project_context

        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: CI\non: push\n")
        # need at least one non-CI file or _gather returns the empty placeholder
        (tmp_path / "main.py").write_text("print('x')")
        result = gather_project_context(str(tmp_path))
        assert "### CI / Workflow Files" in result
        assert "ci.yml" in result

    def test_dockerfile_detected_as_deployment_signal(self, tmp_path: Any) -> None:
        from spec4.agents.code_scanner import gather_project_context

        (tmp_path / "Dockerfile").write_text("FROM python:3.12\n")
        (tmp_path / "main.py").write_text("print('x')")
        result = gather_project_context(str(tmp_path))
        assert "### Deployment Signals" in result
        assert "Dockerfile" in result

    def test_terraform_directory_detected_as_deployment_signal(
        self, tmp_path: Any
    ) -> None:
        from spec4.agents.code_scanner import gather_project_context

        tf_dir = tmp_path / "terraform"
        tf_dir.mkdir()
        (tf_dir / "main.tf").write_text('resource "null_resource" "x" {}\n')
        (tmp_path / "main.py").write_text("print('x')")
        result = gather_project_context(str(tmp_path))
        assert "Terraform configuration detected" in result

    def test_entrypoint_files_prioritized_in_source_samples(
        self, tmp_path: Any
    ) -> None:
        from spec4.agents.code_scanner import gather_project_context

        # Create many alphabetically-earlier files so plain-alpha ordering
        # would push 'main.py' past the 8-file priority cutoff.
        for i in range(10):
            (tmp_path / f"a_aux_{i}.py").write_text(f"# helper {i}\n")
        (tmp_path / "main.py").write_text("def main():\n    pass\n")
        result = gather_project_context(str(tmp_path))
        # main.py should be sampled (and labeled as an entrypoint candidate)
        assert "main.py" in result
        assert "entrypoint candidate" in result


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
            "session",
            "jwt",
            "oauth",
            "sso",
            "api_key",
            "basic",
            "mtls",
            "none",
            "other",
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
            m
            for m in msgs
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
            m
            for m in session["code_scanner_messages"]
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

        with (
            patch("spec4.llm.litellm.completion", side_effect=fake_completion),
            patch(
                "spec4.llm.litellm.get_supported_openai_params",
                return_value=["temperature", "response_format"],
            ),
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

        with (
            patch("spec4.llm.litellm.completion", side_effect=fake_completion),
            patch(
                "spec4.llm.litellm.get_supported_openai_params",
                return_value=["temperature"],  # no response_format
            ),
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

        with (
            patch("spec4.llm.litellm.completion", side_effect=fake_completion),
            patch(
                "spec4.llm.litellm.get_supported_openai_params",
                return_value=["response_format"],
            ),
        ):
            collect(code_scanner.run("Confirm", session, session["llm_config"]))

        assert session["code_scanner_state"] == STATE_REVIEW_COMPLETE
        assert session["code_review"]["code_review"]["schema_version"] == 1


class TestCodeScannerUnparseableArtifact:
    """D-SC-P3: a finalize reply that was suppressed but cannot be parsed.

    ``_extract_and_validate_review`` reports "no JSON, still conversing" both
    when the model genuinely replied in prose and when it emitted an artifact
    block that came back malformed or truncated. The two are not the same: a
    reply opening with a fence was swallowed whole by ``stream_suppressing_json``
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

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            output = collect(
                code_scanner.run("looks good", session, session["llm_config"])
            )
        return session, output

    def test_truncated_block_is_retried(self) -> None:
        session, _ = self._run(self._truncated_review_text(), self._valid_review_text())
        assert session["code_scanner_state"] == STATE_REVIEW_COMPLETE
        assert session["code_review"]["code_review"]["schema_version"] == 1

    def test_retry_message_names_the_parse_failure(self) -> None:
        session, _ = self._run(self._truncated_review_text(), self._valid_review_text())
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
