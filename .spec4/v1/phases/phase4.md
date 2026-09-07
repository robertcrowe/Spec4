---
{
  "phase_number": 4,
  "total_phases": 8,
  "phase_title": "Artifact View Screen — Round Selector, Tree, and Content Pane",
  "phase_summary": "Fill in the Artifact View screen: a round selector above the shared round tree on the left with the current file marked, and on the right a one-line monospace header followed by the file's content — JSON pretty-printed, other text as-is, both with line numbers — or a clear missing-artifact message.",
  "features": [
    {
      "id": "artifact_view",
      "role": "extended",
      "scope_note": "The round selector, selected-file tree, content-pane header, line-numbered rendering, and missing-file message land here; Download and Open-rendered land in Phase 5."
    },
    {
      "id": "artifact_links",
      "role": "extended",
      "scope_note": "The Artifact View now honours a pre-selected round/file arriving from a round-tree link; the chat frame's Open buttons land in Phase 8."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "dash",
      "dash-mantine-components",
      "json (Python 3.12 stdlib)",
      "pathlib (Python 3.12 stdlib)",
      "pytest",
      "playwright",
      "ruff",
      "mypy"
    ],
    "configurations": "No new environment variables. Selected round and selected file are read from the browser session dcc.Store keys added in Phase 1; the round selector defaults to the active round from src/spec4/session.py. All file reads go through the Phase 3 confined resolver."
  },
  "instructions": [
    "Read .spec4/v1/design/mock.html for the Artifact View's intended layout, density, and header format before writing layout code. Lane assignments come exclusively from _round_tree.ROUND_ARTIFACTS, never from the mock's sample data, which misfiles deployment-plan.md.",
    "In src/spec4/layouts/_artifact_view.py, build the left pane: a dmc.Select with id artifact-round-select listing every round from the Phase 3 rounds enumeration, defaulting to the active round, rendered above the shared round tree from _round_tree.py called with the link parameter enabled and the selected-file parameter set from the session store.",
    "Recompute the round list every time the screen is rendered rather than reading a cached value, so a round created since the last visit appears — this is the mitigation the attached specification's failure modes require for a stale round list.",
    "Build the right pane's one-line header with id artifact-view-header, showing path, size, last modified, and lane on a single line in the existing 'mono' class, in that fixed order. Reuse the layout helpers in layouts/_shared.py rather than duplicating spacing or container markup. Set no colour on any component (D-LR2).",
    "Build the content renderer: for a .json file, parse with the stdlib json module and re-serialise with json.dumps(indent=2, ensure_ascii=False); for every other text file, use the raw text unchanged. Then attach line numbers to whichever string resulted.",
    "Render line numbers as two side-by-side html.Pre elements inside a dmc.ScrollArea — one holding the right-aligned gutter of numbers as a single newline-joined string, one holding the content as a single string — rather than one component per line. A per-line component tree makes a large artifact unresponsive, which the attached specification's failure modes call out; the two-Pre approach scales to large plain-text files.",
    "Give the content pane the id artifact-view-content-body and the scroll container the id artifact-view-scroll. Do not introduce a Markdown renderer or any syntax-highlighting component — this round adds no dependency of any kind; Markdown and other text render as-is.",
    "Handle a file whose JSON fails to parse by falling back to raw line-numbered text rather than raising, so a partially written artifact is still readable.",
    "For an artifact the Phase 3 resolver reports as allowed-but-missing, render the missing message in place of content, naming the producing Agent exactly as the attached specification's schema notes describe, while the file's line still appears in the tree.",
    "Write the callback that drives the pane: Inputs are the round selector value and the session-store selection keys; on change it calls the Phase 3 resolver, reads the file only when the resolver allows it, and updates the header and content body. A resolver rejection must render a plain rejection message and must never read a file.",
    "When the round selector changes, update both the tree and the selection: clear the selected file if it does not exist in the newly selected round's allowed set, so switching rounds updates the tree and the available files together.",
    "Add tests in tests/test_artifact_view.py asserting: JSON is pretty-printed and line-numbered, a plain text file is line-numbered without reformatting, the gutter line count equals the content line count for both, the header contains path/size/last-modified/lane in order, and a missing artifact renders the missing message naming its producing Agent.",
    "Add a Playwright end-to-end test that loads /artifacts, selects stack.json in the tree, and asserts the header shows its path and the content pane shows pretty-printed JSON with a line-number gutter."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "Rendering line numbers as one component per line is the obvious implementation and the one that makes a large artifact hang the browser — an AI coder will reach for it by default. Gutter/content misalignment is easy to introduce if the two Pre elements get different line-height or font settings. The round-selector and tree-click callbacks both write the same session-store keys, risking a circular update or a selection that survives a round switch into a round where the file does not exist.",
    "mitigation_strategy": "Specify the two-Pre gutter/content structure explicitly and assert the line counts match in a test. Set line-height and font for both Pre elements from a single CSS rule in src/spec4/assets/v3.css so they cannot drift. Make the pane callback single-purpose and read-only with respect to the session store except for the round-switch clearing rule, and add a test that selecting a file, then switching to a round lacking that file, clears the selection rather than rendering a rejection."
  },
  "verification": "Run `uv run pytest` — the full suite plus the new rendering tests pass. Then run `uv run python src/spec4/app.py`, open /artifacts, and confirm: the round selector lists every round on disk with the active round preselected; selecting stack.json shows its path, size, last-modified, and lane on one monospace line above pretty-printed, line-numbered JSON; selecting phases/phase1.md shows line-numbered Markdown as-is; selecting a missing artifact shows 'missing — produced by {Agent}'; switching rounds updates the tree and the available files. Scroll a large artifact and confirm the pane stays responsive. Confirms nfr_screens_render_fast_enough_to_feel_instantaneous_for_local_file_and_round_data__sub_second__ and nfr_viewing_or_obtaining_a_copy_of_an_artifact_works_consistently_regardless_of_round_or_file_size__without_noticeable_delay_for_typical_spec_file_sizes_, and re-confirms nfr_all_artifact_reads_are_strictly_confined_to_the_current_project_s_spec_folder__with_no_other_path_ever_reachable_ (every read in this screen goes through the Phase 3 resolver).",
  "references": [
    {
      "standard": "Dash Mantine Components",
      "url": "https://www.dash-mantine-components.com"
    },
    {
      "standard": "Dash Mantine Components — ScrollArea",
      "url": "https://www.dash-mantine-components.com/components/scrollarea"
    },
    {
      "standard": "Dash Mantine Components — Select",
      "url": "https://www.dash-mantine-components.com/components/select"
    },
    {
      "standard": "Python json module",
      "url": "https://docs.python.org/3/library/json.html"
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

# Phase 4 of 8: Artifact View Screen — Round Selector, Tree, and Content Pane

Fill in the Artifact View screen: a round selector above the shared round tree on the left with the current file marked, and on the right a one-line monospace header followed by the file's content — JSON pretty-printed, other text as-is, both with line numbers — or a clear missing-artifact message.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Artifact View — product feature — extended in this phase

*Scope for this phase: The round selector, selected-file tree, content-pane header, line-numbered rendering, and missing-file message land here; Download and Open-rendered land in Phase 5.*

Lets the user open and read any artifact from any round without leaving the app, giving full visibility into what each agent produced or is expected to produce.

**Invocation**

- Trigger: The user navigates to the Artifacts destination, or selects a file from a round tree or link elsewhere in the app.

**Inputs**

- `round_identifier` (text, optional) — The round to display, defaulting to the active round.
- `selected_file_path` (text, optional) — The artifact selected for viewing within the chosen round.
- `rounds_on_disk` (list of items, required) — Every round present for the current project.

**Outputs**

- Primary: The rendered content of the selected artifact, or a missing-file message.
- Format: Two-part screen: a round/tree selector and a content pane
- Schema notes: The content pane shows a one-line header (path, size, last modified, lane) followed by the file's content — structured content pretty-printed, plain text shown with line numbers; a missing file shows 'missing — produced by {Agent}' in place of content.

**Success criteria**

- Selecting any listed artifact displays its content correctly, with line numbers for every text file (JSON included, pretty-printed).
- Only files that belong to the reviewed artifact set can ever be opened, and no path outside the project's spec folder can be reached this way.
- Switching rounds updates both the tree and the available files.
- The file that renders the app's mock output can also be opened in a rendered, viewable form separate from its raw text.
- A way to obtain a copy of the currently viewed file is always available.
- A missing artifact is shown in the tree and clearly explained when selected.

**Failure modes**

- A request for a file outside the recognized artifact set is attempted. (likelihood: high) — mitigation: Reject any path not present in the reviewed artifact table, resolved strictly within the project's spec folder.
- Viewing a very large file causes the screen to become unresponsive. (likelihood: medium) — mitigation: Apply line numbering and rendering that scales to large plain-text files.
- Stale round list after a new round is created. (likelihood: low) — mitigation: Recompute the list of rounds on disk each time the screen opens.

- depends on: round_tree (build these no later than `artifact_view`)
- entities: Round, Artifact, ArtifactFile

### Artifact Links — product feature — extended in this phase

*Scope for this phase: The Artifact View now honours a pre-selected round/file arriving from a round-tree link; the chat frame's Open buttons land in Phase 8.*

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
- json (Python 3.12 stdlib)
- pathlib (Python 3.12 stdlib)
- pytest
- playwright
- ruff
- mypy

**Configurations:** No new environment variables. Selected round and selected file are read from the browser session dcc.Store keys added in Phase 1; the round selector defaults to the active round from src/spec4/session.py. All file reads go through the Phase 3 confined resolver.

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- round_artifacts (persistence) — serves `artifact_links`, `artifact_view`
- session_store (persistence) — serves `artifact_view`

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

1. Read .spec4/v1/design/mock.html for the Artifact View's intended layout, density, and header format before writing layout code. Lane assignments come exclusively from _round_tree.ROUND_ARTIFACTS, never from the mock's sample data, which misfiles deployment-plan.md.
2. In src/spec4/layouts/_artifact_view.py, build the left pane: a dmc.Select with id artifact-round-select listing every round from the Phase 3 rounds enumeration, defaulting to the active round, rendered above the shared round tree from _round_tree.py called with the link parameter enabled and the selected-file parameter set from the session store.
3. Recompute the round list every time the screen is rendered rather than reading a cached value, so a round created since the last visit appears — this is the mitigation the attached specification's failure modes require for a stale round list.
4. Build the right pane's one-line header with id artifact-view-header, showing path, size, last modified, and lane on a single line in the existing 'mono' class, in that fixed order. Reuse the layout helpers in layouts/_shared.py rather than duplicating spacing or container markup. Set no colour on any component (D-LR2).
5. Build the content renderer: for a .json file, parse with the stdlib json module and re-serialise with json.dumps(indent=2, ensure_ascii=False); for every other text file, use the raw text unchanged. Then attach line numbers to whichever string resulted.
6. Render line numbers as two side-by-side html.Pre elements inside a dmc.ScrollArea — one holding the right-aligned gutter of numbers as a single newline-joined string, one holding the content as a single string — rather than one component per line. A per-line component tree makes a large artifact unresponsive, which the attached specification's failure modes call out; the two-Pre approach scales to large plain-text files.
7. Give the content pane the id artifact-view-content-body and the scroll container the id artifact-view-scroll. Do not introduce a Markdown renderer or any syntax-highlighting component — this round adds no dependency of any kind; Markdown and other text render as-is.
8. Handle a file whose JSON fails to parse by falling back to raw line-numbered text rather than raising, so a partially written artifact is still readable.
9. For an artifact the Phase 3 resolver reports as allowed-but-missing, render the missing message in place of content, naming the producing Agent exactly as the attached specification's schema notes describe, while the file's line still appears in the tree.
10. Write the callback that drives the pane: Inputs are the round selector value and the session-store selection keys; on change it calls the Phase 3 resolver, reads the file only when the resolver allows it, and updates the header and content body. A resolver rejection must render a plain rejection message and must never read a file.
11. When the round selector changes, update both the tree and the selection: clear the selected file if it does not exist in the newly selected round's allowed set, so switching rounds updates the tree and the available files together.
12. Add tests in tests/test_artifact_view.py asserting: JSON is pretty-printed and line-numbered, a plain text file is line-numbered without reformatting, the gutter line count equals the content line count for both, the header contains path/size/last-modified/lane in order, and a missing artifact renders the missing message naming its producing Agent.
13. Add a Playwright end-to-end test that loads /artifacts, selects stack.json in the tree, and asserts the header shows its path and the content pane shows pretty-printed JSON with a line-number gutter.

## Risk Assessment

**Potential bottlenecks:**

Rendering line numbers as one component per line is the obvious implementation and the one that makes a large artifact hang the browser — an AI coder will reach for it by default. Gutter/content misalignment is easy to introduce if the two Pre elements get different line-height or font settings. The round-selector and tree-click callbacks both write the same session-store keys, risking a circular update or a selection that survives a round switch into a round where the file does not exist.

**Mitigation strategy:**

Specify the two-Pre gutter/content structure explicitly and assert the line counts match in a test. Set line-height and font for both Pre elements from a single CSS rule in src/spec4/assets/v3.css so they cannot drift. Make the pane callback single-purpose and read-only with respect to the session store except for the round-switch clearing rule, and add a test that selecting a file, then switching to a round lacking that file, clears the selection rather than rendering a rejection.

## Verification

Run `uv run pytest` — the full suite plus the new rendering tests pass. Then run `uv run python src/spec4/app.py`, open /artifacts, and confirm: the round selector lists every round on disk with the active round preselected; selecting stack.json shows its path, size, last-modified, and lane on one monospace line above pretty-printed, line-numbered JSON; selecting phases/phase1.md shows line-numbered Markdown as-is; selecting a missing artifact shows 'missing — produced by {Agent}'; switching rounds updates the tree and the available files. Scroll a large artifact and confirm the pane stays responsive. Confirms nfr_screens_render_fast_enough_to_feel_instantaneous_for_local_file_and_round_data__sub_second__ and nfr_viewing_or_obtaining_a_copy_of_an_artifact_works_consistently_regardless_of_round_or_file_size__without_noticeable_delay_for_typical_spec_file_sizes_, and re-confirms nfr_all_artifact_reads_are_strictly_confined_to_the_current_project_s_spec_folder__with_no_other_path_ever_reachable_ (every read in this screen goes through the Phase 3 resolver).

## References

- [Dash Mantine Components](https://www.dash-mantine-components.com)
- [Dash Mantine Components — ScrollArea](https://www.dash-mantine-components.com/components/scrollarea)
- [Dash Mantine Components — Select](https://www.dash-mantine-components.com/components/select)
- [Python json module](https://docs.python.org/3/library/json.html)
- [Playwright for Python](https://playwright.dev/python/docs/intro)
- [pytest](https://docs.pytest.org/)
