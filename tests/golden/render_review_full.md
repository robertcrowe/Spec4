**Code Review Complete**

**Project Type:** web app

**Existing self-description:** A Dash app for planning. _(from README.md)_

**Architecture:** monolith / one Flask process

**Languages & Frameworks:** Python (source: pyproject.toml), JavaScript, Dash

**Protocols Implemented:**
- MCP v2025-06 — `src/mcp`
- A2A
- plain text

**Runtime versions:** python: 3.12, node: 20

**Build System:** uv (pyproject.toml, uv_build)

**Dependencies:**
- dash — UI · source: pyproject.toml
- litellm
- requests

**Commands:**
- build: `uv build`
- test: `uv run pytest`
- run: `spec4`

**Entrypoints:**
- main: `src/spec4/app.py`
- cli script: `spec4`

**Directory Map:**
- `src/spec4` — package
- {'role': 'no path'}
- docs/

**Persistence:** databases: SQLite (cache), Postgres · ORM: SQLAlchemy · migrations: alembic · migrations path: `migrations/`

**Environment Variables:**
- `OPENAI_API_KEY` (required) — LLM access
- `DASH_DEBUG` (optional)
- `PORT`
- RAW_STRING

**Deployment:**
- Docker (`Dockerfile`, compose: `compose.yml`, base: `python:3.12-slim`)
- orchestration: Kubernetes — `k8s/`
- PaaS: Fly.io — `fly.toml`
- IaC: Terraform — `infra/`

**API Surface:**
- [HTTP] `/api/plan` — → `plan_view` · creates a plan
- [gRPC]
- raw

**Authentication:** session · self · flask-login

**AI Capabilities:**
- summariser [llm] — summarises threads · `src/ai.py`
- nameless-kind
- raw

**UI:** SPA · Dash · CSS

**Coding Style:**
- Formatter: ruff (source: pyproject.toml)
- Line Length: 88 (inferred from: ruff config)
- Naming: functions: snake_case, classes: PascalCase

**Test Coverage:** framework: pytest · covered: app · uncovered: cli

**CI/CD:** .github/workflows/ci.yml

**Incomplete or Dead Code:**
- old_view() is unused

**Change Risks:**
- **app.py** — import order is load-bearing
  - Mitigation: keep the noqa
- a bare risk

**Security Observations:**
- secrets read from env

**Other Notes:**
- README is stale

---

We've finished the code review, so now you're ready to move on to creating a vision. Please click on the **Continue to Brainstormer** button below.