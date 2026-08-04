"""Design manifest (D-DM): extract, enrich, and validate the plan-then-build plan.

Designer generates the mock plan-then-build (D-DM2a): it emits a structured
manifest between sentinels, then the HTML that realizes it. This module pulls the
manifest out of the model output, pins the catalog-fact fields on AI surfaces so
the model can't drift them (D-DM4), and runs the advisory coverage/reference
guardrail (D-DM5). Nothing here blocks a mock from saving — the manifest is a
handoff aid for Phaser, not load-bearing, so failures degrade to warnings.
"""

from __future__ import annotations

import json
import re
from typing import Any

from spec4.agents._utils import slug

MANIFEST_START = "<<<DESIGN_MANIFEST>>>"
MANIFEST_END = "<<<END_DESIGN_MANIFEST>>>"


def _unwrap_vision(vision: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(vision, dict):
        return {}
    inner = vision.get("vision_statement")
    return inner if isinstance(inner, dict) else vision


def _user_facing_ai_surfaces(ai_features: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map each user-facing AI surface name to its catalog-fact fields."""
    feats: list[dict[str, Any]] = (ai_features or {}).get("ai_features") or []
    out: dict[str, dict[str, Any]] = {}
    for f in feats:
        infra = f.get("tier") == "infrastructure" or f.get("kind") == "infrastructure"
        if f.get("scope") == "feature" and not infra:
            name = f.get("name")
            if name:
                out[name] = {
                    "id": f.get("id") or slug(str(name)),
                    "implements_features": f.get("linked_vision_features") or [],
                    "invocation": f.get("invocation") or {},
                }
    return out


def _feature_name_to_id(vision: dict[str, Any] | None) -> dict[str, str]:
    """Map each vision feature *name* to its stable *id* — the DR4 join key.

    Handles the shapes Brainstormer emits: ``key_features_mvp`` nested under
    ``vision_statement.vision`` (canonical) or directly under the statement, with
    entries as ``{Name: {..., id}}``, ``{name, id, ...}``, or a bare ``{name}``.
    Falls back to ``slug(name)`` when an entry carries no id, matching the
    ``id == slug(name)`` invariant. Returns ``{}`` when no features are present.
    """
    vs = _unwrap_vision(vision)
    inner = vs.get("vision")
    kf = inner.get("key_features_mvp") if isinstance(inner, dict) else None
    if kf is None:
        kf = vs.get("key_features_mvp")
    out: dict[str, str] = {}
    for item in kf or []:
        if not isinstance(item, dict):
            continue
        if "name" in item:
            name = str(item["name"])
            out[name] = str(item.get("id") or slug(name))
        else:
            for key, val in item.items():
                fid = val.get("id") if isinstance(val, dict) else None
                out[str(key)] = str(fid or slug(str(key)))
    return out


def extract_manifest(text: str) -> dict[str, Any] | None:
    """Parse the sentinel-delimited manifest JSON from model output, or None."""
    match = re.search(
        re.escape(MANIFEST_START) + r"(.*?)" + re.escape(MANIFEST_END),
        text,
        re.DOTALL,
    )
    if not match:
        return None
    body = match.group(1).strip()
    # Tolerate a ```json fence the model may add inside the sentinels.
    fence = re.match(r"```(?:json)?\s*(.*?)\s*```$", body, re.DOTALL)
    if fence:
        body = fence.group(1).strip()
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def enrich_manifest(
    manifest: dict[str, Any],
    ai_features: dict[str, Any],
    vision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pin catalog facts and the stable id join keys the manifest carries (DR4).

    Each AI surface is matched to its catalog entry by its ``catalog_surface``
    link, not its ``name`` — the model renames/regroups surfaces for the UI, so
    the link is what ties a UI surface back to the AI feature it realizes. The
    linkage + invocation fields are pure catalog facts the model must not invent,
    so we overwrite them; UI-shaped fields (inputs/output) and derived fields
    (affordance/states) stay as the model authored them.

    On top of that, we pin two *derived* join keys so the manifest is joinable by
    the stable id the rest of the pipeline uses (DR4), alongside the
    human-readable names the model authors:

    - ``catalog_surface_id`` on every AI surface — the catalog node's id resolved
      from its ``catalog_surface`` name (``slug`` fallback when unresolved).
    - ``implements_feature_ids`` on every surface — the vision feature *ids* for
      its ``implements_features`` names, via the vision name→id map (``slug``
      fallback when the vision is absent or a name is unmapped).

    ``vision`` is optional; without it the id maps degrade to slug derivation,
    which still honours the ``id == slug(name)`` invariant.
    """
    facts = _user_facing_ai_surfaces(ai_features or {})
    name_to_id = _feature_name_to_id(vision)
    for surface in manifest.get("surfaces") or []:
        if not isinstance(surface, dict):
            continue
        if surface.get("kind") == "ai":
            catalog_surface = surface.get("catalog_surface")
            fact = facts.get(catalog_surface)
            if fact:
                surface["implements_features"] = fact["implements_features"]
                if fact["invocation"]:
                    surface["invocation"] = fact["invocation"]
                surface["catalog_surface_id"] = fact["id"]
            elif catalog_surface:
                surface["catalog_surface_id"] = slug(str(catalog_surface))
        impl = surface.get("implements_features") or []
        surface["implements_feature_ids"] = [
            name_to_id.get(str(n), slug(str(n))) for n in impl
        ]
    return manifest


def validate_manifest(
    manifest: dict[str, Any],
    ai_features: dict[str, Any],
    vision: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    """Advisory coverage + reference guardrail (D-DM5).

    Warns on gross drift and lightly repairs dangling references (drops
    `reads`/`writes` that name no declared entity and `depends_on` that name no
    real surface). Never blocks; returns the (possibly repaired) manifest and the
    list of warnings.
    """
    warnings: list[str] = []
    surfaces = [s for s in (manifest.get("surfaces") or []) if isinstance(s, dict)]
    surface_names = {s.get("name") for s in surfaces if s.get("name")}
    entity_names = {
        e.get("name")
        for e in (manifest.get("entities") or [])
        if isinstance(e, dict) and e.get("name")
    }

    # Coverage via catalog_surface links. Each AI surface realizes one catalog
    # surface (a catalog surface may be realized by several UI surfaces). Invert
    # the links to find catalog surfaces realized by nothing, and flag links that
    # are missing or don't resolve (so enrichment can't silently no-op).
    catalog_surfaces = set(_user_facing_ai_surfaces(ai_features or {}))
    linked: set[str] = set()
    for s in surfaces:
        if s.get("kind") != "ai":
            continue
        cs = s.get("catalog_surface")
        if not cs:
            warnings.append(f"AI surface '{s.get('name')}' has no catalog_surface link")
        elif cs not in catalog_surfaces:
            warnings.append(
                f"surface '{s.get('name')}' catalog_surface '{cs}' is not a "
                "catalog AI surface"
            )
        else:
            linked.add(cs)
    for cs in catalog_surfaces - linked:
        warnings.append(f"catalog AI surface '{cs}' is realized by no surface")

    # Coverage (approximate): vision MVP features should be implemented by a
    # surface. Advisory only — not every vision feature is necessarily a distinct
    # user-facing surface.
    vs = _unwrap_vision(vision)
    implemented: set[str] = set()
    for s in surfaces:
        implemented.update(s.get("implements_features") or [])
    for feat in vs.get("key_features_mvp") or []:
        fname = feat.get("name") if isinstance(feat, dict) else feat
        if isinstance(fname, str) and fname and fname not in implemented:
            warnings.append(f"vision feature '{fname}' implemented by no surface")

    # Audience validity.
    audiences = {
        a.get("name") if isinstance(a, dict) else a
        for a in (vs.get("target_audiences") or [])
    }
    audiences.discard(None)
    if audiences:
        for screen in manifest.get("screens") or []:
            if not isinstance(screen, dict):
                continue
            aud = screen.get("audience")
            if aud and aud not in audiences:
                warnings.append(f"screen audience '{aud}' is not a vision audience")

    # Reference integrity — light repair of dangling references.
    for s in surfaces:
        for key in ("reads", "writes"):
            refs = s.get(key) or []
            kept = [r for r in refs if r in entity_names]
            if len(kept) != len(refs):
                warnings.append(
                    f"surface '{s.get('name')}' {key} references unknown entities"
                )
            s[key] = kept
        deps = s.get("depends_on") or []
        kept_deps = [d for d in deps if d in surface_names]
        if len(kept_deps) != len(deps):
            warnings.append(
                f"surface '{s.get('name')}' depends_on references unknown surfaces"
            )
        s["depends_on"] = kept_deps

    return manifest, warnings