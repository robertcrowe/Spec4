"""The blocks that render between the transcript and the composer.

Cleanup Phase 4f moved them out of :mod:`spec4.layouts._chat`. All three share
one contract — each returns ``None`` when it has nothing to say, so the frame
can omit it from the tree — and none of them is part of the pipeline indicator
(:mod:`spec4.layouts._chat_status`) or the action row
(:mod:`spec4.layouts._chat_actions`).

Every name here is re-exported from ``spec4.layouts._chat``, so importing from
either module reaches the same object.
"""

from __future__ import annotations

from typing import Any

from dash import html
import dash_mantine_components as dmc

from spec4 import llm_selection
from spec4.app_constants import (
    STATE_AGENTIFIER_COMPLETE,
    STATE_DEPLOYER_COMPLETE,
    STATE_PHASES_COMPLETE,
    STATE_REVIEW_COMPLETE,
    STATE_STACK_COMPLETE,
    STATE_VISION_COMPLETE,
)
from spec4.agentifier.panel_closure import close_selection, pool_from_dicts
from spec4.layouts._round_cost import run_cost_strip


# When a chat agent's run is complete: the same predicates the action row and
# the status bar use, so the cost card appears exactly when the Download /
# Continue buttons do. Designer is not here — it has no chat turn; its card
# renders on the mock preview step (layouts.designer).
_RUN_COMPLETE: dict[str, tuple[str, str]] = {
    "code_scanner": ("code_scanner_state", STATE_REVIEW_COMPLETE),
    "brainstormer": ("brainstormer_state", STATE_VISION_COMPLETE),
    "agentifier": ("agentifier_state", STATE_AGENTIFIER_COMPLETE),
    "stack_advisor": ("stack_advisor_state", STATE_STACK_COMPLETE),
    "phaser": ("phaser_state", STATE_PHASES_COMPLETE),
    "deployer": ("deployer_state", STATE_DEPLOYER_COMPLETE),
}


def cost_summary(session: dict[str, Any]) -> Any | None:
    """The cost strip for the active agent, on the turn that ended its run.

    The strip itself is ``_round_cost.run_cost_strip`` — the same three-line
    renderer the project view closes with, handed this run's figures instead
    of the round's. Sourcing both from one renderer is the mitigation for the
    chat frame's "the completion cost strip fails to match the round-cost
    presentation" failure mode: there is no second wording to drift.

    What is decided *here* is only whether a run has ended. Two gates, both
    needed. The completion state says the agent has produced its artifact at
    some point; on a Modify run of a completed agent that state stays set
    through every conversational turn, so on its own it put the strip after
    each step. The artifact stamp (``<agent>_artifact_msg_count``, written by
    every agent at the moment it emits its artifact — the same signal the
    resume helper reads) says the artifact is the *last* message: chatting
    past it grows the history and the strip leaves; re-emitting it stamps the
    new length and the strip returns. Never mid-stream.
    """
    if session.get("_stream_id"):
        return None
    # `or ""` rather than a cast: the lookup below is what narrows this to a
    # real agent key — a session with no active agent, or one naming Designer
    # (which has no chat turn), misses `_RUN_COMPLETE` and leaves here.
    active: str = session.get("active_agent") or ""
    gate = _RUN_COMPLETE.get(active)
    if gate is None or session.get(gate[0]) != gate[1]:
        return None
    history = session.get(f"{active}_messages") or []
    stamp = session.get(f"{active}_artifact_msg_count")
    if isinstance(stamp, bool) or not isinstance(stamp, int) or stamp != len(history):
        return None
    return run_cost_strip(session.get("working_dir"), session, active)


def render_retry_panel(session: dict[str, Any]) -> Any | None:
    """Recovery affordance for a turn that died on a provider error (D-ER1).

    Renders only once the failed stream has been finalised — mid-stream the
    progress bar owns the space, and a retry button there would compete with a
    turn that may still succeed. Returns None when there is nothing to recover
    so the caller can omit it from the tree.

    The wording is deliberately concrete about what is and isn't lost: provider
    overloads are transient and the same request usually succeeds on a second
    attempt, but the user has no way to know that from the exception text alone.
    """
    if not session.get("_stream_error") or session.get("_stream_id"):
        return None
    # The panel retries the assistant turn at the end of the transcript, so it
    # only makes sense while that turn is still on screen. This also makes the
    # panel immune to a flag that outlived its turn: every path that starts the
    # chat over (agent switch, re-scan, skip-into-agent) empties `messages`, so
    # a leftover flag renders nothing regardless of who forgot to clear it.
    messages = session.get("messages") or []
    if not messages or messages[-1].get("role") != "assistant":
        return None
    # The model the step ran on, which is also the model Try Again would run it
    # on again — the fact that makes the choice between the two buttons a real
    # one. Read through `llm_selection`, and printed by the one helper the
    # status bar, the model chip and the agent rows print models with, so the
    # panel cannot name the step's model differently from the bar above it.
    agent = str(session.get("active_agent") or "")
    ran_on = llm_selection.model_effort_display(
        (llm_selection.resolve(session, agent) or {}).get("model"),
        llm_selection.effort_for(session, agent),
    )
    return dmc.Alert(
        [
            dmc.Text(
                ["Ran on ", html.Span(ran_on, className="mono"), "."],
                size="sm",
                mb="xs",
            )
            if ran_on
            else html.Div(),
            dmc.Text(
                "That request didn't complete. Nothing already saved is lost. "
                "An overload or rate limit is usually temporary, so running "
                "the same step again often works — but a provider that is "
                "unreachable, a key that was rejected, or a model that cannot "
                "do this step will fail the same way every time. For those, "
                "choose a different provider or model and the step re-runs "
                "on it straight away.",
                size="sm",
                mb="sm",
            ),
            dmc.Group(
                [
                    dmc.Button(
                        "↺ Try Again",
                        id="btn-chat-retry",
                        variant="outline",
                        color="orange",
                        size="sm",
                    ),
                    dmc.Button(
                        "↺ Try a different provider/model",
                        id="btn-chat-retry-model",
                        variant="outline",
                        color="orange",
                        size="sm",
                    ),
                ],
                gap="sm",
            ),
        ],
        title="The last step failed",
        color="orange",
        variant="light",
        mb="md",
    )


