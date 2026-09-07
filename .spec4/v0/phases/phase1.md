---
{
  "phase_number": 1,
  "total_phases": 7,
  "phase_title": "Integration Thread — Baseline Validation of the Existing Spec4 App",
  "phase_summary": "Prove the existing Dash application builds, serves at localhost:8050, and passes its full quality gate (pytest, ruff, mypy) unchanged, and read the existing callback co-presence contract so the coming shell rework is done against a known-green baseline rather than a guessed one. No feature work, no layout changes, no new files.",
  "features": [],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "uv",
      "dash",
      "dash-mantine-components",
      "pytest",
      "pytest-cov",
      "ruff",
      "mypy",
      "types-pyyaml",
      "gunicorn"
    ],
    "configurations": "No required env vars. Optional: DASH_DEBUG (enables Dash hot-reload; set to true for the dev server), LITELLM_LOG (suppresses litellm startup verbosity, must be set before litellm is first imported by any module). App serves HTTP on localhost:8050 only and is not exposed beyond the local machine."
  },
  "instructions": [
    "Run `uv build` and confirm it completes without error using the existing uv_build backend and pyproject.toml; do not modify pyproject.toml in this phase.",
    "Run `uv run pytest` and record the exact number of passing tests and any pre-existing failures. This count is the baseline every later phase must meet or exceed.",
    "Run `uv run ruff check src/ tests/` and confirm it reports no violations under the configured rule set (select = [\"E\", \"F\"]).",
    "Run `uv run mypy src/` and record the result. The project configures mypy strict = true but has no documented invocation; record the current output as the baseline without fixing unrelated pre-existing errors and without touching the dead [[tool.mypy.overrides]] entry for a2a_sdk.",
    "Start the app with `uv run python src/spec4/app.py` and confirm it serves at http://localhost:8050 and renders without a browser console error.",
    "Start the app a second time with `uv run gunicorn 'spec4.app:server' --bind 0.0.0.0:8050 --workers 1 --threads 4` and confirm the same page renders, so the production-style local serving path is known-good before any layout change.",
    "Open src/spec4/app.py and confirm the litellm setup ordering is intact: LITELLM_LOG / litellm.suppress_debug_info are set before any litellm-importing module, and the `import spec4.callbacks` statements carry the deliberate `# noqa: E402`. Write a one-line D-XX comment above that block noting the ordering must not be changed by this round's work.",
    "Read tests/test_callback_co_presence.py in full and list, in your working notes, the component ids it already enumerates for the shell, the landing layout, and the project view. This file is the existing component-id contract; do NOT create a parallel inventory, a new id-manifest file, or a duplicate test module.",
    "Read tests/test_cost_summary.py and tests/test_agent_llm_selection.py and record the relative-ordering assertions they make (cost card between transcript and token count; model chip before status line). These orderings must survive every later phase.",
    "Read src/spec4/app_constants.py and confirm AGENT_KEYS is the single definition of the seven-agent pipeline order, and read src/spec4/layouts/__init__.py to locate the existing _AGENT_ROWS table asserted against it.",
    "Read src/spec4/project_manager.py and record the exact names of the functions that expose artifact staleness (detect_stale_inputs) and agent readiness (agent_button_state), plus the shape of what they return. Later phases consume these unchanged and must not re-derive status.",
    "Read src/spec4/session.py and src/spec4/llm_selection.py and record how working directory, current round, and the default provider/model are obtained, noting that all state lives in the two browser dcc.Stores (session in sessionStorage, prefs in localStorage) and must be threaded into server-side callbacks as State.",
    "Open .spec4/v0/design/mock.html in a browser and read .spec4/v0/design/manifest.json. Record the target visual register for the project-view screen and its four surfaces (status-bar, round-tree, agent-rows, round-cost) as the reference all later phases match against.",
    "Add a single new pytest case to tests/test_callback_co_presence.py named test_agent_keys_is_single_pipeline_order that asserts spec4.app_constants.AGENT_KEYS has exactly seven entries and that the existing layouts agent table is derived from or equal to it in order. Use a new test name; do not rename or delete any existing test."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "The mypy strict gate has no documented invocation, so its first run may surface a large volume of pre-existing errors that look like this phase's responsibility. The gunicorn path may behave differently from the dev server for asset loading. Reading the co-presence test can tempt the agent to 'improve' it by restructuring the id lists.",
    "mitigation_strategy": "Treat every pre-existing mypy error as baseline and out of scope — record the count, fix nothing unrelated, and do not add ignores to silence them. Verify both serving paths explicitly rather than assuming parity. Change exactly one thing in tests/: the additive AGENT_KEYS ordering test. Leave the existing id enumerations byte-for-byte alone; later phases will extend them as screens actually change."
  },
  "verification": "`uv build` succeeds; `uv run ruff check src/ tests/` is clean; `uv run pytest` passes with the recorded baseline count plus the one new test (test_agent_keys_is_single_pipeline_order); `uv run python src/spec4/app.py` and the gunicorn command each serve a rendering page at http://localhost:8050. The baseline pytest count, the mypy output, and the list of ids already enumerated in tests/test_callback_co_presence.py are all recorded in the phase notes.",
  "references": [
    {
      "standard": "Dash for Python",
      "url": "https://dash.plotly.com/"
    },
    {
      "standard": "Dash Mantine Components",
      "url": "https://www.dash-mantine-components.com/"
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
    },
    {
      "standard": "uv",
      "url": "https://docs.astral.sh/uv/"
    },
    {
      "standard": "Gunicorn",
      "url": "https://docs.gunicorn.org/"
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

# Phase 1 of 7: Integration Thread — Baseline Validation of the Existing Spec4 App

Prove the existing Dash application builds, serves at localhost:8050, and passes its full quality gate (pytest, ruff, mypy) unchanged, and read the existing callback co-presence contract so the coming shell rework is done against a known-green baseline rather than a guessed one. No feature work, no layout changes, no new files.

## Tech Stack

**Dependencies:**

- uv
- dash
- dash-mantine-components
- pytest
- pytest-cov
- ruff
- mypy
- types-pyyaml
- gunicorn

**Configurations:** No required env vars. Optional: DASH_DEBUG (enables Dash hot-reload; set to true for the dev server), LITELLM_LOG (suppresses litellm startup verbosity, must be set before litellm is first imported by any module). App serves HTTP on localhost:8050 only and is not exposed beyond the local machine.

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

1. Run `uv build` and confirm it completes without error using the existing uv_build backend and pyproject.toml; do not modify pyproject.toml in this phase.
2. Run `uv run pytest` and record the exact number of passing tests and any pre-existing failures. This count is the baseline every later phase must meet or exceed.
3. Run `uv run ruff check src/ tests/` and confirm it reports no violations under the configured rule set (select = ["E", "F"]).
4. Run `uv run mypy src/` and record the result. The project configures mypy strict = true but has no documented invocation; record the current output as the baseline without fixing unrelated pre-existing errors and without touching the dead [[tool.mypy.overrides]] entry for a2a_sdk.
5. Start the app with `uv run python src/spec4/app.py` and confirm it serves at http://localhost:8050 and renders without a browser console error.
6. Start the app a second time with `uv run gunicorn 'spec4.app:server' --bind 0.0.0.0:8050 --workers 1 --threads 4` and confirm the same page renders, so the production-style local serving path is known-good before any layout change.
7. Open src/spec4/app.py and confirm the litellm setup ordering is intact: LITELLM_LOG / litellm.suppress_debug_info are set before any litellm-importing module, and the `import spec4.callbacks` statements carry the deliberate `# noqa: E402`. Write a one-line D-XX comment above that block noting the ordering must not be changed by this round's work.
8. Read tests/test_callback_co_presence.py in full and list, in your working notes, the component ids it already enumerates for the shell, the landing layout, and the project view. This file is the existing component-id contract; do NOT create a parallel inventory, a new id-manifest file, or a duplicate test module.
9. Read tests/test_cost_summary.py and tests/test_agent_llm_selection.py and record the relative-ordering assertions they make (cost card between transcript and token count; model chip before status line). These orderings must survive every later phase.
10. Read src/spec4/app_constants.py and confirm AGENT_KEYS is the single definition of the seven-agent pipeline order, and read src/spec4/layouts/__init__.py to locate the existing _AGENT_ROWS table asserted against it.
11. Read src/spec4/project_manager.py and record the exact names of the functions that expose artifact staleness (detect_stale_inputs) and agent readiness (agent_button_state), plus the shape of what they return. Later phases consume these unchanged and must not re-derive status.
12. Read src/spec4/session.py and src/spec4/llm_selection.py and record how working directory, current round, and the default provider/model are obtained, noting that all state lives in the two browser dcc.Stores (session in sessionStorage, prefs in localStorage) and must be threaded into server-side callbacks as State.
13. Open .spec4/v0/design/mock.html in a browser and read .spec4/v0/design/manifest.json. Record the target visual register for the project-view screen and its four surfaces (status-bar, round-tree, agent-rows, round-cost) as the reference all later phases match against.
14. Add a single new pytest case to tests/test_callback_co_presence.py named test_agent_keys_is_single_pipeline_order that asserts spec4.app_constants.AGENT_KEYS has exactly seven entries and that the existing layouts agent table is derived from or equal to it in order. Use a new test name; do not rename or delete any existing test.

## Risk Assessment

**Potential bottlenecks:**

The mypy strict gate has no documented invocation, so its first run may surface a large volume of pre-existing errors that look like this phase's responsibility. The gunicorn path may behave differently from the dev server for asset loading. Reading the co-presence test can tempt the agent to 'improve' it by restructuring the id lists.

**Mitigation strategy:**

Treat every pre-existing mypy error as baseline and out of scope — record the count, fix nothing unrelated, and do not add ignores to silence them. Verify both serving paths explicitly rather than assuming parity. Change exactly one thing in tests/: the additive AGENT_KEYS ordering test. Leave the existing id enumerations byte-for-byte alone; later phases will extend them as screens actually change.

## Verification

`uv build` succeeds; `uv run ruff check src/ tests/` is clean; `uv run pytest` passes with the recorded baseline count plus the one new test (test_agent_keys_is_single_pipeline_order); `uv run python src/spec4/app.py` and the gunicorn command each serve a rendering page at http://localhost:8050. The baseline pytest count, the mypy output, and the list of ids already enumerated in tests/test_callback_co_presence.py are all recorded in the phase notes.

## References

- [Dash for Python](https://dash.plotly.com/)
- [Dash Mantine Components](https://www.dash-mantine-components.com/)
- [pytest](https://docs.pytest.org/)
- [Ruff](https://docs.astral.sh/ruff/)
- [mypy](https://mypy.readthedocs.io/)
- [uv](https://docs.astral.sh/uv/)
- [Gunicorn](https://docs.gunicorn.org/)
- [Spec4 design mock (unique to this project)](.spec4/v0/design/mock.html)
- [Spec4 design manifest (unique to this project)](.spec4/v0/design/manifest.json)
