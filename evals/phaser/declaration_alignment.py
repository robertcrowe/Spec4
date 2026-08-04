"""Phase-file probe: declaration alignment (D-PS15) and spec restatement (D-PS14).

Dev tooling under ``evals/``. Never wired into the pipeline.

Reads a saved draw directory containing ``ai_features.json`` and the generated
phase files (``phases/phase*.md``, or ``phase*.md`` at the top level) and reports
two independent things:

**A. Restatement vs reference (no LLM).** Deterministic. The phase file attaches
each declared feature's spec verbatim, as a binding preamble above the
instructions, so an instruction that re-types the spec's field names creates a
second copy that can drift from the first. This section counts, per phase:

  * ``restated`` — how many of the attached specs' input names and output schema
    keys appear verbatim in that phase's instructions;
  * ``refs`` — how many times the instructions point at the specification instead
    ("the specification above", "as specified", …);
  * ``drift?`` — a *heuristic*. Instructions of the shape "… with fields: a, b, c"
    are parsed and their field names diffed against the spec's own terms. Names
    the instructions introduce for a spec'd model are candidate renames or
    additions. This is a lead, not a verdict: an instruction may legitimately
    define a model the spec never described.

  Falling ``restated`` and rising ``refs`` on a later draw is the D-PS14(a)
  signal. Zero ``refs`` across every phase — as observed before D-PS14(a) — means
  the directive was inert.

**B. Declaration alignment (LLM, opt-in).** Compares what each phase *declares*
in ``features[]`` against what the seam-check extractor reads out of its prose.
A phase that builds a feature it did not declare receives no spec for it; a phase
that declares one it never builds carries a spurious spec. Both advisory.

  This section costs one model call, so it is **off by default**. Pass ``--llm``
  to run it (the caller owns the key and the draw), or ``--graph FILE`` to supply
  a previously extracted graph and re-run the deterministic comparison for free.

Scoping caveats, so the numbers mean something:

  * Infrastructure nodes carry no spec, so they contribute no terms to section A
    and can only ever be *under*-declared in section B.
  * ``budgets`` and ``eval_approach`` are excluded from phase files (D-PS13);
    their terms are excluded here too, or every phase would look clean by virtue
    of never having been shown them.
  * The extractor reads prose. A phase that *calls* a feature's endpoint can look
    like it implements it. Section B is advisory in both directions.

Usage::

    uv run python evals/phaser/declaration_alignment.py <draw_dir>
    uv run python evals/phaser/declaration_alignment.py <draw_dir> --llm
    uv run python evals/phaser/declaration_alignment.py <draw_dir> --graph g.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from spec4 import project_manager
from spec4.agents._seam_check import (
    _check_declaration_alignment,
    _check_feature_coverage,
    _extract_graph,
)

INFRA_KIND = "infrastructure"

# Instructions that point at the spec rather than copying it.
_REFERENCE_RE = re.compile(
    r"specification[s]?\s+(above|section|below)"
    r"|the\s+specification[’']?s?\b"
    r"|as\s+specified\b"
    r"|per\s+the\s+spec\b"
    r"|listed\s+in\s+the\s+specification",
    re.I,
)

# "Create a Pydantic model Foo with fields: a (str), b (int), ..."
_WITH_FIELDS_RE = re.compile(r"with fields?:\s*(.+?)(?:\.\s|\.$|$)", re.I | re.S)
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _load_phases(draw: Path) -> list[dict[str, Any]]:
    files = sorted(draw.glob("phases/phase*.md")) or sorted(draw.glob("phase*.md"))
    phases: list[dict[str, Any]] = []
    for f in files:
        parsed = project_manager.parse_phase_markdown(f.read_text(encoding="utf-8"))
        if parsed is not None:
            phases.append(parsed)
    phases.sort(key=lambda p: p.get("phase_number", 0))
    # A draw dir may hold stale files from an earlier, differently-sized run.
    if phases:
        total = max(p.get("total_phases", 0) for p in phases)
        phases = [p for p in phases if p.get("total_phases") == total]
    return phases


def _spec_terms(feature: dict[str, Any]) -> set[str]:
    """Input names + output schema keys the coder could copy out of the spec."""
    if feature.get("kind") == INFRA_KIND:
        return set()
    terms: set[str] = set()
    for item in feature.get("inputs") or []:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            terms.add(item["name"].strip())
    outputs = feature.get("outputs")
    if isinstance(outputs, dict):
        notes = str(outputs.get("schema_notes") or "")
        for m in re.finditer(r"\{([^}]*)\}", notes):
            for token in re.split(r"[,\s]+", m.group(1)):
                token = token.strip().strip(":")
                if _IDENT_RE.match(token):
                    terms.add(token)
    return {t for t in terms if len(t) > 2}


def _instruction_field_names(instructions: list[str]) -> set[str]:
    """Field names an instruction introduces via a "with fields: …" list.

    Parenthesised type annotations are stripped first: "limit (int, optional,
    default 20)" would otherwise contribute `optional` and `default` as if they
    were field names.
    """
    names: set[str] = set()
    for step in instructions:
        for m in _WITH_FIELDS_RE.finditer(step):
            body = re.sub(r"\([^)]*\)", "", m.group(1))
            for chunk in body.split(","):
                token = chunk.strip()
                if _IDENT_RE.match(token):
                    names.add(token)
    return names


def _restatement_report(
    phases: list[dict[str, Any]], catalog: dict[str, Any]
) -> None:
    by_id = {
        n["id"]: n
        for n in catalog.get("ai_features") or []
        if isinstance(n, dict) and n.get("id")
    }
    print("\n=== A. Restatement vs reference (deterministic) ===\n")
    print(f"{'phase':>5}  {'declared':<34} {'restated':>10} {'refs':>5}  drift?")
    print("-" * 88)
    tot_restated = tot_terms = tot_refs = 0
    for p in phases:
        number = p.get("phase_number")
        decls = [d for d in (p.get("features") or []) if isinstance(d, dict)]
        instructions = [str(s) for s in (p.get("instructions") or [])]
        blob = "\n".join(instructions)
        refs = len(_REFERENCE_RE.findall(blob))
        tot_refs += refs

        terms: set[str] = set()
        for d in decls:
            node = by_id.get(str(d.get("id")))
            if node:
                terms |= _spec_terms(node)
        hit = {
            t for t in terms if re.search(rf"\b{re.escape(t)}\b", blob, re.I)
        }
        tot_restated += len(hit)
        tot_terms += len(terms)

        introduced = _instruction_field_names(instructions)
        drift = sorted(introduced - terms) if terms else []

        label = ", ".join(d.get("id", "?") for d in decls) or "—"
        ratio = f"{len(hit)}/{len(terms)}" if terms else "—"
        flag = ",".join(drift[:4]) + ("…" if len(drift) > 4 else "") if drift else ""
        print(f"{number:>5}  {label[:34]:<34} {ratio:>10} {refs:>5}  {flag}")

    print("-" * 88)
    pct = f"{100 * tot_restated // tot_terms}%" if tot_terms else "n/a"
    print(f"{'TOTAL':>5}  {'':<34} {tot_restated}/{tot_terms} ({pct}) {tot_refs:>5}")
    if tot_refs == 0 and tot_terms:
        print("\n  ! Zero references across every phase — the reference directive is inert.")


def _alignment_report(
    phases: list[dict[str, Any]],
    catalog: dict[str, Any],
    graph: dict[str, Any] | None,
) -> None:
    print("\n=== B. Declaration alignment ===\n")
    if graph is None:
        print("  (skipped — pass --llm to extract, or --graph FILE to reuse)")
        return
    print("  extracted covers_features:")
    for p in graph["phases"]:
        print(f"    phase {p.get('phase_number')}: {p.get('covers_features') or []}")
    findings = _check_feature_coverage(graph, catalog) + _check_declaration_alignment(
        graph, phases, catalog
    )
    if not findings:
        print("\n  no findings.")
        return
    print()
    for f in findings:
        print(f"  [{f.severity:<6}] [{f.check}] {f.message}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("draw_dir", type=Path)
    ap.add_argument("--llm", action="store_true", help="run the extractor (1 call)")
    ap.add_argument("--graph", type=Path, help="reuse a previously extracted graph")
    ap.add_argument("--model", default="anthropic/claude-sonnet-4-5")
    ap.add_argument("--save-graph", type=Path, help="write the extracted graph here")
    args = ap.parse_args()

    draw: Path = args.draw_dir
    catalog_path = draw / "ai_features.json"
    if not catalog_path.exists():
        print(f"missing {catalog_path}", file=sys.stderr)
        return 2
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    phases = _load_phases(draw)
    if not phases:
        print(f"no parseable phase files under {draw}", file=sys.stderr)
        return 2

    nodes = catalog.get("ai_features") or []
    print(f"draw: {draw}")
    print(f"phases: {len(phases)}   catalog nodes: {len(nodes)} "
          f"({sum(1 for n in nodes if n.get('kind') == INFRA_KIND)} infrastructure)")

    _restatement_report(phases, catalog)

    graph: dict[str, Any] | None = None
    if args.graph:
        graph = json.loads(args.graph.read_text(encoding="utf-8"))
    elif args.llm:
        graph = _extract_graph(phases, catalog, {"model": args.model})
        if graph is None:
            print("\n  extraction failed or unparseable.", file=sys.stderr)
        elif args.save_graph:
            args.save_graph.write_text(json.dumps(graph, indent=2), encoding="utf-8")
            print(f"\n  graph saved to {args.save_graph}")

    _alignment_report(phases, catalog, graph)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())