"""LLM conversation turns, with transparent web-search tool handling.

Every model call in Spec4 goes through here: ``complete`` / ``acomplete`` for
one-shot calls and ``stream_turn`` for a streamed turn that loops until the
model stops asking for tools. Both axes are provider-agnostic — the model comes
from ``llm_config`` and the web search from a :class:`SearchConfig` (Tavily or
Exa; :mod:`spec4.websearch` owns the provider registry and the MCP transport).

``search``, ``WEB_SEARCH_TOOL`` and ``WEB_SEARCH_ADDENDUM`` are re-exported
here because that is where the rest of the codebase already reaches for them.

Formerly ``tavily_mcp`` — renamed once Tavily stopped being the only search
provider and no Tavily-specific code was left in it.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import AsyncIterator, Generator
from datetime import datetime, timezone
from typing import Any

import httpx
import litellm
from litellm.exceptions import BadRequestError as LiteLLMBadRequestError

from spec4.websearch import (
    WEB_SEARCH_ADDENDUM,
    WEB_SEARCH_TOOL,
    SearchConfig,
    search,
)

__all__ = [
    "LLM_STREAM_TIMEOUT",
    "WEB_SEARCH_ADDENDUM",
    "WEB_SEARCH_TOOL",
    "SearchConfig",
    "acomplete",
    "build_system_prompt",
    "complete",
    "complete_stream",
    "drain_usage_records",
    "search",
    "stream_completion",
    "stream_turn",
    "supports_response_format",
]

logger = logging.getLogger(__name__)

# Inter-chunk stall bound for streamed one-shot calls. On a streaming response
# the read timeout is applied between chunks (the clock resets on every chunk
# received), so it bounds *silence*, not total generation time — a long but
# healthy generation never trips it. The read bound is generous because the
# longest legitimate gap is time-to-first-token, which is unmeasured across
# the supported model range (floor: claude-haiku-4-5); tune it from the
# [llm-ttft] log lines, not by guessing.
LLM_STREAM_TIMEOUT = httpx.Timeout(connect=15.0, read=180.0, write=30.0, pool=15.0)


def build_system_prompt(base: str, search_config: SearchConfig | str | None) -> str:
    """Append the web-search addendum to base when a search provider is set up."""
    return base + (WEB_SEARCH_ADDENDUM if search_config else "")


# NOTE: `temperature` is never sent. A growing number of models reject the
# parameter outright (deprecated / unsupported / fixed at 1.0), and the
# per-agent tuning that used to live here was not worth the request failures
# and the fallback-retry machinery needed to survive them. Every call now
# takes the provider's default sampling settings. An explicit
# `llm_config["temperature"]` is likewise ignored rather than forwarded.


def _history_has_tool_use(messages: list[dict[str, Any]]) -> bool:
    """Return True if the message log contains tool calls or tool results.

    Anthropic (via litellm) rejects requests whose message history contains
    `tool_use` / `tool_result` blocks unless the request also specifies
    `tools=`. This check lets `stream_turn` keep `tools=` present on retry
    calls when prior tool use has already occurred, even when we would
    otherwise suppress the tool for `response_format`-style structured
    output.
    """
    for m in messages:
        if m.get("role") == "tool":
            return True
        if m.get("tool_calls"):
            return True
    return False


def _is_tool_incompatible_error(exc: Exception) -> bool:
    """Return True if the error indicates the model rejects tool calling."""
    msg = str(exc).lower()
    return "tool" in msg and any(
        p in msg for p in ("not support", "tool_choice", "unsupported")
    )


def _build_completion_kwargs(
    llm_config: dict[str, Any],
    messages: list[dict[str, Any]],
    response_format: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Assemble a litellm-compatible kwargs dict from llm_config and messages.

    Covers model, api_key, the four aws_* credential keys, api_base, and
    response_format. Temperature is never included — see the note above.
    Any additional keyword arguments are merged via **extra. A streamed call
    (``stream=True``) also asks LiteLLM for a usage chunk
    (``stream_options={"include_usage": True}``) so token counts reach the
    usage capture below; ``stream_options`` is exempt from LiteLLM's
    unsupported-param check, so it is safe to send to every provider.
    """
    kwargs: dict[str, Any] = {"model": llm_config["model"], "messages": messages}
    if llm_config.get("api_key"):
        kwargs["api_key"] = llm_config["api_key"]
    for _aws_key in (
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_region_name",
        "aws_session_token",
    ):
        if llm_config.get(_aws_key):
            kwargs[_aws_key] = llm_config[_aws_key]
    if "api_base" in llm_config:
        kwargs["api_base"] = llm_config["api_base"]
    if response_format is not None:
        kwargs["response_format"] = response_format
    kwargs.update(extra)
    if kwargs.get("stream"):
        kwargs.setdefault("stream_options", _STREAM_USAGE_OPTIONS)
    return kwargs


