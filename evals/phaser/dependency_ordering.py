"""Phase-set probe: dependency ordering (D-PH0f, option c — both graphs).

Dev tooling under ``evals/``. Never wired into the pipeline.

Checks that development items with dependencies are phased *after* (or with)
the things they depend on, over the two dependency graphs on the wire — each
in its own id space, never merged:

**[1] PRODUCT GRAPH** — ``feature_specs.json`` ``dependencies`` (consumer
depends on producer, a validated DAG over product-feature ids).

**[2] AI GRAPH** — ``ai_features.json`` ``requires`` edges (consumer ->
producer over catalog nodes; holds *names*, resolved through the explicit
name->id map with a slug fallback, mirroring ``_phase_coverage``). Includes
feature->infrastructure edges, making this a superset of the in-pipeline
infra-only ordering check. ``composed_under`` is membership, not ordering,
and is not checked.

**The rule (D-DO1, role-aware).** A requires-edge is consumed by the
consumer's *dependency-consuming* phase, not its shell-introduction phase: the
schema guarantees exactly one phase *introduces* an item and every later touch
*extends* it, so a consumer wires its dependencies in by its **last** (max)
declaring phase, while a producer is stood up at its **first** (min) declaring
phase. The ordering is satisfied when ``producer_first <= consumer_last`` — the
producer exists no later than the consumer is fully built (same phase allowed).
This removes the introduced/extended false positive (a consumer whose shell
lands early but whose wiring lands after its producers).

**Staged substrate (D-DO2, surface-to-adjudicate).** A dependency can be met
functionally by a substrate/seed an earlier phase stands up, ahead of the
producer's formal introduction — a genuinely-correct plan the ``<=`` rule
still flags. Whether a given scope_note records such staging is a prose
judgment this probe does not make deterministically (the note names the
establishment, not the producer id, so it cannot be matched by id). So the
verdict stays binary, and every VIOLATION is annotated with the scope_notes
that let a human adjudicate: the consumer's and producer's own notes, plus any
non-empty scope_note on an earlier phase (the "something was staged earlier"
hint). A VIOLATION with *no* earlier scope_notes has no staging evidence and
is the more likely genuine defect.

Scope is declared items only (D-PH0f): prose is not deterministically
checkable. An edge with an undeclared endpoint is reported as such — per
D-PH0b, never silently skipped — and AMBIGUOUS ids count as declared in either
space, annotated.

Usage::

    python3 dependency_ordering.py <draw_dir>
"""

from __future__ import annotations

import sys
from typing import Any

from _load import (
    AMBIGUOUS,
    CAPABILITY,
    PRODUCT,
    capability_name_to_id,
    catalog_nodes,
    declarations,
    first_declaring_phase,
    last_declaring_phase,
    load_draw,
    product_features,
    slug,
)


def _span_str(first: int, last: int) -> str:
    return f"phase {first}" if first == last else f"phases {first}→{last}"


def _scope_note_for(
    decls: list[dict[str, Any]],
    fid: str,
    phase: int | None,
    spaces: tuple[str, ...],
) -> str:
    """The non-empty scope_note on ``fid``'s declaration at ``phase``, if any."""
    if phase is None:
        return ""
    for d in decls:
        if (
            d["id"] == fid
            and d["phase"] == phase
            and d["space"] in spaces
            and d.get("scope_note")
        ):
            return str(d["scope_note"])
    return ""


def _earlier_scope_notes(
    decls: list[dict[str, Any]], before_phase: int
) -> list[tuple[int, str, str]]:
    """Non-empty scope_notes on any phase strictly before ``before_phase``.

    Staged establishment is recorded in a scope_note per the phase schema, but
    which note satisfies a given producer cannot be matched to an id
    deterministically (D-DO2), so surface every earlier scope_note — any id
    space — for a human to adjudicate. Deduped, phase-ordered.
    """
    seen: set[tuple[int, str, str]] = set()
    for d in decls:
        ph = d["phase"]
        note = str(d.get("scope_note") or "")
        if isinstance(ph, int) and ph < before_phase and note:
            seen.add((ph, str(d["id"]), note))
    return sorted(seen)


