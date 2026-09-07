---
{
  "phase_number": 3,
  "total_phases": 7,
  "phase_title": "Round Tree — Current Round's Artifacts With Lanes and Live Status",
  "phase_summary": "Render the current round's .spec4/v{N}/ folder as the project view's first element: one line per Artifact in pipeline order, each with a live present / needs-update / missing status derived from the existing dependency graph, lane colouring, and a three-item legend. Status is recomputed from disk on every render and never cached.",
  "features": [
    {
      "id": "round_tree",
      "role": "introduced",
      "scope_note": ""
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
    "configurations": "No new env vars. Reads Artifact files from the local filesystem under .spec4/v{N}/ (the artifact_store), and reads the active WorkingDirectory and Round from the existing session dcc.Store threaded in as callback State. Tree layout lives in src/spec4/layouts/, its callback in src/spec4/callbacks/, and lane styling in src/spec4/assets/v3.css."
  },
  "instructions": [
    "Open .spec4/v0/design/mock.html and match the round-tree surface's line layout, lane colours, and legend placement; the manifest's TreeLine entity (path, lane, status) is the shape each rendered line carries.",
    "Define the fixed artifact-to-lane mapping as a single module-level constant in src/spec4/layouts/ (or app_constants.py, alongside AGENT_KEYS) — a reviewed, explicit table, not inferred from filename patterns. The three lanes are: prompts-for-the-agent (phases/), reference-for-the-agent (code_review.json, vision.json, feature_specs.json, ai_features.json, design/mock.html, design/manifest.json, stack.json), and a-record-for-you (deployment-plan.md, usage.json). This constant is the mitigation for the wrong-lane failure mode in the specification above.",
    "Order the tree's lines by pipeline order, deriving that order from spec4.app_constants.AGENT_KEYS rather than hand-listing filenames, so the tree cannot drift from the pipeline definition.",
    "Write a function in src/spec4/layouts/ that takes the resolved working directory and round number and returns the list of TreeLine records: for each artifact in the mapping, its path, its lane, and its status.",
    "Derive status from src/spec4/project_manager.py's existing dependency graph and staleness detection (detect_stale_inputs) as-is. Do not re-implement mtime comparison, and do not add any artifact to the dependency graph.",
    "Render usage.json's status from file presence ONLY — present if the file exists, missing if it does not. usage.json is deliberately excluded from the dependency graph and must never be shown as needing update, because including it would mark downstream agents stale after every run.",
    "When an artifact file is absent from disk, emit its line with the missing status rather than omitting the line, so every artifact in the mapping appears exactly once on every render.",
    "Render each artifact path in the monospace font, apply the lane colour as a CSS class from v3.css, and render the status as a short text token — no icons and no emoji.",
    "Render a three-item legend naming all three lanes, using the same lane classes as the lines so legend and lines cannot drift apart.",
    "Write the tree's callback in src/spec4/callbacks/ so it recomputes the full line list from disk on every project-view render and on every change of the session store's round or working directory. Do not memoise, cache, or store the computed result in a dcc.Store.",
    "Place the round tree as the first element of the project view, directly beneath the status bar, with a NEW component id; keep every existing project-view id.",
    "Show only the current round's artifacts. Do not render lines for any other round's folder, and do not make the tree lines clickable — opening a file is a later round's work.",
    "Add pytest cases that call the tree-line function with a temporary directory fixture and assert: every artifact in the mapping appears exactly once; a file absent from the fixture yields the missing status; a fixture where an upstream artifact is newer than a downstream one yields needs-update for the downstream artifact; and usage.json is never returned with needs-update even when every upstream artifact is newer than it.",
    "Add a pytest case asserting the tree's line order matches AGENT_KEYS-derived pipeline order, and one asserting every line's lane is one of the three lane values and matches the fixed mapping.",
    "Extend tests/test_callback_co_presence.py with the round tree's new ids for the project view."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "The usage.json exemption is easy to lose: a straightforward 'compute status for every line the same way' implementation will mark it needs-update and, worse, invite adding it to the dependency graph. Status computed once and stashed in a dcc.Store will go stale the moment an agent writes a file. Lane assignment inferred from file extension or directory will misfile design/mock.html and deployment-plan.md.",
    "mitigation_strategy": "Special-case usage.json explicitly in the status function with a D-XX comment explaining why, and add the dedicated test that upstream changes never make it needs-update. Recompute the whole line list inside the render callback with no caching layer, and add no dcc.Store for tree state. Encode lanes in the reviewed constant table and assert each line's lane against that table in a test, so no inference path exists."
  },
  "verification": "`uv run pytest` passes with the new round-tree cases: full-coverage of the artifact mapping, missing-file status, upstream-newer yields needs-update, usage.json never needs-update, pipeline ordering matches AGENT_KEYS, and lane assignment matches the fixed mapping. `uv run ruff check src/ tests/` is clean. Loading the project view at http://localhost:8050 shows the tree as the first element under the status bar, one monospace line per artifact in pipeline order with a status and lane colour, and a three-item legend; touching a file on disk and reloading changes its status. Manual check: the tree matches .spec4/v0/design/mock.html. Goals verified here: nfr_status_information__round__artifact_state__cost__always_reflects_the_true_current_state_of_the_working_directory__never_a_stale_cached_view (status recomputed from disk on every render, nothing cached) and nfr_the_project_view_remains_fully_usable_without_any_network_access_beyond_explicit_llm_calls (the tree reads only the local filesystem).",
  "references": [
    {
      "standard": "Dash Mantine Components",
      "url": "https://www.dash-mantine-components.com/"
    },
    {
      "standard": "Dash — Advanced Callbacks",
      "url": "https://dash.plotly.com/advanced-callbacks"
    },
    {
      "standard": "pytest — tmp_path fixture",
      "url": "https://docs.pytest.org/en/stable/how-to/tmp_path.html"
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

# Phase 3 of 7: Round Tree — Current Round's Artifacts With Lanes and Live Status

Render the current round's .spec4/v{N}/ folder as the project view's first element: one line per Artifact in pipeline order, each with a live present / needs-update / missing status derived from the existing dependency graph, lane colouring, and a three-item legend. Status is recomputed from disk on every render and never cached.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Round Tree — product feature — introduced in this phase

Gives the user an at-a-glance, ordered view of every artifact in the current round and whether each is present, needs updating, or missing, so they know what to work on next.

**Invocation**

- Trigger: The project view loads or the active round changes

**Inputs**

- `current_round_artifacts` (list of items, required) — The set of artifacts belonging to the current round in pipeline order
- `artifact_dependency_graph` (structured data, required) — Relationships used to determine whether an artifact is stale relative to its upstream artifacts
- `usage_record` (structured data, required) — The round's recorded usage information, used to exempt it from staleness checks

**Outputs**

- Primary: A single-round tree listing each artifact with its status and lane coloring
- Format: ordered list with a legend
- Schema notes: One line per artifact in pipeline order; status is one of present, needs update, or missing; lane is one of prompt-for-agent, reference-for-agent, or record-for-you; a three-item legend explains the lanes

**Success criteria**

- Every artifact in the current round appears exactly once, in pipeline order
- An artifact's status correctly reflects whether any upstream artifact is newer
- The usage record is never shown as needing update regardless of upstream changes
- Only the current round's artifacts appear; no other round's artifacts are shown
- Each artifact's lane coloring matches its designated category and the legend accurately describes all three lanes

**Failure modes**

- Status is computed incorrectly due to an incomplete dependency graph (likelihood: medium) — mitigation: Recompute status directly from the current dependency graph on every load rather than caching a prior result
- An artifact is missing from disk but expected (likelihood: medium) — mitigation: Represent absence explicitly as the missing status rather than omitting the line
- An artifact is placed in the wrong lane (likelihood: low) — mitigation: Derive lane assignment from a fixed, reviewed mapping rather than inference

- depends on: development_tool_shell (build these no later than `round_tree`)
- entities: Round, Artifact, WorkingDirectory

### UI surfaces for this phase (from the design)

- **`round-tree`** [non_ai]
  - screens: project-view
  - output: Mono heading .spec4/v{N}/, one full-width line per artifact in pipeline order coloured by lane (reference lane uncoloured), status at right only when 'needs update' or 'missing', three-item lane legend
  - states: idle, needs-update, missing
  - reads: Artifact, Round, UsageRecord
  - after (advisory UI ordering): status-bar

## Tech Stack

**Dependencies:**

- dash
- dash-mantine-components
- pytest
- ruff
- mypy

**Configurations:** No new env vars. Reads Artifact files from the local filesystem under .spec4/v{N}/ (the artifact_store), and reads the active WorkingDirectory and Round from the existing session dcc.Store threaded in as callback State. Tree layout lives in src/spec4/layouts/, its callback in src/spec4/callbacks/, and lane styling in src/spec4/assets/v3.css.

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- round_artifacts (persistence) — serves `round_tree`

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

1. Open .spec4/v0/design/mock.html and match the round-tree surface's line layout, lane colours, and legend placement; the manifest's TreeLine entity (path, lane, status) is the shape each rendered line carries.
2. Define the fixed artifact-to-lane mapping as a single module-level constant in src/spec4/layouts/ (or app_constants.py, alongside AGENT_KEYS) — a reviewed, explicit table, not inferred from filename patterns. The three lanes are: prompts-for-the-agent (phases/), reference-for-the-agent (code_review.json, vision.json, feature_specs.json, ai_features.json, design/mock.html, design/manifest.json, stack.json), and a-record-for-you (deployment-plan.md, usage.json). This constant is the mitigation for the wrong-lane failure mode in the specification above.
3. Order the tree's lines by pipeline order, deriving that order from spec4.app_constants.AGENT_KEYS rather than hand-listing filenames, so the tree cannot drift from the pipeline definition.
4. Write a function in src/spec4/layouts/ that takes the resolved working directory and round number and returns the list of TreeLine records: for each artifact in the mapping, its path, its lane, and its status.
5. Derive status from src/spec4/project_manager.py's existing dependency graph and staleness detection (detect_stale_inputs) as-is. Do not re-implement mtime comparison, and do not add any artifact to the dependency graph.
6. Render usage.json's status from file presence ONLY — present if the file exists, missing if it does not. usage.json is deliberately excluded from the dependency graph and must never be shown as needing update, because including it would mark downstream agents stale after every run.
7. When an artifact file is absent from disk, emit its line with the missing status rather than omitting the line, so every artifact in the mapping appears exactly once on every render.
8. Render each artifact path in the monospace font, apply the lane colour as a CSS class from v3.css, and render the status as a short text token — no icons and no emoji.
9. Render a three-item legend naming all three lanes, using the same lane classes as the lines so legend and lines cannot drift apart.
10. Write the tree's callback in src/spec4/callbacks/ so it recomputes the full line list from disk on every project-view render and on every change of the session store's round or working directory. Do not memoise, cache, or store the computed result in a dcc.Store.
11. Place the round tree as the first element of the project view, directly beneath the status bar, with a NEW component id; keep every existing project-view id.
12. Show only the current round's artifacts. Do not render lines for any other round's folder, and do not make the tree lines clickable — opening a file is a later round's work.
13. Add pytest cases that call the tree-line function with a temporary directory fixture and assert: every artifact in the mapping appears exactly once; a file absent from the fixture yields the missing status; a fixture where an upstream artifact is newer than a downstream one yields needs-update for the downstream artifact; and usage.json is never returned with needs-update even when every upstream artifact is newer than it.
14. Add a pytest case asserting the tree's line order matches AGENT_KEYS-derived pipeline order, and one asserting every line's lane is one of the three lane values and matches the fixed mapping.
15. Extend tests/test_callback_co_presence.py with the round tree's new ids for the project view.

## Risk Assessment

**Potential bottlenecks:**

The usage.json exemption is easy to lose: a straightforward 'compute status for every line the same way' implementation will mark it needs-update and, worse, invite adding it to the dependency graph. Status computed once and stashed in a dcc.Store will go stale the moment an agent writes a file. Lane assignment inferred from file extension or directory will misfile design/mock.html and deployment-plan.md.

**Mitigation strategy:**

Special-case usage.json explicitly in the status function with a D-XX comment explaining why, and add the dedicated test that upstream changes never make it needs-update. Recompute the whole line list inside the render callback with no caching layer, and add no dcc.Store for tree state. Encode lanes in the reviewed constant table and assert each line's lane against that table in a test, so no inference path exists.

## Verification

`uv run pytest` passes with the new round-tree cases: full-coverage of the artifact mapping, missing-file status, upstream-newer yields needs-update, usage.json never needs-update, pipeline ordering matches AGENT_KEYS, and lane assignment matches the fixed mapping. `uv run ruff check src/ tests/` is clean. Loading the project view at http://localhost:8050 shows the tree as the first element under the status bar, one monospace line per artifact in pipeline order with a status and lane colour, and a three-item legend; touching a file on disk and reloading changes its status. Manual check: the tree matches .spec4/v0/design/mock.html. Goals verified here: nfr_status_information__round__artifact_state__cost__always_reflects_the_true_current_state_of_the_working_directory__never_a_stale_cached_view (status recomputed from disk on every render, nothing cached) and nfr_the_project_view_remains_fully_usable_without_any_network_access_beyond_explicit_llm_calls (the tree reads only the local filesystem).

## References

- [Dash Mantine Components](https://www.dash-mantine-components.com/)
- [Dash — Advanced Callbacks](https://dash.plotly.com/advanced-callbacks)
- [pytest — tmp_path fixture](https://docs.pytest.org/en/stable/how-to/tmp_path.html)
- [Spec4 design mock (unique to this project)](.spec4/v0/design/mock.html)
- [Spec4 design manifest (unique to this project)](.spec4/v0/design/manifest.json)