# ---------------------------------------------------------------------------
# Usage capture
# ---------------------------------------------------------------------------
#
# Every call that leaves this module (sync, async, streamed or not) appends one
# record to a module-level sink. The sink is process-global on purpose: the
# Agentifier sub-agents receive only ``llm_config`` (no session), and their
# asyncio bridge runs in a separate thread that does not inherit contextvars,
# so the only context reliably present at the hook is what the caller already
# passes — ``agent_name`` and the kwargs about to be sent. The turn owner
# (``session._persist_artifacts`` for chat turns, the Designer generation
# thread for mocks) drains the sink once the active round's version is known
# and writes ``.spec4/v{N}/usage.json`` via ``project_manager.save_usage``.
#
# Capture must never break an agent run: extraction is wrapped, a failure logs
# a warning, and a call whose provider returned no usage is still recorded
# (token fields null, ``usage_missing`` true) rather than dropped.

_STREAM_USAGE_OPTIONS: dict[str, Any] = {"include_usage": True}

_USAGE_LOCK = threading.Lock()
_USAGE_RECORDS: list[dict[str, Any]] = []


def drain_usage_records() -> list[dict[str, Any]]:
    """Return every usage record captured since the last drain, and clear them."""
    with _USAGE_LOCK:
        records = list(_USAGE_RECORDS)
        _USAGE_RECORDS.clear()
    return records


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_int(value: Any) -> int | None:
    """Return ``value`` as an int, or None for anything that is not a real int.

    Test doubles are ``MagicMock`` objects whose every attribute is another
    truthy mock, so a bare ``getattr`` is not enough to tell a real count from
    an absent one. ``bool`` is excluded because it subclasses ``int``.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _get(obj: Any, name: str) -> Any:
    """Attribute-or-key lookup: LiteLLM usage may arrive as an object or a dict."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _usage_fields(usage: Any) -> dict[str, int | None] | None:
    """Normalise a LiteLLM ``Usage`` into plain ints. None when unusable.

    Cache fields are read only where the provider actually reported them
    (OpenAI's ``prompt_tokens_details.cached_tokens``; Anthropic's
    ``cache_creation_input_tokens`` / ``cache_read_input_tokens``, which
    LiteLLM also mirrors onto ``prompt_tokens_details``). Absent means null —
    LiteLLM's private zero-default attributes are deliberately not consulted.
    A usage block whose prompt AND completion counts are both zero is treated
    as missing: LiteLLM synthesises such a block from chunks that carried no
    usage at all, and no real call has an empty prompt.
    """
    if usage is None:
        return None
    prompt = _as_int(_get(usage, "prompt_tokens"))
    completion = _as_int(_get(usage, "completion_tokens"))
    if prompt is None and completion is None:
        return None
    if not prompt and not completion:
        return None
    total = _as_int(_get(usage, "total_tokens"))
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    details = _get(usage, "prompt_tokens_details")
    cached = _as_int(_get(details, "cached_tokens"))
    creation = _as_int(_get(usage, "cache_creation_input_tokens"))
    if creation is None:
        creation = _as_int(_get(details, "cache_creation_tokens"))
    read = _as_int(_get(usage, "cache_read_input_tokens"))
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "cached_tokens": cached,
        "cache_creation_input_tokens": creation,
        "cache_read_input_tokens": read,
    }


def _resolve_provider(model: Any, api_base: Any) -> str | None:
    """Provider name as LiteLLM resolves it from the model string (and api_base)."""
    if not isinstance(model, str) or not model:
        return None
    try:
        provider = litellm.get_llm_provider(model=model, api_base=api_base)[1]
    except Exception:
        return None
    return str(provider) if provider else None


