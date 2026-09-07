---
{
  "phase_number": 2,
  "total_phases": 8,
  "phase_title": "Shared Round Tree — Linkable Lines via a Parameter",
  "phase_summary": "Turn the existing round tree into a single shared renderer whose lines can be links, controlled by a parameter rather than a duplicated copy. The project view passes the parameter, each line click resolves its target at the moment of selection and navigates to the Artifact View with that round/file pairing in the session store, and the existing test that asserts lines are not clickable is inverted.",
  "features": [
    {
      "id": "round_tree",
      "role": "introduced",
      "scope_note": "This round's only change to the round tree is the link parameter and the click-to-navigate behaviour; artifact ordering, lane colouring, the three-item legend, status derivation, and the usage-record needs-update exemption are already built and carry forward unchanged."
    },
    {
      "id": "artifact_links",
      "role": "extended",
      "scope_note": "Round-tree line links land here; the chat frame's Open buttons land in Phase 8."
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
    "configurations": "No new environment variables. Selected round and selected file are read from and written to the existing browser session dcc.Store keys added in Phase 1. Navigation uses the app's existing dcc.Location."
  },
  "instructions": [
    "Read .spec4/v1/design/mock.html for the intended appearance of a linked round-tree line versus a plain one. Lane assignments come exclusively from _round_tree.ROUND_ARTIFACTS, never from the mock's sample data, which misfiles deployment-plan.md.",
    "In src/spec4/layouts/_round_tree.py, add a keyword parameter to the existing tree-rendering function that switches its lines between plain text and clickable links, defaulting to the current plain-text behaviour. Render the link form from the same code path as the plain form — do not fork, copy, or duplicate the tree rendering, and do not add a second tree module.",
    "When the parameter selects the link form, give each line a pattern-matching id of the form {'type': 'round-tree-line', 'index': <artifact key>} where the artifact key is the key from _round_tree.ROUND_ARTIFACTS. For a phases/ entry that expands into multiple .md files, index each expanded file individually so a click identifies one exact file.",
    "Add an optional selected-file parameter to the same function that marks one line as the current selection using the shell's existing active-state mechanism. Set no colour on the component (D-LR2); the accent comes from the Mantine theme primary. Use the existing 'mono' class for the file paths.",
    "Update the project view to call the shared renderer with the link form enabled, so every line in the project view's round tree is clickable, as required by the attached Artifact Links specification.",
    "Add a callback in src/spec4/callbacks/ with a pattern-matching Input on {'type': 'round-tree-line', 'index': ALL} that, on click, reads the triggered id via dash.ctx.triggered_id, writes the clicked file path and its round into the session-store selection keys, and sets the dcc.Location pathname to '/artifacts'. Resolve the target from the triggered id at click time — never from a value captured when the tree was rendered — which is the mitigation the attached specification's failure modes require for a round changing mid-session.",
    "Guard the callback against the initial-call fire (prevent_initial_call=True) and against a triggered_id of None, so a page load never writes a spurious selection into the session store.",
    "Invert the assertion in tests/test_round_tree.py that currently asserts round-tree lines are NOT clickable: it must now assert that lines rendered with the link parameter enabled carry the {'type': 'round-tree-line'} pattern id, and keep a case asserting the default (unlinked) form still renders plain lines.",
    "Add a test asserting that the project view renders its tree via the shared renderer with links enabled, and that the number of linked lines equals the number of entries produced from _round_tree.ROUND_ARTIFACTS for the round under test.",
    "Run `uv run ruff check src/ tests/`, `uv run ruff format src/ tests/`, and `uv run mypy src/`, fixing every finding introduced by this phase."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "Pattern-matching ids are the most common source of silent callback failure in Dash — a mismatch between the id dict written at render time and the Input pattern produces a control that simply does nothing, with no error. The phases/ expansion means the line count is dynamic, so a hard-coded expectation in the inverted test will break as soon as a phase file is added or removed. Adding a parameter to a function the project view already calls risks a positional-argument break at existing call sites.",
    "mitigation_strategy": "Define the id dict in exactly one helper inside _round_tree.py and have both the renderer and the tests obtain ids from that helper, so render and Input can never drift. Write the inverted test to derive its expected line set from _round_tree.ROUND_ARTIFACTS and the actual phases/*.md files on disk rather than hard-coding a count. Add the new parameter as keyword-only with a default that preserves current behaviour, then update the project view call site explicitly."
  },
  "verification": "Run `uv run pytest` — the whole suite passes, including the inverted tests/test_round_tree.py assertions. Then run `uv run python src/spec4/app.py`, open the project view, and click the vision.json line in the round tree: the browser navigates to /artifacts, the Artifacts nav item shows active, and the session store holds that exact file/round pairing (confirm via the Dash dev tools or a debug readout). Repeat with a phases/phase1.md line to confirm expanded phase files are individually addressable. Confirms nfr_the_visual_and_navigational_register_is_fully_consistent_across_every_screen_in_the_app_ (one shared tree renderer serves both screens) and nfr_screens_render_fast_enough_to_feel_instantaneous_for_local_file_and_round_data__sub_second_ (the tree renders from the existing dependency graph with no added I/O).",
  "references": [
    {
      "standard": "Dash pattern-matching callbacks",
      "url": "https://dash.plotly.com/pattern-matching-callbacks"
    },
    {
      "standard": "Dash URL routing (dcc.Location)",
      "url": "https://dash.plotly.com/urls"
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

# Phase 2 of 8: Shared Round Tree — Linkable Lines via a Parameter

Turn the existing round tree into a single shared renderer whose lines can be links, controlled by a parameter rather than a duplicated copy. The project view passes the parameter, each line click resolves its target at the moment of selection and navigates to the Artifact View with that round/file pairing in the session store, and the existing test that asserts lines are not clickable is inverted.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Round Tree — product feature — introduced in this phase

*Scope for this phase: This round's only change to the round tree is the link parameter and the click-to-navigate behaviour; artifact ordering, lane colouring, the three-item legend, status derivation, and the usage-record needs-update exemption are already built and carry forward unchanged.*

Shows the current round's full set of expected artifacts as an ordered tree with per-artifact status, so the user can see at a glance what exists, what's outdated, and what's missing.

**Invocation**

- Trigger: The project view is opened, or the current round's artifacts change.

**Inputs**

- `round_identifier` (text, required) — The current round number.
- `artifact_dependency_graph` (structured data, required) — The known upstream/downstream relationships between pipeline artifacts.
- `artifact_existence_and_timestamps` (structured data, required) — Which artifacts exist and when each was last produced.

**Outputs**

- Primary: An ordered list of artifacts with status and lane coloring.
- Format: Tree/list display
- Schema notes: One entry per pipeline artifact, in pipeline order, each carrying a status (present, needs update, missing) and a lane (prompt for the agent, reference for the agent, record for you).

**Success criteria**

- Every pipeline artifact for the round appears exactly once, in pipeline order.
- An artifact whose upstream dependency is newer shows needs-update.
- An artifact that does not exist shows missing.
- The usage record never shows needs-update regardless of upstream changes.
- A three-item legend explains the lane distinctions.
- Only the current round's artifacts are shown.

**Failure modes**

- Status miscalculated when dependency information or timestamps are unavailable. (likelihood: medium) — mitigation: Treat unknown state as missing rather than present.
- Usage record incorrectly flagged as needing update. (likelihood: low) — mitigation: Exempt the usage record explicitly from the needs-update calculation.

- depends on: development_tool_shell (build these no later than `round_tree`)
- entities: Round, Artifact, DependencyGraph

### Artifact Links — product feature — extended in this phase

*Scope for this phase: Round-tree line links land here; the chat frame's Open buttons land in Phase 8.*

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

## Tech Stack

**Dependencies:**

- dash
- dash-mantine-components
- pytest
- ruff
- mypy

**Configurations:** No new environment variables. Selected round and selected file are read from and written to the existing browser session dcc.Store keys added in Phase 1. Navigation uses the app's existing dcc.Location.

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- round_artifacts (persistence) — serves `artifact_links`, `round_tree`

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

1. Read .spec4/v1/design/mock.html for the intended appearance of a linked round-tree line versus a plain one. Lane assignments come exclusively from _round_tree.ROUND_ARTIFACTS, never from the mock's sample data, which misfiles deployment-plan.md.
2. In src/spec4/layouts/_round_tree.py, add a keyword parameter to the existing tree-rendering function that switches its lines between plain text and clickable links, defaulting to the current plain-text behaviour. Render the link form from the same code path as the plain form — do not fork, copy, or duplicate the tree rendering, and do not add a second tree module.
3. When the parameter selects the link form, give each line a pattern-matching id of the form {'type': 'round-tree-line', 'index': <artifact key>} where the artifact key is the key from _round_tree.ROUND_ARTIFACTS. For a phases/ entry that expands into multiple .md files, index each expanded file individually so a click identifies one exact file.
4. Add an optional selected-file parameter to the same function that marks one line as the current selection using the shell's existing active-state mechanism. Set no colour on the component (D-LR2); the accent comes from the Mantine theme primary. Use the existing 'mono' class for the file paths.
5. Update the project view to call the shared renderer with the link form enabled, so every line in the project view's round tree is clickable, as required by the attached Artifact Links specification.
6. Add a callback in src/spec4/callbacks/ with a pattern-matching Input on {'type': 'round-tree-line', 'index': ALL} that, on click, reads the triggered id via dash.ctx.triggered_id, writes the clicked file path and its round into the session-store selection keys, and sets the dcc.Location pathname to '/artifacts'. Resolve the target from the triggered id at click time — never from a value captured when the tree was rendered — which is the mitigation the attached specification's failure modes require for a round changing mid-session.
7. Guard the callback against the initial-call fire (prevent_initial_call=True) and against a triggered_id of None, so a page load never writes a spurious selection into the session store.
8. Invert the assertion in tests/test_round_tree.py that currently asserts round-tree lines are NOT clickable: it must now assert that lines rendered with the link parameter enabled carry the {'type': 'round-tree-line'} pattern id, and keep a case asserting the default (unlinked) form still renders plain lines.
9. Add a test asserting that the project view renders its tree via the shared renderer with links enabled, and that the number of linked lines equals the number of entries produced from _round_tree.ROUND_ARTIFACTS for the round under test.
10. Run `uv run ruff check src/ tests/`, `uv run ruff format src/ tests/`, and `uv run mypy src/`, fixing every finding introduced by this phase.

## Risk Assessment

**Potential bottlenecks:**

Pattern-matching ids are the most common source of silent callback failure in Dash — a mismatch between the id dict written at render time and the Input pattern produces a control that simply does nothing, with no error. The phases/ expansion means the line count is dynamic, so a hard-coded expectation in the inverted test will break as soon as a phase file is added or removed. Adding a parameter to a function the project view already calls risks a positional-argument break at existing call sites.

**Mitigation strategy:**

Define the id dict in exactly one helper inside _round_tree.py and have both the renderer and the tests obtain ids from that helper, so render and Input can never drift. Write the inverted test to derive its expected line set from _round_tree.ROUND_ARTIFACTS and the actual phases/*.md files on disk rather than hard-coding a count. Add the new parameter as keyword-only with a default that preserves current behaviour, then update the project view call site explicitly.

## Verification

Run `uv run pytest` — the whole suite passes, including the inverted tests/test_round_tree.py assertions. Then run `uv run python src/spec4/app.py`, open the project view, and click the vision.json line in the round tree: the browser navigates to /artifacts, the Artifacts nav item shows active, and the session store holds that exact file/round pairing (confirm via the Dash dev tools or a debug readout). Repeat with a phases/phase1.md line to confirm expanded phase files are individually addressable. Confirms nfr_the_visual_and_navigational_register_is_fully_consistent_across_every_screen_in_the_app_ (one shared tree renderer serves both screens) and nfr_screens_render_fast_enough_to_feel_instantaneous_for_local_file_and_round_data__sub_second_ (the tree renders from the existing dependency graph with no added I/O).

## References

- [Dash pattern-matching callbacks](https://dash.plotly.com/pattern-matching-callbacks)
- [Dash URL routing (dcc.Location)](https://dash.plotly.com/urls)
- [Dash Mantine Components](https://www.dash-mantine-components.com)
- [pytest](https://docs.pytest.org/)
