"""The round cost tells the truth about what the round has spent.

The failure this surface exists to prevent is a *confident* number. Summing
every call and treating an unpriceable one as zero produces a figure that is
wrong in the one direction that matters — too low — and looks exactly like a
correct one. So four things are asserted here and each has its own class:

* the figure is labelled an estimate in every state, including the two states
  where there is no figure at all;
* its token counts are the round's ``usage.json``, so they agree with the chat
  frame's cost card and with ``spec4-usage``;
* a call that could not be priced is named, with its model, and left out of
  the total rather than folded in at zero;
* "nothing has run" and "something ran and we cannot price it" are two
  different sentences, and neither is ``$0.0000``.

The fixtures are real ``usage.json`` files written through
``project_manager.save_usage``, because the point is that the strip agrees
with the file the rest of the app reads.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

from spec4 import project_manager
from spec4.callbacks import on_round_cost
from spec4.layouts import _agent_select_layout, _round_cost, round_cost_lines
from spec4.layouts._round_cost import COST_LABEL, NO_CALLS, _unpriced_name
from spec4.layouts._shared import PRICE_SOURCE_FALLBACK, price_source_note
from spec4.session import _default_session

from tests.test_usage_capture import _call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _texts(node: Any, acc: list[str] | None = None) -> list[str]:
    """Every string leaf under ``node``, in document order."""
    acc = [] if acc is None else acc
    if isinstance(node, str):
        acc.append(node)
        return acc
    if isinstance(node, list | tuple):
        for item in node:
            _texts(item, acc)
        return acc
    children = getattr(node, "children", None)
    if children is not None:
        _texts(children, acc)
    return acc


def _ids(node: Any, acc: list[Any] | None = None) -> list[Any]:
    """Every component id under ``node``, in document order."""
    acc = [] if acc is None else acc
    if isinstance(node, list | tuple):
        for item in node:
            _ids(item, acc)
        return acc
    node_id = getattr(node, "id", None)
    if node_id is not None:
        acc.append(node_id)
    children = getattr(node, "children", None)
    if children is not None and not isinstance(children, str):
        _ids(children, acc)
    return acc


def _by_id(node: Any) -> dict[Any, Any]:
    """Every component under ``node`` that carries an id, keyed by it."""
    found: dict[Any, Any] = {}
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, list | tuple):
            stack.extend(current)
            continue
        node_id = getattr(current, "id", None)
        if isinstance(node_id, str):
            found[node_id] = current
        children = getattr(current, "children", None)
        if children is not None and not isinstance(children, str):
            stack.append(children)
    return found


def _write(root: pathlib.Path, records: list[dict[str, Any]], version: int = 0) -> None:
    project_manager.save_usage(root, records, version)


def _lines(root: pathlib.Path | None, version: int | None = 0) -> list[str]:
    return list(round_cost_lines(str(root) if root else None, version))


def _session(working_dir: pathlib.Path | None) -> dict[str, Any]:
    session = _default_session()
    session.update(
        {
            "phase": "agent_select",
            "project_mode": "new",
            "working_dir": str(working_dir) if working_dir else None,
            "phase_version": 0,
        }
    )
    return session


# The three fixtures the states are named for, so a test says which one it is
# exercising rather than restating a list of calls.
def _priced(root: pathlib.Path) -> None:
    """A round where everything could be priced."""
    _write(root, [_call("brainstormer", cost=0.02), _call("phaser", cost=0.5)])


def _partly_unpriced(root: pathlib.Path) -> None:
    """Two of five calls have no price: one with no cost-map entry, one that
    reported no usage at all."""
    _write(
        root,
        [
            _call("brainstormer", cost=0.02),
            _call("phaser", cost=0.5),
            _call("phaser", cost=0.1),
            _call("agentifier", model="gpt-5-mini", cost=None),
            _call(
                "stack_advisor",
                model="gpt-5-mini",
                prompt=None,
                completion=None,
                cost=None,
                missing=True,
            ),
        ],
    )


def _all_unpriced(root: pathlib.Path) -> None:
    _write(
        root,
        [
            _call("agentifier", model="gpt-5-mini", cost=None),
            _call("agentifier", model="gpt-5-mini", cost=None),
        ],
    )


_FIXTURES = {
    "priced": _priced,
    "partly-unpriced": _partly_unpriced,
    "all-unpriced": _all_unpriced,
    "no-calls": lambda root: None,
}


# ---------------------------------------------------------------------------
# The estimate label
# ---------------------------------------------------------------------------


class TestEstimateLabel:
    @pytest.mark.parametrize("fixture", sorted(_FIXTURES))
    def test_every_state_is_labelled_an_estimate(
        self, tmp_path: pathlib.Path, fixture: str
    ) -> None:
        """Including the two states that show no figure — a line reading only
        "unknown" would leave the developer to guess whether the app is quoting
        a bill or its own arithmetic."""
        _FIXTURES[fixture](tmp_path)
        figure, _, note = _lines(tmp_path)
        assert figure.startswith(f"{COST_LABEL}, v0: ")
        assert note.startswith("Estimates from ")

    @pytest.mark.parametrize("fixture", sorted(_FIXTURES))
    def test_the_price_source_disclaimer_is_always_present(
        self, tmp_path: pathlib.Path, fixture: str
    ) -> None:
        _FIXTURES[fixture](tmp_path)
        assert "your provider's billing is authoritative" in _lines(tmp_path)[2].lower()

    def test_the_disclaimer_names_the_source_the_file_recorded(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Not the source this build happens to use: a round priced months ago
        against a different map still describes itself."""
        _priced(tmp_path)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        source = data["notes"]["computed_cost_source"]
        assert _lines(tmp_path)[2] == price_source_note(source)
        assert source in _lines(tmp_path)[2]

    def test_a_round_with_no_file_falls_back_to_a_named_source(
        self, tmp_path: pathlib.Path
    ) -> None:
        assert PRICE_SOURCE_FALLBACK in _lines(tmp_path)[2]

    def test_the_label_carries_the_round(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, [_call("phaser", cost=0.1)], version=0)
        _write(tmp_path, [_call("phaser", cost=0.9)], version=3)
        assert _lines(tmp_path, 3)[0].startswith(f"{COST_LABEL}, v3: $0.9000")


