---
name: rag
category: tier
library_version: "1.0.0"
last_reviewed: "2026-05-30"
tier_order: 4
cost_range_usd: "$0.002–$0.08"
latency_range_seconds: "1–6"
required_infrastructure:
  - "chunking_pipeline"
  - "retriever"
  - "embedding_pipeline"
  - "vector_index"
references:
  - "Lewis et al. — Retrieval-Augmented Generation for Knowledge-Intensive NLP (https://arxiv.org/abs/2005.11401)"
  - "Anthropic — Contextual Retrieval (https://www.anthropic.com/news/contextual-retrieval)"
---

## Description

A single LLM call augmented with retrieved context: fetch the most relevant
documents (usually via `embeddings` similarity, sometimes keyword/hybrid), inject
them into the prompt, and generate an answer grounded in them. RAG buys two
things a bare `single_call` can't: knowledge the model wasn't trained on, and
citations back to a source. It is `single_call` plus a retrieval step — not an
agent, not multi-step reasoning.

## When it works

- The knowledge base is too large to fit in a prompt (product docs, a wiki, a code base, a policy library).
- Knowledge changes more often than you redeploy — new docs land daily and must be answerable without retraining or prompt edits.
- Answers must cite their sources so users (or auditors) can verify them.
- Coverage is broad but each query touches only a small, retrievable slice.
- The same corpus serves many different questions (support assistant, internal Q&A).

## When it doesn't

- The knowledge is small and stable — fits in ~5,000 tokens and rarely changes. Put it in the system prompt and use `single_call`.
- The model's training already covers the domain well enough (general knowledge, common programming questions) and testing shows no factual gap.
- The task needs to *act*, not just answer from documents — querying a live API, mutating state. That's `tool_agent`.
- Answers depend on synthesising across the *whole* corpus at once (global summarisation), which top-k retrieval can't assemble.
- Retrieval quality is the real problem and no amount of generation fixes bad chunks.

## Over-engineering signs

- RAG was proposed for a 3,000-token glossary that never changes — *put it in the system prompt instead.*
- A vector database, chunker, and reranker were built before testing whether a single call with the docs pasted in already answers the questions.
- RAG added where the model's own training answers the questions correctly in testing (no measured hallucination gap).
- An elaborate multi-stage retrieval pipeline stood up for a corpus of a few dozen documents that fit comfortably in one context window.
- Retrieval added "for citations" when the source set is one short document that could just be quoted.

## Under-engineering signs

- A `single_call` feature is hallucinating on customer-specific or internal facts, and the team keeps tweaking the prompt instead of grounding it in retrieved data.
- Internal knowledge is being copy-pasted into prompts by hand and goes stale between updates.
- The system prompt has ballooned past tens of thousands of tokens trying to inline a knowledge base — that knowledge belongs in a retrieval index.
- Users need citations and the current answer can't point at a source.

## References

- Lewis et al. (2020), "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks" — the foundational RAG paper.
- Anthropic, "Contextual Retrieval" — practical guidance on improving retrieval quality, and an implicit reminder that retrieval quality, not generation, is usually the bottleneck.
