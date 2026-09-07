"""Every Download in the chat frame's action row has an Open beside it.

The Artifact Links feature's criterion is "every place a copy of a file can be
obtained from the chat frame also offers a way to open it in place". That is a
claim about a *pairing*, and the way it breaks is drift: an agent is added, its
row gets a Download, and nobody remembers the Open. So it is asserted by
walking every action row the frame can draw and comparing the two id sets,
rather than by naming the six buttons that exist today.

Three further properties, each guarding a specific failure:

* the paths the Open buttons carry are the round tree's reviewed table, not a
  second list and not the design mock's sample data, which misfiles
  ``deployment-plan.md`` — an Open that named a path the Artifact View does not
  list would be a dead link with no error anywhere to explain it;
* the click resolves its target from the id that was clicked and from the round
  as it stands at that moment, which is the mitigation for "a link opens the
  wrong file or round after a round changes mid-session";
* ``phases/`` — the one entry that stands for many files — resolves to a phase
  file that is actually in the round's allowed set, since the directory itself
  drops out of that set as soon as Phaser has written anything into it.
"""

from __future__ import annotations

import pathlib
from typing import Any
from unittest.mock import patch

import dash_mantine_components as dmc
from dash import no_update

from spec4 import project_manager
from spec4.callbacks import (
    OPEN_ARTIFACT_CALLBACKS,
    _open_target,
    on_round_tree_line,
    select_artifact,
)
from spec4.layouts._artifact_view import RESOLUTION_PRESENT, resolve_artifact
from spec4.layouts._chat import (
    CHAT_ARTIFACTS,
    DOWNLOAD_BTN_PREFIX,
    OPEN_BTN_PREFIX,
    _chat_action_buttons,
    open_button_id,
)
from spec4.layouts._round_tree import ARTIFACT_LANES, PHASES_DIR
from spec4.session import _default_session

from tests.test_chat_action_row_emphasis import _rows


class _FakeCtx:
    """Stand-in for ``dash.ctx`` carrying only the triggered id.

    The same stand-in ``tests/test_round_tree.py`` uses for the tree's line
    click, because these two callbacks resolve their target the same way and
    for the same reason.
    """

    def __init__(self, triggered_id: Any) -> None:
        self.triggered_id = triggered_id


def _open(key: str, session: Any, n_clicks: Any = 1) -> Any:
    """Click ``btn-open-<key>``, the way Dash would deliver it."""
    with patch("spec4.callbacks.ctx", _FakeCtx(open_button_id(key))):
        return OPEN_ARTIFACT_CALLBACKS[key](n_clicks, session)


def _buttons(session: dict[str, Any]) -> list[Any]:
    """The row's buttons, in render order."""
    rendered = _chat_action_buttons(session)
    children = rendered.children or []
    group = next(c for c in children if isinstance(c, dmc.Group))
    return [c for c in group.children if isinstance(c, dmc.Button)]


def _suffixes(session: dict[str, Any], prefix: str) -> list[str]:
    return [
        button.id[len(prefix) :]
        for button in _buttons(session)
        if isinstance(button.id, str) and button.id.startswith(prefix)
    ]


# ---------------------------------------------------------------------------
# The pairing
# ---------------------------------------------------------------------------


class TestEveryDownloadHasAnOpen:
    def test_the_walk_covers_every_row(self) -> None:
        """A generator that quietly produced nothing would pass forever."""
        rows = _rows()
        assert len(rows) == 10
        assert [name for name, session in rows if _buttons(session)] == [
            name for name, _ in rows
        ]

    def test_each_row_pairs_its_downloads_one_to_one(self) -> None:
        mismatched = []
        for name, session in _rows():
            downloads = _suffixes(session, DOWNLOAD_BTN_PREFIX)
            opens = _suffixes(session, OPEN_BTN_PREFIX)
            if downloads != opens:
                mismatched.append(f"{name}: download {downloads}, open {opens}")
        assert not mismatched, "Download/Open pairing broken in:\n" + "\n".join(
            mismatched
        )

    def test_the_pairing_is_not_vacuously_empty(self) -> None:
        """Every completed run downloads something, so every completed run
        opens something — a pairing of two empty sets would pass above."""
        for name, session in _rows():
            if "complete" not in name:
                continue
            assert _suffixes(session, DOWNLOAD_BTN_PREFIX), name

    def test_the_open_precedes_the_download_it_belongs_to(self) -> None:
        """The mock's order: read it, then take a copy of it."""
        for name, session in _rows():
            ids = [b.id for b in _buttons(session) if isinstance(b.id, str)]
            for key in _suffixes(session, OPEN_BTN_PREFIX):
                assert ids.index(open_button_id(key)) + 1 == ids.index(
                    f"{DOWNLOAD_BTN_PREFIX}{key}"
                ), f"{name}: {key}"

    def test_every_mapped_artifact_is_reachable_from_some_row(self) -> None:
        """The mapping is the row's, not a wish list: a key nothing renders
        would leave a callback registered for a button that never exists."""
        rendered = {
            key for _, session in _rows() for key in _suffixes(session, OPEN_BTN_PREFIX)
        }
        assert rendered == set(CHAT_ARTIFACTS)


