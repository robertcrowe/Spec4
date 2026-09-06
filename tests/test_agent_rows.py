"""The agent table is the pipeline, and it tells the truth about every stage.

Four things can go wrong here, and each has its own class below. The table can
drift from the pipeline — so the rows are checked against ``AGENT_KEYS``, the
one definition of the seven agents and their order. The action can disagree
with the readiness state — so every row is compared against
``project_manager.agent_button_state`` directly, on a fixture that puts more
than one state on screen at once. The five states can drift from the design
manifest — so all five variants are asserted, not just the ones a given fixture
happens to produce. And a missing ``usage.json`` entry can turn a normal state
into a crash — so an omitted agent gets its own fixture, and the assertion is
both that the cells are blank and that nothing raised.

The usage fixtures go through ``project_manager.save_usage`` rather than
writing the JSON by hand: the rows are a read side of that writer, and a
hand-rolled file would let the two drift without the suite noticing.
"""

from __future__ import annotations

import json
import pathlib
import time
from typing import Any

import pytest

from spec4 import project_manager
from spec4.app_constants import AGENT_KEYS
from spec4.layouts import _agent_rows, _agent_select_layout, agent_rows
from spec4.layouts._agent_rows import (
    ACTION_BUTTON_PROPS,
    ACTION_LABELS,
    AGENT_DISPLAY_NAMES,
    AGENT_PRODUCES,
    USAGE_BLANK,
    _AGENT_ROWS,
    _action_class,
    _agent_action_button,
    agent_row_id,
    round_usage,
)
from spec4.session import _default_session

# The five states, named here rather than reached through the module under
# test, so a renamed constant fails loudly instead of silently shrinking the
# mapping this file checks.
_START = project_manager.AGENT_BTN_START
_MODIFY = project_manager.AGENT_BTN_MODIFY
_NEEDS_UPDATE = project_manager.AGENT_BTN_NEEDS_UPDATE
_NOT_READY = project_manager.AGENT_BTN_NOT_READY
_REQUIRED = project_manager.AGENT_BTN_REQUIRED

_ALL_STATES = (_START, _MODIFY, _NEEDS_UPDATE, _NOT_READY, _REQUIRED)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _session(working_dir: pathlib.Path | None = None, **extra: Any) -> dict[str, Any]:
    session = _default_session()
    session["phase"] = "agent_select"
    session["project_mode"] = "new"
    if working_dir is not None:
        session["working_dir"] = str(working_dir)
    session.update(extra)
    return session


def _usage_record(agent: str, model: str, tokens_in: int, tokens_out: int) -> dict:
    """One call's usage record, in the shape `spec4.llm` appends."""
    return {
        "timestamp": "2026-03-05T12:00:00+00:00",
        "agent": agent,
        "model": model,
        "provider": "anthropic",
        "streamed": False,
        "prompt_tokens": tokens_in,
        "completion_tokens": tokens_out,
        "total_tokens": tokens_in + tokens_out,
        "computed_cost_usd": 0.01,
        "usage_missing": False,
        "error": None,
    }


@pytest.fixture
def two_state_project(tmp_path: pathlib.Path) -> pathlib.Path:
    """A round where the seven agents are not all in the same state.

    CodeScanner and Brainstormer have run and are consistent (``modify``);
    Agentifier's input moved after its output was written (``needs_update``);
    Designer has its inputs but no output yet (``start``); the tail of the
    pipeline is still missing required inputs (``not_ready``). That spread is
    the point — a fixture where every row says the same thing would pass the
    comparison below without exercising it.
    """
    base = project_manager.ensure_version_dir(tmp_path, 0)
    (base / "code_review.json").write_text("{}")
    (base / "vision.json").write_text("{}")
    (base / "feature_specs.json").write_text("{}")
    time.sleep(0.02)
    (base / "ai_features.json").write_text("{}")
    time.sleep(0.02)
    # Now bump an Agentifier input past its output, so it reads stale.
    (base / "vision.json").write_text("{}")
    return tmp_path


