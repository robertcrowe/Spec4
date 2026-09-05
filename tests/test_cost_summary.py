"""The estimated-cost card shown at the end of every user-visible agent run.

Three properties:

* the card renders exactly when a run is complete — under the last message of
  a completed chat agent, on the Designer preview step — and never mid-stream,
  mid-run, without a project directory, or before any usage has been written;
* its numbers are the round's ``usage.json`` (the agent's rollup and the
  round total), so they agree with ``spec4-usage``;
* pricing gaps are spelled out rather than shown as ``$0.0000``, and the
  disclaimer is always part of the card.
"""

from __future__ import annotations

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
from spec4.layouts._shared import COST_DISCLAIMER, _fmt_usd, cost_summary_card
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
# The card's numbers come from usage.json
# ---------------------------------------------------------------------------


class TestCardNumbers:
    def test_agent_cost_and_running_total(self, tmp_path: Path) -> None:
        _write_usage(
            tmp_path,
            [
                _call("brainstormer", cost=0.0021),
                _call("feature_speccer", cost=0.0004),  # rolls into brainstormer
                _call("code_scanner", cost=0.0100),
            ],
        )
        session = _session(tmp_path, "brainstormer")
        card = cost_summary_card(
            str(tmp_path), session, "brainstormer", "Brainstormer"
        )
        text = _card_text(card)
        # _call() reports 100 in / 20 out per call.
        assert "Brainstormer run: $0.0025 · Tokens: 200 in / 40 out" in text
        assert "Running total for v0: $0.0125 · Tokens: 300 in / 60 out" in text
        assert COST_DISCLAIMER in text
        assert card.id == "cost-summary-card"

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
        assert (
            cost_summary_card(str(tmp_path), None, "brainstormer", "Brainstormer")
            is None
        )

    def test_reads_the_pinned_round(self, tmp_path: Path) -> None:
        _write_usage(tmp_path, [_call("brainstormer", cost=0.1)], version=0)
        _write_usage(tmp_path, [_call("brainstormer", cost=0.9)], version=1)
        session = _session(tmp_path, "brainstormer")
        session["phase_version"] = 1
        text = _card_text(
            cost_summary_card(str(tmp_path), session, "brainstormer", "Brainstormer")
        )
        assert "Brainstormer run: $0.9000" in text
        assert "Running total for v1: $0.9000" in text


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
            cost_summary_card(
                str(tmp_path), _session(tmp_path, "phaser"), "phaser", "Phaser"
            )
        )
        assert (
            "Phaser run: $0.5100 · Tokens: 12,800 in / 1,600 out (4,000 cached)"
            in text
        )

    def test_no_cache_reads_means_no_cached_note(self, tmp_path: Path) -> None:
        _write_usage(tmp_path, [_call("deployer", cost=0.01)])
        text = _card_text(
            cost_summary_card(
                str(tmp_path), _session(tmp_path, "deployer"), "deployer", "Deployer"
            )
        )
        assert "Tokens: 100 in / 20 out" in text
        assert "cached" not in text

    def test_tokens_shown_even_when_nothing_could_be_priced(
        self, tmp_path: Path
    ) -> None:
        _write_usage(tmp_path, [_call("phaser", cost=None)])
        text = _card_text(
            cost_summary_card(
                str(tmp_path), _session(tmp_path, "phaser"), "phaser", "Phaser"
            )
        )
        assert (
            "Phaser run: not available (none of the 1 calls could be priced) · "
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
            cost_summary_card(
                str(tmp_path), _session(tmp_path, "deployer"), "deployer", "Deployer"
            )
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
            cost_summary_card(
                str(tmp_path),
                _session(tmp_path, "stack_advisor"),
                "stack_advisor",
                "StackAdvisor",
            )
        )
        note = "(1 of 2 calls could not be priced and is excluded)"
        assert f"StackAdvisor run: $0.0200 {note}" in text
        assert f"Running total for v0: $0.0200 {note}" in text

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
            cost_summary_card(
                str(tmp_path), _session(tmp_path, "deployer"), "deployer", "Deployer"
            )
        )
        note = "(2 of 3 calls could not be priced and are excluded)"
        assert f"Deployer run: $0.0300 {note}" in text

    def test_nothing_priced_reads_as_not_available(self, tmp_path: Path) -> None:
        _write_usage(tmp_path, [_call("phaser", cost=None), _call("phaser", cost=None)])
        text = _card_text(
            cost_summary_card(
                str(tmp_path), _session(tmp_path, "phaser"), "phaser", "Phaser"
            )
        )
        assert (
            "Phaser run: not available (none of the 2 calls could be priced)" in text
        )
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
# Where the card renders — chat agents
# ---------------------------------------------------------------------------


