"""The agent rows — the seven pipeline agents as one dense table.

Five columns per agent: what it is called, the artifact it produces, the model
it last ran on this round, the tokens that run cost, and the one thing you can
do with it next. No step numbers, no descriptions, no emoji — the row *is* the
description, and the button is the instruction.

Three rules hold this module together.

*The pipeline order is not restated.* ``_AGENT_ROWS`` is built by walking
``AGENT_KEYS``, and each row's produced artifact is the first entry in the
round tree's reviewed lane table (``ARTIFACT_GROUPS``). Adding a pipeline stage
therefore adds a row, and a file that moves between agents moves in both the
tree and the table at once, because neither reads a second copy of the mapping.

*The action is read, never re-derived.* ``project_manager.agent_button_state``
is the pipeline's one readiness authority. This module asks it for a state and
then only chooses a label and a variant; it does not look at an artifact's
mtime, and there is no second state model here to drift from the first. The
buttons keep the existing ``agent-pill`` pattern id, so activating one routes
through ``on_agent_pill_click`` exactly as the previous cards did (D-AR2).

*A missing usage entry is a normal state, not an error.* An agent that has not
run this round has no block in ``usage.json``, and the row shows blank model
and token cells for it — never a zero, which would read as "ran and cost
nothing", and never an exception, which would take the whole project view down
with it (D-AR3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from dash import html
import dash_mantine_components as dmc

from spec4 import project_manager
from spec4.app_constants import AGENT_KEYS
from spec4.layouts._round_tree import ARTIFACT_GROUPS

__all__ = [
    "ACTION_BUTTON_PROPS",
    "ACTION_LABELS",
    "AGENT_DISPLAY_NAMES",
    "AGENT_PRODUCES",
    "AgentRow",
    "AgentRowSpec",
    "RowUsage",
    "USAGE_BLANK",
    "_AGENT_ROWS",
    "_action_class",
    "_agent_action_button",
    "_agent_rows",
    "agent_row_id",
    "agent_rows",
    "round_usage",
]


# ---------------------------------------------------------------------------
# The table's fixed columns
# ---------------------------------------------------------------------------

# The display name for each pipeline key. The keys are snake_case because they
# index artifacts and session state; these are what the developer reads, and
# they are the names the rest of the app already uses in prose.
AGENT_DISPLAY_NAMES: dict[str, str] = {
    "code_scanner": "CodeScanner",
    "brainstormer": "Brainstormer",
    "agentifier": "Agentifier",
    "designer": "Designer",
    "stack_advisor": "StackAdvisor",
    "phaser": "Phaser",
    "deployer": "Deployer",
}

# What each agent produces, taken from the round tree's reviewed lane table
# rather than restated: the first artifact an agent writes is its headline
# output, and it is the same file the tree draws a line for. Deriving it here
# is what stops the two disagreeing about, say, whether Designer produces the
# mock or the manifest.
AGENT_PRODUCES: dict[str, str] = {
    agent: artifacts[0].path
    for agent, artifacts in ARTIFACT_GROUPS
    if agent is not None and artifacts
}


class AgentRowSpec(NamedTuple):
    """One row's fixed data: what does not change between renders."""

    key: str
    name: str
    produces: str


# The seven rows, in pipeline order, derived from ``AGENT_KEYS`` so the order
# here cannot drift from the pipeline's one definition.
_AGENT_ROWS: tuple[AgentRowSpec, ...] = tuple(
    AgentRowSpec(key, AGENT_DISPLAY_NAMES[key], AGENT_PRODUCES[key])
    for key in AGENT_KEYS
)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

ACTION_LABELS: dict[str, str] = {
    project_manager.AGENT_BTN_START: "Start",
    project_manager.AGENT_BTN_MODIFY: "Modify",
    project_manager.AGENT_BTN_NEEDS_UPDATE: "Needs Update",
    project_manager.AGENT_BTN_NOT_READY: "Not Ready",
    project_manager.AGENT_BTN_REQUIRED: "Required",
}

