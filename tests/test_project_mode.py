"""D-PM1: ask whether a non-empty directory holds an existing project.

Spec4 used to infer brownfield from directory contents alone, which meant a
`uv init` skeleton read as a real codebase. The developer is asked instead,
once per browser session, and the answer is never written to disk.

Covers:
- directory_has_content: what counts as occupied (.spec4/ does not)
- needs_project_mode: when the question is asked, and that artifacts on disk
  never answer it on the developer's behalf
- the /agents gate replaces the agent list until answered
- the answer drives the agents-page guidance and Designer's capture offer
- the answer is session-scoped, so a restart asks again
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from spec4 import project_manager
from spec4.app_constants import PROJECT_MODE_EXISTING, PROJECT_MODE_NEW
from spec4.layouts import _agent_select_layout
from spec4.session import _default_session, _load_working_dir


def _walk_ids(component: Any, out: list[Any]) -> None:
    if hasattr(component, "id"):
        out.append(component.id)
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            _walk_ids(child, out)
    elif children is not None:
        _walk_ids(children, out)


def _ids(component: Any) -> list[Any]:
    out: list[Any] = []
    _walk_ids(component, out)
    return out


def _text(component: Any) -> str:
    chunks: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            chunks.append(node)
            return
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            for child in children:
                walk(child)
        elif children is not None:
            walk(children)

    walk(component)
    return " ".join(chunks)


def _session(tmp_path: pathlib.Path, **overrides: Any) -> dict[str, Any]:
    session = _default_session()
    session.update({"working_dir": str(tmp_path), "phase": "agent_select"})
    session.update(overrides)
    return session


# ---------------------------------------------------------------------------
# directory_has_content
# ---------------------------------------------------------------------------


class TestDirectoryHasContent:
    def test_empty_directory(self, tmp_path: pathlib.Path) -> None:
        assert project_manager.directory_has_content(tmp_path) is False

    def test_spec4_bookkeeping_does_not_count(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Counting our own directory would flag every project Spec4 touched."""
        (tmp_path / ".spec4" / "v0").mkdir(parents=True)
        (tmp_path / ".spec4" / "v0" / "vision.json").write_text("{}")
        assert project_manager.directory_has_content(tmp_path) is False

    def test_a_single_source_file_counts(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / "main.py").write_text("print('hi')")
        assert project_manager.directory_has_content(tmp_path) is True

    def test_uv_init_skeleton_counts(self, tmp_path: pathlib.Path) -> None:
        # The case that motivated this: indistinguishable from real code.
        for name in ("main.py", "pyproject.toml", "README.md"):
            (tmp_path / name).write_text("x")
        assert project_manager.directory_has_content(tmp_path) is True

    def test_no_working_dir(self) -> None:
        assert project_manager.directory_has_content(None) is False

    def test_missing_directory(self, tmp_path: pathlib.Path) -> None:
        assert project_manager.directory_has_content(tmp_path / "nope") is False


# ---------------------------------------------------------------------------
# needs_project_mode
# ---------------------------------------------------------------------------


class TestNeedsProjectMode:
    def test_asked_when_directory_is_occupied(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / "main.py").write_text("x")
        assert project_manager.needs_project_mode(tmp_path, _default_session())

    def test_not_asked_for_an_empty_directory(
        self, tmp_path: pathlib.Path
    ) -> None:
        assert not project_manager.needs_project_mode(tmp_path, _default_session())

    def test_not_asked_once_answered(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / "main.py").write_text("x")
        for mode in (PROJECT_MODE_EXISTING, PROJECT_MODE_NEW):
            session = {**_default_session(), "project_mode": mode}
            assert not project_manager.needs_project_mode(tmp_path, session)

    def test_garbage_answer_is_not_an_answer(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / "main.py").write_text("x")
        session = {**_default_session(), "project_mode": "maybe"}
        assert project_manager.needs_project_mode(tmp_path, session)

    def test_code_review_does_not_answer_it(self, tmp_path: pathlib.Path) -> None:
        """A developer may run CodeScanner on a greenfield skeleton, so a
        code_review.json on disk is not evidence of an existing project."""
        (tmp_path / "main.py").write_text("x")
        v0 = tmp_path / ".spec4" / "v0"
        v0.mkdir(parents=True)
        (v0 / "code_review.json").write_text(
            json.dumps({"code_review": {"is_software_project": True}})
        )
        assert project_manager.needs_project_mode(tmp_path, _default_session())

    def test_a_full_pipeline_on_disk_does_not_answer_it(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / "main.py").write_text("x")
        v0 = tmp_path / ".spec4" / "v0"
        v0.mkdir(parents=True)
        for name in ("vision.json", "stack.json", "code_review.json"):
            (v0 / name).write_text("{}")
        assert project_manager.needs_project_mode(tmp_path, _default_session())

    def test_no_working_dir(self) -> None:
        assert not project_manager.needs_project_mode(None, _default_session())


