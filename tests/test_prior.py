"""CodeScanner v2 step 1d: the ``prior_round`` block.

Covers ``code_scanner._prior`` on the trimmed BWS4 v7 and v8 round
directories under ``tests/golden/fixtures/rounds/`` (Spec4's own output,
reduced to the fields the extract reads): which round is read, what each
artifact reduces to, the one catalog exception, and the schema.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
from typing import Any
from unittest.mock import patch

from spec4.agents._code_review_schema import validate_code_review
from spec4.agents.code_scanner import _collect, _prior
from spec4.agents.code_scanner._scan import SampleRecord
from tests._golden import FIXTURE_DIR
from tests._review_helpers import review_envelope

_ROUNDS = FIXTURE_DIR / "rounds"


def install_rounds(root: pathlib.Path, *versions: int) -> pathlib.Path:
    """Copy the trimmed ``v{N}`` round fixtures into ``root/.spec4/``."""
    spec4 = root / ".spec4"
    for v in versions:
        shutil.copytree(_ROUNDS / f"v{v}", spec4 / f"v{v}")
    return spec4


def _block(root: pathlib.Path) -> dict[str, Any]:
    block = _prior.prior_round_block(str(root))
    assert block is not None
    return block


class TestWhichRound:
    def test_no_implemented_round_is_no_block(self, tmp_path: pathlib.Path) -> None:
        assert _prior.prior_round_block(str(tmp_path)) is None
        spec4 = install_rounds(tmp_path, 8)
        (spec4 / "v8" / "IMPLEMENTED").unlink()
        assert _prior.prior_round_block(str(tmp_path)) is None

    def test_latest_implemented_round_not_the_latest_directory(
        self, tmp_path: pathlib.Path
    ) -> None:
        spec4 = install_rounds(tmp_path, 7, 8)
        (spec4 / "v9").mkdir()
        (spec4 / "v9" / "stack.json").write_text('{"stack_spec": {"libraries": []}}')
        block = _block(tmp_path)
        assert block["version"] == 8
        assert len(block["stack"]["libraries"]) == 36

    def test_implemented_is_the_marker_mtime(self, tmp_path: pathlib.Path) -> None:
        spec4 = install_rounds(tmp_path, 8)
        os.utime(spec4 / "v8" / "IMPLEMENTED", (1_759_361_422, 1_759_361_422))
        assert _block(tmp_path)["implemented"] == "2025-10-01T23:30:22+00:00"
        assert _prior._implemented_at(tmp_path / "nowhere") is None

    def test_artifacts_present_names_what_the_directory_holds(
        self, tmp_path: pathlib.Path
    ) -> None:
        install_rounds(tmp_path, 7)
        assert _block(tmp_path)["artifacts_present"] == [
            "phases",
            "stack",
            "vision",
            "feature_specs",
            "ai_features",
            "ai_catalog",
            "design",
            "code_review",
        ]
        shutil.rmtree(tmp_path / ".spec4")
        install_rounds(tmp_path, 8)
        present = _block(tmp_path)["artifacts_present"]
        assert "deployment_plan" in present
        assert "ai_features" not in present
        assert "design" not in present

    def test_an_empty_directory_is_not_present(self, tmp_path: pathlib.Path) -> None:
        spec4 = install_rounds(tmp_path, 8)
        (spec4 / "v8" / "design").mkdir()
        present = _block(tmp_path)["artifacts_present"]
        assert "design" not in present
        assert "phases" in present


class TestOneVersionOneDirectory:
    def test_missing_files_are_null_never_another_round(
        self, tmp_path: pathlib.Path
    ) -> None:
        # D-SC1d-3: v8 has no catalog of its own; everything else must come
        # from v8 even though v7 has every artifact.
        spec4 = install_rounds(tmp_path, 7, 8)
        (spec4 / "v8" / "stack.json").unlink()
        (spec4 / "v8" / "vision.json").unlink()
        (spec4 / "v8" / "feature_specs.json").unlink()
        (spec4 / "v8" / "code_review.json").unlink()
        shutil.rmtree(spec4 / "v8" / "phases")
        block = _block(tmp_path)
        assert block["version"] == 8
        assert block["stack"] is None
        assert block["vision"] is None
        assert block["feature_specs"] is None
        assert block["review"] is None
        assert block["phases"] == []
        assert block["artifacts_present"] == ["deployment_plan"]

    def test_catalog_falls_back_to_the_newest_implemented_round_with_one(
        self, tmp_path: pathlib.Path
    ) -> None:
        install_rounds(tmp_path, 7, 8)
        block = _block(tmp_path)
        assert block["version"] == 8
        assert block["capabilities_from_version"] == 7
        assert [c["id"] for c in block["capabilities"]][:2] == [
            "rag_example_app",
            "custom_text_semantic_placement",
        ]
        assert block["capabilities"][0] == {
            "id": "rag_example_app",
            "kind": "feature",
            "tier": "rag",
            "introduced_in_version": 0,
            "linked_vision_features": ["rag_example_app"],
            "requires": [
                "chunking_pipeline",
                "retriever",
                "embedding_pipeline",
                "vector_index",
            ],
        }

    def test_no_catalog_anywhere(self, tmp_path: pathlib.Path) -> None:
        install_rounds(tmp_path, 8)
        block = _block(tmp_path)
        assert block["capabilities"] == []
        assert block["capabilities_from_version"] is None

    def test_unimplemented_round_is_not_a_catalog_source(
        self, tmp_path: pathlib.Path
    ) -> None:
        spec4 = install_rounds(tmp_path, 7, 8)
        (spec4 / "v7" / "IMPLEMENTED").unlink()
        block = _block(tmp_path)
        assert block["capabilities"] == []
        assert block["capabilities_from_version"] is None

    def test_catalog_nodes_without_an_id_are_skipped(self) -> None:
        nodes = [1, {"name": "no id"}, {"id": "ok", "kind": 3, "requires": "x"}]
        assert _prior.capabilities_extract({"ai_features": nodes}) == [
            {
                "id": "ok",
                "kind": None,
                "tier": None,
                "introduced_in_version": None,
                "linked_vision_features": [],
                "requires": [],
            }
        ]
        assert _prior.capabilities_extract({"ai_features": "x"}) == []

    def test_unreadable_catalog_is_empty(self, tmp_path: pathlib.Path) -> None:
        spec4 = install_rounds(tmp_path, 7)
        (spec4 / "v7" / "ai_features.json").write_text("{")
        block = _block(tmp_path)
        assert block["capabilities"] == []
        assert block["capabilities_from_version"] is None


class TestPhases:
    def test_frontmatter_reduced_to_ids_shape_and_clipped_prose(
        self, tmp_path: pathlib.Path
    ) -> None:
        install_rounds(tmp_path, 8)
        phases = _block(tmp_path)["phases"]
        assert [p["number"] for p in phases] == [1, 2, 3, 4, 5, 6]
        first = phases[0]
        assert first["title"].startswith("Integration Thread")
        assert first["features"] == [
            {"id": "self_hosted_deployment", "role": "introduced"},
            {"id": "shared_framework_services", "role": "introduced"},
        ]
        assert first["capabilities"] == []
        assert "Python 3.12" in first["dependencies"]
        assert "systemd" not in first["dependencies"]
        assert len(first["summary"]) <= _prior._MAX_PHASE_TEXT_CHARS
        assert len(first["verification"]) <= _prior._MAX_PHASE_TEXT_CHARS
        assert set(first) == {
            "number",
            "title",
            "summary",
            "verification",
            "features",
            "capabilities",
            "dependencies",
        }

    def test_capabilities_join_to_catalog_ids(self, tmp_path: pathlib.Path) -> None:
        install_rounds(tmp_path, 7)
        block = _block(tmp_path)
        declared = {c["id"] for p in block["phases"] for c in p["capabilities"]}
        assert "react_search_loop" in declared
        roles = {c["role"] for p in block["phases"] for c in p["capabilities"]}
        assert roles == {"introduced", "extended"}

    def test_bare_string_declarations_have_no_role(self) -> None:
        extract = _prior.phase_extract(
            {"phase_number": 2, "features": ["a", {"id": "b"}, {"role": "x"}, 3]}
        )
        assert extract["features"] == [
            {"id": "a", "role": None},
            {"id": "b", "role": None},
        ]
        assert extract["number"] == 2
        assert extract["dependencies"] == []

    def test_a_phase_without_frontmatter_is_skipped_and_order_is_numeric(
        self, tmp_path: pathlib.Path
    ) -> None:
        spec4 = install_rounds(tmp_path, 8)
        phases = spec4 / "v8" / "phases"
        (phases / "phase3.md").write_text("# No frontmatter\n")
        (phases / "phase10.md").write_text('---\n{"phase_number": 10}\n---\n')
        (phases / "notes.md").write_text('---\n{"phase_number": 99}\n---\n')
        numbers = [p["number"] for p in _block(tmp_path)["phases"]]
        assert numbers == [1, 2, 4, 5, 6, 10]

    def test_an_unreadable_phase_file_is_skipped(self, tmp_path: pathlib.Path) -> None:
        install_rounds(tmp_path, 8)
        real = _prior._read_text

        def _read(path: pathlib.Path) -> str | None:
            return None if path.name == "phase2.md" else real(path)

        with patch.object(_prior, "_read_text", _read):
            numbers = [p["number"] for p in _block(tmp_path)["phases"]]
        assert numbers == [1, 3, 4, 5, 6]

    def test_phase_cap(self, tmp_path: pathlib.Path) -> None:
        install_rounds(tmp_path, 8)
        with patch.object(_prior, "_MAX_PHASES", 2):
            assert [p["number"] for p in _block(tmp_path)["phases"]] == [1, 2]


class TestStackVisionSpecs:
    def test_stack_names_and_kinds(self, tmp_path: pathlib.Path) -> None:
        install_rounds(tmp_path, 8)
        stack = _block(tmp_path)["stack"]
        assert stack["languages"] == [
            {"name": "Python", "version": "3.12"},
            {"name": "TypeScript", "version": "5.9"},
        ]
        assert {"name": "PydanticAI", "category": "agent framework"} in stack[
            "libraries"
        ]
        assert stack["deployment_targets"] == [
            {"name": "web_client", "kind": "spa"},
            {"name": "api", "kind": "rest_api"},
        ]
        assert stack["persistence_primary"] == "Neon (serverless Postgres) + pgvector"
        assert stack["provider_names"] == [
            "OpenRouter (via LiteLLM)",
            "OpenRouter (via PydanticAI)",
        ]
        assert "process_supervision" in stack["infrastructure_keys"]
        assert stack["integrations"][0] == {
            "name": "Exa Search API",
            "kind": "third_party_api",
        }

    def test_stack_extract_tolerates_bare_and_odd_shapes(self) -> None:
        bare = _prior.stack_extract(
            {"libraries": ["x", {"name": "y"}], "persistence": 3}
        )
        assert bare["libraries"] == [{"name": "y", "category": None}]
        assert bare["persistence_primary"] is None
        assert _prior.stack_extract({"stack_spec": "nope"})["languages"] == []
        primary = _prior.stack_extract({"persistence": {"primary_store": "SQLite"}})
        assert primary["persistence_primary"] == "SQLite"

    def test_vision_ids_and_revision_count(self, tmp_path: pathlib.Path) -> None:
        install_rounds(tmp_path, 8)
        vision = _block(tmp_path)["vision"]
        assert vision["name"] == "Built with Spec4 (BWS4)"
        assert vision["revision_count"] == 8
        assert vision["feature_ids"][0] == "landing_page"
        assert vision["feature_ids"][-1] == "self_hosted_deployment"
        assert len(vision["feature_ids"]) == 12

    def test_vision_feature_id_shapes(self) -> None:
        vision = {
            "vision_statement": {
                "name": "X",
                "vision": {
                    "key_features_mvp": [
                        {"Bare Name": {}},
                        {"With Id": {"id": "given"}},
                        {"name": "Flat", "id": "flat_id"},
                        {"name": "Flat No Id"},
                        "Just A String",
                        7,
                    ]
                },
            }
        }
        assert _prior.vision_extract(vision)["feature_ids"] == [
            "bare_name",
            "given",
            "flat_id",
            "flat_no_id",
            "just_a_string",
        ]
        flat = {"name": "Y", "key_features_mvp": ["A"]}
        assert _prior.vision_extract(flat) == {
            "name": "Y",
            "feature_ids": ["a"],
            "revision_count": 0,
        }

    def test_feature_specs(self, tmp_path: pathlib.Path) -> None:
        install_rounds(tmp_path, 7)
        specs = _block(tmp_path)["feature_specs"]
        assert specs["version"] == 1
        assert len(specs["feature_ids"]) == 11
        assert "react_loop_example_app" in specs["feature_ids"]

    def test_malformed_artifact_is_null(self, tmp_path: pathlib.Path) -> None:
        spec4 = install_rounds(tmp_path, 8)
        (spec4 / "v8" / "vision.json").write_text("[1, 2]")
        (spec4 / "v8" / "stack.json").write_text("not json")
        block = _block(tmp_path)
        assert block["vision"] is None
        assert block["stack"] is None
        assert block["feature_specs"] is not None


class TestReview:
    def test_v1_review_by_reference_with_its_extract(
        self, tmp_path: pathlib.Path
    ) -> None:
        install_rounds(tmp_path, 8)
        review = _block(tmp_path)["review"]
        assert review["path"] == ".spec4/v8/code_review.json"
        assert review["schema_version"] == 1
        assert (
            review["bytes"] == (tmp_path / ".spec4/v8/code_review.json").stat().st_size
        )
        assert review["project_type"].startswith("full-stack web application")
        assert set(review["commands"]) == {
            "build",
            "test",
            "lint",
            "typecheck",
            "run",
            "dev",
        }
        assert review["deployment"] == [{"kind": "paas", "name": "render"}]
        assert "pydantic-ai" in review["dependency_names"]
        assert "@tanstack/react-query" in review["dependency_names"]

    def test_v2_review_reads_the_review_layer(self, tmp_path: pathlib.Path) -> None:
        spec4 = install_rounds(tmp_path, 8)
        envelope = review_envelope(
            project_type="cli",
            commands={"test": "pytest", "deploy": 3},
            deployment={
                "containerization": {"tool": "docker"},
                "iac": {"path": "infra/"},
                "paas": "render",
            },
            dependencies=[{"name": "click"}, "typer", {"purpose": "x"}],
        )
        (spec4 / "v8" / "code_review.json").write_text(json.dumps(envelope))
        review = _block(tmp_path)["review"]
        assert review["schema_version"] == 2
        assert review["project_type"] == "cli"
        assert review["commands"] == {"test": "pytest"}
        assert review["deployment"] == [
            {"kind": "containerization", "name": "docker"},
            {"kind": "iac", "name": None},
        ]
        assert review["dependency_names"] == ["click", "typer"]

    def test_bytes_count_the_file_and_odd_deployment_is_empty(
        self, tmp_path: pathlib.Path
    ) -> None:
        spec4 = install_rounds(tmp_path, 8)
        path = spec4 / "v8" / "code_review.json"
        envelope = review_envelope(deployment="render", commands="make")
        path.write_text(json.dumps(envelope) + "\n")
        review = _block(tmp_path)["review"]
        assert review["bytes"] == path.stat().st_size
        assert review["deployment"] == []
        assert review["commands"] == {}

    def test_unreadable_or_unwrapped_review_is_null(
        self, tmp_path: pathlib.Path
    ) -> None:
        spec4 = install_rounds(tmp_path, 8)
        path = spec4 / "v8" / "code_review.json"
        path.write_text('{"review": {}}')
        assert _block(tmp_path)["review"] is None
        path.write_text("{")
        assert _block(tmp_path)["review"] is None
        path.write_text("[]")
        assert _block(tmp_path)["review"] is None
        path.unlink()
        assert _block(tmp_path)["review"] is None


class TestSchema:
    def test_the_block_validates_in_a_collected_scan(
        self, tmp_path: pathlib.Path
    ) -> None:
        install_rounds(tmp_path, 7, 8)
        scan = _collect.collect_scan(str(tmp_path), [], SampleRecord(), None)
        assert scan["prior_round"]["version"] == 8
        assert validate_code_review(review_envelope(scan=scan)) == []

    def test_the_block_is_closed(self, tmp_path: pathlib.Path) -> None:
        install_rounds(tmp_path, 8)
        scan = _collect.collect_scan(str(tmp_path), [], SampleRecord(), None)
        scan["prior_round"]["phases"][0]["instructions"] = []
        errors = validate_code_review(review_envelope(scan=scan))
        assert errors
        assert any("instructions" in e for e in errors)

    def test_without_an_implemented_round_the_block_is_absent(
        self, tmp_path: pathlib.Path
    ) -> None:
        scan = _collect.collect_scan(str(tmp_path), [], SampleRecord(), None)
        assert "prior_round" not in scan
        assert "plan_drift" not in scan
        assert "dependencies" in scan
