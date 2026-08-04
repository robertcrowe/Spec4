---
name: reflection
category: mechanism
library_version: "1.0.0"
last_reviewed: "2026-05-30"
references:
  - "Madaan et al. — Self-Refine: Iterative Refinement with Self-Feedback (https://arxiv.org/abs/2303.17651)"
  - "Shinn et al. — Reflexion: Language Agents with Verbal Reinforcement Learning (https://arxiv.org/abs/2303.11366)"
---

## Description

Generate, critique, regenerate — the same task and the same agent looping over
its own output to improve it. A first draft is produced, then evaluated (by the
model itself or against a checker), and the feedback drives a revision. The loop
repeats until a termination condition is met. Reflection trades extra calls and
latency for quality, and only earns its place when the critique step measurably
moves the output and the loop reliably terminates.

## When it works

- Output quality measurably improves when the model critiques and revises, demonstrated in testing — not assumed (*e.g., code that fails a test, gets the error fed back, and is fixed*).
- There is an external signal to reflect against: a test suite, a linter, a validator, a rubric — so the critique is grounded rather than the model marking its own homework.
- Termination conditions are well defined (tests pass, score threshold met, max iterations) so the loop can't run forever.
- The cost and latency of extra iterations are acceptable for the quality gained.
- The task has a clear notion of "better" that the critique can target.

## When it doesn't

- A single well-prompted call already achieves the target quality — reflection then just adds latency and cost.
- There's no objective signal and the model critiques its own output without grounding, so iterations drift sideways rather than improving (self-praise, not self-correction).
- The loop fails to converge — each revision introduces new problems and the output oscillates.
- Latency budgets don't permit multiple round trips (interactive, sub-second-feel features).
- The "critique" can't articulate a concrete, actionable defect, so the rewrite is random.

## Over-engineering signs

- Reflection was added by default rather than because testing showed it helps — *measure single-call quality first; only add the loop if it closes a real gap.*
- The termination condition is poorly defined or missing, risking infinite or runaway loops and unbounded cost.
- A second "critic" pass was bolted on where the first output was already correct in the vast majority of cases.
- Iterations keep running past the point of improvement because there's no convergence check, just a fixed high iteration count.
- The reflection has no external signal to anchor on, so it's the model rubber-stamping itself at 2× the cost.

## Under-engineering signs

- Output quality is just below the bar and a single grounded critique-and-revise pass would clear it, but the team ships the first draft and asks users to fix it.
- A code-generation or extraction feature has access to a validator (tests, schema) but never feeds failures back for a retry, so recoverable errors reach the user.
- Quality is inconsistent and a cheap "check then fix once" loop would catch the bad cases the first draft misses.

## References

- Madaan et al. (2023), "Self-Refine" — iterative refinement with self-feedback; evidence for when reflection improves output and when gains plateau.
- Shinn et al. (2023), "Reflexion" — reflection grounded in environment feedback; underscores that the loop needs a real signal and a termination condition.
