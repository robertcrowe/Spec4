# Phase 1 notes — Baseline Validation of the Existing Spec4 App

Recorded 2026-09-05 on branch `look-rework`, from commit `00c1377` (Cost cards).
This is the known-green baseline every later phase of the shell rework must meet
or exceed. Nothing here is a target to change; it is the state to preserve.

---

## 1. Quality gate — the baseline numbers

| Gate | Command | Baseline result |
| --- | --- | --- |
| Build | `uv build` | **Passes.** `dist/spec4-1.1.0.tar.gz` + `dist/spec4-1.1.0-py3-none-any.whl` via the `uv_build` backend. `pyproject.toml` untouched. |
| Tests | `uv run pytest` | **3027 passed, 0 failed**, ~65 s. No pre-existing failures, no skips, no xfails. |
| Lint | `uv run ruff check src/ tests/` | **Clean** ("All checks passed!") under `select = ["E", "F"]`. |
| Types | `uv run mypy src/` | **38 errors in 15 files** (55 source files checked) under `strict = true`. |

**After this phase's two edits: 3028 passed** — the baseline plus exactly one new
test (`test_agent_keys_is_single_pipeline_order`). Ruff still clean, mypy still
38, build still succeeds.

> **Every later phase must show ≥ 3028 passing, ruff clean, and mypy at 38 or
> fewer.** A rise in the mypy count is this round's regression, not baseline.

### mypy baseline detail — all pre-existing, all out of scope

Full output saved during the run; the distribution is:

| File | Errors |
| --- | --- |
| `src/spec4/project_manager.py` | 8 |
| `src/spec4/agentifier/agentifier.py` | 8 |
| `src/spec4/session.py` | 6 |
| `src/spec4/agents/deployer.py` | 3 |
| `src/spec4/layouts/_chat.py` | 2 |
| `src/spec4/callbacks/designer.py` | 2 |
| `src/spec4/agents/brainstormer.py` | 2 |
| `src/spec4/agentifier/cross_cutting_analyst.py` | 2 |
| `src/spec4/version_check.py` | 1 |
| `src/spec4/layouts/designer.py` | 1 |
| `src/spec4/agents/stack_advisor.py` | 1 |
| `src/spec4/agents/phaser.py` | 1 |
| `src/spec4/agents/_utils.py` | 1 |
| `src/spec4/agents/_manifest.py` | 1 |
| `src/spec4/agentifier/reference_verifier.py` | 1 |

Almost all are the same two shapes: `Any | None` flowing into a parameter typed
`str`/`Path`/`dict`, and `Returning Any from function declared to return …`.
They are the untyped edges of the session dict and the JSON artifacts. **Fixed
nothing, added no `# type: ignore`.** The dead `[[tool.mypy.overrides]]` entry
for `a2a_sdk` was left in place.

Two files the shell rework *will* touch already carry baseline errors — note
them so a later phase does not mistake them for its own:

- `src/spec4/layouts/_chat.py:161` — 2 errors, both on the
  `cost_summary_card(…, agent, label)` call where the agent key is `Any | None`.
- `src/spec4/layouts/designer.py:607` — `active_version` given `str | None`.

---

## 2. Both serving paths verified

Verified with headless Chromium (Playwright, already a dev dependency) rather
than assumed, since the phase calls out asset-loading parity as a risk.

| Path | Command | Result |
| --- | --- | --- |
| Dev server | `uv run python src/spec4/app.py` | HTTP 200, title `Spec4 AI`, `#page-content` mounted, `#btn-landing-start` present, body text 2277 chars. **No console errors, no uncaught page errors, no failed requests.** |
| Production-style | `uv run gunicorn 'spec4.app:server' --bind 0.0.0.0:8050 --workers 1 --threads 4` | Identical on every measure — same status, same title, same 2277-char body, clean console. |

Asset parity under gunicorn checked explicitly: `/assets/favicon.svg` → 200 and
the Dash renderer bundle under `/_dash-component-suites/` → 200. **The two paths
are at parity today**; a later phase that changes the layout should re-run both,
not just the dev server.

---

## 3. The litellm import ordering (D-LR1)

Confirmed intact in `src/spec4/app.py`, in this order:

1. `os.environ.setdefault("LITELLM_LOG", "ERROR")` — line 14
2. `import litellm as _litellm` / `_litellm.suppress_debug_info = True` — 16–17
3. everything that imports litellm downstream (`spec4.session`, `spec4.layouts`, …)
4. `import spec4.callbacks` / `import spec4.callbacks.designer` **after** `app`
   exists, each carrying the deliberate `# noqa: E402, F401`

A one-line **D-LR1** comment now sits above the block recording that this round
must not reorder it. `D-LR` is the new decision prefix for the look rework,
following the project's existing `D-XX` convention (`D-PH`, `D-SC`, `D-PM`,
`D-ER`, `D-AF`); phase 2's theme decision should continue at `D-LR2`.

