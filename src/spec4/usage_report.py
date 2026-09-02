"""Per-agent token and cost table for a round's ``usage.json``.

``spec4-usage [WORKING_DIR] [--round N]`` prints one row per planning agent
(agent, calls, input, output, cached, models used, computed cost) plus a totals
row. This is the read side of :func:`spec4.project_manager.save_usage` and the
seed for the cost page: tokens are what the providers reported, the cost column
is LiteLLM's advisory estimate.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from spec4 import project_manager

_COLUMNS = ("agent", "calls", "input", "output", "cached", "models", "cost_usd")


def _fmt_int(value: Any) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return "-"


def _fmt_cost(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.4f}"
    return "-"


def _fmt_models(models: Any) -> str:
    if not isinstance(models, list) or not models:
        return "-"
    parts = []
    for pair in models:
        if not isinstance(pair, dict):
            continue
        model = pair.get("model") or "?"
        provider = pair.get("provider")
        parts.append(f"{model} ({provider})" if provider else str(model))
    return ", ".join(parts) or "-"


def _rows(data: dict[str, Any]) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    agents = data.get("agents")
    if isinstance(agents, dict):
        for name in sorted(agents):
            entry = agents[name]
            if not isinstance(entry, dict):
                continue
            rows.append(
                (
                    str(name),
                    _fmt_int(entry.get("calls")),
                    _fmt_int(entry.get("input_tokens")),
                    _fmt_int(entry.get("output_tokens")),
                    _fmt_int(entry.get("cached_input_tokens")),
                    _fmt_models(entry.get("models")),
                    _fmt_cost(entry.get("computed_cost_usd")),
                )
            )
    totals = data.get("totals")
    if isinstance(totals, dict):
        rows.append(
            (
                "TOTAL",
                _fmt_int(totals.get("calls")),
                _fmt_int(totals.get("input_tokens")),
                _fmt_int(totals.get("output_tokens")),
                _fmt_int(totals.get("cached_input_tokens")),
                "",
                _fmt_cost(totals.get("computed_cost_usd")),
            )
        )
    return rows


def render_usage_table(data: dict[str, Any]) -> str:
    """Render ``usage.json`` content as an aligned plain-text table."""
    rows = _rows(data)
    widths = [len(c) for c in _COLUMNS]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    right = {1, 2, 3, 4, 6}

    def _line(cells: tuple[str, ...]) -> str:
        return "  ".join(
            cell.rjust(widths[i]) if i in right else cell.ljust(widths[i])
            for i, cell in enumerate(cells)
        ).rstrip()

    lines = [
        f"Round {data.get('round', '?')}  (updated {data.get('updated_at', '?')})",
        _line(_COLUMNS),
        _line(tuple("-" * w for w in widths)),
    ]
    lines.extend(_line(row) for row in rows)
    missing = 0
    agents = data.get("agents")
    if isinstance(agents, dict):
        for entry in agents.values():
            if isinstance(entry, dict):
                value = entry.get("calls_missing_usage")
                if isinstance(value, int) and not isinstance(value, bool):
                    missing += value
    if missing:
        lines.append(
            f"note: {missing} call(s) returned no usage; their tokens are not counted."
        )
    notes = data.get("notes")
    if isinstance(notes, dict) and notes.get("computed_cost_source"):
        lines.append(f"cost_usd: {notes['computed_cost_source']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="spec4-usage",
        description="Print the per-agent LLM usage table for a Spec4 round.",
    )
    parser.add_argument(
        "working_dir",
        nargs="?",
        default=".",
        help="project directory holding .spec4/ (default: current directory)",
    )
    parser.add_argument(
        "--round",
        type=int,
        default=None,
        help="round number N for .spec4/vN/usage.json (default: latest round)",
    )
    args = parser.parse_args(argv)

    version = args.round
    if version is None:
        version = project_manager.latest_phase_version(args.working_dir)
        if version is None:
            print(
                f"No .spec4/v*/ round found under {args.working_dir}",
                file=sys.stderr,
            )
            return 1
    data = project_manager.load_usage(args.working_dir, version)
    if data is None:
        path = project_manager.get_version_dir(args.working_dir, version)
        print(
            f"No readable {project_manager.USAGE_FILENAME} in {path}", file=sys.stderr
        )
        return 1
    print(render_usage_table(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
