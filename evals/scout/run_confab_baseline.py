#!/usr/bin/env python3
"""Layer-2 confabulation baseline — the trusted judge over real Scout output.

This is the payoff run the calibration corpus was built to enable. It:

  1. runs Scout over each probe vision N times (Scout is non-deterministic);
  2. filters DETERMINISTIC candidates via the Tier Analyst — the membership
     floor, which is NOT the relevance judge's job — and reports that drop rate
     separately (drive it toward 0);
  3. judges every remaining candidate instance with the LOCKED ``drop_domain``
     relevance judge on ``SPEC4_JUDGE_MODEL``;
  4. reports the pooled grounded / adjacent / off_domain distribution, the
     per-run spread, a candidate TIER PROFILE, and a TIMING & RELIABILITY
     section so a long run explains itself.

Per-candidate tier + judge calls run under a bounded thread pool
(``--concurrency``); the underlying ``complete`` is blocking, so real parallelism
needs threads, not just asyncio. Individual call failures are recorded and the
run continues — one bad call no longer aborts a vision.

Usage:
    uv run python evals/scout/run_confab_baseline.py [vision.json ...] \
        [--runs N] [--concurrency K] [--variant drop_domain|audience_goal] \
        [--filter-model MODEL] [--skip-filter] [--tier-only] [--dry-run]

Defaults to every *.json under evals/scout/visions/, --runs 3, --concurrency 6.
ALWAYS exits 0.  Real LLM calls unless --dry-run (which stubs the whole pipeline).

Environment (live runs):
    SPEC4_MODEL           required — Scout's model (and the deterministic filter's
                          model unless --filter-model overrides it).
    SPEC4_JUDGE_MODEL     required (unless --tier-only) — the trusted judge's
                          model. Separate from SPEC4_MODEL on purpose.
    SPEC4_API_KEY / _BASE            optional — provider creds for Scout/filter.
    SPEC4_JUDGE_API_KEY / _BASE      optional — fall back to SPEC4_API_KEY / _BASE.

Caveat (D3): the confab rate is a mild OVER-estimate — the judge has three
confirmed over-flag blind spots. The reason dump on off_domain + borderline rows
is printed so a human can separate likely confabulation from that known bias.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from confab_baseline import (  # noqa: E402
    CallRecord,
    Instance,
    VisionDiag,
    format_corpus_rollup,
    format_diagnostics,
    format_tier_profile,
    format_vision_report,
    split_membership,
    summarise_vision,
)
from relevance_judge import VARIANTS, judge_candidate  # noqa: E402

from spec4.agentifier.pattern_loader import load_patterns  # noqa: E402
from spec4.agentifier.scout import ScoutAgent, ScoutInput  # noqa: E402
from spec4.agentifier.tier_analyst import (  # noqa: E402
    TierAnalystAgent,
    TierAnalystInput,
)

_DEFAULT_VISIONS_DIR = Path(__file__).resolve().parent / "visions"

_BANNER = """\
==============================================================
  CONFABULATION BASELINE  —  trusted judge over real Scout output
  Real LLM calls (Scout + Tier Analyst filter + judge). Costs tokens.
=============================================================="""

_DRY_BANNER = """\
==============================================================
  CONFABULATION BASELINE  —  DRY-RUN (no LLM calls)
  Scout, filter, and judge are all stubbed to show output shape.
