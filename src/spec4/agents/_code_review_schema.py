"""JSON Schemas for the CodeScanner `code_review` artifact (schema_version 2).

Two shapes, one property vocabulary:

- `REVIEW_BLOCK_SCHEMA` — what the LLM emits: `{"review": {...}}`.
- `CODE_REVIEW_SCHEMA` — what is stored: `{"code_review": {"schema_version",
  "scan", "review"}}`. `scan` is computed by code and never shown to the
  scanner's model; `review` is the model's block, attached at commit.

The `review` vocabulary captures the *structural* contract that downstream
agents depend on: closed canonical key vocabularies for `commands` and
`entrypoints`, the `ui_summary.kind` enum, the closed `notes.*` shape, and
entry-array item shapes. It does NOT enforce conditional required fields
(`project_type`, `languages`, etc. when `is_software_project` is true) —
those are guidance in the prompt, and a soft miss should not trigger a
costly retry.

The schemas are consumed in three places:

1. `validate_review_block(data)` — called after every JSON extraction in
   `code_scanner.run()`. If validation fails, the agent re-streams once
   with `response_format={"type": "json_object"}` and a corrective user
   message listing the specific errors, on providers that support it.

2. `validate_code_review(data)` — called on the assembled envelope at
   `_scanner_commit`, so a wrapping bug fails loudly.

3. Tests assert structural rules survive prompt edits.
"""

from __future__ import annotations

from typing import Any

import jsonschema


# The ``schema_version`` every review this Spec4 writes carries, and the one
# ``project_manager.code_review_needs_rescan`` compares a round's on-disk review
# against. A review written under an older value is not read as current: the
# /agents page gates the round until CodeScanner re-scans (D-SV1). Bumped only
# when the artifact's shape changes in a way downstream consumers must follow.
# 2: the ``{scan, review}`` envelope (CodeScanner v2 step 1a). Step 3's three
# ``review`` arrays (2.6.0) and step 4's three (2.8.0) are optional additions
# and do not bump it.
CODE_REVIEW_SCHEMA_VERSION = 2


_PROVENANCE_FIELDS: dict[str, dict[str, str]] = {
    "source": {"type": "string"},
    "inferred_from": {"type": "string"},
}


_NAMED_WITH_PROVENANCE: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        **_PROVENANCE_FIELDS,
    },
    "required": ["name"],
    "additionalProperties": False,
}


_STYLE_FIELD: dict[str, Any] = {
    "anyOf": [
        {"type": "string"},
        {"type": "number"},
        {"type": "integer"},
        {
            "type": "object",
            "properties": {
                "value": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "number"},
                        {"type": "integer"},
                    ]
                },
                **_PROVENANCE_FIELDS,
            },
            "required": ["value"],
            "additionalProperties": False,
        },
    ]
}


# Closed enum — load-bearing for Deployer/Phaser auth-handling decisions.
_AUTH_MODELS = [
    "session",
    "jwt",
    "oauth",
    "sso",
    "api_key",
    "basic",
    "mtls",
    "none",
    "other",
]


# Closed enum — keeps api_surface shape uniform across protocol families so
# Phaser can branch on a fixed set when proposing API changes.
_API_PROTOCOLS = [
    "http",
    "graphql",
    "grpc",
    "websocket",
    "rpc",
    "other",
]


_PERSISTENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "databases": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "engine": {"type": "string"},
                    "name": {"type": "string"},
                    # Free-text role (primary, cache, search, queue, ...);
                    # not enumerated because the long tail is genuinely open.
                    "role": {"type": "string"},
                    **_PROVENANCE_FIELDS,
                },
                "required": ["engine"],
            },
        },
        "orm": _NAMED_WITH_PROVENANCE,
        "migration_tool": _NAMED_WITH_PROVENANCE,
        "migrations_path": {"type": "string"},
    },
}


_ENV_VAR_ITEM: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        # NAME only — values are a security boundary and must never appear here.
        "name": {"type": "string"},
        "purpose": {"type": "string"},
        "required": {"type": "boolean"},
        **_PROVENANCE_FIELDS,
    },
    "required": ["name"],
}


_DEPLOYMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "containerization": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "tool": {"type": "string"},
                "dockerfile_path": {"type": "string"},
                "compose_path": {"type": "string"},
                "base_image": {"type": "string"},
                **_PROVENANCE_FIELDS,
            },
        },
        "orchestration": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "tool": {"type": "string"},
                "manifests_path": {"type": "string"},
                **_PROVENANCE_FIELDS,
            },
        },
        "paas": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "platform": {"type": "string"},
                "config_path": {"type": "string"},
                **_PROVENANCE_FIELDS,
            },
        },
        "iac": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "tool": {"type": "string"},
                "path": {"type": "string"},
                **_PROVENANCE_FIELDS,
            },
        },
    },
}


_API_SURFACE_ITEM: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "protocol": {"type": "string", "enum": _API_PROTOCOLS},
        # For http: e.g. "GET /users/:id". For grpc/rpc: the method name.
        # For graphql: the operation name. Free-form by design.
        "path_or_method": {"type": "string"},
        "handler": {"type": "string"},
        "summary": {"type": "string"},
        **_PROVENANCE_FIELDS,
    },
    "required": ["protocol", "path_or_method"],
}


