---
{
  "phase_number": 1,
  "total_phases": 8,
  "phase_title": "Integration Thread \u2014 ReAct Slice Wired Into the Existing Gallery",
  "phase_summary": "Wire a new, model-free ReAct Loop slice into the already-built BWS4 gallery end to end: the react_runs table, the backend/app/react/ package with its typed preset catalog, a presets endpoint, a stub SSE run endpoint that proves the streaming path, and a lazy-loaded frontend route that appears in both the landing roster and the persistent navigation. No model calls, no Exa calls, no loop logic \u2014 th",
  "features": [
    {
      "id": "react_loop_example_app",
      "role": "introduced",
      "scope_note": "Only the slice scaffolding lands here \u2014 the react_runs table, the questions-only preset catalog, a presets endpoint, a model-free stub SSE run endpoint, and the route/roster/navigation wiring; the loop, its observations, the terminal cards, the suitability check, the hop annotations and the overview copy all land in later phases."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "fastapi",
      "sse-starlette",
      "sqlalchemy",
      "asyncpg",
      "alembic",
      "pydantic",
      "pydantic-settings",
      "structlog",
      "pytest",
      "ruff",
      "mypy",
      "react",
      "react-router",
      "@tanstack/react-query",
      "vite",
      "tailwindcss",
      "vitest",
      "@testing-library/react"
    ]
  },
  "verification": "Run `uv run alembic upgrade head` and confirm the react_runs table exists with its header columns and JSONB columns. Start the backend with `uv run uvicorn backend.app.main:app --reload` and confirm it fails with a clear, descriptive error when any of DATABASE_URL, OPENROUTER_API_KEY, GROQ_API_KEY, EXA_API_KEY or CORS_ORIGIN is missing. Call GET /api/react/presets and confirm it returns exactly fi"
}
---
# Phase 1: Integration Thread — ReAct Slice Wired Into the Existing Gallery

_Trimmed fixture: frontmatter only; the prose body of the real phase is not reproduced._
