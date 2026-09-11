"""Agentifier Fast Forward review -- the presentable half of both sweeps.

Cleanup Phase 4i moved the leaf edges of the D-AF review flows here: the two
review prompts, the deterministic ``name: instruction`` router shared by both,
the two review presenters, and the cross-cutting sweep.

The three generators record their outcome on the ``session`` they are handed
and yield the display text, so they are not side-effect-free; they are leaves.
Their whole dependency set is closed -- ``_format_cross_cutting_topic`` and
``format_spec_as_text`` from :mod:`spec4.agentifier._render`, and each other --
so nothing here imports ``spec4.agentifier.agentifier``.

The three handlers that complete these flows -- ``_handle_cc_ff_review``,
``_handle_spec_ff_review`` and ``_ff_sweep_specs`` -- stayed in ``agentifier``:
each calls back into a phase driver there (``_begin_priority_phase``,
``_finalize_specs``, ``_draft_spec``), which would be a cycle.
"""

from __future__ import annotations

import re
from collections.abc import Generator
from typing import Any

from spec4.agentifier._render import _format_cross_cutting_topic, format_spec_as_text

__all__ = [
    "_FF_REVISION_RE",
    "_cc_ff_review_prompt",
    "_ff_sweep_cross_cutting",
    "_present_cc_ff_review",
    "_present_spec_ff_review",
    "_route_ff_revision_lines",
    "_spec_ff_review_prompt",
]

# ---------------------------------------------------------------------------
# Cross-cutting review
# ---------------------------------------------------------------------------


def _cc_ff_review_prompt(locked_topics: list[str]) -> str:
    prompt = (
        "\n\n---\n**Comprehensive review.** Reply **yes** to accept all "
        "cross-cutting decisions as shown, or give revisions one per line "
        "as `topic: instruction` (`topic: skip` to drop a skippable topic)."
    )
    if locked_topics:
        prompt += (
            "\nLocked (decided earlier, not revisable here): "
            + ", ".join(f"`{t}`" for t in locked_topics)
            + "."
        )
    return prompt


def _present_cc_ff_review(
    session: dict[str, Any],
    only_topics: list[str] | None = None,
) -> Generator[str, None, None]:
    """Render the comprehensive cross-cutting review (or revised topics)."""
    msgs = session["agentifier_messages"]
    topics: list[str] = session.get("agentifier_cross_cutting_topics") or []
    analysis = session.get("agentifier_cross_cutting_analysis") or {}
    decisions = session.get("agentifier_cross_cutting_decisions") or {}
    locked = session.get("agentifier_cc_ff_locked") or 0
    locked_topics = topics[:locked]

    shown = only_topics if only_topics is not None else topics
    parts: list[str] = []
    if only_topics is None:
        parts.append("## Comprehensive cross-cutting review\n")
    for t in shown:
        i = topics.index(t)
        # Show the recorded decision, falling back to the analysis view.
        view = {t: decisions.get(t) or analysis.get(t) or {}}
        body = _format_cross_cutting_topic(
            t, i, view, len(topics), include_prompt=False
        )
        if i < locked:
            parts.append(f"*(locked — decided earlier)*\n{body}")
        elif not (decisions.get(t) or {}):
            parts.append(f"{body}\n*(skipped)*")
        else:
            parts.append(body)
    display = "\n\n".join(parts) + _cc_ff_review_prompt(locked_topics)
    msgs.append({"role": "assistant", "content": display})
    session["_display_override"] = display
    yield display


def _ff_sweep_cross_cutting(
    session: dict[str, Any],
    analysis: dict[str, Any],
) -> Generator[str, None, None]:
    """D-AF3/D-AF4: adopt the analysis for all remaining topics, one review.

    The analyst has already computed every topic upfront, so the sweep makes
    no model calls: it records the recommendations (including skippable
    topics — accepting is the recommendation, skipping is a user
    prerogative) and presents the batch. Topics decided before the sweep
    are locked and kept verbatim.
    """
    topics: list[str] = session.get("agentifier_cross_cutting_topics") or []
    index: int = session.get("agentifier_cross_cutting_index") or 0
    decisions: dict[str, Any] = dict(
        session.get("agentifier_cross_cutting_decisions") or {}
    )
    for t in topics[index:]:
        decisions[t] = analysis.get(t) or {}
    session["agentifier_cross_cutting_decisions"] = decisions
    session["agentifier_cc_ff_locked"] = index
    session["agentifier_cross_cutting_ff_review"] = True
    yield from _present_cc_ff_review(session)


