"""Mutation harness (§60.5, §60.6): anchored edits, a full run, a verified restore.

    uv run python scripts/cleanup/mutate.py CASES.json CASE
    uv run python scripts/cleanup/mutate.py CASES.json CASE \\
        --trace BASE.json[,BASE2.json,...] --basetemp DIR --out NEW.json

A case (data/cases_7q.json holds 7q's) is a label, a list of edits, each
{file, anchor, replacement}, and a prediction. Each anchor must match exactly once, on
the text as the case's earlier edits left it. A case that does not is refused before
anything is written.

The verdict depends on what the case predicts:
  "fail" / "pass"  the suite verdict. The full suite runs. Every "fail" test must fail
                   and every "pass" test must pass. Any other failure is listed, to be
                   explained (§60.6's amended failure condition).
  "diverge"        the trace verdict, as in 7q0's probes. The full suite runs under
                   trace_identity.py with the baselines' --basetemp, and trace_diff.py
                   compares the run with them. Every "diverge" test must diverge.
                   Others that diverge are listed as observed.

The harness writes to src/ and tests/, so it guards both ends of the run:
  before  it refuses to start unless `git status --porcelain` is empty, so the case's
          edits are the only change on disk while the suite runs;
  after   every edited file is restored from the bytes saved before the edit, and its
          sha256 is compared with the one taken then. The tree must then be clean
          again. The restore runs in a `finally`, and SIGTERM and SIGHUP are turned
          into an exit so it runs for them too. The suite runs in its own process
          group, killed whole on any exit, so nothing of it outlives the harness.
Exit 0 as predicted; 1 a wrong prediction; 2 refused, nothing written; 3 the restore
could not be verified. A mutation left half-applied is a worse artifact than none.
"""

import argparse
import contextlib
import hashlib
import json
import os
import pathlib
import re
import signal
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent


def refuse(msg: str) -> None:
    print(f"REFUSED: {msg}", file=sys.stderr)
    sys.exit(2)


def status() -> str:
    return subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
    ).stdout


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _exit(signum: int, frame: object) -> None:
    raise SystemExit(128 + signum)


