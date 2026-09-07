"""The chat frame's action row has exactly one emphasis, and it is the continue.

The rule comes from the design manifest's Action Row entry: the continue button
is the only filled-green button in its row, Fast Forward, Download and the
'Continue to <skip>' button are neutral outlines, and Re-scan Project carries
the warn tone. It is a rule about the row as a whole rather than about any one
button, which is why it is asserted by walking every row the frame can draw
rather than by checking the six continues one at a time.

*Neutral is the absence of a colour, not a grey.* Per D-AR1 a bare
``variant="outline"`` takes the theme primary and, at the shade Mantine picks
for a dark scheme, washes out to near-white — the mock's ``.btn-outline``. So
the emphasised button is the one that passes *no* ``variant`` at all, and the
neutral ones are the outlines beside it. Nothing in this row names the accent
(D-LR2); the one colour here is the warn yellow, which is a semantic.

*The filled button is last.* Asserted structurally rather than against a list
of the six continue ids: the mock draws the continue at the end of the row, and
a list of ids would pass against a row that had put the filled one in the
middle.
"""

from __future__ import annotations

import pathlib
from typing import Any

import dash_mantine_components as dmc

from spec4.app_constants import (
    STATE_AGENTIFIER_COMPLETE,
    STATE_DEPLOYER_COMPLETE,
    STATE_REVIEW_COMPLETE,
    STATE_STACK_COMPLETE,
    STATE_VISION_COMPLETE,
)
from spec4.layouts._chat import _chat_action_buttons

_STYLESHEET = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src"
    / "spec4"
    / "assets"
    / "v3.css"
)

# The one button in the row that is neither filled nor an outline. It is the
# "(i)" beside Fast Forward — an explanation of the control next to it, not an
# action of its own — so it is drawn subtle and named here rather than left to
# weaken the rule into "most buttons are outlines".
_INFO_AFFORDANCE = "btn-ff-info"

# The warn tone's one wearer in this row, and the pairing it must wear: the
# same `color` the agent rows' Needs Update uses, plus the class that carries
# the mock's weight (Mantine's own yellow outline is as pale as the neutrals).
_WARN_BUTTON = "btn-rescan-project"
_WARN_CLASS = "btn-warn"


# Every action row the chat frame can draw, as (name, session). Both halves of
# each agent — the run in flight and the run complete — because the rule is
# about rows, and a mid-run row is a row.
def _rows() -> list[tuple[str, dict[str, Any]]]:
    return [
        (
            "code_scanner complete",
            {
                "active_agent": "code_scanner",
                "code_scanner_state": STATE_REVIEW_COMPLETE,
                "messages": [{"role": "assistant", "content": "done"}],
            },
        ),
        (
            "brainstormer complete",
            {
                "active_agent": "brainstormer",
                "brainstormer_state": STATE_VISION_COMPLETE,
                "messages": [{"role": "assistant", "content": "done"}],
            },
        ),
        (
            "agentifier complete",
            {
                "active_agent": "agentifier",
                "agentifier_state": STATE_AGENTIFIER_COMPLETE,
                "messages": [{"role": "assistant", "content": "done"}],
            },
        ),
        (
            "agentifier mid-run",
            {
                "active_agent": "agentifier",
                "agentifier_breadth_chosen": True,
                "messages": [{"role": "assistant", "content": "x"}],
            },
        ),
        (
            "stack_advisor complete",
            {
                "active_agent": "stack_advisor",
                "stack_advisor_state": STATE_STACK_COMPLETE,
                "messages": [{"role": "assistant", "content": "done"}],
            },
        ),
        (
            "stack_advisor mid-run",
            {"active_agent": "stack_advisor", "messages": []},
        ),
        (
            "phaser complete",
            {
                "active_agent": "phaser",
                "phases": [{"phase_number": 1}],
                "messages": [{"role": "assistant", "content": "done"}],
            },
        ),
        ("phaser mid-run", {"active_agent": "phaser", "messages": []}),
        (
            "deployer complete",
            {
                "active_agent": "deployer",
                "deployer_state": STATE_DEPLOYER_COMPLETE,
                "messages": [{"role": "assistant", "content": "done"}],
            },
        ),
        ("deployer mid-run", {"active_agent": "deployer", "messages": []}),
    ]


def _buttons(session: dict[str, Any]) -> list[Any]:
    """The row's buttons, in render order.

    The row also carries the mono counters and Fast Forward's modal; those are
    not actions and are not what the emphasis rule is about.
    """
    rendered = _chat_action_buttons(session)
    children = rendered.children or []
    group = next(c for c in children if isinstance(c, dmc.Group))
    return [c for c in group.children if isinstance(c, dmc.Button)]


def _variant(button: Any) -> str | None:
    """A button's variant, with ``None`` meaning it passed none.

    That is the emphasised case: Mantine's default is filled in the theme
    primary, which is how a continue reaches the accent without naming it.
    """
    return getattr(button, "variant", None)


