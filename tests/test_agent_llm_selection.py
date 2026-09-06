"""Per-agent provider/model selection: the resolver spine.

Covers the half of the feature that has no UI — the shared builder and probe
wrapper, the resolver every agent turn goes through, key isolation between an
override and the default, and the guard that keeps sub-agents from escaping
their parent's selection. The gate card and the model chip are tested
separately once they exist.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any
from unittest.mock import patch

import pytest

from dash import no_update

from spec4 import llm_selection, providers
from spec4.app_constants import AGENT_KEYS
from spec4.callbacks import (
    on_fast_forward,
    on_gate_connect,
    on_gate_continue,
    on_gate_chip,
    on_gate_keep,
    on_gate_pick,
    on_gate_provider_change,
    on_gate_use_default,
    on_init_turn,
    on_setup_connect,
    on_setup_model_continue,
)
from spec4.layouts import _AGENT_ROWS
from spec4.layouts._chat import _chat_action_buttons, _chat_layout
from spec4.layouts._llm_gate import gate_card, is_open, model_chip
from spec4.layouts.designer import designer_layout
from spec4.project_manager import _USAGE_ROLLUP_PARENT
from spec4.session import _default_session, _get_agent_gen, _reset_for_new_project

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "spec4"

_DEFAULT_CONFIG = {"model": "claude-sonnet-4-6", "api_key": "default-key"}
_OVERRIDE_CONFIG = {"model": "gpt-5-mini", "api_key": "override-key"}


def _session(**extra: Any) -> dict[str, Any]:
    session = _default_session()
    session.update(
        {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "api_key": "default-key",
            "llm_config": dict(_DEFAULT_CONFIG),
            "working_dir": "/tmp/project",
        }
    )
    session.update(extra)
    return session


def _with_override(agent: str, **entry: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "provider": "openai",
        "model": "gpt-5-mini",
        "available_models": ["gpt-5-mini", "gpt-5"],
        "llm_config": dict(_OVERRIDE_CONFIG),
        "image_support": True,
        "tool_support": True,
    }
    base.update(entry)
    return _session(agent_llm={agent: base})


class TestAgentKeys:
    def test_seven_user_facing_agents(self) -> None:
        assert len(AGENT_KEYS) == 7

    def test_matches_the_agent_select_rows(self) -> None:
        """One authority for the agent list — the /agents rows cannot drift."""
        assert tuple(key for key, *_ in _AGENT_ROWS) == AGENT_KEYS


class TestBuildLlmConfig:
    def test_plain_provider_carries_key_and_model(self) -> None:
        cfg = llm_selection.build_llm_config("openai", "gpt-5-mini", "sk-abc")
        assert cfg == {"model": "gpt-5-mini", "api_key": "sk-abc"}

    def test_registry_api_base_is_applied(self) -> None:
        cfg = llm_selection.build_llm_config("nebius", "openai/x", "k")
        assert cfg["api_base"] == providers.PROVIDERS["nebius"]["api_base"]

    def test_missing_key_becomes_empty_string(self) -> None:
        cfg = llm_selection.build_llm_config("openai", "gpt-5-mini", None)
        assert cfg["api_key"] == ""

    def test_bedrock_api_key_parses_into_region(self) -> None:
        cfg = llm_selection.build_llm_config(
            "bedrock", "bedrock/converse/m", "bdak_x:us-east-1"
        )
        assert cfg["aws_region_name"] == "us-east-1"
        assert cfg["api_key"] == "bdak_x"

    def test_bedrock_iam_key_parses_into_aws_fields(self) -> None:
        cfg = llm_selection.build_llm_config(
            "bedrock", "bedrock/converse/m", "AKIAX:secret:eu-west-1"
        )
        assert cfg["aws_access_key_id"] == "AKIAX"
        assert cfg["aws_secret_access_key"] == "secret"
        assert cfg["aws_region_name"] == "eu-west-1"
        assert "api_key" not in cfg


class TestProbeCapabilities:
    def test_bedrock_is_assumed_capable_without_probing(self) -> None:
        with patch("spec4.llm_selection.probe_image_support") as image, patch(
            "spec4.llm_selection.probe_tool_support"
        ) as tool:
            assert llm_selection.probe_capabilities("bedrock", {"model": "m"}) == (
                True,
                True,
            )
        image.assert_not_called()
        tool.assert_not_called()

    def test_results_are_passed_through(self) -> None:
        with patch(
            "spec4.llm_selection.probe_image_support", return_value=False
        ), patch("spec4.llm_selection.probe_tool_support", return_value=True):
            assert llm_selection.probe_capabilities("openai", _OVERRIDE_CONFIG) == (
                False,
                True,
            )

    def test_a_raising_probe_yields_unknown_not_an_error(self) -> None:
        """Advisory, never blocking: a broken probe must not fail the flow."""
        with patch(
            "spec4.llm_selection.probe_image_support", side_effect=RuntimeError("boom")
        ), patch(
            "spec4.llm_selection.probe_tool_support", side_effect=RuntimeError("boom")
        ):
            assert llm_selection.probe_capabilities("openai", _OVERRIDE_CONFIG) == (
                None,
                None,
            )

    def test_aws_credentials_reach_the_probe(self) -> None:
        cfg = llm_selection.build_llm_config("openai", "gpt-5", "k")
        cfg["aws_region_name"] = "us-east-1"
        with patch(
            "spec4.llm_selection.probe_image_support", return_value=True
        ) as image, patch("spec4.llm_selection.probe_tool_support", return_value=True):
            llm_selection.probe_capabilities("openai", cfg)
        assert image.call_args[1]["aws_region_name"] == "us-east-1"


class TestResolve:
    def test_falls_back_to_the_default(self) -> None:
        assert llm_selection.resolve(_session(), "phaser") == _DEFAULT_CONFIG

    def test_returns_the_override_when_one_exists(self) -> None:
        session = _with_override("code_scanner")
        assert llm_selection.resolve(session, "code_scanner") == _OVERRIDE_CONFIG

    def test_other_agents_are_unaffected_by_an_override(self) -> None:
        session = _with_override("code_scanner")
        assert llm_selection.resolve(session, "phaser") == _DEFAULT_CONFIG

    def test_an_entry_without_a_model_is_ignored(self) -> None:
        session = _with_override("phaser", llm_config={"api_key": "x"})
        assert llm_selection.resolve(session, "phaser") == _DEFAULT_CONFIG

    def test_unconfigured_session_still_yields_none(self) -> None:
        """Preserves the pre-change failure mode rather than inventing a config."""
        assert llm_selection.resolve(_default_session(), "phaser") is None


class TestCapability:
    def test_override_answers_for_itself(self) -> None:
        session = _with_override("designer", image_support=False)
        assert (
            llm_selection.capability(session, "designer", "image_support", True)
            is False
        )

    def test_unknown_override_falls_back_to_the_store(self) -> None:
        session = _with_override("designer", image_support=None)
        assert (
            llm_selection.capability(session, "designer", "image_support", True) is True
        )

    def test_no_override_uses_the_store(self) -> None:
        assert (
            llm_selection.capability(_session(), "designer", "image_support", False)
            is False
        )


class TestKeyForProvider:
    def test_prefers_the_remembered_key_for_that_provider(self) -> None:
        prefs = {"provider_keys": {"openai": "sk-remembered"}}
        assert llm_selection.key_for_provider(_session(), prefs, "openai") == (
            "sk-remembered"
        )

    def test_falls_back_to_the_legacy_single_key(self) -> None:
        prefs = {"provider": "openai", "api_key": "sk-legacy"}
        assert llm_selection.key_for_provider(_session(), prefs, "openai") == (
            "sk-legacy"
        )

    def test_falls_back_to_the_session_default_on_a_matching_provider(self) -> None:
        assert llm_selection.key_for_provider(_session(), {}, "anthropic") == (
            "default-key"
        )

    def test_never_offers_one_providers_key_for_another(self) -> None:
        prefs = {"provider_keys": {"openai": "sk-openai"}}
        assert llm_selection.key_for_provider(_session(), prefs, "cohere") == ""


class TestKeyIsolation:
    """An override must never write through to the default's credentials."""

    def test_override_does_not_touch_the_default(self) -> None:
        session = _session()
        before_key = session["api_key"]
        before_config = dict(session["llm_config"])

        session["agent_llm"] = {
            "code_scanner": {
                "provider": "openai",
                "model": "gpt-5-mini",
                "llm_config": llm_selection.build_llm_config(
                    "openai", "gpt-5-mini", "sk-override"
                ),
            }
        }

        assert session["api_key"] == before_key
        assert session["llm_config"] == before_config
        assert llm_selection.resolve(session, "code_scanner")["api_key"] == (
            "sk-override"
        )
        assert llm_selection.resolve(session, "phaser")["api_key"] == "default-key"

    def test_the_two_configs_are_not_the_same_object(self) -> None:
        session = _with_override("code_scanner")
        override = llm_selection.resolve(session, "code_scanner")
        default = llm_selection.resolve(session, "phaser")
        assert override is not default
        override["api_key"] = "mutated"
        assert session["llm_config"]["api_key"] == "default-key"


