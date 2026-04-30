from __future__ import annotations

import pathlib
from typing import Any

from dash import dcc, html
import dash_mantine_components as dmc

from spec4.layouts._shared import _card


def _done_layout(session: dict[str, Any]) -> html.Div:
    phases = session.get("phases", [])
    n = len(phases)
    spec4_dir = pathlib.Path(session.get("working_dir", "")) / ".spec4"
    has_vision = (spec4_dir / "vision.json").exists()
    has_stack = (spec4_dir / "stack.json").exists()

    phase_rows = [
        dmc.Text(
            f"Phase {p.get('phase_number')}: {p.get('phase_title', '')}",
            size="sm",
            style={
                "paddingLeft": "0.5rem",
                "borderLeft": "2px solid var(--mantine-color-blue-5)",
            },
            mb="xs",
        )
        for p in sorted(phases, key=lambda x: x.get("phase_number", 0))
    ]

    return html.Div(
        [
            dcc.Download(id="dl-phases-done"),
            dcc.Download(id="dl-vision-done"),
            dcc.Download(id="dl-stack-done"),
            dmc.Title("Your Project Phases Are Ready", order=3, mb="xs"),
            dmc.Text(
                f"Spec4 has broken your project into {n} executable phase{'s' if n != 1 else ''}. "  # noqa: E501
                "Hand them to an agentic coding tool and work through them in order.",
                c="dimmed",
                mb="lg",
            ),
            _card(
                dmc.Title("How to use your phases", order=5, mb="sm"),
                dcc.Markdown(
                    "1. Open your agentic coding tool (Claude Code, Codex, Antigravity, Hermes, etc.) "  # noqa: E501
                    "inside your project directory.\n"
                    "2. Load or paste the contents of **Phase 1** as your prompt.\n"
                    "3. Let the agent complete the phase fully — verify it passes before continuing.\n"  # noqa: E501
                    "4. Repeat for Phase 2, Phase 3, and so on **in order**.\n\n"
                    "> Do not skip phases. Each phase builds directly on the one before it.\n\n"  # noqa: E501
                    "**Loading options:**\n"
                    "- **Copy/paste** — open each `.json` file and paste the contents into your tool.\n"  # noqa: E501
                    "- **File loading** — tools like Claude Code accept files directly "
                    "(e.g. `Please implement @.spec4/phases/phase1.json`).\n"
                    "- **Download** — use the button below to get all phases as a zip.",
                    style={"fontSize": "0.9rem"},
                ),
                mb="md",
            ),
            _card(
                dmc.Title(
                    "Python project? Set up your environment first", order=5, mb="sm"
                ),
                dcc.Markdown(
                    "Before starting your agentic coding tool, initialise a virtual environment "  # noqa: E501
                    "so your agent installs dependencies in an isolated, reproducible way:\n\n"  # noqa: E501
                    "```bash\n"
                    "uv init\n"
                    "uv sync\n"
                    "source .venv/bin/activate\n"
                    "```\n\n"
                    "On Windows use `.venv\\Scripts\\activate` instead of `source .venv/bin/activate`.",  # noqa: E501
                    style={"fontSize": "0.9rem"},
                ),
                mb="md",
            ),
            _card(
                dmc.Title(f"Your {n} phase{'s' if n != 1 else ''}", order=5, mb="sm"),
                *phase_rows,
            )
            if phase_rows
            else html.Div(),
            dmc.Divider(my="md"),
            dmc.Group(
                [
                    dmc.Button(
                        "← Back to Phaser",
                        id="btn-done-back-to-phaser",
                        variant="outline",
                        color="gray",
                    ),
                    dmc.Button(
                        "💾 Download vision.json",
                        id="btn-dl-vision-done",
                        variant="outline",
                        style={"display": "none"} if not has_vision else {},
                    ),
                    dmc.Button(
                        "💾 Download stack.json",
                        id="btn-dl-stack-done",
                        variant="outline",
                        style={"display": "none"} if not has_stack else {},
                    ),
                    dmc.Button(
                        "💾 Download phases.zip",
                        id="btn-dl-phases-done",
                        variant="outline",
                    ),
                    dmc.Button(
                        "Start New Project", id="btn-done-new-project", variant="light"
                    ),
                ]
            ),
        ]
    )
