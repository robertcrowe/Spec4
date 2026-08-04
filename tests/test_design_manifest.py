"""Tests for ``spec4.design_manifest`` — the shared manifest helpers.

Shape tolerance (``screen`` string/list/null, ``inputs`` strings/objects), the
attach join (implements ∩ declared features OR catalog id ∈ declared
capabilities, each key against its own array), and the disposition rules:
scaffolding surfaces can never attach; internal surfaces annotate rather than
disappear; excluded-feature surfaces attach nowhere because their feature is
never declared.
"""

from __future__ import annotations

from typing import Any

from spec4.design_manifest import (
    input_names,
    screens_of,
    surface_detail_lines,
    surface_summary_line,
    surfaces_for_declarations,
)


def _surface(name: str = "s", **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"name": name, "kind": "non_ai"}
    base.update(extra)
    return base


class TestShapeTolerance:
    def test_screen_string_list_and_null(self) -> None:
        assert screens_of(_surface(screen="main")) == ["main"]
        assert screens_of(_surface(screen=["a", "b"])) == ["a", "b"]
        assert screens_of(_surface(screen=None)) == []

    def test_inputs_strings_and_objects(self) -> None:
        surface = _surface(
            inputs=["raw_text", {"name": "submit", "type": "button"}, {"x": 1}]
        )
        assert input_names(surface) == ["raw_text", "submit"]


class TestAttachJoin:
    _MANIFEST = {
        "surfaces": [
            _surface(
                "fare_form",
                implements_feature_ids=["fare_lookup"],
                screen="main",
            ),
            _surface(
                "summary_view",
                kind="ai",
                implements_feature_ids=["thread_summarization"],
                catalog_surface_id="thread_summarization",
                screen="main",
            ),
            _surface("config_panel", implements_feature_ids=[]),  # scaffolding
            _surface(
                "replies_view",
                implements_feature_ids=["suggested_replies"],  # excluded
                screen="main",
            ),
        ]
    }

    def test_implements_joins_declared_features(self) -> None:
        recs = surfaces_for_declarations(self._MANIFEST, {"fare_lookup"}, set())
        assert [r["surface"]["name"] for r in recs] == ["fare_form"]
        assert recs[0]["via_features"] == ["fare_lookup"]
        assert recs[0]["via_capability"] is False

    def test_catalog_id_joins_declared_capabilities(self) -> None:
        recs = surfaces_for_declarations(
            self._MANIFEST, set(), {"thread_summarization"}
        )
        assert [r["surface"]["name"] for r in recs] == ["summary_view"]
        assert recs[0]["via_capability"] is True

    def test_each_key_matches_its_own_array_only(self) -> None:
        # the catalog id in the FEATURE set must not match catalog_surface_id
        recs = surfaces_for_declarations(
            self._MANIFEST, {"thread_summarization"}, set()
        )
        # summary_view still attaches — via implements (product id), which is
        # the correct axis for the feature set; via_capability stays False.
        assert recs[0]["via_capability"] is False
        assert recs[0]["via_features"] == ["thread_summarization"]

    def test_scaffolding_never_attaches(self) -> None:
        recs = surfaces_for_declarations(
            self._MANIFEST, {"fare_lookup", "anything"}, {"anything"}
        )
        assert all(r["surface"]["name"] != "config_panel" for r in recs)

    def test_excluded_feature_surface_attaches_nowhere(self) -> None:
        # suggested_replies is excluded -> never declared -> never in the set.
        recs = surfaces_for_declarations(
            self._MANIFEST, {"fare_lookup", "thread_summarization"}, set()
        )
        assert all(r["surface"]["name"] != "replies_view" for r in recs)


class TestRendering:
    def test_summary_line_annotates_dispositions(self) -> None:
        internal = surface_summary_line(
            _surface("validator", implements_feature_ids=["f"], screen=None)
        )
        assert "internal, non-UI" in internal
        scaffolding = surface_summary_line(_surface("cfg"))
        assert "scaffolding" in scaffolding

    def test_detail_lines_carry_build_facing_fields(self) -> None:
        lines = surface_detail_lines(
            _surface(
                "fare_form",
                screen="main",
                inputs=[{"name": "origin_zone"}, "submit"],
                output="fare_result_display",
                states=["idle", "loading"],
                reads=["Zone"],
                writes=["Fare"],
                depends_on=["shell"],
            )
        )
        text = "\n".join(lines)
        assert "**`fare_form`**" in text
        assert "inputs: origin_zone, submit" in text
        assert "output: fare_result_display" in text
        assert "states: idle, loading" in text
        assert "reads: Zone" in text and "writes: Fare" in text
        assert "after (advisory UI ordering): shell" in text

    def test_dict_output_renders_key_names(self) -> None:
        lines = surface_detail_lines(
            _surface("result", output={"fareAmount": "currency", "save": "action"})
        )
        assert any("output: fareAmount, save" in line for line in lines)