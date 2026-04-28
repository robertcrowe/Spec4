from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

_NO_UI_KEYWORDS = (
    "cli",
    "command-line",
    "command line",
    "no ui",
    "no-ui",
    "terminal",
    "batch",
)

_SYSTEM_PROMPT = (
    "You are an expert UI/UX designer. Your task is to generate a clean, "
    "modern, self-contained HTML mock-up for a web application's landing page "
    "or starting screen. You write HTML, CSS, and JavaScript directly — no "
    "frameworks, no external assets, no CDN links. All CSS goes inside a "
    "<style> block in the <head> and all JavaScript goes inside a <script> "
    "block at the end of <body>. The output must be a single complete HTML "
    "document."
)

_HTML_INSTRUCTION = (
    "Generate a single self-contained HTML file for the landing page or "
    "starting screen. Place all CSS inside a <style> block in <head> and all "
    "JavaScript inside a <script> block at the bottom of <body>. Do not use "
    "external CDN links or import statements."
)


class DesignerSession(TypedDict):
    step: int
    preference_text: str
    screenshots: list[dict[str, str]]
    mock_html: str
    finalized: bool


def detect_no_ui(
    vision: dict[str, object],
    code_review: dict[str, object],
) -> bool:
    """Return True if the project appears to have no graphical UI."""
    for obj in (vision, code_review):
        for field in ("purpose", "project_type", "description", "vision", "ui_type"):
            val = obj.get(field)
            if isinstance(val, str):
                lower = val.lower()
                if any(kw in lower for kw in _NO_UI_KEYWORDS):
                    return True
    return False


def detect_greenfield(project_root: Path) -> bool:
    """Return True if project_root contains only the .spec4/ directory."""
    entries = list(project_root.iterdir())
    return len(entries) == 1 and entries[0].name == ".spec4"


def load_session(design_dir: Path) -> DesignerSession | None:
    """Load a DesignerSession from design_dir/session.json, or return None."""
    path = design_dir / "session.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        session: DesignerSession = {
            "step": data["step"],
            "preference_text": data["preference_text"],
            "screenshots": data["screenshots"],
            "mock_html": data["mock_html"],
            "finalized": data["finalized"],
        }
        return session
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.warning("Malformed Designer session file: %s", path)
        return None


def save_session(session: DesignerSession, design_dir: Path) -> None:
    """Persist session to design_dir/session.json."""
    design_dir.mkdir(parents=True, exist_ok=True)
    (design_dir / "session.json").write_text(
        json.dumps(session, indent=2), encoding="utf-8"
    )


def save_mock(html: str, design_dir: Path) -> None:
    """Write mock HTML to design_dir/mock.html."""
    design_dir.mkdir(parents=True, exist_ok=True)
    (design_dir / "mock.html").write_text(html, encoding="utf-8")


def clear_session(design_dir: Path) -> None:
    """Delete session.json and mock.html from design_dir if they exist."""
    for name in ("session.json", "mock.html"):
        f = design_dir / name
        if f.exists():
            f.unlink()


def build_mock_prompt(
    session: DesignerSession,
    ui_source_snippets: list[str],
    image_support: bool,
) -> list[dict[str, object]]:
    """Construct the LiteLLM messages list for mock generation."""
    parts: list[dict[str, object]] = [
        {"type": "text", "text": session["preference_text"]},
    ]
    if image_support and session["screenshots"]:
        for shot in session["screenshots"]:
            parts.append({"type": "image_url", "image_url": {"url": shot["data"]}})
            parts.append({"type": "text", "text": f"Note: {shot['annotation']}"})
    if ui_source_snippets:
        combined = "\n\n".join(
            f"--- UI Source Snippet ---\n{s}" for s in ui_source_snippets
        )
        parts.append(
            {
                "type": "text",
                "text": (
                    "Existing UI code for reference (use as starting point):\n\n"
                    + combined
                ),
            }
        )
    parts.append({"type": "text", "text": _HTML_INSTRUCTION})
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": parts},
    ]
