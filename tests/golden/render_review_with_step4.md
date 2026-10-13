**Code Review Complete**

**Scan Summary**

- Files: 2,412 (1890 .py, 402 .ts, 70 .yml, 31 .md, 12 .png) — 188,340 lines
- Skipped: `__pycache__` ×2, `node_modules` ×2, `.git`, `.venv`, `dist`
- Shown to the model: 4 of 2292 source files sampled, 3 manifests, README, 1 CI, 2 deployment, 10 signature files, 2 convention files (~22,814 tokens)
- Git: `main` @ `9f3c2ab`, 3 modified, 2 untracked; 14 commits since the last implemented round (2026-09-28), 2 authors, touching `.`, `src`, `tests`
- Load-bearing candidates: `src/app/models.py` (41), `src/app/config.py` (30), `src/app/db.py` (22), `src/app/auth.py` (9), `src/app/http.py` (7) and 2 more
- Reach: 1,874 modules from entrypoint `src/app/cli.py`, `src/app/main.py`, `src/app/server.py` and 1 more; unreached: `scripts`, `tools/bench`
- Prior round: v8 (3 phases; implemented 2025-10-01; catalog from v7); plan drift: 31 planned deps unmatched, 1 imported but undeclared, 2 declared but unplanned

**Project Type:** web app

**Existing self-description:** A Dash app for planning. _(from README.md)_

**Architecture:** monolith / one Flask process

**Load-Bearing Modules:**
- `src/app/llm.py` · `stream_turn` (consumers: 0) — The one path every agent's LLM call goes through
  - inputs: system prompt; message list, mutated in place
  - outputs: yields text chunks
  - invariants: messages ends with the assistant turn
  - side effects: records usage in the session; network calls
- `src/app/constants.py` (consumers: 0) — Session keys and state names shared by every module
  - outputs: string constants

**Implemented:**
- Structured code review [complete] — Walks a directory and drafts a schema-checked review · `src/app/scanner/` · prior: round_tree, agent_rows
- Deployment plan [stub] — `src/app/deployer.py`
- VPS runtime bring-up [complete] — Boots the API under systemd on the VPS with the environment contract from /etc/bws4 · `deploy/bws4.service`, `backend/app/main.py` · prior: self_hosted_deployment

**Prior Round Reconciliation** (feature coverage, not phase scope):
- phase 1 [evidence_partial] — `vps_runtime`; gap: The shared framework services package is planned but no module under backend/app/services exists yet
- phase 2 [evidence_partial] — `vps_runtime`; gap: Warm-at-boot is wired in the unit file but the model preload it names is a no-op
- phase 3 [unassessed]

**Unplanned Changes:**
- scanner evidence tiers [out_of_round] — The scanner gained tiered sampling and a most-touched body tier that no phase of the last round planned · affects: `src/app/scanner/`, `code_review`
- documentation and manifests [out_of_round] — CHANGELOG and lock-file churn across the round · affects: `CHANGELOG.md`, `uv.lock`
- deployment plan [unknown] — deployer.py is a stub that nothing in the prior plan introduced · affects: `src/app/deployer.py`

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
- no path
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

**Integrations:**
- litellm [llm_provider] — every model call · `src/app/llm.py` · env: OPENAI_API_KEY, ANTHROPIC_API_KEY
- Redis [cache] — `src/app/cache.py`

**Divergences:**
- persistence: Neon (serverless Postgres) + pgvector → PostgreSQL [renamed] — Same engine; the review names the product, the plan named the host
- providers: OpenRouter (via LiteLLM) → OpenRouter [renamed]
- deployment: netcup VPS (systemd) → docker [replaced] — A Dockerfile and compose file now ship; the unit file is still present

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