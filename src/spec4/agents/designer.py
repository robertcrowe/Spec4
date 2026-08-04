from __future__ import annotations

import json
import logging
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TypedDict

import litellm

from spec4.agents._manifest import MANIFEST_END, MANIFEST_START
from spec4.websearch import WEB_SEARCH_TOOL, search as web_search

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
    "You are an expert UI/UX designer generating a self-contained HTML mock-up "
    "of a working software application. You are given a project vision (purpose, "
    "target audiences, and key features) and, when the product has AI features, "
    "a list of user-facing AI surfaces describing what each AI feature does, what "
    "the user provides, what result it returns, and how it should be presented. "
    "Use both as your primary design input. "
    "Design the actual application, not a marketing landing page. Organise it as "
    "one screen per target audience (for example, an end-user screen and an "
    "administrator screen), all within the single HTML document and reachable "
    "through in-page navigation — a nav bar or tabs. Give each audience the "
    "screen it needs. "
    "Turn every user-facing AI surface into a real, in-context interaction on the "
    "relevant screen: build its inputs into real form controls, show its output "
    "as a realistic result, trigger it as described, and apply its noted "
    "affordance — suggestion, confirmation, streaming, background notification, or "
    "multi-step progress. Nest each surface's component-step outputs (citations, "
    "confidence, routing, related items) inside that surface rather than as "
    "separate cards. Also design the vision's user-facing features that are not "
    "AI-driven. Do not reduce features to a 'how it works' marketing grid — show "
    "them working. "
    "The mock-up will be shown to the project owner for approval and will serve "
    "as a visual reference for downstream development, so it must be polished and "
    "realistic: use the project's actual name and feature names (not Lorem ipsum "
    "or generic placeholder text) and realistic sample content drawn from the "
    "vision and AI-surface data, with a coherent colour scheme and typography. "
    "You write HTML, CSS, and JavaScript directly — no frameworks, no external "
    "assets, no CDN links. All CSS goes inside a <style> block in <head> and all "
    "JavaScript goes inside a <script> block at the end of <body>. The output "
    "must be a single complete HTML document."
)

_SYSTEM_PROMPT_REFINE = (
    "You are an expert UI/UX designer. You will receive an existing HTML mock-up "
    "followed by a refinement request. Apply the requested changes precisely and "
    "preserve everything that was not explicitly asked to change — do not "
    "redesign, refactor, or improve unrequested parts. When feedback is "
    "ambiguous, apply the most conservative interpretation that satisfies the "
    "request. "
    "You write HTML, CSS, and JavaScript directly — no frameworks, no external "
    "assets, no CDN links. All CSS goes inside a <style> block in <head> and all "
    "JavaScript goes inside a <script> block at the end of <body>. The output "
    "must be a single complete HTML document."
)

_HTML_INSTRUCTION = (
    "Generate a single self-contained HTML file for the working application, "
    "organised as one screen per target audience with in-page navigation between "
    "them. Use the project vision above — name, purpose, key features, and target "
    "audiences — and the user-facing AI surfaces to inform every design decision: "
    "which screens exist, their layout, colour, typography, and content. Design "
    "each AI surface as a real interaction (its inputs as controls, its output as "
    "a result, its affordance applied), design the non-AI user-facing features "
    "too, and use realistic content drawn from the vision and surface data rather "
    "than placeholder text. "
    "Place all CSS inside a <style> block in <head> and all JavaScript inside a "
    "<script> block at the bottom of <body>. Do not use external CDN links or "
    "import statements. "
    "Output ONLY the HTML document — no introduction, no explanation, no "
    "recap, no markdown commentary before or after the code."
)

_SYSTEM_PROMPT_CAPTURE = (
    "You are an expert UI/UX designer. You will receive source code from an "
    "existing web application and must produce a self-contained HTML mock-up "
    "that faithfully captures its current look and feel — this is a reference "
    "baseline, not a redesign. Match the colour scheme, typography, spacing, "
    "layout, and component shapes as closely as possible. When the source uses "
    "a framework (React, Vue, Svelte, etc.), translate the component structure "
    "into equivalent semantic HTML with matching styles — do not attempt to "
    "reproduce the framework runtime. If screenshots are provided, they take "
    "precedence over source code for all visual decisions. "
    "You write HTML, CSS, and JavaScript directly — no frameworks, no external "
    "assets, no CDN links. All CSS goes inside a <style> block in <head> and all "
    "JavaScript goes inside a <script> block at the end of <body>. The output "
    "must be a single complete HTML document."
)

