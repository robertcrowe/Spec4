"""The ``dependencies`` block of the ``scan`` layer: what the manifests declare (1d).

Three manifest formats are parsed, and only for their dependency names and
version specifiers (D-SC1d-6): ``pyproject.toml`` (``[project].dependencies``
and every ``[project.optional-dependencies]`` group, as PEP 508 names),
``package.json`` (``dependencies`` and ``devDependencies``) and ``go.mod``
(``require``). Nothing else in a manifest is read — the block exists so that
``plan_drift`` can ask "was what the plan named ever declared?" and ``delta``
can say what was added, dropped or bumped between two scans without opening
``git`` (D-SC1d-5: scan to scan only). A manifest that does not parse is
left out, not failed on.

Names are stored as declared; folding (``Pydantic-AI`` / ``pydantic_ai``) is
``_drift``'s job, since it is the comparison that needs it.
"""

from __future__ import annotations

import json
import pathlib
import re
import tomllib
from typing import Any

from spec4.agents.code_scanner._scan import _read_text_safely

_MANIFEST_NAMES = frozenset({"pyproject.toml", "package.json", "go.mod"})
_MAX_MANIFESTS = 50
_MAX_MANIFEST_BYTES = 2_000_000

# A PEP 508 requirement starts with the distribution name; whatever follows
# (extras, specifiers, markers) is kept verbatim as the "spec".
_PEP508_NAME_RE = re.compile(
    r"^\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)\s*(.*)$"
)
_GO_REQUIRE_BLOCK_RE = re.compile(r"^require[ \t]*\(([^)]*)\)", re.M | re.S)
_GO_REQUIRE_LINE_RE = re.compile(r"^require[ \t]+(\S+)[ \t]+(\S+)", re.M)
_GO_ENTRY_RE = re.compile(r"^[ \t]*(\S+)[ \t]+(v\S+)", re.M)


def _rel(root: pathlib.Path, path: pathlib.Path) -> str:
    return path.relative_to(root).as_posix()


def _pyproject(text: str) -> dict[str, str] | None:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None
    project = data.get("project")
    if not isinstance(project, dict):
        return {}
    groups: list[Any] = [project.get("dependencies")]
    optional = project.get("optional-dependencies")
    if isinstance(optional, dict):
        groups.extend(optional.values())
    out: dict[str, str] = {}
    for group in groups:
        if not isinstance(group, list):
            continue
        for req in group:
            m = _PEP508_NAME_RE.match(req) if isinstance(req, str) else None
            if m:
                out.setdefault(m.group(1), m.group(2).strip())
    return out


def _package_json(text: str) -> dict[str, str] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    out: dict[str, str] = {}
    for key in ("dependencies", "devDependencies"):
        block = data.get(key)
        if isinstance(block, dict):
            for name, spec in block.items():
                out.setdefault(str(name), str(spec))
    return out


def _go_mod(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, version in _GO_REQUIRE_LINE_RE.findall(text):
        out.setdefault(name, version)
    for block in _GO_REQUIRE_BLOCK_RE.finditer(text):
        for name, version in _GO_ENTRY_RE.findall(block.group(1)):
            out.setdefault(name, version)
    return out


def parse_manifest(path: pathlib.Path) -> dict[str, str] | None:
    """``{name: spec}`` declared by one manifest; ``None`` if unreadable or unparseable.

    Dispatches on the file name. A manifest of another name is ``None`` too —
    the caller filters, this parses.
    """
    text = _read_text_safely(path, _MAX_MANIFEST_BYTES)
    if text is None:
        return None
    if path.name == "pyproject.toml":
        return _pyproject(text)
    if path.name == "package.json":
        return _package_json(text)
    if path.name == "go.mod":
        return _go_mod(text)
    return None


def dependencies_block(
    root: pathlib.Path, all_files: list[pathlib.Path]
) -> dict[str, Any]:
    """The ``dependencies`` block: every parseable manifest in the walk, by path.

    Walk order is the tree's; the first ``_MAX_MANIFESTS`` are kept and
    ``truncated`` says whether any were left out. A vendored tree's manifests
    never reach here — the walk already pruned ``node_modules`` and its kin.
    """
    files: dict[str, dict[str, str]] = {}
    truncated = False
    for path in all_files:
        if path.name not in _MANIFEST_NAMES:
            continue
        if len(files) >= _MAX_MANIFESTS:
            truncated = True
            break
        deps = parse_manifest(path)
        if deps is not None:
            files[_rel(root, path)] = deps
    return {"files": files, "truncated": truncated}
