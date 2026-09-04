from __future__ import annotations

import logging
import os
from typing import Any

# Suppress litellm's startup warnings about optional AWS dependencies
# (botocore/Bedrock/SageMaker) that are not used by Spec4.  Must be set
# before litellm is first imported by any downstream module.
os.environ.setdefault("LITELLM_LOG", "ERROR")

import litellm as _litellm
_litellm.suppress_debug_info = True

import dash
from dash import Input, Output, State, callback, dcc, html, no_update
import dash_mantine_components as dmc

from spec4 import __version__, version_check
from spec4.app_constants import DARK_THEME, GOOGLE_FONTS
from spec4.session import _default_session, _load_working_dir
from spec4.layouts import (
    _footer,
    _nav_drawer,
    _landing_layout,
    _working_dir_layout,
    _setup_layout,
    _agent_select_layout,
    _chat_layout,
)
from spec4.layouts.designer import designer_layout

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = dash.Dash(
    __name__,
    suppress_callback_exceptions=True,
    title="Spec4 AI",
    external_stylesheets=[GOOGLE_FONTS],
)

app.index_string = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        <link rel="icon" type="image/svg+xml" href="/assets/favicon.svg">
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""
server = app.server  # expose Flask server for gunicorn

# ---------------------------------------------------------------------------
# URL / browser history
# ---------------------------------------------------------------------------


# Register all callbacks (must come after app is created)
import spec4.callbacks  # noqa: E402, F401
import spec4.callbacks.designer  # noqa: E402, F401

# ---------------------------------------------------------------------------
# Root layout
# ---------------------------------------------------------------------------

app.layout = dmc.MantineProvider(
    theme=DARK_THEME,
    forceColorScheme="dark",
    children=[
        dmc.NotificationContainer(),
        html.Div(id="notifications-container", style={"display": "none"}),
        # Blueprint grid background (sits behind everything)
        html.Div(id="blueprint-grid"),
        _nav_drawer(),
        dcc.Location(id="url", refresh=False),
        html.Div(id="_scroll-dummy", style={"display": "none"}),
        html.Div(id="_progress-dummy", style={"display": "none"}),
        html.Div(id="_progress-show-dummy", style={"display": "none"}),
        html.Div(id="_progress-probe-dummy", style={"display": "none"}),
        dcc.Store(id="session", storage_type="session", data=_default_session()),
        dcc.Store(id="prefs", storage_type="local", data={}),
        dcc.Store(id="_last_render", data=0),
        dcc.Store(id="image-support-store", storage_type="local", data=None),
        dcc.Store(id="tool-support-store", storage_type="local", data=None),
        # Live developer intent for the Agentifier breadth panel, kept distinct
        # from the checkbox value so panel closure can force-check/lock producers
        # without losing an independently-picked producer. Keyed by the panel's
        # breadth nonce so a new panel starts from a clean intent.
        dcc.Store(id="breadth-intent-store", data={}),
        # Wall-clock start of the in-flight stream, stamped client-side by the
        # elapsed-time ticker. Held outside `session` deliberately: the server
        # never reads it, and writing it into the session store would make every
        # tick a session mutation and re-render the page (D-SC-P2).
        dcc.Store(id="stream-start-ts", data=None),
        html.Div(id="_designer-fs-dummy", style={"display": "none"}),
        # Polling interval for streaming agent responses; enabled (max_intervals=-1)
        # while a stream is active, disabled (max_intervals=0) otherwise.
        dcc.Interval(id="stream-poll-interval", interval=500, max_intervals=0),
        # Fires once, shortly after page load, to run the PyPI version check
        # off the render path — the page never waits on the network. The
        # check itself is once-per-process (version_check caches).
        dcc.Interval(id="version-check-interval", interval=1500, max_intervals=1),
        # Once-per-browser-session guard for the upgrade dialog: flipped to
        # True the first time the dialog opens, so reloads within the same
        # tab don't re-nag. A new tab/session starts fresh.
        dcc.Store(id="version-notice-shown", storage_type="session", data=False),
        dmc.Modal(
            id="version-check-modal",
            title="A newer version of Spec4 is available",
            opened=False,
            styles={"content": {"border": "1px solid #ffffff"}},
        ),
        dmc.AppShell(
            children=[
                dmc.AppShellHeader(
                    dmc.Group(
                        [
                            dmc.Group(
                                [
                                    html.A(
                                        [
                                            html.Span("Spec", className="logo-spec"),
                                            html.Span("4", className="logo-4"),
                                            html.Span(" AI", className="logo-spec"),
                                        ],
                                        href="/",
                                        className="logo-text",
                                        style={"textDecoration": "none"},
                                    ),
                                    dmc.Text(
                                        "AI Project Planning for Developers",
                                        size="sm",
                                        c="dimmed",
                                        visibleFrom="sm",
                                    ),
                                    dmc.Text(
                                        __version__,
                                        size="sm",
                                        c="dimmed",
                                        visibleFrom="sm",
                                        style={"opacity": 0.5},
                                    ),
                                ],
                                gap="md",
                            ),
                            html.Button(
                                "☰",
                                id="nav-burger",
                                n_clicks=0,
                                style={
                                    "background": "none",
                                    "border": "none",
                                    "color": "var(--mantine-color-text)",
                                    "cursor": "pointer",
                                    "fontSize": "1.25rem",
                                    "lineHeight": 1,
                                    "padding": "4px 8px",
                                },
                            ),
                        ],
                        justify="space-between",
                        h="100%",
                        px="md",
                    ),
                ),
                dmc.AppShellMain(
                    dmc.Container(
                        html.Div(id="page-content"),
                        size="xl",
                        py="lg",
                    )
                ),
            ],
            header={"height": 56},
        ),
    ],
)