class TestOverridesSurviveTheDefaultChanging:
    def test_setup_flow_leaves_overrides_intact(self) -> None:
        """Re-running the wizard changes the default only (plan §2.6)."""
        session = _with_override("code_scanner")
        session["agent_llm_asked"] = {"code_scanner": True, "phaser": True}
        before = {k: dict(v) for k, v in session["agent_llm"].items()}

        with patch.object(
            providers, "list_models", return_value=(["gpt-5"], "")
        ), patch(
            "spec4.callbacks.providers.list_models", return_value=(["gpt-5"], "")
        ):
            connected, _ = on_setup_connect(
                1, "OpenAI", "sk-new-default", False, session, {}
            )

        with patch(
            "spec4.llm_selection.probe_image_support", return_value=True
        ), patch("spec4.llm_selection.probe_tool_support", return_value=True):
            updated, _, _, _, _ = on_setup_model_continue(1, "gpt-5", connected, {})

        assert updated["agent_llm"] == before
        assert updated["agent_llm_asked"] == {"code_scanner": True, "phaser": True}
        # The overridden agent keeps its model; an agent on the default follows
        # the new one.
        assert llm_selection.resolve(updated, "code_scanner") == _OVERRIDE_CONFIG
        assert llm_selection.resolve(updated, "phaser")["model"] == "gpt-5"

    def test_new_project_keeps_overrides_but_re_asks(self) -> None:
        session = _with_override("code_scanner")
        session["agent_llm_asked"] = {"code_scanner": True}
        fresh = _reset_for_new_project(session)
        assert fresh["agent_llm"] == session["agent_llm"]
        assert fresh["agent_llm_asked"] == {}


