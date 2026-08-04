"""Linker sub-agent for Agentifier.

Wires the Scout graph contract — ``composed_under`` and ``requires`` — over the
closed candidate set Scout surfaced, in a single pass, before the Composer
groups by it. Scout surfaces nodes; the Linker owns edges; the Composer
materialises coordinators from the labels.

Splitting edge inference out of Scout is deliberate: an edge is a function of the
*complete* node set (which candidate consumes which other candidate's output),
and a node-at-a-time generator cannot compute a function of a set while it is
still emitting the set. Running the wiring as its own pass over the closed list
gives the graph a single owner and a checkable, closed-world contract.

The Linker emits an *overlay* — per candidate, ``composed_under`` and
``requires`` — never touching any other field and never adding, dropping, or
renaming a node. ``requires`` targets are closed to emitted candidate names; a
``composed_under`` label may be an existing candidate or a coined snake_case
coordinator (the Composer crowns a headless >=2-member label). Empty or
unreadable output passes through edgeless (the panel simply auto-links nothing);
both cases are logged, and the orchestrator surfaces them in the chat.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from spec4.agentifier.scout import Candidate
from spec4.agentifier.subagents import validate_dataclass_input
from spec4.llm import complete

_log = logging.getLogger(__name__)

_LINKER_SYSTEM_PROMPT = """\
You are the Linker for Agentifier. You are given the COMPLETE list of AI
capability candidates another agent surfaced for one project — every node that
exists. Your one job is to wire the dependency graph over that fixed list: which
candidates depend on which, and which are members of a shared coordinated
capability. You do NOT add, remove, rename, or re-describe candidates; you only
declare edges between the ones you are given.

There are two edge types.

`requires` — candidate B requires candidate A when B consumes A's output: A must
run first and produce something B takes as input. Read each candidate's
description for what it takes in and what it produces, and connect a consumer to
its producer(s). A `requires` target MUST be the exact name of another candidate
in the list — never invent a name, and never point a candidate at itself. List
only the DIRECT producers a candidate consumes; do not chain transitively (if C
consumes B and B consumes A, then C requires B, not A).

`requires` also covers indirect consumption through a shared store. When one
candidate writes, saves, indexes, or populates a persistent library, store, or
collection, and another candidate searches, reads, retrieves, or ranks over that
same library, the reader `requires` the writer — even when the reader's direct
input is a query or a single item rather than the writer's output. The writer of
the stored content runs first; the reader `requires` it, never the reverse. When
two candidates both act on a newly-saved item, the one that produces the stored
or normalized content is the producer, and the one that inspects, compares, or
searches it is the consumer.

`composed_under` — set this on candidates that are members of ONE coordinated
capability: an orchestrator directing specialists, a fixed pipeline whose stages
feed each other, a tool-using loop, or agents negotiating for their owners. Set
each member's `composed_under` to the coordinator's name — either an existing
candidate in the list that acts as the coordinator, or, when no candidate names
the whole, a plain snake_case name you coin for it. A coordinator needs at least
TWO members; never coin a coordinator for a single candidate.

Be conservative about composition. Group members only when they genuinely form
one coordinated capability with a shared purpose — never crown unrelated peers
just because they touch the same domain. When you are unsure whether candidates
compose, leave them flat (no `composed_under`). Under-grouping is safe; inventing
a coordinator that should not exist is not. The same caution applies to
`requires`: assert an edge only when one candidate truly consumes another's
output, not merely because they are topically related.

Before you return, run a consolidation pass for shattered capabilities. The
conservative default above prevents crowning unrelated peers, but it must not
leave one capability split across rows. Scan for this fingerprint: two or more
candidates naming the SAME single vision feature. Within each such group, ask of
every member — would a user invoke this on its own, as a distinct request, or
does it only run as a step in fulfilling the shared capability? Set
`composed_under` on every candidate that only serves the others. To pick the
coordinator, first look for a candidate already in the group whose own
description names or runs the whole — an orchestrator, or a capability that
manages, routes, or coordinates the others. If one exists, crown it: point the
group's members at it, and do NOT coin a new parent over it (crowning an
existing candidate never means giving it its own `composed_under` within this
group). Only when no candidate plays that role do you coin a plain snake_case
coordinator name (a coined coordinator needs at least TWO members). A
step you already linked with `requires` is still a member when it feeds only that
shared capability — `requires` records data-flow, `composed_under` records
membership; set both. Two limits: a candidate that many candidates across
DIFFERENT capabilities require is shared substrate, not a member — leave it flat;
and a candidate a user truly invokes on its own stays standalone even when it
shares a feature. When unsure whether a shared-feature candidate is a distinct
capability or a step, treat it as a step and group it — one whole capability with
rich internals is the right default. This applies only to un-splitting a
shattered capability; it never groups genuinely distinct or breadth candidates.

