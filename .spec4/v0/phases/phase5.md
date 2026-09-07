---
{
  "phase_number": 5,
  "total_phases": 7,
  "phase_title": "Round Cost — Estimated Round Total With Named Unpriced Calls",
  "phase_summary": "Put the current round's estimated cost on the project view, reusing the existing cost card's labelling rules so the figure is always marked an estimate, token totals match the usage record, and calls that could not be priced are named and excluded rather than folded into the total or shown as zero.",
  "features": [
    {
      "id": "round_cost",
      "role": "introduced",
      "scope_note": ""
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "dash",
      "dash-mantine-components",
      "pytest",
      "ruff",
      "mypy"
    ],
    "configurations": "No new env vars. Reads UsageRecord totals from usage.json under .spec4/v{N}/ via src/spec4/project_manager.py's existing usage rollups; Round and WorkingDirectory come from the session dcc.Store via callback State. Layout reuses helpers in src/spec4/layouts/_shared.py."
  },
  "instructions": [
    "Open .spec4/v0/design/mock.html and match the round-cost surface's placement and typography; the manifest's UsageRecord entity (round, calls, tokensIn, tokensOut, costUsd, unpriced, priceSource) is the shape the figure is computed from.",
    "Read src/spec4/layouts/_shared.py's existing cost_summary_card helper and reuse it rather than writing a second cost renderer. If the project view needs a different frame, pass the same computed record into the shared helper — do not duplicate its labelling logic.",
    "Read the round's usage totals through src/spec4/project_manager.py's existing usage.json rollup; do not re-aggregate usage.json independently.",
    "Compute the total from priced calls only, and collect the unpriced calls as a named list. Rendering must follow the specification's Outputs and success criteria above exactly: the estimate label, the token counts, and the named excluded calls.",
    "Distinguish 'no activity this round' from 'activity whose price is unknown' as two separate render paths with different text, so an unknown cost can never present as an all-zero figure. Add a D-XX comment at the branch recording why the two cases must not be conflated.",
    "Render all figures — cost, token counts, call counts — in the monospace font, consistent with the status bar and the round tree.",
    "Place the cost figure on the project view where the mock shows it, with a NEW component id. Do not move, re-id, or re-order the chat frame's existing cost card: tests/test_cost_summary.py asserts it sits between the transcript and the token count, and that ordering must keep passing.",
    "Write the callback so the figure recomputes from usage.json whenever the project view loads and whenever the round's usage record changes; do not cache the computed total.",
    "Add pytest cases in the style of tests/test_cost_summary.py asserting: the rendered output always contains the estimate label; token totals equal the fixture's usage record; a fixture containing unpriced calls renders each of their names and excludes them from the total; and a fixture whose calls are all unpriced never renders an all-zero cost figure.",
    "Add a pytest case for the empty case — a round with no recorded calls — asserting it renders the no-activity text and not the unknown-price text.",
    "Extend tests/test_callback_co_presence.py with the new project-view cost id, and confirm tests/test_cost_summary.py's existing ordering assertions still pass untouched."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "The tempting implementation sums every call and treats an unpriceable one as zero, which silently understates cost and satisfies a naive test. Adding a cost component to the project view risks disturbing the chat frame's cost card ordering contract. Reimplementing the rollup instead of reusing project_manager's produces two aggregation paths that drift.",
    "mitigation_strategy": "Make unpriced calls a first-class field on the computed record — never a zero-valued price — and add the dedicated all-unpriced test that fails if the figure renders as zero. Give the project-view cost a new id in a separate subtree from the chat frame and run tests/test_cost_summary.py after the change. Route all aggregation through project_manager's existing rollup and reuse _shared.py's cost helper for labelling."
  },
  "verification": "`uv run pytest` passes with the new round-cost cases (estimate label always present, token totals match the fixture, unpriced calls named and excluded, all-unpriced never renders zero, empty round renders no-activity text) and with tests/test_cost_summary.py's existing ordering assertions unchanged. `uv run ruff check src/ tests/` is clean. The project view shows a line of the form \"Estimated cost, v0: $0.7312 · 2 of 19 calls could not be priced and are excluded\" in monospace, and never \"$0.0000\" for an unknown cost. Manual check: placement matches .spec4/v0/design/mock.html. Goal verified here: nfr_status_information__round__artifact_state__cost__always_reflects_the_true_current_state_of_the_working_directory__never_a_stale_cached_view (the figure is recomputed from usage.json on every render, never cached).",
  "references": [
    {
      "standard": "Dash Mantine Components",
      "url": "https://www.dash-mantine-components.com/"
    },
    {
      "standard": "Dash — Advanced Callbacks",
      "url": "https://dash.plotly.com/advanced-callbacks"
    },
    {
      "standard": "Spec4 design mock (unique to this project)",
      "url": ".spec4/v0/design/mock.html"
    },
    {
      "standard": "Spec4 design manifest (unique to this project)",
      "url": ".spec4/v0/design/manifest.json"
    }
  ]
}
---

