---
{
  "phase_number": 5,
  "total_phases": 7,
  "phase_title": "Setup Wizard Register — Terse Three-Step Setup and the Default Effort Select",
  "phase_summary": "Bring the three-step setup wizard into the dev-tool register — one short title per step, alerts reduced to single dimmed lines, the free-tier notice and the return-to-picker button removed, one filled primary per step — and add the default Effort select beside the model field. The shared provider/key/model field builders are restyled here once, so the gate panel inherits them in Phase 6.",
  "features": [
    {
      "id": "setup_wizard_register",
      "role": "introduced",
      "scope_note": "Implements the feature in full, including restyling the shared provider_key_fields / model_field builders that the gate inherits in Phase 6."
    },
    {
      "id": "per_agent_effort",
      "role": "extended",
      "scope_note": "Adds the default Effort select to the wizard's model step, reading and writing through llm_selection.py from Phase 4; the gate's own Effort select and the model-name effort suffixes land in Phase 6."
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
    "configurations": "No new configuration. The default provider, model, and effort live in the prefs dcc.Store (localStorage) and are read via callback State; the BYOK credential stays client-side only and never reaches the server or disk. Styling lands in src/spec4/assets/v3.css. Effort values come from llm_selection.py's offered-values function built in Phase 4."
  },
  "instructions": [
    "In src/spec4/layouts/_setup.py, reduce each of the three steps' titles to one short line and delete the explanatory paragraphs beneath them. Keep every field, every id in SETUP_IDS, and every validation rule exactly as they are — the specification's success criteria require fields, identifiers, and validation to be unchanged.",
    "Replace the 'your key is never stored outside your system' alert with a single dimmed dmc.Text line directly under the key field. Delete the alert component itself; the fact survives as one dimmed line.",
    "Replace the 'Connected to X' alert with a single dimmed dmc.Text line directly above the model select. Delete the alert component.",
    "Delete the Google free-tier warning entirely — it does not survive as a dimmed line.",
    "Restyle the shared field builders `provider_key_fields` and `model_field` in _setup.py ONCE, here. These are shared with src/spec4/layouts/_llm_gate.py through SETUP_IDS / GATE_IDS — do not fork them, do not create a gate-specific copy, and do not restyle equivalent fields again in Phase 6. The gate inherits whatever these builders produce.",
    "Add an Effort select beside the model field inside `model_field` (or immediately adjacent within the same shared builder), so both the setup wizard and the gate inherit it together. Use dmc.Select with the existing `mono` class on its displayed value, and populate its options from llm_selection.py's offered-effort-values function built in Phase 4, keyed on the currently resolved model.",
    "Wire the Effort select's read and write through llm_selection.py's single (model, effort) read/write path — in the setup wizard it sets the project DEFAULT effort in the prefs store, alongside the default provider and model. Do not add a parallel store key or a second write path.",
    "Repopulate the Effort select's options whenever the resolved model changes, so the offered values always match what the newly resolved model supports. Default the selection to 'default' when no effort has been chosen.",
    "Keep the stepper, but render it compactly using the shared step-row renderer extracted into src/spec4/layouts/_shared.py in Phase 1 — do not reimplement the active/complete/dimmed marking in _setup.py.",
    "Give each step exactly one filled primary button: Connect on the provider/key step, then Continue. Render 'Clear saved credentials' as a neutral outline in the warn tone taken from the theme — never via a `color` prop on the component (D-LR2). Render the within-wizard Back as a neutral outline with no directional glyph in its label.",
    "Remove the `btn-setup-back-to-dir` button that returns to the directory picker, together with its callback in src/spec4/callbacks/. The status bar's path control provides that navigation. The specification's success criteria require that no button in the wizard returns to the directory picker.",
    "Update tests/test_callback_co_presence.py to remove `btn-setup-back-to-dir` from the setup screen's enumerated ids in the same change as the button and callback removal. Also check tests/test_agent_llm_selection.py and any test_setup test module for references to that id and update them.",
    "Cut vertical spacing across the wizard and remove any remaining kicker labels, emoji, and card hover effects, matching the density of the already-reworked shell.",
    "Add a test asserting the setup wizard renders no button with id `btn-setup-back-to-dir` and that no action in the wizard routes to the directory picker.",
    "Add a test asserting each step renders exactly one filled-primary button, and that Clear saved credentials and the within-wizard Back are neutral outlines with no directional glyph in the Back label.",
    "Add a test asserting the wizard's model step renders an Effort select whose options for an unseeded provider are exactly 'default', 'low', 'medium', 'high', and that selecting a value writes the default effort through llm_selection.py's single path into the prefs store.",
    "Add a test asserting the never-stored notice and the connected-provider notice each render as a single dimmed text line and not as an alert component, and that no free-tier notice renders at all.",
    "Add a test asserting the setup wizard's step indicator is produced by the shared renderer from layouts/_shared.py.",
    "Reference .spec4/v2/design/mock.html's setup-view screen for the intended step-indicator density, the dimmed helper-line treatment, and the model/effort field pairing."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "The shared-builder rule is the crux of this phase and the easiest thing to get wrong: an AI coder that restyles the setup screen by writing new field markup inline — rather than editing provider_key_fields / model_field — produces a gate that silently keeps the old look and no longer shares a definition, which the specification explicitly forbids. Separately, removing btn-setup-back-to-dir is a three-place change (button, callback, co-presence test) and leaving any one behind breaks the suite: a stale callback Input whose component is gone fires against a missing id.",
    "mitigation_strategy": "Make the field restyle an edit to the two named builder functions only, then confirm by rendering the gate (Phase 6's screen) and observing it already picked up the new field styling before writing any gate code. For the button removal, do all three edits — layout, callback, test entry — in one commit-sized change as the change_risks mitigation hint prescribes, then run `uv run pytest` immediately. Keep every SETUP_IDS entry other than the removed button untouched, and diff the id set before and after to prove nothing else moved."
  },
  "verification": "`uv run pytest` passes, including the updated tests/test_callback_co_presence.py with `btn-setup-back-to-dir` removed, plus the new no-return-to-picker, one-primary-per-step, dimmed-notices, shared-stepper, and Effort-select tests. `uv run mypy` (strict) is clean. Run `uv run python src/spec4/app.py`, open the setup wizard: each step shows one short title with no explanatory paragraph, the key field carries one dimmed line beneath it, the model select carries one dimmed connected line above it, no free-tier warning appears, no button returns to the directory picker, and an Effort select sits beside the model with values matching the resolved model. Every step shows exactly one filled-primary action in the single accent colour, with Clear saved credentials and Back as neutral outlines (nfr_a_single_accent_color_and_consistent_low_chrome_visual_language_across_every_screen__with_no_exceptions). The entered credential remains in the browser prefs store only (nfr_provider_credentials_remain_visible_only_to_the_user_s_own_browser_and_are_never_transmitted_elsewhere_or_written_to_disk).",
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

# Phase 5 of 7: Setup Wizard Register — Terse Three-Step Setup and the Default Effort Select

Bring the three-step setup wizard into the dev-tool register — one short title per step, alerts reduced to single dimmed lines, the free-tier notice and the return-to-picker button removed, one filled primary per step — and add the default Effort select beside the model field. The shared provider/key/model field builders are restyled here once, so the gate panel inherits them in Phase 6.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Setup Wizard Register — product feature — introduced in this phase

*Scope for this phase: Implements the feature in full, including restyling the shared provider_key_fields / model_field builders that the gate inherits in Phase 6.*

Presents the existing three-step setup in the same terse developer-tool style, dropping explanatory prose and alert-style notices while keeping every field and step working exactly as before.

**Invocation**

- Trigger: Setup is opened for an unconfigured provider, or the user revisits an existing step.

**Inputs**

- `provider_choice` (text, required) — The provider being configured.
- `key_entry` (text, required) — The credential entered for the provider.
- `model_choice` (text, required) — The default model selected for the provider.

**Outputs**

- Primary: The reworked three-step setup.
- Format: A compact step indicator with one short title and one primary action per step.
- Schema notes: The never-stored-outside-your-system notice becomes one dimmed line under the key entry; the connected-provider notice becomes one dimmed line above the model choice; the free-tier notice is removed.

**Success criteria**

- Each step keeps its fields, identifiers, and validation exactly as before
- Each step shows exactly one primary action (Connect, then Continue)
- Clearing saved credentials is a neutral, warning-toned action
- The within-wizard back action has no directional mark
- No action in the wizard returns to the directory picker

**Failure modes**

- Removing prose accidentally removes needed guidance (likelihood: low) — mitigation: Keep the single dimmed line carrying the essential notice
- A step's validation regresses during the visual rework (likelihood: low) — mitigation: Keep field identifiers and validation logic untouched

- depends on: development_tool_shell (build these no later than `setup_wizard_register`)
- entities: Provider, Credential, Model, SetupStep

### Per-Agent Effort — product feature — extended in this phase

*Scope for this phase: Adds the default Effort select to the wizard's model step, reading and writing through llm_selection.py from Phase 4; the gate's own Effort select and the model-name effort suffixes land in Phase 6.*

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

### UI surfaces for this phase (from the design)

- **`Agent Rows`** [non_ai]
  - screens: project-view
  - inputs: action button per agent: Start, Continue and Required are filled green (one variant); Modify a neutral outline with green text; Needs Update a warn outline; Not Ready a disabled outline. Activating a button routes to that agent as today; Continue resumes an in-progress conversation
  - output: Seven rows in pipeline order: agent, produced artifact, last model (with effort when not default), tokens in/out, one action
  - states: Start, Continue, Required, Modify, Needs Update, Not Ready (disabled), not run (blank model/tokens)
  - reads: Agent, Model, Effort, TokenCount, RunState
  - writes: RunState
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
- **`Model & Status Line`** [non_ai]
  - screens: chat-view
  - inputs: change
  - output: Model chip with effort when not default, and the run status line
  - states: idle, replying
  - reads: Model, Effort, RunProgress
  - after (advisory UI ordering): Composer
- **`Setup Stepper`** [non_ai]
  - screens: setup-view
  - output: Plain-text 'Provider · Model · Search' row with the active step marked like the active nav item
  - states: step 1, step 2 active, step 3
  - reads: SetupStep
  - after (advisory UI ordering): Status Bar & Nav
- **`Default Model Panel`** [non_ai]
  - screens: setup-view
  - inputs: Model select, Effort select
  - output: The default model and effort for the project, with one dimmed connection line and one dimmed effort-scope line
  - states: connected, effort default, effort chosen, model without effort support (Effort shows only "default", disabled)
  - reads: Model, Effort, Provider
  - writes: Model, Effort
  - after (advisory UI ordering): Setup Stepper
- **`Setup Button Row`** [non_ai]
  - screens: setup-view
  - inputs: Back, Continue
  - output: Step navigation with exactly one primary action
  - states: idle
  - reads: SetupStep
  - writes: SetupStep
  - after (advisory UI ordering): Default Model Panel
- **`Setup Steps 1 and 3 (not drawn)`** [non_ai]
  - screens: setup-view
  - inputs: Step 1: Provider select; API key field (masked) with one dimmed line beneath, 'Stored in this browser only, never on the server or disk'; checkbox 'Remember provider and keys in this browser'; button row: Back (outline) at left, Clear saved credentials (warn outline) and Connect (filled) at right, Step 3: the existing web-search provider and key fields, same panel and field style as step 2; button row: Back (outline), Finish (filled)
  - output: Same panel, stepper and button-row pattern as the drawn step 2: one-line title, at most one dimmed notice line, one filled primary per step. No explanatory paragraphs, no alerts, no free-tier warning, no button that leaves the wizard for the directory picker
  - states: step 1 active, step 3 active, connected (dimmed 'Connected to <provider>' line above the model select)
  - reads: Provider, Credential, Model, Effort
  - writes: Provider, Credential, Model, Effort
  - after (advisory UI ordering): Setup Stepper

## Tech Stack

**Dependencies:**

- dash
- dash-mantine-components
- litellm
- pytest

**Configurations:** No new configuration. The default provider, model, and effort live in the prefs dcc.Store (localStorage) and are read via callback State; the BYOK credential stays client-side only and never reaches the server or disk. Styling lands in src/spec4/assets/v3.css. Effort values come from llm_selection.py's offered-values function built in Phase 4.

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- usage_records (persistence): per-round usage/cost rollup; deliberately excluded from the artifact dependency graph and never marked needs-update; now also the durable record of which reasoning effort was actually used per call, including fallback-from-rejected-value outcomes — serves `per_agent_effort`
- session_store (persistence) — serves `per_agent_effort`
- prefs_store (persistence) — serves `per_agent_effort`, `setup_wizard_register`

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

1. In src/spec4/layouts/_setup.py, reduce each of the three steps' titles to one short line and delete the explanatory paragraphs beneath them. Keep every field, every id in SETUP_IDS, and every validation rule exactly as they are — the specification's success criteria require fields, identifiers, and validation to be unchanged.
2. Replace the 'your key is never stored outside your system' alert with a single dimmed dmc.Text line directly under the key field. Delete the alert component itself; the fact survives as one dimmed line.
3. Replace the 'Connected to X' alert with a single dimmed dmc.Text line directly above the model select. Delete the alert component.
4. Delete the Google free-tier warning entirely — it does not survive as a dimmed line.
5. Restyle the shared field builders `provider_key_fields` and `model_field` in _setup.py ONCE, here. These are shared with src/spec4/layouts/_llm_gate.py through SETUP_IDS / GATE_IDS — do not fork them, do not create a gate-specific copy, and do not restyle equivalent fields again in Phase 6. The gate inherits whatever these builders produce.
6. Add an Effort select beside the model field inside `model_field` (or immediately adjacent within the same shared builder), so both the setup wizard and the gate inherit it together. Use dmc.Select with the existing `mono` class on its displayed value, and populate its options from llm_selection.py's offered-effort-values function built in Phase 4, keyed on the currently resolved model.
7. Wire the Effort select's read and write through llm_selection.py's single (model, effort) read/write path — in the setup wizard it sets the project DEFAULT effort in the prefs store, alongside the default provider and model. Do not add a parallel store key or a second write path.
8. Repopulate the Effort select's options whenever the resolved model changes, so the offered values always match what the newly resolved model supports. Default the selection to 'default' when no effort has been chosen.
9. Keep the stepper, but render it compactly using the shared step-row renderer extracted into src/spec4/layouts/_shared.py in Phase 1 — do not reimplement the active/complete/dimmed marking in _setup.py.
10. Give each step exactly one filled primary button: Connect on the provider/key step, then Continue. Render 'Clear saved credentials' as a neutral outline in the warn tone taken from the theme — never via a `color` prop on the component (D-LR2). Render the within-wizard Back as a neutral outline with no directional glyph in its label.
11. Remove the `btn-setup-back-to-dir` button that returns to the directory picker, together with its callback in src/spec4/callbacks/. The status bar's path control provides that navigation. The specification's success criteria require that no button in the wizard returns to the directory picker.
12. Update tests/test_callback_co_presence.py to remove `btn-setup-back-to-dir` from the setup screen's enumerated ids in the same change as the button and callback removal. Also check tests/test_agent_llm_selection.py and any test_setup test module for references to that id and update them.
13. Cut vertical spacing across the wizard and remove any remaining kicker labels, emoji, and card hover effects, matching the density of the already-reworked shell.
14. Add a test asserting the setup wizard renders no button with id `btn-setup-back-to-dir` and that no action in the wizard routes to the directory picker.
15. Add a test asserting each step renders exactly one filled-primary button, and that Clear saved credentials and the within-wizard Back are neutral outlines with no directional glyph in the Back label.
16. Add a test asserting the wizard's model step renders an Effort select whose options for an unseeded provider are exactly 'default', 'low', 'medium', 'high', and that selecting a value writes the default effort through llm_selection.py's single path into the prefs store.
17. Add a test asserting the never-stored notice and the connected-provider notice each render as a single dimmed text line and not as an alert component, and that no free-tier notice renders at all.
18. Add a test asserting the setup wizard's step indicator is produced by the shared renderer from layouts/_shared.py.
19. Reference .spec4/v2/design/mock.html's setup-view screen for the intended step-indicator density, the dimmed helper-line treatment, and the model/effort field pairing.

## Risk Assessment

**Potential bottlenecks:**

The shared-builder rule is the crux of this phase and the easiest thing to get wrong: an AI coder that restyles the setup screen by writing new field markup inline — rather than editing provider_key_fields / model_field — produces a gate that silently keeps the old look and no longer shares a definition, which the specification explicitly forbids. Separately, removing btn-setup-back-to-dir is a three-place change (button, callback, co-presence test) and leaving any one behind breaks the suite: a stale callback Input whose component is gone fires against a missing id.

**Mitigation strategy:**

Make the field restyle an edit to the two named builder functions only, then confirm by rendering the gate (Phase 6's screen) and observing it already picked up the new field styling before writing any gate code. For the button removal, do all three edits — layout, callback, test entry — in one commit-sized change as the change_risks mitigation hint prescribes, then run `uv run pytest` immediately. Keep every SETUP_IDS entry other than the removed button untouched, and diff the id set before and after to prove nothing else moved.

## Verification

`uv run pytest` passes, including the updated tests/test_callback_co_presence.py with `btn-setup-back-to-dir` removed, plus the new no-return-to-picker, one-primary-per-step, dimmed-notices, shared-stepper, and Effort-select tests. `uv run mypy` (strict) is clean. Run `uv run python src/spec4/app.py`, open the setup wizard: each step shows one short title with no explanatory paragraph, the key field carries one dimmed line beneath it, the model select carries one dimmed connected line above it, no free-tier warning appears, no button returns to the directory picker, and an Effort select sits beside the model with values matching the resolved model. Every step shows exactly one filled-primary action in the single accent colour, with Clear saved credentials and Back as neutral outlines (nfr_a_single_accent_color_and_consistent_low_chrome_visual_language_across_every_screen__with_no_exceptions). The entered credential remains in the browser prefs store only (nfr_provider_credentials_remain_visible_only_to_the_user_s_own_browser_and_are_never_transmitted_elsewhere_or_written_to_disk).

**Non-functional acceptance** (deterministic, from the stack spec):

- `nfr_cost_and_token_figures_stay_accurate_and_reflect_the_latest_completed_run__never_showing_an_unknown_cost_as_zero`: Cost and token figures stay accurate and reflect the latest completed run, never showing an unknown cost as zero — delivered by usage_records


## References

- [Dash](https://dash.plotly.com/)
- [Dash Mantine Components — Select](https://www.dash-mantine-components.com/components/select)
- [Dash Mantine Components](https://www.dash-mantine-components.com)
- [LiteLLM reasoning_effort / reasoning content](https://docs.litellm.ai/docs/reasoning_content)
- [pytest](https://docs.pytest.org/)
