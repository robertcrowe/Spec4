"""Tests for :mod:`spec4.agents.brainstormer`.

Split out of ``tests/test_agents.py`` by source module, with every class unchanged
(Phase 8, D9: ``PHASE8_RECORD.md`` §25).
"""

from typing import Any
from unittest.mock import patch
from spec4.agents import brainstormer
from spec4.app_constants import STATE_IN_PROGRESS, STATE_VISION_COMPLETE
from tests._chunks import make_stream_chunk
from tests._agent_helpers import (
    _reply_sequence,
    collect,
    make_session,
    mock_litellm_stream,
)


# ---------------------------------------------------------------------------
# Brainstormer tests
# ---------------------------------------------------------------------------


class TestBrainstormer:
    def test_opening_asks_for_idea(self) -> None:
        session = make_session()
        output = collect(brainstormer.run(None, session, session["llm_config"]))
        assert (
            "project" in output.lower()
            or "idea" in output.lower()
            or "brainstorm" in output.lower()
        )

    def test_opening_does_not_call_llm(self) -> None:
        session = make_session()
        with patch("spec4.llm.litellm.completion") as mock_llm:
            collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()

    def test_user_input_streams_llm_output(self) -> None:
        session = make_session()
        with mock_litellm_stream("Great idea! Let me ask some questions."):
            output = collect(
                brainstormer.run(
                    "I want to build a todo app", session, session["llm_config"]
                )
            )
        assert "Great idea!" in output

    def test_conversation_history_accumulated(self) -> None:
        session = make_session()
        with mock_litellm_stream("Interesting!"):
            collect(
                brainstormer.run("I want a todo app", session, session["llm_config"])
            )

        assert len(session["brainstormer_messages"]) == 2
        assert session["brainstormer_messages"][0] == {
            "role": "user",
            "content": "I want a todo app",
        }
        assert session["brainstormer_messages"][1]["role"] == "assistant"
        assert "Interesting!" in session["brainstormer_messages"][1]["content"]

    def test_vision_json_sets_state_complete(self) -> None:
        session = make_session()
        vision_response = (
            "Great vision!\n\n```json\n"
            '{"vision_statement": {"name": "TodoApp", "vision": "A simple task manager"}}\n'  # noqa: E501
            "```"
        )
        with mock_litellm_stream(vision_response):
            collect(
                brainstormer.run("Yes, finalize it", session, session["llm_config"])
            )

        assert session["brainstormer_state"] == STATE_VISION_COMPLETE
        assert session["vision_statement"] == {
            "vision_statement": {"name": "TodoApp", "vision": "A simple task manager"}
        }

    def test_non_vision_response_stays_in_progress(self) -> None:
        session = make_session()
        with mock_litellm_stream("What type of users will use this app?"):
            collect(
                brainstormer.run("I want a todo app", session, session["llm_config"])
            )

        assert session["brainstormer_state"] == STATE_IN_PROGRESS
        assert session["vision_statement"] is None

    def test_llm_called_with_system_prompt_and_user_message(self) -> None:
        session = make_session()
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [
                    make_stream_chunk("Response"),
                    make_stream_chunk("", finish_reason="stop"),
                ]
            )
            collect(brainstormer.run("My idea", session, session["llm_config"]))

        call_kwargs = mock_llm.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1] == {"role": "user", "content": "My idea"}

    def test_llm_called_with_full_history_on_second_turn(self) -> None:
        session = make_session(
            brainstormer_messages=[
                {"role": "user", "content": "first message"},
                {"role": "assistant", "content": "first response"},
            ]
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [
                    make_stream_chunk("Second response"),
                    make_stream_chunk("", finish_reason="stop"),
                ]
            )
            collect(brainstormer.run("second message", session, session["llm_config"]))

        call_kwargs = mock_llm.call_args[1]
        messages = call_kwargs["messages"]
        # system + 2 prior + new user = 4 messages
        assert len(messages) == 4
        assert messages[-1] == {"role": "user", "content": "second message"}

    def test_initialises_brainstormer_messages_if_missing(self) -> None:
        session = make_session()
        del session["brainstormer_messages"]
        with mock_litellm_stream("Hello!"):
            collect(brainstormer.run("An idea", session, session["llm_config"]))
        assert "brainstormer_messages" in session


