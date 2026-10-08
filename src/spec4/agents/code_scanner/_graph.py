"""The ``module_graph`` and ``signatures`` blocks of the ``scan`` layer (1c).

Both are computed over the same walk ``_collect`` measures and stashed with
it; neither is LLM-visible. They exist for the steps that follow: step 2's
sampling draws on ``load_bearing_candidates``, and step 3's ``load_bearing``
judgment reads a candidate's ``consumers`` and its signatures.

- ``module_graph`` — import edges between the project's own source files,
  resolved for Python, JavaScript/TypeScript and Go (D-SC1c-5/6); the other
  ``_SOURCE_EXTENSIONS`` are nodes without edges. Test files are outside the
  graph on both ends (D-SC1c-4): a test helper with thirteen importers is not
  load-bearing. The edge list itself is not stored (D-SC1c-2) — per-node
  fan-in and fan-out counts are, and the consumers of the top-``_TOP_K``
  candidates, which is the part step 3 asked for. Imports that resolve to
  nothing in the tree are counted by top-level name in ``unresolved``
  (D-SC1c-7): third-party and, for Python, non-stdlib names only.
- ``signatures`` — the public top-level symbols of the candidates and the
  entrypoint candidates, with the first line of each docstring. Python goes
  through ``ast`` (which also yields its edges: one parse, two products); the
  other two through line regexes. The first ``scan`` block whose size follows
  the code rather than the file count, so it has a hard budget (D-SC1c-8)
  and says when it hit it.

A file Python cannot parse contributes no edges and no signatures and never
fails the scan.
"""

from __future__ import annotations

import ast
import collections
import json
import pathlib
import re
import sys
from typing import TYPE_CHECKING, Any

from spec4.agents.code_scanner._scan import (
    _SOURCE_EXTENSIONS,
    _is_entrypoint_candidate,
    _is_test_path,
    _read_text_safely,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
}
_JS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx")
_TEST_FILE_SUFFIXES = (
    "_test.go",
    *(f".{infix}{s}" for infix in ("test", "spec") for s in _JS_SUFFIXES),
)
_TOP_K = 10
_MIN_FAN_IN = 2
_MAX_UNRESOLVED = 50
_MAX_SYMBOLS_PER_FILE = 40
_MAX_SIGNATURES_BYTES = 32_000
_MAX_SIGNATURE_CHARS = 200
_MAX_SOURCE_BYTES = 2_000_000
_PRIVATE_PREFIX = "_"
_ROOT_DIR = "."

_JS_IMPORT_RE = re.compile(
    r"""(?:^[ \t]*(?:import|export)\b[^'"\n]*?\bfrom[ \t]*|^[ \t]*import[ \t]*)"""
    r"""['"]([^'"\n]+)['"]"""
    r"""|\brequire\([ \t]*['"]([^'"\n]+)['"][ \t]*\)"""
    r"""|\bimport\([ \t]*['"]([^'"\n]+)['"][ \t]*\)""",
    re.M,
)
_JS_EXPORT_RE = re.compile(
    r"^[ \t]*export[ \t]+(?:default[ \t]+)?(?:async[ \t]+)?"
    r"(function\*?|class|const|let|var|interface|type|enum)[ \t]+(\w+)",
    re.M,
)
# 1d (D-SC1d-7): the two export forms 1c missed — ``export default App`` (a
# bare identifier, which is how a React entry file exports its component) and
# the re-export list ``export { a, b as c }``. A ``default`` whose identifier
# is itself a keyword (``export default function () {}``) is anonymous and
# stays unlisted: the trailing anchor refuses the parameter list.
_JS_DEFAULT_IDENT_RE = re.compile(
    r"^[ \t]*export[ \t]+default[ \t]+(\w+)[ \t]*;?[ \t]*$", re.M
)
_JS_EXPORT_LIST_RE = re.compile(r"^[ \t]*export[ \t]*(?:type[ \t]+)?\{([^}]*)\}", re.M)
_JS_EXPORT_ITEM_RE = re.compile(r"^(?:type[ \t]+)?(\w+)(?:[ \t]+as[ \t]+(\w+))?$")
_JS_COMMENT_MARKERS = ("//", "/*", "*")
_GO_IMPORT_BLOCK_RE = re.compile(r"^import[ \t]*\(([^)]*)\)", re.M | re.S)
_GO_IMPORT_LINE_RE = re.compile(r'^import[ \t]+(?:\w+[ \t]+)?"([^"\n]+)"', re.M)
_GO_IMPORT_PATH_RE = re.compile(r'"([^"\n]+)"')
_GO_FUNC_RE = re.compile(r"^func[ \t]+(?:\([^)]*\)[ \t]*)?([A-Z]\w*)[ \t]*\(", re.M)
_GO_TYPE_RE = re.compile(r"^type[ \t]+([A-Z]\w*)[ \t]+", re.M)
_GO_COMMENT_MARKERS = ("//",)
_GO_MODULE_RE = re.compile(r"^module[ \t]+(\S+)", re.M)


