"""Designer manifest-signal probe — baseline metrics for the Designer round.

Given a draw directory holding ``vision.json``, ``ai_features.json``,
``feature_specs.json`` and ``design/manifest.json`` (or ``manifest.json``),
reports the signals the Designer redesign targets:

  1. Entity grounding (DR3): feature_specs entity union vs manifest entities,
     matched camel-aware so ``PitchDeck`` and ``Pitch Deck`` count as one.
  2. Feature-id join readiness (DR4): are ``implements_features`` names or ids,
     and do the pinned ``implements_feature_ids`` resolve to vision ids?
  3. Catalog-surface join (DR4): do AI surfaces' ``catalog_surface`` links (and
     pinned ``catalog_surface_id``) resolve to catalog nodes?
  4. Coverage: user-facing catalog surfaces realized / orphaned, plus the count
     of ``cross_feature`` nodes still invisible to Designer (the D-DR7 band).

Read-only. Never wired into the pipeline. Run from ``evals/designer/``:

    python3 manifest_signal_probe.py <draw_dir>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _slug(name: str) -> str:
    """Canonical id derivation — mirrors spec4.agents._utils.slug."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower()) if name else ""


def _norm_entity(name: str) -> str:
    """Camel/space/underscore-insensitive key for entity matching.

    ``PitchDeck``, ``Pitch Deck`` and ``pitch_deck`` all collapse to the same
    key, so the grounding overlap is not understated by casing conventions.
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(name))
    return re.sub(r"[^a-z0-9]+", "", spaced.lower())


def _words(name: str) -> set[str]:
    """Content words (>= 4 chars) of a name, camel/space/underscore-split.

    Used for field grounding: ``Visual Design`` shares ``visual`` with a
    ``visual_guidance`` field, so the concept counts as grounded-as-field even
    though neither name matches whole.
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(name))
    return {w for w in re.split(r"[^a-z0-9]+", spaced.lower()) if len(w) >= 4}


# Field-name shapes that tend to carry a domain concept as an enumerated *value*
# the manifest schema (field names only) never spells out — e.g. a
# ``specialist_domain`` field whose values are the specialist domains. Purely
# advisory: flagged for inspection, never counted as grounding.
_DISCRIMINATOR = re.compile(r"(_domain|_type|_kind|_category|_role|_source)$|specialist", re.I)


def _load(d: Path, *names: str) -> dict:
    for name in names:
        p = d / name
        if p.exists():
            return json.loads(p.read_text())
    return {}


def _vision_name_to_id(vision: dict) -> dict[str, str]:
    vs = vision.get("vision_statement", vision)
    inner = vs.get("vision") if isinstance(vs, dict) else None
    kf = (inner or {}).get("key_features_mvp") if isinstance(inner, dict) else None
    if kf is None and isinstance(vs, dict):
        kf = vs.get("key_features_mvp")
    out: dict[str, str] = {}
    for item in kf or []:
        if not isinstance(item, dict):
            continue
        if "name" in item:
            out[str(item["name"])] = str(item.get("id") or _slug(str(item["name"])))
        else:
            for k, v in item.items():
                fid = v.get("id") if isinstance(v, dict) else None
                out[str(k)] = str(fid or _slug(str(k)))
    return out


def _spec_entities(fs: dict) -> list[str]:
    seen, out = set(), []
    for f in fs.get("features") or []:
        for e in f.get("entities") or []:
            if e not in seen:
                seen.add(e)
                out.append(e)
    return out


