"""The Designer wizard in the dev-tool register.

The wizard was the last screen still carrying the marketing-era chrome: a
paragraph introducing the agent, a "How to use Designer" accordion standing in
front of the thing it explained, a yellow filled disclaimer that was the
loudest element on the screen it was disclaiming, and a `dmc.Stepper` drawing
six circles and check marks. What is asserted here is the register it moved
into, not the flow it runs — the flow is unchanged, deliberately, and
``test_designer.py`` still holds it to that.

Four of these are structural rather than cosmetic, and they are the ones worth
having:

* the step row comes out of the **shared** step-row renderer, so a re-themed
  accent moves the wizard's active mark with the chat frame's and the setup
  wizard's;
* ``render_designer_step``'s second Output resolves against a component that is
  actually on the screen, with a property that component actually has — the
  Stepper it used to write to had an ``active``, and a plain-text row does not,
  so this is the one failure the swap could have left behind (it surfaces at
  runtime on the Designer route, never at import);
* every step has exactly one filled action, so "the button to press" is never
  a guess;
* nothing in the wizard routes out of it to the project view, which is now the
  status bar's job.
"""

from __future__ import annotations

from typing import Any

import pytest
from dash._callback import GLOBAL_CALLBACK_MAP

import spec4.app  # noqa: F401  — imported for its side effect: registering callbacks
from spec4.layouts import _shared
from spec4.layouts.designer import (
    DESIGNER_STEP_CLASS,
    DESIGNER_STEPPER_ID,
    DESIGNER_STEPS,
    DESIGNER_STEPS_CLASS,
    MOCK_APPROVED,
    MOCK_DISCLAIMER,
    _step1_content,
    _step2_content,
    _step3_content,
    _step4_content,
    _step5_content,
    _step6_content,
    _step7_content,
    designer_layout,
)
from spec4.session import _default_session

# The glyphs the wizard's buttons wore, plus the ASCII and guillemet stand-ins
# somebody would reach for next. The criterion is about the *mark*, not about
# any one codepoint.
_GLYPHS = "↺→←⇒⇐⟶⟵▶◀‹›«»"


# ---------------------------------------------------------------------------
# Walking a rendered screen
# ---------------------------------------------------------------------------


def _walk(node: Any) -> list[Any]:
    """Every component in a rendered tree, the root included."""
    if isinstance(node, list | tuple):
        found: list[Any] = []
        for item in node:
            found.extend(_walk(item))
        return found
    if not hasattr(node, "_prop_names"):
        return []
    found = [node]
    children = getattr(node, "children", None)
    if children is not None and not isinstance(children, str):
        found.extend(_walk(children))
    return found


def _of_type(node: Any, name: str) -> list[Any]:
    return [c for c in _walk(node) if type(c).__name__ == name]


def _ids(node: Any) -> set[str]:
    return {c.id for c in _walk(node) if isinstance(getattr(c, "id", None), str)}


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


def _filled(node: Any) -> list[Any]:
    return [b for b in _buttons(node) if _variant(b) == "filled"]


def _step_row(node: Any) -> Any:
    return next(
        c
        for c in _walk(node)
        if getattr(c, "className", None) == DESIGNER_STEPS_CLASS
    )


def _marked(row: Any, state: str) -> list[str]:
    """The labels in a step row carrying one state's modifier class."""
    modifier = _shared.step_modifier_class(DESIGNER_STEP_CLASS, state)
    return [
        entry.children
        for entry in row.children
        if modifier in (getattr(entry, "className", "") or "").split()
    ]


# ---------------------------------------------------------------------------
# The wizard and its seven steps
# ---------------------------------------------------------------------------


def _session(**extra: Any) -> dict[str, Any]:
    """A session whose Designer gate is answered, so the wizard renders."""
    session = _default_session()
    session.update(
        {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "api_key": "k",
            "llm_config": {"model": "claude-sonnet-4-6", "api_key": "k"},
            "phase": "designer",
            "agent_llm_asked": {"designer": True},
        }
    )
    session.update(extra)
    return session


