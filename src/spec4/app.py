from __future__ import annotations

import logging
from typing import Any

import dash
from dash import Input, Output, State, callback, dcc, html, no_update
import dash_mantine_components as dmc

from spec4 import __version__
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
        dcc.Store(id="session", storage_type="session", data=_default_session()),
        dcc.Store(id="prefs", storage_type="local", data={}),
        dcc.Store(id="_last_render", data=0),
        dcc.Store(id="image-support-store", storage_type="local", data=None),
        html.Div(id="_designer-fs-dummy", style={"display": "none"}),
        # Polling interval for streaming agent responses; enabled (max_intervals=-1)
        # while a stream is active, disabled (max_intervals=0) otherwise.
        dcc.Interval(id="stream-poll-interval", interval=500, max_intervals=0),
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

app.clientside_callback(  # type: ignore[no-untyped-call]
    """
    (function() {
        var _lastCount = 0;
        return function(bufferData) {
            if (!bufferData || !bufferData._debug_events) {
                _lastCount = 0;
                return window.dash_clientside.no_update;
            }
            var events = bufferData._debug_events;
            for (var i = _lastCount; i < events.length; i++) {
                console.log('[Designer]', events[i]);
            }
            _lastCount = events.length;
            return window.dash_clientside.no_update;
        };
    })()
    """,
    Output("_designer-fs-dummy", "children", allow_duplicate=True),
    Input("mock-stream-buffer", "data"),
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
    prevent_initial_call="initial_duplicate",
)
def render_page(session: Any, prefs: Any, render_count: Any, image_support: Any) -> Any:
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
        content = _setup_layout(session, prefs, image_support)
    elif phase == "agent_select":
        content = _agent_select_layout(session)
    elif phase == "chat":
        content = _chat_layout(session)
    elif phase == "designer":
        content = designer_layout(session)
    else:
        content = _landing_layout()
    return html.Div([content, _footer()]), (render_count or 0) + 1, new_session


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    import os
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        print(f"spec4 {__version__}")
        sys.exit(0)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    if os.environ.get("DASH_DEBUG", "").lower() == "true":
        import litellm

        litellm._turn_on_debug()  # type: ignore[attr-defined, no-untyped-call]
        print("[dev] litellm verbose debug enabled (DASH_DEBUG=true)", flush=True)
    print("Starting Spec4 AI — open http://localhost:8050 in your browser")
    app.run(host="0.0.0.0", port=8050, debug=False, dev_tools_ui=False, threaded=True)


if __name__ == "__main__":
    main()
