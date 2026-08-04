#!/usr/bin/env python3
"""Tier Analyst calibration eval runner.

Feeds frozen labeled candidates directly to the Tier Analyst and reports
over/under-engineering rates and mean absolute tier error.

Usage:
    uv run python evals/run_tier_eval.py [fixture.json ...]  [--runs N] [--dry-run]

Defaults to every *.json under evals/tier_calibration/fixtures/ when no
fixture paths are given.

ALWAYS exits 0. This is a measurement tool, not a CI gate.

⚠  Real LLM calls are made unless --dry-run is passed. This costs tokens.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup — allow importing spec4 without installing the package
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from spec4.agentifier.pattern_loader import load_patterns  # noqa: E402
from spec4.agentifier.scout import Candidate  # noqa: E402
from spec4.agentifier.tier_analyst import TierAnalystAgent, TierAnalystInput  # noqa: E402
# Reuse the existing tier-ordinal map — defined once in _utils, referenced here.
from spec4.agents._utils import _TIER_ORDER_FOR_SUMMARY as _TIER_ORDER  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parent / "tier_calibration" / "fixtures"

_BANNER = """\
==============================================================
  TIER CALIBRATION EVAL  —  real LLM calls, costs tokens
=============================================================="""

_DRY_RUN_BANNER = """\
==============================================================
  TIER CALIBRATION EVAL  —  DRY-RUN (no LLM calls)
  Recommendations are stubbed to show output format.
