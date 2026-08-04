"""Edge-emission metrics for the Scout graph contract (dev tooling).

Pure, unit-tested, no LLM. Measures how Scout populates the two graph-contract
edges — ``composed_under`` (coordination membership) and ``requires`` (data-flow)
— on RAW output, i.e. before the integrity pass degrades danglers away. This is
the gauge for Piece 2: once the primer is loosened to emit edges it reports the
load-bearing unknown (does Scout tag ``composed_under`` reliably per member) and
the grouped-but-headless vs. scattered split that separates a clean
decompose-and-recompose from renamed shattering.

At Piece 1 (no primer change, no emission) every number here reads zero — the
honest baseline the emission rate climbs from.

Group shapes are classified per run from RAW edges. The one number that leans on
the contract implementation — surviving ``requires`` edges after integrity — is
derived by running the REAL ``_normalize_edges`` over copies, so it can never
drift from scout.py. Everything else (emission, shapes, degrade counts) is
computed directly from the raw edges; a degraded-to-flat instance is exactly a
scattered singleton or a self-edge, so it needs no re-derivation.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from spec4.agentifier.scout import Candidate, _normalize_edges

# A minimal raw view of one candidate: (name, scope, composed_under, requires).
_Raw = tuple[str, str, str, list[str]]


def _raw(c: dict[str, Any]) -> _Raw:
    return (
        str(c.get("name", "")),
        str(c.get("scope", "")),
        str(c.get("composed_under", "") or ""),
        [str(r) for r in (c.get("requires") or [])],
    )


@dataclass
class GroupShapes:
    """Counts of coordinator-group shapes, pooled across runs.

    A group is a distinct ``composed_under`` label within a single run.
    """

    head_present: int = 0  # label is an emitted candidate (head exists)
    headless: int = 0  # >=2 members, no matching candidate (Composer synthesizes)
    scattered: int = 0  # exactly 1 member, no matching candidate (a dangler)
    self_edge: int = 0  # composed_under == the member's own name


@dataclass
class EdgeMetrics:
    """Aggregate edge-emission metrics over N runs of one vision."""

    n_runs: int
    n_instances: int  # candidate instances across all runs
    composed_emitted: int  # instances carrying a non-empty composed_under
    requires_emitted: int  # instances carrying at least one requires target
    requires_edges_emitted: int  # distinct requires targets, summed over instances
    requires_edges_surviving: int  # after the real integrity pass
    shapes: GroupShapes

    @property
    def composed_emission_rate(self) -> float | None:
        return self.composed_emitted / self.n_instances if self.n_instances else None

    @property
    def requires_emission_rate(self) -> float | None:
        return self.requires_emitted / self.n_instances if self.n_instances else None

    @property
    def requires_edges_dropped(self) -> int:
        """Emitted-but-not-surviving requires edges (self / dangling / cyclic)."""
        return self.requires_edges_emitted - self.requires_edges_surviving

    @property
    def grouped_share(self) -> float | None:
        """Share of instances that are members of some composition.

        Read against the fan-out block: high fan-out with a high grouped share
        is decompose-and-recompose (pieces recompose under a coordinator); high
        fan-out with a low grouped share is raw shattering wearing a new name.
        """
        return self.composed_emission_rate


def _classify_run(cands: list[_Raw]) -> tuple[GroupShapes, int, int, int, int]:
    """Return (shapes, n_composed, n_requires, req_emitted, req_surviving)."""
    names = {name for (name, _s, _cu, _r) in cands}

    shapes = GroupShapes()
    label_members: dict[str, list[str]] = defaultdict(list)
    n_composed = 0
    for name, _scope, cu, _req in cands:
        if not cu:
            continue
        n_composed += 1
        if cu == name:
            shapes.self_edge += 1
            continue
        label_members[cu].append(name)
    for label, members in label_members.items():
        if label in names:
            shapes.head_present += 1
        elif len(members) >= 2:
            shapes.headless += 1
        else:
            shapes.scattered += 1

    n_requires = sum(1 for (_n, _s, _cu, req) in cands if req)
    req_emitted = sum(len(dict.fromkeys(req)) for (_n, _s, _cu, req) in cands)

    # Surviving requires: run the real integrity pass over faithful copies.
    copies = [
        Candidate(
            name=name,
            linked_vision_features=[],
            scope=scope,
            rough_description="",
            composed_under=cu,
            requires=list(req),
        )
        for (name, scope, cu, req) in cands
    ]
    _normalize_edges(copies)
    req_surviving = sum(len(c.requires) for c in copies)

    return shapes, n_composed, n_requires, req_emitted, req_surviving


def edge_metrics(runs: list[list[dict[str, Any]]]) -> EdgeMetrics:
    """Build :class:`EdgeMetrics` from raw candidate dicts, pooled over runs.

    Each dict carries at least ``name``; ``composed_under`` and ``requires``
    default to empty, so pre-emission output scores all-zero.
    """
    totals = GroupShapes()
    n_instances = composed_emitted = requires_emitted = 0
    req_emitted = req_surviving = 0
    for run in runs:
        raw = [_raw(c) for c in run]
        n_instances += len(raw)
        shapes, n_composed, n_requires, r_em, r_surv = _classify_run(raw)
        totals.head_present += shapes.head_present
        totals.headless += shapes.headless
        totals.scattered += shapes.scattered
        totals.self_edge += shapes.self_edge
        composed_emitted += n_composed
        requires_emitted += n_requires
        req_emitted += r_em
        req_surviving += r_surv
    return EdgeMetrics(
        n_runs=len(runs),
        n_instances=n_instances,
        composed_emitted=composed_emitted,
        requires_emitted=requires_emitted,
        requires_edges_emitted=req_emitted,
        requires_edges_surviving=req_surviving,
        shapes=totals,
    )


def _pct(x: float | None) -> str:
    return "  — " if x is None else f"{100 * x:.0f}%"


def format_edge_metrics(m: EdgeMetrics) -> str:
    """Human-readable edge block for the probe scorecard."""
    s = m.shapes
    return "\n".join(
        [
            f"  Graph edges:  composed_under {_pct(m.composed_emission_rate)} "
            f"({m.composed_emitted}/{m.n_instances} instances)   "
            f"requires {_pct(m.requires_emission_rate)}",
            f"    groups: {s.head_present} head-present, "
            f"{s.headless} headless (synthesizable), "
            f"{s.scattered} scattered, {s.self_edge} self-edge",
            f"    requires edges: {m.requires_edges_emitted} emitted → "
            f"{m.requires_edges_surviving} surviving "
            f"({m.requires_edges_dropped} dropped by integrity)",
        ]
    )


def edge_summary_row(m: EdgeMetrics) -> dict[str, Any]:
    """Columns for the overall scorecard table."""
    return {
        "cu_emit": m.composed_emission_rate,
        "headless": m.shapes.headless,
        "scattered": m.shapes.scattered,
    }