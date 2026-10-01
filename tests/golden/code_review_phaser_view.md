**Existing architecture**
_The existing pattern. Extend it rather than restructure it unless the vision says otherwise._
- pattern: monolith
- summary: one Flask process

**Existing commands**
_Authoritative. Use `test` to write each phase's verification criterion; `build`, `lint` and `typecheck` are the gates every phase must pass._
- build: uv build
- test: uv run pytest
- run: spec4

**Existing entrypoints**
_Authoritative. Phase 1 is an integration thread for the existing app that starts from these, not a from-scratch scaffold._
- main: src/spec4/app.py
- cli script: spec4

**Existing directory map**
_Ground every instruction in these real paths._
- **src/spec4** — role: package
- role: no path
- docs/

**Existing build system**
_Authoritative. Build and install through this tool and manifest._
- tool: uv
- manifest: pyproject.toml
- build backend: uv_build

**Existing persistence**
_The existing data layer. Phase 1's steel thread must verify the connection to every engine listed; every DB-touching phase runs migrations via the migration tool against the migrations path. Do not propose a different ORM or migration tool without explicit user approval._
- databases:
  - **SQLite** — role: cache
  - **Postgres**
  - bad
- orm: **SQLAlchemy**
- migration tool: **alembic**
- migrations path: migrations/

**Existing environment variables**
_List every `required: yes` variable in Phase 1's `tech_stack_spec.configurations` and verify it in Phase 1's verification step (a clear error when missing). Names only — never values; values belong in the developer's secret store. A later phase that depends on a variable names it in its own `tech_stack_spec.configurations`._
- **OPENAI_API_KEY** — purpose: LLM access; required: yes
- **DASH_DEBUG** — required: no
- **PORT**
- purpose: nameless
- RAW_STRING

**Existing API surface**
_Anchor any phase that proposes API changes on these routes — extend rather than parallel-invent — and match each `protocol`'s conventions (HTTP verb+path, gRPC service.method, GraphQL operation) when describing new endpoints._
- **/api/plan** — protocol: HTTP; handler: plan_view; summary: creates a plan
- protocol: gRPC
- raw

**Existing protocols implemented**
_Industry standards the project already implements. Cite each protocol's canonical doc URL in the corresponding phase's `references` array._
- **MCP** — version: 2025-06; location: src/mcp
- **A2A**
- plain text

**Existing incomplete or dead code**
_Do not extend any of this in a phase unless explicitly asked._
- old_view() is unused

**Existing change risks**
_Apply each mitigation hint in the phases that touch its area._
- **app.py** — risk: import order is load-bearing; mitigation hint: keep the noqa
- a bare risk

**Existing test coverage**
_Where tests exist today. A phase that touches an uncovered module adds its tests in that phase._
- has tests: yes
- framework: pytest
- covered modules:
  - app
- uncovered modules:
  - cli