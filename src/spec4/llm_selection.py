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
from spec4.llm import supports_reasoning_effort

__all__ = [
    "AGENT_KEYS",
    "BASE_EFFORTS",
    "DEFAULT_EFFORT",
    "PROVIDER_EXTRA_EFFORTS",
    "build_llm_config",
    "capability",
    "default_is_connected",
    "default_provider_model",
    "effort_for",
    "entry",
    "is_connected",
    "key_for_provider",
    "model_effort_display",
    "offered_efforts",
    "probe_capabilities",
    "resolve",
]

# The value meaning "send nothing" — never transmitted as a level. Stored
# rather than absent so a selection record always answers the question.
DEFAULT_EFFORT = "default"

# Offered for every model whose provider accepts `reasoning_effort` at all.
BASE_EFFORTS: tuple[str, ...] = (DEFAULT_EFFORT, "low", "medium", "high")

# D-EF1: the extension point for provider-specific effort levels beyond the
# base four. Seeded from the two providers that document a level above "high";
# a provider with no entry here offers exactly `BASE_EFFORTS`.
#
# This table is keyed by *provider*, not by model, and is deliberately coarse:
# a level that a specific model, or the installed LiteLLM's mapping for it,
# rejects is handled by the one-shot fallback retry in `llm.py`, NOT by
# pruning entries from here. Do not add model-level conditions to this table —
# the retry is what keeps a rejected level from failing a run, and it works for
# models that do not exist yet.
PROVIDER_EXTRA_EFFORTS: dict[str, tuple[str, ...]] = {
    "anthropic": ("max",),
    "openai": ("xhigh",),
}


def build_llm_config(
    provider_key: str,
    model: str,
    api_key: str | None,
    effort: str = DEFAULT_EFFORT,
) -> dict[str, Any]:
    """LiteLLM kwargs for one provider/model/credential triple, plus effort.

    The only place an ``llm_config`` is assembled — the setup wizard's default
    and every per-agent override come out of here, so both carry the same
    shape: ``model`` always, ``api_base`` where the provider registry pins one
    (Nebius), and either an ``api_key`` or the parsed ``aws_*`` set for
    Bedrock, whose single credential field encodes region and credential
    variant both (see ``providers.bedrock_auth_kwargs``).

    ``effort`` rides *inside* this dict rather than beside it, and that is what
    makes sub-agent inheritance free: :func:`resolve` hands one object to the
    agent dispatch, every sub-agent already receives that same object, so the
    effort follows the model down the tree under the existing rule instead of
    a second one. ``llm._build_completion_kwargs`` pops it back out — it is a
    spec4 field, not a LiteLLM parameter, and is never forwarded under this
    name.
    """
    provider_info = providers.PROVIDERS.get(provider_key, {})
    llm_config: dict[str, Any] = {"model": model}
    if "api_base" in provider_info:
        llm_config["api_base"] = provider_info["api_base"]
    if provider_key == "bedrock":
        llm_config.update(providers.bedrock_auth_kwargs(api_key or ""))
    else:
        llm_config["api_key"] = api_key or ""
    llm_config["effort"] = effort or DEFAULT_EFFORT
    return llm_config


def offered_efforts(provider_key: str | None, model: str) -> list[str]:
    """The effort values to offer for a resolved provider/model pair.

    D-EF2: the capability probe is consulted **only** for whether
    `reasoning_effort` is an accepted parameter — never for which levels are
    accepted, which LiteLLM does not report. The levels come from
    :data:`BASE_EFFORTS` plus this provider's :data:`PROVIDER_EXTRA_EFFORTS`
    entry, and from nothing else. Never infer a level list from a model name.

    The three probe answers are three different results, and ``False`` is not
    ``None``:

    * accepted   -> the base four, plus the provider's extra levels
    * unknown    -> the base four (the probe could not answer; offer the
                    portable set rather than raising or returning nothing)
    * unaccepted -> ``["default"]`` alone, which is how the gate and the setup
                    wizard know to render the control disabled

    D-EF4: ``provider_key`` is passed in, never derived from ``model``. The
    model string is not a reliable provider source — Nebius models carry an
    ``openai/`` prefix for LiteLLM compatibility, and OpenAI, Anthropic and
    Cohere models arrive bare — so prefix-parsing would misfile them. The
    provider is stored alongside the model (``session["provider"]``,
    ``entry["provider"]``) precisely because it cannot be recovered from it.
    """
    supported = supports_reasoning_effort(model)
    if supported is False:
        return [DEFAULT_EFFORT]
    if supported is None:
        return list(BASE_EFFORTS)
    return [*BASE_EFFORTS, *PROVIDER_EXTRA_EFFORTS.get(provider_key or "", ())]


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


def is_connected(session: dict[str, Any], agent: str) -> bool:
    """Whether ``agent`` has a model it can actually send a request with.

    The question every turn implicitly asks, made explicit and asked *before*
    the request rather than by subscripting the result. It goes through
    :func:`resolve`, so it answers about the same config the turn will use: an
    agent with a working per-agent override is connected even when the session
    default is empty, and one riding the default is connected only when the
    default is real.

    ``model`` is the field checked because it is the field the request cannot
    be built without (``llm._build_completion_kwargs`` reads it first, and
    every credential beside it is optional — a Bedrock config carries
    ``aws_*`` and no ``api_key``, a local model may carry neither).

    Note what this deliberately does not consult: the saved prefs. A remembered
    provider and model are what the setup wizard *prefills from*, not evidence
    that a connection was ever made in this session, and treating them as such
    is what let an unconfigured session reach an agent turn and die inside
    LiteLLM.
    """
    return bool((resolve(session, agent) or {}).get("model"))


