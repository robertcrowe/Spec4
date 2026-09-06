from __future__ import annotations

import re
from typing import Any

from dash import dcc, html
import dash_mantine_components as dmc

from spec4 import project_manager


# ---------------------------------------------------------------------------
# Primitive UI helpers
# ---------------------------------------------------------------------------


def _card(*children: Any, **kwargs: Any) -> Any:
    """A bordered panel. ``p`` is overridable so the denser project-view frame
    can halve its padding without moving the setup wizard or the gate card."""
    padding = kwargs.pop("p", "md")
    return dmc.Paper(
        list(children), p=padding, radius="md", withBorder=True, **kwargs
    )


def _error(msg: str) -> Any:
    return dmc.Alert(msg, color="red", variant="light", mt="sm")


# ---------------------------------------------------------------------------
# Cost summary card — shown at the end of every user-visible agent run
# ---------------------------------------------------------------------------

COST_DISCLAIMER = (
    "Estimates only. Costs are derived from provider-reported token counts and "
    "LiteLLM's community-maintained price map, which can lag provider price "
    "sheets and has no entry for some models. Your provider's billing is the "
    "authoritative figure."
)

# The same caveat at the density the project view's one-line strip can carry.
# It names the price source the round's ``usage.json`` recorded, so a file
# written by an older Spec4 against a different map still describes itself
# rather than whatever this build happens to use.
PRICE_SOURCE_FALLBACK = "LiteLLM's price map"


def price_source_note(source: Any) -> str:
    """``Estimates from <source>. Your provider's billing is authoritative.``

    The short form of :data:`COST_DISCLAIMER`, for a surface that has one line
    rather than a paragraph. Both say the same two things — these figures are
    estimates, and the provider's bill is the real number — and both live here
    so a reworded caveat cannot land on only one of them.

    Two sentences rather than the mock's one clause, because the source the
    file records carries its own parenthetical and a semicolon after it left
    three levels of punctuation in one breath.
    """
    name = (
        source
        if isinstance(source, str) and source.strip()
        else PRICE_SOURCE_FALLBACK
    )
    return f"Estimates from {name}. Your provider's billing is authoritative."


_COST_NOT_AVAILABLE = "not available"


