---
name: single_call
category: tier
library_version: "1.0.0"
last_reviewed: "2026-05-30"
tier_order: 3
cost_range_usd: "$0.001–$0.05"
latency_range_seconds: "1–5"
required_infrastructure: []
references:
  - "Anthropic — Building Effective Agents (https://www.anthropic.com/engineering/building-effective-agents)"
  - "OpenAI — Structured Outputs (https://platform.openai.com/docs/guides/structured-outputs)"
---

## Description

A single LLM invocation that takes input and produces output. No retrieval, no
tool use, no multi-step reasoning. Includes structured-output cases
(classification, extraction, structured generation) and free-form output
(summaries, drafts, single-turn responses). This is the workhorse tier and the
right answer for a large fraction of "add AI here" features. The whole shape is:
prompt in, completion out.

## When it works

- Input is bounded — a few thousand tokens at most, with a predictable shape.
- Output is bounded — a category, a short summary, a structured extraction, a draft.
- The task is "transform input into output" rather than "decide and act in the world."
- Failure is recoverable: the user can regenerate, edit, or fall back to manual handling.
- Latency budget is single-digit seconds and one round trip is acceptable.
- Classification into a small fixed set of categories with bounded input.
- Extraction of structured data from a single document (invoice fields, entities, a JSON record).
- Summarisation of one document, or draft generation the user will review and edit.

## When it doesn't

- The model needs facts it wasn't trained on — customer data, internal docs, post-cutoff events. Consider `rag`.
- The task requires acting on the world (sending a message, updating a record, querying a live system). Consider `tool_agent`.
- Output quality depends on multiple rounds of reasoning or self-correction. Consider `chained_calls`, `reflection`, or `planning_agent`.
- Input is unbounded — an entire corpus or a long, growing conversation history. Consider `rag`.
- The output must be verified against a source of truth the model can't see. Consider `rag` or `tool_agent`.

## Over-engineering signs

- An "agent" was proposed for what is really classification into five categories — *no tools, no planning, just a labelled prompt.*
- RAG was proposed but the knowledge fits in the system prompt (under ~5,000 tokens, stable) — *put the glossary in the prompt, skip the vector store.*
- Tool use was proposed but the "tool" is one deterministic operation that could be inlined in the prompt or done after the call.
- Multi-step reasoning was proposed for a task the model gets right in one shot during testing.
- Chained calls were proposed where a single structured-output prompt consolidates the whole transform.

## Under-engineering signs

- Hallucinations on specific facts the model couldn't know — the feature needs grounding (`rag`) or tool access.
- Users are dissatisfied because the model can't see their data, current state, or recent events — needs `rag` or `tool_agent`.
- The right answer depends on doing two or three distinct things in sequence and the single prompt conflates or drops steps — consider `chained_calls`.
- Quality varies wildly with phrasing in ways that few-shot examples don't fix, suggesting the task is genuinely multi-step.

## References

- Anthropic, "Building Effective Agents" — start with the simplest thing that works; a single well-prompted call beats an agent for most bounded tasks.
- OpenAI Structured Outputs — canonical reference for schema-constrained single-call generation (classification, extraction).
