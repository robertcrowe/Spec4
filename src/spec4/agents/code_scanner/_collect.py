"""The code-owned ``scan`` layer: what CodeScanner can *measure* about a tree.

Everything here is computed, never LLM-edited or LLM-visible (D-EV2/D-EV4):
``collect_scan`` runs after the walk, its result is stashed in the session
under ``code_scanner_scan`` until the model's ``review`` block is committed,
and ``_scanner_commit`` merges the two into the stored envelope. Step 1b of
the CodeScanner v2 plan ships three blocks:

- ``inventory`` — the exhaustive census of the walked tree: file and line
  counts per extension, the first ``_MAX_LISTED`` paths, and the directories
  the walk pruned (``unscanned_dirs``), so a consumer can tell "not there"
  from "not looked at".
- ``coverage`` — what the seed actually showed the model, from the
  ``SampleRecord`` the formatters in ``_scan`` fill while pasting
  (D-SC1b-4): one source of truth for the sampling, no second derivation.
- ``git`` — present only when the project root *is* a repository top-level
  (a ``.git`` entry at the root; D-SC1b-5): head, branch, cleanliness, the
  commits since the last Spec4 round, and the last commit per top-level
  directory. Author names only, never emails (D-SC1b-6). Dormancy is a
  judgment and is not classified here — step 3 derives it from
  ``activity.last_commit_per_top_dir`` once it knows what it needs.

Step 1c adds ``module_graph`` and ``signatures``, computed in ``_graph`` and
assembled here. Step 1d adds ``dependencies`` (``_manifests``), ``prior_round``
(``_prior``), ``plan_drift`` (``_drift``) and ``delta`` (``_delta``), and
gives ``git`` a ``working_tree`` block with Spec4's own ``.spec4/`` output
excluded from the dirty and untracked counts (D-SC1d-8).

``_run_git`` is the one seam to the ``git`` binary, and the first subprocess
call in Spec4. Tests patch it by name (AGENTS.md: the module-level seam, not
``subprocess.run``); every failure mode — no binary, a timeout, a non-zero
exit — resolves to ``None`` and from there to ``{"available": False}``, so a
scan never fails because ``git`` did.
"""

from __future__ import annotations

import collections
import datetime
import os
import pathlib
import re
import subprocess
from typing import TYPE_CHECKING, Any

from spec4 import project_manager
from spec4.agents.code_scanner._delta import delta_block, prior_scan
from spec4.agents.code_scanner._drift import plan_drift_block
from spec4.agents.code_scanner._graph import module_graph_block, signatures_block
from spec4.agents.code_scanner._manifests import dependencies_block
from spec4.agents.code_scanner._prior import prior_round_block
from spec4.agents.code_scanner._scan import _SKIP_DIRS, SampleRecord
from spec4.app_constants import ARTIFACT_CODE_REVIEW

if TYPE_CHECKING:
    from collections.abc import Iterable


_MAX_LISTED = 2_000
_MAX_LOC_FILE_BYTES = 2_000_000
_BINARY_SNIFF_BYTES = 8_192
_MAX_LOG_COMMITS = 500
_GIT_TIMEOUT_SECONDS = 10
_NO_EXTENSION = "(none)"
_ROOT_DIR = "."
_SPEC4_DIR = ".spec4"
_UNTRACKED_CODE = "??"
_STATUS_CODE_WIDTH = 2  # porcelain v1: two status columns, a space, the path

# Record and unit separators keep ``git log`` parseable whatever a commit
# message holds; ``%(trailers)`` is the raw trailer block, matched below.
_LOG_FORMAT = "%x1e%H%x1f%an%x1f%aI%x1f%(trailers)%x1f"
_RECORD_SEP = "\x1e"
_UNIT_SEP = "\x1f"

