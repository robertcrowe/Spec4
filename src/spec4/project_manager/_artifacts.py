"""Reading and writing the ``.spec4/`` artifacts, plus README assembly.

Every ``save_*``/``load_*`` pair for the version-scoped JSON and Markdown
artifacts, the phase-file writer, and the project-root ``README.md`` with its
attribution footer.

Split out of :mod:`spec4.project_manager` in cleanup Phase 4b; that module
re-exports every name defined here, so both import paths resolve to the same
object.
"""

from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path
from typing import Any

from spec4.app_constants import (
    ARTIFACT_AI_FEATURES,
    ARTIFACT_CODE_REVIEW,
    ARTIFACT_FEATURE_SPECS,
    ARTIFACT_MANIFEST,
    ARTIFACT_STACK,
    ARTIFACT_VISION,
)
from spec4.project_manager._paths import (
    active_version,
    ensure_version_dir,
    get_version_dir,
    latest_implemented_version,
    latest_phase_version,
)
from spec4.project_manager._phase_markdown import (
    parse_phase_markdown,
    render_phase_markdown,
)


# ---------------------------------------------------------------------------
# Artifact I/O
# ---------------------------------------------------------------------------


def load_spec4_artifacts(working_dir: str | Path) -> dict[str, Any]:
    """Load vision/stack/code_review and phases from the latest ``.spec4/v{N}/``.

    All artifacts are version-scoped under ``.spec4/v{N}/``. The highest version
    directory is the latest round (in-progress or implemented); the session and
    Deployer track that round. Each version is a self-contained 1..k phase set;
    lower versions are prior, implemented rounds. There is no flat-layout
    fallback — a project with no version directories loads as empty.
    """
    result: dict[str, Any] = {
        "vision": None,
        "stack": None,
        "code_review": None,
        "phases": [],
        "phase_version": None,
        "feature_specs": None,
    }

    version = latest_phase_version(working_dir)
    result["phase_version"] = version
    if version is None:
        return result

    version_dir = get_version_dir(working_dir, version)

    for key, filename in (
        ("vision", ARTIFACT_VISION),
        ("stack", ARTIFACT_STACK),
        ("code_review", ARTIFACT_CODE_REVIEW),
        ("feature_specs", ARTIFACT_FEATURE_SPECS),
    ):
        with contextlib.suppress(OSError, json.JSONDecodeError):
            result[key] = json.loads((version_dir / filename).read_text())

    phases_dir = version_dir / "phases"

    def _by_number(p: Path) -> tuple[int, str]:
        m = re.match(r"phase(\d+)", p.stem)
        return (int(m.group(1)) if m else 0, p.name)

    for pf in sorted(phases_dir.glob("phase*.md"), key=_by_number):
        phase = parse_phase_markdown(pf.read_text(encoding="utf-8"))
        if phase is not None:
            result["phases"].append(phase)

    return result


