"""Deployment-plan probe: NFR threading + classification (D-DE1 / D-DE8).

Dev tooling under ``evals/``. Never wired into the pipeline.

Twin of ``evals/phaser/nfr_threading.py``, retargeted from phase text to the
finished ``deployment-plan.md`` and extended with the deployment-relevant vs.
feature-behavioral split the Deployer round turns on.

**[1] DERIVED GOALS** — the ``nfr_<slug>`` ids from ``feature_specs.nfr_goals``
(the D-SC2 rule), the authoritative id set.

**[2] STACK CLAIMS** — ids appearing in any stack entry's ``satisfies_nfr``.
CLAIMED (matches a derived id), UNKNOWN (model-coined, matches none), or the
derived goal is ORPHANED (no stack entry claims it). An orphan is reported
honestly and is *not* a probe defect: Deployer must surface an unclaimed but
deployment-relevant goal without ever inventing an infra claim for it — the
same honesty discipline Phaser applied.

**[3] CLASSIFICATION** — a blunt keyword split of each goal into:
  * DEPLOYMENT-RELEVANT — latency/offline/zero-downtime/scale/isolation/etc.,
    which belong threaded into the plan (Target / Scaling / Security /
    Monitoring).
  * FEATURE-BEHAVIORAL — citations/refusal/coherence/etc., the coding-agent's
    or StackAdvisor's job, which Deployer should recognize and leave aside.
  The keyword split is deliberately crude and reported as an *advisory* — the
  real classification is a semantic judgment made in the drawn conversation
  (D-DE8). The probe's job is to flag which goals a human should check, not to
  be authoritative.

**[4] GOALS TO READ** — the goals listed for a human to check against the plan.
This section deliberately does **not** score. Whether a goal is addressed is a
judgment about meaning, and a plan states a goal in its own words: "Latency &
responsiveness" addresses "complete and display results quickly" without sharing
a phrase with it. Literal matching cannot see that.

Loosening the match until it could would be worse than useless. It would make
the probe count a passing mention of a term as coverage — a false positive — and
a probe that reports coverage it cannot verify hides exactly the regression it
exists to catch. Under-reporting is a conservative failure; over-matching is a
silent one. So the score is gone and a verbatim-appearance hint remains: it is
evidence when present and means nothing when absent.

If this judgment is ever worth automating, the honest home for it is a live
model pass — the pattern in ``evals/phaser/declaration_alignment.py``'s
``--llm`` section — not a cleverer string match.

Usage::

    python3 nfr_threading.py <draw_dir>
"""

from __future__ import annotations

import sys

from _load import (
    derived_nfr_ids,
    load_deployer_draw,
    name_matches,
    plan_text,
    stack_entries,
)

# Crude lexical cues. Deliberately not exhaustive: the authoritative call is
# semantic and lives in the drawn conversation. Reported as advisory only.
_DEPLOYMENT_CUES = (
    # latency / responsiveness
    "latency", "sub-second", "subsecond", "fast", "quick", "quickly",
    "response time", "real-time", "realtime", "responsive",
    # offline / network resilience
    "offline", "service worker", "pwa", "cache", "cdn", "network",
    "connectivity", "intermittent", "unavailable", "no connection",
    # availability / deploys
    "zero-downtime", "zero downtime", "without interrupt", "without interruption",
    "uninterrupted", "blue-green", "rolling", "availability", "uptime",
    # scale
    "scale", "scales", "scaling", "concurrent", "throughput", "load", "region",
    # durability / persistence (storage provisioning, backups)
    "persist", "persistence", "persisted", "durable", "durably", "durability",
    "reliably", "restart", "restarts", "across sessions", "device restart",
    "backup", "recover", "data loss",
    # isolation / security posture
    "isolation", "isolated", "confidential", "never exposed", "tenant",
    "per-tenant", "secure", "encryption", "at rest", "in transit",
)
_BEHAVIORAL_CUES = (
    "citation", "cited", "verifiable", "verify", "refuse", "refusal",
    "out-of-scope", "out of scope", "coherent", "coherence", "accurate",
    "accuracy", "hallucinat", "grounded", "relevant", "helpful", "tone",
    "consistent across", "faithful",
)


