"""Tests for ``spec4.agents._phase_coverage`` (two-array contract, D-PH2).

Capability side (``capabilities[]`` over the AI catalog): every
``steel_thread``/``mvp`` node is built by some phase; infrastructure is stood
up no later than its first consumer; ``v2``/``future`` nodes are deferrable
and only ever produce advisories.

Product side (``features[]`` over the Brainstormer spine): every spine feature
is built by some phase — hard failure — except features excluded by the
developer's Agentifier selection, which pass undeclared with an advisory;
declaring an excluded feature is itself a failure. Product ``dependencies``
ordering is advisory (D-PH2f). The array determines the id space, so an id
valid in both spaces is read unambiguously.
"""

from __future__ import annotations

from typing import Any

from spec4.agents._phase_coverage import check_phase_coverage


def _catalog(**overrides: Any) -> dict[str, Any]:
    """A catalog with infra, a cross_feature mvp consumer, and a v2 deferral.

    Note ``requires`` holds feature *names*, while declarations key on ``id``.
    ``RAG Answerer`` deliberately has ``id != name`` so the name→id join is
    exercised rather than assumed.
    """
    catalog: dict[str, Any] = {
        "ai_features": [
            {
                "id": "vector_index",
                "name": "vector_index",
                "kind": "infrastructure",
                "tier": "infrastructure",
                "phase_priority": "steel_thread",
                "requires": [],
            },
            {
                "id": "rag_answerer",
                "name": "RAG Answerer",
                "kind": "feature",
                "tier": "rag",
                "scope": "cross_feature",
                "phase_priority": "mvp",
                "requires": ["vector_index"],
            },
            {
                "id": "summarizer",
                "name": "Summarizer",
                "kind": "feature",
                "tier": "single_call",
                "phase_priority": "v2",
                "requires": [],
            },
        ]
    }
    catalog.update(overrides)
    return catalog


def _specs(*features: dict[str, Any]) -> dict[str, Any]:
    return {"features": list(features)}


def _feature(fid: str, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"id": fid, "name": fid}
    base.update(extra)
    return base


def _phase(
    number: int,
    *capabilities: dict[str, Any],
    features: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "phase_number": number,
        "features": features or [],
        "capabilities": list(capabilities),
    }


def _decl(fid: str, role: str = "introduced", note: str = "") -> dict[str, Any]:
    return {"id": fid, "role": role, "scope_note": note}


def _messages(failures: list[tuple[int | None, list[str]]]) -> str:
    return " ".join(msg for _, errors in failures for msg in errors)


# =========================== capability side ================================


class TestCapabilityPresence:
    def test_full_coverage_passes(self) -> None:
        phases = [
            _phase(1, _decl("vector_index")),
            _phase(2, _decl("rag_answerer")),
        ]
        failures, advisories = check_phase_coverage(phases, _catalog())
        assert failures == []
        assert any("Summarizer" in a for a in advisories)  # v2 deferral

    def test_missing_mvp_capability_fails(self) -> None:
        phases = [_phase(1, _decl("vector_index"))]
        failures, _ = check_phase_coverage(phases, _catalog())
        assert "RAG Answerer" in _messages(failures)
        assert "capabilities" in _messages(failures)

    def test_missing_infrastructure_fails(self) -> None:
        phases = [_phase(1, _decl("rag_answerer"))]
        failures, _ = check_phase_coverage(phases, _catalog())
        assert "vector_index" in _messages(failures)

    def test_deferred_capability_is_advisory_not_failure(self) -> None:
        phases = [
            _phase(1, _decl("vector_index")),
            _phase(2, _decl("rag_answerer")),
        ]
        failures, advisories = check_phase_coverage(phases, _catalog())
        assert failures == []
        assert any("deferred" in a for a in advisories)

    def test_no_catalog_and_no_spine_is_a_no_op(self) -> None:
        assert check_phase_coverage([_phase(1)], None) == ([], [])
        assert check_phase_coverage([_phase(1)], {"ai_features": []}) == ([], [])

    def test_no_phases_is_a_no_op(self) -> None:
        assert check_phase_coverage([], _catalog()) == ([], [])

    def test_unknown_id_fails_and_is_attributed(self) -> None:
        phases = [
            _phase(1, _decl("vector_index"), _decl("rag_answerer")),
            _phase(2, _decl("mystery_feature")),
        ]
        failures, _ = check_phase_coverage(phases, _catalog())
        assert any(
            number == 2 and "mystery_feature" in " ".join(errors)
            for number, errors in failures
        )

    def test_duplicate_id_in_one_phase_fails(self) -> None:
        phases = [
            _phase(1, _decl("vector_index"), _decl("vector_index")),
            _phase(2, _decl("rag_answerer")),
        ]
        failures, _ = check_phase_coverage(phases, _catalog())
        assert "more than once" in _messages(failures)

    def test_same_id_across_phases_is_allowed(self) -> None:
        phases = [
            _phase(1, _decl("vector_index")),
            _phase(2, _decl("rag_answerer")),
            _phase(3, _decl("rag_answerer", role="extended")),
        ]
        failures, _ = check_phase_coverage(phases, _catalog())
        assert failures == []


