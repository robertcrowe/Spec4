"""The agent chat frame.

Cleanup Phase 4f split the three self-contained parts of this screen into
siblings, one module each:

* :mod:`spec4.layouts._chat_status` -- the pipeline indicator above the
  transcript, and the artifact-existence check behind it.
* :mod:`spec4.layouts._chat_actions` -- the action row below the transcript,
  the Download/Open id prefixes, and the counters that ride in the row.
* :mod:`spec4.layouts._chat_panels` -- the optional blocks between the two:
  the run-cost strip, the provider-error retry panel, and the Agentifier
  breadth panel. Each returns ``None`` when inactive.

``_chat_layout`` itself stays here: it is the one function that assembles the
three into a screen, and it belongs to none of them.

Every name the split moved is re-exported below, so no importer changed when
the code moved -- import from here or from the owning module, both resolve to
the same object. ``__all__`` is load-bearing rather than decorative:
``[tool.mypy] strict`` implies ``no_implicit_reexport``, so without it a
re-exported name could not be imported from this module at all.

The gate helpers come from ``spec4.layouts._llm_gate`` by name rather than as
``from spec4.layouts import _llm_gate``. That package import was the whole of
the ``layouts`` -> ``layouts._chat`` -> ``layouts`` cycle recorded in
CLEANUP_INVENTORY.md 6.1; a sibling import reaches the same three functions
without asking the package to be built while it is still building this module.
"""

from __future__ import annotations

from typing import Any

from dash import dcc, html
import dash_mantine_components as dmc

from spec4.layouts._agent_rows import AGENT_DISPLAY_NAMES
from spec4.layouts._chat_actions import (
    CHAT_ARTIFACTS,
    DOWNLOAD_BTN_PREFIX,
    OPEN_BTN_PREFIX,
    _chat_action_buttons,
    _ff_controls,
    _NO_CALLS_RECORDED,
    _NO_TOKEN_COUNT,
    _open_button,
    open_button_id,
    _streamed_token_count,
    _token_count_text,
    _TOKEN_COUNTER_AGENTS,
    _turn_token_text,
)
from spec4.layouts._chat_panels import (
    _breadth_panel,
    _cost_summary,
    _retry_panel,
    _RUN_COMPLETE,
)
from spec4.layouts._chat_status import (
    _agent_status_bar,
    _completed_agents,
    _PILL_ACTIVE,
    _PILL_BASE,
    _PILL_DONE,
    _PILL_UNREACHABLE,
)
from spec4.layouts._llm_gate import gate_card, is_open, model_chip
from spec4.layouts._shared import PROGRESS_CLASS_NAMES, _render_message

__all__ = [
    "_agent_status_bar",
    "_breadth_panel",
    "_chat_action_buttons",
    "_chat_layout",
    "CHAT_ARTIFACTS",
    "_completed_agents",
    "_cost_summary",
    "DOWNLOAD_BTN_PREFIX",
    "_ff_controls",
    "_NO_CALLS_RECORDED",
    "_NO_TOKEN_COUNT",
    "_open_button",
    "open_button_id",
    "OPEN_BTN_PREFIX",
    "_PILL_ACTIVE",
    "_PILL_BASE",
    "_PILL_DONE",
    "_PILL_UNREACHABLE",
    "_retry_panel",
    "_RUN_COMPLETE",
    "_streamed_token_count",
    "_token_count_text",
    "_TOKEN_COUNTER_AGENTS",
    "_turn_token_text",
]