def _rel(root: pathlib.Path, path: pathlib.Path) -> str:
    return path.relative_to(root).as_posix()


def _source_text(path: pathlib.Path) -> str | None:
    """A source file's text, or ``None`` when unreadable or implausibly large."""
    try:
        if path.stat().st_size > _MAX_SOURCE_BYTES:
            return None
    except OSError:
        return None
    return _read_text_safely(path, _MAX_SOURCE_BYTES)


# ---------------------------------------------------------------------------
# resolution
# ---------------------------------------------------------------------------


class _Index:
    """Where the tree's own modules live, for resolving imports to files."""

    def __init__(self, root: pathlib.Path, nodes: list[pathlib.Path]) -> None:
        self.root = root
        self.nodes = nodes
        self.rel = {n: _rel(root, n) for n in nodes}
        self.node_set = set(self.rel.values())
        # Every path suffix of a module is registered, so ``spec4.agents.x``
        # resolves whether the package sits at the root or under ``src/``
        # (D-SC1c-5). Deeper paths register first, so a short name that is
        # both a top-level module and a suffix elsewhere keeps the fuller
        # registration only when nothing shorter claims it. Packages map to
        # their ``__init__``.
        self.python: dict[str, str] = {}
        for n in sorted(nodes, key=lambda p: (-len(p.parts), p)):
            if n.suffix != ".py":
                continue
            parts = list(n.relative_to(root).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            for i in range(len(parts)):
                self.python.setdefault(".".join(parts[i:]), self.rel[n])
        self.go_module = self._go_module()
        self.go_dirs: dict[str, list[str]] = collections.defaultdict(list)
        for n in nodes:
            if n.suffix == ".go":
                key = _ROOT_DIR if n.parent == root else _rel(root, n.parent)
                self.go_dirs[key].append(self.rel[n])

    def _go_module(self) -> str | None:
        text = _read_text_safely(self.root / "go.mod", _MAX_SOURCE_BYTES)
        if text is None:
            return None
        m = _GO_MODULE_RE.search(text)
        return m.group(1) if m else None

    def resolve_python(self, dotted: str) -> str | None:
        """The file for a dotted name, by its longest registered prefix."""
        segs = dotted.split(".")
        for j in range(len(segs), 0, -1):
            hit = self.python.get(".".join(segs[:j]))
            if hit is not None:
                return hit
        return None

    def resolve_js(self, importer: pathlib.Path, spec: str) -> str | None:
        """A relative specifier, with the usual extension and index probing."""
        target = importer.parent / spec
        candidates = [target]
        # ESM-style TypeScript imports name the emitted ``.js``; the source
        # sits beside it under another suffix.
        if target.suffix in {".js", ".jsx"}:
            candidates.extend(target.with_suffix(s) for s in _JS_SUFFIXES)
        candidates.extend(target.with_name(target.name + s) for s in _JS_SUFFIXES)
        candidates.extend(target / f"index{s}" for s in _JS_SUFFIXES)
        for c in candidates:
            if not c.is_file():
                continue
            try:
                rel = _rel(self.root.resolve(), c.resolve())
            except ValueError:  # ``../`` out of the tree
                return None
            return rel if rel in self.node_set else None
        return None

    def resolve_go(self, import_path: str) -> list[str]:
        """The files of an in-module package; empty for anything else."""
        if self.go_module is None:
            return []
        if import_path == self.go_module:
            return list(self.go_dirs.get(_ROOT_DIR, []))
        prefix = self.go_module + "/"
        if not import_path.startswith(prefix):
            return []
        return list(self.go_dirs.get(import_path[len(prefix) :], []))


def _python_imports(
    tree: ast.Module, importer_rel: str, index: _Index
) -> Iterator[tuple[str | None, str]]:
    """``(resolved_path_or_None, external_name)`` per import in a Python file.

    ``from pkg import name`` resolves to ``pkg/name.py`` when that is a
    module, else to ``pkg`` itself — the longest-prefix lookup does both
    (D-SC1c-5). Relative imports are rooted at the importer's package. The
    external name is empty for a relative import, which has nowhere else to
    resolve to.
    """
    head, sep, _ = importer_rel.rpartition("/")
    package = head.replace("/", ".") if sep else ""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield index.resolve_python(alias.name), alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            base = _from_base(node, package)
            if base is None:
                continue
            external = base.split(".")[0] if node.level == 0 else ""
            for alias in node.names:
                yield index.resolve_python(f"{base}.{alias.name}"), external


def _from_base(node: ast.ImportFrom, package: str) -> str | None:
    if node.level == 0:
        return node.module
    parts = package.split(".") if package else []
    up = node.level - 1
    if up > len(parts):
        return None
    base = parts[: len(parts) - up]
    if node.module:
        base = [*base, *node.module.split(".")]
    return ".".join(base) if base else None


def _js_imports(
    text: str, importer: pathlib.Path, index: _Index
) -> Iterator[tuple[str | None, str]]:
    for m in _JS_IMPORT_RE.finditer(text):
        spec = m.group(1) or m.group(2) or m.group(3)
        if spec.startswith("."):
            yield index.resolve_js(importer, spec), ""
        else:
            segs = spec.split("/")
            name = "/".join(segs[:2]) if spec.startswith("@") else segs[0]
            yield None, name


def _go_imports(text: str, index: _Index) -> Iterator[tuple[str | None, str]]:
    paths = [m.group(1) for m in _GO_IMPORT_LINE_RE.finditer(text)]
    for block in _GO_IMPORT_BLOCK_RE.finditer(text):
        paths.extend(_GO_IMPORT_PATH_RE.findall(block.group(1)))
    for p in paths:
        targets = index.resolve_go(p)
        if targets:
            for t in targets:
                yield t, ""
        else:
            yield None, p.split("/")[0]


def _parse_python(text: str) -> ast.Module | None:
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError):
        return None


