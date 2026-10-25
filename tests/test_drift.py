"""CodeScanner v2 step 1d: the ``plan_drift`` block.

Covers ``code_scanner._drift`` — the normaliser, the scoped-name subset
match, the buckets and their sources — against the trimmed BWS4 v8 round,
whose stack and phases spell the same libraries two ways (StackAdvisor
display names, Phaser package names), plus the block's place in
``collect_scan`` and the schema. 2.13.0 (D-SC1d-11) adds ``_tooling``: the
files and manifest tables that witness a planned runtime or tool no manifest
declares, and the ``planned_tooling`` bucket they feed.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any
from unittest.mock import patch

import pytest

from spec4.agents._code_review_schema import validate_code_review
from spec4.agents.code_scanner import _collect, _drift, _tooling
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
    witnesses = _tooling.tooling_witnesses(root, files)
    return _drift.plan_drift_block(
        scan["prior_round"], scan["dependencies"], graph, witnesses
    )


def _write_deploy(root: pathlib.Path) -> None:
    """The three files BWS4's v8 round left that no manifest can declare."""
    (root / "uv.lock").write_text("version = 1\n")
    (root / "deploy").mkdir()
    (root / "deploy" / "Caddyfile").write_text("bw.spec4.ai {\n}\n")
    (root / "deploy" / "bws4-api.service").write_text("[Unit]\n")


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
        # 2.13.0 (D-SC1d-11): the two manifests witness their runtimes; the
        # three deploy-time names have nothing in this tree yet.
        assert _names(drift["planned_unmatched"]) == [
            "Caddy 2",
            "Playwright",
            "systemd",
            "uv",
        ]
        assert [(e["name"], e["witnessed_by"]) for e in drift["planned_tooling"]] == [
            ("Node 20", ["frontend/package.json"]),
            ("Python 3.12", ["pyproject.toml"]),
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

    def test_dev_tools_in_dependency_groups_are_declared_not_unmatched(
        self, tmp_path: pathlib.Path
    ) -> None:
        # 2.7.1 (D-SC4-13): the Spec4-shaped case — ``uv`` puts the dev tools
        # the plan names into PEP 735 ``[dependency-groups]``, which 1d's
        # parser did not read, so they fell into ``planned_unmatched`` and
        # 3b showed StackAdvisor "planned, not found" for tools in daily use.
        install_rounds(tmp_path, 8)
        _write_manifests(tmp_path)
        tools = ["mypy", "pytest", "ruff", "pytest-cov"]
        runtime = [n for n in _PYTHON_DECLARED if n not in tools]
        (tmp_path / "pyproject.toml").write_text(
            "[project]\nname = 'bws4'\ndependencies = [\n"
            + "".join(f'  "{n}>=1",\n' for n in runtime)
            + "]\n[dependency-groups]\ndev = [\n"
            + "".join(f'  "{n}>=1",\n' for n in tools)
            + "]\n"
        )
        drift = _drift_of(tmp_path, {"caddy_api": 1, "remark_gfm": 3})
        matched = {e["name"]: e["manifest"] for e in drift["planned_in_manifests"]}
        for name in ("mypy", "pytest", "Ruff"):
            assert matched[name] == "pyproject.toml"
            assert name not in _names(drift["planned_unmatched"])
        # v8 never planned pytest-cov: declared from the group, still unplanned.
        assert "pytest-cov" in _names(drift["declared_not_planned"])
        # Everything else is as the full-manifest case above.
        assert _names(drift["planned_unmatched"]) == [
            "Caddy 2",
            "Playwright",
            "systemd",
            "uv",
        ]
        assert _names(drift["planned_tooling"]) == ["Node 20", "Python 3.12"]
        assert drift["declared"] == len(_PYTHON_DECLARED) + len(_JS_DECLARED)

    def test_bws4_v8_with_its_deploy_files_leaves_only_playwright_unmatched(
        self, tmp_path: pathlib.Path
    ) -> None:
        # 2.13.0 (D-SC1d-11): the case the lever was built from — five of the
        # six "planned, not found" entries StackAdvisor read on BWS4's v8
        # round were a runtime, a package manager, a unit file and a reverse
        # proxy in daily use. With the files BWS4 holds, only Playwright is
        # left: the v8 stack named it and nothing in the tree supports it.
        install_rounds(tmp_path, 8)
        _write_manifests(tmp_path)
        _write_deploy(tmp_path)
        drift = _drift_of(tmp_path, {"caddy_api": 1, "remark_gfm": 3})
        assert drift["planned_unmatched"] == [
            {"name": "Playwright", "sources": ["stack"]}
        ]
        tooling = {e["name"]: e["witnessed_by"] for e in drift["planned_tooling"]}
        assert tooling == {
            "Caddy 2": ["deploy/Caddyfile"],
            "Node 20": ["frontend/package.json"],
            "Python 3.12": ["pyproject.toml", "uv.lock"],
            "systemd": ["deploy/bws4-api.service"],
            "uv": ["uv.lock"],
        }
        assert [e["name"] for e in drift["planned_tooling"]] == sorted(
            tooling, key=str.lower
        )
        # The sources ride along, as in every other bucket.
        by_name = {e["name"]: e["sources"] for e in drift["planned_tooling"]}
        assert by_name["systemd"] == ["phase:2", "phase:3", "phase:4", "phase:6"]
        # The other buckets are untouched by the new one.
        assert drift["planned"] == 41
        assert len(drift["planned_in_manifests"]) == 41 - 5 - 1 - 1
        assert _names(drift["planned_only_imported"]) == ["remark-gfm"]
        assert drift["truncated"] is False
        # And the block is what ``collect_scan`` stores.
        files = collect_files(tmp_path)
        scan = _collect.collect_scan(str(tmp_path), files, SampleRecord(), None)
        assert scan["plan_drift"]["planned_tooling"] == drift["planned_tooling"]
        assert validate_code_review(review_envelope(scan=scan)) == []

    def test_a_declared_or_imported_tool_is_not_tooling(self) -> None:
        # Bucket order: manifests, then imports, then witnesses — a declared
        # or imported tool is evidence of use in the code, a witness only of
        # presence in the tree.
        prior = {
            "version": 1,
            "stack": {
                "libraries": [{"name": "pytest"}, {"name": "Ruff"}, {"name": "uv"}]
            },
            "phases": [],
        }
        manifests = {"files": {"pyproject.toml": {"pytest": ">=9"}}, "truncated": False}
        graph = {"unresolved": {"ruff": 2}}
        witnesses = {
            "pytest": ["conftest.py"],
            "ruff": ["ruff.toml"],
            "uv": ["uv.lock"],
        }
        drift = _drift.plan_drift_block(prior, manifests, graph, witnesses)
        assert _names(drift["planned_in_manifests"]) == ["pytest"]
        assert _names(drift["planned_only_imported"]) == ["Ruff"]
        assert drift["planned_tooling"] == [
            {"name": "uv", "sources": ["stack"], "witnessed_by": ["uv.lock"]}
        ]
        assert drift["planned_unmatched"] == []
        # Without witnesses (a pre-2.13.0 caller) the tool is unmatched.
        before = _drift.plan_drift_block(prior, manifests, graph)
        assert before["planned_tooling"] == []
        assert _names(before["planned_unmatched"]) == ["uv"]
        # The witness list is a copy, not the map's own.
        drift["planned_tooling"][0]["witnessed_by"].append("x")
        assert witnesses["uv"] == ["uv.lock"]

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
        tooling = {e["name"]: e["sources"] for e in drift["planned_tooling"]}
        assert tooling["Python 3.12"][0] == "phase:1"

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
        assert drift["planned_tooling"] == []
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
        # The tooling bucket is capped and counted the same way.
        witnesses = {f"lib{i}": ["w"] for i in range(5)}
        with patch.object(_drift, "_MAX_ENTRIES", 3):
            drift = _drift.plan_drift_block(prior, {"files": {}}, {}, witnesses)
        assert len(drift["planned_tooling"]) == 3
        assert drift["planned_unmatched"] == []
        assert drift["truncated"] is True


class TestToolingWitnesses:
    # 2.13.0 (D-SC1d-11): ``_tooling.tooling_witnesses`` — the file table and
    # the manifest tables, over the walked tree.

    @staticmethod
    def _witnesses(root: pathlib.Path) -> dict[str, list[str]]:
        return _tooling.tooling_witnesses(root, collect_files(root))

    def test_file_names_witness_their_tools(self, tmp_path: pathlib.Path) -> None:
        for rel in (
            "uv.lock",
            ".python-version",
            "deploy/api.service",
            "deploy/Caddyfile",
            "Dockerfile",
            "docker-compose.prod.yml",
            ".github/workflows/ci.yml",
            "Makefile",
            "frontend/package.json",
            "frontend/.nvmrc",
            "frontend/pnpm-lock.yaml",
            "frontend/playwright.config.ts",
            "frontend/vite.config.ts",
            "frontend/tsconfig.app.json",
            "frontend/.oxlintrc.json",
            "frontend/tailwind.config.js",
            "backend/alembic.ini",
            "backend/tests/conftest.py",
            "infra/main.tf",
            "go.mod",
        ):
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}" if rel.endswith(".json") else "")
        out = self._witnesses(tmp_path)
        assert out["uv"] == ["uv.lock"]
        assert out["python"] == [".python-version", "uv.lock"]
        assert out["systemd"] == ["deploy/api.service"]
        assert out["caddy"] == ["deploy/Caddyfile"]
        assert out["docker"] == ["Dockerfile", "docker-compose.prod.yml"]
        assert out["dockercompose"] == ["docker-compose.prod.yml"]
        assert out["compose"] == ["docker-compose.prod.yml"]
        assert out["githubactions"] == [".github/workflows/ci.yml"]
        assert out["make"] == ["Makefile"]
        assert out["node"] == ["frontend/.nvmrc", "frontend/package.json"]
        assert out["nodejs"] == out["node"]
        assert out["pnpm"] == ["frontend/pnpm-lock.yaml"]
        assert out["playwright"] == ["frontend/playwright.config.ts"]
        assert out["vite"] == ["frontend/vite.config.ts"]
        assert out["typescript"] == ["frontend/tsconfig.app.json"]
        assert out["oxlint"] == ["frontend/.oxlintrc.json"]
        assert out["tailwindcss"] == ["frontend/tailwind.config.js"]
        assert out["tailwind"] == out["tailwindcss"]
        assert out["alembic"] == ["backend/alembic.ini"]
        assert out["pytest"] == ["backend/tests/conftest.py"]
        assert out["terraform"] == ["infra/main.tf"]
        assert out["go"] == ["go.mod"]
        assert out["golang"] == ["go.mod"]
        # Nothing witnesses what the tree does not hold.
        for absent in ("vitest", "nginx", "rust", "poetry", "yarn", "ruff", "mypy"):
            assert absent not in out

    def test_the_walk_s_pruning_applies(self, tmp_path: pathlib.Path) -> None:
        # A vendored copy under ``node_modules`` or ``.venv`` is not the
        # project's tooling; the walk already leaves those out.
        for rel in ("node_modules/x/Dockerfile", ".venv/lib/uv.lock", "src/app.py"):
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
        assert self._witnesses(tmp_path) == {}

    def test_names_are_case_sensitive_and_paths_are_posix(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / "caddyfile").write_text("")  # not the name
        (tmp_path / "makefile").write_text("")  # a spelling make accepts
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "Dockerfile.dev").write_text("")
        out = self._witnesses(tmp_path)
        assert "caddy" not in out
        assert out["make"] == ["makefile"]
        assert out["docker"] == ["a/Dockerfile.dev"]

    def test_witnesses_are_capped_per_key_in_walk_order(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / "deploy").mkdir()
        for name in ("a", "b", "c", "d"):
            (tmp_path / "deploy" / f"{name}.service").write_text("")
        out = self._witnesses(tmp_path)
        assert out["systemd"] == [
            "deploy/a.service",
            "deploy/b.service",
            "deploy/c.service",
        ]

    def test_pyproject_tables_witness_without_declaring(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[project]\nname = 'x'\nrequires-python = '>=3.12'\n"
            "[build-system]\nrequires = ['hatchling>=1.0', 'uv_build', 7]\n"
            "[tool.ruff]\nline-length = 88\n[tool.mypy]\nstrict = true\n"
            "[tool.uv]\n[tool.pytest.ini_options]\naddopts = '-q'\n"
        )
        out = self._witnesses(tmp_path)
        assert out["python"] == ["pyproject.toml", "pyproject.toml requires-python"]
        assert out["ruff"] == ["pyproject.toml [tool.ruff]"]
        assert out["mypy"] == ["pyproject.toml [tool.mypy]"]
        assert out["uv"] == ["pyproject.toml [tool.uv]"]
        assert out["pytest"] == ["pyproject.toml [tool.pytest]"]
        assert out["hatchling"] == ["pyproject.toml [build-system].requires"]
        assert out["uvbuild"] == ["pyproject.toml [build-system].requires"]
        # Unparseable or shapeless: the file name still witnesses Python
        # (under each of its spellings), the tables nothing.
        (tmp_path / "pyproject.toml").write_text("[tool.ruff\n")
        out = self._witnesses(tmp_path)
        assert out["python"] == ["pyproject.toml"]
        assert all(v == ["pyproject.toml"] for v in out.values())
        (tmp_path / "pyproject.toml").write_text(
            "tool = 3\nproject = 'x'\n[build-system]\nrequires = 'hatchling'\n"
        )
        out = self._witnesses(tmp_path)
        assert out["python"] == ["pyproject.toml"]
        assert all(v == ["pyproject.toml"] for v in out.values())

    def test_package_json_engines_and_package_manager(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / "package.json").write_text(
            json.dumps(
                {
                    "engines": {"node": ">=20", "npm": ">=10"},
                    "packageManager": "pnpm@9.1.0",
                }
            )
        )
        out = self._witnesses(tmp_path)
        assert out["node"] == ["package.json", "package.json engines.node"]
        assert out["npm"] == ["package.json engines.npm"]
        assert out["pnpm"] == ["package.json packageManager"]
        (tmp_path / "package.json").write_text(
            json.dumps({"engines": {"": ">=1", "node": "20"}, "packageManager": "@9"})
        )
        out = self._witnesses(tmp_path)
        assert "" not in out
        assert out["node"] == ["package.json", "package.json engines.node"]
        for text in (
            "[1, 2]",
            "{not json",
            json.dumps({"engines": "node", "packageManager": "  "}),
        ):
            (tmp_path / "package.json").write_text(text)
            out = self._witnesses(tmp_path)
            assert out["node"] == ["package.json"]
            assert all(v == ["package.json"] for v in out.values())
            assert "npm" not in out
            assert "pnpm" not in out

    def test_tool_versions_lines(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / ".tool-versions").write_text(
            "nodejs 20.11.0\npython 3.12.1 # system\n\n# golang 1.22\n"
            "#rust 1.80\nuv 0.5\npython 3.11\n-- 1.0\n"
        )
        out = self._witnesses(tmp_path)
        assert out["nodejs"] == [".tool-versions nodejs"]
        # A tool named twice is one witness; a comment, with or without the
        # space, is none; a line that folds to nothing stores no key.
        assert out["python"] == [".tool-versions python"]
        assert out["uv"] == [".tool-versions uv"]
        assert "golang" not in out
        assert "rust" not in out
        assert "" not in out
        assert set(out) == {"nodejs", "python", "uv"}

    def test_unreadable_manifests_and_the_manifest_cap(
        self, tmp_path: pathlib.Path
    ) -> None:
        for i in range(3):
            d = tmp_path / f"p{i}"
            d.mkdir()
            (d / "pyproject.toml").write_text("[tool.ruff]\n")
        files = collect_files(tmp_path)
        with patch.object(_tooling, "_MAX_MANIFESTS", 2):
            out = _tooling.tooling_witnesses(tmp_path, files)
        # Three file-name witnesses, two opened manifests.
        assert out["python"] == [
            "p0/pyproject.toml",
            "p1/pyproject.toml",
            "p2/pyproject.toml",
        ]
        assert out["ruff"] == [
            "p0/pyproject.toml [tool.ruff]",
            "p1/pyproject.toml [tool.ruff]",
        ]
        with patch.object(_tooling, "_read_text_safely", lambda *_: None):
            out = _tooling.tooling_witnesses(tmp_path, files)
        assert "ruff" not in out
        assert len(out["python"]) == 3


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

    def test_planned_tooling_is_optional_and_closed(
        self, tmp_path: pathlib.Path
    ) -> None:
        # 2.13.0 (D-SC1d-11): a 2.3.0…2.12.0 block has no ``planned_tooling``
        # and still validates; a present one is closed on its three keys.
        install_rounds(tmp_path, 8)
        _write_manifests(tmp_path)
        _write_deploy(tmp_path)
        files = collect_files(tmp_path)
        scan = _collect.collect_scan(str(tmp_path), files, SampleRecord(), None)
        assert len(scan["plan_drift"]["planned_tooling"]) == 5
        assert validate_code_review(review_envelope(scan=scan)) == []
        del scan["plan_drift"]["planned_tooling"]
        assert validate_code_review(review_envelope(scan=scan)) == []
        scan["plan_drift"]["planned_tooling"] = [{"name": "uv", "sources": []}]
        assert validate_code_review(review_envelope(scan=scan)) != []
        scan["plan_drift"]["planned_tooling"] = [
            {"name": "uv", "sources": [], "witnessed_by": ["uv.lock"], "x": 1}
        ]
        assert validate_code_review(review_envelope(scan=scan)) != []
        scan["plan_drift"]["planned_tooling"] = [
            {"name": "uv", "sources": [], "witnessed_by": "uv.lock"}
        ]
        assert validate_code_review(review_envelope(scan=scan)) != []