# ---------------------------------------------------------------------------
# Spec review
# ---------------------------------------------------------------------------

#: `name: instruction` — same shape as the priority-edit reader: an optional
#: bullet, an optional bold/backtick-wrapped name, a colon, free instruction.
_FF_REVISION_RE = re.compile(
    r"^\s*(?:[-*•]\s*)?(?:\*\*|`)?([A-Za-z0-9_][A-Za-z0-9_.\-]*)(?:\*\*|`)?"
    r"\s*:\s*(.+?)\s*$"
)


def _route_ff_revision_lines(
    user_input: str,
    valid_names: list[str],
    locked_names: list[str],
) -> tuple[dict[str, str], list[str], list[str], bool]:
    """Deterministically route review-turn revision lines by name.

    Returns (routed, unknown, locked_hits, saw_pair). Routing is atomic at
    the call site: any unknown or locked name means nothing is applied.
    ``saw_pair`` distinguishes "tried to give revisions and got the format
    wrong" from free-form input, mirroring the priority-edit reader.
    """
    routed: dict[str, str] = {}
    unknown: list[str] = []
    locked_hits: list[str] = []
    saw_pair = False
    for line in user_input.splitlines():
        if not line.strip():
            continue
        m = _FF_REVISION_RE.match(line)
        if not m:
            continue
        saw_pair = True
        name, instruction = m.group(1), m.group(2)
        if name in locked_names:
            locked_hits.append(name)
        elif name not in valid_names:
            unknown.append(name)
        else:
            routed[name] = instruction
    return routed, unknown, locked_hits, saw_pair


def _spec_ff_review_prompt(locked_names: list[str]) -> str:
    prompt = (
        "\n\n---\n**Comprehensive review.** Reply **yes** to save "
        "`ai_features.json` with all specs as shown, or give revisions one "
        "per line as `feature_name: instruction`."
    )
    if locked_names:
        prompt += (
            "\nLocked (confirmed earlier, not revisable here): "
            + ", ".join(f"`{n}`" for n in locked_names)
            + "."
        )
    return prompt


def _present_spec_ff_review(
    session: dict[str, Any],
    only_indices: list[int] | None = None,
    failure_note: str = "",
) -> Generator[str, None, None]:
    """Render the comprehensive spec review (or just re-drafted entries)."""
    msgs = session["agentifier_messages"]
    catalog_entries = (session.get("ai_catalog") or {}).get("ai_catalog", [])
    n = len(catalog_entries)
    results = session.get("agentifier_spec_results") or []
    locked = session.get("agentifier_spec_ff_locked") or 0
    locked_names = [e.get("name", "") for e in catalog_entries[:locked]]

    indices = only_indices if only_indices is not None else list(range(n))
    parts: list[str] = []
    if only_indices is None:
        parts.append("## Comprehensive spec review\n")
    for i in indices:
        entry = catalog_entries[i]
        spec = results[i] if len(results) > i else {}
        if i < locked:
            parts.append(
                f"*(locked — confirmed earlier)*\n"
                f"{format_spec_as_text(entry, spec, i, n)}"
            )
        elif not spec:
            parts.append(
                f"### Feature {i + 1}/{n}: `{entry.get('name', '')}` — "
                "*(not yet drafted)*"
            )
        else:
            parts.append(format_spec_as_text(entry, spec, i, n))
    display = "\n\n".join(parts) + _spec_ff_review_prompt(locked_names) + failure_note
    msgs.append({"role": "assistant", "content": display})
    session["_display_override"] = display
    yield display
