"""Tests for ``spec4.feature_specs`` — the shared spec renderer.

Covers verbatim field rendering, field selection, infrastructure nodes (which
carry no spec body), ``cross_feature`` scope surfacing, and the phase-file
exclusion of ``provider_strategy``.
"""

from __future__ import annotations

from typing import Any

from spec4.feature_specs import (
    ALL_SPEC_FIELDS,
    PHASE_EXCLUDED_CROSS_CUTTING,
    PHASE_EXCLUDED_SPEC_FIELDS,
    PHASE_SPEC_FIELDS,
    render_cross_cutting,
    render_feature_block,
    spec_index,
)


def _rag_feature(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "rag_answerer",
        "name": "RAG Answerer",
        "kind": "feature",
        "tier": "rag",
        "scope": "cross_feature",
        "phase_priority": "mvp",
        "composed_under": "",
        "requires": ["vector_index"],
        "purpose": "Answer user questions grounded in the indexed corpus.",
        "invocation": {"trigger": "user submits a question", "mode": "synchronous"},
        "inputs": [
            {
                "name": "question",
                "type": "string",
                "description": "natural-language query",
                "required": True,
            },
            {
                "name": "top_k",
                "type": "integer",
                "description": "retrieval depth",
                "required": False,
            },
        ],
        "outputs": {
            "primary": "grounded answer with citations",
            "format": "JSON object",
            "schema_notes": "answer: str, sources: list[str]",
        },
        "decision_authority": "suggest",
        "success_criteria": ["p95 latency under 2s", "citation present"],
        "failure_modes": [
            {
                "mode": "no relevant chunks retrieved",
                "likelihood": "medium",
                "mitigation": "fall back to a direct answer with a caveat",
            }
        ],
        "escalation": "surface a low-confidence banner",
        "eval_approach": {
            "offline": "golden question set",
            "online": "thumbs feedback",
            "ground_truth": "curated answers",
        },
        "budgets": {"cost_per_call": "$0.01", "p95_latency": "2s"},
        "privacy_safety": ["strip PII before embedding"],
        "mechanisms": [
            {
                "name": "retrieval_reranking",
                "rationale": "raw similarity is noisy",
                "configuration": {"reranker": "cross-encoder"},
            }
        ],
        "knowledge_sources": [
            {
                "name": "docs_corpus",
                "type": "vector_store",
                "content_description": "product documentation",
                "update_frequency": "daily",
            }
        ],
        "references": ["https://example.invalid/rag"],
        "tier_analysis": {
            "rationale": "requires grounding in a private corpus",
            "compared_to_next_tier_down": "single_call would hallucinate specifics",
            "borderline": True,
            "borderline_seams": ["chunk size sensitivity"],
        },
    }
    base.update(overrides)
    return base


def _infra_node(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "vector_index",
        "name": "vector_index",
        "kind": "infrastructure",
        "tier": "infrastructure",
        "scope": "feature",
        "phase_priority": "steel_thread",
        "composed_under": "",
        "requires": [],
        "rough_description": (
            "Enabling infrastructure (vector index): shared substrate."
        ),
    }
    base.update(overrides)
    return base


