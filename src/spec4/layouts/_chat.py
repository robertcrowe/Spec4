from __future__ import annotations

from typing import Any

from dash import dcc, html
import dash_mantine_components as dmc

from spec4.app_constants import (
    STATE_PHASES_COMPLETE,
    STATE_REVIEW_COMPLETE,
    STATE_STACK_COMPLETE,
    STATE_VISION_COMPLETE,
)
from spec4.layouts._shared import _render_message


def _agent_status_bar(session: dict[str, Any]) -> html.Div:
    active = session.get("active_agent", "brainstormer")
    agents = [
        ("code_scanner", "🔍 CodeScanner", session.get("code_review") is not None),
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

    if active == "code_scanner" and session.get("code_scanner_state") == STATE_REVIEW_COMPLETE:
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