@pytest.fixture
def page(tmp_path: Any) -> Any:
    """The wizard itself, with its gate answered.

    A working directory is not optional here: the layout resolves the round's
    design dir on every render, which is a disk read of the open project.
    """
    return designer_layout(_session(working_dir=str(tmp_path)), {})


_STORE: dict[str, Any] = {
    "step": 6,
    "preference_text": "dark and dense",
    "screenshots": [{"data": "data:image/png;base64,x", "annotation": ""}],
    "refine_images": [{"filename": "b.png", "data": "data:image/png;base64,x"}],
    "mock_html": "<html></html>",
    "finalized": False,
    "_has_existing_ui": True,
    "_is_revision": False,
}
_BUFFER: dict[str, Any] = {"tokens": 0, "progress": 0, "error": None}


def _steps() -> list[tuple[str, Any]]:
    """Every step's content, in every state the wizard can draw it in.

    The step builders are called directly rather than through
    `render_designer_step`, which reads a callback context it cannot have here
    — the same thing `test_callback_co_presence.py` does with them.
    """
    return [
        ("1 no-ui check", _step1_content()),
        ("2 start/resume", _step2_content(True, False)),
        ("2 no existing ui", _step2_content(False, False)),
        ("2 revision", _step2_content(True, True)),
        ("3 preferences", _step3_content()),
        ("4 screenshots", _step4_content(_STORE, True)),
        ("4 no image support", _step4_content(_STORE, False)),
        ("5 generating", _step5_content(_BUFFER)),
        ("6 preview", _step6_content(_STORE)),
        ("6 approved", _step6_content({**_STORE, "finalized": True})),
        ("7 refine", _step7_content(_STORE, True)),
        ("7 no image support", _step7_content(_STORE, False)),
    ]


# The two states that are genuinely an alert: a draw that failed (which is the
# retry panel's own frame) and a mock whose inputs have moved under it. They
# are excluded from the no-alert sweep for that reason, and asserted to still
# be alerts by `TestErrorsAreStillAlerts` below — a sweep that passed because
# alerts had stopped working would prove nothing.
def _warning_steps() -> list[tuple[str, Any]]:
    return [
        ("5 failed", _step5_content({**_BUFFER, "error": "boom"})),
        ("6 stale", _step6_content({**_STORE, "_stale_inputs": ["vision.json"]})),
    ]


# ---------------------------------------------------------------------------
# The step row
# ---------------------------------------------------------------------------


