---
{
  "phase_number": 1,
  "total_phases": 2,
  "phase_title": "Thread summaries",
  "phase_summary": "Build the summary path end to end.",
  "features": [
    {
      "id": "thread_summarization",
      "role": "introduced",
      "scope_note": "API only; UI polish lands in phase 2."
    },
    {
      "id": "unknown_product_id",
      "role": "extended"
    }
  ],
  "capabilities": [
    {
      "id": "thread_summarization",
      "role": "introduced"
    },
    {
      "id": "unknown_capability_id"
    }
  ],
  "tech_stack_spec": {
    "dependencies": [
      "fastapi",
      "litellm"
    ],
    "configurations": "PORT, OPENAI_API_KEY"
  },
  "instructions": [
    "Add the summarise endpoint.",
    "Persist the summary.",
    "Wire the view."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "Long threads exceed the context window.",
    "mitigation_strategy": "Chunk and merge."
  },
  "verification": "Run pytest; POST a thread and read the summary back.",
  "references": [
    {
      "standard": "RFC 5322",
      "url": "https://www.rfc-editor.org/rfc/rfc5322"
    },
    {
      "standard": "House style"
    },
    {
      "url": "https://example.com/no-standard"
    }
  ]
}
---

# Phase 1 of 2: Thread summaries

Build the summary path end to end.

## Tech Stack

**Dependencies:**

- fastapi
- litellm

**Configurations:** PORT, OPENAI_API_KEY

## Instructions

1. Add the summarise endpoint.
2. Persist the summary.
3. Wire the view.

## Risk Assessment

**Potential bottlenecks:**

Long threads exceed the context window.

**Mitigation strategy:**

Chunk and merge.

## Verification

Run pytest; POST a thread and read the summary back.

## References

- [RFC 5322](https://www.rfc-editor.org/rfc/rfc5322)
- House style