class TestDefaultSessionKeys:
    @pytest.mark.parametrize(
        "key", ["agent_llm", "agent_llm_asked", "agent_llm_error"]
    )
    def test_key_is_present(self, key: str) -> None:
        assert key in _default_session()

    def test_error_is_transient(self) -> None:
        from spec4.session import _PRESERVED_SETUP_KEYS

        assert "agent_llm" in _PRESERVED_SETUP_KEYS
        assert "agent_llm_asked" not in _PRESERVED_SETUP_KEYS
        assert "agent_llm_error" not in _PRESERVED_SETUP_KEYS


class TestDispatchResolvesPerAgent:
    def test_the_agents_generator_receives_the_override(self) -> None:
        session = _with_override("brainstormer", llm_config={"model": "gpt-5-mini"})
        session["active_agent"] = "brainstormer"
        with patch("spec4.session.brainstormer.run") as run:
            run.return_value = iter(())
            _get_agent_gen(None, session)
        assert run.call_args[0][2] == {"model": "gpt-5-mini"}

    def test_an_agent_without_an_override_receives_the_default(self) -> None:
        session = _with_override("brainstormer")
        session["active_agent"] = "phaser"
        with patch("spec4.session.phaser.run") as run:
            run.return_value = iter(())
            _get_agent_gen(None, session)
        assert run.call_args[0][2] == _DEFAULT_CONFIG


class TestSubAgentsCannotEscapeTheirParent:
    """Selection is keyed by the seven parents; every caller must map to one.

    A new sub-agent that passes an unregistered ``agent_name`` would be
    invisible to the rollup and — the reason this guard exists — would signal
    that someone had introduced an LLM path outside the parent's resolved
    config.
    """

    def test_every_agent_name_literal_maps_to_a_user_facing_agent(self) -> None:
        pattern = re.compile(r'agent_name=["\']([a-z_]+)["\']')
        found: dict[str, str] = {}
        for path in _SRC.rglob("*.py"):
            for name in pattern.findall(path.read_text()):
                found.setdefault(name, str(path.relative_to(_SRC)))

        assert found, "no agent_name literals found — has the call convention changed?"
        unmapped = {
            name: where
            for name, where in found.items()
            if name not in AGENT_KEYS and name not in _USAGE_ROLLUP_PARENT
        }
        assert not unmapped, (
            "these LLM callers roll up to no user-facing agent; add them to "
            f"_USAGE_ROLLUP_PARENT: {unmapped}"
        )

    def test_every_rollup_parent_is_a_user_facing_agent(self) -> None:
        assert set(_USAGE_ROLLUP_PARENT.values()) <= set(AGENT_KEYS)

    def test_no_sub_agent_is_also_a_parent(self) -> None:
        assert not set(_USAGE_ROLLUP_PARENT) & set(AGENT_KEYS)


# ---------------------------------------------------------------------------
# The gate: card shapes, the chip, and the failure paths through it
# ---------------------------------------------------------------------------


def _find(component: Any, comp_id: str) -> Any:
    """Depth-first search for a dash component with the given id."""
    if getattr(component, "id", None) == comp_id:
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        found = _find(child, comp_id)
        if found is not None:
            return found
    return None


def _text(component: Any) -> str:
    """All string content under a component, flattened."""
    if isinstance(component, str):
        return component
    children = getattr(component, "children", None)
    if children is None:
        return ""
    if not isinstance(children, (list, tuple)):
        children = [children]
    return " ".join(_text(c) for c in children)


class TestGateCardShapes:
    def test_first_run_offers_default_or_pick(self) -> None:
        card = gate_card(_session(), {}, "code_scanner")
        assert _find(card, "btn-agent-llm-default") is not None
        assert _find(card, "btn-agent-llm-pick") is not None
        assert _find(card, "btn-agent-llm-keep") is None

    def test_carried_forward_entry_offers_keep(self) -> None:
        card = gate_card(_with_override("code_scanner"), {}, "code_scanner")
        assert _find(card, "btn-agent-llm-keep") is not None
        assert _find(card, "btn-agent-llm-default") is not None
        assert _find(card, "btn-agent-llm-pick") is not None

    def test_carried_forward_card_names_the_model(self) -> None:
        session = _with_override("code_scanner")
        assert "gpt-5-mini" in _text(gate_card(session, {}, "code_scanner"))

    def test_the_default_button_names_the_default_model(self) -> None:
        assert "claude-sonnet-4-6" in _text(gate_card(_session(), {}, "phaser"))

    def test_survives_a_new_project_as_the_keep_shape(self) -> None:
        """The state §2.1 hands over: entry preserved, answer cleared."""
        fresh = _reset_for_new_project(_with_override("code_scanner"))
        assert is_open(fresh, "code_scanner")
        assert _find(gate_card(fresh, {}, "code_scanner"), "btn-agent-llm-keep")


