"""The pipeline indicator that opens the chat frame.

Cleanup Phase 4f moved it out of :mod:`spec4.layouts._chat`: the strip above
the transcript is decided from artifact existence and agent preconditions,
which is a different question from what the row below the transcript offers
(:mod:`spec4.layouts._chat_actions`) or what the optional blocks between them
say (:mod:`spec4.layouts._chat_panels`).

Every name here is re-exported from ``spec4.layouts._chat``, so importing from
either module reaches the same object.
"""

from __future__ import annotations

from typing import Any

from dash import html
import dash_mantine_components as dmc

from spec4 import project_manager
from spec4.app_constants import (
    AGENT_KEYS,
    STATE_AGENTIFIER_COMPLETE,
    STATE_DEPLOYER_COMPLETE,
    STATE_PHASES_COMPLETE,
)
from spec4.layouts._agent_rows import AGENT_DISPLAY_NAMES
from spec4.layouts._shared import (
    STEP_ACTIVE,
    STEP_DONE,
    STEP_UNREACHABLE,
    STEP_UPCOMING,
    StepEntry,
    step_modifier_class,
    step_row,
)
from spec4.session import validate_agent_preconditions


# The pipeline indicator's four states, as the modifier classes `v3.css`
# draws. The active one takes the theme primary through its class exactly as
# the header nav's active link does (`.sb-nav-link--active`), so the accent is
# reached the one way D-LR2 allows and a re-themed accent moves both at once.
# Every scrap of button chrome is stripped in the stylesheet, for the same
# reason `.sb-dir` and the tree's lines strip theirs: these have to read as
# seven plain labels, not as seven buttons.
#
# The names are derived from the shared renderer (D-LR9) rather than written
# out, so the constant this module's tests assert against and the class the row
# actually receives cannot come apart.
_PILL_BASE = "pipeline-agent"
_PILL_ACTIVE = step_modifier_class(_PILL_BASE, STEP_ACTIVE)
_PILL_DONE = step_modifier_class(_PILL_BASE, STEP_DONE)
_PILL_UNREACHABLE = step_modifier_class(_PILL_BASE, STEP_UNREACHABLE)


def _completed_agents(session: dict[str, Any]) -> dict[str, bool]:
    """Which pipeline agents have already produced their artifact.

    Keyed by the same agent keys ``AGENT_KEYS`` names, so the pill bar can walk
    that tuple and ask this for each entry rather than carrying a second list
    of agents in its own order.

    Designer is the one agent whose completion is not a session flag: it writes
    `design/mock.html` and nothing else records that it ran, so the file's
    existence is the state.
    """
    working_dir = session.get("working_dir", "")
    mock = (
        project_manager.get_version_dir(
            working_dir, project_manager.active_version(working_dir, session)
        )
        / "design"
        / "mock.html"
        if working_dir
        else None
    )
    return {
        "code_scanner": session.get("code_review") is not None,
        "brainstormer": session.get("vision_statement") is not None,
        "agentifier": session.get("agentifier_state") == STATE_AGENTIFIER_COMPLETE,
        "designer": bool(mock and mock.exists()),
        "stack_advisor": session.get("stack_statement") is not None,
        "phaser": session.get("phaser_state") == STATE_PHASES_COMPLETE,
        "deployer": session.get("deployer_state") == STATE_DEPLOYER_COMPLETE,
    }


def agent_status_bar(session: dict[str, Any], *, active: str | None = None) -> html.Div:
    """The pipeline indicator: seven plain labels, in order, no connectors.

    The order is ``AGENT_KEYS`` itself rather than a list restated here — a
    stage added to the pipeline appears in this bar without anyone editing it,
    and the bar cannot drift from the rows on /agents that walk the same tuple.

    Three states, and the arrows between them are gone: the labels are already
    in pipeline order, so a connector said nothing the sequence did not. The
    active agent is a `<span>` because clicking it would navigate to where the
    developer already is; every other agent keeps the `agent-pill` pattern id
    it has always had, so routing is `on_agent_pill_click` untouched.

    What is decided *here* is only which agent is in which state — the pipeline
    order, whether each agent's artifact exists, and whether its preconditions
    hold. The marking itself is `_shared.step_row` (D-LR9), shared with the
    setup and Designer steppers, so this frame cannot be the only one whose
    active mark or dimming is right.

    ``active`` names the agent to mark when the frame is not the session's
    active agent's own. Designer's route is the one: entering it does not
    write ``active_agent`` (``_nav._enter_agent``), so the session still names
    whichever agent the developer came from, and the frame names Designer
    itself. Omitted, the session's ``active_agent`` is marked, as before.
    """
    if active is None:
        active = session.get("active_agent", "brainstormer")
    done = _completed_agents(session)
    entries: list[StepEntry] = []
    for key in AGENT_KEYS:
        label = AGENT_DISPLAY_NAMES[key]
        if key == active:
            entries.append(StepEntry(label, STEP_ACTIVE))
            continue
        blocked = validate_agent_preconditions(key, session)
        if blocked is not None:
            state = STEP_UNREACHABLE
        elif done.get(key):
            state = STEP_DONE
        else:
            state = STEP_UPCOMING
        entries.append(
            StepEntry(
                label,
                state,
                id={"type": "agent-pill", "agent": key},
                # Unchanged: the precondition message is the tooltip, and it is
                # the only explanation a dimmed label carries.
                tooltip=blocked,
            )
        )
    return html.Div(
        [
            # D-LR8: the pipeline is the whole bar. A `← Back` button stood
            # to its right and went to `/agents`; the status bar's Project
            # link is that same route, mounted in the app shell, so this was
            # the one control in the app whose destination already had a
            # permanent second door. The full reachability walk behind the
            # four Back removals is recorded at `chat_action_buttons` below.
            #
            # `mt` on the divider is what the retired Group's `mb` was doing:
            # `.pipeline` draws its own bottom rule, and without the gap the
            # two lines would sit 1px apart.
            step_row(entries, base_class=_PILL_BASE, row_class="pipeline"),
            dmc.Divider(mt="sm", mb="md"),
        ]
    )
