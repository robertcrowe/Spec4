---
{
  "phase_number": 7,
  "total_phases": 7,
  "phase_title": "Designer Wizard Register — Plain-Text Step Row and Prose Removal",
  "phase_summary": "Bring the seven-step Designer wizard into the dev-tool register: delete the intro paragraph, the usage accordion, the disclaimer box and the approved alert down to single dimmed lines, replace the dmc.Stepper with the shared plain-text step row, reduce the upload zones to dashed outlines with one dimmed line, strip glyphs from buttons, and remove the duplicated back-to-project button. The stores, clientside progress painter, preview, cost strip, and retry behaviour are untouched, completing the register rollout.",
  "features": [
    {
      "id": "designer_wizard_register",
      "role": "introduced",
      "scope_note": "Implements the feature in full."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "dash",
      "dash-mantine-components",
      "pytest"
    ],
    "configurations": "No new configuration. The designer-session-store and mock-stream-buffer dcc.Stores and the clientside progress painter are untouched. Upload-zone and dimmed-line styling lands in src/spec4/assets/v3.css. The generated mock is written to .spec4/v{N}/design/mock.html as today."
  },
  "instructions": [
    "In src/spec4/layouts/designer.py, delete the wizard's introductory paragraph and the 'How to use Designer' accordion outright. Neither survives in any form.",
    "Delete the `_MOCK_DISCLAIMER` alert box and re-render the look-and-feel-reference-only fact as a single dimmed dmc.Text line above the preview.",
    "Delete the 'Mock approved and saved' alert and re-render that fact as a single dimmed dmc.Text line.",
    "Give each `_stepN_content` function at most one line of instruction above its controls, in place of whatever explanatory prose it carries today. Every step keeps its fields, ids, and behaviour exactly as they are.",
    "Replace the `dmc.Stepper` with a plain-text step row built from the shared active/complete/dimmed renderer in src/spec4/layouts/_shared.py extracted in Phase 1 — the same renderer the chat frame's `_agent_status_bar` uses. No circular markers, no check icons; the active step is marked the way the active nav item is, completed steps at full weight, later steps dimmed.",
    "`render_designer_step` currently writes to `designer-stepper.active`. Either keep that id and that property on the new plain-text row so the existing Output continues to resolve, or change the callback's Output to the new row's id and property in src/spec4/callbacks/designer.py — whichever you choose, do it in THIS phase, in the same change as the stepper replacement. Do not leave an Output pointing at a component or property that no longer exists.",
    "Restyle the screenshot and reference-image upload zones as a 1px dashed outline containing one dimmed line of text, in src/spec4/assets/v3.css. Keep the upload components' ids and their file-handling callbacks unchanged.",
    "Give each step exactly one filled primary button (Start, Next, Generate, Approve, Regenerate, Continue to StackAdvisor as applicable to that step). Render Refine and Cancel as neutral outlines, and Start Over as a neutral outline in the warn tone taken from the theme — never via a `color` prop (D-LR2).",
    "Remove the ↺ and → glyphs from every step button label, leaving the plain word.",
    "Remove the Designer wizard's '← Back' button that returns to the project view, together with its callback in src/spec4/callbacks/designer.py — the status bar's Project link is the route back. The within-wizard Back and Cancel buttons STAY, as neutral outlines.",
    "Update tests/test_callback_co_presence.py to remove the back-to-project button's id from the Designer screen's enumerated ids in the same change as the button and callback removal.",
    "Do not touch the `designer-session-store` or `mock-stream-buffer` dcc.Stores, the clientside progress painter, the preview iframe, the fullscreen row (including the `#mock-fullscreen-btn` id the clientside mock viewer targets), the cost strip, or the retry panel — all keep working exactly as they do today.",
    "Cut vertical spacing across the wizard to match the density of the already-reworked shell, and remove any remaining emoji, kicker labels, or card hover effects.",
    "Add a test asserting the Designer wizard renders no dmc.Stepper and that its step row is produced by the shared renderer from layouts/_shared.py, with exactly one step marked active.",
    "Add a test asserting the wizard renders no accordion and no alert component, and that the look-and-feel disclaimer and the approved notice each render as a single dimmed text line.",
    "Add a test asserting each step renders exactly one filled-primary button, with Refine, Cancel, and the within-wizard Back as neutral outlines, and that no button label contains ↺ or →.",
    "Add a test asserting the back-to-project button id is absent from the Designer layout while the within-wizard Back and Cancel ids are still present.",
    "Add a test asserting `render_designer_step`'s Output resolves against a component actually present in the rendered Designer layout, so the stepper replacement cannot leave a dangling Output.",
    "Run the Designer wizard end to end against a real project and confirm the preview iframe, the fullscreen view, the cost strip, and the retry panel all still work, and that the generated mock is still written to .spec4/v{N}/design/mock.html.",
    "Reference .spec4/v2/design/mock.html's designer-view screen for the intended step-row rendering, upload-zone outline, and button emphasis.",
    "As the final step of this phase, run `touch .spec4/v2/IMPLEMENTED`."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "The stepper swap is the sharp edge: `render_designer_step` outputs to `designer-stepper.active`, a dmc.Stepper property that a plain-text row does not have, so replacing the component without reconciling the Output leaves a callback firing at a property that no longer exists — a failure that surfaces at runtime on the Designer route rather than at import. Separately, the wizard shares the screen with a clientside progress painter and DOM-selector-dependent controls (#mock-fullscreen-btn), and a broad restyle can rename or reparent those out from under the JS. Removing the back-to-project button is again a three-place change.",
    "mitigation_strategy": "Decide the stepper Output reconciliation before writing any layout code — keep the `designer-stepper` id on the new row with a compatible property, or change the Output — and add the dangling-Output test that proves the choice landed. Leave every id the clientside code targets exactly as it is; restyle via CSS classes rather than restructuring those elements. Do the back-button removal across layout, callback, and co-presence test in one change per the change_risks mitigation hint, then run `uv run pytest`. Finish with a manual end-to-end Designer run, since the preview, cost strip, and retry are not fully covered by the pytest suite."
  },
  "verification": "`uv run pytest` passes, including the updated tests/test_callback_co_presence.py and the new no-stepper, shared-step-row, no-accordion/no-alert, one-primary-per-step, no-glyph, back-button-absent, and Output-resolves tests. `uv run ruff check src/ tests/` is clean and `uv run mypy` (strict) passes. Run `uv run python src/spec4/app.py` and walk the Designer wizard end to end: the step row reads as plain text with no circles or check icons and one step marked active, each step shows at most one instruction line and exactly one filled-primary button, the upload zones are dashed outlines with one dimmed line, the disclaimer and approved notices are single dimmed lines, no back-to-project button appears while within-wizard Back and Cancel remain as outlines, and the preview, fullscreen view, cost strip, and retry all still work. With this screen done, every screen in the app now shares the single accent colour and low-chrome register with none left needing it (nfr_a_single_accent_color_and_consistent_low_chrome_visual_language_across_every_screen__with_no_exceptions, nfr_the_visual_register_rework_is_complete_after_this_round__with_no_screens_left_needing_it). Finally, `.spec4/v2/IMPLEMENTED` exists.",
  "references": [
    {
      "standard": "Dash",
      "url": "https://dash.plotly.com/"
    },
    {
      "standard": "Dash Mantine Components — Stepper",
      "url": "https://www.dash-mantine-components.com/components/stepper"
    },
    {
      "standard": "Dash Mantine Components",
      "url": "https://www.dash-mantine-components.com"
    },
    {
      "standard": "Dash clientside callbacks",
      "url": "https://dash.plotly.com/clientside-callbacks"
    },
    {
      "standard": "pytest",
      "url": "https://docs.pytest.org/"
    }
  ]
}
---

