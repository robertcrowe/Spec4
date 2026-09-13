"""The app's Dash callbacks -- and, by importing them, their registration.

Cleanup Phase 4g split this module four ways along the banner comments it
already carried, and 4g2 split the largest of those four again. Importing
``spec4.callbacks`` still registers every one of them, because the six imports
below are what run the ``@callback`` decorators; that is the whole contract
``src/spec4/app.py`` relies on.

* :mod:`spec4.callbacks._shared` -- the helpers more than one of the rest needs.
* :mod:`spec4.callbacks._setup` -- the setup wizard's three steps.
* :mod:`spec4.callbacks._chat` -- the turn, the Agentifier breadth panel, and
  the streaming poll.
* :mod:`spec4.callbacks._gate` -- the per-agent model gate, and the picker the
  retry path opens.
* :mod:`spec4.callbacks._nav` -- the pipeline pills and the Continue buttons
  between agents.
* :mod:`spec4.callbacks._artifacts` -- the round tree, the Artifact View, the
  round cost strip, the Downloads and the Open buttons beside them.

What stays here is the app shell: the status bar that is on every screen, the
URL router behind it, and the directory picker they both lead to. None of the
three belongs to a single agent or a single screen.

Phase 4j then moved every importer onto the owning module and dropped the
re-exports nothing reached through here, so what is listed below is exactly
the set some importer outside the owning module still needs. ``__all__`` is
load-bearing rather than decorative: ``[tool.mypy] strict`` implies
``no_implicit_reexport``, so without it a re-exported name could not be
imported from this module at all. Registration does not depend on that list: it
is the six imports themselves, not the names they carry, that run the decorators.

The six sub-modules never import this package back. That direction is pinned
by rule 4 of the layering contract (CLEANUP_INVENTORY.md 15.2, asserted in
``tests/test_import_layering.py``), and it is why shared helpers live in
``_shared`` rather than here.
"""

from __future__ import annotations

import pathlib
from typing import Any

from dash import ALL, Input, Output, State, callback, ctx, no_update

from spec4 import llm_selection, project_manager
from spec4.layouts._status_bar import status_context, _status_nav_class
from spec4.app_constants import (
    FF_PROMPT,
    PATH_TO_PHASE,
    PHASE_DIRECTORY_PICKER,
    PHASE_PROJECT_VIEW,
    PHASE_ROOT,
)
from spec4.session import default_session, load_working_dir
from spec4.callbacks._shared import _HOME
from spec4.callbacks._setup import (
    on_search_provider_hint,
    on_setup_back_provider,
    on_setup_connect,
    on_setup_effort_options,
    on_setup_model_continue,
    on_setup_search_connect,
    on_setup_search_skip,
)
from spec4.callbacks._chat import (
    on_breadth_try_again,
    on_chat_retry,
    on_chat_submit,
    on_fast_forward,
    on_ff_info,
    on_init_turn,
    on_stream_poll,
)
from spec4.callbacks._gate import (
    on_chat_retry_model,
    on_gate_chip,
    on_gate_connect,
    on_gate_continue,
    on_gate_effort_options,
    on_gate_keep,
    on_gate_pick,
    on_gate_provider_change,
    on_gate_use_default,
)
from spec4.callbacks._nav import (
    on_agent_pill_click,
    _switch_agent,
)
from spec4.callbacks._artifacts import (
    on_artifact_download,
    on_artifact_pane,
    on_artifact_round,
    on_project_intro_toggle,
    on_round_cost,
    on_round_tree,
    on_round_tree_line,
    OPEN_ARTIFACT_CALLBACKS,
    _open_target,
    select_artifact,
)

__all__ = [
    "_cannot_open",
    "FF_PROMPT",
    "_HOME",
    "_needs_restoring",
    "_no_change",
    "on_agent_pill_click",
    "on_artifact_download",
    "on_artifact_pane",
    "on_artifact_round",
    "on_breadth_try_again",
    "on_browser_navigate",
    "on_chat_retry",
    "on_chat_retry_model",
    "on_chat_submit",
    "on_create_folder",
    "on_dir_path_enter",
    "on_dir_select",
    "on_dir_up",
    "on_fast_forward",
    "on_ff_info",
    "on_gate_chip",
    "on_gate_connect",
    "on_gate_continue",
    "on_gate_effort_options",
    "on_gate_keep",
    "on_gate_pick",
    "on_gate_provider_change",
    "on_gate_use_default",
    "on_init_turn",
    "on_project_intro_toggle",
    "on_round_cost",
    "on_round_tree",
    "on_round_tree_line",
    "on_search_provider_hint",
    "on_setup_back_provider",
    "on_setup_connect",
    "on_setup_effort_options",
    "on_setup_model_continue",
    "on_setup_search_connect",
    "on_setup_search_skip",
    "on_status_bar",
    "on_status_bar_dir",
    "on_status_bar_setup",
    "on_stream_poll",
    "on_subdir_click",
    "OPEN_ARTIFACT_CALLBACKS",
    "_open_target",
    "_resolve_root",
    "select_artifact",
    "_switch_agent",
]