def _imports(
    path: pathlib.Path, text: str, index: _Index
) -> Iterable[tuple[str | None, str]]:
    suffix = path.suffix
    if suffix == ".py":
        tree = _parse_python(text)
        return [] if tree is None else _python_imports(tree, index.rel[path], index)
    if suffix == ".go":
        return _go_imports(text, index)
    return _js_imports(text, path, index)


# ---------------------------------------------------------------------------
# module_graph
# ---------------------------------------------------------------------------


def graph_nodes(
    root: pathlib.Path, all_files: list[pathlib.Path]
) -> list[pathlib.Path]:
    """Non-test source files, in walk order (D-SC1c-4).

    A test is a file under a test directory (``_is_test_path``) or one named
    as a test where the language keeps tests beside the code: Go's
    ``_test.go``, the ``.test``/``.spec`` infixes of the JavaScript runners,
    and Python's ``test_*.py``.
    """
    return [
        f
        for f in all_files
        if f.suffix in _SOURCE_EXTENSIONS
        and not _is_test_path(root, f)
        and not _is_test_file(f)
    ]


def _is_test_file(path: pathlib.Path) -> bool:
    name = path.name
    return name.endswith(_TEST_FILE_SUFFIXES) or (
        path.suffix == ".py" and name.startswith("test_")
    )


def _is_stdlib(path: pathlib.Path, name: str) -> bool:
    return path.suffix == ".py" and name in sys.stdlib_module_names


def _edges(index: _Index) -> tuple[set[tuple[str, str]], collections.Counter[str]]:
    edges: set[tuple[str, str]] = set()
    unresolved: collections.Counter[str] = collections.Counter()
    for path in index.nodes:
        if path.suffix not in _LANGUAGE_BY_SUFFIX:
            continue
        text = _source_text(path)
        if text is None:
            continue
        src = index.rel[path]
        for target, external in _imports(path, text, index):
            if target is not None:
                if target != src:
                    edges.add((src, target))
            elif external and not _is_stdlib(path, external):
                unresolved[external] += 1
    return edges, unresolved