> Gotcha found while writing it: a comment containing a literal `` `# noqa: …` ``
> is parsed by ruff as a real directive and emits
> `warning: Invalid # noqa directive`. The comment refers to "the E402
> suppressions below" instead. Do not reintroduce the literal.

---

## 4. The component-id contract — `tests/test_callback_co_presence.py`

**This file is the existing id contract. It was read, not modified**, apart from
the additive test in §6. No parallel inventory, no id-manifest file, no
duplicate test module was created, and the id enumerations are byte-for-byte
unchanged.

### How it works — important before extending it

It does **not** hand-list ids. `_shell_ids()` derives them from
`app_module.app.layout`, and each screen's ids come from actually rendering that
screen and subtracting the shell. So **a new component id enters the contract by
being rendered, not by being added to a list.** The lists below are what the
current code derives; they are a record of today's state, not a source the
tests read.

It also collects **string ids only** (`_ids` filters on `isinstance(node_id,
str)`). Pattern-matching dict ids are excluded by design — `_plain_ids` skips
them because they match zero or more components and cannot be half-present.

**Consequence for the agent rows:** the seven agent action buttons use
`id={"type": "agent-pill", "agent": agent_key}` (`layouts/__init__.py:432`), so
they are invisible to this guard. The `agent_select` screen contributes exactly
one page id. A phase that rebuilds the agent rows keeps that co-presence
exemption only while the buttons stay pattern-matched; switching them to string
ids would newly subject them to this guard.

### Shell ids — 24, derived from `app.layout`

```
_designer-fs-dummy      breadth-intent-store    session
_last_render            image-support-store     stream-poll-interval
_progress-dummy         nav-burger              stream-start-ts
_progress-probe-dummy   nav-close-btn           tool-support-store
_progress-show-dummy    nav-drawer              url
_scroll-dummy           nav-overlay             version-check-interval
blueprint-grid          notifications-container version-check-modal
                        page-content            version-notice-shown
                        prefs
```

`TestShellIds` pins `{"session", "prefs", "url", "page-content"}` as a minimum.
`blueprint-grid` and the `nav-*` set are the current shell chrome — the surfaces
the status bar replaces in phase 2.

### Landing layout — 1 page id

```
btn-landing-start
```

### Project view — does not exist yet

There is no `project-view` screen in the app today; it is what phases 2–7 build.
The nearest existing screen is **`agent_select`**, which contributes **1 page
id**:

```
btn-agent-change-provider
```

(plus the seven pattern-matched `agent-pill` buttons, invisible here as above,
and `project_mode` — the question that precedes it — contributing 2.)

### Full screen coverage — 54 screens

`landing` (1) · `working_dir` (5) · `setup: provider` (7) · `setup: model` (4) ·
`setup: web search` (6) · `agent_select` (1) · `project_mode` (2) · six chat
agents × 4 states each (14–21 ids) · 5 model-gate states (16–18) · `chat: retry
panel` (18) · `chat: breadth panel` (18) · `designer: gate` (2) · `designer:
wizard` (7) · 14 designer step screens (8–13).

Three guards keep it honest, and any later phase adding a screen must satisfy
all three:

- `test_the_screen_list_actually_renders_things` — **≥ 30 screens**, none empty.
- `test_every_page_level_callback_is_reached` — a new callback with page-level
  Inputs **fails** until its screen is added to `_phase_screens`.
- `test_it_catches_a_split_callback` — the guard's own regression test, pinned
  on the `btn-agent-llm-pick` / `btn-agent-llm-chip` pair.

---

## 5. Orderings and single sources that must survive every later phase

### Relative ordering — `tests/test_cost_summary.py`

`TestChatPlacement::test_sits_between_the_transcript_and_the_action_row`:

```
index("chat-scroll-area") < index("cost-summary-card") < index("chat-token-count")
```

The card is the single `cost-summary-card` id and there must be **exactly one**
(`test_exactly_one_card`). `TestDesignerPlacement::test_preview_step_shows_the_card`
adds `index("mock-iframe") < index("cost-summary-card")` on Designer step 6.

### Relative ordering — `tests/test_agent_llm_selection.py`

`TestModelChipPlacement::test_it_shares_a_row_with_the_status_line_and_comes_first`
is an **exact** equality, not a subset:

```python
_child_ids(footer) == ["btn-agent-llm-chip", "chat-status-line"]
```

Adding anything to that footer row breaks it. Also pinned there:

- the chip is **not** in the action row (`test_it_left_the_action_row`);
- the footer sits **below** `chat-input` (`test_the_footer_sits_below_the_input`);
- `chat-status-line` keeps `minHeight: "1.4em"`, `textOverflow: "ellipsis"`,
  `minWidth: "0"` — the reserved line that stops the input shifting;