def _computed_cost(
    response: Any, model: Any, provider: str | None, fields: dict[str, int | None]
) -> float | None:
    """LiteLLM's own cost estimate for the call, or None when it has none.

    Prefers the ``response_cost`` LiteLLM stamps on ``_hidden_params``; falls
    back to ``litellm.completion_cost``. A streamed call's final chunk carries
    no cost, so a minimal ``ModelResponse`` rebuilt from the normalised token
    counts (cache fields included, where reported) is handed to the calculator
    instead. Advisory only: the price map is community-maintained, lags new
    models, and has no entry at all for some providers (Nebius models resolve
    as ``openai/<id>`` and are unmapped).
    """
    hidden = getattr(response, "_hidden_params", None)
    if isinstance(hidden, dict):
        cost = hidden.get("response_cost")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            return float(cost)
    try:
        usage_kwargs: dict[str, Any] = {
            "prompt_tokens": fields["prompt_tokens"] or 0,
            "completion_tokens": fields["completion_tokens"] or 0,
            "total_tokens": fields["total_tokens"] or 0,
        }
        if fields["cache_read_input_tokens"] is not None:
            usage_kwargs["cache_read_input_tokens"] = fields["cache_read_input_tokens"]
        elif fields["cached_tokens"] is not None:
            usage_kwargs["prompt_tokens_details"] = {
                "cached_tokens": fields["cached_tokens"]
            }
        if fields["cache_creation_input_tokens"] is not None:
            usage_kwargs["cache_creation_input_tokens"] = fields[
                "cache_creation_input_tokens"
            ]
        priced = litellm.ModelResponse(model=model, usage=litellm.Usage(**usage_kwargs))
        return float(
            litellm.completion_cost(
                completion_response=priced,
                model=model,
                custom_llm_provider=provider,
            )
        )
    except Exception as exc:
        logger.debug("No LiteLLM cost for model=%s: %s", model, exc)
        return None


def _record_usage(
    *,
    agent_name: str | None,
    kwargs: dict[str, Any],
    response: Any,
    usage: Any,
    streamed: bool,
    started_at: str,
    start_mono: float,
    error: str | None = None,
) -> None:
    """Append one usage record for a finished call. Never raises."""
    try:
        model = kwargs.get("model")
        provider = _resolve_provider(model, kwargs.get("api_base"))
        record: dict[str, Any] = {
            "timestamp": started_at,
            "agent": agent_name,
            "model": model,
            "provider": provider,
            "streamed": streamed,
            "duration_s": round(time.monotonic() - start_mono, 3),
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "cached_tokens": None,
            "cache_creation_input_tokens": None,
            "cache_read_input_tokens": None,
            "computed_cost_usd": None,
            "usage_missing": True,
            "error": error,
        }
        fields = _usage_fields(usage)
        if fields is not None:
            record.update(fields)
            record["usage_missing"] = False
            record["computed_cost_usd"] = _computed_cost(
                response, model, provider, fields
            )
        else:
            logger.warning(
                "LLM usage missing for agent=%s provider=%s model=%s%s",
                agent_name,
                provider,
                model,
                f" ({error})" if error else "",
            )
        with _USAGE_LOCK:
            _USAGE_RECORDS.append(record)
    except Exception as exc:
        logger.warning("LLM usage capture failed for agent=%s: %s", agent_name, exc)


def _chunk_usage(chunk: Any) -> Any:
    """The chunk's usage block when it holds real counts, else None.

    Runs on every streamed chunk, so it must never raise into the stream.
    """
    try:
        usage = _get(chunk, "usage")
        return usage if _usage_fields(usage) is not None else None
    except Exception:
        return None


def _hidden_usage(chunk: Any) -> Any:
    """Usage LiteLLM stashes on the final chunk when no usage chunk was sent."""
    try:
        hidden = getattr(chunk, "_hidden_params", None)
        return hidden.get("usage") if isinstance(hidden, dict) else None
    except Exception:
        return None


