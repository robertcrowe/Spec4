---
{
  "phase_number": 1,
  "total_phases": 8,
  "phase_title": "Integration Thread — /artifacts Route, Nav Entry, and Session-Store Selection Keys",
  "phase_summary": "Wire the new Artifact View surface into the existing Dash app as an empty but reachable screen: register the artifacts phase in the existing routing table, add the Artifacts navigation entry, create the new layout module beside its siblings, and add the selected-round/selected-file keys to the session store. No file reading and no content rendering happens in this phase — it proves the new screen is reachable and the existing suite is still green before any feature work begins.",
  "features": [
    {
      "id": "development_tool_shell",
      "role": "introduced",
      "scope_note": "Only the navigation register changes this round — the Artifacts entry is added between Project and Settings; the status strip, spacing, theme, and accent rules are already built and carry forward unchanged from v0."
    },
    {
      "id": "artifact_links",
      "role": "introduced",
      "scope_note": "Only the primary-navigation entry lands here; round-tree line links land in Phase 2 and the chat frame's Open buttons in Phase 8."
    },
    {
      "id": "artifact_view",
      "role": "introduced",
      "scope_note": "Only the route registration, the empty layout module, and the session-store selection keys land here; path resolution, tree, content rendering, and download land in Phases 3-5."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "dash",
      "dash-mantine-components",
      "dash-iconify",
      "pytest",
      "pytest-cov",
      "ruff",
      "mypy",
      "uv"
    ],
    "configurations": "No new environment variables. Existing optional vars are unchanged: LITELLM_LOG (must be set before litellm is first imported, per the D-LR1 comment in src/spec4/app.py) and DASH_DEBUG (dev server hot reload). App serves HTTP on localhost:8050 only; it is not exposed beyond the local machine. Selection state lives in the existing browser session dcc.Store — no server-side session, no new store component."
  },
  "instructions": [
    "Read .spec4/v1/design/mock.html before writing any layout code and match the intended visual register for the navigation entry and the empty Artifact View screen. Note: lane assignments for artifacts come exclusively from _round_tree.ROUND_ARTIFACTS, never from the mock's sample data, which misfiles deployment-plan.md.",
    "Open src/spec4/app.py and re-read the D-LR1 comment before touching anything: do not reorder the litellm-related imports, do not move the spec4.callbacks imports above the app construction, and preserve every existing `# noqa: E402` suppression.",
    "In src/spec4/app_constants.py, add an entry to PATH_TO_PHASE mapping the '/artifacts' path to a new 'artifacts' phase key, following the exact shape of the existing entries. Do not rename or reorder any existing entry.",
    "Create src/spec4/layouts/_artifact_view.py, named to match its siblings _round_tree.py, _round_cost.py, and _agent_rows.py. Export a single layout function that returns the Artifact View screen wrapped in the existing shell, laid out as two panes: a left selector/tree pane (empty placeholder in this phase) and a right content pane (empty placeholder in this phase).",
    "Give the new components new ids rather than reusing or renaming any existing id: artifact-view-root for the screen container, artifact-view-sidebar for the left pane, and artifact-view-content for the right pane. Existing component ids elsewhere in the app remain a test contract and must not change in this phase.",
    "Register the new layout with the app's phase-to-layout dispatch exactly the way the existing screens are registered, so navigating to /artifacts renders the Artifact View screen inside the shell rather than a not-found state.",
    "Add the Artifacts entry to the primary navigation register in the shell/status-bar layout module, positioned between Project and Settings, as required by the attached Artifact Links specification. Render it as plain text using the same active-state mechanism as the existing nav items; set no colour on the component itself (D-LR2) — the accent comes from the Mantine theme primary.",
    "Add two keys to the existing browser session dcc.Store payload: one for the selected round and one for the selected artifact file path. Initialise the selected round to the active round from src/spec4/session.py and the selected file to None. Do not add a new Store component and do not introduce any server-side session state.",
    "Add an 'artifacts' screen entry to tests/test_callback_co_presence.py following the exact structure of the existing screen entries, so the new screen's callbacks and components are covered by the co-presence contract.",
    "Add a test in tests/ asserting that PATH_TO_PHASE contains the '/artifacts' path and that the Artifacts nav entry appears between the Project and Settings entries in the navigation register's declared order.",
    "Run `uv run ruff check src/ tests/`, `uv run ruff format src/ tests/`, and `uv run mypy src/` and fix every finding introduced by this phase; the new module must satisfy mypy strict."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "The import ordering in src/spec4/app.py is load-bearing (D-LR1): a routine import cleanup or auto-formatter run can silently break startup logging and callback registration. The phase-to-layout dispatch and PATH_TO_PHASE are two separate registration points — updating only one produces a route that resolves to a blank or not-found screen with no error. Adding keys to the session store payload can break existing callbacks that destructure it positionally or assume a fixed key set.",
    "mitigation_strategy": "Re-read the D-LR1 comment before editing app.py and leave the litellm/callbacks import sequence and its noqa suppressions untouched. After adding the PATH_TO_PHASE entry, immediately verify the dispatch site by loading /artifacts in a browser — a blank shell is success, a not-found state means the dispatch registration is missing. Add the session-store keys with defaults and read them with .get() so existing callbacks that ignore them are unaffected; the full `uv run pytest` run at the end of this phase is the gate that proves nothing regressed."
  },
  "verification": "Run `uv run pytest` — the entire existing suite plus the new route/nav tests must pass, which also confirms the previously implemented Agent Rows, Round Tree, Round Cost, and shell surfaces still behave. Then run `uv run python src/spec4/app.py`, open http://localhost:8050/artifacts, and confirm: the shell status strip and nav render, the Artifacts nav item sits between Project and Settings and shows as active, and the two empty panes render with no console errors. Confirms nfr_the_visual_and_navigational_register_is_fully_consistent_across_every_screen_in_the_app_ (the new screen wears the same register as every existing screen) and nfr_provider_keys_never_leave_the_browser_under_any_feature_in_this_round_ (selection state was added to the browser session store only; no server-side session state was introduced).",
  "references": [
    {
      "standard": "Dash",
      "url": "https://dash.plotly.com/"
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
    },
    {
      "standard": "Ruff",
      "url": "https://docs.astral.sh/ruff/"
    },
    {
      "standard": "mypy",
      "url": "https://mypy.readthedocs.io/"
    }
  ]
}
---

