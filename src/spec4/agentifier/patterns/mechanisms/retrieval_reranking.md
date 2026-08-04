---
name: retrieval_reranking
category: mechanism
library_version: "1.0.0"
last_reviewed: "2026-05-30"
references:
  - "Nogueira & Cho — Passage Re-ranking with BERT (https://arxiv.org/abs/1901.04085)"
  - "Cohere — Rerank documentation (https://docs.cohere.com/docs/rerank-overview)"
---

## Description

Within a RAG setup, applying a second, more expensive scorer (a cross-encoder or
reranker model) to the candidates returned by first-stage retrieval, to reorder
them by true relevance before they go into the prompt. First-stage retrieval
(embedding similarity, BM25) is cheap and recall-oriented; it casts a wide net.
Reranking is precision-oriented; it reads each query-candidate pair more
carefully to pick the best few. The mechanism only helps when first-stage recall
is good but its ordering is not.

## When it works

- First-stage retrieval returns many plausible candidates (good recall) but the *top* results are often not the most relevant (poor precision at k).
- The reranker measurably lifts answer quality on your data, shown by evaluation — not assumed.
- You can over-retrieve cheaply (top 50–100) and afford a more expensive scorer over that shortlist to pick the final top 3–5.
- Relevance is subtle enough that bi-encoder embedding distance misranks it but a cross-encoder reading the pair catches it.
- The quality gain justifies the added per-query latency and cost of the rerank step.

## When it doesn't

- First-stage retrieval is already accurate enough — the right documents are reliably in the top few, so reranking reorders a list that was already correct.
- The reranker's latency and cost exceed the quality it adds (small corpus, easy queries).
- The real bottleneck is recall or chunking — the right document isn't being retrieved at all — and no amount of reranking can surface what retrieval never fetched.
- The candidate set is tiny (you retrieve 3 and use 3), leaving nothing to rerank.

## Over-engineering signs

- Reranking was added before measuring whether base retrieval is actually the bottleneck — *instrument retrieval precision first; if the right doc is already at rank 1, reranking buys nothing.*
- A reranker is reordering a candidate list that's already correct, adding latency for no measurable quality change.
- The reranking stage was copied from a reference architecture as a default, without evidence it helps on this corpus.
- An expensive cross-encoder reranks hundreds of candidates per query when the answer only ever needs the top 3 and recall is already poor.

## Under-engineering signs

- RAG answers are weak because the most relevant chunk is retrieved but buried at rank 8 and never makes it into the prompt — a reranker would promote it.
- The team keeps enlarging top-k (stuffing more context in) to compensate for poor ordering, bloating cost and diluting the prompt, when reranking the shortlist would be cheaper and better.
- Embedding similarity is demonstrably misranking near-duplicate-but-wrong candidates above the correct one, and there's no second-stage scorer to fix it.

## References

- Nogueira & Cho (2019), "Passage Re-ranking with BERT" — the canonical demonstration that a cross-encoder reranker over first-stage candidates improves retrieval precision.
- Cohere Rerank documentation — practical reference for adding a reranking stage to a retrieval pipeline, including when the precision gain is worth the cost.