Return ONLY a JSON object — no preamble, no explanation, no markdown fence —
mapping each candidate that has at least one edge to its edges. Candidates with
no edges may be omitted. Use this shape:
{
  "consumer_candidate": {"composed_under": "", "requires": ["producer_candidate"]},
  "member_candidate": {"composed_under": "coordinator_name", "requires": []}
}
"""


@dataclass
class LinkerInput:
    candidates: list[Candidate]
    vision_purpose: str
    llm_config: dict[str, Any]


@dataclass
class EdgeOverlay:
    """The edges the Linker assigns to one candidate (edge fields only)."""

    composed_under: str = ""
    requires: list[str] = field(default_factory=list)


class LinkerOutcome(str, Enum):
    """Why the Linker overlay came out the way it did.

    ``OK`` — a readable overlay that carries at least one edge.
    ``EMPTY`` — a readable overlay that carries no edges (the candidates were
    assessed as independent; legitimate for a genuinely flat feature set).
    ``UNREADABLE`` — no JSON object could be parsed, even after one reparse.
    """

    OK = "ok"
    EMPTY = "empty"
    UNREADABLE = "unreadable"


@dataclass
class LinkerOutput:
    overlay: dict[str, EdgeOverlay]
    outcome: LinkerOutcome = LinkerOutcome.OK


# ---------------------------------------------------------------------------
# Graph-contract edge integrity (contract §6) — relocated from Scout so it runs
# on the Linker's overlay-merged output, which is now the sole edge source.
# ---------------------------------------------------------------------------


def _break_requires_cycles(candidates: list[Candidate]) -> None:
    """Break any cycle in the ``requires`` DAG at its back-edge (contract §6).

    Only candidate->candidate edges can form a cycle; ``requires`` entries that
    point at a synthesizable head-absent coordinator are sinks (no outgoing
    edges) and cannot participate. A single depth-first pass records every
    back-edge (an edge to a node still on the recursion stack); removing that
    set afterwards is guaranteed to leave an acyclic graph.
    """
    by_name = {c.name: c for c in candidates}
    white, grey, black = 0, 1, 2
    colour = dict.fromkeys(by_name, white)
    back_edges: set[tuple[str, str]] = set()

    def visit(start: str) -> None:
        # Explicit (node, next-requires-index) stack, so deep chains do not
        # risk Python's recursion limit.
        stack: list[tuple[str, int]] = [(start, 0)]
        colour[start] = grey
        while stack:
            node, i = stack[-1]
            reqs = by_name[node].requires
            if i >= len(reqs):
                colour[node] = black
                stack.pop()
                continue
            stack[-1] = (node, i + 1)
            target = reqs[i]
            if target not in by_name:
                continue  # sink: synthesizable coordinator, already validated
            if colour[target] == grey:
                back_edges.add((node, target))
            elif colour[target] == white:
                colour[target] = grey
                stack.append((target, 0))

    for name in by_name:
        if colour[name] == white:
            visit(name)

    for node, target in back_edges:
        _log.warning("Linker edge: breaking requires cycle %r -> %r", node, target)
        cand = by_name[node]
        cand.requires = [r for r in cand.requires if r != target]


def _normalize_edges(candidates: list[Candidate]) -> list[Candidate]:
    """Enforce the graph-contract edge integrity (contract §6).

    Deterministic, the same spirit as the phantom-link checker: no hard
    failures, every violation degrades safely. Candidates are mutated in place
    and the same list is returned.

    * ``composed_under`` self-edges are cleared; a dangler (a label with no
      matching candidate *and* fewer than two members) degrades to flat, so a
      missing edge yields silent under-crowning, never a wrong grouping.
    * ``requires`` self-references and danglers are dropped. A valid target is
      an emitted candidate, a synthesizable head-absent coordinator (>=2
      members sharing a name that no candidate carries), or a cross-feature
      (itself an emitted candidate).
    * ``requires`` cycles are broken at the back-edge.
    * Scope is normalized (not rejected): a member (``composed_under`` set) is
      ``sub_feature``; an emitted head (referenced by a surviving
      ``composed_under`` and not itself a member) is ``feature``.
    """
    names = {c.name for c in candidates}

    # composed_under: drop self-edges first, then degrade danglers to flat.
    for c in candidates:
        if c.composed_under == c.name:
            c.composed_under = ""
    member_counts = Counter(c.composed_under for c in candidates if c.composed_under)
    for c in candidates:
        label = c.composed_under
        if label and label not in names and member_counts[label] < 2:
            _log.warning(
                "Linker edge: degrading dangling composed_under %r on %r to flat",
                label,
                c.name,
            )
            c.composed_under = ""

    # A requires target may resolve to an emitted candidate, a synthesizable
    # head-absent coordinator, or a cross-feature (an emitted candidate). Only
    # labels with >=2 members and no matching candidate get synthesized later.
    surviving = Counter(c.composed_under for c in candidates if c.composed_under)
    synthesizable = {lbl for lbl, n in surviving.items() if lbl not in names and n >= 2}
    valid_targets = names | synthesizable

    for c in candidates:
        cleaned: list[str] = []
        for r in c.requires:
            if r == c.name:
                _log.warning("Linker edge: dropping self requires on %r", c.name)
                continue
            if r not in valid_targets:
                _log.warning("Linker edge: dropping dangling requires %r on %r", r, c.name)
                continue
            if r not in cleaned:
                cleaned.append(r)
        c.requires = cleaned

    _break_requires_cycles(candidates)

    # Scope consistency: normalize rather than reject. A member is a
    # sub_feature; an emitted head is a feature. composed_under wins, so a
    # nested coordinator (member of a higher coordinator) stays sub_feature.
    referenced = {c.composed_under for c in candidates if c.composed_under}
    for c in candidates:
        if c.composed_under:
            c.scope = "sub_feature"
        elif c.name in referenced:
            c.scope = "feature"

    return candidates


# ---------------------------------------------------------------------------
# Overlay application + parsing
# ---------------------------------------------------------------------------


def apply_overlay(
    candidates: list[Candidate], overlay: dict[str, EdgeOverlay]
) -> list[Candidate]:
    """Merge the Linker overlay onto ``candidates`` (edge fields only), then
    normalise the graph.

    The overlay is authoritative for every candidate: a candidate the Linker
    omitted is set edgeless, so no stray upstream edge survives. Candidates are
    mutated in place and the same list is returned, contract-valid.
    """
    for c in candidates:
        edges = overlay.get(c.name)
        if edges is not None:
            c.composed_under = edges.composed_under
            c.requires = list(edges.requires)
        else:
            c.composed_under = ""
            c.requires = []
    return _normalize_edges(candidates)


def _parse_overlay(raw: str) -> tuple[dict[str, EdgeOverlay], LinkerOutcome]:
    """Extract and parse the JSON overlay object from the LLM response.

    Returns the overlay together with a :class:`LinkerOutcome`: ``OK`` when it
    carries at least one edge, ``EMPTY`` for a readable object with no edges,
    ``UNREADABLE`` when no JSON object could be parsed.
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
        overlay: dict[str, EdgeOverlay] = {}
        for name, edges in data.items():
            if not isinstance(edges, dict):
                continue
            overlay[str(name)] = EdgeOverlay(
                composed_under=str(edges.get("composed_under") or ""),
                requires=[str(r) for r in (edges.get("requires") or [])],
            )
        has_edge = any(eo.composed_under or eo.requires for eo in overlay.values())
        return overlay, (LinkerOutcome.OK if has_edge else LinkerOutcome.EMPTY)
    return {}, LinkerOutcome.UNREADABLE


