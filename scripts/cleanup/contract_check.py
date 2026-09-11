"""Each generator's documented session writes, against the writes a trace observed.

    uv run python scripts/cleanup/contract_check.py TRACE.json [--list]

TRACE.json is a trace_identity.py run of the default family. Each family function's
docstring carries a paragraph that begins "Its contract on ``session``" (7q3,
CLEANUP_INVENTORY.md 79.3). This check reads the paragraph and takes as documented
keys the ``double-backticked`` identifiers in it that name session keys. Two kinds of
name are resolved, not read as keys:
  - a family function (``_begin_priority_phase``): a hand-off, whose own documented keys
    count for this generator too, since its writes land inside the same invocation;
  - a module collection (``_RESTART_DEFAULTS``, ``_RESTART_POP``): its string members.

Observed writes come from the trace. Every recorded invocation carries a "start"
snapshot, the session as the invocation found it. A key is observed changing under a
generator when, in one of that generator's own invocations (the outermost family
frame, so a call made through `run` is `run`'s), some later snapshot adds it, drops
it, or holds a different value.

Reported per generator:
  documented   own keys, and the keys added by its hand-offs;
  observed     keys seen changing under its own entry;
  UNDOCUMENTED observed keys that neither it nor a hand-off documents. Exit 1 on any;
  never seen   documented own keys that no traced invocation changed (the Phase 8
               contract-test list, PHASE8_RECORD.md 1.2 P21).

STAND_INS are keys that test stand-ins write into the session, set aside by name as 7q3
did: `_finalized` and `_priority_begun`.
"""

from __future__ import annotations

import importlib
import inspect
import json
import re
import sys

MODULE = "spec4.agentifier.agentifier"
FAMILY = (
    "run_catalog_phase",
    "run_spec_phase",
    "run_cross_cutting_phase",
    "run_priority_phase",
    "handle_reentry",
    "finalize_specs",
    "begin_priority_phase",
    "complete_agentifier",
)
STAND_INS = {"_finalized", "_priority_begun"}
NOT_KEYS = {"session", "user_input", "None", "True", "False", "reset_agentifier_flow"}
TICKED = re.compile(r"``([A-Za-z_][A-Za-z0-9_]*)``")


def contract(mod, name: str) -> str:
    doc = inspect.getdoc(getattr(mod, name)) or ""
    i = doc.find("Its contract on ``session``")
    if i < 0:
        raise SystemExit(f"contract_check: {name} has no contract paragraph")
    return doc[i:]


def documented(mod) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    own: dict[str, set[str]] = {}
    handoffs: dict[str, set[str]] = {}
    for name in FAMILY:
        keys, hands = set(), set()
        for tok in TICKED.findall(contract(mod, name)):
            bare = tok.lstrip("_")
            if bare in FAMILY and bare != name:
                hands.add(bare)
                continue
            obj = getattr(mod, tok, None)
            if isinstance(obj, (dict, tuple, list, set, frozenset)):
                keys |= {k for k in obj if isinstance(k, str)}
                continue
            if tok in NOT_KEYS or callable(obj):
                continue
            keys.add(tok)
        own[name], handoffs[name] = keys, hands
    return own, handoffs


def closure(name, own, handoffs, seen=None) -> set[str]:
    seen = seen or set()
    out = set()
    for h in handoffs[name]:
        if h in seen:
            continue
        seen.add(h)
        out |= own[h] | closure(h, own, handoffs, seen)
    return out


def as_dict(snap_json: str) -> dict[str, str]:
    snap = json.loads(snap_json)
    return {json.dumps(k): json.dumps(v) for k, v in (snap.get("__pairs__") or [])}


def observed(trace) -> dict[str, set[str]]:
    snaps = trace["snapshots"]
    out: dict[str, set[str]] = {n: set() for n in FAMILY}
    for invs in trace["traces"].values():
        for inv in invs:
            if inv["entry"] not in out or "start" not in inv:
                continue
            base = as_dict(snaps[inv["start"]])
            for ev in inv["events"]:
                now = as_dict(snaps[ev[-1]])
                for k in set(base) | set(now):
                    if base.get(k) != now.get(k):
                        out[inv["entry"]].add(json.loads(k))
    return out


def main() -> int:
    trace = json.load(open(sys.argv[1]))
    mod = importlib.import_module(MODULE)
    own, handoffs = documented(mod)
    seen = observed(trace)
    bad = 0
    total_unseen = 0
    for name in FAMILY:
        via = closure(name, own, handoffs) - own[name]
        obs = seen[name] - STAND_INS
        undocumented = sorted(obs - own[name] - via)
        unseen = sorted(own[name] - seen[name])
        total_unseen += len(unseen)
        bad += bool(undocumented)
        hands = ", ".join(sorted(handoffs[name])) or "no hand-off"
        print(
            f"{name}: documented {len(own[name])} own (+{len(via)} via {hands}); "
            f"observed {len(obs)}; UNDOCUMENTED {', '.join(undocumented) or 'none'}"
        )
        print(f"    documented, never seen changing: {', '.join(unseen) or 'none'}")
    print(f"never seen changing, in all: {total_unseen}; contracts failing: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
