---
{
  "phase_number": 3,
  "total_phases": 7,
  "phase_title": "Entry Screens Register — Directory Picker and Project-Mode Question",
  "phase_summary": "Bring the directory picker and the project-mode question into the dev-tool register: a monospace path entry, a single-column one-per-line subdirectory list, the folder-creation option folded into one row with its text field, and a two-line question with its two choices side by side. Browsing, creating, selecting, and the once-per-session question behaviour are unchanged.",
  "features": [
    {
      "id": "entry_screens_register",
      "role": "introduced",
      "scope_note": "Implements the feature in full — both the picker and the project-mode question."
    },
    {
      "id": "open_to_the_project",
      "role": "introduced",
      "scope_note": "This phase only re-verifies the existing root routing (remembered directory goes straight to the project view, no remembered directory goes straight to the reworked picker, no landing screen) against the restyled picker; the routing logic itself is already built and unchanged."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "dash",
      "dash-mantine-components",
      "pytest"
    ],
    "configurations": "No new configuration. WorkingDirectory and ProjectMode continue to live in the existing session dcc.Store (sessionStorage), read via callback State — never module globals. Styling lands in src/spec4/assets/v3.css."
  },
  "instructions": [
    "In src/spec4/layouts/__init__.py, locate the directory-picker layout and the project-mode question layout. Restyle them in place — keep every existing component id, since ids are a test contract enumerated by tests/test_callback_co_presence.py.",
    "Apply the existing `mono` CSS class to the picker's path input and to every directory name rendered in the list. Do not introduce a second monospace mechanism.",
    "Replace the picker's grid of directory buttons with a single-column list rendering one directory per line, using existing DMC primitives (dmc.Stack of dmc.Button or dmc.Anchor rows, per what the current code already uses for a clickable directory). Keep each entry's click behaviour and id pattern exactly as it is so browsing still works.",
    "Give each directory line a truncation rule in src/spec4/assets/v3.css so a long directory name is truncated rather than wrapping or overflowing the single-column layout, per the failure mode named in the specification above.",
    "Fold the 'create a folder here' option and its text field into a single row using dmc.Group, so the label/action and the newFolderName input sit on one line. Keep the field's id and the create callback unchanged.",
    "Make the Select action the one filled primary button on the picker screen; render every other action on that screen as a neutral outline. Do not set a colour prop on any component (D-LR2) — the accent comes from the Mantine theme primary.",
    "In the project-mode question, set the title in sentence case, cut the explanatory text to at most two lines, and place the two choices as buttons on one row via dmc.Group, with exactly one of them the filled primary and the other a neutral outline.",
    "Do not change the once-per-session behaviour of the question or the ProjectMode value written to the session store — the specification's success criteria require it still be asked exactly once per session.",
    "Remove any remaining decorative chrome on these two screens: kicker labels, gradient text, hero spacing, card hover effects, button glows, and emoji. Cut vertical spacing to match the density of the already-reworked shell and project view.",
    "Update tests/test_root_routing.py if it asserts anything about the picker's internal structure; do not weaken its assertions that a remembered directory routes to the project view and an absent one routes to the picker.",
    "Add a test asserting the picker renders its subdirectories as a single-column list — one entry per rendered line/child, not a grid — and that the path entry and directory names carry the `mono` class.",
    "Add a test asserting the folder-creation control and its text input are children of the same row container, and that the picker renders exactly one filled-primary action (Select).",
    "Add a test asserting the project-mode question renders exactly two choice buttons within one row container, exactly one of them filled primary, and that its explanatory text is at most two lines' worth of content.",
    "Run tests/test_callback_co_presence.py and confirm every picker and question id it enumerates is still present in the reworked layouts; no id is removed in this phase.",
    "Reference .spec4/v2/design/mock.html's picker-view and mode-inset screens for the intended list density, row composition, and button emphasis."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "The picker's directory entries are generated in a loop, so a restyle that changes the container from a grid to a stack can easily drop or rename the per-entry id pattern that the browse callback matches on, silently breaking navigation into subdirectories. The project-mode question's once-per-session guard lives in callback/session logic rather than the layout, and a layout rewrite can accidentally re-render it on every navigation.",
    "mitigation_strategy": "Change only the container and the class names in the picker loop; leave the per-entry id construction expression untouched, and diff the generated ids before and after. For the question, touch the layout function only — do not modify the callback or the session-store write that records askedThisSession — and add the test asserting once-per-session behaviour is preserved. Run `uv run pytest` after the picker change and again after the question change, separately."
  },
  "verification": "`uv run pytest` passes, including tests/test_callback_co_presence.py, tests/test_root_routing.py, and the new single-column-list, folded-create-row, and two-choice-question tests. Run `uv run python src/spec4/app.py` with no remembered directory: the picker appears immediately with no landing screen, the path entry and directory names render in monospace, subdirectories list one per line, the create-folder option shares a row with its field, and Select is the only filled-primary action. Browsing into a subdirectory, creating a folder, and selecting a directory all still work; opening a directory that already has files asks the mode question exactly once for that session, with its two choices on one row. The single accent colour marks the primary action on both screens (nfr_a_single_accent_color_and_consistent_low_chrome_visual_language_across_every_screen__with_no_exceptions).",
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
      "standard": "Dash Mantine Components — TextInput",
      "url": "https://www.dash-mantine-components.com/components/textinput"
    },
    {
      "standard": "pytest",
      "url": "https://docs.pytest.org/"
    }
  ]
}
---

