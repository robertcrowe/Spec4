#!/usr/bin/env python3
"""Which key paths did the model invent because the schema had no slot?

**Read this first: it replaces `render_coverage.py` as the schema-gap detector.**

Before D-SC33 the renderer was a whitelist, so an invented key was silently
dropped and "fields that cannot reach the page" doubled as a gap detector. D-SC33
made the renderer total, so invented keys now render — `render_coverage` reads 0
by construction and answers a different question (does the renderer work?) rather
than this one (does the schema still have gaps?). The first draw after D-SC33
scored 0 dropped while still inventing six key paths. This tool is what saw them.

The reading: a key path in the draw that the prompt's own exemplar never
demonstrates. Interpret it as a **schema gap, not a model error** — the model
invents precisely when a real decision has nowhere to go, so each undeclared path
names a decision the schema should have had a slot for. Two draws invented the
same top-level prose slot under different names (`description`, `vision`), which
is the shape of the whole failure in miniature.

`DECLARED BUT UNUSED` is the mirror and is usually NOT a defect: a project with no
external services correctly omits `integrations`, and the escape hatch going
unused is the desired outcome. Read it for fields that should have been filled and
were not.

Blocks keyed by model-chosen names (`providers`, `persistence`, `infrastructure`,
`ai_conventions`) are normalised to `*` before comparison, since the key is data
there, not schema.

Usage:
    cd evals/stack_advisor && python3 undeclared_keys.py <draw_dir_or_stack.json> ...
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from spec4.agents.stack_advisor import SYSTEM_PROMPT  # noqa: E402

# Blocks whose first-level keys are chosen by the model, not by the schema.
_NAME_KEYED = ("providers", "persistence", "infrastructure", "ai_conventions")


def _exemplar() -> dict[str, Any]:
    match = re.search(r"```json\n(\{.*?\n\})\n```", SYSTEM_PROMPT, re.S)
    if not match:
        raise SystemExit("no fenced JSON exemplar found in SYSTEM_PROMPT")
    return json.loads(match.group(1))


def _key_paths(node: Any, path: str = "") -> set[str]:
    """Structural key paths; list indices collapse to ``[]``."""
    out: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else key
            out.add(child)
            out |= _key_paths(value, child)
    elif isinstance(node, list):
        for value in node:
            out |= _key_paths(value, path + "[]")
    return out


def _normalise(paths: set[str]) -> set[str]:
    out: set[str] = set()
    for path in paths:
        for root in _NAME_KEYED:
            if path.startswith(root + "."):
                bits = path.split(".")
                bits[1] = "*"
                path = ".".join(bits)
                break
        out.add(path)
    return out


def _spec(stack: dict[str, Any]) -> dict[str, Any]:
    return stack.get("stack_spec") or stack.get("stack") or stack


def _load(arg: str) -> tuple[dict[str, Any], str]:
    path = Path(arg)
    if path.is_dir():
        path = path / "stack.json"
    if not path.exists():
        raise SystemExit(f"no stack.json at {path}")
    return json.loads(path.read_text()), str(path)


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit(__doc__)
    declared = _normalise(_key_paths(_spec(_exemplar())))
    print(f"schema exemplar declares {len(declared)} key paths\n")
    for arg in argv:
        stack, label = _load(arg)
        drawn = _normalise(_key_paths(_spec(stack)))
        undeclared = sorted(drawn - declared)
        unused = sorted(declared - drawn)
        print(f"=== {label} ===")
        print(f"  key paths: {len(drawn)}   undeclared: {len(undeclared)}")
        if undeclared:
            print("\n  UNDECLARED — the model invented these; read each as a "
                  "schema gap:")
            for path in undeclared:
                print(f"    {path}")
        else:
            print("  no invented keys — the schema covered every decision made")
        if unused:
            print("\n  declared but unused (often correct — an absent block is a "
                  "decision):")
            for path in unused:
                print(f"    {path}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
