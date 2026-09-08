"""The two entry screens read as a file browser and a question, not a page.

The picker and the project-mode question were the last two screens still drawn
in the marketing register — a three-column grid of directory chips, an
accordion hiding a text field, a bulleted essay in front of two buttons. This
file pins what replaced them, and it pins the three things that are easy to
break while restyling them:

- the per-entry id the browse callback matches on, which a change of container
  is exactly the kind of edit that quietly renames;
- the one filled action per screen, which is the whole of the accent's job
  here (D-LR2) and is asserted as a property of the screen rather than of a
  named button;
- the length of the question, which is what made it an essay in the first place
  and is the only part of it a reviewer cannot see from a diff.

What is *not* pinned here is when the question is asked: that lives in
`needs_project_mode` and the session store, and `test_project_mode.py` owns it.
The one thing this file says about it is that the layout does not decide it —
see `TestTheQuestionIsStillAskedOncePerSession`.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

import dash_mantine_components as dmc

from spec4 import project_manager
from spec4.app_constants import PROJECT_MODE_EXISTING, PROJECT_MODE_NEW
from spec4.layouts import _agent_select_layout, _working_dir_layout
from spec4.session import _default_session

STYLESHEET = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src"
    / "spec4"
    / "assets"
    / "v3.css"
)


# ---------------------------------------------------------------------------
# Walking a rendered screen
# ---------------------------------------------------------------------------


def _flatten(component: Any) -> list[Any]:
    """Every component in a rendered tree, parents before children."""
    out: list[Any] = []

    def walk(node: Any) -> None:
        if isinstance(node, str) or node is None:
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
            return
        out.append(node)
        children = getattr(node, "children", None)
        if children is not None:
            walk(children)

    walk(component)
    return out


def _classes(component: Any) -> set[str]:
    """Every class on a component, from `className` *and* from `classNames`.

    Both are needed because Mantine sets the font on the `<input>` element
    itself: a class on a `TextInput`'s root would style the label and leave the
    field it wraps in the UI face. `classNames={"input": "mono"}` is how the
    field itself is made fixed-width, and a test that only read `className`
    would call that a missing class.
    """
    found: set[str] = set()
    value = getattr(component, "className", None)
    if isinstance(value, str):
        found.update(value.split())
    mapping = getattr(component, "classNames", None)
    if isinstance(mapping, dict):
        for names in mapping.values():
            if isinstance(names, str):
                found.update(names.split())
    return found


def _buttons(component: Any) -> list[Any]:
    return [n for n in _flatten(component) if isinstance(n, dmc.Button)]


def _filled(button: Any) -> bool:
    """Emphasised is the *absence* of a variant, per D-AR1.

    A bare `variant="outline"` takes the theme primary and, at the shade
    Mantine picks for a dark scheme, washes out to the mock's near-white
    neutral. So the one emphasised action passes no variant at all, and no
    button on either screen names a colour.
    """
    return getattr(button, "variant", None) in (None, "filled")


def _picker(tmp_path: pathlib.Path, **overrides: Any) -> Any:
    session = {**_default_session(), "browser_path": str(tmp_path)}
    session.update(overrides)
    return _working_dir_layout(session)


def _find(component: Any, component_id: Any) -> Any:
    for node in _flatten(component):
        if getattr(node, "id", None) == component_id:
            return node
    raise AssertionError(f"{component_id!r} is not on this screen")


def _question(tmp_path: pathlib.Path) -> Any:
    """The project-mode question, rendered the way the app reaches it."""
    (tmp_path / "main.py").write_text("print('hi')\n")
    session = {
        **_default_session(),
        "working_dir": str(tmp_path),
        "phase": "agent_select",
    }
    assert project_manager.needs_project_mode(tmp_path, session)
    return _agent_select_layout(session)


# ---------------------------------------------------------------------------
# The directory list
# ---------------------------------------------------------------------------


class TestTheDirectoryListIsOneColumn:
    def test_the_subdirectories_are_one_per_line(self, tmp_path: pathlib.Path) -> None:
        """One container, one entry per child, and no grid anywhere.

        `dmc.SimpleGrid` is named rather than merely absent from the assertion
        because it is what was there: a three-column grid of chips that made
        the eye scan in two directions for a name the developer already knew.
        """
        for name in ("alpha", "beta", "gamma", "delta"):
            (tmp_path / name).mkdir()
        picker = _picker(tmp_path)

        assert not [n for n in _flatten(picker) if isinstance(n, dmc.SimpleGrid)]

        entries = [
            b
            for b in _buttons(picker)
            if isinstance(getattr(b, "id", None), dict)
            and b.id.get("type") == "subdir-btn"
        ]
        assert len(entries) == 4

        stacks = [
            n
            for n in _flatten(picker)
            if isinstance(n, dmc.Stack) and "dir-list" in _classes(n)
        ]
        assert len(stacks) == 1
        children = list(stacks[0].children)
        assert children == entries, "the list is not one entry per child"
        assert [c.children for c in children] == ["alpha", "beta", "delta", "gamma"]

    def test_the_path_entry_and_the_names_are_fixed_width(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The one monospace mechanism in the app, on both halves of the screen.

        The path and the names it lists are the same kind of thing — filesystem
        text the developer compares character by character — so they are set in
        the same face, and it is `.mono` rather than a second declaration.
        """
        (tmp_path / "alpha").mkdir()
        picker = _picker(tmp_path)

        assert "mono" in _classes(_find(picker, "dir-path-input"))

        entries = [
            b
            for b in _buttons(picker)
            if isinstance(getattr(b, "id", None), dict)
            and b.id.get("type") == "subdir-btn"
        ]
        assert entries
        for entry in entries:
            assert "mono" in _classes(entry), entry.id

    def test_a_long_name_is_truncated_rather_than_wrapped(self) -> None:
        """The failure mode the single column has, answered in the stylesheet.

        Asserted against the rule rather than against a rendered line because
        the truncation is CSS and nothing else: a wrapped name would double a
        28px row and break the rhythm the column is for.
        """
        css = STYLESHEET.read_text(encoding="utf-8")
        rule = re.search(
            r"\.dir-line \[class\*=\"Button-label\"\]\s*\{(.*?)\}", css, re.S
        )
        assert rule is not None, ".dir-line's label rule is gone"
        body = rule.group(1)
        assert "text-overflow: ellipsis" in body
        assert "white-space: nowrap" in body
        assert "overflow: hidden" in body

    def test_an_empty_directory_says_so_instead_of_listing_nothing(
        self, tmp_path: pathlib.Path
    ) -> None:
        picker = _picker(tmp_path)
        assert not [
            n
            for n in _flatten(picker)
            if isinstance(n, dmc.Stack) and "dir-list" in _classes(n)
        ]
        empty = [n for n in _flatten(picker) if "dir-list-empty" in _classes(n)]
        assert len(empty) == 1
        assert "select" in str(empty[0].children).lower()