# ---------------------------------------------------------------------------
# Clientside callbacks
# ---------------------------------------------------------------------------

app.clientside_callback(  # type: ignore[no-untyped-call]
    """
    function(n) {
        requestAnimationFrame(function() {
            var el = document.getElementById('chat-scroll-area');
            if (!el) return;
            var bubbles = el.querySelectorAll('.chat-bubble-user');
            if (bubbles.length > 0) {
                var wrapper = bubbles[bubbles.length - 1].parentElement;
                var offset = wrapper.getBoundingClientRect().top - el.getBoundingClientRect().top + el.scrollTop;
                el.scrollTop = Math.max(0, offset);
            } else {
                el.scrollTop = 0;
            }
        });
        return window.dash_clientside.no_update;
    }
    """,
    Output("_scroll-dummy", "children"),
    Input("_last_render", "data"),
)

app.clientside_callback(  # type: ignore[no-untyped-call]
    """
    function(burger_clicks, close_clicks, overlay_clicks, current_class) {
        var ctx = dash_clientside.callback_context;
        if (!ctx.triggered || !ctx.triggered.length) return [window.dash_clientside.no_update, window.dash_clientside.no_update, window.dash_clientside.no_update];
        var prop = ctx.triggered[0].prop_id;
        var is_open = current_class && current_class.includes("--open");
        var new_open = (prop === 'nav-burger.n_clicks') ? !is_open : false;
        return [
            new_open ? "✕" : "☰",
            new_open ? "nav-drawer nav-drawer--open" : "nav-drawer",
            new_open ? "nav-overlay nav-overlay--open" : "nav-overlay"
        ];
    }
    """,
    Output("nav-burger", "children"),
    Output("nav-drawer", "className"),
    Output("nav-overlay", "className"),
    Input("nav-burger", "n_clicks"),
    Input("nav-close-btn", "n_clicks"),
    Input("nav-overlay", "n_clicks"),
    State("nav-drawer", "className"),
    prevent_initial_call=True,
)

app.clientside_callback(  # type: ignore[no-untyped-call]
    """
    function(n_clicks, n_submit, n_intervals) {
        var el = document.getElementById('chat-progress-container');
        if (el) el.style.display = 'block';
        return window.dash_clientside.no_update;
    }
    """,
    Output("_progress-show-dummy", "children"),
    Input("btn-chat-submit", "n_clicks"),
    Input("chat-input", "n_submit"),
    Input("init-turn-interval", "n_intervals"),
    prevent_initial_call=True,
)

