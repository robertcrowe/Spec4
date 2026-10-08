---
{
  "phase_number": 8,
  "total_phases": 8,
  "phase_title": "Golden Harness, Telemetry and Hardening",
  "phase_summary": "Close the revision with the evidence that the three new capabilities behave as claimed: a fixture-backed golden test suite asserting the loop's structural invariants, labelled sets for the suitability verdict and the hop annotations, per-run and per-cycle telemetry so the ending distribution and budget consumption are watchable in production, and explicit registration of every new file in the lint",
  "features": [
    {
      "id": "react_loop_example_app",
      "role": "extended",
      "scope_note": "Verification and observability only \u2014 the golden harness, labelled evaluation sets, telemetry and gate registration; no new visitor-facing behaviour is added in this phase."
    }
  ],
  "capabilities": [
    {
      "id": "react_search_loop",
      "role": "extended",
      "scope_note": "Extended with its offline golden harness and its per-run online metrics; no change to loop behaviour."
    },
    {
      "id": "react_question_suitability_check",
      "role": "extended",
      "scope_note": "Extended with its labelled golden set, accuracy assertions and per-check telemetry; no change to the check's behaviour."
    },
    {
      "id": "hop_source_annotation",
      "role": "extended",
      "scope_note": "Extended with its labelled fixture-trace set, agreement assertions and annotation telemetry; no change to the annotation's behaviour."
    }
  ],
  "tech_stack_spec": {
    "dependencies": [
      "pytest",
      "structlog",
      "sentry-sdk",
      "ruff",
      "mypy",
      "vitest",
      "@testing-library/react"
    ]
  },
  "verification": "Run `uv run pytest` with no network access available \u2014 the full suite green, deterministic, spending zero model and zero Exa quota, and covering: every loop structural invariant listed above; the full allowance reserve/redeem/refund lifecycle including the disconnect and refused-reservation paths; every adversarial free-form case ending in its labelled ending; the preset catalog storing no answers"
}
---
# Phase 8: Golden Harness, Telemetry and Hardening

_Trimmed fixture: frontmatter only; the prose body of the real phase is not reproduced._
