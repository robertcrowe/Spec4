---
{
  "phase_number": 1,
  "total_phases": 7,
  "phase_title": "Integration Baseline, Shared Step-Row Renderer, and Status-Bar Slot Truncation",
  "phase_summary": "Establish a clean baseline for this round's UI work: confirm the existing app builds and its full pytest suite passes untouched, extract the chat frame's active/complete/dimmed marking into one shared renderer in layouts/_shared.py that later phases reuse for the setup and Designer steppers, and fix the status bar's slot behaviour so only the working-directory path truncates, from its start.",
  "features": [
    {
      "id": "development_tool_shell",
      "role": "introduced",
      "scope_note": "This phase only adjusts the status bar's slot truncation behaviour (path truncates from its start; round, provider/model, and version never truncate); the model slot's effort suffix lands in Phase 6."
    },
    {
      "id": "chat_frame_register",
      "role": "introduced",
      "scope_note": "This phase only extracts the chat frame's existing pill-bar step-marking renderer into layouts/_shared.py and re-points _chat.py at it with no visual change; the chat frame is otherwise already built and untouched."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "dash",
      "dash-mantine-components",
      "pytest",
      "pytest-cov",
      "ruff",
      "mypy"
    ],
    "configurations": "No new configuration. Existing optional env vars only: LITELLM_LOG (defaults to ERROR, set in src/spec4/app.py before litellm is imported) and DASH_DEBUG (dev server). App serves on localhost:8050. Styling changes land in src/spec4/assets/v3.css, the single stylesheet."
  },
  "instructions": [
    "Before changing anything, run `uv run pytest` and record the passing baseline; then run `uv run ruff check src/ tests/` and `uv build`. Do not proceed to any edit until all three succeed on the untouched tree — this phase's purpose is to prove the existing codebase is green before this round's rework begins.",
    "Read src/spec4/layouts/_chat.py and locate the existing `_agent_status_bar` pill-bar renderer that marks the active agent the way the active nav item is marked, renders completed agents at full weight, and dims unreachable agents with their tooltip.",
    "Extract that active/complete/dimmed marking into a single reusable renderer function in src/spec4/layouts/_shared.py. Give it a neutral, screen-agnostic signature: a list of step/agent entries (label plus state, where state is one of active, complete, or upcoming/unreachable) plus an optional per-entry tooltip, returning the plain-text row. Do not bake agent-specific or chat-specific concepts into the shared function — Phase 5 and Phase 7 will call it for the setup wizard's step indicator and the Designer wizard's step row.",
    "Rewrite `_chat._agent_status_bar` to delegate to the new shared renderer, passing the agent pipeline order from `spec4.app_constants.AGENT_KEYS` and the per-agent reachability/tooltip data it already computes. The chat frame's rendered output — component ids, plain-text labels, ordering, marking, and tooltips — must be byte-for-byte equivalent in behaviour to before; this is a pure extraction with no visual change.",
    "Record the extraction as a numbered design-decision comment (D-XX) in src/spec4/layouts/_shared.py per the existing convention, naming this renderer as the single source of active/complete/dimmed step marking for the chat frame, setup wizard, and Designer wizard.",
    "In src/spec4/app.py, locate the status bar's slot layout (working directory path, round, default provider and model, Spec4 version) and give each slot a stable CSS class so the stylesheet can target them individually.",
    "In src/spec4/assets/v3.css, give the round, provider/model, and version slots `flex: none` so they are never compressed or truncated under width pressure, and give the working-directory path slot the flexible, shrinkable role so it is the only slot that ever gives up space.",
    "Make the working-directory path slot truncate from its START, so the project name at the tail stays readable. Implement this either with CSS on that slot only (`direction: rtl` with `text-overflow: ellipsis` and `text-align: left`, wrapping the path text in a `<bdi>`/LTR-isolated inner span so path segment order is not visually reversed) or with a leading-ellipsis Python helper in src/spec4/layouts/_shared.py that shortens from the front. Whichever you choose, apply it to that slot alone and record the choice as a D-XX comment.",
    "Keep the existing `mono` CSS class on the path and model slots; do not introduce a parallel monospace mechanism and do not set any colour on a component (D-LR2 — the accent is the theme primary and components inherit it).",
    "Preserve the import order in src/spec4/app.py exactly as it stands (D-LR1: LITELLM_LOG set and litellm imported before spec4.callbacks, which imports after the app object is constructed). The E402/E501 ruff suppressions on that file are intentional — do not remove them.",
    "Add a test in tests/ asserting that the shared step-row renderer in layouts/_shared.py marks exactly one entry as active, renders completed entries at full weight, and dims later/unreachable entries — driven by the renderer directly, not through a screen.",
    "Add a test asserting the chat frame's pill bar still renders the seven agents from AGENT_KEYS in pipeline order with the same component ids after the extraction.",
    "Add a test for the path-truncation helper or slot class: assert that the working-directory slot carries the shrink/truncate class and that the round, provider/model, and version slots carry the no-shrink class; if you implemented the leading-ellipsis in Python, assert directly that a long path is shortened from its start and retains its final segment.",
    "Reference .spec4/v2/design/mock.html for the intended visual density and slot arrangement of the status bar before finalising the CSS."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "The extraction of the pill-bar renderer touches _chat.py, which is covered by ordering-sensitive tests (test_cost_summary.py, test_agent_llm_selection.py, test_code_scanner_progress.py) and by test_callback_co_presence.py's id enumeration — an id or ordering drift during extraction breaks tests far from the change. The RTL trick for start-truncation is the classic place an AI coder gets it wrong: applying `direction: rtl` without isolating the inner text visually reverses path segments (rendering /home/user/proj as proj/user/home/), and applying it to the whole status bar rather than the one slot reverses everything.",
    "mitigation_strategy": "Treat the renderer extraction as a pure refactor: change no ids, no labels, no ordering, and run `uv run pytest` immediately after the extraction and before any styling work, so a regression is attributable to one change. For the truncation, scope the CSS rule to the path slot's class alone — never a parent — and wrap the path text in an LTR-isolated inner element; verify visually at a narrow viewport that the path reads left-to-right with a leading ellipsis and that round/provider/model/version are still fully visible. If the RTL approach proves fragile, fall back to the Python leading-ellipsis helper, which is directly unit-testable."
  },
  "verification": "`uv build` succeeds, `uv run ruff check src/ tests/` is clean, and `uv run pytest` passes with the new shared-renderer, pill-bar-parity, and slot/truncation tests included. Run `uv run python src/spec4/app.py`, open http://localhost:8050, and narrow the window until the status bar is under width pressure: the round, provider/model, and version stay fully legible while only the working-directory path shortens, and it shortens from its start with the project name still readable (nfr_the_status_bar_s_round__provider__model__and_version_stay_fully_legible_regardless_of_window_width). The chat frame's pill bar is visually and behaviourally unchanged.",
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
      "standard": "CSS text-overflow (MDN)",
      "url": "https://developer.mozilla.org/en-US/docs/Web/CSS/text-overflow"
    },
    {
      "standard": "pytest",
      "url": "https://docs.pytest.org/"
    }
  ]
}
---

