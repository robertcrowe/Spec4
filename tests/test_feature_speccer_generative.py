"""Lever 2b — generative enrichment, normalisation, DAG pruning, render, hook.

The generative call is mocked (Robert draws live). Covers the merge of the
model's judgment fields onto the code-owned scaffold, deterministic dependency
pruning to a DAG, fallback-to-scaffold on any failure, the compact review
render, and the Brainstormer completion-hook wiring end to end.
"""

import json
from typing import Any
from unittest.mock import MagicMock, patch

from spec4.agents import brainstormer, feature_speccer
from spec4.app_constants import STATE_IN_PROGRESS, STATE_VISION_COMPLETE


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


def _envelope(features: list[Any]) -> dict[str, Any]:
    return {
        "vision_statement": {
            "name": "ShopApp",
            "vision": {
                "purpose": "Buy things online.",
                "ui_surface": "Web app",
                "target_audience": ["shoppers"],
                "key_features_mvp": features,
            },
        }
    }


def _two_feature_vision() -> dict[str, Any]:
    return _envelope(
        [
            {"Auth": {"description": "Sign in."}},
            {"Checkout": {"description": "Pay for a cart."}},
        ]
    )


def _complete_returning(payload: Any) -> Any:
    resp = MagicMock()
    text = payload if isinstance(payload, str) else json.dumps(payload)
    resp.choices[0].message.content = f"```json\n{text}\n```"
    return patch("spec4.llm.complete", return_value=resp)


def _stream_chunk(content: str, finish_reason: str | None = None) -> MagicMock:
    chunk = MagicMock()
    chunk.choices[0].delta.content = content
    chunk.choices[0].delta.tool_calls = None
    chunk.choices[0].finish_reason = finish_reason
    return chunk


def _mock_stream(text: str) -> Any:
    chunks = [_stream_chunk(c) for c in text]
    chunks.append(_stream_chunk("", finish_reason="stop"))
    return patch("spec4.llm.litellm.completion", return_value=iter(chunks))


def _scaffold(*names: str) -> list[dict[str, Any]]:
    return [feature_speccer._scaffold_feature(n, f"{n} desc") for n in names]


# ---------------------------------------------------------------------------
# Generative enrichment
# ---------------------------------------------------------------------------


class TestEnrichment:
    def test_enriches_scaffold_fields(self) -> None:
        payload = {
            "features": [
                {
                    "id": "auth",
                    "purpose": "Authenticate users.",
                    "invocation": {"trigger": "User opens the app."},
                    "inputs": [
                        {
                            "name": "credentials",
                            "type": "text",
                            "description": "email + password",
                            "required": True,
                        }
                    ],
                    "outputs": {"primary": "a session", "format": "token"},
                    "success_criteria": ["valid users get in"],
                    "failure_modes": [
                        {"mode": "wrong password", "likelihood": "high",
                         "mitigation": "clear error"}
                    ],
                    "dependencies": [],
                    "entities": ["User", "Session"],
                },
                {
                    "id": "checkout",
                    "purpose": "Take payment.",
                    "dependencies": ["auth"],
                    "entities": ["Order"],
                },
            ],
            "nfr_goals": ["sub-second page loads"],
        }
        with _complete_returning(payload):
            fs = feature_speccer.build_feature_specs(
                _two_feature_vision(), {"model": "x"}
            )
        auth = fs["features"][0]
        assert auth["id"] == "auth"
        assert auth["purpose"] == "Authenticate users."
        assert auth["invocation"] == {"trigger": "User opens the app."}
        assert auth["inputs"][0]["name"] == "credentials"
        assert auth["inputs"][0]["required"] is True
        assert auth["outputs"] == {"primary": "a session", "format": "token"}
        assert auth["success_criteria"] == ["valid users get in"]
        assert auth["failure_modes"][0]["mode"] == "wrong password"
        assert auth["entities"] == ["User", "Session"]
        checkout = fs["features"][1]
        assert checkout["dependencies"] == ["auth"]
        assert fs["nfr_goals"] == ["sub-second page loads"]

    def test_preserves_scaffold_order_and_ids(self) -> None:
        payload = {"features": [{"id": "checkout"}, {"id": "auth"}], "nfr_goals": []}
        with _complete_returning(payload):
            fs = feature_speccer.build_feature_specs(
                _two_feature_vision(), {"model": "x"}
            )
        assert [f["id"] for f in fs["features"]] == ["auth", "checkout"]

    def test_ignores_hallucinated_ids(self) -> None:
        payload = {
            "features": [
                {"id": "auth", "purpose": "real"},
                {"id": "ghost", "purpose": "not a real feature"},
            ],
            "nfr_goals": [],
        }
        with _complete_returning(payload):
            fs = feature_speccer.build_feature_specs(
                _two_feature_vision(), {"model": "x"}
            )
        assert [f["id"] for f in fs["features"]] == ["auth", "checkout"]
        assert fs["features"][0]["purpose"] == "real"

    def test_purpose_falls_back_to_scaffold_when_blank(self) -> None:
        payload = {"features": [{"id": "auth", "purpose": ""}], "nfr_goals": []}
        with _complete_returning(payload):
            fs = feature_speccer.build_feature_specs(
                _envelope([{"Auth": {"description": "Sign in."}}]), {"model": "x"}
            )
        assert fs["features"][0]["purpose"] == "Sign in."


# ---------------------------------------------------------------------------
# Coercion of malformed model output
# ---------------------------------------------------------------------------