_AUTH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "model": {"type": "string", "enum": _AUTH_MODELS},
        "provider": {"type": "string"},
        "library": {"type": "string"},
        **_PROVENANCE_FIELDS,
    },
}


# Closed enum — load-bearing for the Agentifier bias-toward-reuse passes
# (tier_analyst._existing_ai_context and the cross-cutting analyst), which
# render `kind` verbatim into prompts.
_AI_CAPABILITY_KINDS: list[str] = [
    "llm_api",
    "embedding",
    "vector_store",
    "ml_model",
    "rag",
    "agent_framework",
    "other",
]


# Existing AI/ML usage, recorded once at scan time by the model that read the
# code. Without this field Agentifier reconstructs "what AI already exists"
# from a keyword scan of dependency names, which misses local models, in-house
# pipelines, and anything with a non-obvious package name — and existing AI
# infrastructure gets re-proposed from scratch.
_AI_CAPABILITIES_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "kind": {"type": "string", "enum": _AI_CAPABILITY_KINDS},
            "description": {"type": "string"},
            "location": {"type": "string"},
            **_PROVENANCE_FIELDS,
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}


# Closed enum — load-bearing for Brainstormer (a ``complete`` capability is
# never proposed as new) and step 4's reconciliation verdicts (D-SC3-7).
_IMPLEMENTED_STATUSES: list[str] = [
    "complete",
    "partial",
    "stub",
    "scaffolded_only",
]


# Closed enum — StackAdvisor's open ``integrations.kind`` vocabulary plus the
# four kinds CodeScanner sees that StackAdvisor files elsewhere (``llm_provider``
# in its ``providers``; ``database``/``cache``/``queue`` in its ``persistence``),
# so a consumer can route each entry by ``kind`` alone (D-SC3-5).
_INTEGRATION_KINDS: list[str] = [
    "llm_provider",
    "web_search",
    "database",
    "cache",
    "queue",
    "object_storage",
    "identity_provider",
    "email_service",
    "payment",
    "mcp_server",
    "third_party_api",
    "other",
]


def _str_list() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


# Step 3 (D-SC3-3): a module the rest of the code depends on, with the
# contract its consumers rely on. ``consumers`` is code-owned — filled at
# ``wrap_review`` from ``scan.module_graph`` by ``module`` path (D-SC3-4) — and
# is permitted here so an update-mode re-emission that carries the prior value
# forward does not trip a retry; commit always overwrites it.
_LOAD_BEARING_ITEM: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["module", "role", "contract"],
    "properties": {
        "module": {"type": "string"},
        "symbol": {"type": "string"},
        "role": {"type": "string"},
        "contract": {
            "type": "object",
            "additionalProperties": False,
            "minProperties": 1,
            "properties": {
                "inputs": _str_list(),
                "outputs": _str_list(),
                "invariants": _str_list(),
                "side_effects": _str_list(),
            },
        },
        "consumers": _str_list(),
        **_PROVENANCE_FIELDS,
    },
}


# Step 3 (D-SC3-7): what the code already does, product-level, with how far
# along it is. ``prior_feature_ids`` name product-feature ids from the prior
# round (vision / feature-spec id space — never AI-catalog ids, which is why
# this array is ``implemented`` and not ``capabilities``, D-SC3-2); they are
# not validated at commit, so step 4 can judge an id outside the list.
_IMPLEMENTED_ITEM: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "name", "status", "paths"],
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "description": {"type": "string"},
        "status": {"type": "string", "enum": _IMPLEMENTED_STATUSES},
        "paths": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "prior_feature_ids": _str_list(),
        **_PROVENANCE_FIELDS,
    },
}


# Step 3 (D-SC3-5): an index of the external services the code talks to,
# cross-referencing ``ai_capabilities`` / ``persistence`` / ``env_vars`` by
# name. ``config_env_vars`` is NAME-ONLY, as ``env_vars`` is.
_INTEGRATION_ITEM: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "kind"],
    "properties": {
        "name": {"type": "string"},
        "kind": {"type": "string", "enum": _INTEGRATION_KINDS},
        "client_module": {"type": "string"},
        "config_env_vars": _str_list(),
        "purpose": {"type": "string"},
        **_PROVENANCE_FIELDS,
    },
}


# Closed enum — step 4's reconciliation verdict (D-SC4-3). Code-owned: a
# pure function of ``implemented[]`` and the prior round's phases, computed
# at ``wrap_review``. ``unassessed`` is for a phase that declared no
# features — the plan's three values cannot say "nothing to check".
_RECONCILIATION_VERDICTS: list[str] = [
    "evidence_found",
    "evidence_partial",
    "no_evidence_found",
    "unassessed",
]


# Closed enum — code-owned at ``wrap_review`` (D-SC4-4): ``out_of_round``
# when a change touches a file committed since the round boundary or added
# since the prior scan; ``in_round`` needs the round's start, which the scan
# does not carry yet (D-SC4-5, 4b); ``unknown`` otherwise.
_UNPLANNED_CLASSIFICATIONS: list[str] = ["in_round", "out_of_round", "unknown"]


