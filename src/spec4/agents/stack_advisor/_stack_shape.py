"""The shape of a stack spec: revision deltas, normalisation, extraction.

Everything between the LLM's reply and a ``stack_spec`` dict the rest of the
pipeline can walk:

* ``revision_delta`` / ``build_revision_note`` -- read the Brainstormer-stamped
  revision history off the vision and render the scoping note the revision seed
  carries. Deterministic; the model never authors either.
* ``_normalise_stack_shape`` / ``_keyed_from_list`` -- coerce the top-level
  blocks to the one shape their consumers (Phaser, the probes, the renderer)
  key over (D-SC18b, D-SC27).
* ``_extract_stack_json`` -- pull the fenced JSON block out of a reply and
  normalise it.

No Dash, no session, no LLM call. Split out of ``stack_advisor.py`` in Phase
4d; the package ``__init__`` re-exports every name below under its original
spelling.
"""

from __future__ import annotations

from typing import Any

from spec4.agents._turn_flow import extract_json_block


def revision_delta(vision: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return this round's revision delta, or ``None`` for a greenfield vision.

    A revision round's vision carries an accumulating ``revision_history`` (each
    round contributes one entry, stamped deterministically by Brainstormer); its
    final entry is the delta for the current round — ``goal``, the
    ``key_features_mvp`` name changes (``added`` / ``modified`` / ``removed``),
    and ``rationale``. A greenfield vision has no ``revision_history``. The input
    is the session-form vision envelope (``{"vision_statement": {...}}``); a
    non-enveloped or greenfield vision yields ``None`` (not revision mode).
    """
    vs = (vision or {}).get("vision_statement") if isinstance(vision, dict) else None
    history = vs.get("revision_history") if isinstance(vs, dict) else None
    if isinstance(history, list) and history:
        last = history[-1]
        return last if isinstance(last, dict) else None
    return None


def build_revision_note(delta: dict[str, Any]) -> str:
    """Render a revision delta into a stack-scoping note for the revision seed.

    Produces a single bracketed instruction (same shape as the staleness note)
    that scopes the stack recommendation to this revision's ``key_features_mvp``
    changes while preserving the established stack. Deterministic — the
    ``added`` / ``modified`` / ``removed`` names come straight from the
    Brainstormer-stamped delta; the model never authors them.
    """
    changes = delta.get("changes") or {}
    added = list(changes.get("added") or [])
    modified = list(changes.get("modified") or [])
    removed = list(changes.get("removed") or [])
    goal = (delta.get("goal") or "").strip()

    segments: list[str] = ["[This is a stack revision of the established stack."]
    if goal:
        segments.append(f" Goal: {goal}")
    clauses: list[str] = []
    if added:
        clauses.append("added features (" + ", ".join(added) + ")")
    if modified:
        clauses.append("changed features (" + ", ".join(modified) + ")")
    if removed:
        clauses.append("removed features (" + ", ".join(removed) + ")")
    if clauses:
        segments.append(
            " Recommend only the incremental stack changes this revision's "
            + "; ".join(clauses)
            + " require."
        )
    segments.append(
        " Preserve the established stack — languages, deployment, and every "
        "library these changes do not touch. Add or change only what these "
        "feature updates require.]"
    )
    return "".join(segments)


def _keyed_from_list(
    items: list[Any], *, name_fields: tuple[str, ...], prefix: str
) -> dict[str, Any]:
    """Key a list of entry dicts by their own name field, else by position."""
    out: dict[str, Any] = {}
    for i, item in enumerate(items):
        key = None
        if isinstance(item, dict):
            for field in name_fields:
                val = item.get(field)
                if isinstance(val, str) and val.strip():
                    key = val.strip()
                    break
        if key is None:
            key = f"{prefix}_{i + 1}"
        while key in out:
            key += "_"
        out[key] = item
    return out


def _normalise_stack_shape(spec: dict[str, Any]) -> dict[str, Any]:
    """Coerce the top-level blocks to the shape their consumers walk (D-SC18b).

    The renderer is total (D-SC33), so a deviant shape is no longer a crash or a
    silent drop. This pass exists for the *joins*: Phaser and the probes key over
    these blocks, and one shape per block is what lets them do that without a
    per-consumer guess.

    ``libraries`` is a flat list of entries carrying ``category`` and ``language``
    as values (D-SC27), so a category-keyed object folds down into it — the key
    becomes the entry's ``category``. That is the reverse of the pre-D-SC27
    coercion, which flattened a bare list into ``{"all": [...]}``; FareBox had in
    fact emitted the list shape the schema now asks for.
    """
    ss = spec.get("stack_spec") or spec.get("stack") or spec
    if not isinstance(ss, dict):
        return spec

    _fold_library_categories(ss)
    _listify_keyed_blocks(ss)
    _key_listed_blocks(ss)
    _key_ai_conventions(ss)
    return spec


def _fold_library_categories(ss: dict[str, Any]) -> None:
    """A category-keyed ``libraries`` object folds down into the flat list (D-SC27)."""
    libs = ss.get("libraries")
    if isinstance(libs, dict):
        flat: list[Any] = []
        for category, entries in libs.items():
            for entry in entries if isinstance(entries, list) else [entries]:
                if isinstance(entry, dict):
                    entry.setdefault("category", category)
                    flat.append(entry)
                else:
                    flat.append({"name": str(entry), "category": category})
        ss["libraries"] = flat


def _listify_keyed_blocks(ss: dict[str, Any]) -> None:
    """Object-shaped ``integrations`` / ``project_structure`` / ``additional_decisions`` become lists."""
    for block in ("integrations", "project_structure", "additional_decisions"):
        val = ss.get(block)
        if isinstance(val, dict):
            ss[block] = [
                {"name": k, **v} if isinstance(v, dict) else {"name": k, "value": v}
                for k, v in val.items()
            ]


def _key_listed_blocks(ss: dict[str, Any]) -> None:
    """List-shaped ``providers`` / ``infrastructure`` / ``persistence`` become keyed objects."""
    for block, prefix in (
        ("providers", "provider"),
        ("infrastructure", "component"),
        ("persistence", "store"),
    ):
        val = ss.get(block)
        if isinstance(val, list):
            ss[block] = _keyed_from_list(
                val,
                name_fields=("name", "store", "provider", "component", "choice"),
                prefix=prefix,
            )


def _key_ai_conventions(ss: dict[str, Any]) -> None:
    """A list-shaped ``ai_conventions`` becomes a keyed object."""
    conv = ss.get("ai_conventions")
    if isinstance(conv, list):
        ss["ai_conventions"] = _keyed_from_list(
            conv, name_fields=("name", "convention"), prefix="convention"
        )


def _extract_stack_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON stack spec from a fenced code block in the LLM response."""
    data = extract_json_block(text)
    if data is None:
        return None
    if "stack" not in data and "stack_spec" not in data:
        return None
    return _normalise_stack_shape(data)