# D-AR1: the five action states and the button each one draws, exactly as the
# design manifest specifies them for `agent-rows` — Start filled, Required
# filled (the same button as Start), Modify a neutral outline with green text,
# Needs Update a warn outline, Not Ready a disabled outline. It is one
# constant, in one place, because five states written inline at the point of
# render is five chances to drift from the manifest.
#
# Per D-LR2 no entry names its accent. The three states the manifest draws in
# green (Start, Required, Modify) simply pass no `color` and take the theme
# primary; Modify's neutral border is CSS on `.agent-row-action--modify`, not a
# colour prop. Only Needs Update carries a colour, because warn is not the
# accent, and Not Ready carries none at all — Mantine greys a disabled button
# from `disabled` alone.
ACTION_BUTTON_PROPS: dict[str, dict[str, Any]] = {
    project_manager.AGENT_BTN_START: {"variant": "filled"},
    project_manager.AGENT_BTN_REQUIRED: {"variant": "filled"},
    project_manager.AGENT_BTN_MODIFY: {"variant": "outline"},
    project_manager.AGENT_BTN_NEEDS_UPDATE: {"variant": "outline", "color": "yellow"},
    project_manager.AGENT_BTN_NOT_READY: {"variant": "outline"},
}

# The one state that cannot be activated. Named rather than tested inline so
# the row's dimming and the button's `disabled` cannot disagree about it.
ACTION_DISABLED = project_manager.AGENT_BTN_NOT_READY

# The class each action carries, on top of the shared one. Two states need a
# modifier because Mantine's variant does not draw them the way the manifest
# does: Modify wants the accent on the text and a neutral border (an outline
# button colours both), and Needs Update wants warn at the mock's weight rather
# than the near-white shade Mantine picks for a dark scheme. Neither modifier
# writes a raw colour value: both reference the theme's own variables, so a
# re-themed accent still lands on these buttons. See the rules in `v3.css`.
_ACTION_CLASSES: dict[str, str] = {
    project_manager.AGENT_BTN_MODIFY: "agent-row-action--modify",
    project_manager.AGENT_BTN_NEEDS_UPDATE: "agent-row-action--needs-update",
}


def _action_class(state: str) -> str:
    """The button's className: the shared class, plus a modifier when the
    state needs one."""
    modifier = _ACTION_CLASSES.get(state)
    return f"agent-row-action {modifier}" if modifier else "agent-row-action"


# ---------------------------------------------------------------------------
# Usage, from disk
# ---------------------------------------------------------------------------


class RowUsage(NamedTuple):
    """One agent's usage this round, already formatted for its cells.

    Every field is a string and every field is empty for an agent that has not
    run, so a row's shape never depends on whether the numbers exist.
    """

    model: str
    tokens_in: str
    tokens_out: str

    @property
    def tokens(self) -> str:
        """The tokens cell: ``"41,206 in / 3,118 out"``, or blank."""
        if not self.tokens_in and not self.tokens_out:
            return ""
        return f"{self.tokens_in} in / {self.tokens_out} out"


# What a not-yet-run agent renders. D-AR3: blank, in every field.
USAGE_BLANK = RowUsage("", "", "")


def _tokens(value: Any) -> str:
    """A token count with thousands separators; blank when not a real count."""
    if isinstance(value, bool) or not isinstance(value, int):
        return ""
    return f"{value:,}"


def _last_model(entry: dict[str, Any]) -> str:
    """The model this agent last ran on, from its ``models`` list.

    ``summarize_usage`` appends each distinct (model, provider) pair in
    first-seen order, so a developer who re-ran an agent on a second model this
    round has two entries and the *last* one is the run the row is reporting.
    """
    models = entry.get("models")
    if not isinstance(models, list):
        return ""
    for pair in reversed(models):
        if isinstance(pair, dict) and pair.get("model"):
            return str(pair["model"])
    return ""


def _row_usage(entry: Any) -> RowUsage:
    """One agent's block from ``usage.json``, as cells.

    The defensive accessor D-AR3 asks for: anything that is not a usage block
    with at least one recorded call reads as not-yet-run. A malformed file, an
    absent agent and an agent that has genuinely not run are the same row,
    which is the honest answer in all three cases — nothing has been spent.
    """
    if not isinstance(entry, dict):
        return USAGE_BLANK
    calls = entry.get("calls")
    if isinstance(calls, bool) or not isinstance(calls, int) or calls < 1:
        return USAGE_BLANK
    return RowUsage(
        _last_model(entry),
        _tokens(entry.get("input_tokens")),
        _tokens(entry.get("output_tokens")),
    )


def round_usage(
    working_dir: str | Path | None, round_number: int | None
) -> dict[str, RowUsage]:
    """Per-agent usage for the round, keyed by pipeline key.

    Read from disk on every call and never memoised (D-LR4): an agent that
    finishes mid-session changes these numbers, and a cached table would keep
    showing the previous run's. ``usage.json`` is read once per render rather
    than once per row.

    Every one of the seven keys is present in the result, so a caller never has
    to guard the lookup — an agent with no entry maps to ``USAGE_BLANK``.
    """
    data = (
        project_manager.load_usage(working_dir, round_number)
        if working_dir and round_number is not None
        else None
    )
    agents = data.get("agents") if isinstance(data, dict) else None
    if not isinstance(agents, dict):
        agents = {}
    return {key: _row_usage(agents.get(key)) for key in AGENT_KEYS}


