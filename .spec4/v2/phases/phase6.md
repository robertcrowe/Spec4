---
{
  "phase_number": 6,
  "total_phases": 7,
  "phase_title": "Gate Panel Register and Effort Display Across Model Slots",
  "phase_summary": "Turn the per-agent model gate into a one-line monospace panel naming the agent and its default model, across both of its resting shapes and both of its render sites, inheriting the setup wizard's fields (including Effort) when 'Pick a model' expands. Effort then appears after the model name wherever a model is shown — status bar slot, model chip, retry panel, and the agent rows' last-model column — read through the single selection path.",
  "features": [
    {
      "id": "gate_card_register",
      "role": "introduced",
      "scope_note": "Implements the feature in full — both resting shapes, both render sites, and the removal of the Designer-route agent-name heading."
    },
    {
      "id": "per_agent_effort",
      "role": "extended",
      "scope_note": "Adds the gate's Effort control and the '· <effort>' suffix in the status bar slot, model chip, retry panel, Keep-button label, and agent rows; the stored field and call path came from Phase 4 and the setup default select from Phase 5."
    },
    {
      "id": "agent_rows",
      "role": "extended",
      "scope_note": "Adds the '· <effort>' suffix to the last-model column when the agent's recorded effort is not default, read from usage.json as the model already is; the reorder came from Phase 2."
    },
    {
      "id": "development_tool_shell",
      "role": "extended",
      "scope_note": "Adds the effort suffix to the status bar's model slot when the effort is not default; the slot truncation rules came from Phase 1."
    },
    {
      "id": "chat_frame_register",
      "role": "extended",
      "scope_note": "Adds the effort suffix to the chat frame's model chip and retry panel and hosts the reworked gate panel; the chat frame's own register rework is already built and otherwise untouched."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "dash",
      "dash-mantine-components",
      "litellm",
      "pytest"
    ],
    "configurations": "No new configuration. GateSelection (agent, defaultModel, chosenModel, chosenEffort, expanded) lives in the existing session dcc.Store and is read via callback State; the project default model and effort come from the prefs store. Agent-row model and effort are read from the round's usage.json. All reads and writes go through src/spec4/llm_selection.py."
  },
  "instructions": [
    "Read the module docstring at the top of src/spec4/layouts/_llm_gate.py and identify its two resting shapes (no entry present / entry present) before editing. This phase reworks both shapes, and the gate's two render sites — inside the chat frame and in front of the Designer route — in one change.",
    "Rework the gate's collapsed rendering into a single line: the agent name and its default model in monospace using the existing `mono` class, in the shape 'Model for <Agent>: <model> · default'. Keep GATE_IDS unchanged — the button ids are a test contract asserted by tests/test_agent_llm_selection.py and the gate tests.",
    "Beneath that line, render the existing two- or three-button row unchanged in behaviour: 'Use default' as the one filled primary, 'Pick a model' and 'Keep <model>' as neutral outlines. Which of the two or three buttons appear is determined by the existing resting-shape logic — do not change that logic.",
    "Extend the 'Keep' button's label to include the effort when an effort is overridden for that agent, in the shape 'Keep claude-sonnet-5 · high'; when the agent's effort is 'default', the label shows the model name alone. Read both values through llm_selection.py's single (model, effort) path.",
    "Make 'Pick a model' expand to the fields produced by the shared builders `provider_key_fields` and `model_field` in src/spec4/layouts/_setup.py — which Phase 5 restyled and to which it added the Effort select. Do not copy, fork, or re-style those fields here; the gate inherits them so the two cannot diverge.",
    "Wire the gate's Effort selection to write the chosen effort onto the per-agent entry through llm_selection.py's single read/write path, alongside the chosen model — never a second store key or a parallel writer.",
    "Remove the separate 'Designer' agent-name heading rendered above the gate on the Designer route. The status bar and the agent pipeline row already name the active agent. Remove any callback that populated that heading, and update its entry in tests/test_callback_co_presence.py in the same change.",
    "Confirm the reworked gate is still exactly one component serving all seven agents plus the Designer entry point — no route-specific variant may be introduced.",
    "In the status bar in src/spec4/app.py, render the model slot as '<model> · <effort>' when the resolved effort is not 'default', and as the model alone when it is. Keep the `mono` class on the slot and keep its `flex: none` no-truncate rule from Phase 1 intact.",
    "In src/spec4/layouts/_chat.py, apply the same suffix rule to the model chip, and in the retry panel apply it to the model it names — both reading through llm_selection.py, never recomputing the resolution.",
    "In src/spec4/layouts/_agent_rows.py, extend the last-model column so it renders '<model> · <effort>' when the effort recorded for that agent this round is not 'default', reading the effort from the round's usage.json exactly as the model is already read. Leave the column blank when the agent has not run this round, as it is today.",
    "Do not set a colour prop on any gate, chip, or row component — the accent is the theme primary and components inherit it (D-LR2).",
    "Add a test asserting the gate's first rendered line names the agent and its default model and carries the `mono` class, in both resting shapes.",
    "Add a test asserting the gate renders exactly one filled-primary button ('Use default') with the others as neutral outlines, and that GATE_IDS' button ids are unchanged from before this phase.",
    "Add a test asserting the gate rendered on the Designer route has no separate agent-name heading above it, and that the same gate component is used on both the chat-frame and Designer render sites.",
    "Add a test asserting expanding 'Pick a model' renders the same field components produced by _setup.py's shared builders, including the Effort select.",
    "In tests/test_agent_llm_selection.py, add a test that choosing an effort in the gate writes it to the per-agent entry through the single llm_selection path, and that the status bar slot, model chip, and retry panel all render the same '<model> · <effort>' string for that agent, with no suffix when the effort is 'default'.",
    "Add a test asserting the Keep button's label includes '· <effort>' when the agent's effort is overridden and omits it when the effort is 'default'.",
    "In tests/test_agent_rows.py, add a test that an agent whose usage.json record carries a non-default effort renders '<model> · <effort>' in its last-model column, an agent with a default effort renders the model alone, and an agent that has not run renders blank.",
    "Reference .spec4/v2/design/mock.html's chat-view screen — its Gate Panel, Gate Panel — Expanded, and Model & Status Line surfaces — for the intended one-line panel shape and effort-suffix treatment."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "The gate is the highest-connectivity component in this round: one component, two resting shapes, two render sites, and id contracts asserted by tests/test_agent_llm_selection.py and the gate tests. The likeliest hallucination is a coder that 'simplifies' by writing a Designer-specific gate variant or by inlining fresh model/effort fields instead of importing the shared _setup.py builders — both violate the single-component and single-definition rules. A second risk is the effort suffix being computed in four places with four slightly different rules, so the chip and the status bar disagree.",
    "mitigation_strategy": "Write one small formatting helper that turns a (model, effort) pair into its display string, place it beside the resolution path in llm_selection.py, and have the status bar, model chip, retry panel, agent rows, and Keep-button label all call it — assert in a test that the four surfaces render an identical string for the same agent. Import the field builders from _setup.py by name rather than reconstructing fields, and add the test that the expanded gate renders exactly those components. Remove the Designer heading, its callback, and its co-presence test entry in one change, then run `uv run pytest` before starting the effort-suffix work so failures are attributable."
  },
  "verification": "`uv run pytest` passes, including tests/test_agent_llm_selection.py, the gate tests, tests/test_agent_rows.py, and the updated tests/test_callback_co_presence.py with the Designer heading's id removed. `uv run mypy` (strict) is clean. Run `uv run python src/spec4/app.py`: an agent whose model is unconfirmed shows the gate as one monospace line reading 'Model for <Agent>: <model> · default' with Use default as the sole filled primary; 'Pick a model' expands the same fields the setup wizard shows, including the Effort select; the Designer route shows the gate with no separate agent-name heading. After choosing a non-default effort, the status bar's model slot, the chat frame's model chip, the retry panel, and the Keep button all read '<model> · <effort>', and a run's agent row shows the same suffix in its last-model column. The status bar's round, provider, model, and version remain fully legible at any window width (nfr_the_status_bar_s_round__provider__model__and_version_stay_fully_legible_regardless_of_window_width), and the single accent colour marks the one primary action (nfr_a_single_accent_color_and_consistent_low_chrome_visual_language_across_every_screen__with_no_exceptions).",
  "references": [
    {
      "standard": "Dash",
      "url": "https://dash.plotly.com/"
    },
    {
      "standard": "Dash Mantine Components — Select",
      "url": "https://www.dash-mantine-components.com/components/select"
    },
    {
      "standard": "Dash Mantine Components",
      "url": "https://www.dash-mantine-components.com"
    },
    {
      "standard": "LiteLLM reasoning_effort / reasoning content",
      "url": "https://docs.litellm.ai/docs/reasoning_content"
    },
    {
      "standard": "pytest",
      "url": "https://docs.pytest.org/"
    }
  ]
}
---

