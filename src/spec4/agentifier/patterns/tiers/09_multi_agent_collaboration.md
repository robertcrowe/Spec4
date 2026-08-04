---
name: multi_agent_collaboration
category: tier
library_version: "1.0.0"
last_reviewed: "2026-05-30"
tier_order: 9
cost_range_usd: "$0.20–$10.00+"
latency_range_seconds: "30–1800+"
required_infrastructure:
  - "agent_message_bus"
  - "protocol_runtime"
references:
  - "A2A Project — Agent2Agent Protocol (https://github.com/a2aproject/A2A)"
  - "Anthropic — Building Effective Agents (https://www.anthropic.com/engineering/building-effective-agents)"
---

## Description

Peer agents interacting *as agents* — potentially across trust boundaries,
frameworks, vendors, or organizations. Unlike `orchestrated_subagents`, there is
no single owner who controls all the agents; they are autonomous parties that
discover, negotiate, and exchange work over a protocol such as A2A. This is the
narrowest, most expensive, and most over-reached tier in the ladder. It is
justified by *necessity* — agents that genuinely cannot live in one codebase —
almost never by elegance.

## When it works

- Heterogeneous agents that cannot be merged because they belong to different vendors, teams, or organizations and no one party controls them all.
- Negotiation or marketplace dynamics where agents represent different principals with different interests (*e.g., a buyer agent and a seller agent settling terms*).
- Cases where opacity across an organizational boundary is itself a feature — neither side can or should see the other's internals.
- Cross-framework or cross-vendor interop where a standard protocol (A2A) is the only way the agents can talk at all.
- Ecosystems where agents are independently deployed and versioned and must discover each other at run time.

## When it doesn't

- All the agents could live in the same codebase under one owner — *use `orchestrated_subagents`; you don't need a cross-boundary protocol for in-house components.*
- A deterministic orchestrator (or a single coordinator agent) would route the work fine — you're adding peer-to-peer autonomy that nothing requires.
- Multi-agent is being chosen for architectural elegance, novelty, or demo appeal rather than a real trust/ownership boundary.
- You need tight reliability and easy evaluation — distributed autonomous peers are the hardest possible thing to test and debug.
- The "collaboration" is really one agent calling another it fully controls — that's just orchestration with extra network hops.

## Over-engineering signs

- The agents all ship in one repo, deploy together, and are owned by one team — *there is no boundary to cross; collapse them into `orchestrated_subagents`.*
- A peer-to-peer protocol was introduced where a function call or in-process coordinator would do, multiplying network, serialization, and failure modes for nothing.
- "Multi-agent" was chosen because it sounded state-of-the-art, not because any agent is owned by a different party.
- Each agent is a thin wrapper the team fully controls, so the autonomy and negotiation machinery is pure overhead.
- Evaluation and debugging became intractable (non-deterministic cross-agent dialogues) with no capability that a simpler tier lacked.

## Under-engineering signs

Under-engineering this tier is rarely the problem — the common failure is
reaching *up* to it, not stopping short. The genuine cases are narrow:

- Independently owned agents from different organizations are being glued together with brittle point-to-point hacks where a standard protocol (A2A) would give them real interop.
- A growing partner ecosystem needs agents to discover and negotiate with each other at run time, and the current design hard-codes every counterpart.

## References

- A2A Project, "Agent2Agent Protocol" — the open protocol purpose-built for cross-vendor, cross-organization agent interoperability; the canonical reference for when this tier is real.
- Anthropic, "Building Effective Agents" — the recurring theme that complexity must be earned; this tier is where that discipline matters most.
