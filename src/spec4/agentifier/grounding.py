"""Vision grounding — join Agentifier AI-feature nodes to the Brainstormer
product-feature specs they serve.

Brainstormer specs a *product* feature (``feature_specs.json``, keyed by
``slug(name)``). Agentifier's Scout proposes an *AI* feature that serves 0..N
product features, recorded on each candidate as ``linked_vision_features`` — a
list of vision-feature NAMES (Scout coins its own AI-capability names, so the
relation is "serves", never identity). This module resolves those names to their
product-feature specs by the canonical ``slug()`` join (D-AC2 A, exact match)
and packages them as the node's ``vision_grounding``: carried verbatim (lossless
— D-AC1 B) and fed to the Spec Drafter as authoritative product context so it
specifies each AI feature against real behavioral detail rather than a one-line
rough description.

Cardinality is inherent, not a special case: a coordinator's
``linked_vision_features`` is already the order-preserving union of its members'
links (``composer._union_features``), so the same builder grounds coordinators
with no extra logic (D-AC3). An empty link list is legitimate — a cross-cutting
AI feature serves no named product feature — and yields empty grounding. A NAMED
link that fails to resolve is the real miss and is reported separately in
``unresolved_links`` (D-AC2 A); it is the safety-net signal, not a crash.

The served specs carry each product feature's full behavioral detail verbatim,
so the feature-level dependency graph (D-AC6) and domain ``entities`` (D-AC7)
ride along inside ``served_features`` with no separate plumbing. Project-level
``nfr_goals`` is join-independent and is stamped onto the Agentifier output at
its finalization locus, not here.
"""

from __future__ import annotations

from typing import Any

from spec4.agents._utils import slug


def spec_by_id(feature_specs: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Index product-feature specs by ``id`` (= ``slug(name)``), the join key.

    Falls back to ``slug(name)`` for any spec missing an explicit id. Nodes that
    are not dicts, or that resolve to an empty id, are skipped.
    """
    features = (feature_specs or {}).get("features") or []
    index: dict[str, dict[str, Any]] = {}
    for feat in features:
        if not isinstance(feat, dict):
            continue
        fid = str(feat.get("id") or "").strip() or slug(str(feat.get("name") or ""))
        if fid:
            index[fid] = feat
    return index


def build_grounding(
    feature_specs: dict[str, Any] | None,
    linked_vision_features: list[str] | None,
) -> dict[str, Any]:
    """Resolve a node's linked vision-feature NAMES to product-feature specs.

    Returns ``{"served_features": [...], "unresolved_links": [...]}`` with each
    key present only when non-empty; an empty dict means the node serves no named
    product feature (legitimate for cross-cutting AI features). ``served_features``
    carries each matched product-feature spec verbatim (lossless). A named link
    with no matching spec lands in ``unresolved_links`` (D-AC2 A) rather than
    silently vanishing. Duplicate links (a coordinator's union may repeat a
    member's feature) are de-duplicated by id, preserving first-seen order.
    """
    index = spec_by_id(feature_specs)
    served: list[dict[str, Any]] = []
    unresolved: list[str] = []
    seen: set[str] = set()
    for raw in linked_vision_features or []:
        name = str(raw or "").strip()
        if not name:
            continue
        fid = slug(name)
        spec = index.get(fid)
        if spec is None:
            if name not in unresolved:
                unresolved.append(name)
            continue
        if fid in seen:
            continue
        seen.add(fid)
        served.append(spec)
    grounding: dict[str, Any] = {}
    if served:
        grounding["served_features"] = served
    if unresolved:
        grounding["unresolved_links"] = unresolved
    return grounding


def _input_label(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "").strip()
    typ = str(item.get("type") or "").strip()
    if name and typ:
        return f"{name} ({typ})"
    return name or typ


def render_grounding_for_prompt(grounding: dict[str, Any] | None) -> str:
    """Render served product-feature specs as authoritative Spec-Drafter context.

    Empty grounding (no served features) yields ``""`` so the prompt is unchanged
    for cross-cutting AI features. ``unresolved_links`` is deliberately not shown
    to the model — it is an internal quality signal, not context to specify
    against.
    """
    served = (grounding or {}).get("served_features") or []
    if not served:
        return ""
    lines = [
        "**Product features this AI feature serves** (from the confirmed vision — "
        "authoritative behavioral context; specify this feature so it serves and "
        "stays consistent with the following, rather than re-deriving or "
        "contradicting them):",
        "",
    ]
    for feat in served:
        if not isinstance(feat, dict):
            continue
        name = feat.get("name") or feat.get("id") or "(unnamed)"
        lines.append(f"- **{name}**")
        purpose = str(feat.get("purpose") or "").strip()
        if purpose:
            lines.append(f"  - Purpose: {purpose}")
        inv = feat.get("invocation")
        trigger = inv.get("trigger") if isinstance(inv, dict) else None
        if trigger:
            lines.append(f"  - Trigger: {trigger}")
        inputs = [i for i in (feat.get("inputs") or []) if isinstance(i, dict)]
        if inputs:
            rendered = ", ".join(_input_label(i) for i in inputs if _input_label(i))
            if rendered:
                lines.append(f"  - Inputs: {rendered}")
        outputs = feat.get("outputs")
        if isinstance(outputs, dict):
            primary = str(outputs.get("primary") or "").strip()
            if primary:
                lines.append(f"  - Output: {primary}")
        sc = [str(s) for s in (feat.get("success_criteria") or []) if s]
        if sc:
            lines.append(f"  - Success criteria: {'; '.join(sc)}")
        modes = [
            str(m.get("mode"))
            for m in (feat.get("failure_modes") or [])
            if isinstance(m, dict) and m.get("mode")
        ]
        if modes:
            lines.append(f"  - Failure modes: {'; '.join(modes)}")
        entities = [str(e) for e in (feat.get("entities") or []) if e]
        if entities:
            lines.append(f"  - Domain entities: {', '.join(entities)}")
        deps = [str(d) for d in (feat.get("dependencies") or []) if d]
        if deps:
            lines.append(f"  - Depends on (build order): {', '.join(deps)}")
    lines.append("")
    return "\n".join(lines)
