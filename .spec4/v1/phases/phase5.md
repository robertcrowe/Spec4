---
{
  "phase_number": 5,
  "total_phases": 8,
  "phase_title": "Artifact Download and Open-Rendered for the Design Mock",
  "phase_summary": "Complete the Artifact View's controls: a Download button that always offers a copy of the currently viewed file, and — for design/mock.html only — an Open-rendered button that opens the mock in a new tab using the clientside blob pattern already proven on mock-fullscreen-btn.",
  "features": [
    {
      "id": "artifact_view",
      "role": "extended",
      "scope_note": "Download and the mock's Open-rendered control land here, completing the Artifact View screen."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "dash",
      "dash-mantine-components",
      "pathlib (Python 3.12 stdlib)",
      "pytest",
      "playwright",
      "ruff",
      "mypy"
    ],
    "configurations": "No new environment variables. dcc.Download and dcc.send_file are part of Dash core — no new dependency. The download source path is produced solely by the Phase 3 confined resolver."
  },
  "instructions": [
    "Read .spec4/v1/design/mock.html for the placement and register of the Download and Open-rendered controls. Lane assignments come exclusively from _round_tree.ROUND_ARTIFACTS, never from the mock's sample data, which misfiles deployment-plan.md.",
    "Add a dcc.Download component with id artifact-download to the Artifact View layout in src/spec4/layouts/_artifact_view.py, and a Download button with id artifact-download-btn placed beside the content-pane header. Render the button as a neutral outline with no colour set on the component (D-LR2).",
    "Write the download callback in src/spec4/callbacks/: Input is the Download button's n_clicks with prevent_initial_call=True, State is the session-store selection. Pass the requested round and path through the Phase 3 confined resolver and call dcc.send_file only on the resolver's allowed-and-present result — never build a path for send_file from the raw session-store value.",
    "Disable the Download button when no file is selected or when the selected artifact is missing, so the control is never offered for something that cannot be produced.",
    "Add an Open-rendered button with id artifact-open-rendered-btn that is present only when the selected file is design/mock.html, matching the attached Artifact View specification's requirement that the mock be openable in rendered form separate from its raw text.",
    "Open src/spec4/app.py and locate the existing clientside callback attached to mock-fullscreen-btn. Reuse that exact blob pattern for artifact-open-rendered-btn — build a Blob of type text/html, create an object URL, and open it in a new tab — rather than writing a new mechanism or serving the mock through a Flask route.",
    "Feed the mock's HTML text to the clientside callback through a dcc.Store populated server-side by the same resolver-gated read used for the content pane, so the raw HTML never comes from a client-supplied path.",
    "Add tests in tests/test_artifact_view.py asserting: the download callback returns a send_file payload for an allowed present artifact, returns no payload (and never calls send_file) for a rejected or missing path, and the Open-rendered button is present for design/mock.html and absent for every other artifact.",
    "Add a Playwright end-to-end test that selects design/mock.html, clicks Open rendered, and asserts a new browser tab opens with rendered HTML rather than raw text.",
    "Run `uv run ruff check src/ tests/`, `uv run ruff format src/ tests/`, and `uv run mypy src/`, fixing every finding introduced by this phase."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "dcc.send_file takes a filesystem path, which makes it the single most likely place for the confinement boundary to be bypassed — an AI coder may pass the session-store path straight through. The clientside blob pattern is easy to reimplement incorrectly (popup blocking, revoking the object URL too early, or wrong MIME type causing the browser to download instead of render). Playwright's new-tab assertion requires handling the popup event rather than the current page.",
    "mitigation_strategy": "Route every download through the Phase 3 resolver and assert in a test that send_file is never reached for a rejected path. Copy the mock-fullscreen-btn clientside function structure verbatim, including its object-URL lifetime handling and text/html MIME type, rather than composing a new one. In the Playwright test, use the page's expect_popup context manager to capture the new tab."
  },
  "verification": "Run `uv run pytest` — the full suite plus the new download and open-rendered tests pass. Then run `uv run python src/spec4/app.py`, open /artifacts, select stack.json and click Download: the file downloads with its correct name and content. Select design/mock.html and click Open rendered: a new tab opens showing the rendered mock, not its source text. Select a missing artifact and confirm Download is disabled. Confirms nfr_viewing_or_obtaining_a_copy_of_an_artifact_works_consistently_regardless_of_round_or_file_size__without_noticeable_delay_for_typical_spec_file_sizes_ and nfr_all_artifact_reads_are_strictly_confined_to_the_current_project_s_spec_folder__with_no_other_path_ever_reachable_.",
  "references": [
    {
      "standard": "Dash dcc.Download",
      "url": "https://dash.plotly.com/dash-core-components/download"
    },
    {
      "standard": "Dash clientside callbacks",
      "url": "https://dash.plotly.com/clientside-callbacks"
    },
    {
      "standard": "MDN — URL.createObjectURL",
      "url": "https://developer.mozilla.org/en-US/docs/Web/API/URL/createObjectURL_static"
    },
    {
      "standard": "MDN — Blob",
      "url": "https://developer.mozilla.org/en-US/docs/Web/API/Blob"
    },
    {
      "standard": "Playwright for Python",
      "url": "https://playwright.dev/python/docs/intro"
    }
  ]
}
---

