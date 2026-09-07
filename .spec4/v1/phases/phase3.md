---
{
  "phase_number": 3,
  "total_phases": 8,
  "phase_title": "Confined Artifact Resolution and Rounds-on-Disk Enumeration",
  "phase_summary": "Build the security boundary the Artifact View sits behind: a resolver that accepts only paths present in the reviewed artifact table, resolved under the project's .spec4/ folder, rejecting anything else before the filesystem is touched. Also add rounds-on-disk enumeration so the round selector has a live list. No UI is built in this phase — this is the guarded data layer the next two phases render.",
  "features": [
    {
      "id": "artifact_view",
      "role": "extended",
      "scope_note": "The confined path resolver, file metadata lookup, and rounds enumeration land here; the screen that renders them lands in Phase 4."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "pathlib (Python 3.12 stdlib)",
      "json (Python 3.12 stdlib)",
      "os (Python 3.12 stdlib)",
      "pytest",
      "mypy",
      "ruff"
    ],
    "configurations": "No new environment variables. The resolution base is the directory returned by project_manager.get_version_dir for the requested round, itself under the project's working directory .spec4/ folder. No path outside .spec4/ is reachable through this code path."
  },
  "instructions": [
    "Place the resolver in src/spec4/layouts/_artifact_view.py, beside the artifact table it validates against. Do NOT put it in src/spec4/project_manager.py: layouts imports project_manager, and project_manager must never import layouts — adding it there would create a circular import.",
    "Implement a function in _artifact_view.py that builds the allowed file set for a given round: iterate _round_tree.ROUND_ARTIFACTS and, for the phases/ entry, expand it to the .md files actually present on disk in that round's phases/ directory. Every other entry contributes its fixed relative path. Return the allowed set keyed by relative path, each carrying its lane and its producing Agent as recorded in ROUND_ARTIFACTS.",
    "Implement the resolver function taking a round identifier and a requested relative path. Order the checks so rejection happens before any filesystem access of the requested path: (1) reject a requested path that is absolute; (2) reject a requested path containing any '..' segment; (3) reject a requested path not present in the allowed set for that round. Only after all three pass, join it under project_manager.get_version_dir(round) and resolve it.",
    "After resolving, assert with pathlib that the resolved path is relative_to the resolved version directory, and reject if it is not — this catches a symlinked entry escaping the folder even though its relative path was in the allowed set. Return a typed result that distinguishes rejected, allowed-and-present, and allowed-but-missing; the allowed-but-missing case carries the producing Agent so the UI can state who produces it.",
    "For the allowed-and-present case, return the file's size in bytes and last-modified timestamp from a single os.stat call, alongside the lane. Do not read file contents in this function — content reading belongs to the render path in Phase 4.",
    "Add a rounds-on-disk enumeration function to src/spec4/project_manager.py that lists every v{N} round directory present under the project's .spec4/ folder, sorted by round number, and returns them alongside which one is the active round. Recompute from disk on every call — never cache — so a newly created round appears immediately, as the attached Artifact View specification's failure modes require.",
    "Create tests/test_artifact_view.py with a path-confinement test class that asserts rejection for, at minimum: a traversal attempt such as '../../etc/passwd', a nested traversal such as 'phases/../../../secrets.env', an absolute path such as '/etc/passwd', a plausible-but-unlisted file such as 'notes.txt', and a file listed for a different round. Assert each is rejected and that the rejection happens without the filesystem being touched for the requested path (patch the stat/open call site and assert it was never called).",
    "Add tests asserting the positive cases: every fixed entry in _round_tree.ROUND_ARTIFACTS resolves for a round fixture, phases/ expands to exactly the .md files present in the fixture, usage.json resolves, and an entry that is listed but absent on disk returns the allowed-but-missing result carrying its producing Agent.",
    "Add a test for the rounds enumeration asserting that creating a new v{N} directory in a tmp_path project fixture causes it to appear on the very next call with no restart or cache invalidation.",
    "Run `uv run ruff check src/ tests/`, `uv run ruff format src/ tests/`, and `uv run mypy src/` — the resolver's return type must be explicit and satisfy mypy strict."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "Path-confinement code is a classic hallucination site: an AI coder may reach for a string prefix comparison such as startswith(), which is defeated by symlinks and by sibling directories sharing a name prefix, or may call resolve() on attacker-supplied input before validating it. Placement is the other trap — project_manager.py looks like the natural home but would create a circular import with layouts. The phases/ dynamic expansion can also be mistakenly treated as a fixed filename.",
    "mitigation_strategy": "Enforce the allow-list first and the filesystem second, and make that ordering an explicit, tested property (assert the stat call site is never reached on rejection). Use pathlib's relative_to against the resolved version directory as the final containment check, never a string startswith. Keep the resolver in layouts/_artifact_view.py per the stated module boundary, importing project_manager.get_version_dir only. Derive the phases/ file list from a directory glob at call time and assert it in tests against fixture files created by the test itself."
  },
  "verification": "Run `uv run pytest tests/test_artifact_view.py -v` — every path-confinement rejection test and every positive-resolution test passes, including the assertion that no filesystem access occurs for a rejected request. Then run the full `uv run pytest` to confirm no regression, and `uv run mypy src/` for strict-mode cleanliness. Confirms nfr_all_artifact_reads_are_strictly_confined_to_the_current_project_s_spec_folder__with_no_other_path_ever_reachable_ — proven directly by the traversal, absolute-path, and unlisted-file rejection tests.",
  "references": [
    {
      "standard": "Python pathlib",
      "url": "https://docs.python.org/3/library/pathlib.html"
    },
    {
      "standard": "Python os.stat",
      "url": "https://docs.python.org/3/library/os.html#os.stat"
    },
    {
      "standard": "pytest tmp_path fixture",
      "url": "https://docs.pytest.org/en/stable/how-to/tmp_path.html"
    },
    {
      "standard": "mypy strict mode",
      "url": "https://mypy.readthedocs.io/en/stable/command_line.html#cmdoption-mypy-strict"
    }
  ]
}
---

