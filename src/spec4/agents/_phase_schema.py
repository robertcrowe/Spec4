"""JSON Schema for a single Phaser `phase` artifact.

Phaser emits one fenced ```json``` block per phase, so each block is validated
independently against this schema. The schema captures the structural contract
that downstream agents (Deployer) and the coding agent consuming the phases
depend on:

- All required fields are present so renderers do not have to handle missing keys.
- `references[]` items have both `standard` and `url` (otherwise the rendered
  Markdown produces broken links).
- `instructions` is a non-empty list (a phase with no instructions is useless
  for a coding agent).
- `tech_stack_spec` has both `dependencies` and `configurations`.

The schema deliberately does NOT enforce content quality (instruction
specificity, verification executability) — those are guidance in the prompt;
schema validation only catches *shape* drift that would silently degrade the
downstream renderer.
"""

from __future__ import annotations

from typing import Any

import jsonschema


PHASE_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Spec4 phase (single phase object)",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "phase_number",
        "total_phases",
        "phase_title",
        "phase_summary",
        "features",
        "capabilities",
        "tech_stack_spec",
        "instructions",
        "risk_assessment",
        "verification",
    ],
    "properties": {
        "phase_number": {"type": "integer", "minimum": 1},
        "total_phases": {"type": "integer", "minimum": 1},
        "phase_title": {"type": "string", "minLength": 1},
        "phase_summary": {"type": "string", "minLength": 1},
        # D-PH2a: two declaration arrays, two id spaces — the array determines
        # the space, so a capability named after the feature it serves never
        # collides. `features[]` declares product-feature ids from the
        # Brainstormer spine (feature_specs.json); `capabilities[]` declares
        # AI catalog-node ids (ai_features.json, including infrastructure).
        # In both: `id` joins to the source artifact; `role` distinguishes the
        # phase that introduces the item from later phases that extend it; the
        # full spec attaches at every touching phase, so `scope_note` is the
        # sole place a phase's partial coverage is recorded — the spec is
        # never sliced. Both arrays are required but legitimately empty (a
        # steel-thread scaffold declares neither; a no-AI project always has
        # an empty `capabilities`).
        "features": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "role", "scope_note"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "role": {"enum": ["introduced", "extended"]},
                    "scope_note": {"type": "string"},
                },
            },
        },
        "capabilities": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "role", "scope_note"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "role": {"enum": ["introduced", "extended"]},
                    "scope_note": {"type": "string"},
                },
            },
        },
        "tech_stack_spec": {
            "type": "object",
            "additionalProperties": False,
            "required": ["dependencies", "configurations"],
            "properties": {
                "dependencies": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "configurations": {"type": "string"},
            },
        },
        "instructions": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
        "risk_assessment": {
            "type": "object",
            "additionalProperties": False,
            "required": ["potential_bottlenecks", "mitigation_strategy"],
            "properties": {
                "potential_bottlenecks": {"type": "string", "minLength": 1},
                "mitigation_strategy": {"type": "string", "minLength": 1},
            },
        },
        "verification": {"type": "string", "minLength": 1},
        "references": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["standard", "url"],
                "properties": {
                    "standard": {"type": "string", "minLength": 1},
                    "url": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}


def validate_phase(data: Any) -> list[str]:
    """Validate a single phase object against PHASE_SCHEMA.

    Returns a list of human-readable error messages (each formatted as
    "<path>: <message>"). Returns an empty list when the data validates.
    """
    validator = jsonschema.Draft7Validator(PHASE_SCHEMA)
    errors: list[str] = []
    for err in validator.iter_errors(data):
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{path}: {err.message}")
    return errors


def format_validation_errors_for_retry(
    failures: list[tuple[int | None, list[str]]],
    limit: int = 15,
) -> str:
    """Build the corrective user message that Phaser feeds back to the LLM.

    `failures` is a list of (phase_number, errors) tuples — one entry per
    bad phase block. `phase_number` may be None when the offending block did
    not contain a parseable `phase_number` field.
    """
    bullets: list[str] = []
    total = 0
    for phase_number, errors in failures:
        label = (
            f"Phase {phase_number}"
            if phase_number is not None
            else "Phase (number unparseable)"
        )
        for err in errors:
            if total >= limit:
                break
            bullets.append(f"- {label}: {err}")
            total += 1
        if total >= limit:
            break

    remaining = sum(len(errs) for _, errs in failures) - total
    truncated_note = (
        f"\n\n(plus {remaining} more — fix the structural issues above first)"
        if remaining > 0
        else ""
    )

    bullet_list = "\n".join(bullets)
    return (
        "One or more of the phase JSON blocks you just emitted failed schema "
        "validation. Re-emit the FULL set of phase blocks — one fenced "
        "```json``` code block per phase, back to back, no preface or "
        "explanation — fixing these specific issues:\n\n"
        f"{bullet_list}{truncated_note}\n\n"
        "Reminders that match the most common drift:\n"
        "- Every phase must include: phase_number (int), total_phases (int), "
        "phase_title (non-empty), phase_summary (non-empty), features (array; "
        "product-feature ids from the Feature specifications), capabilities "
        "(array; AI catalog-node ids — empty for a project with no AI "
        "features), tech_stack_spec "
        "(with both dependencies and configurations), instructions (non-empty "
        "list of strings), risk_assessment (with both potential_bottlenecks "
        "and mitigation_strategy), and verification (non-empty).\n"
        "- `references` items must each have both `standard` and `url`. "
        "Omit the array (or pass `[]`) if there are no references — never "
        "emit a reference with a missing or empty URL.\n"
        "- Do not add custom top-level keys; the schema is closed."
    )
