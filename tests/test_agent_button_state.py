"""Behavioral tests for the /agents page button-state resolver.

Each agent's button reflects the artifacts in the active ``.spec4/v{N}/``
directory. States: start / modify / needs_update / not_ready / required.
Mtimes are set explicitly so the freshness-chain ordering is unambiguous.
"""

import os
from pathlib import Path

import pytest

from spec4 import project_manager as pm
from spec4.project_manager import (
    AGENT_BTN_MODIFY,
    AGENT_BTN_NEEDS_UPDATE,
    AGENT_BTN_NOT_READY,
    AGENT_BTN_REQUIRED,
    AGENT_BTN_START,
    agent_button_state,
)

# Canonical pipeline order with strictly increasing reference mtimes for a
# fully-populated, healthy round.
_HEALTHY = {
    "code_review.json": 100,
    "vision.json": 101,
    "ai_features.json": 102,
    "design/mock.html": 103,
    "stack.json": 104,
    "phases/phase1.md": 105,
    "deployment-plan.md": 106,
}


def _write(version_dir: Path, rel: str, mtime: float) -> None:
    path = version_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def _make_round(tmp_path: Path, version: int, files: dict[str, float]) -> Path:
    """Create ``.spec4/v{version}/`` with the given {rel: mtime} artifacts."""
    vdir = tmp_path / ".spec4" / f"v{version}"
    vdir.mkdir(parents=True, exist_ok=True)
    for rel, mtime in files.items():
        _write(vdir, rel, mtime)
    return vdir


# ---------------------------------------------------------------------------
# Empty / greenfield start
# ---------------------------------------------------------------------------


def test_empty_project_codescanner_and_brainstormer_start(tmp_path):
    # No .spec4 at all.
    assert agent_button_state(tmp_path, "code_scanner") == AGENT_BTN_START
    assert agent_button_state(tmp_path, "brainstormer") == AGENT_BTN_START


def test_empty_project_downstream_not_ready(tmp_path):
    for agent in ("agentifier", "designer", "stack_advisor", "phaser", "deployer"):
        assert agent_button_state(tmp_path, agent) == AGENT_BTN_NOT_READY


def test_vision_only_gates(tmp_path):
    _make_round(tmp_path, 0, {"vision.json": 101})
    assert agent_button_state(tmp_path, "brainstormer") == AGENT_BTN_MODIFY
    # vision present -> these become runnable with no output yet
    assert agent_button_state(tmp_path, "agentifier") == AGENT_BTN_START
    assert agent_button_state(tmp_path, "designer") == AGENT_BTN_START
    assert agent_button_state(tmp_path, "stack_advisor") == AGENT_BTN_START
    # phaser still needs stack
    assert agent_button_state(tmp_path, "phaser") == AGENT_BTN_NOT_READY
    # deployer still needs phases
    assert agent_button_state(tmp_path, "deployer") == AGENT_BTN_NOT_READY


# ---------------------------------------------------------------------------
# Healthy, fully populated round -> every agent Modify
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "agent",
    [
        "code_scanner",
        "brainstormer",
        "agentifier",
        "designer",
        "stack_advisor",
        "phaser",
        "deployer",
    ],
)
def test_healthy_round_all_modify(tmp_path, agent):
    _make_round(tmp_path, 0, _HEALTHY)
    assert agent_button_state(tmp_path, agent) == AGENT_BTN_MODIFY


# ---------------------------------------------------------------------------
# Needs Update — output older than its nearest input, chain otherwise in order
# ---------------------------------------------------------------------------


def test_deployer_needs_update_when_phases_regenerated(tmp_path):
    files = dict(_HEALTHY)
    files["phases/phase1.md"] = 200  # regenerated after deployment-plan (106)
    _make_round(tmp_path, 0, files)
    assert agent_button_state(tmp_path, "deployer") == AGENT_BTN_NEEDS_UPDATE


def test_brainstormer_needs_update_when_code_review_newer(tmp_path):
    # Brainstormer's only (optional) input is code_review; make it newer.
    _make_round(tmp_path, 0, {"code_review.json": 200, "vision.json": 101})
    assert agent_button_state(tmp_path, "brainstormer") == AGENT_BTN_NEEDS_UPDATE


# ---------------------------------------------------------------------------
# Not Ready — input chain internally out of order
# ---------------------------------------------------------------------------


def test_downstream_not_ready_when_chain_out_of_order(tmp_path):
    files = dict(_HEALTHY)
    files["stack.json"] = 300  # stack now newer than phases (its downstream)
    _make_round(tmp_path, 0, files)
    # deployer's chain ai_features<mock<stack<phases is now violated at stack
    assert agent_button_state(tmp_path, "deployer") == AGENT_BTN_NOT_READY


def test_vision_regenerated_cascades(tmp_path):
    files = dict(_HEALTHY)
    files["vision.json"] = 500  # newer than everything downstream
    _make_round(tmp_path, 0, files)
    # Agentifier's nearest input is the freshened vision -> its output is stale
    assert agent_button_state(tmp_path, "agentifier") == AGENT_BTN_NEEDS_UPDATE
    # Stack/Phaser chains now have vision out of order -> blocked
    assert agent_button_state(tmp_path, "stack_advisor") == AGENT_BTN_NOT_READY
    assert agent_button_state(tmp_path, "phaser") == AGENT_BTN_NOT_READY