def _filled(button: Any) -> bool:
    return _variant(button) in (None, "filled")


class TestTheRowHasOneEmphasis:
    def test_the_walk_finds_every_row(self) -> None:
        """A generator that quietly produced nothing would pass forever."""
        rows = _rows()
        assert len(rows) == 10
        for name, session in rows:
            assert _buttons(session), name

    def test_no_row_has_two_filled_buttons(self) -> None:
        """The whole rule, in the form that holds for every row.

        Mid-run rows have none — there is nothing to continue to yet — so the
        claim is "at most one", and the rows that do have a continue are
        pinned to exactly one just below.
        """
        offenders = []
        for name, session in _rows():
            filled = [b.id for b in _buttons(session) if _filled(b)]
            if len(filled) > 1:
                offenders.append(f"{name}: {filled}")
        assert not offenders, "more than one emphasised action in:\n" + "\n".join(
            offenders
        )

    def test_every_completed_run_ends_in_exactly_one_filled_button(self) -> None:
        """A completed run always offers somewhere to go, and says so once.

        Deployer included: it is the end of the pipeline, so its continue is
        Start New Project rather than a next agent, but the row is still a
        completed run and still needs the one thing to do next to look like it.
        """
        for name, session in _rows():
            if "complete" not in name:
                continue
            buttons = _buttons(session)
            filled = [b for b in buttons if _filled(b)]
            assert len(filled) == 1, f"{name}: {[b.id for b in filled]}"
            assert filled[0] is buttons[-1], f"{name}: emphasis is not the last action"

    def test_a_mid_run_row_emphasises_nothing(self) -> None:
        """Fast Forward is an option, not a destination."""
        for name, session in _rows():
            if "mid-run" not in name:
                continue
            filled = [b.id for b in _buttons(session) if _filled(b)]
            assert filled == [], f"{name}: {filled}"

    def test_every_other_action_is_an_outline(self) -> None:
        """No `light`, no `subtle`, no `default` — one exception, named.

        `light` is what the Deployer's Start New Project used to be, which is
        how the terminal row ended up as the only completed row on screen with
        nothing emphasised in it.
        """
        offenders = []
        for name, session in _rows():
            for button in _buttons(session):
                if _filled(button) or button.id == _INFO_AFFORDANCE:
                    continue
                if _variant(button) != "outline":
                    offenders.append(f"{name}: {button.id} is {_variant(button)!r}")
        assert not offenders, "not a neutral outline:\n" + "\n".join(offenders)

    def test_the_info_affordance_is_the_only_exception(self) -> None:
        """The exception above is a real button, not a stale id.

        If it were renamed the loop would silently stop excusing anything and
        the rule would still pass — and then quietly stop being true.
        """
        ids = [b.id for _, session in _rows() for b in _buttons(session)]
        assert _INFO_AFFORDANCE in ids
        subtle = {
            b.id
            for _, session in _rows()
            for b in _buttons(session)
            if _variant(b) == "subtle"
        }
        assert subtle == {_INFO_AFFORDANCE}


class TestTheWarnTone:
    def test_re_scan_is_the_row_s_only_coloured_action(self) -> None:
        """Warn is a semantic; the accent is not reachable by naming it (D-LR2).

        The info affordance is excluded here as it is everywhere else in this
        file — and its own colour is checked below rather than waved through,
        because "not an action" excuses its variant, not a hue.
        """
        coloured = {
            b.id: getattr(b, "color", None)
            for _, session in _rows()
            for b in _buttons(session)
            if getattr(b, "color", None) is not None and b.id != _INFO_AFFORDANCE
        }
        assert coloured == {_WARN_BUTTON: "yellow"}

    def test_the_info_affordance_recedes_rather_than_speaks(self) -> None:
        """Grey, which is the one thing it can be: it explains, it does not act."""
        info = next(
            b
            for _, session in _rows()
            for b in _buttons(session)
            if b.id == _INFO_AFFORDANCE
        )
        assert getattr(info, "color", None) == "gray"

    def test_re_scan_wears_the_shared_warn_class(self) -> None:
        """The colour alone is Mantine's pale yellow, which reads as neutral."""
        button = next(
            b
            for _, session in _rows()
            for b in _buttons(session)
            if b.id == _WARN_BUTTON
        )
        assert _WARN_CLASS in (button.className or "").split()
        assert _variant(button) == "outline"

    def test_the_stylesheet_draws_that_class_at_the_agent_rows_weight(self) -> None:
        """One warn tone in the app, not two that drift.

        The chat frame's Re-scan and the agent rows' Needs Update are the same
        statement in different rows, so they share the rule rather than each
        carrying a copy of it.
        """
        css = _STYLESHEET.read_text(encoding="utf-8")
        rule = css.split(f".{_WARN_CLASS} {{")[1].split("}")[0]
        assert "var(--mantine-color-yellow-5)" in rule
        assert ".agent-row-action--needs-update,\n" in css