# Phase 3 of 7: Entry Screens Register — Directory Picker and Project-Mode Question

Bring the directory picker and the project-mode question into the dev-tool register: a monospace path entry, a single-column one-per-line subdirectory list, the folder-creation option folded into one row with its text field, and a two-line question with its two choices side by side. Browsing, creating, selecting, and the once-per-session question behaviour are unchanged.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Entry Screens Register — product feature — introduced in this phase

*Scope for this phase: Implements the feature in full — both the picker and the project-mode question.*

Brings the directory picker and the project-mode question in line with the developer-tool look while keeping their exact existing behavior.

**Invocation**

- Trigger: The directory picker or the project-mode question is shown.

**Inputs**

- `candidate_directories` (list of items, required) — Subdirectories available to browse into.
- `current_path_input` (text, required) — The path currently typed or selected.

**Outputs**

- Primary: The reworked picker and question screens.
- Format: Single-column directory list, one-row folder-creation entry, two-line question with two side-by-side choices.
- Schema notes: Exactly one primary-emphasis action on each screen.

**Success criteria**

- Directory names and the path entry render in fixed-width type
- Subdirectories list one per line rather than as a grid
- The folder-creation option and its text entry share one row
- The question's explanation is no longer than two lines and its two choices sit on one row, one of them primary
- The picker still browses, creates, and selects a directory exactly as before
- The question is still asked once per session

**Failure modes**

- A long directory name breaks the single-column layout (likelihood: low) — mitigation: Truncate the name rather than wrap or overflow
- The reworked question is asked more than once per session (likelihood: low) — mitigation: Keep the existing once-per-session behavior unchanged

- depends on: development_tool_shell (build these no later than `entry_screens_register`)
- entities: WorkingDirectory, ProjectMode

### Open To The Project — product feature — introduced in this phase

*Scope for this phase: This phase only re-verifies the existing root routing (remembered directory goes straight to the project view, no remembered directory goes straight to the reworked picker, no landing screen) against the restyled picker; the routing logic itself is already built and unchanged.*

Sends the user straight into their current project when one is already known, removing any need for an introductory screen.

**Invocation**

- Trigger: The app is opened at its root address.

**Inputs**

- `remembered_working_directory` (text, optional) — A previously opened project directory, if one is remembered.

**Outputs**

- Primary: Either the project view or the directory picker.
- Format: Full-screen navigation to exactly one destination.
- Schema notes: Never shows both destinations at once.

**Success criteria**

- With a remembered directory, the project view appears with no intermediate screen
- With no remembered directory, the directory picker appears immediately
- No introduction or landing screen is ever shown

**Failure modes**

- A remembered directory no longer exists (likelihood: medium) — mitigation: Fall back to the directory picker and let the user choose again
- Stale directory memory opens the wrong project (likelihood: low) — mitigation: Always show the working-directory path prominently so the user can confirm

- depends on: entry_screens_register, agent_rows, round_cost, round_tree (build these no later than `open_to_the_project`)
- entities: WorkingDirectory, Project

### UI surfaces for this phase (from the design)

- **`Status Bar & Nav`** [non_ai]
  - screens: all
  - inputs: nav item
  - output: Persistent bar with working-directory path (truncates from start, empty when unknown), round, provider, model+effort, version, and Project / Artifacts / Settings / Docs nav
  - states: path known, path empty (no directory yet), active nav item, narrow viewport
  - reads: Project, WorkingDirectory, Round, Provider, Model, Effort, Navigation
- **`Directory Path Entry`** [non_ai]
  - screens: picker-view
  - inputs: mono path text input, Up
  - output: The path currently typed or browsed to
  - states: idle, typed path, at filesystem root
  - reads: WorkingDirectory
  - writes: WorkingDirectory
  - after (advisory UI ordering): Status Bar & Nav
- **`Directory List`** [non_ai]
  - screens: picker-view
  - inputs: directory line
  - output: One subdirectory per line in mono, 28px rows
  - states: populated, empty, long name truncated
  - reads: WorkingDirectory
  - writes: WorkingDirectory
  - after (advisory UI ordering): Directory Path Entry
- **`Create Folder Row`** [non_ai]
  - screens: picker-view
  - inputs: Create folder, new-folder name input
  - output: A new subdirectory under the current path
  - states: idle, name entered
  - reads: WorkingDirectory
  - writes: WorkingDirectory
  - after (advisory UI ordering): Directory List
- **`Select Directory Action`** [non_ai]
  - screens: picker-view
  - inputs: Select this directory
  - output: The chosen working directory, opening the project
  - states: enabled
  - reads: WorkingDirectory
  - writes: Project, WorkingDirectory
  - after (advisory UI ordering): Directory Path Entry
