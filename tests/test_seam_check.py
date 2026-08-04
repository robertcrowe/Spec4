"""Tests for the advisory cross-phase seam check (Phase-0).

Pure-function tests — no live LLM. The extraction call is patched out; the
deterministic checks and the never-raise guarantee are exercised directly.
"""

from __future__ import annotations

from unittest.mock import patch

from spec4.agents import _seam_check
from spec4.agents._seam_check import (
    SeamFinding,
    _check_declaration_alignment,
    _check_endpoint_provenance,
    _check_feature_coverage,
    _check_table_provenance,
    _format_advisory,
    _parse_graph,
    run_seam_check,
)


def _phase(num, **kw):
    base = {
        "phase_number": num,
        "creates_tables": [],
        "reads_tables": [],
        "creates_endpoints": [],
        "consumes_endpoints": [],
        "covers_features": [],
    }
    base.update(kw)
    return base


def _g(phases):
    return {"phases": phases}


class TestParseGraph:
    def test_parses_clean_object(self):
        raw = '{"phases":[{"phase_number":1,"creates_tables":["users"]}]}'
        g = _parse_graph(raw)
        assert g is not None
        assert g["phases"][0]["creates_tables"] == ["users"]
        assert g["phases"][0]["reads_tables"] == []  # missing keys default empty

    def test_parses_object_wrapped_in_prose(self):
        raw = 'Sure, here:\n```json\n{"phases": []}\n```\n'
        assert _parse_graph(raw) == {"phases": []}

    def test_returns_none_on_garbage(self):
        assert _parse_graph("not json at all") is None

    def test_returns_none_when_phases_key_missing(self):
        assert _parse_graph('{"foo": 1}') is None


class TestTableProvenance:
    def test_read_without_writer_is_high(self):
        g = _g([_phase(3, reads_tables=["purchase_history"])])
        highs = [f for f in _check_table_provenance(g) if f.severity == "high"]
        assert any("purchase_history" in f.message for f in highs)

    def test_created_earlier_then_read_is_clean(self):
        g = _g([
            _phase(1, creates_tables=["inventory_item"]),
            _phase(2, reads_tables=["inventory_item"]),
        ])
        flagged = [
            f for f in _check_table_provenance(g) if f.severity in ("high", "medium")
        ]
        assert flagged == []

    def test_created_after_read_is_medium(self):
        g = _g([
            _phase(2, reads_tables=["orders"]),
            _phase(5, creates_tables=["orders"]),
        ])
        meds = [f for f in _check_table_provenance(g) if f.severity == "medium"]
        assert any("orders" in f.message for f in meds)

    def test_created_never_read_is_info_only(self):
        g = _g([_phase(1, creates_tables=["audit_log"])])
        findings = _check_table_provenance(g)
        assert all(f.severity == "info" for f in findings)
        assert any("audit_log" in f.message for f in findings)


class TestEndpointProvenance:
    def test_consumed_without_producer_is_medium(self):
        g = _g([_phase(1, consumes_endpoints=["POST /inventory/add"])])
        findings = _check_endpoint_provenance(g)
        assert any(f.severity == "medium" for f in findings)

    def test_consumed_with_producer_is_clean(self):
        g = _g([
            _phase(1, creates_endpoints=["POST /inventory/add"]),
            _phase(2, consumes_endpoints=["post /inventory/add"]),  # case-insensitive
        ])
        assert _check_endpoint_provenance(g) == []


class TestFeatureCoverage:
    _AF = {
        "ai_features": [
            {"id": "barcode_scan", "name": "Barcode scan", "phase_priority": "mvp"},
            {"id": "waste_impact", "name": "Waste impact", "phase_priority": "mvp"},
            {"id": "fancy_thing", "name": "Fancy", "phase_priority": "v2"},
        ]
    }

    def test_uncovered_mvp_feature_is_high(self):
        g = _g([_phase(1, covers_features=["barcode_scan"])])
        findings = _check_feature_coverage(g, self._AF)
        assert any(
            f.severity == "high" and "Waste impact" in f.message for f in findings
        )
        assert not any("Barcode scan" in f.message for f in findings)  # covered
        assert not any("Fancy" in f.message for f in findings)  # v2 never flagged

    def test_no_features_no_findings(self):
        assert _check_feature_coverage(_g([]), None) == []


