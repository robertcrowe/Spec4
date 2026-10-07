# Changelog

All notable changes to Spec4, newest first. This file starts at 1.0.0; see
[Pre-1.0](#pre-10) for what came before.

Entries are keyed to release tags, since a tag is what a user could install.
Two places where the repo's own record is uneven, stated rather than smoothed
over: the `v1.5.0` tag sits on the last commit of its series, not on the
version bump eight days earlier, so 1.5.0 covers everything in between; and
1.1.0 was bumped in `pyproject.toml` but never tagged, so its changes reached
users as part of 1.5.0.

## [2.1.0] — unreleased

The first of the `scan` collectors. A `code_review.json` written by 2.0.0
still reads — its `scan` is `{}` and renders as before — but a re-scan is
what fills it.

### Added
- **`scan.inventory`** — the census of the walked tree: file and line counts
  per extension (binary and oversized files counted but not measured), the
  first 2,000 paths, and every directory the walk pruned (`unscanned_dirs`),
  so a consumer can tell "not there" from "not looked at".
- **`scan.coverage`** — what the seed actually showed the model: the README,
  manifests, CI and deployment files whose contents were pasted, the source
  files sampled, and the source total they were drawn from. The record is
  kept by the code that pastes, not re-derived afterwards.
- **`scan.git`** — present when the project root is itself a repository
  (a `.git` entry at the root; a subdirectory of a larger repository gets no
  block): head, branch, dirty flag, untracked count; the commits since the
  last Spec4 round — after the latest `IMPLEMENTED` marker, else after the
  prior `code_review.json`, else absent on a first scan — with their date
  range, author names (never emails), per-top-directory touch counts and
  whether any carries a coding-agent trailer (evidence only); and the last
  commit per top-level directory. Dormancy is not classified here. Logs are
  capped at 500 commits and say so. `git` is Spec4's first subprocess call;
  any failure — no binary, a timeout, an empty repository — stores
  `{"available": false}` and never fails the scan.
- **Scan Summary** leads the rendered review: files and lines, skipped
  directories, what the model was shown, and the git line. Absent for a
  review whose `scan` is empty, so 2.0.0 artifacts render unchanged.
- `scan` is typed in the artifact schema: each block optional, each closed.
  A collector emitting a key the schema does not name fails at commit, as a
  bad envelope does.

### Changed
- The measured layer is taken from the same walk the model is shown and held
  in the session (`code_scanner_scan`) until the model's `review` block is
  committed — the commit may be turns later. It is cleared on commit; a
  commit with no walk behind it is refused rather than stored with an empty
  `scan`.

## [2.0.0] — unreleased

**Breaking.** The code review artifact changes shape. A `code_review.json`
written by any earlier version is no longer read: the 1.6.0 gate fires on it,
CodeScanner shows as *Required*, and one re-scan brings the round back. No
other artifact in the round is affected.

### Changed
- **`code_review.json` is a two-layer envelope.** `code_review` now holds
  `schema_version: 2`, a `scan` object and a `review` object. `review` is the
  model's judgment — the schema-1 field set, unchanged — and `scan` is the
  layer Spec4 computes from the tree itself. It is empty in this release; the
  collectors that fill it (inventory and coverage, git history, the module
  graph, the prior round) land in the 2.x series. The model never sees or
  emits `scan` or the version: CodeScanner's model emits a bare `review`
  block, validated on its own, and the envelope is assembled and validated
  again at commit — a wrapping fault fails before it reaches disk.
- **Consumers read the envelope by path only.** Brainstormer, StackAdvisor,
  Phaser, Deployer, Designer's no-UI detection and the Agentifier's
  TierAnalyst all resolve `code_review.review` through one helper. The
  readers that used to fall back to the outer dict when the inner one was
  missing are gone; under the new shape that fallback would have found the
  envelope and read every field as absent, silently.
- **No raw review JSON reaches a downstream model.** The Agentifier's Scout
  now reads the review through its own field view (self-description, type,
  architecture, AI in place, frameworks and dependencies, routes, standards,
  half-built areas), the same treatment the other agents received in 1.5.3.
  Phaser's raw block — kept alongside its view since 1.5.3 as the verbatim
  carrier for `directory_map` and `commands` — is retired; the view renders
  those values verbatim already. On the revision path ("your code review
  input has been updated"), an agent that reads the review through a view
  receives the update through the same view, so the two are directly
  comparable in its history; Deployer and the Agentifier receive the `review`
  block alone, never `scan`.
- The CodeScanner seeds paste only the `review` layer of a prior review. The
  stale-review fresh seed still reads a schema-1 file for that one purpose —
  the older review as context — and nowhere else.
- The review-reach probe (`evals/code_scanner/review_reach.py`) reads both
  shapes, so the v1–v8 baseline still runs.

## [1.6.0] — unreleased

Groundwork for the CodeScanner v2 review format: a round whose code review was
written under an older schema is gated explicitly rather than read as empty.

### Added
- **Stale-review gate on /agents.** The review schema now carries a declared
  version (`CODE_REVIEW_SCHEMA_VERSION`), and `code_review_needs_rescan`
  compares the active round's `code_review.json` against it. When the file
  was written under an older version the page behaves exactly as it does for
  a pending brownfield round — CodeScanner is *Required*, every other agent is
  *Not Ready* — and a notice names the round's `.spec4/v{N}/` folder, says the
  review predates this Spec4 version, that nothing else in the round is lost,
  and that a re-scan unlocks the rest. Without this, the next schema change
  would have loaded an older review as a set of empty views in every
  downstream agent, with no signal anywhere. Only a review that parses and
  names a different `schema_version` is stale; a missing, corrupt or shapeless
  file behaves as before.
- **Re-scan of a stale review starts fresh.** Opening CodeScanner on a stale
  review no longer displays it; it scans, and the seed is the fresh-scan seed
  with the old review appended as context only — never the update seed, which
  asks for a merge into a shape the current schema does not read.

### Changed
- The seeds name the schema version from the constant rather than a literal.
- Nothing is visible yet at the current version (1): every review on disk
  already carries `schema_version: 1`. The gate first fires when the version
  moves.

## [1.5.3] — 2026-10-05

Brownfield fidelity: what CodeScanner found reaches the planning agents in a
shape they read, a revision round cannot silently lose an entry from the
established stack, and the optional agents' artifacts carry forward across a
round that skipped them.

### Added
- **StackAdvisor's revision diff.** In a revision round StackAdvisor re-emits
  the whole prior `stack.json` with the changes folded in, and re-emitting a
  large JSON artifact is where a model drops a line nobody asked it to drop —
  a live round lost an established `SendGrid` entry with no signal anywhere.
  Every established entry absent from the new spec is now found
  deterministically and classified: requested by the Brainstormer's delta,
  requested by you in this round's conversation, or unrequested. Unrequested
  entries are restored at their prior position, and the commit display carries
  a receipt — "Restored to the established stack" / "Removed from the
  established stack" — so the restoration is visible rather than silent. The
  keys and dispositions are recorded on every revision commit, empty list
  included, so a probe can measure how often it fires.
- **Code-review views per consumer.** Brainstormer, StackAdvisor and Phaser
  used to receive `code_review.json` as a raw JSON paste followed by a
  field-instruction paragraph that differed per seed. A probe
  (`evals/code_scanner/review_reach.py`) showed what that cost: fields a seed
  named reached the plan, fields it did not name mostly did not, and
  StackAdvisor's stack recorded the prompt exemplar's `ESLint`/`Prettier` in
  eight rounds out of eight for a codebase whose review said `oxlint`. Each
  consumer now gets a rendered view of exactly the blocks it reads, each
  under one line of guidance, values verbatim with their `source` /
  `inferred_from` provenance in brackets. The renderer is total: a schema
  field it has no special knowledge of still reaches the seed.
- `evals/stack_advisor/grounding.py`: a read-only probe over recorded draws
  listing the integrations, auth mechanisms, stores and collections that cite
  no feature, capability, NFR or infra id — the measurement a grounding check
  would be judged against, before any such check exists.

### Fixed
- **Optional-agent carry-forward walks back past rounds without the
  artifact.** The prior AI catalog, mock, manifest and deployment plan were
  read from the latest implemented round only, so a round that was implemented
  without running the Agentifier, Designer or Deployer (a hosting migration,
  say) emptied the carry-forward for the round after it. Each loader now reads
  the newest *implemented* round that holds the artifact; unimplemented rounds
  in between are skipped, not read. The required artifacts (vision, stack)
  still read the latest implemented round, since a round cannot be implemented
  without them.
- **Designer finalize leaves the round with a manifest.** Only the generating
  path wrote `manifest.json`, so a revision that carried the prior approved
  mock forward and approved it unchanged ended with `mock.html` and no
  manifest, and StackAdvisor's design input was silently absent. Approve now
  copies the latest implemented round's manifest in when the round has none.
  A manifest already present is left as it is, mtime included.
- **The mock preview stands in for what the sandbox withholds.** The preview
  iframe's opaque origin has no storage, so `localStorage`, `sessionStorage`,
  `document.cookie`, `indexedDB.open` and `history.pushState` all throw
  `SecurityError` there — and a drawn gallery keeps its state in exactly
  these, so a mock that works in a tab reported errors in the preview. The
  error shim now installs in-memory storage, a cookie that reads empty, no
  `indexedDB` so feature detection fails cleanly, and no-op history writes
  before the mock's first script, and drops the sandbox-only `SecurityError`
  messages it cannot shim. Nothing of the mock's own is hidden: no page
  outside a sandbox raises those messages.

## [1.5.2] — 2026-09-21

Designer reliability: the finished mock reaches the screen, the screen says
what the model is doing while it draws, and a drawn mock is checked before
you approve it. Also carries the prompt-caching work below, which the 1.5.1
tag missed.

### Added
- **The drawn mock is checked, and its errors go back to the model.** Two
  deterministic layers. On the server, the extracted document is checked for
  truncation at the 512 kB cap, a document that does not close, unbalanced
  `<script>` or `<style>` tags, and an unterminated template literal. In the
  browser, the preview iframe runs the mock with a one-line error reporter
  injected after `<head>` (line numbers unchanged, the saved `mock.html`
  untouched) that captures thrown errors, unhandled promise rejections and
  failed resource loads. A status line above the preview reads "Checking the
  preview…", then "Rendered cleanly" in the accent or "N errors in the mock —
  the model can fix them" in red, with a **Fix errors** button that starts a
  refine draw quoting the errors back to the model under a
  `--- Fix render errors ---` separator. Nothing runs without the click. No
  new runtime dependency: the checking browser is your own.
- **Thinking is visible.** Reasoning text is counted as it streams: the chat
  counter reads "Thinking — N chars" until the first reply character, and
  Designer's shows it while waiting for the first output. On a model that
  accepts `reasoning_effort`, "default" now sends `medium` rather than
  nothing, which bounds the silent adaptive thinking and makes the summaries
  stream (`llm.DEFAULT_THINKING_EFFORT`).
- **A mid-stream pause is legible.** After 15 seconds without a chunk the
  Designer counter says so — "Chars received: 12345 — thinking, 8901 chars
  (no output for 2 min 10 s)" — instead of sitting still, which read exactly
  like the delivery bug below.
- **A draw outlives the page it started from.** A watchdog interval re-arms
  the Designer poll after a page rebuild (a reload, a model change, a tab the
  browser discarded during a long wait), so the mock the thread went on to
  save is delivered rather than lost.
- Explicit stall bounds per call kind: 600 s between chunks for a chat turn,
  1800 s for a mock draw, whose time-to-first-token on a reasoning model had
  been observed past LiteLLM's 600 s fallback.

### Fixed
- **The finished mock was never displayed** on a long draw: the counter froze
  mid-stream, the server printed `mock delivered` over and over, and the page
  stayed on the progress bar. Cause, verified in dash-renderer 4.1.0: it keeps
  the newer of two in-flight requests of the same callback and discards the
  older one's response, so a poll response slower than the 250 ms interval
  never landed, and neither did anything after it. The delivery response
  carried the mock twice, up to a megabyte, and could not fit. The poll now
  runs at 500 ms, slows itself to 2 s with a small response before sending
  the mock, re-delivers at that cadence until the browser acknowledges, and
  the step renderer no longer makes a server round trip on every buffer
  tick. The duplicate payload and its clientside copy are gone.
- Start Over now deletes the round's `design/` files as well as the store;
  `designer_layout` rebuilds the store from `session.json` on every render and
  was putting the old mock straight back on screen.

### Changed
- The API-key notice in the setup wizard reads "Stored in this browser only."

### Notes
- The `v1.5.1` tag sits on the commit *before* the 1.5.1 version bump, so
  none of the prompt-caching work listed under 1.5.1 reached users at that
  tag. It ships here. Stated rather than smoothed over, like the two
  irregularities in the preamble.
- One pydantic warning from litellm's `ChatCompletionReasoningItem` (a
  `ReadOnly` TypedDict item it cannot enforce) is filtered in the test
  configuration, so a warning in the suite's summary is one of ours.

## [1.5.1] — 2026-09-17

Prompt caching, and the reporting to tell whether it is working. The tag
predates the bump commit (see the 1.5.2 notes): these changes reached users
in 1.5.2.

### Added
- Prompt caching for Anthropic and Bedrock, behind the `SPEC4_PROMPT_CACHING`
  environment variable: a system-message breakpoint on every call, and a moving
  last-message breakpoint in `stream_turn`.
- `cache_creation_input_tokens` in the per-agent and round rollups, with the
  same null-until-reported semantics `cached_input_tokens` has — a field no
  call reported stays null rather than reading as a confident zero, which is
  how a round recorded before caching existed must read.
- `cache_write` and `hit%` columns in `spec4-usage`. `hit%` is cache reads over
  input tokens, and is blank rather than `-` when either figure is missing.
- `evals/caching/`: a read-only probe over recorded `usage.json` files, with a
  "Reading a draw" guide covering the healthy read/write shape, the 4,096-token
  minimum cacheable prefix on Haiku 4.5 and Opus 4.5/4.6, and how a 5-minute
  cache expiry looks in a draw.

### Changed
- The probe's `overlaps` column is now `clock_skew`. It compares a wall-clock
  `timestamp` against a monotonic duration, so it never could detect
  concurrency; the pipeline is sequential and a non-zero count is a timing
  artifact.

### Notes
- Cache reads and cache writes are both already inside `prompt_tokens` for
  every provider Spec4 talks to, so they are a breakdown of the input count,
  not an addition to it. Costs were already priced correctly.

## [1.5.0] — 2026-09-16

147 commits. Designer and Deployer work, in-app cost reporting, and a
nine-phase cleanup that changed no observable behaviour.

### Added
- **Designer manifest and StackAdvisor.** Refine draws update the existing
  manifest instead of replacing it, and freshness keys on real change.
- **Designer UI**: an intro screen, agent pills, and a fix for the
  `_designer_failed_draw` gap.
- **Cost cards** in the app: per-agent and per-round token and cost figures,
  read from `usage.json` at display time and never accumulated.
- A finished **Deployer now displays its plan**.
- `pre-commit` and `pre-push` hooks under `scripts/hooks/`.
- `scripts/cleanup/`: the checks the cleanup ran on, kept as tools — the floor
  check (456 node ids), substitution and token checks, patch-string
  resolution, the trace harness, and the move petition.

### Changed
- The setup wizard returns to the agent you clicked once it connects.
- Agentifier refinement across the scout, tier analyst and try-again paths.
- README reworked; the old landing screen removed.
- `project_manager` became a package, with its concern modules inside it.
- `tests/test_agents.py` split by source module, into five files and a shared
  helper module.

### The cleanup (Phases 0–8)

Behaviour-frozen throughout: component ids, `PATH_TO_PHASE` keys, `.spec4/`
artifact shapes, every session key, every LLM prompt string, and `app.py`'s
load-bearing import order. Measured between Phase 5p and Phase 7's close, both
runs in one session on the same machine:

| | before | after |
|---|---:|---:|
| Suite runtime (median of two) | 155.88 s | **95.24 s** |
| Coverage misses (same scope) | 909 | **876** |
| Tests collected (same scope) | 4,175 | **4,211** |
| `: Any` annotations | 290 | **232** |
| `C901` complexity waivers in `src/` | 11 | **9** |

Nearly all of the −60 s came from one change, Phase 6g's chunk factory
(−51.46 s on its own). No test was deleted or pruned for speed in either phase.
`PLR2004` was promoted into the gate for `src/`; mypy `--strict` is clean.

The cleanup also found defects in the safety net itself — invariants the design
depends on that nothing would have noticed losing. The clearest: `get_agent_gen`
handing an agent a *copy* of the session would have silently discarded every
write the turn made, and no test failed under that mutation until Phase 7n2
added the identity test.

The full records (`CLEANUP_INVENTORY.md`, `CLEANUP_REPORT.md`,
`PHASE8_RECORD.md`, `SPEC4_CLEANUP_PLAN.md`) live at the `cleanup-complete`
tag; read them with `git show cleanup-complete:<file>`. What the product still
depends on was folded into `scripts/cleanup/README.md`.

## [1.1.0] — 2026-09-04

Bumped in `pyproject.toml` but never tagged; these changes shipped to users as
part of 1.5.0.

### Added
- **Per-agent model selection**: each agent can run on its own model, with a
  gate that checks the selection before a run starts.
- **Token and cost reporting**: per-call usage capture for streamed and
  non-streamed calls, the `usage.json` writer, and the `spec4-usage` report
  CLI. Tokens are what the provider reported; cost is LiteLLM's advisory
  estimate, and calls it could not price are counted and named rather than
  silently dropped.

### Changed
- Streaming status UX improved across the agents.

### Removed
- The attribution stamp on generated artifacts.

## [1.0.0] — 2026-08-04

First stable release.

### Added
- Eval harnesses under `evals/` for the agentifier, deployer, designer and
  phaser — mechanism scoring, deployment-signal and env-var coverage, NFR
  threading, declaration alignment, dependency ordering and manifest attach.
- Public-repo scaffolding: `CONTRIBUTING.md`, project logos, and a reworked
  `README.md`.

## Pre-1.0

0.1.0 (2026-04-25) through 0.6.2 (2026-05-30): initial development, from the
first commit to the eve of 1.0.0. The commit record there is too thin to
summarise honestly — several releases are a single `cleanup` or `lock` commit,
and tags are missing for 0.1.0–0.1.3 and 0.1.5. Use `git log` for that period.

[1.5.3]: https://github.com/robertcrowe/Spec4/compare/v1.5.2...v1.5.3
[1.5.2]: https://github.com/robertcrowe/Spec4/compare/v1.5.1...v1.5.2
[1.5.1]: https://github.com/robertcrowe/Spec4/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/robertcrowe/Spec4/compare/v1.0.0...v1.5.0
[1.1.0]: https://github.com/robertcrowe/Spec4/compare/v1.0.0...cb9f9ae
[1.0.0]: https://github.com/robertcrowe/Spec4/releases/tag/v1.0.0