# Closed enums — ``divergences[]`` is the judgment half of plan drift
# (D-SC4-7): a planned fact whose counterpart in this review has a different
# name or shape. Dependency names are never here; ``scan.plan_drift`` has them.
_DIVERGENCE_AREAS: list[str] = [
    "stack",
    "persistence",
    "providers",
    "deployment",
    "integrations",
    "phases",
]
_DIVERGENCE_KINDS: list[str] = ["renamed", "replaced", "dropped", "added", "reshaped"]


# Step 4 (D-SC4-1/3): one entry per prior phase. Everything but ``gap`` (and
# the provenance that goes with it) is code-owned — ``wrap_review`` joins
# ``implemented[].prior_feature_ids`` × ``status`` against
# ``scan.prior_round.phases[].features`` and overwrites whatever the model
# emitted. The model emits ``{phase_number, gap}`` only; the full item is
# permitted so an update-mode re-emission does not trip a retry, as
# ``load_bearing[].consumers``. ``title`` (D-SC4b-5, 2.9.0) is the prior
# phase's title, copied at commit so a renderer handed the item alone can
# name the phase; null when the prior round recorded none.
_RECONCILIATION_ITEM: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["phase_number"],
    "properties": {
        "phase_number": {"type": "integer"},
        "title": {"type": ["string", "null"]},
        "verdict": {"type": "string", "enum": _RECONCILIATION_VERDICTS},
        "implemented_ids": _str_list(),
        "paths": _str_list(),
        "features": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "statuses"],
                "properties": {"id": {"type": "string"}, "statuses": _str_list()},
            },
        },
        "gap": {"type": "string"},
        **_PROVENANCE_FIELDS,
    },
}


# Step 4 (D-SC4-4): changes since the last round that no phase planned,
# grouped by area. ``affects`` holds root-relative paths or ``implemented[]``
# ids; ``classification`` is code-owned and overwritten at commit.
_UNPLANNED_CHANGE_ITEM: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["area", "summary"],
    "properties": {
        "area": {"type": "string"},
        "summary": {"type": "string"},
        "affects": _str_list(),
        "classification": {"type": "string", "enum": _UNPLANNED_CLASSIFICATIONS},
        **_PROVENANCE_FIELDS,
    },
}


# Step 4 (D-SC4-7): where the built stack departs from the planned one.
# ``planned`` is verbatim from the prior round, ``found`` verbatim from this
# review. LLM-emitted whole.
_DIVERGENCE_ITEM: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["area", "planned", "found", "kind"],
    "properties": {
        "area": {"type": "string", "enum": _DIVERGENCE_AREAS},
        "planned": {"type": "string"},
        "found": {"type": "string"},
        "kind": {"type": "string", "enum": _DIVERGENCE_KINDS},
        "note": {"type": "string"},
        **_PROVENANCE_FIELDS,
    },
}


