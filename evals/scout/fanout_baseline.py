"""Offline fan-out baseline over saved Scout draw artifacts (dev tooling).

No LLM. Runs the existing feature-fanout metric (:mod:`scout_granularity`) on
saved draw artifacts (``vision.json`` + ``ai_features.json``) so the
candidates-per-vision-feature signal can be baselined on fixed draws without a
live Scout draw. This is the offline entry point for the anti-fragmentation
lever's before/after measurement (D-CF6); it adds no new metric, only a loader.

Surfaced candidates are the non-infrastructure feature nodes. Injected infra
(``kind == "infrastructure"``) is excluded: it is not surfaced by Scout and
links to no vision feature, so counting it would dilute the fan-out signal.

Vision-feature name matching is exact against the vision's ``key_features_mvp``
keys. For draws whose ``linked_vision_features`` drift in formatting, resolve
them through ``phantom_link_check`` first and pass resolved names in; the saved
draws used for the baseline link exactly, so exact matching is sufficient here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scout_granularity import (  # noqa: E402 (evals/ is a script dir, not a package)
    Fanout,
    feature_fanout,
    format_fanout,
)


def vision_feature_names(vision: dict[str, Any]) -> list[str]:
    """Stated MVP feature names — the keys under ``key_features_mvp``.

    Accepts either the full ``{"vision_statement": {...}}`` envelope or the
    inner vision object directly.
    """
    root = vision.get("vision_statement", vision)
    inner = root.get("vision", root)
    names: list[str] = []
    for entry in inner.get("key_features_mvp", []):
        if isinstance(entry, dict):
            names.extend(entry.keys())
        elif isinstance(entry, str):
            names.append(entry)
    return names


def surfaced_candidates(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The nodes Scout actually surfaced — everything but injected infra."""
    return [f for f in features if f.get("kind") != "infrastructure"]


def fanout_for_draw(vision: dict[str, Any], features: list[dict[str, Any]]) -> Fanout:
    """Fan-out for a single saved draw (one run)."""
    names = vision_feature_names(vision)
    covered = [
        list(c.get("linked_vision_features", []) or [])
        for c in surfaced_candidates(features)
    ]
    return feature_fanout(names, covered, n_runs=1)


def _load(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())


def _features_list(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        return raw.get("ai_features", [])
    return raw


def draw_fanout(vision_path: str | Path, features_path: str | Path) -> Fanout:
    """Load a draw's artifacts from disk and compute its fan-out."""
    return fanout_for_draw(_load(vision_path), _features_list(_load(features_path)))


def _per_feature_block(fo: Fanout) -> str:
    """Sorted candidates-per-feature listing — the cluster view (D-CF6)."""
    rows = sorted(fo.per_feature.items(), key=lambda kv: (-kv[1], kv[0]))
    return "\n".join(f"      {c:>2}  {feat}" for feat, c in rows)


def _draw_report(label: str, fo: Fanout) -> str:
    return (
        f"  {label}\n"
        f"{format_fanout(fo)}\n"
        f"    candidates per vision feature:\n"
        f"{_per_feature_block(fo)}"
    )


def _find_draw(directory: Path) -> tuple[Path, Path] | None:
    vision = directory / "vision.json"
    features = directory / "ai_features.json"
    if vision.exists() and features.exists():
        return vision, features
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fan-out baseline over saved Scout draws "
        "(each dir must hold vision.json + ai_features.json)."
    )
    parser.add_argument(
        "draw_dirs",
        nargs="+",
        help="One or more draw directories; the dir name is used as the label.",
    )
    args = parser.parse_args(argv)

    rows: list[tuple[str, Fanout]] = []
    print("Feature fan-out baseline (candidates per stated vision feature)\n")
    for d in args.draw_dirs:
        directory = Path(d)
        found = _find_draw(directory)
        if found is None:
            print(f"  {directory.name}: missing vision.json or ai_features.json — skipped\n")
            continue
        fo = draw_fanout(*found)
        rows.append((directory.name, fo))
        print(_draw_report(directory.name, fo))
        print()

    if rows:
        print("  Summary")
        print(f"    {'draw':<16}{'mean':>7}{'max':>7}  worst-feature")
        for label, fo in rows:
            mx = fo.max_fanout
            mean = fo.mean_fanout or 0.0
            mx_val = mx[1] if mx else 0.0
            mx_feat = mx[0] if mx else "—"
            print(f"    {label:<16}{mean:>7.1f}{mx_val:>7.1f}  {mx_feat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())