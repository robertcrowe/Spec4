---
{
  "phase_number": 2,
  "total_phases": 7,
  "phase_title": "Project View Reorder — Agent Rows, Round Cost, Round Tree",
  "phase_summary": "Reorder the project view so its controls lead its record: agent rows first, round cost second, round tree third. The three surfaces themselves are already built and keep their existing rendering, ids, and status computation; only their order within _agent_select_layout changes, together with the tests that assert project-view ordering.",
  "features": [
    {
      "id": "agent_rows",
      "role": "introduced",
      "scope_note": "This phase only moves agent rows to first position in the project view; the last-model column's effort suffix lands in Phase 6."
    },
    {
      "id": "round_cost",
      "role": "introduced",
      "scope_note": "This phase only moves the round cost strip to second position in the project view; its labelling and unpriced-call rules are already built and unchanged."
    },
    {
      "id": "round_tree",
      "role": "introduced",
      "scope_note": "This phase only moves the round tree to third position in the project view; its lanes, status computation, and line-opens-Artifact-View behaviour are already built and unchanged."
    },
    {
      "id": "artifact_links",
      "role": "introduced",
      "scope_note": "This phase only re-verifies that every round-tree line still opens the Artifact View at that file after the reorder; the links themselves are already built and unchanged."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "dash",
      "dash-mantine-components",
      "pytest"
    ],
    "configurations": "No new configuration. Reads the existing artifact store (.spec4/v{N}/ files) and usage.json through src/spec4/project_manager.py; usage.json stays out of the dependency graph and is never marked needs-update."
  },
  "instructions": [
    "In src/spec4/layouts/__init__.py, locate `_agent_select_layout` and reorder the three project-view children so the agent rows render first, the round cost strip second, and the round tree (with its lane legend) third.",
    "Change only the order of composition. Do not modify the agent-row renderer in src/spec4/layouts/_agent_rows.py, the cost strip in src/spec4/layouts/_round_cost.py, or the tree in src/spec4/layouts/_round_tree.py — their internals, component ids, and status logic are already built and are a test contract.",
    "Confirm each of the three surfaces still recomputes its state from disk on every render — artifact presence/staleness from project_manager's dependency graph, agent action state from agent_button_state, cost and token totals from usage.json — and that nothing is cached across the reorder.",
    "Record the reorder as a numbered design-decision comment (D-XX) at `_agent_select_layout`, stating that controls (agent rows) precede the record (round tree) with the round cost between them.",
    "Adjust vertical spacing between the three blocks in src/spec4/assets/v3.css so the reordered stack reads at the same tight density as the rest of the shell — no new decorative separators, no card hover effects, no motion.",
    "Inspect tests/test_agent_rows.py and tests/test_round_tree.py for any assertion about the relative position of these surfaces within the project view and update those assertions to the new order.",
    "Do NOT change tests/test_cost_summary.py's ordering assertions: they pin the cost strip's position relative to the transcript on the CHAT FRAME, not on the project view. Read them first to confirm this before touching anything, and leave them as they are.",
    "Add or extend a project-view test that asserts the three surfaces appear in the exact order agent rows, round cost, round tree within `_agent_select_layout`'s rendered children, so a future reorder cannot pass silently.",
    "Add a test asserting the agent rows still render the seven agents in the order given by `spec4.app_constants.AGENT_KEYS`, and that the round tree still renders its artifacts in pipeline order, after the reorder.",
    "Verify manually that clicking any round-tree line still opens the Artifact View at that exact file and round, and that the round-cost strip still shows its estimate label, token totals, and any named unpriced calls.",
    "Reference .spec4/v2/design/mock.html's project-view screen for the intended vertical rhythm of the reordered blocks and the lane legend's placement under the tree."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "The most likely failure is collateral test damage: an AI coder searching for 'cost strip ordering' will find test_cost_summary.py and 'fix' its chat-frame assertions to match the project view, breaking a screen this phase does not touch. A second risk is that moving a block also moves the callbacks' Input/Output components out of a rendered layout, tripping test_callback_co_presence.py.",
    "mitigation_strategy": "Explicitly scope test edits to tests/test_agent_rows.py and tests/test_round_tree.py; open tests/test_cost_summary.py to confirm its assertions are chat-frame-scoped and leave it untouched. Because this is a reorder and not a removal, every component id remains present in the layout — run `uv run pytest` immediately after the reorder and before any CSS work, so a co-presence failure is attributable to the reorder alone."
  },
  "verification": "`uv run pytest` passes, including the new project-view ordering test and the updated assertions in tests/test_agent_rows.py and tests/test_round_tree.py, with tests/test_cost_summary.py unmodified and still passing. Run `uv run python src/spec4/app.py` and open http://localhost:8050 on a project with a working directory: the project view shows agent rows first, then the round cost strip, then the round tree with its lane legend. The cost line is labelled as an estimate, shows token totals, and never displays a zero for an unknown cost (nfr_cost_and_token_figures_stay_accurate_and_reflect_the_latest_completed_run__never_showing_an_unknown_cost_as_zero). Clicking a tree line opens the Artifact View at that file.",
  "references": [
    {
      "standard": "Dash",
      "url": "https://dash.plotly.com/"
    },
    {
      "standard": "Dash Mantine Components",
      "url": "https://www.dash-mantine-components.com"
    },
    {
      "standard": "pytest",
      "url": "https://docs.pytest.org/"
    }
  ]
}
---

