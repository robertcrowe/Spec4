"""Confusion-matrix scoring for the relevance judge (dev tooling).

Compares the judge's predicted Verdicts against a hand-labelled gold set and
produces the numbers that gate whether we trust the judge:

  - full 3x3 confusion matrix (gold x predicted), plus an "error" column for
    unparseable predictions;
  - per-class precision / recall / F1;
  - off_domain RECALL — did the judge catch the planted off-domain candidates?
    (the guardrail; a low value means confabulation slips through);
  - adjacent -> off_domain FALSE-POSITIVE rate — did the judge flag genuine
    adjacent expansion as off-domain? (the opposite error, which would push
    Scout toward under-generation).

Gold and predicted are aligned by candidate name. This module is pure and
unit-tested; it makes no LLM calls.
"""

from __future__ import annotations

from typing import Any

from relevance_judge import LABELS, Verdict

_COLS = (*LABELS, "error")


def confusion_matrix(
    gold: list[Verdict], pred: list[Verdict]
) -> dict[str, dict[str, int]]:
    """Build a gold-label x predicted-label count matrix, aligned by name.

    Raises ValueError if the two sets of candidate names do not match, so a
    dropped/renamed candidate can never silently skew the numbers.
    """
    gmap = {v.candidate_name: v for v in gold}
    pmap = {v.candidate_name: v for v in pred}
    if set(gmap) != set(pmap):
        missing = sorted(set(gmap) - set(pmap))
        extra = sorted(set(pmap) - set(gmap))
        raise ValueError(
            f"gold/pred candidate mismatch — missing from pred: {missing}; "
            f"unexpected in pred: {extra}"
        )
    cm: dict[str, dict[str, int]] = {g: {c: 0 for c in _COLS} for g in LABELS}
    for name, gv in gmap.items():
        if gv.classification not in LABELS:
            raise ValueError(f"gold label for {name!r} is not a real class")
        pcol = pmap[name].classification
        if pcol not in _COLS:
            pcol = "error"
        cm[gv.classification][pcol] += 1
    return cm


def _row_total(cm: dict[str, dict[str, int]], label: str) -> int:
    return sum(cm[label].values())


def _col_total(cm: dict[str, dict[str, int]], label: str) -> int:
    return sum(cm[g].get(label, 0) for g in LABELS)


def per_class_metrics(cm: dict[str, dict[str, int]]) -> dict[str, dict[str, float]]:
    """Precision / recall / F1 per class (predictions of 'error' count against)."""
    out: dict[str, dict[str, float]] = {}
    for label in LABELS:
        tp = cm[label][label]
        gold_n = _row_total(cm, label)          # tp + fn
        pred_n = _col_total(cm, label)          # tp + fp
        precision = tp / pred_n if pred_n else 0.0
        recall = tp / gold_n if gold_n else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall)
            else 0.0
        )
        out[label] = {"precision": precision, "recall": recall, "f1": f1}
    return out


def off_domain_recall(cm: dict[str, dict[str, int]]) -> float:
    """Of gold off_domain candidates, fraction the judge called off_domain."""
    gold_n = _row_total(cm, "off_domain")
    return cm["off_domain"]["off_domain"] / gold_n if gold_n else 0.0


def adjacent_to_offdomain_fp_rate(cm: dict[str, dict[str, int]]) -> float:
    """Of gold adjacent candidates, fraction the judge wrongly called off_domain."""
    gold_n = _row_total(cm, "adjacent")
    return cm["adjacent"]["off_domain"] / gold_n if gold_n else 0.0


def score_verdicts(gold: list[Verdict], pred: list[Verdict]) -> dict[str, Any]:
    """Full calibration report: matrix, per-class metrics, and the trust gate."""
    cm = confusion_matrix(gold, pred)
    n_error = sum(cm[g]["error"] for g in LABELS)
    n_borderline = sum(1 for v in pred if v.borderline)
    return {
        "n": len(gold),
        "confusion_matrix": cm,
        "per_class": per_class_metrics(cm),
        "off_domain_recall": off_domain_recall(cm),
        "adjacent_to_offdomain_fp_rate": adjacent_to_offdomain_fp_rate(cm),
        "n_parse_errors": n_error,
        "n_borderline_pred": n_borderline,
    }


