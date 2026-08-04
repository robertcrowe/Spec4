"""StackAdvisor output baseline probe (D-SA4 / D-SA5 / D-SA6).

Measures the *output* `stack.json` StackAdvisor produces, against the three
combined-lever goals, each asserted independently so a single validating draw
yields three separate verdicts:

* D-SA4 serves_features — every library / infrastructure entry that exists to
  serve specific AI feature(s) carries a ``serves_features`` list referencing
  known feature ids.
* D-SA5 infrastructure — a top-level ``infrastructure`` block keyed to each
  tier-required substrate (from the catalog's infra nodes), each with a concrete
  named choice.
* D-SA6 providers — a ``providers`` block naming provider(s), model/capability
  per tier in use, and a credential env var. Gated: required only when the
  catalog has a model-backed feature (tier >= embeddings); for a deterministic-
  only or no-Agentifier build, an absent providers block is correct (PASS).

Reads a draw directory holding ``stack.json`` (required) and, when present,
``ai_features.json`` (to know what *should* be covered). Run from
``evals/stack_advisor/`` so the sibling import resolves:

    cd evals/stack_advisor && python3 output_baseline.py <draw_dir>

Measurement tooling only — never wired into the pipeline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_MODEL_TIERS = {
    "embeddings", "single_call", "rag", "tool_agent", "chained_calls",
    "planning_agent", "orchestrated_subagents", "multi_agent_collaboration",
}
# Generative tiers call a text-generation model — effectively always *served*
# (a cloud API or a local runtime like Ollama/vLLM), so they always warrant a
# providers block. ``embeddings`` is the ambiguous tier: it may be served (a
# hosted embedding API) or run in-process as a library (sentence-transformers).
_GENERATIVE_TIERS = _MODEL_TIERS - {"embeddings"}
# Signals that a served model (cloud or local runtime) is in use — used only to
# disambiguate the embeddings case. Deliberately specific to avoid matching a
# generic REST "endpoint" in the app's own deployment.
_SERVING_SIGNALS = (
    "base_url", "endpoint_env", "ollama", "vllm", "lm studio", "llama.cpp",
    "text-generation-inference", "huggingface inference", "_api_key", "api_key",
    "openai", "anthropic", "cohere", "gemini", "bedrock", "litellm",
)


def _stack_spec(stack: dict[str, Any]) -> dict[str, Any]:
    return stack.get("stack_spec") or stack.get("stack") or stack


def _feature_ids(catalog: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for f in (catalog.get("ai_features") or []):
        if f.get("kind") == "infrastructure":
            continue
        for key in ("id", "name"):
            if f.get(key):
                out.add(str(f[key]))
    return out


def _required_substrates(catalog: dict[str, Any]) -> set[str]:
    return {
        f.get("name") or f.get("id")
        for f in (catalog.get("ai_features") or [])
        if f.get("kind") == "infrastructure"
    }


def _has_model_feature(catalog: dict[str, Any]) -> bool:
    return any(
        f.get("tier") in _MODEL_TIERS
        for f in (catalog.get("ai_features") or [])
        if f.get("kind") != "infrastructure"
    )


def _has_generative_feature(catalog: dict[str, Any]) -> bool:
    return any(
        f.get("tier") in _GENERATIVE_TIERS
        for f in (catalog.get("ai_features") or [])
        if f.get("kind") != "infrastructure"
    )


def _iter_library_entries(ss: dict[str, Any]) -> list[dict[str, Any]]:
    """All library entries across every category (libraries is category->list)."""
    entries: list[dict[str, Any]] = []
    libs = ss.get("libraries") or {}
    if isinstance(libs, dict):
        for group in libs.values():
            if isinstance(group, list):
                entries += [e for e in group if isinstance(e, dict)]
    elif isinstance(libs, list):
        entries += [e for e in libs if isinstance(e, dict)]
    return entries


def measure(stack: dict[str, Any], catalog: dict[str, Any] | None) -> dict[str, Any]:
    ss = _stack_spec(stack)
    flat = json.dumps(ss).lower()
    catalog = catalog or {}
    feat_ids = _feature_ids(catalog)
    substrates = _required_substrates(catalog)

    # --- D-SA4 serves_features ---
    lib_entries = _iter_library_entries(ss)
    infra_block = ss.get("infrastructure")
    tagged = sum(
        1
        for e in lib_entries
        if isinstance(e, dict) and e.get("serves_features")
    )
    serves_present = "serves_features" in flat
    serves_valid = False
    if serves_present and feat_ids:
        # at least one serves_features value references a known feature id
        serves_valid = any(
            isinstance(e, dict)
            and any(str(x) in feat_ids for x in (e.get("serves_features") or []))
            for e in lib_entries
        )

    # soft completeness signal: which catalog features are reachable via some
    # serves_features (across libraries AND the infrastructure block)? Not a hard
    # gate — a pure-logic feature may have no dedicated library — but it surfaces
    # an under-tagged feature (e.g. a deterministic feature's extraction library).
    linked_ids: set[str] = set()
    for e in lib_entries:
        for x in (e.get("serves_features") or []):
            linked_ids.add(str(x))
    if isinstance(infra_block, dict):
        for v in infra_block.values():
            if isinstance(v, dict):
                for x in (v.get("serves_features") or []):
                    linked_ids.add(str(x))
    covered = sorted(fid for fid in feat_ids if fid in linked_ids)
    uncovered = sorted(fid for fid in feat_ids if fid not in linked_ids)
    coverage = f"{len(covered)}/{len(feat_ids)}" if feat_ids else "0/0"

    # --- D-SA5 infrastructure block keyed to required substrates ---
    infra_present = isinstance(infra_block, dict) and bool(infra_block)
    substrates_keyed = (
        {s for s in substrates if s and s in (infra_block or {})}
        if infra_present else set()
    )
    substrate_coverage = (
        f"{len(substrates_keyed)}/{len(substrates)}" if substrates else "0/0"
    )

    # --- D-SA6 providers block (served-vs-in-process gate) ---
    # A providers block is warranted when a *served* model backs a feature — cloud
    # or a local runtime (Ollama/vLLM). It is optional when the only model-backed
    # features run in-process as a library (e.g. sentence-transformers). Generative
    # tiers are effectively always served → always require. ``embeddings`` is the
    # ambiguous tier: require only if the stack shows a serving signal (a hosted
    # key/provider, or a local runtime/endpoint); otherwise treat as in-process.
    providers = ss.get("providers")
    providers_present = isinstance(providers, dict) and bool(providers)
    prov_entries = [v for v in (providers or {}).values() if isinstance(v, dict)]
    has_model_per_tier = any("capability_by_tier" in e for e in prov_entries)
    has_cred = any("credentials_env" in e for e in prov_entries)
    structured = providers_present and has_model_per_tier and has_cred

    has_generative = _has_generative_feature(catalog)
    has_model = _has_model_feature(catalog)
    serving_signal = any(m in flat for m in _SERVING_SIGNALS)
    if has_generative:
        require_block = True
    elif has_model:  # embeddings-only
        require_block = serving_signal
    else:
        require_block = False

    # verdicts
    d4 = serves_valid  # want feature-id-linked tags
    d5 = (not substrates) or (len(substrates_keyed) == len(substrates))
    if require_block:
        d6 = structured
    else:
        # optional: absence is the in-process ideal; if a block IS emitted it must
        # still be structured (not a free-text note).
        d6 = (not providers_present) or structured

    # --- cross-cutting: prompt_versioning recorded when the analyst warranted it ---
    cc = catalog.get("cross_cutting") or {}
    pv_warranted = bool((cc.get("prompt_versioning") or {}).get("recommendation"))
    pv_recorded = bool((ss.get("ai_conventions") or {}).get("prompt_versioning"))
    d_pv = (not pv_warranted) or pv_recorded

    return {
        "needs_provider": has_model,
        "provider_block_required": require_block,
        "serving_signal": serving_signal,
        "feature_ids": sorted(feat_ids),
        "required_substrates": sorted(s for s in substrates if s),
        "D-SA4_serves_features": {
            "present": serves_present,
            "valid_id_linked": serves_valid,
            "entries_tagged": f"{tagged}/{len(lib_entries)}",
            "feature_link_coverage": coverage,
            "uncovered_features": uncovered,
            "PASS": d4,
        },
        "D-SA5_infrastructure": {
            "block_present": infra_present,
            "substrates_keyed": substrate_coverage,
            "PASS": d5,
        },
        "D-SA6_providers": {
            "block_present": providers_present,
            "block_required": require_block,
            "structured": structured,
            "PASS": d6,
        },
        "CC_prompt_versioning": {
            "warranted": pv_warranted,
            "recorded": pv_recorded,
            "PASS": d_pv,
        },
        "ALL_PASS": d4 and d5 and d6 and d_pv,
    }


def _load(draw_dir: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    stack = json.loads((draw_dir / "stack.json").read_text(encoding="utf-8"))
    cat_path = draw_dir / "ai_features.json"
    catalog = (
        json.loads(cat_path.read_text(encoding="utf-8"))
        if cat_path.exists() else None
    )
    return stack, catalog


def _report(name: str, m: dict[str, Any]) -> None:
    print(f"\n[{name}]  needs_provider={m['needs_provider']}")
    print(f"  required substrates: {m['required_substrates'] or '(none)'}")
    for key in ("D-SA4_serves_features", "D-SA5_infrastructure", "D-SA6_providers",
                "CC_prompt_versioning"):
        block = m[key]
        verdict = "PASS" if block["PASS"] else "FAIL"
        details = ", ".join(
            f"{k}={v}" for k, v in block.items() if k != "PASS"
        )
        print(f"  {key}: {verdict}   ({details})")
    print(f"  >>> ALL_PASS: {m['ALL_PASS']}")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: output_baseline.py <draw_dir> [<draw_dir> ...]")
        return 2
    for arg in sys.argv[1:]:
        d = Path(arg)
        stack, catalog = _load(d)
        _report(d.name, measure(stack, catalog))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
