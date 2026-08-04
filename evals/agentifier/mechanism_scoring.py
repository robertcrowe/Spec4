"""Deterministic scorer for the mechanism probe (no LLM calls).

Joins a produced ``ai_features.json`` against the ``expectations.json`` beside
a probe vision (see ``evals/agentifier/probe_visions/README.md`` for the
contract) and computes the probe's metrics:

- **Coverage** — expectation features with at least one linked entry. A miss
  here is a Scout/Linker failure, not a mechanism failure, so uncovered
  features are excluded from the mechanism denominators and reported apart.
  Features marked ``coverage_optional`` (deterministic fillers Scout is RIGHT
  to decline to surface as AI opportunities) are excluded from the coverage
  denominator too; when Scout does surface them, all checks apply as usual.
- **Required-mechanism recall** — each ``mechanisms_required`` item must appear
  in the spec ``mechanisms`` of at least one linked entry.
- **Forbidden-mechanism violations** — a ``mechanisms_forbidden`` item on any
  linked entry (the over-engineering traps). Entries linked to SEVERAL
  expectation features (Composer coordinators) violate only when every linked
  feature forbids the mechanism: a mechanism legitimately carried for one
  member must not indict a sibling.
- **Target spam** — the vision's target mechanism on any entry not linked to a
  feature in ``target_mechanism_valid_on``.
- **Tier calibration** — the highest-ordinal linked ``kind: "feature"``
  entry's tier against ``expected_tiers``, plus a signed ladder distance
  (positive = inflation). Only the maximum matters: ``expected_tiers`` states
  how complex the vision feature should get OVERALL, and Scout freely
  decomposes a feature into legitimately cheaper sub-stages — scoring every
  child against the parent's expectation reads correct decomposition as
  deflation, and scores multi-feature coordinators against expectations they
  never had. When the checked entry links to several expectation features, it
  is judged against the UNION of their expected tiers — a coordinator
  spanning a chained_calls feature and a single_call feature is fine at
  either, and still reads as inflation above both. (Infrastructure nodes are
  registry-injected, so exempt.)
- **Vision-wide checks** — ``mechanisms_forbidden_everywhere`` and
  ``max_total_mechanism_instances`` (the all-negative control vision).

``also_check`` items are surfaced verbatim for manual/judge review — they
assert on free-shaped spec fields the scorer cannot judge mechanically.

Join rule: an entry belongs to a vision feature when ``slug(vision_feature)``
is in ``{slug(x) for x in entry.linked_vision_features}`` — names are
non-deterministic, edges are not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from spec4.agents._utils import _TIER_ORDER_FOR_SUMMARY, slug

__all__ = [
    "FeatureScore",
    "VisionScore",
    "score_vision",
    "aggregate",
    "format_vision_score",
    "format_overall",
]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class FeatureScore:
    """Scoring outcome for one expectation feature."""

    vision_feature: str
    covered: bool
    coverage_optional: bool = False
    required_hit: list[str] = field(default_factory=list)
    required_miss: list[str] = field(default_factory=list)
    # (mechanism, entry_name) pairs
    forbidden_violations: list[tuple[str, str]] = field(default_factory=list)
    # (entry_name, tier, signed_delta) — at most one element: the
    # highest-ordinal linked kind=="feature" entry, checked against
    # expected_tiers. Delta 0 means its tier is inside the set.
    tier_checks: list[tuple[str, str, int]] = field(default_factory=list)
    also_check: str = ""

    @property
    def tier_ok(self) -> bool:
        return all(d == 0 for _, _, d in self.tier_checks)


@dataclass
class VisionScore:
    """Scoring outcome for one probe vision against one ai_features doc."""

    project: str
    target_mechanism: str | None
    features: list[FeatureScore]
    # (mechanism, entry_name): target mechanism outside target_mechanism_valid_on
    spam: list[tuple[str, str]]
    # (mechanism, entry_name): vision_wide mechanisms_forbidden_everywhere hits
    wide_violations: list[tuple[str, str]]
    total_mechanism_instances: int
    max_total_mechanism_instances: int | None

    @property
    def covered(self) -> list[FeatureScore]:
        return [f for f in self.features if f.covered]

    @property
    def uncovered(self) -> list[FeatureScore]:
        return [f for f in self.features if not f.covered]

    @property
    def required_total(self) -> int:
        return sum(len(f.required_hit) + len(f.required_miss) for f in self.covered)

    @property
    def required_hits(self) -> int:
        return sum(len(f.required_hit) for f in self.covered)

    @property
    def forbidden_count(self) -> int:
        return sum(len(f.forbidden_violations) for f in self.covered)

    @property
    def tier_checked(self) -> int:
        return sum(len(f.tier_checks) for f in self.covered)

    @property
    def tier_in_set(self) -> int:
        return sum(
            1 for f in self.covered for _, _, d in f.tier_checks if d == 0
        )

    @property
    def tier_deltas(self) -> list[int]:
        return [d for f in self.covered for _, _, d in f.tier_checks]

    @property
    def over_budget(self) -> bool:
        cap = self.max_total_mechanism_instances
        return cap is not None and self.total_mechanism_instances > cap


# ---------------------------------------------------------------------------
# Join and extraction helpers
# ---------------------------------------------------------------------------


def _entry_mechanism_names(entry: dict[str, Any]) -> list[str]:
    """Mechanism names on one entry's spec, shape-guarded."""
    raw = entry.get("mechanisms")
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
        elif isinstance(item, str):
            names.append(item)
    return names