def _iter_with_usage(
    response: Any,
    kwargs: dict[str, Any],
    agent_name: str | None,
    started_at: str,
    start_mono: float,
) -> Generator[Any, None, None]:
    """Yield raw chunks from a sync stream, recording usage when it ends.

    The usage chunk LiteLLM appends under ``include_usage`` may arrive with
    empty ``choices``; it is consumed here and never yielded, so consumers can
    keep indexing ``chunk.choices[0]``. A stream that dies or is abandoned
    mid-way (``GeneratorExit``) is still recorded, with ``usage_missing``.
    """
    usage: Any = None
    last: Any = None
    error: str | None = None
    try:
        for chunk in response:
            found = _chunk_usage(chunk)
            if found is not None:
                usage = found
            if not _get(chunk, "choices"):
                continue
            last = chunk
            yield chunk
    except GeneratorExit:
        error = "abandoned"
        raise
    except BaseException as exc:
        error = type(exc).__name__
        raise
    finally:
        if usage is None:
            usage = _hidden_usage(last)
        _record_usage(
            agent_name=agent_name,
            kwargs=kwargs,
            response=last,
            usage=usage,
            streamed=True,
            started_at=started_at,
            start_mono=start_mono,
            error=error,
        )


async def _aiter_with_usage(
    response: Any,
    kwargs: dict[str, Any],
    agent_name: str | None,
    started_at: str,
    start_mono: float,
) -> AsyncIterator[Any]:
    """Async twin of :func:`_iter_with_usage`."""
    usage: Any = None
    last: Any = None
    error: str | None = None
    try:
        async for chunk in response:
            found = _chunk_usage(chunk)
            if found is not None:
                usage = found
            if not _get(chunk, "choices"):
                continue
            last = chunk
            yield chunk
    except GeneratorExit:
        error = "abandoned"
        raise
    except BaseException as exc:
        error = type(exc).__name__
        raise
    finally:
        if usage is None:
            usage = _hidden_usage(last)
        _record_usage(
            agent_name=agent_name,
            kwargs=kwargs,
            response=last,
            usage=usage,
            streamed=True,
            started_at=started_at,
            start_mono=start_mono,
            error=error,
        )


def _open_stream(
    kwargs: dict[str, Any], agent_name: str | None
) -> Generator[Any, None, None]:
    """Open a streamed ``litellm.completion`` and wrap it for usage capture.

    The request itself is made eagerly, so a request-time failure (bad key,
    unsupported tools) raises here — at the call site — exactly as the bare
    ``litellm.completion`` did, and leaves no record: no call was accepted.
    """
    started_at = _utc_now()
    start_mono = time.monotonic()
    response = litellm.completion(**kwargs)
    return _iter_with_usage(response, kwargs, agent_name, started_at, start_mono)


def stream_completion(
    *, agent_name: str | None = None, **kwargs: Any
) -> Generator[Any, None, None]:
    """Streamed ``litellm.completion`` with usage capture; yields raw chunks.

    The low-level entry for a call site that assembles its own kwargs and
    consumes raw LiteLLM chunks (the Designer's mock generator). ``stream``
    is forced on and the usage chunk is requested; everything else is passed
    through untouched. Errors propagate unchanged.
    """
    kwargs["stream"] = True
    kwargs.setdefault("stream_options", _STREAM_USAGE_OPTIONS)
    return _open_stream(kwargs, agent_name)


def complete(
    *,
    llm_config: dict[str, Any],
    messages: list[dict[str, Any]],
    agent_name: str | None = None,
    response_format: dict[str, Any] | None = None,
    **extra_kwargs: Any,
) -> Any:
    """Non-streaming litellm.completion.

    Builds kwargs (model, credentials, api_base, response_format) and calls
    litellm.completion. No temperature is sent. `agent_name` identifies the
    caller and tags the usage record; it is not forwarded to the provider.
    Errors propagate unchanged.
    """
    kwargs = _build_completion_kwargs(
        llm_config, messages, response_format=response_format, **extra_kwargs
    )
    if kwargs.get("stream"):
        return _open_stream(kwargs, agent_name)
    started_at = _utc_now()
    start_mono = time.monotonic()
    response = litellm.completion(**kwargs)
    _record_usage(
        agent_name=agent_name,
        kwargs=kwargs,
        response=response,
        usage=_get(response, "usage"),
        streamed=False,
        started_at=started_at,
        start_mono=start_mono,
    )
    return response


