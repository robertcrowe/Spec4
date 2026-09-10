"""Conversation-history surgery for the shared agent turn loop.

Every agent's ``run`` drives the same message list: replay the last assistant
turn on a resumed round, inject a staleness question or a resume summary when
the session came back changed, and drop the orphaned trailing user message a
cancelled turn leaves behind. Those edits are pure functions over
``msgs``/``session`` and live here; the prompts that surround them stay in each
agent (`SPEC4_CLEANUP_PLAN.md`, Phase 5: "Prompt text is never lifted").

Split out of ``_utils.py`` in Phase 4a; Phase 4j moved every importer here and
retired the ``_utils`` facade, so this module is now the one place these names
are imported from.
"""

from __future__ import annotations

import json
import re
from collections.abc import Generator
from typing import Any

from spec4 import project_manager
from spec4.agents._stack_context import design_manifest_for_stack, load_design_manifest


AGENT_DELIVERABLE: dict[str, str] = {
    "brainstormer": "the vision",
    "stack_advisor": "the stack recommendation",
    "phaser": "the phase plan",
    "deployer": "the deployment plan",
}


def extract_json_block(text: str) -> dict[str, Any] | None:
    """Extract and parse the first ```json {…} ``` block in text, or None."""
    match = re.search(r"```json\s*(\{.*\})\s*```", text, re.DOTALL)
    if match:
        try:
            result: dict[str, Any] = json.loads(match.group(1))
            return result
        except json.JSONDecodeError:
            return None
    return None


def replay_last_assistant(
    msgs: list[dict[str, Any]],
) -> Generator[str, None, None]:
    """Yield the last assistant message from msgs, if one exists."""
    for msg in reversed(msgs):
        if msg["role"] == "assistant":
            yield msg["content"]
            return


def last_assistant_text(msgs: list[dict[str, Any]]) -> str:
    """Return the content of the last assistant message in msgs, or ''."""
    return next(
        (m["content"] or "" for m in reversed(msgs) if m["role"] == "assistant"), ""
    )


def stale_phrase(stale: list[str]) -> str:
    """Format stale input names as 'X', 'X and Y', or 'X, Y, and Z'."""
    if not stale:
        return ""
    if len(stale) == 1:
        return stale[0]
    if len(stale) == 2:
        return f"{stale[0]} and {stale[1]}"
    return ", ".join(stale[:-1]) + f", and {stale[-1]}"


def build_revision_context(session: dict[str, Any], stale: list[str]) -> str:
    """Build a synthetic user message containing the latest upstream artifacts.

    Injected into the conversation history alongside the staleness question so
    the LLM has the new content available when the user asks for a revision.
    """
    parts: list[str] = [
        "[Spec4 system note: the following upstream inputs have been updated "
        "since I last produced my output. Use these latest versions if I ask "
        "you to revise.]"
    ]

    _revision_artifact_blocks(session, stale, parts)
    _revision_phase_blocks(session, stale, parts)
    _revision_design_blocks(session, stale, parts)

    return "\n\n".join(parts)


def _revision_artifact_blocks(
    session: dict[str, Any], stale: list[str], parts: list[str]
) -> None:
    """The four JSON artifact blocks: vision, AI features, stack, code review."""
    if "vision" in stale:
        v = session.get("vision_statement")
        if v is not None:
            parts.append(
                f"Updated vision statement:\n\n```json\n{json.dumps(v, indent=2)}\n```"
            )
    if "AI features" in stale:
        af = session.get("ai_features")
        if af is not None:
            parts.append(
                f"Updated AI features spec:\n\n```json\n{json.dumps(af, indent=2)}\n```"
            )
    if "stack" in stale:
        s = session.get("stack_statement")
        if s is not None:
            parts.append(
                f"Updated stack spec:\n\n```json\n{json.dumps(s, indent=2)}\n```"
            )
    if "code review" in stale:
        cr = session.get("code_review")
        if cr is not None:
            parts.append(
                f"Updated code review:\n\n```json\n{json.dumps(cr, indent=2)}\n```"
            )


def _revision_phase_blocks(
    session: dict[str, Any], stale: list[str], parts: list[str]
) -> None:
    """The phases block."""
    if "phases" in stale:
        ph = session.get("phases") or []
        if ph:
            phases_block = "\n\n".join(
                f"```json\n{json.dumps(p, indent=2)}\n```" for p in ph
            )
            parts.append(f"Updated phases:\n\n{phases_block}")


