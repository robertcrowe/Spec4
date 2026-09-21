"""Designer's mock generation -- the background draw and everything it needs.

Cleanup Phase 4h turned ``callbacks/designer.py`` into a package and moved the
three self-contained concerns into siblings, one module each. This one owns the
generation core: the LLM connection parameters and the planning context every
draw resolves, the process-global ``MOCK_BUFFERS`` a draw writes into,
``_start_gen`` and its worker thread, and the extraction, persistence and
progress-sizing helpers that worker calls.

It registers no callback. The package polls the buffer
(``on_mock_stream_poll``), and ``_wizard`` and ``_refine`` start their draws
through ``_start_gen``; nothing here imports any of the three.

``MOCK_BUFFERS`` is the one name 4h spells differently -- public here, because
it is the module's cross-module surface -- and the modules that had it as
``_MOCK_BUFFERS`` import it under that name, binding the same dict object.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import re
import threading
import time
import uuid
from typing import Any

from spec4.app_constants import (
    ARTIFACT_MANIFEST,
)
from spec4 import llm, llm_selection, project_manager, websearch
from spec4.agents._manifest import (
    enrich_manifest,
    extract_manifest,
    validate_manifest,
)
from spec4.agents.designer import (
    THINKING_MARK,
    DesignerSession,
    collect_ui_source_files,
    generate_mock_streaming,
    save_manifest,
    save_mock,
    save_session,
)

logger = logging.getLogger(__name__)
_DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"
# keyed by gen_id stored in designer-session-store["_gen_id"]
# _run() is the sole writer of buf["text"] / buf["final_html"]; poll callbacks
# only read them.  CPython's GIL makes this single-writer pattern safe without
# a lock.  When _run() finishes extraction, on_mock_stream_poll picks up
# buf["final_html"] and pushes the completed mock straight to
# designer-session-store — no intermediary signal store needed.
#
# Each entry also records ``design_dir`` (the round it draws for, as a string,
# or None) and ``started`` (``time.monotonic()`` at launch). The first is how
# a rebuilt page finds the draw it lost: ``render_page`` recreates the two
# memory stores from disk on every ``session`` write and every browser load,
# and the new store carries no ``_gen_id``, so ``find_live_draw`` looks the
# draw up by round instead. The second is what the poll reports as ``elapsed``
# while no text has arrived yet. A server restart is still the end of a draw:
# this dict, and the thread, die with the process.
MOCK_BUFFERS: dict[str, dict[str, Any]] = {}
_MAX_HTML_BYTES = 512_000
# Progress-bar denominator when there is no prior round to size against: the
# rough character count of a typical mock + manifest stream.
_DEFAULT_EXPECTED_CHARS = 70_000
# The bar's ceiling while text is still arriving; see ``stream_progress``.
_MAX_LIVE_PROGRESS = 99
# The poll's cadence, in ms, from the tick that finds the finished mock until
# the browser acknowledges it. The delivery response carries the whole mock
# (up to 512 kB), and dash-renderer discards the older of two in-flight
# requests of the same callback, so the period must exceed the time that
# response takes to arrive, parse and apply, plus the step-6 render it
# triggers. `POLL_MS` (layouts.designer) is the running cadence.
DELIVERY_MS = 2000
# Safety valve on completion re-delivery: 60 ticks × 2 s ≈ 2 minutes.
# Delivery is acknowledgement-based (see on_mock_stream_poll) — the payload is
# re-emitted until the browser's own poll request proves the store applied it —
# so this cap exists only to stop an unacknowledged loop from re-sending a
# ~512 kB payload forever (e.g. the tab was closed mid-generation and Dash
# keeps replaying a stale queued tick).  It is not a delivery window: under
# normal operation the ack arrives on the first tick after the payload lands.
_MAX_DELIVERY_TICKS = 60
# Seconds without a chunk before the counter line says so. A model that
# reasons between output bursts goes quiet for minutes with the count
# unchanged, which reads exactly like a page that stopped updating.
PAUSE_NOTICE_S = 15
# How many of a broken mock's errors the fix draw quotes back to the model;
# the rest are counted. The same cap the Phaser retry uses.
MOCK_ERROR_LIMIT = 15


def _llm_params(
    session: dict[str, Any], image_support: bool | None
) -> tuple[
    str,
    str,
    websearch.SearchConfig | None,
    str | None,
    bool,
    str | None,
    dict[str, Any],
    str,
]:
    """Extract LLM connection parameters from the main session dict.

    Designer has no chat turn, so this is its equivalent of the resolution in
    ``session.get_agent_gen``: the six generation callbacks all come through
    here, and resolving once covers them all. The model is taken from the
    resolved config rather than ``session["model"]`` — the latter names the
    default, which is the wrong answer whenever Designer has an override.

    Image support is likewise per-agent: a Designer pinned to a text-only model
    must disable screenshot upload even though the default model is multimodal.
    The store-wide flag is the fallback, and an unknown still means capable.

    Effort comes out of the same resolved config as the model, so a Designer on
    an override draws at that override's effort and one on the default inherits
    the default's — the same rule, not a second one.
    """
    llm_config: dict[str, Any] = llm_selection.resolve(session, "designer") or {}
    api_base: str | None = llm_config.get("api_base")
    aws_kwargs = {k: v for k, v in llm_config.items() if k.startswith("aws_")}
    support = llm_selection.capability(
        session, "designer", "image_support", image_support
    )
    return (
        llm_config.get("model") or "",
        llm_config.get("api_key") or "",
        websearch.from_session(session),
        session.get("working_dir"),
        bool(support) if support is not None else True,
        api_base,
        aws_kwargs,
        str(llm_config.get("effort") or llm_selection.DEFAULT_EFFORT),
    )


def _planning_ctx(
    session: dict[str, Any], working_dir: str | None
) -> dict[str, Any] | None:
    """Assemble the vision / AI-catalog / feature-spec context for a generation.

    D-DM7: the capture ("Modify existing") generation used to pass nothing here,
    yet still carried `_MANIFEST_INSTRUCTION` — whose schema tells the model to
    reflect "the feature specifications above" and realize "every AI surface
    listed above". With no planning context those sections are absent from the
    prompt, so the manifest was being asked for against inputs that were not
    there, and brownfield runs routinely came back HTML-only with no manifest.

    The AI catalog and feature specs are sourced from disk so the prompt
    reflects the current `ai_features.json` / `feature_specs.json` (which
    upstream edits like a feature deselection write) rather than a possibly
    stale session snapshot; the session copy is the fallback when no working
    directory is available.
    """
    vision = session.get("vision_statement")
    if not vision:
        return None
    ai_features = (
        project_manager.load_ai_features(working_dir) if working_dir else None
    ) or session.get("ai_features")
    feature_specs = (
        project_manager.load_feature_specs(working_dir) if working_dir else None
    ) or session.get("feature_specs")
    return {
        "vision_statement": vision,
        **({"ai_features": ai_features} if ai_features else {}),
        **({"feature_specs": feature_specs} if feature_specs else {}),
    }


def extract_html(text: str) -> str | None:
    """Extract an HTML document from model output, returning None if not found.

    The **last** complete document wins, not the first. Some models write a
    draft, think better of it mid-response ("Wait — I need to redesign this")
    and write a second one; taking the first would ship the draft the model
    itself discarded. A model that emits one document is unaffected, and a
    trailing fragment without a closing tag never matches, so a completed
    earlier document still beats an abandoned later one.
    """
    matches: list[str] = re.findall(
        r"(<!DOCTYPE html>.*?</html>|<html[\s>].*?</html>)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if matches:
        return matches[-1].strip()
    code_matches: list[str] = re.findall(r"```(?:html)?\s*(.*?)\s*```", text, re.DOTALL)
    for inner in reversed(code_matches):
        inner = inner.strip()
        if "<html" in inner.lower() or "<!doctype" in inner.lower():
            return inner
    return None


_SCRIPT_OPEN = re.compile(r"<script\b[^>]*>", re.IGNORECASE)
_SCRIPT_CLOSE = re.compile(r"</script\s*>", re.IGNORECASE)
_STYLE_OPEN = re.compile(r"<style\b[^>]*>", re.IGNORECASE)
_STYLE_CLOSE = re.compile(r"</style\s*>", re.IGNORECASE)
_SCRIPT_BODY = re.compile(
    r"<script\b[^>]*>(.*?)</script\s*>", re.IGNORECASE | re.DOTALL
)
_UNESCAPED_BACKTICK = re.compile(r"(?<!\\)`")


def check_mock_html(html_text: str, *, truncated: bool = False) -> list[str]:
    """The structural defects a mock document has, as sentences; [] when clean.

    Deterministic and static: what the text alone can show. Runtime errors
    -- the exception a script throws, the resource that fails to load -- are
    the browser's to find, and the preview's shim reports them the same way
    (``layouts.designer.MOCK_ERROR_SHIM``). Both lists feed the fix draw.

    Advisory: nothing here stops a mock from saving or being shown. A false
    positive costs the developer one line of text and a button they need not
    press; a blocked mock costs them the draw.
    """
    errors: list[str] = []
    if truncated:
        errors.append(
            f"The document was cut off at {_MAX_HTML_BYTES // 1000} kB and is "
            "incomplete; it must be shorter."
        )
    lower = html_text.lower()
    if "</body>" not in lower or "</html>" not in lower:
        errors.append("The document does not end with </body> and </html>.")
    scripts_open = len(_SCRIPT_OPEN.findall(html_text))
    scripts_close = len(_SCRIPT_CLOSE.findall(html_text))
    if scripts_open != scripts_close:
        errors.append(
            f"<script> tags are unbalanced: {scripts_open} opened, "
            f"{scripts_close} closed."
        )
    styles_open = len(_STYLE_OPEN.findall(html_text))
    styles_close = len(_STYLE_CLOSE.findall(html_text))
    if styles_open != styles_close:
        errors.append(
            f"<style> tags are unbalanced: {styles_open} opened, {styles_close} closed."
        )
    for index, body in enumerate(_SCRIPT_BODY.findall(html_text), start=1):
        if len(_UNESCAPED_BACKTICK.findall(body)) % 2:
            errors.append(
                f"Script block {index} has an unterminated template literal "
                "(an odd number of backticks)."
            )
    return errors


def mock_error_list(store: dict[str, Any], render_errors: Any) -> list[str]:
    """Every error the mock on screen has, static first, as sentences.

    ``store["_mock_errors"]`` is what ``check_mock_html`` found at delivery;
    ``render_errors`` is the ``mock-render-errors`` store the preview's shim
    fills (``{"errors": [{"message", "source", "line"}, ...]}``). A runtime
    error carries its line when the browser gave one: the shim sits on the
    same line as ``<head>``, so the number is the saved document's.
    """
    errors = [str(error) for error in (store.get("_mock_errors") or [])]
    for reported in (render_errors or {}).get("errors") or []:
        if not isinstance(reported, dict):
            continue
        message = str(reported.get("message") or "Script error")
        line = reported.get("line") or 0
        errors.append(f"{message} (line {line})" if line else message)
    return errors


def format_mock_errors(errors: list[str], limit: int = MOCK_ERROR_LIMIT) -> str:
    """The fix draw's instruction: a fixed header and the errors as bullets.

    Capped at ``limit`` with a count of the rest, the way the Phaser retry
    caps its corrective message: past a point, more errors are the same
    structural fault repeated, and the model fixes it once.
    """
    lines = [
        "Fix these errors in the current mock without changing its design.",
        "Keep every screen, element and id; return the whole corrected document.",
        *(f"- {error}" for error in errors[:limit]),
    ]
    remaining = len(errors) - limit
    if remaining > 0:
        lines.append(
            f"(plus {remaining} more -- fix the structural issues above first)"
        )
    return "\n".join(lines)


def persist_manifest(
    accumulated: str,
    planning_context: dict[str, Any] | None,
    design_dir: pathlib.Path,
) -> None:
    """Extract, enrich, validate, and save the design manifest (D-DM).

    Advisory: any failure is logged and swallowed — a missing or malformed
    manifest never blocks the mock from saving.

    The write is skipped when the finished manifest equals the one on disk
    (parsed JSON, not bytes). A refine that re-states an unchanged design must
    not touch ``manifest.json``'s mtime: ``detect_stale_inputs`` and the
    StackAdvisor button both key on it, and a purely visual refinement is
    exactly the change a stack choice is meant to survive (D-SC5c).
    """
    manifest = extract_manifest(accumulated)
    if manifest is None:
        logger.warning("Designer: no valid design manifest in model output")
        return
    pc = planning_context or {}
    ai_features = pc.get("ai_features") or {}
    manifest = enrich_manifest(manifest, ai_features, pc.get("vision_statement"))
    manifest, warnings = validate_manifest(
        manifest, ai_features, pc.get("vision_statement")
    )
    for warning in warnings:
        logger.warning("Designer manifest: %s", warning)
    if manifest == _manifest_on_disk(design_dir):
        logger.debug("Designer: design manifest unchanged; not rewritten")
        return
    save_manifest(manifest, design_dir)


def _manifest_on_disk(design_dir: pathlib.Path) -> dict[str, Any] | None:
    """The parsed ``manifest.json`` in ``design_dir``; None if absent or unreadable."""
    try:
        data = json.loads((design_dir / ARTIFACT_MANIFEST).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def expected_stream_chars(working_dir: str | None) -> int:
    """Progress-bar denominator for a mock generation.

    Brownfield revision rounds are sized from what the previous implemented
    round actually produced — its ``design/mock.html`` plus
    ``design/manifest.json`` character counts, with 10% headroom — since the
    stream this bar tracks emits both. A round with no prior mock (greenfield,
    or a prior round that never finalized a design) keeps the fixed default.
    """
    if not working_dir:
        return _DEFAULT_EXPECTED_CHARS
    prior_mock = project_manager.load_prior_mock(working_dir)
    if prior_mock is None:
        return _DEFAULT_EXPECTED_CHARS
    manifest_chars = 0
    version = project_manager.latest_implemented_version(working_dir)
    if version is not None:
        manifest_path = (
            project_manager.get_version_dir(working_dir, version)
            / "design"
            / ARTIFACT_MANIFEST
        )
        try:
            manifest_chars = len(manifest_path.read_text(encoding="utf-8"))
        except OSError:
            manifest_chars = 0
    return int((len(prior_mock) + manifest_chars) * 1.1)


def find_live_draw(
    store: dict[str, Any] | None, design_dir: pathlib.Path | None
) -> tuple[str, dict[str, Any]] | None:
    """The draw this page should be polling, as ``(gen_id, entry)``; None if none.

    The store's own ``_gen_id`` wins when it still names a buffer. A store that
    has none -- the memory stores were just rebuilt -- falls back to the entry
    drawing for ``design_dir``, of which there is at most one: ``_start_gen``
    stops and evicts the previous draw for a store before launching the next.
    A draw that has been delivered and acknowledged, errored, or stopped is
    popped by the poll, so it is never found here; only a buffer the poll has
    not finished with is. ``done`` without a result still counts -- the poll
    is what pops it, and it needs to run once more to do so.
    """
    gen_id = (store or {}).get("_gen_id")
    if gen_id and gen_id in MOCK_BUFFERS:
        return gen_id, MOCK_BUFFERS[gen_id]
    if design_dir is None:
        return None
    wanted = str(design_dir)
    for candidate, entry in MOCK_BUFFERS.items():
        if entry.get("design_dir") == wanted:
            return candidate, entry
    return None


def stream_progress(entry: dict[str, Any]) -> dict[str, Any]:
    """The running-tick buffer payload for a draw still streaming.

    Shared by the poll and the watchdog so the two cannot report a different
    number for the same draw. ``progress`` is capped at 99 while the stream is
    live: the estimate is made before a single character arrives, and a model
    that writes a draft and then a whole second document blows past it. A bar
    sitting at 100% while text is still arriving reads as a finished generation
    that failed to display -- the one thing the developer must not be told
    wrongly. 100 means delivered. ``elapsed`` is whole seconds since launch
    and ``thinking`` the characters of reasoning text seen so far, for the
    line the page paints while ``tokens`` is still 0. ``idle`` is whole
    seconds since the last chunk of either kind, 0 until the first arrives,
    for the pause notice the page adds past ``PAUSE_NOTICE_S``.
    """
    tokens = len(entry["text"])
    expected = entry.get("expected_chars") or _DEFAULT_EXPECTED_CHARS
    now = time.monotonic()
    started = entry.get("started")
    last = entry.get("last_chunk_at")
    return {
        "tokens": tokens,
        "progress": min(_MAX_LIVE_PROGRESS, tokens * 100 // expected),
        "error": None,
        "elapsed": int(now - started) if started is not None else 0,
        "thinking": entry.get("thinking_chars", 0),
        "idle": int(now - last) if last is not None else 0,
    }


def _start_gen(  # noqa: PLR0913  # the mock-generation contract, shared verbatim with agents/designer.py
    store: dict[str, Any],
    working_dir: str | None,
    model: str,
    api_key: str,
    search_cfg: websearch.SearchConfig | None,
    image_support: bool,
    planning_context: dict[str, Any] | None = None,
    existing_html: str | None = None,
    capture_mode: bool = False,
    api_base: str | None = None,
    extra_kwargs: dict[str, Any] | None = None,
    session: dict[str, Any] | None = None,
    effort: str = llm_selection.DEFAULT_EFFORT,
    existing_manifest: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Launch generation in a background thread.

    ``existing_manifest`` is the manifest describing ``existing_html`` (see
    ``existing_manifest_for_refine``); a refine draw updates it in place.

    Returns (updated_store, cleared_buffer, interval_disabled=False).
    """
    # A new generation abandons any prior one still in flight or awaiting
    # delivery: stop its stream and drop its buffer, or the entry (up to
    # 512 kB of HTML) stays in MOCK_BUFFERS for the life of the process.
    _mock_stop_previous(store)

    # Resolve the save dir here in the request thread, with the session so the
    # pinned phase_version wins. The no-session fallback (latest on-disk
    # version) can disagree with the pinned round, in which case the thread
    # would save the mock where none of the readers — which all pass the
    # session — ever look, silently breaking refresh/approve/retry. A failure
    # resolving it only skips persistence — delivery must still happen.
    design_dir_path = _mock_design_dir(working_dir, session)

    gen_id = str(uuid.uuid4())
    stop_ev = threading.Event()
    buf_entry: dict[str, Any] = {
        "done": False,
        "stop": stop_ev,
        "text": "",
        "expected_chars": expected_stream_chars(working_dir),
        "design_dir": str(design_dir_path) if design_dir_path is not None else None,
        "started": time.monotonic(),
        "thinking_chars": 0,
        "last_chunk_at": None,
    }
    MOCK_BUFFERS[gen_id] = buf_entry

    ds: DesignerSession = {
        "step": store.get("step", 5),
        "preference_text": store.get("preference_text", ""),
        "screenshots": store.get("screenshots", []),
        "mock_html": store.get("mock_html", ""),
        "finalized": False,
    }

    def _run() -> None:
        try:
            snippets = _mock_collect_snippets(existing_html, working_dir)
            for chunk in generate_mock_streaming(
                ds,
                model,
                api_key,
                snippets,
                image_support,
                search_cfg,
                stop_ev,
                planning_context=planning_context,
                existing_html=existing_html,
                capture_mode=capture_mode,
                api_base=api_base,
                extra_kwargs=extra_kwargs,
                effort=effort,
                existing_manifest=existing_manifest,
            ):
                _mock_absorb_chunk(buf_entry, chunk)
            if _DEV_MODE:
                print("\n[Designer] Done.", flush=True)
            if gen_id not in MOCK_BUFFERS:
                return
            # Do the slow work (HTML extraction + disk save) here in the
            # background thread so the poll callback returns instantly and
            # can't race itself.
            accumulated = buf_entry["text"]
            done_ok = (
                "__DONE__" in accumulated and "__GENERATION_ERROR__:" not in accumulated
            )
            if done_ok:
                _mock_finalise_draw(
                    accumulated, buf_entry, ds, design_dir_path, planning_context
                )
        except Exception as exc:
            # A crash here would otherwise die silently in the daemon thread,
            # leaving the poll spinning on a buffer that never completes.
            # Surface it through the same sentinel the streaming layer uses so
            # the user gets the error alert and a Retry button.
            _mock_report_failure(exc, buf_entry)
        finally:
            # The mock draw never passes through the chat poll's persist
            # funnel, so the generation thread flushes its own LLM usage.
            # Same version resolution as the design dir above; a failure
            # here only loses the usage record, never the mock.
            _mock_persist_session(working_dir, session)
            # Unconditional: `done` without final_html or an error sentinel is
            # the poll's cleanup signal. Setting it on an already-popped entry
            # (user clicked Start Over mid-generation) is harmless.
            buf_entry["done"] = True

    threading.Thread(target=_run, daemon=True).start()

    # Drop screenshots and refine_images from the store.  Load-bearing —
    # don't restore on cleanup.  Their base64 payload can run to several MB,
    # and `ds` (above) has already captured the merged list in the thread
    # closure for the LLM call, so the dcc.Store copy is dead weight.
    # Leaving them in bloats every subsequent callback's State and Output
    # payload, which has been observed to break Dash dispatch silently.
    updated_store = {
        **store,
        "step": 5,
        "_gen_id": gen_id,
        "_has_existing_html": existing_html is not None,
        # D-DM8: retry re-runs whatever this draw was. Without recording the
        # mode, retrying a failed capture silently regenerated as a greenfield
        # design instead of recreating the existing UI.
        "_capture_mode": capture_mode,
        "mock_html": "",
        "screenshots": [],
        "refine_images": [],
        "finalized": False,
        # A failed draw's error rides the store (the poll writes it there so
        # the step re-renders); a new draw starts clean of it, and of the
        # last mock's static defects.
        "_draw_error": None,
        "_mock_errors": [],
    }
    cleared_buffer: dict[str, Any] = {"tokens": 0, "progress": 0, "error": None}
    return updated_store, cleared_buffer, False  # False = not disabled


