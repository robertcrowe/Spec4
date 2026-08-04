"""Design-manifest helpers shared by the Phaser seed projection and the
per-phase attach (D-PH5b).

Leaf module: imports nothing from ``spec4.agents`` so ``project_manager`` can
attach at render time without an import cycle (``agents._utils`` imports
``project_manager``; both import from here — the ``stack_routing`` pattern).

Designer's ``manifest.json`` carries surfaces with two deterministic join keys
(pinned by ``enrich_manifest``): ``implements_feature_ids`` — product-feature
ids — and, on AI surfaces, ``catalog_surface_id`` — the AI catalog-node id.
Surface *names and counts* vary across mock regens; the ids and the three
dispositions are the stable join surface:

1. **Feature surface** — non-empty ``implements`` and a screen: UI for its
   feature's phases.
2. **Scaffolding** — empty ``implements``, no catalog id: not covered by any
   feature's phases; surfaced in the seed for deliberate placement, never
   attached per-phase.
3. **Internal** — feature-attributed but ``screen: null``: implementation
   work for its feature, not UI.

The attach rule mirrors stack routing: a surface reaches a phase when its
``implements_feature_ids`` intersect the phase's declared product features OR
its ``catalog_surface_id`` is among the phase's declared capabilities — each
key against its own array. A surface implementing only an *excluded* feature
attaches nowhere for free: an excluded feature is never declared. Several
surfaces may realize ONE catalog node; grouping by ``catalog_surface_id``
keeps the one-unit-of-work reading.

``screen`` may be a string or a list across draws; ``inputs`` items may be
strings or objects — every helper tolerates both shapes.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "catalog_id",
    "implements_ids",
    "input_names",
    "screens_of",
    "surface_detail_lines",
    "surface_summary_line",
    "surfaces_for_declarations",
]


def _surfaces(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [
        s for s in ((manifest or {}).get("surfaces") or []) if isinstance(s, dict)
    ]


def screens_of(surface: dict[str, Any]) -> list[str]:
    """The surface's screen ids; tolerates string, list, and null shapes."""
    screen = surface.get("screen")
    if isinstance(screen, list):
        return [str(x) for x in screen if x]
    return [str(screen)] if screen else []


def implements_ids(surface: dict[str, Any]) -> list[str]:
    return [str(x) for x in (surface.get("implements_feature_ids") or []) if x]


def catalog_id(surface: dict[str, Any]) -> str:
    return str(surface.get("catalog_surface_id") or "")


def input_names(surface: dict[str, Any]) -> list[str]:
    """Input identifiers; tolerates string items and ``{name: ...}`` objects."""
    out: list[str] = []
    for item in (surface.get("inputs") or []):
        if isinstance(item, dict):
            name = item.get("name")
            if name:
                out.append(str(name))
        elif isinstance(item, str) and item:
            out.append(item)
    return out


def surface_summary_line(surface: dict[str, Any]) -> str:
    """The seed projection's one-line surface summary (D-PH1d line format).

    Leads with the stable join surface: kind, screens (or the internal
    annotation), implements (or the scaffolding annotation), catalog id, the
    entity footprint, and the advisory ordering hint.
    """
    name = surface.get("name") or "surface"
    kind = surface.get("kind") or "unspecified"
    screens = screens_of(surface)
    implements = implements_ids(surface)
    parts = [f"- `{name}` [{kind}]"]
    parts.append(
        f"screens: {', '.join(screens)}"
        if screens
        else "screens: (none — internal, non-UI work for its feature)"
    )
    parts.append(
        f"implements: {', '.join(implements)}"
        if implements
        else "implements: (none — scaffolding, not a feature surface)"
    )
    if catalog_id(surface):
        parts.append(f"catalog: `{catalog_id(surface)}`")
    reads = ", ".join(str(x) for x in (surface.get("reads") or []))
    writes = ", ".join(str(x) for x in (surface.get("writes") or []))
    if reads:
        parts.append(f"reads: {reads}")
    if writes:
        parts.append(f"writes: {writes}")
    depends = ", ".join(str(x) for x in (surface.get("depends_on") or []))
    if depends:
        parts.append(f"after: {depends}")
    return "; ".join(parts)


def surface_detail_lines(surface: dict[str, Any]) -> list[str]:
    """The per-phase detail block for one surface (D-PH5c).

    Fuller than the seed one-liner because the coding agent builds these:
    screens (or the internal annotation), inputs (names only), output,
    states, the entity footprint, and the advisory within-UI ordering hint.
    """
    name = surface.get("name") or "surface"
    kind = surface.get("kind") or "unspecified"
    lines = [f"- **`{name}`** [{kind}]"]
    screens = screens_of(surface)
    lines.append(
        f"  - screens: {', '.join(screens)}"
        if screens
        else "  - screens: none — internal, non-UI implementation work for "
        "its feature"
    )
    names = input_names(surface)
    if names:
        lines.append(f"  - inputs: {', '.join(names)}")
    output = surface.get("output")
    if isinstance(output, str) and output:
        lines.append(f"  - output: {output}")
    elif isinstance(output, dict) and output:
        keys = ", ".join(str(k) for k in output)
        lines.append(f"  - output: {keys}")
    states = ", ".join(str(x) for x in (surface.get("states") or []))
    if states:
        lines.append(f"  - states: {states}")
    reads = ", ".join(str(x) for x in (surface.get("reads") or []))
    writes = ", ".join(str(x) for x in (surface.get("writes") or []))
    if reads:
        lines.append(f"  - reads: {reads}")
    if writes:
        lines.append(f"  - writes: {writes}")
    depends = ", ".join(str(x) for x in (surface.get("depends_on") or []))
    if depends:
        lines.append(f"  - after (advisory UI ordering): {depends}")
    return lines


def surfaces_for_declarations(
    manifest: dict[str, Any] | None,
    feature_ids: set[str],
    capability_ids: set[str],
) -> list[dict[str, Any]]:
    """Manifest surfaces attached to a phase's declarations (D-PH5b).

    Returns records ``{surface, via_features, via_capability}`` in manifest
    order: ``via_features`` is the sorted list of declared product ids the
    surface implements, ``via_capability`` is True when the surface's
    ``catalog_surface_id`` is a declared capability. Disposition-2 surfaces
    (no implements, no catalog id) can never match — they stay seed-only.
    """
    out: list[dict[str, Any]] = []
    for surface in _surfaces(manifest):
        via_features = sorted(set(implements_ids(surface)) & feature_ids)
        via_capability = bool(
            catalog_id(surface) and catalog_id(surface) in capability_ids
        )
        if via_features or via_capability:
            out.append({
                "surface": surface,
                "via_features": via_features,
                "via_capability": via_capability,
            })
    return out