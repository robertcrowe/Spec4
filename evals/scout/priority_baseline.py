"""Phase-priority probe over saved Agentifier draws (dev tooling).

No LLM. Measures the *quality of the priority assignment* on a finished draw.
Originally the pre-Prioritizer baseline; it now scores post-Prioritizer draws on
the same axes, so a before/after is a matter of which draw it is pointed at. Reads a saved
draw dir (``vision.json`` + ``ai_features.json``) and reports, per draw:

  * distribution — how many features sit at each priority;
  * requires-inversions — a consumer scheduled EARLIER than a producer it
    consumes, i.e. an unbuildable edge;
  * coordinator incoherence — a coordinator whose priority is not the priority
    of its SECOND-earliest member (D-PP7-R rule 3(iv)). Coordination begins to
    exist only once two members are on — the same threshold ``panel_closure``
    uses to derive a head — so a head scheduled before that has nothing to
    coordinate, and one scheduled after leaves its members headless. Groups with
    fewer than two surfaced members are skipped: no head is derived for them.
  * steel-thread closure — whether the ``steel_thread`` set is closed under
    ``requires`` (guaranteed by D-PP7 rule 2 once normalization lands; today it
    is not);
  * invalid — features whose ``phase_priority`` is missing or off-enum.

Scoping rules, which matter for the numbers to mean anything:

  * Injected infrastructure (``kind == "infrastructure"``) is excluded from the
    distribution and from the coherence checks. It is pinned ``steel_thread`` by
    D-I6, so counting it would inflate the steel-thread band with substrate the
    developer never chose.
  * Infra IS resolved as a ``requires`` target, because a feature legitimately
    requires substrate. Infra is a source node at the earliest priority, so such
    an edge can never invert — it simply never fires.
  * A ``requires`` target naming no feature in the draw is reported as unresolved
    rather than counted as an inversion. Edges are persisted raw (D-EP2 option A),
    so danglers are expected.
  * A draw whose features ALL share one priority is flagged DEGENERATE. Both
    ordering checks are vacuous there — no producer can precede a consumer and no
    head can precede a member — so zero findings carries no information. Read a
    degenerate draw as unmeasured, not as healthy.

Before the Prioritizer, ``phase_priority`` was authored per-feature by the Spec
Drafter, which saw one feature per call and no edges at all: inversions and
incoherence were unbounded by construction, and ``steel_thread`` counts ranged
from 0 to 5 across six draws.

After it, normalization guarantees zero inversions — rule 2 runs last, to a
fixpoint — so a nonzero ``invert`` column is a genuine regression. It does NOT
guarantee zero ``incoh``: where a coordinator is required by an earlier
consumer, rule 2 takes precedence over rule 3(iv) and the head is left off its
pivot on purpose. Post-Prioritizer, ``incoh > 0`` reports that rule 2 overrode
rule 3 somewhere, which is worth reading rather than fixing.

Run from ``evals/scout/`` so sibling modules import:

    python priority_baseline.py <draw_dir> [<draw_dir> ...]

where each dir holds ``vision.json`` + ``ai_features.json``.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fanout_baseline import surfaced_candidates  # noqa: E402 (script dir, not a package)

# The ratified enum, cheapest/earliest first. Index == build-order rank.
PRIORITIES = ("steel_thread", "mvp", "v2", "future")
_RANK = {p: i for i, p in enumerate(PRIORITIES)}

INVALID = "<invalid>"


def priority_of(feature: dict[str, Any]) -> str:
    """The feature's declared priority, or ``INVALID`` when absent/off-enum.

    Deliberately does NOT default to ``mvp``. Every downstream reader in ``src``
    silently defaults (``.get("phase_priority", "mvp")``), which is exactly what
    hides the defect this probe is meant to count.
    """
    value = feature.get("phase_priority")
    if isinstance(value, str) and value in _RANK:
        return value
    return INVALID


def _rank(priority: str) -> int | None:
    return _RANK.get(priority)


@dataclass
class Inversion:
    """A ``requires`` edge whose producer is scheduled after its consumer."""

    consumer: str
    consumer_priority: str
    producer: str
    producer_priority: str

    def __str__(self) -> str:
        return (
            f"{self.consumer} ({self.consumer_priority}) requires "
            f"{self.producer} ({self.producer_priority})"
        )


@dataclass
class Incoherence:
    """A coordinator whose priority != that of its second-earliest member."""

    coordinator: str
    coordinator_priority: str
    pivot_member: str
    pivot_priority: str

    @property
    def direction(self) -> str:
        early = _RANK[self.coordinator_priority] < _RANK[self.pivot_priority]
        return "too early — nothing to coordinate yet" if early else "too late — members headless"

    def __str__(self) -> str:
        return (
            f"{self.coordinator} ({self.coordinator_priority}) heads a group whose "
            f"2nd member arrives at {self.pivot_priority} (via {self.pivot_member}) "
            f"[{self.direction}]"
        )


@dataclass
class PriorityReport:
    """Everything measured for one draw."""

    distribution: Counter[str] = field(default_factory=Counter)
    invalid: list[str] = field(default_factory=list)
    inversions: list[Inversion] = field(default_factory=list)
    incoherent: list[Incoherence] = field(default_factory=list)
    unclosed_steel: list[Inversion] = field(default_factory=list)
    unresolved: list[tuple[str, str]] = field(default_factory=list)
    singleton_heads: list[str] = field(default_factory=list)
    n_features: int = 0
    n_edges: int = 0

    @property
    def steel_closed(self) -> bool:
        """True when no steel_thread feature requires a later-scheduled node."""
        return not self.unclosed_steel

    @property
    def degenerate(self) -> bool:
        """True when every surfaced feature carries the same priority.

        Both ordering checks are vacuously satisfied in that case. Zero findings
        on a degenerate draw means the draw is unmeasured, NOT that it is sound.
        """
        return len([p for p, n in self.distribution.items() if n]) <= 1


def analyze(features: list[dict[str, Any]]) -> PriorityReport:
    """Measure priority coherence across one draw's feature set.

    ``features`` is the full ``ai_features`` list, infrastructure included; infra
    is partitioned out for reporting but kept resolvable as a requires target.
    """
    report = PriorityReport()

    # Resolve edge targets against EVERY node, infra included.
    all_priority = {f.get("name", ""): priority_of(f) for f in features if f.get("name")}

    surfaced = surfaced_candidates(features)
    report.n_features = len(surfaced)

    for f in surfaced:
        name = f.get("name", "")
        p = priority_of(f)
        report.distribution[p] += 1
        if p == INVALID:
            report.invalid.append(name)

    # requires-inversions: producer scheduled after the consumer that needs it.
    for f in surfaced:
        consumer = f.get("name", "")
        cp = priority_of(f)
        for producer in f.get("requires") or []:
            report.n_edges += 1
            if producer not in all_priority:
                report.unresolved.append((consumer, producer))
                continue
            pp = all_priority[producer]
            cr, pr = _rank(cp), _rank(pp)
            if cr is None or pr is None:
                continue  # an invalid priority is reported on its own, not here
            if pr > cr:
                inv = Inversion(consumer, cp, producer, pp)
                report.inversions.append(inv)
                if cp == "steel_thread":
                    report.unclosed_steel.append(inv)

    # Coordinator incoherence (D-PP7-R rule 3(iv)): a head's priority is the
    # priority at which its SECOND member arrives — the point at which there is
    # coordination to do, matching panel_closure's >=2-member derivation rule.
    members: dict[str, list[str]] = {}
    for f in surfaced:
        head = f.get("composed_under") or ""
        if head:
            members.setdefault(head, []).append(f.get("name", ""))

    for head, group in members.items():
        hp = all_priority.get(head)
        hr = _rank(hp) if hp else None
        if hr is None:
            continue  # dangling or invalid head — not an incoherence finding
        ranked = [(m, _rank(all_priority.get(m, INVALID))) for m in group]
        ranked = sorted(((m, r) for m, r in ranked if r is not None), key=lambda t: t[1])
        if len(ranked) < 2:
            # No head is derived for a one-member group; nothing to check.
            report.singleton_heads.append(head)
            continue
        pivot, pr = ranked[1]  # second-earliest member
        if hr != pr:
            report.incoherent.append(
                Incoherence(head, hp, pivot, all_priority[pivot])
            )

    return report


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _load(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())


def _features_list(raw: Any) -> list[dict[str, Any]]:
    return raw.get("ai_features", []) if isinstance(raw, dict) else raw


def _find_draw(directory: Path) -> Path | None:
    features = directory / "ai_features.json"
    return features if features.exists() else None


def _draw_report(label: str, rep: PriorityReport) -> str:
    dist = "  ".join(
        f"{p}={rep.distribution.get(p, 0)}"
        for p in PRIORITIES
        if rep.distribution.get(p, 0)
    ) or "(none)"
    lines = [f"  {label}", f"    features: {rep.n_features}   edges: {rep.n_edges}"]
    lines.append(f"    priorities: {dist}")
    if rep.degenerate:
        lines.append(
            "    ⚠ DEGENERATE — one priority for every feature. Both ordering checks "
            "below are vacuous; this draw is unmeasured, not sound."
        )
    if rep.invalid:
        lines.append(f"    invalid ({len(rep.invalid)}): {', '.join(rep.invalid)}")
    if rep.inversions:
        lines.append(f"    requires-inversions ({len(rep.inversions)}):")
        lines.extend(f"      ✗ {inv}" for inv in rep.inversions)
    if rep.incoherent:
        lines.append(f"    coordinator incoherence ({len(rep.incoherent)}):")
        lines.extend(f"      ✗ {inc}" for inc in rep.incoherent)
    lines.append(
        f"    steel_thread closed under requires: {'yes' if rep.steel_closed else 'NO'}"
    )
    if rep.singleton_heads:
        lines.append(
            f"    one-member groups, no head derived ({len(rep.singleton_heads)}): "
            + ", ".join(rep.singleton_heads)
        )
    if rep.unresolved:
        pairs = ", ".join(f"{c}→{p}" for c, p in rep.unresolved)
        lines.append(f"    unresolved requires targets ({len(rep.unresolved)}): {pairs}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase-priority probe over saved Agentifier draws "
        "(each dir must hold ai_features.json; vision.json is not required)."
    )
    parser.add_argument(
        "draw_dirs",
        nargs="+",
        help="One or more draw directories; the dir name is used as the label.",
    )
    args = parser.parse_args(argv)

    rows: list[tuple[str, PriorityReport]] = []
    print("Phase-priority coherence over saved draws (offline, no LLM)\n")
    for d in args.draw_dirs:
        directory = Path(d)
        found = _find_draw(directory)
        if found is None:
            print(f"  {directory.name}: missing ai_features.json — skipped\n")
            continue
        rep = analyze(_features_list(_load(found)))
        rows.append((directory.name, rep))
        print(_draw_report(directory.name, rep))
        print()

    if rows:
        print("  Summary")
        header = (
            f"    {'draw':<16}{'feat':>5}{'steel':>7}{'mvp':>5}{'v2':>4}"
            f"{'future':>8}{'invalid':>9}{'invert':>8}{'incoh':>7}{'closed':>8}{'degen':>7}"
        )
        print(header)
        for label, rep in rows:
            d = rep.distribution
            print(
                f"    {label:<16}{rep.n_features:>5}{d.get('steel_thread', 0):>7}"
                f"{d.get('mvp', 0):>5}{d.get('v2', 0):>4}{d.get('future', 0):>8}"
                f"{len(rep.invalid):>9}{len(rep.inversions):>8}"
                f"{len(rep.incoherent):>7}{'yes' if rep.steel_closed else 'NO':>8}"
                f"{'YES' if rep.degenerate else '-':>7}"
            )
        total_inv = sum(len(r.inversions) for _, r in rows)
        total_inc = sum(len(r.incoherent) for _, r in rows)
        total_bad = sum(len(r.invalid) for _, r in rows)
        n_degen = sum(1 for _, r in rows if r.degenerate)
        print(
            f"\n    invert > 0 ⇒ a producer is scheduled after a consumer that needs it "
            f"(unbuildable edge); incoh > 0 ⇒ a coordinator's priority is not that of "
            f"its 2nd-earliest member; invalid > 0 ⇒ the Spec Drafter emitted a missing "
            f"or off-enum priority that every reader in src silently defaults to mvp."
            f"\n    degen = YES ⇒ ordering checks are vacuous; ignore that row's zeros."
            f"\n    totals: inversions={total_inv}  incoherent={total_inc}  "
            f"invalid={total_bad}  degenerate_draws={n_degen}/{len(rows)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())