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
import time
from collections.abc import Generator
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
    "search",
    "stream_turn",
    "supports_response_format",
]

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
    Any additional keyword arguments are merged via **extra.
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
    return kwargs


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
    caller but is not forwarded to the provider. Errors propagate unchanged.
    """
    kwargs = _build_completion_kwargs(
        llm_config, messages, response_format=response_format, **extra_kwargs
    )
    return litellm.completion(**kwargs)


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
    for chunk in litellm.completion(**kwargs):
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
    `agent_name` identifies the caller but is not forwarded to the provider.
    Errors propagate unchanged.
    """
    kwargs = _build_completion_kwargs(
        llm_config, messages, response_format=response_format, **extra_kwargs
    )
    return await litellm.acompletion(**kwargs)


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

    while True:
        llm_messages = [{"role": "system", "content": system_prompt}] + messages
        kwargs: dict[str, Any] = dict(
            model=llm_config["model"],
            messages=llm_messages,
            stream=True,
        )
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
        if tools:
            kwargs["tools"] = tools
        if response_format is not None:
            kwargs["response_format"] = response_format

        try:
            response = litellm.completion(**kwargs)
        except LiteLLMBadRequestError as exc:
            if tools and _is_tool_incompatible_error(exc):
                tools = None
                kwargs.pop("tools", None)
                yield (
                    "\n\n> ⚠️ Web search disabled: this model does not "
                    "support tool calling.\n\n"
                )
                response = litellm.completion(**kwargs)
            else:
                raise

        full_text = ""
        tool_call_acc: dict[int, dict[str, str]] = {}
        tool_call_started = False

        for chunk in response:
            choice = chunk.choices[0]

            if choice.delta.tool_calls:
                tool_call_started = True

            delta = choice.delta.content or ""
            if delta:
                full_text += delta
                if not tool_call_started:
                    yield delta

            if choice.delta.tool_calls:
                for tc in choice.delta.tool_calls:
                    i = tc.index
                    if i not in tool_call_acc:
                        tool_call_acc[i] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        tool_call_acc[i]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_call_acc[i]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_call_acc[i]["arguments"] += tc.function.arguments

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
            continue

        else:
            messages.append({"role": "assistant", "content": full_text})
            return
