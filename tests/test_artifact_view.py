"""The Artifact View: the route to it, the resolver behind it, and the screen.

Four things are pinned here, in the order the developer meets them.

*The route.* ``PATH_TO_PHASE`` turns the URL into a phase and ``render_page``
turns the phase into a screen, and updating only one of them produces a route
that resolves to a blank page with no error anywhere — nothing raises, nothing
logs, the developer just gets an empty shell. So both are asserted, and
asserted together: the last test in ``TestTheRoute`` walks the URL all the way
to the rendered ids rather than stopping at the phase name.

*The resolver.* Every read this screen makes goes through ``resolve_artifact``,
so the confinement claim is checkable in one place. ``TestPathConfinement``
asserts not only that a bad path is refused but that the filesystem was never
touched for it — the check *ordering* is the security property, and a test that
only looked at the outcome would pass against a stat that had crept above the
allow-list.

*The rendering.* A JSON artifact is pretty-printed; everything else, Markdown
included, is shown exactly as written; both are numbered by a gutter whose line
count equals the content's. The gutter is two ``<pre>`` elements rather than a
component per line, and ``TestTheContentPane`` asserts that as a property of
the component tree — a per-line tree is the implementation that makes a large
artifact hang the browser, and it is the one an editor reaches for by default.

*The round switch.* Selecting a file and then switching to a round that does
not have it must clear the selection rather than leave the pane rendering a
rejection for a line the tree beside it is not drawing.
"""

from __future__ import annotations

import json
import pathlib
import re
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from dash import no_update

import spec4.app as app_module
import spec4.callbacks as artifact_view_callbacks
import spec4.layouts._artifact_view as artifact_view
from spec4 import project_manager
from spec4.app_constants import AGENT_KEYS, PATH_TO_PHASE, PHASE_ROOT
from spec4.callbacks import (
    on_artifact_download,
    on_artifact_pane,
    on_artifact_round,
    on_browser_navigate,
    on_round_tree_line,
    on_status_bar,
)
from spec4.layouts import _artifact_view_layout
from spec4.layouts._agent_rows import AGENT_DISPLAY_NAMES
from spec4.layouts._artifact_view import (
    BODY_ID,
    DOWNLOAD_BTN_ID,
    DOWNLOAD_ID,
    EMPTY_CONTENT,
    HEADER_ID,
    MOCK_HTML_PATH,
    MOCK_STORE_ID,
    OPEN_RENDERED_BTN_ID,
    RESOLUTION_MISSING,
    RESOLUTION_PRESENT,
    RESOLUTION_REJECTED,
    ROUND_SELECT_ID,
    ROUND_TYPE,
    SCROLL_ID,
    ArtifactResolution,
    allowed_artifacts,
    artifact_controls,
    artifact_pane,
    line_numbered,
    missing_message,
    mock_html_for_store,
    rejection_message,
    rendered_text,
    resolve_artifact,
    round_id,
    round_value,
    selected_round,
)
from spec4.layouts._round_tree import (
    ARTIFACT_LANES,
    ARTIFACT_TREE_IDS,
    LANE_LABELS,
    PHASES_DIR,
    PROJECT_TREE_IDS,
    ROUND_ARTIFACTS,
    line_id,
    rendered_tree_lines,
)
from spec4.layouts._status_bar import ARTIFACTS_PATH, NAV_ORDER, _status_bar
from spec4.session import _default_session

# Every reviewed artifact whose relative path is the same in every round. The
# ``phases/`` entry is deliberately not here: it is the one entry that stands
# for a set of files that differs round by round, and it is what the
# expansion tests are about.
FIXED_ARTIFACTS = [a.path for a in ROUND_ARTIFACTS if a.path != PHASES_DIR]

# The phase key the route resolves to, and the screen `render_page` draws for
# it. Written once here so a rename has to be made deliberately in both files.
ARTIFACTS_PHASE = "artifacts"


class _TriggeredBy:
    """A stand-in for Dash's ``ctx`` carrying one triggered pattern id.

    Both of this screen's click callbacks read what was clicked out of
    ``ctx.triggered_id`` and from nowhere else — that is the mitigation for a
    control resolving to the state it was *rendered* in rather than the state
    it was clicked in — so driving either from a test means supplying that one
    attribute.
    """

    def __init__(self, triggered_id: dict[str, Any]) -> None:
        self.triggered_id = triggered_id


def _ids(component: Any) -> set[str]:
    """Every string component id in a rendered tree."""
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
    """Every string in a rendered tree, joined — what a developer can read.

    Depth-first and left to right, so the result is in reading order. Several
    assertions below are about *order* — the header's four fields, the
    filename at the head of a missing-file sentence — and a walk that visited
    siblings backwards would quietly reverse both while still containing every
    word they looked for.
    """
    out: list[str] = []
    if isinstance(component, str):
        return component
    if isinstance(component, (list, tuple)):
        return " ".join(part for part in (_text(c) for c in component) if part)
    children = getattr(component, "children", None)
    if children is None:
        return ""
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        part = _text(child)
        if part:
            out.append(part)
    return " ".join(out)


def _pattern_ids(component: Any) -> list[dict[str, str]]:
    """Every dict (pattern-matching) component id in a rendered tree."""
    found: list[dict[str, str]] = []
    stack: list[Any] = [component]
    while stack:
        node = stack.pop()
        if isinstance(node, (list, tuple)):
            stack.extend(node)
            continue
        node_id = getattr(node, "id", None)
        if isinstance(node_id, dict):
            found.append(node_id)
        children = getattr(node, "children", None)
        if children is None:
            continue
        if not isinstance(children, (list, tuple)):
            children = [children]
        stack.extend(children)
    return found


def _by_id(component: Any, wanted: str) -> Any:
    """The one node carrying `wanted` as its id."""
    stack: list[Any] = [component]
    while stack:
        node = stack.pop()
        if isinstance(node, (list, tuple)):
            stack.extend(node)
            continue
        if getattr(node, "id", None) == wanted:
            return node
        children = getattr(node, "children", None)
        if children is None:
            continue
        if not isinstance(children, (list, tuple)):
            children = [children]
        stack.extend(children)
    raise AssertionError(f"no component with id {wanted!r}")


def _nodes(component: Any) -> list[Any]:
    """Every component in a rendered tree, in document order.

    Depth-first and left to right, because two of the assertions below are
    about *order* — the gutter comes before the content it numbers, and the
    header's four fields run path, size, modified, lane. A stack-based walk
    would visit siblings backwards and quietly reverse both.
    """
    out: list[Any] = []
    if isinstance(component, (list, tuple)):
        for child in component:
            out.extend(_nodes(child))
        return out
    if isinstance(component, str) or component is None:
        return out
    out.append(component)
    children = getattr(component, "children", None)
    if children is not None:
        out.extend(_nodes(children))
    return out


def _pres(component: Any) -> list[Any]:
    """The ``<pre>`` elements in a rendered tree, gutter first."""
    return [n for n in _nodes(component) if type(n).__name__ == "Pre"]


def _sentence(component: Any) -> str:
    """`_text` with its whitespace normalised.

    `_text` joins sibling strings with a space, so a span followed by a text
    node that already starts with one — ``<span>a.md</span> — missing`` — comes
    back with two. The browser renders one; this collapses runs so a test can
    assert the sentence a developer actually reads.
    """
    return " ".join(_text(component).split())


def _gutter_and_content(body: Any) -> tuple[str, str]:
    """The two strings the file block is built from."""
    pres = _pres(body)
    assert len(pres) == 2, f"expected a gutter and a content pre, got {len(pres)}"
    return pres[0].children, pres[1].children


def _nav(bar: Any) -> Any:
    """The status bar's ``<nav>``."""
    stack = [bar]
    while stack:
        node = stack.pop()
        if type(node).__name__ == "Nav":
            return node
        children = getattr(node, "children", None)
        if children is None:
            continue
        if not isinstance(children, (list, tuple)):
            children = [children]
        stack.extend(children)
    raise AssertionError("the status bar has no nav")


def _nav_labels() -> list[str]:
    """The nav's link labels, in render order."""
    return [
        child.children
        for child in _nav(_status_bar()).children
        if type(child).__name__ in ("Link", "A")
    ]


def _page(session: dict[str, Any]) -> Any:
    content, _, _ = app_module.render_page(session, {}, 0, None, None)
    return content


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


