# Spec4 AI

> AI-assisted software project planning — from idea to executable coding phases.

[![PyPI version](https://badge.fury.io/py/spec4.svg)](https://badge.fury.io/py/spec4)

Spec4 is a Dash app (using Dash Mantine Components) that guides you through three stages of project planning using a pipeline of specialised LLM agents. Start with a rough idea and finish with a set of structured, ordered development phases ready to hand to an AI coding agent like Claude Code.

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
uv tool install spec4
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

- **Four-stage planning pipeline** — Reviewer (optional) → Brainstormer → StackAdvisor → Phaser
- **Any LLM provider** — works with OpenAI, Anthropic, Google Gemini, Cohere, and Mistral via LiteLLM
- **Web search grounding** — all agents can search the web via Tavily to find canonical documentation
- **Saved credentials** — optionally remember your provider, model, and API keys in the browser (localStorage via `dcc.Store` — never sent to or stored on the server)
- **Incremental output** — each agent produces a downloadable JSON or ZIP file you can reuse in a later session
- **Jump-in anywhere** — start at StackAdvisor or Phaser by uploading previously saved output
- **Project persistence** — artifacts saved to a `.spec4/` folder inside your chosen project directory

---

## Agents

### 🔍 Reviewer *(optional)*
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

Produces `phases.zip` with one JSON file per phase.

---

## Usage

1. **Select a project directory** — new or existing; artifacts are saved to `.spec4/` inside it.
2. **Connect** — select a provider, enter your API key, and choose a model. Optionally add a Tavily key for web search.
3. **Choose a starting point** — pick an agent to begin with.
4. **Plan** — chat with each agent. When an agent completes, download the result and continue to the next agent.

### Picking up where you left off

Each session auto-saves to `.spec4/` inside your project directory. On a future visit, select the same directory and previously completed artifacts will be loaded automatically. You can also upload JSON files manually on the agent-select screen.

---

## Project structure

```
src/spec4/
├── app.py                  # Dash entry point — app wiring, root layout, page render
├── app_constants.py        # Shared constants (theme, routes, fonts)
├── session.py              # Session defaults, agent runner, artifact persistence
├── layouts.py              # All page layout functions
├── callbacks.py            # All Dash server-side callbacks
├── providers.py            # Provider/model registry, live model fetching
├── tavily_mcp.py           # Tavily web search integration
├── project_manager.py      # .spec4/ artifact persistence
├── a2a_bus.py              # In-memory A2A task bus
└── agents/
    ├── reviewer.py         # Code review agent
    ├── brainstormer.py     # Vision development agent
    ├── stack_advisor.py    # Technology stack recommendation agent
    └── phaser.py           # Incremental phase planning agent
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
