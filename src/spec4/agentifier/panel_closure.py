"""Selection-time closure for the Agentifier breadth panel (Panel closure lever).

Pure, LLM-free, deterministic. Given the ranked candidate pool — which carries
the Scout graph-contract edges ``composed_under`` / ``requires`` (persisted by
D-EP) — and the developer's *intent* (the features they explicitly checked),
resolve the selection to a fixpoint under two ratified rules:

* requires-closure (R): a selected dependent transitively pulls in the producers
  it ``requires``; each pulled-in producer is *locked* — it cannot be dropped
  while a dependent that needs it stays selected.
* coordinator toggle (C): a *coordinator* is a head that coordinates >= 2 members
  in the pool; it is *derived*, never chosen. It is on iff >= 2 of its members are
  in the closed set (or it is itself required by a dependent). It is never seeded
  from intent, and a developer cannot force it on with < 2 members. A head with a
  single member is not a coordinator — it is a normal, directly-selectable
  candidate (and so is its lone member).

The two rules interact — a pulled-in producer that is itself a member can flip a
coordinator on, and a derived-on coordinator that is itself a member can flip a
higher one — so closure iterates to a fixpoint. The closed set only ever grows
(producers and derived-on coordinators are added, never removed once justified),
so the loop terminates in at most one pass per candidate.

The same function drives both surfaces: the live panel (force-check and lock
producers, reflect coordinator state as the developer toggles) and the backend
breadth turn (authoritative resolution of survivors before tier analysis). It is
idempotent on an already-closed set, so re-running it on the panel's submitted
value is a safe backstop.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from spec4.agentifier.scout import Candidate


@dataclass
class ClosureResult:
    """Outcome of closing a breadth selection to a fixpoint.

    ``selected`` is the resolved feature set: developer intent, plus auto-added
    producers, plus derived-on coordinators, minus derived-off coordinators.
    ``required_producers`` is every candidate held in by a ``requires`` edge from
    a selected dependent (may include a coordinator that a dependent requires).
    ``coordinators`` is every name that coordinates >= 1 member in the pool.
    """

    selected: set[str] = field(default_factory=set)
    required_producers: set[str] = field(default_factory=set)
    coordinators: set[str] = field(default_factory=set)

    @property
    def locked(self) -> set[str]:
        """Names the developer may not toggle in the panel.

        Required producers are locked on (a selected dependent needs them); every
        coordinator is locked because its state is derived, not chosen.
        """
        return self.required_producers | self.coordinators


def close_selection(
    pool: list[Candidate], intent: list[str] | set[str]
) -> ClosureResult:
    """Close ``intent`` over ``pool`` under the requires (R) and coordinator (C)
    rules, to a fixpoint. See the module docstring for the rules."""
    by_name = {c.name: c for c in pool}

    members_by_coord: dict[str, list[str]] = defaultdict(list)
    for c in pool:
        if c.composed_under:
            members_by_coord[c.composed_under].append(c.name)
    # A head is only a *derived* coordinator when it actually coordinates two
    # or more members in the pool. A head with a single member is a normal,
    # directly-selectable candidate (coordinating one thing is not coordination):
    # since it could never reach the >= 2-member threshold below, treating it as
    # a coordinator would lock it and leave it permanently unselectable. Its lone
    # member likewise stays a normal candidate (keeping its "Part of ..." note).
    # The label must also be a real pool candidate — the Composer materialises
    # every coordinator before the panel, so a label with members but no
    # candidate should not occur; guard anyway so a malformed pool degrades to
    # "no coordinator" rather than erroring.
    coordinators = {
        label
        for label, members in members_by_coord.items()
        if label in by_name and len(members) >= 2
    }

    # Seed: developer intent, restricted to real, non-coordinator candidates.
    # Coordinators are derived, never chosen, so they never enter from intent.
    selected: set[str] = {n for n in intent if n in by_name and n not in coordinators}
    required: set[str] = set()

    changed = True
    while changed:
        changed = False

        # R — requires-closure: a selected dependent pulls in its producers,
        # each of which is then locked on.
        for name in list(selected):
            for producer in by_name[name].requires:
                if producer not in by_name:
                    continue  # dangling target; already degraded upstream
                if producer not in required:
                    required.add(producer)
                    changed = True
                if producer not in selected:
                    selected.add(producer)
                    changed = True

        # C — coordinator toggle: on iff >= 2 members are in the closed set, or
        # the coordinator is itself required by a selected dependent.
        for coord in coordinators:
            present = sum(1 for m in members_by_coord[coord] if m in selected)
            should_be_on = present >= 2 or coord in required
            if should_be_on and coord not in selected:
                selected.add(coord)
                changed = True
            elif not should_be_on and coord in selected:
                selected.discard(coord)
                changed = True

    return ClosureResult(
        selected=selected,
        required_producers=required,
        coordinators=coordinators,
    )


def pool_from_dicts(dicts: list[dict[str, Any]]) -> list[Candidate]:
    """Rebuild a minimal candidate pool from persisted ``agentifier_scout_pool``
    dicts for closure use only.

    Only the three fields closure reads — ``name`` / ``composed_under`` /
    ``requires`` — are load-bearing; the others are filled with inert defaults so
    the UI surfaces can close a selection without importing the full agentifier
    reconstruction (and its heavier import graph).
    """
    pool: list[Candidate] = []
    for d in dicts:
        name = str(d.get("name", ""))
        if not name:
            continue
        pool.append(
            Candidate(
                name=name,
                linked_vision_features=[],
                scope=str(d.get("scope", "feature")),
                rough_description="",
                composed_under=str(d.get("composed_under", "") or ""),
                requires=[str(r) for r in (d.get("requires") or [])],
            )
        )
    return pool