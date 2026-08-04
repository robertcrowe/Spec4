#!/usr/bin/env python3
"""D-SC34 — which stack_spec fields can reach the rendered receipt at all?

The receipt is the developer's only view of what was persisted, so a field the
renderer drops is indistinguishable from a field the model never emitted. This
tool reports the drop set for the prompt's own exemplar and, optionally, for any
draw's ``stack.json``.

It measures by **substitution**, not string search: it places a unique sentinel at
each leaf and re-renders. A plain ``value in rendered`` check reports a false
negative whenever the same value occurs elsewhere in the text — it scored
``satisfies_nfr`` as rendered because the identical nfr id appeared under
persistence, which is how the drop went unnoticed for two rounds.

The exemplar reading is **draw-independent**: no model, no variance, no live call.
It is a property of the code as it sits. ``tests/test_stack_render_totality.py``
holds that reading at zero; this tool is for inspecting a real draw, where a
non-zero count names fields the model invented that the schema has no slot for.

Usage:
    cd evals/stack_advisor && python3 render_coverage.py [<draw_dir_or_stack.json> ...]

A draw dir is any directory containing ``stack.json`` (e.g. ``.spec4/v0/``).
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from spec4.agents.stack_advisor import (  # noqa: E402
    SYSTEM_PROMPT,
    _format_stack_as_text,
)

_SENTINEL = "ZQXJ7SENTINEL"


def _leaf_paths(node: Any, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else key
            if isinstance(value, (dict, list)):
                out.extend(_leaf_paths(value, child))
            elif value is not None:
                out.append(child)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            child = f"{path}[{i}]"
            if isinstance(value, (dict, list)):
                out.extend(_leaf_paths(value, child))
            elif value is not None:
                out.append(child)
    return out


def _assign(node: Any, path: str, value: Any) -> None:
    tokens = re.findall(r"[^.\[\]]+|\[\d+\]", path)
    cursor = node
    for token in tokens[:-1]:
        cursor = cursor[int(token[1:-1])] if token.startswith("[") else cursor[token]
    last = tokens[-1]
    if last.startswith("["):
        cursor[int(last[1:-1])] = value
    else:
        cursor[last] = value


def _exemplar() -> dict[str, Any]:
    match = re.search(r"```json\n(\{.*?\n\})\n```", SYSTEM_PROMPT, re.S)
    if not match:
        raise SystemExit("no fenced JSON exemplar found in SYSTEM_PROMPT")
    return json.loads(match.group(1))


def probe(stack: dict[str, Any], label: str) -> list[str]:
    body = stack.get("stack_spec") or stack.get("stack") or stack
    drops: list[str] = []
    paths = _leaf_paths(body)
    for path in paths:
        mutated = copy.deepcopy(stack)
        target = mutated.get("stack_spec") or mutated.get("stack") or mutated
        _assign(target, path, _SENTINEL)
        if _SENTINEL not in _format_stack_as_text(mutated):
            drops.append(path)

    print(f"\n=== {label} ===")
    print(f"  leaf fields: {len(paths)}   cannot reach the page: {len(drops)}")
    if drops:
        grouped: dict[str, int] = {}
        for drop in drops:
            key = re.sub(r"\[\d+\]", "[]", drop)
            grouped[key] = grouped.get(key, 0) + 1
        print("  DROPPED:")
        for key, count in sorted(grouped.items()):
            print(f"    {key}" + (f"   (x{count})" if count > 1 else ""))
    return drops


def _load(arg: str) -> tuple[dict[str, Any], str]:
    path = Path(arg)
    if path.is_dir():
        path = path / "stack.json"
    if not path.exists():
        raise SystemExit(f"no stack.json at {path}")
    return json.loads(path.read_text()), str(path)


def main(argv: list[str]) -> int:
    exemplar_drops = probe(_exemplar(), "PROMPT EXEMPLAR (draw-independent)")
    if exemplar_drops:
        print(
            "\n  ^ these are DECLARED fields the renderer cannot show. Every draw "
            "loses them,\n    and the developer cannot tell them from fields the "
            "model never emitted."
        )
    for arg in argv:
        stack, label = _load(arg)
        drops = probe(stack, label)
        if drops:
            print(
                "\n  ^ in a draw, a drop is usually a field the model INVENTED "
                "because the\n    schema had no slot for the decision. Read it as a "
                "schema gap, not a model error."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
