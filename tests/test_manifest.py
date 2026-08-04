"""Tests for the design manifest module (D-DM)."""

from spec4.agents._manifest import (
    MANIFEST_END,
    MANIFEST_START,
    enrich_manifest,
    extract_manifest,
    validate_manifest,
)

_AI = {
    "ai_features": [
        {
            "name": "policy_qa",
            "scope": "feature",
            "tier": "single_call",
            "linked_vision_features": ["policy_answers"],
            "invocation": {"mode": "sync", "trigger": "user asks"},
        },
        {"name": "vec_store", "scope": "feature", "tier": "infrastructure"},
    ]
}
_VISION = {
    "vision_statement": {
        "target_audiences": [{"name": "HR"}],
        "key_features_mvp": [{"name": "policy_answers"}, {"name": "doc_upload"}],
    }
}


def _wrap(json_body: str) -> str:
    doc = "<!DOCTYPE html><html></html>"
    return f"{MANIFEST_START}\n{json_body}\n{MANIFEST_END}\n{doc}"


class TestExtract:
    def test_extracts_sentinel_json(self) -> None:
        m = extract_manifest(_wrap('{"version": 1, "surfaces": []}'))
        assert m == {"version": 1, "surfaces": []}

    def test_tolerates_json_fence_inside_sentinels(self) -> None:
        m = extract_manifest(_wrap('```json\n{"version": 1}\n```'))
        assert m == {"version": 1}

    def test_missing_sentinels_returns_none(self) -> None:
        assert extract_manifest("<!DOCTYPE html><html></html>") is None

    def test_malformed_json_returns_none(self) -> None:
        assert extract_manifest(_wrap("{not json")) is None


class TestEnrich:
    def test_pins_catalog_facts_via_catalog_surface_link(self) -> None:
        # UI surface renamed by the model; the catalog_surface link ties it back.
        manifest = {
            "surfaces": [
                {
                    "name": "policy_qa_chat",
                    "kind": "ai",
                    "catalog_surface": "policy_qa",
                    "implements_features": ["WRONG"],
                    "invocation": {"mode": "BOGUS"},
                }
            ]
        }
        out = enrich_manifest(manifest, _AI)
        s = out["surfaces"][0]
        assert s["implements_features"] == ["policy_answers"]
        assert s["invocation"] == {"mode": "sync", "trigger": "user asks"}

    def test_unlinked_ai_surface_not_pinned(self) -> None:
        manifest = {
            "surfaces": [
                {"name": "x", "kind": "ai", "implements_features": ["keep"]}
            ]
        }
        out = enrich_manifest(manifest, _AI)
        assert out["surfaces"][0]["implements_features"] == ["keep"]

    def test_leaves_non_ai_surfaces_untouched(self) -> None:
        manifest = {
            "surfaces": [
                {"name": "doc_upload", "kind": "non_ai", "implements_features": ["x"]}
            ]
        }
        out = enrich_manifest(manifest, _AI)
        assert out["surfaces"][0]["implements_features"] == ["x"]


