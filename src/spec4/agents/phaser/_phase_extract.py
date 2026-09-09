"""Turning a Phaser reply into a validated set of phase objects.

Everything between the streamed text and the phase list ``run`` persists: the
tolerant JSON walk (``_objects_with_key``) both extractors share, the
``stack_addition`` extract-and-strip pass, the phase extractor, the
truncation heuristic (D-PH2i), schema validation, the declared-count
completeness check, and the Markdown rendering of the result for the chat
transcript. Pure functions over text and dicts -- nothing here reads the
session, the LLM, or the filesystem.

Split out of ``phaser.py`` in Phase 4e; the package ``__init__`` re-exports
every name below under its original spelling.
"""

from __future__ import annotations

import json
import re
from typing import Any

from spec4 import project_manager
from spec4.agents._phase_schema import validate_phase


def _objects_with_key(value: Any, key: str) -> list[dict[str, Any]]:
    """Return every dict carrying ``key`` reachable from ``value``, in order.

    Walks nested dicts and lists. A dict that carries ``key`` is collected and
    treated as a leaf — recursion does not descend into it — so each match is
    reported once. This lets the phase / stack-addition extractors find their
    payload objects whether the model emits them bare, as a top-level array, or
    wrapped inside an outer object (e.g. ``{"phases": [...]}``); a top-level-only
    check silently drops the wrapped form.
    """
    out: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if key in value:
            out.append(value)
        else:
            for v in value.values():
                out.extend(_objects_with_key(v, key))
    elif isinstance(value, list):
        for item in value:
            out.extend(_objects_with_key(item, key))
    return out


def _extract_and_strip_stack_additions(text: str) -> tuple[list[dict[str, Any]], str]:
    """Extract human-confirmed ``stack_addition`` blocks and strip them out.

    Phaser emits ``{"stack_addition": {...}}`` blocks in an acknowledgment turn
    when the user confirms (directly or via a disclosed entailed choice) a
    dependency not in the stack. This scans the response with the same tolerant
    decoder ``_extract_phases`` uses, collects the inner addition dicts, and
    returns ``(additions, cleaned_text)`` where ``cleaned_text`` has the raw
    blocks removed so the machinery never reaches the user's view or history.

    Objects carrying a ``stack_addition`` key are collected whether bare or
    nested inside a wrapper object/array; phase objects (keyed on
    ``phase_number``) are left untouched, and a wrapper that also carries phase
    blocks is collected but not stripped — the phase extractor must still see
    those blocks downstream.
    """
    additions: list[dict[str, Any]] = []
    spans: list[tuple[int, int]] = []
    decoder = json.JSONDecoder(strict=False)
    i = 0
    while i < len(text):
        start = text.find("{", i)
        if start == -1:
            break
        try:
            obj, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            i = start + 1
            continue
        found = [
            d["stack_addition"]
            for d in _objects_with_key(obj, "stack_addition")
            if isinstance(d.get("stack_addition"), dict)
        ]
        if found:
            additions.extend(found)
            # Strip the whole decoded object only when it is stack-addition
            # payload — never when it also carries phase blocks (a combined
            # wrapper), or stripping would delete the phases before the phase
            # extractor sees them.
            if not _objects_with_key(obj, "phase_number"):
                spans.append((start, end))
        i = end

    if not spans:
        return additions, text

    cleaned_parts: list[str] = []
    cursor = 0
    for start, end in spans:
        cleaned_parts.append(text[cursor:start])
        cursor = end
    cleaned_parts.append(text[cursor:])
    cleaned = "".join(cleaned_parts)
    # Collapse blank runs left where a block used to be.
    cleaned = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", cleaned).strip()
    return additions, cleaned


def _extract_phases(text: str) -> list[dict[str, Any]]:
    """Extract all JSON phase objects from the LLM response.

    Scans the whole response for top-level JSON objects with a tolerant decoder
    rather than relying on ```json fences. This is robust to the malformations
    small models routinely emit in long phase output:

    - literal unescaped newlines/tabs inside string values (multi-line numbered
      lists in risk_assessment/verification) — handled by ``strict=False``;
    - an extra trailing brace or other junk after an object — ``raw_decode``
      stops at the end of the first complete value and ignores the rest;
    - phase ``instructions`` that themselves contain fenced ```code``` blocks,
      which would prematurely terminate a ```json-fence regex.

    Objects carrying a ``phase_number`` key are collected whether emitted bare,
    as a top-level array, or wrapped inside an outer object (e.g. a model that
    returns ``{"phases": [ {...}, {...} ]}`` instead of one block per phase) —
    the wrapper is descended into rather than skipped, so it does not parse to
    zero phases and dead-end the retry loop.
    """
    phases: list[dict[str, Any]] = []
    decoder = json.JSONDecoder(strict=False)
    i = 0
    while i < len(text):
        start = text.find("{", i)
        if start == -1:
            break
        try:
            obj, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            i = start + 1
            continue
        phases.extend(_objects_with_key(obj, "phase_number"))
        i = end
    return phases


