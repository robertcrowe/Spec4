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

One exception to "never ``git``" since 2.10.0 (D-SC5-9): ``files.modified``
names the files listed by *both* scans whose content changed, and the only
witness to a content change is git — ``git diff --name-only <prior head>``
plus the working tree's modified files, computed by ``_collect`` and handed
in. Without it the delta named only files that came or went, so an edit to
``.env.example`` or ``main.py`` was invisible to the update seed's carry rule
(D-SC5-4). ``[]`` when there is no repository or git is unavailable.

Since 2.11.0 (D-SC5-13, D-SC5-14) the same candidate order also answers a
second question: which review on disk the *update seed* should paste and the
commit-time carry should merge against, when the session holds none — a new
brownfield round, where the previous round is implemented and ``v{N+1}`` has
no review yet. ``prior_envelope`` is that resolver, beside ``prior_scan`` and
through the same read, so the seed's prior and ``delta.prior`` are one choice.
"""

from __future__ import annotations

import json
import pathlib
from typing import TYPE_CHECKING, Any

from spec4 import project_manager
from spec4.agents._code_review_context import unwrap_scan
from spec4.app_constants import ARTIFACT_CODE_REVIEW

if TYPE_CHECKING:
    from collections.abc import Iterable

_MAX_LIST = 200
_KIND_IMPLEMENTED = "implemented"
_KIND_PRIOR_REVIEW = "prior_review"


def _capped(items: set[str]) -> tuple[list[str], bool]:
    ordered = sorted(items)
    return ordered[:_MAX_LIST], len(ordered) > _MAX_LIST


def _envelope_of(path: pathlib.Path) -> dict[str, Any] | None:
    """A review file parsed to a dict, else ``None`` (missing, unreadable, not a dict)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _scan_of(envelope: dict[str, Any] | None) -> dict[str, Any] | None:
    """An envelope's ``scan`` layer, when it is a measured 2.x one (``None`` in → ``None``)."""
    scan = unwrap_scan(envelope)
    return scan if isinstance(scan.get("inventory"), dict) else None


def _prior_candidates(
    working_dir: str, session: dict[str, Any] | None
) -> list[tuple[str, int, pathlib.Path]]:
    """The prior-review files to try, in precedence order (see the module docstring)."""
    kinds: list[tuple[str, int | None]] = [
        (_KIND_IMPLEMENTED, project_manager.latest_implemented_version(working_dir)),
        (_KIND_PRIOR_REVIEW, project_manager.active_version(working_dir, session)),
    ]
    return [
        (
            kind,
            version,
            project_manager.get_version_dir(working_dir, version)
            / ARTIFACT_CODE_REVIEW,
        )
        for kind, version in kinds
        if version is not None
    ]


def prior_envelope(
    working_dir: str, session: dict[str, Any] | None
) -> dict[str, Any] | None:
    """The prior review envelope on disk for a scan the session has no prior for (2.11.0, D-SC5-13).

    The first candidate, in ``prior_scan``'s order, whose file parses to a
    dict — whatever its schema: the caller decides between the update seed
    (a schema-2 ``review``), the fresh seed with the prior as context (an
    older schema, D-SV4) and nothing. ``prior_scan`` wants the first
    candidate with a *measured* scan instead, so the two can in principle
    differ (an implemented round under schema 1 beside an active round under
    schema 2); the session loads the active round's review whenever it
    parses, so a session with no review never reaches that case, and on the
    new-round path both resolve to the implemented round (D-SC5-14).
    """
    for _kind, _version, path in _prior_candidates(working_dir, session):
        envelope = _envelope_of(path)
        if envelope is not None:
            return envelope
    return None


def prior_scan(
    working_dir: str, session: dict[str, Any] | None
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """``(descriptor, scan)`` of the prior scan to diff against, or ``None``.

    The descriptor is the block's ``prior``: which round, by which precedence,
    the head the prior scan recorded (when it had a ``git`` block), and the
    prior scan's ``producer`` — the Spec4 version and schema that measured it
    (2.9.2, D-SC5-2), ``None`` for a scan from before the key existed. With
    it a reader can tell "the prior was measured by an older extractor" from
    a change in the tree: the 2.9.0 BWS4 scan's ``delta`` listed 43 "added"
    symbols on an unchanged tree because its 2.2.0 prior predated
    ``variable`` extraction, and nothing in the block said so.
    """
    for kind, version, path in _prior_candidates(working_dir, session):
        scan = _scan_of(_envelope_of(path))
        if scan is None:
            continue
        git = scan.get("git")
        head = git.get("head") if isinstance(git, dict) else None
        descriptor = {
            "kind": kind,
            "version": version,
            "head": head if isinstance(head, str) else None,
            "producer": _producer_of(scan),
        }
        return descriptor, scan
    return None


def _producer_of(scan: dict[str, Any]) -> dict[str, Any] | None:
    """The prior scan's ``producer`` when it carries a well-formed one."""
    producer = scan.get("producer")
    if (
        isinstance(producer, dict)
        and isinstance(producer.get("spec4"), str)
        and isinstance(producer.get("schema"), int)
    ):
        return {"spec4": producer["spec4"], "schema": producer["schema"]}
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


def _files(
    current: dict[str, Any],
    prior: dict[str, Any],
    modified: Iterable[str] | None,
) -> dict[str, Any]:
    """Added, removed and — from git — modified, over the two listings.

    ``modified`` is restricted to paths both scans list: a path only one
    lists is ``added`` or ``removed``, never both that and modified, so the
    three lists are disjoint and an untracked new file never counts as a
    modification.
    """
    now, now_partial = _listed(current)
    then, then_partial = _listed(prior)
    added, added_truncated = _capped(now - then)
    removed, removed_truncated = _capped(then - now)
    changed, changed_truncated = _capped(
        {p for p in (modified or ()) if isinstance(p, str)} & now & then
    )
    return {
        "added": added,
        "removed": removed,
        "modified": changed,
        "partial": now_partial or then_partial,
        "truncated": added_truncated or removed_truncated or changed_truncated,
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
    current: dict[str, Any],
    prior: dict[str, Any],
    descriptor: dict[str, Any],
    modified: Iterable[str] | None = None,
) -> dict[str, Any]:
    """The ``delta`` block of ``current`` against ``prior``; see the module docstring.

    ``modified`` is git's list of files whose content differs from the prior
    head (``_collect.modified_paths``), ``None`` when there is no repository.
    """
    return {
        "prior": dict(descriptor),
        "files": _files(current, prior, modified),
        "dependencies": _manifests(current, prior),
        "candidates": _candidates(current, prior),
        "signatures": _signatures(current, prior),
    }
