from __future__ import annotations

import pathlib
from typing import Any

from dash import dcc, html
import dash_mantine_components as dmc

from spec4.app_constants import (
    STATE_DEPLOYER_COMPLETE,
    STATE_PHASES_COMPLETE,
    STATE_REVIEW_COMPLETE,
    STATE_STACK_COMPLETE,
    STATE_VISION_COMPLETE,
)
from spec4.layouts._shared import _render_message
from spec4.session import _validate_agent_preconditions

# Reset native html.Button styling so the wrapper looks like the bare badge.
_PILL_BUTTON_STYLE: dict[str, Any] = {
    "background": "none",
    "border": "none",
    "padding": 0,
    "margin": 0,
    "lineHeight": 0,
}


def _agent_status_bar(session: dict[str, Any]) -> html.Div:
    active = session.get("active_agent", "brainstormer")
    working_dir = session.get("working_dir", "")
    _mock = (
        pathlib.Path(working_dir) / ".spec4" / "design" / "mock.html"
        if working_dir
        else None
    )
    designer_done = bool(_mock and _mock.exists())
    agents = [
        ("code_scanner", "🔍 CodeScanner", session.get("code_review") is not None),
        (
            "brainstormer",
            "🧠 Brainstormer",
            session.get("vision_statement") is not None,
        ),
        ("designer", "🎨 Designer", designer_done),
        ("stack_advisor", "⚙️ StackAdvisor", session.get("stack_statement") is not None),
        ("phaser", "📋 Phaser", session.get("phaser_state") == STATE_PHASES_COMPLETE),
        ("deployer", "🚀 Deployer", session.get("deployer_state") == STATE_DEPLOYER_COMPLETE),  # noqa: E501
    ]
    items = []
    for i, (key, label, done) in enumerate(agents):
        is_active = key == active
        if is_active:
            badge: Any = dmc.Badge(label, color="green", variant="filled", size="md")
        elif done:
            badge = dmc.Badge(f"✓ {label}", color="gray", variant="light", size="md")
        else:
            badge = dmc.Badge(label, color="gray", variant="outline", size="md")
        # Active pill is rendered as a plain badge — clicking it would just
        # navigate to where you already are.
        if is_active:
            items.append(badge)
        else:
            reachable = _validate_agent_preconditions(key, session) is None
            items.append(
                html.Button(
                    badge,
                    id={"type": "agent-pill", "agent": key},
                    n_clicks=0,
                    disabled=not reachable,
                    title=None if reachable
                    else _validate_agent_preconditions(key, session),
                    style={
                        **_PILL_BUTTON_STYLE,
                        "cursor": "pointer" if reachable else "not-allowed",
                        "opacity": 1.0 if reachable else 0.4,
                    },
                )
            )
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


_TOKEN_COUNTER_AGENTS = ("phaser", "deployer")


def _streamed_token_count(session: dict[str, Any]) -> int:
    """Length of the in-flight assistant message, used as a token-count proxy."""
    messages = session.get("messages") or []
    if not messages:
        return 0
    last = messages[-1]
    if last.get("role") != "assistant":
        return 0
    return len(last.get("content") or "")


def _token_count_text(session: dict[str, Any]) -> str:
    """Render text for the token counter, or empty when it shouldn't show."""
    if session.get("active_agent") not in _TOKEN_COUNTER_AGENTS:
        return ""
    if not session.get("_stream_id") and _streamed_token_count(session) == 0:
        return ""
    return f"Tokens received: {_streamed_token_count(session)}"


def _chat_action_buttons(session: dict[str, Any]) -> html.Div:
    active = session.get("active_agent")
    buttons = []

    if active == "code_scanner" and session.get("code_scanner_state") == STATE_REVIEW_COMPLETE:
        buttons = [
            dmc.Button(
                "💾 Download code_review.json", id="btn-dl-review", variant="outline"
            ),
            dmc.Button(
                "🔄 Re-scan Project",
                id="btn-rescan-project",
                variant="outline",
                color="orange",
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
            id="btn-stack-to-designer",
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
        token_counter = dmc.Text(
            _token_count_text(session),
            id="chat-token-count",
            c="dimmed",
            size="sm",
        )
        if session.get("phases"):
            buttons = [
                back,
                token_counter,
                dmc.Button(
                    "💾 Download phases.zip", id="btn-dl-phases", variant="outline"
                ),
                dmc.Button("Continue to Deployer →", id="btn-phaser-to-deployer"),
            ]
        else:
            buttons = [back, token_counter]
    elif active == "deployer":
        back = dmc.Button(
            "← Back to Phaser",
            id="btn-deployer-to-phaser",
            variant="outline",
            color="gray",
        )
        token_counter = dmc.Text(
            _token_count_text(session),
            id="chat-token-count",
            c="dimmed",
            size="sm",
        )
        if session.get("deployer_state") == STATE_DEPLOYER_COMPLETE:
            buttons = [
                back,
                token_counter,
                dmc.Button(
                    "💾 Download deployment plan (Markdown)",
                    id="btn-dl-deployment",
                    variant="outline",
                ),
                dmc.Button(
                    "Start New Project", id="btn-deployer-new-project", variant="light"
                ),
            ]
        else:
            buttons = [back, token_counter]

    if not buttons:
        return html.Div()
    return html.Div(
        [
            dmc.Divider(mb="sm"),
            dmc.Group(buttons, mb="md"),
        ]
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
            dcc.Download(id="dl-deployment"),
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
                style={
                    "display": "block" if session.get("_stream_id") else "none",
                    "marginBottom": "12px",
                },
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
