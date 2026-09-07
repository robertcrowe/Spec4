from __future__ import annotations

import io
import json
import os
import pathlib
import zipfile
from datetime import datetime, timezone
from typing import Any


from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
import dash_mantine_components as dmc

from spec4 import llm_selection, project_manager, providers, streaming, websearch
from spec4.agentifier.panel_closure import close_selection, pool_from_dicts
from spec4.layouts._artifact_view import (
    BODY_ID,
    DOWNLOAD_BTN_ID,
    DOWNLOAD_ID,
    HEADER_ID,
    RESOLUTION_PRESENT,
    ROUND_TYPE,
    allowed_artifacts,
    artifact_pane,
    resolve_artifact,
    round_number_from_value,
    selected_round,
)
from spec4.layouts._chat import CHAT_ARTIFACTS, OPEN_BTN_PREFIX, open_button_id
from spec4.layouts._llm_gate import is_open as _gate_is_open
from spec4.layouts._setup import GATE_IDS, provider_key_hint
from spec4.layouts._round_cost import round_cost_lines
from spec4.layouts._round_tree import (
    LINE_TYPE,
    PHASES_DIR,
    _round_tree_head,
    _round_tree_lines_children,
    rendered_tree_lines,
)
from spec4.layouts._status_bar import (
    ARTIFACTS_PATH,
    _status_context,
    _status_nav_class,
)
from spec4.app_constants import (
    PATH_TO_PHASE,
    PHASE_DIRECTORY_PICKER,
    PHASE_PROJECT_VIEW,
    PHASE_ROOT,
    PROJECT_MODE_EXISTING,
    PROJECT_MODE_NEW,
    STATE_IN_PROGRESS,
)
from spec4.session import (
    _default_session,
    _get_agent_gen,
    _load_working_dir,
    _persist_artifacts,
    _reset_for_new_project,
    _validate_agent_preconditions,
)

_HOME = str(pathlib.Path.home())
_DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"

# The phase the Artifact View draws under, read out of the routing table rather
# than typed again. The tree's click handler needs it to tell which screen the
# click came from, and a second literal `"artifacts"` here would be one a
# rename could leave behind.
_ARTIFACTS_PHASE = PATH_TO_PHASE[ARTIFACTS_PATH]


