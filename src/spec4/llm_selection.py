"""Which model each agent runs on: the session default, plus per-agent overrides.

The developer configures one provider/model/key in /setup. That is the
**default**, and every agent uses it unless it has an override of its own —
"a cheap model for CodeScanner, a strong reasoner for Phaser". Overrides are
keyed by the seven user-facing agent names in ``app_constants.AGENT_KEYS`` and
by nothing else: a sub-agent never appears here, it inherits whatever its
parent resolved (see :func:`resolve`).

This module is the single spine both flows share. The setup wizard and the
per-agent gate call the same builder and the same probe wrapper, so the two
paths cannot drift — a Bedrock credential parsed one way in one place and
another way in the other is the class of bug this exists to prevent.

Two conventions inherited from the default flow and preserved deliberately:

* The model-list fetch (``providers.list_models``) is a **hard gate** — no
  models means no config is written. That check lives in the callbacks, since
  it is about what the UI does next.
* The capability probes are **advisory** and never block. ``False`` means
  "probed, unsupported"; ``None`` means unknown, and unknown is treated as
  capable by every consumer. A probe that fails must never leave an agent
  unable to start.
"""

from __future__ import annotations

from typing import Any

from spec4 import providers
from spec4.agents._image_probe import probe_image_support
from spec4.agents._tool_probe import probe_tool_support
from spec4.app_constants import AGENT_KEYS

__all__ = [
    "AGENT_KEYS",
    "build_llm_config",
    "capability",
    "entry",
    "key_for_provider",
    "probe_capabilities",
    "resolve",
]


def build_llm_config(
    provider_key: str, model: str, api_key: str | None
) -> dict[str, Any]:
    """LiteLLM kwargs for one provider/model/credential triple.

    The only place an ``llm_config`` is assembled — the setup wizard's default
    and every per-agent override come out of here, so both carry the same
    shape: ``model`` always, ``api_base`` where the provider registry pins one
    (Nebius), and either an ``api_key`` or the parsed ``aws_*`` set for
    Bedrock, whose single credential field encodes region and credential
    variant both (see ``providers.bedrock_auth_kwargs``).
    """
    provider_info = providers.PROVIDERS.get(provider_key, {})
    llm_config: dict[str, Any] = {"model": model}
    if "api_base" in provider_info:
        llm_config["api_base"] = provider_info["api_base"]
    if provider_key == "bedrock":
        llm_config.update(providers.bedrock_auth_kwargs(api_key or ""))
    else:
        llm_config["api_key"] = api_key or ""
    return llm_config


def probe_capabilities(
    provider_key: str, llm_config: dict[str, Any]
) -> tuple[bool | None, bool | None]:
    """``(image_support, tool_support)`` for a built config. Never raises.

    Bedrock Converse is inherently multimodal and tool-capable; probing it via
    non-streaming completion calls is unreliable against the Converse API, so
    it is skipped and both are assumed.

    Otherwise each probe makes one real, minimal call. The probe helpers
    already swallow their own exceptions and return ``False``, so ``None`` here
    is the defensive case — an unknown, not a negative. Callers treat it as
    capable rather than blocking on it.
    """
    if provider_key == "bedrock":
        return True, True

    model = llm_config.get("model") or ""
    api_key = llm_config.get("api_key") or ""
    api_base = llm_config.get("api_base")
    aws_kwargs = {k: v for k, v in llm_config.items() if k.startswith("aws_")}

    image_support: bool | None = None
    try:
        image_support = probe_image_support(
            model, api_key, api_base=api_base, **aws_kwargs
        )
    except Exception:
        image_support = None

    tool_support: bool | None = None
    try:
        tool_support = probe_tool_support(
            model, api_key, api_base=api_base, **aws_kwargs
        )
    except Exception:
        tool_support = None

    return image_support, tool_support


def entry(session: dict[str, Any], agent: str) -> dict[str, Any] | None:
    """The agent's override entry, or None when it runs on the default."""
    overrides = (session or {}).get("agent_llm") or {}
    value = overrides.get(agent) if isinstance(overrides, dict) else None
    return value if isinstance(value, dict) and value else None


def resolve(session: dict[str, Any], agent: str) -> dict[str, Any] | None:
    """The ``llm_config`` ``agent`` runs on: its override, else the default.

    Called once per turn, at the top of the agent dispatch — which is what
    makes sub-agent inheritance free. Every sub-agent already receives its
    parent's ``llm_config`` as an argument, so resolving here puts the whole
    tree under one selection with no sub-agent knowing an override exists, and
    no interactive step able to land inside a Fast Forward sweep.

    Returns the default unchanged (``None`` included, before setup has run) so
    an unconfigured session fails exactly where it did before.
    """
    override = entry(session, agent)
    if override is not None:
        config = override.get("llm_config")
        if isinstance(config, dict) and config.get("model"):
            return config
    default: dict[str, Any] | None = (session or {}).get("llm_config")
    return default


def capability(
    session: dict[str, Any],
    agent: str,
    field: str,
    fallback: bool | None = None,
) -> bool | None:
    """A per-agent probe result, falling back to the global capability store.

    ``field`` is ``"image_support"`` or ``"tool_support"``. An override that
    probed cleanly answers for itself — a Designer pinned to a text-only model
    must report no image support even though the default model has it. An
    override whose probe came back unknown falls through to ``fallback``, and
    an unknown there means capable, per the module docstring.
    """
    override = entry(session, agent)
    if override is not None:
        value = override.get(field)
        if value is not None:
            return bool(value)
    return fallback


def key_for_provider(
    session: dict[str, Any], prefs: dict[str, Any], provider_key: str
) -> str:
    """Prefill for a credential field, or "" when nothing is known.

    Order: the key remembered for this provider, then the legacy single saved
    key when it belongs to this provider, then the session default's key when
    the provider matches. Never returns one provider's key for another, and
    never mutates anything — reading a prefill must not make the default's
    credential the override's.
    """
    prefs = prefs or {}
    saved = prefs.get("provider_keys")
    if isinstance(saved, dict) and saved.get(provider_key):
        return str(saved[provider_key])
    if prefs.get("api_key") and prefs.get("provider") == provider_key:
        return str(prefs["api_key"])
    session = session or {}
    if session.get("api_key") and session.get("provider") == provider_key:
        return str(session["api_key"])
    return ""