_HTML_REFINEMENT_INSTRUCTION = (
    "Apply the requested changes to the existing mock shown above. Preserve "
    "everything not explicitly changed — do not improve, refactor, or redesign "
    "unrequested parts. Place all CSS inside a <style> block in "
    "<head> and all JavaScript inside a <script> block at the bottom of <body>. "
    "Do not use external CDN links or import statements. "
    "Output ONLY the complete updated HTML document — no introduction, no "
    "explanation, no recap, no markdown commentary before or after the code."
)

_HTML_CAPTURE_INSTRUCTION = (
    "Generate a single self-contained HTML file that faithfully recreates the "
    "landing page or starting screen from the source code above. Preserve the "
    "existing colour scheme, typography, spacing, and layout exactly — this is "
    "a baseline reference, not a redesign. If the source uses a framework, "
    "translate the component structure into equivalent semantic HTML with "
    "matching styles. "
    "Place all CSS inside a <style> block in <head> and all JavaScript inside "
    "a <script> block at the bottom of <body>. Do not use external CDN links "
    "or import statements. "
    "Output ONLY the HTML document — no introduction, no explanation, no "
    "recap, no markdown commentary before or after the code."
)


class DesignerSession(TypedDict):
    step: int
    preference_text: str
    screenshots: list[dict[str, str]]
    mock_html: str
    finalized: bool


def _unwrap(obj: dict[str, object], envelope_key: str) -> dict[str, object]:
    """Unwrap a {envelope_key: {...}} envelope if present, else return obj as-is.

    Spec4 stores artifacts in their LLM-emitted envelope form (e.g.
    ``session["code_review"] == {"code_review": {...}}``). Detection helpers
    accept either the envelope or the inner dict so callers don't have to
    care which form they hold.
    """
    inner = obj.get(envelope_key)
    if isinstance(inner, dict):
        return inner
    return obj


def detect_no_ui(
    vision: dict[str, object],
    code_review: dict[str, object],
) -> bool:
    """Return True if the project appears to have no graphical UI.

    Preference order:
    1. ``code_review.ui_summary.has_ui`` (structured signal — schema_version 1+)
    2. ``vision.ui_surface`` or ``vision.ui_type`` matched against the no-UI
       keyword list (Brainstormer captures the UI surface as topic 5)
    3. Free-text keyword sweep over a handful of legacy fields, for older
       reviews and visions that predate the structured fields
    """
    cr_inner = _unwrap(code_review, "code_review")
    ui_summary = cr_inner.get("ui_summary")
    if isinstance(ui_summary, dict):
        has_ui = ui_summary.get("has_ui")
        if has_ui is False:
            return True
        if has_ui is True:
            return False

    v_inner = _unwrap(vision, "vision_statement")
    vision_block = v_inner.get("vision")
    if isinstance(vision_block, dict):
        v_inner = {**v_inner, **vision_block}

    for obj in (v_inner, cr_inner):
        for field in (
            "purpose",
            "project_type",
            "description",
            "vision",
            "ui_type",
            "ui_surface",
        ):
            val = obj.get(field)
            if isinstance(val, str):
                lower = val.lower()
                if any(kw in lower for kw in _NO_UI_KEYWORDS):
                    return True
    return False


def detect_has_ui_source(project_root: Path, design_dir: Path | None = None) -> bool:
    """Return True if mock.html exists or the project contains UI source files."""
    if design_dir is not None and (design_dir / "mock.html").exists():
        return True
    for root, dirs, files in project_root.walk():
        dirs[:] = sorted(d for d in dirs if d not in _EXCLUDED_DIRS)
        for fname in files:
            if Path(fname).suffix.lower() in _UI_EXTENSIONS:
                return True
    return False


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