# Phase 1 of 8: Integration Thread — /artifacts Route, Nav Entry, and Session-Store Selection Keys

Wire the new Artifact View surface into the existing Dash app as an empty but reachable screen: register the artifacts phase in the existing routing table, add the Artifacts navigation entry, create the new layout module beside its siblings, and add the selected-round/selected-file keys to the session store. No file reading and no content rendering happens in this phase — it proves the new screen is reachable and the existing suite is still green before any feature work begins.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Development Tool Shell — product feature — introduced in this phase

*Scope for this phase: Only the navigation register changes this round — the Artifacts entry is added between Project and Settings; the status strip, spacing, theme, and accent rules are already built and carry forward unchanged from v0.*

Establishes a consistent, minimal-chrome informational register (a status strip plus primary navigation) used across every screen, replacing a decorative marketing-style presentation with a compact developer-tool look.

**Invocation**

- Trigger: The app loads, or any screen renders (the shell wraps every screen).

**Inputs**

- `working_directory` (text, required) — The current project's working directory path.
- `round_identifier` (text, required) — The current round number.
- `default_provider_and_model` (text, required) — The currently selected default LLM provider and model.
- `app_version` (text, required) — The current app version identifier.

**Outputs**

- Primary: A persistent status strip and primary navigation shown around every screen's content.
- Format: Persistent visual frame
- Schema notes: Status strip fields appear in fixed order (directory, round, provider/model, version); navigation entries appear in fixed order (Project, Artifacts, Settings, Docs).

**Success criteria**

- The status strip always shows the current directory, round, provider/model, and version.
- Navigation is present and identical across all screens.
- No decorative elements (hero spacing, gradients, glow effects, emoji) appear anywhere.
- Vertical spacing is visibly tighter than the prior presentation.
- Only one accent emphasis color is used anywhere for primary emphasis or active-state indication.

**Failure modes**

- Status strip shows a stale directory or round after a change. (likelihood: medium) — mitigation: Always recompute status strip fields from current session state on every render.
- Accent emphasis color leaks into secondary or decorative elements. (likelihood: low) — mitigation: Restrict accent color usage strictly to primary emphasis and active-state indication.

- entities: WorkingDirectory, Round, Provider, Model

### Artifact Links — product feature — introduced in this phase

*Scope for this phase: Only the primary-navigation entry lands here; round-tree line links land in Phase 2 and the chat frame's Open buttons in Phase 8.*

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

### Artifact View — product feature — introduced in this phase

*Scope for this phase: Only the route registration, the empty layout module, and the session-store selection keys land here; path resolution, tree, content rendering, and download land in Phases 3-5.*

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

## Tech Stack

**Dependencies:**

- dash
- dash-mantine-components
- dash-iconify
- pytest
- pytest-cov
- ruff
- mypy
- uv

**Configurations:** No new environment variables. Existing optional vars are unchanged: LITELLM_LOG (must be set before litellm is first imported, per the D-LR1 comment in src/spec4/app.py) and DASH_DEBUG (dev server hot reload). App serves HTTP on localhost:8050 only; it is not exposed beyond the local machine. Selection state lives in the existing browser session dcc.Store — no server-side session, no new store component.

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- round_artifacts (persistence) — serves `artifact_links`, `artifact_view`
- session_store (persistence) — serves `artifact_view`, `development_tool_shell`
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

