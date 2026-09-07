"""The chat frame's pipeline indicator: seven plain labels, no connectors.

Three claims, and each is a way the bar has been wrong before or could be.

*The order is not restated here.* The bar walks ``AGENT_KEYS``, so a stage
added to the pipeline appears in it without anyone editing the chat layout. The
test asserts the derivation rather than the seven names: a list of names would
pass just as well against a locally re-declared copy, which is exactly the
drift the phase's mitigation names.

*Nothing sits between the labels.* The arrows were the connector; a badge, a
chevron or a divider dropped in later is the same mistake under a new name, so
the assertion is that the bar contains nothing but the seven labels.

*The three states land on the right agents.* Active, completed and unreachable
are modifier classes on the label, and the precondition message is still the
tooltip on a dimmed one — which is the only explanation a plain dimmed label
carries.
"""

from __future__ import annotations

import pathlib
from typing import Any

from spec4.app_constants import (
    AGENT_KEYS,
    STATE_AGENTIFIER_COMPLETE,
    STATE_DEPLOYER_COMPLETE,
    STATE_PHASES_COMPLETE,
)
from spec4.layouts._agent_rows import AGENT_DISPLAY_NAMES
from spec4.layouts._chat import (
    _PILL_ACTIVE,
    _PILL_BASE,
    _PILL_DONE,
    _PILL_UNREACHABLE,
    _agent_status_bar,
)
from spec4.session import _validate_agent_preconditions

_SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "spec4"
_STYLESHEET = _SRC / "assets" / "v3.css"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _walk(node: Any) -> list[Any]:
    """Every component under `node`, including it, depth first."""
    found = [node]
    children = getattr(node, "children", None)
    if children is None:
        return found
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if isinstance(child, str):
            found.append(child)
        else:
            found.extend(_walk(child))
    return found


def _row(session: dict[str, Any]) -> Any:
    """The `.pipeline` container itself — the row the seven labels sit in."""
    return next(
        node
        for node in _walk(_agent_status_bar(session))
        if getattr(node, "className", None) == "pipeline"
    )


def _labels(session: dict[str, Any]) -> list[Any]:
    return list(_row(session).children)


def _classes(node: Any) -> set[str]:
    return set((getattr(node, "className", "") or "").split())


def _by_agent(session: dict[str, Any]) -> dict[str, Any]:
    """Each label, keyed by the agent it stands for.

    Keyed positionally: the active label is a span with no id to key on,
    precisely because clicking it would navigate to where the developer
    already is. ``strict`` is the assertion that the row and the pipeline are
    the same length.
    """
    return dict(zip(AGENT_KEYS, _labels(session), strict=True))


def _session(**extra: Any) -> dict[str, Any]:
    return {"active_agent": "brainstormer", "working_dir": "", **extra}


def _complete_project(tmp_path: pathlib.Path) -> dict[str, Any]:
    """A session in which every one of the seven agents has run."""
    version = tmp_path / ".spec4" / "v0"
    (version / "design").mkdir(parents=True)
    (version / "design" / "mock.html").write_text("<html></html>", encoding="utf-8")
    return _session(
        working_dir=str(tmp_path),
        code_review={"findings": []},
        vision_statement={"purpose": "x"},
        agentifier_state=STATE_AGENTIFIER_COMPLETE,
        stack_statement={"stack": []},
        phases=[{"phase_number": 1}],
        phaser_state=STATE_PHASES_COMPLETE,
        deployer_state=STATE_DEPLOYER_COMPLETE,
    )


# ---------------------------------------------------------------------------
# The seven, in order, derived
# ---------------------------------------------------------------------------


class TestItRendersExactlyTheSevenAgents:
    def test_the_labels_are_agent_keys_in_agent_keys_order(self) -> None:
        texts = [node.children for node in _labels(_session())]
        assert texts == [AGENT_DISPLAY_NAMES[key] for key in AGENT_KEYS]

    def test_there_are_exactly_seven(self) -> None:
        assert len(_labels(_session())) == len(AGENT_KEYS) == 7

    def test_the_order_is_not_a_second_copy_of_the_list(self, monkeypatch: Any) -> None:
        """The derivation, not the seven names it happens to produce today.

        Asserted by rendering against a pipeline with an eighth stage: a bar
        that walks ``AGENT_KEYS`` grows a label, and a bar carrying its own
        list does not. This is the drift the phase's mitigation names, and a
        test listing the seven current names would not catch it.
        """
        import spec4.layouts._chat as chat

        monkeypatch.setattr(chat, "AGENT_KEYS", (*AGENT_KEYS, "auditor"))
        monkeypatch.setattr(
            chat, "AGENT_DISPLAY_NAMES", {**AGENT_DISPLAY_NAMES, "auditor": "Auditor"}
        )
        texts = [node.children for node in _labels(_session())]
        assert texts[-1] == "Auditor"
        assert len(texts) == 8


class TestNoConnectors:
    def test_nothing_sits_between_the_labels(self) -> None:
        """The arrows are gone, and so is anywhere to put a replacement.

        Every child of the row is one of the seven labels — there is no eighth
        element for a chevron, a bullet or a divider to be.
        """
        labels = _labels(_session())
        assert len(labels) == len(AGENT_KEYS)
        assert all(_PILL_BASE in _classes(node) for node in labels)

    def test_no_arrow_character_survives_in_the_bar(self) -> None:
        """The arrow as text, wherever it might have moved to.

        The Back button's own ``←`` is not in the pipeline row and is removed
        in the next phase together with the button.
        """
        strings = [node for node in _walk(_row(_session())) if isinstance(node, str)]
        assert not [s for s in strings if "→" in s or "←" in s or "›" in s]

    def test_the_labels_are_plain_text_not_badges(self) -> None:
        """A `dmc.Badge` is a filled chip; the register asks for a label."""
        types = {type(node).__name__ for node in _labels(_session())}
        assert types <= {"Span", "Button"}


