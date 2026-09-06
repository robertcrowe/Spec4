"""The status bar — the app's whole header.

A 40px monospace status line in place of the marketing header: wordmark, then
the working directory, the round, and the default provider and model, then the
three nav links and the running version. It is mounted once in the app shell
(``app.layout``), so its ids are shell ids and its callback can never be
half-rendered.

The four values are not baked in here. ``_status_bar`` renders the frame and
its own empty state; the callback in ``spec4.callbacks`` fills the context line
from the two browser stores every time either one changes, which is what stops
the bar showing a stale directory after the developer switches projects.
"""

from __future__ import annotations

from typing import Any

from dash import dcc, html

from spec4 import __version__
from spec4.app_constants import ROOT_PATH

__all__ = [
    "NOT_CONNECTED",
    "STATUS_BAR_HEIGHT",
    "STATUS_EMPTY",
    "_dir_field",
    "_status_bar",
    "_status_context",
    "_status_nav_class",
]

# The bar's height, in px. Shared with the AppShell header so the two cannot
# drift and leave the status line clipped or floating.
STATUS_BAR_HEIGHT = 40

# What a field renders as when its value is not available — a project opened
# before /setup has run has no provider, and no project at all has no
# directory. An em dash reads as "nothing here yet"; a blank reads as a bug.
STATUS_EMPTY = "—"

# What the provider and model fields collapse to when this session has no LLM
# connection. It replaces both, because the two are halves of one fact — which
# model a turn will run on — and when there is no connection neither half has
# an answer. Showing a remembered provider and model here instead is what let a
# restored session look ready to run when no agent could actually start.
NOT_CONNECTED = "Not connected"

# The one external link in the app.
DOCS_URL = "https://spec4.ai/docs"


def _sep() -> Any:
    """The dimmed ``·`` between two context fields."""
    return html.Span("·", className="sb-sep")


def _dir_field(working_dir: str | None) -> Any:
    """The working directory field — a control, not a label.

    The path *is* the button: on a bar this dense there is no room for a
    separate "change project" affordance, and the directory is the one field a
    developer has a reason to act on. It carries none of a button's usual
    chrome (that is `.sb-dir` in the stylesheet: inherited font and colour, no
    border, no accent, pointer cursor) so the bar still reads as a status line
    rather than a toolbar.

    With no directory there is nothing to reopen *at*, so the empty state stays
    plain text — a button whose whole label is an em dash would be a control
    with no object. That is also why the id is absent from the unfilled bar,
    and why the co-presence guard treats it as a shell id filled in by
    ``on_status_bar`` rather than as page content.
    """
    if not working_dir:
        return html.Span(STATUS_EMPTY)
    return html.Button(
        working_dir,
        id="btn-status-bar-dir",
        n_clicks=0,
        title="Change project directory",
        className="sb-dir",
    )


def _status_context(
    working_dir: str | None,
    round_number: int | None,
    provider: str | None,
    model: str | None,
    connected: bool,
) -> list[Any]:
    """``dir · round vN · provider · model``, with each field's empty state.

    Returned as the children of ``status-bar-context`` by both the initial
    render and the callback, so an unfilled bar and a filled one agree about
    what they are saying.

    ``connected`` is not derived from ``provider`` and ``model`` being present,
    and that distinction is the whole point. Those two can be filled from the
    remembered prefs — which are what /setup *prefills from*, not evidence that
    a connection was ever made — so a bar that inferred a connection from them
    reported a working model for a session that had none. The caller asks
    ``llm_selection`` the same question an agent turn asks, and the answer, not
    the leftovers, decides what is drawn.

    The unfilled bar passes ``False``: a bar that has not yet been told
    anything must not imply a connection.
    """
    round_text = f"round v{round_number}" if round_number is not None else STATUS_EMPTY
    fields: list[Any] = [
        _dir_field(working_dir),
        html.Span(round_text),
    ]
    if connected:
        fields.append(html.Span(provider or STATUS_EMPTY))
        fields.append(html.Span(model or STATUS_EMPTY))
    else:
        fields.append(html.Span(NOT_CONNECTED))
    children: list[Any] = []
    for index, field in enumerate(fields):
        if index:
            children.append(_sep())
        children.append(field)
    return children


def _status_nav_class(active: bool) -> str:
    """The nav link's class — the active item is marked, the rest are not."""
    return "sb-nav-link sb-nav-link--active" if active else "sb-nav-link"


def _status_bar() -> html.Div:
    """The application header: wordmark, context line, nav, version.

    Nav is exactly three items. ``Project`` and ``Settings`` are in-app routes
    and go through ``dcc.Link`` so they move the URL without a page reload,
    which is what ``on_browser_navigate`` turns into a phase change; ``Docs``
    is the one external link. There is deliberately no Artifacts item and no
    disabled placeholder for one — the Artifact View arrives in v1.
    """
    return html.Div(
        [
            html.Div(
                [
                    html.A(
                        [
                            html.Span("Spec", className="logo-spec"),
                            html.Span("4", className="logo-4"),
                        ],
                        href=ROOT_PATH,
                        className="wordmark",
                    ),
                    html.Span(
                        _status_context(None, None, None, None, False),
                        id="status-bar-context",
                        className="sb-ctx mono",
                    ),
                ],
                className="sb-left",
            ),
            html.Nav(
                [
                    dcc.Link(
                        "Project",
                        href="/agents",
                        id="status-bar-nav-project",
                        className=_status_nav_class(True),
                    ),
                    dcc.Link(
                        "Settings",
                        href="/setup",
                        id="status-bar-nav-settings",
                        className=_status_nav_class(False),
                    ),
                    html.A(
                        "Docs",
                        href=DOCS_URL,
                        target="_blank",
                        rel="noopener",
                        id="status-bar-nav-docs",
                        className=_status_nav_class(False),
                    ),
                    html.Span(
                        __version__,
                        id="status-bar-version",
                        className="sb-version mono",
                    ),
                ],
                className="sb-nav",
            ),
        ],
        id="status-bar",
        className="statusbar",
    )
