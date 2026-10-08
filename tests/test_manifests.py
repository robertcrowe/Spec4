"""CodeScanner v2 step 1d: the ``dependencies`` block.

Covers ``code_scanner._manifests`` — the three parsers (``pyproject.toml``,
``package.json``, ``go.mod``), what each keeps and ignores, and the block's
cap — plus its place in ``collect_scan`` and the schema.
"""

from __future__ import annotations

import pathlib
from unittest.mock import patch

from spec4.agents._code_review_schema import validate_code_review
from spec4.agents.code_scanner import _collect, _manifests
from spec4.agents.code_scanner._scan import SampleRecord, collect_files
from tests._review_helpers import review_envelope


def _write(root: pathlib.Path, rel: str, text: str) -> pathlib.Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


_PYPROJECT = """
[project]
name = "x"
dependencies = [
  "fastapi>=0.100",
  "uvicorn[standard] >= 0.30, < 1",
  "Pydantic_Settings",
  "httpx ; python_version < '4'",
]

[project.optional-dependencies]
dev = ["pytest", "ruff==0.5"]
docs = ["mkdocs"]

[tool.poetry.dependencies]
ignored = "^1"
"""

_PACKAGE_JSON = """{
  "name": "web",
  "dependencies": {"react": "^18.2.0", "@tanstack/react-query": "5.0.0"},
  "devDependencies": {"vite": "^5", "react": "^0"},
  "peerDependencies": {"ignored": "*"}
}
"""

_GO_MOD = """module example.com/app

go 1.22

require github.com/one/single v1.2.3

require (
\tgithub.com/two/block v0.9.0
\tgolang.org/x/text v0.14.0 // indirect
)
"""


class TestPyproject:
    def test_names_and_specs_from_project_and_optional_groups(
        self, tmp_path: pathlib.Path
    ) -> None:
        deps = _manifests.parse_manifest(_write(tmp_path, "pyproject.toml", _PYPROJECT))
        assert deps == {
            "fastapi": ">=0.100",
            "uvicorn": "[standard] >= 0.30, < 1",
            "Pydantic_Settings": "",
            "httpx": "; python_version < '4'",
            "pytest": "",
            "ruff": "==0.5",
            "mkdocs": "",
        }
        assert "ignored" not in deps

    def test_no_project_table_is_empty_not_none(self, tmp_path: pathlib.Path) -> None:
        path = _write(tmp_path, "pyproject.toml", "[tool.ruff]\nline-length = 88\n")
        assert _manifests.parse_manifest(path) == {}

    def test_invalid_toml_is_none(self, tmp_path: pathlib.Path) -> None:
        path = _write(tmp_path, "pyproject.toml", "[project\nname =\n")
        assert _manifests.parse_manifest(path) is None

    def test_non_string_requirements_are_skipped(self, tmp_path: pathlib.Path) -> None:
        path = _write(
            tmp_path, "pyproject.toml", '[project]\ndependencies = [1, "a", {b=1}]\n'
        )
        assert _manifests.parse_manifest(path) == {"a": ""}


class TestPackageJson:
    def test_dependencies_and_dev_dependencies_first_wins(
        self, tmp_path: pathlib.Path
    ) -> None:
        deps = _manifests.parse_manifest(
            _write(tmp_path, "package.json", _PACKAGE_JSON)
        )
        assert deps == {
            "react": "^18.2.0",
            "@tanstack/react-query": "5.0.0",
            "vite": "^5",
        }
        assert "ignored" not in deps

    def test_invalid_or_non_object_json_is_none(self, tmp_path: pathlib.Path) -> None:
        assert _manifests.parse_manifest(_write(tmp_path, "package.json", "{")) is None
        assert _manifests.parse_manifest(_write(tmp_path, "package.json", "[]")) is None


class TestGoMod:
    def test_single_and_block_requires(self, tmp_path: pathlib.Path) -> None:
        deps = _manifests.parse_manifest(_write(tmp_path, "go.mod", _GO_MOD))
        assert deps == {
            "github.com/one/single": "v1.2.3",
            "github.com/two/block": "v0.9.0",
            "golang.org/x/text": "v0.14.0",
        }

    def test_no_requires_is_empty(self, tmp_path: pathlib.Path) -> None:
        path = _write(tmp_path, "go.mod", "module example.com/app\n\ngo 1.22\n")
        assert _manifests.parse_manifest(path) == {}


class TestParseManifest:
    def test_other_names_and_unreadable_files_are_none(
        self, tmp_path: pathlib.Path
    ) -> None:
        assert _manifests.parse_manifest(_write(tmp_path, "setup.py", "")) is None
        assert _manifests.parse_manifest(tmp_path / "missing" / "go.mod") is None


class TestManifestsBlock:
    def test_every_manifest_in_the_walk_by_path(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "pyproject.toml", _PYPROJECT)
        _write(tmp_path, "web/package.json", _PACKAGE_JSON)
        _write(tmp_path, "svc/go.mod", _GO_MOD)
        _write(
            tmp_path,
            "web/node_modules/dep/package.json",
            '{"dependencies": {"x": "1"}}',
        )
        _write(tmp_path, "broken/package.json", "{")
        block = _manifests.dependencies_block(tmp_path, collect_files(tmp_path))
        assert set(block["files"]) == {
            "pyproject.toml",
            "web/package.json",
            "svc/go.mod",
        }
        assert block["files"]["svc/go.mod"]["github.com/one/single"] == "v1.2.3"
        assert block["truncated"] is False

    def test_cap_is_declared(self, tmp_path: pathlib.Path) -> None:
        for i in range(3):
            _write(tmp_path, f"p{i}/go.mod", _GO_MOD)
        with patch.object(_manifests, "_MAX_MANIFESTS", 2):
            block = _manifests.dependencies_block(tmp_path, collect_files(tmp_path))
        assert len(block["files"]) == 2
        assert block["truncated"] is True

    def test_collect_scan_carries_the_block_and_it_validates(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, "pyproject.toml", _PYPROJECT)
        files = collect_files(tmp_path)
        scan = _collect.collect_scan(str(tmp_path), files, SampleRecord(), None)
        assert scan["dependencies"]["files"]["pyproject.toml"]["fastapi"] == ">=0.100"
        assert validate_code_review(review_envelope(scan=scan)) == []
        scan["dependencies"]["files"]["pyproject.toml"]["fastapi"] = 1
        assert validate_code_review(review_envelope(scan=scan))

    def test_empty_tree_has_an_empty_block(self, tmp_path: pathlib.Path) -> None:
        scan = _collect.collect_scan(str(tmp_path), [], SampleRecord(), None)
        assert scan["dependencies"] == {"files": {}, "truncated": False}