# Phase 5 of 7: Round Cost — Estimated Round Total With Named Unpriced Calls

Put the current round's estimated cost on the project view, reusing the existing cost card's labelling rules so the figure is always marked an estimate, token totals match the usage record, and calls that could not be priced are named and excluded rather than folded into the total or shown as zero.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Round Cost — product feature — introduced in this phase

Gives the user a trustworthy running estimate of what the current round has cost so far, being explicit about what could and could not be priced.

**Invocation**

- Trigger: The project view loads or the round's usage record changes

**Inputs**

- `usage_totals` (structured data, required) — Aggregated token and cost totals for the current round, including any calls that could not be priced

**Outputs**

- Primary: An estimated cost figure for the round, with token counts and any unpriced calls named
- Format: labelled figure with supporting detail
- Schema notes: Figure is always labelled as an estimate; unpriced calls are named and excluded from the total rather than folded into it

**Success criteria**

- The displayed figure is always labelled as an estimate
- Token totals shown match the underlying usage record
- Any call that could not be priced is named explicitly and excluded from the total rather than silently ignored or shown as zero
- The figure never displays as an all-zero cost when the true cost is unknown

**Failure modes**

- An unpriced call is silently included in the total, understating cost (likelihood: medium) — mitigation: Exclude unpriced calls from the total and list them by name separately
- Cost shows as zero for a round with actual unpriced activity (likelihood: medium) — mitigation: Distinguish 'no activity' from 'activity with unknown price' and never conflate the two

- depends on: development_tool_shell (build these no later than `round_cost`)
- entities: UsageRecord, Round

### UI surfaces for this phase (from the design)

- **`round-cost`** [non_ai]
  - screens: project-view
  - output: Three lines: estimated cost and tokens; unpriced calls named with models and excluded; dimmed price-source disclaimer
  - states: idle, unknown-cost, no-calls
  - reads: UsageRecord, Round
  - after (advisory UI ordering): status-bar

## Tech Stack

**Dependencies:**

- dash
- dash-mantine-components
- pytest
- ruff
- mypy

**Configurations:** No new env vars. Reads UsageRecord totals from usage.json under .spec4/v{N}/ via src/spec4/project_manager.py's existing usage rollups; Round and WorkingDirectory come from the session dcc.Store via callback State. Layout reuses helpers in src/spec4/layouts/_shared.py.

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- usage_records (persistence): per-round usage/cost rollup; deliberately excluded from the artifact dependency graph and never marked needs-update — serves `round_cost`

**Project-wide stack** (applies to every phase):

- Dash
- Dash Mantine Components
- dash-iconify
- litellm
- mcp
- boto3
- httpx
- jsonschema
- gunicorn
- pyyaml
- mypy
- types-pyyaml
- pytest
- pytest-cov
- Playwright
- Ruff