def _revision_design_blocks(
    session: dict[str, Any], stale: list[str], parts: list[str]
) -> None:
    """The design manifest and UI mock blocks, both read from the version dir."""
    if "design manifest" in stale:
        wd = session.get("working_dir")
        if wd:
            design_dir = (
                project_manager.get_version_dir(
                    wd, project_manager.active_version(wd, session)
                )
                / "design"
            )
            block = design_manifest_for_stack(load_design_manifest(design_dir))
            if block:
                parts.append("Updated design manifest:\n\n" + block)
    if "UI mock" in stale:
        wd = session.get("working_dir")
        if wd:
            mock_path = (
                project_manager.get_version_dir(
                    wd, project_manager.active_version(wd, session)
                )
                / "design"
                / "mock.html"
            )
            try:
                html = mock_path.read_text(encoding="utf-8", errors="replace")
                parts.append("Updated UI mock (HTML):\n\n```html\n" + html + "\n```")
            except OSError:
                pass


def maybe_inject_staleness_question(
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
    deliverable = AGENT_DELIVERABLE.get(agent, "the previous output")
    phrase = stale_phrase(stale_names)
    verb = "have" if len(stale_names) > 1 else "has"
    question = (
        f"I notice that {phrase} {verb} been updated since I last ran. Would "
        f"you like me to revise {deliverable}? "
        "(yes/no — you're also welcome to ask questions or share comments "
        "either way)"
    )
    messages.append(
        {"role": "user", "content": build_revision_context(session, stale_names)}
    )
    messages.append({"role": "assistant", "content": question})
    session[ack_key] = dict(stale)
    return question


def maybe_inject_resume_summary(
    session: dict[str, Any],
    agent: str,
    msgs: list[dict[str, Any]],
    complete_state: str,
) -> bool:
    """Append a "recap then continue" user prompt on the first re-entry of a session.

    Without this, navigating back to an in-progress agent replays the last
    assistant message verbatim — which is usually a mid-thought sentence
    (e.g. "Good. Now I understand how Vercel handles environment
    variables...") that reads as nonsense without the surrounding context.

    Returns True if a synthetic user message was appended (caller should
    fall through to the LLM call to produce the recap). Returns False if
    no action — caller should follow its normal replay branch.

    Skips when:
    - msgs is empty (fresh start, not a resume),
    - `session[f"{agent}_resumed"]` is truthy (already summarized once for
      this session-store lifetime), or
    - the agent has finished AND the user is still sitting on the
      just-written formatted-artifact message (i.e. `*_state == complete_state`
      and `len(msgs) == *_artifact_msg_count`). In that exact case, replay
      of the artifact text is the right behavior. If the user has chatted
      further past the artifact (revision mode after a brownfield reload),
      msgs has grown and the recap fires.

    The flag and the message-count snapshot both clear in
    `session.load_working_dir()`, so reloading the project directory
    triggers a fresh summary on the next visit.
    """
    if not msgs:
        return False
    if session.get(f"{agent}_resumed"):
        return False
    if session.get(f"{agent}_state") == complete_state and session.get(
        f"{agent}_artifact_msg_count"
    ) == len(msgs):
        return False
    msgs.append(
        {
            "role": "user",
            "content": (
                "[Spec4 system note: the developer is resuming this session "
                "after a break and has lost the chat context. Begin your "
                "reply with a brief recap (2-4 sentences) of what we have "
                "discussed and decided so far, then continue from where we "
                "left off — either by re-asking your most recent question "
                "or by moving on to the next topic. Do not output any "
                "final JSON artifact in this turn; the recap and next "
                "question is all that is needed."
            ),
        }
    )
    session[f"{agent}_resumed"] = True
    return True


def drop_orphan_trailing_user(msgs: list[dict[str, Any]]) -> int:
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


def drop_orphan_or_route_to_fresh_start(
    msgs: list[dict[str, Any]], user_input: str | None
) -> str | None:
    """Drop orphan trailing user messages, returning adjusted ``user_input``.

    Companion to :func:`drop_orphan_trailing_user` for callers that follow
    the standard ``if user_input is None: <fresh-start> else: append+LLM``
    dispatch. When dropping orphans empties ``msgs`` AND a ``user_input`` was
    supplied, the previous turn was interrupted before any assistant reply
    could be committed — so the carefully-built seed context (vision/stack/
    code review/etc.) is gone. Calling the LLM with only the new user reply
    would strip all that context and produce a hallucinated "I'm ready to
    help — please share your project info" greeting.

    In that case we return ``None`` so the caller routes through its
    fresh-start branch and re-seeds from session state. The user's reply is
    silently discarded (they were responding to text the agent never
    committed to ``msgs`` in the first place); the LLM re-emits its opening
    turn and the user can re-engage from a known-good state.

    Returns ``user_input`` unchanged in the common case.
    """
    if drop_orphan_trailing_user(msgs) and user_input is not None and not msgs:
        return None
    return user_input
