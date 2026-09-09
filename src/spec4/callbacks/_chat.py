"""The chat frame's core: the turn, the Agentifier breadth panel, the poll.

Split out of ``spec4.callbacks`` by cleanup Phase 4g, then narrowed by 4g2,
which moved the per-agent model gate to :mod:`spec4.callbacks._gate` and the
navigation buttons to :mod:`spec4.callbacks._nav`. What is left is the three
things the chat frame does on its own behalf: start and submit a turn (including
Fast Forward and the retry that replays a failed one), run the breadth
selection, and poll the stream that any of them opened.

``_start_retry_turn`` is the one name a sibling reads: ``_gate.on_gate_continue``
re-runs a failed step once the developer picks a model. The direction is one-way
-- nothing here imports ``_gate`` or ``_nav``, and nothing here imports the
``spec4.callbacks`` package, which rule 4 of the layering contract forbids
(CLEANUP_INVENTORY.md 15.2). It is also why the ``_chat`` module remains the
patch surface for ``_get_agent_gen``, ``_persist_artifacts`` and ``streaming``:
every path that reaches them, gate answers included, runs through this module.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from dash import ALL, Input, Output, State, callback, ctx, no_update

from spec4 import streaming
from spec4.agentifier.panel_closure import close_selection, pool_from_dicts
from spec4.layouts._llm_gate import is_open as _gate_is_open
from spec4.session import (
    _get_agent_gen,
    _persist_artifacts,
)


_DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"


# ---------------------------------------------------------------------------
# Agent select
# ---------------------------------------------------------------------------


# D-LR8: `on_chat_back` stood here, serving the chat frame's `← Back` button
# with a route to `/agents`. Both are gone — the status bar's Project link is
# the same route from the same screen, and it is mounted in the shell rather
# than in this layout. The walk covering all four removed Back controls is in
# `layouts/_chat.py`, at `_chat_action_buttons`.


# `on_agent_change_provider` stood here, serving the agents page's "Change
# model / provider" button. Both are gone: the status bar's model slot and its
# Settings item are the same route from every screen (`on_status_bar_setup`),
# mounted in the shell rather than in this layout — the D-LR8 walk again.


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
    it survives exactly this restart. With no notes at all the prompts are
    untouched (the orchestrator passes Scout ``None`` for empty notes): that
    is the plain redraw this button always was.

    Every click is also logged as one ``history`` event — the note (None for
    a blank redraw), the set rejected, and when — which ``_complete_agentifier``
    writes to ``ai_features.json`` as ``discovery_guidance``, so the round's
    record shows each redraw the developer asked for, in order.
    """
    from spec4.agentifier.agentifier import reset_agentifier_flow

    if not n_clicks:
        return no_update, no_update
    if session.get("_stream_id"):
        return no_update, no_update
    session = dict(session or {})
    note = (note or "").strip() if isinstance(note, str) else ""
    prior = session.get("agentifier_retry_guidance") or {}
    prior_notes = [str(n).strip() for n in (prior.get("notes") or []) if str(n).strip()]
    prior_history = [e for e in (prior.get("history") or []) if isinstance(e, dict)]
    rejected = [
        {
            "name": str(c.get("name", "")),
            "rough_description": str(c.get("rough_description", "")),
        }
        for c in (session.get("agentifier_scout_pool") or [])
        if isinstance(c, dict) and c.get("name")
    ]
    reset_agentifier_flow(session)
    session["agentifier_retry_guidance"] = {
        "notes": prior_notes + ([note] if note else []),
        "previous_candidates": rejected,
        "history": prior_history
        + [
            {
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "note": note or None,
                "rejected_candidates": rejected,
            }
        ],
    }
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
        return _poll_missing_stream(stream_id)

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
        return _poll_running(session, messages, text, received, status)

    # Stream complete — merge agent-mutated session and finalise
    _poll_dev_trace(stream_id, text, messages)
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
    _poll_finalise(stream_id, agent_session, messages)
    # D-ER2: a finished turn whose assistant message is empty is never correct —
    # it renders as a blank bubble with no controls under it, which reads as the
    # app hanging. It happens when a generator returns without yielding and
    # without setting a display override: an artifact reply that was suppressed
    # on its way to the screen and then failed to parse takes exactly that path.
    # Agents fix their own causes; this is the last line of defence, and it
    # routes the turn into the same Try Again recovery a raised exception gets.
    empty_turn = _poll_substitute_empty_turn(stream_id, messages)
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


def _poll_missing_stream(stream_id: str) -> Any:
    """The poll tick for a stream id whose entry another poll already finalised."""
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


def _poll_running(
    session: dict[str, Any],
    messages: list[dict[str, Any]],
    text: str,
    received: Any,
    status: Any,
) -> Any:
    """The poll tick while the stream is still producing."""
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


def _poll_dev_trace(stream_id: str, text: str, messages: list[dict[str, Any]]) -> None:
    """DEV_MODE trace of the done branch firing."""
    if _DEV_MODE:
        print(
            f"[poll {stream_id[:8]}] done branch firing; text_len={len(text)}, "
            f"messages_count={len(messages)}, "
            f"last_msg_preview={text[:120]!r}",
            flush=True,
        )


def _poll_finalise(
    stream_id: str, agent_session: dict[str, Any], messages: list[dict[str, Any]]
) -> None:
    """Claim the finalise once, persist artifacts, apply any display override."""
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


def _poll_substitute_empty_turn(stream_id: str, messages: list[dict[str, Any]]) -> bool:
    """D-ER2: substitute the notice when a finished turn produced no visible text."""
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
    return empty_turn