# An agent key no override can ever be filed under: `AGENT_KEYS` holds seven
# non-empty names, so `entry()` always misses on this one and `resolve()` falls
# straight through to the session default. It exists so asking for the default
# goes through the same function every agent turn goes through.
_NO_AGENT = ""


def default_is_connected(session: dict[str, Any] | None) -> bool:
    """Whether the *session default* is a real connection — what the bar says.

    Asked through :func:`is_connected` with the same no-op agent key
    :func:`default_provider_model` uses, so the status bar's "am I connected"
    and its "which model" come from one resolution path and cannot disagree.

    Scoped to the default deliberately: the bar has only ever described the
    default, so an agent running on a per-agent override does not make this
    true. That agent's own gate names its model.
    """
    return is_connected(session or {}, _NO_AGENT)


def effort_for(session: dict[str, Any] | None, agent: str) -> str:
    """The effort ``agent`` runs at — its override's, else the default's.

    Goes through :func:`resolve`, so it answers about the same config the turn
    will use and an agent left on the default inherits the default's effort by
    the same route it inherits the default's model. Not a parallel read path:
    it has the relationship to :func:`resolve` that :func:`is_connected` has.

    Falls back to ``"default"`` rather than ``None`` so callers never have to
    special-case a config written before this field existed.
    """
    config = resolve(session or {}, agent) or {}
    return str(config.get("effort") or DEFAULT_EFFORT)


def model_effort_display(model: str | None, effort: str | None) -> str:
    """``"claude-sonnet-5 · high"`` — the model, and the effort when it is one.

    The one formatting rule behind every surface that prints a model name: the
    status bar's model slot, the chat frame's model chip and its retry panel,
    the agent rows' last-model column, and the gate's Keep button. It is a
    function rather than five f-strings because five copies of "show it unless
    it is the default" is how the chip and the bar end up disagreeing about the
    same agent.

    ``"default"`` means *send nothing* (see :data:`DEFAULT_EFFORT`), so it is
    not a level and never shows. On a model that accepts the parameter the
    request actually carries ``llm.DEFAULT_THINKING_EFFORT``; the usage record
    shows that, this shows the developer's choice. Every other value does —
    including the fallback string ``"default (fallback from high)"`` that
    ``llm`` records when a provider refuses a level, which is not
    ``"default"`` and is worth seeing. ``usage_report._fmt_models`` already
    draws the line in that same place.

    A blank model stays blank rather than becoming a lone effort: an agent that
    has not run this round has an empty last-model cell, and ``· high`` on its
    own would read as a run.

    Note what this deliberately does **not** serve: the gate panel's naming
    line, which reads ``Model for Phaser: claude-sonnet-5 · default`` and shows
    the effort *always*. That line states the default in full, suffix rule and
    all, and folding it in here would either strip the ``· default`` it is
    specified to carry or put one onto every other surface.
    """
    if not model:
        return ""
    level = str(effort or DEFAULT_EFFORT)
    return f"{model} · {level}" if level != DEFAULT_EFFORT else str(model)


def default_provider_model(
    session: dict[str, Any] | None,
    prefs: dict[str, Any] | None,
    agent: str = _NO_AGENT,
) -> tuple[str | None, str | None, str]:
    """``(provider, model, effort)`` for the session default, or for an agent.

    The model and the effort come back through :func:`resolve`, so whichever
    selection is asked for is read by the *same* path an agent turn reads it
    by and the app keeps exactly one model-resolution route. The provider has
    no home in an ``llm_config`` (it is folded into the model string and the
    credential kwargs), so it is read from the entry, the session, and then
    from the remembered prefs.

    ``agent`` defaults to the no-op key :data:`_NO_AGENT`, which no override
    can be filed under, so the bare two-argument call answers about the
    project default exactly as it always has. Passing a real agent key answers
    about *that agent's* selection instead — its override when it has one, the
    default when it does not — which is what lets the status bar name the
    model the screen in front of the developer is actually going to run on
    without a second resolution path being written to do it.

    Provider and model are ``None`` before /setup has run, or after a "Clear
    saved settings"; the caller renders its own empty state rather than a
    blank. Effort is never ``None`` — an unset effort is ``"default"``, which
    is a real value meaning "send nothing".
    """
    session = session or {}
    prefs = prefs or {}
    config = resolve(session, agent) or {}
    override = entry(session, agent)
    model = config.get("model") or session.get("model") or prefs.get("model")
    if override is not None:
        # An override carries its own provider and its own effort, and neither
        # falls back to the default's: an agent pinned to OpenAI must not be
        # labelled with the default's Anthropic, and one left on "default"
        # effort must not inherit the default's "high".
        provider = override.get("provider")
        effort = config.get("effort") or DEFAULT_EFFORT
    else:
        provider = session.get("provider") or prefs.get("provider")
        effort = config.get("effort") or session.get("effort") or prefs.get("effort")
    return (
        str(provider) if provider else None,
        str(model) if model else None,
        str(effort) if effort else DEFAULT_EFFORT,
    )


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
