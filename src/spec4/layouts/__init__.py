from __future__ import annotations

import pathlib
import re
from typing import Any

from dash import dcc, html
import dash_mantine_components as dmc

from spec4 import providers
from spec4.app_constants import (
    STATE_PHASES_COMPLETE,
    STATE_REVIEW_COMPLETE,
    STATE_STACK_COMPLETE,
    STATE_VISION_COMPLETE,
)


# ---------------------------------------------------------------------------
# Shared UI helpers
# ---------------------------------------------------------------------------


def _card(*children: Any, **kwargs: Any) -> Any:
    return dmc.Paper(list(children), p="md", radius="md", withBorder=True, **kwargs)


def _feature_card(*children: Any, **kwargs: Any) -> Any:
    return dmc.Paper(
        list(children),
        p="lg",
        radius="lg",
        withBorder=True,
        className="feature-card",
        **kwargs,
    )


def _error(msg: str) -> Any:
    return dmc.Alert(msg, color="red", variant="light", mt="sm")


# Navigation links shared between the footer and nav drawer.
_NAV_LINKS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Spec4",
        [
            ("How It Works", "https://spec4.ai/how-it-works/"),
            ("About", "https://spec4.ai/about/"),
            ("Get Started", "https://github.com/robertcrowe/Spec4"),
        ],
    ),
    (
        "Agents",
        [
            ("Reviewer", "https://spec4.ai/agents/reviewer/"),
            ("Brainstormer", "https://spec4.ai/agents/brainstormer/"),
            ("StackAdvisor", "https://spec4.ai/agents/stackadvisor/"),
            ("Phaser", "https://spec4.ai/agents/phaser/"),
        ],
    ),
    (
        "Resources",
        [
            ("Community", "https://github.com/robertcrowe/Spec4/discussions"),
            ("GitHub", "https://github.com/robertcrowe/Spec4"),
            (
                "Contributing",
                "https://github.com/robertcrowe/Spec4/blob/main/CONTRIBUTING.md",
            ),
        ],
    ),
]


def _nav_drawer() -> html.Div:
    def _link(text: str, href: str) -> Any:
        return html.A(
            text, href=href, target="_blank", rel="noopener", className="footer-link"
        )

    sections = [
        html.Div(
            [html.Div(heading, className="footer-col-heading")]
            + [_link(label, url) for label, url in links],
            style={"marginBottom": "1.5rem"},
        )
        for heading, links in _NAV_LINKS
    ]
    # Remove marginBottom from the last section
    sections[-1] = html.Div(
        [html.Div(_NAV_LINKS[-1][0], className="footer-col-heading")]
        + [_link(label, url) for label, url in _NAV_LINKS[-1][1]],
    )

    return html.Div(
        [
            html.Div(id="nav-overlay", className="nav-overlay"),
            html.Div(
                id="nav-drawer",
                className="nav-drawer",
                children=[
                    html.Button("✕", id="nav-close-btn", className="nav-close-btn"),
                    html.Div(style={"clear": "both", "marginBottom": "1.5rem"}),
                    *sections,
                ],
            ),
        ]
    )


def _footer() -> html.Footer:
    return html.Footer(
        [
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 2},
                spacing="xl",
                mb="lg",
                children=[
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("Spec", className="logo-spec"),
                                    html.Span("4", className="logo-4"),
                                    html.Span(" AI", className="logo-spec"),
                                ],
                                className="footer-brand-logo",
                            ),
                            html.P(
                                "Spec-driven development, from idea to implementation plan.",  # noqa: E501
                                className="footer-brand-tagline",
                            ),
                        ]
                    ),
                    dmc.SimpleGrid(
                        cols=3,
                        spacing="md",
                        children=[
                            html.Div(
                                [html.Div(heading, className="footer-col-heading")]
                                + [
                                    html.A(
                                        label,
                                        href=url,
                                        target="_blank",
                                        rel="noopener",
                                        className="footer-link",
                                    )
                                    for label, url in links
                                ],
                            )
                            for heading, links in _NAV_LINKS
                        ],
                    ),
                ],
            ),
            html.Div(
                "© 2026 Robert Crowe. Open source under Apache 2.0 License.",
                className="footer-bottom",
            ),
        ],
        className="footer",
    )


# ---------------------------------------------------------------------------
# Phase layouts
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
                                    dmc.Title("🔍 Reviewer", order=4),
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


