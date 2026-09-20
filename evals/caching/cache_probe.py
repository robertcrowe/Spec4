"""Read-only prompt-cache probe over recorded ``.spec4/v*/usage.json`` files.

    uv run python evals/caching/cache_probe.py <project_dir> [<project_dir> ...] [--json]
    uv run python evals/caching/cache_probe.py --compare <before_dir> <after_dir> [--json]

Reads the per-call ``history`` records that ``project_manager._usage.save_usage``
writes (shape: ``src/spec4/llm.py::_record_usage``), never the rollups. Makes no
LLM call and writes nothing. Null-safe: a figure no call reported is ``None`` in
JSON and ``-`` in the table, never 0.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

TTL_SECONDS = 300
MISSING = "-"


def _int(value: Any) -> int | None:
    """Same guard as ``_usage._usage_int``: bools and non-ints are not counts."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def cache_read(call: dict[str, Any]) -> int | None:
    """Cache-read tokens for one call: Anthropic's field first, else OpenAI's."""
    read = _int(call.get("cache_read_input_tokens"))
    return read if read is not None else _int(call.get("cached_tokens"))


def _sum(values: list[int | float]) -> int | float | None:
    return sum(values) if values else None


def _timestamp(call: dict[str, Any]) -> datetime | None:
    raw = call.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _timeline(history: list[dict[str, Any]]) -> list[tuple[datetime, float | None]]:
    """(start, duration_s) per call with a usable timestamp, in start order."""
    rows = [(t, _float(c.get("duration_s"))) for c in history if (t := _timestamp(c))]
    try:
        return sorted(rows, key=lambda r: r[0])
    except TypeError:  # naive and aware timestamps in one history
        return []


def _gaps_and_clock_skew(
    history: list[dict[str, Any]],
) -> tuple[list[float], int | None]:
    """Start-to-start gaps in seconds, and how many calls carry a wall-clock
    ``timestamp`` earlier than the preceding call's monotonic finish.

    The comparison crosses two clocks -- see ``clock_skew`` in the README -- so
    a non-zero count is a timing artifact, not evidence of concurrency. None
    with no pair to compare.
    """
    line = _timeline(history)
    gaps = [(b[0] - a[0]).total_seconds() for a, b in zip(line, line[1:])]
    if not gaps:
        return gaps, None
    clock_skew = sum(
        1
        for a, b in zip(line, line[1:])
        if a[1] is not None and (b[0] - a[0]).total_seconds() < a[1]
    )
    return gaps, clock_skew


def _both_differ(history: list[dict[str, Any]]) -> int | None:
    """Records carrying both cache-read fields with unequal values. None when no
    record carried both, so "never comparable" does not read as "always equal"."""
    pairs = [
        (r, c)
        for call in history
        if (r := _int(call.get("cache_read_input_tokens"))) is not None
        and (c := _int(call.get("cached_tokens"))) is not None
    ]
    return sum(1 for r, c in pairs if r != c) if pairs else None


