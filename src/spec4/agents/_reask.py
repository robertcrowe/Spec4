"""The artifact re-ask protocol and the stream wrappers it is built on.

An agent that must end its turn with a JSON artifact can instead end it with
prose. ``reask_for_artifact`` is the one retry that asks again in the artifact's
own words; ``abandon_reask`` is what happens when that retry also fails. The
stream wrappers below are the machinery underneath: ``stream_suppressing_json``
hides a fenced JSON block from the user while still yielding the prose around
it, ``stream_counting`` is its pass-through counterpart for agents that only
need the token count, and ``drain_stream`` consumes a generator for its return
value alone.

Split out of ``_utils.py`` in Phase 4a; Phase 4j moved every importer here and
retired the ``_utils`` facade, so this module is now the one place these names
are imported from.
"""

from __future__ import annotations

import os
import time
from collections.abc import Generator, Iterable
from typing import TYPE_CHECKING, Any

from spec4.agents._turn_flow import AGENT_DELIVERABLE

if TYPE_CHECKING:
    from spec4.websearch import SearchConfig


DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"


def suppressed_as_artifact(text: str) -> bool:
    """True when ``stream_suppressing_json`` would swallow this reply whole.

    The suppression rule is "the response opens with a fence", and the two
    places that care about it must not drift: the generator applies it while
    streaming, and the agents apply it afterwards to tell an artifact turn that
    failed to parse (developer saw nothing) from ordinary conversation
    (developer saw the reply). Sharing the predicate keeps them in lockstep.
    """
    return text.lstrip().startswith("```")


def artifact_reask_prompt(artifact: str) -> str:
    """Corrective user message for an artifact block that could not be read.

    Deliberately asks for a fenced block rather than bare JSON: the extractors
    that will read the reply look for a fence, and an agent that re-asks in a
    shape its own extractor rejects has only moved the failure.
    """
    return (
        f"The JSON block you just emitted could not be read — it was malformed, "
        f"or truncated before its closing fence. Re-emit the complete "
        f"{artifact} as a single fenced ```json``` block and nothing else: no "
        f"preface, no summary, no commentary after it."
    )


def artifact_reask_status(artifact: str) -> str:
    """The one line the developer sees while the silent re-ask runs."""
    return f"\n\n_The {artifact} didn't come through cleanly — asking again…_\n"


def artifact_fallback(artifact: str) -> str:
    """Recoverable message for when the re-ask fails too.

    The turn has to end with something on screen. Naming the next move matters:
    the agent is still in conversation, so the developer can simply ask again.
    """
    return (
        f"I tried to emit the structured {artifact} but it didn't come back in "
        f"a usable form. Reply 'try again' and I'll re-emit it, or tell me what "
        f"to change first."
    )


def reask_for_artifact(  # noqa: PLR0913  # the reask contract: agent, artifact, schema, model and callbacks, all threaded through
    *,
    system: str,
    msgs: list[dict[str, Any]],
    llm_config: dict[str, Any],
    search_config: SearchConfig | None,
    agent_name: str,
    correction: str,
    status_line: str,
    response_format: dict[str, Any] | None = None,
    session: dict[str, Any] | None = None,
    seed: int = 0,
) -> Generator[str, None, None]:
    """Ask the model once more for an artifact it failed to emit usably.

    Appends ``correction`` to ``msgs``, yields ``status_line`` so the turn is not
    silent, then drains the reply without yielding it — the body is the artifact
    block itself, which the developer must never see raw. ``stream_turn`` records
    the reply on ``msgs``, so the caller re-extracts from there afterwards, and
    calls :func:`abandon_reask` if it is still unusable.

    ``seed`` is the characters already received this turn. Publishing the running
    total onto ``session`` keeps the chars counter climbing through the drain
    (D-PH9 / D-SC-P1) instead of freezing for its duration.
    """
    # Imported here rather than at module scope: `_reask` is a shared leaf that
    # every agent imports, and pulling the litellm/mcp stack in at its import time
    # would make that cost unconditional for callers that never re-ask.
    from spec4 import llm

    msgs.append({"role": "user", "content": correction})
    yield status_line
    set_status(
        session,
        f"Re-requesting {AGENT_DELIVERABLE.get(agent_name, 'the artifact')} "
        "from the model…",
    )
    received = seed + len(status_line)
    if session is not None:
        session["_stream_received_chars"] = received
    for chunk in llm.stream_turn(
        system,
        msgs,
        llm_config,
        search_config,
        agent_name=agent_name,
        response_format=response_format,
    ):
        if chunk and session is not None:
            received += len(chunk)
            session["_stream_received_chars"] = received