def _setup_provider_layout(
    session: dict[str, Any],
    prefs: dict[str, Any],
    labels: list[str],
    setup_error: str | None,
) -> html.Div:
    saved_prov = prefs.get("provider")
    default_label = (
        providers.PROVIDERS[saved_prov]["label"]
        if saved_prov in providers.PROVIDERS
        else labels[0]
    )
    return html.Div(
        [
            dmc.Title("Connect to an LLM provider", order=3, mb="sm"),
            dmc.Text(
                "Spec4 works with a wide variety of LLM providers and models. "
                "Choose the one that works best for you.",
                c="dimmed",
                mb="sm",
            ),
            dmc.Alert(
                "Note: Your API key is never stored outside of your system.",
                color="blue",
                variant="light",
                mb="lg",
            ),
            _card(
                dmc.Select(
                    id="setup-provider",
                    label="Provider",
                    data=labels,
                    value=default_label,
                    mb="md",
                ),
                dmc.PasswordInput(
                    id="setup-api-key",
                    label="API Key",
                    value=prefs.get("api_key") or "",
                    mb="md",
                ),
                dmc.Checkbox(
                    id="setup-save-prefs",
                    label="Remember provider and keys in this browser? (stored in localStorage only)",  # noqa: E501
                    checked=bool(prefs.get("save_prefs")),
                    mb="md",
                ),
                _error(setup_error) if setup_error else html.Div(),
                dmc.Group(
                    [
                        dmc.Button(
                            "← Back",
                            id="btn-setup-back-to-dir",
                            variant="outline",
                            color="gray",
                        ),
                        dmc.Button("Connect", id="btn-setup-connect"),
                        dmc.Button(
                            "Clear saved credentials",
                            id="btn-setup-clear",
                            variant="outline",
                            color="red",
                            disabled=not bool(prefs),
                        ),
                    ],
                    mt="sm",
                ),
            ),
        ]
    )


def _setup_model_layout(
    session: dict[str, Any],
    prefs: dict[str, Any],
    setup_error: str | None,
) -> html.Div:
    available = session["available_models"]
    saved_model = prefs.get("model")
    default_model = (
        saved_model
        if saved_model in available
        else (available[0] if available else None)
    )
    provider_label = providers.PROVIDERS[session["provider"]]["label"]
    return html.Div(
        [
            dmc.Title("Select a Model", order=3, mb="sm"),
            dmc.Text(
                "Now that you have a provider, please select one of the models that this provider provides. "  # noqa: E501
                "Remember that different models have different capabilities and different costs.",  # noqa: E501
                c="dimmed",
                mb="lg",
            ),
            _card(
                dmc.Alert(f"Connected to {provider_label}", color="green", mb="md"),
                dmc.Select(
                    id="setup-model",
                    label="Model",
                    data=available,
                    value=default_model,
                    mb="md",
                ),
                _error(setup_error) if setup_error else html.Div(),
                dmc.Group(
                    [
                        dmc.Button(
                            "← Change Provider",
                            id="btn-setup-back-provider",
                            variant="outline",
                            color="gray",
                        ),
                        dmc.Button("Continue →", id="btn-setup-model-continue"),
                    ],
                    mt="sm",
                ),
            ),
        ]
    )