def format_scoring_report(report: dict[str, Any]) -> str:
    cm = report["confusion_matrix"]
    lines = [
        f"Relevance-judge calibration ({report['n']} candidates)",
        f"  parse errors: {report['n_parse_errors']}   "
        f"borderline predictions: {report['n_borderline_pred']}",
        "",
        "  Confusion matrix (rows = gold, cols = predicted):",
        f"    {'gold\\pred':<12}" + "".join(f"{c:>12}" for c in _COLS),
    ]
    for g in LABELS:
        lines.append(f"    {g:<12}" + "".join(f"{cm[g][c]:>12}" for c in _COLS))
    lines.append("")
    lines.append("  Per class:")
    for label, m in report["per_class"].items():
        lines.append(
            f"    {label:<12} precision {m['precision']:.2f}  "
            f"recall {m['recall']:.2f}  f1 {m['f1']:.2f}"
        )
    lines.append("")
    lines.append(
        f"  ** off_domain recall (guardrail): {report['off_domain_recall']:.2f}"
    )
    lines.append(
        f"  ** adjacent->off_domain FP rate:  "
        f"{report['adjacent_to_offdomain_fp_rate']:.2f}"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tier-sliced gate numbers + matched-pair drift (corpus-level; dev tooling)
# ---------------------------------------------------------------------------
# Candidate names are assumed unique across the pooled corpus (each gold set
# uses distinct names), so pooling gold/pred by name never collides.

_TIER_DISPLAY_ORDER = (
    "embeddings",
    "single_call",
    "rag",
    "tool_agent",
    "chained_calls",
    "planning_agent",
    "orchestrated_subagents",
    "multi_agent_collaboration",
    "deterministic",
    "untagged",
)

_TIER_ABBR = {
    "embeddings": "embed",
    "single_call": "single",
    "rag": "rag",
    "tool_agent": "tool",
    "chained_calls": "chained",
    "planning_agent": "planning",
    "orchestrated_subagents": "orch",
    "multi_agent_collaboration": "multi",
    "deterministic": "det",
    "untagged": "untagged",
}


def _fmt_rate(x: float | None) -> str:
    return "—" if x is None else f"{x:.2f}"


def gate_for(gold: list[Verdict], pred: list[Verdict]) -> dict[str, Any]:
    """The two trust-gate numbers for one aligned gold/pred set.

    Rates are ``None`` (not 0.0) when the slice has no gold candidates of the
    relevant class, so an absent denominator reads as "not measured" rather than
    "perfect" or "failed".
    """
    cm = confusion_matrix(gold, pred)
    off_n = _row_total(cm, "off_domain")
    adj_n = _row_total(cm, "adjacent")
    return {
        "n": len(gold),
        "n_off_domain": off_n,
        "n_adjacent": adj_n,
        "off_domain_recall": cm["off_domain"]["off_domain"] / off_n if off_n else None,
        "adjacent_to_offdomain_fp_rate": (
            cm["adjacent"]["off_domain"] / adj_n if adj_n else None
        ),
    }


def score_by_tier(
    gold: list[Verdict], pred: list[Verdict], name_to_tier: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """Gate numbers bucketed by each candidate's tier tag.

    Candidates with no tier tag bucket under ``"untagged"``. Aligned by name; a
    name present in gold but missing from pred raises (via confusion_matrix).
    """
    pmap = {v.candidate_name: v for v in pred}
    buckets: dict[str, tuple[list[Verdict], list[Verdict]]] = {}
    for gv in gold:
        tier = name_to_tier.get(gv.candidate_name) or "untagged"
        g_list, p_list = buckets.setdefault(tier, ([], []))
        g_list.append(gv)
        p_list.append(pmap[gv.candidate_name])
    return {t: gate_for(g, p) for t, (g, p) in buckets.items()}


def pair_drift(
    pred: list[Verdict], name_to_pair: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """For each matched pair, whether its members got different predicted labels.

    Members of a ``pair_id`` express the SAME relevance relationship at
    different tiers. The judge is told to ignore tier, so a within-pair label
    split ("drift") means tier bled into the relevance call.
    """
    pmap = {v.candidate_name: v for v in pred}
    groups: dict[str, list[Verdict]] = {}
    for name, pid in name_to_pair.items():
        if name in pmap:
            groups.setdefault(pid, []).append(pmap[name])
    out: dict[str, dict[str, Any]] = {}
    for pid, members in groups.items():
        labels = {m.classification for m in members}
        out[pid] = {
            "members": [(m.candidate_name, m.classification) for m in members],
            "drift": len(labels) > 1,
        }
    return out


def format_tier_breakdown(
    by_tier: dict[str, dict[str, dict[str, Any]]], variants: list[str]
) -> str:
    """Render the pooled per-tier gate table, one column group per variant."""
    tiers = [t for t in _TIER_DISPLAY_ORDER if any(t in by_tier[v] for v in variants)]
    lines = ["CORPUS TIER BREAKDOWN  (all gold sets pooled, per variant)"]
    header = f"  {'tier':<26}{'n':>4}  "
    for v in variants:
        header += f"  {v:<20}"
    lines.append(header)
    subhdr = f"  {'':<26}{'':>4}  "
    for _ in variants:
        subhdr += f"  {'offR':<6}{'adj>offFP':<12}"
    lines.append(subhdr)
    for t in tiers:
        n = next(by_tier[v][t]["n"] for v in variants if t in by_tier[v])
        label = f"({t})" if t in ("deterministic", "untagged") else t
        row = f"  {label:<26}{n:>4}  "
        for v in variants:
            g = by_tier[v].get(t)
            if g is None:
                row += f"  {'—':<6}{'—':<12}"
            else:
                row += (
                    f"  {_fmt_rate(g['off_domain_recall']):<6}"
                    f"{_fmt_rate(g['adjacent_to_offdomain_fp_rate']):<12}"
                )
        lines.append(row)
    lines.append(
        "  offR = off_domain recall   adj>offFP = adjacent->off_domain FP   "
        "— = no gold denominator in tier"
    )
    return "\n".join(lines)


def format_pair_drift(
    drift: dict[str, dict[str, dict[str, Any]]],
    variants: list[str],
    name_to_tier: dict[str, str],
) -> str:
    """Render the matched-pair drift table, one column per variant."""

    def _tier_idx(name: str) -> int:
        t = name_to_tier.get(name) or "untagged"
        return _TIER_DISPLAY_ORDER.index(t) if t in _TIER_DISPLAY_ORDER else 99

    pair_ids = sorted({pid for v in variants for pid in drift[v]})
    lines = [
        "MATCHED-PAIR DRIFT  (same relevance at two tiers; "
        "split = tier bled into relevance)"
    ]
    header = f"  {'pair':<12}{'tiers':<20}"
    for v in variants:
        header += f"{v:<30}"
    lines.append(header)
    for pid in pair_ids:
        members0 = next(drift[v][pid]["members"] for v in variants if pid in drift[v])
        ordered0 = sorted(members0, key=lambda m: _tier_idx(m[0]))
        tiers = "/".join(
            _TIER_ABBR.get(name_to_tier.get(n) or "untagged", "?") for n, _ in ordered0
        )
        row = f"  {pid:<12}{tiers:<20}"
        for v in variants:
            d = drift[v].get(pid)
            if d is None:
                row += f"{'—':<30}"
            else:
                ordered = sorted(d["members"], key=lambda m: _tier_idx(m[0]))
                labs = "/".join(lbl for _, lbl in ordered)
                flag = "DRIFT" if d["drift"] else "ok"
                row += f"{labs + '  ' + flag:<30}"
        lines.append(row)
    return "\n".join(lines)