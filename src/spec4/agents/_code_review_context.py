"""Deterministic, per-consumer views of CodeScanner's ``code_review``.

Brownfield's entire input to Brainstormer, StackAdvisor and Phaser was a
``json.dumps(code_review)`` paste followed by a field-instruction paragraph
that differed per seed and named a different subset of the schema each time.
The probe (``evals/code_scanner/review_reach.py``, BWS4 v1–v8 baseline) showed
what that shape costs: fields a seed names reach the plan, fields it does not
name mostly do not, and in StackAdvisor's case the review's ``coding_style``
lost to the prompt exemplar's toolchain in eight rounds out of eight — every
stack recorded ``ESLint + @typescript-eslint`` / ``Prettier`` for a frontend
whose review said ``oxlint``.

This module is the same treatment the Deployer stack paste received
(``_stack_context.stack_for_deployer``, D-CR series): one renderer, and a
field tuple per consumer that says exactly which blocks that consumer reads
and, per block, the one line of guidance that consumer needs. Rendering is
lossless and verbatim — values are emitted as they stand, never paraphrased;
provenance (``source`` / ``inferred_from``) rides along in brackets because it
is what lets the model tell a fact from an inference.

It is a **leaf**, like ``feature_specs.py``: it imports nothing from
``spec4.agents`` or ``spec4.project_manager``. Keep it that way.

The renderer is total (D-SC33's rule, applied here): any JSON shape under any
key renders through the generic walker, so a schema field this module has no
special knowledge of still reaches the seed rather than vanishing.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "EXCLUDED_PATHS",
    "FIELD_GUIDANCE",
    "PHASER_FIELD_GUIDANCE",
    "PHASER_REVIEW_FIELDS",
    "STACK_REVIEW_FIELDS",
    "render_code_review",
]

#: Provenance keys: rendered in brackets after the value they annotate.
_PROVENANCE = ("source", "inferred_from", "_source")

#: Keys promoted to the front of a list entry's line, in order of preference.
_PRIMARY_KEYS = (
    "name",
    "engine",
    "path_or_method",
    "path",
    "area",
    "platform",
    "tool",
    "mechanism",
)

#: One line of guidance per field, shown under its heading. Consumers share
#: these; a tuple selects which fields (and so which lines) a consumer sees.
FIELD_GUIDANCE: dict[str, str] = {
    "existing_self_description": "How the project describes itself, verbatim.",
    "architecture": (
        "The existing pattern. Extend it rather than restructure it unless the "
        "vision says otherwise."
    ),
    "languages": "Authoritative. Every language listed is in the codebase today.",
    "runtime_versions": "Authoritative. Carry these versions forward as the floor.",
    "frameworks": "Authoritative. Already in use; a swap is a migration, not a choice.",
    "dependencies": (
        "Authoritative. Already declared; prefer them over a parallel library for "
        "the same purpose."
    ),
    "build_system": "Authoritative. The existing build tool and manifest.",
    "coding_style": (
        "The existing toolchain and conventions, authoritative per language. Carry "
        "them forward exactly — the linter, formatter, type checker, indentation and "
        "quote style the codebase already uses. Do not substitute other tools."
    ),
    "persistence": (
        "The existing data layer: engines, ORM, migration tool and migrations path."
    ),
    "deployment": "How the project already ships: containers, orchestration, PaaS, IaC.",
    "auth": "The existing authentication model, provider and library.",
    "protocols_implemented": (
        "Industry standards already wired in. Treat them as constraints when "
        "proposing changes."
    ),
    "api_surface": "The existing routes and methods. Extend rather than parallel-invent.",
    "env_vars": "Configuration the code already reads. Names only; never values.",
    "commands.deploy": "The existing deploy command.",
    "notes.change_risks": (
        "Typed observations about what is fragile. Weigh them before proposing a "
        "technology swap."
    ),
}

#: Sub-keys no consumer view renders (D-CR6). ``entrypoints.ui_root`` reached
#: nothing in the BWS4 baseline and duplicates ``ui_summary.entry_files`` and
#: ``directory_map``; the schema still carries it for the transcript.
EXCLUDED_PATHS: frozenset[str] = frozenset({"entrypoints.ui_root"})

#: What Phaser reads from the review, in the order it is rendered. Phaser
#: keeps the raw JSON block alongside this view (D-CR1): it hands
#: ``directory_map`` and ``commands`` through to the coder verbatim and the
#: raw block is the cheapest lossless carrier. The view is where each block's
#: planning rule sits next to the data it governs.
PHASER_REVIEW_FIELDS: tuple[str, ...] = (
    "architecture",
    "commands",
    "entrypoints",
    "directory_map",
    "build_system",
    "persistence",
    "env_vars",
    "api_surface",
    "protocols_implemented",
    "notes.incomplete_or_dead_code",
    "notes.change_risks",
    "notes.test_coverage",
)

#: Phaser's per-field rules, folded in from the paragraphs that used to follow
#: the paste (``_phaser_review_instruction``). Blocks not listed here fall back
#: to :data:`FIELD_GUIDANCE`.
PHASER_FIELD_GUIDANCE: dict[str, str] = {
    "commands": (
        "Authoritative. Use `test` to write each phase's verification criterion; "
        "`build`, `lint` and `typecheck` are the gates every phase must pass."
    ),
    "entrypoints": (
        "Authoritative. Phase 1 is an integration thread for the existing app "
        "that starts from these, not a from-scratch scaffold."
    ),
    "directory_map": "Ground every instruction in these real paths.",
    "build_system": "Authoritative. Build and install through this tool and manifest.",
    "persistence": (
        "The existing data layer. Phase 1's steel thread must verify the "
        "connection to every engine listed; every DB-touching phase runs "
        "migrations via the migration tool against the migrations path. Do not "
        "propose a different ORM or migration tool without explicit user approval."
    ),
    "env_vars": (
        "List every `required: yes` variable in Phase 1's "
        "`tech_stack_spec.configurations` and verify it in Phase 1's verification "
        "step (a clear error when missing). Names only — never values; values "
        "belong in the developer's secret store. A later phase that depends on a "
        "variable names it in its own `tech_stack_spec.configurations`."
    ),
    "api_surface": (
        "Anchor any phase that proposes API changes on these routes — extend "
        "rather than parallel-invent — and match each `protocol`'s conventions "
        "(HTTP verb+path, gRPC service.method, GraphQL operation) when describing "
        "new endpoints."
    ),
    "protocols_implemented": (
        "Industry standards the project already implements. Cite each "
        "protocol's canonical doc URL in the corresponding phase's `references` "
        "array."
    ),
    "notes.incomplete_or_dead_code": (
        "Do not extend any of this in a phase unless explicitly asked."
    ),
    "notes.change_risks": (
        "Apply each mitigation hint in the phases that touch its area."
    ),
    "notes.test_coverage": (
        "Where tests exist today. A phase that touches an uncovered module adds "
        "its tests in that phase."
    ),
}

#: What StackAdvisor reads from the review, in the order it is rendered. Chosen
#: from the BWS4 baseline: every block that names a technology, version, tool,
#: route, variable or risk the stack must carry forward. ``commands`` other than
#: ``deploy``, ``entrypoints``, ``directory_map`` and ``ui_summary`` are Phaser's
#: and Brainstormer's concerns, not the stack's.
STACK_REVIEW_FIELDS: tuple[str, ...] = (
    "existing_self_description",
    "architecture",
    "languages",
    "runtime_versions",
    "frameworks",
    "dependencies",
    "build_system",
    "coding_style",
    "persistence",
    "deployment",
    "auth",
    "protocols_implemented",
    "api_surface",
    "env_vars",
    "commands.deploy",
    "notes.change_risks",
)


# ---------------------------------------------------------------------------
# Shape helpers
# ---------------------------------------------------------------------------


def _unwrap(review: Any) -> dict[str, Any]:
    if not isinstance(review, dict):
        return {}
    inner = review.get("code_review")
    return inner if isinstance(inner, dict) else review


def _resolve(node: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


#: Heading overrides where the key's own words read badly after "Existing".
_HEADINGS = {
    "existing_self_description": "self-description",
    "commands.deploy": "deploy command",
    "api_surface": "API surface",
    "env_vars": "environment variables",
}


def _label(key: str) -> str:
    return key.rsplit(".", 1)[-1].replace("_", " ")


def _heading(field: str) -> str:
    return _HEADINGS.get(field) or _label(field)


def _empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return not value
    return False


def _provenance(entry: dict[str, Any]) -> str:
    parts = [str(entry[k]).strip() for k in _PROVENANCE if _text(entry.get(k))]
    return f" [{'; '.join(parts)}]" if parts else ""


def _private(key: Any) -> bool:
    """Provenance, or an underscore-prefixed key (the transcript renderer's rule)."""
    k = str(key)
    return k in _PROVENANCE or k.startswith("_")


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_annotated_scalar(value: Any) -> bool:
    """``{"value": X, "source": ...}`` — a scalar with provenance (coding_style)."""
    return (
        isinstance(value, dict)
        and "value" in value
        and all(k == "value" or _private(k) for k in value)
    )


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value).strip()


