---
{
  "phase_number": 5,
  "total_phases": 8,
  "phase_title": "Free-Form Questions \u2014 Shared Moderation Gate and the Suitability Advisory",
  "phase_summary": "Open the ReAct Loop to the visitor's own questions safely and honestly: route free-form input through the framework's existing shared moderation service, then add a typed suitability advisory that tells the visitor up front whether their question will actually exercise the loop \u2014 an advisory that never blocks Start, never touches the two-run allowance, and fails open to a neutral state.",
  "features": [
    {
      "id": "react_loop_example_app",
      "role": "extended",
      "scope_note": "The free-form question path lands here \u2014 the moderation gate, the suitability advisory and its UI states; preset questions bypass both, and the hop-annotation panel and overview copy land in Phases 6 and 7."
    }
  ],
  "capabilities": [
    {
      "id": "react_question_suitability_check",
      "role": "introduced",
      "scope_note": "Implemented in full in this phase \u2014 the typed verdict, the debounce and cache, the session check cap, the fail-open neutral state and the advisory UI."
    },
    {
      "id": "react_search_loop",
      "role": "extended",
      "scope_note": "Extended only to accept a moderated free-form question as a run input and to persist the suitability verdict onto the run record; the loop itself is unchanged from Phase 3."
    }
  ],
  "tech_stack_spec": {
    "dependencies": [
      "pydantic-ai",
      "pydantic",
      "httpx",
      "tenacity",
      "sqlalchemy",
      "structlog",
      "sentry-sdk",
      "pytest",
      "react",
      "@tanstack/react-query",
      "tailwindcss",
      "vitest",
      "@testing-library/react"
    ]
  },
  "verification": "Run `uv run pytest` \u2014 all green, including: presets spend zero moderation and zero suitability calls; a refused moderation verdict prevents any downstream call; each invariant breach is rejected by a validator; one repair retry then unknown; a simulated timeout yields unknown with the run allowance untouched; the cache prevents a repeat call; the session check cap holds; and an injected instructio"
}
---
# Phase 5: Free-Form Questions — Shared Moderation Gate and the Suitability Advisory

_Trimmed fixture: frontmatter only; the prose body of the real phase is not reproduced._
