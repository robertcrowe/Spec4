from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI",
        "env_var": "OPENAI_API_KEY",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    },
    "anthropic": {
        "label": "Anthropic",
        "env_var": "ANTHROPIC_API_KEY",
        "models": [
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
        ],
    },
    "gemini": {
        "label": "Google Gemini",
        "env_var": "GEMINI_API_KEY",
        "models": [
            "gemini/gemini-2.0-flash",
            "gemini/gemini-1.5-pro",
            "gemini/gemini-1.5-flash",
        ],
    },
    "cohere": {
        "label": "Cohere",
        "env_var": "COHERE_API_KEY",
        "models": ["command-r-plus", "command-r", "command"],
    },
    "mistral": {
        "label": "Mistral",
        "env_var": "MISTRAL_API_KEY",
        "models": [
            "mistral/mistral-large-latest",
            "mistral/mistral-small-latest",
            "mistral/open-mistral-7b",
        ],
    },
}


def list_models(provider_key: str, api_key: str) -> tuple[list[str], str]:
    """Fetch available chat models from the provider's API.

    Returns (models, "") on success or ([], error_message) on HTTP/network failure.
    Falls back to the hardcoded model list if the API returns an empty result.
    """
    fallback = PROVIDERS[provider_key]["models"]
    try:
        raw = _fetch_models(provider_key, api_key)
        # Preserve order while removing duplicates (some APIs return the same model ID twice).  # noqa: E501
        models = list(dict.fromkeys(raw))
        return (models if models else fallback), ""
    except urllib.error.HTTPError as exc:
        return [], f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        return [], str(exc)


def _json_get(url: str, headers: dict[str, str]) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        result: dict[str, Any] = json.loads(resp.read().decode())
        return result


def _fetch_models(provider_key: str, api_key: str) -> list[str]:
    if provider_key == "openai":
        data = _json_get(
            "https://api.openai.com/v1/models", {"Authorization": f"Bearer {api_key}"}
        )
        chat_prefixes = ("gpt-", "o1", "o3", "chatgpt-")
        return sorted(
            m["id"]
            for m in data.get("data", [])
            if any(m["id"].startswith(p) for p in chat_prefixes)
        )

    if provider_key == "anthropic":
        data = _json_get(
            "https://api.anthropic.com/v1/models",
            {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        )
        return [m["id"] for m in data.get("data", [])]

    if provider_key == "gemini":
        data = _json_get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}", {}
        )
        return [
            f"gemini/{m['name'].removeprefix('models/')}"
            for m in data.get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        ]

    if provider_key == "cohere":
        data = _json_get(
            "https://api.cohere.com/v2/models", {"Authorization": f"Bearer {api_key}"}
        )
        return [
            m["name"]
            for m in data.get("models", [])
            if "chat" in m.get("endpoints", [])
        ]

    if provider_key == "mistral":
        data = _json_get(
            "https://api.mistral.ai/v1/models", {"Authorization": f"Bearer {api_key}"}
        )
        return [
            f"mistral/{m['id']}"
            for m in data.get("data", [])
            if "embed" not in m.get("id", "")
        ]

    return []