# Phase 1 of 7: Integration Baseline, Shared Step-Row Renderer, and Status-Bar Slot Truncation

Establish a clean baseline for this round's UI work: confirm the existing app builds and its full pytest suite passes untouched, extract the chat frame's active/complete/dimmed marking into one shared renderer in layouts/_shared.py that later phases reuse for the setup and Designer steppers, and fix the status bar's slot behaviour so only the working-directory path truncates, from its start.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Development Tool Shell — product feature — introduced in this phase

*Scope for this phase: This phase only adjusts the status bar's slot truncation behaviour (path truncates from its start; round, provider/model, and version never truncate); the model slot's effort suffix lands in Phase 6.*

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

### Chat Frame Register — product feature — introduced in this phase

*Scope for this phase: This phase only extracts the chat frame's existing pill-bar step-marking renderer into layouts/_shared.py and re-points _chat.py at it with no visual change; the chat frame is otherwise already built and untouched.*

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
- **`Agent Pipeline Row`** [non_ai]
  - screens: chat-view, designer-view
  - inputs: agent link
  - output: Plain-text row of seven agents; active marked like active nav, done at full emphasis, unreachable dimmed
  - states: done, active, reachable, unreachable
  - reads: Agent, RunState
  - after (advisory UI ordering): Status Bar & Nav
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
- pytest
- pytest-cov
- ruff
- mypy

**Configurations:** No new configuration. Existing optional env vars only: LITELLM_LOG (defaults to ERROR, set in src/spec4/app.py before litellm is imported) and DASH_DEBUG (dev server). App serves on localhost:8050. Styling changes land in src/spec4/assets/v3.css, the single stylesheet.

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- usage_records (persistence): per-round usage/cost rollup; deliberately excluded from the artifact dependency graph and never marked needs-update; now also the durable record of which reasoning effort was actually used per call, including fallback-from-rejected-value outcomes — serves `chat_frame_register`
- session_store (persistence) — serves `development_tool_shell`
- prefs_store (persistence) — serves `development_tool_shell`

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

