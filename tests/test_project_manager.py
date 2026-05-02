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
            "deployment": None,
        }

    def test_loads_vision(self, tmp_path: Path) -> None:
        vision = {"name": "App", "vision": "desc"}
        project_manager.save_vision(tmp_path, vision)
        assert project_manager.load_spec4_artifacts(tmp_path)["vision"] == vision

    def test_loads_stack(self, tmp_path: Path) -> None:
        stack = {"language": "Python"}
        project_manager.save_stack(tmp_path, stack)
        assert project_manager.load_spec4_artifacts(tmp_path)["stack"] == stack

    def test_loads_code_review(self, tmp_path: Path) -> None:
        review = {"code_review": {"is_software_project": True}}
        project_manager.save_code_review(tmp_path, review)
        assert project_manager.load_spec4_artifacts(tmp_path)["code_review"] == review

    def test_loads_phases_in_order(self, tmp_path: Path) -> None:
        phases = [
            {"phase_number": 2, "phase_title": "Auth"},
            {"phase_number": 1, "phase_title": "Steel Thread"},
        ]
        project_manager.save_phases(tmp_path, phases)
        result = project_manager.load_spec4_artifacts(tmp_path)["phases"]
        assert len(result) == 2
        assert result[0]["phase_number"] == 1

    def test_ignores_invalid_json_files(self, tmp_path: Path) -> None:
        spec4_dir = project_manager.ensure_spec4_dir(tmp_path)
        (spec4_dir / "vision.json").write_text("not valid json {{")
        result = project_manager.load_spec4_artifacts(tmp_path)
        assert result["vision"] is None

    def test_ignores_invalid_phase_json(self, tmp_path: Path) -> None:
        spec4_dir = project_manager.ensure_spec4_dir(tmp_path)
        phases_dir = spec4_dir / "phases"
        phases_dir.mkdir()
        (phases_dir / "phase1.json").write_text("bad json")
        result = project_manager.load_spec4_artifacts(tmp_path)
        assert result["phases"] == []


class TestSaveArtifacts:
    def test_save_vision_writes_json_file(self, tmp_path: Path) -> None:
        vision = {"name": "MyApp"}
        project_manager.save_vision(tmp_path, vision)
        path = tmp_path / ".spec4" / "vision.json"
        assert path.exists()
        assert json.loads(path.read_text()) == vision

    def test_save_stack_writes_json_file(self, tmp_path: Path) -> None:
        stack = {"language": "Python"}
        project_manager.save_stack(tmp_path, stack)
        path = tmp_path / ".spec4" / "stack.json"
        assert path.exists()
        assert json.loads(path.read_text()) == stack

    def test_save_code_review_writes_json_file(self, tmp_path: Path) -> None:
        review: dict[str, Any] = {"code_review": {}}
        project_manager.save_code_review(tmp_path, review)
        path = tmp_path / ".spec4" / "code_review.json"
        assert path.exists()
        assert json.loads(path.read_text()) == review

    def test_save_phases_writes_individual_files(self, tmp_path: Path) -> None:
        phases = [
            {"phase_number": 1, "phase_title": "A"},
            {"phase_number": 2, "phase_title": "B"},
        ]
        project_manager.save_phases(tmp_path, phases)
        assert (tmp_path / ".spec4" / "phases" / "phase1.json").exists()
        assert (tmp_path / ".spec4" / "phases" / "phase2.json").exists()

    def test_save_creates_spec4_dir_if_missing(self, tmp_path: Path) -> None:
        project_manager.save_vision(tmp_path, {"name": "App"})
        assert (tmp_path / ".spec4").is_dir()


class TestSpecmem:
    def test_read_missing_returns_none(self, tmp_path: Path) -> None:
        assert project_manager.read_specmem(tmp_path) is None

    def test_write_and_read_roundtrip(self, tmp_path: Path) -> None:
        project_manager.write_specmem(tmp_path, "# Notes\nContent here")
        assert project_manager.read_specmem(tmp_path) == "# Notes\nContent here"

    def test_update_creates_planning_state_section(self, tmp_path: Path) -> None:
        session: dict[str, Any] = {
            "vision_statement": {"name": "App"},
            "stack_statement": None,
            "phases": [],
        }
        project_manager.update_specmem_planning_state(tmp_path, session)
        content = project_manager.read_specmem(tmp_path)
        assert content is not None
        assert "Spec4 Planning State" in content
        assert "App" in content

    def test_update_preserves_existing_content(self, tmp_path: Path) -> None:
        project_manager.write_specmem(tmp_path, "# My Notes\nKeep this.")
        session: dict[str, Any] = {
            "vision_statement": {"name": "App"},
            "stack_statement": None,
            "phases": [],
        }
        project_manager.update_specmem_planning_state(tmp_path, session)
        content = project_manager.read_specmem(tmp_path)
        assert content is not None
        assert "Keep this." in content

    def test_update_replaces_existing_planning_section(self, tmp_path: Path) -> None:
        s1: dict[str, Any] = {
            "vision_statement": {"name": "V1"},
            "stack_statement": None,
            "phases": [],
        }
        project_manager.update_specmem_planning_state(tmp_path, s1)
        s2: dict[str, Any] = {
            "vision_statement": {"name": "V2"},
            "stack_statement": None,
            "phases": [],
        }
        project_manager.update_specmem_planning_state(tmp_path, s2)
        content = project_manager.read_specmem(tmp_path)
        assert content is not None
        assert content.count("Spec4 Planning State") == 1
        assert "V2" in content
        assert "V1" not in content

    def test_update_includes_stack(self, tmp_path: Path) -> None:
        session: dict[str, Any] = {
            "vision_statement": None,
            "stack_statement": {"language": "Python"},
            "phases": [],
        }
        project_manager.update_specmem_planning_state(tmp_path, session)
        content = project_manager.read_specmem(tmp_path)
        assert content is not None
        assert "Python" in content

    def test_update_includes_phases_summary(self, tmp_path: Path) -> None:
        session: dict[str, Any] = {
            "vision_statement": None,
            "stack_statement": None,
            "phases": [{"phase_number": 1, "phase_title": "Steel Thread"}],
        }
        project_manager.update_specmem_planning_state(tmp_path, session)
        content = project_manager.read_specmem(tmp_path)
        assert content is not None
        assert "Phases (1 total)" in content
        assert "Steel Thread" in content