def render_breadth_panel(session: dict[str, Any]) -> Any | None:
    """Checkbox panel for Agentifier breadth selection.

    Renders only when agentifier_breadth_groups is set and the user has not yet
    submitted their selection. Returns None when inactive so the caller can
    omit it from the component tree.
    """
    candidates: list[dict[str, str]] | None = session.get("agentifier_breadth_groups")
    if not candidates:
        return None
    if session.get("agentifier_breadth_chosen"):
        return None
    if session.get("_stream_id"):
        # The selection has just been submitted and a stream is running. Hide
        # the panel immediately on Continue instead of waiting for the backend
        # to flip agentifier_breadth_chosen mid-stream.
        return None

    # First paint already reflects panel closure: pre-checked features (the
    # reselection path seeds these) pull in their producers and turn on their
    # coordinators, and the derived/required set is locked. The live callback
    # keeps this in sync as the developer toggles.
    pool = pool_from_dicts(session.get("agentifier_scout_pool") or [])
    closure = close_selection(pool, session.get("agentifier_breadth_selection") or [])
    locked = closure.locked

    # One flat list — there is no relevance ranking to band on, so candidates
    # appear in pool (Composer) order.
    checkboxes: list[Any] = [
        dmc.Checkbox(
            id={"type": "breadth-cb", "name": item["name"]},
            value=item["name"],
            label=html.Strong(item["name"]),
            description=item.get("description", ""),
            disabled=item["name"] in locked,
            # Name and description both render as ordinary chat text:
            # chat-text size (md matches the unstyled Markdown body) and
            # the bubble's own colour, picked up via `inherit` from the
            # enclosing .chat-bubble-assistant so the two never drift.
            # `inherit` also keeps an auto-selected (disabled) candidate
            # readable — the disabled state greys label/description via a
            # zero-specificity rule that these inline styles override, so
            # only the checkbox box shows the disabled cue. The name's
            # weight comes from the <strong> wrapper on the label; the
            # description pins 400 rather than inheriting, since it sits
            # inside the same <label> element and would otherwise pick up
            # whatever weight the cascade lands on.
            styles={
                "label": {
                    "fontSize": "var(--mantine-font-size-md)",
                    "color": "inherit",
                },
                "description": {
                    "fontSize": "var(--mantine-font-size-md)",
                    "fontWeight": 400,
                    "color": "inherit",
                },
            },
            mb="xs",
        )
        for item in candidates
    ]

    return dmc.Paper(
        [
            dmc.CheckboxGroup(
                id="breadth-checkbox-group",
                value=sorted(closure.selected),
                children=checkboxes,
                mb="md",
            ),
            dmc.Group(
                [dmc.Button("Next Step", id="btn-breadth-submit")],
                justify="center",
                mb="md",
            ),
            # Guided redraw (D-TA7). The note is optional: a blank box with Try
            # Again is the plain redraw it always was. Text typed here reaches
            # Scout (and, after Continue, the Tier Analyst) via
            # session["agentifier_retry_guidance"]; see on_breadth_try_again.
            # The main chat-input row is hidden while this panel is up, so this
            # is the only text box on screen. Typed text survives checkbox
            # toggles because on_breadth_change never re-renders the layout.
            # The label lives outside the Textarea (rather than its `label`
            # prop) so the row below can stretch Try Again to the field's
            # height alone, exactly as the Send button matches chat-input —
            # same flex row, same stretch rule in v3.css.
            html.Label(
                "Tell me what to change (optional)",
                htmlFor="breadth-retry-input",
                style={
                    "display": "block",
                    "fontSize": "var(--mantine-font-size-sm)",
                    "fontWeight": 500,
                    "marginBottom": "calc(var(--mantine-spacing-xs) / 2)",
                },
            ),
            html.Div(
                [
                    dmc.Textarea(
                        id="breadth-retry-input",
                        placeholder=(
                            "e.g. Too many — keep only the 3 that matter most "
                            "for the MVP, and prefer simpler approaches."
                        ),
                        autosize=True,
                        minRows=2,
                        style={"flex": "1"},
                    ),
                    dmc.Button(
                        "↺ Try Again",
                        id="btn-breadth-try-again",
                        variant="outline",
                        color="gray",
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "stretch",
                    "gap": "var(--mantine-spacing-sm)",
                    "width": "100%",
                },
            ),
        ],
        p="md",
        radius="md",
        className="chat-bubble-assistant",
        mb="md",
    )
