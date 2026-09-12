"""The status bar — the app's whole header.

A 40px monospace status line in place of the marketing header: wordmark, then
the working directory, the round, and the provider and model — with the effort
after the model when one is set — then the four nav links and the running
version. It is mounted once in the app shell (``app.layout``), so its ids are
shell ids and its callback can never be half-rendered.

The four values are not baked in here. ``status_bar`` renders the frame and
its own empty state; the callback in ``spec4.callbacks`` fills the context line
from the two browser stores every time either one changes, which is what stops
the bar showing a stale directory after the developer switches projects.

Two of the values are controls. The working directory reopens the picker
(``on_status_bar_dir``); the model — or the ``Not connected`` phrase in its
place — opens the setup wizard at its first step (``on_status_bar_setup``),
as the Settings nav item does. Neither commits anything: the picker leaves
the project as it was, and the wizard leaves the connection in place until a
new one is made. Both are drawn as the same text they were, with no chrome,
so the bar still reads as a status line.

The provider and model slots describe the project default on every screen
*except* the two that are about one agent — chat and Designer — where they
describe that agent's own resolution. The bar's job is to say what the next
turn will run on, and on those two screens the answer is the agent's override
whenever it has one. It is one resolution path either way:
``llm_selection.default_provider_model`` takes the agent key, and the no-op key
it defaults to is the same one that reads the default.
"""

from __future__ import annotations

from typing import Any

from dash import dcc, html

from spec4 import __version__, llm_selection
from spec4.app_constants import ROOT_PATH
from spec4.layouts._shared import _sep

