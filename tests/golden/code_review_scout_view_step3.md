**Existing self-description**
_How the project describes itself, verbatim._
- text: A Dash app for planning. [README.md]

**Existing project type**
web app

**Existing architecture**
_The existing pattern. Extend it rather than restructure it unless the vision says otherwise._
- pattern: monolith
- summary: one Flask process

**Existing ai capabilities**
- **summariser** — kind: llm; description: summarises threads; location: src/ai.py
- **nameless-kind**
- raw

**Existing API surface**
_The existing routes and methods. Extend rather than parallel-invent._
- **/api/plan** — protocol: HTTP; handler: plan_view; summary: creates a plan
- protocol: gRPC
- raw

**Existing protocols implemented**
_Industry standards already wired in. Treat them as constraints when proposing changes._
- **MCP** — version: 2025-06; location: src/mcp
- **A2A**
- plain text

**Existing frameworks**
_Authoritative. Already in use; a swap is a migration, not a choice._
- Dash

**Existing dependencies**
_Authoritative. Already declared; prefer them over a parallel library for the same purpose._
- **dash** — purpose: UI [pyproject.toml]
- **litellm**
- requests

**Existing incomplete or dead code**
- old_view() is unused