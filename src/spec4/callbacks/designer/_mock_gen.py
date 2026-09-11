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

import logging
import os
import pathlib
import re
import threading
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
MOCK_BUFFERS: dict[str, dict[str, Any]] = {}
_MAX_HTML_BYTES = 512_000
# Progress-bar denominator when there is no prior round to size against: the
# rough character count of a typical mock + manifest stream.
_DEFAULT_EXPECTED_CHARS = 70_000
# Safety valve on completion re-delivery: 480 ticks × 250 ms ≈ 2 minutes.
# Delivery is acknowledgement-based (see on_mock_stream_poll) — the payload is
# re-emitted until the browser's own poll request proves the store applied it —
# so this cap exists only to stop an unacknowledged loop from re-sending a
# ~512 kB payload forever (e.g. the tab was closed mid-generation and Dash
# keeps replaying a stale queued tick).  It is not a delivery window: under
# normal operation the ack arrives on the first tick after the payload lands.
_MAX_DELIVERY_TICKS = 480


def _llm_params(
    session: dict[str, Any], image_support: Any
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


def persist_manifest(
    accumulated: str,
    planning_context: dict[str, Any] | None,
    design_dir: pathlib.Path,
) -> None:
    """Extract, enrich, validate, and save the design manifest (D-DM).

    Advisory: any failure is logged and swallowed — a missing or malformed
    manifest never blocks the mock from saving.
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
    save_manifest(manifest, design_dir)


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


def _start_gen(  # noqa: PLR0913  # the mock-generation contract, shared verbatim with agents/designer.py
    store: dict[str, Any],
    working_dir: str | None,
    model: str,
    api_key: str,
    search_cfg: Any,
    image_support: bool,
    planning_context: dict[str, Any] | None = None,
    existing_html: str | None = None,
    capture_mode: bool = False,
    api_base: str | None = None,
    extra_kwargs: dict[str, Any] | None = None,
    session: dict[str, Any] | None = None,
    effort: str = llm_selection.DEFAULT_EFFORT,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Launch generation in a background thread.

    Returns (updated_store, cleared_buffer, interval_disabled=False).
    """
    # A new generation abandons any prior one still in flight or awaiting
    # delivery: stop its stream and drop its buffer, or the entry (up to
    # 512 kB of HTML) stays in MOCK_BUFFERS for the life of the process.
    _mock_stop_previous(store)

    gen_id = str(uuid.uuid4())
    stop_ev = threading.Event()
    buf_entry: dict[str, Any] = {
        "done": False,
        "stop": stop_ev,
        "text": "",
        "expected_chars": expected_stream_chars(working_dir),
    }
    MOCK_BUFFERS[gen_id] = buf_entry

    ds: DesignerSession = {
        "step": store.get("step", 5),
        "preference_text": store.get("preference_text", ""),
        "screenshots": store.get("screenshots", []),
        "mock_html": store.get("mock_html", ""),
        "finalized": False,
    }

    # Resolve the save dir here in the request thread, with the session so the
    # pinned phase_version wins. The no-session fallback (latest on-disk
    # version) can disagree with the pinned round, in which case the thread
    # would save the mock where none of the readers — which all pass the
    # session — ever look, silently breaking refresh/approve/retry. A failure
    # resolving it only skips persistence — delivery must still happen.
    design_dir_path = _mock_design_dir(working_dir, session)

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
            ):
                buf_entry["text"] += chunk
                if _DEV_MODE and not chunk.startswith("__"):
                    print(chunk, end="", flush=True)
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
    }
    cleared_buffer: dict[str, Any] = {"tokens": 0, "progress": 0, "error": None}
    return updated_store, cleared_buffer, False  # False = not disabled


def _mock_stop_previous(store: dict[str, Any]) -> None:
    """Stop and evict any generation still running for this store."""
    old_gen_id = store.get("_gen_id")
    if old_gen_id:
        old_entry = MOCK_BUFFERS.pop(old_gen_id, None)
        if old_entry:
            old_entry["stop"].set()


def _mock_design_dir(
    working_dir: Any, session: dict[str, Any] | None
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


def _mock_collect_snippets(existing_html: str | None, working_dir: Any) -> list[str]:
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
    ds: Any,
    design_dir_path: Any,
    planning_context: dict[str, Any] | None,
) -> None:
    """Extract the HTML from a finished draw, save it and its manifest."""
    html_text = accumulated.replace("__DONE__", "").strip()
    extracted = extract_html(html_text)
    if extracted is None:
        buf_entry["text"] += (
            "__GENERATION_ERROR__: The model did not return a valid "
            "HTML document. Please retry or refine your style "
            "description."
        )
    else:
        if len(extracted) > _MAX_HTML_BYTES:
            extracted = (
                extracted[:_MAX_HTML_BYTES]
                + "\n<!-- Designer: output truncated at 512 kB -->"
            )
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


def _mock_persist_session(working_dir: Any, session: dict[str, Any] | None) -> None:
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
