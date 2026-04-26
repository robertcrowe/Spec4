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
