from __future__ import annotations

import json
import os
import re
import traceback
from collections.abc import Generator
from pathlib import Path
from typing import Any

from spec4 import project_manager

_DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"

_AGENT_DELIVERABLE: dict[str, str] = {
    "brainstormer": "the vision",
    "stack_advisor": "the stack recommendation",
    "phaser": "the phase plan",
    "deployer": "the deployment plan",
}


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


def _stale_phrase(stale: list[str]) -> str:
    """Format stale input names as 'X', 'X and Y', or 'X, Y, and Z'."""
    if not stale:
        return ""
    if len(stale) == 1:
        return stale[0]
    if len(stale) == 2:
        return f"{stale[0]} and {stale[1]}"
    return ", ".join(stale[:-1]) + f", and {stale[-1]}"


def _build_revision_context(
    session: dict[str, Any], stale: list[str]
) -> str:
    """Build a synthetic user message containing the latest upstream artifacts.

    Injected into the conversation history alongside the staleness question so
    the LLM has the new content available when the user asks for a revision.
    """
    parts: list[str] = [
        "[Spec4 system note: the following upstream inputs have been updated "
        "since I last produced my output. Use these latest versions if I ask "
        "you to revise.]"
    ]
    if "vision" in stale:
        v = session.get("vision_statement")
        if v is not None:
            parts.append(
                "Updated vision statement:\n\n"
                f"```json\n{json.dumps(v, indent=2)}\n```"
            )
    if "stack" in stale:
        s = session.get("stack_statement")
        if s is not None:
            parts.append(
                "Updated stack spec:\n\n"
                f"```json\n{json.dumps(s, indent=2)}\n```"
            )
    if "code review" in stale:
        cr = session.get("code_review")
        if cr is not None:
            parts.append(
                "Updated code review:\n\n"
                f"```json\n{json.dumps(cr, indent=2)}\n```"
            )
    if "phases" in stale:
        ph = session.get("phases") or []
        if ph:
            phases_block = "\n\n".join(
                f"```json\n{json.dumps(p, indent=2)}\n```" for p in ph
            )
            parts.append(f"Updated phases:\n\n{phases_block}")
    if "UI mock" in stale:
        wd = session.get("working_dir")
        if wd:
            mock_path = Path(wd) / ".spec4" / "design" / "mock.html"
            try:
                html = mock_path.read_text(encoding="utf-8", errors="replace")
                parts.append(
                    "Updated UI mock (HTML):\n\n```html\n" + html + "\n```"
                )
            except OSError:
                pass
    return "\n\n".join(parts)


def _maybe_inject_staleness_question(
    session: dict[str, Any],
    agent: str,
    messages: list[dict[str, Any]],
) -> str | None:
    """Append a staleness-revision question pair if upstream inputs are stale.

    Detects upstream artifacts whose mtime is newer than `agent`'s output. If
    any are detected and have not already been asked about at their current
    mtime, appends a synthetic user message with the latest artifact content
    plus an assistant question asking whether to revise. Returns the question
    text for the caller to yield, or None if no question is needed.
    """
    working_dir = session.get("working_dir")
    if not working_dir:
        return None
    stale = project_manager.detect_stale_inputs(working_dir, agent)
    if not stale:
        return None
    ack_key = f"{agent}_stale_acknowledged"
    acknowledged: dict[str, float] = session.get(ack_key) or {}
    # Re-ask only if a stale input has a newer mtime than what we last asked
    # about — handles "user updated the same upstream artifact again."
    if all(acknowledged.get(name) == mtime for name, mtime in stale.items()):
        return None
    stale_names = list(stale)
    deliverable = _AGENT_DELIVERABLE.get(agent, "the previous output")
    phrase = _stale_phrase(stale_names)
    verb = "have" if len(stale_names) > 1 else "has"
    question = (
        f"I notice that {phrase} {verb} been updated since I last ran. Would "
        f"you like me to revise {deliverable}? "
        "(yes/no — you're also welcome to ask questions or share comments "
        "either way)"
    )
    messages.append(
        {"role": "user", "content": _build_revision_context(session, stale_names)}
    )
    messages.append({"role": "assistant", "content": question})
    session[ack_key] = dict(stale)
    return question


def _drop_orphan_trailing_user(msgs: list[dict[str, Any]]) -> int:
    """Remove trailing non-assistant messages left over from an interrupted turn.

    When an LLM call raises mid-stream (rate limit, network error, etc.) the
    agent has already appended its user/tool message to msgs but no assistant
    reply gets recorded. On the next entry the replay branch then finds no
    assistant to yield (silent stuck UI), and resubmitting would produce two
    consecutive user messages that Anthropic and others reject.

    Pops trailing entries until msgs ends with an assistant turn or is empty.
    Returns the number of entries removed (caller can log it in dev mode).
    """
    removed = 0
    while msgs and msgs[-1].get("role") != "assistant":
        msgs.pop()
        removed += 1
    return removed


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
    received = 0
    if _DEV_MODE:
        print("[suppress] entering", flush=True)
    try:
        for chunk in chunks:
            received += 1
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
    except BaseException as exc:
        if _DEV_MODE:
            print(
                f"[suppress] EXCEPTION after {received} chunks "
                f"(suppress={suppress}, flushed={flushed}, buf_len={len(buf)}): "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
            traceback.print_exc()
        raise
    finally:
        if _DEV_MODE:
            print(
                f"[suppress] exit: received={received} suppress={suppress} "
                f"flushed={flushed}",
                flush=True,
            )


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
