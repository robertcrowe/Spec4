---
{
  "phase_number": 5,
  "total_phases": 6,
  "phase_title": "Behaviour-Preservation Acceptance on the Staging Origin",
  "phase_summary": "Verify through the Caddy edge at bwtemp.spec4.ai that all ten example apps, all four server-sent-event streams, every usage cap and every visitor-facing message behave exactly as they do on Render \u2014 producing a written, per-app acceptance checklist. This is the gate that must pass before any DNS is touched, and it is deliberately manual observation plus the existing test suites, because the stack ",
  "features": [
    {
      "id": "self_hosted_deployment",
      "role": "extended",
      "scope_note": "Establishes the behaviour-preserving acceptance evidence on the validation origin; the canonical bw.spec4.ai cutover and retirement of earlier addresses is Phase 6."
    },
    {
      "id": "shared_framework_services",
      "role": "extended",
      "scope_note": "Confirms every shared capability \u2014 generation, embedding, web search, moderation, storage, usage limiting \u2014 behaves identically under the new host with the warm embedding model answering the first request as fast as later ones; no service behaviour is changed."
    },
    {
      "id": "landing_page",
      "role": "extended",
      "scope_note": "Confirms the landing roster and header navigation list every example app exactly once and every entry routes correctly through the new edge; no landing-page content is changed."
    },
    {
      "id": "rag_example_app",
      "role": "introduced",
      "scope_note": "Verification only of the already-built app through the new edge \u2014 retrieval, grounded answer with citations, and the honest not-covered outcome; no RAG code is written or changed."
    },
    {
      "id": "tool_use_integration",
      "role": "introduced",
      "scope_note": "Verification only that the shared Exa web-search capability returns the verbatim issued query and ranked findings through the new host, and reports unavailability distinctly from an empty result; no code is changed."
    },
    {
      "id": "embeddings_example_app",
      "role": "introduced",
      "scope_note": "Verification only that the map renders immediately on first arrival from the warm boot-time projection and that custom text places deterministically; no embeddings code is changed."
    },
    {
      "id": "single_call_example_app",
      "role": "introduced",
      "scope_note": "Verification only of Simple and Structured modes including the surfaced non-conformance behaviour; no single-call code is changed."
    },
    {
      "id": "chained_calls_example_app",
      "role": "introduced",
      "scope_note": "Verification only that exactly two calls run, the intermediate result stays visible, and a failed second call preserves the first; no chained-calls code is changed."
    },
    {
      "id": "planning_agent_example_app",
      "role": "introduced",
      "scope_note": "Verification only that the plan displays before execution, nothing runs until the visitor advances, per-step results stream progressively through Caddy, and the ReAct cross-reference is present; no planning code is changed."
    },
    {
      "id": "orchestrated_subagents_example_app",
      "role": "introduced",
      "scope_note": "Verification only of the delegation decision, concurrent specialist columns, merged answer, three-call budget and runs-remaining behaviour through the new edge; no orchestration code is changed."
    },
    {
      "id": "multi_agent_collaboration_example_app",
      "role": "introduced",
      "scope_note": "Verification only of the six-stage negotiation streaming per stage, the code-enforced no-seller-to-seller opacity invariant, the reveal and message log; no collaboration code is changed."
    },
    {
      "id": "react_loop_example_app",
      "role": "introduced",
      "scope_note": "Verification only that the cycle trace fills progressively with an advancing counter, both terminal card kinds remain possible, and the two-run session limit holds; no ReAct code is changed."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "pytest",
      "Ruff",
      "mypy",
      "Vitest",
      "React Testing Library",
      "Caddy 2",
      "uvicorn",
      "sse-starlette",
      "@microsoft/fetch-event-source"
    ]
  },
  "verification": "deploy/ACCEPTANCE.md exists with a PASS verdict for every section and no open FAIL. Specifically: (1) `uv run pytest`, `uv run ruff check .`, `uv run mypy backend` and `npm run test` match the Phase 1 baseline, with the deselected-live-tests and path-exemption caveats recorded. (2) The landing roster and header navigation each list every existing example app exactly once with no dead entry, every "
}
---
# Phase 5: Behaviour-Preservation Acceptance on the Staging Origin

_Trimmed fixture: frontmatter only; the prose body of the real phase is not reproduced._
