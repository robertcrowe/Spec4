from __future__ import annotations

import asyncio
import concurrent.futures
import json
from collections.abc import Coroutine, Generator
from typing import Any

import litellm
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


# Tool spec supplied to the LLM for web search.
WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for current information on any topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                }
            },
            "required": ["query"],
        },
    },
}

# Appended to a system prompt when web search is available.
WEB_SEARCH_ADDENDUM = (
    "\n\nYou have direct access to the web_search tool. "
    "Whenever the user asks you to search, look something up, or find information, "
    "you MUST immediately call the web_search tool — never say you cannot search or "
    "that you lack access to it. The tool works for any query on any topic."
)


def _url(api_key: str) -> str:
    return f"https://mcp.tavily.com/mcp/?tavilyApiKey={api_key}"


def _run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine from synchronous code.

    Always delegates to a fresh thread so it works regardless of whether
    the calling thread already has a running event loop (e.g. Streamlit).
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _list_tools_async(api_key: str) -> list[str]:
    async with streamablehttp_client(_url(api_key)) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [t.name for t in result.tools]


async def _call_search_async(query: str, api_key: str) -> str:
    async with streamablehttp_client(_url(api_key)) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # Discover the actual search tool name rather than hardcoding it.
            tools_result = await session.list_tools()
            tool = next(
                (t for t in tools_result.tools if "search" in t.name.lower()),
                None,
            )
            if tool is None:
                available = [t.name for t in tools_result.tools]
                return f"No search tool found. Available tools: {available}"
            result = await session.call_tool(tool.name, {"query": query})
            if result.content:
                return "\n".join(c.text for c in result.content if hasattr(c, "text"))
            return ""


def validate(api_key: str) -> tuple[bool, list[str], str]:
    """Validate a Tavily API key by listing available tools.

    Returns (True, tool_names, "") on success or (False, [], error_message) on failure.
    """
    try:
        tools = _run_async(_list_tools_async(api_key))
        return True, tools, ""
    except Exception as exc:
        return False, [], str(exc)


def search(query: str, api_key: str) -> str:
    """Run a web search via the Tavily MCP server. Returns the result text."""
    try:
        return str(_run_async(_call_search_async(query, api_key)))
    except Exception as exc:
        import traceback

        traceback.print_exc()
        return f"Search failed: {exc}"


def stream_turn(
    system_prompt: str,
    messages: list[dict[str, Any]],
    llm_config: dict[str, Any],
    tavily_api_key: str | None,
) -> Generator[str, None, None]:
    """Stream one LLM conversation turn, handling tool calls transparently.

    Yields text chunks for st.write_stream().
    Mutates `messages` to record the full turn (assistant reply + tool calls/results).
    Loops internally until the LLM produces a final text response.
    """
    tools = [WEB_SEARCH_TOOL] if tavily_api_key else None

    while True:
        llm_messages = [{"role": "system", "content": system_prompt}] + messages
        kwargs: dict[str, Any] = dict(
            model=llm_config["model"],
            messages=llm_messages,
            api_key=llm_config["api_key"],
            stream=True,
        )
        if tools:
            kwargs["tools"] = tools

        response = litellm.completion(**kwargs)

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
            # Record assistant's tool-call request.
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
            # Execute each tool call and add results.
            for tc in tool_call_acc.values():
                if tc["name"] == "web_search":
                    try:
                        query = json.loads(tc["arguments"]).get("query", "")
                    except (json.JSONDecodeError, KeyError):
                        query = tc["arguments"]
                    yield f"\n\n*🔍 Searching: {query}*\n\n"
                    assert tavily_api_key is not None  # guarded by `tools` check above
                    result = search(query, tavily_api_key)
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
            # Loop to get LLM's response to the tool results.
            continue

        else:
            messages.append({"role": "assistant", "content": full_text})
            return
