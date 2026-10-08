---
{
  "phase_number": 2,
  "total_phases": 8,
  "phase_title": "Cycle Mechanics \u2014 Typed Thought/Action Step, Verbatim Observations, Duplicate Guard",
  "phase_summary": "Build the three self-contained mechanisms one ReAct cycle is made of, each independently testable before any loop wraps them: the versioned per-cycle prompt with its typed thought-plus-discriminated-action output on the existing PydanticAI lane, the direct in-process Exa call that turns a chosen query into a verbatim observation (including an explicit empty-result observation), and the pure-functi",
  "features": [
    {
      "id": "react_loop_example_app",
      "role": "extended",
      "scope_note": "The single-cycle mechanisms only \u2014 typed ReactStep generation, the observation builder over the shared Exa wrapper, and the duplicate-query guard; the bounded loop, allowance holds, terminal cards, streaming and persistence land in Phase 3."
    }
  ],
  "capabilities": [
    {
      "id": "react_search_loop",
      "role": "introduced",
      "scope_note": "The per-cycle building blocks land here \u2014 the ReactStep typed output, the cycle-1-search-only constraint on the action union, verbatim observation construction and the near-duplicate guard; the bounded iteration, budget reservation, terminal cards and SSE emission land in Phase 3."
    }
  ],
  "tech_stack_spec": {
    "dependencies": [
      "pydantic-ai",
      "pydantic",
      "httpx",
      "sentence-transformers",
      "numpy",
      "tenacity",
      "structlog",
      "sentry-sdk",
      "pytest",
      "ruff",
      "mypy"
    ]
  },
  "verification": "Run `uv run pytest` \u2014 all new tests green, with no network access required (fixtures only) and no model quota spent. Confirm specifically: the ReactStep union rejects malformed actions; the cycle-1 output type cannot express an answer action; one validation re-ask occurs then the terminate result is returned; an empty Exa fixture yields an observation with is_empty set rather than a dropped cycle;"
}
---
# Phase 2: Cycle Mechanics — Typed Thought/Action Step, Verbatim Observations, Duplicate Guard

_Trimmed fixture: frontmatter only; the prose body of the real phase is not reproduced._
