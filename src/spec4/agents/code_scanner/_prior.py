"""The ``prior_round`` block of the ``scan`` layer: what the last implemented
Spec4 round planned, as an extract (1d).

The block is for the consumers that today open ``.spec4/`` themselves, or
cannot: the scanner's own update-mode draw, Phaser's "what did we build last
time", and ``plan_drift`` beside it. It is an *extract*, never a pass-through
(D-SC1d-1) — a round's phases, stack, vision, feature specs and AI catalog run
to several hundred kilobytes, and what the comparisons need of them is the
ids, the names and the shape. The long prose stays on disk, where the files
still are; ``artifacts_present`` says which (D-SC1d-9), so a ``null`` extract
reads as "absent", not "unreadable".

One version, one directory (D-SC1d-3): everything comes from
``latest_implemented_version()``'s ``v{N}/``, and a missing file there is
``null`` or ``[]``, never a value from another round. The AI catalog is the
one named exception, since a round can be implemented without the Agentifier
having run (BWS4 v8); it falls back to the newest implemented round that has
one, and ``capabilities_from_version`` says which. The prior review is by
reference plus a small extract of what ``delta`` and ``plan_drift`` compare
(D-SC1d-2); its ``path`` is in the same tree, for a consumer that wants the
whole thing.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import pathlib
import re
from typing import Any

from spec4 import project_manager
from spec4.agents._feature_context import slug
from spec4.app_constants import (
    ARTIFACT_AI_FEATURES,
    ARTIFACT_CODE_REVIEW,
    ARTIFACT_FEATURE_SPECS,
    ARTIFACT_STACK,
    ARTIFACT_VISION,
)

_ARTIFACT_AI_CATALOG = "ai_catalog.json"
_ARTIFACT_DEPLOYMENT_PLAN = "deployment-plan.md"
_PHASES_DIR = "phases"
_DESIGN_DIR = "design"
_IMPLEMENTED_MARKER = "IMPLEMENTED"
_PHASE_FILE_RE = re.compile(r"^phase(\d+)\.md$")

# Which files the block names in ``artifacts_present`` (D-SC1d-9), in the
# order they are listed. Directories count when they hold anything.
_ARTIFACT_PROBES: tuple[tuple[str, str], ...] = (
    ("phases", _PHASES_DIR),
    ("stack", ARTIFACT_STACK),
    ("vision", ARTIFACT_VISION),
    ("feature_specs", ARTIFACT_FEATURE_SPECS),
    ("ai_features", ARTIFACT_AI_FEATURES),
    ("ai_catalog", _ARTIFACT_AI_CATALOG),
    ("design", _DESIGN_DIR),
    ("code_review", ARTIFACT_CODE_REVIEW),
    ("deployment_plan", _ARTIFACT_DEPLOYMENT_PLAN),
)

# The phase prose kept in the extract is capped: a phase summary runs to a
# paragraph and a verification section to several, and the block's budget
# is the ids and the shape, not the text (D-SC1d-1).
_MAX_PHASE_TEXT_CHARS = 400
_MAX_PHASES = 50
_MAX_CAPABILITIES = 200
_MAX_LIST = 200


def _read_text(path: pathlib.Path) -> str | None:
    """A file's text, or ``None`` when it cannot be read. The one I/O seam."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _read_json(path: pathlib.Path) -> dict[str, Any] | None:
    text = _read_text(path)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _names(items: Any, key: str = "name") -> list[str]:
    """The string ``key`` of each dict in a list, or bare strings, in order."""
    out: list[str] = []
    if not isinstance(items, list):
        return out
    for item in items:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and isinstance(item.get(key), str):
            out.append(item[key])
    return out[:_MAX_LIST]


def _pairs(items: Any, first: str, second: str) -> list[dict[str, Any]]:
    """``{first, second}`` per dict in a list; ``second`` is ``null`` when absent."""
    out: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return out
    for item in items:
        if isinstance(item, dict) and isinstance(item.get(first), str):
            value = item.get(second)
            out.append(
                {first: item[first], second: value if isinstance(value, str) else None}
            )
    return out[:_MAX_LIST]


def _keys(block: Any) -> list[str]:
    return sorted(str(k) for k in block) if isinstance(block, dict) else []


def _clip(text: Any) -> str | None:
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    return stripped[:_MAX_PHASE_TEXT_CHARS] if stripped else None


def _iso(epoch: float) -> str:
    return (
        datetime.datetime.fromtimestamp(epoch, tz=datetime.UTC)
        .replace(microsecond=0)
        .isoformat()
    )


# ---------------------------------------------------------------------------
# per-artifact extracts
# ---------------------------------------------------------------------------