# ---------------------------------------------------------------------------
# The three states
# ---------------------------------------------------------------------------


class TestStates:
    def test_the_active_agent_carries_the_active_class(self) -> None:
        by_key = _by_agent(_session(active_agent="agentifier"))
        assert _PILL_ACTIVE in _classes(by_key["agentifier"])
        assert [key for key in AGENT_KEYS if _PILL_ACTIVE in _classes(by_key[key])] == [
            "agentifier"
        ]

    def test_the_active_agent_is_not_a_control(self) -> None:
        """Clicking it would navigate to where the developer already is."""
        by_key = _by_agent(_session(active_agent="agentifier"))
        assert type(by_key["agentifier"]).__name__ == "Span"

    def test_completed_agents_carry_the_done_class(
        self, tmp_path: pathlib.Path
    ) -> None:
        session = _complete_project(tmp_path)
        by_key = _by_agent(session)
        done = {key for key in AGENT_KEYS if _PILL_DONE in _classes(by_key[key])}
        # Everything but the active agent, which wears the active class instead.
        assert done == set(AGENT_KEYS) - {session["active_agent"]}

    def test_an_agent_that_has_not_run_is_neither_done_nor_dimmed(self) -> None:
        """Reachable but not yet run: a plain label, no modifier at all."""
        session = _session(active_agent="code_scanner")
        by_key = _by_agent(session)
        assert _classes(by_key["brainstormer"]) == {_PILL_BASE}

    def test_unreachable_agents_are_dimmed_and_disabled(self) -> None:
        """No vision yet, so four of the seven cannot be entered."""
        session = _session(active_agent="brainstormer")
        by_key = _by_agent(session)
        blocked = {
            key
            for key in AGENT_KEYS
            if _validate_agent_preconditions(key, session) is not None
        }
        assert blocked, "precondition for the test: something is unreachable"
        for key in AGENT_KEYS:
            if key == session["active_agent"]:
                continue
            node = by_key[key]
            assert (_PILL_UNREACHABLE in _classes(node)) is (key in blocked), key
            assert node.disabled is (key in blocked), key

    def test_a_dimmed_label_keeps_its_precondition_tooltip(self) -> None:
        session = _session(active_agent="brainstormer")
        by_key = _by_agent(session)
        assert by_key["phaser"].title == _validate_agent_preconditions(
            "phaser", session
        )
        assert "vision statement" in by_key["phaser"].title

    def test_a_reachable_label_has_no_tooltip(self) -> None:
        """The tooltip is the reason it cannot be entered; there isn't one."""
        session = _session(active_agent="brainstormer")
        by_key = _by_agent(session)
        assert by_key["code_scanner"].title is None


# ---------------------------------------------------------------------------
# The ids the rest of the app routes through
# ---------------------------------------------------------------------------


class TestTheIdsAreUnchanged:
    def test_every_inactive_agent_keeps_its_agent_pill_id(self) -> None:
        session = _session(active_agent="brainstormer")
        ids = [
            node.id
            for node in _labels(session)
            if getattr(node, "id", None) is not None
        ]
        assert ids == [
            {"type": "agent-pill", "agent": key}
            for key in AGENT_KEYS
            if key != "brainstormer"
        ]

    def test_the_bar_holds_no_control_but_the_pills(self) -> None:
        """D-LR8: the `← Back` button that stood beside the labels is gone.

        Asserted as "every button here is a pill" rather than as the absence
        of the one id it had, because the id is the weaker claim: a different
        control dropped in beside the labels later would pass that and fail
        this. The bar is the seven labels and the rule under them.

        Every pill carries a pattern id (`{"type": "agent-pill", ...}`) except
        the active one, which is a span rather than a button precisely because
        it has nowhere to go — so a plain string id on a button in this bar is
        exactly what should not be here.
        """
        strays = [
            node
            for node in _walk(_agent_status_bar(_session()))
            if type(node).__name__ == "Button"
            and not isinstance(getattr(node, "id", None), dict)
        ]
        assert not strays, [getattr(n, "children", n) for n in strays]


# ---------------------------------------------------------------------------
# The stylesheet the classes reach
# ---------------------------------------------------------------------------


class TestTheStylesheetDrawsThem:
    def test_every_class_the_layout_attaches_is_styled(self) -> None:
        css = _STYLESHEET.read_text(encoding="utf-8")
        for name in (_PILL_BASE, _PILL_ACTIVE, _PILL_DONE, _PILL_UNREACHABLE):
            assert f".{name}" in css, name

    def test_the_active_state_uses_the_navs_mechanism(self) -> None:
        """The theme primary through a class, never a green named here (D-LR2)."""
        css = _STYLESHEET.read_text(encoding="utf-8")
        rule = css.split(f".{_PILL_ACTIVE} {{")[1].split("}")[0]
        assert "var(--mantine-primary-color-filled)" in rule
        assert "#39" not in rule.upper()
