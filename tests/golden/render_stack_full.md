**Tech Stack: Ragmeister**

A policy Q&A service with retrieval over an internal library.

**Languages:**
- Python 3.12 — backend
  - Notes: typed
- TypeScript 5.4
- SQL

**Deployment:**
- api (container)
  - Runtime: Fly.io
  - Regions: iad, ams
- web (static)
- worker
- Strategy: blue-green
- Secrets:
  - Manager: 1Password
  - Rotation Days: 90

**Providers:**
- OpenAI
  - single_call: fast cheap model (primary)
    - Models: gpt-5-mini
  - agentic: reasoning model
  - embeddings
  - Credentials Env: OPENAI_API_KEY
  - Fallback: Claude
- Anthropic: fallback only

**Integrations:**
- Stripe — billing
  - Auth: api key
  - Webhooks: yes
- Slack
- PagerDuty

**Libraries:**

*Backend:*
- FastAPI — HTTP API [Python, web]
  - Serves Features: `policy_qa`
  - Satisfies: `nfr_fast_`
- pgvector
- httpx

*Frontend:*
- Frontend: React (pinned by the design)

*Deferred:*

**Data & persistence:**
- primary_store — PostgreSQL 16
  - Purpose: system of record
  - Durability: source of truth
  - Serves Features: `policy_qa`, `policy_library_management`
  - Satisfies: `nfr_durable_`
  - policy_audit_log (holds Policy change history; serves `policy_library_management`)
  - policies (holds Policy, PolicyVersion; current text; serves `policy_qa`)
    - Indexes: policy_id
  - sessions
  - Backup:
    - Cadence: daily
    - Retention Days: 30
- cache — Redis
  - Ttl Seconds: 300
- blob: S3

**Infrastructure:**
- queue: Redis Streams
  - Serves Capabilities: `summariser`
  - Satisfies required substrate: `async_jobs`
  - Consumers: 2
- search
  - Provider: pgvector
- cdn: Cloudflare

**AI conventions:**
- Prompt Storage: prompts/ as versioned markdown
- Evals: golden set, LLM judge
- Guardrails:
  - Pii: redact before send
  - Max Tokens: 4000

**Project structure:**
- `src/api` — FastAPI app
  - Owner: backend
- `src/web`
- tests/

**Coding Style:**
- Formatter: ruff format
- Line Length: 88
- Naming:
  - Functions: snake_case
  - Classes: PascalCase
- Strict Typing: yes

**Additional decisions:**
- monorepo: yes
  - One repo, two packages.
  - Revisit: after MVP
- no ORM
- Feature flags via env vars

**References:**
- OWASP ASVS: https://owasp.org/asvs
- PEP 8

- Unknown Block:
  - Vendor: acme
  - Notes: a, b
  - Nested:
    - Deep: 1
- Status: ratified
---

We've finished defining the tech stack, so now you're ready to move on to creating implementation phases for your coding agent. Please click on the **Continue to Phaser** button below.