# Phase 3 of 8: Confined Artifact Resolution and Rounds-on-Disk Enumeration

Build the security boundary the Artifact View sits behind: a resolver that accepts only paths present in the reviewed artifact table, resolved under the project's .spec4/ folder, rejecting anything else before the filesystem is touched. Also add rounds-on-disk enumeration so the round selector has a live list. No UI is built in this phase — this is the guarded data layer the next two phases render.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Artifact View — product feature — extended in this phase

*Scope for this phase: The confined path resolver, file metadata lookup, and rounds enumeration land here; the screen that renders them lands in Phase 4.*

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

- pathlib (Python 3.12 stdlib)
- json (Python 3.12 stdlib)
- os (Python 3.12 stdlib)
- pytest
- mypy
- ruff

**Configurations:** No new environment variables. The resolution base is the directory returned by project_manager.get_version_dir for the requested round, itself under the project's working directory .spec4/ folder. No path outside .spec4/ is reachable through this code path.

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

1. Place the resolver in src/spec4/layouts/_artifact_view.py, beside the artifact table it validates against. Do NOT put it in src/spec4/project_manager.py: layouts imports project_manager, and project_manager must never import layouts — adding it there would create a circular import.
2. Implement a function in _artifact_view.py that builds the allowed file set for a given round: iterate _round_tree.ROUND_ARTIFACTS and, for the phases/ entry, expand it to the .md files actually present on disk in that round's phases/ directory. Every other entry contributes its fixed relative path. Return the allowed set keyed by relative path, each carrying its lane and its producing Agent as recorded in ROUND_ARTIFACTS.
3. Implement the resolver function taking a round identifier and a requested relative path. Order the checks so rejection happens before any filesystem access of the requested path: (1) reject a requested path that is absolute; (2) reject a requested path containing any '..' segment; (3) reject a requested path not present in the allowed set for that round. Only after all three pass, join it under project_manager.get_version_dir(round) and resolve it.
4. After resolving, assert with pathlib that the resolved path is relative_to the resolved version directory, and reject if it is not — this catches a symlinked entry escaping the folder even though its relative path was in the allowed set. Return a typed result that distinguishes rejected, allowed-and-present, and allowed-but-missing; the allowed-but-missing case carries the producing Agent so the UI can state who produces it.
5. For the allowed-and-present case, return the file's size in bytes and last-modified timestamp from a single os.stat call, alongside the lane. Do not read file contents in this function — content reading belongs to the render path in Phase 4.
6. Add a rounds-on-disk enumeration function to src/spec4/project_manager.py that lists every v{N} round directory present under the project's .spec4/ folder, sorted by round number, and returns them alongside which one is the active round. Recompute from disk on every call — never cache — so a newly created round appears immediately, as the attached Artifact View specification's failure modes require.
7. Create tests/test_artifact_view.py with a path-confinement test class that asserts rejection for, at minimum: a traversal attempt such as '../../etc/passwd', a nested traversal such as 'phases/../../../secrets.env', an absolute path such as '/etc/passwd', a plausible-but-unlisted file such as 'notes.txt', and a file listed for a different round. Assert each is rejected and that the rejection happens without the filesystem being touched for the requested path (patch the stat/open call site and assert it was never called).
8. Add tests asserting the positive cases: every fixed entry in _round_tree.ROUND_ARTIFACTS resolves for a round fixture, phases/ expands to exactly the .md files present in the fixture, usage.json resolves, and an entry that is listed but absent on disk returns the allowed-but-missing result carrying its producing Agent.
9. Add a test for the rounds enumeration asserting that creating a new v{N} directory in a tmp_path project fixture causes it to appear on the very next call with no restart or cache invalidation.
10. Run `uv run ruff check src/ tests/`, `uv run ruff format src/ tests/`, and `uv run mypy src/` — the resolver's return type must be explicit and satisfy mypy strict.

