"""Deterministic stack→phase and NFR→phase joins (D-PH3 / D-PH4).

Leaf module: imports nothing from ``spec4.agents`` so ``project_manager`` can
join at render time without an import cycle (``agents._utils`` imports
``project_manager``; both import from here).

Phases declare what they build in two id spaces (``features[]`` — product ids,
``capabilities[]`` — AI catalog ids; D-PH2a), and stack entries carry
``serves_features`` / ``serves_capabilities`` backlinks (StackAdvisor D-SC
series). That makes two joins mechanical, so they are code, not prompt:

* **Stack routing** (D-PH3): a serving stack entry attaches to every phase
  whose declarations intersect its served ids, each serves key matched against
  its own array. ``status: optional/deferred`` entries are roadmap and never
  route. An entry whose served features are all *excluded* routes nowhere for
  free — an excluded feature is never declared (enforced by
  ``check_phase_coverage``), so the intersection is empty by construction.
  Entries with no serves keys are the project-wide baseline, rendered in every
  phase so a global staple can never silently vanish from the plan.

* **NFR threading** (D-PH4): a non-functional goal claimed by serving entries
  (``satisfies_nfr``) threads into the phases those entries route to; a goal
  claimed only by global entries threads into the final phase as project-wide
  acceptance. Orphaned goals (no claim) are never threaded — surfacing them is
  conversational, and inventing a claim is forbidden.

The walker (``stack_signal_entries``) is the single owner of "what is a stack
entry and what is it called" — the Phaser seed digest renders through it too.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "ROADMAP_STATUSES",
    "baseline_library_names",
    "derived_nfr_ids",
    "entries_for_declarations",
    "nfr_threads",
    "stack_signal_entries",
]

ROADMAP_STATUSES = ("optional", "deferred")

#: Container keys that never identify a stack entry on their own. An unnamed
#: entry (a provider ``capabilities[]`` item; persistence stores are keyed, and
#: the store key IS the identity) takes the nearest ancestor key *outside* this
#: set as its name — e.g. ``providers.OpenAI.capabilities[0]`` names ``OpenAI``.
_STACK_CONTAINER_KEYS = frozenset({
    "capabilities",
    "collections",
    "libraries",
    "integrations",
    "infrastructure",
    "targets",
    "auth",
    "providers",
    "persistence",
    "deployment",
    "security",
    "stack_spec",
})

#: The join/semantics fields whose presence makes a stack object an "entry".
_STACK_SIGNAL_FIELDS = (
    "serves_features",
    "serves_capabilities",
    "satisfies_nfr",
    "satisfies_infra",
    "status",
)


def _slug(name: str) -> str:
    """Mirror ``spec4.agents._utils.slug`` (kept local: leaf module)."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower()) if name else ""


def stack_signal_entries(stack: dict[str, Any]) -> list[dict[str, Any]]:
    """Every stack object carrying at least one signal field, with an identity.

    Walks the whole (wrapped or bare) stack spec. Each item:
    ``{label, section, entry}`` — ``label`` is the entry's own ``name`` when
    present, else the nearest non-container ancestor key, suffixed with the
    entry's ``tier`` when the name was a fallback (sibling provider
    capabilities stay distinguishable); ``section`` is the top-level stack key
    the entry lives under (``libraries``, ``persistence``, ...).
    """
    out: list[dict[str, Any]] = []

    def walk(obj: Any, key_name: str, section: str) -> None:
        if isinstance(obj, dict):
            if any(f in obj for f in _STACK_SIGNAL_FIELDS):
                own = obj.get("name")
                label = str(own or key_name or section or "entry")
                if not own and obj.get("tier"):
                    label = f"{label} [{obj['tier']}]"
                out.append({"label": label, "section": section, "entry": obj})
            for k, v in obj.items():
                k = str(k)
                child_key = k if k not in _STACK_CONTAINER_KEYS else key_name
                child_section = section or (k if k != "stack_spec" else "")
                walk(v, child_key, child_section)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, key_name, section)

    walk(stack, "", "")
    return out


