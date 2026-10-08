"""CodeScanner v2 step 1c: ``module_graph`` and ``signatures``.

Covers ``code_scanner._graph`` — import resolution per language, the ranked
candidates and their bounds, the signature extractors and their budget — on
fixture trees, plus the two blocks' place in ``collect_scan`` and the schema.
"""

from __future__ import annotations

import pathlib
from typing import Any
from unittest.mock import patch

import pytest

from spec4.agents._code_review_schema import validate_code_review
from spec4.agents.code_scanner import _collect, _graph
from spec4.agents.code_scanner._scan import (
    SampleRecord,
    collect_files,
    gather_project_context,
)
from tests._review_helpers import review_envelope


def _write(root: pathlib.Path, rel: str, text: str = "") -> pathlib.Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _graph_of(root: pathlib.Path) -> dict[str, Any]:
    return _graph.module_graph_block(root, collect_files(root))


def _signatures_of(root: pathlib.Path) -> dict[str, Any]:
    files = collect_files(root)
    return _graph.signatures_block(root, files, _graph.module_graph_block(root, files))


def _consumers(graph: dict[str, Any], path: str) -> list[str]:
    for c in graph["load_bearing_candidates"]:
        if c["path"] == path:
            return list(c["consumers"])
    raise AssertionError(f"{path} is not a candidate")


# ---------------------------------------------------------------------------
# Python resolution
# ---------------------------------------------------------------------------


def _make_python_project(root: pathlib.Path) -> None:
    _write(root, "src/pkg/__init__.py", "from pkg.core import run\n")
    _write(
        root,
        "src/pkg/core.py",
        "import json\nimport requests\nfrom pkg import util\n"
        "from pkg.util import helper\n"
        "from . import sibling\nfrom .sibling import thing\n",
    )
    _write(root, "src/pkg/util.py", "from pkg import VERSION\n")
    _write(
        root, "src/pkg/sibling.py", "from ..outside import nothing\nimport pkg.core\n"
    )
    _write(root, "src/pkg/sub/__init__.py", "")
    _write(
        root, "src/pkg/sub/deep.py", "from ...pkg import util\nfrom .. import core\n"
    )
    _write(root, "src/pkg/broken.py", "def (:\n")
    _write(root, "src/pkg/test_core.py", "from pkg.core import run\n")
    _write(
        root, "tests/test_core.py", "from pkg.core import run\nfrom pkg import util\n"
    )


