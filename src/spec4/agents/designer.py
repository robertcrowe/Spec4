from __future__ import annotations

import json
import logging
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TypedDict

import litellm

from spec4.tavily_mcp import WEB_SEARCH_TOOL, search as tavily_search

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

_SYSTEM_PROMPT_REFINE = (
    "You are an expert UI/UX designer. Your task is to modify an existing "
    "self-contained HTML mock-up based on the feedback provided. You write "
    "HTML, CSS, and JavaScript directly — no frameworks, no external assets, "
    "no CDN links. All CSS goes inside a <style> block in the <head> and all "
    "JavaScript goes inside a <script> block at the end of <body>. The output "
    "must be a single complete HTML document."
)

_HTML_INSTRUCTION = (
    "Generate a single self-contained HTML file for the landing page or "
    "starting screen. Place all CSS inside a <style> block in <head> and all "
    "JavaScript inside a <script> block at the bottom of <body>. Do not use "
    "external CDN links or import statements. "
    "Output ONLY the HTML document — no introduction, no explanation, no "
    "recap, no markdown commentary before or after the code."
)

_HTML_REFINEMENT_INSTRUCTION = (
    "Apply the requested changes to the existing mock shown above. Preserve "
    "everything not explicitly changed. Place all CSS inside a <style> block "
    "in <head> and all JavaScript inside a <script> block at the bottom of "
    "<body>. Do not use external CDN links or import statements. "
    "Output ONLY the complete updated HTML document — no introduction, no "
    "explanation, no recap, no markdown commentary before or after the code."
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
    planning_context: dict[str, Any] | None = None,
    existing_html: str | None = None,
) -> list[dict[str, object]]:
    """Construct the LiteLLM messages list for mock generation or refinement."""
    parts: list[dict[str, object]] = []

    if existing_html:
        parts.append({
            "type": "text",
            "text": (
                "## Existing Mock\n\n"
                "Below is the current HTML. Apply the requested changes to it — "
                "preserve everything not explicitly changed.\n\n"
                "```html\n" + existing_html + "\n```\n\n---"
            ),
        })
    elif planning_context and planning_context.get("vision_statement"):
        parts.append({
            "type": "text",
            "text": (
                "## Project Vision\n\n"
                "Use the following project vision to inform the UI design "
                "(purpose, audience, and key features):\n\n"
                + json.dumps(planning_context["vision_statement"], indent=2)
                + "\n\n---"
            ),
        })

    if session["preference_text"]:
        parts.append({"type": "text", "text": session["preference_text"]})
    if image_support and session["screenshots"]:
        for shot in session["screenshots"]:
            parts.append({"type": "image_url", "image_url": {"url": shot["data"]}})
            parts.append({"type": "text", "text": f"Note: {shot['annotation']}"})
    if not existing_html and ui_source_snippets:
        combined = "\n\n".join(
            f"--- UI Source Snippet ---\n{s}" for s in ui_source_snippets
        )
        parts.append({
            "type": "text",
            "text": "Existing UI code for reference (use as starting point):\n\n" + combined,
        })
    parts.append({"type": "text", "text": _HTML_REFINEMENT_INSTRUCTION if existing_html else _HTML_INSTRUCTION})
    return [
        {"role": "system", "content": _SYSTEM_PROMPT_REFINE if existing_html else _SYSTEM_PROMPT},
        {"role": "user", "content": parts},
    ]


_UI_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".html",
        ".htm",
        ".css",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".jinja",
        ".jinja2",
        ".j2",
        ".svelte",
        ".vue",
    }
)
_EXCLUDED_DIRS: frozenset[str] = frozenset(
    {".spec4", ".git", "__pycache__", "node_modules", "dist", ".venv"}
)
_MAX_UI_FILES = 20


