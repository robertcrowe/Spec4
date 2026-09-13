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

from dash import html
import dash_mantine_components as dmc

from spec4 import project_manager
from spec4.app_constants import (
    ARTIFACT_CODE_REVIEW,
    ARTIFACT_STACK,
    ARTIFACT_VISION,
    PROJECT_MODE_EXISTING,
    PROJECT_MODE_NEW,
)
from spec4.layouts._agent_rows import (
    ACTION_LABELS,
    _AGENT_ROWS,
    _agent_action_button,
    build_agent_rows,
    agent_row_id,
    agent_rows,
)
from spec4.layouts._artifact_view import artifact_view_layout
from spec4.layouts._chat import agent_status_bar, chat_action_buttons, chat_layout
from spec4.layouts._setup import setup_layout
from spec4.layouts._shared import (
    _card,
    _error,
    _render_message,
    _reformat_inline_lists,
    intro_disclosure,
)
from spec4.layouts._round_cost import (
    round_cost,
    round_cost_lines,
)
from spec4.layouts._round_tree import (
    LINE_TYPE,
    round_tree,
    _round_tree_head,
    _round_tree_lines_children,
    line_id,
    rendered_tree_lines,
    round_tree_lines,
)
from spec4.layouts._status_bar import (
    STATUS_BAR_HEIGHT,
    STATUS_EMPTY,
    status_bar,
    status_context,
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
    "build_agent_rows",
    "agent_row_id",
    "agent_rows",
    "round_cost",
    "round_cost_lines",
    "LINE_TYPE",
    "round_tree",
    "_round_tree_head",
    "_round_tree_lines_children",
    "line_id",
    "rendered_tree_lines",
    "round_tree_lines",
    "status_bar",
    "status_context",
    "_status_nav_class",
    "agent_status_bar",
    "chat_action_buttons",
    "chat_layout",
    "setup_layout",
    "working_dir_layout",
    "agent_select_layout",
    "artifact_view_layout",
    "PROJECT_INTRO_BODY_ID",
    "PROJECT_INTRO_TOGGLE_ID",
]


# ---------------------------------------------------------------------------
# Working directory browser
# ---------------------------------------------------------------------------