def _appears_truncated(text: str) -> bool:
    """Heuristic: the response ends inside an unterminated JSON object.

    D-PH2i — the emission stream carries no explicit output-limit signal here
    (``finish_reason`` is not surfaced by ``stream_turn``), but a response cut
    off at the model's max-output cap almost always ends mid-object: the tail
    contains a ``{`` that never completes. Detecting that turns an opaque
    "fewer phases than declared" failure into an actionable one — no retry can
    fix a hard output cap, and the failure surface should say so.
    """
    decoder = json.JSONDecoder(strict=False)
    i = 0
    last_incomplete = False
    while i < len(text):
        start = text.find("{", i)
        if start == -1:
            break
        try:
            _, end = decoder.raw_decode(text, start)
            i = end
            last_incomplete = False
        except json.JSONDecodeError:
            i = start + 1
            last_incomplete = True
    return last_incomplete


def _extract_and_validate_phases(
    text: str,
) -> tuple[list[dict[str, Any]], list[tuple[int | None, list[str]]]]:
    """Extract phase JSON blocks and validate each against PHASE_SCHEMA.

    Returns ``(phases, failures)``:

    - ``phases`` — the full extracted list (whether or not individual phases
      validated cleanly). Callers may use this for diagnostics, but should
      only persist when ``failures`` is empty.
    - ``failures`` — one ``(phase_number, errors)`` entry per phase that
      failed validation. ``phase_number`` is ``None`` if the offending block
      lacks a parseable integer phase_number.

    An empty ``failures`` list means every extracted phase validated; an
    empty extracted list means either a normal conversational turn (no phase
    JSON) or output too malformed to parse — the latter is surfaced as a
    recoverable message by ``run()``.
    """
    phases = _extract_phases(text)
    failures: list[tuple[int | None, list[str]]] = []
    for phase in phases:
        errors = validate_phase(phase)
        if errors:
            raw_num = phase.get("phase_number")
            number = raw_num if isinstance(raw_num, int) else None
            failures.append((number, errors))
    return phases, failures


def _phase_completeness_failure(
    phases: list[dict[str, Any]],
) -> tuple[int | None, list[str]] | None:
    """Detect a fresh full generation that emitted fewer phases than it declared.

    Every phase block carries ``total_phases``, so a complete fresh generation
    must yield exactly the phase_numbers ``{1..total_phases}`` with no gaps or
    duplicates. A block whose outer JSON is malformed is silently skipped by
    ``_extract_phases``, so it appears in neither the extracted list nor the
    schema ``failures`` — and because the surviving blocks still parse, the
    parse-retry (gated on *zero* phases) never fires either. This reconciles the
    extracted set against the declared count and returns a synthetic failure
    entry, which the caller folds into ``failures`` so the existing
    validation-retry re-emits the full set.

    Returns ``None`` when the set is complete, when nothing was extracted (the
    parse-retry owns that case), or when no usable ``total_phases`` is present
    (schema validation governs instead). The caller gates this to fresh
    generations; brownfield updates emit a subset with ``total_phases`` set to
    the combined count and must not be checked here.
    """
    if not phases:
        return None
    totals = [
        p["total_phases"]
        for p in phases
        if isinstance(p.get("total_phases"), int) and p["total_phases"] > 0
    ]
    if not totals:
        return None
    expected = max(totals)
    numbers = [
        p["phase_number"] for p in phases if isinstance(p.get("phase_number"), int)
    ]
    missing = sorted(set(range(1, expected + 1)) - set(numbers))
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    distinct_totals = sorted(set(totals))
    if not missing and not duplicates and len(distinct_totals) == 1:
        return None
    problems: list[str] = []
    if missing:
        problems.append(f"phase_number(s) {missing} are missing")
    if duplicates:
        problems.append(f"phase_number(s) {duplicates} are duplicated")
    if len(distinct_totals) > 1:
        problems.append(f"blocks disagree on total_phases ({distinct_totals})")
    detail = "; ".join(problems)
    return (
        None,
        [
            f"The emitted phase set is incomplete: expected {expected} phases "
            f"numbered 1..{expected} (per total_phases), but {detail}. A phase "
            "block was likely malformed and silently dropped — re-emit every "
            "phase as a complete block."
        ],
    )


def _format_phases_for_display(phases: list[dict[str, Any]]) -> str:
    """Render every phase as Markdown for the in-chat display."""
    return "\n\n---\n\n".join(project_manager.render_phase_markdown(p) for p in phases)
