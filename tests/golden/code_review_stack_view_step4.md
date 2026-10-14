**Existing self-description**
_How the project describes itself, verbatim._
- text: A Dash app for planning. [README.md]

**Existing architecture**
_The existing pattern. Extend it rather than restructure it unless the vision says otherwise._
- pattern: monolith
- summary: one Flask process

**Existing languages**
_Authoritative. Every language listed is in the codebase today._
- **Python** [pyproject.toml]
- JavaScript

**Existing runtime versions**
_Authoritative. Carry these versions forward as the floor._
- python: 3.12
- node: 20

**Existing frameworks**
_Authoritative. Already in use; a swap is a migration, not a choice._
- Dash

**Existing dependencies**
_Authoritative. Already declared; prefer them over a parallel library for the same purpose._
- **dash** — purpose: UI [pyproject.toml]
- **litellm**
- requests

**Existing build system**
_Authoritative. The existing build tool and manifest._
- tool: uv
- manifest: pyproject.toml
- build backend: uv_build

**Existing coding style**
_The existing toolchain and conventions, authoritative per language. Carry them forward exactly — the linter, formatter, type checker, indentation and quote style the codebase already uses. Do not substitute other tools._
- formatter: ruff [pyproject.toml]
- line length: 88 [ruff config]
- naming conventions:
  - functions: snake_case
  - classes: PascalCase
- docstrings: Google style

**Existing persistence**
_The existing data layer: engines, ORM, migration tool and migrations path._
- databases:
  - **SQLite** — role: cache
  - **Postgres**
  - bad
- orm: **SQLAlchemy**
- migration tool: **alembic**
- migrations path: migrations/

**Existing deployment**
_How the project already ships: containers, orchestration, PaaS, IaC._
- containerization: **Docker** — dockerfile path: Dockerfile; compose path: compose.yml; base image: python:3.12-slim
- orchestration: **Kubernetes** — manifests path: k8s/
- paas: **Fly.io** — config path: fly.toml
- iac: **infra/** — tool: Terraform

**Existing auth**
_The existing authentication model, provider and library._
- model: session
- provider: self
- library: flask-login

**Existing integrations**
_`llm_provider` entries are Topic 3's `providers`; the rest are your `integrations`, already in place._
- **litellm** — kind: llm_provider; client module: src/app/llm.py; config env vars: OPENAI_API_KEY; ANTHROPIC_API_KEY; purpose: every model call [pyproject.toml]
- **Redis** — kind: cache; client module: src/app/cache.py [src/app/cache.py]

**Divergences from the planned stack**
_Where the built stack departs from the one the last round planned. Record the built name, not the planned one — this is what D-CR7 overwrites from._
- **persistence** — planned: Neon (serverless Postgres) + pgvector; found: PostgreSQL; kind: renamed; note: Same engine; the review names the product, the plan named the host [backend/app/db.py]
- **providers** — planned: OpenRouter (via LiteLLM); found: OpenRouter; kind: renamed [backend/app/llm.py]
- **deployment** — planned: netcup VPS (systemd); found: docker; kind: replaced; note: A Dockerfile and compose file now ship; the unit file is still present [Dockerfile]

**Existing protocols implemented**
_Industry standards already wired in. Treat them as constraints when proposing changes._
- **MCP** — version: 2025-06; location: src/mcp
- **A2A**
- plain text

**Existing API surface**
_The existing routes and methods. Extend rather than parallel-invent._
- **/api/plan** — protocol: HTTP; handler: plan_view; summary: creates a plan
- protocol: gRPC
- raw

**Existing environment variables**
_Configuration the code already reads. Names only; never values._
- **OPENAI_API_KEY** — purpose: LLM access; required: yes
- **DASH_DEBUG** — required: no
- **PORT**
- purpose: nameless
- RAW_STRING

**Existing change risks**
_Typed observations about what is fragile. Weigh them before proposing a technology swap._
- **app.py** — risk: import order is load-bearing; mitigation hint: keep the noqa
- a bare risk

**Planned last round, not found in the code**
_Measured: technologies the last round's stack or phases named that no manifest declares and no module imports. They were never adopted or have since been dropped — do not carry them forward unexamined._
- **@microsoft/fetch-event-source** — sources: stack
- **@sentry/react** — sources: stack
- **Alembic** — sources: stack; phase:1
- **asyncpg** — sources: stack; phase:1
- **httpx** — sources: stack
- **LiteLLM** — sources: stack
- **mypy** — sources: stack; phase:1
- **Node 20** — sources: phase:1
- **numpy** — sources: stack; phase:1; phase:2
- **pgvector** — sources: stack; phase:1
- **Playwright** — sources: stack
- **plotly.js** — sources: stack
- **Pydantic** — sources: stack; phase:1
- **pydantic-settings** — sources: stack; phase:1; phase:2
- **pytest** — sources: stack; phase:1
- **Python 3.12** — sources: phase:1; phase:2
- **React Testing Library** — sources: stack
- **react-markdown** — sources: stack
- **react-plotly.js** — sources: stack
- **Ruff** — sources: stack; phase:1
- **scikit-learn** — sources: stack; phase:1; phase:2
- **sentence-transformers** — sources: stack; phase:1; phase:2
- **sentry-sdk** — sources: stack; phase:1; phase:2
- **SQLAlchemy** — sources: stack; phase:1
- **sse-starlette** — sources: stack
- **systemd** — sources: phase:2
- **tenacity** — sources: stack
- **torch** — sources: stack; phase:1; phase:2
- **uv** — sources: phase:1; phase:2
- **Vite** — sources: stack
- **Vitest** — sources: stack

**Declared in a manifest, not planned**
_Measured: dependencies a manifest declares that the last round's plan never named — adopted outside Spec4. Record them in the stack rather than proposing a parallel choice for the same purpose._
- **oxlint** — manifest: web/package.json
- **pytest-cov** — manifest: pyproject.toml

**Dependency changes since the prior scan**
_Measured: declared dependencies added, removed or bumped since the prior scan, per manifest. These are recent, deliberate choices — keep them unless the vision says otherwise._
- **pyproject.toml** — added: pydantic-ai, pytest-cov, structlog; removed: gone; bumped: fastapi