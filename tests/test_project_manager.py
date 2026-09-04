import json
from pathlib import Path
from typing import Any


from spec4 import project_manager


class TestDirHelpers:
    def test_get_spec4_dir_returns_dotspec4_subdir(self, tmp_path: Path) -> None:
        assert project_manager.get_spec4_dir(tmp_path) == tmp_path / ".spec4"

    def test_ensure_spec4_dir_creates_directory(self, tmp_path: Path) -> None:
        d = project_manager.ensure_spec4_dir(tmp_path)
        assert d.exists() and d.is_dir()

    def test_ensure_spec4_dir_is_idempotent(self, tmp_path: Path) -> None:
        project_manager.ensure_spec4_dir(tmp_path)
        project_manager.ensure_spec4_dir(tmp_path)  # must not raise


class TestLoadArtifacts:
    def test_missing_dir_returns_empty_result(self, tmp_path: Path) -> None:
        result = project_manager.load_spec4_artifacts(tmp_path)
        assert result == {
            "vision": None,
            "stack": None,
            "code_review": None,
            "phases": [],
            "phase_version": None,
            "feature_specs": None,
        }

    def test_loads_vision(self, tmp_path: Path) -> None:
        vision = {"name": "App", "vision": "desc"}
        project_manager.save_vision(tmp_path, vision, 0)
        assert project_manager.load_spec4_artifacts(tmp_path)["vision"] == vision

    def test_loads_stack(self, tmp_path: Path) -> None:
        stack = {"language": "Python"}
        project_manager.save_stack(tmp_path, stack, 0)
        assert project_manager.load_spec4_artifacts(tmp_path)["stack"] == stack

    def test_loads_code_review(self, tmp_path: Path) -> None:
        review = {"code_review": {"is_software_project": True}}
        project_manager.save_code_review(tmp_path, review, 0)
        assert project_manager.load_spec4_artifacts(tmp_path)["code_review"] == review

    def test_loads_phases_in_order(self, tmp_path: Path) -> None:
        phases = [
            {"phase_number": 2, "phase_title": "Auth"},
            {"phase_number": 1, "phase_title": "Steel Thread"},
        ]
        project_manager.save_phases(tmp_path, phases, 0)
        result = project_manager.load_spec4_artifacts(tmp_path)["phases"]
        assert len(result) == 2
        assert result[0]["phase_number"] == 1

    def test_loads_latest_version_only(self, tmp_path: Path) -> None:
        # v0 greenfield, then a v1 brownfield round. The session/Deployer track
        # only the latest set, so load returns v1 and reports phase_version=1.
        project_manager.save_phases(
            tmp_path, [{"phase_number": 1, "phase_title": "v0 only"}], 0
        )
        project_manager.save_phases(
            tmp_path,
            [
                {"phase_number": 1, "phase_title": "v1 first"},
                {"phase_number": 2, "phase_title": "v1 second"},
            ],
            1,
        )
        result = project_manager.load_spec4_artifacts(tmp_path)
        assert result["phase_version"] == 1
        titles = [p["phase_title"] for p in result["phases"]]
        assert titles == ["v1 first", "v1 second"]

    def test_ignores_invalid_json_files(self, tmp_path: Path) -> None:
        spec4_dir = project_manager.ensure_spec4_dir(tmp_path)
        (spec4_dir / "vision.json").write_text("not valid json {{")
        result = project_manager.load_spec4_artifacts(tmp_path)
        assert result["vision"] is None


class TestSaveArtifacts:
    def test_save_vision_writes_json_file(self, tmp_path: Path) -> None:
        vision = {"name": "MyApp"}
        project_manager.save_vision(tmp_path, vision, 0)
        path = tmp_path / ".spec4" / "v0" / "vision.json"
        assert path.exists()
        assert json.loads(path.read_text()) == vision

    def test_save_stack_writes_json_file(self, tmp_path: Path) -> None:
        stack = {"language": "Python"}
        project_manager.save_stack(tmp_path, stack, 0)
        path = tmp_path / ".spec4" / "v0" / "stack.json"
        assert path.exists()
        assert json.loads(path.read_text()) == stack

    def test_save_code_review_writes_json_file(self, tmp_path: Path) -> None:
        review: dict[str, Any] = {"code_review": {}}
        project_manager.save_code_review(tmp_path, review, 0)
        path = tmp_path / ".spec4" / "v0" / "code_review.json"
        assert path.exists()
        assert json.loads(path.read_text()) == review

    def test_save_phases_writes_individual_files(self, tmp_path: Path) -> None:
        phases = [
            {"phase_number": 1, "phase_title": "A"},
            {"phase_number": 2, "phase_title": "B"},
        ]
        project_manager.save_phases(tmp_path, phases, 0)
        assert (tmp_path / ".spec4" / "v0" / "phases" / "phase1.md").exists()
        assert (tmp_path / ".spec4" / "v0" / "phases" / "phase2.md").exists()

    def test_save_phases_writes_under_brownfield_version(self, tmp_path: Path) -> None:
        project_manager.save_phases(
            tmp_path, [{"phase_number": 1, "phase_title": "v2"}], 2
        )
        assert (tmp_path / ".spec4" / "v2" / "phases" / "phase1.md").exists()

    def test_save_phases_clears_stale_files_in_target_version(
        self, tmp_path: Path
    ) -> None:
        # A re-defined set may be shorter; stale higher-numbered files must go.
        project_manager.save_phases(
            tmp_path,
            [
                {"phase_number": 1, "phase_title": "A"},
                {"phase_number": 2, "phase_title": "B"},
                {"phase_number": 3, "phase_title": "C"},
            ],
            0,
        )
        project_manager.save_phases(
            tmp_path, [{"phase_number": 1, "phase_title": "A only"}], 0
        )
        phases_dir = tmp_path / ".spec4" / "v0" / "phases"
        assert (phases_dir / "phase1.md").exists()
        assert not (phases_dir / "phase2.md").exists()
        assert not (phases_dir / "phase3.md").exists()

    def test_save_phases_preserves_implemented_marker(self, tmp_path: Path) -> None:
        project_manager.save_phases(
            tmp_path, [{"phase_number": 1, "phase_title": "A"}], 0
        )
        marker = tmp_path / ".spec4" / "v0" / "IMPLEMENTED"
        marker.touch()
        project_manager.save_phases(
            tmp_path, [{"phase_number": 1, "phase_title": "A revised"}], 0
        )
        assert marker.exists()

    def test_save_creates_spec4_dir_if_missing(self, tmp_path: Path) -> None:
        project_manager.save_vision(tmp_path, {"name": "App"}, 0)
        assert (tmp_path / ".spec4").is_dir()


