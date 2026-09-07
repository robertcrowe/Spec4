from __future__ import annotations

import re
from typing import Any

from dash import dcc, html
import dash_mantine_components as dmc


# ---------------------------------------------------------------------------
# Primitive UI helpers
# ---------------------------------------------------------------------------

# The class the stripe rule in `v3.css` hangs on, attached to a `dmc.Progress`
# through Mantine's Styles API rather than to its root — the stripes live on
# the filled *section*, and the root is the unfilled track behind it.
#
# It is one constant because all three of the app's progress bars have the same
# problem and must have the same fix: Mantine stripes with white at 15%, which
# is invisible on the accent (see the rule in `v3.css` for the numbers). A
# per-call-site class would let one bar keep the unreadable default.
PROGRESS_CLASS_NAMES: dict[str, str] = {"section": "progress-stripe"}


def _card(*children: Any, **kwargs: Any) -> Any:
    """A bordered panel. ``p`` is overridable so the denser project-view frame
    can halve its padding without moving the setup wizard or the gate card."""
    padding = kwargs.pop("p", "md")
    return dmc.Paper(
        list(children), p=padding, radius="md", withBorder=True, **kwargs
    )


def _error(msg: str) -> Any:
    return dmc.Alert(msg, color="red", variant="light", mt="sm")


def _sep() -> Any:
    """The dimmed ``·`` between two fields of a one-line mono strip.

    Two such strips exist — the status bar's context line and the Artifact
    View's file header — and the design mock draws them with the same dot at
    the same weight and the same padding. One helper and one CSS rule
    (``.sb-sep``) rather than two of each, so a change to the separator cannot
    land on only one of the strips that use it.
    """
    return html.Span("·", className="sb-sep")


# ---------------------------------------------------------------------------
# Cost wording — the pieces every cost surface in the app is built from
# ---------------------------------------------------------------------------
#
# The frames live elsewhere: `_round_cost` draws the three-line strip that both
# the project view and the chat frame wear. What is here is the wording those
# lines are assembled from — the money format, the token readout, the sentence
# about calls that could not be priced — so that a reworded caveat lands on
# every surface at once rather than on whichever one somebody remembered.

# The standing caveat, at the density a one-line strip can carry. It names the
# price source the round's ``usage.json`` recorded, so a file written by an
# older Spec4 against a different map still describes itself rather than
# whatever this build happens to use.
PRICE_SOURCE_FALLBACK = "LiteLLM's price map"


def price_source_note(source: Any) -> str:
    """``Estimates from <source>. Your provider's billing is authoritative.``

    Two things, on one line: these figures are estimates, and the provider's
    bill is the real number. It is the third line of every cost strip in the
    app and lives here, beside the wording of the other two, so that a
    reworded caveat cannot land on only one of them.

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

    The sentence, without a frame around it. The cost strip gives it a line
    of its own with the calls named; anything with less room can parenthesise
    it onto the figure. Neither writes the wording twice.
    """
    excluded = _excluded_calls(block)
    if not excluded:
        return ""
    calls = int(block.get("calls") or 0)
    noun = "call" if calls == 1 else "calls"
    verb = "is" if excluded == 1 else "are"
    return f"{excluded} of {calls} {noun} could not be priced and {verb} excluded"


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


def _render_message(msg: dict[str, Any], speaker: str = "Agent") -> html.Div:
    """One transcript message, as a block rather than a bubble.

    A dimmed one-word label says who is speaking and the block itself carries
    no fill — the developer is reading a transcript, and two competing tinted
    rounded rectangles were chrome around the only thing on the screen that
    matters. The user's block keeps a neutral left rule, which is enough to
    find their own turns while scrolling back and is the one mark that does
    not read as a colour.

    Two nested divs on purpose. The outer wrapper is what the auto-scroll
    clientside callback measures: it finds the last ``.chat-bubble-user`` and
    scrolls that element's *parent* to the top of the viewport, so the class
    has to sit on the inner block with a wrapper above it. That class name is
    a JavaScript selector contract, not a description of a fill — see
    ``app.py`` and ``tests/test_chat_transcript_blocks.py``.
    """
    is_user = msg["role"] == "user"
    content = msg["content"] if is_user else _reformat_inline_lists(msg["content"])
    return html.Div(
        html.Div(
            [
                html.Div("You" if is_user else speaker, className="msg-label"),
                html.Div(
                    dcc.Markdown(content, style={"margin": 0}),
                    className="msg-body",
                ),
            ],
            className=(
                "chat-msg chat-bubble-user"
                if is_user
                else "chat-msg chat-bubble-assistant"
            ),
        ),
        className="msg-row",
    )
