# Changelog

All notable changes to Spec4, newest first. This file starts at 1.0.0; see
[Pre-1.0](#pre-10) for what came before.

Entries are keyed to release tags, since a tag is what a user could install.
Two places where the repo's own record is uneven, stated rather than smoothed
over: the `v1.5.0` tag sits on the last commit of its series, not on the
version bump eight days earlier, so 1.5.0 covers everything in between; and
1.1.0 was bumped in `pyproject.toml` but never tagged, so its changes reached
users as part of 1.5.0.

## [2.10.0] — unreleased

The changed-tree datum (D-SC5-4 firmed, D-SC5-9, D-SC5-12): on the first
update scan of BWS4 after the v9 Router round, both Sonnet and Haiku rewrote
every `review` field from the context window and dropped the ten `env_vars`
whose source file (`config.py`, unchanged) had fallen out of the evidence
sample, plus 21 of 46 `dependencies`. The update draw is now told to carry
what the delta did not touch, and the two keyed lists are merged back in
code. A minor bump: the update draw's behaviour changes.

### Changed
- The update-scan seed states the carry rule beside its labels: an entry
  whose `source` / `inferred_from` path is not in the changed-path list is
  carried verbatim from the prior review; re-derive only where the list
  names the path, add for paths it adds, drop for paths it removes; an
  untouched `implemented` entry keeps its status; "complete" means carried
  plus re-derived, never a fresh listing. The delta's path sets — files
  added / removed / modified, signatures changed, manifests changed,
  load-bearing candidates entered / left — are rendered in full under
  **Paths this scan changed** so the model reads the list rather than
  inferring it from what it was shown. Without a delta the block says the
  rule is suspended; with a partial or truncated file delta it says the
  list is incomplete and suspends it the same way.
- The seed asks the model to reuse the prior review's `implemented[].id` for
  a capability it already names and mint one only for a new capability
  (Haiku re-minted every id; the reconciliation survived only because it
  joins on `prior_feature_ids`).
- `wrap_review` takes the prior envelope and, after `consumers`, carries
  back any `env_vars` / `dependencies` entry (keyed by `name`) the prior had,
  the model dropped, and whose source path the delta does not name — in the
  prior's order, after the model's entries. The model's own entry wins by
  name; nothing is carried without a prior `review` layer, without a delta,
  or when the delta's file lists are partial or truncated. On the BWS4
  2.9.1 → 2.9.2 pair this restores `env_vars` to 22 and `dependencies` to
  46 (the regression fixture).

### Added
- `scan.delta.files.modified` — files both scans list whose content differs
  from the prior head: `git diff --name-only <prior head>` plus the working
  tree's modified files, Spec4's own output excluded, disjoint from `added`
  and `removed`, capped like them, `[]` outside a repository. The delta's
  one git-witnessed list (its module docstring said "never git" — this is
  the stated exception): without it an edit to `.env.example` or `main.py`
  was invisible to the carry rule. Optional in the schema, so every stored
  2.x review still validates. The seed's Changes block lists it beside
  added and removed.

## [2.9.2] — unreleased

Three small levers from the first measured 2.9.1 update scan on BWS4
(D-SC5-1, 2, 5). No change to what is stored in `review`.

### Changed
- The update-scan seed pastes the prior `review` minus the fields Spec4
  recomputes at commit — `load_bearing[].consumers`, every
  `prior_round_reconciliation[]` field but `gap` (with its `source` /
  `inferred_from`; an item with no gap goes, and the key with it), and
  `unplanned_changes[].classification`. They cost ~2.6 k tokens of a 78 k
  prompt on BWS4 and had the model announcing it would drop them. The
  stale-schema fresh seed is unchanged.
- The update summary gains a fourth label, **Previously omitted**, for an
  entry the evidence supports but the prior review lacked — a completeness
  fix in the review, which the first 2.9.1 scan had to label "Added" and
  disclaim in prose.

### Added
- `scan.producer` — `{spec4, schema}`, the Spec4 version and schema that
  measured the scan — on every scan as its last key, and `delta.prior.producer`
  copied from the prior scan (`null` for one from before 2.9.2). A reader of
  `delta` can now tell "measured by an older extractor" from "the tree
  changed": the 2.9.0 BWS4 scan listed 43 "added" symbols on an unchanged
  tree because its 2.2.0 prior predated `variable` extraction. Optional in
  the schema, so every stored 2.x review still validates.

## [2.9.1] — unreleased

### Added
- CodeScanner writes a review emission that fails schema validation to
  `.spec4/failures/code_scanner_review_<n>.txt` — the validator's error
  list first, then the raw reply — before re-asking, and again if the
  re-ask fails too. Every BWS4 scan since the closed shapes of 2.6.0/2.8.0
  has taken the correction pass, and the re-ask path kept the first
  emission and its errors only in the session's message list, where
  nothing could read them. Unconditional, not dev-gated (unlike the
  Agentifier's D-AF7 dumps): a failure on every scan is a defect signal.
  Instrument before any lever.

## [2.9.0] — unreleased

Step 4b of the CodeScanner v2 plan (D-SC4b-1…8, 10, 12): the consumer side
of reconciliation. Phaser, StackAdvisor and Brainstormer now read the three
step-4 arrays through their views, with the guidance line each needs; the
reconciliation renders one line per phase rather than a dump of its paths.
The in-round window (D-SC4-5) stays deferred (D-SC4b-9): the first real BWS4
scan found nothing after the round boundary to classify.

### Added
- **Consumer tuples** (D-SC4b-1…3): `PHASER_REVIEW_FIELDS` gains
  `prior_round_reconciliation` and `unplanned_changes` after `implemented`
  (a `no_evidence_found` / `evidence_partial` phase outside Scan coverage is
  unverified, not absent — Phase 1 verifies before any phase re-plans it; an
  `evidence_found` phase is not re-planned; a phase touching an unplanned
  area starts from what is there now); `STACK_REVIEW_FIELDS` gains
  `divergences` after `integrations` (record the built name — what D-CR7
  overwrites from); `BRAINSTORMER_REVIEW_FIELDS` gains `unplanned_changes`
  after `implemented` (acknowledge, don't propose fresh). Shared
  `FIELD_GUIDANCE` lines for all three; Scout's tuple is untouched.
- **Reconciliation renderer** (D-SC4b-4): a hand renderer in `_RENDERERS` —
  `- phase n — *title* [verdict]: ids`, with the unclaimed feature ids, the
  ones claimed only short of `complete`, and `gap` for a phase short of
  `evidence_found`; `(no features declared)` for `unassessed`. `paths` and
  the features' statuses are not rendered — the paths are on `implemented`,
  which Phaser already reads (on BWS4 the walker printed 27 to one line).
- **`prior_round_reconciliation[].title`** (D-SC4b-5): `wrap_review` copies
  each prior phase's title onto its item at commit (null when the round
  recorded none), so a renderer handed the item alone can name the phase;
  the schema permits it and the transcript renderer shows it.
- **Bare headings** (D-SC4b-6): the three step-4 arrays head as "Prior round
  reconciliation (feature coverage, not phase scope)", "Unplanned changes
  since the last round" and "Divergences from the planned stack" — not
  "Existing …", which misread. `_BARE_HEADINGS` names them; every other
  review field is unchanged.
- **Prompt nudges** (D-SC4b-8): `divergences` — one entry per found
  counterpart, `found` one name verbatim, never a conjunction (the first BWS4
  scan emitted "OpenRouter and Groq"); `load_bearing` — an invariant or side
  effect stated in the draft prose goes in `contract.invariants` /
  `side_effects`, not only in the prose (`run_typed_step`'s stayed in prose).
- Goldens `code_review_{phaser,stack,brainstormer}_view_step4.md` from
  `fixtures/review_with_step4.json`; `render_review_with_step4.md`
  regenerated for the title; every other golden byte-unchanged.

## [2.8.1] — unreleased

### Fixed
- `git.since_last_round` and `most_touched` passed the round boundary to
  `git log` as `--since=@<epoch>`. Git reads a short `@N` by its
  approximate-date parser rather than as a Unix timestamp, so a boundary at
  epoch 0 meant "now" and counted only the current second's commits — the
  source of the intermittent `test_throwaway_repository_end_to_end`
  failure (`assert 0 == 2`). Both call sites now pass an ISO-8601 UTC
  timestamp, which git parses as a timestamp whatever its value. Real
  boundaries are file mtimes and were never mis-read; the stored
  `boundary` string is unchanged.

## [2.8.0] — unreleased

Step 4a of the CodeScanner v2 plan (D-SC4-1…4, 6…10): the producer side of
reconciliation. The review says which of the last round's phases the code
evidences, what changed since that round outside any plan, and where the
built stack departs from the planned one; the seed gains the evidence those
are answered from. The in-round window and the consumer tuples are step 4b
(2.9.0), after one real BWS4 2.8.0 scan.

### Added
- **`review.prior_round_reconciliation[]`** — one entry per prior phase:
  `{phase_number, verdict, implemented_ids[], paths[], features[{id,
  statuses[]}], gap?, source | inferred_from}`. Everything but `gap` is
  code-owned (D-SC4-3): `wrap_review` joins `implemented[].prior_feature_ids`
  × `status` against `scan.prior_round.phases[].features` — `evidence_found`
  when every feature id the phase declared is claimed by a `complete` entry,
  `no_evidence_found` when none is claimed, `evidence_partial` otherwise,
  `unassessed` for a phase that declared no features (a fourth value the
  plan's three could not say). The rule reads feature coverage, not phase
  scope (`extended` counts as `introduced`). The model emits `{phase_number,
  gap}` for phases it judges short; `gap` and its provenance are merged by
  phase number, anything else it emits is overwritten, an entry naming no
  prior phase is dropped, and without a prior round the key is removed. The
  plan's `capability_ids` is `implemented_ids` (D-SC4-2: `capabilities` is
  the AI-catalog id space) and its `evidence[]` is the code-filled `paths[]`.
- **`review.unplanned_changes[]`** — `{area, summary, affects[],
  classification, source | inferred_from}`, 3–10 entries grouped by area.
  `classification` is code-owned (D-SC4-4): `out_of_round` when any path in
  `affects` is one of `git.since_last_round.most_touched` or
  `delta.files.added`, or a directory one of them sits under; `unknown`
  otherwise — `in_round` is in the enum but needs the round's start, which
  the scan does not carry yet (D-SC4-5, 4b). Hand-versus-agent edits are not
  classified; `agent_trailers_present` is shown as a fact.
- **`review.divergences[]`** — `{area, planned, found, kind, note?, source |
  inferred_from}`, LLM-emitted; `area` closed (`stack | persistence |
  providers | deployment | integrations | phases`), `kind` closed (`renamed
  | replaced | dropped | added | reshaped`); never a dependency name, which
  `scan.plan_drift` has (D-SC4-7).
- **`scan.coverage.changes_shown`** — whether the seed carried the Changes
  block (D-SC4-6). Optional, so an older scan still validates. Schema
  version stays 2.
- **Seed** (`code_scanner._sample`): the Prior Round block lists the phases
  by number and title ahead of the ids and closes with the planned stack
  facts (`persistence_primary`, `provider_names`, `integrations[].name`,
  `deployment_targets[].name`) as one paragraph (D-SC4-7/8); a new tier-A
  "Changes Since the Last Round" block after it — commits, authors, agent
  trailers, touched directories, the most-touched files (≤ 25) and, with a
  delta, the files added and removed (≤ 10 each) and the candidates that
  entered or left (D-SC4-6). Absent without a round boundary.
- **Prompt**: the three arrays in the consumers paragraph (Phaser
  `prior_round_reconciliation` and `unplanned_changes`, StackAdvisor
  `divergences`, Brainstormer `unplanned_changes`), the draft section names,
  the schema example (reconciliation as `{phase_number, gap}` only) and the
  field rules; the retry message names the two divergence enums and the two
  omit rules (D-SC4-9). **Renderer**: Prior Round Reconciliation and
  Unplanned Changes after Implemented, Divergences after Integrations; a
  review without the arrays renders as before (D-SC4-10).

## [2.7.1] — unreleased

D-SC4-13: `scan.dependencies` reads PEP 735 `[dependency-groups]`.

### Fixed
- `pyproject.toml` parsing read `[project].dependencies` and
  `[project.optional-dependencies]` only, so the dev tools `uv` and `pdm`
  declare in `[dependency-groups]` (`pytest`, `mypy`, `ruff`, …) counted as
  never declared: `plan_drift` listed them as `planned_unmatched` (4 of
  Spec4's own 6), and from 2.7.0 StackAdvisor's "Planned last round, not
  found in the code" block showed tools in daily use as missing. Every
  group's PEP 508 entries are now declared; `{include-group = …}` entries
  are skipped (the group they name is read on its own); a pyproject with
  groups but no `[project]` table declares them too. `delta.dependencies`
  and `plan_drift` follow with no change of their own.

## [2.7.0] — unreleased

Step 3b of the CodeScanner v2 plan (D-SC3-11): the consumer side of step 3.
The three `review` arrays 2.6.0 added reach the agents that asked for them,
and for the first time a consumer view carries measured `scan` facts beside
the model's judgments. Built after the first real BWS4 2.6.0 scan (D-SC3-14)
showed what the arrays contain.

### Added
- **`scan.` paths in `render_code_review`** — a field under the `scan.`
  prefix resolves against the envelope's computed `scan` layer and renders
  under a "Scan …" / measured heading rather than "Existing …", with its
  own guidance line in `FIELD_GUIDANCE`. Three fields render by hand
  instead of through the generic walker: `load_bearing` (contract keys
  beneath their module, `consumers` as a count), `scan.coverage` (one line
  of counts, never the sampled paths) and `scan.delta.dependencies` (one
  line per manifest that changed, the manifest name printed whole).
- **Phaser** reads `load_bearing` ("a phase that touches a load-bearing
  module names, in its instructions and verification, the contract it
  preserves"), `implemented` and a `scan.coverage` line.
- **StackAdvisor** reads `integrations` with its own routing line
  (`STACK_FIELD_GUIDANCE`: `llm_provider` entries are Topic 3's providers,
  the rest are its integrations), `scan.plan_drift.planned_unmatched`,
  `scan.plan_drift.declared_not_planned` and `scan.delta.dependencies`.
- **Brainstormer** reads `implemented` ("never propose a `complete` one as
  new; a `partial`/`stub` one is a finish-or-remove question").
- **Deployer**'s existing-infrastructure excerpt carries `integrations`,
  and a scan whose `git.dirty` is true adds a one-line note to plan against
  the committed tree.
- Four goldens for the consumer views from the step-3 fixture
  (`code_review_*_view_step3.md`); the 2a goldens are unchanged.

### Changed
- CodeScanner prompt: an `llm_provider` integration names the provider
  (OpenRouter, Anthropic, Groq); the SDK it is called through is in
  `ai_capabilities` (D-SC3-14 finding 1).
- `AGENT_REVIEW_VIEWS["stack_advisor"]` now carries `STACK_FIELD_GUIDANCE`,
  so the revision-path "updated code review" block matches the seed.

## [2.6.0] — unreleased

Step 3a of the CodeScanner v2 plan (D-SC3-1…10, 12): the review gains the
architecture, contract and integration judgments the plan's step 3 asks for,
and the seed gains the evidence they are answered from. The consumer tuples
are step 3b (2.7.0), after one real scan shows what the arrays contain.

### Added
- **`review.load_bearing[]`** — `{module, symbol?, role, contract: {inputs,
  outputs, invariants, side_effects}, consumers[], source | inferred_from}`,
  one entry per load-bearing candidate the seed names. `consumers` is
  code-owned (D-SC3-4): `wrap_review` fills it from
  `scan.module_graph.load_bearing_candidates` by module path and replaces
  whatever the model emitted, so the stored list is always the measured one;
  the emitted-block schema permits the key so an update-mode re-emission
  that carries it forward does not trip a retry.
- **`review.implemented[]`** — `{id, name, description, status, paths[],
  prior_feature_ids[], source | inferred_from}`; `status` closed
  (`complete | partial | stub | scaffolded_only`), `paths` required and
  non-empty. Named `implemented`, not the plan's `capabilities`, because
  that word already means AI-catalog ids downstream (D-SC3-2);
  `prior_feature_ids` are product-feature ids and are not validated at
  commit.
- **`review.integrations[]`** — `{name, kind, client_module,
  config_env_vars[], purpose, source | inferred_from}`; `kind` closed over
  StackAdvisor's vocabulary plus `llm_provider`, `web_search`, `database`,
  `cache`, `queue`, `mcp_server`; env-var names only (D-SC3-5).
- **`scan.module_graph.external_imports`** — `{package: [importing
  modules]}` for every package `unresolved` counts, up to 10 modules each
  (D-SC3-6). Optional in the schema, so a 2.1–2.5 scan still validates.
- **Two tier-A seed blocks** rendered from the scan (`code_scanner._sample`):
  "External Packages and Their Importers" (≤ 6 modules per package) and
  "Prior Round" (the prior round's product-feature ids with the phases that
  declared them, ≤ 50), plus the candidate list at the head of Key Module
  Signatures (D-SC3-8/9). `coverage.external_imports_shown` and
  `coverage.prior_round_shown` record them.
- **Prompt**: the three arrays in the consumers paragraph, draft section
  names, the schema example and the field rules; the retry message names
  the two new enums. **Renderer**: Load-Bearing Modules and Implemented
  after Architecture, Integrations after AI Capabilities; a review without
  the arrays renders as before.

## [2.5.0] — unreleased

Step 2b of the CodeScanner v2 plan (D-SC2-6): the seed's body tier adds the
files most touched since the last round, and the git block records them.

### Added
- **`git.since_last_round.most_touched`** — `[{path, commits}]`, the 25
  files with the most commits since the round boundary, most first, then by
  path; `.spec4/` excluded as elsewhere in the block. One extra
  `git log --name-only` that is not capped at 500 commits, so the counts are
  exact when the commit list is truncated. Optional in the schema, so a
  2.1–2.4 block on disk still validates. Absent when that one log fails;
  the rest of `since_last_round` stands.
- **Tier C's third group** (`code_scanner._sample`): after the entrypoint
  candidates and the top three by fan-in, the most-touched files that are
  graph nodes, in the git block's order with reached files first, skipping
  any file already shown and any thin `__init__.py`. Whole-or-headed bodies
  and the C budget are unchanged; without a git block or a round boundary
  the group is empty and the seed is as in 2.4.0.
- Signature and body headings note a file's churn: `(fan-in 22, 12 commits
  since last round)`. Only when the file is in `most_touched`.

### Changed
- The Scan Summary's Git line is unchanged: the per-file list is in the
  stored scan and the seed, not the one-line summary.

## [2.4.0] — unreleased

Step 2a of the CodeScanner v2 plan: the scan seed's evidence is chosen from
the `scan` layer instead of walk order. The graph, signatures and reach are
computed before the seed and the sampler spends one token budget across
four tiers. On Spec4's own tree the seed goes from 3 sampled files (two of
them eval scripts) and 41 of 103 `src/` modules named to 4 bodies, 17
signature files and every `src/` module named, at ~17.4 k tokens of
evidence (was ~5.8 k). Step 2b adds the files most touched since the last
round.

### Added
- **Tiered evidence** (`code_scanner._sample`). A — the file tree, README,
  manifests, CI, deployment signals and a new Project Conventions section.
  B — every load-bearing candidate and entrypoint candidate as a compact
  signature block (`def name(sig)  # first doc line`, one per symbol), up to
  6 k tokens. C — bodies of the entrypoint candidates and the top three
  candidates by fan-in, whole when at most 4 k tokens, else the first 150
  lines plus the file's signatures; up to 12 k plus what B left unspent,
  less what D needs. D — one signature block per product package no B or C
  file sits in, from its highest fan-in member, up to 3 k. A block that does
  not fit is skipped, so a smaller one later in the order can still use the
  room. Within each tier, files reached from an entrypoint go first; an
  `__init__.py` under 20 non-blank lines never takes a slot.
- **Evidence budget**: 24,000 tokens (`approx_tokens`), overridable per scan
  with `llm_config["scan_context_tokens"]`. `approx_tokens` is now the
  budget's meter as well as the narrated request size.
- **`module_graph.reach`** — `{basis, entrypoints, reached, unreached_dirs}`:
  how many graph nodes are transitively imported from the entrypoint
  candidates (or, with none, from the packages `pyproject.toml`'s
  `[project].name` / `[tool.*].packages` or `package.json`'s `main`
  declare), and the shallowest directories nothing reaches. On Spec4: 97
  from `src/spec4/app.py`; unreached `evals`, `scripts`, `src/spec4/assets`.
  The sampler's ranking, made auditable without storing the edge list.
- **Project Conventions** section: root-level `.env.example` /
  `.env.sample` / `.env.template` (first 1,500 characters), `CLAUDE.md`,
  `AGENTS.md`, `CONTRIBUTING.md` (first 80 lines each); `CLA.md` and
  `LICENSE` named as present, never pasted.
- **`scan.coverage`** gains `signatures_shown`, `conventions`, `tree: {form,
  nodes_listed, truncated}` and `evidence_tokens`. All optional in the
  schema, so a 2.1–2.3 scan on disk still validates.
- **Scan Summary**: the "Shown to the model" line adds signature and
  convention file counts and the evidence size; a Reach line follows the
  candidates. Both absent for older scans, whose goldens are unchanged.

### Changed
- The **file tree** is a directory rollup (every directory holding a file,
  with its count and top three extensions; never capped) plus the list of
  every non-test source file (capped at 400). It replaces the first 150
  paths of the walk, which on Spec4 hid 68 `src/` files.
  `coverage.tree_listed` / `tree_truncated` now count that node list.
- **Deployment signals** add `Caddyfile`, `deploy.sh`, `nginx.conf` and any
  `*.service` unit; the cap stays five files.
- `collect_scan` is split into `measure_scan` (before the seed) and
  `attach_coverage` (after it); `collect_scan` composes them.
  `gather_project_context` moved from `_scan` to `_sample` and takes the
  measured scan; the package import path is unchanged.

## [2.3.0] — unreleased

The last of the step-1 `scan` collectors: what the prior Spec4 round planned,
how the tree's manifests compare to that plan, and what changed since the
previous scan. With these, a scan carries its own history; downstream
consumers no longer need to open `.spec4/` to know what was built last time.
The visible change is one more Scan Summary line.

### Added
- **`scan.prior_round`** — the latest implemented round as an *extract*,
  never a pass-through (a round's artifacts run to hundreds of kilobytes;
  the extract is ~15 KB on BWS4): per phase its number, title, clipped
  summary and verification, feature and capability declarations (`{id,
  role}`) and `tech_stack_spec` dependency names; the stack's languages,
  libraries (`{name, category}`), deployment targets, primary persistence
  choice, provider and infrastructure keys and integrations; the vision's
  name, feature ids and revision count; the feature specs' version and ids;
  the AI catalog's nodes reduced to `{id, kind, tier, introduced_in_version,
  linked_vision_features, requires}`; and the prior `code_review.json` by
  reference (`path`, `schema_version`, `bytes`) with a small extract of what
  the comparisons read (`project_type`, `commands`, deployment kinds,
  dependency names). One version, one directory: a file missing from that
  round is `null` or `[]`, never a value from another round — except the
  catalog, which falls back to the newest implemented round that has one
  (a round can be implemented without the Agentifier having run), with
  `capabilities_from_version` saying which. `artifacts_present` names the
  files the directory holds, so "absent" and "unreadable" read differently.
- **`scan.dependencies`** — the dependencies each `pyproject.toml`
  (`[project].dependencies` and optional groups), `package.json`
  (`dependencies`, `devDependencies`) and `go.mod` (`require`) declares, by
  manifest path, as `{name: specifier}`. On every scan, since the next
  scan's `delta` reads this one's. Nothing else in a manifest is read.
- **`scan.plan_drift`** — the prior plan's dependencies (the stack's
  libraries and every phase's `tech_stack_spec.dependencies`, each entry
  tagged with its sources) against `scan.dependencies`, in four buckets:
  `planned_in_manifests`, `planned_only_imported` (never declared, but in
  `module_graph.unresolved` — a smell), `planned_unmatched` (systemd, Caddy,
  uv: what a manifest cannot see, or a plan the code never followed) and
  `declared_not_planned`. Names are compared after lowercasing, stripping a
  trailing version token (`Python 3.12`) and folding non-alphanumerics, so
  StackAdvisor's `PydanticAI` meets Phaser's `pydantic-ai`; the scoped npm
  names that defeat the fold (`@tanstack/react-query` for `TanStack Query`)
  match on word-token subset. No alias table. Which bucket means drift is
  the consumer's judgment.
- **`scan.delta`** — this scan against the prior one, scan to scan and
  never through `git`: paths added and removed (with `partial` when either
  listing was capped), dependencies added, removed and bumped per manifest
  in both scans, load-bearing candidates that entered or left, and public
  symbols added, removed or changed (by name; `changed` when the signature
  text differs) for files in both signature blocks. The prior is the latest
  implemented round's review when it carries a measured 2.x `scan`, else the
  active round's prior review — the same precedence as
  `git.since_last_round`. An identical scan yields a present, empty block.
- **Scan Summary** gains a line naming the prior round, its phase count and
  implementation date, the catalog's round when it differs, and the drift
  counts — present only when the scan carries a `prior_round`. Every
  existing golden is unchanged.

### Changed
- `scan.git` excludes Spec4's own `.spec4/` from the dirty and untracked
  counts (a round's artifacts are its record of the project, not a change
  to it — every BWS4 scan read "1 untracked" for its own `v9/`), counts
  untracked *files* rather than collapsed directories, and adds
  `working_tree: {modified_top_dirs, untracked_top_dirs}` in the shape of
  `since_last_round.touched_top_dirs`. The Scan Summary's git line reads
  "3 modified, 2 untracked" from it; a 2.1/2.2 block keeps its "dirty"
  wording.
- `scan.signatures` lists public module-level assignments as
  `kind: "variable"` — the name and its annotation, never the value
  (Python `ast.Assign`/`AnnAssign`; `export const` was already covered) —
  so `settings: Settings` and `async_session_factory` appear beside the
  `def`s and `class`es that use them. JavaScript/TypeScript signatures now
  see `export default <Identifier>` (`kind: "default"`) and `export { a, b
  as c }` lists (`kind: "export"`); BWS4's `App.tsx` and `main.tsx` had no
  symbols without them.

## [2.2.0] — unreleased

The second pair of `scan` collectors: the import graph and the signatures of
what it ranks. Both feed the steps that follow (sampling and the
`load_bearing` judgment); for now the only visible change is one line in the
Scan Summary.

### Added
- **`scan.module_graph`** — import edges between the project's own source
  files, resolved for Python (through `ast`, so `from pkg import mod` lands
  on `pkg/mod.py`, not the package), JavaScript/TypeScript (relative
  specifiers, with the usual extension and `index` probing) and Go (in-module
  packages via `go.mod`). Other source languages are nodes without edges.
  Test files are outside the graph on both ends — under a test directory, or
  named as a test beside the code (`_test.go`, `.test.ts`, `test_*.py`).
  Stored: per-node fan-in and fan-out counts (never the edge list), the top
  ten modules by fan-in with at least two importers as
  `load_bearing_candidates`, each with its consumers, and the imports that
  resolve to nothing in the tree, counted by top-level name (Python's
  stdlib filtered; capped at fifty, with a flag).
- **`scan.signatures`** — for the candidates and the entrypoint candidates:
  public top-level definitions with the first line of their docstring
  (Python `def`/`class` via `ast`; JavaScript/TypeScript `export`s; Go's
  exported `func`s and `type`s), plus the module docstring. The first `scan`
  block whose size follows the code, so it is budgeted: forty symbols per
  file, 32 KB in all, taken in rank order, with `truncated` flags at both
  levels.
- **Scan Summary** gains a line naming the top five candidates by fan-in,
  present only when the scan carries a graph. Every existing golden is
  unchanged.

### Fixed
- A re-scan forced by the schema gate (a `code_review.json` from an older
  Spec4) kept the loaded *complete* state while the new review was still
  being discussed, so the chat action row offered Open / Download / Continue
  for the stale file. The gate-driven re-scan now drops that state as the
  Re-scan button does, until the new review is committed.

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
