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

**Existing implemented capabilities**
_Already built, with status. Never propose a `complete` one as new; a `partial`/`stub` one is a finish-or-remove question._
- **Structured code review** — id: code_review; description: Walks a directory and drafts a schema-checked review; status: complete; paths: src/app/scanner/; prior feature ids: round_tree; agent_rows [src/app/scanner/__init__.py]
- **Deployment plan** — id: deploy_plan; status: stub; paths: src/app/deployer.py [src/app/deployer.py]
- **VPS runtime bring-up** — id: vps_runtime; description: Boots the API under systemd on the VPS with the environment contract from /etc/bws4; status: complete; paths: deploy/bws4.service; backend/app/main.py; prior feature ids: self_hosted_deployment [deploy/bws4.service]

**Unplanned changes since the last round**
_What changed since the last round outside any plan. A feature that touches an area here acknowledges it rather than proposing it fresh._
- **scanner evidence tiers** — summary: The scanner gained tiered sampling and a most-touched body tier that no phase of the last round planned; affects: src/app/scanner/; code_review; classification: out_of_round [src/app/scanner/__init__.py]
- **documentation and manifests** — summary: CHANGELOG and lock-file churn across the round; affects: CHANGELOG.md; uv.lock; classification: out_of_round [CHANGELOG.md]
- **deployment plan** — summary: deployer.py is a stub that nothing in the prior plan introduced; affects: src/app/deployer.py; classification: unknown [src/app/deployer.py]

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