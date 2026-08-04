---
name: tool_agent
category: tier
library_version: "1.0.0"
last_reviewed: "2026-05-30"
tier_order: 5
cost_range_usd: "$0.005–$0.15"
latency_range_seconds: "2–15"
required_infrastructure:
  - "tool_execution_harness"
references:
  - "Anthropic — Building Effective Agents (https://www.anthropic.com/engineering/building-effective-agents)"
  - "Anthropic — Tool use (https://docs.claude.com/en/docs/build-with-claude/tool-use)"
---

## Description

A single LLM call (or short chain) with access to a small, fixed set of tools.
The model can call tools to fetch data or take bounded actions, but the overall
shape stays simple: one user turn → maybe a few tool calls → a response. The
model decides *whether* and *which* tool to call from a handful of well-defined
options; it is not planning a long autonomous campaign. Most of Spec4's own
agents fit here.

## When it works

- User-in-the-loop conversational flows that occasionally need a lookup or a bounded action (*e.g., a chat assistant that can search the web or check an order status*).
- A small, fixed tool surface — typically a handful of well-described tools — where the right one is usually obvious from the request.
- Actions are bounded and individually safe or confirmable (read a record, post a message, run a search).
- The interaction is mostly one round trip with an optional tool detour, not a deep multi-step workflow.
- You want the model to fetch *just-in-time* context rather than pre-retrieving everything (a lighter alternative to full RAG plumbing).

## When it doesn't

- The right *sequence* of tool calls is unpredictable in advance and depends heavily on intermediate results — that's `planning_agent` territory.
- The workflow is deep and multi-stage with many decision points and long time horizons.
- The tool surface is large and open-ended (dozens of tools, ambiguous selection), so the model frequently picks wrong.
- The sequence is actually fixed and known — then a `chained_calls` pipeline is more reliable and testable than letting the model choose each step.
- Any single tool action is high-stakes and irreversible without review — wrap it with `human_in_the_loop`.

## Over-engineering signs

- A `planning_agent` was reached for when a tool_agent with three well-chosen tools handles every real case — *the task didn't need autonomous replanning.*
- Tools were added for operations the model never actually needs at call time, or that could be done deterministically before/after the call.
- A tool wraps a single deterministic transform (date math, a formatter) that belongs in plain code, not behind a model decision.
- An open-ended agent loop was built where the realistic interaction is one lookup then an answer.
- The same fixed two-step flow is implemented as a tool-calling loop instead of a straightforward `chained_calls` sequence.

## Under-engineering signs

- A `single_call` feature keeps failing because it needs live data or must take an action it has no way to perform — give it a tool.
- The team simulates tool use by pasting API results into the prompt by hand each turn.
- Users want the assistant to *do* things (create the ticket, send the email), not just describe how, but the feature is read-only.
- The realistic flow genuinely needs adaptive multi-step tool use with replanning, and a fixed chain keeps breaking — consider `planning_agent`.

## References

- Anthropic, "Building Effective Agents" — distinguishes simple tool-augmented calls from full autonomous agents and recommends the former wherever it suffices.
- Anthropic, "Tool use" documentation — canonical reference for defining and invoking a bounded tool set.
