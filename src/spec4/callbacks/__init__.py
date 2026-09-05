from __future__ import annotations

import io
import json
import os
import pathlib
import zipfile
from typing import Any


from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
import dash_mantine_components as dmc

from spec4 import llm_selection, project_manager, providers, streaming, websearch
from spec4.agentifier.panel_closure import close_selection, pool_from_dicts
from spec4.layouts._llm_gate import is_open as _gate_is_open
from spec4.layouts._setup import GATE_IDS, provider_key_hint
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
        key = (api_key or "").strip()
        new_prefs = (
            {
                **prefs,
                "provider": provider_key,
                "api_key": key,
                # Keyed by provider so a per-agent override on a different
                # provider has somewhere to prefill from. Written only under
                # the same "Remember" consent as the single key above.
                "provider_keys": {
                    **(prefs.get("provider_keys") or {}),
                    provider_key: key,
                },
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
    llm_config = llm_selection.build_llm_config(
        provider_key, model, session.get("api_key")
    )
    new_session = {
        **session,
        "model": model,
        "llm_config": llm_config,
        "setup_error": None,
    }
    new_prefs = {**prefs, "model": model} if prefs.get("save_prefs") else prefs

    # The config is committed above, before the probes run and whatever they
    # return: capability probing is advisory and must never cost the developer
    # a working connection. `llm_selection.probe_capabilities` owns the Bedrock
    # skip and the never-raises contract, so the per-agent gate gets identical
    # behaviour from the same call.
    image_support, tool_support = llm_selection.probe_capabilities(
        provider_key, llm_config
    )
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
    # The layout already disables the interval while the gate is open; this is
    # the belt to that braces, so a stale tick cannot start a turn on a model
    # the developer has not agreed to.
    if _gate_is_open(session, session.get("active_agent") or ""):
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
    # Turn-integrity guard: ignore clicks while a stream is in flight, or while
    # the model gate is still unanswered — FF is a turn like any other and must
    # not slip past a choice the developer has not made.
    if session.get("_stream_id"):
        return no_update, no_update
    if _gate_is_open(session, session.get("active_agent") or ""):
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
# Per-agent model gate
# ---------------------------------------------------------------------------
#
# One set of callbacks for all seven agents and both surfaces: only one gate is
# ever open, and the agent it belongs to is carried in `agent_llm_draft`. The
# gate answers a question the setup wizard already answers for the default, so
# both go through the same builder and probe wrapper in `llm_selection` — a
# Bedrock credential parsed one way here and another way there is exactly the
# drift this shares code to prevent.


def _gate_agent(session: dict[str, Any]) -> str:
    """Which agent the open gate belongs to."""
    draft = session.get("agent_llm_draft") or {}
    if draft.get("agent"):
        return str(draft["agent"])
    if session.get("phase") == "designer":
        return "designer"
    return str(session.get("active_agent") or "brainstormer")


def _gate_answered(session: dict[str, Any], agent: str, **extra: Any) -> dict[str, Any]:
    """Close the gate for `agent`, clearing the draft and any error."""
    asked = {**(session.get("agent_llm_asked") or {}), agent: True}
    return {
        **session,
        "agent_llm_asked": asked,
        "agent_llm_draft": None,
        "agent_llm_error": None,
        **extra,
    }


@callback(
    Output(GATE_IDS["hint"], "children"),
    Output(GATE_IDS["api_key"], "value"),
    Input(GATE_IDS["provider"], "value"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call=False,
)
def on_gate_provider_change(provider_label: Any, session: Any, prefs: Any) -> Any:
    """Update the credential hint and the key field for the chosen provider.

    Refilling the key matters here in a way it does not in the setup wizard.
    The gate opens with the provider Select on the *default's* provider, so the
    box starts holding the default's key; switching the Select to another
    provider without clearing it submits one provider's credential to another.
    That is a 401 at the first real call — and for OpenRouter, whose model list
    answers the same for any bearer, Connect could not catch it either.

    The draft's own provider is left alone: re-opening "pick a different model"
    prefills the key from the existing override, and the initial render must not
    wipe it.
    """
    provider_key = providers.provider_key_for_label(provider_label or "")
    hint = provider_key_hint(provider_label or "")
    draft = (session or {}).get("agent_llm_draft") or {}
    if draft.get("provider") == provider_key and draft.get("api_key") is not None:
        return hint, no_update
    return hint, llm_selection.key_for_provider(
        session or {}, prefs or {}, provider_key
    )


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-agent-llm-default", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_gate_use_default(n: Any, session: Any) -> Any:
    """Answer "use the default" — which stores no entry.

    Dropping any existing override is what makes the answer live: the agent
    resolves against `llm_config` from now on and follows the default if the
    developer later changes it.
    """
    if not n:
        return no_update
    agent = _gate_agent(session)
    overrides = {
        k: v for k, v in (session.get("agent_llm") or {}).items() if k != agent
    }
    return _gate_answered(session, agent, agent_llm=overrides)


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-agent-llm-keep", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_gate_keep(n: Any, session: Any) -> Any:
    """Keep a carried-forward override: no key re-entry, no re-probe.

    The entry survived `_reset_for_new_project` intact — credential, model list
    and both capability flags — so answering costs nothing but the flag.
    """
    if not n:
        return no_update
    return _gate_answered(session, _gate_agent(session))


def _open_pick_fields(
    session: dict[str, Any], *, retry: bool = False
) -> dict[str, Any]:
    """Expand the gate into the provider/key/model fields.

    Seeded from any existing override, so an unchanged provider and key need no
    Connect round trip: the model list came with the entry, which is what makes
    "pick a different model" one click and a dropdown rather than a re-type.

    ``retry`` marks a picker opened from a failed step. Two things follow from
    it, and *only* from it — a picker opened deliberately (the chip, or agent
    entry) behaves exactly as before:

    * choosing a model re-runs the failed step immediately, and
    * a model the tool probe reports as incapable is refused rather than
      committed.

    The second bends the rule that probes are advisory and never block. It is
    bent here because this is the one path where the app spends a call without
    asking again, and it must not spend it on a model just measured as unable to
    do the step.
    """
    agent = _gate_agent(session)
    existing = llm_selection.entry(session, agent) or {}
    draft: dict[str, Any] = {"agent": agent}
    if retry:
        draft["retry"] = True
    if existing:
        draft.update(
            {
                "provider": existing.get("provider"),
                "api_key": (existing.get("llm_config") or {}).get("api_key", ""),
                "available_models": existing.get("available_models") or [],
                "model": existing.get("model"),
            }
        )
    return {**session, "agent_llm_draft": draft, "agent_llm_error": None}


# The gate button and the chip open the same fields but live in different
# subtrees — the chip is suppressed while the gate is open, and never renders at
# all on the Designer surface. They therefore need one callback each: Dash
# refuses to dispatch a callback whose Inputs are not all present in the current
# layout, so pairing them would break whichever one is on screen.
@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-agent-llm-pick", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_gate_pick(n: Any, session: Any) -> Any:
    """Open the fields from the gate card itself, at agent entry."""
    if not n:
        return no_update
    return _open_pick_fields(session)


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-agent-llm-chip", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_gate_chip(n: Any, session: Any) -> Any:
    """Re-open the same card mid-agent, from the control-row chip.

    Refused while a turn is streaming: that turn is already committed to a
    config, and changing the label under it would misreport what produced the
    answer on screen. A change made here applies from the next turn, which the
    per-turn resolution in `_get_agent_gen` gives for free.
    """
    if not n or session.get("_stream_id"):
        return no_update
    return _open_pick_fields(session)


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-chat-retry-model", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_chat_retry_model(n: Any, session: Any) -> Any:
    """Open the model picker from the failed-turn panel.

    Retrying a step on the model that just failed is the right move for an
    overload and useless for an unreachable provider or a rejected key. This is
    the second door out of that panel: pick a different provider/model, then the
    panel's own Try Again re-runs the step on it.

    Deliberately does *not* retry by itself — the step may be expensive, and the
    developer may still back out of the picker. It only opens the fields; the
    gate's answer preserves `_stream_error` and the transcript, so the retry
    panel is still there afterwards.

    Its own callback rather than sharing the chip's: the chip and this button
    render in different subtrees, and Dash refuses to dispatch a callback whose
    Inputs are not all on screen.
    """
    if not n or session.get("_stream_id"):
        return no_update
    return _open_pick_fields(session, retry=True)


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-agent-llm-back", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_gate_back(n: Any, session: Any) -> Any:
    """Collapse the fields back to the resting card, discarding the draft."""
    if not n:
        return no_update
    return {**session, "agent_llm_draft": None, "agent_llm_error": None}


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("prefs", "data", allow_duplicate=True),
    Input("btn-agent-llm-connect", "n_clicks"),
    State(GATE_IDS["provider"], "value"),
    State(GATE_IDS["api_key"], "value"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call=True,
)
def on_gate_connect(
    n: Any, provider_label: Any, api_key: Any, session: Any, prefs: Any
) -> Any:
    """Fetch the model list — the hard gate, exactly as in the setup wizard.

    No models means nothing is written: no draft models, no entry, no answered
    flag, and above all no change to the default's own provider or key. The
    model field is not rendered until this succeeds, so Continue cannot be
    reached with a credential that does not work.
    """
    if not n:
        return no_update, no_update
    prefs = prefs or {}
    provider_key = providers.provider_key_for_label(provider_label)
    key = (api_key or "").strip()
    draft = {
        **(session.get("agent_llm_draft") or {}),
        "agent": _gate_agent(session),
        "provider": provider_key,
        "api_key": key,
    }
    if provider_key != "bedrock" and not key:
        return {
            **session,
            "agent_llm_draft": {**draft, "available_models": []},
            "agent_llm_error": "Please enter an API key.",
        }, no_update

    models, err = providers.list_models(provider_key, key)
    if not models:
        return {
            **session,
            "agent_llm_draft": {**draft, "available_models": []},
            "agent_llm_error": f"Connection failed: {err}",
        }, no_update

    new_prefs = (
        {
            **prefs,
            "provider_keys": {
                **(prefs.get("provider_keys") or {}),
                provider_key: key,
            },
        }
        if prefs.get("save_prefs")
        else no_update
    )
    return {
        **session,
        "agent_llm_draft": {**draft, "available_models": models},
        "agent_llm_error": None,
    }, new_prefs


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("stream-poll-interval", "max_intervals", allow_duplicate=True),
    Input("btn-agent-llm-continue", "n_clicks"),
    State(GATE_IDS["model"], "value"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_gate_continue(n: Any, model: Any, session: Any) -> Any:
    """Commit the override and answer the gate — and, from a failed step, re-run it.

    The entry is normally written whatever the probes return, `None/None`
    included: capability probing is advisory, and a probe that fails must never
    leave an agent unable to start.

    A picker opened from a failed step (`draft["retry"]`, see
    :func:`_open_pick_fields`) is the one exception, because choosing a model
    there spends a call immediately without asking again. A model whose tool
    probe came back a definite ``False`` is refused rather than committed: the
    picker stays open, on its model list, with the reason in the slot it already
    renders errors into. ``None`` never refuses — unknown is not a negative, and
    gateway providers do report false negatives, which is why the message points
    at the way round it.

    The retry itself is the same replay Try Again performs. Writes only into
    `agent_llm[agent]` — the default's credential is not this flow's to touch.
    """
    if not n or not model:
        return no_update, no_update
    agent = _gate_agent(session)
    draft = session.get("agent_llm_draft") or {}
    from_retry = bool(draft.get("retry"))
    provider_key = draft.get("provider") or ""
    llm_config = llm_selection.build_llm_config(
        provider_key, model, draft.get("api_key")
    )
    image_support, tool_support = llm_selection.probe_capabilities(
        provider_key, llm_config
    )

    if from_retry and tool_support is False:
        return {
            **session,
            "agent_llm_error": (
                f"{model} reports no tool support, so the step was not re-run. "
                "Pick another model, or go Back and use Try Again to run it "
                "anyway."
            ),
        }, no_update

    entry = {
        "provider": provider_key,
        "model": model,
        "available_models": draft.get("available_models") or [],
        "llm_config": llm_config,
        "image_support": image_support,
        "tool_support": tool_support,
    }
    overrides = {**(session.get("agent_llm") or {}), agent: entry}
    answered = _gate_answered(session, agent, agent_llm=overrides)

    if not from_retry:
        return answered, no_update

    if agent == "designer":
        # Designer's gate replaces its wizard, so the stores a draw writes to
        # are not mounted here and this callback cannot start one. Arm the
        # restored wizard instead — `designer_layout` reads this and mounts a
        # one-shot interval that fires the draw.
        failed = dict(answered.get("_designer_failed_draw") or {})
        if failed:
            failed["auto_retry"] = True
            answered = {**answered, "_designer_failed_draw": failed}
        return answered, no_update

    return _start_retry_turn(answered)


# ---------------------------------------------------------------------------
# Chat — retry after a failed turn
# ---------------------------------------------------------------------------


def _start_retry_turn(session: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Replay the turn that failed. Returns the store and the poll setting.

    The failed assistant bubble is dropped so the retry streams into a fresh
    one. What gets re-sent is whatever the dead turn was sent: the user message
    it was answering when one precedes it, or ``None`` for an agent-opening turn
    such as the CodeScanner scan. The agents' own orphan handling
    (``_drop_orphan_or_route_to_fresh_start``) discards the half-finished
    exchange their message history is carrying, so a retried opening turn
    re-seeds from session state rather than resuming mid-sentence.

    Shared by the Try Again button and by the picker, which re-runs the step the
    moment a model is chosen — one replay, so the two cannot drift.
    """
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
    Output("session", "data", allow_duplicate=True),
    Output("stream-poll-interval", "max_intervals", allow_duplicate=True),
    Input("btn-chat-retry", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_chat_retry(n_clicks: Any, session: Any) -> Any:
    """Re-run the turn that failed, on the model it is already using (D-ER1).

    A provider error (overload, rate limit, dropped connection) leaves the
    formatted exception as the assistant message and no state transition. This
    replays the same turn unchanged — the right move for a transient failure,
    and the escape hatch when the picker has refused a model the developer wants
    to try anyway.
    """
    if not n_clicks:
        return no_update, no_update
    if session.get("_stream_id"):
        return no_update, no_update
    return _start_retry_turn(session)


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
    State("breadth-retry-input", "value"),
    prevent_initial_call=True,
)
def on_breadth_try_again(n_clicks: Any, session: Any, note: Any = None) -> Any:
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

    Guided redraw (D-TA7): ``note`` is the panel's "Tell me what to change"
    text. Notes accumulate across successive Try Agains on the same panel — a
    second note is added to the first, not substituted, so an earlier "fewer,
    simpler" is not silently lost — and the set being rejected travels with
    them so "too many" and "drop X" have a referent. The block is written
    *after* the reset (which clears it, like every other agentifier key), so
    it survives exactly this restart. A blank note with no prior notes leaves
    the key ``None``: that is the plain redraw this button always was.
    """
    from spec4.agentifier.agentifier import reset_agentifier_flow

    if not n_clicks:
        return no_update, no_update
    if session.get("_stream_id"):
        return no_update, no_update
    session = dict(session or {})
    note = (note or "").strip() if isinstance(note, str) else ""
    prior_notes = [
        str(n).strip()
        for n in ((session.get("agentifier_retry_guidance") or {}).get("notes") or [])
        if str(n).strip()
    ]
    prior_pool = [
        c for c in (session.get("agentifier_scout_pool") or []) if isinstance(c, dict)
    ]
    reset_agentifier_flow(session)
    notes = prior_notes + ([note] if note else [])
    session["agentifier_retry_guidance"] = (
        {
            "notes": notes,
            "previous_candidates": [
                {
                    "name": str(c.get("name", "")),
                    "rough_description": str(c.get("rough_description", "")),
                }
                for c in prior_pool
                if c.get("name")
            ],
        }
        if notes
        else None
    )
    messages = list(session.get("messages", []))
    user_text = "Try Again — draw a new set of candidates."
    if note:
        quoted = "\n".join(f"> {line}" for line in note.splitlines())
        user_text = f"{user_text}\n\n{quoted}"
    messages.append({"role": "user", "content": user_text})
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
    # Claimed so it runs once even when two polls race into this branch. The
    # persist funnel drains the process-global usage sink, so a second run finds
    # it empty and clears the turn's token readout — the numbers vanish from the
    # chat row while the chars counter beside them stays. Both polls still return
    # the same terminal store, because the first run's mutations land on this
    # shared session dict.
    if streaming.claim_finalise(stream_id):
        try:
            _persist_artifacts(agent_session)
        except Exception as exc:  # a side effect — never strand the chat
            if _DEV_MODE:
                print(
                    f"[poll {stream_id[:8]}] _persist_artifacts failed "
                    f"({type(exc).__name__}: {exc}); finalising anyway",
                    flush=True,
                )
    elif _DEV_MODE:
        print(
            f"[poll {stream_id[:8]}] finalisation already claimed; "
            f"returning the same terminal store",
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
