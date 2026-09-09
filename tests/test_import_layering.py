"""The layers of ``src/spec4`` may only be imported downward.

Phase 0's import-graph inventory (``CLEANUP_INVENTORY.md`` §6) found the source
tree already layered: the agent side — ``agents/``, ``agentifier/``,
``project_manager`` — is reachable from the Dash side and never the reverse,
``app`` is imported by nothing, and exactly one cycle exists
(``layouts`` ↔ ``layouts._chat``). §6.3 chose to guard that with a test rather
than install import-linter, because there were three boundaries worth stating
rather than a family of them.

Phase 4 splits the eight files over 1,300 lines, and a split is exactly the
operation that breaks a layer quietly. A helper moved into a new sibling reaches
for ``session``, because that is where its caller's data came from; or a new
sub-module imports the package that imports it back. Nothing fails: the code
still runs, the suite still passes, and the graph is one edge worse than it was.
This test is the thing that notices.

The walk is ``ast`` over the files rather than ``importlib`` over the modules.
That way it sees imports inside function bodies — §6.2 lists seven, and a lazy
import is precisely where an upward edge would hide — it needs nothing imported
in order to run, and it can read a module that would not import at all.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "spec4"

# The agent side. Nothing here may reach for anything in _DASH_SIDE below.
_AGENT_SIDE = ("spec4.agents", "spec4.agentifier", "spec4.project_manager")

# The Dash side: screens, callbacks, the app object, and the session/agent
# hinge that ties them together (§6.2).
_DASH_SIDE = ("spec4.layouts", "spec4.callbacks", "spec4.app", "spec4.session")

# Prefixes are matched as "the name itself, or the name plus a dot", so
# `spec4.app_constants` is not part of the `spec4.app` layer, and a module that
# becomes a package in a later sub-phase is still matched by its own name.
#
# Rule 4's scope. A callbacks sub-module must reach shared helpers through
# `spec4.callbacks._shared`, never through the package `__init__` that imports
# it for registration — the layouts/_chat cycle must not reappear one directory
# over. Phase 4g created the four private siblings the rule was written for;
# Phase 4h widened it from `spec4.callbacks._` to all of `spec4.callbacks.`,
# so the `designer` package and its own sub-modules are covered by it too.
_CALLBACKS_PRIVATE = "spec4.callbacks."


def _is_spec4(name: str) -> bool:
    return name == "spec4" or name.startswith("spec4.")


def _under(name: str, prefix: str) -> bool:
    """True when ``name`` is ``prefix`` itself or lives beneath it."""
    return name == prefix or name.startswith(prefix + ".")


def _module_name(path: pathlib.Path) -> str:
    parts = list(path.relative_to(_SRC.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _import_edges(
    module: str, tree: ast.Module, is_package: bool, known: frozenset[str]
) -> set[str]:
    """Every ``spec4`` module ``module`` imports, at any nesting depth.

    ``from spec4.x import y`` records an edge to ``spec4.x`` and, when
    ``spec4.x.y`` is itself a module, one to ``spec4.x.y`` as well — the same
    rule §6 of the inventory was built with. Relative imports are resolved
    against the importing module's own package.
    """
    package = module if is_package else module.rpartition(".")[0]
    edges: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            edges.update(a.name for a in node.names if _is_spec4(a.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package
                for _ in range(node.level - 1):
                    base = base.rpartition(".")[0]
                target = f"{base}.{node.module}" if node.module else base
            else:
                target = node.module or ""
            if not _is_spec4(target):
                continue
            edges.add(target)
            edges.update(
                f"{target}.{a.name}"
                for a in node.names
                if f"{target}.{a.name}" in known
            )
    return edges


@pytest.fixture(scope="module")
def graph() -> dict[str, set[str]]:
    """``{module: {the spec4 modules it imports}}`` for all of ``src/spec4``."""
    assert _SRC.is_dir(), f"source tree not found at {_SRC}"
    paths = {
        _module_name(p): p
        for p in sorted(_SRC.rglob("*.py"))
        if "__pycache__" not in p.parts
    }
    known = frozenset(paths)
    return {
        name: _import_edges(
            name,
            ast.parse(path.read_text(encoding="utf-8")),
            path.name == "__init__.py",
            known,
        )
        for name, path in paths.items()
    }


def _crossings(
    graph: dict[str, set[str]],
    importers: tuple[str, ...],
    imported: tuple[str, ...],
) -> list[tuple[str, str]]:
    return sorted(
        (src, dst)
        for src, targets in graph.items()
        if any(_under(src, p) for p in importers)
        for dst in targets
        if any(_under(dst, p) for p in imported)
    )


def _report(pairs: list[tuple[str, str]]) -> str:
    return "\n".join(f"  {src} -> {dst}" for src, dst in pairs)


class TestTheWalkItself:
    """A contract test that silently stops seeing edges guards nothing."""

    def test_it_finds_the_whole_source_tree(self, graph: dict[str, set[str]]) -> None:
        assert len(graph) >= 55, f"only {len(graph)} modules walked"
        assert [m for m in graph if any(_under(m, p) for p in _AGENT_SIDE)]
        assert [m for m in graph if any(_under(m, p) for p in _DASH_SIDE)]

    def test_it_sees_a_top_level_import(self, graph: dict[str, set[str]]) -> None:
        # app.py imports the callback modules at module scope (D-LR1 ordering).
        assert "spec4.callbacks" in graph["spec4.app"]

    def test_it_sees_a_function_body_import(self, graph: dict[str, set[str]]) -> None:
        # session imports the Agentifier orchestrator lazily, inside a function.
        # If this stops being seen, the walk has gone shallow and every rule
        # below is passing for the wrong reason.
        assert "spec4.agentifier.agentifier" in graph["spec4.session"]


class TestTheLayeringContract:
    def test_the_agent_side_never_imports_the_dash_side(
        self, graph: dict[str, set[str]]
    ) -> None:
        crossings = _crossings(graph, _AGENT_SIDE, _DASH_SIDE)
        assert not crossings, (
            "agents/agentifier/project_manager must not import the Dash layer "
            "(layouts, callbacks, app, session):\n" + _report(crossings)
        )

    def test_nothing_imports_app(self, graph: dict[str, set[str]]) -> None:
        crossings = _crossings(graph, ("spec4",), ("spec4.app",))
        assert not crossings, (
            "spec4.app is the top of the graph and is imported by nothing in "
            "src/ — it is reached through the spec4 console script:\n"
            + _report(crossings)
        )

    def test_layouts_never_imports_callbacks(self, graph: dict[str, set[str]]) -> None:
        crossings = _crossings(graph, ("spec4.layouts",), ("spec4.callbacks",))
        assert not crossings, (
            "layouts render; callbacks import layouts, never the reverse:\n"
            + _report(crossings)
        )

    def test_a_private_callback_module_never_imports_its_package(
        self, graph: dict[str, set[str]]
    ) -> None:
        crossings = sorted(
            (src, dst)
            for src, targets in graph.items()
            if src.startswith(_CALLBACKS_PRIVATE)
            for dst in targets
            if dst == "spec4.callbacks"
        )
        assert not crossings, (
            "a private callbacks sub-module takes shared helpers from "
            "spec4.callbacks._shared, not from the package that imports it:\n"
            + _report(crossings)
        )
