"""Phase 0's measurements, re-run on two trees and compared
(cleanup-complete:CLEANUP_REPORT.md §7).

    uv run python scripts/cleanup/remeasure.py BASE HEAD \\
        [--cov-base FILE] [--cov-head FILE] [--run-coverage DIR] \\
        [--families FILE] [--json OUT.json]

BASE and HEAD are revisions. Each is exported with `git archive` into a temporary
directory, so the working tree is never read or written. Every measurement is taken on
both exports with the same tool, and printed as the report's tables:

  gate          `ruff check src/ tests/` and `ruff format --check src/ tests/` under the
                tree's own configuration, and `mypy src/`. The test and coverage totals
                come from the coverage outputs.
  coverage      per module, from `pytest --cov=spec4 --cov-report=term-missing` output:
                --cov-base and --cov-head name saved outputs; --run-coverage DIR
                runs the suite in each export that has none, saving the output in
                DIR. Modules that were split are compared as families: --families is a
                JSON object from an old module to the paths it became, under
                src/spec4/, where a path ending in "/" is a package.
  dead code     `uvx vulture@2.16 src/ tests/ --min-confidence 60`, without and with the
                tree's vulture_whitelist.py; ruff `F401,F811,F841,ARG` with noqa
                respected; cleanup-complete:CLEANUP_INVENTORY.md §7's cross-reference.
  dependencies  `uvx deptry@0.25.1 .`, its DEP001 split into the project's own `spec4`
                imports, evals/ sibling imports and the rest.
  complexity    ruff `C90,PLR0912,PLR0913,PLR0915,SIM,B` on src/ with noqa ignored, so
                what the gate accepts still counts, and the functions over C901's
                threshold.
  size          §2's file-size measures.
  imports       §6's edge set: cycles, the three layer rules, the importers of `llm`
                and `project_manager`, lazy couplings and TYPE_CHECKING-only edges; and
                §8's `global` statements.

Vulture and deptry are pinned to Phase 0's versions; ruff and mypy are the repo's. On
1d1dcbd, the ast measures reproduce every figure Phase 0 recorded, and so do ruff,
deptry and mypy. Two conventions are Phase 0's: an empty file counts as one line,
and `from P import m` is an edge to P as well as to P.m. scripts/cleanup/ is left out of
the cross-reference: it is tooling about the code, as the record is.
"""

import argparse
import ast
import collections
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

REPO = pathlib.Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
)
VULTURE = ["uvx", "vulture@2.16"]
DEPTRY = ["uvx", "deptry@0.25.1"]
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
COV_ROW = re.compile(r"^src/spec4/(\S+\.py)\s+(\d+)\s+(\d+)\s+\d+%", re.M)
COV_TOTAL = re.compile(r"^TOTAL\s+(\d+)\s+(\d+)\s+(\d+)%", re.M)
TESTS = re.compile(
    r"((?:\d+ (?:failed|passed|skipped|errors?|xfailed|xpassed)(?:, )?)+) in [\d.]+s"
)
HIT = re.compile(r"^(\S+?):\d+:\d+: ([A-Z]+\d+) (.*)$", re.M)
FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)
DEFS = (*FUNCS, ast.ClassDef)
LOWER = (
    "spec4.agents",
    "spec4.agentifier",
    "spec4.project_manager",
    "spec4.llm",
    "spec4.feature_specs",
    "spec4.design_manifest",
    "spec4.stack_routing",
    "spec4.streaming",
)
UI = ("spec4.layouts", "spec4.callbacks", "spec4.app", "spec4.session")


def tool(name: str) -> str:
    local = REPO / ".venv" / "bin" / name
    return str(local) if local.exists() else shutil.which(name) or name


def run(cmd: list[str], cwd: pathlib.Path, env: dict | None = None) -> str:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    return ANSI.sub("", r.stdout + r.stderr)


