"""Every callback's Inputs and States must render together, in every phase.

Dash refuses to dispatch a callback when any component it references is missing
from the current layout. The browser logs "A nonexistent object was used in an
`Input` of a Dash callback" and the click silently does nothing —
``suppress_callback_exceptions=True`` silences the definition-time check, not
this one. Calling a callback function directly in a test cannot see the problem
at all, because the Python is fine; only the rendered tree shows it.

So this walks the real callback registry against every layout the app can put on
screen and fails any callback that is *half* rendered: some of the page ids it
needs present, the rest not. It caught one real bug — the model gate's "Pick a
model" button and the control-row model chip shared a callback, but the chip is
suppressed while the gate is open, so the button threw and did nothing.

A callback that touches none of a layout's page ids is simply not that layout's
concern and is skipped; one whose ids all live in the app shell (stores, the
URL, the nav) is always satisfied.
"""

from __future__ import annotations

import pathlib
from typing import Any
from unittest.mock import patch

import pytest
from dash import html
from dash._callback import GLOBAL_CALLBACK_MAP

import spec4.app as app_module
from spec4 import providers
from spec4.app_constants import AGENT_KEYS, STATE_VISION_COMPLETE
from spec4.callbacks import on_gate_chip, on_gate_connect, on_gate_pick
from spec4.layouts import _AGENT_ROWS, _agent_select_layout
from spec4.layouts._status_bar import _status_context
from spec4.layouts.designer import (
    _step1_content,
    _step2_content,
    _step3_content,
    _step4_content,
    _step5_content,
    _step6_content,
    _step7_content,
)
from spec4.session import _default_session, _reset_for_new_project

# The round tree's ids, added to the project view this round. Listed rather
# than derived so that renaming one of them has to be a deliberate edit here.
_ROUND_TREE_IDS = {"round-tree", "round-tree-head", "round-tree-list"}

# The agent table's ids, which replaced the agent cards on the project view.
# Listed for the same reason as the tree's, and one per pipeline key so a row
# that stops rendering is a failure here rather than a quietly shorter table.
_AGENT_ROW_IDS = {
    "agent-rows",
    "agent-rows-body",
    "agent-row-code_scanner",
    "agent-row-brainstormer",
    "agent-row-agentifier",
    "agent-row-designer",
    "agent-row-stack_advisor",
    "agent-row-phaser",
    "agent-row-deployer",
}

# The round-cost strip's ids. Listed, like the tree's and the rows', so that
# renaming one has to be a deliberate edit here — `on_round_cost` writes into
# the three line ids and would silently stop filling a renamed one.
_ROUND_COST_IDS = {
    "round-cost",
    "round-cost-line",
    "round-cost-unpriced",
    "round-cost-note",
}

# The only plain id the retired agent cards carried. The cards themselves, the
# per-agent rows inside them and their action buttons had no string ids — the
# buttons used, and still use, the `agent-pill` pattern id — so this is the
# whole of what had to survive the swap, and `_PROJECT_VIEW_IDS` below pins the
# rest of the view to what replaced them.
_AGENT_CARD_SURVIVING_IDS = {"btn-agent-change-provider"}

# Everything the project view mounts, exactly. An id retired with the cards
# that came back, or a new one added without a decision, fails here.
_PROJECT_VIEW_IDS = (
    _ROUND_TREE_IDS
    | {"round-tree-legend"}
    | _AGENT_ROW_IDS
    | _ROUND_COST_IDS
    | _AGENT_CARD_SURVIVING_IDS
)

# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


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