def _prefs_keep_working_dir(prefs: Any) -> dict[str, Any]:
    """Return a prefs dict retaining only working_dir, or empty dict."""
    if prefs and prefs.get("working_dir"):
        return {"working_dir": prefs["working_dir"]}
    return {}


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
def on_status_bar(session: Any, prefs: Any) -> Any:
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
    provider, model = llm_selection.default_provider_model(session, prefs)

    # The current item is marked from the phase rather than the URL: Settings
    # is the setup wizard, Artifacts is the Artifact View, and every other
    # phase is somewhere inside Project. Project is what is left over rather
    # than a phase list of its own, so a screen added inside the project marks
    # Project without this callback having to hear about it.
    phase = session.get("phase")
    on_settings = phase == "setup"
    on_artifacts = phase == "artifacts"
    return (
        _status_context(working_dir, round_number, provider, model, connected),
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
def on_status_bar_dir(n: Any, session: Any) -> Any:
    """Reopen the directory picker from the bar's working-directory field.

    The same move as ``on_setup_back_to_dir``, from the one place the developer
    is already looking at the directory. It only *opens* the picker: the
    working directory and the prefs are untouched here, so backing out of the
    picker leaves the project exactly as it was, and a new directory is
    committed by ``on_dir_select`` and nowhere else.

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


# ---------------------------------------------------------------------------
# Round tree
# ---------------------------------------------------------------------------


@callback(
    Output("round-tree-head", "children"),
    Output("round-tree-list", "children"),
    Input("round-tree", "id"),
    State("session", "data"),
)
def on_round_tree(_id: Any, session: Any) -> Any:
    """Recompute the round tree from disk, from scratch, on every render.

    D-LR4: there is no cache here and no ``dcc.Store`` behind it. The whole
    line list is rebuilt by stating the round's files each time this runs, so
    an agent that finished a minute ago is reflected the moment the view is
    drawn again. Caching the list — the obvious optimisation on a page that
    redraws often — is precisely the bug: the tree's only job is to be true
    right now.

    The Input is the tree's own container rather than the session store. That
    is not a way of firing less often: ``render_page`` rebuilds the whole page
    on every session and prefs change, so a new round or a switched working
    directory mounts a fresh ``round-tree`` and this runs again with the new
    session. Taking the session as an *Input* instead would ask Dash to write
    into ``round-tree-list`` on screens where the tree is not mounted at all —
    chat, the designer, the setup wizard — which is the half-rendered callback
    the co-presence suite exists to catch.
    """
    session = session or {}
    working_dir = session.get("working_dir")
    round_number = (
        project_manager.active_version(working_dir, session) if working_dir else None
    )
    lines = rendered_tree_lines(working_dir, round_number)
    return (
        _round_tree_head(round_number),
        # The same two arguments the first paint used. This output replaces the
        # whole list, so recomputing it in the plain form would silently strip
        # the links off a tree that drew as clickable a moment ago — the lines
        # would still be there, still be right, and simply stop working.
        _round_tree_lines_children(
            lines, linked=True, selected=session.get("selected_file")
        ),
    )


def select_artifact(
    session: dict[str, Any], round_number: int | None, path: str
) -> dict[str, Any]:
    """The session, with one artifact selected in it.

    The two keys the Artifact View reads, written in one place. Every link
    into that screen goes through here — the round tree's lines and the chat
    frame's Open buttons — so a third selection key, or a change to what
    "selected" means, cannot land on one door and not the other.

    A copy rather than a mutation: the session is a ``dcc.Store`` value, and
    Dash only pushes a store update the browser can see when the callback
    returns a new object.
    """
    return {**session, "selected_round": round_number, "selected_file": path}


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input({"type": LINE_TYPE, "index": ALL}, "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_round_tree_line(n_clicks_list: Any, session: Any) -> Any:
    """A round-tree line click → open that file in the Artifact View.

    The target is read from ``ctx.triggered_id`` — the id of the line that was
    actually clicked, at the moment it was clicked — and from nowhere else.
    That is the whole mitigation for the failure this link has: a round can
    change while the page is open (an agent finishes and starts a new one), and
    a target captured when the tree was *rendered* would then open a file from
    the round the developer was looking at a minute ago. The round is resolved
    here too, from the session as it stands now, for the same reason.

    Two guards, both about writing nothing on a click that did not happen.
    ``prevent_initial_call`` stops the page-load fire; the ``n_clicks`` check
    stops the fire Dash sends when the set of matching components changes —
    every render mounts a fresh tree, so without it simply drawing the project
    view would write a selection into the session store. A ``triggered_id`` of
    ``None`` is the same case seen from the other side and is refused with it.

    Two screens draw this tree, for two different rounds, and the click means
    "the round the tree I am looking at is showing". On the project view that
    is the active round; on the Artifact View it is whichever round the
    selector names, which is the session's ``selected_round`` — so the round is
    read from the screen the click came from rather than assumed. Reading the
    active round on both would mean clicking a line while viewing v1 opened
    that path in v3.
    """
    if not ctx.triggered_id or not any(n for n in n_clicks_list if n):
        return no_update, no_update
    path = ctx.triggered_id.get("index")
    if not path:
        return no_update, no_update
    session = session or _default_session()
    working_dir = session.get("working_dir")
    if session.get("phase") == _ARTIFACTS_PHASE:
        round_number = selected_round(working_dir, session)
    else:
        round_number = (
            project_manager.active_version(working_dir, session)
            if working_dir
            else None
        )
    return select_artifact(session, round_number, path), ARTIFACTS_PATH


# ---------------------------------------------------------------------------
# Artifact View
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Input({"type": ROUND_TYPE, "index": ALL}, "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_artifact_round(n_clicks_list: Any, session: Any) -> Any:
    """A round in the selector was chosen → move the selection to that round.

    The one place the Artifact View writes the session, and it writes exactly
    two keys. ``selected_round`` becomes the chosen round; ``selected_file`` is
    **cleared when that file is not in the new round's allowed set**, and kept
    when it is. Both halves matter. Keeping a file that v1 never had would
    leave the pane rendering a rejection for a line the tree beside it is not
    even drawing — a dead end the developer did not ask for. Clearing one that
    both rounds have would throw away the comparison they were making, which is
    the main reason to switch rounds at all.

    Writing the session is what redraws the screen: ``render_page`` rebuilds
    the page on every session change, so the tree, the selector and the pane
    all come back for the new round together. That is the whole mechanism
    behind "switching rounds updates the tree and the available files".

    The guards are the round tree's, for the round tree's reasons.
    ``prevent_initial_call`` stops the page-load fire; the ``n_clicks`` check
    stops the fire Dash sends when the set of matching components changes —
    every render mounts a fresh strip, so without it simply redrawing the
    screen would write a round into the session. ``n_clicks`` is what makes
    this reliable across those redraws and is why the selector is a strip of
    buttons rather than a dropdown; see ``_round_select`` for the failure a
    dropdown has here.
    """
    if not ctx.triggered_id or not any(n for n in n_clicks_list if n):
        return no_update
    chosen = round_number_from_value(ctx.triggered_id.get("index"))
    if chosen is None or chosen == session_round(session):
        return no_update
    session = session or _default_session()
    selected_file = session.get("selected_file")
    if selected_file is not None and selected_file not in allowed_artifacts(
        session.get("working_dir"), chosen
    ):
        selected_file = None
    return {**session, "selected_round": chosen, "selected_file": selected_file}


def session_round(session: Any) -> int | None:
    """The round the session names, or ``None``.

    Deliberately the *stored* value rather than ``selected_round``'s resolved
    one: this is used to tell "the developer chose the round already showing"
    from a real switch, and resolving would answer the same for a session that
    has not chosen at all.
    """
    return round_number_from_value((session or {}).get("selected_round"))


@callback(
    Output(HEADER_ID, "children"),
    Output(BODY_ID, "children"),
    Input("artifact-view-content", "id"),
    State("session", "data"),
)
def on_artifact_pane(_id: Any, session: Any) -> Any:
    """Redraw the content pane: the header line and the file body.

    Single-purpose and read-only. It resolves, it reads, it renders — it never
    writes the session, so it cannot race ``on_artifact_round`` above or loop
    with it. Everything it needs is recomputed here from disk; nothing is
    cached, so a file an agent rewrote a moment ago shows its new size and its
    new contents the next time this runs.

    The file is read only for a request the resolver allows. A rejection
    renders the plain "no such artifact in v{N}" line and reaches no
    filesystem at all — the check ordering that guarantees this lives in
    ``resolve_artifact`` and is asserted there.

    One Input and one State, and the shape is deliberate. The pane's own
    container is the remount trigger, exactly as ``on_round_tree`` uses the
    tree's: ``render_page`` rebuilds the page whenever the session changes, so
    a new selection, a new working directory or a round switch all mount a
    fresh ``artifact-view-content`` and run this with the session as it now
    stands. Taking the session store as an *Input* instead would ask Dash to
    dispatch this on every screen in the app — chat, the designer, the setup
    wizard — none of which mount the header or the body, which is the
    half-rendered callback the co-presence suite exists to catch.
    """
    session = session or {}
    working_dir = session.get("working_dir")
    return artifact_pane(
        working_dir,
        selected_round(working_dir, session),
        session.get("selected_file"),
    )


@callback(
    Output(DOWNLOAD_ID, "data"),
    Input(DOWNLOAD_BTN_ID, "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_artifact_download(n_clicks: Any, session: Any) -> Any:
    """The Download click → a copy of exactly the file the pane is showing.

    The click hands over nothing but itself; the round and the path are read
    back out of the session and re-resolved here, through the same confined
    resolver the pane reads through. That is the one rule this callback
    exists to keep: ``dcc.send_file`` is reached only for the resolver's own
    ``present`` outcome, off the resolver's own ``resolved`` path — never off
    the session store's raw string, which is exactly the shortcut that would
    let a doctored ``selected_file`` walk the resolver's confinement.

    A stale click — the button was enabled, then the file vanished, or a
    round switch cleared the selection before the click landed — resolves to
    something other than ``present`` and sends nothing, the same silence the
    disabled button would have produced had the render caught up in time.
    """
    if not n_clicks:
        return no_update
    session = session or {}
    working_dir = session.get("working_dir")
    round_number = selected_round(working_dir, session)
    result = resolve_artifact(working_dir, round_number, session.get("selected_file"))
    if result.outcome != RESOLUTION_PRESENT:
        return no_update
    assert result.resolved is not None  # `present` carries every field
    return dcc.send_file(str(result.resolved))  # type: ignore[attr-defined, no-untyped-call]


# ---------------------------------------------------------------------------
# Round cost
# ---------------------------------------------------------------------------


@callback(
    Output("round-cost-line", "children"),
    Output("round-cost-unpriced", "children"),
    Output("round-cost-note", "children"),
    Input("round-cost", "id"),
    State("session", "data"),
)
def on_round_cost(_id: Any, session: Any) -> Any:
    """Recompute the round's cost from ``usage.json``, from scratch, every time.

    The same shape as ``on_round_tree`` above and for the same reason: no
    cache, no ``dcc.Store``, and the strip's own container as the Input rather
    than the session store. ``render_page`` rebuilds the page on every session
    change, so a new round or a switched working directory mounts a fresh
    ``round-cost`` and this runs again with the new session; taking the
    session as an Input instead would ask Dash to write into these three lines
    on screens that do not mount them.

    Caching the total is the obvious optimisation and is precisely the bug:
    the agent that finished thirty seconds ago is the whole reason a developer
    looks at this line, and a memoised figure would still be showing the
    round's cost before that run.
    """
    session = session or {}
    working_dir = session.get("working_dir")
    round_number = (
        project_manager.active_version(working_dir, session) if working_dir else None
    )
    return tuple(round_cost_lines(working_dir, round_number))


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
        session = _load_working_dir(remembered, session)
    return {**session, "phase": PHASE_PROJECT_VIEW, "dir_error": None}


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("url", "pathname"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call="initial_duplicate",
)
def on_browser_navigate(pathname: Any, session: Any, prefs: Any) -> Any:
    """URL → session phase, on first mount and on every back/forward after it.

    This is the app's one router. It runs on the initial call as well as on
    navigation (``initial_duplicate``) because the root path has no phase to
    fall back on: the session starts in ``PHASE_ROOT``, which draws an empty
    container, and this callback is what turns that into one of the two real
    destinations. Anything unrecognised is treated as the root rather than
    guessed at, so no URL can strand the app on a blank page.
    """
    session = session or _default_session()
    prefs = prefs or {}
    if pathname not in PATH_TO_PHASE:
        return _no_change(session, _resolve_root(session, prefs))

    phase = PATH_TO_PHASE[pathname]
    new_session = {**session, "phase": phase}
    if _needs_restoring(session, prefs, phase):
        # A deep URL opened in a fresh browser session — a bookmark, a new tab.
        # The phase still comes from the path, but the project it describes
        # outlived the session store and has to be re-loaded from the pref.
        new_session = {
            **_load_working_dir(prefs["working_dir"], session),
            "phase": phase,
        }
    return _no_change(session, new_session)


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


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-setup-back-to-dir", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_setup_back_to_dir(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return {
        **session,
        "phase": "working_dir",
        "available_models": None,
        "setup_error": None,
    }, "/dir"


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
def on_dir_select(n: Any, session: Any, prefs: Any) -> Any:
    if not n:
        return no_update, no_update, no_update
    # `_working_dir_layout` shows home when the browsed path cannot be opened,
    # so selecting anything else here would open a directory the developer was
    # never looking at — a remembered-but-gone path, most of all.
    path = session.get("browser_path")
    if not project_manager.directory_opens(path):
        path = _HOME
    new_prefs = {**(prefs or {}), "working_dir": path}
    new_session = _load_working_dir(path, session)
    # If the developer already has a working LLM connection from a previous
    # project, skip the setup screen and drop them straight into agent select.
    # The "Change provider" button on the agents page is still there if they
    # want to swap models or change their web search provider.
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
def on_dir_up(n: Any, session: Any) -> Any:
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
def on_dir_path_enter(n: Any, value: Any, session: Any) -> Any:
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
def on_subdir_click(n_clicks_list: Any, session: Any) -> Any:
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
def on_create_folder(n: Any, name: Any, session: Any) -> Any:
    if not n or not name or not name.strip():
        return no_update
    current = pathlib.Path(session.get("browser_path") or _HOME)
    new_path = current / name.strip()
    try:
        new_path.mkdir(parents=True, exist_ok=True)
        return {**session, "browser_path": str(new_path)}
    except OSError:
        return no_update


# ---------------------------------------------------------------------------
# Setup — step 1: provider + API key
# ---------------------------------------------------------------------------


@callback(
    Output("setup-api-key-hint", "children"),
    Input("setup-provider", "value"),
    prevent_initial_call=False,
)
def on_provider_hint(provider_label: Any) -> Any:
    if providers.provider_key_for_label(provider_label or "") == "bedrock":
        return dmc.Text(
            "Bedrock API key: enter KEY:REGION (e.g. bdak_…:us-east-1). "
            "IAM credentials: ACCESS_KEY_ID:SECRET_ACCESS_KEY:REGION[:SESSION_TOKEN]. "
            "Leave blank to use ambient credentials "
            "(env vars, ~/.aws/credentials, IAM role).",
            size="xs",
            c="dimmed",
        )
    return html.Div()


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("prefs", "data", allow_duplicate=True),
    Input("btn-setup-connect", "n_clicks"),
    State("setup-provider", "value"),
    State("setup-api-key", "value"),
    State("setup-save-prefs", "checked"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call=True,
)
def on_setup_connect(
    n: Any, provider_label: Any, api_key: Any, save_prefs: Any, session: Any, prefs: Any
) -> Any:
    if not n:
        return no_update, no_update
    provider_key = providers.provider_key_for_label(provider_label)
    if provider_key != "bedrock" and (not api_key or not api_key.strip()):
        return {**session, "setup_error": "Please enter an API key."}, no_update

    models, err = providers.list_models(provider_key, (api_key or "").strip())
    if models:
        new_session = {
            **session,
            "provider": provider_key,
            "api_key": (api_key or "").strip(),
            "available_models": models,
            "setup_error": None,
        }
        base = _prefs_keep_working_dir(prefs)
        key = (api_key or "").strip()
        new_prefs = (
            {
                **prefs,
                "provider": provider_key,
                "api_key": key,
                # Keyed by provider so a per-agent override on a different
                # provider has somewhere to prefill from. Written only under
                # the same "Remember" consent as the single key above.
                "provider_keys": {
                    **(prefs.get("provider_keys") or {}),
                    provider_key: key,
                },
                "save_prefs": True,
            }
            if save_prefs
            else base
        )
        return new_session, new_prefs
    if provider_key == "bedrock":
        if "partial credentials" in err.lower():
            err = (
                "Partial IAM credentials — use ACCESS_KEY_ID:SECRET_ACCESS_KEY:REGION, "
                "or switch to a Bedrock API key (KEY:REGION)."
            )
        elif "unrecognizedclientexception" in err.lower() or (
            "invalid" in err.lower() and "token" in err.lower()
        ):
            err = (
                "AWS credentials rejected. "
                "If you have a Bedrock API key, enter it as KEY:REGION "
                "(e.g. bdak_…:us-east-1). For IAM credentials use "
                "ACCESS_KEY_ID:SECRET_ACCESS_KEY:REGION[:SESSION_TOKEN]."
            )
    return {**session, "setup_error": f"Connection failed: {err}"}, no_update


@callback(
    Output("prefs", "data", allow_duplicate=True),
    Input("btn-setup-clear", "n_clicks"),
    State("prefs", "data"),
    prevent_initial_call=True,
)
def on_setup_clear(n: Any, prefs: Any) -> Any:
    if not n:
        return no_update
    return _prefs_keep_working_dir(prefs)


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-setup-back-provider", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_setup_back_provider(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return {**session, "available_models": None, "setup_error": None}


# ---------------------------------------------------------------------------
# Setup — step 2: model
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("prefs", "data", allow_duplicate=True),
    Output("image-support-store", "data", allow_duplicate=True),
    Output("tool-support-store", "data", allow_duplicate=True),
    Output("notifications-container", "children", allow_duplicate=True),
    Input("btn-setup-model-continue", "n_clicks"),
    State("setup-model", "value"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call=True,
)
def on_setup_model_continue(n: Any, model: Any, session: Any, prefs: Any) -> Any:
    if not n or not model:
        return no_update, no_update, no_update, no_update, no_update
    provider_key = session.get("provider") or ""
    llm_config = llm_selection.build_llm_config(
        provider_key, model, session.get("api_key")
    )
    new_session = {
        **session,
        "model": model,
        "llm_config": llm_config,
        "setup_error": None,
    }
    new_prefs = {**prefs, "model": model} if prefs.get("save_prefs") else prefs

    # The config is committed above, before the probes run and whatever they
    # return: capability probing is advisory and must never cost the developer
    # a working connection. `llm_selection.probe_capabilities` owns the Bedrock
    # skip and the never-raises contract, so the per-agent gate gets identical
    # behaviour from the same call.
    image_support, tool_support = llm_selection.probe_capabilities(
        provider_key, llm_config
    )
    return new_session, new_prefs, image_support, tool_support, no_update


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-setup-back-model", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_setup_back_model(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return {**session, "model": None, "llm_config": None, "setup_error": None}


# ---------------------------------------------------------------------------
# Setup — step 3: web search provider
# ---------------------------------------------------------------------------


@callback(
    Output("setup-search-key", "label"),
    Output("setup-search-key", "placeholder"),
    Output("setup-search-hint", "children"),
    Input("setup-search-provider", "value"),
    prevent_initial_call=False,
)
def on_search_provider_hint(provider_label: Any) -> Any:
    """Retitle the key field and describe whichever provider is selected."""
    key = websearch.provider_key_for_label(provider_label or "")
    spec = websearch.PROVIDERS[key]
    hint = dmc.Text(
        [
            f"{spec['blurb']} Get a key at ",
            html.A(
                spec["signup_url"],
                href=spec["signup_url"],
                target="_blank",
                style={"color": "inherit"},
            ),
            ".",
        ],
        size="xs",
        c="dimmed",
    )
    return spec["key_label"], spec["placeholder"], hint


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("prefs", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-setup-search-connect", "n_clicks"),
    State("setup-search-provider", "value"),
    State("setup-search-key", "value"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call=True,
)
def on_setup_search_connect(
    n: Any, provider_label: Any, search_key: Any, session: Any, prefs: Any
) -> Any:
    if not n:
        return no_update, no_update, no_update
    provider = websearch.provider_key_for_label(provider_label or "")
    label = websearch.label_for_provider(provider)
    if not search_key or not search_key.strip():
        return (
            {**session, "setup_error": f"Please enter a {label} API key."},
            no_update,
            no_update,
        )
    key = search_key.strip()
    ok, _, err = websearch.validate(websearch.SearchConfig(provider, key))
    if ok:
        new_session = {
            **session,
            "search_provider": provider,
            "search_api_key": key,
            # Cleared so a stale pre-Exa key cannot outrank the new choice:
            # `websearch.from_session` falls back to it when search_api_key is
            # empty, which would silently route to Tavily.
            "tavily_api_key": None,
            "setup_error": None,
            "phase": "agent_select",
        }
        new_prefs = (
            {
                **prefs,
                "search_provider": provider,
                "search_key": key,
                "tavily_key": None,
            }
            if prefs.get("save_prefs")
            else prefs
        )
        return new_session, new_prefs, "/agents"
    return (
        {**session, "setup_error": f"{label} connection failed: {err}"},
        no_update,
        no_update,
    )


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-setup-search-skip", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_setup_search_skip(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return {
        **session,
        "search_provider": None,
        "search_api_key": None,
        # Also cleared: `from_session` reads it as a fallback, so leaving it set
        # would turn "Skip" into "keep using the old Tavily key".
        "tavily_api_key": None,
        "setup_error": None,
        "phase": "agent_select",
    }, "/agents"


# ---------------------------------------------------------------------------
# Agent select
# ---------------------------------------------------------------------------


# D-LR8: `on_chat_back` stood here, serving the chat frame's `← Back` button
# with a route to `/agents`. Both are gone — the status bar's Project link is
# the same route from the same screen, and it is mounted in the shell rather
# than in this layout. The walk covering all four removed Back controls is in
# `layouts/_chat.py`, at `_chat_action_buttons`.


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-agent-change-provider", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_agent_change_provider(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return {
        **session,
        "phase": "setup",
        "available_models": None,
        "model": None,
        "llm_config": None,
        "setup_error": None,
        "agent_select_error": None,
    }, "/setup"


# ---------------------------------------------------------------------------
# Chat — initial turn
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("stream-poll-interval", "max_intervals"),
    Input("init-turn-interval", "n_intervals"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_init_turn(n: Any, session: Any) -> Any:
    if not n or session.get("_initial_turn_done") or session.get("messages"):
        return no_update, no_update
    # The layout already disables the interval while the gate is open; this is
    # the belt to that braces, so a stale tick cannot start a turn on a model
    # the developer has not agreed to.
    if _gate_is_open(session, session.get("active_agent") or ""):
        return no_update, no_update
    gen = _get_agent_gen(None, session)
    stream_id = streaming.start(gen, session)
    return (
        {
            **session,
            "messages": [{"role": "assistant", "content": ""}],
            "_stream_id": stream_id,
            "_initial_turn_done": True,
            "_stream_error": None,
        },
        -1,
    )


# ---------------------------------------------------------------------------
# Chat — user message
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("chat-input", "value"),
    Output("stream-poll-interval", "max_intervals"),
    Input("btn-chat-submit", "n_clicks"),
    Input("chat-input", "n_submit"),
    State("chat-input", "value"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_chat_submit(n_clicks: Any, n_submit: Any, user_input: Any, session: Any) -> Any:
    if not user_input or not user_input.strip():
        return no_update, no_update, no_update
    if session.get("_stream_id"):
        return no_update, no_update, no_update
    messages = list(session.get("messages", []))
    messages.append({"role": "user", "content": user_input.strip()})
    messages.append({"role": "assistant", "content": ""})
    gen = _get_agent_gen(user_input.strip(), session)
    stream_id = streaming.start(gen, session)
    return (
        {
            **session,
            "messages": messages,
            "_stream_id": stream_id,
            "_stream_error": None,
        },
        "",
        -1,
    )


# ---------------------------------------------------------------------------
# Chat — StackAdvisor Fast Forward
# ---------------------------------------------------------------------------

# The developer's sweep instruction lives in app_constants (single source:
# the Agentifier's Python-paced phases match against it too, and importing
# callbacks from agentifier would be circular). Re-exported here so the
# button callback and existing imports keep one name.
from spec4.app_constants import FF_PROMPT  # noqa: E402


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("stream-poll-interval", "max_intervals", allow_duplicate=True),
    Input("btn-chat-fast-forward", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_fast_forward(n_clicks: Any, session: Any) -> Any:
    if not n_clicks:
        return no_update, no_update
    # Turn-integrity guard: ignore clicks while a stream is in flight, or while
    # the model gate is still unanswered — FF is a turn like any other and must
    # not slip past a choice the developer has not made.
    if session.get("_stream_id"):
        return no_update, no_update
    if _gate_is_open(session, session.get("active_agent") or ""):
        return no_update, no_update
    messages = list(session.get("messages", []))
    messages.append({"role": "user", "content": FF_PROMPT})
    messages.append({"role": "assistant", "content": ""})
    gen = _get_agent_gen(FF_PROMPT, session)
    stream_id = streaming.start(gen, session)
    return (
        {
            **session,
            "messages": messages,
            "_stream_id": stream_id,
            "_stream_error": None,
        },
        -1,
    )


# ---------------------------------------------------------------------------
# Per-agent model gate
# ---------------------------------------------------------------------------
#
# One set of callbacks for all seven agents and both surfaces: only one gate is
# ever open, and the agent it belongs to is carried in `agent_llm_draft`. The
# gate answers a question the setup wizard already answers for the default, so
# both go through the same builder and probe wrapper in `llm_selection` — a
# Bedrock credential parsed one way here and another way there is exactly the
# drift this shares code to prevent.


def _gate_agent(session: dict[str, Any]) -> str:
    """Which agent the open gate belongs to."""
    draft = session.get("agent_llm_draft") or {}
    if draft.get("agent"):
        return str(draft["agent"])
    if session.get("phase") == "designer":
        return "designer"
    return str(session.get("active_agent") or "brainstormer")


def _gate_answered(session: dict[str, Any], agent: str, **extra: Any) -> dict[str, Any]:
    """Close the gate for `agent`, clearing the draft and any error."""
    asked = {**(session.get("agent_llm_asked") or {}), agent: True}
    return {
        **session,
        "agent_llm_asked": asked,
        "agent_llm_draft": None,
        "agent_llm_error": None,
        **extra,
    }


@callback(
    Output(GATE_IDS["hint"], "children"),
    Output(GATE_IDS["api_key"], "value"),
    Input(GATE_IDS["provider"], "value"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call=False,
)
def on_gate_provider_change(provider_label: Any, session: Any, prefs: Any) -> Any:
    """Update the credential hint and the key field for the chosen provider.

    Refilling the key matters here in a way it does not in the setup wizard.
    The gate opens with the provider Select on the *default's* provider, so the
    box starts holding the default's key; switching the Select to another
    provider without clearing it submits one provider's credential to another.
    That is a 401 at the first real call — and for OpenRouter, whose model list
    answers the same for any bearer, Connect could not catch it either.

    The draft's own provider is left alone: re-opening "pick a different model"
    prefills the key from the existing override, and the initial render must not
    wipe it.
    """
    provider_key = providers.provider_key_for_label(provider_label or "")
    hint = provider_key_hint(provider_label or "")
    draft = (session or {}).get("agent_llm_draft") or {}
    if draft.get("provider") == provider_key and draft.get("api_key") is not None:
        return hint, no_update
    return hint, llm_selection.key_for_provider(
        session or {}, prefs or {}, provider_key
    )


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-agent-llm-default", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_gate_use_default(n: Any, session: Any) -> Any:
    """Answer "use the default" — which stores no entry.

    Dropping any existing override is what makes the answer live: the agent
    resolves against `llm_config` from now on and follows the default if the
    developer later changes it.
    """
    if not n:
        return no_update
    agent = _gate_agent(session)
    overrides = {
        k: v for k, v in (session.get("agent_llm") or {}).items() if k != agent
    }
    return _gate_answered(session, agent, agent_llm=overrides)


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-agent-llm-keep", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_gate_keep(n: Any, session: Any) -> Any:
    """Keep a carried-forward override: no key re-entry, no re-probe.

    The entry survived `_reset_for_new_project` intact — credential, model list
    and both capability flags — so answering costs nothing but the flag.
    """
    if not n:
        return no_update
    return _gate_answered(session, _gate_agent(session))


def _open_pick_fields(
    session: dict[str, Any], *, retry: bool = False
) -> dict[str, Any]:
    """Expand the gate into the provider/key/model fields.

    Seeded from any existing override, so an unchanged provider and key need no
    Connect round trip: the model list came with the entry, which is what makes
    "pick a different model" one click and a dropdown rather than a re-type.

    ``retry`` marks a picker opened from a failed step. Two things follow from
    it, and *only* from it — a picker opened deliberately (the chip, or agent
    entry) behaves exactly as before:

    * choosing a model re-runs the failed step immediately, and
    * a model the tool probe reports as incapable is refused rather than
      committed.

    The second bends the rule that probes are advisory and never block. It is
    bent here because this is the one path where the app spends a call without
    asking again, and it must not spend it on a model just measured as unable to
    do the step.
    """
    agent = _gate_agent(session)
    existing = llm_selection.entry(session, agent) or {}
    draft: dict[str, Any] = {"agent": agent}
    if retry:
        draft["retry"] = True
    if existing:
        draft.update(
            {
                "provider": existing.get("provider"),
                "api_key": (existing.get("llm_config") or {}).get("api_key", ""),
                "available_models": existing.get("available_models") or [],
                "model": existing.get("model"),
            }
        )
    return {**session, "agent_llm_draft": draft, "agent_llm_error": None}


# The gate button and the chip open the same fields but live in different
# subtrees — the chip is suppressed while the gate is open, and never renders at
# all on the Designer surface. They therefore need one callback each: Dash
# refuses to dispatch a callback whose Inputs are not all present in the current
# layout, so pairing them would break whichever one is on screen.
@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-agent-llm-pick", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_gate_pick(n: Any, session: Any) -> Any:
    """Open the fields from the gate card itself, at agent entry."""
    if not n:
        return no_update
    return _open_pick_fields(session)


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-agent-llm-chip", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_gate_chip(n: Any, session: Any) -> Any:
    """Re-open the same card mid-agent, from the control-row chip.

    Refused while a turn is streaming: that turn is already committed to a
    config, and changing the label under it would misreport what produced the
    answer on screen. A change made here applies from the next turn, which the
    per-turn resolution in `_get_agent_gen` gives for free.
    """
    if not n or session.get("_stream_id"):
        return no_update
    return _open_pick_fields(session)


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-chat-retry-model", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_chat_retry_model(n: Any, session: Any) -> Any:
    """Open the model picker from the failed-turn panel.

    Retrying a step on the model that just failed is the right move for an
    overload and useless for an unreachable provider or a rejected key. This is
    the second door out of that panel: pick a different provider/model, then the
    panel's own Try Again re-runs the step on it.

    Deliberately does *not* retry by itself — the step may be expensive, and the
    developer may still back out of the picker. It only opens the fields; the
    gate's answer preserves `_stream_error` and the transcript, so the retry
    panel is still there afterwards.

    Its own callback rather than sharing the chip's: the chip and this button
    render in different subtrees, and Dash refuses to dispatch a callback whose
    Inputs are not all on screen.
    """
    if not n or session.get("_stream_id"):
        return no_update
    return _open_pick_fields(session, retry=True)


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-agent-llm-back", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_gate_back(n: Any, session: Any) -> Any:
    """Collapse the fields back to the resting card, discarding the draft."""
    if not n:
        return no_update
    return {**session, "agent_llm_draft": None, "agent_llm_error": None}


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("prefs", "data", allow_duplicate=True),
    Input("btn-agent-llm-connect", "n_clicks"),
    State(GATE_IDS["provider"], "value"),
    State(GATE_IDS["api_key"], "value"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call=True,
)
def on_gate_connect(
    n: Any, provider_label: Any, api_key: Any, session: Any, prefs: Any
) -> Any:
    """Fetch the model list — the hard gate, exactly as in the setup wizard.

    No models means nothing is written: no draft models, no entry, no answered
    flag, and above all no change to the default's own provider or key. The
    model field is not rendered until this succeeds, so Continue cannot be
    reached with a credential that does not work.
    """
    if not n:
        return no_update, no_update
    prefs = prefs or {}
    provider_key = providers.provider_key_for_label(provider_label)
    key = (api_key or "").strip()
    draft = {
        **(session.get("agent_llm_draft") or {}),
        "agent": _gate_agent(session),
        "provider": provider_key,
        "api_key": key,
    }
    if provider_key != "bedrock" and not key:
        return {
            **session,
            "agent_llm_draft": {**draft, "available_models": []},
            "agent_llm_error": "Please enter an API key.",
        }, no_update

    models, err = providers.list_models(provider_key, key)
    if not models:
        return {
            **session,
            "agent_llm_draft": {**draft, "available_models": []},
            "agent_llm_error": f"Connection failed: {err}",
        }, no_update

    new_prefs = (
        {
            **prefs,
            "provider_keys": {
                **(prefs.get("provider_keys") or {}),
                provider_key: key,
            },
        }
        if prefs.get("save_prefs")
        else no_update
    )
    return {
        **session,
        "agent_llm_draft": {**draft, "available_models": models},
        "agent_llm_error": None,
    }, new_prefs


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("stream-poll-interval", "max_intervals", allow_duplicate=True),
    Input("btn-agent-llm-continue", "n_clicks"),
    State(GATE_IDS["model"], "value"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_gate_continue(n: Any, model: Any, session: Any) -> Any:
    """Commit the override and answer the gate — and, from a failed step, re-run it.

    The entry is normally written whatever the probes return, `None/None`
    included: capability probing is advisory, and a probe that fails must never
    leave an agent unable to start.

    A picker opened from a failed step (`draft["retry"]`, see
    :func:`_open_pick_fields`) is the one exception, because choosing a model
    there spends a call immediately without asking again. A model whose tool
    probe came back a definite ``False`` is refused rather than committed: the
    picker stays open, on its model list, with the reason in the slot it already
    renders errors into. ``None`` never refuses — unknown is not a negative, and
    gateway providers do report false negatives, which is why the message points
    at the way round it.

    The retry itself is the same replay Try Again performs. Writes only into
    `agent_llm[agent]` — the default's credential is not this flow's to touch.
    """
    if not n or not model:
        return no_update, no_update
    agent = _gate_agent(session)
    draft = session.get("agent_llm_draft") or {}
    from_retry = bool(draft.get("retry"))
    provider_key = draft.get("provider") or ""
    llm_config = llm_selection.build_llm_config(
        provider_key, model, draft.get("api_key")
    )
    image_support, tool_support = llm_selection.probe_capabilities(
        provider_key, llm_config
    )

    if from_retry and tool_support is False:
        return {
            **session,
            "agent_llm_error": (
                f"{model} reports no tool support, so the step was not re-run. "
                "Pick another model, or go Back and use Try Again to run it "
                "anyway."
            ),
        }, no_update

    entry = {
        "provider": provider_key,
        "model": model,
        "available_models": draft.get("available_models") or [],
        "llm_config": llm_config,
        "image_support": image_support,
        "tool_support": tool_support,
    }
    overrides = {**(session.get("agent_llm") or {}), agent: entry}
    answered = _gate_answered(session, agent, agent_llm=overrides)

    if not from_retry:
        return answered, no_update

    if agent == "designer":
        # Designer's gate replaces its wizard, so the stores a draw writes to
        # are not mounted here and this callback cannot start one. Arm the
        # restored wizard instead — `designer_layout` reads this and mounts a
        # one-shot interval that fires the draw.
        failed = dict(answered.get("_designer_failed_draw") or {})
        if failed:
            failed["auto_retry"] = True
            answered = {**answered, "_designer_failed_draw": failed}
        return answered, no_update

    return _start_retry_turn(answered)


# ---------------------------------------------------------------------------
# Chat — retry after a failed turn
# ---------------------------------------------------------------------------


def _start_retry_turn(session: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Replay the turn that failed. Returns the store and the poll setting.

    The failed assistant bubble is dropped so the retry streams into a fresh
    one. What gets re-sent is whatever the dead turn was sent: the user message
    it was answering when one precedes it, or ``None`` for an agent-opening turn
    such as the CodeScanner scan. The agents' own orphan handling
    (``_drop_orphan_or_route_to_fresh_start``) discards the half-finished
    exchange their message history is carrying, so a retried opening turn
    re-seeds from session state rather than resuming mid-sentence.

    Shared by the Try Again button and by the picker, which re-runs the step the
    moment a model is chosen — one replay, so the two cannot drift.
    """
    messages = list(session.get("messages") or [])
    if messages and messages[-1].get("role") == "assistant":
        messages.pop()
    retry_input: str | None = None
    if messages and messages[-1].get("role") == "user":
        retry_input = messages[-1].get("content")
    messages.append({"role": "assistant", "content": ""})
    gen = _get_agent_gen(retry_input, session)
    stream_id = streaming.start(gen, session)
    return (
        {
            **session,
            "messages": messages,
            "_stream_id": stream_id,
            "_stream_error": None,
        },
        -1,
    )


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("stream-poll-interval", "max_intervals", allow_duplicate=True),
    Input("btn-chat-retry", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_chat_retry(n_clicks: Any, session: Any) -> Any:
    """Re-run the turn that failed, on the model it is already using (D-ER1).

    A provider error (overload, rate limit, dropped connection) leaves the
    formatted exception as the assistant message and no state transition. This
    replays the same turn unchanged — the right move for a transient failure,
    and the escape hatch when the picker has refused a model the developer wants
    to try anyway.
    """
    if not n_clicks:
        return no_update, no_update
    if session.get("_stream_id"):
        return no_update, no_update
    return _start_retry_turn(session)


@callback(
    Output("ff-info-modal", "opened"),
    Input("btn-ff-info", "n_clicks"),
    prevent_initial_call=True,
)
def on_ff_info(n_clicks: Any) -> Any:
    """Open the Fast Forward info dialog; the modal closes itself client-side."""
    if not n_clicks:
        return no_update
    return True


# ---------------------------------------------------------------------------
# Chat — Agentifier breadth selection
# ---------------------------------------------------------------------------


def _breadth_summary(selected: list[str]) -> str:
    """Human-readable summary of the checkbox selection for the chat bubble."""
    if not selected:
        return "Selected no features."
    names = ", ".join(selected[:5])
    if len(selected) > 5:
        names += f" … and {len(selected) - 5} more"
    plural = "s" if len(selected) != 1 else ""
    return f"Selected {len(selected)} feature{plural}: {names}"


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("stream-poll-interval", "max_intervals", allow_duplicate=True),
    Input("btn-breadth-submit", "n_clicks"),
    State("breadth-checkbox-group", "value"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_breadth_submit(n_clicks: Any, selected: Any, session: Any) -> Any:
    if not n_clicks:
        return no_update, no_update
    if session.get("_stream_id"):
        return no_update, no_update
    selected = selected or []
    session["agentifier_breadth_selection"] = selected
    summary = _breadth_summary(selected)
    messages = list(session.get("messages", []))
    messages.append({"role": "user", "content": summary})
    messages.append({"role": "assistant", "content": ""})
    gen = _get_agent_gen(summary, session)
    stream_id = streaming.start(gen, session)
    return (
        {
            **session,
            "messages": messages,
            "_stream_id": stream_id,
            "_stream_error": None,
        },
        -1,
    )


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("stream-poll-interval", "max_intervals", allow_duplicate=True),
    Input("btn-breadth-try-again", "n_clicks"),
    State("session", "data"),
    State("breadth-retry-input", "value"),
    prevent_initial_call=True,
)
def on_breadth_try_again(n_clicks: Any, session: Any, note: Any = None) -> Any:
    """Discard the current candidate set and run Scout again (D-TA2).

    Session-only. Nothing on disk is touched: the reset demotes
    ``agentifier_state``, which is the sole condition under which
    ``_persist_artifacts`` writes ``ai_features.json``, so the current round's
    artifact is retained until the flow re-completes and replaces it. Earlier
    implemented rounds are read (for revision carry-forward) but never written.

    With the flow reset, ``agentifier_messages`` empty and the cached pool
    cleared, ``run(None, …)`` dispatches to ``_run_catalog_phase``'s fresh-start
    branch — the same route the stale-input rediscovery takes — which re-derives
    the revision block from disk. That is what makes Try Again inside a revision
    round produce a genuinely new candidate set rather than re-opening the
    reselection panel over the old one.

    Guided redraw (D-TA7): ``note`` is the panel's "Tell me what to change"
    text. Notes accumulate across successive Try Agains on the same panel — a
    second note is added to the first, not substituted, so an earlier "fewer,
    simpler" is not silently lost — and the set being rejected travels with
    them so "too many" and "drop X" have a referent. The block is written
    *after* the reset (which clears it, like every other agentifier key), so
    it survives exactly this restart. With no notes at all the prompts are
    untouched (the orchestrator passes Scout ``None`` for empty notes): that
    is the plain redraw this button always was.

    Every click is also logged as one ``history`` event — the note (None for
    a blank redraw), the set rejected, and when — which ``_complete_agentifier``
    writes to ``ai_features.json`` as ``discovery_guidance``, so the round's
    record shows each redraw the developer asked for, in order.
    """
    from spec4.agentifier.agentifier import reset_agentifier_flow

    if not n_clicks:
        return no_update, no_update
    if session.get("_stream_id"):
        return no_update, no_update
    session = dict(session or {})
    note = (note or "").strip() if isinstance(note, str) else ""
    prior = session.get("agentifier_retry_guidance") or {}
    prior_notes = [
        str(n).strip() for n in (prior.get("notes") or []) if str(n).strip()
    ]
    prior_history = [e for e in (prior.get("history") or []) if isinstance(e, dict)]
    rejected = [
        {
            "name": str(c.get("name", "")),
            "rough_description": str(c.get("rough_description", "")),
        }
        for c in (session.get("agentifier_scout_pool") or [])
        if isinstance(c, dict) and c.get("name")
    ]
    reset_agentifier_flow(session)
    session["agentifier_retry_guidance"] = {
        "notes": prior_notes + ([note] if note else []),
        "previous_candidates": rejected,
        "history": prior_history
        + [
            {
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "note": note or None,
                "rejected_candidates": rejected,
            }
        ],
    }
    messages = list(session.get("messages", []))
    user_text = "Try Again — draw a new set of candidates."
    if note:
        quoted = "\n".join(f"> {line}" for line in note.splitlines())
        user_text = f"{user_text}\n\n{quoted}"
    messages.append({"role": "user", "content": user_text})
    messages.append({"role": "assistant", "content": ""})
    gen = _get_agent_gen(None, session)
    stream_id = streaming.start(gen, session)
    return (
        {
            **session,
            "messages": messages,
            "_stream_id": stream_id,
            "_stream_error": None,
        },
        -1,
    )


@callback(
    Output("breadth-checkbox-group", "value"),
    Output("breadth-intent-store", "data"),
    Output({"type": "breadth-cb", "name": ALL}, "disabled"),
    Input("breadth-checkbox-group", "value"),
    State("breadth-intent-store", "data"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_breadth_change(value: Any, intent_store: Any, session: Any) -> Any:
    """Live panel closure: as the developer toggles a candidate, force-check and
    lock the producers a selected feature requires, and turn coordinators on/off
    by member count — mirroring the authoritative backend closure at submit.
    """
    if not session or not session.get("agentifier_breadth_groups"):
        return no_update, no_update, no_update
    if session.get("agentifier_breadth_chosen"):
        return no_update, no_update, no_update

    pool = pool_from_dicts(session.get("agentifier_scout_pool") or [])

    # Developer intent is tracked apart from the checkbox value, so a
    # force-checked producer can never mask or silently drop one the developer
    # picked independently. Reset to the panel's seed when the nonce changes.
    nonce = session.get("agentifier_breadth_nonce")
    store = intent_store if isinstance(intent_store, dict) else {}
    if store.get("nonce") != nonce:
        intent = set(session.get("agentifier_breadth_selection") or [])
    else:
        intent = set(store.get("intent") or [])

    # The displayed value before this event was closure(intent); only enabled
    # checkboxes can be toggled, so any difference is a genuine developer action.
    prev_display = close_selection(pool, intent).selected
    value_set = set(value or [])
    for name in value_set ^ prev_display:
        if name in value_set:
            intent.add(name)
        else:
            intent.discard(name)

    result = close_selection(pool, intent)
    disabled = [o["id"]["name"] in result.locked for o in ctx.outputs_list[2]]
    return (
        sorted(result.selected),
        {"nonce": nonce, "intent": sorted(intent)},
        disabled,
    )


# ---------------------------------------------------------------------------
# Chat — streaming poll
# ---------------------------------------------------------------------------


# D-ER2: stands in for a turn that produced no visible text at all. Deliberately
# does not claim anything about what was or wasn't saved — the poll cannot know,
# and the developer's next move is the same either way.
_EMPTY_TURN_NOTICE = (
    "_This step finished without producing a response — the model's reply "
    "either came back empty or could not be read. Nothing is lost; use Try "
    "Again below to re-run the step._"
)


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("stream-poll-interval", "max_intervals", allow_duplicate=True),
    Input("stream-poll-interval", "n_intervals"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_stream_poll(n: Any, session: Any) -> Any:
    stream_id = session.get("_stream_id")
    if not stream_id:
        return no_update, 0

    stream = streaming.get(stream_id)
    if not stream:
        if _DEV_MODE:
            print(
                f"[poll {stream_id[:8]}] stream entry missing — another poll already "
                f"finalised this stream; leaving authoritative session intact",
                flush=True,
            )
        # Entries are evicted at the next start(), not in the done branch, so a
        # missing entry means this stream was already finalised and the store's
        # _stream_id is already None (a later turn has begun or is about to).
        # Return no_update to avoid clobbering the authoritative session from our
        # stale State snapshot.
        return no_update, 0

    text = stream["text"]
    messages = list(session.get("messages", []))
    if messages:
        messages[-1] = {"role": "assistant", "content": text}
    # D-PH9: the phaser validation-retry drain yields no visible text, so the
    # displayed message freezes; the generator publishes a cumulative
    # received-character total on the live (agent-mutated) session instead.
    # Surface that scalar so the token counter keeps climbing during the drain,
    # and re-render when it advances even though the displayed text has not.
    received = stream["session"].get("_stream_received_chars")
    # The one-line status under the chat input rides the same live-session
    # channel as the received-chars scalar: agents overwrite it stage by stage,
    # and the poll surfaces the latest value mid-stream.
    status = stream["session"].get("_stream_status")

    if not stream["done"]:
        prev = (session.get("messages") or [{}])[-1].get("content", "")
        if (
            text == prev
            and received == session.get("_stream_received_chars")
            and status == session.get("_stream_status")
        ):
            return no_update, no_update
        updated = {**session, "messages": messages}
        updated["_stream_received_chars"] = received
        updated["_stream_status"] = status
        return updated, no_update

    # Stream complete — merge agent-mutated session and finalise
    if _DEV_MODE:
        print(
            f"[poll {stream_id[:8]}] done branch firing; text_len={len(text)}, "
            f"messages_count={len(messages)}, "
            f"last_msg_preview={text[:120]!r}",
            flush=True,
        )
    # Read (do NOT pop) the agent-mutated session from the live entry. Eviction
    # happens at the next start(); leaving the entry in place means two polls
    # racing into this branch both read the same authoritative session and return
    # a byte-identical terminal store — whichever Dash applies last, _stream_id
    # ends up None and the agent mutations survive. Sourcing from stream["session"]
    # (never the stale State snapshot) preserves the no-clobber guarantee.
    agent_session = stream["session"]
    # Claimed so it runs once even when two polls race into this branch. The
    # persist funnel drains the process-global usage sink, so a second run finds
    # it empty and clears the turn's token readout — the numbers vanish from the
    # chat row while the chars counter beside them stays. Both polls still return
    # the same terminal store, because the first run's mutations land on this
    # shared session dict.
    if streaming.claim_finalise(stream_id):
        try:
            _persist_artifacts(agent_session)
        except Exception as exc:  # a side effect — never strand the chat
            if _DEV_MODE:
                print(
                    f"[poll {stream_id[:8]}] _persist_artifacts failed "
                    f"({type(exc).__name__}: {exc}); finalising anyway",
                    flush=True,
                )
    elif _DEV_MODE:
        print(
            f"[poll {stream_id[:8]}] finalisation already claimed; "
            f"returning the same terminal store",
            flush=True,
        )
    if agent_session.get("_display_override") is not None and messages:
        messages[-1] = {
            "role": "assistant",
            "content": agent_session["_display_override"],
        }
        if _DEV_MODE:
            print(
                f"[poll {stream_id[:8]}] _display_override applied "
                f"(len={len(agent_session['_display_override'])})",
                flush=True,
            )
    # D-ER2: a finished turn whose assistant message is empty is never correct —
    # it renders as a blank bubble with no controls under it, which reads as the
    # app hanging. It happens when a generator returns without yielding and
    # without setting a display override: an artifact reply that was suppressed
    # on its way to the screen and then failed to parse takes exactly that path.
    # Agents fix their own causes; this is the last line of defence, and it
    # routes the turn into the same Try Again recovery a raised exception gets.
    empty_turn = bool(
        messages
        and messages[-1].get("role") == "assistant"
        and not (messages[-1].get("content") or "").strip()
    )
    if empty_turn:
        messages[-1] = {"role": "assistant", "content": _EMPTY_TURN_NOTICE}
        if _DEV_MODE:
            print(
                f"[poll {stream_id[:8]}] empty assistant turn — substituting "
                f"the notice and enabling retry",
                flush=True,
            )
    return (
        {
            **agent_session,
            "messages": messages,
            "_stream_id": None,
            "_initial_turn_done": True,
            "_display_override": None,
            "_stream_received_chars": None,
            "_stream_status": None,
            # D-ER1: the turn died and the error text is the whole assistant
            # message. Record that so the chat can offer Try Again; a clean
            # finish writes None here and retires any earlier failure.
            "_stream_error": True if (stream.get("error") or empty_turn) else None,
        },
        0,
    )


# ---------------------------------------------------------------------------
# Chat — navigation
# ---------------------------------------------------------------------------


def _switch_agent(
    session: dict[str, Any],
    target: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Switch active_agent and clear UI display state, preserving the target
    agent's conversation and artifact state.

    The recap helper (`_maybe_inject_resume_summary`) handles resumption when
    `{target}_messages` is non-empty, so navigating between agents picks up
    where the user left off rather than starting from scratch.
    """
    return {
        **session,
        "active_agent": target,
        "messages": [],
        "_initial_turn_done": False,
        # D-ER1: a failure belongs to the turn that produced it. Leaving the flag
        # set would put a Try Again button under the incoming agent's opening
        # turn, where it would retry something the user never saw fail.
        "_stream_error": None,
        **(extra or {}),
    }


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input({"type": "agent-pill", "agent": ALL}, "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_agent_pill_click(n_clicks_list: Any, session: Any) -> Any:
    """Pipeline pill click → navigate to that agent.

    Chat-view pills disable themselves on unmet preconditions, so this check is
    defensive there. The /agents buttons are enabled by `agent_button_state`,
    which is a separate authority and can diverge — when it does, the block is
    reported through `agent_select_error` rather than swallowed (D-BB2).
    """
    if not ctx.triggered_id or not any(n for n in n_clicks_list if n):
        return no_update, no_update
    target = ctx.triggered_id["agent"]
    session = session or {}
    if target == session.get("active_agent") and session.get("phase") == "chat":
        return no_update, no_update
    error = _validate_agent_preconditions(target, session)
    if error is not None:
        return {**session, "agent_select_error": error}, no_update
    # No connection, no turn. Entering an agent is what leads to a provider
    # request, so the check belongs here rather than at the point the request
    # is built, where nothing can be done about it but raise. The remembered
    # prefs are not consulted (see `llm_selection.is_connected`): a restored
    # session that has never connected reaches this with a status bar happily
    # naming the previous session's model, and sending it into chat produced a
    # `TypeError` from inside LiteLLM instead of the setup screen it needed.
    if not llm_selection.is_connected(session, target):
        return {**session, "phase": "setup", "agent_select_error": None}, "/setup"
    if target == "designer":
        return {
            **session,
            "phase": "designer",
            "agent_select_error": None,
        }, "/design"
    return _switch_agent(
        session, target, extra={"phase": "chat", "agent_select_error": None}
    ), "/chat"


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-project-mode-existing", "n_clicks"),
    Input("btn-project-mode-new", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_project_mode_choice(n_existing: Any, n_new: Any, session: Any) -> Any:
    """Record whether the working directory holds an existing project (D-PM1).

    Session-only: the answer is never persisted, so the next launch asks again.
    Clearing `agent_select_error` alongside it keeps a stale precondition
    message from surviving into the newly-revealed agent list.
    """
    if not ctx.triggered_id or not (n_existing or n_new):
        return no_update
    mode = (
        PROJECT_MODE_EXISTING
        if ctx.triggered_id == "btn-project-mode-existing"
        else PROJECT_MODE_NEW
    )
    return {**(session or {}), "project_mode": mode, "agent_select_error": None}


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-rescan-project", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_rescan_project(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return {
        **session,
        "code_scanner_messages": [],
        "code_scanner_state": STATE_IN_PROGRESS,
        "code_scanner_artifact_msg_count": None,
        "code_scanner_resumed": False,
        "messages": [],
        "_initial_turn_done": False,
        # D-ER1: the re-scan is a fresh turn, so a prior failure's Try Again
        # panel must not sit over it in the window before the turn starts.
        "_stream_error": None,
    }


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-review-to-brainstormer", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_review_to_brainstormer(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _switch_agent(session, "brainstormer")


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-brainstormer-to-designer", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_brainstormer_to_designer(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return {**session, "phase": "designer"}, "/design"


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-brainstormer-to-agentifier", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_brainstormer_to_agentifier(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return _switch_agent(session, "agentifier", extra={"phase": "chat"}), "/chat"


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-agentifier-to-designer", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_agentifier_to_designer(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return {**session, "phase": "designer"}, "/design"


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-stack-to-phaser", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_stack_to_phaser(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _switch_agent(session, "phaser")


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------


def _send_json(data: Any, filename: str) -> Any:
    return dcc.send_string(  # type: ignore[attr-defined, no-untyped-call]
        json.dumps(data or {}, indent=2), filename, type="application/json"
    )


def _build_phases_zip(session: dict[str, Any]) -> Any:
    phases = session.get("phases", [])
    version = session.get("phase_version") or 0
    # Same context bundle the on-disk save uses, so the downloaded phases carry
    # the identical verbatim spec preamble.
    context = {"ai_features": session.get("ai_features")}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for phase in phases:
            zf.writestr(
                f"v{version}/phases/phase{phase['phase_number']}.md",
                project_manager.render_phase_markdown(phase, context),
            )
    buf.seek(0)
    return dcc.send_bytes(buf.read(), "phases.zip")  # type: ignore[attr-defined, no-untyped-call]


@callback(
    Output("dl-vision", "data"),
    Input("btn-dl-vision", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_vision(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _send_json(session.get("vision_statement"), "vision.json")


@callback(
    Output("dl-stack", "data"),
    Input("btn-dl-stack", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_stack(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _send_json(session.get("stack_statement"), "stack.json")


@callback(
    Output("dl-code-review", "data"),
    Input("btn-dl-review", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_code_review(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _send_json(session.get("code_review"), "code_review.json")


@callback(
    Output("dl-features", "data"),
    Input("btn-dl-features", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_features(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _send_json(session.get("ai_features"), "ai_features.json")


@callback(
    Output("dl-phases", "data"),
    Input("btn-dl-phases", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_phases(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _build_phases_zip(session)


# ---------------------------------------------------------------------------
# Open in the Artifact View — the chat frame's other half of every Download
# ---------------------------------------------------------------------------


def _open_target(
    working_dir: Any, round_number: int | None, path: str
) -> str:
    """The path an Open button actually selects, resolved for this round.

    One artifact needs the indirection: ``phases/`` is a directory standing
    for many files, and ``allowed_artifacts`` expands it into the phase files
    that are on disk — so the directory itself is *not* in the allowed set once
    Phaser has written anything, and selecting it would land the developer on
    a rejection immediately after clicking Open on a finished Phaser run. The
    first phase file is what the tree draws first and is what the developer
    means by "open the phases".

    The expansion is read at click time, from the round the click resolved to,
    for the same reason the target is: a run that finished while the page was
    open has written phase files that were not there when the row rendered.

    Everything else falls through untouched, including a path that is not in
    the set at all — a round with nothing on disk yet resolves to
    allowed-but-missing, which names the agent that would produce the file,
    and that is a better answer than silently opening nothing.
    """
    if path != PHASES_DIR:
        return path
    allowed = allowed_artifacts(working_dir, round_number)
    if path in allowed:
        return path
    # Insertion order is `_phase_files`' order, which sorts phase10 after
    # phase9 — so this is the first phase, not the lexicographically first.
    return next((p for p in allowed if p.startswith(PHASES_DIR)), path)


def _register_open_artifact(key: str) -> Any:
    """Wire one Open button to the Artifact View, and hand the handler back.

    One callback per button rather than one taking all six as Inputs, because
    only the active agent's row is ever on screen: a single callback would
    reference five components that are not rendered, Dash would refuse to
    dispatch it, and the click would do nothing with no error anywhere — the
    exact half-rendered failure ``tests/test_callback_co_presence.py`` exists
    to catch. The Download buttons beside these are wired the same way for the
    same reason.

    The target is resolved from ``ctx.triggered_id`` — the button that was
    actually clicked, at the moment it was clicked — rather than from the
    ``key`` this closure was registered with. The two agree today; reading the
    trigger is what keeps them agreeing if the row is ever generated
    differently, and it is the same rule ``on_round_tree_line`` follows for the
    same failure: a round can change while the page is open, so nothing about
    the destination may be captured at render time.
    """

    @callback(
        Output("session", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Input(open_button_id(key), "n_clicks"),
        State("session", "data"),
        prevent_initial_call=True,
    )
    def on_open_artifact(n: Any, session: Any) -> Any:
        """A click on ``btn-open-<key>`` → that artifact, open in place."""
        if not n:
            return no_update, no_update
        triggered = ctx.triggered_id
        path = CHAT_ARTIFACTS.get(
            triggered[len(OPEN_BTN_PREFIX) :] if isinstance(triggered, str) else ""
        )
        if path is None:
            return no_update, no_update
        session = session or _default_session()
        working_dir = session.get("working_dir")
        round_number = (
            project_manager.active_version(working_dir, session)
            if working_dir
            else None
        )
        return (
            select_artifact(
                session, round_number, _open_target(working_dir, round_number, path)
            ),
            ARTIFACTS_PATH,
        )

    return on_open_artifact


# One handler per button, kept by key so the tests can call the one they mean.
# Registration happens at import, like every other callback in this module; the
# mapping is a by-product of it rather than a second source of truth.
OPEN_ARTIFACT_CALLBACKS: dict[str, Any] = {
    key: _register_open_artifact(key) for key in CHAT_ARTIFACTS
}


# ---------------------------------------------------------------------------
# Deployer navigation
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-phaser-to-deployer", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_phaser_to_deployer(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _switch_agent(session, "deployer")


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-deployer-new-project", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_deployer_new_project(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    fresh = _reset_for_new_project(session or {})
    fresh["phase"] = "working_dir"
    # Open the directory browser at home rather than letting the prefs-stored
    # previous-project path get auto-restored (which would land the developer
    # back on the project they just finished).
    fresh["browser_path"] = _HOME
    return fresh, "/dir"


@callback(
    Output("dl-deployment", "data"),
    Input("btn-dl-deployment", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_deployment(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    messages = session.get("deployer_messages") or []
    md = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "assistant"),
        "",
    )
    return dcc.send_string(md, "deployment-plan.md", type="text/markdown")  # type: ignore[attr-defined, no-untyped-call]
