from __future__ import annotations

from typing import Any

GOOGLE_FONTS = (
    "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700"
    "&family=JetBrains+Mono:wght@400;500&display=swap"
)

PATH_TO_PHASE = {
    "/": "landing",
    "/dir": "working_dir",
    "/setup": "setup",
    "/agents": "agent_select",
    "/chat": "chat",
    "/design": "designer",
}

DARK_THEME: dict[str, Any] = {
    "primaryColor": "blue",
    "primaryShade": {"dark": 5, "light": 6},
    "fontFamily": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    "fontFamilyMonospace": "JetBrains Mono, Fira Code, monospace",
    "colors": {
        "dark": [
            "#f5f5f7",
            "#a0a0b0",
            "#6a6a7a",
            "#3a3a4a",
            "#2a2a3a",
            "#1a1a24",
            "#12121a",
            "#0a0a0f",
            "#050508",
            "#020204",
        ],
        "blue": [
            "#e3f2fd",
            "#bbdefb",
            "#90caf9",
            "#64b5f6",
            "#42a5f5",
            "#1e88e5",
            "#1976d2",
            "#1565c0",
            "#0d47a1",
            "#0a3880",
        ],
    },
}

# Agent state values
STATE_IN_PROGRESS = "in_progress"
STATE_VISION_COMPLETE = "vision_complete"
STATE_AGENTIFIER_COMPLETE = "agentifier_complete"
STATE_STACK_COMPLETE = "stack_complete"
STATE_PHASES_COMPLETE = "phases_complete"
STATE_REVIEW_COMPLETE = "review_complete"
STATE_DEPLOYER_COMPLETE = "deployer_complete"

# Whether the working directory holds a project we are modifying, or is where
# a brand-new project will be built (D-PM1). Spec4 cannot infer this from the
# files alone — a `uv init` skeleton is indistinguishable from a real codebase
# by directory contents — so the developer is asked once per session and the
# answer lives only in the session store (never on disk), which is what makes
# it re-ask after a quit and restart.
PROJECT_MODE_EXISTING = "existing"
PROJECT_MODE_NEW = "new"
PROJECT_MODES = (PROJECT_MODE_EXISTING, PROJECT_MODE_NEW)

# The Fast Forward sweep instruction, validated across live draws. Injected
# verbatim by the FF button and honoured by LLM-conversational phases
# directly; the Python-paced Agentifier phases (spec drafting,
# cross-cutting) detect it by exact match (D-AF1) and run their own sweep.
FF_PROMPT = (
    "For this and all of the remaining topics please create a comprehensive "
    "set of recommendations, which I will review and potentially modify as a "
    "whole before finalizing."
)
