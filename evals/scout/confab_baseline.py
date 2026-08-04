"""Aggregation + formatting for the Layer-2 confabulation baseline (dev tooling).

Pure, unit-tested, makes no LLM calls. The driver (``run_confab_baseline.py``)
runs Scout over the probe visions, filters deterministic candidates via the Tier
Analyst (the membership floor — NOT the relevance judge's job), judges the rest
with the locked ``drop_domain`` relevance judge, and hands the resulting
``Instance`` rows here to be turned into the baseline number.

The baseline is an UNLABELLED distribution, not a scored confusion matrix: over
the candidates Scout actually emits, what share does the trusted judge call
grounded / adjacent / off_domain. The ``off_domain`` share is the confabulation
rate. Because Scout is non-deterministic, every candidate instance from every run
is judged (D1: judge all across N runs) and the per-run confab rate is reported
as a spread, so the pooled number carries its own error bars.

Known caveat (D3), surfaced by the driver, not computed here: the judge has three
confirmed over-flag blind spots (derivable-job / different-surface adjacents it
wrongly calls off_domain), so the raw confab rate is a mild OVER-estimate. The
reason dump on off_domain + borderline rows is what lets a human separate likely
confabulation from that known bias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# The relevance labels a judged candidate can carry (plus "error" for an
# unparseable judge response). Kept in sync with relevance_judge.LABELS but not
# imported, so this module stays free of the LLM-calling package.
_LABELS = ("grounded", "adjacent", "off_domain")
_COUNT_KEYS = (*_LABELS, "error")

# A candidate the Tier Analyst rates at this tier is a membership drop, not a
# relevance candidate: it never reaches the judge.
_DETERMINISTIC = "deterministic"

# The tier ladder (deterministic .. multi_agent_collaboration), mirroring
# spec4.agentifier.tier_analyst._VALID_TIERS. Defined locally so this module
# stays free of the LLM-calling package (same reason _LABELS is local).
_TIER_LADDER = (
    "deterministic",
    "embeddings",
    "single_call",
    "rag",
    "tool_agent",
    "chained_calls",
    "planning_agent",
    "orchestrated_subagents",
    "multi_agent_collaboration",
)
_TIER_SHORT = {
    "deterministic": "det",
    "embeddings": "emb",
    "single_call": "sc",
    "rag": "rag",
    "tool_agent": "tool",
    "chained_calls": "chn",
    "planning_agent": "plan",
    "orchestrated_subagents": "orch",
    "multi_agent_collaboration": "multi",
}


@dataclass
class Instance:
    """One Scout-emitted candidate instance from one run of one vision.

    ``tier`` is the Tier Analyst's recommendation. When it is ``deterministic``
    the instance is a membership drop and ``classification`` is ``None`` (it was
    never judged). Otherwise ``classification`` is the relevance judge's verdict
    (one of ``_LABELS`` or ``"error"``).
    """

    vision: str
    run: int
    name: str
    tier: str
    classification: str | None = None
    borderline: bool = False
    reason: str = ""

    @property
    def is_deterministic(self) -> bool:
        return self.tier == _DETERMINISTIC


@dataclass
class CallRecord:
    """One LLM round-trip: which agent, how long, and whether it succeeded."""

    kind: str  # "scout" | "tier" | "judge"
    seconds: float
    ok: bool
    error: str = ""


@dataclass
class VisionDiag:
    """Per-vision instrumentation. ``attempted_runs`` is what we ASKED Scout for,

    so an empty run (Scout returned nothing) stays visible instead of silently
    shrinking the denominator — the bug that made vision 02 read as N=2.
    """

    vision: str
    attempted_runs: int
    empty_runs: int = 0
    scout_failures: int = 0
    calls: list[CallRecord] = field(default_factory=list)


def split_membership(
    instances: list[Instance],
) -> tuple[list[Instance], list[Instance]]:
    """Partition into (deterministic-filtered, judged) by tier.

    Deterministic candidates are the membership floor (the Tier Analyst's rate,
    measured separately) and are never fed to the relevance judge.
    """
    filtered = [i for i in instances if i.is_deterministic]
    judged = [i for i in instances if not i.is_deterministic]
    return filtered, judged


def distribution(judged: list[Instance]) -> dict[str, int]:
    """Count judged instances by relevance class (plus an ``error`` bucket)."""
    counts = {k: 0 for k in _COUNT_KEYS}
    for inst in judged:
        key = inst.classification if inst.classification in _COUNT_KEYS else "error"
        counts[key] += 1
    counts["n"] = len(judged)
    return counts


def _rate(numerator: int, denominator: int) -> float | None:
    """Share, or ``None`` when there is no denominator (not measured != 0.0)."""
    return numerator / denominator if denominator else None


def rates(dist: dict[str, int]) -> dict[str, float | None]:
    """grounded / adjacent / off_domain shares of the judged pool.

    ``confab`` is an alias for the off_domain share — the headline baseline.
    Rates are ``None`` when nothing was judged, so an empty vision reads as "not
    measured" rather than a misleading 0.0.
    """
    n = dist.get("n", 0)
    return {
        "grounded": _rate(dist["grounded"], n),
        "adjacent": _rate(dist["adjacent"], n),
        "off_domain": _rate(dist["off_domain"], n),
        "confab": _rate(dist["off_domain"], n),
    }


def deterministic_rate(
    filtered: list[Instance], judged: list[Instance]
) -> float | None:
    """Share of ALL Scout-emitted instances that were deterministic-filtered.

    The denominator is emitted = filtered + judged, so this is "of everything
    Scout produced, how much was membership noise" — the number to drive to 0.
    """
    total = len(filtered) + len(judged)
    return _rate(len(filtered), total)


def tier_histogram(instances: list[Instance]) -> dict[str, int]:
    """Count ALL emitted instances by Tier Analyst tier, across the full ladder.

    Includes deterministic (tier 1) candidates: the histogram is over everything
    Scout surfaced, so it answers "what tiers did this vision actually elicit."
    A tier off the ladder (the ``unfiltered`` sentinel, or any unexpected value)
    is bucketed under ``other`` so nothing is silently dropped.
    """
    hist: dict[str, int] = {t: 0 for t in _TIER_LADDER}
    for inst in instances:
        if inst.tier in hist:
            hist[inst.tier] += 1
        else:
            hist["other"] = hist.get("other", 0) + 1
    return hist


def peak_tier(hist: dict[str, int]) -> str | None:
    """Highest ladder tier with any candidate; ``None`` if none on the ladder.

    Sensitive to a single outlier candidate — read the histogram mass, not just
    this. A high-tier vision whose peak sits low is the decomposition-dissolution
    effect: per-feature candidates are individually low-tier even when the system
    is not.
    """
    for tier in reversed(_TIER_LADDER):
        if hist.get(tier, 0) > 0:
            return tier
    return None


def per_run_spread(judged: list[Instance]) -> dict[str, Any]:
    """Confab (off_domain) rate computed per run, then summarised.

    Runs with nothing judged contribute no rate (excluded from min/max/mean), so
    an empty run never drags the spread to a false 0.0. Returns per-run rates and
    the min / mean / max across the runs that had a denominator.
    """
    by_run: dict[int, list[Instance]] = {}
    for inst in judged:
        by_run.setdefault(inst.run, []).append(inst)
    per_run: dict[int, float] = {}
    for run, insts in sorted(by_run.items()):
        rate = _rate(sum(i.classification == "off_domain" for i in insts), len(insts))
        if rate is not None:
            per_run[run] = rate
    vals = list(per_run.values())
    return {
        "per_run": per_run,
        "min": min(vals) if vals else None,
        "mean": sum(vals) / len(vals) if vals else None,
        "max": max(vals) if vals else None,
    }


def summarise_vision(
    vision: str, instances: list[Instance], attempted_runs: int | None = None
) -> dict[str, Any]:
    """Full per-vision rollup: counts, rates, deterministic drop, run spread.

    ``attempted_runs`` is the honest run denominator (what Scout was asked for).
    When omitted it falls back to the number of runs that actually emitted a
    candidate — which undercounts when a run came back empty, so the driver
    always passes the attempted count.
    """
    filtered, judged = split_membership(instances)
    dist = distribution(judged)
    if attempted_runs is not None:
        n_runs = attempted_runs
    else:
        n_runs = len({i.run for i in instances})
    return {
        "vision": vision,
        "n_runs": n_runs,
        "n_emitted": len(instances),
        "n_deterministic": len(filtered),
        "deterministic_rate": deterministic_rate(filtered, judged),
        "distribution": dist,
        "rates": rates(dist),
        "spread": per_run_spread(judged),
        "tier_histogram": tier_histogram(instances),
    }


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _pct(x: float | None) -> str:
    return "  — " if x is None else f"{x * 100:4.1f}"


def _reason_rows(judged: list[Instance]) -> list[Instance]:
    """The rows the reason dump explains: every off_domain, plus any borderline.

    On unlabelled probe output the named calibration blind spots cannot be
    matched, so their SHAPE is caught via the judge's own ``borderline`` flag —
    exactly the surface where the D3 over-flag bias lives.
    """
    rows = [
        i
        for i in judged
        if i.classification == "off_domain" or i.borderline
    ]
    return sorted(rows, key=lambda i: (i.run, i.name))


def format_vision_report(summary: dict[str, Any], judged: list[Instance]) -> str:
    """Render one vision's baseline block, including the reason dump."""
    d = summary["distribution"]
    r = summary["rates"]
    sp = summary["spread"]
    n = d["n"]
    avg = summary["n_emitted"] / summary["n_runs"] if summary["n_runs"] else 0.0
    lines = [
        "==============================================================",
        f"VISION: {summary['vision']}   (N={summary['n_runs']} runs)",
        f"  Scout emitted: {summary['n_emitted']} candidate-instances "
        f"across {summary['n_runs']} runs (avg {avg:.1f}/run)",
        f"  Deterministic-filtered (membership, not judged): "
        f"{summary['n_deterministic']}  ({_pct(summary['deterministic_rate'])}%)"
        f"   <- drive toward 0",
        f"  Judged (relevance): {n}",
        f"    grounded    {d['grounded']:>3}  ({_pct(r['grounded'])}%)",
        f"    adjacent    {d['adjacent']:>3}  ({_pct(r['adjacent'])}%)",
        f"    off_domain  {d['off_domain']:>3}  ({_pct(r['off_domain'])}%)"
        f"   <- CONFABULATION RATE",
        f"    error       {d['error']:>3}",
        f"  Per-run confab rate: min {_pct(sp['min'])}  mean {_pct(sp['mean'])}  "
        f"max {_pct(sp['max'])}  (spread over runs with a denominator)",
    ]
    reason_rows = _reason_rows(judged)
    if reason_rows:
        lines.append("")
        lines.append("  Reason dump (off_domain + borderline rows):")
        for inst in reason_rows:
            flag = inst.classification or "?"
            bd = ", borderline" if inst.borderline else ""
            lines.append(f"    [{flag}{bd}] {inst.name} (run {inst.run})")
            lines.append(f"       {inst.reason or '(no reason)'}")
    return "\n".join(lines)