# The ``review`` field set — the v1 property vocabulary, unchanged in shape.
# It is the LLM's judgment about the codebase; every entry carries its own
# ``source``/``inferred_from`` provenance. Shared by the two schemas below.
# Step 3 (2.6.0) adds three optional arrays at the end; step 4 (2.8.0) three
# more after them.
_REVIEW_PROPERTIES: dict[str, Any] = {
    "is_software_project": {"type": "boolean"},
    # Empty-project branch
    "summary": {"type": "string"},
    # Full-project branch
    "project_type": {"type": "string"},
    "existing_self_description": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "source": {"type": "string"},
        },
        "required": ["text", "source"],
        "additionalProperties": False,
    },
    "architecture": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "pattern": {"type": "string"},
            **_PROVENANCE_FIELDS,
        },
        "additionalProperties": False,
    },
    "languages": {
        "type": "array",
        "items": _NAMED_WITH_PROVENANCE,
    },
    "frameworks": {
        "type": "array",
        "items": _NAMED_WITH_PROVENANCE,
    },
    "protocols_implemented": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "version": {"type": "string"},
                "location": {"type": "string"},
                **_PROVENANCE_FIELDS,
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    "runtime_versions": {
        "type": "object",
        "additionalProperties": {"type": "string"},
    },
    "build_system": {
        "type": "object",
        "properties": {
            "tool": {"type": "string"},
            "manifest": {"type": "string"},
            "build_backend": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "dependencies": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "purpose": {"type": "string"},
                **_PROVENANCE_FIELDS,
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    # Persistence layer — DB engine + ORM + migration tool. The
    # DB engine has no home in `dependencies` (an ORM SDK is a
    # library; the engine is infrastructure), so without this
    # field Phaser writes weaker DB setup/verification phases.
    "persistence": _PERSISTENCE_SCHEMA,
    # Required environment variables — NAMES only, never values.
    # Names belong in the artifact so Deployer/Phaser can write
    # accurate env-setup and verification steps; values are a
    # security boundary and stay in the developer's secret store.
    "env_vars": {
        "type": "array",
        "items": _ENV_VAR_ITEM,
    },
    # Deployment infra signals — Dockerfile, compose, k8s
    # manifests, PaaS configs, IaC. Already harvested in the
    # seed prompt but previously had no schema home; Deployer
    # had to reconstruct from directory_map heuristics.
    "deployment": _DEPLOYMENT_SCHEMA,
    # Exposed API surface — routes, gRPC methods, GraphQL ops.
    # `protocols_implemented` captures the protocol itself; this
    # captures the endpoint shape Phaser needs when proposing
    # API changes. Sampled, not exhaustive.
    "api_surface": {
        "type": "array",
        "items": _API_SURFACE_ITEM,
    },
    # Auth model — previously tangled across protocols_implemented
    # and security_observations. Closed enum + free-text provider
    # and library keeps the discriminator stable while letting the
    # long tail of IdPs and libraries live as string values.
    "auth": _AUTH_SCHEMA,
    # Existing AI/ML usage — first-class so Agentifier's reuse
    # bias does not depend on keyword-matching dependency names.
    "ai_capabilities": _AI_CAPABILITIES_SCHEMA,
    # CLOSED canonical key set — load-bearing for Phaser lookups.
    "commands": {
        "type": "object",
        "properties": {
            "build": {"type": "string"},
            "test": {"type": "string"},
            "lint": {"type": "string"},
            "typecheck": {"type": "string"},
            "run": {"type": "string"},
            "dev": {"type": "string"},
            "deploy": {"type": "string"},
        },
        "additionalProperties": False,
    },
    # CLOSED canonical key set — load-bearing for Phaser lookups.
    "entrypoints": {
        "type": "object",
        "properties": {
            "main": {"type": "string"},
            "wsgi_app": {"type": "string"},
            "cli_script": {"type": "string"},
            "dev_server": {"type": "string"},
            "ui_root": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "directory_map": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "role": {"type": "string"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    "ui_summary": {
        "type": "object",
        "required": ["has_ui"],
        "additionalProperties": False,
        "properties": {
            "has_ui": {"type": "boolean"},
            # CLOSED enum — load-bearing for Designer routing.
            "kind": {
                "type": "string",
                "enum": [
                    "spa",
                    "mpa",
                    "mobile",
                    "desktop",
                    "tui",
                    "none",
                ],
            },
            "framework": {"type": "string"},
            "styling": {"type": "string"},
            "routing": {"type": "string"},
            "entry_files": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    },
    "coding_style": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "linter": _STYLE_FIELD,
            "formatter": _STYLE_FIELD,
            "type_checker": _STYLE_FIELD,
            "indentation": _STYLE_FIELD,
            "quotes": _STYLE_FIELD,
            "line_length": _STYLE_FIELD,
            "naming_conventions": {
                "type": "object",
                "additionalProperties": _STYLE_FIELD,
            },
            "other_rules": {
                "type": "array",
                "items": {"type": "string"},
            },
            "patterns": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    },
    "notes": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "test_coverage": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "has_tests": {"type": "boolean"},
                    "framework": {"type": "string"},
                    "covered_modules": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "uncovered_modules": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "coverage_summary": {"type": "string"},
                    **_PROVENANCE_FIELDS,
                },
            },
            "ci_cd": {
                "type": "object",
                "additionalProperties": False,
                "required": ["present"],
                "properties": {
                    "present": {"type": "boolean"},
                    "type": {"type": ["string", "null"]},
                    "path": {"type": ["string", "null"]},
                },
            },
            "incomplete_or_dead_code": {
                "type": "array",
                "items": {"type": "string"},
            },
            "change_risks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "area": {"type": "string"},
                        "risk": {"type": "string"},
                        "mitigation_hint": {"type": "string"},
                    },
                },
            },
            "security_observations": {
                "type": "array",
                "items": {"type": "string"},
            },
            "other_notes": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    },
    # Step 3 (D-SC3-1): architecture, contracts and integrations. Optional —
    # a review without them still validates; present, each item is closed.
    "load_bearing": {"type": "array", "items": _LOAD_BEARING_ITEM},
    "implemented": {"type": "array", "items": _IMPLEMENTED_ITEM},
    "integrations": {"type": "array", "items": _INTEGRATION_ITEM},
    # Step 4 (D-SC4-1): the prior round reconciled against ``implemented``,
    # what changed outside any plan, and where the built stack departs from
    # the planned one. Optional; present, each item is closed.
    "prior_round_reconciliation": {"type": "array", "items": _RECONCILIATION_ITEM},
    "unplanned_changes": {"type": "array", "items": _UNPLANNED_CHANGE_ITEM},
    "divergences": {"type": "array", "items": _DIVERGENCE_ITEM},
}


_REVIEW_OBJECT: dict[str, Any] = {
    "type": "object",
    "required": ["is_software_project"],
    "additionalProperties": False,
    "properties": _REVIEW_PROPERTIES,
}


# What the CodeScanner LLM emits: the ``review`` block alone. ``schema_version``
# and ``scan`` are code-owned metadata the model never sees or writes — they
# are attached at ``_scanner_commit`` (D-EV2/D-EV4).
REVIEW_BLOCK_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Spec4 CodeScanner review block",
    "type": "object",
    "required": ["review"],
    "additionalProperties": False,
    "properties": {"review": _REVIEW_OBJECT},
}


def _int_map() -> dict[str, Any]:
    return {"type": "object", "additionalProperties": {"type": "integer", "minimum": 0}}


