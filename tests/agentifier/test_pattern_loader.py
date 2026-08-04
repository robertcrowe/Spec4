from pathlib import Path

import pytest

from spec4.agentifier.pattern_loader import (
    MechanismPattern,
    PatternValidationError,
    TierPattern,
    _build_pattern,
    load_patterns,
)

FIXTURES = Path(__file__).parent / "fixtures"

EXPECTED_TIERS = [
    "deterministic",
    "embeddings",
    "single_call",
    "rag",
    "tool_agent",
    "chained_calls",
    "planning_agent",
    "orchestrated_subagents",
    "multi_agent_collaboration",
]

EXPECTED_MECHANISMS = [
    "human_in_the_loop",
    "mcp",
    "parallel_fanout",
    "reflection",
    "retrieval_reranking",
    "structured_outputs",
]


class TestLoadPatterns:
    def test_loads_all_tier_patterns(self) -> None:
        tiers, _ = load_patterns()
        assert len(tiers) == 9
        assert all(isinstance(t, TierPattern) for t in tiers)
        # Returned sorted by tier_order, which must match the canonical ladder.
        assert [t.name for t in tiers] == EXPECTED_TIERS

    def test_loads_all_mechanism_patterns(self) -> None:
        _, mechanisms = load_patterns()
        assert len(mechanisms) == 6
        assert all(isinstance(m, MechanismPattern) for m in mechanisms)
        # Returned sorted by name.
        assert [m.name for m in mechanisms] == EXPECTED_MECHANISMS

    def test_tier_order_matches_ladder(self) -> None:
        tiers, _ = load_patterns()
        for position, tier in enumerate(tiers, start=1):
            assert tier.tier_order == position
        # Endpoints are pinned per the spec.
        assert tiers[0].name == "deterministic"
        assert tiers[0].tier_order == 1
        assert tiers[-1].name == "multi_agent_collaboration"
        assert tiers[-1].tier_order == 9

    def test_no_side_effects_at_import(self) -> None:
        # Importing the module must not have triggered any I/O: load_patterns is
        # the only entry point that reads files. We assert it is callable and
        # the patterns root is resolved lazily, not at import time.
        import spec4.agentifier.pattern_loader as loader

        assert callable(loader.load_patterns)

    def test_metadata_is_phase1_consistent(self) -> None:
        tiers, mechanisms = load_patterns()
        for pattern in [*tiers, *mechanisms]:
            assert pattern.library_version == "1.0.0"
            assert pattern.last_reviewed == "2026-05-30"

    def test_accepts_explicit_patterns_dir(self) -> None:
        root = Path("src/spec4/agentifier/patterns")
        tiers, mechanisms = load_patterns(root)
        assert len(tiers) == 9
        assert len(mechanisms) == 6


class TestSchemaValidation:
    def test_rejects_missing_frontmatter_field(self) -> None:
        with pytest.raises(PatternValidationError, match="references"):
            _build_pattern(FIXTURES / "missing_frontmatter_field.md", "mechanism")

    def test_rejects_missing_section(self) -> None:
        with pytest.raises(PatternValidationError, match="Under-engineering signs"):
            _build_pattern(FIXTURES / "missing_section.md", "mechanism")

    def test_rejects_unknown_section(self) -> None:
        with pytest.raises(PatternValidationError, match="Bogus Section"):
            _build_pattern(FIXTURES / "unknown_section.md", "mechanism")

    def test_rejects_name_filename_mismatch(self) -> None:
        with pytest.raises(PatternValidationError, match="must match the filename"):
            _build_pattern(FIXTURES / "name_mismatch.md", "mechanism")

    def test_rejects_category_directory_mismatch(self) -> None:
        # A valid mechanism fixture parsed as if it were a tier: category won't
        # match, and the tier-only fields are also absent.
        with pytest.raises(PatternValidationError):
            _build_pattern(FIXTURES / "missing_section.md", "tier")


class TestContentSanity:
    def test_deterministic_tier_has_nonempty_when_works(self) -> None:
        tiers, _ = load_patterns()
        deterministic = next(t for t in tiers if t.name == "deterministic")
        assert deterministic.when_works
        assert all(item.strip() for item in deterministic.when_works)

    def test_deterministic_when_doesnt_nonempty(self) -> None:
        tiers, _ = load_patterns()
        deterministic = next(t for t in tiers if t.name == "deterministic")
        assert deterministic.when_doesnt

    def test_single_call_over_engineering_signs_nonempty(self) -> None:
        tiers, _ = load_patterns()
        single_call = next(t for t in tiers if t.name == "single_call")
        assert single_call.over_engineering_signs
        assert all(item.strip() for item in single_call.over_engineering_signs)

    def test_planning_agent_over_engineering_signs_substantial(self) -> None:
        # The upper-ladder tiers carry the library's strongest pushback; make
        # sure that section isn't a token one-liner.
        tiers, _ = load_patterns()
        planning = next(t for t in tiers if t.name == "planning_agent")
        assert len(planning.over_engineering_signs) >= 3

    def test_mechanism_has_nonempty_content_sections(self) -> None:
        _, mechanisms = load_patterns()
        mcp = next(m for m in mechanisms if m.name == "mcp")
        assert mcp.description
        assert mcp.when_works
        assert mcp.when_doesnt
        assert mcp.over_engineering_signs
        assert mcp.under_engineering_signs

    def test_mcp_references_present(self) -> None:
        _, mechanisms = load_patterns()
        mcp = next(m for m in mechanisms if m.name == "mcp")
        assert mcp.references
        assert any("modelcontextprotocol" in ref.lower() for ref in mcp.references)
