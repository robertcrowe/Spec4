"""The setup wizard in the dev-tool register.

The wizard was the last screen still wearing the marketing-era chrome: a title,
a paragraph explaining what a provider is, and three alert boxes carrying facts
that were never warnings. What is asserted here is the register it moved into,
not the flow it runs — the flow is unchanged, deliberately, and
``test_setup_search_provider.py`` still holds it to that.

Four of these are structural rather than cosmetic, and they are the ones worth
having:

* the fields come out of the **shared** builders, so the per-agent gate cannot
  end up with a second field register (the phase's stated failure mode);
* the step indicator comes out of the **shared** step-row renderer, so a
  re-themed accent moves the wizard's active mark with everything else's;
* the effort's values come out of ``llm_selection.offered_efforts`` and its
  choice is written through ``llm_selection.build_llm_config`` — one read path
  and one write path, which is the only thing keeping the gate and the wizard
  from disagreeing about the stored value;
* nothing in the wizard routes back to the directory picker, which is now the
  status bar's job.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Any
from unittest.mock import patch

import pytest

from spec4 import llm_selection
from spec4.app_constants import PHASE_DIRECTORY_PICKER
from spec4.callbacks import on_setup_effort_options, on_setup_model_continue
from spec4.layouts import _shared
from spec4.layouts._setup import (
    EFFORT_SCOPE_NOTICE,
    NEVER_STORED_NOTICE,
    SETUP_IDS,
    SETUP_STEP_CLASS,
    SETUP_STEPS,
    SETUP_STEPS_CLASS,
    _setup_layout,
    model_field,
    provider_key_fields,
)

CALLBACKS = (
    pathlib.Path(__file__).resolve().parent.parent / "src" / "spec4" / "callbacks"
)

# What "routes to the directory picker" looks like in a callback body: the path
# it navigates to, or the phase it puts the session in. Both are needed —
# `on_setup_back_to_dir` did both — and the phase has to be matched as the
# `phase` field rather than as a bare string, because `working_dir` is also a
# prefs key that several surviving wizard callbacks legitimately read.
_PICKER_PATH = "/dir"
_PICKER_PHASE_FIELD = f"'phase': {PHASE_DIRECTORY_PICKER!r}"

# The character classes a "directional glyph" covers: the arrow block the app's
# buttons used, plus the ASCII and guillemet stand-ins somebody would reach for
# next. The criterion is about the *mark*, not about any one codepoint.
_DIRECTIONAL = "←→⇐⇒⟵⟶◀▶‹›«»<>"


# ---------------------------------------------------------------------------
# Walking a rendered screen
# ---------------------------------------------------------------------------


def _walk(node: Any) -> list[Any]:
    """Every component in a rendered tree, the root included."""
    found = [node]
    children = getattr(node, "children", None)
    if children is None:
        return found
    if not isinstance(children, list | tuple):
        children = [children]
    for child in children:
        if hasattr(child, "children") or hasattr(child, "_prop_names"):
            found.extend(_walk(child))
    return found


def _of_type(node: Any, name: str) -> list[Any]:
    return [c for c in _walk(node) if type(c).__name__ == name]


def _ids(node: Any) -> set[str]:
    return {
        c.id
        for c in _walk(node)
        if isinstance(getattr(c, "id", None), str)
    }


def _strings(node: Any) -> list[str]:
    """Every bare string anywhere in the tree — text, labels, placeholders."""
    out: list[str] = []
    for component in _walk(node):
        for prop in ("children", "label", "placeholder", "title"):
            value = getattr(component, prop, None)
            if isinstance(value, str):
                out.append(value)
            elif isinstance(value, list | tuple):
                out.extend(v for v in value if isinstance(v, str))
    return out


def _dim_lines(node: Any) -> list[str]:
    """The text of every dimmed line on the screen, in render order."""
    lines: list[str] = []
    for component in _walk(node):
        classes = getattr(component, "className", None)
        if isinstance(classes, str) and "dim-line" in classes.split():
            text = getattr(component, "children", None)
            lines.append(text if isinstance(text, str) else str(text))
    return lines


def _buttons(node: Any) -> list[Any]:
    """The screen's Mantine buttons — the ones a variant means something on.

    Deliberately not `html.Button`, which shares the class name: the step row's
    entries are plain buttons stripped of every scrap of chrome, and counting
    them as actions would make "one filled primary" unanswerable.
    """
    return [
        c
        for c in _of_type(node, "Button")
        if type(c).__module__.startswith("dash_mantine_components")
    ]


def _button(node: Any, button_id: str) -> Any:
    return next(b for b in _buttons(node) if getattr(b, "id", None) == button_id)


def _variant(button: Any) -> str:
    """A Button's variant, with Mantine's default spelled out.

    Mantine renders a `Button` with no `variant` as `filled`, so "no variant"
    and "filled" are the same button and must be counted as one thing — which
    is the whole point of the one-primary-per-step criterion.
    """
    return getattr(button, "variant", None) or "filled"


# ---------------------------------------------------------------------------
# The three screens
# ---------------------------------------------------------------------------


def _provider_step(**prefs: Any) -> Any:
    return _setup_layout({"available_models": None, "model": None}, dict(prefs))


def _model_step(session: Any = None, prefs: Any = None) -> Any:
    base = {
        "available_models": ["gpt-5-mini", "gpt-5"],
        "model": None,
        "provider": "openai",
    }
    base.update(session or {})
    return _setup_layout(base, dict(prefs or {}))


def _search_step(session: Any = None, prefs: Any = None) -> Any:
    base = {
        "available_models": ["gpt-5-mini"],
        "model": "gpt-5-mini",
        "provider": "openai",
    }
    base.update(session or {})
    return _setup_layout(base, dict(prefs or {}))


def _steps() -> list[tuple[str, Any]]:
    return [
        ("provider", _provider_step()),
        ("model", _model_step()),
        ("search", _search_step()),
    ]


# ---------------------------------------------------------------------------
# No route back to the directory picker
# ---------------------------------------------------------------------------


def _wizard_callbacks() -> list[ast.FunctionDef]:
    """Every callback in the package whose Input is a control in the wizard.

    Parsed rather than read off the callback registry because what has to be
    checked is what the function *does* — where it routes — and the registry
    holds the wrapped callable, not its body.
    """
    wizard_ids = set().union(*(_ids(page) for _, page in _steps()))
    found: list[ast.FunctionDef] = []
    for path in sorted(CALLBACKS.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            inputs: set[str] = set()
            for decorator in node.decorator_list:
                for sub in ast.walk(decorator):
                    if (
                        isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Name)
                        and sub.func.id == "Input"
                        and sub.args
                        and isinstance(sub.args[0], ast.Constant)
                        and isinstance(sub.args[0].value, str)
                    ):
                        inputs.add(sub.args[0].value)
            if inputs & wizard_ids:
                found.append(node)
    return found


class TestNoReturnToTheDirectoryPicker:
    """The status bar's path control is the one way back (success criterion 5)."""

    def test_no_step_renders_the_removed_button(self) -> None:
        for label, page in _steps():
            assert "btn-setup-back-to-dir" not in _ids(page), label

    def test_the_callback_is_gone_too(self) -> None:
        """A stale callback on a removed id fires against nothing and throws."""
        import spec4.callbacks as callbacks

        assert not hasattr(callbacks, "on_setup_back_to_dir")

    def test_the_walk_actually_finds_the_wizards_callbacks(self) -> None:
        """A parse that matched nothing would pass the next test forever."""
        names = {node.name for node in _wizard_callbacks()}
        assert {"on_setup_connect", "on_setup_model_continue"} <= names

    def test_no_wizard_action_routes_to_the_picker(self) -> None:
        offenders = []
        for node in _wizard_callbacks():
            body = ast.unparse(node)
            if _PICKER_PATH in body or _PICKER_PHASE_FIELD in body:
                offenders.append(node.name)
        assert not offenders, f"these wizard callbacks route to the picker: {offenders}"

    def test_the_route_patterns_would_catch_the_removed_callback(self) -> None:
        """The guard's own regression test: both halves of what was deleted."""
        removed = (
            "return ({**session, 'phase': 'working_dir', "
            "'available_models': None}, '/dir')"
        )
        assert _PICKER_PATH in removed
        assert _PICKER_PHASE_FIELD in removed
        assert _PICKER_PHASE_FIELD not in "prefs.get('working_dir')"


