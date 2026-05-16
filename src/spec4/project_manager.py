"""Project directory management for Spec4.

Handles working directory selection, .spec4 artifact storage, and SPECMEM.md updates.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_SPECMEM_PLANNING_MARKER = "\n---\n\n## Spec4 Planning State"

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


# ---------------------------------------------------------------------------
# Artifact I/O
# ---------------------------------------------------------------------------


def load_spec4_artifacts(working_dir: str | Path) -> dict[str, Any]:
    """Load vision.json, stack.json, code_review.json, and phases/*.md (legacy *.json) from .spec4/."""  # noqa: E501
    spec4_dir = get_spec4_dir(working_dir)
    result: dict[str, Any] = {
        "vision": None,
        "stack": None,
        "code_review": None,
        "phases": [],
    }

    for key, filename in (
        ("vision", "vision.json"),
        ("stack", "stack.json"),
        ("code_review", "code_review.json"),
    ):
        try:
            result[key] = json.loads((spec4_dir / filename).read_text())
        except (OSError, json.JSONDecodeError):
            pass

    phases_dir = spec4_dir / "phases"
    # Primary format is .md (frontmatter holds the structured phase JSON).
    # Legacy .json files are still read so projects produced by older Spec4
    # versions keep working without a manual migration step.
    seen_numbers: set[int] = set()

    def _by_number(p: Path) -> tuple[int, str]:
        m = re.match(r"phase(\d+)", p.stem)
        return (int(m.group(1)) if m else 0, p.name)

    for pf in sorted(phases_dir.glob("phase*.md"), key=_by_number):
        phase = parse_phase_markdown(pf.read_text(encoding="utf-8"))
        if phase is not None:
            result["phases"].append(phase)
            num = phase.get("phase_number")
            if isinstance(num, int):
                seen_numbers.add(num)
    for pf in sorted(phases_dir.glob("phase*.json"), key=_by_number):
        try:
            phase = json.loads(pf.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        num = phase.get("phase_number")
        if isinstance(num, int) and num in seen_numbers:
            continue
        result["phases"].append(phase)

    return result


def save_vision(working_dir: str | Path, vision: dict[str, Any]) -> None:
    spec4_dir = ensure_spec4_dir(working_dir)
    (spec4_dir / "vision.json").write_text(
        json.dumps(vision, indent=2), encoding="utf-8"
    )


def save_stack(working_dir: str | Path, stack: dict[str, Any]) -> None:
    spec4_dir = ensure_spec4_dir(working_dir)
    (spec4_dir / "stack.json").write_text(json.dumps(stack, indent=2), encoding="utf-8")


def save_code_review(working_dir: str | Path, review: dict[str, Any]) -> None:
    spec4_dir = ensure_spec4_dir(working_dir)
    (spec4_dir / "code_review.json").write_text(
        json.dumps(review, indent=2), encoding="utf-8"
    )


def save_phases(working_dir: str | Path, phases: list[dict[str, Any]]) -> None:
    """Write each phase as a Markdown-with-JSON-frontmatter file.

    The coding agent reads the prose body; Spec4 itself round-trips through
    the frontmatter JSON when reloading the project. Any pre-existing
    `phase{N}.json` from older Spec4 versions is removed once the matching
    `.md` lands so the directory does not accumulate two copies of every
    phase.
    """
    spec4_dir = ensure_spec4_dir(working_dir)
    phases_dir = spec4_dir / "phases"
    phases_dir.mkdir(exist_ok=True)
    for phase in phases:
        num = phase.get("phase_number", 0)
        md_path = phases_dir / f"phase{num}.md"
        md_path.write_text(render_phase_markdown(phase), encoding="utf-8")
        legacy = phases_dir / f"phase{num}.json"
        if legacy.exists():
            legacy.unlink()


# ---------------------------------------------------------------------------
# Phase Markdown serialization
# ---------------------------------------------------------------------------


def render_phase_markdown(phase: dict[str, Any]) -> str:
    """Render a phase dict as Markdown with JSON frontmatter.

    Frontmatter carries the canonical structured payload (full round-trip);
    the body renders the same fields as prose for the coding agent.
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
        "## Tech Stack",
        "",
    ]
    if deps:
        lines.append("**Dependencies:**")
        lines.append("")
        lines.extend(f"- {d}" for d in deps)
        lines.append("")
    if configs:
        lines.append(f"**Configurations:** {configs}")
        lines.append("")
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


def save_deployment_plan(working_dir: str | Path, markdown: str) -> None:
    spec4_dir = ensure_spec4_dir(working_dir)
    (spec4_dir / "deployment-plan.md").write_text(markdown, encoding="utf-8")


def load_deployment_plan(working_dir: str | Path) -> str | None:
    path = get_spec4_dir(working_dir) / "deployment-plan.md"
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        return None


# ---------------------------------------------------------------------------
# Staleness detection
# ---------------------------------------------------------------------------

# Maps each agent to (output artifact rel path, [(input name, input rel path)…]).
# Output and input paths are relative to .spec4/. A directory is treated as the
# newest mtime among its files.
_STALE_DEPENDENCIES: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "brainstormer": ("vision.json", [("code review", "code_review.json")]),
    "stack_advisor": (
        "stack.json",
        [
            ("vision", "vision.json"),
            ("code review", "code_review.json"),
            ("UI mock", "design/mock.html"),
        ],
    ),
    "phaser": (
        "phases",
        [
            ("vision", "vision.json"),
            ("stack", "stack.json"),
            ("code review", "code_review.json"),
            ("UI mock", "design/mock.html"),
        ],
    ),
    "deployer": (
        "deployment-plan.md",
        [
            ("stack", "stack.json"),
            ("phases", "phases"),
            ("UI mock", "design/mock.html"),
        ],
    ),
    "designer": ("design/mock.html", [("vision", "vision.json")]),
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
    spec4_dir = get_spec4_dir(working_dir)
    output_mtime = _path_mtime(spec4_dir / output_rel)
    if output_mtime is None:
        return {}
    stale: dict[str, float] = {}
    for name, rel in inputs:
        input_mtime = _path_mtime(spec4_dir / rel)
        if input_mtime is not None and input_mtime > output_mtime:
            stale[name] = input_mtime
    return stale


# ---------------------------------------------------------------------------
# SPECMEM helpers
# ---------------------------------------------------------------------------


def read_specmem(working_dir: str | Path) -> str | None:
    path = get_spec4_dir(working_dir) / "SPECMEM.md"
    if path.exists():
        try:
            return path.read_text()
        except OSError:
            pass
    return None


def write_specmem(working_dir: str | Path, content: str) -> None:
    spec4_dir = ensure_spec4_dir(working_dir)
    (spec4_dir / "SPECMEM.md").write_text(content, encoding="utf-8")


def update_specmem_planning_state(
    working_dir: str | Path, session: dict[str, Any]
) -> None:
    """Append or replace the Spec4 Planning State section in SPECMEM.md."""
    existing = read_specmem(working_dir) or ""

    # Strip any existing planning state section
    if _SPECMEM_PLANNING_MARKER in existing:
        existing = existing[: existing.index(_SPECMEM_PLANNING_MARKER)]

    vision = session.get("vision_statement")
    stack = session.get("stack_statement")
    phases = session.get("phases", [])

    vision_section = (
        f"### Vision Statement\n```json\n{json.dumps(vision, indent=2)}\n```\n\n"
        if vision
        else ""
    )
    stack_section = (
        f"### Stack Spec\n```json\n{json.dumps(stack, indent=2)}\n```\n\n"
        if stack
        else ""
    )
    if phases:
        phase_lines = "\n".join(
            f"- Phase {p.get('phase_number')}: {p.get('phase_title', '')}"
            for p in phases
        )
        phases_section = f"### Phases ({len(phases)} total)\n{phase_lines}\n\n"
    else:
        phases_section = ""

    addition = (
        f"{_SPECMEM_PLANNING_MARKER}\n\n"
        f"*Last updated by Spec4*\n\n"
        f"{vision_section}{stack_section}{phases_section}"
    )
    write_specmem(working_dir, existing.rstrip() + addition)
