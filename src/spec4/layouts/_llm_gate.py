"""The per-agent model gate: "use the default, or pick one for this agent".

Rendered at agent entry, before the agent's first turn, and again whenever the
developer clicks the model chip mid-agent. One card serves all seven agents and
both surfaces (chat and the Designer wizard) — only one gate is ever open, so
the agent it belongs to is recorded in ``session["agent_llm_draft"]`` rather
than in component ids.

The card has two resting shapes, because ``agent_llm`` and ``agent_llm_asked``
are cleared on different events. After "Start New Project" the override
survives but the answer does not, so the developer arrives with a choice
already made and needs it offered back rather than re-entered:

* **no entry** — "use the default" or "pick a model"
* **entry present** — "keep <model>", "use the default", or "pick a different
  model". Keeping costs nothing: the entry carries its own credential, model
  list and probe results, so there is no key to re-type and no probe to re-run.

Expanding "pick" swaps in the same provider/key/model fields the setup wizard
uses (``layouts._setup``), so the two cannot drift.
"""

from __future__ import annotations

from typing import Any

from dash import html
import dash_mantine_components as dmc

from spec4 import llm_selection, providers
from spec4.layouts._setup import GATE_IDS, model_field, provider_key_fields
from spec4.layouts._shared import _card, _error

_AGENT_LABELS: dict[str, str] = {
    "code_scanner": "CodeScanner",
    "brainstormer": "Brainstormer",
    "agentifier": "Agentifier",
    "designer": "Designer",
    "stack_advisor": "StackAdvisor",
    "phaser": "Phaser",
    "deployer": "Deployer",
}


def agent_label(agent: str) -> str:
    return _AGENT_LABELS.get(agent, agent)


def _describe(provider_key: str | None, model: str | None) -> str:
    """"gpt-5-mini (OpenAI)" — or just the model when the provider is unknown."""
    if not model:
        return "no model selected"
    info = providers.PROVIDERS.get(provider_key or "", {})
    label = info.get("label")
    return f"{model} ({label})" if label else str(model)


def default_description(session: dict[str, Any]) -> str:
    return _describe(session.get("provider"), (session.get("llm_config") or {}).get(
        "model"
    ) or session.get("model"))


def is_open(session: dict[str, Any], agent: str) -> bool:
    """Whether the gate must be answered before this agent can run."""
    asked = session.get("agent_llm_asked") or {}
    return not asked.get(agent)


def _draft_for(session: dict[str, Any], agent: str) -> dict[str, Any] | None:
    draft = session.get("agent_llm_draft") or {}
    return draft if isinstance(draft, dict) and draft.get("agent") == agent else None


def _resting_card(session: dict[str, Any], agent: str) -> Any:
    """The two- or three-button shape, depending on a carried-forward override."""
    label = agent_label(agent)
    override = llm_selection.entry(session, agent)
    default_text = f"Use the default — {default_description(session)}"

    if override is None:
        return _card(
            dmc.Text(f"Which model should {label} use?", size="lg", fw=600, mb="xs"),
            dmc.Text(
                "Every agent runs on your default unless you give it one of its "
                "own. Sub-agents follow whichever you choose here.",
                c="dimmed",
                size="sm",
                mb="md",
            ),
            dmc.Group(
                [
                    dmc.Button(default_text, id="btn-agent-llm-default"),
                    dmc.Button(
                        f"Pick a model for {label}",
                        id="btn-agent-llm-pick",
                        variant="outline",
                    ),
                ]
            ),
        )

    kept = _describe(override.get("provider"), override.get("model"))
    return _card(
        dmc.Text(f"{label} used {kept} last time.", size="lg", fw=600, mb="xs"),
        dmc.Text(
            "Keeping it needs nothing re-entered — the key and model list came "
            "with it.",
            c="dimmed",
            size="sm",
            mb="md",
        ),
        dmc.Group(
            [
                dmc.Button(
                    f"Keep {override.get('model') or 'it'}",
                    id="btn-agent-llm-keep",
                ),
                dmc.Button(
                    default_text, id="btn-agent-llm-default", variant="outline"
                ),
                dmc.Button(
                    "Pick a different model",
                    id="btn-agent-llm-pick",
                    variant="subtle",
                ),
            ]
        ),
    )