# Phase 6 of 7: Gate Panel Register and Effort Display Across Model Slots

Turn the per-agent model gate into a one-line monospace panel naming the agent and its default model, across both of its resting shapes and both of its render sites, inheriting the setup wizard's fields (including Effort) when 'Pick a model' expands. Effort then appears after the model name wherever a model is shown — status bar slot, model chip, retry panel, and the agent rows' last-model column — read through the single selection path.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Gate Card Register — product feature — introduced in this phase

*Scope for this phase: Implements the feature in full — both resting shapes, both render sites, and the removal of the Designer-route agent-name heading.*

Turns the shared per-agent model gate into a compact one-line panel naming the agent and its default model, with a small, clear set of choices, reused identically wherever a model must be confirmed.

**Invocation**

- Trigger: An agent is about to run and its model has not yet been confirmed for this round.

**Inputs**

- `agent_name` (text, required) — The agent the gate is confirming a model for.
- `default_model` (text, required) — The model that would be used if the default is accepted.
- `current_selection_state` (text, required) — Whether a model has already been chosen or kept for this agent.

**Outputs**

- Primary: The reworked gate panel.
- Format: One monospace naming line plus a two- or three-action row.
- Schema notes: 'Use default' is primary; 'Pick a model' and 'Keep <model>' are neutral; picking expands the setup wizard's model fields inline.

