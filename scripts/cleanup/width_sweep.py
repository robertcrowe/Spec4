"""pytest plugin: the annotation-width sweep (7o5, §77.9; ruled at review of 7o).

    WIDTH_SWEEP_OUT=/outside/the/repo/sweep.json PYTHONPATH=scripts/cleanup \\
        uv run pytest -p width_sweep -q -p no:cacheprovider

The rule: an annotation must not be narrower than what a test in the suite exercises.

The targets are 7o's rows classed "genuinely typeable": WIDTH_SWEEP_ROWS, by default
data/rows_7o.json, which has 58 of them. Each row is located by its line number at
WIDTH_SWEEP_BASE (default 4acdffd, the tree the rows were mapped on) and found by
qualified name in the working tree. While the whole suite runs, the value that actually
arrives at each target is recorded, through sys.monitoring local events on exactly
those code objects, so nothing else is slowed.

Each value is checked against the annotation in the working tree, the way mypy would
accept it: int for float, bool for int, a TypedDict as a dict, and so on. A value that
is not accepted is recorded with the test that was running. unittest.mock objects and
SimpleNamespace are marked as stand-ins, so a stand-in for the annotated type can be
told apart from a value of a different real type.

The results go to WIDTH_SWEEP_OUT, and a summary line is printed at the end.
Each value's caller is recorded too, per target, so a value a production caller
passes can be told apart from one a test passes directly (Phase 8,
PHASE8_RECORD.md 2.1(c)). The summary line is unchanged.
"""

from __future__ import annotations

import ast
import builtins
import collections
import collections.abc as abc
import importlib
import inspect
import json
import os
import pathlib
import re
import subprocess
import sys
import types
import unittest.mock

HERE = pathlib.Path(__file__).resolve().parent
ROWS = pathlib.Path(os.environ.get("WIDTH_SWEEP_ROWS", HERE / "data" / "rows_7o.json"))
BASE = os.environ.get("WIDTH_SWEEP_BASE", "4acdffd")  # the rows' "head" lines are here
TOOL = 4
FALLBACK = {
    "SearchConfig": "spec4.websearch.SearchConfig",
    "AsyncIterable": abc.AsyncIterable,
    "Iterable": abc.Iterable,
    "Awaitable": abc.Awaitable,
}

_current = {"node": "<collection>"}
_targets: list[dict] = []
_by_code: dict = collections.defaultdict(list)
_ret_by_code: dict = collections.defaultdict(list)
_obs: dict = collections.defaultdict(lambda: collections.Counter())
_bad: dict = collections.defaultdict(list)


def _names(r: dict) -> dict[str, str]:
    if r["file"].endswith("subagents.py") and r["base"] == 236:
        return {"coro": "Awaitable[Any]"}
    if ";" in r["ptype"]:
        return dict(p.strip().split(": ", 1) for p in r["ptype"].split(";"))
    return {re.sub(r"\s*\(.*\)$", "", r["target"]).strip().split(".")[-1]: r["ptype"]}


def _enclosing(tree: ast.AST, line: int) -> list[ast.AST]:
    """The chain of class/def nodes whose span holds `line`, outermost first."""
    chain, node = [], tree
    while True:
        inner = [
            n
            for n in ast.iter_child_nodes(node)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and (
                min([n.lineno] + [d.lineno for d in n.decorator_list])
                <= line
                <= n.end_lineno
            )
        ]
        if not inner:
            return chain
        node = inner[0]
        chain.append(node)


def _find(tree: ast.AST, qual: list[str]) -> ast.AST:
    node = tree
    for name in qual:
        node = next(
            n
            for n in ast.iter_child_nodes(node)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and n.name == name
        )
    return node


def _resolve(name: str, ns: dict):
    head, *rest = name.split(".")
    if head in ns:
        obj = ns[head]
    elif hasattr(builtins, head):
        obj = getattr(builtins, head)
    elif head in FALLBACK:
        f = FALLBACK[head]
        if isinstance(f, str):
            mod, _, attr = f.rpartition(".")
            return getattr(importlib.import_module(mod), attr)
        return f
    else:
        raise KeyError(name)
    for part in rest:
        obj = getattr(obj, part)
    return obj