def _shell_ids() -> set[str]:
    """Ids mounted once in the app shell, outside any page's content.

    Derived from ``app.layout`` rather than hand-listed, so a new store added to
    the shell does not quietly become a false positive here.

    The status bar's context line is the one part of the shell whose ids are not
    all in that initial render: ``app.layout`` draws the bar's *empty* state,
    and ``on_status_bar`` — itself a shell callback, mounted for the app's whole
    life — refills it on every store change. ``btn-status-bar-dir`` only exists
    once there is a directory to reopen at, so the filled context is rendered
    here too. It is still derived, not hand-listed: a second control added to
    that line is picked up without editing this function.
    """
    filled = html.Span(
        _status_context("/a/project", 0, "anthropic", "m", True)
    )
    return _ids(app_module.app.layout) | _ids(filled)


def _page_ids(*components: Any) -> set[str]:
    """Page-content ids for one screen, with shell ids removed."""
    found: set[str] = set()
    for component in components:
        found |= _ids(component)
    return found - _shell_ids()


def _session(**extra: Any) -> dict[str, Any]:
    session = _default_session()
    session.update(
        {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "api_key": "k",
            "llm_config": {"model": "claude-sonnet-4-6", "api_key": "k"},
            "project_mode": "new",
        }
    )
    session.update(extra)
    return session


def _answered(session: dict[str, Any], *agents: str) -> dict[str, Any]:
    """A session whose model gate has been answered for the given agents."""
    return {
        **session,
        "agent_llm_asked": {
            **(session.get("agent_llm_asked") or {}),
            **{a: True for a in agents},
        },
    }


def _render(session: dict[str, Any]) -> Any:
    """The page content `render_page` produces for a session."""
    content, _, _ = app_module.render_page(session, {}, 0, None, None)
    return content


# ---------------------------------------------------------------------------
# The screens
# ---------------------------------------------------------------------------

_CHAT_AGENTS = (
    "code_scanner",
    "brainstormer",
    "agentifier",
    "stack_advisor",
    "phaser",
    "deployer",
)