# ---------------------------------------------------------------------------
# The /agents gate
# ---------------------------------------------------------------------------


class TestAgentsGate:
    def test_question_replaces_the_agent_list(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / "main.py").write_text("x")
        ids = _ids(_agent_select_layout(_session(tmp_path)))
        assert "btn-project-mode-existing" in ids
        assert "btn-project-mode-new" in ids
        assert not any(
            isinstance(i, dict) and i.get("type") == "agent-pill" for i in ids
        )

    def test_question_names_the_skeleton_case(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / "main.py").write_text("x")
        text = _text(_agent_select_layout(_session(tmp_path)))
        assert "uv init" in text

    def test_question_says_it_will_be_asked_again(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / "main.py").write_text("x")
        text = _text(_agent_select_layout(_session(tmp_path)))
        assert "asked again" in text

    def test_empty_directory_skips_the_question(
        self, tmp_path: pathlib.Path
    ) -> None:
        ids = _ids(_agent_select_layout(_session(tmp_path)))
        assert "btn-project-mode-existing" not in ids
        assert any(
            isinstance(i, dict) and i.get("type") == "agent-pill" for i in ids
        )

    def test_answering_reveals_the_agent_list(
        self, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / "main.py").write_text("x")
        for mode in (PROJECT_MODE_EXISTING, PROJECT_MODE_NEW):
            layout = _agent_select_layout(
                _session(tmp_path, project_mode=mode)
            )
            ids = _ids(layout)
            assert "btn-project-mode-existing" not in ids
            pills = [
                i for i in ids
                if isinstance(i, dict) and i.get("type") == "agent-pill"
            ]
            assert {p["agent"] for p in pills} >= {"code_scanner", "brainstormer"}


class TestGuidanceFollowsTheAnswer:
    def _text_for(self, tmp_path: pathlib.Path, mode: str | None) -> str:
        (tmp_path / "main.py").write_text("x")
        return _text(_agent_select_layout(_session(tmp_path, project_mode=mode)))

    def test_existing_nudges_code_scanner(self, tmp_path: pathlib.Path) -> None:
        text = self._text_for(tmp_path, PROJECT_MODE_EXISTING)
        assert "existing project here" in text
        assert "CodeScanner first" in text

    def test_new_treats_files_as_scaffolding(
        self, tmp_path: pathlib.Path
    ) -> None:
        text = self._text_for(tmp_path, PROJECT_MODE_NEW)
        assert "scaffolding" in text
        assert "CodeScanner is optional" in text

    def test_new_does_not_nudge_code_scanner(
        self, tmp_path: pathlib.Path
    ) -> None:
        text = self._text_for(tmp_path, PROJECT_MODE_NEW)
        assert "CodeScanner first" not in text

    def test_empty_directory_keeps_its_own_guidance(
        self, tmp_path: pathlib.Path
    ) -> None:
        text = _text(_agent_select_layout(_session(tmp_path)))
        assert "directory is empty" in text


# ---------------------------------------------------------------------------
# The callback
# ---------------------------------------------------------------------------


class _Ctx:
    def __init__(self, triggered_id: str | None) -> None:
        self.triggered_id = triggered_id