class TestBrowsingStillWorks:
    """The restyle changed the container. It must not have changed the entries.

    `on_subdir_click` reads `ctx.triggered_id["path"]` and writes it straight
    to `browser_path`, so the id is the whole of the browse behaviour. A
    renamed key or a name where an absolute path used to be would leave the
    screen looking right and navigating nowhere.
    """

    def test_each_entry_carries_the_absolute_path_the_callback_reads(
        self, tmp_path: pathlib.Path
    ) -> None:
        for name in ("alpha", "beta"):
            (tmp_path / name).mkdir()
        ids = [
            b.id
            for b in _buttons(_picker(tmp_path))
            if isinstance(getattr(b, "id", None), dict)
        ]
        assert ids == [
            {"type": "subdir-btn", "path": str(tmp_path / "alpha")},
            {"type": "subdir-btn", "path": str(tmp_path / "beta")},
        ]

    def test_hidden_directories_are_still_left_out(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / ".spec4").mkdir()
        (tmp_path / "src").mkdir()
        picker = _picker(tmp_path)
        listed = [
            b.children
            for b in _buttons(picker)
            if isinstance(getattr(b, "id", None), dict)
        ]
        assert listed == ["src"]

    def test_every_control_the_picker_callbacks_name_is_still_here(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The id contract, restated where the restyle could break it.

        `test_callback_co_presence.py` enumerates these against the whole app;
        this is the same claim scoped to the screen being reworked, so a
        dropped id fails beside the change that dropped it.
        """
        rendered = {
            getattr(n, "id", None)
            for n in _flatten(_picker(tmp_path))
            if isinstance(getattr(n, "id", None), str)
        }
        assert {
            "btn-dir-select",
            "btn-dir-up",
            "dir-path-input",
            "btn-create-folder",
            "new-folder-name",
        } <= rendered

    def test_up_is_disabled_only_at_the_filesystem_root(
        self, tmp_path: pathlib.Path
    ) -> None:
        assert _find(_picker(tmp_path), "btn-dir-up").disabled is False
        root = str(pathlib.Path(tmp_path.anchor))
        assert _find(_picker(tmp_path, browser_path=root), "btn-dir-up").disabled


# ---------------------------------------------------------------------------
# The create row, and the screen's one emphasis
# ---------------------------------------------------------------------------


class TestTheCreateRowIsOneRow:
    def test_the_option_and_its_field_share_a_row(self, tmp_path: pathlib.Path) -> None:
        """Children of one `Group`, which is what "one row" means in DMC.

        Asserted as a shared parent rather than as "both are on the screen":
        the accordion this replaced had both of them on the screen too, one of
        them behind a disclosure the developer had to open to find the other.
        """
        picker = _picker(tmp_path)
        rows = [
            n
            for n in _flatten(picker)
            if isinstance(n, dmc.Group) and "create-row" in _classes(n)
        ]
        assert len(rows) == 1
        ids = [getattr(c, "id", None) for c in rows[0].children]
        assert ids == ["btn-create-folder", "new-folder-name"]

    def test_nothing_hides_the_field_behind_a_disclosure(
        self, tmp_path: pathlib.Path
    ) -> None:
        assert not [
            n for n in _flatten(_picker(tmp_path)) if isinstance(n, dmc.Accordion)
        ]


class TestThePickerHasOneEmphasis:
    def test_select_is_the_only_filled_action(self, tmp_path: pathlib.Path) -> None:
        """The accent marks the thing the screen is for, once (D-LR2).

        Up, Create folder and the directory lines are moves *around* the
        filesystem; Select is the one that opens a project, and it is the only
        button on the screen drawn as one.
        """
        for name in ("alpha", "beta"):
            (tmp_path / name).mkdir()
        filled = [b for b in _buttons(_picker(tmp_path)) if _filled(b)]
        assert [b.id for b in filled] == ["btn-dir-select"]

    def test_every_other_action_is_a_neutral_outline(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Subtle is allowed for the directory lines and nowhere else.

        A line in a listing is not an action beside Select — it is the listing
        — which is why it is the one variant here that is neither filled nor
        outlined, and why that exception is named rather than left to widen.
        """
        (tmp_path / "alpha").mkdir()
        for button in _buttons(_picker(tmp_path)):
            if _filled(button):
                continue
            expected = "subtle" if isinstance(button.id, dict) else "outline"
            assert button.variant == expected, button.id

    def test_no_button_on_the_picker_names_a_colour(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / "alpha").mkdir()
        coloured = {
            str(b.id): b.color
            for b in _buttons(_picker(tmp_path))
            if getattr(b, "color", None) is not None
        }
        assert coloured == {}


# ---------------------------------------------------------------------------
# The project-mode question
# ---------------------------------------------------------------------------


# What fits on one line of the panel the question is drawn in — `.mode-question`
# is 560px wide and the dimmed line is 12px, which is roughly 85 characters. A
# budget rather than a measurement: it cannot see a browser, so what it really
# guards is that the explanation cannot grow back into the four-bullet essay it
# was without somebody deciding to raise it. Two elements holding a paragraph
# each would pass a count of elements and still draw six lines on screen, which
# is why the length is checked and not just the number of them.
_LINE_BUDGET = 85


class TestTheQuestionIsTwoLinesAndTwoChoices:
    def test_the_two_choices_are_one_row(self, tmp_path: pathlib.Path) -> None:
        question = _question(tmp_path)
        rows = [
            n
            for n in _flatten(question)
            if isinstance(n, dmc.Group) and "mode-choices" in _classes(n)
        ]
        assert len(rows) == 1
        ids = [getattr(c, "id", None) for c in rows[0].children]
        assert ids == ["btn-project-mode-existing", "btn-project-mode-new"]
        # And they are the only buttons on the screen: the question is a gate,
        # so nothing else may be pressable while it is unanswered.
        assert [b.id for b in _buttons(question)] == ids

    def test_exactly_one_choice_is_filled(self, tmp_path: pathlib.Path) -> None:
        buttons = _buttons(_question(tmp_path))
        filled = [b.id for b in buttons if _filled(b)]
        assert filled == ["btn-project-mode-existing"]
        assert [b.variant for b in buttons if not _filled(b)] == ["outline"]

    def test_neither_choice_names_a_colour(self, tmp_path: pathlib.Path) -> None:
        assert not [
            b.id
            for b in _buttons(_question(tmp_path))
            if getattr(b, "color", None) is not None
        ]

    def test_the_explanation_is_at_most_two_lines(self, tmp_path: pathlib.Path) -> None:
        """Two dimmed lines, each of them one line's worth of words.

        Both halves matter. Two elements holding a paragraph each would satisfy
        a count of elements and still draw six lines on screen, which is the
        shape this replaced.
        """
        lines = [
            n.children
            for n in _flatten(_question(tmp_path))
            if "dim-line" in _classes(n)
        ]
        assert len(lines) == 2
        for line in lines:
            assert isinstance(line, str)
            assert len(line) <= _LINE_BUDGET, f"{len(line)} chars: {line!r}"

    def test_the_ambiguity_and_both_paths_still_survive_the_cut(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Shorter, not vaguer. The three facts the answer depends on stay.

        A developer who cannot tell which answer is theirs will guess, and a
        wrong guess sends them down the brownfield path for a project that does
        not exist yet — which is the whole reason the question is asked.
        """
        text = " ".join(
            n.children
            for n in _flatten(_question(tmp_path))
            if "dim-line" in _classes(n)
        )
        assert "uv init" in text  # what the ambiguous case looks like
        assert "CodeScanner" in text  # what "existing" starts with
        assert "Brainstormer" in text  # what "new" starts with
        assert "asked again" in text  # and that the answer is session-scoped

    def test_the_title_is_a_sentence(self, tmp_path: pathlib.Path) -> None:
        titles = [
            n.children
            for n in _flatten(_question(tmp_path))
            if "screen-title" in _classes(n)
        ]
        assert titles == ["Is there an existing project here?"]


class TestTheQuestionIsStillAskedOncePerSession:
    """The restyle touched the layout function and nothing else.

    The guard is `needs_project_mode` reading the session store, so the way to
    break it from a layout is to draw the question regardless of the answer.
    These three cases are that failure, from both sides.
    """

    def test_an_answer_replaces_the_question_with_the_project_view(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / "main.py").write_text("x")
        for mode in (PROJECT_MODE_EXISTING, PROJECT_MODE_NEW):
            session = {
                **_default_session(),
                "working_dir": str(tmp_path),
                "phase": "agent_select",
                "project_mode": mode,
            }
            ids = {
                getattr(n, "id", None)
                for n in _flatten(_agent_select_layout(session))
                if isinstance(getattr(n, "id", None), str)
            }
            assert "btn-project-mode-existing" not in ids
            assert "agent-rows" in ids

    def test_rendering_the_question_twice_does_not_answer_it(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The layout is a pure function of the session; it writes nothing.

        A layout that recorded the answer as a side effect of drawing would
        make the question un-re-askable — and one that recorded it *wrongly*
        would answer it on the developer's behalf.
        """
        (tmp_path / "main.py").write_text("x")
        session = {
            **_default_session(),
            "working_dir": str(tmp_path),
            "phase": "agent_select",
        }
        before = dict(session)
        _agent_select_layout(session)
        _agent_select_layout(session)
        assert session == before
        assert session["project_mode"] is None
        assert project_manager.needs_project_mode(tmp_path, session)