class TestResolvePhaseVersion:
    def _make_version(
        self, tmp_path: Path, n: int, implemented: bool = False
    ) -> None:
        vdir = tmp_path / ".spec4" / f"v{n}"
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "phases").mkdir(exist_ok=True)
        (vdir / "phases" / "phase1.md").write_text("x", encoding="utf-8")
        if implemented:
            (vdir / "IMPLEMENTED").touch()

    def test_no_dirs_greenfield_is_v0(self, tmp_path: Path) -> None:
        assert project_manager.resolve_phase_version(tmp_path, False) == (0, True)

    def test_no_dirs_brownfield_is_v1(self, tmp_path: Path) -> None:
        # An imported existing codebase has no v0 of Spec4's making: v0 stands
        # for the implementation that was already there, so Spec4 starts at v1.
        assert project_manager.resolve_phase_version(tmp_path, True) == (1, False)

    def test_unimplemented_v0_is_redefined(self, tmp_path: Path) -> None:
        self._make_version(tmp_path, 0, implemented=False)
        assert project_manager.resolve_phase_version(tmp_path, False) == (0, True)

    def test_lowest_unimplemented_is_targeted(self, tmp_path: Path) -> None:
        self._make_version(tmp_path, 0, implemented=True)
        self._make_version(tmp_path, 1, implemented=False)
        assert project_manager.resolve_phase_version(tmp_path, True) == (1, False)

    def test_all_implemented_starts_new_round(self, tmp_path: Path) -> None:
        self._make_version(tmp_path, 0, implemented=True)
        self._make_version(tmp_path, 1, implemented=True)
        assert project_manager.resolve_phase_version(tmp_path, True) == (2, False)

    def test_only_implemented_v0_yields_v1(self, tmp_path: Path) -> None:
        self._make_version(tmp_path, 0, implemented=True)
        assert project_manager.resolve_phase_version(tmp_path, True) == (1, False)

    def test_highest_dir_governs_even_when_lower_unimplemented(
        self, tmp_path: Path
    ) -> None:
        # v0 was started but never implemented; v1 was completed. The highest
        # implemented dir is v1, so the next round is v2 — not v0 again.
        self._make_version(tmp_path, 0, implemented=False)
        self._make_version(tmp_path, 1, implemented=True)
        assert project_manager.resolve_phase_version(tmp_path, True) == (2, False)

    def test_latest_phase_version_tracks_highest(self, tmp_path: Path) -> None:
        assert project_manager.latest_phase_version(tmp_path) is None
        self._make_version(tmp_path, 0)
        self._make_version(tmp_path, 2)
        assert project_manager.latest_phase_version(tmp_path) == 2


class TestDetectStaleInputs:
    def _touch_with_mtime(self, path: Path, mtime: float) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        import os
        os.utime(path, (mtime, mtime))

    def test_unknown_agent_returns_empty(self, tmp_path: Path) -> None:
        assert project_manager.detect_stale_inputs(tmp_path, "nonsense") == {}

    def test_no_output_artifact_returns_empty(self, tmp_path: Path) -> None:
        # vision.json exists but stack.json does not — stack hasn't run yet
        self._touch_with_mtime(tmp_path / ".spec4" / "v0" / "vision.json", 1_000.0)
        assert project_manager.detect_stale_inputs(tmp_path, "stack_advisor") == {}

    def test_output_newer_than_inputs_returns_empty(self, tmp_path: Path) -> None:
        self._touch_with_mtime(tmp_path / ".spec4" / "v0" / "vision.json", 1_000.0)
        self._touch_with_mtime(tmp_path / ".spec4" / "v0" / "stack.json", 2_000.0)
        assert project_manager.detect_stale_inputs(tmp_path, "stack_advisor") == {}

    def test_input_newer_than_output_marks_stale(self, tmp_path: Path) -> None:
        self._touch_with_mtime(tmp_path / ".spec4" / "v0" / "stack.json", 1_000.0)
        self._touch_with_mtime(tmp_path / ".spec4" / "v0" / "vision.json", 2_000.0)
        result = project_manager.detect_stale_inputs(tmp_path, "stack_advisor")
        assert result == {"vision": 2_000.0}

    def test_multiple_stale_inputs(self, tmp_path: Path) -> None:
        self._touch_with_mtime(tmp_path / ".spec4" / "v0" / "stack.json", 1_000.0)
        self._touch_with_mtime(tmp_path / ".spec4" / "v0" / "vision.json", 2_000.0)
        self._touch_with_mtime(tmp_path / ".spec4" / "v0" / "code_review.json", 3_000.0)
        result = project_manager.detect_stale_inputs(tmp_path, "stack_advisor")
        assert set(result) == {"vision", "code review"}
        assert result["vision"] == 2_000.0
        assert result["code review"] == 3_000.0

    def test_missing_input_is_skipped(self, tmp_path: Path) -> None:
        # Only stack.json present; no upstream files at all
        self._touch_with_mtime(tmp_path / ".spec4" / "v0" / "stack.json", 1_000.0)
        assert project_manager.detect_stale_inputs(tmp_path, "stack_advisor") == {}

    def test_phaser_uses_phases_directory_mtime(self, tmp_path: Path) -> None:
        self._touch_with_mtime(
            tmp_path / ".spec4" / "v0" / "phases" / "phase1.json", 1_000.0
        )
        self._touch_with_mtime(
            tmp_path / ".spec4" / "v0" / "phases" / "phase2.json", 1_500.0
        )
        # Vision newer than the most recent phase
        self._touch_with_mtime(tmp_path / ".spec4" / "v0" / "vision.json", 2_000.0)
        result = project_manager.detect_stale_inputs(tmp_path, "phaser")
        assert result == {"vision": 2_000.0}

    def test_designer_depends_on_vision(self, tmp_path: Path) -> None:
        self._touch_with_mtime(
            tmp_path / ".spec4" / "v0" / "design" / "mock.html", 1_000.0
        )
        self._touch_with_mtime(tmp_path / ".spec4" / "v0" / "vision.json", 2_000.0)
        result = project_manager.detect_stale_inputs(tmp_path, "designer")
        assert result == {"vision": 2_000.0}

    def test_deployer_depends_on_phases_dir(self, tmp_path: Path) -> None:
        self._touch_with_mtime(
            tmp_path / ".spec4" / "v0" / "deployment-plan.md", 1_000.0
        )
        self._touch_with_mtime(
            tmp_path / ".spec4" / "v0" / "phases" / "phase1.json", 2_000.0
        )
        result = project_manager.detect_stale_inputs(tmp_path, "deployer")
        assert "phases" in result