def working_dir_layout(session: dict[str, Any]) -> html.Div:
    """The directory picker, and one of the two destinations the root resolves to.

    ``dir_error`` is why it is on screen rather than the project view: the root
    was asked for a remembered directory that could not be opened, and the
    message names it. It sits above the browser, before the developer starts
    clicking, because it is the answer to "why am I not looking at my project".

    The screen is a file browser, so it is drawn as one: the path in monospace
    with Up beside it, the subdirectories one per line underneath in the same
    fixed-width type, the folder-creation option folded onto a single row with
    the field it needs, and Select as the one filled action. The paragraph that
    used to explain what a project directory is has gone with the rest of the
    marketing-era chrome (D-LR7) — the developer is being asked for a
    directory, and the path entry says that on its own.
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

    # One directory per line, and nothing about the line but its name. The id
    # is built exactly as it was — `on_subdir_click` matches on this pattern,
    # so the entries' *container* changed here and the entries themselves did
    # not. `.dir-line` truncates a long name in `v3.css`; a wrapped name would
    # break the one-per-line rhythm that makes the column scannable.
    subdir_buttons = [
        dmc.Button(
            f"{d.name}",
            id={"type": "subdir-btn", "path": str(d)},
            variant="subtle",
            size="xs",
            fullWidth=True,
            className="dir-line mono",
        )
        for d in subdirs[:30]
    ]

    dir_error = session.get("dir_error")

    return html.Div(
        [
            html.H2("Select project directory", className="screen-title"),
            _error(dir_error) if dir_error else None,
            dmc.Group(
                [
                    # `classNames` rather than `className`: Mantine sets the
                    # font on the `<input>` itself, so a class on the root
                    # would be inherited by everything except the one element
                    # whose type has to be fixed-width. This is the app's one
                    # monospace class either way (D-LR7).
                    dmc.TextInput(
                        id="dir-path-input",
                        value=str(current),
                        classNames={"input": "mono"},
                        **{"aria-label": "Directory path"},
                    ),
                    dmc.Button(
                        "Up",
                        id="btn-dir-up",
                        variant="outline",
                        size="compact-sm",
                        disabled=(current == current.parent),
                    ),
                ],
                gap="xs",
                wrap="nowrap",
                className="path-row",
            ),
            dmc.Stack(subdir_buttons, gap=0, className="dir-list")
            if subdir_buttons
            else html.Div(
                "No subdirectories here — this one can still be selected.",
                className="dim-line dir-list-empty",
            ),
            # One row, not a disclosure: the option and the name it needs are
            # the same decision, and an accordion made the developer open a
            # panel to find that out.
            dmc.Group(
                [
                    dmc.Button(
                        "Create folder",
                        id="btn-create-folder",
                        variant="outline",
                        size="compact-sm",
                    ),
                    dmc.TextInput(
                        id="new-folder-name",
                        placeholder="new-folder",
                        classNames={"input": "mono"},
                        **{"aria-label": "New folder name"},
                    ),
                ],
                gap="xs",
                wrap="nowrap",
                className="create-row",
            ),
            # The one filled action on the screen. Up and Create folder are
            # neutral outlines beside it — moves around the filesystem, not the
            # thing the screen is for. Nothing here names a colour: the
            # emphasis is the absence of a `variant` (D-LR2).
            dmc.Group(
                dmc.Button("Select this directory", id="btn-dir-select"),
                justify="flex-end",
                className="btn-row",
            ),
        ],
        className="picker-view",
    )


# ---------------------------------------------------------------------------
# Agent select
# ---------------------------------------------------------------------------


def _project_mode_layout(_session: dict[str, Any]) -> html.Div:
    """Ask whether the working directory holds a project we are modifying.

    Spec4 cannot tell a real codebase from a `uv init` skeleton by looking at
    the files, and guessing wrong sends the developer down the brownfield path
    (a CodeScanner nudge, Designer offering to reproduce a UI that is not
    theirs) for a project that does not exist yet. So we ask, and we ask once
    per session — the answer is never written to disk (D-PM1).

    This replaces the agent list rather than sitting above it: nothing on the
    page should be startable while the mode is undecided.

    Two dimmed lines and two buttons on one row. The question is a gate on the
    way to the project view, so it is asked at the size of a gate: what the
    ambiguity is, what each answer starts with, and that the answer is only
    good for this session. The bulleted explanation this replaced said the same
    three things at four times the height, in front of a developer who has to
    read it every session.

    Nothing here decides *when* the question appears — `needs_project_mode` and
    the session store do, and neither is touched by this function.
    """
    return html.Div(
        _card(
            html.H2("Is there an existing project here?", className="screen-title"),
            # Two lines, and they are two lines at the width this panel is
            # actually drawn at (`.mode-question`, 560px) rather than two
            # elements that wrap into four.
            html.Div(
                "This directory has files — a project you're modifying, or a "
                "uv init skeleton.",
                className="dim-line",
            ),
            html.Div(
                "Existing starts with CodeScanner, new with Brainstormer; "
                "asked again next session.",
                className="dim-line",
            ),
            # One filled, one outline: both are answers, but Existing is the
            # one a directory with files in it usually wants, and a row of two
            # equal buttons is a row with nothing to press first.
            dmc.Group(
                [
                    dmc.Button(
                        "Existing project",
                        id="btn-project-mode-existing",
                        n_clicks=0,
                        size="compact-sm",
                    ),
                    dmc.Button(
                        "New project",
                        id="btn-project-mode-new",
                        n_clicks=0,
                        variant="outline",
                        size="compact-sm",
                    ),
                ],
                gap="xs",
                className="mode-choices",
            ),
            p="xs",
        ),
        className="mode-question",
    )


# The project view's introduction (D-LR13): the text-label toggle and the
# `dmc.Collapse` it opens. Plain string ids — one of each on the screen, both
# addressed by `on_project_intro_toggle` — mounted only once a project is open,
# so neither the directory picker nor the project-mode question carries them.
PROJECT_INTRO_TOGGLE_ID = "project-intro-toggle"
PROJECT_INTRO_BODY_ID = "project-intro-body"

# The six action states in the order "How Spec4 works" explains them. Each
# note's lead word is `ACTION_LABELS[state]` rather than a retyped label, so
# the notes cannot name a button the table does not draw.
_PIPELINE_NOTE_STATES: tuple[str, ...] = (
    project_manager.AGENT_BTN_START,
    project_manager.AGENT_BTN_CONTINUE,
    project_manager.AGENT_BTN_MODIFY,
    project_manager.AGENT_BTN_NEEDS_UPDATE,
    project_manager.AGENT_BTN_NOT_READY,
    project_manager.AGENT_BTN_REQUIRED,
)


def _pipeline_intro() -> list[str | html.Span]:
    """The project view's one sentence of orientation (D-LR13).

    Full contrast, as Designer's line is: it is the page saying what it is,
    not reference material. The path is monospace like every other path the
    app prints.
    """
    return [
        "Seven agents, in order. Each reads what the ones before it wrote, and "
        "everything they write is a file under ",
        html.Span(".spec4/", className="mono"),
        " in this project.",
    ]


def _pipeline_notes() -> list[html.P | html.Ul]:
    """The body of "How Spec4 works", element for element (D-LR13).

    Reference material, so the renderer sets it at the dim-line weight. Bold
    names an action by the button's own label, the round's folder and the
    usage file are monospace, and Artifacts and Settings are the status bar's
    nav labels as it writes them.
    """
    glosses = (
        " — ready to run.",
        " — a conversation is in progress; pick it up where you left it.",
        " — the artifact exists and can be revised.",
        " — something upstream changed since this agent ran.",
        " — an input this agent needs hasn't been produced yet.",
        " — start here; the round can't proceed until this agent runs.",
    )
    return [
        html.P(
            "The table is the pipeline. Rows run top to bottom, and the button "
            "on each row is the one thing you can do with that agent right now:"
        ),
        # `strict`: six glosses for six states, and a count that differs is a
        # bug to raise on, not a state to drop without a word.
        html.Ul(
            [
                html.Li([html.Strong(ACTION_LABELS[state]), gloss])
                for state, gloss in zip(_PIPELINE_NOTE_STATES, glosses, strict=True)
            ]
        ),
        html.P(
            [
                "Each pass over the project is a round, kept in its own ",
                # `{N}` is the literal text the developer reads, not a format
                # placeholder: the round number is whichever round is open.
                html.Span(".spec4/v{N}/", className="mono"),
                " folder. When a round has been implemented, the next one "
                "starts with CodeScanner, so the plan is made against the code "
                "as it was actually built — not against the previous plan.",
            ]
        ),
        html.P(
            [
                "The cost strip is this round's estimated spend, from ",
                html.Span("usage.json", className="mono"),
                "; your provider's bill is authoritative. The round tree below "
                "it lists every artifact, and each line opens that file in "
                "Artifacts.",
            ]
        ),
        html.P(
            "Settings sets the project's default model. Each agent's gate can "
            "override it for that agent alone."
        ),
    ]


def agent_select_layout(session: dict[str, Any]) -> html.Div:
    if project_manager.needs_project_mode(session.get("working_dir"), session):
        return _project_mode_layout(session)

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
    review_in_spec4 = bool(
        version_dir and (version_dir / ARTIFACT_CODE_REVIEW).exists()
    )

    mock_loaded = bool(version_dir and (version_dir / "design" / "mock.html").exists())

    loaded_items = _agent_select_loaded_items(session, mock_loaded)

    round_number = (
        project_manager.active_version(working_dir, session) if working_dir else None
    )

    # D-LR13: the pipeline's one sentence of orientation stands above
    # everything else on the view, with "How Spec4 works" under it — what the
    # table's six buttons mean, what a round is, where the cost strip reads
    # from and where the tree's lines lead. The notes sit closed because the
    # table is in front of them: they are there to be opened, not read on the
    # way past. The block is `_shared.intro_disclosure`, the renderer
    # Designer's introduction uses (D-LR12), so the two cannot drift. D-LR11's
    # order below it is untouched — controls, cost, record — and the
    # orientation line now stands above all three.
    #
    # D-LR11: the controls precede the record. The agent table comes first of
    # the three, directly under that introduction — the project view is
    # opened to run something, so the seven rows and their one action each
    # are what the screen leads with. The round's cost sits between: it is
    # what the last run cost, and it belongs beside the control that will
    # spend again rather than at the foot of the page. The tree closes the
    # stack, with its lane legend under it — it is the record of what the
    # round has produced, read after deciding what to do, not before.
    #
    # This replaces the earlier produced-then-to-do-then-spent order (tree,
    # rows, cost). Only the order changed: all three surfaces keep their
    # renderers, ids, and status computation.
    #
    # The agent table is the whole of the "what next" guidance — the seven rows
    # say what each agent produces and what to do with it, so the prose that
    # used to introduce them (and the step numbers and one-line descriptions on
    # the old cards) is gone rather than restated above a table that already
    # says it. D-LR13's introduction does not restate it either: it says what
    # the table's buttons mean, closed until asked, not what to press.
    #
    # None of the three is cached. Each is computed here for the first paint
    # and recomputed from disk on every render after that (D-LR4): the rows
    # from `agent_button_state` and `usage.json`, the strip from `usage.json`
    # by `on_round_cost`, the tree from project_manager's dependency graph by
    # `on_round_tree`.
    children = [
        intro_disclosure(
            _pipeline_intro(),
            "How Spec4 works",
            _pipeline_notes(),
            toggle_id=PROJECT_INTRO_TOGGLE_ID,
            body_id=PROJECT_INTRO_BODY_ID,
        ),
        build_agent_rows(working_dir, round_number, session),
        round_cost(working_dir, round_number),
        # `linked=True`: every line opens the file it names in the Artifact
        # View. The tree is the app's index of the round, so the line a
        # developer is already reading is the natural way in — which is why
        # this is the same renderer the Artifact View draws, told to link,
        # rather than a project-view tree and an artifact-view tree.
        round_tree(working_dir, round_number, linked=True),
    ]

    if error:
        children.append(_error(error))

    _append_new_round_children(children, session, new_round, review_in_spec4)

    _append_loaded_children(children, loaded_items, new_round)

    # The "Change model / provider" button that closed this view is gone: the
    # status bar's model slot and Settings item are the same route, on every
    # screen, so a page-level copy was one more control to keep in agreement.

    return html.Div(children)


def _agent_select_loaded_items(session: dict[str, Any], mock_loaded: bool) -> list[str]:
    """The already-loaded artifact names, in pipeline order."""
    vision_loaded = session.get("vision_statement") is not None
    stack_loaded = session.get("stack_statement") is not None
    phases_loaded = bool(session.get("phases"))
    loaded_items = []
    if vision_loaded:
        loaded_items.append(ARTIFACT_VISION)
    if stack_loaded:
        loaded_items.append(ARTIFACT_STACK)
    if phases_loaded:
        loaded_items.append(f"phases/ ({len(session['phases'])} phases)")
    if mock_loaded:
        loaded_items.append("design/mock.html")
    return loaded_items


def _append_new_round_children(
    children: list[Any],
    session: dict[str, Any],
    new_round: bool,
    review_in_spec4: bool,
) -> None:
    """The new-round block: what a fresh round carries forward and what it rescans."""
    working_dir = session.get("working_dir")
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


def _append_loaded_children(
    children: list[Any], loaded_items: list[str], new_round: bool
) -> None:
    """The already-loaded summary, shown only outside a new round."""
    if loaded_items and not new_round:
        children.append(
            dmc.Alert(
                f"Loaded from .spec4/: {', '.join(loaded_items)}",
                mb="xs",
            )
        )