1. Before changing anything, run `uv run pytest` and record the passing baseline; then run `uv run ruff check src/ tests/` and `uv build`. Do not proceed to any edit until all three succeed on the untouched tree — this phase's purpose is to prove the existing codebase is green before this round's rework begins.
2. Read src/spec4/layouts/_chat.py and locate the existing `_agent_status_bar` pill-bar renderer that marks the active agent the way the active nav item is marked, renders completed agents at full weight, and dims unreachable agents with their tooltip.
3. Extract that active/complete/dimmed marking into a single reusable renderer function in src/spec4/layouts/_shared.py. Give it a neutral, screen-agnostic signature: a list of step/agent entries (label plus state, where state is one of active, complete, or upcoming/unreachable) plus an optional per-entry tooltip, returning the plain-text row. Do not bake agent-specific or chat-specific concepts into the shared function — Phase 5 and Phase 7 will call it for the setup wizard's step indicator and the Designer wizard's step row.
4. Rewrite `_chat._agent_status_bar` to delegate to the new shared renderer, passing the agent pipeline order from `spec4.app_constants.AGENT_KEYS` and the per-agent reachability/tooltip data it already computes. The chat frame's rendered output — component ids, plain-text labels, ordering, marking, and tooltips — must be byte-for-byte equivalent in behaviour to before; this is a pure extraction with no visual change.
5. Record the extraction as a numbered design-decision comment (D-XX) in src/spec4/layouts/_shared.py per the existing convention, naming this renderer as the single source of active/complete/dimmed step marking for the chat frame, setup wizard, and Designer wizard.
6. In src/spec4/app.py, locate the status bar's slot layout (working directory path, round, default provider and model, Spec4 version) and give each slot a stable CSS class so the stylesheet can target them individually.
7. In src/spec4/assets/v3.css, give the round, provider/model, and version slots `flex: none` so they are never compressed or truncated under width pressure, and give the working-directory path slot the flexible, shrinkable role so it is the only slot that ever gives up space.
8. Make the working-directory path slot truncate from its START, so the project name at the tail stays readable. Implement this either with CSS on that slot only (`direction: rtl` with `text-overflow: ellipsis` and `text-align: left`, wrapping the path text in a `<bdi>`/LTR-isolated inner span so path segment order is not visually reversed) or with a leading-ellipsis Python helper in src/spec4/layouts/_shared.py that shortens from the front. Whichever you choose, apply it to that slot alone and record the choice as a D-XX comment.
9. Keep the existing `mono` CSS class on the path and model slots; do not introduce a parallel monospace mechanism and do not set any colour on a component (D-LR2 — the accent is the theme primary and components inherit it).
10. Preserve the import order in src/spec4/app.py exactly as it stands (D-LR1: LITELLM_LOG set and litellm imported before spec4.callbacks, which imports after the app object is constructed). The E402/E501 ruff suppressions on that file are intentional — do not remove them.
11. Add a test in tests/ asserting that the shared step-row renderer in layouts/_shared.py marks exactly one entry as active, renders completed entries at full weight, and dims later/unreachable entries — driven by the renderer directly, not through a screen.
12. Add a test asserting the chat frame's pill bar still renders the seven agents from AGENT_KEYS in pipeline order with the same component ids after the extraction.
13. Add a test for the path-truncation helper or slot class: assert that the working-directory slot carries the shrink/truncate class and that the round, provider/model, and version slots carry the no-shrink class; if you implemented the leading-ellipsis in Python, assert directly that a long path is shortened from its start and retains its final segment.
14. Reference .spec4/v2/design/mock.html for the intended visual density and slot arrangement of the status bar before finalising the CSS.

## Risk Assessment

**Potential bottlenecks:**

The extraction of the pill-bar renderer touches _chat.py, which is covered by ordering-sensitive tests (test_cost_summary.py, test_agent_llm_selection.py, test_code_scanner_progress.py) and by test_callback_co_presence.py's id enumeration — an id or ordering drift during extraction breaks tests far from the change. The RTL trick for start-truncation is the classic place an AI coder gets it wrong: applying `direction: rtl` without isolating the inner text visually reverses path segments (rendering /home/user/proj as proj/user/home/), and applying it to the whole status bar rather than the one slot reverses everything.

**Mitigation strategy:**

Treat the renderer extraction as a pure refactor: change no ids, no labels, no ordering, and run `uv run pytest` immediately after the extraction and before any styling work, so a regression is attributable to one change. For the truncation, scope the CSS rule to the path slot's class alone — never a parent — and wrap the path text in an LTR-isolated inner element; verify visually at a narrow viewport that the path reads left-to-right with a leading ellipsis and that round/provider/model/version are still fully visible. If the RTL approach proves fragile, fall back to the Python leading-ellipsis helper, which is directly unit-testable.

## Verification

`uv build` succeeds, `uv run ruff check src/ tests/` is clean, and `uv run pytest` passes with the new shared-renderer, pill-bar-parity, and slot/truncation tests included. Run `uv run python src/spec4/app.py`, open http://localhost:8050, and narrow the window until the status bar is under width pressure: the round, provider/model, and version stay fully legible while only the working-directory path shortens, and it shortens from its start with the project name still readable (nfr_the_status_bar_s_round__provider__model__and_version_stay_fully_legible_regardless_of_window_width). The chat frame's pill bar is visually and behaviourally unchanged.

**Non-functional acceptance** (deterministic, from the stack spec):

- `nfr_cost_and_token_figures_stay_accurate_and_reflect_the_latest_completed_run__never_showing_an_unknown_cost_as_zero`: Cost and token figures stay accurate and reflect the latest completed run, never showing an unknown cost as zero — delivered by usage_records


## References

- [Dash](https://dash.plotly.com/)
- [Dash Mantine Components](https://www.dash-mantine-components.com)
- [CSS text-overflow (MDN)](https://developer.mozilla.org/en-US/docs/Web/CSS/text-overflow)
- [pytest](https://docs.pytest.org/)