def _closed(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": required,
        "additionalProperties": False,
        "properties": properties,
    }


_NON_NEGATIVE = {"type": "integer", "minimum": 0}
_NULLABLE_STRING = {"type": ["string", "null"]}

# The computed ``scan`` layer (D-SC1b-9): each block is optional, so a later
# step adds its own without touching this version, but a block that is present
# is closed — a collector emitting a key this schema does not name is a code
# fault, caught at commit like a bad envelope (D-EV3). ``git`` is absent for a
# project that is not a repository root, and ``{"available": false}`` for one
# where ``git`` could not be run.
_SCAN_INVENTORY = _closed(
    [
        "files_total",
        "files_listed",
        "truncated",
        "loc_total",
        "by_extension",
        "listed",
        "unscanned_dirs",
    ],
    {
        "files_total": _NON_NEGATIVE,
        "files_listed": _NON_NEGATIVE,
        "truncated": {"type": "boolean"},
        "loc_total": _NON_NEGATIVE,
        "by_extension": {
            "type": "object",
            "additionalProperties": _closed(
                ["files", "loc", "unmeasured"],
                {
                    "files": _NON_NEGATIVE,
                    "loc": _NON_NEGATIVE,
                    "unmeasured": _NON_NEGATIVE,
                },
            ),
        },
        "listed": _str_list(),
        "unscanned_dirs": _str_list(),
    },
)

_SCAN_COVERAGE = _closed(
    [
        "tree_listed",
        "tree_truncated",
        "readme",
        "manifests",
        "ci",
        "deploy",
        "sampled",
        "source_files_total",
        "source_files_sampled",
    ],
    {
        "tree_listed": _NON_NEGATIVE,
        "tree_truncated": {"type": "boolean"},
        "readme": _NULLABLE_STRING,
        "manifests": _str_list(),
        "ci": _str_list(),
        "deploy": _str_list(),
        "sampled": _str_list(),
        "source_files_total": _NON_NEGATIVE,
        "source_files_sampled": _NON_NEGATIVE,
        # 2.4.0 (D-SC2-13): optional, so a 2.1–2.3 scan on disk still reads.
        "signatures_shown": _str_list(),
        "conventions": _str_list(),
        "tree": _closed(
            ["form", "nodes_listed", "truncated"],
            {
                "form": {"enum": ["rollup+nodes", "empty"]},
                "nodes_listed": _NON_NEGATIVE,
                "truncated": {"type": "boolean"},
            },
        ),
        "evidence_tokens": _NON_NEGATIVE,
        # 2.6.0 (D-SC3-6/8): whether the seed carried the external-import
        # index and the prior round's feature ids. Optional for older scans.
        "external_imports_shown": {"type": "boolean"},
        "prior_round_shown": {"type": "boolean"},
        # 2.8.0 (D-SC4-6): whether the seed carried the Changes Since the Last
        # Round block. Optional for older scans.
        "changes_shown": {"type": "boolean"},
    },
)

_SCAN_GIT_SINCE = _closed(
    [
        "boundary_kind",
        "boundary",
        "commits",
        "truncated",
        "first",
        "last",
        "authors",
        "touched_top_dirs",
        "agent_trailers_present",
    ],
    {
        "boundary_kind": {"enum": ["implemented", "prior_review"]},
        "boundary": {"type": "string"},
        "commits": _NON_NEGATIVE,
        "truncated": {"type": "boolean"},
        "first": _NULLABLE_STRING,
        "last": _NULLABLE_STRING,
        "authors": _str_list(),
        "touched_top_dirs": _int_map(),
        "agent_trailers_present": {"type": "boolean"},
        # 2.5.0 (D-SC2-6): the files with the most commits since the boundary,
        # most first. Optional, so a 2.1–2.4 block on disk still validates.
        "most_touched": {
            "type": "array",
            "items": _closed(
                ["path", "commits"],
                {"path": {"type": "string"}, "commits": _NON_NEGATIVE},
            ),
        },
    },
)

_SCAN_GIT_ACTIVITY = _closed(
    ["commits_scanned", "truncated", "last_commit_per_top_dir"],
    {
        "commits_scanned": _NON_NEGATIVE,
        "truncated": {"type": "boolean"},
        "last_commit_per_top_dir": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
    },
)

# 1d (D-SC1d-8): the working tree's modified and untracked files per top-level
# directory, in the shape of ``since_last_round.touched_top_dirs``. Optional,
# so a 2.1/2.2 block still validates.
_SCAN_GIT_WORKING_TREE = _closed(
    ["modified_top_dirs", "untracked_top_dirs"],
    {"modified_top_dirs": _int_map(), "untracked_top_dirs": _int_map()},
)

_SCAN_GIT = {
    "oneOf": [
        _closed(["available"], {"available": {"const": False}}),
        _closed(
            ["available", "head", "branch", "dirty", "untracked_count", "activity"],
            {
                "available": {"const": True},
                "head": {"type": "string"},
                "branch": {"type": "string"},
                "dirty": {"type": "boolean"},
                "untracked_count": _NON_NEGATIVE,
                "working_tree": _SCAN_GIT_WORKING_TREE,
                "activity": _SCAN_GIT_ACTIVITY,
                "since_last_round": _SCAN_GIT_SINCE,
            },
        ),
    ]
}

