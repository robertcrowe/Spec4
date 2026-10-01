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