def _entry_links(entry: dict[str, Any]) -> set[str]:
    raw = entry.get("linked_vision_features")
    if not isinstance(raw, list):
        return set()
    return {slug(str(x)) for x in raw if x}


def _entries_for(feature_key: str, entries: list[dict[str, Any]]) -> list[dict]:
    key = slug(feature_key)
    return [e for e in entries if key in _entry_links(e)]


def _tier_delta(tier: str, expected: list[str]) -> int:
    """Signed ladder distance to the nearest expected tier; 0 when in the set.

    Positive = above (inflation), negative = below. Covers the gap case too:
    a tier strictly between two expected tiers scores its distance to the
    nearer one, never 0. Unknown tier names get ordinal 0 (reads as maximal
    deflation).
    """
    if not expected or tier in expected:
        return 0
    got = _TIER_ORDER_FOR_SUMMARY.get(tier, 0)
    diffs = [got - _TIER_ORDER_FOR_SUMMARY.get(t, 0) for t in expected]
    return min(diffs, key=abs)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_vision(
    expectations: dict[str, Any], ai_features: dict[str, Any]
) -> VisionScore:
    """Score one ai_features document against one expectations document."""
    entries: list[dict[str, Any]] = [
        e for e in (ai_features.get("ai_features") or []) if isinstance(e, dict)
    ]
    target: str | None = expectations.get("target_mechanism")
    valid_on = {slug(str(f)) for f in expectations.get("target_mechanism_valid_on") or []}

    # Per-feature ground truth, keyed by slug — used to judge entries that
    # link to SEVERAL expectation features (Composer coordinators), which
    # carry no single feature's ground truth of their own.
    forbidden_by_slug: dict[str, set[str]] = {}
    tiers_by_slug: dict[str, list[str]] = {}
    for exp in expectations.get("expectations") or []:
        s = slug(str(exp.get("vision_feature", "")))
        forbidden_by_slug[s] = set(exp.get("mechanisms_forbidden") or [])
        tiers_by_slug[s] = [str(t) for t in exp.get("expected_tiers") or []]

    features: list[FeatureScore] = []
    for exp in expectations.get("expectations") or []:
        key = str(exp.get("vision_feature", ""))
        linked = _entries_for(key, entries)
        fs = FeatureScore(
            vision_feature=key,
            covered=bool(linked),
            coverage_optional=bool(exp.get("coverage_optional", False)),
            also_check=str(exp.get("also_check", "")),
        )
        all_mechs = {m for e in linked for m in _entry_mechanism_names(e)}
        for m in exp.get("mechanisms_required") or []:
            (fs.required_hit if m in all_mechs else fs.required_miss).append(m)
        for m in exp.get("mechanisms_forbidden") or []:
            for e in linked:
                if m not in _entry_mechanism_names(e):
                    continue
                known_links = _entry_links(e) & set(forbidden_by_slug)
                if len(known_links) > 1 and not all(
                    m in forbidden_by_slug[s] for s in known_links
                ):
                    # A coordinator carrying the mechanism for a sibling
                    # feature that permits it — not this feature's violation.
                    continue
                fs.forbidden_violations.append((m, e.get("name", "?")))
        expected_tiers = [str(t) for t in exp.get("expected_tiers") or []]
        if expected_tiers:
            # Only the highest-ordinal linked entry is checked: the feature's
            # overall complexity. Children of a decomposition and coordinators
            # spanning several vision features carry no per-feature ground
            # truth of their own (see module docstring).
            feature_entries = [
                e for e in linked if e.get("kind", "feature") == "feature"
            ]
            if feature_entries:
                top = max(
                    feature_entries,
                    key=lambda e: _TIER_ORDER_FOR_SUMMARY.get(
                        str(e.get("tier", "")), 0
                    ),
                )
                tier = str(top.get("tier", ""))
                allowed = expected_tiers
                top_links = _entry_links(top) & set(tiers_by_slug)
                if len(top_links) > 1:
                    union = sorted(
                        {t for s in top_links for t in tiers_by_slug[s]},
                        key=lambda t: _TIER_ORDER_FOR_SUMMARY.get(t, 0),
                    )
                    allowed = union or expected_tiers
                fs.tier_checks.append(
                    (top.get("name", "?"), tier, _tier_delta(tier, allowed))
                )
        features.append(fs)

    spam: list[tuple[str, str]] = []
    if target:
        for e in entries:
            if target in _entry_mechanism_names(e) and not (
                _entry_links(e) & valid_on
            ):
                spam.append((target, e.get("name", "?")))

    wide = expectations.get("vision_wide") or {}
    forbidden_everywhere = set(wide.get("mechanisms_forbidden_everywhere") or [])
    wide_violations: list[tuple[str, str]] = []
    if forbidden_everywhere:
        for e in entries:
            for m in _entry_mechanism_names(e):
                if m in forbidden_everywhere:
                    wide_violations.append((m, e.get("name", "?")))

    return VisionScore(
        project=str(expectations.get("project", "")),
        target_mechanism=target,
        features=features,
        spam=spam,
        wide_violations=wide_violations,
        total_mechanism_instances=sum(
            len(_entry_mechanism_names(e)) for e in entries
        ),
        max_total_mechanism_instances=wide.get("max_total_mechanism_instances"),
    )