class TestGateAnswers:
    def test_use_default_answers_without_writing_an_entry(self) -> None:
        session = _session(active_agent="phaser")
        updated = on_gate_use_default(1, session)
        assert updated["agent_llm_asked"]["phaser"] is True
        assert "phaser" not in updated["agent_llm"]
        assert llm_selection.resolve(updated, "phaser") == _DEFAULT_CONFIG

    def test_use_default_drops_an_existing_override(self) -> None:
        session = _with_override("phaser")
        session["active_agent"] = "phaser"
        updated = on_gate_use_default(1, session)
        assert "phaser" not in updated["agent_llm"]
        assert llm_selection.resolve(updated, "phaser") == _DEFAULT_CONFIG

    def test_keep_costs_no_probe_and_no_re_entry(self) -> None:
        session = _with_override("code_scanner")
        session["active_agent"] = "code_scanner"
        before = dict(session["agent_llm"]["code_scanner"])
        with patch("spec4.llm_selection.probe_image_support") as image, patch(
            "spec4.llm_selection.probe_tool_support"
        ) as tool:
            updated = on_gate_keep(1, session)
        image.assert_not_called()
        tool.assert_not_called()
        assert updated["agent_llm"]["code_scanner"] == before
        assert updated["agent_llm_asked"]["code_scanner"] is True

    def test_pick_prefills_from_an_existing_entry(self) -> None:
        """No Connect round trip when provider and key are unchanged."""
        session = _with_override("code_scanner")
        session["active_agent"] = "code_scanner"
        updated = on_gate_pick(1, session)
        draft = updated["agent_llm_draft"]
        assert draft["agent"] == "code_scanner"
        assert draft["provider"] == "openai"
        assert draft["api_key"] == "override-key"
        assert draft["available_models"] == ["gpt-5-mini", "gpt-5"]
        # The model field renders straight away, so Continue is reachable.
        card = gate_card(updated, {}, "code_scanner")
        assert _find(card, "agent-llm-model") is not None
        assert _find(card, "btn-agent-llm-continue") is not None

    def test_continue_writes_the_entry_and_answers(self) -> None:
        session = _session(active_agent="code_scanner")
        session["agent_llm_draft"] = {
            "agent": "code_scanner",
            "provider": "openai",
            "api_key": "sk-override",
            "available_models": ["gpt-5-mini"],
        }
        with patch(
            "spec4.llm_selection.probe_image_support", return_value=True
        ), patch("spec4.llm_selection.probe_tool_support", return_value=False):
            updated, _ = on_gate_continue(1, "gpt-5-mini", session)
        entry = updated["agent_llm"]["code_scanner"]
        assert entry["llm_config"] == {"model": "gpt-5-mini", "api_key": "sk-override"}
        assert entry["image_support"] is True
        assert entry["tool_support"] is False
        assert updated["agent_llm_asked"]["code_scanner"] is True
        assert updated["agent_llm_draft"] is None
        # And the default is untouched — §2.5, through the real callback.
        assert updated["api_key"] == "default-key"
        assert updated["llm_config"] == _DEFAULT_CONFIG


class TestGateFailureParity:
    """Connect blocks; probes never do (plan §2.3)."""

    def _drafted(self) -> dict[str, Any]:
        session = _session(active_agent="code_scanner")
        session["agent_llm_draft"] = {"agent": "code_scanner"}
        return session

    def test_a_bad_key_writes_nothing_and_blocks_continue(self) -> None:
        session = self._drafted()
        with patch.object(providers, "list_models", return_value=([], "bad key")):
            updated, prefs = on_gate_connect(
                1, "OpenAI", "sk-bad", session, {"save_prefs": True}
            )
        assert updated["agent_llm"] == {}
        assert updated["agent_llm_asked"] == {}
        assert "bad key" in updated["agent_llm_error"]
        assert prefs is no_update
        # No model field means Continue is unreachable, not merely disabled.
        card = gate_card(updated, {}, "code_scanner")
        assert _find(card, "agent-llm-model") is None
        assert _find(card, "btn-agent-llm-continue") is None

    def test_a_failed_connect_leaves_the_default_credentials_alone(self) -> None:
        session = self._drafted()
        with patch.object(providers, "list_models", return_value=([], "nope")):
            updated, _ = on_gate_connect(1, "OpenAI", "sk-bad", session, {})
        assert updated["provider"] == "anthropic"
        assert updated["api_key"] == "default-key"
        assert updated["llm_config"] == _DEFAULT_CONFIG

    def test_an_empty_but_successful_list_is_a_failure(self) -> None:
        session = self._drafted()
        with patch.object(providers, "list_models", return_value=([], "")):
            updated, _ = on_gate_connect(1, "OpenAI", "sk-ok", session, {})
        assert updated["agent_llm_error"].startswith("Connection failed")

    def test_a_blank_key_is_caught_before_the_network(self) -> None:
        session = self._drafted()
        with patch.object(providers, "list_models") as listed:
            updated, _ = on_gate_connect(1, "OpenAI", "  ", session, {})
        listed.assert_not_called()
        assert updated["agent_llm_error"] == "Please enter an API key."

    def test_a_successful_connect_remembers_the_key_per_provider(self) -> None:
        session = self._drafted()
        with patch.object(providers, "list_models", return_value=(["gpt-5"], "")):
            _, prefs = on_gate_connect(
                1, "OpenAI", "sk-new", session, {"save_prefs": True}
            )
        assert prefs["provider_keys"]["openai"] == "sk-new"

    def test_without_consent_no_key_is_remembered(self) -> None:
        session = self._drafted()
        with patch.object(providers, "list_models", return_value=(["gpt-5"], "")):
            _, prefs = on_gate_connect(1, "OpenAI", "sk-new", session, {})
        assert prefs is no_update

    def test_a_raising_probe_still_commits_and_starts_the_agent(self) -> None:
        session = _session(active_agent="code_scanner")
        session["agent_llm_draft"] = {
            "agent": "code_scanner",
            "provider": "openai",
            "api_key": "sk-x",
            "available_models": ["gpt-5-mini"],
        }
        with patch(
            "spec4.llm_selection.probe_image_support", side_effect=RuntimeError
        ), patch("spec4.llm_selection.probe_tool_support", side_effect=RuntimeError):
            updated, _ = on_gate_continue(1, "gpt-5-mini", session)
        entry = updated["agent_llm"]["code_scanner"]
        assert entry["image_support"] is None
        assert entry["tool_support"] is None
        assert updated["agent_llm_asked"]["code_scanner"] is True
        assert not is_open(updated, "code_scanner")
        # Unknown means capable, so nothing downstream is gated off.
        assert (
            llm_selection.capability(updated, "code_scanner", "image_support", True)
            is True
        )


