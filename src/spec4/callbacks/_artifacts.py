"""The Artifact View and everything that reaches it: the round tree, the round
cost strip, the Download buttons, and the Open buttons beside them.

Split out of ``spec4.callbacks`` by cleanup Phase 4g. Every name is re-exported
from the package, so an importer may use either path.

``dl_deployment`` is here with the other five ``dl_*`` handlers rather than under
the Deployer-navigation banner it used to sit beside: it is a Download, and the
six are one concern.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from dash import ALL, Input, Output, State, callback, ctx, dcc, no_update

from spec4 import project_manager
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
from spec4.layouts._round_cost import round_cost_lines
from spec4.layouts._round_tree import (
    LINE_TYPE,
    PHASES_DIR,
    _round_tree_head,
    _round_tree_lines_children,
    rendered_tree_lines,
)
from spec4.layouts._status_bar import ARTIFACTS_PATH
from spec4.app_constants import (
    ARTIFACT_AI_FEATURES,
    ARTIFACT_CODE_REVIEW,
    ARTIFACT_STACK,
    ARTIFACT_VISION,
    PATH_TO_PHASE,
)
from spec4.session import default_session


# The phase the Artifact View draws under, read out of the routing table rather
# than typed again. The tree's click handler needs it to tell which screen the
# click came from, and a second literal `"artifacts"` here would be one a
# rename could leave behind.
_ARTIFACTS_PHASE = PATH_TO_PHASE[ARTIFACTS_PATH]


# ---------------------------------------------------------------------------
# Round tree
# ---------------------------------------------------------------------------


@callback(
    Output("round-tree-head", "children"),
    Output("round-tree-list", "children"),
    Input("round-tree", "id"),
    State("session", "data"),
)
def on_round_tree(_id: str, session: Any) -> tuple[str, list[Any]]:
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
def on_round_tree_line(n_clicks_list: list[int | None], session: Any) -> Any:
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
    session = session or default_session()
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
def on_artifact_round(n_clicks_list: list[int | None], session: Any) -> Any:
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
    session = session or default_session()
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
def on_artifact_pane(_id: str, session: Any) -> Any:
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
def on_artifact_download(n_clicks: int | None, session: Any) -> Any:
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
def on_round_cost(_id: str, session: Any) -> tuple[str, ...]:
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
def dl_vision(n: int | None, session: Any) -> Any:
    if not n:
        return no_update
    return _send_json(session.get("vision_statement"), ARTIFACT_VISION)


@callback(
    Output("dl-stack", "data"),
    Input("btn-dl-stack", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_stack(n: int | None, session: Any) -> Any:
    if not n:
        return no_update
    return _send_json(session.get("stack_statement"), ARTIFACT_STACK)


@callback(
    Output("dl-code-review", "data"),
    Input("btn-dl-review", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_code_review(n: int | None, session: Any) -> Any:
    if not n:
        return no_update
    return _send_json(session.get("code_review"), ARTIFACT_CODE_REVIEW)


@callback(
    Output("dl-features", "data"),
    Input("btn-dl-features", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_features(n: int | None, session: Any) -> Any:
    if not n:
        return no_update
    return _send_json(session.get("ai_features"), ARTIFACT_AI_FEATURES)


@callback(
    Output("dl-phases", "data"),
    Input("btn-dl-phases", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_phases(n: int | None, session: Any) -> Any:
    if not n:
        return no_update
    return _build_phases_zip(session)


@callback(
    Output("dl-deployment", "data"),
    Input("btn-dl-deployment", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_deployment(n: int | None, session: Any) -> Any:
    if not n:
        return no_update
    messages = session.get("deployer_messages") or []
    md = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "assistant"),
        "",
    )
    return dcc.send_string(md, "deployment-plan.md", type="text/markdown")  # type: ignore[attr-defined, no-untyped-call]


# ---------------------------------------------------------------------------
# Open in the Artifact View — the chat frame's other half of every Download
# ---------------------------------------------------------------------------


def _open_target(working_dir: str | None, round_number: int | None, path: str) -> str:
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
    def on_open_artifact(n: int | None, session: Any) -> Any:
        """A click on ``btn-open-<key>`` → that artifact, open in place."""
        if not n:
            return no_update, no_update
        triggered = ctx.triggered_id
        path = CHAT_ARTIFACTS.get(
            triggered[len(OPEN_BTN_PREFIX) :] if isinstance(triggered, str) else ""
        )
        if path is None:
            return no_update, no_update
        session = session or default_session()
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
