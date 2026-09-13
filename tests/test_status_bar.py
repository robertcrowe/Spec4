"""The shell is a status bar and four nav links, and nothing else.

Two altitudes here. The first calls ``status_bar()`` directly and asserts on
the component tree it returns — what is present, what the nav says, and what
the marketing-era shell left behind that must not come back. The second drives
``on_status_bar`` the way Dash does, since the bar's whole job is to be right
after the developer switches projects, and a callback that only ran on page
load would pass every render test while showing a stale directory.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

import spec4.app as app_module
from spec4 import __version__
from spec4.app_constants import PATH_TO_PHASE, PHASE_ROOT
from spec4.callbacks import on_status_bar
from spec4 import llm_selection
from spec4.layouts import STATUS_EMPTY, status_bar
from spec4.layouts._status_bar import (
    ARTIFACTS_PATH,
    NAV_ORDER,
    NOT_CONNECTED,
    SLOT_CLASS,
    SLOT_CONNECTION,
    SLOT_MODEL,
    SLOT_PATH,
    SLOT_PROVIDER,
    SLOT_ROUND,
    SLOT_VERSION,
    _dir_field,
    status_context,
)
from spec4.session import default_session

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
    """The nav's entry labels, in render order.

    Settings is a button rather than a link — it resets the session instead of
    moving the URL — so the entry types are three, not two. The version span
    is not an entry and is not counted.
    """
    return [
        child.children
        for child in _nav(bar).children
        if type(child).__name__ in ("Link", "A", "Button")
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
        assert "status-bar" in _ids(status_bar())

    def test_it_renders_all_four_fields(self) -> None:
        """The context line, the version, and the ids the callback writes to."""
        ids = _ids(status_bar())
        assert {
            "status-bar-context",
            "status-bar-version",
            "status-bar-nav-project",
            "status-bar-nav-artifacts",
            "status-bar-nav-settings",
            "status-bar-nav-docs",
        } <= ids

    def test_the_nav_is_exactly_project_artifacts_settings_docs(self) -> None:
        assert _nav_labels(status_bar()) == [
            "Project",
            "Artifacts",
            "Settings",
            "Docs",
        ]

    def test_the_declared_order_is_the_rendered_order(self) -> None:
        """``NAV_ORDER`` is data the tests read; the bar is what a user sees.

        They are pinned to each other so the register cannot be changed in one
        place and asserted from the other.
        """
        assert _nav_labels(status_bar()) == list(NAV_ORDER)

    def test_artifacts_sits_between_project_and_settings(self) -> None:
        """The position the Artifact Links specification fixes, not merely its
        presence: the entry is a second way into the open project, so it goes
        beside Project rather than beside the app's own configuration."""
        labels = _nav_labels(status_bar())
        assert labels.index("Project") < labels.index("Artifacts")
        assert labels.index("Artifacts") < labels.index("Settings")

    def test_artifacts_is_an_in_app_route(self) -> None:
        """A ``dcc.Link`` to the routing table's path, not a page reload."""
        entry = _nav(status_bar()).children[1]
        assert type(entry).__name__ == "Link"
        assert entry.href == ARTIFACTS_PATH
        assert PATH_TO_PHASE[ARTIFACTS_PATH] == "artifacts"

    def test_docs_is_the_one_external_link(self) -> None:
        docs = _nav(status_bar()).children[3]
        assert docs.href.startswith("https://")
        assert docs.target == "_blank"

    def test_settings_is_a_button_not_a_route(self) -> None:
        """It restarts the wizard, which is a session reset and not a URL.

        `setup_layout` branches on session fields, so a `dcc.Link` to
        `/setup` would open whichever step the session happened to be on.
        The button carries the id `on_status_bar` marks active and the one
        `on_status_bar_setup` fires from; it has no href to be followed.
        """
        settings = _nav(status_bar()).children[2]
        assert type(settings).__name__ == "Button"
        assert settings.id == "status-bar-nav-settings"
        assert settings.children == "Settings"
        assert getattr(settings, "href", None) is None

    def test_no_nav_entry_names_a_colour(self) -> None:
        """D-LR2: the active accent is the theme primary, never a local prop."""
        for entry in _nav(status_bar()).children:
            assert getattr(entry, "color", None) is None
            assert getattr(entry, "style", None) is None

    def test_the_version_is_the_running_one(self) -> None:
        versions = [
            node.children
            for node in _nav(status_bar()).children
            if getattr(node, "id", None) == "status-bar-version"
        ]
        assert versions == [__version__]

    def test_the_mono_fields_are_marked_monospace(self) -> None:
        """Working directory, provider/model and version ride in JetBrains Mono."""
        classes = " ".join(_class_names(status_bar()))
        assert classes.count("mono") >= 2

    def test_it_uses_no_icon_component(self) -> None:
        """dash-iconify is not used by anything this round — text only."""
        stack = [status_bar()]
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


