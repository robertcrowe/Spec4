"""The ``delta`` block of the ``scan`` layer: this scan against the prior one (1d).

``delta`` compares ``scan`` to ``scan`` and nothing else (D-SC1d-5): the
prior is the computed layer of an earlier ``code_review.json``, never the
model's ``review`` and never ``git`` — a tree with no repository, or one
whose history was rewritten, gets the same answer. The prior scan comes from
the latest implemented round's review when that review carries a 2.x
``scan``, else from the active round's prior review (the file this scan will
replace), else there is no block: the same precedence ``round_boundary``
uses for ``git.since_last_round``, so the two agree on what "since" means.

Four comparisons, each over what both scans measured: paths in
``inventory.listed`` (``partial`` when either side's listing was capped),
dependencies per manifest in both ``dependencies`` blocks (added, removed,
bumped — a changed specifier), the ``load_bearing_candidates`` that entered
or left, and the public symbols of files in both ``signatures`` blocks,
keyed by name and ``changed`` when the signature text differs. Lists are
capped and say so. A scan identical to its prior yields a present, empty
block — "nothing changed" is a measurement, "absent" means there was nothing
to compare against.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from spec4 import project_manager
from spec4.agents._code_review_context import unwrap_scan
from spec4.app_constants import ARTIFACT_CODE_REVIEW

_MAX_LIST = 200
_KIND_IMPLEMENTED = "implemented"
_KIND_PRIOR_REVIEW = "prior_review"


def _capped(items: set[str]) -> tuple[list[str], bool]:
    ordered = sorted(items)
    return ordered[:_MAX_LIST], len(ordered) > _MAX_LIST


def _scan_of(path: pathlib.Path) -> dict[str, Any] | None:
    """A review file's ``scan`` layer, when it is a measured 2.x one."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    scan = unwrap_scan(data)
    return scan if isinstance(scan.get("inventory"), dict) else None


def prior_scan(
    working_dir: str, session: dict[str, Any] | None
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """``(descriptor, scan)`` of the prior scan to diff against, or ``None``.

    The descriptor is the block's ``prior``: which round, by which precedence,
    and the head the prior scan recorded (when it had a ``git`` block).
    """
    candidates: list[tuple[str, int | None]] = [
        (_KIND_IMPLEMENTED, project_manager.latest_implemented_version(working_dir)),
        (_KIND_PRIOR_REVIEW, project_manager.active_version(working_dir, session)),
    ]
    for kind, version in candidates:
        if version is None:
            continue
        path = (
            project_manager.get_version_dir(working_dir, version) / ARTIFACT_CODE_REVIEW
        )
        scan = _scan_of(path)
        if scan is None:
            continue
        git = scan.get("git")
        head = git.get("head") if isinstance(git, dict) else None
        descriptor = {
            "kind": kind,
            "version": version,
            "head": head if isinstance(head, str) else None,
        }
        return descriptor, scan
    return None


# ---------------------------------------------------------------------------
# the four comparisons
# ---------------------------------------------------------------------------


def _listed(scan: dict[str, Any]) -> tuple[set[str], bool]:
    inventory = scan.get("inventory")
    if not isinstance(inventory, dict):
        return set(), True
    listed = inventory.get("listed")
    paths = (
        {p for p in listed if isinstance(p, str)} if isinstance(listed, list) else set()
    )
    return paths, bool(inventory.get("truncated"))


def _files(current: dict[str, Any], prior: dict[str, Any]) -> dict[str, Any]:
    now, now_partial = _listed(current)
    then, then_partial = _listed(prior)
    added, added_truncated = _capped(now - then)
    removed, removed_truncated = _capped(then - now)
    return {
        "added": added,
        "removed": removed,
        "partial": now_partial or then_partial,
        "truncated": added_truncated or removed_truncated,
    }


def _manifest_files(scan: dict[str, Any]) -> dict[str, dict[str, str]]:
    block = scan.get("dependencies")
    files = block.get("files") if isinstance(block, dict) else None
    return {
        str(path): {str(k): str(v) for k, v in deps.items()}
        for path, deps in (files.items() if isinstance(files, dict) else [])
        if isinstance(deps, dict)
    }


def _manifests(current: dict[str, Any], prior: dict[str, Any]) -> dict[str, Any]:
    now = _manifest_files(current)
    then = _manifest_files(prior)
    out: dict[str, Any] = {}
    for path in sorted(now.keys() & then.keys()):
        added, a_t = _capped(now[path].keys() - then[path].keys())
        removed, r_t = _capped(then[path].keys() - now[path].keys())
        bumped, b_t = _capped(
            {
                n
                for n in now[path].keys() & then[path].keys()
                if now[path][n] != then[path][n]
            }
        )
        out[path] = {
            "added": added,
            "removed": removed,
            "bumped": bumped,
            "truncated": a_t or r_t or b_t,
        }
    return out


def _candidate_paths(scan: dict[str, Any]) -> set[str]:
    graph = scan.get("module_graph")
    ranked = graph.get("load_bearing_candidates") if isinstance(graph, dict) else None
    return {
        c["path"]
        for c in (ranked if isinstance(ranked, list) else [])
        if isinstance(c, dict) and isinstance(c.get("path"), str)
    }


def _candidates(current: dict[str, Any], prior: dict[str, Any]) -> dict[str, Any]:
    now = _candidate_paths(current)
    then = _candidate_paths(prior)
    return {"entered": sorted(now - then), "left": sorted(then - now)}


def _symbols(scan: dict[str, Any]) -> dict[str, dict[str, str]]:
    """``{path: {symbol name: signature}}`` of a scan's ``signatures`` block."""
    block = scan.get("signatures")
    files = block.get("files") if isinstance(block, dict) else None
    out: dict[str, dict[str, str]] = {}
    for path, entry in files.items() if isinstance(files, dict) else []:
        symbols = entry.get("symbols") if isinstance(entry, dict) else None
        names: dict[str, str] = {}
        for s in symbols if isinstance(symbols, list) else []:
            if isinstance(s, dict) and isinstance(s.get("name"), str):
                names.setdefault(s["name"], str(s.get("signature", "")))
        out[str(path)] = names
    return out


def _signatures(current: dict[str, Any], prior: dict[str, Any]) -> dict[str, Any]:
    now = _symbols(current)
    then = _symbols(prior)
    out: dict[str, Any] = {}
    for path in sorted(now.keys() & then.keys()):
        added, a_t = _capped(now[path].keys() - then[path].keys())
        removed, r_t = _capped(then[path].keys() - now[path].keys())
        changed, c_t = _capped(
            {
                n
                for n in now[path].keys() & then[path].keys()
                if now[path][n] != then[path][n]
            }
        )
        out[path] = {
            "added": added,
            "removed": removed,
            "changed": changed,
            "truncated": a_t or r_t or c_t,
        }
    return out


def delta_block(
    current: dict[str, Any], prior: dict[str, Any], descriptor: dict[str, Any]
) -> dict[str, Any]:
    """The ``delta`` block of ``current`` against ``prior``; see the module docstring."""
    return {
        "prior": dict(descriptor),
        "files": _files(current, prior),
        "dependencies": _manifests(current, prior),
        "candidates": _candidates(current, prior),
        "signatures": _signatures(current, prior),
    }