def _isinst(v, t) -> bool:
    if t is float:
        return isinstance(v, (int, float))
    if isinstance(t, type) and hasattr(t, "__required_keys__"):  # TypedDict
        return isinstance(v, dict)
    return isinstance(v, t)


def accepts(v, node, ns) -> bool:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return accepts(v, node.left, ns) or accepts(v, node.right, ns)
    if isinstance(node, ast.Constant) and node.value is None:
        return v is None
    if isinstance(node, (ast.Name, ast.Attribute)):
        name = ast.unparse(node)
        if name == "Any":
            return True
        if name == "None":
            return v is None
        return _isinst(v, _resolve(name, ns))
    if isinstance(node, ast.Subscript):
        base = ast.unparse(node.value)
        args = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        if base == "dict":
            return isinstance(v, dict) and all(
                accepts(k, args[0], ns) and accepts(x, args[1], ns)
                for k, x in v.items()
            )
        if base == "list":
            return isinstance(v, list) and all(accepts(e, args[0], ns) for e in v)
        if base == "Iterable":
            return isinstance(v, abc.Iterable)
        if base == "AsyncIterable":
            return isinstance(v, abc.AsyncIterable)
        if base == "Awaitable":
            return inspect.isawaitable(v)
    raise ValueError(f"unhandled annotation {ast.unparse(node)}")


def _standin(v) -> bool:
    return isinstance(v, (unittest.mock.NonCallableMock, types.SimpleNamespace))


# Each value's caller, so a value a production caller passes can be told apart from
# one a test passes directly (Phase 8's `_fmt_usd` rule, PHASE8_RECORD.md 2.1(c)).
_callers: dict = collections.defaultdict(lambda: collections.Counter())


def _caller(frame) -> str:
    """The calling frame's module and qualified name: ``spec4.layouts._shared:f``."""
    back = frame.f_back
    if back is None:
        return "<none>"
    return f"{back.f_globals.get('__name__', '?')}:{back.f_code.co_qualname}"


def _record(t: dict, value, caller: str) -> None:
    key = t["key"]
    try:
        ok = accepts(value, t["ann_ast"], t["ns"])
    except (
        Exception
    ) as exc:  # an annotation the checker cannot read is itself a finding
        ok = None
        _bad[key].append({"test": _current["node"], "type": f"checker error: {exc}"})
    tname = type(value).__module__ + "." + type(value).__qualname__
    _obs[key][(tname, ok, _standin(value))] += 1
    _callers[key][(caller, tname, ok)] += 1
    if ok is False and len(_bad[key]) < 12:
        _bad[key].append(
            {
                "test": _current["node"],
                "type": tname,
                "standin": _standin(value),
                "repr": repr(value)[:80],
            }
        )


def _on_start(code, offset):
    frame = sys._getframe(1)
    for t in _by_code.get(code, ()):
        if t["param"] in frame.f_locals:
            _record(t, frame.f_locals[t["param"]], _caller(frame))


def _on_return(code, offset, retval):
    frame = sys._getframe(1)
    for t in _ret_by_code.get(code, ()):
        if t["param"] in frame.f_locals:
            _record(t, frame.f_locals[t["param"]], _caller(frame))


