"""Lever 2a — feature_specs.json artifact + deterministic scaffold + plumbing.

Covers the deterministic scaffold builder (the floor the 2b generative pass
fills), its feature extraction, the Brainstormer completion-hook wiring that
stamps ``session['feature_specs']``, and the persistence round-trip
(save/load + ``load_spec4_artifacts`` + resume-hydrate).
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from spec4 import project_manager
from spec4.agents import brainstormer, feature_speccer
from spec4.agents._utils import slug
from spec4.app_constants import STATE_IN_PROGRESS, STATE_VISION_COMPLETE
from spec4.session import _default_session, _load_working_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(**overrides: Any) -> dict[str, Any]:
    session: dict[str, Any] = {
        "active_agent": "brainstormer",
        "working_dir": None,
        "code_review": None,
        "brainstormer_state": STATE_IN_PROGRESS,
        "brainstormer_messages": [],
        "vision_statement": None,
        "feature_specs": None,
        "llm_config": {"model": "test-model", "api_key": "test-key"},
    }
    session.update(overrides)
    return session


def _make_stream_chunk(content: str, finish_reason: str | None = None) -> MagicMock:
    chunk = MagicMock()
    chunk.choices[0].delta.content = content
    chunk.choices[0].delta.tool_calls = None
    chunk.choices[0].finish_reason = finish_reason
    return chunk


def _mock_stream(text: str) -> Any:
    chunks = [_make_stream_chunk(c) for c in text]
    chunks.append(_make_stream_chunk("", finish_reason="stop"))
    return patch("spec4.llm.litellm.completion", return_value=iter(chunks))


def _envelope(features: list[Any]) -> dict[str, Any]:
    return {
        "vision_statement": {
            "name": "App",
            "vision": {"purpose": "A thing.", "key_features_mvp": features},
        }
    }


# ---------------------------------------------------------------------------
# _vision_features()
# ---------------------------------------------------------------------------


class TestVisionFeatures:
    def test_canonical_entries(self) -> None:
        vision = _envelope(
            [
                {"AI Recs": {"description": "Personalized picks."}},
                {"Reviews": {"description": "User reviews."}},
            ]
        )
        assert feature_speccer._vision_features(vision) == [
            ("AI Recs", "Personalized picks."),
            ("Reviews", "User reviews."),
        ]

    def test_flat_shape(self) -> None:
        vision = _envelope([{"name": "Flat", "description": "d"}])
        assert feature_speccer._vision_features(vision) == [("Flat", "d")]

    def test_bare_string(self) -> None:
        vision = _envelope(["Just A Name"])
        assert feature_speccer._vision_features(vision) == [("Just A Name", "")]

    def test_missing_features_is_empty(self) -> None:
        assert feature_speccer._vision_features({"vision_statement": {}}) == []
        assert feature_speccer._vision_features({}) == []


# ---------------------------------------------------------------------------
# build_feature_specs() — deterministic scaffold
# ---------------------------------------------------------------------------


class TestBuildFeatureSpecs:
    def test_scaffold_shape(self) -> None:
        vision = _envelope(
            [{"Checkout Flow": {"description": "Buy things."}}]
        )
        fs = feature_speccer.build_feature_specs(vision)
        assert fs["version"] == feature_speccer.FEATURE_SPECS_VERSION
        assert fs["nfr_goals"] == []
        assert len(fs["features"]) == 1
        feat = fs["features"][0]
        assert feat["id"] == slug("Checkout Flow") == "checkout_flow"
        assert feat["name"] == "Checkout Flow"
        assert feat["purpose"] == "Buy things."
        # Behavioral fields present but empty until the 2b generative pass.
        assert feat["inputs"] == []
        assert feat["outputs"] == {}
        assert feat["success_criteria"] == []
        assert feat["failure_modes"] == []
        assert feat["dependencies"] == []
        assert feat["entities"] == []

    def test_ids_are_slugged_and_ordered(self) -> None:
        vision = _envelope(
            [
                {"Feature One": {"description": "a"}},
                {"Feature Two": {"description": "b"}},
            ]
        )
        fs = feature_speccer.build_feature_specs(vision)
        assert [f["id"] for f in fs["features"]] == ["feature_one", "feature_two"]

    def test_empty_vision_yields_no_features(self) -> None:
        fs = feature_speccer.build_feature_specs({"vision_statement": {}})
        assert fs["features"] == []
        assert fs["nfr_goals"] == []

    def test_accepts_llm_config_without_using_it(self) -> None:
        # 2a ignores llm_config; the parameter exists so 2b keeps the call site.
        vision = _envelope([{"F": {"description": "d"}}])
        with_cfg = feature_speccer.build_feature_specs(vision, {"model": "x"})
        without = feature_speccer.build_feature_specs(vision)
        assert with_cfg == without


# ---------------------------------------------------------------------------
# Brainstormer completion-hook wiring
# ---------------------------------------------------------------------------


class TestHookStampsFeatureSpecs:
    def test_completion_hook_builds_feature_specs(self) -> None:
        session = _make_session()
        vision_json = (
            '{"vision_statement": {"name": "TodoApp", "vision": '
            '{"purpose": "Track tasks.", "key_features_mvp": '
            '[{"Task List": {"description": "See tasks."}}]}}}'
        )
        response = f"Done.\n\n```json\n{vision_json}\n```"
        with _mock_stream(response):
            "".join(brainstormer.run("finalize", session, session["llm_config"]))

        assert session["brainstormer_state"] == STATE_VISION_COMPLETE
        fs = session["feature_specs"]
        assert fs is not None
        assert [f["id"] for f in fs["features"]] == ["task_list"]
        assert fs["features"][0]["purpose"] == "See tasks."


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    def _specs(self) -> dict[str, Any]:
        return {
            "version": 1,
            "features": [{"id": "f", "name": "F", "purpose": "p"}],
            "nfr_goals": ["sub-second search"],
        }

    def test_save_load_round_trip(self, tmp_path: Path) -> None:
        specs = self._specs()
        project_manager.save_feature_specs(tmp_path, specs, 0)
        assert project_manager.load_feature_specs(tmp_path) == specs

    def test_load_spec4_artifacts_includes_feature_specs(self, tmp_path: Path) -> None:
        specs = self._specs()
        project_manager.save_feature_specs(tmp_path, specs, 0)
        assert project_manager.load_spec4_artifacts(tmp_path)["feature_specs"] == specs

    def test_missing_feature_specs_loads_none(self, tmp_path: Path) -> None:
        # A version dir with only a vision must not error on the missing file.
        project_manager.save_vision(tmp_path, {"name": "X"}, 0)
        assert project_manager.load_feature_specs(tmp_path) is None
        assert project_manager.load_spec4_artifacts(tmp_path)["feature_specs"] is None

    def test_restore_hydrates_feature_specs(self, tmp_path: Path) -> None:
        project_manager.save_vision(tmp_path, {"name": "X"}, 0)
        project_manager.save_feature_specs(tmp_path, self._specs(), 0)
        session = _default_session()
        session["provider"] = "openai"
        session["api_key"] = "sk-test"
        session = _load_working_dir(str(tmp_path), session)
        assert session["feature_specs"] == self._specs()
