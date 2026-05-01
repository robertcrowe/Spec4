from __future__ import annotations

import json
import re
import threading
import uuid
from collections.abc import Generator
from typing import Any

_STREAMS: dict[str, dict[str, Any]] = {}


def _format_error(exc: BaseException) -> str:
    msg = str(exc)
    # litellm wraps API error bodies as b'{"..."}' — extract and pretty-print the JSON.
    m = re.search(r"b'(\{.*\})'", msg, re.DOTALL)
    if m:
        try:
            pretty = json.dumps(json.loads(m.group(1)), indent=2)
            prefix = msg[: m.start()].rstrip(" -")
            return f"**Error:** {prefix}\n\n```json\n{pretty}\n```"
        except json.JSONDecodeError:
            pass
    # Fallback: try the whole message as JSON.
    try:
        pretty = json.dumps(json.loads(msg), indent=2)
        return f"**Error:**\n\n```json\n{pretty}\n```"
    except json.JSONDecodeError:
        pass
    return f"**Error:** {msg}"


def _format_error(exc: BaseException) -> str:
    msg = str(exc)
    # litellm wraps API error bodies as b'{"..."}' — extract and pretty-print the JSON.
    m = re.search(r"b'(\{.*\})'", msg, re.DOTALL)
    if m:
        try:
            pretty = json.dumps(json.loads(m.group(1)), indent=2)
            prefix = msg[: m.start()].rstrip(" -")
            return f"**Error:** {prefix}\n\n```json\n{pretty}\n```"
        except json.JSONDecodeError:
            pass
    # Fallback: try the whole message as JSON.
    try:
        pretty = json.dumps(json.loads(msg), indent=2)
        return f"**Error:**\n\n```json\n{pretty}\n```"
    except json.JSONDecodeError:
        pass
    return f"**Error:** {msg}"


def start(gen: Generator[str, None, None], session: dict[str, Any]) -> str:
    """Exhaust gen in a background thread, accumulating text. Returns stream_id."""
    stream_id = str(uuid.uuid4())
    entry: dict[str, Any] = {"text": "", "done": False, "session": session}
    with _lock:
        _STREAMS[stream_id] = entry

    def _run() -> None:
        try:
            for chunk in gen:
                _STREAMS[stream_id]["text"] += chunk
        except Exception as exc:
            _STREAMS[stream_id]["text"] += _format_error(exc)
        finally:
            with _lock:
                entry["done"] = True

    threading.Thread(target=_run, daemon=True).start()
    return stream_id


def get(stream_id: str) -> dict[str, Any] | None:
    with _lock:
        return _STREAMS.get(stream_id)


def pop(stream_id: str) -> dict[str, Any] | None:
    with _lock:
        return _STREAMS.pop(stream_id, None)
