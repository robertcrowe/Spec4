"""Golden artifact files for ``project_manager``'s assembly paths (Phase 1).

Two files leave Spec4 for a coding agent to read: the phase files under
``.spec4/v{N}/phases/`` and the project ``README.md``. Their shape — the JSON
frontmatter, the section order, the deterministic spec preamble, the stack and
NFR threading, the attribution footer — is a frozen surface (cleanup Rule 4).
``tests/test_project_manager.py`` asserts individual lines; this pins the
whole file, through the real write path, against checked-in goldens.

The full-phase fixture is built to drive every branch of
``_phase_spec_preamble``: a product feature with a known and an unknown id,
a capability with a known and an unknown id, a plain and a catalog-backed UI
surface, a dependency and an entities line, the served-features relation,
and cross-cutting guidance with the excluded ``provider_strategy`` key. The
final-phase fixture reaches the project-wide NFR acceptance branch.
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Any

from spec4 import project_manager
from tests._golden import assert_golden, load_fixture


def _phase_dir(root: pathlib.Path, version: int = 1) -> pathlib.Path:
    return project_manager.get_version_dir(root, version) / "phases"


class TestPhaseMarkdown:
    def test_full_phase_with_context(self) -> None:
        assert_golden(
            "phase_full.md",
            project_manager.render_phase_markdown(
                load_fixture("phase_full.json"), load_fixture("phase_context.json")
            ),
        )

    def test_final_phase_threads_global_nfr(self) -> None:
        assert_golden(
            "phase_final.md",
            project_manager.render_phase_markdown(
                load_fixture("phase_final.json"), load_fixture("phase_context.json")
            ),
        )

    def test_full_phase_without_context(self) -> None:
        assert_golden(
            "phase_full_no_context.md",
            project_manager.render_phase_markdown(load_fixture("phase_full.json")),
        )

    def test_a_stack_with_nothing_to_route_adds_no_lines(self) -> None:
        with_stack = project_manager.render_phase_markdown(
            load_fixture("phase_minimal.json"),
            load_fixture("phase_context_deferred_stack.json"),
        )
        without = project_manager.render_phase_markdown(
            load_fixture("phase_minimal.json")
        )
        assert with_stack == without

    def test_minimal_phase(self) -> None:
        assert_golden(
            "phase_minimal.md",
            project_manager.render_phase_markdown(load_fixture("phase_minimal.json")),
        )

    def test_frontmatter_round_trips_the_phase_verbatim(self) -> None:
        for name in ("phase_full.json", "phase_final.json", "phase_minimal.json"):
            phase = load_fixture(name)
            text = project_manager.render_phase_markdown(
                phase, load_fixture("phase_context.json")
            )
            assert project_manager.parse_phase_markdown(text) == phase

    def test_frontmatter_is_indented_json_with_unicode_kept(self) -> None:
        phase = {"phase_number": 1, "phase_title": "Résumé — naïve"}
        text = project_manager.render_phase_markdown(phase)
        head, body = text.split("\n---\n", 1)
        assert head == "---\n" + json.dumps(phase, indent=2, ensure_ascii=False)
        assert body.startswith("\n# Phase 1 of ?: Résumé — naïve")

    def test_parse_rejects_text_without_frontmatter(self) -> None:
        assert project_manager.parse_phase_markdown("# no frontmatter\n") is None
        assert project_manager.parse_phase_markdown("---\nnot json\n---\n") is None
        assert project_manager.parse_phase_markdown("---\n[1, 2]\n---\n") is None


class TestSavePhases:
    def test_writes_one_file_per_phase_matching_the_goldens(
        self, tmp_path: pathlib.Path
    ) -> None:
        context = load_fixture("phase_context.json")
        phases = [load_fixture("phase_full.json"), load_fixture("phase_final.json")]
        project_manager.save_phases(tmp_path, phases, 1, context)
        phases_dir = _phase_dir(tmp_path)
        assert sorted(p.name for p in phases_dir.iterdir()) == [
            "phase1.md",
            "phase2.md",
        ]
        assert_golden("phase_full.md", (phases_dir / "phase1.md").read_text())
        assert_golden("phase_final.md", (phases_dir / "phase2.md").read_text())

    def test_stale_phase_files_are_removed_and_the_marker_kept(
        self, tmp_path: pathlib.Path
    ) -> None:
        phases_dir = _phase_dir(tmp_path)
        phases_dir.mkdir(parents=True)
        (phases_dir / "phase3.md").write_text("stale")
        (phases_dir / "notes.txt").write_text("not a phase file")
        marker = phases_dir.parent / "IMPLEMENTED"
        marker.write_text("")
        project_manager.save_phases(
            tmp_path, [load_fixture("phase_minimal.json")], 1, None
        )
        assert sorted(p.name for p in phases_dir.iterdir()) == [
            "notes.txt",
            "phase3.md",
        ]
        assert marker.exists()

    def test_unchanged_resave_leaves_mtime_alone(self, tmp_path: pathlib.Path) -> None:
        phases = [load_fixture("phase_minimal.json")]
        project_manager.save_phases(tmp_path, phases, 1, None)
        target = _phase_dir(tmp_path) / "phase3.md"
        old = 1_000_000_000
        os.utime(target, (old, old))
        project_manager.save_phases(tmp_path, phases, 1, None)
        assert target.stat().st_mtime == old
        project_manager.save_phases(
            tmp_path, [{**phases[0], "phase_title": "Changed"}], 1, None
        )
        assert target.stat().st_mtime != old


_README_BODY = (
    "# Ragmeister\n\nPolicy Q&A with citations.\n\n## Install\n\n```\nuv sync\n```\n"
)


class TestReadme:
    def test_fresh_readme_gets_the_footer(self, tmp_path: pathlib.Path) -> None:
        project_manager.save_readme(tmp_path, _README_BODY)
        assert_golden("README.md", (tmp_path / "README.md").read_text())

    def test_saving_the_stamped_file_again_is_byte_identical(
        self, tmp_path: pathlib.Path
    ) -> None:
        project_manager.save_readme(tmp_path, _README_BODY)
        stamped = (tmp_path / "README.md").read_text()
        project_manager.save_readme(tmp_path, stamped)
        assert (tmp_path / "README.md").read_text() == stamped

    def test_a_footer_in_the_middle_moves_to_the_end(
        self, tmp_path: pathlib.Path
    ) -> None:
        line = project_manager.SPEC4_README_ATTRIBUTION
        revised = f"# T\n\nintro\n\n{line}\n\n## Added later\n\nmore\n"
        project_manager.save_readme(tmp_path, revised)
        assert_golden("README_moved_footer.md", (tmp_path / "README.md").read_text())

    def test_footer_only_input(self) -> None:
        line = project_manager.SPEC4_README_ATTRIBUTION
        assert project_manager._with_readme_attribution(line) == f"{line}\n"
        assert project_manager._with_readme_attribution(f"\n{line}\n\n") == f"{line}\n"

    def test_empty_input_is_returned_unchanged(self, tmp_path: pathlib.Path) -> None:
        assert project_manager._with_readme_attribution("") == ""
        assert project_manager._with_readme_attribution("  \n") == "  \n"
        project_manager.save_readme(tmp_path, "")
        assert (tmp_path / "README.md").read_text() == ""

    def test_load_existing_readme_round_trips(self, tmp_path: pathlib.Path) -> None:
        assert project_manager.load_existing_readme(tmp_path) is None
        project_manager.save_readme(tmp_path, _README_BODY)
        loaded: Any = project_manager.load_existing_readme(tmp_path)
        assert loaded == (tmp_path / "README.md").read_text()