class TestOnlyThePathEverGivesUpSpace:
    """D-LR10 — the bar's slots, and which of them is allowed to shrink.

    The bar used to ellipsise as one line, so the browser cut whatever sat at
    its *end*: the model first, then the provider, then the round. Those three
    are short, fixed, and the reason to look at the bar at all; the working
    directory is the one arbitrarily long field. The fix is per-slot: every
    slot is pinned, the path alone shrinks, and it shortens from its start so
    the project name at the tail survives.

    Asserted at both altitudes, because either alone is half a claim. The
    layout side says the classes are attached to the right elements; the
    stylesheet side says those classes still mean what the layout is relying
    on them to mean. A rule renamed in `v3.css` would pass the first and fail
    the second.
    """

    def _slots(self, context: Any) -> dict[str, set[str]]:
        """Each slot's classes, keyed by the slot class that identifies it."""
        found: dict[str, set[str]] = {}
        stack = list(context)
        while stack:
            node = stack.pop()
            classes = set((getattr(node, "className", "") or "").split())
            for name in classes:
                if name.startswith("sb-slot--"):
                    found[name] = classes
            children = getattr(node, "children", None)
            if children is None:
                continue
            if not isinstance(children, (list, tuple)):
                children = [children]
            stack.extend(children)
        return found

    def _filled(self) -> dict[str, set[str]]:
        return self._slots(
            status_context("/home/dev/Projects/spec4/Spec4", 2, "anthropic", "m", True)
        )

    def test_every_value_on_the_line_is_its_own_slot(self) -> None:
        """Four values, four classes the stylesheet can target individually."""
        assert set(self._filled()) == {
            SLOT_PATH,
            SLOT_ROUND,
            SLOT_PROVIDER,
            SLOT_MODEL,
        }

    def test_the_working_directory_carries_the_shrinking_class(self) -> None:
        assert SLOT_PATH in self._filled()

    def test_round_provider_and_model_carry_the_pinned_class(self) -> None:
        slots = self._filled()
        for name in (SLOT_ROUND, SLOT_PROVIDER, SLOT_MODEL):
            assert SLOT_CLASS in slots[name], name
            assert SLOT_PATH not in slots[name], name

    def test_the_version_carries_the_pinned_class_too(self) -> None:
        """It is the one slot that lives in the nav rather than on the line."""
        version = next(
            node
            for node in _nav(status_bar()).children
            if getattr(node, "id", None) == "status-bar-version"
        )
        classes = set(version.className.split())
        assert {SLOT_CLASS, SLOT_VERSION} <= classes
        assert SLOT_PATH not in classes

    def test_the_empty_path_is_still_the_path_slot(self) -> None:
        """The em dash shrinks in the same place a real path would."""
        slots = self._slots(status_context(None, None, None, None, False))
        assert SLOT_PATH in slots

    def test_not_connected_is_one_pinned_slot_not_two(self) -> None:
        """It replaces the provider and the model, and it is one phrase."""
        slots = self._slots(status_context("/a/b", 0, None, None, False))
        assert SLOT_PROVIDER not in slots
        assert SLOT_MODEL not in slots
        assert SLOT_CLASS in slots[SLOT_CONNECTION]

    def test_the_path_text_is_isolated_left_to_right(self) -> None:
        """The half of the RTL trick that is easy to leave out.

        `.sb-slot--path` sets `direction: rtl` to move the ellipsis to the
        front of the path. Without an isolated left-to-right run inside it,
        `/home/dev/Spec4` renders as `Spec4/dev/home/`, which is the specific
        way this fix goes wrong.
        """
        button = _dir_field("/home/dev/Projects/spec4/Spec4")
        assert type(button.children).__name__ == "Bdi"
        assert button.children.children == "/home/dev/Projects/spec4/Spec4"

    def test_the_path_keeps_its_monospace_and_names_no_colour(self) -> None:
        """D-LR2: the slot classes are layout, not a second styling mechanism."""
        button = _dir_field("/a/b")
        assert "sb-dir" in button.className
        assert getattr(button, "style", None) is None
        assert "mono" in " ".join(_class_names(status_bar()))


