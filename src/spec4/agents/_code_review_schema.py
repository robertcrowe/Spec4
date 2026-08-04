"""JSON Schema for the CodeScanner `code_review` artifact (schema_version 1).

The schema captures the *structural* contract that downstream agents depend on:
closed canonical key vocabularies for `commands` and `entrypoints`, the
`ui_summary.kind` enum, the closed `notes.*` shape, and entry-array item
shapes. It does NOT enforce conditional required fields (`project_type`,
`languages`, etc. when `is_software_project` is true) — those are guidance
in the prompt, and a soft miss should not trigger a costly retry.

The schema is consumed in two places:

1. `validate_code_review(data)` — called after every JSON extraction in
   `code_scanner.run()`. If validation fails, the agent re-streams once
   with `response_format={"type": "json_object"}` and a corrective user
   message listing the specific errors, on providers that support it.

2. Tests assert structural rules survive prompt edits.
"""

from __future__ import annotations

from typing import Any

import jsonschema


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


CODE_REVIEW_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Spec4 code_review (schema_version 1)",
    "type": "object",
    "required": ["code_review"],
    "additionalProperties": False,
    "properties": {
        "code_review": {
            "type": "object",
            "required": ["schema_version", "is_software_project"],
            "additionalProperties": False,
            "properties": {
                "schema_version": {"const": 1},
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
            },
        }
    },
}


def validate_code_review(data: Any) -> list[str]:
    """Validate an extracted code review against CODE_REVIEW_SCHEMA.

    Returns a list of human-readable error messages (each formatted as
    "<path>: <message>"). Returns an empty list when the data validates.

    The errors list is what the CodeScanner agent surfaces back to the LLM
    on its retry turn, so phrasing must be specific enough to act on.
    """
    validator = jsonschema.Draft7Validator(CODE_REVIEW_SCHEMA)
    errors: list[str] = []
    for err in validator.iter_errors(data):
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{path}: {err.message}")
    return errors


def format_validation_errors_for_retry(errors: list[str], limit: int = 15) -> str:
    """Build the corrective user message that the agent feeds back to the LLM.

    Caps the error list to avoid bloating context if a single bad emission
    triggers many cascading errors.
    """
    capped = errors[:limit]
    bullet_list = "\n".join(f"- {e}" for e in capped)
    truncated_note = (
        f"\n\n(plus {len(errors) - limit} more — fix the structural issues "
        "above first)"
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
        "- Do not add custom sub-keys anywhere in the schema; route "
        "extras to `notes.other_notes`.\n"
        "- Each canonical key takes a single invocation, never a "
        "disjunction or list."
    )
