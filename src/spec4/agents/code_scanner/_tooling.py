"""Tooling the tree witnesses without a manifest declaring it (2.13.0, D-SC1d-11).

``plan_drift`` matches what the prior round planned against what the
manifests declare, and a runtime, a package manager or a piece of
infrastructure can never be declared there: on BWS4's v8 round ``Caddy 2``,
``Node 20``, ``Python 3.12``, ``systemd`` and ``uv`` all landed in
``planned_unmatched`` beside ``Playwright`` — the one planned name nothing in
the tree supported — and StackAdvisor's "planned, not found" block carried
five false positives of a kind 2.7.1's dependency-group fix did not reach.

This module answers "does the tree witness it?" for a planned name, by two
deterministic signals and nothing else:

- a **file** whose name (or path, for the workflow directory) is the tool's
  own — ``uv.lock``, a ``*.service`` unit, a ``Caddyfile``, ``Dockerfile``,
  ``playwright.config.ts``, ``.github/workflows/*.yml`` — over the walked
  tree, so a vendored copy under ``node_modules`` or ``.venv`` never counts;
- a **manifest table** that names the tool without depending on it:
  ``pyproject.toml``'s ``[tool.<name>]`` tables, ``requires-python`` and
  ``[build-system].requires``; ``package.json``'s ``engines`` keys and
  ``packageManager``; one line per tool in an asdf ``.tool-versions``.

A witness is a presence test, not a version check (D-SC1d-4: classification,
not judgment): ``Python 3.12`` planned and ``.python-version`` saying 3.11 is
witnessed, and the review's ``runtime_versions`` is where the version lives.
The table is keyed by ``_drift.normalise`` of the tool's common spellings;
no alias beyond spelling (``Node`` / ``Node.js``, ``Go`` / ``Golang``). A
planned name that no row names is not witnessed, however present it may be —
a miss is reported, not papered over, as everywhere in ``plan_drift``.
"""

from __future__ import annotations

import fnmatch
import json
import pathlib
import tomllib
from typing import TYPE_CHECKING, Any

from spec4.agents.code_scanner._drift import normalise
from spec4.agents.code_scanner._scan import _read_text_safely

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

_MAX_WITNESSES = 3
_MAX_MANIFESTS = 50
_MAX_MANIFEST_BYTES = 2_000_000
_TOOL_VERSIONS = ".tool-versions"

# (the tool's spellings, the file patterns that witness it). A pattern with a
# ``/`` is matched against the whole relative path, any other against the file
# name; both case-sensitively, since ``Caddyfile`` and ``Makefile`` are names.
# Rows are checked in order and every row that matches a path contributes, so
# ``uv.lock`` witnesses both ``uv`` and ``python``.
_FILE_WITNESSES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("python", "python3", "cpython"),
        (
            "pyproject.toml",
            ".python-version",
            "requirements*.txt",
            "setup.py",
            "setup.cfg",
            "Pipfile",
            "uv.lock",
            "poetry.lock",
        ),
    ),
    (("uv",), ("uv.lock",)),
    (("poetry",), ("poetry.lock",)),
    (("pipenv",), ("Pipfile", "Pipfile.lock")),
    (("pip",), ("requirements*.txt",)),
    (("node", "nodejs", "node.js"), ("package.json", ".nvmrc", ".node-version")),
    (("npm",), ("package-lock.json",)),
    (("pnpm",), ("pnpm-lock.yaml",)),
    (("yarn",), ("yarn.lock",)),
    (("bun",), ("bun.lockb", "bun.lock")),
    (("go", "golang"), ("go.mod",)),
    (("rust", "cargo"), ("Cargo.toml",)),
    (("systemd",), ("*.service", "*.timer", "*.socket")),
    (("caddy",), ("Caddyfile",)),
    (("nginx",), ("nginx.conf", "*.nginx", "*.nginx.conf")),
    (
        ("docker",),
        (
            "Dockerfile",
            "Dockerfile.*",
            "*.dockerfile",
            ".dockerignore",
            "docker-compose*.yml",
            "docker-compose*.yaml",
            "compose.yml",
            "compose.yaml",
        ),
    ),
    (
        ("docker compose", "docker-compose", "compose"),
        ("docker-compose*.yml", "docker-compose*.yaml", "compose.yml", "compose.yaml"),
    ),
    (("github actions",), (".github/workflows/*.yml", ".github/workflows/*.yaml")),
    (("make", "gnu make", "gnumake"), ("Makefile", "makefile", "GNUmakefile")),
    (("terraform",), ("*.tf",)),
    (("ansible",), ("ansible.cfg",)),
    (("helm",), ("Chart.yaml",)),
    (("typescript",), ("tsconfig.json", "tsconfig.*.json")),
    (("vite",), ("vite.config.*",)),
    (("vitest",), ("vitest.config.*", "vitest.workspace.*")),
    (("playwright",), ("playwright.config.*",)),
    (("jest",), ("jest.config.*",)),
    (("tailwind", "tailwindcss", "tailwind css"), ("tailwind.config.*",)),
    (("postcss",), ("postcss.config.*",)),
    (("eslint",), (".eslintrc", ".eslintrc.*", "eslint.config.*")),
    (("oxlint",), (".oxlintrc", ".oxlintrc.*")),
    (("prettier",), (".prettierrc", ".prettierrc.*", "prettier.config.*")),
    (("ruff",), ("ruff.toml", ".ruff.toml")),
    (("mypy",), ("mypy.ini", ".mypy.ini")),
    (("pytest",), ("pytest.ini", "conftest.py")),
    (("tox",), ("tox.ini",)),
    (("pre-commit",), (".pre-commit-config.yaml",)),
    (("alembic",), ("alembic.ini",)),
)

