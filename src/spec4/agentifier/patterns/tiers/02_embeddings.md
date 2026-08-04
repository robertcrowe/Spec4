---
name: embeddings
category: tier
library_version: "1.0.0"
last_reviewed: "2026-05-30"
tier_order: 2
cost_range_usd: "$0.00001–$0.001 per item embedded"
latency_range_seconds: "0.05–0.5"
required_infrastructure:
  - "embedding_pipeline"
  - "vector_index"
references:
  - "OpenAI — Embeddings guide (https://platform.openai.com/docs/guides/embeddings)"
  - "Nils Reimers — Sentence-BERT / Sentence Transformers (https://www.sbert.net/)"
---

## Description

Semantic operations without generation: turn text (or images, audio) into
vectors and operate on the vectors — nearest-neighbour search, clustering,
deduplication, similarity scoring, topic routing. No tokens are generated; there
is no "answer" to read, only ranked or grouped items. Often paired with a higher
tier (it is the retrieval half of RAG), but it stands alone whenever semantic
search or grouping *is* the feature.

## When it works

- Semantic search where users find items by meaning rather than exact keywords (*e.g., "docs about login problems" surfacing a page titled "Authentication troubleshooting"*).
- Clustering or deduplication of near-duplicate records, tickets, or documents that differ in wording.
- Routing/triage by topic: embed the input, route to the nearest labelled centroid, no generation needed.
- Recommendation and "more like this" over a catalogue.
- Similarity scoring as a ranking signal feeding deterministic downstream logic.
- Fuzzy matching where exact-match keys fail (synonyms, paraphrases, multilingual).

## When it doesn't

- The feature needs *generated* output — an explanation, summary, rewrite, or answer. Embeddings rank and group; they do not write. Add `single_call` or `rag`.
- Exact-match or boolean keyword search already satisfies users (product SKUs, error codes, tag filters).
- The corpus is tiny (a few dozen items) and a linear scan with simple string matching is simpler and good enough.
- You need to explain *why* two things are similar — a vector distance is not an explanation.

## Over-engineering signs

- A vector database was stood up for a corpus of 200 rows where `WHERE category = ?` or trigram search answers every real query.
- Embedding-based search added where users actually search by exact identifier (order number, SKU) — *they want a lookup, not semantics.*
- A heavyweight embedding model and ANN index introduced before measuring whether keyword search (BM25) meets the quality bar; classical IR is a strong, cheap baseline.
- Re-embedding the entire corpus on every request instead of indexing once and querying.

## Under-engineering signs

- Keyword search is silently failing on synonyms and paraphrases and users complain they "can't find anything," but the team keeps adding stop-word and stemming hacks instead of semantic search.
- Manual tagging/categorisation of a growing corpus that semantic clustering could bootstrap.
- Deduplication done by exact-string match while near-duplicates (whitespace, casing, reworded) pile up unmerged.
- The product needs "find similar" and the team is hand-maintaining a related-items table.

## References

- OpenAI Embeddings guide — canonical reference for using embeddings for search, clustering, and recommendations.
- Sentence-Transformers (Reimers & Gurevych) — practical semantic search and similarity without a generative model; useful baseline framing for when embeddings alone suffice.
