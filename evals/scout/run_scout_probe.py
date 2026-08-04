#!/usr/bin/env python3
"""Scout output probe.

Feeds a project vision directly to Scout (bypassing Brainstormer/Agentifier) and
dumps the RAW candidate list Scout emits — name, scope, linked_vision_features,
and the full rough_description — plus a cross-run stability summary.

This is a read-only diagnostic. It answers questions the downstream tier report
cannot: how many candidates Scout produces from a vision (decomposition breadth),
whether it ever surfaces an orchestration/agent-level candidate, and exactly how
it words the description of any routing/coordination candidate.

Usage:
    uv run python evals/run_scout_probe.py [vision.json ...] [--runs N] [--dry-run]

A vision file is the INNER vision dict Scout consumes — e.g.:
    {"purpose": "...", "key_features_mvp": [{"Feature": {"description": "..."}}]}
Defaults to every *.json under evals/scout/visions/ when none given.

ALWAYS exits 0. This is a measurement tool, not a CI gate.

⚠  Real LLM calls are made unless --dry-run is passed. This costs tokens.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import textwrap
from collections import Counter
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup — allow importing spec4 without installing the package
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
# Sibling dev-tooling in this directory (phantom_link_check) must be importable
# regardless of how the probe is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from spec4.agentifier.scout import ScoutAgent, ScoutInput  # noqa: E402
import spec4.agentifier.scout as _scout_mod  # noqa: E402  (raw-edge interpose)

from phantom_link_check import (  # noqa: E402
    _resolve_feature_names,
    check_phantom_links,
    format_phantom_report,
    phantom_link_summary,
)
from scout_edge_metrics import (  # noqa: E402
    edge_metrics,
    edge_summary_row,
    format_edge_metrics,
)
from scout_granularity import (  # noqa: E402
    feature_fanout,
    fanout_summary_row,
    format_fanout,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_VISIONS_DIR = Path(__file__).resolve().parent / "visions"

_BANNER = """\
==============================================================
  SCOUT OUTPUT PROBE  —  real LLM calls, costs tokens
=============================================================="""

_DRY_RUN_BANNER = """\
==============================================================
  SCOUT OUTPUT PROBE  —  DRY-RUN (no LLM calls)
  Candidates are stubbed to show output format.
