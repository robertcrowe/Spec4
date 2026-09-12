"""Project directory management for Spec4.

Handles working directory selection and .spec4 artifact storage.

Cleanup Phase 4b split the four self-contained concerns into siblings, one
module each:

* :mod:`spec4.project_manager._paths` -- where an artifact lives: the
  ``.spec4/`` directory helpers, phase-set versioning, and the rounds on disk.
* :mod:`spec4.project_manager._artifacts` -- reading and writing every
  ``.spec4/`` artifact, plus README assembly.
* :mod:`spec4.project_manager._phase_markdown` -- phase-file assembly and parsing.
* :mod:`spec4.project_manager._usage` -- the LLM usage log and the cost rollup.

Staleness detection and agent-select button state stay here: both are decided
from artifact mtimes across the whole pipeline rather than from any one
concern, so they read the other four rather than belonging to one of them.

Phase 4j then moved every importer onto the owning module and dropped the
re-exports nothing reached through here, so what is listed below is exactly
the set some importer outside the owning module still needs. ``__all__`` is
load-bearing rather than decorative: ``[tool.mypy] strict`` implies
``no_implicit_reexport``, so without it a re-exported name could not be
imported from this module at all.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from spec4.app_constants import (
    ARTIFACT_AI_FEATURES,
    ARTIFACT_CODE_REVIEW,
    ARTIFACT_FEATURE_SPECS,
    ARTIFACT_STACK,
    ARTIFACT_VISION,
    PROJECT_MODES,
)

from spec4.project_manager._artifacts import (
    load_ai_catalog,
    load_ai_features,
    load_deployment_plan,
    load_design_manifest,
    load_existing_readme,
    load_feature_specs,
    load_prior_ai_features,
    load_prior_deployment_plan,
    load_prior_mock,
    load_prior_stack,
    load_prior_vision,
    load_spec4_artifacts,
    load_vision,
    merge_library_additions,
    save_ai_catalog,
    save_ai_features,
    save_code_review,
    save_deployment_plan,
    save_feature_specs,
    save_phases,
    save_readme,
    save_stack,
    save_vision,
    SPEC4_README_ATTRIBUTION,
    _with_readme_attribution,
    _write_text_if_changed,
)
from spec4.project_manager._paths import (
    active_version,
    ensure_spec4_dir,
    ensure_version_dir,
    get_spec4_dir,
    get_version_dir,
    latest_implemented_version,
    latest_phase_version,
    resolve_phase_version,
    rounds_on_disk,
    session_is_brownfield,
)
from spec4.project_manager._phase_markdown import (
    parse_phase_markdown,
    _phase_spec_preamble,
    render_phase_markdown,
)
from spec4.project_manager._usage import (
    cost_summary,
    load_usage,
    round_cost,
    save_usage,
    summarize_usage,
    unpriced_calls,
    USAGE_FILENAME,
    _USAGE_ROLLUP_PARENT,
    usage_totals,
)

__all__ = [
    "active_version",
    "AGENT_BTN_CONTINUE",
    "AGENT_BTN_MODIFY",
    "AGENT_BTN_NEEDS_UPDATE",
    "AGENT_BTN_NOT_READY",
    "AGENT_BTN_REQUIRED",
    "AGENT_BTN_START",
    "agent_button_state",
    "_artifact_button_state",
    "brownfield_new_round_pending",
    "cost_summary",
    "detect_stale_inputs",
    "directory_has_content",
    "directory_opens",
    "ensure_spec4_dir",
    "ensure_version_dir",
    "get_spec4_dir",
    "get_version_dir",
    "_has_transcript",
    "latest_implemented_version",
    "latest_phase_version",
    "load_ai_catalog",
    "load_ai_features",
    "load_deployment_plan",
    "load_design_manifest",
    "load_existing_readme",
    "load_feature_specs",
    "load_prior_ai_features",
    "load_prior_deployment_plan",
    "load_prior_mock",
    "load_prior_stack",
    "load_prior_vision",
    "load_spec4_artifacts",
    "load_usage",
    "load_vision",
    "merge_library_additions",
    "needs_project_mode",
    "_NON_ARTIFACT_FILES",
    "parse_phase_markdown",
    "_path_mtime",
    "_phase_spec_preamble",
    "_PIPELINE_ARTIFACT_ORDER",
    "render_phase_markdown",
    "_REQUIRED_INPUTS",
    "resolve_phase_version",
    "round_cost",
    "rounds_on_disk",
    "save_ai_catalog",
    "save_ai_features",
    "save_code_review",
    "save_deployment_plan",
    "save_feature_specs",
    "save_phases",
    "save_readme",
    "save_stack",
    "save_usage",
    "save_vision",
    "session_is_brownfield",
    "SPEC4_README_ATTRIBUTION",
    "_STALE_DEPENDENCIES",
    "summarize_usage",
    "unpriced_calls",
    "USAGE_FILENAME",
    "_USAGE_ROLLUP_PARENT",
    "usage_totals",
    "_with_readme_attribution",
    "_write_text_if_changed",
]


# ---------------------------------------------------------------------------
# Staleness detection
# ---------------------------------------------------------------------------

# Maps each agent to (output artifact rel path, [(input name, input rel path)…]).
# Output and input paths are relative to .spec4/. A directory is treated as the
# newest mtime among its files.
# Files that live in ``.spec4/v{N}/`` but are NOT pipeline artifacts: written
# by the pipeline for the developer's benefit, read by no agent, and therefore
# never a dependency edge. The freshness graph below is declared by explicit
# filename, so this set is the declared exclusion — a name in it must never be
# added to ``_STALE_DEPENDENCIES`` or ``_PIPELINE_ARTIFACT_ORDER`` (a test
# enforces that), and touching one of these files cannot flip any agent to
# Needs Update.
_NON_ARTIFACT_FILES: frozenset[str] = frozenset({USAGE_FILENAME})

_STALE_DEPENDENCIES: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "brainstormer": (ARTIFACT_VISION, [("code review", ARTIFACT_CODE_REVIEW)]),
    "agentifier": (
        ARTIFACT_AI_FEATURES,
        [("vision", ARTIFACT_VISION), ("code review", ARTIFACT_CODE_REVIEW)],
    ),
    # StackAdvisor depends on Designer's *manifest* (the data model and screen
    # structure), not the visual mock: a purely visual change cannot invalidate a
    # stack choice, and inlining the mock's markup only crowded the context
    # (D-SC5c). The mock remains Phaser's and Deployer's dependency — they hand it
    # to the coding agent.
    "stack_advisor": (
        ARTIFACT_STACK,
        [
            ("vision", ARTIFACT_VISION),
            ("AI features", ARTIFACT_AI_FEATURES),
            ("code review", ARTIFACT_CODE_REVIEW),
            ("design manifest", "design/manifest.json"),
        ],
    ),
    "phaser": (
        "phases",
        [
            ("vision", ARTIFACT_VISION),
            ("AI features", ARTIFACT_AI_FEATURES),
            ("stack", ARTIFACT_STACK),
            ("code review", ARTIFACT_CODE_REVIEW),
            ("UI mock", "design/mock.html"),
        ],
    ),
    # Deployer reads `feature_specs.json` for the project's non-functional goals
    # (D-DE6), so an edit to it can invalidate a deployment plan. Note this is
    # tracked by `detect_stale_inputs` (the in-conversation staleness prompt) but
    # not yet by `agent_button_state`, which only considers inputs listed in
    # `_PIPELINE_ARTIFACT_ORDER` — feature_specs.json is absent from that list
    # pipeline-wide, which is a broader reconciliation than this entry.
    "deployer": (
        "deployment-plan.md",
        [
            ("AI features", ARTIFACT_AI_FEATURES),
            ("stack", ARTIFACT_STACK),
            ("feature specs", ARTIFACT_FEATURE_SPECS),
            ("phases", "phases"),
            ("UI mock", "design/mock.html"),
        ],
    ),
    "designer": (
        "design/mock.html",
        [("vision", ARTIFACT_VISION), ("AI features", ARTIFACT_AI_FEATURES)],
    ),
}


def _path_mtime(path: Path) -> float | None:
    """Return the most recent mtime at `path`. None if missing.

    For a directory, returns the newest mtime among its files (recursive).
    """
    if not path.exists():
        return None
    if path.is_file():
        return path.stat().st_mtime
    mtimes = [p.stat().st_mtime for p in path.rglob("*") if p.is_file()]
    return max(mtimes) if mtimes else None


def detect_stale_inputs(working_dir: str | Path, agent: str) -> dict[str, float]:
    """Return {input_name: input_mtime} for upstream inputs newer than `agent`'s output.

    Returns {} if `agent` has no recorded dependencies, the agent has not
    produced an output yet, or no input is newer than the output. Mtimes are
    returned alongside names so callers can detect a *further* upstream update
    (the same input name appearing with a different mtime than what was last
    acknowledged).
    """
    spec = _STALE_DEPENDENCIES.get(agent)
    if not spec:
        return {}
    output_rel, inputs = spec
    base = get_version_dir(working_dir, active_version(working_dir))
    output_mtime = _path_mtime(base / output_rel)
    if output_mtime is None:
        return {}
    stale: dict[str, float] = {}
    for name, rel in inputs:
        input_mtime = _path_mtime(base / rel)
        if input_mtime is not None and input_mtime > output_mtime:
            stale[name] = input_mtime
    return stale


# ---------------------------------------------------------------------------
# Agent-select button state
# ---------------------------------------------------------------------------

# Canonical pipeline order of artifacts (earliest stage -> latest), relative to
# .spec4/v{N}/. The freshness chain is evaluated against this order: each
# upstream artifact must be older than the one downstream of it.
_PIPELINE_ARTIFACT_ORDER: list[str] = [
    ARTIFACT_CODE_REVIEW,
    ARTIFACT_VISION,
    ARTIFACT_AI_FEATURES,
    "design/mock.html",
    ARTIFACT_STACK,
    "phases",
    "deployment-plan.md",
]

# Inputs that must exist for an agent to be runnable at all (the Not-Ready gate),
# derived from `validate_agent_preconditions`. Every other input listed in
# `_STALE_DEPENDENCIES` is optional: it joins the freshness chain only when
# present and never blocks. Agents absent from this map have no required inputs.
_REQUIRED_INPUTS: dict[str, list[str]] = {
    "agentifier": [ARTIFACT_VISION],
    "designer": [ARTIFACT_VISION],
    "stack_advisor": [ARTIFACT_VISION],
    "phaser": [ARTIFACT_VISION, ARTIFACT_STACK],
    "deployer": ["phases"],
}

# Button states for the /agents page.
AGENT_BTN_START = "start"
AGENT_BTN_CONTINUE = "continue"
AGENT_BTN_MODIFY = "modify"
AGENT_BTN_NEEDS_UPDATE = "needs_update"
AGENT_BTN_NOT_READY = "not_ready"
AGENT_BTN_REQUIRED = "required"


def brownfield_new_round_pending(working_dir: str | Path | None) -> bool:
    """True when the highest on-disk round is implemented and the next has not
    started yet — the initial state of a new brownfield round.

    When the highest ``.spec4/v{N}/`` holds an ``IMPLEMENTED`` marker, ``v{N+1}``
    does not exist yet (it would otherwise be the highest), so the only allowed
    action is to re-scan: CodeScanner is *required* and every other agent is
    blocked until a fresh ``code_review.json`` creates ``v{N+1}``.
    """
    if not working_dir:
        return False
    latest = latest_phase_version(working_dir)
    if latest is None:
        return False
    return (get_version_dir(working_dir, latest) / "IMPLEMENTED").exists()


def directory_has_content(working_dir: str | Path | None) -> bool:
    """True when the working directory holds anything of the developer's own.

    Dot-entries are ignored, which excludes Spec4's own ``.spec4/`` bookkeeping
    (counting it would make every directory Spec4 has touched look occupied)
    along with `.git/`, `.venv/`, and similar tooling state. An unreadable or
    missing directory reads as empty.
    """
    if not working_dir:
        return False
    try:
        return any(
            not item.name.startswith(".") for item in Path(working_dir).iterdir()
        )
    except OSError:
        return False


def _is_dir(path: Path) -> bool:
    """``Path.is_dir``, behind a seam.

    A test that must make the directory check fail patches this name, which reaches
    `directory_opens` alone; patching ``Path.is_dir`` itself would reach every path
    check in the process while the test runs (CLEANUP_INVENTORY.md §60.7(i)2, §71).
    A designed patch point, private on purpose.
    """
    return path.is_dir()


def directory_opens(working_dir: str | Path | None) -> bool:
    """True when ``working_dir`` is a directory this process can still list.

    Every filesystem failure is one answer — "not openable" — because every
    caller has the same single fallback for all of them. A revoked permission,
    a detached network mount and a deleted folder are indistinguishable to the
    developer looking at a directory picker, and letting an ``OSError`` escape
    would turn the ordinary case of a moved project into a crash on the root
    path. The sibling of `directory_has_content`, and unreadable reads the
    same way there.
    """
    if not working_dir or not isinstance(working_dir, (str, Path)):
        return False
    try:
        return _is_dir(Path(working_dir)) and os.access(working_dir, os.R_OK)
    except OSError:
        return False


def needs_project_mode(
    working_dir: str | Path | None, session: dict[str, Any] | None = None
) -> bool:
    """True when the developer still has to say whether this is a new project.

    Asked whenever the directory is non-empty and the current session carries
    no answer. Deliberately *not* short-circuited by on-disk artifacts: a
    ``code_review.json`` can legitimately exist for a greenfield project (the
    developer may run CodeScanner on a skeleton), so its presence does not
    establish that we are modifying an existing codebase. The answer is read
    from the session, which is per-browser-session storage, so quitting and
    restarting asks again — by design (D-PM1).
    """
    if not working_dir or not directory_has_content(working_dir):
        return False
    return (session or {}).get("project_mode") not in PROJECT_MODES


def _has_transcript(agent: str, session: dict[str, Any] | None) -> bool:
    """True when ``agent`` has an unfinished conversation in this session.

    ``{agent}_messages`` is the agent's own LLM transcript, distinct from the
    ``messages`` the chat frame renders. It is seeded empty for every agent in
    ``default_session``, so "non-empty list" is the honest test for "this
    agent has been talked to" — anything else (absent, ``None``, a value of the
    wrong shape) is a session that has not run it.
    """
    messages = (session or {}).get(f"{agent}_messages")
    return isinstance(messages, list) and bool(messages)


def agent_button_state(
    working_dir: str | Path | None,
    agent: str,
    session: dict[str, Any] | None = None,
) -> str:
    """Resolve the /agents button state for ``agent`` from the artifacts in the
    active version directory.

    State machine (after the brownfield new-round gate):

    - A required input is missing -> ``not_ready``.
    - The existing input chain is internally out of order (some upstream
      artifact is newer than one downstream of it in pipeline order) ->
      ``not_ready``.
    - Otherwise, with the input chain in order: no output -> ``start``; output
      newer than (or equal to) the nearest input -> ``modify``; output older
      than the nearest input -> ``needs_update``.

    CodeScanner has no inputs: ``start`` with no ``code_review.json`` in the
    active version, ``modify`` once one exists. During a pending brownfield
    round it is ``required`` while every other agent is ``not_ready``. With no
    working directory yet, artifacts are treated as absent (empty project).

    One state is read from the session rather than from disk. ``start`` means
    "nothing on disk yet", which is also true of an agent the developer is
    halfway through talking to — the artifact only lands when the conversation
    finishes. When that agent has a transcript in this session the button says
    ``continue`` instead, so re-entering a half-finished agent no longer reads
    as starting it over. It is a relabelling of ``start`` and nothing more:
    ``required``, ``modify``, ``needs_update`` and ``not_ready`` are decided by
    the artifacts alone and are untouched by it.
    """
    state = _artifact_button_state(working_dir, agent, session)
    if state == AGENT_BTN_START and _has_transcript(agent, session):
        return AGENT_BTN_CONTINUE
    return state


def _artifact_button_state(  # noqa: C901, E501  # the branches are the documented artifact button state machine; E501 because project_manager.py carries no per-file E501 ignore
    working_dir: str | Path | None,
    agent: str,
    session: dict[str, Any] | None = None,
) -> str:
    """The state machine above, decided from the artifacts alone."""
    if brownfield_new_round_pending(working_dir):
        return AGENT_BTN_REQUIRED if agent == "code_scanner" else AGENT_BTN_NOT_READY

    base = (
        get_version_dir(working_dir, active_version(working_dir, session))
        if working_dir
        else None
    )

    def mtime(rel: str) -> float | None:
        return _path_mtime(base / rel) if base is not None else None

    if agent == "code_scanner":
        if mtime(ARTIFACT_CODE_REVIEW) is not None:
            return AGENT_BTN_MODIFY
        return AGENT_BTN_START

    spec = _STALE_DEPENDENCIES.get(agent)
    if spec is None:
        return AGENT_BTN_NOT_READY
    output_rel, raw_inputs = spec

    for rel in _REQUIRED_INPUTS.get(agent, []):
        if mtime(rel) is None:
            return AGENT_BTN_NOT_READY

    input_rels = {rel for _name, rel in raw_inputs}
    ordered = [rel for rel in _PIPELINE_ARTIFACT_ORDER if rel in input_rels]
    raw_chain = [(rel, mtime(rel)) for rel in ordered]
    chain: list[tuple[str, float]] = [(rel, m) for rel, m in raw_chain if m is not None]

    for (_, m_prev), (_, m_next) in zip(chain, chain[1:], strict=False):
        if m_prev > m_next:
            return AGENT_BTN_NOT_READY

    output_mtime = mtime(output_rel)
    if output_mtime is None:
        return AGENT_BTN_START
    if not chain:
        return AGENT_BTN_MODIFY
    nearest_mtime = chain[-1][1]
    if output_mtime >= nearest_mtime:
        return AGENT_BTN_MODIFY
    return AGENT_BTN_NEEDS_UPDATE