=============================================================="""

# For dry-run: stub recommendations cycle through a small pattern so the
# table shows non-trivial deltas (some over-engineered, some exact) without
# spending tokens.  The stubs are ONLY used when --dry-run is passed.
_DRY_RUN_STUB: dict[str, str] = {
    "receipt_photo_ocr_parsing":      "single_call",     # exact
    "barcode_data_enrichment":        "single_call",     # over by 2
    "smart_expiry_prediction":        "single_call",     # over by 2
    "expiration_alert_optimization":  "embeddings",      # over by 1
    "recipe_suggestion_engine":       "single_call",     # exact
    "recipe_personalization":         "embeddings",      # exact
    "intelligent_shopping_list_generation": "single_call",  # over by 2
    "shopping_list_optimization":     "deterministic",   # exact
    "inventory_sort_and_prioritization": "deterministic", # exact
}


# ---------------------------------------------------------------------------
# llm_config sourcing
# ---------------------------------------------------------------------------

def _build_llm_config() -> dict[str, Any]:
    """Build an llm_config dict from environment variables.

    Mirrors the shape expected by TierAnalystInput and the rest of the pipeline.
    Required: SPEC4_MODEL (e.g. claude-sonnet-4-6, gpt-4o-mini).
    Optional: SPEC4_API_KEY (overrides provider-specific env var),
              SPEC4_API_BASE (for non-default endpoints like Nebius).
    LiteLLM picks up ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY etc.
    automatically when SPEC4_API_KEY is not set.
    """
    model = os.environ.get("SPEC4_MODEL") or os.environ.get("LITELLM_MODEL", "")
    if not model:
        print(
            "\nERROR: SPEC4_MODEL is not set.\n"
            "Set it to a LiteLLM-compatible model identifier, e.g.:\n"
            "  export SPEC4_MODEL='claude-sonnet-4-6'\n"
            "  export SPEC4_MODEL='gpt-4o-mini'\n"
            "  export SPEC4_MODEL='gemini/gemini-2.0-flash'\n",
            file=sys.stderr,
        )
        sys.exit(1)

    cfg: dict[str, Any] = {"model": model}
    api_key = os.environ.get("SPEC4_API_KEY", "")
    if api_key:
        cfg["api_key"] = api_key
    api_base = os.environ.get("SPEC4_API_BASE", "")
    if api_base:
        cfg["api_base"] = api_base
    return cfg


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _tier_ordinal(tier: str) -> int:
    """Return the 1-based ladder ordinal for a tier name, or 0 if unknown."""
    return _TIER_ORDER.get(tier, 0)


def _delta(recommended: str, expected: str) -> int:
    """Signed tier distance: positive = over-engineered, negative = under-engineered."""
    return _tier_ordinal(recommended) - _tier_ordinal(expected)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _load_fixture(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _make_candidate(d: dict[str, Any]) -> Candidate:
    return Candidate(
        name=str(d.get("name", "")),
        linked_vision_features=list(d.get("linked_vision_features") or []),
        scope=str(d.get("scope", "feature")),
        rough_description=str(d.get("rough_description", "")),
        linked_existing_workflow=str(d.get("linked_existing_workflow") or ""),
    )


async def _run_once(
    agent: TierAnalystAgent,
    candidate: Candidate,
    llm_config: dict[str, Any],
    tiers: Any,
) -> tuple[str, bool]:
    """Run the agent once and return (recommended_tier, borderline)."""
    inp = TierAnalystInput(
        candidate=candidate,
        llm_config=llm_config,
        tier_patterns=tiers,
    )
    out = await agent.run(inp)
    return out.recommended_tier, out.borderline


async def _run_once_full(
    agent: TierAnalystAgent,
    candidate: Candidate,
    llm_config: dict[str, Any],
    tiers: Any,
) -> Any:
    """Run the agent once and return the full TierAnalystOutput (investigation aid).

    Read-only: identical inputs to ``_run_once`` but preserves rationale,
    compared_to_next_tier_down, and borderline_seams instead of discarding them.
    """
    inp = TierAnalystInput(
        candidate=candidate,
        llm_config=llm_config,
        tier_patterns=tiers,
    )
    return await agent.run(inp)


def _print_rationale(name: str, out: Any) -> None:
    """Print the full Tier Analyst output for one candidate (investigation aid).

    This is a single representative draw, printed in addition to the modal
    recommendation above; on a borderline result the reasoning is what tells you
    which adjacent tier it is hovering toward and why it escalated.
    """
    print(f"\n── Rationale capture: {name}  (single representative draw) {'─' * 12}")
    print(f"  recommended_tier:            {out.recommended_tier}")
    print(f"  borderline:                  {out.borderline}")
    if out.borderline_seams:
        print(f"  borderline_seams:            {', '.join(out.borderline_seams)}")
    print(f"  compared_to_next_tier_down:  {out.compared_to_next_tier_down}")
    if out.risks_of_going_higher:
        print("  risks_of_going_higher:")
        for r in out.risks_of_going_higher:
            print(f"    - {r}")
    if out.risks_of_going_lower:
        print("  risks_of_going_lower:")
        for r in out.risks_of_going_lower:
            print(f"    - {r}")
    print(f"  rationale:                   {out.rationale}")


def _evaluate_fixture(
    fixture: dict[str, Any],
    fixture_name: str,
    llm_config: dict[str, Any],
    n_runs: int,
    dry_run: bool,
    show_rationale: bool = False,
) -> dict[str, Any]:
    """Evaluate all candidates in one fixture and return result dict."""
    project = fixture.get("project", fixture_name)
    entries: list[dict[str, Any]] = fixture.get("candidates", [])
    tiers, _ = load_patterns()
    agent = TierAnalystAgent()

    results = []
    for entry in entries:
        cand_data = entry.get("candidate", {})
        expected = str(entry.get("expected_tier", "deterministic"))
        candidate = _make_candidate(cand_data)

        if dry_run:
            stub_tier = _DRY_RUN_STUB.get(candidate.name, expected)
            recommended = stub_tier
            borderline = False
            variation_note = "(dry-run)"
        elif n_runs == 1:
            recommended, borderline = asyncio.run(_run_once(agent, candidate, llm_config, tiers))
            variation_note = ""
        else:
            recs = []
            bl_flags = []
            for _ in range(n_runs):
                rec, bl = asyncio.run(_run_once(agent, candidate, llm_config, tiers))
                recs.append(rec)
                bl_flags.append(bl)
            counter = Counter(recs)
            recommended, _ = counter.most_common(1)[0]
            borderline = Counter(bl_flags).most_common(1)[0][0]
            if len(counter) > 1:
                variation_note = f"(varied: {dict(counter)})"
            else:
                variation_note = f"(stable ×{n_runs})"

        d = _delta(recommended, expected)
        results.append({
            "name": candidate.name,
            "expected": expected,
            "recommended": recommended,
            "delta": d,
            "borderline": borderline,
            "variation_note": variation_note if n_runs > 1 or dry_run else "",
        })

        if show_rationale and not dry_run:
            full = asyncio.run(_run_once_full(agent, candidate, llm_config, tiers))
            _print_rationale(candidate.name, full)

    return {"project": project, "fixture_name": fixture_name, "results": results}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _print_fixture_report(report: dict[str, Any]) -> None:
    project = report["project"]
    fixture_name = report["fixture_name"]
    results = report["results"]
    n = len(results)

    print(f"\nFixture: {fixture_name}  (project: {project}, {n} candidates)\n")

    col_name = max(len(r["name"]) for r in results) if results else 30
    col_name = max(col_name, 26)
    hdr = (
        f"{'Candidate':<{col_name}}  {'Expected':<14}  {'Got':<14}  {'Δ':>3}  {'B':>1}"
    )
    print(hdr)
    print("─" * len(hdr))

    for r in results:
        d = r["delta"]
        d_str = f"{d:+d}" if d != 0 else " 0"
        b_str = "✓" if r["borderline"] else ""
        vn = f"  {r['variation_note']}" if r["variation_note"] else ""
        print(
            f"{r['name']:<{col_name}}  {r['expected']:<14}  {r['recommended']:<14}  {d_str:>3}  {b_str}{vn}"
        )

    over = [r for r in results if r["delta"] > 0]
    under = [r for r in results if r["delta"] < 0]
    exact = [r for r in results if r["delta"] == 0]
    mae = sum(abs(r["delta"]) for r in results) / n if n else 0.0

    print(f"\n── Summary {'─' * 50}")
    print(f"Over-engineering rate:    {len(over)}/{n} ({100*len(over)//n if n else 0}%)")
    print(f"Under-engineering rate:   {len(under)}/{n} ({100*len(under)//n if n else 0}%)")
    print(f"Exact-match rate:         {len(exact)}/{n} ({100*len(exact)//n if n else 0}%)")
    print(f"Mean absolute tier error: {mae:.2f}")

    if over:
        print("\nOver-engineered candidates:")
        for r in over:
            print(f"  {r['name']:<{col_name}}  {r['expected']} → {r['recommended']}  (+{r['delta']})")
    if under:
        print("\nUnder-engineered candidates:")
        for r in under:
            print(f"  {r['name']:<{col_name}}  {r['expected']} → {r['recommended']}  ({r['delta']})")


def _print_overall_summary(all_reports: list[dict[str, Any]]) -> None:
    all_results = [r for rep in all_reports for r in rep["results"]]
    n = len(all_results)
    if n == 0:
        return

    over = sum(1 for r in all_results if r["delta"] > 0)
    under = sum(1 for r in all_results if r["delta"] < 0)
    exact = sum(1 for r in all_results if r["delta"] == 0)
    mae = sum(abs(r["delta"]) for r in all_results) / n

    print(f"\n{'═' * 62}")
    print(f"OVERALL ({len(all_reports)} fixture{'s' if len(all_reports) != 1 else ''}, {n} candidates)")
    print(f"  Over-engineering rate:    {over}/{n} ({100*over//n}%)   ← headline metric")
    print(f"  Under-engineering rate:   {under}/{n} ({100*under//n}%)")
    print(f"  Exact-match rate:         {exact}/{n} ({100*exact//n}%)")
    print(f"  Mean absolute tier error: {mae:.2f}")
    print(f"{'═' * 62}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tier Analyst calibration eval. Always exits 0.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "fixtures",
        nargs="*",
        metavar="fixture.json",
        help="Fixture file(s) to evaluate. Defaults to all *.json in tier_calibration/fixtures/.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        metavar="N",
        help="Call Tier Analyst N times per candidate and report modal result (default: 1).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Skip real LLM calls; use stub recommendations to show output format.",
    )
    parser.add_argument(
        "--show-rationale",
        action="store_true",
        default=False,
        help="After the modal result, print one full Tier Analyst output per "
        "candidate (rationale, compared_to_next_tier_down, borderline_seams). "
        "Read-only investigation aid; costs one extra call per candidate.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.dry_run:
        print(_DRY_RUN_BANNER)
        llm_config: dict[str, Any] = {"model": "dry-run-stub", "api_key": "none"}
    else:
        print(_BANNER)
        llm_config = _build_llm_config()
        if args.runs > 1:
            print(f"Running each candidate {args.runs} times (reporting modal recommendation).")

    # Resolve fixture paths
    if args.fixtures:
        fixture_paths = [Path(p) for p in args.fixtures]
    else:
        fixture_paths = sorted(_DEFAULT_FIXTURES_DIR.glob("*.json"))

    if not fixture_paths:
        print(
            f"\nNo fixtures found in {_DEFAULT_FIXTURES_DIR}\n"
            "Add a .json file following evals/tier_calibration/schema.md",
            file=sys.stderr,
        )
        sys.exit(0)

    all_reports = []
    for path in fixture_paths:
        if not path.exists():
            print(f"\nWARNING: fixture not found: {path}", file=sys.stderr)
            continue
        fixture = _load_fixture(path)
        report = _evaluate_fixture(
            fixture=fixture,
            fixture_name=path.name,
            llm_config=llm_config,
            n_runs=args.runs,
            dry_run=args.dry_run,
            show_rationale=args.show_rationale,
        )
        _print_fixture_report(report)
        all_reports.append(report)

    if all_reports:
        _print_overall_summary(all_reports)

    # Always exit 0 — this is a measurement tool, not a gate.
    sys.exit(0)


if __name__ == "__main__":
    main()