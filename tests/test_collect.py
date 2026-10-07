"""CodeScanner v2 step 1b: the code-owned ``scan`` layer.

Covers ``code_scanner._collect`` — the ``inventory``, ``coverage`` and ``git``
collectors and their assembly — plus the two seams that carry the result:
the ``SampleRecord`` that ``gather_project_context`` fills, and the
``code_scanner_scan`` stash between the walk and the commit (D-SC1b-1).

The ``git`` block's tests patch ``_collect._run_git`` by name (AGENTS.md: the
module-level seam, not ``subprocess.run``); one integration test runs real
``git`` on a throwaway repository and is skipped where the binary is absent.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
from typing import Any
from unittest.mock import patch

import pytest

from spec4 import session as session_mod
from spec4.agents import code_scanner
from spec4.agents._code_review_schema import validate_code_review
from spec4.agents.code_scanner import _collect
from spec4.agents.code_scanner._scan import (
    SampleRecord,
    collect_files,
    gather_project_context,
)
from spec4.app_constants import STATE_REVIEW_COMPLETE
from spec4.callbacks._nav import on_rescan_project
from tests._agent_helpers import collect, make_session
from tests._review_helpers import review_block_text, review_envelope

_GIT = shutil.which("git")


def _make_project(root: pathlib.Path) -> None:
    (root / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    (root / "README.md").write_text("# X\n\nA thing.\n")
    (root / "Dockerfile").write_text("FROM python:3.12\n")
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("print('hi')\nprint('there')\n")
    (root / "src" / "util.py").write_text("x = 1")  # no trailing newline
    (root / "src" / "empty.py").write_text("")
    (root / "src" / "logo.png").write_bytes(b"\x89PNG\0\0\0binary")
    (root / "tests").mkdir()
    (root / "tests" / "test_main.py").write_text("def test_x():\n    pass\n")
    for skipped in ("node_modules/dep", "src/__pycache__", "web/node_modules"):
        d = root / skipped
        d.mkdir(parents=True)
        (d / "index.js").write_text("module.exports = {}\n")


def _scan(root: pathlib.Path) -> dict[str, Any]:
    files = collect_files(root)
    record = SampleRecord()
    gather_project_context(str(root), files, record)
    return _collect.collect_scan(str(root), files, record, None)


# ---------------------------------------------------------------------------
# inventory
# ---------------------------------------------------------------------------


class TestInventory:
    def test_census_counts_every_walked_file_by_extension(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_project(tmp_path)
        inv = _scan(tmp_path)["inventory"]
        assert inv["files_total"] == 9
        assert inv["by_extension"][".py"] == {"files": 4, "loc": 5, "unmeasured": 0}
        assert inv["by_extension"][".png"] == {"files": 1, "loc": 0, "unmeasured": 1}
        assert inv["by_extension"]["(none)"]["files"] == 1  # Dockerfile
        assert inv["loc_total"] == sum(e["loc"] for e in inv["by_extension"].values())

    def test_line_count_handles_missing_trailing_newline_and_empty_files(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / "a.txt").write_text("one\ntwo\n")
        (tmp_path / "b.txt").write_text("one\ntwo")
        (tmp_path / "c.txt").write_text("")
        assert _collect._measure_lines(tmp_path / "a.txt") == 2
        assert _collect._measure_lines(tmp_path / "b.txt") == 2
        assert _collect._measure_lines(tmp_path / "c.txt") == 0

    def test_binary_oversized_and_unreadable_files_are_unmeasured(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / "bin.dat").write_bytes(b"abc\0def\n")
        (tmp_path / "big.txt").write_text("x\n" * 10)
        assert _collect._measure_lines(tmp_path / "bin.dat") is None
        with patch.object(_collect, "_MAX_LOC_FILE_BYTES", 5):
            assert _collect._measure_lines(tmp_path / "big.txt") is None
        assert _collect._measure_lines(tmp_path / "missing.txt") is None

    def test_listed_paths_are_capped_and_the_cap_is_declared(
        self, tmp_path: pathlib.Path
    ) -> None:
        for i in range(5):
            (tmp_path / f"f{i}.py").write_text("\n")
        with patch.object(_collect, "_MAX_LISTED", 3):
            inv = _scan(tmp_path)["inventory"]
        assert inv["files_total"] == 5
        assert inv["files_listed"] == 3
        assert inv["listed"] == ["f0.py", "f1.py", "f2.py"]
        assert inv["truncated"] is True

    def test_small_tree_is_not_truncated(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / "a.py").write_text("\n")
        inv = _scan(tmp_path)["inventory"]
        assert inv["listed"] == ["a.py"]
        assert inv["truncated"] is False

    def test_unscanned_dirs_records_every_pruned_directory(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_project(tmp_path)
        inv = _scan(tmp_path)["inventory"]
        assert inv["unscanned_dirs"] == [
            "node_modules",
            "src/__pycache__",
            "web/node_modules",
        ]
        # Pruned means not descended: nothing beneath a skipped dir is listed.
        assert not any(p.startswith("node_modules/") for p in inv["listed"])
        assert "src/main.py" in inv["listed"]


# ---------------------------------------------------------------------------
# coverage — the formatters' own ledger
# ---------------------------------------------------------------------------


class TestCoverage:
    def test_record_names_what_the_seed_pasted(self, tmp_path: pathlib.Path) -> None:
        _make_project(tmp_path)
        cov = _scan(tmp_path)["coverage"]
        assert cov["readme"] == "README.md"
        assert cov["manifests"] == ["pyproject.toml"]
        assert cov["ci"] == [".github/workflows/ci.yml"]
        assert cov["deploy"] == ["Dockerfile"]
        # Non-test sources, entrypoint candidates first; the test file is
        # never sampled.
        assert cov["sampled"][0] == "src/main.py"
        assert "tests/test_main.py" not in cov["sampled"]
        assert cov["source_files_total"] == 4
        assert cov["source_files_sampled"] == len(cov["sampled"])
        assert cov["tree_listed"] == 9
        assert cov["tree_truncated"] is False

    def test_record_is_optional_and_the_text_is_unchanged(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_project(tmp_path)
        files = collect_files(tmp_path)
        record = SampleRecord()
        with_record = gather_project_context(str(tmp_path), files, record)
        without = gather_project_context(str(tmp_path), files)
        assert with_record == without
        assert record.sampled

    def test_empty_directory_leaves_the_record_blank(
        self, tmp_path: pathlib.Path
    ) -> None:
        cov = _scan(tmp_path)["coverage"]
        assert cov["readme"] is None
        assert cov["sampled"] == []
        assert cov["source_files_total"] == 0


# ---------------------------------------------------------------------------
# git — behind the one seam
# ---------------------------------------------------------------------------

_LOG_SINCE = (
    "\x1e"
    "aaa\x1fA. Developer\x1f2026-10-04T16:40:11-07:00\x1f"
    "Co-Authored-By: Claude <noreply@anthropic.com>\n\x1f\n"
    "src/app/main.py\ntests/test_main.py\n"
    "\x1e"
    "bbb\x1fB. Reviewer\x1f2026-10-01T09:00:00-07:00\x1f\x1f\n"
    "README.md\nsrc/app/cli.py\n"
)
_LOG_ALL = _LOG_SINCE + (
    "\x1e"
    "ccc\x1fA. Developer\x1f2026-07-02T09:01:44-07:00\x1f\x1f\n"
    "web/index.ts\nsrc/old.py\n"
)


def _canned(status: str = " M src/app/main.py\n?? notes.txt\n?? tmp/\n") -> Any:
    def _run(args: list[str], cwd: pathlib.Path) -> str | None:
        if args[:2] == ["rev-parse", "--short"]:
            return "9f3c2ab\n"
        if args[:2] == ["rev-parse", "--abbrev-ref"]:
            return "main\n"
        if args[0] == "status":
            return status
        if args[0] == "log":
            return (
                _LOG_SINCE if any(a.startswith("--since=") for a in args) else _LOG_ALL
            )
        return None

    return _run


class TestGitBlock:
    def test_repo_root_is_a_dot_git_directory_or_gitfile(
        self, tmp_path: pathlib.Path
    ) -> None:
        assert _collect.is_repo_root(tmp_path) is False
        (tmp_path / ".git").mkdir()
        assert _collect.is_repo_root(tmp_path) is True
        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git").write_text("gitdir: ../.git/worktrees/wt\n")
        assert _collect.is_repo_root(worktree) is True

    def test_no_git_block_outside_a_repository_root(
        self, tmp_path: pathlib.Path
    ) -> None:
        # D-SC1b-5: a subdirectory of a repository is not a repository root.
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "pkg"
        sub.mkdir()
        (sub / "a.py").write_text("\n")
        with patch.object(_collect, "_run_git", _canned()):
            assert "git" not in _scan(sub)
            assert "git" in _scan(tmp_path)

    def test_block_fields_from_the_porcelain_outputs(
        self, tmp_path: pathlib.Path
    ) -> None:
        with patch.object(_collect, "_run_git", _canned()):
            git = _collect.git_block(tmp_path, ("implemented", 1_759_000_000.0))
        assert git["available"] is True
        assert git["head"] == "9f3c2ab"
        assert git["branch"] == "main"
        assert git["dirty"] is True
        assert git["untracked_count"] == 2
        since = git["since_last_round"]
        assert since["boundary_kind"] == "implemented"
        assert since["boundary"] == "2025-09-27T19:06:40+00:00"
        assert since["commits"] == 2
        assert since["truncated"] is False
        assert since["first"] == "2026-10-01T09:00:00-07:00"
        assert since["last"] == "2026-10-04T16:40:11-07:00"
        assert since["authors"] == ["A. Developer", "B. Reviewer"]
        assert since["touched_top_dirs"] == {".": 1, "src": 2, "tests": 1}
        assert since["agent_trailers_present"] is True

    def test_activity_keeps_the_newest_commit_per_top_dir(
        self, tmp_path: pathlib.Path
    ) -> None:
        with patch.object(_collect, "_run_git", _canned()):
            git = _collect.git_block(tmp_path, None)
        assert "since_last_round" not in git
        activity = git["activity"]
        assert activity["commits_scanned"] == 3
        assert activity["truncated"] is False
        assert activity["last_commit_per_top_dir"] == {
            ".": "2026-10-01T09:00:00-07:00",
            "src": "2026-10-04T16:40:11-07:00",
            "tests": "2026-10-04T16:40:11-07:00",
            "web": "2026-07-02T09:01:44-07:00",
        }

    def test_clean_tree_and_no_agent_trailers(self, tmp_path: pathlib.Path) -> None:
        with (
            patch.object(_collect, "_run_git", _canned(status="")),
            patch.object(_collect, "_AGENT_TRAILER_RE", _collect.re.compile("zzz")),
        ):
            git = _collect.git_block(tmp_path, ("prior_review", 0.0))
        assert git["dirty"] is False
        assert git["untracked_count"] == 0
        assert git["since_last_round"]["agent_trailers_present"] is False

    def test_log_cap_is_reported_as_truncation(self, tmp_path: pathlib.Path) -> None:
        with (
            patch.object(_collect, "_run_git", _canned()),
            patch.object(_collect, "_MAX_LOG_COMMITS", 2),
        ):
            git = _collect.git_block(tmp_path, ("implemented", 0.0))
        assert git["activity"]["truncated"] is True
        assert git["since_last_round"]["truncated"] is True

    @pytest.mark.parametrize("failing", ["rev-parse", "status", "log"])
    def test_any_failed_probe_marks_git_unavailable(
        self, tmp_path: pathlib.Path, failing: str
    ) -> None:
        canned = _canned()

        def _run(args: list[str], cwd: pathlib.Path) -> str | None:
            return None if args[0] == failing else canned(args, cwd)

        with patch.object(_collect, "_run_git", _run):
            assert _collect.git_block(tmp_path, None) == {"available": False}

    def test_failed_since_log_drops_only_that_block(
        self, tmp_path: pathlib.Path
    ) -> None:
        canned = _canned()

        def _run(args: list[str], cwd: pathlib.Path) -> str | None:
            if args[0] == "log" and any(a.startswith("--since=") for a in args):
                return None
            return canned(args, cwd)

        with patch.object(_collect, "_run_git", _run):
            git = _collect.git_block(tmp_path, ("implemented", 0.0))
        assert git["available"] is True
        assert "since_last_round" not in git
        assert git["activity"]["commits_scanned"] == 3

    def test_parse_log_skips_malformed_records(self) -> None:
        commits = _collect._parse_log("\x1egarbage\x1e" + _LOG_SINCE)
        assert [c["sha"] for c in commits] == ["aaa", "bbb"]
        assert commits[0]["files"] == ["src/app/main.py", "tests/test_main.py"]

    def test_top_dir_of_a_root_file_is_dot(self) -> None:
        assert _collect._top_dir("README.md") == "."
        assert _collect._top_dir("src/app/main.py") == "src"


class TestRunGit:
    @pytest.mark.skipif(_GIT is None, reason="git not installed")
    def test_failure_is_none_not_an_exception(self, tmp_path: pathlib.Path) -> None:
        # A directory that is not a repository: non-zero exit → None.
        assert _collect._run_git(["rev-parse", "HEAD"], tmp_path) is None

    def test_missing_binary_is_none(self, tmp_path: pathlib.Path) -> None:
        with patch.object(
            _collect.subprocess, "run", side_effect=FileNotFoundError("git")
        ):
            assert _collect._run_git(["status"], tmp_path) is None

    def test_timeout_is_none(self, tmp_path: pathlib.Path) -> None:
        with patch.object(
            _collect.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=1),
        ):
            assert _collect._run_git(["status"], tmp_path) is None

    @pytest.mark.skipif(_GIT is None, reason="git not installed")
    def test_throwaway_repository_end_to_end(self, tmp_path: pathlib.Path) -> None:
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Test Author",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "Test Author",
            "GIT_COMMITTER_EMAIL": "t@example.com",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }

        def git(*args: str) -> None:
            subprocess.run(
                ["git", *args], cwd=tmp_path, env=env, check=True, capture_output=True
            )

        git("init", "-q", "-b", "main")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("x = 1\n")
        git("add", ".")
        git("commit", "-q", "-m", "first")
        (tmp_path / "src" / "b.py").write_text("y = 2\n")
        git("add", ".")
        git(
            "commit",
            "-q",
            "-m",
            "second\n\nCo-Authored-By: Claude <noreply@anthropic.com>",
        )
        (tmp_path / "untracked.txt").write_text("\n")

        git_block = _collect.git_block(tmp_path, ("prior_review", 0.0))
        assert git_block["available"] is True
        assert git_block["branch"] == "main"
        assert len(git_block["head"]) >= 7
        assert git_block["dirty"] is False
        assert git_block["untracked_count"] == 1
        assert git_block["activity"]["last_commit_per_top_dir"].keys() == {"src"}
        since = git_block["since_last_round"]
        assert since["commits"] == 2
        assert since["authors"] == ["Test Author"]
        assert since["touched_top_dirs"] == {"src": 2}
        assert since["agent_trailers_present"] is True


# ---------------------------------------------------------------------------
# round boundary
# ---------------------------------------------------------------------------


class TestRoundBoundary:
    def test_implemented_marker_wins(self, tmp_path: pathlib.Path) -> None:
        v1 = tmp_path / ".spec4" / "v1"
        v1.mkdir(parents=True)
        (v1 / "IMPLEMENTED").write_text("")
        (v1 / "code_review.json").write_text("{}")
        v2 = tmp_path / ".spec4" / "v2"
        v2.mkdir()
        (v2 / "code_review.json").write_text("{}")
        os.utime(v1 / "IMPLEMENTED", (1_700_000_000, 1_700_000_000))
        os.utime(v2 / "code_review.json", (1_800_000_000, 1_800_000_000))
        assert _collect.round_boundary(str(tmp_path), None) == (
            "implemented",
            1_700_000_000.0,
        )

    def test_prior_review_when_nothing_implemented(
        self, tmp_path: pathlib.Path
    ) -> None:
        v1 = tmp_path / ".spec4" / "v1"
        v1.mkdir(parents=True)
        (v1 / "code_review.json").write_text("{}")
        os.utime(v1 / "code_review.json", (1_750_000_000, 1_750_000_000))
        assert _collect.round_boundary(str(tmp_path), None) == (
            "prior_review",
            1_750_000_000.0,
        )

    def test_first_scan_has_no_boundary(self, tmp_path: pathlib.Path) -> None:
        assert _collect.round_boundary(str(tmp_path), None) is None


# ---------------------------------------------------------------------------
# schema and assembly
# ---------------------------------------------------------------------------


class TestScanSchema:
    def test_a_collected_scan_validates_in_the_envelope(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_project(tmp_path)
        (tmp_path / ".git").mkdir()
        with patch.object(_collect, "_run_git", _canned()):
            scan = _scan(tmp_path)
        assert set(scan) == {"inventory", "coverage", "git"}
        assert validate_code_review(review_envelope(scan=scan)) == []
        json.dumps(scan)  # the stash and the artifact are both JSON

    def test_unavailable_git_validates(self) -> None:
        scan = {"git": {"available": False}}
        assert validate_code_review(review_envelope(scan=scan)) == []

    def test_an_unknown_key_in_a_block_is_a_code_fault(self) -> None:
        # D-SC1b-9: blocks are closed, so a collector drifting from the schema
        # is caught at commit rather than stored.
        scan = {"coverage": {"readme": None, "extra": 1}}
        errors = validate_code_review(review_envelope(scan=scan))
        assert errors
        assert any("extra" in e or "required" in e for e in errors)

    def test_empty_scan_still_validates(self) -> None:
        assert validate_code_review(review_envelope(scan={})) == []


# ---------------------------------------------------------------------------
# the stash between walk and commit (D-SC1b-1)
# ---------------------------------------------------------------------------


def _fake_stream(text: str) -> Any:
    def _stream(*args: Any, **kwargs: Any) -> Any:
        args[1].append({"role": "assistant", "content": text})
        yield text

    return _stream


class TestScanStash:
    def test_default_session_carries_an_empty_stash(self) -> None:
        assert session_mod.default_session()["code_scanner_scan"] is None

    def test_rescan_clears_the_stash(self) -> None:
        session = {"code_scanner_scan": {"inventory": {}}, "messages": ["x"]}
        assert on_rescan_project(1, session)["code_scanner_scan"] is None

    def test_walk_stashes_and_commit_merges_then_clears(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_project(tmp_path)
        session = make_session(active_agent="code_scanner", working_dir=str(tmp_path))
        with patch.object(
            code_scanner.llm, "stream_turn", _fake_stream(review_block_text())
        ):
            collect(code_scanner.run(None, session, {"model": "m"}))
        assert session["code_scanner_state"] == STATE_REVIEW_COMPLETE
        stored = session["code_review"]["code_review"]["scan"]
        assert stored["inventory"]["files_total"] == 9
        assert stored["coverage"]["readme"] == "README.md"
        assert "git" not in stored
        assert session["code_scanner_scan"] is None

    def test_stash_survives_a_conversational_turn(self, tmp_path: pathlib.Path) -> None:
        # The model may talk before it emits the block; the walk's scan waits.
        _make_project(tmp_path)
        session = make_session(active_agent="code_scanner", working_dir=str(tmp_path))
        with patch.object(code_scanner.llm, "stream_turn", _fake_stream("Hello.")):
            collect(code_scanner.run(None, session, {"model": "m"}))
        assert session["code_scanner_scan"]["inventory"]["files_total"] == 9
        with patch.object(
            code_scanner.llm, "stream_turn", _fake_stream(review_block_text())
        ):
            collect(code_scanner.run("go on", session, {"model": "m"}))
        assert (
            session["code_review"]["code_review"]["scan"]["inventory"]["files_total"]
            == 9
        )
        assert session["code_scanner_scan"] is None

    def test_commit_without_a_stash_is_refused(self) -> None:
        session = make_session(
            code_scanner_messages=[{"role": "assistant", "content": ""}]
        )
        assert session.get("code_scanner_scan") is None
        with pytest.raises(ValueError, match="no scan stashed"):
            code_scanner._scanner_commit(
                session, session["code_scanner_messages"], {"review": {}}
            )
        assert session["code_review"] is None
        assert session["code_scanner_state"] != STATE_REVIEW_COMPLETE
