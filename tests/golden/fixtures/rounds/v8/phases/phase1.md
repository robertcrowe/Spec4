---
{
  "phase_number": 1,
  "total_phases": 6,
  "phase_title": "Integration Thread \u2014 VPS Baseline Bring-Up and Environment Contract Relocation",
  "phase_summary": "Prove the existing BWS4 repository builds, migrates and boots warm on the netcup VPS 500 G12 with the carried-over environment contract read from a root-owned 0600 secrets file outside the repository tree, verified through a single loopback health check. No Caddy, no TLS, no public exposure, and no application code change \u2014 this phase establishes that the existing codebase runs unmodified on the n",
  "features": [
    {
      "id": "self_hosted_deployment",
      "role": "introduced",
      "scope_note": "Establishes only that the existing application boots warm on the VPS with the relocated environment contract, reachable on loopback; process supervision lands in Phase 2, the trusted public HTTPS origin in Phase 3, and the canonical-address requirement in Phase 6."
    },
    {
      "id": "shared_framework_services",
      "role": "introduced",
      "scope_note": "Verifies the existing shared services substrate (embedding model load, Neon connectivity, provider credentials) initialises correctly under the VPS environment contract; no service behaviour is changed and the always-on warm retention guarantee is proven across restarts in Phase 2."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "Python 3.12",
      "uv",
      "Node 20",
      "FastAPI",
      "uvicorn",
      "SQLAlchemy",
      "asyncpg",
      "Alembic",
      "pgvector",
      "Pydantic",
      "pydantic-settings",
      "sentence-transformers",
      "torch",
      "scikit-learn",
      "numpy",
      "structlog",
      "sentry-sdk",
      "pytest",
      "Ruff",
      "mypy"
    ]
  },
  "verification": "All of the following must hold on the VPS. (1) `uv run alembic -c backend/alembic.ini current` reports the same revision as `heads`, confirming Neon with pgvector is reachable and at the repository's schema head. (2) With the environment sourced from /etc/bws4/bws4.env, `uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1` boots and the structlog JSON boot output contains "
}
---
# Phase 1: Integration Thread — VPS Baseline Bring-Up and Environment Contract Relocation

_Trimmed fixture: frontmatter only; the prose body of the real phase is not reproduced._