app.clientside_callback(  # type: ignore[no-untyped-call]
    """
    function(render_n, session) {
        if (session && session._stream_id) return window.dash_clientside.no_update;
        var el = document.getElementById('chat-progress-container');
        if (el) el.style.display = 'none';
        var el2 = document.getElementById('setup-probe-progress-container');
        if (el2) el2.style.display = 'none';
        return window.dash_clientside.no_update;
    }
    """,
    Output("_progress-dummy", "children"),
    Input("_last_render", "data"),
    State("session", "data"),
    prevent_initial_call=True,
)

app.clientside_callback(  # type: ignore[no-untyped-call]
    """
    function(n_clicks) {
        var el = document.getElementById('setup-probe-progress-container');
        if (el) el.style.display = 'block';
        return window.dash_clientside.no_update;
    }
    """,
    Output("_progress-probe-dummy", "children"),
    Input("btn-setup-model-continue", "n_clicks"),
    prevent_initial_call=True,
)

# D-SC-P2: elapsed-time ticker for the in-flight stream.
#
# The long wait in an agent turn is the provider's prefill before the first
# token — no session state changes during it, so nothing server-side can
# re-render and the animated bar is the only sign of life. The poll interval
# keeps firing client-side even when its server callback returns no_update, so
# it doubles as a 500ms tick source here.
#
# `_last_render` is a second input purely to repaint: every page re-render
# recreates `chat-elapsed` with the server's empty children, which would blank
# the readout until the next tick.
app.clientside_callback(  # type: ignore[no-untyped-call]
    """
    function(n_intervals, render_n, session, start) {
        var el = document.getElementById('chat-elapsed');
        if (!session || !session._stream_id) {
            if (el) el.textContent = '';
            return start === null ? window.dash_clientside.no_update : null;
        }
        var now = Date.now();
        var began = start || now;
        var secs = Math.floor((now - began) / 1000);
        if (el) {
            el.textContent = secs < 60
                ? ('Elapsed: ' + secs + 's')
                : ('Elapsed: ' + Math.floor(secs / 60) + 'm ' + (secs % 60) + 's');
        }
        return start ? window.dash_clientside.no_update : began;
    }
    """,
    Output("stream-start-ts", "data"),
    Input("stream-poll-interval", "n_intervals"),
    Input("_last_render", "data"),
    State("session", "data"),
    State("stream-start-ts", "data"),
    prevent_initial_call=True,
)