# ---------------------------------------------------------------------------
# One filled primary per step
# ---------------------------------------------------------------------------


class TestOnePrimaryPerStep:
    @pytest.mark.parametrize("label,page", _steps())
    def test_exactly_one_filled_button(self, label: str, page: Any) -> None:
        filled = [b for b in _buttons(page) if _variant(b) == "filled"]
        assert len(filled) == 1, (
            f"{label}: expected one filled primary, got "
            f"{[getattr(b, 'id', None) for b in filled]}"
        )

    @pytest.mark.parametrize("label,page", _steps())
    def test_the_primary_takes_the_theme_accent(self, label: str, page: Any) -> None:
        """No `color` prop: the single accent is inherited, never named (D-LR2)."""
        primary = next(b for b in _buttons(page) if _variant(b) == "filled")
        assert getattr(primary, "color", None) is None, label

    def test_the_primaries_are_connect_then_continue_then_finish(self) -> None:
        labels = [
            next(b for b in _buttons(page) if _variant(b) == "filled").children
            for _, page in _steps()
        ]
        assert labels == ["Connect", "Continue", "Finish"]

    def test_clear_saved_credentials_is_a_neutral_outline_in_the_warn_tone(
        self,
    ) -> None:
        clear = _button(_provider_step(provider="openai"), "btn-setup-clear")
        assert clear.variant == "outline"
        # The tone comes from the theme through `.btn-warn`, never from a
        # `color` prop on the component — that is the D-LR2 half of it.
        assert getattr(clear, "color", None) is None
        assert "btn-warn" in (clear.className or "").split()

    @pytest.mark.parametrize(
        "back_id,page",
        [
            ("btn-setup-back-provider", _model_step()),
            ("btn-setup-back-model", _search_step()),
        ],
    )
    def test_back_is_a_neutral_outline_with_no_directional_glyph(
        self, back_id: str, page: Any
    ) -> None:
        back = _button(page, back_id)
        assert back.variant == "outline"
        assert getattr(back, "color", None) is None
        assert back.children == "Back"
        assert not set(back.children) & set(_DIRECTIONAL)

    def test_no_button_anywhere_in_the_wizard_carries_a_directional_glyph(
        self,
    ) -> None:
        offenders = []
        for label, page in _steps():
            for button in _buttons(page):
                text = button.children
                if isinstance(text, str) and set(text) & set(_DIRECTIONAL):
                    offenders.append(f"{label}: {text!r}")
        assert not offenders, offenders