class TestTheOpenButtonsRegister:
    """Neutral outlines, no colour (D-LR2). The row's one emphasis is its
    continue, and `tests/test_chat_action_row_emphasis.py` holds that rule for
    the row as a whole; what is checked here is that these particular buttons
    do not reach for the accent by naming it."""

    def _open_buttons(self) -> list[Any]:
        return [
            button
            for _, session in _rows()
            for button in _buttons(session)
            if isinstance(button.id, str) and button.id.startswith(OPEN_BTN_PREFIX)
        ]

    def test_each_is_an_uncoloured_outline(self) -> None:
        buttons = self._open_buttons()
        assert buttons
        for button in buttons:
            assert button.variant == "outline", button.id
            assert getattr(button, "color", None) is None, button.id

    def test_each_names_the_file_it_opens(self) -> None:
        for button in self._open_buttons():
            key = button.id[len(OPEN_BTN_PREFIX) :]
            assert button.children == f"Open {CHAT_ARTIFACTS[key]}"


# ---------------------------------------------------------------------------
# The paths come from the round tree
# ---------------------------------------------------------------------------


class TestTheTargetsAreTheTreesArtifacts:
    def test_every_target_is_a_reviewed_artifact(self) -> None:
        """`_round_tree.ROUND_ARTIFACTS` is the app's one artifact-to-lane
        table. The design mock's own sample data misfiles
        `deployment-plan.md`, so it is not a source for anything here."""
        assert set(CHAT_ARTIFACTS.values()) <= set(ARTIFACT_LANES)

    def test_no_existing_download_id_was_renamed(self) -> None:
        """The Open buttons are new ids beside the old ones, which is what
        keeps every download callback and its tests working untouched."""
        for name, session in _rows():
            for key in _suffixes(session, DOWNLOAD_BTN_PREFIX):
                assert f"{DOWNLOAD_BTN_PREFIX}{key}" in [
                    b.id for b in _buttons(session)
                ], name


# ---------------------------------------------------------------------------
# What a click writes
# ---------------------------------------------------------------------------


def _project(root: pathlib.Path, version: int = 0) -> pathlib.Path:
    directory = project_manager.ensure_version_dir(root, version)
    (directory / "stack.json").write_text("{}", encoding="utf-8")
    return directory


class TestSelectionIsWrittenThroughOneHelper:
    """The round tree's lines and the Open buttons write the same two keys,
    through the same function — so a change to what "selected" means cannot
    land on one door into the Artifact View and not the other."""

    def test_it_writes_exactly_the_two_selection_keys(self) -> None:
        session = _default_session()
        written = select_artifact(session, 3, "stack.json")
        assert written["selected_round"] == 3
        assert written["selected_file"] == "stack.json"
        changed = {k for k in written if written[k] != session.get(k)}
        assert changed == {"selected_round", "selected_file"}

    def test_it_does_not_mutate_the_session_it_was_given(self) -> None:
        """The session is a `dcc.Store` value: Dash pushes an update the
        browser can see only when a *new* object comes back."""
        session = _default_session()
        select_artifact(session, 3, "stack.json")
        assert session.get("selected_file") is None

    def test_both_doors_write_the_same_two_keys(self, tmp_path: pathlib.Path) -> None:
        """A tree line and an Open button, on the same file, are the same
        selection — which is what "reuse the round tree's helper" buys."""
        _project(tmp_path)
        session = {**_default_session(), "working_dir": str(tmp_path)}
        with patch(
            "spec4.callbacks.ctx",
            _FakeCtx({"type": "round-tree-line", "index": "stack.json"}),
        ):
            from_tree, tree_path = on_round_tree_line([1], session)
        from_button, button_path = _open("stack", session)
        assert from_tree == from_button == select_artifact(session, 0, "stack.json")
        assert tree_path == button_path == "/artifacts"


