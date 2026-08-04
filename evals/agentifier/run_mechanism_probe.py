#!/usr/bin/env python3
"""Mechanism probe runner.

Feeds each probe vision (``evals/agentifier/probe_visions/*/``) through the
real Agentifier sub-agent pipeline headlessly, writes the resulting
``ai_features.json`` under ``<vision_dir>/runs/<label>/``, and scores every
produced document against the ``expectations.json`` beside the vision.

Pipeline stages, mirroring production (``spec4.agentifier.agentifier``):

    Scout -> Linker -> Composer -> select ALL (panel closure) ->
    Tier Analyst per candidate -> auto-accept recommended tiers ->
    Spec Drafter per entry -> _build_ai_features -> infra expansion

Deliberately skipped, with why it doesn't bias the mechanism measurement:
- the interactive catalog conversation (tiers are auto-accepted, so the
  Tier Analyst's recommendation is measured raw, undiluted by a second model
  pass arguing with the developer);
- reference_verifier (needs a web-search provider; touches only
  ``references``);
- cross-cutting analysis and priority review (write ``cross_cutting`` and
  ordering, never per-feature ``mechanisms`` or ``tier``);
- requires-reconciliation (pure edge-direction pass, not scored).

Usage:
    uv run python evals/agentifier/run_mechanism_probe.py \
        [vision_dir ...] [--runs N] [--label NAME] [--dry-run] [--score-only]

Typical impact measurement:
    ... run_mechanism_probe.py --label before --runs 3
    (make the prompt change)
    ... run_mechanism_probe.py --label after --runs 3
    ... run_mechanism_probe.py --score-only --label before
    ... run_mechanism_probe.py --score-only --label after

``--score-only`` also scores a ``.spec4/v0/ai_features.json`` saved by a real
interactive app session against the probe project directory, when one exists.

ALWAYS exits 0. This is a measurement tool, not a CI gate.

WARNING: Real LLM calls are made unless --dry-run or --score-only is passed.
A full sweep is roughly (1 Scout + 1 Linker + 1 Composer + ~2N Tier/Spec
calls) per vision, times --runs.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup — allow importing spec4 and sibling modules without installing
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from spec4.agentifier.agentifier import (  # noqa: E402
    _build_ai_features,
    _call_composer,
    _call_linker,
    _call_scout,
    _call_tier_analyst,
    _candidates_to_dicts,
    _analyses_to_dicts,
    _expand_infrastructure,
)
from spec4.agentifier.linker import apply_overlay  # noqa: E402
from spec4.agentifier.panel_closure import close_selection  # noqa: E402
from spec4.agentifier.pattern_loader import load_patterns  # noqa: E402
from spec4.agentifier.spec_drafter import (  # noqa: E402
    SpecDrafterAgent,
    SpecDrafterInput,
)
from spec4.agents._utils import _extract_json_block  # noqa: E402

from mechanism_scoring import (  # noqa: E402  (evals/ is a script dir)
    aggregate,
    format_overall,
    format_vision_score,
    score_vision,
)

_DEFAULT_VISIONS_DIR = Path(__file__).resolve().parent / "probe_visions"

_BANNER = """\
==============================================================
  MECHANISM PROBE  —  real LLM calls, costs tokens
=============================================================="""

_DRY_RUN_BANNER = """\
==============================================================
  MECHANISM PROBE  —  DRY-RUN (no LLM calls)
  ai_features are stubbed to show the report format only.
