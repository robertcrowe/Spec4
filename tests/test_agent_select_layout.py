"""Alert rendering for the agent-select page.

A pending brownfield round (the highest .spec4/v{N}/ holds an IMPLEMENTED
marker) must show the new-round message and suppress both the empty-directory
alert and the "Loaded from .spec4/" alert — the latter would otherwise report
prior-round artifacts (e.g. design/mock.html, still on disk under the
implemented round) that the new round does not treat as active.

The page's introduction (D-LR13) is held here too: one line of orientation
and a closed "How Spec4 works", as the first thing on the view. The renderer
it comes from is ``test_intro_disclosure.py``'s subject; what is asserted here
is this screen's use of it — the copy, the labels, and where it stands.
"""

import json
import pathlib
from typing import Any

from spec4 import project_manager
from spec4.layouts import (
    PROJECT_INTRO_BODY_ID,
    PROJECT_INTRO_TOGGLE_ID,
    agent_select_layout,
    working_dir_layout,
)
from spec4.layouts._agent_rows import ACTION_LABELS
from spec4.layouts._status_bar import NAV_ORDER
from spec4.session import default_session, load_working_dir


def _alert_texts(component: Any) -> list[str]:
    """Collect the text of every dmc.Alert in a rendered component tree."""
    found: list[str] = []

    def walk(node: Any) -> None:
        if type(node).__name__ == "Alert":
            children = getattr(node, "children", "")
            found.append(children if isinstance(children, str) else str(children))
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            for child in children:
                walk(child)

    walk(component)
    return found


def _base_session() -> dict[str, Any]:
    s = default_session()
    s["provider"] = "openai"
    s["api_key"] = "sk-test"
    return s


def _implemented_v0_with_mock(tmp_path: pathlib.Path) -> None:
    v0 = tmp_path / ".spec4" / "v0"
    (v0 / "design").mkdir(parents=True)
    (v0 / "vision.json").write_text(json.dumps({"name": "ShelfLife"}))
    (v0 / "design" / "mock.html").write_text("<html></html>")
    (v0 / "IMPLEMENTED").write_text("")


class TestNewRoundAlerts:
    def test_shows_new_round_message_with_app_name(
        self, tmp_path: pathlib.Path
    ) -> None:
        _implemented_v0_with_mock(tmp_path)
        session = load_working_dir(str(tmp_path), _base_session())
        texts = _alert_texts(agent_select_layout(session))
        assert any(
            "previous version of ShelfLife has been implemented" in t
            and "CodeScanner" in t
            for t in texts
        )

    def test_suppresses_empty_directory_alert(self, tmp_path: pathlib.Path) -> None:
        _implemented_v0_with_mock(tmp_path)
        session = load_working_dir(str(tmp_path), _base_session())
        texts = _alert_texts(agent_select_layout(session))
        assert not any("project directory is empty" in t for t in texts)

    def test_suppresses_loaded_from_alert(self, tmp_path: pathlib.Path) -> None:
        # mock.html still exists on disk under the implemented round, so the
        # Loaded-from alert would fire without the new-round suppression.
        _implemented_v0_with_mock(tmp_path)
        session = load_working_dir(str(tmp_path), _base_session())
        texts = _alert_texts(agent_select_layout(session))
        assert not any("Loaded from .spec4/" in t for t in texts)

    def test_falls_back_when_no_prior_name(self, tmp_path: pathlib.Path) -> None:
        # A prior vision without a name must not break the message.
        v0 = tmp_path / ".spec4" / "v0"
        v0.mkdir(parents=True)
        (v0 / "vision.json").write_text(json.dumps({"description": "no name"}))
        (v0 / "IMPLEMENTED").write_text("")
        session = load_working_dir(str(tmp_path), _base_session())
        texts = _alert_texts(agent_select_layout(session))
        assert any("Your previous version has been implemented" in t for t in texts)


# ---------------------------------------------------------------------------
# The introduction (D-LR13)
# ---------------------------------------------------------------------------

# Written out here rather than imported: the point is that the words on screen
# are these words, and a constant shared with the layout would pass whatever it
# said.
_INTRO = (
    "Seven agents, in order. Each reads what the ones before it wrote, and "
    "everything they write is a file under .spec4/ in this project."
)

# The notes, element by element: a paragraph is its text, the list is its
# items' texts.
_NOTES: list[str | list[str]] = [
    "The table is the pipeline. Rows run top to bottom, and the button on each "
    "row is the one thing you can do with that agent right now:",
    [
        "Start — ready to run.",
        "Continue — a conversation is in progress; pick it up where you left it.",
        "Modify — the artifact exists and can be revised.",
        "Needs Update — something upstream changed since this agent ran.",
        "Not Ready — an input this agent needs hasn't been produced yet.",
        "Required — start here; the round can't proceed until this agent runs.",
    ],
    "Each pass over the project is a round, kept in its own .spec4/v{N}/ "
    "folder. When a round has been implemented, the next one starts with "
    "CodeScanner, so the plan is made against the code as it was actually "
    "built — not against the previous plan.",
    "The cost strip is this round's estimated spend, from usage.json; your "
    "provider's bill is authoritative. The round tree below it lists every "
    "artifact, and each line opens that file in Artifacts.",
    "Settings sets the project's default model. Each agent's gate can "
    "override it for that agent alone.",
]

_INTRO_IDS = {PROJECT_INTRO_TOGGLE_ID, PROJECT_INTRO_BODY_ID}