# ---------------------------------------------------------------------------
# The generic walker (total)
# ---------------------------------------------------------------------------


def _render_value(value: Any, indent: str) -> list[str]:
    """Render any JSON value as markdown lines at ``indent``."""
    if _is_annotated_scalar(value):
        return [f"{indent}{_scalar(value['value'])}{_provenance(value)}"]
    if isinstance(value, dict):
        return _render_dict(value, indent)
    if isinstance(value, list):
        return _render_list(value, indent)
    return [f"{indent}{_scalar(value)}"]


def _render_dict(node: dict[str, Any], indent: str) -> list[str]:
    lines: list[str] = []
    prov = _provenance(node)
    for key, val in node.items():
        if _private(key) or _empty(val):
            continue
        label = _label(str(key))
        if _is_annotated_scalar(val) or not isinstance(val, (dict, list)):
            lines.append(f"{indent}- {label}: {_render_value(val, '')[0]}")
        elif isinstance(val, dict) and _has_primary(val):
            lines.append(f"{indent}- {label}: {_entry_line(val)}")
        else:
            lines.append(f"{indent}- {label}:")
            lines.extend(_render_value(val, indent + "  "))
    if prov and lines:
        lines[-1] = lines[-1] + prov
    return lines


def _render_list(items: list[Any], indent: str) -> list[str]:
    lines: list[str] = []
    for item in items:
        if _empty(item):
            continue
        if isinstance(item, dict):
            lines.append(f"{indent}- {_entry_line(item)}")
        elif isinstance(item, list):
            lines.append(f"{indent}-")
            lines.extend(_render_list(item, indent + "  "))
        else:
            lines.append(f"{indent}- {_scalar(item)}")
    return lines