def aggregate(scores: list[VisionScore]) -> dict[str, Any]:
    """Headline metrics over many scored runs (controls counted separately)."""
    probes = [s for s in scores if s.target_mechanism]
    controls = [s for s in scores if not s.target_mechanism]
    req_total = sum(s.required_total for s in probes)
    req_hits = sum(s.required_hits for s in probes)
    tier_checked = sum(s.tier_checked for s in scores)
    tier_in_set = sum(s.tier_in_set for s in scores)
    deltas = [d for s in scores for d in s.tier_deltas]
    # Coverage counts only features Scout is expected to surface; a declined
    # coverage_optional feature is correct behavior, not a miss.
    expected = [
        f for s in scores for f in s.features if not f.coverage_optional
    ]
    n_feat = len(expected)
    n_cov = sum(1 for f in expected if f.covered)
    return {
        "runs": len(scores),
        "coverage": (n_cov, n_feat),
        "required_recall": (req_hits, req_total),
        "forbidden_violations": sum(s.forbidden_count for s in probes),
        "target_spam": sum(len(s.spam) for s in probes),
        "tier_in_set": (tier_in_set, tier_checked),
        "mean_tier_delta": (sum(deltas) / len(deltas)) if deltas else 0.0,
        "inflated_entries": sum(1 for d in deltas if d > 0),
        "control_mechanism_instances": sum(
            s.total_mechanism_instances for s in controls
        ),
        "control_wide_violations": sum(
            len(s.wide_violations) for s in controls
        ),
    }


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def _pct(hit: int, total: int) -> str:
    return f"{hit}/{total} ({round(100 * hit / total)}%)" if total else "n/a"


