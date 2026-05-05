# Spec4 AI

> AI-assisted software project planning — from idea to executable coding phases.

![PyPI version](https://img.shields.io/pypi/v/spec4)

Spec4 is a Dash app (using Dash Mantine Components) that guides you from idea to deployment using a pipeline of specialised LLM agents. Start with a rough idea and finish with a set of structured, ordered development phases — plus an optional UI mock and deployment plan — ready to hand to an AI coding agent like Claude Code.

> _"You've made something really really really cool. I'm almost done with our driver app. Will be
> field tested by Friday. I don't think I would have built what this is going to become without it."_<br />
> Wihan Booyse, [Kriterion.ai](https://kriterion.ai)

### Quick Demo Video
[![Spec4 Demo](https://github.com/robertcrowe/Spec4/raw/main/src/spec4/assets/thumb.png)](https://youtu.be/vhIcx05FoUs)

---

## Requirements

- Python 3.12+
- **[uv](https://docs.astral.sh/uv/) package manager**
- An API key for at least one supported LLM provider
- _(Optional)_ A [Tavily](https://tavily.com/) API key for web search

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

## Features

- **Five-stage pipeline** — CodeScanner (optional) → Brainstormer → StackAdvisor → Phaser → Deployer
- **Designer** — optional parallel stage that generates an HTML mock of your UI from a vision and (optionally) reference screenshots
- **Any LLM provider** — works with OpenAI, Anthropic, Google Gemini, Cohere, and Mistral via LiteLLM
- **Web search grounding** — all agents can search the web via Tavily to find canonical documentation
- **Saved credentials** — optionally remember your provider, model, and API keys in the browser (localStorage via `dcc.Store` — never sent to or stored on the server)
- **Incremental output** — each agent produces a downloadable artifact you can reuse in a later session
- **Jump-in anywhere** — pick up at any stage by selecting a project directory with previously saved artifacts
- **Project persistence** — artifacts saved to a `.spec4/` folder inside your chosen project directory

---

## Agents

### 🔍 CodeScanner *(optional)*
Analyzes an existing project directory to understand its architecture, technology stack, and coding style. Results inform Brainstormer and StackAdvisor when working on brownfield projects. Produces `code_review.json`.

### 🧠 Brainstormer
Develops a clear project vision through focused, one-at-a-time questions. Identifies technical standards via web search and embeds canonical documentation links in the output. Produces `vision.json`.

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
Plans the path from working code to a running production deployment. Walks through coding-agent workflow, deployment target, containerization, CI/CD, environment config, and monitoring — and can optionally generate complete Terraform scripts grounded in live provider docs via web search. Produces `deployment-plan.md`.

### 🎨 Designer *(optional, parallel)*
Generates a single-file HTML mock of your UI from your vision and reference screenshots. Supports two modes — create from scratch, or modify an existing UI while preserving its look and feel — with iterative refinement. Skipped automatically for CLI/terminal projects. Produces `design/mock.html`.

---

## Usage

1. **Select a project directory** — new or existing; artifacts are saved to `.spec4/` inside it.
2. **Connect** — select a provider, enter your API key, and choose a model. Optionally add a Tavily key for web search.
3. **Choose a starting point** — pick an agent to begin with.
4. **Plan** — chat with each agent. When an agent completes, download the result and continue to the next agent.

### Picking up where you left off

Each session auto-saves to `.spec4/` inside your project directory. On a future visit, select the same directory and previously completed artifacts will be loaded automatically.

---

## Project structure

```
src/spec4/
├── app.py                  # Dash entry point — app wiring, root layout, page render
├── app_constants.py        # Phase names, URL→phase routing, agent state constants
├── session.py              # Session defaults, agent runner, artifact persistence
├── streaming.py            # Background-thread streaming + provider error formatting
├── providers.py            # Provider/model registry, live model fetching
├── tavily_mcp.py           # Tavily web search integration (async bridge)
├── project_manager.py      # .spec4/ artifact persistence
├── agents/
│   ├── code_scanner.py     # Code review agent
│   ├── brainstormer.py     # Vision development agent
│   ├── stack_advisor.py    # Technology stack recommendation agent
│   ├── phaser.py           # Incremental phase planning agent
│   ├── deployer.py         # Deployment planning agent (terminal pipeline stage)
│   └── designer.py         # UI mock generation agent (parallel, optional)
├── callbacks/              # Dash server-side callbacks (main pipeline + designer)
└── layouts/                # Page layout functions (chat, setup, designer, shared)
tests/                      # pytest test suite
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

---

## Supported providers

| Provider | Models fetched from |
|----------|-------------------|
| OpenAI | `api.openai.com/v1/models` |
| Anthropic | `api.anthropic.com/v1/models` |
| Google Gemini | `generativelanguage.googleapis.com` |
| Cohere | `api.cohere.com/v2/models` |
| Mistral | `api.mistral.ai/v1/models` |

Models are fetched live from each provider's API when you connect, with a hardcoded fallback list if the API is unavailable.

---

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
