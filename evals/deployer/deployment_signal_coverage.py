"""Deployment-plan probe: deployment-signal coverage (D-DE1).

Dev tooling under ``evals/``. Never wired into the pipeline.

Walks the deployment-shaped signals in ``stack.json`` and asks, for each,
whether it surfaced anywhere in the finished ``deployment-plan.md``. These are
the signals the four upstream rounds sharpened *for* deployment and that
pre-redesign Deployer received only as a raw JSON paste (never joined):

**[1] DEPLOYMENT TARGETS** — every ``deployment.targets[]`` entry (by name /
provider / transport), and its ``exposure`` (``transport``, ``cors``). Each
target is a hosting surface; each ``cors`` value is literal CORS config.

**[2] AUTH** — every ``security.auth[]`` mechanism (by name / provider). Its
absence is a *trustworthy negative* (no accounts), reported as such — not a
gap.

**[3] INFRA TO PROVISION** — every ``kind: infrastructure`` node and every
``satisfies_infra`` target: the substrate a plan must actually provision
(vector index, retriever, chunking, stores).

Coverage here is blunt containment (does the signal's matchable name appear in
the plan text), mirroring the phaser suite's ``name_matches`` philosophy: a
plan that provisions a target in prose without ever naming it reports NOT
COVERED, which is the legibility gap the round exists to close. This is a
pre/post *measurement*, not a pass/fail gate — a pre-round draw is expected to
score low because the paste never routed these fields.

Usage::

    python3 deployment_signal_coverage.py <draw_dir>
"""

from __future__ import annotations

import sys

from _load import (
    load_deployer_draw,
    name_matches,
    plan_text,
    stack_entries,
)


def _targets(stack: dict) -> list[dict]:
    dep = (stack or {}).get("deployment") or {}
    return [t for t in (dep.get("targets") or []) if isinstance(t, dict)]


def _auth(stack: dict) -> list[dict]:
    sec = (stack or {}).get("security") or {}
    return [a for a in (sec.get("auth") or []) if isinstance(a, dict)]


def _label(entry: dict, *keys: str) -> str:
    for k in keys:
        v = entry.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _as_list(value) -> list:
    """Tolerate a field declared as either a string or a list of strings."""
    if isinstance(value, list):
        return value
    return [value] if value else []


def _lead_phrase(choice) -> str:
    """The leading technology phrase of a ``choice``, minus its prose tail.

    ``choice`` reads like "LangChain RecursiveCharacterTextSplitter (in-process,
    in FastAPI)" — the technology, then a parenthetical describing how it is
    deployed. Only the leading phrase is a name a plan might repeat; matching on
    tokens from the tail would let an unrelated mention of "FastAPI" count a
    chunking pipeline as provisioned, which is the false positive that would
    make this probe useless as a regression check.
    """
    text = str(choice or "").strip()
    for sep in ("(", ",", " backed by ", " with ", " + "):
        idx = text.find(sep)
        if idx > 0:
            text = text[:idx]
    return text.strip()


def _any_matches(names, haystack: str) -> bool:
    """True when any declared name for a signal appears in the plan."""
    return any(n and name_matches(str(n), haystack) for n in names)


def report(draw_dir: str) -> None:
    draw = load_deployer_draw(draw_dir)
    print(f"deployment_signal_coverage: {draw_dir}")

    stack = draw.get("stack")
    if not stack:
        print("  UNMEASURABLE — no stack.json in draw")
        return
    if draw.get("plan") is None:
        print("  UNMEASURABLE — no deployment-plan.md in draw")
        return

    ptext = plan_text(draw)
    covered = 0
    total = 0

    print("\n[1] DEPLOYMENT TARGETS")
    targets = _targets(stack)
    if not targets:
        print("  (no deployment.targets[] — nothing to provision as a host)")
    for t in targets:
        name = _label(t, "name", "provider", "service", "type")
        hit = bool(name) and name_matches(name, ptext)
        total += 1
        covered += int(hit)
        print(f"  [{'x' if hit else ' '}] {name or '(unnamed target)'}")
        exposure = t.get("exposure") or {}
        if isinstance(exposure, dict):
            for facet in ("transport", "cors"):
                val = exposure.get(facet)
                if not val:
                    continue
                token = val if isinstance(val, str) else facet
                fhit = name_matches(str(token), ptext) or facet in ptext
                total += 1
                covered += int(fhit)
                print(f"      exposure.{facet}: [{'x' if fhit else ' '}] {val}")

    print("\n[2] AUTH (security.auth[])")
    auth = _auth(stack)
    if "security" not in stack or not (stack.get("security") or {}).get("auth"):
        print("  TRUSTWORTHY NEGATIVE — no auth block; no accounts expected. "
              "The plan should not provision auth or re-ask for it.")
    for a in auth:
        name = _label(a, "name", "provider", "mechanism", "type")
        # A mechanism is declared under several names, and `mechanism` is often a
        # whole prose sentence no plan would quote verbatim. Check every name the
        # stack gives it, including its credential variables — those are literal,
        # distinctive tokens (OIDC_CLIENT_ID), so a plan configuring them has
        # demonstrably carried the signal through.
        aliases = [
            str(a.get(k)) for k in ("name", "provider", "mechanism", "type")
            if str(a.get(k) or "").strip()
        ]
        aliases += [
            str(c) for c in _as_list(a.get("credentials_env")) if str(c).strip()
        ]
        hit = _any_matches(aliases, ptext)
        total += 1
        covered += int(hit)
        print(f"  [{'x' if hit else ' '}] {name or '(unnamed auth)'}")

    print("\n[3] INFRA TO PROVISION")
    infra_aliases: dict[str, tuple[str, list[str]]] = {}
    for e in stack_entries(draw):
        entry = e["entry"]
        # Infrastructure entries are identified by *section membership*, not by a
        # ``kind`` field: the stack's ``infrastructure`` block is a dict keyed by
        # name (chunking_pipeline, retriever, ...) and its entries carry no
        # ``kind``. Filtering on ``kind == "infrastructure"`` silently matched
        # nothing and under-counted every substrate in the corpus.
        origin = None
        if str(e.get("path") or "").startswith("infrastructure."):
            origin = "infrastructure section"
        elif entry.get("kind") == "infrastructure":
            origin = "kind:infrastructure"
        if origin:
            # The stack names a substrate twice: an internal key
            # (``chunking_pipeline``) and the ratified ``choice`` that a plan
            # would actually write about. Check both, taking the choice's leading
            # technology phrase rather than its whole prose description.
            infra_aliases.setdefault(
                e["name"], (origin, [e["name"], _lead_phrase(entry.get("choice"))])
            )
        for tgt in entry.get("satisfies_infra") or []:
            infra_aliases.setdefault(str(tgt), ("satisfies_infra", [str(tgt)]))
    if not infra_aliases:
        print("  (no infrastructure entries or satisfies_infra targets)")
    for name, (origin, aliases) in sorted(infra_aliases.items()):
        hit = _any_matches(aliases, ptext)
        total += 1
        covered += int(hit)
        print(f"  [{'x' if hit else ' '}] {name}  ({origin})")

    print(f"\nCOVERAGE: {covered}/{total} deployment signals surfaced in the plan"
          if total else "\nCOVERAGE: no deployment signals present to measure")
    print(
        "  Names are matched literally against the declared names for each signal. "
        "A plan that provisions a substrate while describing it only by concept "
        "will read as NOT COVERED: this probe under-reports rather than "
        "over-claims, so read an unchecked line as 'go look', not as a defect."
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python3 deployment_signal_coverage.py <draw_dir>")
        raise SystemExit(2)
    report(sys.argv[1])
