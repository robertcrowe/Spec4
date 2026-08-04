"""Alert rendering for the agent-select page.

A pending brownfield round (the highest .spec4/v{N}/ holds an IMPLEMENTED
marker) must show the new-round message and suppress both the empty-directory
alert and the "Loaded from .spec4/" alert — the latter would otherwise report
prior-round artifacts (e.g. design/mock.html, still on disk under the
implemented round) that the new round does not treat as active.
"""

import json
import pathlib
from typing import Any

from spec4.layouts import _agent_select_layout
from spec4.session import _default_session, _load_working_dir


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
    s = _default_session()
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
        session = _load_working_dir(str(tmp_path), _base_session())
        texts = _alert_texts(_agent_select_layout(session))
        assert any(
            "previous version of ShelfLife has been implemented" in t
            and "CodeScanner" in t
            for t in texts
        )

    def test_suppresses_empty_directory_alert(
        self, tmp_path: pathlib.Path
    ) -> None:
        _implemented_v0_with_mock(tmp_path)
        session = _load_working_dir(str(tmp_path), _base_session())
        texts = _alert_texts(_agent_select_layout(session))
        assert not any("project directory is empty" in t for t in texts)

    def test_suppresses_loaded_from_alert(self, tmp_path: pathlib.Path) -> None:
        # mock.html still exists on disk under the implemented round, so the
        # Loaded-from alert would fire without the new-round suppression.
        _implemented_v0_with_mock(tmp_path)
        session = _load_working_dir(str(tmp_path), _base_session())
        texts = _alert_texts(_agent_select_layout(session))
        assert not any("Loaded from .spec4/" in t for t in texts)

    def test_falls_back_when_no_prior_name(
        self, tmp_path: pathlib.Path
    ) -> None:
        # A prior vision without a name must not break the message.
        v0 = tmp_path / ".spec4" / "v0"
        v0.mkdir(parents=True)
        (v0 / "vision.json").write_text(json.dumps({"description": "no name"}))
        (v0 / "IMPLEMENTED").write_text("")
        session = _load_working_dir(str(tmp_path), _base_session())
        texts = _alert_texts(_agent_select_layout(session))
        assert any(
            "Your previous version has been implemented" in t for t in texts
        )
