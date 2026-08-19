from __future__ import annotations

import io
import json
import os
import pathlib
import zipfile
from typing import Any


from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
import dash_mantine_components as dmc

from spec4 import project_manager, providers, streaming, websearch
from spec4.agentifier.panel_closure import close_selection, pool_from_dicts
from spec4.agents._image_probe import probe_image_support
from spec4.agents._tool_probe import probe_tool_support
from spec4.app_constants import (
    PATH_TO_PHASE,
    PROJECT_MODE_EXISTING,
    PROJECT_MODE_NEW,
    STATE_IN_PROGRESS,
)
from spec4.session import (
    _default_session,
    _get_agent_gen,
    _load_working_dir,
    _persist_artifacts,
    _reset_for_new_project,
    _validate_agent_preconditions,
)

_HOME = str(pathlib.Path.home())
_DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"


def _prefs_keep_working_dir(prefs: Any) -> dict[str, Any]:
    """Return a prefs dict retaining only working_dir, or empty dict."""
    if prefs and prefs.get("working_dir"):
        return {"working_dir": prefs["working_dir"]}
    return {}


# ---------------------------------------------------------------------------
# URL / browser history
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("url", "pathname"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_browser_navigate(pathname: Any, session: Any) -> Any:
    """Handle browser back/forward: sync URL → session phase."""
    new_phase = PATH_TO_PHASE.get(pathname, "landing")
    session = session or _default_session()
    if session.get("phase") == new_phase:
        return no_update
    return {**session, "phase": new_phase}


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-setup-back-to-dir", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_setup_back_to_dir(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return {
        **session,
        "phase": "working_dir",
        "available_models": None,
        "setup_error": None,
    }, "/dir"


# ---------------------------------------------------------------------------
# Landing
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-landing-start", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_landing_start(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return {**session, "phase": "working_dir"}, "/dir"


