---
{
  "phase_number": 7,
  "total_phases": 7,
  "phase_title": "Global Register Audit — Emoji Removal, Chrome Checklist, and Accent Consistency",
  "phase_summary": "Close the shell feature's project-wide criteria: sweep every screen in the app for emoji and remove them outright, run the marketing-era removal list as a reviewed checklist against every screen, and prove no component sets an accent colour locally — while confirming the chat frame, setup wizard, gate card, and Designer wizard keep their current layouts this round.",
  "features": [
    {
      "id": "development_tool_shell",
      "role": "extended",
      "scope_note": "Completes the feature's global criteria — the app-wide emoji sweep, the removal-list checklist across every screen, and single-accent enforcement; the shell layout itself landed in Phase 2."
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
    "configurations": "No new env vars and no new libraries. dash-iconify remains an installed dependency but is not used by anything this round — do not introduce it, any other icon component, or an icon font as part of the emoji removal. Changes span src/spec4/layouts/, src/spec4/callbacks/, src/spec4/agents/ (any user-facing strings), and src/spec4/assets/v3.css."
  },
  "instructions": [
    "Sweep the entire app for emoji: search src/spec4/ for characters in the Unicode emoji and pictographic ranges, covering layouts, callbacks, agent-authored user-facing strings, button and nav labels, status text, and src/spec4/assets/. The sweep is global this round, including screens whose layout is otherwise untouched.",
    "Remove every emoji found — never replace one. Where an emoji sat beside a word, delete the emoji and keep the word unchanged. Where an emoji stood alone as the whole label or indicator, replace it with a short text label that says what it meant.",
    "Do not add dash-iconify icons, any other icon component, or an icon font anywhere in the app as part of this sweep. dash-iconify is not used by anything this round.",
    "Add a pytest case that walks every .py and .css file under src/spec4/ and asserts no emoji or pictographic character is present, so a reintroduced emoji fails the suite. Exclude nothing from the walk except test fixtures.",
    "Write the marketing-era removal list as an explicit checklist in the phase notes and review it against every screen in the app: external-link drawer, footer, in-app landing page, grid background, kicker labels, gradient text, hero spacing, card hover effects, and button glows. Record each screen against each item.",
    "Grep src/spec4/assets/v3.css for any surviving rule implementing a checklist item — background grid patterns, background-clip: text gradients, transform or box-shadow hover states, glow shadows on buttons — and delete each one outright rather than overriding it.",
    "Add a pytest case asserting src/spec4/assets/v3.css contains no gradient-text, grid-background, hover-transform, or button-glow declarations, using the specific property patterns found during the grep, so a marketing-era style cannot bleed back in through an unreviewed component.",
    "Grep src/spec4/layouts/ for components passing a local accent colour — a `color` prop set to a hex value or to a colour name that is not the theme primary key — and remove each so the component inherits the theme primary. Leave genuinely semantic colours (error, warn) in place.",
    "Add a pytest case asserting no layout module contains the literal #39FF14, and that #1E88E5 appears in exactly one place: the wordmark. The accent must be reachable only through the theme primary registered in Phase 2.",
    "Confirm the layout and density changes stayed confined to the shell and the project view: verify the chat frame, setup wizard, gate card, and Designer wizard render with their current layouts, and that tests/test_cost_summary.py and tests/test_agent_llm_selection.py still pass with their ordering assertions untouched. The emoji sweep may change strings on those screens; it must not change their layouts.",
    "Run the full quality gate — `uv run pytest`, `uv run ruff check src/ tests/`, and `uv run mypy src/` — and confirm results are at or better than the Phase 1 baseline.",
    "Run `uv run python scripts/screenshot_ui.py` (the existing Playwright-backed screenshot script) to capture the reworked shell and project view, and compare the output side by side with .spec4/v0/design/mock.html as this round's final manual visual conformance check.",
    "Record a closing D-XX comment in src/spec4/layouts/ noting that the removal checklist is the standing review gate for new components: if an element on screen is not a fact, a command, an artifact, or a control, it does not ship.",
    "After this phase is complete and all verification passes, create the set-completion marker so Spec4 can detect this phase set is implemented: `touch .spec4/v0/IMPLEMENTED`"
  ],
  "risk_assessment": {
    "potential_bottlenecks": "Emoji hide in places a layout-focused sweep misses — agent-authored user-facing strings, CSS content properties, button labels built by string concatenation — so a partial sweep passes review and fails the criterion. An emoji that stood alone carried meaning, and deleting it without a text replacement silently removes information. Marketing-era CSS is frequently overridden rather than deleted, leaving the rule alive for any component that does not receive the override.",
    "mitigation_strategy": "Automate the sweep as a repository-wide test over every .py and .css file under src/spec4/ rather than a manual pass, so the criterion is enforced continuously. For each standalone emoji, record what it indicated before deleting it and substitute a short text label carrying the same meaning — never an icon. Delete marketing-era CSS declarations at their source and add the stylesheet assertion test so an override-based reintroduction fails the suite."
  },
  "verification": "`uv run pytest` passes with the new global cases: no emoji anywhere under src/spec4/, no gradient-text/grid-background/hover-transform/button-glow declarations in v3.css, no literal #39FF14 in any layout module, and #1E88E5 present only in the wordmark. `uv run ruff check src/ tests/` is clean and `uv run mypy src/` is at or better than the Phase 1 baseline. tests/test_cost_summary.py and tests/test_agent_llm_selection.py pass with their ordering assertions unchanged, and the chat frame, setup wizard, gate card, and Designer wizard render with their current layouts. `uv run python scripts/screenshot_ui.py` produces screenshots that match .spec4/v0/design/mock.html on manual comparison. Goals verified here: nfr_visual_density_and_accent_color_usage_remain_consistent_across_all_screens_with_no_per_view_drift (a single theme primary enforced by test, with no per-component accent anywhere) and nfr_the_shell_and_navigation_render_in_well_under_a_second_on_every_view (shell and nav render in under one second on every view after the sweep).",
  "references": [
    {
      "standard": "Dash Mantine Components",
      "url": "https://www.dash-mantine-components.com/"
    },
    {
      "standard": "Mantine — Colors and primaryColor",
      "url": "https://mantine.dev/theming/colors"
    },
    {
      "standard": "Unicode Emoji (UTS #51)",
      "url": "https://www.unicode.org/reports/tr51/"
    },
    {
      "standard": "Playwright for Python",
      "url": "https://playwright.dev/python/docs/intro"
    },
    {
      "standard": "Ruff",
      "url": "https://docs.astral.sh/ruff/"
    },
    {
      "standard": "mypy",
      "url": "https://mypy.readthedocs.io/"
    },
    {
      "standard": "Spec4 design mock (unique to this project)",
      "url": ".spec4/v0/design/mock.html"
    }
  ]
}
---

# Phase 7 of 7: Global Register Audit — Emoji Removal, Chrome Checklist, and Accent Consistency

Close the shell feature's project-wide criteria: sweep every screen in the app for emoji and remove them outright, run the marketing-era removal list as a reviewed checklist against every screen, and prove no component sets an accent colour locally — while confirming the chat frame, setup wizard, gate card, and Designer wizard keep their current layouts this round.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Development Tool Shell — product feature — extended in this phase

*Scope for this phase: Completes the feature's global criteria — the app-wide emoji sweep, the removal-list checklist across every screen, and single-accent enforcement; the shell layout itself landed in Phase 2.*

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

**Configurations:** No new env vars and no new libraries. dash-iconify remains an installed dependency but is not used by anything this round — do not introduce it, any other icon component, or an icon font as part of the emoji removal. Changes span src/spec4/layouts/, src/spec4/callbacks/, src/spec4/agents/ (any user-facing strings), and src/spec4/assets/v3.css.

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

1. Sweep the entire app for emoji: search src/spec4/ for characters in the Unicode emoji and pictographic ranges, covering layouts, callbacks, agent-authored user-facing strings, button and nav labels, status text, and src/spec4/assets/. The sweep is global this round, including screens whose layout is otherwise untouched.
2. Remove every emoji found — never replace one. Where an emoji sat beside a word, delete the emoji and keep the word unchanged. Where an emoji stood alone as the whole label or indicator, replace it with a short text label that says what it meant.
3. Do not add dash-iconify icons, any other icon component, or an icon font anywhere in the app as part of this sweep. dash-iconify is not used by anything this round.
4. Add a pytest case that walks every .py and .css file under src/spec4/ and asserts no emoji or pictographic character is present, so a reintroduced emoji fails the suite. Exclude nothing from the walk except test fixtures.
5. Write the marketing-era removal list as an explicit checklist in the phase notes and review it against every screen in the app: external-link drawer, footer, in-app landing page, grid background, kicker labels, gradient text, hero spacing, card hover effects, and button glows. Record each screen against each item.
6. Grep src/spec4/assets/v3.css for any surviving rule implementing a checklist item — background grid patterns, background-clip: text gradients, transform or box-shadow hover states, glow shadows on buttons — and delete each one outright rather than overriding it.
7. Add a pytest case asserting src/spec4/assets/v3.css contains no gradient-text, grid-background, hover-transform, or button-glow declarations, using the specific property patterns found during the grep, so a marketing-era style cannot bleed back in through an unreviewed component.
8. Grep src/spec4/layouts/ for components passing a local accent colour — a `color` prop set to a hex value or to a colour name that is not the theme primary key — and remove each so the component inherits the theme primary. Leave genuinely semantic colours (error, warn) in place.
9. Add a pytest case asserting no layout module contains the literal #39FF14, and that #1E88E5 appears in exactly one place: the wordmark. The accent must be reachable only through the theme primary registered in Phase 2.
10. Confirm the layout and density changes stayed confined to the shell and the project view: verify the chat frame, setup wizard, gate card, and Designer wizard render with their current layouts, and that tests/test_cost_summary.py and tests/test_agent_llm_selection.py still pass with their ordering assertions untouched. The emoji sweep may change strings on those screens; it must not change their layouts.
11. Run the full quality gate — `uv run pytest`, `uv run ruff check src/ tests/`, and `uv run mypy src/` — and confirm results are at or better than the Phase 1 baseline.
12. Run `uv run python scripts/screenshot_ui.py` (the existing Playwright-backed screenshot script) to capture the reworked shell and project view, and compare the output side by side with .spec4/v0/design/mock.html as this round's final manual visual conformance check.
13. Record a closing D-XX comment in src/spec4/layouts/ noting that the removal checklist is the standing review gate for new components: if an element on screen is not a fact, a command, an artifact, or a control, it does not ship.
14. After this phase is complete and all verification passes, create the set-completion marker so Spec4 can detect this phase set is implemented: `touch .spec4/v0/IMPLEMENTED`

## Risk Assessment

**Potential bottlenecks:**

Emoji hide in places a layout-focused sweep misses — agent-authored user-facing strings, CSS content properties, button labels built by string concatenation — so a partial sweep passes review and fails the criterion. An emoji that stood alone carried meaning, and deleting it without a text replacement silently removes information. Marketing-era CSS is frequently overridden rather than deleted, leaving the rule alive for any component that does not receive the override.

**Mitigation strategy:**

Automate the sweep as a repository-wide test over every .py and .css file under src/spec4/ rather than a manual pass, so the criterion is enforced continuously. For each standalone emoji, record what it indicated before deleting it and substitute a short text label carrying the same meaning — never an icon. Delete marketing-era CSS declarations at their source and add the stylesheet assertion test so an override-based reintroduction fails the suite.

## Verification

`uv run pytest` passes with the new global cases: no emoji anywhere under src/spec4/, no gradient-text/grid-background/hover-transform/button-glow declarations in v3.css, no literal #39FF14 in any layout module, and #1E88E5 present only in the wordmark. `uv run ruff check src/ tests/` is clean and `uv run mypy src/` is at or better than the Phase 1 baseline. tests/test_cost_summary.py and tests/test_agent_llm_selection.py pass with their ordering assertions unchanged, and the chat frame, setup wizard, gate card, and Designer wizard render with their current layouts. `uv run python scripts/screenshot_ui.py` produces screenshots that match .spec4/v0/design/mock.html on manual comparison. Goals verified here: nfr_visual_density_and_accent_color_usage_remain_consistent_across_all_screens_with_no_per_view_drift (a single theme primary enforced by test, with no per-component accent anywhere) and nfr_the_shell_and_navigation_render_in_well_under_a_second_on_every_view (shell and nav render in under one second on every view after the sweep).

**Non-functional acceptance** (deterministic, from the stack spec):

- `nfr_the_shell_and_navigation_render_in_well_under_a_second_on_every_view`: The shell and navigation render in well under a second on every view — project-wide acceptance
- `nfr_visual_density_and_accent_color_usage_remain_consistent_across_all_screens_with_no_per_view_drift`: Visual density and accent color usage remain consistent across all screens with no per-view drift — project-wide acceptance
- `nfr_the_project_view_remains_fully_usable_without_any_network_access_beyond_explicit_llm_calls`: The project view remains fully usable without any network access beyond explicit LLM calls — project-wide acceptance
- `nfr_status_information__round__artifact_state__cost__always_reflects_the_true_current_state_of_the_working_directory__never_a_stale_cached_view`: Status information (round, artifact state, cost) always reflects the true current state of the working directory, never a stale cached view — project-wide acceptance


## References

- [Dash Mantine Components](https://www.dash-mantine-components.com/)
- [Mantine — Colors and primaryColor](https://mantine.dev/theming/colors)
- [Unicode Emoji (UTS #51)](https://www.unicode.org/reports/tr51/)
- [Playwright for Python](https://playwright.dev/python/docs/intro)
- [Ruff](https://docs.astral.sh/ruff/)
- [mypy](https://mypy.readthedocs.io/)
- [Spec4 design mock (unique to this project)](.spec4/v0/design/mock.html)