# 1c: the import graph and the signatures of what it ranks. ``fan_in`` and
# ``fan_out`` carry only non-zero counts; the edge list is not stored
# (D-SC1c-2). ``signatures.files`` is keyed by root-relative path.
_SCAN_MODULE_GRAPH = _closed(
    [
        "languages",
        "nodes",
        "edges",
        "fan_in",
        "fan_out",
        "load_bearing_candidates",
        "unresolved",
        "unresolved_truncated",
    ],
    {
        "languages": _str_list(),
        "nodes": _NON_NEGATIVE,
        "edges": _NON_NEGATIVE,
        "fan_in": _int_map(),
        "fan_out": _int_map(),
        "load_bearing_candidates": {
            "type": "array",
            "items": _closed(
                ["path", "fan_in", "consumers"],
                {
                    "path": {"type": "string"},
                    "fan_in": _NON_NEGATIVE,
                    "consumers": _str_list(),
                },
            ),
        },
        "unresolved": _int_map(),
        "unresolved_truncated": {"type": "boolean"},
        # 2.4.0 (D-SC2-4): what the sampler ranked by; optional for older scans.
        "reach": _closed(
            ["basis", "entrypoints", "reached", "unreached_dirs"],
            {
                "basis": {"enum": ["entrypoints", "manifest", "none"]},
                "entrypoints": _str_list(),
                "reached": _NON_NEGATIVE,
                "unreached_dirs": _str_list(),
            },
        ),
        # 2.6.0 (D-SC3-6): the modules importing each external package —
        # ``unresolved`` counts them, this names them. Optional for older scans.
        "external_imports": {"type": "object", "additionalProperties": _str_list()},
    },
)

_SCAN_SIGNATURE_FILE = _closed(
    ["language", "doc", "symbols", "truncated"],
    {
        "language": {"type": "string"},
        "doc": _NULLABLE_STRING,
        "symbols": {
            "type": "array",
            "items": _closed(
                ["kind", "name", "signature", "doc"],
                {
                    "kind": {"type": "string"},
                    "name": {"type": "string"},
                    "signature": {"type": "string"},
                    "doc": _NULLABLE_STRING,
                },
            ),
        },
        "truncated": {"type": "boolean"},
    },
)

_SCAN_SIGNATURES = _closed(
    ["files", "truncated"],
    {
        "files": {"type": "object", "additionalProperties": _SCAN_SIGNATURE_FILE},
        "truncated": {"type": "boolean"},
    },
)

# 1d: declared dependencies per manifest, the prior round's extract, the
# plan-versus-manifests classification and the scan-to-scan delta.
_NULLABLE_INT = {"type": ["integer", "null"]}
_STR_MAP = {"type": "object", "additionalProperties": {"type": "string"}}


def _named_list(second: str) -> dict[str, Any]:
    """A list of ``{name, <second>}`` pairs, the second nullable."""
    return {
        "type": "array",
        "items": _closed(
            ["name", second], {"name": {"type": "string"}, second: _NULLABLE_STRING}
        ),
    }


_SCAN_DEPENDENCIES = _closed(
    ["files", "truncated"],
    {
        "files": {"type": "object", "additionalProperties": _STR_MAP},
        "truncated": {"type": "boolean"},
    },
)

_PRIOR_DECLARATION = _closed(
    ["id", "role"], {"id": {"type": "string"}, "role": _NULLABLE_STRING}
)

_PRIOR_PHASE = _closed(
    [
        "number",
        "title",
        "summary",
        "verification",
        "features",
        "capabilities",
        "dependencies",
    ],
    {
        "number": _NULLABLE_INT,
        "title": _NULLABLE_STRING,
        "summary": _NULLABLE_STRING,
        "verification": _NULLABLE_STRING,
        "features": {"type": "array", "items": _PRIOR_DECLARATION},
        "capabilities": {"type": "array", "items": _PRIOR_DECLARATION},
        "dependencies": _str_list(),
    },
)

_PRIOR_STACK = _closed(
    [
        "languages",
        "libraries",
        "deployment_targets",
        "persistence_primary",
        "provider_names",
        "infrastructure_keys",
        "integrations",
    ],
    {
        "languages": _named_list("version"),
        "libraries": _named_list("category"),
        "deployment_targets": _named_list("kind"),
        "persistence_primary": _NULLABLE_STRING,
        "provider_names": _str_list(),
        "infrastructure_keys": _str_list(),
        "integrations": _named_list("kind"),
    },
)

_PRIOR_VISION = _closed(
    ["name", "feature_ids", "revision_count"],
    {
        "name": _NULLABLE_STRING,
        "feature_ids": _str_list(),
        "revision_count": _NON_NEGATIVE,
    },
)

_PRIOR_FEATURE_SPECS = _closed(
    ["version", "feature_ids"],
    {"version": _NULLABLE_INT, "feature_ids": _str_list()},
)

_PRIOR_CAPABILITY = _closed(
    [
        "id",
        "kind",
        "tier",
        "introduced_in_version",
        "linked_vision_features",
        "requires",
    ],
    {
        "id": {"type": "string"},
        "kind": _NULLABLE_STRING,
        "tier": _NULLABLE_STRING,
        "introduced_in_version": _NULLABLE_INT,
        "linked_vision_features": _str_list(),
        "requires": _str_list(),
    },
)

