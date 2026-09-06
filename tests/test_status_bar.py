"""The shell is a status bar and three nav links, and nothing else.

Two altitudes here. The first calls ``_status_bar()`` directly and asserts on
the component tree it returns — what is present, what the nav says, and what
the marketing-era shell left behind that must not come back. The second drives
``on_status_bar`` the way Dash does, since the bar's whole job is to be right
after the developer switches projects, and a callback that only ran on page
load would pass every render test while showing a stale directory.
"""

from __future__ import annotations

import pathlib
from typing import Any

import spec4.app as app_module
from spec4 import __version__
from spec4.callbacks import on_status_bar
from spec4.layouts import STATUS_EMPTY, _status_bar
from spec4.session import _default_session

# The marketing-era shell, gone in this round. `nav-*` are the external-link
# drawer, `blueprint-grid` the grid background behind everything.
_REMOVED_SHELL_IDS = {
    "nav-drawer",
    "nav-overlay",
    "nav-burger",
    "nav-close-btn",
    "blueprint-grid",
}


def _ids(component: Any) -> set[str]:
    """Every string component id in a rendered tree."""
    found: set[str] = set()
    stack = [component]
    while stack:
        node = stack.pop()
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


def _class_names(component: Any) -> list[str]:
    """Every className in a rendered tree."""
    found: list[str] = []
    stack = [component]
    while stack:
        node = stack.pop()
        name = getattr(node, "className", None)
        if isinstance(name, str):
            found.append(name)
        children = getattr(node, "children", None)
        if children is None:
            continue
        if not isinstance(children, (list, tuple)):
            children = [children]
        stack.extend(children)
    return found


def _nav(bar: Any) -> Any:
    """The bar's ``<nav>``."""
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


def _nav_labels(bar: Any) -> list[str]:
    """The nav's link labels, in render order."""
    return [
        child.children
        for child in _nav(bar).children
        if type(child).__name__ in ("Link", "A")
    ]


def _text(children: Any) -> str:
    """Flatten a context line back to the string a developer reads."""
    if isinstance(children, str):
        return children
    if isinstance(children, (list, tuple)):
        return "".join(_text(child) for child in children)
    inner = getattr(children, "children", None)
    return _text(inner) if inner is not None else ""


# ---------------------------------------------------------------------------
# The rendered shell
# ---------------------------------------------------------------------------


class TestStatusBarLayout:
    def test_the_status_bar_id_is_present(self) -> None:
        assert "status-bar" in _ids(_status_bar())

    def test_it_renders_all_four_fields(self) -> None:
        """The context line, the version, and the ids the callback writes to."""
        ids = _ids(_status_bar())
        assert {
            "status-bar-context",
            "status-bar-version",
            "status-bar-nav-project",
            "status-bar-nav-settings",
            "status-bar-nav-docs",
        } <= ids

    def test_the_nav_is_exactly_project_settings_docs(self) -> None:
        assert _nav_labels(_status_bar()) == ["Project", "Settings", "Docs"]

    def test_there_is_no_artifacts_nav_item(self) -> None:
        """Not as a link and not as a disabled placeholder either.

        Artifacts arrives in v1 with the Artifact View; a greyed-out item now
        would promise a screen that does not exist.
        """
        bar = _status_bar()
        assert not any("artifact" in label.lower() for label in _nav_labels(bar))
        assert not any("artifact" in i.lower() for i in _ids(bar))

    def test_docs_is_the_one_external_link(self) -> None:
        docs = _nav(_status_bar()).children[2]
        assert docs.href.startswith("https://")
        assert docs.target == "_blank"

    def test_the_version_is_the_running_one(self) -> None:
        versions = [
            node.children
            for node in _nav(_status_bar()).children
            if getattr(node, "id", None) == "status-bar-version"
        ]
        assert versions == [__version__]

    def test_the_mono_fields_are_marked_monospace(self) -> None:
        """Working directory, provider/model and version ride in JetBrains Mono."""
        classes = " ".join(_class_names(_status_bar()))
        assert classes.count("mono") >= 2

    def test_it_uses_no_icon_component(self) -> None:
        """dash-iconify is not used by anything this round — text only."""
        stack = [_status_bar()]
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