class TestTheStylesheetPinsWhatTheLayoutMarks:
    """The other half of D-LR10: the classes above still mean what they say."""

    def _css(self) -> str:
        return (
            pathlib.Path(app_module.__file__).resolve().parent / "assets" / "v3.css"
        ).read_text(encoding="utf-8")

    def _rule(self, selector: str) -> str:
        css = self._css()
        match = re.search(
            rf"(?:^|\}}|\*/)\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", css
        )
        assert match, f"no rule for {selector} in v3.css"
        return match.group(1)

    def test_a_slot_never_shrinks(self) -> None:
        assert "flex: none" in self._rule(f".{SLOT_CLASS}")

    def test_nothing_else_on_the_line_shrinks_either(self) -> None:
        """The separators are not slots and would otherwise be squeezed."""
        assert "flex: none" in self._rule(".sb-ctx > *")

    def test_the_path_slot_is_the_one_that_shrinks_and_truncates(self) -> None:
        rule = self._rule(f".sb-ctx > .{SLOT_PATH}")
        assert "flex: 0 1 auto" in rule
        assert "min-width: 0" in rule
        assert "overflow: hidden" in rule
        assert "text-overflow: ellipsis" in rule

    def test_the_path_truncates_from_its_start(self) -> None:
        rule = self._rule(f".sb-ctx > .{SLOT_PATH}")
        assert "direction: rtl" in rule
        assert "text-align: left" in rule

    def test_the_reversal_is_scoped_to_that_slot_alone(self) -> None:
        """On a parent it would reverse the whole bar. It appears once.

        Comments are swept first — the rule explains itself in prose directly
        above the declaration, and a test that counted the explanation as a
        second reversal would have to be answered by deleting the comment.
        """
        swept = re.sub(r"/\*.*?\*/", "", self._css(), flags=re.S)
        assert len(re.findall(r"direction:\s*rtl", swept)) == 1
        assert f".sb-ctx > .{SLOT_PATH} {{" in self._css()

    def test_the_inner_run_is_restored_to_left_to_right(self) -> None:
        rule = self._rule(f".{SLOT_PATH} > bdi")
        assert "direction: ltr" in rule
        assert "unicode-bidi: isolate" in rule

    def test_the_line_no_longer_ellipsises_as_a_whole(self) -> None:
        """The bug itself: a single ellipsis on `.sb-ctx` cut the model."""
        assert "text-overflow" not in self._rule(".sb-ctx")

    def test_a_nav_button_wears_no_button_chrome(self) -> None:
        """Settings is a `<button>` among anchors and must not look like one.

        The chrome is stripped in the shared nav rule, and `border: 0` must
        precede the `border-bottom` that draws the active underline or it
        would erase it.
        """
        rule = self._rule(".sb-nav-link")
        assert "font: inherit" in rule
        assert "background: none" in rule
        assert "cursor: pointer" in rule
        assert rule.index("border: 0") < rule.index("border-bottom:")

    def test_both_bar_controls_get_the_focus_ring(self) -> None:
        """The ring is drawn on every button in the bar, not the directory
        alone — the model slot and Settings are buttons too."""
        assert "#status-bar button:focus-visible" in self._css()


