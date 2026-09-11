"""This round's revision delta, read off the Brainstormer-stamped vision.

One function, and a leaf: it imports nothing from ``spec4``. The Agentifier, the
Designer, StackAdvisor, Phaser and the Deployer each read the delta through it. Until
cleanup Phase 8 (``PHASE8_RECORD.md``, sub-phase 8d2) each of the five carried its own
token-identical copy (``CLEANUP_INVENTORY.md`` 67.11).
"""

from __future__ import annotations

from typing import Any

__all__ = ["revision_delta"]


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