# ---------------------------------------------------------------------------
# Dimmed lines, not alerts
# ---------------------------------------------------------------------------


class TestNoticesAreDimmedLines:
    def test_the_never_stored_notice_is_one_dimmed_line_under_the_key(self) -> None:
        page = _provider_step()
        lines = _dim_lines(page)
        assert lines.count(NEVER_STORED_NOTICE) == 1

    def test_the_connected_notice_is_one_dimmed_line(self) -> None:
        lines = _dim_lines(_model_step())
        assert lines.count("Connected to OpenAI") == 1

    def test_the_connected_notice_sits_above_the_model_select(self) -> None:
        page = _model_step()
        order = [
            getattr(c, "className", None) or getattr(c, "id", None)
            for c in _walk(page)
        ]
        assert order.index("dim-line") < order.index(SETUP_IDS["model"])

    @pytest.mark.parametrize("label,page", _steps())
    def test_no_step_renders_an_alert(self, label: str, page: Any) -> None:
        """With no error to show, nothing on the screen is a framed box.

        `_error` still renders a `dmc.Alert`, and should: a failed connection
        *is* an alert. Every other notice the wizard used to frame is now a
        line.
        """
        assert _of_type(page, "Alert") == [], label

    def test_an_error_still_renders_as_an_alert(self) -> None:
        """The guard above must not be passing because alerts stopped working."""
        page = _model_step({"setup_error": "Connection failed: nope"})
        assert len(_of_type(page, "Alert")) == 1

    def test_no_free_tier_notice_renders_at_all(self) -> None:
        """Deleted rather than dimmed — it does not survive as a line."""
        for prefs in ({}, {"provider": "gemini"}):
            page = _model_step({"provider": "gemini"}, prefs)
            text = " ".join(_strings(page)).lower()
            assert "free tier" not in text
            assert "pro model" not in text

    def test_no_step_carries_an_explanatory_paragraph(self) -> None:
        """One short title per step, and no prose under it.

        Asserted as a length bound rather than against the exact sentences that
        were removed: the failure mode is prose coming *back*, in whatever
        words. Dimmed lines are exempt — they are the register's way of
        carrying a fact — but they are short too, and the hint slot is empty
        until a provider callback fills it.
        """
        for label, page in _steps():
            for line in _strings(page):
                assert len(line) <= 120, f"{label}: {line!r}"