class TestTheShellHasNoMarketingChrome:
    def test_the_drawer_and_grid_ids_are_gone(self) -> None:
        assert not _REMOVED_SHELL_IDS & _ids(app_module.app.layout)

    def test_the_shell_mounts_the_status_bar(self) -> None:
        assert "status-bar" in _ids(app_module.app.layout)

    def test_the_page_no_longer_carries_a_footer(self) -> None:
        """`render_page` used to wrap every screen in the marketing footer."""
        content, _, _ = app_module.render_page(default_session(), {}, 0, None, None)
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
    session = default_session()
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
        context, *_ = on_status_bar(_session(working_dir=str(tmp_path)), {})
        text = _text(context)
        assert str(tmp_path) in text
        assert "round v0" in text
        assert "anthropic" in text
        assert "claude-sonnet-4-6" in text

    def test_every_field_has_an_explicit_empty_state(self) -> None:
        """A missing value renders a placeholder, never a blank gap.

        Two placeholders, not four: the directory and the round each have their
        own em dash, while the provider and model collapse into the single
        ``Not connected`` that replaces them. Two dashes there would say "we do
        not know which model", when what is true is "there is no connection".
        """
        context, *_ = on_status_bar({}, {})
        text = _text(context)
        assert text.count(STATUS_EMPTY) == 2
        assert NOT_CONNECTED in text

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

        before, *_ = on_status_bar(_session(working_dir=str(first)), {})
        after, *_ = on_status_bar(_session(working_dir=str(second)), {})

        assert str(first) in _text(before)
        assert str(first) not in _text(after)
        assert str(second) in _text(after)

    def test_it_follows_the_round(self, tmp_path: pathlib.Path) -> None:
        session = _session(working_dir=str(tmp_path), phase_version=3)
        context, *_ = on_status_bar(session, {})
        assert "round v3" in _text(context)

    def test_the_directory_falls_back_to_the_remembered_prefs(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A fresh browser session has prefs but not yet a loaded session.

        The directory legitimately comes from the pref: it is re-checked
        against disk right here, so a path that survives is a real one. The
        provider and model have no equivalent check — see the test below.
        """
        prefs = {
            "working_dir": str(tmp_path),
            "provider": "openai",
            "model": "gpt-5-mini",
        }
        context, *_ = on_status_bar({}, prefs)
        assert str(tmp_path) in _text(context)

    def test_a_remembered_model_is_not_reported_as_a_connection(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The bug this bar existed to prevent, in its second form.

        Restart Spec4 with a project and credentials remembered in
        localStorage: the root router opens the project without passing
        /setup, so the session has no ``llm_config`` — and the bar used to
        print the previous session's provider and model anyway, because
        ``default_provider_model`` falls back to the prefs. The app looked
        ready; the first agent click died inside LiteLLM.

        Saved prefs are what /setup prefills from. They are not a connection.
        """
        prefs = {
            "working_dir": str(tmp_path),
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "api_key": "sk-ant-xxx",
        }
        context, *_ = on_status_bar({}, prefs)
        text = _text(context)
        assert NOT_CONNECTED in text
        assert "anthropic" not in text
        assert "claude-sonnet-4-6" not in text
        # The directory is still reported: it was re-checked against disk.
        assert str(tmp_path) in text

    def test_a_session_level_model_is_not_a_connection_either(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Mid-wizard state: a model chosen, the connection not yet built.

        ``model`` and ``provider`` are fields /setup fills in as it walks; the
        ``llm_config`` is what a turn needs, and it is written last.
        """
        session = {
            "working_dir": str(tmp_path),
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "llm_config": None,
        }
        text = _text(on_status_bar(session, {})[0])
        assert NOT_CONNECTED in text
        assert "claude-sonnet-4-6" not in text

    def test_a_real_connection_is_reported_normally(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The guard must not swallow the fields it is guarding."""
        context, *_ = on_status_bar(_session(working_dir=str(tmp_path)), {})
        text = _text(context)
        assert NOT_CONNECTED not in text
        assert "anthropic" in text
        assert "claude-sonnet-4-6" in text

    def test_it_agrees_with_what_a_turn_would_do(self, tmp_path: pathlib.Path) -> None:
        """The bar and the dispatch answer one question, through one route.

        A bar saying "connected" while `get_agent_gen` refuses to start is
        the whole failure this closes, so the two are pinned together rather
        than asserted separately.
        """
        cases = [
            {},
            {"llm_config": None},
            {"provider": "anthropic", "model": "m", "llm_config": None},
            {"llm_config": {"api_key": "k"}},
            {"llm_config": {"model": "m", "api_key": "k"}},
        ]
        for extra in cases:
            session = {"working_dir": str(tmp_path), **extra}
            says_connected = NOT_CONNECTED not in _text(on_status_bar(session, {})[0])
            assert says_connected == llm_selection.default_is_connected(session), extra

    def test_the_unfilled_bar_does_not_imply_a_connection(self) -> None:
        """`app.layout` draws the bar before any callback has run.

        It has been told nothing, so the one thing it must not do is suggest a
        working model.
        """
        assert NOT_CONNECTED in _text(status_bar())

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
        context, *_ = on_status_bar(session, {})
        text = _text(context)
        assert "claude-sonnet-4-6" in text
        assert "gpt-5" not in text

    def test_it_marks_project_as_current_by_default(self) -> None:
        _, project, artifacts, settings = on_status_bar(
            _session(phase="agent_select"), {}
        )
        assert "active" in project
        assert "active" not in artifacts
        assert "active" not in settings

    def test_the_setup_wizard_marks_settings(self) -> None:
        _, project, artifacts, settings = on_status_bar(_session(phase="setup"), {})
        assert "active" not in project
        assert "active" not in artifacts
        assert "active" in settings

    def test_the_artifact_view_marks_artifacts(self) -> None:
        _, project, artifacts, settings = on_status_bar(_session(phase="artifacts"), {})
        assert "active" not in project
        assert "active" in artifacts
        assert "active" not in settings

    def test_exactly_one_item_is_ever_marked(self) -> None:
        """One accent, one active state: two marked items would be two.

        Every phase the app can sit in is walked, so a phase added later
        without a nav rule fails here rather than lighting up nothing.
        """
        for phase in [PHASE_ROOT, *PATH_TO_PHASE.values()]:
            marked = [
                cls
                for cls in on_status_bar(_session(phase=phase), {})[1:]
                if "active" in cls
            ]
            assert len(marked) == 1, phase

    def test_it_survives_empty_stores(self) -> None:
        """The very first render, before either store has been written."""
        assert on_status_bar(None, None) is not None


class TestTheModelSlotCarriesTheEffort:
    """Instruction 9: `<model> · <effort>`, without giving up the slot rules."""

    def _slot(self, context: Any) -> Any:
        return next(
            node
            for node in context
            if SLOT_MODEL in set((getattr(node, "className", "") or "").split())
        )

    def test_a_real_level_is_appended(self) -> None:
        slot = self._slot(
            status_context("/a/b", 1, "anthropic", "claude-sonnet-5", True, "high")
        )
        assert slot.children == "claude-sonnet-5 · high"

    def test_the_default_leaves_the_model_alone(self) -> None:
        for effort in ("default", llm_selection.DEFAULT_EFFORT):
            slot = self._slot(status_context("/a/b", 1, "anthropic", "m", True, effort))
            assert slot.children == "m"

    def test_the_effort_is_optional_at_the_call_site(self) -> None:
        """The unfilled bar and the tests that predate the field still call
        this with five arguments."""
        assert (
            self._slot(status_context("/a/b", 1, "anthropic", "m", True)).children
            == "m"
        )

    def test_the_suffixed_slot_still_refuses_to_truncate(self) -> None:
        """Phase 1's rule survives a longer string: the model slot is pinned
        and only the path may shrink (D-LR10)."""
        classes = set(
            self._slot(
                status_context("/a/b", 1, "anthropic", "m", True, "high")
            ).className.split()
        )
        assert SLOT_CLASS in classes
        assert SLOT_PATH not in classes

    def test_the_line_it_sits_on_is_still_monospace(self) -> None:
        context = next(
            node
            for node in _flatten(status_bar())
            if getattr(node, "id", None) == "status-bar-context"
        )
        assert "mono" in set(context.className.split())

    def test_an_empty_model_is_still_the_em_dash(self) -> None:
        """A connected session with no model name renders the empty state, not
        a bare separator."""
        slot = self._slot(status_context("/a/b", 1, "anthropic", None, True, "high"))
        assert slot.children == STATUS_EMPTY


class _Ctx:
    def __init__(self, triggered_id: str | None) -> None:
        self.triggered_id = triggered_id


class TestTheBarOpensSetup:
    """The bar's second control: the model slot, and the Settings item with it.

    The directory field is the route to the picker; the model — or the
    ``Not connected`` phrase standing in for it — is the route to the wizard.
    Both are the same kind of thing: the fact itself, drawn without chrome,
    pressable, and with the same contract — pressing *opens* and commits
    nothing. The wizard shows its Provider step over the live connection,
    which keeps running until Connect fetches a fresh model list; that is
    the one place the old connection ends, and it is pinned here too.
    """

    _ID = "btn-status-bar-model"

    def _button(self, context: Any) -> Any:
        """The control, from a context line (a list of top-level fields)."""
        return next(node for node in context if getattr(node, "id", None) == self._ID)

    def test_the_model_is_a_button(self, tmp_path: pathlib.Path) -> None:
        session = {
            **default_session(),
            "working_dir": str(tmp_path),
            "llm_config": {"model": "claude-sonnet-5", "api_key": "k"},
            "model": "claude-sonnet-5",
            "provider": "anthropic",
        }
        context, *_ = on_status_bar(session, {})
        button = self._button(context)
        # It still reads as the same field it was — the model, not a label.
        assert button.children == "claude-sonnet-5"
        assert SLOT_MODEL in button.className.split()

    def test_not_connected_is_the_same_button(self) -> None:
        """No connection is *more* reason to open setup, so no empty state
        stays plain text: one id, whichever phrase it carries."""
        context, *_ = on_status_bar({**default_session()}, {})
        button = self._button(context)
        assert button.children == NOT_CONNECTED
        assert SLOT_CONNECTION in button.className.split()

    def test_the_unfilled_bar_already_carries_it(self) -> None:
        """Present from the first render, so it is in `app.layout` itself."""
        assert self._ID in _ids(status_bar())

    def test_it_is_dressed_as_the_directory_is(self) -> None:
        """D-LR2 and the bar's own rule: no chrome, no colour, the same font."""
        button = self._button(status_context("/a/b", 0, "anthropic", "m", True))
        assert type(button).__name__ == "Button"
        assert "sb-dir" in button.className.split()
        assert getattr(button, "style", None) is None
        assert button.title

    def _press(self, monkeypatch: Any, which: str, session: dict[str, Any]) -> Any:
        from spec4 import callbacks as cb

        monkeypatch.setattr(cb, "ctx", _Ctx(which))
        model_n = 1 if which == self._ID else 0
        settings_n = 1 if which == "status-bar-nav-settings" else 0
        return cb.on_status_bar_setup(model_n, settings_n, session)

    def _connected(self, tmp_path: pathlib.Path) -> dict[str, Any]:
        return {
            **default_session(),
            "working_dir": str(tmp_path),
            "available_models": ["claude-sonnet-5"],
            "model": "claude-sonnet-5",
            "llm_config": {"model": "claude-sonnet-5", "api_key": "k"},
            "setup_error": "old",
            "agent_select_error": "old",
        }

    def test_pressing_the_model_opens_the_wizard_at_provider(
        self, monkeypatch: Any, tmp_path: pathlib.Path
    ) -> None:
        new_session, pathname = self._press(
            monkeypatch, self._ID, self._connected(tmp_path)
        )
        assert pathname == "/setup"
        assert new_session["phase"] == "setup"
        # Step 1 is what `setup_layout` shows when there is no model list.
        assert new_session["available_models"] is None
        assert new_session["setup_error"] is None
        assert new_session["agent_select_error"] is None

    def test_pressing_it_commits_nothing(
        self, monkeypatch: Any, tmp_path: pathlib.Path
    ) -> None:
        """The directory's contract, kept: the connection is not dropped.

        Backing out through Project must leave a session that can still run
        a turn, so the model and its config survive the click untouched. Only
        Connect, on the Provider step, replaces them.
        """
        before = self._connected(tmp_path)
        new_session, _ = self._press(monkeypatch, self._ID, before)
        assert new_session["model"] == before["model"]
        assert new_session["llm_config"] == before["llm_config"]
        assert new_session["working_dir"] == str(tmp_path)
        assert llm_selection.default_is_connected(new_session)

    def test_the_bar_still_names_the_model_on_the_provider_step(
        self, monkeypatch: Any, tmp_path: pathlib.Path
    ) -> None:
        """What the developer sees after the click: the wizard's first step
        under a bar that still says which model the next turn would run on."""
        new_session, _ = self._press(monkeypatch, self._ID, self._connected(tmp_path))
        context, *_ = on_status_bar(new_session, {})
        assert self._button(context).children == "claude-sonnet-5"
        assert NOT_CONNECTED not in _text(context)

    def test_pressing_settings_does_exactly_the_same(
        self, monkeypatch: Any, tmp_path: pathlib.Path
    ) -> None:
        via_model = self._press(monkeypatch, self._ID, self._connected(tmp_path))
        via_settings = self._press(
            monkeypatch, "status-bar-nav-settings", self._connected(tmp_path)
        )
        assert via_model == via_settings

    def test_settings_drops_an_abandoned_detour(
        self, monkeypatch: Any, tmp_path: pathlib.Path
    ) -> None:
        """An agent click diverted to the wizard and walked away from is not
        carried into the wizard Settings opens."""
        detoured = {**self._connected(tmp_path), "_pending_agent": "brainstormer"}
        new_session, pathname = self._press(
            monkeypatch, "status-bar-nav-settings", detoured
        )
        assert pathname == "/setup"
        assert new_session["phase"] == "setup"
        assert new_session["_pending_agent"] is None

    def test_it_is_the_back_buttons_write_plus_a_route(
        self, monkeypatch: Any, tmp_path: pathlib.Path
    ) -> None:
        """One definition of "show Provider": the Model step's Back button and
        the bar agree on which fields that clears."""
        from spec4 import callbacks as cb

        via_bar, _ = self._press(monkeypatch, self._ID, self._connected(tmp_path))
        via_back = cb.on_setup_back_provider(1, self._connected(tmp_path))
        assert via_bar == {**via_back, "phase": "setup", "agent_select_error": None}

    def test_connect_is_where_the_old_connection_ends(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Advancing to Model selection replaces the connection — not before.

        The Provider step is shown over a live `model`, and `setup_layout`
        would skip straight to Search if Connect left it set; the list just
        fetched may also be another provider's. So a *successful* Connect
        clears the model and its config, and a failed one clears nothing —
        a mistyped key must not cost a working connection.
        """
        from unittest.mock import patch

        from spec4 import callbacks as cb

        opened = {**self._connected(tmp_path), "available_models": None}
        with patch(
            "spec4.callbacks._setup.providers.list_models", return_value=(["gpt-5"], "")
        ):
            advanced, _ = cb.on_setup_connect(1, "OpenAI", "sk-new", False, opened, {})
        assert advanced["available_models"] == ["gpt-5"]
        assert advanced["model"] is None
        assert advanced["llm_config"] is None

        with patch(
            "spec4.callbacks._setup.providers.list_models", return_value=([], "nope")
        ):
            failed, _ = cb.on_setup_connect(1, "OpenAI", "sk-bad", False, opened, {})
        assert failed["model"] == opened["model"]
        assert failed["llm_config"] == opened["llm_config"]
        assert failed["setup_error"]

    def test_no_click_is_a_no_op(self, monkeypatch: Any) -> None:
        from dash import no_update

        assert self._press(monkeypatch, None, default_session()) == (
            no_update,
            no_update,
        )

    def test_it_survives_an_empty_store(self, monkeypatch: Any) -> None:
        new_session, pathname = self._press(monkeypatch, self._ID, None)  # type: ignore[arg-type]
        assert new_session["phase"] == "setup"
        assert pathname == "/setup"
