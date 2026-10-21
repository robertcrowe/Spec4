"""Tests for :mod:`spec4.agents.code_scanner`, its project context and its review
schema.

Split out of ``tests/test_agents.py`` by source module, with every class unchanged
(Phase 8, D9: ``PHASE8_RECORD.md`` §25).
"""

import json
import pathlib
from typing import Any
from unittest.mock import patch
import pytest
from spec4.agents import code_scanner
from spec4.agents._code_review_schema import CODE_REVIEW_SCHEMA_VERSION
from spec4.app_constants import STATE_IN_PROGRESS, STATE_REVIEW_COMPLETE
from spec4.layouts._chat_actions import _code_scanner_action_buttons
from tests._golden import load_fixture
from tests._review_helpers import review_envelope
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
            code_scanner_scan={},
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ],
        )
        with mock_litellm_stream("Here is my review."):
            output = collect(
                code_scanner.run("Looks good", session, session["llm_config"])
            )
        assert "Here is my review." in output

    def test_review_json_sets_state_complete(self) -> None:
        session = make_session(
            code_scanner_scan={},
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ],
        )
        review_response = '```json\n{"review": {"is_software_project": true}}\n```'
        with mock_litellm_stream(review_response):
            collect(code_scanner.run("Confirm", session, session["llm_config"]))
        assert session["code_scanner_state"] == STATE_REVIEW_COMPLETE
        # D-EV2/D-EV4: the model emitted the bare ``review`` block; the stored
        # envelope carries the code-owned version and an empty ``scan``.
        assert session["code_review"] == review_envelope()

    def test_non_review_response_stays_in_progress(self) -> None:
        session = make_session(
            code_scanner_scan={},
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ],
        )
        with mock_litellm_stream("Tell me about section 1."):
            collect(code_scanner.run("Go on", session, session["llm_config"]))
        assert session["code_scanner_state"] == STATE_IN_PROGRESS
        assert session["code_review"] is None

    def test_extract_review_json_valid(self) -> None:
        from spec4.agents.code_scanner import extract_review_json

        text = '```json\n{"review": {"is_software_project": true}}\n```'
        assert extract_review_json(text) == {"review": {"is_software_project": True}}

    def test_extract_review_json_no_review_key_returns_none(self) -> None:
        from spec4.agents.code_scanner import extract_review_json

        assert extract_review_json('```json\n{"name": "App"}\n```') is None

    def test_extract_review_json_invalid_json_returns_none(self) -> None:
        from spec4.agents.code_scanner import extract_review_json

        assert extract_review_json("```json\n{bad}\n```") is None

    def test_initialises_code_scanner_messages_if_missing(self) -> None:
        session = make_session(
            code_scanner_scan={},
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ],
        )
        del session["code_scanner_messages"]
        with mock_litellm_stream("Ok"):
            collect(code_scanner.run("Hi", session, session["llm_config"]))
        assert "code_scanner_messages" in session

    def test_brownfield_display_shows_existing_review_without_llm(self) -> None:
        review = {
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {"is_software_project": True, "project_type": "CLI tool"},
            }
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
        review = {
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {"notes": "Directory is flat"},
            }
        }
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
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {"is_software_project": True, "project_type": "web app"},
            }
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

        review = {
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {"notes": "Directory is flat, no CI found"},
            }
        }
        result = format_review_as_text(review)
        assert "- Directory is flat, no CI found" in result
        assert "- D\n" not in result

    def test_format_review_langs_as_string_renders_correctly(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

        review = {
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {"languages": "Python", "frameworks": []},
            }
        }
        result = format_review_as_text(review)
        assert "Python" in result
        assert "- P\n" not in result

    def test_format_review_renders_schema_v1_fields(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

        review = {
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {
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
                        {
                            "name": "dash",
                            "purpose": "Web UI",
                            "source": "pyproject.toml",
                        }
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
                "schema_version": 2,
                "scan": {},
                "review": {
                    "is_software_project": False,
                    "summary": "Directory is empty.",
                },
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
                "schema_version": 2,
                "scan": {},
                "review": {
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
                },
            }
        }
        out = format_review_as_text(review)
        assert "**Protocols Implemented:**" in out
        assert "A2A Protocol v1.0" in out
        assert "`arrg/a2a/`" in out
        assert "MCP v2025-11-25" in out
        assert "`arrg/mcp/`" in out
        # Absent → heading omitted.
        bare = {
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {"is_software_project": True, "project_type": "CLI"},
            }
        }
        assert "**Protocols Implemented:**" not in format_review_as_text(bare)

    def test_format_review_renders_ai_capabilities(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

        review = {
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {
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
                },
            }
        }
        out = format_review_as_text(review)
        assert "**AI Capabilities:**" in out
        assert "anthropic [llm_api]" in out
        assert "Claude client drafting replies" in out
        assert "`src/app/ai/reply_drafter.py`" in out
        assert "- chromadb" in out
        # Absent → heading omitted.
        bare = {
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {"is_software_project": True, "project_type": "CLI"},
            }
        }
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
                "schema_version": 2,
                "scan": {},
                "review": {
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
        bare = {
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {"is_software_project": True, "project_type": "CLI"},
            }
        }
        assert "**Persistence:**" not in format_review_as_text(bare)

    def test_format_review_renders_env_vars(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

        review = {
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {
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
                },
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
                "schema_version": 2,
                "scan": {},
                "review": {
                    "is_software_project": True,
                    "env_vars": [{"name": "SECRET_KEY", "value": "leaked-secret"}],
                },
            }
        }
        out = format_review_as_text(review)
        assert "`SECRET_KEY`" in out
        assert "leaked-secret" not in out

    def test_format_review_renders_deployment(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

        review = {
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {
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
        bare = {
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {"is_software_project": True},
            }
        }
        assert "**Deployment:**" not in format_review_as_text(bare)

    def test_format_review_renders_api_surface(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

        review = {
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {
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
                },
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
                "schema_version": 2,
                "scan": {},
                "review": {
                    "is_software_project": True,
                    "auth": {
                        "model": "oauth",
                        "provider": "Auth0",
                        "library": "authlib",
                    },
                },
            }
        }
        out = format_review_as_text(review)
        assert "**Authentication:**" in out
        assert "oauth" in out
        assert "Auth0" in out
        assert "authlib" in out
        # Absent → heading omitted.
        bare = {
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {"is_software_project": True},
            }
        }
        assert "**Authentication:**" not in format_review_as_text(bare)

    def test_format_review_test_coverage_summary_preferred_over_lists(self) -> None:
        from spec4.agents.code_scanner import format_review_as_text

        review = {
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {
                    "is_software_project": True,
                    "notes": {
                        "test_coverage": {
                            "has_tests": True,
                            "framework": "pytest",
                            "coverage_summary": (
                                "10 modules covered; UI layer uncovered"
                            ),
                            "covered_modules": ["should_be_ignored"],
                        }
                    },
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
                "schema_version": 2,
                "scan": {},
                "review": {
                    "is_software_project": True,
                    "ui_summary": {"has_ui": False, "kind": "none"},
                },
            }
        }
        out = format_review_as_text(review)
        assert "**UI:** none" in out

    def test_update_mode_seeds_with_prior_review(self) -> None:
        from spec4.agents.code_scanner import build_update_scan_seed

        prior = review_envelope(
            project_type="CLI", scan={"inventory": {"files_total": 9}}
        )
        seed = build_update_scan_seed("/tmp/does-not-matter", prior)
        assert "Update mode instructions" in seed
        assert "Prior code review on disk" in seed
        assert "project_type" in seed
        assert "Added / Removed / Changed" in seed
        assert "updated `review` JSON block" in seed
        # D-EV6: the scanner's model sees the ``review`` layer only.
        assert "files_total" not in seed
        assert '"scan"' not in seed
        assert '"schema_version"' not in seed
        assert '"code_review"' not in seed

    def test_update_seed_carries_the_previously_omitted_label(self) -> None:
        # 2.9.2 (D-SC5-5): a prior-review omission is not a project change.
        from spec4.agents.code_scanner import build_update_scan_seed

        seed = build_update_scan_seed("/tmp/does-not-matter", review_envelope())
        body = " ".join(seed.split())
        assert "Added / Removed / Changed." in body
        assert (
            "is marked **Previously omitted**, not Added: it is a completeness "
            "fix in the review, not a change in the project." in body
        )

    def test_update_seed_strips_what_spec4_recomputes(self) -> None:
        # 2.9.2 (D-SC5-1): the update seed pastes the prior ``review`` minus
        # the fields ``wrap_review`` overwrites at commit — ``consumers``,
        # the computed reconciliation fields, ``classification`` — which only
        # cost tokens and had the model announcing it would drop them.
        from spec4.agents.code_scanner import (
            _prior_review_for_update_seed,
            build_update_scan_seed,
        )

        prior = review_envelope(
            project_type="CLI",
            load_bearing=[
                {
                    "module": "a.py",
                    "role": "r",
                    "contract": {"inputs": ["x"]},
                    "consumers": ["b.py", "c.py"],
                },
                "not-a-dict",
            ],
            prior_round_reconciliation=[
                {
                    "phase_number": 1,
                    "title": "One",
                    "verdict": "evidence_found",
                    "implemented_ids": ["f"],
                    "paths": ["a.py"],
                    "features": [{"id": "f", "statuses": ["complete"]}],
                },
                {
                    "phase_number": 2,
                    "title": "Two",
                    "verdict": "evidence_partial",
                    "implemented_ids": [],
                    "paths": [],
                    "features": [{"id": "g", "statuses": []}],
                    "gap": "g is unclaimed",
                    "source": "README.md",
                    "inferred_from": "src/",
                },
                "not-a-dict",
            ],
            unplanned_changes=[
                {"area": "x", "classification": "out_of_round", "affects": ["a.py"]},
                7,
            ],
        )
        stripped = _prior_review_for_update_seed(prior)
        assert stripped["project_type"] == "CLI"
        assert stripped["load_bearing"] == [
            {"module": "a.py", "role": "r", "contract": {"inputs": ["x"]}},
            "not-a-dict",
        ]
        assert stripped["prior_round_reconciliation"] == [
            {
                "phase_number": 2,
                "gap": "g is unclaimed",
                "source": "README.md",
                "inferred_from": "src/",
            }
        ]
        assert stripped["unplanned_changes"] == [{"area": "x", "affects": ["a.py"]}, 7]
        # Order of the surviving keys is the prior's.
        assert list(stripped) == list(prior["code_review"]["review"])
        # The prior itself is untouched, and the seed carries the stripped one.
        assert prior["code_review"]["review"]["load_bearing"][0]["consumers"] == [
            "b.py",
            "c.py",
        ]
        seed = build_update_scan_seed("/tmp/does-not-matter", prior)
        assert '"consumers"' not in seed
        assert '"verdict"' not in seed
        assert '"classification"' not in seed
        assert '"gap": "g is unclaimed"' in seed

    def test_update_seed_drops_a_reconciliation_with_no_gap_at_all(self) -> None:
        # Six ``evidence_found`` phases (BWS4 v9) carry nothing the model
        # wrote, so the key goes rather than six ``{phase_number}`` stubs; a
        # review without the arrays, or with malformed ones, passes through.
        from spec4.agents.code_scanner import _prior_review_for_update_seed

        prior = review_envelope(
            prior_round_reconciliation=[
                {"phase_number": n, "verdict": "evidence_found"} for n in (1, 2)
            ]
            + [{"phase_number": 3, "gap": ""}],
        )
        assert "prior_round_reconciliation" not in _prior_review_for_update_seed(prior)
        plain = review_envelope(project_type="CLI")
        assert _prior_review_for_update_seed(plain) == {
            "is_software_project": True,
            "project_type": "CLI",
        }
        odd = review_envelope(
            load_bearing="x", prior_round_reconciliation=3, unplanned_changes={}
        )
        assert _prior_review_for_update_seed(odd)["load_bearing"] == "x"
        assert _prior_review_for_update_seed(odd)["prior_round_reconciliation"] == 3
        assert _prior_review_for_update_seed(odd)["unplanned_changes"] == {}
        assert _prior_review_for_update_seed({}) == {}

    def test_seed_prior_review_reader_handles_each_shape(self) -> None:
        from spec4.agents.code_scanner import _prior_review_for_seed

        v2 = review_envelope(project_type="CLI", scan={"x": 1})
        assert _prior_review_for_seed(v2) == {
            "is_software_project": True,
            "project_type": "CLI",
        }
        v1 = {"code_review": {"schema_version": 1, "project_type": "CLI"}}
        assert _prior_review_for_seed(v1) == {"project_type": "CLI"}
        assert _prior_review_for_seed({"code_review": "x"}) == {}
        assert _prior_review_for_seed({}) == {}

    def test_wrap_review_attaches_the_code_owned_layers(self) -> None:
        from spec4.agents.code_scanner import wrap_review

        block = {"review": {"is_software_project": True, "project_type": "CLI"}}
        assert wrap_review(block) == review_envelope(project_type="CLI")
        scan = {"inventory": {"files_total": 2}}
        assert wrap_review(block, scan) == review_envelope(
            project_type="CLI", scan=scan
        )

    def test_commit_refuses_an_envelope_that_fails_validation(self) -> None:
        # D-EV3: the block passed its own check; a wrapper bug must not reach
        # the session or disk.
        from spec4.agents.code_scanner import _scanner_commit

        session = make_session(
            code_scanner_scan={},
            code_scanner_messages=[{"role": "assistant", "content": ""}],
        )
        bad = {"code_review": {"schema_version": 1, "is_software_project": True}}
        with (
            patch("spec4.agents.code_scanner.wrap_review", return_value=bad),
            pytest.raises(ValueError, match="failed validation"),
        ):
            _scanner_commit(session, session["code_scanner_messages"], {"review": {}})
        assert session["code_review"] is None
        assert session["code_scanner_state"] != STATE_REVIEW_COMPLETE

    def test_rescan_enters_update_mode_when_review_exists(self) -> None:
        # Simulate the state immediately after on_rescan_project: prior review
        # is kept in session but state and msgs are reset.
        review = {
            "code_review": {
                "schema_version": 2,
                "scan": {},
                "review": {"is_software_project": True, "project_type": "web"},
            }
        }
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

    def test_stale_schema_seeds_fresh_scan_with_prior_as_context(
        self, tmp_path: Any
    ) -> None:
        # D-SV3/D-SV4: a review on disk under an older schema_version is loaded
        # into the session as complete, exactly as a current one is — but the
        # first entry must scan rather than display it, and the seed is the
        # fresh one carrying the prior review as context, never the update seed.
        stale = {
            "code_review": {
                "schema_version": CODE_REVIEW_SCHEMA_VERSION - 1,
                "is_software_project": True,
                "project_type": "CLI",
            }
        }
        v0 = tmp_path / ".spec4" / "v0"
        v0.mkdir(parents=True)
        (v0 / "code_review.json").write_text(json.dumps(stale), encoding="utf-8")
        session = make_session(
            code_review=stale,
            code_scanner_state=STATE_REVIEW_COMPLETE,
            code_scanner_messages=[],
            working_dir=str(tmp_path),
        )
        with mock_litellm_stream("(LLM fresh response)"):
            out = collect(code_scanner.run(None, session, session["llm_config"]))
        assert "Re-scanning" in out
        seed = session["code_scanner_messages"][0]["content"]
        assert "Update mode" not in seed
        assert "Added / Removed / Changed" not in seed
        assert "older schema" in seed
        assert '"project_type": "CLI"' in seed
        # The schema-1 inner dict is pasted as the review, minus its version.
        assert '"schema_version"' not in seed
        assert "Emit the `review` block" in seed

    def test_stale_rescan_drops_the_complete_state_until_commit(
        self, tmp_path: Any
    ) -> None:
        # The loaded state is complete (the file on disk parsed), and the chat
        # action row keys on that state alone — so during the correction turn
        # it offered Open / Download / Continue for the stale file. The stale
        # branch now flips the state as the Re-scan button does, keeping
        # `code_review` as the seed's prior context; the commit restores it.
        stale = {
            "code_review": {
                "schema_version": CODE_REVIEW_SCHEMA_VERSION - 1,
                "is_software_project": True,
                "project_type": "CLI",
            }
        }
        v0 = tmp_path / ".spec4" / "v0"
        v0.mkdir(parents=True)
        (v0 / "code_review.json").write_text(json.dumps(stale), encoding="utf-8")
        session = make_session(
            code_review=stale,
            code_scanner_state=STATE_REVIEW_COMPLETE,
            code_scanner_messages=[],
            working_dir=str(tmp_path),
        )
        with mock_litellm_stream("Anything to correct?"):
            collect(code_scanner.run(None, session, session["llm_config"]))
        assert session["code_scanner_state"] == STATE_IN_PROGRESS
        assert session["code_review"] == stale
        ids = {getattr(b, "id", None) for b in _code_scanner_action_buttons(session)}
        assert "btn-review-to-brainstormer" not in ids
        assert "btn-dl-review" not in ids
        assert "chat-token-count" in ids

    def test_in_round_rescan_stashes_the_session_review_as_the_prior(self) -> None:
        # 2.11.0: the commit reads one key for the carry's prior on both doors.
        review = review_envelope(project_type="web")
        session = make_session(
            code_review=review,
            code_scanner_state=STATE_IN_PROGRESS,
            working_dir="/tmp/not-real-but-not-empty",
        )
        with mock_litellm_stream("(LLM update response)"):
            collect(code_scanner.run(None, session, session["llm_config"]))
        assert session["code_scanner_prior"] == review
        assert session["code_review"] == review

    def test_current_schema_still_displays_existing_review(self, tmp_path: Any) -> None:
        # The inverse: a review under the current schema keeps the display
        # short-circuit — no scan, no seed appended.
        current = review_envelope(project_type="CLI")
        v0 = tmp_path / ".spec4" / "v0"
        v0.mkdir(parents=True)
        (v0 / "code_review.json").write_text(json.dumps(current), encoding="utf-8")
        session = make_session(
            code_review=current,
            code_scanner_state=STATE_REVIEW_COMPLETE,
            code_scanner_messages=[],
            working_dir=str(tmp_path),
        )
        out = collect(code_scanner.run(None, session, session["llm_config"]))
        assert "Re-scanning" not in out
        assert session["code_scanner_messages"][0]["content"] == (
            "[Spec4: displaying existing code review]"
        )


def _new_round_project(tmp_path: pathlib.Path, prior: dict[str, Any] | None) -> None:
    """A small tree whose previous round (v9) is implemented and holds ``prior``.

    The session loads no review for such a project (``brownfield_new_round_pending``),
    which until 2.11.0 made the scan a fresh one.
    """
    (tmp_path / "README.md").write_text("# App\n\nA thing.\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def main() -> None:\n    pass\n")
    (tmp_path / "src" / "config.py").write_text("HOURLY_LIMIT = 5\n")
    v9 = tmp_path / ".spec4" / "v9"
    v9.mkdir(parents=True)
    (v9 / "IMPLEMENTED").write_text("", encoding="utf-8")
    if prior is not None:
        (v9 / "code_review.json").write_text(json.dumps(prior), encoding="utf-8")


def _implemented_prior() -> dict[str, Any]:
    """A schema-2 prior whose listing matches the tree, so the delta names nothing."""
    return review_envelope(
        scan={
            "inventory": {
                "files_total": 3,
                "files_listed": 3,
                "truncated": False,
                "listed": ["README.md", "src/app.py", "src/config.py"],
            }
        },
        project_type="CLI",
        env_vars=[
            {"name": "DATABASE_URL", "purpose": "db", "source": ".env.example"},
            {"name": "HOURLY_LIMIT", "purpose": "cap", "source": "src/config.py"},
        ],
    )


class TestNewRoundScan:
    # 2.11.0 (D-SC5-13…15): the first scan of a new brownfield round draws the
    # update seed against the previous round's review on disk and carries
    # against it at commit — the BWS4 2.10.0 scans showed this door opening on
    # the fresh seed with ``prior=None`` while ``delta`` named the v9 review.

    def test_the_previous_round_s_review_opens_the_update_seed(
        self, tmp_path: pathlib.Path
    ) -> None:
        prior = _implemented_prior()
        _new_round_project(tmp_path, prior)
        session = make_session(working_dir=str(tmp_path))
        assert session["code_review"] is None
        with mock_litellm_stream("Anything to correct?"):
            out = collect(code_scanner.run(None, session, session["llm_config"]))
        assert "Re-scanning" in out
        seed = session["code_scanner_messages"][0]["content"]
        assert "Update mode" in seed
        assert "Prior code review on disk" in seed
        assert "**Paths this scan changed**" in seed
        assert '"name": "HOURLY_LIMIT"' in seed
        assert "older schema" not in seed
        # The prior is stashed for the commit; the new round's review is not
        # minted until then, so the /agents gate still reads a pending round.
        assert session["code_scanner_prior"] == prior
        assert session["code_review"] is None
        assert session["code_scanner_state"] == STATE_IN_PROGRESS
        assert session["code_scanner_scan"]["delta"]["prior"]["version"] == 9

    def test_the_commit_carries_against_the_disk_prior_and_clears_the_stash(
        self, tmp_path: pathlib.Path
    ) -> None:
        from tests._review_helpers import review_block_text

        _new_round_project(tmp_path, _implemented_prior())
        session = make_session(working_dir=str(tmp_path))
        with mock_litellm_stream("Anything to correct?"):
            collect(code_scanner.run(None, session, session["llm_config"]))
        emitted = [{"name": "DATABASE_URL", "purpose": "re-derived", "source": ".env"}]
        with mock_litellm_stream(review_block_text(env_vars=emitted)):
            collect(code_scanner.run("looks good", session, session["llm_config"]))
        assert session["code_scanner_state"] == STATE_REVIEW_COMPLETE
        stored = session["code_review"]["code_review"]["review"]
        # The model's entry wins; the untouched config.py entry comes back.
        assert stored["env_vars"] == [
            *emitted,
            {"name": "HOURLY_LIMIT", "purpose": "cap", "source": "src/config.py"},
        ]
        assert session["code_scanner_prior"] is None
        assert session["code_scanner_scan"] is None

    def test_an_older_schema_prior_opens_the_fresh_seed_with_context_and_no_carry(
        self, tmp_path: pathlib.Path
    ) -> None:
        from tests._review_helpers import review_block_text

        stale = {
            "code_review": {
                "schema_version": CODE_REVIEW_SCHEMA_VERSION - 1,
                "is_software_project": True,
                "project_type": "CLI",
                "env_vars": [
                    {"name": "OLD", "purpose": "x", "source": "src/config.py"}
                ],
            }
        }
        _new_round_project(tmp_path, stale)
        session = make_session(working_dir=str(tmp_path))
        with mock_litellm_stream("Anything to correct?"):
            out = collect(code_scanner.run(None, session, session["llm_config"]))
        assert "Re-scanning" in out
        seed = session["code_scanner_messages"][0]["content"]
        assert "Update mode" not in seed
        assert "older schema" in seed
        assert '"project_type": "CLI"' in seed
        assert session["code_scanner_prior"] == stale
        with mock_litellm_stream(review_block_text(env_vars=[])):
            collect(code_scanner.run("looks good", session, session["llm_config"]))
        assert session["code_review"]["code_review"]["review"]["env_vars"] == []
        assert session["code_scanner_prior"] is None

    def test_no_prior_on_disk_is_a_fresh_scan(self, tmp_path: pathlib.Path) -> None:
        _new_round_project(tmp_path, None)
        session = make_session(working_dir=str(tmp_path))
        with mock_litellm_stream("Anything to correct?"):
            out = collect(code_scanner.run(None, session, session["llm_config"]))
        assert "Scanning" in out
        assert "Re-scanning" not in out
        seed = session["code_scanner_messages"][0]["content"]
        assert "Update mode" not in seed
        assert "older schema" not in seed
        assert session["code_scanner_prior"] is None
        assert "delta" not in session["code_scanner_scan"]

    def test_the_seed_s_prior_is_the_delta_s_prior(
        self, tmp_path: pathlib.Path
    ) -> None:
        # D-SC5-14: one resolver — the envelope the seed pasted is the file
        # whose scan ``delta.prior`` describes.
        prior = _implemented_prior()
        prior["code_review"]["scan"]["git"] = {"available": True, "head": "abc1234"}
        _new_round_project(tmp_path, prior)
        session = make_session(working_dir=str(tmp_path))
        with mock_litellm_stream("Anything to correct?"):
            collect(code_scanner.run(None, session, session["llm_config"]))
        assert session["code_scanner_scan"]["delta"]["prior"] == {
            "kind": "implemented",
            "version": 9,
            "head": "abc1234",
            "producer": None,
        }
        assert session["code_scanner_prior"]["code_review"]["scan"]["git"]["head"] == (
            "abc1234"
        )


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
    """Direct tests of the validate_review_block() schema check (the LLM's block)."""

    def test_minimal_valid_review_passes(self) -> None:
        from spec4.agents._code_review_schema import validate_review_block

        data = {"review": {"is_software_project": True}}
        assert validate_review_block(data) == []

    def test_empty_project_review_passes(self) -> None:
        from spec4.agents._code_review_schema import validate_review_block

        data = {
            "review": {
                "is_software_project": False,
                "summary": "Directory contained only a CNAME file.",
            }
        }
        assert validate_review_block(data) == []

    def test_valid_ui_kind_enum_passes(self) -> None:
        from spec4.agents._code_review_schema import validate_review_block

        for kind in ("spa", "mpa", "mobile", "desktop", "tui", "none"):
            data = {
                "review": {
                    "is_software_project": True,
                    "ui_summary": {"has_ui": kind != "none", "kind": kind},
                }
            }
            assert validate_review_block(data) == [], f"kind={kind} should pass"

    def test_protocols_implemented_entry_validates(self) -> None:
        from spec4.agents._code_review_schema import validate_review_block

        data = {
            "review": {
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
        assert validate_review_block(data) == []

    def test_persistence_block_validates(self) -> None:
        from spec4.agents._code_review_schema import validate_review_block

        data = {
            "review": {
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
        assert validate_review_block(data) == []

    def test_env_vars_block_validates(self) -> None:
        from spec4.agents._code_review_schema import validate_review_block

        data = {
            "review": {
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
        assert validate_review_block(data) == []

    def test_deployment_block_validates(self) -> None:
        from spec4.agents._code_review_schema import validate_review_block

        data = {
            "review": {
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
        assert validate_review_block(data) == []

    def test_api_surface_block_validates(self) -> None:
        from spec4.agents._code_review_schema import validate_review_block

        data = {
            "review": {
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
        assert validate_review_block(data) == []

    def test_auth_block_validates(self) -> None:
        from spec4.agents._code_review_schema import validate_review_block

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
                "review": {
                    "is_software_project": True,
                    "auth": {
                        "model": model,
                        "provider": "Auth0" if model in ("oauth", "sso") else "",
                        "library": "authlib",
                        "source": "src/app/auth.py",
                    },
                }
            }
            assert validate_review_block(data) == [], f"auth.model={model} should pass"

    def test_full_realistic_review_passes(self) -> None:
        from spec4.agents._code_review_schema import validate_review_block

        data = {
            "review": {
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
        assert validate_review_block(data) == []

    def test_ai_capabilities_block_validates(self) -> None:
        from spec4.agents._code_review_schema import validate_review_block

        data = {
            "review": {
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
        assert validate_review_block(data) == []

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
        from spec4.agents._code_review_schema import validate_review_block

        data = {
            "review": {
                "is_software_project": True,
                section: value,
            }
        }
        errors = validate_review_block(data)
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
        from spec4.agents._code_review_schema import validate_review_block

        data = {
            "review": {
                "is_software_project": True,
                section: value,
            }
        }
        errors = validate_review_block(data)
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
        from spec4.agents._code_review_schema import validate_review_block

        data = {
            "review": {
                "is_software_project": True,
                section: value,
            }
        }
        errors = validate_review_block(data)
        assert any(all(n in e for n in needles) for e in errors)

    def test_review_block_rejects_code_owned_fields(self) -> None:
        # D-EV2: ``schema_version`` and ``scan`` are never the model's to emit.
        from spec4.agents._code_review_schema import validate_review_block

        for extra in ({"schema_version": 2}, {"scan": {}}):
            errors = validate_review_block(
                {"review": {"is_software_project": True, **extra}}
            )
            assert any(next(iter(extra)) in e for e in errors)

    @pytest.mark.parametrize(
        "inner",
        [
            {"scan": {}, "review": {"is_software_project": True}},  # version missing
            {"schema_version": 1, "scan": {}, "review": {"is_software_project": True}},
        ],
    )
    def test_envelope_schema_version_constraint_fails(
        self, inner: dict[str, Any]
    ) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        errors = validate_code_review({"code_review": inner})
        assert any("schema_version" in e for e in errors)

    def test_envelope_requires_scan_and_review(self) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        v1_shaped = {"code_review": {"schema_version": 2, "is_software_project": True}}
        errors = validate_code_review(v1_shaped)
        assert any("'scan' is a required property" in e for e in errors)
        assert any("'review' is a required property" in e for e in errors)
        assert validate_code_review(review_envelope()) == []
        assert validate_code_review(review_envelope(is_software_project=False)) == []


# ---------------------------------------------------------------------------
# CodeScanner validation + retry flow
# ---------------------------------------------------------------------------


class TestCodeScannerValidationRetry:
    """Integration tests for the validate-and-retry behavior in run()."""

    def _valid_review_text(self) -> str:
        return '```json\n{"review": {"is_software_project": true}}\n```'

    def _invalid_review_text(self) -> str:
        # ``commands`` is a closed key set → fails validation.
        return (
            '```json\n{"review": {"is_software_project": true, '
            '"commands": {"bogus": "x"}}}\n```'
        )

    def test_valid_review_does_not_retry(self) -> None:
        session = make_session(
            code_scanner_scan={},
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ],
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
            code_scanner_scan={},
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ],
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
        assert (
            session["code_review"]["code_review"]["schema_version"]
            == CODE_REVIEW_SCHEMA_VERSION
        )

    def test_retry_drained_silently_not_yielded(self) -> None:
        # The retry stream's body (raw or fenced JSON) must not be yielded
        # to the user. The original suppression already swallows fenced JSON;
        # here we verify the retry pass adds nothing to the visible output.
        session = make_session(
            code_scanner_scan={},
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ],
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
            code_scanner_scan={},
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ],
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
            code_scanner_scan={},
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ],
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
            code_scanner_scan={},
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ],
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
            code_scanner_scan={},
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ],
        )
        raw_valid = '{"review": {"is_software_project": true}}'
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
        assert (
            session["code_review"]["code_review"]["schema_version"]
            == CODE_REVIEW_SCHEMA_VERSION
        )


class TestReviewFailureDump:
    """2.9.1: a review emission that fails validation is written to
    ``.spec4/failures/code_scanner_review_<n>.txt`` with its errors, so the
    cause of a retry can be read after the fact (the Agentifier's D-AF7
    precedent). Unconditional — not dev-gated."""

    _valid = '```json\n{"review": {"is_software_project": true}}\n```'
    _invalid = (
        '```json\n{"review": {"is_software_project": true, '
        '"commands": {"bogus": "x"}}}\n```'
    )

    def _run(self, working_dir: str | None, *replies: str) -> dict[str, Any]:
        session = make_session(
            code_scanner_scan={},
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ],
        )
        session["working_dir"] = working_dir
        chunk_seqs = [list(_chunkify_stream(r)) for r in replies]

        def fake_completion(**kwargs: Any) -> Any:
            return iter(chunk_seqs.pop(0))

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            collect(code_scanner.run("Confirm", session, session["llm_config"]))
        return session

    def test_first_failed_emission_is_dumped_with_its_errors(
        self, tmp_path: pathlib.Path
    ) -> None:
        session = self._run(str(tmp_path), self._invalid, self._valid)
        assert session["code_scanner_state"] == STATE_REVIEW_COMPLETE
        dumps = sorted((tmp_path / ".spec4" / "failures").glob("*.txt"))
        assert [d.name for d in dumps] == ["code_scanner_review_1.txt"]
        text = dumps[0].read_text(encoding="utf-8")
        head, _, raw = text.partition("\n\n")
        assert head.splitlines()[0] == (
            "# code_scanner review emission failed validation (first emission)"
        )
        assert f"# schema_version {CODE_REVIEW_SCHEMA_VERSION}; 1 error(s):" in head
        assert "bogus" in head  # the validator's own error line
        assert raw == self._invalid  # the reply, verbatim, after the header

    def test_both_failures_are_dumped_in_order(self, tmp_path: pathlib.Path) -> None:
        session = self._run(str(tmp_path), self._invalid, self._invalid)
        assert session["code_scanner_state"] != STATE_REVIEW_COMPLETE
        dumps = sorted((tmp_path / ".spec4" / "failures").glob("*.txt"))
        assert [d.name for d in dumps] == [
            "code_scanner_review_1.txt",
            "code_scanner_review_2.txt",
        ]
        assert "(first emission)" in dumps[0].read_text(encoding="utf-8")
        assert "(re-ask)" in dumps[1].read_text(encoding="utf-8")
        # A later scan numbers on from what is there.
        self._run(str(tmp_path), self._invalid, self._valid)
        names = sorted(p.name for p in (tmp_path / ".spec4" / "failures").glob("*"))
        assert names == [f"code_scanner_review_{n}.txt" for n in (1, 2, 3)]

    def test_a_valid_emission_writes_nothing(self, tmp_path: pathlib.Path) -> None:
        session = self._run(str(tmp_path), self._valid)
        assert session["code_scanner_state"] == STATE_REVIEW_COMPLETE
        assert not (tmp_path / ".spec4").exists()

    def test_no_working_dir_or_unwritable_dir_never_breaks_the_turn(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No working directory: nothing is written anywhere (not to the
        # current directory either), and the retry still runs.
        monkeypatch.chdir(tmp_path)
        session = self._run(None, self._invalid, self._valid)
        assert session["code_scanner_state"] == STATE_REVIEW_COMPLETE
        assert list(tmp_path.iterdir()) == []
        # A file where the failures directory should be: mkdir raises, the
        # dump is skipped and the retry still completes.
        (tmp_path / ".spec4").write_text("not a directory", encoding="utf-8")
        session = self._run(str(tmp_path), self._invalid, self._valid)
        assert session["code_scanner_state"] == STATE_REVIEW_COMPLETE
        assert (tmp_path / ".spec4").read_text(encoding="utf-8") == "not a directory"


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
        return '```json\n{"review": {"is_soft'

    def _valid_review_text(self) -> str:
        return '```json\n{"review": {"is_software_project": true}}\n```'

    def _session(self) -> dict[str, Any]:
        return make_session(
            code_scanner_scan={},
            code_scanner_messages=[
                {"role": "user", "content": "seed"},
                {"role": "assistant", "content": "draft"},
            ],
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
        assert (
            session["code_review"]["code_review"]["schema_version"]
            == CODE_REVIEW_SCHEMA_VERSION
        )

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


# ---------------------------------------------------------------------------
# step 3a: load_bearing / implemented / integrations (D-SC3-1…5, 7, 10)
# ---------------------------------------------------------------------------


def _load_bearing(**over: Any) -> dict[str, Any]:
    return {
        "module": "src/app/llm.py",
        "symbol": "stream_turn",
        "role": "every LLM call",
        "contract": {"inputs": ["messages"], "side_effects": ["network"]},
        "inferred_from": "src/app/llm.py",
        **over,
    }


def _implemented(**over: Any) -> dict[str, Any]:
    return {
        "id": "code_review",
        "name": "Code review",
        "description": "Drafts a review",
        "status": "complete",
        "paths": ["src/app/scanner/"],
        "prior_feature_ids": ["round_tree"],
        "inferred_from": "src/app/scanner/__init__.py",
        **over,
    }


def _integration(**over: Any) -> dict[str, Any]:
    return {
        "name": "Tavily",
        "kind": "web_search",
        "client_module": "src/app/websearch.py",
        "config_env_vars": ["TAVILY_API_KEY"],
        "purpose": "look-ups during a scan",
        "inferred_from": "src/app/websearch.py",
        **over,
    }


class TestStep3Schema:
    def test_the_three_arrays_validate_in_both_schemas(self) -> None:
        from spec4.agents._code_review_schema import (
            validate_code_review,
            validate_review_block,
        )
        from tests._review_helpers import review_block

        fields = {
            "load_bearing": [_load_bearing(), _load_bearing(module="src/app/c.py")],
            "implemented": [_implemented()],
            "integrations": [_integration()],
        }
        assert validate_review_block(review_block(**fields)) == []
        assert validate_code_review(review_envelope(**fields)) == []
        # Minimal items: the required keys alone.
        lean = {
            "load_bearing": [
                {"module": "a.py", "role": "r", "contract": {"outputs": ["x"]}}
            ],
            "implemented": [
                {"id": "a", "name": "A", "status": "stub", "paths": ["a.py"]}
            ],
            "integrations": [{"name": "Redis", "kind": "cache"}],
        }
        assert validate_review_block(review_block(**lean)) == []

    def test_emitted_block_permits_consumers_so_an_update_does_not_retry(
        self,
    ) -> None:
        # D-SC3-4: the stored value is code-owned, but an update-mode
        # re-emission carries the prior one forward; the schema lets it
        # through and ``wrap_review`` replaces it.
        from spec4.agents._code_review_schema import validate_review_block
        from tests._review_helpers import review_block

        block = review_block(load_bearing=[_load_bearing(consumers=["x.py"])])
        assert validate_review_block(block) == []

    @pytest.mark.parametrize(
        "field, item, needle",
        [
            ("load_bearing", _load_bearing(contract={}), "contract"),
            ("load_bearing", _load_bearing(contract={"inputs": "x"}), "inputs"),
            ("load_bearing", _load_bearing(contract={"callers": ["x"]}), "callers"),
            ("load_bearing", _load_bearing(evidence="x"), "evidence"),
            ("implemented", _implemented(status="done"), "status"),
            ("implemented", _implemented(paths=[]), "paths"),
            ("implemented", _implemented(evidence="x"), "evidence"),
            ("integrations", _integration(kind="search"), "kind"),
            ("integrations", _integration(config_env_vars=[{"name": "K"}]), "config"),
            ("integrations", _integration(value="secret"), "value"),
        ],
    )
    def test_closed_shapes_and_enums_reject_drift(
        self, field: str, item: dict[str, Any], needle: str
    ) -> None:
        from spec4.agents._code_review_schema import validate_review_block
        from tests._review_helpers import review_block

        errors = validate_review_block(review_block(**{field: [item]}))
        assert errors
        assert any(needle in e for e in errors)

    @pytest.mark.parametrize(
        "field, item, missing",
        [
            ("load_bearing", {"role": "r", "contract": {"inputs": ["x"]}}, "module"),
            ("load_bearing", {"module": "a.py", "contract": {"inputs": ["x"]}}, "role"),
            ("load_bearing", {"module": "a.py", "role": "r"}, "contract"),
            ("implemented", {"name": "A", "status": "stub", "paths": ["a"]}, "id"),
            ("implemented", {"id": "a", "name": "A", "status": "stub"}, "paths"),
            ("integrations", {"name": "Redis"}, "kind"),
            ("integrations", {"kind": "cache"}, "name"),
        ],
    )
    def test_required_keys(
        self, field: str, item: dict[str, Any], missing: str
    ) -> None:
        from spec4.agents._code_review_schema import validate_review_block
        from tests._review_helpers import review_block

        errors = validate_review_block(review_block(**{field: [item]}))
        assert any(f"'{missing}' is a required property" in e for e in errors)

    def test_retry_message_names_the_new_enums(self) -> None:
        from spec4.agents._code_review_schema import (
            _IMPLEMENTED_STATUSES,
            _INTEGRATION_KINDS,
            format_validation_errors_for_retry,
        )

        msg = format_validation_errors_for_retry(["x"])
        for status in _IMPLEMENTED_STATUSES:
            assert status in msg
        for kind in _INTEGRATION_KINDS:
            assert kind in msg
        assert "omit `consumers`" in msg

    def test_system_prompt_documents_the_three_arrays(self) -> None:
        from spec4.agents.code_scanner import SYSTEM_PROMPT

        for key in ("load_bearing", "implemented", "integrations"):
            assert f'"{key}": [' in SYSTEM_PROMPT  # the JSON exemplar
            assert f"**`{key}`**" in SYSTEM_PROMPT  # the field rule
        for name in (
            "Load-Bearing Modules",
            "Implemented Capabilities",
            "Integrations",
        ):
            assert name in SYSTEM_PROMPT  # the draft section list
        assert "scaffolded_only" in SYSTEM_PROMPT
        assert "mcp_server" in SYSTEM_PROMPT
        assert "Do NOT emit `consumers`" in SYSTEM_PROMPT
        assert "Load-bearing candidates" in SYSTEM_PROMPT
        assert "Prior Round" in SYSTEM_PROMPT
        assert "External Packages and Their Importers" in SYSTEM_PROMPT

    def test_llm_provider_entries_name_the_provider_not_the_sdk(self) -> None:
        # 3b (D-SC3-14 finding 1): the first real 2.6.0 scan named providers
        # (OpenRouter, Groq) while ``ai_capabilities`` names SDKs (litellm,
        # pydantic-ai), so the cross-reference rule now says exactly that.
        from spec4.agents.code_scanner import SYSTEM_PROMPT

        assert (
            "an `llm_provider` entry's `name` is the\n  provider itself "
            "(OpenRouter, Anthropic, Groq)" in SYSTEM_PROMPT
        )
        assert "(litellm, pydantic-ai) is in `ai_capabilities`, not here" in (
            SYSTEM_PROMPT
        )
        assert "matches\n  the `ai_capabilities` entry it backs" not in SYSTEM_PROMPT


class TestWrapReviewConsumers:
    _scan = {
        "module_graph": {
            "languages": ["python"],
            "nodes": 4,
            "edges": 4,
            "fan_in": {"src/app/llm.py": 2, "src/app/c.py": 2},
            "fan_out": {"a.py": 2, "b.py": 1, "d.py": 1},
            "load_bearing_candidates": [
                {"path": "src/app/llm.py", "fan_in": 2, "consumers": ["a.py", "b.py"]},
                {"path": "src/app/c.py", "fan_in": 2, "consumers": ["a.py", "d.py"]},
            ],
            "unresolved": {},
            "unresolved_truncated": False,
        }
    }

    def test_consumers_are_filled_from_the_graph_by_module(self) -> None:
        from spec4.agents.code_scanner import wrap_review

        block = {
            "review": {
                "is_software_project": True,
                "load_bearing": [
                    _load_bearing(),
                    _load_bearing(module="src/app/other.py"),
                ],
            }
        }
        out = wrap_review(block, self._scan)["code_review"]["review"]["load_bearing"]
        assert out[0]["consumers"] == ["a.py", "b.py"]
        assert out[1]["consumers"] == []
        assert out[0]["symbol"] == "stream_turn"  # the rest passes through
        # The block itself is not mutated.
        assert "consumers" not in block["review"]["load_bearing"][0]

    def test_an_emitted_consumers_value_is_replaced_not_kept(self) -> None:
        from spec4.agents.code_scanner import wrap_review

        block = {
            "review": {
                "is_software_project": True,
                "load_bearing": [
                    _load_bearing(consumers=["stale.py"]),
                    _load_bearing(module="src/app/other.py", consumers=["x.py"]),
                ],
            }
        }
        out = wrap_review(block, self._scan)["code_review"]["review"]["load_bearing"]
        assert out[0]["consumers"] == ["a.py", "b.py"]
        assert out[1]["consumers"] == []

    def test_without_a_graph_every_entry_gets_an_empty_list(self) -> None:
        from spec4.agents.code_scanner import wrap_review

        block = {
            "review": {"is_software_project": True, "load_bearing": [_load_bearing()]}
        }
        for scan in (None, {}, {"module_graph": {}}):
            out = wrap_review(block, scan)["code_review"]["review"]
            assert out["load_bearing"][0]["consumers"] == []

    def test_a_review_without_load_bearing_passes_through_unchanged(self) -> None:
        from spec4.agents.code_scanner import wrap_review

        block = {"review": {"is_software_project": True, "project_type": "CLI"}}
        assert (
            wrap_review(block, self._scan)["code_review"]["review"] == block["review"]
        )
        odd = {"review": {"is_software_project": True, "load_bearing": "n/a"}}
        assert wrap_review(odd, self._scan)["code_review"]["review"] == odd["review"]

    def test_commit_stores_the_joined_list_and_the_envelope_validates(
        self, tmp_path: Any
    ) -> None:
        from spec4.agents._code_review_schema import validate_code_review
        from spec4.agents.code_scanner import _scanner_commit

        session = make_session(
            code_scanner_scan=self._scan,
            code_scanner_messages=[{"role": "assistant", "content": ""}],
        )
        block = {
            "review": {
                "is_software_project": True,
                "load_bearing": [_load_bearing(consumers=["stale.py"])],
            }
        }
        _scanner_commit(session, session["code_scanner_messages"], block)
        stored = session["code_review"]
        assert validate_code_review(stored) == []
        lb = stored["code_review"]["review"]["load_bearing"][0]
        assert lb["consumers"] == ["a.py", "b.py"]
        assert "consumers: 2" in session["_display_override"]


# ---------------------------------------------------------------------------
# step 4a (2.8.0): reconciliation, unplanned changes, divergences
# ---------------------------------------------------------------------------


def _reconciliation(**over: Any) -> dict[str, Any]:
    return {"phase_number": 2, "gap": "the retriever is a stub", **over}


def _unplanned(**over: Any) -> dict[str, Any]:
    return {
        "area": "provider fallback",
        "summary": "llm.py gained a fallback ladder",
        "affects": ["src/app/llm.py", "code_review"],
        "inferred_from": "src/app/llm.py",
        **over,
    }


def _divergence(**over: Any) -> dict[str, Any]:
    return {
        "area": "persistence",
        "planned": "Neon (serverless Postgres) + pgvector",
        "found": "PostgreSQL",
        "kind": "renamed",
        "note": "same engine, product name",
        "inferred_from": "src/app/db.py",
        **over,
    }


def _phase(number: int | None, ids: list[str], **over: Any) -> dict[str, Any]:
    return {
        "number": number,
        "title": f"Phase {number}",
        "features": [{"id": i, "role": "introduced"} for i in ids],
        **over,
    }


def _prior_scan(*phases: dict[str, Any]) -> dict[str, Any]:
    return {"prior_round": {"version": 2, "phases": list(phases)}}


class TestStep4Schema:
    def test_the_three_arrays_validate_in_both_schemas(self) -> None:
        from spec4.agents._code_review_schema import (
            validate_code_review,
            validate_review_block,
        )
        from tests._review_helpers import review_block

        fields = {
            "prior_round_reconciliation": [_reconciliation()],
            "unplanned_changes": [_unplanned()],
            "divergences": [_divergence()],
        }
        assert validate_review_block(review_block(**fields)) == []
        assert validate_code_review(review_envelope(**fields)) == []
        # Minimal items: the required keys alone.
        lean = {
            "prior_round_reconciliation": [{"phase_number": 1}],
            "unplanned_changes": [{"area": "a", "summary": "s"}],
            "divergences": [
                {"area": "stack", "planned": "p", "found": "f", "kind": "dropped"}
            ],
        }
        assert validate_review_block(review_block(**lean)) == []

    def test_emitted_block_permits_the_code_owned_fields(self) -> None:
        # D-SC4-3/4: as ``consumers`` — an update-mode re-emission carries the
        # stored item forward; the schema lets it through and commit overwrites.
        from spec4.agents._code_review_schema import validate_review_block
        from tests._review_helpers import review_block

        full = _reconciliation(
            title="Phase 2 — Retrieval",
            verdict="evidence_partial",
            implemented_ids=["a"],
            paths=["a.py"],
            features=[{"id": "x", "statuses": ["partial"]}],
        )
        block = review_block(
            prior_round_reconciliation=[full],
            unplanned_changes=[_unplanned(classification="unknown")],
        )
        assert validate_review_block(block) == []
        # ``title`` is nullable (D-SC4b-5): a round that recorded none.
        block = review_block(prior_round_reconciliation=[_reconciliation(title=None)])
        assert validate_review_block(block) == []

    @pytest.mark.parametrize(
        "field, item, needle",
        [
            ("prior_round_reconciliation", _reconciliation(phase_number="2"), "2"),
            ("prior_round_reconciliation", _reconciliation(verdict="done"), "done"),
            ("prior_round_reconciliation", _reconciliation(title=3), "title"),
            ("prior_round_reconciliation", _reconciliation(evidence=["x"]), "evidence"),
            (
                "prior_round_reconciliation",
                _reconciliation(features=[{"id": "x"}]),
                "statuses",
            ),
            ("unplanned_changes", _unplanned(classification="hand"), "hand"),
            ("unplanned_changes", _unplanned(affects="src/"), "affects"),
            ("unplanned_changes", _unplanned(files=["x"]), "files"),
            ("divergences", _divergence(area="dependencies"), "dependencies"),
            ("divergences", _divergence(kind="changed"), "changed"),
            ("divergences", _divergence(severity="high"), "severity"),
        ],
    )
    def test_closed_shapes_and_enums_reject_drift(
        self, field: str, item: dict[str, Any], needle: str
    ) -> None:
        from spec4.agents._code_review_schema import validate_review_block
        from tests._review_helpers import review_block

        errors = validate_review_block(review_block(**{field: [item]}))
        assert errors
        assert any(needle in e for e in errors)

    @pytest.mark.parametrize(
        "field, item, missing",
        [
            ("prior_round_reconciliation", {"gap": "x"}, "phase_number"),
            ("unplanned_changes", {"summary": "s"}, "area"),
            ("unplanned_changes", {"area": "a"}, "summary"),
            ("divergences", {"planned": "p", "found": "f", "kind": "added"}, "area"),
            (
                "divergences",
                {"area": "stack", "found": "f", "kind": "added"},
                "planned",
            ),
            (
                "divergences",
                {"area": "stack", "planned": "p", "kind": "added"},
                "found",
            ),
            ("divergences", {"area": "stack", "planned": "p", "found": "f"}, "kind"),
        ],
    )
    def test_required_keys(
        self, field: str, item: dict[str, Any], missing: str
    ) -> None:
        from spec4.agents._code_review_schema import validate_review_block
        from tests._review_helpers import review_block

        errors = validate_review_block(review_block(**{field: [item]}))
        assert any(f"'{missing}' is a required property" in e for e in errors)

    def test_coverage_accepts_changes_shown_and_older_scans_without_it(
        self,
    ) -> None:
        from spec4.agents._code_review_schema import validate_code_review

        coverage = {
            "tree_listed": 1,
            "tree_truncated": False,
            "readme": None,
            "manifests": [],
            "ci": [],
            "deploy": [],
            "sampled": [],
            "source_files_total": 1,
            "source_files_sampled": 0,
        }
        assert validate_code_review(review_envelope(scan={"coverage": coverage})) == []
        with_flag = {**coverage, "changes_shown": True}
        assert validate_code_review(review_envelope(scan={"coverage": with_flag})) == []
        bad = {**coverage, "changes_shown": "yes"}
        errors = validate_code_review(review_envelope(scan={"coverage": bad}))
        assert any("changes_shown" in e for e in errors)

    def test_retry_message_names_the_enums_and_the_omit_rules(self) -> None:
        from spec4.agents._code_review_schema import (
            _DIVERGENCE_AREAS,
            _DIVERGENCE_KINDS,
            format_validation_errors_for_retry,
        )

        msg = format_validation_errors_for_retry(["x"])
        for area in _DIVERGENCE_AREAS:
            assert area in msg
        for kind in _DIVERGENCE_KINDS:
            assert kind in msg
        assert "`phase_number` (integer) and `gap` only" in msg
        assert "omit `classification`" in msg
        assert "Never a dependency name" in msg

    def test_system_prompt_documents_the_three_arrays(self) -> None:
        from spec4.agents._code_review_schema import (
            _DIVERGENCE_AREAS,
            _DIVERGENCE_KINDS,
        )
        from spec4.agents.code_scanner import SYSTEM_PROMPT

        for key in ("prior_round_reconciliation", "unplanned_changes", "divergences"):
            assert f'"{key}": [' in SYSTEM_PROMPT  # the JSON exemplar
            assert f"**`{key}`**" in SYSTEM_PROMPT  # the field rule
            assert f"`{key}`" in SYSTEM_PROMPT.split("**Scope:**")[0]  # consumers
        for name in (
            "Prior Round Reconciliation",
            "Unplanned Changes",
            "Divergences",
        ):
            assert name in SYSTEM_PROMPT  # the draft section list
        for value in (*_DIVERGENCE_AREAS, *_DIVERGENCE_KINDS):
            assert f'"{value}"' in SYSTEM_PROMPT
        # The exemplar shows reconciliation as {phase_number, gap} only.
        exemplar = SYSTEM_PROMPT.split('"prior_round_reconciliation": [')[1]
        exemplar = exemplar.split("]")[0]
        assert '"phase_number"' in exemplar
        assert '"gap"' in exemplar
        assert "verdict" not in exemplar
        assert "Never emit `verdict`, `implemented_ids`, `paths`" in SYSTEM_PROMPT
        assert "Never emit `classification`" in SYSTEM_PROMPT
        assert "NEVER a dependency or package name" in SYSTEM_PROMPT
        assert "Changes Since the Last Round" in SYSTEM_PROMPT

    def test_step4b_nudges_are_in_the_prompt(self) -> None:
        # D-SC4b-8: the two sentences the first real BWS4 scan asked for,
        # each inside the rule for its own field (the prompt is wrapped, so
        # the pins compare on collapsed whitespace).
        from spec4.agents.code_scanner import SYSTEM_PROMPT

        def rule(field: str) -> str:
            body = SYSTEM_PROMPT.split(f"- **`{field}`**")[1].split("\n- ")[0]
            return " ".join(body.split())

        assert (
            "One entry per found counterpart; `found` is one name, verbatim — "
            "never a conjunction" in rule("divergences")
        )
        assert "never a conjunction" not in rule("load_bearing")
        assert (
            "An invariant or side effect you state in the draft prose goes in "
            "`contract.invariants` / `side_effects`, not only in the prose."
            in rule("load_bearing")
        )
        assert "not only in the prose" not in rule("divergences")


class TestWrapReviewReconciliation:
    def _review(self, block: dict[str, Any], scan: dict[str, Any]) -> list[Any]:
        from spec4.agents.code_scanner import wrap_review

        out = wrap_review(block, scan)["code_review"]["review"]
        return list(out.get("prior_round_reconciliation", []))

    def test_every_prior_phase_gets_a_verdict_from_the_join(self) -> None:
        # D-SC4-3: found when every id has a complete claim; none when no id
        # is claimed; partial otherwise; unassessed without features. The
        # role (``extended``) does not enter.
        scan = _prior_scan(
            _phase(1, ["a", "b"]),
            _phase(2, ["c"]),
            _phase(3, ["a", "d"]),
            _phase(4, []),
            _phase(5, ["e"]),
        )
        scan["prior_round"]["phases"][0]["features"][1]["role"] = "extended"
        block = {
            "review": {
                "is_software_project": True,
                "implemented": [
                    _implemented(
                        id="i1", paths=["a.py", "b.py"], prior_feature_ids=["a", "b"]
                    ),
                    _implemented(
                        id="i2",
                        status="partial",
                        paths=["b.py"],
                        prior_feature_ids=["b", "e"],
                    ),
                    _implemented(
                        id="i3", status="stub", paths=["d.py"], prior_feature_ids=["d"]
                    ),
                ],
            }
        }
        out = self._review(block, scan)
        assert [e["phase_number"] for e in out] == [1, 2, 3, 4, 5]
        assert [e["verdict"] for e in out] == [
            "evidence_found",
            "no_evidence_found",
            "evidence_partial",
            "unassessed",
            "evidence_partial",
        ]
        assert out[0]["implemented_ids"] == ["i1", "i2"]
        assert out[0]["paths"] == ["a.py", "b.py"]
        assert out[0]["features"] == [
            {"id": "a", "statuses": ["complete"]},
            {"id": "b", "statuses": ["complete", "partial"]},
        ]
        assert out[1] == {
            "phase_number": 2,
            "title": "Phase 2",
            "verdict": "no_evidence_found",
            "implemented_ids": [],
            "paths": [],
            "features": [{"id": "c", "statuses": []}],
        }
        assert out[2]["implemented_ids"] == ["i1", "i3"]
        assert out[2]["paths"] == ["a.py", "b.py", "d.py"]  # the union, in order
        assert out[3] == {
            "phase_number": 4,
            "title": "Phase 4",
            "verdict": "unassessed",
            "implemented_ids": [],
            "paths": [],
            "features": [],
        }
        assert out[4]["features"] == [{"id": "e", "statuses": ["partial"]}]
        assert all("gap" not in e for e in out)

    def test_a_duplicate_feature_id_in_a_phase_counts_once(self) -> None:
        scan = _prior_scan(_phase(1, ["a", "a"]))
        block = {
            "review": {
                "is_software_project": True,
                "implemented": [_implemented(prior_feature_ids=["a"])],
            }
        }
        out = self._review(block, scan)
        assert out[0]["verdict"] == "evidence_found"
        assert out[0]["features"] == [{"id": "a", "statuses": ["complete"]}]

    def test_the_models_gap_is_merged_by_phase_and_the_rest_overwritten(self) -> None:
        scan = _prior_scan(_phase(1, ["a"]), _phase(2, ["b"]))
        block = {
            "review": {
                "is_software_project": True,
                "implemented": [_implemented(prior_feature_ids=["a"])],
                "prior_round_reconciliation": [
                    {
                        "phase_number": 2,
                        "gap": "b has no module",
                        "inferred_from": "src/",
                        "verdict": "evidence_found",  # the model's claim
                        "implemented_ids": ["code_review"],
                        "paths": ["stale.py"],
                        "features": [{"id": "zzz", "statuses": ["complete"]}],
                    },
                    {"phase_number": 1, "gap": ""},  # empty gap: nothing kept
                    {"phase_number": 9, "gap": "no such phase"},  # dropped
                    "raw",
                ],
            }
        }
        out = self._review(block, scan)
        assert [e["phase_number"] for e in out] == [1, 2]
        assert "gap" not in out[0]
        assert out[0]["verdict"] == "evidence_found"
        assert out[1] == {
            "phase_number": 2,
            "title": "Phase 2",
            "verdict": "no_evidence_found",
            "implemented_ids": [],
            "paths": [],
            "features": [{"id": "b", "statuses": []}],
            "gap": "b has no module",
            "inferred_from": "src/",
        }
        # The block itself is not mutated.
        assert block["review"]["prior_round_reconciliation"][0]["paths"] == ["stale.py"]

    def test_the_phase_title_is_copied_onto_the_item_at_commit(self) -> None:
        # D-SC4b-5: the item carries its phase's title, null when the prior
        # round recorded none (or a blank), and the model cannot set it.
        scan = _prior_scan(
            _phase(1, ["a"], title="Integration Thread"),
            _phase(2, ["a"], title=None),
            _phase(3, ["a"], title="   "),
            _phase(4, ["a"], title=7),
        )
        del scan["prior_round"]["phases"][1]["title"]
        block = {
            "review": {
                "is_software_project": True,
                "implemented": [_implemented(prior_feature_ids=["a"])],
                "prior_round_reconciliation": [
                    {"phase_number": 1, "title": "the model's name", "gap": "g"},
                    {"phase_number": 2, "title": "invented", "gap": "g"},
                ],
            }
        }
        out = self._review(block, scan)
        assert [e["title"] for e in out] == ["Integration Thread", None, None, None]
        assert list(out[0]) == [
            "phase_number",
            "title",
            "verdict",
            "implemented_ids",
            "paths",
            "features",
            "gap",
        ]
        assert out[0]["gap"] == "g"  # the gap still merges beside it

    def test_a_phase_without_a_number_is_skipped(self) -> None:
        scan = _prior_scan(_phase(None, ["a"]), _phase(2, ["a"]))
        block = {
            "review": {
                "is_software_project": True,
                "implemented": [_implemented(prior_feature_ids=["a"])],
            }
        }
        out = self._review(block, scan)
        assert [e["phase_number"] for e in out] == [2]

    def test_without_a_prior_round_the_key_is_dropped(self) -> None:
        from spec4.agents.code_scanner import wrap_review

        block = {
            "review": {
                "is_software_project": True,
                "implemented": [_implemented()],
                "prior_round_reconciliation": [_reconciliation()],
            }
        }
        for scan in (None, {}, {"prior_round": {}}, {"prior_round": {"phases": []}}):
            out = wrap_review(block, scan)["code_review"]["review"]
            assert "prior_round_reconciliation" not in out
            assert out["implemented"] == block["review"]["implemented"]
        # Paired positive: a phase makes the key appear even when the model
        # emitted nothing.
        plain = {"review": {"is_software_project": True}}
        out = wrap_review(plain, _prior_scan(_phase(1, [])))["code_review"]["review"]
        assert out["prior_round_reconciliation"] == [
            {
                "phase_number": 1,
                "title": "Phase 1",
                "verdict": "unassessed",
                "implemented_ids": [],
                "paths": [],
                "features": [],
            }
        ]

    def test_malformed_implemented_claims_nothing(self) -> None:
        scan = _prior_scan(_phase(1, ["a"]))
        for implemented in ("n/a", ["raw", {"id": "x"}], None):
            block = {
                "review": {"is_software_project": True, "implemented": implemented}
            }
            block = {
                "review": {k: v for k, v in block["review"].items() if v is not None}
            }
            out = self._review(block, scan)
            assert out[0]["verdict"] == "no_evidence_found"

    def test_commit_stores_the_join_and_the_envelope_validates(self) -> None:
        from spec4.agents._code_review_schema import validate_code_review
        from spec4.agents.code_scanner import _scanner_commit

        prior = load_fixture("review_with_step3.json")["code_review"]["scan"]
        session = make_session(
            code_scanner_scan={"prior_round": prior["prior_round"]},
            code_scanner_messages=[{"role": "assistant", "content": ""}],
        )
        block = {
            "review": {
                "is_software_project": True,
                "implemented": [
                    _implemented(id="vps", prior_feature_ids=["self_hosted_deployment"])
                ],
                "prior_round_reconciliation": [{"phase_number": 1, "gap": "half"}],
            }
        }
        _scanner_commit(session, session["code_scanner_messages"], block)
        stored = session["code_review"]
        assert validate_code_review(stored) == []
        entries = stored["code_review"]["review"]["prior_round_reconciliation"]
        assert [e["verdict"] for e in entries] == ["evidence_partial"] * 2
        assert entries[0]["gap"] == "half"
        assert entries[0]["title"] == (
            "Integration Thread — VPS Baseline Bring-Up and Environment Contract "
            "Relocation"
        )
        assert (
            "phase 1 — *Integration Thread — VPS Baseline Bring-Up and Environment "
            "Contract Relocation* [evidence_partial] — `vps`; gap: half"
            in (session["_display_override"])
        )


class TestWrapReviewClassification:
    _scan = {
        "git": {
            "available": True,
            "since_last_round": {
                "most_touched": [
                    {"path": "src/app/llm.py", "commits": 4},
                    {"path": "CHANGELOG.md", "commits": 3},
                ]
            },
        },
        "delta": {"files": {"added": ["src/app/new.py"], "removed": ["gone.py"]}},
    }

    def _review(self, entries: list[Any], scan: Any) -> list[Any]:
        from spec4.agents.code_scanner import wrap_review

        block = {"review": {"is_software_project": True, "unplanned_changes": entries}}
        out = wrap_review(block, scan)["code_review"]["review"]
        return list(out["unplanned_changes"])

    @pytest.mark.parametrize(
        "affects, expected",
        [
            (["src/app/llm.py"], "out_of_round"),  # most touched
            (["src/app/new.py"], "out_of_round"),  # added since the prior scan
            (["src/app/"], "out_of_round"),  # a directory a touched file is under
            (["src/app"], "out_of_round"),
            (["docs/", "CHANGELOG.md"], "out_of_round"),  # any path suffices
            (["src/app/llm"], "unknown"),  # a prefix is not a directory
            (["gone.py"], "unknown"),  # removed is not a change to classify
            (["code_review"], "unknown"),  # an implemented id
            ([], "unknown"),
        ],
    )
    def test_out_of_round_or_unknown_by_affects(
        self, affects: list[str], expected: str
    ) -> None:
        out = self._review([_unplanned(affects=affects)], self._scan)
        assert out[0]["classification"] == expected

    def test_an_emitted_classification_is_replaced_and_the_rest_kept(self) -> None:
        entries = [
            _unplanned(affects=["src/app/llm.py"], classification="in_round"),
            _unplanned(affects=["docs/x.md"], classification="out_of_round"),
            {"area": "a", "summary": "s"},  # no affects at all
            "raw",
        ]
        out = self._review(entries, self._scan)
        assert [e["classification"] for e in out[:3]] == [
            "out_of_round",
            "unknown",
            "unknown",
        ]
        assert out[0]["summary"] == "llm.py gained a fallback ladder"
        assert out[3] == "raw"
        assert entries[0]["classification"] == "in_round"  # not mutated

    def test_without_git_or_delta_everything_is_unknown(self) -> None:
        for scan in (None, {}, {"git": {"available": False}}, {"delta": {}}):
            out = self._review([_unplanned(affects=["src/app/llm.py"])], scan)
            assert out[0]["classification"] == "unknown"

    def test_a_review_without_the_array_passes_through(self) -> None:
        from spec4.agents.code_scanner import wrap_review

        block = {"review": {"is_software_project": True, "project_type": "CLI"}}
        assert (
            wrap_review(block, self._scan)["code_review"]["review"] == block["review"]
        )
        odd = {"review": {"is_software_project": True, "unplanned_changes": "n/a"}}
        assert wrap_review(odd, self._scan)["code_review"]["review"] == odd["review"]


# ---------------------------------------------------------------------------
# 2.10.0 (D-SC5-4 ii): the keyed-list carry at commit
# ---------------------------------------------------------------------------


def _delta(**over: Any) -> dict[str, Any]:
    """A ``delta`` block naming ``src/app/changed.py`` and ``gone.py`` only."""
    base: dict[str, Any] = {
        "prior": {
            "kind": "prior_review",
            "version": 1,
            "head": "abc",
            "producer": None,
        },
        "files": {
            "added": ["src/app/new.py"],
            "removed": ["gone.py"],
            "modified": ["src/app/changed.py"],
            "partial": False,
            "truncated": False,
        },
        "dependencies": {
            "pyproject.toml": {
                "added": [],
                "removed": [],
                "bumped": [],
                "truncated": False,
            }
        },
        "candidates": {"entered": [], "left": []},
        "signatures": {
            "src/app/quiet.py": {
                "added": [],
                "removed": [],
                "changed": [],
                "truncated": False,
            }
        },
    }
    return {**base, **over}


def _env(name: str, source: str | None = None, **over: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": name, "purpose": f"{name} purpose"}
    if source is not None:
        entry["source"] = source
    return {**entry, **over}


class TestWrapReviewCarry:
    def _carry(
        self,
        emitted: dict[str, Any],
        prior: dict[str, Any] | None,
        scan: dict[str, Any] | None,
    ) -> dict[str, Any]:
        from spec4.agents.code_scanner import wrap_review

        block = {"review": {"is_software_project": True, **emitted}}
        return wrap_review(block, scan, prior)["code_review"]["review"]

    def test_a_dropped_entry_from_an_untouched_file_is_restored(self) -> None:
        # The BWS4 shape: ``config.py`` fell out of the sample, the delta
        # names nothing about it, and the model listed only what it saw.
        prior = review_envelope(
            env_vars=[
                _env("DATABASE_URL", ".env.example"),
                _env("HOURLY_LIMIT", "src/app/config.py", required=False),
                _env("SALT", inferred_from="src/app/config.py"),
            ]
        )
        out = self._carry(
            {"env_vars": [_env("DATABASE_URL", ".env.example", purpose="new")]},
            prior,
            {"delta": _delta()},
        )
        assert out["env_vars"] == [
            _env("DATABASE_URL", ".env.example", purpose="new"),  # the model's
            _env("HOURLY_LIMIT", "src/app/config.py", required=False),
            _env("SALT", inferred_from="src/app/config.py"),
        ]
        # The prior and the block are untouched.
        assert len(prior["code_review"]["review"]["env_vars"]) == 3

    def test_entries_from_paths_the_delta_names_are_not_restored(self) -> None:
        prior = review_envelope(
            env_vars=[
                _env("GONE", "gone.py"),  # removed
                _env("EDITED", "src/app/changed.py"),  # modified
                _env("UNDER", "src/app/"),  # a directory a changed file is under
                _env("UNDER2", "src/app"),
                _env("NAMELESS", "src/app/quiet.py"),
            ],
            dependencies=[
                {"name": "pinned", "source": "pyproject.toml"},
                {"name": "bumped", "source": "frontend/package.json"},
            ],
        )
        delta = _delta(
            dependencies={
                "frontend/package.json": {
                    "added": [],
                    "removed": [],
                    "bumped": ["react"],
                    "truncated": False,
                }
            },
            signatures={
                "src/app/quiet.py": {
                    "added": [],
                    "removed": [],
                    "changed": ["main"],
                    "truncated": False,
                }
            },
        )
        out = self._carry({"env_vars": [], "dependencies": []}, prior, {"delta": delta})
        assert out["env_vars"] == []
        # ``pyproject.toml`` has a delta entry with nothing in it: unchanged.
        assert out["dependencies"] == [{"name": "pinned", "source": "pyproject.toml"}]

    def test_the_model_s_entry_wins_over_the_prior_s_by_name(self) -> None:
        prior = review_envelope(
            dependencies=[
                {"name": "fastapi", "purpose": "old", "source": "pyproject.toml"},
                {"name": "pydantic", "purpose": "kept", "source": "pyproject.toml"},
            ]
        )
        out = self._carry(
            {"dependencies": [{"name": "fastapi", "purpose": "re-derived"}]},
            prior,
            {"delta": _delta()},
        )
        assert out["dependencies"] == [
            {"name": "fastapi", "purpose": "re-derived"},
            {"name": "pydantic", "purpose": "kept", "source": "pyproject.toml"},
        ]

    def test_a_key_the_model_dropped_whole_comes_back(self) -> None:
        prior = review_envelope(env_vars=[_env("A", "cfg.py"), _env("B", "cfg.py")])
        out = self._carry({}, prior, {"delta": _delta()})
        assert out["env_vars"] == [_env("A", "cfg.py"), _env("B", "cfg.py")]

    def test_nothing_carries_without_a_prior_review_a_delta_or_a_complete_delta(
        self,
    ) -> None:
        prior = review_envelope(env_vars=[_env("A", "cfg.py")])
        emitted = {"env_vars": []}
        assert self._carry(emitted, None, {"delta": _delta()})["env_vars"] == []
        stale = {"code_review": {"schema_version": 1, "env_vars": [_env("A", "c")]}}
        assert self._carry(emitted, stale, {"delta": _delta()})["env_vars"] == []
        assert self._carry(emitted, prior, {})["env_vars"] == []
        assert self._carry(emitted, prior, None)["env_vars"] == []
        assert self._carry(emitted, prior, {"delta": "x"})["env_vars"] == []
        for flag in ("partial", "truncated"):
            delta = _delta()
            delta["files"][flag] = True
            assert self._carry(emitted, prior, {"delta": delta})["env_vars"] == []
        # ...and carries with the same delta when both flags are off.
        assert self._carry(emitted, prior, {"delta": _delta()})["env_vars"] == [
            _env("A", "cfg.py")
        ]

    def test_entries_without_a_name_or_a_path_are_never_carried(self) -> None:
        prior = review_envelope(
            env_vars=[
                _env("NO_PATH"),
                _env("BLANK", "  "),
                {"purpose": "nameless", "source": "cfg.py"},
                {"name": 3, "source": "cfg.py"},
                "raw",
                _env("OK", "cfg.py"),
            ],
            dependencies="not-a-list",
        )
        out = self._carry(
            {"env_vars": [{"name": 7}, "raw"], "dependencies": []},
            prior,
            {"delta": _delta()},
        )
        assert out["env_vars"] == [{"name": 7}, "raw", _env("OK", "cfg.py")]
        assert out["dependencies"] == []

    def test_a_delta_without_the_modified_list_still_carries(self) -> None:
        # A 2.9.2 delta (the regression fixture's) has no ``modified``.
        delta = _delta()
        del delta["files"]["modified"]
        prior = review_envelope(env_vars=[_env("A", "cfg.py")])
        out = self._carry({"env_vars": []}, prior, {"delta": delta})
        assert out["env_vars"] == [_env("A", "cfg.py")]

    def test_bws4_2_9_1_to_2_9_2_env_vars_back_to_22_and_dependencies_to_46(
        self,
    ) -> None:
        # The regression case the lever was built from: both models dropped
        # the ten ``config.py``-sourced ``env_vars`` and shrank
        # ``dependencies`` though the delta named neither source file.
        from spec4.agents._code_review_schema import validate_code_review
        from spec4.agents.code_scanner import wrap_review

        fx = load_fixture("carry_bws4_2_9_1_to_2_9_2.json")
        prior = review_envelope(**{k: v for k, v in fx["prior_review"].items()})
        emitted = fx["emitted"]
        assert len(emitted["env_vars"]) == 12
        assert len(emitted["dependencies"]) == 25
        out = wrap_review({"review": emitted}, {"delta": fx["delta"]}, prior)
        review = out["code_review"]["review"]
        assert validate_code_review(out) == []
        assert len(review["env_vars"]) == 22
        assert len(review["dependencies"]) == 46
        assert [e["name"] for e in review["env_vars"][:12]] == [
            e["name"] for e in emitted["env_vars"]
        ]
        restored = {e["name"] for e in review["env_vars"][12:]}
        assert restored == {
            "MODERATION_HASH_SALT",
            "GENERATION_HOURLY_LIMIT",
            "STORAGE_HOURLY_LIMIT",
            "SEARCH_HOURLY_LIMIT",
            "PLANNING_HOURLY_LIMIT",
            "REACT_CYCLE_BUDGET",
            "REACT_DUPLICATE_SIMILARITY_THRESHOLD",
            "REACT_SUITABILITY_TIMEOUT_SECONDS",
            "REACT_SUITABILITY_CHECKS_PER_SESSION",
            "REACT_SUITABILITY_CACHE_TTL_HOURS",
        }
        assert all(
            e["source"] == "backend/app/core/config.py" for e in review["env_vars"][12:]
        )
        # Wrapping the merged review again changes nothing.
        again = wrap_review({"review": review}, {"delta": fx["delta"]}, prior)
        assert again == out

    def test_delta_named_paths_is_the_union_the_rule_is_stated_against(self) -> None:
        from spec4.agents.code_scanner import delta_named_paths

        delta = _delta(
            candidates={"entered": ["src/app/in.py"], "left": ["src/app/out.py"]},
            signatures={
                "src/app/sig.py": {
                    "added": ["x"],
                    "removed": [],
                    "changed": [],
                    "truncated": False,
                },
                "src/app/same.py": {
                    "added": [],
                    "removed": [],
                    "changed": [],
                    "truncated": False,
                },
                "bad": "x",
            },
            dependencies={
                "pyproject.toml": {
                    "added": [],
                    "removed": ["old"],
                    "bumped": [],
                    "truncated": False,
                }
            },
        )
        assert delta_named_paths(delta) == {
            "src/app/new.py",
            "gone.py",
            "src/app/changed.py",
            "src/app/in.py",
            "src/app/out.py",
            "src/app/sig.py",
            "pyproject.toml",
        }
        assert delta_named_paths({}) == set()
        assert delta_named_paths({"files": {"partial": True}}) is None
        assert delta_named_paths({"files": {"truncated": True}}) is None
        assert delta_named_paths({"files": "x"}) is None

    def test_commit_carries_against_the_session_s_prior_review(self) -> None:
        # The prior envelope is still ``session["code_review"]`` at commit.
        from spec4.agents.code_scanner import _scanner_commit

        prior = review_envelope(env_vars=[_env("A", "cfg.py")])
        session = make_session(
            code_review=prior,
            code_scanner_scan={"delta": _delta()},
            code_scanner_messages=[{"role": "assistant", "content": ""}],
        )
        _scanner_commit(
            session,
            session["code_scanner_messages"],
            {"review": {"is_software_project": True, "env_vars": []}},
        )
        assert session["code_review"]["code_review"]["review"]["env_vars"] == [
            _env("A", "cfg.py")
        ]


class TestUpdateSeedCarryRule:
    def _seed(self, delta: dict[str, Any] | None, with_scan: bool = True) -> str:
        from spec4.agents.code_scanner import build_update_scan_seed
        from spec4.agents.code_scanner._sample import ScanEvidence

        scan = {"delta": delta} if delta is not None else {}
        evidence = ScanEvidence([], scan, frozenset()) if with_scan else None
        return build_update_scan_seed(
            "/tmp/does-not-matter", review_envelope(), scan=evidence
        )

    def test_the_rule_and_the_id_reuse_sentence_are_pinned(self) -> None:
        # 2.10.0 (D-SC5-4 i, D-SC5-12), pinned on collapsed whitespace.
        body = " ".join(self._seed(_delta()).split())
        assert (
            "**Carry what the scan did not touch.** An entry whose `source` / "
            "`inferred_from` path is not in the changed-path list below is "
            "carried verbatim from the prior review: the prior is the evidence "
            "for it, whether or not that file appears in this scan's evidence. "
            "Re-derive only entries whose path the list names, add entries for "
            "paths it adds, and drop entries for paths it removes. This covers "
            "`implemented[].status`: an entry whose paths the list does not "
            'name keeps its status. "Complete" means the carried entries plus '
            "the re-derived ones, never a fresh listing of what you can see." in body
        )
        assert (
            "Reuse the prior review's `implemented[].id` for a capability it "
            "already names; mint a new id only for a capability it does not." in body
        )
        # The earlier labels still hold verbatim beside the new rule.
        assert "Added / Removed / Changed." in body
        assert "is marked **Previously omitted**, not Added" in body

    def test_the_changed_paths_block_renders_every_set_in_full(self) -> None:
        delta = _delta(
            candidates={"entered": ["src/app/in.py"], "left": []},
            signatures={
                "src/app/sig.py": {
                    "added": [],
                    "removed": [],
                    "changed": ["main"],
                    "truncated": False,
                },
                "src/app/same.py": {
                    "added": [],
                    "removed": [],
                    "changed": [],
                    "truncated": False,
                },
            },
            dependencies={
                "pyproject.toml": {
                    "added": ["x"],
                    "removed": [],
                    "bumped": [],
                    "truncated": False,
                }
            },
        )
        delta["files"]["added"] = [f"src/app/n{i}.py" for i in range(30)]
        seed = self._seed(delta)
        block = seed.split("**Paths this scan changed**")[1].split(
            "**Prior code review on disk:**"
        )[0]
        assert "(measured against the prior scan):" in block
        lines = [ln for ln in block.splitlines() if ln.startswith("- ")]
        assert lines == [
            "- Files added: " + ", ".join(f"`src/app/n{i}.py`" for i in range(30)),
            "- Files removed: `gone.py`",
            "- Files modified: `src/app/changed.py`",
            "- Signatures changed: `src/app/sig.py`",
            "- Manifests changed: `pyproject.toml`",
            "- Load-bearing candidates entered: `src/app/in.py`",
            "- Load-bearing candidates left: none",
        ]
        assert "incomplete" not in block
        # The block sits between the instructions and the prior paste.
        assert (
            seed.index("**Update mode instructions:**")
            < seed.index("**Paths this scan changed**")
            < seed.index("**Prior code review on disk:**")
        )

    def test_without_a_delta_the_rule_is_suspended(self) -> None:
        for seed in (self._seed(None), self._seed(None, with_scan=False)):
            assert (
                "**Paths this scan changed:** no prior scan was measured, so "
                "there is no changed-path list; re-derive from the evidence and "
                "carry nothing on the strength of the prior alone." in seed
            )
            assert "Files added:" not in seed

    def test_a_partial_or_truncated_delta_says_the_list_is_incomplete(self) -> None:
        for flag in ("partial", "truncated"):
            delta = _delta()
            delta["files"][flag] = True
            seed = self._seed(delta)
            assert "- Files added: `src/app/new.py`" in seed
            assert (
                "- This list is incomplete (a capped listing or a capped delta): "
                "a path not shown may still have changed, so carry nothing on "
                "the strength of this list alone." in seed
            )
        assert "This list is incomplete" not in self._seed(_delta())
