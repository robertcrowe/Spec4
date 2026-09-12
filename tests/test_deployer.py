"""Tests for :mod:`spec4.agents.deployer`.

Split out of ``tests/test_agents.py`` by source module, with every class unchanged
(Phase 8, D9: ``PHASE8_RECORD.md`` §25).
"""

from typing import Any
from unittest.mock import patch
from spec4.agents import deployer
from spec4.app_constants import STATE_DEPLOYER_COMPLETE
from tests._chunks import make_stream_chunk
from tests._agent_helpers import (
    _phaser_revision_vision,
    collect,
    make_session,
    mock_litellm_stream,
)


# ---------------------------------------------------------------------------
# Deployer return-with-existing-plan behavior
# ---------------------------------------------------------------------------


class TestDeployerExistingInfra:
    """Deployer pulls deployment-relevant code_review fields into its seed
    so it can reference existing infra rather than re-deciding from scratch."""

    def test_build_existing_infra_block_emits_only_present_fields(self) -> None:
        from spec4.agents.deployer import _build_existing_infra_block

        code_review = {
            "code_review": {
                "is_software_project": True,
                "deployment": {
                    "containerization": {
                        "tool": "docker",
                        "dockerfile_path": "Dockerfile",
                    },
                },
                "env_vars": [{"name": "DATABASE_URL", "required": True}],
                # persistence and auth absent
            }
        }
        block = _build_existing_infra_block(code_review)
        assert "deployment-relevant excerpt" in block
        # Inspect the JSON body, not the prose instructions (which mention
        # the field names by reference).
        json_body = block.split("```json", 1)[1].split("```", 1)[0]
        assert '"deployment"' in json_body
        assert '"env_vars"' in json_body
        assert "DATABASE_URL" in json_body
        assert '"persistence"' not in json_body
        assert '"auth"' not in json_body
        # Names-only reminder lives in the prose.
        assert "values live in the developer" in block.lower()

    def test_build_existing_infra_block_empty_when_nothing_relevant(self) -> None:
        from spec4.agents.deployer import _build_existing_infra_block

        # Code review present but no deployment-relevant blocks.
        cr = {
            "code_review": {
                "is_software_project": True,
                "project_type": "CLI tool",
                "languages": [{"name": "Python"}],
            }
        }
        assert _build_existing_infra_block(cr) == ""

    def test_build_existing_infra_block_empty_when_no_review(self) -> None:
        from spec4.agents.deployer import _build_existing_infra_block

        assert _build_existing_infra_block({}) == ""

    def test_build_existing_infra_block_accepts_unwrapped_form(self) -> None:
        """Works whether code_review is wrapped in the LLM envelope or not."""
        from spec4.agents.deployer import _build_existing_infra_block

        unwrapped = {
            "is_software_project": True,
            "auth": {"model": "jwt", "library": "authlib"},
        }
        block = _build_existing_infra_block(unwrapped)
        assert "auth" in block
        assert "jwt" in block

    def test_fresh_start_seed_includes_infra_excerpt_when_present(self) -> None:
        session = make_session(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            _deployer_readme_optin_done=True,
            code_review={
                "code_review": {
                    "is_software_project": True,
                    "deployment": {
                        "containerization": {
                            "tool": "docker",
                            "dockerfile_path": "Dockerfile",
                        },
                    },
                    "env_vars": [{"name": "API_KEY", "required": True}],
                }
            },
        )
        with mock_litellm_stream("Hi! I'm Deployer."):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        assert "deployment-relevant excerpt" in seed
        assert "API_KEY" in seed
        assert "Dockerfile" in seed

    def test_fresh_start_seed_omits_infra_excerpt_when_review_lacks_fields(
        self,
    ) -> None:
        session = make_session(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            _deployer_readme_optin_done=True,
            code_review={
                "code_review": {
                    "is_software_project": True,
                    "project_type": "library",
                }
            },
        )
        with mock_litellm_stream("Hi! I'm Deployer."):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        assert "deployment-relevant excerpt" not in seed


