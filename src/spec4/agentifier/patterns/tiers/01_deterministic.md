---
name: deterministic
category: tier
library_version: "1.0.0"
last_reviewed: "2026-05-30"
tier_order: 1
cost_range_usd: "$0 (no model inference)"
latency_range_seconds: "<0.01"
required_infrastructure: []
references:
  - "Anthropic — Building Effective Agents (https://www.anthropic.com/engineering/building-effective-agents)"
  - "Martin Fowler — Rules Engine (https://martinfowler.com/bliki/RulesEngine.html)"
---

## Description

Not AI at all — rule-based logic, lookup tables, regular expressions, finite
state machines, and classical algorithms. This tier exists so Agentifier can
make a legitimate "don't use a model here" recommendation. If the decision space
is enumerable and the rules are stable, deterministic code is cheaper, faster,
fully testable, and never hallucinates. It is the default the other eight tiers
have to earn their way past.

## When it works

- The decision space is a small fixed set of categories with clear, stated rules (*e.g., routing a support ticket by the product field on the form*).
- The transformation is mechanical: parsing, formatting, unit conversion, date math, sorting, deduplication by exact key.
- Inputs are structured and validated upstream (form fields, API payloads, enum values) rather than free-form natural language.
- Correctness must be 100% and auditable — billing, tax, access control, compliance gates.
- The logic must run in microseconds or offline with no network call.
- A lookup table or `if/elif` ladder would fit on one screen and rarely changes.

## When it doesn't

- The input is unstructured natural language whose meaning, not its surface form, drives the decision (*e.g., classifying the sentiment of a free-text review*).
- The rules would need hundreds of hand-maintained branches to cover the real distribution of inputs, and new edge cases arrive faster than anyone can encode them.
- The mapping is fuzzy or example-defined ("things like this go here") rather than crisply specifiable.
- You find yourself writing regexes to extract meaning from prose — that is usually a sign the problem is semantic, not syntactic.

## Over-engineering signs

- An LLM call was proposed for what is really classification into five fixed categories with documented rules — *the rules already exist in the spec; encode them.*
- A model is being used to parse a structured format (JSON, CSV, a fixed log line) that a parser handles deterministically and faster.
- "We'll use AI to be future-proof" with no current input that the rules can't handle — speculative generality.
- A model is invoked to do arithmetic, date math, or string formatting that a library does exactly and for free.
- The team is paying per-token latency and cost for a decision that a hash-map lookup resolves in nanoseconds.

## Under-engineering signs

This section captures the *opposite* failure for this tier: clinging to rules
where AI would genuinely help.

- The rules engine has grown to hundreds of brittle branches and a backlog of "unhandled input" bugs — the distribution is too long-tailed for hand-coded rules.
- Inputs are free-form text and the regex/keyword approach silently misclassifies paraphrases, typos, and synonyms (*e.g., keyword "cancel" misses "I'd like to close my account"*).
- Maintainers spend more time patching rules for new edge cases than the feature is worth, and accuracy still plateaus below requirements.
- The task is "understand what the user meant" rather than "match a known pattern" — semantics, not syntax. Consider `single_call` or `embeddings`.

## References

- Anthropic, "Building Effective Agents" — repeatedly stresses finding the simplest solution possible and only increasing complexity when it demonstrably improves outcomes.
- Martin Fowler, "Rules Engine" — on when explicit rule logic is appropriate and when it becomes an unmaintainable tangle.