def format_corpus_rollup(summaries: list[dict[str, Any]]) -> str:
    """Per-vision table plus the pooled baseline across every vision."""
    lines = [
        "==============================================================",
        "CONFABULATION BASELINE — CORPUS ROLLUP  (drop_domain judge)",
        f"  {'vision':<32}{'emit':>5}{'det%':>7}{'judged':>8}"
        f"{'grnd%':>7}{'adj%':>7}{'confab%':>9}",
    ]
    tot_emit = tot_det = tot_judged = 0
    tot_g = tot_a = tot_o = 0
    for s in summaries:
        d = s["distribution"]
        r = s["rates"]
        lines.append(
            f"  {s['vision']:<32}{s['n_emitted']:>5}"
            f"{_pct(s['deterministic_rate']):>7}{d['n']:>8}"
            f"{_pct(r['grounded']):>7}{_pct(r['adjacent']):>7}"
            f"{_pct(r['off_domain']):>9}"
        )
        tot_emit += s["n_emitted"]
        tot_det += s["n_deterministic"]
        tot_judged += d["n"]
        tot_g += d["grounded"]
        tot_a += d["adjacent"]
        tot_o += d["off_domain"]
    lines.append("  " + "-" * 68)
    det_pool = _rate(tot_det, tot_emit)
    g_pool = _rate(tot_g, tot_judged)
    a_pool = _rate(tot_a, tot_judged)
    o_pool = _rate(tot_o, tot_judged)
    lines.append(
        f"  {'POOLED':<32}{tot_emit:>5}{_pct(det_pool):>7}{tot_judged:>8}"
        f"{_pct(g_pool):>7}{_pct(a_pool):>7}{_pct(o_pool):>9}"
    )
    lines.append("")
    lines.append(
        "  det%    = deterministic-filtered share of emitted "
        "(membership floor — drive to 0)"
    )
    lines.append(
        "  confab% = off_domain share of judged candidates "
        "(the pre-redesign baseline)"
    )
    lines.append(
        "  NOTE: confab% is a mild OVER-estimate — the judge has 3 confirmed"
    )
    lines.append(
        "  over-flag blind spots (derivable-job / different-surface adjacents)."
    )
    lines.append(
        "  The per-vision reason dump separates likely confab from that bias."
    )
    return "\n".join(lines)


