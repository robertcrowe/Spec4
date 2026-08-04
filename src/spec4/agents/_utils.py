from __future__ import annotations

import json
import os
import re
from collections.abc import Generator
from pathlib import Path
from typing import Any

from spec4 import project_manager
from spec4.design_manifest import surface_summary_line
from spec4.stack_routing import (
    ROADMAP_STATUSES,
    derived_nfr_ids,
    stack_signal_entries,
)
from spec4.agentifier.infra_expander import INFRA_KIND
from spec4.feature_specs import (
    DESIGNER_SPEC_FIELDS,
    PHASER_PRODUCT_SPEC_FIELDS,
    STACK_SPEC_FIELDS,
    render_cross_cutting,
    render_feature_block,
)

_DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"

_AGENT_DELIVERABLE: dict[str, str] = {
    "brainstormer": "the vision",
    "stack_advisor": "the stack recommendation",
    "phaser": "the phase plan",
    "deployer": "the deployment plan",
}


def slug(name: str) -> str:
    """Canonical feature-id derivation shared across the pipeline.

    ``id = slug(name)`` — lowercase, with every character outside ``[a-z0-9_]``
    collapsed to ``_``. This mirrors the derivation already used by the
    Agentifier feature builder (``agentifier.py``) and the Phaser coverage check
    (``_phase_coverage._slug``), so a feature's Brainstormer-assigned id and its
    Agentifier id coincide by construction on matching names — the join key the
    downstream agents key off. Empty input yields ``""``.
    """
    return re.sub(r"[^a-z0-9_]", "_", name.lower()) if name else ""


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
    if "AI features" in stale:
        af = session.get("ai_features")
        if af is not None:
            parts.append(
                "Updated AI features spec:\n\n"
                f"```json\n{json.dumps(af, indent=2)}\n```"
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
    if "design manifest" in stale:
        wd = session.get("working_dir")
        if wd:
            design_dir = (
                project_manager.get_version_dir(
                    wd, project_manager.active_version(wd, session)
                )
                / "design"
            )
            block = _design_manifest_for_stack(_load_design_manifest(design_dir))
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


def _maybe_inject_resume_summary(
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
    `session._load_working_dir()`, so reloading the project directory
    triggers a fresh summary on the next visit.
    """
    if not msgs:
        return False
    if session.get(f"{agent}_resumed"):
        return False
    if (
        session.get(f"{agent}_state") == complete_state
        and session.get(f"{agent}_artifact_msg_count") == len(msgs)
    ):
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


def _drop_orphan_or_route_to_fresh_start(
    msgs: list[dict[str, Any]], user_input: str | None
) -> str | None:
    """Drop orphan trailing user messages, returning adjusted ``user_input``.

    Companion to :func:`_drop_orphan_trailing_user` for callers that follow
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
    if _drop_orphan_trailing_user(msgs) and user_input is not None and not msgs:
        return None
    return user_input


def _suppressed_as_artifact(text: str) -> bool:
    """True when ``_stream_suppressing_json`` would swallow this reply whole.

    The suppression rule is "the response opens with a fence", and the two
    places that care about it must not drift: the generator applies it while
    streaming, and the agents apply it afterwards to tell an artifact turn that
    failed to parse (developer saw nothing) from ordinary conversation
    (developer saw the reply). Sharing the predicate keeps them in lockstep.
    """
    return text.lstrip().startswith("```")


def _artifact_reask_prompt(artifact: str) -> str:
    """Corrective user message for an artifact block that could not be read.

    Deliberately asks for a fenced block rather than bare JSON: the extractors
    that will read the reply look for a fence, and an agent that re-asks in a
    shape its own extractor rejects has only moved the failure.
    """
    return (
        f"The JSON block you just emitted could not be read — it was malformed, "
        f"or truncated before its closing fence. Re-emit the complete "
        f"{artifact} as a single fenced ```json``` block and nothing else: no "
        f"preface, no summary, no commentary after it."
    )


def _artifact_reask_status(artifact: str) -> str:
    """The one line the developer sees while the silent re-ask runs."""
    return f"\n\n_The {artifact} didn't come through cleanly — asking again…_\n"


def _artifact_fallback(artifact: str) -> str:
    """Recoverable message for when the re-ask fails too.

    The turn has to end with something on screen. Naming the next move matters:
    the agent is still in conversation, so the developer can simply ask again.
    """
    return (
        f"I tried to emit the structured {artifact} but it didn't come back in "
        f"a usable form. Reply 'try again' and I'll re-emit it, or tell me what "
        f"to change first."
    )


def _reask_for_artifact(
    *,
    system: str,
    msgs: list[dict[str, Any]],
    llm_config: dict[str, Any],
    search_config: Any,
    agent_name: str,
    correction: str,
    status_line: str,
    response_format: dict[str, Any] | None = None,
    session: dict[str, Any] | None = None,
    seed: int = 0,
) -> Generator[str, None, None]:
    """Ask the model once more for an artifact it failed to emit usably.

    Appends ``correction`` to ``msgs``, yields ``status_line`` so the turn is not
    silent, then drains the reply without yielding it — the body is the artifact
    block itself, which the developer must never see raw. ``stream_turn`` records
    the reply on ``msgs``, so the caller re-extracts from there afterwards, and
    calls :func:`_abandon_reask` if it is still unusable.

    ``seed`` is the characters already received this turn. Publishing the running
    total onto ``session`` keeps the chars counter climbing through the drain
    (D-PH9 / D-SC-P1) instead of freezing for its duration.
    """
    # Imported here rather than at module scope: `_utils` is the shared leaf that
    # every agent imports, and pulling the litellm/mcp stack in at its import time
    # would make that cost unconditional for callers that never re-ask.
    from spec4 import llm

    msgs.append({"role": "user", "content": correction})
    yield status_line
    received = seed + len(status_line)
    if session is not None:
        session["_stream_received_chars"] = received
    for chunk in llm.stream_turn(
        system,
        msgs,
        llm_config,
        search_config,
        agent_name=agent_name,
        response_format=response_format,
    ):
        if chunk and session is not None:
            received += len(chunk)
            session["_stream_received_chars"] = received


def _abandon_reask(
    msgs: list[dict[str, Any]],
    correction: str,
    fallback: str,
    session: dict[str, Any],
) -> None:
    """Give up on the artifact, leaving the conversation in a usable state.

    Drops the synthesized correction exchange so the history does not carry a
    dead-end user turn the developer never wrote, and replaces the unreadable
    reply with ``fallback`` — both in the history and, via ``_display_override``,
    on screen. Without the override the turn ends showing the suppressed reply's
    empty bubble, which is the failure this whole path exists to prevent.
    """
    if (
        len(msgs) >= 2
        and msgs[-2].get("role") == "user"
        and msgs[-2].get("content") == correction
    ):
        del msgs[-2:]
    if msgs and msgs[-1].get("role") == "assistant":
        msgs[-1]["content"] = fallback
    else:
        msgs.append({"role": "assistant", "content": fallback})
    session["_display_override"] = fallback


def _stream_suppressing_json(
    chunks: Generator[str, None, None],
    session: dict[str, Any] | None = None,
    seed: int = 0,
) -> Generator[str, None, None]:
    """Yield chunks, suppressing the entire response if it starts with a fence.

    When the LLM outputs its final JSON artifact the response begins with ```
    (possibly after leading whitespace). Suppressing it prevents raw JSON from
    appearing in the chat window; the caller replaces it via _display_override.

    D-SC60: that suppression is precisely why the chat token counter's
    displayed-character fallback cannot work on an artifact turn — nothing is
    ever yielded, so the visible assistant message never grows and the counter
    reads 0 for the whole multi-minute draw. Suppression is owned here, so the
    correction belongs here too. When a ``session`` is supplied, publish a
    cumulative received-character total onto it (the same shared dict the poll
    reads as ``stream["session"]``, and which it threads into the counter), so
    the counter tracks real receipt rather than displayed text. This is the same
    remedy D-PH9 applied to the phaser validation-retry drain. Callers that pass
    no session keep the previous behaviour exactly.

    D-AT3: ``seed`` is the number of characters the caller already yielded in
    this turn before opening the stream. The counter reads the published total
    in preference to the displayed message length, so a caller that yielded
    progress text first (Agentifier's tier-analysis loop) would otherwise see
    the counter drop to zero the moment the stream opens. Seeding with that
    text's length keeps the count monotonic within a turn. Defaults to 0, which
    is the prior behaviour.
    """
    _FENCE = "```"
    buf = ""
    flushed = False
    suppress = False
    received = 0
    received_chars = seed
    if session is not None:
        # Seed the turn at the caller's pre-stream total (0 unless supplied) so
        # a stale total from a prior turn cannot be read as this turn's
        # progress before the first chunk lands.
        session["_stream_received_chars"] = seed
    if _DEV_MODE:
        print("[suppress] entering", flush=True)
    try:
        for chunk in chunks:
            received += 1
            if session is not None and chunk:
                received_chars += len(chunk)
                session["_stream_received_chars"] = received_chars
            if flushed:
                yield chunk
            elif suppress:
                pass
            else:
                buf += chunk
                stripped = buf.lstrip()
                if _suppressed_as_artifact(buf):
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
        raise
    finally:
        if _DEV_MODE:
            print(
                f"[suppress] exit: received={received} suppress={suppress} "
                f"flushed={flushed}",
                flush=True,
            )


def _stream_counting(
    chunks: Generator[str, None, None],
    session: dict[str, Any],
    seed: int = 0,
) -> Generator[str, None, int]:
    """Yield chunks unchanged, publishing a running received-character total.

    The pass-through counterpart to :func:`_stream_suppressing_json`, for agents
    whose replies reach the screen verbatim (Deployer). The chars counter falls
    back to the length of the in-flight assistant message when nothing is
    published, and for a verbatim reply that fallback is accurate — but only
    while the turn is one stream that yields exactly what the message holds.
    Deployer's greenfield README beat is neither: it yields an authoring note
    between two ``stream_turn`` calls, and the second call starts a fresh
    assistant message, so the fallback counter drops back to zero mid-turn.
    Publishing a cumulative total keeps it monotonic, and leaves the counter
    correct if a suppressed artifact turn is ever added here (D-SC60).

    Returns the running total so a caller with several streams in one turn can
    seed the next from it: ``received = yield from _stream_counting(...)``.
    """
    received = seed
    # Publish before the first chunk so a stale total from the previous turn
    # cannot be read as this turn's progress (as in _stream_suppressing_json).
    session["_stream_received_chars"] = received
    for chunk in chunks:
        if chunk:
            received += len(chunk)
            session["_stream_received_chars"] = received
        yield chunk
    return received


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


_STYLE_LEAF_KEYS = (
    "linter",
    "formatter",
    "type_checker",
    "type_checking",
    "language",
    "indentation",
    "line_length",
    "quotes",
)


def _render_one_style(style: dict[str, Any], lines: list[str], indent: str = "") -> None:
    """Append one style block's fields. Shared by the flat and nested shapes."""
    for key in _STYLE_LEAF_KEYS:
        if key in style:
            lines.append(f"{indent}- {key.replace('_', ' ').title()}: {style[key]}")
    naming: dict[str, str] = style.get("naming_conventions", {})
    if naming:
        naming_str = ", ".join(f"{k}: {v}" for k, v in naming.items())
        lines.append(f"{indent}- Naming: {naming_str}")
    other_rules: list[str] = style.get("other_rules", [])
    if other_rules:
        lines.append(f"{indent}- Other rules: {'; '.join(other_rules)}")
    patterns: list[str] = style.get("patterns", [])
    if patterns:
        lines.append(f"{indent}- Patterns: {'; '.join(patterns)}")


def _render_coding_style(style: dict[str, Any], lines: list[str]) -> None:
    """Append a **Coding Style:** section to lines in-place. No-op if style is empty.

    Handles both shapes the model emits (D-SC23). A single-language project gives a
    flat block; a two-language one nests by tier — ``{"backend": {...}, "frontend":
    {...}}`` or ``{"python": {...}, "typescript": {...}}``. Probing only for flat
    keys printed the heading and nothing else, so a developer who had just
    negotiated linter, formatter, type checker, naming and patterns across two
    turns saw an empty section.
    """
    if not style:
        return
    lines.append("**Coding Style:**")
    if any(k in style for k in (*_STYLE_LEAF_KEYS, "naming_conventions", "patterns")):
        _render_one_style(style, lines)
    else:
        for tier, sub in style.items():
            label = str(tier).replace("_", " ").title()
            if isinstance(sub, dict):
                lines.append(f"- {label}:")
                _render_one_style(sub, lines, indent="  ")
            else:
                lines.append(f"- {label}: {sub}")
    lines.append("")


# ---------------------------------------------------------------------------
# AI features context blocks (for downstream agent seed injection)
# ---------------------------------------------------------------------------

_TIER_ORDER_FOR_SUMMARY = {
    "deterministic": 1, "embeddings": 2, "single_call": 3, "rag": 4,
    "tool_agent": 5, "chained_calls": 6, "planning_agent": 7,
    "orchestrated_subagents": 8, "multi_agent_collaboration": 9,
}


def _served_product_feature_ids(node: dict[str, Any]) -> list[str]:
    """Product-feature ids an AI node serves, from its ``vision_grounding``.

    The serves relation (D-AC1) is the only sound capability→product-feature
    mapping: an AI node's id is a capability-*surface* id and never equals the
    product feature id it serves. Ids are returned in grounding order, de-duped.
    Empty for infrastructure and cross-cutting nodes, which ground nothing.
    """
    grounding = node.get("vision_grounding") or {}
    out: list[str] = []
    for sf in (grounding.get("served_features") or []):
        if isinstance(sf, dict) and sf.get("id"):
            fid = str(sf["id"])
            if fid not in out:
                out.append(fid)
    return out


def _project_feature_for_stack(
    f: dict[str, Any], current_version: int | None, lines: list[str]
) -> None:
    """Append one feature's stack-driving fields to ``lines`` (D-SA1(c)).

    Tier-agnostic: every field here can force a concrete library choice with no
    model in sight — a ``deterministic`` feature may declare a ``document_store``
    knowledge source or a ``scheduled`` invocation. So the projection surfaces
    the same fields regardless of tier rather than gating them behind a model
    threshold (the histogram's bias, which dropped exactly this detail).

    ``scope`` and the serves relation are rendered because the stack prompt's
    linkage rules condition on them (D-SC14): ``serves_features`` must carry the
    product feature id a capability serves, and the ``cross_feature`` lane fires
    on scope. Both were computed upstream and dropped here, leaving the model to
    infer the capability→product mapping from name similarity — which is exactly
    how a catalog node id reaches ``serves_features`` in place of a product id.
    """
    name = f.get("name") or f.get("id") or "unnamed"
    tier = f.get("tier", "single_call")
    scope = f.get("scope")
    header = f"- **{name}** ({tier}"
    header += f", scope: {scope})" if scope else ")"
    if current_version and f.get("introduced_in_version") == current_version:
        header += " — NEW this revision"
    lines.append(header)

    served = _served_product_feature_ids(f)
    if served:
        lines.append(f"    - serves product feature(s): {', '.join(served)}")

    mode = (f.get("invocation") or {}).get("mode")
    if mode:
        lines.append(f"    - invocation: {mode}")

    fmt = (f.get("outputs") or {}).get("format")
    if fmt:
        lines.append(f"    - output format: {fmt}")

    for ks in (f.get("knowledge_sources") or []):
        if not isinstance(ks, dict):
            continue
        ks_name = ks.get("name") or "source"
        ks_type = ks.get("type") or "unspecified"
        desc = (ks.get("content_description") or "").strip()
        line = f"    - knowledge source: {ks_name} ({ks_type})"
        if desc:
            line += f" — {desc[:100]}"
        lines.append(line)

    for cap in ((f.get("tool_access") or {}).get("capabilities_needed") or []):
        if not isinstance(cap, dict):
            continue
        purpose = (cap.get("purpose") or "capability").strip()
        detail = f"source={cap.get('source') or 'unspecified'}"
        if cap.get("protocol"):
            detail += f", protocol={cap['protocol']}"
        if cap.get("mcp_server"):
            detail += f", server={cap['mcp_server']}"
        lines.append(f"    - tool access: {purpose[:80]} [{detail}]")

    mechs = [
        (m.get("name") if isinstance(m, dict) else str(m))
        for m in (f.get("mechanisms") or [])
    ]
    mechs = [m for m in mechs if m]
    if mechs:
        lines.append(f"    - mechanisms: {', '.join(mechs)}")

    privacy = [
        str(p).strip() for p in (f.get("privacy_safety") or []) if str(p).strip()
    ]
    if privacy:
        lines.append(f"    - privacy/safety: {'; '.join(privacy)[:120]}")

    online = (f.get("eval_approach") or {}).get("online")
    if online:
        lines.append(f"    - online eval signal: {str(online)[:100]}")

    refs = [str(r).strip() for r in (f.get("references") or []) if str(r).strip()]
    if refs:
        lines.append(f"    - references: {'; '.join(refs)[:160]}")


def _ai_features_for_stack(
    ai_features: dict[str, Any], current_version: int | None = None
) -> str:
    """Per-feature stack-driving projection for StackAdvisor (D-SA1(c), D-SA2).

    Replaces the prior tier-histogram + boolean-hint summary. The histogram
    framed every signal through model tiers, which (a) scored infrastructure
    nodes — whose sentinel ``tier="infrastructure"`` defaulted to the
    ``single_call`` order — as generative, emitting a phantom "LLM-backed"
    instruction on catalogs with zero generative features, and (b) gated the
    vector-store hint above the ``embeddings`` tier, so an embeddings feature's
    vector substrate was never surfaced (the D-PS5b mechanism). Deleting the
    hint layer retires both defects together (D-SA3(a)); the replacement
    surfaces, per feature and regardless of tier, exactly the fields that force
    a concrete library choice (D-SA1(c)).

    Infrastructure nodes (``kind == INFRA_KIND``) are split out of the
    per-feature projection and rendered as an explicit required-infrastructure
    section (D-SA2), each reverse-mapped to the feature(s) that ``require`` it,
    so StackAdvisor knows each substrate needs a concrete library or service
    choice. The provider *gate* itself (D-SA6 / D-SA10) is consumed by the topic
    sequence and schema in ``stack_advisor.py`` and is not computed here.

    ``current_version`` is the revision round being planned. When it identifies
    a revision (truthy / > 0), features whose ``introduced_in_version`` equals it
    are tagged ``NEW this revision`` inline, plus a single note that carries the
    "not yet in the carried-forward stack" instruction so revision-mode
    StackAdvisor does not mistake a brand-new feature for existing capability.
    Greenfield builds (version 0) tag nothing — every feature is new there.
    """
    all_nodes: list[dict[str, Any]] = ai_features.get("ai_features") or []
    cross: dict[str, Any] = ai_features.get("cross_cutting") or {}
    if not all_nodes:
        return ""

    features = [f for f in all_nodes if f.get("kind") != INFRA_KIND]
    infra = [f for f in all_nodes if f.get("kind") == INFRA_KIND]

    lines = [
        "**AI features spec (from Agentifier) — tailor your stack "
        "recommendations to these:**\n"
    ]

    any_new = False
    for f in features:
        _project_feature_for_stack(f, current_version, lines)
        if current_version and f.get("introduced_in_version") == current_version:
            any_new = True

    if any_new:
        lines.append(
            "- Features tagged \"NEW this revision\" are NOT yet implemented in "
            "the carried-forward stack; treat each as a new functional area "
            "requiring stack support, not pre-existing capability."
        )

    if infra:
        lines.append(
            "\n**Required infrastructure (tier-derived — each needs a concrete "
            "library or service choice in the stack):**"
        )
        for node in infra:
            comp = node.get("name") or node.get("id") or "unnamed"
            consumers = [
                (c.get("name") or c.get("id") or "unnamed")
                for c in features
                if comp in (c.get("requires") or [])
            ]
            if consumers:
                lines.append(f"- {comp} — required by: {', '.join(consumers)}")
            else:
                lines.append(f"- {comp}")

    # Cross-cutting strategies the analyst produced for stack selection. Provider
    # strategy is ratified into the providers block; tool-protocol strategy informs
    # tool/MCP library selection; prompt versioning is recorded as a convention.
    # (observability / eval are owned by StackAdvisor and Deployer natively.)
    if cross.get("provider_strategy", {}).get("recommendation"):
        rec = cross["provider_strategy"]["recommendation"][:120]
        lines.append(f"\n- Provider strategy: {rec}")
    if (cross.get("tool_protocol_strategy") or {}).get("recommendation"):
        rec = cross["tool_protocol_strategy"]["recommendation"][:200]
        lines.append(
            f"- Tool protocol strategy (MCP vs direct, build vs reuse): {rec}"
        )
    if (cross.get("prompt_versioning") or {}).get("recommendation"):
        rec = cross["prompt_versioning"]["recommendation"][:200]
        lines.append(f"- Prompt versioning: {rec}")

    # D-SC55a. StackAdvisor could not see the rejection list, and Phaser always
    # could (`_ai_features_for_phaser` calls the same helper) -- the asymmetry ran
    # exactly the wrong way, since StackAdvisor is where the provider decision is
    # made and Phaser only inherits it as authoritative.
    #
    # The cost was measured on both validated draws. Threadline's developer
    # deselected the whole reply cluster; StackAdvisor provisioned an OpenAI
    # primary AND an Anthropic fallback for `suggested_replies_in_three_tones` and
    # called it "a single_call feature" -- assigning a tier, which is Agentifier's
    # job, with none of Agentifier's machinery. Ragmeister's developer deselected
    # `policy_gap_identification`; StackAdvisor rebuilt it as a sub-agent of
    # `subagent_orchestration_runtime` with its own `inquiry_log` table. In both
    # cases D-SC14's spine-as-base was doing its job with one input missing: it saw
    # a need in the spine, saw no catalog node, and filled the hole.
    #
    # Deselection is the panel's only act of developer agency, and it was being
    # reversed two agents downstream on a receipt the developer then ratified.
    lines.extend(_explicitly_rejected_lines(ai_features, consumer="stack"))

    lines.append("")
    return "\n".join(lines)


def _feature_relationship_lines(features: list[dict[str, Any]]) -> list[str]:
    """Render the Scout graph-contract edges as a data-only relationships block.

    Two edge kinds are surfaced verbatim for Phaser to read; no build-order or
    coordinated-feature directives are added here — interpreting the edges is
    Phaser's own logic (a later lever). ``composed_under`` groups members beneath
    their coordinator; ``requires`` names the producers a feature consumes. Edges
    are rendered exactly as persisted (D-EP2 option A), including any that dangle.
    Returns ``[]`` when no edges are present.
    """
    groups: dict[str, list[str]] = {}
    for f in features:
        parent = f.get("composed_under") or ""
        if parent:
            groups.setdefault(parent, []).append(f.get("name", ""))
    req_edges: list[tuple[str, list[str]]] = []
    for f in features:
        reqs = [r for r in (f.get("requires") or []) if r]
        if reqs:
            req_edges.append((f.get("name", ""), reqs))
    if not groups and not req_edges:
        return []
    lines = ["**Feature relationships (from Agentifier's graph contract):**\n"]
    if groups:
        lines.append("- `composed_under` (coordinator → members):")
        for coord in sorted(groups):
            members = ", ".join(m for m in groups[coord] if m)
            lines.append(f"  - {coord}: {members}")
    if req_edges:
        lines.append("- `requires` (feature → producers it consumes):")
        for name, reqs in req_edges:
            lines.append(f"  - {name}: {', '.join(reqs)}")
    lines.append("")
    return lines


def _explicitly_rejected_lines(
    ai_features: dict[str, Any], consumer: str = "phaser"
) -> list[str]:
    """Name the candidates the developer deselected, so they are not re-added.

    The instruction differs by consumer because the failure differs. Phaser must
    not *phase* a rejected candidate. StackAdvisor must not *provision a mechanism*
    for one — and, crucially, must still give the product feature its ordinary
    stack: `source_citations` is a Ragmeister spine feature with no catalog node
    that correctly carries stores, an API and a UI and no provider. Telling
    StackAdvisor "do not plan phases for these" would say nothing about the
    decision it actually makes; telling it to drop the feature entirely would strip
    a spine feature of the persistence it needs (D-SC56).
    """
    rejected = ai_features.get("explicitly_rejected") or []
    names = [
        r.get("name", "") for r in rejected if isinstance(r, dict) and r.get("name")
    ]
    if not names:
        return []
    if consumer == "stack":
        return [
            "\n**Explicitly rejected by the developer — these are NOT AI features:** "
            + ", ".join(names),
            "Agentifier never tiered, coordinated or specced these, so there is no "
            "decision behind them to honour. Do NOT give any of them a provider "
            "capability, an infrastructure entry, or a library that exists to serve "
            "them — a mechanism you pick here would be invented, not chosen. Where a "
            "rejected name is also an MVP feature in the spine, it still needs its "
            "ordinary stack (its store, its API, its UI); it just is not built with "
            "AI.",
            "",
        ]
    return [
        "**Explicitly rejected by the developer — do NOT plan phases for these:** "
        + ", ".join(names),
        "",
    ]


def _ai_features_for_phaser(
    ai_features: dict[str, Any], revision_version: int | None = None
) -> str:
    """Full AI features context for Phaser: index table, complete specs, edges.

    Phaser is the agent that sequences the build and authors the per-phase
    ``features[]`` declaration, so it receives the *entire* Agentifier surface
    (D-PS3 option B): every Spec Drafter field, the tier analysis behind each
    tier, graph edges, scope (including ``cross_feature``), infrastructure
    substrate, cross-cutting decisions, and the rejected set. It cannot curate
    what it has not been shown — and it cannot write an honest per-phase
    ``scope_note`` about part of a feature whose parts it never saw.

    Spec bodies are rendered by ``spec4.feature_specs`` — the same renderer the
    phase-file preamble uses — so what Phaser reads and what the coding agent
    receives cannot drift.

    Note the asymmetry with the phase files: Phaser sees ``provider_strategy``
    here, but it is excluded from the rendered phases (D-PS6 A'), where
    StackAdvisor's ratified ``tech_stack_spec`` is the authority.

    In a revision round (``revision_version`` set to the active round's version),
    the feature set is partitioned by the deterministic ``introduced_in_version``
    stamp: features introduced in this round are rendered as the phase/priority
    table to plan, while features from earlier rounds are listed as already-built
    context the agent must not re-phase. ``introduced_in_version`` is the hard
    phase/don't-phase split (code-owned, deterministic); the vision delta's
    ``modified`` set stays soft context in the seed's revision note, kept out of
    this partition to avoid the brittle ``linked_vision_features`` name-join. With
    ``revision_version`` left ``None`` (greenfield or plain brownfield), the output
    is unchanged.
    """
    features: list[dict[str, Any]] = ai_features.get("ai_features") or []
    if not features:
        return ""
    # Full feature set for the relationships block below — captured before the
    # revision partition reassigns ``features`` to the to-phase slice, so the
    # graph-contract edges render completely regardless of the partition.
    all_feats = list(features)

    established: list[dict[str, Any]] = []
    if revision_version is not None:
        to_phase: list[dict[str, Any]] = []
        for f in features:
            iv = f.get("introduced_in_version")
            if isinstance(iv, int) and iv == revision_version:
                to_phase.append(f)
            else:
                established.append(f)
        features = to_phase

    lines: list[str] = []
    if established:
        names = ", ".join(f.get("name", "") for f in established)
        lines.append(
            "**Already-implemented AI features — in place, do NOT create phases "
            f"for these:** {names}\n"
        )

    if not features:
        # Revision round whose delta touched no AI features: established context
        # only, nothing new to phase.
        return "\n".join(lines)

    header = (
        "**New/changed AI features for this revision — plan phases for these:**\n"
        if revision_version is not None
        else "**AI features spec (from Agentifier) — use phase_priority to decide when to implement each:**\n"
    )
    lines.extend([
        header,
        "| Feature | id | Kind | Tier | Scope | Phase Priority |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for f in features:
        name = f.get("name", "")
        fid = f.get("id", "")
        kind = "infrastructure" if f.get("kind") == INFRA_KIND else "feature"
        tier = f.get("tier", "")
        scope = f.get("scope", "")
        priority = f.get("phase_priority", "mvp")
        lines.append(f"| {name} | `{fid}` | {kind} | {tier} | {scope} | {priority} |")
    lines.append("")
    lines.append(
        "The `id` column is the exact key to use in each phase's `features` array."
    )

    lines.append("\nPhasing guidance:")
    steel = [f.get("name", "") for f in features if f.get("phase_priority") == "steel_thread"]
    if steel:
        lines.append(f"- **steel_thread** features belong in Phase 1 or Phase 2: {', '.join(steel)}")
    mvp = [f.get("name", "") for f in features if f.get("phase_priority") == "mvp"]
    if mvp:
        lines.append(f"- **mvp** features must be implemented before the first release: {', '.join(mvp)}")
    v2 = [f.get("name", "") for f in features if f.get("phase_priority") in ("v2", "future")]
    if v2:
        lines.append(f"- **v2/future** features may be deferred post-MVP: {', '.join(v2)}")
    infra = [f.get("name", "") for f in features if f.get("kind") == INFRA_KIND]
    if infra:
        lines.append(
            "- **infrastructure** nodes are shared substrate, not user-selected "
            "capabilities. Each must be stood up in the same phase as its first "
            f"consumer or earlier: {', '.join(infra)}"
        )
    cross_feat = [f.get("name", "") for f in features if f.get("scope") == "cross_feature"]
    if cross_feat:
        lines.append(
            "- **cross_feature** features span more than one vision feature. Treat "
            "them as shared surface — sequence them where every consumer can reach "
            f"them, not inside one consumer's phase: {', '.join(cross_feat)}"
        )
    lines.append("")
    lines.extend(_feature_relationship_lines(all_feats))

    # Full spec bodies — the artifact the phase files attach verbatim.
    lines.append("**Full implementation specs (from Agentifier's Spec Drafter):**\n")
    for f in features:
        name = f.get("name", "")
        fid = f.get("id", "")
        lines.append(f"### {name} (`{fid}`)\n")
        lines.extend(render_feature_block(f))
    lines.extend(render_cross_cutting(ai_features.get("cross_cutting")))
    lines.extend(_explicitly_rejected_lines(ai_features))

    consolidation = ai_features.get("consolidation") or []
    if consolidation:
        lines.append("**Consolidation notes:**\n")
        lines.extend(f"- {c}" for c in consolidation if c)
        lines.append("")
    references = ai_features.get("references") or []
    if references:
        lines.append("**Catalog references:**\n")
        lines.extend(f"- {r}" for r in references if r)
        lines.append("")
    return "\n".join(lines)


def _ai_features_for_deployer(
    ai_features: dict[str, Any] | None,
    stack: dict[str, Any] | None = None,
) -> str:
    """AI deployment context for Deployer: providers, tiers, budgets (D-DE7).

    What a deployment plan needs about the AI side is narrow and specific: which
    providers it must configure access to, what latency and cost the features are
    budgeted for, and whether evals and guardrails need a home. This renders
    exactly that.

    **Providers come from the stack, not the catalog.** The stack's ``providers``
    block is the ratified decision (D-PH6 A′); the catalog's
    ``cross_cutting.provider_strategy`` is a recommendation it supersedes, and
    rendering both would give one decision two owners — so the recommendation is
    no longer surfaced here. Each provider renders as its ``model_family`` — the
    family is the decision, and a plan must never pin a specific model id — with
    the roles and tiers it serves, its ``credentials_env``, and its
    ``endpoint_env``. A provider carrying ``endpoint_env`` is self-hosted: it is
    infrastructure to run, not a key to hold, which is a materially different
    deployment.

    **Budgets** (``p95_latency``, ``cost_per_call``) are per-feature targets the
    deployment has to meet — they drive timeouts, autoscaling, and capacity
    planning, and reach Deployer through no other channel.

    **Evals and safety** are reported as counts only. Deployer's job is to give
    them a cadence and an enforcement point; the approaches and constraints
    themselves (gold-standard datasets, redaction rules) are the coding agent's
    to implement, and would cost several times this whole projection to carry.

    Infrastructure nodes are deliberately absent: the catalog's infrastructure
    ids are the same substrate the stack digest already lists for provisioning.

    Returns ``""`` when the project has no AI features.
    """
    features: list[dict[str, Any]] = (ai_features or {}).get("ai_features") or []
    if not features:
        return ""

    lines = ["**AI features spec — deployment context:**\n"]

    inner = (stack or {}).get("stack_spec") if isinstance(stack, dict) else None
    spec = inner if isinstance(inner, dict) else (stack or {})
    providers = spec.get("providers") if isinstance(spec, dict) else None
    if isinstance(providers, dict) and providers:
        lines.append(
            "**Providers to configure access to** (from the ratified stack). The "
            "family is the decision — do not pin a specific model id in the plan:"
        )
        for name, prov in providers.items():
            if not isinstance(prov, dict):
                continue
            family = str(prov.get("model_family") or "").strip()
            caps = [c for c in (prov.get("capabilities") or []) if isinstance(c, dict)]
            roles = sorted({str(c.get("role")) for c in caps if c.get("role")})
            tiers = sorted({str(c.get("tier")) for c in caps if c.get("tier")})
            head = f"- {name}"
            if family:
                head += f" — model family: {family}"
            if roles:
                head += f" ({', '.join(roles)})"
            lines.append(head)
            if tiers:
                lines.append(f"  - serves tiers: {', '.join(tiers)}")
            creds = str(prov.get("credentials_env") or "").strip()
            if creds:
                lines.append(f"  - credentials (environment): {creds}")
            endpoint = str(prov.get("endpoint_env") or "").strip()
            if endpoint:
                lines.append(
                    f"  - self-hosted: reachable at `{endpoint}` — this is a model "
                    f"host to run and size, not a third-party key to hold"
                )
            fallback = str(prov.get("fallback") or "").strip()
            if fallback:
                lines.append(f"  - fallback: {fallback}")
        lines.append("")

    tiers_in_use = sorted({str(f.get("tier")) for f in features if f.get("tier")})
    if tiers_in_use:
        lines.append(f"- AI feature tiers in use: {', '.join(tiers_in_use)}")
    if any(
        _TIER_ORDER_FOR_SUMMARY.get(str(f.get("tier") or ""), 0) >= 5
        for f in features
    ):
        lines.append(
            "- Tool-calling features require LLM API keys in environment configuration"
        )

    budget_lines: list[str] = []
    for f in features:
        budgets = f.get("budgets")
        if not isinstance(budgets, dict):
            continue
        parts = []
        p95 = str(budgets.get("p95_latency") or "").strip()
        cost = str(budgets.get("cost_per_call") or "").strip()
        if p95:
            parts.append(f"p95 latency {p95}")
        if cost:
            parts.append(f"cost/call {cost}")
        if parts:
            budget_lines.append(f"- {f.get('id') or f.get('name')}: {'; '.join(parts)}")
    if budget_lines:
        lines.append("")
        lines.append(
            "**Per-feature budgets** — the latency and cost targets this deployment "
            "has to meet; they drive timeouts, autoscaling, and capacity planning:"
        )
        lines.extend(budget_lines)

    n_eval = sum(1 for f in features if f.get("eval_approach"))
    n_safety = sum(1 for f in features if f.get("privacy_safety"))
    if n_eval or n_safety:
        lines.append("")
        lines.append(
            f"**Evals and safety** — {n_eval} of {len(features)} AI features declare "
            f"an eval approach and {n_safety} declare safety constraints. The plan "
            f"needs an eval cadence and a place where guardrails are enforced; the "
            f"approaches and constraints themselves are the coding agent's to build."
        )

    lines.append("")
    return "\n".join(lines)


def _phases_for_deployer(phases: list[dict[str, Any]], version: Any) -> str:
    """Deployment-shaped projection of the phase plan for Deployer (D-DE4).

    Deployer previously received phase numbers and titles only, discarding the
    rest of a payload it already held. Two things in that payload are
    deployment-shaped and reach Deployer through no other channel:

    * the **build order**, which is both the sequence a coding agent executes
      (pointing the agent at these files is Deployer's first job, so the paths
      stay) and the order infrastructure has to come up in;
    * each phase's ``tech_stack_spec.configurations`` — the environment
      variables, ports, and config files that phase's code actually reads. Their
      union is the factual basis for the plan's Environment section, which
      otherwise gets derived from a brownfield code review or asked for cold.

    ``configurations`` is projected **verbatim** rather than mined for variable
    names. The prose carries the example values, the local-versus-production
    split, and what each variable is *for*; a name-only extraction would drop all
    three and would have to guess at naming conventions besides. Phases that add
    no new variables still get their line, so silence reads as "nothing new here"
    rather than as an omission.

    Verification text and per-phase dependency lists are deliberately not
    projected. Verification is overwhelmingly the local dev loop (bring compose
    up, curl the health endpoint, run the tests) and the dependency lists are
    package installs the stack spec already owns — neither is a deployment
    decision, and together they cost several times the whole projection above.

    Returns ``""`` when there are no phases, so a project without a phase plan
    contributes nothing rather than an empty heading.
    """
    if not phases:
        return ""

    lines: list[str] = [
        f"**Development phases (from Phaser) — the {len(phases)} phases a coding agent "
        f"will execute, in order. The deployment has to accommodate what these phases "
        f"configure and stand up.**\n"
    ]

    lines.append(f"**Build order** (saved under `.spec4/v{version}/phases/`):")
    for p in phases:
        num = p.get("phase_number")
        title = str(p.get("phase_title") or "").strip()
        lines.append(f"- Phase {num}: {title} (`.spec4/v{version}/phases/phase{num}.md`)")
    lines.append("")

    config_lines: list[str] = []
    for p in phases:
        tech: dict[str, Any] = p.get("tech_stack_spec") or {}
        raw = tech.get("configurations")
        if isinstance(raw, list):
            cfg = "; ".join(str(c).strip() for c in raw if str(c).strip())
        else:
            cfg = str(raw or "").strip()
        if cfg:
            config_lines.append(f"- Phase {p.get('phase_number')}: {cfg}")

    if config_lines:
        lines.append(
            "**Per-phase configuration** — the environment variables, ports, and config "
            "files each phase expects, verbatim from its tech stack spec. Their union is "
            "the factual starting point for this plan's Environment section: confirm and "
            "correct them with the developer rather than asking cold, and read a phase "
            "that adds nothing as exactly that."
        )
        lines.extend(config_lines)
        lines.append("")

    return "\n".join(lines)


def _stack_for_deployer(stack: dict[str, Any] | None) -> str:
    """Deployment-shaped digest of the stack spec for Deployer (D-DE5).

    Deployer previously received the whole stack as a raw ``json.dumps`` paste —
    tens of thousands of characters in which every deployment decision the stack
    had already made was present but never legible. Measured against three
    drawn plans, most of it never arrived: transport never once reached a plan,
    one of two targets and both auth mechanisms went unmentioned, and the
    substrate to provision was largely missed.

    This replaces the paste with the deployment-shaped view, rendered
    deterministically and verbatim:

    * **targets** — every ``deployment.targets[]`` entry with the fields that
      *are* the Target, Containerization, and Environment sections: kind,
      purpose, language, runtime, hosting, build, distribution, api_contract,
      and ``exposure`` (transport and CORS). ``build`` and ``hosting`` are what
      carry, e.g., the service-worker/PWA and CDN stories;
    * **auth** — every ``security.auth[]`` mechanism with its purpose, what it
      serves, and its ``credentials_env``, which is a source of required
      environment variables independent of the phase configurations;
    * **provisioning** — the persistence stores and ``infrastructure`` entries
      this build stands up, each with its ratified choice and why;
    * **roadmap** — entries carrying ``status: optional``/``deferred``, named so
      they are recorded rather than built.

    Two absences are load-bearing and stated rather than left silent: an absent
    or empty ``security.auth`` means the project has no accounts, and an absent
    ``integrations`` block means no external services. Deployer must not read
    either as an omission and re-ask.

    Providers and ``model_family`` are deliberately not rendered here: provider
    and model deployment is the AI channel's to own, and surfacing it in both
    places would give one decision two owners.

    Returns ``""`` when the stack is absent or empty.
    """
    if not isinstance(stack, dict) or not stack:
        return ""
    inner = stack.get("stack_spec")
    spec = inner if isinstance(inner, dict) else stack

    lines: list[str] = [
        "**Technology stack — deployment signals (from StackAdvisor). This is the "
        "deployment-shaped view of the ratified stack: what to host, how to expose "
        "it, what to provision, and what to keep out of this build. These decisions "
        "are already settled — build on them rather than re-asking.**\n"
    ]

    def _field(entry: dict[str, Any], key: str, label: str) -> str | None:
        val = entry.get(key)
        text = str(val or "").strip()
        return f"  - {label}: {text}" if text else None

    targets = [
        t for t in ((spec.get("deployment") or {}).get("targets") or [])
        if isinstance(t, dict)
    ]
    if targets:
        lines.append(
            f"**Deployment targets** — {len(targets)} surface(s) to host. Each is a "
            f"distinct hosting decision; its `exposure` is literal transport and CORS "
            f"configuration:"
        )
        for t in targets:
            name = str(t.get("name") or "target").strip()
            kind = str(t.get("kind") or "").strip()
            purpose = str(t.get("purpose") or "").strip()
            head = f"- `{name}`" + (f" ({kind})" if kind else "")
            lines.append(f"{head} — {purpose}" if purpose else head)
            for key, label in (
                ("language", "language"),
                ("runtime", "runtime"),
                ("hosting", "hosting"),
                ("build", "build"),
                ("distribution", "distribution"),
                ("api_contract", "API contract"),
            ):
                row = _field(t, key, label)
                if row:
                    lines.append(row)
            exposure = t.get("exposure")
            if isinstance(exposure, dict):
                for key, label in (("transport", "transport"), ("cors", "CORS")):
                    row = _field(exposure, key, label)
                    if row:
                        lines.append(row)
        lines.append("")

    security = spec.get("security")
    auth = [
        a for a in ((security or {}).get("auth") or []) if isinstance(a, dict)
    ] if isinstance(security, dict) else []
    if auth:
        lines.append(
            f"**Authentication** — {len(auth)} mechanism(s). Their credentials are "
            f"required environment variables and belong in the Environment section:"
        )
        for a in auth:
            mech = str(a.get("mechanism") or a.get("name") or "auth").strip()
            purpose = str(a.get("purpose") or "").strip()
            lines.append(f"- {mech}" + (f" — {purpose}" if purpose else ""))
            serves = [str(s) for s in (a.get("serves_features") or []) if str(s)]
            if serves:
                lines.append(f"  - serves: {', '.join(serves)}")
            creds = [str(c) for c in (a.get("credentials_env") or []) if str(c)]
            if creds:
                lines.append(f"  - credentials (environment): {', '.join(creds)}")
        lines.append("")
    else:
        lines.append(
            "**Authentication** — the stack declares none. This project has no user "
            "accounts: do not provision an identity provider, do not plan auth "
            "secrets, and do not ask the developer to choose one.\n"
        )

    if not (spec.get("integrations") or []):
        lines.append(
            "**External integrations** — the stack declares none. There are no "
            "third-party services to configure credentials or network egress for.\n"
        )

    provision: list[str] = []
    roadmap: list[str] = []
    for section in ("persistence", "infrastructure"):
        block = spec.get(section)
        if not isinstance(block, dict):
            continue
        for key, entry in block.items():
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or key).strip()
            status = str(entry.get("status") or "").strip()
            choice = str(entry.get("choice") or "").strip()
            purpose = str(entry.get("purpose") or "").strip()
            if status in ROADMAP_STATUSES:
                roadmap.append(f"- `{name}` ({section}, {status})"
                               + (f" — {purpose}" if purpose else ""))
                continue
            row = f"- `{name}` ({section})" + (f": {choice}" if choice else "")
            if purpose:
                row += f" — {purpose}"
            provision.append(row)
            for key_name, label in (
                ("durability", "durability"),
                ("implementation", "implementation"),
            ):
                extra = _field(entry, key_name, label)
                if extra:
                    provision.append(extra)
            sat = [str(s) for s in (entry.get("satisfies_infra") or []) if str(s)]
            if sat:
                provision.append(f"  - satisfies infrastructure need: {', '.join(sat)}")

    if provision:
        lines.append(
            "**To provision** — the stores and infrastructure this build stands up. "
            "Each choice is ratified; the deployment plan's job is to say how it gets "
            "created and configured, not to re-choose it:"
        )
        lines.extend(provision)
        lines.append("")

    for e in stack_signal_entries(stack):
        entry = e["entry"]
        if str(entry.get("status") or "") not in ROADMAP_STATUSES:
            continue
        if e["section"] in ("persistence", "infrastructure"):
            continue  # already captured above, with its section context
        roadmap.append(f"- `{e['label']}` ({e['section']}, {entry.get('status')})")

    if roadmap:
        lines.append(
            "**Roadmap — recorded, not provisioned.** These carry a non-MVP `status`. "
            "Note them in the plan so they are not lost, but do not build, provision, "
            "or configure them in this deployment:"
        )
        lines.extend(roadmap)
        lines.append("")

    return "\n".join(lines)


def _nfr_goals_for_deployer(
    stack: dict[str, Any] | None,
    feature_specs: dict[str, Any] | None,
) -> str:
    """Every project non-functional goal, with its stack claim status (D-DE6).

    The project's ``nfr_goals`` are outcome-phrased statements of what the built
    system must be like — fast, available offline, durable across restarts,
    updatable without interrupting users, confidential between parties. Several
    of those are deployment decisions and nothing else: they are settled by
    region, caching, replica and scaling posture, backup policy, and network
    isolation. Deployer received none of them, and they evaporated between the
    vision and the plan.

    This renders all of them, each marked with whether any stack entry claims to
    satisfy it (``satisfies_nfr``):

    * **claimed** — the claiming entries are named, so the plan can say how that
      component's deployment actually delivers the goal;
    * **unclaimed** — surfaced honestly rather than dropped. An unclaimed goal is
      not a defect: goals satisfied by *features* rather than by stack components
      correctly have no claimer. What must never happen is inventing a claim, so
      an unclaimed goal is marked as unclaimed and left that way.

    Ids follow the shared ``nfr_<slug>`` derivation (D-SC2) via
    ``derived_nfr_ids``, so a goal has the same id here as everywhere else in the
    pipeline. Goal order follows the source list.

    Returns ``""`` when the project declares no goals.
    """
    derived = derived_nfr_ids(feature_specs)
    if not derived:
        return ""

    claimers: dict[str, list[str]] = {}
    if isinstance(stack, dict) and stack:
        for rec in stack_signal_entries(stack):
            for raw in (rec["entry"].get("satisfies_nfr") or []):
                nid = str(raw)
                if nid in derived:
                    claimers.setdefault(nid, []).append(rec["label"])

    lines: list[str] = [
        "**Non-functional goals (from the vision).** These state what the built "
        "system has to be like. Some are settled by deployment and nothing else — "
        "where a goal is, the plan is where it gets delivered, so say how. Each "
        "goal below is marked with whether any stack component claims to satisfy "
        "it; a goal no component claims must be left unclaimed rather than given "
        "an invented one.\n"
    ]
    for nid, goal in derived.items():
        lines.append(f"- `{nid}` — \"{goal}\"")
        named = sorted(set(claimers.get(nid, [])))
        if named:
            lines.append(f"  - claimed by: {', '.join(named)}")
        else:
            lines.append(
                "  - claimed by: no stack component. Do not invent an "
                "infrastructure claim for this goal."
            )
    lines.append("")
    return "\n".join(lines)


def _designer_affordance_hints(mode: str, authority: str, tier_order: int) -> list[str]:
    """UX affordance hints for a surface, from its invocation mode / authority / tier.

    Mode drives the wait model (streaming vs. blocking vs. background), authority
    drives whether the user confirms or can dismiss, and multi-step tiers
    (chained_calls and up) warrant visible progress.
    """
    hints: list[str] = []
    if mode == "streaming":
        hints.append("stream the output progressively (streaming/typing indicator)")
    elif mode == "asynchronous":
        hints.append(
            "runs in the background — surface results as a notification, alert, or "
            "status badge rather than a blocking wait"
        )
    if authority == "confirm":
        hints.append("require explicit confirmation before the action commits")
    elif authority == "suggest":
        hints.append("present as a suggestion the user can accept or dismiss")
    if tier_order >= 6:  # chained_calls and up are inherently multi-step
        hints.append("show multi-step progress/status while it runs")
    return hints


def _short_text(text: str, limit: int = 220) -> str:
    """Collapse whitespace and truncate ``text`` to ``limit`` chars for prompts."""
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _ai_features_for_designer(ai_features: dict[str, Any]) -> str:
    """User-facing surface graph for Designer.

    Projects the catalog into the surfaces Designer must actually build, rather
    than a flat list of affordance hints. Each top-level ``scope == "feature"``
    (non-infrastructure) node is a user-facing *surface* carrying the substance
    needed to design it for real: the vision feature(s) it serves, its trigger,
    the inputs the user provides, the result to show, and a UX affordance derived
    from its invocation mode / decision authority / tier. Each surface's
    ``composed_under`` members are nested beneath it as in-surface affordances
    (citations, verification, routing, related items), never standalone screens.
    Infrastructure nodes and unparented internal steps never surface.

    Returns ``""`` when the catalog has no user-facing AI surface, so a no-AI or
    deterministic-only build designs from the vision alone.
    """
    features: list[dict[str, Any]] = ai_features.get("ai_features") or []
    if not features:
        return ""

    def _is_infra(f: dict[str, Any]) -> bool:
        return f.get("tier") == "infrastructure" or f.get("kind") == "infrastructure"

    surfaces = [
        f for f in features if f.get("scope") == "feature" and not _is_infra(f)
    ]
    if not surfaces:
        return ""

    members_by_parent: dict[str, list[dict[str, Any]]] = {}
    for f in features:
        if f.get("scope") == "sub_feature" and not _is_infra(f):
            parent = f.get("composed_under") or ""
            if parent:
                members_by_parent.setdefault(parent, []).append(f)

    def _edge_state(f: dict[str, Any]) -> str:
        """The user-visible failure condition to design an empty/error state for."""
        fails = f.get("failure_modes")
        if isinstance(fails, list) and fails and isinstance(fails[0], dict):
            mode = fails[0].get("mode")
            if isinstance(mode, str) and mode.strip():
                return mode
        esc = f.get("escalation")
        return esc if isinstance(esc, str) else ""

    lines: list[str] = [
        "**User-facing AI surfaces** — each entry below is a real interaction the "
        "user has with an AI feature. Design each as a working surface on the "
        "appropriate screen: build its inputs into real controls, show its output "
        "as a real result, trigger it as described, and apply the noted affordance. "
        "These are surfaces to build, not features to advertise.\n"
    ]

    for f in surfaces:
        name = f.get("name", "")
        tier = f.get("tier", "")
        tier_order = _TIER_ORDER_FOR_SUMMARY.get(tier, 0)
        inv = f.get("invocation") or {}
        mode = inv.get("mode", "synchronous")
        trigger = inv.get("trigger", "")
        authority = f.get("decision_authority", "autonomous")
        served = f.get("linked_vision_features") or []

        header = f"### `{name}` (tier: {tier}, {mode})"
        if served:
            header += " — serves vision feature(s): " + ", ".join(served)
        lines.append(header)

        purpose = f.get("purpose", "")
        if purpose:
            lines.append(f"- Purpose: {_short_text(purpose)}")
        if trigger:
            lines.append(f"- Triggered when: {_short_text(trigger, 160)}")

        inputs = f.get("inputs")
        if isinstance(inputs, list) and inputs:
            rendered: list[str] = []
            for i in inputs:
                if not isinstance(i, dict):
                    continue
                iname = i.get("name", "")
                idesc = _short_text(i.get("description", ""), 90)
                req = "" if i.get("required", True) else " (optional)"
                rendered.append(f"{iname}{req}: {idesc}" if idesc else f"{iname}{req}")
            if rendered:
                lines.append("- User provides: " + "; ".join(rendered))

        outputs = f.get("outputs")
        primary_out = outputs.get("primary", "") if isinstance(outputs, dict) else ""
        if primary_out:
            lines.append(f"- Result to show: {_short_text(primary_out)}")

        hints = _designer_affordance_hints(mode, authority, tier_order)
        if hints:
            lines.append("- Affordance: " + "; ".join(hints))

        edge = _edge_state(f)
        if edge:
            lines.append(f"- Edge state to design for: {_short_text(edge, 160)}")

        members = members_by_parent.get(name) or []
        if members:
            lines.append(
                "- Within this surface, also design the user-visible output of its "
                "component steps — only those producing something the user sees "
                "(citations, confidence, routing, related items):"
            )
            for m in members:
                mname = m.get("name", "")
                mtier = m.get("tier", "")
                m_out = m.get("outputs")
                m_primary = m_out.get("primary", "") if isinstance(m_out, dict) else ""
                detail = _short_text(m_primary or m.get("purpose", ""), 130)
                mauth = m.get("decision_authority", "autonomous")
                aff = " [suggestion]" if mauth == "suggest" else (
                    " [confirm]" if mauth == "confirm" else ""
                )
                lines.append(f"    - `{mname}` ({mtier}){aff}: {detail}")

        lines.append("")

    return "\n".join(lines)


# Framing fields kept in Designer's vision block (DR2). The per-feature substance
# now rides in the feature-specs block, so the raw vision dump is slimmed to the
# project-wide framing that shapes global design (name, one-line purpose, the UI
# surface, audiences, and differentiators for tone). `key_features_mvp`,
# monetization, references, and revision history are dropped as noise or
# duplication of the richer feature specs.
_VISION_FRAMING_FIELDS: tuple[str, ...] = (
    "purpose",
    "ui_surface",
    "target_audience",
    "target_audiences",
    "differentiators",
)


def _slim_vision_framing(vision: dict[str, Any] | None) -> dict[str, Any]:
    """Project the vision envelope to the framing fields Designer needs (DR2).

    Accepts any of the shapes Designer sees: the full envelope
    (``{"vision_statement": {"name", "vision": {...}}}``), the inner statement,
    or an already-flat framing dict. Returns ``{}`` when nothing usable is
    present, so the caller can skip the section.
    """
    if not isinstance(vision, dict):
        return {}
    inner = vision.get("vision_statement")
    if not isinstance(inner, dict):
        inner = vision
    vblock = inner.get("vision")
    if not isinstance(vblock, dict):
        vblock = inner
    out: dict[str, Any] = {}
    name = inner.get("name") or vblock.get("name")
    if name:
        out["name"] = name
    for key in _VISION_FRAMING_FIELDS:
        val = vblock.get(key)
        if val:
            out[key] = val
    return out


def _feature_specs_for_designer(feature_specs: dict[str, Any] | None) -> str:
    """Render Brainstormer's ``feature_specs.json`` as a Designer prompt block (DR1/DR3).

    Emits one behavioural block per vision feature (the ``DESIGNER_SPEC_FIELDS``
    subset, no graph lines), the project-wide non-functional goals, and — as an
    advisory domain vocabulary (DR3, soft grounding) — the union of the features'
    ``entities``. The vocabulary is offered for the model to reflect in its
    manifest entities where the concept is data the UI presents or edits; it is
    deliberately not a deterministic overwrite, since these are conceptual domain
    nouns, not UI data entities. Returns ``""`` when no specs are present.
    """
    feats = (feature_specs or {}).get("features") or []
    if not feats:
        return ""

    lines: list[str] = [
        "**Feature specifications** — the authoritative behavioural spec for each "
        "product feature. Design each feature's surface(s) to satisfy these: build "
        "its inputs as real controls, show its outputs as a real result, trigger it "
        "as described, and design its failure modes as empty/error states.\n"
    ]

    entities: list[str] = []
    seen: set[str] = set()
    for f in feats:
        if not isinstance(f, dict):
            continue
        name = f.get("name") or f.get("id") or ""
        lines.append(f"### `{name}`")
        lines.extend(
            render_feature_block(
                f, fields=DESIGNER_SPEC_FIELDS, include_graph=False
            )
        )
        lines.append("")
        for ent in f.get("entities") or []:
            if isinstance(ent, str) and ent not in seen:
                seen.add(ent)
                entities.append(ent)

    nfr = (feature_specs or {}).get("nfr_goals") or []
    if isinstance(nfr, list) and nfr:
        lines.append("**Non-functional goals (project-wide):**")
        for goal in nfr:
            if isinstance(goal, str) and goal.strip():
                lines.append(f"- {goal.strip()}")
        lines.append("")

    if entities:
        lines.append(
            "**Domain vocabulary** — the concepts these features operate on: "
            + ", ".join(entities)
            + ". Reflect these in your manifest `entities` where they are data the "
            "UI presents or edits; you may add UI-specific entities (a list item, a "
            "form record) as needed. This is a vocabulary to honour, not a "
            "replacement for UI-appropriate entities."
        )
        lines.append("")

    return "\n".join(lines)


def _load_design_manifest(design_dir: Path | None) -> dict[str, Any] | None:
    """Read Designer's ``manifest.json`` from ``design_dir``. None when absent.

    Tolerant by design: Designer is optional, and a project that never ran it (or
    ran an older round) simply has no manifest. Unreadable or malformed content is
    treated the same as absent rather than raising into an agent turn.
    """
    if design_dir is None:
        return None
    path = design_dir / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _design_manifest_for_stack(manifest: dict[str, Any] | None) -> str:
    """Render Designer's manifest as a StackAdvisor block (D-SC5c).

    Designer is authoritative about two things a stack must accommodate: the data
    model the UI is built on (entities *with their fields*, where the feature spine
    carries only bare entity names) and the screen structure. Both are surfaced as
    advisory *shape* — never a mechanism mandate. Which store, which schema, which
    router remain StackAdvisor's call, exactly as the feature-spec entity
    vocabulary does (D-SC6).

    Deliberately omits the surface→feature join fields (``implements_feature_ids``,
    ``catalog_surface_id``). StackAdvisor already has a sound feature join, via the
    Brainstormer spine and the AI catalog's serves relation; the manifest's join is
    a second, redundant path that is known to over-attribute (surfaces claiming
    features they do not implement), so importing it would risk corrupting the very
    attribution this round exists to produce. Take the data model, leave the joins.

    The visual mock is not projected here at all: it is the coding agent's
    reference, handed downstream by path, and no stack decision needs its markup.
    Returns ``""`` when the manifest carries nothing usable.
    """
    man = manifest or {}
    entities = [e for e in (man.get("entities") or []) if isinstance(e, dict)]
    surfaces = [s for s in (man.get("surfaces") or []) if isinstance(s, dict)]
    screens = [s for s in (man.get("screens") or []) if isinstance(s, dict)]
    if not (entities or surfaces or screens):
        return ""

    lines: list[str] = [
        "**Design manifest (from Designer) — the structured plan behind the UI. It "
        "is authoritative about the *shape* of what the app stores and how it is "
        "laid out; the mechanism for both remains your decision.**\n"
    ]

    if entities:
        lines.append(
            "**Data model** — the entities the UI is built on, with the fields it "
            "expects. These are the UI's view of the domain, so treat them as the "
            "shape your persistence and validation choices must accommodate, not as "
            "a schema to adopt verbatim:"
        )
        for e in entities:
            name = str(e.get("name") or "").strip()
            if not name:
                continue
            fields = [str(f) for f in (e.get("fields") or []) if str(f).strip()]
            lines.append(f"- `{name}`: {', '.join(fields)}" if fields else f"- `{name}`")
        lines.append("")

    if surfaces:
        written: list[str] = []
        read: list[str] = []
        for s in surfaces:
            for ent in (s.get("writes") or []):
                if isinstance(ent, str) and ent not in written:
                    written.append(ent)
            for ent in (s.get("reads") or []):
                if isinstance(ent, str) and ent not in read:
                    read.append(ent)
        read_only = [e for e in read if e not in written]
        if written or read_only:
            lines.append(
                "**Entity access** — which entities the UI writes versus only reads. "
                "An entity the app writes must survive whatever durability its "
                "feature promises; an entity only ever read may be static, bundled, "
                "or fetched rather than stored:"
            )
            if written:
                lines.append(f"- written: {', '.join(written)}")
            if read_only:
                lines.append(f"- read-only: {', '.join(read_only)}")
            lines.append("")

    if screens:
        ids = [str(s.get("id") or s.get("name") or "") for s in screens]
        ids = [i for i in ids if i]
        nav = (man.get("shared_layout") or {}).get("nav")
        if isinstance(nav, dict):
            nav_desc = str(nav.get("type") or "navigation")
        elif isinstance(nav, str) and nav.strip():
            nav_desc = nav.strip()
        else:
            nav_desc = ""
        tail = f", with `{nav_desc}` navigation" if nav_desc else ""
        lines.append(
            f"**Screens** — the app has {len(ids)} screen(s){tail}: "
            + ", ".join(f"`{i}`" for i in ids)
            + ". Distinct screens the user moves between are a routing and "
            "code-splitting signal; how you route (or whether a library is warranted "
            "at all) is your call."
        )
        lines.append("")

    return "\n".join(lines)


def _feature_specs_for_stack(
    feature_specs: dict[str, Any] | None,
    ai_features: dict[str, Any] | None = None,
) -> str:
    """Render Brainstormer's ``feature_specs.json`` as a StackAdvisor block (D-SC1).

    The product-feature spine is StackAdvisor's *base* input: one behavioural
    block per MVP feature — AI *and* non-AI — so every feature, not only the AI
    ones, gets stack coverage. The AI catalog projection
    (``_ai_features_for_stack``) is enrichment layered on the AI subset; a feature
    an AI-catalog node *serves* is tagged ``(AI)`` here so the two views connect
    without the reader mistaking one feature for two. The serves relation is read
    from each node's ``vision_grounding.served_features[].id`` — never identity, as
    an AI node's own id (a capability surface id like
    ``adaptive_investigation_orchestration``) is distinct from the product-feature
    id it serves (``adaptive_investigation``). Per D-SC7 the product *signal* comes
    from this direct spine — each feature exactly once — not from vision_grounding's
    embedded feature copies (which repeat a product spec across every AI node that
    serves it); vision_grounding is consulted here only for the id join, not for
    content.

    Surfaces per feature the behavioural fields that force a component choice
    (``STACK_SPEC_FIELDS``) and the product-level ``dependencies`` (a chain signal,
    distinct from the AI ``requires`` DAG). The union of ``entities`` is offered as
    an advisory data model (D-SC6): a vocabulary and persistence signal, never a
    deterministic store mapping — the mechanism stays StackAdvisor's to choose.
    Finally, the project-wide ``nfr_goals`` are listed each keyed by a stable
    ``nfr_<slug>`` id (D-SC2), for the model to reference in an entry's
    ``satisfies_nfr`` when a stack decision is what makes a goal achievable.
    Returns ``""`` when no specs are present.
    """
    feats = (feature_specs or {}).get("features") or []
    if not feats:
        return ""

    # Product-feature ids that some AI node serves. The serves relation lives in
    # ``vision_grounding.served_features`` (an AI node serves a product feature —
    # never shares its id), so this is the only sound "is this feature AI-backed"
    # signal available without the manifest (D-SC5).
    ai_served: set[str] = set()
    for node in ((ai_features or {}).get("ai_features") or []):
        if not isinstance(node, dict) or node.get("kind") == INFRA_KIND:
            continue
        grounding = node.get("vision_grounding") or {}
        for sf in (grounding.get("served_features") or []):
            if isinstance(sf, dict):
                for key in ("id", "name"):
                    if sf.get(key):
                        ai_served.add(str(sf[key]))

    lines: list[str] = [
        "**Feature specifications (from Brainstormer) — the authoritative "
        "behavioural spec for every product feature. This is the base for your "
        "stack: choose libraries, persistence, and infrastructure that satisfy "
        "each feature's inputs, outputs, trigger, and reliability needs. Features "
        "tagged (AI) are also specified as AI capabilities below, where their "
        "implementation detail lives — treat that as enrichment on the same "
        "feature, not a second one.**\n"
    ]

    entities: list[str] = []
    seen: set[str] = set()
    for f in feats:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("id") or "")
        name = f.get("name") or fid or "unnamed"
        tag = " (AI)" if (fid and fid in ai_served) or name in ai_served else ""
        header = f"### `{name}`"
        if fid:
            # The linkage rules instruct the model to tag entries with these ids
            # (D-SC3); rendering only the name left it to infer them (D-SC14).
            header += f" — id: `{fid}`"
        lines.append(f"{header}{tag}")
        lines.extend(
            render_feature_block(f, fields=STACK_SPEC_FIELDS, include_graph=False)
        )
        deps = [
            str(d).strip() for d in (f.get("dependencies") or []) if str(d).strip()
        ]
        if deps:
            lines.append(f"- depends on: {', '.join(deps)}")
        lines.append("")
        for ent in (f.get("entities") or []):
            if isinstance(ent, str) and ent not in seen:
                seen.add(ent)
                entities.append(ent)

    if entities:
        lines.append(
            "**Domain vocabulary** — the data model these features operate on: "
            + ", ".join(entities)
            + ". These domain nouns are the persistence signal: features sharing "
            "entities read and write shared data, which drives your data-store and "
            "schema choices. Honour them as the vocabulary for stack decisions; the "
            "mechanism (which store, which schema) is yours to choose."
        )
        lines.append("")

    nfr_lines = [
        f"- `nfr_{slug(g.strip())}`: {g.strip()}"
        for g in ((feature_specs or {}).get("nfr_goals") or [])
        if isinstance(g, str) and g.strip()
    ]
    if nfr_lines:
        lines.append(
            "**Non-functional goals (project-wide)** — operational, performance, and "
            "reliability targets the stack must make achievable, each with a stable "
            "`nfr_<slug>` id. When a stack decision is what makes one of these achievable, "
            "record the id in that entry's `satisfies_nfr` (see the NFR linkage "
            "instruction), so the downstream planner can thread the goal into the phase "
            "that builds it:"
        )
        lines.extend(nfr_lines)
        lines.append("")

    return "\n".join(lines)


def _ai_served_feature_ids(ai_features: dict[str, Any] | None) -> set[str]:
    """Product-feature ids/names some surfaced AI node serves.

    Derived from ``vision_grounding.served_features`` on non-infrastructure
    catalog nodes — the only sound "is this feature AI-backed" signal without
    the manifest. Used for the spine's ``(AI)`` tag and as the guard in
    ``excluded_feature_ids`` (a served feature is never excluded).
    """
    served: set[str] = set()
    for node in ((ai_features or {}).get("ai_features") or []):
        if not isinstance(node, dict) or node.get("kind") == INFRA_KIND:
            continue
        grounding = node.get("vision_grounding") or {}
        for sf in (grounding.get("served_features") or []):
            if isinstance(sf, dict):
                for key in ("id", "name"):
                    if sf.get(key):
                        served.add(str(sf[key]))
    return served


def excluded_feature_ids(
    feature_specs: dict[str, Any] | None,
    ai_features: dict[str, Any] | None,
) -> set[str]:
    """Spine feature ids excluded from the plan by the Agentifier selection.

    D-PH1i / D-PH2b — the single source of truth for the excluded disposition,
    shared by the spine renderer (which tags) and ``check_phase_coverage``
    (which enforces), so the tag and the enforcement can never drift.

    Computed, not judged: a spine feature is excluded when a name in the AI
    catalog's ``explicitly_rejected`` matches its id/name (or their slugs)
    AND no surfaced AI node serves it via ``vision_grounding``. Rejected
    *members* (deselected sub-capabilities) match no spine id and never
    exclude anything; the serves-join wins over a same-named rejection.
    """
    feats = (feature_specs or {}).get("features") or []
    if not feats:
        return set()
    rejected: set[str] = set()
    for entry in ((ai_features or {}).get("explicitly_rejected") or []):
        name = entry.get("name") if isinstance(entry, dict) else entry
        if name:
            rejected.add(str(name))
            rejected.add(slug(str(name)))
    if not rejected:
        return set()
    served = _ai_served_feature_ids(ai_features)
    out: set[str] = set()
    for f in feats:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("id") or "")
        name = str(f.get("name") or fid)
        if not fid or fid in served or name in served:
            continue
        if (
            fid in rejected
            or slug(fid) in rejected
            or name in rejected
            or slug(name) in rejected
        ):
            out.add(fid)
    return out


def _feature_specs_for_phaser(
    feature_specs: dict[str, Any] | None,
    ai_features: dict[str, Any] | None = None,
) -> str:
    """Render Brainstormer's ``feature_specs.json`` as Phaser's spine block (D-PH1a).

    The product-feature spine is Phaser's *base* input: one behavioural block per
    MVP feature — AI *and* non-AI — so every feature the phases must build is on
    the table, including every feature of a no-AI app (which previously reached
    Phaser only as vision prose). The AI catalog block remains enrichment on the
    AI subset; a feature an AI-catalog node *serves* is tagged ``(AI)`` here so
    the two views connect without the reader mistaking one feature for two. Per
    the D-SC7 discipline the product signal comes from this direct spine — each
    feature exactly once — and ``vision_grounding`` is consulted only for the
    serves id join, never for content.

    Surfaces per feature the behavioural fields Phaser turns into phase content
    (``PHASER_PRODUCT_SPEC_FIELDS``: success criteria are verification raw
    material, failure modes are risk raw material, inputs/outputs anchor
    instructions), plus the product-level ``dependencies`` stated as build-order
    guidance (producer no later than consumer — a distinct graph from the AI
    ``requires`` DAG). The union of ``entities`` is offered as the shared domain
    vocabulary so phases name the same nouns consistently. Project-wide
    ``nfr_goals`` are listed with stable ``nfr_<slug>`` ids (D-SC2) and the
    Phaser-side citation rule (D-PH1c): cite the id in the verification criteria
    of the phases that build the claiming entries' features; never invent a
    stack claim for an unclaimed goal. Returns ``""`` when no specs are present.
    """
    feats = (feature_specs or {}).get("features") or []
    if not feats:
        return ""

    ai_served = _ai_served_feature_ids(ai_features)
    excluded = excluded_feature_ids(feature_specs, ai_features)

    lines: list[str] = [
        "**Feature specifications (from Brainstormer) — the authoritative "
        "behavioural spec for every product feature. This is the base of your "
        "plan: sequence phases so that ALL of these features are built — "
        "except any feature tagged (excluded), which the developer removed "
        "from this plan via the Agentifier selection — using "
        "each feature's success criteria as verification raw material and its "
        "failure modes as risk-assessment raw material. `depends on` means the "
        "named feature must be built no later than the feature that depends on "
        "it. Features tagged (AI) are also specified as AI capabilities in the "
        "AI features context below, where their implementation detail lives — "
        "treat that as enrichment on the same feature, not a second one. "
        "Declare each product feature a phase builds in that phase's "
        "`features` array using these exact ids; AI capabilities are declared "
        "separately in `capabilities` using the AI catalog ids.**\n"
    ]

    entities: list[str] = []
    seen: set[str] = set()
    for f in feats:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("id") or "")
        name = f.get("name") or fid or "unnamed"
        served = (fid and fid in ai_served) or name in ai_served
        if fid in excluded:
            tag = (
                " (excluded — AI implementation rejected at the Agentifier "
                "panel; to include it, revisit the Agentifier selection)"
            )
        else:
            tag = " (AI)" if served else ""
        header = f"### `{name}`"
        if fid:
            header += f" — id: `{fid}`"
        lines.append(f"{header}{tag}")
        lines.extend(
            render_feature_block(
                f, fields=PHASER_PRODUCT_SPEC_FIELDS, include_graph=False
            )
        )
        deps = [
            str(d).strip() for d in (f.get("dependencies") or []) if str(d).strip()
        ]
        if deps:
            lines.append(
                f"- depends on: {', '.join(deps)} (build these no later than "
                f"`{fid or name}`)"
            )
        lines.append("")
        for ent in (f.get("entities") or []):
            if isinstance(ent, str) and ent not in seen:
                seen.add(ent)
                entities.append(ent)

    if entities:
        lines.append(
            "**Domain vocabulary** — the data model these features operate on: "
            + ", ".join(entities)
            + ". Use these nouns consistently across every phase's instructions "
            "so phase N names the same concepts as phase 1; do not invent "
            "synonyms or parallel schemas for concepts already named here."
        )
        lines.append("")

    nfr_lines = [
        f"- `nfr_{slug(g.strip())}`: {g.strip()}"
        for g in ((feature_specs or {}).get("nfr_goals") or [])
        if isinstance(g, str) and g.strip()
    ]
    if nfr_lines:
        lines.append(
            "**Non-functional goals (project-wide)** — each with a stable "
            "`nfr_<slug>` id. The stack spec's `satisfies_nfr` fields record "
            "which stack choices make each goal achievable (the stack signal "
            "digest below indexes them). Cite the `nfr_<slug>` id in the "
            "verification criteria of the phases that build the claiming "
            "entries' features, so each goal is checked where it is delivered. "
            "A goal no stack entry claims must be surfaced to the developer as "
            "unclaimed — never invent a stack claim for it:"
        )
        lines.extend(nfr_lines)
        lines.append("")

    return "\n".join(lines)