=============================================================="""


# ---------------------------------------------------------------------------
# llm_config sourcing
# ---------------------------------------------------------------------------

def _cfg_from(model_var: str, key_var: str, base_var: str) -> dict[str, Any]:
    model = os.environ.get(model_var, "")
    if not model:
        print(f"\nERROR: {model_var} is not set.", file=sys.stderr)
        sys.exit(1)
    cfg: dict[str, Any] = {"model": model}
    key = os.environ.get(key_var, "") or os.environ.get("SPEC4_API_KEY", "")
    base = os.environ.get(base_var, "") or os.environ.get("SPEC4_API_BASE", "")
    if key:
        cfg["api_key"] = key
    if base:
        cfg["api_base"] = base
    return cfg


def _scout_cfg() -> dict[str, Any]:
    return _cfg_from("SPEC4_MODEL", "SPEC4_API_KEY", "SPEC4_API_BASE")


def _judge_cfg() -> dict[str, Any]:
    return _cfg_from("SPEC4_JUDGE_MODEL", "SPEC4_JUDGE_API_KEY", "SPEC4_JUDGE_API_BASE")


# ---------------------------------------------------------------------------
# Scout phase (async agent, sequential runs) + per-candidate worker (threaded)
# ---------------------------------------------------------------------------

async def _scout_once(
    agent: ScoutAgent, vision: dict[str, Any], cfg: dict[str, Any]
) -> list[Any]:
    out = await agent.run(ScoutInput(vision=vision, llm_config=cfg))
    return out.candidates


def _scout_phase(
    scout: ScoutAgent,
    vision: dict[str, Any],
    scout_cfg: dict[str, Any],
    n_runs: int,
    diag: VisionDiag,
) -> list[tuple[int, Any]]:
    """Run Scout n_runs times (sequential). Records timing/empties/failures."""
    pending: list[tuple[int, Any]] = []
    for run in range(1, n_runs + 1):
        t0 = time.perf_counter()
        try:
            cands = asyncio.run(_scout_once(scout, vision, scout_cfg))
            diag.calls.append(CallRecord("scout", time.perf_counter() - t0, True))
            if not cands:
                diag.empty_runs += 1
            pending.extend((run, c) for c in cands)
        except Exception as exc:  # noqa: BLE001 - record and survive
            diag.calls.append(
                CallRecord("scout", time.perf_counter() - t0, False,
                           type(exc).__name__)
            )
            diag.scout_failures += 1
    return pending


def _tier_sync(
    agent: TierAnalystAgent, cand: Any, cfg: dict[str, Any], patterns: list[Any]
) -> str:
    """Blocking Tier Analyst call (its own event loop inside the worker thread)."""
    out = asyncio.run(
        agent.run(
            TierAnalystInput(candidate=cand, llm_config=cfg, tier_patterns=patterns)
        )
    )
    return out.recommended_tier


def _process_candidate(
    run_idx: int,
    cand: Any,
    *,
    vision: dict[str, Any],
    vision_name: str,
    tier_agent: TierAnalystAgent | None,
    filter_cfg: dict[str, Any],
    tier_patterns: list[Any],
    judge_cfg: dict[str, Any],
    variant: str,
    skip_filter: bool,
    tier_only: bool,
) -> tuple[Instance, list[CallRecord]]:
    """One candidate: tier (unless skipped) then judge (unless deterministic /
    tier-only). Runs in a worker thread; records timing + any failure."""
    records: list[CallRecord] = []
    name = str(getattr(cand, "name", ""))

    if skip_filter:
        tier = "unfiltered"
    else:
        t0 = time.perf_counter()
        try:
            tier = _tier_sync(tier_agent, cand, filter_cfg, tier_patterns)
            records.append(CallRecord("tier", time.perf_counter() - t0, True))
        except Exception as exc:  # noqa: BLE001 - record and survive
            records.append(
                CallRecord("tier", time.perf_counter() - t0, False,
                           type(exc).__name__)
            )
            tier = "error"

    if tier == "deterministic":
        return Instance(vision_name, run_idx, name, tier=tier), records
    if tier_only:
        return Instance(vision_name, run_idx, name, tier=tier), records

    t0 = time.perf_counter()
    try:
        verdict = judge_candidate(vision, cand, judge_cfg, variant)
        records.append(CallRecord("judge", time.perf_counter() - t0, True))
        return (
            Instance(
                vision=vision_name, run=run_idx, name=name, tier=tier,
                classification=verdict.classification,
                borderline=verdict.borderline, reason=verdict.reason,
            ),
            records,
        )
    except Exception as exc:  # noqa: BLE001 - record and survive
        records.append(
            CallRecord("judge", time.perf_counter() - t0, False, type(exc).__name__)
        )
        return (
            Instance(vision_name, run_idx, name, tier=tier, classification="error",
                     reason=f"judge failed: {type(exc).__name__}"),
            records,
        )


def _collect_vision(
    *,
    vision: dict[str, Any],
    vision_name: str,
    scout_cfg: dict[str, Any],
    filter_cfg: dict[str, Any],
    judge_cfg: dict[str, Any],
    variant: str,
    n_runs: int,
    skip_filter: bool,
    tier_only: bool,
    concurrency: int,
) -> tuple[list[Instance], VisionDiag]:
    """Scout (sequential) -> tier+judge (concurrent, bounded) for one vision."""
    scout = ScoutAgent()
    tier_agent = None if skip_filter else TierAnalystAgent()
    tier_patterns: list[Any] = []
    if not skip_filter:
        tier_patterns, _ = load_patterns()

    diag = VisionDiag(vision=vision_name, attempted_runs=n_runs)
    pending = _scout_phase(scout, vision, scout_cfg, n_runs, diag)

    instances: list[Instance] = []
    if pending:
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = [
                pool.submit(
                    _process_candidate, run_idx, cand,
                    vision=vision, vision_name=vision_name, tier_agent=tier_agent,
                    filter_cfg=filter_cfg, tier_patterns=tier_patterns,
                    judge_cfg=judge_cfg, variant=variant,
                    skip_filter=skip_filter, tier_only=tier_only,
                )
                for run_idx, cand in pending
            ]
            for fut in futures:
                inst, recs = fut.result()
                instances.append(inst)
                diag.calls.extend(recs)
    return instances, diag


# ---------------------------------------------------------------------------
# Dry-run stubs (no LLM)
# ---------------------------------------------------------------------------

def _stub_instances(vision_name: str, n_runs: int) -> list[Instance]:
    """Stub exercising every branch: filtered, grounded, adjacent, off_domain,
    and a borderline row."""
    rows = [
        ("field_extractor", "single_call", "grounded", False),
        ("smart_helper", "tool_agent", "adjacent", False),
        ("cross_product_upsell", "single_call", "off_domain", False),
        ("edge_case_expander", "rag", "adjacent", True),
        ("static_lookup_table", "deterministic", None, False),
    ]
    out: list[Instance] = []
    for run in range(1, n_runs + 1):
        for name, tier, cls, bd in rows:
            reason = "" if cls is None else f"stub reason for {name}"
            out.append(Instance(vision_name, run, name, tier, cls, bd, reason))
    return out


def _stub_diag(vision_name: str, n_runs: int) -> VisionDiag:
    diag = VisionDiag(vision=vision_name, attempted_runs=n_runs)
    for _ in range(n_runs):
        diag.calls.append(CallRecord("scout", 0.5, True))
        for _ in range(4):  # 4 non-deterministic candidates -> tier + judge
            diag.calls.append(CallRecord("tier", 0.3, True))
            diag.calls.append(CallRecord("judge", 0.9, True))
        diag.calls.append(CallRecord("tier", 0.3, True))  # the deterministic one
    return diag


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Layer-2 confabulation baseline. Always exits 0.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("visions", nargs="*", metavar="vision.json")
    p.add_argument("--runs", type=int, default=3, metavar="N")
    p.add_argument(
        "--concurrency", type=int, default=6, metavar="K",
        help="Max in-flight tier+judge calls (default 6). Also throttles "
        "rate-limit pressure; lower it if you see 429-class failures.",
    )
    p.add_argument("--variant", choices=list(VARIANTS), default="drop_domain")
    p.add_argument(
        "--filter-model", default="", metavar="MODEL",
        help="Model for the deterministic filter (Tier Analyst). Defaults to "
        "SPEC4_MODEL.",
    )
    p.add_argument(
        "--skip-filter", action="store_true", default=False,
        help="Judge every candidate without the deterministic membership filter.",
    )
    p.add_argument(
        "--tier-only", action="store_true", default=False,
        help="Run Scout + Tier Analyst only (no judge, no SPEC4_JUDGE_MODEL "
        "needed). Prints just the candidate tier profile — the cheap way to see "
        "which tiers a vision elicited.",
    )
    p.add_argument("--dry-run", action="store_true", default=False)
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    if args.tier_only and args.skip_filter:
        print("\nERROR: --tier-only needs the Tier Analyst; drop --skip-filter.",
              file=sys.stderr)
        sys.exit(1)

    scout_cfg: dict[str, Any] = {}
    judge_cfg: dict[str, Any] = {}
    filter_cfg: dict[str, Any] = {}
    if args.dry_run:
        print(_DRY_BANNER)
    else:
        print(_BANNER)
        scout_cfg = _scout_cfg()
        filter_cfg = dict(scout_cfg)
        if args.filter_model:
            filter_cfg = dict(scout_cfg, model=args.filter_model)
        print(f"Scout model (SPEC4_MODEL):        {scout_cfg['model']}")
        if args.tier_only:
            print("Mode: TIER-ONLY (no judge calls)")
        else:
            judge_cfg = _judge_cfg()
            print(f"Judge model (SPEC4_JUDGE_MODEL):  {judge_cfg['model']}  "
                  f"[variant={args.variant}]")
        if not args.skip_filter:
            print(f"Filter model (Tier Analyst):      {filter_cfg['model']}")
        print(f"Concurrency:                      {args.concurrency}")
        if judge_cfg and scout_cfg["model"] == judge_cfg["model"]:
            print("\n!  WARNING: judge shares Scout's model — it shares Scout's "
                  "blind spots. Use a stronger judge for a trusted number.")

    if args.visions:
        vision_paths = [Path(p) for p in args.visions]
    else:
        vision_paths = sorted(_DEFAULT_VISIONS_DIR.glob("*.json"))
    if not vision_paths:
        print(f"\nNo vision files found in {_DEFAULT_VISIONS_DIR}", file=sys.stderr)
        sys.exit(0)

    start = time.perf_counter()
    summaries: list[dict[str, Any]] = []
    diags: list[VisionDiag] = []
    for path in vision_paths:
        if not path.exists():
            print(f"\nWARNING: vision not found: {path}", file=sys.stderr)
            continue
        if args.dry_run:
            instances = _stub_instances(path.name, args.runs)
            diag = _stub_diag(path.name, args.runs)
        else:
            vision = json.loads(path.read_text(encoding="utf-8"))
            instances, diag = _collect_vision(
                vision=vision, vision_name=path.name, scout_cfg=scout_cfg,
                filter_cfg=filter_cfg, judge_cfg=judge_cfg, variant=args.variant,
                n_runs=args.runs, skip_filter=args.skip_filter,
                tier_only=args.tier_only, concurrency=args.concurrency,
            )
        summary = summarise_vision(
            path.name, instances, attempted_runs=diag.attempted_runs
        )
        diags.append(diag)
        if not args.tier_only:
            _, judged = split_membership(instances)
            print()
            print(format_vision_report(summary, judged))
        summaries.append(summary)
    wall = time.perf_counter() - start

    if summaries:
        if not args.tier_only:
            print()
            print(format_corpus_rollup(summaries))
        print()
        print(format_tier_profile(summaries))
    print()
    print(format_diagnostics(diags, wall_seconds=wall))

    sys.exit(0)


if __name__ == "__main__":
    main()