def collect_ui_source_files(
    project_root: Path,
    max_chars_per_file: int = 8000,
) -> list[str]:
    result: list[str] = []
    for root, dirs, files in project_root.walk():
        dirs[:] = sorted(d for d in dirs if d not in _EXCLUDED_DIRS)
        for fname in sorted(files):
            if Path(fname).suffix.lower() not in _UI_EXTENSIONS:
                continue
            fpath = root / fname
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if len(content) > max_chars_per_file:
                content = content[:max_chars_per_file] + "\n# [truncated]"
            rel = fpath.relative_to(project_root)
            result.append(f"# --- {rel} ---\n{content}")
            if len(result) >= _MAX_UI_FILES:
                return result
    return result


def generate_mock_streaming(
    session: DesignerSession,
    model: str,
    api_key: str,
    ui_source_snippets: list[str],
    image_support: bool,
    tavily_api_key: str | None = None,
    stop_event: threading.Event | None = None,
    planning_context: dict[str, Any] | None = None,
    existing_html: str | None = None,
) -> Iterator[str]:
    messages: list[dict[str, Any]] = build_mock_prompt(
        session, ui_source_snippets, image_support, planning_context, existing_html
    )
    tools: list[dict[str, Any]] | None = [WEB_SEARCH_TOOL] if tavily_api_key else None

    print("[Designer] Sending input to model...", flush=True)
    yield "__DBG_INPUT_START__"

    first_call = True
    first_token = True

    try:
        while True:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "api_key": api_key,
                "stream": True,
            }
            if tools:
                kwargs["tools"] = tools

            response = litellm.completion(**kwargs)

            if first_call:
                print("[Designer] Input sent — awaiting first output token", flush=True)
                yield "__DBG_INPUT_END__"
                first_call = False

            full_text = ""
            tool_call_acc: dict[int, dict[str, str]] = {}
            chunk_count = 0
            last_finish_reason = None

            for chunk in response:
                chunk_count += 1
                if stop_event is not None and stop_event.is_set():
                    return

                choice = chunk.choices[0] if chunk.choices else None
                if choice is None:
                    print(f"[Designer] Chunk {chunk_count}: no choices", flush=True)
                    continue

                last_finish_reason = getattr(choice, "finish_reason", None)
                delta = choice.delta
                content = getattr(delta, "content", None) or ""
                tc_deltas = getattr(delta, "tool_calls", None)

                if chunk_count <= 3 or tc_deltas:
                    print(
                        f"[Designer] Chunk {chunk_count}: content={content!r} "
                        f"tool_calls={bool(tc_deltas)} finish_reason={last_finish_reason}",
                        flush=True,
                    )

                if content:
                    if first_token:
                        print("[Designer] First output token received", flush=True)
                        yield "__DBG_OUTPUT_START__"
                        first_token = False
                    full_text += content
                    print(content, end="", flush=True)
                    yield content

                if tc_deltas:
                    for tc in tc_deltas:
                        i = tc.index
                        if i not in tool_call_acc:
                            tool_call_acc[i] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_call_acc[i]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_call_acc[i]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_call_acc[i]["arguments"] += tc.function.arguments

            print(
                f"[Designer] Iteration complete — {chunk_count} chunks, "
                f"finish_reason={last_finish_reason}",
                flush=True,
            )

            if tool_call_acc:
                messages.append({
                    "role": "assistant",
                    "content": full_text or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        }
                        for tc in tool_call_acc.values()
                    ],
                })
                for tc in tool_call_acc.values():
                    print(
                        f"[Designer] Tool call: {tc['name']} args={tc['arguments']}",
                        flush=True,
                    )
                    if tc["name"] == "web_search":
                        try:
                            query = json.loads(tc["arguments"]).get("query", "")
                        except (json.JSONDecodeError, KeyError):
                            query = tc["arguments"]
                        print(f"[Designer] Web search: {query!r}", flush=True)
                        result = tavily_search(query, tavily_api_key or "")
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        })
                continue

            break

        print("[Designer] Output complete", flush=True)
        yield "__DONE__"

    except Exception as exc:
        print(f"[Designer] Generation error: {exc}", flush=True)
        yield f"__GENERATION_ERROR__: {exc}"