class TestCoercion:
    def test_bad_shapes_are_coerced(self) -> None:
        payload = {
            "features": [
                {
                    "id": "auth",
                    "inputs": ["not a dict", {"name": "x"}],
                    "outputs": "not a dict",
                    "success_criteria": "not a list",
                    "failure_modes": [{"no_mode": 1}, {"mode": "ok"}],
                    "dependencies": "not a list",
                    "entities": [1, "User"],
                }
            ],
            "nfr_goals": "not a list",
        }
        with _complete_returning(payload):
            fs = feature_speccer.build_feature_specs(
                _envelope([{"Auth": {"description": "d"}}]), {"model": "x"}
            )
        feat = fs["features"][0]
        assert feat["inputs"] == [
            {"name": "x", "type": "", "description": "", "required": False}
        ]
        assert feat["outputs"] == {}
        assert feat["success_criteria"] == []
        assert feat["failure_modes"] == [
            {"mode": "ok", "likelihood": "", "mitigation": ""}
        ]
        assert feat["dependencies"] == []
        assert feat["entities"] == ["1", "User"]
        assert fs["nfr_goals"] == []


# ---------------------------------------------------------------------------
# Fallback to scaffold
# ---------------------------------------------------------------------------


class TestFallback:
    def _assert_is_scaffold(self, fs: dict[str, Any]) -> None:
        assert [f["id"] for f in fs["features"]] == ["auth", "checkout"]
        assert fs["features"][0]["inputs"] == []
        assert fs["features"][0]["success_criteria"] == []
        assert fs["nfr_goals"] == []

    def test_call_raises_falls_back(self) -> None:
        with patch("spec4.llm.complete", side_effect=RuntimeError("boom")):
            fs = feature_speccer.build_feature_specs(
                _two_feature_vision(), {"model": "x"}
            )
        self._assert_is_scaffold(fs)

    def test_unparseable_output_falls_back(self) -> None:
        with _complete_returning("this is not json at all"):
            fs = feature_speccer.build_feature_specs(
                _two_feature_vision(), {"model": "x"}
            )
        self._assert_is_scaffold(fs)

    def test_no_llm_config_is_scaffold(self) -> None:
        fs = feature_speccer.build_feature_specs(_two_feature_vision())
        self._assert_is_scaffold(fs)


# ---------------------------------------------------------------------------
# Dependency DAG pruning (deterministic)
# ---------------------------------------------------------------------------


class TestDependencyValidation:
    def test_drops_self_and_dangling(self) -> None:
        feats = _scaffold("a", "b")
        feats[0]["dependencies"] = ["a", "ghost", "b"]
        out = feature_speccer._validate_dependencies(feats)
        assert out[0]["dependencies"] == ["b"]

    def test_breaks_cycle(self) -> None:
        feats = _scaffold("a", "b", "c")
        feats[0]["dependencies"] = ["b"]
        feats[1]["dependencies"] = ["c"]
        feats[2]["dependencies"] = ["a"]  # closes the cycle
        out = feature_speccer._validate_dependencies(feats)
        deps = {f["id"]: f["dependencies"] for f in out}
        assert deps == {"a": ["b"], "b": ["c"], "c": []}

    def test_keeps_valid_dag(self) -> None:
        feats = _scaffold("a", "b", "c")
        feats[2]["dependencies"] = ["a", "b"]
        out = feature_speccer._validate_dependencies(feats)
        assert out[2]["dependencies"] == ["a", "b"]

    def test_dedups(self) -> None:
        feats = _scaffold("a", "b")
        feats[1]["dependencies"] = ["a", "a"]
        out = feature_speccer._validate_dependencies(feats)
        assert out[1]["dependencies"] == ["a"]


# ---------------------------------------------------------------------------
# Review render
# ---------------------------------------------------------------------------


class TestRender:
    def test_render_includes_names_purpose_deps_nfr(self) -> None:
        fs = {
            "features": [
                {"id": "auth", "name": "Auth", "purpose": "Sign in.",
                 "dependencies": []},
                {"id": "checkout", "name": "Checkout", "purpose": "Pay.",
                 "dependencies": ["auth"]},
            ],
            "nfr_goals": ["fast"],
        }
        out = feature_speccer.render_feature_specs(fs)
        assert "**Auth**" in out
        assert "Sign in." in out
        assert "depends on: Auth" in out  # id resolved to name
        assert "**Quality goals:** fast" in out

    def test_empty_specs_render_blank(self) -> None:
        assert feature_speccer.render_feature_specs({"features": []}) == ""
        assert feature_speccer.render_feature_specs(None) == ""


# ---------------------------------------------------------------------------
# Completion-hook integration
# ---------------------------------------------------------------------------


class TestHookIntegration:
    def test_hook_enriches_and_displays(self) -> None:
        session = _make_session()
        vision_json = (
            '{"vision_statement": {"name": "ShopApp", "vision": '
            '{"purpose": "Shop.", "key_features_mvp": '
            '[{"Auth": {"description": "Sign in."}}]}}}'
        )
        stream_response = f"Here.\n\n```json\n{vision_json}\n```"
        payload = {
            "features": [
                {"id": "auth", "purpose": "Authenticate.",
                 "success_criteria": ["users get in"]}
            ],
            "nfr_goals": ["fast"],
        }
        with _mock_stream(stream_response), _complete_returning(payload):
            "".join(brainstormer.run("finalize", session, session["llm_config"]))

        assert session["brainstormer_state"] == STATE_VISION_COMPLETE
        fs = session["feature_specs"]
        assert fs["features"][0]["purpose"] == "Authenticate."
        assert fs["features"][0]["success_criteria"] == ["users get in"]
        # The drafted specs and the transition both appear in the chat display.
        display = session["_display_override"]
        assert "Feature specs" in display
        assert "**Auth**" in display
        assert "Continue to Agentifier" in display