class TestCapabilityRoles:
    def test_extended_without_introduced_fails(self) -> None:
        phases = [
            _phase(1, _decl("vector_index")),
            _phase(2, _decl("rag_answerer", role="extended")),
        ]
        failures, _ = check_phase_coverage(phases, _catalog())
        assert "never 'introduced'" in _messages(failures)

    def test_two_introductions_fail(self) -> None:
        phases = [
            _phase(1, _decl("vector_index")),
            _phase(2, _decl("rag_answerer")),
            _phase(3, _decl("rag_answerer")),
        ]
        failures, _ = check_phase_coverage(phases, _catalog())
        assert "more than one" in _messages(failures)

    def test_introduced_after_extended_fails(self) -> None:
        phases = [
            _phase(1, _decl("vector_index")),
            _phase(2, _decl("rag_answerer", role="extended")),
            _phase(3, _decl("rag_answerer")),
        ]
        failures, _ = check_phase_coverage(phases, _catalog())
        assert "earliest" in _messages(failures)


class TestInfrastructureOrdering:
    def test_infra_before_consumer_passes(self) -> None:
        phases = [
            _phase(1, _decl("vector_index")),
            _phase(2, _decl("rag_answerer")),
        ]
        failures, _ = check_phase_coverage(phases, _catalog())
        assert failures == []

    def test_infra_in_same_phase_as_consumer_passes(self) -> None:
        phases = [_phase(1, _decl("vector_index"), _decl("rag_answerer"))]
        failures, _ = check_phase_coverage(phases, _catalog())
        assert failures == []

    def test_infra_after_consumer_fails(self) -> None:
        phases = [
            _phase(1, _decl("rag_answerer")),
            _phase(2, _decl("vector_index")),
        ]
        failures, _ = check_phase_coverage(phases, _catalog())
        assert "not stood up until phase 2" in _messages(failures)

    def test_ordering_uses_earliest_declaring_phase(self) -> None:
        phases = [
            _phase(1, _decl("vector_index")),
            _phase(2, _decl("rag_answerer")),
            _phase(3, _decl("vector_index", role="extended")),
        ]
        failures, _ = check_phase_coverage(phases, _catalog())
        assert failures == []

    def test_feature_to_feature_edges_are_not_order_checked(self) -> None:
        catalog = _catalog()
        catalog["ai_features"].append({
            "id": "reranker",
            "name": "Reranker",
            "kind": "feature",
            "tier": "single_call",
            "phase_priority": "mvp",
            "requires": ["RAG Answerer"],
        })
        phases = [
            _phase(1, _decl("vector_index"), _decl("reranker")),
            _phase(2, _decl("rag_answerer")),
        ]
        failures, _ = check_phase_coverage(phases, catalog)
        assert failures == []

    def test_undeclared_infra_is_left_to_the_presence_check(self) -> None:
        phases = [_phase(1, _decl("rag_answerer"))]
        failures, _ = check_phase_coverage(phases, _catalog())
        messages = _messages(failures)
        assert "vector_index" in messages
        assert "not stood up" not in messages