def _fmt_usd(value: Any) -> str:
    """``$0.0123`` — four decimals, thousands separated; a marker for None.

    Four decimals because a single agent turn on a small model is fractions
    of a cent, and rounding it to ``$0.00`` would read as free.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"${value:,.4f}"
    return _COST_NOT_AVAILABLE


def _token_part(block: dict[str, Any]) -> str:
    """``Tokens: 5,080 in / 352 out`` — the provider-reported counts.

    Same shape as the per-turn readout in the action row. Cache reads are
    named when any call reported them. Flagged partial when some calls
    returned no usage, since those tokens are simply not in the sum.
    """
    text = (
        f"Tokens: {int(block.get('input_tokens') or 0):,} in / "
        f"{int(block.get('output_tokens') or 0):,} out"
    )
    cached = block.get("cached_input_tokens")
    if isinstance(cached, int) and not isinstance(cached, bool):
        text += f" ({cached:,} cached)"
    if int(block.get("calls_missing_usage") or 0):
        text += " (partial)"
    return text


def _excluded_calls(block: dict[str, Any]) -> int:
    """How many of the block's calls carry no price.

    Two ways a call ends up here and they are the same fact to a reader: the
    provider reported usage LiteLLM had no price map entry for, or it reported
    no usage at all. Either way its cost is not in the figure.
    """
    return int(block.get("calls_missing_cost") or 0) + int(
        block.get("calls_missing_usage") or 0
    )


def _cost_figure(block: dict[str, Any]) -> str:
    """The money, or the reason there isn't any: never a confident ``$0.0000``.

    A block whose calls could none of them be priced has an *unknown* cost,
    not a zero one, and says so. This is the one rule every cost surface in
    the app shares, which is why it lives here rather than at each call site.
    """
    cost = block.get("cost_usd")
    calls = int(block.get("calls") or 0)
    if cost is None and calls:
        return f"{_COST_NOT_AVAILABLE} (none of the {calls} calls could be priced)"
    return _fmt_usd(cost)


def _excluded_note(block: dict[str, Any]) -> str:
    """``2 of 19 calls could not be priced and are excluded``, or ``""``.

    The sentence, without a frame around it: the chat card parenthesises it
    onto its cost line and the project view's round cost gives it a line of
    its own with the calls named, but neither writes the wording twice.
    """
    excluded = _excluded_calls(block)
    if not excluded:
        return ""
    calls = int(block.get("calls") or 0)
    noun = "call" if calls == 1 else "calls"
    verb = "is" if excluded == 1 else "are"
    return f"{excluded} of {calls} {noun} could not be priced and {verb} excluded"


def _cost_line(label: str, block: dict[str, Any]) -> str:
    """``<label>: <cost> · Tokens: …`` with the pricing gaps spelled out.

    A call the provider reported usage for but LiteLLM could not price is
    excluded from the figure, so the figure is an undercount by exactly the
    calls counted in the note. When nothing could be priced there is no figure
    at all, and the line says so instead of showing ``$0.0000`` — and then the
    note is redundant, because the figure has already accounted for every
    call. The token counts follow either way: they are ground truth and do not
    depend on pricing.
    """
    text = f"{label}: {_cost_figure(block)}"
    note = "" if block.get("cost_usd") is None else _excluded_note(block)
    if note:
        text = f"{text} ({note})"
    return f"{text} · {_token_part(block)}"


def cost_summary_card(
    working_dir: Any, session: dict[str, Any] | None, agent_key: str, agent_label: str
) -> Any | None:
    """The estimated-cost card for a finished agent run, or None.

    Reads the round's ``usage.json`` at render time — the persist funnel (chat
    turns) and the Designer generation thread (mock draws) have both flushed
    their usage by the time a run is complete, and reading the file means a
    resumed session shows the same numbers. None when there is no project
    directory or no usage file yet, so the caller simply omits the card.

    Two figures: the agent's summed cost in this round (sub-agents rolled in,
    re-runs included — the same block ``spec4-usage`` prints) and the round's
    running total. Both are LiteLLM estimates; the disclaimer is part of the
    card, not optional.
    """
    if not working_dir:
        return None
    version = project_manager.active_version(working_dir, session)
    summary = project_manager.cost_summary(working_dir, version, agent_key)
    if summary is None:
        return None
    return dmc.Paper(
        [
            dmc.Text("Estimated cost", fw=600, mb="xs"),
            dmc.Text(_cost_line(f"{agent_label} run", summary["agent"])),
            dmc.Text(
                _cost_line(f"Running total for {summary['round']}", summary["total"])
            ),
            dmc.Text(COST_DISCLAIMER, size="sm", c="dimmed", mt="xs"),
        ],
        id="cost-summary-card",
        withBorder=True,
        p="md",
        radius="md",
        mb="md",
    )


# ---------------------------------------------------------------------------
# Chat message rendering
# ---------------------------------------------------------------------------


def _reformat_inline_lists(text: str) -> str:
    """Break inline numbered lists onto separate lines for proper Markdown rendering."""
    # Insert a newline before each "N. " that isn't already at the start of a line
    text = re.sub(r"(?<!\n)[ \t]+(\d+)\.[ \t]+", r"\n\1. ", text)
    # Ensure a blank line separates the preamble from the first list item
    text = re.sub(r"([^\n])\n(1\. )", r"\1\n\n\2", text)
    return text


def _render_message(msg: dict[str, Any]) -> html.Div:
    is_user = msg["role"] == "user"
    content = msg["content"] if is_user else _reformat_inline_lists(msg["content"])
    return html.Div(
        dmc.Paper(
            dcc.Markdown(content, style={"margin": 0}),
            p="sm",
            radius="md",
            className="chat-bubble-user" if is_user else "chat-bubble-assistant",
            style={"maxWidth": "85%"} if is_user else {"width": "100%"},
        ),
        style={
            "display": "flex",
            "justifyContent": "flex-end" if is_user else "flex-start",
            "marginBottom": "8px",
        },
    )
