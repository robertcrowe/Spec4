# Tests

This file covers how the suite is laid out, how to run it, and what it pins. Module
names are current. Line numbers are left out, because they go stale.

## Running it

- **`uv run pytest`** runs the suite. `pyproject.toml` sets `testpaths = ["tests"]`, so
  `evals/`, which makes real LLM calls, is not collected.
- **The gate:**

  ```sh
  uv run ruff check src/ tests/
  uv run ruff format --check src/ tests/
  uv run mypy src/
  uv run pytest --cov=spec4
  ```

  Keep `--cov=spec4`: a bare `--cov` also measures the test files, and inflates the
  total.
- **At the last measurement,** 4,211 tests were collected: 4,210 pass and 1 is skipped.
  The skip is `tests/test_session.py`'s "Designer has no chat turn".

## Layout

| Path | What it holds |
|---|---|
| `tests/test_*.py` | 91 files: agents, layouts, callbacks, session, streaming and utilities |
| `tests/agentifier/` | 27 files: the Agentifier orchestrator and its sub-agents |
| `tests/integration/` | 5 files: end-to-end pipeline runs with mocked LLMs, and browser tests |
| `tests/golden/` | Pinned renderer and phase-file output, and the JSON fixtures that produce it (`fixtures/`) |
| `tests/snapshots/` | `component_ids.json`: every component id the layouts emit |
| `tests/conftest.py` | Suite-wide fixtures. An autouse stub replaces the Prioritizer's draw, so orchestrator and integration tests never reach the network |
| `tests/_golden.py` | `assert_golden` and `load_fixture` |
| `tests/_chunks.py` | Streaming-chunk stand-ins shaped like LiteLLM's real chunk types |

**A browser test starts the Dash server as a subprocess.** An in-process server drains
Dash's callback registry, and other test modules then fail.

## Goldens and the component-id snapshot

Both pin a frozen surface byte for byte. They are characterization tests: they say what
the code does today, so a diff in one is a question ("did this change on purpose?"), not a
verdict. Regenerate them deliberately, then read the diff before committing it:

```sh
SPEC4_UPDATE_GOLDENS=1 uv run pytest tests/test_renderer_goldens.py tests/test_project_manager_golden.py
SPEC4_UPDATE_SNAPSHOTS=1 uv run pytest tests/test_layout_contract.py
```

These are the suite's only two environment switches.

## Streaming chunks

**Build streamed LLM output with `tests/_chunks.py`, not `MagicMock`.**
- A mock answers every attribute with a truthy child. A test can then pass against a
  field the real chunk never has, and the production code's `getattr` guards are never
  exercised.
- A mock is also slow. The chunk factory replaced about 216,000 mock instantiations
  (cleanup Phase 6g).

## The regression floor

The cleanup protected 456 node ids:
- the seven whole-file entries, which collect 188 of them: `test_app_import_smoke.py`, `test_layout_contract.py`, `test_project_manager_golden.py`, `test_renderer_goldens.py`, `test_streaming_characterization.py`, `test_callback_co_presence.py`, `test_import_layering.py`;
- 85 named tier-A and ordering ids;
- 183 tier-B ids, in 33 classes.

The list is `scripts/cleanup/data/floor.json`. `uv run python scripts/cleanup/floor_check.py`
checks that every one still collects, and `scripts/cleanup/petition_check.py` checks a
change that touches one. `scripts/cleanup/README.md` has the details.

## Coverage by module

Measured with `uv run pytest --cov=spec4 --cov-report=term-missing -q` at `85a9cb6`. No
code in `src/` or `tests/` has changed since. Total: **12,459 statements,
876 missed, 93%**.

The UI callbacks are the least-covered code. That is the cleanup's known limit
(`CLEANUP_REPORT.md` §7.1).

