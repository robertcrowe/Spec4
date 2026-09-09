"""Helpers more than one callback module needs.

Cleanup Phase 4g split ``spec4.callbacks`` into four modules; this one holds the
three names that would otherwise have to be imported across them. It imports no
sibling and nothing from the package ``__init__`` -- the direction the layering
contract's rule 4 pins (CLEANUP_INVENTORY.md 15.2), and the reason
``callbacks/designer.py`` now reaches ``_open_pick_fields`` here rather than
through the package that imports ``designer`` for registration.

``_gate_agent`` is here rather than beside the gate callbacks -- in
:mod:`spec4.callbacks._chat` when 4g wrote this, in
:mod:`spec4.callbacks._gate` since 4g2 -- because ``_open_pick_fields`` calls
it: leaving it there would make this module import a sibling and invert the
dependency.
"""

from __future__ import annotations

import pathlib
from typing import Any

from spec4 import llm_selection


_HOME = str(pathlib.Path.home())


def _gate_agent(session: dict[str, Any]) -> str:
    """Which agent the open gate belongs to."""
    draft = session.get("agent_llm_draft") or {}
    if draft.get("agent"):
        return str(draft["agent"])
    if session.get("phase") == "designer":
        return "designer"
    return str(session.get("active_agent") or "brainstormer")


def _open_pick_fields(
    session: dict[str, Any], *, retry: bool = False
) -> dict[str, Any]:
    """Expand the gate into the provider/key/model fields.

    Seeded from any existing override, so an unchanged provider and key need no
    Connect round trip: the model list came with the entry, which is what makes
    "pick a different model" one click and a dropdown rather than a re-type.

    ``retry`` marks a picker opened from a failed step. Two things follow from
    it, and *only* from it — a picker opened deliberately (the chip, or agent
    entry) behaves exactly as before:

    * choosing a model re-runs the failed step immediately, and
    * a model the tool probe reports as incapable is refused rather than
      committed.

    The second bends the rule that probes are advisory and never block. It is
    bent here because this is the one path where the app spends a call without
    asking again, and it must not spend it on a model just measured as unable to
    do the step.
    """
    agent = _gate_agent(session)
    existing = llm_selection.entry(session, agent) or {}
    draft: dict[str, Any] = {"agent": agent}
    if retry:
        draft["retry"] = True
    if existing:
        draft.update(
            {
                "provider": existing.get("provider"),
                "api_key": (existing.get("llm_config") or {}).get("api_key", ""),
                "available_models": existing.get("available_models") or [],
                "model": existing.get("model"),
            }
        )
    return {**session, "agent_llm_draft": draft, "agent_llm_error": None}
