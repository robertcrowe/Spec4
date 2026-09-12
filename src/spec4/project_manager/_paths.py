"""Where a Spec4 artifact lives: the ``.spec4/`` directory helpers and the
phase-set versioning that decides which round a read or a write targets.

Split out of :mod:`spec4.project_manager` in cleanup Phase 4b; that module
re-exports every name defined here, so both import paths resolve to the same
object.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, NamedTuple

from spec4.app_constants import PROJECT_MODE_EXISTING


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------


def get_spec4_dir(working_dir: str | Path) -> Path:
    return Path(working_dir) / ".spec4"


def ensure_spec4_dir(working_dir: str | Path) -> Path:
    d = get_spec4_dir(working_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_version_dir(working_dir: str | Path, version: int) -> Path:
    """Return ``.spec4/v{version}`` — the per-round artifact root.

    Every artifact for a round (vision, stack, code_review, ai_*, design/,
    phases/, deployment-plan, the IMPLEMENTED marker) lives under this
    directory. Each version is self-contained; lower versions are prior,
    implemented rounds.
    """
    return get_spec4_dir(working_dir) / f"v{version}"


def ensure_version_dir(working_dir: str | Path, version: int) -> Path:
    d = get_version_dir(working_dir, version)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Phase-set versioning
# ---------------------------------------------------------------------------

_PHASE_VERSION_RE = re.compile(r"^v(\d+)$")


def _phase_version_dirs(working_dir: str | Path) -> dict[int, Path]:
    """Map version number -> existing ``.spec4/v{N}`` directory."""
    spec4_dir = get_spec4_dir(working_dir)
    out: dict[int, Path] = {}
    if spec4_dir.is_dir():
        for d in spec4_dir.iterdir():
            m = _PHASE_VERSION_RE.match(d.name)
            if m and d.is_dir():
                out[int(m.group(1))] = d
    return out


def latest_phase_version(working_dir: str | Path) -> int | None:
    """Highest existing phase-set version, or None when no version dirs exist."""
    dirs = _phase_version_dirs(working_dir)
    return max(dirs) if dirs else None


def latest_implemented_version(working_dir: str | Path) -> int | None:
    """Highest version whose ``.spec4/v{N}/`` holds an ``IMPLEMENTED`` marker.

    This is the most recent *completed* round — the round whose vision is the
    established product identity a new revision builds on. It differs from
    ``latest_phase_version`` (which returns the highest dir regardless of
    completion): once a new round's ``v{N+1}`` dir exists but is not yet
    implemented, the latest phase version is ``N+1`` while the latest
    *implemented* version is still ``N``. Returns ``None`` when no round has
    been implemented.
    """
    dirs = _phase_version_dirs(working_dir)
    implemented = [v for v, d in dirs.items() if (d / "IMPLEMENTED").exists()]
    return max(implemented) if implemented else None


def active_version(
    working_dir: str | Path, session: dict[str, Any] | None = None
) -> int:
    """Return the version to read/write artifacts for the current round.

    Prefers the session's pinned ``phase_version`` (set once at flow start);
    falls back to the latest on-disk version directory, then ``0``. Used by the
    design-path reads/writes that need the active round but do not themselves
    drive the persist funnel (which pins the version). This is a read helper —
    it never resolves a *new* round; that is the persist funnel's job.
    """
    if session is not None:
        v = session.get("phase_version")
        if v is not None:
            return int(v)
    return latest_phase_version(working_dir) or 0


class RoundsOnDisk(NamedTuple):
    """Every round the project has on disk, and which one is active.

    ``rounds`` is ascending by round number, which is not what
    ``Path.iterdir`` gives back and not what a lexicographic sort of the
    directory names gives either — ``v10`` sorts before ``v9`` as text, and a
    round selector listing the rounds in that order would be quietly wrong the
    first time a project reached ten rounds.

    ``active`` is the round the rest of the app considers current, and it is
    ``None`` only when there is no round at all. It can name a round that is
    *not* in ``rounds``: a session pins ``phase_version`` at flow start, and
    the directory for that round is not created until the first agent persists
    an artifact into it. A caller populating a selector should fall back to the
    highest entry in ``rounds`` when ``active`` is not among them, rather than
    offering a value its own option list does not contain.
    """

    rounds: tuple[int, ...]
    active: int | None


def rounds_on_disk(
    working_dir: str | Path | None, session: dict[str, Any] | None = None
) -> RoundsOnDisk:
    """The rounds present under ``.spec4/``, recomputed from disk every call.

    Nothing here is memoised and nothing is stashed in a store. That is the
    whole point of the function rather than an oversight: a round created since
    the screen was last drawn — by the persist funnel, or by the developer
    running a new round in another tab — has to appear the next time the
    selector is built, with no restart and no cache to invalidate.

    ``session`` is threaded through to :func:`active_version` so that the
    active round reported here is the same one the status bar and the round
    tree are showing. Reading it from disk alone would disagree with both
    whenever a session is pinned to an earlier round than the newest folder,
    and the Artifact View would then default its selector to one round while
    drawing the tree of another.
    """
    if not working_dir:
        return RoundsOnDisk((), None)
    rounds = tuple(sorted(_phase_version_dirs(working_dir)))
    if not rounds:
        return RoundsOnDisk((), None)
    return RoundsOnDisk(rounds, active_version(working_dir, session))


def session_is_brownfield(session: dict[str, Any] | None) -> bool:
    """Whether this round modifies a codebase that already existed (D-PM1).

    The developer's own answer, from the session, is the only thing that
    establishes this. It is deliberately *not* inferred from a code review on
    disk: running CodeScanner over a greenfield skeleton is a normal thing to
    do and says nothing about whether the project pre-existed Spec4 — the same
    reasoning ``needs_project_mode`` sets out. Treating a scan as proof of
    brownfield is what used to push a greenfield project's first round into
    ``v1``.

    Unanswered (an empty directory never asks) reads as greenfield.
    """
    return bool(session and session.get("project_mode") == PROJECT_MODE_EXISTING)


def resolve_phase_version(
    working_dir: str | Path, is_brownfield: bool
) -> tuple[int, bool]:
    """Resolve the active version for the current flow.

    Returns ``(version, is_greenfield)``. A round counts as implemented once its
    ``.spec4/v{N}/`` directory holds an ``IMPLEMENTED`` marker (the coding agent
    touches it after finishing the round's last phase). This is resolved once at
    flow start (the first agent that persists an artifact) and pinned in the
    session; every artifact for the round is then written under that version.

    - No version dirs: ``v0`` greenfield; ``v1`` brownfield, where ``v0`` stands
      for the implementation that existed before Spec4 saw the project, so the
      first round Spec4 defines is the one after it. ``is_brownfield`` is the
      developer's answer (:func:`session_is_brownfield`), never a guess from
      what happens to be on disk.
    - Highest version dir lacks ``IMPLEMENTED``: the in-progress round — target
      it (it is being defined/overwritten). ``is_greenfield`` iff it is ``v0``.
    - Highest version dir is implemented: a new brownfield round — ``max + 1``.
    """
    dirs = _phase_version_dirs(working_dir)
    if not dirs:
        return (1, False) if is_brownfield else (0, True)
    highest = max(dirs)
    if (dirs[highest] / "IMPLEMENTED").exists():
        return highest + 1, False
    return highest, highest == 0
