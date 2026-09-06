from __future__ import annotations

from typing import Any

GOOGLE_FONTS = (
    "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700"
    "&family=JetBrains+Mono:wght@400;500&display=swap"
)

# The fixed routes. The root path is deliberately absent: it has no fixed
# phase, because it resolves at navigation time to the project view when a
# working directory is remembered and still readable, and to the directory
# picker otherwise (D-LR6, `on_browser_navigate`).
PATH_TO_PHASE = {
    "/dir": "working_dir",
    "/setup": "setup",
    "/agents": "agent_select",
    "/chat": "chat",
    "/design": "designer",
}

# The application root, whose destination is decided rather than looked up.
ROOT_PATH = "/"

# The phase a session sits in before the root path has resolved. Nothing is
# drawn for it — `render_page` returns an empty container — which is what keeps
# any intermediate screen off the page between mount and destination. It is
# also the default session phase, so a first paint can never show a screen the
# router has not chosen.
PHASE_ROOT = "root"

# Where the root resolves to. The project view when a directory is remembered
# and openable; the directory picker otherwise. There is no third destination.
PHASE_PROJECT_VIEW = "agent_select"
PHASE_DIRECTORY_PICKER = "working_dir"

# The one accent colour. Every primary action, active state and focus ring in
# the app is this green, and nothing else is.
SPEC4_GREEN = "#39FF14"

# D-LR2: the accent is set here, once, and every component inherits it.
#
# `spec4-green` is registered as a ten-shade colour and named as the theme's
# `primaryColor`, which Mantine resolves as a KEY of `theme.colors` — handing
# it the raw hex value instead throws while the theme is merged. `primaryShade`
# then picks which of the ten shades actually renders, and shade 5 is
# SPEC4_GREEN exactly, so the dark scheme the app forces draws #39FF14. Shade 6
# is the hover step the design mock specifies (#31e510).
#
# The consequence for every layout: **no component may pass a local `color`
# prop for its accent.** A component that wants the accent omits `color` and
# takes the theme primary. `color` survives only for semantics the accent does
# not carry — red for errors, yellow/orange for warnings, gray for neutral.
SPEC4_GREEN_SHADES = [
    "#e9ffe3",
    "#d3ffc7",
    "#aeff96",
    "#86ff62",
    "#5fff36",
    SPEC4_GREEN,
    "#31e510",
    "#26c00b",
    "#1c9c07",
    "#127803",
]

DARK_THEME: dict[str, Any] = {
    "primaryColor": "spec4-green",
    "primaryShade": {"dark": 5, "light": 6},
    # The accent is a bright neon, so Mantine's default white label on a filled
    # primary button is unreadable. `autoContrast` makes it pick the dark label
    # the design mock draws (`.btn-primary` is `--bg` on `--accent`), and it
    # does so from the resolved primary — one more thing no component has to
    # restate locally.
    "autoContrast": True,
    "fontFamily": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    "fontFamilyMonospace": "JetBrains Mono, Fira Code, monospace",
    "colors": {
        "spec4-green": SPEC4_GREEN_SHADES,
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


# The seven user-facing agents, in pipeline order. This is the authority for
# anything keyed by agent — the per-agent model overrides in `llm_selection`,
# and the rows on /agents. It lives here rather than in `layouts` because
# `session` and `llm_selection` need it and `layouts` imports `session`;
# `_AGENT_ROWS` carries the display data for the same keys and is checked
# against this tuple by the suite.
AGENT_KEYS: tuple[str, ...] = (
    "code_scanner",
    "brainstormer",
    "agentifier",
    "designer",
    "stack_advisor",
    "phaser",
    "deployer",
)
