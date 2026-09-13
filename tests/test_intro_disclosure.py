"""The shared introduction block: one renderer, two screens, one toggle.

D-LR12 gave Designer an introduction line and a closed disclosure; D-LR13 gave
the project view the same block. Both are drawn by
``layouts._shared.intro_disclosure`` and both toggles flip through
``callbacks._shared.toggle_disclosure``, so a change to either lands on both
screens at once rather than on whichever one somebody remembered.

The renderer is driven directly, with nonsense copy and ids, for the reason
``test_step_row.py`` drives ``step_row`` directly: a test that reached it
through a screen would pass for a screen that had kept its own copy. Each
screen's use of it is asserted beside that screen, in
``test_designer_wizard_register.py`` and ``test_agent_select_layout.py``.
"""

from __future__ import annotations

from typing import Any

import pytest
from dash import html, no_update
from dash._callback import GLOBAL_CALLBACK_MAP

import spec4.app  # noqa: F401  — imported for its side effect: registering callbacks
from spec4.callbacks import on_project_intro_toggle
from spec4.callbacks._shared import toggle_disclosure
from spec4.layouts import PROJECT_INTRO_BODY_ID, PROJECT_INTRO_TOGGLE_ID
from spec4.layouts._shared import (
    INTRO_BODY_CLASS,
    INTRO_TOGGLE_CLASS,
    intro_disclosure,
)
from spec4.layouts.designer import DESIGNER_INTRO_BODY_ID, DESIGNER_INTRO_TOGGLE_ID

TOGGLE = "widget-toggle"
BODY = "widget-body"


def _block(intro: str | list[str | html.Span] = "Widgets, in order.") -> Any:
    return intro_disclosure(
        intro,
        "How widgets work",
        [html.P("Alpha"), html.Ul(html.Li("Beta"))],
        toggle_id=TOGGLE,
        body_id=BODY,
    )


def _classes(component: Any) -> list[str]:
    return (getattr(component, "className", None) or "").split()


class TestIntroDisclosure:
    def test_it_is_the_line_then_the_toggle_then_the_body(self) -> None:
        names = [type(child).__name__ for child in _block().children]
        assert names == ["Text", "Button", "Collapse"]

    def test_the_line_is_the_intro_at_full_contrast(self) -> None:
        line = _block().children[0]
        assert line.children == "Widgets, in order."
        assert "dim-line" not in _classes(line)
        assert getattr(line, "c", None) is None

    def test_a_list_intro_passes_through_as_the_line_s_children(self) -> None:
        path = html.Span(".widgets/", className="mono")
        line = _block(["Under ", path, " here."]).children[0]
        assert line.children == ["Under ", path, " here."]

    def test_the_toggle_is_a_text_label_not_a_second_primary(self) -> None:
        toggle = _block().children[1]
        assert toggle.children == "How widgets work"
        assert toggle.id == TOGGLE
        assert toggle.variant == "transparent"
        assert getattr(toggle, "color", None) is None
        assert _classes(toggle) == [INTRO_TOGGLE_CLASS]

    def test_the_body_starts_closed_and_does_not_animate(self) -> None:
        collapse = _block().children[2]
        assert collapse.id == BODY
        assert collapse.opened is False
        assert collapse.transitionDuration == 0

    def test_the_body_is_dimmed_and_holds_what_it_was_handed(self) -> None:
        body = [html.P("Alpha"), html.Ul(html.Li("Beta"))]
        block = intro_disclosure("x", "y", body, toggle_id=TOGGLE, body_id=BODY)
        div = block.children[2].children
        assert type(div).__name__ == "Div"
        assert _classes(div) == ["dim-line", INTRO_BODY_CLASS]
        assert list(div.children) == body

    def test_the_stack_aligns_to_the_start(self) -> None:
        """So the toggle stays the width of its words, not a full-width bar."""
        assert _block().align == "flex-start"


def _refs(name: str) -> set[str]:
    """Every component id the registered callback ``name`` addresses.

    Found by the registered function's name, as
    ``test_designer_wizard_register.py`` finds its toggle, rather than by the
    output key Dash files it under.
    """
    for spec in GLOBAL_CALLBACK_MAP.values():
        if getattr(spec.get("callback"), "__name__", None) != name:
            continue
        outputs = spec["output"]
        outputs = outputs if isinstance(outputs, list) else [outputs]
        return {
            *(dep["id"] for dep in spec["inputs"]),
            *(dep["id"] for dep in spec["state"]),
            *(out.component_id for out in outputs),
        }
    raise AssertionError(f"{name} is not a registered callback")


class TestToggleDisclosure:
    """The flip, once, and the two callbacks over it."""

    def test_no_click_changes_nothing(self) -> None:
        assert toggle_disclosure(None, False) is no_update

    def test_the_first_click_opens_it(self) -> None:
        assert toggle_disclosure(1, False) is True

    def test_the_second_click_closes_it(self) -> None:
        assert toggle_disclosure(2, True) is False

    @pytest.mark.parametrize(
        ("n", "opened", "expected"),
        [(None, False, no_update), (1, False, True), (2, True, False)],
    )
    def test_the_project_callback_flips_as_the_helper_does(
        self, n: int | None, opened: bool, expected: Any
    ) -> None:
        assert on_project_intro_toggle(n, opened) is expected

    @pytest.mark.parametrize(
        ("name", "ids"),
        [
            (
                "on_designer_intro_toggle",
                {DESIGNER_INTRO_TOGGLE_ID, DESIGNER_INTRO_BODY_ID},
            ),
            (
                "on_project_intro_toggle",
                {PROJECT_INTRO_TOGGLE_ID, PROJECT_INTRO_BODY_ID},
            ),
        ],
    )
    def test_each_callback_names_its_two_ids_and_not_the_session(
        self, name: str, ids: set[str]
    ) -> None:
        refs = _refs(name)
        assert refs == ids
        assert "session" not in refs