# Phase 5 of 8: Artifact Download and Open-Rendered for the Design Mock

Complete the Artifact View's controls: a Download button that always offers a copy of the currently viewed file, and — for design/mock.html only — an Open-rendered button that opens the mock in a new tab using the clientside blob pattern already proven on mock-fullscreen-btn.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Artifact View — product feature — extended in this phase

*Scope for this phase: Download and the mock's Open-rendered control land here, completing the Artifact View screen.*

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
- pathlib (Python 3.12 stdlib)
- pytest
- playwright
- ruff
- mypy

**Configurations:** No new environment variables. dcc.Download and dcc.send_file are part of Dash core — no new dependency. The download source path is produced solely by the Phase 3 confined resolver.

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- round_artifacts (persistence) — serves `artifact_view`
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

1. Read .spec4/v1/design/mock.html for the placement and register of the Download and Open-rendered controls. Lane assignments come exclusively from _round_tree.ROUND_ARTIFACTS, never from the mock's sample data, which misfiles deployment-plan.md.
2. Add a dcc.Download component with id artifact-download to the Artifact View layout in src/spec4/layouts/_artifact_view.py, and a Download button with id artifact-download-btn placed beside the content-pane header. Render the button as a neutral outline with no colour set on the component (D-LR2).
3. Write the download callback in src/spec4/callbacks/: Input is the Download button's n_clicks with prevent_initial_call=True, State is the session-store selection. Pass the requested round and path through the Phase 3 confined resolver and call dcc.send_file only on the resolver's allowed-and-present result — never build a path for send_file from the raw session-store value.
4. Disable the Download button when no file is selected or when the selected artifact is missing, so the control is never offered for something that cannot be produced.
5. Add an Open-rendered button with id artifact-open-rendered-btn that is present only when the selected file is design/mock.html, matching the attached Artifact View specification's requirement that the mock be openable in rendered form separate from its raw text.
6. Open src/spec4/app.py and locate the existing clientside callback attached to mock-fullscreen-btn. Reuse that exact blob pattern for artifact-open-rendered-btn — build a Blob of type text/html, create an object URL, and open it in a new tab — rather than writing a new mechanism or serving the mock through a Flask route.
7. Feed the mock's HTML text to the clientside callback through a dcc.Store populated server-side by the same resolver-gated read used for the content pane, so the raw HTML never comes from a client-supplied path.
8. Add tests in tests/test_artifact_view.py asserting: the download callback returns a send_file payload for an allowed present artifact, returns no payload (and never calls send_file) for a rejected or missing path, and the Open-rendered button is present for design/mock.html and absent for every other artifact.
9. Add a Playwright end-to-end test that selects design/mock.html, clicks Open rendered, and asserts a new browser tab opens with rendered HTML rather than raw text.
10. Run `uv run ruff check src/ tests/`, `uv run ruff format src/ tests/`, and `uv run mypy src/`, fixing every finding introduced by this phase.

## Risk Assessment

**Potential bottlenecks:**

dcc.send_file takes a filesystem path, which makes it the single most likely place for the confinement boundary to be bypassed — an AI coder may pass the session-store path straight through. The clientside blob pattern is easy to reimplement incorrectly (popup blocking, revoking the object URL too early, or wrong MIME type causing the browser to download instead of render). Playwright's new-tab assertion requires handling the popup event rather than the current page.

**Mitigation strategy:**

Route every download through the Phase 3 resolver and assert in a test that send_file is never reached for a rejected path. Copy the mock-fullscreen-btn clientside function structure verbatim, including its object-URL lifetime handling and text/html MIME type, rather than composing a new one. In the Playwright test, use the page's expect_popup context manager to capture the new tab.

## Verification

Run `uv run pytest` — the full suite plus the new download and open-rendered tests pass. Then run `uv run python src/spec4/app.py`, open /artifacts, select stack.json and click Download: the file downloads with its correct name and content. Select design/mock.html and click Open rendered: a new tab opens showing the rendered mock, not its source text. Select a missing artifact and confirm Download is disabled. Confirms nfr_viewing_or_obtaining_a_copy_of_an_artifact_works_consistently_regardless_of_round_or_file_size__without_noticeable_delay_for_typical_spec_file_sizes_ and nfr_all_artifact_reads_are_strictly_confined_to_the_current_project_s_spec_folder__with_no_other_path_ever_reachable_.

## References

- [Dash dcc.Download](https://dash.plotly.com/dash-core-components/download)
- [Dash clientside callbacks](https://dash.plotly.com/clientside-callbacks)
- [MDN — URL.createObjectURL](https://developer.mozilla.org/en-US/docs/Web/API/URL/createObjectURL_static)
- [MDN — Blob](https://developer.mozilla.org/en-US/docs/Web/API/Blob)
- [Playwright for Python](https://playwright.dev/python/docs/intro)