class TestRevisionPartition:
    @staticmethod
    def _revision_catalog() -> dict[str, Any]:
        catalog = _catalog()
        for node in catalog["ai_features"]:
            node["introduced_in_version"] = 0
        catalog["ai_features"].append({
            "id": "new_feature",
            "name": "New Feature",
            "kind": "feature",
            "tier": "single_call",
            "phase_priority": "mvp",
            "requires": [],
            "introduced_in_version": 1,
        })
        return catalog

    def test_established_capabilities_are_not_required(self) -> None:
        phases = [_phase(1, _decl("new_feature"))]
        failures, _ = check_phase_coverage(
            phases, self._revision_catalog(), revision_version=1
        )
        assert failures == []

    def test_new_capability_still_required(self) -> None:
        failures, _ = check_phase_coverage(
            [_phase(1)], self._revision_catalog(), revision_version=1
        )
        assert "New Feature" in _messages(failures)

    def test_established_infra_is_not_order_checked(self) -> None:
        catalog = self._revision_catalog()
        catalog["ai_features"][-1]["requires"] = ["vector_index"]
        phases = [_phase(1, _decl("new_feature"))]
        failures, _ = check_phase_coverage(phases, catalog, revision_version=1)
        assert failures == []

    def test_greenfield_checks_everything(self) -> None:
        phases = [_phase(1, _decl("vector_index"))]
        failures, _ = check_phase_coverage(phases, _catalog(), revision_version=None)
        assert "RAG Answerer" in _messages(failures)

    def test_product_checks_skip_revision_rounds(self) -> None:
        # The product spine carries no version partition yet; a revision round
        # emits a subset of phases and must not fail spine presence.
        specs = _specs(_feature("checkout"))
        failures, advisories = check_phase_coverage(
            [_phase(1, _decl("new_feature"))],
            self._revision_catalog(),
            feature_specs=specs,
            revision_version=1,
        )
        assert "checkout" not in _messages(failures)
        assert all("checkout" not in a for a in advisories)


# ============================= product side =================================


class TestProductPresence:
    def test_all_declared_passes(self) -> None:
        specs = _specs(_feature("checkout"), _feature("catalog_browse"))
        phases = [
            _phase(1, features=[_decl("checkout")]),
            _phase(2, features=[_decl("catalog_browse")]),
        ]
        failures, _ = check_phase_coverage(phases, None, feature_specs=specs)
        assert failures == []

    def test_undeclared_spine_feature_fails(self) -> None:
        specs = _specs(_feature("checkout"), _feature("catalog_browse"))
        phases = [_phase(1, features=[_decl("checkout")])]
        failures, _ = check_phase_coverage(phases, None, feature_specs=specs)
        messages = _messages(failures)
        assert "catalog_browse" in messages
        assert "features:" in messages

    def test_unknown_product_id_fails_with_spine_source(self) -> None:
        specs = _specs(_feature("checkout"))
        phases = [_phase(1, features=[_decl("checkout"), _decl("mystery")])]
        failures, _ = check_phase_coverage(phases, None, feature_specs=specs)
        assert "Feature specifications" in _messages(failures)

    def test_catalog_id_in_features_array_is_a_cross_space_failure(self) -> None:
        # An AI-node id placed in `features[]` does not resolve in the spine —
        # the array determines the space.
        specs = _specs(_feature("checkout"))
        phases = [
            _phase(
                1,
                _decl("rag_answerer"),
                features=[_decl("checkout"), _decl("rag_answerer")],
            )
        ]
        failures, _ = check_phase_coverage(phases, _catalog(), feature_specs=specs)
        assert any(
            "features: declared id 'rag_answerer'" in " ".join(errors)
            for _, errors in failures
        )

    def test_ambiguous_id_reads_per_array(self) -> None:
        # The observed Threadline collision: one id valid in both spaces.
        # Declared in both arrays, each side reads its own space — no failure.
        specs = _specs(_feature("thread_summarization"))
        catalog = {
            "ai_features": [
                {
                    "id": "thread_summarization",
                    "name": "Thread Summarization",
                    "kind": "feature",
                    "tier": "chained_calls",
                    "phase_priority": "mvp",
                    "requires": [],
                }
            ]
        }
        phases = [
            _phase(
                1,
                _decl("thread_summarization"),
                features=[_decl("thread_summarization")],
            )
        ]
        failures, _ = check_phase_coverage(phases, catalog, feature_specs=specs)
        assert failures == []

    def test_product_roles_checked_like_capabilities(self) -> None:
        specs = _specs(_feature("checkout"))
        phases = [
            _phase(1, features=[_decl("checkout", role="extended")]),
        ]
        failures, _ = check_phase_coverage(phases, None, feature_specs=specs)
        assert "never 'introduced'" in _messages(failures)

    def test_no_spine_leaves_product_side_inert(self) -> None:
        phases = [
            _phase(1, _decl("vector_index")),
            _phase(2, _decl("rag_answerer")),
        ]
        failures, _ = check_phase_coverage(phases, _catalog(), feature_specs=None)
        assert failures == []