def _phase_screens(tmp_path: pathlib.Path) -> list[tuple[str, set[str]]]:
    """Every distinct page the app renders, as (label, page ids)."""
    wd = str(tmp_path)
    base = _session(working_dir=wd)
    screens: list[tuple[str, set[str]]] = []

    # The directory browser. There is no landing screen to walk: the root
    # resolves to this or to the project view, and nothing else renders.
    screens.append(
        ("working_dir", _page_ids(_render(_session(phase="working_dir"))))
    )
    screens.append(
        (
            "working_dir: unopenable remembered directory",
            _page_ids(
                _render(
                    _session(
                        phase="working_dir",
                        dir_error="Could not open /gone. Select a project directory.",
                    )
                )
            ),
        )
    )

    # The setup wizard's three screens, keyed the way `_setup_layout` branches.
    setup = {**base, "phase": "setup"}
    screens.append(
        (
            "setup: provider",
            _page_ids(_render({**setup, "available_models": None, "model": None})),
        )
    )
    screens.append(
        (
            "setup: model",
            _page_ids(
                _render({**setup, "available_models": ["a", "b"], "model": None})
            ),
        )
    )
    screens.append(
        (
            "setup: web search",
            _page_ids(_render({**setup, "available_models": ["a", "b"]})),
        )
    )

    # Agent select, and the project-mode question that precedes it.
    screens.append(
        ("agent_select", _page_ids(_render({**base, "phase": "agent_select"})))
    )
    (tmp_path / "existing.py").write_text("print('hi')\n")
    screens.append(
        (
            "project_mode",
            _page_ids(
                _agent_select_layout(
                    {**base, "phase": "agent_select", "project_mode": None}
                )
            ),
        )
    )

    # Chat, per agent: the gate, the answered opening turn, a live stream, and
    # a finished turn (which is what puts the terminal-state buttons on screen).
    for agent in _CHAT_AGENTS:
        chat = {**base, "phase": "chat", "active_agent": agent}
        screens.append((f"chat {agent}: gate", _page_ids(_render(chat))))
        answered = _answered(chat, agent)
        screens.append((f"chat {agent}: opening", _page_ids(_render(answered))))
        streaming = {
            **answered,
            "messages": [{"role": "assistant", "content": "…"}],
            "_stream_id": "live",
            "_initial_turn_done": True,
        }
        screens.append((f"chat {agent}: streaming", _page_ids(_render(streaming))))
        done = {
            **answered,
            "messages": [{"role": "assistant", "content": "done"}],
            "_initial_turn_done": True,
            "vision_statement": {"app_name": "x"},
            "brainstormer_state": STATE_VISION_COMPLETE,
            "code_review": {"summary": "x"},
            "code_scanner_state": "review_complete",
            "stack_statement": {"stack": []},
            "stack_advisor_state": "stack_complete",
            "phases": [{"name": "p"}],
            "phaser_state": "phases_complete",
            "agentifier_state": "agentifier_complete",
            "deployer_state": "deployer_complete",
            "ai_features": {"ai_features": []},
        }
        screens.append((f"chat {agent}: complete", _page_ids(_render(done))))

    # The model gate's expanded states: these put the shared provider/key/model
    # fields on screen, and are where the paired-callback bug lived.
    gate_base = {**base, "phase": "chat", "active_agent": "code_scanner"}
    picking = on_gate_pick(1, gate_base)
    screens.append(("gate: picking provider+key", _page_ids(_render(picking))))
    with patch.object(providers, "list_models", return_value=(["gpt-5"], "")):
        connected, _ = on_gate_connect(1, "OpenAI", "sk-x", picking, {})
    screens.append(("gate: picking model", _page_ids(_render(connected))))
    with patch.object(providers, "list_models", return_value=([], "401")):
        failed, _ = on_gate_connect(1, "OpenAI", "sk-bad", picking, {})
    screens.append(("gate: connect failed", _page_ids(_render(failed))))

    # A carried-forward override with the answer cleared — the three-button
    # shape a developer meets after "Start New Project".
    carried = _reset_for_new_project(
        {
            **gate_base,
            "agent_llm": {
                "code_scanner": {
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "available_models": ["gpt-5-mini"],
                    "llm_config": {"model": "gpt-5-mini", "api_key": "sk"},
                    "image_support": True,
                    "tool_support": True,
                }
            },
        }
    )
    carried.update(
        {"phase": "chat", "active_agent": "code_scanner", "working_dir": wd}
    )
    screens.append(("gate: carried forward", _page_ids(_render(carried))))
    reopened = on_gate_chip(1, _answered(carried, "code_scanner"))
    screens.append(("gate: reopened via chip", _page_ids(_render(reopened))))

    # The two chat panels that render conditionally alongside the transcript.
    retry = _answered(
        {
            **gate_base,
            "_stream_error": True,
            "_initial_turn_done": True,
            "messages": [{"role": "assistant", "content": "boom"}],
        },
        "code_scanner",
    )
    screens.append(("chat: retry panel", _page_ids(_render(retry))))
    breadth = _answered(
        {
            **base,
            "phase": "chat",
            "active_agent": "agentifier",
            "_initial_turn_done": True,
            "agentifier_breadth_groups": [{"name": "g", "description": "d"}],
            "agentifier_breadth_intro": "pick some",
        },
        "agentifier",
    )
    screens.append(("chat: breadth panel", _page_ids(_render(breadth))))

    # Designer: its gate, then the wizard, then each wizard step's content —
    # the steps are injected by `render_designer_step`, so they are rendered
    # here alongside the layout that hosts them.
    design = {**base, "phase": "designer"}
    screens.append(("designer: gate", _page_ids(_render(design))))
    answered_design = _answered(design, "designer")
    shell = _render(answered_design)
    screens.append(("designer: wizard", _page_ids(shell)))
    # The step builders are called directly rather than through
    # `render_designer_step`, which reads a callback context it cannot have here.
    store = {
        "step": 6,
        "preference_text": "",
        "screenshots": [{"data": "data:image/png;base64,x", "annotation": ""}],
        "refine_images": [{"filename": "b.png", "data": "data:image/png;base64,x"}],
        "mock_html": "<html></html>",
        "finalized": False,
        "_has_existing_ui": True,
        "_is_revision": False,
    }
    buffer = {"tokens": 0, "progress": 0, "error": None}
    steps: list[tuple[str, Any]] = [
        ("1", _step1_content()),
        ("2", _step2_content(True, False)),
        ("2 (no existing ui)", _step2_content(False, False)),
        ("2 (revision)", _step2_content(True, True)),
        ("3", _step3_content()),
        ("4", _step4_content(store, True)),
        ("4 (no image support)", _step4_content(store, False)),
        ("5", _step5_content(buffer)),
        ("5 (error)", _step5_content({**buffer, "error": "boom"})),
        ("6", _step6_content(store)),
        ("6 (finalized)", _step6_content({**store, "finalized": True})),
        ("6 (stale)", _step6_content({**store, "_stale_inputs": ["vision.json"]})),
        ("7", _step7_content(store, True)),
        ("7 (no image support)", _step7_content(store, False)),
    ]
    for name, content in steps:
        screens.append((f"designer: step {name}", _page_ids(shell, content)))

    return screens