=============================================================="""


# ---------------------------------------------------------------------------
# llm_config sourcing (same contract as run_tier_eval.py)
# ---------------------------------------------------------------------------


def _build_llm_config() -> dict[str, Any]:
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
    if os.environ.get("SPEC4_API_KEY"):
        cfg["api_key"] = os.environ["SPEC4_API_KEY"]
    if os.environ.get("SPEC4_API_BASE"):
        cfg["api_base"] = os.environ["SPEC4_API_BASE"]
    return cfg


# ---------------------------------------------------------------------------
# Headless pipeline
# ---------------------------------------------------------------------------


def _draft_spec(
    entry: dict[str, Any], llm_config: dict[str, Any]
) -> dict[str, Any]:
    """One Spec Drafter call with production's single unreadable-output retry."""
    tiers, mechanisms = load_patterns()
    spec_input = SpecDrafterInput(
        catalog_entry=entry,
        llm_config=llm_config,
        tier_patterns=tiers,
        mechanism_patterns=mechanisms,
    )
    agent = SpecDrafterAgent()

    async def _collect() -> str:
        text = ""
        async for chunk in agent.stream(spec_input):
            text += chunk
        return text

    for attempt in (1, 2):  # mirrors D-AF6 in _draft_spec
        text = asyncio.run(_collect())
        spec = _extract_json_block(text)
        if not spec:
            try:
                spec = json.loads(text.strip())
            except Exception:
                spec = None
        if isinstance(spec, dict):
            return spec
        if attempt == 1:
            print("      spec unreadable — retrying once…", flush=True)
    print("      spec unreadable after retry — recorded as empty", flush=True)
    return {}


def run_pipeline(
    vision: dict[str, Any], llm_config: dict[str, Any]
) -> dict[str, Any]:
    """Vision -> ai_features document, through the production sub-agents."""
    print("    Scout…", flush=True)
    scout_out = _call_scout(vision, None, llm_config)
    candidates = scout_out.candidates
    if not candidates:
        print("    Scout surfaced no candidates.", flush=True)
        return {"ai_features": []}

    if len(candidates) >= 2:
        print("    Linker…", flush=True)
        try:
            candidates = apply_overlay(
                candidates, _call_linker(candidates, vision, llm_config).overlay
            )
        except Exception as exc:  # production proceeds edgeless
            print(f"    Linker failed ({exc}); proceeding edgeless", flush=True)

    print("    Composer…", flush=True)
    try:
        candidates = _call_composer(candidates, vision, llm_config).candidates
    except Exception as exc:  # production keeps Scout output unchanged
        print(f"    Composer failed ({exc}); using Scout output", flush=True)

    # Breadth panel stand-in: the probe selects everything, then applies the
    # same closure production applies to the developer's checked set.
    closure = close_selection(candidates, [c.name for c in candidates])
    survivors = [c for c in candidates if c.name in closure.selected]

    analyses = []
    for i, cand in enumerate(survivors, 1):
        print(
            f"    Tier Analyst {i}/{len(survivors)}: {cand.name}", flush=True
        )
        analyses.append(_call_tier_analyst(cand, llm_config, None))

    # Auto-accept every recommendation — the catalog-conversation stand-in.
    # tier_decision_rationale stays empty exactly as production records an
    # accepted recommendation.
    catalog_entries = [
        {
            "name": c.name,
            "scope": c.scope,
            "rough_description": c.rough_description,
            "tier_recommendation": a.recommended_tier,
            "tier_decision": a.recommended_tier,
            "tier_decision_rationale": "",
        }
        for c, a in zip(survivors, analyses)
    ]

    spec_results = []
    for i, entry in enumerate(catalog_entries, 1):
        print(
            f"    Spec Drafter {i}/{len(catalog_entries)}: {entry['name']}",
            flush=True,
        )
        spec_results.append(_draft_spec(entry, llm_config))

    features = _build_ai_features(
        catalog_entries,
        spec_results,
        _candidates_to_dicts(survivors),
        _analyses_to_dicts(analyses, survivors),
        None,
    )
    return {"ai_features": _expand_infrastructure(features, None)}


# ---------------------------------------------------------------------------
# Dry-run stub
# ---------------------------------------------------------------------------


def _stub_ai_features(expectations: dict[str, Any]) -> dict[str, Any]:
    """Fabricate a near-perfect document so the report format is visible.

    The first expectation feature (always a positive case in the fixture
    design) drops its required mechanisms, showing what a miss looks like
    without spending tokens.
    """
    exps = expectations.get("expectations") or []
    entries = []
    for i, exp in enumerate(exps):
        required = list(exp.get("mechanisms_required") or [])
        if i == 0:
            required = []
        tiers = exp.get("expected_tiers") or ["single_call"]
        entries.append(
            {
                "name": f"{exp['vision_feature']}_stub",
                "kind": "feature",
                "linked_vision_features": [exp["vision_feature"]],
                "tier": tiers[0],
                "mechanisms": [
                    {"name": m, "rationale": "stub", "configuration": {}}
                    for m in required
                ],
            }
        )
    return {"ai_features": entries}