# Evidence only (plan 1b): a trailer naming a coding agent says a commit
# *may* have been agent-authored, nothing more. Hand-vs-agent is not
# classified anywhere in v2 (step 4 keeps to timestamp boundaries).
_AGENT_TRAILER_RE = re.compile(
    r"(?i)\b(claude|codex|copilot|cursor|aider|devin|anthropic|openai|spec4)\b"
)


def _rel(root: pathlib.Path, path: pathlib.Path) -> str:
    return path.relative_to(root).as_posix()


# ---------------------------------------------------------------------------
# inventory
# ---------------------------------------------------------------------------


def _measure_lines(path: pathlib.Path) -> int | None:
    """Line count of a text file; ``None`` for binary, oversized, or unreadable.

    Reads bytes and counts newlines rather than decoding — the census runs over
    every file in the tree, and decoding is the expensive part. A NUL in the
    first ``_BINARY_SNIFF_BYTES`` marks a binary.
    """
    try:
        if path.stat().st_size > _MAX_LOC_FILE_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:_BINARY_SNIFF_BYTES]:
        return None
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def _pruned_dirs(root: pathlib.Path) -> list[str]:
    """Root-relative paths of every directory the walk skips.

    ``collect_files`` prunes by path part; this walk prunes the same names
    top-down and records each one, so a tree with three ``node_modules`` lists
    all three. ``collect_files`` itself is untouched (its output is pinned).
    """
    pruned: list[str] = []
    for dirpath, dirnames, _ in os.walk(root):
        keep: list[str] = []
        for name in sorted(dirnames):
            if name in _SKIP_DIRS:
                pruned.append(_rel(root, pathlib.Path(dirpath) / name))
            else:
                keep.append(name)
        dirnames[:] = keep
    return pruned


def inventory_block(
    root: pathlib.Path, all_files: list[pathlib.Path]
) -> dict[str, Any]:
    """The exhaustive census of the walked tree (plan 1b ``inventory``)."""
    by_ext: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: {"files": 0, "loc": 0, "unmeasured": 0}
    )
    for f in all_files:
        entry = by_ext[f.suffix or _NO_EXTENSION]
        entry["files"] += 1
        loc = _measure_lines(f)
        if loc is None:
            entry["unmeasured"] += 1
        else:
            entry["loc"] += loc
    listed = [_rel(root, f) for f in all_files[:_MAX_LISTED]]
    return {
        "files_total": len(all_files),
        "files_listed": len(listed),
        "truncated": len(all_files) > _MAX_LISTED,
        "loc_total": sum(e["loc"] for e in by_ext.values()),
        "by_extension": dict(sorted(by_ext.items())),
        "listed": listed,
        "unscanned_dirs": _pruned_dirs(root),
    }


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------


def coverage_block(record: SampleRecord) -> dict[str, Any]:
    """What the seed showed the model, from the formatters' own ledger."""
    return {
        "tree_listed": record.tree_listed,
        "tree_truncated": record.tree_truncated,
        "readme": record.readme,
        "manifests": list(record.manifests),
        "ci": list(record.ci),
        "deploy": list(record.deploy),
        "sampled": list(record.sampled),
        "source_files_total": record.source_files_total,
        "source_files_sampled": len(record.sampled),
    }


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------


