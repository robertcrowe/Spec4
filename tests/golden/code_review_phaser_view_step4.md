**Existing architecture**
_The existing pattern. Extend it rather than restructure it unless the vision says otherwise._
- pattern: monolith
- summary: one Flask process

**Existing load-bearing modules**
_A phase that touches a load-bearing module names, in its instructions and verification, the contract it preserves._
- **src/app/llm.py** · `stream_turn` (consumers: 0) — The one path every agent's LLM call goes through [src/app/llm.py]
  - inputs: system prompt; message list, mutated in place
  - outputs: yields text chunks
  - invariants: messages ends with the assistant turn
  - side effects: records usage in the session; network calls
- **src/app/constants.py** (consumers: 0) — Session keys and state names shared by every module [src/app/constants.py]
  - outputs: string constants

**Existing implemented capabilities**
_Already built, with status. Phases extend a `complete` capability rather than rebuild it; a `partial` or `stub` one a phase touches is finished or removed in that phase, as the vision decides._
- **Structured code review** — id: code_review; description: Walks a directory and drafts a schema-checked review; status: complete; paths: src/app/scanner/; prior feature ids: round_tree; agent_rows [src/app/scanner/__init__.py]
- **Deployment plan** — id: deploy_plan; status: stub; paths: src/app/deployer.py [src/app/deployer.py]
- **VPS runtime bring-up** — id: vps_runtime; description: Boots the API under systemd on the VPS with the environment contract from /etc/bws4; status: complete; paths: deploy/bws4.service; backend/app/main.py; prior feature ids: self_hosted_deployment [deploy/bws4.service]

**Prior round reconciliation (feature coverage, not phase scope)**
_Which of the last round's phases the code evidences, by feature coverage. A `no_evidence_found` or `evidence_partial` phase whose paths lie outside Scan coverage is unverified, not absent — Phase 1 verifies before any phase re-plans it; an `evidence_found` phase is not re-planned._
- phase 1 — *Integration Thread — VPS Baseline Bring-Up and Environment Contract Relocation* [evidence_partial]: `vps_runtime`; unclaimed: shared_framework_services; gap: The shared framework services package is planned but no module under backend/app/services exists yet [backend/app/]
- phase 2 — *Process Supervision — systemd Unit, Warm-at-Boot, Restart Survival* [evidence_partial]: `vps_runtime`; unclaimed: shared_framework_services; gap: Warm-at-boot is wired in the unit file but the model preload it names is a no-op
- phase 3 — *Observability — structlog JSON Boot Output and Health Probe* [unassessed] (no features declared)

**Unplanned changes since the last round**
_Changes made since the last round outside any plan; a phase that touches an area here starts from what is there now._
- **scanner evidence tiers** — summary: The scanner gained tiered sampling and a most-touched body tier that no phase of the last round planned; affects: src/app/scanner/; code_review; classification: out_of_round [src/app/scanner/__init__.py]
- **documentation and manifests** — summary: CHANGELOG and lock-file churn across the round; affects: CHANGELOG.md; uv.lock; classification: out_of_round [CHANGELOG.md]
- **deployment plan** — summary: deployer.py is a stub that nothing in the prior plan introduced; affects: src/app/deployer.py; classification: unknown [src/app/deployer.py]

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

**Scan coverage**
_Measured: how much of the source the review's evidence covered. A module outside the sampled set was reviewed from its signatures or not at all — a phase that touches one verifies before it relies on a claim about it._
- 4 of 2292 source files shown as bodies; 10 more as signature blocks; ~22,814 tokens of evidence