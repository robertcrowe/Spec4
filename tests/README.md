# Test Coverage Baseline (Phase 1)

Recorded from `uv run pytest --cov --cov-report=term-missing` on 2026-04-28.
Total: **96%** (1435 statements, 64 missed)

| Module | Coverage | Notes |
|--------|----------|-------|
| `spec4/__init__.py` | 60% | version-read fallback path |
| `spec4/agents/__init__.py` | 100% | |
| `spec4/agents/_utils.py` | 100% | |
| `spec4/agents/brainstormer.py` | 100% | |
| `spec4/agents/phaser.py` | 90% | lines 255-262, 267-271 |
| `spec4/agents/reviewer.py` | 91% | lines 130, 143-144, 159, 169-170, 292-293 |
| `spec4/agents/stack_advisor.py` | 100% | |
| `spec4/app_constants.py` | 100% | |
| `spec4/project_manager.py` | 91% | lines 72-78, 121-122 |
| `spec4/providers.py` | 70% | provider-specific fetch paths not all exercised |
| `spec4/session.py` | 90% | lines 93-94, 96-97, 103, 109-110 |
| `spec4/tavily_mcp.py` | 78% | MCP async paths, lines 57-61, 65-80, 183-184, 187, 194 |
| **`spec4/app.py`** | **0%** | UI entry point — not tested |
| **`spec4/layouts.py`** | **0%** | UI layouts — not tested |
| **`spec4/callbacks.py`** | **0%** | Dash callbacks — not tested |
| **`spec4/streaming.py`** | **0%** | Background streaming — not tested |

Zero-coverage modules (expected): `app.py`, `layouts.py`, `callbacks.py`, `streaming.py`.
These are Dash UI modules; integration/browser tests would be needed to cover them.
