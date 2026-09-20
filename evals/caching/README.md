# Cache probe

Read-only look at how much of each agent's prompt was served from the provider's
prompt cache, taken from recorded `.spec4/v*/usage.json` files. It makes no LLM
call and writes nothing.

    uv run python evals/caching/cache_probe.py <project_dir> [<project_dir> ...] [--json]
    uv run python evals/caching/cache_probe.py --compare <before_dir> <after_dir> [--json]
    uv run pytest -q evals/caching

It reads the per-call `history` records (the shape `save_usage` writes and
`llm._record_usage` builds), not the rollups. Rows are grouped by each record's
own `agent` field, so sub-agents (`scout`, `tier_analyst`, ...) that `save_usage`
folds under `agentifier` report as separate rows. The file's rollup key is used
only for a record with no usable `agent`. The `parent` column names the rollup
key when it differs from the agent, and rows are ordered with sub-agents under
their parent. Gap statistics are per raw agent.

## Columns

Per agent and in total, for each usage file: calls; calls missing usage; sum of
`prompt_tokens`; cache read; cache creation (`cache_creation_input_tokens`);
calls with any read > 0; read ratio; `computed_cost_usd`; distinct
(model, provider) pairs. A figure no call reported prints `-`, never 0.

Cache read is `cache_read_input_tokens`, else `cached_tokens`. Note that
`summarize_usage` tries them in the opposite order; for a record carrying both
they mirror the same figure, so the totals should agree.

`both_differ` counts records carrying both `cache_read_input_tokens` and
`cached_tokens` with unequal values (`-` when no record carried both). Read
precedence stays read-first. A non-zero count means the two fields are not
interchangeable for that provider.

Timing columns: `min_gap_s`, and `clock_skew`, the number of calls whose
`timestamp` falls before the previous call's `timestamp + duration_s`, taken in
start order. (`-` with fewer than two timestamped calls.) Only the immediately
preceding call is checked.

`clock_skew` cannot detect concurrency, and was misread as doing so before it
was renamed. It compares a wall-clock `timestamp` against a duration measured
on the monotonic clock: the two are different clocks, so their sum is not a
wall-clock instant and a later call's `timestamp` falling below it says nothing
about overlap. The pipeline is sequential — no two LLM calls are ever in flight
at once — so a non-zero count is a timing artifact, not a fan-out signal. It has
recurred on `tier_analyst` call 1→2 in three of five draws; the cause is not
established.

Gap columns (per agent only) give the median and max seconds between
consecutive calls and the count of gaps over 300 s, the evidence for the cache
TTL decision. Gaps are start-to-start from each record's `timestamp`, so they
include the earlier call's own duration; the idle time is somewhat shorter.
Gaps are computed within one usage file, never across rounds.

`--compare` pools each agent across every round in a directory and prints
before, after and delta for cache read, cache creation and cost.

## What `prompt_tokens` includes

Settled, from the litellm 1.101.0 source and confirmed by five measured draws:
`usage.prompt_tokens` **includes** both cache-read and cache-creation tokens for
Anthropic, Bedrock, Gemini and OpenAI. Cached tokens are a subset of input
tokens, not an addition to them, so nothing here is double-counted and nothing
needs re-normalizing; `_computed_cost` already prices reads and writes at their
own rates. Read ratio (cache read / prompt tokens) is a valid hit rate.

On Anthropic, `cached_tokens` and `cache_read_input_tokens` always carry the
same value, which is why `both_differ` reads `0` there rather than `-`.

## Reading a draw

`cache_creation` on an agent's first call and `cache_read` on its later ones is
the healthy shape: the first call writes the prefix, the rest are served from
it.

Nothing at all on a chat agent is not necessarily a failure. Models with a
4,096-token minimum cacheable prefix (Haiku 4.5, Opus 4.5/4.6) cache nothing
until the whole prompt up to the breakpoint clears that floor, so a short chat
agent shows `-` in both columns until its prompt grows past it.

A call with `cache_read` 0 and a full-prefix `cache_creation`, immediately after
a gap counted in `gaps_over_ttl`, is the 5-minute cache lifetime expiring, not a
bug. A Brainstormer turn after a 400–500 s pause showed exactly this, with reads
resuming on the next turn.