def _run_git(args: list[str], cwd: pathlib.Path) -> str | None:
    """Run ``git`` in ``cwd``; stdout on success, ``None`` on any failure.

    The seam for tests. ``LC_ALL=C`` keeps output parseable; the optional-locks
    switch stops ``status`` from touching the index of a tree we only read.
    """
    env = {**os.environ, "LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0"}
    try:
        done = subprocess.run(
            ["git", "--no-pager", *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout


def is_repo_root(root: pathlib.Path) -> bool:
    """True when ``root`` is itself a repository top-level (D-SC1b-5).

    A ``.git`` directory, or the ``.git`` *file* a worktree or submodule
    checkout carries. A project that is a subdirectory of a larger repository
    gets no ``git`` block: its per-directory counts would describe the wrong
    tree.
    """
    return (root / ".git").exists()


def round_boundary(
    working_dir: str, session: dict[str, Any] | None
) -> tuple[str, float] | None:
    """When the last Spec4 round ended, for ``git.since_last_round``.

    After the ``IMPLEMENTED`` marker of the latest implemented round; else
    after the active round's ``code_review.json`` (the prior scan this one
    replaces); else absent — a first scan has no "since".
    """
    implemented = project_manager.latest_implemented_version(working_dir)
    if implemented is not None:
        marker = (
            project_manager.get_version_dir(working_dir, implemented) / "IMPLEMENTED"
        )
        mtime = _mtime(marker)
        if mtime is not None:
            return ("implemented", mtime)
    prior = (
        project_manager.get_version_dir(
            working_dir, project_manager.active_version(working_dir, session)
        )
        / ARTIFACT_CODE_REVIEW
    )
    mtime = _mtime(prior)
    if mtime is not None:
        return ("prior_review", mtime)
    return None


def _mtime(path: pathlib.Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _iso(epoch: float) -> str:
    return (
        datetime.datetime.fromtimestamp(epoch, tz=datetime.UTC)
        .replace(microsecond=0)
        .isoformat()
    )


def _top_dir(rel_path: str) -> str:
    head, sep, _ = rel_path.partition("/")
    return head if sep else _ROOT_DIR


def _parse_log(text: str) -> list[dict[str, Any]]:
    """Commits from ``git log --name-only`` under ``_LOG_FORMAT``, newest first."""
    commits: list[dict[str, Any]] = []
    for chunk in text.split(_RECORD_SEP):
        if not chunk.strip():
            continue
        parts = chunk.split(_UNIT_SEP)
        if len(parts) < 5:  # noqa: PLR2004 — the five fields `_LOG_FORMAT` emits
            continue
        sha, author, date, trailers, names = parts[:5]
        files = [line for line in names.splitlines() if line.strip()]
        commits.append(
            {
                "sha": sha.strip(),
                "author": author.strip(),
                "date": date.strip(),
                "trailers": trailers,
                "files": files,
            }
        )
    return commits


def _log(root: pathlib.Path, extra: Iterable[str]) -> list[dict[str, Any]] | None:
    out = _run_git(
        [
            "log",
            f"-n{_MAX_LOG_COMMITS}",
            "--name-only",
            f"--format={_LOG_FORMAT}",
            *extra,
        ],
        root,
    )
    return None if out is None else _parse_log(out)


def _since_last_round(
    root: pathlib.Path, boundary: tuple[str, float]
) -> dict[str, Any] | None:
    kind, epoch = boundary
    commits = _log(root, [f"--since=@{int(epoch)}"])
    if commits is None:
        return None
    touched: collections.Counter[str] = collections.Counter()
    authors: set[str] = set()
    for c in commits:
        authors.add(c["author"])
        for d in {_top_dir(f) for f in c["files"]}:
            touched[d] += 1
    return {
        "boundary_kind": kind,
        "boundary": _iso(epoch),
        "commits": len(commits),
        "truncated": len(commits) >= _MAX_LOG_COMMITS,
        "first": commits[-1]["date"] if commits else None,
        "last": commits[0]["date"] if commits else None,
        "authors": sorted(authors),
        "touched_top_dirs": dict(sorted(touched.items())),
        "agent_trailers_present": any(
            _AGENT_TRAILER_RE.search(c["trailers"]) for c in commits
        ),
    }


def _activity(root: pathlib.Path) -> dict[str, Any] | None:
    commits = _log(root, [])
    if commits is None:
        return None
    last: dict[str, str] = {}
    for c in commits:  # newest first: the first sighting of a dir is its latest
        for d in {_top_dir(f) for f in c["files"]}:
            last.setdefault(d, c["date"])
    return {
        "commits_scanned": len(commits),
        "truncated": len(commits) >= _MAX_LOG_COMMITS,
        "last_commit_per_top_dir": dict(sorted(last.items())),
    }


def _status_path(line: str) -> str:
    """The path of one porcelain status line; a rename's *new* name."""
    path = line[_STATUS_CODE_WIDTH:].strip()
    _, arrow, renamed = path.rpartition(" -> ")
    return renamed if arrow else path


def _status(root: pathlib.Path) -> tuple[list[str], list[str]] | None:
    """``(modified paths, untracked paths)``, Spec4's own output excluded.

    ``--untracked-files=all`` lists files, not collapsed directories, so the
    count is a file count (D-SC1d-8). Anything under ``.spec4/`` is left out
    of both: a round's artifacts are Spec4's record of the project, not a
    change to it, and they are what made every BWS4 scan read as "1
    untracked".
    """
    out = _run_git(["status", "--porcelain", "--untracked-files=all"], root)
    if out is None:
        return None
    modified: list[str] = []
    untracked: list[str] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        path = _status_path(line)
        if path == _SPEC4_DIR or path.startswith(_SPEC4_DIR + "/"):
            continue
        (untracked if line.startswith(_UNTRACKED_CODE) else modified).append(path)
    return modified, untracked


def _top_dir_counts(paths: Iterable[str]) -> dict[str, int]:
    counts = collections.Counter(_top_dir(p) for p in paths)
    return dict(sorted(counts.items()))


def git_block(root: pathlib.Path, boundary: tuple[str, float] | None) -> dict[str, Any]:
    """The ``git`` block for a repository root; see the module docstring.

    ``{"available": False}`` when any of the probes fails — an empty
    repository, no ``git`` on PATH, a timeout.
    """
    head = _run_git(["rev-parse", "--short", "HEAD"], root)
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    status = _status(root)
    activity = _activity(root)
    if head is None or branch is None or status is None or activity is None:
        return {"available": False}
    modified, untracked = status
    block: dict[str, Any] = {
        "available": True,
        "head": head.strip(),
        "branch": branch.strip(),
        "dirty": bool(modified),
        "untracked_count": len(untracked),
        "working_tree": {
            "modified_top_dirs": _top_dir_counts(modified),
            "untracked_top_dirs": _top_dir_counts(untracked),
        },
        "activity": activity,
    }
    if boundary is not None:
        since = _since_last_round(root, boundary)
        if since is not None:
            block["since_last_round"] = since
    return block


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------


def collect_scan(
    working_dir: str,
    all_files: list[pathlib.Path],
    record: SampleRecord,
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The whole ``scan`` layer for one walk; stashed until commit.

    ``git`` is present only for a repository root. ``session`` reaches
    ``active_version`` for the round boundary and the prior scan, and nothing
    else. The graph feeds the signatures: the candidates it ranks are the
    files whose signatures are kept (1c). ``prior_round`` and ``plan_drift``
    are present when a round is implemented; ``delta`` when an earlier 2.x
    scan is on disk to compare against (1d). ``dependencies`` is on every scan,
    since the next scan's ``delta`` reads this one's.
    """
    root = pathlib.Path(working_dir)
    graph = module_graph_block(root, all_files)
    dependencies = dependencies_block(root, all_files)
    scan: dict[str, Any] = {
        "inventory": inventory_block(root, all_files),
        "coverage": coverage_block(record),
        "dependencies": dependencies,
        "module_graph": graph,
        "signatures": signatures_block(root, all_files, graph),
    }
    if is_repo_root(root):
        scan["git"] = git_block(root, round_boundary(working_dir, session))
    prior = prior_round_block(working_dir)
    if prior is not None:
        scan["prior_round"] = prior
        scan["plan_drift"] = plan_drift_block(prior, dependencies, graph)
    found = prior_scan(working_dir, session)
    if found is not None:
        descriptor, earlier = found
        scan["delta"] = delta_block(scan, earlier, descriptor)
    return scan
