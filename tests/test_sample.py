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
