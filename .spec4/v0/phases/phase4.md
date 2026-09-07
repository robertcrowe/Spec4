---
{
  "phase_number": 4,
  "total_phases": 7,
  "phase_title": "Agent Rows — Seven Compact Pipeline Rows With Existing Action Semantics",
  "phase_summary": "Replace the marketing-style agent cards with seven dense rows in fixed pipeline order, each showing the agent's name, produced artifact, last-run model, tokens in and out for this round, and an action button whose state, variant, and routing come from the existing agent state model unchanged.",
  "features": [
    {
      "id": "agent_rows",
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
    "configurations": "No new env vars. Reads UsageRecord data from usage.json under .spec4/v{N}/ and Agent readiness from src/spec4/project_manager.py; WorkingDirectory and Round come from the existing session dcc.Store via callback State. Row layout in src/spec4/layouts/, callbacks in src/spec4/callbacks/, row density styling in src/spec4/assets/v3.css."
  },
  "instructions": [
    "Open .spec4/v0/design/mock.html and .spec4/v0/design/manifest.json; the manifest's AgentRow entity (agent, produces, model, tokens, action, disabled) is the shape each row carries. Where the mock and the manifest differ in coverage, the manifest is the source — the mock shows no Start or Required row.",
    "Render exactly seven rows, iterating spec4.app_constants.AGENT_KEYS directly so pipeline order cannot drift; do not hand-list the agents.",
    "For each row render, in the order the mock shows: agent name, the artifact it produces (monospace), the model it last ran on this round (monospace), tokens in, tokens out, and the action button.",
    "Read the last-run model from usage.json's per-agent models list for the current round. When usage.json has no entry for an agent, treat that agent as not-yet-run and render the model and token fields blank — never raise, and never render a zero or an error string in place of a missing entry.",
    "Derive each row's action directly from the existing agent readiness state via src/spec4/project_manager.py's agent_button_state. Do not re-derive readiness, and do not add a second state model.",
    "Render the action button variants exactly as the design manifest specifies: Start is a filled green button; Required is a filled green button; Modify is a neutral outline with green text; Needs Update is a warn outline; Not Ready is a disabled outline. Green here means the theme primary set in Phase 2 — set the variant, not a local colour value.",
    "Wire each row's action to the existing agent-select routing so activating it navigates to that agent exactly as the current agent-select buttons do. Reuse the existing callback path rather than writing new routing logic.",
    "Give each row and each action button a NEW component id derived from its AGENT_KEYS key, and keep every existing agent-select component id intact so its callbacks stay co-present.",
    "Remove the previous agent card layout and its card-specific styling from src/spec4/layouts/ and src/spec4/assets/v3.css, including the step numbers and per-agent description text.",
    "Render no step numbers, no agent descriptions, and no emoji in any row. Do not add any icon component: dash-iconify is not used by anything this round.",
    "Place the agent rows on the project view directly beneath the round tree, matching the mock's row height and spacing.",
    "Add pytest cases that call the agent-rows layout function and assert: exactly seven rows are returned; their order equals AGENT_KEYS; each row exposes the produced-artifact and action elements; and each of the five action states maps to its specified button variant (Start filled, Required filled, Modify outline with green text, Needs Update warn outline, Not Ready disabled outline).",
    "Add a pytest case with a usage.json fixture that omits one agent, asserting that agent's model and token fields render blank and no exception is raised.",
    "Add a pytest case asserting each row's action is exactly what project_manager's agent_button_state returns for that agent, using a fixture that exercises more than one state.",
    "Extend tests/test_callback_co_presence.py with the new row and action-button ids, and remove the retired agent-card ids in the same change."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "Removing agent-card ids breaks any callback still listing them as an Input, and Dash surfaces this only when the callback fires. The five action states with distinct variants invite an ad-hoc mapping written inline in the layout, which will drift from the manifest. A missing usage.json entry is a normal condition that a naive dict lookup turns into a KeyError, taking down the whole project view.",
    "mitigation_strategy": "Delete retired card callbacks alongside the card layout and update tests/test_callback_co_presence.py in the same change, then run `uv run pytest` immediately. Put the action-state-to-variant mapping in one module-level constant with a D-XX comment citing the design manifest, and assert all five entries in a test. Read usage entries through a defensive accessor that returns a not-yet-run record for any absent agent, and cover it with the omitted-agent fixture test."
  },
  "verification": "`uv run pytest` passes with the new agent-row cases: seven rows in AGENT_KEYS order, all five action-state variants correct, missing usage entry renders blank without raising, and each action matches agent_button_state. `uv run ruff check src/ tests/` is clean; tests/test_cost_summary.py and tests/test_agent_llm_selection.py still pass unchanged. On the project view, the seven agents render as compact rows beneath the round tree with no step numbers, descriptions, or emoji, and clicking a row's action navigates to that agent exactly as before. Manual check: rows match .spec4/v0/design/mock.html and the button variants match .spec4/v0/design/manifest.json. Goals verified here: nfr_status_information__round__artifact_state__cost__always_reflects_the_true_current_state_of_the_working_directory__never_a_stale_cached_view (model, tokens, and action are read fresh from usage.json and project_manager on every render) and nfr_the_project_view_remains_fully_usable_without_any_network_access_beyond_explicit_llm_calls (rows read only local files and existing in-process state).",
  "references": [
    {
      "standard": "Dash Mantine Components — Button",
      "url": "https://www.dash-mantine-components.com/components/button"
    },
    {
      "standard": "Dash — Basic Callbacks and State",
      "url": "https://dash.plotly.com/basic-callbacks"
    },
    {
      "standard": "Spec4 design manifest (unique to this project)",
      "url": ".spec4/v0/design/manifest.json"
    },
    {
      "standard": "Spec4 design mock (unique to this project)",
      "url": ".spec4/v0/design/mock.html"
    }
  ]
}
---

# Phase 4 of 7: Agent Rows — Seven Compact Pipeline Rows With Existing Action Semantics

Replace the marketing-style agent cards with seven dense rows in fixed pipeline order, each showing the agent's name, produced artifact, last-run model, tokens in and out for this round, and an action button whose state, variant, and routing come from the existing agent state model unchanged.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Agent Rows — product feature — introduced in this phase

Shows the seven pipeline agents as compact, information-dense rows so the user can see at a glance what each agent produces, what it last ran on, and what to do next.

**Invocation**

- Trigger: The round tree has rendered for the current round

**Inputs**

- `agent_pipeline_order` (list of items, required) — The seven agents in their fixed execution order
- `agent_artifact_mapping` (structured data, required) — Which artifact each agent produces
- `usage_record` (structured data, required) — Per-agent model used and token counts for the current round
- `agent_state` (structured data, required) — The existing readiness state per agent used to choose the row's action

**Outputs**

- Primary: One row per agent showing name, produced artifact, last-run model, tokens in and out, and an action
- Format: ordered list of rows
- Schema notes: Action is one of Start, Modify, Needs Update, Not Ready, Required, following existing semantics; model field is blank when the agent has not yet run this round

**Success criteria**

- All seven agents appear in fixed pipeline order with no step numbers, descriptions, or emoji
- The action shown for each agent matches its existing state exactly
- The model field is blank when an agent has not run this round and shows the correct model otherwise
- Token counts shown match the recorded usage for that agent this round
- Activating a row's action navigates to that agent exactly as the current agent-select buttons do; no routing is re-derived

**Failure modes**

- Usage record lacks an entry for an agent that has run (likelihood: medium) — mitigation: Treat a missing entry as not-yet-run and show blank fields rather than an error
- Action shown does not match the underlying readiness state (likelihood: low) — mitigation: Derive the action directly from the existing state model rather than re-deriving it independently

- depends on: development_tool_shell (build these no later than `agent_rows`)
- entities: Agent, Artifact, UsageRecord

### UI surfaces for this phase (from the design)

- **`agent-rows`** [non_ai]
  - screens: project-view
  - inputs: action button per row: Start (filled green), Required (filled green, same as Start), Modify (neutral outline, green text), Needs Update (warn outline), Not Ready (disabled outline). Activating a button routes to that agent exactly as the current agent-select buttons do
  - output: Seven-row table: Agent · Produces · Last model · Tokens this round · action
  - states: idle, not-run (blank model/tokens), disabled
  - reads: Agent, UsageRecord
  - after (advisory UI ordering): status-bar

## Tech Stack

**Dependencies:**

- dash
- dash-mantine-components
- pytest
- ruff
- mypy

**Configurations:** No new env vars. Reads UsageRecord data from usage.json under .spec4/v{N}/ and Agent readiness from src/spec4/project_manager.py; WorkingDirectory and Round come from the existing session dcc.Store via callback State. Row layout in src/spec4/layouts/, callbacks in src/spec4/callbacks/, row density styling in src/spec4/assets/v3.css.

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- round_artifacts (persistence) — serves `agent_rows`
- usage_records (persistence): per-round usage/cost rollup; deliberately excluded from the artifact dependency graph and never marked needs-update — serves `agent_rows`

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

1. Open .spec4/v0/design/mock.html and .spec4/v0/design/manifest.json; the manifest's AgentRow entity (agent, produces, model, tokens, action, disabled) is the shape each row carries. Where the mock and the manifest differ in coverage, the manifest is the source — the mock shows no Start or Required row.
2. Render exactly seven rows, iterating spec4.app_constants.AGENT_KEYS directly so pipeline order cannot drift; do not hand-list the agents.
3. For each row render, in the order the mock shows: agent name, the artifact it produces (monospace), the model it last ran on this round (monospace), tokens in, tokens out, and the action button.
4. Read the last-run model from usage.json's per-agent models list for the current round. When usage.json has no entry for an agent, treat that agent as not-yet-run and render the model and token fields blank — never raise, and never render a zero or an error string in place of a missing entry.
5. Derive each row's action directly from the existing agent readiness state via src/spec4/project_manager.py's agent_button_state. Do not re-derive readiness, and do not add a second state model.
6. Render the action button variants exactly as the design manifest specifies: Start is a filled green button; Required is a filled green button; Modify is a neutral outline with green text; Needs Update is a warn outline; Not Ready is a disabled outline. Green here means the theme primary set in Phase 2 — set the variant, not a local colour value.
7. Wire each row's action to the existing agent-select routing so activating it navigates to that agent exactly as the current agent-select buttons do. Reuse the existing callback path rather than writing new routing logic.
8. Give each row and each action button a NEW component id derived from its AGENT_KEYS key, and keep every existing agent-select component id intact so its callbacks stay co-present.
9. Remove the previous agent card layout and its card-specific styling from src/spec4/layouts/ and src/spec4/assets/v3.css, including the step numbers and per-agent description text.
10. Render no step numbers, no agent descriptions, and no emoji in any row. Do not add any icon component: dash-iconify is not used by anything this round.
11. Place the agent rows on the project view directly beneath the round tree, matching the mock's row height and spacing.
12. Add pytest cases that call the agent-rows layout function and assert: exactly seven rows are returned; their order equals AGENT_KEYS; each row exposes the produced-artifact and action elements; and each of the five action states maps to its specified button variant (Start filled, Required filled, Modify outline with green text, Needs Update warn outline, Not Ready disabled outline).
13. Add a pytest case with a usage.json fixture that omits one agent, asserting that agent's model and token fields render blank and no exception is raised.
14. Add a pytest case asserting each row's action is exactly what project_manager's agent_button_state returns for that agent, using a fixture that exercises more than one state.
15. Extend tests/test_callback_co_presence.py with the new row and action-button ids, and remove the retired agent-card ids in the same change.

## Risk Assessment

**Potential bottlenecks:**

Removing agent-card ids breaks any callback still listing them as an Input, and Dash surfaces this only when the callback fires. The five action states with distinct variants invite an ad-hoc mapping written inline in the layout, which will drift from the manifest. A missing usage.json entry is a normal condition that a naive dict lookup turns into a KeyError, taking down the whole project view.

**Mitigation strategy:**

Delete retired card callbacks alongside the card layout and update tests/test_callback_co_presence.py in the same change, then run `uv run pytest` immediately. Put the action-state-to-variant mapping in one module-level constant with a D-XX comment citing the design manifest, and assert all five entries in a test. Read usage entries through a defensive accessor that returns a not-yet-run record for any absent agent, and cover it with the omitted-agent fixture test.

## Verification

`uv run pytest` passes with the new agent-row cases: seven rows in AGENT_KEYS order, all five action-state variants correct, missing usage entry renders blank without raising, and each action matches agent_button_state. `uv run ruff check src/ tests/` is clean; tests/test_cost_summary.py and tests/test_agent_llm_selection.py still pass unchanged. On the project view, the seven agents render as compact rows beneath the round tree with no step numbers, descriptions, or emoji, and clicking a row's action navigates to that agent exactly as before. Manual check: rows match .spec4/v0/design/mock.html and the button variants match .spec4/v0/design/manifest.json. Goals verified here: nfr_status_information__round__artifact_state__cost__always_reflects_the_true_current_state_of_the_working_directory__never_a_stale_cached_view (model, tokens, and action are read fresh from usage.json and project_manager on every render) and nfr_the_project_view_remains_fully_usable_without_any_network_access_beyond_explicit_llm_calls (rows read only local files and existing in-process state).

## References

- [Dash Mantine Components — Button](https://www.dash-mantine-components.com/components/button)
- [Dash — Basic Callbacks and State](https://dash.plotly.com/basic-callbacks)
- [Spec4 design manifest (unique to this project)](.spec4/v0/design/manifest.json)
- [Spec4 design mock (unique to this project)](.spec4/v0/design/mock.html)