class TestVersionedLayoutExtras:
    def _make_version(self, tmp_path: Path, n: int, implemented: bool = False) -> None:
        vdir = tmp_path / ".spec4" / f"v{n}"
        vdir.mkdir(parents=True, exist_ok=True)
        if implemented:
            (vdir / "IMPLEMENTED").touch()

    def test_active_version_prefers_session_pin(self, tmp_path: Path) -> None:
        self._make_version(tmp_path, 3)
        session: dict[str, Any] = {"phase_version": 1}
        assert project_manager.active_version(tmp_path, session) == 1

    def test_active_version_falls_back_to_latest_on_disk(
        self, tmp_path: Path
    ) -> None:
        self._make_version(tmp_path, 0)
        self._make_version(tmp_path, 2)
        assert project_manager.active_version(tmp_path, None) == 2

    def test_active_version_returns_zero_when_no_dirs(self, tmp_path: Path) -> None:
        assert project_manager.active_version(tmp_path) == 0


class TestIdempotentWrites:
    """Re-persisting an unchanged artifact must not bump its mtime, so the
    freshness model never sees an untouched upstream as 'newer'."""

    def test_write_if_changed_preserves_mtime_on_noop(self, tmp_path: Path) -> None:
        import os

        p = tmp_path / "a.json"
        project_manager._write_text_if_changed(p, '{"x": 1}')
        os.utime(p, (1000, 1000))
        project_manager._write_text_if_changed(p, '{"x": 1}')  # identical
        assert os.stat(p).st_mtime == 1000

    def test_write_if_changed_rewrites_on_change(self, tmp_path: Path) -> None:
        import os

        p = tmp_path / "a.json"
        project_manager._write_text_if_changed(p, '{"x": 1}')
        os.utime(p, (1000, 1000))
        project_manager._write_text_if_changed(p, '{"x": 2}')  # different
        assert os.stat(p).st_mtime != 1000
        assert p.read_text(encoding="utf-8") == '{"x": 2}'

    def test_resave_unchanged_vision_keeps_designer_modify(
        self, tmp_path: Path
    ) -> None:
        # Regression: the persist funnel re-saving an unchanged vision.json on a
        # later turn must not make it newer than a Designer mock produced in
        # between (which previously flipped Designer to needs_update and the
        # downstream agent to not_ready).
        import os

        from spec4.app_constants import (
            STATE_AGENTIFIER_COMPLETE,
            STATE_REVIEW_COMPLETE,
            STATE_VISION_COMPLETE,
        )
        from spec4.session import _persist_artifacts

        session: dict[str, Any] = {
            "working_dir": str(tmp_path),
            "code_scanner_state": STATE_REVIEW_COMPLETE,
            "code_review": {"summary": "x"},
            "brainstormer_state": STATE_VISION_COMPLETE,
            "vision_statement": {"title": "ShelfLife"},
            "agentifier_state": STATE_AGENTIFIER_COMPLETE,
            "ai_features": {"features": []},
            "agentifier_catalog_done": True,
            "ai_catalog": {"catalog": []},
        }
        _persist_artifacts(session)
        version = session["phase_version"]
        base = tmp_path / ".spec4" / f"v{version}"

        # Pin upstream artifacts to a known-old time, then drop a newer mock.
        for rel in ("vision.json", "ai_features.json", "code_review.json"):
            os.utime(base / rel, (1000, 1000))
        design = base / "design"
        design.mkdir(parents=True, exist_ok=True)
        (design / "mock.html").write_text("<html>final</html>", encoding="utf-8")
        os.utime(design / "mock.html", (2000, 2000))

        # A later agent turn re-runs the funnel; vision is unchanged.
        _persist_artifacts(session)

        assert os.stat(base / "vision.json").st_mtime == 1000  # not bumped
        assert (
            project_manager.agent_button_state(str(tmp_path), "designer", session)
            == project_manager.AGENT_BTN_MODIFY
        )
        assert (
            project_manager.agent_button_state(str(tmp_path), "stack_advisor", session)
            == project_manager.AGENT_BTN_START
        )


class TestImplementedVersionHelpers:
    """latest_implemented_version / load_prior_vision underpin Brainstormer's
    revision mode: they identify the most recent *completed* round and read its
    vision as read-only reference, independent of any in-progress round above it.
    """

    def _implement(self, tmp_path: Path, version: int, vision: dict[str, Any]) -> None:
        project_manager.save_vision(str(tmp_path), vision, version)
        project_manager.get_version_dir(str(tmp_path), version).joinpath(
            "IMPLEMENTED"
        ).write_text("")

    def test_latest_implemented_none_when_no_versions(self, tmp_path: Path) -> None:
        assert project_manager.latest_implemented_version(str(tmp_path)) is None

    def test_latest_implemented_none_when_round_in_progress(
        self, tmp_path: Path
    ) -> None:
        # v0 exists but is not implemented (no marker).
        project_manager.save_vision(str(tmp_path), {"vision_statement": {}}, 0)
        assert project_manager.latest_implemented_version(str(tmp_path)) is None

    def test_latest_implemented_returns_highest_implemented(
        self, tmp_path: Path
    ) -> None:
        self._implement(tmp_path, 0, {"vision_statement": {"name": "A"}})
        self._implement(tmp_path, 1, {"vision_statement": {"name": "B"}})
        assert project_manager.latest_implemented_version(str(tmp_path)) == 1

    def test_latest_implemented_ignores_higher_in_progress_round(
        self, tmp_path: Path
    ) -> None:
        # v0 implemented, v1 started (review persisted) but not yet implemented.
        self._implement(tmp_path, 0, {"vision_statement": {"name": "A"}})
        project_manager.save_code_review(
            str(tmp_path), {"code_review": {"is_software_project": True}}, 1
        )
        assert project_manager.latest_phase_version(str(tmp_path)) == 1
        assert project_manager.latest_implemented_version(str(tmp_path)) == 0

    def test_load_prior_vision_returns_implemented_vision(
        self, tmp_path: Path
    ) -> None:
        vision = {"vision_statement": {"name": "Checkers"}}
        self._implement(tmp_path, 0, vision)
        assert project_manager.load_prior_vision(str(tmp_path)) == vision

    def test_load_prior_vision_none_without_implemented_round(
        self, tmp_path: Path
    ) -> None:
        assert project_manager.load_prior_vision(str(tmp_path)) is None

    def test_load_prior_vision_handles_bad_json(self, tmp_path: Path) -> None:
        version_dir = project_manager.get_version_dir(str(tmp_path), 0)
        version_dir.mkdir(parents=True)
        (version_dir / "vision.json").write_text("{not valid json")
        (version_dir / "IMPLEMENTED").write_text("")
        assert project_manager.load_prior_vision(str(tmp_path)) is None