class TestDeployerExistingPlanGuard:
    """A deployment-plan.md on disk must not be replaced silently when the
    user returns — including in a fresh browser with no in-memory state."""

    def _returning_session(self, **overrides: Any) -> dict[str, Any]:
        # Mirrors what session.load_working_dir produces when an on-disk
        # deployment-plan.md is detected: state is COMPLETE, the "existed"
        # flag is True, the in-memory plan markdown is None, no chat history.
        defaults: dict[str, Any] = dict(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            stack_statement={"name": "App"},
            deployer_state=STATE_DEPLOYER_COMPLETE,
            deployer_messages=[],
            _deployer_plan_existed=True,
            _deployer_plan_markdown=None,
            _deployer_pending_plan=False,
        )
        defaults.update(overrides)
        return make_session(**defaults)

    def test_fresh_start_seed_acknowledges_existing_plan(self, tmp_path) -> None:
        # The agent's first turn must inform the developer that an existing
        # plan was found and ask how they want to proceed, rather than the
        # generic "which coding agent are you using" intro. Mirror what
        # load_working_dir produces: a working_dir with an on-disk plan, and
        # the _deployer_plan_existed flag set from having detected it.
        from spec4 import project_manager

        plan = "# Existing Deployment Plan\n\n## Steps\n\nDeploy the thing."
        project_manager.save_deployment_plan(str(tmp_path), plan, 0)
        session = self._returning_session(working_dir=str(tmp_path), phase_version=0)
        with mock_litellm_stream("Hi! I see you have an existing plan…"):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        assert "existing" in seed.lower() or "previous session" in seed.lower()
        assert "deployment-plan.md" in seed
        # The seed offers concrete options to the user.
        assert "1." in seed and "2." in seed and "3." in seed
        # The loaded plan's contents are embedded so the agent need not ask the
        # developer to paste the file (the re-entry seed behavior).
        assert "Existing Deployment Plan" in seed

    def test_fresh_start_seed_unchanged_when_no_existing_plan(self) -> None:
        # Greenfield: the agent uses its original intro, asking which coding
        # agent the developer plans to use.
        session = make_session(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            _deployer_plan_existed=False,
            _deployer_readme_optin_done=True,
        )
        with mock_litellm_stream("Hi! I'm Deployer."):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        assert "coding agent" in seed.lower()
        # And does NOT mention an existing on-disk plan.
        assert "deployment-plan.md" not in seed

    def test_no_reply_clears_pending_markdown(self) -> None:
        # The previous turn produced a candidate plan; user replies "no".
        session = self._returning_session(
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {
                    "role": "assistant",
                    "content": "## Deployment Steps … replace? (yes/no)",
                },
            ],
            _deployer_plan_markdown="# Plan\n\n## Deployment Steps\n…",
            _deployer_pending_plan=True,
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(
                deployer.run("no, keep it", session, session["llm_config"])
            )
        # No LLM call — the agent short-circuits with the keep_msg.
        mock_llm.assert_not_called()
        assert "kept" in output.lower() or "existing" in output.lower()
        # Critical: the staged markdown is cleared so persist_artifacts
        # cannot save it on a subsequent turn.
        assert session["_deployer_plan_markdown"] is None
        assert session["_deployer_pending_plan"] is False

    def test_yes_reply_preserves_markdown_for_persist(self) -> None:
        plan = "# Plan\n\n## Deployment Steps\n\n### 1. Build\n…"
        session = self._returning_session(
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {
                    "role": "assistant",
                    "content": plan + "\n\n…replace? (yes/no)",
                },
            ],
            _deployer_plan_markdown=plan,
            _deployer_pending_plan=True,
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            collect(deployer.run("yes", session, session["llm_config"]))
        mock_llm.assert_not_called()
        # Markdown is still set so persist_artifacts can write it.
        assert session["_deployer_plan_markdown"] == plan
        assert session["deployer_state"] == STATE_DEPLOYER_COMPLETE
        assert session["_deployer_pending_plan"] is False

    def test_new_plan_on_returning_user_triggers_confirmation(self) -> None:
        # Returning user with existing plan; chat history has built up and
        # the LLM now produces a fresh plan. The confirmation prompt must
        # fire — the new plan must NOT be persisted before approval.
        session = self._returning_session(
            deployer_messages=[
                {"role": "user", "content": "let's revise the plan"},
                {"role": "assistant", "content": "OK, what changes?"},
                {"role": "user", "content": "use Cloud Run instead"},
            ],
        )
        new_plan = (
            "# Deployment Plan\n\n## Target\n- **Provider:** GCP\n\n"
            "## Deployment Steps\n\n### 1. Build image\n…"
        )
        with mock_litellm_stream(new_plan):
            collect(
                deployer.run("use Cloud Run instead", session, session["llm_config"])
            )
        assert session["_deployer_plan_markdown"] == new_plan
        assert session["_deployer_pending_plan"] is True
        # State was already COMPLETE on entry but the agent does not "re-set"
        # it — the affirmative branch on the next turn is what locks in the
        # save.
        last_assistant = session["deployer_messages"][-1]["content"]
        assert "yes" in last_assistant.lower() and "no" in last_assistant.lower()