**Success criteria**

- The panel's first line names the agent and its default model in fixed-width type
- Exactly one component serves all seven agents and the Designer entry point
- Expanding 'Pick a model' reveals the same fields the setup wizard uses
- The separate agent-name heading above the panel on the Designer entry point is gone, since the status bar and agent progress row already name the agent
- The underlying selection identifiers, behavior, and capability check are unchanged

**Failure modes**

- The panel diverges from the setup wizard's fields over time (likelihood: low) — mitigation: Keep the expanded fields sourced from the same definition as the setup wizard
- Removing the heading leaves the Designer entry point unclear about which agent is active (likelihood: low) — mitigation: Confirm the status bar and agent progress row always name the current agent

- depends on: development_tool_shell, setup_wizard_register (build these no later than `gate_card_register`)
- entities: Agent, Model, SetupStep

### Per-Agent Effort — product feature — extended in this phase

*Scope for this phase: Adds the gate's Effort control and the '· <effort>' suffix in the status bar slot, model chip, retry panel, Keep-button label, and agent rows; the stored field and call path came from Phase 4 and the setup default select from Phase 5.*

Lets a reasoning-effort level be chosen per agent alongside its model, so agents that need deeper reasoning can use it while others stay fast and cheap.

**Invocation**

- Trigger: A model is resolved for an agent, in the gate panel or the setup wizard's model step.

**Inputs**

- `resolved_model_capabilities` (list of items, required) — The effort levels the chosen model actually supports.
- `chosen_effort` (text, required) — The effort level selected for the agent, or for the default.

**Outputs**

- Primary: The stored effort choice for an agent, or for the default.
- Format: One value alongside the model in the same selection record.
- Schema notes: Allowed values are always 'default' plus low, medium, high, with xhigh or max appearing only when the resolved model supports them.

