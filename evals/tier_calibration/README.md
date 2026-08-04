# Tier Calibration Eval Harness

A lightweight, on-demand evaluation tool that measures the Tier Analyst's
over-engineering rate against frozen labeled fixtures.

**This is NOT part of `make test`.** It makes real LLM calls, costs tokens,
and is run manually before/after prompt or pattern changes to measure calibration.

---

## What it measures

The Tier Analyst is biased toward over-engineering when:

- Aspirational candidate names ("smart_", "intelligent_", "engine") inflate
  perceived complexity.
- The system prompt lacks a strong burden of proof for escalating above
  `deterministic`.

This harness feeds frozen labeled candidates directly to Tier Analyst (no Scout,
no full pipeline) and computes:

- **Over-engineering rate** — the headline metric: fraction of candidates
  recommended at a higher tier than the labeled ground truth.
- **Under-engineering rate** — fraction recommended below ground truth.
- **Exact-match rate** — fraction exactly matching the label.
- **Mean absolute tier error** — average distance on the 9-tier ladder.

The ShelfLife `focused-9` fixture has a ground-truth distribution of
6 deterministic / 1 embeddings / 2 single_call. A well-calibrated Tier Analyst
should produce an over-engineering rate below ~20% on this fixture.

---

## Not part of `make test`

The eval runner (`run_tier_eval.py`) lives in `evals/`, outside `src/` and
`tests/`. It is never collected by pytest. It always exits 0 — it is a
measurement tool, not a gate.

---

## Requirements

- Python 3.12+, `uv` environment active (`source .venv/bin/activate` or prefix with `uv run`)
- A configured LLM provider. Set:

```bash
export SPEC4_MODEL="claude-sonnet-4-6"      # or gpt-4o-mini, gemini/gemini-2.0-flash, etc.
export ANTHROPIC_API_KEY="sk-ant-..."       # or OPENAI_API_KEY, GEMINI_API_KEY, etc.
# Optional: override API key directly
export SPEC4_API_KEY="sk-..."
# Optional: custom base URL (e.g. Nebius)
export SPEC4_API_BASE="https://api.example.com/v1"
```

`SPEC4_MODEL` is required. The API key is picked up automatically by LiteLLM
from the provider-specific environment variable (`ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`, etc.); `SPEC4_API_KEY` overrides this if set.

---

## How to run

```bash
# Default: all fixtures in evals/tier_calibration/fixtures/
uv run python evals/run_tier_eval.py

# Specific fixture(s):
uv run python evals/run_tier_eval.py evals/tier_calibration/fixtures/shelflife_focused9.json

# Run each candidate N times and report modal recommendation + variation:
uv run python evals/run_tier_eval.py --runs 3

# Dry-run (no real LLM calls — shows output format only):
uv run python evals/run_tier_eval.py --dry-run
```

---

## Example output

```
==============================================================
  TIER CALIBRATION EVAL  —  real LLM calls, costs tokens
==============================================================

Fixture: shelflife_focused9.json  (project: shelflife, 9 candidates)

Candidate                          Expected        Got             Δ   Borderline
─────────────────────────────────────────────────────────────────────────────────
receipt_photo_ocr_parsing          single_call     single_call      0
barcode_data_enrichment            deterministic   deterministic    0
smart_expiry_prediction            deterministic   deterministic    0
...

── Summary ─────────────────────────────────────────────────
Over-engineering rate:   2/9 (22%)
Under-engineering rate:  0/9 (0%)
Exact-match rate:        7/9 (78%)
Mean absolute tier error: 0.44

Over-engineered candidates:
  smart_expiry_prediction:  deterministic → single_call  (+1)
  expiration_alert_optimization:  deterministic → embeddings  (+2)

══════════════════════════════════════════════════════════════
OVERALL (1 fixture, 9 candidates)
  Over-engineering rate:   22%   ← headline metric
  Under-engineering rate:  0%
  Exact-match rate:        78%
  Mean absolute tier error: 0.44
══════════════════════════════════════════════════════════════
```

---

## Intended workflow

1. Run the harness before making a prompt or pattern change:
   ```
   uv run python evals/run_tier_eval.py > before.txt
   ```
2. Make the change (edit `TIER_ANALYST_SYSTEM_PROMPT` or a tier pattern file).
3. Run again and compare:
   ```
   uv run python evals/run_tier_eval.py > after.txt
   diff before.txt after.txt
   ```
4. The over-engineering rate is the headline metric. A decrease is good.

---

## Adding a new fixture

1. Drop a `.json` file in `evals/tier_calibration/fixtures/` following the
   schema in `schema.md`.
2. For highest fidelity, paste **verbatim Scout output** for `name` and
   `rough_description` — aspirational naming is part of what is being tested.
3. Label each candidate with `expected_tier` using your best judgment, or a
   consensus of two independent human reviewers.
4. Run the harness to get a baseline before any prompt changes.

The harness has no dependency on the ShelfLife fixture; any fixture in
`fixtures/` will be evaluated automatically.

---

## Interpreting the over-engineering rate

| Rate | Interpretation |
|---|---|
| 0–15% | Well-calibrated. Prompt and patterns are working. |
| 15–30% | Moderate over-engineering. Worth investigating which candidates are affected. |
| 30%+ | Systematic over-engineering. Likely a framing or burden-of-proof gap. |

A single fixture of 9 candidates has high variance — use `--runs 3` or more for
a stable rate before drawing conclusions.
