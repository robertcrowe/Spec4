"""The step-2a sampler, ``code_scanner._sample`` (D-SC2-1…13).

Tier order and budgets with rollover (D-SC2-5), reach ranking (D-SC2-4),
whole-or-headed bodies (D-SC2-7), compact signatures (D-SC2-8), thin
``__init__.py`` demotion (D-SC2-9), the budget override (D-SC2-2) and the
record the coverage block is built from (D-SC2-13), on fixture trees.
"""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Any
from unittest.mock import patch

import pytest

from spec4.agents.code_scanner import _collect, _sample
from spec4.agents.code_scanner._sample import (
    ScanEvidence,
    evidence_budget,
    gather_project_context,
    local_evidence,
    render_signatures,
)
from spec4.agents.code_scanner._scan import (
    EVIDENCE_TOKEN_BUDGET,
    SampleRecord,
    approx_tokens,
    collect_files,
)


def _write(root: pathlib.Path, rel: str, text: str = "") -> pathlib.Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _module(name: str, n_funcs: int = 2, extra_lines: int = 0) -> str:
    """A small module with ``n_funcs`` public functions and padding lines."""
    body = [f'"""The {name} module."""', ""]
    for i in range(n_funcs):
        body += [
            f"def {name}_f{i}(x: int) -> int:",
            f'    """Doc {i}."""',
            "    return x",
            "",
        ]
    body += [f"# pad {i}" for i in range(extra_lines)]
    return "\n".join(body) + "\n"


def _product(root: pathlib.Path) -> None:
    """``app.py`` reaching a package; tooling beside it that nothing reaches."""
    _write(root, "README.md", "# Demo\n")
    _write(root, "pyproject.toml", "[project]\nname = 'demo'\n")
    _write(
        root,
        "src/demo/app.py",
        "from demo import core, models, util\nfrom demo.api import views\n"
        + _module("app"),
    )
    _write(root, "src/demo/__init__.py", "")
    for name in ("core", "util"):
        _write(root, f"src/demo/{name}.py", "from demo import models\n" + _module(name))
    _write(root, "src/demo/models.py", _module("models"))
    _write(
        root,
        "src/demo/api/routes.py",
        "from demo import core, util\n" + _module("routes"),
    )
    _write(
        root,
        "src/demo/api/views.py",
        "from demo.api import routes\n" + _module("views"),
    )
    # Unreached tooling with a higher fan-in than anything in the product.
    _write(root, "evals/_load.py", _module("load"))
    for i in range(5):
        _write(root, f"evals/e{i}.py", "from evals import _load\n")
    _write(root, "tests/test_core.py", "from demo import core\n")


def _context(
    root: pathlib.Path, *, budget: int | None = None
) -> tuple[str, SampleRecord]:
    files = collect_files(root)
    evidence = _collect.measure_scan(str(root), files, None)
    if budget is not None:
        evidence = dataclasses.replace(evidence, budget_tokens=budget)
    record = SampleRecord()
    return gather_project_context(str(root), files, record, evidence), record


def _touched(
    evidence: ScanEvidence, most_touched: list[tuple[str, int]]
) -> ScanEvidence:
    """``evidence`` with a git block whose ``since_last_round`` carries the list."""
    since = {"most_touched": [{"path": p, "commits": n} for p, n in most_touched]}
    git = {"available": True, "since_last_round": since}
    return dataclasses.replace(evidence, scan={**evidence.scan, "git": git})


def _context_touched(
    root: pathlib.Path,
    most_touched: list[tuple[str, int]],
    *,
    budget: int | None = None,
) -> tuple[str, SampleRecord]:
    files = collect_files(root)
    evidence = _touched(_collect.measure_scan(str(root), files, None), most_touched)
    if budget is not None:
        evidence = dataclasses.replace(evidence, budget_tokens=budget)
    record = SampleRecord()
    return gather_project_context(str(root), files, record, evidence), record


# ---------------------------------------------------------------------------
# tiers and reach
# ---------------------------------------------------------------------------