def complete_stream(
    *,
    llm_config: dict[str, Any],
    messages: list[dict[str, Any]],
    agent_name: str | None = None,
    response_format: dict[str, Any] | None = None,
    timeout: httpx.Timeout | float = LLM_STREAM_TIMEOUT,
    **extra_kwargs: Any,
) -> Generator[str, None, None]:
    """Streamed one-shot litellm.completion; yields text deltas.

    The streamed sibling of ``complete`` for call sites whose response is
    drained internally rather than displayed: same kwargs handling, plus
    ``stream=True`` and an inter-chunk stall timeout (``LLM_STREAM_TIMEOUT``
    unless overridden). Deliberately NOT ``stream_turn``: no tool-call loop,
    no message mutation, no warning text injected into the stream. Errors —
    including a tripped stall timeout mid-stream — propagate unchanged.
    """
    kwargs = _build_completion_kwargs(
        llm_config,
        messages,
        response_format=response_format,
        stream=True,
        timeout=timeout,
        **extra_kwargs,
    )
    start = time.monotonic()
    first = True
    stream = _open_stream(kwargs, agent_name)
    try:
        for chunk in stream:
            if first:
                print(
                    f"[llm-ttft] {agent_name or '?'}: first chunk after "
                    f"{time.monotonic() - start:.1f}s",
                    flush=True,
                )
                first = False
            delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            if delta:
                yield delta
    finally:
        # Close the wrapped stream explicitly so an abandoned generator records
        # its usage now, not whenever the garbage collector gets to it.
        stream.close()


async def acomplete(
    *,
    llm_config: dict[str, Any],
    messages: list[dict[str, Any]],
    agent_name: str | None = None,
    response_format: dict[str, Any] | None = None,
    **extra_kwargs: Any,
) -> Any:
    """Async litellm.acompletion.

    Returns the acompletion response (a regular response object, or an async
    iterable of chunks when stream=True is passed). No temperature is sent.
    `agent_name` identifies the caller and tags the usage record; it is not
    forwarded to the provider. Errors propagate unchanged. The streamed form
    is wrapped for usage capture; the wrapper swallows LiteLLM's usage chunk
    and is otherwise transparent.
    """
    kwargs = _build_completion_kwargs(
        llm_config, messages, response_format=response_format, **extra_kwargs
    )
    started_at = _utc_now()
    start_mono = time.monotonic()
    response = await litellm.acompletion(**kwargs)
    if kwargs.get("stream"):
        return _aiter_with_usage(response, kwargs, agent_name, started_at, start_mono)
    _record_usage(
        agent_name=agent_name,
        kwargs=kwargs,
        response=response,
        usage=_get(response, "usage"),
        streamed=False,
        started_at=started_at,
        start_mono=start_mono,
    )
    return response


def supports_response_format(model: str) -> bool:
    """Return True if the provider/model accepts the `response_format` kwarg.

    Used by agents (currently only CodeScanner) that want to force a
    JSON-only retry after schema validation fails. LiteLLM exposes
    `get_supported_openai_params` per model; if that probe fails we
    conservatively return False rather than risking a 400 on the retry.
    """
    if not model:
        return False
    try:
        params = litellm.get_supported_openai_params(model=model) or []
    except Exception:
        return False
    return "response_format" in params


