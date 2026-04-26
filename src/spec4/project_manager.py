"""Project directory management for Spec4.

Handles working directory selection, .spec4 artifact storage, and SPECMEM.md updates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SPECMEM_PLANNING_MARKER = "\n---\n\n## Spec4 Planning State"


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
    """Load vision.json, stack.json, code_review.json, and phases/*.json from .spec4/."""  # noqa: E501
    spec4_dir = get_spec4_dir(working_dir)
    result: dict[str, Any] = {  # noqa: E501
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
        path = spec4_dir / filename
        if path.exists():
            try:
                result[key] = json.loads(path.read_text())
            except Exception:
                pass

    phases_dir = spec4_dir / "phases"
    if phases_dir.exists():
        for pf in sorted(phases_dir.glob("phase*.json")):
            try:
                result["phases"].append(json.loads(pf.read_text()))
            except Exception:
                pass

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
    spec4_dir = ensure_spec4_dir(working_dir)
    phases_dir = spec4_dir / "phases"
    phases_dir.mkdir(exist_ok=True)
    for phase in phases:
        num = phase.get("phase_number", 0)
        (phases_dir / f"phase{num}.json").write_text(
            json.dumps(phase, indent=2), encoding="utf-8"
        )


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


def update_specmem_planning_state(  # noqa: E501
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
