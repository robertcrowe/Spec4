"""Tests for the ``required_infrastructure`` tier registry.

Covers the real tier YAML (every tier declares the field; the values match the
ratified registry; shared components dedup by id), the cross_cutting guard
(D-I7: substrate ids never name a project-wide concern), and the loader
validation of the new field (required for tiers, forbidden for mechanisms,
must be a list of strings).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spec4.agentifier.pattern_loader import (
    PatternValidationError,
    _build_pattern,
    load_patterns,
)

# The ratified per-tier registry (see INFRA_DECISIONS.md / session handoff).
EXPECTED: dict[str, list[str]] = {
    "deterministic": [],
    "embeddings": ["embedding_pipeline", "vector_index"],
    "single_call": [],
    "rag": ["chunking_pipeline", "retriever", "embedding_pipeline", "vector_index"],
    "tool_agent": ["tool_execution_harness"],
    "chained_calls": ["pipeline_runner"],
    "planning_agent": ["agent_loop_runtime", "tool_execution_harness"],
    "orchestrated_subagents": ["subagent_orchestration_runtime"],
    "multi_agent_collaboration": ["agent_message_bus", "protocol_runtime"],
}

# Ids that are cross_cutting concerns, not tier substrate — must never appear in
# any tier's required_infrastructure (D-I7). A structural guard on the YAML.
FORBIDDEN_CROSS_CUTTING = frozenset({
    "provider",
    "provider_strategy",
    "model_access",
    "model_provider",
    "prompt_versioning",
    "prompt_management",
    "tool_protocol",
    "mcp",
    "observability",
    "evaluation",
    "guardrails",
})


class TestRealRegistry:
    def test_every_tier_declares_the_field(self) -> None:
        tiers, _ = load_patterns()
        for t in tiers:
            assert isinstance(t.required_infrastructure, list)
            assert all(isinstance(c, str) for c in t.required_infrastructure)

    def test_registry_matches_ratified(self) -> None:
        tiers, _ = load_patterns()
        actual = {t.name: t.required_infrastructure for t in tiers}
        assert actual == EXPECTED

    def test_shared_components_dedup_by_id(self) -> None:
        tiers, _ = load_patterns()
        by_name = {t.name: set(t.required_infrastructure) for t in tiers}
        shared = {"embedding_pipeline", "vector_index"}
        # The embedding index is shared identity between embeddings and rag.
        assert shared <= by_name["embeddings"]
        assert shared <= by_name["rag"]

    def test_tool_harness_shared_between_tool_and_planning(self) -> None:
        tiers, _ = load_patterns()
        by_name = {t.name: set(t.required_infrastructure) for t in tiers}
        assert "tool_execution_harness" in by_name["tool_agent"]
        assert "tool_execution_harness" in by_name["planning_agent"]


class TestCrossCuttingGuard:
    def test_no_cross_cutting_ids_in_registry(self) -> None:
        tiers, _ = load_patterns()
        for t in tiers:
            offending = set(t.required_infrastructure) & FORBIDDEN_CROSS_CUTTING
            assert not offending, (
                f"tier '{t.name}' names cross_cutting id(s) {offending} in "
                "required_infrastructure — substrate only (D-I7)."
            )


# ---------------------------------------------------------------------------
# Loader validation of the new field
# ---------------------------------------------------------------------------

_SECTIONS = "\n".join(
    [
        "## Description",
        "A minimal valid pattern body for loader tests.",
        "## When it works",
        "- always",
        "## When it doesn't",
        "- never",
        "## Over-engineering signs",
        "- none",
        "## Under-engineering signs",
        "- none",
        "## References",
        "- https://example.com",
        "",
    ]
)


def _write(path: Path, frontmatter: str) -> Path:
    path.write_text(f"---\n{frontmatter}\n---\n\n{_SECTIONS}", encoding="utf-8")
    return path


def _tier_fm(name: str, *, infra_line: str | None) -> str:
    lines = [
        f"name: {name}",
        "category: tier",
        'library_version: "1.0.0"',
        'last_reviewed: "2026-05-30"',
        "tier_order: 3",
        'cost_range_usd: "$0.01"',
        'latency_range_seconds: "1-2"',
        "references:",
        "  - https://example.com",
    ]
    if infra_line is not None:
        lines.insert(7, infra_line)
    return "\n".join(lines)


class TestLoaderValidation:
    def test_tier_missing_field_rejected(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "03_x.md", _tier_fm("x", infra_line=None))
        with pytest.raises(PatternValidationError, match="required_infrastructure"):
            _build_pattern(p, "tier")

    def test_tier_non_list_field_rejected(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path / "03_x.md",
            _tier_fm("x", infra_line="required_infrastructure: not_a_list"),
        )
        with pytest.raises(PatternValidationError, match="list of"):
            _build_pattern(p, "tier")

    def test_tier_non_string_items_rejected(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path / "03_x.md",
            _tier_fm("x", infra_line="required_infrastructure: [1, 2]"),
        )
        with pytest.raises(PatternValidationError, match="list of"):
            _build_pattern(p, "tier")

    def test_tier_empty_list_accepted(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path / "03_x.md",
            _tier_fm("x", infra_line="required_infrastructure: []"),
        )
        pattern = _build_pattern(p, "tier")
        assert pattern.required_infrastructure == []

    def test_mechanism_declaring_field_rejected(self, tmp_path: Path) -> None:
        fm = "\n".join(
            [
                "name: m",
                "category: mechanism",
                'library_version: "1.0.0"',
                'last_reviewed: "2026-05-30"',
                "required_infrastructure: []",
                "references:",
                "  - https://example.com",
            ]
        )
        p = _write(tmp_path / "m.md", fm)
        with pytest.raises(PatternValidationError, match="tier-only"):
            _build_pattern(p, "mechanism")
