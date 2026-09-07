"""The cost strip shown at the end of every user-visible agent run.

Four properties:

* the strip renders exactly when a run is complete — under the last message of
  a completed chat agent, on the Designer preview step — and never mid-stream,
  mid-run, without a project directory, or before any usage has been written;
* its numbers are the round's ``usage.json`` (the agent's own rollup, with
  sub-agents folded in), so they agree with ``spec4-usage``;
* pricing gaps are spelled out rather than shown as ``$0.0000``, and the
  estimate caveat is always part of the strip;
* it is the *same renderer* as the project view's round cost, not a second
  presentation that happens to agree — which is the mitigation this feature's
  "the completion cost strip fails to match the round-cost presentation"
  failure mode asks for, and is asserted directly in :class:`TestOneRenderer`.

The strip keeps the ``cost-summary-card`` id the retired
``_shared.cost_summary_card`` carried: the placement assertions below are
written against that id, and the contract is worth more than the tidier name.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from spec4 import project_manager
from spec4.app_constants import (
    STATE_AGENTIFIER_COMPLETE,
    STATE_DEPLOYER_COMPLETE,
    STATE_IN_PROGRESS,
    STATE_PHASES_COMPLETE,
    STATE_REVIEW_COMPLETE,
    STATE_STACK_COMPLETE,
    STATE_VISION_COMPLETE,
)
from spec4.layouts._chat import _chat_layout, _cost_summary
from spec4.layouts._round_cost import (
    COST_LABEL,
    RUN_SCOPE,
    CostFigures,
    cost_strip_lines,
    round_cost_lines,
    run_cost_lines,
    run_cost_strip,
)
from spec4.layouts._shared import _fmt_usd, price_source_note
from spec4.layouts.designer import _step6_content
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


def _card_text(node: Any) -> str:
    return "\n".join(_texts(node))


_COMPLETE: dict[str, tuple[str, str]] = {
    "code_scanner": ("code_scanner_state", STATE_REVIEW_COMPLETE),
    "brainstormer": ("brainstormer_state", STATE_VISION_COMPLETE),
    "agentifier": ("agentifier_state", STATE_AGENTIFIER_COMPLETE),
    "stack_advisor": ("stack_advisor_state", STATE_STACK_COMPLETE),
    "phaser": ("phaser_state", STATE_PHASES_COMPLETE),
    "deployer": ("deployer_state", STATE_DEPLOYER_COMPLETE),
}

_LABELS = {
    "code_scanner": "CodeScanner",
    "brainstormer": "Brainstormer",
    "agentifier": "Agentifier",
    "stack_advisor": "StackAdvisor",
    "phaser": "Phaser",
    "deployer": "Deployer",
}


def _session(
    working_dir: Path | None, agent: str, complete: bool = True
) -> dict[str, Any]:
    session = _default_session()
    session.update(
        {
            "phase": "chat",
            "active_agent": agent,
            "working_dir": str(working_dir) if working_dir else None,
            "phase_version": 0,
            "messages": [{"role": "assistant", "content": "done"}],
        }
    )
    key, value = _COMPLETE[agent]
    session[key] = value if complete else STATE_IN_PROGRESS
    # The run's own history, sitting on the artifact it just emitted: the
    # agent stamps the artifact's position when it completes, and the card
    # keys off that stamp matching the history length.
    session[f"{agent}_messages"] = [
        {"role": "user", "content": "seed"},
        {"role": "assistant", "content": "artifact"},
    ]
    session[f"{agent}_artifact_msg_count"] = 2
    return session


def _write_usage(root: Path, records: list[dict[str, Any]], version: int = 0) -> None:
    project_manager.save_usage(root, records, version)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


class TestFormat:
    def test_four_decimals_with_thousands(self) -> None:
        assert _fmt_usd(0.0123) == "$0.0123"
        assert _fmt_usd(1234.5) == "$1,234.5000"
        assert _fmt_usd(0) == "$0.0000"

    def test_none_and_non_numbers_read_as_not_available(self) -> None:
        assert _fmt_usd(None) == "not available"
        assert _fmt_usd(True) == "not available"
        assert _fmt_usd("0.5") == "not available"


# ---------------------------------------------------------------------------
# The strip's numbers come from usage.json
# ---------------------------------------------------------------------------

# The label every line one carries on this screen. The scope is the run rather
# than the round: the developer has just watched this agent finish and is
# deciding whether to continue, and the round's running total is one screen
# away on the project view, drawn by this same renderer.
_RUN_LABEL = f"{COST_LABEL}, {RUN_SCOPE}:"


class TestStripNumbers:
    def test_the_figure_is_the_agent_s_own_rollup(self, tmp_path: Path) -> None:
        """Sub-agents folded in, other agents left out.

        ``feature_speccer`` rolls into Brainstormer, so it is in the figure;
        CodeScanner ran in the same round and is not. The round's total —
        $0.0125 over three calls — belongs to the project view's strip, and
        showing it here as well was what let the two surfaces word the same
        fact two different ways.
        """
        _write_usage(
            tmp_path,
            [
                _call("brainstormer", cost=0.0021),
                _call("feature_speccer", cost=0.0004),  # rolls into brainstormer
                _call("code_scanner", cost=0.0100),
            ],
        )
        session = _session(tmp_path, "brainstormer")
        strip = run_cost_strip(str(tmp_path), session, "brainstormer")
        text = _card_text(strip)
        # _call() reports 100 in / 20 out per call.
        assert f"{_RUN_LABEL} $0.0025 · Tokens: 200 in / 40 out" in text
        assert "$0.0125" not in text
        assert price_source_note(
            project_manager.round_cost(tmp_path, 0)["cost_source"]
        ) in text
        assert strip.id == "cost-summary-card"

    def test_it_mounts_all_three_lines(self, tmp_path: Path) -> None:
        """The strip's own shape, and the ids it answers to.

        The root id is the one the retired card carried; the three line ids
        are the strip's own and deliberately *not* the project view's, whose
        lines ``on_round_cost`` writes into on a screen this one never shares.
        """
        _write_usage(tmp_path, [_call("brainstormer", cost=0.01)])
        session = _session(tmp_path, "brainstormer")
        assert _ids(run_cost_strip(str(tmp_path), session, "brainstormer")) == [
            "cost-summary-card",
            "run-cost-line",
            "run-cost-unpriced",
            "run-cost-note",
        ]

    def test_agrees_with_the_cli_rollup(self, tmp_path: Path) -> None:
        _write_usage(
            tmp_path,
            [
                _call("phaser", cost=0.5),
                _call("phaser_seam", cost=0.25),
                _call("deployer", cost=0.125),
            ],
        )
        data = project_manager.load_usage(tmp_path, 0)
        assert data is not None
        summary = project_manager.cost_summary(tmp_path, 0, "phaser")
        assert summary is not None
        phaser = data["agents"]["phaser"]
        assert summary["agent"]["cost_usd"] == phaser["computed_cost_usd"]
        assert summary["total"]["cost_usd"] == data["totals"]["computed_cost_usd"]
        assert summary["round"] == "v0"
        assert summary["cost_source"] == data["notes"]["computed_cost_source"]

    def test_agent_without_a_block_reads_as_zero_calls(self, tmp_path: Path) -> None:
        _write_usage(tmp_path, [_call("brainstormer", cost=0.01)])
        summary = project_manager.cost_summary(tmp_path, 0, "deployer")
        assert summary is not None
        assert summary["agent"] == {
            "cost_usd": None,
            "calls": 0,
            "calls_missing_cost": 0,
            "calls_missing_usage": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": None,
        }
        assert summary["total"]["cost_usd"] == 0.01

    def test_no_usage_file_means_no_summary(self, tmp_path: Path) -> None:
        assert project_manager.cost_summary(tmp_path, 0, "brainstormer") is None
        assert run_cost_strip(str(tmp_path), None, "brainstormer") is None
        assert run_cost_lines(str(tmp_path), None, "brainstormer") is None

    def test_no_working_directory_means_no_summary(self) -> None:
        assert run_cost_strip(None, None, "brainstormer") is None

    def test_reads_the_pinned_round(self, tmp_path: Path) -> None:
        _write_usage(tmp_path, [_call("brainstormer", cost=0.1)], version=0)
        _write_usage(tmp_path, [_call("brainstormer", cost=0.9)], version=1)
        session = _session(tmp_path, "brainstormer")
        session["phase_version"] = 1
        text = _card_text(run_cost_strip(str(tmp_path), session, "brainstormer"))
        assert f"{_RUN_LABEL} $0.9000" in text
        assert "$0.1000" not in text


# ---------------------------------------------------------------------------
# Token counts ride along with the cost
# ---------------------------------------------------------------------------


class TestTokenCounts:
    def test_thousands_separated_with_cache_reads(self, tmp_path: Path) -> None:
        _write_usage(
            tmp_path,
            [
                _call("phaser", prompt=12000, completion=1500, cached=4000, cost=0.5),
                _call("phaser_seam", prompt=800, completion=100, cost=0.01),
            ],
        )
        text = _card_text(
            run_cost_strip(str(tmp_path), _session(tmp_path, "phaser"), "phaser")
        )
        assert (
            f"{_RUN_LABEL} $0.5100 · Tokens: 12,800 in / 1,600 out (4,000 cached)"
            in text
        )

    def test_no_cache_reads_means_no_cached_note(self, tmp_path: Path) -> None:
        _write_usage(tmp_path, [_call("deployer", cost=0.01)])
        text = _card_text(
            run_cost_strip(str(tmp_path), _session(tmp_path, "deployer"), "deployer")
        )
        assert "Tokens: 100 in / 20 out" in text
        assert "cached" not in text

    def test_tokens_shown_even_when_nothing_could_be_priced(
        self, tmp_path: Path
    ) -> None:
        _write_usage(tmp_path, [_call("phaser", cost=None)])
        text = _card_text(
            run_cost_strip(str(tmp_path), _session(tmp_path, "phaser"), "phaser")
        )
        assert (
            f"{_RUN_LABEL} not available (none of the 1 calls could be priced) · "
            "Tokens: 100 in / 20 out"
        ) in text

    def test_missing_usage_flags_the_count_partial(self, tmp_path: Path) -> None:
        _write_usage(
            tmp_path,
            [
                _call("deployer", cost=0.03),
                _call(
                    "deployer", prompt=None, completion=None, cost=None, missing=True
                ),
            ],
        )
        text = _card_text(
            run_cost_strip(str(tmp_path), _session(tmp_path, "deployer"), "deployer")
        )
        assert "Tokens: 100 in / 20 out (partial)" in text


# ---------------------------------------------------------------------------
# Pricing gaps are said, not zeroed
# ---------------------------------------------------------------------------


class TestPricingGaps:
    def test_unpriced_calls_are_named_and_excluded(self, tmp_path: Path) -> None:
        _write_usage(
            tmp_path,
            [
                _call("stack_advisor", cost=0.02),
                _call("stack_advisor", cost=None),  # usage reported, no price map entry
            ],
        )
        text = _card_text(
            run_cost_strip(
                str(tmp_path),
                _session(tmp_path, "stack_advisor"),
                "stack_advisor",
            )
        )
        assert f"{_RUN_LABEL} $0.0200 · Tokens: 200 in / 40 out" in text
        # Named, not merely counted: the strip has a line for it, which is the
        # whole reason the round view and this one share a renderer.
        assert (
            "1 of 2 calls could not be priced and is excluded: "
            "StackAdvisor (gpt-4o-mini)"
        ) in text

    def test_calls_without_usage_count_as_unpriced_too(self, tmp_path: Path) -> None:
        _write_usage(
            tmp_path,
            [
                _call("deployer", cost=0.03),
                _call(
                    "deployer", prompt=None, completion=None, cost=None, missing=True
                ),
                _call("deployer", cost=None),
            ],
        )
        text = _card_text(
            run_cost_strip(str(tmp_path), _session(tmp_path, "deployer"), "deployer")
        )
        assert f"{_RUN_LABEL} $0.0300 ·" in text
        assert (
            "2 of 3 calls could not be priced and are excluded: "
            "Deployer (gpt-4o-mini)"
        ) in text

    def test_nothing_priced_reads_as_not_available(self, tmp_path: Path) -> None:
        _write_usage(tmp_path, [_call("phaser", cost=None), _call("phaser", cost=None)])
        text = _card_text(
            run_cost_strip(str(tmp_path), _session(tmp_path, "phaser"), "phaser")
        )
        assert (
            f"{_RUN_LABEL} not available (none of the 2 calls could be priced)"
        ) in text
        assert "$0.0000" not in text

    def test_rollup_counts_unpriced_calls(self) -> None:
        rollup = project_manager.summarize_usage(
            [
                _call("a", cost=0.1),
                _call("a", cost=None),
                _call("a", prompt=None, completion=None, cost=None, missing=True),
            ]
        )
        assert rollup["calls"] == 3
        assert rollup["calls_missing_cost"] == 1
        assert rollup["calls_missing_usage"] == 1
        totals = project_manager.usage_totals(
            {"a": rollup, "b": project_manager.summarize_usage([_call("b", cost=None)])}
        )
        assert totals["calls_missing_cost"] == 2
        assert totals["calls_missing_usage"] == 1
        assert totals["computed_cost_usd"] == 0.1


# ---------------------------------------------------------------------------
# Where the strip renders — chat agents
# ---------------------------------------------------------------------------


class TestChatPlacement:
    @pytest.mark.parametrize("agent", sorted(_COMPLETE))
    def test_completed_run_shows_the_strip(self, tmp_path: Path, agent: str) -> None:
        _write_usage(tmp_path, [_call(agent, cost=0.0042)])
        session = _session(tmp_path, agent)
        strip = _cost_summary(session)
        assert strip is not None
        text = _card_text(strip)
        assert f"{_RUN_LABEL} $0.0042 · Tokens: 100 in / 20 out" in text
        assert "all 1 call priced" in text
        assert "your provider's billing is authoritative" in text.lower()

    @pytest.mark.parametrize("agent", sorted(_COMPLETE))
    def test_run_in_progress_shows_nothing(self, tmp_path: Path, agent: str) -> None:
        _write_usage(tmp_path, [_call(agent, cost=0.0042)])
        assert _cost_summary(_session(tmp_path, agent, complete=False)) is None

    def test_hidden_while_a_stream_is_live(self, tmp_path: Path) -> None:
        _write_usage(tmp_path, [_call("brainstormer", cost=0.01)])
        session = _session(tmp_path, "brainstormer")
        session["_stream_id"] = "abc"
        assert _cost_summary(session) is None

    def test_hidden_without_a_project_directory(self) -> None:
        assert _cost_summary(_session(None, "brainstormer")) is None

    def test_hidden_before_any_usage_is_written(self, tmp_path: Path) -> None:
        assert _cost_summary(_session(tmp_path, "brainstormer")) is None

    def test_unknown_agent_shows_nothing(self, tmp_path: Path) -> None:
        _write_usage(tmp_path, [_call("designer", cost=0.01)])
        session = _session(tmp_path, "brainstormer")
        session["active_agent"] = "designer"
        assert _cost_summary(session) is None

    def test_the_agent_name_is_not_needed_to_read_it(self, tmp_path: Path) -> None:
        """The scope is "this run", not the agent's name.

        The pipeline indicator above the transcript already says which agent
        this is, and naming it again here would be the one thing that could
        not be shared with the round's strip.
        """
        _write_usage(tmp_path, [_call("brainstormer", cost=0.0042)])
        text = _card_text(_cost_summary(_session(tmp_path, "brainstormer")))
        assert RUN_SCOPE in text
        assert "Brainstormer" not in text

    def test_sits_between_the_transcript_and_the_action_row(
        self, tmp_path: Path
    ) -> None:
        _write_usage(tmp_path, [_call("brainstormer", cost=0.01)])
        session = _session(tmp_path, "brainstormer")
        session["_initial_turn_done"] = True
        ids = _ids(_chat_layout(session))
        assert "cost-summary-card" in ids
        assert ids.index("chat-scroll-area") < ids.index("cost-summary-card")
        # The action row's counter/download buttons come after the card.
        assert ids.index("cost-summary-card") < ids.index("chat-token-count")

    def test_exactly_one_strip(self, tmp_path: Path) -> None:
        _write_usage(tmp_path, [_call("brainstormer", cost=0.01)])
        session = _session(tmp_path, "brainstormer")
        session["_initial_turn_done"] = True
        assert _ids(_chat_layout(session)).count("cost-summary-card") == 1


# ---------------------------------------------------------------------------
# Modify runs — the strip marks the artifact turn, not every turn
# ---------------------------------------------------------------------------


def _chat_past_the_artifact(session: dict[str, Any], agent: str) -> None:
    """A conversational turn in a Modify run: the agent stays complete, the
    history grows past the stamped artifact."""
    session[f"{agent}_messages"].extend(
        [
            {"role": "user", "content": "please change X"},
            {"role": "assistant", "content": "sure — what about Y?"},
        ]
    )


class TestModifyRun:
    @pytest.mark.parametrize("agent", sorted(_COMPLETE))
    def test_chatting_past_the_artifact_hides_the_strip(
        self, tmp_path: Path, agent: str
    ) -> None:
        _write_usage(tmp_path, [_call(agent, cost=0.01)])
        session = _session(tmp_path, agent)
        assert _cost_summary(session) is not None
        _chat_past_the_artifact(session, agent)
        assert _cost_summary(session) is None

    @pytest.mark.parametrize("agent", sorted(_COMPLETE))
    def test_re_emitting_the_artifact_brings_it_back(
        self, tmp_path: Path, agent: str
    ) -> None:
        _write_usage(tmp_path, [_call(agent, cost=0.01)])
        session = _session(tmp_path, agent)
        _chat_past_the_artifact(session, agent)
        # The revised artifact lands as the last message and is stamped.
        session[f"{agent}_messages"].append(
            {"role": "assistant", "content": "revised artifact"}
        )
        session[f"{agent}_artifact_msg_count"] = len(session[f"{agent}_messages"])
        assert _cost_summary(session) is not None

    def test_no_stamp_means_no_strip(self, tmp_path: Path) -> None:
        """A completed state with no artifact position on record is not
        enough — the strip would otherwise sit on every turn."""
        _write_usage(tmp_path, [_call("brainstormer", cost=0.01)])
        session = _session(tmp_path, "brainstormer")
        session["brainstormer_artifact_msg_count"] = None
        assert _cost_summary(session) is None
        session["brainstormer_artifact_msg_count"] = True  # bool is not a count
        assert _cost_summary(session) is None

    def test_layout_carries_no_strip_mid_modify(self, tmp_path: Path) -> None:
        _write_usage(tmp_path, [_call("brainstormer", cost=0.01)])
        session = _session(tmp_path, "brainstormer")
        session["_initial_turn_done"] = True
        _chat_past_the_artifact(session, "brainstormer")
        assert "cost-summary-card" not in _ids(_chat_layout(session))


# ---------------------------------------------------------------------------
# Where the strip renders — Designer
# ---------------------------------------------------------------------------


class TestDesignerPlacement:
    def test_preview_step_shows_the_strip(self, tmp_path: Path) -> None:
        _write_usage(
            tmp_path, [_call("designer", cost=0.2), _call("brainstormer", cost=0.05)]
        )
        session = {"working_dir": str(tmp_path), "phase_version": 0}
        content = _step6_content({"mock_html": "<html></html>"}, session)
        ids = _ids(content)
        assert "cost-summary-card" in ids
        assert ids.index("mock-iframe") < ids.index("cost-summary-card")
        text = _card_text(content)
        # The Designer's own run, not the round's $0.2500.
        assert f"{_RUN_LABEL} $0.2000" in text
        assert "$0.2500" not in text
        assert "your provider's billing is authoritative" in text.lower()

    def test_preview_without_a_session_still_renders(self) -> None:
        content = _step6_content({"mock_html": "<html></html>"})
        ids = _ids(content)
        assert "mock-iframe" in ids
        assert "cost-summary-card" not in ids

    def test_preview_without_usage_omits_the_strip(self, tmp_path: Path) -> None:
        session = {"working_dir": str(tmp_path), "phase_version": 0}
        ids = _ids(_step6_content({"mock_html": ""}, session))
        assert "cost-summary-card" not in ids


# ---------------------------------------------------------------------------
# One renderer, two screens
# ---------------------------------------------------------------------------


class TestOneRenderer:
    """The chat frame's run cost and the project view's round cost are the
    same function's output.

    This is the mitigation the Chat Frame Register's "the completion cost strip
    fails to match the round-cost presentation" failure mode asks for, and the
    reason ``_shared.cost_summary_card`` was retired rather than kept in step
    by hand: two renderers that agree today are two renderers, and the first
    reworded line lands on only one of them.

    Asserted two ways, because either alone is weak. Same *output* for the same
    input is the property that matters and is checked first; same *function* is
    what stops a second implementation being written that happens to match the
    cases these tests cover.
    """

    def test_identical_usage_produces_identical_lines(self, tmp_path: Path) -> None:
        """Only the scope differs. Every other word — the estimate label, the
        figure, the token counts, the named unpriced calls, the caveat — is
        the same string on both screens."""
        _write_usage(
            tmp_path,
            [
                _call("brainstormer", cost=0.02),
                _call("agentifier", model="gpt-5-mini", cost=None),
            ],
        )
        record = project_manager.round_cost(tmp_path, 0)
        figures = (record["total"], record["unpriced"], record["cost_source"])
        run = cost_strip_lines(CostFigures(RUN_SCOPE, *figures))
        rounded = cost_strip_lines(CostFigures("v0", *figures))
        assert run.figure.replace(RUN_SCOPE, "v0") == rounded.figure
        assert run.unpriced == rounded.unpriced
        assert run.note == rounded.note
        # The property is not vacuous: line two really does name a gap here.
        assert "Agentifier (gpt-5-mini)" in run.unpriced

    def test_both_surfaces_call_the_one_renderer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Not "they agree", but "there is only one of them".

        Replacing ``cost_strip_lines`` has to change both screens' wording, or
        one of them is wording its lines somewhere else.
        """
        _write_usage(tmp_path, [_call("brainstormer", cost=0.02)])
        # By `sys.modules`, not `import ... as`: `spec4.layouts` re-exports the
        # `_round_cost` *function*, which shadows the submodule of that name on
        # the package.
        module = sys.modules["spec4.layouts._round_cost"]

        monkeypatch.setattr(
            module,
            "cost_strip_lines",
            lambda figures: module.RoundCost(f"stub {figures.scope}", "", ""),
        )
        assert round_cost_lines(str(tmp_path), 0).figure == "stub v0"
        run = run_cost_lines(str(tmp_path), None, "brainstormer")
        assert run is not None
        assert run.figure == f"stub {RUN_SCOPE}"

    def test_the_estimate_label_and_the_gap_rules_survive_the_move(
        self, tmp_path: Path
    ) -> None:
        """The three rules that were easy to lose in the move between
        renderers, asserted on the run strip specifically: every state is
        labelled an estimate, an unpriced call is named, and an unknown cost
        is never ``$0.0000``."""
        _write_usage(
            tmp_path,
            [
                _call("phaser", model="gpt-5-mini", cost=None),
                _call("phaser", model="gpt-5-mini", cost=None),
            ],
        )
        lines = run_cost_lines(str(tmp_path), _session(tmp_path, "phaser"), "phaser")
        assert lines is not None
        assert lines.figure.startswith(f"{COST_LABEL}, {RUN_SCOPE}: ")
        assert "$" not in lines.figure
        assert lines.unpriced == (
            "2 of 2 calls could not be priced and are excluded: Phaser (gpt-5-mini)"
        )
        assert lines.note.startswith("Estimates from ")

    def test_the_run_s_gaps_are_the_run_s_own(self, tmp_path: Path) -> None:
        """Line two explains line one. A round-wide list beside an agent's
        figure would name calls that are not in the figure it sits under."""
        _write_usage(
            tmp_path,
            [
                _call("brainstormer", cost=0.02),
                _call("agentifier", model="gpt-5-mini", cost=None),
            ],
        )
        lines = run_cost_lines(
            str(tmp_path), _session(tmp_path, "brainstormer"), "brainstormer"
        )
        assert lines is not None
        assert lines.unpriced == "all 1 call priced"
        assert "Agentifier" not in lines.unpriced
