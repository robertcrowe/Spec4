"""pytest plugin for trace identity (7q0, §79): the refactor's rename check.

    TRACE_OUT=/outside/the/repo/run.json PYTHONHASHSEED=0 PYTHONPATH=scripts/cleanup \\
        uv run pytest -p trace_identity -q -p no:cacheprovider --basetemp=/outside/tmp

Optional: TRACE_MODULE (default spec4.agentifier.agentifier) and TRACE_FAMILY (default
the eight agentifier generators and `run`, comma-separated) name what is traced.
TRACE_STEPS names step functions whose entry is recorded (7q's proof 7). Compare two
runs with trace_diff.py.

--basetemp is required, and must be the same for the baseline and every run compared
with it. A test's tmp_path becomes a session value (`working_dir`), and pytest's
default numbered base directory changes on every run. The first determinism check found
exactly that in 10 tests. A fixed base makes the paths identical by construction, so
nothing is normalised for it.

The family is the functions of TRACE_MODULE whose name, with any leading underscore
stripped, is in TRACE_FAMILY. So the tree before the promotion and the tree after it
are traced alike. sys.monitoring watches exactly their code objects: local PY_START,
PY_YIELD and PY_RETURN, plus a global PY_UNWIND filtered to them.

Only the OUTERMOST family frame is recorded: a frame with no family frame anywhere in
its f_back chain. A split's new nesting is therefore invisible, and what is recorded is
what the consumer receives:
  start   -- the entry's name and its arguments (session and llm_config excluded);
  yield   -- the chunk delivered, and a snapshot of the session at that moment;
  return  -- the return value and a final snapshot;
  unwind  -- the exception and a final snapshot. GeneratorExit is not recorded: a
             consumer that stops early closes the generator at a GC-dependent moment.

Snapshots serialise the session in INSERTION ORDER, every nested dict too, so key order
is part of the trace and a reordered write is a divergence. The only normalisation is
of values: 32-hex and dashed uuid4 strings, ISO timestamps, and 0x addresses inside the
reprs of non-JSON objects.

Each invocation also records the thread it ran in. trace_diff.py takes its verdict on
main-thread invocations and classifies worker-thread ones (§79.0, §79.2).
"""

from __future__ import annotations

import collections
import hashlib
import importlib
import json
import os
import re
import sys
import threading

DEFAULT_MODULE = "spec4.agentifier.agentifier"
DEFAULT_FAMILY = {
    "run_catalog_phase",
    "run_spec_phase",
    "run_cross_cutting_phase",
    "run_priority_phase",
    "handle_reentry",
    "finalize_specs",
    "begin_priority_phase",
    "complete_agentifier",
    "run",
}
TOOL = 3
UUID = re.compile(
    r"\b[0-9a-f]{32}\b|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
)
ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?")
ADDR = re.compile(r"0x[0-9a-fA-F]+")

_lock = threading.RLock()
_current = {"node": "<collection>"}
_family: dict = {}  # code -> normalised name
_steps: dict = {}  # code -> step name
_traces: dict = collections.defaultdict(list)
_open: dict = {}  # id(frame) -> invocation
_snaps: dict = {}
_step_hits: dict = collections.defaultdict(set)


def _norm(s: str) -> str:
    return ISO.sub("<ts>", UUID.sub("<uuid>", s))


def _ser(v):
    if isinstance(v, str):
        return _norm(v)
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, dict):
        return {"__pairs__": [[_ser(k), _ser(x)] for k, x in list(v.items())]}
    if isinstance(v, (list, tuple)):
        return [_ser(x) for x in list(v)]
    return {
        "__obj__": type(v).__qualname__,
        "repr": ADDR.sub("0x?", _norm(repr(v)))[:400],
    }


def _snap(frame) -> str:
    session = frame.f_locals.get("session")
    text = json.dumps(_ser(session), ensure_ascii=False)
    h = hashlib.sha1(text.encode()).hexdigest()[:16]
    _snaps.setdefault(h, text)
    return h


def _outermost(frame) -> bool:
    b = frame.f_back
    while b is not None:
        if b.f_code in _family:
            return False
        b = b.f_back
    return True


def _under_family(frame) -> bool:
    b = frame.f_back
    while b is not None:
        if b.f_code in _family:
            return True
        b = b.f_back
    return False


def _args(frame, code) -> dict:
    n = code.co_argcount + code.co_kwonlyargcount
    return {
        k: _ser(frame.f_locals.get(k))
        for k in code.co_varnames[:n]
        if k not in ("session", "llm_config", "_llm_config")
    }


