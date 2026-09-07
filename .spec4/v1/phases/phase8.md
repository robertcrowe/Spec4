---
{
  "phase_number": 8,
  "total_phases": 8,
  "phase_title": "Run-Cost Strip, Chat-Frame Open Links, and Round Close-Out",
  "phase_summary": "Close the round: render a completed run's cost through the same three-line renderer the project view uses, retire the old cost card while preserving the ids its tests assert, add an Open button beside every Download in the chat frame's action row so every artifact reference leads into the Artifact View, and mark the round implemented.",
  "features": [
    {
      "id": "chat_frame_register",
      "role": "extended",
      "scope_note": "The completed-run cost strip and the Open buttons in the action row land here, completing this feature."
    },
    {
      "id": "artifact_links",
      "role": "extended",
      "scope_note": "The chat frame's Open buttons land here, completing the feature — every Download in the action row now has an Open beside it."
    },
    {
      "id": "round_cost",
      "role": "introduced",
      "scope_note": "Only this round's change lands here — the renderer in _round_cost.py becomes the single shared cost presentation and _shared.cost_summary_card is retired; the project view's round-cost figures, labelling rules, and unpriced-call handling are already built and carry forward unchanged."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "dash",
      "dash-mantine-components",
      "pytest",
      "playwright",
      "ruff",
      "mypy"
    ],
    "configurations": "No new environment variables. Cost figures come from project_manager.cost_summary reading the round's usage.json; usage.json remains outside the artifact dependency graph and is never marked needs-update."
  },
  "instructions": [
    "Read .spec4/v1/design/mock.html for the cost strip's three-line form and the Open button's placement beside Download. Lane assignments, where the mock shows artifacts, come exclusively from _round_tree.ROUND_ARTIFACTS, never from the mock's sample data, which misfiles deployment-plan.md.",
    "In src/spec4/layouts/_chat.py, replace the completed-run cost card with a call to the rendering function in src/spec4/layouts/_round_cost.py, passing figures obtained from project_manager.cost_summary. Both the project view and the chat frame must now source their cost presentation from that one renderer, which is the mitigation the attached specification's failure modes require for the two presentations diverging.",
    "Retire cost_summary_card from src/spec4/layouts/_shared.py: remove the helper and every call site. Preserve the component ids that tests/test_cost_summary.py asserts by having the _round_cost.py renderer emit those same ids, so the existing test contract holds without renaming.",
    "Update tests/test_cost_summary.py only where it references the retired helper by name; its id assertions must continue to pass unchanged against the _round_cost.py output.",
    "Add a test asserting the chat frame's completed-run cost and the project view's round cost are produced by the same renderer function and carry identical labelling for the same usage input, including the 'estimated' label and the naming of calls that could not be priced.",
    "In the chat frame's action row, add an Open button beside every existing Download button, one per downloadable artifact, giving each a new id of the form btn-open-<artifact key> rather than renaming any existing Download id. Render each Open as a neutral outline with no colour set on the component (D-LR2).",
    "Wire each Open button to write that artifact's file path and its round into the session-store selection keys and set the dcc.Location pathname to '/artifacts', reusing the same selection-writing helper the round-tree link callback uses in Phase 2. Resolve the target at click time from the triggered id, not from a value captured at render.",
    "Add a test asserting that for every Download button present in the chat frame's action row there is a corresponding Open button, so the pairing cannot drift as agents are added.",
    "Add a Playwright end-to-end test that completes or loads a finished run, clicks an Open button in the action row, and asserts the Artifact View opens with that exact artifact selected and its content rendered.",
    "Add the 'artifacts' screen's Open-button ids to tests/test_callback_co_presence.py so the new controls are covered by the co-presence contract.",
    "Run `uv run ruff check src/ tests/`, `uv run ruff format src/ tests/`, and `uv run mypy src/`, fixing every finding introduced by this phase.",
    "As the final instruction of this phase, after the full test suite passes, run `touch .spec4/v1/IMPLEMENTED`."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "Retiring cost_summary_card while keeping its asserted ids is the delicate part — moving ids to a different renderer can produce duplicate ids if a call site is missed, which Dash rejects at layout validation. The Open buttons are generated per artifact, so a hard-coded list would drift from the agents that actually produce downloads. Cost labelling rules (estimated label, named unpriced calls, never a zero figure for unknown) are easy to lose in the move between renderers.",
    "mitigation_strategy": "Remove the helper and all its call sites in one pass, then start the app once — a duplicate id fails loudly at layout validation. Generate Open buttons from the same per-agent artifact mapping that already generates the Download buttons, and lock the pairing with the one-to-one test. Move the cost labelling by reusing _round_cost.py's renderer wholesale rather than reimplementing its lines, and assert identical labelling from identical input in a test."
  },
  "verification": "Run `uv run pytest` — the full suite passes, including tests/test_cost_summary.py with its original id assertions intact, the shared-renderer test, and the Download/Open pairing test. Then run `uv run python src/spec4/app.py` and confirm: a completed run shows its cost as the same three-line strip the project view uses, labelled 'estimated', with any unpriced calls named and never shown as $0.0000; every Download button in the action row has an Open button beside it; clicking an Open button lands on /artifacts with that artifact selected and rendered. Finally confirm `.spec4/v1/IMPLEMENTED` exists. Confirms nfr_the_visual_and_navigational_register_is_fully_consistent_across_every_screen_in_the_app_ (one cost renderer across screens) and nfr_viewing_or_obtaining_a_copy_of_an_artifact_works_consistently_regardless_of_round_or_file_size__without_noticeable_delay_for_typical_spec_file_sizes_.",
  "references": [
    {
      "standard": "Dash Mantine Components — Button",
      "url": "https://www.dash-mantine-components.com/components/button"
    },
    {
      "standard": "Dash pattern-matching callbacks",
      "url": "https://dash.plotly.com/pattern-matching-callbacks"
    },
    {
      "standard": "Dash URL routing (dcc.Location)",
      "url": "https://dash.plotly.com/urls"
    },
    {
      "standard": "Playwright for Python",
      "url": "https://playwright.dev/python/docs/intro"
    },
    {
      "standard": "pytest",
      "url": "https://docs.pytest.org/"
    }
  ]
}
---

