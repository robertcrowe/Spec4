"""The shared step row: one renderer, three screens, one way to mark a step.

D-LR9 put active/done/dimmed marking in ``layouts._shared`` because the chat
frame's pipeline indicator, the setup wizard's step indicator and the Designer
wizard's step row are the same row three times, and three copies is how the
active mark ends up right on one of them and stale on the other two.

These tests drive ``step_row`` directly rather than through a screen. That is
deliberate: a test that reached the renderer through the chat frame would pass
for a chat frame that had quietly kept its own copy, which is exactly the
regression the extraction exists to prevent. The chat frame's own parity is
asserted separately, in ``test_chat_pill_bar.py``.

The labels here are nonsense on purpose. The renderer must know nothing about
agents, wizards, routes or preconditions — it is handed labels and states, and
a renderer that only worked for the seven agents would be the old code under a
new name.
"""

from __future__ import annotations

from typing import Any

from spec4.layouts._shared import (
    STEP_ACTIVE,
    STEP_DONE,
    STEP_UNREACHABLE,
    STEP_UPCOMING,
    StepEntry,
    step_modifier_class,
    step_row,
)

BASE = "widget-step"
ROW = "widget-row"


def _entries() -> list[StepEntry]:
    """One row in every state: two behind, one here, one ahead, one barred."""
    return [
        StepEntry("Alpha", STEP_DONE, id="alpha"),
        StepEntry("Beta", STEP_DONE, id="beta"),
        StepEntry("Gamma", STEP_ACTIVE),
        StepEntry("Delta", STEP_UPCOMING, id="delta"),
        StepEntry("Epsilon", STEP_UNREACHABLE, id="epsilon", tooltip="Gamma first"),
    ]


def _row(entries: list[StepEntry] | None = None) -> Any:
    return step_row(
        entries if entries is not None else _entries(),
        base_class=BASE,
        row_class=ROW,
    )


def _items(entries: list[StepEntry] | None = None) -> list[Any]:
    return list(_row(entries).children)


def _by_label(entries: list[StepEntry] | None = None) -> dict[str, Any]:
    return {node.children: node for node in _items(entries)}


def _classes(node: Any) -> set[str]:
    return set((getattr(node, "className", "") or "").split())


# ---------------------------------------------------------------------------
# The row itself
# ---------------------------------------------------------------------------


class TestTheRow:
    def test_it_is_one_element_per_entry_and_nothing_else(self) -> None:
        """No connectors. The entries are in order; an arrow adds nothing."""
        assert [node.children for node in _items()] == [
            "Alpha",
            "Beta",
            "Gamma",
            "Delta",
            "Epsilon",
        ]

    def test_the_container_wears_the_row_class_it_was_given(self) -> None:
        assert _row().className == ROW

    def test_an_empty_row_renders_empty_rather_than_raising(self) -> None:
        assert _items([]) == []


# ---------------------------------------------------------------------------
# Exactly one active, and it is marked the way the active nav item is
# ---------------------------------------------------------------------------


class TestActiveMarking:
    def test_exactly_one_entry_carries_the_active_modifier(self) -> None:
        active = step_modifier_class(BASE, STEP_ACTIVE)
        marked = [
            node.children for node in _items() if active in _classes(node)
        ]
        assert marked == ["Gamma"]

    def test_the_active_entry_is_not_a_control(self) -> None:
        """Clicking it would navigate to where the developer already is."""
        assert type(_by_label()["Gamma"]).__name__ == "Span"

    def test_every_other_entry_is_a_control(self) -> None:
        others = [node for node in _items() if node.children != "Gamma"]
        assert {type(node).__name__ for node in others} == {"Button"}

    def test_a_row_with_no_active_entry_marks_nothing_active(self) -> None:
        """A wizard that has not been entered yet is not a bug; it is a row."""
        active = step_modifier_class(BASE, STEP_ACTIVE)
        entries = [StepEntry("Alpha"), StepEntry("Beta")]
        assert not [n for n in _items(entries) if active in _classes(n)]


# ---------------------------------------------------------------------------
# Done at full weight, upcoming plain, unreachable dimmed
# ---------------------------------------------------------------------------


