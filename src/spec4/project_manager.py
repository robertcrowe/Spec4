"""Project directory management for Spec4.

Handles working directory selection and .spec4 artifact storage.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from spec4.app_constants import PROJECT_MODE_EXISTING

from spec4 import __version__
from spec4.app_constants import PROJECT_MODES
from spec4.design_manifest import (
    surface_detail_lines,
    surfaces_for_declarations,
)
from spec4.stack_routing import (
    baseline_library_names,
    entries_for_declarations,
    nfr_threads,
)
from spec4.feature_specs import (
    PHASE_EXCLUDED_CROSS_CUTTING,
    PHASE_SPEC_FIELDS,
    PHASER_PRODUCT_SPEC_FIELDS,
    render_cross_cutting,
    render_feature_block,
    spec_index,
)

# Phase artifacts are stored as Markdown-with-frontmatter so the coding agent
# consumes them as natural prose, while Spec4 retains a machine-readable copy
# of the full phase object inside the frontmatter for round-trip. The
# frontmatter payload is plain JSON (a YAML superset, so this remains
# compatible with any frontmatter-aware tooling) — no extra YAML dep required.
_PHASE_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


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
        ("vision", "vision.json"),
        ("stack", "stack.json"),
        ("code_review", "code_review.json"),
        ("feature_specs", "feature_specs.json"),
    ):
        try:
            result[key] = json.loads((version_dir / filename).read_text())
        except (OSError, json.JSONDecodeError):
            pass

    phases_dir = version_dir / "phases"

    def _by_number(p: Path) -> tuple[int, str]:
        m = re.match(r"phase(\d+)", p.stem)
        return (int(m.group(1)) if m else 0, p.name)

    for pf in sorted(phases_dir.glob("phase*.md"), key=_by_number):
        phase = parse_phase_markdown(pf.read_text(encoding="utf-8"))
        if phase is not None:
            result["phases"].append(phase)

    return result


def _write_text_if_changed(path: Path, content: str) -> None:
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


def save_vision(
    working_dir: str | Path, vision: dict[str, Any], version: int
) -> None:
    version_dir = ensure_version_dir(working_dir, version)
    _write_text_if_changed(
        version_dir / "vision.json", json.dumps(vision, indent=2)
    )


def save_stack(
    working_dir: str | Path, stack: dict[str, Any], version: int
) -> None:
    version_dir = ensure_version_dir(working_dir, version)
    _write_text_if_changed(
        version_dir / "stack.json", json.dumps(stack, indent=2)
    )


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
        tier_libs.append(new_lib)

    return merged


def save_code_review(
    working_dir: str | Path, review: dict[str, Any], version: int
) -> None:
    version_dir = ensure_version_dir(working_dir, version)
    _write_text_if_changed(
        version_dir / "code_review.json", json.dumps(review, indent=2)
    )


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
    vision_path = get_version_dir(working_dir, version) / "vision.json"
    if not vision_path.exists():
        return None
    try:
        return json.loads(vision_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


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
    return bool(session) and session.get("project_mode") == PROJECT_MODE_EXISTING


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
    # an unchanged phase keeps its mtime (see _write_text_if_changed).
    for stale in phases_dir.glob("phase*.md"):
        if stale.name not in desired:
            stale.unlink()
    for name, content in desired.items():
        _write_text_if_changed(phases_dir / name, content)


# ---------------------------------------------------------------------------
# Phase Markdown serialization
# ---------------------------------------------------------------------------


def _phase_spec_preamble(
    phase: dict[str, Any], context: dict[str, Any] | None
) -> list[str]:
    """Render the binding spec preamble for the features this phase builds.

    The phase file is the *sole* deliverable to the coding agent — it never sees
    ``ai_features.json`` — so the Spec Drafter's output has to reach the build
    through here or not at all. Assembly is deterministic and verbatim: Phaser
    sequences and writes the glue, code attaches the specs, and no model
    re-drafts an already-drafted spec.

    A **preamble**, not an appendix: the coding agent must read what a feature's
    inputs and failure modes are before it reads step 3 of the instructions, and
    a preamble reads as binding where an appendix reads as optional.

    The whole spec attaches at *every* phase that touches the feature — the spec
    describes the finished feature and has no principled cut into "the phase-2
    half". A phase's partial coverage is stated in Phaser's ``scope_note``, never
    by slicing the spec. Duplication across files is cheap; a dangling
    cross-phase reference would break the self-containment that makes each phase
    handable to the coder alone.

    Specs are resolved from ``context["ai_features"]`` at render time rather than
    frozen into the phase dict, so they are stored once and cannot drift from the
    catalog. ``context`` is a bundle (D-PS11) so later consumers — a StackAdvisor
    stack↔feature linkage, say — can be added without re-breaking every caller.
    Returns ``[]`` when the phase declares no features or no catalog is supplied.
    """
    # D-PH2/D-PH5a: two declaration arrays, two spec altitudes, each attached
    # from its own source. `features[]` attaches the Brainstormer behavioural
    # spec (what the product feature is and when it is done); `capabilities[]`
    # attaches the Agentifier implementation spec (how the AI capability is
    # built at its tier). Never merged: a phase building a feature AND the
    # capability serving it gets both blocks, the serves-relation stated on
    # the capability side. The legacy `or features` fallback keeps pre-D-PH2
    # sets rendering (AI ids lived in features[] then); either lookup simply
    # misses for ids from the other era's space.
    feature_decls = [
        d for d in (phase.get("features") or []) if isinstance(d, dict)
    ]
    # Era detection is KEY PRESENCE, not truthiness: a new-schema phase with
    # an empty `capabilities` array declares no capabilities — falling back to
    # `features[]` there would read product ids against the AI catalog and
    # resurrect the collision misread the two-array schema exists to kill.
    legacy = "capabilities" not in phase
    capability_decls = [
        d
        for d in (
            (phase.get("features") if legacy else phase.get("capabilities"))
            or []
        )
        if isinstance(d, dict)
    ]
    if not feature_decls and not capability_decls:
        return []

    ai_index = spec_index((context or {}).get("ai_features"))
    product_index = {
        str(f["id"]): f
        for f in (((context or {}).get("feature_specs") or {}).get("features") or [])
        if isinstance(f, dict) and f.get("id")
    }
    declared_feature_ids = {
        str(d.get("id")) for d in feature_decls if d.get("id")
    }
    declared_capability_ids = {
        str(d.get("id")) for d in capability_decls if d.get("id")
    }

    def _decl_heading(name: str, altitude: str, decl: dict[str, Any]) -> list[str]:
        role = str(decl.get("role") or "").strip()
        heading = f"### {name} — {altitude}"
        if role:
            heading += f" — {role} in this phase"
        lines = [heading, ""]
        scope_note = str(decl.get("scope_note") or "").strip()
        if scope_note:
            lines.append(f"*Scope for this phase: {scope_note}*")
            lines.append("")
        return lines

    # --- product feature blocks (D-PH5a) -----------------------------------
    product_blocks: list[str] = []
    for decl in feature_decls:
        feature = product_index.get(str(decl.get("id") or ""))
        if feature is None:
            continue  # unknown/legacy id: coverage owns validation
        name = feature.get("name") or decl.get("id")
        product_blocks.extend(_decl_heading(str(name), "product feature", decl))
        product_blocks.extend(
            render_feature_block(
                feature, fields=PHASER_PRODUCT_SPEC_FIELDS, include_graph=False
            )
        )
        deps = [
            str(d).strip()
            for d in (feature.get("dependencies") or [])
            if str(d).strip()
        ]
        if deps:
            product_blocks.append(
                f"- depends on: {', '.join(deps)} (build these no later than "
                f"`{decl.get('id')}`)"
            )
        entities = [
            str(e) for e in (feature.get("entities") or []) if isinstance(e, str)
        ]
        if entities:
            product_blocks.append(f"- entities: {', '.join(entities)}")
        product_blocks.append("")

    # --- UI surfaces block (D-PH5b/c) ---------------------------------------
    surface_blocks: list[str] = []
    attached = surfaces_for_declarations(
        (context or {}).get("manifest"),
        declared_feature_ids,
        declared_capability_ids,
    )
    if attached:
        surface_blocks.append("### UI surfaces for this phase (from the design)")
        surface_blocks.append("")
        by_catalog: dict[str, list[dict[str, Any]]] = {}
        plain: list[dict[str, Any]] = []
        for rec in attached:
            cid = str(rec["surface"].get("catalog_surface_id") or "")
            if cid:
                by_catalog.setdefault(cid, []).append(rec)
            else:
                plain.append(rec)
        for rec in plain:
            surface_blocks.extend(surface_detail_lines(rec["surface"]))
        for cid, recs in by_catalog.items():
            surface_blocks.append(
                f"The following surface(s) realize the AI capability `{cid}` "
                "— one unit of work; the surfaces are views onto it:"
            )
            for rec in recs:
                surface_blocks.extend(surface_detail_lines(rec["surface"]))
        surface_blocks.append("")

    # --- AI capability blocks (existing altitude, serves-relation stated) ---
    ai_blocks: list[str] = []
    for decl in capability_decls:
        feature = ai_index.get(str(decl.get("id") or ""))
        if feature is None:
            continue  # unknown id: _phase_coverage fails the set before here
        name = feature.get("name") or decl.get("id")
        ai_blocks.extend(_decl_heading(str(name), "AI capability", decl))
        grounding = feature.get("vision_grounding") or {}
        served = sorted({
            str(sf.get("id"))
            for sf in (grounding.get("served_features") or [])
            if isinstance(sf, dict) and sf.get("id")
        } & declared_feature_ids)
        if served:
            ai_blocks.append(
                "Serves product feature(s): "
                + ", ".join(f"`{s}`" for s in served)
                + " (specified above)."
            )
            ai_blocks.append("")
        ai_blocks.extend(render_feature_block(feature, fields=PHASE_SPEC_FIELDS))

    if not product_blocks and not surface_blocks and not ai_blocks:
        return []

    lines = [
        "## Feature Specifications",
        "",
        "These specifications are authoritative for this phase. Implement to "
        "them; the instructions below tell you how and in what order.",
        "",
        *product_blocks,
        *surface_blocks,
        *ai_blocks,
    ]
    # Project-wide AI decisions, rendered only where AI capabilities are
    # actually being built (D-PH5 gate — cross-cutting is catalog-level
    # guidance and has no place in a product-only phase). `provider_strategy`
    # is excluded — StackAdvisor's `tech_stack_spec` above is the ratified
    # stack authority and must not be contradicted here.
    if ai_blocks:
        lines.extend(
            render_cross_cutting(
                (context or {}).get("ai_features", {}).get("cross_cutting"),
                exclude=PHASE_EXCLUDED_CROSS_CUTTING,
            )
        )
    return lines


def _declared_ids(phase: dict[str, Any], key: str) -> set[str]:
    """Ids a phase declares in one array (two-array schema, D-PH2a)."""
    return {
        str(d.get("id"))
        for d in (phase.get(key) or [])
        if isinstance(d, dict) and d.get("id")
    }


def _phase_stack_lines(
    phase: dict[str, Any], context: dict[str, Any] | None
) -> list[str]:
    """Deterministic stack routing for one phase's Tech Stack section (D-PH3).

    Renders the serving entries whose ``serves_features`` /
    ``serves_capabilities`` intersect this phase's declarations (each key
    against its own array), then the project-wide baseline staples that render
    in every phase. Renderer-added body only — the frontmatter stays the
    model's artifact verbatim. Returns ``[]`` when the context carries no
    stack (older sessions), so a stack-less render is unchanged.
    """
    stack = (context or {}).get("stack")
    if not stack:
        return []
    routed = entries_for_declarations(
        stack,
        _declared_ids(phase, "features"),
        _declared_ids(phase, "capabilities"),
    )
    baseline = baseline_library_names(stack)
    if not routed and not baseline:
        return []
    lines: list[str] = []
    if routed:
        lines.append(
            "**Approved stack for this phase's declared work** "
            "(deterministic, from the stack spec):"
        )
        lines.append("")
        for rec in routed:
            label = rec["label"]
            if rec["section"] and rec["section"] not in label:
                label = f"{label} ({rec['section']})"
            served = ", ".join(f"`{m}`" for m in rec["matched"])
            purpose = str(rec["entry"].get("purpose") or "").strip()
            detail = f": {purpose}" if purpose else ""
            lines.append(f"- {label}{detail} — serves {served}")
        lines.append("")
    if baseline:
        lines.append("**Project-wide stack** (applies to every phase):")
        lines.append("")
        lines.extend(f"- {name}" for name in baseline)
        lines.append("")
    return lines


def _phase_nfr_lines(
    phase: dict[str, Any], context: dict[str, Any] | None
) -> list[str]:
    """Deterministic NFR threading for one phase's Verification section (D-PH4).

    A claimed goal threads into every phase whose declarations intersect the
    claiming entries' served ids; a goal claimed only by global entries (no
    serves keys) threads into the final phase as project-wide acceptance.
    Orphaned goals never appear. Returns ``[]`` when nothing threads here.
    """
    stack = (context or {}).get("stack")
    specs = (context or {}).get("feature_specs")
    if not stack or not specs:
        return []
    features = _declared_ids(phase, "features")
    capabilities = _declared_ids(phase, "capabilities")
    number = phase.get("phase_number")
    total = phase.get("total_phases")
    is_final = (
        isinstance(number, int) and isinstance(total, int) and number == total
    )
    hits: list[str] = []
    for thread in nfr_threads(stack, specs):
        if thread["global"]:
            if not is_final:
                continue
            scope = "project-wide acceptance"
        else:
            matched = (thread["serves_features"] & features) | (
                thread["serves_capabilities"] & capabilities
            )
            if not matched:
                continue
            scope = "delivered by " + ", ".join(thread["claimers"])
        hits.append(f"- `{thread['nfr_id']}`: {thread['goal']} — {scope}")
    if not hits:
        return []
    return [
        "",
        "**Non-functional acceptance** (deterministic, from the stack spec):",
        "",
        *hits,
        "",
    ]


def render_phase_markdown(
    phase: dict[str, Any], context: dict[str, Any] | None = None
) -> str:
    """Render a phase dict as Markdown with JSON frontmatter.

    Frontmatter carries the canonical structured payload (full round-trip);
    the body renders the same fields as prose for the coding agent, plus the
    verbatim spec preamble resolved from ``context`` (see
    ``_phase_spec_preamble``). ``context`` defaults to ``None``, which renders
    exactly as before — the round-trip through ``parse_phase_markdown`` reads
    only the frontmatter, so a spec-less render loses nothing.
    """
    frontmatter = json.dumps(phase, indent=2, ensure_ascii=False)

    number = phase.get("phase_number", "?")
    total = phase.get("total_phases", "?")
    title = phase.get("phase_title", "")
    summary = phase.get("phase_summary", "")
    tech = phase.get("tech_stack_spec") or {}
    deps = tech.get("dependencies") or []
    configs = tech.get("configurations") or ""
    instructions = phase.get("instructions") or []
    risk = phase.get("risk_assessment") or {}
    bottlenecks = risk.get("potential_bottlenecks", "")
    mitigation = risk.get("mitigation_strategy", "")
    verification = phase.get("verification", "")
    references = phase.get("references") or []

    lines: list[str] = [
        "---",
        frontmatter,
        "---",
        "",
        f"# Phase {number} of {total}: {title}".rstrip(": "),
        "",
        summary,
        "",
    ]
    lines.extend(_phase_spec_preamble(phase, context))
    lines.extend([
        "## Tech Stack",
        "",
    ])
    if deps:
        lines.append("**Dependencies:**")
        lines.append("")
        lines.extend(f"- {d}" for d in deps)
        lines.append("")
    if configs:
        lines.append(f"**Configurations:** {configs}")
        lines.append("")
    lines.extend(_phase_stack_lines(phase, context))
    lines.append("## Instructions")
    lines.append("")
    for idx, step in enumerate(instructions, start=1):
        lines.append(f"{idx}. {step}")
    lines.append("")
    lines.append("## Risk Assessment")
    lines.append("")
    if bottlenecks:
        lines.append("**Potential bottlenecks:**")
        lines.append("")
        lines.append(bottlenecks)
        lines.append("")
    if mitigation:
        lines.append("**Mitigation strategy:**")
        lines.append("")
        lines.append(mitigation)
        lines.append("")
    lines.append("## Verification")
    lines.append("")
    lines.append(verification)
    lines.extend(_phase_nfr_lines(phase, context))
    lines.append("")
    if references:
        lines.append("## References")
        lines.append("")
        for ref in references:
            standard = ref.get("standard", "")
            url = ref.get("url", "")
            if standard and url:
                lines.append(f"- [{standard}]({url})")
            elif standard:
                lines.append(f"- {standard}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse_phase_markdown(text: str) -> dict[str, Any] | None:
    """Parse a phase Markdown file back into its structured dict.

    Reads only the JSON frontmatter — the prose body is a deterministic
    rendering of the same fields, so re-parsing it would be redundant and
    error-prone. Returns None when no frontmatter is present or it is not
    valid JSON.
    """
    match = _PHASE_FRONTMATTER_RE.match(text)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def save_ai_catalog(
    working_dir: str | Path, catalog: dict[str, Any], version: int
) -> None:
    version_dir = ensure_version_dir(working_dir, version)
    _write_text_if_changed(
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
    _write_text_if_changed(
        version_dir / "ai_features.json", json.dumps(features, indent=2)
    )


def load_ai_features(working_dir: str | Path) -> dict[str, Any] | None:
    version = latest_phase_version(working_dir)
    if version is None:
        return None
    path = get_version_dir(working_dir, version) / "ai_features.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def save_feature_specs(
    working_dir: str | Path, feature_specs: dict[str, Any], version: int
) -> None:
    version_dir = ensure_version_dir(working_dir, version)
    _write_text_if_changed(
        version_dir / "feature_specs.json", json.dumps(feature_specs, indent=2)
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
    path = get_version_dir(working_dir, version) / "design" / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_feature_specs(working_dir: str | Path) -> dict[str, Any] | None:
    version = latest_phase_version(working_dir)
    if version is None:
        return None
    path = get_version_dir(working_dir, version) / "feature_specs.json"
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
    path = get_version_dir(working_dir, version) / "vision.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def save_deployment_plan(
    working_dir: str | Path, markdown: str, version: int
) -> None:
    version_dir = ensure_version_dir(working_dir, version)
    _write_text_if_changed(version_dir / "deployment-plan.md", markdown)


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
    path = get_version_dir(working_dir, version) / "ai_features.json"
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
    path = get_version_dir(working_dir, version) / "stack.json"
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


# ---------------------------------------------------------------------------
# LLM usage log
# ---------------------------------------------------------------------------

USAGE_FILENAME = "usage.json"
USAGE_SCHEMA_VERSION = "1"
_USAGE_COST_SOURCE = (
    "litellm response_cost (community cost map; may lag provider price sheets)"
)

# Sub-agents roll up into the planning agent whose turn runs them. Anything not
# listed reports under its own name, so a new sub-agent is visible rather than
# silently misattributed.
_USAGE_ROLLUP_PARENT: dict[str, str] = {
    "feature_speccer": "brainstormer",
    "phaser_seam": "phaser",
    "scout": "agentifier",
    "tier_analyst": "agentifier",
    "linker": "agentifier",
    "composer": "agentifier",
    "prioritizer": "agentifier",
    "spec_drafter": "agentifier",
    "cross_cutting_analyst": "agentifier",
}

_USAGE_LOCK = threading.Lock()


def _usage_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _usage_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def usage_rollup_name(agent: Any) -> str:
    raw = agent if isinstance(agent, str) and agent else "unknown"
    return _USAGE_ROLLUP_PARENT.get(raw, raw)


def _usage_versions() -> tuple[str, str]:
    """(spec4 version, litellm version) for the file header. Never raises."""
    try:
        litellm_version = importlib.metadata.version("litellm")
    except importlib.metadata.PackageNotFoundError:
        litellm_version = "unknown"
    return __version__, litellm_version


def summarize_usage(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll one agent's per-call ``history`` up into its summary block.

    Derived, never accumulated: every write recomputes this from the full
    history, so the summary cannot drift from the call records. Token and
    cost sums cover only calls that reported them; ``cached_input_tokens``
    and ``computed_cost_usd`` stay null when no call in the history had a
    value, rather than reading as a confident zero. ``models`` lists each
    distinct (model, provider) pair in first-seen order, which is how a
    re-run on a different model within the round becomes visible.
    """
    rollup: dict[str, Any] = {
        "calls": 0,
        "calls_missing_usage": 0,
        # Calls the provider reported usage for but LiteLLM could not price
        # (no cost-map entry). Their tokens are counted; their cost is not,
        # so a cost figure shown next to this count is a known undercount.
        "calls_missing_cost": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cached_input_tokens": None,
        "computed_cost_usd": None,
        "models": [],
    }
    for call in history:
        rollup["calls"] += 1
        if call.get("usage_missing"):
            rollup["calls_missing_usage"] += 1
        elif _usage_float(call.get("computed_cost_usd")) is None:
            rollup["calls_missing_cost"] += 1
        for src, dst in (
            ("prompt_tokens", "input_tokens"),
            ("completion_tokens", "output_tokens"),
            ("total_tokens", "total_tokens"),
        ):
            value = _usage_int(call.get(src))
            if value is not None:
                rollup[dst] += value
        cached = _usage_int(call.get("cached_tokens"))
        if cached is None:
            cached = _usage_int(call.get("cache_read_input_tokens"))
        if cached is not None:
            rollup["cached_input_tokens"] = (
                rollup["cached_input_tokens"] or 0
            ) + cached
        cost = _usage_float(call.get("computed_cost_usd"))
        if cost is not None:
            rollup["computed_cost_usd"] = round(
                (rollup["computed_cost_usd"] or 0.0) + cost, 8
            )
        pair = {"model": call.get("model"), "provider": call.get("provider")}
        if pair not in rollup["models"]:
            rollup["models"].append(pair)
    return rollup


