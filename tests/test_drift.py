"""CodeScanner v2 step 1d: the ``plan_drift`` block.

Covers ``code_scanner._drift`` — the normaliser, the scoped-name subset
match, the four buckets and their sources — against the trimmed BWS4 v8
round, whose stack and phases spell the same libraries two ways (StackAdvisor
display names, Phaser package names), plus the block's place in
``collect_scan`` and the schema.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any
from unittest.mock import patch

import pytest

from spec4.agents._code_review_schema import validate_code_review
from spec4.agents.code_scanner import _collect, _drift
from spec4.agents.code_scanner._scan import SampleRecord, collect_files
from tests._review_helpers import review_envelope
from tests.test_prior import install_rounds

_PYTHON_DECLARED = [
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "asyncpg",
    "alembic",
    "pgvector",
    "pydantic",
    "pydantic-settings",
    "pydantic-ai",
    "litellm",
    "sentence-transformers",
    "torch",
    "scikit-learn",
    "numpy",
    "httpx",
    "sse-starlette",
    "structlog",
    "tenacity",
    "sentry-sdk",
    "mypy",
    "pytest",
    "ruff",
    "pytest-cov",
]
_JS_DECLARED = [
    "react",
    "react-dom",
    "react-router",
    "@tanstack/react-query",
    "@microsoft/fetch-event-source",
    "plotly.js",
    "react-plotly.js",
    "react-markdown",
    "@sentry/react",
    "typescript",
    "vite",
    "@vitejs/plugin-react",
    "vitest",
    "jsdom",
    "@testing-library/react",
    "@testing-library/jest-dom",
    "oxlint",
    "tailwindcss",
]


def _write_manifests(root: pathlib.Path) -> None:
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'bws4'\ndependencies = [\n"
        + "".join(f'  "{n}>=1",\n' for n in _PYTHON_DECLARED)
        + "]\n"
    )
    (root / "frontend").mkdir()
    (root / "frontend" / "package.json").write_text(
        json.dumps({"dependencies": {n: "^1" for n in _JS_DECLARED}})
    )


def _drift_of(
    root: pathlib.Path, unresolved: dict[str, int] | None = None
) -> dict[str, Any]:
    files = collect_files(root)
    scan = _collect.collect_scan(str(root), files, SampleRecord(), None)
    graph = {**scan["module_graph"], "unresolved": unresolved or {}}
    return _drift.plan_drift_block(scan["prior_round"], scan["dependencies"], graph)


def _names(entries: list[dict[str, Any]]) -> list[str]:
    return [e["name"] for e in entries]


class TestNormalise:
    @pytest.mark.parametrize(
        ("name", "key"),
        [
            ("PydanticAI", "pydanticai"),
            ("pydantic-ai", "pydanticai"),
            ("pydantic_ai", "pydanticai"),
            ("Tailwind CSS", "tailwindcss"),
            ("React Router", "reactrouter"),
            ("Python 3.12", "python"),
            ("Node 20", "node"),
            ("Caddy 2", "caddy"),
            ("TypeScript 5.9", "typescript"),
            ("plotly.js", "plotlyjs"),
            ("vue3", "vue3"),
            ("  ", ""),
            ("3.12", "312"),
        ],
    )
    def test_fold(self, name: str, key: str) -> None:
        assert _drift.normalise(name) == key

    def test_tokens(self) -> None:
        assert _drift.tokens("TanStack Query") == {"tanstack", "query"}
        assert _drift.tokens("@tanstack/react-query") == {"tanstack", "react", "query"}
        assert _drift.tokens("Node 20") == {"node"}


class TestBuckets:
    def test_bws4_v8_against_its_manifests(self, tmp_path: pathlib.Path) -> None:
        install_rounds(tmp_path, 8)
        _write_manifests(tmp_path)
        drift = _drift_of(tmp_path, {"caddy_api": 1, "remark_gfm": 3})
        assert drift["prior_version"] == 8
        assert drift["planned"] == 41
        assert drift["declared"] == len(_PYTHON_DECLARED) + len(_JS_DECLARED)
        # The five spellings that differ between StackAdvisor and Phaser.
        matched = {e["name"]: e["declared_as"] for e in drift["planned_in_manifests"]}
        assert matched["PydanticAI"] == "pydantic-ai"
        assert matched["React Router"] == "react-router"
        assert matched["Tailwind CSS"] == "tailwindcss"
        assert matched["TanStack Query"] == "@tanstack/react-query"
        assert matched["React Testing Library"] == "@testing-library/react"
        assert _names(drift["planned_unmatched"]) == [
            "Caddy 2",
            "Node 20",
            "Playwright",
            "Python 3.12",
            "systemd",
            "uv",
        ]
        assert _names(drift["planned_only_imported"]) == ["remark-gfm"]
        assert drift["planned_only_imported"][0]["imported_as"] == "remark_gfm"
        assert drift["planned_only_imported"][0]["imports"] == 3
        unplanned = _names(drift["declared_not_planned"])
        assert "oxlint" in unplanned
        assert "pytest-cov" in unplanned
        assert "react" not in unplanned
        assert "@testing-library/react" not in unplanned
        assert drift["truncated"] is False

    def test_sources_name_the_stack_and_each_phase(
        self, tmp_path: pathlib.Path
    ) -> None:
        install_rounds(tmp_path, 8)
        _write_manifests(tmp_path)
        drift = _drift_of(tmp_path)
        by_name = {e["name"]: e["sources"] for e in drift["planned_in_manifests"]}
        assert by_name["uvicorn"] == [
            "stack",
            "phase:1",
            "phase:2",
            "phase:3",
            "phase:4",
            "phase:5",
            "phase:6",
        ]
        assert by_name["httpx"] == ["stack"]
        unmatched = {e["name"]: e["sources"] for e in drift["planned_unmatched"]}
        assert unmatched["systemd"] == ["phase:2", "phase:3", "phase:4", "phase:6"]
        assert unmatched["Python 3.12"][0] == "phase:1"

    def test_manifest_entry_names_the_manifest(self, tmp_path: pathlib.Path) -> None:
        install_rounds(tmp_path, 8)
        _write_manifests(tmp_path)
        drift = _drift_of(tmp_path)
        by_name = {e["name"]: e["manifest"] for e in drift["planned_in_manifests"]}
        assert by_name["FastAPI"] == "pyproject.toml"
        assert by_name["React"] == "frontend/package.json"
        unplanned = {e["name"]: e["manifest"] for e in drift["declared_not_planned"]}
        assert unplanned["oxlint"] == "frontend/package.json"

    def test_no_manifests_leaves_everything_unmatched(
        self, tmp_path: pathlib.Path
    ) -> None:
        install_rounds(tmp_path, 8)
        drift = _drift_of(tmp_path)
        assert drift["declared"] == 0
        assert drift["planned_in_manifests"] == []
        assert drift["declared_not_planned"] == []
        assert len(drift["planned_unmatched"]) == 41

    def test_no_plan_leaves_everything_unplanned(self, tmp_path: pathlib.Path) -> None:
        prior = {"version": 3, "stack": None, "phases": []}
        manifests = {"files": {"go.mod": {"github.com/x/y": "v1"}}, "truncated": False}
        drift = _drift.plan_drift_block(prior, manifests, {})
        assert drift["planned"] == 0
        assert drift["declared_not_planned"] == [
            {"name": "github.com/x/y", "manifest": "go.mod"}
        ]
        assert drift["planned_unmatched"] == []


class TestMatching:
    def test_subset_match_needs_two_tokens_and_a_scoped_name(self) -> None:
        prior = {
            "version": 1,
            "stack": {"libraries": [{"name": "React"}, {"name": "Testing Library"}]},
            "phases": [],
        }
        declared = {"@types/react": "1", "@testing-library/react": "1"}
        manifests = {"files": {"package.json": declared}, "truncated": False}
        drift = _drift.plan_drift_block(prior, manifests, {})
        assert _names(drift["planned_unmatched"]) == ["React"]
        assert (
            drift["planned_in_manifests"][0]["declared_as"] == "@testing-library/react"
        )
        assert _names(drift["declared_not_planned"]) == ["@types/react"]

    def test_subset_match_ignores_unscoped_names(self) -> None:
        prior = {
            "version": 1,
            "stack": {"libraries": [{"name": "React Query"}]},
            "phases": [],
        }
        manifests = {
            "files": {"package.json": {"react-query-devtools": "1"}},
            "truncated": False,
        }
        drift = _drift.plan_drift_block(prior, manifests, {})
        assert _names(drift["planned_unmatched"]) == ["React Query"]

    def test_several_scoped_hits_take_the_first_by_name(self) -> None:
        prior = {
            "version": 1,
            "stack": {"libraries": [{"name": "React Query"}]},
            "phases": [],
        }
        manifests = {
            "files": {
                "package.json": {"@z/react-query": "1", "@a/react-query-core": "1"}
            },
            "truncated": False,
        }
        drift = _drift.plan_drift_block(prior, manifests, {})
        assert drift["planned_in_manifests"][0]["declared_as"] == "@a/react-query-core"

    def test_first_spelling_and_first_manifest_win(self) -> None:
        prior = {
            "version": 1,
            "stack": {"libraries": [{"name": "Pydantic AI"}]},
            "phases": [{"number": 1, "dependencies": ["pydantic-ai"]}],
        }
        manifests = {
            "files": {
                "a/pyproject.toml": {"pydantic_ai": ""},
                "b/pyproject.toml": {"Pydantic-AI": ""},
            },
            "truncated": False,
        }
        drift = _drift.plan_drift_block(prior, manifests, {})
        assert drift["planned"] == 1
        entry = drift["planned_in_manifests"][0]
        assert entry["name"] == "Pydantic AI"
        assert entry["sources"] == ["stack", "phase:1"]
        assert entry["declared_as"] == "pydantic_ai"
        assert entry["manifest"] == "a/pyproject.toml"

    def test_odd_shapes_are_ignored(self) -> None:
        prior = {
            "version": 1,
            "stack": {"libraries": ["bare", {"name": 3}, {"name": "  "}]},
            "phases": ["nope", {"number": 2, "dependencies": [None, "ok"]}],
        }
        manifests = {"files": {"m": "nope", "n": {"ok": "1"}}, "truncated": False}
        drift = _drift.plan_drift_block(prior, manifests, {"unresolved": "x"})
        assert drift["planned"] == 1
        assert drift["planned_in_manifests"][0]["sources"] == ["phase:2"]

    def test_cap_is_declared(self) -> None:
        prior = {
            "version": 1,
            "stack": {"libraries": [{"name": f"lib{i}"} for i in range(5)]},
            "phases": [],
        }
        with patch.object(_drift, "_MAX_ENTRIES", 3):
            drift = _drift.plan_drift_block(prior, {"files": {}}, {})
        assert len(drift["planned_unmatched"]) == 3
        assert drift["truncated"] is True


class TestSchema:
    def test_the_block_validates_and_is_closed(self, tmp_path: pathlib.Path) -> None:
        install_rounds(tmp_path, 8)
        _write_manifests(tmp_path)
        files = collect_files(tmp_path)
        scan = _collect.collect_scan(str(tmp_path), files, SampleRecord(), None)
        assert scan["plan_drift"]["prior_version"] == 8
        assert validate_code_review(review_envelope(scan=scan)) == []
        scan["plan_drift"]["planned_in_manifests"][0]["why"] = "x"
        errors = validate_code_review(review_envelope(scan=scan))
        assert errors
        assert any("why" in e for e in errors)
