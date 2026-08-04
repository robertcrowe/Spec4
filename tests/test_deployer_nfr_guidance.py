"""Tests for Deployer's non-functional goal guidance (D-DE8).

The prompt previously had no concept of non-functional goals at all, so the
deployment-relevant ones — latency, offline, zero-downtime, scale, durability,
confidentiality — evaporated between the vision and the plan even though the
stack had already recorded them.

The guidance added here does three things, and each is asserted below because
each is a distinct failure if it goes missing:

* it tells Deployer the goals are *requirements on the deployment*, to be
  threaded into the decision that they bear on rather than answered once as a
  separate topic;
* it gives a worked taxonomy in both directions, because the split is genuinely
  non-obvious in prose — "persist reliably across restarts" is a deployment
  concern and "citations are verifiable" is not, and nothing about their
  phrasing says so;
* it forbids claiming that infrastructure satisfies a goal it does not.

That last one guards against a regression this lever could itself cause.
Measured plans already decline to invent infrastructure for behavioural goals;
an instruction to "thread the non-functional goals" is exactly what would push a
model into claiming a CDN makes citations verifiable. The honesty constraint
keeps the existing good behaviour while the threading is added.
"""

from __future__ import annotations

from spec4.agents.deployer import SYSTEM_PROMPT as DEPLOYER_PROMPT


class TestGoalsAreFramedAsRequirements:
    def test_prompt_references_the_non_functional_goals(self) -> None:
        assert "non-functional goals" in DEPLOYER_PROMPT.lower()

    def test_goals_are_framed_as_requirements_not_commentary(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "requirements on this deployment" in low

    def test_goals_are_threaded_into_the_decision_they_bear_on(self) -> None:
        """Threading beats an appendix: the decision says why it was made."""
        low = DEPLOYER_PROMPT.lower()
        assert "say so in the section where you record that decision" in low


class TestDeploymentRelevantTaxonomy:
    def test_latency_maps_to_region_and_caching(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "latency" in low
        assert "region choice" in low

    def test_offline_maps_to_static_hosting_and_service_worker(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "working offline" in low
        assert "service worker" in low

    def test_uninterrupted_updates_map_to_zero_downtime_deploys(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "without interrupting users" in low
        assert "zero-downtime" in low

    def test_scale_maps_to_autoscaling(self) -> None:
        assert "autoscaling" in DEPLOYER_PROMPT.lower()

    def test_durability_maps_to_backup_policy(self) -> None:
        assert "backup policy" in DEPLOYER_PROMPT.lower()

    def test_confidentiality_maps_to_isolation_and_secrets(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "confidentiality" in low
        assert "network isolation" in low


class TestFeatureBehaviouralGoalsAreLeftAlone:
    def test_behavioural_examples_are_named(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        for example in ("answer correctness", "citation verifiability", "refusal"):
            assert example in low

    def test_behavioural_goals_are_attributed_to_the_code(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "come from the code the agent writes, not from infrastructure" in low


class TestHonestyConstraint:
    def test_fabricating_an_infrastructure_claim_is_forbidden(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "never write that infrastructure satisfies a goal it does not" in low

    def test_the_forbidden_case_is_made_concrete(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "no hosting choice makes a citation verifiable" in low

    def test_unclaimed_goals_may_still_be_deployment_relevant(self) -> None:
        """An absent ``satisfies_nfr`` is not permission to ignore the goal."""
        low = DEPLOYER_PROMPT.lower()
        assert "no stack component claims may still be deployment-relevant" in low

    def test_classification_is_recorded_so_nothing_is_dropped(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "silently dropped" in low


class TestNotesSectionCarriesTheRecord:
    def test_notes_spec_asks_for_the_goal_record(self) -> None:
        notes = DEPLOYER_PROMPT.split("## Notes")[1]
        low = notes.lower()
        assert "non-functional goals" in low
        assert "coding agent's to satisfy" in low
