# Spec4 Cleanup Plan

Executed with Claude Code directly on the repo (no Spec4 round). Eight phases, each ending in a clean `pytest` / `ruff` / `mypy` run and a commit made by Robert, then `/clear`.

## Reframing

The original list (spaghetti, large files, dead code, unused files, globals, smells, stale tests) is a list of *symptoms*. Handing it over as-is invites Claude Code to fix them in whatever order it encounters them, which is how cleanups cause regressions. The better framing is:

> **Goal:** Reduce the cost of the next change to Spec4 without changing what Spec4 does.
> **Constraint:** Every phase is behavior-preserving. Observable behavior — CLI output, `.spec4/` artifact formats, component ids, URL routes, session-store keys, LLM prompt text — is identical before and after.
> **Method:** Measure first, build a safety net second, delete third, restructure fourth, rationalize tests last.

The seven symptom categories become acceptance criteria for the final audit rather than a to-do list.

## Rules that apply to every phase

1. **No commits.** Claude Code never runs `git commit`, `git add`, or `git stash`. It reports what changed; Robert commits.
2. **No writes under `.spec4/`, `.venv/`, `.git/`, `node_modules/`, or any cache dir.** The existing deny rule in `.claude/settings.json` stays in place. Nothing in those directories is ever a cleanup target.
3. **Behavior-preserving only.** If a real bug is found, append it to `CLEANUP_INVENTORY.md` under *Bugs found (not fixed)* and move on. Bug fixes are a separate commit with its own review.
4. **Public surfaces are frozen:** component ids, `PATH_TO_PHASE` keys, `.spec4/` file names and JSON/frontmatter shapes, `spec4-usage` CLI output, session-store keys, and every string that ends up in an LLM prompt. Refactoring around them is fine; changing them is not.
5. **`src/spec4/app.py` import ordering is load-bearing (D-LR1).** Do not reorder litellm-related imports, do not move `spec4.callbacks` imports above app construction, keep every `# noqa: E402`. Ruff's isort rule must remain suppressed there.
6. **Gate at the end of every phase:** `uv run ruff check src/ tests/`, `uv run ruff format --check src/ tests/`, `uv run mypy src/` (strict), `uv run pytest --cov=spec4`. The `=spec4` matters: bare `--cov` also measures the test files and inflates the total. Coverage on non-UI modules may not drop below the Phase 0 baseline.
7. **One concern per phase.** If a phase reveals work belonging to a later phase, note it in the inventory and leave it.
8. **Each phase ends with a short written report**: files touched, what was removed/moved, anything deferred, and the four gate results.

## Tooling

Nothing is added to `pyproject.toml` for measurement. Vulture and deptry run via `uvx` from an isolated cache; ruff and pytest features are already present. Only import-linter is ever installed, and only in Phase 4 if it is chosen over an assertion test.

| Tool | Used in | Purpose |
|---|---|---|
| **vulture** (`uvx vulture`) | 0, 2, 7 | Dead functions, classes, variables. Output is *candidates*: Dash callbacks are registered by decorator and will all be flagged. Keep a `vulture_whitelist.py` for them. |
| **deptry** (`uvx deptry .`) | 0, 2, 7 | Unused, missing, and transitive dependencies in `pyproject.toml`. |
| **ruff extra rule sets** | 0, 5, 7 | `C90` (complexity), `PLR0912/0913/0915` (branches/args/statements), `SIM`, `B`, `ARG`. Enabled only for measurement runs via `--select`; not added to the permanent config until Phase 5 has cleared them, or the gate fails from Phase 1 onward. Replaces radon. |
| **import-linter** | 4, 7 | Enforceable layering contract (`agents` and `project_manager` never import `layouts`; `app` is top-only). The one tool that would go in `pyproject.toml` (`uv add --dev import-linter`), because `lint-imports` then joins the permanent gate. Install in Phase 4 only if Phase 0 finds more than two or three boundaries worth guarding; otherwise a single import-assertion test suffices and nothing is installed. |
| **pytest `--durations`** | 6 | Built in. Finds the slow tests for the `slow` marker. |

Not used: radon (duplicates `C90`), pylint (overlaps ruff), pydeps/grimp (import-linter is the enforceable form), bandit/pip-audit (security, separate round).