# ---------------------------------------------------------------------------
# Working directory
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Output("prefs", "data", allow_duplicate=True),
    Input("btn-dir-select", "n_clicks"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call=True,
)
def on_dir_select(n: Any, session: Any, prefs: Any) -> Any:
    if not n:
        return no_update, no_update, no_update
    path = session.get("browser_path") or _HOME
    new_prefs = {**(prefs or {}), "working_dir": path}
    new_session = _load_working_dir(path, session)
    # If the developer already has a working LLM connection from a previous
    # project, skip the setup screen and drop them straight into agent select.
    # The "Change provider" button on the agents page is still there if they
    # want to swap models or change their web search provider.
    if new_session.get("llm_config") and new_session.get("model"):
        new_session = {**new_session, "phase": "agent_select"}
        return new_session, "/agents", new_prefs
    return new_session, "/setup", new_prefs


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-dir-up", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_dir_up(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    current = pathlib.Path(session.get("browser_path") or _HOME)
    return {**session, "browser_path": str(current.parent)}


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("dir-path-input", "n_submit"),
    State("dir-path-input", "value"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_dir_path_enter(n: Any, value: Any, session: Any) -> Any:
    if not n or not value:
        return no_update
    p = pathlib.Path(value)
    if p.is_dir():
        return {**session, "browser_path": str(p)}
    return no_update


@callback(
    Output("session", "data", allow_duplicate=True),
    Input({"type": "subdir-btn", "path": ALL}, "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_subdir_click(n_clicks_list: Any, session: Any) -> Any:
    if not ctx.triggered_id or not any(n for n in n_clicks_list if n):
        return no_update
    return {**session, "browser_path": ctx.triggered_id["path"]}


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-create-folder", "n_clicks"),
    State("new-folder-name", "value"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_create_folder(n: Any, name: Any, session: Any) -> Any:
    if not n or not name or not name.strip():
        return no_update
    current = pathlib.Path(session.get("browser_path") or _HOME)
    new_path = current / name.strip()
    try:
        new_path.mkdir(parents=True, exist_ok=True)
        return {**session, "browser_path": str(new_path)}
    except OSError:
        return no_update


# ---------------------------------------------------------------------------
# Setup — step 1: provider + API key
# ---------------------------------------------------------------------------


@callback(
    Output("setup-api-key-hint", "children"),
    Input("setup-provider", "value"),
    prevent_initial_call=False,
)
def on_provider_hint(provider_label: Any) -> Any:
    if providers.provider_key_for_label(provider_label or "") == "bedrock":
        return dmc.Text(
            "Bedrock API key: enter KEY:REGION (e.g. bdak_…:us-east-1). "
            "IAM credentials: ACCESS_KEY_ID:SECRET_ACCESS_KEY:REGION[:SESSION_TOKEN]. "
            "Leave blank to use ambient credentials "
            "(env vars, ~/.aws/credentials, IAM role).",
            size="xs",
            c="dimmed",
        )
    return html.Div()


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("prefs", "data", allow_duplicate=True),
    Input("btn-setup-connect", "n_clicks"),
    State("setup-provider", "value"),
    State("setup-api-key", "value"),
    State("setup-save-prefs", "checked"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call=True,
)
def on_setup_connect(
    n: Any, provider_label: Any, api_key: Any, save_prefs: Any, session: Any, prefs: Any
) -> Any:
    if not n:
        return no_update, no_update
    provider_key = providers.provider_key_for_label(provider_label)
    if provider_key != "bedrock" and (not api_key or not api_key.strip()):
        return {**session, "setup_error": "Please enter an API key."}, no_update

    models, err = providers.list_models(provider_key, (api_key or "").strip())
    if models:
        new_session = {
            **session,
            "provider": provider_key,
            "api_key": (api_key or "").strip(),
            "available_models": models,
            "setup_error": None,
        }
        base = _prefs_keep_working_dir(prefs)
        new_prefs = (
            {
                **prefs,
                "provider": provider_key,
                "api_key": (api_key or "").strip(),
                "save_prefs": True,
            }
            if save_prefs
            else base
        )
        return new_session, new_prefs
    if provider_key == "bedrock":
        if "partial credentials" in err.lower():
            err = (
                "Partial IAM credentials — use ACCESS_KEY_ID:SECRET_ACCESS_KEY:REGION, "
                "or switch to a Bedrock API key (KEY:REGION)."
            )
        elif "unrecognizedclientexception" in err.lower() or (
            "invalid" in err.lower() and "token" in err.lower()
        ):
            err = (
                "AWS credentials rejected. "
                "If you have a Bedrock API key, enter it as KEY:REGION "
                "(e.g. bdak_…:us-east-1). For IAM credentials use "
                "ACCESS_KEY_ID:SECRET_ACCESS_KEY:REGION[:SESSION_TOKEN]."
            )
    return {**session, "setup_error": f"Connection failed: {err}"}, no_update


@callback(
    Output("prefs", "data", allow_duplicate=True),
    Input("btn-setup-clear", "n_clicks"),
    State("prefs", "data"),
    prevent_initial_call=True,
)
def on_setup_clear(n: Any, prefs: Any) -> Any:
    if not n:
        return no_update
    return _prefs_keep_working_dir(prefs)


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-setup-back-provider", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_setup_back_provider(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return {**session, "available_models": None, "setup_error": None}


# ---------------------------------------------------------------------------
# Setup — step 2: model
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("prefs", "data", allow_duplicate=True),
    Output("image-support-store", "data", allow_duplicate=True),
    Output("tool-support-store", "data", allow_duplicate=True),
    Output("notifications-container", "children", allow_duplicate=True),
    Input("btn-setup-model-continue", "n_clicks"),
    State("setup-model", "value"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call=True,
)
def on_setup_model_continue(n: Any, model: Any, session: Any, prefs: Any) -> Any:
    if not n or not model:
        return no_update, no_update, no_update, no_update, no_update
    provider_key = session.get("provider") or ""
    provider_info = providers.PROVIDERS.get(provider_key, {})
    llm_config: dict[str, Any] = {"model": model}
    if "api_base" in provider_info:
        llm_config["api_base"] = provider_info["api_base"]
    if provider_key == "bedrock":
        llm_config.update(providers.bedrock_auth_kwargs(session.get("api_key") or ""))
    else:
        llm_config["api_key"] = session.get("api_key", "")
    new_session = {
        **session,
        "model": model,
        "llm_config": llm_config,
        "setup_error": None,
    }
    new_prefs = {**prefs, "model": model} if prefs.get("save_prefs") else prefs

    # Bedrock Converse is inherently multimodal and tool-capable; probing
    # via non-streaming completion calls is unreliable against the Converse
    # API, so skip it and assume both are supported.
    if provider_key == "bedrock":
        return new_session, new_prefs, True, True, no_update

    api_key = llm_config.get("api_key") or ""
    api_base = llm_config.get("api_base")
    aws_kwargs = {k: v for k, v in llm_config.items() if k.startswith("aws_")}

    image_support: bool | None = None
    try:
        image_support = probe_image_support(
            model, api_key, api_base=api_base, **aws_kwargs
        )
    except Exception:
        image_support = None

    tool_support: bool | None = None
    try:
        tool_support = probe_tool_support(
            model, api_key, api_base=api_base, **aws_kwargs
        )
    except Exception:
        tool_support = None

    return new_session, new_prefs, image_support, tool_support, no_update


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-setup-back-model", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_setup_back_model(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return {**session, "model": None, "llm_config": None, "setup_error": None}


# ---------------------------------------------------------------------------
# Setup — step 3: web search provider
# ---------------------------------------------------------------------------


@callback(
    Output("setup-search-key", "label"),
    Output("setup-search-key", "placeholder"),
    Output("setup-search-hint", "children"),
    Input("setup-search-provider", "value"),
    prevent_initial_call=False,
)
def on_search_provider_hint(provider_label: Any) -> Any:
    """Retitle the key field and describe whichever provider is selected."""
    key = websearch.provider_key_for_label(provider_label or "")
    spec = websearch.PROVIDERS[key]
    hint = dmc.Text(
        [
            f"{spec['blurb']} Get a key at ",
            html.A(
                spec["signup_url"],
                href=spec["signup_url"],
                target="_blank",
                style={"color": "inherit"},
            ),
            ".",
        ],
        size="xs",
        c="dimmed",
    )
    return spec["key_label"], spec["placeholder"], hint


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("prefs", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-setup-search-connect", "n_clicks"),
    State("setup-search-provider", "value"),
    State("setup-search-key", "value"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call=True,
)
def on_setup_search_connect(
    n: Any, provider_label: Any, search_key: Any, session: Any, prefs: Any
) -> Any:
    if not n:
        return no_update, no_update, no_update
    provider = websearch.provider_key_for_label(provider_label or "")
    label = websearch.label_for_provider(provider)
    if not search_key or not search_key.strip():
        return (
            {**session, "setup_error": f"Please enter a {label} API key."},
            no_update,
            no_update,
        )
    key = search_key.strip()
    ok, _, err = websearch.validate(websearch.SearchConfig(provider, key))
    if ok:
        new_session = {
            **session,
            "search_provider": provider,
            "search_api_key": key,
            # Cleared so a stale pre-Exa key cannot outrank the new choice:
            # `websearch.from_session` falls back to it when search_api_key is
            # empty, which would silently route to Tavily.
            "tavily_api_key": None,
            "setup_error": None,
            "phase": "agent_select",
        }
        new_prefs = (
            {
                **prefs,
                "search_provider": provider,
                "search_key": key,
                "tavily_key": None,
            }
            if prefs.get("save_prefs")
            else prefs
        )
        return new_session, new_prefs, "/agents"
    return (
        {**session, "setup_error": f"{label} connection failed: {err}"},
        no_update,
        no_update,
    )


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-setup-search-skip", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_setup_search_skip(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return {
        **session,
        "search_provider": None,
        "search_api_key": None,
        # Also cleared: `from_session` reads it as a fallback, so leaving it set
        # would turn "Skip" into "keep using the old Tavily key".
        "tavily_api_key": None,
        "setup_error": None,
        "phase": "agent_select",
    }, "/agents"


# ---------------------------------------------------------------------------
# Agent select
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Chat — back to agent select
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-chat-back", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_chat_back(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return {**session, "phase": "agent_select"}, "/agents"


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-agent-change-provider", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_agent_change_provider(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return {
        **session,
        "phase": "setup",
        "available_models": None,
        "model": None,
        "llm_config": None,
        "setup_error": None,
        "agent_select_error": None,
    }, "/setup"


# ---------------------------------------------------------------------------
# Chat — initial turn
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("stream-poll-interval", "max_intervals"),
    Input("init-turn-interval", "n_intervals"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_init_turn(n: Any, session: Any) -> Any:
    if not n or session.get("_initial_turn_done") or session.get("messages"):
        return no_update, no_update
    gen = _get_agent_gen(None, session)
    stream_id = streaming.start(gen, session)
    return (
        {
            **session,
            "messages": [{"role": "assistant", "content": ""}],
            "_stream_id": stream_id,
            "_initial_turn_done": True,
            "_stream_error": None,
        },
        -1,
    )


# ---------------------------------------------------------------------------
# Chat — user message
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("chat-input", "value"),
    Output("stream-poll-interval", "max_intervals"),
    Input("btn-chat-submit", "n_clicks"),
    Input("chat-input", "n_submit"),
    State("chat-input", "value"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_chat_submit(n_clicks: Any, n_submit: Any, user_input: Any, session: Any) -> Any:
    if not user_input or not user_input.strip():
        return no_update, no_update, no_update
    if session.get("_stream_id"):
        return no_update, no_update, no_update
    messages = list(session.get("messages", []))
    messages.append({"role": "user", "content": user_input.strip()})
    messages.append({"role": "assistant", "content": ""})
    gen = _get_agent_gen(user_input.strip(), session)
    stream_id = streaming.start(gen, session)
    return (
        {
            **session,
            "messages": messages,
            "_stream_id": stream_id,
            "_stream_error": None,
        },
        "",
        -1,
    )


# ---------------------------------------------------------------------------
# Chat — StackAdvisor Fast Forward
# ---------------------------------------------------------------------------

# The developer's sweep instruction lives in app_constants (single source:
# the Agentifier's Python-paced phases match against it too, and importing
# callbacks from agentifier would be circular). Re-exported here so the
# button callback and existing imports keep one name.
from spec4.app_constants import FF_PROMPT  # noqa: E402


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("stream-poll-interval", "max_intervals", allow_duplicate=True),
    Input("btn-chat-fast-forward", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_fast_forward(n_clicks: Any, session: Any) -> Any:
    if not n_clicks:
        return no_update, no_update
    # Turn-integrity guard: ignore clicks while a stream is in flight.
    if session.get("_stream_id"):
        return no_update, no_update
    messages = list(session.get("messages", []))
    messages.append({"role": "user", "content": FF_PROMPT})
    messages.append({"role": "assistant", "content": ""})
    gen = _get_agent_gen(FF_PROMPT, session)
    stream_id = streaming.start(gen, session)
    return (
        {
            **session,
            "messages": messages,
            "_stream_id": stream_id,
            "_stream_error": None,
        },
        -1,
    )


# ---------------------------------------------------------------------------
# Chat — retry after a failed turn
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("stream-poll-interval", "max_intervals", allow_duplicate=True),
    Input("btn-chat-retry", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_chat_retry(n_clicks: Any, session: Any) -> Any:
    """Re-run the turn that failed (D-ER1).

    A provider error (overload, rate limit, dropped connection) leaves the
    formatted exception as the assistant message and no state transition, and
    until now offered the user nothing to click. This replays the same turn.

    The failed assistant bubble is dropped so the retry streams into a fresh
    one. What gets re-sent is whatever the dead turn was sent: the user message
    it was answering when one precedes it, or ``None`` for an agent-opening turn
    such as the CodeScanner scan. The agents' own orphan handling
    (``_drop_orphan_or_route_to_fresh_start``) discards the half-finished
    exchange their message history is carrying, so a retried opening turn
    re-seeds from session state rather than resuming mid-sentence.
    """
    if not n_clicks:
        return no_update, no_update
    if session.get("_stream_id"):
        return no_update, no_update
    messages = list(session.get("messages") or [])
    if messages and messages[-1].get("role") == "assistant":
        messages.pop()
    retry_input: str | None = None
    if messages and messages[-1].get("role") == "user":
        retry_input = messages[-1].get("content")
    messages.append({"role": "assistant", "content": ""})
    gen = _get_agent_gen(retry_input, session)
    stream_id = streaming.start(gen, session)
    return (
        {
            **session,
            "messages": messages,
            "_stream_id": stream_id,
            "_stream_error": None,
        },
        -1,
    )


@callback(
    Output("ff-info-modal", "opened"),
    Input("btn-ff-info", "n_clicks"),
    prevent_initial_call=True,
)
def on_ff_info(n_clicks: Any) -> Any:
    """Open the Fast Forward info dialog; the modal closes itself client-side."""
    if not n_clicks:
        return no_update
    return True


# ---------------------------------------------------------------------------
# Chat — Agentifier breadth selection
# ---------------------------------------------------------------------------


def _breadth_summary(selected: list[str]) -> str:
    """Human-readable summary of the checkbox selection for the chat bubble."""
    if not selected:
        return "Selected no features."
    names = ", ".join(selected[:5])
    if len(selected) > 5:
        names += f" … and {len(selected) - 5} more"
    plural = "s" if len(selected) != 1 else ""
    return f"Selected {len(selected)} feature{plural}: {names}"


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("stream-poll-interval", "max_intervals", allow_duplicate=True),
    Input("btn-breadth-submit", "n_clicks"),
    State("breadth-checkbox-group", "value"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_breadth_submit(n_clicks: Any, selected: Any, session: Any) -> Any:
    if not n_clicks:
        return no_update, no_update
    if session.get("_stream_id"):
        return no_update, no_update
    selected = selected or []
    session["agentifier_breadth_selection"] = selected
    summary = _breadth_summary(selected)
    messages = list(session.get("messages", []))
    messages.append({"role": "user", "content": summary})
    messages.append({"role": "assistant", "content": ""})
    gen = _get_agent_gen(summary, session)
    stream_id = streaming.start(gen, session)
    return (
        {
            **session,
            "messages": messages,
            "_stream_id": stream_id,
            "_stream_error": None,
        },
        -1,
    )


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("stream-poll-interval", "max_intervals", allow_duplicate=True),
    Input("btn-breadth-try-again", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_breadth_try_again(n_clicks: Any, session: Any) -> Any:
    """Discard the current candidate set and run Scout again (D-TA2).

    Session-only. Nothing on disk is touched: the reset demotes
    ``agentifier_state``, which is the sole condition under which
    ``_persist_artifacts`` writes ``ai_features.json``, so the current round's
    artifact is retained until the flow re-completes and replaces it. Earlier
    implemented rounds are read (for revision carry-forward) but never written.

    With the flow reset, ``agentifier_messages`` empty and the cached pool
    cleared, ``run(None, …)`` dispatches to ``_run_catalog_phase``'s fresh-start
    branch — the same route the stale-input rediscovery takes — which re-derives
    the revision block from disk. That is what makes Try Again inside a revision
    round produce a genuinely new candidate set rather than re-opening the
    reselection panel over the old one.
    """
    from spec4.agentifier.agentifier import reset_agentifier_flow

    if not n_clicks:
        return no_update, no_update
    if session.get("_stream_id"):
        return no_update, no_update
    session = dict(session or {})
    reset_agentifier_flow(session)
    messages = list(session.get("messages", []))
    messages.append(
        {"role": "user", "content": "Try Again — draw a new set of candidates."}
    )
    messages.append({"role": "assistant", "content": ""})
    gen = _get_agent_gen(None, session)
    stream_id = streaming.start(gen, session)
    return (
        {
            **session,
            "messages": messages,
            "_stream_id": stream_id,
            "_stream_error": None,
        },
        -1,
    )


@callback(
    Output("breadth-checkbox-group", "value"),
    Output("breadth-intent-store", "data"),
    Output({"type": "breadth-cb", "name": ALL}, "disabled"),
    Input("breadth-checkbox-group", "value"),
    State("breadth-intent-store", "data"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_breadth_change(value: Any, intent_store: Any, session: Any) -> Any:
    """Live panel closure: as the developer toggles a candidate, force-check and
    lock the producers a selected feature requires, and turn coordinators on/off
    by member count — mirroring the authoritative backend closure at submit.
    """
    if not session or not session.get("agentifier_breadth_groups"):
        return no_update, no_update, no_update
    if session.get("agentifier_breadth_chosen"):
        return no_update, no_update, no_update

    pool = pool_from_dicts(session.get("agentifier_scout_pool") or [])

    # Developer intent is tracked apart from the checkbox value, so a
    # force-checked producer can never mask or silently drop one the developer
    # picked independently. Reset to the panel's seed when the nonce changes.
    nonce = session.get("agentifier_breadth_nonce")
    store = intent_store if isinstance(intent_store, dict) else {}
    if store.get("nonce") != nonce:
        intent = set(session.get("agentifier_breadth_selection") or [])
    else:
        intent = set(store.get("intent") or [])

    # The displayed value before this event was closure(intent); only enabled
    # checkboxes can be toggled, so any difference is a genuine developer action.
    prev_display = close_selection(pool, intent).selected
    value_set = set(value or [])
    for name in value_set ^ prev_display:
        if name in value_set:
            intent.add(name)
        else:
            intent.discard(name)

    result = close_selection(pool, intent)
    disabled = [o["id"]["name"] in result.locked for o in ctx.outputs_list[2]]
    return (
        sorted(result.selected),
        {"nonce": nonce, "intent": sorted(intent)},
        disabled,
    )


# ---------------------------------------------------------------------------
# Chat — streaming poll
# ---------------------------------------------------------------------------


# D-ER2: stands in for a turn that produced no visible text at all. Deliberately
# does not claim anything about what was or wasn't saved — the poll cannot know,
# and the developer's next move is the same either way.
_EMPTY_TURN_NOTICE = (
    "_This step finished without producing a response — the model's reply "
    "either came back empty or could not be read. Nothing is lost; use Try "
    "Again below to re-run the step._"
)


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("stream-poll-interval", "max_intervals", allow_duplicate=True),
    Input("stream-poll-interval", "n_intervals"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_stream_poll(n: Any, session: Any) -> Any:
    stream_id = session.get("_stream_id")
    if not stream_id:
        return no_update, 0

    stream = streaming.get(stream_id)
    if not stream:
        if _DEV_MODE:
            print(
                f"[poll {stream_id[:8]}] stream entry missing — another poll already "
                f"finalised this stream; leaving authoritative session intact",
                flush=True,
            )
        # Entries are evicted at the next start(), not in the done branch, so a
        # missing entry means this stream was already finalised and the store's
        # _stream_id is already None (a later turn has begun or is about to).
        # Return no_update to avoid clobbering the authoritative session from our
        # stale State snapshot.
        return no_update, 0

    text = stream["text"]
    messages = list(session.get("messages", []))
    if messages:
        messages[-1] = {"role": "assistant", "content": text}
    # D-PH9: the phaser validation-retry drain yields no visible text, so the
    # displayed message freezes; the generator publishes a cumulative
    # received-character total on the live (agent-mutated) session instead.
    # Surface that scalar so the token counter keeps climbing during the drain,
    # and re-render when it advances even though the displayed text has not.
    received = stream["session"].get("_stream_received_chars")
    # The one-line status under the chat input rides the same live-session
    # channel as the received-chars scalar: agents overwrite it stage by stage,
    # and the poll surfaces the latest value mid-stream.
    status = stream["session"].get("_stream_status")

    if not stream["done"]:
        prev = (session.get("messages") or [{}])[-1].get("content", "")
        if (
            text == prev
            and received == session.get("_stream_received_chars")
            and status == session.get("_stream_status")
        ):
            return no_update, no_update
        updated = {**session, "messages": messages}
        updated["_stream_received_chars"] = received
        updated["_stream_status"] = status
        return updated, no_update

    # Stream complete — merge agent-mutated session and finalise
    if _DEV_MODE:
        print(
            f"[poll {stream_id[:8]}] done branch firing; text_len={len(text)}, "
            f"messages_count={len(messages)}, "
            f"last_msg_preview={text[:120]!r}",
            flush=True,
        )
    # Read (do NOT pop) the agent-mutated session from the live entry. Eviction
    # happens at the next start(); leaving the entry in place means two polls
    # racing into this branch both read the same authoritative session and return
    # a byte-identical terminal store — whichever Dash applies last, _stream_id
    # ends up None and the agent mutations survive. Sourcing from stream["session"]
    # (never the stale State snapshot) preserves the no-clobber guarantee.
    agent_session = stream["session"]
    try:
        _persist_artifacts(agent_session)
    except Exception as exc:  # persistence is a side effect — never strand the chat
        if _DEV_MODE:
            print(
                f"[poll {stream_id[:8]}] _persist_artifacts failed "
                f"({type(exc).__name__}: {exc}); finalising anyway",
                flush=True,
            )
    if agent_session.get("_display_override") is not None and messages:
        messages[-1] = {
            "role": "assistant",
            "content": agent_session["_display_override"],
        }
        if _DEV_MODE:
            print(
                f"[poll {stream_id[:8]}] _display_override applied "
                f"(len={len(agent_session['_display_override'])})",
                flush=True,
            )
    # D-ER2: a finished turn whose assistant message is empty is never correct —
    # it renders as a blank bubble with no controls under it, which reads as the
    # app hanging. It happens when a generator returns without yielding and
    # without setting a display override: an artifact reply that was suppressed
    # on its way to the screen and then failed to parse takes exactly that path.
    # Agents fix their own causes; this is the last line of defence, and it
    # routes the turn into the same Try Again recovery a raised exception gets.
    empty_turn = bool(
        messages
        and messages[-1].get("role") == "assistant"
        and not (messages[-1].get("content") or "").strip()
    )
    if empty_turn:
        messages[-1] = {"role": "assistant", "content": _EMPTY_TURN_NOTICE}
        if _DEV_MODE:
            print(
                f"[poll {stream_id[:8]}] empty assistant turn — substituting "
                f"the notice and enabling retry",
                flush=True,
            )
    return (
        {
            **agent_session,
            "messages": messages,
            "_stream_id": None,
            "_initial_turn_done": True,
            "_display_override": None,
            "_stream_received_chars": None,
            "_stream_status": None,
            # D-ER1: the turn died and the error text is the whole assistant
            # message. Record that so the chat can offer Try Again; a clean
            # finish writes None here and retires any earlier failure.
            "_stream_error": True if (stream.get("error") or empty_turn) else None,
        },
        0,
    )


# ---------------------------------------------------------------------------
# Chat — navigation
# ---------------------------------------------------------------------------


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
    error = _validate_agent_preconditions(target, session)
    if error is not None:
        return {**session, "agent_select_error": error}, no_update
    if target == "designer":
        return {
            **session,
            "phase": "designer",
            "agent_select_error": None,
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
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-stack-to-designer", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_stack_to_designer(n: Any, session: Any) -> Any:
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


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-phaser-to-stack", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_phaser_to_stack(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _switch_agent(session, "stack_advisor")


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------


def _send_json(data: Any, filename: str) -> Any:
    return dcc.send_string(  # type: ignore[attr-defined, no-untyped-call]
        json.dumps(data or {}, indent=2), filename, type="application/json"
    )


def _build_phases_zip(session: dict[str, Any]) -> Any:
    phases = session.get("phases", [])
    version = session.get("phase_version") or 0
    # Same context bundle the on-disk save uses, so the downloaded phases carry
    # the identical verbatim spec preamble.
    context = {"ai_features": session.get("ai_features")}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for phase in phases:
            zf.writestr(
                f"v{version}/phases/phase{phase['phase_number']}.md",
                project_manager.render_phase_markdown(phase, context),
            )
    buf.seek(0)
    return dcc.send_bytes(buf.read(), "phases.zip")  # type: ignore[attr-defined, no-untyped-call]


@callback(
    Output("dl-vision", "data"),
    Input("btn-dl-vision", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_vision(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _send_json(session.get("vision_statement"), "vision.json")


@callback(
    Output("dl-stack", "data"),
    Input("btn-dl-stack", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_stack(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _send_json(session.get("stack_statement"), "stack.json")


@callback(
    Output("dl-code-review", "data"),
    Input("btn-dl-review", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_code_review(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _send_json(session.get("code_review"), "code_review.json")


@callback(
    Output("dl-features", "data"),
    Input("btn-dl-features", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_features(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _send_json(session.get("ai_features"), "ai_features.json")


@callback(
    Output("dl-phases", "data"),
    Input("btn-dl-phases", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_phases(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _build_phases_zip(session)


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
    Input("btn-deployer-to-phaser", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_deployer_to_phaser(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    return _switch_agent(session, "phaser")


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
    fresh = _reset_for_new_project(session or {})
    fresh["phase"] = "working_dir"
    # Open the directory browser at home rather than letting the prefs-stored
    # previous-project path get auto-restored (which would land the developer
    # back on the project they just finished).
    fresh["browser_path"] = _HOME
    return fresh, "/dir"


@callback(
    Output("dl-deployment", "data"),
    Input("btn-dl-deployment", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def dl_deployment(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    messages = session.get("deployer_messages") or []
    md = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "assistant"),
        "",
    )
    return dcc.send_string(md, "deployment-plan.md", type="text/markdown")  # type: ignore[attr-defined, no-untyped-call]