def _declarations(items: Any) -> list[dict[str, Any]]:
    """The ``{id, role}`` of each phase feature or capability declaration.

    Phaser writes ``{id, role, scope_note}`` (D-PH2a); older rounds wrote bare
    id strings, which read as ``role: null``. ``scope_note`` stays on disk.
    """
    out: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return out
    for item in items:
        if isinstance(item, str):
            out.append({"id": item, "role": None})
        elif isinstance(item, dict) and isinstance(item.get("id"), str):
            role = item.get("role")
            out.append(
                {"id": item["id"], "role": role if isinstance(role, str) else None}
            )
    return out[:_MAX_LIST]


def phase_extract(phase: dict[str, Any]) -> dict[str, Any]:
    """One phase's frontmatter reduced to its ids, shape and clipped prose."""
    stack_spec = phase.get("tech_stack_spec")
    deps = stack_spec.get("dependencies") if isinstance(stack_spec, dict) else None
    number = phase.get("phase_number")
    return {
        "number": number if isinstance(number, int) else None,
        "title": _clip(phase.get("phase_title")),
        "summary": _clip(phase.get("phase_summary")),
        "verification": _clip(phase.get("verification")),
        "features": _declarations(phase.get("features")),
        "capabilities": _declarations(phase.get("capabilities")),
        "dependencies": [d for d in _names(deps) if d],
    }


def _phase_files(version_dir: pathlib.Path) -> list[pathlib.Path]:
    phases_dir = version_dir / _PHASES_DIR
    if not phases_dir.is_dir():
        return []
    numbered: list[tuple[int, pathlib.Path]] = []
    for p in phases_dir.iterdir():
        m = _PHASE_FILE_RE.match(p.name)
        if m and p.is_file():
            numbered.append((int(m.group(1)), p))
    return [p for _, p in sorted(numbered)][:_MAX_PHASES]


def phases_extract(version_dir: pathlib.Path) -> list[dict[str, Any]]:
    """Every parseable ``phases/phase{N}.md`` of a round, by number."""
    out: list[dict[str, Any]] = []
    for path in _phase_files(version_dir):
        text = _read_text(path)
        phase = None if text is None else project_manager.parse_phase_markdown(text)
        if phase is not None:
            out.append(phase_extract(phase))
    return out


def stack_extract(stack: dict[str, Any]) -> dict[str, Any]:
    """The stack's names and kinds; ``stack_spec`` or a bare spec both read."""
    ss = stack.get("stack_spec") or stack.get("stack") or stack
    if not isinstance(ss, dict):
        ss = {}
    deployment = ss.get("deployment")
    targets = deployment.get("targets") if isinstance(deployment, dict) else None
    persistence = ss.get("persistence")
    primary = (
        persistence.get("primary_store") if isinstance(persistence, dict) else None
    )
    choice = primary.get("choice") if isinstance(primary, dict) else primary
    return {
        "languages": _pairs(ss.get("languages"), "name", "version"),
        "libraries": _pairs(ss.get("libraries"), "name", "category"),
        "deployment_targets": _pairs(targets, "name", "kind"),
        "persistence_primary": choice if isinstance(choice, str) else None,
        "provider_names": _keys(ss.get("providers")),
        "infrastructure_keys": _keys(ss.get("infrastructure")),
        "integrations": _pairs(ss.get("integrations"), "name", "kind"),
    }


def _vision_feature_ids(vs: dict[str, Any]) -> list[str]:
    """``key_features_mvp`` ids: the entry's ``id`` or ``slug(name)``.

    The same container lookup and entry shapes as ``brainstormer.feature_names``
    (canonical ``{Name: {...}}``, ``{name, id}``, bare string); the id falls back
    to ``slug(name)``, the invariant ``assign_feature_ids`` stamps.
    """
    inner = vs.get("vision")
    kf = inner.get("key_features_mvp") if isinstance(inner, dict) else None
    if kf is None:
        kf = vs.get("key_features_mvp")
    ids: list[str] = []
    for item in kf if isinstance(kf, list) else []:
        if isinstance(item, str):
            ids.append(slug(item))
        elif isinstance(item, dict) and item:
            if isinstance(item.get("name"), str):
                ids.append(str(item.get("id") or slug(item["name"])))
            else:
                name, val = next(iter(item.items()))
                fid = val.get("id") if isinstance(val, dict) else None
                ids.append(str(fid or slug(str(name))))
    return ids[:_MAX_LIST]


def vision_extract(vision: dict[str, Any]) -> dict[str, Any]:
    """The vision's name, its feature ids and how many revisions it records."""
    vs = vision.get("vision_statement")
    if not isinstance(vs, dict):
        vs = vision
    history = vs.get("revision_history")
    name = vs.get("name")
    return {
        "name": name if isinstance(name, str) else None,
        "feature_ids": _vision_feature_ids(vs),
        "revision_count": len(history) if isinstance(history, list) else 0,
    }


def feature_specs_extract(specs: dict[str, Any]) -> dict[str, Any]:
    """The drafted specs' version and feature ids."""
    version = specs.get("version")
    return {
        "version": version if isinstance(version, int) else None,
        "feature_ids": _names(specs.get("features"), "id"),
    }


