"""Compare two trace_identity.py runs, test by test. Exit 1 on any divergence.

    python scripts/cleanup/trace_diff.py BASE.json[,BASE2.json,...] NEW.json [--list]

A test's trace is its outermost family invocations in order: each entry, its
arguments, and its events (chunks with session snapshots, then the return or the
exception). For every test in either run, the first divergence is reported. A snapshot
pair whose dicts hold the same keys with the same values in a different order is
flagged KEY ORDER ONLY. It is still a divergence, reported for a ruling and never
normalised away.
"""

import json
import re
import sys

NET = re.compile(r"sub-agent '\w+' raised")
# The nine tests that race their own streaming worker (§79.0; on the Phase 8 list). A
# network reach in one of them is the defect firing, recorded and not counted against
# the refactor (ruled at the 7q2 stop). The same event anywhere else is still escalated.
_R = "tests/agentifier/test_try_again.py::"
KNOWN_RACE = {
    _R + t
    for t in (
        "TestCallback::test_prior_transcript_is_preserved",
        "TestCallback::test_starts_a_stream_and_records_the_action",
        "TestDiskIsUntouched::test_implemented_round_survives_a_full_try_again",
        "TestGuidedRedraw::test_blank_note_is_the_plain_redraw",
        "TestGuidedRedraw::test_blank_note_keeps_prior_notes_and_refreshes_the_set",
        "TestGuidedRedraw::test_every_click_is_one_history_event",
        "TestGuidedRedraw::test_note_survives_the_reset_with_the_rejected_set",
        "TestGuidedRedraw::test_notes_accumulate_across_retries",
        "TestGuidedRedraw::test_user_bubble_quotes_the_note",
    )
}


def pairs_to_obj(v, ordered=True):
    if isinstance(v, dict) and "__pairs__" in v:
        items = [(json.dumps(k), pairs_to_obj(x, ordered)) for k, x in v["__pairs__"]]
        return items if ordered else sorted(items, key=lambda kv: kv[0])
    if isinstance(v, list):
        return [pairs_to_obj(x, ordered) for x in v]
    return v


def describe_snap(a_json, b_json):
    a, b = json.loads(a_json), json.loads(b_json)
    if pairs_to_obj(a, ordered=False) == pairs_to_obj(b, ordered=False):
        return "KEY ORDER ONLY (same keys and values, different insertion order)"
    ad = dict(pairs_to_obj(a)) if isinstance(a, dict) else {}
    bd = dict(pairs_to_obj(b)) if isinstance(b, dict) else {}
    changed = [k for k in dict.fromkeys(list(ad) + list(bd)) if ad.get(k) != bd.get(k)]
    return (
        "session keys differing: "
        + ", ".join(changed[:12])
        + (" …" if len(changed) > 12 else "")
    )


def first_divergence(ta, tb, sa, sb):
    if len(ta) != len(tb):
        return f"invocation count {len(ta)} vs {len(tb)}"
    for i, (x, y) in enumerate(zip(ta, tb)):
        if x["entry"] != y["entry"] or x["args"] != y["args"]:
            return (
                f"invocation {i}: entry/args {x['entry']}{x['args']} vs "
                f"{y['entry']}{y['args']}"
            )
        ex, ey = x["events"], y["events"]
        for j, (e, f) in enumerate(zip(ex, ey)):
            if e == f:
                continue
            if e[0] != f[0]:
                return f"invocation {i} event {j}: kind {e[0]!r} vs {f[0]!r}"
            if e[0] == "y" and e[1] != f[1]:
                return (
                    f"invocation {i} event {j}: chunk {str(e[1])[:70]!r} vs "
                    f"{str(f[1])[:70]!r}"
                )
            if e[0] == "x" and e[1:3] != f[1:3]:
                return f"invocation {i} event {j}: exception {e[1:3]} vs {f[1:3]}"
            if e[0] == "r" and e[1] != f[1]:
                return f"invocation {i} event {j}: return {e[1]!r} vs {f[1]!r}"
            return f"invocation {i} event {j} ({e[0]}): " + describe_snap(
                sa[e[-1]], sb[f[-1]]
            )
        if len(ex) != len(ey):
            return f"invocation {i}: event count {len(ex)} vs {len(ey)}"
    return None


# BASE may be several files joined by commas: the baseline recorded more than once. A
# test whose baseline runs disagree (a race inside the test itself) passes only if its
# new trace is IDENTICAL to one of the recorded variants. Nothing is normalised for it,
# and every other event in its trace is still compared exactly.
bases = [json.load(open(p)) for p in sys.argv[1].split(",")]
b = json.load(open(sys.argv[2]))


def by_thread(run, kind):
    """The run's traces restricted to one thread kind, tests with none dropped."""
    out = {}
    for n, invs in run["traces"].items():
        keep = [i for i in invs if i.get("thread", "main") == kind]
        if keep:
            out[n] = keep
    return out


# The identity verdict is taken over MAIN-THREAD invocations: the test's own thread,
# deterministic across repeated baselines. Invocations in streaming worker threads are
# compared too, but reported as advisory. A worker the test does not wait for can
# outlive the test's patches, so its trace depends on timing (§79.0).
workers_b = by_thread(b, "worker")
workers_v = [by_thread(v, "worker") for v in bases]


def states(invs, snaps):
    """Everything a worker trace shows: its chunk texts, and every (key, value) pair of
    every snapshot. The value is serialised with its own nested order."""
    chunks, pairs = set(), set()
    for inv in invs:
        for ev in inv["events"]:
            if ev[0] == "y":
                chunks.add(json.dumps(ev[1]))
            snap = json.loads(snaps[ev[-1]])
            for k, v in snap.get("__pairs__") or []:
                pairs.add((json.dumps(k), json.dumps(v)))
    return chunks, pairs