class TestCallback:
    def _choose(self, monkeypatch, button: str | None, n: int = 1) -> Any:
        from spec4 import callbacks as cb

        monkeypatch.setattr(cb, "ctx", _Ctx(button))
        existing = n if button == "btn-project-mode-existing" else 0
        new = n if button == "btn-project-mode-new" else 0
        return cb.on_project_mode_choice(existing, new, {"phase": "agent_select"})

    def test_existing_button(self, monkeypatch) -> None:
        out = self._choose(monkeypatch, "btn-project-mode-existing")
        assert out["project_mode"] == PROJECT_MODE_EXISTING

    def test_new_button(self, monkeypatch) -> None:
        out = self._choose(monkeypatch, "btn-project-mode-new")
        assert out["project_mode"] == PROJECT_MODE_NEW

    def test_clears_a_stale_precondition_error(self, monkeypatch) -> None:
        from spec4 import callbacks as cb

        monkeypatch.setattr(cb, "ctx", _Ctx("btn-project-mode-new"))
        out = cb.on_project_mode_choice(
            0, 1, {"agent_select_error": "Requires a vision statement."}
        )
        assert out["agent_select_error"] is None

    def test_no_click_is_a_no_op(self, monkeypatch) -> None:
        from dash import no_update

        assert self._choose(monkeypatch, "btn-project-mode-new", n=0) is no_update

    def test_no_trigger_is_a_no_op(self, monkeypatch) -> None:
        from dash import no_update

        assert self._choose(monkeypatch, None) is no_update


# ---------------------------------------------------------------------------
# The answer does not outlive the session
# ---------------------------------------------------------------------------


class TestDesignerFollowsTheAnswer:
    """D-PM1: "Modify existing" must not offer to reproduce a starter template."""

    def _has_existing_ui(
        self, tmp_path: pathlib.Path, mode: str | None
    ) -> bool:
        from spec4.layouts.designer import designer_layout

        (tmp_path / "index.html").write_text("<html><body>starter</body></html>")
        session = _session(tmp_path, project_mode=mode, phase="designer")
        layout = designer_layout(session)
        stores = [
            c
            for c in _flatten(layout)
            if getattr(c, "id", None) == "designer-session-store"
        ]
        assert stores, "designer-session-store not rendered"
        return bool(stores[0].data.get("_has_existing_ui"))

    def test_new_project_ignores_scaffolding_ui(
        self, tmp_path: pathlib.Path
    ) -> None:
        assert self._has_existing_ui(tmp_path, PROJECT_MODE_NEW) is False

    def test_existing_project_still_detects_ui(
        self, tmp_path: pathlib.Path
    ) -> None:
        assert self._has_existing_ui(tmp_path, PROJECT_MODE_EXISTING) is True

    def test_unanswered_behaves_as_before(self, tmp_path: pathlib.Path) -> None:
        assert self._has_existing_ui(tmp_path, None) is True

    def test_new_project_still_sees_a_saved_spec4_mock(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Spec4's own mock.html is our output, not the developer's scaffolding."""
        from spec4.layouts.designer import designer_layout

        design_dir = tmp_path / ".spec4" / "v0" / "design"
        design_dir.mkdir(parents=True)
        (design_dir / "mock.html").write_text("<html>spec4 mock</html>")
        session = _session(
            tmp_path, project_mode=PROJECT_MODE_NEW, phase="designer"
        )
        layout = designer_layout(session)
        store = next(
            c for c in _flatten(layout)
            if getattr(c, "id", None) == "designer-session-store"
        )
        assert store.data["_has_existing_ui"] is True


def _flatten(component: Any) -> list[Any]:
    out: list[Any] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            return
        out.append(node)
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            for child in children:
                walk(child)
        elif children is not None:
            walk(children)

    walk(component)
    return out


class TestAnswerIsSessionScoped:
    def test_default_session_is_unanswered(self) -> None:
        assert _default_session()["project_mode"] is None

    def test_answer_is_not_written_to_disk(self, tmp_path: pathlib.Path) -> None:
        """A restart re-reads .spec4/ and must not find the answer there."""
        (tmp_path / "main.py").write_text("x")
        session = _load_working_dir(str(tmp_path), _default_session())
        session["project_mode"] = PROJECT_MODE_NEW
        from spec4.session import _persist_artifacts

        _persist_artifacts(session)
        for path in (tmp_path / ".spec4").rglob("*"):
            if path.is_file():
                assert "project_mode" not in path.read_text(errors="replace")

    def test_a_fresh_session_asks_again(self, tmp_path: pathlib.Path) -> None:
        """Simulates quit-and-restart: a new session over the same directory."""
        (tmp_path / "main.py").write_text("x")
        answered = {**_default_session(), "project_mode": PROJECT_MODE_NEW}
        assert not project_manager.needs_project_mode(tmp_path, answered)
        restarted = _load_working_dir(str(tmp_path), _default_session())
        assert project_manager.needs_project_mode(tmp_path, restarted)