def stream_turn(
    system_prompt: str,
    messages: list[dict[str, Any]],
    llm_config: dict[str, Any],
    search_config: SearchConfig | str | None,
    agent_name: str | None = None,
    response_format: dict[str, Any] | None = None,
    session: dict[str, Any] | None = None,
) -> Generator[str, None, None]:
    """Stream one LLM conversation turn, handling tool calls transparently.

    Yields text chunks consumed by streaming.start() via the agent run() generators.
    Mutates `messages` to record the full turn (assistant reply + tool calls/results).
    Loops internally until the LLM produces a final text response.

    `search_config` is the developer's web-search provider and key, or None to
    run without the tool. A bare key string is accepted and read as Tavily (see
    `websearch.coerce`).

    `agent_name` identifies the calling agent; it is not forwarded to the
    provider. No temperature is sent — see the note near the top of the module.

    `session`, when provided, receives status-line updates on
    `session["_stream_status"]` around web-search round-trips ("Searching the
    web: …", then "Reading search results…" while the follow-up request
    prefills, then the caller's entry status back once content resumes). The
    in-chat 🔍 marker alone is not enough: on a suppressed artifact turn the
    marker is swallowed with everything else, leaving the status line as the
    only sign of what the pipeline is doing.

    `response_format`, when provided, is forwarded to LiteLLM as-is — e.g.
    `{"type": "json_object"}` to force JSON-only output. When set, the
    web-search tool is suppressed for the call since JSON-mode responses
    do not interleave tool calls cleanly across providers — UNLESS the
    message history already contains tool_use / tool_result blocks, in
    which case `tools=` must remain present (Anthropic rejects the request
    otherwise with `UnsupportedParamsError`).
    """
    suppress_tools_for_format = (
        response_format is not None and not _history_has_tool_use(messages)
    )
    tools = (
        [WEB_SEARCH_TOOL]
        if search_config and not suppress_tools_for_format
        else None
    )

    # Snapshot the status at entry so it can be restored once the model
    # resumes producing text after a search round. Callers streaming through
    # _stream_suppressing_json get this for free (the wrapper republishes its
    # turn-kind status on every content chunk), but bare callers (Phaser,
    # Deployer) would otherwise show "Reading search results…" for the rest of
    # the turn.
    entry_status = session.get("_stream_status") if session is not None else None

    while True:
        llm_messages = [{"role": "system", "content": system_prompt}] + messages
        kwargs = _build_completion_kwargs(
            llm_config, llm_messages, response_format=response_format, stream=True
        )
        if tools:
            kwargs["tools"] = tools

        # Each round of the tool loop is its own request and gets its own
        # usage record — a search round re-sends the whole context, so its
        # prompt tokens are real spend, not a duplicate.
        try:
            response = _open_stream(kwargs, agent_name)
        except LiteLLMBadRequestError as exc:
            if tools and _is_tool_incompatible_error(exc):
                tools = None
                kwargs.pop("tools", None)
                yield (
                    "\n\n> ⚠️ Web search disabled: this model does not "
                    "support tool calling.\n\n"
                )
                response = _open_stream(kwargs, agent_name)
            else:
                raise

        full_text = ""
        tool_call_acc: dict[int, dict[str, str]] = {}
        tool_call_started = False

        try:
            for chunk in response:
                choice = chunk.choices[0]

                if choice.delta.tool_calls:
                    tool_call_started = True

                delta = choice.delta.content or ""
                if delta:
                    full_text += delta
                    if (
                        session is not None
                        and entry_status
                        and session.get("_stream_status")
                        == "Reading search results…"
                    ):
                        # Content resumed after a search round: put the
                        # caller's own status back. Guarded on the exact
                        # search text so a status someone else set in between
                        # is never clobbered.
                        session["_stream_status"] = entry_status
                    if not tool_call_started:
                        yield delta

                if choice.delta.tool_calls:
                    for tc in choice.delta.tool_calls:
                        i = tc.index
                        if i not in tool_call_acc:
                            tool_call_acc[i] = {
                                "id": "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc.id:
                            tool_call_acc[i]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_call_acc[i]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_call_acc[i]["arguments"] += (
                                    tc.function.arguments
                                )
        finally:
            # Close the wrapped stream explicitly so an abandoned turn records
            # its usage now, not whenever the garbage collector gets to it.
            response.close()

        if tool_call_acc:
            messages.append(
                {
                    "role": "assistant",
                    "content": full_text or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"],
                            },
                        }
                        for tc in tool_call_acc.values()
                    ],
                }
            )
            for tc in tool_call_acc.values():
                if tc["name"] == "web_search":
                    try:
                        query = json.loads(tc["arguments"]).get("query", "")
                    except (json.JSONDecodeError, KeyError):
                        query = tc["arguments"]
                    yield f"\n\n*🔍 Searching: {query}*\n\n"
                    # After the marker yield: the suppressing wrapper writes
                    # its own status on receiving the marker chunk, and this
                    # must land on top of that, not under it.
                    if session is not None:
                        session["_stream_status"] = (
                            f"Searching the web: {query}…"
                        )
                    if search_config is None:
                        raise RuntimeError(
                            "web_search tool called but search_config is None"
                        )
                    result = search(query, search_config)
                    if result.startswith("Search failed:") or result.startswith(
                        "No search tool"
                    ):
                        yield f"\n\n> ⚠️ {result}\n\n"
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        }
                    )
            # The next completion's prefill can take a while; the search
            # status would sit there stale. The streaming wrapper replaces
            # this the moment content chunks resume.
            if session is not None:
                session["_stream_status"] = "Reading search results…"
            continue

        else:
            messages.append({"role": "assistant", "content": full_text})
            return