def capabilities_extract(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """Each ``ai_features`` node reduced to its id, kind, tier and joins."""
    out: list[dict[str, Any]] = []
    nodes = catalog.get("ai_features")
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            continue
        introduced = node.get("introduced_in_version")
        out.append(
            {
                "id": node["id"],
                "kind": node.get("kind") if isinstance(node.get("kind"), str) else None,
                "tier": node.get("tier") if isinstance(node.get("tier"), str) else None,
                "introduced_in_version": introduced
                if isinstance(introduced, int)
                else None,
                "linked_vision_features": _names(node.get("linked_vision_features")),
                "requires": _names(node.get("requires")),
            }
        )
    return out[:_MAX_CAPABILITIES]


def _review_fields(inner: dict[str, Any]) -> dict[str, Any]:
    """The review's fields, wherever its schema version keeps them.

    A schema-1 file carries them directly under ``code_review``; schema 2
    keeps them under ``code_review.review`` (D-EV1).
    """
    review = inner.get("review")
    return review if isinstance(review, dict) else inner


def _deployment(fields: dict[str, Any]) -> list[dict[str, Any]]:
    """``{kind, name}`` per deployment facet: ``paas`` → its platform, else its tool."""
    deployment = fields.get("deployment")
    out: list[dict[str, Any]] = []
    if not isinstance(deployment, dict):
        return out
    for kind, facet in deployment.items():
        if not isinstance(facet, dict):
            continue
        name = facet.get("platform") if kind == "paas" else facet.get("tool")
        out.append({"kind": str(kind), "name": name if isinstance(name, str) else None})
    return out


def review_extract(path: pathlib.Path, rel_path: str) -> dict[str, Any] | None:
    """The prior review by reference, plus what the comparisons read (D-SC1d-2)."""
    text = _read_text(path)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    inner = data.get("code_review") if isinstance(data, dict) else None
    if not isinstance(inner, dict):
        return None
    fields = _review_fields(inner)
    commands = fields.get("commands")
    project_type = fields.get("project_type")
    schema_version = inner.get("schema_version")
    return {
        "path": rel_path,
        "schema_version": schema_version if isinstance(schema_version, int) else None,
        "bytes": len(text.encode("utf-8")),
        "project_type": project_type if isinstance(project_type, str) else None,
        "commands": {str(k): v for k, v in commands.items() if isinstance(v, str)}
        if isinstance(commands, dict)
        else {},
        "deployment": _deployment(fields),
        "dependency_names": _names(fields.get("dependencies")),
    }


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------


def _present(version_dir: pathlib.Path) -> list[str]:
    out: list[str] = []
    for key, name in _ARTIFACT_PROBES:
        path = version_dir / name
        if path.is_dir():
            if any(path.iterdir()):
                out.append(key)
        elif path.is_file():
            out.append(key)
    return out


def _implemented_at(version_dir: pathlib.Path) -> str | None:
    implemented: str | None = None
    with contextlib.suppress(OSError):
        implemented = _iso((version_dir / _IMPLEMENTED_MARKER).stat().st_mtime)
    return implemented


def _catalog(working_dir: str) -> tuple[list[dict[str, Any]], int | None]:
    """The capabilities and the implemented round they came from.

    D-SC1d-3's one exception: the newest *implemented* round holding an
    ``ai_features.json``, which may be older than the round the rest of the
    block describes.
    """
    source = project_manager.latest_implemented_version_with(
        working_dir, ARTIFACT_AI_FEATURES
    )
    if source is None:
        return [], None
    catalog = _read_json(
        project_manager.get_version_dir(working_dir, source) / ARTIFACT_AI_FEATURES
    )
    if catalog is None:
        return [], None
    return capabilities_extract(catalog), source


def prior_round_block(working_dir: str) -> dict[str, Any] | None:
    """The ``prior_round`` block, or ``None`` when no round is implemented."""
    version = project_manager.latest_implemented_version(working_dir)
    if version is None:
        return None
    version_dir = project_manager.get_version_dir(working_dir, version)
    stack = _read_json(version_dir / ARTIFACT_STACK)
    vision = _read_json(version_dir / ARTIFACT_VISION)
    specs = _read_json(version_dir / ARTIFACT_FEATURE_SPECS)
    capabilities, capabilities_from = _catalog(working_dir)
    review_path = version_dir / ARTIFACT_CODE_REVIEW
    review_rel = review_path.relative_to(working_dir).as_posix()
    return {
        "version": version,
        "implemented": _implemented_at(version_dir),
        "artifacts_present": _present(version_dir),
        "phases": phases_extract(version_dir),
        "stack": None if stack is None else stack_extract(stack),
        "vision": None if vision is None else vision_extract(vision),
        "feature_specs": None if specs is None else feature_specs_extract(specs),
        "capabilities": capabilities,
        "capabilities_from_version": capabilities_from,
        "review": review_extract(review_path, review_rel),
    }
