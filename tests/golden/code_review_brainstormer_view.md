**Existing self-description**
_How the project describes itself. The vision's identity starts here — do not rename the project or re-derive what it is for._
- text: A Dash app for planning. [README.md]

**Existing project type**
_Authoritative._
web app

**Existing architecture**
_The existing shape. New features fit into it unless the user asks for a restructure._
- pattern: monolith
- summary: one Flask process

**Existing ui summary**
_What users already see. New features extend this surface._
- has ui: yes
- kind: SPA
- framework: Dash
- styling: CSS

**Existing API surface**
_What the product already does, route by route — the existing feature inventory. Never propose as new a capability that is already here._
- **/api/plan** — protocol: HTTP; handler: plan_view; summary: creates a plan
- protocol: gRPC
- raw

**Existing ai capabilities**
_AI already in the codebase. These are existing features, not candidates; a new AI feature should say how it relates to them._
- **summariser** — kind: llm; description: summarises threads; location: src/ai.py
- **nameless-kind**
- raw

**Existing protocols implemented**
_Standards already implemented. Features that touch them stay compatible._
- **MCP** — version: 2025-06; location: src/mcp
- **A2A**
- plain text

**Existing incomplete or dead code**
_Half-built or abandoned areas. Before planning a feature that touches one, ask whether to finish it, remove it or leave it._
- old_view() is unused

**Existing change risks**
_What is fragile. Respect these when asking about future features._
- **app.py** — risk: import order is load-bearing; mitigation hint: keep the noqa
- a bare risk