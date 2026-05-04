from __future__ import annotations

import io
import json
import pathlib
import zipfile
from typing import Any


from dash import ALL, Input, Output, State, callback, ctx, dcc, no_update

from spec4 import providers, streaming, tavily_mcp
from spec4.agents._image_probe import probe_image_support
from spec4.app_constants import PATH_TO_PHASE
from spec4.session import (
    _default_session,
    _get_agent_gen,
    _load_working_dir,
    _persist_artifacts,
    _validate_agent_preconditions,
)

_HOME = str(pathlib.Path.home())


def _prefs_keep_working_dir(prefs: Any) -> dict[str, Any]:
    """Return a prefs dict retaining only working_dir, or empty dict."""
    return {"working_dir": prefs["working_dir"]} if prefs and prefs.get("working_dir") else {}


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
    return _load_working_dir(path, session), "/setup", new_prefs


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
    if not api_key or not api_key.strip():
        return {**session, "setup_error": "Please enter an API key."}, no_update

    provider_key = providers.provider_key_for_label(provider_label)
    models, err = providers.list_models(provider_key, api_key.strip())
    if models:
        new_session = {
            **session,
            "provider": provider_key,
            "api_key": api_key.strip(),
            "available_models": models,
            "setup_error": None,
        }
        base = _prefs_keep_working_dir(prefs)
        new_prefs = (
            {
                **prefs,
                "provider": provider_key,
                "api_key": api_key.strip(),
                "save_prefs": True,
            }
            if save_prefs
            else base
        )
        return new_session, new_prefs
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
    Output("notifications-container", "children", allow_duplicate=True),
    Input("btn-setup-model-continue", "n_clicks"),
    State("setup-model", "value"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call=True,
)
def on_setup_model_continue(n: Any, model: Any, session: Any, prefs: Any) -> Any:
    if not n or not model:
        return no_update, no_update, no_update, no_update
    new_session = {
        **session,
        "model": model,
        "llm_config": {"model": model, "api_key": session["api_key"]},
        "setup_error": None,
    }
    new_prefs = {**prefs, "model": model} if prefs.get("save_prefs") else prefs

    image_support: bool | None = None
    try:
        image_support = probe_image_support(model, session.get("api_key") or "")
    except Exception:
        image_support = None

    return new_session, new_prefs, image_support, no_update


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
# Setup — step 3: Tavily
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("prefs", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-setup-tavily-connect", "n_clicks"),
    State("setup-tavily-key", "value"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call=True,
)
def on_setup_tavily_connect(n: Any, tavily_key: Any, session: Any, prefs: Any) -> Any:
    if not n:
        return no_update, no_update, no_update
    if not tavily_key or not tavily_key.strip():
        return (
            {**session, "setup_error": "Please enter a Tavily API key."},
            no_update,
            no_update,
        )
    ok, _, err = tavily_mcp.validate(tavily_key.strip())
    if ok:
        new_session = {
            **session,
            "tavily_api_key": tavily_key.strip(),
            "setup_error": None,
            "phase": "agent_select",
        }
        new_prefs = (
            {**prefs, "tavily_key": tavily_key.strip()}
            if prefs.get("save_prefs")
            else prefs
        )
        return new_session, new_prefs, "/agents"
    return (
        {**session, "setup_error": f"Tavily connection failed: {err}"},
        no_update,
        no_update,
    )


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-setup-tavily-skip", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_setup_tavily_skip(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return {
        **session,
        "tavily_api_key": None,
        "setup_error": None,
        "phase": "agent_select",
    }, "/agents"


# ---------------------------------------------------------------------------
# Agent select
# ---------------------------------------------------------------------------


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-agent-start", "n_clicks"),
    State("agent-select-radio", "value"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_agent_start(n: Any, agent_choice: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update

    err = _validate_agent_preconditions(agent_choice, session)
    if err:
        return {**session, "agent_select_error": err}, no_update
    if agent_choice == "designer":
        return {**session, "agent_select_error": None, "phase": "designer"}, "/design"
    return {
        **session,
        "agent_select_error": None,
        "active_agent": agent_choice,
        "phase": "chat",
        "messages": [],
        "_initial_turn_done": False,
    }, "/chat"


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
    return {**session, "messages": messages, "_stream_id": stream_id}, "", -1


# ---------------------------------------------------------------------------
# Chat — streaming poll
# ---------------------------------------------------------------------------


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
        return {**session, "_stream_id": None}, 0

    text = stream["text"]
    messages = list(session.get("messages", []))
    if messages:
        messages[-1] = {"role": "assistant", "content": text}

    if not stream["done"]:
        prev = (session.get("messages") or [{}])[-1].get("content", "")
        if text == prev:
            return no_update, no_update
        return {**session, "messages": messages}, no_update

    # Stream complete — merge agent-mutated session and finalise
    final = streaming.pop(stream_id)
    if final is None:
        return {**session, "_stream_id": None}, 0
    agent_session = final["session"]
    _persist_artifacts(agent_session)
    if agent_session.get("_display_override") is not None and messages:
        messages[-1] = {"role": "assistant", "content": agent_session["_display_override"]}
    return (
        {
            **agent_session,
            "messages": messages,
            "_stream_id": None,
            "_initial_turn_done": True,
            "_display_override": None,
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
    """Switch active_agent and reset its message history in a session dict copy."""
    return {
        **session,
        "active_agent": target,
        f"{target}_messages": [],
        "messages": [],
        "_initial_turn_done": False,
        **(extra or {}),
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
    return _switch_agent(session, "phaser", {"phaser_state": None, "phases": []})


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
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for phase in phases:
            zf.writestr(
                f"phase{phase['phase_number']}.json", json.dumps(phase, indent=2)
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
    return _switch_agent(session, "phaser", {"phaser_state": None, "phases": []})


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
    return {**session, "phase": "landing"}, "/"


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