## Phases

### Phase 0 — Baseline and inventory (no code changes)

**Purpose:** Know what "clean" means before touching anything, and have numbers to compare against at the end.

- Record the gate results verbatim into `CLEANUP_INVENTORY.md`: test count, pass/fail, coverage per module, ruff finding count, mypy status.
- Produce a file-size table for `src/spec4/**` and `tests/**` (lines, functions, longest function).
- Run a dead-code pass with `uvx vulture src/ tests/ --min-confidence 60` and `ruff check --select F401,F811,F841,ARG`. Record candidates; do not act. Create `vulture_whitelist.py` for the decorator-registered callbacks so later runs are quiet.
- Run `uvx deptry .` and record unused, missing, and transitive dependencies.
- Run `ruff check --select C90,PLR0912,PLR0913,PLR0915,SIM,B --statistics src/` and record the per-rule counts plus the ten worst functions by complexity. This is the "spaghetti" measurement for Phase 5.
- Import-graph inventory: for each module, list which other `spec4` modules it imports. Note any cycles and any `agents`/`project_manager` → `layouts` edge. Decide here whether import-linter is warranted (see *Tooling*).
- Grep-based cross-reference: for every module and every top-level function/class, list importers. Anything with zero importers outside its own file and outside tests is a candidate.
- Inventory module-level mutable state: every `global` statement, every module-level `dict`/`list`/`set`/lock/counter that is mutated after import, and every `threading` primitive at module scope.
- Test inventory: for each test file, which source module it targets, test count, and whether any test targets a function that no longer exists or is marked in the dead-code pass.
- Note that `tests/README.md`'s coverage table is stale (line numbers and `layouts.py` predate the `layouts/` package). Flag for Phase 7.

**Model/effort:** Sonnet 5, auto mode. This is measurement, not judgment.
**Deliverable:** `CLEANUP_INVENTORY.md` at repo root. Robert reviews it before Phase 1 starts — it is the scope document for everything that follows.

### Phase 0.5 — Green the gate

**Purpose:** Phase 0 found the gate red at baseline (130 files unformatted, 30 mypy errors, 1 failing test). Later phases need "all green" to mean something, and mixing formatting churn into real diffs makes review harder. Three commits, one per item.

- **0.5a — Format.** `uv run ruff format src/ tests/`. No other change. Tests must pass identically.
- **0.5b — Mypy.** Fix the 30 strict-mode errors using annotations, `cast`, narrowing, or `TYPE_CHECKING` imports only. Any error that would need a logic change is logged under *Bugs found (not fixed)* and left; the count is then ratcheted, not zeroed.
- **0.5c — Failing test.** Robert decides from the v1 chat-frame Designer brief whether `.chat-msg` blocks are meant to carry the `#12121a` surface. If yes, the assertion is stale and gets corrected; if no, the CSS is fixed. One-line change either way.

**Model/effort:** Sonnet 5, auto mode.
**Gate after this phase:** all four commands pass with zero findings. Rule 6 applies unmodified from here on.

### Phase 1 — Regression safety net for the untested UI layer

**Purpose:** `app.py`, `layouts/`, `callbacks`, and `streaming.py` have behavioural coverage (Phase 0 measured 89%, 90–100%, 74–77%, 90%) but no *contract* tests: nothing fails when a component id, a frozen artifact format, a renderer's output, or the contents of a module-level state container changes without breaking a behaviour. Phases 2–5 change exactly those things, so the contracts get pinned first. Phase 1 adds tests only.