def _on_start(code, offset):
    frame = sys._getframe(1)
    if code in _steps:
        if _under_family(frame):
            with _lock:
                _step_hits[_steps[code]].add(_current["node"])
        return
    if code not in _family or not _outermost(frame):
        return
    with _lock:
        # The thread matters. A streaming worker the test does not wait for can outlive
        # the test's patches, and its trace then depends on timing, not on the code
        # (§79.0).
        main = threading.current_thread() is threading.main_thread()
        inv = {
            "entry": _family[code],
            "args": _args(frame, code),
            "thread": "main" if main else "worker",
            "events": [],
            # The session as the invocation found it: kept beside the events and not
            # in them, so traces stay comparable with baselines recorded without it.
            # 7q3 used it to measure the keys each generator writes.
            "start": _snap(frame),
        }
        _open[id(frame)] = inv
        _traces[_current["node"]].append(inv)


def _on_yield(code, offset, value):
    frame = sys._getframe(1)
    with _lock:
        inv = _open.get(id(frame))
        if inv is not None:
            inv["events"].append(["y", _ser(value), _snap(frame)])


def _on_return(code, offset, value):
    frame = sys._getframe(1)
    with _lock:
        inv = _open.pop(id(frame), None)
        if inv is not None:
            inv["events"].append(["r", _ser(value), _snap(frame)])


def _on_unwind(code, offset, exc):
    if code not in _family:
        return
    frame = sys._getframe(1)
    with _lock:
        inv = _open.pop(id(frame), None)
        if inv is not None and not isinstance(exc, GeneratorExit):
            event = ["x", type(exc).__name__, _norm(str(exc))[:300], _snap(frame)]
            inv["events"].append(event)


def pytest_collection_finish(session) -> None:
    import inspect

    mod = importlib.import_module(os.environ.get("TRACE_MODULE", DEFAULT_MODULE))
    family = {s for s in os.environ.get("TRACE_FAMILY", "").split(",") if s}
    family = family or DEFAULT_FAMILY
    step_names = [s for s in os.environ.get("TRACE_STEPS", "").split(",") if s]
    for name, obj in vars(mod).items():
        if inspect.isfunction(obj) and obj.__module__ == mod.__name__:
            code = inspect.unwrap(obj).__code__
            if name.lstrip("_") in family:
                _family[code] = name.lstrip("_")
            elif name in step_names:
                _steps[code] = name
    missing = sorted(family - set(_family.values()))
    if missing:
        raise RuntimeError(f"trace_identity: family members not found: {missing}")
    unknown = sorted(set(step_names) - set(_steps.values()))
    if unknown:
        raise RuntimeError(f"trace_identity: steps not found: {unknown}")
    ev = sys.monitoring.events
    sys.monitoring.use_tool_id(TOOL, "trace_identity")
    sys.monitoring.register_callback(TOOL, ev.PY_START, _on_start)
    sys.monitoring.register_callback(TOOL, ev.PY_YIELD, _on_yield)
    sys.monitoring.register_callback(TOOL, ev.PY_RETURN, _on_return)
    sys.monitoring.register_callback(TOOL, ev.PY_UNWIND, _on_unwind)
    for code in _family:
        sys.monitoring.set_local_events(
            TOOL, code, ev.PY_START | ev.PY_YIELD | ev.PY_RETURN
        )
    for code in _steps:
        sys.monitoring.set_local_events(TOOL, code, ev.PY_START)
    sys.monitoring.set_events(TOOL, ev.PY_UNWIND)
    print(f"\ntrace_identity: family {len(_family)} code objects; steps {len(_steps)}")


def pytest_runtest_setup(item) -> None:
    _current["node"] = item.nodeid


def pytest_sessionfinish(session, exitstatus) -> None:
    try:
        sys.monitoring.set_events(TOOL, 0)
        sys.monitoring.free_tool_id(TOOL)
    except Exception:
        pass
    out = os.environ.get("TRACE_OUT")
    if not out:
        return
    traces = {k: v for k, v in _traces.items() if v}
    n_inv = sum(len(v) for v in traces.values())
    n_events = sum(len(i["events"]) for v in traces.values() for i in v)
    entries = collections.Counter(i["entry"] for v in traces.values() for i in v)
    meta = {
        "tests_traced": len(traces),
        "invocations": n_inv,
        "events": n_events,
        "distinct_snapshots": len(_snaps),
        "exitstatus": int(exitstatus),
        "entries": dict(entries),
    }
    with open(out, "w") as f:
        json.dump(
            {
                "meta": meta,
                "traces": traces,
                "snapshots": _snaps,
                "steps": {k: sorted(v) for k, v in _step_hits.items()},
            },
            f,
        )
    print(f"trace_identity: {json.dumps(meta)}")