# ---------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------


def _plain_ids(deps: Any) -> set[str]:
    """String component ids in a dependency list.

    Pattern-matching ids arrive here as serialised JSON objects
    (``{"index":["ALL"],"type":"…"}``). They match zero or more components by
    design and cannot be half-present in this sense, so they are excluded.
    """
    return {
        dep["id"]
        for dep in deps
        if isinstance(dep.get("id"), str) and not dep["id"].startswith("{")
    }


def _callback_refs() -> list[tuple[str, set[str], set[str]]]:
    """(name, Input ids, all referenced ids) for every registered callback.

    The distinction matters: a callback can only fire when one of its *Inputs*
    changes, and Dash checks co-presence only then. A callback that merely holds
    a State on something rendered here — every Designer callback holds
    ``designer-session-store`` — is not this screen's concern.
    """
    refs: list[tuple[str, set[str], set[str]]] = []
    for name, spec in GLOBAL_CALLBACK_MAP.items():
        inputs = _plain_ids(spec["inputs"])
        outs = spec["output"] if isinstance(spec["output"], list) else [spec["output"]]
        # Outputs count too: a firing callback needs somewhere to put every one
        # of its results, and a missing target rejects the whole response — the
        # same way a missing Input does.
        output_ids = {
            o.component_id
            for o in outs
            if isinstance(getattr(o, "component_id", None), str)
            and not o.component_id.startswith("{")
        }
        every = inputs | _plain_ids(spec["state"]) | output_ids
        if inputs:
            refs.append((name, inputs, every))
    return refs