def existing_manifest_for_refine(
    store: dict[str, Any],
    working_dir: str | None,
    session: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """The manifest describing the mock a refine draw starts from (D-DM9).

    The active round's ``design/manifest.json`` when that round has drawn a
    mock — ``None`` if its last draw produced no extractable manifest, rather
    than a manifest for some other mock. A revision round whose store carries
    the prior approved mock (``on_designer_carry_forward``) has no mock of its
    own yet, so the prior implemented round's manifest is the one to update.
    """
    if not working_dir:
        return None
    active = project_manager.active_version(working_dir, session)
    design_dir = project_manager.get_version_dir(working_dir, active) / "design"
    if (design_dir / "mock.html").exists():
        return project_manager.load_design_manifest(working_dir, active)
    if store.get("_is_revision"):
        return project_manager.load_prior_manifest(working_dir)
    return None


def _mock_stop_previous(store: dict[str, Any]) -> None:
    """Stop and evict any generation still running for this store."""
    old_gen_id = store.get("_gen_id")
    if old_gen_id:
        old_entry = MOCK_BUFFERS.pop(old_gen_id, None)
        if old_entry:
            old_entry["stop"].set()


def _mock_design_dir(
    working_dir: str | None, session: dict[str, Any] | None
) -> pathlib.Path | None:
    """Resolve the version's design directory; None when it cannot be resolved."""
    design_dir_path: pathlib.Path | None = None
    if working_dir:
        try:
            design_dir_path = (
                project_manager.get_version_dir(
                    working_dir,
                    project_manager.active_version(working_dir, session),
                )
                / "design"
            )
        except Exception as exc:
            logger.warning("Designer: could not resolve the design save dir: %s", exc)
    return design_dir_path


def _mock_absorb_chunk(buf_entry: dict[str, Any], chunk: str) -> None:
    """Fold one yielded chunk into the buffer.

    Thinking text (``THINKING_MARK``) is counted and dropped: a reasoning
    summary can quote HTML, so it must never reach ``extract_html``, the
    manifest extraction or the ``__DONE__`` check. Everything else is output
    and accumulates. Both kinds stamp ``last_chunk_at``: a model reasoning
    between output bursts is not paused, and the notice must not say it is.
    """
    buf_entry["last_chunk_at"] = time.monotonic()
    if chunk.startswith(THINKING_MARK):
        buf_entry["thinking_chars"] = buf_entry.get("thinking_chars", 0) + (
            len(chunk) - len(THINKING_MARK)
        )
        return
    buf_entry["text"] += chunk
    if _DEV_MODE and not chunk.startswith("__"):
        print(chunk, end="", flush=True)


def _mock_collect_snippets(
    existing_html: str | None, working_dir: str | None
) -> list[str]:
    """UI source snippets for a first draw; none on a refine."""
    snippets: list[str] = []
    if not existing_html and working_dir:
        snippets = collect_ui_source_files(pathlib.Path(working_dir))
    if _DEV_MODE:
        print("\n[Designer] Generating mock...", flush=True)
    return snippets


def _mock_finalise_draw(
    accumulated: str,
    buf_entry: dict[str, Any],
    ds: DesignerSession,
    design_dir_path: pathlib.Path | None,
    planning_context: dict[str, Any] | None,
) -> None:
    """Extract the HTML from a finished draw, save it and its manifest.

    Records the document's static defects (``check_mock_html``) on the buffer
    as ``static_errors`` for the poll to deliver; they never block the save.
    """
    html_text = accumulated.replace("__DONE__", "").strip()
    extracted = extract_html(html_text)
    if extracted is None:
        buf_entry["text"] += (
            "__GENERATION_ERROR__: The model did not return a valid "
            "HTML document. Please retry or refine your style "
            "description."
        )
    else:
        truncated = len(extracted) > _MAX_HTML_BYTES
        if truncated:
            extracted = (
                extracted[:_MAX_HTML_BYTES]
                + "\n<!-- Designer: output truncated at 512 kB -->"
            )
        buf_entry["static_errors"] = check_mock_html(extracted, truncated=truncated)
        if design_dir_path is not None:
            try:
                save_ds: DesignerSession = {
                    "step": 6,
                    "preference_text": ds["preference_text"],
                    "screenshots": ds["screenshots"],
                    "mock_html": extracted,
                    "finalized": False,
                }
                save_session(save_ds, design_dir_path)
                save_mock(extracted, design_dir_path)
                # D-DM9: refine draws are manifest-bearing too, so
                # the manifest tracks the mock that actually ships
                # instead of freezing at the initial draw.
                # Extraction failure still returns early and leaves
                # the prior manifest.json untouched, so a missed
                # manifest is never worse than the pre-D-DM9
                # behaviour.
                persist_manifest(accumulated, planning_context, design_dir_path)
            except Exception as exc:
                logger.warning(
                    "Designer: could not persist session to disk: %s",
                    exc,
                )
        # Set last: the poll treats final_html as "complete and
        # persisted", so everything savable must already be on
        # disk by the time this appears.
        buf_entry["final_html"] = extracted


def _mock_report_failure(exc: Exception, buf_entry: dict[str, Any]) -> None:
    """Surface a thread crash through the streaming layer's error sentinel."""
    logger.warning("Designer generation thread crashed", exc_info=True)
    msg = str(exc).strip() or repr(exc)
    buf_entry["text"] += f"__GENERATION_ERROR__: {type(exc).__name__}: {msg}"


def _mock_persist_session(
    working_dir: str | None, session: dict[str, Any] | None
) -> None:
    """Persist the designer session after a draw, however it ended."""
    if working_dir:
        try:
            project_manager.save_usage(
                working_dir,
                llm.drain_usage_records(),
                project_manager.active_version(working_dir, session),
            )
        except Exception as exc:
            logger.warning("Designer: could not save LLM usage: %s", exc)
