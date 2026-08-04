"""Tests for vision grounding — Agentifier consuming Brainstormer feature_specs.

Covers the join (D-AC2 A), the per-node ``vision_grounding`` carry and the
Spec-Drafter prompt injection (D-AC1 B), coordinator union (D-AC3), the slug
unification (D-AC8), the session/disk source resolution, and the Spec Drafter
input plumbing.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from spec4.agentifier.agentifier import (
    _build_ai_features,
    _existing_workflow_for_entry,
    _feature_specs_for_session,
    _linked_features_for_entry,
)
from spec4.agentifier.grounding import (
    build_grounding,
    render_grounding_for_prompt,
    spec_by_id,
)
from spec4.agentifier.spec_drafter import SpecDrafterInput, _build_user_content

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _product_spec(name: str, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": name.lower().replace(" ", "_"),
        "name": name,
        "purpose": f"{name} purpose",
        "invocation": {"trigger": f"user does {name}"},
        "inputs": [
            {"name": "query", "type": "text", "description": "the ask", "required": True}
        ],
        "outputs": {"primary": f"{name} result", "format": "list", "schema_notes": ""},
        "success_criteria": [f"{name} works"],
        "failure_modes": [{"mode": "empty", "likelihood": "low", "mitigation": "retry"}],
        "dependencies": [],
        "entities": ["Item"],
    }
    base.update(kw)
    return base


def _feature_specs(*features: dict[str, Any], nfr_goals: list[str] | None = None) -> dict[str, Any]:
    return {
        "version": 1,
        "features": list(features),
        "nfr_goals": list(nfr_goals or []),
    }


def _entry(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "rough_description": "",
        "scope": "feature",
        "tier_decision": "single_call",
        "tier_recommendation": "",
        "tier_decision_rationale": "",
    }


def _candidate(name: str, linked: list[str], **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": name,
        "linked_vision_features": list(linked),
        "scope": "feature",
        "rough_description": "desc",
        "linked_existing_workflow": "",
        "composed_under": "",
        "requires": [],
        "kind": "feature",
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# spec_by_id
# ---------------------------------------------------------------------------


class TestSpecById:
    def test_indexes_by_id(self) -> None:
        specs = _feature_specs(_product_spec("Smart Search"))
        index = spec_by_id(specs)
        assert "smart_search" in index
        assert index["smart_search"]["name"] == "Smart Search"

    def test_falls_back_to_slug_when_id_missing(self) -> None:
        feat = _product_spec("Smart Search")
        del feat["id"]
        index = spec_by_id(_feature_specs(feat))
        assert "smart_search" in index

    def test_skips_non_dicts_and_none(self) -> None:
        assert spec_by_id(None) == {}
        assert spec_by_id({"features": ["nope", 3, None]}) == {}


# ---------------------------------------------------------------------------
# build_grounding — the join (D-AC2 A)
# ---------------------------------------------------------------------------


class TestBuildGrounding:
    def test_exact_match_single(self) -> None:
        specs = _feature_specs(_product_spec("Smart Search"))
        g = build_grounding(specs, ["Smart Search"])
        assert [f["name"] for f in g["served_features"]] == ["Smart Search"]
        assert "unresolved_links" not in g

    def test_name_slugged_before_join(self) -> None:
        # Linked name differs in case/punctuation but slugs to the same id.
        specs = _feature_specs(_product_spec("Smart Search"))
        g = build_grounding(specs, ["smart search"])
        assert [f["name"] for f in g["served_features"]] == ["Smart Search"]

    def test_many_to_one_union_and_dedup(self) -> None:
        specs = _feature_specs(_product_spec("Alpha"), _product_spec("Beta"))
        # A coordinator's union may repeat a member's feature.
        g = build_grounding(specs, ["Alpha", "Beta", "Alpha"])
        assert [f["name"] for f in g["served_features"]] == ["Alpha", "Beta"]

    def test_empty_links_yield_empty_grounding(self) -> None:
        # Legitimate: a cross-cutting AI feature serves no named product feature.
        assert build_grounding(_feature_specs(_product_spec("Alpha")), []) == {}
        assert build_grounding(_feature_specs(_product_spec("Alpha")), None) == {}

    def test_named_but_unresolved_reported(self) -> None:
        specs = _feature_specs(_product_spec("Alpha"))
        g = build_grounding(specs, ["Ghost Feature"])
        assert "served_features" not in g
        assert g["unresolved_links"] == ["Ghost Feature"]

    def test_mixed_matched_and_unresolved(self) -> None:
        specs = _feature_specs(_product_spec("Alpha"))
        g = build_grounding(specs, ["Alpha", "Ghost"])
        assert [f["name"] for f in g["served_features"]] == ["Alpha"]
        assert g["unresolved_links"] == ["Ghost"]

    def test_served_carries_deps_and_entities_verbatim(self) -> None:
        feat = _product_spec("Alpha", dependencies=["beta"], entities=["User", "Order"])
        g = build_grounding(_feature_specs(feat), ["Alpha"])
        served = g["served_features"][0]
        assert served["dependencies"] == ["beta"]
        assert served["entities"] == ["User", "Order"]

    def test_no_specs_yields_empty(self) -> None:
        assert build_grounding(None, ["Alpha"]) == {"unresolved_links": ["Alpha"]}
        assert build_grounding({}, ["Alpha"]) == {"unresolved_links": ["Alpha"]}


# ---------------------------------------------------------------------------
# render_grounding_for_prompt
# ---------------------------------------------------------------------------


class TestRenderGroundingForPrompt:
    def test_empty_yields_blank(self) -> None:
        assert render_grounding_for_prompt(None) == ""
        assert render_grounding_for_prompt({}) == ""
        assert render_grounding_for_prompt({"unresolved_links": ["x"]}) == ""

    def test_served_renders_key_fields(self) -> None:
        feat = _product_spec("Alpha", entities=["User"], dependencies=["beta"])
        text = render_grounding_for_prompt({"served_features": [feat]})
        assert "**Alpha**" in text
        assert "Alpha purpose" in text
        assert "user does Alpha" in text
        assert "query (text)" in text
        assert "Alpha result" in text
        assert "Alpha works" in text
        assert "User" in text
        assert "beta" in text

    def test_unresolved_not_shown_to_model(self) -> None:
        text = render_grounding_for_prompt(
            {"served_features": [_product_spec("Alpha")], "unresolved_links": ["SECRET"]}
        )
        assert "SECRET" not in text


# ---------------------------------------------------------------------------
# _build_ai_features — per-node carry, slug join, coordinator union (D-AC1/3/8)
# ---------------------------------------------------------------------------


class TestBuildAiFeaturesGrounding:
    def test_node_carries_grounding(self) -> None:
        specs = _feature_specs(_product_spec("Smart Search"))
        entry = _entry("semantic_ranking")
        cand = _candidate("semantic_ranking", ["Smart Search"])
        [feat] = _build_ai_features([entry], [{}], [cand], None, specs)
        assert feat["vision_grounding"]["served_features"][0]["name"] == "Smart Search"

    def test_slug_join_across_name_forms(self) -> None:
        # Brainstormer id is slug("Smart Search"); Scout linked the display name.
        specs = _feature_specs(_product_spec("Smart Search"))
        entry = _entry("ranker")
        cand = _candidate("ranker", ["Smart Search"])
        [feat] = _build_ai_features([entry], [{}], [cand], None, specs)
        assert "vision_grounding" in feat

    def test_coordinator_union_grounds_all_members(self) -> None:
        # A coordinator candidate's linked list is already the union of members.
        specs = _feature_specs(_product_spec("Alpha"), _product_spec("Beta"))
        entry = _entry("coordinator")
        cand = _candidate("coordinator", ["Alpha", "Beta"])
        [feat] = _build_ai_features([entry], [{}], [cand], None, specs)
        names = [f["name"] for f in feat["vision_grounding"]["served_features"]]
        assert names == ["Alpha", "Beta"]

    def test_no_grounding_key_when_feature_specs_absent(self) -> None:
        entry = _entry("ranker")
        cand = _candidate("ranker", ["Smart Search"])
        [feat] = _build_ai_features([entry], [{}], [cand], None, None)
        assert "vision_grounding" not in feat

    def test_no_grounding_key_when_no_links(self) -> None:
        specs = _feature_specs(_product_spec("Smart Search"))
        entry = _entry("cross_cutting_thing")
        cand = _candidate("cross_cutting_thing", [])
        [feat] = _build_ai_features([entry], [{}], [cand], None, specs)
        assert "vision_grounding" not in feat

    def test_id_uses_shared_slug(self) -> None:
        # D-AC8: node id routes through slug(); empty name keeps positional id.
        specs = _feature_specs()
        [feat] = _build_ai_features([_entry("Ticket Routing")], [{}], [], None, specs)
        assert feat["id"] == "ticket_routing"

    def test_grounding_survives_spec_echo(self) -> None:
        # A Spec Drafter that echoes the key cannot clobber the joined grounding.
        specs = _feature_specs(_product_spec("Alpha"))
        entry = _entry("ranker")
        cand = _candidate("ranker", ["Alpha"])
        spec = [{"vision_grounding": {"served_features": [{"name": "WRONG"}]}}]
        [feat] = _build_ai_features([entry], spec, [cand], None, specs)
        assert feat["vision_grounding"]["served_features"][0]["name"] == "Alpha"


# ---------------------------------------------------------------------------
# _feature_specs_for_session / _linked_features_for_entry
# ---------------------------------------------------------------------------


class TestFeatureSpecsForSession:
    def test_prefers_session_copy(self) -> None:
        specs = _feature_specs(_product_spec("Alpha"))
        session = {"feature_specs": specs, "working_dir": "/nope"}
        assert _feature_specs_for_session(session) is specs

    def test_falls_back_to_disk(self) -> None:
        specs = _feature_specs(_product_spec("Alpha"))
        session = {"feature_specs": None, "working_dir": "/wd"}
        with patch(
            "spec4.project_manager.load_feature_specs", return_value=specs
        ) as m:
            got = _feature_specs_for_session(session)
        m.assert_called_once_with("/wd")
        assert got is specs

    def test_empty_when_neither(self) -> None:
        assert _feature_specs_for_session({}) == {}

    def test_linked_features_from_candidate(self) -> None:
        cands = [_candidate("ranker", ["Alpha", "Beta"])]
        assert _linked_features_for_entry(_entry("ranker"), cands) == ["Alpha", "Beta"]

    def test_linked_features_missing_candidate(self) -> None:
        assert _linked_features_for_entry(_entry("orphan"), []) == []

    def test_existing_workflow_for_entry_found(self) -> None:
        cands = [
            _candidate("ranker", [], linked_existing_workflow="regex ranking in views.py")
        ]
        assert (
            _existing_workflow_for_entry(_entry("ranker"), cands)
            == "regex ranking in views.py"
        )

    def test_existing_workflow_for_entry_missing_returns_empty(self) -> None:
        assert _existing_workflow_for_entry(_entry("orphan"), []) == ""
        # A candidate without the key (or with None) degrades to "".
        assert _existing_workflow_for_entry(_entry("ranker"), [{"name": "ranker"}]) == ""


# ---------------------------------------------------------------------------
# Spec Drafter input plumbing (D-AC1 B / D-AC4 A)
# ---------------------------------------------------------------------------


class TestSpecDrafterGrounding:
    def _input(self, grounding: dict[str, Any] | None) -> SpecDrafterInput:
        return SpecDrafterInput(
            catalog_entry=_entry("ranker"),
            llm_config={"model": "m", "api_key": "k"},
            tier_patterns=[],
            mechanism_patterns=[],
            vision_grounding=grounding,
        )

    def test_user_content_includes_grounding(self) -> None:
        g = build_grounding(_feature_specs(_product_spec("Alpha")), ["Alpha"])
        content = _build_user_content(self._input(g), "single_call")
        assert "Product features this AI feature serves" in content
        assert "Alpha purpose" in content

    def test_user_content_omits_when_absent(self) -> None:
        content = _build_user_content(self._input(None), "single_call")
        assert "Product features this AI feature serves" not in content

    def test_user_content_omits_when_only_unresolved(self) -> None:
        content = _build_user_content(
            self._input({"unresolved_links": ["Ghost"]}), "single_call"
        )
        assert "Product features this AI feature serves" not in content
        assert "Ghost" not in content


class TestSpecDrafterBrownfieldInputs:
    def _input(self, **kw: Any) -> SpecDrafterInput:
        return SpecDrafterInput(
            catalog_entry=_entry("ranker"),
            llm_config={"model": "m", "api_key": "k"},
            tier_patterns=[],
            mechanism_patterns=[],
            **kw,
        )

    def test_user_content_includes_existing_workflow(self) -> None:
        content = _build_user_content(
            self._input(linked_existing_workflow="regex ranking in views.py"),
            "single_call",
        )
        assert "Existing implementation this replaces:" in content
        assert "regex ranking in views.py" in content

    def test_user_content_includes_existing_ai_context(self) -> None:
        content = _build_user_content(
            self._input(
                existing_ai_context="AI/LLM dependencies already in place: chromadb"
            ),
            "single_call",
        )
        assert "Existing AI infrastructure (bias toward reuse):" in content
        assert "chromadb" in content

    def test_user_content_clean_when_brownfield_fields_empty(self) -> None:
        # Defaults ("") must leave the greenfield prompt byte-identical.
        content = _build_user_content(self._input(), "single_call")
        assert "Existing implementation this replaces" not in content
        assert "Existing AI infrastructure" not in content