def _classify(goal: str) -> str:
    low = goal.lower()
    dep = any(c in low for c in _DEPLOYMENT_CUES)
    beh = any(c in low for c in _BEHAVIORAL_CUES)
    if dep and not beh:
        return "DEPLOYMENT-RELEVANT"
    if beh and not dep:
        return "FEATURE-BEHAVIORAL"
    if dep and beh:
        return "MIXED (inspect)"
    return "UNCLASSIFIED (inspect)"


def report(draw_dir: str) -> None:
    draw = load_deployer_draw(draw_dir)
    print(f"nfr_threading: {draw_dir}")

    derived = derived_nfr_ids(draw)
    print(f"\n[1] DERIVED GOALS ({len(derived)})")
    if not derived:
        print("  UNMEASURABLE — no feature_specs.json nfr_goals in draw")
        return
    for nid, goal in derived.items():
        print(f"  {nid}")
        print(f"    \"{goal}\"")

    print("\n[2] STACK CLAIMS (satisfies_nfr)")
    if not draw.get("stack"):
        print("  UNMEASURABLE — no stack.json in draw")
        claims: dict[str, list[str]] = {}
    else:
        claims = {}
        for e in stack_entries(draw):
            for nid in e["entry"].get("satisfies_nfr") or []:
                claims.setdefault(str(nid), []).append(e["name"])
        for nid, entries in sorted(claims.items()):
            tag = "CLAIMED" if nid in derived else "UNKNOWN (matches no derived goal)"
            print(f"  {tag}  {nid}")
            print(f"    by: {', '.join(sorted(set(entries)))}")
        orphans = [nid for nid in derived if nid not in claims]
        for nid in orphans:
            print(f"  ORPHANED  {nid} (no stack entry claims it)")

    plan = draw.get("plan")
    if plan is None:
        print("\n[3/4] UNMEASURABLE — no deployment-plan.md in draw")
        return
    ptext = plan_text(draw)

    print("\n[3] CLASSIFICATION (advisory keyword split)")
    kinds: dict[str, str] = {}
    for nid, goal in derived.items():
        kind = _classify(goal)
        kinds[nid] = kind
        print(f"  {kind:24}  {nid}")

    print("\n[4] DEPLOYMENT-RELEVANT GOALS — READ THESE IN THE PLAN")
    print("  This section does not score the plan. Whether a goal is *addressed*")
    print("  is a judgment about meaning, and a plan states it in its own words:")
    print("  \"Latency & responsiveness\" addresses \"complete and display results")
    print("  quickly\" without sharing a phrase with it. Literal matching cannot")
    print("  see that, and loosening it until it could would make this probe")
    print("  count a passing mention as coverage — which is the failure that")
    print("  hides a real regression. So the goals are listed for a human to")
    print("  check, with a verbatim-appearance hint that is evidence when present")
    print("  and means nothing when absent.")
    dep_ids = [n for n, k in kinds.items() if k == "DEPLOYMENT-RELEVANT"]
    beh_ids = [n for n, k in kinds.items() if k == "FEATURE-BEHAVIORAL"]
    other_ids = [n for n, k in kinds.items() if k not in
                 ("DEPLOYMENT-RELEVANT", "FEATURE-BEHAVIORAL")]

    if dep_ids or other_ids:
        print("\n  Should be addressed by the deployment:")
    for nid in dep_ids + other_ids:
        goal = derived[nid]
        verbatim = " (appears verbatim)" if name_matches(goal, ptext) else ""
        print(f"    - \"{goal}\"{verbatim}")
        if kinds[nid] != "DEPLOYMENT-RELEVANT":
            print(f"      [{kinds[nid]} — classify this one yourself]")

    if beh_ids:
        print("\n  Should NOT be satisfied by infrastructure — confirm the plan")
        print("  names them as the coding agent's rather than claiming them:")
    for nid in beh_ids:
        goal = derived[nid]
        mentioned = " (mentioned in the plan — check how)" if name_matches(
            goal, ptext) else ""
        print(f"    - \"{goal}\"{mentioned}")

    print("\n  Orphaned goals (no stack component claims them) are legitimate:")
    print("  a goal satisfied by features has no claimer. What must never appear")
    print("  is an invented infrastructure claim for one.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python3 nfr_threading.py <draw_dir>")
        raise SystemExit(2)
    report(sys.argv[1])
