"""StackAdvisor input-projection baseline probe (D-SA1 / D-SA2 / D-SA3).

Measures the *deterministic input layer* of StackAdvisor: the context block
``_ai_features_for_stack`` renders from a catalog. This is a pure function of
``ai_features.json`` — no live model — so the probe runs without a live draw,
using built-in three-state fixtures, and also accepts a real draw directory
(``vision.json`` + ``ai_features.json``) when one is supplied.

It exists to make two proven defects, and their fix, attributable:

* DEFECT-1 (phantom LLM requirement): infra nodes carry a sentinel
  ``tier="infrastructure"`` that the histogram scored as ``single_call``,
  emitting an "LLM-backed features present" instruction on catalogs with zero
  generative features.
* DEFECT-2 (vector store invisibility): the RAG hint gated above the
  ``embeddings`` tier, so an embeddings feature's vector substrate was never
  surfaced to StackAdvisor — the D-PS5b mechanism (``vector_index`` declared
  required, never built).

Run from ``evals/stack_advisor/`` so the src import resolves via the installed
package:

    cd evals/stack_advisor && python3 projection_baseline.py            # fixtures
    cd evals/stack_advisor && python3 projection_baseline.py <draw_dir> # real draw

The probe is measurement tooling only; it is never wired into the pipeline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from spec4.agents._utils import _ai_features_for_stack

_GENERATIVE_TIERS = {
    "single_call",
    "rag",
    "tool_agent",
    "chained_calls",
    "planning_agent",
    "orchestrated_subagents",
    "multi_agent_collaboration",
}
_VECTOR_INFRA = {"vector_index", "embedding_pipeline"}
_PHANTOM_MARKERS = ("LLM-backed features present", "provider/client library")


def _feature_nodes(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        f
        for f in (catalog.get("ai_features") or [])
        if f.get("kind") != "infrastructure"
    ]


def _infra_nodes(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        f
        for f in (catalog.get("ai_features") or [])
        if f.get("kind") == "infrastructure"
    ]


def _classify_state(catalog: dict[str, Any]) -> str:
    feats = _feature_nodes(catalog)
    if not feats:
        return "1: no Agentifier"
    if all(f.get("tier") == "deterministic" for f in feats):
        return "2: deterministic-only"
    return "3: model-backed"


def measure(catalog: dict[str, Any]) -> dict[str, Any]:
    """Return the projection metrics for one catalog."""
    out = _ai_features_for_stack(catalog)
    feats = _feature_nodes(catalog)
    infra = _infra_nodes(catalog)

    has_generative = any(f.get("tier") in _GENERATIVE_TIERS for f in feats)
    vector_infra_present = any(n.get("name") in _VECTOR_INFRA for n in infra)
    phantom = any(m in out for m in _PHANTOM_MARKERS)
    vector_surfaced = any(name in out for name in _VECTOR_INFRA)

    ks_expected = sum(len(f.get("knowledge_sources") or []) for f in feats)
    ks_surfaced = out.count("knowledge source:")
    tool_expected = sum(
        len((f.get("tool_access") or {}).get("capabilities_needed") or [])
        for f in feats
    )
    tool_surfaced = out.count("tool access:")

    defect_1 = phantom and not has_generative
    defect_2 = vector_infra_present and not vector_surfaced

    return {
        "state": _classify_state(catalog),
        "features": len(feats),
        "infra_nodes": len(infra),
        "has_generative": has_generative,
        "vector_infra_present": vector_infra_present,
        "phantom_llm_instruction": phantom,
        "vector_surfaced": vector_surfaced,
        "knowledge_sources": f"{ks_surfaced}/{ks_expected}",
        "tool_access": f"{tool_surfaced}/{tool_expected}",
        "DEFECT_1_phantom_llm": defect_1,
        "DEFECT_2_vector_invisible": defect_2,
        "empty_output": out == "",
    }


def _infra_node(name: str, tiers: list[str]) -> dict[str, Any]:
    return {"name": name, "kind": "infrastructure", "tier": "infrastructure",
            "requires": []}


def fixtures() -> dict[str, dict[str, Any]]:
    """Built-in three-state catalogs exercising both defects."""
    det = {
        "name": "Nightly digest",
        "tier": "deterministic",
        "invocation": {"mode": "scheduled"},
        "knowledge_sources": [
            {"name": "orders_db", "type": "relational_db",
             "content_description": "order history"}
        ],
    }
    emb = {
        "name": "Semantic search",
        "tier": "embeddings",
        "knowledge_sources": [
            {"name": "docs", "type": "vector_store",
             "content_description": "help articles"}
        ],
        "requires": ["embedding_pipeline", "vector_index"],
    }
    tool = {
        "name": "Itinerary agent",
        "tier": "tool_agent",
        "tool_access": {
            "capabilities_needed": [
                {"purpose": "flight search", "source": "existing_third_party_mcp",
                 "protocol": "mcp", "mcp_server": "flights.example"}
            ]
        },
        "requires": ["tool_execution_harness"],
    }
    return {
        "state1_no_agentifier": {"ai_features": [], "cross_cutting": {}},
        "state2_deterministic_only": {
            "ai_features": [det], "cross_cutting": {}
        },
        "state3_embeddings": {
            "ai_features": [
                emb,
                _infra_node("embedding_pipeline", ["embeddings"]),
                _infra_node("vector_index", ["embeddings"]),
            ],
            "cross_cutting": {},
        },
        "state3_tool_agent": {
            "ai_features": [
                tool,
                _infra_node("tool_execution_harness", ["tool_agent"]),
            ],
            "cross_cutting": {},
        },
    }


def _load_draw(draw_dir: Path) -> dict[str, Any]:
    path = draw_dir / "ai_features.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _report(name: str, m: dict[str, Any]) -> None:
    d1 = "FAIL" if m["DEFECT_1_phantom_llm"] else "ok"
    d2 = "FAIL" if m["DEFECT_2_vector_invisible"] else "ok"
    print(f"\n[{name}]  state {m['state']}")
    print(f"  features={m['features']}  infra={m['infra_nodes']}  "
          f"generative={m['has_generative']}")
    print(f"  knowledge_sources surfaced={m['knowledge_sources']}  "
          f"tool_access surfaced={m['tool_access']}")
    print(f"  vector_infra_present={m['vector_infra_present']}  "
          f"vector_surfaced={m['vector_surfaced']}")
    print(f"  DEFECT-1 phantom-LLM: {d1}    DEFECT-2 vector-invisible: {d2}")


def main() -> int:
    if len(sys.argv) > 1:
        draw_dir = Path(sys.argv[1])
        catalog = _load_draw(draw_dir)
        _report(draw_dir.name, measure(catalog))
        return 0

    print("=== StackAdvisor projection baseline — built-in fixtures ===")
    any_defect = False
    for name, catalog in fixtures().items():
        m = measure(catalog)
        _report(name, m)
        any_defect = any_defect or m["DEFECT_1_phantom_llm"] or m[
            "DEFECT_2_vector_invisible"
        ]
    print(f"\n>>> any defect present: {any_defect}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