**Success criteria**

- The offered effort values always match what the resolved model actually supports
- An agent left on 'default' inherits the default's effort exactly as it inherits its model
- The effort appears after the model name wherever the model is shown, but only when it isn't 'default'
- Every run records which effort was actually used
- An unsupported effort value never causes a run to fail
- The gate, the model indicator, the retry flow, and the setup wizard all read and write the same stored value

**Failure modes**

- A model's supported effort levels are misreported (likelihood: medium) — mitigation: Trust only the resolved capability check, never an assumed list
- An unsupported effort value is sent to a model that rejects it (likelihood: low) — mitigation: Drop the parameter silently rather than let the run fail
- Gate and wizard fall out of sync on the stored value (likelihood: low) — mitigation: Keep one single read/write path for the field

- depends on: gate_card_register, setup_wizard_register, chat_frame_register, development_tool_shell (build these no later than `per_agent_effort`)
- entities: Agent, Model, Effort, RunRecord

### Agent Rows — product feature — extended in this phase

*Scope for this phase: Adds the '· <effort>' suffix to the last-model column when the agent's recorded effort is not default, read from usage.json as the model already is; the reorder came from Phase 2.*

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

### Development Tool Shell — product feature — extended in this phase

*Scope for this phase: Adds the effort suffix to the status bar's model slot when the effort is not default; the slot truncation rules came from Phase 1.*

Provides the single persistent status bar and primary navigation that frames every screen, replacing the prior marketing-style header and footer with a compact, information-dense developer-tool bar.

**Invocation**

- Trigger: Any screen loads, or the working directory, round, or default provider/model changes.

**Inputs**

- `working_directory_path` (text, required) — The path of the currently open project.
- `current_round_number` (number, required) — The round currently active in the project.
- `default_provider_and_model` (text, required) — The provider and model configured as the project default.
- `app_version` (text, required) — The running version of the tool.
- `viewport_width` (number, required) — Available horizontal space, used to decide what truncates.

**Outputs**

- Primary: A rendered status bar and four-item navigation.
- Format: Persistent header row plus navigation row on every screen.
- Schema notes: Slots for path, round, provider/model, version, and links to Project, Artifacts, Settings, and Docs.

**Success criteria**

- Round, provider+model, and version are always fully visible regardless of width
- Only the working-directory path ever truncates, always from its start, leaving the project name visible
- No external-link drawer, footer, or landing page appears anywhere
- A single accent color marks every primary action, active nav state, and focus indicator
- Vertical spacing is visibly tighter than the prior register

**Failure modes**

- Wrong element truncates under extreme narrowness (likelihood: medium) — mitigation: Enforce a fixed truncation order with the directory path always first
- Two accent colors compete for primary emphasis (likelihood: low) — mitigation: Restrict the accent color to a single role across the app

- entities: WorkingDirectory, Round, Provider, Model, Navigation

### Chat Frame Register — product feature — extended in this phase

*Scope for this phase: Adds the effort suffix to the chat frame's model chip and retry panel and hosts the reworked gate panel; the chat frame's own register rework is already built and otherwise untouched.*

Keeps the conversation screen's full set of existing functions — agent progress, transcript, live indicators, retries, downloads — while presenting them in the plain, low-chrome developer-tool style.

**Invocation**

- Trigger: A conversation with any agent is opened or continues.

**Inputs**

- `agent_pipeline_state` (list of items, required) — Which agents are completed, active, or unreachable.
- `transcript_messages` (list of items, required) — The conversation history for the current agent.
- `live_run_progress` (structured data, required) — Character and elapsed-time counters for an in-progress run.
- `run_cost_summary` (structured data, required) — The cost of a completed run.

**Outputs**

- Primary: The reworked conversation screen.
- Format: Plain-text agent progress row, block-style transcript, action row, and composer.
- Schema notes: Exactly one primary action per row; a completed run's cost appears as the same summary style used for round cost.

**Success criteria**