class TestExcludedDisposition:
    """D-PH1i/D-PH2b: rejection at the Agentifier panel excludes the feature."""

    @staticmethod
    def _specs_with_rejection() -> tuple[dict[str, Any], dict[str, Any]]:
        specs = _specs(_feature("checkout"), _feature("smart_replies"))
        catalog = {
            "ai_features": [],
            "explicitly_rejected": [
                {"name": "smart_replies", "reason": "closure_coordinator_off"}
            ],
        }
        return specs, catalog

    def test_undeclared_excluded_feature_is_advisory_not_failure(self) -> None:
        specs, catalog = self._specs_with_rejection()
        phases = [_phase(1, features=[_decl("checkout")])]
        failures, advisories = check_phase_coverage(
            phases, catalog, feature_specs=specs
        )
        assert failures == []
        assert any(
            "smart_replies" in a and "Agentifier" in a for a in advisories
        )

    def test_declared_excluded_feature_fails(self) -> None:
        specs, catalog = self._specs_with_rejection()
        phases = [
            _phase(1, features=[_decl("checkout"), _decl("smart_replies")])
        ]
        failures, _ = check_phase_coverage(phases, catalog, feature_specs=specs)
        assert "excluded from this plan" in _messages(failures)

    def test_served_feature_is_not_excluded(self) -> None:
        # The serves-join wins over a same-named rejection: the feature stays
        # required, so leaving it undeclared is a hard failure.
        specs = _specs(_feature("smart_replies"))
        catalog = {
            "ai_features": [
                {
                    "id": "smart_replies_capability",
                    "name": "smart_replies_capability",
                    "kind": "feature",
                    "tier": "single_call",
                    "phase_priority": "mvp",
                    "requires": [],
                    "vision_grounding": {
                        "served_features": [{"id": "smart_replies"}]
                    },
                }
            ],
            "explicitly_rejected": [{"name": "smart_replies"}],
        }
        phases = [_phase(1, _decl("smart_replies_capability"))]
        failures, _ = check_phase_coverage(phases, catalog, feature_specs=specs)
        assert "smart_replies (id: smart_replies)" in _messages(failures)


class TestProductDependencyOrdering:
    """D-PH2f option B: producer-first over spine dependencies, advisory."""

    def test_violation_is_advisory_not_failure(self) -> None:
        specs = _specs(
            _feature("history", dependencies=["lookup"]),
            _feature("lookup"),
        )
        phases = [
            _phase(1, features=[_decl("history")]),
            _phase(2, features=[_decl("lookup")]),
        ]
        failures, advisories = check_phase_coverage(
            phases, None, feature_specs=specs
        )
        assert failures == []
        assert any("Build order" in a and "history" in a for a in advisories)

    def test_correct_order_produces_no_advisory(self) -> None:
        specs = _specs(
            _feature("history", dependencies=["lookup"]),
            _feature("lookup"),
        )
        phases = [
            _phase(1, features=[_decl("lookup")]),
            _phase(2, features=[_decl("history")]),
        ]
        failures, advisories = check_phase_coverage(
            phases, None, feature_specs=specs
        )
        assert failures == []
        assert not any("Build order" in a for a in advisories)

    def test_same_phase_passes(self) -> None:
        specs = _specs(
            _feature("history", dependencies=["lookup"]),
            _feature("lookup"),
        )
        phases = [
            _phase(1, features=[_decl("lookup"), _decl("history")]),
        ]
        _, advisories = check_phase_coverage(phases, None, feature_specs=specs)
        assert not any("Build order" in a for a in advisories)

    def test_excluded_endpoints_are_skipped(self) -> None:
        specs = _specs(
            _feature("history", dependencies=["smart_replies"]),
            _feature("smart_replies"),
        )
        catalog = {
            "ai_features": [],
            "explicitly_rejected": [{"name": "smart_replies"}],
        }
        phases = [_phase(1, features=[_decl("history")])]
        failures, advisories = check_phase_coverage(
            phases, catalog, feature_specs=specs
        )
        assert failures == []
        assert not any("Build order" in a for a in advisories)