"""Join-coverage probe over saved full-pipeline draws (dev tooling).

No LLM. Measures how well the vision-grounding join works on a real draw: how
reliably an AI feature's ``linked_vision_features`` (names Scout coined) resolve
to Brainstormer's product-feature specs by the canonical ``slug()`` join. This is
the direct read on the one empirical unknown behind D-AC2 — whether exact
slug-match (option A) is good enough, or whether Scout should link by id
(option C). The unresolved-link rate IS the A→C trigger.

The join here reuses the pipeline's own ``spec4.agentifier.grounding`` helpers,
so the probe can never drift from what Agentifier actually computes. It reports,
per draw:

  * Link cardinality — how many surfaced AI features carry 0 links (legitimate
    cross-cutting), exactly 1 (clean 1:1), or >=2 (coordinator / multi-serve).
  * Resolution — of the unique linked names, how many resolve to a product-feature
    spec vs land unresolved; the unresolved names are listed (the actionable
    signal: a name Scout coined that matches no product feature).
  * Grounded coverage — the fraction of surfaced AI features that end up with at
    least one served product feature, with the ungrounded remainder split into
    *suspected unlinking misses* (zero-link nodes structurally attached to a
    grounded node — the resolution metric's blind spot, since a node that names
    nothing can never be "unmatched") vs *likely cross-cutting* (unattached
    zero-link nodes). This is the signal the Embeddy draw motivated: a clean 0%
    unresolved rate can still hide an AI feature reaching the Spec Drafter
    ungrounded because Scout never linked it.
  * Product-feature utilisation — the reverse view: how many of the vision's
    product features are served by >=1 AI feature vs orphaned.
  * Carry consistency — a cross-check that each node's persisted
    ``vision_grounding`` matches an independent recomputation (a mismatch flags a
    stale draw or a pipeline bug, never expected on a fresh draw).

A draw with no ``feature_specs.json`` (or an empty one) exercises only the
safety-net path: grounding is inert and the resolution read is meaningless. The
probe says so and skips the rates rather than reporting a misleading 0%.

Run from ``evals/scout/`` so sibling modules import:

    python join_coverage.py <draw_dir> [<draw_dir> ...]

where each dir holds ``vision.json`` + ``ai_features.json`` + ``feature_specs.json``.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fanout_baseline import (  # noqa: E402 (evals/ is a script dir, not a package)
    surfaced_candidates,
    vision_feature_names,
)

from spec4.agentifier.grounding import build_grounding, spec_by_id
from spec4.agents._utils import slug


@dataclass
class Coverage:
    """Per-draw join-coverage tallies."""

    n_nodes: int = 0
    card0: int = 0  # nodes with no links (cross-cutting / unlinked)
    card1: int = 0  # nodes with exactly one link (clean 1:1)
    card_many: int = 0  # nodes with >=2 links (coordinator / multi-serve)
    raw_links: int = 0  # total links incl. duplicates
    resolved: int = 0  # unique linked names that matched a product-feature spec
    unresolved: int = 0  # unique linked names with no matching spec
    grounded_nodes: int = 0  # nodes with >=1 served feature
    ungrounded_nodes: int = 0  # nodes with 0 served features
    unresolved_names: Counter = field(default_factory=Counter)  # name -> occurrences
    pf_total: int = 0  # product features that have a spec
    pf_served: int = 0  # product features served by >=1 AI feature
    orphaned_pf: list[str] = field(default_factory=list)  # product-feature ids served by none
    consistency_mismatch: list[tuple[str, int, int]] = field(default_factory=list)
    kf_count: int = 0  # key_features_mvp count (Brainstormer-side cross-check)
    # Zero-link nodes split by whether they look like an unlinking miss. A
    # zero-link node passes the resolution metric silently (it names nothing, so
    # nothing can be unmatched), yet may be an AI feature Scout should have
    # linked — the blind spot the Embeddy draw exposed. suspected_miss records
    # (node, reason) for a zero-link node structurally attached to a grounded
    # node; likely_cross_cutting records the rest (plausibly genuine).
    suspected_miss: list[tuple[str, str]] = field(default_factory=list)
    likely_cross_cutting: list[str] = field(default_factory=list)

    @property
    def unique_links(self) -> int:
        return self.resolved + self.unresolved

    @property
    def resolution_rate(self) -> float | None:
        return self.resolved / self.unique_links if self.unique_links else None

    @property
    def unresolved_rate(self) -> float | None:
        return self.unresolved / self.unique_links if self.unique_links else None

    @property
    def grounded_rate(self) -> float | None:
        return self.grounded_nodes / self.n_nodes if self.n_nodes else None

    @property
    def pf_utilisation(self) -> float | None:
        return self.pf_served / self.pf_total if self.pf_total else None

    @property
    def suspected_miss_rate(self) -> float | None:
        """Suspected unlinking misses as a fraction of surfaced AI features."""
        return len(self.suspected_miss) / self.n_nodes if self.n_nodes else None

    @property
    def inert(self) -> bool:
        """True when there is no product-feature spec set to join against."""
        return self.pf_total == 0


def _miss_reasons(
    name: str,
    node: dict[str, Any],
    by_name: dict[str, dict[str, Any]],
    is_grounded: Any,
) -> list[str]:
    """Why a zero-link node looks like an unlinking miss, or [] if it doesn't.

    A zero-link node is suspect when it is structurally attached to a GROUNDED
    node — the same evidence that flagged Embeddy's ``item_summary_generation``
    (a scope=sub_feature twin of a grounded sibling, requiring a grounded node).
    Attachment to a grounded node means Scout surfaced a capability that plainly
    belongs to a served product feature yet carries no link. An unattached
    zero-link node (no such edges) is left as plausibly genuine cross-cutting.
    """
    reasons: list[str] = []
    if node.get("scope") == "sub_feature":
        reasons.append("scope=sub_feature")
    grounded_reqs = [r for r in (node.get("requires") or []) if is_grounded(r)]
    if grounded_reqs:
        reasons.append(f"requires grounded {grounded_reqs}")
    cu = node.get("composed_under") or ""
    if cu and is_grounded(cu):
        reasons.append(f"composed under grounded '{cu}'")
    consumers = [
        m
        for m, other in by_name.items()
        if name in (other.get("requires") or []) and is_grounded(m)
    ]
    if consumers:
        reasons.append(f"required by grounded {consumers}")
    return reasons


def coverage_for_draw(
    vision: dict[str, Any],
    feature_specs: dict[str, Any] | None,
    features: list[dict[str, Any]],
) -> Coverage:
    """Compute join coverage for one draw.

    ``features`` is the raw ``ai_features`` node list; injected infrastructure is
    excluded (only Scout-surfaced AI features carry links). The join reuses the
    pipeline's ``build_grounding`` so counts mirror what Agentifier persisted.
    Every node is grounded once up front so the suspected-miss detector can ask
    whether a zero-link node depends on a GROUNDED node.
    """
    fs = feature_specs or {}
    index = spec_by_id(fs)
    nodes = surfaced_candidates(features)
    by_name = {str(n.get("name", "")): n for n in nodes}

    grounding_of: dict[str, dict[str, Any]] = {
        name: build_grounding(fs, list(node.get("linked_vision_features") or []))
        for name, node in by_name.items()
    }

    def _is_grounded(name: str) -> bool:
        return bool((grounding_of.get(name) or {}).get("served_features"))

    cov = Coverage(
        n_nodes=len(nodes),
        pf_total=len(index),
        kf_count=len(vision_feature_names(vision)),
    )
    served_pf_ids: set[str] = set()

    for node in nodes:
        name = str(node.get("name", ""))
        links = list(node.get("linked_vision_features") or [])
        cov.raw_links += len(links)
        if not links:
            cov.card0 += 1
        elif len(links) == 1:
            cov.card1 += 1
        else:
            cov.card_many += 1

        grounding = grounding_of.get(name) or build_grounding(fs, links)
        served = grounding.get("served_features") or []
        unresolved = grounding.get("unresolved_links") or []
        cov.resolved += len(served)
        cov.unresolved += len(unresolved)
        for uname in unresolved:
            cov.unresolved_names[uname] += 1
        if served:
            cov.grounded_nodes += 1
        else:
            cov.ungrounded_nodes += 1
        for spec in served:
            sid = str(spec.get("id") or "").strip() or slug(str(spec.get("name") or ""))
            if sid:
                served_pf_ids.add(sid)

        # Carry consistency: the persisted vision_grounding on the node should
        # match this independent recomputation (served-count is the cheap gauge).
        carried = node.get("vision_grounding") or {}
        carried_served = len(carried.get("served_features") or [])
        if carried_served != len(served):
            cov.consistency_mismatch.append((name, carried_served, len(served)))

        # Suspected-miss detection targets the ZERO-LINK blind spot only. A node
        # with links-but-all-unresolved is already visible via unresolved_names
        # (the named-but-unmatched, D-AC2 path); this catches the invisible case
        # of a node that names nothing at all yet looks structurally linked.
        if not links:
            reasons = _miss_reasons(name, node, by_name, _is_grounded)
            if reasons:
                cov.suspected_miss.append((name, "; ".join(reasons)))
            else:
                cov.likely_cross_cutting.append(name)

    cov.pf_served = len(served_pf_ids & set(index))
    cov.orphaned_pf = sorted(pid for pid in index if pid not in served_pf_ids)
    return cov


def _pct(value: float | None) -> str:
    return "  n/a" if value is None else f"{value * 100:5.1f}%"


def _draw_report(label: str, cov: Coverage) -> str:
    lines = [f"  {label}"]
    if cov.inert:
        lines.append(
            "    no feature_specs.json product features — grounding INERT "
            "(safety-net path only). Run a full-pipeline draw with real "
            "feature_specs to measure the join."
        )
        lines.append(f"    surfaced AI features: {cov.n_nodes}")
        return "\n".join(lines)

    lines.append(
        f"    surfaced AI features: {cov.n_nodes}  "
        f"(links: {cov.card0} none / {cov.card1} single / {cov.card_many} multi)"
    )
    lines.append(
        f"    link resolution:  {cov.resolved}/{cov.unique_links} resolved  "
        f"({_pct(cov.resolution_rate)})   unresolved: {cov.unresolved} "
        f"({_pct(cov.unresolved_rate)})"
    )
    lines.append(
        f"    grounded coverage: {cov.grounded_nodes}/{cov.n_nodes} AI features "
        f"grounded ({_pct(cov.grounded_rate)})"
    )
    if cov.ungrounded_nodes:
        lines.append(
            f"      ungrounded: {cov.ungrounded_nodes}  "
            f"({len(cov.suspected_miss)} suspected miss, "
            f"{len(cov.likely_cross_cutting)} likely cross-cutting)"
        )
    for node_name, reason in cov.suspected_miss:
        lines.append(f"      !! suspected unlinking miss: {node_name} — {reason}")
    lines.append(
        f"    product-feature use: {cov.pf_served}/{cov.pf_total} served "
        f"({_pct(cov.pf_utilisation)})"
    )
    if cov.kf_count and cov.kf_count != cov.pf_total:
        lines.append(
            f"    note: key_features_mvp count ({cov.kf_count}) != feature_specs "
            f"count ({cov.pf_total}) — Brainstormer-side spec gap"
        )
    if cov.unresolved_names:
        top = ", ".join(
            f"{name!r}x{n}" if n > 1 else repr(name)
            for name, n in cov.unresolved_names.most_common(8)
        )
        lines.append(f"    unresolved names: {top}")
    if cov.orphaned_pf:
        shown = ", ".join(cov.orphaned_pf[:8])
        more = "" if len(cov.orphaned_pf) <= 8 else f" (+{len(cov.orphaned_pf) - 8})"
        lines.append(f"    orphaned product features (no AI surface): {shown}{more}")
    if cov.consistency_mismatch:
        lines.append(
            f"    !! carry mismatch on {len(cov.consistency_mismatch)} node(s) "
            "(persisted vision_grounding != recomputed): "
            + ", ".join(
                f"{name}(carried {c}/recomputed {r})"
                for name, c, r in cov.consistency_mismatch[:6]
            )
        )
    return "\n".join(lines)


def _load(path: Path) -> Any:
    return json.loads(path.read_text())


def _find_draw(directory: Path) -> tuple[Path, Path, Path | None] | None:
    vision = directory / "vision.json"
    features = directory / "ai_features.json"
    if not (vision.exists() and features.exists()):
        return None
    specs = directory / "feature_specs.json"
    return vision, features, (specs if specs.exists() else None)


def coverage_from_dir(directory: Path) -> Coverage | None:
    found = _find_draw(directory)
    if found is None:
        return None
    vision_p, features_p, specs_p = found
    vision = _load(vision_p)
    ai_features = _load(features_p)
    features = ai_features.get("ai_features") or []
    feature_specs = _load(specs_p) if specs_p is not None else None
    return coverage_for_draw(vision, feature_specs, features)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Join-coverage probe over saved full-pipeline draws "
        "(each dir must hold vision.json + ai_features.json + feature_specs.json)."
    )
    parser.add_argument(
        "draw_dirs",
        nargs="+",
        help="One or more draw directories; the dir name is used as the label.",
    )
    args = parser.parse_args(argv)

    print("Vision-grounding join coverage (linked_vision_features -> product-feature specs)\n")
    rows: list[tuple[str, Coverage]] = []
    for d in args.draw_dirs:
        directory = Path(d)
        found = _find_draw(directory)
        if found is None:
            print(f"  {directory.name}: missing vision.json or ai_features.json — skipped\n")
            continue
        if found[2] is None:
            print(
                f"  {directory.name}: no feature_specs.json in draw dir — "
                "grounding inert; skipped\n"
            )
            continue
        cov = coverage_from_dir(directory)
        assert cov is not None
        rows.append((directory.name, cov))
        print(_draw_report(directory.name, cov))
        print()

    live = [(label, c) for label, c in rows if not c.inert]
    if live:
        print("  Summary")
        header = f"    {'draw':<16}{'resolved':>10}{'unresolved':>12}{'grounded':>10}{'susp.miss':>11}"
        print(header)
        for label, c in live:
            print(
                f"    {label:<16}{_pct(c.resolution_rate):>10}"
                f"{_pct(c.unresolved_rate):>12}{_pct(c.grounded_rate):>10}"
                f"{_pct(c.suspected_miss_rate):>11}"
            )
        tot_u = sum(c.unresolved for _, c in live)
        tot_l = sum(c.unique_links for _, c in live)
        tot_miss = sum(len(c.suspected_miss) for _, c in live)
        tot_nodes = sum(c.n_nodes for _, c in live)
        if tot_l:
            print(
                f"\n    aggregate unresolved rate:     {tot_u}/{tot_l} "
                f"({tot_u / tot_l * 100:.1f}%) — the D-AC2 A->C trigger (named-but-unmatched)"
            )
        if tot_nodes:
            print(
                f"    aggregate suspected-miss rate: {tot_miss}/{tot_nodes} "
                f"({tot_miss / tot_nodes * 100:.1f}%) — Scout under-linking (zero-link blind spot)"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())