def module_graph_block(
    root: pathlib.Path, all_files: list[pathlib.Path]
) -> dict[str, Any]:
    """The ``module_graph`` block; see the module docstring."""
    index = _Index(root, graph_nodes(root, all_files))
    edges, unresolved = _edges(index)
    fan_in = collections.Counter(dst for _, dst in edges)
    fan_out = collections.Counter(src for src, _ in edges)
    consumers: dict[str, list[str]] = collections.defaultdict(list)
    for src, dst in sorted(edges):
        consumers[dst].append(src)
    ranked = sorted(
        (p for p, n in fan_in.items() if n >= _MIN_FAN_IN),
        key=lambda p: (-fan_in[p], p),
    )
    top_unresolved = sorted(unresolved.items(), key=lambda kv: (-kv[1], kv[0]))
    languages = {
        _LANGUAGE_BY_SUFFIX[n.suffix]
        for n in index.nodes
        if n.suffix in _LANGUAGE_BY_SUFFIX
    }
    return {
        "languages": sorted(languages),
        "nodes": len(index.nodes),
        "edges": len(edges),
        "fan_in": dict(sorted(fan_in.items())),
        "fan_out": dict(sorted(fan_out.items())),
        "load_bearing_candidates": [
            {"path": p, "fan_in": fan_in[p], "consumers": consumers[p]}
            for p in ranked[:_TOP_K]
        ],
        "unresolved": dict(top_unresolved[:_MAX_UNRESOLVED]),
        "unresolved_truncated": len(top_unresolved) > _MAX_UNRESOLVED,
    }


# ---------------------------------------------------------------------------
# signatures
# ---------------------------------------------------------------------------


def _first_line(doc: str | None) -> str | None:
    if not doc:
        return None
    for line in doc.splitlines():
        if line.strip():
            return line.strip()
    return None


def _symbol(kind: str, name: str, signature: str, doc: str | None) -> dict[str, Any]:
    return {
        "kind": kind,
        "name": name,
        "signature": signature[:_MAX_SIGNATURE_CHARS],
        "doc": doc,
    }


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    """The plain names a top-level assignment binds, in source order."""
    targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
    names: list[str] = []
    for target in targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, ast.Tuple | ast.List):
            names.extend(e.id for e in target.elts if isinstance(e, ast.Name))
    return names


def _python_variables(node: ast.Assign | ast.AnnAssign) -> list[dict[str, Any]]:
    """Public module-level assignments as ``variable`` symbols (D-SC1d-7).

    The name and its annotation, never the value: ``settings: Settings`` is
    the contract a consumer imports; what it is set to is not. A bare
    ``settings = get_settings()`` carries only its name.
    """
    annotation = (
        f": {ast.unparse(node.annotation)}" if isinstance(node, ast.AnnAssign) else ""
    )
    return [
        _symbol("variable", name, f"{name}{annotation}", None)
        for name in _assigned_names(node)
        if not name.startswith(_PRIVATE_PREFIX)
    ]


def _python_symbols(tree: ast.Module) -> list[dict[str, Any]]:
    symbols: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if node.name.startswith(_PRIVATE_PREFIX):
                continue
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            sig = f"class {node.name}" + (f"({bases})" if bases else "")
            doc = _first_line(ast.get_docstring(node))
            symbols.append(_symbol("class", node.name, sig, doc))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name.startswith(_PRIVATE_PREFIX):
                continue
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            sig = f"{prefix} {node.name}({ast.unparse(node.args)})"
            if node.returns is not None:
                sig += f" -> {ast.unparse(node.returns)}"
            doc = _first_line(ast.get_docstring(node))
            symbols.append(_symbol("function", node.name, sig, doc))
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            symbols.extend(_python_variables(node))
    return symbols


def _comment_above(
    lines: list[str], lineno: int, markers: tuple[str, ...]
) -> str | None:
    """The first line of a comment block ending right above line ``lineno``."""
    i = lineno - 1
    block: list[str] = []
    while i >= 0:
        stripped = lines[i].strip()
        if not stripped.startswith(markers):
            break
        block.append(stripped)
        if stripped.startswith("/*"):
            break
        i -= 1
    for line in reversed(block):
        text = line.lstrip("/* \t").rstrip("*/ \t")
        if text:
            return text
    return None


def _line_signature(line: str) -> str:
    sig = line.strip()
    for stop in ("{", " =", ";"):
        cut = sig.find(stop)
        if cut > 0:
            sig = sig[:cut]
    return sig.strip()


def _regex_symbols(
    text: str,
    pattern: re.Pattern[str],
    kind_of: Callable[[re.Match[str]], tuple[str, str]],
    markers: tuple[str, ...],
) -> list[tuple[int, dict[str, Any]]]:
    """``(line number, symbol)`` per match; callers merge and sort by line."""
    lines = text.splitlines()
    out: list[tuple[int, dict[str, Any]]] = []
    for m in pattern.finditer(text):
        lineno = text.count("\n", 0, m.start())
        kind, name = kind_of(m)
        sig = _line_signature(lines[lineno])
        out.append(
            (lineno, _symbol(kind, name, sig, _comment_above(lines, lineno, markers)))
        )
    return out


