---
{
  "phase_number": 6,
  "total_phases": 8,
  "phase_title": "Hop-Source Annotation \u2014 Labelling Where Observation Actually Did the Work",
  "phase_summary": "Add the post-run call that reads the completed trace and labels each hop as grounded in an observation or recalled from the model's own knowledge, with a one-line reason \u2014 plus the deterministic cross-checks that stop the model over-crediting itself, and the backend-derived flag that proves presets one through three reached a fully-observed run. Annotation is decorative: every failure path renders",
  "features": [
    {
      "id": "react_loop_example_app",
      "role": "extended",
      "scope_note": "The hop-annotation panel and its backend call land here, completing the app's functional surface; only the educational overview copy and the cross-gallery consistency pass remain, in Phase 7."
    }
  ],
  "capabilities": [
    {
      "id": "hop_source_annotation",
      "role": "introduced",
      "scope_note": "Implemented in full in this phase \u2014 the post-run typed call, the deterministic downgrade cross-checks, the derived all-hops-observed flag, persistence onto the run record, and the annotation panel."
    },
    {
      "id": "react_search_loop",
      "role": "extended",
      "scope_note": "Extended only to fire the annotation call once a run reaches a terminal state and to redeem the annotation call reserved in Phase 3; the loop itself is unchanged."
    }
  ],
  "tech_stack_spec": {
    "dependencies": [
      "pydantic-ai",
      "pydantic",
      "sqlalchemy",
      "structlog",
      "sentry-sdk",
      "pytest",
      "react",
      "react-markdown",
      "tailwindcss",
      "vitest",
      "@testing-library/react"
    ]
  },
  "verification": "Run `uv run pytest` \u2014 all green, including: an out-of-range cycle index is dropped; an observation claim on a search-free cycle is downgraded to model_knowledge; a supporting cycle later than its hop is downgraded; the all-hops-observed flag is computed in code and true on a fully-grounded fixture; a budget-exhausted fixture is never annotated as resolved; one retry then a clean skip on validation"
}
---
# Phase 6: Hop-Source Annotation — Labelling Where Observation Actually Did the Work

_Trimmed fixture: frontmatter only; the prose body of the real phase is not reproduced._