# Phase 2 of 7: Project View Reorder — Agent Rows, Round Cost, Round Tree

Reorder the project view so its controls lead its record: agent rows first, round cost second, round tree third. The three surfaces themselves are already built and keep their existing rendering, ids, and status computation; only their order within _agent_select_layout changes, together with the tests that assert project-view ordering.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Agent Rows — product feature — introduced in this phase

*Scope for this phase: This phase only moves agent rows to first position in the project view; the last-model column's effort suffix lands in Phase 6.*

Lists the seven planning agents in pipeline order as compact rows, each showing its produced artifact, the model it last used, this round's token counts, and the single next action available.

**Invocation**

- Trigger: The project view is opened, or an agent's run state changes.

**Inputs**

- `agent_pipeline_order` (list of items, required) — The fixed sequence of the seven agents.
- `per_agent_last_model` (text per agent, required) — The model each agent last ran with this round, blank if not yet run.
- `per_agent_tokens_in_out` (number pair per agent, required) — Tokens consumed and produced this round for each agent.
- `per_agent_run_state` (text, required) — The agent's current state used to decide which action to show.

**Outputs**

- Primary: Seven compact rows, one per agent.
- Format: One row per agent, fixed pipeline order.
- Schema notes: Each row has agent name, artifact name, last-run model, tokens in/out, and one action.

**Success criteria**

- Rows appear in fixed pipeline order with no numbering
- The shown action always matches the agent's real state
- A model name only appears once that agent has actually run this round
- Choosing the action routes to the correct next screen for that agent

**Failure modes**

- Shown action does not match actual state after a run completes (likelihood: medium) — mitigation: Recompute state from the same usage record and dependency graph the round tree uses
- Token counts fail to update after a run (likelihood: low) — mitigation: Refresh counts from the same record the round cost reads

- entities: Agent, Artifact, Model, TokenCount, RunState

### Round Cost — product feature — introduced in this phase

*Scope for this phase: This phase only moves the round cost strip to second position in the project view; its labelling and unpriced-call rules are already built and unchanged.*

Gives an at-a-glance estimate of how much the current round has spent so far, based on recorded token usage.

**Invocation**

- Trigger: The project view is opened, or the round's usage record changes.

**Inputs**

- `round_usage_totals` (structured data, required) — Aggregated token and cost totals for the round.

**Outputs**

- Primary: A labelled cost estimate with token counts.
- Format: Short summary line(s).
- Schema notes: Names any call excluded from the estimate because it could not be priced.

**Success criteria**

- The figure is always labelled as an estimate
- Token totals are shown alongside the cost
- Any unpriced call is named rather than silently folded into the total
- The estimate is never shown as a zero value when the true cost is unknown

**Failure modes**

- A provider's pricing is unavailable (likelihood: medium) — mitigation: Exclude and name that call rather than assume zero cost
- Totals lag behind the latest run (likelihood: low) — mitigation: Recompute from the same usage record every time the view opens

- entities: Round, TokenCount, Cost

### Round Tree — product feature — introduced in this phase

*Scope for this phase: This phase only moves the round tree to third position in the project view; its lanes, status computation, and line-opens-Artifact-View behaviour are already built and unchanged.*

Shows the current round's full set of planning artifacts as a single ordered list, so the user can see at a glance what exists, what's stale, and what's missing.

**Invocation**

- Trigger: The project view is opened, or an artifact's underlying data changes.

**Inputs**

- `current_round_artifacts` (list of items, required) — Every artifact expected in the current round.
- `artifact_dependency_graph` (structured data, required) — Which artifacts depend on which others, used to compute staleness.

**Outputs**

- Primary: An ordered list of artifact lines with status and lane.
- Format: One line per artifact.
- Schema notes: Each line carries artifact name, status (present, needs update, or missing), and lane (prompt, reference, or record).

**Success criteria**

- Artifacts always appear in pipeline order
- An artifact whose upstream source changed after it was produced shows as needing an update
- The round's usage record never shows as needing an update
- Each line's lane matches the three-item legend
- Selecting a line opens that artifact's detail view

