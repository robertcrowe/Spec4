"""Deterministic seed material for a Phaser turn: the design note and the
revision delta.

Three functions the seed builders in ``run`` call before any model text
exists: the UI-mock note (``_load_phaser_design_note``, the one filesystem
read in the package), and the revision-round pair that reads the vision's
Brainstormer-stamped ``revision_history`` and renders it into a phase-scoping
note. None of them touch the session, the LLM, or the emitted phases.

Split out of ``phaser.py`` in Phase 4e; the package ``__init__`` re-exports
every name below under its original spelling. ``revision_delta`` itself lives in
:mod:`spec4.agents._revision` since cleanup Phase 8, shared by the five agents
that read it, and is re-exported here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spec4.agents._revision import revision_delta as revision_delta


def _load_phaser_design_note(design_dir: Path, version: int) -> str:
    """Return a note about the UI design mock for inclusion in the Phaser seed."""
    mock_path = design_dir / "mock.html"
    if mock_path.exists() and mock_path.read_text(encoding="utf-8").strip():
        return (
            f"A finalized UI design mock is available at "
            f".spec4/v{version}/design/mock.html. "
            "Direct the coding agent to reference this file during implementation "
            "to match the intended visual design."
        )
    return (
        "No UI design mock was produced. UI design decisions are left to the "
        "developer's discretion."
    )


def build_revision_note(delta: dict[str, Any]) -> str:
    """Render a revision delta into a phase-scoping note for the revision seed.

    Produces a single bracketed instruction (same shape as the staleness note)
    that scopes the phase plan to this revision's ``key_features_mvp`` changes
    while treating the rest of the system as already built and in place.
    Deterministic — the ``added`` / ``modified`` / ``removed`` names come straight
    from the Brainstormer-stamped delta; the model never authors them.
    """
    changes = delta.get("changes") or {}
    added = list(changes.get("added") or [])
    modified = list(changes.get("modified") or [])
    removed = list(changes.get("removed") or [])
    goal = (delta.get("goal") or "").strip()

    segments: list[str] = ["[This is a revision of an already-implemented project."]
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
            " Plan phases only for this revision's " + "; ".join(clauses) + "."
        )
    segments.append(
        " Treat the rest of the system as already built and in place — do not "
        "re-plan phases for established, unchanged surface. Number the new phases "
        "1..k as a self-contained set.]"
    )
    return "".join(segments)