def _js_kind(m: re.Match[str]) -> tuple[str, str]:
    keyword, name = m.group(1), m.group(2)
    if keyword.startswith("function"):
        return "function", name
    if keyword in {"class", "interface", "type", "enum"}:
        return keyword, name
    return "const", name


def _js_export_lists(text: str) -> list[tuple[int, dict[str, Any]]]:
    """One ``export`` symbol per name in an ``export { a, b as c }`` list."""
    lines = text.splitlines()
    out: list[tuple[int, dict[str, Any]]] = []
    for m in _JS_EXPORT_LIST_RE.finditer(text):
        lineno = text.count("\n", 0, m.start())
        doc = _comment_above(lines, lineno, _JS_COMMENT_MARKERS)
        for raw in m.group(1).split(","):
            item = _JS_EXPORT_ITEM_RE.match(raw.strip())
            if item is None:
                continue
            name = item.group(2) or item.group(1)
            out.append((lineno, _symbol("export", name, f"export {{ {name} }}", doc)))
    return out


def _js_symbols(text: str) -> list[dict[str, Any]]:
    found = _regex_symbols(text, _JS_EXPORT_RE, _js_kind, _JS_COMMENT_MARKERS)
    found += _regex_symbols(
        text,
        _JS_DEFAULT_IDENT_RE,
        lambda m: ("default", m.group(1)),
        _JS_COMMENT_MARKERS,
    )
    found += _js_export_lists(text)
    return [s for _, s in sorted(found, key=lambda t: t[0])]


def _go_symbols(text: str) -> list[dict[str, Any]]:
    found = _regex_symbols(
        text, _GO_FUNC_RE, lambda m: ("function", m.group(1)), _GO_COMMENT_MARKERS
    )
    found += _regex_symbols(
        text, _GO_TYPE_RE, lambda m: ("type", m.group(1)), _GO_COMMENT_MARKERS
    )
    return [s for _, s in sorted(found, key=lambda t: t[0])]


def file_signatures(path: pathlib.Path) -> dict[str, Any] | None:
    """One ``signatures.files`` entry; ``None`` when unreadable or unparseable."""
    language = _LANGUAGE_BY_SUFFIX.get(path.suffix)
    if language is None:
        return None
    text = _source_text(path)
    if text is None:
        return None
    doc: str | None = None
    if language == "python":
        tree = _parse_python(text)
        if tree is None:
            return None
        doc = _first_line(ast.get_docstring(tree))
        symbols = _python_symbols(tree)
    elif language == "go":
        symbols = _go_symbols(text)
    else:
        symbols = _js_symbols(text)
    return {
        "language": language,
        "doc": doc,
        "symbols": symbols[:_MAX_SYMBOLS_PER_FILE],
        "truncated": len(symbols) > _MAX_SYMBOLS_PER_FILE,
    }


def signature_targets(
    root: pathlib.Path, all_files: list[pathlib.Path], graph: dict[str, Any]
) -> list[pathlib.Path]:
    """Candidates by rank, then entrypoint candidates by path, no repeats."""
    nodes = graph_nodes(root, all_files)
    by_rel = {_rel(root, n): n for n in nodes}
    ordered = [by_rel[c["path"]] for c in graph["load_bearing_candidates"]]
    ordered.extend(n for n in nodes if _is_entrypoint_candidate(n) and n not in ordered)
    return ordered


def signatures_block(
    root: pathlib.Path, all_files: list[pathlib.Path], graph: dict[str, Any]
) -> dict[str, Any]:
    """The ``signatures`` block, within ``_MAX_SIGNATURES_BYTES`` (D-SC1c-8).

    Files are taken in ``signature_targets`` order until the next one would
    overrun the budget; ``truncated`` says that happened. A file that cannot
    be parsed is skipped, not charged.
    """
    files: dict[str, Any] = {}
    spent = 0
    truncated = False
    for path in signature_targets(root, all_files, graph):
        entry = file_signatures(path)
        if entry is None:
            continue
        cost = len(json.dumps(entry))
        if spent + cost > _MAX_SIGNATURES_BYTES:
            truncated = True
            break
        files[_rel(root, path)] = entry
        spent += cost
    return {"files": files, "truncated": truncated}