def usage_totals(agents: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Round-wide totals across the per-agent summaries."""
    totals: dict[str, Any] = {
        "calls": 0,
        "calls_missing_usage": 0,
        "calls_missing_cost": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cached_input_tokens": None,
        "computed_cost_usd": None,
    }
    for entry in agents.values():
        for key in (
            "calls",
            "calls_missing_usage",
            "calls_missing_cost",
            "input_tokens",
            "output_tokens",
            "total_tokens",
        ):
            totals[key] += _usage_int(entry.get(key)) or 0
        cached = _usage_int(entry.get("cached_input_tokens"))
        if cached is not None:
            totals["cached_input_tokens"] = (
                totals["cached_input_tokens"] or 0
            ) + cached
        cost = _usage_float(entry.get("computed_cost_usd"))
        if cost is not None:
            totals["computed_cost_usd"] = round(
                (totals["computed_cost_usd"] or 0.0) + cost, 8
            )
    return totals


def load_usage(working_dir: str | Path, version: int) -> dict[str, Any] | None:
    """Read ``.spec4/v{version}/usage.json``; None when missing or unreadable."""
    path = get_version_dir(working_dir, version) / USAGE_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


_COST_SUMMARY_EMPTY: dict[str, Any] = {
    "cost_usd": None,
    "calls": 0,
    "calls_missing_cost": 0,
    "calls_missing_usage": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cached_input_tokens": None,
}


def _cost_block(entry: Any) -> dict[str, Any]:
    """One agent's (or the totals') cost and token figures, shape-guarded.

    Tokens are the provider-reported sums over calls that returned usage;
    ``cached_input_tokens`` stays None when no call reported a cache read.
    """
    if not isinstance(entry, dict):
        return dict(_COST_SUMMARY_EMPTY)
    return {
        "cost_usd": _usage_float(entry.get("computed_cost_usd")),
        "calls": _usage_int(entry.get("calls")) or 0,
        "calls_missing_cost": _usage_int(entry.get("calls_missing_cost")) or 0,
        "calls_missing_usage": _usage_int(entry.get("calls_missing_usage")) or 0,
        "input_tokens": _usage_int(entry.get("input_tokens")) or 0,
        "output_tokens": _usage_int(entry.get("output_tokens")) or 0,
        "cached_input_tokens": _usage_int(entry.get("cached_input_tokens")),
    }


def cost_summary(
    working_dir: str | Path, version: int, agent: str
) -> dict[str, Any] | None:
    """The in-app cost card's numbers for one agent in one round.

    A read-time view over ``usage.json``: ``agent`` is that planning agent's
    rollup (sub-agents already folded in by :func:`save_usage`) and ``total``
    is the round's. ``None`` when the round has no usage file yet. An agent
    with no block yet reads as zero calls and no cost. The cost figures are
    LiteLLM's estimate and carry the same caveats as the file: a call that
    could not be priced is counted in ``calls_missing_cost`` and excluded
    from ``cost_usd``, so the caller can say so rather than show a confident
    undercount.
    """
    data = load_usage(working_dir, version)
    if data is None:
        return None
    agents = data.get("agents")
    entry = agents.get(agent) if isinstance(agents, dict) else None
    notes = data.get("notes")
    return {
        "round": str(data.get("round") or f"v{version}"),
        "agent": _cost_block(entry),
        "total": _cost_block(data.get("totals")),
        "cost_source": (
            notes.get("computed_cost_source") if isinstance(notes, dict) else None
        ),
    }


def _call_is_unpriced(call: dict[str, Any]) -> bool:
    """Whether one history record contributes no cost to the round's total.

    The same test :func:`summarize_usage` applies when it counts
    ``calls_missing_usage`` and ``calls_missing_cost``, written once and read
    from both places: a record that reported no usage at all, or one that
    reported usage LiteLLM had no price for. If these two ever disagreed, the
    named list below and the count beside it would describe different calls.
    """
    if call.get("usage_missing"):
        return True
    return _usage_float(call.get("computed_cost_usd")) is None


def unpriced_calls(agents: Any) -> list[dict[str, Any]]:
    """The round's unpriced calls, grouped by the agent and model that made
    them, in the order ``usage.json`` recorded them.

    Grouped rather than listed one by one because a re-run that failed to
    price is the *same* gap five times over, and a reader wants the model to
    go look up, not five identical rows. The agent is the rollup key the file
    is organised by (sub-agents already folded into their parent by
    :func:`save_usage`), so a name here is a name the agent table also shows.
    """
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    if not isinstance(agents, dict):
        return []
    for name, entry in agents.items():
        history = entry.get("history") if isinstance(entry, dict) else None
        for call in history or []:
            if not isinstance(call, dict) or not _call_is_unpriced(call):
                continue
            model = call.get("model")
            model = str(model) if isinstance(model, str) and model else ""
            key = (str(name), model)
            group = groups.setdefault(
                key, {"agent": str(name), "model": model, "calls": 0}
            )
            group["calls"] += 1
    return list(groups.values())


def round_cost(
    working_dir: str | Path | None, version: int | None
) -> dict[str, Any]:
    """The round's cost figures for the project view.

    A read-time view over ``usage.json``, like :func:`cost_summary` beside it,
    and it aggregates nothing of its own: ``total`` is the file's own
    ``totals`` block, which :func:`save_usage` recomputes from the full
    history on every write. The only thing read out of the histories here is
    *which* calls could not be priced, which the summaries count but do not
    name.

    Never None. No project directory, no round, no usage file, and a usage
    file recording nothing are the same answer to the only question this
    surface asks — nothing has been spent yet — and returning a record for all
    four spares the caller three more empty states to render.
    """
    data = (
        load_usage(working_dir, version)
        if working_dir is not None and version is not None
        else None
    )
    if not isinstance(data, dict):
        data = {}
    notes = data.get("notes")
    return {
        "round": str(data.get("round") or f"v{version if version is not None else 0}"),
        "total": _cost_block(data.get("totals")),
        "unpriced": unpriced_calls(data.get("agents")),
        "cost_source": (
            notes.get("computed_cost_source") if isinstance(notes, dict) else None
        ),
    }


def _write_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a sibling temp file and ``os.replace``.

    A crash or disk error mid-write leaves the previous file untouched; the
    temp file is removed on failure.
    """
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def save_usage(
    working_dir: str | Path,
    records: list[dict[str, Any]],
    version: int,
    fast_forward: bool | None = None,
) -> None:
    """Append per-call usage records to the round's ``usage.json``.

    Read-modify-write: the existing file (if any) is loaded, the new records
    are appended to their agent's ``history``, and every agent summary plus
    the round ``totals`` are recomputed from the full history. History is
    never overwritten, so a developer who quits and re-enters with a
    different provider keeps both runs side by side. The write is atomic.

    ``fast_forward`` is what the writer knows about the turn being recorded:
    ``True`` marks the round as having used Fast Forward (sticky), ``False``
    records a known non-FF turn only while nothing else is known, and
    ``None`` (a Designer draw, say) leaves the note as it was.

    Not a pipeline artifact: this file is an output of every agent and an
    input to none. It is declared in ``_NON_ARTIFACT_FILES`` and never
    appears in ``_STALE_DEPENDENCIES`` or ``_PIPELINE_ARTIFACT_ORDER``, so
    its mtime cannot make any agent read as Needs Update. Serialised under a
    lock because the chat persist funnel and the Designer thread can both
    flush.
    """
    if not records:
        return
    with _USAGE_LOCK:
        version_dir = ensure_version_dir(working_dir, version)
        now = datetime.now(timezone.utc).isoformat()
        existing = load_usage(working_dir, version) or {}

        agents_in = existing.get("agents")
        agents: dict[str, dict[str, Any]] = {}
        if isinstance(agents_in, dict):
            for name, entry in agents_in.items():
                history = entry.get("history") if isinstance(entry, dict) else None
                agents[str(name)] = {
                    "history": [h for h in (history or []) if isinstance(h, dict)]
                }
        for rec in records:
            agents.setdefault(usage_rollup_name(rec.get("agent")), {"history": []})[
                "history"
            ].append(rec)
        for name, entry in agents.items():
            history = entry["history"]
            agents[name] = {**summarize_usage(history), "history": history}

        notes_in = existing.get("notes")
        notes: dict[str, Any] = dict(notes_in) if isinstance(notes_in, dict) else {}
        notes["tokens_are_ground_truth"] = True
        notes["computed_cost_source"] = _USAGE_COST_SOURCE
        if fast_forward is True:
            notes["fast_forward"] = True
        elif fast_forward is False and notes.get("fast_forward") is None:
            notes["fast_forward"] = False
        else:
            notes.setdefault("fast_forward", None)

        spec4_version, litellm_version = _usage_versions()
        payload = {
            "schema_version": USAGE_SCHEMA_VERSION,
            "spec4_version": spec4_version,
            "litellm_version": litellm_version,
            "round": f"v{version}",
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
            "notes": notes,
            "agents": agents,
            "totals": usage_totals(agents),
        }
        _write_atomic(version_dir / USAGE_FILENAME, json.dumps(payload, indent=2))


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
    Routed through :func:`_write_text_if_changed` so an unchanged README is a
    no-op and does not bump mtimes the freshness model watches.
    """
    _write_text_if_changed(
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
    "brainstormer": ("vision.json", [("code review", "code_review.json")]),
    "agentifier": (
        "ai_features.json",
        [("vision", "vision.json"), ("code review", "code_review.json")],
    ),
    # StackAdvisor depends on Designer's *manifest* (the data model and screen
    # structure), not the visual mock: a purely visual change cannot invalidate a
    # stack choice, and inlining the mock's markup only crowded the context
    # (D-SC5c). The mock remains Phaser's and Deployer's dependency — they hand it
    # to the coding agent.
    "stack_advisor": (
        "stack.json",
        [
            ("vision", "vision.json"),
            ("AI features", "ai_features.json"),
            ("code review", "code_review.json"),
            ("design manifest", "design/manifest.json"),
        ],
    ),
    "phaser": (
        "phases",
        [
            ("vision", "vision.json"),
            ("AI features", "ai_features.json"),
            ("stack", "stack.json"),
            ("code review", "code_review.json"),
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
            ("AI features", "ai_features.json"),
            ("stack", "stack.json"),
            ("feature specs", "feature_specs.json"),
            ("phases", "phases"),
            ("UI mock", "design/mock.html"),
        ],
    ),
    "designer": (
        "design/mock.html",
        [("vision", "vision.json"), ("AI features", "ai_features.json")],
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
    "code_review.json",
    "vision.json",
    "ai_features.json",
    "design/mock.html",
    "stack.json",
    "phases",
    "deployment-plan.md",
]

# Inputs that must exist for an agent to be runnable at all (the Not-Ready gate),
# derived from `_validate_agent_preconditions`. Every other input listed in
# `_STALE_DEPENDENCIES` is optional: it joins the freshness chain only when
# present and never blocks. Agents absent from this map have no required inputs.
_REQUIRED_INPUTS: dict[str, list[str]] = {
    "agentifier": ["vision.json"],
    "designer": ["vision.json"],
    "stack_advisor": ["vision.json"],
    "phaser": ["vision.json", "stack.json"],
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
        return Path(working_dir).is_dir() and os.access(working_dir, os.R_OK)
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
    ``_default_session``, so "non-empty list" is the honest test for "this
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


def _artifact_button_state(
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
        if mtime("code_review.json") is not None:
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
    chain = [(rel, mtime(rel)) for rel in ordered]
    chain = [(rel, m) for rel, m in chain if m is not None]

    for (_, m_prev), (_, m_next) in zip(chain, chain[1:]):
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