=============================================================="""


# ---------------------------------------------------------------------------
# llm_config sourcing (mirrors run_tier_eval.py)
# ---------------------------------------------------------------------------

def _build_llm_config() -> dict[str, Any]:
    """Build an llm_config dict from environment variables.

    Required: SPEC4_MODEL (e.g. claude-sonnet-4-6, gpt-4o-mini).
    Optional: SPEC4_API_KEY (overrides provider-specific env var),
              SPEC4_API_BASE (for non-default endpoints).
    LiteLLM picks up ANTHROPIC_API_KEY / OPENAI_API_KEY etc. automatically
    when SPEC4_API_KEY is not set.
    """
    model = os.environ.get("SPEC4_MODEL") or os.environ.get("LITELLM_MODEL", "")
    if not model:
        print(
            "\nERROR: SPEC4_MODEL is not set.\n"
            "Set it to a LiteLLM-compatible model identifier, e.g.:\n"
            "  export SPEC4_MODEL='claude-sonnet-4-6'\n",
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
# Running Scout
# ---------------------------------------------------------------------------

def _load_vision(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def _run_scout_once(
    agent: ScoutAgent, vision: dict[str, Any], llm_config: dict[str, Any]
) -> tuple[list[Any], list[tuple[str, list[str]]]]:
    """One Scout pass.

    Returns the Candidate objects together with a per-candidate raw edge
    snapshot ``(composed_under, requires)`` captured BEFORE the integrity pass
    ran — so the probe can measure what Scout actually emitted, including
    scattered singletons that ``_normalize_edges`` degrades to flat. The
    snapshot is aligned by index with the returned candidates.

    Captured by interposing the module-global ``_normalize_edges`` (its input is
    exactly the raw parsed candidate list). Runs are sequential, so this is
    race-free; it is a dev-measurement seam only and is always restored.
    """
    raw_edges: list[tuple[str, list[str]]] = []
    real_normalize = _scout_mod._normalize_edges

    def _capture(cands: list[Any]) -> list[Any]:
        raw_edges.clear()
        raw_edges.extend((c.composed_under, list(c.requires)) for c in cands)
        return real_normalize(cands)

    _scout_mod._normalize_edges = _capture
    try:
        out = await agent.run(ScoutInput(vision=vision, llm_config=llm_config))
    finally:
        _scout_mod._normalize_edges = real_normalize
    return out.candidates, raw_edges


_STUB_CANDIDATES = [
    {"name": "stub_feature_a", "scope": "feature", "linked_vision_features": ["A"],
     "rough_description": "(dry-run stub) Takes an input, returns an output."},
    {"name": "stub_feature_b", "scope": "sub_feature", "linked_vision_features": ["B"],
     "rough_description": "(dry-run stub) A second stubbed candidate."},
]


def _candidate_row(
    c: Any, edges: tuple[str, list[str]] | None = None
) -> dict[str, Any]:
    """Normalize a Candidate (or stub dict) to a plain dict for printing.

    ``edges`` carries the raw pre-normalization ``(composed_under, requires)``
    snapshot for a Candidate; when absent (stub dicts) the graph edges default
    empty so edge metrics score them zero.
    """
    if isinstance(c, dict):
        row = dict(c)
        row.setdefault("composed_under", "")
        row.setdefault("requires", [])
        return row
    composed_under, requires = (
        edges if edges is not None else (c.composed_under, list(c.requires))
    )
    return {
        "name": c.name,
        "scope": c.scope,
        "linked_vision_features": c.linked_vision_features,
        "rough_description": c.rough_description,
        "composed_under": composed_under,
        "requires": requires,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _print_run(run_idx: int, n_runs: int, cands: list[dict[str, Any]]) -> None:
    label = f"run {run_idx}/{n_runs}" if n_runs > 1 else "candidates"
    print(f"\n── Scout {label}: {len(cands)} candidate(s) {'─' * 30}")
    for c in cands:
        linked = ", ".join(c.get("linked_vision_features") or []) or "—"
        print(f"\n  • {c.get('name', '')}   [scope: {c.get('scope', '')}]   "
              f"[linked: {linked}]")
        desc = (c.get("rough_description") or "").strip()
        for line in textwrap.wrap(desc, width=88):
            print(f"      {line}")


def _print_stability(all_runs: list[list[dict[str, Any]]]) -> None:
    n_runs = len(all_runs)
    if n_runs <= 1:
        return
    name_counts: Counter[str] = Counter()
    for run in all_runs:
        for c in run:
            name_counts[c.get("name", "")] += 1
    counts = [len(r) for r in all_runs]
    print(f"\n── Cross-run summary ({n_runs} runs) {'─' * 34}")
    print(f"  Candidates per run: {counts}  "
          f"(min {min(counts)}, max {max(counts)}, avg {sum(counts) / n_runs:.1f})")
    print(f"  Distinct candidate names across runs: {len(name_counts)}")
    print("  Name  →  runs present:")
    for name, cnt in sorted(name_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        marker = "" if cnt == n_runs else "   (unstable)"
        print(f"    {cnt}/{n_runs}  {name}{marker}")


# ---------------------------------------------------------------------------
# Scoring layer (--score)
#
# Objective signals (over-generation count, reproducibility) are computed;
# the "did the coordinating candidate surface?" question is NOT faked with a
# boolean (substring-matching would match dozens of fragments). Instead the
# feature/cross_feature-scoped candidate names are surfaced for human judgment,
# and the sub_feature share is reported as a fragmentation number.
# ---------------------------------------------------------------------------

_LADDER = [
    "deterministic", "embeddings", "single_call", "rag", "tool_agent",
    "chained_calls", "planning_agent", "orchestrated_subagents",
    "multi_agent_collaboration",
]


def _infer_target_tier(vision_name: str) -> str:
    """Best-effort target tier from the filename (e.g. 05_tool_agent_orderly).

    Also accepts common short filename variants (e.g. ``orchestrated_subagent``,
    ``multi_agent``) that don't contain the full ladder name.
    """
    stem = vision_name.rsplit(".", 1)[0]
    matches = [t for t in _LADDER if t in stem]
    if matches:
        return max(matches, key=len)
    aliases = {
        "orchestrated_subagent": "orchestrated_subagents",
        "multi_agent": "multi_agent_collaboration",
    }
    for short, canon in aliases.items():
        if short in stem:
            return canon
    return "?"


def _name_sets(all_runs: list[list[dict[str, Any]]]) -> list[set[str]]:
    return [{c.get("name", "") for c in run} for run in all_runs]


def _reproducibility(sets: list[set[str]]) -> dict[str, Any]:
    """Stable-core count, total distinct, stability ratio, mean pairwise Jaccard."""
    union: set[str] = set().union(*sets) if sets else set()
    core: set[str] = set.intersection(*sets) if sets else set()
    total = len(union)
    ratio = len(core) / total if total else 0.0
    jacc: list[float] = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            u = sets[i] | sets[j]
            jacc.append(len(sets[i] & sets[j]) / len(u) if u else 0.0)
    mean_j = sum(jacc) / len(jacc) if jacc else float("nan")
    return {
        "stable_core": len(core),
        "total_distinct": total,
        "stability_ratio": ratio,
        "mean_jaccard": mean_j,
    }


def _scope_view(all_runs: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """Distinct-name scope breakdown + the feature/cross_feature names to inspect.

    A name's scope can vary across runs; take the coarsest scope ever seen, so a
    name that appeared even once as ``feature`` is credited as a whole-candidate.
    """
    rank = {"sub_feature": 0, "cross_feature": 1, "feature": 2}
    best: dict[str, str] = {}
    for run in all_runs:
        for c in run:
            nm = c.get("name", "")
            sc = c.get("scope", "")
            if nm not in best or rank.get(sc, -1) > rank.get(best[nm], -1):
                best[nm] = sc
    counts = Counter(best.values())
    return {
        "counts": counts,
        "feature_names": sorted(n for n, s in best.items() if s == "feature"),
        "cross_feature_names": sorted(n for n, s in best.items() if s == "cross_feature"),
    }


def _phantom_view(
    vision: dict[str, Any], all_runs: list[list[dict[str, Any]]]
) -> dict[str, Any]:
    """Layer-1 phantom-link stats over all candidate instances across runs.

    A phantom link is a ``linked_vision_features`` entry that names no feature in
    the vision — the crudest confabulation, caught deterministically. Near-misses
    (formatting drift that matches a real feature once normalized) are reported
    separately and never counted as phantoms.
    """
    flat = [c for run in all_runs for c in run]
    reports = check_phantom_links(flat, vision)
    summary = phantom_link_summary(reports)
    distinct_phantoms = sorted({link for r in reports for link in r.phantom_links})
    return {"summary": summary, "distinct_phantoms": distinct_phantoms, "reports": reports}


def _fanout_view(vision: dict[str, Any], all_runs: list[list[dict[str, Any]]]) -> Any:
    """Feature fan-out over all candidate instances across runs.

    Reuses the phantom checker's resolution: a candidate covers a real feature
    via an exact link (present in ``links``, not phantom, not a near-miss emitted
    token) or via a near-miss's resolved target(s). The real feature universe
    comes from the same resolver the phantom check uses.
    """
    real = _resolve_feature_names(vision)
    flat = [c for run in all_runs for c in run]
    reports = check_phantom_links(flat, vision)
    covered_per: list[list[str]] = []
    for r in reports:
        near_emitted = {emitted for (emitted, _) in r.near_miss_links}
        phantom = set(r.phantom_links)
        exact = [ln for ln in r.links if ln not in phantom and ln not in near_emitted]
        near = [rn for (_, reals) in r.near_miss_links for rn in reals]
        covered_per.append(exact + near)
    return feature_fanout(real, covered_per, n_runs=len(all_runs))


def _print_scorecard(
    vision_name: str,
    vision: dict[str, Any],
    all_runs: list[list[dict[str, Any]]],
    flood_threshold: int,
    show_grounding: bool = False,
) -> dict[str, Any]:
    tier = _infer_target_tier(vision_name)
    counts = [len(r) for r in all_runs]
    avg = sum(counts) / len(counts) if counts else 0.0
    rep = _reproducibility(_name_sets(all_runs))
    scope = _scope_view(all_runs)
    sc = scope["counts"]
    total = sum(sc.values()) or 1
    sub_pct = 100 * sc.get("sub_feature", 0) // total
    flood = "FLOOD" if avg > flood_threshold else "ok"
    phantom = _phantom_view(vision, all_runs)
    ps = phantom["summary"]
    fo = _fanout_view(vision, all_runs)

    print(f"\n── Scorecard: {vision_name}  (target: {tier}) {'─' * 14}")
    print(f"  Over-generation:  avg {avg:.1f}/run  "
          f"(per-run {counts}, threshold {flood_threshold})  → {flood}")
    if len(all_runs) > 1:
        print(f"  Reproducibility:  stable core {rep['stable_core']}/"
              f"{rep['total_distinct']} distinct  "
              f"(stability {rep['stability_ratio']:.2f}, "
              f"mean Jaccard {rep['mean_jaccard']:.2f})")
    else:
        print("  Reproducibility:  n/a (needs --runs > 1)")
    print(f"  Scope mix (distinct): feature {sc.get('feature', 0)}, "
          f"cross_feature {sc.get('cross_feature', 0)}, "
          f"sub_feature {sc.get('sub_feature', 0)}  ({sub_pct}% sub_feature)")
    wholes = scope["feature_names"] + [f"{n} (cross)" for n in scope["cross_feature_names"]]
    print("  Whole-candidates to inspect (feature/cross_feature scope):")
    if wholes:
        for n in wholes:
            print(f"    · {n}")
    else:
        print("    (none — every candidate is a sub_feature fragment)")

    for line in format_fanout(fo).splitlines():
        print(line)

    em = edge_metrics(all_runs)
    for line in format_edge_metrics(em).splitlines():
        print(line)

    print(f"  Phantom links:    {ps['phantom_flagged']}/{ps['candidates_with_links']} "
          f"flagged  (rate {ps['phantom_rate']:.2f}, {ps['total_phantom_links']} links; "
          f"{ps['near_miss_flagged']} near-miss)")
    if phantom["distinct_phantoms"]:
        print(f"    invented feature refs: {', '.join(phantom['distinct_phantoms'])}")
    if show_grounding:
        for line in format_phantom_report(phantom["reports"]).splitlines():
            print(f"    {line}")

    return {
        "vision": vision_name,
        "tier": tier,
        "avg": avg,
        "flood": flood,
        "stability": rep["stability_ratio"] if len(all_runs) > 1 else float("nan"),
        "sub_pct": sub_pct,
        "n_whole": len(scope["feature_names"]) + len(scope["cross_feature_names"]),
        "phantom_rate": ps["phantom_rate"],
        "n_phantom": len(phantom["distinct_phantoms"]),
        **fanout_summary_row(fo),
        **edge_summary_row(em),
    }


def _print_overall_scorecard(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    print("\n══════════════════════════════════════════════════════════════")
    print("OVERALL SCORECARD")
    print(f"  {'vision':<40} {'target tier':<26} {'avg':>5} {'stab':>5} "
          f"{'sub%':>5} {'fan':>5} {'unlnk%':>7} {'whole':>5} {'phan%':>6} "
          f"{'cu%':>5} {'hdls':>5} {'scat':>5}  flood")
    for r in rows:
        stab = " n/a" if r["stability"] != r["stability"] else f"{r['stability']:.2f}"
        fan = "  — " if r.get("mean_fanout") is None else f"{r['mean_fanout']:.1f}"
        unl = r.get("unlinked_share")
        unl_txt = "   — " if unl is None else f"{100 * unl:.0f}%"
        cu = r.get("cu_emit")
        cu_txt = "   — " if cu is None else f"{100 * cu:.0f}%"
        print(f"  {r['vision']:<40} {r['tier']:<26} {r['avg']:>5.1f} {stab:>5} "
              f"{r['sub_pct']:>4}% {fan:>5} {unl_txt:>7} {r['n_whole']:>5} "
              f"{100 * r['phantom_rate']:>5.0f}% {cu_txt:>5} "
              f"{r.get('headless', 0):>5} {r.get('scattered', 0):>5}  {r['flood']}")
    print("──────────────────────────────────────────────────────────────")
    print("  avg   = mean candidates/run (over-generation)")
    print("  stab  = stable-core / distinct names across runs (1.0 = reproducible)")
    print("  sub%  = share of distinct candidates scoped sub_feature (fragmentation)")
    print("  fan   = mean candidates per stated feature per run (shattering)")
    print("  unlnk%= share of candidate instances covering no stated feature")
    print("  whole = # feature/cross_feature-scoped candidates (inspect these by hand)")
    print("  phan% = share of linked candidate instances with an invented feature ref")
    print("  cu%   = share of candidate instances carrying a composed_under edge")
    print("  hdls  = headless groups (>=2 members, no head — Composer synthesizes)")
    print("  scat  = scattered singletons (1 member, no head — a degraded dangler)")
    print("══════════════════════════════════════════════════════════════")


def _probe_vision(
    vision: dict[str, Any],
    vision_name: str,
    llm_config: dict[str, Any],
    n_runs: int,
    dry_run: bool,
    score: bool = False,
    flood_threshold: int = 8,
    show_grounding: bool = False,
) -> dict[str, Any] | None:
    purpose = str(vision.get("purpose", "")).strip().replace("\n", " ")
    feats = vision.get("key_features_mvp", [])
    print("\n==============================================================")
    print(f"VISION: {vision_name}")
    if purpose:
        for line in textwrap.wrap(f"purpose: {purpose}", width=88):
            print(f"  {line}")
    print(f"  key_features_mvp: {len(feats)} feature(s)")

    agent = None if dry_run else ScoutAgent()
    all_runs: list[list[dict[str, Any]]] = []
    for i in range(1, n_runs + 1):
        if dry_run:
            cands = list(_STUB_CANDIDATES)
        else:
            raw_cands, raw_edges = asyncio.run(
                _run_scout_once(agent, vision, llm_config)
            )
            cands = [
                _candidate_row(c, e) for c, e in zip(raw_cands, raw_edges)
            ]
        all_runs.append(cands)
        _print_run(i, n_runs, cands)

    if score:
        # Scorecard supersedes the verbose per-name stability dump.
        return _print_scorecard(
            vision_name, vision, all_runs, flood_threshold, show_grounding
        )
    _print_stability(all_runs)
    if show_grounding:
        print()
        for line in format_phantom_report(
            _phantom_view(vision, all_runs)["reports"]
        ).splitlines():
            print(f"  {line}")
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scout output probe. Always exits 0.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "visions",
        nargs="*",
        metavar="vision.json",
        help="Vision file(s) to probe. Defaults to all *.json in "
        "scout/visions/.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        metavar="N",
        help="Run Scout N times per vision and report stability (default: 1). "
        "Scout is divergent/non-deterministic, so repeat passes reveal whether "
        "a given candidate (e.g. an orchestration candidate) surfaces reliably.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Skip real LLM calls; use stub candidates to show output format.",
    )
    parser.add_argument(
        "--score",
        action="store_true",
        default=False,
        help="Print a per-vision scorecard (over-generation, reproducibility, "
        "scope fragmentation, phantom-link rate, and the feature-scoped "
        "candidates to inspect) plus an overall table. Replaces the per-name "
        "stability dump.",
    )
    parser.add_argument(
        "--show-grounding",
        action="store_true",
        default=False,
        help="Dump the per-candidate Layer-1 phantom-link report (flagged "
        "candidates only) for each vision, in addition to the summary line.",
    )
    parser.add_argument(
        "--flood-threshold",
        type=int,
        default=8,
        metavar="N",
        help="Avg candidates/run above this is flagged FLOOD in --score output "
        "(default: 8). A reference knob, not ground truth.",
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
            print(f"Running each vision {args.runs} times (reporting stability).")

    if args.visions:
        vision_paths = [Path(p) for p in args.visions]
    else:
        vision_paths = sorted(_DEFAULT_VISIONS_DIR.glob("*.json"))

    if not vision_paths:
        print(
            f"\nNo vision files found in {_DEFAULT_VISIONS_DIR}",
            file=sys.stderr,
        )
        sys.exit(0)

    rows: list[dict[str, Any]] = []
    for path in vision_paths:
        if not path.exists():
            print(f"\nWARNING: vision not found: {path}", file=sys.stderr)
            continue
        vision = _load_vision(path)
        row = _probe_vision(
            vision=vision,
            vision_name=path.name,
            llm_config=llm_config,
            n_runs=args.runs,
            dry_run=args.dry_run,
            score=args.score,
            flood_threshold=args.flood_threshold,
            show_grounding=args.show_grounding,
        )
        if row is not None:
            rows.append(row)

    if args.score:
        _print_overall_scorecard(rows)

    # Always exit 0 — this is a measurement tool, not a gate.
    sys.exit(0)


if __name__ == "__main__":
    main()