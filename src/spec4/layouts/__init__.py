"""Every screen the app draws.

D-LR7 — the standing review gate for anything added here.

The look rework removed a fixed list of marketing-era elements: the
external-link drawer, the footer, the in-app landing page, the grid
background, kicker labels, gradient text, hero spacing, card hover effects,
button glows, and every emoji in the app. That list is not history; it is the
checklist a new component is reviewed against before it ships.

The rule the list is shorthand for: **if an element on screen is not a fact, a
command, an artifact, or a control, it does not ship.** A pictograph beside a
word is none of the four — the word already said it. A glow, a gradient or a
lift on hover is none of the four either; it decorates a control that was
already legible.

Three of these are enforced by `tests/test_visual_register.py` rather than by
review alone — no emoji anywhere under `src/spec4/`, no marketing-era
declaration in `v3.css`, and no accent colour named by a layout module. The
rest are the reviewer's job, because a checklist a machine can run is the part
that stops rotting and the part that stops being read.
"""

from __future__ import annotations

import pathlib
from typing import Any

from dash import dcc, html
import dash_mantine_components as dmc

from spec4 import project_manager
from spec4.app_constants import PROJECT_MODE_EXISTING, PROJECT_MODE_NEW
from spec4.layouts._agent_rows import (
    _AGENT_ROWS,
    _agent_action_button,
    _agent_rows,
    agent_row_id,
    agent_rows,
)
from spec4.layouts._artifact_view import _artifact_view_layout
from spec4.layouts._chat import _agent_status_bar, _chat_action_buttons, _chat_layout
from spec4.layouts._setup import _setup_layout
from spec4.layouts._shared import (
    _card,
    _error,
    _render_message,
    _reformat_inline_lists,
)
from spec4.layouts._round_cost import (
    _round_cost,
    round_cost_lines,
)
from spec4.layouts._round_tree import (
    LINE_TYPE,
    _round_tree,
    _round_tree_head,
    _round_tree_lines_children,
    line_id,
    rendered_tree_lines,
    round_tree_lines,
)
from spec4.layouts._status_bar import (
    STATUS_BAR_HEIGHT,
    STATUS_EMPTY,
    _status_bar,
    _status_context,
    _status_nav_class,
)

__all__ = [
    "_card",
    "_error",
    "_render_message",
    "_reformat_inline_lists",
    "STATUS_BAR_HEIGHT",
    "STATUS_EMPTY",
    "_AGENT_ROWS",
    "_agent_action_button",
    "_agent_rows",
    "agent_row_id",
    "agent_rows",
    "_round_cost",
    "round_cost_lines",
    "LINE_TYPE",
    "_round_tree",
    "_round_tree_head",
    "_round_tree_lines_children",
    "line_id",
    "rendered_tree_lines",
    "round_tree_lines",
    "_status_bar",
    "_status_context",
    "_status_nav_class",
    "_agent_status_bar",
    "_chat_action_buttons",
    "_chat_layout",
    "_setup_layout",
    "_working_dir_layout",
    "_agent_select_layout",
    "_artifact_view_layout",
]


# ---------------------------------------------------------------------------
# Working directory browser
# ---------------------------------------------------------------------------


