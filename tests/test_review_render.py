"""The Scan Summary section of ``code_scanner._review_render`` (v2 steps 1b–1c).

The renderer's other sections are pinned by ``tests/test_renderer_goldens.py``,
a whole-file floor entry whose node ids may not change; the 1b goldens live
here for that reason, with the unit tests for the summary's line builders.
"""

from __future__ import annotations

from spec4.agents.code_scanner._review_render import (
    _scan_candidates_line,
    _since_summary,
    _skipped_summary,
    format_review_as_text,
)
from tests._golden import assert_golden, load_fixture
from tests._review_helpers import review_envelope


class TestScanSummaryGoldens:
    def test_scan_summary_leads_a_measured_review(self) -> None:
        # The computed layer renders ahead of the model's block. The fixtures
        # in test_renderer_goldens carry `scan: {}` and are unchanged by it.
        assert_golden(
            "render_review_with_scan.md",
            format_review_as_text(load_fixture("review_with_scan.json")),
        )

    def test_scan_summary_names_the_load_bearing_candidates(self) -> None:
        # 1c: one more line, present only when the scan carries a graph; the
        # 1b fixtures above have none and their goldens are unchanged.
        assert_golden(
            "render_review_with_scan_graph.md",
            format_review_as_text(load_fixture("review_with_scan_graph.json")),
        )

    def test_scan_summary_on_a_non_software_directory(self) -> None:
        assert_golden(
            "render_review_empty_with_scan.md",
            format_review_as_text(load_fixture("review_not_software_with_scan.json")),
        )

    def test_empty_scan_renders_no_summary(self) -> None:
        text = format_review_as_text(review_envelope(scan={}))
        assert "Scan Summary" not in text
        assert "**Code Review Complete**" in text

    def test_scan_without_inventory_renders_no_summary(self) -> None:
        text = format_review_as_text(
            review_envelope(scan={"git": {"available": False}})
        )
        assert "Scan Summary" not in text


class TestSummaryLines:
    def test_skipped_groups_by_name_and_caps(self) -> None:
        dirs = [f"pkg{i}/__pycache__" for i in range(14)] + [".git", ".venv"]
        assert _skipped_summary(dirs) == "`__pycache__` ×14, `.git`, `.venv`"
        many = [f"d{i}" for i in range(8)]
        assert _skipped_summary(many).endswith("and 2 more")

    def test_candidates_line_caps_at_five_and_is_absent_when_empty(self) -> None:
        graph = {
            "load_bearing_candidates": [
                {"path": f"m{i}.py", "fan_in": 9 - i, "consumers": []} for i in range(7)
            ]
        }
        assert _scan_candidates_line(graph) == (
            "- Load-bearing candidates: `m0.py` (9), `m1.py` (8), `m2.py` (7), "
            "`m3.py` (6), `m4.py` (5) and 2 more"
        )
        assert _scan_candidates_line({"load_bearing_candidates": []}) is None
        assert _scan_candidates_line({}) is None
        text = format_review_as_text(
            review_envelope(
                scan={
                    "inventory": {"files_total": 1},
                    "module_graph": {"load_bearing_candidates": []},
                }
            )
        )
        assert "Load-bearing" not in text
        assert "**Scan Summary**" in text

    def test_since_summary_says_no_commits_plainly(self) -> None:
        since = {
            "commits": 0,
            "boundary": "2026-09-28T17:00:00+00:00",
            "boundary_kind": "prior_review",
        }
        assert _since_summary(since) == "no commits since the prior scan (2026-09-28)"

    def test_since_summary_singulars(self) -> None:
        since = {
            "commits": 1,
            "boundary": "2026-09-28T17:00:00+00:00",
            "boundary_kind": "implemented",
            "authors": ["A"],
            "touched_top_dirs": {"src": 1},
        }
        assert _since_summary(since) == (
            "1 commit since the last implemented round (2026-09-28), 1 author, "
            "touching `src`"
        )
