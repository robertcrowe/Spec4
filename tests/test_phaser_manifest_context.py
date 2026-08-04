"""Unit tests for ``_manifest_for_phaser`` — the deterministic projection of
Designer's ``manifest.json`` into Phaser's seed (D-PH1d option B).

The projection leads with the stable join surface (ids and dispositions, since
surface names/counts vary across mock regens): per surface, the
``implements_feature_ids`` product join and ``catalog_surface_id`` AI join,
with the three dispositions annotated inline — feature surface, scaffolding
(empty ``implements``), and internal (``screen: null``). ``screen`` may be a
string or a list across draws; both must render.
"""

from __future__ import annotations

from typing import Any

from spec4.agents._utils import _manifest_for_phaser


def _surface(name: str, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": name,
        "kind": "non_ai",
        "screen": "main",
        "implements_feature_ids": ["some_feature"],
    }
    base.update(extra)
    return base


# --- empty / absent --------------------------------------------------------


def test_absent_manifest_or_no_surfaces_returns_empty() -> None:
    assert _manifest_for_phaser(None) == ""
    assert _manifest_for_phaser({}) == ""
    assert _manifest_for_phaser({"surfaces": []}) == ""


# --- screens ---------------------------------------------------------------


def test_screens_render_audience_purpose_and_membership() -> None:
    out = _manifest_for_phaser({
        "screens": [
            {
                "id": "commuter_main",
                "audience": "Daily commuters",
                "purpose": "Primary fare lookup",
                "surfaces": ["fare_lookup_form", "fare_result"],
            }
        ],
        "surfaces": [_surface("fare_lookup_form")],
    })
    assert "- `commuter_main` (Daily commuters): Primary fare lookup" in out
    assert "surfaces: fare_lookup_form, fare_result" in out


# --- surface lines and dispositions ----------------------------------------


def test_feature_surface_line_carries_both_join_keys() -> None:
    out = _manifest_for_phaser({
        "surfaces": [
            _surface(
                "summary_view",
                kind="ai",
                implements_feature_ids=["thread_summarization"],
                catalog_surface_id="thread_summarization",
                reads=["EmailThread"],
                writes=["Summary"],
                depends_on=["input_paste"],
            )
        ]
    })
    line = next(
        text for text in out.splitlines() if text.startswith("- `summary_view`")
    )
    assert "[ai]" in line
    assert "implements: thread_summarization" in line
    assert "catalog: `thread_summarization`" in line
    assert "reads: EmailThread" in line and "writes: Summary" in line
    assert "after: input_paste" in line


def test_screen_list_and_string_both_render() -> None:
    out = _manifest_for_phaser({
        "surfaces": [
            _surface("form", screen=["commuter_main", "visitor_main"]),
            _surface("paste", screen="main_thread_processor"),
        ]
    })
    assert "screens: commuter_main, visitor_main" in out
    assert "screens: main_thread_processor" in out


def test_empty_implements_annotated_as_scaffolding() -> None:
    out = _manifest_for_phaser({
        "surfaces": [_surface("config_panel", implements_feature_ids=[])]
    })
    assert "implements: (none — scaffolding, not a feature surface)" in out


def test_null_screen_annotated_as_internal() -> None:
    out = _manifest_for_phaser({
        "surfaces": [_surface("constraint_validation", screen=None)]
    })
    assert "screens: (none — internal, non-UI work for its feature)" in out


# --- guidance and entities --------------------------------------------------


def test_dedup_and_placement_guidance_stated() -> None:
    out = _manifest_for_phaser({"surfaces": [_surface("s")]})
    assert "Group surfaces by product-feature id" in out
    assert "ONE AI capability" in out
    assert "scaffolding" in out
    assert "advisory" in out


def test_entities_render_with_fields() -> None:
    out = _manifest_for_phaser({
        "surfaces": [_surface("s")],
        "entities": [{"name": "Zone", "fields": ["id", "name"]}],
    })
    assert "Design entities" in out
    assert "- Zone: id, name" in out