def _extract_json_object(text: str) -> str | None:
    """Return the first top-level JSON object found in text, or None."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group() if match else None


def _format_candidates_block(candidates: list[Candidate], vision_purpose: str) -> str:
    """Render the closed candidate list (name, vision features, description)
    plus the one-line project purpose as the Linker's user message."""
    lines: list[str] = []
    if vision_purpose:
        lines.append(f"Project purpose: {vision_purpose}\n")
    lines.append("Candidates (the complete, fixed list — wire edges over exactly these):\n")
    for c in candidates:
        vision = ", ".join(c.linked_vision_features) or "—"
        lines.append(
            f"- {c.name} (vision: {vision}): {c.rough_description}"
        )
    lines.append("\nReturn the edge overlay as a JSON object.")
    return "\n".join(lines)


class LinkerAgent:
    """Request/response sub-agent that wires the graph over a closed candidate
    set, emitting an edge overlay. One reparse on a hard JSON-parse failure."""

    name = "linker"

    async def run(self, input: LinkerInput) -> LinkerOutput:  # noqa: A002
        validate_dataclass_input(input, LinkerInput)

        user_content = _format_candidates_block(
            input.candidates, input.vision_purpose
        )
        llm_config = input.llm_config

        overlay: dict[str, EdgeOverlay] = {}
        outcome = LinkerOutcome.UNREADABLE
        # Draw, and reparse ONCE on a hard parse failure (D-L6). A readable but
        # empty overlay is a legitimate result (flat feature set) — not retried.
        for _ in range(2):
            response = complete(
                llm_config=llm_config,
                messages=[
                    {"role": "system", "content": _LINKER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                agent_name="linker",
                stream=False,
            )
            raw = (response.choices[0].message.content or "").strip()
            overlay, outcome = _parse_overlay(raw)
            if outcome is not LinkerOutcome.UNREADABLE:
                break

        return LinkerOutput(overlay=overlay, outcome=outcome)