# ---------------------------------------------------------------------------
# Status bar
# ---------------------------------------------------------------------------


@callback(
    Output("status-bar-context", "children"),
    Output("status-bar-nav-project", "className"),
    Output("status-bar-nav-artifacts", "className"),
    Output("status-bar-nav-settings", "className"),
    Input("session", "data"),
    Input("prefs", "data"),
)
def on_status_bar(session: Any, prefs: Any) -> tuple[list[Any], str, str, str]:
    """Recompute the status line from the two browser stores.

    Both stores are **Inputs**, not State. That is the whole mitigation for the
    stale-working-directory failure mode: opening a different project rewrites
    the session store, starting a new round rewrites it again, and changing the
    default model rewrites prefs — each of those has to redraw the bar, and a
    State would only be read when something else happened to fire.

    Nothing is read from a module global and nothing touches the network: the
    directory and round come from the session, the provider and model from
    ``llm_selection`` (the app's one model-resolution path), and the round
    number from ``project_manager.active_version``, which is a disk read of the
    already-open project.
    """
    session = session or {}
    prefs = prefs or {}

    working_dir = session.get("working_dir") or prefs.get("working_dir") or None
    # A remembered path is not a working directory until disk agrees. The pref
    # outlives the project it names — a deleted or unmounted folder would
    # otherwise sit on the bar looking current, which is the stale-directory
    # failure this bar exists to prevent.
    if not project_manager.directory_opens(working_dir):
        working_dir = None
    round_number = (
        project_manager.active_version(working_dir, session) if working_dir else None
    )
    # Asked before the provider and model are read, because it decides whether
    # they mean anything. `default_provider_model` falls back to the remembered
    # prefs, which is right once a connection exists (an `llm_config` carries no
    # provider *name*) and a lie before one does — that fallback is what printed
    # the previous session's model onto a bar whose session could not run a turn.
    connected = llm_selection.default_is_connected(session)
    # Which selection the bar is describing. On the two screens that are about
    # one agent, it is that agent's — the bar says what the next turn will run
    # on, and an agent with an override does not run on the default. Everywhere
    # else the key is absent and `default_provider_model` reads the default by
    # the same route it always has.
    #
    # `connected` above is deliberately *not* asked per agent: it answers
    # whether this session ever made a connection, and a remembered override is
    # not evidence of one. That is why it is read before this line rather than
    # from it.
    phase_now = session.get("phase")
    if phase_now == "designer":
        gate_agent = "designer"
    elif phase_now == "chat":
        gate_agent = str(session.get("active_agent") or "")
    else:
        gate_agent = ""
    provider, model, effort = llm_selection.default_provider_model(
        session, prefs, gate_agent
    )

    # The current item is marked from the phase rather than the URL: Settings
    # is the setup wizard, Artifacts is the Artifact View, and every other
    # phase is somewhere inside Project. Project is what is left over rather
    # than a phase list of its own, so a screen added inside the project marks
    # Project without this callback having to hear about it.
    on_settings = phase_now == "setup"
    on_artifacts = phase_now == "artifacts"
    return (
        status_context(working_dir, round_number, provider, model, connected, effort),
        _status_nav_class(not on_settings and not on_artifacts),
        _status_nav_class(on_artifacts),
        _status_nav_class(on_settings),
    )


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-status-bar-dir", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_status_bar_dir(n: int | None, session: Any) -> Any:
    """Reopen the directory picker from the bar's working-directory field.

    The one route back to the picker, and it is on every screen. The setup
    wizard used to carry a second one of its own; it is gone, because the
    control that names the directory is the obvious place to change it and a
    wizard step is not.

    It only *opens* the picker: the working directory and the prefs are
    untouched here, so backing out of the picker leaves the project exactly as
    it was, and a new directory is committed by ``on_dir_select`` and nowhere
    else.

    ``browser_path`` is seeded from the open project so the picker opens where
    the developer already is rather than at home — changing project almost
    always means moving to a sibling of the current one.
    """
    if not n:
        return no_update, no_update
    session = session or {}
    return {
        **session,
        "phase": "working_dir",
        "browser_path": session.get("working_dir") or session.get("browser_path"),
    }, "/dir"


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-status-bar-model", "n_clicks"),
    Input("status-bar-nav-settings", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_status_bar_setup(
    model_n: int | None, settings_n: int | None, session: Any
) -> Any:
    """Open the setup wizard at Provider, from the bar's model slot or Settings.

    The bar's second control, on every screen alongside the directory, and
    with the directory's contract: it only *opens*. ``model`` and
    ``llm_config`` are left exactly as they are, so backing out through
    Project leaves the session able to run a turn, and the bar keeps naming
    the live model while the Provider step is on screen. The connection is
    replaced in one place only — ``on_setup_connect``, when the wizard
    advances to Model selection with a fresh list — and nowhere earlier.

    ``available_models`` is the field ``setup_layout`` branches on to show
    Provider, so clearing it is what "open at step 1" means; it is the same
    write the Model step's Back button makes (``on_setup_back_provider``),
    with a phase and a URL added. The two error fields are cleared so a
    stale message from an earlier visit is not the first thing drawn.

    Settings shares the callback rather than owning a second one because the
    two controls mean the same thing — the model slot says *what* will change,
    the nav item says *where* — and two callbacks writing the same session
    would be one more place for the two to drift.

    ``_pending_agent`` is cleared too: an agent click abandoned on its way
    through the wizard must not be replayed by a later visit to Settings.
    """
    fired = {
        "btn-status-bar-model": model_n,
        "status-bar-nav-settings": settings_n,
    }.get(ctx.triggered_id)
    if not fired:
        return no_update, no_update
    return {
        **(session or {}),
        "phase": "setup",
        "available_models": None,
        "setup_error": None,
        "agent_select_error": None,
        "_pending_agent": None,
    }, "/setup"


# ---------------------------------------------------------------------------
# URL / browser history
# ---------------------------------------------------------------------------


def _cannot_open(path: str) -> str:
    """The picker's message when the remembered directory is gone."""
    return f"Could not open {path}. Select a project directory."


def _resolve_root(session: dict[str, Any], prefs: dict[str, Any]) -> dict[str, Any]:
    """The root path's destination: the project view, or the directory picker.

    Two outcomes, never a third. The remembered directory is whatever the
    browser still holds — the session's open project first, then the
    localStorage pref that survives a restart — and it is re-checked against
    disk on every root visit rather than trusted, so a project that was
    deleted, unmounted or renamed since the last visit sends the developer to
    the picker with the path named instead of onto a project view describing a
    directory that is not there.
    """
    remembered = session.get("working_dir") or prefs.get("working_dir")
    if not remembered:
        return {**session, "phase": PHASE_DIRECTORY_PICKER, "dir_error": None}
    if not project_manager.directory_opens(remembered):
        return {
            **session,
            "phase": PHASE_DIRECTORY_PICKER,
            # The status bar reads the working directory from here, so a
            # directory that cannot be opened must not stay in the session:
            # leaving it would put a path on the bar that resolves to nothing.
            "working_dir": None,
            "browser_path": None,
            "dir_error": _cannot_open(remembered),
        }
    if not session.get("working_dir"):
        # Remembered across a browser restart: the pref outlived the session
        # store, so the project's artifacts are loaded here before the view
        # that reports them is asked to draw.
        session = load_working_dir(remembered, session)
    return {**session, "phase": PHASE_PROJECT_VIEW, "dir_error": None}


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("url", "pathname"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call="initial_duplicate",
)
def on_browser_navigate(pathname: str | None, session: Any, prefs: Any) -> Any:
    """URL → session phase, on first mount and on every back/forward after it.

    This is the app's one router. It runs on the initial call as well as on
    navigation (``initial_duplicate``) because the root path has no phase to
    fall back on: the session starts in ``PHASE_ROOT``, which draws an empty
    container, and this callback is what turns that into one of the two real
    destinations. Anything unrecognised is treated as the root rather than
    guessed at, so no URL can strand the app on a blank page.
    """
    session = session or default_session()
    prefs = prefs or {}
    if pathname not in PATH_TO_PHASE:
        return _no_change(session, _drop_detour(_resolve_root(session, prefs)))

    phase = PATH_TO_PHASE[pathname]
    new_session = {**session, "phase": phase}
    if _needs_restoring(session, prefs, phase):
        # A deep URL opened in a fresh browser session — a bookmark, a new tab.
        # The phase still comes from the path, but the project it describes
        # outlived the session store and has to be re-loaded from the pref.
        new_session = {
            **load_working_dir(prefs["working_dir"], session),
            "phase": phase,
        }
    return _no_change(session, _drop_detour(new_session))


def _drop_detour(session: dict[str, Any]) -> dict[str, Any]:
    """Forget a diverted agent click once the router leaves the wizard.

    ``_pending_agent`` belongs to the detour ``on_agent_pill_click`` sends an
    unconnected click on, and the detour is over the moment the router takes
    the developer anywhere but /setup: the Project and Artifacts links, the
    directory, the root, Back. /setup keeps it, and must, because the
    diversion's own URL write arrives here as /setup carrying the key it just
    set.

    Written only when the key is set, so a navigation that changed nothing is
    still ``no_update``. The clears on Settings (``on_status_bar_setup``) and on
    selecting a directory (``load_working_dir``) stand on their own. Settings
    is a session write, not a route, so this never sees it.
    """
    if session.get("phase") == "setup" or not session.get("_pending_agent"):
        return session
    return {**session, "_pending_agent": None}


def _no_change(session: dict[str, Any], new_session: dict[str, Any]) -> Any:
    """``no_update`` when routing changed nothing, so no needless re-render."""
    return no_update if new_session == session else new_session


def _needs_restoring(
    session: dict[str, Any], prefs: dict[str, Any], phase: str
) -> bool:
    """Whether this navigation should re-open the remembered directory.

    The gate is the *unresolved* phase, not the missing working directory, and
    the difference matters: "Start New Project" hands over a session that has
    deliberately dropped its working directory while the pref still names the
    project just finished. Keying off the missing directory would restore it
    and land the developer back where they started; keying off ``PHASE_ROOT``
    restores only a session store that has never routed at all — which is to
    say a genuinely new browser session.

    The picker is excluded because it is where a directory gets chosen; it is
    the one screen that never needs one restored behind it.
    """
    return (
        session.get("phase") == PHASE_ROOT
        and phase != PHASE_DIRECTORY_PICKER
        and not session.get("working_dir")
        and project_manager.directory_opens(prefs.get("working_dir"))
    )


# ---------------------------------------------------------------------------
# Working directory
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Output("prefs", "data", allow_duplicate=True),
    Input("btn-dir-select", "n_clicks"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call=True,
)
def on_dir_select(n: int | None, session: Any, prefs: Any) -> Any:
    if not n:
        return no_update, no_update, no_update
    # `working_dir_layout` shows home when the browsed path cannot be opened,
    # so selecting anything else here would open a directory the developer was
    # never looking at — a remembered-but-gone path, most of all.
    path = session.get("browser_path")
    if not project_manager.directory_opens(path):
        path = _HOME
    new_prefs = {**(prefs or {}), "working_dir": path}
    new_session = load_working_dir(path, session)
    # If the developer already has a working LLM connection from a previous
    # project, skip the setup screen and drop them straight into agent select.
    # The bar's model slot and its Settings item are there on every screen if
    # they want to swap models or change their web search provider.
    if new_session.get("llm_config") and new_session.get("model"):
        new_session = {**new_session, "phase": "agent_select"}
        return new_session, "/agents", new_prefs
    return new_session, "/setup", new_prefs


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-dir-up", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_dir_up(n: int | None, session: Any) -> Any:
    if not n:
        return no_update
    current = pathlib.Path(session.get("browser_path") or _HOME)
    return {**session, "browser_path": str(current.parent)}


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("dir-path-input", "n_submit"),
    State("dir-path-input", "value"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_dir_path_enter(n: int | None, value: str | None, session: Any) -> Any:
    if not n or not value:
        return no_update
    p = pathlib.Path(value)
    if p.is_dir():
        return {**session, "browser_path": str(p)}
    return no_update


@callback(
    Output("session", "data", allow_duplicate=True),
    Input({"type": "subdir-btn", "path": ALL}, "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_subdir_click(n_clicks_list: list[int | None], session: Any) -> Any:
    if not ctx.triggered_id or not any(n for n in n_clicks_list if n):
        return no_update
    return {**session, "browser_path": ctx.triggered_id["path"]}


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-create-folder", "n_clicks"),
    State("new-folder-name", "value"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_create_folder(n: int | None, name: str | None, session: Any) -> Any:
    if not n or not name or not name.strip():
        return no_update
    current = pathlib.Path(session.get("browser_path") or _HOME)
    new_path = current / name.strip()
    try:
        new_path.mkdir(parents=True, exist_ok=True)
        return {**session, "browser_path": str(new_path)}
    except OSError:
        return no_update