def write_text_if_changed(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` only when it differs from what is on disk.

    Re-persisting an unchanged artifact must not bump its mtime: the agent-select
    freshness model and ``detect_stale_inputs`` both treat a newer input mtime as
    a semantic change, so a no-op re-save (the persist funnel re-writes every
    COMPLETE artifact on every later turn) would otherwise make untouched
    upstream artifacts look newer than the outputs they precede.
    """
    try:
        if path.exists() and path.read_text(encoding="utf-8") == content:
            return
    except OSError:
        pass
    path.write_text(content, encoding="utf-8")


def save_vision(working_dir: str | Path, vision: dict[str, Any], version: int) -> None:
    version_dir = ensure_version_dir(working_dir, version)
    write_text_if_changed(version_dir / ARTIFACT_VISION, json.dumps(vision, indent=2))


def save_stack(working_dir: str | Path, stack: dict[str, Any], version: int) -> None:
    version_dir = ensure_version_dir(working_dir, version)
    write_text_if_changed(version_dir / ARTIFACT_STACK, json.dumps(stack, indent=2))


def merge_library_additions(
    stack: dict[str, Any] | None,
    additions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge human-confirmed library additions into a stack spec.

    Each addition is a dict with at least ``name`` and ``tier`` (one of
    ``backend`` / ``frontend`` / ``infrastructure``); ``category`` and
    ``purpose`` are optional and carried through when present, as are the
    join keys ``serves_features`` / ``serves_capabilities`` /
    ``satisfies_nfr`` (D-PH7d — each sanitized to a list of non-empty
    strings and dropped when nothing survives). Preserving the join keys is
    what keeps a purpose-made addition attributable across rounds: without
    them it reads as a global staple and any NFR it satisfied reads as
    orphaned forever. Additions land in ``stack_spec.libraries[tier]`` in
    the same shape StackAdvisor's own entries occupy, so a later
    StackAdvisor re-entry treats them as its own.

    Guard: **dedup by name within the tier.** An addition whose ``name``
    already appears in that tier (case-insensitive) is dropped — the only
    deterministic redundancy. A same-category, different-name library (e.g. a
    second ``external_api``) is a distinct, legitimate entry and is kept.

    Pure and idempotent: returns a new merged stack and does not mutate the
    input. Re-applying the same additions is a no-op. Malformed additions
    (missing ``name`` or ``tier``, or an unknown tier) are skipped rather than
    raising, so a bad parse never strands the caller.
    """
    import copy

    valid_tiers = ("backend", "frontend", "infrastructure")
    merged = copy.deepcopy(stack) if isinstance(stack, dict) else {}

    # Locate (or create) the inner spec and its libraries map, tolerating both
    # the wrapped ({"stack_spec": {...}}) and bare shapes.
    spec, libraries = _libraries_map(merged)

    for entry in additions:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        tier = str(entry.get("tier", "")).strip().lower()
        if not name or tier not in valid_tiers:
            continue
        tier_libs = libraries.get(tier)
        if not isinstance(tier_libs, list):
            tier_libs = []
            libraries[tier] = tier_libs
        if any(
            isinstance(lib, dict)
            and str(lib.get("name", "")).strip().lower() == name.lower()
            for lib in tier_libs
        ):
            continue  # dedup-by-name guard
        tier_libs.append(_library_entry(entry, name))

    return merged


def save_code_review(
    working_dir: str | Path, review: dict[str, Any], version: int
) -> None:
    version_dir = ensure_version_dir(working_dir, version)
    write_text_if_changed(
        version_dir / ARTIFACT_CODE_REVIEW, json.dumps(review, indent=2)
    )


def load_prior_vision(working_dir: str | Path) -> dict[str, Any] | None:
    """Read the vision of the latest *implemented* round, as read-only reference.

    Used by Brainstormer's revision mode to carry the established product
    identity (name, purpose, audience, the prior feature set, and the
    accumulated ``revision_history``) into a new revision round without loading
    it as the active working artifact. Returns ``None`` when no implemented
    round exists or its ``vision.json`` is missing/unreadable.
    """
    version = latest_implemented_version(working_dir)
    if version is None:
        return None
    vision_path = get_version_dir(working_dir, version) / ARTIFACT_VISION
    if not vision_path.exists():
        return None
    try:
        vision: dict[str, Any] = json.loads(vision_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return vision


def save_phases(
    working_dir: str | Path,
    phases: list[dict[str, Any]],
    version: int,
    context: dict[str, Any] | None = None,
) -> None:
    """Write each phase as a Markdown-with-JSON-frontmatter file under
    ``.spec4/v{version}/phases/``.

    The coding agent reads the prose body; Spec4 round-trips through the
    frontmatter JSON when reloading. The target ``phases/`` directory's existing
    ``phase*.md`` files are cleared first — a re-defined set may be shorter than
    the one it replaces — then the new set is written. The round's
    ``IMPLEMENTED`` marker lives at ``.spec4/v{version}/IMPLEMENTED`` (one level
    up) and is therefore untouched by clearing the phases directory.
    """
    phases_dir = ensure_version_dir(working_dir, version) / "phases"
    phases_dir.mkdir(parents=True, exist_ok=True)
    desired = {
        f"phase{phase.get('phase_number', 0)}.md": render_phase_markdown(phase, context)
        for phase in phases
    }
    # Remove only phase files no longer in the set; rewrite the rest in place so
    # an unchanged phase keeps its mtime (see write_text_if_changed).
    for stale in phases_dir.glob("phase*.md"):
        if stale.name not in desired:
            stale.unlink()
    for name, content in desired.items():
        write_text_if_changed(phases_dir / name, content)


def save_ai_catalog(
    working_dir: str | Path, catalog: dict[str, Any], version: int
) -> None:
    version_dir = ensure_version_dir(working_dir, version)
    write_text_if_changed(
        version_dir / "ai_catalog.json", json.dumps(catalog, indent=2)
    )


def load_ai_catalog(working_dir: str | Path) -> dict[str, Any] | None:
    version = latest_phase_version(working_dir)
    if version is None:
        return None
    path = get_version_dir(working_dir, version) / "ai_catalog.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def save_ai_features(
    working_dir: str | Path, features: dict[str, Any], version: int
) -> None:
    version_dir = ensure_version_dir(working_dir, version)
    write_text_if_changed(
        version_dir / ARTIFACT_AI_FEATURES, json.dumps(features, indent=2)
    )


def load_ai_features(working_dir: str | Path) -> dict[str, Any] | None:
    version = latest_phase_version(working_dir)
    if version is None:
        return None
    path = get_version_dir(working_dir, version) / ARTIFACT_AI_FEATURES
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def save_feature_specs(
    working_dir: str | Path, feature_specs: dict[str, Any], version: int
) -> None:
    version_dir = ensure_version_dir(working_dir, version)
    write_text_if_changed(
        version_dir / ARTIFACT_FEATURE_SPECS, json.dumps(feature_specs, indent=2)
    )


def load_design_manifest(
    working_dir: str | Path, version: int
) -> dict[str, Any] | None:
    """Load Designer's finalized ``design/manifest.json`` for a version.

    Absent or unparseable manifests return ``None`` (older projects, or a
    design round that never finalized); consumers render nothing in that case.
    Single loader shared by the Phaser seed projection and the ``save_phases``
    context bundle (D-PH5b).
    """
    path = get_version_dir(working_dir, version) / "design" / ARTIFACT_MANIFEST
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_feature_specs(working_dir: str | Path) -> dict[str, Any] | None:
    version = latest_phase_version(working_dir)
    if version is None:
        return None
    path = get_version_dir(working_dir, version) / ARTIFACT_FEATURE_SPECS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def load_vision(
    working_dir: str | Path, session: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Read the current ``vision.json`` for the active round from disk.

    Uses the same version resolution (``active_version``) as ``agent_button_state``
    so that Brainstormer's entry decision and the agent button agree on whether a
    vision exists. Returns ``None`` when the file is absent or unreadable.
    """
    version = active_version(working_dir, session)
    path = get_version_dir(working_dir, version) / ARTIFACT_VISION
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def save_deployment_plan(working_dir: str | Path, markdown: str, version: int) -> None:
    version_dir = ensure_version_dir(working_dir, version)
    write_text_if_changed(version_dir / "deployment-plan.md", markdown)


def load_prior_ai_features(working_dir: str | Path) -> dict[str, Any] | None:
    """Read the ai_features of the latest *implemented* round, as reference.

    Twin of :func:`load_prior_vision`. Used by Agentifier's revision mode to
    carry the established AI surface (the features already built in the previous
    implemented version, plus their cross-cutting decisions) into a new revision
    round without loading it as the active working artifact — the current round
    has no ai_features of its own yet. It reads from ``latest_implemented_version``
    (the highest round bearing an ``IMPLEMENTED`` marker), in contrast to
    :func:`load_ai_features`, which reads the highest dir regardless of
    completion. Returns ``None`` when no implemented round exists or its
    ``ai_features.json`` is missing/unreadable.
    """
    version = latest_implemented_version(working_dir)
    if version is None:
        return None
    path = get_version_dir(working_dir, version) / ARTIFACT_AI_FEATURES
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def load_prior_mock(working_dir: str | Path) -> str | None:
    """Read the UI mock of the latest *implemented* round, as read-only reference.

    Twin of :func:`load_prior_vision` / :func:`load_prior_ai_features`, but for
    Designer's ``design/mock.html``. Used by Designer's revision mode to carry the
    established, approved look and feel into a new revision round as the baseline
    the revision's delta is applied onto — the current round has no mock of its
    own yet. It reads from ``latest_implemented_version`` (the highest round
    bearing an ``IMPLEMENTED`` marker). Returns ``None`` when no implemented round
    exists or its ``design/mock.html`` is missing/unreadable/empty.
    """
    version = latest_implemented_version(working_dir)
    if version is None:
        return None
    path = get_version_dir(working_dir, version) / "design" / "mock.html"
    if not path.exists():
        return None
    try:
        html = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return html if html.strip() else None


def load_prior_stack(working_dir: str | Path) -> dict[str, Any] | None:
    """Read the stack spec of the latest *implemented* round, as reference.

    Twin of :func:`load_prior_vision` / :func:`load_prior_ai_features`, but for
    StackAdvisor's ``stack.json``. Used by StackAdvisor's revision mode to carry
    the established technology stack (the languages, deployment, libraries, and
    coding style already chosen in the previous implemented version) into a new
    revision round as the baseline its delta-scoped recommendations build on —
    the current round has no stack of its own yet. It reads from
    ``latest_implemented_version`` (the highest round bearing an ``IMPLEMENTED``
    marker), in contrast to :func:`load_spec4_artifacts`, which hydrates the
    active round's stack regardless of completion. Returns ``None`` when no
    implemented round exists or its ``stack.json`` is missing/unreadable.
    """
    version = latest_implemented_version(working_dir)
    if version is None:
        return None
    path = get_version_dir(working_dir, version) / ARTIFACT_STACK
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def load_deployment_plan(working_dir: str | Path) -> str | None:
    version = latest_phase_version(working_dir)
    if version is None:
        return None
    path = get_version_dir(working_dir, version) / "deployment-plan.md"
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        return None


def load_prior_deployment_plan(working_dir: str | Path) -> str | None:
    """Read the deployment plan of the latest *implemented* round, as reference.

    Twin of :func:`load_prior_mock` / :func:`load_prior_stack`, but for Deployer's
    ``deployment-plan.md``. Used by Deployer's revision mode to carry the
    established deployment plan (the provider, service, containerization, CI/CD,
    environment, and infrastructure already in place in the previous implemented
    version) into a new revision round as the baseline the revision's delta-scoped
    update builds on — the current round has no deployment plan of its own yet. It
    reads from ``latest_implemented_version`` (the highest round bearing an
    ``IMPLEMENTED`` marker), in contrast to :func:`load_deployment_plan`, which
    reads the active round's plan regardless of completion. Returns ``None`` when
    no implemented round exists or its ``deployment-plan.md`` is
    missing/unreadable/empty (the prior round may have skipped Deployer).
    """
    version = latest_implemented_version(working_dir)
    if version is None:
        return None
    path = get_version_dir(working_dir, version) / "deployment-plan.md"
    if not path.exists():
        return None
    try:
        markdown = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return markdown if markdown.strip() else None


SPEC4_README_ATTRIBUTION = "[Built with Spec4 AI](https://spec4.ai)"


def _with_readme_attribution(markdown: str) -> str:
    """Return ``markdown`` ending with the Spec4 attribution line, exactly once.

    Applied deterministically at write time rather than asked of the model: the
    line then appears whether the README was authored fresh or updated in place,
    and cannot be dropped by a re-generation.

    Idempotent by design, and position-correcting. Deployer updates an existing
    README in place and is given the current file as a baseline, so a previously
    stamped README arrives already carrying the line — and once the model
    appends a new section after it, the line is no longer last. Any existing
    occurrence is therefore removed and re-appended, which keeps it at the
    bottom exactly once however the document was assembled.

    The README is the only file Spec4 attributes: it carries the line as its
    closing footer. Phase files no longer ask the coding agent to stamp the
    source files it creates.
    """
    raw = markdown.rstrip()
    if not raw:
        return markdown
    kept: list[str] = []
    for line in raw.split("\n"):
        if line.strip() == SPEC4_README_ATTRIBUTION:
            # Drop the blank line that separated it too, or each revision round
            # would leave one behind at the seam.
            if kept and not kept[-1].strip():
                kept.pop()
            continue
        kept.append(line)
    body = "\n".join(kept).rstrip()
    if not body:
        return f"{SPEC4_README_ATTRIBUTION}\n"
    return f"{body}\n\n{SPEC4_README_ATTRIBUTION}\n"


def save_readme(working_dir: str | Path, markdown: str) -> None:
    """Write the project ``README.md`` to the project **root** (not ``.spec4``).

    The README is the one Spec4 artifact that lives at the project root rather
    than under ``.spec4/v{N}/``: it is the human-facing entry point for the
    repository — vision, features, install, and usage in one document — so it
    belongs where anyone (or any coding agent) opening the repo will find it.
    The Spec4 attribution line is appended as the closing line here rather than
    requested of the model, so it survives every authoring and revision path.
    Routed through :func:`write_text_if_changed` so an unchanged README is a
    no-op and does not bump mtimes the freshness model watches.
    """
    write_text_if_changed(
        Path(working_dir) / "README.md", _with_readme_attribution(markdown)
    )


def load_existing_readme(working_dir: str | Path) -> str | None:
    """Return the project-root ``README.md`` as a baseline, or ``None`` if absent.

    Twin of :func:`load_prior_deployment_plan`, but reads the project **root**
    rather than a version dir — the README is not version-scoped. Deployer's
    README authoring uses it to update an existing README in place rather than
    overwriting it from scratch. A missing, unreadable, or blank/whitespace-only
    file is treated as absent (``None``) so the caller falls back to authoring a
    fresh README.
    """
    path = Path(working_dir) / "README.md"
    if not path.exists():
        return None
    try:
        markdown = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return markdown if markdown.strip() else None


def _libraries_map(
    merged: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Locate (or create) the inner spec and its libraries map."""
    # Locate (or create) the inner spec and its libraries map, tolerating both
    # the wrapped ({"stack_spec": {...}}) and bare shapes.
    _inner = merged.get("stack_spec")
    spec = _inner if isinstance(_inner, dict) else None
    if spec is None:
        if "stack_spec" in merged:
            merged["stack_spec"] = {}
            spec = merged["stack_spec"]
        else:
            spec = merged
    libraries = spec.get("libraries")
    if not isinstance(libraries, dict):
        libraries = {}
        spec["libraries"] = libraries
    return spec, libraries


def _library_entry(
    entry: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    """One merged library entry, carrying its D-PH7d join keys."""
    new_lib: dict[str, Any] = {"name": name}
    category = str(entry.get("category", "")).strip()
    purpose = str(entry.get("purpose", "")).strip()
    if category:
        new_lib["category"] = category
    if purpose:
        new_lib["purpose"] = purpose
    # D-PH7d: preserve the join keys so the addition stays attributable
    # (stack routing / NFR threading read these; an unkeyed entry is a
    # global staple). List-of-non-empty-strings only; drop when empty.
    for join_key in ("serves_features", "serves_capabilities", "satisfies_nfr"):
        raw = entry.get(join_key)
        if not isinstance(raw, list):
            continue
        ids = [s.strip() for s in raw if isinstance(s, str) and s.strip()]
        if ids:
            new_lib[join_key] = ids
    return new_lib