_PRIOR_REVIEW = _closed(
    [
        "path",
        "schema_version",
        "bytes",
        "project_type",
        "commands",
        "deployment",
        "dependency_names",
    ],
    {
        "path": {"type": "string"},
        "schema_version": _NULLABLE_INT,
        "bytes": _NON_NEGATIVE,
        "project_type": _NULLABLE_STRING,
        "commands": _STR_MAP,
        "deployment": {
            "type": "array",
            "items": _closed(
                ["kind", "name"], {"kind": {"type": "string"}, "name": _NULLABLE_STRING}
            ),
        },
        "dependency_names": _str_list(),
    },
)

_SCAN_PRIOR_ROUND = _closed(
    [
        "version",
        "implemented",
        "artifacts_present",
        "phases",
        "stack",
        "vision",
        "feature_specs",
        "capabilities",
        "capabilities_from_version",
        "review",
    ],
    {
        "version": _NON_NEGATIVE,
        "implemented": _NULLABLE_STRING,
        "artifacts_present": _str_list(),
        "phases": {"type": "array", "items": _PRIOR_PHASE},
        "stack": {"anyOf": [_PRIOR_STACK, {"type": "null"}]},
        "vision": {"anyOf": [_PRIOR_VISION, {"type": "null"}]},
        "feature_specs": {"anyOf": [_PRIOR_FEATURE_SPECS, {"type": "null"}]},
        "capabilities": {"type": "array", "items": _PRIOR_CAPABILITY},
        "capabilities_from_version": _NULLABLE_INT,
        "review": {"anyOf": [_PRIOR_REVIEW, {"type": "null"}]},
    },
)

_DRIFT_PLANNED = {"name": {"type": "string"}, "sources": _str_list()}

_SCAN_PLAN_DRIFT = _closed(
    [
        "prior_version",
        "planned",
        "declared",
        "planned_in_manifests",
        "planned_only_imported",
        "planned_unmatched",
        "declared_not_planned",
        "truncated",
    ],
    {
        "prior_version": _NULLABLE_INT,
        "planned": _NON_NEGATIVE,
        "declared": _NON_NEGATIVE,
        "planned_in_manifests": {
            "type": "array",
            "items": _closed(
                ["name", "sources", "declared_as", "manifest"],
                {
                    **_DRIFT_PLANNED,
                    "declared_as": {"type": "string"},
                    "manifest": {"type": "string"},
                },
            ),
        },
        "planned_only_imported": {
            "type": "array",
            "items": _closed(
                ["name", "sources", "imported_as", "imports"],
                {
                    **_DRIFT_PLANNED,
                    "imported_as": {"type": "string"},
                    "imports": _NON_NEGATIVE,
                },
            ),
        },
        "planned_unmatched": {
            "type": "array",
            "items": _closed(["name", "sources"], dict(_DRIFT_PLANNED)),
        },
        "declared_not_planned": {
            "type": "array",
            "items": _closed(
                ["name", "manifest"],
                {"name": {"type": "string"}, "manifest": {"type": "string"}},
            ),
        },
        "truncated": {"type": "boolean"},
    },
)


def _delta_lists(*keys: str) -> dict[str, Any]:
    """A per-path delta entry: the named string lists plus ``truncated``."""
    return _closed(
        [*keys, "truncated"],
        {**{k: _str_list() for k in keys}, "truncated": {"type": "boolean"}},
    )


# 2.9.2 (D-SC5-2): which Spec4 measured a scan, under which schema. On every
# scan as its last key; ``delta.prior`` copies the prior scan's, ``null`` for
# a prior from before the key existed. Optional in both places so every
# stored 2.x review still validates.
_SCAN_PRODUCER = _closed(
    ["spec4", "schema"], {"spec4": {"type": "string"}, "schema": _NON_NEGATIVE}
)

_SCAN_DELTA = _closed(
    ["prior", "files", "dependencies", "candidates", "signatures"],
    {
        "prior": _closed(
            ["kind", "version", "head"],
            {
                "kind": {"enum": ["implemented", "prior_review"]},
                "version": _NON_NEGATIVE,
                "head": _NULLABLE_STRING,
                "producer": {**_SCAN_PRODUCER, "type": ["object", "null"]},
            },
        ),
        # ``modified`` (2.10.0, D-SC5-9) is optional: a 2.3.0…2.9.2 delta
        # has only the two listing-derived lists and still validates.
        "files": _closed(
            ["added", "removed", "partial", "truncated"],
            {
                "added": _str_list(),
                "removed": _str_list(),
                "modified": _str_list(),
                "partial": {"type": "boolean"},
                "truncated": {"type": "boolean"},
            },
        ),
        "dependencies": {
            "type": "object",
            "additionalProperties": _delta_lists("added", "removed", "bumped"),
        },
        "candidates": _closed(
            ["entered", "left"], {"entered": _str_list(), "left": _str_list()}
        ),
        "signatures": {
            "type": "object",
            "additionalProperties": _delta_lists("added", "removed", "changed"),
        },
    },
)

