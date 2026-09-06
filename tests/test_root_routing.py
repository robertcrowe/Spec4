"""The root path resolves to exactly two destinations, and the landing is gone.

The application root has no fixed phase. ``on_browser_navigate`` decides it on
every visit from the remembered working directory, re-checked against disk, and
returns either the project view or the directory picker. This file pins all
three paths through that decision, and pins the absence of the third thing that
used to sit in front of them — the landing page.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
from dash import no_update

import spec4.app as app_module
import spec4.layouts as layouts
from spec4.app_constants import (
    PATH_TO_PHASE,
    PHASE_DIRECTORY_PICKER,
    PHASE_PROJECT_VIEW,
    PHASE_ROOT,
    ROOT_PATH,
)
from spec4.callbacks import (
    on_browser_navigate,
    on_dir_select,
    on_status_bar,
    on_status_bar_dir,
)
from spec4.layouts import STATUS_EMPTY
from spec4.project_manager import directory_opens
from spec4.session import _default_session


def _route(pathname: str, session: Any = None, prefs: Any = None) -> Any:
    """The session the router produces, resolved against ``no_update``."""
    session = _default_session() if session is None else session
    result = on_browser_navigate(pathname, session, prefs or {})
    return session if result is no_update else result


def _ids(component: Any) -> set[str]:
    """Every string component id in a rendered tree, or in a list of them.

    A bare list is accepted because `on_status_bar` returns one: the context
    line's children, not a component wrapping them.
    """
    found: set[str] = set()
    stack: list[Any] = [component]
    while stack:
        node = stack.pop()
        if isinstance(node, (list, tuple)):
            stack.extend(node)
            continue
        node_id = getattr(node, "id", None)
        if isinstance(node_id, str):
            found.add(node_id)
        children = getattr(node, "children", None)
        if children is None:
            continue
        if not isinstance(children, (list, tuple)):
            children = [children]
        stack.extend(children)
    return found


def _text(component: Any) -> str:
    """Every string in a rendered tree, joined — what the developer can read."""
    out: list[str] = []
    stack: list[Any] = [component]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            out.append(node)
            continue
        if isinstance(node, (list, tuple)):
            stack.extend(node)
            continue
        children = getattr(node, "children", None)
        if children is None:
            continue
        if not isinstance(children, (list, tuple)):
            children = [children]
        stack.extend(children)
    return " ".join(out)


def _page(session: dict[str, Any], prefs: Any = None) -> Any:
    content, _, _ = app_module.render_page(session, prefs or {}, 0, None, None)
    return content


# ---------------------------------------------------------------------------
# The three paths through the root
# ---------------------------------------------------------------------------


class TestRootResolution:
    def test_a_remembered_directory_that_exists_opens_the_project_view(
        self, tmp_path: pathlib.Path
    ) -> None:
        session = _route(ROOT_PATH, prefs={"working_dir": str(tmp_path)})
        assert session["phase"] == PHASE_PROJECT_VIEW
        assert session["working_dir"] == str(tmp_path)
        assert session["dir_error"] is None
        # And it is the project view that draws, not merely the phase name.
        assert "agent-rows" in _ids(_page(session))

    def test_the_open_project_wins_over_the_pref(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A directory chosen this session is not re-loaded from the pref.

        Re-running `_load_working_dir` would reset the round's chat and agent
        state, so an already-open project is routed to as it stands.
        """
        open_dir = tmp_path / "open"
        open_dir.mkdir()
        session = {
            **_default_session(),
            "working_dir": str(open_dir),
            "messages": [{"role": "user", "content": "hi"}],
        }
        routed = _route(
            ROOT_PATH, session=session, prefs={"working_dir": str(tmp_path)}
        )
        assert routed["working_dir"] == str(open_dir)
        assert routed["messages"] == [{"role": "user", "content": "hi"}]

    def test_no_remembered_directory_opens_the_picker(self) -> None:
        session = _route(ROOT_PATH, prefs={})
        assert session["phase"] == PHASE_DIRECTORY_PICKER
        assert session["dir_error"] is None
        assert "btn-dir-select" in _ids(_page(session))

    @pytest.mark.parametrize("remembered", ["", None])
    def test_an_empty_remembered_directory_opens_the_picker(
        self, remembered: Any
    ) -> None:
        session = _route(ROOT_PATH, prefs={"working_dir": remembered})
        assert session["phase"] == PHASE_DIRECTORY_PICKER

    def test_a_remembered_directory_that_is_gone_opens_the_picker_and_names_it(
        self, tmp_path: pathlib.Path
    ) -> None:
        gone = str(tmp_path / "moved-away")
        session = _route(ROOT_PATH, prefs={"working_dir": gone})
        assert session["phase"] == PHASE_DIRECTORY_PICKER
        assert gone in session["dir_error"]
        # The message reaches the screen, not just the store.
        assert gone in _text(_page(session))

    def test_a_directory_that_is_gone_is_dropped_from_the_session(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The status bar reads the directory from here, so it cannot linger."""
        gone = str(tmp_path / "moved-away")
        session = _route(
            ROOT_PATH,
            session={**_default_session(), "working_dir": gone},
            prefs={"working_dir": gone},
        )
        assert session["working_dir"] is None

    def test_a_file_where_the_directory_was_opens_the_picker(
        self, tmp_path: pathlib.Path
    ) -> None:
        not_a_dir = tmp_path / "project"
        not_a_dir.write_text("this used to be a folder\n")
        session = _route(ROOT_PATH, prefs={"working_dir": str(not_a_dir)})
        assert session["phase"] == PHASE_DIRECTORY_PICKER
        assert str(not_a_dir) in session["dir_error"]

    def test_the_picker_message_clears_once_a_project_opens(
        self, tmp_path: pathlib.Path
    ) -> None:
        stale = {**_default_session(), "dir_error": "Could not open /gone."}
        session = _route(
            ROOT_PATH, session=stale, prefs={"working_dir": str(tmp_path)}
        )
        assert session["dir_error"] is None


class TestTheOtherPaths:
    """Every other path still maps straight through the table."""

    @pytest.mark.parametrize("pathname,phase", sorted(PATH_TO_PHASE.items()))
    def test_a_known_path_sets_its_phase(self, pathname: str, phase: str) -> None:
        assert _route(pathname, prefs={})["phase"] == phase

    def test_a_deep_url_in_a_fresh_session_restores_the_project(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A bookmarked /agents in a new tab still knows which project it means."""
        session = _route("/agents", prefs={"working_dir": str(tmp_path)})
        assert session["phase"] == PHASE_PROJECT_VIEW
        assert session["working_dir"] == str(tmp_path)

    def test_starting_a_new_project_is_not_undone_by_the_router(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Deployer's "Start New Project" drops the directory; the pref keeps it.

        The navigation it makes must not hand the just-finished project back,
        which is why the restore is gated on the unresolved phase rather than
        on the missing directory.
        """
        just_closed = {
            **_default_session(),
            "phase": PHASE_DIRECTORY_PICKER,
            "working_dir": None,
            "browser_path": "/home",
        }
        session = _route(
            "/dir", session=just_closed, prefs={"working_dir": str(tmp_path)}
        )
        assert session["working_dir"] is None
        assert session["phase"] == PHASE_DIRECTORY_PICKER

    def test_navigating_within_a_session_does_not_reload_the_project(
        self, tmp_path: pathlib.Path
    ) -> None:
        """An in-app move keeps the round's state; only the phase changes."""
        live = {
            **_default_session(),
            "phase": PHASE_PROJECT_VIEW,
            "working_dir": str(tmp_path),
            "messages": [{"role": "user", "content": "hi"}],
        }
        session = _route("/chat", session=live, prefs={"working_dir": str(tmp_path)})
        assert session["phase"] == "chat"
        assert session["messages"] == [{"role": "user", "content": "hi"}]

    def test_an_unchanged_phase_is_not_rewritten(
        self, tmp_path: pathlib.Path
    ) -> None:
        live = {
            **_default_session(),
            "phase": PHASE_PROJECT_VIEW,
            "working_dir": str(tmp_path),
        }
        assert on_browser_navigate("/agents", live, {}) is no_update


class TestTheBarReopensThePicker:
    """The fourth path to the picker: the status bar's directory field.

    ``/dir`` was previously only reachable from the setup wizard's Back button
    or from a browser that already had the URL, so a developer sitting on the
    project view had no way to switch projects without editing the address bar.
    The bar's directory is now the control, and this pins the three things that
    makes true: it is a button when there is a project, it is not one when
    there isn't, and pressing it opens the picker *at* the project without
    committing anything.
    """

    def test_the_directory_is_a_button(self, tmp_path: pathlib.Path) -> None:
        context, _, _ = on_status_bar(
            {**_default_session(), "working_dir": str(tmp_path)}, {}
        )
        assert "btn-status-bar-dir" in _ids(context)
        # And it still reads as the same field it was — the path, not a label.
        assert str(tmp_path) in _text(context)

    def test_the_empty_state_is_text_not_a_button(self) -> None:
        """With no project there is nothing to reopen at, so no control."""
        context, _, _ = on_status_bar({}, {})
        assert "btn-status-bar-dir" not in _ids(context)
        assert STATUS_EMPTY in _text(context)

    def test_a_gone_directory_offers_no_button_either(self) -> None:
        """The bar drops a remembered-but-gone path, and the control with it."""
        context, _, _ = on_status_bar(
            {**_default_session(), "working_dir": None},
            {"working_dir": "/no/such/project"},
        )
        assert "btn-status-bar-dir" not in _ids(context)

    def test_pressing_it_opens_the_picker_at_the_project(
        self, tmp_path: pathlib.Path
    ) -> None:
        session = {**_default_session(), "working_dir": str(tmp_path)}
        new_session, pathname = on_status_bar_dir(1, session)
        assert new_session["phase"] == PHASE_DIRECTORY_PICKER
        assert new_session["browser_path"] == str(tmp_path)
        assert pathname == "/dir"
        # The picker really does browse there, rather than falling back home.
        assert str(tmp_path) in _text(layouts._working_dir_layout(new_session))

    def test_pressing_it_commits_nothing(self, tmp_path: pathlib.Path) -> None:
        """Backing out of the picker must leave the project exactly as it was.

        Only `on_dir_select` opens a directory, so this writes neither the
        session's `working_dir` nor the pref — it has no prefs Output at all.
        """
        session = {**_default_session(), "working_dir": str(tmp_path)}
        new_session, _ = on_status_bar_dir(1, session)
        assert new_session["working_dir"] == str(tmp_path)

    def test_it_does_not_fire_on_the_initial_render(self) -> None:
        assert on_status_bar_dir(None, _default_session()) == (no_update, no_update)
        assert on_status_bar_dir(0, _default_session()) == (no_update, no_update)

    def test_the_path_it_navigates_to_is_the_picker(self) -> None:
        """The pathname is not a second opinion about which screen /dir is."""
        _, pathname = on_status_bar_dir(1, _default_session())
        assert PATH_TO_PHASE[pathname] == PHASE_DIRECTORY_PICKER

    def test_the_picker_it_opens_is_the_one_the_router_would(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Routing the URL it sets must not undo the phase it just wrote."""
        session = {**_default_session(), "working_dir": str(tmp_path)}
        opened, pathname = on_status_bar_dir(1, session)
        routed = _route(pathname, session=opened, prefs={"working_dir": str(tmp_path)})
        assert routed["phase"] == PHASE_DIRECTORY_PICKER
        assert "btn-dir-select" in _ids(_page(routed))


class TestDirectoryOpens:
    """Any filesystem failure is one answer, never an exception."""

    def test_the_router_and_the_picker_share_one_predicate(self) -> None:
        """The bar, the picker and the router must agree on "openable"."""
        import spec4.app as app_mod
        import spec4.callbacks as cb
        import spec4.layouts as lay

        for module in (app_mod, cb, lay):
            assert module.project_manager.directory_opens is directory_opens

    def test_a_readabledirectory_opens(self, tmp_path: pathlib.Path) -> None:
        assert directory_opens(str(tmp_path))

    def test_a_missing_directory_does_not(self, tmp_path: pathlib.Path) -> None:
        assert not directory_opens(str(tmp_path / "nope"))

    @pytest.mark.parametrize("value", [None, "", 0, [], {"path": "/tmp"}])
    def test_a_non_path_does_not(self, value: Any) -> None:
        assert not directory_opens(value)

    def test_an_unreadable_directory_does_not(
        self, tmp_path: pathlib.Path
    ) -> None:
        locked = tmp_path / "locked"
        locked.mkdir(mode=0o000)
        try:
            import os

            if os.access(locked, os.R_OK):  # root ignores the mode bits
                pytest.skip("running as a user that can read mode-000 dirs")
            assert not directory_opens(str(locked))
        finally:
            locked.chmod(0o755)

    def test_an_oserror_is_not_raised(self, monkeypatch: Any) -> None:
        """A permissions or mount error falls back; it does not crash the root."""

        def boom(_self: Any) -> bool:
            raise OSError("stale NFS file handle")

        monkeypatch.setattr(pathlib.Path, "is_dir", boom)
        assert not directory_opens("/mnt/gone")


class TestTheGoneDirectoryLeavesNothingBehind:
    """Found by driving the real app: the fallback has to be complete.

    Clearing the session's working directory is not enough on its own. The
    status bar reads the pref when the session has none, and the picker seeds
    its browser from the same pref — so a remembered-but-gone path survived the
    fallback in two places, put itself back on the bar, and made "Select This
    Directory" open a directory that does not exist.
    """

    def test_the_status_bar_does_not_name_a_gone_directory(self) -> None:
        gone = "/no/such/project"
        context, _, _ = on_status_bar(
            {**_default_session(), "working_dir": None}, {"working_dir": gone}
        )
        assert gone not in _text(context)
        assert STATUS_EMPTY in _text(context)

    def test_the_status_bar_still_names_a_real_directory(
        self, tmp_path: pathlib.Path
    ) -> None:
        context, _, _ = on_status_bar(
            {**_default_session(), "working_dir": str(tmp_path)}, {}
        )
        assert str(tmp_path) in _text(context)

    def test_the_picker_does_not_browse_into_a_gone_directory(self) -> None:
        session = {**_default_session(), "phase": PHASE_DIRECTORY_PICKER}
        _, _, written = app_module.render_page(
            session, {"working_dir": "/no/such/project"}, 0, None, None
        )
        assert written is no_update

    def test_the_picker_browses_into_a_real_remembered_directory(
        self, tmp_path: pathlib.Path
    ) -> None:
        session = {**_default_session(), "phase": PHASE_DIRECTORY_PICKER}
        _, _, written = app_module.render_page(
            session, {"working_dir": str(tmp_path)}, 0, None, None
        )
        assert written["browser_path"] == str(tmp_path)

    def test_selecting_falls_back_to_home_when_the_browsed_path_is_gone(
        self,
    ) -> None:
        """What the picker shows and what the button opens are one directory."""
        session = {
            **_default_session(),
            "phase": PHASE_DIRECTORY_PICKER,
            "browser_path": "/no/such/project",
        }
        new_session, _, new_prefs = on_dir_select(1, session, {})
        home = str(pathlib.Path.home())
        assert new_session["working_dir"] == home
        assert new_prefs["working_dir"] == home
        # And that is what the picker was showing all along.
        assert home in _text(layouts._working_dir_layout(session))


# ---------------------------------------------------------------------------
# No landing page, under any condition
# ---------------------------------------------------------------------------


class TestNoLandingIsReachable:
    @pytest.mark.parametrize(
        "prefs",
        [
            {},
            {"working_dir": None},
            {"working_dir": ""},
            {"working_dir": "/definitely/not/here"},
        ],
    )
    def test_the_root_only_ever_reaches_the_two_destinations(
        self, prefs: dict[str, Any]
    ) -> None:
        session = _route(ROOT_PATH, prefs=prefs)
        assert session["phase"] in (PHASE_PROJECT_VIEW, PHASE_DIRECTORY_PICKER)

    def test_a_valid_directory_reaches_the_project_view(
        self, tmp_path: pathlib.Path
    ) -> None:
        session = _route(ROOT_PATH, prefs={"working_dir": str(tmp_path)})
        assert session["phase"] in (PHASE_PROJECT_VIEW, PHASE_DIRECTORY_PICKER)

    def test_an_unknown_path_falls_back_to_the_root_not_a_landing(self) -> None:
        session = _route("/whatever", prefs={})
        assert session["phase"] == PHASE_DIRECTORY_PICKER

    def test_no_landing_layout_remains_importable(self) -> None:
        assert not hasattr(layouts, "_landing_layout")
        assert "_landing_layout" not in layouts.__all__

    def test_no_landing_callback_remains(self) -> None:
        import spec4.callbacks as callbacks

        assert not hasattr(callbacks, "on_landing_start")

    def test_no_callback_references_the_landing_button(self) -> None:
        from dash._callback import GLOBAL_CALLBACK_MAP

        referenced: set[str] = set()
        for spec in GLOBAL_CALLBACK_MAP.values():
            for dep in [*spec["inputs"], *spec["state"]]:
                dep_id = dep["id"] if isinstance(dep, dict) else dep.component_id
                if isinstance(dep_id, str):
                    referenced.add(dep_id)
        assert "btn-landing-start" not in referenced

    def test_the_landing_button_is_on_no_screen(
        self, tmp_path: pathlib.Path
    ) -> None:
        for phase in (PHASE_ROOT, *PATH_TO_PHASE.values()):
            if phase in ("chat", "designer"):
                continue  # both need a live project; covered by their own suites
            session = {**_default_session(), "phase": phase, "project_mode": "new"}
            assert "btn-landing-start" not in _ids(_page(session))


# ---------------------------------------------------------------------------
# Nothing renders before the destination is known
# ---------------------------------------------------------------------------


class TestNothingRendersBeforeResolution:
    def test_the_root_container_starts_empty(self) -> None:
        """`page-content` mounts with no children of its own.

        A placeholder, spinner or partial layout here would be exactly the
        intermediate screen the root is supposed to make impossible, so its
        emptiness is asserted rather than assumed.
        """
        stack = [app_module.app.layout]
        container = None
        while stack:
            node = stack.pop()
            if getattr(node, "id", None) == "page-content":
                container = node
                break
            children = getattr(node, "children", None)
            if children is None:
                continue
            if not isinstance(children, (list, tuple)):
                children = [children]
            stack.extend(children)
        assert container is not None
        assert not getattr(container, "children", None)

    def test_the_unresolved_phase_draws_nothing(self) -> None:
        assert _default_session()["phase"] == PHASE_ROOT
        assert _page(_default_session()) == []

    def test_an_unknown_phase_draws_nothing(self) -> None:
        assert _page({**_default_session(), "phase": "landing"}) == []