class TestPythonResolution:
    def test_submodule_wins_over_package_for_from_imports(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_python_project(tmp_path)
        graph = _graph_of(tmp_path)
        # `from pkg import util` -> util.py; `from pkg.util import helper` ->
        # util.py (helper is a name, not a module); `from pkg import VERSION`
        # -> the package itself.
        assert _consumers(graph, "src/pkg/util.py") == [
            "src/pkg/core.py",
            "src/pkg/sub/deep.py",
        ]
        assert graph["fan_in"]["src/pkg/__init__.py"] == 1
        assert graph["fan_out"]["src/pkg/util.py"] == 1

    def test_relative_imports_root_at_the_importer_package(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_python_project(tmp_path)
        graph = _graph_of(tmp_path)
        # `from . import sibling` and `from .sibling import thing` are one edge.
        assert graph["fan_in"]["src/pkg/sibling.py"] == 1
        assert graph["fan_out"]["src/pkg/core.py"] == 2
        assert _consumers(graph, "src/pkg/core.py") == [
            "src/pkg/__init__.py",
            "src/pkg/sibling.py",
            "src/pkg/sub/deep.py",
        ]

    def test_relative_import_beyond_the_tree_is_dropped(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_python_project(tmp_path)
        graph = _graph_of(tmp_path)
        # `from ..outside import nothing` in sibling.py climbs past `src/`:
        # no edge, and not an external name either (it is relative).
        assert "outside" not in graph["unresolved"]
        assert graph["fan_out"]["src/pkg/sibling.py"] == 1

    def test_stdlib_is_not_unresolved_but_third_party_is(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_python_project(tmp_path)
        graph = _graph_of(tmp_path)
        assert graph["unresolved"] == {"requests": 1}
        assert graph["unresolved_truncated"] is False

    def test_tests_are_outside_the_graph_on_both_ends(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_python_project(tmp_path)
        graph = _graph_of(tmp_path)
        assert graph["nodes"] == 7  # tests/ and the test_*.py beside the code
        assert not any(
            "tests/" in src
            for c in graph["load_bearing_candidates"]
            for src in c["consumers"]
        )
        assert all("tests/" not in p for p in graph["fan_out"])

    def test_unparseable_file_has_no_edges_and_no_signatures(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_python_project(tmp_path)
        graph = _graph_of(tmp_path)
        assert "src/pkg/broken.py" not in graph["fan_out"]
        assert _graph.file_signatures(tmp_path / "src/pkg/broken.py") is None

    def test_self_import_is_not_an_edge(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "solo.py", "import solo\nfrom solo import x\n")
        graph = _graph_of(tmp_path)
        assert graph["edges"] == 0
        assert graph["fan_in"] == {}
        assert graph["nodes"] == 1

    def test_relative_import_from_a_root_level_module_resolves_nothing(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(
            tmp_path,
            "top.py",
            "from . import other\nfrom .other import x\nfrom .. import above\n",
        )
        _write(tmp_path, "other.py", "")
        graph = _graph_of(tmp_path)
        # No package to be relative to: `_from_base` yields None for the bare
        # `from .` and for `from ..` (which climbs past the root), and
        # `other` for `from .other`.
        assert graph["edges"] == 1
        assert graph["fan_in"] == {"other.py": 1}


# ---------------------------------------------------------------------------
# JavaScript / TypeScript resolution
# ---------------------------------------------------------------------------


def _make_js_project(root: pathlib.Path) -> None:
    _write(
        root,
        "web/src/app.ts",
        "import React from 'react';\n"
        "import { a } from './lib/a';\n"
        "import b from './lib/b.js';\n"
        "import * as c from './lib/c';\n"
        'export { d } from "./lib/d";\n'
        "const e = require('./lib/e');\n"
        "const f = import('./lib/f');\n"
        "import '@scope/pkg/style.css';\n"
        "import { t } from './tests/helper';\n"
        "import missing from './lib/missing';\n",
    )
    _write(root, "web/src/lib/a.ts", "export const a = 1;\n")
    _write(root, "web/src/lib/b.ts", "export default 2;\n")
    _write(root, "web/src/lib/c/index.tsx", "export const c = 3;\n")
    _write(root, "web/src/lib/d.js", "export const d = 4;\n")
    _write(root, "web/src/lib/e.jsx", "module.exports = 5;\n")
    _write(root, "web/src/lib/f.ts", "export const f = 6;\n")
    _write(root, "web/src/tests/helper.ts", "export const t = 7;\n")
    _write(root, "web/src/app.spec.ts", "import { a } from './lib/a';\n")
    _write(root, "web/src/lib/a.test.tsx", "import { a } from './a';\n")


class TestJsResolution:
    def test_relative_specifiers_resolve_by_extension_and_index(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_js_project(tmp_path)
        graph = _graph_of(tmp_path)
        assert graph["languages"] == ["javascript", "typescript"]
        assert graph["fan_out"]["web/src/app.ts"] == 6
        assert set(graph["fan_in"]) == {
            "web/src/lib/a.ts",
            "web/src/lib/b.ts",
            "web/src/lib/c/index.tsx",
            "web/src/lib/d.js",
            "web/src/lib/e.jsx",
            "web/src/lib/f.ts",
        }

    def test_bare_specifiers_are_external_and_scoped_names_keep_their_scope(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_js_project(tmp_path)
        graph = _graph_of(tmp_path)
        assert graph["unresolved"] == {"@scope/pkg": 1, "react": 1}

    def test_import_of_a_test_file_or_a_missing_file_is_no_edge(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_js_project(tmp_path)
        graph = _graph_of(tmp_path)
        assert "web/src/tests/helper.ts" not in graph["fan_in"]
        assert graph["edges"] == 6
        assert graph["fan_in"]["web/src/lib/a.ts"] == 1
        assert graph["nodes"] == 7

    def test_relative_specifier_escaping_the_tree_is_no_edge(
        self, tmp_path: pathlib.Path
    ) -> None:
        project = tmp_path / "proj"
        _write(tmp_path, "outside.js", "export const o = 1;\n")
        _write(project, "main.js", "import { o } from '../outside.js';\n")
        graph = _graph_of(project)
        assert graph["edges"] == 0
        assert graph["nodes"] == 1


# ---------------------------------------------------------------------------
# Go resolution
# ---------------------------------------------------------------------------


def _make_go_project(root: pathlib.Path, *, go_mod: bool = True) -> None:
    if go_mod:
        _write(root, "go.mod", "module example.com/svc\n\ngo 1.22\n")
    _write(
        root,
        "main.go",
        'package main\n\nimport "fmt"\n\nimport (\n\t"example.com/svc/store"\n'
        '\tlog "github.com/rs/zerolog"\n)\n\nfunc main() {}\n',
    )
    _write(root, "store/store.go", 'package store\n\nimport "example.com/svc"\n')
    _write(root, "store/extra.go", "package store\n")
    _write(root, "store/store_test.go", 'package store\n\nimport "example.com/svc"\n')
    _write(root, "api/api.go", 'package api\n\nimport "example.com/svc/store"\n')


class TestGoResolution:
    def test_in_module_packages_resolve_to_every_file_in_the_directory(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_go_project(tmp_path)
        graph = _graph_of(tmp_path)
        assert graph["languages"] == ["go"]
        assert graph["fan_in"] == {
            "main.go": 1,
            "store/extra.go": 2,
            "store/store.go": 2,
        }
        assert graph["unresolved"] == {"fmt": 1, "github.com": 1}
        # store_test.go sits beside the code; it is a test by name, so its
        # import of the root package is not an edge.
        assert graph["nodes"] == 4

    def test_without_go_mod_every_import_is_external(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_go_project(tmp_path, go_mod=False)
        graph = _graph_of(tmp_path)
        assert graph["edges"] == 0
        assert graph["unresolved"]["example.com"] == 3

    def test_go_mod_without_a_module_line_is_no_module(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_go_project(tmp_path)
        (tmp_path / "go.mod").write_text("go 1.22\n")
        assert _graph_of(tmp_path)["edges"] == 0


# ---------------------------------------------------------------------------
# nodes, candidates, bounds
# ---------------------------------------------------------------------------


class TestGraphShape:
    def test_other_source_extensions_are_nodes_without_edges(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, "lib.rs", "use std::io;\n")
        _write(tmp_path, "Main.java", "import java.util.List;\n")
        _write(tmp_path, "notes.md", "# not source\n")
        graph = _graph_of(tmp_path)
        assert graph["nodes"] == 2
        assert graph["edges"] == 0
        assert graph["languages"] == []

    def test_candidates_need_fan_in_of_two_and_are_capped_at_top_k(
        self, tmp_path: pathlib.Path
    ) -> None:
        # Twelve modules with fan-in 2..13 and one with fan-in 1.
        for i in range(12):
            _write(tmp_path, f"m{i:02d}.py", "")
            for j in range(i + 2):
                _write(tmp_path, f"u{i:02d}_{j:02d}.py", f"import m{i:02d}\n")
        _write(tmp_path, "lonely.py", "")
        _write(tmp_path, "one.py", "import lonely\n")
        graph = _graph_of(tmp_path)
        candidates = graph["load_bearing_candidates"]
        assert len(candidates) == _graph._TOP_K
        assert [c["path"] for c in candidates[:2]] == ["m11.py", "m10.py"]
        assert candidates[0]["fan_in"] == 13
        assert candidates[0]["consumers"] == sorted(candidates[0]["consumers"])
        assert "lonely.py" not in {c["path"] for c in candidates}
        assert graph["fan_in"]["lonely.py"] == 1

    def test_ties_rank_by_path(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "b.py", "")
        _write(tmp_path, "a.py", "")
        _write(tmp_path, "x.py", "import a\nimport b\n")
        _write(tmp_path, "y.py", "import a\nimport b\n")
        graph = _graph_of(tmp_path)
        assert [c["path"] for c in graph["load_bearing_candidates"]] == ["a.py", "b.py"]

    def test_unresolved_is_capped_and_says_so(self, tmp_path: pathlib.Path) -> None:
        body = "".join(f"import thirdparty{i:03d}\n" for i in range(60))
        _write(tmp_path, "deps.py", body + "import thirdparty000\n")
        graph = _graph_of(tmp_path)
        assert len(graph["unresolved"]) == _graph._MAX_UNRESOLVED
        assert graph["unresolved_truncated"] is True
        assert graph["unresolved"]["thirdparty000"] == 2

    def test_unreadable_or_oversized_source_contributes_nothing(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, "big.py", "import os\n" * 10)
        _write(tmp_path, "ok.py", "import big\n")
        with patch.object(_graph, "_MAX_SOURCE_BYTES", 20):
            graph = _graph_of(tmp_path)
        assert graph["fan_in"] == {"big.py": 1}
        assert "big.py" not in graph["fan_out"]
        files = [tmp_path / "ok.py", tmp_path / "gone.py"]
        graph = _graph.module_graph_block(tmp_path, files)
        assert graph["nodes"] == 2
        assert graph["edges"] == 0
        assert _graph.file_signatures(tmp_path / "gone.py") is None


# ---------------------------------------------------------------------------
# signatures
# ---------------------------------------------------------------------------


_PY_MODULE = '''"""Module doc.

More.
"""

import os


class Base:
    pass


class Thing(Base, metaclass=type):
    """A thing.

    Second paragraph.
    """


def run(a: int, *args: str, b: bool = True, **kw: object) -> list[int]:
    """Run it."""
    return []


async def fetch(url):
    return url


def _private() -> None:
    pass


class _Hidden:
    pass
'''


class TestPythonSignatures:
    def test_public_symbols_with_first_doc_lines(self, tmp_path: pathlib.Path) -> None:
        path = _write(tmp_path, "mod.py", _PY_MODULE)
        entry = _graph.file_signatures(path)
        assert entry is not None
        assert entry["language"] == "python"
        assert entry["doc"] == "Module doc."
        assert entry["truncated"] is False
        assert entry["symbols"] == [
            {"kind": "class", "name": "Base", "signature": "class Base", "doc": None},
            {
                "kind": "class",
                "name": "Thing",
                "signature": "class Thing(Base)",
                "doc": "A thing.",
            },
            {
                "kind": "function",
                "name": "run",
                "signature": (
                    "def run(a: int, *args: str, b: bool=True, **kw: object)"
                    " -> list[int]"
                ),
                "doc": "Run it.",
            },
            {
                "kind": "function",
                "name": "fetch",
                "signature": "async def fetch(url)",
                "doc": None,
            },
        ]

    def test_public_assignments_are_variables_without_values(
        self, tmp_path: pathlib.Path
    ) -> None:
        # D-SC1d-7: the contract a consumer imports is the name and its
        # annotation; ``settings = get_settings()`` carries only its name.
        body = (
            "settings: Settings = get_settings()\n"
            "async_session_factory = make_factory()\n"
            "A, B = 1, 2\n"
            "[C, _d] = [3, 4]\n"
            "_private = 0\n"
            "__all__ = ['A']\n"
            "obj.attr = 1\n"
            "x: int\n"
            "def f():\n    inner = 1\n"
        )
        entry = _graph.file_signatures(_write(tmp_path, "vars.py", body))
        assert entry is not None
        assert [(s["kind"], s["name"], s["signature"]) for s in entry["symbols"]] == [
            ("variable", "settings", "settings: Settings"),
            ("variable", "async_session_factory", "async_session_factory"),
            ("variable", "A", "A"),
            ("variable", "B", "B"),
            ("variable", "C", "C"),
            ("variable", "x", "x: int"),
            ("function", "f", "def f()"),
        ]
        assert all(s["doc"] is None for s in entry["symbols"][:6])

    def test_symbols_per_file_are_capped(self, tmp_path: pathlib.Path) -> None:
        body = "".join(f"def f{i}():\n    pass\n\n" for i in range(45))
        entry = _graph.file_signatures(_write(tmp_path, "many.py", body))
        assert entry is not None
        assert len(entry["symbols"]) == _graph._MAX_SYMBOLS_PER_FILE
        assert entry["truncated"] is True

    def test_long_signature_is_cut(self, tmp_path: pathlib.Path) -> None:
        params = ", ".join(f"param_{i}: int" for i in range(40))
        entry = _graph.file_signatures(
            _write(tmp_path, "w.py", f"def f({params}): ...\n")
        )
        assert entry is not None
        assert len(entry["symbols"][0]["signature"]) == _graph._MAX_SIGNATURE_CHARS

    def test_first_line_skips_leading_blank_lines(self) -> None:
        assert _graph._first_line("\n\n  first  \nsecond") == "first"
        assert _graph._first_line("   \n ") is None
        assert _graph._first_line(None) is None

    def test_non_graph_language_has_no_signatures(self, tmp_path: pathlib.Path) -> None:
        assert (
            _graph.file_signatures(_write(tmp_path, "lib.rs", "pub fn x() {}\n"))
            is None
        )


_TS_MODULE = """import x from 'y';

/**
 * Starts the server.
 * @param port the port
 */
export async function start(port: number): Promise<void> {
}

// Handy constant.
export const LIMIT = 10;
export default class App extends Base {
}
/* one-liner */
export interface Options { a: string }
export type Id = string;
export enum Mode { A, B }
export function* gen() {}
function notExported() {}
export let counter = 0;
"""


class TestJsSignatures:
    def test_exports_with_doc_comments(self, tmp_path: pathlib.Path) -> None:
        entry = _graph.file_signatures(_write(tmp_path, "app.ts", _TS_MODULE))
        assert entry is not None
        assert entry["language"] == "typescript"
        assert entry["doc"] is None
        assert [
            (s["kind"], s["name"], s["signature"], s["doc"]) for s in entry["symbols"]
        ] == [
            (
                "function",
                "start",
                "export async function start(port: number): Promise<void>",
                "Starts the server.",
            ),
            ("const", "LIMIT", "export const LIMIT", "Handy constant."),
            ("class", "App", "export default class App extends Base", None),
            ("interface", "Options", "export interface Options", "one-liner"),
            ("type", "Id", "export type Id", None),
            ("enum", "Mode", "export enum Mode", None),
            ("function", "gen", "export function* gen()", None),
            ("const", "counter", "export let counter", None),
        ]

    def test_default_identifier_and_export_lists(self, tmp_path: pathlib.Path) -> None:
        # D-SC1d-7: the two forms 1c missed — ``App.tsx`` and ``main.tsx``
        # had 0 symbols on BWS4.
        body = (
            "import React from 'react';\n"
            "function App() { return null; }\n"
            "const helper = 1;\n"
            "type Props = {};\n"
            "// The root component.\n"
            "export default App;\n"
            "export { helper, App as Root };\n"
            "export type { Props };\n"
            "export {\n  helper as again,\n};\n"
            "export { x } from './x';\n"
            "export default function () {}\n"
            "export default async function () {}\n"
            "export default {};\n"
            "export default memo(App);\n"
            "export * from './y';\n"
        )
        entry = _graph.file_signatures(_write(tmp_path, "App.tsx", body))
        assert entry is not None
        assert [
            (s["kind"], s["name"], s["signature"], s["doc"]) for s in entry["symbols"]
        ] == [
            ("default", "App", "export default App", "The root component."),
            ("export", "helper", "export { helper }", None),
            ("export", "Root", "export { Root }", None),
            ("export", "Props", "export { Props }", None),
            ("export", "again", "export { again }", None),
            ("export", "x", "export { x }", None),
        ]

    def test_comment_block_with_only_markers_yields_no_doc(self) -> None:
        lines = ["/**", " */", "export const x = 1;"]
        assert _graph._comment_above(lines, 2, _graph._JS_COMMENT_MARKERS) is None
        assert _graph._comment_above(["export const x = 1;"], 0, ("//",)) is None


_GO_MODULE = """package svc

// Server serves.
type Server struct{}

// Start starts the server.
func (s *Server) Start(addr string) error {
\treturn nil
}

func helper() {}

type private struct{}

func New() *Server { return &Server{} }
"""


class TestGoSignatures:
    def test_exported_funcs_and_types_in_line_order(
        self, tmp_path: pathlib.Path
    ) -> None:
        entry = _graph.file_signatures(_write(tmp_path, "svc.go", _GO_MODULE))
        assert entry is not None
        assert entry["language"] == "go"
        assert [
            (s["kind"], s["name"], s["signature"], s["doc"]) for s in entry["symbols"]
        ] == [
            ("type", "Server", "type Server struct", "Server serves."),
            (
                "function",
                "Start",
                "func (s *Server) Start(addr string) error",
                "Start starts the server.",
            ),
            ("function", "New", "func New() *Server", None),
        ]


class TestSignaturesBlock:
    def test_candidates_then_entrypoints_without_repeats(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, "core.py", "def core(): ...\n")
        _write(tmp_path, "main.py", "import core\ndef main(): ...\n")
        _write(tmp_path, "other.py", "import core\nimport main\n")
        _write(tmp_path, "third.py", "import main\n")
        _write(tmp_path, "cli.py", "import os\n")
        _write(tmp_path, "tests/main.py", "def main(): ...\n")
        block = _signatures_of(tmp_path)
        assert list(block["files"]) == ["core.py", "main.py", "cli.py"]
        assert block["truncated"] is False
        assert block["files"]["main.py"]["symbols"][0]["name"] == "main"

    def test_budget_stops_before_overrunning_and_says_so(
        self, tmp_path: pathlib.Path
    ) -> None:
        for name in ("main", "app", "server"):
            _write(tmp_path, f"{name}.py", f"def {name}(): ...\n")
        with patch.object(_graph, "_MAX_SIGNATURES_BYTES", 300):
            block = _signatures_of(tmp_path)
        assert list(block["files"]) == ["app.py", "main.py"]
        assert block["truncated"] is True

    def test_unparseable_target_is_skipped_not_charged(
        self, tmp_path: pathlib.Path
    ) -> None:
        _write(tmp_path, "main.py", "def (:\n")
        _write(tmp_path, "app.py", "def app(): ...\n")
        block = _signatures_of(tmp_path)
        assert list(block["files"]) == ["app.py"]
        assert block["truncated"] is False


# ---------------------------------------------------------------------------
# assembly and schema
# ---------------------------------------------------------------------------


class TestAssembly:
    def test_collect_scan_carries_both_blocks_and_validates(
        self, tmp_path: pathlib.Path
    ) -> None:
        _make_python_project(tmp_path)
        files = collect_files(tmp_path)
        record = SampleRecord()
        gather_project_context(str(tmp_path), files, record)
        scan = _collect.collect_scan(str(tmp_path), files, record, None)
        assert scan["module_graph"]["edges"] == 7
        assert "src/pkg/core.py" in scan["signatures"]["files"]
        assert validate_code_review(review_envelope(scan=scan)) == []

    def test_empty_tree_has_empty_blocks(self, tmp_path: pathlib.Path) -> None:
        scan = _collect.collect_scan(str(tmp_path), [], SampleRecord(), None)
        assert scan["module_graph"] == {
            "languages": [],
            "nodes": 0,
            "edges": 0,
            "fan_in": {},
            "fan_out": {},
            "load_bearing_candidates": [],
            "unresolved": {},
            "unresolved_truncated": False,
        }
        assert scan["signatures"] == {"files": {}, "truncated": False}
        assert validate_code_review(review_envelope(scan=scan)) == []

    @pytest.mark.parametrize(
        ("block", "extra"),
        [
            ("module_graph", {"dormant": []}),
            ("signatures", {"bodies": {}}),
        ],
    )
    def test_blocks_are_closed(
        self, tmp_path: pathlib.Path, block: str, extra: dict[str, Any]
    ) -> None:
        scan = _collect.collect_scan(str(tmp_path), [], SampleRecord(), None)
        scan[block].update(extra)
        errors = validate_code_review(review_envelope(scan=scan))
        assert errors
        assert any(next(iter(extra)) in e for e in errors)

    def test_candidate_entries_are_closed(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "a.py", "")
        _write(tmp_path, "x.py", "import a\n")
        _write(tmp_path, "y.py", "import a\n")
        files = collect_files(tmp_path)
        scan = _collect.collect_scan(str(tmp_path), files, SampleRecord(), None)
        assert validate_code_review(review_envelope(scan=scan)) == []
        scan["module_graph"]["load_bearing_candidates"][0]["role"] = "hub"
        assert validate_code_review(review_envelope(scan=scan))