def _has_primary(entry: dict[str, Any]) -> bool:
    return any(_text(entry.get(k)) for k in _PRIMARY_KEYS)


def _entry_line(entry: dict[str, Any]) -> str:
    """One list entry on one line: primary key first, the rest as ``k: v``."""
    primary = next((k for k in _PRIMARY_KEYS if _text(entry.get(k))), None)
    head = f"**{_scalar(entry[primary])}**" if primary else ""
    rest: list[str] = []
    for key, val in entry.items():
        if key == primary or _private(key) or _empty(val):
            continue
        if isinstance(val, (dict, list)) and not _is_annotated_scalar(val):
            inner = "; ".join(
                line.strip().lstrip("- ") for line in _render_value(val, "")
            )
            rest.append(f"{_label(str(key))}: {inner}")
        else:
            rest.append(f"{_label(str(key))}: {_render_value(val, '')[0]}")
    body = " — ".join(part for part in (head, "; ".join(rest)) if part)
    return body + _provenance(entry)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def _without_excluded(field: str, value: Any) -> Any:
    """``value`` with every :data:`EXCLUDED_PATHS` entry under ``field`` removed."""
    if not isinstance(value, dict):
        return value
    prefix = field + "."
    dropped = {p[len(prefix) :] for p in EXCLUDED_PATHS if p.startswith(prefix)}
    if not dropped:
        return value
    return {k: v for k, v in value.items() if str(k) not in dropped}


def render_code_review(
    review: Any,
    fields: tuple[str, ...],
    *,
    guidance: dict[str, str] | None = None,
) -> str:
    """Render the selected ``fields`` of ``review`` as a markdown block.

    ``fields`` are top-level keys or dotted paths (``notes.change_risks``,
    ``commands.deploy``), rendered in the order given under a bold heading
    each, with that field's guidance line when one exists: ``guidance``
    overrides :data:`FIELD_GUIDANCE` per field, so a consumer whose use of a
    block differs (Phaser's ``persistence`` is a Phase 1 verification rule,
    StackAdvisor's is a carry-forward fact) says so next to the data. A field
    absent from the review, or present but empty, is skipped, as is any
    sub-key in :data:`EXCLUDED_PATHS`. Returns ``""`` for a review that is not
    a dict, not a software project, or contains none of the fields — the
    caller then emits nothing.
    """
    cr = _unwrap(review)
    if not cr or cr.get("is_software_project") is False:
        return ""
    lines_for = {**FIELD_GUIDANCE, **(guidance or {})}
    blocks: list[str] = []
    for field in fields:
        value = _without_excluded(field, _resolve(cr, field))
        if _empty(value):
            continue
        body = _render_value(value, "")
        if not body:
            continue  # present, but every leaf was empty
        lines = [f"**Existing {_heading(field)}**"]
        line = lines_for.get(field)
        if line:
            lines.append(f"_{line}_")
        lines.extend(body)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