@pytest.fixture
def usage_missing_one(two_state_project: pathlib.Path) -> pathlib.Path:
    """Usage recorded for CodeScanner and Brainstormer, and for nobody else.

    Agentifier is the omitted agent the failure mode names: it has produced an
    artifact, so it is plainly not a fresh round, and it still has no block in
    ``usage.json``.
    """
    project_manager.save_usage(
        two_state_project,
        [
            _usage_record("code_scanner", "claude-sonnet-4-6", 41206, 3118),
            _usage_record("brainstormer", "claude-sonnet-4-6", 32880, 2914),
        ],
        0,
    )
    return two_state_project


# ---------------------------------------------------------------------------
# Walking a rendered tree
# ---------------------------------------------------------------------------


def _walk(node: Any) -> Any:
    """Every component in a rendered tree, depth first."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        children = getattr(current, "children", None)
        if children is None:
            continue
        if not isinstance(children, (list, tuple)):
            children = [children]
        stack.extend(children)


def _rows_of(component: Any) -> list[Any]:
    """The rendered ``<tr>`` rows, in document order."""
    body = next(
        node
        for node in _walk(component)
        if getattr(node, "id", None) == "agent-rows-body"
    )
    children = body.children
    return list(children) if isinstance(children, (list, tuple)) else [children]


def _cell(row: Any, class_name: str) -> Any:
    """The one ``<td>`` in `row` carrying `class_name`."""
    return next(
        node
        for node in _walk(row)
        if type(node).__name__ == "Td"
        and class_name in (getattr(node, "className", "") or "").split()
    )


def _text(node: Any) -> str:
    """All string content in a subtree, joined."""
    return " ".join(
        child for child in _walk(node) if isinstance(child, str)
    )


def _button(row: Any) -> Any:
    return next(
        node for node in _walk(row) if type(node).__name__ == "Button"
    )


# ---------------------------------------------------------------------------
# The seven rows, in pipeline order
# ---------------------------------------------------------------------------


class TestTheRowsAreThePipeline:
    def test_there_are_exactly_seven_rows(self, tmp_path: pathlib.Path) -> None:
        rendered = _agent_rows(tmp_path, 0, _session(tmp_path))
        assert len(_rows_of(rendered)) == 7
        assert len(agent_rows(tmp_path, 0, _session(tmp_path))) == 7

    def test_their_order_is_agent_keys(self, tmp_path: pathlib.Path) -> None:
        rows = agent_rows(tmp_path, 0, _session(tmp_path))
        assert tuple(row.key for row in rows) == AGENT_KEYS

    def test_the_rendered_order_is_agent_keys(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The order survives rendering, not just the data function."""
        rendered = _agent_rows(tmp_path, 0, _session(tmp_path))
        ids = [getattr(row, "id", None) for row in _rows_of(rendered)]
        assert ids == [agent_row_id(key) for key in AGENT_KEYS]

    def test_the_row_table_is_derived_from_agent_keys(self) -> None:
        assert tuple(spec.key for spec in _AGENT_ROWS) == AGENT_KEYS

    def test_every_agent_has_a_display_name(self) -> None:
        assert set(AGENT_DISPLAY_NAMES) == set(AGENT_KEYS)

    def test_no_working_directory_still_renders_seven_rows(self) -> None:
        """An unopened project is not an error: seven rows, all not-yet-run."""
        rows = agent_rows(None, None, _session())
        assert len(rows) == 7
        assert all(row.model == "" and row.tokens == "" for row in rows)


