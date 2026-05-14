from __future__ import annotations

import json
import pathlib
from collections.abc import Generator
from typing import Any

from spec4 import tavily_mcp
from spec4.agents._code_review_schema import (
    format_validation_errors_for_retry,
    validate_code_review,
)
from spec4.agents._utils import (
    _drop_orphan_trailing_user,
    _extract_json_block,
    _last_assistant_text,
    _maybe_inject_resume_summary,
    _render_coding_style,
    _replay_last_assistant,
    _stream_suppressing_json,
)
from spec4.app_constants import STATE_REVIEW_COMPLETE


CODE_REVIEW_SCHEMA_VERSION = 1


_SKIP_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "venv",
    ".env",
    "env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    ".cargo",
    ".spec4",
}

_MANIFEST_FILES = {
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "requirements-dev.txt",
    "Pipfile",
    "package.json",
    "package-lock.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Makefile",
    "tsconfig.json",
    "babel.config.js",
    ".eslintrc",
    ".eslintrc.json",
    ".eslintrc.js",
    ".eslintrc.yaml",
    ".prettierrc",
    ".prettierrc.json",
    "ruff.toml",
    ".ruff.toml",
    "mypy.ini",
    ".mypy.ini",
    "tox.ini",
    ".flake8",
    "pylintrc",
    ".pylintrc",
}

_DEPLOY_SIGNAL_FILES = {
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Procfile",
    "fly.toml",
    "render.yaml",
    "vercel.json",
    "netlify.toml",
    "app.yaml",
}

_README_NAMES = {"README.md", "README.rst", "README.txt", "README"}
_CI_DIR_PARTS = (
    (".github", "workflows"),
)
_CI_FILE_BASENAMES = {
    ".gitlab-ci.yml",
    ".circleci",
    "azure-pipelines.yml",
    "bitbucket-pipelines.yml",
    "Jenkinsfile",
}
_TERRAFORM_DIRS = {"terraform", "infra", "infrastructure"}

_MAX_TREE_FILES = 150
_MAX_MANIFEST_CHARS = 10_000
_MAX_MANIFEST_FILE_CHARS = 3_000
_MAX_README_LINES = 80
_MAX_PRIORITY_SOURCE_FILES = 8
_MAX_SOURCE_SAMPLE_CHARS = 8_000
_MAX_SOURCE_SAMPLE_LINES = 80

_SOURCE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".swift",
    ".cs",
    ".cpp",
    ".c",
    ".h",
    ".rb",
    ".php",
    ".scala",
    ".r",
    ".R",
    ".lua",
    ".ex",
    ".exs",
}

_ENTRYPOINT_NAME_STEMS = {"main", "app", "index", "server", "cli", "__main__"}


def _is_entrypoint_candidate(path: pathlib.Path) -> bool:
    stem = path.stem.lower()
    return stem in _ENTRYPOINT_NAME_STEMS


def _read_text_safely(path: pathlib.Path, limit: int) -> str | None:
    try:
        return path.read_text(errors="replace")[:limit]
    except OSError:
        return None


