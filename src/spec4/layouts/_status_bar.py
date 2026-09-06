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
    "STATUS_BAR_HEIGHT",
    "STATUS_EMPTY",
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

# The one external link in the app.
DOCS_URL = "https://spec4.ai/docs"


def _sep() -> Any:
    """The dimmed ``·`` between two context fields."""
    return html.Span("·", className="sb-sep")


def _status_context(
    working_dir: str | None,
    round_number: int | None,
    provider: str | None,
    model: str | None,
) -> list[Any]:
    """``dir · round vN · provider · model``, with each field's empty state.

    Returned as the children of ``status-bar-context`` by both the initial
    render and the callback, so an unfilled bar and a filled one are the same
    shape and never jump.
    """
    round_text = f"round v{round_number}" if round_number is not None else STATUS_EMPTY
    fields = [
        working_dir or STATUS_EMPTY,
        round_text,
        provider or STATUS_EMPTY,
        model or STATUS_EMPTY,
    ]
    children: list[Any] = []
    for index, field in enumerate(fields):
        if index:
            children.append(_sep())
        children.append(html.Span(field))
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
                        _status_context(None, None, None, None),
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