def _spec(stack: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(stack, dict):
        return {}
    inner = stack.get("stack_spec")
    return inner if isinstance(inner, dict) else stack


def _is_roadmap(entry: dict[str, Any]) -> bool:
    return str(entry.get("status") or "") in ROADMAP_STATUSES


def _served(entry: dict[str, Any], key: str) -> set[str]:
    return {str(x) for x in (entry.get(key) or []) if str(x)}


def entries_for_declarations(
    stack: dict[str, Any] | None,
    feature_ids: set[str],
    capability_ids: set[str],
) -> list[dict[str, Any]]:
    """Serving stack entries routed to a phase's declarations (D-PH3a).

    Returns records ``{label, section, entry, matched}`` where ``matched`` is
    the sorted list of declared ids the entry serves (union across both serves
    keys, each matched against its own array's ids). Roadmap-status entries
    never route. Order follows the walker (stack-spec order), deduplicated by
    object identity.
    """
    if not isinstance(stack, dict) or not stack:
        return []
    out: list[dict[str, Any]] = []
    for rec in stack_signal_entries(stack):
        entry = rec["entry"]
        if _is_roadmap(entry):
            continue
        matched = sorted(
            (_served(entry, "serves_features") & feature_ids)
            | (_served(entry, "serves_capabilities") & capability_ids)
        )
        if matched:
            out.append({**rec, "matched": matched})
    return out


def baseline_library_names(stack: dict[str, Any] | None) -> list[str]:
    """Library names with no serves keys and no roadmap status (D-PH3b).

    The project-wide staples: rendered in every phase so none can silently
    vanish from the plan. Libraries only — persistence stores are structural
    (their collections route individually) and providers route via their
    capability entries. Handles both observed ``libraries`` shapes (flat list,
    dict-of-tiers).
    """
    libs = _spec(stack).get("libraries")
    flat: list[Any] = []
    if isinstance(libs, dict):
        for group in libs.values():
            if isinstance(group, list):
                flat.extend(group)
    elif isinstance(libs, list):
        flat = list(libs)
    out: list[str] = []
    for lib in flat:
        if not isinstance(lib, dict) or not lib.get("name"):
            continue
        if lib.get("serves_features") or lib.get("serves_capabilities"):
            continue
        if _is_roadmap(lib):
            continue
        out.append(str(lib["name"]))
    return out


def derived_nfr_ids(feature_specs: dict[str, Any] | None) -> dict[str, str]:
    """``nfr_<slug>`` id → goal text, for every project non-functional goal.

    The D-SC2 derivation, kept in one place: ``feature_specs.nfr_goals`` is a
    list of outcome-phrased strings, and every consumer that needs to talk about
    a goal by id derives it the same way. Order follows the source list, so
    callers iterating this dict get a stable goal order.

    Returns every goal, claimed or not. Callers that must exclude orphans (goal
    threading, where inventing a claim is forbidden) filter on top; callers that
    must surface them honestly (deployment planning, where an unclaimed but
    deployment-relevant goal is the interesting case) do not.
    """
    out: dict[str, str] = {}
    for goal in ((feature_specs or {}).get("nfr_goals") or []):
        if isinstance(goal, str) and goal.strip():
            out[f"nfr_{_slug(goal.strip())}"] = goal.strip()
    return out


def nfr_threads(
    stack: dict[str, Any] | None,
    feature_specs: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Claimed non-functional goals with their deterministic phase targets.

    For each ``nfr_<slug>`` derived from ``feature_specs.nfr_goals`` (the
    D-SC2 rule) that at least one stack entry claims (``satisfies_nfr``):

    ``{nfr_id, goal, claimers, serves_features, serves_capabilities, global}``

    * ``serves_features`` / ``serves_capabilities`` — the union of served ids
      across claiming entries: the goal threads into phases declaring any of
      them (D-PH4a/b).
    * ``global`` — True when NO claiming entry carries a serves key: the goal
      threads into the final phase as project-wide acceptance.

    Orphaned goals (no claim) are omitted — never threaded, never invented.
    Claims matching no derived goal are omitted too (unknown ids are a
    stack-side drift signal, not a plan input).
    """
    derived = derived_nfr_ids(feature_specs)
    if not derived or not isinstance(stack, dict) or not stack:
        return []

    by_id: dict[str, dict[str, Any]] = {}
    for rec in stack_signal_entries(stack):
        entry = rec["entry"]
        for raw in (entry.get("satisfies_nfr") or []):
            nid = str(raw)
            if nid not in derived:
                continue
            rec_out = by_id.setdefault(
                nid,
                {
                    "nfr_id": nid,
                    "goal": derived[nid],
                    "claimers": [],
                    "serves_features": set(),
                    "serves_capabilities": set(),
                },
            )
            rec_out["claimers"].append(rec["label"])
            rec_out["serves_features"] |= _served(entry, "serves_features")
            rec_out["serves_capabilities"] |= _served(
                entry, "serves_capabilities"
            )

    out: list[dict[str, Any]] = []
    for nid in derived:  # stable goal order
        if nid not in by_id:
            continue
        rec_out = by_id[nid]
        rec_out["claimers"] = sorted(set(rec_out["claimers"]))
        rec_out["serves_features"] = set(rec_out["serves_features"])
        rec_out["serves_capabilities"] = set(rec_out["serves_capabilities"])
        rec_out["global"] = not (
            rec_out["serves_features"] or rec_out["serves_capabilities"]
        )
        out.append(rec_out)
    return out