# ---------------------------------------------------------------------------
# The step indicator
# ---------------------------------------------------------------------------


class TestStepIndicator:
    def test_the_indicator_comes_from_the_shared_renderer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D-LR9: the wizard must not mark its own active step.

        Patched at the name ``_setup`` calls, so a reimplementation inside the
        module fails this even though it would render something that looks
        identical.
        """
        import spec4.layouts._setup as setup_module

        calls: list[Any] = []

        def _fake(entries: Any, **kwargs: Any) -> Any:
            calls.append((entries, kwargs))
            return _shared.step_row(entries, **kwargs)

        monkeypatch.setattr(setup_module, "step_row", _fake)
        _provider_step()
        _model_step()
        _search_step()
        assert len(calls) == 3, "a step did not go through _shared.step_row"
        for _entries, kwargs in calls:
            assert kwargs == {
                "base_class": SETUP_STEP_CLASS,
                "row_class": SETUP_STEPS_CLASS,
            }

    @pytest.mark.parametrize("active,label", list(enumerate(SETUP_STEPS)))
    def test_the_step_on_screen_is_the_marked_one(
        self, active: int, label: str
    ) -> None:
        page = _steps()[active][1]
        row = next(
            c
            for c in _walk(page)
            if getattr(c, "className", None) == SETUP_STEPS_CLASS
        )
        marked = [
            c
            for c in row.children
            if _shared.step_modifier_class(SETUP_STEP_CLASS, _shared.STEP_ACTIVE)
            in (getattr(c, "className", "") or "").split()
        ]
        assert [c.children for c in marked] == [label]

    def test_the_marks_are_the_shared_renderers_own_class_names(self) -> None:
        """Never spelled out here or in `_setup`: joined by the shared helper."""
        row = next(
            c
            for c in _walk(_model_step())
            if getattr(c, "className", None) == SETUP_STEPS_CLASS
        )
        classes = [(c.className or "").split() for c in row.children]
        assert classes == [
            [
                SETUP_STEP_CLASS,
                _shared.step_modifier_class(SETUP_STEP_CLASS, _shared.STEP_DONE),
            ],
            [
                SETUP_STEP_CLASS,
                _shared.step_modifier_class(SETUP_STEP_CLASS, _shared.STEP_ACTIVE),
            ],
            [
                SETUP_STEP_CLASS,
                _shared.step_modifier_class(
                    SETUP_STEP_CLASS, _shared.STEP_UNREACHABLE
                ),
            ],
        ]

    def test_a_step_not_yet_reachable_says_why(self) -> None:
        row = next(
            c
            for c in _walk(_provider_step())
            if getattr(c, "className", None) == SETUP_STEPS_CLASS
        )
        later = row.children[1]
        assert later.disabled is True
        assert later.title == "Finish Provider first"

    def test_no_step_in_the_row_is_a_route(self) -> None:
        """The row reports position; Back is what moves the wizard.

        An id here would either collide with the Back button's or add a second
        way to the same place, and neither is a stepper's job.
        """
        for _, page in _steps():
            row = next(
                c
                for c in _walk(page)
                if getattr(c, "className", None) == SETUP_STEPS_CLASS
            )
            assert all(getattr(c, "id", None) is None for c in row.children)


# ---------------------------------------------------------------------------
# The Effort select
# ---------------------------------------------------------------------------


class TestEffortSelect:
    def test_the_model_step_renders_an_effort_select_beside_the_model(self) -> None:
        page = _model_step()
        row = next(
            c
            for c in _walk(page)
            if "model-effort-row" in (getattr(c, "className", "") or "").split()
        )
        ids = _ids(row)
        assert SETUP_IDS["model"] in ids
        assert SETUP_IDS["effort"] in ids

    def test_the_offered_values_for_an_unseeded_provider_are_the_base_four(
        self,
    ) -> None:
        with patch(
            "spec4.llm_selection.supports_reasoning_effort", return_value=True
        ):
            page = _model_step({"provider": "cohere"})
        effort = next(
            c for c in _walk(page) if getattr(c, "id", None) == SETUP_IDS["effort"]
        )
        assert effort.data == ["default", "low", "medium", "high"]
        assert effort.value == "default"
        assert effort.disabled is False

    def test_the_values_come_from_the_shared_offered_efforts(self) -> None:
        """One source for the level list, in the layout and in the callback."""
        with patch.object(
            llm_selection, "offered_efforts", return_value=["default", "max"]
        ) as offered:
            page = _model_step({"provider": "anthropic"})
        assert offered.called
        effort = next(
            c for c in _walk(page) if getattr(c, "id", None) == SETUP_IDS["effort"]
        )
        assert effort.data == ["default", "max"]

    def test_the_value_is_keyed_on_the_resolved_provider_and_model(self) -> None:
        """D-EF4: the provider is passed, never parsed out of the model name."""
        with patch.object(
            llm_selection, "offered_efforts", return_value=["default"]
        ) as offered:
            _model_step({"provider": "openai"}, {"model": "gpt-5"})
        offered.assert_called_with("openai", "gpt-5")

    def test_a_model_without_effort_support_offers_default_alone_disabled(
        self,
    ) -> None:
        with patch(
            "spec4.llm_selection.supports_reasoning_effort", return_value=False
        ):
            page = _model_step()
        effort = next(
            c for c in _walk(page) if getattr(c, "id", None) == SETUP_IDS["effort"]
        )
        assert effort.data == ["default"]
        assert effort.disabled is True

    def test_the_stored_default_effort_prefills_the_select(self) -> None:
        with patch(
            "spec4.llm_selection.supports_reasoning_effort", return_value=True
        ):
            page = _model_step({}, {"effort": "medium"})
        effort = next(
            c for c in _walk(page) if getattr(c, "id", None) == SETUP_IDS["effort"]
        )
        assert effort.value == "medium"

    def test_the_prefill_is_read_through_the_shared_read_path(self) -> None:
        """`default_provider_model` is the (provider, model, effort) reader."""
        with patch.object(
            llm_selection,
            "default_provider_model",
            return_value=("openai", "gpt-5", "high"),
        ) as read, patch(
            "spec4.llm_selection.supports_reasoning_effort", return_value=True
        ):
            page = _model_step()
        assert read.called
        effort = next(
            c for c in _walk(page) if getattr(c, "id", None) == SETUP_IDS["effort"]
        )
        assert effort.value == "high"

    def test_the_displayed_value_is_monospace(self) -> None:
        """An effort level is an identifier the run records, like the model."""
        page = _model_step()
        effort = next(
            c for c in _walk(page) if getattr(c, "id", None) == SETUP_IDS["effort"]
        )
        assert effort.classNames == {"input": "mono"}

    def test_the_scope_of_the_choice_is_stated_once_beside_it(self) -> None:
        assert _dim_lines(_model_step()).count(EFFORT_SCOPE_NOTICE) == 1


class TestEffortOptionsFollowTheModel:
    """Instruction 8: repopulate whenever the resolved model changes."""

    def test_a_new_model_re_offers_from_the_same_function(self) -> None:
        with patch.object(
            llm_selection, "offered_efforts", return_value=["default", "low"]
        ) as offered:
            data, value, disabled = on_setup_effort_options(
                "gpt-5", "low", {"provider": "openai"}
            )
        offered.assert_called_once_with("openai", "gpt-5")
        assert data == ["default", "low"]
        assert value == "low"
        assert disabled is False

    def test_a_level_the_new_model_does_not_offer_falls_back_to_default(
        self,
    ) -> None:
        with patch.object(
            llm_selection, "offered_efforts", return_value=["default", "low"]
        ):
            _, value, _ = on_setup_effort_options("m", "xhigh", {"provider": "openai"})
        assert value == llm_selection.DEFAULT_EFFORT

    def test_a_model_without_support_disables_the_control(self) -> None:
        with patch.object(llm_selection, "offered_efforts", return_value=["default"]):
            data, value, disabled = on_setup_effort_options("m", "high", {})
        assert data == ["default"]
        assert value == "default"
        assert disabled is True

    def test_it_survives_a_session_with_no_provider_yet(self) -> None:
        with patch(
            "spec4.llm_selection.supports_reasoning_effort", return_value=True
        ):
            data, _, _ = on_setup_effort_options("m", None, None)
        assert data == ["default", "low", "medium", "high"]


class TestEffortIsWrittenThroughTheOnePath:
    """Instruction 7: the wizard sets the project DEFAULT effort, once."""

    def _continue(self, chosen: Any, prefs: Any) -> Any:
        session = {"provider": "openai", "api_key": "sk-test", "model": None}
        with patch(
            "spec4.llm_selection.probe_image_support", return_value=True
        ), patch("spec4.llm_selection.probe_tool_support", return_value=True):
            return on_setup_model_continue(1, "gpt-5", chosen, session, prefs)

    def test_the_chosen_effort_reaches_the_prefs_store(self) -> None:
        _, new_prefs, _, _, _ = self._continue("high", {"save_prefs": True})
        assert new_prefs["effort"] == "high"
        assert new_prefs["model"] == "gpt-5"

    def test_it_is_the_config_the_shared_builder_produces(self) -> None:
        """One write path: the stored config is `build_llm_config`'s output."""
        session, _, _, _, _ = self._continue("high", {"save_prefs": True})
        assert session["llm_config"] == llm_selection.build_llm_config(
            "openai", "gpt-5", "sk-test", "high"
        )
        assert session["effort"] == "high"

    def test_it_is_read_back_by_the_same_path_every_agent_reads(self) -> None:
        session, _, _, _, _ = self._continue("low", {})
        assert llm_selection.effort_for(session, "phaser") == "low"

    def test_there_is_no_second_store_key_for_the_default_effort(self) -> None:
        """The effort rides inside the config and in `effort`, and nowhere else."""
        _, new_prefs, _, _, _ = self._continue("medium", {"save_prefs": True})
        carriers = {k for k, v in new_prefs.items() if v == "medium"}
        assert carriers == {"effort"}

    def test_a_step_re_run_without_a_choice_keeps_the_remembered_one(self) -> None:
        _, new_prefs, _, _, _ = self._continue(
            None, {"save_prefs": True, "effort": "medium"}
        )
        assert new_prefs["effort"] == "medium"