class TestTiers:
    def test_tiers_appear_in_order_and_the_record_matches_the_text(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        text, record = _context(tmp_path)
        order = [
            "### File Tree",
            "### README Excerpt",
            "### Config and Manifest Files",
            "### Key Module Signatures",
            "### Source File Samples",
            "### Other Package Signatures",
        ]
        positions = [text.index(h) for h in order]
        assert positions == sorted(positions)
        for path in record.sampled + record.signatures_shown:
            assert f"`{path}`" in text
        assert record.evidence_tokens == approx_tokens(text)

    def test_entrypoint_body_comes_first_then_top_fan_in_reached_first(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        _, record = _context(tmp_path)
        # app.py is the entrypoint; models (fan-in 3), core and util (2) are
        # the reached candidates. evals/_load.py has fan-in 5 but is
        # unreached, so it ranks after them and misses the top three.
        assert record.sampled == [
            "src/demo/app.py",
            "src/demo/models.py",
            "src/demo/core.py",
            "src/demo/util.py",
        ]
        assert "evals/_load.py" not in record.sampled

    def test_an_unreached_candidate_fills_a_top_slot_reached_ones_leave(
        self, tmp_path: pathlib.Path
    ) -> None:
        # Reach demotes, it does not exclude (D-SC2-4 (a)): with one reached
        # candidate, the next top-fan-in slot goes to the unreached one.
        _write(tmp_path, "main.py", "import core\n")
        _write(tmp_path, "core.py", "")
        _write(tmp_path, "side.py", "import core\n")
        _write(tmp_path, "tools/_load.py", "")
        for i in range(3):
            _write(tmp_path, f"tools/t{i}.py", "from tools import _load\n")
        _, record = _context(tmp_path)
        assert record.sampled == ["main.py", "core.py", "tools/_load.py"]

    def test_unreached_candidates_rank_last_in_the_signature_tier(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        _, record = _context(tmp_path)
        shown = record.signatures_shown
        assert "evals/_load.py" in shown
        assert shown.index("src/demo/models.py") < shown.index("evals/_load.py")
        assert shown.index("src/demo/app.py") < shown.index("evals/_load.py")

    def test_breadth_tier_takes_one_member_of_each_untouched_package(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        text, record = _context(tmp_path)
        # src/demo/api is the one reached package no B or C file sits in;
        # routes.py and views.py tie at fan-in 1; the path breaks the tie.
        d_part = text[text.index("### Other Package Signatures") :]
        assert "`src/demo/api/routes.py` (package `src/demo/api/`, fan-in 1)" in d_part
        assert "src/demo/api/views.py" not in d_part
        # src/demo/ and evals/ already have B/C files: no D block for them.
        assert "(package `src/demo/`" not in d_part
        assert "(package `evals/`" not in d_part
        assert "src/demo/api/routes.py" in record.signatures_shown

    def test_thin_init_never_takes_a_slot_but_a_real_one_does(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, "main.py", "import thin\nimport fat\nimport leaf\n")
        _write(tmp_path, "thin/__init__.py", "from thin.x import y\n")
        _write(tmp_path, "thin/x.py", "")
        _write(tmp_path, "fat/__init__.py", _module("fat", n_funcs=8))
        _write(tmp_path, "leaf.py", "import thin\nimport fat\n")
        _, record = _context(tmp_path)
        everything = record.sampled + record.signatures_shown
        assert "thin/__init__.py" not in everything
        assert "fat/__init__.py" in everything

    def test_unknown_reach_keeps_the_given_order(self, tmp_path: pathlib.Path) -> None:
        # No entrypoint, no manifest: reach is unknown and nothing is demoted.
        _write(tmp_path, "lib/base.py", _module("base"))
        _write(tmp_path, "lib/a.py", "from lib import base\n")
        _write(tmp_path, "lib/b.py", "from lib import base\n")
        _write(tmp_path, "other/c.py", _module("c"))
        _, record = _context(tmp_path)
        assert record.sampled == ["lib/base.py"]
        assert "other/c.py" in record.signatures_shown


# ---------------------------------------------------------------------------
# tier C's third group: the most-touched files (2b, D-SC2-6)
# ---------------------------------------------------------------------------


class TestMostTouched:
    def test_most_touched_follow_the_top_fan_in_in_git_order_reached_first(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        _write(tmp_path, "docs/notes.md", "# notes\n")
        _, record = _context_touched(
            tmp_path,
            [
                ("evals/e1.py", 5),  # a node, unreached: last of the group
                ("src/demo/api/views.py", 4),
                ("src/demo/__init__.py", 3),  # thin: never a slot
                ("src/demo/core.py", 3),  # already a top-fan-in body
                ("docs/notes.md", 2),  # not a graph node
                ("src/demo/api/routes.py", 1),
            ],
        )
        assert record.sampled == [
            "src/demo/app.py",
            "src/demo/models.py",
            "src/demo/core.py",
            "src/demo/util.py",
            "src/demo/api/views.py",
            "src/demo/api/routes.py",
            "evals/e1.py",
        ]
        assert record.sampled.count("src/demo/core.py") == 1

    def test_git_order_is_kept_within_the_reached_half(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        _, by_commits = _context_touched(
            tmp_path, [("src/demo/api/routes.py", 9), ("src/demo/api/views.py", 8)]
        )
        _, reversed_ = _context_touched(
            tmp_path, [("src/demo/api/views.py", 9), ("src/demo/api/routes.py", 8)]
        )
        assert by_commits.sampled[-2:] == [
            "src/demo/api/routes.py",
            "src/demo/api/views.py",
        ]
        assert reversed_.sampled[-2:] == [
            "src/demo/api/views.py",
            "src/demo/api/routes.py",
        ]

    def test_without_a_git_block_or_a_boundary_c_is_as_in_2a(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        _, plain = _context(tmp_path)
        files = collect_files(tmp_path)
        evidence = _collect.measure_scan(str(tmp_path), files, None)
        for git in (
            {"available": False},
            {"available": True},
            {"available": True, "since_last_round": {"commits": 0}},
            {"available": True, "since_last_round": {"most_touched": []}},
        ):
            record = SampleRecord()
            scan = {**evidence.scan, "git": git}
            gather_project_context(
                str(tmp_path), files, record, dataclasses.replace(evidence, scan=scan)
            )
            assert record.sampled == plain.sampled
        assert plain.sampled == [
            "src/demo/app.py",
            "src/demo/models.py",
            "src/demo/core.py",
            "src/demo/util.py",
        ]

    def test_headings_note_the_commits_since_the_round(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        text, _ = _context_touched(
            tmp_path,
            [
                ("src/demo/app.py", 7),
                ("src/demo/models.py", 1),
                ("src/demo/api/views.py", 2),
            ],
        )
        c_part = text[text.index("### Source File Samples") :]
        headings = {
            line.split("`")[1]: line.rpartition(" (")[2].rstrip(")")
            for line in c_part.splitlines()
            if line.startswith("#### ")
        }
        assert headings["src/demo/app.py"] == (
            "entrypoint candidate, 7 commits since last round"
        )
        assert headings["src/demo/models.py"] == "fan-in 3, 1 commit since last round"
        assert (
            headings["src/demo/api/views.py"] == "fan-in 1, 2 commits since last round"
        )
        assert headings["src/demo/core.py"] == "fan-in 2"
        # The signature tier carries the same note.
        b_part = text[
            text.index("### Key Module Signatures") : text.index(
                "### Source File Samples"
            )
        ]
        assert "`src/demo/models.py` (fan-in 3, 1 commit since last round)" in b_part

    def test_most_touched_share_the_body_budget_and_skip_what_does_not_fit(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, "main.py", "import core\n")
        _write(tmp_path, "core.py", _module("core"))
        _write(tmp_path, "u.py", "import core\n")
        _write(tmp_path, "big.py", _module("big", extra_lines=300))
        _write(tmp_path, "small.py", _module("small"))
        files = collect_files(tmp_path)
        evidence = _collect.measure_scan(str(tmp_path), files, None)
        bodies = sum(
            approx_tokens((tmp_path / f).read_text()) for f in ("main.py", "core.py")
        )
        with (
            patch.object(_sample, "_TIER_C_TOKENS", bodies + 150),
            patch.object(_sample, "_TIER_B_TOKENS", 0),
        ):
            record = SampleRecord()
            text = gather_project_context(
                str(tmp_path),
                files,
                record,
                _touched(evidence, [("big.py", 3), ("small.py", 2)]),
            )
        assert record.sampled == ["main.py", "core.py", "small.py"]
        # Neither an entrypoint nor a candidate: the churn is the whole label.
        assert (
            "#### `small.py` (whole file, 10 lines) (2 commits since last round)"
            in text
        )


# ---------------------------------------------------------------------------
# budgets
# ---------------------------------------------------------------------------


class TestBudgets:
    def test_total_stays_within_the_budget(self, tmp_path: pathlib.Path) -> None:
        _product(tmp_path)
        full, _ = _context(tmp_path)
        budget = approx_tokens(full) - 100
        text, record = _context(tmp_path, budget=budget)
        assert approx_tokens(text) <= budget
        assert record.evidence_tokens < approx_tokens(full)  # the cut bit

    def test_tier_a_alone_over_budget_leaves_no_room_for_b_c_d(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        text, record = _context(tmp_path, budget=10)
        assert record.sampled == []
        assert record.signatures_shown == []
        assert "### Key Module Signatures" not in text
        assert "### Source File Samples" in text  # header kept, nothing under it

    def test_unspent_signature_budget_rolls_into_bodies(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, "main.py", "import big\n")
        _write(tmp_path, "big.py", _module("big", extra_lines=300))
        _write(tmp_path, "user.py", "import big\n")
        big_cost = approx_tokens((tmp_path / "big.py").read_text())
        # C's own budget is too small for big.py; B's unspent share makes it fit.
        with (
            patch.object(_sample, "_TIER_C_TOKENS", big_cost // 2),
            patch.object(_sample, "_TIER_B_TOKENS", big_cost * 2),
        ):
            _, record = _context(tmp_path)
        assert "big.py" in record.sampled
        with (
            patch.object(_sample, "_TIER_C_TOKENS", big_cost // 2),
            patch.object(_sample, "_TIER_B_TOKENS", 0),
        ):
            _, starved = _context(tmp_path)
        assert "big.py" not in starved.sampled

    def test_a_block_that_does_not_fit_is_skipped_not_a_stop(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, "main.py", "import big\nimport small\n")
        _write(tmp_path, "big.py", _module("big", extra_lines=300))
        _write(tmp_path, "small.py", _module("small"))
        _write(tmp_path, "u.py", "import big\nimport small\n")
        _write(tmp_path, "v.py", "import big\n")
        with (
            patch.object(_sample, "_TIER_C_TOKENS", 400),
            patch.object(_sample, "_TIER_B_TOKENS", 0),
        ):
            _, record = _context(tmp_path)
        assert "big.py" not in record.sampled
        assert "small.py" in record.sampled

    def test_breadth_reserve_is_zero_when_nothing_is_left(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        with patch.object(_sample, "_TIER_D_TOKENS", 0):
            text, _ = _context(tmp_path)
        assert "### Other Package Signatures" not in text


# ---------------------------------------------------------------------------
# body form and signature rendering
# ---------------------------------------------------------------------------


class TestRendering:
    def test_small_file_is_whole_large_file_is_headed_with_signatures(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, "main.py", "import big\n")
        _write(tmp_path, "big.py", _module("big", extra_lines=400))
        _write(tmp_path, "u.py", "import big\n")
        with patch.object(_sample, "_WHOLE_BODY_TOKENS", 200):
            text, record = _context(tmp_path)
        assert "#### `main.py` (whole file, 1 lines) (entrypoint candidate)" in text
        assert "#### `big.py` (first 150 of 410 lines) (fan-in 2)" in text
        assert "# pad 139" in text
        assert "# pad 140" not in text
        assert "_Signatures of `big.py`:_" in text
        assert "def big_f1(x: int) -> int  # Doc 1." in text
        assert record.sampled == ["main.py", "big.py"]

    def test_an_imported_entrypoint_is_labelled_as_an_entrypoint_only(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, "main.py", _module("main"))
        _write(tmp_path, "u.py", "import main\n")
        _write(tmp_path, "v.py", "import main\n")
        text, _ = _context(tmp_path)
        assert "#### `main.py` (whole file, 10 lines) (entrypoint candidate)" in text
        assert "fan-in" not in text.split("### Source File Samples")[1]

    def test_headed_file_without_symbols_has_no_signature_trailer(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, "main.py", "".join(f"_x{i} = {i}\n" for i in range(50)))
        with (
            patch.object(_sample, "_WHOLE_BODY_TOKENS", 10),
            patch.object(_sample, "_HEAD_BODY_LINES", 5),
        ):
            text, _ = _context(tmp_path)
        assert "(first 5 of 50 lines)" in text
        assert "_Signatures of" not in text

    def test_render_signatures_compact_form(self) -> None:
        entry = {
            "language": "python",
            "doc": "Module doc.",
            "symbols": [
                {
                    "kind": "function",
                    "name": "f",
                    "signature": "def f(x)",
                    "doc": "Does f.",
                },
                {"kind": "variable", "name": "X", "signature": "X: int", "doc": None},
            ],
            "truncated": True,
        }
        assert render_signatures("m.py", entry, " (fan-in 4)") == (
            "#### `m.py` (fan-in 4)\n_Module doc._\n```\n"
            "def f(x)  # Does f.\nX: int\n# … more public symbols not shown\n```\n"
        )
        empty = {"language": "go", "doc": None, "symbols": [], "truncated": False}
        assert render_signatures("m.go", empty, "") == (
            "#### `m.go`\n```\n(no public symbols)\n```\n"
        )

    def test_signatures_fall_back_to_parsing_when_not_in_the_scan(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, "main.py", "import core\n")
        _write(tmp_path, "core.py", _module("core"))
        _write(tmp_path, "u.py", "import core\n")
        files = collect_files(tmp_path)
        evidence = _collect.measure_scan(str(tmp_path), files, None)
        evidence.scan["signatures"] = {"files": {}, "truncated": True}
        record = SampleRecord()
        text = gather_project_context(str(tmp_path), files, record, evidence)
        assert "def core_f0(x: int) -> int  # Doc 0." in text
        assert "core.py" in record.signatures_shown

    def test_unparseable_unreadable_and_symbol_less_files_are_skipped(
        self, tmp_path: pathlib.Path
    ) -> None:
        both = "import broken\nimport gone\nimport pkg.bad\nimport quiet.empty\n"
        _write(tmp_path, "main.py", both)
        _write(tmp_path, "u.py", "import broken\nimport gone\n")
        _write(tmp_path, "broken.py", "def (:\n")  # no signatures: parse fails
        _write(tmp_path, "gone.py", "x = 1\n")  # unreadable below
        _write(tmp_path, "pkg/bad.py", "class (:\n")
        _write(tmp_path, "quiet/empty.py", "# nothing public\n")
        files = collect_files(tmp_path)
        real_read = _sample._read_text_safely

        def flaky(path: pathlib.Path, limit: int) -> str | None:
            return None if path.name == "gone.py" else real_read(path, limit)

        record = SampleRecord()
        with patch.object(_sample, "_read_text_safely", side_effect=flaky):
            gather_project_context(str(tmp_path), files, record)
        # broken.py: no signature block, but its body is readable text.
        assert "broken.py" not in record.signatures_shown
        assert "broken.py" in record.sampled
        # gone.py: its signatures were parsed by the graph; its body unreadable.
        assert "gone.py" in record.signatures_shown
        assert "gone.py" not in record.sampled
        # D skips a package member with no signatures or no public symbols.
        assert "pkg/bad.py" not in record.signatures_shown
        assert "quiet/empty.py" not in record.signatures_shown
        assert record.sampled[0] == "main.py"  # paired positive


# ---------------------------------------------------------------------------
# entry points into the sampler
# ---------------------------------------------------------------------------


class TestEntry:
    def test_local_evidence_matches_the_measured_scan(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        files = collect_files(tmp_path)
        measured = gather_project_context(
            str(tmp_path), files, None, _collect.measure_scan(str(tmp_path), files)
        )
        assert gather_project_context(str(tmp_path), files) == measured
        local = local_evidence(tmp_path, files)
        assert local.reached == _collect.measure_scan(str(tmp_path), files).reached
        assert local.reached  # paired: not vacuously equal

    def test_files_come_from_the_evidence_when_not_passed(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        files = collect_files(tmp_path)
        evidence = _collect.measure_scan(str(tmp_path), files)
        with patch.object(_sample, "collect_files", side_effect=AssertionError):
            text = gather_project_context(str(tmp_path), None, None, evidence)
        assert "src/demo/app.py" in text

    def test_empty_directory_records_its_tokens(self, tmp_path: pathlib.Path) -> None:
        record = SampleRecord()
        text = gather_project_context(str(tmp_path), [], record)
        assert "empty" in text
        assert record.evidence_tokens == approx_tokens(text) > 0
        assert record.tree_form == "empty"

    @pytest.mark.parametrize(
        ("config", "expected"),
        [
            ({}, EVIDENCE_TOKEN_BUDGET),
            ({"scan_context_tokens": 9_000}, 9_000),
            ({"scan_context_tokens": 0}, EVIDENCE_TOKEN_BUDGET),
            ({"scan_context_tokens": True}, EVIDENCE_TOKEN_BUDGET),
            ({"scan_context_tokens": "9000"}, EVIDENCE_TOKEN_BUDGET),
        ],
    )
    def test_evidence_budget_override(
        self, config: dict[str, Any], expected: int
    ) -> None:
        assert evidence_budget(config) == expected

    def test_scan_evidence_defaults_to_the_constant(self) -> None:
        assert ScanEvidence([], {}, frozenset()).budget_tokens == 24_000


# ---------------------------------------------------------------------------
# step 3a: the blocks rendered from the scan (D-SC3-6/8/9)
# ---------------------------------------------------------------------------


def _with_prior(evidence: ScanEvidence, prior: dict[str, Any] | None) -> ScanEvidence:
    """``evidence`` with ``scan.prior_round`` set (or removed when ``None``)."""
    scan = {k: v for k, v in evidence.scan.items() if k != "prior_round"}
    if prior is not None:
        scan["prior_round"] = prior
    return dataclasses.replace(evidence, scan=scan)


def _prior(
    feature_ids: list[str], phases: list[tuple[int | None, list[str]]]
) -> dict[str, Any]:
    return {
        "version": 2,
        "implemented": "2026-09-08T06:00:21+00:00",
        "vision": {"name": "Demo", "feature_ids": feature_ids, "revision_count": 0},
        "phases": [
            {"number": n, "features": [{"id": f, "role": None} for f in fs]}
            for n, fs in phases
        ],
    }


def _context_prior(
    root: pathlib.Path, prior: dict[str, Any] | None
) -> tuple[str, SampleRecord]:
    files = collect_files(root)
    evidence = _with_prior(_collect.measure_scan(str(root), files, None), prior)
    record = SampleRecord()
    return gather_project_context(str(root), files, record, evidence), record


def _since(
    evidence: ScanEvidence,
    since: dict[str, Any] | None,
    delta: dict[str, Any] | None = None,
) -> ScanEvidence:
    """``evidence`` with ``git.since_last_round`` and ``delta`` set (or removed)."""
    scan = {k: v for k, v in evidence.scan.items() if k not in ("git", "delta")}
    if since is not None:
        scan["git"] = {"available": True, "since_last_round": since}
    if delta is not None:
        scan["delta"] = delta
    return dataclasses.replace(evidence, scan=scan)


def _since_block(
    commits: int = 14, most_touched: list[tuple[str, int]] | None = None
) -> dict[str, Any]:
    return {
        "boundary_kind": "implemented",
        "boundary": "2026-09-08T06:00:21+00:00",
        "commits": commits,
        "authors": ["A", "B"],
        "touched_top_dirs": {"src": 12, "tests": 9},
        "agent_trailers_present": True,
        "most_touched": [{"path": p, "commits": n} for p, n in most_touched or []],
    }


def _context_since(
    root: pathlib.Path,
    since: dict[str, Any] | None,
    delta: dict[str, Any] | None = None,
) -> tuple[str, SampleRecord]:
    files = collect_files(root)
    evidence = _since(_collect.measure_scan(str(root), files, None), since, delta)
    record = SampleRecord()
    return gather_project_context(str(root), files, record, evidence), record


def _block(text: str, head: str) -> str:
    """The tier-A block under ``head``, up to the next heading."""
    return text.split(head)[1].split("\n###")[0]


def _candidate_line(text: str) -> tuple[str, list[str]]:
    """The candidate line under Key Module Signatures and the paths it names."""
    head = text.split("### Key Module Signatures\n")[1].split("####")[0].strip()
    listed = [p.strip().strip("`") for p in head.split("): ")[1].split(", ")]
    return head, listed


class TestScanRenderedBlocks:
    def test_external_imports_block_names_importers_and_sets_the_flag(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        _write(
            tmp_path, "src/demo/search.py", "import httpx\nimport mcp\n" + _module("s")
        )
        _write(tmp_path, "src/demo/llm.py", "import httpx\n" + _module("llm"))
        text, record = _context(tmp_path)
        assert record.external_imports_shown is True
        block = text.split("### External Packages and Their Importers")[1]
        block = block.split("###")[0]
        assert "- httpx: `src/demo/llm.py`, `src/demo/search.py`" in block
        assert "- mcp: `src/demo/search.py`" in block
        assert block.index("httpx") < block.index("mcp")  # most imported first
        # Tier A closes with it: after conventions, before the signatures.
        assert text.index("### External Packages") < text.index(
            "### Key Module Signatures"
        )

    def test_external_imports_block_caps_the_modules_shown(
        self, tmp_path: pathlib.Path
    ) -> None:
        for i in range(_sample._MAX_IMPORTERS_SHOWN + 2):
            _write(tmp_path, f"m{i}.py", "import widely\n")
        text, _ = _context(tmp_path)
        assert "`m5.py` (+2 more)" in text
        assert "`m6.py`" not in text

    def test_no_external_imports_means_no_block_and_no_flag(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, "main.py", "import os\n" + _module("main"))
        text, record = _context(tmp_path)
        assert "External Packages" not in text
        assert record.external_imports_shown is False

    def test_prior_round_block_lists_ids_with_their_phases(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        prior = _prior(
            ["round_tree", "agent_rows", "unbuilt"],
            [(1, ["round_tree"]), (2, ["round_tree", "agent_rows"]), (3, ["extra"])],
        )
        text, record = _context_prior(tmp_path, prior)
        assert record.prior_round_shown is True
        block = text.split("### Prior Round (v2, implemented 2026-09-08)")[1]
        block = block.split("###")[0]
        assert "`implemented[].prior_feature_ids`" in block
        lines = [ln for ln in block.splitlines() if ln.startswith("- `")]
        assert lines == [
            "- `round_tree` — phase 1, 2",
            "- `agent_rows` — phase 2",
            "- `unbuilt` — no phase declared it",
            "- `extra` — phase 3",
        ]
        assert text.index("### Prior Round") < text.index("### Key Module Signatures")

    def test_prior_round_block_caps_and_handles_a_phase_without_a_number(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        ids = [f"f{i:02d}" for i in range(_sample._MAX_PRIOR_IDS_SHOWN + 2)]
        prior = _prior(ids, [(None, ["f00"])])
        prior["implemented"] = None
        text, _ = _context_prior(tmp_path, prior)
        assert "### Prior Round (v2)\n" in text
        assert "- `f00` — no phase declared it" in text
        assert f"- `f{_sample._MAX_PRIOR_IDS_SHOWN - 1:02d}`" in text
        assert f"- `f{_sample._MAX_PRIOR_IDS_SHOWN:02d}`" not in text
        assert "(+2 more)" in text

    def test_no_prior_round_or_no_ids_means_no_block(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        text, record = _context_prior(tmp_path, None)
        assert "Prior Round" not in text
        assert record.prior_round_shown is False
        text, record = _context_prior(tmp_path, _prior([], [(1, [])]))
        assert "Prior Round" not in text
        assert record.prior_round_shown is False

    def test_candidate_line_names_the_shown_candidates_by_fan_in(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        text, record = _context(tmp_path)
        head, listed = _candidate_line(text)
        assert head.startswith(
            "Load-bearing candidates (by fan-in, emit one `load_bearing` entry "
            "for each): "
        )
        # evals/_load.py (fan-in 5, unreached) is a candidate; app.py is an
        # entrypoint shown in B but not a candidate, so it is not listed.
        assert listed[0] == "evals/_load.py"
        assert "src/demo/app.py" not in listed
        assert "src/demo/app.py" in record.signatures_shown
        assert set(listed) <= set(record.signatures_shown)
        assert len(listed) == 4

    def test_candidate_line_lists_only_candidates_that_fit_and_is_budgeted(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        full, _ = _context(tmp_path)
        tight = approx_tokens(full.split("### Key Module Signatures")[0]) + 180
        text, record = _context(tmp_path, budget=tight)
        assert approx_tokens(text) <= tight
        _, listed = _candidate_line(text)
        assert all(p in record.signatures_shown for p in listed)
        assert listed == ["src/demo/models.py", "src/demo/core.py", "src/demo/util.py"]
        assert "evals/_load.py" not in record.signatures_shown

    def test_no_signatures_means_no_candidate_line(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, "main.py", _module("main"))
        text, _ = _context(tmp_path)
        assert "Load-bearing candidates" not in text
        assert "Key Module Signatures" not in text or "####" in text


class TestStep4Blocks:
    def test_prior_round_block_lists_phase_titles_ahead_of_the_ids(
        self, tmp_path: pathlib.Path
    ) -> None:
        # D-SC4-8 (a): "- phase n — *title*" per numbered phase, before the
        # id list; summaries are not shown.
        _product(tmp_path)
        prior = _prior(["round_tree"], [(1, ["round_tree"]), (2, []), (None, [])])
        prior["phases"][0]["title"] = "Integration Thread"
        prior["phases"][0]["summary"] = "A long summary that must not appear"
        prior["phases"][1]["title"] = None
        prior["phases"][2]["title"] = "Unnumbered"
        text, _ = _context_prior(tmp_path, prior)
        block = _block(text, "### Prior Round (v2, implemented 2026-09-08)")
        assert "Phases of that round:\n- phase 1 — *Integration Thread*\n" in block
        assert "- phase 2 — *untitled*\n" in block
        assert "Unnumbered" not in block
        assert "long summary" not in block
        assert block.index("phase 1 — ") < block.index("- `round_tree`")
        assert "Planned stack facts" not in block  # no stack: no paragraph

    def test_prior_round_block_without_titles_has_no_phase_list(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        prior = _prior(["round_tree"], [(None, ["round_tree"])])
        text, _ = _context_prior(tmp_path, prior)
        assert "Phases of that round" not in text
        assert "- `round_tree` — no phase declared it" in text

    def test_prior_round_block_ends_with_the_planned_stack_facts(
        self, tmp_path: pathlib.Path
    ) -> None:
        # D-SC4-7: persistence_primary, provider_names, integrations[].name
        # and deployment_targets[].name, one paragraph after the ids.
        _product(tmp_path)
        prior = _prior(["round_tree"], [(1, ["round_tree"])])
        prior["stack"] = {
            "persistence_primary": "Neon (serverless Postgres) + pgvector",
            "provider_names": ["OpenRouter (via LiteLLM)", "Groq"],
            "integrations": [{"name": "Tavily", "kind": "search"}, {"name": None}],
            "deployment_targets": [{"name": "netcup VPS", "kind": "vps"}],
            "libraries": [{"name": "FastAPI", "category": "web"}],
        }
        text, _ = _context_prior(tmp_path, prior)
        block = _block(text, "### Prior Round")
        assert block.rstrip().endswith(
            "Planned stack facts (verbatim from that round's stack; a "
            "`divergences` entry names one whose counterpart in your review has "
            "a different name or shape): persistence: Neon (serverless Postgres) "
            "+ pgvector; providers: OpenRouter (via LiteLLM), Groq; integrations: "
            "Tavily; deployment targets: netcup VPS."
        )
        assert "FastAPI" not in block  # libraries are plan_drift's, not here
        assert block.index("- `round_tree`") < block.index("Planned stack facts")

    def test_planned_stack_facts_omit_absent_fields(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        prior = _prior(["round_tree"], [(1, ["round_tree"])])
        prior["stack"] = {"persistence_primary": None, "provider_names": ["Groq"]}
        text, _ = _context_prior(tmp_path, prior)
        block = _block(text, "### Prior Round")
        assert block.rstrip().endswith("shape): providers: Groq.")
        assert "persistence:" not in block

    def test_changes_block_lists_commits_dirs_and_most_touched(
        self, tmp_path: pathlib.Path
    ) -> None:
        # D-SC4-6: after the Prior Round block, before the signatures.
        _product(tmp_path)
        since = _since_block(
            most_touched=[("src/demo/core.py", 5), ("README.md", 2), ("x.py", 1)]
        )
        text, record = _context_since(tmp_path, since)
        assert record.changes_shown is True
        block = _block(
            text, "### Changes Since the Last Round (implemented 2026-09-08)"
        )
        assert (
            "14 commits by 2 authors; agent trailers present: yes; touched: "
            "`src` 12, `tests` 9." in block
        )
        assert (
            "Most-touched files since then (commits):\n"
            "- `src/demo/core.py` — 5\n- `README.md` — 2\n- `x.py` — 1\n" in block
        )
        assert "since the prior scan" not in block  # no delta on this scan
        assert text.index("### Changes Since") < text.index("### Key Module Signatures")

    def test_changes_block_caps_most_touched_and_wording_for_one(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        touched = [
            (f"f{i:02d}.py", 30 - i) for i in range(_sample._MAX_TOUCHED_SHOWN + 3)
        ]
        since = _since_block(commits=1, most_touched=touched)
        since["authors"] = ["A"]
        since["agent_trailers_present"] = False
        since["touched_top_dirs"] = {}
        text, _ = _context_since(tmp_path, since)
        block = _block(text, "### Changes Since the Last Round")
        assert "1 commit by 1 author; agent trailers present: no.\n" in block
        assert f"- `f{_sample._MAX_TOUCHED_SHOWN - 1:02d}.py`" in block
        assert f"- `f{_sample._MAX_TOUCHED_SHOWN:02d}.py`" not in block

    def test_changes_block_names_the_file_and_candidate_delta(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        since = _since_block()
        since["boundary_kind"] = "prior_review"
        added = [f"src/a{i}.py" for i in range(_sample._MAX_DELTA_SHOWN + 2)]
        delta = {
            "files": {"added": added, "removed": ["old.py"]},
            "candidates": {"entered": ["src/demo/core.py"], "left": []},
        }
        text, _ = _context_since(tmp_path, since, delta)
        block = _block(text, "### Changes Since the Last Round (scanned 2026-09-08)")
        assert "Most-touched" not in block
        assert (
            "Files added since the prior scan: `src/a0.py`, " in block
            and f"`src/a{_sample._MAX_DELTA_SHOWN - 1}.py` (+2 more)\n" in block
        )
        assert f"`src/a{_sample._MAX_DELTA_SHOWN}.py`" not in block
        assert "Files removed since the prior scan: `old.py`\n" in block
        assert (
            "Load-bearing candidates entered since the prior scan: "
            "`src/demo/core.py`\n" in block
        )
        assert "candidates left" not in block

    def test_no_round_boundary_means_no_changes_block_and_no_flag(
        self, tmp_path: pathlib.Path
    ) -> None:
        _product(tmp_path)
        text, record = _context_since(tmp_path, None)
        assert "Changes Since" not in text
        assert record.changes_shown is False
        # A git block without ``since_last_round`` is the same.
        files = collect_files(tmp_path)
        evidence = _collect.measure_scan(str(tmp_path), files, None)
        evidence = dataclasses.replace(
            evidence, scan={**evidence.scan, "git": {"available": True}}
        )
        record = SampleRecord()
        text = gather_project_context(str(tmp_path), files, record, evidence)
        assert "Changes Since" not in text
        assert record.changes_shown is False