**Failure modes**

- Status miscalculated because an upstream timestamp is missing (likelihood: medium) — mitigation: Treat unknown upstream state as needing an update rather than marking it present
- A lane is mis-colored (likelihood: low) — mitigation: Derive lane strictly from a fixed artifact-to-lane mapping

- entities: Round, Artifact, Lane

### Artifact Links — product feature — introduced in this phase

*Scope for this phase: This phase only re-verifies that every round-tree line still opens the Artifact View at that file after the reorder; the links themselves are already built and unchanged.*

Makes every artifact reachable from wherever it's mentioned — navigation, round tree, and chat downloads — so the user is never more than one choice away from seeing a file.

**Invocation**

- Trigger: The navigation is rendered, a round-tree line is rendered, or a download option is rendered in the chat frame.

**Inputs**

- `artifact_identity` (text, required) — The artifact and round a given link should point to.

**Outputs**

- Primary: A link that opens the artifact view at the right file.
- Format: An inline link beside or in place of existing entries.
- Schema notes: One link per artifact reference, always pointing at the matching file and round.

**Success criteria**

- The Artifacts destination sits between Project and Settings in the navigation
- Every round-tree line opens the artifact view at that exact file
- Every download option in the chat frame's action row is paired with an equivalent option that opens the file instead of downloading it

**Failure modes**

- A link opens the wrong round's version of a file (likelihood: low) — mitigation: Always carry the round identity together with the file identity
- A new download option is added without its matching open option (likelihood: medium) — mitigation: Derive both options from one shared list of artifacts

- depends on: development_tool_shell, artifact_view, round_tree, chat_frame_register (build these no later than `artifact_links`)
- entities: Artifact, Round, Navigation

### UI surfaces for this phase (from the design)

- **`Status Bar & Nav`** [non_ai]
  - screens: all
  - inputs: nav item
  - output: Persistent bar with working-directory path (truncates from start, empty when unknown), round, provider, model+effort, version, and Project / Artifacts / Settings / Docs nav
  - states: path known, path empty (no directory yet), active nav item, narrow viewport
  - reads: Project, WorkingDirectory, Round, Provider, Model, Effort, Navigation
- **`Agent Rows`** [non_ai]
  - screens: project-view
  - inputs: action button per agent: Start, Continue and Required are filled green (one variant); Modify a neutral outline with green text; Needs Update a warn outline; Not Ready a disabled outline. Activating a button routes to that agent as today; Continue resumes an in-progress conversation
  - output: Seven rows in pipeline order: agent, produced artifact, last model (with effort when not default), tokens in/out, one action
  - states: Start, Continue, Required, Modify, Needs Update, Not Ready (disabled), not run (blank model/tokens)
  - reads: Agent, Model, Effort, TokenCount, RunState
  - writes: RunState
  - after (advisory UI ordering): Status Bar & Nav
- **`Round Cost Strip`** [non_ai]
  - screens: project-view
  - output: Three-line estimate: labelled cost + tokens, unpriced-call line, price-source note
  - states: priced, partially unpriced, no calls recorded, all unpriced (unknown)
  - reads: Cost, TokenCount, Round
  - after (advisory UI ordering): Status Bar & Nav
- **`Round Tree`** [non_ai]
  - screens: project-view, artifact-view
  - inputs: artifact line link
  - output: Ordered list of artifact lines with lane colour and status (present unlabelled, needs update, missing)
  - states: present, needs update, missing, selected
  - reads: Artifact, Lane, Round
  - after (advisory UI ordering): Status Bar & Nav
- **`Lane Legend`** [non_ai]
  - screens: project-view, artifact-view
  - output: Three swatch/label pairs matching the tree's lanes
  - states: static
  - reads: Lane
  - after (advisory UI ordering): Round Tree
- **`Run Cost Strip`** [non_ai]
  - screens: chat-view, designer-view
  - output: Same three-line cost strip as round cost, scoped to this run
  - states: priced, partially unpriced, no calls recorded
  - reads: Cost, TokenCount, RunRecord
  - after (advisory UI ordering): Transcript
- **`Run Action Row`** [non_ai]
  - screens: chat-view
  - inputs: Open artifact, Download, Continue to <skip>, Continue to <next>
  - output: Run meta (chars, turn tokens, elapsed) at left; one primary action and neutral others at right
  - states: run in progress, run complete
  - reads: RunProgress, RunRecord, Artifact
  - writes: RunState
  - after (advisory UI ordering): Transcript
- **`Artifact File Pane`** [non_ai]
  - screens: artifact-view
  - inputs: Download
  - output: Header line (path, size, modified, lane) plus line-numbered content
  - states: file shown, no preview, missing (names producing agent), nothing selected
  - reads: Artifact, Lane, Round
  - after (advisory UI ordering): Round Tree