class TestOrphanTurnRecovery:
    """An LLM error mid-stream leaves the agent's history with a trailing user
    turn and no assistant followup. The next entry must recover, not stall."""

    def test_init_turn_recovers_when_history_ends_with_user(self) -> None:
        # Brownfield init: an earlier vision-update prompt was appended to
        # brainstormer_messages but the LLM call that followed raised, so the
        # message log is now [user_only].
        session = make_session(
            vision_statement={"summary": "existing"},
            brainstormer_messages=[
                {
                    "role": "user",
                    "content": "I have an existing vision statement...",
                }
            ],
        )
        with mock_litellm_stream("Hi! Let's review your existing vision."):
            output = collect(brainstormer.run(None, session, session["llm_config"]))

        # The agent must have produced output (didn't silently return zero
        # chunks via a stale-replay path).
        assert "existing vision" in output.lower()
        # And history ends correctly with the new assistant turn.
        assert session["brainstormer_messages"][-1]["role"] == "assistant"

    def test_user_submit_after_failure_routes_to_fresh_start(self) -> None:
        # The previous turn failed before the assistant reply could be
        # committed, leaving phaser_messages = [seed_orphan]. The user's new
        # message is a reply to UI text the agent never actually committed —
        # if we just dropped the orphan and appended the new message, the LLM
        # would be called with that reply alone, stripped of all seed context,
        # and would hallucinate an "I'm ready to help — please share your
        # project info" greeting. The recovery instead routes through the
        # fresh-start branch so the LLM gets the seed (or the static greeting
        # for greenfield projects with no vision/code_review).
        session = make_session(
            brainstormer_messages=[
                {"role": "user", "content": "earlier orphan"},
            ]
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(
                brainstormer.run("new message", session, session["llm_config"])
            )

        # No vision and no code review → fresh-start branch yields a static
        # greeting and does NOT call the LLM. The user's "new message" reply
        # is silently discarded since it was responding to nothing real.
        mock_llm.assert_not_called()
        assert "Brainstormer" in output

    def test_user_submit_after_failure_reseeds_brownfield_context(self) -> None:
        # Same orphan setup but with a vision_statement present (brownfield
        # revision mode). Recovery must re-seed the brownfield context rather
        # than calling the LLM with just the new user reply.
        vision = {"vision_statement": {"name": "CheckersApp"}}
        session = make_session(
            vision_statement=vision,
            brainstormer_messages=[
                {"role": "user", "content": "earlier orphan"},
            ],
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [
                    make_stream_chunk("Welcome back"),
                    make_stream_chunk("", finish_reason="stop"),
                ]
            )
            collect(brainstormer.run("new message", session, session["llm_config"]))

        sent = mock_llm.call_args[1]["messages"]
        user_content = " ".join(
            m["content"]
            for m in sent
            if m["role"] == "user" and isinstance(m["content"], str)
        )
        # The brownfield re-seed must include the existing vision so the
        # LLM has context, not just the user's "new message" reply alone.
        assert "CheckersApp" in user_content
        assert "new message" not in user_content


# ---------------------------------------------------------------------------
# Brainstormer branch tests
# ---------------------------------------------------------------------------


class TestBrainstormerBranches:
    def test_format_vision_handles_string_features(self) -> None:
        # Real LLMs sometimes emit features as bare strings rather than the
        # canonical {Name: {description, example}} shape — this used to crash
        # with `'str' object has no attribute 'items'` and surface raw JSON
        # plus an AttributeError to the user.
        from spec4.agents.brainstormer import format_vision_as_text

        vision = {
            "vision_statement": {
                "name": "Chrome & Carbon",
                "vision": {
                    "purpose": "demo",
                    "key_features_mvp": ["AI Recommendations", "User Reviews"],
                    "future_enhancements": ["Predictive AI"],
                },
            }
        }
        out = format_vision_as_text(vision)
        assert "AI Recommendations" in out
        assert "User Reviews" in out
        assert "Continue to Agentifier" in out

    def test_format_vision_handles_flat_named_features(self) -> None:
        from spec4.agents.brainstormer import format_vision_as_text

        vision = {
            "vision_statement": {
                "name": "App",
                "vision": {
                    "key_features_mvp": [
                        {"name": "AI Recs", "description": "Personalized suggestions"},
                    ],
                },
            }
        }
        out = format_vision_as_text(vision)
        assert "AI Recs" in out
        assert "Personalized suggestions" in out

    def test_format_vision_handles_string_monetization(self) -> None:
        # Real LLMs sometimes emit `monetization` as a bare string rather than
        # the canonical {current, future_options} dict — this used to crash with
        # `'str' object has no attribute 'get'` and drop to the minimal fallback
        # display.
        from spec4.agents.brainstormer import format_vision_as_text

        vision = {
            "vision_statement": {
                "name": "App",
                "vision": {
                    "purpose": "demo",
                    "monetization": "Free with optional donations",
                },
            }
        }
        out = format_vision_as_text(vision)
        assert "Monetization" in out
        assert "Free with optional donations" in out

    def test_transition_includes_review_offer(self) -> None:
        from spec4.agents.brainstormer import _VISION_TRANSITION

        assert "Would you like to review the current vision?" in _VISION_TRANSITION

    def test_yes_after_review_offer_shows_vision(self) -> None:
        # Answering the review offer with a bare "yes" in the completed state
        # re-renders the stored vision deterministically — no LLM round-trip —
        # using the lighter review footer (not the transition with its offer, so
        # a follow-up "yes" can't re-loop).
        vision = {
            "vision_statement": {
                "name": "Checkers",
                "vision": {"purpose": "play checkers online"},
            }
        }
        session = make_session(
            brainstormer_state=STATE_VISION_COMPLETE,
            vision_statement=vision,
            brainstormer_messages=[
                {"role": "user", "content": "done"},
                {
                    "role": "assistant",
                    "content": (
                        "**Vision Statement: Checkers**\n\n...\n\n"
                        "Would you like to review the current vision? (yes/no)"
                    ),
                },
            ],
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            out = collect(brainstormer.run("yes", session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "Checkers" in out
        assert "play checkers online" in out
        assert "That's the current vision" in out
        assert "Would you like to review the current vision?" not in out
        assert "Continue to Agentifier" in out
        # Deterministic render leaves the LLM log and state untouched.
        assert session["brainstormer_messages"][-1]["content"].endswith("(yes/no)")
        assert session["brainstormer_state"] == STATE_VISION_COMPLETE

    def test_y_shortform_shows_review(self) -> None:
        vision = {"vision_statement": {"name": "App", "vision": {"purpose": "x"}}}
        session = make_session(
            brainstormer_state=STATE_VISION_COMPLETE,
            vision_statement=vision,
            brainstormer_messages=[
                {
                    "role": "assistant",
                    "content": "Would you like to review the current vision? (yes/no)",
                },
            ],
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            out = collect(brainstormer.run("  Y ", session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "App" in out

    def test_yes_confirming_revision_is_not_review(self) -> None:
        # A "yes" that confirms a pending revision — where the latest assistant
        # turn is a proposal, not the review offer — must reach the LLM, not be
        # hijacked into a review render.
        vision = {"vision_statement": {"name": "App", "vision": {"purpose": "x"}}}
        session = make_session(
            brainstormer_state=STATE_VISION_COMPLETE,
            vision_statement=vision,
            brainstormer_messages=[
                {"role": "user", "content": "rename it to Foo"},
                {
                    "role": "assistant",
                    "content": "Got it — shall I rename the project to Foo?",
                },
            ],
        )
        with mock_litellm_stream("Updating the name now."):
            out = collect(brainstormer.run("yes", session, session["llm_config"]))
        assert "Updating the name now." in out
        assert "That's the current vision" not in out

    def test_question_after_offer_reaches_llm(self) -> None:
        # A non-affirmative reply to the offer (e.g. a question) is not a review
        # request and falls through to the LLM.
        vision = {"vision_statement": {"name": "App", "vision": {"purpose": "x"}}}
        session = make_session(
            brainstormer_state=STATE_VISION_COMPLETE,
            vision_statement=vision,
            brainstormer_messages=[
                {
                    "role": "assistant",
                    "content": "Would you like to review the current vision? (yes/no)",
                },
            ],
        )
        with mock_litellm_stream("Here is an answer."):
            out = collect(
                brainstormer.run(
                    "what are the features?", session, session["llm_config"]
                )
            )
        assert "Here is an answer." in out

    def test_run_uses_fallback_display_when_format_raises(self) -> None:
        # Even with a hardened formatter, an unexpected schema shape must not
        # leak raw JSON to the chat. The agent's run() wraps the formatter in
        # try/except and falls back to a minimal display that still includes
        # the project name and the transition message.
        session = make_session(
            brainstormer_messages=[
                {"role": "user", "content": "ready"},
                {
                    "role": "assistant",
                    "content": (
                        "```json\n"
                        '{"vision_statement": {"name": "App", "vision": "desc"}}\n'
                        "```"
                    ),
                },
            ],
            brainstormer_resumed=True,
        )
        with patch(
            "spec4.agents.brainstormer.format_vision_as_text",
            side_effect=AttributeError("'str' object has no attribute 'items'"),
        ):
            with mock_litellm_stream(
                '```json\n{"vision_statement": {"name": "App", "vision": "desc"}}\n```'
            ):
                collect(brainstormer.run("yes", session, session["llm_config"]))
        override = session.get("_display_override")
        assert override is not None
        assert "App" in override
        assert "Continue to Agentifier" in override
        # The agent still records vision_statement and flips state to complete.
        assert session["brainstormer_state"] == STATE_VISION_COMPLETE
        assert session["vision_statement"] == {
            "vision_statement": {"name": "App", "vision": "desc"}
        }

    def test_reentry_replays_last_assistant_message(self) -> None:
        session = make_session(
            brainstormer_resumed=True,
            brainstormer_messages=[
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "Existing response"},
            ],
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "Existing response" in output

    def test_reentry_drops_orphan_user_and_falls_through(self) -> None:
        # An interrupted previous turn left a user message orphaned in history.
        # Re-entry must drop it and proceed to the fresh-start greeting (no
        # vision/code_review in this session), not silently yield zero
        # chunks.
        session = make_session(
            brainstormer_messages=[{"role": "user", "content": "hi"}]
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert output != ""
        assert session["brainstormer_messages"] == []

    def test_preloaded_vision_calls_llm(self) -> None:
        vision = {"name": "MyApp", "vision": "desc"}
        session = make_session(vision_statement=vision)
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [
                    make_stream_chunk("Summary"),
                    make_stream_chunk("", finish_reason="stop"),
                ]
            )
            output = collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_called_once()
        assert "Summary" in output

    def test_preloaded_vision_seed_contains_vision_name(self) -> None:
        vision = {"name": "MyApp", "vision": "desc"}
        session = make_session(vision_statement=vision)
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [make_stream_chunk("Ok"), make_stream_chunk("", finish_reason="stop")]
            )
            collect(brainstormer.run(None, session, session["llm_config"]))
        sent_messages = mock_llm.call_args[1]["messages"]
        assert any(
            "MyApp" in m["content"] for m in sent_messages if m["role"] != "system"
        )

    def test_code_review_seed_calls_llm(self) -> None:
        review = {"code_review": {"is_software_project": True}}
        session = make_session(code_review=review, vision_statement=None)
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [
                    make_stream_chunk("Review"),
                    make_stream_chunk("", finish_reason="stop"),
                ]
            )
            collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_called_once()


class TestBrainstormerRevisionMode:
    """Revision mode: when a prior implemented vision exists, Brainstormer scopes
    to the revision delta and the round's delta is folded into an accumulating
    ``revision_history`` deterministically (code owns the version integers)."""

    FENCE = "```json\n{}\n```"

    def _emit(self, vision_statement: dict, revision: object) -> Any:
        from json import dumps

        payload = {"vision_statement": vision_statement}
        if revision is not None:
            payload["revision"] = revision
        text = self.FENCE.format(dumps(payload))
        return iter(
            [make_stream_chunk(text), make_stream_chunk("", finish_reason="stop")]
        )

    def _implement(self, project_manager, wd: str, version: int, vision: dict) -> None:
        project_manager.save_vision(wd, vision, version)
        project_manager.get_version_dir(wd, version).joinpath("IMPLEMENTED").write_text(
            ""
        )

    # ----- pure merge -----

    def test_stamp_normalizes_block(self) -> None:
        from spec4.agents.brainstormer import stamp_revision_block

        out = stamp_revision_block(
            {"goal": "g", "changes": {"added": ["X"]}, "rationale": "r"}, 2, 1
        )
        assert out == {
            "version": 2,
            "based_on_version": 1,
            "goal": "g",
            "changes": {"added": ["X"], "modified": [], "removed": []},
            "rationale": "r",
        }

    def test_apply_first_revision_empty_base(self) -> None:
        from spec4.agents.brainstormer import apply_revision_history

        emitted = {"vision_statement": {"name": "A"}, "revision": {"goal": "g"}}
        prior = {"vision_statement": {"name": "A"}}  # no prior history
        out = apply_revision_history(emitted, prior, None, 1, 0)
        hist = out["vision_statement"]["revision_history"]
        assert len(hist) == 1
        assert hist[0]["version"] == 1 and hist[0]["based_on_version"] == 0
        assert "revision" not in out

    def test_apply_accumulates_on_prior_history(self) -> None:
        from spec4.agents.brainstormer import apply_revision_history

        prior = {
            "vision_statement": {
                "name": "A",
                "revision_history": [{"version": 1, "based_on_version": 0}],
            }
        }
        emitted = {"vision_statement": {"name": "A"}, "revision": {"goal": "g2"}}
        out = apply_revision_history(emitted, prior, None, 2, 1)
        hist = out["vision_statement"]["revision_history"]
        assert [e["version"] for e in hist] == [1, 2]

    def test_apply_missing_block_preserves_prior_history(self) -> None:
        from spec4.agents.brainstormer import apply_revision_history

        prior = {
            "vision_statement": {
                "revision_history": [{"version": 1, "based_on_version": 0}]
            }
        }
        emitted = {"vision_statement": {"name": "A"}}  # model emitted no revision
        out = apply_revision_history(emitted, prior, None, 2, 1)
        # No new entry, but prior lineage is never dropped.
        hist = out["vision_statement"]["revision_history"]
        assert [e["version"] for e in hist] == [1]

    def test_apply_reentry_recovers_current_round_entry(self) -> None:
        from spec4.agents.brainstormer import apply_revision_history

        prior = {"vision_statement": {"revision_history": []}}
        # The current session vision already carries this round's (v1) entry.
        current = {
            "vision_statement": {
                "revision_history": [{"version": 1, "based_on_version": 0, "goal": "g"}]
            }
        }
        emitted = {"vision_statement": {"name": "A"}}  # re-edit, no fresh block
        out = apply_revision_history(emitted, prior, current, 1, 0)
        hist = out["vision_statement"]["revision_history"]
        assert len(hist) == 1 and hist[0]["goal"] == "g"

    # ----- seed selection + end-to-end -----

    def test_revision_seed_used_when_prior_vision_exists(self, tmp_path: Any) -> None:
        from spec4 import project_manager

        wd = str(tmp_path)
        self._implement(
            project_manager, wd, 0, {"vision_statement": {"name": "Checkers"}}
        )
        project_manager.save_code_review(wd, {"code_review": {}}, 1)
        session = make_session(
            working_dir=wd, code_review={"code_review": {}}, vision_statement=None
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = self._emit({"name": "Checkers"}, None)
            collect(brainstormer.run(None, session, session["llm_config"]))
        seed = session["brainstormer_messages"][0]["content"]
        assert "REVISION mode" in seed
        assert "Checkers" in seed and "read-only" in seed

    def test_revision_round_merges_history_end_to_end(self, tmp_path: Any) -> None:
        from spec4 import project_manager

        wd = str(tmp_path)
        self._implement(
            project_manager, wd, 0, {"vision_statement": {"name": "Checkers"}}
        )
        project_manager.save_code_review(wd, {"code_review": {}}, 1)
        session = make_session(
            working_dir=wd, code_review={"code_review": {}}, vision_statement=None
        )
        rev = {
            "goal": "Add online play",
            "changes": {"added": ["Online Multiplayer"], "modified": [], "removed": []},
            "rationale": "users asked",
        }
        new_vs = {
            "name": "Checkers",
            "key_features_mvp": [{"Online Multiplayer": {"description": "remote"}}],
        }
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = self._emit(new_vs, rev)
            collect(brainstormer.run(None, session, session["llm_config"]))
        hist = session["vision_statement"]["vision_statement"]["revision_history"]
        assert len(hist) == 1
        assert hist[0]["version"] == 1 and hist[0]["based_on_version"] == 0
        assert hist[0]["changes"]["added"] == ["Online Multiplayer"]
        assert "revision" not in session["vision_statement"]

    def test_greenfield_gets_no_revision_history(self, tmp_path: Any) -> None:
        # No implemented round -> not revision mode -> history untouched.
        session = make_session(working_dir=str(tmp_path), vision_statement=None)
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = self._emit({"name": "Fresh"}, None)
            collect(brainstormer.run("done", session, session["llm_config"]))
        vs = session["vision_statement"]["vision_statement"]
        assert "revision_history" not in vs


class TestBrainstormerUnparseableArtifact:
    """D-BR-P3: the D-SC-P3 fix applied to Brainstormer."""

    _TRUNCATED = '```json\n{"vision_statement": {"name": "TodoApp", "vis'
    _VALID = (
        '```json\n{"vision_statement": {"name": "TodoApp", '
        '"vision": "A simple task manager"}}\n```'
    )

    def _session(self) -> dict[str, Any]:
        session = make_session()
        session["brainstormer_messages"] = [
            {"role": "user", "content": "I want a todo app"},
            {"role": "assistant", "content": "Who is it for?"},
        ]
        return session

    def _run(self, *replies: str) -> tuple[dict[str, Any], str, list[Any]]:
        session = self._session()
        fake_completion, calls = _reply_sequence(*replies)
        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            output = collect(
                brainstormer.run("looks good", session, session["llm_config"])
            )
        return session, output, calls

    def test_truncated_block_is_re_asked(self) -> None:
        session, _, calls = self._run(self._TRUNCATED, self._VALID)
        assert len(calls) >= 2, "the unreadable artifact must trigger one re-ask"
        assert session["brainstormer_state"] == STATE_VISION_COMPLETE
        assert session["vision_statement"]["vision_statement"]["name"] == "TodoApp"

    def test_turn_never_ends_silently(self) -> None:
        session, output, _ = self._run(self._TRUNCATED, self._TRUNCATED)
        assert session["_display_override"]
        assert output.strip(), "the turn yielded nothing visible"
        last = session["brainstormer_messages"][-1]
        assert last["role"] == "assistant"
        assert last["content"] == session["_display_override"]

    def test_failed_reask_leaves_no_dead_end_user_turn(self) -> None:
        session, _, _ = self._run(self._TRUNCATED, self._TRUNCATED)
        assert not [
            m
            for m in session["brainstormer_messages"]
            if m["role"] == "user" and "could not be read" in m["content"]
        ]

    def test_state_is_not_advanced_when_both_attempts_fail(self) -> None:
        session, _, _ = self._run(self._TRUNCATED, self._TRUNCATED)
        assert session["brainstormer_state"] != STATE_VISION_COMPLETE
        assert session.get("vision_statement") is None

    def test_ordinary_prose_reply_is_left_alone(self) -> None:
        session = self._session()
        with mock_litellm_stream("What type of users will use this app?") as llm:
            output = collect(
                brainstormer.run("not yet", session, session["llm_config"])
            )
        assert llm.call_count == 1, "a prose reply must not trigger a re-ask"
        assert "What type of users" in output
        assert session["brainstormer_state"] != STATE_VISION_COMPLETE
