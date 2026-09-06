"""The round cost — what this round has spent so far, in three lines.

It closes the project view: the tree says what the round has produced, the
agent table says what to do next, and this says what it has cost. One strip,
monospace, the same figures ``spec4-usage`` prints.

Three rules hold this module together.

*The total is the file's total.* ``project_manager.round_cost`` hands back the
``totals`` block ``save_usage`` recomputes from the full call history on every
write. Nothing here adds a column of numbers up, so this strip and the chat
frame's cost card cannot disagree about what the round cost.

*The wording is the cost card's wording.* ``_shared`` owns the money format,
the token readout, and the sentence about calls that could not be priced;
this module owns only the frame the project view needs — the mock's three
dense lines rather than the card's bordered panel — and the naming of the
unpriced calls, which the card has no room for (D-RC2).

*An unknown cost is never a zero one.* A round with nothing recorded and a
round whose every call went unpriced are two different sentences here, and
neither of them is ``$0.0000`` (D-RC1).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from dash import html

from spec4 import project_manager
from spec4.layouts._agent_rows import AGENT_DISPLAY_NAMES
from spec4.layouts._shared import (
    _cost_figure,
    _excluded_note,
    _token_part,
    price_source_note,
)

__all__ = [
    "COST_LABEL",
    "NO_CALLS",
    "RoundCost",
    "_round_cost",
    "round_cost_lines",
]

# The estimate label, on every one of the three states. It is a prefix rather
# than a suffix because it is the one word that must survive a line the
# developer only glances at: whatever follows the colon — a figure, "unknown",
# "nothing yet" — has already been framed as an estimate by the time they
# read it.
COST_LABEL = "Estimated cost"

# D-RC1: the no-activity sentence. It exists so that "this round has not spent
# anything" and "this round spent something we cannot price" are two different
# strings on screen. Conflating them is the failure this surface is for: an
# all-unpriced round rendered as $0.0000 tells the developer they spent
# nothing, which is the one thing that is certainly false. The unknown-cost
# wording is `_shared._cost_figure`'s, shared with the chat card.
NO_CALLS = "no calls recorded this round"


class RoundCost(NamedTuple):
    """The three lines the strip renders, as text.

    Text rather than components because these are also what the callback
    writes on every render, and because the assertion a test wants to make
    about a cost figure is an assertion about a string.
    """

    figure: str
    unpriced: str
    note: str


def _unpriced_name(group: dict[str, Any]) -> str:
    """``StackAdvisor (gpt-5-mini)`` — one unpriced group, named.

    The agent's display name, not its pipeline key, so the name here is the
    name the agent table shows a row for. A record with no model recorded —
    a call that failed before the provider answered — is named by its agent
    alone rather than by an empty pair of brackets.
    """
    key = str(group.get("agent") or "")
    label = AGENT_DISPLAY_NAMES.get(key, key)
    model = group.get("model")
    return f"{label} ({model})" if model else label


def _figure_line(record: dict[str, Any]) -> str:
    """Line one: the estimate, and the tokens behind it.

    Two paths, and the split is D-RC1. A round with no calls has no cost *and*
    no tokens, so it says so and stops — a "Tokens: 0 in / 0 out" tail would
    be three zeroes on a line whose whole message is that there is nothing to
    report yet. Every other round shows a figure — money, or the reason there
    isn't a figure — followed by the token counts, which are the provider's
    ground truth and hold whether or not anything could be priced.
    """
    total = record["total"]
    label = f"{COST_LABEL}, {record['round']}"
    if not int(total.get("calls") or 0):
        return f"{label}: {NO_CALLS}"
    return f"{label}: {_cost_figure(total)} · {_token_part(total)}"


def _unpriced_line(record: dict[str, Any]) -> str:
    """Line two: which calls are missing from the figure above, by name.

    The count and its phrasing come from ``_shared``, so this line and the
    chat card's parenthetical are the same sentence; the names are the part
    only this surface has room for. When every call was priced the line still
    renders, saying so: "all 19 calls priced" is the reassurance that makes
    the figure above readable as a whole number rather than a partial one.
    """
    total = record["total"]
    calls = int(total.get("calls") or 0)
    if not calls:
        return ""
    note = _excluded_note(total)
    if not note:
        return f"all {calls} {'call' if calls == 1 else 'calls'} priced"
    names = ", ".join(_unpriced_name(g) for g in record["unpriced"])
    return f"{note}: {names}" if names else note


def round_cost_lines(
    working_dir: str | Path | None, round_number: int | None
) -> RoundCost:
    """The round's three cost lines, read from disk.

    Read on every call and never memoised (D-LR4), the same rule the tree and
    the agent table follow: an agent that finishes mid-session changes these
    numbers, and a cached total would keep showing the previous run's. There
    is no project directory before one is chosen, and that is the same empty
    record as a round that has not spent anything.
    """
    record = project_manager.round_cost(working_dir or None, round_number)
    return RoundCost(
        _figure_line(record),
        _unpriced_line(record),
        price_source_note(record["cost_source"]),
    )


def _round_cost(
    working_dir: str | Path | None, round_number: int | None
) -> html.Section:
    """The round-cost strip, rendered for a round.

    The first paint computes its own lines so the view is never briefly blank;
    the callback in ``spec4.callbacks`` recomputes them from disk on every
    render after that. All three lines are always mounted — an empty line two
    keeps its element — so the strip's height does not change as a round goes
    from all-priced to partly unpriced, and so the callback always has all
    three targets to write into.
    """
    lines = round_cost_lines(working_dir, round_number)
    return html.Section(
        [
            html.Div(lines.figure, id="round-cost-line", className="cost-line mono"),
            html.Div(
                lines.unpriced, id="round-cost-unpriced", className="cost-line mono"
            ),
            html.Div(lines.note, id="round-cost-note", className="cost-note"),
        ],
        id="round-cost",
        className="round-cost",
        # Dash passes unknown props straight through to the DOM; its stubs only
        # know the documented ones, hence the ignore for a plain accessibility
        # attribute the design mock also carries.
        **{"aria-label": "Round cost"},  # type: ignore[arg-type]
    )
