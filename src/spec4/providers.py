from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import boto3

PROVIDERS: dict[str, dict[str, Any]] = {
    "anthropic": {
        "label": "Anthropic",
        "env_var": "ANTHROPIC_API_KEY",
    },
    "bedrock": {
        "label": "AWS Bedrock",
        "env_var": "AWS_ACCESS_KEY_ID",
    },
    "cohere": {
        "label": "Cohere",
        "env_var": "COHERE_API_KEY",
    },
    "gemini": {
        "label": "Google Gemini",
        "env_var": "GEMINI_API_KEY",
    },
    "mistral": {
        "label": "Mistral",
        "env_var": "MISTRAL_API_KEY",
    },
    "nebius": {
        "label": "Nebius Token Factory",
        "env_var": "NEBIUS_API_KEY",
        "api_base": "https://api.tokenfactory.nebius.com/v1/",
    },
    "openai": {
        "label": "OpenAI",
        "env_var": "OPENAI_API_KEY",
    },
    "openrouter": {
        "label": "OpenRouter",
        "env_var": "OPENROUTER_API_KEY",
    },
}


def _is_iam_access_key(key: str) -> bool:
    """Return True if key looks like an AWS IAM access key ID (AKIA…/ASIA… prefix)."""
    return key.upper()[:4] in ("AKIA", "ASIA", "AROA", "AIPA", "ANPA", "ANVA", "APKA")


def bedrock_auth_kwargs(api_key: str) -> dict[str, str]:
    """Parse Bedrock credentials into litellm kwargs.

    Bedrock API key (new-style, recommended):
      API_KEY:REGION

    IAM access key (legacy):
      ACCESS_KEY_ID:SECRET_ACCESS_KEY:REGION
      ACCESS_KEY_ID:SECRET_ACCESS_KEY:REGION:SESSION_TOKEN

    Blank → ambient AWS credential chain (env vars, ~/.aws/credentials, IAM role).

    Detection: if the first token starts with a known IAM prefix (AKIA/ASIA/…)
    it is treated as an IAM access key; everything else is a Bedrock API key.
    """
    parts = (api_key or "").split(":", 3)
    first = parts[0].strip()

    if not first:
        return {}

    if _is_iam_access_key(first):
        result: dict[str, str] = {"aws_access_key_id": first}
        if len(parts) >= 2 and parts[1].strip():
            result["aws_secret_access_key"] = parts[1].strip()
        if len(parts) >= 3 and parts[2].strip():
            result["aws_region_name"] = parts[2].strip()
        if len(parts) >= 4 and parts[3].strip():
            result["aws_session_token"] = parts[3].strip()
        return result

    # Bedrock API key
    result = {"api_key": first}
    if len(parts) >= 2 and parts[1].strip():
        result["aws_region_name"] = parts[1].strip()
    return result


def list_models(provider_key: str, api_key: str) -> tuple[list[str], str]:
    """Fetch available chat models from the provider's API.

    Returns (models, "") on success or ([], error_message) on failure.
    """
    try:
        raw = _fetch_models(provider_key, api_key)
        return sorted(dict.fromkeys(raw)), ""
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

    if provider_key == "bedrock":
        creds = bedrock_auth_kwargs(api_key)
        region = creds.get("aws_region_name", "us-east-1")
        if "api_key" in creds:
            # New-style Bedrock API key — use REST API with bearer token.
            data = _json_get(
                f"https://bedrock.{region}.amazonaws.com/foundation-models",
                {"Authorization": f"Bearer {creds['api_key']}"},
            )
            return [
                f"bedrock/converse/{m['modelId']}"
                for m in data.get("modelSummaries", [])
                if "ON_DEMAND" in m.get("inferenceTypesSupported", [])
            ]
        # IAM or ambient credentials — use boto3/SigV4.
        client_kwargs: dict[str, Any] = {
            "service_name": "bedrock",
            "region_name": region,
        }
        for k in ("aws_access_key_id", "aws_secret_access_key", "aws_session_token"):
            if creds.get(k):
                client_kwargs[k] = creds[k]
        client = boto3.client(**client_kwargs)
        response = client.list_foundation_models(byOutputModality="TEXT")
        return [
            f"bedrock/converse/{m['modelId']}"
            for m in response.get("modelSummaries", [])
            if "ON_DEMAND" in m.get("inferenceTypesSupported", [])
        ]

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

    if provider_key == "openrouter":
        # The model list is public — it returns the full catalogue for a bogus
        # bearer just as happily as for a real one. Every other provider's list
        # call doubles as the credential check that gates the setup and
        # per-agent flows, so on its own this one would let a wrong key through
        # to the first real call, which fails as a bare 401 minutes later. Verify
        # the key against an endpoint that actually requires it first.
        if api_key:
            _json_get(
                "https://openrouter.ai/api/v1/key",
                {"Authorization": f"Bearer {api_key}"},
            )
        data = _json_get(
            "https://openrouter.ai/api/v1/models",
            {"Authorization": f"Bearer {api_key}"} if api_key else {},
        )
        return [
            f"openrouter/{m['id']}"
            for m in data.get("data", [])
            if m.get("id")
        ]

    if provider_key == "nebius":
        api_base = PROVIDERS["nebius"]["api_base"]
        data = _json_get(
            f"{api_base}models", {"Authorization": f"Bearer {api_key}"}
        )
        return [
            f"openai/{m['id']}"
            for m in data.get("data", [])
            if "embed" not in m.get("id", "").lower()
        ]

    return []


def all_provider_labels() -> list[str]:
    """Return display labels for all providers, in registry order."""
    return [p["label"] for p in PROVIDERS.values()]


def provider_key_for_label(label: str) -> str:
    """Return the provider key for a display label, falling back to first."""
    for key, info in PROVIDERS.items():
        if info["label"] == label:
            return key
    return next(iter(PROVIDERS))
