"""The per-round LLM usage log and the cost rollup built from it.

Split out of :mod:`spec4.project_manager` in cleanup Phase 4b. That module
re-exports ``cost_summary``, ``load_usage``, ``round_cost``, ``save_usage``,
``summarize_usage``, ``unpriced_calls``, ``usage_totals``, ``USAGE_FILENAME`` and
``_USAGE_ROLLUP_PARENT``, so both import paths resolve to the same object for those.
``_write_atomic``, ``_replace`` and ``_fdopen`` are not re-exported.
"""

from __future__ import annotations

import importlib.metadata
import contextlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from spec4.app_constants import (
    ARTIFACT_USAGE,
)
from spec4 import __version__
from spec4.project_manager._paths import ensure_version_dir, get_version_dir

# Test seams for ``_write_atomic``'s stdlib calls (CLEANUP_INVENTORY.md §52.5, §71).
# A test that must make one of them fail patches the name here, which reaches
# ``_write_atomic`` alone; patching ``os.replace`` itself would reach every write in
# the process while the test runs. The rule: a test that needs to fail any other call
# in ``_write_atomic`` (``fsync``, ``unlink``) adds that call's name to this block --
# it never patches ``os``. Designed patch points, private on purpose.
_replace = os.replace
_fdopen = os.fdopen


# ---------------------------------------------------------------------------
# LLM usage log
# ---------------------------------------------------------------------------

USAGE_FILENAME = ARTIFACT_USAGE
USAGE_SCHEMA_VERSION = "1"
_USAGE_COST_SOURCE = (
    "litellm response_cost (community cost map; may lag provider price sheets)"
)

# Sub-agents roll up into the planning agent whose turn runs them. Anything not
# listed reports under its own name, so a new sub-agent is visible rather than
# silently misattributed.
_USAGE_ROLLUP_PARENT: dict[str, str] = {
    "feature_speccer": "brainstormer",
    "phaser_seam": "phaser",
    "scout": "agentifier",
    "tier_analyst": "agentifier",
    "linker": "agentifier",
    "composer": "agentifier",
    "prioritizer": "agentifier",
    "spec_drafter": "agentifier",
    "cross_cutting_analyst": "agentifier",
}

# Serialises the read-modify-write of .spec4/v{N}/usage.json in save_usage():
# the chat persist funnel (poll thread) and the Designer generation thread can
# each flush a turn, and both load the existing file, merge their records and
# rewrite the whole thing. Module-scoped because the file is the shared
# resource here, not any one session.
_USAGE_LOCK = threading.Lock()


def _usage_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _usage_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _add_reported(rollup: dict[str, Any], key: str, value: int | None) -> None:
    """Add ``value`` into a null-until-reported slot, leaving None alone.

    The slot starts at None and becomes a number the first time any call
    reports one, so "no call reported this" never renders as a confident
    zero -- which is exactly how a round recorded before the field existed
    must read. One function for both cache fields in both rollups: the two
    counters would otherwise be four copies of the same three lines.
    """
    if value is not None:
        rollup[key] = (rollup[key] or 0) + value


def usage_rollup_name(agent: str | None) -> str:
    raw = agent if isinstance(agent, str) and agent else "unknown"
    return _USAGE_ROLLUP_PARENT.get(raw, raw)


def _usage_versions() -> tuple[str, str]:
    """(spec4 version, litellm version) for the file header. Never raises."""
    try:
        litellm_version = importlib.metadata.version("litellm")
    except importlib.metadata.PackageNotFoundError:
        litellm_version = "unknown"
    return __version__, litellm_version