# ---------------------------------------------------------------------------
# The numbers come from usage.json
# ---------------------------------------------------------------------------


class TestNumbers:
    def test_token_totals_match_the_usage_record(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(
            tmp_path,
            [
                _call("phaser", prompt=12000, completion=1500, cost=0.5),
                _call("brainstormer", prompt=800, completion=100, cost=0.01),
            ],
        )
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        totals = data["totals"]
        assert totals["input_tokens"] == 12800
        assert totals["output_tokens"] == 1600
        assert "Tokens: 12,800 in / 1,600 out" in _lines(tmp_path)[0]

    def test_the_cost_is_the_files_own_total(self, tmp_path: pathlib.Path) -> None:
        """No second aggregation path: the figure is the ``totals`` block
        ``save_usage`` recomputed, not a sum taken here."""
        _partly_unpriced(tmp_path)
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        total = data["totals"]["computed_cost_usd"]
        assert total == pytest.approx(0.62)
        assert f"${total:,.4f}" in _lines(tmp_path)[0]

    def test_it_agrees_with_the_chat_frames_cost_card(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The two surfaces read the same round total, so they can never quote
        the developer two different numbers for the same round."""
        _partly_unpriced(tmp_path)
        summary = project_manager.cost_summary(tmp_path, 0, "phaser")
        assert summary is not None
        record = project_manager.round_cost(tmp_path, 0)
        assert record["total"] == summary["total"]

    def test_cache_reads_are_named_when_reported(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, [_call("phaser", cached=4000, cost=0.5)])
        assert "(4,000 cached)" in _lines(tmp_path)[0]


# ---------------------------------------------------------------------------
# Pricing gaps are named, not folded in
# ---------------------------------------------------------------------------


class TestUnpricedCalls:
    def test_each_unpriced_call_is_named_with_its_model(
        self, tmp_path: pathlib.Path
    ) -> None:
        _partly_unpriced(tmp_path)
        unpriced = _lines(tmp_path)[1]
        assert unpriced.startswith(
            "2 of 5 calls could not be priced and are excluded: "
        )
        assert "Agentifier (gpt-5-mini)" in unpriced
        assert "StackAdvisor (gpt-5-mini)" in unpriced

    def test_the_named_calls_are_excluded_from_the_total(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The figure is the three priced calls and nothing else — the two
        named ones are absent from it, not present at zero."""
        _partly_unpriced(tmp_path)
        assert f"{COST_LABEL}, v0: $0.6200 ·" in _lines(tmp_path)[0]

    def test_repeated_gaps_group_by_agent_and_model(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A re-run that failed to price five times is one gap, named once —
        five identical rows would bury the one model to go look up."""
        _write(
            tmp_path,
            [_call("agentifier", model="gpt-5-mini", cost=None) for _ in range(5)],
        )
        record = project_manager.round_cost(tmp_path, 0)
        assert record["unpriced"] == [
            {"agent": "agentifier", "model": "gpt-5-mini", "calls": 5}
        ]
        assert _lines(tmp_path)[1] == (
            "5 of 5 calls could not be priced and are excluded: "
            "Agentifier (gpt-5-mini)"
        )

    def test_two_models_under_one_agent_are_two_entries(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(
            tmp_path,
            [
                _call("agentifier", model="gpt-5-mini", cost=None),
                _call("agentifier", model="gpt-5-nano", cost=None),
            ],
        )
        assert "Agentifier (gpt-5-mini), Agentifier (gpt-5-nano)" in _lines(tmp_path)[1]

    def test_the_named_count_matches_the_rollups_count(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The list and the count beside it must describe the same calls: the
        count comes from ``summarize_usage`` and the names from the history,
        and a drift between the two tests would be invisible on screen."""
        _partly_unpriced(tmp_path)
        record = project_manager.round_cost(tmp_path, 0)
        total = record["total"]
        named = sum(group["calls"] for group in record["unpriced"])
        assert named == total["calls_missing_cost"] + total["calls_missing_usage"]

    def test_a_call_with_no_model_is_named_by_its_agent_alone(self) -> None:
        assert _unpriced_name({"agent": "phaser", "model": ""}) == "Phaser"
        assert _unpriced_name({"agent": "phaser", "model": "gpt-5"}) == "Phaser (gpt-5)"

    def test_a_fully_priced_round_says_so(self, tmp_path: pathlib.Path) -> None:
        _priced(tmp_path)
        assert _lines(tmp_path)[1] == "all 2 calls priced"

    def test_one_priced_call_is_singular(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, [_call("phaser", cost=0.5)])
        assert _lines(tmp_path)[1] == "all 1 call priced"


# ---------------------------------------------------------------------------
# Unknown is not zero, and neither is empty (D-RC1)
# ---------------------------------------------------------------------------


class TestUnknownIsNotZero:
    def test_an_all_unpriced_round_never_renders_a_zero_cost(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The failure mode this surface exists for. Every call went unpriced,
        so the round's true cost is unknown and greater than nothing — a
        ``$0.0000`` here would report the opposite."""
        _all_unpriced(tmp_path)
        figure, unpriced, _ = _lines(tmp_path)
        assert "$0.0000" not in figure
        assert "$" not in figure
        assert "none of the 2 calls could be priced" in figure
        assert unpriced.startswith("2 of 2 calls could not be priced and are excluded")

    def test_an_all_unpriced_round_still_shows_its_tokens(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Tokens are the provider's ground truth and do not depend on
        pricing, so they are the one number that survives the gap."""
        _all_unpriced(tmp_path)
        assert "Tokens: 200 in / 40 out" in _lines(tmp_path)[0]

    def test_an_empty_round_says_no_activity_not_unknown_price(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The other half of D-RC1: nothing has run, which is a different fact
        from "something ran and we cannot price it" and must not borrow its
        wording."""
        figure, unpriced, _ = _lines(tmp_path)
        assert figure == f"{COST_LABEL}, v0: {NO_CALLS}"
        assert "could not be priced" not in figure
        assert "could be priced" not in figure
        assert "$" not in figure
        assert unpriced == ""

    def test_the_two_empty_states_read_differently(
        self, tmp_path: pathlib.Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        other = tmp_path_factory.mktemp("unpriced")
        _all_unpriced(other)
        assert _lines(tmp_path)[0] != _lines(other)[0]

    def test_no_working_directory_reads_as_no_activity(self) -> None:
        assert round_cost_lines(None, None).figure == f"{COST_LABEL}, v0: {NO_CALLS}"

    def test_a_round_recorded_at_exactly_zero_still_shows_a_figure(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A genuinely free call — a priced model at a zero rate — is a known
        zero, not an unknown one, and is allowed to say ``$0.0000``."""
        _write(tmp_path, [_call("phaser", cost=0.0)])
        assert f"{COST_LABEL}, v0: $0.0000 ·" in _lines(tmp_path)[0]


# ---------------------------------------------------------------------------
# Where it renders, and how
# ---------------------------------------------------------------------------


class TestPlacement:
    def test_it_closes_the_project_view(self, tmp_path: pathlib.Path) -> None:
        """Produced, then to do, then spent — the mock's order."""
        ids = _ids(_agent_select_layout(_session(tmp_path)))
        assert ids.index("round-tree") < ids.index("agent-rows")
        assert ids.index("agent-rows") < ids.index("round-cost")

    def test_all_three_lines_are_mounted_in_every_state(
        self, tmp_path: pathlib.Path
    ) -> None:
        """An empty line two keeps its element, so the strip does not change
        height as a round goes from all-priced to partly unpriced — and so the
        callback always has all three targets to write into."""
        for fixture in sorted(_FIXTURES):
            root = tmp_path / fixture
            root.mkdir()
            _FIXTURES[fixture](root)
            ids = _ids(_round_cost(str(root), 0))
            assert ids == [
                "round-cost",
                "round-cost-line",
                "round-cost-unpriced",
                "round-cost-note",
            ], fixture

    def test_the_figures_are_monospace(self, tmp_path: pathlib.Path) -> None:
        """Consistent with the status bar and the round tree: a column of
        digits only lines up in a monospace face."""
        components = _by_id(_round_cost(str(tmp_path), 0))
        assert "mono" in components["round-cost-line"].className
        assert "mono" in components["round-cost-unpriced"].className
        # The disclaimer is prose, not a figure, and is deliberately not mono.
        assert "mono" not in components["round-cost-note"].className

    def test_it_does_not_disturb_the_chat_frames_cost_card(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The card's id belongs to the chat frame, where
        ``tests/test_cost_summary.py`` asserts its position."""
        _priced(tmp_path)
        assert "cost-summary-card" not in _ids(_agent_select_layout(_session(tmp_path)))

    def test_the_first_paint_matches_what_the_callback_writes(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Otherwise the strip would visibly change the instant the callback
        lands, which is what a first paint of placeholder text looks like."""
        _partly_unpriced(tmp_path)
        painted = [
            component.children
            for component in (
                _by_id(_round_cost(str(tmp_path), 0))[name]
                for name in (
                    "round-cost-line",
                    "round-cost-unpriced",
                    "round-cost-note",
                )
            )
        ]
        assert list(on_round_cost("round-cost", _session(tmp_path))) == painted


# ---------------------------------------------------------------------------
# Never cached
# ---------------------------------------------------------------------------


class TestRecomputedEveryRender:
    def test_a_finished_run_changes_the_figure_without_a_reload(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The goal this phase verifies: the strip is the working directory's
        current state, never a stale cached view. An agent that finishes
        mid-session appends to ``usage.json``, and the next render must show
        it."""
        session = _session(tmp_path)
        assert on_round_cost("round-cost", session)[0] == (
            f"{COST_LABEL}, v0: {NO_CALLS}"
        )

        _write(tmp_path, [_call("brainstormer", cost=0.02)])
        assert f"{COST_LABEL}, v0: $0.0200 ·" in on_round_cost("round-cost", session)[0]

        _write(tmp_path, [_call("phaser", cost=0.5)])
        assert f"{COST_LABEL}, v0: $0.5200 ·" in on_round_cost("round-cost", session)[0]

    def test_a_gap_appearing_mid_round_appears_on_the_strip(
        self, tmp_path: pathlib.Path
    ) -> None:
        session = _session(tmp_path)
        _write(tmp_path, [_call("brainstormer", cost=0.02)])
        assert on_round_cost("round-cost", session)[1] == "all 1 call priced"

        _write(tmp_path, [_call("agentifier", model="gpt-5-mini", cost=None)])
        assert on_round_cost("round-cost", session)[1] == (
            "1 of 2 calls could not be priced and is excluded: Agentifier (gpt-5-mini)"
        )

    def test_it_reads_the_sessions_pinned_round(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, [_call("phaser", cost=0.1)], version=0)
        _write(tmp_path, [_call("phaser", cost=0.9)], version=1)
        session = {**_session(tmp_path), "phase_version": 1}
        assert f"{COST_LABEL}, v1: $0.9000 ·" in on_round_cost("round-cost", session)[0]


# ---------------------------------------------------------------------------
# A malformed file is a normal state, not a crash
# ---------------------------------------------------------------------------


class TestMalformedUsage:
    def test_a_corrupt_usage_file_reads_as_no_activity(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The strip is one line on a page the developer needs — it must never
        be what takes the project view down."""
        version_dir = project_manager.ensure_version_dir(tmp_path, 0)
        (version_dir / "usage.json").write_text("{ not json", encoding="utf-8")
        assert _lines(tmp_path)[0] == f"{COST_LABEL}, v0: {NO_CALLS}"

    def test_a_history_of_junk_records_is_skipped(
        self, tmp_path: pathlib.Path
    ) -> None:
        record = project_manager.round_cost(tmp_path, 0)
        junk = {"phaser": {"history": ["x", None]}}
        assert project_manager.unpriced_calls(junk) == []
        assert project_manager.unpriced_calls("not a dict") == []
        assert record["unpriced"] == []