def format_tier_profile(summaries: list[dict[str, Any]]) -> str:
    """Per-vision histogram across the tier ladder — what tiers Scout surfaced.

    Answers the question the relevance distribution cannot: did a vision built to
    elicit a high tier actually produce high-tier candidates, or did Scout's
    per-feature decomposition flatten everything to low tiers? Tiers are the Tier
    Analyst's per-candidate recommendation (on the filter model), over ALL
    emitted candidates including deterministic.
    """
    heads = "".join(f"{_TIER_SHORT[t]:>6}" for t in _TIER_LADDER)
    width = 34 + 6 * len(_TIER_LADDER) + 8
    lines = [
        "==============================================================",
        "CANDIDATE TIER PROFILE  (Tier Analyst tier per surfaced candidate)",
        f"  {'vision':<32}{heads}   peak",
    ]
    totals: dict[str, int] = {t: 0 for t in _TIER_LADDER}
    for s in summaries:
        h = s["tier_histogram"]
        row = "".join(f"{h.get(t, 0):>6}" for t in _TIER_LADDER)
        pk = peak_tier(h)
        lines.append(f"  {s['vision']:<32}{row}   {_TIER_SHORT.get(pk, '—')}")
        for t in _TIER_LADDER:
            totals[t] += h.get(t, 0)
    lines.append("  " + "-" * width)
    trow = "".join(f"{totals[t]:>6}" for t in _TIER_LADDER)
    lines.append(f"  {'POOLED':<32}{trow}")
    lines.append("")
    lines.append(
        "  Tier = Tier Analyst recommendation per candidate (filter model), over"
    )
    lines.append(
        "  ALL emitted candidates incl. deterministic (det = the membership drop)."
    )
    lines.append(
        "  peak = highest ladder tier with any candidate (one outlier can set it —"
    )
    lines.append("  read the mass). A high-tier vision peaking low is decomposition")
    lines.append("  dissolution: per-feature candidates are individually low-tier.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Timing & reliability (self-diagnosis)
# ---------------------------------------------------------------------------

_CALL_KINDS = ("scout", "tier", "judge")


def summarise_calls(diags: list[VisionDiag]) -> dict[str, Any]:
    """Aggregate call counts / time / failures across every vision's records."""
    per: dict[str, dict[str, float]] = {
        k: {"n": 0, "fail": 0, "seconds": 0.0} for k in _CALL_KINDS
    }
    failures: dict[tuple[str, str], int] = {}
    attempted = empty = scout_fail = 0
    for d in diags:
        attempted += d.attempted_runs
        empty += d.empty_runs
        scout_fail += d.scout_failures
        for c in d.calls:
            bucket = per.setdefault(c.kind, {"n": 0, "fail": 0, "seconds": 0.0})
            bucket["n"] += 1
            bucket["seconds"] += c.seconds
            if not c.ok:
                bucket["fail"] += 1
                key = (c.kind, c.error or "?")
                failures[key] = failures.get(key, 0) + 1
    return {
        "per_kind": per,
        "failures": failures,
        "attempted_runs": attempted,
        "empty_runs": empty,
        "scout_failures": scout_fail,
    }


def format_diagnostics(
    diags: list[VisionDiag], wall_seconds: float | None = None
) -> str:
    """Render the TIMING & RELIABILITY section — makes a long run self-explaining.

    ``total_s`` is serial-equivalent wait (the sum of every call). With bounded
    concurrency the actual wall clock is lower; the ratio is the speedup.
    """
    s = summarise_calls(diags)
    lines = [
        "==============================================================",
        "TIMING & RELIABILITY",
        f"  {'calls':<8}{'n':>6}{'fail':>6}{'total_s':>10}{'mean_s':>9}",
    ]
    tot_n = tot_fail = 0
    tot_sec = 0.0
    for kind in _CALL_KINDS:
        b = s["per_kind"].get(kind, {"n": 0, "fail": 0, "seconds": 0.0})
        n = int(b["n"])
        mean = b["seconds"] / n if n else 0.0
        lines.append(
            f"  {kind:<8}{n:>6}{int(b['fail']):>6}{b['seconds']:>10.1f}{mean:>9.2f}"
        )
        tot_n += n
        tot_fail += int(b["fail"])
        tot_sec += b["seconds"]
    lines.append("  " + "-" * 39)
    lines.append(f"  {'TOTAL':<8}{tot_n:>6}{tot_fail:>6}{tot_sec:>10.1f}")
    if wall_seconds is not None:
        speedup = tot_sec / wall_seconds if wall_seconds else 0.0
        lines.append(
            f"  wall {wall_seconds:.1f}s  vs serial-equivalent {tot_sec:.1f}s"
            f"  ({speedup:.1f}x from concurrency)"
        )
    lines.append(
        f"  runs attempted {s['attempted_runs']}   empty runs {s['empty_runs']}"
        f"   scout failures {s['scout_failures']}"
    )
    if s["failures"]:
        lines.append("  Call failures:")
        for (kind, err), cnt in sorted(s["failures"].items()):
            lines.append(f"    {kind}: {err} x{cnt}")
    else:
        lines.append("  No call failures.")
    return "\n".join(lines)