class TestGateBlocksTheTurn:
    def test_init_turn_refuses_while_the_gate_is_open(self) -> None:
        session = _session(active_agent="phaser")
        with patch("spec4.callbacks._get_agent_gen") as gen:
            result = on_init_turn(1, session)
        gen.assert_not_called()
        assert result == (no_update, no_update)

    def test_fast_forward_refuses_while_the_gate_is_open(self) -> None:
        session = _session(
            active_agent="stack_advisor",
            messages=[{"role": "assistant", "content": "Topic 1?"}],
        )
        with patch("spec4.callbacks._get_agent_gen") as gen:
            result = on_fast_forward(1, session)
        gen.assert_not_called()
        assert result == (no_update, no_update)

    def test_the_turn_starts_once_answered(self) -> None:
        session = _session(active_agent="phaser")
        answered = on_gate_use_default(1, session)
        with patch(
            "spec4.callbacks._get_agent_gen", return_value=iter(["x"])
        ) as gen, patch("spec4.callbacks.streaming.start", return_value="sid"):
            updated, _ = on_init_turn(1, answered)
        gen.assert_called_once()
        assert updated["_stream_id"] == "sid"


class TestModelChip:
    def test_names_the_override_when_there_is_one(self) -> None:
        session = _with_override("code_scanner")
        assert "gpt-5-mini" in _text(model_chip(session, "code_scanner"))

    def test_names_the_default_otherwise(self) -> None:
        assert "claude-sonnet-4-6" in _text(model_chip(_session(), "phaser"))

    def test_disabled_mid_stream(self) -> None:
        session = _session(_stream_id="live")
        assert model_chip(session, "phaser").disabled is True
        assert model_chip(_session(), "phaser").disabled is False

    def test_carries_a_light_outline(self) -> None:
        """Outlined, and neutral rather than the theme's primary blue — the
        pale border itself is pinned in v3.css."""
        chip = model_chip(_session(), "phaser")
        assert chip.variant == "outline"
        assert chip.color == "gray"
        css = (_SRC / "assets" / "v3.css").read_text(encoding="utf-8")
        assert "#btn-agent-llm-chip" in css

    def test_clicking_it_reopens_the_same_card(self) -> None:
        session = _with_override("code_scanner")
        session["active_agent"] = "code_scanner"
        session["agent_llm_asked"] = {"code_scanner": True}
        updated = on_gate_chip(1, session)
        assert updated["agent_llm_draft"]["agent"] == "code_scanner"
        # Answered already, so this is the chip path, not the entry gate.
        assert not is_open(updated, "code_scanner")

    def test_a_mid_stream_click_is_refused(self) -> None:
        session = _with_override("code_scanner")
        session["active_agent"] = "code_scanner"
        session["_stream_id"] = "live"
        assert on_gate_chip(1, session) is no_update


class TestChatLayoutGate:
    def test_the_opening_turn_is_disabled_while_the_gate_is_open(self) -> None:
        session = _session(active_agent="phaser", phase="chat")
        layout = _chat_layout(session, {})
        assert _find(layout, "init-turn-interval").max_intervals == 0
        assert _find(layout, "btn-agent-llm-default") is not None

    def test_the_interval_arms_once_answered(self) -> None:
        session = on_gate_use_default(1, _session(active_agent="phaser", phase="chat"))
        layout = _chat_layout(session, {})
        assert _find(layout, "init-turn-interval").max_intervals == 1
        assert _find(layout, "btn-agent-llm-default") is None
        assert _find(layout, "btn-agent-llm-chip") is not None


def _child_ids(node: Any) -> list[str]:
    """The ids of one component's direct children, blank for the unnamed."""
    children = getattr(node, "children", None) or []
    if not isinstance(children, (list, tuple)):
        children = [children]
    return [getattr(c, "id", "") or "" for c in children]


def _row_index(layout: Any, comp_id: str) -> int:
    """Where in the chat layout's top level the row holding ``comp_id`` sits."""
    return next(
        i for i, c in enumerate(layout.children) if comp_id in _child_ids(c)
    )


