"""The ``plan_drift`` block of the ``scan`` layer: what the prior round planned
against what the tree declares (1d).

A deterministic classification, not a judgment (D-SC1d-4). The planned side
is the union of the prior stack's ``libraries`` and every prior phase's
``tech_stack_spec.dependencies``, each entry tagged with where it was named
(``stack``, ``phase:N``). The declared side is the ``dependencies`` block. Each
planned name lands in one bucket:

- ``planned_in_manifests`` — declared, under whatever spelling the manifest
  uses;
- ``planned_only_imported`` — never declared, but imported: it appears in
  ``module_graph.unresolved`` (a dependency the code reaches for that no
  manifest pins — a smell, which is why the bucket exists);
- ``planned_tooling`` (2.13.0, D-SC1d-11) — neither declared nor imported,
  but a file in the tree witnesses it as a runtime, a package manager, a
  piece of infrastructure or a configured tool: ``uv.lock`` for ``uv``, a
  ``*.service`` unit for ``systemd``, a ``Caddyfile``, ``package.json`` for
  ``Node`` — the names a manifest can never declare (``_tooling``);
- ``planned_unmatched`` — none of the three: a plan the code never followed,
  or a dropped one. Until 2.13.0 the tooling landed here too, and on BWS4's
  v8 round five of the six "planned, not found" entries StackAdvisor read
  were in daily use.

``declared_not_planned`` is the other direction: manifest entries no plan
named. The two sides spell names differently (StackAdvisor writes the
display name, Phaser the package name: ``PydanticAI`` and ``pydantic-ai``,
``Tailwind CSS`` and ``tailwindcss``), so matching goes through
``normalise``: lowercase, strip a trailing version token (``Python 3.12``),
fold every non-alphanumeric. The two scoped npm names that defeat the fold
(``@tanstack/react-query`` for ``TanStack Query``) match when the planned
name's word tokens are a subset of the scoped name's. No alias table: a miss
is reported, not papered over.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

_SOURCE_STACK = "stack"
_SOURCE_PHASE = "phase:{n}"
_MIN_SUBSET_TOKENS = 2
_MAX_ENTRIES = 500
_SCOPED_PREFIX = "@"

_TRAILING_VERSION_RE = re.compile(r"\s+v?\d+(?:\.\d+)*[a-z0-9.+-]*$")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _strip_version(name: str) -> str:
    return _TRAILING_VERSION_RE.sub("", name.lower().strip())


def normalise(name: str) -> str:
    """The comparison key of a dependency name; ``""`` for a name that is only noise."""
    return _NON_ALNUM_RE.sub("", _strip_version(name))


def tokens(name: str) -> frozenset[str]:
    """The word tokens of a name, for the scoped-name subset match."""
    return frozenset(_TOKEN_RE.findall(_strip_version(name)))


# ---------------------------------------------------------------------------
# the two sides
# ---------------------------------------------------------------------------


def _planned_names(prior: dict[str, Any]) -> Iterator[tuple[Any, str]]:
    """``(name, source)`` for every dependency the prior round's plan named."""
    stack = prior.get("stack")
    if isinstance(stack, dict):
        for lib in stack.get("libraries") or []:
            if isinstance(lib, dict):
                yield lib.get("name"), _SOURCE_STACK
    for phase in prior.get("phases") or []:
        if isinstance(phase, dict):
            source = _SOURCE_PHASE.format(n=phase.get("number"))
            for dep in phase.get("dependencies") or []:
                yield dep, source


def _planned(prior: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Planned names by key: the first spelling seen and every source that named it."""
    out: dict[str, dict[str, Any]] = {}
    for name, source in _planned_names(prior):
        key = normalise(name) if isinstance(name, str) else ""
        if not key:
            continue
        entry = out.setdefault(key, {"name": name, "sources": []})
        if source not in entry["sources"]:
            entry["sources"].append(source)
    return out


def _declared(dependencies: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Declared names by key: ``(spelling, manifest path)``, first manifest wins."""
    out: dict[str, tuple[str, str]] = {}
    files = dependencies.get("files")
    for path, deps in files.items() if isinstance(files, dict) else []:
        if not isinstance(deps, dict):
            continue
        for name in deps:
            key = normalise(str(name))
            if key:
                out.setdefault(key, (str(name), str(path)))
    return out


def _imported(graph: dict[str, Any]) -> dict[str, tuple[str, int]]:
    """Unresolved import names by key: ``(name, count)``."""
    out: dict[str, tuple[str, int]] = {}
    unresolved = graph.get("unresolved")
    for name, count in unresolved.items() if isinstance(unresolved, dict) else []:
        key = normalise(str(name))
        if key and isinstance(count, int):
            out.setdefault(key, (str(name), count))
    return out


def _subset_match(name: str, declared: dict[str, tuple[str, str]]) -> str | None:
    """The key of the scoped manifest name whose tokens contain all of ``name``'s."""
    wanted = tokens(name)
    if len(wanted) < _MIN_SUBSET_TOKENS:
        return None
    hits = [
        key
        for key, (spelling, _) in declared.items()
        if spelling.startswith(_SCOPED_PREFIX) and wanted <= tokens(spelling)
    ]
    return min(hits, key=lambda k: declared[k][0]) if hits else None


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------


def plan_drift_block(
    prior: dict[str, Any],
    dependencies: dict[str, Any],
    graph: dict[str, Any],
    witnesses: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """The ``plan_drift`` block; see the module docstring.

    ``witnesses`` is ``_tooling.tooling_witnesses``'s map — tooling key to
    the files that witness it — and decides ``planned_tooling``; ``None``
    (a caller from before 2.13.0) witnesses nothing, so every such name is
    unmatched as before. A planned name is tried against the manifests, then
    the imports, then the witnesses: a declared or imported tool is evidence
    of use in the code, a witness only of presence in the tree.
    """
    planned = _planned(prior)
    declared = _declared(dependencies)
    imported = _imported(graph)
    witnessed = witnesses or {}
    in_manifests: list[dict[str, Any]] = []
    only_imported: list[dict[str, Any]] = []
    tooling: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    matched_keys: set[str] = set()
    for key, entry in sorted(planned.items(), key=lambda kv: kv[1]["name"].lower()):
        hit = key if key in declared else _subset_match(entry["name"], declared)
        if hit is not None:
            spelling, path = declared[hit]
            matched_keys.add(hit)
            in_manifests.append({**entry, "declared_as": spelling, "manifest": path})
        elif key in imported:
            name, count = imported[key]
            only_imported.append({**entry, "imported_as": name, "imports": count})
        elif key in witnessed:
            tooling.append({**entry, "witnessed_by": list(witnessed[key])})
        else:
            unmatched.append(dict(entry))
    not_planned = [
        {"name": spelling, "manifest": path}
        for key, (spelling, path) in sorted(
            declared.items(), key=lambda kv: kv[1][0].lower()
        )
        if key not in matched_keys
    ]
    buckets = (in_manifests, only_imported, tooling, unmatched, not_planned)
    return {
        "prior_version": prior.get("version"),
        "planned": len(planned),
        "declared": len(declared),
        "planned_in_manifests": in_manifests[:_MAX_ENTRIES],
        "planned_only_imported": only_imported[:_MAX_ENTRIES],
        "planned_tooling": tooling[:_MAX_ENTRIES],
        "planned_unmatched": unmatched[:_MAX_ENTRIES],
        "declared_not_planned": not_planned[:_MAX_ENTRIES],
        "truncated": any(len(b) > _MAX_ENTRIES for b in buckets),
    }
