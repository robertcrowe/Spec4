"""Deterministic tier-required infrastructure expansion.

The *real feature* is what the developer selected; the enabling substrate a
tier implies (a vector index, a tool-execution harness, a peer-negotiation
mediator) is **infrastructure**, injected based on the *tiers* of the features
that were kept. This is a **registry lookup, not LLM invention**, and a
**deterministic expansion pass, not an instruction inside any agent's prompt** —
same thesis as the Linker: give the model closed, checkable tasks; keep open
graph reasoning out of the LLM.

Ratified decisions this module implements:

* **D-I2 (option B)** — runs *post-assembly*, over the final feature dicts,
  entirely off the LLM path. It materialises nodes and wires edges the way the
  Composer materialises coordinator heads, rather than asking a model to invent
  substrate.
* **D-I3** — components are generic string-id nodes; identity is the id; dedup
  is by id; no per-corpus parameterisation.
* **Infra is a source node** — injected nodes carry *no* ``requires`` of their
  own. Substrate is foundational build-order scaffolding (you stand up an
  embedding pipeline or a vector index before any feature feeds it), so it is a
  pure source: features require it, it requires nothing. This supersedes the
  original D-I4(ii) upstream-inheritance rule, which encoded a runtime data-flow
  fact into ``requires`` (a build-order channel) and thereby produced priority
  inversions (a steel_thread node ordered after an ``mvp`` producer) and closed
  ``requires`` cycles when a triggering feature sat upstream of an inherited
  producer. A node with no out-edges cannot sit in a cycle and has no producer
  to invert against, so this removes both failure classes structurally rather
  than repairing them after the fact.
* **D-I5** — injected nodes carry ``kind: "infrastructure"``.
* **D-I6** — injected nodes carry ``phase_priority: "steel_thread"``.

The pass is idempotent and revision-safe: it dedups against infrastructure nodes
already present in the feature set, so a carried-forward component is not
re-injected, while a genuinely new tier still contributes its component.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "INFRA_KIND",
    "INFRA_TIER",
    "INFRA_PRIORITY",
    "expand_infrastructure",
]

# Marker written onto injected nodes and used to partition them back out.
INFRA_KIND = "infrastructure"
# Sentinel tier for infra nodes — deliberately not one of the nine ladder tiers,
# so downstream ladder logic never treats substrate as a selectable capability.
INFRA_TIER = "infrastructure"
# Foundational priority (D-I6): substrate is part of the core thread — nothing
# runs without it — and reuses the existing ``steel_thread`` value rather than
# widening the priority enum.
INFRA_PRIORITY = "steel_thread"


def _slug(name: str) -> str:
    """Feature-id slug, matching ``_build_ai_features``' id derivation."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower()) if name else ""


def _infra_description(component: str, tiers: list[str]) -> str:
    """Templated node description (D-I3: no separate component metadata table)."""
    pretty = component.replace("_", " ")
    tier_list = ", ".join(sorted(t for t in tiers if t)) or "selected"
    return (
        f"Enabling infrastructure ({pretty}): shared substrate injected because "
        f"the selected {tier_list} feature(s) require it. Not a user-selected "
        "feature — foundational and tier-derived."
    )


def _infra_node(
    component: str,
    triggering_tiers: list[str],
    introduced_in_version: int | None,
) -> dict[str, Any]:
    """Materialise one infrastructure node as a full feature dict.

    Infrastructure is a source node: ``requires`` is always empty. Features
    require the substrate (the downstream edges), never the other way round.
    """
    node: dict[str, Any] = {
        "id": _slug(component),
        "name": component,
        "linked_vision_features": [],
        "scope": "feature",
        "kind": INFRA_KIND,
        "tier": INFRA_TIER,
        "tier_recommendation": "",
        "tier_decision_rationale": "",
        "rough_description": _infra_description(component, triggering_tiers),
        "composed_under": "",
        "requires": [],
        "tier_analysis": {},
        "phase_priority": INFRA_PRIORITY,
    }
    if introduced_in_version is not None:
        # Revision round: stamp so Phaser phases new substrate rather than
        # misfiling it as already-implemented (S6). Carried infra keeps its own
        # stamp — it is deduped out before we reach here.
        node["introduced_in_version"] = introduced_in_version
    return node


def expand_infrastructure(
    features: list[dict[str, Any]],
    tier_infrastructure: dict[str, list[str]],
    introduced_in_version: int | None = None,
) -> list[dict[str, Any]]:
    """Inject tier-required infrastructure nodes into ``features``.

    Args:
        features: the assembled AI-feature dicts (selectable features, possibly
            already including infrastructure nodes from a prior revision round).
        tier_infrastructure: registry map ``tier name -> [component id, ...]``
            (from ``TierPattern.required_infrastructure``).
        introduced_in_version: when set (revision round), newly injected nodes
            are stamped with this version so Phaser treats them as new.

    Returns:
        A new list: the original selectable features (mutated in place to gain
        their downstream ``requires`` edges) followed by any pre-existing
        infrastructure nodes, then the newly injected ones (sorted by id for a
        deterministic order).

    The pass never invokes a model and never removes a node (lossless).
    """
    feats = [f for f in features if f.get("kind") != INFRA_KIND]
    existing_infra = [f for f in features if f.get("kind") == INFRA_KIND]
    existing_infra_names = {f.get("name") for f in existing_infra}

    # component id -> triggering feature dicts (insertion order = feature order).
    triggered: dict[str, list[dict[str, Any]]] = {}
    for f in feats:
        tier = f.get("tier", "")
        for component in tier_infrastructure.get(tier, ()):  # () for 01/03/unknown
            triggered.setdefault(component, []).append(f)

    if not triggered:
        return list(features)

    # Downstream edges (deterministic from tier): each triggering feature
    # consumes the component. Idempotent — re-runs do not duplicate the edge.
    for component, trig_feats in triggered.items():
        for f in trig_feats:
            reqs = f.setdefault("requires", [])
            if component not in reqs:
                reqs.append(component)

    new_infra: list[dict[str, Any]] = []
    for component, trig_feats in triggered.items():
        if component in existing_infra_names:
            continue  # revision idempotency: already present, edges asserted above
        # Infra is a source node: no upstream ``requires`` (see module docstring).
        tiers_for_component = [f.get("tier", "") for f in trig_feats]
        new_infra.append(
            _infra_node(component, tiers_for_component, introduced_in_version)
        )

    new_infra.sort(key=lambda n: n["id"])
    return feats + existing_infra + new_infra