def abandon_reask(
    msgs: list[dict[str, Any]],
    correction: str,
    fallback: str,
    session: dict[str, Any],
) -> None:
    """Give up on the artifact, leaving the conversation in a usable state.

    Drops the synthesized correction exchange so the history does not carry a
    dead-end user turn the developer never wrote, and replaces the unreadable
    reply with ``fallback`` — both in the history and, via ``_display_override``,
    on screen. Without the override the turn ends showing the suppressed reply's
    empty bubble, which is the failure this whole path exists to prevent.
    """
    if (
        len(msgs) >= 2  # noqa: PLR2004  # guards msgs[-2]
        and msgs[-2].get("role") == "user"
        and msgs[-2].get("content") == correction
    ):
        del msgs[-2:]
    if msgs and msgs[-1].get("role") == "assistant":
        msgs[-1]["content"] = fallback
    else:
        msgs.append({"role": "assistant", "content": fallback})
    session["_display_override"] = fallback


def set_status(session: dict[str, Any] | None, text: str) -> None:
    """Publish a one-line status message for the chat status line.

    The line sits under the chat input and shows what the pipeline is doing
    while the user waits; each call replaces the previous message. Written to
    the live (agent-mutated) session dict — the same object the poll reads as
    ``stream["session"]`` — which threads it into the store mid-stream and
    clears it when the stream finalises. ``session=None`` is a no-op so
    helpers that may run without a session can call unconditionally.
    """
    if session is not None:
        session["_stream_status"] = text