def run_suite(cmd: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    """Run the suite in its own process group, and kill the whole group on any exit.

    subprocess.run would kill only its direct child. A signal that stops the harness
    must also stop what the suite started, such as a test's server subprocess.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate()
    except BaseException:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def edited(case: dict) -> dict[pathlib.Path, bytes]:
    """Each file's mutated bytes, computed in full before anything is written."""
    texts: dict[pathlib.Path, str] = {}
    for i, e in enumerate(case["edits"]):
        p = pathlib.Path(e["file"])
        t = texts[p] if p in texts else p.read_bytes().decode()
        n = t.count(e["anchor"])
        if n != 1:
            refuse(f"edit {i}'s anchor matched {n} times in {p}, not once")
        texts[p] = t.replace(e["anchor"], e["replacement"])
    return {p: t.encode() for p, t in texts.items()}


def last_summary(stdout: str) -> str:
    lines = [ln for ln in stdout.splitlines() if re.search(r"\d+ (passed|failed)", ln)]
    return lines[-1] if lines else "?"


def suite_verdict(name: str, case: dict, run: subprocess.CompletedProcess) -> bool:
    predicted, must_pass = case["fail"], case.get("pass", [])
    failed = sorted(set(re.findall(r"^FAILED (\S+)", run.stdout, re.M)))
    hit = [t for t in predicted if t in failed]
    missed = [t for t in predicted if t not in failed]
    broke = [t for t in must_pass if t in failed]
    others = [f for f in failed if f not in predicted]
    ok = not missed and not broke and bool(hit)
    print(
        f"M {name} ({case['label']}): predicted {len(predicted)}, failed {len(hit)}; "
        f"must-pass {len(must_pass)}, failed {len(broke)}; "
        f"{'as predicted' if ok else 'A WRONG PREDICTION'}"
    )
    for t in hit:
        print(f"   FAILED (predicted)       {t}")
    for t in missed:
        print(f"   PASSED (predicted fail)  {t}")
    for t in must_pass:
        print(f"   {'FAILED' if t in broke else 'PASSED'} (must pass)       {t}")
    for t in others:
        print(f"   FAILED (other, to explain) {t}")
    print(f"   other failures: {len(others)}")
    print(f"   summary: {last_summary(run.stdout)}")
    return ok


def trace_verdict(
    name: str, case: dict, run: subprocess.CompletedProcess, a: argparse.Namespace
) -> bool:
    diff = subprocess.run(
        [sys.executable, str(HERE / "trace_diff.py"), a.trace, a.out, "--list"],
        capture_output=True,
        text=True,
    )
    if diff.returncode not in (0, 1):
        print(f"trace_diff.py failed (exit {diff.returncode}):\n{diff.stderr}")
        return False
    diverged = {
        ln.split("DIVERGES ", 1)[1].split(": ", 1)[0]
        for ln in diff.stdout.splitlines()
        if "DIVERGES " in ln
    }
    predicted = case["diverge"]
    missed = sorted(set(predicted) - diverged)
    ok = not missed and bool(diverged)
    print(
        f"probe {name} ({case['label']}): "
        f"{'as predicted' if ok else 'A WRONG PREDICTION'}"
    )
    print(f"  suite under the probe: {last_summary(run.stdout)}")
    print(
        f"  traces diverging: {len(diverged)}; predicted {len(predicted)}, of which "
        f"diverged {len(set(predicted) & diverged)}; predicted but NOT diverging: "
        f"{missed or 'none'}"
    )
    for ln in diff.stdout.splitlines():
        if ln.startswith("tests traced"):
            print("  " + ln)
    for t in sorted(diverged):
        print(f"   {'PREDICTED' if t in predicted else 'observed '}  {t}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Mutation harness; see the module docstring."
    )
    ap.add_argument(
        "cases", help="a cases file, e.g. scripts/cleanup/data/cases_7q.json"
    )
    ap.add_argument("case", help="the case's name in that file")
    ap.add_argument("--trace", help="baseline trace file(s), comma-separated")
    ap.add_argument(
        "--basetemp", help="the --basetemp the baselines were recorded with"
    )
    ap.add_argument("--out", help="where the traced run is written, outside the repo")
    a = ap.parse_args()
    cases = json.loads(pathlib.Path(a.cases).read_text())["cases"]
    if a.case not in cases:
        refuse(f"no case {a.case!r}; the file has {sorted(cases)}")
    case = cases[a.case]
    root = pathlib.Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    os.chdir(root)
    # The suite runs as sys.executable -m pytest, in its own process group (run_suite).
    cmd = [sys.executable, "-m", "pytest", "-q", "-rf", "-p", "no:cacheprovider"]
    env = dict(os.environ)
    if "diverge" in case:
        if not (a.trace and a.basetemp and a.out):
            refuse("a 'diverge' case needs --trace, --basetemp and --out")
        for path in (a.out, a.basetemp):
            if pathlib.Path(path).resolve().is_relative_to(root):
                refuse(f"{path} is inside the repo; the run must leave the tree clean")
        cmd = [sys.executable, "-m", "pytest", "-p", "trace_identity", "-q"]
        cmd += ["-p", "no:cacheprovider", f"--basetemp={a.basetemp}"]
        env.update(
            TRACE_OUT=str(pathlib.Path(a.out).resolve()),
            PYTHONHASHSEED="0",
            PYTHONPATH=str(HERE),
            PYTHONDONTWRITEBYTECODE="1",
        )
    if dirty := status():
        refuse(
            f"the tree is not clean; the case's edits must be the only change:\n{dirty}"
        )
    new = edited(case)
    saved = {p: p.read_bytes() for p in new}
    digests = {p: sha(b) for p, b in saved.items()}
    signal.signal(signal.SIGTERM, _exit)
    signal.signal(signal.SIGHUP, _exit)
    try:
        for p, b in new.items():
            p.write_bytes(b)
        run = run_suite(cmd, env)
    finally:
        for p, b in saved.items():
            p.write_bytes(b)
        restored = all(sha(p.read_bytes()) == digests[p] for p in saved)
        left = status()
        if not restored or left:
            print(
                f"RESTORE NOT VERIFIED: sha256 {'matches' if restored else 'DIFFERS'}; "
                f"the tree after the restore:\n{left or '(clean)'}",
                file=sys.stderr,
            )
            sys.exit(3)
        print(f"restore: {len(saved)} file(s) byte-identical by sha256; tree clean")
    if "diverge" in case:
        ok = trace_verdict(a.case, case, run, a)
    else:
        ok = suite_verdict(a.case, case, run)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
