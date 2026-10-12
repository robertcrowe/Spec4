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

Step 3b (D-SC3-11, 2.7.0): a field may also be a ``scan.``-prefixed dotted
path, resolved against the envelope's computed ``scan`` layer instead of the
model's ``review``. Those blocks are measured facts — plan drift, dependency
delta, sampling coverage — and render under a "Scan …" heading rather than
"Existing …", so a consumer can tell what was computed from what was judged.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

__all__ = [
    "AGENT_REVIEW_VIEWS",
    "BRAINSTORMER_FIELD_GUIDANCE",
    "BRAINSTORMER_REVIEW_FIELDS",
    "EXCLUDED_PATHS",
    "FIELD_GUIDANCE",
    "PHASER_FIELD_GUIDANCE",
    "PHASER_REVIEW_FIELDS",
    "SCAN_PREFIX",
    "SCOUT_REVIEW_FIELDS",
    "STACK_FIELD_GUIDANCE",
    "STACK_REVIEW_FIELDS",
    "render_code_review",
    "unwrap_review",
    "unwrap_scan",
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
    # Step 3 (2.6.0) arrays — the shared lines; Phaser, StackAdvisor and
    # Brainstormer override the ones whose use differs (D-SC3-11).
    "load_bearing": (
        "The modules the rest of the code depends on, each with the contract its "
        "consumers rely on and how many of them there are. Changing one changes "
        "every consumer."
    ),
    "implemented": (
        "What the code already does, product-level, with how far along each one "
        "is. `prior_feature_ids` name the last round's features it realises."
    ),
    "integrations": (
        "The external services the code already talks to, with the module that "
        "holds each client and the variable names that configure it."
    ),
    # ``scan.`` paths (D-SC3-11): measured by the scan, never judged by the
    # model. Each line says what was measured and what to do with it.
    "scan.coverage": (
        "Measured: how much of the source the review's evidence covered. A "
        "module outside the sampled set was reviewed from its signatures or not "
        "at all — a phase that touches one verifies before it relies on a claim "
        "about it."
    ),
    "scan.plan_drift.planned_unmatched": (
        "Measured: technologies the last round's stack or phases named that no "
        "manifest declares and no module imports. They were never adopted or "
        "have since been dropped — do not carry them forward unexamined."
    ),
    "scan.plan_drift.declared_not_planned": (
        "Measured: dependencies a manifest declares that the last round's plan "
        "never named — adopted outside Spec4. Record them in the stack rather "
        "than proposing a parallel choice for the same purpose."
    ),
    "scan.delta.dependencies": (
        "Measured: declared dependencies added, removed or bumped since the "
        "prior scan, per manifest. These are recent, deliberate choices — keep "
        "them unless the vision says otherwise."
    ),
}

#: Prefix that routes a field to the envelope's computed ``scan`` layer
#: (D-SC3-11). Everything else resolves against ``review``.
SCAN_PREFIX = "scan."

#: Sub-keys no consumer view renders (D-CR6). ``entrypoints.ui_root`` reached
#: nothing in the BWS4 baseline and duplicates ``ui_summary.entry_files`` and
#: ``directory_map``; the schema still carries it for the transcript.
EXCLUDED_PATHS: frozenset[str] = frozenset({"entrypoints.ui_root"})

#: What Brainstormer reads from the review, in the order it is rendered. The
#: vision is about the product, so this is the review's product-facing half:
#: identity (how the project describes itself, its type, its shape), what is
#: already built (the UI, the routes, the AI in place, the standards wired in)
#: and what constrains new features (half-built areas, fragile ones). The
#: toolchain blocks are StackAdvisor's; commands and paths are Phaser's.
BRAINSTORMER_REVIEW_FIELDS: tuple[str, ...] = (
    "existing_self_description",
    "summary",
    "project_type",
    "architecture",
    "ui_summary",
    "api_surface",
    "implemented",
    "ai_capabilities",
    "protocols_implemented",
    "notes.incomplete_or_dead_code",
    "notes.change_risks",
)

