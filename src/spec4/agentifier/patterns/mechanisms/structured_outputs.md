---
name: structured_outputs
category: mechanism
library_version: "1.0.0"
last_reviewed: "2026-05-30"
references:
  - "OpenAI — Structured Outputs (https://platform.openai.com/docs/guides/structured-outputs)"
  - "Anthropic — Increase output consistency / tool use for structured data (https://docs.claude.com/en/docs/build-with-claude/tool-use)"
---

## Description

Typed or schema-constrained generation: the model's output is forced to conform
to a defined structure — a JSON Schema, a Pydantic model, an enum, a function
signature. Instead of free text the consumer gets a parseable object with known
fields and types. Structured output is the mechanism that makes LLM results safe
for downstream code to consume programmatically, and it bounds what the model
can emit, which suppresses some classes of hallucination.

## When it works

- Downstream code consumes the output programmatically and needs reliable fields and types (*e.g., extracted invoice fields written straight to a database*).
- Bounded fields (enums, fixed keys) prevent the model from inventing unexpected categories or shapes.
- You want schema-driven evaluation — assert on fields, diff against expected objects, validate automatically.
- The output is a record, classification, or set of parameters rather than prose meant for a person.
- Integration with tool/function calling, where the model must emit arguments matching a signature.

## When it doesn't

- The output is meant for a human to read and a rigid structure makes it stilted or drops nuance (explanations, narratives, conversational replies).
- The schema is changing so fast that maintaining it costs more than parsing free text would.
- The task is inherently open-ended and forcing fields truncates or distorts the real answer.
- Over-constraining causes the model to omit information that doesn't fit the schema, when that information was the point.

## Over-engineering signs

- A strict schema constrains output that no downstream code actually parses — *the result is read by a human, so the schema is ceremony.*
- Free-form prose was forced into rigid JSON fields, making the output worse for its actual (human) consumer.
- A deeply nested schema with many optional fields was defined for a response that has one meaningful value.
- Schema validation and repair loops were added where the model already returns clean, parseable output reliably.

## Under-engineering signs

- Downstream code is parsing the model's prose with regexes and string splits, breaking whenever phrasing shifts — define a schema and let the model fill it.
- Hallucinated or out-of-range categories slip through because the output is free text instead of a constrained enum.
- The same extraction is re-prompted repeatedly to "please return only JSON" instead of using the provider's structured-output / tool-calling mode.
- Programmatic consumers crash on malformed output that a schema constraint would have prevented at the source.

## References

- OpenAI Structured Outputs — canonical reference for schema-constrained generation and guaranteed-valid JSON.
- Anthropic tool-use documentation — using typed tool/function schemas to obtain structured, programmatically consumable output.