def agent_stats(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Every figure the probe reports for one agent's call history."""
    prompt = [v for c in history if (v := _int(c.get("prompt_tokens"))) is not None]
    reads = [v for c in history if (v := cache_read(c)) is not None]
    creations = [
        v
        for c in history
        if (v := _int(c.get("cache_creation_input_tokens"))) is not None
    ]
    costs = [
        v for c in history if (v := _float(c.get("computed_cost_usd"))) is not None
    ]
    prompt_sum = _sum(prompt)
    read_sum = _sum(reads)
    models: list[list[str | None]] = []
    for call in history:
        pair = [call.get("model"), call.get("provider")]
        if pair not in models:
            models.append(pair)
    gaps, clock_skew = _gaps_and_clock_skew(history)
    return {
        "calls": len(history),
        "calls_missing_usage": sum(1 for c in history if c.get("usage_missing")),
        "prompt_tokens": prompt_sum,
        "cache_read": read_sum,
        "cache_creation": _sum(creations),
        "calls_with_read": sum(1 for v in reads if v > 0) if reads else None,
        "read_ratio": (read_sum / prompt_sum)
        if read_sum is not None and prompt_sum
        else None,
        "computed_cost_usd": round(cost, 8)
        if (cost := _sum(costs)) is not None
        else None,
        "models": models,
        "gap_count": len(gaps),
        "gap_median_s": statistics.median(gaps) if gaps else None,
        "gap_max_s": max(gaps) if gaps else None,
        "min_gap_s": min(gaps) if gaps else None,
        "clock_skew": clock_skew,
        "both_differ": _both_differ(history),
        "gaps_over_ttl": sum(1 for g in gaps if g > TTL_SECONDS) if gaps else None,
    }


def find_usage_files(project_dir: Path) -> list[Path]:
    """Every ``.spec4/v*/usage.json`` under the project, in version order."""

    def version(path: Path) -> tuple[int, str]:
        digits = path.parent.name[1:]
        return (int(digits) if digits.isdigit() else 0, path.parent.name)

    return sorted((project_dir / ".spec4").glob("v*/usage.json"), key=version)


def load_histories(
    path: Path,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """``({agent: per-call history}, {agent: rollup parent})`` from one usage.json.

    Records are grouped by their own ``agent`` field; the file's rollup key is
    used only for a record with no usable one. A parent is listed only for an
    agent whose rollup key differs from its name. Empty when unreadable.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, {}
    agents = data.get("agents") if isinstance(data, dict) else None
    if not isinstance(agents, dict):
        return {}, {}
    out: dict[str, list[dict[str, Any]]] = {}
    parents: dict[str, str] = {}
    for rollup, entry in agents.items():
        history = entry.get("history") if isinstance(entry, dict) else None
        for call in history or []:
            if not isinstance(call, dict):
                continue
            raw = call.get("agent")
            name = raw if isinstance(raw, str) and raw else str(rollup)
            out.setdefault(name, []).append(call)
            if name != str(rollup):
                parents.setdefault(name, str(rollup))
    return out, parents


def _row_order(name: str, parents: dict[str, str]) -> tuple[str, int, str]:
    """Sub-agents sort directly under their parent; the parent's own row first."""
    group = parents.get(name, name)
    return (group, 0 if group == name else 1, name)


def report_file(path: Path) -> dict[str, Any]:
    histories, parents = load_histories(path)
    every = [call for history in histories.values() for call in history]
    total = agent_stats(every)
    for key in (
        "gap_count", "gap_median_s", "gap_max_s", "min_gap_s", "gaps_over_ttl", "clock_skew",
    ):  # fmt: skip
        total[key] = None  # gaps are per agent; interleaved agents would mix them
    names = sorted(histories, key=lambda n: _row_order(n, parents))
    return {
        "file": str(path),
        "agents": {
            n: {**agent_stats(histories[n]), "parent": parents.get(n)} for n in names
        },
        "total": total,
    }


def report_projects(project_dirs: list[Path]) -> list[dict[str, Any]]:
    return [
        report_file(usage)
        for project in project_dirs
        for usage in find_usage_files(project)
    ]


def dir_agent_stats(project_dir: Path) -> dict[str, dict[str, Any]]:
    """Per-agent stats with each agent's histories pooled across all rounds."""
    pooled: dict[str, list[dict[str, Any]]] = {}
    for usage in find_usage_files(project_dir):
        for name, history in load_histories(usage)[0].items():
            pooled.setdefault(name, []).extend(history)
    return {name: agent_stats(h) for name, h in sorted(pooled.items())}


def _delta(before: float | None, after: float | None) -> float | None:
    if before is None and after is None:
        return None
    return (after or 0) - (before or 0)


def compare(before_dir: Path, after_dir: Path) -> dict[str, Any]:
    before = dir_agent_stats(before_dir)
    after = dir_agent_stats(after_dir)
    rows: dict[str, dict[str, Any]] = {}
    for name in sorted(set(before) | set(after)):
        b, a = before.get(name), after.get(name)
        row: dict[str, Any] = {}
        for key in ("cache_read", "cache_creation", "computed_cost_usd"):
            bv = b[key] if b else None
            av = a[key] if a else None
            row[key] = {"before": bv, "after": av, "delta": _delta(bv, av)}
        rows[name] = row
    return {"before": str(before_dir), "after": str(after_dir), "agents": rows}


# --- rendering --------------------------------------------------------------


def _fmt(value: float | None, kind: str = "int") -> str:
    if value is None:
        return MISSING
    if kind == "ratio":
        return f"{value:.1%}"
    if kind == "usd":
        return f"${value:.4f}"
    if kind == "sec":
        return f"{value:.1f}"
    return f"{int(value):,}"


def _models(pairs: list[list[str | None]]) -> str:
    return "; ".join(f"{m or MISSING}/{p or MISSING}" for m, p in pairs) or MISSING


def _table(header: list[str], rows: list[list[str]], left: int = 1) -> str:
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]

    def line(cells: list[str]) -> str:
        return "  ".join(
            c.ljust(widths[i]) if i < left else c.rjust(widths[i])
            for i, c in enumerate(cells)
        )

    return "\n".join(
        [line(header), line(["-" * w for w in widths]), *(line(r) for r in rows)]
    )


def render_file(rep: dict[str, Any]) -> str:
    header = [
        "agent", "parent", "calls", "no_usage", "prompt", "read", "creation",
        "w/read", "read%", "cost", "min_gap_s", "gap_med_s", "gap_max_s", f">{TTL_SECONDS}s", "clock_skew", "both_differ", "models",
    ]  # fmt: skip
    rows = []
    for name, s in [*rep["agents"].items(), ("TOTAL", rep["total"])]:
        rows.append([
            name, s.get("parent") or MISSING, _fmt(s["calls"]),
            _fmt(s["calls_missing_usage"]), _fmt(s["prompt_tokens"]),
            _fmt(s["cache_read"]), _fmt(s["cache_creation"]),
            _fmt(s["calls_with_read"]), _fmt(s["read_ratio"], "ratio"),
            _fmt(s["computed_cost_usd"], "usd"), _fmt(s["min_gap_s"], "sec"),
            _fmt(s["gap_median_s"], "sec"), _fmt(s["gap_max_s"], "sec"),
            _fmt(s["gaps_over_ttl"]), _fmt(s["clock_skew"]), _fmt(s["both_differ"]),
            _models(s["models"]),
        ])  # fmt: skip
    return f"== {rep['file']}\n{_table(header, rows, left=2)}"


def render_compare(cmp: dict[str, Any]) -> str:
    header = ["agent"]
    for key in ("cache_read", "cache_creation", "cost_usd"):
        header += [f"{key}_before", f"{key}_after", f"{key}_delta"]
    rows = []
    for name, row in cmp["agents"].items():
        cells = [name]
        for key, kind in (
            ("cache_read", "int"),
            ("cache_creation", "int"),
            ("computed_cost_usd", "usd"),
        ):
            cells += [_fmt(row[key][p], kind) for p in ("before", "after", "delta")]
        rows.append(cells)
    return (
        f"== before: {cmp['before']}\n== after:  {cmp['after']}\n{_table(header, rows)}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prompt-cache probe over usage.json files."
    )
    parser.add_argument("projects", nargs="*", type=Path, help="project directories")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BEFORE", "AFTER"))
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.compare:
        cmp = compare(*args.compare)
        print(json.dumps(cmp, indent=2) if args.json else render_compare(cmp))
        return 0
    if not args.projects:
        parser.error("give at least one project_dir, or --compare BEFORE AFTER")
    reports = report_projects(args.projects)
    if not reports:
        print("no .spec4/v*/usage.json found", file=sys.stderr)
        return 1
    print(
        json.dumps(reports, indent=2)
        if args.json
        else "\n\n".join(map(render_file, reports))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