- Every function present before the rework still works: progress indicators, turn tokens, fast-forward with its explanation, retry, alternative-response choice, downloads, continue actions, composer, model indicator, status line
- The agent progress row shows plain text only, active agent marked the same way as the active nav item, completed agents at full emphasis, unreachable agents dimmed with their explanation still available, no connecting marks between them
- Duplicated back-navigation controls are gone, since the agent progress row and the status bar's project link already provide that path
- Transcript messages read as plain blocks with a dimmed one-word label, no fill color, and a neutral marker on the user's own messages
- A completed run's cost renders in the same three-line style as round cost
- Exactly one primary-emphasis action appears per row, with all others neutral
- The live-activity indicator is the only moving element on screen

**Failure modes**

- A function is silently dropped during the visual rework (likelihood: medium) — mitigation: Verify each pre-existing function against a checklist before release
- Removed back-navigation leaves a dead end (likelihood: low) — mitigation: Confirm the agent progress row and status bar project link always remain reachable

- depends on: development_tool_shell, round_cost (build these no later than `chat_frame_register`)
- entities: Agent, Message, RunProgress, Cost, Model

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
- **`Agent Pipeline Row`** [non_ai]
  - screens: chat-view, designer-view
  - inputs: agent link
  - output: Plain-text row of seven agents; active marked like active nav, done at full emphasis, unreachable dimmed
  - states: done, active, reachable, unreachable
  - reads: Agent, RunState
  - after (advisory UI ordering): Status Bar & Nav
- **`Gate Panel`** [non_ai]
  - screens: chat-view
  - inputs: Use default (filled), Pick a model (outline), Keep <model> (outline; only when the agent already has an override from a previous entry — the three-button shape)
  - output: One mono naming line 'Model for <agent>: <model> · <effort>' plus the action row. Exactly one gate state is on screen at a time, and the gate precedes the run: while it shows, the transcript, cost strip, action row and composer are not rendered. The mock draws both gate states above a transcript only so both are visible
  - states: no entry: Use default · Pick a model, entry present: Keep <model> · Use default · Pick a model, expanded (see Gate Panel — Expanded)
  - reads: GateSelection, Agent, Model, Effort
  - writes: GateSelection
  - after (advisory UI ordering): Agent Pipeline Row
- **`Gate Panel — Expanded`** [non_ai]
  - screens: chat-view
  - inputs: Provider select, API key field, Model select, Effort select, Use this model, Cancel
  - output: The setup wizard's own fields revealed inline, with effort beside the model
  - states: expanded, effort overridden, model without effort support (Effort shows only "default", disabled)
  - reads: Provider, Credential, Model, Effort, GateSelection
  - writes: GateSelection, Effort, Credential
  - after (advisory UI ordering): Gate Panel
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
- **`Live Activity Indicator`** [non_ai]
  - screens: chat-view
  - output: Thin striped bar — the only moving element
  - states: active, idle
  - reads: RunProgress
  - after (advisory UI ordering): Run Action Row
- **`Composer`** [non_ai]
  - screens: chat-view
  - inputs: reply textarea, Send
  - output: The user's next turn
  - states: empty, typing, sending
  - reads: Message
  - writes: Message
  - after (advisory UI ordering): Transcript
- **`Model & Status Line`** [non_ai]
  - screens: chat-view
  - inputs: change
  - output: Model chip with effort when not default, and the run status line
  - states: idle, replying
  - reads: Model, Effort, RunProgress
  - after (advisory UI ordering): Composer
- **`Default Model Panel`** [non_ai]
  - screens: setup-view
  - inputs: Model select, Effort select
  - output: The default model and effort for the project, with one dimmed connection line and one dimmed effort-scope line
  - states: connected, effort default, effort chosen, model without effort support (Effort shows only "default", disabled)
  - reads: Model, Effort, Provider
  - writes: Model, Effort
  - after (advisory UI ordering): Setup Stepper
