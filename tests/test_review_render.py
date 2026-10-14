"""The Scan Summary section of ``code_scanner._review_render`` (v2 steps 1b–1d).

The renderer's other sections are pinned by ``tests/test_renderer_goldens.py``,
a whole-file floor entry whose node ids may not change; the 1b goldens live
here for that reason, with the unit tests for the summary's line builders.
"""

from __future__ import annotations

from spec4.agents.code_scanner._review_render import (
    _scan_candidates_line,
    _scan_coverage_line,
    _scan_prior_line,
    _scan_reach_line,
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

    def test_scan_summary_names_the_sampled_evidence_and_the_reach(self) -> None:
        # 2.4.0 (step 2a): the coverage line gains signature and convention
        # counts and the evidence size, and a reach line follows the
        # candidates; differs from the 1d golden by those two lines only.
        assert_golden(
            "render_review_with_scan_sampled.md",
            format_review_as_text(load_fixture("review_with_scan_sampled.json")),
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


class TestSampledEvidenceLines:
    def test_coverage_line_adds_the_2a_counts_only_when_present(self) -> None:
        base = {"source_files_sampled": 2, "source_files_total": 9, "manifests": []}
        assert _scan_coverage_line(base) == (
            "- Shown to the model: 2 of 9 source files sampled, 0 manifests"
        )
        full = {
            **base,
            "signatures_shown": ["a.py", "b.py"],
            "conventions": ["AGENTS.md"],
            "evidence_tokens": 17368,
        }
        assert _scan_coverage_line(full) == (
            "- Shown to the model: 2 of 9 source files sampled, 0 manifests, "
            "2 signature files, 1 convention file (~17,368 tokens)"
        )

    def test_reach_line_names_roots_and_unreached_dirs_with_caps(self) -> None:
        reach = {
            "basis": "entrypoints",
            "entrypoints": ["a.py", "b.py", "c.py", "d.py"],
            "reached": 97,
            "unreached_dirs": ["evals", "scripts", "x", "y", "z"],
        }
        assert _scan_reach_line(reach) == (
            "- Reach: 97 modules from entrypoint `a.py`, `b.py`, `c.py` and 1 more; "
            "unreached: `evals`, `scripts`, `x` and 2 more"
        )

    def test_reach_line_from_a_declared_package_without_unreached_dirs(
        self,
    ) -> None:
        reach = {
            "basis": "manifest",
            "entrypoints": ["src/pkg"],
            "reached": 4,
            "unreached_dirs": [],
        }
        assert _scan_reach_line(reach) == (
            "- Reach: 4 modules from declared package `src/pkg`"
        )

    def test_reach_line_is_absent_when_reach_is_unknown_or_missing(self) -> None:
        assert _scan_reach_line(None) is None
        assert _scan_reach_line({"basis": "none", "entrypoints": []}) is None
        # Paired positive: a known basis does render.
        assert _scan_reach_line({"basis": "entrypoints", "reached": 0}) is not None


class TestStep3Sections:
    def test_load_bearing_implemented_and_integrations_render(self) -> None:
        # 2.6.0 (step 3a, D-SC3-12): Load-Bearing Modules and Implemented
        # after Architecture, Integrations after AI Capabilities. The 2a
        # fixture with the three arrays added; the 2a golden is unchanged.
        assert_golden(
            "render_review_with_step3.md",
            format_review_as_text(load_fixture("review_with_step3.json")),
        )

    def test_sections_sit_where_the_decision_placed_them(self) -> None:
        text = format_review_as_text(load_fixture("review_with_step3.json"))
        order = [
            "**Architecture:**",
            "**Load-Bearing Modules:**",
            "**Implemented:**",
            "**Languages & Frameworks:**",
            "**AI Capabilities:**",
            "**Integrations:**",
            "**UI:**",
        ]
        positions = [text.index(h) for h in order]
        assert positions == sorted(positions)

    def test_absent_or_empty_arrays_render_nothing(self) -> None:
        for value in (None, [], "n/a"):
            fields = {
                "load_bearing": value,
                "implemented": value,
                "integrations": value,
            }
            fields = {k: v for k, v in fields.items() if v is not None}
            text = format_review_as_text(review_envelope(**fields))
            for heading in ("Load-Bearing", "Implemented:", "Integrations:"):
                assert heading not in text

    def test_odd_entries_fall_back_to_their_text(self) -> None:
        text = format_review_as_text(
            review_envelope(
                load_bearing=["raw", {"module": "m.py", "contract": "x"}],
                implemented=["raw", {"id": "only_id"}],
                integrations=["raw", {"name": "Thing"}],
            )
        )
        assert text.count("- raw") == 3
        assert "- `m.py`\n" in text  # no symbol, no consumers, no role, no contract
        assert "- only_id\n" in text
        assert "- Thing\n" in text


class TestStep4Sections:
    def test_reconciliation_unplanned_changes_and_divergences_render(self) -> None:
        # 2.8.0 (step 4a, D-SC4-10): Prior Round Reconciliation and Unplanned
        # Changes after Implemented, Divergences after Integrations. The 3a
        # fixture with the three arrays (as stored — the code-owned fields
        # filled) and a third implemented entry; the 3a golden is unchanged.
        assert_golden(
            "render_review_with_step4.md",
            format_review_as_text(load_fixture("review_with_step4.json")),
        )

    def test_sections_sit_where_the_decision_placed_them(self) -> None:
        text = format_review_as_text(load_fixture("review_with_step4.json"))
        order = [
            "**Implemented:**",
            "**Prior Round Reconciliation**",
            "**Unplanned Changes:**",
            "**Languages & Frameworks:**",
            "**Integrations:**",
            "**Divergences:**",
            "**UI:**",
        ]
        positions = [text.index(h) for h in order]
        assert positions == sorted(positions)
        assert text.count("(feature coverage, not phase scope)") == 1

    def test_reconciliation_lines_carry_verdict_ids_and_gap(self) -> None:
        text = format_review_as_text(
            review_envelope(
                prior_round_reconciliation=[
                    {
                        "phase_number": 1,
                        "verdict": "evidence_partial",
                        "implemented_ids": ["a", "b"],
                        "paths": ["x.py"],
                        "features": [],
                        "gap": "b is a stub",
                    },
                    {"phase_number": 2, "verdict": "unassessed", "title": None},
                    {"phase_number": 3},
                    {"phase_number": 4, "title": "Edge — TLS", "verdict": "unassessed"},
                ]
            )
        )
        assert "- phase 1 [evidence_partial] — `a`, `b`; gap: b is a stub\n" in text
        assert "- phase 2 [unassessed]\n" in text
        assert "- phase 3\n" in text
        # D-SC4b-5: the title, when the item carries one, follows the number.
        assert "- phase 4 — *Edge — TLS* [unassessed]\n" in text
        assert "x.py" not in text  # paths are stored, not shown

    def test_unplanned_change_and_divergence_lines(self) -> None:
        text = format_review_as_text(
            review_envelope(
                unplanned_changes=[
                    {
                        "area": "auth",
                        "summary": "A session store appeared",
                        "affects": ["src/auth.py"],
                        "classification": "out_of_round",
                    },
                    {"area": "docs", "summary": "Churn"},
                ],
                divergences=[
                    {
                        "area": "providers",
                        "planned": "OpenRouter (via LiteLLM)",
                        "found": "OpenRouter",
                        "kind": "renamed",
                        "note": "Same provider",
                    },
                    {"planned": "a", "found": "b"},
                ],
            )
        )
        assert (
            "- auth [out_of_round] — A session store appeared · affects: "
            "`src/auth.py`\n" in text
        )
        assert "- docs — Churn\n" in text
        assert (
            "- providers: OpenRouter (via LiteLLM) → OpenRouter [renamed] — "
            "Same provider\n" in text
        )
        assert "- a → b\n" in text

    def test_absent_or_empty_arrays_render_nothing(self) -> None:
        for value in (None, [], "n/a"):
            fields = {
                "prior_round_reconciliation": value,
                "unplanned_changes": value,
                "divergences": value,
            }
            fields = {k: v for k, v in fields.items() if v is not None}
            text = format_review_as_text(review_envelope(**fields))
            for heading in ("Reconciliation", "Unplanned Changes", "Divergences"):
                assert heading not in text
        # Paired positive: one entry each does render.
        text = format_review_as_text(
            review_envelope(
                prior_round_reconciliation=[{"phase_number": 1}],
                unplanned_changes=[{"area": "a", "summary": "s"}],
                divergences=[{"area": "stack", "planned": "p", "found": "f"}],
            )
        )
        for heading in ("Reconciliation", "Unplanned Changes", "Divergences"):
            assert heading in text

    def test_odd_entries_fall_back_to_their_text(self) -> None:
        text = format_review_as_text(
            review_envelope(
                prior_round_reconciliation=["raw"],
                unplanned_changes=["raw", {"summary": "no area"}],
                divergences=["raw"],
            )
        )
        assert text.count("- raw") == 3
        assert "- {'summary': 'no area'} — no area\n" in text