- **Layout render smoke tests:** for every public layout function in `layouts/`, a test that calls it with a representative session fixture and asserts it returns a Dash component tree without raising. One parametrized test, not one test per screen.
- **Component-id contract snapshot:** walk every rendered layout, collect the set of string ids and pattern-matching id `type`s, and assert equality against a checked-in snapshot file. This makes rule 4 mechanically enforced. `tests/test_callback_co_presence.py` already covers callbacks-to-components; this covers the inverse direction.
- **App import smoke:** a test that imports `spec4.app` in a subprocess and asserts it constructs the Dash app and registers callbacks without error. Subprocess so the D-LR1 ordering is exercised exactly as at startup.
- **Streaming characterization:** a test that runs `streaming.py`'s background loop against a mocked LiteLLM stream and asserts the sequence of state transitions and the error-formatting paths. Capture current behavior, including anything odd — that is the point.
- **Golden artifact files:** for `project_manager.py`, a test that builds a phase file and a README through the real assembly path and compares against a checked-in golden. Frontmatter JSON shape and attribution footer are locked.
- **Golden renderer output:** every `_format_*_as_text` renderer (the Phase 0 inventory lists them; `_format_stack_as_text` at C901 61 is the largest) gets a golden test driven by a representative artifact fixture. These renderers write frozen surfaces and are Phase 5's biggest decomposition targets; they must be pinned here first.
- **Streaming state containers:** the characterization test asserts on the contents of `_STREAMS`, `_USAGE_RECORDS`, and `_MOCK_BUFFERS` at each transition, not only on the transition sequence. Phase 3 will move these; the test is what proves the move preserved behavior.

**Model/effort:** Opus 5, plan mode, high. Getting fixtures right for Dash layouts is fiddly; a wrong fixture gives a false sense of safety.
**Gate addition:** the per-module coverage numbers after this phase become the UI baseline for later phases. The layout tests call private `_*_layout` functions directly; when Phase 4 splits `layouts/`, that test file is a required edit in the same sub-phase.

### Phase 2 — Dead code and unused files

**Purpose:** Remove what is provably unreachable. Smallest possible diff per removal so the review is easy.

- Work strictly from the Phase 0 candidate list. For each candidate: confirm with grep across `src/`, `tests/`, `pyproject.toml` (`[project.scripts]`, entry points), and any Dash `callback` decorator that references it by string id. Remove only if all four are empty.
- Remove unused imports, unreachable branches (code after unconditional `return`/`raise`, `if False:`, feature flags that are constant), and functions/classes with zero callers.
- Remove orphan modules and orphan test files. An orphan test file is one whose target module is gone or whose every test targets removed code.
- Untrack `.coverage` (`git rm --cached`) and add it to `.gitignore`. Robert commits the removal; the pytest run in Phase 0 showed it being rewritten in place.
- Remove `dash-iconify` (deptry: unused). Add `gunicorn` and `pyyaml` to `[tool.deptry.ignore]` as known false positives. Run deptry as `uv run --with deptry deptry .` so it sees the project environment; the `uvx` form produces ~240 DEP001 noise lines.
- Remove other dependencies deptry reports as unused; add any it reports as missing (imported but not declared). Re-run `uv sync` and the full gate afterwards. Transitive-use findings are fixed by declaring the package directly, not by leaving it implicit.
- Re-run `uvx vulture` and `uvx deptry` at the end; both should be clean apart from whitelisted items.
- Keep any name that is re-exported from `spec4/__init__.py` or `spec4/agents/__init__.py` unless the re-export itself is unused.
- Check `README.md`'s project-structure tree and `CLAUDE.md` for references to deleted files; fix in place (documentation of deleted things is dead code too).

**Model/effort:** Sonnet 5, auto mode. Mechanical, but each removal must cite its evidence in the phase report.
**Do not:** rename, move, or refactor anything in this phase. Deletion only.

### Phase 3 — Module-level state and globals

**Purpose:** Every remaining `global` and mutable module-level object is either justified in a comment or converted to explicit state. This is one of the two riskiest phases.

