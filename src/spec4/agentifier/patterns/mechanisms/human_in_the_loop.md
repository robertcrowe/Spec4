---
name: human_in_the_loop
category: mechanism
library_version: "1.0.0"
last_reviewed: "2026-05-30"
references:
  - "Anthropic — Building Effective Agents (https://www.anthropic.com/engineering/building-effective-agents)"
  - "Google PAIR — People + AI Guidebook (https://pair.withgoogle.com/guidebook/)"
---

## Description

Confirmation, approval, or correction patterns where the agent's output is
reviewed by a human before it takes final effect. The human is a gate on the
action, not a co-author of every token. Done well, it puts review where mistakes
are costly and confidence is low. Done badly, it either floods a person with
rubber-stamp approvals they stop reading, or gates routine actions the agent
gets right every time — both of which destroy the value the gate was supposed to
add.

## When it works

- Mistakes have meaningful cost — money moves, data is deleted, a message goes to a customer, a legal/medical/safety decision is made.
- The human's review time is high-leverage: a few seconds of attention prevents an expensive error (*e.g., approving a refund above a threshold*).
- The agent's confidence varies and you can route only the low-confidence or high-impact cases to a person while auto-approving the rest.
- Actions are irreversible or hard to undo, so a checkpoint before commit is worth the latency.
- Regulatory or trust requirements demand a human decision of record.

## When it doesn't

- The volume of decisions far exceeds human review capacity, so the queue backs up and the gate becomes the bottleneck.
- The agent is reliably correct on the routine case and the human approves everything without looking — a rubber stamp adds latency and false assurance, not safety.
- Latency budgets don't permit a human in the path (real-time or high-throughput flows).
- The decision is low-stakes and fully reversible, so the cost of review exceeds the cost of an occasional wrong call you simply undo.

## Over-engineering signs

- Confirmation is required for routine, low-stakes decisions the agent gets right essentially every time — *the human clicks "approve" reflexively and adds no safety.*
- A review step was added to every action uniformly instead of routing only high-impact or low-confidence cases to a person.
- The review UI fatigues the human with so many approvals that they stop reading and approve on autopilot — the gate now provides false confidence.
- A human checkpoint sits in a high-throughput pipeline where it can't possibly keep up, throttling the whole system.

## Under-engineering signs

- The agent autonomously takes irreversible, high-cost actions (sending funds, deleting records, emailing customers) with no approval step — add a gate before commit.
- There is no confidence signal and no escalation path, so confidently-wrong outputs ship straight to production with nothing to catch them.
- All cases are auto-approved when a cheap confidence threshold could route the risky minority to a person.
- Errors that a quick human glance would have caught are reaching users because no review point exists.

## References

- Anthropic, "Building Effective Agents" — recommends human checkpoints and stop conditions, especially for higher-stakes autonomous actions.
- Google PAIR, "People + AI Guidebook" — design guidance on calibrating user trust, confidence display, and avoiding rubber-stamp review patterns.
