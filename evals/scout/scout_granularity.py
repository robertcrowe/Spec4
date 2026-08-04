"""Feature fan-out — the granularity axis of Scout's output (dev tooling).

Pure, unit-tested, no LLM. Measures how many candidates Scout produces PER stated
vision feature — the direct signal for the question "is Scout shattering a
conceptually coherent feature into multiple pieces." This complements the probe's
existing granularity signals: over-generation (breadth, candidates/run) and the
``sub_feature`` share (Scout's own scope tag, a proxy that misses a feature
shattered into several ``feature``-scoped candidates).

A candidate COVERS a real feature when its ``linked_vision_features`` names it
exactly, or via a normalized near-miss (formatting drift that resolves to a real
feature). Phantom links (naming no real feature) cover nothing. A candidate that
covers no real feature is vision-underived — Scout's adjacent / unrequested
over-generation — and is counted separately, not as fan-out.

This module takes ALREADY-RESOLVED coverage (the probe does the exact/near-miss
resolution via the phantom checker and hands the real feature names in), so it
stays free of the vision-shape parsing and the LLM package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Fanout:
    """Fan-out result for one vision, pooled over N runs.

    ``per_feature`` counts covering candidate INSTANCES (across all runs) for each
    stated feature. Rates normalise by ``n_runs`` so they read as "candidates per
    feature per run" and compare across visions run different numbers of times.
    """

    n_features: int
    n_runs: int
    n_candidate_instances: int
    per_feature: dict[str, int]
    unlinked_instances: int  # covered no real feature (adjacent / unrequested)

    @property
    def mean_fanout(self) -> float | None:
        """Avg candidates covering a feature, per run. None if no features/runs."""
        if not self.n_features or not self.n_runs:
            return None
        return sum(self.per_feature.values()) / (self.n_features * self.n_runs)

    @property
    def max_fanout(self) -> tuple[str, float] | None:
        """(feature, per-run count) for the single most-shattered feature."""
        if not self.per_feature or not self.n_runs:
            return None
        feat = max(self.per_feature, key=lambda k: self.per_feature[k])
        return feat, self.per_feature[feat] / self.n_runs

    @property
    def uncovered_features(self) -> list[str]:
        """Stated features no candidate ever covered — coverage gaps."""
        return sorted(f for f, c in self.per_feature.items() if c == 0)

    @property
    def unlinked_share(self) -> float | None:
        """Share of candidate instances covering no stated feature."""
        n = self.n_candidate_instances
        return self.unlinked_instances / n if n else None


def feature_fanout(
    real_feature_names: list[str],
    covered_per_candidate: list[list[str]],
    n_runs: int,
) -> Fanout:
    """Build a Fanout from stated feature names and per-candidate coverage.

    ``covered_per_candidate`` is one entry per candidate INSTANCE (across runs):
    the list of real feature names it covers (exact + near-miss, resolved by the
    caller). A candidate is counted once per distinct feature it covers.
    """
    per_feature: dict[str, int] = {f: 0 for f in real_feature_names}
    unlinked = 0
    for covered in covered_per_candidate:
        real = {f for f in covered if f in per_feature}
        if not real:
            unlinked += 1
            continue
        for f in real:
            per_feature[f] += 1
    return Fanout(
        n_features=len(real_feature_names),
        n_runs=n_runs,
        n_candidate_instances=len(covered_per_candidate),
        per_feature=per_feature,
        unlinked_instances=unlinked,
    )


def _fanout_str(x: float | None) -> str:
    return " —  " if x is None else f"{x:4.1f}"


def format_fanout(fo: Fanout) -> str:
    """Human-readable fan-out block for the probe scorecard."""
    mx = fo.max_fanout
    mx_txt = "—" if mx is None else f"{mx[0]} ({mx[1]:.1f}/run)"
    lines = [
        f"  Feature fan-out:  mean {_fanout_str(fo.mean_fanout)} candidates/"
        f"feature/run  (max: {mx_txt})",
        f"    {fo.n_features} stated features; "
        f"{fo.unlinked_instances} candidate-instances cover no feature "
        f"({_fanout_str((fo.unlinked_share or 0) * 100)}% vision-underived)",
    ]
    uncovered = fo.uncovered_features
    if uncovered:
        lines.append(f"    uncovered features ({len(uncovered)}): "
                     f"{', '.join(uncovered)}")
    return "\n".join(lines)


def fanout_summary_row(fo: Fanout) -> dict[str, Any]:
    """Compact numbers for the overall table."""
    mx = fo.max_fanout
    return {
        "mean_fanout": fo.mean_fanout,
        "max_fanout": mx[1] if mx else None,
        "n_uncovered": len(fo.uncovered_features),
        "unlinked_share": fo.unlinked_share,
    }