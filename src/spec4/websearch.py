"""Web search providers.

Spec4's agents can call a `web_search` tool during a turn. The search itself is
served by a third-party MCP endpoint the developer supplies a key for — either
Tavily or Exa. Both speak streamable-HTTP MCP and both expose a search tool, so
the transport below is shared; only the endpoint URL and how the key is
presented differ (see ``PROVIDERS``).

The credential travels through the agents as a :class:`SearchConfig` rather than
a bare key string, because the key alone no longer says which service to call.
Everything that accepts one also accepts a plain string, which is read as a
Tavily key — that keeps sessions and preferences saved before Exa existed
working after an upgrade, and it is why ``coerce`` exists.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# Tool spec supplied to the LLM for web search. Deliberately provider-neutral:
# the model asks for `web_search` and Spec4 routes it, so a developer switching
# providers does not change what any agent's prompt has to say about searching.
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

# `auth` is how the key reaches the endpoint:
#   "query" — appended as a query parameter named `key_param`.
#   "header" — sent as the `key_header` request header. Preferred where the
#     provider documents it: a key in the URL leaks into logs and history.
PROVIDERS: dict[str, dict[str, Any]] = {
    "tavily": {
        "label": "Tavily",
        "url": "https://mcp.tavily.com/mcp/",
        "auth": "query",
        "key_param": "tavilyApiKey",
        "key_label": "Tavily API Key",
        "placeholder": "tvly-…",
        "signup_url": "https://tavily.com/",
        "blurb": (
            "Search built for AI agents, with a generous free tier. "
            "Keys start with `tvly-`."
        ),
    },
    "exa": {
        "label": "Exa",
        "url": "https://mcp.exa.ai/mcp",
        "auth": "header",
        "key_header": "x-api-key",
        "key_label": "Exa API Key",
        "placeholder": "your Exa API key",
        "signup_url": "https://exa.ai/",
        "blurb": (
            "Neural search over a curated web index, strong on technical and "
            "research content."
        ),
    },
}

DEFAULT_PROVIDER = "tavily"


@dataclass(frozen=True)
class SearchConfig:
    """A web-search provider plus the key to reach it.

    Instances are always truthy, so the many ``if search:`` / ``if not
    search_cfg:`` checks that used to test a key string still read correctly.
    Absence is represented by ``None``, never by an empty config.
    """

    provider: str
    api_key: str


def all_provider_labels() -> list[str]:
    """Display labels for the setup page's provider select, in registry order."""
    return [p["label"] for p in PROVIDERS.values()]


def provider_key_for_label(label: str) -> str:
    """Map a display label back to its registry key. Unknown → the default."""
    for key, spec in PROVIDERS.items():
        if spec["label"] == label:
            return key
    return DEFAULT_PROVIDER


def label_for_provider(provider: str) -> str:
    """Display label for a registry key. Unknown → the default's label."""
    spec = PROVIDERS.get(provider) or PROVIDERS[DEFAULT_PROVIDER]
    return str(spec["label"])


def coerce(value: SearchConfig | str | None) -> SearchConfig | None:
    """Normalise a search credential to a ``SearchConfig`` or ``None``.

    A bare string is read as a Tavily key: Tavily was the only provider before
    Exa, so that is what a pre-upgrade session, saved preference, or older test
    is holding. Empty strings mean "no search", not "Tavily with a blank key".
    """
    if value is None:
        return None
    if isinstance(value, SearchConfig):
        return value if value.api_key else None
    text = str(value).strip()
    return SearchConfig(DEFAULT_PROVIDER, text) if text else None


def from_session(session: dict[str, Any]) -> SearchConfig | None:
    """Build the search config a turn should use, or None if search is off.

    Falls back to the pre-Exa ``tavily_api_key`` key so a browser session
    carried across an upgrade keeps its web search instead of silently losing
    it (``session`` is sessionStorage — it outlives a reload).
    """
    key = session.get("search_api_key") or session.get("tavily_api_key")
    if not key:
        return None
    provider = session.get("search_provider") or DEFAULT_PROVIDER
    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER
    return SearchConfig(provider, str(key))


def _endpoint(config: SearchConfig) -> tuple[str, dict[str, str] | None]:
    """Return the (url, headers) pair that reaches this provider's MCP server."""
    spec = PROVIDERS.get(config.provider) or PROVIDERS[DEFAULT_PROVIDER]
    if spec["auth"] == "header":
        return str(spec["url"]), {spec["key_header"]: config.api_key}
    return f"{spec['url']}?{spec['key_param']}={config.api_key}", None


def _url(api_key: str) -> str:
    """Tavily's endpoint URL. Retained for the Tavily-only call path."""
    return _endpoint(SearchConfig("tavily", api_key))[0]


def _run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine from synchronous code.

    Always delegates to a fresh thread so it works regardless of whether
    the calling thread already has a running event loop.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _list_tools_async(config: SearchConfig) -> list[str]:
    url, headers = _endpoint(config)
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [t.name for t in result.tools]


async def _call_search_async(query: str, config: SearchConfig) -> str:
    url, headers = _endpoint(config)
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # Discover the actual search tool name rather than hardcoding it —
            # Tavily calls it `tavily_search`, Exa `web_search_exa`, and either
            # is free to rename it.
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


def validate(config: SearchConfig | str) -> tuple[bool, list[str], str]:
    """Validate a search key by listing the provider's tools.

    Returns (True, tool_names, "") on success or (False, [], error) on failure.
    """
    cfg = coerce(config)
    if cfg is None:
        return False, [], "No API key supplied."
    try:
        tools = _run_async(_list_tools_async(cfg))
        return True, tools, ""
    except Exception as exc:
        return False, [], str(exc)


def search(query: str, config: SearchConfig | str | None) -> str:
    """Run a web search via the configured provider. Returns the result text."""
    cfg = coerce(config)
    if cfg is None:
        return "Search failed: no web search provider is configured."
    try:
        return str(_run_async(_call_search_async(query, cfg)))
    except Exception as exc:
        return f"Search failed: {exc}"
