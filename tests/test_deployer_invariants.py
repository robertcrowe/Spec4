"""Tests for Deployer's invariants after the context and prompt work (D-DE10).

Five context channels and two prompt levers were added to Deployer. This file
guards the things that were load-bearing *before* that work and had to survive
it, plus the one registry entry the new consumption required.

**Seed threading.** Deployer builds its opening context in three branches — a
prior plan exists, a revision round, and greenfield. Every channel has to reach
all three in the same order; a channel added to two of them is a silent hole
that only shows up in whichever flow was not exercised.

**Revision scoping.** Revision mode carries the prior plan forward and scopes to
the delta. The environment step now assembles a union of variables from every
source in context, which is exactly the kind of instruction that could push a
revision into re-deriving a settled plan, so it carries an explicit revision
qualifier.

**Registry.** Deployer reads ``feature_specs.json`` for the project's
non-functional goals, so an edit to it can invalidate a deployment plan and must
mark the plan stale.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from spec4 import project_manager
from spec4.agents import deployer
from spec4.agents.deployer import SYSTEM_PROMPT as DEPLOYER_PROMPT


class TestSeedThreadingAcrossBranches:
    """Every channel reaches all three seed branches, in one order."""

    _COMPOSITION = (
        '{stack_block}{nfr_block}{phases_block}'
        '{existing_infra_block}{ai_features_block}'
    )

    def _source(self) -> str:
        return Path(deployer.__file__).read_text(encoding="utf-8")

    def test_all_three_branches_share_one_composition(self) -> None:
        assert self._source().count(self._COMPOSITION) == 3

    def test_no_branch_omits_a_channel(self) -> None:
        """A partial composition would mean a channel reaches only some flows."""
        src = self._source()
        for fragment in (
            "{stack_block}",
            "{nfr_block}",
            "{phases_block}",
            "{existing_infra_block}",
            "{ai_features_block}",
        ):
            assert src.count(fragment) >= 3


class TestRevisionScoping:
    def test_environment_step_carries_a_revision_qualifier(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "in revision mode, assemble the same union" in low
        assert "present only what this revision adds" in low

    def test_revision_mode_still_forbids_re_deriving(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "do not re-derive the whole deployment plan" in low

    def test_revision_mode_still_carries_the_prior_plan_forward(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "established baseline" in low
        assert "carrying the established sections forward unchanged" in low


class TestStalenessRegistry:
    def test_feature_specs_is_a_deployer_input(self) -> None:
        _, inputs = project_manager._STALE_DEPENDENCIES["deployer"]
        assert ("feature specs", "feature_specs.json") in inputs

    def test_editing_feature_specs_marks_the_plan_stale(
        self, tmp_path: Any
    ) -> None:
        wd = str(tmp_path)
        project_manager.save_phases(
            wd, [{"phase_number": 1, "phase_title": "Steel"}], 0
        )
        project_manager.save_feature_specs(wd, {"nfr_goals": ["Fast"]}, 0)
        time.sleep(0.02)
        project_manager.save_deployment_plan(wd, "# Deployment Plan\n", 0)
        assert project_manager.detect_stale_inputs(wd, "deployer") == {}

        time.sleep(0.02)
        project_manager.save_feature_specs(
            wd, {"nfr_goals": ["Fast", "Offline"]}, 0
        )
        assert "feature specs" in project_manager.detect_stale_inputs(wd, "deployer")

    def test_design_manifest_is_not_a_deployer_input(self) -> None:
        """Deployer never reads the manifest; its dependency is transitive
        through StackAdvisor, so a direct entry would mark the plan stale on a
        file it does not consume."""
        _, inputs = project_manager._STALE_DEPENDENCIES["deployer"]
        assert all(rel != "design/manifest.json" for _, rel in inputs)

    def test_feature_specs_does_not_gate_deployer_to_not_ready(self) -> None:
        """Freshness-only: Deployer must still run without feature specs."""
        required = project_manager._REQUIRED_INPUTS.get("deployer", [])
        assert "feature_specs.json" not in required
