"""D-SC34 — every field the schema declares must be able to reach the page.

The receipt ``_format_stack_as_text`` produces is the developer's only view of
what was persisted, and a field the renderer drops is indistinguishable from a
field the model never emitted. So a silent drop does not merely look untidy: it
removes the one check that would catch a lost decision.

The old renderer was a whitelist, and three ratified fields had already landed
behind it unnoticed — ``physical`` (D-SC11), ``satisfies_nfr`` on library entries
(D-SC2), and ``foundational`` (D-SC4). None of them had ever been seen by a user.
D-SC33 made the renderer total instead: known keys get bespoke formatting and
everything else falls through to a generic printer, so guessing the schema wrong
costs cosmetics rather than invisibility.

These tests are the floor under that. They are **draw-independent** — no live
model, no fixture that could drift from what the prompt actually says — because
they read the exemplar out of ``SYSTEM_PROMPT`` itself. That coupling is the
point: add a field to the exemplar and the sentinel test forces the renderer to
handle it, so exemplar and renderer cannot silently diverge again.

The instrument matters as much as the reading. A plain ``value in rendered``
check reports a false negative whenever the same value appears elsewhere in the
text — it scored ``satisfies_nfr`` as rendered because the identical nfr id
appeared under persistence. Substituting a unique sentinel and re-rendering is
immune to that.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

import pytest

from spec4.agents.stack_advisor import SYSTEM_PROMPT, _format_stack_as_text

_SENTINEL = "ZQXJ7SENTINEL"


def _exemplar() -> dict[str, Any]:
    """The schema example the prompt actually ships, parsed from the prompt."""
    match = re.search(r"```json\n(\{.*?\n\})\n```", SYSTEM_PROMPT, re.S)
    assert match, "no fenced JSON exemplar found in SYSTEM_PROMPT"
    return json.loads(match.group(1))


def _leaf_paths(node: Any, path: str = "") -> list[str]:
    """Every scalar leaf in the spec, as an assignable path."""
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


def _renders(path: str) -> bool:
    """True if a sentinel placed at ``path`` reaches the rendered receipt."""
    spec = copy.deepcopy(_exemplar())
    _assign(spec, path, _SENTINEL)
    return _SENTINEL in _format_stack_as_text(spec)


def test_exemplar_parses() -> None:
    assert "stack_spec" in _exemplar()


@pytest.mark.parametrize("path", _leaf_paths(_exemplar()["stack_spec"]))
def test_every_exemplar_field_can_reach_the_page(path: str) -> None:
    """The floor: no field the schema demonstrates may be silently dropped.

    Parametrised per field so a regression names the field it lost rather than
    reporting a count.
    """
    assert _renders(f"stack_spec.{path}"), (
        f"`{path}` is in the schema exemplar but cannot reach the rendered "
        f"receipt — the developer would have no way to tell it from a field the "
        f"model never emitted."
    )


def test_the_sentinel_probe_can_actually_fail() -> None:
    """Guard the instrument: a field the renderer ignores must read as dropped.

    Without this, a probe that silently always passed would look identical to a
    total renderer.
    """
    spec = copy.deepcopy(_exemplar())
    spec["stack_spec"]["languages"][0]["__never_rendered__"] = _SENTINEL
    rendered = _format_stack_as_text(spec)
    assert _SENTINEL in rendered, (
        "the generic fall-through should render an unknown key; if this fails "
        "the renderer is no longer total"
    )


def test_unknown_top_level_key_still_renders() -> None:
    """An invented top-level key costs cosmetics, not invisibility (D-SC33)."""
    spec = copy.deepcopy(_exemplar())
    spec["stack_spec"]["some_block_we_never_declared"] = {"decision": _SENTINEL}
    assert _SENTINEL in _format_stack_as_text(spec)


def test_unknown_key_inside_a_known_block_still_renders() -> None:
    """The shape the live draws actually produced: an invented field in a block.

    FareBox invented ``deployment.frontend_hosting`` and Threadline invented
    ``coding_style.backend_linter``; both vanished. Neither key is declared now
    either — the point is that inventing one is no longer silent.
    """
    spec = copy.deepcopy(_exemplar())
    spec["stack_spec"]["deployment"]["frontend_hosting"] = _SENTINEL
    assert _SENTINEL in _format_stack_as_text(spec)


def test_deviant_scalar_where_a_block_is_expected_does_not_crash() -> None:
    spec = copy.deepcopy(_exemplar())
    spec["stack_spec"]["providers"] = "decided later"
    assert "decided later" in _format_stack_as_text(spec)


def test_legacy_string_languages_still_render() -> None:
    """Pre-D-SC26 stacks carried `languages` as a list of bare strings."""
    spec = copy.deepcopy(_exemplar())
    spec["stack_spec"]["languages"] = ["Python", "TypeScript"]
    rendered = _format_stack_as_text(spec)
    assert "Python" in rendered and "TypeScript" in rendered


# --- D-SC51: totality closed the drop path, not the garble path ---------------


def _garbled_stack() -> dict:
    """The live Ragmeister shapes verbatim: a sentence where a list belongs.

    `policy_audit_log` and `inquiry_log` hold no domain entity, so the model wrote
    a description into `entities` -- which the renderer then iterated one character
    at a time, putting `holds P, o, l, i, c, y,  , c, h, a, n, g, e...` on the
    developer's receipt. D-SC33 made the renderer total, which stopped fields being
    dropped; nothing stopped them being mangled.
    """
    return {"stack_spec": {"persistence": {"primary_store": {
        "choice": "PostgreSQL 16",
        "durability": "source of truth",
        "collections": [
            {"name": "policy_audit_log", "entities": "Policy change history",
             "serves_features": "policy_library_management"},
            {"name": "policies", "entities": ["Policy"],
             "serves_features": ["policy_qa"]},
        ],
    }}}}


def test_a_string_where_entities_expects_a_list_does_not_garble() -> None:
    out = _format_stack_as_text(_garbled_stack())
    assert "P, o, l, i, c, y" not in out
    assert "holds Policy change history" in out


def test_a_string_where_serves_features_expects_a_list_does_not_garble() -> None:
    out = _format_stack_as_text(_garbled_stack())
    assert "`p`, `o`, `l`" not in out
    assert "`policy_library_management`" in out


def test_well_formed_lists_are_unaffected_by_the_coercion() -> None:
    out = _format_stack_as_text(_garbled_stack())
    assert "holds Policy" in out
    assert "`policy_qa`" in out