def stream_suppressing_json(
    chunks: Generator[str, None, None],
    session: dict[str, Any] | None = None,
    seed: int = 0,
    *,
    reply_status: str | None = None,
    artifact_status: str | None = None,
) -> Generator[str, None, None]:
    """Yield chunks, suppressing the entire response if it starts with a fence.

    When the LLM outputs its final JSON artifact the response begins with ```
    (possibly after leading whitespace). Suppressing it prevents raw JSON from
    appearing in the chat window; the caller replaces it via _display_override.

    D-SC60: that suppression is precisely why the chat token counter's
    displayed-character fallback cannot work on an artifact turn — nothing is
    ever yielded, so the visible assistant message never grows and the counter
    reads 0 for the whole multi-minute draw. Suppression is owned here, so the
    correction belongs here too. When a ``session`` is supplied, publish a
    cumulative received-character total onto it (the same shared dict the poll
    reads as ``stream["session"]``, and which it threads into the counter), so
    the counter tracks real receipt rather than displayed text. This is the same
    remedy D-PH9 applied to the phaser validation-retry drain. Callers that pass
    no session keep the previous behaviour exactly.

    D-AT3: ``seed`` is the number of characters the caller already yielded in
    this turn before opening the stream. The counter reads the published total
    in preference to the displayed message length, so a caller that yielded
    progress text first (Agentifier's tier-analysis loop) would otherwise see
    the counter drop to zero the moment the stream opens. Seeding with that
    text's length keeps the count monotonic within a turn. Defaults to 0, which
    is the prior behaviour.

    ``reply_status`` / ``artifact_status`` publish stage-accurate status-line
    text the moment this wrapper can tell which kind of turn it is watching:
    ``reply_status`` once visible text starts flushing, ``artifact_status``
    once the reply is recognised as a suppressed artifact draw (the
    multi-minute silent stretch that otherwise sits on the generic "…is
    thinking" seed for its whole duration). Republished on later content
    chunks if something else (e.g. ``stream_turn``'s web-search status) has
    overwritten it in between — a search status stands only until the model
    starts producing text again. Both default to None (no status writes),
    which is the prior behaviour.
    """
    _FENCE = "```"
    buf = ""
    flushed = False
    suppress = False
    received = 0
    received_chars = seed
    _seed_stream_session(session, seed)
    _log_suppress_entry()
    try:
        for chunk in chunks:
            received += 1
            received_chars = _record_received_chars(session, chunk, received_chars)
            if flushed:
                yield chunk
            elif suppress:
                pass
            else:
                buf += chunk
                stripped = buf.lstrip()
                if suppressed_as_artifact(buf):
                    suppress = True
                elif len(stripped) >= len(_FENCE):
                    flushed = True
                    yield buf
                    buf = ""
            _publish_stream_status(
                session, suppress, flushed, reply_status, artifact_status
            )
        if not suppress and not flushed and buf:
            yield buf
    except BaseException as exc:
        if DEV_MODE:
            print(
                f"[suppress] EXCEPTION after {received} chunks "
                f"(suppress={suppress}, flushed={flushed}, buf_len={len(buf)}): "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
        raise
    finally:
        _log_suppress_exit(received, suppress, flushed)


def _seed_stream_session(session: dict[str, Any] | None, seed: int) -> None:
    """Seed the turn at the caller's pre-stream character total."""
    if session is not None:
        # Seed the turn at the caller's pre-stream total (0 unless supplied) so
        # a stale total from a prior turn cannot be read as this turn's
        # progress before the first chunk lands.
        session["_stream_received_chars"] = seed


def _publish_stream_status(
    session: dict[str, Any] | None,
    suppress: bool,
    flushed: bool,
    reply_status: str | None,
    artifact_status: str | None,
) -> None:
    """Publish stage-accurate status-line text for this turn."""
    if session is not None:
        desired = artifact_status if suppress else (reply_status if flushed else None)
        if desired and session.get("_stream_status") != desired:
            session["_stream_status"] = desired


def _log_suppress_entry() -> None:
    """DEV_MODE entry trace for the suppression wrapper."""
    if DEV_MODE:
        print("[suppress] entering", flush=True)


def _record_received_chars(
    session: dict[str, Any] | None, chunk: str, received_chars: int
) -> int:
    """Publish the cumulative received-character total (D-SC60), and return it."""
    if session is not None and chunk:
        received_chars += len(chunk)
        session["_stream_received_chars"] = received_chars
    return received_chars


def _log_suppress_exit(received: int, suppress: bool, flushed: bool) -> None:
    """DEV_MODE exit trace for the suppression wrapper."""
    if DEV_MODE:
        print(
            f"[suppress] exit: received={received} suppress={suppress} "
            f"flushed={flushed}",
            flush=True,
        )


def stream_counting(
    chunks: Generator[str, None, None],
    session: dict[str, Any],
    seed: int = 0,
) -> Generator[str, None, int]:
    """Yield chunks unchanged, publishing a running received-character total.

    The pass-through counterpart to :func:`stream_suppressing_json`, for agents
    whose replies reach the screen verbatim (Deployer). The chars counter falls
    back to the length of the in-flight assistant message when nothing is
    published, and for a verbatim reply that fallback is accurate — but only
    while the turn is one stream that yields exactly what the message holds.
    Deployer's greenfield README beat is neither: it yields an authoring note
    between two ``stream_turn`` calls, and the second call starts a fresh
    assistant message, so the fallback counter drops back to zero mid-turn.
    Publishing a cumulative total keeps it monotonic, and leaves the counter
    correct if a suppressed artifact turn is ever added here (D-SC60).

    Returns the running total so a caller with several streams in one turn can
    seed the next from it: ``received = yield from stream_counting(...)``.
    """
    received = seed
    # Publish before the first chunk so a stale total from the previous turn
    # cannot be read as this turn's progress (as in stream_suppressing_json).
    session["_stream_received_chars"] = received
    for chunk in chunks:
        if chunk:
            received += len(chunk)
            session["_stream_received_chars"] = received
        yield chunk
    return received


def drain_stream(
    chunks: Iterable[str],
    session: dict[str, Any] | None = None,
    seed: int = 0,
    ttft_label: str | None = None,
) -> tuple[str, int]:
    """Silently drain a text-delta iterator, publishing the receipt counter.

    For call sites whose streamed response is consumed internally and never
    shown to the user (D-PH9): accumulates the deltas into a string while
    publishing a cumulative character total to
    ``session["_stream_received_chars"]``, the key the chat poll reads. A
    climbing counter proves liveness; a frozen one is a diagnosable stall.
    Seeds eagerly — before the first chunk — so a stale total from a previous
    turn is overwritten the moment the drain opens. ``session=None`` drains
    without publishing. Returns ``(accumulated_text, final_total)`` so a
    caller with several drains in one turn can seed the next from the total.

    ``ttft_label`` logs first-chunk latency for drains whose transport does
    not go through ``llm.complete_stream`` (the ``acomplete(stream=True)``
    sites); leave it None when complete_stream already logs the TTFT.
    """
    received = seed
    if session is not None:
        session["_stream_received_chars"] = received
    parts: list[str] = []
    start = time.monotonic()
    first = True
    for chunk in chunks:
        if first and ttft_label is not None:
            print(
                f"[llm-ttft] {ttft_label}: first chunk after "
                f"{time.monotonic() - start:.1f}s",
                flush=True,
            )
        first = False
        if not chunk:
            continue
        parts.append(chunk)
        received += len(chunk)
        if session is not None:
            session["_stream_received_chars"] = received
    return "".join(parts), received
