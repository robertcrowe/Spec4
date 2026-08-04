#!/usr/bin/env python3
"""Relevance-judge calibration driver + prompt bake-off (dev tooling).

Loads a hand-labelled gold set, runs the Layer-2 relevance judge over its
candidates, and scores predictions against the gold labels (confusion matrix +
the two trust-gate numbers: off_domain recall, adjacent->off_domain FP rate).

Two prompt variants can be compared head-to-head — they differ ONLY on the
adjacency / off_domain boundary (grounded is held identical):
  drop_domain   — adjacency rides on the stated purpose + audience only.
  audience_goal — derive the job(s) first (at most one per feature), then judge
                  adjacency against those jobs; emits stated_jobs.

Usage:
    uv run python evals/scout/run_relevance_eval.py [gold.json ...] \
        [--variant drop_domain|audience_goal|both] [--dry-run]

Defaults to every *.json under evals/scout/calibration/ and --variant both.
ALWAYS exits 0.  ⚠ Real LLM calls unless --dry-run (which stubs predictions).

Environment (live runs):
    SPEC4_JUDGE_MODEL      required — the judge's model (separate from Scout's
                           SPEC4_MODEL; use your strongest available).
    SPEC4_JUDGE_API_KEY    optional — falls back to SPEC4_API_KEY.
    SPEC4_JUDGE_API_BASE   optional — falls back to SPEC4_API_BASE.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from relevance_judge import LABELS, VARIANTS, Verdict, judge_candidates  # noqa: E402
from relevance_scoring import (  # noqa: E402
    format_pair_drift,
    format_scoring_report,
    format_tier_breakdown,
    pair_drift,
    score_by_tier,
    score_verdicts,
)

_DEFAULT_DIR = Path(__file__).resolve().parent / "calibration"


def _build_llm_config() -> dict[str, Any]:
    """Build the JUDGE llm_config from SPEC4_JUDGE_* env vars.

    The judge runs on its OWN model — deliberately separate from SPEC4_MODEL
    (which drives Scout) — so it can be a stronger model than the one Scout is
    scored on. SPEC4_JUDGE_MODEL is required (no silent fallback to SPEC4_MODEL:
    that is how you'd accidentally judge on Haiku and never notice). The
    key/base fall back to the plain SPEC4_API_KEY / SPEC4_API_BASE when the
    judge-specific overrides are unset.
    """
    model = os.environ.get("SPEC4_JUDGE_MODEL", "")
    if not model:
        print(
            "\nERROR: SPEC4_JUDGE_MODEL is not set.\n"
            "The judge runs on its own model, separate from SPEC4_MODEL (Scout).\n"
            "Set it to your strongest available model, e.g.:\n"
            "  export SPEC4_JUDGE_MODEL='claude-opus-4-...'\n",
            file=sys.stderr,
        )
        sys.exit(1)
    cfg: dict[str, Any] = {"model": model}
    api_key = os.environ.get("SPEC4_JUDGE_API_KEY") or os.environ.get("SPEC4_API_KEY")
    if api_key:
        cfg["api_key"] = api_key
    api_base = os.environ.get("SPEC4_JUDGE_API_BASE") or os.environ.get("SPEC4_API_BASE")
    if api_base:
        cfg["api_base"] = api_base
    return cfg


def _gold_verdicts(candidates: list[dict[str, Any]]) -> list[Verdict]:
    out: list[Verdict] = []
    for c in candidates:
        label = str(c.get("gold_label", "")).strip().lower()
        if label not in LABELS:
            raise ValueError(f"gold_label for {c.get('name')!r} is not a real class")
        out.append(Verdict(str(c["name"]), label,
                           borderline=bool(c.get("gold_borderline", False))))
    return out


def _stub_predictions(gold: list[Verdict], variant: str) -> list[Verdict]:
    """Deterministic per-variant stub so --dry-run exercises everything.

    The two variants are made to disagree (drop_domain flips the first
    adjacent->off_domain; audience_goal flips the first off_domain->adjacent and
    attaches stub stated_jobs), so `both` mode shows real divergence rows.
    """
    pred = [Verdict(v.candidate_name, v.classification, borderline=v.borderline)
            for v in gold]
    if variant == "drop_domain":
        for v in pred:
            if v.classification == "adjacent":
                v.classification = "off_domain"
                break
    else:  # audience_goal
        for v in pred:
            v.stated_jobs = ["(stub) cook tonight from saved recipes"]
        for v in pred:
            if v.classification == "off_domain":
                v.classification = "adjacent"
                break
    return pred


def _predict(vision: dict[str, Any], candidates: list[dict[str, Any]],
             gold: list[Verdict], variant: str,
             llm_config: dict[str, Any] | None, dry_run: bool) -> list[Verdict]:
    if dry_run:
        return _stub_predictions(gold, variant)
    assert llm_config is not None
    return judge_candidates(vision, candidates, llm_config, variant)


def _run_single(vision: dict[str, Any], candidates: list[dict[str, Any]],
                gold: list[Verdict], variant: str,
                llm_config: dict[str, Any] | None,
                dry_run: bool) -> dict[str, list[Verdict]]:
    pred = _predict(vision, candidates, gold, variant, llm_config, dry_run)
    print(f"\n-- variant: {variant} --")
    print(format_scoring_report(score_verdicts(gold, pred)))
    gmap = {v.candidate_name: v for v in gold}
    dis = [p for p in pred if p.classification != gmap[p.candidate_name].classification]
    if dis:
        print("\n  Disagreements (gold -> predicted):")
        for p in dis:
            tag = "  [borderline]" if p.borderline else ""
            jobs = f"   jobs={p.stated_jobs}" if p.stated_jobs else ""
            print(f"    {p.candidate_name}: "
                  f"{gmap[p.candidate_name].classification} -> {p.classification}"
                  f"{tag}{jobs}")
    return {variant: pred}


def _run_both(vision: dict[str, Any], candidates: list[dict[str, Any]],
              gold: list[Verdict], llm_config: dict[str, Any] | None,
              dry_run: bool) -> dict[str, list[Verdict]]:
    pa = _predict(vision, candidates, gold, "drop_domain", llm_config, dry_run)
    pb = _predict(vision, candidates, gold, "audience_goal", llm_config, dry_run)
    ra, rb = score_verdicts(gold, pa), score_verdicts(gold, pb)

    print("\n  Gate numbers (vs gold):")
    for name, r in (("drop_domain", ra), ("audience_goal", rb)):
        print(f"    {name:<14} off_domain recall {r['off_domain_recall']:.2f}   "
              f"adjacent->off_domain FP {r['adjacent_to_offdomain_fp_rate']:.2f}   "
              f"(errors {r['n_parse_errors']}, borderline {r['n_borderline_pred']})")

    amap = {v.candidate_name: v for v in pa}
    bmap = {v.candidate_name: v for v in pb}
    gmap = {v.candidate_name: v for v in gold}
    print("\n  Per-candidate (gold | drop_domain | audience_goal; * = variants "
          "disagree):")
    print(f"    {'candidate':<36}{'gold':<12}{'drop_domain':<14}{'audience_goal':<14}")
    divergent: list[str] = []
    for name in [g.candidate_name for g in gold]:
        a, b = amap[name].classification, bmap[name].classification
        star = " *" if a != b else ""
        print(f"    {name:<36}{gmap[name].classification:<12}{a:<14}{b:<14}{star}")
        if a != b:
            divergent.append(name)

    if divergent:
        print("\n  Divergent rows (why each variant landed where it did):")
        for name in divergent:
            print(f"    {name}:")
            print(f"      drop_domain   [{amap[name].classification}] "
                  f"{amap[name].reason or '(no reason)'}")
            jtxt = f"  jobs={bmap[name].stated_jobs}" if bmap[name].stated_jobs else ""
            print(f"      audience_goal [{bmap[name].classification}] "
                  f"{bmap[name].reason or '(no reason)'}{jtxt}")
    return {"drop_domain": pa, "audience_goal": pb}


def _run_one(
    path: Path, variant: str, llm_config: dict[str, Any] | None, dry_run: bool
) -> tuple[list[Verdict], dict[str, list[Verdict]], dict[str, str], dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    vision, candidates = data["vision"], data["candidates"]
    gold = _gold_verdicts(candidates)
    name_to_tier = {str(c["name"]): c["tier"] for c in candidates if c.get("tier")}
    name_to_pair = {
        str(c["name"]): c["pair_id"] for c in candidates if c.get("pair_id")
    }
    print("\n==============================================================")
    print(f"GOLD SET: {path.name}   ({len(candidates)} candidates)   variant={variant}")
    if variant == "both":
        preds = _run_both(vision, candidates, gold, llm_config, dry_run)
    else:
        preds = _run_single(vision, candidates, gold, variant, llm_config, dry_run)
    return gold, preds, name_to_tier, name_to_pair


def main() -> None:
    parser = argparse.ArgumentParser(description="Relevance-judge bake-off. Exits 0.")
    parser.add_argument("gold", nargs="*", metavar="gold.json")
    parser.add_argument("--variant", choices=[*VARIANTS, "both"], default="both")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Stub predictions (no LLM calls) to verify plumbing.")
    args = parser.parse_args()

    paths = [Path(p) for p in args.gold] if args.gold else sorted(
        _DEFAULT_DIR.glob("*.json"))
    if not paths:
        print(f"\nNo gold files found in {_DEFAULT_DIR}", file=sys.stderr)
        sys.exit(0)

    llm_config = None if args.dry_run else _build_llm_config()
    if args.dry_run:
        print("=== DRY-RUN: predictions are stubbed, no LLM calls ===")
    else:
        print(f"Judge model (SPEC4_JUDGE_MODEL): {llm_config['model']}")
        scout_model = os.environ.get("SPEC4_MODEL", "")
        if scout_model and scout_model == llm_config["model"]:
            print(
                f"⚠  WARNING: judging with the SAME model Scout uses ({scout_model}) "
                "— the judge shares its blind spots. Use a stronger judge model "
                "for a trusted calibration or confabulation number."
            )
    corpus_gold: list[Verdict] = []
    corpus_preds: dict[str, list[Verdict]] = {}
    corpus_tier: dict[str, str] = {}
    corpus_pair: dict[str, str] = {}
    for path in paths:
        if not path.exists():
            print(f"\nWARNING: gold file not found: {path}", file=sys.stderr)
            continue
        gold, preds, t_map, p_map = _run_one(
            path, args.variant, llm_config, args.dry_run
        )
        corpus_gold.extend(gold)
        for v, pr in preds.items():
            corpus_preds.setdefault(v, []).extend(pr)
        corpus_tier.update(t_map)
        corpus_pair.update(p_map)

    # Corpus-level rollups: per-tier gate numbers and matched-pair drift are
    # only meaningful pooled across all gold sets (per-vision, tiers are n=1-2).
    if corpus_gold and corpus_preds:
        variants = [v for v in VARIANTS if v in corpus_preds]
        by_tier = {
            v: score_by_tier(corpus_gold, corpus_preds[v], corpus_tier)
            for v in variants
        }
        print("\n==============================================================")
        print(format_tier_breakdown(by_tier, variants))
        if corpus_pair:
            drift = {v: pair_drift(corpus_preds[v], corpus_pair) for v in variants}
            print("")
            print(format_pair_drift(drift, variants, corpus_tier))
    sys.exit(0)


if __name__ == "__main__":
    main()