app.clientside_callback(  # type: ignore[no-untyped-call]
    """
    function(n_clicks, store_data) {
        if (!n_clicks || !store_data || !store_data.mock_html) return window.dash_clientside.no_update;
        var blob = new Blob([store_data.mock_html], {type: 'text/html'});
        var url = URL.createObjectURL(blob);
        window.open(url, '_blank');
        return window.dash_clientside.no_update;
    }
    """,
    Output("_designer-fs-dummy", "children"),
    Input("mock-fullscreen-btn", "n_clicks"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)

# Step-5 progress paint. render_designer_step deliberately ignores plain
# buffer ticks (re-rendering the step subtree 4x/sec churned dash-renderer's
# paths map and could silently drop the completion delivery), so the bar and
# counter are poked into the DOM here instead.
app.clientside_callback(  # type: ignore[no-untyped-call]
    """
    function(buf) {
        var nu = window.dash_clientside.no_update;
        if (!buf || typeof buf.tokens !== 'number') return nu;
        var txt = document.getElementById('mock-token-count');
        if (txt) txt.textContent = 'Chars received: ' + buf.tokens;
        var bar = document.getElementById('mock-progress');
        if (bar) {
            var section = bar.querySelector('[class*="Progress-section"]')
                || bar.firstElementChild;
            if (section) section.style.width = (buf.progress || 0) + '%';
        }
        return nu;
    }
    """,
    Output("_designer-fs-dummy", "children", allow_duplicate=True),
    Input("mock-stream-buffer", "data"),
    prevent_initial_call=True,
)

# Redundant mock-completion delivery (see note 3 in on_mock_stream_poll).
# The server response's designer-session-store output is occasionally never
# applied by the browser while the buffer output of the same response keeps
# landing, so delivery ticks embed the step-6 store under buf.complete and
# this browser-side copy applies it. Guards: never fire once the user has
# moved off step 5 (a stale tick must not bounce a Refine click back to the
# preview), and never apply a payload from a superseded generation.
app.clientside_callback(  # type: ignore[no-untyped-call]
    """
    function(buf, store) {
        var nu = window.dash_clientside.no_update;
        if (!buf || !buf.complete || !store) return nu;
        if (store.step !== 5) return nu;
        if (store._gen_id !== buf.complete._gen_id) return nu;
        return buf.complete;
    }
    """,
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("mock-stream-buffer", "data"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Page render
# ---------------------------------------------------------------------------


@callback(
    Output("page-content", "children"),
    Output("_last_render", "data"),
    Output("session", "data", allow_duplicate=True),
    Input("session", "data"),
    Input("prefs", "data"),
    State("_last_render", "data"),
    State("image-support-store", "data"),
    State("tool-support-store", "data"),
    prevent_initial_call="initial_duplicate",
)
def render_page(session: Any, prefs: Any, render_count: Any, image_support: Any, tool_support: Any) -> Any:
    session = session or _default_session()
    prefs = prefs or {}

    # Restore working_dir from localStorage when starting a fresh browser session.
    # Returns a new session so the restored state is also persisted in sessionStorage.
    # Keep phase as "landing" so the home page still shows on restart.
    new_session = no_update
    if not session.get("working_dir") and prefs.get("working_dir"):
        session = _load_working_dir(prefs["working_dir"], session)
        session = {**session, "phase": "landing"}
        new_session = session

    phase = session.get("phase", "landing")
    if phase == "working_dir":
        # If a directory was previously saved, start the browser there.
        if prefs.get("working_dir") and not session.get("browser_path"):
            session = {**session, "browser_path": prefs["working_dir"]}
            new_session = session
        content = _working_dir_layout(session)
    elif phase == "setup":
        content = _setup_layout(session, prefs, image_support, tool_support)
    elif phase == "agent_select":
        content = _agent_select_layout(session)
    elif phase == "chat":
        content = _chat_layout(session, prefs)
    elif phase == "designer":
        content = designer_layout(session, prefs)
    else:
        content = _landing_layout()
    return html.Div([content, _footer()]), (render_count or 0) + 1, new_session


@callback(
    Output("version-check-modal", "opened"),
    Output("version-check-modal", "children"),
    Output("version-notice-shown", "data"),
    Input("version-check-interval", "n_intervals"),
    State("version-notice-shown", "data"),
    prevent_initial_call=True,
)
def on_version_check(_n: Any, already_shown: Any) -> Any:
    """Open the upgrade dialog when PyPI has a newer release than this one.

    Shown at most once per browser session (the version-notice-shown session
    store); the PyPI fetch behind it runs once per server process
    (version_check caches, and any failure reads as up-to-date). The modal
    closes itself client-side, like ff-info-modal.
    """
    if already_shown:
        return no_update, no_update, no_update
    info = version_check.check_for_update()
    if not info:
        return no_update, no_update, no_update
    body = dmc.Stack(
        [
            dmc.Text(
                f"You're running Spec4 {info['current']} — the latest release "
                f"is {info['latest']}. Upgrading is recommended.",
                size="sm",
            ),
            dmc.Text("If you installed from PyPI:", size="sm"),
            dmc.Code("uv tool upgrade spec4", block=True),
            dmc.Text("If you run from source:", size="sm"),
            dmc.Code("git pull && make install", block=True),
        ],
        gap="xs",
    )
    return True, body, True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"spec4 {__version__}")
        sys.exit(0)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    print("Starting Spec4 AI — open http://localhost:8050 in your browser")
    app.run(host="0.0.0.0", port=8050, debug=False, dev_tools_ui=False, threaded=True)


if __name__ == "__main__":
    main()
