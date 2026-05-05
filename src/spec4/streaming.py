from __future__ import annotations

import json
import os
import re
import threading
import traceback
import uuid
from collections.abc import Generator
from typing import Any

_STREAMS: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

_DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"


def _extract_json_body(raw: str) -> tuple[Any, str]:
    """Pull a JSON body out of an error string. Returns (parsed_or_None, prefix)."""
    # litellm/SDKs commonly stringify the response body as b'{...}' or b"{...}".
    for quote in ("'", '"'):
        m = re.search(rf"b{quote}(\{{.*\}}){quote}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1)), raw[: m.start()].rstrip(" -:")
            except json.JSONDecodeError:
                continue
    # Whole message might be JSON.
    stripped = raw.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            return json.loads(stripped), ""
        except json.JSONDecodeError:
            pass
    return None, raw


def _strip_redundant_prefix(prefix: str) -> str:
    """Remove litellm's doubled "Foo: Foo:" prefix and any leading "litellm.X:" leader.

    The heading already shows the real exception class, so a `litellm.<Class>:` leader
    in the prefix only adds noise — strip it regardless of whether it matches the
    outer class.
    """
    p = re.sub(r"^(\S+):\s*\1:\s*", r"\1: ", prefix.strip())
    p = re.sub(r"^litellm\.\S+?:\s*", "", p)
    return p.rstrip(" -:").strip()


def _walk_str(payload: Any, *paths: tuple[str, ...]) -> str | None:
    """Walk dotted-path tuples through nested dicts; return first str value found."""
    for path in paths:
        cur: Any = payload
        for key in path:
            if not isinstance(cur, dict):
                cur = None
                break
            cur = cur.get(key)
        if isinstance(cur, str) and cur.strip():
            return cur
    return None


def _extract_message(payload: Any) -> str | None:
    return _walk_str(
        payload,
        ("error", "message"),         # OpenAI, Google, Mistral
        ("error", "error", "message"),  # Some doubly-wrapped responses
        ("message",),                 # Cohere, plain envelopes
        ("detail",),                  # FastAPI-style
        ("error",),                   # Some providers stuff a plain str under "error"
    )


def _extract_status(payload: Any) -> str | None:
    return _walk_str(
        payload,
        ("error", "status"),          # Google: RESOURCE_EXHAUSTED, INVALID_ARGUMENT
        ("error", "type"),            # OpenAI: invalid_request_error
        ("error", "error", "type"),   # Anthropic: rate_limit_error
        ("type",),
    )


def _extract_code(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    err = payload.get("error")
    candidates: list[Any] = []
    if isinstance(err, dict):
        candidates.append(err.get("code"))
        if isinstance(err.get("error"), dict):
            candidates.append(err["error"].get("code"))
    candidates.append(payload.get("code"))
    for c in candidates:
        if c is None or c == "":
            continue
        return str(c)
    return None


def _extract_retry(payload: Any, message: str) -> str | None:
    """Best-effort retry-after — Google's details list, or a mention in prose."""
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            details = err.get("details")
            if isinstance(details, list):
                for d in details:
                    if not isinstance(d, dict):
                        continue
                    if "RetryInfo" in str(d.get("@type", "")):
                        delay = d.get("retryDelay")
                        if isinstance(delay, str) and delay.strip():
                            return delay
    m = re.search(r"retry in ([\d.]+\s*s(?:ec(?:onds?)?)?)\b", message, re.IGNORECASE)
    return m.group(1) if m else None


def _extract_doc_links(payload: Any) -> list[str]:
    out: list[str] = []
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            details = err.get("details")
            if isinstance(details, list):
                for d in details:
                    if not isinstance(d, dict) or "Help" not in str(d.get("@type", "")):
                        continue
                    links = d.get("links")
                    items = links if isinstance(links, list) else [links]
                    for ln in items:
                        if isinstance(ln, dict) and isinstance(ln.get("url"), str):
                            out.append(ln["url"])
    seen: set[str] = set()
    deduped: list[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


def _dedupe_consecutive_lines(text: str) -> str:
    out: list[str] = []
    prev: str | None = None
    for line in text.splitlines():
        s = line.strip()
        if s and s == prev:
            continue
        out.append(line)
        prev = s
    return "\n".join(out)


def _format_error(exc: BaseException) -> str:
    raw = str(exc)
    cls_name = type(exc).__name__
    payload, prefix = _extract_json_body(raw)
    prefix = _strip_redundant_prefix(prefix)

    # No parsable JSON — present what we have as plain text.
    if payload is None:
        body = " ".join(raw.split()) or repr(exc)
        return f"**Error: {cls_name}**\n\n{body}"

    message = _extract_message(payload)
    status = _extract_status(payload)
    code = _extract_code(payload)

    # Structure parsed but no message extracted — keep the raw JSON as a debugging aid.
    if not message:
        try:
            pretty = json.dumps(payload, indent=2)
        except (TypeError, ValueError):
            pretty = str(payload)
        head = f"**Error: {cls_name}**"
        if prefix:
            head += f" — {prefix}"
        return f"{head}\n\n```json\n{pretty}\n```"

    badge_parts = [f"HTTP {code}" if code else None, status]
    badge = " · ".join(b for b in badge_parts if b)
    head = f"**Error: {cls_name}**" + (f" ({badge})" if badge else "")

    body = _dedupe_consecutive_lines(message).strip()
    # Preserve original line breaks under CommonMark (two trailing spaces = hard break).
    body = body.replace("\n", "  \n")

    bullets: list[str] = []
    retry = _extract_retry(payload, message)
    if retry:
        bullets.append(f"Retry after: {retry}")
    for url in _extract_doc_links(payload):
        if url not in message:
            bullets.append(f"Docs: {url}")
    if prefix:
        bullets.append(f"Source: {prefix}")

    parts = [head, "", body]
    if bullets:
        parts.append("")
        parts.extend(f"- {b}" for b in bullets)
    return "\n".join(parts)


def start(gen: Generator[str, None, None], session: dict[str, Any]) -> str:
    """Exhaust gen in a background thread, accumulating text. Returns stream_id."""
    stream_id = str(uuid.uuid4())
    entry: dict[str, Any] = {"text": "", "done": False, "session": session}
    with _lock:
        _STREAMS[stream_id] = entry
    short = stream_id[:8]
    if _DEV_MODE:
        print(f"[stream {short}] started", flush=True)

    def _run() -> None:
        chunks = 0
        try:
            for chunk in gen:
                chunks += 1
                _STREAMS[stream_id]["text"] += chunk
            if _DEV_MODE:
                print(
                    f"[stream {short}] generator exhausted cleanly, "
                    f"chunks={chunks}, text_len={len(_STREAMS[stream_id]['text'])}",
                    flush=True,
                )
        except Exception as exc:
            formatted = _format_error(exc)
            _STREAMS[stream_id]["text"] += formatted
            if _DEV_MODE:
                print(
                    f"[stream {short}] EXCEPTION after {chunks} chunks: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
                traceback.print_exc()
                print(
                    f"[stream {short}] formatted error written to text "
                    f"({len(formatted)} chars); text_len now "
                    f"{len(_STREAMS[stream_id]['text'])}",
                    flush=True,
                )
        finally:
            with _lock:
                entry["done"] = True
            if _DEV_MODE:
                print(f"[stream {short}] done=True", flush=True)

    threading.Thread(target=_run, daemon=True).start()
    return stream_id


def get(stream_id: str) -> dict[str, Any] | None:
    with _lock:
        return _STREAMS.get(stream_id)


def pop(stream_id: str) -> dict[str, Any] | None:
    with _lock:
        return _STREAMS.pop(stream_id, None)