def _working_dir_layout(session: dict[str, Any]) -> html.Div:
    """The directory picker, and one of the two destinations the root resolves to.

    ``dir_error`` is why it is on screen rather than the project view: the root
    was asked for a remembered directory that could not be opened, and the
    message names it. It sits above the browser, before the developer starts
    clicking, because it is the answer to "why am I not looking at my project".
    """
    browser_path = session.get("browser_path") or str(pathlib.Path.home())
    # One predicate for what is shown and what `on_dir_select` opens, so the
    # two can never name different directories.
    if not project_manager.directory_opens(browser_path):
        browser_path = str(pathlib.Path.home())
    current = pathlib.Path(browser_path)

    try:
        subdirs = sorted(
            d for d in current.iterdir() if d.is_dir() and not d.name.startswith(".")
        )
    except PermissionError:
        subdirs = []

    subdir_buttons = [
        dmc.Button(
            f"{d.name}",
            id={"type": "subdir-btn", "path": str(d)},
            variant="subtle",
            size="xs",
            fullWidth=True,
        )
        for d in subdirs[:30]
    ]

    dir_error = session.get("dir_error")

    return html.Div(
        [
            dmc.Title("Select Project Directory", order=3, mb="sm"),
            _error(dir_error) if dir_error else None,
            dmc.Text(
                "Where do you want to work? Spec4 needs a project directory. "
                "If you're starting a new project, the project directory will probably start out empty. "  # noqa: E501
                "If you're working on an existing project, Spec4 will review your current code using CodeScanner.",  # noqa: E501
                c="dimmed",
                mb="lg",
            ),
            _card(
                dmc.Text(
                    f"Current location: {current}",
                    size="lg",
                    mb="sm",
                    style={"color": "var(--mantine-color-dark-0)", "fontWeight": 400},
                ),
                dmc.Group(
                    [
                        dmc.Button(
                            "↑ Up",
                            id="btn-dir-up",
                            variant="outline",
                            color="gray",
                            size="sm",
                            disabled=(current == current.parent),
                        ),
                        dmc.Button(
                            "Select This Directory",
                            id="btn-dir-select",
                            size="sm",
                        ),
                    ],
                    mb="md",
                ),
                dmc.TextInput(
                    id="dir-path-input",
                    label="Or type a path directly:",
                    value=str(current),
                    mb="md",
                ),
                dmc.Accordion(
                    dmc.AccordionItem(
                        [
                            dmc.AccordionControl("Create a new subdirectory here"),
                            dmc.AccordionPanel(
                                dmc.Stack(
                                    [
                                        dmc.TextInput(
                                            id="new-folder-name",
                                            placeholder="Directory name",
                                        ),
                                        dmc.Button(
                                            "Create directory",
                                            id="btn-create-folder",
                                            variant="outline",
                                            size="sm",
                                        ),
                                    ],
                                    gap="xs",
                                )
                            ),
                        ],
                        value="create",
                    ),
                    mb="md",
                ),
                dmc.Text("Subdirectories:", fw=600, mb="xs"),
                dmc.SimpleGrid(cols=3, spacing="xs", children=subdir_buttons)
                if subdir_buttons
                else dmc.Text(
                    "(no subdirectories — you can select the current directory)",
                    size="sm",
                    c="dimmed",
                ),
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Agent select
# ---------------------------------------------------------------------------


def _project_mode_layout(session: dict[str, Any]) -> html.Div:
    """Ask whether the working directory holds a project we are modifying.

    Spec4 cannot tell a real codebase from a `uv init` skeleton by looking at
    the files, and guessing wrong sends the developer down the brownfield path
    (a CodeScanner nudge, Designer offering to reproduce a UI that is not
    theirs) for a project that does not exist yet. So we ask, and we ask once
    per session — the answer is never written to disk (D-PM1).

    This replaces the agent list rather than sitting above it: nothing on the
    page should be startable while the mode is undecided.
    """
    return html.Div(
        _card(
            dmc.Title("Is There an Existing Project Here?", order=3, mb="xs"),
            dcc.Markdown(
                "This directory already contains files, but that alone doesn't "
                "tell us much — it could be a project you're modifying, or just "
                "the skeleton a tool like `uv init` or `npm init` left behind.\n\n"
                "* **Existing project** — there's real code here to work with. "
                "Spec4 will start with CodeScanner so it understands what you "
                "already have.\n"
                "* **New project** — anything here is scaffolding, and you're "
                "building something new. Spec4 will start with Brainstormer.",
                style={
                    "color": "var(--mantine-color-dark-1)",
                    "marginBottom": "0.75rem",
                },
            ),
            dmc.Group(
                [
                    dmc.Button(
                        "Existing project",
                        id="btn-project-mode-existing",
                        n_clicks=0,
                    ),
                    dmc.Button(
                        "New project",
                        id="btn-project-mode-new",
                        n_clicks=0,
                        variant="outline",
                        color="gray",
                    ),
                ],
                gap="md",
            ),
            dmc.Text(
                "You'll be asked again next time you start Spec4, so nothing "
                "here is permanent.",
                size="xs",
                c="dimmed",
                mt="xs",
            ),
            p="xs",
        )
    )


def _agent_select_layout(session: dict[str, Any]) -> html.Div:
    if project_manager.needs_project_mode(session.get("working_dir"), session):
        return _project_mode_layout(session)

    vision_loaded = session.get("vision_statement") is not None
    stack_loaded = session.get("stack_statement") is not None
    phases_loaded = bool(session.get("phases"))
    error = session.get("agent_select_error")

    working_dir = session.get("working_dir")
    new_round = bool(working_dir) and project_manager.brownfield_new_round_pending(
        working_dir
    )
    version_dir = (
        project_manager.get_version_dir(
            working_dir, project_manager.active_version(working_dir, session)
        )
        if working_dir
        else None
    )
    review_in_spec4 = bool(version_dir and (version_dir / "code_review.json").exists())

    mock_loaded = bool(version_dir and (version_dir / "design" / "mock.html").exists())

    loaded_items = []
    if vision_loaded:
        loaded_items.append("vision.json")
    if stack_loaded:
        loaded_items.append("stack.json")
    if phases_loaded:
        loaded_items.append(f"phases/ ({len(session['phases'])} phases)")
    if mock_loaded:
        loaded_items.append("design/mock.html")

    round_number = (
        project_manager.active_version(working_dir, session) if working_dir else None
    )

    # The round tree comes first, directly under the status bar: what this
    # round has produced, before anything about what to run next. Its lines are
    # computed here for the first paint and recomputed from disk by
    # `on_round_tree` on every render after that (D-LR4).
    #
    # The agent table sits directly beneath it, and it is the whole of the
    # "what next" guidance now — the seven rows say what each agent produces
    # and what to do with it, so the prose that used to introduce them (and the
    # step numbers and one-line descriptions on the old cards) is gone rather
    # than restated above a table that already says it.
    # The round tree comes first, the agent table beneath it, and the round's
    # cost closes the block — produced, then to do, then spent, which is the
    # mock's order and the order the three questions actually occur in. The
    # strip's lines are recomputed from `usage.json` by `on_round_cost` on
    # every render, like the tree's (D-LR4).
    children = [
        # `linked=True`: every line opens the file it names in the Artifact
        # View. The tree is the app's index of the round, so the line a
        # developer is already reading is the natural way in — which is why
        # this is the same renderer the Artifact View draws, told to link,
        # rather than a project-view tree and an artifact-view tree.
        _round_tree(working_dir, round_number, linked=True),
        _agent_rows(working_dir, round_number, session),
        _round_cost(working_dir, round_number),
    ]

    if error:
        children.append(_error(error))

    if new_round:
        app_name = session.get("_prior_app_name")
        prior = (
            f"Your previous version of {app_name}"
            if app_name
            else "Your previous version"
        )
        children.append(
            dmc.Alert(
                f"{prior} has been implemented, and you may also have made "
                "additional changes yourself. You are now starting a new version, "
                "so you must begin by scanning your existing code with CodeScanner.",
                mb="xs",
            )
        )
    elif session.get("project_mode") == PROJECT_MODE_NEW:
        # D-PM1: the developer said this is a new project, so whatever is in
        # the directory is scaffolding. Same guidance as an empty directory.
        children.append(
            dmc.Alert(
                "You told us this is a new project, so Spec4 will treat anything "
                "already in the directory as scaffolding. CodeScanner is "
                "optional — feel free to skip ahead to Brainstormer.",
                mb="xs",
            )
        )
    elif session.get("project_mode") == PROJECT_MODE_EXISTING:
        children.append(
            dmc.Alert(
                "You told us there's an existing project here. "
                "Consider running CodeScanner first to help Spec4 understand the current state of your project.",  # noqa: E501
                color="yellow",
                mb="xs",
            )
        )
    elif working_dir and not project_manager.directory_has_content(working_dir):
        children.append(
            dmc.Alert(
                "Your project directory is empty. You can still run CodeScanner if you'd like, "  # noqa: E501
                "but it's optional — feel free to skip ahead to Brainstormer.",
                mb="xs",
            )
        )
    elif review_in_spec4:
        children.append(
            dmc.Alert(
                "This project directory appears to contain existing files. "
                "The previous code review has been loaded, but you might want to consider running "  # noqa: E501
                "CodeScanner again just to make sure that Spec4 understands the current state of your "  # noqa: E501
                "project. Purely optional.",
                color="yellow",
                mb="xs",
            )
        )

    if loaded_items and not new_round:
        children.append(
            dmc.Alert(
                f"Loaded from .spec4/: {', '.join(loaded_items)}",
                mb="xs",
            )
        )

    children.append(
        dmc.Group(
            [
                dmc.Button(
                    "Change model / provider",
                    id="btn-agent-change-provider",
                    variant="outline",
                    color="gray",
                    size="compact-sm",
                ),
            ],
            mt="xs",
        )
    )

    return html.Div(children)
