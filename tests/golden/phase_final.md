---
{
  "phase_number": 2,
  "total_phases": 2,
  "phase_title": "Polish & offline",
  "phase_summary": "Ship the UI and the offline path.",
  "features": [
    {
      "id": "thread_summarization",
      "role": "extended",
      "scope_note": ""
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [],
    "configurations": ""
  },
  "instructions": [
    "Add the history panel."
  ],
  "risk_assessment": {},
  "verification": "Run the e2e suite.",
  "references": []
}
---

# Phase 2 of 2: Polish & offline

Ship the UI and the offline path.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Thread Summarization — product feature — extended in this phase

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

## Tech Stack

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- React Hook Form (libraries): Form state — serves `thread_summarization`

**Project-wide stack** (applies to every phase):

- FastAPI
- vite-plugin-pwa

## Instructions

1. Add the history panel.

## Risk Assessment

## Verification

Run the e2e suite.

**Non-functional acceptance** (deterministic, from the stack spec):

- `nfr_works_offline_`: Works offline. — project-wide acceptance