_WITNESS_KEYS: tuple[tuple[frozenset[str], tuple[str, ...]], ...] = tuple(
    (frozenset(normalise(s) for s in spellings), patterns)
    for spellings, patterns in _FILE_WITNESSES
)


def _file_witness_keys(rel: str) -> Iterator[str]:
    """Every tooling key a relative path witnesses by its name."""
    name = rel.rsplit("/", 1)[-1]
    for keys, patterns in _WITNESS_KEYS:
        if any(fnmatch.fnmatchcase(rel if "/" in p else name, p) for p in patterns):
            yield from keys


def _requirement_name(req: Any) -> str:
    """The distribution name of a PEP 508 requirement string, else ``""``."""
    if not isinstance(req, str):
        return ""
    head = req.strip()
    for stop in " <>=!~;[(":
        head = head.split(stop, 1)[0]
    return head


def _pyproject_keys(text: str) -> Iterator[tuple[str, str]]:
    """``(key, label)`` for the tools a ``pyproject.toml`` names without depending on them."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return
    tool = data.get("tool")
    for name in tool if isinstance(tool, dict) else {}:
        yield normalise(str(name)), f"[tool.{name}]"
    project = data.get("project")
    if isinstance(project, dict) and isinstance(project.get("requires-python"), str):
        yield "python", "requires-python"
    build = data.get("build-system")
    requires = build.get("requires") if isinstance(build, dict) else None
    for req in requires if isinstance(requires, list) else []:
        key = normalise(_requirement_name(req))
        if key:
            yield key, "[build-system].requires"


def _package_json_keys(text: str) -> Iterator[tuple[str, str]]:
    """``(key, label)`` for ``engines`` and ``packageManager`` in a ``package.json``."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict):
        return
    engines = data.get("engines")
    for name in engines if isinstance(engines, dict) else {}:
        yield normalise(str(name)), f"engines.{name}"
    manager = data.get("packageManager")
    if isinstance(manager, str) and manager.strip():
        yield normalise(manager.split("@", 1)[0]), "packageManager"


def _tool_versions_keys(text: str) -> Iterator[tuple[str, str]]:
    """``(key, label)`` per tool line of an asdf ``.tool-versions``."""
    for line in text.splitlines():
        head = line.split("#", 1)[0].split()
        if head:
            yield normalise(head[0]), head[0]


_MANIFEST_READERS = {
    "pyproject.toml": _pyproject_keys,
    "package.json": _package_json_keys,
    _TOOL_VERSIONS: _tool_versions_keys,
}


def tooling_witnesses(
    root: pathlib.Path, all_files: Iterable[pathlib.Path]
) -> dict[str, list[str]]:
    """``{tooling key: [witness, ...]}`` over the walked tree; see the module docstring.

    A witness is the relative path of the file whose name is the tool's own,
    or ``"<manifest path> <table>"`` for a manifest that names it. At most
    ``_MAX_WITNESSES`` per key, in walk order, so the stored entry stays
    small; the first ``_MAX_MANIFESTS`` manifests are opened. A key with no
    witness is absent.
    """
    out: dict[str, list[str]] = {}

    def add(key: str, witness: str) -> None:
        if key:
            seen = out.setdefault(key, [])
            if len(seen) < _MAX_WITNESSES and witness not in seen:
                seen.append(witness)

    opened = 0
    for path in all_files:
        rel = path.relative_to(root).as_posix()
        for key in _file_witness_keys(rel):
            add(key, rel)
        reader = _MANIFEST_READERS.get(path.name)
        if reader is None or opened >= _MAX_MANIFESTS:
            continue
        opened += 1
        text = _read_text_safely(path, _MAX_MANIFEST_BYTES)
        for key, label in reader(text) if text is not None else []:
            add(key, f"{rel} {label}")
    return out
