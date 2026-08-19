"""Prioritizer sub-agent for Agentifier.

Assigns ``phase_priority`` over the closed AI-feature set, in a single pass,
after cross-cutting review and before infrastructure expansion.

Splitting priority authorship out of the Spec Drafter is deliberate, and is the
same argument the Linker makes for edges. Priority is a *relational* property:
``steel_thread`` names the thinnest end-to-end path through **this** system and
``mvp`` names what ships in the first release **relative to everything else on
the table**. Neither is a predicate on a single node. The Spec Drafter sees one
feature per call and cannot see the others, so it could only ever answer "is this
feature important?" — to which, for anything that survived Scout, the panel, and
tier review, the answer is always yes. Measured over six draws, its
``steel_thread`` count ranged from 0 to 5 with no relation to draw size. Running
priority as its own pass over the closed list gives the field a single owner and
a checkable, closed-world contract.

The Prioritizer emits an *overlay* — per feature, one priority string — never
touching any other field and never adding, dropping, or renaming a node. A
deterministic normalization pass then repairs the overlay against the graph the
Linker already wired (D-PP7):

1. A missing or off-enum value degrades to ``mvp``.
2. **requires-monotonicity** — if B requires A, A is scheduled no later than B.
   Repaired by *promoting the producer*, never by demoting the consumer:
   demotion would silently drop a feature the developer wanted early.
3. **coordinator placement (D-PP7-R rule 3(iv))** — a coordinator's priority is
   that of its *second-earliest* member. Coordination begins to exist only once
   two members are on, which is the same threshold ``panel_closure`` uses to
   derive a head; a head placed before that has nothing to coordinate, and one
   placed after leaves its members headless.

Rule 2 takes precedence over rule 3 where they disagree: a ``requires`` edge is a
hard build dependency, while ``composed_under`` is organizational. Empty or
unreadable output degrades to an all-``mvp`` assignment (normalization still
runs); both cases are logged, and the orchestrator surfaces them in the chat.

Features tracing back to a capability the vision names under ``key_features_mvp``
are marked ``[MVP]`` in the prompt and must not be deferred (D-PP14). This is a
prompt rule rather than a normalization clamp: deferring something the developer
wrote down months ago is a decision they are entitled to make, and a clamp has no
way to ask. If the model defers one anyway, that is a signal worth seeing.

Carried-forward features (revision rounds) are already built. They enter the
prompt as read-only context, receive no assignment, and normalization never
mutates them (D-PP11). For monotonicity they count as already shipped — earlier
than any priority — so a new feature requiring a carried one is never an
inversion.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from spec4.agentifier.subagents import validate_dataclass_input
from spec4.llm import complete_stream

_log = logging.getLogger(__name__)

# The ratified enum, earliest first. Index == build-order rank.
PRIORITIES: tuple[str, ...] = ("steel_thread", "mvp", "v2", "future")
_RANK: dict[str, int] = {p: i for i, p in enumerate(PRIORITIES)}

#: What a missing or off-enum value degrades to (D-PP7 rule 1).
DEFAULT_PRIORITY = "mvp"

#: Carried-forward features are already implemented — earlier than anything this
#: round can schedule, so they never invert against a new consumer.
_BUILT_RANK = -1

#: Rule 2 only ever promotes (rank strictly decreases) so it converges on its
#: own. Rule 3 assigns an equality and may demote, so the two together are not
#: guaranteed monotone. The alternation is capped; on non-convergence rule 2 is
#: enforced last, because an unbuildable edge is the failure that matters.
_MAX_PASSES = 8


_PRIORITIZER_SYSTEM_PROMPT = """\
You are the Prioritizer for Agentifier. You are given the COMPLETE list of AI
features selected for one project — every node that exists — together with the
dependency graph another agent already wired over them. Your one job is to
assign each feature a build-order priority. You do NOT add, remove, rename, or
re-describe features; you only assign one of four values to each.

The four values, earliest first:

`steel_thread` — implemented FIRST, before the MVP. These are the features an
end-to-end path runs through: the thinnest slice that proves the system works
from one end to the other, and the foundation the MVP is then built on top of.
This is a SLICE, not a ranking of importance. Not every dependency of an MVP
feature belongs here — only those on the thinnest working path. Usually 1-3
features. Every system has such a path: never leave this empty.

`mvp` — required for the first release. Most features belong here. A feature
being important, or being depended upon, does not by itself make it a steel
thread; it makes it `mvp`.