def _chat_layout(
    session: dict[str, Any], prefs: dict[str, Any] | None = None
) -> html.Div:
    messages = session.get("messages", [])
    active = session.get("active_agent", "brainstormer")
    # The model gate stands between entering an agent and its opening turn. The
    # interval below stays mounted while it is open — `on_init_turn` takes it as
    # an Input, so the component has to exist — but disabled, so the turn cannot
    # start until the choice is made.
    gate_open = is_open(session, active)
    needs_init = (
        not messages and not session.get("_initial_turn_done") and not gate_open
    )
    # The one-word label above each assistant block. The agent naming itself
    # is what tells the two speakers apart now that neither block is filled.
    speaker = AGENT_DISPLAY_NAMES.get(active, "Agent")
    breadth_panel = _breadth_panel(session)
    retry_panel = _retry_panel(session)
    cost_card = _cost_summary(session)
    # Mid-agent, the chip re-opens the same card. `agent_llm_draft` marks it
    # open; a resting chip renders nothing extra.
    chip_open = bool(
        not gate_open and (session.get("agent_llm_draft") or {}).get("agent") == active
    )
    gate = gate_card(session, prefs, active) if gate_open or chip_open else None

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
            dcc.Download(id="dl-features"),
            _agent_status_bar(session),
            *([gate] if gate is not None else []),
            html.Div(
                html.Div(
                    [_render_message(m, speaker) for m in messages]
                    + (
                        [dmc.Text("Thinking…", c="dimmed", size="sm")]
                        if needs_init
                        else []
                    ),
                    style={"display": "flex", "flexDirection": "column"},
                ),
                id="chat-scroll-area",
                # Height and scrolling are in `v3.css` (60vh, `overflow-y:
                # auto`) rather than here: an inline height would win over the
                # stylesheet, and the whole point of the viewport-relative
                # value is that it answers to the window rather than to a
                # number written into the layout.
                style={
                    # Tight against the action row below: the divider that opens
                    # that row already reads as the separator, so md here just
                    # stranded the buttons.
                    "marginBottom": "var(--mantine-spacing-xs)",
                },
            ),
            # The run's cost, under its last message and above the row that
            # moves on from it. Renders only once the run is complete.
            *([cost_card] if cost_card is not None else []),
            _chat_action_buttons(session),
            *([retry_panel] if retry_panel is not None else []),
            *([breadth_panel] if breadth_panel is not None else []),
            html.Div(
                [
                    dmc.Progress(
                        value=100,
                        animated=True,
                        striped=True,
                        # Thin, at the mock's 4px: the live-activity signal is
                        # the only motion on this screen, and it says "still
                        # running" from the edge of vision rather than from a
                        # bar the eye has to land on.
                        size="xs",
                        classNames=PROGRESS_CLASS_NAMES,
                    ),
                    # The elapsed readout that used to sit here now rides in the
                    # action row, next to the chars counter — see
                    # _chat_action_buttons.
                ],
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
                    # Hide the text input + Send button while the breadth
                    # checkbox panel is active — the user acts via checkboxes at
                    # this step. Components stay mounted (display:none) so
                    # on_chat_submit's State references remain valid under
                    # suppress_callback_exceptions.
                    "display": "none" if breadth_panel is not None else "flex",
                    "alignItems": "stretch",
                    "gap": "var(--mantine-spacing-sm)",
                    "width": "100%",
                },
            ),
            # The footer row under the composer. The model chip is the standing
            # answer to "what is this agent running on" and the only way to
            # change it without re-entering the agent, so it sits where the
            # developer is actually typing rather than up in the action row.
            # To its right, the one-line status says what that model is doing
            # right now, published by agents via session["_stream_status"] and
            # cleared when the stream finalises. The status keeps its reserved
            # line of height so the input row doesn't shift when the first
            # message lands mid-turn; each new message replaces the previous.
            # The chip is suppressed while the gate is open, where the card is
            # already asking the question.
            html.Div(
                [
                    *([] if gate_open else [model_chip(session, active)]),
                    dmc.Text(
                        session.get("_stream_status") or "",
                        id="chat-status-line",
                        c="dimmed",
                        size="xs",
                        style={
                            # Takes the rest of the row so a long status still
                            # ellipsises instead of pushing the chip; minWidth
                            # is what lets a flex child shrink below its
                            # content width at all.
                            "flex": "1",
                            "minWidth": "0",
                            "minHeight": "1.4em",
                            "whiteSpace": "nowrap",
                            "overflow": "hidden",
                            "textOverflow": "ellipsis",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "var(--mantine-spacing-sm)",
                    "marginTop": "4px",
                },
            ),
        ]
    )
