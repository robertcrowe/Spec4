from __future__ import annotations

import threading
import uuid
from collections.abc import Generator
from typing import Any

_STREAMS: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def start(gen: Generator[str, None, None], session: dict[str, Any]) -> str:
    """Exhaust gen in a background thread, accumulating text. Returns stream_id."""
    stream_id = str(uuid.uuid4())
    entry: dict[str, Any] = {"text": "", "done": False, "session": session}
    with _lock:
        _STREAMS[stream_id] = entry

    def _run() -> None:
        try:
            for chunk in gen:
                with _lock:
                    entry["text"] += chunk
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