class TestLoadPriorAiFeatures:
    """load_prior_ai_features reads the AI surface of the latest *implemented*
    round, underpinning Agentifier's revision mode (carry already-built features
    forward into a new round). It mirrors load_prior_vision but for ai_features.
    """

    def _implement_features(
        self, tmp_path: Path, version: int, features: dict[str, Any]
    ) -> None:
        project_manager.save_ai_features(str(tmp_path), features, version)
        project_manager.get_version_dir(str(tmp_path), version).joinpath(
            "IMPLEMENTED"
        ).write_text("")

    def test_none_when_no_versions(self, tmp_path: Path) -> None:
        assert project_manager.load_prior_ai_features(str(tmp_path)) is None

    def test_none_when_round_in_progress(self, tmp_path: Path) -> None:
        # v0 features saved but round not implemented (no marker).
        project_manager.save_ai_features(
            str(tmp_path), {"ai_features": [{"name": "a"}]}, 0
        )
        assert project_manager.load_prior_ai_features(str(tmp_path)) is None

    def test_returns_implemented_features(self, tmp_path: Path) -> None:
        feats = {"ai_features": [{"name": "expiry_prediction"}], "cross_cutting": {}}
        self._implement_features(tmp_path, 0, feats)
        assert project_manager.load_prior_ai_features(str(tmp_path)) == feats

    def test_ignores_higher_in_progress_round(self, tmp_path: Path) -> None:
        # v0 implemented; v1 started (features saved) but not yet implemented.
        self._implement_features(tmp_path, 0, {"ai_features": [{"name": "old"}]})
        project_manager.save_ai_features(
            str(tmp_path), {"ai_features": [{"name": "new"}]}, 1
        )
        assert project_manager.latest_phase_version(str(tmp_path)) == 1
        got = project_manager.load_prior_ai_features(str(tmp_path))
        assert got == {"ai_features": [{"name": "old"}]}

    def test_none_when_file_missing(self, tmp_path: Path) -> None:
        # Implemented round exists but never wrote ai_features.json.
        project_manager.save_vision(str(tmp_path), {"vision_statement": {}}, 0)
        project_manager.get_version_dir(str(tmp_path), 0).joinpath(
            "IMPLEMENTED"
        ).write_text("")
        assert project_manager.load_prior_ai_features(str(tmp_path)) is None

    def test_handles_bad_json(self, tmp_path: Path) -> None:
        version_dir = project_manager.get_version_dir(str(tmp_path), 0)
        version_dir.mkdir(parents=True)
        (version_dir / "ai_features.json").write_text("{not valid json")
        (version_dir / "IMPLEMENTED").write_text("")
        assert project_manager.load_prior_ai_features(str(tmp_path)) is None


class TestLoadPriorMock:
    """load_prior_mock reads the approved UI mock of the latest *implemented*
    round, underpinning Designer's revision mode (carry the prior look and feel
    forward as the baseline a revision's delta is applied onto). It mirrors
    load_prior_vision / load_prior_ai_features but for design/mock.html.
    """

    def _implement_mock(self, tmp_path: Path, version: int, html: str) -> None:
        design_dir = (
            project_manager.get_version_dir(str(tmp_path), version) / "design"
        )
        design_dir.mkdir(parents=True, exist_ok=True)
        (design_dir / "mock.html").write_text(html, encoding="utf-8")
        project_manager.get_version_dir(str(tmp_path), version).joinpath(
            "IMPLEMENTED"
        ).write_text("")

    def test_none_when_no_versions(self, tmp_path: Path) -> None:
        assert project_manager.load_prior_mock(str(tmp_path)) is None

    def test_none_when_round_in_progress(self, tmp_path: Path) -> None:
        # v0 mock saved but round not implemented (no marker).
        design_dir = project_manager.get_version_dir(str(tmp_path), 0) / "design"
        design_dir.mkdir(parents=True, exist_ok=True)
        (design_dir / "mock.html").write_text("<html><body>x</body></html>")
        assert project_manager.load_prior_mock(str(tmp_path)) is None

    def test_returns_implemented_mock(self, tmp_path: Path) -> None:
        html = "<!DOCTYPE html><html><body><h1>App</h1></body></html>"
        self._implement_mock(tmp_path, 0, html)
        assert project_manager.load_prior_mock(str(tmp_path)) == html

    def test_ignores_higher_in_progress_round(self, tmp_path: Path) -> None:
        # v0 implemented; v1 started (mock saved) but not yet implemented.
        self._implement_mock(tmp_path, 0, "<html><body>old</body></html>")
        d1 = project_manager.get_version_dir(str(tmp_path), 1) / "design"
        d1.mkdir(parents=True, exist_ok=True)
        (d1 / "mock.html").write_text("<html><body>new</body></html>")
        assert project_manager.latest_phase_version(str(tmp_path)) == 1
        assert (
            project_manager.load_prior_mock(str(tmp_path))
            == "<html><body>old</body></html>"
        )

    def test_none_when_mock_missing(self, tmp_path: Path) -> None:
        # Implemented round exists but Designer was skipped (no mock.html).
        project_manager.save_vision(str(tmp_path), {"vision_statement": {}}, 0)
        project_manager.get_version_dir(str(tmp_path), 0).joinpath(
            "IMPLEMENTED"
        ).write_text("")
        assert project_manager.load_prior_mock(str(tmp_path)) is None

    def test_none_when_mock_blank(self, tmp_path: Path) -> None:
        # A whitespace-only mock is treated as absent.
        self._implement_mock(tmp_path, 0, "   \n  ")
        assert project_manager.load_prior_mock(str(tmp_path)) is None


