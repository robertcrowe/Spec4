# Agentifier Mechanism Probe

Measures the impact of giving the **Tier Analyst** and **Spec Drafter** the
mechanism pattern library (`src/spec4/agentifier/patterns/mechanisms/*`), by
running the frozen visions in `probe_visions/` through the real sub-agent
pipeline and scoring the resulting `ai_features.json` against per-vision
`expectations.json` files.

**Not part of `make test`.** The runner makes real LLM calls and costs
tokens; it always exits 0. Only the scorer's unit tests
(`test_mechanism_scoring.py`) run under pytest — they are pure.

---

## Pieces

| File | Role |
|---|---|
| `probe_visions/*/` | Frozen inputs: `.spec4/v0/vision.json` + `expectations.json` per vision (see `probe_visions/README.md` for the fixture design) |
| `run_mechanism_probe.py` | Headless pipeline runner + report CLI |
| `mechanism_scoring.py` | Deterministic scorer — the actual probe; no LLM calls |
| `test_mechanism_scoring.py` | Unit tests pinning the scorer's semantics |

The scorer is separate from the runner on purpose: `ai_features.json`
produced any other way — a real interactive app session pointed at a probe
directory, a saved artifact from a bug report — scores identically via
`--score-only`.

---

## What the runner executes

The production phase-1/phase-2 sequence from `spec4.agentifier.agentifier`,
with the conversational pauses replaced by their most-permissive resolution:

```
Scout → Linker (apply_overlay) → Composer
      → breadth panel: select ALL, then close_selection (production closure)
      → Tier Analyst per candidate
      → catalog: auto-accept every recommendation (tier_decision = recommendation)
      → Spec Drafter per entry (with production's one unreadable-output retry)
      → _build_ai_features → _expand_infrastructure
```

Skipped, and why the omission doesn't bias the mechanism measurement:

- **Catalog conversation** — auto-accepting means the Tier Analyst's raw
  recommendation is what gets measured, undiluted by a second model arguing
  with a simulated developer. That is the quantity the prompt change acts on.
- **reference_verifier** — needs a live web-search provider; only rewrites
  `references`, which the probe does not score.
- **Cross-cutting analysis / priority review** — write the `cross_cutting`
  block and feature ordering; never touch per-feature `mechanisms` or `tier`.
- **Requires-reconciliation** — a pure edge-direction pass, not scored.

Cost per vision per run: 3 fixed calls (Scout, Linker, Composer) plus two
calls per surviving candidate (Tier Analyst + Spec Drafter). With 3–4 vision
features each typically decomposing into 3–8 candidates, expect roughly
10–20 calls per vision, ~100 per full 7-vision sweep.

---

## How to run

Requires `SPEC4_MODEL` (and provider key) exactly like
`evals/run_tier_eval.py`:

```bash
export SPEC4_MODEL="claude-sonnet-4-6"
export ANTHROPIC_API_KEY="sk-ant-..."

# Baseline, three runs per vision (variance is real — never compare single runs)
uv run python evals/agentifier/run_mechanism_probe.py --label before --runs 3

# …make the prompt/pattern change…

uv run python evals/agentifier/run_mechanism_probe.py --label after --runs 3

# Re-score anytime without LLM calls, and diff the OVERALL blocks
uv run python evals/agentifier/run_mechanism_probe.py --score-only --label before
uv run python evals/agentifier/run_mechanism_probe.py --score-only --label after

# Single vision, format preview without any calls
uv run python evals/agentifier/run_mechanism_probe.py \
    evals/agentifier/probe_visions/04_parallel_fanout_grantloom --dry-run
```

Outputs land in `<vision_dir>/runs/<label>/ai_features_run{i}.json` with a
`meta.json` recording the model. `--score-only` with no `--label` also picks
up a `.spec4/v0/ai_features.json` saved by an interactive session.

---

## Metrics

Per vision and aggregated across the sweep (`OVERALL` block):

| Metric | Meaning | Expected effect of the change |
|---|---|---|
| Vision-feature coverage | expectation features with ≥1 linked entry, excluding `coverage_optional` fillers Scout is right to decline | unchanged — a Scout property; uncovered features are excluded from the mechanism denominators so a Scout miss can't masquerade as a mechanism result |
| **Required-mechanism recall** | `mechanisms_required` satisfied on covered features | **should rise** |
| **Forbidden violations** | `mechanisms_forbidden` hits — the traps | **must not rise**; the patterns' over-engineering sections exist to hold this down |
| Target-mechanism spam | target mechanism on entries not linked to `target_mechanism_valid_on` | should stay ~0 |
| Tier within expected set / mean signed delta | tier calibration; positive delta = inflation | inflation should fall — vision 04's `portfolio_clause_sweep` is the sharpest single indicator |
| Control mechanism instances | any mechanism in vision 07 | should stay 0 |

`also_check` lines (decision_authority, tool_access source, mechanism
configuration quality) are printed when their feature has a finding — they
are for manual or judge-model review, not mechanical scoring.

### Reading a result

The scorer's join is by edges, not names: an entry belongs to a vision
feature when `slug(vision_feature)` appears in its `linked_vision_features`.
Requirements apply to the linked **set** — a required mechanism must appear
on at least one linked entry, a forbidden one on none. The tier check reads
only the **highest-ordinal** linked `kind: "feature"` entry against
`expected_tiers`: the feature's overall complexity, so Scout decomposing a
feature into cheaper sub-stages doesn't read as deflation
(registry-injected `kind: "infrastructure"` nodes are exempt).

Entries linked to **several** expectation features (Composer coordinators)
carry no single feature's ground truth, so they get set arithmetic instead:
a forbidden violation only when every linked feature forbids the mechanism
(intersection), and a tier check against the union of the linked features'
`expected_tiers` — real inflation above all members still scores.

Run-to-run variance is high (small candidate counts per vision). Use
`--runs 3` minimum and compare aggregate rates between labels, not
individual runs or individual features.