# ---------------------------------------------------------------------------
# The shared field builders
# ---------------------------------------------------------------------------


class TestFieldsComeFromTheSharedBuilders:
    """The phase's stated failure mode: a gate that keeps the old field look.

    The wizard must render the *same objects* the gate does, which is only true
    if it goes through the builders rather than writing its own markup — so
    these patch the builders out and assert the screen loses its fields.
    """

    def test_the_provider_and_key_fields_come_from_provider_key_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import spec4.layouts._setup as setup_module

        monkeypatch.setattr(
            setup_module, "provider_key_fields", lambda *a, **k: []
        )
        ids = _ids(_provider_step())
        assert SETUP_IDS["provider"] not in ids
        assert SETUP_IDS["api_key"] not in ids

    def test_the_model_and_effort_fields_come_from_model_field(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import spec4.layouts._setup as setup_module
        from dash import html

        monkeypatch.setattr(setup_module, "model_field", lambda *a, **k: html.Div())
        ids = _ids(_model_step())
        assert SETUP_IDS["model"] not in ids
        assert SETUP_IDS["effort"] not in ids

    def test_the_gate_inherits_the_same_builders(self) -> None:
        """Not a copy: `_llm_gate` imports these two names and calls them."""
        import spec4.layouts._llm_gate as gate_module

        assert gate_module.provider_key_fields is provider_key_fields
        assert gate_module.model_field is model_field

    def test_both_id_sets_have_the_same_field_keys(self) -> None:
        """A key in one and not the other is a field only one screen can have."""
        from spec4.layouts._setup import GATE_IDS

        assert set(GATE_IDS) == set(SETUP_IDS)
        assert not set(GATE_IDS.values()) & set(SETUP_IDS.values())

    def test_the_builders_render_the_same_shape_for_either_id_set(self) -> None:
        from spec4.layouts._setup import GATE_IDS

        setup_fields = provider_key_fields(
            SETUP_IDS, provider_label="OpenAI", api_key="", labels=["OpenAI"]
        )
        gate_fields = provider_key_fields(
            GATE_IDS, provider_label="OpenAI", api_key="", labels=["OpenAI"]
        )
        assert [type(c).__name__ for c in setup_fields] == [
            type(c).__name__ for c in gate_fields
        ]

    def test_the_never_stored_line_reaches_the_gate_too(self) -> None:
        from spec4.layouts._setup import GATE_IDS

        fields = provider_key_fields(
            GATE_IDS, provider_label="OpenAI", api_key="", labels=["OpenAI"]
        )
        lines = [line for field in fields for line in _dim_lines(field)]
        assert NEVER_STORED_NOTICE in lines

    def test_the_effort_select_reaches_the_gate_too(self) -> None:
        from spec4.layouts._setup import GATE_IDS

        with patch(
            "spec4.llm_selection.supports_reasoning_effort", return_value=True
        ):
            row = model_field(
                GATE_IDS,
                available=["gpt-5"],
                value="gpt-5",
                provider_key="openai",
                effort="high",
            )
        effort = next(
            c for c in _walk(row) if getattr(c, "id", None) == GATE_IDS["effort"]
        )
        assert effort.value == "high"
        assert "xhigh" in effort.data


# ---------------------------------------------------------------------------
# What must not have changed
# ---------------------------------------------------------------------------


class TestTheFlowIsUnchanged:
    """Success criterion 1: fields, identifiers and validation as before."""

    def test_every_field_id_still_renders_on_its_step(self) -> None:
        assert {
            SETUP_IDS["provider"],
            SETUP_IDS["api_key"],
            SETUP_IDS["hint"],
            "setup-save-prefs",
            "btn-setup-connect",
            "btn-setup-clear",
        } <= _ids(_provider_step())
        assert {
            SETUP_IDS["model"],
            SETUP_IDS["effort"],
            "btn-setup-back-provider",
            "btn-setup-model-continue",
            "setup-probe-progress-container",
        } <= _ids(_model_step())
        assert {
            "setup-search-provider",
            "setup-search-key",
            "setup-search-hint",
            "btn-setup-back-model",
            "btn-setup-search-skip",
            "btn-setup-search-connect",
        } <= _ids(_search_step())

    def test_the_id_set_gained_only_the_effort_field(self) -> None:
        """The diff the phase's mitigation asks for, written down.

        Everything in `SETUP_IDS` before this phase is still in it, at the same
        id; `effort` is the one addition and `btn-setup-back-to-dir` — never an
        entry here — is the one removal from the screen.
        """
        assert SETUP_IDS == {
            "provider": "setup-provider",
            "api_key": "setup-api-key",
            "hint": "setup-api-key-hint",
            "model": "setup-model",
            "effort": "setup-effort",
        }
