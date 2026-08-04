---
name: parallel_fanout
category: mechanism
library_version: "1.0.0"
last_reviewed: "2026-05-30"
references:
  - "Anthropic — Building Effective Agents (https://www.anthropic.com/engineering/building-effective-agents)"
  - "Anthropic — How we built our multi-agent research system (https://www.anthropic.com/engineering/built-multi-agent-research-system)"
---

## Description

Decompose a task into independent subtasks, execute them concurrently, and
aggregate the results. The defining property is *independence*: each branch can
run without waiting on any other. Fan-out buys wall-clock latency (work that
would be sequential happens at once) and, sometimes, quality (each branch gets a
focused prompt). It pays off only when the decomposition is clean and the
aggregation is cheaper than the work it combines.

## When it works

- The task splits into genuinely independent subtasks with a clear decomposition (*e.g., review 20 files for the same issue — one branch per file*).
- Latency matters and the work parallelizes cleanly, so N branches finish in roughly the time of the slowest one instead of the sum.
- Aggregation is straightforward — concatenation, voting, max/min, a short merge — and cheaper than the subtasks themselves.
- Each subtask benefits from a focused prompt and isolated context rather than one mega-prompt juggling everything.
- You want multiple independent samples/perspectives and then a deterministic or lightweight merge (e.g., majority vote).

## When it doesn't

- The subtasks have dependencies — B needs A's output. That's a `chained_calls` sequence, not a fan-out.
- Aggregating the branch results is as hard as (or harder than) the original task — you've moved the difficulty, not removed it.
- A single well-prompted call produces comparable results, making the fan-out pure overhead and cost multiplication.
- The branches need to share state or coordinate mid-flight — independence doesn't hold, so parallelism breaks down.
- Rate limits or cost ceilings make N concurrent calls impractical for the latency you'd save.

## Over-engineering signs

- Work was fanned out "for diversity of perspective" when one well-prompted call covers the same ground — *the perspectives mostly agreed and the merge threw away the difference.*
- Elaborate aggregation logic (weighting, tie-breaking, meta-summarization) was built for only two parallel branches.
- A fan-out was added where the subtasks actually depend on each other and now race or produce inconsistent partial results.
- The decomposition is artificial — the task was split just to look parallel, and each branch re-derives the same shared context.

## Under-engineering signs

- A batch of obviously independent items is processed strictly sequentially and the latency is a user-visible problem — fan them out.
- A single call is being asked to handle many independent inputs at once and quality degrades as the list grows; per-item branches would each stay focused.
- The team manually runs the same prompt over a list one at a time when a concurrent map would be trivial and far faster.

## References

- Anthropic, "Building Effective Agents" — the parallelization (sectioning and voting) workflow and when independence makes it worthwhile.
- Anthropic, "How we built our multi-agent research system" — practical notes on fanning subtasks out to parallel workers and the aggregation cost that comes with it.