## Instructions

1. Open .spec4/v0/design/mock.html and match the round-cost surface's placement and typography; the manifest's UsageRecord entity (round, calls, tokensIn, tokensOut, costUsd, unpriced, priceSource) is the shape the figure is computed from.
2. Read src/spec4/layouts/_shared.py's existing cost_summary_card helper and reuse it rather than writing a second cost renderer. If the project view needs a different frame, pass the same computed record into the shared helper — do not duplicate its labelling logic.
3. Read the round's usage totals through src/spec4/project_manager.py's existing usage.json rollup; do not re-aggregate usage.json independently.
4. Compute the total from priced calls only, and collect the unpriced calls as a named list. Rendering must follow the specification's Outputs and success criteria above exactly: the estimate label, the token counts, and the named excluded calls.
5. Distinguish 'no activity this round' from 'activity whose price is unknown' as two separate render paths with different text, so an unknown cost can never present as an all-zero figure. Add a D-XX comment at the branch recording why the two cases must not be conflated.
6. Render all figures — cost, token counts, call counts — in the monospace font, consistent with the status bar and the round tree.
7. Place the cost figure on the project view where the mock shows it, with a NEW component id. Do not move, re-id, or re-order the chat frame's existing cost card: tests/test_cost_summary.py asserts it sits between the transcript and the token count, and that ordering must keep passing.
8. Write the callback so the figure recomputes from usage.json whenever the project view loads and whenever the round's usage record changes; do not cache the computed total.
9. Add pytest cases in the style of tests/test_cost_summary.py asserting: the rendered output always contains the estimate label; token totals equal the fixture's usage record; a fixture containing unpriced calls renders each of their names and excludes them from the total; and a fixture whose calls are all unpriced never renders an all-zero cost figure.
10. Add a pytest case for the empty case — a round with no recorded calls — asserting it renders the no-activity text and not the unknown-price text.
11. Extend tests/test_callback_co_presence.py with the new project-view cost id, and confirm tests/test_cost_summary.py's existing ordering assertions still pass untouched.

## Risk Assessment

**Potential bottlenecks:**

The tempting implementation sums every call and treats an unpriceable one as zero, which silently understates cost and satisfies a naive test. Adding a cost component to the project view risks disturbing the chat frame's cost card ordering contract. Reimplementing the rollup instead of reusing project_manager's produces two aggregation paths that drift.

**Mitigation strategy:**

Make unpriced calls a first-class field on the computed record — never a zero-valued price — and add the dedicated all-unpriced test that fails if the figure renders as zero. Give the project-view cost a new id in a separate subtree from the chat frame and run tests/test_cost_summary.py after the change. Route all aggregation through project_manager's existing rollup and reuse _shared.py's cost helper for labelling.

## Verification

`uv run pytest` passes with the new round-cost cases (estimate label always present, token totals match the fixture, unpriced calls named and excluded, all-unpriced never renders zero, empty round renders no-activity text) and with tests/test_cost_summary.py's existing ordering assertions unchanged. `uv run ruff check src/ tests/` is clean. The project view shows a line of the form "Estimated cost, v0: $0.7312 · 2 of 19 calls could not be priced and are excluded" in monospace, and never "$0.0000" for an unknown cost. Manual check: placement matches .spec4/v0/design/mock.html. Goal verified here: nfr_status_information__round__artifact_state__cost__always_reflects_the_true_current_state_of_the_working_directory__never_a_stale_cached_view (the figure is recomputed from usage.json on every render, never cached).

## References

- [Dash Mantine Components](https://www.dash-mantine-components.com/)
- [Dash — Advanced Callbacks](https://dash.plotly.com/advanced-callbacks)
- [Spec4 design mock (unique to this project)](.spec4/v0/design/mock.html)
- [Spec4 design manifest (unique to this project)](.spec4/v0/design/manifest.json)
