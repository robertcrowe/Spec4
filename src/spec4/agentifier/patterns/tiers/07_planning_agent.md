---
name: planning_agent
category: tier
library_version: "1.0.0"
last_reviewed: "2026-05-30"
tier_order: 7
cost_range_usd: "$0.05–$2.00+"
latency_range_seconds: "10–300+"
required_infrastructure:
  - "agent_loop_runtime"
  - "tool_execution_harness"
references:
  - "Anthropic — Building Effective Agents (https://www.anthropic.com/engineering/building-effective-agents)"
  - "Yao et al. — ReAct: Synergizing Reasoning and Acting in Language Models (https://arxiv.org/abs/2210.03629)"
---

## Description

Multi-step, adaptive, autonomous reasoning. The agent plans, executes, observes,
reflects, and revises its own plan in a loop, deciding at run time what to do
next based on what it has learned. Larger tool surface, deeper call chains,
longer time horizons. This is the most powerful single-agent tier — and the one
where most failed agent projects live. The library's job here is to push back
hard: an autonomous loop should be the conclusion you're forced to, not the
starting point.

## When it works

- Open-ended research or investigation where the next step genuinely depends on what the previous step found, and no fixed sequence could be written in advance.
- Code generation with iteration: write, run, read the error, fix, repeat until tests pass.
- Long-horizon tasks with real intermediate decision points (*e.g., debugging across an unfamiliar code base, where which file to read next is unknowable up front*).
- Tasks where the *space* of valid action sequences is large and branchy, and a human would also work iteratively rather than from a script.
- The team can articulate what success looks like and can evaluate the agent's autonomous decisions after the fact.

## When it doesn't

- A shorter, fixed `chained_calls` pipeline would be more reliable, cheaper, and far easier to evaluate — most "agent" tasks are really fixed workflows.
- The task can be specified as a sequence of steps in advance — if you can write the runbook, you don't need autonomous planning.
- Failures are costly or irreversible and there's no review gate — an autonomous loop can take many wrong actions before anyone notices.
- You can't define or measure what a "good" autonomous decision is, so you can't tell whether the agent is working or just looking busy.
- Latency and cost budgets are tight — planning loops are the most expensive and slowest tier by a wide margin.

## Over-engineering signs

- The task can be specified as a sequence in advance — *if you can write it as a numbered runbook, build a `chained_calls` pipeline, not an autonomous agent.*
- The team can't articulate what success looks like for the agent's autonomous decisions, so there's no way to evaluate or improve it.
- Shorter, well-prompted chains already succeed in testing, but an agent loop was chosen because it sounded more capable.
- The "agent" runs the same handful of steps in nearly the same order every time — that's a chain wearing an agent costume.
- Token spend and wall-clock time exploded with no measured quality gain over a `tool_agent` or chain on the same inputs.
- "Autonomy" is being added for demo appeal, not because any real input requires run-time replanning.

## Under-engineering signs

This tier is far more often over-reached than under-reached, so this list is
deliberately short.

- A fixed chain keeps breaking because the real task genuinely needs run-time replanning — the inputs branch in ways no static sequence covers.
- The team is hand-driving an iterative loop (run, read error, paste back, retry) that the agent could close autonomously, and the manual loop is the bottleneck.
- Each task instance needs a different, unpredictable sequence of tool calls that can't be enumerated ahead of time.

## References

- Anthropic, "Building Effective Agents" — explicitly cautions that autonomous agents trade reliability and cost for flexibility, and should be used only when that flexibility is required.
- Yao et al. (2022), "ReAct" — the interleaved reason-and-act loop that underpins planning agents; useful for understanding both the capability and its failure modes.