def _gather_project_context(working_dir: str) -> str:
    root = pathlib.Path(working_dir)
    lines: list[str] = [f"## Project Directory: `{root}`\n"]

    all_files: list[pathlib.Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        all_files.append(path)

    if not all_files:
        lines.append("The directory appears to be empty (no non-hidden files found).\n")
        return "\n".join(lines)

    lines.append("### File Tree\n```")
    for f in all_files[:_MAX_TREE_FILES]:
        lines.append(str(f.relative_to(root)))
    if len(all_files) > _MAX_TREE_FILES:
        lines.append(
            f"... and {len(all_files) - _MAX_TREE_FILES} more files (truncated)"
        )
    lines.append("```\n")

    readme_lines = _format_readme_block(root, all_files)
    if readme_lines:
        lines.extend(readme_lines)

    lines.append("### Config and Manifest Files\n")
    manifest_chars = 0
    for f in all_files:
        if f.name in _MANIFEST_FILES and manifest_chars < _MAX_MANIFEST_CHARS:
            content = _read_text_safely(f, _MAX_MANIFEST_FILE_CHARS)
            if content is None:
                continue
            lines.append(f"#### `{f.relative_to(root)}`\n```\n{content}\n```\n")
            manifest_chars += len(content)

    ci_block = _format_ci_block(root, all_files)
    if ci_block:
        lines.extend(ci_block)

    deploy_block = _format_deployment_signals(root, all_files)
    if deploy_block:
        lines.extend(deploy_block)

    lines.append("### Source File Samples\n")
    source_files = [f for f in all_files if f.suffix in _SOURCE_EXTENSIONS]

    def _is_test(p: pathlib.Path) -> bool:
        parts = [x.lower() for x in p.relative_to(root).parts]
        return any(x in ("test", "tests", "spec", "specs") for x in parts)

    non_test_sources = [f for f in source_files if not _is_test(f)]
    entrypoint_files = [f for f in non_test_sources if _is_entrypoint_candidate(f)]
    other_files = [f for f in non_test_sources if not _is_entrypoint_candidate(f)]
    priority_files = (entrypoint_files + other_files)[:_MAX_PRIORITY_SOURCE_FILES]

    source_chars = 0
    for f in priority_files:
        if source_chars >= _MAX_SOURCE_SAMPLE_CHARS:
            break
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue
        sample_lines = content.splitlines()[:_MAX_SOURCE_SAMPLE_LINES]
        sample = "\n".join(sample_lines)
        label = " (entrypoint candidate)" if _is_entrypoint_candidate(f) else ""
        lines.append(
            f"#### `{f.relative_to(root)}` (first {len(sample_lines)} lines){label}\n"
            f"```\n{sample}\n```\n"
        )
        source_chars += len(sample)

    return "\n".join(lines)


def _format_readme_block(
    root: pathlib.Path, all_files: list[pathlib.Path]
) -> list[str]:
    readme = next(
        (f for f in all_files if f.name in _README_NAMES and f.parent == root),
        None,
    )
    if readme is None:
        return []
    try:
        text = readme.read_text(errors="replace")
    except OSError:
        return []
    sample_lines = text.splitlines()[:_MAX_README_LINES]
    sample = "\n".join(sample_lines)
    return [
        "### README Excerpt\n"
        f"_Source: `{readme.relative_to(root)}` (first {len(sample_lines)} lines)_\n"
        f"```\n{sample}\n```\n"
    ]


def _format_ci_block(
    root: pathlib.Path, all_files: list[pathlib.Path]
) -> list[str]:
    ci_files: list[pathlib.Path] = []
    for f in all_files:
        rel_parts = f.relative_to(root).parts
        if any(rel_parts[: len(dp)] == dp for dp in _CI_DIR_PARTS):
            ci_files.append(f)
            continue
        if f.name in _CI_FILE_BASENAMES:
            ci_files.append(f)
    if not ci_files:
        return []
    out: list[str] = ["### CI / Workflow Files\n"]
    for f in ci_files[:5]:
        content = _read_text_safely(f, 1500)
        if content is None:
            continue
        out.append(f"#### `{f.relative_to(root)}`\n```\n{content}\n```\n")
    return out


def _format_deployment_signals(
    root: pathlib.Path, all_files: list[pathlib.Path]
) -> list[str]:
    deploy_files: list[pathlib.Path] = []
    has_terraform = False
    for f in all_files:
        rel_parts = f.relative_to(root).parts
        if f.name in _DEPLOY_SIGNAL_FILES:
            deploy_files.append(f)
        if any(p in _TERRAFORM_DIRS for p in rel_parts) and f.suffix in {".tf", ".tfvars"}:
            has_terraform = True
    if not deploy_files and not has_terraform:
        return []
    out: list[str] = ["### Deployment Signals\n"]
    for f in deploy_files[:5]:
        content = _read_text_safely(f, 1500)
        if content is None:
            out.append(f"- `{f.relative_to(root)}` present\n")
            continue
        out.append(f"#### `{f.relative_to(root)}`\n```\n{content}\n```\n")
    if has_terraform:
        out.append("- Terraform configuration detected under infrastructure directory\n")
    return out


SYSTEM_PROMPT = """\
You are an expert software architect and code reviewer. You have been given the file\
listing and selected contents of a software project directory. Your job is to produce a\
structured code review for Spec4, a project-planning tool. The review is consumed\
verbatim by four downstream agents — quality here directly determines theirs.

**Downstream consumers — what each one will use:**

- **Brainstormer** (vision agent) — reads `existing_self_description`, `project_type`,
  and `ui_summary.has_ui` to ground the vision conversation in what already exists.
- **StackAdvisor** — reads `languages`, `frameworks`, `runtime_versions`,
  `dependencies`, `protocols_implemented`, `persistence`, `auth`, and
  `commands.deploy` to flag stack conflicts and migration costs.
- **Phaser** — reads `commands` (test/lint/run/build) to write executable
  verification criteria on every phase; reads `entrypoints` and `directory_map` to
  design Phase 1 as a brownfield integration thread (not a from-scratch scaffold);
  reads `notes.incomplete_or_dead_code` and `notes.change_risks` to avoid extending
  broken code; reads `coding_style` to match conventions; reads
  `protocols_implemented` to cite canonical protocol docs in phase `references`;
  reads `persistence` to plan DB-connection and migration steps; reads `env_vars`
  to verify env plumbing in Phase 1 and reference required variables in later
  phases; reads `api_surface` to anchor proposed API changes on existing routes.
- **Designer** — reads `ui_summary.has_ui` to decide whether to skip UI mock
  generation entirely; reads `ui_summary.framework` and `ui_summary.styling` to
  preserve look-and-feel when modifying existing UI.
- **Deployer** — reads `deployment` to know whether containerization /
  orchestration / PaaS / IaC already exist (so it asks whether to keep or
  replace, instead of re-deciding from scratch); reads `env_vars` to
  pre-populate the required-variables list during deployment planning; reads
  `persistence` to size the database resource in the deployment plan; reads
  `auth.model` so the plan reflects existing auth choices rather than
  proposing conflicting ones.

If you write generic prose into fields where structured specifics are required,
downstream agents will produce worse output. Be specific.

**Scope:** Describe only what already exists in the directory. Never ask the user
about technology choices, language preferences, frameworks, hosting, deployment, or
libraries — those are handled by StackAdvisor. If the user volunteers such
information, acknowledge it and note it will be revisited with StackAdvisor.

**Web search:** If you encounter an unfamiliar framework, build tool, or technology
in the project files, use web search to identify it before presenting findings.

**Evidence and inference discipline:**

- Anything sourced from a manifest file (e.g. `package.json`, `pyproject.toml`,
  `Cargo.toml`, `go.mod`) is a fact. Mark these with `source: "<filename>"`.
- Anything inferred from reading source samples (naming conventions, indentation,
  architecture classification, "patterns" you noticed) is an inference. Mark these
  with `inferred_from: "<file path>"` citing the file you inferred it from.
- **Do not invent dependencies.** Only list packages that appear in a manifest you
  were shown, or that are imported by a source file you were shown. If unsure, omit.
- If a field is genuinely unknown after looking at the evidence, omit it. Do not
  fill it with "none detected" / "n/a" / "unknown" prose — leave the key absent.

**Schema discipline (load-bearing — downstream agents read these fields by name):**

- The schema is closed: do NOT add custom sub-keys to any schema field. If you
  observe something that does not fit a defined field, place it in
  `notes.other_notes` as a string.
- `commands` and `entrypoints` use a fixed, canonical key vocabulary (listed in
  the schema below). Phaser, StackAdvisor, and Deployer look these keys up by
  name to write executable verification commands and plan Phase 1. Inventing
  custom keys breaks that lookup.
  - For `commands`: use ONLY `build`, `test`, `lint`, `typecheck`, `run`, `dev`,
    `deploy`. If a project's invocation does not map to one of these (e.g.
    `arrg cli --topic ...`, `make migrate`, `npm run storybook`), OMIT it from
    `commands` and add a one-line entry to `notes.other_notes` such as
    "CLI invocation: `arrg cli --topic <topic>`". Do NOT add `run_dashboard`,
    `run_cli`, `version`, `migrate`, or any other custom key.
  - For `entrypoints`: use ONLY `main`, `wsgi_app`, `cli_script`, `dev_server`,
    `ui_root`. Use `cli_script` for CLI executables defined via a
    `[project.scripts]` entry or equivalent. Use `main` for the file that runs
    if you `python <file>` the project. If a project has additional notable
    runtime entry points that do not map to these (e.g. a custom MCP server, a
    worker daemon, an orchestrator class), OMIT them from `entrypoints` and add
    a `notes.other_notes` entry like "MCP server entry: `arrg/mcp/server.py
    :: MCPServer.run()`".

**Distinguishing frameworks, dependencies, and protocols:**

- `frameworks` lists **external runtime libraries the project imports** (e.g.
  Dash, React, FastAPI, Streamlit, Vue, Spring). Source must be a manifest
  file or an explicit import in a source sample.
- `dependencies` lists installable packages from a manifest. An SDK that
  consumes a protocol (e.g. the `mcp` Python package, `@modelcontextprotocol/sdk`)
  is a dependency.
- `protocols_implemented` lists **industry-standard protocols, specifications,
  or wire formats the project implements in-project** — meaning there is local
  code that constructs and parses the protocol's wire messages, types, state
  machine, or RPC envelopes itself. Examples: A2A (Agent-to-Agent Protocol),
  MCP (Model Context Protocol), OAuth 2.0, JSON-RPC, WebSocket, OpenAPI, gRPC,
  ActivityPub. Each entry should cite the in-project directory or files where
  the implementation lives. Omit the field entirely if nothing applies.

  **Decision test (apply for every candidate protocol):** Does the project
  contain local code that constructs/parses the protocol's wire messages,
  types, state machine, or RPC envelopes itself — separate from any vendor
  SDK that handles those mechanics? If yes, include it in
  `protocols_implemented`. If the project only USES a vendor SDK that handles
  the protocol mechanics (even when you observe a local glue file that imports
  the SDK and configures or calls into it), list the SDK in `dependencies` and
  do NOT add a `protocols_implemented` entry. Local code that merely *consumes*
  a protocol via an SDK is not "implementing" the protocol.

  **Version field rule:** The `version` value must be the **protocol
  specification version** (e.g. `"1.0"`, `"2025-11-25"`, `"2.0"`). Never use
  the SDK or library package version (e.g. `mcp>=1.26.0` → the spec version
  is `2025-11-25`, not `1.26.0`). If the protocol spec version cannot be
  determined from the evidence, omit the `version` key — do not substitute
  the SDK version.

**Empty or non-software directory:** Set `is_software_project: false` only when the
directory meets ALL of these criteria:

1. No source files in any recognized programming language. This INCLUDES web
   languages: HTML, CSS, JavaScript, TypeScript, and template files (Jinja,
   Handlebars, etc.). A directory containing `index.html` and `styles.css` is
   a software project even with no build system.
2. No deployment signals (no Dockerfile, docker-compose, Procfile, CI workflow,
   `CNAME`, `_config.yml`, `vercel.json`, `netlify.toml`, or similar).
3. Either truly empty, or contains only documentation and asset files (PDFs,
   images, design files, raw datasets without code that processes them).

**Static-site clarification (load-bearing):** Hand-authored static web content —
HTML, CSS, vanilla JavaScript or TypeScript, with no `package.json` / `webpack` /
`vite` / `npm` build pipeline — IS a software project. Set
`is_software_project: true`, leave `build_system.tool` absent (or omit
`build_system` entirely), set `ui_summary.kind: "mpa"` for multi-page sites or
`"spa"` for single-page sites, list the entry HTML file(s) in
`ui_summary.entry_files`, list HTML/CSS/JavaScript in `languages`, and treat
the directory layout normally for `directory_map`. GitHub Pages projects,
hand-authored marketing sites, and Jekyll/Hugo source trees all qualify.
Downstream agents (Brainstormer, Designer, Phaser) can produce useful output
for these projects — collapsing them to the empty form removes their access.

When the directory truly meets all three empty-project criteria above, briefly
explain what you found in one or two sentences, then immediately output the
minimal JSON (see Empty Project Format below). Do not ask follow-up questions.

**Interaction flow (one-shot draft, then targeted corrections):**

1. **Draft.** Analyze the project evidence and produce a single readable summary of
   the full review, organized under these section names: Project Type, Architecture,
   Languages & Frameworks, Build System & Dependencies, Commands & Entrypoints,
   Directory Map, UI Summary, Persistence, Environment Variables, Deployment,
   API Surface, Authentication, Coding Style, Test Coverage & CI, Notable
   Observations. Only include the sections that apply to this project — for
   example, skip Persistence for a project with no database, skip API Surface
   for a CLI, skip Deployment for a library. Present it once, in full.
2. **Ask.** End with: "Anything to correct? Reference sections by name, or reply
   'looks good' to finalize." Do not solicit per-section confirmation; the user will
   point out what needs fixing.
3. **Revise.** Apply corrections the user names. Only re-present full sections that
   materially changed. For minor fixes, acknowledge briefly.
4. **Generate JSON.** When the user says it looks good (or equivalent), output only
   the fenced JSON code block — no preface, no narration. The block must validate
   against the schema below.

**JSON Output Schema (schema_version = 1):**

```json
{
  "code_review": {
    "schema_version": 1,
    "is_software_project": true,
    "project_type": "string — concise label, e.g. 'web application — Dash SPA' or 'CLI tool'",
    "existing_self_description": {
      "text": "string — VERBATIM quote (1–3 sentences) from the named source. Do not paraphrase. If no clear self-description exists, omit the entire existing_self_description object.",
      "source": "README.md | pyproject.toml | package.json | etc."
    },
    "architecture": {
      "summary": "string — concise prose, one or two sentences",
      "pattern": "string — e.g. 'layered', 'MVC', 'microservices', 'pipeline'",
      "inferred_from": "string — file path that supports the classification"
    },
    "languages": [
      {"name": "Python", "source": "pyproject.toml"}
    ],
    "frameworks": [
      {"name": "Dash", "source": "pyproject.toml"}
    ],
    "protocols_implemented": [
      {
        "name": "string — e.g. 'A2A Protocol v1.0', 'MCP', 'OAuth 2.0', 'JSON-RPC'",
        "version": "string — e.g. '1.0', '2025-11-25' (omit if unspecified)",
        "location": "string — in-project directory or file path implementing it",
        "source": "string — README.md or source file where the implementation is cited"
      }
    ],
    "runtime_versions": {
      "python": ">=3.12",
      "node": "20",
      "_source": "pyproject.toml / package.json / .nvmrc / .tool-versions"
    },
    "build_system": {
      "tool": "uv",
      "manifest": "pyproject.toml",
      "build_backend": "uv_build"
    },
    "dependencies": [
      {"name": "dash", "purpose": "Web UI framework", "source": "pyproject.toml"}
    ],
    "commands": {
      "build": "string — canonical key, e.g. 'make build' or 'npm run build'",
      "test": "string — canonical key, e.g. 'make test' or 'uv run pytest'",
      "lint": "string — canonical key",
      "typecheck": "string — canonical key",
      "run": "string — canonical key",
      "dev": "string — canonical key",
      "deploy": "string — canonical key"
    },
    "entrypoints": {
      "main": "string — canonical key, file run by `python <file>`",
      "wsgi_app": "string — canonical key, e.g. 'spec4.app:server'",
      "cli_script": "string — canonical key, e.g. 'spec4 = spec4.app:main'",
      "dev_server": "string — canonical key, dev-mode launch command",
      "ui_root": "string — canonical key, UI root file when applicable"
    },
    "directory_map": [
      {"path": "src/spec4/agents/", "role": "pipeline LLM agents"},
      {"path": "src/spec4/callbacks/", "role": "Dash server-side callbacks"},
      {"path": "tests/", "role": "pytest suite"}
    ],
    "persistence": {
      "databases": [
        {"engine": "PostgreSQL", "role": "primary", "source": "docker-compose.yml"},
        {"engine": "Redis", "role": "cache", "source": "docker-compose.yml"}
      ],
      "orm": {"name": "SQLAlchemy", "source": "pyproject.toml"},
      "migration_tool": {"name": "Alembic", "source": "pyproject.toml"},
      "migrations_path": "migrations/"
    },
    "env_vars": [
      {
        "name": "DATABASE_URL",
        "purpose": "Postgres connection string",
        "required": true,
        "source": "src/spec4/db.py"
      },
      {
        "name": "DASH_DEBUG",
        "purpose": "Enable Dash hot reload (dev only)",
        "required": false,
        "inferred_from": "Makefile"
      }
    ],
    "deployment": {
      "containerization": {
        "tool": "docker",
        "dockerfile_path": "Dockerfile",
        "compose_path": "docker-compose.yml",
        "base_image": "python:3.12-slim",
        "source": "Dockerfile"
      },
      "orchestration": {
        "tool": "kubernetes",
        "manifests_path": "k8s/",
        "source": "k8s/deployment.yaml"
      },
      "paas": {
        "platform": "fly.io",
        "config_path": "fly.toml",
        "source": "fly.toml"
      },
      "iac": {
        "tool": "terraform",
        "path": "infra/",
        "source": "infra/main.tf"
      }
    },
    "api_surface": [
      {
        "protocol": "http",
        "path_or_method": "GET /users/:id",
        "handler": "users.get_user",
        "summary": "Fetch a user by ID",
        "source": "src/app/routes.py"
      },
      {
        "protocol": "grpc",
        "path_or_method": "UserService.GetUser",
        "source": "proto/user.proto"
      }
    ],
    "auth": {
      "model": "oauth",
      "provider": "Auth0",
      "library": "authlib",
      "source": "src/spec4/auth.py"
    },
    "ui_summary": {
      "has_ui": true,
      "kind": "spa  // one of: spa | mpa | mobile | desktop | tui | none",
      "framework": "Dash + Mantine",
      "styling": "Mantine component primitives + custom CSS",
      "routing": "dcc.Location + url.pathname → PATH_TO_PHASE",
      "entry_files": ["src/spec4/app.py", "src/spec4/layouts/_chat.py"]
    },
    "coding_style": {
      "linter": {"value": "ruff", "source": "pyproject.toml"},
      "formatter": {"value": "ruff format", "source": "pyproject.toml"},
      "type_checker": {"value": "mypy strict", "source": "pyproject.toml"},
      "indentation": {"value": "4 spaces", "inferred_from": "src/spec4/session.py"},
      "quotes": {"value": "double", "inferred_from": "src/spec4/session.py"},
      "line_length": {"value": 88, "source": "pyproject.toml"},
      "naming_conventions": {
        "functions": {"value": "snake_case", "inferred_from": "src/spec4/session.py"},
        "classes": {"value": "PascalCase", "inferred_from": "src/spec4/agents/code_scanner.py"}
      }
    },
    "notes": {
      "test_coverage": {
        "has_tests": true,
        "framework": "pytest",
        "covered_modules": ["agents", "project_manager", "session"],
        "uncovered_modules": ["app.py", "callbacks/", "layouts/"],
        "coverage_summary": "string — use INSTEAD of covered/uncovered when module-level coverage cannot be cleanly inferred",
        "inferred_from": "tests/ directory listing"
      },
      "ci_cd": {
        "present": false,
        "type": null,
        "path": null
      },
      "incomplete_or_dead_code": [
        "Phaser will avoid extending these files in future phases unless explicitly directed."
      ],
      "change_risks": [
        {
          "area": "session.py state mutation",
          "risk": "background-thread agent mutations are merged back via streaming.pop; new fields must respect this contract",
          "mitigation_hint": "always update via {**session, key: value} in callbacks; mutate-in-place only in agent threads"
        }
      ],
      "security_observations": [
        "API keys stored in browser localStorage via dcc.Store; never persisted server-side"
      ],
      "other_notes": [
        "py.typed marker present — package declares itself fully typed",
        "Custom non-canonical commands and entry points belong here as one-line strings: 'CLI invocation: `arrg cli --topic <topic>`'"
      ]
    }
  }
}
```

**Empty Project Format (use exactly this shape when is_software_project is false):**

```json
{
  "code_review": {
    "schema_version": 1,
    "is_software_project": false,
    "summary": "string — one or two sentences describing what was found (or that the directory is empty)"
  }
}
```

**Field rules:**

- `schema_version`, `is_software_project` are REQUIRED in every review.
- When `is_software_project` is true, these are REQUIRED: `project_type`, `languages`,
  `frameworks`, `build_system`, `commands`, `entrypoints`, `ui_summary`, `notes`.
- `protocols_implemented` is OPTIONAL — include it only when the project ships
  its own implementation of a named industry-standard protocol or spec. Do not
  include it for projects that only consume protocols via an SDK dependency.
- Inside `commands`, `entrypoints`, and `runtime_versions`, omit individual keys you
  cannot verify. Do NOT write "none detected" / "n/a". An absent key means "not
  found in this project."
- **`commands` keys are CLOSED.** Use ONLY: `build`, `test`, `lint`, `typecheck`,
  `run`, `dev`, `deploy`. Any other invocation (e.g. `arrg cli --topic ...`,
  `make migrate`, `npm run storybook`) belongs in `notes.other_notes` as a
  one-line string. Do NOT add custom keys like `run_dashboard`, `run_cli`,
  `version`, `migrate`.
- **`entrypoints` keys are CLOSED.** Use ONLY: `main`, `wsgi_app`, `cli_script`,
  `dev_server`, `ui_root`. Additional notable entry points (custom servers,
  worker daemons, orchestrator classes) belong in `notes.other_notes`. Do NOT
  add custom keys like `cli_main`, `dashboard_ui`, `mcp_server`,
  `convenience_wrapper`.
- **"Omit-rather-than-invent" applies to KEYS, not to documented values.**
  The rule against inventing forbids: (a) fabricating commands or entry
  points the project does not actually have, and (b) coining custom keys
  outside the canonical vocabulary. It does NOT prevent you from
  populating canonical keys with invocations that ARE documented but are
  not wrapped in a Makefile target or `[project.scripts]` alias. If a
  project documents its build / test / lint / typecheck / run / dev /
  deploy invocation in any of `README.md`, `CONTRIBUTING.md`, `CLAUDE.md`,
  `AGENTS.md`, the `docs/` directory, or the package manifest's
  description field — even without a wrapping Makefile target — you SHOULD
  populate the corresponding canonical `commands.*` key with that
  documented invocation. Examples:
  - Project has `mypy = "strict"` in `pyproject.toml` and CLAUDE.md says
    "Type checking: `uv run mypy src/`" → populate `commands.typecheck:
    "uv run mypy src/"`.
  - Project's README states "Launch the dashboard with `arrg dashboard`" →
    populate `commands.run: "arrg dashboard"`.
  - Project's CONTRIBUTING.md says "Run tests via `pytest`" with no
    Makefile target → populate `commands.test: "pytest"`.
  Phaser depends on these populated keys to write executable verification
  criteria. Leaving them empty when the project documents how to invoke
  them is over-conservative and degrades downstream output.

  When the project does NOT document a particular invocation anywhere
  (no Makefile target, no manifest script, no README/CONTRIBUTING/CLAUDE
  mention), omit the key — that is the rule's intent.

- **Each canonical key in `commands` and `entrypoints` takes a SINGLE
  invocation as its value** — not a disjunction (`"X or Y"`), not a
  concatenation, not a list. If a project has multiple invocations that
  would all map to the same canonical key (e.g. two CLI scripts, two run
  modes, two test commands), pick the primary one — the invocation a new
  contributor would run first to verify the project works (typically the
  one documented most prominently in README, or the one referenced from
  the Makefile's default target) — and route the secondary invocations to
  `notes.other_notes` with a one-line description such as
  "Secondary CLI: `python -m kiji_inspector.generate_pairs <num_pairs>`"
  or "Alternate run mode: `make notebook`". A compound value like
  "python -m foo or python -m bar" will produce gibberish verification
  commands downstream — pick one.
- **The schema is closed.** Do NOT add custom sub-keys to any field
  (`build_system`, `coding_style`, `ui_summary`, `notes.test_coverage`, etc.).
  Additional observations go in `notes.other_notes` as strings.
- **Material defects belong in typed defect fields, not `other_notes`.**
  If you find a behavior defect — a broken command target, dead configuration,
  a missing dependency that breaks a documented workflow, an internal contract
  violation, a config-drift mismatch, a documented invocation that does not
  actually function — it goes in `notes.incomplete_or_dead_code` (one entry
  per defect, one short sentence each) or `notes.change_risks` (with a
  mitigation_hint) — NEVER in `notes.other_notes`. The `other_notes` array
  is for residual factual observations (e.g. "`.python-version` file
  present"); it is NOT a catch-all for problems.
- **Defective-but-canonical commands** still belong in `commands.*` so
  downstream agents can find them by name, but you MUST pair them with a
  `notes.incomplete_or_dead_code` entry describing the breakage. Example:
  if `make lint` is a documented command but the Makefile target silently
  no-ops because `ruff` is not in the project's dependencies, list
  `commands.lint: "make lint"` AND add a defect entry like
  `"make lint silently no-ops: target invokes ruff but ruff is not declared
  in pyproject.toml dependencies; install ruff manually or add to
  dependencies before relying on this command."` Without the defect entry,
  Phaser will write `verification: "Run make lint"` and silently get a no-op
  pass on every phase touching Python code.
- **Do NOT rewrite the command value to mask a defect.** The `commands.*`
  value must be the clean canonical invocation a developer would type as a
  baseline. Specifically, do NOT embed any of these in the command string
  to silence a known failure mode:
  - Output redirection that hides errors: `2>/dev/null`, `&>/dev/null`,
    `2>&1 | grep -v ...`
  - Graceful-degradation fallbacks: `|| echo "skipping ..."`,
    `|| true`, `|| exit 0`, `|| :`
  - Conditional skip wrappers: `command -v ruff && ruff check ... || echo`
  Such patterns turn a defective command into an always-passing command,
  which causes Phaser to write verification steps that silently pass even
  when the underlying tooling is broken. Instead: write
  `commands.lint: "uv run ruff check ."` (clean) AND add a
  `notes.incomplete_or_dead_code` entry like `"uv run ruff check will fail
  until ruff is added to dev dependencies; project's lint workflow is
  currently broken."` This shape gives downstream agents both the canonical
  command name AND visibility into the defect.
- `ui_summary.has_ui` is REQUIRED whenever the `ui_summary` block is present. Set it
  to `false` for CLI / library / API-only projects and set `kind: "none"`.
- `ui_summary.kind` is a **closed enum**. Use ONLY one of: `"spa"`,
  `"mpa"`, `"mobile"`, `"desktop"`, `"tui"`, `"none"`. Do NOT invent values
  like `"streamlit_dashboard"`, `"web_app"`, `"hybrid"`, or `"dashboard"`.
  Express specifics in `ui_summary.framework` (e.g. `"Streamlit"`,
  `"Dash + Mantine"`) and `ui_summary.styling`. A Streamlit dashboard is
  `kind: "spa"` with `framework: "Streamlit"`. A multi-page server-rendered
  app is `kind: "mpa"`. A terminal UI (curses, Textual, Bubble Tea) is
  `kind: "tui"`. Use `"none"` only when `has_ui` is `false`.
- **`ui_summary` describes the PRIMARY user-facing UI only.** When a
  project ships multiple distinct UIs (e.g. a CLI/TUI plus a web UI, a
  demo UI plus a separate API server, multiple demo variants), describe
  exactly one — the UI most likely to be referenced or modified by
  downstream agents. The primary UI is typically the one launched by
  `commands.run` or pointed to by `entrypoints.ui_root`, or the one
  demonstrated most prominently in the README. List secondary UIs in
  `notes.other_notes` with their entry files and `kind`, e.g.
  "Secondary UI: Rich TUI variant at `demo/investment_demo_ui.py` (kind: tui)"
  or "Sibling REST service: FastAPI server at `sae-inference-server/app/main.py` (no UI)".
  `ui_summary.framework` is a SINGLE string value (e.g. `"Streamlit"`),
  never a comma-separated list of multiple UIs' frameworks. If the project
  has no UI at all (CLI-only / library / API-only), set `has_ui: false`
  and `kind: "none"`.
- **`persistence`** — include only when the project actually has a persistence
  layer. Evidence: a DB driver / ORM in dependencies, a database connection
  string in source samples, a docker-compose service for a database, a
  migrations directory.
  - `databases[]` lists each persistent data store. `engine` is the database
    PRODUCT name as it appears in vendor docs (`PostgreSQL`, `MySQL`,
    `SQLite`, `Redis`, `MongoDB`, `Elasticsearch`, `DynamoDB`, etc.), NEVER
    an ORM, wrapper library, or SDK name. `role` is short free text:
    `primary`, `cache`, `search`, `queue`, `analytics`, etc.
  - `orm` is the ORM or query-builder LIBRARY the project uses
    (`SQLAlchemy`, `Prisma`, `TypeORM`, `Drizzle`, `ActiveRecord`,
    `Sequelize`). The ORM also appears in `dependencies` — that is not
    duplication; `persistence.orm` is the discriminator pointing to which
    dependency plays this role.
  - `migration_tool` is the migration framework (`Alembic`, `Flyway`,
    `Liquibase`, `Prisma Migrate`, `goose`, `dbmate`). `migrations_path` is
    the directory holding migration files relative to the project root.
  - Omit `persistence` entirely (do not emit an empty object) when the
    project has no persistence layer.
- **`env_vars`** — list required and optional environment variables.
  Evidence: explicit reads in source files (e.g. `os.environ["FOO"]`,
  `process.env.BAR`), references in deployment configs (Dockerfile `ENV` /
  `ARG`, `fly.toml`, `docker-compose.yml`), or a `.env.example` file. Set
  `required: true` for variables without which the application will not
  start (DB URLs, auth secrets, mandatory API keys); set `required: false`
  for development-only or behavioral toggles. Use the `source` field to
  cite the file where the variable is read/declared.
- **`env_vars` is NAME-ONLY (load-bearing security rule).** Each entry
  contains the variable NAME, an optional PURPOSE describing what the
  variable controls, and `required`. NEVER include a `value`, `default`,
  `example_value`, `secret`, or any other field that holds the variable's
  contents — even when an example value appears in `.env.example` or a
  docker-compose file. Values are a security boundary and live in the
  developer's secret store, not in this artifact. The schema explicitly
  rejects a `value` key; emitting one is a critical violation that may
  leak credentials to anyone who reads `code_review.json`.
- **`deployment`** — capture infrastructure signals found in the project.
  Each sub-field's presence requires concrete file evidence:
  - `containerization` requires a real `Dockerfile` and/or
    `docker-compose.yml` / `compose.yaml`. `tool` is the actual tool name
    (`docker`, `podman`, `nerdctl`). `base_image` is the verbatim `FROM`
    line from the Dockerfile.
  - `orchestration` requires real Kubernetes / Helm / Nomad manifests.
    `tool` is the actual orchestrator (`kubernetes`, `helm`, `nomad`,
    `swarm`); `manifests_path` is the directory holding the manifests.
  - `paas` requires a real platform config file (`fly.toml`, `vercel.json`,
    `netlify.toml`, `render.yaml`, `Procfile`, `app.yaml`,
    `railway.json`). `platform` is the platform name.
  - `iac` requires real Terraform (`*.tf`), Pulumi, or CDK files.
    `tool` is the framework name; `path` is the IaC directory.
  - Omit any sub-field with no file evidence. Omit `deployment` entirely
    when no deployment infrastructure exists in the project at all.
- **`api_surface`** — sample, not exhaustive. For projects with many
  routes/methods, include up to ~8 representative entries that cover the
  primary verbs and resource categories. For libraries and CLIs with no
  network API, omit the field. Evidence: route declarations, gRPC service
  definitions, GraphQL schema files, RPC handler registrations in the
  source samples.
  - `protocol` is a CLOSED enum: `"http"`, `"graphql"`, `"grpc"`,
    `"websocket"`, `"rpc"`, `"other"`. Do NOT invent new values.
  - `path_or_method` format conventions:
    - For `http`: `"METHOD /path"`, e.g. `"GET /users/:id"`, `"POST /api/login"`.
    - For `grpc`: `"Service.Method"`, e.g. `"UserService.GetUser"`.
    - For `graphql`: the operation name, e.g. `"getUser"` / `"createUser"`.
    - For `websocket`: the connection path, e.g. `"/ws/stream"`.
    - For `rpc`/`other`: free-form, but specific.
  - `handler` is the function/method that implements the endpoint; cite
    its location in `source`. `summary` is one short sentence — omit when
    redundant with `path_or_method`.
- **`auth`** — include when the project has any authentication mechanism.
  `model` is a CLOSED enum: `"session"`, `"jwt"`, `"oauth"`, `"sso"`,
  `"api_key"`, `"basic"`, `"mtls"`, `"none"`, `"other"`. Use `"none"`
  explicitly when an application that COULD have auth has chosen not to;
  omit the entire `auth` block for libraries / CLIs where auth is not a
  meaningful concept. `provider` is the identity provider when applicable
  (`Auth0`, `Clerk`, `Cognito`, `Okta`, `Keycloak`, `custom`). `library` is
  the auth implementation library (`authlib`, `passport.js`, `devise`,
  `next-auth`). NEVER include any secret, token, password, signing key,
  client secret, or credential value — only the auth MECHANISM. The
  schema rejects custom sub-keys; do not add `secret`, `signing_key`,
  `client_secret`, or similar.
- `notes.ci_cd.present` is REQUIRED (boolean) whenever `notes` is present.
- `notes.test_coverage` shape (when `has_tests` is `true`): EITHER include both
  `covered_modules` and `uncovered_modules` arrays, OR include a single
  `coverage_summary` string. Do not mix — pick the form you can fill cleanly
  from the evidence. If even a one-line summary is not supported by the
  evidence, leave `notes.test_coverage` out of the review.
- For `naming_conventions`, omit any sub-key you cannot infer with confidence rather
  than guessing.
- `existing_self_description.text` must be a VERBATIM quote of 1–3 sentences
  from the named source. Do not paraphrase. Do NOT fabricate a description
  and attribute it to a source; do NOT synthesize prose "from project context"
  and present it as if it were quoted. If no source contains a clearly
  quotable self-description, OMIT the entire `existing_self_description`
  object — leave the key absent rather than constructing content.

  **Quotable sources** (where descriptive prose typically lives):
  `README.md` / `README.rst` / `README.txt`, the `description` field in
  `pyproject.toml` / `package.json` / `Cargo.toml` / `Gemfile`, the
  top-level module docstring of an obvious entry file (e.g.
  `src/spec4/__init__.py`), or a `description` field in `app.yaml` /
  similar manifests.

  **NOT quotable sources** (these contain configuration data, not
  descriptive prose, even if they imply something about the project):
  `CNAME`, `sitemap.xml`, `robots.txt`, `.gitignore`, `.python-version`,
  `Makefile`, lock files, CI workflow YAML, `tsconfig.json`,
  `vercel.json`, `netlify.toml`, or any other config/data file. If your
  only candidate source is one of these, omit `existing_self_description`
  rather than attributing fabricated text to it.

Output only the fenced JSON code block when emitting the final review — no
additional text after it.
"""


def _extract_review_json(text: str) -> dict[str, Any] | None:
    data = _extract_json_block(text)
    return data if data is not None and "code_review" in data else None


def _extract_and_validate_review(
    text: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Extract and validate the JSON code review from text.

    Tries a fenced ```json``` block first (the standard prompt-driven path),
    then falls back to parsing the whole stripped body as raw JSON (the
    shape produced by `response_format={"type": "json_object"}` on the
    retry turn).

    Three outcomes:
    - `(review, [])`     — JSON parsed and validated cleanly.
    - `(None, errors)`   — JSON parsed but failed schema validation;
                          caller should surface `errors` back to the LLM
                          and retry once.
    - `(None, [])`       — no JSON found at all; the agent is still in
                          conversation, no retry needed.
    """
    data = _extract_json_block(text)
    if data is None:
        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                data = parsed
    if data is None:
        return None, []
    if "code_review" not in data:
        return None, ["<root>: extracted JSON block is missing the 'code_review' key"]
    errors = validate_code_review(data)
    if errors:
        return None, errors
    return data, []


def _as_str_list(value: Any) -> list[str]:
    """Coerce a value to list[str], guarding against the LLM returning a string."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [value] if value else []
    return []


def _name_label(item: Any) -> str:
    """Render an entry as 'Name' or 'Name (source: foo)' across legacy/new shapes."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        name = str(item.get("name", "") or "")
        source = item.get("source")
        return f"{name} (source: {source})" if name and source else name or str(item)
    return str(item)


def _style_value(field: Any) -> str:
    """Render a coding_style field as 'value' or 'value (source: X)' / 'value (from: X)'.

    Accepts either a raw scalar (legacy) or a dict with value+source/inferred_from.
    """
    if isinstance(field, dict):
        value = field.get("value", "")
        source = field.get("source")
        inferred = field.get("inferred_from")
        if source:
            return f"{value} (source: {source})"
        if inferred:
            return f"{value} (inferred from: {inferred})"
        return str(value)
    return str(field) if field is not None else ""


def _normalize_style_for_renderer(style: dict[str, Any]) -> dict[str, Any]:
    """Flatten provenance-tagged style entries to scalars for legacy renderer."""
    if not isinstance(style, dict):
        return {}
    flat: dict[str, Any] = {}
    for key, val in style.items():
        if key == "naming_conventions" and isinstance(val, dict):
            flat[key] = {
                k: v.get("value") if isinstance(v, dict) else v
                for k, v in val.items()
            }
        elif isinstance(val, dict) and "value" in val:
            flat[key] = _style_value(val)
        else:
            flat[key] = val
    return flat


def _format_empty_review(cr: dict[str, Any]) -> str:
    """Render the is_software_project=false display."""
    lines = ["**Code Review Complete**\n"]
    summary = cr.get("summary")
    notes = cr.get("notes")
    if summary:
        lines.append(f"{summary}\n")
    elif isinstance(notes, str):
        lines.append(f"{notes}\n")
    elif isinstance(notes, list):
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")
    else:
        lines.append(
            "This directory does not appear to contain a software project.\n"
        )
    lines.append(
        "---\n\n"
        "You can still continue to the **Brainstormer** to define a vision for a new "
        "project in this directory."
    )
    return "\n".join(lines)


def _format_review_as_text(review: dict[str, Any]) -> str:
    cr = review.get("code_review", {})
    if cr.get("is_software_project") is False:
        return _format_empty_review(cr)

    lines: list[str] = ["**Code Review Complete**\n"]

    if "project_type" in cr:
        lines.append(f"**Project Type:** {cr['project_type']}\n")

    self_desc = cr.get("existing_self_description")
    if isinstance(self_desc, dict) and self_desc.get("text"):
        src = self_desc.get("source", "")
        suffix = f" _(from {src})_" if src else ""
        lines.append(f"**Existing self-description:** {self_desc['text']}{suffix}\n")
    elif isinstance(self_desc, str) and self_desc:
        lines.append(f"**Existing self-description:** {self_desc}\n")

    arch = cr.get("architecture")
    if isinstance(arch, dict):
        summary = arch.get("summary", "")
        pattern = arch.get("pattern", "")
        if summary or pattern:
            label = " / ".join(p for p in (pattern, summary) if p)
            lines.append(f"**Architecture:** {label}\n")
    elif isinstance(arch, str) and arch:
        lines.append(f"**Architecture:** {arch}\n")

    langs = cr.get("languages", [])
    frameworks = cr.get("frameworks", [])
    parts: list[str] = []
    for item in langs if isinstance(langs, list) else []:
        parts.append(_name_label(item))
    for item in frameworks if isinstance(frameworks, list) else []:
        parts.append(_name_label(item))
    if isinstance(langs, str) and langs:
        parts.append(langs)
    if isinstance(frameworks, str) and frameworks:
        parts.append(frameworks)
    if parts:
        lines.append(f"**Languages & Frameworks:** {', '.join(parts)}\n")

    protocols = cr.get("protocols_implemented")
    if isinstance(protocols, list) and protocols:
        lines.append("**Protocols Implemented:**")
        for proto in protocols:
            if isinstance(proto, dict):
                name = proto.get("name", "")
                version = proto.get("version", "")
                location = proto.get("location", "")
                head = f"{name} v{version}" if version else name
                tail = f" — `{location}`" if location else ""
                lines.append(f"- {head}{tail}" if head else f"- {proto}")
            else:
                lines.append(f"- {proto}")
        lines.append("")

    runtime = cr.get("runtime_versions")
    if isinstance(runtime, dict) and runtime:
        items = [
            f"{k}: {v}" for k, v in runtime.items() if not k.startswith("_") and v
        ]
        if items:
            lines.append(f"**Runtime versions:** {', '.join(items)}\n")

    build = cr.get("build_system")
    if isinstance(build, dict):
        tool = build.get("tool", "")
        manifest = build.get("manifest", "")
        backend = build.get("build_backend", "")
        suffix_bits = [b for b in (manifest, backend) if b]
        suffix = f" ({', '.join(suffix_bits)})" if suffix_bits else ""
        if tool:
            lines.append(f"**Build System:** {tool}{suffix}\n")
    elif isinstance(build, str) and build:
        lines.append(f"**Build System:** {build}\n")

    raw_deps = cr.get("dependencies", [])
    deps: list[Any] = raw_deps if isinstance(raw_deps, list) else []
    if deps:
        lines.append("**Dependencies:**")
        for d in deps:
            if isinstance(d, dict):
                name = d.get("name", "")
                purpose = d.get("purpose", "")
                source = d.get("source", "")
                suffix_bits = [p for p in (purpose, f"source: {source}" if source else "") if p]
                suffix = f" — {' · '.join(suffix_bits)}" if suffix_bits else ""
                lines.append(f"- {name}{suffix}" if name else f"- {d}")
            else:
                lines.append(f"- {d}")
        lines.append("")

    commands = cr.get("commands")
    if isinstance(commands, dict) and commands:
        lines.append("**Commands:**")
        for key in ("build", "test", "lint", "typecheck", "run", "dev", "deploy"):
            if key in commands and commands[key]:
                lines.append(f"- {key}: `{commands[key]}`")
        lines.append("")

    entrypoints = cr.get("entrypoints")
    if isinstance(entrypoints, dict) and entrypoints:
        lines.append("**Entrypoints:**")
        for key in ("main", "wsgi_app", "cli_script", "dev_server", "ui_root"):
            if key in entrypoints and entrypoints[key]:
                lines.append(f"- {key.replace('_', ' ')}: `{entrypoints[key]}`")
        lines.append("")

    dmap = cr.get("directory_map")
    if isinstance(dmap, list) and dmap:
        lines.append("**Directory Map:**")
        for entry in dmap:
            if isinstance(entry, dict):
                path = entry.get("path", "")
                role = entry.get("role", "")
                lines.append(f"- `{path}` — {role}" if path else f"- {entry}")
            else:
                lines.append(f"- {entry}")
        lines.append("")

    _render_persistence(cr.get("persistence"), lines)
    _render_env_vars(cr.get("env_vars"), lines)
    _render_deployment(cr.get("deployment"), lines)
    _render_api_surface(cr.get("api_surface"), lines)
    _render_auth(cr.get("auth"), lines)

    ui = cr.get("ui_summary")
    if isinstance(ui, dict) and ui:
        has_ui = ui.get("has_ui")
        if has_ui is False:
            lines.append("**UI:** none (CLI / library / API-only)\n")
        elif has_ui is True:
            kind = ui.get("kind", "")
            framework = ui.get("framework", "")
            styling = ui.get("styling", "")
            bits = [b for b in (kind, framework, styling) if b]
            lines.append(f"**UI:** {' · '.join(bits)}\n" if bits else "**UI:** present\n")

    _render_coding_style(_normalize_style_for_renderer(cr.get("coding_style", {})), lines)

    notes = cr.get("notes")
    if isinstance(notes, dict):
        _render_typed_notes(notes, lines)
    else:
        notes_list = _as_str_list(notes if notes is not None else [])
        if notes_list:
            lines.append("**Notable Observations:**")
            for note in notes_list:
                lines.append(f"- {note}")
            lines.append("")

    lines.append(
        "---\n\n"
        "We've finished the code review, so now you're ready to move on to creating "
        "a vision. Please click on the **Continue to Brainstormer** button below."
    )
    return "\n".join(lines)


def _render_persistence(persistence: Any, lines: list[str]) -> None:
    if not isinstance(persistence, dict) or not persistence:
        return
    bits: list[str] = []
    dbs = persistence.get("databases") or []
    if isinstance(dbs, list) and dbs:
        db_parts: list[str] = []
        for db in dbs:
            if not isinstance(db, dict):
                continue
            engine = db.get("engine", "")
            role = db.get("role", "")
            if engine and role:
                db_parts.append(f"{engine} ({role})")
            elif engine:
                db_parts.append(engine)
        if db_parts:
            bits.append(f"databases: {', '.join(db_parts)}")
    orm = persistence.get("orm")
    if isinstance(orm, dict) and orm.get("name"):
        bits.append(f"ORM: {orm['name']}")
    migration = persistence.get("migration_tool")
    if isinstance(migration, dict) and migration.get("name"):
        bits.append(f"migrations: {migration['name']}")
    mig_path = persistence.get("migrations_path")
    if mig_path:
        bits.append(f"migrations path: `{mig_path}`")
    if bits:
        lines.append(f"**Persistence:** {' · '.join(bits)}\n")


def _render_env_vars(env_vars: Any, lines: list[str]) -> None:
    if not isinstance(env_vars, list) or not env_vars:
        return
    lines.append("**Environment Variables:**")
    for entry in env_vars:
        if not isinstance(entry, dict):
            lines.append(f"- {entry}")
            continue
        name = entry.get("name", "")
        if not name:
            continue
        purpose = entry.get("purpose", "")
        required = entry.get("required")
        flag = " (required)" if required is True else " (optional)" if required is False else ""
        suffix = f" — {purpose}" if purpose else ""
        lines.append(f"- `{name}`{flag}{suffix}")
    lines.append("")


def _render_deployment(deployment: Any, lines: list[str]) -> None:
    if not isinstance(deployment, dict) or not deployment:
        return
    bits: list[str] = []
    container = deployment.get("containerization")
    if isinstance(container, dict) and container:
        tool = container.get("tool", "")
        dfp = container.get("dockerfile_path")
        compose = container.get("compose_path")
        base = container.get("base_image")
        sub_bits = [b for b in (
            f"`{dfp}`" if dfp else "",
            f"compose: `{compose}`" if compose else "",
            f"base: `{base}`" if base else "",
        ) if b]
        head = tool or "container"
        bits.append(f"{head} ({', '.join(sub_bits)})" if sub_bits else head)
    orch = deployment.get("orchestration")
    if isinstance(orch, dict) and orch:
        tool = orch.get("tool", "")
        manifests = orch.get("manifests_path")
        suffix = f" — `{manifests}`" if manifests else ""
        if tool:
            bits.append(f"orchestration: {tool}{suffix}")
    paas = deployment.get("paas")
    if isinstance(paas, dict) and paas:
        platform = paas.get("platform", "")
        config = paas.get("config_path")
        suffix = f" — `{config}`" if config else ""
        if platform:
            bits.append(f"PaaS: {platform}{suffix}")
    iac = deployment.get("iac")
    if isinstance(iac, dict) and iac:
        tool = iac.get("tool", "")
        path = iac.get("path")
        suffix = f" — `{path}`" if path else ""
        if tool:
            bits.append(f"IaC: {tool}{suffix}")
    if bits:
        lines.append("**Deployment:**")
        for bit in bits:
            lines.append(f"- {bit}")
        lines.append("")


def _render_api_surface(api_surface: Any, lines: list[str]) -> None:
    if not isinstance(api_surface, list) or not api_surface:
        return
    lines.append("**API Surface:**")
    for entry in api_surface:
        if not isinstance(entry, dict):
            lines.append(f"- {entry}")
            continue
        protocol = entry.get("protocol", "")
        path_or_method = entry.get("path_or_method", "")
        handler = entry.get("handler", "")
        summary = entry.get("summary", "")
        head = f"[{protocol}] `{path_or_method}`" if path_or_method else f"[{protocol}]"
        tail_bits = [b for b in (
            f"→ `{handler}`" if handler else "",
            summary,
        ) if b]
        tail = f" — {' · '.join(tail_bits)}" if tail_bits else ""
        lines.append(f"- {head}{tail}")
    lines.append("")


def _render_auth(auth: Any, lines: list[str]) -> None:
    if not isinstance(auth, dict) or not auth:
        return
    model = auth.get("model", "")
    provider = auth.get("provider", "")
    library = auth.get("library", "")
    bits = [b for b in (model, provider, library) if b]
    if bits:
        lines.append(f"**Authentication:** {' · '.join(bits)}\n")


def _render_typed_notes(notes: dict[str, Any], lines: list[str]) -> None:
    tc = notes.get("test_coverage")
    if isinstance(tc, dict):
        bits: list[str] = []
        if tc.get("has_tests") is False:
            bits.append("no tests detected")
        else:
            fw = tc.get("framework")
            if fw:
                bits.append(f"framework: {fw}")
            summary = tc.get("coverage_summary")
            covered = tc.get("covered_modules") or []
            uncovered = tc.get("uncovered_modules") or []
            if summary:
                bits.append(str(summary))
            else:
                if covered:
                    bits.append(f"covered: {', '.join(covered)}")
                if uncovered:
                    bits.append(f"uncovered: {', '.join(uncovered)}")
        if bits:
            lines.append(f"**Test Coverage:** {' · '.join(bits)}\n")

    ci = notes.get("ci_cd")
    if isinstance(ci, dict):
        if ci.get("present"):
            path = ci.get("path") or ci.get("type") or "detected"
            lines.append(f"**CI/CD:** {path}\n")
        elif ci.get("present") is False:
            lines.append("**CI/CD:** none detected\n")

    dead = notes.get("incomplete_or_dead_code") or []
    if isinstance(dead, list) and dead:
        lines.append("**Incomplete or Dead Code:**")
        for item in dead:
            lines.append(f"- {item}")
        lines.append("")

    risks = notes.get("change_risks") or []
    if isinstance(risks, list) and risks:
        lines.append("**Change Risks:**")
        for risk in risks:
            if isinstance(risk, dict):
                area = risk.get("area", "")
                desc = risk.get("risk", "")
                mit = risk.get("mitigation_hint", "")
                head = f"**{area}** — {desc}" if area else desc
                lines.append(f"- {head}")
                if mit:
                    lines.append(f"  - Mitigation: {mit}")
            else:
                lines.append(f"- {risk}")
        lines.append("")

    sec = notes.get("security_observations") or []
    if isinstance(sec, list) and sec:
        lines.append("**Security Observations:**")
        for item in sec:
            lines.append(f"- {item}")
        lines.append("")

    other = notes.get("other_notes") or []
    if isinstance(other, list) and other:
        lines.append("**Other Notes:**")
        for note in other:
            lines.append(f"- {note}")
        lines.append("")


def _build_fresh_scan_seed(working_dir: str) -> str:
    context = _gather_project_context(working_dir)
    return (
        "Please introduce yourself as CodeScanner, then analyze this project "
        "directory and produce the full draft review in one shot as described in "
        "your operating instructions.\n\n"
        f"{context}"
    )


def _build_update_scan_seed(working_dir: str, prior_review: dict[str, Any]) -> str:
    context = _gather_project_context(working_dir)
    prior_json = json.dumps(prior_review, indent=2)
    return (
        "Please introduce yourself as CodeScanner. The user has asked you to "
        "re-scan this project, which already has a prior code review on disk.\n\n"
        "**Update mode instructions:**\n"
        "- Compare the latest project evidence below against the prior review.\n"
        "- Produce a structured **update** focusing only on what has changed: new "
        "dependencies, removed dependencies, version bumps, new commands or "
        "entrypoints, new files in the directory map, shifts in coding style, "
        "newly resolved or newly introduced incomplete/dead code, etc.\n"
        "- Present the changes as a readable summary grouped under the same "
        "section names used in the prior review. Mark each item explicitly as "
        "Added / Removed / Changed.\n"
        "- After presenting the changes, ask: \"Anything to correct? Reply "
        "'looks good' to merge and finalize.\"\n"
        "- When the user confirms, emit a complete updated `code_review` JSON block "
        "(schema_version 1) reflecting the merged state. The block must be "
        "complete — not a diff — so downstream agents always see the full review.\n\n"
        "**Prior code review on disk:**\n\n"
        f"```json\n{prior_json}\n```\n\n"
        "**Latest project evidence (fresh scan):**\n\n"
        f"{context}"
    )


def run(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """CodeScanner — analyzes the project directory and creates a structured code review.

    Yields text chunks consumed by streaming.start().
    Mutates `session` to track conversation state and review output.
    """
    if "code_scanner_messages" not in session:
        session["code_scanner_messages"] = []

    msgs = session["code_scanner_messages"]
    _drop_orphan_trailing_user(msgs)

    if user_input is None:
        if msgs:
            if (
                session.get("code_scanner_state") == STATE_REVIEW_COMPLETE
                and session.get("code_scanner_artifact_msg_count") == len(msgs)
                and session.get("code_review") is not None
            ):
                display = _format_review_as_text(session["code_review"])
                msgs[-1]["content"] = display
                session["_display_override"] = display
                yield display
                return
            if not _maybe_inject_resume_summary(
                session, "code_scanner", msgs, STATE_REVIEW_COMPLETE
            ):
                yield from _replay_last_assistant(msgs)
                return
        else:
            existing_review = session.get("code_review")
            if (
                existing_review is not None
                and session.get("code_scanner_state") == STATE_REVIEW_COMPLETE
            ):
                display = _format_review_as_text(existing_review)
                msgs.append(
                    {"role": "user", "content": "[Spec4: displaying existing code review]"}
                )
                msgs.append({"role": "assistant", "content": display})
                session["code_scanner_artifact_msg_count"] = len(msgs)
                session["_display_override"] = display
                yield display
                return

            working_dir = session.get("working_dir")
            if not working_dir:
                yield (
                    "I'm the **CodeScanner**. I analyze your project directory to "
                    "understand the existing codebase.\n\n"
                    "⚠️ No project directory has been selected. Please go back and "
                    "select a working directory first."
                )
                return

            if existing_review is not None:
                seed = _build_update_scan_seed(working_dir, existing_review)
            else:
                seed = _build_fresh_scan_seed(working_dir)
            msgs.append({"role": "user", "content": seed})
    else:
        msgs.append({"role": "user", "content": user_input})

    tavily_api_key = session.get("tavily_api_key")
    system = tavily_mcp.build_system_prompt(SYSTEM_PROMPT, tavily_api_key)

    yield from _stream_suppressing_json(
        tavily_mcp.stream_turn(
            system, msgs, llm_config, tavily_api_key, agent_name="code_scanner"
        )
    )

    review, errors = _extract_and_validate_review(_last_assistant_text(msgs))
    if review is None and errors:
        # JSON was emitted but failed schema validation. Retry once,
        # surfacing the specific errors back to the model. On providers
        # that support it, force json_object mode so the retry response
        # is pure JSON instead of prose-wrapped re-explanation.
        retry_user_msg = format_validation_errors_for_retry(errors)
        msgs.append({"role": "user", "content": retry_user_msg})
        response_format: dict[str, Any] | None = None
        if tavily_mcp.supports_response_format(llm_config.get("model", "")):
            response_format = {"type": "json_object"}
        # Drain the retry stream silently — its body is raw or fenced
        # JSON that the user should never see. The stream_turn generator
        # still mutates msgs to record the assistant reply.
        for _chunk in tavily_mcp.stream_turn(
            system,
            msgs,
            llm_config,
            tavily_api_key,
            agent_name="code_scanner",
            response_format=response_format,
        ):
            pass
        review, _ = _extract_and_validate_review(_last_assistant_text(msgs))
        if review is None:
            # Retry failed too. Drop the synthesized correction exchange
            # so the chat history does not carry a dead-end user turn,
            # surface a brief recoverable message in place of the bad
            # JSON, and leave code_scanner_state untouched so the user
            # can re-engage by chatting further.
            if (
                len(msgs) >= 2
                and msgs[-2].get("role") == "user"
                and msgs[-2].get("content") == retry_user_msg
            ):
                del msgs[-2:]
            fallback = (
                "I tried to emit the structured review but it didn't pass "
                "validation. Please point me to the section to correct, "
                "or reply 'try again' and I'll re-emit it."
            )
            if msgs and msgs[-1].get("role") == "assistant":
                msgs[-1]["content"] = fallback
            else:
                msgs.append({"role": "assistant", "content": fallback})
            session["_display_override"] = fallback

    if review:
        session["code_scanner_state"] = STATE_REVIEW_COMPLETE
        session["code_review"] = review
        display = _format_review_as_text(review)
        msgs[-1]["content"] = display
        session["_display_override"] = display
        session["code_scanner_artifact_msg_count"] = len(msgs)