class TestModelChipPlacement:
    """The chip lives in the footer row under the composer, left of the status
    line — not in the action row above it, where it read as one more item
    among the Fast Forward / download buttons and the readouts."""

    def _answered(self) -> dict[str, Any]:
        return on_gate_use_default(
            1, _session(active_agent="phaser", phase="chat")
        )

    def test_it_left_the_action_row(self) -> None:
        session = self._answered()
        assert _find(_chat_action_buttons(session), "btn-agent-llm-chip") is None

    def test_it_shares_a_row_with_the_status_line_and_comes_first(self) -> None:
        layout = _chat_layout(self._answered(), {})
        footer = layout.children[_row_index(layout, "chat-status-line")]
        ids = _child_ids(footer)
        assert ids == ["btn-agent-llm-chip", "chat-status-line"]

    def test_the_footer_sits_below_the_input(self) -> None:
        layout = _chat_layout(self._answered(), {})
        assert _row_index(layout, "chat-status-line") > _row_index(
            layout, "chat-input"
        )

    def test_the_status_line_still_reserves_its_line(self) -> None:
        """Moving it into a flex row must not cost the reserved height that
        keeps the input from shifting when the first status lands."""
        layout = _chat_layout(self._answered(), {})
        line = _find(layout, "chat-status-line")
        assert line.style["minHeight"] == "1.4em"
        assert line.style["textOverflow"] == "ellipsis"
        # Shrinkable, so a long status ellipsises instead of pushing the chip.
        assert line.style["minWidth"] == "0"

    def test_the_gate_still_suppresses_it(self) -> None:
        layout = _chat_layout(_session(active_agent="phaser", phase="chat"), {})
        assert _find(layout, "btn-agent-llm-chip") is None
        assert _child_ids(
            layout.children[_row_index(layout, "chat-status-line")]
        ) == ["chat-status-line"]


class TestDesignerGate:
    def test_the_wizard_waits_behind_the_gate(self) -> None:
        session = _session(phase="designer")
        layout = designer_layout(session, {})
        assert _find(layout, "btn-agent-llm-default") is not None
        assert _find(layout, "designer-session-store") is None

    def test_the_wizard_renders_once_answered(self, tmp_path: Any) -> None:
        session = _session(phase="designer", working_dir=str(tmp_path))
        answered = on_gate_use_default(1, {**session, "active_agent": "designer"})
        layout = designer_layout(answered, {})
        assert _find(layout, "designer-session-store") is not None
        assert _find(layout, "btn-agent-llm-default") is None


class TestPerAgentCapabilityReachesTheDesigner:
    """Both probes run for an override, and the Designer reads the answer.

    Reported against openrouter/deepseek/deepseek-v4-flash: chosen as the
    *default*, the probe correctly found no image support and the wizard hid
    screenshot upload; chosen as a Designer *override*, the same probe returned
    the same answer but the wizard kept offering upload. The probe was never the
    problem — `render_designer_step` read the store-wide flag, which described
    the (image-capable) default, and never the per-agent result.
    """

    _ENTRY = {
        "provider": "openrouter",
        "model": "openrouter/deepseek/deepseek-v4-flash",
        "available_models": ["openrouter/deepseek/deepseek-v4-flash"],
        "llm_config": {"model": "openrouter/deepseek/deepseek-v4-flash"},
        "image_support": False,
        "tool_support": False,
    }

    def _render(self, step: int, session: dict[str, Any], global_flag: Any) -> Any:
        from spec4.callbacks.designer import render_designer_step

        store = {
            "step": step,
            "screenshots": [],
            "refine_images": [],
            "mock_html": "<p/>",
            "finalized": False,
            "_has_existing_ui": True,
            "_is_revision": False,
        }
        with patch("spec4.callbacks.designer.ctx") as fake_ctx:
            fake_ctx.triggered = [{"prop_id": "designer-session-store.data"}]
            content, _ = render_designer_step(
                store, {"tokens": 0, "progress": 0, "error": None},
                global_flag, session,
            )
        return content

    def _is_upload(self, content: Any, comp_id: str) -> bool:
        """True only for a real dcc.Upload — step 7 keeps a hidden Div stand-in."""
        el = _find(content, comp_id)
        return type(el).__name__ == "Upload"

    def test_both_probes_run_for_an_override(self) -> None:
        session = _session(active_agent="designer", phase="designer")
        session["agent_llm_draft"] = {
            "agent": "designer",
            "provider": "openrouter",
            "api_key": "sk-or",
            "available_models": ["openrouter/deepseek/deepseek-v4-flash"],
        }
        with patch(
            "spec4.llm_selection.probe_image_support", return_value=False
        ) as image, patch(
            "spec4.llm_selection.probe_tool_support", return_value=False
        ) as tool:
            after, _ = on_gate_continue(
                1, "openrouter/deepseek/deepseek-v4-flash", session
            )
        image.assert_called_once()
        tool.assert_called_once()
        entry = after["agent_llm"]["designer"]
        assert entry["image_support"] is False
        assert entry["tool_support"] is False

    def test_the_default_still_offers_upload(self) -> None:
        assert self._is_upload(
            self._render(4, {}, True), "designer-screenshot-upload"
        )
        assert self._is_upload(self._render(7, {}, True), "designer-refine-upload")

    def test_an_override_without_image_support_hides_upload(self) -> None:
        session = {"agent_llm": {"designer": self._ENTRY}}
        # The store-wide flag still says True — it describes the default.
        assert not self._is_upload(
            self._render(4, session, True), "designer-screenshot-upload"
        )
        assert not self._is_upload(
            self._render(7, session, True), "designer-refine-upload"
        )

    def test_step_seven_keeps_the_hidden_stand_in(self) -> None:
        """The callback taking it as an Input must still be dispatchable."""
        session = {"agent_llm": {"designer": self._ENTRY}}
        # `is not None`: an empty Dash component is falsy (no children).
        assert (
            _find(self._render(7, session, True), "designer-refine-upload")
            is not None
        )

    def test_an_image_capable_override_still_offers_upload(self) -> None:
        session = {
            "agent_llm": {"designer": {**self._ENTRY, "image_support": True}}
        }
        # ...even when the *default* was probed as incapable.
        assert self._is_upload(
            self._render(4, session, False), "designer-screenshot-upload"
        )

    def test_an_override_on_another_agent_does_not_gate_the_designer(self) -> None:
        session = {"agent_llm": {"phaser": self._ENTRY}}
        assert self._is_upload(
            self._render(4, session, True), "designer-screenshot-upload"
        )

    def test_an_unprobed_override_falls_back_to_the_store(self) -> None:
        session = {
            "agent_llm": {"designer": {**self._ENTRY, "image_support": None}}
        }
        assert self._is_upload(
            self._render(4, session, True), "designer-screenshot-upload"
        )
        assert not self._is_upload(
            self._render(4, session, False), "designer-screenshot-upload"
        )


