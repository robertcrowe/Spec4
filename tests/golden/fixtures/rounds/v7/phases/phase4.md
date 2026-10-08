---
{
  "phase_number": 4,
  "total_phases": 8,
  "phase_title": "The ReAct Screen \u2014 Live Trace, Cycle Counter, Runs-Remaining and Exhausted State",
  "phase_summary": "Build the visitor-facing ReAct Loop screen against the finalized mock: a preset selector and a start control that shows no plan and asks for no mid-run approval, a trace that fills cycle by cycle as the SSE envelopes arrive, a live 'search N of 8' counter, two visually distinct terminal cards, and the two-run session allowance whose exhausted state disables input while leaving every previous trace",
  "features": [
    {
      "id": "react_loop_example_app",
      "role": "extended",
      "scope_note": "The preset-driven UI lands here \u2014 trace stream, cycle counter, terminal cards, runs-remaining and the exhausted state; the free-form question input's moderation and suitability advisory land in Phase 5, the hop-annotation panel in Phase 6, and the educational overview copy in Phase 7."
    }
  ],
  "capabilities": [
    {
      "id": "react_search_loop",
      "role": "extended",
      "scope_note": "The client-side realization of the loop \u2014 consuming the per-cycle SSE envelopes, rendering thought/action/observation in arrival order, and the two-run per-visit allowance; the backend loop was completed in Phase 3."
    }
  ],
  "tech_stack_spec": {
    "dependencies": [
      "react",
      "react-router",
      "@tanstack/react-query",
      "@microsoft/fetch-event-source",
      "react-markdown",
      "tailwindcss",
      "typescript",
      "vite",
      "vitest",
      "@testing-library/react",
      "@sentry/react"
    ]
  },
  "verification": "Run `npm --prefix frontend run test` \u2014 all new Vitest suites green, including the assertion that the DOM grows between individually-delivered envelopes (proving no buffering), that the counter advances, that the two terminal cards are distinguishable, and that exhausting the allowance disables input while leaving prior traces on screen. Run `npm --prefix frontend run lint` and `npm --prefix fronte"
}
---
# Phase 4: The ReAct Screen — Live Trace, Cycle Counter, Runs-Remaining and Exhausted State

_Trimmed fixture: frontmatter only; the prose body of the real phase is not reproduced._