class TestTheShellHasNoMarketingChrome:
    def test_the_drawer_and_grid_ids_are_gone(self) -> None:
        assert not _REMOVED_SHELL_IDS & _ids(app_module.app.layout)

    def test_the_shell_mounts_the_status_bar(self) -> None:
        assert "status-bar" in _ids(app_module.app.layout)

    def test_the_page_no_longer_carries_a_footer(self) -> None:
        """`render_page` used to wrap every screen in the marketing footer."""
        content, _, _ = app_module.render_page(
            _default_session(), {}, 0, None, None
        )
        assert "footer" not in _class_names(content)
        assert not any(
            type(node).__name__ == "Footer" for node in [content, *_flatten(content)]
        )

    def test_the_layout_helpers_are_gone(self) -> None:
        """The functions go with the components, not just the call sites."""
        import spec4.layouts as layouts

        assert not hasattr(layouts, "_footer")
        assert not hasattr(layouts, "_nav_drawer")


def _flatten(component: Any) -> list[Any]:
    out: list[Any] = []
    stack = [component]
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
# The callback
# ---------------------------------------------------------------------------


def _session(**extra: Any) -> dict[str, Any]:
    session = _default_session()
    session.update(
        {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "api_key": "k",
            "llm_config": {"model": "claude-sonnet-4-6", "api_key": "k"},
        }
    )
    session.update(extra)
    return session


class TestStatusBarCallback:
    def test_it_shows_the_four_values(self, tmp_path: pathlib.Path) -> None:
        context, _, _ = on_status_bar(_session(working_dir=str(tmp_path)), {})
        text = _text(context)
        assert str(tmp_path) in text
        assert "round v0" in text
        assert "anthropic" in text
        assert "claude-sonnet-4-6" in text

    def test_every_field_has_an_explicit_empty_state(self) -> None:
        """A missing value renders a placeholder, never a blank gap."""
        context, _, _ = on_status_bar({}, {})
        assert _text(context).count(STATUS_EMPTY) == 4

    def test_it_recomputes_after_switching_projects(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The stale-working-directory failure mode, driven directly.

        Both stores are Inputs, so Dash calls this again the moment the session
        store is rewritten — which is exactly what opening a second project
        does.
        """
        first = tmp_path / "one"
        second = tmp_path / "two"
        first.mkdir()
        second.mkdir()

        before, _, _ = on_status_bar(_session(working_dir=str(first)), {})
        after, _, _ = on_status_bar(_session(working_dir=str(second)), {})

        assert str(first) in _text(before)
        assert str(first) not in _text(after)
        assert str(second) in _text(after)

    def test_it_follows_the_round(self, tmp_path: pathlib.Path) -> None:
        session = _session(working_dir=str(tmp_path), phase_version=3)
        context, _, _ = on_status_bar(session, {})
        assert "round v3" in _text(context)

    def test_it_falls_back_to_the_remembered_prefs(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A fresh browser session has prefs but not yet a loaded session."""
        prefs = {
            "working_dir": str(tmp_path),
            "provider": "openai",
            "model": "gpt-5-mini",
        }
        context, _, _ = on_status_bar({}, prefs)
        text = _text(context)
        assert str(tmp_path) in text
        assert "openai" in text
        assert "gpt-5-mini" in text

    def test_a_per_agent_override_does_not_replace_the_default(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The bar shows the *default*, which is what /setup configured.

        It resolves through ``llm_selection`` rather than reaching into the
        session itself, so an agent pinned to another model cannot leak into
        the shell.
        """
        session = _session(
            working_dir=str(tmp_path),
            agent_llm={
                "phaser": {
                    "provider": "openai",
                    "model": "gpt-5",
                    "llm_config": {"model": "gpt-5", "api_key": "sk"},
                }
            },
        )
        context, _, _ = on_status_bar(session, {})
        text = _text(context)
        assert "claude-sonnet-4-6" in text
        assert "gpt-5" not in text

    def test_it_marks_project_as_current_by_default(self) -> None:
        _, project, settings = on_status_bar(_session(phase="agent_select"), {})
        assert "active" in project
        assert "active" not in settings

    def test_the_setup_wizard_marks_settings(self) -> None:
        _, project, settings = on_status_bar(_session(phase="setup"), {})
        assert "active" not in project
        assert "active" in settings

    def test_it_survives_empty_stores(self) -> None:
        """The very first render, before either store has been written."""
        assert on_status_bar(None, None) is not None