def _stack_digest_for_phaser(
    stack: dict[str, Any] | None,
    feature_specs: dict[str, Any] | None = None,
) -> str:
    """Deterministic join-key digest of the stack spec (D-PH1b option A).

    The raw stack JSON stays in the seed as the authoritative approved-
    components list; this digest rides alongside it and makes the join keys
    legible as structure instead of prose-in-a-paste: which stack entries serve
    which product features (``serves_features``) and AI capabilities
    (``serves_capabilities``), which entries claim which non-functional goals
    (``satisfies_nfr``, with unclaimed goals named honestly), which entries are
    roadmap rather than build items (``status``), what each deployment target
    exposes (``exposure``), and the trustworthy negatives — the decisions the
    stack records by *absence*, which must not be re-asked or re-invented.

    Purely an index of the paste: it renders only what the stack carries and
    derives nothing except the ``nfr_<slug>`` ids (from ``feature_specs``, when
    supplied, so orphaned goals can be named). Returns ``""`` when the stack is
    absent or empty.
    """
    if not isinstance(stack, dict) or not stack:
        return ""
    inner = stack.get("stack_spec")
    spec = inner if isinstance(inner, dict) else stack
    entries = stack_signal_entries(stack)

    lines: list[str] = [
        "**Stack signal digest — a deterministic index of the join keys in the "
        "stack spec above. The JSON above remains the authoritative "
        "approved-components list; use this digest to route stack entries to "
        "the right phases.**\n"
    ]

    def backlinks(field: str) -> dict[str, list[str]]:
        links: dict[str, list[str]] = {}
        for e in entries:
            for target in e["entry"].get(field) or []:
                label = e["label"]
                if e["section"] and e["section"] not in label:
                    label = f"{label} ({e['section']})"
                links.setdefault(str(target), []).append(label)
        return links

    by_feature = backlinks("serves_features")
    if by_feature:
        lines.append(
            "Feature → stack backlinks (entries whose `serves_features` names "
            "the feature; make each entry available in the phases that build "
            "its feature):"
        )
        for fid in sorted(by_feature):
            lines.append(f"- `{fid}`: {', '.join(by_feature[fid])}")
        lines.append("")

    by_capability = backlinks("serves_capabilities")
    if by_capability:
        lines.append(
            "AI capability → stack backlinks (entries whose "
            "`serves_capabilities` names the AI catalog node):"
        )
        for cid in sorted(by_capability):
            lines.append(f"- `{cid}`: {', '.join(by_capability[cid])}")
        lines.append("")

    nfr_claims = backlinks("satisfies_nfr")
    derived: dict[str, str] = {}
    for g in ((feature_specs or {}).get("nfr_goals") or []):
        if isinstance(g, str) and g.strip():
            derived[f"nfr_{slug(g.strip())}"] = g.strip()
    if nfr_claims or derived:
        lines.append(
            "Non-functional goals — stack claims (`satisfies_nfr`). Cite the "
            "`nfr_<slug>` id in the verification criteria of the phases that "
            "build the claiming entries' features:"
        )
        for nid in sorted(set(nfr_claims) | set(derived)):
            claimers = nfr_claims.get(nid)
            if claimers:
                unknown = "" if (not derived or nid in derived) else (
                    " [matches no project goal]"
                )
                lines.append(f"- `{nid}`{unknown}: claimed by "
                             f"{', '.join(sorted(set(claimers)))}")
            else:
                lines.append(
                    f"- `{nid}`: UNCLAIMED — no stack entry claims this goal. "
                    "Surface it to the developer as unclaimed; do NOT invent a "
                    "stack claim or an implementation for it."
                )
        lines.append("")

    status_entries = [e for e in entries if e["entry"].get("status")]
    lines.append(
        "Status semantics: entries with `status: optional` or `status: "
        "deferred` are ROADMAP, not build items — never place them in a "
        "phase's dependencies or instructions."
    )
    if status_entries:
        for e in status_entries:
            label = e["label"]
            if e["section"] and e["section"] not in label:
                label = f"{label} ({e['section']})"
            lines.append(f"- {label}: status `{e['entry']['status']}`")
    else:
        lines.append(
            "- No entry carries a status in this stack: every entry is a "
            "build item."
        )
    lines.append("")

    targets = ((spec.get("deployment") or {}).get("targets") or [])
    exposure_lines = []
    for t in targets:
        if not isinstance(t, dict):
            continue
        exp = t.get("exposure")
        if isinstance(exp, dict) and exp:
            detail = "; ".join(f"{k}={v}" for k, v in exp.items())
            exposure_lines.append(f"- {t.get('name') or 'target'}: {detail}")
    if exposure_lines:
        lines.append(
            "Deployment exposure per target (wire these into the phases that "
            "set up each target):"
        )
        lines.extend(exposure_lines)
        lines.append("")

    lines.append(
        "Trustworthy negatives — absence in the stack is a recorded decision, "
        "not an omission; do not re-ask for or re-invent what is absent:"
    )
    security = spec.get("security")
    no_auth = security is None or (
        isinstance(security, dict)
        and not any(v for v in security.values())
    )
    if no_auth:
        lines.append(
            "- `security` is absent or empty: this app has no accounts or "
            "authentication. Plan no auth, login, or user-management work."
        )
    if not spec.get("integrations"):
        lines.append(
            "- `integrations` is absent or empty: this app uses no external "
            "integrations beyond any AI providers listed above."
        )
    lines.append(
        "- An entry with no `serves_features` is a global staple serving the "
        "whole app, not any single feature."
    )
    lines.append("")

    return "\n".join(lines)