# Phase 7 of 7: Designer Wizard Register — Plain-Text Step Row and Prose Removal

Bring the seven-step Designer wizard into the dev-tool register: delete the intro paragraph, the usage accordion, the disclaimer box and the approved alert down to single dimmed lines, replace the dmc.Stepper with the shared plain-text step row, reduce the upload zones to dashed outlines with one dimmed line, strip glyphs from buttons, and remove the duplicated back-to-project button. The stores, clientside progress painter, preview, cost strip, and retry behaviour are untouched, completing the register rollout.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Designer Wizard Register — product feature — introduced in this phase

*Scope for this phase: Implements the feature in full.*

Brings the seven-step Designer flow in line with the developer-tool look — trimming explanatory text and decorative step markers — while keeping every step, field, and outcome the same.

**Invocation**

- Trigger: The Designer agent's gate is passed and its multi-step flow begins.

**Inputs**

- `current_step_index` (number, required) — Which of the seven steps is active.
- `uploaded_reference_material` (file, optional) — Screenshots or reference images supplied for the design.
- `generated_mock_state` (text, required) — Whether a mock has been generated, approved, or needs regeneration.

**Outputs**

- Primary: The reworked seven-step flow.
- Format: A plain-text step row plus one instruction line and one primary action per step.
- Schema notes: Upload zones are a plain dashed outline with one dimmed line of text; approval and disclaimer notices are single dimmed lines, not alerts.