# ---------------------------------------------------------------------------
# The rows
# ---------------------------------------------------------------------------


class AgentRow(NamedTuple):
    """A rendered row: the design manifest's ``AgentRow`` entity.

    ``action`` is the readiness state ``agent_button_state`` returned, not a
    label — the label is chosen at render time from ``ACTION_LABELS``, so a
    test can compare a row against the state authority directly.
    """

    key: str
    agent: str
    produces: str
    model: str
    tokens: str
    action: str
    disabled: bool


def agent_rows(
    working_dir: str | Path | None,
    round_number: int | None,
    session: dict[str, Any] | None = None,
) -> list[AgentRow]:
    """The seven rows for this round, in pipeline order.

    Every agent yields exactly one row on every call, whether or not it has
    run: the table is the pipeline, so a row that vanished would be a stage the
    developer could no longer see.
    """
    usage = round_usage(working_dir, round_number)
    rows: list[AgentRow] = []
    for spec in _AGENT_ROWS:
        state = project_manager.agent_button_state(working_dir, spec.key, session)
        cells = usage[spec.key]
        rows.append(
            AgentRow(
                key=spec.key,
                agent=spec.name,
                produces=spec.produces,
                model=cells.model,
                tokens=cells.tokens,
                action=state,
                disabled=state == ACTION_DISABLED,
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def agent_row_id(key: str) -> str:
    """The row's component id, derived from its pipeline key."""
    return f"agent-row-{key}"


def _agent_action_button(agent_key: str, state: str) -> Any:
    """One row's action button.

    The id is the existing ``agent-pill`` pattern id, unchanged: the routing
    this button needs already exists in ``on_agent_pill_click``, and reusing
    the id is what makes "activating a row's action navigates to that agent"
    true by construction rather than by a second implementation (D-AR2).
    """
    return dmc.Button(
        ACTION_LABELS[state],
        id={"type": "agent-pill", "agent": agent_key},
        n_clicks=0,
        disabled=state == ACTION_DISABLED,
        size="compact-xs",
        className=_action_class(state),
        **ACTION_BUTTON_PROPS[state],
    )


def _row_children(row: AgentRow) -> html.Tr:
    """One ``<tr>``: the five cells the mock draws, in its order.

    The model and token cells are always rendered, even when blank, so the
    table keeps its column widths as agents finish during a session.
    """
    return html.Tr(
        [
            html.Td(row.agent, className="agent"),
            html.Td(row.produces, className="produces mono"),
            html.Td(row.model, className="model mono"),
            html.Td(row.tokens, className="tokens mono"),
            html.Td(
                _agent_action_button(row.key, row.action),
                className="action",
            ),
        ],
        id=agent_row_id(row.key),
        className="is-disabled" if row.disabled else "",
    )


def _head() -> html.Thead:
    """The column heads, in the mock's order. The action column is unlabelled
    — the buttons name themselves, and a heading over them would only repeat
    whichever one happened to be first."""
    return html.Thead(
        html.Tr(
            [
                html.Th("Agent", scope="col", className="agent"),
                html.Th("Produces", scope="col", className="produces"),
                html.Th("Last model", scope="col", className="model"),
                html.Th("Tokens this round", scope="col", className="tokens"),
                html.Th("", scope="col", className="action"),
            ]
        )
    )


def _agent_rows(
    working_dir: str | Path | None,
    round_number: int | None,
    session: dict[str, Any] | None = None,
) -> html.Section:
    """The agent table, rendered for a round.

    It sits directly beneath the round tree on the project view: the tree says
    what the round has produced, and this says what to do about it.
    """
    return html.Section(
        html.Table(
            [
                _head(),
                html.Tbody(
                    [
                        _row_children(row)
                        for row in agent_rows(working_dir, round_number, session)
                    ],
                    id="agent-rows-body",
                ),
            ],
            className="agents-table",
        ),
        id="agent-rows",
        className="agent-rows",
        # Dash passes unknown props straight through to the DOM; its stubs only
        # know the documented ones, hence the ignore for a plain accessibility
        # attribute the design mock also carries.
        **{"aria-label": "Agents"},  # type: ignore[arg-type]
    )
