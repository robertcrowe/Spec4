---
{
  "phase_number": 6,
  "total_phases": 7,
  "phase_title": "Open To The Project — Root Routing and Landing-Page Retirement",
  "phase_summary": "Make the application root resolve to exactly one of two destinations — the project view for a remembered working directory, or the directory picker — and retire the in-app landing page entirely so no landing layout is ever rendered under any condition.",
  "features": [
    {
      "id": "open_to_the_project",
      "role": "introduced",
      "scope_note": ""
    },
    {
      "id": "development_tool_shell",
      "role": "extended",
      "scope_note": "Removes the in-app landing page, one of the shell's removal-list items; the global emoji sweep and cross-screen removal audit remain in Phase 7."
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
    "configurations": "No new env vars. The remembered WorkingDirectory is read from the existing browser dcc.Store pair (session in sessionStorage, prefs in localStorage) and threaded into the routing callback as State. Directory existence is checked against the local filesystem. Routing callback lives in src/spec4/callbacks/ alongside the existing dcc.Location-driven view switching."
  },
  "instructions": [
    "Locate the existing dcc.Location-driven routing callback in src/spec4/callbacks/ and extend it; do not add a second routing callback or a parallel dcc.Location.",
    "Implement the root path so the routing callback decides the destination after mount and returns exactly one of two layouts: the project view for the remembered working directory, or the directory picker. The acceptance criterion is that no landing layout is ever rendered — not that the destination is resolved before first render.",
    "Read the remembered working directory from the existing browser store via State. If the value is absent, empty, or null, return the directory picker.",
    "Before returning the project view, verify the remembered directory still exists and is readable on the local filesystem. If it does not, return the directory picker together with a short, plain-text message naming the directory that could not be opened — this is the mitigation for the invalid-remembered-directory failure mode in the specification above.",
    "Ensure the root container renders no content of its own while the routing callback resolves — an empty container, not a placeholder screen, spinner text, or partial layout — so no intermediate screen can appear between mount and destination.",
    "Delete the landing layout function _landing_layout from src/spec4/layouts/ entirely; do not leave it unreferenced or commented out.",
    "Delete the landing callback on_landing_start from src/spec4/callbacks/ and remove the btn-landing-start component id along with it.",
    "Remove the landing layout's ids — including btn-landing-start — from tests/test_callback_co_presence.py, and delete or rewrite any existing test that asserts the landing screen renders. Retiring the landing entries from the co-presence contract is part of this phase's work.",
    "Grep src/ for any remaining reference to the landing layout, on_landing_start, or btn-landing-start and remove each one, including navigation links that pointed at it and any CSS rules in src/spec4/assets/v3.css that styled it.",
    "Add pytest cases for the routing callback covering all three paths: a remembered directory that exists returns the project view; no remembered directory returns the directory picker; a remembered directory that no longer exists returns the directory picker plus the message naming it.",
    "Add a pytest case asserting no landing layout is reachable — that the routing callback returns the project view or the directory picker for the root path under every fixture, and that no importable landing layout function remains in src/spec4/layouts/.",
    "Run `uv run pytest` and confirm the whole suite passes with the landing entries removed from the co-presence contract."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "Deleting the landing layout while a callback, nav link, or test still references it produces an import error or a co-presence failure that surfaces only when the callback fires. The filesystem existence check can be slow or can raise on a permissions error rather than returning False, turning a normal fallback into a crash. Rendering a placeholder in the root container while routing resolves would reintroduce exactly the intermediate screen this feature forbids.",
    "mitigation_strategy": "Delete the layout, its callback, its id, its CSS, and its test entries in one change, then grep src/ and tests/ for each name to prove nothing dangles. Wrap the directory check in a try/except that treats any OSError as 'not accessible' and falls back to the picker with the message. Assert in a test that the root container's initial children are empty, so a placeholder cannot be added later without failing."
  },
  "verification": "`uv run pytest` passes with the three routing cases (remembered-and-valid → project view; none remembered → directory picker; remembered-but-gone → directory picker with a naming message) and the no-landing-reachable case, and with the landing ids removed from tests/test_callback_co_presence.py. `uv run ruff check src/ tests/` is clean, and grepping src/ for _landing_layout, on_landing_start, and btn-landing-start returns nothing. Visiting http://localhost:8050/ with a remembered directory lands on the project view with no intervening screen; clearing the store and reloading lands on the directory picker. Goals verified here: nfr_the_project_view_remains_fully_usable_without_any_network_access_beyond_explicit_llm_calls (the destination is resolved from the browser store and the local filesystem with no network call) and nfr_status_information__round__artifact_state__cost__always_reflects_the_true_current_state_of_the_working_directory__never_a_stale_cached_view (a remembered directory is re-validated against disk on every root visit rather than trusted from the store).",
  "references": [
    {
      "standard": "Dash — dcc.Location",
      "url": "https://dash.plotly.com/dash-core-components/location"
    },
    {
      "standard": "Dash — Multi-Page Apps and URL Support",
      "url": "https://dash.plotly.com/urls"
    },
    {
      "standard": "Dash — dcc.Store",
      "url": "https://dash.plotly.com/dash-core-components/store"
    },
    {
      "standard": "Spec4 design mock (unique to this project)",
      "url": ".spec4/v0/design/mock.html"
    }
  ]
}
---

# Phase 6 of 7: Open To The Project — Root Routing and Landing-Page Retirement

Make the application root resolve to exactly one of two destinations — the project view for a remembered working directory, or the directory picker — and retire the in-app landing page entirely so no landing layout is ever rendered under any condition.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Open To The Project — product feature — introduced in this phase

Ensures returning users land directly on their project instead of passing through an introductory screen, matching the expectations of an experienced developer tool.

**Invocation**

- Trigger: The user navigates to the application's root location

**Inputs**

- `remembered_working_directory` (text, optional) — A previously opened project folder path, if one is remembered

**Outputs**

- Primary: Either the project view for the remembered directory, or a directory picker
- Format: navigation result
- Schema notes: Exactly one of the two destinations is shown; no intermediate screen exists

**Success criteria**

- When a working directory is remembered, the project view for it appears with no intervening screen
- When no working directory is remembered, the directory picker appears immediately
- No introduction or landing screen is ever shown under any condition

**Failure modes**

- Remembered directory no longer exists or is inaccessible (likelihood: medium) — mitigation: Detect the invalid directory and fall back to the directory picker with a clear message
- Brief flash of an intermediate screen before the correct destination renders (likelihood: low) — mitigation: Resolve the destination before the first render completes

- depends on: round_tree, agent_rows, round_cost (build these no later than `open_to_the_project`)
- entities: WorkingDirectory, ProjectView

### Development Tool Shell — product feature — extended in this phase

*Scope for this phase: Removes the in-app landing page, one of the shell's removal-list items; the global emoji sweep and cross-screen removal audit remain in Phase 7.*

Replaces the marketing-style header and layout with a dense, status-bar-driven shell so the app reads as a professional development tool rather than a promotional site.

**Invocation**

- Trigger: The app loads or the user navigates between views

**Inputs**

- `working_directory` (text, required) — The currently open project's folder path
- `current_round` (number, required) — The active round number being worked on
- `default_provider_model` (text, required) — The provider and model currently set as default
- `spec4_version` (text, required) — The running version identifier of the app

**Outputs**

- Primary: A rendered application shell with a status bar and primary navigation
- Format: structured layout
- Schema notes: Status bar shows working directory, round, default provider/model, and version; nav shows Project, Artifacts, Settings, and one Docs link; no other chrome is present

**Success criteria**

- Status bar always shows current working directory, round, provider/model, and version when available
- No external-link drawer, footer, in-app landing page, grid background, kicker labels, gradient text, or hover glows remain in the shell or on the project view
- No emoji appear anywhere in the app: the sweep is global in this round, including screens whose layout is otherwise untouched
- Vertical spacing in the shell and on the project view is roughly half the prior layout's
- Exactly one accent colour is used for all primary actions, active states, and focus indicators; it is set once as the theme primary, so every screen inherits it
- The wordmark is the only place a second colour appears
- Layout and density changes are confined to the shell and the project view; the chat frame, setup wizard, gate card, and Designer wizard keep their current layouts this round

**Failure modes**

- Status bar shows blank or stale working directory after switching projects (likelihood: medium) — mitigation: Recompute status bar contents whenever the active project or round changes
- A marketing-era style bleeds back in through an unreviewed component (likelihood: medium) — mitigation: Treat the removal list as a checklist reviewed against every screen before release
- Accent color is applied inconsistently across components (likelihood: low) — mitigation: Define the accent as the single theme primary so all components inherit it uniformly

- entities: WorkingDirectory, Round, ProviderModel

### UI surfaces for this phase (from the design)

- **`status-bar`** [non_ai]
  - screens: project-view
  - inputs: nav links: Project, Settings, Docs
  - output: Wordmark, working directory · round · provider · model in mono, nav with current item marked, version
  - states: idle
  - reads: ProjectView, WorkingDirectory, Round, ProviderModel

## Tech Stack

**Dependencies:**

- dash
- dash-mantine-components
- pytest
- ruff
- mypy

**Configurations:** No new env vars. The remembered WorkingDirectory is read from the existing browser dcc.Store pair (session in sessionStorage, prefs in localStorage) and threaded into the routing callback as State. Directory existence is checked against the local filesystem. Routing callback lives in src/spec4/callbacks/ alongside the existing dcc.Location-driven view switching.

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- round_artifacts (persistence) — serves `open_to_the_project`
- session_store (persistence) — serves `development_tool_shell`, `open_to_the_project`
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

1. Locate the existing dcc.Location-driven routing callback in src/spec4/callbacks/ and extend it; do not add a second routing callback or a parallel dcc.Location.
2. Implement the root path so the routing callback decides the destination after mount and returns exactly one of two layouts: the project view for the remembered working directory, or the directory picker. The acceptance criterion is that no landing layout is ever rendered — not that the destination is resolved before first render.
3. Read the remembered working directory from the existing browser store via State. If the value is absent, empty, or null, return the directory picker.
4. Before returning the project view, verify the remembered directory still exists and is readable on the local filesystem. If it does not, return the directory picker together with a short, plain-text message naming the directory that could not be opened — this is the mitigation for the invalid-remembered-directory failure mode in the specification above.
5. Ensure the root container renders no content of its own while the routing callback resolves — an empty container, not a placeholder screen, spinner text, or partial layout — so no intermediate screen can appear between mount and destination.
6. Delete the landing layout function _landing_layout from src/spec4/layouts/ entirely; do not leave it unreferenced or commented out.
7. Delete the landing callback on_landing_start from src/spec4/callbacks/ and remove the btn-landing-start component id along with it.
8. Remove the landing layout's ids — including btn-landing-start — from tests/test_callback_co_presence.py, and delete or rewrite any existing test that asserts the landing screen renders. Retiring the landing entries from the co-presence contract is part of this phase's work.
9. Grep src/ for any remaining reference to the landing layout, on_landing_start, or btn-landing-start and remove each one, including navigation links that pointed at it and any CSS rules in src/spec4/assets/v3.css that styled it.
10. Add pytest cases for the routing callback covering all three paths: a remembered directory that exists returns the project view; no remembered directory returns the directory picker; a remembered directory that no longer exists returns the directory picker plus the message naming it.
11. Add a pytest case asserting no landing layout is reachable — that the routing callback returns the project view or the directory picker for the root path under every fixture, and that no importable landing layout function remains in src/spec4/layouts/.
12. Run `uv run pytest` and confirm the whole suite passes with the landing entries removed from the co-presence contract.

## Risk Assessment

**Potential bottlenecks:**

Deleting the landing layout while a callback, nav link, or test still references it produces an import error or a co-presence failure that surfaces only when the callback fires. The filesystem existence check can be slow or can raise on a permissions error rather than returning False, turning a normal fallback into a crash. Rendering a placeholder in the root container while routing resolves would reintroduce exactly the intermediate screen this feature forbids.

**Mitigation strategy:**

Delete the layout, its callback, its id, its CSS, and its test entries in one change, then grep src/ and tests/ for each name to prove nothing dangles. Wrap the directory check in a try/except that treats any OSError as 'not accessible' and falls back to the picker with the message. Assert in a test that the root container's initial children are empty, so a placeholder cannot be added later without failing.

## Verification

`uv run pytest` passes with the three routing cases (remembered-and-valid → project view; none remembered → directory picker; remembered-but-gone → directory picker with a naming message) and the no-landing-reachable case, and with the landing ids removed from tests/test_callback_co_presence.py. `uv run ruff check src/ tests/` is clean, and grepping src/ for _landing_layout, on_landing_start, and btn-landing-start returns nothing. Visiting http://localhost:8050/ with a remembered directory lands on the project view with no intervening screen; clearing the store and reloading lands on the directory picker. Goals verified here: nfr_the_project_view_remains_fully_usable_without_any_network_access_beyond_explicit_llm_calls (the destination is resolved from the browser store and the local filesystem with no network call) and nfr_status_information__round__artifact_state__cost__always_reflects_the_true_current_state_of_the_working_directory__never_a_stale_cached_view (a remembered directory is re-validated against disk on every root visit rather than trusted from the store).

## References

- [Dash — dcc.Location](https://dash.plotly.com/dash-core-components/location)
- [Dash — Multi-Page Apps and URL Support](https://dash.plotly.com/urls)
- [Dash — dcc.Store](https://dash.plotly.com/dash-core-components/store)
- [Spec4 design mock (unique to this project)](.spec4/v0/design/mock.html)