- From the Phase 0 inventory, classify each item: (a) genuinely process-wide (the Dash app object, a registry populated once at import, a lock guarding a file write), (b) session state that leaked to module scope, (c) test-convenience state.
- (a) stays, gains a one-line comment stating why it is module-scoped and what guards it.
- (b) moves to the session dict or the browser `dcc.Store` payload per the existing pattern — no new server-side session mechanism. Callbacks that read it get it as an `Input`/`State`, not by import.
- (c) moves to fixtures.
- `streaming.py` is the most likely home of (b). Its Phase 1 characterization test must still pass with identical state-transition sequences.
- Import-time registries (agentifier's sub-agent registry, `providers.py`, `websearch.py`): if built once and read-only afterwards, wrap the construction in a named `_build_registry()`-style function so the module-level assignment is a single explicit call, and comment the result as category (a). Do not add init calls from `app.py` — that would create top-level import edges the layering deliberately avoids. A registry that is mutated after import is category (b) and gets the session-state treatment instead.

**Model/effort:** Opus 5, plan mode, ultrathink. Phase 0 found 8 items (0 `global` statements; `_STREAMS`, `_USAGE_RECORDS`, `_MOCK_BUFFERS`, `version_check._cache`, `project_manager._USAGE_LOCK`, `_registry`, one `lru_cache`, the `app.py` import side effects), so this runs as a single phase. The lock, the registry, and the `lru_cache` are almost certainly category (a); the three streaming containers and `version_check._cache` are the real work.

### Phase 4 — Large file decomposition

**Purpose:** Split files by cohesion, not by line count. Every split preserves import paths.

- Candidates from the Phase 0 size table. Likely: `project_manager.py` (directory helpers, artifact I/O, phase-file assembly, README handling are four concerns), `agents/code_scanner.py` (scan constants and file walking vs. the agent turn loop), `agents/_utils.py` (reask/replay/resume helpers vs. JSON extraction vs. style rendering), `session.py`, and whatever module holds the callbacks.
- Rule for each split: the original module keeps its name and re-exports every public name from the new sub-modules, so no importer changes in this phase. Importer cleanup is a later, optional pass. Underscore-prefixed names used across files get promoted to public names in the new module — no cross-module private imports.
- One file per sub-phase (4a, 4b, 4c…), each with its own commit. Never split two files in one sub-phase.
- No logic changes. If a function needs to change to be movable, that is a Phase 5 finding.
- Circular-import check after every split: the artifact resolver in `layouts/_artifact_view.py` was placed there specifically to avoid a `project_manager` ↔ `layouts` cycle; do not reintroduce one.
- Before 4a, write the layering contract as a single ast-based test in `tests/` asserting the three boundaries the Phase 0 inventory identified (no `agents`/`agentifier`/`project_manager` edge into `layouts`, `callbacks`, `app`, or `session`; nothing imports `app`). Import-linter is not installed — Phase 0 found too few boundaries to justify it. The test must pass on the unsplit code first, then after every sub-phase. Revisit import-linter only if a split turns `agents/_utils.py` or `callbacks/__init__.py` into a package with internal layering.
- Resolve the one existing cycle, `layouts` ↔ `layouts._chat`, in whichever sub-phase touches `layouts/`. Usually a name that `_chat` imports from the package `__init__` belongs in a sibling module instead.

**Model/effort:** Opus 5, plan mode, high. Not ultrathink — the safety net makes this mechanical if the rules are followed.

### Phase 5 — Local smells and duplication

**Purpose:** Now that files are small and state is explicit, fix the code inside them.

- **Duplication across agents:** the seven agents share reask/replay/resume/stream-suppression patterns. Where two agents have the same 10+ lines with different constants, lift to `_utils` with the constants as parameters. Prompt text is never lifted — it stays in each agent.
- **Long functions:** work from the Phase 0 complexity list (151 findings: C901 61, PLR0912 40, PLR0915 25, PLR0913 12). Start with the `_format_*_as_text` renderers, which are now golden-tested from Phase 1; each renderer becomes one sub-phase. Anything ruff flags under `C901` (default threshold 10), `PLR0912`, or `PLR0915` gets split into named steps. Extract, don't rewrite. When a function is legitimately complex (a dispatch table, a schema validator), add a targeted `# noqa` with a reason rather than fragmenting it.
- **`ARG` in tests:** 162 of the 171 findings are fixture and stub parameters. Add a per-file ignore for `ARG` under `tests/` rather than renaming every parameter; fix the 9 under `src/`.
- **Promote the rule sets:** at the end of the phase, add `C90`, `PLR`, `SIM`, `B`, `ARG` to the permanent ruff config with whatever per-rule ignores were justified above. From here on they are part of the gate.
- **Magic strings:** artifact file names, session keys, state constants, component ids that appear as literals in more than one place become constants in `app_constants.py` (or a sibling). String values stay identical.
- **Error handling:** bare `except:` and `except Exception: pass` get a specific exception and a log line, or a comment stating why swallowing is correct.
- **Type hygiene:** replace `Any` where the actual type is known from usage; do not introduce `TypedDict`s for the session dict in this phase (that is a design change, not cleanup).

**Model/effort:** Opus 5, auto mode, high. Sub-phase per source directory (`agents/`, `layouts/`, root modules) with a commit between.

### Phase 6 — Test suite rationalization

**Purpose:** The suite should be fast, non-redundant, and test current behavior. This is the other risky phase: deleting the wrong test removes the safety net.

- **Stale tests:** any test whose assertions describe pre-rework behavior (landing page, footer, nav drawer, old `layouts.py` module, FeatureSpeccer as an agent) is deleted, not updated — if the behavior is gone, so is the test.
- **Duplicate coverage:** tests asserting the same code path through different entry points collapse to one. Use `--cov` per test file to find pairs whose coverage sets are subsets of each other.
- **Over-granular tests:** groups like `test_excludes_git_dir` / `test_excludes_node_modules` / `test_excludes_venv_and_pycache` collapse into one `@pytest.mark.parametrize` over the skip-dir set. Same assertion, one test function.
- **Slow tests:** run `uv run pytest --durations=20`; anything that spins up a subprocess or takes >1s gets `@pytest.mark.slow`; register the marker in `pyproject.toml`; default `pytest` still runs them, but `pytest -m "not slow"` is documented for the inner loop.
- **Tests added in Phase 1 are not candidates for removal** in this phase. They are the regression net for this cleanup and can be revisited in a later round.
- Coverage on every non-UI module must stay at or above the Phase 0 baseline; on UI modules at or above the Phase 1 baseline. If a deletion drops it, the test was not redundant — restore it.

**Model/effort:** Opus 5, plan mode, ultrathink.

### Phase 7 — Final audit and documentation

**Purpose:** Prove the cleanup did what it claimed and leave the repo self-describing.

- Re-run Phase 0's measurements, including `uvx vulture`, `uv run --with deptry deptry .`, the ruff rule-set statistics, and the layering contract. Produce `CLEANUP_REPORT.md` with before/after: file-size table, test count and runtime, coverage per module, ruff/mypy findings, dead-code candidates remaining (should be zero or justified).
- Walk the seven original symptom categories as a checklist; for each, state what was found and what was done.
- Update `tests/README.md` (coverage table with current module names and no line numbers — they go stale), `README.md`'s project-structure tree, and `CLAUDE.md` for any moved modules or new markers.
- Delete `CLEANUP_INVENTORY.md` or fold its *Bugs found (not fixed)* section into a `BACKLOG.md` alongside the two existing horizon items (CodeScanner incremental scan, Designer mock capture).

**Model/effort:** Sonnet 5, auto mode.

## Suggested per-phase prompt shape for Claude Code

```
You are executing Phase N of SPEC4_CLEANUP_PLAN.md. Read the plan's
"Rules that apply to every phase" and the Phase N section, then
CLEANUP_INVENTORY.md.

Do not run git commit, git add, or git stash. Do not write under .spec4/,
.venv/, or .git/. Do not change observable behavior. Do not do work that
belongs to another phase — note it in CLEANUP_INVENTORY.md instead.

When finished, run the four gate commands and append a Phase N report
to CLEANUP_INVENTORY.md: files touched, what was removed/moved and why,
anything deferred, and the gate results. Stop and wait for review.
```

## Phase summary

| Phase | Scope | Risk | Model / mode |
|---|---|---|---|
| 0 | Baseline + inventory, no changes | none | Sonnet 5, auto |
| 0.5 | Format, mypy, failing test (three commits) | low | Sonnet 5, auto |
| 1 | Contract tests: id snapshot, goldens, state containers | low–med | Opus 5, plan, high |
| 2 | Dead code + orphan files | low | Sonnet 5, auto |
| 3 | Module state → explicit (8 items, single phase) | **high** | Opus 5, plan, ultrathink |
| 4 | Large-file splits (one per sub-phase) | med | Opus 5, plan, high |
| 5 | Local smells + duplication | med | Opus 5, auto, high |
| 6 | Test rationalization | **high** | Opus 5, plan, ultrathink |
| 7 | Audit + docs | none | Sonnet 5, auto |