def format_vision_score(score: VisionScore) -> str:
    """Render one vision's scorecard as plain text."""
    lines = [
        f"Vision: {score.project}"
        + (
            f"  (target: {score.target_mechanism})"
            if score.target_mechanism
            else "  (control — no mechanism should appear)"
        )
    ]
    for f in score.features:
        if not f.covered:
            if f.coverage_optional:
                lines.append(
                    f"  {f.vision_feature}: not surfaced (coverage-optional — "
                    "Scout declining a non-AI feature is correct)"
                )
            else:
                lines.append(
                    f"  {f.vision_feature}: UNCOVERED — no ai_features entry "
                    "links to it (Scout/Linker miss; excluded from mechanism "
                    "metrics)"
                )
            continue
        marks: list[str] = []
        for m in f.required_hit:
            marks.append(f"+{m}")
        for m in f.required_miss:
            marks.append(f"MISS:{m}")
        for m, entry in f.forbidden_violations:
            marks.append(f"VIOLATION:{m}@{entry}")
        for entry, tier, d in f.tier_checks:
            if d:
                marks.append(f"TIER:{entry}={tier}({d:+d})")
        lines.append(
            f"  {f.vision_feature}: " + (", ".join(marks) if marks else "clean")
        )
        if f.also_check and (f.required_miss or f.forbidden_violations):
            lines.append(f"    manual check: {f.also_check}")
    for m, entry in score.spam:
        lines.append(f"  SPAM: {m} on unrelated entry '{entry}'")
    for m, entry in score.wide_violations:
        lines.append(f"  CONTROL VIOLATION: {m} on '{entry}'")
    if score.max_total_mechanism_instances is not None:
        state = "OVER BUDGET" if score.over_budget else "ok"
        lines.append(
            f"  mechanism instances: {score.total_mechanism_instances} "
            f"(max {score.max_total_mechanism_instances}) — {state}"
        )
    lines.append(
        "  required "
        + _pct(score.required_hits, score.required_total)
        + f" | violations {score.forbidden_count}"
        + f" | spam {len(score.spam)}"
        + " | tier "
        + _pct(score.tier_in_set, score.tier_checked)
    )
    return "\n".join(lines)


def format_overall(agg: dict[str, Any]) -> str:
    """Render the aggregate block printed after all visions."""
    cov = agg["coverage"]
    req = agg["required_recall"]
    tier = agg["tier_in_set"]
    return "\n".join(
        [
            "=" * 62,
            f"OVERALL ({agg['runs']} scored run(s))",
            f"  Vision-feature coverage:      {_pct(*cov)}",
            f"  Required-mechanism recall:    {_pct(*req)}   <- headline",
            f"  Forbidden violations (traps): {agg['forbidden_violations']}"
            "   <- headline",
            f"  Target-mechanism spam:        {agg['target_spam']}",
            f"  Tier within expected set:     {_pct(*tier)}",
            f"  Mean signed tier delta:       {agg['mean_tier_delta']:+.2f}"
            "  (positive = inflation)",
            f"  Inflated entries:             {agg['inflated_entries']}",
            f"  Control mechanism instances:  "
            f"{agg['control_mechanism_instances']} (should be 0)",
            "=" * 62,
        ]
    )