class TestEachRowsCells:
    def test_each_row_names_its_agent_and_artifact(
        self, tmp_path: pathlib.Path
    ) -> None:
        rendered = _agent_rows(tmp_path, 0, _session(tmp_path))
        for key, row in zip(AGENT_KEYS, _rows_of(rendered)):
            assert _text(_cell(row, "agent")) == AGENT_DISPLAY_NAMES[key]
            assert _text(_cell(row, "produces")) == AGENT_PRODUCES[key]

    def test_the_produced_artifact_matches_the_design_mock(self) -> None:
        """The mock's Produces column, agent by agent."""
        assert AGENT_PRODUCES == {
            "code_scanner": "code_review.json",
            "brainstormer": "vision.json",
            "agentifier": "ai_features.json",
            "designer": "design/mock.html",
            "stack_advisor": "stack.json",
            "phaser": "phases/",
            "deployer": "deployment-plan.md",
        }

    def test_the_artifact_model_and_token_cells_are_monospace(
        self, tmp_path: pathlib.Path
    ) -> None:
        rendered = _agent_rows(tmp_path, 0, _session(tmp_path))
        for row in _rows_of(rendered):
            for name in ("produces", "model", "tokens"):
                assert "mono" in _cell(row, name).className.split()

    def test_each_row_exposes_an_action_button(
        self, tmp_path: pathlib.Path
    ) -> None:
        rendered = _agent_rows(tmp_path, 0, _session(tmp_path))
        for row in _rows_of(rendered):
            button = _button(_cell(row, "action"))
            assert _text(button) in set(ACTION_LABELS.values())

    def test_the_columns_are_in_the_mocks_order(
        self, tmp_path: pathlib.Path
    ) -> None:
        rendered = _agent_rows(tmp_path, 0, _session(tmp_path))
        first = _rows_of(rendered)[0]
        classes = [
            (cell.className or "").split()[0]
            for cell in first.children
        ]
        assert classes == ["agent", "produces", "model", "tokens", "action"]

    def test_it_uses_no_step_numbers_no_descriptions_and_no_emoji(
        self, usage_missing_one: pathlib.Path
    ) -> None:
        """The three things the cards carried and the rows must not.

        Emoji are caught by codepoint rather than by listing the seven the old
        table used, so a different one cannot slip back in.
        """
        rendered = _agent_rows(usage_missing_one, 0, _session(usage_missing_one))
        text = _text(rendered)
        assert "Step" not in text
        assert not any(ord(ch) > 0x2000 for ch in text), text
        # The old per-agent descriptions, one sample from each end of the table.
        assert "analyze the existing project directory" not in text
        assert "plan coding-agent workflow" not in text


# ---------------------------------------------------------------------------
# The action comes from the one readiness authority
# ---------------------------------------------------------------------------


class TestTheActionIsNotReDerived:
    def test_every_row_matches_agent_button_state(
        self, two_state_project: pathlib.Path
    ) -> None:
        session = _session(two_state_project)
        rows = agent_rows(two_state_project, 0, session)
        for row in rows:
            assert row.action == project_manager.agent_button_state(
                two_state_project, row.key, session
            )

    def test_the_fixture_exercises_more_than_one_state(
        self, two_state_project: pathlib.Path
    ) -> None:
        """Guards the guard: one uniform state would make the check vacuous."""
        rows = agent_rows(two_state_project, 0, _session(two_state_project))
        assert len({row.action for row in rows}) > 1

    def test_a_pending_brownfield_round_is_required_then_not_ready(
        self, two_state_project: pathlib.Path
    ) -> None:
        """The one state the ordinary fixtures cannot reach.

        ``required`` exists only while a new round is pending, and it is the
        state that must not be re-derived into ``start`` — the two draw the
        same button, so only the label would show the mistake.
        """
        (two_state_project / ".spec4" / "v0" / "IMPLEMENTED").write_text("")
        session = _session(two_state_project)
        rows = {row.key: row for row in agent_rows(two_state_project, 0, session)}
        assert rows["code_scanner"].action == _REQUIRED
        assert all(
            row.action == _NOT_READY
            for key, row in rows.items()
            if key != "code_scanner"
        )

    def test_the_label_follows_the_state(
        self, two_state_project: pathlib.Path
    ) -> None:
        rendered = _agent_rows(
            two_state_project, 0, _session(two_state_project)
        )
        rows = agent_rows(two_state_project, 0, _session(two_state_project))
        for row, node in zip(rows, _rows_of(rendered)):
            assert _text(_button(node)) == ACTION_LABELS[row.action]

    def test_only_not_ready_is_disabled(
        self, two_state_project: pathlib.Path
    ) -> None:
        rendered = _agent_rows(
            two_state_project, 0, _session(two_state_project)
        )
        rows = agent_rows(two_state_project, 0, _session(two_state_project))
        for row, node in zip(rows, _rows_of(rendered)):
            assert _button(node).disabled == (row.action == _NOT_READY)
            assert row.disabled == (row.action == _NOT_READY)