class TestRenderFeatureBlock:
    def test_renders_every_spec_field_verbatim(self) -> None:
        text = "\n".join(render_feature_block(_rag_feature()))
        # Purpose and the structured spec body all reach the output.
        assert "Answer user questions grounded in the indexed corpus." in text
        assert "user submits a question" in text
        assert "`question`" in text and "required" in text
        assert "`top_k`" in text and "optional" in text
        assert "grounded answer with citations" in text
        assert "answer: str, sources: list[str]" in text
        assert "suggest" in text
        assert "p95 latency under 2s" in text
        assert "no relevant chunks retrieved" in text
        assert "fall back to a direct answer with a caveat" in text
        assert "surface a low-confidence banner" in text
        assert "golden question set" in text
        assert "$0.01" in text
        assert "strip PII before embedding" in text
        assert "retrieval_reranking" in text
        assert "cross-encoder" in text
        assert "docs_corpus" in text
        assert "https://example.invalid/rag" in text

    def test_renders_tier_analysis_and_edges(self) -> None:
        text = "\n".join(render_feature_block(_rag_feature()))
        assert "Tier: `rag`" in text
        assert "requires grounding in a private corpus" in text
        assert "single_call would hallucinate specifics" in text
        assert "chunk size sensitivity" in text
        assert "`vector_index`" in text

    def test_cross_feature_scope_is_explained(self) -> None:
        text = "\n".join(render_feature_block(_rag_feature()))
        assert "spans more than one vision feature" in text

    def test_plain_scope_is_rendered_bare(self) -> None:
        text = "\n".join(render_feature_block(_rag_feature(scope="sub_feature")))
        assert "Scope: `sub_feature`" in text
        assert "spans more than one vision feature" not in text

    def test_field_selection_limits_output(self) -> None:
        text = "\n".join(
            render_feature_block(
                _rag_feature(),
                fields=("purpose", "invocation"),
                include_graph=False,
            )
        )
        assert "Answer user questions" in text
        assert "user submits a question" in text
        # Deselected fields are absent entirely.
        assert "Failure modes" not in text
        assert "Budgets" not in text

    def test_absent_fields_are_skipped_silently(self) -> None:
        sparse = {"id": "x", "name": "X", "purpose": "Do a thing."}
        text = "\n".join(render_feature_block(sparse))
        assert "Do a thing." in text
        assert "Inputs" not in text

    def test_empty_spec_falls_back_to_rough_description(self) -> None:
        node = {"id": "x", "name": "X", "rough_description": "A rough sketch."}
        text = "\n".join(render_feature_block(node))
        assert "A rough sketch." in text

    def test_null_scalars_are_dropped(self) -> None:
        feature = _rag_feature(
            outputs={"primary": "answer", "format": "", "schema_notes": None}
        )
        text = "\n".join(render_feature_block(feature))
        assert "Primary: answer" in text
        assert "Schema notes" not in text

    def test_all_spec_fields_have_a_renderer(self) -> None:
        # Guards against adding a field to the canonical order without a renderer.
        from spec4.feature_specs import _FIELD_RENDERERS

        assert set(ALL_SPEC_FIELDS) <= set(_FIELD_RENDERERS)


class TestInfrastructureNodes:
    def test_infra_renders_as_labelled_substrate(self) -> None:
        text = "\n".join(render_feature_block(_infra_node()))
        assert "Enabling infrastructure" in text
        assert "substrate" in text
        assert "stand it up before anything that requires it" in text

    def test_infra_never_renders_an_empty_spec_body(self) -> None:
        text = "\n".join(render_feature_block(_infra_node()))
        assert "Inputs" not in text
        assert "Failure modes" not in text

    def test_infra_spec_fields_are_ignored_even_if_present(self) -> None:
        # Defensive: a stray spec field on an infra node must not resurrect the
        # normal feature rendering path.
        node = _infra_node(purpose="should not appear")
        text = "\n".join(render_feature_block(node))
        assert "should not appear" not in text


class TestRenderCrossCutting:
    def _cross(self) -> dict[str, Any]:
        return {
            "provider_strategy": {
                "recommendation": "a strong general model",
                "rationale": "the RAG tier needs reasoning",
            },
            "prompt_versioning": {
                "recommendation": "pin prompts per release",
                "rationale": "reproducibility",
            },
        }

    def test_renders_recommendations_and_rationales(self) -> None:
        text = "\n".join(render_cross_cutting(self._cross()))
        assert "a strong general model" in text
        assert "pin prompts per release" in text
        assert "reproducibility" in text

    def test_phase_exclusion_drops_provider_strategy(self) -> None:
        text = "\n".join(
            render_cross_cutting(self._cross(), exclude=PHASE_EXCLUDED_CROSS_CUTTING)
        )
        assert "a strong general model" not in text
        assert "pin prompts per release" in text

    def test_empty_or_missing_yields_nothing(self) -> None:
        assert render_cross_cutting(None) == []
        assert render_cross_cutting({}) == []
        assert render_cross_cutting({"x": {"recommendation": ""}}) == []

    def test_excluding_everything_yields_nothing(self) -> None:
        cross = {"provider_strategy": {"recommendation": "x"}}
        assert render_cross_cutting(cross, exclude=("provider_strategy",)) == []