def _pick_card(
    session: dict[str, Any],
    prefs: dict[str, Any],
    agent: str,
    draft: dict[str, Any],
) -> Any:
    """The expanded provider → key → model flow, in whichever half it is at.

    The model field only appears once a model-list fetch has succeeded, which is
    what makes a bad key impossible to get past: Continue is not rendered until
    Connect has returned models.
    """
    label = agent_label(agent)
    error = session.get("agent_llm_error")
    labels = providers.all_provider_labels()
    provider_key = draft.get("provider") or session.get("provider") or ""
    provider_label = providers.PROVIDERS.get(provider_key, {}).get(
        "label", labels[0]
    )
    available = draft.get("available_models") or []

    if not available:
        api_key = draft.get("api_key")
        if api_key is None:
            api_key = llm_selection.key_for_provider(session, prefs, provider_key)
        return _card(
            dmc.Text(f"Pick a model for {label}", size="lg", fw=600, mb="md"),
            *provider_key_fields(
                GATE_IDS,
                provider_label=provider_label,
                api_key=api_key,
                labels=labels,
            ),
            _error(error) if error else html.Div(),
            dmc.Group(
                [
                    dmc.Button(
                        "← Back",
                        id="btn-agent-llm-back",
                        variant="outline",
                        color="gray",
                    ),
                    dmc.Button("Connect", id="btn-agent-llm-connect"),
                ],
                mt="sm",
            ),
        )

    current = draft.get("model")
    value = current if current in available else available[0]
    return _card(
        dmc.Text(f"Pick a model for {label}", size="lg", fw=600, mb="md"),
        dmc.Alert(f"Connected to {provider_label}", mb="md"),
        model_field(GATE_IDS, available=available, value=value),
        _error(error) if error else html.Div(),
        dmc.Group(
            [
                dmc.Button(
                    "← Back",
                    id="btn-agent-llm-back",
                    variant="outline",
                    color="gray",
                ),
                dmc.Button(f"Use this for {label} →", id="btn-agent-llm-continue"),
            ],
            mt="sm",
        ),
    )


def gate_card(
    session: dict[str, Any], prefs: dict[str, Any] | None, agent: str
) -> Any:
    """The gate in whichever state it is in, resting or expanded."""
    draft = _draft_for(session, agent)
    if draft is None:
        return _resting_card(session, agent)
    return _pick_card(session, prefs or {}, agent, draft)


def model_chip(session: dict[str, Any], agent: str) -> Any:
    """The always-visible "Model: … · Change" affordance under the composer.

    Outlined rather than subtle: it sits in the footer row beside the status
    line, where a borderless button reads as one more piece of dimmed text
    instead of something to click. The light border is pinned in ``v3.css``
    (``#btn-agent-llm-chip``) so it stays pale against the dark ground rather
    than resolving to whatever Mantine picks for gray.

    Disabled mid-stream: the in-flight turn is already committed to a config,
    and letting the label change under it would misreport what produced the
    answer on screen. A change made here applies from the next turn, which
    needs no machinery — the dispatch resolves per turn.
    """
    override = llm_selection.entry(session, agent)
    if override is not None:
        text = f"Model: {override.get('model')}"
    else:
        text = f"Model: {(session.get('llm_config') or {}).get('model') or '—'}"
    return dmc.Button(
        f"{text} · Change",
        id="btn-agent-llm-chip",
        variant="outline",
        color="gray",
        size="compact-sm",
        c="dimmed",
        disabled=bool(session.get("_stream_id")),
    )
