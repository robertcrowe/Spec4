---
name: orchestrated_subagents
category: tier
library_version: "1.0.0"
last_reviewed: "2026-05-30"
tier_order: 8
cost_range_usd: "$0.10–$5.00+"
latency_range_seconds: "15–600+"
required_infrastructure:
  - "subagent_orchestration_runtime"
references:
  - "Anthropic — How we built our multi-agent research system (https://www.anthropic.com/engineering/built-multi-agent-research-system)"
  - "Anthropic — Building Effective Agents (https://www.anthropic.com/engineering/building-effective-agents)"
---

## Description

One user-facing entry point that internally coordinates multiple specialist
sub-agents. The sub-agents are opaque to the user; the coordinator owns the
user-facing voice and decides which specialist handles what, then synthesises
their outputs. Communication is internal (in-process calls, function calls, or
A2A within one system). Spec4's own Agentifier is in this tier. The bar to clear
versus a single `planning_agent` or `chained_calls` pipeline is high: the split
has to buy something a single well-prompted agent can't.

## When it works

- The work spans distinct cognitive modes that would interfere if combined into one prompt (*e.g., a creative ideation persona and a skeptical risk-assessment persona — each degrades when forced to also be the other*).
- A coordinator persona owns the user-facing voice while specialists work behind it with bounded inputs and outputs.
- Each sub-agent's prompt is meaningfully shorter and more focused than a single combined prompt would be, improving reliability per sub-agent.
- Sub-tasks can run in parallel and the latency win is real (see `parallel_fanout`).
- Specialists have genuinely different tool sets or knowledge, so one combined agent would carry irrelevant tools and context for every call.

## When it doesn't

- The "sub-agents" are really just steps with the same persona and tools — *that's a chain, not orchestration; use `chained_calls`.*
- The orchestrator ends up re-doing the sub-agents' reasoning to check or merge it, so the split adds coordination cost without dividing the work.
- A single `planning_agent` or `tool_agent` produces equivalent output with far less plumbing and token overhead.
- The sub-agents need to see each other's full context to do their jobs, so the "opacity" you're paying for doesn't actually hold.
- The coordination logic is fixed and simple enough to be deterministic glue around a couple of calls.

## Over-engineering signs

- The system was split into sub-agents for separation-of-concerns *purity* when a single agent produces equivalent output — *architectural elegance is not a runtime requirement.*
- Each "sub-agent" shares the same persona, tools, and context and runs in fixed order — it's a `chained_calls` pipeline relabeled.
- The orchestrator's prompt is as long and complex as a monolithic agent would have been, plus N sub-agent prompts on top — net complexity went up, not down.
- Sub-agents were introduced before a single agent was tried and found wanting on real inputs.
- Token cost multiplied (coordinator + N specialists + synthesis) with no measured quality or latency gain over one agent.

## Under-engineering signs

- A single agent's prompt has become an unmanageable tangle of conflicting personas ("be creative but also rigorously skeptical but also concise"), and quality suffers because the modes interfere — split them.
- Distinct specialist tasks are being crammed into one agent that carries every tool and every instruction on every call, bloating cost and confusing tool selection.
- Parallelizable sub-tasks are run sequentially inside one agent because there's no coordinator to fan them out.

## References

- Anthropic, "How we built our multi-agent research system" — a concrete account of an orchestrator-plus-subagents design, including where the overhead is and when it pays off.
- Anthropic, "Building Effective Agents" — orchestrator-workers pattern, with the caution to adopt it only when the coordination genuinely divides the work.