_session_with_default = _session


class TestKeyFieldFollowsTheProvider:
    """Switching provider in the gate must not carry the old key across.

    Reported as a 401 from OpenRouter on the first Designer draw. The gate opens
    with the provider Select on the default's provider, so the key box starts
    holding the default's key (Anthropic); changing the Select to OpenRouter
    left that key in place and it was committed to the override.
    """

    def _session(self, **extra: Any) -> dict[str, Any]:
        session = _session_with_default()
        session.update({"agent_llm_draft": {"agent": "designer"}, **extra})
        return session

    def test_the_default_provider_keeps_its_key(self) -> None:
        _, key = on_gate_provider_change("Anthropic", self._session(), {})
        assert key == "default-key"

    def test_switching_provider_clears_the_old_key(self) -> None:
        _, key = on_gate_provider_change("OpenRouter", self._session(), {})
        assert key == ""

    def test_switching_provider_uses_a_remembered_key(self) -> None:
        _, key = on_gate_provider_change(
            "OpenRouter", self._session(), {"provider_keys": {"openrouter": "sk-or"}}
        )
        assert key == "sk-or"

    def test_reopening_an_override_keeps_its_own_key(self) -> None:
        session = self._session(
            agent_llm_draft={
                "agent": "designer",
                "provider": "openrouter",
                "api_key": "sk-or-from-entry",
            }
        )
        _, key = on_gate_provider_change("OpenRouter", session, {})
        assert key is no_update

    def test_the_hint_follows_the_provider_too(self) -> None:
        hint, _ = on_gate_provider_change("AWS Bedrock", self._session(), {})
        assert "KEY:REGION" in str(hint.children)
        hint, _ = on_gate_provider_change("OpenAI", self._session(), {})
        assert not getattr(hint, "children", None)


class TestOpenRouterKeyIsVerified:
    """OpenRouter's model list answers the same for any bearer.

    Every other provider's list call doubles as the credential check that gates
    setup and the per-agent flow. OpenRouter's does not, so a wrong key sailed
    through Connect and surfaced minutes later as a bare 401 mid-generation.
    """

    def test_the_key_endpoint_is_checked_before_the_list(self) -> None:
        calls: list[str] = []

        def _get(url: str, headers: dict[str, str]) -> dict[str, Any]:
            calls.append(url)
            return {"data": [{"id": "deepseek/deepseek-chat"}]}

        with patch("spec4.providers._json_get", side_effect=_get):
            models, err = providers.list_models("openrouter", "sk-or-real")
        assert err == ""
        assert models == ["openrouter/deepseek/deepseek-chat"]
        assert calls[0].endswith("/api/v1/key"), calls
        assert calls[1].endswith("/api/v1/models"), calls

    def test_a_rejected_key_yields_no_models(self) -> None:
        import urllib.error

        def _get(url: str, headers: dict[str, str]) -> dict[str, Any]:
            if url.endswith("/api/v1/key"):
                raise urllib.error.HTTPError(url, 401, "Unauthorized", None, None)
            return {"data": [{"id": "deepseek/deepseek-chat"}]}

        with patch("spec4.providers._json_get", side_effect=_get):
            models, err = providers.list_models("openrouter", "sk-or-bad")
        assert models == []
        assert "401" in err

    def test_an_empty_key_still_lists_the_public_catalogue(self) -> None:
        """Browsing without a key stays possible — only a wrong key is caught."""
        calls: list[str] = []

        def _get(url: str, headers: dict[str, str]) -> dict[str, Any]:
            calls.append(url)
            return {"data": [{"id": "deepseek/deepseek-chat"}]}

        with patch("spec4.providers._json_get", side_effect=_get):
            models, err = providers.list_models("openrouter", "")
        assert models and err == ""
        assert all("/api/v1/key" not in c for c in calls)


