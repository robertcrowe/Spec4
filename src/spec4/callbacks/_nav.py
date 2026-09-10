"""Navigation between agents: the pipeline pills and the Continue buttons.

Split out of :mod:`spec4.callbacks._chat` by cleanup Phase 4g2. Everything here
answers the same question -- which agent is active -- and answers it by writing
``active_agent`` and clearing the display state around it, which is what
``_switch_agent`` does for all of them. The pill is the free-form route; the
``on_*_to_*`` buttons are the pipeline's own forward edges; ``on_rescan_project``
and ``on_deployer_new_project`` are the two that re-enter a stage rather than
advance past one.

The turn, breadth and streaming-poll core stays in :mod:`spec4.callbacks._chat`;
nothing here imports it, and it imports nothing from here.
"""

from __future__ import annotations

from typing import Any

from dash import ALL, Input, Output, State, callback, ctx, no_update

from spec4 import llm_selection
from spec4.app_constants import (
    PROJECT_MODE_EXISTING,
    PROJECT_MODE_NEW,
    STATE_IN_PROGRESS,
)
from spec4.callbacks._shared import _HOME
from spec4.session import reset_for_new_project, validate_agent_preconditions


def _switch_agent(
    session: dict[str, Any],
    target: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Switch active_agent and clear UI display state, preserving the target
    agent's conversation and artifact state.

    The recap helper (`_maybe_inject_resume_summary`) handles resumption when
    `{target}_messages` is non-empty, so navigating between agents picks up
    where the user left off rather than starting from scratch.
    """
    return {
        **session,
        "active_agent": target,
        "messages": [],
        "_initial_turn_done": False,
        # D-ER1: a failure belongs to the turn that produced it. Leaving the flag
        # set would put a Try Again button under the incoming agent's opening
        # turn, where it would retry something the user never saw fail.
        "_stream_error": None,
        **(extra or {}),
    }


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input({"type": "agent-pill", "agent": ALL}, "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_agent_pill_click(n_clicks_list: Any, session: Any) -> Any:
    """Pipeline pill click → navigate to that agent.

    Chat-view pills disable themselves on unmet preconditions, so this check is
    defensive there. The /agents buttons are enabled by `agent_button_state`,
    which is a separate authority and can diverge — when it does, the block is
    reported through `agent_select_error` rather than swallowed (D-BB2).
    """
    if not ctx.triggered_id or not any(n for n in n_clicks_list if n):
        return no_update, no_update
    target = ctx.triggered_id["agent"]
    session = session or {}
    if target == session.get("active_agent") and session.get("phase") == "chat":
        return no_update, no_update
    error = validate_agent_preconditions(target, session)
    if error is not None:
        return {**session, "agent_select_error": error}, no_update
    # No connection, no turn. Entering an agent is what leads to a provider
    # request, so the check belongs here rather than at the point the request
    # is built, where nothing can be done about it but raise. The remembered
    # prefs are not consulted (see `llm_selection.is_connected`): a restored
    # session that has never connected reaches this with a status bar happily
    # naming the previous session's model, and sending it into chat produced a
    # `TypeError` from inside LiteLLM instead of the setup screen it needed.
    if not llm_selection.is_connected(session, target):
        return {**session, "phase": "setup", "agent_select_error": None}, "/setup"
    if target == "designer":
        return {
            **session,
            "phase": "designer",
            "agent_select_error": None,
            # Entering Designer from the project view starts it clean. The
            # snapshot exists to carry a failed draw across the model picker's
            # page rebuild, which happens without ever leaving this route;
            # left behind, it would resurrect an error the developer walked
            # away from — and could re-arm the auto-retry with it. This is
            # where the removed wizard Back button used to discard it, moved
            # to the route in now that the way out is the status bar's
            # Project link.
            "_designer_failed_draw": None,
        }, "/design"
    return _switch_agent(
        session, target, extra={"phase": "chat", "agent_select_error": None}
    ), "/chat"


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-project-mode-existing", "n_clicks"),
    Input("btn-project-mode-new", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_project_mode_choice(n_existing: Any, n_new: Any, session: Any) -> Any:
    """Record whether the working directory holds an existing project (D-PM1).

    Session-only: the answer is never persisted, so the next launch asks again.
    Clearing `agent_select_error` alongside it keeps a stale precondition
    message from surviving into the newly-revealed agent list.
    """
    if not ctx.triggered_id or not (n_existing or n_new):
        return no_update
    mode = (
        PROJECT_MODE_EXISTING
        if ctx.triggered_id == "btn-project-mode-existing"
        else PROJECT_MODE_NEW
    )
    return {**(session or {}), "project_mode": mode, "agent_select_error": None}


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-rescan-project", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_rescan_project(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return {
        **session,
        "code_scanner_messages": [],
        "code_scanner_state": STATE_IN_PROGRESS,
        "code_scanner_artifact_msg_count": None,
        "code_scanner_resumed": False,
        "messages": [],
        "_initial_turn_done": False,
        # D-ER1: the re-scan is a fresh turn, so a prior failure's Try Again
        # panel must not sit over it in the window before the turn starts.
        "_stream_error": None,
    }


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-review-to-brainstormer", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_review_to_brainstormer(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _switch_agent(session, "brainstormer")


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-brainstormer-to-designer", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_brainstormer_to_designer(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return {**session, "phase": "designer"}, "/design"


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-brainstormer-to-agentifier", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_brainstormer_to_agentifier(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return _switch_agent(session, "agentifier", extra={"phase": "chat"}), "/chat"


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-agentifier-to-designer", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_agentifier_to_designer(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return {**session, "phase": "designer"}, "/design"


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-stack-to-phaser", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_stack_to_phaser(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _switch_agent(session, "phaser")


# ---------------------------------------------------------------------------
# Deployer navigation
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-phaser-to-deployer", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_phaser_to_deployer(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _switch_agent(session, "deployer")


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-deployer-new-project", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_deployer_new_project(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    fresh = reset_for_new_project(session or {})
    fresh["phase"] = "working_dir"
    # Open the directory browser at home rather than letting the prefs-stored
    # previous-project path get auto-restored (which would land the developer
    # back on the project they just finished).
    fresh["browser_path"] = _HOME
    return fresh, "/dir"