def _setup_tavily_layout(
    session: dict[str, Any],
    prefs: dict[str, Any],
    setup_error: str | None,
    image_support: bool | None = None,
) -> html.Div:
    if image_support is True:
        image_alert: Any = dmc.Alert(
            "This model supports image input — screenshot examples are available "
            "in the Designer step.",
            title="Image Support",
            color="green",
            variant="light",
            mb="md",
        )
    elif image_support is False:
        image_alert = dmc.Alert(
            "This model does not support image input — screenshot upload will be "
            "disabled in the Designer step. Go back to choose a different model if "
            "you need image support.",
            title="No Image Support",
            color="orange",
            variant="light",
            mb="md",
        )
    else:
        image_alert = html.Div()
    return html.Div(
        [
            dmc.Title("Connect to Tavily Web Search", order=3, mb="sm"),
            dmc.Text(
                "Web search tends to be fairly useful when you're creating a spec for an application. "  # noqa: E501
                "It will allow Spec4 to do things like look up the features of a library you might want "  # noqa: E501
                "to use, or compare and contrast two different protocols that you're considering.",  # noqa: E501
                c="dimmed",
                mb="lg",
            ),
            _card(
                dmc.Alert(f"LLM: {session['model']}", color="green", mb="md"),
                image_alert,
                dmc.Text(
                    "Enables all agents to search the web for current information. "
                    "Optional — skip if you don't have a Tavily key.",
                    c="dimmed",
                    mb="md",
                ),
                dmc.PasswordInput(
                    id="setup-tavily-key",
                    label="Tavily API Key",
                    placeholder="tvly-…",
                    value=prefs.get("tavily_key") or "",
                    mb="md",
                ),
                _error(setup_error) if setup_error else html.Div(),
                dmc.Group(
                    [
                        dmc.Button(
                            "← Change Model",
                            id="btn-setup-back-model",
                            variant="outline",
                            color="gray",
                        ),
                        dmc.Button(
                            "Skip →", id="btn-setup-tavily-skip", variant="outline"
                        ),
                        dmc.Button("Connect & Start →", id="btn-setup-tavily-connect"),
                    ],
                    mt="sm",
                ),
            ),
        ]
    )


