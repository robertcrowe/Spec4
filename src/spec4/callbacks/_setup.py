"""The setup wizard's three steps: provider + key, model, web search.

Split out of ``spec4.callbacks`` by cleanup Phase 4g. Every name is re-exported
from the package, so an importer may use either path.

``_prefs_keep_working_dir`` is here because its only two callers are: Connect
writes the remembered credential, Clear takes it away again, and both must leave
the working directory alone.
"""

from __future__ import annotations

from typing import Any

from dash import Input, Output, State, callback, html, no_update
import dash_mantine_components as dmc

from spec4 import llm_selection, providers, websearch
from spec4.layouts._setup import SETUP_IDS, provider_key_hint


def _prefs_keep_working_dir(prefs: Any) -> dict[str, Any]:
    """Return a prefs dict retaining only working_dir, or empty dict."""
    if prefs and prefs.get("working_dir"):
        return {"working_dir": prefs["working_dir"]}
    return {}


# ---------------------------------------------------------------------------
# Setup — step 1: provider + API key
# ---------------------------------------------------------------------------


@callback(
    Output("setup-api-key-hint", "children"),
    Input("setup-provider", "value"),
    prevent_initial_call=False,
)
def on_provider_hint(provider_label: str | None) -> Any:
    """Fill the wizard's hint slot — from the shared builder, not a copy.

    The gate's own hint callback already went through
    :func:`provider_key_hint`; this one had its own inline copy of the Bedrock
    wording, which is exactly the drift the shared function exists to prevent.
    """
    return provider_key_hint(provider_label or "")


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
def on_setup_connect(  # noqa: PLR0913  # parameters are the callback's Input/State list
    n: int | None,
    provider_label: Any,
    api_key: str | None,
    save_prefs: bool | None,
    session: Any,
    prefs: Any,
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
            # This is where a previous connection ends, and the only place.
            # The bar's model slot and Settings open the wizard *over* a live
            # connection (`on_status_bar_setup`), and `setup_layout` would
            # skip straight to Search while `model` is still set; the list
            # just fetched may also belong to a different provider than the
            # model that was running. A failed Connect below changes neither
            # field, so a mistyped key costs nothing.
            "model": None,
            "llm_config": None,
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
def on_setup_clear(n: int | None, prefs: Any) -> Any:
    if not n:
        return no_update
    return _prefs_keep_working_dir(prefs)


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-setup-back-provider", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_setup_back_provider(n: int | None, session: Any) -> Any:
    if not n:
        return no_update
    return {**session, "available_models": None, "setup_error": None}


# ---------------------------------------------------------------------------
# Setup — step 2: model
# ---------------------------------------------------------------------------


@callback(
    Output(SETUP_IDS["effort"], "data"),
    Output(SETUP_IDS["effort"], "value"),
    Output(SETUP_IDS["effort"], "disabled"),
    Input(SETUP_IDS["model"], "value"),
    State(SETUP_IDS["effort"], "value"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_setup_effort_options(model: str | None, effort: str | None, session: Any) -> Any:
    """Re-offer the effort levels whenever the resolved model changes.

    The success criterion is that the offered values always match what the
    resolved model supports, and the model can change without the page
    re-rendering — the select's own value is what moves. So the list is
    recomputed here from the *same* function the layout builds it with
    (:func:`llm_selection.offered_efforts`), keyed on the session's provider
    and the newly chosen model.

    A chosen level that the new model does not offer falls back to
    ``"default"`` rather than being left dangling: "send nothing" is always
    valid, which is the whole reason it is a stored value rather than an
    absence. A model that does not accept the parameter at all offers that one
    value and the control is disabled.
    """
    offered = llm_selection.offered_efforts(
        (session or {}).get("provider"), model or ""
    )
    value = effort if effort in offered else llm_selection.DEFAULT_EFFORT
    return offered, value, len(offered) <= 1


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("prefs", "data", allow_duplicate=True),
    Output("image-support-store", "data", allow_duplicate=True),
    Output("tool-support-store", "data", allow_duplicate=True),
    Output("notifications-container", "children", allow_duplicate=True),
    Input("btn-setup-model-continue", "n_clicks"),
    State("setup-model", "value"),
    State(SETUP_IDS["effort"], "value"),
    State("session", "data"),
    State("prefs", "data"),
    prevent_initial_call=True,
)
def on_setup_model_continue(
    n: int | None,
    model: str | None,
    chosen_effort: str | None,
    session: Any,
    prefs: Any,
) -> Any:
    if not n or not model:
        return no_update, no_update, no_update, no_update, no_update
    provider_key = session.get("provider") or ""
    # The select's value is the project default's effort. It falls back to the
    # remembered one rather than to "default" so that a step re-run with the
    # control absent — an older layout, a test driving the callback directly —
    # cannot silently discard a stored choice.
    effort = (
        chosen_effort
        or session.get("effort")
        or prefs.get("effort")
        or llm_selection.DEFAULT_EFFORT
    )
    llm_config = llm_selection.build_llm_config(
        provider_key, model, session.get("api_key"), effort
    )
    new_session = {
        **session,
        "model": model,
        "effort": effort,
        "llm_config": llm_config,
        "setup_error": None,
    }
    new_prefs = (
        {**prefs, "model": model, "effort": effort}
        if prefs.get("save_prefs")
        else prefs
    )

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
def on_setup_back_model(n: int | None, session: Any) -> Any:
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
def on_search_provider_hint(provider_label: str | None) -> Any:
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
        # The wizard's one dimmed-line class, not a size and a colour of this
        # slot's own — it sits directly under a field, exactly where the
        # never-stored notice sits under the key.
        className="dim-line",
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
    n: int | None,
    provider_label: str | None,
    search_key: str | None,
    session: Any,
    prefs: Any,
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
def on_setup_search_skip(n: int | None, session: Any) -> Any:
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