`v2` — genuinely valuable, but deliberately deferred past the first release.

`future` — speculative; worth recording, not worth scheduling.

Some features are marked `[MVP]`. Those are capabilities the project's own vision
document names as part of the first release. The developer has already committed
to shipping them, so they belong in `steel_thread` or `mvp` — never in `v2` or
`future`. If you believe one should be deferred, put it in `mvp` anyway; that
decision is the developer's to make, not yours. Features WITHOUT the mark carry
no such commitment and may be scheduled wherever they best belong, including
`v2` and `future`.

Two graph rules constrain you, and the graph is given to you:

- If feature A appears in feature B's `requires` list, then A must be scheduled
  no LATER than B. B cannot be built before the thing it consumes exists.
- A coordinator (a feature that other features name in `composed_under`) is
  scheduled when its SECOND member arrives. With only one member on there is
  nothing to coordinate; the coordinator is not built yet.

Features listed as ALREADY BUILT are context only. Do not assign them a
priority and do not include them in your output; they exist already, so nothing
that requires them is blocked.

Return ONLY a JSON object — no preamble, no explanation, no markdown fence —
mapping every feature name to exactly one of the four values. Use this shape:
{
  "some_feature": "steel_thread",
  "another_feature": "mvp"
}
"""


@dataclass
class PrioritizerInput:
    features: list[dict[str, Any]]
    vision_purpose: str
    llm_config: dict[str, Any]
    carried_forward: list[dict[str, Any]] = field(default_factory=list)
    #: Names from the vision's ``key_features_mvp``. A feature whose
    #: ``linked_vision_features`` meets this set is committed to the first
    #: release (D-PP14) and is marked ``[MVP]`` in the prompt.
    mvp_vision_features: list[str] = field(default_factory=list)
    #: Receipt-counter hook (D-PH9): called with each streamed text delta as
    #: it arrives, so the orchestrator can publish liveness while the response
    #: is drained internally. ``None`` drains silently (the prior behavior).
    on_chunk: Callable[[str], None] | None = field(default=None)


class PrioritizerOutcome(str, Enum):
    """Why the Prioritizer overlay came out the way it did.

    ``OK`` — a readable overlay carrying at least one valid assignment.
    ``EMPTY`` — a readable object with no usable assignment in it.
    ``UNREADABLE`` — no JSON object could be parsed, even after one reparse.
    """

    OK = "ok"
    EMPTY = "empty"
    UNREADABLE = "unreadable"


@dataclass
class PrioritizerOutput:
    overlay: dict[str, str]
    outcome: PrioritizerOutcome = PrioritizerOutcome.OK


# ---------------------------------------------------------------------------
# Deterministic normalization (D-PP7)
# ---------------------------------------------------------------------------


def _members_by_head(features: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Map each coordinator label to the names of its members.

    Every member counts toward a group's size, carried ones included: a head
    whose second member is already built arrives when its *new* member does. A
    carried head is never repositioned, but that is enforced in
    :func:`_coordinator_pass`, not by hiding its members here.
    """
    heads: dict[str, list[str]] = {}
    for f in features:
        label = f.get("composed_under") or ""
        name = f.get("name") or ""
        if label and name:
            heads.setdefault(label, []).append(name)
    return heads


def _member_rank(
    name: str,
    by_name: dict[str, dict[str, Any]],
    carried_names: frozenset[str],
) -> int | None:
    """Build-order rank of ``name``, or None when it is not a known node."""
    if name in carried_names:
        return _BUILT_RANK
    f = by_name.get(name)
    return _RANK[f["phase_priority"]] if f else None


def _requires_pass(
    features: list[dict[str, Any]],
    by_name: dict[str, dict[str, Any]],
    carried_names: frozenset[str],
) -> bool:
    """Promote every producer scheduled later than a consumer that needs it.

    Runs to its own fixpoint. Promotion only ever lowers a rank, so this
    terminates. Returns True if anything moved.
    """

    def rank(name: str) -> int | None:
        return _member_rank(name, by_name, carried_names)

    moved = False
    changed = True
    while changed:
        changed = False
        for f in features:
            consumer = f.get("name") or ""
            if consumer in carried_names:
                continue
            cr = rank(consumer)
            if cr is None:
                continue
            for producer in f.get("requires") or []:
                pr = rank(producer)
                if pr is None:
                    continue  # dangling target — edges persist raw (D-EP2 A)
                if pr <= cr:
                    continue
                if producer in carried_names:
                    continue  # already built; cannot invert
                _log.warning(
                    "Prioritizer: promoting producer %r from %r to %r — required "
                    "by %r",
                    producer,
                    by_name[producer]["phase_priority"],
                    f["phase_priority"],
                    consumer,
                )
                by_name[producer]["phase_priority"] = f["phase_priority"]
                changed = moved = True
    return moved