def _check_edges(
    edges: list[tuple[str, str]],
    decls: list[dict[str, Any]],
    spaces: tuple[str, ...],
    ambiguous: set[str],
) -> None:
    """Report each consumer->producer edge under the role-aware <= rule."""
    if not edges:
        print("  no edges")
        return
    ok = violations = undeclared = 0
    for consumer, producer in edges:
        c_first = first_declaring_phase(decls, consumer, spaces)
        c_last = last_declaring_phase(decls, consumer, spaces)
        p_first = first_declaring_phase(decls, producer, spaces)
        note = "".join(
            f" ({i} ambiguous id)" for i in (consumer, producer) if i in ambiguous
        )
        if c_last is None or p_first is None:
            missing = [
                i for i, ph in ((consumer, c_last), (producer, p_first))
                if ph is None
            ]
            print(
                f"  UNDECLARED-ENDPOINT  {consumer} -> {producer} "
                f"(not declared: {', '.join(missing)}){note}"
            )
            undeclared += 1
        elif p_first <= c_last:
            print(
                f"  OK         {consumer} ({_span_str(c_first, c_last)}) -> "
                f"{producer} (intro {p_first}){note}"
            )
            ok += 1
        else:
            print(
                f"  VIOLATION  {consumer} (fully built by phase {c_last}) needs "
                f"{producer}, not stood up until phase {p_first}{note}"
            )
            violations += 1
            c_note = _scope_note_for(decls, consumer, c_last, spaces)
            p_note = _scope_note_for(decls, producer, p_first, spaces)
            if c_note:
                print(f"               ↳ consumer scope @{c_last}: {c_note}")
            if p_note:
                print(f"               ↳ producer scope @{p_first}: {p_note}")
            earlier = _earlier_scope_notes(decls, c_last)
            if earlier:
                for ph, eid, en in earlier:
                    print(
                        f"               ↳ earlier scope note "
                        f"(phase {ph}, {eid}): {en}"
                    )
            else:
                print(
                    "               ↳ no earlier scope notes "
                    "— no staging evidence, likely genuine"
                )
    print(
        f"  edges: {len(edges)} — ok {ok}, violations {violations}, "
        f"undeclared-endpoint {undeclared}"
    )


def report(draw_dir: str) -> None:
    draw = load_draw(draw_dir)
    decls = declarations(draw)
    ambiguous = {d["id"] for d in decls if d["space"] == AMBIGUOUS}
    print(f"dependency_ordering: {draw_dir}")
    print("  rule: producer's first phase <= consumer's last phase (role-aware)")

    # --- [1] product graph ---------------------------------------------------
    print("\n[1] PRODUCT GRAPH (feature_specs dependencies)")
    feats = product_features(draw)
    if not feats:
        print("  UNMEASURABLE — no feature_specs.json in draw")
    else:
        edges = [
            (str(f["id"]), str(dep))
            for f in feats
            if f.get("id")
            for dep in (f.get("dependencies") or [])
            if str(dep).strip()
        ]
        _check_edges(edges, decls, (PRODUCT, AMBIGUOUS), ambiguous)

    # --- [2] AI graph --------------------------------------------------------
    print("\n[2] AI GRAPH (ai_features requires; incl. infrastructure edges)")
    nodes = catalog_nodes(draw)
    if not nodes:
        print("  UNMEASURABLE — empty AI catalog (no-AI draw)")
        return
    name_to_id = capability_name_to_id(draw)
    edges = []
    for n in nodes:
        nid = str(n.get("id") or "")
        if not nid:
            continue
        for req_name in n.get("requires") or []:
            req = str(req_name)
            edges.append((nid, name_to_id.get(req) or slug(req)))
    _check_edges(edges, decls, (CAPABILITY, AMBIGUOUS), ambiguous)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    report(sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