class TestSpecIndex:
    def test_indexes_by_id(self) -> None:
        catalog = {"ai_features": [_rag_feature(), _infra_node()]}
        index = spec_index(catalog)
        assert set(index) == {"rag_answerer", "vector_index"}

    def test_skips_nodes_without_an_id(self) -> None:
        catalog = {"ai_features": [{"name": "no id"}, _infra_node()]}
        assert set(spec_index(catalog)) == {"vector_index"}

    def test_missing_catalog_yields_empty_index(self) -> None:
        assert spec_index(None) == {}
        assert spec_index({}) == {}


class TestPhaseSpecFields:
    """D-PS13: the coder-facing preamble carries the build contract, not the
    operating contract.

    `budgets` and `eval_approach` are drafted before StackAdvisor picks a stack,
    so they routinely price and compare vendors that were never selected.
    """

    def test_excluded_fields_are_budgets_and_eval_approach(self) -> None:
        assert PHASE_EXCLUDED_SPEC_FIELDS == ("budgets", "eval_approach")

    def test_phase_fields_are_all_fields_minus_exclusions(self) -> None:
        assert set(PHASE_SPEC_FIELDS) == set(ALL_SPEC_FIELDS) - set(
            PHASE_EXCLUDED_SPEC_FIELDS
        )
        # Canonical order is preserved, not merely the set.
        assert list(PHASE_SPEC_FIELDS) == [
            f for f in ALL_SPEC_FIELDS if f not in PHASE_EXCLUDED_SPEC_FIELDS
        ]

    def test_phase_render_drops_budgets_and_eval_approach(self) -> None:
        feature = _rag_feature(
            budgets={"cost_per_call": "$0.00002 via text-embedding-3-small"},
            eval_approach={"offline": "compare OpenAI vs Cohere embeddings"},
        )
        text = "\n".join(render_feature_block(feature, fields=PHASE_SPEC_FIELDS))
        assert "Budgets" not in text
        assert "Eval approach" not in text
        assert "text-embedding-3-small" not in text
        assert "Cohere" not in text

    def test_phase_render_keeps_the_build_contract(self) -> None:
        text = "\n".join(render_feature_block(_rag_feature(), fields=PHASE_SPEC_FIELDS))
        for kept in (
            "Invocation",
            "Inputs",
            "Outputs",
            "Decision authority",
            "Success criteria",
            "Failure modes",
            "Escalation",
            "Privacy & safety",
            "Mechanisms",
            "References",
        ):
            assert kept in text, kept

    def test_default_render_still_carries_everything(self) -> None:
        # Phaser's own context is unchanged: it sequences with cost in mind.
        text = "\n".join(render_feature_block(_rag_feature()))
        assert "Budgets" in text and "Eval approach" in text


class TestMechanismGlossary:
    """Each mechanism entry carries the pattern library's canonical one-line
    definition. The rendered spec is the only channel to Phaser and the coding
    agent — without it, `reflection` means whatever the reader thinks it
    means, which is the drift the library exists to end."""

    def test_known_mechanism_gets_its_definition(self) -> None:
        text = "\n".join(render_feature_block(_rag_feature()))
        assert "`retrieval_reranking` — raw similarity is noisy" in text
        idx = text.index("`retrieval_reranking`")
        block = text[idx : idx + 600]
        assert "- definition: " in block
        # A distinctive phrase from the pattern's description, not the
        # instance rationale — proves the library is the source.
        assert "second, more expensive scorer" in block

    def test_definition_sits_with_the_entry_not_in_a_far_section(self) -> None:
        text = "\n".join(render_feature_block(_rag_feature()))
        lines = text.splitlines()
        head = next(
            i for i, ln in enumerate(lines) if "`retrieval_reranking`" in ln
        )
        assert lines[head + 1].strip().startswith("- definition: ")

    def test_unknown_mechanism_renders_without_definition(self) -> None:
        feature = _rag_feature(
            mechanisms=[{"name": "bespoke_magic", "rationale": "why not"}]
        )
        text = "\n".join(render_feature_block(feature))
        assert "`bespoke_magic` — why not" in text
        assert "definition:" not in text

    def test_all_library_mechanisms_have_definitions(self) -> None:
        from spec4.feature_specs import _mechanism_definitions

        definitions = _mechanism_definitions()
        for name in (
            "human_in_the_loop",
            "mcp",
            "parallel_fanout",
            "reflection",
            "retrieval_reranking",
            "structured_outputs",
        ):
            assert definitions.get(name), name
            assert len(definitions[name]) <= 201  # trimmed, one line
            assert "\n" not in definitions[name]
