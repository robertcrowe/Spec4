from __future__ import annotations

import json
import re
from collections.abc import Generator
from typing import Any


def _extract_json_block(text: str) -> dict[str, Any] | None:
    """Extract and parse the first ```json {…} ``` block in text, or None."""
    match = re.search(r"```json\s*(\{.*\})\s*```", text, re.DOTALL)
    if match:
        try:
            result: dict[str, Any] = json.loads(match.group(1))
            return result
        except json.JSONDecodeError:
            return None
    return None


def _replay_last_assistant(
    msgs: list[dict[str, Any]],
) -> Generator[str, None, None]:
    """Yield the last assistant message from msgs, if one exists."""
    for msg in reversed(msgs):
        if msg["role"] == "assistant":
            yield msg["content"]
            return


def _last_assistant_text(msgs: list[dict[str, Any]]) -> str:
    """Return the content of the last assistant message in msgs, or ''."""
    return next(
        (m["content"] or "" for m in reversed(msgs) if m["role"] == "assistant"), ""
    )


def _stream_suppressing_json(
    chunks: Generator[str, None, None],
) -> Generator[str, None, None]:
    """Yield chunks, suppressing the entire response if it starts with a fence.

    When the LLM outputs its final JSON artifact the response begins with ```
    (possibly after leading whitespace). Suppressing it prevents raw JSON from
    appearing in the chat window; the caller replaces it via _display_override.
    """
    _FENCE = "```"
    buf = ""
    flushed = False
    suppress = False
    for chunk in chunks:
        if flushed:
            yield chunk
        elif suppress:
            pass
        else:
            buf += chunk
            stripped = buf.lstrip()
            if stripped.startswith(_FENCE):
                suppress = True
            elif len(stripped) >= len(_FENCE):
                flushed = True
                yield buf
                buf = ""
    if not suppress and not flushed and buf:
        yield buf


def _render_references(refs: list[dict[str, str]], lines: list[str]) -> None:
    """Append a **References:** section to lines in-place. No-op if refs is empty."""
    if not refs:
        return
    lines.append("**References:**")
    for ref in refs:
        standard = ref.get("standard", "")
        url = ref.get("url", "")
        lines.append(f"- {standard}: {url}" if url else f"- {standard}")
    lines.append("")


def _render_coding_style(style: dict[str, Any], lines: list[str]) -> None:
    """Append a **Coding Style:** section to lines in-place. No-op if style is empty."""
    if not style:
        return
    lines.append("**Coding Style:**")
    for key in ("linter", "formatter", "type_checker", "indentation", "line_length", "quotes"):
        if key in style:
            lines.append(f"- {key.replace('_', ' ').title()}: {style[key]}")
    naming: dict[str, str] = style.get("naming_conventions", {})
    if naming:
        naming_str = ", ".join(f"{k}: {v}" for k, v in naming.items())
        lines.append(f"- Naming: {naming_str}")
    other_rules: list[str] = style.get("other_rules", [])
    if other_rules:
        lines.append(f"- Other rules: {'; '.join(other_rules)}")
    patterns: list[str] = style.get("patterns", [])
    if patterns:
        lines.append(f"- Patterns: {'; '.join(patterns)}")
    lines.append("")