def pytest_collection_finish(session) -> None:
    if not os.environ.get("WIDTH_SWEEP_OUT"):
        raise RuntimeError(
            "width_sweep: set WIDTH_SWEEP_OUT to a path outside the repo"
        )
    repo = pathlib.Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    rows = [
        r for r in json.loads(ROWS.read_text()) if r["klass"] == "genuinely typeable"
    ]
    for r in rows:
        rel = r["file"]
        old = ast.parse(
            subprocess.run(
                ["git", "-C", str(repo), "show", f"{BASE}:{rel}"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
        new = ast.parse((repo / rel).read_text())
        chain = _enclosing(old, r["head"])
        qual = [n.name for n in chain]
        modname = rel.removeprefix("src/").removesuffix(".py").replace("/", ".")
        mod = importlib.import_module(modname.removesuffix(".__init__"))
        node = _find(new, qual)
        for name in _names(r):
            t = {
                "key": f"{rel.removeprefix('src/spec4/')}:{r['base']}:{name}",
                "param": name,
                "ns": vars(mod),
                "qual": ".".join(qual),
            }
            obj = _resolve(".".join(qual), vars(mod))
            if isinstance(
                node, ast.ClassDef
            ):  # a dataclass field: its generated __init__
                field = next(
                    n
                    for n in node.body
                    if isinstance(n, ast.AnnAssign) and n.target.id == name
                )
                t["ann_ast"] = field.annotation
                _by_code[obj.__init__.__code__].append(t)
            else:
                a = node.args
                params = [*a.posonlyargs, *a.args, *a.kwonlyargs]
                arg = next((x for x in params if x.arg == name), None)
                code = inspect.unwrap(obj).__code__
                if arg is not None:
                    t["ann_ast"] = arg.annotation
                    _by_code[code].append(t)
                else:  # an annotated local: read at return
                    loc = next(
                        n
                        for n in ast.walk(node)
                        if isinstance(n, ast.AnnAssign)
                        and isinstance(n.target, ast.Name)
                        and n.target.id == name
                    )
                    t["ann_ast"] = loc.annotation
                    _ret_by_code[code].append(t)
            t["annotation"] = ast.unparse(t["ann_ast"])
            _targets.append(t)
    ev = sys.monitoring.events
    sys.monitoring.use_tool_id(TOOL, "width_sweep")
    sys.monitoring.register_callback(TOOL, ev.PY_START, _on_start)
    sys.monitoring.register_callback(TOOL, ev.PY_RETURN, _on_return)
    for code in _by_code:
        sys.monitoring.set_local_events(TOOL, code, ev.PY_START)
    for code in _ret_by_code:
        both = ev.PY_START | ev.PY_RETURN
        sys.monitoring.set_local_events(
            TOOL, code, both if code in _by_code else ev.PY_RETURN
        )
    n_codes = len(_by_code) + len(_ret_by_code)
    print(f"\nwidth_sweep: {len(_targets)} targets on {n_codes} code objects")


def pytest_runtest_setup(item) -> None:
    _current["node"] = item.nodeid


def pytest_sessionfinish(session, exitstatus) -> None:
    try:
        sys.monitoring.free_tool_id(TOOL)
    except Exception:
        pass
    out = []
    for t in _targets:
        k = t["key"]
        obs = _obs.get(k, {})
        out.append(
            {
                "key": k,
                "qual": t["qual"],
                "annotation": t["annotation"],
                "calls": sum(obs.values()),
                "types": sorted(
                    f"{n} ok={ok} standin={s} x{c}" for (n, ok, s), c in obs.items()
                ),
                "callers": sorted(
                    f"{who} {n} ok={ok} x{c}"
                    for (who, n, ok), c in _callers.get(k, {}).items()
                ),
                "rejected": _bad.get(k, []),
            }
        )
    pathlib.Path(os.environ["WIDTH_SWEEP_OUT"]).write_text(json.dumps(out, indent=1))
    reached = sum(1 for r in out if r["calls"])
    errors = [r["key"] for r in out if any("standin" not in x for x in r["rejected"])]
    real = [
        r["key"] for r in out if any(x.get("standin") is False for x in r["rejected"])
    ]
    standin = [
        r["key"]
        for r in out
        if r["rejected"] and all(x.get("standin") is True for x in r["rejected"])
    ]
    print(
        f"\nwidth_sweep: targets {len(out)}; reached {reached}; never reached "
        f"{len(out) - reached}; rejected by a real value {len(real)} {real}; "
        f"by stand-ins only {len(standin)}; checker errors {len(errors)} {errors}"
    )