1. Read .spec4/v1/design/mock.html before writing any layout code and match the intended visual register for the navigation entry and the empty Artifact View screen. Note: lane assignments for artifacts come exclusively from _round_tree.ROUND_ARTIFACTS, never from the mock's sample data, which misfiles deployment-plan.md.
2. Open src/spec4/app.py and re-read the D-LR1 comment before touching anything: do not reorder the litellm-related imports, do not move the spec4.callbacks imports above the app construction, and preserve every existing `# noqa: E402` suppression.
3. In src/spec4/app_constants.py, add an entry to PATH_TO_PHASE mapping the '/artifacts' path to a new 'artifacts' phase key, following the exact shape of the existing entries. Do not rename or reorder any existing entry.
4. Create src/spec4/layouts/_artifact_view.py, named to match its siblings _round_tree.py, _round_cost.py, and _agent_rows.py. Export a single layout function that returns the Artifact View screen wrapped in the existing shell, laid out as two panes: a left selector/tree pane (empty placeholder in this phase) and a right content pane (empty placeholder in this phase).
5. Give the new components new ids rather than reusing or renaming any existing id: artifact-view-root for the screen container, artifact-view-sidebar for the left pane, and artifact-view-content for the right pane. Existing component ids elsewhere in the app remain a test contract and must not change in this phase.
6. Register the new layout with the app's phase-to-layout dispatch exactly the way the existing screens are registered, so navigating to /artifacts renders the Artifact View screen inside the shell rather than a not-found state.
7. Add the Artifacts entry to the primary navigation register in the shell/status-bar layout module, positioned between Project and Settings, as required by the attached Artifact Links specification. Render it as plain text using the same active-state mechanism as the existing nav items; set no colour on the component itself (D-LR2) — the accent comes from the Mantine theme primary.
8. Add two keys to the existing browser session dcc.Store payload: one for the selected round and one for the selected artifact file path. Initialise the selected round to the active round from src/spec4/session.py and the selected file to None. Do not add a new Store component and do not introduce any server-side session state.
9. Add an 'artifacts' screen entry to tests/test_callback_co_presence.py following the exact structure of the existing screen entries, so the new screen's callbacks and components are covered by the co-presence contract.
10. Add a test in tests/ asserting that PATH_TO_PHASE contains the '/artifacts' path and that the Artifacts nav entry appears between the Project and Settings entries in the navigation register's declared order.
11. Run `uv run ruff check src/ tests/`, `uv run ruff format src/ tests/`, and `uv run mypy src/` and fix every finding introduced by this phase; the new module must satisfy mypy strict.

## Risk Assessment

**Potential bottlenecks:**

The import ordering in src/spec4/app.py is load-bearing (D-LR1): a routine import cleanup or auto-formatter run can silently break startup logging and callback registration. The phase-to-layout dispatch and PATH_TO_PHASE are two separate registration points — updating only one produces a route that resolves to a blank or not-found screen with no error. Adding keys to the session store payload can break existing callbacks that destructure it positionally or assume a fixed key set.

**Mitigation strategy:**

Re-read the D-LR1 comment before editing app.py and leave the litellm/callbacks import sequence and its noqa suppressions untouched. After adding the PATH_TO_PHASE entry, immediately verify the dispatch site by loading /artifacts in a browser — a blank shell is success, a not-found state means the dispatch registration is missing. Add the session-store keys with defaults and read them with .get() so existing callbacks that ignore them are unaffected; the full `uv run pytest` run at the end of this phase is the gate that proves nothing regressed.

## Verification

Run `uv run pytest` — the entire existing suite plus the new route/nav tests must pass, which also confirms the previously implemented Agent Rows, Round Tree, Round Cost, and shell surfaces still behave. Then run `uv run python src/spec4/app.py`, open http://localhost:8050/artifacts, and confirm: the shell status strip and nav render, the Artifacts nav item sits between Project and Settings and shows as active, and the two empty panes render with no console errors. Confirms nfr_the_visual_and_navigational_register_is_fully_consistent_across_every_screen_in_the_app_ (the new screen wears the same register as every existing screen) and nfr_provider_keys_never_leave_the_browser_under_any_feature_in_this_round_ (selection state was added to the browser session store only; no server-side session state was introduced).

## References

- [Dash](https://dash.plotly.com/)
- [Dash URL routing (dcc.Location)](https://dash.plotly.com/urls)
- [Dash Mantine Components](https://www.dash-mantine-components.com)
- [pytest](https://docs.pytest.org/)
- [Ruff](https://docs.astral.sh/ruff/)
- [mypy](https://mypy.readthedocs.io/)
