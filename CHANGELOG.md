# Changelog

All notable changes to Spec4, newest first. This file starts at 1.0.0; see
[Pre-1.0](#pre-10) for what came before.

Entries are keyed to release tags, since a tag is what a user could install.
Two places where the repo's own record is uneven, stated rather than smoothed
over: the `v1.5.0` tag sits on the last commit of its series, not on the
version bump eight days earlier, so 1.5.0 covers everything in between; and
1.1.0 was bumped in `pyproject.toml` but never tagged, so its changes reached
users as part of 1.5.0.

## [1.5.1] — unreleased

Prompt caching, and the reporting to tell whether it is working. Present in the
working tree, not yet committed or tagged.

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

[1.5.1]: https://github.com/robertcrowe/Spec4/compare/v1.5.0...HEAD
[1.5.0]: https://github.com/robertcrowe/Spec4/compare/v1.0.0...v1.5.0
[1.1.0]: https://github.com/robertcrowe/Spec4/compare/v1.0.0...cb9f9ae
[1.0.0]: https://github.com/robertcrowe/Spec4/releases/tag/v1.0.0