class TestTheRoute:
    def test_the_path_is_in_the_routing_table(self) -> None:
        assert ARTIFACTS_PATH in PATH_TO_PHASE
        assert PATH_TO_PHASE[ARTIFACTS_PATH] == ARTIFACTS_PHASE

    def test_no_existing_route_was_renamed_or_repointed(self) -> None:
        """The table gained an entry; it did not lose or move one."""
        assert PATH_TO_PHASE["/dir"] == "working_dir"
        assert PATH_TO_PHASE["/setup"] == "setup"
        assert PATH_TO_PHASE["/agents"] == "agent_select"
        assert PATH_TO_PHASE["/chat"] == "chat"
        assert PATH_TO_PHASE["/design"] == "designer"

    def test_the_router_sets_the_phase(self) -> None:
        session = on_browser_navigate(ARTIFACTS_PATH, _default_session(), {})
        assert session is not no_update
        assert session["phase"] == ARTIFACTS_PHASE

    def test_a_bookmarked_url_restores_the_project(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A deep /artifacts in a fresh tab still knows which project it means.

        The same restore every other deep path gets — the screen is about a
        round's files, so arriving without a working directory would leave it
        with nothing to resolve against.
        """
        session = on_browser_navigate(
            ARTIFACTS_PATH, _default_session(), {"working_dir": str(tmp_path)}
        )
        assert session["phase"] == ARTIFACTS_PHASE
        assert session["working_dir"] == str(tmp_path)

    def test_the_route_actually_draws_the_screen(self) -> None:
        """Both registration points, walked end to end.

        The failure this closes is silent: a path in the table with no branch
        in ``render_page`` falls through to the empty container that
        ``PHASE_ROOT`` uses, so the URL resolves, no error is raised, and the
        developer gets a blank shell. Asserting the phase name alone would
        pass against exactly that.
        """
        session = on_browser_navigate(ARTIFACTS_PATH, _default_session(), {})
        assert "artifact-view-root" in _ids(_page(session))

    def test_it_is_not_the_unresolved_phase(self) -> None:
        """A screen that draws nothing is what ``PHASE_ROOT`` is for."""
        assert PATH_TO_PHASE[ARTIFACTS_PATH] != PHASE_ROOT
        assert _page({**_default_session(), "phase": PHASE_ROOT}) == []


# ---------------------------------------------------------------------------
# The navigation entry
# ---------------------------------------------------------------------------


class TestTheNavEntry:
    def test_the_entry_is_present(self) -> None:
        assert "Artifacts" in _nav_labels()
        assert "status-bar-nav-artifacts" in _ids(_status_bar())

    def test_it_sits_between_project_and_settings(self) -> None:
        """The order the Artifact Links specification fixes."""
        labels = _nav_labels()
        assert labels.index("Project") < labels.index("Artifacts")
        assert labels.index("Artifacts") < labels.index("Settings")

    def test_the_declared_order_says_the_same_thing(self) -> None:
        assert NAV_ORDER.index("Artifacts") == NAV_ORDER.index("Project") + 1
        assert NAV_ORDER.index("Settings") == NAV_ORDER.index("Artifacts") + 1

    def test_it_points_at_the_route(self) -> None:
        entry = next(
            child
            for child in _nav(_status_bar()).children
            if getattr(child, "id", None) == "status-bar-nav-artifacts"
        )
        assert entry.href == ARTIFACTS_PATH
        assert PATH_TO_PHASE[entry.href] == ARTIFACTS_PHASE

    def test_it_is_plain_text_with_no_colour_of_its_own(self) -> None:
        """D-LR2: the accent arrives from the theme primary, never from here."""
        entry = next(
            child
            for child in _nav(_status_bar()).children
            if getattr(child, "id", None) == "status-bar-nav-artifacts"
        )
        assert entry.children == "Artifacts"
        assert getattr(entry, "color", None) is None
        assert getattr(entry, "style", None) is None

    def test_the_nav_is_the_same_on_every_screen(self) -> None:
        """The bar is mounted once in the shell, so the entry cannot be missing
        from a screen that should offer it — asserted rather than assumed."""
        assert "status-bar-nav-artifacts" in _ids(app_module.app.layout)

    def test_it_shows_as_active_on_the_artifact_view(self) -> None:
        _, project, artifacts, settings = on_status_bar(
            {**_default_session(), "phase": ARTIFACTS_PHASE}, {}
        )
        assert "active" in artifacts
        assert "active" not in project
        assert "active" not in settings


# ---------------------------------------------------------------------------
# The screen
# ---------------------------------------------------------------------------


class TestTheScreen:
    def test_it_renders_the_three_new_ids(self) -> None:
        ids = _ids(_artifact_view_layout(_default_session()))
        assert {
            "artifact-view-root",
            "artifact-view-sidebar",
            "artifact-view-content",
        } <= ids

    def test_it_is_two_panes_on_one_grid(self) -> None:
        """The mock's shape: a selector column and a content column."""
        root = _artifact_view_layout(_default_session())
        assert root.className == "artifact-layout"
        assert [child.id for child in root.children] == [
            "artifact-view-sidebar",
            "artifact-view-content",
        ]

    def test_the_selector_pane_is_the_round_select_above_the_tree(self) -> None:
        """In that order: pick a round, then pick a file within it."""
        root = _artifact_view_layout(_default_session())
        sidebar = root.children[0]
        assert [type(child).__name__ for child in sidebar.children] == [
            "Div",
            "Section",
        ]
        assert sidebar.children[0].id == ROUND_SELECT_ID
        assert sidebar.children[1].id == ARTIFACT_TREE_IDS.root

    def test_the_tree_is_the_shared_one_in_its_linked_form(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The same renderer the project view uses, with links switched on.

        Asserted through the line ids rather than by inspecting the call:
        a linked line carries the pattern id the click callback listens for,
        and a plain one carries no id at all.
        """
        _make_round(tmp_path, 1, ["stack.json"])
        session = {**_default_session(), "working_dir": str(tmp_path)}
        root = _artifact_view_layout(session)
        assert line_id("stack.json") in _pattern_ids(root)

    def test_the_tree_carries_its_own_ids_not_the_project_view_s(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Two trees, two id sets.

        Sharing them would let ``on_round_tree`` — which recomputes the project
        view's tree for the *active* round — write over this screen's tree,
        which is drawn for whichever round the developer selected. The
        developer would pick v1 and watch v3's files replace its own.
        """
        _make_round(tmp_path, 1, ["stack.json"])
        session = {**_default_session(), "working_dir": str(tmp_path)}
        ids = _ids(_artifact_view_layout(session))
        assert set(ARTIFACT_TREE_IDS) <= ids
        assert not set(PROJECT_TREE_IDS) & ids

    def test_the_content_pane_shows_its_empty_state(self) -> None:
        """Nothing is selected, so nothing is opened on the developer's behalf."""
        root = _artifact_view_layout(_default_session())
        assert EMPTY_CONTENT in _text(root.children[1])

    def test_an_empty_pane_has_an_empty_header(self) -> None:
        """No file, nothing to say about one. The header keeps its slot so the
        pane does not jump when a file is chosen."""
        root = _artifact_view_layout(_default_session())
        header = _by_id(root, HEADER_ID)
        assert header.children == []
        assert _text(header) == ""

    def test_a_traversal_selection_renders_a_rejection_and_reads_nothing(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A session naming a path outside the round opens no file.

        The screen now resolves and reads, so the guarantee has to be asserted
        where it is used and not only at the resolver: the rendered pane says
        the round does not have that artifact, and no read was attempted.
        """
        _make_round(tmp_path, 1, ["stack.json"])
        reads = _watch_reads(monkeypatch)
        session = {
            **_default_session(),
            "working_dir": str(tmp_path),
            "selected_round": 1,
            "selected_file": "../../etc/passwd",
        }
        assert rejection_message(1) in _text(_artifact_view_layout(session))
        assert reads == []

    def test_it_uses_no_icon_component(self) -> None:
        """dash-iconify stays unused — text only, like the rest of the app."""
        stack = [_artifact_view_layout(_default_session())]
        seen = []
        while stack:
            node = stack.pop()
            seen.append(type(node).__name__)
            children = getattr(node, "children", None)
            if children is None:
                continue
            if not isinstance(children, (list, tuple)):
                children = [children]
            stack.extend(children)
        assert not any("Icon" in name for name in seen)


# ---------------------------------------------------------------------------
# The session keys
# ---------------------------------------------------------------------------


class TestTheSelectionKeys:
    def test_both_keys_are_in_the_default_session(self) -> None:
        session = _default_session()
        assert "selected_round" in session
        assert "selected_file" in session

    def test_the_round_starts_at_the_active_round(self) -> None:
        """Which is unresolved until a project is open — the same value
        ``phase_version`` carries, and read through the same fallback."""
        session = _default_session()
        assert session["selected_round"] == session["phase_version"]

    def test_no_file_is_selected_by_default(self) -> None:
        assert _default_session()["selected_file"] is None

    def test_they_live_in_the_browser_session_store(self) -> None:
        """One store, browser-scoped: no server-side session, no new component.

        The nfr this closes is about provider keys, and it is closed the same
        way for a selection — the shell's store list is unchanged, so nothing
        added this round can be read anywhere but in the developer's browser.
        """
        stores = [
            node
            for node in _flatten(app_module.app.layout)
            if type(node).__name__ == "Store"
        ]
        session_stores = [s for s in stores if s.id == "session"]
        assert len(session_stores) == 1
        assert session_stores[0].storage_type == "session"
        assert "selected_round" in session_stores[0].data
        assert not any("artifact" in str(s.id) for s in stores)

    def test_a_session_without_them_still_renders_every_screen(self) -> None:
        """A tab left open across an upgrade has a store written before these
        keys existed. Nothing may read them positionally or assume a fixed key
        set, so every screen is drawn from a session with both keys removed."""
        legacy = {
            k: v
            for k, v in _default_session().items()
            if k not in ("selected_round", "selected_file")
        }
        for phase in PATH_TO_PHASE.values():
            assert _page({**legacy, "phase": phase}) is not None
        assert on_status_bar(legacy, {}) is not None


def _flatten(component: Any) -> list[Any]:
    out: list[Any] = []
    stack: list[Any] = [component]
    while stack:
        node = stack.pop()
        children = getattr(node, "children", None)
        if children is None:
            continue
        if not isinstance(children, (list, tuple)):
            children = [children]
        out.extend(children)
        stack.extend(children)
    return out


# ---------------------------------------------------------------------------
# Fixtures for the resolver
# ---------------------------------------------------------------------------


def _make_round(root: pathlib.Path, version: int, paths: list[str]) -> pathlib.Path:
    """Create ``.spec4/v{version}/`` and write each of ``paths`` into it.

    The fixture writes the files, and the tests assert against exactly what it
    wrote — never against a hard-coded list of phase filenames. That is the
    point: the resolver's phase expansion reads the directory, so a test that
    restated the expected names would pass even if the expansion had stopped
    reading the directory at all.
    """
    base = root / ".spec4" / f"v{version}"
    base.mkdir(parents=True, exist_ok=True)
    for rel in paths:
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"contents of {rel}\n")
    return base


def _watch_filesystem(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """Record every touch of the requested path, and let none of them through.

    Both seams, not just the stat. ``_resolve`` reads symlinks along the whole
    path, so it is a filesystem operation too, and watching only ``_stat``
    would miss a ``resolve()`` that had crept above the allow-list check —
    which is precisely the mistake the check ordering exists to prevent.
    """
    calls: list[tuple[str, Any]] = []

    def resolve(path: pathlib.Path) -> pathlib.Path:
        calls.append(("resolve", path))
        return path

    def stat(path: pathlib.Path) -> None:
        calls.append(("stat", path))
        return None

    monkeypatch.setattr(artifact_view, "_resolve", resolve)
    monkeypatch.setattr(artifact_view, "_stat", stat)
    return calls


def _watch_reads(monkeypatch: pytest.MonkeyPatch) -> list[pathlib.Path]:
    """Record every attempt to read an artifact's contents, and block them all.

    The third seam, and the one the *screen* adds. ``resolve_artifact`` never
    opens a file, so the resolver's own tests cannot catch a render path that
    reads before it resolves — this one can, and the rendering tests use it to
    assert that a rejected selection reaches no file at all.
    """
    reads: list[pathlib.Path] = []

    def read(path: pathlib.Path) -> None:
        reads.append(path)
        return None

    monkeypatch.setattr(artifact_view, "_read", read)
    return reads


# ---------------------------------------------------------------------------
# Path confinement
# ---------------------------------------------------------------------------


# Every request that must never reach a file, and why it is here.
REFUSED = [
    pytest.param("../../etc/passwd", id="traversal"),
    pytest.param("phases/../../../secrets.env", id="nested-traversal"),
    pytest.param("/etc/passwd", id="absolute"),
    pytest.param("notes.txt", id="plausible-but-unlisted"),
    pytest.param("./stack.json", id="listed-under-another-spelling"),
    pytest.param("", id="empty"),
    pytest.param("design/", id="a-directory-that-is-not-an-artifact"),
    pytest.param("../v2/stack.json", id="a-sibling-round"),
]


class TestPathConfinement:
    """The nfr, asserted directly: nothing outside the round is reachable."""

    @pytest.fixture
    def project(self, tmp_path: pathlib.Path) -> pathlib.Path:
        _make_round(tmp_path, 1, ["stack.json", "phases/phase1.md"])
        _make_round(tmp_path, 2, ["stack.json"])
        return tmp_path

    @pytest.mark.parametrize("requested", REFUSED)
    def test_it_is_refused(self, project: pathlib.Path, requested: str) -> None:
        assert resolve_artifact(project, 1, requested).outcome == RESOLUTION_REJECTED

    @pytest.mark.parametrize("requested", REFUSED)
    def test_a_refusal_says_nothing_else(
        self, project: pathlib.Path, requested: str
    ) -> None:
        """A rejection carries no lane, no producer, no path, no metadata.

        There is nothing truthful to say about a path the app does not
        recognise for this round, and inventing a lane for one would let a
        caller render a header for a file that does not exist.
        """
        result = resolve_artifact(project, 1, requested)
        assert (result.lane, result.agent, result.resolved) == (None, None, None)
        assert (result.size, result.modified) == (None, None)

    @pytest.mark.parametrize("requested", REFUSED)
    def test_the_filesystem_is_never_touched_for_the_requested_path(
        self,
        project: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        requested: str,
    ) -> None:
        """The check ordering, asserted as a property rather than read off the
        source. A refusal happens with the requested path unresolved and
        unstated — so a future edit that moved the stat above the allow-list
        would fail here rather than pass review."""
        calls = _watch_filesystem(monkeypatch)
        assert resolve_artifact(project, 1, requested).outcome == RESOLUTION_REJECTED
        assert calls == []

    def test_a_file_listed_for_another_round_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The only per-round asymmetry there is.

        Every other entry in the reviewed table has the same relative path in
        every round, so ``phases/`` is where "listed elsewhere" can even be
        expressed: ``phase7.md`` exists in v2 and never existed in v1.
        """
        _make_round(tmp_path, 1, ["phases/phase1.md"])
        _make_round(tmp_path, 2, ["phases/phase7.md"])
        assert (
            resolve_artifact(tmp_path, 2, "phases/phase7.md").outcome
            == RESOLUTION_PRESENT
        )
        assert (
            resolve_artifact(tmp_path, 1, "phases/phase7.md").outcome
            == RESOLUTION_REJECTED
        )

    def test_a_listed_entry_that_symlinks_out_of_the_round_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The case the allow-list alone cannot catch.

        ``phases/phase1.md`` is in the allowed set — it is a file in the
        round's phases directory, and its relative path is impeccable. Only
        resolving it and re-checking containment reveals that reading it would
        read something else entirely. This is what ``is_relative_to`` against
        the resolved base is for, and what a ``startswith`` on the unresolved
        path would wave straight through.
        """
        outside = tmp_path / "secrets.env"
        outside.write_text("PROVIDER_KEY=sk-live\n")
        base = _make_round(tmp_path, 1, ["stack.json"])
        (base / "phases").mkdir()
        (base / "phases" / "phase1.md").symlink_to(outside)

        assert "phases/phase1.md" in allowed_artifacts(tmp_path, 1)
        assert (
            resolve_artifact(tmp_path, 1, "phases/phase1.md").outcome
            == RESOLUTION_REJECTED
        )

    def test_a_sibling_round_sharing_a_name_prefix_is_not_reachable(
        self, tmp_path: pathlib.Path
    ) -> None:
        """``.spec4/v1`` is a string prefix of ``.spec4/v10``.

        A containment check written as ``startswith`` would consider v10's
        files to be inside v1. Nothing in v10 is listed for v1 under any
        relative path, so this is refused at the allow-list — and the final
        containment check is a path comparison, not a text one, so it would
        refuse it again.
        """
        _make_round(tmp_path, 1, ["stack.json"])
        _make_round(tmp_path, 10, ["stack.json"])
        assert (
            resolve_artifact(tmp_path, 1, "../v10/stack.json").outcome
            == RESOLUTION_REJECTED
        )


# ---------------------------------------------------------------------------
# The allowed set
# ---------------------------------------------------------------------------


class TestTheAllowedSet:
    def test_every_fixed_entry_is_listed(self, tmp_path: pathlib.Path) -> None:
        _make_round(tmp_path, 1, [])
        allowed = allowed_artifacts(tmp_path, 1)
        assert set(FIXED_ARTIFACTS) <= set(allowed)

    def test_usage_json_is_listed(self, tmp_path: pathlib.Path) -> None:
        _make_round(tmp_path, 1, [])
        assert "usage.json" in allowed_artifacts(tmp_path, 1)

    def test_every_lane_comes_from_the_reviewed_table(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Not from a filename, not from a parent directory.

        ``design/mock.html`` and ``deployment-plan.md`` are exactly the two a
        pattern would misfile, and both are checked here by comparing against
        the table itself rather than against a restated expectation.
        """
        _make_round(tmp_path, 1, [])
        for path, entry in allowed_artifacts(tmp_path, 1).items():
            if path != PHASES_DIR:
                assert entry.lane == ARTIFACT_LANES[path]

    def test_the_producer_is_the_pipeline_key_not_a_display_name(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The data layer carries ``stack_advisor``; Phase 4 renders it."""
        _make_round(tmp_path, 1, [])
        allowed = allowed_artifacts(tmp_path, 1)
        assert allowed["stack.json"].agent == "stack_advisor"
        assert allowed["vision.json"].agent == "brainstormer"
        assert allowed["design/mock.html"].agent == "designer"
        assert all(
            entry.agent is None or entry.agent in AGENT_KEYS
            for entry in allowed.values()
        )

    def test_every_producer_has_a_display_name_to_render_through(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Phase 4's half of the contract, pinned from this side.

        The resolver hands out keys on the promise that
        ``AGENT_DISPLAY_NAMES`` can turn each one into something a developer
        reads. A key with no entry there would surface as a raw
        ``stack_advisor`` in the missing message, so the promise is asserted
        rather than assumed.
        """
        _make_round(tmp_path, 1, [])
        assert all(
            entry.agent in AGENT_DISPLAY_NAMES
            for entry in allowed_artifacts(tmp_path, 1).values()
            if entry.agent is not None
        )

    def test_usage_json_has_no_producer(self, tmp_path: pathlib.Path) -> None:
        """D-LR3: every agent writes it, so no single agent produces it."""
        _make_round(tmp_path, 1, [])
        assert allowed_artifacts(tmp_path, 1)["usage.json"].agent is None

    def test_phases_expands_to_the_files_on_disk(self, tmp_path: pathlib.Path) -> None:
        _make_round(
            tmp_path, 1, ["phases/phase1.md", "phases/phase2.md", "phases/phase10.md"]
        )
        allowed = allowed_artifacts(tmp_path, 1)
        assert {p for p in allowed if p.startswith(PHASES_DIR)} == {
            "phases/phase1.md",
            "phases/phase2.md",
            "phases/phase10.md",
        }
        assert PHASES_DIR not in allowed

    def test_an_expanded_phase_file_keeps_the_directory_lane_and_producer(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_round(tmp_path, 1, ["phases/phase1.md"])
        entry = allowed_artifacts(tmp_path, 1)["phases/phase1.md"]
        assert entry.lane == ARTIFACT_LANES[PHASES_DIR]
        assert entry.agent == "phaser"

    def test_an_empty_phases_directory_keeps_its_own_entry(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The tree still draws the line, so the line still has to resolve."""
        base = _make_round(tmp_path, 1, [])
        (base / "phases").mkdir()
        entry = allowed_artifacts(tmp_path, 1)[PHASES_DIR]
        assert entry.agent == "phaser"

    def test_an_absent_phases_directory_keeps_its_own_entry(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_round(tmp_path, 1, [])
        assert PHASES_DIR in allowed_artifacts(tmp_path, 1)

    @pytest.mark.parametrize(
        "files",
        [
            pytest.param([], id="empty-phases"),
            pytest.param(["phases/phase1.md", "phases/phase2.md"], id="populated"),
        ],
    )
    def test_it_is_exactly_what_the_tree_draws(
        self, tmp_path: pathlib.Path, files: list[str]
    ) -> None:
        """The invariant that makes every tree line clickable.

        The round tree renders a line per path and links each one to this
        resolver. If the two sets ever diverged, the difference would show up
        as a line that opens nothing — no exception, no log, just a click that
        does not work — or as a file that is reachable without appearing
        anywhere on screen. Asserting set equality closes both directions at
        once.
        """
        _make_round(tmp_path, 1, ["stack.json", *files])
        assert set(allowed_artifacts(tmp_path, 1)) == {
            line.path for line in rendered_tree_lines(tmp_path, 1)
        }


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


class TestResolution:
    def test_every_fixed_entry_resolves_for_a_populated_round(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_round(tmp_path, 1, FIXED_ARTIFACTS)
        for path in FIXED_ARTIFACTS:
            assert resolve_artifact(tmp_path, 1, path).outcome == RESOLUTION_PRESENT

    def test_every_phase_file_on_disk_resolves(self, tmp_path: pathlib.Path) -> None:
        _make_round(tmp_path, 1, ["phases/phase1.md", "phases/phase10.md"])
        for path in ("phases/phase1.md", "phases/phase10.md"):
            assert resolve_artifact(tmp_path, 1, path).outcome == RESOLUTION_PRESENT

    def test_a_present_file_carries_its_metadata(self, tmp_path: pathlib.Path) -> None:
        base = _make_round(tmp_path, 1, ["stack.json"])
        on_disk = (base / "stack.json").stat()
        result = resolve_artifact(tmp_path, 1, "stack.json")
        assert result.size == on_disk.st_size
        assert result.modified == pytest.approx(on_disk.st_mtime)
        assert result.lane == ARTIFACT_LANES["stack.json"]
        assert result.agent == "stack_advisor"
        assert result.resolved == (base / "stack.json").resolve()

    def test_the_metadata_comes_from_one_stat(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Size and mtime off a single call, not an exists() plus two more."""
        _make_round(tmp_path, 1, ["stack.json"])
        real = artifact_view._stat
        calls: list[pathlib.Path] = []

        def counted(path: pathlib.Path) -> Any:
            calls.append(path)
            return real(path)

        monkeypatch.setattr(artifact_view, "_stat", counted)
        assert resolve_artifact(tmp_path, 1, "stack.json").outcome == RESOLUTION_PRESENT
        assert len(calls) == 1

    def test_no_content_is_read(self, tmp_path: pathlib.Path) -> None:
        """Reading belongs to the render path, so there is nowhere to put it."""
        _make_round(tmp_path, 1, ["stack.json"])
        result = resolve_artifact(tmp_path, 1, "stack.json")
        assert not hasattr(result, "content")
        assert not hasattr(result, "text")

    def test_a_listed_but_absent_file_names_its_producer(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_round(tmp_path, 1, ["stack.json"])
        result = resolve_artifact(tmp_path, 1, "vision.json")
        assert result.outcome == RESOLUTION_MISSING
        assert result.agent == "brainstormer"
        assert result.lane == ARTIFACT_LANES["vision.json"]
        assert (result.resolved, result.size, result.modified) == (None, None, None)

    def test_an_absent_usage_json_has_no_producer_to_name(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_round(tmp_path, 1, [])
        result = resolve_artifact(tmp_path, 1, "usage.json")
        assert result.outcome == RESOLUTION_MISSING
        assert result.agent is None

    @pytest.mark.parametrize(
        "make_directory",
        [pytest.param(True, id="empty-dir"), pytest.param(False, id="no-dir")],
    )
    def test_an_unproduced_phases_is_missing_and_owned_by_phaser(
        self, tmp_path: pathlib.Path, make_directory: bool
    ) -> None:
        """The case the round tree draws and the developer can click.

        An empty folder is not a produced artifact — the same judgement
        ``_round_tree._exists`` makes — so this is missing, not present, and it
        names Phaser so the view can say who would produce it.
        """
        base = _make_round(tmp_path, 1, [])
        if make_directory:
            (base / "phases").mkdir()
        result = resolve_artifact(tmp_path, 1, PHASES_DIR)
        assert result.outcome == RESOLUTION_MISSING
        assert result.agent == "phaser"
        assert result.size is None

    def test_a_populated_phases_is_no_longer_requestable_as_a_directory(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Once it expands, the directory is not one of the round's files."""
        _make_round(tmp_path, 1, ["phases/phase1.md"])
        assert resolve_artifact(tmp_path, 1, PHASES_DIR).outcome == RESOLUTION_REJECTED

    def test_a_round_with_no_directory_on_disk_is_all_missing(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The selector can name a round the persist funnel has not created."""
        _make_round(tmp_path, 0, ["stack.json"])
        result = resolve_artifact(tmp_path, 7, "stack.json")
        assert result.outcome == RESOLUTION_MISSING
        assert result.agent == "stack_advisor"

    @pytest.mark.parametrize(
        ("working_dir", "round_number"),
        [
            pytest.param(None, 1, id="no-working-dir"),
            pytest.param("", None, id="nothing-at-all"),
        ],
    )
    def test_an_unopened_project_is_missing_rather_than_refused(
        self, working_dir: str | None, round_number: int | None
    ) -> None:
        """The same answer ``round_tree_lines`` gives for the same state."""
        result = resolve_artifact(working_dir, round_number, "stack.json")
        assert result.outcome == RESOLUTION_MISSING
        assert result.agent == "stack_advisor"


# ---------------------------------------------------------------------------
# Rounds on disk
# ---------------------------------------------------------------------------


class TestRoundsOnDisk:
    def test_it_lists_every_round(self, tmp_path: pathlib.Path) -> None:
        for version in (0, 1, 2):
            _make_round(tmp_path, version, [])
        assert project_manager.rounds_on_disk(tmp_path).rounds == (0, 1, 2)

    def test_it_sorts_by_round_number_not_by_name(self, tmp_path: pathlib.Path) -> None:
        """``v10`` sorts before ``v9`` as text, and after it as a round."""
        for version in (9, 10, 2):
            _make_round(tmp_path, version, [])
        assert project_manager.rounds_on_disk(tmp_path).rounds == (2, 9, 10)

    def test_a_new_round_appears_on_the_very_next_call(
        self, tmp_path: pathlib.Path
    ) -> None:
        """No restart, no cache to invalidate — the mitigation the Artifact
        View's stale-round-list failure mode asks for."""
        _make_round(tmp_path, 0, [])
        assert project_manager.rounds_on_disk(tmp_path).rounds == (0,)
        _make_round(tmp_path, 1, [])
        assert project_manager.rounds_on_disk(tmp_path).rounds == (0, 1)

    def test_the_active_round_is_the_newest_by_default(
        self, tmp_path: pathlib.Path
    ) -> None:
        for version in (0, 1):
            _make_round(tmp_path, version, [])
        assert project_manager.rounds_on_disk(tmp_path).active == 1

    def test_a_pinned_session_decides_the_active_round(
        self, tmp_path: pathlib.Path
    ) -> None:
        """So the selector and the tree beside it name the same round."""
        for version in (0, 1):
            _make_round(tmp_path, version, [])
        result = project_manager.rounds_on_disk(tmp_path, {"phase_version": 0})
        assert result.active == 0
        assert result.rounds == (0, 1)

    def test_a_directory_that_is_not_a_round_is_ignored(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_round(tmp_path, 1, [])
        (tmp_path / ".spec4" / "notes").mkdir()
        (tmp_path / ".spec4" / "vNext").mkdir()
        (tmp_path / ".spec4" / "v2.bak").mkdir()
        assert project_manager.rounds_on_disk(tmp_path).rounds == (1,)

    @pytest.mark.parametrize(
        "working_dir",
        [pytest.param(None, id="none"), pytest.param("", id="empty")],
    )
    def test_no_project_is_empty_rather_than_an_error(
        self, working_dir: str | None
    ) -> None:
        assert project_manager.rounds_on_disk(working_dir) == ((), None)

    def test_a_project_with_no_rounds_yet_has_no_active_round(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / ".spec4").mkdir()
        assert project_manager.rounds_on_disk(tmp_path) == ((), None)


# ---------------------------------------------------------------------------
# The round selector
# ---------------------------------------------------------------------------


class TestTheRoundSelector:
    """Every round on disk, recomputed on every render."""

    def _strip(self, working_dir: pathlib.Path, **session: Any) -> Any:
        layout = _artifact_view_layout(
            {**_default_session(), "working_dir": str(working_dir), **session}
        )
        return _by_id(layout, ROUND_SELECT_ID)

    def _labels(self, working_dir: pathlib.Path, **session: Any) -> list[str]:
        return [b.children for b in self._strip(working_dir, **session).children]

    def _current(self, working_dir: pathlib.Path, **session: Any) -> str | None:
        marked = [
            b.children
            for b in self._strip(working_dir, **session).children
            if "is-active" in (b.className or "")
        ]
        assert len(marked) <= 1, f"more than one round marked current: {marked}"
        return marked[0] if marked else None

    def test_it_lists_every_round_on_disk(self, tmp_path: pathlib.Path) -> None:
        for version in (0, 1, 2):
            _make_round(tmp_path, version, [])
        assert self._labels(tmp_path) == ["v0", "v1", "v2"]

    def test_each_round_is_a_control_carrying_its_own_number(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A click has to say which round, and ``n_clicks`` has to survive the
        page rebuild the click causes — which is why these are buttons."""
        for version in (0, 1):
            _make_round(tmp_path, version, [])
        buttons = self._strip(tmp_path).children
        assert [b.id for b in buttons] == [round_id(0), round_id(1)]
        assert all(b.n_clicks == 0 for b in buttons)
        assert all(b.id["type"] == ROUND_TYPE for b in buttons)

    def test_it_defaults_to_the_active_round(self, tmp_path: pathlib.Path) -> None:
        for version in (0, 1, 2):
            _make_round(tmp_path, version, [])
        assert self._current(tmp_path) == round_value(2)

    def test_a_pinned_session_decides_the_default(self, tmp_path: pathlib.Path) -> None:
        """So the selector and the tree beside it name the same round."""
        for version in (0, 1):
            _make_round(tmp_path, version, [])
        assert self._current(tmp_path, phase_version=0) == round_value(0)

    def test_the_session_selection_wins_over_the_active_round(
        self, tmp_path: pathlib.Path
    ) -> None:
        for version in (0, 1):
            _make_round(tmp_path, version, [])
        assert self._current(tmp_path, selected_round=0) == round_value(0)

    def test_a_round_created_since_the_last_render_appears(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The stale-round-list mitigation, asserted at the screen.

        No restart and no cache to invalidate: the second render simply sees
        the folder the first one did not.
        """
        _make_round(tmp_path, 0, [])
        assert self._labels(tmp_path) == ["v0"]
        _make_round(tmp_path, 1, [])
        assert self._labels(tmp_path) == ["v0", "v1"]

    def test_a_selection_naming_a_round_that_is_gone_falls_back(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A session store outlives the project it was written against."""
        _make_round(tmp_path, 1, [])
        assert self._current(tmp_path, selected_round=9) == round_value(1)

    def test_a_project_with_no_rounds_offers_nothing(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / ".spec4").mkdir()
        assert self._strip(tmp_path).children == []
        assert self._current(tmp_path) is None

    def test_it_names_no_colour_of_its_own(self, tmp_path: pathlib.Path) -> None:
        """D-LR2: the accent arrives from the theme primary through the
        ``is-active`` class, never from a colour named here."""
        for version in (0, 1):
            _make_round(tmp_path, version, [])
        for button in self._strip(tmp_path).children:
            assert getattr(button, "color", None) is None
            assert getattr(button, "style", None) is None

    def test_the_tree_beside_it_is_drawn_for_the_selected_round(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Switching rounds updates the tree, not only the pane."""
        _make_round(tmp_path, 0, ["phases/phase1.md"])
        _make_round(tmp_path, 1, ["phases/phase7.md"])
        layout = _artifact_view_layout(
            {
                **_default_session(),
                "working_dir": str(tmp_path),
                "selected_round": 0,
            }
        )
        assert line_id("phases/phase1.md") in _pattern_ids(layout)
        assert line_id("phases/phase7.md") not in _pattern_ids(layout)
        assert ".spec4/v0/" in _text(_by_id(layout, ARTIFACT_TREE_IDS.head))


# ---------------------------------------------------------------------------
# The header
# ---------------------------------------------------------------------------


class TestTheHeader:
    """One line: path, size, last modified, lane — in that fixed order."""

    @pytest.fixture
    def project(self, tmp_path: pathlib.Path) -> pathlib.Path:
        base = _make_round(tmp_path, 1, ["stack.json"])
        (base / "stack.json").write_text("x" * 4300)
        return tmp_path

    def _header(
        self, working_dir: pathlib.Path, path: str, round_number: int = 1
    ) -> Any:
        header, _ = artifact_pane(working_dir, round_number, path)
        return header

    def test_the_four_fields_are_in_the_specified_order(
        self, project: pathlib.Path
    ) -> None:
        """Read off the rendered strings, not off the source.

        Each field is located by its own marker — the round folder for the
        path, the unit for the size, the word ``modified`` for the timestamp,
        the legend phrase for the lane — and the assertion is that their
        positions increase. A reordered header fails here even though every
        field is still present.
        """
        text = _text(self._header(project, "stack.json"))
        positions = [
            text.index(".spec4/v1/stack.json"),
            text.index("KB"),
            text.index("modified"),
            text.index(LANE_LABELS[ARTIFACT_LANES["stack.json"]]),
        ]
        assert positions == sorted(positions)

    def test_the_path_is_the_full_path_within_the_round(
        self, project: pathlib.Path
    ) -> None:
        """The same folder the tree above the pane heads itself with."""
        assert ".spec4/v1/stack.json" in _text(self._header(project, "stack.json"))

    def test_the_size_is_the_file_s_own(self, project: pathlib.Path) -> None:
        assert "4.2 KB" in _text(self._header(project, "stack.json"))

    def test_the_modified_time_is_the_file_s_own(self, project: pathlib.Path) -> None:
        stamp = datetime.fromtimestamp(
            (project / ".spec4" / "v1" / "stack.json").stat().st_mtime
        ).strftime("%Y-%m-%d %H:%M")
        assert f"modified {stamp}" in _text(self._header(project, "stack.json"))

    def test_the_lane_comes_from_the_reviewed_table(
        self, project: pathlib.Path
    ) -> None:
        """Not from the mock's sample data, which misfiles deployment-plan.md."""
        _make_round(project, 1, ["deployment-plan.md"])
        text = _text(self._header(project, "deployment-plan.md"))
        assert LANE_LABELS[ARTIFACT_LANES["deployment-plan.md"]] in text
        assert LANE_LABELS["record"] in text

    def test_a_missing_artifact_keeps_the_path_and_the_lane(
        self, project: pathlib.Path
    ) -> None:
        """There is no size and no timestamp to state, so those two collapse
        into the word `missing` and every field left is still true."""
        text = _text(self._header(project, "vision.json"))
        assert ".spec4/v1/vision.json" in text
        assert RESOLUTION_MISSING in text
        assert LANE_LABELS[ARTIFACT_LANES["vision.json"]] in text
        assert "modified" not in text

    def test_a_rejected_request_renders_no_header(self, project: pathlib.Path) -> None:
        """Echoing back an unrecognised path would dress it as a fact about
        this round. The body says what happened instead."""
        assert self._header(project, "../../etc/passwd") == []

    def test_it_is_one_line_in_the_mono_class(self, project: pathlib.Path) -> None:
        layout = _artifact_view_layout(
            {
                **_default_session(),
                "working_dir": str(project),
                "selected_round": 1,
                "selected_file": "stack.json",
            }
        )
        header = _by_id(layout, HEADER_ID)
        assert "mono" in header.className
        assert "\n" not in _text(header)

    def test_it_names_no_colour_of_its_own(self, project: pathlib.Path) -> None:
        """D-LR2: every colour on this line comes from a class in v3.css."""
        for node in _nodes(self._header(project, "stack.json")):
            assert getattr(node, "style", None) is None
            assert getattr(node, "color", None) is None


# ---------------------------------------------------------------------------
# The content pane
# ---------------------------------------------------------------------------


_COMPACT_JSON = '{"round":4,"features":["artifact_view","artifact_links"]}'

_MARKDOWN = "# Phase 1\n\nRead this **verbatim**.\n\n1. First\n2. Second\n"


class TestTheContentPane:
    def _body(self, working_dir: pathlib.Path, path: str, round_number: int = 1) -> Any:
        _, body = artifact_pane(working_dir, round_number, path)
        return body

    # -- JSON ---------------------------------------------------------------

    def test_json_is_pretty_printed(self, tmp_path: pathlib.Path) -> None:
        base = _make_round(tmp_path, 1, ["stack.json"])
        (base / "stack.json").write_text(_COMPACT_JSON)
        _, content = _gutter_and_content(self._body(tmp_path, "stack.json"))
        assert content == json.dumps(json.loads(_COMPACT_JSON), indent=2)
        assert content.splitlines()[1].startswith("  ")

    def test_pretty_printed_json_is_line_numbered(self, tmp_path: pathlib.Path) -> None:
        """Numbered against the *rendered* text, not the file on disk.

        The compact file is one line; the pane shows six. Numbering the file's
        own lines would put a single ``1`` beside six lines of output.
        """
        base = _make_round(tmp_path, 1, ["stack.json"])
        (base / "stack.json").write_text(_COMPACT_JSON)
        gutter, content = _gutter_and_content(self._body(tmp_path, "stack.json"))
        assert gutter.splitlines() == [
            str(n) for n in range(1, len(content.splitlines()) + 1)
        ]

    def test_json_keeps_non_ascii_readable(self, tmp_path: pathlib.Path) -> None:
        """`ensure_ascii=False`: a feature name stays a name, not \\uXXXX."""
        base = _make_round(tmp_path, 1, ["vision.json"])
        (base / "vision.json").write_text('{"name":"продукт"}', encoding="utf-8")
        _, content = _gutter_and_content(self._body(tmp_path, "vision.json"))
        assert "продукт" in content
        assert "\\u" not in content

    def test_json_that_does_not_parse_falls_back_to_raw_text(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A half-written artifact is exactly when the developer wants to look."""
        base = _make_round(tmp_path, 1, ["stack.json"])
        truncated = '{\n  "stack": [\n    "dash",\n'
        (base / "stack.json").write_text(truncated)
        gutter, content = _gutter_and_content(self._body(tmp_path, "stack.json"))
        assert content == truncated.rstrip("\n")
        assert len(gutter.splitlines()) == len(content.splitlines())

    # -- Plain text ---------------------------------------------------------

    def test_a_plain_text_file_is_not_reformatted(self, tmp_path: pathlib.Path) -> None:
        """Markdown renders as-is: no renderer, no highlighter, no rewrap."""
        base = _make_round(tmp_path, 1, ["phases/phase1.md"])
        (base / "phases" / "phase1.md").write_text(_MARKDOWN)
        _, content = _gutter_and_content(self._body(tmp_path, "phases/phase1.md"))
        assert content == _MARKDOWN.rstrip("\n")

    def test_a_plain_text_file_is_line_numbered(self, tmp_path: pathlib.Path) -> None:
        base = _make_round(tmp_path, 1, ["phases/phase1.md"])
        (base / "phases" / "phase1.md").write_text(_MARKDOWN)
        gutter, content = _gutter_and_content(self._body(tmp_path, "phases/phase1.md"))
        assert gutter.splitlines() == [
            str(n) for n in range(1, len(content.splitlines()) + 1)
        ]

    def test_no_markdown_or_highlighting_component_is_used(
        self, tmp_path: pathlib.Path
    ) -> None:
        """This round adds no dependency of any kind."""
        base = _make_round(tmp_path, 1, ["phases/phase1.md"])
        (base / "phases" / "phase1.md").write_text(_MARKDOWN)
        body = self._body(tmp_path, "phases/phase1.md")
        names = {type(n).__name__ for n in _nodes(body)}
        assert not {"Markdown", "CodeHighlight", "Prism", "Code"} & names

    # -- The gutter ---------------------------------------------------------

    @pytest.mark.parametrize(
        ("name", "text"),
        [
            pytest.param("stack.json", _COMPACT_JSON, id="json"),
            pytest.param("deployment-plan.md", _MARKDOWN, id="markdown"),
        ],
    )
    def test_the_gutter_has_exactly_as_many_lines_as_the_content(
        self, tmp_path: pathlib.Path, name: str, text: str
    ) -> None:
        """The alignment invariant, for both kinds of file.

        A gutter one line short or one line long slides every number below the
        discrepancy onto the wrong line, and nothing about the page looks
        broken while it does.
        """
        base = _make_round(tmp_path, 1, [name])
        (base / name).write_text(text)
        gutter, content = _gutter_and_content(self._body(tmp_path, name))
        assert len(gutter.splitlines()) == len(content.splitlines())

    def test_one_trailing_newline_is_not_a_line(self) -> None:
        """``a\\nb\\n`` is two lines — what every editor and diff agrees on."""
        gutter, content = line_numbered("a\nb\n")
        assert content == "a\nb"
        assert gutter.splitlines() == ["1", "2"]

    def test_further_trailing_blank_lines_are_content(self) -> None:
        gutter, content = line_numbered("a\n\n\n")
        assert content == "a\n\n"
        assert gutter.splitlines() == ["1", "2", "3"]

    def test_an_empty_file_is_one_empty_line(self) -> None:
        assert line_numbered("") == ("1", "")

    def test_the_numbers_are_right_aligned(self) -> None:
        """So the ones column stays a column when the file passes line 9."""
        gutter, _ = line_numbered("\n".join("x" for _ in range(10)))
        assert gutter.splitlines()[:2] == [" 1", " 2"]
        assert gutter.splitlines()[-1] == "10"

    # -- Scale --------------------------------------------------------------

    def test_the_pane_is_two_pre_elements_whatever_the_file_s_size(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The failure mode this closes: a component per line.

        It is the obvious implementation and it is the one that makes a large
        artifact unresponsive — 4,000 lines becomes 8,000 React nodes for Dash
        to serialise, ship and diff on every render. Asserted as a count of
        components rather than as a rule about the source, so any route back to
        a per-line tree fails here.
        """
        base = _make_round(tmp_path, 1, ["deployment-plan.md"])
        small = 10
        large = 4000
        counts = []
        for lines in (small, large):
            (base / "deployment-plan.md").write_text(
                "\n".join(f"line {n}" for n in range(lines))
            )
            body = self._body(tmp_path, "deployment-plan.md")
            assert len(_pres(body)) == 2
            counts.append(len(_nodes(body)))
        assert counts[0] == counts[1]

    def test_the_gutter_comes_before_the_content(self, tmp_path: pathlib.Path) -> None:
        base = _make_round(tmp_path, 1, ["deployment-plan.md"])
        (base / "deployment-plan.md").write_text("one\ntwo\nthree\n")
        body = self._body(tmp_path, "deployment-plan.md")
        gutter, content = _gutter_and_content(body)
        assert gutter == "1\n2\n3"
        assert content == "one\ntwo\nthree"

    def test_the_two_pres_take_their_metrics_from_one_css_rule(self) -> None:
        """Gutter/content drift is a stylesheet problem, so it is pinned there.

        Two rules could be edited apart by half a pixel of line height and
        slide the numbers off their lines twenty rows down. One rule cannot.
        """
        css = (
            pathlib.Path(artifact_view.__file__).resolve().parent.parent
            / "assets"
            / "v3.css"
        ).read_text(encoding="utf-8")
        # Comments first: a rule's selector otherwise arrives with the whole
        # paragraph explaining it glued to the front.
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        rules = re.findall(r"([^{}]*)\{([^}]*)\}", css)
        metric = re.compile(r"(^|[\s;])(font-size|line-height|font-family)\s*:", re.M)
        setters = [
            selector.strip()
            for selector, body in rules
            if metric.search(body)
            and (
                "file-gutter" in selector
                or "file-content" in selector
                or "file-lines pre" in selector
            )
        ]
        assert setters == [".file-lines pre"]

    def test_the_scroll_container_is_present(self, tmp_path: pathlib.Path) -> None:
        base = _make_round(tmp_path, 1, ["stack.json"])
        (base / "stack.json").write_text(_COMPACT_JSON)
        assert SCROLL_ID in _ids(self._body(tmp_path, "stack.json"))

    def test_the_body_carries_the_declared_id(self, tmp_path: pathlib.Path) -> None:
        _make_round(tmp_path, 1, ["stack.json"])
        layout = _artifact_view_layout(
            {
                **_default_session(),
                "working_dir": str(tmp_path),
                "selected_round": 1,
                "selected_file": "stack.json",
            }
        )
        assert SCROLL_ID in _ids(_by_id(layout, BODY_ID))


# ---------------------------------------------------------------------------
# Missing, and refused
# ---------------------------------------------------------------------------


class TestTheMissingMessage:
    def test_it_names_the_producing_agent(self, tmp_path: pathlib.Path) -> None:
        """The schema note's exact sentence: 'missing — produced by {Agent}'."""
        _make_round(tmp_path, 1, ["stack.json"])
        _, body = artifact_pane(tmp_path, 1, "deployment-plan.md")
        assert _sentence(body) == "deployment-plan.md — missing — produced by Deployer"

    def test_the_agent_is_the_display_name_not_the_pipeline_key(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_round(tmp_path, 1, [])
        text = _text(artifact_pane(tmp_path, 1, "stack.json")[1])
        assert AGENT_DISPLAY_NAMES["stack_advisor"] in text
        assert "stack_advisor" not in text

    @pytest.mark.parametrize("path", [p for p in FIXED_ARTIFACTS if p != "usage.json"])
    def test_every_missing_artifact_names_a_producer(
        self, tmp_path: pathlib.Path, path: str
    ) -> None:
        _make_round(tmp_path, 1, [])
        assert "produced by" in _text(artifact_pane(tmp_path, 1, path)[1])

    def test_usage_json_names_no_producer(self, tmp_path: pathlib.Path) -> None:
        """D-LR3: every agent writes it, so naming one would be a plausible lie."""
        _make_round(tmp_path, 1, [])
        text = _sentence(artifact_pane(tmp_path, 1, "usage.json")[1])
        assert text == "usage.json — missing"
        assert "produced by" not in text

    def test_a_missing_artifact_still_has_its_line_in_the_tree(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Shown in the tree and explained when selected — both halves."""
        _make_round(tmp_path, 1, ["stack.json"])
        layout = _artifact_view_layout(
            {
                **_default_session(),
                "working_dir": str(tmp_path),
                "selected_round": 1,
                "selected_file": "deployment-plan.md",
            }
        )
        assert line_id("deployment-plan.md") in _pattern_ids(layout)
        assert missing_message("deployment-plan.md", "deployer") in _sentence(layout)

    def test_it_reads_no_file(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_round(tmp_path, 1, [])
        reads = _watch_reads(monkeypatch)
        artifact_pane(tmp_path, 1, "stack.json")
        assert reads == []


class TestARefusedRequest:
    @pytest.mark.parametrize("requested", REFUSED)
    def test_it_renders_the_plain_rejection(
        self, tmp_path: pathlib.Path, requested: str
    ) -> None:
        _make_round(tmp_path, 1, ["stack.json"])
        header, body = artifact_pane(tmp_path, 1, requested)
        if not requested:
            # An empty selection is "nothing chosen", not a refusal.
            assert EMPTY_CONTENT in _text(body)
            return
        assert header == []
        assert _sentence(body) == rejection_message(1)

    @pytest.mark.parametrize("requested", [p for p in REFUSED if p.values[0]])
    def test_it_never_reads_a_file(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        requested: str,
    ) -> None:
        _make_round(tmp_path, 1, ["stack.json"])
        reads = _watch_reads(monkeypatch)
        calls = _watch_filesystem(monkeypatch)
        artifact_pane(tmp_path, 1, requested)
        assert (reads, calls) == ([], [])

    def test_the_message_names_the_round_rather_than_the_path(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A statement about this round, and an invitation to pick again — not
        an error, and nothing echoed back to whoever asked."""
        _make_round(tmp_path, 2, ["stack.json"])
        text = _sentence(artifact_pane(tmp_path, 2, "../../etc/passwd")[1])
        assert text == "No such artifact in v2."
        assert "passwd" not in text

    def test_a_file_that_vanishes_between_the_stat_and_the_read_is_survivable(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rare, and not worth taking the screen down for: the tree, the
        selector and the header are all still true."""
        base = _make_round(tmp_path, 1, ["stack.json"])
        real = artifact_view._read

        def gone(path: pathlib.Path) -> None:
            (base / "stack.json").unlink()
            return real(path)

        monkeypatch.setattr(artifact_view, "_read", gone)
        header, body = artifact_pane(tmp_path, 1, "stack.json")
        assert artifact_view.UNREADABLE in _text(body)
        assert ".spec4/v1/stack.json" in _text(header)


# ---------------------------------------------------------------------------
# Which round the screen is showing
# ---------------------------------------------------------------------------


class TestTheRoundInEffect:
    """`selected_round` is the one answer the tree, the selector and the pane
    all take, so a screen cannot draw one round's tree beside another's file."""

    def test_it_is_the_active_round_by_default(self, tmp_path: pathlib.Path) -> None:
        for version in (0, 1):
            _make_round(tmp_path, version, [])
        assert selected_round(tmp_path, _default_session()) == 1

    def test_the_session_choice_wins_when_it_is_on_disk(
        self, tmp_path: pathlib.Path
    ) -> None:
        for version in (0, 1):
            _make_round(tmp_path, version, [])
        session = {**_default_session(), "selected_round": 0}
        assert selected_round(tmp_path, session) == 0

    def test_a_choice_that_is_no_longer_on_disk_is_dropped(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A session store outlives the project it was written against."""
        _make_round(tmp_path, 1, [])
        session = {**_default_session(), "selected_round": 9}
        assert selected_round(tmp_path, session) == 1

    def test_no_project_has_no_round(self) -> None:
        assert selected_round(None, _default_session()) is None


# ---------------------------------------------------------------------------
# The text, before it is numbered
# ---------------------------------------------------------------------------


class TestRenderedText:
    def test_json_is_re_serialised_at_two_space_indent(self) -> None:
        assert rendered_text("stack.json", '{"a":1}') == '{\n  "a": 1\n}'

    def test_a_non_json_extension_is_never_parsed(self) -> None:
        """A ``.md`` file that happens to hold JSON is still a text file."""
        assert rendered_text("notes.md", '{"a":1}') == '{"a":1}'

    def test_markdown_is_returned_byte_for_byte(self) -> None:
        assert rendered_text("phases/phase1.md", _MARKDOWN) == _MARKDOWN

    def test_broken_json_is_returned_as_written(self) -> None:
        assert rendered_text("stack.json", "{oops") == "{oops"

    def test_an_empty_json_file_is_returned_as_written(self) -> None:
        """A file an agent created and has not written to yet."""
        assert rendered_text("stack.json", "") == ""


# ---------------------------------------------------------------------------
# Switching rounds
# ---------------------------------------------------------------------------


class TestSwitchingRounds:
    """The selector, the tree and the available files move together."""

    @pytest.fixture
    def project(self, tmp_path: pathlib.Path) -> pathlib.Path:
        """Two rounds. v1 has a phase file; v2 has none, and never did."""
        _make_round(tmp_path, 1, ["stack.json", "phases/phase1.md"])
        _make_round(tmp_path, 2, ["stack.json"])
        return tmp_path

    def _session(self, project: pathlib.Path, **extra: Any) -> dict[str, Any]:
        return {
            **_default_session(),
            "working_dir": str(project),
            "phase": ARTIFACTS_PHASE,
            **extra,
        }

    def _choose(self, round_number: int, session: dict[str, Any]) -> Any:
        """Click the strip's button for `round_number`."""
        with patch.object(
            artifact_view_callbacks, "ctx", _TriggeredBy(round_id(round_number))
        ):
            return on_artifact_round([1], session)

    def test_it_records_the_chosen_round(self, project: pathlib.Path) -> None:
        session = self._choose(1, self._session(project, selected_round=2))
        assert session["selected_round"] == 1

    def test_a_file_the_new_round_lacks_is_cleared(self, project: pathlib.Path) -> None:
        """The mitigation the risk assessment asks for by name.

        Keeping it would leave the pane rendering a rejection for a line the
        tree beside it is not even drawing — a dead end the developer did not
        ask for.
        """
        session = self._choose(
            2,
            self._session(project, selected_round=1, selected_file="phases/phase1.md"),
        )
        assert session["selected_round"] == 2
        assert session["selected_file"] is None

    def test_a_file_both_rounds_have_survives_the_switch(
        self, project: pathlib.Path
    ) -> None:
        """Comparing the same artifact across two rounds is the main reason to
        switch at all, so the selection is kept whenever it still resolves."""
        session = self._choose(
            2, self._session(project, selected_round=1, selected_file="stack.json")
        )
        assert session["selected_file"] == "stack.json"

    def test_the_cleared_selection_renders_the_empty_state_not_a_rejection(
        self, project: pathlib.Path
    ) -> None:
        """End to end: the clearing rule is what the developer actually sees."""
        session = self._choose(
            2,
            self._session(project, selected_round=1, selected_file="phases/phase1.md"),
        )
        text = _text(_artifact_view_layout(session))
        assert EMPTY_CONTENT in text
        assert rejection_message(2) not in text

    def test_switching_rounds_redraws_the_tree(self, project: pathlib.Path) -> None:
        session = self._choose(2, self._session(project, selected_round=1))
        layout = _artifact_view_layout(session)
        assert ".spec4/v2/" in _text(_by_id(layout, ARTIFACT_TREE_IDS.head))
        assert line_id("phases/phase1.md") not in _pattern_ids(layout)

    def test_choosing_the_round_already_shown_writes_nothing(
        self, project: pathlib.Path
    ) -> None:
        assert self._choose(2, self._session(project, selected_round=2)) is no_update

    def test_a_render_that_mounts_the_strip_writes_nothing(
        self, project: pathlib.Path
    ) -> None:
        """Dash fires a pattern callback when the set of matching components
        changes, and every render mounts a fresh strip. Without the
        ``n_clicks`` guard, simply redrawing the screen would write a round
        into the session — the same fire the round tree's lines guard against,
        and the reason this control is a button rather than a dropdown."""
        with patch.object(artifact_view_callbacks, "ctx", _TriggeredBy(round_id(1))):
            assert on_artifact_round([0, 0], self._session(project)) is no_update

    def test_a_fire_with_nothing_triggered_writes_nothing(
        self, project: pathlib.Path
    ) -> None:
        with patch.object(artifact_view_callbacks, "ctx", _TriggeredBy(None)):
            assert on_artifact_round([1], self._session(project)) is no_update

    def test_it_touches_no_other_session_key(self, project: pathlib.Path) -> None:
        """Single-purpose: two keys change, and nothing else does."""
        before = self._session(project, selected_round=1, selected_file="stack.json")
        after = self._choose(2, before)
        assert {k for k in after if after[k] != before.get(k)} == {"selected_round"}


class TestThePaneCallback:
    @pytest.fixture
    def project(self, tmp_path: pathlib.Path) -> pathlib.Path:
        base = _make_round(tmp_path, 1, ["stack.json"])
        (base / "stack.json").write_text('{"round":1}')
        base = _make_round(tmp_path, 2, ["stack.json"])
        (base / "stack.json").write_text('{"round":2}')
        return tmp_path

    def test_it_renders_the_selected_file(self, project: pathlib.Path) -> None:
        header, body = on_artifact_pane(
            "artifact-view-content",
            {
                **_default_session(),
                "working_dir": str(project),
                "selected_round": 1,
                "selected_file": "stack.json",
            },
        )
        assert ".spec4/v1/stack.json" in _text(header)
        assert '"round": 1' in _gutter_and_content(body)[1]

    def test_the_session_round_decides_which_round_is_read(
        self, project: pathlib.Path
    ) -> None:
        """The same path in two rounds is two different files."""
        _, body = on_artifact_pane(
            "artifact-view-content",
            {
                **_default_session(),
                "working_dir": str(project),
                "selected_round": 2,
                "selected_file": "stack.json",
            },
        )
        assert '"round": 2' in _gutter_and_content(body)[1]

    def test_it_falls_back_to_the_active_round(self, project: pathlib.Path) -> None:
        header, _ = on_artifact_pane(
            "artifact-view-content",
            {
                **_default_session(),
                "working_dir": str(project),
                "selected_file": "stack.json",
            },
        )
        assert ".spec4/v2/stack.json" in _text(header)

    def test_a_missing_session_renders_the_empty_state(self) -> None:
        header, body = on_artifact_pane("artifact-view-content", None)
        assert header == []
        assert EMPTY_CONTENT in _text(body)

    def test_it_matches_what_the_first_paint_drew(self, project: pathlib.Path) -> None:
        """One renderer behind both, so the screen cannot change on arrival."""
        session = {
            **_default_session(),
            "working_dir": str(project),
            "selected_round": 1,
            "selected_file": "stack.json",
        }
        header, body = on_artifact_pane("artifact-view-content", session)
        layout = _artifact_view_layout(session)
        assert _text(header) == _text(_by_id(layout, HEADER_ID))
        assert _text(body) == _text(_by_id(layout, BODY_ID))


class TestATreeLineOnThisScreen:
    """A click means the round the tree the developer is looking at is showing."""

    @pytest.fixture
    def project(self, tmp_path: pathlib.Path) -> pathlib.Path:
        _make_round(tmp_path, 1, ["stack.json"])
        _make_round(tmp_path, 2, ["stack.json"])
        return tmp_path

    def _click(self, path: str, session: dict[str, Any]) -> Any:
        with patch.object(artifact_view_callbacks, "ctx", _TriggeredBy(line_id(path))):
            return on_round_tree_line([1], session)

    def test_it_opens_the_file_in_the_round_being_viewed(
        self, project: pathlib.Path
    ) -> None:
        """v2 is the active round; the developer is looking at v1.

        Resolving the active round here would open v2's copy of the file the
        developer clicked in v1 — the same file path, a different round, and
        nothing on screen to say so.
        """
        session, path = self._click(
            "stack.json",
            {
                **_default_session(),
                "working_dir": str(project),
                "phase": ARTIFACTS_PHASE,
                "selected_round": 1,
            },
        )
        assert session["selected_round"] == 1
        assert session["selected_file"] == "stack.json"
        assert path == ARTIFACTS_PATH

    def test_the_project_view_still_opens_the_active_round(
        self, project: pathlib.Path
    ) -> None:
        """The other screen's contract, unchanged: its tree draws the active
        round, so its lines mean the active round."""
        session, _ = self._click(
            "stack.json",
            {
                **_default_session(),
                "working_dir": str(project),
                "phase": "agent_select",
                "selected_round": 1,
            },
        )
        assert session["selected_round"] == 2


# ---------------------------------------------------------------------------
# The pane's controls, unit level
# ---------------------------------------------------------------------------


def _present(path: str, resolved: pathlib.Path | None = None) -> ArtifactResolution:
    """A ``present`` resolution for `path`, with metadata that is never
    inspected by the functions these fixtures feed."""
    return ArtifactResolution(
        RESOLUTION_PRESENT, path, "ref", "designer", resolved, 10, 0.0
    )


def _missing(path: str) -> ArtifactResolution:
    return ArtifactResolution(
        RESOLUTION_MISSING, path, "ref", "designer", None, None, None
    )


class TestArtifactControls:
    """Download and Open rendered, built from a resolution alone."""

    def test_nothing_selected_still_offers_a_download_button_disabled(self) -> None:
        row = artifact_controls(None)
        assert DOWNLOAD_BTN_ID in _ids(row)
        assert _by_id(row, DOWNLOAD_BTN_ID).disabled is True

    def test_nothing_selected_offers_no_open_rendered_button(self) -> None:
        assert OPEN_RENDERED_BTN_ID not in _ids(artifact_controls(None))

    def test_a_rejected_selection_disables_download_and_omits_open_rendered(
        self,
    ) -> None:
        row = artifact_controls(
            ArtifactResolution(RESOLUTION_REJECTED, "x", None, None, None, None, None)
        )
        assert _by_id(row, DOWNLOAD_BTN_ID).disabled is True
        assert OPEN_RENDERED_BTN_ID not in _ids(row)

    def test_a_missing_artifact_disables_download(self) -> None:
        row = artifact_controls(_missing("stack.json"))
        assert _by_id(row, DOWNLOAD_BTN_ID).disabled is True

    def test_a_present_artifact_enables_download(self) -> None:
        row = artifact_controls(_present("stack.json"))
        assert _by_id(row, DOWNLOAD_BTN_ID).disabled is False

    def test_a_present_non_mock_artifact_offers_no_open_rendered_button(self) -> None:
        assert OPEN_RENDERED_BTN_ID not in _ids(
            artifact_controls(_present("stack.json"))
        )

    def test_a_present_mock_offers_an_enabled_open_rendered_button(self) -> None:
        row = artifact_controls(_present(MOCK_HTML_PATH))
        assert _by_id(row, OPEN_RENDERED_BTN_ID).disabled is False

    def test_a_missing_mock_offers_a_disabled_open_rendered_button(self) -> None:
        """Present in the DOM — it is the mock — but nothing to open yet."""
        row = artifact_controls(_missing(MOCK_HTML_PATH))
        assert _by_id(row, OPEN_RENDERED_BTN_ID).disabled is True

    def test_neither_button_names_a_colour_of_its_own(self) -> None:
        """D-LR2: both are the theme's neutral outline."""
        row = artifact_controls(_present(MOCK_HTML_PATH))
        for node in _nodes(row):
            assert getattr(node, "color", None) is None
            assert getattr(node, "style", None) is None


class TestMockHtmlForStore:
    """The clientside Open-rendered handler's only source of HTML."""

    def test_nothing_selected_is_empty(self) -> None:
        assert mock_html_for_store(None) == ""

    def test_a_present_non_mock_artifact_is_empty(self) -> None:
        assert mock_html_for_store(_present("stack.json")) == ""

    def test_a_missing_mock_is_empty(self) -> None:
        assert mock_html_for_store(_missing(MOCK_HTML_PATH)) == ""

    def test_a_rejected_selection_is_empty(self) -> None:
        rejected = ArtifactResolution(
            RESOLUTION_REJECTED, MOCK_HTML_PATH, None, None, None, None, None
        )
        assert mock_html_for_store(rejected) == ""

    def test_a_present_mock_returns_its_raw_text(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "mock.html"
        path.write_text("<h1>Mock</h1>", encoding="utf-8")
        assert mock_html_for_store(_present(MOCK_HTML_PATH, path)) == "<h1>Mock</h1>"

    def test_it_reads_through_the_read_seam(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """So a test that watches `_read` catches a store built off it too."""
        path = tmp_path / "mock.html"
        path.write_text("<h1>Mock</h1>", encoding="utf-8")
        reads = _watch_reads(monkeypatch)
        mock_html_for_store(_present(MOCK_HTML_PATH, path))
        assert reads == [path]


# ---------------------------------------------------------------------------
# The controls, wired into the screen
# ---------------------------------------------------------------------------


class TestTheDownloadButtonOnScreen:
    def _layout(self, working_dir: pathlib.Path, **session: Any) -> Any:
        return _artifact_view_layout(
            {**_default_session(), "working_dir": str(working_dir), **session}
        )

    def test_it_is_present_and_disabled_with_nothing_selected(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_round(tmp_path, 1, ["stack.json"])
        btn = _by_id(self._layout(tmp_path, selected_round=1), DOWNLOAD_BTN_ID)
        assert btn.disabled is True

    def test_it_is_enabled_for_a_present_artifact(self, tmp_path: pathlib.Path) -> None:
        _make_round(tmp_path, 1, ["stack.json"])
        layout = self._layout(tmp_path, selected_round=1, selected_file="stack.json")
        assert _by_id(layout, DOWNLOAD_BTN_ID).disabled is False

    def test_it_is_disabled_for_a_missing_artifact(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_round(tmp_path, 1, [])
        layout = self._layout(tmp_path, selected_round=1, selected_file="vision.json")
        assert _by_id(layout, DOWNLOAD_BTN_ID).disabled is True

    def test_it_is_disabled_for_a_rejected_selection(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_round(tmp_path, 1, ["stack.json"])
        layout = self._layout(
            tmp_path, selected_round=1, selected_file="../../etc/passwd"
        )
        assert _by_id(layout, DOWNLOAD_BTN_ID).disabled is True

    def test_the_download_component_is_on_the_screen(
        self, tmp_path: pathlib.Path
    ) -> None:
        assert DOWNLOAD_ID in _ids(_artifact_view_layout(_default_session()))


class TestTheOpenRenderedButtonOnScreen:
    @pytest.fixture
    def project(self, tmp_path: pathlib.Path) -> pathlib.Path:
        base = _make_round(tmp_path, 1, ["stack.json"])
        (base / "design").mkdir()
        (base / "design" / "mock.html").write_text("<h1>Mock</h1>", encoding="utf-8")
        return tmp_path

    def _layout(self, project: pathlib.Path, selected_file: str | None) -> Any:
        return _artifact_view_layout(
            {
                **_default_session(),
                "working_dir": str(project),
                "selected_round": 1,
                "selected_file": selected_file,
            }
        )

    def test_it_is_present_for_the_mock(self, project: pathlib.Path) -> None:
        assert OPEN_RENDERED_BTN_ID in _ids(self._layout(project, MOCK_HTML_PATH))

    def test_it_is_absent_for_every_other_artifact(self, project: pathlib.Path) -> None:
        assert OPEN_RENDERED_BTN_ID not in _ids(self._layout(project, "stack.json"))

    def test_it_is_absent_when_nothing_is_selected(self, project: pathlib.Path) -> None:
        assert OPEN_RENDERED_BTN_ID not in _ids(self._layout(project, None))

    def test_the_store_carries_the_mock_s_raw_html(self, project: pathlib.Path) -> None:
        store = _by_id(self._layout(project, MOCK_HTML_PATH), MOCK_STORE_ID)
        assert store.data == {"mock_html": "<h1>Mock</h1>"}

    def test_the_store_is_empty_for_a_different_selection(
        self, project: pathlib.Path
    ) -> None:
        store = _by_id(self._layout(project, "stack.json"), MOCK_STORE_ID)
        assert store.data == {"mock_html": ""}

    def test_the_store_is_empty_when_the_mock_is_missing(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_round(tmp_path, 1, ["stack.json"])
        store = _by_id(self._layout(tmp_path, MOCK_HTML_PATH), MOCK_STORE_ID)
        assert store.data == {"mock_html": ""}


# ---------------------------------------------------------------------------
# The download callback
# ---------------------------------------------------------------------------


class TestTheDownloadCallback:
    @pytest.fixture
    def project(self, tmp_path: pathlib.Path) -> pathlib.Path:
        _make_round(tmp_path, 1, ["stack.json"])
        return tmp_path

    def _session(self, project: pathlib.Path, **extra: Any) -> dict[str, Any]:
        return {
            **_default_session(),
            "working_dir": str(project),
            "selected_round": 1,
            **extra,
        }

    def test_a_present_artifact_is_sent(
        self, project: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sentinel = {"filename": "stack.json", "content": "sent"}
        send_file = MagicMock(return_value=sentinel)
        monkeypatch.setattr(artifact_view_callbacks.dcc, "send_file", send_file)
        session = self._session(project, selected_file="stack.json")
        assert on_artifact_download(1, session) is sentinel
        send_file.assert_called_once_with(
            str((project / ".spec4" / "v1" / "stack.json").resolve())
        )

    @pytest.mark.parametrize(
        "selected_file",
        [
            pytest.param(None, id="nothing-selected"),
            pytest.param("vision.json", id="missing"),
            pytest.param("../../etc/passwd", id="rejected"),
        ],
    )
    def test_anything_but_present_sends_nothing(
        self,
        project: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        selected_file: str | None,
    ) -> None:
        send_file = MagicMock()
        monkeypatch.setattr(artifact_view_callbacks.dcc, "send_file", send_file)
        session = self._session(project, selected_file=selected_file)
        assert on_artifact_download(1, session) is no_update
        send_file.assert_not_called()

    @pytest.mark.parametrize("n_clicks", [None, 0])
    def test_a_render_with_no_click_sends_nothing(
        self, project: pathlib.Path, n_clicks: int | None
    ) -> None:
        session = self._session(project, selected_file="stack.json")
        assert on_artifact_download(n_clicks, session) is no_update


# ---------------------------------------------------------------------------
# D-LR2: the header is now shared with the controls beside it
# ---------------------------------------------------------------------------


class TestTheContentPaneHead:
    def test_the_header_and_the_controls_share_one_row(
        self, tmp_path: pathlib.Path
    ) -> None:
        """`HEADER_ID` sits beside the controls, not above or inside them —
        both are ultimately children of the same flex row."""
        _make_round(tmp_path, 1, ["stack.json"])
        layout = _artifact_view_layout(
            {
                **_default_session(),
                "working_dir": str(tmp_path),
                "selected_round": 1,
                "selected_file": "stack.json",
            }
        )
        content = _by_id(layout, "artifact-view-content")
        head_row = content.children[0]
        assert [c.id for c in head_row.children if getattr(c, "id", None)] == [
            HEADER_ID
        ]
        assert DOWNLOAD_BTN_ID in _ids(head_row)