__all__ = [
    "ARTIFACTS_PATH",
    "NAV_ORDER",
    "NOT_CONNECTED",
    "SLOT_CLASS",
    "SLOT_CONNECTION",
    "SLOT_MODEL",
    "SLOT_PATH",
    "SLOT_PROVIDER",
    "SLOT_ROUND",
    "SLOT_VERSION",
    "STATUS_BAR_HEIGHT",
    "STATUS_EMPTY",
    "_dir_field",
    "_model_field",
    "status_bar",
    "status_context",
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

# The Artifact View's route, named here so the nav entry and the routing table
# cannot drift apart — `PATH_TO_PHASE` is asserted against this constant rather
# than against a second copy of the string.
ARTIFACTS_PATH = "/artifacts"

# The primary navigation, in the order it renders. Declared as data as well as
# rendered, because the Artifact Links specification fixes the *order* — the
# Artifacts entry sits between Project and Settings — and an order that only
# exists inside a component tree is one a test has to reverse-engineer.
NAV_ORDER: tuple[str, ...] = ("Project", "Artifacts", "Settings", "Docs")

# D-LR10: the bar's five values are slots, and only the path one ever gives up
# space.
#
# The bar used to ellipsise as a single line: `.sb-ctx` carried `overflow:
# hidden` and `text-overflow: ellipsis`, so under width pressure the browser
# cut whatever sat at the *end* of it — the model, then the provider, then the
# round. Those three are short, fixed and the reason to look at the bar at all;
# the working directory is the one field that is arbitrarily long and the one
# whose middle nobody reads. So each value gets its own class here: everything
# wearing `SLOT_CLASS` is `flex: none` in the stylesheet and cannot be
# compressed, and `SLOT_PATH` alone is allowed to shrink.
#
# The path shortens from its *start*, because the project name is at the tail
# and is the half a developer identifies the bar by. That is done in CSS rather
# than by shortening the string in Python: how much room the path has is a
# function of the viewport, which the server does not know, and a fixed
# character budget computed here would either truncate a path that fitted or
# fail to truncate one that did not. The rule is `direction: rtl` scoped to
# this one slot — never to a parent, which would reverse the whole bar — and
# the path text is wrapped in `<bdi>` so the segments still read left to right
# (`/home/rcrowe/Spec4`, not `Spec4/rcrowe/home/`).
SLOT_CLASS = "sb-slot"
SLOT_PATH = "sb-slot--path"
SLOT_ROUND = "sb-slot--round"
SLOT_PROVIDER = "sb-slot--provider"
SLOT_MODEL = "sb-slot--model"
SLOT_CONNECTION = "sb-slot--connection"
SLOT_VERSION = "sb-slot--version"


def _slot(*names: str) -> str:
    """``sb-slot sb-slot--round`` — the base class plus this slot's own."""
    return " ".join((SLOT_CLASS, *names))


def _dir_field(working_dir: str | None) -> html.Button | html.Span:
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
        return html.Span(STATUS_EMPTY, className=_slot(SLOT_PATH))
    return html.Button(
        # The `<bdi>` is load-bearing, not decoration: `.sb-slot--path` sets
        # `direction: rtl` so the ellipsis lands at the front of the path
        # (D-LR10), and without an isolated left-to-right run inside it the
        # segments would render in reverse order.
        html.Bdi(working_dir),
        id="btn-status-bar-dir",
        n_clicks=0,
        title="Change project directory",
        className=f"sb-dir {_slot(SLOT_PATH)}",
    )


def _model_field(text: str, slot_name: str) -> html.Button:
    """The model slot — the second control on the line, and the same kind.

    The model name, or the ``Not connected`` phrase standing in for it, is the
    field a developer reads when a turn ran on the wrong model or could not
    run at all, so it is where the route to /setup belongs — as the path is
    the route to the picker. It wears ``.sb-dir`` for the same reason: no
    button chrome, the bar's own font and colour, a pointer and a hover
    underline as the whole affordance.

    Unlike the directory there is no empty state that stays plain text: with
    no connection there is *more* reason to open setup, not less, so the
    control is there from the unfilled bar onward under one id, whichever
    phrase it carries. Pressing it opens the wizard at Provider and nothing
    more — the model it names keeps running until a new one is chosen.
    ``slot_name`` is the layout class — ``SLOT_MODEL`` when
    a model is named, ``SLOT_CONNECTION`` when the phrase replaces both the
    provider and the model — so the D-LR10 slot tests still see the slot they
    expect.
    """
    return html.Button(
        text,
        id="btn-status-bar-model",
        n_clicks=0,
        title="Change model / provider",
        className=f"sb-dir {_slot(slot_name)}",
    )


def status_context(  # noqa: PLR0913  # the status-bar field set, one parameter per field
    working_dir: str | None,
    round_number: int | None,
    provider: str | None,
    model: str | None,
    connected: bool,
    effort: str = llm_selection.DEFAULT_EFFORT,
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

    ``model`` and ``effort`` are *not* always the project default's. On the
    chat and Designer routes the caller resolves them for the agent on screen,
    so the bar names the model the next turn will actually run on rather than a
    default that agent has overridden. ``connected`` stays scoped to the
    default, because it answers a different question — whether this session
    ever made a connection — and an override is not evidence of one.

    The effort is rendered as a suffix on the model, and only when it is a real
    level, by :func:`llm_selection.model_effort_display` — the same helper the
    model chip, the retry panel, the agent rows and the gate's Keep button
    call, so all five say the same thing about the same agent.

    The unfilled bar passes ``False``: a bar that has not yet been told
    anything must not imply a connection.
    """
    round_text = f"round v{round_number}" if round_number is not None else STATUS_EMPTY
    fields: list[Any] = [
        _dir_field(working_dir),
        html.Span(round_text, className=_slot(SLOT_ROUND)),
    ]
    if connected:
        fields.append(
            html.Span(provider or STATUS_EMPTY, className=_slot(SLOT_PROVIDER))
        )
        fields.append(
            _model_field(
                llm_selection.model_effort_display(model, effort) or STATUS_EMPTY,
                SLOT_MODEL,
            )
        )
    else:
        # One slot, not two, for the same reason it is one phrase: with no
        # connection there is no provider and no model to hold apart.
        fields.append(_model_field(NOT_CONNECTED, SLOT_CONNECTION))
    children: list[Any] = []
    for index, field in enumerate(fields):
        if index:
            children.append(_sep())
        children.append(field)
    return children


def _status_nav_class(active: bool) -> str:
    """The nav link's class — the active item is marked, the rest are not."""
    return "sb-nav-link sb-nav-link--active" if active else "sb-nav-link"


def status_bar() -> html.Div:
    """The application header: wordmark, context line, nav, version.

    Nav is exactly four items, in the order the Artifact Links specification
    fixes: ``Project``, ``Artifacts``, ``Settings``, ``Docs``. The first two
    are in-app routes and go through ``dcc.Link`` so they move the URL without
    a page reload, which is what ``on_browser_navigate`` turns into a phase
    change. ``Settings`` is a button: it opens the setup wizard at its first
    step, which is a session write and not a route (see the note beside it).
    ``Docs`` is the one external link.

    ``Artifacts`` sits between ``Project`` and ``Settings`` because that is
    where the register puts it, not where it happened to be added: the
    Artifact View is a second way of looking at the open project, and Settings
    is the app's own configuration. Every item is plain text carrying no
    ``color`` of its own (D-LR2) — the active one is marked by
    ``_status_nav_class``, and the accent it picks up is the Mantine theme
    primary.
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
                        status_context(None, None, None, None, False),
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
                        "Artifacts",
                        href=ARTIFACTS_PATH,
                        id="status-bar-nav-artifacts",
                        className=_status_nav_class(False),
                    ),
                    # A button, not a link: Settings opens the wizard at its
                    # first step, and the wizard branches on a session field
                    # rather than on the URL, so getting there means clearing
                    # that field — a `dcc.Link` to `/setup` would land on
                    # whichever step the session happened to be on. The write
                    # is `on_status_bar_setup`, shared with the model slot;
                    # it leaves the connection itself alone.
                    html.Button(
                        "Settings",
                        id="status-bar-nav-settings",
                        n_clicks=0,
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
                        className=f"sb-version mono {_slot(SLOT_VERSION)}",
                    ),
                ],
                className="sb-nav",
            ),
        ],
        id="status-bar",
        className="statusbar",
    )