class TestLoadPriorStack:
    """load_prior_stack reads the stack spec of the latest *implemented* round,
    underpinning StackAdvisor's revision mode (carry the established stack forward
    as the baseline a revision's delta-scoped recommendations build on). It mirrors
    load_prior_vision / load_prior_ai_features but for stack.json.
    """

    def _implement_stack(
        self, tmp_path: Path, version: int, stack: dict[str, Any]
    ) -> None:
        project_manager.save_stack(str(tmp_path), stack, version)
        project_manager.get_version_dir(str(tmp_path), version).joinpath(
            "IMPLEMENTED"
        ).write_text("")

    def test_none_when_no_versions(self, tmp_path: Path) -> None:
        assert project_manager.load_prior_stack(str(tmp_path)) is None

    def test_none_when_round_in_progress(self, tmp_path: Path) -> None:
        # v0 stack saved but round not implemented (no marker).
        project_manager.save_stack(str(tmp_path), {"stack_spec": {"name": "X"}}, 0)
        assert project_manager.load_prior_stack(str(tmp_path)) is None

    def test_returns_implemented_stack(self, tmp_path: Path) -> None:
        stack = {"stack_spec": {"name": "App", "languages": ["Python"]}}
        self._implement_stack(tmp_path, 0, stack)
        assert project_manager.load_prior_stack(str(tmp_path)) == stack

    def test_ignores_higher_in_progress_round(self, tmp_path: Path) -> None:
        # v0 implemented; v1 started (stack saved) but not yet implemented.
        self._implement_stack(tmp_path, 0, {"stack_spec": {"name": "old"}})
        project_manager.save_stack(str(tmp_path), {"stack_spec": {"name": "new"}}, 1)
        assert project_manager.latest_phase_version(str(tmp_path)) == 1
        assert project_manager.load_prior_stack(str(tmp_path)) == {
            "stack_spec": {"name": "old"}
        }

    def test_none_when_stack_missing(self, tmp_path: Path) -> None:
        # Implemented round exists but StackAdvisor was skipped (no stack.json).
        project_manager.save_vision(str(tmp_path), {"vision_statement": {}}, 0)
        project_manager.get_version_dir(str(tmp_path), 0).joinpath(
            "IMPLEMENTED"
        ).write_text("")
        assert project_manager.load_prior_stack(str(tmp_path)) is None

    def test_none_when_stack_not_a_dict(self, tmp_path: Path) -> None:
        # A malformed (non-object) stack.json is treated as absent, not crashed on.
        version_dir = project_manager.ensure_version_dir(str(tmp_path), 0)
        (version_dir / "stack.json").write_text("[1, 2, 3]")
        version_dir.joinpath("IMPLEMENTED").write_text("")
        assert project_manager.load_prior_stack(str(tmp_path)) is None

class TestLoadPriorDeploymentPlan:
    """load_prior_deployment_plan reads the deployment plan of the latest
    *implemented* round, underpinning Deployer's revision mode (carry the
    established deployment forward as the baseline a revision's delta-scoped
    update builds on). It mirrors load_prior_mock — a string artifact, with a
    blank file treated as absent — but for deployment-plan.md.
    """

    def _implement_plan(self, tmp_path: Path, version: int, markdown: str) -> None:
        project_manager.save_deployment_plan(str(tmp_path), markdown, version)
        project_manager.get_version_dir(str(tmp_path), version).joinpath(
            "IMPLEMENTED"
        ).write_text("")

    def test_none_when_no_versions(self, tmp_path: Path) -> None:
        assert project_manager.load_prior_deployment_plan(str(tmp_path)) is None

    def test_none_when_round_in_progress(self, tmp_path: Path) -> None:
        # v0 plan saved but round not implemented (no marker).
        project_manager.save_deployment_plan(str(tmp_path), "# Plan\n\n## Steps\n", 0)
        assert project_manager.load_prior_deployment_plan(str(tmp_path)) is None

    def test_returns_implemented_plan(self, tmp_path: Path) -> None:
        md = "# Deployment Plan\n\n## Target\n\n- **Provider:** Fly.io\n"
        self._implement_plan(tmp_path, 0, md)
        assert project_manager.load_prior_deployment_plan(str(tmp_path)) == md

    def test_ignores_higher_in_progress_round(self, tmp_path: Path) -> None:
        # v0 implemented; v1 started (plan saved) but not yet implemented — the
        # prior loader must return v0's plan, not the active v1 one.
        self._implement_plan(tmp_path, 0, "# Old plan\n")
        project_manager.save_deployment_plan(str(tmp_path), "# New plan\n", 1)
        assert project_manager.latest_phase_version(str(tmp_path)) == 1
        assert (
            project_manager.load_prior_deployment_plan(str(tmp_path)) == "# Old plan\n"
        )

    def test_none_when_plan_missing(self, tmp_path: Path) -> None:
        # Implemented round exists but Deployer was skipped (no deployment-plan.md).
        project_manager.save_vision(str(tmp_path), {"vision_statement": {}}, 0)
        project_manager.get_version_dir(str(tmp_path), 0).joinpath(
            "IMPLEMENTED"
        ).write_text("")
        assert project_manager.load_prior_deployment_plan(str(tmp_path)) is None

    def test_none_when_plan_blank(self, tmp_path: Path) -> None:
        # A whitespace-only plan is treated as absent.
        self._implement_plan(tmp_path, 0, "   \n  ")
        assert project_manager.load_prior_deployment_plan(str(tmp_path)) is None