# Phase 8 of 8: Run-Cost Strip, Chat-Frame Open Links, and Round Close-Out

Close the round: render a completed run's cost through the same three-line renderer the project view uses, retire the old cost card while preserving the ids its tests assert, add an Open button beside every Download in the chat frame's action row so every artifact reference leads into the Artifact View, and mark the round implemented.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Chat Frame Register — product feature — extended in this phase

*Scope for this phase: The completed-run cost strip and the Open buttons in the action row land here, completing this feature.*

Restyles the existing chat/run interaction surface to match the developer-tool register — a plain-text pipeline indicator, block-style transcript, consistent cost reporting, and outline-style secondary actions — while preserving every existing function.

**Invocation**

- Trigger: The user is on the chat frame for any agent's run.

**Inputs**

- `agent_pipeline_state` (structured data, required) — The seven agents in order along with which is active, completed, or unreachable.
- `transcript_messages` (list of items, required) — The messages exchanged during the run.
- `live_progress_signal` (structured data, required) — Elapsed time and character counters reflecting live activity.
- `turn_token_counts` (structured data, required) — Token counts for the current turn.
- `run_cost_on_completion` (structured data, optional) — The completed run's usage/cost summary.
- `retry_and_breadth_panel_state` (structured data, optional) — State needed to show retry and breadth options.

**Outputs**

- Primary: A rendered chat frame with restyled pipeline indicator, transcript, action row, composer, and progress signal.
- Format: Interactive screen
- Schema notes: Pipeline indicator lists all seven agents in order with active/completed/unreachable states; transcript is a sequence of speaker-labelled blocks; completed-run cost uses the same three-line summary as round cost.

**Success criteria**

- All prior functions remain reachable and working: pipeline indicator, transcript, progress signal, turn tokens, fast-forward with its explanatory panel, retry, breadth, downloads, continue, composer, model indicator, status line.
- The pipeline indicator shows plain text with no connecting arrows and correctly reflects active/completed/unreachable state.
- No per-agent or pipeline-level back control remains, since equivalent navigation exists via the pipeline indicator and the status strip.
- Transcript blocks show a dimmed one-word speaker label and no filled background.
- The transcript's default height is noticeably taller than before while remaining independently scrollable.
- On run completion, cost is shown in the same three-line form used elsewhere.
- Exactly one strongly emphasized action exists per row (the continue action); all others are neutral outlines, except the rescan action shown in a warning tone.
- The live-activity signal is the only moving element on the screen.
- Chars, turn-token and elapsed counters, and the model name in the model chip, render in monospace.

**Failure modes**

- Removing back controls leaves a run state unreachable from the pipeline indicator. (likelihood: medium) — mitigation: Verify every navigable state remains reachable via the pipeline indicator or status strip before removing legacy controls.
- Transcript height change breaks scroll behavior at small viewport sizes. (likelihood: low) — mitigation: Keep the transcript independently scrollable regardless of viewport size.
- The completion cost strip fails to match the round-cost presentation. (likelihood: low) — mitigation: Source both from the same cost-estimation output.

