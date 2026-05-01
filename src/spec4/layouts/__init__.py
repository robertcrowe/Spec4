from __future__ import annotations

import pathlib
from typing import Any

from dash import dcc, html
import dash_mantine_components as dmc

from spec4.layouts._chat import _agent_status_bar, _chat_action_buttons, _chat_layout
from spec4.layouts._done import _done_layout
from spec4.layouts._setup import _setup_layout
from spec4.layouts._shared import (
    _card,
    _error,
    _feature_card,
    _footer,
    _nav_drawer,
    _render_message,
    _reformat_inline_lists,
)

__all__ = [
    "_card",
    "_error",
    "_feature_card",
    "_footer",
    "_nav_drawer",
    "_render_message",
    "_reformat_inline_lists",
    "_agent_status_bar",
    "_chat_action_buttons",
    "_chat_layout",
    "_done_layout",
    "_setup_layout",
    "_landing_layout",
    "_working_dir_layout",
    "_agent_select_layout",
]


# ---------------------------------------------------------------------------
# Landing
# ---------------------------------------------------------------------------


def _landing_layout() -> html.Div:
    return html.Div(
        [
            # Hero section
            html.Div(
                [
                    # Badge
                    html.Div(
                        [
                            html.Span(className="badge-dot"),
                            html.Span("Spec-Driven AI Development for Developers"),
                        ],
                        className="hero-badge",
                    ),
                    # Title
                    html.H1(
                        [
                            "From idea to ",
                            html.Span("executable phases", className="text-gradient"),
                        ],
                        style={
                            "fontSize": "clamp(2.25rem, 5vw, 3.5rem)",
                            "fontWeight": 700,
                            "lineHeight": 1.1,
                            "letterSpacing": "-0.03em",
                            "marginBottom": "1.25rem",
                            "color": "var(--mantine-color-dark-0)",
                        },
                    ),
                    # Subtitle
                    dmc.Text(
                        "A pipeline of specialised LLM agents guides you from a rough idea to "  # noqa: E501
                        "a set of structured, ordered development phases — ready to hand off to "  # noqa: E501
                        "Claude Code, Cursor, or any AI coding agent.",
                        size="lg",
                        c="dimmed",
                        style={
                            "maxWidth": "600px",
                            "lineHeight": 1.7,
                            "margin": "0 auto 0.5rem",
                        },
                    ),
                    dmc.Text(
                        ["It's way more powerful than ", html.Code("/plan"), "."],
                        size="lg",
                        c="blue.5",
                        style={"maxWidth": "600px", "margin": "0 auto 1.5rem"},
                    ),
                    # CTA
                    dmc.Button(
                        "Get Started →",
                        id="btn-landing-start",
                        size="lg",
                        mb="md",
                        style={"fontWeight": 600},
                    ),
                ],
                style={
                    "textAlign": "center",
                    "paddingTop": "2rem",
                    "paddingBottom": "1rem",
                },
            ),
            # Divider with section label
            dmc.Divider(mb="md"),
            html.Div(
                "The Pipeline",
                className="section-label",
                style={"display": "block", "textAlign": "center"},
            ),
            # Agent feature cards
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 2, "lg": 4},
                spacing="md",
                mb="xl",
                children=[
                    html.A(
                        _feature_card(
                            dmc.Group(
                                [
                                    dmc.Title("🔍 CodeScanner", order=4),
                                    dmc.Text("(optional)", size="xs", c="dimmed"),
                                ],
                                gap="xs",
                                align="center",
                                mb="xs",
                            ),
                            dmc.Text(
                                "Analyzes an existing project directory to understand its architecture, "  # noqa: E501
                                "technology stack, and coding style.",
                                size="sm",
                                mb="md",
                                c="dimmed",
                            ),
                            html.Span("code_review.json", className="output-badge"),
                        ),
                        href="https://spec4.ai/agents/reviewer/",
                        target="_blank",
                        style={"textDecoration": "none", "color": "inherit"},
                    ),
                    html.A(
                        _feature_card(
                            dmc.Title("🧠 Brainstormer", order=4, mb="sm"),
                            dmc.Text(
                                "Develops a clear project vision through focused questions. "  # noqa: E501
                                "Identifies technical standards via web search.",
                                size="sm",
                                mb="md",
                                c="dimmed",
                            ),
                            html.Span("vision.json", className="output-badge"),
                        ),
                        href="https://spec4.ai/agents/brainstormer/",
                        target="_blank",
                        style={"textDecoration": "none", "color": "inherit"},
                    ),
                    html.A(
                        _feature_card(
                            dmc.Title("⚙️ StackAdvisor", order=4, mb="sm"),
                            dmc.Text(
                                "Recommends languages, frameworks, hosting, and infrastructure. "  # noqa: E501
                                "Compares options and explains trade-offs.",
                                size="sm",
                                mb="md",
                                c="dimmed",
                            ),
                            html.Span("stack.json", className="output-badge"),
                        ),
                        href="https://spec4.ai/agents/stackadvisor/",
                        target="_blank",
                        style={"textDecoration": "none", "color": "inherit"},
                    ),
                    html.A(
                        _feature_card(
                            dmc.Title("📋 Phaser", order=4, mb="sm"),
                            dmc.Text(
                                "Decomposes your vision and stack into ordered, executable development phases. "  # noqa: E501
                                "Phase 1 is always a steel thread.",
                                size="sm",
                                mb="md",
                                c="dimmed",
                            ),
                            html.Span("phases.zip", className="output-badge"),
                        ),
                        href="https://spec4.ai/agents/phaser/",
                        target="_blank",
                        style={"textDecoration": "none", "color": "inherit"},
                    ),
                ],
            ),
            dmc.Divider(mb="md"),
            dmc.Text(
                "You can start at any stage. StackAdvisor requires a saved vision; "
                "Phaser requires both a vision and a stack.",
                size="lg",
                mb="lg",
                ta="center",
                style={"color": "var(--mantine-color-dark-0)", "fontWeight": 400},
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Working directory browser
# ---------------------------------------------------------------------------


def _working_dir_layout(session: dict[str, Any]) -> html.Div:
    browser_path = session.get("browser_path") or str(pathlib.Path.home())
    current = pathlib.Path(browser_path)
    if not current.exists():
        current = pathlib.Path.home()

    try:
        subdirs = sorted(
            d for d in current.iterdir() if d.is_dir() and not d.name.startswith(".")
        )
    except PermissionError:
        subdirs = []

    subdir_buttons = [
        dmc.Button(
            f"📁 {d.name}",
            id={"type": "subdir-btn", "path": str(d)},
            variant="subtle",
            size="xs",
            fullWidth=True,
        )
        for d in subdirs[:30]
    ]

    return html.Div(
        [
            dmc.Title("Select Project Directory", order=3, mb="sm"),
            dmc.Text(
                "Where do you want to work? Spec4 needs a project directory. "
                "If you're starting a new project, the project directory will probably start out empty. "  # noqa: E501
                "If you're working on an existing project, Spec4 will review your current code using the Reviewer.",  # noqa: E501
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
                            "✓ Select This Directory",
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
                            dmc.AccordionControl("📁 Create a new subdirectory here"),
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


def _agent_select_layout(session: dict[str, Any]) -> html.Div:
    vision_loaded = session.get("vision_statement") is not None
    stack_loaded = session.get("stack_statement") is not None
    phases_loaded = bool(session.get("phases"))
    error = session.get("agent_select_error")

    working_dir = session.get("working_dir")
    spec4_dir = pathlib.Path(working_dir) / ".spec4" if working_dir else None
    vision_in_spec4 = bool(spec4_dir and (spec4_dir / "vision.json").exists())
    stack_in_spec4 = bool(spec4_dir and (spec4_dir / "stack.json").exists())
    review_in_spec4 = bool(spec4_dir and (spec4_dir / "code_review.json").exists())

    loaded_items = []
    if vision_loaded:
        loaded_items.append("vision.json")
    if stack_loaded:
        loaded_items.append("stack.json")
    if phases_loaded:
        loaded_items.append(f"phases/ ({len(session['phases'])} phases)")

    children = [
        dmc.Title("Where Should We Begin?", order=3, mb="sm"),
        dcc.Markdown(
            "If you're just starting to work on your plan you should probably begin with either "  # noqa: E501
            "CodeScanner or Brainstormer.\n\n"
            "* Start with **CodeScanner** if you're modifying an existing project, so that Spec4 can "  # noqa: E501
            "understand the current state of your code.\n"
            "* Start with **Brainstormer** if you're starting an entirely new project, and Spec4 "  # noqa: E501
            "will help you refine and complete your vision.",
            style={"color": "var(--mantine-color-dark-1)", "marginBottom": "1.5rem"},
        ),
    ]

    if session.get("_warn_existing_content"):
        children.append(
            dmc.Alert(
                "This project directory appears to contain existing files. "
                "Consider running CodeScanner first to help Spec4 understand the current state of your project.",  # noqa: E501
                color="yellow",
                mb="md",
            )
        )
    elif working_dir and not session.get("_dir_has_content"):
        children.append(
            dmc.Alert(
                "Your project directory is empty. You can still run CodeScanner if you'd like, "  # noqa: E501
                "but it's optional — feel free to skip ahead to Brainstormer.",
                color="blue",
                mb="md",
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
                mb="md",
            )
        )

    if loaded_items:
        children.append(
            dmc.Alert(
                f"Loaded from .spec4/: {', '.join(loaded_items)}",
                color="green",
                mb="md",
            )
        )

    children.append(
        dmc.Accordion(
            dmc.AccordionItem(
                [
                    dmc.AccordionControl(
                        "📎 Upload an existing design mock to skip Designer"
                    ),
                    dmc.AccordionPanel(
                        dmc.Stack(
                            [
                                dmc.Text(
                                    "If you already have a mock.html from a previous "
                                    "session or an external tool, upload it here to "
                                    "proceed directly to StackAdvisor.",
                                    size="sm",
                                    c="dimmed",
                                ),
                                dcc.Upload(
                                    id="mock-html-upload",
                                    accept=".html,text/html",
                                    multiple=False,
                                    children=dmc.Text(
                                        "Drag & drop a mock.html, or click to upload",
                                        ta="center",
                                        c="dimmed",
                                        py="sm",
                                    ),
                                    style={
                                        "border": "2px dashed "
                                        "var(--mantine-color-dark-4)",
                                        "borderRadius": "8px",
                                        "cursor": "pointer",
                                    },
                                ),
                            ],
                            gap="xs",
                        )
                    ),
                ],
                value="upload-mock",
            ),
            mb="md",
        )
    )

    if session.get("specmem"):
        children.append(
            dmc.Accordion(
                dmc.AccordionItem(
                    [
                        dmc.AccordionControl("📋 Current Project State (SPECMEM.md)"),
                        dmc.AccordionPanel(dcc.Markdown(session["specmem"])),
                    ],
                    value="specmem",
                ),
                mb="md",
            )
        )

    children.append(
        _card(
            dmc.RadioGroup(
                id="agent-select-radio",
                label="Start with:",
                value="code_scanner" if session.get("_dir_has_content") else "brainstormer",
                mb="md",
                children=dmc.Stack(
                    [
                        dmc.Radio(
                            label="🔍 CodeScanner — analyze the existing project directory (optional)",  # noqa: E501
                            value="code_scanner",
                        ),
                        dmc.Radio(
                            label="🧠 Brainstormer — develop or refine a project vision",  # noqa: E501
                            value="brainstormer",
                        ),
                        dmc.Radio(
                            label="🎨 Designer — create a visual mock-up for your application's starting screen",  # noqa: E501
                            value="designer",
                        ),
                        dmc.Radio(
                            label="⚙️ StackAdvisor — select or refine a technology stack",  # noqa: E501
                            value="stack_advisor",
                        ),
                        dmc.Radio(
                            label="📋 Phaser — break your project into executable coding phases",  # noqa: E501
                            value="phaser",
                        ),
                    ],
                    gap="xs",
                ),
            ),
            dmc.Button(
                "Load existing vision.json",
                id="btn-load-vision",
                variant="outline",
                size="sm",
                mb="xs",
                style={"display": "none"} if not vision_in_spec4 else {},
            ),
            dmc.Button(
                "Load existing stack.json",
                id="btn-load-stack",
                variant="outline",
                size="sm",
                mb="xs",
                style={"display": "none"} if not stack_in_spec4 else {},
            ),
            _error(error) if error else html.Div(),
            dmc.Button("Start →", id="btn-agent-start", mt="md"),
        )
    )

    return html.Div(children)
