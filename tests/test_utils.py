from __future__ import annotations

from typing import Any

from spec4.agents._utils import (
    _ai_features_for_designer,
    _drop_orphan_trailing_user,
    _feature_specs_for_designer,
    _slim_vision_framing,
)


class TestDropOrphanTrailingUser:
    def test_empty_list_no_op(self) -> None:
        msgs: list[dict[str, Any]] = []
        assert _drop_orphan_trailing_user(msgs) == 0
        assert msgs == []

    def test_well_formed_history_unchanged(self) -> None:
        msgs = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
        ]
        original = list(msgs)
        assert _drop_orphan_trailing_user(msgs) == 0
        assert msgs == original

    def test_drops_single_orphan_user(self) -> None:
        msgs = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2 (failed before reply)"},
        ]
        assert _drop_orphan_trailing_user(msgs) == 1
        assert msgs == [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
        ]

    def test_drops_user_only_history(self) -> None:
        msgs = [{"role": "user", "content": "first try, failed"}]
        assert _drop_orphan_trailing_user(msgs) == 1
        assert msgs == []

    def test_drops_trailing_tool_and_user_chain(self) -> None:
        # If a tool-call response was appended but the next assistant never
        # arrived, both the tool message and the assistant-with-tool-call
        # turn (which has role=assistant but is followed by tool/user only)
        # need to be considered. We only pop non-assistant trailing entries.
        msgs = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
            {"role": "tool", "tool_call_id": "x", "content": "tool result"},
        ]
        assert _drop_orphan_trailing_user(msgs) == 2
        assert msgs == [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
        ]

    def test_keeps_empty_assistant_turn(self) -> None:
        # An empty assistant turn is still well-formed and must NOT be dropped.
        msgs = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": ""},
        ]
        assert _drop_orphan_trailing_user(msgs) == 0
        assert msgs[-1]["role"] == "assistant"


def _surface(
    name: str,
    *,
    scope: str = "feature",
    tier: str = "single_call",
    mode: str = "synchronous",
    authority: str = "suggest",
    served: list[str] | None = None,
    composed_under: str = "",
    inputs: list[dict[str, Any]] | None = None,
    primary_out: str = "",
    failure_modes: list[dict[str, Any]] | None = None,
    escalation: str = "",
    kind: str = "",
) -> dict[str, Any]:
    f: dict[str, Any] = {
        "name": name,
        "scope": scope,
        "tier": tier,
        "purpose": f"purpose of {name}",
        "invocation": {"mode": mode, "trigger": f"trigger for {name}"},
        "decision_authority": authority,
        "linked_vision_features": served or [],
        "composed_under": composed_under,
        "inputs": inputs or [],
        "outputs": {"primary": primary_out} if primary_out else {},
    }
    if failure_modes is not None:
        f["failure_modes"] = failure_modes
    if escalation:
        f["escalation"] = escalation
    if kind:
        f["kind"] = kind
    return f