class TestStepRow:
    def test_the_wizard_renders_no_stepper(self, page: Any) -> None:
        """The `dmc.Stepper` is gone — circles, connectors and check icons."""
        assert _of_type(page, "Stepper") == []
        assert _of_type(page, "StepperStep") == []

    def test_the_row_comes_from_the_shared_renderer(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """D-LR9: the wizard must not mark its own active step.

        Patched at the name `designer` calls, so a reimplementation inside the
        module fails this even though it would render something that looks
        identical.
        """
        import spec4.layouts.designer as designer_module

        calls: list[Any] = []

        def _fake(entries: Any, **kwargs: Any) -> Any:
            calls.append((entries, kwargs))
            return _shared.step_row(entries, **kwargs)

        monkeypatch.setattr(designer_module, "step_row", _fake)
        designer_layout(_session(working_dir=str(tmp_path)), {})
        assert len(calls) == 1, "the wizard did not go through _shared.step_row"
        _entries, kwargs = calls[0]
        assert kwargs == {
            "base_class": DESIGNER_STEP_CLASS,
            "row_class": DESIGNER_STEPS_CLASS,
        }

    def test_exactly_one_step_is_marked_active(self, page: Any) -> None:
        row = _step_row(page)
        assert len(_marked(row, _shared.STEP_ACTIVE)) == 1

    @pytest.mark.parametrize(
        "step,label",
        [(n + 1, label) for n, label in enumerate(DESIGNER_STEPS)] + [(7, "Preview")],
    )
    def test_the_step_on_screen_is_the_marked_one(
        self, step: int, label: str
    ) -> None:
        """Every wizard step from 1 to 7, including the two that share Preview."""
        from spec4.layouts.designer import designer_step_row, stepper_index

        row = designer_step_row(stepper_index(step))
        assert _marked(row, _shared.STEP_ACTIVE) == [label]

    def test_the_row_reads_as_plain_text(self, page: Any) -> None:
        """No markers of any kind: the entries are the labels, and nothing else."""
        row = _step_row(page)
        assert [
            entry.children for entry in row.children
        ] == list(DESIGNER_STEPS)

    def test_earlier_steps_are_done_and_later_ones_dimmed(self) -> None:
        from spec4.layouts.designer import designer_step_row

        row = designer_step_row(2)
        assert _marked(row, _shared.STEP_DONE) == list(DESIGNER_STEPS[:2])
        assert _marked(row, _shared.STEP_UNREACHABLE) == list(DESIGNER_STEPS[3:])

    def test_the_marks_are_the_shared_renderers_own_class_names(self) -> None:
        """Never spelled out here or in `designer`: joined by the shared helper."""
        from spec4.layouts.designer import designer_step_row

        classes = [
            (entry.className or "").split() for entry in designer_step_row(1).children
        ]
        assert classes[0] == [
            DESIGNER_STEP_CLASS,
            _shared.step_modifier_class(DESIGNER_STEP_CLASS, _shared.STEP_DONE),
        ]
        assert classes[1] == [
            DESIGNER_STEP_CLASS,
            _shared.step_modifier_class(DESIGNER_STEP_CLASS, _shared.STEP_ACTIVE),
        ]
        assert classes[2] == [
            DESIGNER_STEP_CLASS,
            _shared.step_modifier_class(DESIGNER_STEP_CLASS, _shared.STEP_UNREACHABLE),
        ]

    def test_no_step_in_the_row_is_a_route(self, page: Any) -> None:
        """The row reports position; the controls under it move the wizard."""
        row = _step_row(page)
        assert all(getattr(entry, "id", None) is None for entry in row.children)


# ---------------------------------------------------------------------------
# The Output the Stepper left behind
# ---------------------------------------------------------------------------


def _render_designer_step_outputs() -> list[Any]:
    """Every Output of `render_designer_step`, off the real callback registry.

    Found by the registered function's own name rather than by the id string
    Dash keys the map with — that key *is* the outputs, so looking the callback
    up by it would be asserting the answer.
    """
    for spec in GLOBAL_CALLBACK_MAP.values():
        if getattr(spec.get("callback"), "__name__", None) != "render_designer_step":
            continue
        outputs = spec["output"]
        return list(outputs) if isinstance(outputs, list) else [outputs]
    raise AssertionError("render_designer_step is not a registered callback")


class TestTheStepperOutputResolves:
    """The sharp edge of the swap, pinned.

    `render_designer_step` wrote to `designer-stepper.active` — a `dmc.Stepper`
    property. A plain-text row has no such property, so replacing the component
    without moving the Output leaves the callback writing at something that is
    not there: Dash rejects the whole response, and both of this callback's
    outputs are lost, on the Designer route, at runtime.
    """

    def test_the_walk_finds_the_callback(self) -> None:
        """A registry lookup that matched nothing would pass the rest forever."""
        assert len(_render_designer_step_outputs()) == 2

    def test_every_output_names_a_component_on_the_screen(self, page: Any) -> None:
        present = _ids(page)
        missing = [
            out.component_id
            for out in _render_designer_step_outputs()
            if out.component_id not in present
        ]
        assert not missing, f"outputs with no component to write to: {missing}"

    def test_every_output_names_a_property_that_component_has(
        self, page: Any
    ) -> None:
        by_id = {
            c.id: c for c in _walk(page) if isinstance(getattr(c, "id", None), str)
        }
        offenders = [
            f"{out.component_id}.{out.component_property}"
            for out in _render_designer_step_outputs()
            if out.component_property
            not in getattr(by_id[out.component_id], "_prop_names", ())
        ]
        assert not offenders, f"outputs at properties that do not exist: {offenders}"

    def test_the_guard_would_catch_the_stepper_property(self, page: Any) -> None:
        """`active` is exactly what a plain-text row does not have."""
        row = _step_row(page)
        assert "children" in row._prop_names
        assert "active" not in row._prop_names

    def test_the_row_container_is_what_the_callback_writes(self) -> None:
        outputs = _render_designer_step_outputs()
        assert [out.component_id for out in outputs] == [
            "designer-step-content",
            DESIGNER_STEPPER_ID,
        ]
        assert outputs[1].component_property == "children"


# ---------------------------------------------------------------------------
# No accordion, no alerts, no prose
# ---------------------------------------------------------------------------


class TestNoAccordionAndNoAlerts:
    def test_the_wizard_renders_no_accordion(self, page: Any) -> None:
        """"How to use Designer" is deleted, not collapsed or moved."""
        assert _of_type(page, "Accordion") == []
        assert _of_type(page, "AccordionItem") == []

    def test_the_wizard_renders_no_introduction(self, page: Any) -> None:
        text = " ".join(
            c for c in _dim_lines(page) + [str(page)] if isinstance(c, str)
        )
        assert "Hello! I'm the" not in text
        assert "How to use Designer" not in text

    @pytest.mark.parametrize("label,content", _steps())
    def test_no_step_renders_an_alert(self, label: str, content: Any) -> None:
        assert _of_type(content, "Alert") == [], label

    def test_the_wizard_shell_renders_no_alert(self, page: Any) -> None:
        assert _of_type(page, "Alert") == []

    def test_the_disclaimer_is_one_dimmed_line_above_the_preview(self) -> None:
        for label, content in (
            ("preview", _step6_content(_STORE)),
            ("refine", _step7_content(_STORE, True)),
        ):
            lines = _dim_lines(content)
            assert lines.count(MOCK_DISCLAIMER) == 1, label
            order = [
                getattr(c, "children", None)
                if getattr(c, "className", None) == "dim-line"
                else getattr(c, "id", None)
                for c in _walk(content)
            ]
            assert order.index(MOCK_DISCLAIMER) < order.index("mock-iframe"), label

    def test_the_approved_notice_is_one_dimmed_line(self) -> None:
        approved = _step6_content({**_STORE, "finalized": True})
        assert _dim_lines(approved).count(MOCK_APPROVED) == 1

    def test_the_approved_notice_only_shows_once_approved(self) -> None:
        assert MOCK_APPROVED not in _dim_lines(_step6_content(_STORE))

    @pytest.mark.parametrize("label,content", _steps())
    def test_each_step_carries_at_most_one_instruction_line(
        self, label: str, content: Any
    ) -> None:
        """The prose is gone; what is left is short enough to be a line.

        Asserted as a length bound rather than against the exact sentences
        that were removed: the failure mode is prose coming *back*, in
        whatever words.
        """
        for line in _dim_lines(content):
            assert len(line) <= 120, f"{label}: {line!r}"


class TestErrorsAreStillAlerts:
    """The sweep above must not be passing because alerts stopped working.

    Two states are genuinely an alert and keep one: a draw that failed, and a
    mock whose inputs moved under it. Neither is a fact about the step — they
    are the two things that have actually gone wrong in this wizard.
    """

    @pytest.mark.parametrize("label,content", _warning_steps())
    def test_the_warning_states_still_frame_themselves(
        self, label: str, content: Any
    ) -> None:
        assert len(_of_type(content, "Alert")) == 1, label

    def test_the_retry_panel_still_offers_both_doors(self) -> None:
        ids = _ids(_step5_content({**_BUFFER, "error": "boom"}))
        assert {"btn-designer-retry", "btn-designer-retry-model"} <= ids


# ---------------------------------------------------------------------------
# One filled primary per step
# ---------------------------------------------------------------------------


# What each state's one filled action is. `None` is a step with no action to
# take: a draw is running, or it has failed and both of the doors out of it are
# alternatives rather than the way on.
_PRIMARIES: dict[str, str | None] = {
    "1 no-ui check": "Add a GUI",
    "2 start/resume": "Create new design",
    "2 no existing ui": "Create new design",
    "2 revision": "Carry design forward & update",
    "3 preferences": "Next",
    "4 screenshots": "Generate",
    "4 no image support": "Generate",
    "5 generating": None,
    "6 preview": "Approve",
    "6 approved": "Continue to Stack Advisor",
    "7 refine": "Regenerate",
    "7 no image support": "Regenerate",
}


class TestOnePrimaryPerStep:
    @pytest.mark.parametrize("label,content", _steps() + _warning_steps())
    def test_never_more_than_one_filled_button(
        self, label: str, content: Any
    ) -> None:
        filled = _filled(content)
        assert len(filled) <= 1, (
            f"{label}: two things to press — "
            f"{[getattr(b, 'children', None) for b in filled]}"
        )

    @pytest.mark.parametrize("label,content", _steps())
    def test_the_step_with_an_action_has_exactly_one(
        self, label: str, content: Any
    ) -> None:
        expected = _PRIMARIES[label]
        filled = [b.children for b in _filled(content)]
        assert filled == ([expected] if expected else []), label

    @pytest.mark.parametrize("label,content", _steps())
    def test_the_primary_takes_the_theme_accent(
        self, label: str, content: Any
    ) -> None:
        """No `color` prop: the single accent is inherited, never named (D-LR2)."""
        for button in _filled(content):
            assert getattr(button, "color", None) is None, label

    @pytest.mark.parametrize(
        "button_id,content",
        [
            ("btn-designer-refine", _step6_content(_STORE)),
            ("btn-designer-refine", _step6_content({**_STORE, "finalized": True})),
            ("btn-designer-refine-cancel", _step7_content(_STORE, True)),
            ("btn-designer-step-back", _step3_content()),
            ("btn-designer-step-back", _step4_content(_STORE, True)),
        ],
    )
    def test_refine_cancel_and_back_are_neutral_outlines(
        self, button_id: str, content: Any
    ) -> None:
        button = _button(content, button_id)
        assert button.variant == "outline"
        # Neutral is a bare outline: a `color` here would be a second emphasis
        # in the row, and an accent named by a layout (D-LR2).
        assert getattr(button, "color", None) is None
        assert getattr(button, "className", None) is None

    @pytest.mark.parametrize(
        "content",
        [_step6_content(_STORE), _step6_content({**_STORE, "finalized": True})],
    )
    def test_start_over_is_a_neutral_outline_in_the_warn_tone(
        self, content: Any
    ) -> None:
        start_over = _button(content, "btn-designer-start-over")
        assert start_over.variant == "outline"
        # The tone comes from the theme through `.btn-warn`, never from a
        # `color` prop on the component — that is the D-LR2 half of it.
        assert getattr(start_over, "color", None) is None
        assert "btn-warn" in (start_over.className or "").split()

    @pytest.mark.parametrize("label,content", _steps() + _warning_steps())
    def test_no_button_label_carries_a_glyph(
        self, label: str, content: Any
    ) -> None:
        offenders = [
            b.children
            for b in _buttons(content)
            if isinstance(b.children, str) and set(b.children) & set(_GLYPHS)
        ]
        assert not offenders, f"{label}: {offenders}"

    def test_the_guard_would_catch_the_removed_glyphs(self) -> None:
        """Both of the marks the wizard's buttons actually wore."""
        assert set("↺ Start Over") & set(_GLYPHS)
        assert set("Generate Mock →") & set(_GLYPHS)
        assert not set("Regenerate") & set(_GLYPHS)


# ---------------------------------------------------------------------------
# No route out of the wizard
# ---------------------------------------------------------------------------


class TestNoBackToTheProjectView:
    """The status bar's Project link is the one way out (D-LR8)."""

    def test_the_wizard_renders_no_back_to_project_button(self, page: Any) -> None:
        assert "btn-designer-back" not in _ids(page)

    def test_no_step_renders_it_either(self) -> None:
        for label, content in _steps() + _warning_steps():
            assert "btn-designer-back" not in _ids(content), label

    def test_the_callback_is_gone_too(self) -> None:
        """A stale callback on a removed id fires against nothing and throws."""
        import spec4.callbacks.designer as designer_callbacks

        assert not hasattr(designer_callbacks, "on_designer_back")

    def test_the_within_wizard_back_and_cancel_are_still_there(self) -> None:
        """Moving *inside* the wizard is what these two do, and they stay."""
        assert "btn-designer-step-back" in _ids(_step3_content())
        assert "btn-designer-step-back" in _ids(_step4_content(_STORE, True))
        assert "btn-designer-refine-cancel" in _ids(_step7_content(_STORE, True))

    @pytest.mark.parametrize("step,expected", [(3, 2), (4, 3), (2, 2)])
    def test_back_moves_one_step_and_never_leaves(
        self, step: int, expected: int
    ) -> None:
        from spec4.callbacks.designer import on_designer_step_back

        moved = on_designer_step_back(1, {**_STORE, "step": step})
        assert moved["step"] == expected


# ---------------------------------------------------------------------------
# The parts that must not have moved
# ---------------------------------------------------------------------------


class TestTheUntouchedMachinery:
    """The stores, the preview, the fullscreen control and the cost strip.

    The wizard shares its screen with a clientside progress painter and a
    clientside mock viewer that find their targets by DOM id. A restyle that
    renamed or reparented one of them would break something no other test in
    this file is looking at.
    """

    def test_the_two_stores_and_the_intervals_are_still_mounted(
        self, page: Any
    ) -> None:
        ids = _ids(page)
        assert {
            "designer-session-store",
            "mock-stream-buffer",
            "mock-stream-interval",
            "designer-autoretry-interval",
            "designer-step-content",
            DESIGNER_STEPPER_ID,
        } <= ids

    def test_the_progress_painters_targets_survive(self) -> None:
        ids = _ids(_step5_content(_BUFFER))
        assert {"mock-progress", "mock-token-count"} <= ids

    def test_the_fullscreen_button_keeps_its_id_on_both_views(self) -> None:
        for content in (_step6_content(_STORE), _step7_content(_STORE, True)):
            assert "mock-fullscreen-btn" in _ids(content)

    def test_the_upload_zones_keep_their_ids_and_their_class(self) -> None:
        drawn = _walk(_step4_content(_STORE, True)) + _walk(
            _step7_content(_STORE, True)
        )
        uploads = [c for c in drawn if type(c).__name__ == "Upload"]
        assert {u.id for u in uploads} == {
            "designer-screenshot-upload",
            "designer-refine-upload",
        }
        for upload in uploads:
            assert upload.className == "designer-upload-zone"

    def test_each_upload_zone_holds_one_dimmed_line(self) -> None:
        for content in (_step4_content(_STORE, True), _step7_content(_STORE, True)):
            upload = next(
                c for c in _walk(content) if type(c).__name__ == "Upload"
            )
            assert len(_dim_lines(upload.children)) == 1

    def test_the_cost_strip_still_closes_the_preview(self, tmp_path: Any) -> None:
        from spec4 import project_manager
        from spec4.layouts._round_cost import RUN_COST_IDS

        project_manager.save_usage(
            str(tmp_path),
            [
                {
                    "agent": "designer",
                    "model": "m",
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "cost_usd": 0.01,
                }
            ],
            0,
        )
        content = _step6_content(_STORE, _session(working_dir=str(tmp_path)))
        assert {
            RUN_COST_IDS.root,
            RUN_COST_IDS.line,
            RUN_COST_IDS.unpriced,
            RUN_COST_IDS.note,
        } <= _ids(content)