def last_line(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[-1] if lines else "?"


def export(rev: str, dest: pathlib.Path) -> pathlib.Path:
    dest.mkdir(parents=True)
    data = subprocess.run(
        ["git", "-C", str(REPO), "archive", rev], capture_output=True, check=True
    ).stdout
    tarfile.open(fileobj=io.BytesIO(data)).extractall(dest, filter="data")
    return dest


def pyfiles(root: pathlib.Path, d: str, exclude: tuple = ()) -> list[pathlib.Path]:
    out = []
    for p in sorted((root / d).rglob("*.py")):
        rel = p.relative_to(root).as_posix()
        if "__pycache__" not in p.parts and not rel.startswith(exclude):
            out.append(p)
    return out


def modname(root: pathlib.Path, p: pathlib.Path) -> str:
    parts = list(p.relative_to(root / "src").with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def span(n: ast.AST) -> int:
    return n.end_lineno - n.lineno + 1


# --- §2: file sizes -------------------------------------------------------------------


def sizes(root: pathlib.Path, d: str) -> list[dict]:
    rows = []
    for p in pyfiles(root, d):
        text = p.read_text()
        tree = ast.parse(text)
        fns = [n for n in ast.walk(tree) if isinstance(n, FUNCS)]
        # Phase 0's count: an unterminated last line counts, so an empty file is 1 line.
        n_lines = text.count("\n") + (0 if text.endswith("\n") else 1)
        rows.append(
            {
                "file": p.relative_to(root).as_posix(),
                "lines": n_lines,
                "functions": len(fns),
                "classes": sum(isinstance(n, ast.ClassDef) for n in ast.walk(tree)),
            }
        )
    return sorted(rows, key=lambda r: -r["lines"])


def longest_functions(root: pathlib.Path, n: int) -> list[tuple[int, str]]:
    out = []
    for p in pyfiles(root, "src/spec4"):
        for f in ast.walk(ast.parse(p.read_text())):
            if isinstance(f, FUNCS):
                out.append((span(f), f"{modname(root, p)}.{f.name}"))
    return sorted(out, reverse=True)[:n]


# --- §6 and §8: the import graph, and module state ------------------------------------


def edges(root: pathlib.Path, mods: dict) -> dict:
    kinds = {k: collections.defaultdict(set) for k in ("top", "lazy", "typing")}
    for m, p in mods.items():
        tree = ast.parse(p.read_text())
        parent = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
        pkg = m if p.name == "__init__.py" else m.rpartition(".")[0]
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                targets = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                if n.level:
                    base = pkg.split(".")
                    base = base[: len(base) - (n.level - 1)]
                    mod = ".".join(base + ([n.module] if n.module else []))
                else:
                    mod = n.module or ""
                # Phase 0: `from P import m` is an edge to P, and to P.m when m is a
                # module.
                subs = [f"{mod}.{a.name}" for a in n.names]
                targets = [mod] + [s for s in subs if s in mods]
            else:
                continue
            kind, a = "top", parent.get(n)
            while a is not None:
                if isinstance(a, FUNCS):
                    kind = "lazy"
                    break
                test = ast.unparse(a.test) if isinstance(a, ast.If) else ""
                if test in ("TYPE_CHECKING", "typing.TYPE_CHECKING"):
                    kind = "typing"
                    break
                a = parent.get(a)
            for t in targets:
                if t in mods and t != m:
                    kinds[kind][m].add(t)
    return kinds


def cycles(graph: dict, nodes: list[str]) -> list[list[str]]:
    """Strongly connected components of more than one module (Tarjan)."""
    index: dict = {}
    low: dict = {}
    stack: list = []
    on: set = set()
    out: list = []

    def visit(v: str) -> None:
        index[v] = low[v] = len(index)
        stack.append(v)
        on.add(v)
        for w in sorted(graph.get(v, ())):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                out.append(sorted(comp))

    sys.setrecursionlimit(10000)
    for v in sorted(nodes):
        if v not in index:
            visit(v)
    return out


def under(m: str, prefixes: tuple) -> bool:
    return any(m == x or m.startswith(x + ".") for x in prefixes)


def imports(root: pathlib.Path, mods: dict) -> dict:
    kinds = edges(root, mods)
    alle = collections.defaultdict(set)
    for k in ("top", "lazy"):
        for m, ts in kinds[k].items():
            alle[m] |= ts
    importers = collections.Counter(t for ts in alle.values() for t in ts)
    pairs = [(m, t) for m, ts in alle.items() for t in ts]
    return {
        "modules": len(mods),
        "cycles": cycles(alle, list(mods)),
        "layer_violations": sorted(
            f"{m} -> {t}"
            for m, t in pairs
            if (under(m, LOWER) and under(t, UI))
            or (
                under(m, ("spec4.layouts",))
                and under(t, ("spec4.callbacks", "spec4.app"))
            )
            or t == "spec4.app"
        ),
        "importers_llm": importers["spec4.llm"],
        "importers_project_manager": importers["spec4.project_manager"],
        "lazy": sorted(
            f"{m} -> {t}"
            for m, ts in kinds["lazy"].items()
            for t in ts
            if t not in kinds["top"].get(m, ())
        ),
        "typing_only": sum(len(v) for v in kinds["typing"].values()),
        "globals": sum(
            isinstance(n, ast.Global)
            for p in mods.values()
            for n in ast.walk(ast.parse(p.read_text()))
        ),
    }


# --- §7: the cross-reference ----------------------------------------------------------


def xref(root: pathlib.Path, mods: dict) -> dict:
    files = {
        p.relative_to(root).as_posix(): set(WORD.findall(p.read_text(errors="replace")))
        for d in ("src", "tests", "evals", "scripts")
        if (root / d).exists()
        for p in pyfiles(root, d, exclude=("scripts/cleanup",))
    }
    rows = []
    for m, p in mods.items():
        own = p.relative_to(root).as_posix()
        for n in ast.parse(p.read_text()).body:
            if not isinstance(n, DEFS):
                continue
            refs = [f for f, words in files.items() if f != own and n.name in words]
            src = sum(f.startswith("src/") for f in refs)
            rows.append(
                {
                    "name": f"{m}.{n.name}",
                    "private": n.name.startswith("_"),
                    "callback": any(
                        "callback" in ast.unparse(d).split("(")[0]
                        for d in n.decorator_list
                    ),
                    "refs": len(refs),
                    "src_refs": src,
                }
            )
    zero = [r for r in rows if not r["refs"]]
    public = [r for r in zero if not r["private"]]
    return {
        "definitions": len(rows),
        "zero": len(zero),
        "zero_private": len(zero) - len(public),
        "zero_public": len(public),
        "zero_public_callbacks": sum(r["callback"] for r in public),
        "review_list": sorted(r["name"] for r in public if not r["callback"]),
        "test_only": sum(1 for r in rows if r["refs"] and not r["src_refs"]),
    }


# --- the tools ------------------------------------------------------------------------


def ruff_hits(
    root: pathlib.Path, select: str, paths: list[str], ignore_noqa: bool
) -> list:
    cmd = [tool("ruff"), "check", "--isolated", "--no-cache", "--select", select]
    cmd += ["--output-format", "concise", *paths]
    if ignore_noqa:
        cmd.append("--ignore-noqa")
    return HIT.findall(run(cmd, root))


def vulture(root: pathlib.Path) -> dict:
    out = {}
    for label, extra in (("raw", []), ("whitelisted", ["vulture_whitelist.py"])):
        if extra and not (root / extra[0]).exists():
            out[label] = None
            continue
        text = run([*VULTURE, "src/", "tests/", *extra, "--min-confidence", "60"], root)
        lines = [ln for ln in text.splitlines() if "confidence)" in ln]
        out[label] = {
            "src": sum(ln.startswith("src/") for ln in lines),
            "tests": sum(ln.startswith("tests/") for ln in lines),
            "lines": lines,
        }
    return out


def deptry(root: pathlib.Path) -> dict:
    text = run([*DEPTRY, "."], root, env=dict(os.environ, NO_COLOR="1"))
    # DEP002 is reported against pyproject.toml, with no line or column.
    found = re.findall(r"^(\S+?)(?::\d+:\d+)?: (DEP\d{3}) '([^']+)'", text, re.M)
    out = collections.Counter()
    other = []
    for path, code, name in found:
        if code == "DEP001":
            key = (
                "own"
                if name == "spec4"
                else "evals"
                if path.startswith("evals/")
                else "other"
            )
            out[f"DEP001 {key}"] += 1
            if key == "other":
                other.append(f"{path}: {name}")
        else:
            out[code] += 1
            other.append(f"{path}: {code} {name}")
    return {"counts": dict(out), "total": len(found), "listed": other}


def gate(root: pathlib.Path) -> dict:
    return {
        "ruff": last_line(
            run([tool("ruff"), "check", "--no-cache", "src/", "tests/"], root)
        ),
        "format": last_line(
            run(
                [tool("ruff"), "format", "--check", "--no-cache", "src/", "tests/"],
                root,
            )
        ),
        "mypy": last_line(run([tool("mypy"), "src/"], root)),
    }


def coverage_run(root: pathlib.Path, rev: str, outdir: pathlib.Path) -> pathlib.Path:
    """Run the suite in an export, importing its own src/ ahead of the installed one."""
    env = dict(os.environ, PYTHONPATH=str(root / "src"))
    cmd = [sys.executable, "-m", "pytest", "--cov=spec4", "--cov-report=term-missing"]
    text = run([*cmd, "-q", "-p", "no:cacheprovider"], root, env=env)
    out = outdir / f"coverage_{rev}.txt"
    out.write_text(text)
    return out


def coverage(path: pathlib.Path) -> dict:
    text = path.read_text()
    total = COV_TOTAL.search(text)
    tests = TESTS.findall(text)
    return {
        "modules": {m[1]: (int(m[2]), int(m[3])) for m in COV_ROW.finditer(text)},
        "total": (int(total[1]), int(total[2]), int(total[3])) if total else None,
        "tests": tests[-1] if tests else "?",
    }


# --- the measurement of one tree, and the comparison ----------------------------------


def measure(root: pathlib.Path) -> dict:
    mods = {modname(root, p): p for p in pyfiles(root, "src/spec4")}
    arg = ruff_hits(root, "F401,F811,F841,ARG", ["src/", "tests/"], ignore_noqa=False)
    cx = ruff_hits(
        root, "C90,PLR0912,PLR0913,PLR0915,SIM,B", ["src/"], ignore_noqa=True
    )
    c901 = []
    for path, code, msg in cx:
        m = re.match(r"`(\w+)` is too complex \((\d+) > \d+\)", msg)
        if code == "C901" and m:
            c901.append((int(m[2]), f"{m[1]} ({path.removeprefix('src/spec4/')})"))
    src_sizes, test_sizes = sizes(root, "src/spec4"), sizes(root, "tests")
    return {
        "gate": gate(root),
        "vulture": vulture(root),
        "arg": {
            d: dict(collections.Counter(c for p, c, _ in arg if p.startswith(d)))
            for d in ("src/", "tests/")
        },
        "xref": xref(root, mods),
        "deptry": deptry(root),
        "complexity": dict(collections.Counter(c for _, c, _ in cx)),
        "c901": sorted(c901, reverse=True),
        "size": {
            "src_files": len(src_sizes),
            "src_lines": sum(r["lines"] for r in src_sizes),
            "over_1300": [
                (r["file"], r["lines"]) for r in src_sizes if r["lines"] > 1300
            ],
            "longest": longest_functions(root, 5),
            "test_files": len(test_sizes),
            "test_lines": sum(r["lines"] for r in test_sizes),
            "largest_test": test_sizes[0] if test_sizes else None,
        },
        "imports": imports(root, mods),
    }


def pct(s: int, m: int) -> float:
    return 100.0 * (s - m) / s if s else 100.0


def cell(sm: tuple) -> str:
    return f"{sm[0]:,} / {sm[1]:,} / {pct(*sm):.1f}%"


def table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def compare_coverage(base: dict, head: dict, families: dict) -> str:
    bm, hm = base["modules"], head["modules"]
    out, claimed = [], set()
    rows = []
    for old, parts in families.items():
        members = [
            f
            for f in hm
            if any(f == x or (x.endswith("/") and f.startswith(x)) for x in parts)
        ]
        claimed |= set(members)
        now = (sum(hm[f][0] for f in members), sum(hm[f][1] for f in members))
        rows.append([f"`{old}`", cell(bm[old]), cell(now), f"{len(members)} modules"])
    if rows:
        out += ["Split modules, as families (statements / missed / cover):", ""]
        out += [table(["Base module", "Base", "Head", "Became"], rows), ""]
    same = [f for f in hm if f in bm and f not in claimed]
    moved = {f: pct(*hm[f]) - pct(*bm[f]) for f in same}
    fell = [f for f in same if moved[f] < -0.05]
    rose = [f for f in same if moved[f] > 0.05]
    out.append(
        f"Same path: {len(same)} modules; {len(rose)} rose, "
        f"{len(same) - len(rose) - len(fell)} unchanged, {len(fell)} fell."
    )
    for f in fell:
        out.append(f"- fell: `{f}` {cell(bm[f])} -> {cell(hm[f])}")
    new = sorted(f for f in hm if f not in bm and f not in claimed)
    if new:
        out.append(f"- new at head, outside any family: {', '.join(new)}")
    lowest = sorted(hm, key=lambda f: pct(*hm[f]))[:10]
    out += ["", "Lowest-covered at head:", ""]
    out += [
        table(["Module", "Cover"], [[f"`{f}`", f"{pct(*hm[f]):.1f}%"] for f in lowest])
    ]

    def now_of(f: str) -> tuple:
        members = [
            g
            for g in claimed
            if f in families
            and any(
                g == x or (x.endswith("/") and g.startswith(x)) for x in families[f]
            )
        ]
        if members:
            return (sum(hm[g][0] for g in members), sum(hm[g][1] for g in members))
        return hm.get(f, (0, 0))

    # As in cleanup-complete:CLEANUP_INVENTORY.md §1.3's list: a module of under 10
    # statements (a package __init__) is left out.
    six = sorted((f for f in bm if bm[f][0] >= 10), key=lambda f: pct(*bm[f]))[:6]
    out += ["", "The base's six lowest-covered (10 or more statements), then and now:"]
    out += [""]
    out += [
        table(
            ["Module", "Base", "Head"],
            [[f"`{f}`", f"{pct(*bm[f]):.1f}%", f"{pct(*now_of(f)):.1f}%"] for f in six],
        )
    ]
    return "\n".join(out)


def report(b: dict, h: dict, cb: dict | None, ch: dict | None, families: dict) -> str:
    out = []

    def pair(label: str, f) -> list:
        return [label, f(b), f(h)]

    rows = [
        pair("`ruff check src/ tests/`", lambda t: t["gate"]["ruff"]),
        pair("`ruff format --check src/ tests/`", lambda t: t["gate"]["format"]),
        pair("`mypy src/`", lambda t: t["gate"]["mypy"]),
    ]
    if cb and ch:
        rows.insert(0, ["Tests", cb["tests"], ch["tests"]])
        rows.insert(1, ["Coverage", cell(cb["total"][:2]), cell(ch["total"][:2])])
    out += ["## The gate", "", table(["Check", "Base", "Head"], rows), ""]
    if cb and ch:
        out += ["## Coverage per module", "", compare_coverage(cb, ch, families), ""]

    def vul(t: dict, k: str) -> str:
        v = t["vulture"][k]
        return (
            "n/a (no whitelist)"
            if v is None
            else f"{v['src'] + v['tests']} (src {v['src']}, tests {v['tests']})"
        )

    def xr(k: str):
        return lambda t: t["xref"][k] if k != "review_list" else len(t["xref"][k])

    out += ["## Dead code", ""]
    out += [
        table(
            ["Measure", "Base", "Head"],
            [
                pair("vulture, no whitelist", lambda t: vul(t, "raw")),
                pair(
                    "vulture, with `vulture_whitelist.py`",
                    lambda t: vul(t, "whitelisted"),
                ),
                pair(
                    "ruff F401/F811/F841/ARG, `src/`",
                    lambda t: sum(t["arg"]["src/"].values()),
                ),
                pair(
                    "ruff F401/F811/F841/ARG, `tests/`",
                    lambda t: sum(t["arg"]["tests/"].values()),
                ),
                pair("Top-level definitions", xr("definitions")),
                pair("No reference outside own file", xr("zero")),
                pair("  of which private", xr("zero_private")),
                pair("  of which public", xr("zero_public")),
                pair("  public: Dash callbacks", xr("zero_public_callbacks")),
                pair("  public: the review list", xr("review_list")),
                pair("Referenced only from tests/evals/scripts", xr("test_only")),
            ],
        ),
        "",
        "Head's remaining vulture lines (whitelisted run):",
        "",
    ]
    wl = h["vulture"]["whitelisted"] or h["vulture"]["raw"]
    out += [f"    {ln}" for ln in wl["lines"]]
    out += ["", "Head's review list: " + ", ".join(h["xref"]["review_list"]), ""]
    keys = ["DEP001 own", "DEP001 evals", "DEP001 other", "DEP002", "DEP003", "DEP004"]
    out += ["## Dependencies", ""]
    out += [
        table(
            ["deptry", "Base", "Head"],
            [
                [k, b["deptry"]["counts"].get(k, 0), h["deptry"]["counts"].get(k, 0)]
                for k in keys
            ]
            + [["Total", b["deptry"]["total"], h["deptry"]["total"]]],
        ),
        "",
        "Head's findings other than the project's own imports and evals/ siblings:",
        "",
    ]
    out += [f"    {ln}" for ln in h["deptry"]["listed"]]
    rules = sorted(set(b["complexity"]) | set(h["complexity"]))
    out += ["", "## Complexity and size", ""]
    out += [
        table(
            ["Rule (noqa ignored)", "Base", "Head"],
            [[r, b["complexity"].get(r, 0), h["complexity"].get(r, 0)] for r in rules]
            + [["Total", sum(b["complexity"].values()), sum(h["complexity"].values())]],
        ),
        "",
        "Over C901's threshold at head: "
        + ", ".join(f"{n} {name}" for n, name in h["c901"]),
        "",
    ]

    def size(t: dict) -> dict:
        return t["size"]

    out += [
        table(
            ["", "Base", "Head"],
            [
                pair(
                    "`src/spec4/`",
                    lambda t: (
                        f"{size(t)['src_files']} files, {size(t)['src_lines']:,} lines"
                    ),
                ),
                pair(
                    "Files over 1,300 lines",
                    lambda t: (
                        ", ".join(f"`{f}` {n:,}" for f, n in size(t)["over_1300"])
                        or "none"
                    ),
                ),
                pair(
                    "Longest functions",
                    lambda t: ", ".join(
                        f"`{name}` {n}" for n, name in size(t)["longest"]
                    ),
                ),
                pair(
                    "`tests/`",
                    lambda t: (
                        f"{size(t)['test_files']} files, "
                        f"{size(t)['test_lines']:,} lines"
                    ),
                ),
                pair(
                    "Largest test file",
                    lambda t: (
                        f"`{size(t)['largest_test']['file']}` "
                        f"{size(t)['largest_test']['lines']:,} lines, "
                        f"{size(t)['largest_test']['functions']} functions"
                    ),
                ),
            ],
        ),
        "",
        "## The import graph and module state",
        "",
    ]

    def imp(k: str):
        return lambda t: t["imports"][k]

    out += [
        table(
            ["", "Base", "Head"],
            [
                pair("Modules", imp("modules")),
                pair(
                    "Cycles",
                    lambda t: (
                        "; ".join(" <-> ".join(c) for c in t["imports"]["cycles"]) or 0
                    ),
                ),
                pair(
                    "Layer violations", lambda t: len(t["imports"]["layer_violations"])
                ),
                pair(
                    "Importers of `llm` / `project_manager`",
                    lambda t: (
                        f"{t['imports']['importers_llm']} / "
                        f"{t['imports']['importers_project_manager']}"
                    ),
                ),
                pair("TYPE_CHECKING-only edges", imp("typing_only")),
                pair("`global` statements", imp("globals")),
            ],
        ),
        "",
        "Lazy couplings at head: " + ", ".join(h["imports"]["lazy"]),
    ]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 0's measurements on two trees.")
    ap.add_argument("base")
    ap.add_argument("head")
    ap.add_argument("--cov-base", type=pathlib.Path, help="the base's coverage output")
    ap.add_argument("--cov-head", type=pathlib.Path, help="the head's coverage output")
    ap.add_argument(
        "--run-coverage",
        type=pathlib.Path,
        metavar="DIR",
        help="run the suite in each export without a coverage file",
    )
    ap.add_argument("--families", type=pathlib.Path, help="split lineage, JSON")
    ap.add_argument("--json", type=pathlib.Path, help="write every measurement here")
    a = ap.parse_args()
    # Keys starting with an underscore (`_about`) document the file, not modules.
    raw = json.loads(a.families.read_text()) if a.families else {}
    families = {k: v for k, v in raw.items() if not k.startswith("_")}
    work = pathlib.Path(tempfile.mkdtemp(prefix="remeasure_"))
    try:
        trees = {
            rev: export(rev, work / rev.replace("/", "_")) for rev in (a.base, a.head)
        }
        found = {rev: measure(root) for rev, root in trees.items()}
        cov = {}
        for rev, given in ((a.base, a.cov_base), (a.head, a.cov_head)):
            if given is None and a.run_coverage:
                a.run_coverage.mkdir(parents=True, exist_ok=True)
                given = coverage_run(trees[rev], rev, a.run_coverage)
            cov[rev] = coverage(given) if given else None
    finally:
        shutil.rmtree(work)
    b, h = found[a.base], found[a.head]
    print(f"# Phase 0's measurements: {a.base} (base) against {a.head} (head)\n")
    print(report(b, h, cov[a.base], cov[a.head], families))
    if a.json:
        a.json.write_text(json.dumps({"base": b, "head": h, "coverage": cov}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
