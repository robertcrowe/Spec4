"""The revision re-emission diff: which established entries did the model drop?

In a revision round StackAdvisor is seeded with the previous implemented
version's ``stack.json`` and asked to emit the FULL updated spec with this
revision's incremental changes folded in. Re-emitting a large JSON artifact is
exactly where a model drops a line nobody asked it to drop — a live FF-round
draw lost an established ``SendGrid`` library entry with no signal anywhere:
Phaser then planned against a stack missing a library the shipped code depends
on, and the developer was reviewing a plan, not a diff.

This module is the deterministic diff that closes that gap (D-RD series):

* :func:`revision_removals` keys every list- or name-keyed block of the prior
  and new spec with the normaliser's own ``_keyed_from_list`` (one keying
  scheme, not two) and reports each prior key absent from the new spec as a
  :class:`Removal`, classified by *why* it may have gone (D-RD0):

  - ``requested_by_delta`` — the entry is named after, or served only, a
    feature the Brainstormer-stamped delta lists under ``removed``;
  - ``requested_in_conversation`` — the developer named the entry in one of
    this round's StackAdvisor turns (the seed is excluded: it pastes the whole
    prior stack and would match everything);
  - ``unrequested`` — nothing asked for it.

* :func:`restore_unrequested` puts each unrequested entry back at its prior
  position (lossless assembly: nodes survive, restructuring edits edges —
  D-RD2). The receipt makes the restoration visible rather than silent.
* :func:`removals_record` is the envelope-level instrument persisted on every
  revision commit, empty list included, so a later probe can measure how often
  the model drops entries and how often the restore fires (D-RD3). It carries
  keys and dispositions only — never entry bodies — so it adds no key paths
  inside ``stack_spec`` for ``undeclared_keys.py`` to flag and no signal
  fields for ``stack_routing.stack_signal_entries`` to pick up.
* :func:`render_revision_receipt` renders the two receipt sections the commit
  display carries ("Restored to the established stack" / "Removed from the
  established stack").

No Dash, no session, no LLM call. The one caller is ``run`` in the package
``__init__``, immediately before ``_stack_commit``.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

from spec4.agents._feature_context import slug
from spec4.agents.stack_advisor._stack_shape import (
    _keyed_from_list,
    _normalise_stack_shape,
)

__all__ = [
    "Removal",
    "removals_record",
    "render_revision_receipt",
    "restore_unrequested",
    "revision_removals",
]

REQUESTED_BY_DELTA = "requested_by_delta"
REQUESTED_IN_CONVERSATION = "requested_in_conversation"
UNREQUESTED = "unrequested"

#: Envelope-level key the instrument is persisted under (D-RD3).
REVISION_REMOVALS_KEY = "revision_removals"

#: List-shaped blocks, keyed by the first non-empty of ``name_fields`` else by
#: position (the normaliser's own fallback). ``security.auth`` entries carry
#: ``mechanism`` rather than ``name``; ``project_structure`` carries ``path``;
#: ``references`` carries ``standard`` / ``url``. Provider ``capabilities`` are
#: deliberately absent (D-RD4): they have no stable name field, so a positional
#: diff would report noise, not removals.
_LIST_BLOCKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("languages", ("name",)),
    ("deployment.targets", ("name",)),
    ("integrations", ("name",)),
    ("security.auth", ("mechanism", "name")),
    ("libraries", ("name",)),
    ("project_structure", ("path", "name")),
    ("additional_decisions", ("name",)),
    ("references", ("standard", "url")),
)

#: Blocks the normaliser keys by name (D-SC18b); their keys are the entry keys.
_KEYED_BLOCKS: tuple[str, ...] = (
    "providers",
    "persistence",
    "infrastructure",
    "ai_conventions",
)

#: Nested list under every ``persistence.<store>``, keyed by ``name``.
_COLLECTIONS_NAME_FIELDS: tuple[str, ...] = ("name",)


@dataclass(frozen=True)
class Removal:
    """One prior-stack entry absent from the re-emitted stack.

    ``block`` is the dotted path of the list or keyed object the entry lived in
    (``libraries``, ``persistence.primary_store.collections``); ``key`` is its
    name under the normaliser's keying; ``prior_index`` its position there.
    ``disposition`` is one of the three module constants and ``matched`` names
    the evidence (the removed feature, or the user turn's first matching line)
    — empty for ``unrequested``. ``entry`` is the prior entry itself, carried
    for restoration and never persisted.
    """

    block: str
    key: str
    prior_index: int
    disposition: str
    matched: str
    entry: Any

    @property
    def unrequested(self) -> bool:
        return self.disposition == UNREQUESTED


# ---------------------------------------------------------------------------
# Walking the two specs
# ---------------------------------------------------------------------------


def _inner(stack: dict[str, Any]) -> dict[str, Any]:
    ss = stack.get("stack_spec") or stack.get("stack") or stack
    return ss if isinstance(ss, dict) else {}


def _resolve(ss: dict[str, Any], dotted: str) -> Any:
    node: Any = ss
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _keyed_blocks(ss: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every diffable block of ``ss`` as ``{dotted_block: {key: entry}}``."""
    out: dict[str, dict[str, Any]] = {}
    for block, name_fields in _LIST_BLOCKS:
        items = _resolve(ss, block)
        if isinstance(items, list):
            prefix = block.rsplit(".", 1)[-1].rstrip("s") or "entry"
            out[block] = _keyed_from_list(items, name_fields=name_fields, prefix=prefix)
    for block in _KEYED_BLOCKS:
        val = ss.get(block)
        if isinstance(val, dict):
            out[block] = {str(k): v for k, v in val.items()}
    stores = ss.get("persistence")
    if isinstance(stores, dict):
        for store_key, store in stores.items():
            colls = store.get("collections") if isinstance(store, dict) else None
            if isinstance(colls, list):
                out[f"persistence.{store_key}.collections"] = _keyed_from_list(
                    colls, name_fields=_COLLECTIONS_NAME_FIELDS, prefix="collection"
                )
    return out


# ---------------------------------------------------------------------------
# Disposition (D-RD0)
# ---------------------------------------------------------------------------


def _removed_feature_ids(delta: dict[str, Any] | None) -> dict[str, str]:
    """``{slug: name}`` for every feature the delta lists as removed."""
    changes = (delta or {}).get("changes") or {}
    removed = changes.get("removed") or []
    return {slug(str(n)): str(n) for n in removed if str(n).strip()}


def _served_features(entry: Any) -> list[str]:
    if not isinstance(entry, dict):
        return []
    served = entry.get("serves_features")
    if isinstance(served, str):
        served = [served]
    return (
        [slug(str(s)) for s in served if str(s).strip()]
        if isinstance(served, list)
        else []
    )


def _requested_by_delta(key: str, entry: Any, removed: dict[str, str]) -> str | None:
    """The removed feature that accounts for this entry, else None.

    Two joins: the entry is named after a removed feature (collections and
    integrations are routinely named for the feature they serve), or the
    entry's ``serves_features`` is non-empty and every id in it is removed —
    it served nothing else, so it goes with the feature.
    """
    if not removed:
        return None
    key_slug = slug(key)
    if key_slug in removed:
        return removed[key_slug]
    served = _served_features(entry)
    if served and all(s in removed for s in served):
        return removed[served[0]]
    return None


def _requested_in_conversation(key: str, user_turns: list[str]) -> str | None:
    """The first user line naming this entry, else None.

    A whole-word, case-insensitive match on the entry's key. Any mention
    counts: the developer naming an established entry in a revision turn is
    the one signal the diff has that its fate was discussed, and the receipt
    still records the removal so a misread is visible rather than silent.
    """
    if not key.strip():
        return None
    pattern = re.compile(rf"(?<![\w-]){re.escape(key.strip())}(?![\w-])", re.IGNORECASE)
    for turn in user_turns:
        for line in turn.splitlines():
            if pattern.search(line):
                return line.strip()
    return None


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def revision_removals(
    prior_stack: dict[str, Any],
    new_stack: dict[str, Any],
    delta: dict[str, Any] | None,
    user_turns: list[str] | None = None,
) -> list[Removal]:
    """Every prior-stack entry absent from ``new_stack``, with its disposition.

    ``prior_stack`` is normalised on a copy before keying (a stack read back
    from disk may carry the pre-D-SC27 category-keyed ``libraries`` that
    ``merge_library_additions`` still writes); ``new_stack`` arrives already
    normalised from ``_extract_stack_json`` and is read as-is. Order follows
    the prior spec: block by block, entry by entry.
    """
    prior = _inner(_normalise_stack_shape(copy.deepcopy(prior_stack)))
    new = _inner(new_stack)
    removed = _removed_feature_ids(delta)
    turns = user_turns or []

    prior_blocks = _keyed_blocks(prior)
    new_blocks = _keyed_blocks(new)
    out: list[Removal] = []
    for block, prior_entries in prior_blocks.items():
        new_entries = new_blocks.get(block, {})
        for index, (key, entry) in enumerate(prior_entries.items()):
            if key in new_entries:
                continue
            feature = _requested_by_delta(key, entry, removed)
            if feature is not None:
                out.append(
                    Removal(block, key, index, REQUESTED_BY_DELTA, feature, entry)
                )
                continue
            line = _requested_in_conversation(key, turns)
            if line is not None:
                out.append(
                    Removal(block, key, index, REQUESTED_IN_CONVERSATION, line, entry)
                )
                continue
            out.append(Removal(block, key, index, UNREQUESTED, "", entry))
    return out


def restore_unrequested(new_stack: dict[str, Any], removals: list[Removal]) -> int:
    """Put every unrequested removal back into ``new_stack`` in place (D-RD2).

    A list entry returns at its prior index, clamped to the list's current
    length; a keyed-object entry returns at its prior position in key order. A
    block the new spec no longer has at all is recreated. Returns the number
    of entries restored.
    """
    ss = _inner(new_stack)
    restored = 0
    for removal in removals:
        if not removal.unrequested:
            continue
        if removal.block in _KEYED_BLOCKS:
            _restore_keyed(ss, removal)
        else:
            _restore_listed(ss, removal)
        restored += 1
    return restored


def _restore_listed(ss: dict[str, Any], removal: Removal) -> None:
    parts = removal.block.split(".")
    node: Any = ss
    for part in parts[:-1]:
        child = node.get(part) if isinstance(node, dict) else None
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    items = node.get(parts[-1]) if isinstance(node, dict) else None
    if not isinstance(items, list):
        items = []
        node[parts[-1]] = items
    items.insert(min(removal.prior_index, len(items)), copy.deepcopy(removal.entry))


def _restore_keyed(ss: dict[str, Any], removal: Removal) -> None:
    block = ss.get(removal.block)
    if not isinstance(block, dict):
        block = {}
    entries = list(block.items())
    entries.insert(
        min(removal.prior_index, len(entries)),
        (removal.key, copy.deepcopy(removal.entry)),
    )
    ss[removal.block] = dict(entries)


def removals_record(removals: list[Removal]) -> list[dict[str, str]]:
    """The persisted form of the diff (D-RD3): keys and dispositions only."""
    return [
        {
            "block": r.block,
            "key": r.key,
            "disposition": r.disposition,
            "matched": r.matched,
        }
        for r in removals
    ]


def render_revision_receipt(removals: list[Removal]) -> str:
    """The receipt sections for the commit display; empty when nothing dropped.

    Unrequested removals are reported as restored (they are, by
    :func:`restore_unrequested`); requested ones as removed, each with the
    evidence that made it a request.
    """
    restored = [r for r in removals if r.unrequested]
    removed = [r for r in removals if not r.unrequested]
    lines: list[str] = []
    if restored:
        lines.append("**Restored to the established stack**\n")
        lines.append(
            "These entries were in the established stack and absent from the "
            "re-emitted spec, but nothing in this revision asked to remove them. "
            "They have been put back; tell me if any should go.\n"
        )
        lines.extend(f"- `{r.key}` ({_block_label(r.block)})" for r in restored)
        lines.append("")
    if removed:
        lines.append("**Removed from the established stack**\n")
        for r in removed:
            why = (
                f"removed feature *{r.matched}*"
                if r.disposition == REQUESTED_BY_DELTA
                else f"you said: “{r.matched}”"
            )
            lines.append(f"- `{r.key}` ({_block_label(r.block)}) — {why}")
        lines.append("")
    return "\n".join(lines)


def _block_label(block: str) -> str:
    return block.replace("_", " ").replace(".", " › ")
