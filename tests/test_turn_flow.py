"""``_turn_flow``'s revision context: the updated code review, per agent (D-EV6 a′).

The "upstream inputs have been updated" message pastes the vision, AI features
and stack as JSON. The code review is different: the agents that read it
through a field view at seed time (``AGENT_REVIEW_VIEWS``) receive the update
through the same view, so the two are directly comparable in the agent's own
history; any other agent receives the ``review`` block as JSON — never the
``scan`` layer or the version, which are not the model's to reason about.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from spec4.agents._code_review_context import (
    AGENT_REVIEW_VIEWS,
    PHASER_FIELD_GUIDANCE,
)
from spec4.agents._turn_flow import (
    build_revision_context,
    maybe_inject_staleness_question,
)
from spec4.project_manager import _STALE_DEPENDENCIES
from tests._review_helpers import review_envelope

_REVIEW = review_envelope(
    commands={"test": "uv run pytest"},
    persistence={"databases": [{"engine": "PostgreSQL"}]},
    scan={"inventory": {"files_total": 3}},
)


def _ctx(review: dict[str, Any], agent: str | None) -> str:
    return build_revision_context({"code_review": review}, ["code review"], agent)


class TestRevisionReviewBlock:
    def test_viewed_agent_gets_the_view_not_the_json(self) -> None:
        ctx = build_revision_context(
            {"code_review": _REVIEW}, ["code review"], "phaser"
        )
        assert "Updated code review, by block:" in ctx
        assert f"_{PHASER_FIELD_GUIDANCE['persistence']}_" in ctx
        assert "- test: uv run pytest" in ctx
        assert "- **PostgreSQL**" in ctx
        assert "```json" not in ctx
        assert "files_total" not in ctx  # scan is not the model's

    def test_other_agent_gets_the_review_block_as_json(self) -> None:
        ctx = build_revision_context(
            {"code_review": _REVIEW}, ["code review"], "deployer"
        )
        assert "Updated code review:\n\n```json" in ctx
        body = json.loads(ctx.split("```json\n", 1)[1].split("```", 1)[0])
        assert body["commands"] == {"test": "uv run pytest"}
        assert "scan" not in body
        assert "schema_version" not in body
        assert "code_review" not in body

    def test_no_agent_falls_back_to_json(self) -> None:
        ctx = build_revision_context({"code_review": _REVIEW}, ["code review"])
        assert "Updated code review:\n\n```json" in ctx

    def test_viewed_agent_with_an_empty_view_falls_back_to_json(self) -> None:
        # Nothing in Phaser's tuple → the block is still delivered, as JSON.
        review = review_envelope(languages=[{"name": "Go"}])
        ctx = build_revision_context({"code_review": review}, ["code review"], "phaser")
        assert "Updated code review:\n\n```json" in ctx
        assert '"Go"' in ctx

    def test_not_stale_or_absent_emits_nothing(self) -> None:
        ctx = build_revision_context({"code_review": _REVIEW}, ["vision"], "phaser")
        assert "code review" not in ctx
        ctx = build_revision_context({"code_review": None}, ["code review"], "phaser")
        assert "code review" not in ctx

    def test_every_viewed_agent_depends_on_the_code_review(self) -> None:
        # A view for an agent whose staleness map never names the review
        # would be dead; the keys are the names ``detect_stale_inputs`` uses.
        for agent in AGENT_REVIEW_VIEWS:
            _, inputs = _STALE_DEPENDENCIES[agent]
            assert ("code review", "code_review.json") in inputs


class TestStalenessQuestionCarriesTheAgent:
    def test_phaser_reentry_pastes_the_view(self, tmp_path: Path) -> None:
        v0 = tmp_path / ".spec4" / "v0"
        (v0 / "phases").mkdir(parents=True)
        (v0 / "phases" / "phase1.md").write_text("x")
        (v0 / "code_review.json").write_text(json.dumps(_REVIEW))
        os.utime(v0 / "phases" / "phase1.md", (1000, 1000))
        os.utime(v0 / "code_review.json", (2000, 2000))
        session: dict[str, Any] = {"working_dir": str(tmp_path), "code_review": _REVIEW}
        msgs: list[dict[str, Any]] = []
        question = maybe_inject_staleness_question(session, "phaser", msgs)
        assert question is not None and "code review" in question
        assert "Updated code review, by block:" in msgs[0]["content"]
        assert "```json" not in msgs[0]["content"]