The following surface(s) realize the AI capability `chat_frame_register` — one unit of work; the surfaces are views onto it:
- **`Transcript`** [ai]
  - screens: chat-view
  - output: Plain message blocks with dimmed one-word labels, neutral marker on user turns, code blocks in mono
  - states: idle, streaming, empty, error
  - reads: Message, RunRecord
  - after (advisory UI ordering): Agent Pipeline Row

## Tech Stack

**Dependencies:**

- dash
- dash-mantine-components
- litellm
- pytest

**Configurations:** No new configuration. GateSelection (agent, defaultModel, chosenModel, chosenEffort, expanded) lives in the existing session dcc.Store and is read via callback State; the project default model and effort come from the prefs store. Agent-row model and effort are read from the round's usage.json. All reads and writes go through src/spec4/llm_selection.py.

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- round_artifacts (persistence) — serves `agent_rows`
- usage_records (persistence): per-round usage/cost rollup; deliberately excluded from the artifact dependency graph and never marked needs-update; now also the durable record of which reasoning effort was actually used per call, including fallback-from-rejected-value outcomes — serves `agent_rows`, `chat_frame_register`, `per_agent_effort`
- session_store (persistence) — serves `development_tool_shell`, `gate_card_register`, `per_agent_effort`
- prefs_store (persistence) — serves `development_tool_shell`, `per_agent_effort`

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

1. Read the module docstring at the top of src/spec4/layouts/_llm_gate.py and identify its two resting shapes (no entry present / entry present) before editing. This phase reworks both shapes, and the gate's two render sites — inside the chat frame and in front of the Designer route — in one change.
2. Rework the gate's collapsed rendering into a single line: the agent name and its default model in monospace using the existing `mono` class, in the shape 'Model for <Agent>: <model> · default'. Keep GATE_IDS unchanged — the button ids are a test contract asserted by tests/test_agent_llm_selection.py and the gate tests.
3. Beneath that line, render the existing two- or three-button row unchanged in behaviour: 'Use default' as the one filled primary, 'Pick a model' and 'Keep <model>' as neutral outlines. Which of the two or three buttons appear is determined by the existing resting-shape logic — do not change that logic.
4. Extend the 'Keep' button's label to include the effort when an effort is overridden for that agent, in the shape 'Keep claude-sonnet-5 · high'; when the agent's effort is 'default', the label shows the model name alone. Read both values through llm_selection.py's single (model, effort) path.
5. Make 'Pick a model' expand to the fields produced by the shared builders `provider_key_fields` and `model_field` in src/spec4/layouts/_setup.py — which Phase 5 restyled and to which it added the Effort select. Do not copy, fork, or re-style those fields here; the gate inherits them so the two cannot diverge.
6. Wire the gate's Effort selection to write the chosen effort onto the per-agent entry through llm_selection.py's single read/write path, alongside the chosen model — never a second store key or a parallel writer.
7. Remove the separate 'Designer' agent-name heading rendered above the gate on the Designer route. The status bar and the agent pipeline row already name the active agent. Remove any callback that populated that heading, and update its entry in tests/test_callback_co_presence.py in the same change.
8. Confirm the reworked gate is still exactly one component serving all seven agents plus the Designer entry point — no route-specific variant may be introduced.
9. In the status bar in src/spec4/app.py, render the model slot as '<model> · <effort>' when the resolved effort is not 'default', and as the model alone when it is. Keep the `mono` class on the slot and keep its `flex: none` no-truncate rule from Phase 1 intact.
10. In src/spec4/layouts/_chat.py, apply the same suffix rule to the model chip, and in the retry panel apply it to the model it names — both reading through llm_selection.py, never recomputing the resolution.
11. In src/spec4/layouts/_agent_rows.py, extend the last-model column so it renders '<model> · <effort>' when the effort recorded for that agent this round is not 'default', reading the effort from the round's usage.json exactly as the model is already read. Leave the column blank when the agent has not run this round, as it is today.
12. Do not set a colour prop on any gate, chip, or row component — the accent is the theme primary and components inherit it (D-LR2).
13. Add a test asserting the gate's first rendered line names the agent and its default model and carries the `mono` class, in both resting shapes.
14. Add a test asserting the gate renders exactly one filled-primary button ('Use default') with the others as neutral outlines, and that GATE_IDS' button ids are unchanged from before this phase.
15. Add a test asserting the gate rendered on the Designer route has no separate agent-name heading above it, and that the same gate component is used on both the chat-frame and Designer render sites.
16. Add a test asserting expanding 'Pick a model' renders the same field components produced by _setup.py's shared builders, including the Effort select.
17. In tests/test_agent_llm_selection.py, add a test that choosing an effort in the gate writes it to the per-agent entry through the single llm_selection path, and that the status bar slot, model chip, and retry panel all render the same '<model> · <effort>' string for that agent, with no suffix when the effort is 'default'.
18. Add a test asserting the Keep button's label includes '· <effort>' when the agent's effort is overridden and omits it when the effort is 'default'.
19. In tests/test_agent_rows.py, add a test that an agent whose usage.json record carries a non-default effort renders '<model> · <effort>' in its last-model column, an agent with a default effort renders the model alone, and an agent that has not run renders blank.
20. Reference .spec4/v2/design/mock.html's chat-view screen — its Gate Panel, Gate Panel — Expanded, and Model & Status Line surfaces — for the intended one-line panel shape and effort-suffix treatment.