## Tech Stack

**Dependencies:**

- dash
- dash-mantine-components
- pytest

**Configurations:** No new configuration. Reads the existing artifact store (.spec4/v{N}/ files) and usage.json through src/spec4/project_manager.py; usage.json stays out of the dependency graph and is never marked needs-update.

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- round_artifacts (persistence) — serves `agent_rows`, `artifact_links`, `round_tree`
- usage_records (persistence): per-round usage/cost rollup; deliberately excluded from the artifact dependency graph and never marked needs-update; now also the durable record of which reasoning effort was actually used per call, including fallback-from-rejected-value outcomes — serves `agent_rows`, `round_cost`

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

1. In src/spec4/layouts/__init__.py, locate `_agent_select_layout` and reorder the three project-view children so the agent rows render first, the round cost strip second, and the round tree (with its lane legend) third.
2. Change only the order of composition. Do not modify the agent-row renderer in src/spec4/layouts/_agent_rows.py, the cost strip in src/spec4/layouts/_round_cost.py, or the tree in src/spec4/layouts/_round_tree.py — their internals, component ids, and status logic are already built and are a test contract.
3. Confirm each of the three surfaces still recomputes its state from disk on every render — artifact presence/staleness from project_manager's dependency graph, agent action state from agent_button_state, cost and token totals from usage.json — and that nothing is cached across the reorder.
4. Record the reorder as a numbered design-decision comment (D-XX) at `_agent_select_layout`, stating that controls (agent rows) precede the record (round tree) with the round cost between them.
5. Adjust vertical spacing between the three blocks in src/spec4/assets/v3.css so the reordered stack reads at the same tight density as the rest of the shell — no new decorative separators, no card hover effects, no motion.
6. Inspect tests/test_agent_rows.py and tests/test_round_tree.py for any assertion about the relative position of these surfaces within the project view and update those assertions to the new order.
7. Do NOT change tests/test_cost_summary.py's ordering assertions: they pin the cost strip's position relative to the transcript on the CHAT FRAME, not on the project view. Read them first to confirm this before touching anything, and leave them as they are.
8. Add or extend a project-view test that asserts the three surfaces appear in the exact order agent rows, round cost, round tree within `_agent_select_layout`'s rendered children, so a future reorder cannot pass silently.
9. Add a test asserting the agent rows still render the seven agents in the order given by `spec4.app_constants.AGENT_KEYS`, and that the round tree still renders its artifacts in pipeline order, after the reorder.
10. Verify manually that clicking any round-tree line still opens the Artifact View at that exact file and round, and that the round-cost strip still shows its estimate label, token totals, and any named unpriced calls.
11. Reference .spec4/v2/design/mock.html's project-view screen for the intended vertical rhythm of the reordered blocks and the lane legend's placement under the tree.

## Risk Assessment

**Potential bottlenecks:**

The most likely failure is collateral test damage: an AI coder searching for 'cost strip ordering' will find test_cost_summary.py and 'fix' its chat-frame assertions to match the project view, breaking a screen this phase does not touch. A second risk is that moving a block also moves the callbacks' Input/Output components out of a rendered layout, tripping test_callback_co_presence.py.

**Mitigation strategy:**

Explicitly scope test edits to tests/test_agent_rows.py and tests/test_round_tree.py; open tests/test_cost_summary.py to confirm its assertions are chat-frame-scoped and leave it untouched. Because this is a reorder and not a removal, every component id remains present in the layout — run `uv run pytest` immediately after the reorder and before any CSS work, so a co-presence failure is attributable to the reorder alone.

## Verification

`uv run pytest` passes, including the new project-view ordering test and the updated assertions in tests/test_agent_rows.py and tests/test_round_tree.py, with tests/test_cost_summary.py unmodified and still passing. Run `uv run python src/spec4/app.py` and open http://localhost:8050 on a project with a working directory: the project view shows agent rows first, then the round cost strip, then the round tree with its lane legend. The cost line is labelled as an estimate, shows token totals, and never displays a zero for an unknown cost (nfr_cost_and_token_figures_stay_accurate_and_reflect_the_latest_completed_run__never_showing_an_unknown_cost_as_zero). Clicking a tree line opens the Artifact View at that file.

**Non-functional acceptance** (deterministic, from the stack spec):

- `nfr_cost_and_token_figures_stay_accurate_and_reflect_the_latest_completed_run__never_showing_an_unknown_cost_as_zero`: Cost and token figures stay accurate and reflect the latest completed run, never showing an unknown cost as zero — delivered by usage_records


## References

- [Dash](https://dash.plotly.com/)
- [Dash Mantine Components](https://www.dash-mantine-components.com)
- [pytest](https://docs.pytest.org/)