class TestDeployerRevisionMode:
    """Revision mode: when a prior round is implemented and the vision carries a
    delta, Deployer carries the prior deployment plan forward as the baseline and
    scopes the update to the delta (whole-system-scoped — the ai_features context
    stays whole, no introduced_in_version partition). The reader/note helpers are
    deterministic (no LLM). The gate is an implemented-predecessor probe and is NOT
    gated on the prior plan loading (the prior round may have skipped Deployer)."""

    # ----- revision_delta -----

    def test_delta_none_for_greenfield_vision(self) -> None:
        assert deployer.revision_delta({"vision_statement": {"name": "Fresh"}}) is None

    def test_delta_none_for_empty_or_missing(self) -> None:
        assert deployer.revision_delta(None) is None
        assert deployer.revision_delta({}) is None
        assert (
            deployer.revision_delta({"vision_statement": {"revision_history": []}})
            is None
        )
        # Non-enveloped (inner-form) vision is not revision mode.
        assert deployer.revision_delta({"name": "App"}) is None

    def test_delta_returns_last_history_entry(self) -> None:
        vision = {
            "vision_statement": {
                "revision_history": [
                    {"version": 0, "goal": "first"},
                    {
                        "version": 1,
                        "goal": "Add billing",
                        "changes": {"added": ["Subscriptions"]},
                    },
                ]
            }
        }
        delta = deployer.revision_delta(vision)
        assert delta is not None
        assert delta["goal"] == "Add billing"
        assert delta["changes"]["added"] == ["Subscriptions"]

    def test_delta_non_dict_last_entry_is_none(self) -> None:
        vision = {"vision_statement": {"revision_history": ["not a dict"]}}
        assert deployer.revision_delta(vision) is None

    # ----- build_revision_note -----

    def test_note_includes_all_change_buckets_and_goal(self) -> None:
        delta = {
            "goal": "Add billing",
            "changes": {
                "added": ["Subscriptions"],
                "modified": ["Checkout"],
                "removed": ["Free Tier"],
            },
        }
        note = deployer.build_revision_note(delta)
        assert note.startswith("[") and note.endswith("]")
        assert "Add billing" in note
        assert "Subscriptions" in note
        assert "Checkout" in note
        assert "Free Tier" in note
        # Deployment-scoping intent is explicit.
        assert "already provisioned and in place" in note
        assert "do not re-ask settled deployment decisions" in note

    def test_note_omits_goal_when_blank(self) -> None:
        note = deployer.build_revision_note(
            {"goal": "", "changes": {"added": ["X"], "modified": [], "removed": []}}
        )
        assert "Goal:" not in note
        assert "added features (X)" in note

    def test_note_empty_changes_still_preserves(self) -> None:
        # Degenerate delta (no feature changes) → still a valid scoping note.
        note = deployer.build_revision_note({"changes": {}})
        assert "already provisioned and in place" in note
        assert "Update the deployment plan only for" not in note

    def test_note_missing_changes_key(self) -> None:
        note = deployer.build_revision_note({"goal": "g"})
        assert "Goal: g" in note
        assert note.endswith("]")

    # ----- seed selection -----

    def _implement_prior_round(self, wd: str, *, with_plan: bool = True) -> None:
        from spec4 import project_manager

        project_manager.save_phases(
            wd, [{"phase_number": 1, "phase_title": "Steel"}], 0
        )
        if with_plan:
            project_manager.save_deployment_plan(
                wd, "# Deployment Plan\n\n## Target\n\n- **Provider:** Fly.io\n", 0
            )
        project_manager.get_version_dir(wd, 0).joinpath("IMPLEMENTED").write_text("")

    def test_revision_seed_carries_prior_plan_and_scopes_delta(
        self, tmp_path: Any
    ) -> None:
        wd = str(tmp_path)
        self._implement_prior_round(wd, with_plan=True)
        session = make_session(
            active_agent="deployer",
            working_dir=wd,
            phase_version=1,
            phases=[{"phase_number": 1, "phase_title": "Integration"}],
            stack_statement={"name": "App"},
            vision_statement=_phaser_revision_vision(
                added=["Subscriptions"], goal="Add billing"
            ),
            _deployer_plan_existed=False,
        )
        with mock_litellm_stream("Carrying forward your deployment."):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        # Operates in revision mode, scoped to the delta.
        assert "REVISION mode" in seed
        assert "Subscriptions" in seed
        assert "Add billing" in seed
        assert "already provisioned and in place" in seed
        # Carries the prior implemented plan forward as the baseline.
        assert "established baseline" in seed
        assert "Provider:** Fly.io" in seed
        assert "carrying forward from the baseline above" in seed
        # Not the generic greenfield intro.
        assert "then begin by asking which AI coding agent" not in seed

    def test_revision_seed_without_prior_plan_skipped_predecessor(
        self, tmp_path: Any
    ) -> None:
        # Prior round implemented but Deployer was skipped (no deployment-plan.md):
        # still revision mode, no baseline block, graceful intro.
        wd = str(tmp_path)
        self._implement_prior_round(wd, with_plan=False)
        session = make_session(
            active_agent="deployer",
            working_dir=wd,
            phase_version=1,
            phases=[{"phase_number": 1, "phase_title": "Integration"}],
            stack_statement={"name": "App"},
            vision_statement=_phaser_revision_vision(
                added=["Subscriptions"], goal="Add billing"
            ),
            _deployer_plan_existed=False,
        )
        with mock_litellm_stream("Revision, no baseline."):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        assert "REVISION mode" in seed
        assert "Subscriptions" in seed
        # No prior-plan baseline block.
        assert "established baseline" not in seed
        assert "carrying forward from the baseline above" not in seed
        # Graceful no-baseline intro instead.
        assert "note that this is a revision of an already-deployed project" in seed

    def test_revision_seed_keeps_ai_features_whole(self, tmp_path: Any) -> None:
        # D3: _ai_features_for_deployer stays whole in revision mode — no
        # introduced_in_version partition into new-vs-established buckets.
        wd = str(tmp_path)
        self._implement_prior_round(wd, with_plan=True)
        ai_features = {
            "ai_features": [
                {"name": "Summarizer", "tier": "rag", "introduced_in_version": 0},
                {"name": "Agent", "tier": "tool_agent", "introduced_in_version": 1},
            ],
            "cross_cutting": {
                "provider_strategy": {"recommendation": "Use one provider"}
            },
        }
        session = make_session(
            active_agent="deployer",
            working_dir=wd,
            phase_version=1,
            phases=[{"phase_number": 1, "phase_title": "Integration"}],
            stack_statement={"name": "App"},
            ai_features=ai_features,
            vision_statement=_phaser_revision_vision(
                added=["Agent"], goal="Add an agent"
            ),
            _deployer_plan_existed=False,
        )
        with mock_litellm_stream("Whole AI context."):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        # The whole deployment-context block is present...
        assert "AI features spec — deployment context" in seed
        # ...and it is NOT partitioned the way _ai_features_for_phaser would.
        assert "do NOT create phases" not in seed
        assert "Already-implemented AI features" not in seed

    def test_prior_round_without_delta_is_not_revision(self, tmp_path: Any) -> None:
        # Implemented prior round exists, but the vision has no revision delta —
        # falls through to the fresh greenfield seed, not revision mode.
        wd = str(tmp_path)
        self._implement_prior_round(wd, with_plan=True)
        session = make_session(
            active_agent="deployer",
            working_dir=wd,
            phase_version=1,
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            stack_statement={"name": "App"},
            vision_statement={"vision_statement": {"name": "App"}},
            _deployer_plan_existed=False,
            _deployer_readme_optin_done=True,
        )
        with mock_litellm_stream("Fresh plan."):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        assert "REVISION mode" not in seed
        assert "asking which AI coding agent" in seed

    def test_delta_without_implemented_round_is_not_revision(
        self, tmp_path: Any
    ) -> None:
        # Vision carries a revision delta but no prior round is IMPLEMENTED →
        # not revision mode (fresh greenfield seed).
        wd = str(tmp_path)
        session = make_session(
            active_agent="deployer",
            working_dir=wd,
            phase_version=0,
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            stack_statement={"name": "App"},
            vision_statement=_phaser_revision_vision(
                added=["Subscriptions"], goal="Add billing"
            ),
            _deployer_plan_existed=False,
            _deployer_readme_optin_done=True,
        )
        with mock_litellm_stream("Greenfield plan."):
            collect(deployer.run(None, session, session["llm_config"]))
        seed = session["deployer_messages"][0]["content"]
        assert "REVISION mode" not in seed
        assert "asking which AI coding agent" in seed


