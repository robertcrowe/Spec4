from __future__ import annotations

from typing import Any

import litellm

# Minimal tool — trivial enough that any tool-capable model will accept it.
_PROBE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_color",
        "description": "Return the typical color of an object.",
        "parameters": {
            "type": "object",
            "properties": {
                "item": {"type": "string", "description": "The object to look up."}
            },
            "required": ["item"],
        },
    },
}


def probe_tool_support(model: str, api_key: str, api_base: str | None = None) -> bool:
    """Return True if the model accepts tool/function calling.

    Sends a real minimal API call with a tool definition.  A successful
    response (text or tool call) means the model accepted the parameter;
    any exception means it didn't.
    """
    try:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": "What color is a banana?"}],
            "tools": [_PROBE_TOOL],
            "api_key": api_key,
            "max_tokens": 10,
            "stream": False,
        }
        if api_base is not None:
            kwargs["api_base"] = api_base
        litellm.completion(**kwargs)
        return True
    except Exception:
        return False
