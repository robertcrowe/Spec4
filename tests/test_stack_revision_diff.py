"""The revision re-emission diff (D-RD series).

A revision round re-emits the whole carried-forward stack, and a live FF-round
draw dropped an established ``SendGrid`` library entry nobody asked to remove.
These tests pin the deterministic diff that catches that: what counts as a
removal, how a removal is classified (D-RD0), that unrequested removals are
restored in place (D-RD2), that the diff is persisted at envelope level and
leaks into no consumer (D-RD3), and that the commit display carries the
receipt. The end-to-end test drives ``run`` through the mocked stream so the
hook's gating (revision mode only, first commit of the round only) is tested
where it lives.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from spec4 import project_manager
from spec4.agents import stack_advisor
from spec4.agents.stack_advisor import _revision_diff as rd
from spec4.stack_routing import stack_signal_entries
from tests._agent_helpers import collect, make_session, mock_litellm_stream


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _prior() -> dict[str, Any]:
    return {
        "stack_spec": {
            "name": "App",
            "languages": [{"name": "Python", "version": "3.12"}],
            "deployment": {
                "targets": [
                    {"name": "api", "kind": "rest_api"},
                    {"name": "worker", "kind": "worker"},
                ]
            },
            "providers": {
                "OpenAI": {"capabilities": [{"tier": "single_call"}]},
                "Ollama": {"capabilities": [{"tier": "single_call"}]},
            },
            "integrations": [
                {"name": "Stripe", "serves_features": ["billing"]},
                {"name": "Kroger Product API", "serves_features": ["shopping_list"]},
            ],
            "security": {
                "auth": [{"mechanism": "session cookie", "purpose": "returning users"}]
            },
            "persistence": {
                "primary_store": {
                    "choice": "PostgreSQL",
                    "collections": [
                        {"name": "users", "serves_features": ["accounts"]},
                        {"name": "invoices", "serves_features": ["billing"]},
                    ],
                },
                "cache": {"choice": "Redis"},
            },
            "libraries": [
                {"name": "FastAPI", "category": "web framework"},
                {
                    "name": "SendGrid",
                    "category": "email",
                    "serves_features": ["notify"],
                },
                {"name": "pytest", "category": "testing"},
            ],
            "project_structure": [{"path": "app/api/", "purpose": "routers"}],
            "additional_decisions": [{"name": "commit_message_format", "value": "cc"}],
            "references": [{"standard": "OpenAI API", "url": "https://x"}],
        }
    }


def _delta(
    removed: list[str] | None = None, added: list[str] | None = None
) -> dict[str, Any]:
    return {
        "goal": "",
        "changes": {"added": added or [], "modified": [], "removed": removed or []},
    }


def _drop(stack: dict[str, Any], block: str, key: str) -> dict[str, Any]:
    """A deep copy of ``stack`` with one entry removed from one list block."""
    new = copy.deepcopy(stack)
    node: Any = new["stack_spec"]
    parts = block.split(".")
    for part in parts[:-1]:
        node = node[part]
    items = node[parts[-1]]
    if isinstance(items, dict):
        del items[key]
    else:
        node[parts[-1]] = [
            e
            for e in items
            if not any(
                e.get(f) == key for f in ("name", "mechanism", "path", "standard")
            )
        ]
    return new


def _by_key(removals: list[rd.Removal]) -> dict[str, rd.Removal]:
    return {r.key: r for r in removals}


# ---------------------------------------------------------------------------
# revision_removals — what is a removal, and why
# ---------------------------------------------------------------------------


class TestRevisionRemovals:
    def test_identical_specs_report_nothing(self) -> None:
        assert rd.revision_removals(_prior(), _prior(), _delta()) == []

    def test_dropped_library_with_no_request_is_unrequested(self) -> None:
        # The SendGrid incident, exactly.
        new = _drop(_prior(), "libraries", "SendGrid")
        removals = rd.revision_removals(_prior(), new, _delta(added=["Subscriptions"]))
        assert [(r.block, r.key, r.disposition) for r in removals] == [
            ("libraries", "SendGrid", rd.UNREQUESTED)
        ]
        assert removals[0].prior_index == 1
        assert removals[0].matched == ""

    def test_delta_removed_feature_named_like_entry_is_requested(self) -> None:
        # An integration named after the removed feature.
        new = _drop(_prior(), "integrations", "Stripe")
        removals = rd.revision_removals(_prior(), new, _delta(removed=["Stripe"]))
        assert _by_key(removals)["Stripe"].disposition == rd.REQUESTED_BY_DELTA
        assert _by_key(removals)["Stripe"].matched == "Stripe"

    def test_entry_serving_only_removed_features_is_requested(self) -> None:
        # SendGrid serves only `notify`; the delta removes `Notify` → requested.
        new = _drop(_prior(), "libraries", "SendGrid")
        removals = rd.revision_removals(_prior(), new, _delta(removed=["Notify"]))
        assert _by_key(removals)["SendGrid"].disposition == rd.REQUESTED_BY_DELTA
        assert _by_key(removals)["SendGrid"].matched == "Notify"

    def test_entry_serving_a_surviving_feature_is_not_requested(self) -> None:
        prior = _prior()
        prior["stack_spec"]["libraries"][1]["serves_features"] = ["notify", "billing"]
        new = _drop(prior, "libraries", "SendGrid")
        removals = rd.revision_removals(prior, new, _delta(removed=["Notify"]))
        assert _by_key(removals)["SendGrid"].disposition == rd.UNREQUESTED

    def test_entry_named_in_a_user_turn_is_requested_in_conversation(self) -> None:
        new = _drop(_prior(), "libraries", "SendGrid")
        turns = ["Let's keep everything.", "Drop SendGrid, we're moving to SES."]
        removals = rd.revision_removals(_prior(), new, _delta(), turns)
        r = _by_key(removals)["SendGrid"]
        assert r.disposition == rd.REQUESTED_IN_CONVERSATION
        assert r.matched == "Drop SendGrid, we're moving to SES."

    def test_conversation_match_is_whole_word(self) -> None:
        new = _drop(_prior(), "libraries", "SendGrid")
        removals = rd.revision_removals(
            _prior(), new, _delta(), ["use SendGridX instead"]
        )
        assert _by_key(removals)["SendGrid"].disposition == rd.UNREQUESTED

    def test_delta_wins_over_conversation(self) -> None:
        new = _drop(_prior(), "libraries", "SendGrid")
        removals = rd.revision_removals(
            _prior(), new, _delta(removed=["Notify"]), ["drop sendgrid"]
        )
        assert _by_key(removals)["SendGrid"].disposition == rd.REQUESTED_BY_DELTA

    def test_every_block_is_diffed(self) -> None:
        drops = [
            ("languages", "Python"),
            ("deployment.targets", "worker"),
            ("providers", "Ollama"),
            ("integrations", "Kroger Product API"),
            ("security.auth", "session cookie"),
            ("persistence", "cache"),
            ("persistence.primary_store.collections", "invoices"),
            ("libraries", "pytest"),
            ("project_structure", "app/api/"),
            ("additional_decisions", "commit_message_format"),
            ("references", "OpenAI API"),
        ]
        new = _prior()
        for block, key in drops:
            new = _drop(new, block, key)
        removals = rd.revision_removals(_prior(), new, _delta())
        assert sorted((r.block, r.key) for r in removals) == sorted(drops)
        assert all(r.unrequested for r in removals)

    def test_provider_capabilities_are_not_diffed(self) -> None:
        # D-RD4: no stable name field, so a positional diff would be noise.
        new = _prior()
        new["stack_spec"]["providers"]["OpenAI"]["capabilities"] = []
        assert rd.revision_removals(_prior(), new, _delta()) == []

    def test_nameless_entries_key_by_position(self) -> None:
        prior = {"stack_spec": {"libraries": [{"purpose": "a"}, {"purpose": "b"}]}}
        new = {"stack_spec": {"libraries": [{"purpose": "a"}]}}
        removals = rd.revision_removals(prior, new, _delta())
        assert [(r.key, r.prior_index) for r in removals] == [("librarie_2", 1)]

    def test_prior_with_category_keyed_libraries_is_normalised(self) -> None:
        # merge_library_additions still writes {tier: [...]}; the diff must read
        # it as the flat list the normaliser produces.
        prior = {
            "stack_spec": {
                "libraries": {"backend": [{"name": "FastAPI"}, {"name": "SendGrid"}]}
            }
        }
        new = {
            "stack_spec": {"libraries": [{"name": "FastAPI", "category": "backend"}]}
        }
        removals = rd.revision_removals(prior, new, _delta())
        assert [(r.block, r.key) for r in removals] == [("libraries", "SendGrid")]
        # The caller's prior is untouched.
        assert isinstance(prior["stack_spec"]["libraries"], dict)

    def test_bare_and_wrapped_specs_both_read(self) -> None:
        prior = _prior()["stack_spec"]
        new = {"stack": _drop(_prior(), "libraries", "pytest")["stack_spec"]}
        removals = rd.revision_removals(prior, new, _delta())
        assert [r.key for r in removals] == ["pytest"]


# ---------------------------------------------------------------------------
# restore_unrequested — lossless assembly (D-RD2)
# ---------------------------------------------------------------------------


class TestRestoreUnrequested:
    def test_unrequested_list_entry_returns_at_prior_index(self) -> None:
        new = _drop(_prior(), "libraries", "SendGrid")
        removals = rd.revision_removals(_prior(), new, _delta())
        assert rd.restore_unrequested(new, removals) == 1
        assert new["stack_spec"]["libraries"] == _prior()["stack_spec"]["libraries"]

    def test_requested_entries_stay_removed(self) -> None:
        new = _drop(_drop(_prior(), "libraries", "SendGrid"), "integrations", "Stripe")
        removals = rd.revision_removals(_prior(), new, _delta(removed=["Stripe"]), [])
        assert rd.restore_unrequested(new, removals) == 1
        names = [e["name"] for e in new["stack_spec"]["libraries"]]
        assert "SendGrid" in names
        assert [e["name"] for e in new["stack_spec"]["integrations"]] == [
            "Kroger Product API"
        ]

    def test_index_is_clamped_when_list_shrank(self) -> None:
        new = _drop(_drop(_prior(), "libraries", "FastAPI"), "libraries", "pytest")
        # Drop FastAPI *and* pytest; pytest's prior index (2) exceeds the new
        # list's length once SendGrid is the only survivor.
        removals = rd.revision_removals(_prior(), new, _delta(), ["drop FastAPI"])
        rd.restore_unrequested(new, removals)
        assert [e["name"] for e in new["stack_spec"]["libraries"]] == [
            "SendGrid",
            "pytest",
        ]

    def test_keyed_entry_returns_at_prior_position(self) -> None:
        new = _drop(_prior(), "providers", "OpenAI")
        removals = rd.revision_removals(_prior(), new, _delta())
        rd.restore_unrequested(new, removals)
        assert list(new["stack_spec"]["providers"]) == ["OpenAI", "Ollama"]

    def test_nested_collection_returns_to_its_store(self) -> None:
        new = _drop(_prior(), "persistence.primary_store.collections", "users")
        removals = rd.revision_removals(_prior(), new, _delta())
        rd.restore_unrequested(new, removals)
        colls = new["stack_spec"]["persistence"]["primary_store"]["collections"]
        assert [c["name"] for c in colls] == ["users", "invoices"]

    def test_missing_block_is_recreated(self) -> None:
        new = _prior()
        del new["stack_spec"]["security"]
        removals = rd.revision_removals(_prior(), new, _delta())
        rd.restore_unrequested(new, removals)
        assert (
            new["stack_spec"]["security"]["auth"]
            == _prior()["stack_spec"]["security"]["auth"]
        )

    def test_restored_entry_is_a_copy(self) -> None:
        new = _drop(_prior(), "libraries", "SendGrid")
        removals = rd.revision_removals(_prior(), new, _delta())
        rd.restore_unrequested(new, removals)
        new["stack_spec"]["libraries"][1]["name"] = "mutated"
        assert removals[0].entry["name"] == "SendGrid"


# ---------------------------------------------------------------------------
# removals_record / render_revision_receipt (D-RD3, D-RD2 rendering)
# ---------------------------------------------------------------------------


class TestRecordAndReceipt:
    def test_record_carries_keys_and_dispositions_only(self) -> None:
        new = _drop(_drop(_prior(), "libraries", "SendGrid"), "integrations", "Stripe")
        removals = rd.revision_removals(_prior(), new, _delta(removed=["Stripe"]))
        record = rd.removals_record(removals)
        assert record == [
            {
                "block": "integrations",
                "key": "Stripe",
                "disposition": rd.REQUESTED_BY_DELTA,
                "matched": "Stripe",
            },
            {
                "block": "libraries",
                "key": "SendGrid",
                "disposition": rd.UNREQUESTED,
                "matched": "",
            },
        ]
        assert all(set(r) == {"block", "key", "disposition", "matched"} for r in record)

    def test_record_is_json_serialisable(self) -> None:
        new = _drop(_prior(), "libraries", "SendGrid")
        json.dumps(rd.removals_record(rd.revision_removals(_prior(), new, _delta())))

    def test_receipt_empty_when_nothing_dropped(self) -> None:
        assert rd.render_revision_receipt([]) == ""

    def test_receipt_names_restored_and_removed(self) -> None:
        new = _drop(_drop(_prior(), "libraries", "SendGrid"), "integrations", "Stripe")
        removals = rd.revision_removals(_prior(), new, _delta(), ["drop Stripe please"])
        text = rd.render_revision_receipt(removals)
        assert "**Restored to the established stack**" in text
        assert "`SendGrid` (libraries)" in text
        assert "**Removed from the established stack**" in text
        assert "`Stripe` (integrations) — you said: “drop Stripe please”" in text

    def test_receipt_cites_the_removed_feature(self) -> None:
        new = _drop(_prior(), "libraries", "SendGrid")
        removals = rd.revision_removals(_prior(), new, _delta(removed=["Notify"]))
        text = rd.render_revision_receipt(removals)
        assert "Restored" not in text
        assert "`SendGrid` (libraries) — removed feature *Notify*" in text

    def test_record_adds_no_signal_entries(self) -> None:
        # D-RD3: the envelope-level record must be invisible to the routing
        # walk — it carries no name/serves_features/status.
        stack = _drop(_prior(), "libraries", "SendGrid")
        removals = rd.revision_removals(_prior(), stack, _delta())
        before = len(stack_signal_entries(stack))
        stack[rd.REVISION_REMOVALS_KEY] = rd.removals_record(removals)
        assert len(stack_signal_entries(stack)) == before


# ---------------------------------------------------------------------------
# The hook in run() — gating and effect
# ---------------------------------------------------------------------------


def _revision_vision(removed: list[str] | None = None) -> dict[str, Any]:
    return {
        "vision_statement": {
            "name": "App",
            "revision_history": [
                {
                    "version": 1,
                    "based_on_version": 0,
                    "goal": "Add billing",
                    "changes": {
                        "added": ["Subscriptions"],
                        "modified": [],
                        "removed": removed or [],
                    },
                    "rationale": "",
                }
            ],
        }
    }


def _implement_prior(wd: str, stack: dict[str, Any]) -> None:
    project_manager.save_stack(wd, stack, 0)
    project_manager.get_version_dir(wd, 0).joinpath("IMPLEMENTED").write_text("")


def _artifact_reply(stack: dict[str, Any]) -> str:
    return "```json\n" + json.dumps(stack) + "\n```"


class TestRunHook:
    def _run_revision_round(
        self, tmp_path: Any, reply_stack: dict[str, Any], **session_kw: Any
    ) -> dict[str, Any]:
        wd = str(tmp_path)
        _implement_prior(wd, _prior())
        session = make_session(
            active_agent="stack_advisor",
            working_dir=wd,
            vision_statement=_revision_vision(),
            **session_kw,
        )
        with mock_litellm_stream("Carrying forward your stack."):
            collect(stack_advisor.run(None, session, session["llm_config"]))
        with mock_litellm_stream(_artifact_reply(reply_stack)):
            collect(stack_advisor.run("finalize", session, session["llm_config"]))
        return session

    def test_unrequested_drop_is_restored_recorded_and_shown(
        self, tmp_path: Any
    ) -> None:
        session = self._run_revision_round(
            tmp_path, _drop(_prior(), "libraries", "SendGrid")
        )
        stack = session["stack_statement"]
        assert "SendGrid" in [e["name"] for e in stack["stack_spec"]["libraries"]]
        assert stack[rd.REVISION_REMOVALS_KEY] == [
            {
                "block": "libraries",
                "key": "SendGrid",
                "disposition": rd.UNREQUESTED,
                "matched": "",
            }
        ]
        display = session["_display_override"]
        assert "**Restored to the established stack**" in display
        assert display.index("Restored to the established stack") < display.index(
            "Continue to Phaser"
        )

    def test_clean_re_emission_persists_empty_record(self, tmp_path: Any) -> None:
        # D-RD3: the instrument is written unconditionally in a revision round.
        session = self._run_revision_round(tmp_path, _prior())
        assert session["stack_statement"][rd.REVISION_REMOVALS_KEY] == []
        assert "established stack" not in session["_display_override"]

    def test_conversational_request_in_this_round_is_honoured(
        self, tmp_path: Any
    ) -> None:
        wd = str(tmp_path)
        _implement_prior(wd, _prior())
        session = make_session(
            active_agent="stack_advisor",
            working_dir=wd,
            vision_statement=_revision_vision(),
        )
        with mock_litellm_stream("Carrying forward."):
            collect(stack_advisor.run(None, session, session["llm_config"]))
        with mock_litellm_stream("Noted, dropping SendGrid."):
            collect(
                stack_advisor.run(
                    "Drop SendGrid, we are moving to SES.",
                    session,
                    session["llm_config"],
                )
            )
        with mock_litellm_stream(
            _artifact_reply(_drop(_prior(), "libraries", "SendGrid"))
        ):
            collect(stack_advisor.run("finalize", session, session["llm_config"]))
        stack = session["stack_statement"]
        assert "SendGrid" not in [e["name"] for e in stack["stack_spec"]["libraries"]]
        assert (
            stack[rd.REVISION_REMOVALS_KEY][0]["disposition"]
            == rd.REQUESTED_IN_CONVERSATION
        )
        assert "**Removed from the established stack**" in session["_display_override"]

    def test_seed_paste_does_not_count_as_conversation(self, tmp_path: Any) -> None:
        # The seed pastes the whole prior stack; if it counted as a user turn
        # every drop would read as requested. SendGrid appears only there.
        session = self._run_revision_round(
            tmp_path, _drop(_prior(), "libraries", "SendGrid")
        )
        assert session["stack_statement"][rd.REVISION_REMOVALS_KEY][0][
            "disposition"
        ] == (rd.UNREQUESTED)

    def test_greenfield_commit_is_untouched(self, tmp_path: Any) -> None:
        session = make_session(
            active_agent="stack_advisor",
            working_dir=str(tmp_path),
            vision_statement={"vision_statement": {"name": "App"}},
        )
        with mock_litellm_stream(
            _artifact_reply(_drop(_prior(), "libraries", "SendGrid"))
        ):
            collect(stack_advisor.run(None, session, session["llm_config"]))
        stack = session["stack_statement"]
        assert rd.REVISION_REMOVALS_KEY not in stack
        assert "SendGrid" not in [e["name"] for e in stack["stack_spec"]["libraries"]]

    def test_update_mode_reentry_is_not_reconciled(self, tmp_path: Any) -> None:
        # A stack already committed this round means the seed was update mode
        # ("refine or start from scratch"); a from-scratch stack must not be
        # back-filled from the old baseline.
        wd = str(tmp_path)
        _implement_prior(wd, _prior())
        session = make_session(
            active_agent="stack_advisor",
            working_dir=wd,
            vision_statement=_revision_vision(),
            stack_statement=_prior(),
        )
        fresh = {"stack_spec": {"name": "App", "libraries": [{"name": "Django"}]}}
        with mock_litellm_stream(_artifact_reply(fresh)):
            collect(stack_advisor.run(None, session, session["llm_config"]))
        stack = session["stack_statement"]
        assert [e["name"] for e in stack["stack_spec"]["libraries"]] == ["Django"]
        assert rd.REVISION_REMOVALS_KEY not in stack