def summarize_usage(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll one agent's per-call ``history`` up into its summary block.

    Derived, never accumulated: every write recomputes this from the full
    history, so the summary cannot drift from the call records. Token and
    cost sums cover only calls that reported them; ``cached_input_tokens``,
    ``cache_creation_input_tokens`` and ``computed_cost_usd`` stay null when
    no call in the history had a value, rather than reading as a confident
    zero -- which is what a round recorded before prompt caching existed must
    read as. ``models`` lists each distinct (model, provider) pair in
    first-seen order, which is how a re-run on a different model within the
    round becomes visible.

    Cache reads and cache writes are both already inside ``input_tokens``:
    every provider Spec4 talks to counts them in ``prompt_tokens``, so these
    two are a breakdown of that sum, not additions to it.
    """
    rollup: dict[str, Any] = {
        "calls": 0,
        "calls_missing_usage": 0,
        # Calls the provider reported usage for but LiteLLM could not price
        # (no cost-map entry). Their tokens are counted; their cost is not,
        # so a cost figure shown next to this count is a known undercount.
        "calls_missing_cost": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cached_input_tokens": None,
        "cache_creation_input_tokens": None,
        "computed_cost_usd": None,
        "models": [],
    }
    for call in history:
        rollup["calls"] += 1
        if call.get("usage_missing"):
            rollup["calls_missing_usage"] += 1
        elif _usage_float(call.get("computed_cost_usd")) is None:
            rollup["calls_missing_cost"] += 1
        for src, dst in (
            ("prompt_tokens", "input_tokens"),
            ("completion_tokens", "output_tokens"),
            ("total_tokens", "total_tokens"),
        ):
            value = _usage_int(call.get(src))
            if value is not None:
                rollup[dst] += value
        cached = _usage_int(call.get("cached_tokens"))
        if cached is None:
            cached = _usage_int(call.get("cache_read_input_tokens"))
        _add_reported(rollup, "cached_input_tokens", cached)
        _add_reported(
            rollup,
            "cache_creation_input_tokens",
            _usage_int(call.get("cache_creation_input_tokens")),
        )
        cost = _usage_float(call.get("computed_cost_usd"))
        if cost is not None:
            rollup["computed_cost_usd"] = round(
                (rollup["computed_cost_usd"] or 0.0) + cost, 8
            )
        # Effort joins the pair rather than getting a list of its own, so the
        # "last entry is the run being reported" rule the agent rows rely on
        # keeps model and effort together. A record written before the field
        # existed reads as "default", which is also what an unset effort means.
        pair = {
            "model": call.get("model"),
            "provider": call.get("provider"),
            "effort": call.get("effort") or "default",
        }
        if pair not in rollup["models"]:
            rollup["models"].append(pair)
    return rollup


def usage_totals(agents: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Round-wide totals across the per-agent summaries."""
    totals: dict[str, Any] = {
        "calls": 0,
        "calls_missing_usage": 0,
        "calls_missing_cost": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cached_input_tokens": None,
        "cache_creation_input_tokens": None,
        "computed_cost_usd": None,
    }
    for entry in agents.values():
        for key in (
            "calls",
            "calls_missing_usage",
            "calls_missing_cost",
            "input_tokens",
            "output_tokens",
            "total_tokens",
        ):
            totals[key] += _usage_int(entry.get(key)) or 0
        for key in ("cached_input_tokens", "cache_creation_input_tokens"):
            _add_reported(totals, key, _usage_int(entry.get(key)))
        cost = _usage_float(entry.get("computed_cost_usd"))
        if cost is not None:
            totals["computed_cost_usd"] = round(
                (totals["computed_cost_usd"] or 0.0) + cost, 8
            )
    return totals


def load_usage(working_dir: str | Path, version: int) -> dict[str, Any] | None:
    """Read ``.spec4/v{version}/usage.json``; None when missing or unreadable."""
    path = get_version_dir(working_dir, version) / USAGE_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


_COST_SUMMARY_EMPTY: dict[str, Any] = {
    "cost_usd": None,
    "calls": 0,
    "calls_missing_cost": 0,
    "calls_missing_usage": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cached_input_tokens": None,
    "cache_creation_input_tokens": None,
}


def _cost_block(entry: Any) -> dict[str, Any]:
    """One agent's (or the totals') cost and token figures, shape-guarded.

    Tokens are the provider-reported sums over calls that returned usage;
    ``cached_input_tokens`` stays None when no call reported a cache read and
    ``cache_creation_input_tokens`` when none reported a cache write. Both are
    already counted inside ``input_tokens``, so a caller that adds them to it
    double-counts. The shape must stay identical to ``_COST_SUMMARY_EMPTY``
    above: a caller reading a key from one and not the other is the drift this
    pairing exists to prevent.
    """
    if not isinstance(entry, dict):
        return dict(_COST_SUMMARY_EMPTY)
    return {
        "cost_usd": _usage_float(entry.get("computed_cost_usd")),
        "calls": _usage_int(entry.get("calls")) or 0,
        "calls_missing_cost": _usage_int(entry.get("calls_missing_cost")) or 0,
        "calls_missing_usage": _usage_int(entry.get("calls_missing_usage")) or 0,
        "input_tokens": _usage_int(entry.get("input_tokens")) or 0,
        "output_tokens": _usage_int(entry.get("output_tokens")) or 0,
        "cached_input_tokens": _usage_int(entry.get("cached_input_tokens")),
        "cache_creation_input_tokens": _usage_int(
            entry.get("cache_creation_input_tokens")
        ),
    }


def cost_summary(
    working_dir: str | Path, version: int, agent: str
) -> dict[str, Any] | None:
    """The in-app cost card's numbers for one agent in one round.

    A read-time view over ``usage.json``: ``agent`` is that planning agent's
    rollup (sub-agents already folded in by :func:`save_usage`) and ``total``
    is the round's. ``None`` when the round has no usage file yet. An agent
    with no block yet reads as zero calls and no cost. The cost figures are
    LiteLLM's estimate and carry the same caveats as the file: a call that
    could not be priced is counted in ``calls_missing_cost`` and excluded
    from ``cost_usd``, so the caller can say so rather than show a confident
    undercount.

    ``unpriced`` names those excluded calls — this agent's own, grouped the
    same way :func:`round_cost` groups the round's, and through the same
    function. It is here because counting a gap and naming it are one fact
    told at two densities, and the chat frame's run strip renders both lines
    from the same three-line renderer the project view uses: a summary that
    carried only the count would have left that renderer with nothing to name
    and would have quietly reintroduced the divergence the shared renderer
    exists to prevent.
    """
    data = load_usage(working_dir, version)
    if data is None:
        return None
    agents = data.get("agents")
    entry = agents.get(agent) if isinstance(agents, dict) else None
    notes = data.get("notes")
    return {
        "round": str(data.get("round") or f"v{version}"),
        "agent": _cost_block(entry),
        "total": _cost_block(data.get("totals")),
        # Scoped to this one agent by handing `unpriced_calls` a one-entry
        # mapping rather than the whole file: the block above is this agent's,
        # and a list of the *round's* gaps beside it would name calls that are
        # not in the figure it explains.
        "unpriced": unpriced_calls({agent: entry}),
        "cost_source": (
            notes.get("computed_cost_source") if isinstance(notes, dict) else None
        ),
    }


def _call_is_unpriced(call: dict[str, Any]) -> bool:
    """Whether one history record contributes no cost to the round's total.

    The same test :func:`summarize_usage` applies when it counts
    ``calls_missing_usage`` and ``calls_missing_cost``, written once and read
    from both places: a record that reported no usage at all, or one that
    reported usage LiteLLM had no price for. If these two ever disagreed, the
    named list below and the count beside it would describe different calls.
    """
    if call.get("usage_missing"):
        return True
    return _usage_float(call.get("computed_cost_usd")) is None


def unpriced_calls(agents: Any) -> list[dict[str, Any]]:
    """The round's unpriced calls, grouped by the agent and model that made
    them, in the order ``usage.json`` recorded them.

    Grouped rather than listed one by one because a re-run that failed to
    price is the *same* gap five times over, and a reader wants the model to
    go look up, not five identical rows. The agent is the rollup key the file
    is organised by (sub-agents already folded into their parent by
    :func:`save_usage`), so a name here is a name the agent table also shows.
    """
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    if not isinstance(agents, dict):
        return []
    for name, entry in agents.items():
        history = entry.get("history") if isinstance(entry, dict) else None
        for call in history or []:
            if not isinstance(call, dict) or not _call_is_unpriced(call):
                continue
            model = call.get("model")
            model = str(model) if isinstance(model, str) and model else ""
            key = (str(name), model)
            group = groups.setdefault(
                key, {"agent": str(name), "model": model, "calls": 0}
            )
            group["calls"] += 1
    return list(groups.values())


def round_cost(working_dir: str | Path | None, version: int | None) -> dict[str, Any]:
    """The round's cost figures for the project view.

    A read-time view over ``usage.json``, like :func:`cost_summary` beside it,
    and it aggregates nothing of its own: ``total`` is the file's own
    ``totals`` block, which :func:`save_usage` recomputes from the full
    history on every write. The only thing read out of the histories here is
    *which* calls could not be priced, which the summaries count but do not
    name.

    Never None. No project directory, no round, no usage file, and a usage
    file recording nothing are the same answer to the only question this
    surface asks — nothing has been spent yet — and returning a record for all
    four spares the caller three more empty states to render.
    """
    data = (
        load_usage(working_dir, version)
        if working_dir is not None and version is not None
        else None
    )
    if not isinstance(data, dict):
        data = {}
    notes = data.get("notes")
    return {
        "round": str(data.get("round") or f"v{version if version is not None else 0}"),
        "total": _cost_block(data.get("totals")),
        "unpriced": unpriced_calls(data.get("agents")),
        "cost_source": (
            notes.get("computed_cost_source") if isinstance(notes, dict) else None
        ),
    }


def _write_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a sibling temp file and ``os.replace``.

    A crash or disk error mid-write leaves the previous file untouched; the
    temp file is removed on failure.
    """
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with _fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        _replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def save_usage(
    working_dir: str | Path,
    records: list[dict[str, Any]],
    version: int,
    fast_forward: bool | None = None,
) -> None:
    """Append per-call usage records to the round's ``usage.json``.

    Read-modify-write: the existing file (if any) is loaded, the new records
    are appended to their agent's ``history``, and every agent summary plus
    the round ``totals`` are recomputed from the full history. History is
    never overwritten, so a developer who quits and re-enters with a
    different provider keeps both runs side by side. The write is atomic.

    ``fast_forward`` is what the writer knows about the turn being recorded:
    ``True`` marks the round as having used Fast Forward (sticky), ``False``
    records a known non-FF turn only while nothing else is known, and
    ``None`` (a Designer draw, say) leaves the note as it was.

    Not a pipeline artifact: this file is an output of every agent and an
    input to none. It is declared in ``_NON_ARTIFACT_FILES`` and never
    appears in ``_STALE_DEPENDENCIES`` or ``_PIPELINE_ARTIFACT_ORDER``, so
    its mtime cannot make any agent read as Needs Update. Serialised under a
    lock because the chat persist funnel and the Designer thread can both
    flush.
    """
    if not records:
        return
    with _USAGE_LOCK:
        version_dir = ensure_version_dir(working_dir, version)
        now = datetime.now(timezone.utc).isoformat()
        existing = load_usage(working_dir, version) or {}

        agents_in = existing.get("agents")
        agents: dict[str, dict[str, Any]] = {}
        if isinstance(agents_in, dict):
            for name, entry in agents_in.items():
                history = entry.get("history") if isinstance(entry, dict) else None
                agents[str(name)] = {
                    "history": [h for h in (history or []) if isinstance(h, dict)]
                }
        for rec in records:
            agents.setdefault(usage_rollup_name(rec.get("agent")), {"history": []})[
                "history"
            ].append(rec)
        for name, entry in agents.items():
            history = entry["history"]
            agents[name] = {**summarize_usage(history), "history": history}

        notes_in = existing.get("notes")
        notes: dict[str, Any] = dict(notes_in) if isinstance(notes_in, dict) else {}
        notes["tokens_are_ground_truth"] = True
        notes["computed_cost_source"] = _USAGE_COST_SOURCE
        if fast_forward is True:
            notes["fast_forward"] = True
        elif fast_forward is False and notes.get("fast_forward") is None:
            notes["fast_forward"] = False
        else:
            notes.setdefault("fast_forward", None)

        spec4_version, litellm_version = _usage_versions()
        payload = {
            "schema_version": USAGE_SCHEMA_VERSION,
            "spec4_version": spec4_version,
            "litellm_version": litellm_version,
            "round": f"v{version}",
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
            "notes": notes,
            "agents": agents,
            "totals": usage_totals(agents),
        }
        _write_atomic(version_dir / USAGE_FILENAME, json.dumps(payload, indent=2))
