# Spec4 AI

> AI-assisted software project planning — from idea to executable coding phases.

![PyPI version](https://img.shields.io/pypi/v/spec4)

Spec4 is a Dash app (using Dash Mantine Components) that guides you from idea to deployment using a pipeline of specialised LLM agents. Start with a rough idea and finish with a set of structured, ordered development phases — plus an optional UI mock and deployment plan — ready to hand to an AI coding agent like Claude Code.

> _"You've made something really really really cool. I'm almost done with our driver app. Will be
> field tested by Friday. I don't think I would have built what this is going to become without it."_<br />
> Wihan Booyse, [Kriterion.ai](https://kriterion.ai)

### How It Works
[![How Spec4 Works](https://github.com/robertcrowe/Spec4/raw/main/src/spec4/assets/landing.png)](https://spec4.ai/how-it-works/)

---

## Built With Spec4 (BWS4)

<img align="right" src="https://github.com/robertcrowe/Spec4/raw/main/BWS4-logos/BWS4-white-100.png" alt="BWS4 logo" width="100" />

**[Built With Spec4 (BWS4)](https://bw.spec4.ai)** is the companion showcase: a live gallery of small example apps, every one of them planned with Spec4 and built by AI coding agents working directly from Spec4's phase files. Each app demonstrates one rung of the nine-tier complexity ladder that Spec4's Agentifier recommends from, so you can see what each pattern looks like as working software — and what Spec4's artifacts turn into when a coding agent executes them.

| Example app | Pattern demonstrated |
|-------------|----------------------|
| [Embeddings](https://bw.spec4.ai/embeddings) | Semantic similarity via vector representations |
| [Single Call](https://bw.spec4.ai/single-call) | One prompt in, one response out — plain or schema-constrained |
| [RAG](https://bw.spec4.ai/rag) | Retrieval-augmented generation with cited passages |
| [Tool Use](https://bw.spec4.ai/tool-use) | A real function-calling loop with live web search |
| [Chained Calls](https://bw.spec4.ai/chained-calls) | Sequential calls, each building on the last |
| [Planning Agent](https://bw.spec4.ai/planning) | A model that plans its own research steps, streamed live |
| [Orchestrated Subagents](https://bw.spec4.ai/orchestrated) | A coordinator briefing parallel specialists and merging their answers |
| [Multi-Agent Collaboration](https://bw.spec4.ai/collab) | Peer agents negotiating with private, mutually invisible constraints |

---

## Requirements

- Python 3.12+
- **[uv](https://docs.astral.sh/uv/) package manager**
- An API key for at least one supported LLM provider
- _(Optional)_ A [Tavily](https://tavily.com/) or [Exa](https://exa.ai/) API key for web search

---

## Installation

**Option 1 — Install from PyPI (recommended for most users):**

```bash
uv tool install spec4 --refresh
spec4
```

**Option 2 — Run from source (for contributors and developers):**

```bash
git clone https://github.com/robertcrowe/spec4
cd spec4
make spec4
```

`make spec4` runs `uv sync` (creates a `.venv` and installs all dependencies) then launches the app. All packages stay inside `.venv` — nothing is installed into your global Python.

> **Subsequent runs:** `make run` reuses the existing `.venv`.

The app will be available at [http://localhost:8050](http://localhost:8050) in both cases.

---

## Upgrading

**If you installed from PyPI:**

```bash
uv tool upgrade spec4
spec4 --version   # confirm the new version
```

**If you run from source:**

```bash
cd spec4
git pull
make install      # re-sync .venv with any changed dependencies
make run
```

Upgrades never touch your project artifacts: everything Spec4 has produced for a
project lives in the `.spec4/` folder inside that project's directory and is
picked up again the next time you select it. Saved provider credentials live in
your browser's localStorage and also carry over.

---

## Features

- **Seven-stage pipeline** — CodeScanner (optional) → Brainstormer → Agentifier → Designer (optional) → StackAdvisor → Phaser → Deployer
- **Agentifier** — identifies AI/LLM integration opportunities in your vision, recommends the right complexity tier and implementation mechanisms for each, drafts a full implementation spec per feature, and produces `ai_features.json` consumed by StackAdvisor, Phaser, and Deployer
- **Designer** — optional parallel stage that generates [an HTML mock of your UI](https://spec4.ai/examples/mock.html) from a vision and (optionally) reference screenshots
- **Any LLM provider** — works with Anthropic, AWS Bedrock, Cohere, Google Gemini, Mistral, Nebius, and OpenAI via LiteLLM
- **Web search grounding** — all agents can search the web via Tavily or Exa to find canonical documentation
- **Saved credentials** — optionally remember your provider, model, and API keys in the browser (localStorage via `dcc.Store` — never sent to or stored on the server)
- **Incremental output** — each agent produces a downloadable artifact you can reuse in a later session
- **Jump-in anywhere** — pick up at any stage by selecting a project directory with previously saved artifacts
- **Project persistence** — artifacts saved to a `.spec4/` folder inside your chosen project directory
- **Deployer** — Generates a [deployment plan](https://spec4.ai/examples/deployment-plan.html) including coding agent instructions and even Terraform scripts

---

## Agents

### 🔍 CodeScanner *(optional)*
Analyzes an existing project directory to understand its architecture, technology stack, and coding style. Results inform Brainstormer and StackAdvisor when working on brownfield projects. Produces `code_review.json`.

### 🧠 Brainstormer
Develops a clear project vision through focused, one-at-a-time questions. Identifies technical standards via web search and embeds canonical documentation links in the output. On completion it also derives a technology-agnostic behavioral spec for every MVP feature (inputs, outputs, success criteria, failure modes). Produces `vision.json` and `feature_specs.json`.

### 🤖 Agentifier
Identifies every AI/LLM integration opportunity in your project vision, recommends the right complexity tier for each (from a nine-level ladder: deterministic → embeddings → single_call → RAG → tool agent → chained calls → planning agent → orchestrated subagents → multi-agent collaboration), and selects the implementation mechanisms that genuinely apply from a six-pattern library (structured outputs, retrieval reranking, parallel fan-out, reflection, human-in-the-loop, MCP reuse). Both decisions are grounded in a versioned Markdown pattern library whose when-to-use and over-engineering guidance is injected into the analysis prompts — wanting a mechanism never inflates a tier, and each chosen mechanism's canonical definition travels into the phase files the coding agent receives. Drafts a full implementation spec per feature (inputs, outputs, evals, budgets, failure modes, mechanisms) and produces system-level cross-cutting recommendations (observability, eval cadence, provider strategy, tool protocol strategy, and more). Produces `ai_features.json`, consumed downstream by StackAdvisor, Phaser, and Deployer. Supports both greenfield and brownfield projects.

### 🎨 Designer *(optional, parallel)*
Generates a single-file HTML mock of your UI from your vision and reference screenshots. Supports two modes — create from scratch, or modify an existing UI while preserving its look and feel — with iterative refinement. Skipped automatically for CLI/terminal projects. Produces `design/mock.html`. [Sample Design Mock](https://spec4.ai/examples/mock.html)

### ⚙️ StackAdvisor
Recommends languages, frameworks, hosting, and infrastructure based on the vision. Compares options, explains trade-offs, and uses web search to ground every recommendation. Produces `stack.json`.

### 📋 Phaser
Decomposes the vision and stack into an ordered sequence of development phases:

- **Phase 1 is always a steel thread** — a minimal end-to-end path that validates the core architecture
- **Each phase builds on the previous one**
- **Stack spec fidelity** — confirms before adding any dependency not in the stack spec
- **Verification criteria** — every phase includes the exact command needed to confirm it succeeded

Saves one JSON file per phase under `.spec4/phases/`, downloadable as `phases.zip`.

### 🚀 Deployer
Plans the path from working code to a running production deployment. Walks through coding-agent workflow, deployment target, containerization, CI/CD, environment config, and monitoring — and can optionally generate complete Terraform scripts grounded in live provider docs via web search. Produces `deployment-plan.md`. [Sample Deployment Plan](https://spec4.ai/examples/deployment-plan.html)


---

## Usage

1. **Select a project directory** — new or existing; artifacts are saved to `.spec4/` inside it.
2. **Connect** — select a provider, enter your API key, and choose a model. Optionally pick a web search provider (Tavily or Exa) and add its key.
3. **Choose a starting point** — pick an agent to begin with.
4. **Plan** — chat with each agent. When an agent completes, download the result and continue to the next agent.

### Picking up where you left off

Each session auto-saves to `.spec4/` inside your project directory. On a future visit, select the same directory and previously completed artifacts will be loaded automatically.

### Usage log (`usage.json`)

**Location:** `.spec4/v{N}/usage.json`, one file per round.

**Produced by:** the pipeline itself. Every LLM call Spec4 makes is recorded, and the file is rewritten after each agent turn and each Designer draw, not only at the end of a round, so a crashed or abandoned session still leaves a record.

**Consumed by:** you. No agent reads it. It is not a pipeline artifact: it is excluded from the artifact dependency graph, so writing or editing it never marks an agent *Needs Update*.

**Purpose:** per-agent token and cost accounting for a round, with the per-call history that the summaries are derived from.

**Schema (`schema_version` 1):**

| Field | Meaning |
|---|---|
| `spec4_version`, `litellm_version` | Versions that last wrote the file |
| `round` | `v{N}` |
| `created_at`, `updated_at` | UTC ISO 8601; `created_at` is preserved across writes |
| `notes.tokens_are_ground_truth` | Always `true` (see below) |
| `notes.computed_cost_source` | Where `computed_cost_usd` comes from |
| `notes.fast_forward` | `true` once any Fast Forward turn was recorded in the round, `false` when only ordinary turns are known, `null` when nothing is known |
| `agents.<name>` | One block per planning agent (`brainstormer`, `agentifier`, `designer`, `stack_advisor`, `phaser`, `deployer`, `code_scanner`). Sub-agents roll up into the agent whose turn runs them |
| `agents.<name>.calls`, `input_tokens`, `output_tokens`, `total_tokens` | Call count and summed tokens over calls that reported usage |
| `agents.<name>.calls_missing_usage` | Calls the provider returned no usage for; their tokens are not counted |
| `agents.<name>.calls_missing_cost` | Calls that reported usage but LiteLLM could not price; their tokens are counted, their cost is not |
| `agents.<name>.cached_input_tokens` | Summed cache-read tokens where the provider reported them, else `null` |
| `agents.<name>.computed_cost_usd` | Summed LiteLLM cost estimate, `null` when no call could be priced |
| `agents.<name>.models` | Distinct `{model, provider}` pairs used, in first-seen order |
| `agents.<name>.history` | The per-call records: `timestamp`, `agent` (the sub-agent, if any), `model`, `provider` (as LiteLLM resolves it), `streamed`, `duration_s`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `cached_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `computed_cost_usd`, `usage_missing`, `error` |
| `totals` | The same sums across all agents (including both `calls_missing_*` counts) |

Every summary is recomputed from `history` on each write; nothing in the file is accumulated independently of the call records.

**Two notes on the numbers:**

- Token counts come from the providers' own responses, passed through LiteLLM. They are ground truth. When a provider returns no usage for a call, the call is still recorded with `null` token fields and `usage_missing: true`; nothing is estimated from text length.
- `computed_cost_usd` comes from LiteLLM's community-maintained cost map, which can lag provider price sheets and has no entry for some models (Nebius models, for instance, are recorded with `null` cost). Treat it as advisory. When the dollar figure matters, recompute it from the token counts and the providers' current price sheets.

The file survives quitting and re-entering, including with a different provider or model: a re-run appends to the agent's `history` and adds the new `{model, provider}` pair to `models`. It never overwrites earlier calls.

**In-app cost card.** When an agent's run completes (CodeScanner, Brainstormer, Agentifier, StackAdvisor, Phaser, Deployer under the run's last message; Designer on the mock preview), Spec4 shows an *Estimated cost* card read from this file: the agent's summed cost for the round and the round's running total, each with a note when calls could not be priced, and a disclaimer that the figures are LiteLLM estimates rather than provider billing.

To print a per-agent table for a round:

```bash
spec4-usage /path/to/project            # latest round
spec4-usage /path/to/project --round 0  # a specific round
```

---

## Project structure

```
src/spec4/
├── app.py                  # Dash entry point — app wiring, root layout, page render
├── app_constants.py        # Phase names, URL→phase routing, agent state constants
├── session.py              # Session defaults, agent runner, artifact persistence
├── streaming.py            # Background-thread streaming + provider error formatting
├── providers.py            # Provider/model registry, live model fetching
├── llm.py                  # LLM conversation turns + web search tool loop
├── websearch.py            # Web search providers (Tavily, Exa) — MCP async bridge
├── project_manager.py      # .spec4/ artifact persistence + phase-file assembly
├── usage_report.py         # spec4-usage CLI: per-agent table from usage.json
├── feature_specs.py        # Shared spec renderer (Phaser context + phase files)
├── design_manifest.py      # Design-mock manifest joins for Phaser
├── stack_routing.py        # Deterministic stack→phase and NFR→phase joins
├── agents/
│   ├── code_scanner.py     # Code review agent
│   ├── brainstormer.py     # Vision development agent
│   ├── feature_speccer.py  # Post-vision behavioral feature specs (feature_specs.json)
│   ├── stack_advisor.py    # Technology stack recommendation agent
│   ├── phaser.py           # Incremental phase planning agent
│   ├── deployer.py         # Deployment planning agent (terminal pipeline stage)
│   └── designer.py         # UI mock generation agent (parallel, optional)
├── agentifier/             # AI feature identification and specification pipeline
│   ├── agentifier.py       # Orchestrator: catalog → spec → cross-cutting → priority
│   ├── scout.py            # Sub-agent: surface AI opportunity candidates
│   ├── tier_analyst.py     # Sub-agent: recommend complexity tier per candidate
│   ├── spec_drafter.py     # StreamingSubAgent: draft per-feature implementation spec
│   ├── cross_cutting_analyst.py  # StreamingSubAgent: system-level recommendations
│   ├── reference_verifier.py     # Web-search-backed reference URL enrichment
│   ├── pattern_loader.py   # Load and validate the tier/mechanism pattern library
│   ├── subagents.py        # Sub-agent protocol, registry, and error types
│   └── patterns/           # Markdown pattern library (tiers/ and mechanisms/)
├── callbacks/              # Dash server-side callbacks (main pipeline + designer)
└── layouts/                # Page layout functions (chat, setup, designer, shared)
tests/
├── agentifier/             # Agentifier unit tests
├── integration/            # End-to-end pipeline tests (mocked LLMs)
└── test_*.py               # Agent and utility unit tests
evals/                      # On-demand measurement harnesses (real LLM calls;
├── agentifier/             #   not part of make test) — mechanism probe,
├── tier_calibration/       #   tier calibration, Scout/Phaser/Deployer/
└── ...                     #   StackAdvisor/Designer probes
Makefile                    # Common commands
```

---

## Development

```bash
make spec4       # First-time setup: create .venv, install deps, and launch
make install     # Create .venv and install all dependencies (uv sync)
make run         # Start the app (http://localhost:8050)
make dev         # Start with debug/hot-reload enabled
make test        # Run tests
make lint        # Lint check with ruff
make serve       # Production server via gunicorn (requires: uv add gunicorn)

# Add a dependency (always use uv so it stays in .venv)
uv add <package>
uv add --dev <package>
```

On-demand eval harnesses live in `evals/` — they make real LLM calls, are never
run by `make test`, and exist to measure prompt/pattern changes before and after
(see `evals/agentifier/README.md` and `evals/tier_calibration/README.md`).

---

## Supported Model Providers

| Provider | Models fetched from |
|----------|-------------------|
| Anthropic | `api.anthropic.com/v1/models` |
| AWS Bedrock | `bedrock.amazonaws.com` |
| Cohere | `api.cohere.com/v2/models` |
| Google Gemini | `generativelanguage.googleapis.com` |
| Mistral | `api.mistral.ai/v1/models` |
| Nebius | `api.tokenfactory.nebius.com/v1/` |
| OpenAI | `api.openai.com/v1/models` |
| OpenRouter | `openrouter.ai/api/v1/models` |

Models are fetched live from each provider's API when you connect, with a hardcoded fallback list if the API is unavailable.

**AWS Bedrock** authentication supports Bedrock API keys, IAM access keys, or ambient AWS credentials (environment variables, `~/.aws/credentials`, or IAM roles).

---

## Supported Search Providers

Web search grounds agent recommendations in live documentation and is available to every agent in the pipeline. It is optional — without a key the agents still run, just without live grounding. Both providers are reached through their hosted MCP servers, so there is nothing extra to install:

| Provider | Connected via | Get a key |
|----------|---------------|-----------|
| Tavily *(default)* | `mcp.tavily.com` | [tavily.com](https://tavily.com/) |
| Exa | `mcp.exa.ai` | [exa.ai](https://exa.ai/) |

Pick the search provider and enter its API key on the Connect screen, alongside your model provider.

---

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
