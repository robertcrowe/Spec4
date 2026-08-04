"""Requires-direction inversion leads over the AI catalog (D-RI series).

Dev tooling under ``evals/``. Never wired into the pipeline.

The signal core — matchers, production map, and per-edge classification —
lives in ``src/spec4/agentifier/requires_reconciler.py`` (single source of
truth, D-RC4/D-RC5); this probe imports it and adds draw I/O and reporting.
The reconciler flips SUSPECTED-INVERSION edges at assembly time; this probe
remains the before/after instrument over saved draws and the transfer check
that the ported core is behaviour-identical to the calibrated original.

See the core module's docstring for the full signal doctrine (S1/S1b/S2/S3,
D-RI1–D-RI13) and the reframe: on iterative products data flows both ways
between builders and analyzers; ``requires`` holds one direction and its
consumers need the **build path** — an inversion is an edge encoding the
revision/feedback path instead.

**Blunt lexical lead-generator, not a verdict** — every classification line
carries the signals that fired and the matched names/tokens for one-glance
adjudication.

Classification per edge ``A requires B``, with ``fwd`` = signals(A consumes
B) and ``rev`` = signals(B consumes A): **SUPPORTED** (fwd only),
**SUSPECTED-INVERSION** (rev only), **CONFLICTING** (both; surfaced, never
auto-flip material), **NO-EVIDENCE** (neither; annotations preserved).

Edge universe (D-RI2): feature -> feature edges only; feature -> infra edges
are direction-correct by construction and reported as SKIPPED-INFRA;
unresolvable producer names are reported as UNRESOLVED-ENDPOINT.

Summary reports per-class counts and the inversion rate over evidenced edges
(SUPPORTED + SUSPECTED-INVERSION + CONFLICTING) — the before/after
instrument for the assembly-time reconciliation pass.

Usage::

    python3 requires_inversion.py <draw_dir>

``<draw_dir>`` holds ``ai_features.json``; ``feature_specs.json`` alongside
activates the S2 production map (strictly better than the fallback gate).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _load import (  # noqa: E402  (evals/ is a script dir, not a package)
    catalog_nodes,
    load_draw,
    product_features,
    slug,
)
from spec4.agentifier.requires_reconciler import (  # noqa: E402
    CONFLICTING,
    INFRA_KIND,
    INVERSION,
    NO_EVIDENCE,
    SUPPORTED,
    _stem_prefix_match,  # re-exported for the unit tests
    _tokens,  # re-exported for the unit tests
    classify_edge,
)
from spec4.agentifier.requires_reconciler import (  # noqa: E402
    build_production_map as _core_build_production_map,
)

__all__ = [
    "CONFLICTING",
    "INVERSION",
    "NO_EVIDENCE",
    "SUPPORTED",
    "_stem_prefix_match",
    "_tokens",
    "build_production_map",
    "classify_draw",
]


def build_production_map(draw: dict[str, Any]) -> dict[str, str] | None:
    """Draw-shaped adapter over the core production map.

    Product-feature id -> producing AI node id, or None without specs. See
    ``requires_reconciler.build_production_map`` for the resolution rules
    (unique max, margin, floor — conservative).
    """
    return _core_build_production_map(product_features(draw), catalog_nodes(draw))


def classify_draw(draw: dict[str, Any]) -> dict[str, Any]:
    """Classify every requires edge; returns the full report structure."""
    nodes = catalog_nodes(draw)
    # Mirrors the capability_name_to_id contract (requires holds names, id
    # holds the slug) but maps to whole nodes, which this probe needs.
    name_to_node = {str(n["name"]): n for n in nodes if n.get("name")}
    slug_to_node = {str(n["id"]): n for n in nodes if n.get("id")}
    prod_map = build_production_map(draw)
    vf_link_counts: dict[str, int] = {}
    for n in nodes:
        if n.get("kind") == INFRA_KIND:
            continue
        for vf in n.get("linked_vision_features") or []:
            key = slug(str(vf))
            vf_link_counts[key] = vf_link_counts.get(key, 0) + 1

    edges: list[dict[str, Any]] = []
    skipped_infra = 0
    unresolved: list[tuple[str, str]] = []

    for consumer in nodes:
        cname = str(consumer.get("name") or consumer.get("id") or "")
        if consumer.get("kind") == INFRA_KIND:
            continue
        for req_name in consumer.get("requires") or []:
            req_name = str(req_name)
            producer = name_to_node.get(req_name) or slug_to_node.get(slug(req_name))
            if producer is None:
                unresolved.append((cname, req_name))
                continue
            if producer.get("kind") == INFRA_KIND:
                skipped_infra += 1
                continue
            if producer is consumer:
                continue

            verdict = classify_edge(consumer, producer, prod_map, vf_link_counts)
            edges.append({
                "consumer": cname,
                "producer": str(producer.get("name") or ""),
                "class": verdict["class"],
                "fwd": verdict["fwd"],
                "rev": verdict["rev"],
                "notes": verdict["notes"],
            })

    counts = {c: 0 for c in (SUPPORTED, INVERSION, CONFLICTING, NO_EVIDENCE)}
    for e in edges:
        counts[e["class"]] += 1
    evidenced = counts[SUPPORTED] + counts[INVERSION] + counts[CONFLICTING]
    return {
        "edges": edges,
        "counts": counts,
        "evidenced": evidenced,
        "skipped_infra": skipped_infra,
        "unresolved": unresolved,
        "production_map": prod_map,
    }


def report(draw_dir: str) -> None:
    draw = load_draw(draw_dir)
    nodes = catalog_nodes(draw)
    print(f"=== requires_inversion — {draw_dir} ===")
    if not nodes:
        print("  UNMEASURABLE — empty AI catalog (no-AI draw)")
        return

    res = classify_draw(draw)
    pm = res["production_map"]
    if pm is None:
        print("  (no feature_specs.json — S2 running on fallback selectivity gate)")
    else:
        print(f"  (S2 production map active: {len(pm)} feature(s) resolved)")
        for fid, nid in sorted(pm.items()):
            print(f"      {fid} -> {nid}")

    order = (INVERSION, CONFLICTING, SUPPORTED, NO_EVIDENCE)
    for cls in order:
        group = [e for e in res["edges"] if e["class"] == cls]
        if not group:
            continue
        print(f"\n[{cls}] ({len(group)})")
        for e in group:
            print(f"  '{e['consumer']}' requires '{e['producer']}'")
            for s in e["fwd"]:
                print(f"      fwd  {s}")
            for s in e["rev"]:
                print(f"      rev  {s}")
            for s in e["notes"]:
                print(f"      note {s}")

    if res["unresolved"]:
        print(f"\n[UNRESOLVED-ENDPOINT] ({len(res['unresolved'])})")
        for cname, req in res["unresolved"]:
            print(f"  '{cname}' requires '{req}' — no catalog node")

    c = res["counts"]
    print(f"\nSummary: {len(res['edges'])} feature->feature edges "
          f"({res['skipped_infra']} feature->infra SKIPPED-INFRA, "
          f"{len(res['unresolved'])} unresolved)")
    print(f"  SUPPORTED {c[SUPPORTED]}  SUSPECTED-INVERSION {c[INVERSION]}  "
          f"CONFLICTING {c[CONFLICTING]}  NO-EVIDENCE {c[NO_EVIDENCE]}")
    if res["evidenced"]:
        rate = c[INVERSION] / res["evidenced"] * 100
        print(f"  Inversion rate over evidenced edges: "
              f"{c[INVERSION]}/{res['evidenced']} ({rate:.1f}%)")
    else:
        print("  Inversion rate over evidenced edges: n/a (no evidenced edges)")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    report(sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