# ---------------------------------------------------------------------------
# Start — required inputs present, no output yet, chain in order
# ---------------------------------------------------------------------------


def test_phaser_start_when_stack_present_no_phases(tmp_path):
    _make_round(
        tmp_path,
        0,
        {"vision.json": 101, "ai_features.json": 102, "stack.json": 104},
    )
    assert agent_button_state(tmp_path, "phaser") == AGENT_BTN_START


# ---------------------------------------------------------------------------
# Optional inputs absent never block
# ---------------------------------------------------------------------------


def test_optional_inputs_absent_do_not_block(tmp_path):
    # No code_review, no mock, no ai_features anywhere.
    _make_round(tmp_path, 0, {"vision.json": 101, "stack.json": 104})
    assert agent_button_state(tmp_path, "brainstormer") == AGENT_BTN_MODIFY
    assert agent_button_state(tmp_path, "stack_advisor") == AGENT_BTN_MODIFY
    assert agent_button_state(tmp_path, "phaser") == AGENT_BTN_START


def test_tie_mtime_counts_as_modify(tmp_path):
    # Output mtime equal to nearest input -> not older -> Modify.
    _make_round(tmp_path, 0, {"vision.json": 101, "stack.json": 101})
    # stack_advisor: nearest input vision(101), output stack(101) -> modify
    assert agent_button_state(tmp_path, "stack_advisor") == AGENT_BTN_MODIFY


def test_equal_upstream_mtimes_are_in_order(tmp_path):
    # Artifacts written in one persist pass can share an mtime; equal upstream
    # values must read as in-order, not as a broken chain.
    _make_round(
        tmp_path,
        0,
        {
            "code_review.json": 100,
            "vision.json": 100,
            "ai_features.json": 100,
            "stack.json": 100,
        },
    )
    # phaser chain code_review=vision=ai_features=stack all equal -> in order,
    # output phases absent -> Start (not Not Ready).
    assert agent_button_state(tmp_path, "phaser") == AGENT_BTN_START


# ---------------------------------------------------------------------------
# CodeScanner has no inputs
# ---------------------------------------------------------------------------


def test_codescanner_start_then_modify(tmp_path):
    _make_round(tmp_path, 0, {"vision.json": 101})
    assert agent_button_state(tmp_path, "code_scanner") == AGENT_BTN_START
    _write(tmp_path / ".spec4" / "v0", "code_review.json", 99)
    assert agent_button_state(tmp_path, "code_scanner") == AGENT_BTN_MODIFY


# ---------------------------------------------------------------------------
# Brownfield new-round gate — highest version implemented
# ---------------------------------------------------------------------------


def test_brownfield_new_round_requires_codescanner(tmp_path):
    _make_round(tmp_path, 0, _HEALTHY)
    (tmp_path / ".spec4" / "v0" / "IMPLEMENTED").write_text("", encoding="utf-8")
    assert pm.brownfield_new_round_pending(tmp_path) is True
    assert agent_button_state(tmp_path, "code_scanner") == AGENT_BTN_REQUIRED
    for agent in (
        "brainstormer",
        "agentifier",
        "designer",
        "stack_advisor",
        "phaser",
        "deployer",
    ):
        assert agent_button_state(tmp_path, agent) == AGENT_BTN_NOT_READY


def test_unimplemented_round_not_pending(tmp_path):
    _make_round(tmp_path, 0, _HEALTHY)  # no IMPLEMENTED marker
    assert pm.brownfield_new_round_pending(tmp_path) is False
    assert agent_button_state(tmp_path, "code_scanner") == AGENT_BTN_MODIFY


def test_active_round_is_highest_unimplemented(tmp_path):
    # v0 implemented, v1 in progress -> evaluate against v1, not the gate.
    _make_round(tmp_path, 0, _HEALTHY)
    (tmp_path / ".spec4" / "v0" / "IMPLEMENTED").write_text("", encoding="utf-8")
    _make_round(tmp_path, 1, {"code_review.json": 300, "vision.json": 301})
    assert pm.brownfield_new_round_pending(tmp_path) is False
    assert agent_button_state(tmp_path, "code_scanner") == AGENT_BTN_MODIFY
    assert agent_button_state(tmp_path, "brainstormer") == AGENT_BTN_MODIFY
    assert agent_button_state(tmp_path, "agentifier") == AGENT_BTN_START


# ---------------------------------------------------------------------------
# No working directory yet -> empty-project semantics, never crashes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wd", [None, ""])
def test_no_working_dir_is_empty_project(wd):
    assert pm.brownfield_new_round_pending(wd) is False
    assert agent_button_state(wd, "code_scanner") == AGENT_BTN_START
    assert agent_button_state(wd, "brainstormer") == AGENT_BTN_START
    assert agent_button_state(wd, "phaser") == AGENT_BTN_NOT_READY