class TestFormatAndEntry:
    def test_format_empty_when_only_info(self):
        assert _format_advisory([SeamFinding("table", "info", "x")]) == ""

    def test_format_orders_high_before_medium(self):
        findings = [
            SeamFinding("endpoint", "medium", "ep_msg"),
            SeamFinding("table", "high", "tbl_msg"),
        ]
        out = _format_advisory(findings)
        assert out.index("tbl_msg") < out.index("ep_msg")

    def test_run_seam_check_degrades_to_empty_on_extraction_failure(self):
        with patch.object(_seam_check, "_extract_graph", return_value=None):
            assert run_seam_check([_phase(1)], None, {"model": "x"}) == ""

    def test_run_seam_check_never_raises(self):
        with patch.object(
            _seam_check, "_extract_graph", side_effect=RuntimeError("boom")
        ):
            assert run_seam_check([_phase(1)], None, {"model": "x"}) == ""

    def test_run_seam_check_empty_phases(self):
        assert run_seam_check([], None, {"model": "x"}) == ""

    def test_run_seam_check_surfaces_findings(self):
        graph = _g([_phase(2, reads_tables=["purchase_history"])])
        with patch.object(_seam_check, "_extract_graph", return_value=graph):
            out = run_seam_check([_phase(2)], None, {"model": "x"})
        assert "purchase_history" in out


class TestDeclarationAlignment:
    """D-PS15: what a phase declares vs what its prose implements.

    Under-declaration is the interesting direction: the spec attaches only to
    declared phases, so a phase that builds a feature without declaring it gets
    no spec for it. The deterministic presence check cannot see this.
    """

    _AF = {
        "ai_features": [
            {"id": "meaning_search", "name": "Meaning search", "phase_priority": "mvp"},
            {"id": "related_items", "name": "Related items", "phase_priority": "mvp"},
            {
                "id": "vector_index",
                "name": "vector_index",
                "phase_priority": "steel_thread",
            },
        ]
    }

    @staticmethod
    def _decl(num, *ids, features=()):
        """A phase declaring AI ids in `capabilities[]` (two-array schema).

        `features` optionally carries product-feature declarations, which the
        alignment check must ignore entirely (D-PH2k).
        """
        return {
            "phase_number": num,
            "capabilities": [
                {"id": i, "role": "introduced", "scope_note": ""} for i in ids
            ],
            "features": [
                {"id": i, "role": "introduced", "scope_note": ""}
                for i in features
            ],
        }

    def test_aligned_declaration_is_silent(self):
        g = _g([_phase(1, covers_features=["meaning_search"])])
        phases = [self._decl(1, "meaning_search")]
        assert _check_declaration_alignment(g, phases, self._AF) == []

    def test_under_declaration_is_high(self):
        # Phase 2 builds the search frontend but declares only its sibling.
        g = _g([
            _phase(1, covers_features=["meaning_search"]),
            _phase(2, covers_features=["related_items", "meaning_search"]),
        ])
        phases = [self._decl(1, "meaning_search"), self._decl(2, "related_items")]
        findings = _check_declaration_alignment(g, phases, self._AF)
        assert len(findings) == 1
        f = findings[0]
        assert f.severity == "high" and f.check == "declaration"
        assert "Phase 2 implements `Meaning search`" in f.message
        assert "not attached to phase 2" in f.message

    def test_over_declaration_is_medium(self):
        g = _g([
            _phase(1, covers_features=["meaning_search"]),
            _phase(2, covers_features=["related_items"]),
        ])
        # Phase 2 also declares meaning_search, but does not implement it there.
        phases = [
            self._decl(1, "meaning_search"),
            self._decl(2, "related_items", "meaning_search"),
        ]
        findings = _check_declaration_alignment(g, phases, self._AF)
        assert len(findings) == 1
        assert findings[0].severity == "medium"
        assert "may be spurious" in findings[0].message

    def test_unimplemented_feature_is_not_also_over_declared(self):
        # `related_items` is implemented nowhere: _check_feature_coverage owns
        # that finding; we must not also accuse phase 1 of over-declaring it.
        g = _g([_phase(1, covers_features=["meaning_search"])])
        phases = [self._decl(1, "meaning_search", "related_items")]
        assert _check_declaration_alignment(g, phases, self._AF) == []
        assert any(
            "Related items" in f.message
            for f in _check_feature_coverage(g, self._AF)
        )

    def test_extracted_ids_outside_the_catalog_are_ignored(self):
        g = _g([_phase(1, covers_features=["meaning_search", "hallucinated_id"])])
        phases = [self._decl(1, "meaning_search")]
        assert _check_declaration_alignment(g, phases, self._AF) == []

    def test_infrastructure_under_declaration_is_flagged(self):
        g = _g([_phase(1, covers_features=["vector_index", "meaning_search"])])
        phases = [self._decl(1, "meaning_search")]
        findings = _check_declaration_alignment(g, phases, self._AF)
        assert any("vector_index" in f.message for f in findings)

    def test_no_features_no_findings(self):
        assert _check_declaration_alignment(_g([]), [], None) == []
        assert _check_declaration_alignment(_g([]), [], {"ai_features": []}) == []

    def test_phase_without_declarations_still_compared(self):
        # A phase that declares nothing but implements something is the exact
        # bug this check exists for.
        g = _g([_phase(1, covers_features=["meaning_search"])])
        phases = [{"phase_number": 1}]
        findings = _check_declaration_alignment(g, phases, self._AF)
        assert len(findings) == 1 and findings[0].severity == "high"

    def test_declaration_findings_reach_the_advisory(self):
        findings = [SeamFinding("declaration", "high", "Phase 2 implements `X`.")]
        out = _format_advisory(findings)
        assert "[declaration]" in out and "Phase 2 implements `X`." in out