def _manifest_for_phaser(manifest: dict[str, Any] | None) -> str:
    """Deterministic projection of Designer's ``manifest.json`` (D-PH1d).

    Surfaces the manifest's structure with its join keys legible: screens
    (audience, purpose, surface membership) and one line per surface carrying
    the two id-space keys — ``implements_feature_ids`` (product-feature ids,
    pinned deterministically by ``enrich_manifest``) and ``catalog_surface_id``
    (AI catalog-node id, on AI surfaces) — plus the entity footprint
    (``reads``/``writes``) and the within-mock ordering hint (``depends_on``,
    advisory). The three surface dispositions are annotated inline: a feature
    surface joins its feature's phases; an empty-``implements`` surface is
    scaffolding (not covered by any feature's phases — it must be planned
    deliberately); a ``screen: null`` surface is internal, non-UI work for its
    feature. ``screen`` may be a string or a list across draws; both render.
    Surface *names and counts* are non-deterministic across mock regens — ids
    and dispositions are the stable join surface, which is why this projection
    leads with them. Returns ``""`` when no manifest or no surfaces.
    """
    surfaces = (manifest or {}).get("surfaces") or []
    if not surfaces:
        return ""

    lines: list[str] = [
        "**UI design manifest (from Designer) — screens and surfaces with "
        "their join keys. `implements` holds product-feature ids; `catalog` "
        "holds the AI catalog-node id realized by the surface.**\n"
    ]

    screens = (manifest or {}).get("screens") or []
    if screens:
        lines.append("Screens:")
        for s in screens:
            if not isinstance(s, dict):
                continue
            sid = s.get("id") or "screen"
            audience = s.get("audience") or "unspecified audience"
            purpose = s.get("purpose") or ""
            members = ", ".join(str(x) for x in (s.get("surfaces") or []))
            line = f"- `{sid}` ({audience}): {purpose}"
            if members:
                line += f" — surfaces: {members}"
            lines.append(line)
        lines.append("")

    lines.append("Surfaces:")
    for s in surfaces:
        if not isinstance(s, dict):
            continue
        lines.append(surface_summary_line(s))
    lines.append("")

    lines.append("How to read the surfaces:")
    lines.append(
        "- Group surfaces by product-feature id when attaching UI work to a "
        "feature's phases — one feature may be realized by several surfaces."
    )
    lines.append(
        "- Several surfaces may realize ONE AI capability (same `catalog` id): "
        "the capability is one unit of work; its surfaces are views onto it."
    )
    lines.append(
        "- A surface with empty `implements` is scaffolding: no feature's "
        "phases cover it, so place it deliberately (a foundational phase, or "
        "defer it) and say which."
    )
    lines.append(
        "- `after` is the mock's within-UI ordering hint (advisory), not a "
        "build-order constraint."
    )
    lines.append("")

    entity_list = (manifest or {}).get("entities") or []
    ent_lines = []
    for ent in entity_list:
        if isinstance(ent, dict) and ent.get("name"):
            fields = ", ".join(str(x) for x in (ent.get("fields") or []))
            ent_lines.append(
                f"- {ent['name']}: {fields}" if fields else f"- {ent['name']}"
            )
    if ent_lines:
        lines.append(
            "Design entities (the design's data vocabulary; align phase data "
            "models with these fields):"
        )
        lines.extend(ent_lines)
        lines.append("")

    return "\n".join(lines)