## Risk Assessment

**Potential bottlenecks:**

Path-confinement code is a classic hallucination site: an AI coder may reach for a string prefix comparison such as startswith(), which is defeated by symlinks and by sibling directories sharing a name prefix, or may call resolve() on attacker-supplied input before validating it. Placement is the other trap — project_manager.py looks like the natural home but would create a circular import with layouts. The phases/ dynamic expansion can also be mistakenly treated as a fixed filename.

**Mitigation strategy:**

Enforce the allow-list first and the filesystem second, and make that ordering an explicit, tested property (assert the stat call site is never reached on rejection). Use pathlib's relative_to against the resolved version directory as the final containment check, never a string startswith. Keep the resolver in layouts/_artifact_view.py per the stated module boundary, importing project_manager.get_version_dir only. Derive the phases/ file list from a directory glob at call time and assert it in tests against fixture files created by the test itself.

## Verification

Run `uv run pytest tests/test_artifact_view.py -v` — every path-confinement rejection test and every positive-resolution test passes, including the assertion that no filesystem access occurs for a rejected request. Then run the full `uv run pytest` to confirm no regression, and `uv run mypy src/` for strict-mode cleanliness. Confirms nfr_all_artifact_reads_are_strictly_confined_to_the_current_project_s_spec_folder__with_no_other_path_ever_reachable_ — proven directly by the traversal, absolute-path, and unlisted-file rejection tests.

## References

- [Python pathlib](https://docs.python.org/3/library/pathlib.html)
- [Python os.stat](https://docs.python.org/3/library/os.html#os.stat)
- [pytest tmp_path fixture](https://docs.pytest.org/en/stable/how-to/tmp_path.html)
- [mypy strict mode](https://mypy.readthedocs.io/en/stable/command_line.html#cmdoption-mypy-strict)