class TestChatPlacement:
    @pytest.mark.parametrize("agent", sorted(_COMPLETE))
    def test_completed_run_shows_the_card(self, tmp_path: Path, agent: str) -> None:
        _write_usage(tmp_path, [_call(agent, cost=0.0042)])
        session = _session(tmp_path, agent)
        card = _cost_summary(session)
        assert card is not None
        text = _card_text(card)
        assert f"{_LABELS[agent]} run: $0.0042" in text
        assert "Running total for v0: $0.0042" in text
        assert COST_DISCLAIMER in text

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

    def test_exactly_one_card(self, tmp_path: Path) -> None:
        _write_usage(tmp_path, [_call("brainstormer", cost=0.01)])
        session = _session(tmp_path, "brainstormer")
        session["_initial_turn_done"] = True
        assert _ids(_chat_layout(session)).count("cost-summary-card") == 1


# ---------------------------------------------------------------------------
# Modify runs — the card marks the artifact turn, not every turn
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
    def test_chatting_past_the_artifact_hides_the_card(
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

    def test_no_stamp_means_no_card(self, tmp_path: Path) -> None:
        """A completed state with no artifact position on record is not
        enough — the card would otherwise sit on every turn."""
        _write_usage(tmp_path, [_call("brainstormer", cost=0.01)])
        session = _session(tmp_path, "brainstormer")
        session["brainstormer_artifact_msg_count"] = None
        assert _cost_summary(session) is None
        session["brainstormer_artifact_msg_count"] = True  # bool is not a count
        assert _cost_summary(session) is None

    def test_layout_carries_no_card_mid_modify(self, tmp_path: Path) -> None:
        _write_usage(tmp_path, [_call("brainstormer", cost=0.01)])
        session = _session(tmp_path, "brainstormer")
        session["_initial_turn_done"] = True
        _chat_past_the_artifact(session, "brainstormer")
        assert "cost-summary-card" not in _ids(_chat_layout(session))


# ---------------------------------------------------------------------------
# Where the card renders — Designer
# ---------------------------------------------------------------------------


class TestDesignerPlacement:
    def test_preview_step_shows_the_card(self, tmp_path: Path) -> None:
        _write_usage(
            tmp_path, [_call("designer", cost=0.2), _call("brainstormer", cost=0.05)]
        )
        session = {"working_dir": str(tmp_path), "phase_version": 0}
        content = _step6_content({"mock_html": "<html></html>"}, session)
        ids = _ids(content)
        assert "cost-summary-card" in ids
        assert ids.index("mock-iframe") < ids.index("cost-summary-card")
        text = _card_text(content)
        assert "Designer run: $0.2000" in text
        assert "Running total for v0: $0.2500" in text
        assert COST_DISCLAIMER in text

    def test_preview_without_a_session_still_renders(self) -> None:
        content = _step6_content({"mock_html": "<html></html>"})
        ids = _ids(content)
        assert "mock-iframe" in ids
        assert "cost-summary-card" not in ids

    def test_preview_without_usage_omits_the_card(self, tmp_path: Path) -> None:
        session = {"working_dir": str(tmp_path), "phase_version": 0}
        ids = _ids(_step6_content({"mock_html": ""}, session))
        assert "cost-summary-card" not in ids