- depends on: round_cost, development_tool_shell (build these no later than `chat_frame_register`)
- entities: Agent, ChatSession, Message, UsageRecord, CostEstimate

### Artifact Links — product feature — extended in this phase

*Scope for this phase: The chat frame's Open buttons land here, completing the feature — every Download in the action row now has an Open beside it.*

Makes every artifact reference in the app clickable, so the round tree and chat outputs consistently lead into the Artifact View instead of leaving the user to hunt for files.

**Invocation**

- Trigger: The user selects a line in the round tree, or selects an open-artifact control in the chat frame's action row.

**Inputs**

- `target_file_path` (text, required) — The artifact the user wants to open.
- `target_round` (text, optional) — The round the artifact belongs to, defaulting to the current round.

**Outputs**

- Primary: Navigation to the Artifact View with the requested file pre-selected.
- Format: Screen navigation
- Schema notes: The destination always resolves to the exact file/round pairing the user selected.

**Success criteria**

- Every round-tree line opens the Artifact View at that exact file.
- Every place a copy of a file can be obtained from the chat frame also offers a way to open it in place.
- The Artifacts navigation entry is present in the app's primary navigation, positioned between Project and Settings.

**Failure modes**

- A link opens the wrong file or round after a round changes mid-session. (likelihood: medium) — mitigation: Resolve the target at the moment of selection, not at render time.
- The navigation entry is missing from a screen that should offer it. (likelihood: low) — mitigation: Keep the navigation register consistent across all screens.

- depends on: artifact_view (build these no later than `artifact_links`)
- entities: Artifact, Round, NavigationRegister

### Round Cost — product feature — introduced in this phase

*Scope for this phase: Only this round's change lands here — the renderer in _round_cost.py becomes the single shared cost presentation and _shared.cost_summary_card is retired; the project view's round-cost figures, labelling rules, and unpriced-call handling are already built and carry forward unchanged.*

Surfaces the round's running estimated cost so the user always knows what they've spent before deciding whether to continue.

**Invocation**

- Trigger: The project view is opened, or the round's usage record changes.

**Inputs**

- `round_usage_totals` (structured data, required) — Token totals and priced/unpriced call information for the current round.

**Outputs**

- Primary: A labelled estimated-cost figure with supporting token counts.
- Format: Short summary strip
- Schema notes: Three lines: labelled estimate, token totals, and any calls excluded from pricing named individually.

**Success criteria**

- The figure is always labelled as an estimate, never presented as exact.
- Any call that could not be priced is named rather than silently dropped or shown as zero.
- The total is never displayed as a zero-cost figure when some usage is unpriced.
- The figure updates whenever the underlying usage record changes.

**Failure modes**

- Unpriced usage silently ignored, making the total look lower than reality. (likelihood: medium) — mitigation: Always name excluded calls alongside the total.
- Cost shown as exactly zero when data is simply unavailable. (likelihood: medium) — mitigation: Distinguish 'no usage yet' from 'usage present but unpriced'.

- depends on: development_tool_shell (build these no later than `round_cost`)
- entities: Round, UsageRecord, CostEstimate

## Tech Stack

**Dependencies:**

- dash
- dash-mantine-components
- pytest
- playwright
- ruff
- mypy

**Configurations:** No new environment variables. Cost figures come from project_manager.cost_summary reading the round's usage.json; usage.json remains outside the artifact dependency graph and is never marked needs-update.

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- round_artifacts (persistence) — serves `artifact_links`
- usage_records (persistence): per-round usage/cost rollup; deliberately excluded from the artifact dependency graph and never marked needs-update; also now the source for the chat frame's on-completion cost strip — serves `chat_frame_register`, `round_cost`

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

