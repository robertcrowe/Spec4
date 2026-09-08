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
uses (``layouts._setup``), including its Effort select, so the two cannot
drift.

Both resting shapes are one monospace line and one row of buttons. The line
(:func:`naming_line`) names the agent and the model it would run on if the
default were accepted; the row offers the two or three answers. It carries no
heading of its own, on either surface — the line names the agent, which is why
the Designer route no longer draws a separate title above it.
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


# What the naming line prints where a model would be, before /setup has run.
# The same em dash the status bar's empty slots use: on a fixed-width line a
# blank reads as a rendering bug, and "no model selected" is a sentence in a
# place that holds identifiers.
_NO_MODEL = "—"


def naming_line(
    session: dict[str, Any], prefs: dict[str, Any] | None, agent: str
) -> Any:
    """``Model for Phaser: claude-sonnet-5 · default`` — the panel's first line.

    The whole of the gate's resting copy, in one monospace line naming the
    agent and the model it would run on if the developer simply accepted the
    default. It replaces a heading, two sentences of explanation and a button
    label that repeated the model: the question the panel asks is *which
    model*, and stating the answer on offer asks it.

    The effort shows **always** here, ``· default`` included, and that is the
    one place in the app where it does. Everywhere else a model is printed the
    effort is a suffix that appears only when it is a real level
    (:func:`llm_selection.model_effort_display`); here the line is a full
    statement of the default rather than a label, and a line that dropped half
    of it when nothing was overridden would leave the developer unable to tell
    "no effort set" from "this panel does not mention effort".

    Both resting shapes show the *default*, never the carried-forward
    override — the override is named on the Keep button, which is the thing
    that would act on it.
    """
    _, model, effort = llm_selection.default_provider_model(session, prefs or {})
    return dmc.Text(
        f"Model for {agent_label(agent)}: {model or _NO_MODEL} · {effort}",
        className="mono",
    )


def is_open(session: dict[str, Any], agent: str) -> bool:
    """Whether the gate must be answered before this agent can run."""
    asked = session.get("agent_llm_asked") or {}
    return not asked.get(agent)


def _draft_for(session: dict[str, Any], agent: str) -> dict[str, Any] | None:
    draft = session.get("agent_llm_draft") or {}
    return draft if isinstance(draft, dict) and draft.get("agent") == agent else None


def _neutral(label: str, component_id: str) -> Any:
    """A choice that is not the recommended one.

    Outline in the neutral grey rather than the theme's own outline, which is
    the accent drawn as a border and would put a second emphasis on the row.
    ``gray`` is a semantic, not a colour decision — the accent is never named
    here (D-LR2), and `tests/test_visual_register.py` polices the difference.
    """
    return dmc.Button(
        label,
        id=component_id,
        variant="outline",
        color="gray",
        size="compact-sm",
    )


def _resting_card(
    session: dict[str, Any], prefs: dict[str, Any] | None, agent: str
) -> Any:
    """The two- or three-button shape, depending on a carried-forward override.

    Which buttons appear is unchanged and is still decided by one thing —
    whether this agent has an override to be offered back. What changed is the
    emphasis: **Use default** is the single filled action in both shapes, where
    Keep used to take it. Accepting the default is the answer that costs
    nothing and is right for six agents out of seven, and a row whose primary
    moved depending on what the previous project happened to leave behind was
    pointing at a different thing on each of the two screens it drew.
    """
    override = llm_selection.entry(session, agent)
    use_default = dmc.Button(
        "Use default", id="btn-agent-llm-default", size="compact-sm"
    )
    pick = _neutral("Pick a model", "btn-agent-llm-pick")

    if override is None:
        buttons = [use_default, pick]
    else:
        kept = llm_selection.model_effort_display(
            override.get("model"), llm_selection.effort_for(session, agent)
        )
        buttons = [
            _neutral(f"Keep {kept or 'it'}", "btn-agent-llm-keep"),
            use_default,
            pick,
        ]

    return _card(
        naming_line(session, prefs, agent),
        dmc.Group(buttons, gap="xs", mt="sm", className="btn-row"),
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
            naming_line(session, prefs, agent),
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
        naming_line(session, prefs, agent),
        # The connection is a fact, at the weight a fact gets — the same dimmed
        # line the setup wizard's model step carries, not a framed alert
        # (D-LR7).
        dmc.Text(f"Connected to {provider_label}", className="dim-line", mb="xs"),
        model_field(
            GATE_IDS,
            available=available,
            value=value,
            provider_key=provider_key,
            # The draft's own effort once the gate writes one; until then the
            # agent's current effort, through the same read path every other
            # consumer uses.
            effort=draft.get("effort") or llm_selection.effort_for(session, agent),
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
        return _resting_card(session, prefs, agent)
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
    # Read, not re-derived. The chip used to pick the override's model or the
    # session default's by hand, which was a second resolution path that could
    # disagree with the one the turn actually uses; `resolve` and `effort_for`
    # are the path, and the effort suffix comes off the same helper the status
    # bar, the retry panel and the agent rows use.
    config = llm_selection.resolve(session, agent) or {}
    name = (
        llm_selection.model_effort_display(
            config.get("model"), llm_selection.effort_for(session, agent)
        )
        or _NO_MODEL
    )
    # The model name is an identifier — `claude-sonnet-5`, `gpt-5-mini` — so it
    # is monospace, like every other identifier the app prints, and so is the
    # effort that qualifies it. The words around it are prose and stay in the
    # UI face; the class goes on the name alone rather than on the button, and
    # carries no colour of its own.
    return dmc.Button(
        ["Model: ", html.Span(name, className="mono"), " · Change"],
        id="btn-agent-llm-chip",
        variant="outline",
        color="gray",
        size="compact-sm",
        c="dimmed",
        disabled=bool(session.get("_stream_id")),
    )