def save_manifest(manifest: dict[str, Any], design_dir: Path) -> None:
    """Write the design manifest to design_dir/manifest.json (D-DM)."""
    design_dir.mkdir(parents=True, exist_ok=True)
    (design_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def clear_session(design_dir: Path) -> None:
    """Delete session.json and mock.html from design_dir if they exist."""
    for name in ("session.json", "mock.html", "manifest.json"):
        f = design_dir / name
        if f.exists():
            f.unlink()


# ---------------------------------------------------------------------------
# Revision mode — deterministic helpers (no LLM)
# ---------------------------------------------------------------------------


def revision_delta(vision: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return this round's revision delta, or ``None`` for a greenfield vision.

    A revision round's vision carries an accumulating ``revision_history`` (each
    round contributes one entry, stamped deterministically by Brainstormer); its
    final entry is the delta for the current round — ``goal``, the
    ``key_features_mvp`` name changes (``added`` / ``modified`` / ``removed``),
    and ``rationale``. A greenfield vision has no ``revision_history``. The input
    is the session-form vision envelope (``{"vision_statement": {...}}``).
    """
    vs = (vision or {}).get("vision_statement") if isinstance(vision, dict) else None
    history = vs.get("revision_history") if isinstance(vs, dict) else None
    if isinstance(history, list) and history:
        last = history[-1]
        return last if isinstance(last, dict) else None
    return None


def build_revision_note(delta: dict[str, Any]) -> str:
    """Render a revision delta into a refinement note for the carry-forward flow.

    Produces a single bracketed instruction (same shape as the staleness note)
    that scopes the refine to this revision's ``key_features_mvp`` changes while
    preserving the established look and feel. Deterministic — the
    ``added`` / ``modified`` / ``removed`` names come straight from the
    Brainstormer-stamped delta; the model never authors them.
    """
    changes = delta.get("changes") or {}
    added = list(changes.get("added") or [])
    modified = list(changes.get("modified") or [])
    removed = list(changes.get("removed") or [])
    goal = (delta.get("goal") or "").strip()

    segments: list[str] = ["[This is a design revision of the existing mock."]
    if goal:
        segments.append(f" Goal: {goal}")
    clauses: list[str] = []
    if added:
        clauses.append("added features (" + ", ".join(added) + ")")
    if modified:
        clauses.append("changed features (" + ", ".join(modified) + ")")
    if removed:
        clauses.append("removed features (" + ", ".join(removed) + ")")
    if clauses:
        segments.append(
            " Update the mock to reflect this revision's " + "; ".join(clauses) + "."
        )
    segments.append(
        " Preserve the existing look and feel — colour scheme, typography, "
        "spacing, layout, and every screen or element these changes do not "
        "touch. Change only what these feature updates require.]"
    )
    return "".join(segments)


_MANIFEST_INSTRUCTION = (
    "## Output format: plan the manifest, then build the mock\n\n"
    "Produce your response in exactly two parts, in this order, with nothing "
    "else before, between (other than the sentinels), or after:\n\n"
    "1. A **design manifest** — a single JSON object describing what you are about "
    "to build — wrapped exactly in these sentinel lines:\n\n"
    "" + MANIFEST_START + "\n"
    "{ ...the JSON object... }\n"
    "" + MANIFEST_END + "\n\n"
    "2. The complete HTML document. The HTML-output rules stated above apply to "
    "this part, and the HTML must realize the manifest exactly — the same screens "
    "with the same surfaces placed on them. Design the manifest first, then render "
    "the HTML to match it.\n\n"
    "Manifest schema:\n"
    "- `entities`: [{name, fields[]}] — the conceptual data the UI presents and "
    "edits (e.g. Policy, Question). This is a shared vocabulary, NOT a database "
    "schema; do not invent storage or endpoints. Reflect the Domain vocabulary "
    "from the feature specifications above where those concepts are data the UI "
    "presents or edits, adding UI-specific entities as needed.\n"
    "- `screens`: [{id, audience, purpose, surfaces[]}] — one screen per target "
    "audience; `surfaces` lists the surface names placed on that screen.\n"
    "- `surfaces`: [{name, kind, screen, implements_features[], inputs[], output, "
    "states[], reads[], writes[], depends_on[]}] — one entry per user-facing UI "
    "surface. Cover every user-facing non-AI vision feature (kind: \"non_ai\"), "
    "and realize every AI surface listed above through one or more UI surfaces "
    "(kind: \"ai\"). `implements_features` names only the vision feature(s) this "
    "surface genuinely realizes — leave it empty (`[]`) for a surface that no MVP "
    "feature covers (setup/config, history, or a surface serving an audience whose "
    "needs are not in the feature set), rather than attributing it to an unrelated "
    "feature; "
    "`inputs` are the form controls; `output` is the result shown; `states` are "
    "the UI states to design (e.g. idle, loading, empty, error); `reads`/`writes` "
    "name `entities`; `depends_on` names other surfaces that must exist first (a "
    "detail needs its list, an edit needs the record). For kind \"ai\" also "
    "include `affordance`, `invocation`, and `catalog_surface` — the exact name "
    "from the AI-surfaces list above that this surface realizes (if you split one "
    "AI capability across several UI surfaces, each names the same "
    "`catalog_surface`).\n"
    "- `shared_layout`: {nav, shell[]} — the app frame (nav style and shell "
    "components), built before per-screen features.\n"
)

# Capture mode recreates the UI that already exists, so the manifest must
# describe that — not the app the vision plans. Without this the schema above
# ("one screen per target audience", "cover every user-facing vision feature")
# reads as an instruction to invent screens the source code does not have, or
# to skip the manifest entirely as inapplicable (D-DM7). Surfaces that no
# planned feature covers are a legitimate outcome here — `design_manifest`
# calls them scaffolding and attaches them to no phase.
_MANIFEST_CAPTURE_NOTE = (
    "\n**Capture mode — describe what you recreated.** The manifest above must "
    "describe the existing UI you are reproducing, not the application the "
    "vision plans. Include one screen entry per screen you actually recreated, "
    "and one surface per UI surface actually present in the source. Do not "
    "invent screens, surfaces, or audiences that the existing UI does not "
    "have. Use the vision and feature specifications only to *name* what you "
    "found: set `implements_features` where a surface genuinely realizes a "
    "planned feature, and leave it empty (`[]`) otherwise — most surfaces in a "
    "baseline capture will have it empty, which is correct and expected.\n"
)

# A refinement changes the mock, so it must change the manifest too (D-DM9).
# Before this, the manifest was written once by the initial draw and never
# revisited, so a heavily-refined mock shipped a manifest describing a design
# that no longer existed — and Phaser attached UI work per surface from that
# stale record. Re-emitting in full rather than as a diff matches how the
# artifact is consumed (whole-file load) and how `design_manifest` treats it:
# names and counts are expected to vary across draws, and the stable join
# surface is the derived id pair, which `enrich_manifest` re-pins every time.
_MANIFEST_REFINE_NOTE = (
    "\n**Refinement — re-state the manifest for the updated mock.** Emit the "
    "complete manifest describing the mock *after* your changes, not a diff and "
    "not the manifest of the mock you were given. Carry every screen, surface, "
    "and entity that survives the refinement through unchanged, add entries for "
    "anything the refinement introduces, and drop entries for anything it "
    "removes. If the refinement is purely visual (colour, spacing, copy, "
    "typography) the manifest will be identical to the design it describes — "
    "re-state it anyway.\n"
)


def build_mock_prompt(
    session: DesignerSession,
    ui_source_snippets: list[str],
    image_support: bool,
    planning_context: dict[str, Any] | None = None,
    existing_html: str | None = None,
    capture_mode: bool = False,
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
    if planning_context and planning_context.get("vision_statement"):
        from spec4.agents._utils import _slim_vision_framing
        framing = _slim_vision_framing(planning_context["vision_statement"])
        if framing:
            parts.append({
                "type": "text",
                "text": (
                    "## Project Vision\n\n"
                    "Use the following project framing to inform global design "
                    "(purpose, UI surface, audiences, and differentiators). The "
                    "per-feature substance is in the feature specifications "
                    "below:\n\n"
                    + json.dumps(framing, indent=2)
                    + "\n\n---"
                ),
            })
    if planning_context and planning_context.get("feature_specs"):
        from spec4.agents._utils import _feature_specs_for_designer
        specs_note = _feature_specs_for_designer(planning_context["feature_specs"])
        if specs_note:
            parts.append({
                "type": "text",
                "text": "## Feature Specifications\n\n" + specs_note + "\n---",
            })
    if planning_context and planning_context.get("ai_features"):
        from spec4.agents._utils import _ai_features_for_designer
        ai_note = _ai_features_for_designer(planning_context["ai_features"])
        if ai_note:
            parts.append({
                "type": "text",
                "text": "## User-Facing AI Surfaces\n\n" + ai_note + "\n---",
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
        label = (
            "Existing UI source code — recreate its look and feel:\n\n"
            if capture_mode
            else "Existing UI code for reference (use as starting point):\n\n"
        )
        parts.append({"type": "text", "text": label + combined})
    if existing_html:
        instruction = _HTML_REFINEMENT_INSTRUCTION
        system = _SYSTEM_PROMPT_REFINE
    elif capture_mode:
        instruction = _HTML_CAPTURE_INSTRUCTION
        system = _SYSTEM_PROMPT_CAPTURE
    else:
        instruction = _HTML_INSTRUCTION
        system = _SYSTEM_PROMPT
    parts.append({"type": "text", "text": instruction})
    # Every draw is manifest-bearing (D-DM9). The mode-specific note comes
    # after the shared schema; a refine is a refine even if the flag is set.
    manifest_text = _MANIFEST_INSTRUCTION
    if existing_html:
        manifest_text += _MANIFEST_REFINE_NOTE
    elif capture_mode:
        manifest_text += _MANIFEST_CAPTURE_NOTE
    parts.append({"type": "text", "text": manifest_text})
    return [
        {"role": "system", "content": system},
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
_MAX_UI_FILE_CHARS = 8_000


def collect_ui_source_files(project_root: Path) -> list[str]:
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
            if len(content) > _MAX_UI_FILE_CHARS:
                content = content[:_MAX_UI_FILE_CHARS] + "\n# [truncated]"
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
    search_config: Any = None,
    stop_event: threading.Event | None = None,
    planning_context: dict[str, Any] | None = None,
    existing_html: str | None = None,
    capture_mode: bool = False,
    api_base: str | None = None,
    extra_kwargs: dict[str, Any] | None = None,
) -> Iterator[str]:
    messages: list[dict[str, Any]] = build_mock_prompt(
        session, ui_source_snippets, image_support, planning_context, existing_html,
        capture_mode,
    )
    tools: list[dict[str, Any]] | None = [WEB_SEARCH_TOOL] if search_config else None

    logger.debug("Sending input to model...")

    try:
        while True:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": True,
            }
            if api_key:
                kwargs["api_key"] = api_key
            if api_base is not None:
                kwargs["api_base"] = api_base
            if extra_kwargs:
                kwargs.update(extra_kwargs)
            if tools:
                kwargs["tools"] = tools

            response = litellm.completion(**kwargs)
            logger.debug("Awaiting first output token")

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
                    logger.debug("Chunk %d: no choices", chunk_count)
                    continue

                last_finish_reason = getattr(choice, "finish_reason", None)
                delta = choice.delta
                content = getattr(delta, "content", None) or ""
                tc_deltas = getattr(delta, "tool_calls", None)

                if chunk_count <= 3 or tc_deltas:
                    logger.debug(
                        "Chunk %d: content=%r tool_calls=%s finish_reason=%s",
                        chunk_count, content, bool(tc_deltas), last_finish_reason,
                    )

                if content:
                    full_text += content
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

            logger.debug(
                "Iteration complete — %d chunks, finish_reason=%s",
                chunk_count, last_finish_reason,
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
                    logger.debug("Tool call: %s args=%s", tc["name"], tc["arguments"])
                    if tc["name"] == "web_search":
                        try:
                            query = json.loads(tc["arguments"]).get("query", "")
                        except (json.JSONDecodeError, KeyError):
                            query = tc["arguments"]
                        logger.debug("Web search: %r", query)
                        result = web_search(query, search_config)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        })
                continue

            break

        logger.debug("Output complete")
        yield "__DONE__"

    except Exception as exc:
        # Use warning + exc_info so the actual exception type and traceback
        # land in the server log unconditionally — debug-level was hiding
        # litellm errors behind logger config, leaving only the unhelpful
        # "Give Feedback / Get Help" banner that litellm prints itself.
        logger.warning("Designer generation failed", exc_info=True)
        msg = str(exc).strip() or repr(exc)
        yield f"__GENERATION_ERROR__: {type(exc).__name__}: {msg}"