| Module (`src/spec4/`) | Statements | Missed | Cover |
|---|---:|---:|---:|
| `__init__.py` | 5 | 2 | 60.0% |
| `_artifacts.py` | 257 | 17 | 93.4% |
| `_paths.py` | 60 | 0 | 100.0% |
| `_phase_markdown.py` | 230 | 0 | 100.0% |
| `_usage.py` | 160 | 2 | 98.8% |
| `agentifier/__init__.py` | 0 | 0 | 100.0% |
| `agentifier/_ff_review.py` | 93 | 1 | 98.9% |
| `agentifier/_render.py` | 253 | 11 | 95.7% |
| `agentifier/_seed.py` | 161 | 13 | 91.9% |
| `agentifier/agentifier.py` | 1,002 | 114 | 88.6% |
| `agentifier/composer.py` | 133 | 3 | 97.7% |
| `agentifier/cross_cutting_analyst.py` | 118 | 1 | 99.2% |
| `agentifier/grounding.py` | 89 | 3 | 96.6% |
| `agentifier/infra_expander.py` | 42 | 0 | 100.0% |
| `agentifier/linker.py` | 165 | 0 | 100.0% |
| `agentifier/panel_closure.py` | 61 | 2 | 96.7% |
| `agentifier/pattern_loader.py` | 159 | 18 | 88.7% |
| `agentifier/prioritizer.py` | 178 | 3 | 98.3% |
| `agentifier/reference_verifier.py` | 36 | 0 | 100.0% |
| `agentifier/requires_reconciler.py` | 264 | 9 | 96.6% |
| `agentifier/scout.py` | 136 | 0 | 100.0% |
| `agentifier/spec_drafter.py` | 101 | 1 | 99.0% |
| `agentifier/subagents.py` | 73 | 1 | 98.6% |
| `agentifier/tier_analyst.py` | 132 | 3 | 97.7% |
| `agents/__init__.py` | 0 | 0 | 100.0% |
| `agents/_code_review_schema.py` | 28 | 0 | 100.0% |
| `agents/_feature_context.py` | 585 | 21 | 96.4% |
| `agents/_image_probe.py` | 16 | 0 | 100.0% |
| `agents/_manifest.py` | 127 | 6 | 95.3% |
| `agents/_phase_coverage.py` | 144 | 2 | 98.6% |
| `agents/_phase_schema.py` | 27 | 2 | 92.6% |
| `agents/_reask.py` | 116 | 7 | 94.0% |
| `agents/_seam_check.py` | 180 | 11 | 93.9% |
| `agents/_stack_context.py` | 403 | 14 | 96.5% |
| `agents/_tool_probe.py` | 16 | 0 | 100.0% |
| `agents/_turn_flow.py` | 118 | 29 | 75.4% |
| `agents/_utils.py` | 0 | 0 | 100.0% |
| `agents/brainstormer.py` | 314 | 9 | 97.1% |
| `agents/code_scanner/__init__.py` | 125 | 3 | 97.6% |
| `agents/code_scanner/_prompt.py` | 2 | 0 | 100.0% |
| `agents/code_scanner/_review_render.py` | 403 | 5 | 98.8% |
| `agents/code_scanner/_scan.py` | 152 | 13 | 91.4% |
| `agents/deployer.py` | 213 | 3 | 98.6% |
| `agents/designer.py` | 273 | 33 | 87.9% |
| `agents/feature_speccer.py` | 229 | 6 | 97.4% |
| `agents/phaser/__init__.py` | 204 | 8 | 96.1% |
| `agents/phaser/_phase_extract.py` | 114 | 0 | 100.0% |
| `agents/phaser/_prompt.py` | 2 | 0 | 100.0% |
| `agents/phaser/_revision.py` | 35 | 0 | 100.0% |
| `agents/stack_advisor/__init__.py` | 76 | 0 | 100.0% |
| `agents/stack_advisor/_prompt.py` | 2 | 0 | 100.0% |
| `agents/stack_advisor/_render.py` | 290 | 6 | 97.9% |
| `agents/stack_advisor/_stack_shape.py` | 87 | 2 | 97.7% |
| `app.py` | 72 | 8 | 88.9% |
| `app_constants.py` | 30 | 0 | 100.0% |
| `callbacks/__init__.py` | 115 | 25 | 78.3% |
| `callbacks/_artifacts.py` | 140 | 30 | 78.6% |
| `callbacks/_chat.py` | 196 | 50 | 74.5% |
| `callbacks/_gate.py` | 98 | 8 | 91.8% |
| `callbacks/_nav.py` | 74 | 28 | 62.2% |
| `callbacks/_setup.py` | 90 | 16 | 82.2% |
| `callbacks/_shared.py` | 21 | 0 | 100.0% |
| `callbacks/designer/__init__.py` | 77 | 7 | 90.9% |
| `callbacks/designer/_mock_gen.py` | 146 | 16 | 89.0% |
| `callbacks/designer/_refine.py` | 115 | 23 | 80.0% |
| `callbacks/designer/_wizard.py` | 125 | 63 | 49.6% |
| `design_manifest.py` | 80 | 0 | 100.0% |
| `feature_specs.py` | 344 | 80 | 76.7% |
| `layouts/__init__.py` | 78 | 3 | 96.2% |
| `layouts/_agent_rows.py` | 86 | 3 | 96.5% |
| `layouts/_artifact_view.py` | 196 | 7 | 96.4% |
| `layouts/_chat.py` | 23 | 0 | 100.0% |
| `layouts/_chat_actions.py` | 124 | 1 | 99.2% |
| `layouts/_chat_panels.py` | 43 | 0 | 100.0% |
| `layouts/_chat_status.py` | 34 | 0 | 100.0% |
| `layouts/_llm_gate.py` | 55 | 0 | 100.0% |
| `layouts/_round_cost.py` | 70 | 0 | 100.0% |
| `layouts/_round_tree.py` | 113 | 0 | 100.0% |
| `layouts/_setup.py` | 70 | 1 | 98.6% |
| `layouts/_shared.py` | 83 | 0 | 100.0% |
| `layouts/_status_bar.py` | 45 | 0 | 100.0% |
| `layouts/designer.py` | 159 | 12 | 92.5% |
| `llm.py` | 348 | 17 | 95.1% |
| `llm_selection.py` | 101 | 0 | 100.0% |
| `project_manager.py` | 110 | 1 | 99.1% |
| `providers.py` | 93 | 15 | 83.9% |
| `session.py` | 196 | 34 | 82.7% |
| `stack_routing.py` | 101 | 2 | 98.0% |
| `streaming.py` | 194 | 18 | 90.7% |
| `usage_report.py` | 98 | 7 | 92.9% |
| `version_check.py` | 40 | 0 | 100.0% |
| `websearch.py` | 87 | 17 | 80.5% |