#: Brainstormer's per-field rules. Blocks not listed here fall back to
#: :data:`FIELD_GUIDANCE`.
BRAINSTORMER_FIELD_GUIDANCE: dict[str, str] = {
    "existing_self_description": (
        "How the project describes itself. The vision's identity starts here — "
        "do not rename the project or re-derive what it is for."
    ),
    "summary": "What the scan found, in one paragraph.",
    "project_type": "Authoritative.",
    "architecture": (
        "The existing shape. New features fit into it unless the user asks for a "
        "restructure."
    ),
    "ui_summary": "What users already see. New features extend this surface.",
    "api_surface": (
        "What the product already does, route by route — the existing feature "
        "inventory. Never propose as new a capability that is already here."
    ),
    "implemented": (
        "Already built, with status. Never propose a `complete` one as new; a "
        "`partial`/`stub` one is a finish-or-remove question."
    ),
    "ai_capabilities": (
        "AI already in the codebase. These are existing features, not candidates; "
        "a new AI feature should say how it relates to them."
    ),
    "protocols_implemented": (
        "Standards already implemented. Features that touch them stay compatible."
    ),
    "notes.incomplete_or_dead_code": (
        "Half-built or abandoned areas. Before planning a feature that touches "
        "one, ask whether to finish it, remove it or leave it."
    ),
    "notes.change_risks": (
        "What is fragile. Respect these when asking about future features."
    ),
}

#: What Phaser reads from the review, in the order it is rendered. The view is
#: Phaser's only carrier of the review (D-EV6 retired the raw JSON block D-CR1
#: had kept alongside it): ``commands``, ``entrypoints`` and ``directory_map``
#: render verbatim through the generic walker, so what the coder receives is
#: still the review's own values, now beside the planning rule each governs.
PHASER_REVIEW_FIELDS: tuple[str, ...] = (
    "architecture",
    "load_bearing",
    "implemented",
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
    "scan.coverage",
)

#: Phaser's per-field rules, folded in from the paragraphs that used to follow
#: the paste (``_phaser_review_instruction``). Blocks not listed here fall back
#: to :data:`FIELD_GUIDANCE`.
PHASER_FIELD_GUIDANCE: dict[str, str] = {
    "load_bearing": (
        "A phase that touches a load-bearing module names, in its instructions "
        "and verification, the contract it preserves."
    ),
    "implemented": (
        "Already built, with status. Phases extend a `complete` capability "
        "rather than rebuild it; a `partial` or `stub` one a phase touches is "
        "finished or removed in that phase, as the vision decides."
    ),
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
    "integrations",
    "protocols_implemented",
    "api_surface",
    "env_vars",
    "commands.deploy",
    "notes.change_risks",
    "scan.plan_drift.planned_unmatched",
    "scan.plan_drift.declared_not_planned",
    "scan.delta.dependencies",
)

#: StackAdvisor's per-field rules (D-SC3-11). One block reads differently for
#: the stack than for anyone else: ``integrations`` is split by ``kind`` across
#: two of its topics. Blocks not listed here fall back to :data:`FIELD_GUIDANCE`.
STACK_FIELD_GUIDANCE: dict[str, str] = {
    "integrations": (
        "`llm_provider` entries are Topic 3's `providers`; the rest are your "
        "`integrations`, already in place."
    ),
}

#: What the Agentifier's Scout reads from the review, in the order it is
#: rendered (D-EV7; replaces the raw JSON paste in ``scout.py``). Scout
#: catalogues candidate AI capabilities against what the product is and what
#: AI it already has, so this is the identity half plus the AI-relevant
#: inventory: the self-description, type and shape; the AI already in place
#: and the frameworks and dependencies it rides on; the routes and standards
#: a new capability would attach to; and the half-built areas to avoid.
SCOUT_REVIEW_FIELDS: tuple[str, ...] = (
    "existing_self_description",
    "summary",
    "project_type",
    "architecture",
    "ai_capabilities",
    "api_surface",
    "protocols_implemented",
    "frameworks",
    "dependencies",
    "notes.incomplete_or_dead_code",
)

#: Per-agent view used on the revision path (``_turn_flow``'s "updated code
#: review" block, D-EV6 a′): the same tuple and guidance that agent's seed
#: renders, so the revised input is directly comparable to the original.
#: Keyed by the agent name ``project_manager.detect_stale_inputs`` uses.
#: Agents absent here (Deployer reads its own excerpt; the Agentifier seeds
#: through Scout) receive the ``review`` block as raw JSON instead.
AGENT_REVIEW_VIEWS: dict[str, tuple[tuple[str, ...], dict[str, str] | None]] = {
    "brainstormer": (BRAINSTORMER_REVIEW_FIELDS, BRAINSTORMER_FIELD_GUIDANCE),
    "stack_advisor": (STACK_REVIEW_FIELDS, STACK_FIELD_GUIDANCE),
    "phaser": (PHASER_REVIEW_FIELDS, PHASER_FIELD_GUIDANCE),
}