SCAN_SCHEMA: dict[str, Any] = _closed(
    [],
    {
        "inventory": _SCAN_INVENTORY,
        "coverage": _SCAN_COVERAGE,
        "git": _SCAN_GIT,
        "module_graph": _SCAN_MODULE_GRAPH,
        "signatures": _SCAN_SIGNATURES,
        "dependencies": _SCAN_DEPENDENCIES,
        "prior_round": _SCAN_PRIOR_ROUND,
        "plan_drift": _SCAN_PLAN_DRIFT,
        "delta": _SCAN_DELTA,
        "producer": _SCAN_PRODUCER,
    },
)


# What is stored in ``session["code_review"]`` and written to
# ``.spec4/v{N}/code_review.json``: the envelope. ``scan`` is the computed,
# deterministic layer (``SCAN_SCHEMA``; the 1b, 1c and 1d blocks);
# ``review`` is the LLM's block. Consumers unwrap by path through
# ``_code_review_context.unwrap_review`` / ``unwrap_scan`` — never by falling
# back to the outer dict (D-EV5).
CODE_REVIEW_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Spec4 code_review (schema_version 2)",
    "type": "object",
    "required": ["code_review"],
    "additionalProperties": False,
    "properties": {
        "code_review": {
            "type": "object",
            "required": ["schema_version", "scan", "review"],
            "additionalProperties": False,
            "properties": {
                "schema_version": {"const": CODE_REVIEW_SCHEMA_VERSION},
                "scan": SCAN_SCHEMA,
                "review": _REVIEW_OBJECT,
            },
        }
    },
}


def _errors(schema: dict[str, Any], data: dict[str, Any]) -> list[str]:
    validator = jsonschema.Draft7Validator(schema)
    errors: list[str] = []
    for err in validator.iter_errors(data):
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{path}: {err.message}")
    return errors


def validate_review_block(data: dict[str, Any]) -> list[str]:
    """Validate the LLM's ``{"review": {...}}`` block against REVIEW_BLOCK_SCHEMA.

    Returns a list of human-readable error messages (each formatted as
    "<path>: <message>"). Returns an empty list when the data validates.

    The errors list is what the CodeScanner agent surfaces back to the LLM
    on its retry turn, so phrasing must be specific enough to act on.
    """
    return _errors(REVIEW_BLOCK_SCHEMA, data)


def validate_code_review(data: dict[str, Any]) -> list[str]:
    """Validate a stored ``code_review`` envelope against CODE_REVIEW_SCHEMA.

    Same error format as ``validate_review_block``. Run at commit on the
    envelope the scanner assembled, so a wrapping bug fails loudly rather
    than writing a shape no consumer can read.
    """
    return _errors(CODE_REVIEW_SCHEMA, data)


def format_validation_errors_for_retry(errors: list[str], limit: int = 15) -> str:
    """Build the corrective user message that the agent feeds back to the LLM.

    Caps the error list to avoid bloating context if a single bad emission
    triggers many cascading errors.
    """
    capped = errors[:limit]
    bullet_list = "\n".join(f"- {e}" for e in capped)
    truncated_note = (
        f"\n\n(plus {len(errors) - limit} more — fix the structural issues above first)"
        if len(errors) > limit
        else ""
    )
    return (
        "The JSON you just emitted failed schema validation. Re-emit a "
        "corrected JSON block — only the fenced ```json``` block, no "
        "preface — that fixes these specific issues:\n\n"
        f"{bullet_list}{truncated_note}\n\n"
        "Reminders that match the most common drift:\n"
        "- `commands` and `entrypoints` use CLOSED canonical key sets. "
        "Custom keys go in `notes.other_notes` as one-line strings.\n"
        "- `ui_summary.kind` must be one of: spa, mpa, mobile, desktop, "
        "tui, none.\n"
        "- `ai_capabilities[].kind` must be one of: llm_api, embedding, "
        "vector_store, ml_model, rag, agent_framework, other.\n"
        "- `implemented[].status` must be one of: complete, partial, stub, "
        "scaffolded_only; every entry needs at least one path.\n"
        "- `integrations[].kind` must be one of: llm_provider, web_search, "
        "database, cache, queue, object_storage, identity_provider, "
        "email_service, payment, mcp_server, third_party_api, other.\n"
        "- `load_bearing[].contract` holds only `inputs`, `outputs`, "
        "`invariants`, `side_effects` (string lists); omit `consumers`.\n"
        "- `prior_round_reconciliation[]` items carry `phase_number` (integer) "
        "and `gap` only; omit `verdict`, `implemented_ids`, `paths`, "
        "`features`.\n"
        "- `unplanned_changes[]` items carry `area`, `summary`, `affects`; "
        "omit `classification`.\n"
        "- `divergences[].area` must be one of: stack, persistence, providers, "
        "deployment, integrations, phases; `divergences[].kind` must be one "
        "of: renamed, replaced, dropped, added, reshaped. Never a dependency "
        "name.\n"
        "- Do not add custom sub-keys anywhere in the schema; route "
        "extras to `notes.other_notes`.\n"
        "- Each canonical key takes a single invocation, never a "
        "disjunction or list."
    )