class TestDesignerStartOverReopensTheGate:
    """"Start over" restarts Designer at its first question, which is the model.

    It reset the wizard to the intro but left the gate answered, so the previous
    model stayed silently in force — not what starting over means. The override
    is kept so the gate can offer it back rather than demanding a re-typed key.
    """

    _ENTRY = {
        "provider": "openrouter",
        "model": "openrouter/deepseek/deepseek-v4-flash",
        "available_models": ["openrouter/deepseek/deepseek-v4-flash"],
        "llm_config": {"model": "openrouter/deepseek/deepseek-v4-flash"},
        "image_support": False,
        "tool_support": False,
    }

    def _start_over(self, **session_extra: Any) -> dict[str, Any]:
        from spec4.callbacks.designer import on_designer_start_over

        session = _session(
            phase="designer",
            working_dir="/tmp",
            agent_llm_asked={"designer": True, "phaser": True},
            agent_llm={"designer": dict(self._ENTRY)},
            **session_extra,
        )
        store = {"step": 6, "mock_html": "<p/>", "_has_existing_ui": True}
        _, _, _, updated = on_designer_start_over(1, store, session)
        return updated

    def test_the_gate_is_reopened(self) -> None:
        assert is_open(self._start_over(), "designer")

    def test_the_override_is_offered_back(self) -> None:
        updated = self._start_over()
        assert updated["agent_llm"]["designer"] == self._ENTRY
        card = gate_card(updated, {}, "designer")
        assert _find(card, "btn-agent-llm-keep") is not None
        assert _find(card, "btn-agent-llm-default") is not None
        assert _find(card, "btn-agent-llm-pick") is not None

    def test_other_agents_keep_their_answers(self) -> None:
        assert self._start_over()["agent_llm_asked"] == {"phaser": True}

    def test_any_open_draft_is_discarded(self) -> None:
        updated = self._start_over(
            agent_llm_draft={"agent": "designer", "provider": "openai"}
        )
        assert updated["agent_llm_draft"] is None

    def test_the_wizard_waits_behind_the_gate_again(self) -> None:
        layout = designer_layout(self._start_over(), {})
        assert _find(layout, "btn-agent-llm-keep") is not None
        assert _find(layout, "designer-session-store") is None

    def test_answering_returns_to_the_wizard_intro(self) -> None:
        answered = on_gate_keep(1, {**self._start_over(), "active_agent": "designer"})
        layout = designer_layout(answered, {})
        assert _find(layout, "designer-session-store") is not None
        assert _find(layout, "btn-agent-llm-keep") is None

    def test_a_no_click_changes_nothing(self) -> None:
        from spec4.callbacks.designer import on_designer_start_over

        result = on_designer_start_over(None, {"step": 6}, _session())
        assert all(r is no_update for r in result)


# ---------------------------------------------------------------------------
# is_connected
# ---------------------------------------------------------------------------


class TestIsConnected:
    """"Can this agent send a request?", asked before the request.

    It goes through `resolve`, so it answers about the same config the turn
    will use — which is the whole point. A predicate that read
    `session["llm_config"]` directly would send a developer with a working
    per-agent override back to /setup to fix nothing.
    """

    def test_a_default_config_is_a_connection(self) -> None:
        session = {"llm_config": {"model": "m", "api_key": "k"}}
        assert llm_selection.is_connected(session, "brainstormer")

    def test_no_config_is_not(self) -> None:
        assert not llm_selection.is_connected({"llm_config": None}, "brainstormer")

    def test_an_empty_session_is_not(self) -> None:
        assert not llm_selection.is_connected({}, "brainstormer")

    def test_a_config_without_a_model_is_not(self) -> None:
        """`model` is what `_build_completion_kwargs` reads first."""
        assert not llm_selection.is_connected(
            {"llm_config": {"api_key": "k"}}, "brainstormer"
        )

    def test_credentials_beside_the_model_are_not_required(self) -> None:
        """A Bedrock config carries `aws_*` and no `api_key`; it is connected."""
        session = {
            "llm_config": {
                "model": "bedrock/anthropic.claude-v2",
                "aws_region_name": "us-east-1",
            }
        }
        assert llm_selection.is_connected(session, "brainstormer")

    def test_an_override_connects_its_own_agent(self) -> None:
        session = {
            "llm_config": None,
            "agent_llm": {
                "phaser": {"llm_config": {"model": "gpt-5", "api_key": "sk"}}
            },
        }
        assert llm_selection.is_connected(session, "phaser")
        assert not llm_selection.is_connected(session, "brainstormer")

    def test_the_remembered_prefs_are_not_consulted(self) -> None:
        """The bug: a saved provider/model made the app look connected.

        `is_connected` takes no prefs argument at all, which is the structural
        version of this assertion — these session-level echoes of the same
        values must not stand in for a config either.
        """
        session = {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "api_key": "sk-ant-xxx",
            "llm_config": None,
        }
        assert not llm_selection.is_connected(session, "brainstormer")

    def test_it_agrees_with_what_the_turn_resolves(self) -> None:
        """The contract: connected iff `resolve` yields something usable."""
        for session in (
            {},
            {"llm_config": None},
            {"llm_config": {"api_key": "k"}},
            {"llm_config": {"model": "m"}},
            {"agent_llm": {"phaser": {"llm_config": {"model": "m"}}}},
        ):
            resolved = llm_selection.resolve(session, "phaser") or {}
            assert llm_selection.is_connected(session, "phaser") == bool(
                resolved.get("model")
            )
