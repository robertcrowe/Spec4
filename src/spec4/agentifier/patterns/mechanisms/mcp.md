---
name: mcp
category: mechanism
library_version: "1.0.0"
last_reviewed: "2026-05-30"
references:
  - "Model Context Protocol — Specification and docs (https://modelcontextprotocol.io/)"
  - "Anthropic — Introducing the Model Context Protocol (https://www.anthropic.com/news/model-context-protocol)"
---

## Description

Whether to use the Model Context Protocol (MCP) for tool and data access. MCP
bundles two genuinely distinct decisions that must be reasoned about separately:
**consumption** — for a capability you *need*, should you reuse an existing MCP
server rather than build an integration? — and **exposure** — for a capability
you *build*, should you expose it over MCP or just call it directly? Conflating
the two is the most common source of bad MCP decisions.

## When it works

- **Consumption:** a maintained MCP server already exists for the capability you need (web search, GitHub, filesystem, browser automation, a database) — reuse it off the shelf rather than reimplementing the integration, *regardless of how many agents will use it*.
- **Exposure:** your own capability will have multiple consumers (several agents, several teams, external partners) and a standard protocol saves everyone writing a bespoke client.
- Interop matters — you want any MCP-aware client (Claude Desktop, IDEs, other agents) to use your capability without custom glue.
- Your org has standardized on MCP and consistency across tools has real operational value.
- You want tools to be discoverable and hot-swappable at run time rather than hard-wired into one agent.

## When it doesn't

- **Exposure:** the capability has exactly one consumer living in the same codebase — a direct function call is simpler, faster, and easier to test than running a protocol server.
- The "tool" is a pure in-process function with no external resource — wrapping it in MCP adds a transport, a server lifecycle, and serialization for nothing.
- Latency is critical and the extra process hop / serialization round trip is not worth it for a single local call.
- The capability is a throwaway prototype where standing up a server slows you down.

## Over-engineering signs

- A custom MCP server was built for a capability a maintained third-party server already provides — *don't rebuild web search or GitHub access; reuse the existing server.*
- A single-consumer function in one codebase was wrapped in MCP "for consistency" when a direct call does the same job with none of the protocol overhead.
- An MCP server, transport, and schema were stood up for a prototype with one caller and no interop requirement.
- Every internal helper got an MCP wrapper, turning ordinary function calls into network/IPC hops.

## Under-engineering signs

- The team is hand-rolling a custom integration to a backend that an existing MCP server already exposes — *reach for the off-the-shelf server instead.*
- Several features independently hand-roll their own tool access to the same backend, duplicating auth, retry, and schema logic that one MCP server would centralize.
- A capability that clearly has multiple present and future consumers is buried as a private function, forcing each new consumer to re-integrate from scratch.
- Tools are hard-wired into one agent when the org has standardized on MCP and other agents will need the same capability.

## References

- Model Context Protocol — specification and server/client docs (https://modelcontextprotocol.io/); canonical reference for both consuming and exposing capabilities over MCP.
- Anthropic, "Introducing the Model Context Protocol" — the rationale for a standard tool/data protocol and when reuse-over-build applies.
