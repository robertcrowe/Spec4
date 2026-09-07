---
{
  "phase_number": 2,
  "total_phases": 7,
  "phase_title": "Development Tool Shell — Theme Primary, Status Bar, and Chrome Removal",
  "phase_summary": "Rework the application shell into a dense, status-bar-driven frame: the accent colour is set once as the Mantine theme primary, the header becomes a monospace status line, navigation reduces to Project / Settings / Docs, and the marketing-era chrome is stripped from the shell. This phase lands the shell portion of the feature; the global cross-screen emoji sweep and removal-checklist audit are deferred to Phase 7, and landing-page removal is deferred to Phase 6.",
  "features": [
    {
      "id": "development_tool_shell",
      "role": "introduced",
      "scope_note": "Theme primary, status bar, reduced nav, and chrome/spacing removal within the shell and project-view frame; the global emoji sweep and cross-screen removal audit land in Phase 7 and landing-page removal lands in Phase 6."
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
    "configurations": "No new env vars. Optional DASH_DEBUG for the dev server. Theme and layout changes land in src/spec4/app.py (MantineProvider theme), src/spec4/layouts/ (shell components), and src/spec4/assets/v3.css (the single stylesheet). Status bar reads WorkingDirectory and Round from the existing sessionStorage dcc.Store and ProviderModel from the existing localStorage prefs dcc.Store, both threaded in as callback State — never from module globals."
  },
  "instructions": [
    "Open .spec4/v0/design/mock.html and .spec4/v0/design/manifest.json before writing any code, and match the status-bar surface's layout, spacing, and typography to what the mock shows.",
    "In src/spec4/app.py, register a custom Mantine colour named `spec4-green` as a ten-shade array built around #39FF14 in the MantineProvider theme's `colors` object, then set `primaryColor` to the string \"spec4-green\". Mantine's primaryColor must be a KEY of theme.colors — assigning the raw hex value directly will throw during theme merging.",
    "Set the theme's `primaryShade` so the rendered accent matches #39FF14 in the dark colour scheme, and keep the existing dark theme otherwise unchanged.",
    "Record a numbered D-XX comment at the theme definition stating that the accent is set once here and every component inherits it; no component may pass a local `color` prop for its accent.",
    "Search src/spec4/layouts/ for any component that sets a `color` or `variant` prop to a hard-coded accent value and remove it so the component inherits the theme primary. Leave semantic colours (error/warn) alone.",
    "Confirm #1E88E5 blue survives only in the wordmark: grep src/spec4/assets/v3.css and src/spec4/layouts/ for that value and remove every other occurrence.",
    "Build the status bar as a new component in src/spec4/layouts/ with a NEW component id (do not rename any existing id). It renders the four inputs named in the feature specification above, in the order the mock shows, with working directory, provider/model, and version in the monospace font already loaded in app.py (JetBrains Mono).",
    "Write the status-bar callback in src/spec4/callbacks/ that reads working directory and round from the session dcc.Store and default provider/model from the prefs dcc.Store via State, and resolves the default provider/model through the existing src/spec4/llm_selection.py path — do not add a parallel model-resolution path.",
    "Make the status-bar callback fire on change of the session store and the prefs store, not only on initial page load, so the bar recomputes whenever the active project or round changes — this is the mitigation for the stale-working-directory failure mode in the specification above.",
    "Render each status-bar field with an explicit empty-state (an em dash or short text placeholder) when its value is unavailable, so a missing value never renders as a blank gap that reads as a layout bug. Use text only — no icons.",
    "Reduce the primary navigation to exactly three items: Project, Settings, and one Docs link. Do not render an Artifacts item, and do not render a disabled Artifacts placeholder — Artifacts arrives in v1 with the Artifact View.",
    "Delete the external-link drawer and the footer from the shell, including their layout functions and any callbacks whose only Inputs are their component ids. Remove the corresponding ids from tests/test_callback_co_presence.py in the same commit so the co-presence contract stays accurate.",
    "In src/spec4/assets/v3.css, remove the grid background rules, the gradient-text rules, the card hover-effect rules, and the button glow rules. Delete the declarations outright rather than commenting them out or overriding them later in the file.",
    "In src/spec4/assets/v3.css and the shell layout, halve the vertical spacing tokens used by the shell and the project-view frame (section padding, stack gaps, card padding), targeting roughly 50% of the prior values, and match the resulting density against the mock.",
    "Remove kicker labels and hero-scale spacing from the shell and the project-view frame. Leave the chat frame, setup wizard, gate card, and Designer wizard layouts untouched this round.",
    "Do not add any icon component in this phase: dash-iconify is not used by anything this round.",
    "Add pytest cases to tests/ in the existing style that call the shell layout function directly and assert on the returned component tree: the status-bar id is present, the nav contains exactly the three expected labels, no Artifacts nav item exists, and the drawer and footer ids are absent.",
    "Add a pytest case that imports the app's theme object and asserts primaryColor equals \"spec4-green\" and that \"spec4-green\" is a key of theme colors.",
    "Update tests/test_callback_co_presence.py to reflect the shell's new and removed ids, extending the existing enumeration in place."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "Removing drawer and footer ids will break any registered callback that still lists them as an Input, and Dash raises at callback-fire time rather than import time, so the failure surfaces as a broken screen rather than a clear error. Mantine's primaryColor rejecting a raw hex value is a common and confusing failure. Halving spacing by editing CSS in one place can be silently overridden by inline style props still set in layout functions.",
    "mitigation_strategy": "Delete each removed component's callbacks in the same commit as the component and update tests/test_callback_co_presence.py immediately, then run `uv run pytest` before touching anything else. Register the accent as a named ten-shade colour key and assert it in a test rather than trusting visual inspection. When halving spacing, grep the shell layout for inline style/padding/gap props and change them alongside the CSS, since inline props win over the stylesheet."
  },
  "verification": "`uv run pytest` passes at or above the Phase 1 baseline, including the new shell tests (status-bar id present, nav is exactly Project/Settings/Docs with no Artifacts item, drawer and footer ids absent, theme primaryColor is the registered spec4-green key). `uv run ruff check src/ tests/` is clean. Loading http://localhost:8050 shows the header rendering as a status line with monospace working directory, round, provider/model, and version; no grid background, gradient text, kicker labels, hover glows, button glows, drawer, or footer are present; primary buttons, active states, and focus rings are all #39FF14 and #1E88E5 appears only in the wordmark. Manual check: the shell matches .spec4/v0/design/mock.html. Goals verified here: nfr_visual_density_and_accent_color_usage_remain_consistent_across_all_screens_with_no_per_view_drift (accent set once as the theme primary so every screen inherits it), nfr_the_shell_and_navigation_render_in_well_under_a_second_on_every_view (shell and nav render in under one second on a cold load), and nfr_the_project_view_remains_fully_usable_without_any_network_access_beyond_explicit_llm_calls (status bar sources all four values from the browser stores and local state, making no network call).",
  "references": [
    {
      "standard": "Dash Mantine Components — MantineProvider",
      "url": "https://www.dash-mantine-components.com/components/mantineprovider"
    },
    {
      "standard": "Mantine — Colors and primaryColor",
      "url": "https://mantine.dev/theming/colors"
    },
    {
      "standard": "Dash Mantine Components — Theme Object",
      "url": "https://www.dash-mantine-components.com/theme-object"
    },
    {
      "standard": "Dash — Basic Callbacks and State",
      "url": "https://dash.plotly.com/basic-callbacks"
    },
    {
      "standard": "Dash — dcc.Store",
      "url": "https://dash.plotly.com/dash-core-components/store"
    },
    {
      "standard": "Spec4 design mock (unique to this project)",
      "url": ".spec4/v0/design/mock.html"
    },
    {
      "standard": "Spec4 design manifest (unique to this project)",
      "url": ".spec4/v0/design/manifest.json"
    }
  ]
}
---

# Phase 2 of 7: Development Tool Shell — Theme Primary, Status Bar, and Chrome Removal

Rework the application shell into a dense, status-bar-driven frame: the accent colour is set once as the Mantine theme primary, the header becomes a monospace status line, navigation reduces to Project / Settings / Docs, and the marketing-era chrome is stripped from the shell. This phase lands the shell portion of the feature; the global cross-screen emoji sweep and removal-checklist audit are deferred to Phase 7, and landing-page removal is deferred to Phase 6.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Development Tool Shell — product feature — introduced in this phase

*Scope for this phase: Theme primary, status bar, reduced nav, and chrome/spacing removal within the shell and project-view frame; the global emoji sweep and cross-screen removal audit land in Phase 7 and landing-page removal lands in Phase 6.*

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

**Configurations:** No new env vars. Optional DASH_DEBUG for the dev server. Theme and layout changes land in src/spec4/app.py (MantineProvider theme), src/spec4/layouts/ (shell components), and src/spec4/assets/v3.css (the single stylesheet). Status bar reads WorkingDirectory and Round from the existing sessionStorage dcc.Store and ProviderModel from the existing localStorage prefs dcc.Store, both threaded in as callback State — never from module globals.

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

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

1. Open .spec4/v0/design/mock.html and .spec4/v0/design/manifest.json before writing any code, and match the status-bar surface's layout, spacing, and typography to what the mock shows.
2. In src/spec4/app.py, register a custom Mantine colour named `spec4-green` as a ten-shade array built around #39FF14 in the MantineProvider theme's `colors` object, then set `primaryColor` to the string "spec4-green". Mantine's primaryColor must be a KEY of theme.colors — assigning the raw hex value directly will throw during theme merging.
3. Set the theme's `primaryShade` so the rendered accent matches #39FF14 in the dark colour scheme, and keep the existing dark theme otherwise unchanged.
4. Record a numbered D-XX comment at the theme definition stating that the accent is set once here and every component inherits it; no component may pass a local `color` prop for its accent.
5. Search src/spec4/layouts/ for any component that sets a `color` or `variant` prop to a hard-coded accent value and remove it so the component inherits the theme primary. Leave semantic colours (error/warn) alone.
6. Confirm #1E88E5 blue survives only in the wordmark: grep src/spec4/assets/v3.css and src/spec4/layouts/ for that value and remove every other occurrence.
7. Build the status bar as a new component in src/spec4/layouts/ with a NEW component id (do not rename any existing id). It renders the four inputs named in the feature specification above, in the order the mock shows, with working directory, provider/model, and version in the monospace font already loaded in app.py (JetBrains Mono).
8. Write the status-bar callback in src/spec4/callbacks/ that reads working directory and round from the session dcc.Store and default provider/model from the prefs dcc.Store via State, and resolves the default provider/model through the existing src/spec4/llm_selection.py path — do not add a parallel model-resolution path.
9. Make the status-bar callback fire on change of the session store and the prefs store, not only on initial page load, so the bar recomputes whenever the active project or round changes — this is the mitigation for the stale-working-directory failure mode in the specification above.
10. Render each status-bar field with an explicit empty-state (an em dash or short text placeholder) when its value is unavailable, so a missing value never renders as a blank gap that reads as a layout bug. Use text only — no icons.
11. Reduce the primary navigation to exactly three items: Project, Settings, and one Docs link. Do not render an Artifacts item, and do not render a disabled Artifacts placeholder — Artifacts arrives in v1 with the Artifact View.
12. Delete the external-link drawer and the footer from the shell, including their layout functions and any callbacks whose only Inputs are their component ids. Remove the corresponding ids from tests/test_callback_co_presence.py in the same commit so the co-presence contract stays accurate.
13. In src/spec4/assets/v3.css, remove the grid background rules, the gradient-text rules, the card hover-effect rules, and the button glow rules. Delete the declarations outright rather than commenting them out or overriding them later in the file.
14. In src/spec4/assets/v3.css and the shell layout, halve the vertical spacing tokens used by the shell and the project-view frame (section padding, stack gaps, card padding), targeting roughly 50% of the prior values, and match the resulting density against the mock.
15. Remove kicker labels and hero-scale spacing from the shell and the project-view frame. Leave the chat frame, setup wizard, gate card, and Designer wizard layouts untouched this round.
16. Do not add any icon component in this phase: dash-iconify is not used by anything this round.
17. Add pytest cases to tests/ in the existing style that call the shell layout function directly and assert on the returned component tree: the status-bar id is present, the nav contains exactly the three expected labels, no Artifacts nav item exists, and the drawer and footer ids are absent.
18. Add a pytest case that imports the app's theme object and asserts primaryColor equals "spec4-green" and that "spec4-green" is a key of theme colors.
19. Update tests/test_callback_co_presence.py to reflect the shell's new and removed ids, extending the existing enumeration in place.

## Risk Assessment

**Potential bottlenecks:**

Removing drawer and footer ids will break any registered callback that still lists them as an Input, and Dash raises at callback-fire time rather than import time, so the failure surfaces as a broken screen rather than a clear error. Mantine's primaryColor rejecting a raw hex value is a common and confusing failure. Halving spacing by editing CSS in one place can be silently overridden by inline style props still set in layout functions.

**Mitigation strategy:**

Delete each removed component's callbacks in the same commit as the component and update tests/test_callback_co_presence.py immediately, then run `uv run pytest` before touching anything else. Register the accent as a named ten-shade colour key and assert it in a test rather than trusting visual inspection. When halving spacing, grep the shell layout for inline style/padding/gap props and change them alongside the CSS, since inline props win over the stylesheet.

## Verification

`uv run pytest` passes at or above the Phase 1 baseline, including the new shell tests (status-bar id present, nav is exactly Project/Settings/Docs with no Artifacts item, drawer and footer ids absent, theme primaryColor is the registered spec4-green key). `uv run ruff check src/ tests/` is clean. Loading http://localhost:8050 shows the header rendering as a status line with monospace working directory, round, provider/model, and version; no grid background, gradient text, kicker labels, hover glows, button glows, drawer, or footer are present; primary buttons, active states, and focus rings are all #39FF14 and #1E88E5 appears only in the wordmark. Manual check: the shell matches .spec4/v0/design/mock.html. Goals verified here: nfr_visual_density_and_accent_color_usage_remain_consistent_across_all_screens_with_no_per_view_drift (accent set once as the theme primary so every screen inherits it), nfr_the_shell_and_navigation_render_in_well_under_a_second_on_every_view (shell and nav render in under one second on a cold load), and nfr_the_project_view_remains_fully_usable_without_any_network_access_beyond_explicit_llm_calls (status bar sources all four values from the browser stores and local state, making no network call).

## References

- [Dash Mantine Components — MantineProvider](https://www.dash-mantine-components.com/components/mantineprovider)
- [Mantine — Colors and primaryColor](https://mantine.dev/theming/colors)
- [Dash Mantine Components — Theme Object](https://www.dash-mantine-components.com/theme-object)
- [Dash — Basic Callbacks and State](https://dash.plotly.com/basic-callbacks)
- [Dash — dcc.Store](https://dash.plotly.com/dash-core-components/store)
- [Spec4 design mock (unique to this project)](.spec4/v0/design/mock.html)
- [Spec4 design manifest (unique to this project)](.spec4/v0/design/manifest.json)
