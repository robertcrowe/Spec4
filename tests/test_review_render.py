"""The Scan Summary section of ``code_scanner._review_render`` (v2 steps 1b–1d).

The renderer's other sections are pinned by ``tests/test_renderer_goldens.py``,
a whole-file floor entry whose node ids may not change; the 1b goldens live
here for that reason, with the unit tests for the summary's line builders.
"""

from __future__ import annotations

from spec4.agents.code_scanner._review_render import (
    _scan_candidates_line,
    _scan_prior_line,
    _since_summary,
    _skipped_summary,
    _tree_state,
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

    def test_scan_summary_names_the_prior_round_and_the_drift(self) -> None:
        # 1d: one more line, gated on ``prior_round``, and the git line reads
        # ``working_tree``; the 1b and 1c goldens above are unchanged.
        assert_golden(
            "render_review_with_scan_prior.md",
            format_review_as_text(load_fixture("review_with_scan_prior.json")),
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

    def test_prior_line_counts_and_names_the_catalog_round(self) -> None:
        prior = {
            "version": 8,
            "phases": [{}] * 6,
            "implemented": "2026-10-01T23:30:22+00:00",
            "capabilities_from_version": 7,
        }
        drift = {
            "planned_unmatched": [{}] * 5,
            "planned_only_imported": [],
            "declared_not_planned": [{}] * 11,
        }
        assert _scan_prior_line(prior, drift) == (
            "- Prior round: v8 (6 phases; implemented 2026-10-01; catalog from v7); "
            "plan drift: 5 planned deps unmatched, 11 declared but unplanned"
        )

    def test_prior_line_singulars_own_catalog_and_no_drift(self) -> None:
        prior = {"version": 3, "phases": [{}], "capabilities_from_version": 3}
        assert _scan_prior_line(prior, None) == "- Prior round: v3 (1 phase)"
        drift = {
            "planned_unmatched": [{}],
            "planned_only_imported": [{}, {}],
            "declared_not_planned": [],
        }
        assert _scan_prior_line(prior, drift) == (
            "- Prior round: v3 (1 phase); plan drift: 1 planned dep unmatched, "
            "2 imported but undeclared, 0 declared but unplanned"
        )
        text = format_review_as_text(
            review_envelope(
                scan={"inventory": {"files_total": 1}, "prior_round": prior}
            )
        )
        assert "- Prior round: v3 (1 phase)" in text
        assert "plan drift" not in text

    def test_tree_state_reads_working_tree_when_present(self) -> None:
        assert (
            _tree_state({"dirty": True, "untracked_count": 2}) == "dirty, 2 untracked"
        )
        assert _tree_state({"dirty": False, "untracked_count": 0}) == "clean"
        tree = {"modified_top_dirs": {"src": 2, ".": 1}, "untracked_top_dirs": {}}
        assert _tree_state({"working_tree": tree, "untracked_count": 0}) == "3 modified"
        empty = {"modified_top_dirs": {}, "untracked_top_dirs": {}}
        assert _tree_state({"working_tree": empty, "untracked_count": 0}) == "clean"
        assert (
            _tree_state({"working_tree": empty, "untracked_count": 4, "dirty": False})
            == "4 untracked"
        )

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
