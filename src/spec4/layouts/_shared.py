from __future__ import annotations

import re
from typing import Any

from dash import dcc, html
import dash_mantine_components as dmc


# ---------------------------------------------------------------------------
# Primitive UI helpers
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


# ---------------------------------------------------------------------------
# Navigation / footer
# ---------------------------------------------------------------------------

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
            ("CodeScanner", "https://spec4.ai/agents/reviewer/"),
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
# Chat message rendering
# ---------------------------------------------------------------------------


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