class TestAiFeaturesForDesigner:
    def test_empty_returns_empty_string(self) -> None:
        assert _ai_features_for_designer({}) == ""
        assert _ai_features_for_designer({"ai_features": []}) == ""

    def test_only_infra_and_subfeatures_returns_empty(self) -> None:
        cat = {
            "ai_features": [
                _surface("vector_index", tier="infrastructure"),
                _surface("orphan_step", scope="sub_feature", composed_under=""),
            ]
        }
        assert _ai_features_for_designer(cat) == ""

    def test_top_level_feature_becomes_surface(self) -> None:
        cat = {"ai_features": [_surface("qa", served=["answers"])]}
        out = _ai_features_for_designer(cat)
        assert "### `qa`" in out
        assert "serves vision feature(s): answers" in out

    def test_low_tier_top_level_feature_is_included(self) -> None:
        # Regression: the old tier>=single_call gate dropped user-facing
        # features below single_call. A scope=feature embeddings surface must
        # now appear.
        cat = {"ai_features": [_surface("repeat_detect", tier="embeddings")]}
        assert "### `repeat_detect`" in _ai_features_for_designer(cat)

    def test_infrastructure_excluded_by_tier_or_kind(self) -> None:
        cat = {
            "ai_features": [
                _surface("real", tier="single_call"),
                _surface("infra_a", tier="infrastructure"),
                _surface("infra_b", tier="single_call", kind="infrastructure"),
            ]
        }
        out = _ai_features_for_designer(cat)
        assert "`real`" in out
        assert "infra_a" not in out
        assert "infra_b" not in out

    def test_subfeatures_nested_under_parent_not_top_level(self) -> None:
        cat = {
            "ai_features": [
                _surface("pipeline", tier="chained_calls"),
                _surface(
                    "citations",
                    scope="sub_feature",
                    composed_under="pipeline",
                    primary_out="citation list",
                ),
            ]
        }
        out = _ai_features_for_designer(cat)
        # parent is a surface header; member is nested (indented), not a header
        assert "### `pipeline`" in out
        assert "### `citations`" not in out
        assert "    - `citations`" in out

    def test_carries_purpose_inputs_output(self) -> None:
        cat = {
            "ai_features": [
                _surface(
                    "qa",
                    inputs=[
                        {"name": "question", "description": "the q", "required": True},
                        {"name": "ctx", "description": "opt", "required": False},
                    ],
                    primary_out="a grounded answer",
                )
            ]
        }
        out = _ai_features_for_designer(cat)
        assert "Purpose: purpose of qa" in out
        assert "User provides: question: the q" in out
        assert "ctx (optional)" in out
        assert "Result to show: a grounded answer" in out

    def test_affordance_hints_by_mode_and_authority(self) -> None:
        stream = _ai_features_for_designer(
            {"ai_features": [_surface("s", mode="streaming", authority="autonomous")]}
        )
        assert "stream the output" in stream

        async_cat = {
            "ai_features": [_surface("s", mode="asynchronous", authority="autonomous")]
        }
        async_ = _ai_features_for_designer(async_cat)
        assert "background" in async_

        confirm = _ai_features_for_designer(
            {"ai_features": [_surface("s", authority="confirm")]}
        )
        assert "confirmation" in confirm

        suggest = _ai_features_for_designer(
            {"ai_features": [_surface("s", authority="suggest")]}
        )
        assert "suggestion the user can accept or dismiss" in suggest

        multistep = _ai_features_for_designer(
            {"ai_features": [_surface("s", tier="chained_calls")]}
        )
        assert "multi-step progress" in multistep

    def test_edge_state_prefers_failure_mode_then_escalation(self) -> None:
        with_fm = _ai_features_for_designer(
            {
                "ai_features": [
                    _surface(
                        "s",
                        failure_modes=[{"mode": "out of scope", "likelihood": "med"}],
                        escalation="route to human",
                    )
                ]
            }
        )
        assert "Edge state to design for: out of scope" in with_fm

        esc_only = _ai_features_for_designer(
            {"ai_features": [_surface("s", escalation="route to human")]}
        )
        assert "Edge state to design for: route to human" in esc_only

class TestSlimVisionFraming:
    def test_keeps_framing_drops_features_and_noise(self) -> None:
        vision = {
            "vision_statement": {
                "name": "App",
                "vision": {
                    "purpose": "do things",
                    "ui_surface": "Web app",
                    "target_audience": ["founders"],
                    "differentiators": ["fast"],
                    "key_features_mvp": [{"Secret": {"id": "secret"}}],
                    "monetization": {"current": "free"},
                    "references": [],
                },
            }
        }
        out = _slim_vision_framing(vision)
        assert out["name"] == "App"
        assert out["purpose"] == "do things"
        assert out["ui_surface"] == "Web app"
        assert out["target_audience"] == ["founders"]
        assert out["differentiators"] == ["fast"]
        assert "key_features_mvp" not in out
        assert "monetization" not in out
        assert "references" not in out

    def test_flat_inner_shape(self) -> None:
        assert _slim_vision_framing({"name": "X"}) == {"name": "X"}

    def test_none_and_empty(self) -> None:
        assert _slim_vision_framing(None) == {}
        assert _slim_vision_framing({}) == {}


class TestFeatureSpecsForDesigner:
    def test_empty_returns_blank(self) -> None:
        assert _feature_specs_for_designer({}) == ""
        assert _feature_specs_for_designer({"features": []}) == ""
        assert _feature_specs_for_designer(None) == ""

    def test_renders_blocks_nfr_and_vocabulary(self) -> None:
        fs = {
            "features": [
                {
                    "id": "deck_build",
                    "name": "Deck_Build",
                    "purpose": "build decks",
                    "invocation": {"trigger": "founder describes idea"},
                    "inputs": [
                        {"name": "idea", "description": "the idea", "required": True}
                    ],
                    "outputs": {"primary": "a complete deck"},
                    "success_criteria": ["deck is usable"],
                    "failure_modes": [{"mode": "vague idea", "likelihood": "medium"}],
                    "entities": ["Pitch Deck", "Narrative"],
                }
            ],
            "nfr_goals": ["sub-minute generation"],
        }
        out = _feature_specs_for_designer(fs)
        assert "### `Deck_Build`" in out
        assert "build decks" in out
        assert "a complete deck" in out
        assert "deck is usable" in out
        assert "vague idea" in out
        assert "Non-functional goals" in out
        assert "sub-minute generation" in out
        assert "Domain vocabulary" in out
        assert "Pitch Deck" in out
        assert "Narrative" in out

    def test_no_graph_lines_leak_from_catalog_fields(self) -> None:
        # A stray catalog-only field must not surface graph lines in the
        # Designer block (include_graph=False).
        fs = {"features": [{"id": "f", "name": "F", "purpose": "p", "tier": "rag"}]}
        out = _feature_specs_for_designer(fs)
        assert "Tier:" not in out