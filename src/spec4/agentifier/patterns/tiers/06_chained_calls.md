---
name: chained_calls
category: tier
library_version: "1.0.0"
last_reviewed: "2026-05-30"
tier_order: 6
cost_range_usd: "$0.01–$0.20"
latency_range_seconds: "3–20"
required_infrastructure:
  - "pipeline_runner"
references:
  - "Anthropic — Building Effective Agents (https://www.anthropic.com/engineering/building-effective-agents)"
  - "Wu et al. — AI Chains: Transparent and Controllable LLM Prompting (https://arxiv.org/abs/2110.01691)"
---

## Description

Multiple LLM calls wired in a *known, fixed* sequence — for example
extract → classify → generate, or translate → summarise → format. Each step's
output feeds the next, but the pipeline structure is decided by the developer at
design time, not by the model at run time. There is no adaptive replanning: the
same steps run in the same order every time. This is prompt chaining /
"workflow," distinct from an autonomous `planning_agent`.

## When it works

- The task decomposes into a stable sequence of sub-steps that are the same on every run (*e.g., OCR-clean → extract fields → validate → format*).
- Each step is simpler and easier to prompt, test, and evaluate in isolation than one giant prompt would be.
- Intermediate outputs are valuable to inspect, log, cache, or gate on (you can assert on the extraction before generating).
- Splitting the work measurably improves reliability over a single mega-prompt that tried to do everything at once.
- You can insert a deterministic check or a `human_in_the_loop` gate between steps.

## When it doesn't

- The sequence of steps varies based on intermediate results — sometimes you need step C, sometimes you skip it. That adaptivity is `planning_agent`.
- A single structured-output call already produces all the needed fields reliably in testing — the chain adds latency and cost for no quality gain.
- The steps are so tightly coupled that splitting them loses context the model needs to do any of them well.
- The "chain" is really one model call plus deterministic glue — keep the glue as plain code, not extra LLM calls.

## Over-engineering signs

- Three sequential calls were used where one structured-output prompt returns all the fields at once and tests just as well — *consolidate the calls.*
- A step is an LLM call that does something deterministic (parse JSON, look up a code, format a date) — replace it with code.
- The chain was built "for modularity" though no intermediate output is ever inspected, gated, or reused.
- Each step re-sends the entire growing context, multiplying token cost, when later steps need only a small slice.
- A fixed 5-call chain is being maintained where a `tool_agent` or single call would cover the realistic inputs.

## Under-engineering signs

- A single prompt is being asked to extract, reason, and generate all at once, and it drops or conflates steps — splitting into a chain would make each step reliable.
- Failures are hard to debug because everything happens in one opaque call with no inspectable intermediates.
- The genuine sequence depends on intermediate results and the fixed chain keeps hitting cases it can't route — you've outgrown chaining; consider `planning_agent`.
- Per-step evaluation is impossible because there are no per-step outputs to evaluate.

## References

- Anthropic, "Building Effective Agents" — prompt chaining as a first-class workflow pattern, preferred over autonomous agents when the steps are known.
- Wu et al. (2022), "AI Chains" — evidence that decomposing a task into chained LLM steps improves transparency, controllability, and quality over a single call.
