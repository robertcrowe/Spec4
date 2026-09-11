"""The per-agent model gate: one flow, seven agents, two surfaces.

Split out of :mod:`spec4.callbacks._chat` by cleanup Phase 4g2. One set of
callbacks serves all seven agents and both surfaces: only one gate is ever open,
and the agent it belongs to is carried in ``agent_llm_draft``. The gate answers a
question the setup wizard already answers for the default, so both go through the
same builder and probe wrapper in ``llm_selection`` -- a Bedrock credential parsed
one way here and another way there is exactly the drift this shares code to
prevent.

``on_chat_retry_model`` is here rather than with the retry callbacks because it
is the picker's entry point: it opens the gate on a failed step, and everything
that follows is a gate answer.

``_start_retry_turn`` comes from :mod:`spec4.callbacks._chat`, the one name this
module needs from a sibling -- ``on_gate_continue`` re-runs a failed step once the
developer picks a model. The direction is one-way; ``_chat`` imports nothing from
here. ``_gate_agent`` and ``_open_pick_fields`` come from
:mod:`spec4.callbacks._shared`, where 4g put them. Neither import is of the
package, which rule 4 of the layering contract forbids (CLEANUP_INVENTORY.md
15.2).
"""

from __future__ import annotations

from typing import Any

from dash import Input, Output, State, callback, no_update

from spec4 import llm_selection, providers
from spec4.callbacks._chat import _start_retry_turn
from spec4.callbacks._shared import _gate_agent, _open_pick_fields
from spec4.layouts._setup import GATE_IDS, provider_key_hint


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
    Output(GATE_IDS["effort"], "data"),
    Output(GATE_IDS["effort"], "value"),
    Output(GATE_IDS["effort"], "disabled"),
    Input(GATE_IDS["model"], "value"),
    State(GATE_IDS["effort"], "value"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_gate_effort_options(model: Any, effort: Any, session: Any) -> Any:
    """Re-offer the effort levels whenever the gate's chosen model changes.

    The gate's twin of :func:`on_setup_effort_options`, and deliberately its
    twin rather than a variant: the criterion is that the offered values always
    match what the *resolved* model supports, and the two screens resolve the
    same way. Both call :func:`llm_selection.offered_efforts` — the same
    function the layout builds the control with — so the list cannot depend on
    which of the two screens is asking.

    The provider comes off the open draft, which is where Connect put it, and
    only falls back to the session's when there is no draft provider yet: the
    levels are keyed on the provider the *override* will use, not on the
    default's (D-EF4).
    """
    session = session or {}
    draft = session.get("agent_llm_draft") or {}
    provider_key = draft.get("provider") or session.get("provider")
    offered = llm_selection.offered_efforts(provider_key, model or "")
    value = effort if effort in offered else llm_selection.DEFAULT_EFFORT
    return offered, value, len(offered) <= 1


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

    The entry survived `reset_for_new_project` intact — credential, model list
    and both capability flags — so answering costs nothing but the flag.
    """
    if not n:
        return no_update
    return _gate_answered(session, _gate_agent(session))


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
    per-turn resolution in `get_agent_gen` gives for free.
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
    State(GATE_IDS["effort"], "value"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_gate_continue(n: Any, model: Any, chosen_effort: Any, session: Any) -> Any:
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
    # The gate's own Effort select, written onto the same per-agent entry as
    # the model and by this one callback — never a store key of its own. It
    # falls back to whatever this agent already had rather than to "default",
    # for the reason the setup wizard's does: a step re-run with the control
    # absent (an older layout, a test driving the callback directly) must not
    # silently discard a stored choice.
    effort = (
        chosen_effort
        or draft.get("effort")
        or (llm_selection.entry(session, agent) or {}).get("effort")
        or llm_selection.DEFAULT_EFFORT
    )
    llm_config = llm_selection.build_llm_config(
        provider_key, model, draft.get("api_key"), effort
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
        "effort": effort,
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