class TestDeployerReadme:
    """Deployer offers a comprehensive project README after the deployment plan
    is finalized; on acceptance it authors the README and stages it for the
    project root (not .spec4). build_readme_request scaffolds the authoring turn;
    the offer/accept/decline flow mirrors the existing replace-confirmation."""

    # --- build_readme_request --------------------------------------------

    def test_build_request_fresh(self) -> None:
        req = deployer.build_readme_request(None, None)
        low = req.lower()
        assert "readme" in low
        assert "install" in low
        assert "usage" in low or "use the application" in low
        assert "vision" in low
        assert "output the readme directly" in low
        # No baseline block and no revision note in the greenfield case.
        assert "already exists" not in low
        assert "revision round" not in low

    def test_build_request_with_existing_baseline(self) -> None:
        req = deployer.build_readme_request("# Existing\n\nBody.\n", None)
        assert "already exists at the project root" in req
        assert "# Existing" in req
        assert "update it in place" in req

    def test_build_request_with_delta_names_changes(self) -> None:
        delta = {
            "changes": {
                "added": ["Export to PDF"],
                "modified": ["Login"],
                "removed": [],
            }
        }
        req = deployer.build_readme_request(None, delta)
        assert "revision round" in req.lower()
        assert "Export to PDF" in req
        assert "Login" in req

    # --- offer placement --------------------------------------------------

    def test_offer_appended_on_no_prior_plan_finalization(self) -> None:
        session = make_session(
            active_agent="deployer",
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": "ready to finalize?"},
            ],
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            _deployer_plan_existed=False,
        )
        plan = (
            "# Deployment Plan\n\n## Target\n- **Provider:** Fly.io\n\n"
            "## Deployment Steps\n\n### 1. Build\n…"
        )
        with mock_litellm_stream(plan):
            collect(deployer.run("yes, looks good", session, session["llm_config"]))
        assert session["_deployer_pending_readme"] is True
        assert "README" in session["deployer_messages"][-1]["content"]
        assert session["deployer_state"] == STATE_DEPLOYER_COMPLETE
        # The plan itself is still staged for persistence, unchanged.
        assert session["_deployer_plan_markdown"] == plan

    def test_offer_appended_after_replace_confirmation_accepted(self) -> None:
        plan = "# Plan\n\n## Deployment Steps\n\n### 1. Build\n…"
        session = make_session(
            active_agent="deployer",
            deployer_state=STATE_DEPLOYER_COMPLETE,
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": plan + "\n\n…replace? (yes/no)"},
            ],
            _deployer_plan_existed=True,
            _deployer_plan_markdown=plan,
            _deployer_pending_plan=True,
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(deployer.run("yes", session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert session["_deployer_pending_readme"] is True
        assert "README" in output
        assert session["_deployer_plan_markdown"] == plan

    # --- accept / decline -------------------------------------------------

    def test_accept_generates_and_stages_readme(self) -> None:
        session = make_session(
            active_agent="deployer",
            working_dir=None,
            deployer_state=STATE_DEPLOYER_COMPLETE,
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": "plan…readme? (yes/no)"},
            ],
            _deployer_pending_readme=True,
        )
        readme = "# My App\n\nA great app.\n\n## Install\n\n`pip install .`\n"
        with mock_litellm_stream(readme):
            collect(deployer.run("yes please", session, session["llm_config"]))
        assert session["_deployer_readme_markdown"] == readme
        assert session.get("_deployer_generating_readme") is False
        assert session["_deployer_pending_readme"] is False
        # The authoring instruction was injected as the user turn.
        user_msgs = [
            m["content"] for m in session["deployer_messages"] if m["role"] == "user"
        ]
        assert any("comprehensive project README" in c for c in user_msgs)

    def test_accept_uses_existing_readme_as_baseline(self, tmp_path: Any) -> None:
        from spec4 import project_manager

        project_manager.save_readme(str(tmp_path), "# Old README\n\nOld content.\n")
        session = make_session(
            active_agent="deployer",
            working_dir=str(tmp_path),
            deployer_state=STATE_DEPLOYER_COMPLETE,
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": "readme? (yes/no)"},
            ],
            _deployer_pending_readme=True,
        )
        with mock_litellm_stream("# New README\n"):
            collect(deployer.run("yes", session, session["llm_config"]))
        seed = next(
            m["content"]
            for m in session["deployer_messages"]
            if m["role"] == "user" and "comprehensive project README" in m["content"]
        )
        assert "Old README" in seed
        assert "update it in place" in seed

    def test_decline_skips_readme_no_llm_call(self) -> None:
        session = make_session(
            active_agent="deployer",
            deployer_state=STATE_DEPLOYER_COMPLETE,
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": "plan…" + deployer._README_OFFER},
            ],
            _deployer_pending_readme=True,
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(deployer.run("no thanks", session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "README" in output
        assert session["_deployer_pending_readme"] is False
        assert session.get("_deployer_readme_markdown") in (None, "")
        assert not session.get("_deployer_generating_readme")


class TestDeployerReadmeUpfrontOptin:
    """Greenfield asks the README opt-in up front (a standalone, prominent turn
    before any plan work) and auto-authors the README after the plan when
    accepted — replacing the old offer buried at the bottom of the plan."""

    # --- the up-front gate ------------------------------------------------

    def test_optin_asked_first_on_greenfield_open(self) -> None:
        session = make_session(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            _deployer_plan_existed=False,
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(deployer.run(None, session, session["llm_config"]))
        # Deterministic gate: no LLM call, and the opening seed is not built yet.
        mock_llm.assert_not_called()
        assert "README" in output
        assert session["_deployer_pending_readme_optin"] is True
        assert session["_deployer_readme_optin_done"] is True
        assert session["deployer_messages"] == []

    def test_optin_accept_records_choice_and_opens(self) -> None:
        session = make_session(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            _deployer_plan_existed=False,
            _deployer_readme_optin_done=True,
            _deployer_pending_readme_optin=True,
        )
        with mock_litellm_stream("Which coding agent are you using?"):
            collect(deployer.run("yes please", session, session["llm_config"]))
        assert session["_deployer_readme_requested"] is True
        assert session["_deployer_pending_readme_optin"] is False
        # The opt-in Q&A never enters the LLM history; the first message is the
        # coding-agent opening seed, and the bare "yes" is absent.
        assert session["deployer_messages"][0]["role"] == "user"
        assert "coding agent" in session["deployer_messages"][0]["content"].lower()
        assert all(
            "yes please" not in m["content"] for m in session["deployer_messages"]
        )

    def test_optin_decline_records_choice_and_opens(self) -> None:
        session = make_session(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            _deployer_plan_existed=False,
            _deployer_readme_optin_done=True,
            _deployer_pending_readme_optin=True,
        )
        with mock_litellm_stream("Which coding agent are you using?"):
            collect(deployer.run("no thanks", session, session["llm_config"]))
        assert session["_deployer_readme_requested"] is False
        assert session["_deployer_pending_readme_optin"] is False
        assert "coding agent" in session["deployer_messages"][0]["content"].lower()

    def test_optin_ambiguous_reasks_without_llm(self) -> None:
        session = make_session(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            _deployer_plan_existed=False,
            _deployer_readme_optin_done=True,
            _deployer_pending_readme_optin=True,
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(
                deployer.run("what's a README?", session, session["llm_config"])
            )
        mock_llm.assert_not_called()
        assert "README" in output
        # Still pending — the gate persists until a clear yes/no, and no choice
        # is recorded yet.
        assert session["_deployer_pending_readme_optin"] is True
        assert "_deployer_readme_requested" not in session
        assert session["deployer_messages"] == []

    # --- auto-author / skip after the plan --------------------------------

    def test_optin_yes_autoauthors_readme_after_plan(self) -> None:
        session = make_session(
            active_agent="deployer",
            working_dir=None,
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": "ready to finalize?"},
            ],
            _deployer_plan_existed=False,
            _deployer_readme_optin_done=True,
            _deployer_readme_requested=True,
        )
        plan = (
            "# Deployment Plan\n\n## Target\n- **Provider:** Fly.io\n\n"
            "## Deployment Steps\n\n### 1. Build\n…"
        )
        readme = "# My App\n\nA great app.\n\n## Install\n\n`pip install .`\n"
        plan_chunks = [make_stream_chunk(c) for c in plan]
        plan_chunks.append(make_stream_chunk("", finish_reason="stop"))
        readme_chunks = [make_stream_chunk(c) for c in readme]
        readme_chunks.append(make_stream_chunk("", finish_reason="stop"))
        with patch(
            "spec4.llm.litellm.completion",
            side_effect=[iter(plan_chunks), iter(readme_chunks)],
        ) as mock_llm:
            output = collect(deployer.run("looks good", session, session["llm_config"]))
        # Exactly two LLM calls: the plan, then the README authored from it.
        assert mock_llm.call_count == 2
        assert session["_deployer_plan_markdown"] == plan
        assert session["_deployer_readme_markdown"] == readme
        # No trailing offer / pending flag — the decision was made up front — and
        # the request flag is consumed so a later plan turn won't re-author.
        assert not session.get("_deployer_pending_readme")
        assert deployer._README_OFFER not in output
        assert session["_deployer_readme_requested"] is False
        # The authoring instruction was injected as a user turn, and both the
        # plan and the freshly-authored README appear in the turn's output.
        assert any(
            "comprehensive project README" in m["content"]
            for m in session["deployer_messages"]
            if m["role"] == "user"
        )
        assert "Deployment Steps" in output
        assert "My App" in output
        assert session["deployer_state"] == STATE_DEPLOYER_COMPLETE

    def test_optin_no_skips_readme_after_plan(self) -> None:
        session = make_session(
            active_agent="deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            deployer_messages=[
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": "ready to finalize?"},
            ],
            _deployer_plan_existed=False,
            _deployer_readme_optin_done=True,
            _deployer_readme_requested=False,
        )
        plan = "# Plan\n\n## Deployment Steps\n\n### 1. Build\n…"
        plan_chunks = [make_stream_chunk(c) for c in plan]
        plan_chunks.append(make_stream_chunk("", finish_reason="stop"))
        with patch(
            "spec4.llm.litellm.completion",
            side_effect=[iter(plan_chunks)],
        ) as mock_llm:
            output = collect(deployer.run("looks good", session, session["llm_config"]))
        # Exactly one LLM call (the plan) — no README authoring call.
        assert mock_llm.call_count == 1
        assert session["_deployer_plan_markdown"] == plan
        assert session.get("_deployer_readme_markdown") in (None, "")
        # No README authored, no trailing offer, no pending flag.
        assert not session.get("_deployer_pending_readme")
        assert deployer._README_OFFER not in output
        assert not any(
            "comprehensive project README" in m["content"]
            for m in session["deployer_messages"]
            if m["role"] == "user"
        )
        assert session["deployer_state"] == STATE_DEPLOYER_COMPLETE