- with the gate open the chip is absent and the row is `["chat-status-line"]`
  alone (`test_the_gate_still_suppresses_it`).

### `AGENT_KEYS` — the one pipeline order

`src/spec4/app_constants.py:88`, seven entries:

```
code_scanner · brainstormer · agentifier · designer · stack_advisor · phaser · deployer
```

`src/spec4/layouts/__init__.py:391` holds `_AGENT_ROWS`, a
`list[tuple[key, step, emoji, name, desc]]` in the same order, consumed by the
render loop at line 613. It was **already** asserted against `AGENT_KEYS` by
`tests/test_agent_llm_selection.py:83` (`TestAgentKeys`). The new test in §6 is
a second, deliberate pin at the id-contract altitude; the original is untouched.

Note `AGENT_KEYS` order and `project_manager._PIPELINE_ARTIFACT_ORDER`
(line 1555) are *parallel but distinct* — the latter is the artifact freshness
chain (`code_review.json`, `vision.json`, `ai_features.json`,
`design/mock.html`, `stack.json`, `phases`, `deployment-plan.md`). Later phases
should read each from its own module rather than deriving one from the other.

---

## 6. The one change in `tests/`

Added `test_agent_keys_is_single_pipeline_order` to
`tests/test_callback_co_presence.py` (module level, after
`test_every_phase_renders`), plus the two imports it needs. It asserts
`len(AGENT_KEYS) == 7` and `tuple(key for key, *_ in _AGENT_ROWS) == AGENT_KEYS`.
No existing test was renamed, deleted, or reordered.

---

## 7. Functions later phases consume unchanged (do not re-derive status)

### `project_manager.detect_stale_inputs(working_dir, agent) -> dict[str, float]`

`src/spec4/project_manager.py:1523`. Returns `{input_name: input_mtime}` for
upstream inputs newer than the agent's output. Returns `{}` when the agent has
no recorded dependencies, has produced no output, or nothing is newer. Mtimes
ride along so a caller can spot a *further* upstream update — the same input
name reappearing with a different mtime than the one last acknowledged. Drives
the round-tree's "needs update" state.

### `project_manager.agent_button_state(working_dir, agent, session=None) -> str`

`src/spec4/project_manager.py:1638`. Returns **one string** from the five
constants at lines 1578–1582:

| Constant | Value | Mock's action label |
| --- | --- | --- |
| `AGENT_BTN_START` | `"start"` | Start (filled green) |
| `AGENT_BTN_MODIFY` | `"modify"` | Modify (neutral outline, green text) |
| `AGENT_BTN_NEEDS_UPDATE` | `"needs_update"` | Needs Update (warn outline) |
| `AGENT_BTN_NOT_READY` | `"not_ready"` | Not Ready (disabled outline) |
| `AGENT_BTN_REQUIRED` | `"required"` | Required (filled green, as Start) |

The state machine, in order: a pending brownfield round → `required` for
`code_scanner` and `not_ready` for everything else; a missing required input →
`not_ready`; an input chain out of pipeline order → `not_ready`; then no output
→ `start`, output at least as new as its nearest input → `modify`, output older
→ `needs_update`. CodeScanner has no inputs: `start` without
`code_review.json`, `modify` with one. No working directory reads as an empty
project.

`layouts/__init__.py` already maps these to labels (`_AGENT_BTN_LABELS`, 408)
and colours (`_AGENT_BTN_COLORS`, 418). **The colour map is what phase 2's
"no local accent colour" instruction collides with** — it currently hard-codes
`blue`/`green`/`red`/`gray` per state.

---

## 8. State plumbing — the two browser stores

All state lives in two `dcc.Store`s mounted in the app shell
(`src/spec4/app.py:94–95`) and **must be threaded into server-side callbacks as
`State`** — never read from a module global:

- `dcc.Store(id="session", storage_type="session", data=_default_session())` —
  sessionStorage. Shape from `session._default_session()` (line 26).
- `dcc.Store(id="prefs", storage_type="local", data={})` — localStorage.

### Working directory

`session["working_dir"]`, set by `session._load_working_dir(path, session)`
(line 193). Selecting a directory clears every project-specific field; only
`_PRESERVED_SETUP_KEYS` (provider / model / api_key / available_models /
llm_config plus the web-search pair) survive, so a configured developer picking
a new directory is not sent back through `/setup`.

### Current round

`project_manager.active_version(working_dir, session=None) -> int` (line 328).
Prefers the session's pinned `phase_version`; falls back to
`latest_phase_version(working_dir)`, then `0`. **Read helper only** — it never
resolves a *new* round; that is the persist funnel's job. The status bar and
round-tree should call this, not recompute from the directory listing.

