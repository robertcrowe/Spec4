"""Lever 1 (D-BS2 id foundation): stable feature ids on ``key_features_mvp``.

Covers the deterministic ``slug`` convention, the ``_assign_feature_ids`` stamp,
the load-bearing property that a Brainstormer-assigned id coincides with the
id the downstream coverage check derives (so the join is deterministic, not a
brittle name-match), and the ``run()`` hook that applies the stamp on the real
vision-completion path.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from spec4.agents import brainstormer
from spec4.agents._phase_coverage import _slug as coverage_slug
from spec4.agents._utils import slug
from spec4.app_constants import STATE_IN_PROGRESS, STATE_VISION_COMPLETE


# ---------------------------------------------------------------------------
# Test helpers (kept local so this file stands alone)
# ---------------------------------------------------------------------------


def _make_session(**overrides: Any) -> dict[str, Any]:
    session: dict[str, Any] = {
        "active_agent": "brainstormer",
        "working_dir": None,
        "code_review": None,
        "brainstormer_state": STATE_IN_PROGRESS,
        "brainstormer_messages": [],
        "vision_statement": None,
        "llm_config": {"model": "test-model", "api_key": "test-key"},
    }
    session.update(overrides)
    return session


def _make_stream_chunk(content: str, finish_reason: str | None = None) -> MagicMock:
    chunk = MagicMock()
    chunk.choices[0].delta.content = content
    chunk.choices[0].delta.tool_calls = None
    chunk.choices[0].finish_reason = finish_reason
    return chunk


def _mock_stream(text: str) -> Any:
    chunks = [_make_stream_chunk(c) for c in text]
    chunks.append(_make_stream_chunk("", finish_reason="stop"))
    return patch("spec4.llm.litellm.completion", return_value=iter(chunks))


def _envelope(features: list[Any]) -> dict[str, Any]:
    return {
        "vision_statement": {
            "name": "App",
            "vision": {
                "purpose": "A thing.",
                "key_features_mvp": features,
            },
        }
    }


def _mvp(vision: dict[str, Any]) -> list[Any]:
    return vision["vision_statement"]["vision"]["key_features_mvp"]


# ---------------------------------------------------------------------------
# slug()
# ---------------------------------------------------------------------------


class TestSlug:
    def test_lowercases_and_collapses_non_alnum(self) -> None:
        assert slug("AI Recommendations") == "ai_recommendations"
        assert slug("User_Reviews") == "user_reviews"
        assert slug("Two-Factor Auth!") == "two_factor_auth_"

    def test_empty_yields_empty(self) -> None:
        assert slug("") == ""

    def test_already_slug_is_stable(self) -> None:
        assert slug("recipe_semantic_search") == "recipe_semantic_search"

    def test_coincides_with_coverage_slug(self) -> None:
        # The load-bearing D-BS2 property: the id Brainstormer stamps is the same
        # id the Phaser coverage check derives, so the join is deterministic.
        for name in (
            "AI Recommendations",
            "User_Reviews",
            "Ingredient Extraction",
            "Two-Factor Auth",
            "Real-time Chat (beta)",
            "checkout",
        ):
            assert slug(name) == coverage_slug(name)


# ---------------------------------------------------------------------------
# _assign_feature_ids()
# ---------------------------------------------------------------------------


class TestAssignFeatureIds:
    def test_stamps_canonical_entries(self) -> None:
        vision = _envelope(
            [
                {"AI Recommendations": {"description": "d", "example": "e"}},
                {"User Reviews": {"description": "d", "example": "e"}},
            ]
        )
        brainstormer._assign_feature_ids(vision)
        feats = _mvp(vision)
        assert feats[0]["AI Recommendations"]["id"] == "ai_recommendations"
        assert feats[1]["User Reviews"]["id"] == "user_reviews"

    def test_id_equals_slug_of_name_invariant(self) -> None:
        vision = _envelope(
            [{"Some Weird Name!": {"description": "d"}}]
        )
        brainstormer._assign_feature_ids(vision)
        val = _mvp(vision)[0]["Some Weird Name!"]
        assert val["id"] == slug("Some Weird Name!")

    def test_reassigns_from_current_name(self) -> None:
        # A carried-forward id must not survive a rename: id always tracks name.
        vision = _envelope(
            [{"Renamed Feature": {"description": "d", "id": "stale_id"}}]
        )
        brainstormer._assign_feature_ids(vision)
        assert _mvp(vision)[0]["Renamed Feature"]["id"] == "renamed_feature"

    def test_handles_flat_shape(self) -> None:
        vision = _envelope([{"name": "Flat Feature", "description": "d"}])
        brainstormer._assign_feature_ids(vision)
        assert _mvp(vision)[0]["id"] == "flat_feature"

    def test_leaves_bare_strings_untouched(self) -> None:
        vision = _envelope(["Just A String"])
        brainstormer._assign_feature_ids(vision)
        assert _mvp(vision) == ["Just A String"]

    def test_idempotent(self) -> None:
        vision = _envelope([{"Feature One": {"description": "d"}}])
        brainstormer._assign_feature_ids(vision)
        once = _mvp(vision)[0]["Feature One"]["id"]
        brainstormer._assign_feature_ids(vision)
        assert _mvp(vision)[0]["Feature One"]["id"] == once

    def test_missing_features_is_noop(self) -> None:
        vision = {"vision_statement": {"name": "App", "vision": "a string vision"}}
        # Must not raise on a plain-string vision body.
        brainstormer._assign_feature_ids(vision)
        assert vision["vision_statement"]["vision"] == "a string vision"

    def test_non_dict_input_is_noop(self) -> None:
        assert brainstormer._assign_feature_ids(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# run() hook — ids stamped on the real completion path
# ---------------------------------------------------------------------------


class TestRunStampsIds:
    def test_completion_hook_stamps_ids(self) -> None:
        session = _make_session()
        vision_json = (
            '{"vision_statement": {"name": "TodoApp", "vision": '
            '{"purpose": "Track tasks.", "key_features_mvp": '
            '[{"Task List": {"description": "See tasks.", "example": "x"}}]}}}'
        )
        response = f"Here it is.\n\n```json\n{vision_json}\n```"
        with _mock_stream(response):
            "".join(brainstormer.run("finalize it", session, session["llm_config"]))

        assert session["brainstormer_state"] == STATE_VISION_COMPLETE
        feats = _mvp(session["vision_statement"])
        assert feats[0]["Task List"]["id"] == "task_list"
