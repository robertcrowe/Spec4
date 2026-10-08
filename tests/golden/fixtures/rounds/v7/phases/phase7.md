---
{
  "phase_number": 7,
  "total_phases": 8,
  "phase_title": "Educational Copy and Gallery Consistency \u2014 Including the Planning Agent Cross-Reference",
  "phase_summary": "Make the ReAct Loop teach even when nobody runs it: write the educational overview explaining the loop, how it differs from a single should-I-search decision and from a fixed pre-approved plan, and what a run costs; update the Planning Agent overview to cross-reference ReAct Loop as its interleaved counterpart; and run the shared-layout, responsive and assistive-technology pass so a visitor who un",
  "features": [
    {
      "id": "react_loop_example_app",
      "role": "extended",
      "scope_note": "The educational overview, the quota-disclosure copy and the cross-gallery layout and accessibility pass \u2014 the last of this app's surface; only the test harness and telemetry remain, in Phase 8."
    },
    {
      "id": "planning_agent_example_app",
      "role": "extended",
      "scope_note": "Copy-only change: the existing Planning Agent overview gains a cross-reference to ReAct Loop as the interleaved counterpart to its plan-first approach; no planning-agent behaviour, route, schema or model call is altered."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "react",
      "react-router",
      "react-markdown",
      "tailwindcss",
      "typescript",
      "vitest",
      "@testing-library/react"
    ]
  },
  "verification": "Run `npm --prefix frontend run test` \u2014 the full frontend suite green, including the new assertions that the ReAct overview contains the loop explanation, the Tool Use contrast, the Planning Agent contrast, the presets 4\u20135 note and the quota disclosure; that the quota rationale appears next to the run control; that the Planning Agent overview links to the ReAct Loop route; and that every pre-existi"
}
---
# Phase 7: Educational Copy and Gallery Consistency — Including the Planning Agent Cross-Reference

_Trimmed fixture: frontmatter only; the prose body of the real phase is not reproduced._
