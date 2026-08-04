"""Tests for Deployer's environment sourcing and stack semantics (D-DE9).

Three gaps this covers, each measured on drawn plans before the change:

**The Target schema could not hold what the stack declared.** Every corpus stack
declares two deployment surfaces — a static frontend and an API — while the
output structure had one Type/Provider/Service/Region block and no exposure
fields at all. Drawn plans collapsed both surfaces into one, and one of them
improvised a ``Services:`` key that was never in the spec, which is the tell for
a schema gap rather than a model defect. Transport reached no plan in the corpus
because there was nowhere to put it.

**Environment was derived from the wrong end.** The step read the code review
first and otherwise said only "derive from the stack", naming none of the phase
``configurations``, auth ``credentials_env``, or provider
``credentials_env``/``endpoint_env`` now in context. Measured coverage of
phase-declared variables was 2/4, 3/8, and 11/29.

**Absences were not stated as decisions.** Roadmap entries, ``exposure`` as
literal configuration, and the trustworthy negatives (no auth means no accounts;
no integrations means no external services) had no expression in the prompt, so
nothing stopped Deployer re-asking a settled question.

Brownfield precedence is deliberately preserved: the code review still comes
first where it exists, because it reflects what the deployed code actually reads.
"""

from __future__ import annotations

from spec4.agents.deployer import SYSTEM_PROMPT as DEPLOYER_PROMPT


class TestTargetSchemaHoldsEverySurface:
    def test_target_is_per_surface(self) -> None:
        target = DEPLOYER_PROMPT.split("## Target")[1].split("## Containerization")[0]
        assert "One block per deployment surface" in target

    def test_frontend_and_api_are_named_as_two_surfaces(self) -> None:
        """The cardinality mismatch that collapsed both into one block."""
        target = DEPLOYER_PROMPT.split("## Target")[1].split("## Containerization")[0]
        assert "two" in target.lower()
        assert "surfaces, not one" in target.lower()

    def test_transport_and_cors_have_fields(self) -> None:
        target = DEPLOYER_PROMPT.split("## Target")[1].split("## Containerization")[0]
        assert "**Transport:**" in target
        assert "**CORS:**" in target

    def test_step_one_carries_declared_hosting_and_exposure(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "carry each" in low
        assert "hosting, build, and `exposure`" in low


class TestEnvironmentIsAssembledNotAsked:
    def test_variables_are_assembled_before_asking(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "assemble the required variables from every source" in low
        assert "rather than asking" in low

    def test_phase_configurations_are_a_named_source(self) -> None:
        assert "`tech_stack_spec.configurations`" in DEPLOYER_PROMPT

    def test_auth_and_provider_credentials_are_named_sources(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "`credentials_env`" in low
        assert "`endpoint_env`" in low

    def test_brownfield_code_review_keeps_precedence(self) -> None:
        """It reflects what the deployed code actually reads (D-DE9d)."""
        low = DEPLOYER_PROMPT.lower()
        assert "`env_vars` list when present" in low
        assert "so start there" in low

    def test_variable_names_only_is_preserved(self) -> None:
        assert "NAMES only — never values" in DEPLOYER_PROMPT


class TestSettledDecisionsAreNotReopened:
    def test_roadmap_entries_are_recorded_not_provisioned(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "`optional` or `deferred` is roadmap" in low
        assert "do not provision, configure, or build it" in low

    def test_exposure_is_framed_as_literal_configuration(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "literal configuration" in low
        assert "not advice to weigh" in low

    def test_absent_auth_means_no_accounts_and_no_question(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "no user accounts" in low
        assert "ask the developer to choose one" in low

    def test_absent_integrations_means_no_external_services(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "no third-party services to configure" in low

    def test_re_asking_a_settled_question_is_called_out(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "already answered wastes the developer's turn" in low


class TestEarlierGuidanceSurvives:
    """D-DE8's goal guidance and the interaction rules must not be displaced."""

    def test_non_functional_goal_guidance_is_intact(self) -> None:
        low = DEPLOYER_PROMPT.lower()
        assert "non-functional goals" in low
        assert "never write that infrastructure satisfies a goal it does not" in low

    def test_one_question_per_turn_is_intact(self) -> None:
        assert "one question per turn" in DEPLOYER_PROMPT.lower()