def _walk(node: Any) -> list[Any]:
    """Every component in a rendered tree, the root included, in order."""
    if isinstance(node, (list, tuple)):
        return [found for item in node for found in _walk(item)]
    if not hasattr(node, "_prop_names"):
        return []
    children = getattr(node, "children", None)
    if children is None or isinstance(children, str):
        return [node]
    return [node, *_walk(children)]


def _ids(node: Any) -> set[str]:
    return {c.id for c in _walk(node) if isinstance(getattr(c, "id", None), str)}


def _by_id(node: Any, component_id: str) -> Any:
    return next(c for c in _walk(node) if getattr(c, "id", None) == component_id)


def _text(node: Any) -> str:
    """A rendered tree's text, its strings joined the way the browser runs them."""
    if isinstance(node, str):
        return node
    if isinstance(node, (list, tuple)):
        return "".join(_text(n) for n in node)
    return _text(getattr(node, "children", None) or "")


def _mono(node: Any) -> list[str]:
    return [
        c.children
        for c in _walk(node)
        if "mono" in (getattr(c, "className", None) or "").split()
    ]


def _view(tmp_path: pathlib.Path) -> Any:
    """The project view of an open, empty project: no mode question to ask."""
    return agent_select_layout(load_working_dir(str(tmp_path), _base_session()))


class TestPipelineIntroduction:
    """D-LR13: the project view opens with one line of orientation and a
    closed "How Spec4 works", drawn by the renderer Designer's introduction
    uses (D-LR12)."""

    def test_it_is_the_first_thing_on_the_view(self, tmp_path: pathlib.Path) -> None:
        view = _view(tmp_path)
        assert _ids(view.children[0]) >= _INTRO_IDS
        assert getattr(view.children[1], "id", None) == "agent-rows"

    def test_the_line_is_the_sentence_verbatim(self, tmp_path: pathlib.Path) -> None:
        line = _view(tmp_path).children[0].children[0]
        assert type(line).__name__ == "Text"
        assert _text(line) == _INTRO
        assert "dim-line" not in (getattr(line, "className", None) or "").split()

    def test_the_line_s_path_is_monospace(self, tmp_path: pathlib.Path) -> None:
        assert _mono(_view(tmp_path).children[0].children[0]) == [".spec4/"]

    def test_the_toggle_names_the_notes_and_they_start_closed(
        self, tmp_path: pathlib.Path
    ) -> None:
        view = _view(tmp_path)
        assert _by_id(view, PROJECT_INTRO_TOGGLE_ID).children == "How Spec4 works"
        body = _by_id(view, PROJECT_INTRO_BODY_ID)
        assert type(body).__name__ == "Collapse"
        assert body.opened is False

    def test_the_six_labels_are_the_table_s_own(self, tmp_path: pathlib.Path) -> None:
        """Asserted against the constant, so a renamed button fails here."""
        body = _by_id(_view(tmp_path), PROJECT_INTRO_BODY_ID)
        strong = [c.children for c in _walk(body) if type(c).__name__ == "Strong"]
        assert strong == [
            ACTION_LABELS[state]
            for state in (
                project_manager.AGENT_BTN_START,
                project_manager.AGENT_BTN_CONTINUE,
                project_manager.AGENT_BTN_MODIFY,
                project_manager.AGENT_BTN_NEEDS_UPDATE,
                project_manager.AGENT_BTN_NOT_READY,
                project_manager.AGENT_BTN_REQUIRED,
            )
        ]

    def test_the_notes_are_the_copy_verbatim(self, tmp_path: pathlib.Path) -> None:
        div = _by_id(_view(tmp_path), PROJECT_INTRO_BODY_ID).children
        rendered = [
            [_text(item) for item in child.children]
            if type(child).__name__ == "Ul"
            else _text(child)
            for child in div.children
        ]
        assert rendered == _NOTES

    def test_the_notes_are_dimmed_and_their_paths_monospace(
        self, tmp_path: pathlib.Path
    ) -> None:
        div = _by_id(_view(tmp_path), PROJECT_INTRO_BODY_ID).children
        assert "dim-line" in div.className.split()
        assert _mono(div) == [".spec4/v{N}/", "usage.json"]

    def test_the_screens_it_names_are_the_status_bar_s(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Artifacts and Settings, as the nav writes them."""
        text = _text(_by_id(_view(tmp_path), PROJECT_INTRO_BODY_ID))
        assert f"each line opens that file in {NAV_ORDER[1]}." in text
        assert f"{NAV_ORDER[2]} sets the project's default model." in text

    def test_neither_id_is_on_the_picker_or_the_mode_question(
        self, tmp_path: pathlib.Path
    ) -> None:
        opened = tmp_path / "open"
        opened.mkdir()
        assert _ids(_view(opened)) >= _INTRO_IDS

        picker = working_dir_layout({**_base_session(), "browser_path": str(tmp_path)})
        assert "btn-dir-select" in _ids(picker)
        assert not _INTRO_IDS & _ids(picker)

        busy = tmp_path / "busy"
        busy.mkdir()
        (busy / "main.py").write_text("print('hi')\n")
        session = load_working_dir(str(busy), _base_session())
        session["project_mode"] = None
        question = agent_select_layout(session)
        assert "btn-project-mode-existing" in _ids(question)
        assert not _INTRO_IDS & _ids(question)
