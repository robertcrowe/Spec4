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

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Thread Summarization — product feature — introduced in this phase

*Scope for this phase: API only; UI polish lands in phase 2.*

Users get a summary of a pasted thread.

**Success criteria**

- Summary matches thread

- depends on: auth (build these no later than `thread_summarization`)
- entities: EmailThread, Summary

### UI surfaces for this phase (from the design)

- **`history_panel`** [non_ai]
  - screens: main
The following surface(s) realize the AI capability `thread_summarization` — one unit of work; the surfaces are views onto it:
- **`summary_view`** [ai]
  - screens: main
  - inputs: raw_thread
  - reads: EmailThread
  - writes: Summary

### Thread Summarization — AI capability — introduced in this phase

Serves product feature(s): `thread_summarization` (specified above).

Summarize threads with AI.

**Inputs**


**Success criteria**

- summary matches thread

**Failure modes**


**Cross-cutting decisions (project-wide):**

- **Evaluation:** Keep a golden set.
- **Observability:** Trace every call.

## Tech Stack

**Dependencies:**

- fastapi
- litellm

**Configurations:** PORT, OPENAI_API_KEY

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- litellm (libraries): LLM calls — serves `thread_summarization`
- React Hook Form (libraries): Form state — serves `thread_summarization`

**Project-wide stack** (applies to every phase):

- FastAPI
- vite-plugin-pwa

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

**Non-functional acceptance** (deterministic, from the stack spec):

- `nfr_summaries_are_fast_`: Summaries are fast. — delivered by litellm


## References

- [RFC 5322](https://www.rfc-editor.org/rfc/rfc5322)
- House style
