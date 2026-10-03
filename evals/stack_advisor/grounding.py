"""Which stack entries cite nothing the vision asked for?

**Target 3 probe (probe-before-lever).** StackAdvisor's prompt has many
"never invent a *field*" rules but no grounding rule: nothing says an
``integrations[]`` or ``auth[]`` entry, or a store, must serve a feature the
vision names. On a live sweep-mode draw it invented an IMAP/SMTP integration
the vision never asked for; with FF the default flow, a phantom integration
becomes phantom phases. The candidate lever is a deterministic post-extraction
check: every integration, auth mechanism, store and collection must carry at
least one non-empty join to a known feature, capability, NFR or infra id, with
a one-shot re-ask and a persisted ``ungrounded_dropped`` record on failure.

This probe is the measurement that lever is judged against. For each draw it
lists the entries in the at-risk blocks that carry **no join at all**
(``serves_features``, ``serves_capabilities``, ``satisfies_nfr``,
``satisfies_infra`` all absent or empty), and — when the draw directory also
holds ``feature_specs.json`` / ``ai_features.json`` — the entries whose joins
**resolve to no known id** (a typo or an invented feature name, which grounds
nothing). An entry marked ``foundational: true`` is reported separately: the
schema lets a substrate entry omit joins by design, so it is not ungrounded,
but a foundational *integration* is worth a human look.

**Reading.** ``no_join`` is the band the lever would act on. ``unresolved`` is
the band the lever would need the id universe to act on, and is
``UNMEASURABLE`` when the draw has no spine artifacts. Neither is proof of
invention — a grounded entry can still be a bad choice, and an unjoined store
can be a legitimate operational one — but every invented entry on record
(IMAP/SMTP) would have appeared in ``no_join``. Run it over the archived
draws for the baseline and over each new draw before ratifying the stack.

Reads draw directories holding ``stack.json`` (required; wrapped or bare) and
optionally ``feature_specs.json`` and ``ai_features.json`` (the
``evals/phaser/_load`` convention). Run from the repo root::

    uv run python evals/stack_advisor/grounding.py <draw_dir> [<draw_dir> ...]
    uv run python evals/stack_advisor/grounding.py <draw_dir> ... --json

Dev tooling under ``evals/``. Never wired into the pipeline.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO / "evals" / "phaser"))

from _load import capability_ids, load_draw, product_ids  # noqa: E402

JOIN_FIELDS = (
    "serves_features",
    "serves_capabilities",
    "satisfies_nfr",
    "satisfies_infra",
)

#: The blocks the Target 3 lever would check (D-SI1 lean), by dotted path.
#: ``persistence`` is name-keyed by the normaliser; its stores and their
#: ``collections`` are both checked. Provider ``capabilities`` and
#: ``libraries`` are deliberately out: libraries carry ``foundational`` as
#: their grounding story (D-SC4) and a probe already covers them.
LIST_BLOCKS = ("integrations", "security.auth")
STORE_BLOCK = "persistence"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", name.lower()) if name else ""


# ---------------------------------------------------------------------------
# Id universe
# ---------------------------------------------------------------------------


def _nfr_ids(feature_specs: dict[str, Any] | None) -> set[str]:
    return {
        f"nfr_{slug(g.strip())}"
        for g in ((feature_specs or {}).get("nfr_goals") or [])
        if isinstance(g, str) and g.strip()
    }


def _infra_ids(ai_features: dict[str, Any] | None) -> set[str]:
    nodes = (ai_features or {}).get("ai_features") or []
    return {
        str(n.get("id"))
        for n in nodes
        if isinstance(n, dict) and n.get("kind") == "infrastructure" and n.get("id")
    }


def id_universe(draw: dict[str, Any]) -> dict[str, set[str]] | None:
    """Known ids per join field, or None when no spine artifact is present."""
    if draw.get("feature_specs") is None and draw.get("ai_features") is None:
        return None
    products = product_ids(draw)
    caps = capability_ids(draw)
    return {
        "serves_features": products | caps,
        "serves_capabilities": caps,
        "satisfies_nfr": _nfr_ids(draw.get("feature_specs")),
        "satisfies_infra": _infra_ids(draw.get("ai_features")),
    }


# ---------------------------------------------------------------------------
# Walking the stack
# ---------------------------------------------------------------------------


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return []


def _resolve(ss: dict[str, Any], dotted: str) -> Any:
    node: Any = ss
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _name(entry: dict[str, Any], fallback: str) -> str:
    for k in ("name", "mechanism", "choice", "store", "provider"):
        v = entry.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return fallback


def checked_entries(stack: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """``(block, name, entry)`` for every entry the lever would check."""
    ss = stack.get("stack_spec") or stack.get("stack") or stack
    out: list[tuple[str, str, dict[str, Any]]] = []
    if not isinstance(ss, dict):
        return out
    for block in LIST_BLOCKS:
        items = _resolve(ss, block)
        if isinstance(items, list):
            for i, e in enumerate(items):
                if isinstance(e, dict):
                    out.append((block, _name(e, f"{block}[{i}]"), e))
    stores = ss.get(STORE_BLOCK)
    if isinstance(stores, dict):
        for key, store in stores.items():
            if not isinstance(store, dict):
                continue
            out.append((STORE_BLOCK, _name(store, str(key)), store))
            colls = store.get("collections")
            if isinstance(colls, list):
                for i, c in enumerate(colls):
                    if isinstance(c, dict):
                        out.append(
                            (f"{STORE_BLOCK}.{key}.collections", _name(c, f"[{i}]"), c)
                        )
    return out


def classify(
    entry: dict[str, Any], universe: dict[str, set[str]] | None
) -> tuple[str, list[str]]:
    """``(band, detail)``: grounded / no_join / unresolved / foundational."""
    joins = {f: _as_list(entry.get(f)) for f in JOIN_FIELDS}
    if not any(joins.values()):
        if entry.get("foundational") is True:
            return "foundational", []
        return "no_join", []
    if universe is None:
        return "grounded", ["(ids not checked — no spine artifacts)"]
    bad: list[str] = []
    good = False
    for field, ids in joins.items():
        for i in ids:
            if i in universe[field] or slug(i) in universe[field]:
                good = True
            else:
                bad.append(f"{field}={i}")
    if good:
        return "grounded", bad  # at least one real join; stray ids noted
    return "unresolved", bad


# ---------------------------------------------------------------------------
# Measurement and report
# ---------------------------------------------------------------------------


def measure(draw_dir: Path) -> dict[str, Any] | None:
    draw = load_draw(draw_dir)
    stack_path = draw_dir / "stack.json"
    if not stack_path.exists():
        return None
    stack = json.loads(stack_path.read_text(encoding="utf-8"))
    universe = id_universe(draw)
    rows = []
    for block, name, entry in checked_entries(stack):
        band, detail = classify(entry, universe)
        rows.append({"block": block, "name": name, "band": band, "detail": detail})
    return {
        "draw": draw_dir.name,
        "ids_measurable": universe is not None,
        "checked": len(rows),
        "bands": {
            b: sum(r["band"] == b for r in rows)
            for b in ("grounded", "no_join", "unresolved", "foundational")
        },
        "rows": rows,
    }


def report(m: dict[str, Any]) -> None:
    b = m["bands"]
    ids = (
        "ids checked"
        if m["ids_measurable"]
        else "ids UNMEASURABLE (no spine artifacts)"
    )
    print(
        f"\n[{m['draw']}]  checked={m['checked']}  grounded={b['grounded']}  "
        f"no_join={b['no_join']}  unresolved={b['unresolved']}  "
        f"foundational={b['foundational']}  ({ids})"
    )
    for band in ("no_join", "unresolved", "foundational"):
        rows = [r for r in m["rows"] if r["band"] == band]
        if rows:
            print(f"  {band}:")
            for r in rows:
                extra = f"  [{'; '.join(r['detail'])}]" if r["detail"] else ""
                print(f"    - {r['block']}: {r['name']}{extra}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("draws", nargs="+")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    results = []
    for arg in args.draws:
        m = measure(Path(arg))
        if m is None:
            print(f"[{Path(arg).name}] no stack.json — skipped", file=sys.stderr)
            continue
        results.append(m)
        if not args.json:
            report(m)
    if not results:
        return 1
    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    tot = {k: sum(m["bands"][k] for m in results) for k in results[0]["bands"]}
    checked = sum(m["checked"] for m in results)
    print(
        f"\n[ALL — {len(results)} draw(s)]  checked={checked}  "
        + "  ".join(f"{k}={v}" for k, v in tot.items())
    )
    print(
        "\n  no_join is the band the Target 3 lever would act on. A join is a "
        "non-empty serves_features / serves_capabilities / satisfies_nfr / "
        "satisfies_infra; resolution needs feature_specs.json / ai_features.json "
        "beside stack.json."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