class TestTheButtonRoutesLikeTheOldOnes:
    def test_the_action_carries_the_existing_agent_select_id(
        self, tmp_path: pathlib.Path
    ) -> None:
        """`on_agent_pill_click` is the routing, unchanged (D-AR2).

        Every enabled row activates through the same pattern-matching id the
        previous agent-select buttons used, so nothing about navigation is
        re-derived here.
        """
        rendered = _agent_rows(tmp_path, 0, _session(tmp_path))
        ids = [_button(_cell(row, "action")).id for row in _rows_of(rendered)]
        assert ids == [
            {"type": "agent-pill", "agent": key} for key in AGENT_KEYS
        ]

    def test_the_project_view_still_carries_all_seven(
        self, tmp_path: pathlib.Path
    ) -> None:
        view = _agent_select_layout(_session(tmp_path))
        found = {
            node.id["agent"]
            for node in _walk(view)
            if isinstance(getattr(node, "id", None), dict)
            and node.id.get("type") == "agent-pill"
        }
        assert found == set(AGENT_KEYS)


# ---------------------------------------------------------------------------
# The five variants, against the design manifest
# ---------------------------------------------------------------------------


class TestTheFiveActionVariants:
    """D-AR1: the manifest's five buttons, all five asserted.

    They are checked through ``_agent_action_button`` rather than through a
    fixture that happens to produce them, because no single project state puts
    all five on screen at once — and a mapping is only correct if every entry
    is.
    """

    def test_the_mapping_covers_exactly_the_five_states(self) -> None:
        assert set(ACTION_BUTTON_PROPS) == set(_ALL_STATES)
        assert set(ACTION_LABELS) == set(_ALL_STATES)

    def test_start_is_a_filled_green_button(self) -> None:
        button = _agent_action_button("brainstormer", _START)
        assert button.variant == "filled"
        # D-LR2: no local colour — a filled button with no `color` takes the
        # theme primary, which is the accent.
        assert getattr(button, "color", None) is None
        assert button.children == "Start"

    def test_required_is_the_same_button_as_start(self) -> None:
        start = _agent_action_button("code_scanner", _START)
        required = _agent_action_button("code_scanner", _REQUIRED)
        assert required.variant == start.variant == "filled"
        assert getattr(required, "color", None) is None
        assert required.children == "Required"

    def test_modify_is_a_neutral_outline_with_green_text(self) -> None:
        button = _agent_action_button("brainstormer", _MODIFY)
        assert button.variant == "outline"
        # The green is the theme primary, so the button names no colour; the
        # neutral border is the class, since `variant="outline"` would
        # otherwise draw the border in the accent too.
        assert getattr(button, "color", None) is None
        assert "agent-row-action--modify" in button.className.split()
        assert button.children == "Modify"

    def test_needs_update_is_a_warn_outline(self) -> None:
        button = _agent_action_button("stack_advisor", _NEEDS_UPDATE)
        assert button.variant == "outline"
        assert button.color == "yellow"
        assert "agent-row-action--needs-update" in button.className.split()
        assert button.children == "Needs Update"

    def test_not_ready_is_a_disabled_outline(self) -> None:
        button = _agent_action_button("phaser", _NOT_READY)
        assert button.variant == "outline"
        assert button.disabled is True
        # Mantine greys a disabled button on its own, so this one names no
        # colour either.
        assert getattr(button, "color", None) is None
        assert button.children == "Not Ready"

    @pytest.mark.parametrize("state", _ALL_STATES)
    def test_every_state_renders_a_button(self, state: str) -> None:
        button = _agent_action_button("designer", state)
        assert button.children == ACTION_LABELS[state]
        assert button.variant in {"filled", "outline"}

    @pytest.mark.parametrize("state", _ALL_STATES)
    def test_every_state_carries_the_shared_class(self, state: str) -> None:
        """The row buttons' height and width come from one rule, not five."""
        assert _action_class(state).split()[0] == "agent-row-action"

    def test_only_two_states_need_a_modifier(self) -> None:
        """Mantine draws three of the five as the manifest specifies them; the
        other two are corrected in CSS, and this pins which."""
        modified = {
            state for state in _ALL_STATES if len(_action_class(state).split()) > 1
        }
        assert modified == {_MODIFY, _NEEDS_UPDATE}

    def test_no_button_names_a_colour_but_needs_update(self) -> None:
        """D-LR2, restated as a contract over the whole mapping."""
        coloured = {
            state: props["color"]
            for state, props in ACTION_BUTTON_PROPS.items()
            if "color" in props
        }
        assert coloured == {_NEEDS_UPDATE: "yellow"}