- **`Project Mode Question`** [non_ai]
  - screens: mode-inset
  - inputs: Existing project, New project
  - output: The recorded project mode for this session
  - states: asked, answered
  - reads: ProjectMode, WorkingDirectory
  - writes: ProjectMode
  - after (advisory UI ordering): Select Directory Action

## Tech Stack

**Dependencies:**

- dash
- dash-mantine-components
- pytest

**Configurations:** No new configuration. WorkingDirectory and ProjectMode continue to live in the existing session dcc.Store (sessionStorage), read via callback State — never module globals. Styling lands in src/spec4/assets/v3.css.

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- round_artifacts (persistence) — serves `open_to_the_project`
- session_store (persistence) — serves `entry_screens_register`, `open_to_the_project`

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

1. In src/spec4/layouts/__init__.py, locate the directory-picker layout and the project-mode question layout. Restyle them in place — keep every existing component id, since ids are a test contract enumerated by tests/test_callback_co_presence.py.
2. Apply the existing `mono` CSS class to the picker's path input and to every directory name rendered in the list. Do not introduce a second monospace mechanism.
3. Replace the picker's grid of directory buttons with a single-column list rendering one directory per line, using existing DMC primitives (dmc.Stack of dmc.Button or dmc.Anchor rows, per what the current code already uses for a clickable directory). Keep each entry's click behaviour and id pattern exactly as it is so browsing still works.
4. Give each directory line a truncation rule in src/spec4/assets/v3.css so a long directory name is truncated rather than wrapping or overflowing the single-column layout, per the failure mode named in the specification above.
5. Fold the 'create a folder here' option and its text field into a single row using dmc.Group, so the label/action and the newFolderName input sit on one line. Keep the field's id and the create callback unchanged.
6. Make the Select action the one filled primary button on the picker screen; render every other action on that screen as a neutral outline. Do not set a colour prop on any component (D-LR2) — the accent comes from the Mantine theme primary.
7. In the project-mode question, set the title in sentence case, cut the explanatory text to at most two lines, and place the two choices as buttons on one row via dmc.Group, with exactly one of them the filled primary and the other a neutral outline.
8. Do not change the once-per-session behaviour of the question or the ProjectMode value written to the session store — the specification's success criteria require it still be asked exactly once per session.
9. Remove any remaining decorative chrome on these two screens: kicker labels, gradient text, hero spacing, card hover effects, button glows, and emoji. Cut vertical spacing to match the density of the already-reworked shell and project view.
10. Update tests/test_root_routing.py if it asserts anything about the picker's internal structure; do not weaken its assertions that a remembered directory routes to the project view and an absent one routes to the picker.
11. Add a test asserting the picker renders its subdirectories as a single-column list — one entry per rendered line/child, not a grid — and that the path entry and directory names carry the `mono` class.
12. Add a test asserting the folder-creation control and its text input are children of the same row container, and that the picker renders exactly one filled-primary action (Select).
13. Add a test asserting the project-mode question renders exactly two choice buttons within one row container, exactly one of them filled primary, and that its explanatory text is at most two lines' worth of content.
14. Run tests/test_callback_co_presence.py and confirm every picker and question id it enumerates is still present in the reworked layouts; no id is removed in this phase.
15. Reference .spec4/v2/design/mock.html's picker-view and mode-inset screens for the intended list density, row composition, and button emphasis.

## Risk Assessment

**Potential bottlenecks:**

The picker's directory entries are generated in a loop, so a restyle that changes the container from a grid to a stack can easily drop or rename the per-entry id pattern that the browse callback matches on, silently breaking navigation into subdirectories. The project-mode question's once-per-session guard lives in callback/session logic rather than the layout, and a layout rewrite can accidentally re-render it on every navigation.

**Mitigation strategy:**

Change only the container and the class names in the picker loop; leave the per-entry id construction expression untouched, and diff the generated ids before and after. For the question, touch the layout function only — do not modify the callback or the session-store write that records askedThisSession — and add the test asserting once-per-session behaviour is preserved. Run `uv run pytest` after the picker change and again after the question change, separately.

## Verification

`uv run pytest` passes, including tests/test_callback_co_presence.py, tests/test_root_routing.py, and the new single-column-list, folded-create-row, and two-choice-question tests. Run `uv run python src/spec4/app.py` with no remembered directory: the picker appears immediately with no landing screen, the path entry and directory names render in monospace, subdirectories list one per line, the create-folder option shares a row with its field, and Select is the only filled-primary action. Browsing into a subdirectory, creating a folder, and selecting a directory all still work; opening a directory that already has files asks the mode question exactly once for that session, with its two choices on one row. The single accent colour marks the primary action on both screens (nfr_a_single_accent_color_and_consistent_low_chrome_visual_language_across_every_screen__with_no_exceptions).

## References

- [Dash](https://dash.plotly.com/)
- [Dash Mantine Components](https://www.dash-mantine-components.com)
- [Dash Mantine Components — TextInput](https://www.dash-mantine-components.com/components/textinput)
- [pytest](https://docs.pytest.org/)
