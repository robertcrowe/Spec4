---
{
  "phase_number": 3,
  "total_phases": 8,
  "phase_title": "The Bounded Loop \u2014 Allowance Holds, Terminal Cards, and Live SSE",
  "phase_summary": "Assemble Phase 2's mechanisms into the hand-rolled bounded reason-act-observe loop that is the exhibit itself: reserve the run's full worst-case call budget before the first cycle, iterate up to 8 search cycles with the cycle counter as a code invariant, terminate in exactly one of two candid endings, refund the unspent remainder on an early answer, persist the run record, and stream every cycle b",
  "features": [
    {
      "id": "react_loop_example_app",
      "role": "extended",
      "scope_note": "The backend run is completed here \u2014 bounded iteration, the 10-call reservation and refund, the two terminal cards, react_runs persistence and the real per-cycle SSE stream replacing Phase 1's stub; the UI, the free-form question path and the hop annotations land in Phases 4, 5 and 6."
    }
  ],
  "capabilities": [
    {
      "id": "react_search_loop",
      "role": "extended",
      "scope_note": "The loop itself lands here \u2014 iteration, the fixed 8-search ceiling, allowance reservation and refund, terminal-card selection, run persistence and SSE emission; the free-form question gate is added in Phase 5 and the post-run annotation in Phase 6."
    }
  ],
  "tech_stack_spec": {
    "dependencies": [
      "fastapi",
      "sse-starlette",
      "pydantic-ai",
      "pydantic",
      "sqlalchemy",
      "asyncpg",
      "httpx",
      "sentence-transformers",
      "numpy",
      "structlog",
      "sentry-sdk",
      "pytest"
    ]
  },
  "verification": "Run `uv run pytest` \u2014 all green, with the loop tests running entirely on recorded fixtures and a stubbed model lane so no quota is spent. Confirm specifically: no run exceeds 8 searches; cycle 1 is always a search; exactly one terminal envelope per run; budget-exhausted runs carry no answer field; an early answer refunds the unspent calls; a refused reservation issues zero model and zero Exa calls"
}
---
# Phase 3: The Bounded Loop — Allowance Holds, Terminal Cards, and Live SSE

_Trimmed fixture: frontmatter only; the prose body of the real phase is not reproduced._