# ---------------------------------------------------------------------------
# Usage: the model and tokens for the round
# ---------------------------------------------------------------------------


class TestUsageCells:
    def test_a_recorded_agent_shows_its_model_and_tokens(
        self, usage_missing_one: pathlib.Path
    ) -> None:
        rows = {
            row.key: row
            for row in agent_rows(
                usage_missing_one, 0, _session(usage_missing_one)
            )
        }
        assert rows["code_scanner"].model == "claude-sonnet-4-6"
        assert rows["code_scanner"].tokens == "41,206 in / 3,118 out"
        assert rows["brainstormer"].tokens == "32,880 in / 2,914 out"

    def test_the_model_is_the_last_one_the_agent_ran_on(
        self, two_state_project: pathlib.Path
    ) -> None:
        """A re-run on a second model this round reports the second one."""
        project_manager.save_usage(
            two_state_project,
            [_usage_record("designer", "gpt-5-mini", 100, 10)],
            0,
        )
        project_manager.save_usage(
            two_state_project,
            [_usage_record("designer", "claude-sonnet-4-6", 200, 20)],
            0,
        )
        usage = round_usage(two_state_project, 0)
        assert usage["designer"].model == "claude-sonnet-4-6"
        assert usage["designer"].tokens == "300 in / 30 out"

    def test_every_agent_key_is_present_in_the_usage_map(
        self, usage_missing_one: pathlib.Path
    ) -> None:
        """The defensive accessor: no caller ever has to guard the lookup."""
        assert set(round_usage(usage_missing_one, 0)) == set(AGENT_KEYS)