def main(draw: str) -> None:
    d = Path(draw)
    vision = _load(d, "vision.json")
    ai = _load(d, "ai_features.json")
    fs = _load(d, "feature_specs.json")
    manifest = _load(d, "design/manifest.json", "manifest.json")

    name_to_id = _vision_name_to_id(vision)
    vision_ids = set(name_to_id.values())
    nodes = ai.get("ai_features") or []
    by_name = {n["name"]: n for n in nodes if n.get("name")}

    def _infra(n: dict) -> bool:
        return n.get("tier") == "infrastructure" or n.get("kind") == "infrastructure"

    uf = {n["name"] for n in nodes if n.get("scope") == "feature" and not _infra(n)}
    cross = sorted(
        n["name"] for n in nodes if n.get("scope") == "cross_feature" and not _infra(n)
    )
    surfaces = [s for s in (manifest.get("surfaces") or []) if isinstance(s, dict)]
    ai_surfaces = [s for s in surfaces if s.get("kind") == "ai"]

    print("=" * 72)
    print(f"MANIFEST SIGNAL PROBE — {d.name}")
    print("=" * 72)

    # 1. Entity grounding (DR3) — graded disposition, not a binary name match.
    #    A domain concept is legitimately grounded when it surfaces as an entity,
    #    a field, or a reference elsewhere in the manifest. Soft grounding (DR3)
    #    expects the specialist domains to nest as fields/content rather than
    #    become top-level entities, so entity-name overlap alone systematically
    #    undercounts. Discriminator fields are surfaced separately, since they can
    #    carry a concept as an enumerated value the field-name view can't see.
    spec_ent = _spec_entities(fs)
    entities = [e for e in (manifest.get("entities") or []) if isinstance(e, dict)]
    man_ent = [e.get("name") for e in entities if e.get("name")]
    entity_norms = {_norm_entity(n) for n in man_ent}
    field_words: list[set[str]] = []
    field_refs: list[str] = []
    for e in entities:
        for f in e.get("fields") or []:
            field_words.append(_words(f))
            field_refs.append(f"{e.get('name')}.{f}")
    blob = re.sub(r"[^a-z0-9]+", "", json.dumps(manifest).lower())

    def _disposition(concept: str) -> str:
        norm = _norm_entity(concept)
        words = _words(concept)
        if norm in entity_norms:
            return "entity"
        if words and any(words & fw for fw in field_words):
            return "field"
        if norm and norm in blob:
            return "referenced"
        return "absent"

    graded = [(c, _disposition(c)) for c in spec_ent]
    grounded = [c for c, d in graded if d != "absent"]
    absent = [c for c, d in graded if d == "absent"]
    disc = [r for r, w in zip(field_refs, field_words) if _DISCRIMINATOR.search(r)]

    print("\n[1] ENTITY GROUNDING (DR3) — graded disposition")
    print(f"  feature_specs concepts ({len(spec_ent)}): {spec_ent}")
    print(f"  manifest entities ({len(man_ent)}): {man_ent}")
    for concept, disp in graded:
        print(f"    {concept:24} -> {disp}")
    print(f"  grounded (entity|field|referenced): {len(grounded)}/{len(spec_ent)}")
    if absent:
        print(f"  ABSENT (no entity / field / reference): {absent}")
    if disc:
        print(f"  discriminator fields (may carry concepts as values — inspect): {disc}")

    # 2. Feature-id join (DR4).
    print("\n[2] FEATURE-ID JOIN (DR4)")
    print(f"  vision name->id: {name_to_id}")
    for s in surfaces:
        impl = s.get("implements_features") or []
        ids = s.get("implements_feature_ids")
        pin = "PINNED" if ids is not None else "absent"
        resolved = all(i in vision_ids for i in (ids or []))
        flag = "" if (ids is None or resolved) else "  <-- UNRESOLVED"
        print(f"  {s.get('name'):38} impl={impl} ids={ids} [{pin}]{flag}")

    # 3. Catalog-surface join (DR4 AI side).
    print("\n[3] CATALOG-SURFACE JOIN (DR4 AI side)")
    for s in ai_surfaces:
        cs = s.get("catalog_surface")
        csid = s.get("catalog_surface_id")
        node = by_name.get(cs)
        status = f"node id={node['id']!r}" if node else "UNRESOLVED"
        print(f"  {s.get('name'):36} catalog_surface={cs!r:38} "
              f"catalog_surface_id={csid!r} ({status})")

    # 4. Coverage.
    linked = {s.get("catalog_surface") for s in ai_surfaces} & uf
    print("\n[4] COVERAGE")
    print(f"  user-facing catalog AI surfaces ({len(uf)}): {sorted(uf)}")
    print(f"  realized: {sorted(linked)}")
    print(f"  ORPHANED: {sorted(uf - linked)}")
    print(f"  cross_feature invisible to Designer ({len(cross)}) [D-DR7 band]: {cross}")

    # 5. Over-attribution (join discipline). A surface that claims a feature it
    #    doesn't actually work with corrupts the downstream id-join. Two tells:
    #    (a) multi-feature attribution, and (b) the stronger one — a surface
    #    claims a feature whose spec entities its own reads/writes never touch,
    #    i.e. it was stapled to a feature it has no data relationship with. The
    #    correct authoring for a support/beyond-MVP surface is an empty
    #    implements list (as Haggler's config surfaces show), so empty is clean,
    #    not suspect. Entity overlap needs reads/writes; surfaces without them are
    #    reported as unknown rather than flagged.
    feat_entities = {
        f.get("id"): {_norm_entity(e) for e in (f.get("entities") or [])}
        for f in (fs.get("features") or [])
        if isinstance(f, dict) and f.get("id")
    }
    print("\n[5] OVER-ATTRIBUTION (join discipline)")
    suspects = 0
    for s in surfaces:
        ids = s.get("implements_feature_ids") or []
        if not ids:
            continue  # empty is the correct authoring for support surfaces
        touched = {
            _norm_entity(e)
            for e in (s.get("reads") or []) + (s.get("writes") or [])
        }
        multi = len(ids) >= 2
        no_overlap = []
        for fid in ids:
            ents = feat_entities.get(fid)
            if ents is None:
                continue
            if touched and not (touched & ents):
                no_overlap.append(fid)
        if multi or no_overlap:
            suspects += 1
            reasons = []
            if multi:
                reasons.append(f"multi-feature({len(ids)})")
            if no_overlap:
                reasons.append(f"no-entity-overlap={no_overlap}")
            if not touched:
                reasons.append("no reads/writes to judge overlap")
            print(f"  {s.get('name'):38} claims={ids} reads/writes={sorted(touched)} "
                  f"-> {', '.join(reasons)}")
    if suspects == 0:
        print("  none — every non-empty attribution touches its feature's entities")
    else:
        print(f"  {suspects} suspect surface(s) — inspect for stapled attribution")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")