class TestValidate:
    def _base(self) -> dict:
        return {
            "entities": [{"name": "Policy", "fields": ["title"]}],
            "screens": [{"id": "hr", "audience": "HR", "surfaces": []}],
            "surfaces": [
                {
                    "name": "policy_qa_chat",
                    "kind": "ai",
                    "catalog_surface": "policy_qa",
                    "implements_features": ["policy_answers"],
                    "reads": ["Policy"],
                    "writes": [],
                    "depends_on": [],
                },
                {
                    "name": "doc_upload",
                    "kind": "non_ai",
                    "implements_features": ["doc_upload"],
                    "reads": [],
                    "writes": ["Policy"],
                    "depends_on": ["policy_qa_chat"],
                },
            ],
        }

    def test_clean_manifest_has_no_warnings(self) -> None:
        _m, warnings = validate_manifest(self._base(), _AI, _VISION)
        assert warnings == []

    def test_unrealized_catalog_surface_warns(self) -> None:
        m = self._base()
        m["surfaces"] = [s for s in m["surfaces"] if s["name"] != "policy_qa_chat"]
        _m, warnings = validate_manifest(m, _AI, _VISION)
        assert any("policy_qa" in w and "realized by no surface" in w for w in warnings)

    def test_ai_surface_without_link_warns(self) -> None:
        m = self._base()
        del m["surfaces"][0]["catalog_surface"]
        _m, warnings = validate_manifest(m, _AI, _VISION)
        assert any("no catalog_surface link" in w for w in warnings)

    def test_unresolvable_link_warns(self) -> None:
        m = self._base()
        m["surfaces"][0]["catalog_surface"] = "ghost_surface"
        _m, warnings = validate_manifest(m, _AI, _VISION)
        assert any("ghost_surface" in w for w in warnings)

    def test_split_two_ui_surfaces_one_catalog_surface_ok(self) -> None:
        m = self._base()
        m["surfaces"].append(
            {
                "name": "policy_qa_history",
                "kind": "ai",
                "catalog_surface": "policy_qa",
                "implements_features": [],
                "reads": [],
                "writes": [],
                "depends_on": [],
            }
        )
        _m, warnings = validate_manifest(m, _AI, _VISION)
        assert not any("realized by no surface" in w for w in warnings)

    def test_drops_dangling_entity_and_surface_refs(self) -> None:
        m = self._base()
        m["surfaces"][0]["writes"] = ["Ghost"]
        m["surfaces"][0]["depends_on"] = ["nope"]
        out, warnings = validate_manifest(m, _AI, _VISION)
        assert out["surfaces"][0]["writes"] == []
        assert out["surfaces"][0]["depends_on"] == []
        assert len(warnings) >= 2

    def test_unknown_audience_warns(self) -> None:
        m = self._base()
        m["screens"][0]["audience"] = "Martians"
        _m, warnings = validate_manifest(m, _AI, _VISION)
        assert any("Martians" in w for w in warnings)

    def test_infrastructure_surface_not_required(self) -> None:
        _m, warnings = validate_manifest(self._base(), _AI, _VISION)
        assert not any("vec_store" in w for w in warnings)

class TestEnrichIds:
    def test_pins_feature_ids_via_vision_map(self) -> None:
        ai = {
            "ai_features": [
                {
                    "name": "policy_qa",
                    "scope": "feature",
                    "id": "policy_qa",
                    "linked_vision_features": ["Policy_Answers"],
                    "invocation": {"mode": "sync"},
                }
            ]
        }
        vision = {
            "vision_statement": {
                "vision": {
                    "key_features_mvp": [
                        {"name": "Policy_Answers", "id": "policy_answers"}
                    ]
                }
            }
        }
        manifest = {
            "surfaces": [
                {
                    "name": "chat",
                    "kind": "ai",
                    "catalog_surface": "policy_qa",
                    "implements_features": ["ignored"],
                },
                {
                    "name": "upload",
                    "kind": "non_ai",
                    "implements_features": ["Policy_Answers"],
                },
            ]
        }
        out = enrich_manifest(manifest, ai, vision)
        ai_s, non_s = out["surfaces"]
        # AI surface: implements_features pinned to the catalog name, then mapped.
        assert ai_s["implements_features"] == ["Policy_Answers"]
        assert ai_s["implements_feature_ids"] == ["policy_answers"]
        assert ai_s["catalog_surface_id"] == "policy_qa"
        # non-AI surface: name preserved, id join key added.
        assert non_s["implements_features"] == ["Policy_Answers"]
        assert non_s["implements_feature_ids"] == ["policy_answers"]

    def test_slug_fallback_without_vision(self) -> None:
        manifest = {
            "surfaces": [
                {"name": "x", "kind": "non_ai", "implements_features": ["Deck Build"]}
            ]
        }
        out = enrich_manifest(manifest, {"ai_features": []})
        assert out["surfaces"][0]["implements_feature_ids"] == ["deck_build"]

    def test_catalog_surface_id_slug_fallback_when_unresolved(self) -> None:
        manifest = {
            "surfaces": [
                {
                    "name": "x",
                    "kind": "ai",
                    "catalog_surface": "Ghost Surface",
                    "implements_features": [],
                }
            ]
        }
        out = enrich_manifest(manifest, {"ai_features": []})
        assert out["surfaces"][0]["catalog_surface_id"] == "ghost_surface"
        assert out["surfaces"][0]["implements_feature_ids"] == []