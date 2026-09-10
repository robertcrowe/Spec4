"""Golden output for every ``_format_*_as_text`` renderer (cleanup Phase 1).

These five functions write frozen surfaces: their output is the assistant
message the developer reads at the end of an agent run, and it is persisted
into the session transcript. ``_format_stack_as_text`` is also the most
complex function in the repo (C901 61) and Phase 5's first decomposition
target, so its output has to be pinned before it is touched.

Each renderer is driven by a fixture built to reach as many of its branches as
one document can — scalar and list shapes, the string-where-a-list-belongs
cases the live models actually emit, empty containers that must be skipped —
and the result is compared byte for byte against a checked-in golden. The
existing behavioural tests (``test_stack_*``, ``test_agents``) say what a
line should contain; these say what the whole document is.

Characterization, not specification: a golden that looks odd is recorded in
``CLEANUP_INVENTORY.md``, not fixed here.
"""

from __future__ import annotations

import pytest

from spec4.agentifier.agentifier import _format_catalog_as_text, _format_spec_as_text
from spec4.agents.brainstormer import (
    _VISION_REVIEW_FOOTER,
    format_vision_as_text as _format_vision_as_text,
)
from spec4.agents.code_scanner import format_review_as_text as _format_review_as_text
from spec4.agents.stack_advisor import _format_stack_as_text
from tests._golden import assert_golden, load_fixture


class TestStackRenderer:
    def test_full_stack(self) -> None:
        assert_golden(
            "render_stack_full.md",
            _format_stack_as_text(load_fixture("stack_full.json")),
        )

    def test_minimal_stack(self) -> None:
        assert_golden(
            "render_stack_minimal.md",
            _format_stack_as_text(load_fixture("stack_minimal.json")),
        )

    def test_bare_stack_key_is_accepted_in_place_of_stack_spec(self) -> None:
        spec = load_fixture("stack_minimal.json")["stack_spec"]
        assert _format_stack_as_text({"stack": spec}) == _format_stack_as_text(
            {"stack_spec": spec}
        )
        assert _format_stack_as_text(spec) == _format_stack_as_text(
            {"stack_spec": spec}
        )

    def test_blocks_given_as_bare_strings(self) -> None:
        assert_golden(
            "render_stack_string_blocks.md",
            _format_stack_as_text(load_fixture("stack_string_blocks.json")),
        )

    def test_non_dict_stack_is_stringified(self) -> None:
        assert _format_stack_as_text({"stack_spec": "just a string"}) == "just a string"


class TestReviewRenderer:
    def test_full_review(self) -> None:
        assert_golden(
            "render_review_full.md",
            _format_review_as_text(load_fixture("review_full.json")),
        )

    def test_string_shaped_fields(self) -> None:
        assert_golden(
            "render_review_strings.md",
            _format_review_as_text(load_fixture("review_string_shapes.json")),
        )

    def test_not_a_software_project(self) -> None:
        assert_golden(
            "render_review_empty.md",
            _format_review_as_text(load_fixture("review_not_software.json")),
        )

    @pytest.mark.parametrize(
        ("cr", "name"),
        [
            ({"is_software_project": False, "summary": "Just photos."}, "summary"),
            ({"is_software_project": False, "notes": "One note."}, "notes_str"),
            ({"is_software_project": False}, "bare"),
        ],
    )
    def test_empty_review_variants(self, cr: dict[str, object], name: str) -> None:
        assert_golden(
            f"render_review_empty_{name}.md",
            _format_review_as_text({"code_review": cr}),
        )

    def test_typed_notes_with_no_tests_and_no_ci(self) -> None:
        assert_golden(
            "render_review_no_tests.md",
            _format_review_as_text(load_fixture("review_no_tests.json")),
        )

    def test_no_code_review_key_renders_the_skeleton(self) -> None:
        assert_golden("render_review_skeleton.md", _format_review_as_text({}))


class TestVisionRenderer:
    def test_full_vision(self) -> None:
        assert_golden(
            "render_vision_full.md",
            _format_vision_as_text(load_fixture("vision_full.json")),
        )

    def test_vision_as_a_string(self) -> None:
        assert_golden(
            "render_vision_strings.md",
            _format_vision_as_text(load_fixture("vision_string_shapes.json")),
        )

    def test_no_name_and_string_monetization(self) -> None:
        assert_golden(
            "render_vision_no_name.md",
            _format_vision_as_text(load_fixture("vision_no_name.json")),
        )

    def test_review_footer_variant(self) -> None:
        assert_golden(
            "render_vision_review_footer.md",
            _format_vision_as_text(
                load_fixture("vision_full.json"), footer=_VISION_REVIEW_FOOTER
            ),
        )


class TestCatalogRenderer:
    def test_catalog(self) -> None:
        assert_golden(
            "render_catalog.md", _format_catalog_as_text(load_fixture("catalog.json"))
        )

    def test_empty_catalog(self) -> None:
        assert_golden(
            "render_catalog_empty.md",
            _format_catalog_as_text(load_fixture("catalog_empty.json")),
        )

    def test_missing_key_renders_like_empty(self) -> None:
        assert _format_catalog_as_text({}) == _format_catalog_as_text(
            load_fixture("catalog_empty.json")
        )


class TestSpecRenderer:
    def test_full_spec(self) -> None:
        assert_golden(
            "render_spec.md",
            _format_spec_as_text(
                load_fixture("spec_entry.json"), load_fixture("spec_full.json"), 0, 3
            ),
        )

    def test_tier_falls_back_when_no_decision(self) -> None:
        assert_golden(
            "render_spec_tier_fallback.md",
            _format_spec_as_text(
                load_fixture("spec_entry_tier_fallback.json"), {}, 2, 3
            ),
        )