class TestTheOtherThreeStates:
    def test_completed_entries_carry_the_done_modifier(self) -> None:
        done = step_modifier_class(BASE, STEP_DONE)
        marked = [n.children for n in _items() if done in _classes(n)]
        assert marked == ["Alpha", "Beta"]

    def test_a_completed_entry_is_not_dimmed_or_disabled(self) -> None:
        """Full weight: the step is behind the developer, not barred to them."""
        node = _by_label()["Alpha"]
        assert step_modifier_class(BASE, STEP_UNREACHABLE) not in _classes(node)
        assert node.disabled is False

    def test_an_upcoming_entry_carries_no_modifier_at_all(self) -> None:
        """Reachable and not yet reached is what a plain label looks like."""
        assert _classes(_by_label()["Delta"]) == {BASE}
        assert _by_label()["Delta"].disabled is False

    def test_unreachable_entries_are_dimmed_and_disabled(self) -> None:
        node = _by_label()["Epsilon"]
        assert step_modifier_class(BASE, STEP_UNREACHABLE) in _classes(node)
        assert node.disabled is True

    def test_a_dimmed_entry_keeps_its_explanation_as_the_tooltip(self) -> None:
        """The only thing a dimmed label has to say for itself."""
        assert _by_label()["Epsilon"].title == "Gamma first"

    def test_an_entry_with_no_tooltip_has_none(self) -> None:
        assert _by_label()["Delta"].title is None

    def test_every_entry_carries_the_base_class(self) -> None:
        assert all(BASE in _classes(node) for node in _items())


# ---------------------------------------------------------------------------
# The ids the calling screen routes through
# ---------------------------------------------------------------------------


class TestIds:
    def test_each_control_keeps_the_id_it_was_given(self) -> None:
        ids = [n.id for n in _items() if getattr(n, "id", None) is not None]
        assert ids == ["alpha", "beta", "delta", "epsilon"]

    def test_a_dash_pattern_id_survives_unchanged(self) -> None:
        """The chat frame routes on ``{"type": "agent-pill", ...}``."""
        pattern = {"type": "agent-pill", "agent": "phaser"}
        entries = [StepEntry("Phaser", STEP_UPCOMING, id=pattern)]
        assert _items(entries)[0].id == pattern

    def test_an_entry_with_no_id_is_rendered_without_one(self) -> None:
        """Not with ``id=None``: a null id is a prop Dash would carry around."""
        entries = [StepEntry("Alpha", STEP_UPCOMING)]
        assert "id" not in _items(entries)[0].to_plotly_json()["props"]

    def test_every_control_starts_at_zero_clicks(self) -> None:
        assert all(n.n_clicks == 0 for n in _items() if n.children != "Gamma")


# ---------------------------------------------------------------------------
# Screen-agnostic: the classes are the caller's, not the renderer's
# ---------------------------------------------------------------------------


class TestItIsNotTheChatFrameInDisguise:
    def test_the_class_prefix_is_the_caller_s(self) -> None:
        """Phase 5 and Phase 7 hang their own stylesheet rules on their own
        prefix; what they share with the chat frame is which entry is marked,
        not how much padding it has."""
        row = step_row(_entries(), base_class="setup-step", row_class="setup-steps")
        assert row.className == "setup-steps"
        assert all("setup-step" in _classes(node) for node in row.children)
        assert not any("pipeline-agent" in _classes(n) for n in row.children)

    def test_the_modifier_is_derived_from_the_prefix(self) -> None:
        assert step_modifier_class("setup-step", STEP_ACTIVE) == "setup-step--active"
        assert step_modifier_class("pill", STEP_DONE) == "pill--done"

    def test_upcoming_has_no_modifier_to_derive(self) -> None:
        assert step_modifier_class(BASE, STEP_UPCOMING) == ""

    def test_it_renders_a_row_of_any_length(self) -> None:
        """Seven agents today; the setup wizard has fewer and Designer fewer
        still, and none of the three is a number written down in here."""
        entries = [StepEntry(f"Step {n}") for n in range(11)]
        assert len(_items(entries)) == 11