# ---------------------------------------------------------------------------
# Shape helpers
# ---------------------------------------------------------------------------


def _envelope(envelope: Any) -> dict[str, Any]:
    if not isinstance(envelope, dict):
        return {}
    inner = envelope.get("code_review")
    return inner if isinstance(inner, dict) else {}


def unwrap_review(envelope: Any) -> dict[str, Any]:
    """The ``review`` block of a stored ``code_review`` envelope, else ``{}``.

    By path only (D-EV5): ``envelope["code_review"]["review"]``. A bare v1
    review, a bare ``review`` dict, or anything that is not the schema-2
    envelope resolves to ``{}`` — a consumer handed the wrong shape renders
    nothing rather than a silently degraded view.
    """
    review = _envelope(envelope).get("review")
    return review if isinstance(review, dict) else {}


def unwrap_scan(envelope: Any) -> dict[str, Any]:
    """The computed ``scan`` layer of a stored envelope, else ``{}``."""
    scan = _envelope(envelope).get("scan")
    return scan if isinstance(scan, dict) else {}


def _resolve(node: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


#: Heading overrides where the key's own words read badly after "Existing",
#: and the headings of the ``scan.`` paths (D-SC3-11), which carry no
#: "Existing" — they are measurements, not the state of the code.
_HEADINGS = {
    "existing_self_description": "self-description",
    "commands.deploy": "deploy command",
    "api_surface": "API surface",
    "env_vars": "environment variables",
    "load_bearing": "load-bearing modules",
    "implemented": "implemented capabilities",
    "scan.coverage": "Scan coverage",
    "scan.plan_drift.planned_unmatched": "Planned last round, not found in the code",
    "scan.plan_drift.declared_not_planned": "Declared in a manifest, not planned",
    "scan.delta.dependencies": "Dependency changes since the prior scan",
}


def _label(key: str) -> str:
    return key.rsplit(".", 1)[-1].replace("_", " ")


def _is_scan_field(field: str) -> bool:
    return field.startswith(SCAN_PREFIX)


def _heading(field: str) -> str:
    """The bold heading for ``field``: "Existing …" for the review, not for scan."""
    if _is_scan_field(field):
        return _HEADINGS.get(field) or f"Scan {_label(field)}"
    return "Existing " + (_HEADINGS.get(field) or _label(field))


def _joined(values: Any, sep: str = "; ") -> str:
    """A list of strings as one ``sep``-joined run; a scalar as itself."""
    if isinstance(values, list):
        return sep.join(_scalar(v) for v in values if not _empty(v))
    return _scalar(values)


def _load_bearing_lines(entries: Any) -> list[str]:
    """``load_bearing`` (step 3): one entry per module, its contract beneath.

    The generic walker would fold the nested ``contract`` into the entry's
    line; here each contract key gets its own sub-bullet, as the transcript
    renderer prints it, and ``consumers`` is shown as a count — the list is
    the import graph's, in the JSON for anyone who needs the paths. An entry
    that is not a dict falls back to the walker, so nothing is dropped.
    """
    if not isinstance(entries, list):
        return _render_value(entries, "")
    lines: list[str] = []
    for entry in entries:
        if _empty(entry):
            continue
        if not isinstance(entry, dict):
            lines.extend(_render_list([entry], ""))
            continue
        lines.append(f"- {_load_bearing_head(entry)}{_provenance(entry)}")
        contract = entry.get("contract")
        if isinstance(contract, dict):
            for key in ("inputs", "outputs", "invariants", "side_effects"):
                if not _empty(contract.get(key)):
                    lines.append(f"  - {_label(key)}: {_joined(contract[key])}")
    return lines


def _load_bearing_head(entry: dict[str, Any]) -> str:
    """``**module** · `symbol` (consumers: n) — role``, each part when present."""
    head = f"**{_scalar(entry.get('module', ''))}**"
    if _text(entry.get("symbol")):
        head += f" · `{_scalar(entry['symbol'])}`"
    consumers = entry.get("consumers")
    if isinstance(consumers, list):
        head += f" (consumers: {len(consumers)})"
    if _text(entry.get("role")):
        head += f" — {_scalar(entry['role'])}"
    return head


def _coverage_line(coverage: Any) -> list[str]:
    """``scan.coverage`` as one line (D-SC3-11): counts, not the sampled paths.

    The coder does not need ``sampled[]``; it needs to know how much of the
    tree the review's claims rest on. Older scans without the 2.4.0 keys
    render the two counts alone; a coverage block without them renders
    nothing.
    """
    if not isinstance(coverage, dict):
        return []
    sampled = coverage.get("source_files_sampled")
    total = coverage.get("source_files_total")
    if not isinstance(sampled, int) or not isinstance(total, int):
        return []
    parts = [f"{sampled} of {total} source files shown as bodies"]
    signatures = coverage.get("signatures_shown")
    if isinstance(signatures, list) and signatures:
        parts.append(f"{len(signatures)} more as signature blocks")
    tokens = coverage.get("evidence_tokens")
    if isinstance(tokens, int) and tokens > 0:
        parts.append(f"~{tokens:,} tokens of evidence")
    return ["- " + "; ".join(parts)]


def _dependency_change_lines(delta: Any) -> list[str]:
    """``scan.delta.dependencies``: one line per manifest that changed.

    Each manifest shows its non-empty ``added`` / ``removed`` / ``bumped``
    lists and ``truncated`` only when true; a manifest with none of those is
    omitted, so the block says what moved and nothing else. The manifest
    name is printed whole — the walker's labeller would clip ``pyproject.toml``
    at its dot.
    """
    if not isinstance(delta, dict):
        return _render_value(delta, "")
    lines: list[str] = []
    for manifest, change in delta.items():
        if not isinstance(change, dict):
            if not _empty(change):
                lines.append(f"- **{manifest}** — {_joined(change)}")
            continue
        moved = [
            f"{key}: {_joined(change[key], sep=', ')}"
            for key in ("added", "removed", "bumped")
            if not _empty(change.get(key))
        ]
        if change.get("truncated") is True:
            moved.append("truncated: yes")
        if moved:
            lines.append(f"- **{manifest}** — {'; '.join(moved)}")
    return lines


#: Fields whose body is rendered by hand rather than by the generic walker:
#: the walker is total, but it flattens a nested entry to one line and
#: labels a dict key by its last dot-separated part, which these three
#: cannot afford. Every other field, scan or review, renders verbatim.
_RENDERERS: dict[str, Callable[[Any], list[str]]] = {
    "load_bearing": _load_bearing_lines,
    "scan.coverage": _coverage_line,
    "scan.delta.dependencies": _dependency_change_lines,
}


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


def _field_value(cr: dict[str, Any], scan: dict[str, Any], field: str) -> Any:
    """The value ``field`` names: from ``scan`` under the prefix, else ``cr``."""
    if _is_scan_field(field):
        return _resolve(scan, field[len(SCAN_PREFIX) :])
    return _without_excluded(field, _resolve(cr, field))


def _body(field: str, value: Any) -> list[str]:
    """The rendered body of ``field``: by hand for ``_RENDERERS``, else walked."""
    renderer = _RENDERERS.get(field)
    return renderer(value) if renderer is not None else _render_value(value, "")


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
    sub-key in :data:`EXCLUDED_PATHS`. ``review`` is the stored envelope
    (``session["code_review"]``); it is unwrapped by path. Returns ``""`` for
    a review that is not the envelope, not a software project, or contains
    none of the fields — the caller then emits nothing.

    A field under :data:`SCAN_PREFIX` (``scan.plan_drift.planned_unmatched``,
    ``scan.coverage``) resolves against the same envelope's computed ``scan``
    layer (D-SC3-11) and renders under a "Scan …" heading. The fields in
    ``_RENDERERS`` (``load_bearing``, ``scan.coverage``,
    ``scan.delta.dependencies``) render by hand — coverage to one line, the
    delta to the manifests that changed, contracts beneath their module;
    everything else walks. Scan fields are skipped like any other when the
    envelope has no scan — a review that is not a software project still
    renders nothing, scan or no scan.
    """
    cr = unwrap_review(review)
    if not cr or cr.get("is_software_project") is False:
        return ""
    scan = unwrap_scan(review)
    lines_for = {**FIELD_GUIDANCE, **(guidance or {})}
    blocks: list[str] = []
    for field in fields:
        value = _field_value(cr, scan, field)
        if _empty(value):
            continue
        body = _body(field, value)
        if not body:
            continue  # present, but every leaf was empty
        lines = [f"**{_heading(field)}**"]
        line = lines_for.get(field)
        if line:
            lines.append(f"_{line}_")
        lines.extend(body)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
