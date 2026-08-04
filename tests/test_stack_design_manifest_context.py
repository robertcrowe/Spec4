"""Unit tests for ``_design_manifest_for_stack`` — Designer's manifest as
StackAdvisor input (D-SC5c).

StackAdvisor consumes the manifest's *shape* signal: entities with their fields
(the spine carries only bare names), which entities the UI writes versus only
reads, and the screen structure. It deliberately does **not** consume the
surface→feature join fields — StackAdvisor already has a sound feature join via
the Brainstormer spine and the AI catalog's serves relation, and the manifest's
join is known to over-attribute, so importing it would corrupt the attribution
this round exists to produce. It also never reads the visual mock: that is the
coding agent's reference, handed downstream by path.

Pure rendering assertions; whether the live model then picks a better store or
router is an in-app behavioural draw, not asserted here.
"""

from __future__ import annotations

from typing import Any

from spec4.agents._utils import _design_manifest_for_stack


def _manifest(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "FareBox",
        "entities": [
            {"name": "Zone", "fields": ["id", "name"]},
            {"name": "SavedTrip", "fields": ["originZone", "label"]},
        ],
        "screens": [
            {"id": "commuter_main", "audience": "Commuters"},
            {"id": "history_detail", "audience": "Commuters"},
        ],
        "surfaces": [
            {
                "name": "fare_lookup_form",
                "reads": ["Zone"],
                "writes": ["SavedTrip"],
                "implements_feature_ids": ["fare_lookup"],
                "catalog_surface_id": "some_capability",
            }
        ],
        "shared_layout": {"nav": {"type": "tab_bar", "items": []}},
    }
    base.update(over)
    return base


# --- empty / absent --------------------------------------------------------


def test_no_manifest_returns_empty() -> None:
    assert _design_manifest_for_stack(None) == ""
    assert _design_manifest_for_stack({}) == ""
    assert _design_manifest_for_stack({"name": "X"}) == ""


# --- data model: entities WITH fields (the spine has only names) ------------


def test_entities_rendered_with_fields() -> None:
    out = _design_manifest_for_stack(_manifest())
    assert "Data model" in out
    assert "`Zone`: id, name" in out
    assert "`SavedTrip`: originZone, label" in out


def test_entity_without_fields_still_named() -> None:
    out = _design_manifest_for_stack(
        _manifest(entities=[{"name": "Bare"}], surfaces=[], screens=[])
    )
    assert "`Bare`" in out


def test_data_model_framed_as_advisory_not_a_schema() -> None:
    out = _design_manifest_for_stack(_manifest())
    assert "not as a schema to adopt verbatim" in out


# --- entity access: the persistence signal ---------------------------------


def test_written_vs_read_only_split() -> None:
    out = _design_manifest_for_stack(_manifest())
    assert "- written: SavedTrip" in out
    assert "- read-only: Zone" in out


def test_entity_written_anywhere_is_not_read_only() -> None:
    man = _manifest(
        surfaces=[
            {"name": "a", "reads": ["Trip"], "writes": []},
            {"name": "b", "reads": [], "writes": ["Trip"]},
        ]
    )
    out = _design_manifest_for_stack(man)
    assert "- written: Trip" in out
    assert "read-only: Trip" not in out


# --- screens / navigation --------------------------------------------------


def test_screens_and_nav_rendered() -> None:
    out = _design_manifest_for_stack(_manifest())
    assert "2 screen(s)" in out
    assert "`tab_bar` navigation" in out
    assert "`commuter_main`" in out


def test_nav_may_be_a_bare_string() -> None:
    # Designer emits nav as a dict on some draws and a plain string on others
    out = _design_manifest_for_stack(
        _manifest(shared_layout={"nav": "top_tabs", "shell": []})
    )
    assert "`top_tabs` navigation" in out


def test_routing_left_to_stack_advisor() -> None:
    out = _design_manifest_for_stack(_manifest())
    assert "your call" in out


# --- the joins are deliberately NOT imported (D-SC5c) ----------------------


def test_surface_feature_joins_are_not_projected() -> None:
    out = _design_manifest_for_stack(_manifest())
    assert "implements_feature_ids" not in out
    assert "fare_lookup" not in out
    assert "catalog_surface_id" not in out
    assert "some_capability" not in out