# ---------------------------------------------------------------------------
# File discovery and orchestration
# ---------------------------------------------------------------------------


def _vision_dirs(args_dirs: list[str]) -> list[Path]:
    if args_dirs:
        return [Path(d) for d in args_dirs]
    return sorted(
        p
        for p in _DEFAULT_VISIONS_DIR.iterdir()
        if p.is_dir() and (p / "expectations.json").exists()
    )


def _score_files(vision_dir: Path, label: str | None) -> list[Path]:
    """ai_features documents to score for --score-only, oldest first."""
    runs_root = vision_dir / "runs"
    files: list[Path] = []
    if runs_root.is_dir():
        for run_dir in sorted(runs_root.iterdir()):
            if run_dir.is_dir() and (label is None or run_dir.name == label):
                files.extend(sorted(run_dir.glob("ai_features*.json")))
    app_saved = vision_dir / ".spec4" / "v0" / "ai_features.json"
    if label is None and app_saved.exists():
        files.append(app_saved)
    return files


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dirs", nargs="*", help="probe vision directories")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument(
        "--label",
        default=None,
        help="run-set name (default: UTC timestamp); with --score-only, "
        "limits scoring to that run set",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--score-only",
        action="store_true",
        help="score existing runs/<label>/ai_features*.json (and any "
        ".spec4/v0/ai_features.json) without making LLM calls",
    )
    args = parser.parse_args()

    print(_DRY_RUN_BANNER if args.dry_run else _BANNER)
    dirs = _vision_dirs(args.dirs)
    if not dirs:
        print("No probe vision directories found.")
        return

    llm_config: dict[str, Any] = {}
    if not args.dry_run and not args.score_only:
        llm_config = _build_llm_config()
        print(f"Model: {llm_config['model']}")

    scores = []
    for vision_dir in dirs:
        expectations = _load_json(vision_dir / "expectations.json")
        print(f"\n── {vision_dir.name} " + "─" * max(0, 40 - len(vision_dir.name)))

        docs: list[tuple[str, dict[str, Any]]] = []
        if args.score_only:
            files = _score_files(vision_dir, args.label)
            if not files:
                print("  no ai_features documents found to score")
                continue
            docs = [(str(p.relative_to(vision_dir)), _load_json(p)) for p in files]
        elif args.dry_run:
            docs = [("dry-run stub", _stub_ai_features(expectations))]
        else:
            label = args.label or datetime.datetime.now(
                datetime.timezone.utc
            ).strftime("%Y%m%dT%H%M%SZ")
            out_dir = vision_dir / "runs" / label
            out_dir.mkdir(parents=True, exist_ok=True)
            vision = _load_json(vision_dir / ".spec4" / "v0" / "vision.json")
            for i in range(1, args.runs + 1):
                print(f"  run {i}/{args.runs}:")
                try:
                    doc = run_pipeline(vision, llm_config)
                except Exception as exc:
                    print(f"  run {i} failed: {exc}", flush=True)
                    continue
                out = out_dir / f"ai_features_run{i}.json"
                out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
                print(f"  wrote {out.relative_to(vision_dir)}")
                docs.append((str(out.relative_to(vision_dir)), doc))
            meta = {
                "model": llm_config.get("model", ""),
                "completed_runs": len(docs),
                "requested_runs": args.runs,
            }
            (out_dir / "meta.json").write_text(
                json.dumps(meta, indent=2), encoding="utf-8"
            )

        for source, doc in docs:
            score = score_vision(expectations, doc)
            scores.append(score)
            print(f"\n  [{source}]")
            print(format_vision_score(score))

    if scores:
        print()
        print(format_overall(aggregate(scores)))
    print(
        "\nCompare labels with two --score-only invocations "
        "(e.g. --label before, --label after) and diff the OVERALL blocks."
    )


if __name__ == "__main__":
    main()