**Success criteria**

- The step row renders as plain text with no circular markers or check marks; the active step is marked the same way as the active nav item, completed steps at full emphasis, later steps dimmed
- Each step shows at most one instruction line and exactly one primary action
- The introductory paragraph and usage explanation are gone
- The look-and-feel disclaimer and the approval notice each render as a single dimmed line
- The live preview, its full-view option, the cost summary, and the retry option all keep working exactly as before

**Failure modes**

- Removing the usage explanation leaves new users confused about a step's purpose (likelihood: low) — mitigation: Keep the one-line instruction on every step
- The step row becomes ambiguous about which step is active once icons are removed (likelihood: low) — mitigation: Reuse the exact active/complete/dimmed marking used in the agent progress row

- depends on: development_tool_shell, gate_card_register (build these no later than `designer_wizard_register`)
- entities: DesignStep, DesignMock, ReferenceMaterial, Cost

### UI surfaces for this phase (from the design)

- **`Designer Stepper`** [non_ai]
  - screens: designer-view
  - output: Plain-text row of the six stepper labels (No-UI check · Start / Resume · Preferences · Screenshots · Generate · Preview; the refine step reuses Preview's label), active marked like the active nav item, completed at full emphasis, later steps dimmed. Replaces dmc.Stepper; no circles, no check icons
  - states: completed step, active step, later step
  - reads: DesignStep
  - after (advisory UI ordering): Agent Pipeline Row
- **`Designer Button Row`** [non_ai]
  - screens: designer-view
  - inputs: Back, Next
  - output: Step navigation with exactly one primary action
  - states: idle
  - reads: DesignStep
  - writes: DesignStep
  - after (advisory UI ordering): Design Preferences Entry
- **`Designer Steps other than Preferences (not drawn)`** [non_ai]
  - screens: designer-view
  - inputs: No-UI check: one instruction line; Continue (filled) / Skip Designer (outline), Start / Resume: one instruction line; Create new design (filled) and, when a prior mock exists, Carry forward (outline) and Start over (warn outline); Skip Designer (outline), Screenshots: one instruction line; the screenshot and reference-image upload zones as 1px dashed outlines with one dimmed line of text; each uploaded image as a row with its annotation input and Remove (outline); Back (outline), Generate (filled), Generate: the progress bar and status line as on the chat frame; Cancel (outline), Preview: Full Screen (outline) at right above the iframe; one dimmed line 'Look-and-feel reference only; not the final UI' replacing the yellow disclaimer; the iframe unchanged; run cost strip; on approval one dimmed line 'Mock approved and saved'; button row: Continue to StackAdvisor (filled), Refine (outline), Start Over (warn outline), Refine: one instruction line; refine textarea; the same image rows with annotation inputs; Regenerate (filled), Cancel (outline)
  - output: Every step follows the drawn Preferences step: stepper row, one instruction line at most, controls, one filled primary. No intro paragraph, no 'How to use Designer' accordion, no Back button that leaves the wizard for the project view (the status bar's Project link does that), no ↺ or → glyphs
  - states: no-ui check, start/resume (new), start/resume (prior mock exists), screenshots, generating, preview, approved, refine
  - reads: DesignStep, DesignMock, ReferenceMaterial, RunRecord
  - writes: DesignMock, ReferenceMaterial
  - after (advisory UI ordering): Designer Stepper
The following surface(s) realize the AI capability `designer_wizard_register` — one unit of work; the surfaces are views onto it:
- **`Design Preferences Entry`** [ai]
  - screens: designer-view
  - inputs: preferences textarea (six lines)
  - output: The stored preference text used when generating the mock
  - states: empty, filled, generating
  - reads: DesignMock, ReferenceMaterial
  - writes: DesignMock
  - after (advisory UI ordering): Designer Stepper

## Tech Stack

**Dependencies:**

- dash
- dash-mantine-components
- pytest

**Configurations:** No new configuration. The designer-session-store and mock-stream-buffer dcc.Stores and the clientside progress painter are untouched. Upload-zone and dimmed-line styling lands in src/spec4/assets/v3.css. The generated mock is written to .spec4/v{N}/design/mock.html as today.

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

1. In src/spec4/layouts/designer.py, delete the wizard's introductory paragraph and the 'How to use Designer' accordion outright. Neither survives in any form.
2. Delete the `_MOCK_DISCLAIMER` alert box and re-render the look-and-feel-reference-only fact as a single dimmed dmc.Text line above the preview.
3. Delete the 'Mock approved and saved' alert and re-render that fact as a single dimmed dmc.Text line.
4. Give each `_stepN_content` function at most one line of instruction above its controls, in place of whatever explanatory prose it carries today. Every step keeps its fields, ids, and behaviour exactly as they are.
5. Replace the `dmc.Stepper` with a plain-text step row built from the shared active/complete/dimmed renderer in src/spec4/layouts/_shared.py extracted in Phase 1 — the same renderer the chat frame's `_agent_status_bar` uses. No circular markers, no check icons; the active step is marked the way the active nav item is, completed steps at full weight, later steps dimmed.
6. `render_designer_step` currently writes to `designer-stepper.active`. Either keep that id and that property on the new plain-text row so the existing Output continues to resolve, or change the callback's Output to the new row's id and property in src/spec4/callbacks/designer.py — whichever you choose, do it in THIS phase, in the same change as the stepper replacement. Do not leave an Output pointing at a component or property that no longer exists.
7. Restyle the screenshot and reference-image upload zones as a 1px dashed outline containing one dimmed line of text, in src/spec4/assets/v3.css. Keep the upload components' ids and their file-handling callbacks unchanged.
8. Give each step exactly one filled primary button (Start, Next, Generate, Approve, Regenerate, Continue to StackAdvisor as applicable to that step). Render Refine and Cancel as neutral outlines, and Start Over as a neutral outline in the warn tone taken from the theme — never via a `color` prop (D-LR2).
9. Remove the ↺ and → glyphs from every step button label, leaving the plain word.
10. Remove the Designer wizard's '← Back' button that returns to the project view, together with its callback in src/spec4/callbacks/designer.py — the status bar's Project link is the route back. The within-wizard Back and Cancel buttons STAY, as neutral outlines.
11. Update tests/test_callback_co_presence.py to remove the back-to-project button's id from the Designer screen's enumerated ids in the same change as the button and callback removal.
12. Do not touch the `designer-session-store` or `mock-stream-buffer` dcc.Stores, the clientside progress painter, the preview iframe, the fullscreen row (including the `#mock-fullscreen-btn` id the clientside mock viewer targets), the cost strip, or the retry panel — all keep working exactly as they do today.
13. Cut vertical spacing across the wizard to match the density of the already-reworked shell, and remove any remaining emoji, kicker labels, or card hover effects.
14. Add a test asserting the Designer wizard renders no dmc.Stepper and that its step row is produced by the shared renderer from layouts/_shared.py, with exactly one step marked active.
15. Add a test asserting the wizard renders no accordion and no alert component, and that the look-and-feel disclaimer and the approved notice each render as a single dimmed text line.
16. Add a test asserting each step renders exactly one filled-primary button, with Refine, Cancel, and the within-wizard Back as neutral outlines, and that no button label contains ↺ or →.
17. Add a test asserting the back-to-project button id is absent from the Designer layout while the within-wizard Back and Cancel ids are still present.
18. Add a test asserting `render_designer_step`'s Output resolves against a component actually present in the rendered Designer layout, so the stepper replacement cannot leave a dangling Output.
19. Run the Designer wizard end to end against a real project and confirm the preview iframe, the fullscreen view, the cost strip, and the retry panel all still work, and that the generated mock is still written to .spec4/v{N}/design/mock.html.
20. Reference .spec4/v2/design/mock.html's designer-view screen for the intended step-row rendering, upload-zone outline, and button emphasis.
21. As the final step of this phase, run `touch .spec4/v2/IMPLEMENTED`.

## Risk Assessment

**Potential bottlenecks:**

The stepper swap is the sharp edge: `render_designer_step` outputs to `designer-stepper.active`, a dmc.Stepper property that a plain-text row does not have, so replacing the component without reconciling the Output leaves a callback firing at a property that no longer exists — a failure that surfaces at runtime on the Designer route rather than at import. Separately, the wizard shares the screen with a clientside progress painter and DOM-selector-dependent controls (#mock-fullscreen-btn), and a broad restyle can rename or reparent those out from under the JS. Removing the back-to-project button is again a three-place change.

**Mitigation strategy:**

Decide the stepper Output reconciliation before writing any layout code — keep the `designer-stepper` id on the new row with a compatible property, or change the Output — and add the dangling-Output test that proves the choice landed. Leave every id the clientside code targets exactly as it is; restyle via CSS classes rather than restructuring those elements. Do the back-button removal across layout, callback, and co-presence test in one change per the change_risks mitigation hint, then run `uv run pytest`. Finish with a manual end-to-end Designer run, since the preview, cost strip, and retry are not fully covered by the pytest suite.

## Verification

`uv run pytest` passes, including the updated tests/test_callback_co_presence.py and the new no-stepper, shared-step-row, no-accordion/no-alert, one-primary-per-step, no-glyph, back-button-absent, and Output-resolves tests. `uv run ruff check src/ tests/` is clean and `uv run mypy` (strict) passes. Run `uv run python src/spec4/app.py` and walk the Designer wizard end to end: the step row reads as plain text with no circles or check icons and one step marked active, each step shows at most one instruction line and exactly one filled-primary button, the upload zones are dashed outlines with one dimmed line, the disclaimer and approved notices are single dimmed lines, no back-to-project button appears while within-wizard Back and Cancel remain as outlines, and the preview, fullscreen view, cost strip, and retry all still work. With this screen done, every screen in the app now shares the single accent colour and low-chrome register with none left needing it (nfr_a_single_accent_color_and_consistent_low_chrome_visual_language_across_every_screen__with_no_exceptions, nfr_the_visual_register_rework_is_complete_after_this_round__with_no_screens_left_needing_it). Finally, `.spec4/v2/IMPLEMENTED` exists.

**Non-functional acceptance** (deterministic, from the stack spec):

- `nfr_a_single_accent_color_and_consistent_low_chrome_visual_language_across_every_screen__with_no_exceptions`: A single accent color and consistent low-chrome visual language across every screen, with no exceptions — project-wide acceptance
- `nfr_provider_credentials_remain_visible_only_to_the_user_s_own_browser_and_are_never_transmitted_elsewhere_or_written_to_disk`: Provider credentials remain visible only to the user's own browser and are never transmitted elsewhere or written to disk — project-wide acceptance
- `nfr_the_status_bar_s_round__provider__model__and_version_stay_fully_legible_regardless_of_window_width`: The status bar's round, provider, model, and version stay fully legible regardless of window width — project-wide acceptance
- `nfr_the_visual_register_rework_is_complete_after_this_round__with_no_screens_left_needing_it`: The visual register rework is complete after this round, with no screens left needing it — project-wide acceptance


## References

- [Dash](https://dash.plotly.com/)
- [Dash Mantine Components — Stepper](https://www.dash-mantine-components.com/components/stepper)
- [Dash Mantine Components](https://www.dash-mantine-components.com)
- [Dash clientside callbacks](https://dash.plotly.com/clientside-callbacks)
- [pytest](https://docs.pytest.org/)