class TestPhasesResolvesToAPhaseFile:
    """`phases/` stands for many files. `allowed_artifacts` expands it into the
    files on disk, which means the directory itself leaves the allowed set the
    moment Phaser writes anything — so an Open that selected `phases/` would
    land on a rejection immediately after a finished Phaser run."""

    def test_an_empty_round_keeps_the_directory(self, tmp_path: pathlib.Path) -> None:
        _project(tmp_path)
        assert _open_target(str(tmp_path), 0, PHASES_DIR) == PHASES_DIR

    def test_a_written_round_resolves_to_the_first_phase(
        self, tmp_path: pathlib.Path
    ) -> None:
        directory = _project(tmp_path)
        (directory / "phases").mkdir()
        for n in (2, 10, 1):
            (directory / "phases" / f"phase{n}.md").write_text("x", encoding="utf-8")
        target = _open_target(str(tmp_path), 0, PHASES_DIR)
        assert target == "phases/phase1.md"
        # And it is a file the Artifact View will actually open.
        assert resolve_artifact(str(tmp_path), 0, target).outcome == RESOLUTION_PRESENT

    def test_it_is_resolved_at_click_time_not_at_render(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The failure this guards: Phaser finishes while the page is open, so
        the phase files that exist when the button is clicked are not the ones
        that existed when the row was drawn."""
        directory = _project(tmp_path)
        assert _open_target(str(tmp_path), 0, PHASES_DIR) == PHASES_DIR
        (directory / "phases").mkdir()
        (directory / "phases" / "phase1.md").write_text("x", encoding="utf-8")
        assert _open_target(str(tmp_path), 0, PHASES_DIR) == "phases/phase1.md"

    def test_every_other_target_passes_through_untouched(
        self, tmp_path: pathlib.Path
    ) -> None:
        _project(tmp_path)
        for path in CHAT_ARTIFACTS.values():
            if path == PHASES_DIR:
                continue
            assert _open_target(str(tmp_path), 0, path) == path


# ---------------------------------------------------------------------------
# Clicking Open
# ---------------------------------------------------------------------------


class TestClickingOpen:
    def test_it_lands_on_the_artifact_view_with_the_file_selected(
        self, tmp_path: pathlib.Path
    ) -> None:
        _project(tmp_path)
        session = {**_default_session(), "working_dir": str(tmp_path)}
        new_session, pathname = _open("stack", session)
        assert new_session["selected_file"] == "stack.json"
        assert new_session["selected_round"] == 0
        assert pathname == "/artifacts"

    def test_every_button_opens_its_own_artifact(self, tmp_path: pathlib.Path) -> None:
        _project(tmp_path)
        session = {**_default_session(), "working_dir": str(tmp_path)}
        opened = {
            key: _open(key, session)[0]["selected_file"] for key in CHAT_ARTIFACTS
        }
        assert opened == dict(CHAT_ARTIFACTS)

    def test_the_round_is_the_round_at_click_time(self, tmp_path: pathlib.Path) -> None:
        """The failure this guards: an agent finishes and starts a new round
        while the frame is on screen, and a target captured at render would
        open the previous round's file."""
        _project(tmp_path, version=0)
        session = {**_default_session(), "working_dir": str(tmp_path)}
        assert _open("stack", session)[0]["selected_round"] == 0
        _project(tmp_path, version=1)
        assert _open("stack", session)[0]["selected_round"] == 1

    def test_the_target_comes_from_the_triggered_id(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Not from the key the handler was registered with: a handler asked
        about a different button answers about that button."""
        _project(tmp_path)
        session = {**_default_session(), "working_dir": str(tmp_path)}
        with patch("spec4.callbacks.ctx", _FakeCtx(open_button_id("vision"))):
            written, _ = OPEN_ARTIFACT_CALLBACKS["stack"](1, session)
        assert written["selected_file"] == "vision.json"

    def test_an_unrecognised_trigger_writes_nothing(
        self, tmp_path: pathlib.Path
    ) -> None:
        session = {**_default_session(), "working_dir": str(tmp_path)}
        for triggered in (None, "btn-open-nonesuch", {"type": "round-tree-line"}):
            with patch("spec4.callbacks.ctx", _FakeCtx(triggered)):
                assert OPEN_ARTIFACT_CALLBACKS["stack"](1, session) == (
                    no_update,
                    no_update,
                )

    def test_a_render_with_no_click_writes_nothing(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Dash fires a callback when the component set changes, and every
        session change rebuilds the frame — so without this, simply drawing a
        completed run would navigate away from it."""
        _project(tmp_path)
        session = {**_default_session(), "working_dir": str(tmp_path)}
        assert _open("stack", session, n_clicks=None) == (no_update, no_update)
        assert _open("stack", session, n_clicks=0) == (no_update, no_update)

    def test_no_project_open_is_not_an_error(self) -> None:
        """No working directory means no round — the file is still recorded,
        exactly as the round tree's line click records it."""
        new_session, pathname = _open("stack", _default_session())
        assert new_session["selected_file"] == "stack.json"
        assert new_session["selected_round"] is None
        assert pathname == "/artifacts"

    def test_an_empty_session_is_not_an_error(self) -> None:
        new_session, pathname = _open("stack", None)
        assert new_session["selected_file"] == "stack.json"
        assert pathname == "/artifacts"

    def test_the_selected_file_resolves_in_the_artifact_view(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The end of the link: what the button writes is what the Artifact
        View opens, without a rejection in between."""
        _project(tmp_path)
        session = {**_default_session(), "working_dir": str(tmp_path)}
        written, _ = _open("stack", session)
        result = resolve_artifact(
            str(tmp_path), written["selected_round"], written["selected_file"]
        )
        assert result.outcome == RESOLUTION_PRESENT

    def test_each_button_is_registered_with_the_page_load_guard(self) -> None:
        """`prevent_initial_call=True`, asserted on the registrations."""
        from dash._callback import GLOBAL_CALLBACK_LIST

        for key in CHAT_ARTIFACTS:
            registered = [
                spec
                for spec in GLOBAL_CALLBACK_LIST
                if any(dep.get("id") == open_button_id(key) for dep in spec["inputs"])
            ]
            assert len(registered) == 1, key
            assert registered[0]["prevent_initial_call"] is True, key