class TestProjectReadme:
    """save_readme / load_existing_readme manage the project README, the one
    Spec4 artifact that lives at the project **root** rather than under
    .spec4/v{N}/. save_readme routes through _write_text_if_changed (no-op on
    unchanged content); load_existing_readme is the baseline reader for
    Deployer's README authoring (blank/missing treated as absent)."""

    def test_save_writes_to_project_root(self, tmp_path: Path) -> None:
        project_manager.save_readme(str(tmp_path), "# My App\n\nOverview.\n")
        readme = tmp_path / "README.md"
        assert readme.exists()
        assert readme.read_text(encoding="utf-8") == (
            "# My App\n\nOverview.\n\n[Built with Spec4 AI](https://spec4.ai)\n"
        )
        # It does NOT land under .spec4.
        assert not (project_manager.get_spec4_dir(str(tmp_path)) / "README.md").exists()

    def test_save_overwrites_existing(self, tmp_path: Path) -> None:
        project_manager.save_readme(str(tmp_path), "# Old\n")
        project_manager.save_readme(str(tmp_path), "# New\n\nUpdated.\n")
        text = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert text == (
            "# New\n\nUpdated.\n\n[Built with Spec4 AI](https://spec4.ai)\n"
        )

    def test_attribution_is_the_closing_line(self, tmp_path: Path) -> None:
        project_manager.save_readme(str(tmp_path), "# App\n\nBody.\n")
        text = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert text.rstrip().endswith("[Built with Spec4 AI](https://spec4.ai)")

    def test_attribution_is_not_duplicated_on_re_save(self, tmp_path: Path) -> None:
        """Deployer updates a README in place, so a stamped one comes back in."""
        project_manager.save_readme(str(tmp_path), "# App\n\nBody.\n")
        stamped = (tmp_path / "README.md").read_text(encoding="utf-8")
        project_manager.save_readme(str(tmp_path), stamped)
        text = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert text.count("[Built with Spec4 AI](https://spec4.ai)") == 1

    def test_attribution_moves_to_the_bottom_when_content_follows_it(
        self, tmp_path: Path
    ) -> None:
        """A revision appends after the stamped baseline, displacing the line."""
        project_manager.save_readme(str(tmp_path), "# App\n\nBody.\n")
        stamped = (tmp_path / "README.md").read_text(encoding="utf-8")
        project_manager.save_readme(
            str(tmp_path), stamped + "\n## Deployment\n\nFly.io.\n"
        )
        text = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert text.count("[Built with Spec4 AI](https://spec4.ai)") == 1
        assert text.rstrip().endswith("[Built with Spec4 AI](https://spec4.ai)")
        assert "## Deployment" in text

    def test_attribution_not_added_to_blank_content(self, tmp_path: Path) -> None:
        project_manager.save_readme(str(tmp_path), "   \n")
        text = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert "Built with Spec4 AI" not in text

    def test_re_save_of_stamped_readme_preserves_mtime(self, tmp_path: Path) -> None:
        """Idempotence must keep the no-op write path intact."""
        project_manager.save_readme(str(tmp_path), "# App\n\nBody.\n")
        readme = tmp_path / "README.md"
        before = readme.stat().st_mtime_ns
        project_manager.save_readme(str(tmp_path), readme.read_text(encoding="utf-8"))
        assert readme.stat().st_mtime_ns == before

    def test_save_no_op_when_unchanged_preserves_mtime(self, tmp_path: Path) -> None:
        project_manager.save_readme(str(tmp_path), "# Title\n\nBody.\n")
        readme = tmp_path / "README.md"
        before = readme.stat().st_mtime_ns
        project_manager.save_readme(str(tmp_path), "# Title\n\nBody.\n")
        assert readme.stat().st_mtime_ns == before

    def test_load_none_when_absent(self, tmp_path: Path) -> None:
        assert project_manager.load_existing_readme(str(tmp_path)) is None

    def test_load_returns_content(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# App\n\nHello.\n", encoding="utf-8")
        assert project_manager.load_existing_readme(str(tmp_path)) == (
            "# App\n\nHello.\n"
        )

    def test_load_none_when_blank(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("   \n\n  ", encoding="utf-8")
        assert project_manager.load_existing_readme(str(tmp_path)) is None

    def test_load_reads_root_not_version_dir(self, tmp_path: Path) -> None:
        # A README placed under a version dir must NOT be picked up — the loader
        # reads the project root only.
        vdir = project_manager.ensure_version_dir(str(tmp_path), 0)
        (vdir / "README.md").write_text("# Wrong place\n", encoding="utf-8")
        assert project_manager.load_existing_readme(str(tmp_path)) is None


class TestPhaseSpecPreamble:
    """The verbatim spec preamble attached to each phase file (D-PS2/D-PS4).

    The phase files are the sole deliverable to the coding agent, so the Spec
    Drafter's output has to arrive through them. Specs resolve at render time
    from the context bundle, never from the phase dict.
    """

    @staticmethod
    def _catalog() -> dict[str, Any]:
        return {
            "ai_features": [
                {
                    "id": "vector_index",
                    "name": "vector_index",
                    "kind": "infrastructure",
                    "tier": "infrastructure",
                    "phase_priority": "steel_thread",
                    "requires": [],
                    "rough_description": "Enabling infrastructure (vector index).",
                },
                {
                    "id": "rag_answerer",
                    "name": "RAG Answerer",
                    "kind": "feature",
                    "tier": "rag",
                    "scope": "cross_feature",
                    "phase_priority": "mvp",
                    "requires": ["vector_index"],
                    "purpose": "Answer questions from the corpus.",
                    "inputs": [
                        {
                            "name": "question",
                            "type": "string",
                            "description": "the query",
                            "required": True,
                        }
                    ],
                    "failure_modes": [
                        {
                            "mode": "no hits",
                            "likelihood": "low",
                            "mitigation": "caveat the answer",
                        }
                    ],
                },
            ],
            "cross_cutting": {
                "provider_strategy": {"recommendation": "a strong general model"},
                "prompt_versioning": {"recommendation": "pin prompts per release"},
            },
        }

    @staticmethod
    def _phase(**overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "phase_number": 2,
            "total_phases": 2,
            "phase_title": "Grounded answers",
            "phase_summary": "Wire retrieval into the answer path.",
            "features": [
                {
                    "id": "rag_answerer",
                    "role": "introduced",
                    "scope_note": "Retrieval only; reranking lands later.",
                }
            ],
            "tech_stack_spec": {"dependencies": ["fastapi"], "configurations": "PORT"},
            "instructions": ["Implement the retrieval path."],
            "risk_assessment": {
                "potential_bottlenecks": "Cold index.",
                "mitigation_strategy": "Warm on boot.",
            },
            "verification": "Run pytest.",
        }
        base.update(overrides)
        return base

    def _render(self, **overrides: Any) -> str:
        return project_manager.render_phase_markdown(
            self._phase(**overrides), {"ai_features": self._catalog()}
        )

    def test_spec_body_reaches_the_phase_file(self) -> None:
        text = self._render()
        assert "## Feature Specifications" in text
        assert "Answer questions from the corpus." in text
        assert "`question`" in text
        assert "no hits" in text

    def test_preamble_precedes_instructions(self) -> None:
        text = self._render()
        assert text.index("## Feature Specifications") < text.index("## Instructions")

    def test_preamble_follows_the_summary(self) -> None:
        text = self._render()
        summary = text.index("Wire retrieval into the answer path.")
        assert summary < text.index("## Feature Specifications")

    def test_role_and_scope_note_are_rendered(self) -> None:
        text = self._render()
        assert "introduced in this phase" in text
        assert "Retrieval only; reranking lands later." in text

    def test_provider_strategy_is_excluded_from_phase_files(self) -> None:
        text = self._render()
        assert "a strong general model" not in text
        assert "pin prompts per release" in text

    def test_infrastructure_renders_as_substrate(self) -> None:
        text = self._render(
            features=[{"id": "vector_index", "role": "introduced", "scope_note": ""}]
        )
        assert "Enabling infrastructure" in text
        assert "substrate" in text

    def test_no_declared_features_yields_no_preamble(self) -> None:
        text = self._render(features=[])
        assert "## Feature Specifications" not in text
        # Cross-cutting rides with the specs, so it stays out too.
        assert "pin prompts per release" not in text

    def test_no_context_renders_without_a_preamble(self) -> None:
        text = project_manager.render_phase_markdown(self._phase())
        assert "## Feature Specifications" not in text
        assert "## Instructions" in text

    def test_unknown_id_is_skipped_rather_than_crashing(self) -> None:
        text = self._render(
            features=[{"id": "ghost", "role": "introduced", "scope_note": ""}]
        )
        assert "## Feature Specifications" not in text
        assert "## Instructions" in text

    def test_whole_spec_attaches_to_every_touching_phase(self) -> None:
        extended = self._render(
            phase_number=3,
            features=[
                {
                    "id": "rag_answerer",
                    "role": "extended",
                    "scope_note": "Reranking.",
                }
            ],
        )
        assert "Answer questions from the corpus." in extended
        assert "`question`" in extended
        assert "extended in this phase" in extended

    def test_frontmatter_round_trips_without_the_specs(self) -> None:
        phase = self._phase()
        text = project_manager.render_phase_markdown(
            phase, {"ai_features": self._catalog()}
        )
        parsed = project_manager.parse_phase_markdown(text)
        assert parsed == phase
        # The spec lives in the body only — never duplicated into frontmatter.
        head = text.split("---", 2)[1]
        assert "Answer questions from the corpus." not in head

    def test_budgets_and_eval_approach_never_reach_the_coder(self) -> None:
        """D-PS13: pre-stack vendor pricing must not render as authoritative."""
        catalog = self._catalog()
        catalog["ai_features"][1]["budgets"] = {
            "cost_per_call": "$0.00002 per 1K tokens (text-embedding-3-small)",
            "p95_latency": "800ms",
        }
        catalog["ai_features"][1]["eval_approach"] = {
            "offline": "Compare OpenAI text-embedding-3-small vs Cohere embed-v3.",
        }
        text = project_manager.render_phase_markdown(
            self._phase(), {"ai_features": catalog}
        )
        assert "text-embedding-3-small" not in text
        assert "Cohere" not in text
        assert "Budgets" not in text
        assert "Eval approach" not in text
        # The build contract survives intact.
        assert "Answer questions from the corpus." in text
        assert "no hits" in text

    def test_save_phases_threads_the_context(self, tmp_path: Any) -> None:
        project_manager.save_phases(
            tmp_path, [self._phase()], 0, {"ai_features": self._catalog()}
        )
        written = (
            project_manager.get_version_dir(tmp_path, 0) / "phases" / "phase2.md"
        ).read_text(encoding="utf-8")
        assert "Answer questions from the corpus." in written

    def test_no_attribution_directive_in_phase_files(self) -> None:
        # Phase files no longer ask the coding agent to stamp new files with a
        # Spec4 attribution line. The README footer (Deployer) is separate and
        # unaffected.
        for text in (
            self._render(),
            self._render(features=[]),
            project_manager.render_phase_markdown(self._phase()),
        ):
            assert "## Attribution" not in text
            assert "Built with Spec4" not in text
            assert "spec4.ai" not in text


class TestRenderPhaseStackRoutingAndNfr:
    """D-PH3/D-PH4: render-time deterministic joins in the phase body."""

    @staticmethod
    def _phase(**overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "phase_number": 1,
            "total_phases": 2,
            "phase_title": "Fare core",
            "phase_summary": "s",
            "features": [
                {"id": "fare_lookup", "role": "introduced", "scope_note": ""}
            ],
            "capabilities": [],
            "tech_stack_spec": {
                "dependencies": ["fastapi"],
                "configurations": "c",
            },
            "instructions": ["x"],
            "risk_assessment": {
                "potential_bottlenecks": "b",
                "mitigation_strategy": "m",
            },
            "verification": "Run tests.",
            "references": [],
        }
        base.update(overrides)
        return base

    @staticmethod
    def _context() -> dict[str, Any]:
        return {
            "ai_features": None,
            "feature_specs": {
                "features": [{"id": "fare_lookup"}],
                "nfr_goals": ["Lookups are fast.", "Works offline."],
            },
            "stack": {
                "stack_spec": {
                    "libraries": [
                        {"name": "FastAPI"},
                        {
                            "name": "React Hook Form",
                            "purpose": "Form state",
                            "serves_features": ["fare_lookup"],
                            "satisfies_nfr": ["nfr_lookups_are_fast_"],
                        },
                        {
                            "name": "vite-plugin-pwa",
                            "satisfies_nfr": ["nfr_works_offline_"],
                        },
                        {"name": "Playwright", "status": "deferred"},
                    ]
                }
            },
        }

    def test_routed_and_baseline_blocks_render_in_tech_stack(self) -> None:
        md = project_manager.render_phase_markdown(self._phase(), self._context())
        tech = md[md.index("## Tech Stack") : md.index("## Instructions")]
        assert "Approved stack for this phase's declared work" in tech
        assert (
            "- React Hook Form (libraries): Form state — serves `fare_lookup`"
            in tech
        )
        assert "Project-wide stack" in tech
        assert "- FastAPI" in tech
        assert "Playwright" not in tech  # deferred: neither routed nor baseline

    def test_served_nfr_threads_into_declaring_phase_verification(self) -> None:
        md = project_manager.render_phase_markdown(self._phase(), self._context())
        verification = md[md.index("## Verification") :]
        assert "Non-functional acceptance" in verification
        assert "`nfr_lookups_are_fast_`: Lookups are fast." in verification
        assert "delivered by React Hook Form" in verification
        # the global-only claim does not thread into a non-final phase
        assert "nfr_works_offline_" not in verification

    def test_global_claim_threads_into_final_phase_only(self) -> None:
        md = project_manager.render_phase_markdown(
            self._phase(phase_number=2, features=[]), self._context()
        )
        verification = md[md.index("## Verification") :]
        assert (
            "`nfr_works_offline_`: Works offline. — project-wide acceptance"
            in verification
        )
        assert "nfr_lookups_are_fast_" not in verification  # nothing declared

    def test_without_context_render_is_unchanged(self) -> None:
        md = project_manager.render_phase_markdown(self._phase(), None)
        assert "Approved stack" not in md
        assert "Project-wide stack" not in md
        assert "Non-functional acceptance" not in md

    def test_frontmatter_untouched_by_renderer_additions(self) -> None:
        phase = self._phase()
        md = project_manager.render_phase_markdown(phase, self._context())
        assert project_manager.parse_phase_markdown(md) == phase


class TestPreambleTwoAltitudesAndSurfaces:
    """D-PH5: product spec + UI surfaces + AI capability spec, in that order."""

    @staticmethod
    def _phase(**overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "phase_number": 1,
            "total_phases": 1,
            "phase_title": "T",
            "phase_summary": "s",
            "features": [
                {
                    "id": "thread_summarization",
                    "role": "introduced",
                    "scope_note": "API only",
                }
            ],
            "capabilities": [
                {
                    "id": "thread_summarization",
                    "role": "introduced",
                    "scope_note": "",
                }
            ],
            "tech_stack_spec": {"dependencies": [], "configurations": ""},
            "instructions": ["x"],
            "risk_assessment": {
                "potential_bottlenecks": "b",
                "mitigation_strategy": "m",
            },
            "verification": "v",
            "references": [],
        }
        base.update(overrides)
        return base

    @staticmethod
    def _context() -> dict[str, Any]:
        return {
            "ai_features": {
                "ai_features": [
                    {
                        "id": "thread_summarization",
                        "name": "Thread Summarization",
                        "purpose": "Summarize threads with AI.",
                        "vision_grounding": {
                            "served_features": [{"id": "thread_summarization"}]
                        },
                    }
                ],
                "cross_cutting": {
                    "observability": {"recommendation": "Trace every call."}
                },
            },
            "feature_specs": {
                "features": [
                    {
                        "id": "thread_summarization",
                        "name": "Thread Summarization",
                        "purpose": "Users get a summary of a pasted thread.",
                        "success_criteria": ["Summary matches thread"],
                        "dependencies": [],
                        "entities": ["EmailThread", "Summary"],
                    }
                ],
                "nfr_goals": [],
            },
            "manifest": {
                "surfaces": [
                    {
                        "name": "summary_view",
                        "kind": "ai",
                        "screen": "main",
                        "implements_feature_ids": ["thread_summarization"],
                        "catalog_surface_id": "thread_summarization",
                        "inputs": [{"name": "raw_thread"}],
                        "reads": ["EmailThread"],
                        "writes": ["Summary"],
                    },
                    {
                        "name": "history_panel",
                        "kind": "non_ai",
                        "screen": "main",
                        "implements_feature_ids": ["other_feature"],
                    },
                ]
            },
            "stack": None,
        }

    def _preamble(self, phase: dict[str, Any]) -> str:
        return "\n".join(
            project_manager._phase_spec_preamble(phase, self._context())
        )

    def test_both_altitudes_render_in_order_with_surfaces_between(self) -> None:
        text = self._preamble(self._phase())
        product = text.index("Thread Summarization — product feature")
        surfaces = text.index("UI surfaces for this phase")
        capability = text.index("Thread Summarization — AI capability")
        assert product < surfaces < capability
        assert "Users get a summary" in text  # behavioural spec
        assert "Summarize threads with AI." in text  # implementation spec
        assert "- entities: EmailThread, Summary" in text

    def test_serves_relation_stated_on_capability_block(self) -> None:
        text = self._preamble(self._phase())
        assert (
            "Serves product feature(s): `thread_summarization` "
            "(specified above)." in text
        )

    def test_surface_attaches_via_catalog_grouping(self) -> None:
        text = self._preamble(self._phase(features=[]))
        assert "realize the AI capability `thread_summarization`" in text
        assert "**`summary_view`**" in text
        assert "history_panel" not in text  # other feature undeclared

    def test_product_only_phase_gates_cross_cutting_out(self) -> None:
        text = self._preamble(self._phase(capabilities=[]))
        assert "product feature" in text
        assert "Trace every call." not in text

    def test_capability_phase_renders_cross_cutting(self) -> None:
        text = self._preamble(self._phase())
        assert "Trace every call." in text

    def test_scope_note_and_role_render_per_declaration(self) -> None:
        text = self._preamble(self._phase())
        assert "introduced in this phase" in text
        assert "*Scope for this phase: API only*" in text


class TestSessionIsBrownfield:
    """Only the developer's answer decides brownfield — never on-disk artifacts.

    Regression: `resolve_phase_version` used "a code review exists" as the
    proxy, so running CodeScanner over a greenfield skeleton pushed the first
    round into `v1`. Scanning a directory says nothing about whether the project
    pre-existed Spec4, which is the very reason D-PM1 asks the question.
    """

    def test_existing_is_brownfield(self) -> None:
        assert project_manager.session_is_brownfield({"project_mode": "existing"})

    def test_new_is_greenfield(self) -> None:
        assert not project_manager.session_is_brownfield({"project_mode": "new"})

    def test_unanswered_is_greenfield(self) -> None:
        assert not project_manager.session_is_brownfield({"project_mode": None})
        assert not project_manager.session_is_brownfield({})
        assert not project_manager.session_is_brownfield(None)

    def test_a_code_review_does_not_make_it_brownfield(self) -> None:
        session = {"project_mode": "new", "code_review": {"summary": "scanned"}}
        assert not project_manager.session_is_brownfield(session)

    def test_no_code_review_does_not_make_it_greenfield(self) -> None:
        session = {"project_mode": "existing", "code_review": None}
        assert project_manager.session_is_brownfield(session)


class TestGreenfieldScanStaysAtV0:
    """The reported bug, end to end through the persist funnel."""

    def _scanned(self, tmp_path: Path, mode: str | None) -> dict[str, Any]:
        from spec4.app_constants import STATE_REVIEW_COMPLETE
        from spec4.session import _default_session, _persist_artifacts

        session = {
            **_default_session(),
            "working_dir": str(tmp_path),
            "active_agent": "code_scanner",
            "project_mode": mode,
            "code_scanner_state": STATE_REVIEW_COMPLETE,
            "code_review": {"summary": "x"},
        }
        _persist_artifacts(session)
        return session

    def _version_dirs(self, tmp_path: Path) -> list[str]:
        return sorted(
            d.name
            for d in (tmp_path / ".spec4").iterdir()
            if d.is_dir() and d.name.startswith("v")
        )

    def test_greenfield_scan_writes_v0(self, tmp_path: Path) -> None:
        session = self._scanned(tmp_path, "new")
        assert session["phase_version"] == 0
        assert self._version_dirs(tmp_path) == ["v0"]

    def test_brownfield_scan_writes_v1(self, tmp_path: Path) -> None:
        session = self._scanned(tmp_path, "existing")
        assert session["phase_version"] == 1
        assert self._version_dirs(tmp_path) == ["v1"]

    def test_unanswered_scan_writes_v0(self, tmp_path: Path) -> None:
        """An empty directory is never asked, and is greenfield by definition."""
        session = self._scanned(tmp_path, None)
        assert session["phase_version"] == 0
        assert self._version_dirs(tmp_path) == ["v0"]

    def test_the_code_review_lands_in_that_round(self, tmp_path: Path) -> None:
        self._scanned(tmp_path, "new")
        assert (tmp_path / ".spec4" / "v0" / "code_review.json").exists()
