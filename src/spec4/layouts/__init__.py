from __future__ import annotations

import pathlib
from typing import Any

from dash import dcc, html
import dash_mantine_components as dmc

from spec4 import project_manager
from spec4.app_constants import PROJECT_MODE_EXISTING, PROJECT_MODE_NEW
from spec4.layouts._chat import _agent_status_bar, _chat_action_buttons, _chat_layout
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
                            "Design and deploy ",
                            html.Span("agentic applications", className="text-gradient"),  # noqa: E501
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
                        "A pipeline of specialised LLM agents takes you from a rough idea to "  # noqa: E501
                        "full specification — including the AI features your app needs, "  # noqa: E501
                        "the agents and tools behind them, and how they fit together — then "  # noqa: E501
                        "through structured development phases and a production-level deployment plan ready "  # noqa: E501
                        "for Claude Code, Hermes, Kiro, Antigravity, or any AI coding agent. ",  # noqa: E501
                        size="lg",
                        c="dimmed",
                        # No maxWidth: the intro shares the hero container's
                        # content box with the H1 above it, so both wrap at the
                        # same left and right margins. A narrower cap here left
                        # the paragraph visibly inset from the heading.
                        style={
                            "lineHeight": 1.7,
                            "margin": "0 auto 0.5rem",
                        },
                    ),
                    dmc.Text(
                        [
                            "Not just vibe coding, but production-level "
                            "development.  It's way more powerful than ",
                            html.Code("/plan"),
                            ".",
                        ],
                        size="lg",
                        c="blue.5",
                        style={"margin": "0 auto 1.5rem"},
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
                cols={"base": 1, "sm": 2, "lg": 3},
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
                            dmc.Title("🤖 Agentifier", order=4, mb="sm"),
                            dmc.Text(
                                "Identifies every AI/LLM integration opportunity in your vision, "  # noqa: E501
                                "recommends a complexity tier for each, and drafts a full "  # noqa: E501
                                "implementation spec per feature.",
                                size="sm",
                                mb="md",
                                c="dimmed",
                            ),
                            html.Span("ai_features.json", className="output-badge"),
                        ),
                        href="https://spec4.ai/agents/agentifier/",
                        target="_blank",
                        style={"textDecoration": "none", "color": "inherit"},
                    ),
                    html.A(
                        _feature_card(
                            dmc.Group(
                                [
                                    dmc.Title("🎨 Designer", order=4),
                                    dmc.Text("(optional)", size="xs", c="dimmed"),
                                ],
                                gap="xs",
                                align="center",
                                mb="xs",
                            ),
                            dmc.Text(
                                "Generates a self-contained HTML mock-up of your starting screen "  # noqa: E501
                                "from a style description and optional reference screenshots.",  # noqa: E501
                                size="sm",
                                mb="md",
                                c="dimmed",
                            ),
                            html.Span("mock.html", className="output-badge"),
                        ),
                        href="https://spec4.ai/agents/designer/",
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
                    html.A(
                        _feature_card(
                            dmc.Title("🚀 Deployer", order=4, mb="sm"),
                            dmc.Text(
                                "Guides you through coding-agent workflow and designs a deployment "  # noqa: E501
                                "plan tailored to your stack — cloud, PaaS, containers, CI/CD.",  # noqa: E501
                                size="sm",
                                mb="md",
                                c="dimmed",
                            ),
                            html.Span("deployment.json", className="output-badge"),
                        ),
                        href="https://spec4.ai/agents/deployer/",
                        target="_blank",
                        style={"textDecoration": "none", "color": "inherit"},
                    ),
                ],
            ),
            dmc.Divider(mb="md"),
            dmc.Text(
                "You can start at any stage. Agentifier requires a saved vision; "
                "StackAdvisor requires a vision; "
                "Phaser requires both a vision and a stack; Deployer requires phases.",
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

# (key, step, emoji, name, description) in pipeline order.
_AGENT_ROWS: list[tuple[str, int, str, str, str]] = [
    ("code_scanner", 0, "🔍", "CodeScanner",
     "analyze the existing project directory"),
    ("brainstormer", 1, "🧠", "Brainstormer",
     "develop or refine a project vision"),
    ("agentifier", 2, "🤖", "Agentifier",
     "identify AI opportunities and choose tiers"),
    ("designer", 3, "🎨", "Designer",
     "create a visual mock-up for your application's starting screen"),
    ("stack_advisor", 4, "⚙️", "StackAdvisor",
     "select or refine a technology stack"),
    ("phaser", 5, "📋", "Phaser",
     "break your project into executable coding phases"),
    ("deployer", 6, "🚀", "Deployer",
     "plan coding-agent workflow and deployment strategy"),
]

_AGENT_BTN_LABELS = {
    project_manager.AGENT_BTN_START: "Start",
    project_manager.AGENT_BTN_MODIFY: "Modify",
    project_manager.AGENT_BTN_NEEDS_UPDATE: "Needs Update",
    project_manager.AGENT_BTN_NOT_READY: "Not Ready",
    project_manager.AGENT_BTN_REQUIRED: "Required",
}

# Start keeps the current primary (blue) button; Modify green; Needs Update and
# Required red; Not Ready is a disabled grey button.
_AGENT_BTN_COLORS = {
    project_manager.AGENT_BTN_START: "blue",
    project_manager.AGENT_BTN_MODIFY: "green",
    project_manager.AGENT_BTN_NEEDS_UPDATE: "red",
    project_manager.AGENT_BTN_REQUIRED: "red",
}


def _agent_action_button(agent_key: str, state: str) -> Any:
    """Render one agent's action button. Enabled states route via the shared
    ``agent-pill`` click callback; ``not_ready`` is a disabled grey button."""
    disabled = state == project_manager.AGENT_BTN_NOT_READY
    return dmc.Button(
        _AGENT_BTN_LABELS[state],
        id={"type": "agent-pill", "agent": agent_key},
        n_clicks=0,
        color=_AGENT_BTN_COLORS.get(state, "gray"),
        disabled=disabled,
        w=140,
    )


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
            dmc.Title("Is There an Existing Project Here?", order=3, mb="sm"),
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
                    "marginBottom": "1.5rem",
                },
            ),
            dmc.Group(
                [
                    dmc.Button(
                        "Existing project",
                        id="btn-project-mode-existing",
                        n_clicks=0,
                        color="blue",
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
                mt="md",
            ),
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
                color="blue",
                mb="md",
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
                color="blue",
                mb="md",
            )
        )
    elif session.get("project_mode") == PROJECT_MODE_EXISTING:
        children.append(
            dmc.Alert(
                "You told us there's an existing project here. "
                "Consider running CodeScanner first to help Spec4 understand the current state of your project.",  # noqa: E501
                color="yellow",
                mb="md",
            )
        )
    elif working_dir and not project_manager.directory_has_content(working_dir):
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

    if loaded_items and not new_round:
        children.append(
            dmc.Alert(
                f"Loaded from .spec4/: {', '.join(loaded_items)}",
                color="green",
                mb="md",
            )
        )

    rows = []
    for key, step, emoji, name, desc in _AGENT_ROWS:
        state = project_manager.agent_button_state(working_dir, key, session)
        rows.append(
            dmc.Group(
                [
                    html.Span(
                        f"Step {step}: {emoji} {name} — {desc}",
                        style={"flex": 1},
                    ),
                    _agent_action_button(key, state),
                ],
                justify="space-between",
                wrap="nowrap",
                gap="md",
            )
        )

    children.append(
        _card(
            dmc.Text("Choose an agent:", size="lg", fw=600, mb="md"),
            _error(error) if error else html.Div(),
            dmc.Stack(rows, gap="sm", mb="md"),
            dmc.Group(
                [
                    dmc.Button(
                        "Change model / provider",
                        id="btn-agent-change-provider",
                        variant="outline",
                    ),
                ],
                mt="md",
            ),
        )
    )

    return html.Div(children)
