"""Which ``code_review`` fields actually reach the stack and the phases?

**Target 2 probe (read before any seed-view lever).** Brownfield's entire
input to Brainstormer, StackAdvisor and Phaser is a ``json.dumps(code_review)``
paste followed by a field-instruction paragraph that differs per seed. The
same shape on the Deployer stack paste was measured and found to mostly never
reach a plan, and was replaced by the deterministic ``_stack_context`` view.
Before the code review gets the same treatment, this probe establishes the
baseline the view will be measured against: for every field of the review,
how often does its content visibly surface in ``stack.json`` and in the
generated phases (Phase 1 specifically — the integration thread the Phaser
seed asks for — and any phase)?

**Reading.** A field with a high hit rate is one the consumers already use;
a field with a low or zero rate is either not needed by that consumer or is
being lost in the paste. The probe cannot tell those apart on its own — it
decides *which fields to put in which consumer's tuple*, and the view's
post-lever draw decides whether the loss was the paste's fault.

**Measurement is lexical and blunt, by design.** Every leaf string value of
the review is grouped under its field path (``commands.test``,
``persistence.databases``, ``notes.change_risks``, ...). A short value (≤ 60
characters) hits when it appears in the target text under the same
word-boundary, punctuation-tolerant match the Phaser probes use
(``evals/phaser/_load.name_matches``: "React Hook Form" matches
"react-hook-form"). A long value (prose: a summary, a risk description) hits
when at least ``PROSE_FRACTION`` of its distinctive tokens (≥ 5 letters, not a
stopword) appear in the target. ``source`` / ``inferred_from`` provenance
leaves and booleans are not content and are not counted. A hit is evidence of
reach, not of correct use; a miss on a prose field is weaker evidence than a
miss on a name.

Reads one or more draw directories, each holding ``code_review.json``
(required; the ``{"code_review": {...}}`` envelope or the bare object) plus
any of ``stack.json`` and ``phases/phase*.md`` (or ``phase*.md`` at the top
level — the ``evals/phaser/_load`` convention). Run from the repo root::

    uv run python evals/code_scanner/review_reach.py <draw_dir> [<draw_dir> ...]
    uv run python evals/code_scanner/review_reach.py --self-check

``--self-check`` runs the probe against the golden ``review_full.json``
fixture with synthetic targets, so the matcher's behaviour is pinned without
a live draw. ``--json`` emits the per-draw, per-field table as JSON on stdout
for a later cross-draw comparison.

Dev tooling under ``evals/``. Never wired into the pipeline.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO / "evals" / "phaser"))

from _load import load_draw, name_matches  # noqa: E402

SHORT_LIMIT = 60
PROSE_FRACTION = 0.6
MIN_TOKEN = 5

#: Leaves that are provenance, not content.
_PROVENANCE = {"source", "inferred_from", "schema_version"}

_STOPWORDS = {
    "about",
    "after",
    "against",
    "because",
    "before",
    "being",
    "between",
    "could",
    "during",
    "every",
    "exists",
    "existing",
    "found",
    "from",
    "their",
    "there",
    "these",
    "those",
    "through",
    "under",
    "using",
    "where",
    "which",
    "while",
    "with",
    "within",
    "without",
    "would",
}

#: Field paths are reported at this depth: the top-level key, plus one more
#: level for the containers whose children are distinct decisions.
_SPLIT_SECOND_LEVEL = {
    "commands",
    "entrypoints",
    "persistence",
    "deployment",
    "ui_summary",
    "notes",
    "build_system",
    "auth",
    "architecture",
    "coding_style",
}


# ---------------------------------------------------------------------------
# Walking the review
# ---------------------------------------------------------------------------


def _unwrap(review: dict[str, Any]) -> dict[str, Any]:
    inner = review.get("code_review")
    return inner if isinstance(inner, dict) else review


def _field_of(path: list[str]) -> str:
    """The reporting bucket for a leaf at ``path`` (keys only, no indices)."""
    keys = [p for p in path if not p.startswith("[")]
    if not keys:
        return "(root)"
    if keys[0] in _SPLIT_SECOND_LEVEL and len(keys) > 1:
        return f"{keys[0]}.{keys[1]}"
    return keys[0]


def review_values(review: dict[str, Any]) -> Iterator[tuple[str, str]]:
    """Every content leaf of the review as ``(field, value)``."""

    def walk(node: Any, path: list[str]) -> Iterator[tuple[str, str]]:
        if isinstance(node, dict):
            for k, v in node.items():
                if str(k) in _PROVENANCE:
                    continue
                yield from walk(v, [*path, str(k)])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from walk(v, [*path, f"[{i}]"])
        elif isinstance(node, str):
            text = node.strip()
            if text and re.search(r"[a-z0-9]{2,}", text.lower()):
                yield _field_of(path), text
        # bool / int / float / None: not content.

    yield from walk(_unwrap(review), [])


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9_]+", text.lower())
        if len(t) >= MIN_TOKEN and t not in _STOPWORDS
    }


def value_hits(value: str, target: str, target_tokens: set[str]) -> bool:
    """Does ``value`` visibly surface in ``target``? (See module docstring.)"""
    if len(value) <= SHORT_LIMIT:
        return name_matches(value, target)
    toks = _tokens(value)
    if not toks:
        return name_matches(value, target)
    return len(toks & target_tokens) / len(toks) >= PROSE_FRACTION


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


def _phase_text(phase: dict[str, Any]) -> str:
    """Frontmatter and body together — everything the coder will read."""
    front = {k: v for k, v in phase.items() if k != "_body"}
    return json.dumps(front) + "\n" + str(phase.get("_body") or "")


def targets(draw_dir: Path) -> dict[str, str]:
    """``{target_name: text}`` for every consumer artifact present."""
    draw = load_draw(draw_dir)
    out: dict[str, str] = {}
    stack_path = draw_dir / "stack.json"
    if stack_path.exists():
        out["stack"] = stack_path.read_text(encoding="utf-8")
    phases = draw.get("phases") or []
    if phases:
        out["phase_1"] = _phase_text(phases[0])
        out["any_phase"] = "\n".join(_phase_text(p) for p in phases)
    return out


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


def measure(
    review: dict[str, Any], target_texts: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """Per field: values present, and per target the values that hit.

    Returns ``{field: {"n": int, "values": [...], "hits": {target: int},
    "hit_values": {target: [...]}}}``; fields are in review order.
    """
    toks = {name: _tokens(text) for name, text in target_texts.items()}
    fields: dict[str, dict[str, Any]] = {}
    for field, value in review_values(review):
        rec = fields.setdefault(
            field,
            {
                "n": 0,
                "values": [],
                "hits": defaultdict(int),
                "hit_values": defaultdict(list),
            },
        )
        rec["n"] += 1
        rec["values"].append(value)
        for name, text in target_texts.items():
            if value_hits(value, text, toks[name]):
                rec["hits"][name] += 1
                rec["hit_values"][name].append(value)
    for rec in fields.values():
        rec["hits"] = dict(rec["hits"])
        rec["hit_values"] = dict(rec["hit_values"])
    return fields


def aggregate(
    per_draw: dict[str, dict[str, dict[str, Any]]], target_names: list[str]
) -> dict[str, dict[str, Any]]:
    """Sum ``n`` and hits per field across draws; note how many draws had the field."""
    agg: dict[str, dict[str, Any]] = {}
    for fields in per_draw.values():
        for field, rec in fields.items():
            a = agg.setdefault(
                field, {"n": 0, "draws": 0, "hits": {t: 0 for t in target_names}}
            )
            a["n"] += rec["n"]
            a["draws"] += 1
            for t in target_names:
                a["hits"][t] += rec["hits"].get(t, 0)
    return agg


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _rate(hit: int, n: int) -> str:
    return f"{hit:>3}/{n:<3} {100 * hit / n:5.1f}%" if n else "   -/-      -  "


def report(
    label: str, fields: dict[str, dict[str, Any]], target_names: list[str]
) -> None:
    width = max((len(f) for f in fields), default=10)
    head = f"  {'field':<{width}}  {'n':>3}  " + "  ".join(
        f"{t:<14}" for t in target_names
    )
    print(f"\n[{label}]")
    print(head)
    for field, rec in fields.items():
        cells = "  ".join(_rate(rec["hits"].get(t, 0), rec["n"]) for t in target_names)
        print(f"  {field:<{width}}  {rec['n']:>3}  {cells}")


def report_aggregate(
    agg: dict[str, dict[str, Any]], target_names: list[str], draws: int
) -> None:
    width = max((len(f) for f in agg), default=10)
    print(f"\n[ALL — {draws} draw(s)]  per-field hit rate, pooled over values")
    print(
        f"  {'field':<{width}}  {'draws':>5}  {'n':>3}  "
        + "  ".join(f"{t:<14}" for t in target_names)
    )
    for field, rec in sorted(agg.items(), key=lambda kv: kv[0]):
        cells = "  ".join(_rate(rec["hits"][t], rec["n"]) for t in target_names)
        print(f"  {field:<{width}}  {rec['draws']:>5}  {rec['n']:>3}  {cells}")


def _print_misses(fields: dict[str, dict[str, Any]], target: str) -> None:
    print(f"\n  values that never reached {target}:")
    for field, rec in fields.items():
        hit = set(rec["hit_values"].get(target, []))
        missed = [v for v in rec["values"] if v not in hit]
        if missed:
            print(f"    {field}:")
            for v in missed[:6]:
                print(f"      - {v[:100]}{'…' if len(v) > 100 else ''}")
            if len(missed) > 6:
                print(f"      … and {len(missed) - 6} more")


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------


def self_check() -> int:
    fixture = _REPO / "tests" / "golden" / "fixtures" / "review_full.json"
    review = json.loads(fixture.read_text(encoding="utf-8"))
    cr = _unwrap(review)
    # A synthetic stack that cites the test command, one dependency and the
    # ORM, and nothing else; a synthetic phase that cites the entrypoint path.
    dep = (cr.get("dependencies") or [{}])[0].get("name", "")
    orm = ((cr.get("persistence") or {}).get("orm") or {}).get("name", "")
    stack = json.dumps(
        {"libraries": [{"name": dep}, {"name": orm}], "test": cr["commands"]["test"]}
    )
    entry = next((v for v in (cr.get("entrypoints") or {}).values() if v), "")
    phase = json.dumps(
        {"instructions": [f"Start from {entry} and run {cr['commands']['test']}"]}
    )
    fields = measure(review, {"stack": stack, "phase_1": phase})
    ok = True

    def expect(field: str, target: str, hits: int) -> None:
        nonlocal ok
        got = fields.get(field, {}).get("hits", {}).get(target, 0)
        flag = "ok " if got == hits else "BAD"
        if got != hits:
            ok = False
        print(f"  {flag} {field:<24} {target:<8} expected {hits} got {got}")

    print("[self-check against tests/golden/fixtures/review_full.json]")
    expect("commands.test", "stack", 1)
    expect("commands.test", "phase_1", 1)
    expect("commands.build", "stack", 0)
    expect("persistence.orm", "stack", 1)
    expect("persistence.orm", "phase_1", 0)
    expect(
        "entrypoints.main",
        "phase_1",
        1 if cr["entrypoints"].get("main") == entry else 0,
    )
    expect("notes.change_risks", "stack", 0)
    print(
        "  provenance leaves excluded:",
        "source" not in {f for f, _ in review_values(review)},
    )
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("draws", nargs="*", help="draw directories")
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--json", action="store_true", help="emit per-draw table as JSON")
    ap.add_argument(
        "--misses", action="store_true", help="list values that missed each target"
    )
    args = ap.parse_args(argv)
    if args.self_check:
        return self_check()
    if not args.draws:
        ap.error("no draw directories given")

    per_draw: dict[str, dict[str, dict[str, Any]]] = {}
    seen_targets: list[str] = []
    for arg in args.draws:
        d = Path(arg)
        rp = d / "code_review.json"
        if not rp.exists():
            print(f"[{d.name}] no code_review.json — skipped", file=sys.stderr)
            continue
        review = json.loads(rp.read_text(encoding="utf-8"))
        tg = targets(d)
        if not tg:
            print(f"[{d.name}] no stack.json or phases — skipped", file=sys.stderr)
            continue
        for t in tg:
            if t not in seen_targets:
                seen_targets.append(t)
        per_draw[d.name] = measure(review, tg)
        if not args.json:
            report(d.name, per_draw[d.name], list(tg))
            if args.misses:
                for t in tg:
                    _print_misses(per_draw[d.name], t)

    if not per_draw:
        return 1
    order = [t for t in ("stack", "phase_1", "any_phase") if t in seen_targets]
    agg = aggregate(per_draw, order)
    if args.json:
        print(
            json.dumps(
                {
                    "per_draw": {
                        d: {f: {"n": r["n"], "hits": r["hits"]} for f, r in fs.items()}
                        for d, fs in per_draw.items()
                    },
                    "aggregate": agg,
                },
                indent=2,
            )
        )
    else:
        report_aggregate(agg, order, len(per_draw))
        print(
            "\n  Lexical match only (name_matches for short values; "
            f"≥{int(PROSE_FRACTION * 100)}% distinctive-token overlap for prose). "
            "A hit is reach, not correct use."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
