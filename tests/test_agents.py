"""Tests of behaviour the agents share: the recap on re-entry, and the
suppressed-artifact predicate.

Phase 8's D9 split the per-agent classes into their own files (``PHASE8_RECORD.md``
§25). These two span agents, so they stay here.

Keep the three helper re-exports: ``test_stack_shape_resilience.py:41`` imports them.
"""

from typing import Any
from unittest.mock import patch
from spec4.agents import brainstormer, deployer, stack_advisor
from spec4.agents._reask import suppressed_as_artifact
from spec4.app_constants import STATE_VISION_COMPLETE
from tests._agent_helpers import collect, make_session, mock_litellm_stream


class TestResumeSummary:
    """When the user navigates back to an in-progress agent after a break,
    replaying the last assistant message verbatim drops them into a
    mid-thought sentence with no surrounding context. Instead, the first
    re-entry per session-store lifetime should inject a synthetic user
    message asking the LLM for a recap-then-continue."""

    def _in_progress_session(self, agent: str, **overrides: Any) -> dict[str, Any]:
        msgs_key = f"{agent}_messages"
        return make_session(
            active_agent=agent,
            **{
                msgs_key: [
                    {"role": "user", "content": "earlier turn"},
                    {
                        "role": "assistant",
                        "content": (
                            "Good. Now I understand how Vercel handles env "
                            "variables. For a React + Vite SPA you likely won't "
                            "need many secrets at this stage..."
                        ),
                    },
                ],
                **overrides,
            },
        )

    def test_deployer_first_reentry_calls_llm_for_recap(self) -> None:
        session = self._in_progress_session(
            "deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            stack_statement={"name": "App"},
        )
        with mock_litellm_stream(
            "**Recap:** We've discussed deployment to Vercel. **Next:** "
            "what monitoring would you like?"
        ):
            output = collect(deployer.run(None, session, session["llm_config"]))

        assert "Recap" in output
        assert session["deployer_resumed"] is True
        # The synthetic user prompt is now in the message log, followed by the
        # LLM's recap reply.
        msgs = session["deployer_messages"]
        assert msgs[-2]["role"] == "user"
        assert "resuming this session" in msgs[-2]["content"]
        assert msgs[-1]["role"] == "assistant"
        assert "Recap" in msgs[-1]["content"]

    def test_second_reentry_replays_without_calling_llm(self) -> None:
        session = self._in_progress_session(
            "deployer",
            phases=[{"phase_number": 1, "phase_title": "Steel thread"}],
            deployer_resumed=True,
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(deployer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        # The original last assistant message comes back via replay.
        assert "Vercel" in output

    def test_completed_agent_replays_artifact_not_recap(self) -> None:
        # Brainstormer is done — the last assistant turn is the
        # formatted-vision text, not a mid-thought question. Replay is right.
        session = self._in_progress_session(
            "brainstormer",
            brainstormer_state=STATE_VISION_COMPLETE,
            vision_statement={"name": "App"},
        )
        # Overwrite the last assistant content with a finished-artifact display
        # and snapshot the message count to match (this is what the agent does
        # when it writes the artifact).
        session["brainstormer_messages"][-1]["content"] = "**Vision:** App\n\n…"
        session["brainstormer_artifact_msg_count"] = len(
            session["brainstormer_messages"]
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "Vision" in output
        assert session.get("brainstormer_resumed") is not True

    def test_completed_agent_in_revision_mode_does_recap(self) -> None:
        # Brainstormer finished earlier, the user has chatted further past the
        # artifact (e.g., asking for revisions). The last message is now a
        # mid-thought question — so the recap should fire even though the
        # agent's *_state is STATE_*_COMPLETE.
        session = self._in_progress_session(
            "brainstormer",
            brainstormer_state=STATE_VISION_COMPLETE,
            vision_statement={"name": "App"},
        )
        # Snapshot is older than the current message count, simulating
        # post-artifact revision turns.
        session["brainstormer_artifact_msg_count"] = 0
        with mock_litellm_stream(
            "**Recap:** We finalized your vision for App. **Next:** which "
            "section would you like to refine?"
        ):
            output = collect(brainstormer.run(None, session, session["llm_config"]))
        assert "Recap" in output
        assert session["brainstormer_resumed"] is True

    def test_empty_messages_skips_recap_branch(self) -> None:
        # Fresh start — the static greeting branch must run, not the
        # recap branch (which requires non-empty msgs).
        session = make_session(active_agent="brainstormer")
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(brainstormer.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "Brainstormer" in output
        assert session.get("brainstormer_resumed") is not True

    def test_staleness_takes_precedence_over_recap(self, tmp_path: Any) -> None:
        # Both staleness AND a fresh resume condition are present; the
        # staleness question must fire first (it's more important).
        import os

        v0 = tmp_path / ".spec4" / "v0"
        v0.mkdir(parents=True, exist_ok=True)
        for name, mtime in [("stack.json", 1_000.0), ("vision.json", 2_000.0)]:
            p = v0 / name
            p.write_text("{}", encoding="utf-8")
            os.utime(p, (mtime, mtime))
        session = self._in_progress_session(
            "stack_advisor",
            working_dir=str(tmp_path),
            vision_statement={"name": "App"},
            stack_statement={"name": "App"},
        )
        with patch("spec4.llm.litellm.completion") as mock_llm:
            output = collect(stack_advisor.run(None, session, session["llm_config"]))
        mock_llm.assert_not_called()
        assert "revise" in output.lower() or "updated" in output.lower()
        # Resume flag is NOT set — recap path didn't fire.
        assert session.get("stack_advisor_resumed") is not True


class TestSuppressedAsArtifact:
    """The shared predicate behind both the suppression and the D-SC-P3 guard."""

    def test_fence_at_the_start(self) -> None:
        assert suppressed_as_artifact("```json\n{}") is True

    def test_leading_whitespace_is_ignored(self) -> None:
        assert suppressed_as_artifact("\n\n  ```json\n{}") is True

    def test_bare_fence_counts(self) -> None:
        """Suppression does not check the language tag, so neither does this."""
        assert suppressed_as_artifact("```\n{}") is True

    def test_prose_does_not_count(self) -> None:
        assert suppressed_as_artifact("Here is the review:\n```json\n{}") is False

    def test_empty_does_not_count(self) -> None:
        assert suppressed_as_artifact("") is False