def _setup_layout(
    session: dict[str, Any],
    prefs: dict[str, Any],
    image_support: bool | None = None,
) -> html.Div:
    labels = providers.all_provider_labels()
    setup_error = session.get("setup_error")
    if session.get("available_models") is None:
        return _setup_provider_layout(session, prefs, labels, setup_error)
    if session.get("model") is None:
        return _setup_model_layout(session, prefs, setup_error)
    return _setup_tavily_layout(session, prefs, setup_error, image_support)


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
            "Reviewer or Brainstormer.\n\n"
            "* Start with **Reviewer** if you're modifying an existing project, so that Spec4 can "  # noqa: E501
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
                "Consider running Reviewer first to help Spec4 understand the current state of your project.",  # noqa: E501
                color="yellow",
                mb="md",
            )
        )
    elif working_dir and not session.get("_dir_has_content"):
        children.append(
            dmc.Alert(
                "Your project directory is empty. You can still run Reviewer if you'd like, "  # noqa: E501
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
                "Reviewer again just to make sure that Spec4 understands the current state of your "  # noqa: E501
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
                value="reviewer" if session.get("_dir_has_content") else "brainstormer",
                mb="md",
                children=dmc.Stack(
                    [
                        dmc.Radio(
                            label="🔍 Reviewer — analyze the existing project directory (optional)",  # noqa: E501
                            value="reviewer",
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


def _agent_status_bar(session: dict[str, Any]) -> html.Div:
    active = session.get("active_agent", "brainstormer")
    agents = [
        ("reviewer", "🔍 Reviewer", session.get("code_review") is not None),
        (
            "brainstormer",
            "🧠 Brainstormer",
            session.get("vision_statement") is not None,
        ),
        ("stack_advisor", "⚙️ StackAdvisor", session.get("stack_statement") is not None),
        ("phaser", "📋 Phaser", session.get("phaser_state") == STATE_PHASES_COMPLETE),
    ]
    items = []
    for i, (key, label, done) in enumerate(agents):
        if key == active:
            items.append(dmc.Badge(label, color="green", variant="filled", size="md"))
        elif done:
            items.append(
                dmc.Badge(f"✓ {label}", color="gray", variant="light", size="md")
            )
        else:
            items.append(dmc.Badge(label, color="gray", variant="outline", size="md"))
        if i < len(agents) - 1:
            items.append(dmc.Text("→", c="dimmed", size="sm"))
    return html.Div(
        [
            dmc.Group(
                [
                    dmc.Group(items, gap="xs"),
                    dmc.Button(
                        "← Back",
                        id="btn-chat-back",
                        variant="filled",
                        size="xs",
                        color="blue",
                    ),
                ],
                justify="space-between",
                mb="sm",
            ),
            dmc.Divider(mb="md"),
        ]
    )


def _chat_action_buttons(session: dict[str, Any]) -> html.Div:
    active = session.get("active_agent")
    buttons = []

    if active == "reviewer" and session.get("reviewer_state") == STATE_REVIEW_COMPLETE:
        buttons = [
            dmc.Button(
                "💾 Download code_review.json", id="btn-dl-review", variant="outline"
            ),
            dmc.Button("Continue to Brainstormer →", id="btn-review-to-brainstormer"),
        ]
    elif (
        active == "brainstormer"
        and session.get("brainstormer_state") == STATE_VISION_COMPLETE
    ):
        buttons = [
            dmc.Button(
                "💾 Download vision.json", id="btn-dl-vision", variant="outline"
            ),
            dmc.Button("Continue to Designer →", id="btn-brainstormer-to-designer"),
        ]
    elif active == "stack_advisor":
        back = dmc.Button(
            "← Back to Designer",
            id="btn-stack-to-brainstormer",
            variant="outline",
            color="gray",
        )
        if session.get("stack_advisor_state") == STATE_STACK_COMPLETE:
            buttons = [
                back,
                dmc.Button(
                    "💾 Download stack.json", id="btn-dl-stack", variant="outline"
                ),
                dmc.Button("Send to Phaser →", id="btn-stack-to-phaser"),
            ]
        else:
            buttons = [back]
    elif active == "phaser":
        back = dmc.Button(
            "← Back to Stack Advisor",
            id="btn-phaser-to-stack",
            variant="outline",
            color="gray",
        )
        if session.get("phases"):
            buttons = [
                back,
                dmc.Button(
                    "💾 Download phases.zip", id="btn-dl-phases", variant="outline"
                ),
                dmc.Button("Done →", id="btn-phaser-done"),
            ]
        else:
            buttons = [back]

    if not buttons:
        return html.Div()
    return html.Div(
        [
            dmc.Divider(mb="sm"),
            dmc.Group(buttons, mb="md"),
        ]
    )


def _reformat_inline_lists(text: str) -> str:
    """Break inline numbered lists onto separate lines for proper Markdown rendering."""
    # Insert a newline before each "N. " that isn't already at the start of a line
    text = re.sub(r"(?<!\n)[ \t]+(\d+)\.[ \t]+", r"\n\1. ", text)
    # Ensure a blank line separates the preamble from the first list item
    text = re.sub(r"([^\n])\n(1\. )", r"\1\n\n\2", text)
    return text


def _render_message(msg: dict[str, Any]) -> html.Div:
    is_user = msg["role"] == "user"
    content = msg["content"] if is_user else _reformat_inline_lists(msg["content"])
    return html.Div(
        dmc.Paper(
            dcc.Markdown(content, style={"margin": 0}),
            p="sm",
            radius="md",
            className="chat-bubble-user" if is_user else "chat-bubble-assistant",
            style={"maxWidth": "85%"} if is_user else {"width": "100%"},
        ),
        style={
            "display": "flex",
            "justifyContent": "flex-end" if is_user else "flex-start",
            "marginBottom": "8px",
        },
    )


def _chat_layout(session: dict[str, Any]) -> html.Div:
    messages = session.get("messages", [])
    needs_init = not messages and not session.get("_initial_turn_done")

    return html.Div(
        [
            # Trigger initial agent turn once on first render.
            # max_intervals=0 disables the interval (never fires) when not needed,
            # but keeps n_intervals available as a callback input.
            dcc.Interval(
                id="init-turn-interval",
                interval=300,
                max_intervals=1 if needs_init else 0,
            ),
            # Always-present download triggers (invisible)
            dcc.Download(id="dl-vision"),
            dcc.Download(id="dl-stack"),
            dcc.Download(id="dl-code-review"),
            dcc.Download(id="dl-phases"),
            _agent_status_bar(session),
            html.Div(
                html.Div(
                    [_render_message(m) for m in messages]
                    + (
                        [dmc.Text("Thinking…", c="dimmed", size="sm")]
                        if needs_init
                        else []
                    ),
                    style={"display": "flex", "flexDirection": "column"},
                ),
                id="chat-scroll-area",
                style={
                    "height": "450px",
                    "overflowY": "auto",
                    "marginBottom": "var(--mantine-spacing-md)",
                },
            ),
            _chat_action_buttons(session),
            html.Div(
                dmc.Progress(
                    value=100, animated=True, striped=True, color="blue", size="sm"
                ),
                id="chat-progress-container",
                style={"display": "none", "marginBottom": "12px"},
            ),
            html.Div(
                [
                    dmc.Textarea(
                        id="chat-input",
                        placeholder="Type your message…",
                        style={"flex": "1"},
                        autosize=True,
                        minRows=2,
                        n_submit=0,
                    ),
                    dmc.Button("Send", id="btn-chat-submit"),
                ],
                style={
                    "display": "flex",
                    "alignItems": "stretch",
                    "gap": "var(--mantine-spacing-sm)",
                    "width": "100%",
                },
            ),
        ]
    )


def _done_layout(session: dict[str, Any]) -> html.Div:
    phases = session.get("phases", [])
    n = len(phases)
    spec4_dir = pathlib.Path(session.get("working_dir", "")) / ".spec4"
    has_vision = (spec4_dir / "vision.json").exists()
    has_stack = (spec4_dir / "stack.json").exists()

    phase_rows = [
        dmc.Text(
            f"Phase {p.get('phase_number')}: {p.get('phase_title', '')}",
            size="sm",
            style={
                "paddingLeft": "0.5rem",
                "borderLeft": "2px solid var(--mantine-color-blue-5)",
            },
            mb="xs",
        )
        for p in sorted(phases, key=lambda x: x.get("phase_number", 0))
    ]

    return html.Div(
        [
            dcc.Download(id="dl-phases-done"),
            dcc.Download(id="dl-vision-done"),
            dcc.Download(id="dl-stack-done"),
            dmc.Title("Your Project Phases Are Ready", order=3, mb="xs"),
            dmc.Text(
                f"Spec4 has broken your project into {n} executable phase{'s' if n != 1 else ''}. "  # noqa: E501
                "Hand them to an agentic coding tool and work through them in order.",
                c="dimmed",
                mb="lg",
            ),
            _card(
                dmc.Title("How to use your phases", order=5, mb="sm"),
                dcc.Markdown(
                    "1. Open your agentic coding tool (Claude Code, Codex, Antigravity, Hermes, etc.) "  # noqa: E501
                    "inside your project directory.\n"
                    "2. Load or paste the contents of **Phase 1** as your prompt.\n"
                    "3. Let the agent complete the phase fully — verify it passes before continuing.\n"  # noqa: E501
                    "4. Repeat for Phase 2, Phase 3, and so on **in order**.\n\n"
                    "> Do not skip phases. Each phase builds directly on the one before it.\n\n"  # noqa: E501
                    "**Loading options:**\n"
                    "- **Copy/paste** — open each `.json` file and paste the contents into your tool.\n"  # noqa: E501
                    "- **File loading** — tools like Claude Code accept files directly "
                    "(e.g. `Please implement @.spec4/phases/phase1.json`).\n"
                    "- **Download** — use the button below to get all phases as a zip.",
                    style={"fontSize": "0.9rem"},
                ),
                mb="md",
            ),
            _card(
                dmc.Title(
                    "Python project? Set up your environment first", order=5, mb="sm"
                ),
                dcc.Markdown(
                    "Before starting your agentic coding tool, initialise a virtual environment "  # noqa: E501
                    "so your agent installs dependencies in an isolated, reproducible way:\n\n"  # noqa: E501
                    "```bash\n"
                    "uv init\n"
                    "uv sync\n"
                    "source .venv/bin/activate\n"
                    "```\n\n"
                    "On Windows use `.venv\\Scripts\\activate` instead of `source .venv/bin/activate`.",  # noqa: E501
                    style={"fontSize": "0.9rem"},
                ),
                mb="md",
            ),
            _card(
                dmc.Title(f"Your {n} phase{'s' if n != 1 else ''}", order=5, mb="sm"),
                *phase_rows,
            )
            if phase_rows
            else html.Div(),
            dmc.Divider(my="md"),
            dmc.Group(
                [
                    dmc.Button(
                        "← Back to Phaser",
                        id="btn-done-back-to-phaser",
                        variant="outline",
                        color="gray",
                    ),
                    dmc.Button(
                        "💾 Download vision.json",
                        id="btn-dl-vision-done",
                        variant="outline",
                        style={"display": "none"} if not has_vision else {},
                    ),
                    dmc.Button(
                        "💾 Download stack.json",
                        id="btn-dl-stack-done",
                        variant="outline",
                        style={"display": "none"} if not has_stack else {},
                    ),
                    dmc.Button(
                        "💾 Download phases.zip",
                        id="btn-dl-phases-done",
                        variant="outline",
                    ),
                    dmc.Button(
                        "Start New Project", id="btn-done-new-project", variant="light"
                    ),
                ]
            ),
        ]
    )