1. Read .spec4/v1/design/mock.html for the cost strip's three-line form and the Open button's placement beside Download. Lane assignments, where the mock shows artifacts, come exclusively from _round_tree.ROUND_ARTIFACTS, never from the mock's sample data, which misfiles deployment-plan.md.
2. In src/spec4/layouts/_chat.py, replace the completed-run cost card with a call to the rendering function in src/spec4/layouts/_round_cost.py, passing figures obtained from project_manager.cost_summary. Both the project view and the chat frame must now source their cost presentation from that one renderer, which is the mitigation the attached specification's failure modes require for the two presentations diverging.
3. Retire cost_summary_card from src/spec4/layouts/_shared.py: remove the helper and every call site. Preserve the component ids that tests/test_cost_summary.py asserts by having the _round_cost.py renderer emit those same ids, so the existing test contract holds without renaming.
4. Update tests/test_cost_summary.py only where it references the retired helper by name; its id assertions must continue to pass unchanged against the _round_cost.py output.
5. Add a test asserting the chat frame's completed-run cost and the project view's round cost are produced by the same renderer function and carry identical labelling for the same usage input, including the 'estimated' label and the naming of calls that could not be priced.
6. In the chat frame's action row, add an Open button beside every existing Download button, one per downloadable artifact, giving each a new id of the form btn-open-<artifact key> rather than renaming any existing Download id. Render each Open as a neutral outline with no colour set on the component (D-LR2).
7. Wire each Open button to write that artifact's file path and its round into the session-store selection keys and set the dcc.Location pathname to '/artifacts', reusing the same selection-writing helper the round-tree link callback uses in Phase 2. Resolve the target at click time from the triggered id, not from a value captured at render.
8. Add a test asserting that for every Download button present in the chat frame's action row there is a corresponding Open button, so the pairing cannot drift as agents are added.
9. Add a Playwright end-to-end test that completes or loads a finished run, clicks an Open button in the action row, and asserts the Artifact View opens with that exact artifact selected and its content rendered.
10. Add the 'artifacts' screen's Open-button ids to tests/test_callback_co_presence.py so the new controls are covered by the co-presence contract.
11. Run `uv run ruff check src/ tests/`, `uv run ruff format src/ tests/`, and `uv run mypy src/`, fixing every finding introduced by this phase.
12. As the final instruction of this phase, after the full test suite passes, run `touch .spec4/v1/IMPLEMENTED`.

## Risk Assessment

**Potential bottlenecks:**

Retiring cost_summary_card while keeping its asserted ids is the delicate part — moving ids to a different renderer can produce duplicate ids if a call site is missed, which Dash rejects at layout validation. The Open buttons are generated per artifact, so a hard-coded list would drift from the agents that actually produce downloads. Cost labelling rules (estimated label, named unpriced calls, never a zero figure for unknown) are easy to lose in the move between renderers.

**Mitigation strategy:**

Remove the helper and all its call sites in one pass, then start the app once — a duplicate id fails loudly at layout validation. Generate Open buttons from the same per-agent artifact mapping that already generates the Download buttons, and lock the pairing with the one-to-one test. Move the cost labelling by reusing _round_cost.py's renderer wholesale rather than reimplementing its lines, and assert identical labelling from identical input in a test.

## Verification

Run `uv run pytest` — the full suite passes, including tests/test_cost_summary.py with its original id assertions intact, the shared-renderer test, and the Download/Open pairing test. Then run `uv run python src/spec4/app.py` and confirm: a completed run shows its cost as the same three-line strip the project view uses, labelled 'estimated', with any unpriced calls named and never shown as $0.0000; every Download button in the action row has an Open button beside it; clicking an Open button lands on /artifacts with that artifact selected and rendered. Finally confirm `.spec4/v1/IMPLEMENTED` exists. Confirms nfr_the_visual_and_navigational_register_is_fully_consistent_across_every_screen_in_the_app_ (one cost renderer across screens) and nfr_viewing_or_obtaining_a_copy_of_an_artifact_works_consistently_regardless_of_round_or_file_size__without_noticeable_delay_for_typical_spec_file_sizes_.

**Non-functional acceptance** (deterministic, from the stack spec):

- `nfr_all_artifact_reads_are_strictly_confined_to_the_current_project_s_spec_folder__with_no_other_path_ever_reachable_`: All artifact reads are strictly confined to the current project's spec folder, with no other path ever reachable. — project-wide acceptance
- `nfr_provider_keys_never_leave_the_browser_under_any_feature_in_this_round_`: Provider keys never leave the browser under any feature in this round. — project-wide acceptance
- `nfr_the_visual_and_navigational_register_is_fully_consistent_across_every_screen_in_the_app_`: The visual and navigational register is fully consistent across every screen in the app. — project-wide acceptance
- `nfr_viewing_or_obtaining_a_copy_of_an_artifact_works_consistently_regardless_of_round_or_file_size__without_noticeable_delay_for_typical_spec_file_sizes_`: Viewing or obtaining a copy of an artifact works consistently regardless of round or file size, without noticeable delay for typical spec file sizes. — project-wide acceptance


## References

- [Dash Mantine Components — Button](https://www.dash-mantine-components.com/components/button)
- [Dash pattern-matching callbacks](https://dash.plotly.com/pattern-matching-callbacks)
- [Dash URL routing (dcc.Location)](https://dash.plotly.com/urls)
- [Playwright for Python](https://playwright.dev/python/docs/intro)
- [pytest](https://docs.pytest.org/)
