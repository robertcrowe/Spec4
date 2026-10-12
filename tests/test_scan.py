"""The fixed-evidence formatters in ``code_scanner._scan`` (v2 step 2a).

The file tree's two-part form (D-SC2-3), the Project Conventions block
(D-SC2-10) and the deployment-signal additions (D-SC2-11). Which source files
the seed shows is ``_sample``'s and is tested in ``tests/test_sample.py``.
"""

from __future__ import annotations

import pathlib
from unittest.mock import patch

from spec4.agents.code_scanner import _scan
from spec4.agents.code_scanner._scan import (
    SampleRecord,
    approx_tokens,
    collect_files,
    file_tree_lines,
    format_conventions_block,
    format_deployment_signals,
)


def _write(root: pathlib.Path, rel: str, text: str = "x\n") -> pathlib.Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


# ---------------------------------------------------------------------------
# file tree
# ---------------------------------------------------------------------------


class TestFileTree:
    def test_rollup_names_every_directory_with_counts_and_top_extensions(
        self, tmp_path: pathlib.Path
    ) -> None:
        for rel in ("README.md", "a.py", "src/b.py", "src/c.py", "src/d.ts"):
            _write(tmp_path, rel)
        for i in range(3):
            _write(tmp_path, f"docs/n{i}.md")
        _write(tmp_path, "docs/x.txt")
        _write(tmp_path, "docs/y.rst")
        _write(tmp_path, "docs/Makefile")
        lines: list[str] = []
        record = SampleRecord()
        file_tree_lines(
            tmp_path, collect_files(tmp_path), ["a.py", "src/b.py"], lines, record
        )
        text = "\n".join(lines)
        # The root first, then by path; the top three extensions by count,
        # an extensionless file counted under its own name.
        assert "./  2  (.md 1, .py 1)" in text
        assert "docs/  6  (.md 3, .rst 1, .txt 1)" in text
        assert "src/  3  (.py 2, .ts 1)" in text
        assert text.index("./  2") < text.index("docs/  6") < text.index("src/  3")
        assert "Makefile" not in text  # fourth-ranked in docs/, so not named

    def test_node_list_names_the_given_nodes_and_caps_with_a_more_line(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, "a.py")
        nodes = [f"m{i}.py" for i in range(5)]
        lines: list[str] = []
        record = SampleRecord()
        with patch.object(_scan, "_MAX_TREE_NODES", 3):
            file_tree_lines(tmp_path, collect_files(tmp_path), nodes, lines, record)
        text = "\n".join(lines)
        assert "Source files (non-test, 5):" in text
        assert "m2.py" in text
        assert "m3.py" not in text
        assert "(+2 more)" in text
        assert (record.tree_form, record.tree_listed, record.tree_truncated) == (
            "rollup+nodes",
            3,
            True,
        )

    def test_uncapped_node_list_is_not_truncated(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "a.py")
        lines: list[str] = []
        record = SampleRecord()
        file_tree_lines(tmp_path, collect_files(tmp_path), ["a.py"], lines, record)
        assert "(+" not in "\n".join(lines)
        assert record.tree_listed == 1
        assert record.tree_truncated is False


# ---------------------------------------------------------------------------
# Project Conventions
# ---------------------------------------------------------------------------


class TestConventions:
    def test_env_example_whole_docs_by_head_legal_by_name(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, ".env.example", "DATABASE_URL=\nAPI_KEY=\n")
        _write(tmp_path, "AGENTS.md", "".join(f"rule {i}\n" for i in range(100)))
        _write(tmp_path, "CLAUDE.md", "@AGENTS.md\n")
        _write(tmp_path, "LICENSE", "MIT\n")
        _write(tmp_path, "CLA.md", "sign here\n")
        record = SampleRecord()
        out = "\n".join(
            format_conventions_block(tmp_path, collect_files(tmp_path), record)
        )
        assert out.startswith("### Project Conventions")
        assert "DATABASE_URL=" in out
        assert "#### `AGENTS.md` (first 80 lines)" in out
        assert "rule 79" in out
        assert "rule 80" not in out
        assert "- Also present: `CLA.md`, `LICENSE`" in out
        assert "sign here" not in out  # named, never pasted
        assert record.conventions == [".env.example", "CLAUDE.md", "AGENTS.md"]

    def test_env_example_is_capped(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, ".env.sample", "A=" + "x" * 2000 + "\n")
        record = SampleRecord()
        out = "\n".join(
            format_conventions_block(tmp_path, collect_files(tmp_path), record)
        )
        assert "x" * _scan._MAX_ENV_EXAMPLE_CHARS not in out
        assert "x" * (_scan._MAX_ENV_EXAMPLE_CHARS - 10) in out
        assert record.conventions == [".env.sample"]

    def test_only_root_level_files_count(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "pkg/AGENTS.md", "nested\n")
        _write(tmp_path, "pkg/.env.template", "NESTED=\n")
        _write(tmp_path, "CONTRIBUTING.md", "be kind\n")
        record = SampleRecord()
        out = "\n".join(
            format_conventions_block(tmp_path, collect_files(tmp_path), record)
        )
        assert "be kind" in out
        assert "nested" not in out
        assert "NESTED" not in out
        assert record.conventions == ["CONTRIBUTING.md"]

    def test_unreadable_files_are_skipped(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, ".env.example", "A=\n")
        _write(tmp_path, "AGENTS.md", "x\n")
        record = SampleRecord()
        with patch.object(_scan, "_read_text_safely", return_value=None):
            out = format_conventions_block(tmp_path, collect_files(tmp_path), record)
        assert out == []
        assert record.conventions == []

    def test_absent_when_nothing_is_present(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "main.py")
        record = SampleRecord()
        assert format_conventions_block(tmp_path, collect_files(tmp_path), record) == []
        assert record.conventions == []


# ---------------------------------------------------------------------------
# deployment signals
# ---------------------------------------------------------------------------


class TestDeploySignals:
    def test_caddyfile_deploy_script_nginx_and_systemd_units_are_signals(
        self, tmp_path: pathlib.Path
    ) -> None:
        for rel in (
            "deploy/Caddyfile",
            "deploy/bws4-api.service",
            "deploy/deploy.sh",
            "deploy/nginx.conf",
            "deploy/README.md",
            "deploy/ACCEPTANCE.md",
        ):
            _write(tmp_path, rel, f"{rel}\n")
        record = SampleRecord()
        out = "\n".join(
            format_deployment_signals(tmp_path, collect_files(tmp_path), record)
        )
        assert record.deploy == [
            "deploy/Caddyfile",
            "deploy/bws4-api.service",
            "deploy/deploy.sh",
            "deploy/nginx.conf",
        ]
        assert "ACCEPTANCE" not in out
        assert "deploy/README.md" not in out

    def test_cap_stays_at_five_files(self, tmp_path: pathlib.Path) -> None:
        for i in range(7):
            _write(tmp_path, f"units/s{i}.service")
        record = SampleRecord()
        format_deployment_signals(tmp_path, collect_files(tmp_path), record)
        assert len(record.deploy) == 5


def test_approx_tokens_is_four_characters_per_token() -> None:
    assert approx_tokens("x" * 4_001) == 1_000
    assert approx_tokens("") == 0