class TestAMissingUsageEntry:
    """The failure mode: an agent with no block in ``usage.json`` (D-AR3)."""

    def test_the_omitted_agent_renders_blank_and_does_not_raise(
        self, usage_missing_one: pathlib.Path
    ) -> None:
        rendered = _agent_rows(
            usage_missing_one, 0, _session(usage_missing_one)
        )
        row = _rows_of(rendered)[AGENT_KEYS.index("agentifier")]
        assert _text(_cell(row, "model")) == ""
        assert _text(_cell(row, "tokens")) == ""

    def test_the_omitted_agent_is_blank_in_the_data_too(
        self, usage_missing_one: pathlib.Path
    ) -> None:
        rows = {
            row.key: row
            for row in agent_rows(
                usage_missing_one, 0, _session(usage_missing_one)
            )
        }
        assert rows["agentifier"].model == ""
        assert rows["agentifier"].tokens == ""

    def test_the_omitted_agent_really_is_omitted(
        self, usage_missing_one: pathlib.Path
    ) -> None:
        """Guards the fixture: a file that happened to have the block would
        make the assertions above pass for the wrong reason."""
        data = json.loads(
            (
                project_manager.get_version_dir(usage_missing_one, 0)
                / "usage.json"
            ).read_text()
        )
        assert "agentifier" not in data["agents"]
        assert "code_scanner" in data["agents"]

    def test_a_blank_cell_is_never_a_zero(
        self, usage_missing_one: pathlib.Path
    ) -> None:
        """The whole point of blank: a zero would read as "ran, cost nothing"."""
        rendered = _agent_rows(
            usage_missing_one, 0, _session(usage_missing_one)
        )
        for key in ("agentifier", "designer", "stack_advisor", "phaser"):
            row = _rows_of(rendered)[AGENT_KEYS.index(key)]
            assert _text(_cell(row, "tokens")) == ""
            assert "0" not in _text(_cell(row, "model"))

    def test_no_usage_file_at_all_is_not_an_error(
        self, two_state_project: pathlib.Path
    ) -> None:
        assert not (
            project_manager.get_version_dir(two_state_project, 0) / "usage.json"
        ).exists()
        rows = agent_rows(two_state_project, 0, _session(two_state_project))
        assert all(row.model == "" and row.tokens == "" for row in rows)

    def test_a_malformed_usage_file_is_not_an_error(
        self, two_state_project: pathlib.Path
    ) -> None:
        (
            project_manager.get_version_dir(two_state_project, 0) / "usage.json"
        ).write_text("{ not json")
        assert round_usage(two_state_project, 0) == {
            key: USAGE_BLANK for key in AGENT_KEYS
        }

    def test_an_entry_with_no_calls_reads_as_not_yet_run(
        self, two_state_project: pathlib.Path
    ) -> None:
        base = project_manager.get_version_dir(two_state_project, 0)
        (base / "usage.json").write_text(
            json.dumps({"agents": {"phaser": {"calls": 0, "models": []}}})
        )
        assert round_usage(two_state_project, 0)["phaser"] == USAGE_BLANK


# ---------------------------------------------------------------------------
# Where it sits
# ---------------------------------------------------------------------------


class TestItSitsBeneathTheRoundTree:
    def test_the_rows_follow_the_tree_directly(
        self, two_state_project: pathlib.Path
    ) -> None:
        view = _agent_select_layout(_session(two_state_project))
        assert getattr(view.children[0], "id", None) == "round-tree"
        assert getattr(view.children[1], "id", None) == "agent-rows"

    def test_the_marketing_prose_is_gone(
        self, two_state_project: pathlib.Path
    ) -> None:
        """The heading and the two-bullet introduction the rows replace."""
        text = _text(_agent_select_layout(_session(two_state_project)))
        assert "Where Should We Begin?" not in text
        assert "Choose an agent:" not in text

    def test_the_change_provider_button_survives(
        self, two_state_project: pathlib.Path
    ) -> None:
        view = _agent_select_layout(_session(two_state_project))
        ids = {
            node.id
            for node in _walk(view)
            if isinstance(getattr(node, "id", None), str)
        }
        assert "btn-agent-change-provider" in ids

    def test_the_rows_read_the_round_the_view_is_showing(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A second round must not report the first round's usage."""
        project_manager.ensure_version_dir(tmp_path, 0)
        project_manager.save_usage(
            tmp_path, [_usage_record("brainstormer", "gpt-5-mini", 5, 1)], 0
        )
        project_manager.ensure_version_dir(tmp_path, 1)
        assert round_usage(tmp_path, 1)["brainstormer"] == USAGE_BLANK
        assert round_usage(tmp_path, 0)["brainstormer"].model == "gpt-5-mini"