def _coordinator_pass(
    by_name: dict[str, dict[str, Any]],
    heads: dict[str, list[str]],
    carried_names: frozenset[str],
) -> bool:
    """Place each coordinator at the priority of its second-earliest member.

    Groups with fewer than two members are skipped: ``panel_closure`` derives no
    head for them. Returns True if anything moved.
    """
    moved = False
    for head, members in heads.items():
        if head in carried_names or head not in by_name:
            continue  # frozen, or a label the Composer never materialised
        member_ranks = (_member_rank(m, by_name, carried_names) for m in members)
        ranks = sorted(r for r in member_ranks if r is not None)
        if len(ranks) < 2:
            continue
        # Clamp: a member already built ranks below steel_thread, but a
        # coordinator can be scheduled no earlier than the first phase.
        pivot = PRIORITIES[max(ranks[1], 0)]
        if by_name[head]["phase_priority"] != pivot:
            _log.warning(
                "Prioritizer: moving coordinator %r from %r to %r — its second "
                "member arrives at %r",
                head,
                by_name[head]["phase_priority"],
                pivot,
                pivot,
            )
            by_name[head]["phase_priority"] = pivot
            moved = True
    return moved


def normalize_priorities(
    features: list[dict[str, Any]],
    carried_names: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Repair ``phase_priority`` across ``features`` against the wired graph.

    Deterministic, the same spirit as ``linker._normalize_edges``: no hard
    failures, every violation degrades safely, every repair logged. Features are
    mutated in place and the same list is returned.

    Rule 1 runs once; rules 2 and 3 alternate to a joint fixpoint. Rule 2 is
    enforced last so that no unbuildable edge survives even if the alternation
    is cut short at ``_MAX_PASSES``.
    """
    by_name = {f["name"]: f for f in features if f.get("name")}

    # Rule 1 — a missing or off-enum value degrades to mvp.
    for f in features:
        if f.get("name") in carried_names:
            continue
        value = f.get("phase_priority")
        if not isinstance(value, str) or value not in _RANK:
            _log.warning(
                "Prioritizer: degrading invalid phase_priority %r on %r to %r",
                value,
                f.get("name", ""),
                DEFAULT_PRIORITY,
            )
            f["phase_priority"] = DEFAULT_PRIORITY

    heads = _members_by_head(features)

    for _ in range(_MAX_PASSES):
        moved = _coordinator_pass(by_name, heads, carried_names)
        moved |= _requires_pass(features, by_name, carried_names)
        if not moved:
            break
    else:
        # Rule 3 assigns an equality and can demote; rule 2 only promotes. The
        # two can in principle chase each other. Rule 2 wins: a requires edge is
        # a hard build dependency, composed_under is organizational.
        _log.warning(
            "Prioritizer: priority normalization did not converge in %d passes; "
            "enforcing requires-monotonicity last",
            _MAX_PASSES,
        )
        _requires_pass(features, by_name, carried_names)

    return features


# ---------------------------------------------------------------------------
# Overlay application + parsing
# ---------------------------------------------------------------------------


def apply_overlay(
    features: list[dict[str, Any]],
    overlay: dict[str, str],
    carried_names: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Merge the Prioritizer overlay onto ``features``, then normalise.

    The overlay is authoritative for every non-carried feature: one the
    Prioritizer omitted is set to :data:`DEFAULT_PRIORITY`, so no stale upstream
    value survives. Carried features keep whatever they already carry. Features
    are mutated in place and the same list is returned, contract-valid.
    """
    for f in features:
        name = f.get("name") or ""
        if name in carried_names:
            continue
        f["phase_priority"] = overlay.get(name, DEFAULT_PRIORITY)
    return normalize_priorities(features, carried_names)


def _parse_overlay(raw: str) -> tuple[dict[str, str], PrioritizerOutcome]:
    """Extract and parse the JSON overlay object from the LLM response.

    Returns the overlay together with a :class:`PrioritizerOutcome`: ``OK`` when
    it carries at least one valid assignment, ``EMPTY`` for a readable object
    with none, ``UNREADABLE`` when no JSON object could be parsed. Off-enum
    values are dropped here rather than carried forward; rule 1 then supplies
    the default.
    """
    for attempt in (raw.strip(), _extract_json_object(raw)):
        if attempt is None:
            continue
        try:
            data = json.loads(attempt)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        overlay: dict[str, str] = {}
        for name, value in data.items():
            if isinstance(value, str) and value in _RANK:
                overlay[str(name)] = value
        return overlay, (
            PrioritizerOutcome.OK if overlay else PrioritizerOutcome.EMPTY
        )
    return {}, PrioritizerOutcome.UNREADABLE


def _extract_json_object(text: str) -> str | None:
    """Return the first top-level JSON object found in text, or None."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group() if match else None


def _format_features_block(
    features: list[dict[str, Any]],
    carried_forward: list[dict[str, Any]],
    vision_purpose: str,
    mvp_vision_features: list[str] | None = None,
) -> str:
    """Render the closed feature list plus its edges as the user message.

    A feature whose ``linked_vision_features`` meets ``mvp_vision_features`` is
    marked ``[MVP]``. Without that mark the model sees only an opaque vision
    label and has no way to know the developer already committed to shipping the
    capability in the first release (D-PP14).

    ``sub_feature`` scopes are never marked. ``linked_vision_features`` records
    *provenance*, not commitment: on a decomposed capability every member traces
    back to the same vision entry, so marking members would brand the whole
    catalog ``[MVP]`` and forbid deferral anywhere. The developer committed to
    the capability, which is the coordinator; how it is broken up underneath is
    Scout's decomposition, not theirs.
    """
    committed = set(mvp_vision_features or ())
    lines: list[str] = []
    if vision_purpose:
        lines.append(f"Project purpose: {vision_purpose}\n")

    if committed:
        lines.append(
            "The vision names these capabilities as part of the first release: "
            + ", ".join(sorted(committed))
            + ". Features tracing back to them are marked [MVP] below.\n"
        )

    if carried_forward:
        names = ", ".join(f.get("name", "") for f in carried_forward)
        lines.append(
            f"ALREADY BUILT (context only — do not assign, do not output): {names}\n"
        )

    lines.append("Features (the complete, fixed list — assign a priority to each):\n")
    for f in features:
        name = f.get("name", "")
        tier = f.get("tier", "")
        desc = f.get("purpose") or f.get("rough_description") or ""
        linked = f.get("linked_vision_features") or []
        vision = ", ".join(linked) or "—"
        vision_committed = bool(committed.intersection(linked)) and (
            f.get("scope") != "sub_feature"
        )
        mark = " [MVP]" if vision_committed else ""
        lines.append(f"- {name}{mark} (tier: {tier}; vision: {vision}): {desc}")
        head = f.get("composed_under") or ""
        if head:
            lines.append(f"    composed_under: {head}")
        requires = f.get("requires") or []
        if requires:
            lines.append(f"    requires: {', '.join(requires)}")

    lines.append("\nReturn the priority overlay as a JSON object.")
    return "\n".join(lines)


class PrioritizerAgent:
    """Request/response sub-agent that assigns build-order priority over a closed
    feature set, emitting an overlay. One reparse on a hard JSON-parse failure."""

    name = "prioritizer"

    async def run(self, input: PrioritizerInput) -> PrioritizerOutput:  # noqa: A002
        validate_dataclass_input(input, PrioritizerInput)

        user_content = _format_features_block(
            input.features,
            input.carried_forward,
            input.vision_purpose,
            input.mvp_vision_features,
        )
        llm_config = input.llm_config

        overlay: dict[str, str] = {}
        outcome = PrioritizerOutcome.UNREADABLE
        # Draw, and reparse ONCE on a hard parse failure. A readable object with
        # no usable assignment is a result, not a retry: rule 1 defaults it.
        for _ in range(2):
            buf: list[str] = []
            for delta in complete_stream(
                llm_config=llm_config,
                messages=[
                    {"role": "system", "content": _PRIORITIZER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                agent_name="prioritizer",
            ):
                buf.append(delta)
                if input.on_chunk is not None:
                    input.on_chunk(delta)
            raw = "".join(buf).strip()
            overlay, outcome = _parse_overlay(raw)
            if outcome is not PrioritizerOutcome.UNREADABLE:
                break

        return PrioritizerOutput(overlay=overlay, outcome=outcome)