class TestDeclarationAlignmentTwoArraySchema:
    """D-PH2k: alignment reads `capabilities[]`; product declarations are
    invisible to it, even under the observed id collision."""

    _AF = {
        "ai_features": [
            {
                "id": "thread_summarization",
                "name": "thread_summarization",
                "phase_priority": "mvp",
            },
        ]
    }

    def test_product_declaration_never_read_against_catalog(self):
        # Phase 7 declares the PRODUCT feature `thread_summarization` (the
        # collision id) in features[] and no capability at all. The alignment
        # check must not read that as a spurious capability claim (the
        # pre-D-PH2k phase-7 MEDIUM), nor as an aligned declaration.
        g = _g([_phase(7, covers_features=[])])
        phases = [
            {
                "phase_number": 7,
                "capabilities": [],
                "features": [
                    {
                        "id": "thread_summarization",
                        "role": "extended",
                        "scope_note": "",
                    }
                ],
            }
        ]
        findings = _check_declaration_alignment(g, phases, self._AF)
        assert findings == []

    def test_capability_in_capabilities_array_is_aligned(self):
        g = _g([_phase(1, covers_features=["thread_summarization"])])
        phases = [
            {
                "phase_number": 1,
                "capabilities": [
                    {
                        "id": "thread_summarization",
                        "role": "introduced",
                        "scope_note": "",
                    }
                ],
                "features": [
                    {
                        "id": "thread_summarization",
                        "role": "introduced",
                        "scope_note": "",
                    }
                ],
            }
        ]
        assert _check_declaration_alignment(g, phases, self._AF) == []

    def test_under_declaration_message_names_capabilities(self):
        g = _g([_phase(1, covers_features=["thread_summarization"])])
        phases = [{"phase_number": 1, "capabilities": [], "features": []}]
        findings = _check_declaration_alignment(g, phases, self._AF)
        assert len(findings) == 1
        assert "`capabilities`" in findings[0].message

    def test_legacy_single_array_phase_set_still_read(self):
        # Pre-D-PH2 sets carry AI ids in features[] with no capabilities key.
        g = _g([_phase(1, covers_features=["thread_summarization"])])
        phases = [
            {
                "phase_number": 1,
                "features": [
                    {
                        "id": "thread_summarization",
                        "role": "introduced",
                        "scope_note": "",
                    }
                ],
            }
        ]
        assert _check_declaration_alignment(g, phases, self._AF) == []

    def test_present_empty_capabilities_never_falls_back_to_features(self):
        # New-schema phase: capabilities=[] with a product declaration of the
        # collision id. Era detection is key presence — no fallback, no
        # spurious capability claim.
        g = _g([_phase(7, covers_features=[])])
        phases = [
            {
                "phase_number": 7,
                "capabilities": [],
                "features": [
                    {
                        "id": "thread_summarization",
                        "role": "extended",
                        "scope_note": "",
                    }
                ],
            }
        ]
        assert _check_declaration_alignment(g, phases, self._AF) == []