def worker_kind(n):
    """How a test's worker trace differs from the baseline (ruled at review of 7q1).

    Timing, which stays advisory, reorders or drops states the race has already
    produced: every chunk text and every session (key, value) pair in the new trace
    appears somewhere in the test's recorded worker traces, in some baseline run.
    Content, which is escalated to a verdict failure, introduces a state never
    recorded: a chunk text or a (key, value) pair that no baseline run shows.
    """
    new = workers_b.get(n, [])
    if (
        first_divergence(
            workers_v[0].get(n, []), new, bases[0]["snapshots"], b["snapshots"]
        )
        is None
    ):
        return None
    seen_chunks, seen_pairs = set(), set()
    for v, run in zip(workers_v, bases):
        c, p = states(v.get(n, []), run["snapshots"])
        seen_chunks |= c
        seen_pairs |= p
    # A real sub-agent call is never timing, even though a baseline run recorded one
    # (§79.2). It is the race's network dependency, and it is always escalated.
    seen_chunks = {c for c in seen_chunks if not NET.search(c)}
    seen_pairs = {(k, v) for k, v in seen_pairs if not NET.search(v)}
    new_chunks, new_pairs = states(new, b["snapshots"])
    net = sorted(c for c in new_chunks if NET.search(c))
    if net and n in KNOWN_RACE:
        # Ruled at the 7q2 stop: recorded, not blocking. It fires on the unchanged tree
        # too, so it carries no signal about the split (§79.2).
        return (
            "KNOWN DEFECT (network reach in a known racing test): chunk "
            f"{json.loads(net[0])[:70]!r}"
        )
    if net:
        return (
            "CONTENT (network reach: a real sub-agent call): chunk "
            f"{json.loads(net[0])[:90]!r}"
        )
    novel_chunks = sorted(new_chunks - seen_chunks)
    novel_pairs = sorted(new_pairs - seen_pairs)
    if novel_chunks or novel_pairs:
        detail = [f"chunk {json.loads(c)[:70]!r}" for c in novel_chunks[:2]] + [
            f"{json.loads(k)} = {v[:70]}" for k, v in novel_pairs[:3]
        ]
        return "CONTENT (a state no baseline run recorded): " + "; ".join(detail)
    missing = sorted(seen_chunks - new_chunks)
    if missing:
        return (
            f"timing: arrival -- {len(missing)} recorded chunk(s) did not arrive; "
            "nothing novel"
        )
    return (
        "timing: ordering -- the recorded states, at different points between worker "
        "and main; nothing novel"
    )


w_kinds = {
    n: k for n in sorted(set().union(*workers_v, workers_b)) if (k := worker_kind(n))
}
escalated = {n: k for n, k in w_kinds.items() if k.startswith("CONTENT")}
for v in bases:
    v["traces"] = by_thread(v, "main")
b["traces"] = by_thread(b, "main")
a = bases[0]
ta, tb = a["traces"], b["traces"]
nodes = sorted(set(ta) | set(tb))
diverging, order_only, by_variant = [], 0, []
for n in nodes:
    if n not in ta or n not in tb:
        diverging.append(
            (n, "traced in only one run: " + ("base" if n in ta else "new"))
        )
        continue
    d = first_divergence(ta[n], tb[n], a["snapshots"], b["snapshots"])
    if d:
        alt = next(
            (
                i
                for i, v in enumerate(bases[1:], 1)
                if n in v["traces"]
                and first_divergence(
                    v["traces"][n], tb[n], v["snapshots"], b["snapshots"]
                )
                is None
            ),
            None,
        )
        if alt is not None:
            by_variant.append((n, alt))
            continue
        order_only += "KEY ORDER ONLY" in d
        diverging.append((n, d))
print(f"base: {json.dumps(a['meta'])}")
print(f"new:  {json.dumps(b['meta'])}")
print(
    f"tests traced: base {len(ta)}, new {len(tb)}; identical "
    f"{len(nodes) - len(diverging)}; "
    f"diverging {len(diverging)} (key order only: {order_only})"
    + (
        f"; identical to a recorded variant other than the first: {len(by_variant)}"
        if len(bases) > 1
        else ""
    )
)
for n, i in by_variant:
    print(f"  VARIANT {i} {n}")
print(
    f"worker-thread invocations: tests {len(set().union(*workers_v, workers_b))}; "
    f"differing {len(w_kinds)}: "
    f"advisory (timing) {len(w_kinds) - len(escalated)}, escalated (content) "
    f"{len(escalated)}"
)
recorded = {n for n, k in w_kinds.items() if k.startswith("KNOWN DEFECT")}
for n, k in w_kinds.items():
    tag = (
        "ESCALATED" if n in escalated else "RECORDED " if n in recorded else "ADVISORY "
    )
    print(f"  {tag} {n}: {k}")
for n, d in (
    diverging if "--list" in sys.argv or len(diverging) <= 40 else diverging[:40]
):
    print(f"  DIVERGES {n}: {d}")
if len(diverging) > 40 and "--list" not in sys.argv:
    print(f"  … {len(diverging) - 40} more (use --list)")
# An escalated worker divergence is a verdict failure, as ruled at review of 7q1. It
# fails the exit status exactly as a main-thread divergence does.
sys.exit(1 if diverging or escalated else 0)