## Risk Assessment

**Potential bottlenecks:**

The gate is the highest-connectivity component in this round: one component, two resting shapes, two render sites, and id contracts asserted by tests/test_agent_llm_selection.py and the gate tests. The likeliest hallucination is a coder that 'simplifies' by writing a Designer-specific gate variant or by inlining fresh model/effort fields instead of importing the shared _setup.py builders — both violate the single-component and single-definition rules. A second risk is the effort suffix being computed in four places with four slightly different rules, so the chip and the status bar disagree.

**Mitigation strategy:**

Write one small formatting helper that turns a (model, effort) pair into its display string, place it beside the resolution path in llm_selection.py, and have the status bar, model chip, retry panel, agent rows, and Keep-button label all call it — assert in a test that the four surfaces render an identical string for the same agent. Import the field builders from _setup.py by name rather than reconstructing fields, and add the test that the expanded gate renders exactly those components. Remove the Designer heading, its callback, and its co-presence test entry in one change, then run `uv run pytest` before starting the effort-suffix work so failures are attributable.

## Verification

`uv run pytest` passes, including tests/test_agent_llm_selection.py, the gate tests, tests/test_agent_rows.py, and the updated tests/test_callback_co_presence.py with the Designer heading's id removed. `uv run mypy` (strict) is clean. Run `uv run python src/spec4/app.py`: an agent whose model is unconfirmed shows the gate as one monospace line reading 'Model for <Agent>: <model> · default' with Use default as the sole filled primary; 'Pick a model' expands the same fields the setup wizard shows, including the Effort select; the Designer route shows the gate with no separate agent-name heading. After choosing a non-default effort, the status bar's model slot, the chat frame's model chip, the retry panel, and the Keep button all read '<model> · <effort>', and a run's agent row shows the same suffix in its last-model column. The status bar's round, provider, model, and version remain fully legible at any window width (nfr_the_status_bar_s_round__provider__model__and_version_stay_fully_legible_regardless_of_window_width), and the single accent colour marks the one primary action (nfr_a_single_accent_color_and_consistent_low_chrome_visual_language_across_every_screen__with_no_exceptions).

**Non-functional acceptance** (deterministic, from the stack spec):

- `nfr_cost_and_token_figures_stay_accurate_and_reflect_the_latest_completed_run__never_showing_an_unknown_cost_as_zero`: Cost and token figures stay accurate and reflect the latest completed run, never showing an unknown cost as zero — delivered by usage_records


## References

- [Dash](https://dash.plotly.com/)
- [Dash Mantine Components — Select](https://www.dash-mantine-components.com/components/select)
- [Dash Mantine Components](https://www.dash-mantine-components.com)
- [LiteLLM reasoning_effort / reasoning content](https://docs.litellm.ai/docs/reasoning_content)
- [pytest](https://docs.pytest.org/)