### Default provider / model

Session defaults are `session["provider"]`, `session["model"]`, and the built
`session["llm_config"]`. The resolution path is
`llm_selection.resolve(session, agent) -> dict | None` (line 117): the agent's
override entry if it has one with a `model`, else the session default,
**returned unchanged including `None`** before setup has run. Configs are
assembled in exactly one place, `llm_selection.build_llm_config(provider_key,
model, api_key)` (line 46).

> Phase 2's status bar must resolve the default through `llm_selection` and add
> **no parallel model-resolution path**. `llm_selection.key_for_provider(session,
> prefs, provider_key)` (line 160) is the one function that reads both stores,
> and it deliberately never mutates either.

---

## 9. Target visual register — `.spec4/v0/design/mock.html`

Rendered and read. The reference every later phase matches against.

### Tokens

| Token | Value | Role |
| --- | --- | --- |
| `--bg` | `#0a0a0f` | page ground |
| `--panel` | `#12121c` | status bar, cost box, table header, tree zebra |
| `--panel-2` | `#1a1a24` | raised |
| `--border` | `#2a2a3a` | every 1px rule |
| `--text` | `#f5f5f7` | primary |
| `--dim` | `#a0a0b0` | secondary / labels |
| `--faint` | `#5a5a6a` | separators, disabled |
| `--accent` | `#39FF14` | the one accent (`--accent-hover` `#31e510`) |
| `--wordmark-blue` | `#1E88E5` | **wordmark only** |
| `--lane-prompt` | `#e8925a` | prompts-for-the-agent lane |
| `--lane-record` | `#b39ddb` | a-record-for-you lane |
| `--warn` | `#d8b84a` | Needs Update |

Type: Inter for UI at **13px / 20px**, JetBrains Mono at **12.5px** with
ligatures off for every path, model, token count and cost figure. Focus is
`1px solid var(--accent)`, offset 1. The register is **dense, flat and
rule-separated** — no shadows, no rounded cards, 3px radius on buttons only.

### The four surfaces of `project-view`

1. **status-bar** — 40px tall, `--panel`, 1px bottom border, 16px side padding,
   flex space-between. Left: wordmark (`Spec` in blue, `4` in accent, 14px/600)
   then mono context `dir · round vN · provider · model` with `·` separators in
   `--faint`, ellipsised. Right: nav `Project / Settings / Docs` — active item in
   accent with a 1px accent underline, others `--dim` → `--text` on hover — then
   the version in mono `--dim`, separated by a 16px left border.
2. **round-tree** — mono `.spec4/v{N}/` heading (13px/500, 24px line, 4px
   below), then one full-width `<li>` per artifact **in pipeline order**: 24px
   tall, 8px padding, 1px bottom rule, **even rows tinted `--panel`**. Name
   coloured by lane (reference lane uncoloured `--text`); status at the right in
   `--dim` and **only** when `needs update` or `missing`; missing rows drop the
   name to 0.55 opacity. Below it a three-item legend, 8px swatches, 24px gaps.
3. **agent-rows** — a real `<table>`, `border-collapse`, 1px rules, header in
   `--panel` at 12px/500 `--dim`. Rows 32px, `nowrap`. Columns:
   `Agent (140px, 500) · Produces (220px, mono) · Last model (220px, mono) ·
   Tokens this round (220px, mono) · action (120px, right-aligned)`. **A
   not-yet-run agent leaves model and tokens genuinely empty**, no placeholder.
   Disabled rows dim the agent and produces cells.
4. **round-cost** — `--panel` box, 1px border, 8px/12px padding. Two mono
   `.cost-line`s at 24px (`Estimated cost, vN:` label in `--dim`, then the
   figure; then the unpriced line) and a dimmed 12px `.cost-note` disclaimer
   4px below.

### Shell and buttons

Shell is `status-bar` + a `.view` at **max-width 1100px, 16px padding (32px
bottom), 24px between sections**, on an 8px rhythm. Buttons are 24px tall, 96px
min-width, 12px/500, 3px radius: `.btn-primary` filled accent with `--bg` text
(Start / Required), `.btn-modify` accent text on a neutral border,
`.btn-warn` in `--warn` (Needs Update), `:disabled` in `--faint` (Not Ready).

Per `manifest.json`: `Settings` opens the existing model/provider flow and setup
wizard, `Docs` is the one external link (spec4.ai), and there is **no Artifacts
link this round**. All four surfaces are `kind: non_ai`, all read-only
(`writes: []`), and the other three all `depends_on: ["status-bar"]`.

---

## 10. Out of scope, confirmed untouched

`pyproject.toml`, the `a2a_sdk` mypy override, every existing test name and id
enumeration, every layout, and all 38 baseline mypy errors.
