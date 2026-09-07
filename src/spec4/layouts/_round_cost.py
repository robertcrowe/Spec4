"""The cost strip — what a round, or the run that just ended, has spent.

Three dense lines, monospace, the same figures ``spec4-usage`` prints. Two
surfaces draw it: the project view closes with the *round's* strip (the tree
says what the round has produced, the agent table says what to do next, and
this says what it has cost), and the chat frame puts *this run's* strip under
the last message of a completed run.

They are one renderer, not two that agree. That is the mitigation the chat
frame's "the completion cost strip fails to match the round-cost presentation"
failure mode asks for: :func:`cost_strip_lines` is the only place in the app
that turns a usage block into cost prose, so the two surfaces cannot word the
same fact differently. What varies between them is one string — the *scope*
the label names, ``v3`` or ``this run`` — and the figures handed in.

Four rules hold this module together.

*Neither surface adds anything up.* ``project_manager.round_cost`` and
``project_manager.cost_summary`` hand back blocks that ``save_usage``
recomputed from the full call history on every write. Nothing here sums a
column of numbers, so the project view and the chat frame cannot disagree
about what a round cost.

*The wording is ``_shared``'s wording.* ``_shared`` owns the money format, the
token readout, and the sentence about calls that could not be priced; this
module owns the frame — the mock's three dense lines — and the naming of the
unpriced calls, which the one-line forms have no room for (D-RC2).

*An unknown cost is never a zero one.* A scope with nothing recorded and a
scope whose every call went unpriced are two different sentences here, and
neither of them is ``$0.0000`` (D-RC1).

*The two strips carry different component ids.* Same lines, same class, but
``on_round_cost`` writes into the project view's three line ids, and a chat
frame that answered to them would be asking Dash to fill a strip on a screen
that callback knows nothing about. See :data:`ROUND_COST_IDS`.
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
    "ROUND_COST_IDS",
    "RUN_COST_IDS",
    "RUN_SCOPE",
    "CostFigures",
    "CostStripIds",
    "RoundCost",
    "_round_cost",
    "cost_strip_lines",
    "round_cost_lines",
    "run_cost_lines",
    "run_cost_strip",
]

# The estimate label, on every one of the three states. It is a prefix rather
# than a suffix because it is the one word that must survive a line the
# developer only glances at: whatever follows the colon — a figure, "unknown",
# "nothing yet" — has already been framed as an estimate by the time they
# read it.
COST_LABEL = "Estimated cost"

# What the chat frame's strip calls its scope. The round's strip names the
# round (``v3``); a run has no name of its own and does not need one — it is
# the run whose last message the strip is sitting under.
RUN_SCOPE = "this run"

# D-RC1: the no-activity sentence. It exists so that "this scope has not spent
# anything" and "this scope spent something we cannot price" are two different
# strings on screen. Conflating them is the failure this surface is for: an
# all-unpriced round rendered as $0.0000 tells the developer they spent
# nothing, which is the one thing that is certainly false. The unknown-cost
# wording is `_shared._cost_figure`'s, shared with every other cost surface.
#
# It does not name the scope, because the label already has: "Estimated cost,
# v3: no calls recorded" and "Estimated cost, this run: no calls recorded" are
# both sentences, and a sentence that said "this round" would be wrong on one
# of the two strips that render it.
NO_CALLS = "no calls recorded"


class RoundCost(NamedTuple):
    """The three lines the strip renders, as text.

    Text rather than components because these are also what the callback
    writes on every render, and because the assertion a test wants to make
    about a cost figure is an assertion about a string.
    """

    figure: str
    unpriced: str
    note: str


class CostFigures(NamedTuple):
    """One scope's cost, as :func:`cost_strip_lines` needs it.

    The seam between "where the numbers came from" and "how they are worded".
    Both callers read a different function of ``project_manager`` — the round
    reads ``round_cost``, the run reads ``cost_summary`` — and both arrive
    here in the same shape, which is what lets one renderer serve them.

    ``scope`` is the phrase after the estimate label: ``"v3"`` or
    :data:`RUN_SCOPE`. ``total`` is the block the figure and the token counts
    are read off. ``unpriced`` are the groups ``project_manager`` named for
    exactly that block — the round's for a round, the agent's own for a run —
    so line two always explains line one rather than some wider total.
    """

    scope: str
    total: dict[str, Any]
    unpriced: list[dict[str, Any]]
    cost_source: Any


class CostStripIds(NamedTuple):
    """The four component ids one rendered strip carries.

    A parameter rather than a constant for the same reason the round tree's
    ``TreeIds`` is one: two screens draw this strip, and Dash keys a callback
    to a component id. ``on_round_cost`` recomputes the *project view's* three
    lines from the active round; a chat frame that reused those ids would put
    them on a screen that callback's Input (``round-cost``) is not on, which
    is precisely the half-rendered callback ``tests/test_callback_co_presence``
    exists to catch.
    """

    root: str
    line: str
    unpriced: str
    note: str


# The project view's strip. ``on_round_cost`` writes into the three lines.
ROUND_COST_IDS = CostStripIds(
    "round-cost", "round-cost-line", "round-cost-unpriced", "round-cost-note"
)

# The chat frame's (and the Designer preview's) strip. The root keeps the id
# the retired ``_shared.cost_summary_card`` carried — ``tests/test_cost_summary``
# asserts the strip's position between the transcript and the action row by
# that id, and the contract is worth more than the tidier name. No callback
# writes these lines: the frame is rebuilt from the session on every render,
# so the first paint is the only paint.
RUN_COST_IDS = CostStripIds(
    "cost-summary-card", "run-cost-line", "run-cost-unpriced", "run-cost-note"
)


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


def _figure_line(figures: CostFigures) -> str:
    """Line one: the estimate, and the tokens behind it.

    Two paths, and the split is D-RC1. A scope with no calls has no cost *and*
    no tokens, so it says so and stops — a "Tokens: 0 in / 0 out" tail would
    be three zeroes on a line whose whole message is that there is nothing to
    report yet. Every other scope shows a figure — money, or the reason there
    isn't a figure — followed by the token counts, which are the provider's
    ground truth and hold whether or not anything could be priced.
    """
    total = figures.total
    label = f"{COST_LABEL}, {figures.scope}"
    if not int(total.get("calls") or 0):
        return f"{label}: {NO_CALLS}"
    return f"{label}: {_cost_figure(total)} · {_token_part(total)}"


def _unpriced_line(figures: CostFigures) -> str:
    """Line two: which calls are missing from the figure above, by name.

    The count and its phrasing come from ``_shared``, so this line and the
    one-line forms elsewhere are the same sentence; the names are the part
    only this strip has room for. When every call was priced the line still
    renders, saying so: "all 19 calls priced" is the reassurance that makes
    the figure above readable as a whole number rather than a partial one.
    """
    total = figures.total
    calls = int(total.get("calls") or 0)
    if not calls:
        return ""
    note = _excluded_note(total)
    if not note:
        return f"all {calls} {'call' if calls == 1 else 'calls'} priced"
    names = ", ".join(_unpriced_name(g) for g in figures.unpriced)
    return f"{note}: {names}" if names else note


def cost_strip_lines(figures: CostFigures) -> RoundCost:
    """The three lines, worded. The app's one cost presentation.

    Every cost strip in the app is this function's output. The project view
    and the chat frame differ only in the :class:`CostFigures` they hand in,
    so identical usage produces identical prose on both — the estimate label,
    the named unpriced calls, and the refusal to print ``$0.0000`` for an
    unknown cost included.
    """
    return RoundCost(
        _figure_line(figures),
        _unpriced_line(figures),
        price_source_note(figures.cost_source),
    )


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
    return cost_strip_lines(
        CostFigures(
            str(record["round"]),
            record["total"],
            record["unpriced"],
            record["cost_source"],
        )
    )


def run_cost_lines(
    working_dir: str | Path | None,
    session: dict[str, Any] | None,
    agent_key: str,
) -> RoundCost | None:
    """The finished run's three cost lines, or ``None``.

    ``None`` in exactly two cases, and both mean "there is nothing to show
    yet" rather than "something is wrong": no project directory, and no
    ``usage.json`` written for the round. The caller omits the strip for
    either, which is what the round's own strip cannot do — the project view
    always has a round to report on, whereas a run that has recorded nothing
    has not started.

    The figures are the *agent's* block, not the round's total. That is the
    mock's run strip: the developer has just watched this agent finish and is
    deciding whether to continue, and the round's running total is one screen
    away on the project view, drawn by the same renderer.
    """
    if not working_dir:
        return None
    version = project_manager.active_version(working_dir, session)
    summary = project_manager.cost_summary(working_dir, version, agent_key)
    if summary is None:
        return None
    return cost_strip_lines(
        CostFigures(
            RUN_SCOPE,
            summary["agent"],
            summary["unpriced"],
            summary["cost_source"],
        )
    )


def _cost_strip(lines: RoundCost, ids: CostStripIds, label: str) -> html.Section:
    """The three lines, mounted.

    All three are always present — an empty line two keeps its element — so
    the strip's height does not change as a scope goes from all-priced to
    partly unpriced, and so a callback writing into it always has all three
    targets.
    """
    return html.Section(
        [
            html.Div(lines.figure, id=ids.line, className="cost-line mono"),
            html.Div(lines.unpriced, id=ids.unpriced, className="cost-line mono"),
            html.Div(lines.note, id=ids.note, className="cost-note"),
        ],
        id=ids.root,
        className="cost-strip",
        # Dash passes unknown props straight through to the DOM; its stubs only
        # know the documented ones, hence the ignore for a plain accessibility
        # attribute the design mock also carries.
        **{"aria-label": label},  # type: ignore[arg-type]
    )


def _round_cost(
    working_dir: str | Path | None, round_number: int | None
) -> html.Section:
    """The round-cost strip, closing the project view.

    The first paint computes its own lines so the view is never briefly blank;
    ``on_round_cost`` recomputes them from disk on every render after that.
    """
    return _cost_strip(
        round_cost_lines(working_dir, round_number), ROUND_COST_IDS, "Round cost"
    )


def run_cost_strip(
    working_dir: str | Path | None,
    session: dict[str, Any] | None,
    agent_key: str,
) -> html.Section | None:
    """The completed run's cost strip, or ``None`` when there is none to draw.

    Reads the round's ``usage.json`` at render time — the persist funnel (chat
    turns) and the Designer generation thread (mock draws) have both flushed
    their usage by the time a run is complete, and reading the file means a
    resumed session shows the same numbers.
    """
    lines = run_cost_lines(working_dir, session, agent_key)
    if lines is None:
        return None
    return _cost_strip(lines, RUN_COST_IDS, "Run cost")