class TestCallbackInputsAreCoPresent:
    def test_no_callback_is_half_rendered_in_any_phase(
        self, tmp_path: pathlib.Path
    ) -> None:
        shell = _shell_ids()
        callbacks = _callback_refs()
        problems: list[str] = []

        for label, present in _phase_screens(tmp_path):
            available = present | shell
            for name, inputs, every in callbacks:
                # Can this callback fire on this screen at all?
                if not inputs & present:
                    continue
                if not every <= available:
                    problems.append(
                        f"{label}: {name} can fire via {sorted(inputs & present)} "
                        f"but is missing {sorted(every - available)}"
                    )

        assert not problems, "half-rendered callbacks:\n" + "\n".join(problems)

    def test_the_screen_list_actually_renders_things(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Guards the guard: an empty screen set would make it vacuous."""
        screens = _phase_screens(tmp_path)
        assert len(screens) >= 30
        assert all(present for _, present in screens), [
            label for label, present in screens if not present
        ]

    def test_every_page_level_callback_is_reached(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The screen list must be able to fire every page-level callback.

        Without this, adding a screen-specific callback and forgetting to add
        its screen here would leave the guard quietly blind to it. Callbacks
        whose Inputs are all app-shell components (the URL, the poll interval,
        the stores) are exempt: they are mounted for the app's whole life and so
        can never be half-rendered.
        """
        shell = _shell_ids()
        screens = _phase_screens(tmp_path)
        reached = {
            name
            for _, present in screens
            for name, inputs, _ in _callback_refs()
            if inputs & present
        }
        unreached = [
            sorted(inputs)
            for name, inputs, _ in _callback_refs()
            if name not in reached and inputs - shell
        ]
        assert not unreached, (
            "these callbacks have page-level Inputs no screen here renders — "
            f"add the missing screen to _phase_screens: {unreached}"
        )

    def test_it_catches_a_split_callback(self, tmp_path: pathlib.Path) -> None:
        """The bug this exists for: two Inputs that never render together.

        `btn-agent-llm-pick` shows only while the gate is open and
        `btn-agent-llm-chip` only once it is answered, so a callback taking both
        is refused on every screen either appears on.
        """
        shell = _shell_ids()
        paired = {"btn-agent-llm-pick", "btn-agent-llm-chip"}
        caught = [
            label
            for label, present in _phase_screens(tmp_path)
            if paired & present and not paired <= present | shell
        ]
        assert caught, "the guard would not have caught the paired-callback bug"


class TestProjectViewIds:
    """The round tree's ids belong to the project view, not the shell.

    That distinction is what makes `on_round_tree` safe: it writes into
    `round-tree-head` and `round-tree-list`, which exist only while the project
    view is on screen, so its Input is the tree's own container rather than the
    session store. A session Input would ask Dash to fill those two while the
    developer is in chat, and the co-presence guard above is what would catch
    it — but only if the ids are page ids, which is asserted here.
    """

    def test_the_tree_is_page_content_not_shell(self) -> None:
        assert not _ROUND_TREE_IDS & _shell_ids()

    def test_the_project_view_renders_every_tree_id(
        self, tmp_path: pathlib.Path
    ) -> None:
        session = _session(working_dir=str(tmp_path), phase="agent_select")
        assert _ROUND_TREE_IDS <= _page_ids(_render(session))

    def test_the_project_view_keeps_its_existing_ids(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The tree was added to the view; nothing was displaced by it."""
        session = _session(working_dir=str(tmp_path), phase="agent_select")
        assert _AGENT_CARD_SURVIVING_IDS <= _page_ids(_render(session))


class TestAgentRowIds:
    """The agent table's ids belong to the project view, like the tree's.

    The rows carry no callback of their own — the action buttons keep the
    `agent-pill` pattern id, so routing is `on_agent_pill_click` unchanged —
    but the ids are asserted here anyway, at the same altitude as the tree's,
    because a row that quietly stops rendering takes a pipeline stage off the
    screen with it.
    """

    def test_the_rows_are_page_content_not_shell(self) -> None:
        assert not _AGENT_ROW_IDS & _shell_ids()

    def test_the_project_view_renders_every_row_id(
        self, tmp_path: pathlib.Path
    ) -> None:
        session = _session(working_dir=str(tmp_path), phase="agent_select")
        assert _AGENT_ROW_IDS <= _page_ids(_render(session))

    def test_there_is_one_row_id_per_pipeline_agent(self) -> None:
        assert {f"agent-row-{key}" for key in AGENT_KEYS} < _AGENT_ROW_IDS

    def test_every_action_button_carries_the_routing_id(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The retired cards' buttons and the rows' are the same components.

        `on_agent_pill_click` takes this pattern id as its Input, so a row
        whose button had been given a new id would render fine and do nothing
        when clicked — which is exactly the failure this file exists for.
        """
        session = _session(working_dir=str(tmp_path), phase="agent_select")
        found: set[str] = set()
        stack = [_render(session)]
        while stack:
            node = stack.pop()
            node_id = getattr(node, "id", None)
            if isinstance(node_id, dict) and node_id.get("type") == "agent-pill":
                found.add(node_id["agent"])
            children = getattr(node, "children", None)
            if children is None:
                continue
            if not isinstance(children, (list, tuple)):
                children = [children]
            stack.extend(children)
        assert found == set(AGENT_KEYS)

    def test_the_project_view_mounts_exactly_these_ids(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The retired agent-card ids are gone and nothing new crept in."""
        session = _session(working_dir=str(tmp_path), phase="agent_select")
        assert _page_ids(_render(session)) == _PROJECT_VIEW_IDS

    def test_the_tree_callback_is_reached_by_the_screen_list(
        self, tmp_path: pathlib.Path
    ) -> None:
        """`_phase_screens` must actually put the tree on screen.

        The guard above skips a callback whose page Inputs are all absent, so
        a screen list that never renders the project view would let a
        half-rendered tree callback through unnoticed.
        """
        reached = any(
            "round-tree" in present for _, present in _phase_screens(tmp_path)
        )
        assert reached


class TestRoundCostIds:
    """The round-cost strip's ids belong to the project view, like the tree's.

    `on_round_cost` writes into three line ids that exist only while the
    project view is on screen, so — exactly as for the tree — its Input is the
    strip's own container rather than the session store. A session Input would
    ask Dash to fill those three while the developer is in chat, and the
    co-presence guard above catches that only if these are page ids, which is
    what is asserted here.
    """

    def test_the_strip_is_page_content_not_shell(self) -> None:
        assert not _ROUND_COST_IDS & _shell_ids()

    def test_the_project_view_renders_every_cost_id(
        self, tmp_path: pathlib.Path
    ) -> None:
        session = _session(working_dir=str(tmp_path), phase="agent_select")
        assert _ROUND_COST_IDS <= _page_ids(_render(session))

    def test_the_strip_does_not_reuse_the_chat_cards_id(self) -> None:
        """The chat frame's cost card keeps `cost-summary-card` to itself.

        `tests/test_cost_summary.py` asserts that card's position between the
        transcript and the token count, and a second component answering to
        the same id would make that assertion ambiguous the first time a
        screen rendered both.
        """
        assert "cost-summary-card" not in _ROUND_COST_IDS
        assert "cost-summary-card" not in _PROJECT_VIEW_IDS

    def test_the_cost_callback_is_reached_by_the_screen_list(
        self, tmp_path: pathlib.Path
    ) -> None:
        reached = any(
            "round-cost" in present for _, present in _phase_screens(tmp_path)
        )
        assert reached


class TestShellIds:
    def test_the_shell_is_not_empty(self) -> None:
        assert {"session", "prefs", "url", "page-content"} <= _shell_ids()

    def test_the_status_bar_is_part_of_the_shell(self) -> None:
        """The bar is mounted once in ``app.layout``, not per screen.

        That is what makes its callback exempt from the co-presence guard
        above: shell ids are present on every screen, so a callback whose
        Inputs and Outputs all live here can never be half-rendered.
        """
        assert {
            "status-bar",
            "status-bar-context",
            "status-bar-version",
            "status-bar-nav-project",
            "status-bar-nav-settings",
            "status-bar-nav-docs",
        } <= _shell_ids()

    def test_the_directory_button_is_part_of_the_shell(self) -> None:
        """The bar's working-directory control counts as a shell id.

        It rides in the context line, which is refilled by ``on_status_bar``
        rather than drawn once, so it is absent from the empty bar and present
        the moment a project is open. Treating it as page content would make
        ``on_status_bar_dir`` look half-rendered on every screen; treating it
        as shell is what it actually is — mounted for the app's whole life,
        alongside the two stores its callback writes.
        """
        assert "btn-status-bar-dir" in _shell_ids()
        assert "btn-status-bar-dir" not in _ids(app_module.app.layout)

    def test_the_directory_button_is_never_page_content(
        self, tmp_path: pathlib.Path
    ) -> None:
        """No screen may mount a second control answering to that id.

        ``on_status_bar_dir`` writes the session store and the URL, so a page
        that rendered its own ``btn-status-bar-dir`` would give one id two
        meanings and make which one fires depend on render order.
        """
        offenders = [
            label
            for label, present in _phase_screens(tmp_path)
            if "btn-status-bar-dir" in present
        ]
        assert not offenders

    def test_the_directory_callback_is_satisfied_on_every_screen(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The guard above skips shell-only callbacks; this pins that it is one.

        Every id ``on_status_bar_dir`` touches — its button, the session store
        and the URL — lives in the shell, so it can fire from any screen the
        app can draw.
        """
        shell = _shell_ids()
        # Found by its Input rather than by name: the registry is keyed by a
        # callback's outputs, so the function's name is not in it.
        matching = [
            every
            for _, inputs, every in _callback_refs()
            if "btn-status-bar-dir" in inputs
        ]
        assert len(matching) == 1, "exactly one callback owns the bar's directory"
        assert {"btn-status-bar-dir", "session", "url"} <= matching[0]
        assert matching[0] <= shell

    def test_the_removed_shell_ids_are_gone(self) -> None:
        """The external-link drawer and the grid background left the shell.

        Their ids are listed here rather than merely deleted, because a
        callback still holding one as an Input fails at fire time, not import
        time — a broken screen instead of an error. The contract says they are
        absent, so a component quietly reintroducing one fails here first.
        """
        removed = {
            "nav-drawer",
            "nav-overlay",
            "nav-burger",
            "nav-close-btn",
            "blueprint-grid",
        }
        assert not removed & _shell_ids()

    def test_no_callback_still_references_a_removed_id(self) -> None:
        """The drawer's callback had to go in the same commit as the drawer."""
        removed = {"nav-drawer", "nav-overlay", "nav-burger", "nav-close-btn"}
        offenders = [
            name for name, _, every in _callback_refs() if every & removed
        ]
        assert not offenders

    def test_page_ids_exclude_the_shell(self) -> None:
        session = _session(phase="working_dir")
        assert "session" not in _page_ids(_render(session))


@pytest.mark.parametrize("phase", ["working_dir", "setup", "agent_select"])
def test_every_phase_renders(phase: str) -> None:
    assert _render(_session(phase=phase)) is not None


def test_agent_keys_is_single_pipeline_order() -> None:
    """``AGENT_KEYS`` is the one definition of the seven-agent pipeline order.

    The screens walked above are built from the agent tables, so a second list
    that drifts out of order would render a page this guard still passes. The
    order is asserted here, at the same altitude as the id contract, so the
    shell rework has to keep deriving every agent table from ``AGENT_KEYS``
    rather than restating it.
    """
    assert len(AGENT_KEYS) == 7
    assert tuple(key for key, *_ in _AGENT_ROWS) == AGENT_KEYS


class TestStep2RevisionRegression:
    """A revision round must still be able to dispatch "Create new design".

    `on_designer_step2_choice` takes both step-2 buttons as Inputs. The revision
    branch shows "Carry design forward" in the slot the modify button normally
    occupies, so the modify button has to stay mounted (hidden) or Dash refuses
    to dispatch the callback and the visible "Create new design" button does
    nothing. Found by the co-presence guard above.
    """

    @pytest.mark.parametrize(
        ("has_existing_ui", "is_revision"),
        [(True, False), (False, False), (True, True), (False, True)],
    )
    def test_both_step2_inputs_are_always_mounted(
        self, has_existing_ui: bool, is_revision: bool
    ) -> None:
        ids = _ids(_step2_content(has_existing_ui, is_revision))
        assert {"btn-designer-modify-existing", "btn-designer-create-new"} <= ids

    def test_the_revision_round_still_offers_carry_forward(self) -> None:
        ids = _ids(_step2_content(True, True))
        assert "btn-designer-carry-forward" in ids
