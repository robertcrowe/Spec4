from __future__ import annotations

import logging
import os
import pathlib
import re
import threading
import uuid
from typing import Any

from dash import ALL, Input, Output, State, callback, ctx, no_update

from spec4 import project_manager, websearch
from spec4.agents._manifest import (
    enrich_manifest,
    extract_manifest,
    validate_manifest,
)
from spec4.agents.designer import (
    DesignerSession,
    build_revision_note,
    collect_ui_source_files,
    generate_mock_streaming,
    revision_delta,
    save_manifest,
    save_mock,
    save_session,
)
from spec4.layouts.designer import (
    _default_designer_session,
    _step1_content,
    _step2_content,
    _step3_content,
    _step4_content,
    _step5_content,
    _step6_content,
    _step7_content,
)

logger = logging.getLogger(__name__)

_DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"

# keyed by gen_id stored in designer-session-store["_gen_id"]
# _run() is the sole writer of buf["text"] / buf["final_html"]; poll callbacks
# only read them.  CPython's GIL makes this single-writer pattern safe without
# a lock.  When _run() finishes extraction, on_mock_stream_poll picks up
# buf["final_html"] and pushes the completed mock straight to
# designer-session-store — no intermediary signal store needed.
_MOCK_BUFFERS: dict[str, dict[str, Any]] = {}

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
]:
    """Extract LLM connection parameters from the main session dict."""
    llm_config: dict[str, Any] = session.get("llm_config") or {}
    api_base: str | None = llm_config.get("api_base")
    aws_kwargs = {k: v for k, v in llm_config.items() if k.startswith("aws_")}
    return (
        session.get("model") or "",
        llm_config.get("api_key") or "",
        websearch.from_session(session),
        session.get("working_dir"),
        bool(image_support) if image_support is not None else True,
        api_base,
        aws_kwargs,
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


def _extract_html(text: str) -> str | None:
    """Extract an HTML document from model output, returning None if not found."""
    match = re.search(
        r"(<!DOCTYPE html>.*?</html>|<html[\s>].*?</html>)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    code_match = re.search(r"```(?:html)?\s*(.*?)\s*```", text, re.DOTALL)
    if code_match:
        inner = code_match.group(1).strip()
        if "<html" in inner.lower() or "<!doctype" in inner.lower():
            return inner
    return None


def _persist_manifest(
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


def _expected_stream_chars(working_dir: str | None) -> int:
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
            / "manifest.json"
        )
        try:
            manifest_chars = len(manifest_path.read_text(encoding="utf-8"))
        except OSError:
            manifest_chars = 0
    return int((len(prior_mock) + manifest_chars) * 1.1)


def _start_gen(
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
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Launch generation in a background thread.

    Returns (updated_store, cleared_buffer, interval_disabled=False).
    """
    # A new generation abandons any prior one still in flight or awaiting
    # delivery: stop its stream and drop its buffer, or the entry (up to
    # 512 kB of HTML) stays in _MOCK_BUFFERS for the life of the process.
    old_gen_id = store.get("_gen_id")
    if old_gen_id:
        old_entry = _MOCK_BUFFERS.pop(old_gen_id, None)
        if old_entry:
            old_entry["stop"].set()

    gen_id = str(uuid.uuid4())
    stop_ev = threading.Event()
    buf_entry: dict[str, Any] = {
        "done": False,
        "stop": stop_ev,
        "text": "",
        "expected_chars": _expected_stream_chars(working_dir),
    }
    _MOCK_BUFFERS[gen_id] = buf_entry

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
            logger.warning(
                "Designer: could not resolve the design save dir: %s", exc
            )

    def _run() -> None:
        try:
            snippets: list[str] = []
            if not existing_html and working_dir:
                snippets = collect_ui_source_files(pathlib.Path(working_dir))
            if _DEV_MODE:
                print("\n[Designer] Generating mock...", flush=True)
            for chunk in generate_mock_streaming(
                ds, model, api_key, snippets, image_support, search_cfg, stop_ev,
                planning_context=planning_context,
                existing_html=existing_html,
                capture_mode=capture_mode,
                api_base=api_base,
                extra_kwargs=extra_kwargs,
            ):
                buf_entry["text"] += chunk
                if _DEV_MODE and not chunk.startswith("__"):
                    print(chunk, end="", flush=True)
            if _DEV_MODE:
                print("\n[Designer] Done.", flush=True)
            if gen_id not in _MOCK_BUFFERS:
                return
            # Do the slow work (HTML extraction + disk save) here in the
            # background thread so the poll callback returns instantly and
            # can't race itself.
            accumulated = buf_entry["text"]
            done_ok = (
                "__DONE__" in accumulated
                and "__GENERATION_ERROR__:" not in accumulated
            )
            if done_ok:
                html_text = accumulated.replace("__DONE__", "").strip()
                extracted = _extract_html(html_text)
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
                            _persist_manifest(
                                accumulated, planning_context, design_dir_path
                            )
                        except Exception as exc:
                            logger.warning(
                                "Designer: could not persist session to disk: %s",
                                exc,
                            )
                    # Set last: the poll treats final_html as "complete and
                    # persisted", so everything savable must already be on
                    # disk by the time this appears.
                    buf_entry["final_html"] = extracted
        except Exception as exc:
            # A crash here would otherwise die silently in the daemon thread,
            # leaving the poll spinning on a buffer that never completes.
            # Surface it through the same sentinel the streaming layer uses so
            # the user gets the error alert and a Retry button.
            logger.warning("Designer generation thread crashed", exc_info=True)
            msg = str(exc).strip() or repr(exc)
            buf_entry["text"] += (
                f"__GENERATION_ERROR__: {type(exc).__name__}: {msg}"
            )
        finally:
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
        **store, "step": 5, "_gen_id": gen_id,
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


@callback(
    Output("designer-step-content", "children"),
    Output("designer-stepper", "active"),
    Input("designer-session-store", "data"),
    Input("mock-stream-buffer", "data"),
    State("image-support-store", "data"),
)
def render_designer_step(store: Any, buffer_data: Any, image_support: Any) -> Any:
    if not store:
        return no_update, no_update
    step: int = store.get("step", 2)
    # Buffer ticks arrive 4×/sec during generation. Replacing the whole step
    # subtree on each one forces dash-renderer to recompute its paths map while
    # the poll's completion delivery is trying to apply — a dropped applyProps
    # there strands the UI at step 5 permanently. Progress is painted
    # clientside (see app.py); only a buffer *error* needs a re-render here.
    triggered = getattr(ctx, "triggered", None) or []
    buffer_only = bool(triggered) and all(
        t.get("prop_id") == "mock-stream-buffer.data" for t in triggered
    )
    if buffer_only and not (step == 5 and (buffer_data or {}).get("error")):
        return no_update, no_update
    content: Any
    if step == 1:
        content = _step1_content()
    elif step == 2:
        content = _step2_content(
            bool(store.get("_has_existing_ui", True)),
            bool(store.get("_is_revision", False)),
        )
    elif step == 3:
        content = _step3_content()
    elif step == 4:
        support: bool | None = image_support
        content = _step4_content(store, support)
    elif step == 5:
        content = _step5_content(buffer_data)
    elif step == 6:
        content = _step6_content(store)
    elif step == 7:
        content = _step7_content(store, image_support)
    else:
        content = _step2_content(
            bool(store.get("_has_existing_ui", True)),
            bool(store.get("_is_revision", False)),
        )
    stepper_active = max(0, min(step - 1, 5))
    return content, stepper_active


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("btn-designer-add-gui", "n_clicks"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_add_gui(n: Any, store: Any) -> Any:
    if not n or not store:
        return no_update
    return {**store, "step": 2}


def _skip_to_stack_advisor(session: Any) -> Any:
    session = session or {}
    return {
        **session,
        "phase": "chat",
        "active_agent": "stack_advisor",
        "stack_advisor_messages": [],
        "messages": [],
        "_initial_turn_done": False,
    }, "/chat"


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-designer-skip-1", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_designer_skip_1(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return _skip_to_stack_advisor(session)


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-designer-skip-2", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_designer_skip_2(n: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update
    return _skip_to_stack_advisor(session)


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Output("mock-stream-buffer", "data", allow_duplicate=True),
    Output("mock-stream-interval", "disabled", allow_duplicate=True),
    Input("btn-designer-modify-existing", "n_clicks"),
    Input("btn-designer-create-new", "n_clicks"),
    State("designer-session-store", "data"),
    State("session", "data"),
    State("image-support-store", "data"),
    prevent_initial_call=True,
)
def on_designer_step2_choice(
    n_modify: Any, n_create: Any, store: Any, session: Any, image_support: Any
) -> Any:
    if not ctx.triggered_id or not (n_modify or n_create):
        return no_update, no_update, no_update
    if ctx.triggered_id == "btn-designer-create-new":
        # Clear any capture flag a prior "Modify existing" left behind, so a
        # retry on the create-new draw cannot inherit it (D-DM8).
        cleared = {**(store or {}), "step": 3, "_capture_mode": False}
        return cleared, no_update, no_update
    # "Modify existing" — capture the project's current look and feel
    sess = session or {}
    model, api_key, search_cfg, wd, support, api_base, aws_kw = _llm_params(
        sess, image_support
    )
    # D-DM7: this generation carries the manifest instruction (it is the only
    # non-refine draw in the brownfield path, so it is the sole chance to
    # produce manifest.json — every later refinement passes existing_html,
    # which skips both the instruction and _persist_manifest). It therefore
    # needs the same planning context as every other manifest-bearing draw.
    new_store, buf, disabled = _start_gen(
        store or {}, wd, model, api_key, search_cfg, support,
        _planning_ctx(sess, wd),
        capture_mode=True, api_base=api_base,
        extra_kwargs=aws_kw or None,
        session=sess,
    )
    return new_store, buf, disabled


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("btn-designer-carry-forward", "n_clicks"),
    State("designer-session-store", "data"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_designer_carry_forward(n: Any, store: Any, session: Any) -> Any:
    """Revision round — carry the prior approved mock forward and apply the delta.

    Loads the latest *implemented* round's ``mock.html`` as the baseline, prefills
    the refine note from this revision's vision delta, and drops into the refine
    view (step 7). The existing regenerate flow then refines the carried mock —
    ``existing_html`` is read from the store's ``mock_html``, so seeding it here is
    all that's needed; no generation-path change. Falls back to the create flow
    (step 3) if the prior mock has gone missing since the page rendered.
    """
    if not n or not store:
        return no_update
    sess = session or {}
    wd = sess.get("working_dir")
    prior_mock = project_manager.load_prior_mock(wd) if wd else None
    if not prior_mock:
        return {**store, "step": 3}
    delta = revision_delta(sess.get("vision_statement"))
    note = build_revision_note(delta) if delta else ""
    return {
        **store,
        "step": 7,
        "mock_html": prior_mock,
        "refine_text": note,
        "refine_images": [],
    }


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("btn-designer-preferences-next", "n_clicks"),
    State("designer-preference-input", "value"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_preferences_next(n: Any, pref_text: Any, store: Any) -> Any:
    if not n or not store:
        return no_update
    return {**store, "preference_text": pref_text or "", "step": 4}


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("designer-screenshot-upload", "contents"),
    State({"type": "designer-screenshot-annotation", "index": ALL}, "value"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_screenshot_upload(contents: Any, annotations: Any, store: Any) -> Any:
    if not contents or not store:
        return no_update
    screenshots: list[dict[str, str]] = list(store.get("screenshots", []))
    for i, ann in enumerate(annotations or []):
        if i < len(screenshots):
            screenshots[i] = {**screenshots[i], "annotation": ann or ""}
    screenshots.append({"data": contents, "annotation": ""})
    return {**store, "screenshots": screenshots}


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input({"type": "designer-screenshot-delete", "index": ALL}, "n_clicks"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_screenshot_delete(n_clicks_list: Any, store: Any) -> Any:
    if not any(n for n in (n_clicks_list or []) if n):
        return no_update
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        return no_update
    idx: int = triggered["index"]
    screenshots: list[dict[str, str]] = list((store or {}).get("screenshots", []))
    if 0 <= idx < len(screenshots):
        screenshots.pop(idx)
    return {**(store or {}), "screenshots": screenshots}


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Output("mock-stream-buffer", "data", allow_duplicate=True),
    Output("mock-stream-interval", "disabled", allow_duplicate=True),
    Input("btn-designer-generate-mock", "n_clicks"),
    State({"type": "designer-screenshot-annotation", "index": ALL}, "value"),
    State("designer-session-store", "data"),
    State("session", "data"),
    State("image-support-store", "data"),
    prevent_initial_call=True,
)
def on_designer_generate_mock(
    n: Any,
    annotations: Any,
    store: Any,
    session: Any,
    image_support: Any,
) -> Any:
    if not n or not store:
        return no_update, no_update, no_update
    screenshots: list[dict[str, str]] = list(store.get("screenshots", []))
    for i, ann in enumerate(annotations or []):
        if i < len(screenshots):
            screenshots[i] = {**screenshots[i], "annotation": ann or ""}
    updated = {**store, "screenshots": screenshots}
    sess = session or {}
    model, api_key, search_cfg, wd, support, api_base, aws_kw = _llm_params(
        sess, image_support
    )
    _vision_s1 = sess.get("vision_statement")
    planning_ctx: dict[str, Any] | None = (
        {
            "vision_statement": _vision_s1,
            **({"ai_features": sess["ai_features"]} if sess.get("ai_features") else {}),
            **(
                {"feature_specs": sess["feature_specs"]}
                if sess.get("feature_specs")
                else {}
            ),
        }
        if _vision_s1
        else None
    )
    new_store, buf, disabled = _start_gen(
        updated, wd, model, api_key, search_cfg, support, planning_ctx,
        api_base=api_base,
        extra_kwargs=aws_kw or None,
        session=sess,
    )
    return new_store, buf, disabled


@callback(
    Output("mock-stream-buffer", "data", allow_duplicate=True),
    Output("designer-session-store", "data", allow_duplicate=True),
    Output("mock-stream-interval", "disabled", allow_duplicate=True),
    Input("mock-stream-interval", "n_intervals"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_mock_stream_poll(n: Any, store: Any) -> Any:
    """Poll the mock generation thread and deliver completion in-band.

    On each tick this updates mock-stream-buffer with token/progress info.
    When the background thread finishes and stores the extracted HTML on
    buf_entry["final_html"], this same callback writes the completed mock
    straight into designer-session-store (step=6, mock_html=...) and disables
    the interval.

    Two pieces of load-bearing weirdness — preserve both during cleanup:

    1. **In-band delivery.**  Earlier this fanned out through a separate
       mock-done-store dcc.Store + on_mock_done callback.  That chain failed
       silently when the user attached a screenshot to a refine: the signal
       store updated but on_mock_done never fired.  Cause never fully nailed
       down; consolidating delivery into this callback bypasses it entirely.
       Don't reintroduce a chained completion callback.

    2. **Acknowledgement-based re-delivery.**  Even with the direct in-band
       delivery, the completion response is occasionally dropped by the
       browser (server prints "mock delivered" but UI stays at step 5).  The
       poll request itself is the acknowledgement channel: its
       designer-session-store State is the value the browser has *applied* at
       dispatch time.  While that still reads step 5, the payload has not
       landed — keep the buffer alive and re-emit the identical step=6 /
       mock_html payload every tick.  Only a poll whose store has moved off
       step 5 proves delivery (or that the user already moved on), and only
       then is the buffer popped and the interval disabled.  A fixed-count
       window (formerly 6 ticks) counted requests *sent*, not deliveries
       *applied* — with >250 ms of response latency the whole window could
       burn before the first response ever reached the browser, stranding
       the UI at step 5 with the interval off.  Don't reintroduce one; the
       only counter here is the ~2-minute runaway valve (_MAX_DELIVERY_TICKS).

    3. **Clientside redundant delivery.**  The dropped completion was observed
       to be one-sided: the buffer output of the very same response kept
       applying (chars counter climbing) while the store output never landed.
       Delivery ticks therefore also embed the step-6 payload in the buffer
       under ``complete``, and a clientside callback in app.py copies it into
       designer-session-store from the browser side.  That is not the banned
       chained *server* callback from (1) — no extra round trip, no signal
       store — and the ack loop below still confirms whichever route landed.
    """
    gen_id: str | None = (store or {}).get("_gen_id")
    if not gen_id or gen_id not in _MOCK_BUFFERS:
        return no_update, no_update, True

    buf_entry = _MOCK_BUFFERS[gen_id]
    accumulated = buf_entry["text"]

    if "__GENERATION_ERROR__:" in accumulated:
        idx = accumulated.index("__GENERATION_ERROR__:")
        error_msg = accumulated[idx + len("__GENERATION_ERROR__:"):].strip()
        error_msg = error_msg or "Generation failed — check the server log for details."
        _MOCK_BUFFERS.pop(gen_id, None)
        return {"error": error_msg}, no_update, True

    final_html: str | None = buf_entry.get("final_html")
    if final_html is not None:
        s = store or {}
        final_buf = {"tokens": len(final_html), "progress": 100, "error": None}

        # Acknowledgement: this request's State is the store the browser has
        # actually applied.  Any step other than 5 means the completion
        # payload landed (or the user has already moved past the preview —
        # e.g. clicked Refine between ticks, which must not be bounced back
        # to step 6).  Either way delivery is finished: drop the buffer and
        # stop the interval.
        if s.get("step") != 5:
            _MOCK_BUFFERS.pop(gen_id, None)
            if _DEV_MODE:
                print(
                    f"[Designer] mock delivery acknowledged "
                    f"(store step={s.get('step')}): gen_id={gen_id[:8]}",
                    flush=True,
                )
            return final_buf, no_update, True

        # Unacknowledged — (re-)deliver the identical payload.  Dash
        # deduplicates on identical store values, so once the first delivery
        # lands the repeats cost nothing.
        delivered = buf_entry.get("delivered", 0) + 1
        buf_entry["delivered"] = delivered

        if delivered > _MAX_DELIVERY_TICKS:
            # ~2 minutes of re-delivery with no acknowledgement: the page is
            # not applying updates.  The generation thread already saved the
            # mock to disk before setting final_html, so nothing is lost —
            # tell the user how to get at it instead of spinning forever.
            _MOCK_BUFFERS.pop(gen_id, None)
            return (
                {
                    "error": (
                        "The mock was generated and saved, but this page "
                        "stopped receiving updates and could not display it. "
                        "Refresh the page to load the saved mock, or click "
                        "Retry to regenerate."
                    )
                },
                no_update,
                True,
            )

        # Spread the acknowledged store so flags like _capture_mode,
        # _is_revision, _stale_inputs and refine_text survive delivery (a
        # from-scratch payload here regressed D-DM8: Retry after a capture
        # draw lost the mode and regenerated greenfield). screenshots and
        # refine_images stay empty — their base64 payload must never re-enter
        # the store (see the note in _start_gen).
        new_store: Any = {
            **s,
            "step": 6,
            "mock_html": final_html,
            "screenshots": [],
            "refine_images": [],
            "finalized": False,
        }
        # Redundant delivery route: the buffer channel keeps applying in the
        # browser even when the store output of this same response does not
        # (observed: chars counter climbing while the UI stays at step 5).  A
        # clientside callback in app.py copies `complete` into the store from
        # the browser side, bypassing the flaky server-response store apply.
        deliver_buf = {**final_buf, "complete": new_store}

        if _DEV_MODE:
            print(
                f"[Designer] mock delivered (tick {delivered}, awaiting ack): "
                f"gen_id={gen_id[:8]} mock_html_len={len(final_html)}",
                flush=True,
            )
        return deliver_buf, new_store, no_update

    # Generator finished without a recognised sentinel — stop event fired mid-stream.
    if buf_entry.get("done"):
        _MOCK_BUFFERS.pop(gen_id, None)
        return no_update, no_update, True

    tokens = len(accumulated)
    expected = buf_entry.get("expected_chars") or _DEFAULT_EXPECTED_CHARS
    progress = min(100, tokens * 100 // expected)
    return (
        {"tokens": tokens, "progress": progress, "error": None},
        no_update,
        no_update,
    )


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("btn-designer-approve", "n_clicks"),
    State("designer-session-store", "data"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_designer_approve(n: Any, store: Any, session: Any) -> Any:
    """Finalize and save the mock, marking it approved — but stay on Designer.

    The user is shown a confirmation and a 'Continue to Stack Advisor' button
    (rendered by ``_step6_content`` when ``finalized`` is set) rather than being
    navigated straight into the next agent.
    """
    if not n or not store:
        return no_update
    session = session or {}
    working_dir: str | None = session.get("working_dir")
    if working_dir:
        design_dir = (
            project_manager.get_version_dir(
                working_dir, project_manager.active_version(working_dir, session)
            )
            / "design"
        )
        ds: DesignerSession = {
            "step": store.get("step", 6),
            "preference_text": store.get("preference_text", ""),
            "screenshots": store.get("screenshots", []),
            "mock_html": store.get("mock_html", ""),
            "finalized": True,
        }
        save_session(ds, design_dir)
        save_mock(ds["mock_html"], design_dir)
    return {**store, "step": 6, "finalized": True}


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-designer-continue-stack", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_designer_continue_stack(n: Any, session: Any) -> Any:
    """Proceed from an approved mock into Stack Advisor."""
    if not n:
        return no_update, no_update
    return {
        **(session or {}),
        "phase": "chat",
        "active_agent": "stack_advisor",
        "stack_advisor_messages": [],
        "messages": [],
        "_initial_turn_done": False,
    }, "/chat"


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-designer-back", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_designer_back(n: Any, session: Any) -> Any:
    """Return to the agents page, like the other agents' Back button."""
    if not n:
        return no_update, no_update
    return {**(session or {}), "phase": "agent_select"}, "/agents"


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Output("mock-stream-buffer", "data", allow_duplicate=True),
    Output("mock-stream-interval", "disabled", allow_duplicate=True),
    Input("btn-designer-start-over", "n_clicks"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_start_over(n: Any, store: Any) -> Any:
    if not n:
        return no_update, no_update, no_update
    gen_id: str | None = (store or {}).get("_gen_id")
    if gen_id:
        entry = _MOCK_BUFFERS.pop(gen_id, None)
        if entry:
            entry["stop"].set()
    return (
        {
            **_default_designer_session(step=2),
            "_has_existing_ui": (store or {}).get("_has_existing_ui", False),
        },
        {"text": "", "tokens": 0, "progress": 0, "error": None},
        True,
    )


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("btn-designer-refine", "n_clicks"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_refine(n: Any, store: Any) -> Any:
    if not n or not store:
        return no_update
    return {**store, "step": 7, "refine_text": ""}


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("btn-designer-refine-cancel", "n_clicks"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_refine_cancel(n: Any, store: Any) -> Any:
    if not n or not store:
        return no_update
    return {**store, "step": 6, "refine_images": [], "refine_text": ""}


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("designer-refine-upload", "contents"),
    State("designer-refine-upload", "filename"),
    State("designer-refine-input", "value"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_refine_upload(
    contents: Any, filename: Any, refine_text: Any, store: Any
) -> Any:
    if not contents or not store:
        return no_update
    images: list[dict[str, str]] = list(store.get("refine_images", []))
    images.append({"data": contents, "filename": filename or "image"})
    return {**store, "refine_images": images, "refine_text": refine_text or ""}


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input({"type": "designer-refine-image-delete", "index": ALL}, "n_clicks"),
    State("designer-refine-input", "value"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_refine_image_delete(
    n_clicks_list: Any, refine_text: Any, store: Any
) -> Any:
    if not any(n for n in (n_clicks_list or []) if n):
        return no_update
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        return no_update
    idx: int = triggered["index"]
    images: list[dict[str, str]] = list((store or {}).get("refine_images", []))
    if 0 <= idx < len(images):
        images.pop(idx)
    return {**(store or {}), "refine_images": images, "refine_text": refine_text or ""}


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Output("mock-stream-buffer", "data", allow_duplicate=True),
    Output("mock-stream-interval", "disabled", allow_duplicate=True),
    Input("btn-designer-regenerate", "n_clicks"),
    State("designer-refine-input", "value"),
    State("designer-session-store", "data"),
    State("session", "data"),
    State("image-support-store", "data"),
    prevent_initial_call=True,
)
def on_designer_regenerate(
    n: Any,
    refine_text: Any,
    store: Any,
    session: Any,
    image_support: Any,
) -> Any:
    if not n or not store:
        return no_update, no_update, no_update
    pref: str = store.get("preference_text", "")
    if refine_text and refine_text.strip():
        pref = f"{pref}\n\n--- Refinement ---\n{refine_text.strip()}"
    screenshots: list[dict[str, str]] = list(store.get("screenshots", []))
    for img in store.get("refine_images", []):
        screenshots.append({"data": img["data"], "annotation": img["filename"]})
    existing_html: str | None = store.get("mock_html") or None
    updated = {**store, "preference_text": pref, "screenshots": screenshots}
    sess = session or {}
    model, api_key, search_cfg, wd, support, api_base, aws_kw = _llm_params(
        sess, image_support
    )
    _vision_s3 = sess.get("vision_statement")
    # Source the AI catalog from disk so the surfaces block reflects the current
    # ai_features.json (which upstream edits like a feature deselection write)
    # rather than a possibly-stale session snapshot; fall back to the session
    # copy when no working dir is available.
    _ai_feat_s3 = (project_manager.load_ai_features(wd) if wd else None) or sess.get(
        "ai_features"
    )
    _fs_s3 = (project_manager.load_feature_specs(wd) if wd else None) or sess.get(
        "feature_specs"
    )
    planning_ctx: dict[str, Any] | None = (
        {
            "vision_statement": _vision_s3,
            **({"ai_features": _ai_feat_s3} if _ai_feat_s3 else {}),
            **({"feature_specs": _fs_s3} if _fs_s3 else {}),
        }
        if _vision_s3
        else None
    )
    new_store, buf, disabled = _start_gen(
        updated, wd, model, api_key, search_cfg, support,
        planning_ctx,
        existing_html=existing_html,
        api_base=api_base,
        extra_kwargs=aws_kw or None,
        session=sess,
    )
    return new_store, buf, disabled


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Output("mock-stream-buffer", "data", allow_duplicate=True),
    Output("mock-stream-interval", "disabled", allow_duplicate=True),
    Input("btn-designer-revise-stale", "n_clicks"),
    State("designer-session-store", "data"),
    State("session", "data"),
    State("image-support-store", "data"),
    prevent_initial_call=True,
)
def on_designer_revise_stale(
    n: Any, store: Any, session: Any, image_support: Any
) -> Any:
    """Discard a stale mock and regenerate greenfield from the current catalog.

    The vision or AI features changed after the mock was generated, so a
    surgical refine can't be trusted to reconcile the change (notably feature
    removals). We discard the mock and regenerate greenfield from the current
    on-disk catalog — for a brownfield project the existing UI still feeds in as
    a styling reference, but content is spec-driven so removals stick. The
    user's stated preferences and reference screenshots carry forward.

    This must not write to ``session``: ``render_page`` rebuilds the whole
    designer layout on any session change, which would recreate
    ``designer-session-store`` from the on-disk (still-stale) mock and clobber
    the step-5 streaming store. No staleness acknowledgement is needed — the
    completed regen saves a mock newer than its inputs, so staleness self-clears.
    """
    if not n or not store:
        return no_update, no_update, no_update
    sess = session or {}
    model, api_key, search_cfg, wd, support, api_base, aws_kw = _llm_params(
        sess, image_support
    )
    _vision = sess.get("vision_statement")
    _ai_feat = (project_manager.load_ai_features(wd) if wd else None) or sess.get(
        "ai_features"
    )
    _fs = (project_manager.load_feature_specs(wd) if wd else None) or sess.get(
        "feature_specs"
    )
    planning_ctx: dict[str, Any] | None = (
        {
            "vision_statement": _vision,
            **({"ai_features": _ai_feat} if _ai_feat else {}),
            **({"feature_specs": _fs} if _fs else {}),
        }
        if _vision
        else None
    )
    regen_store = {
        "step": store.get("step", 6),
        "preference_text": store.get("preference_text", ""),
        "screenshots": store.get("screenshots", []),
        "mock_html": "",
        "finalized": False,
        "_stale_inputs": [],
        "_has_existing_ui": store.get("_has_existing_ui", False),
    }
    return _start_gen(
        regen_store, wd, model, api_key, search_cfg, support, planning_ctx,
        api_base=api_base, extra_kwargs=aws_kw or None,
        session=sess,
    )


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Output("mock-stream-buffer", "data", allow_duplicate=True),
    Output("mock-stream-interval", "disabled", allow_duplicate=True),
    Input("btn-designer-retry", "n_clicks"),
    State("designer-session-store", "data"),
    State("session", "data"),
    State("image-support-store", "data"),
    prevent_initial_call=True,
)
def on_designer_retry(n: Any, store: Any, session: Any, image_support: Any) -> Any:
    if not n or not store:
        return no_update, no_update, no_update
    sess = session or {}
    model, api_key, search_cfg, wd, support, api_base, aws_kw = _llm_params(
        sess, image_support
    )
    existing_html: str | None = None
    if store.get("_has_existing_html") and wd:
        mock_path = (
            project_manager.get_version_dir(
                wd, project_manager.active_version(wd, sess)
            )
            / "design"
            / "mock.html"
        )
        try:
            existing_html = mock_path.read_text()
        except (OSError, FileNotFoundError):
            pass
    # D-DM8: a retry must reproduce the draw it is retrying. Both the mode and
    # the planning context now come back: refine draws carry planning context
    # too (they always did at the refine call site), and every draw is
    # manifest-bearing, so withholding it here would leave the manifest
    # instruction referencing sections absent from the prompt.
    new_store, buf, disabled = _start_gen(
        store, wd, model, api_key, search_cfg, support,
        _planning_ctx(sess, wd),
        existing_html=existing_html,
        capture_mode=bool(store.get("_capture_mode")),
        api_base=api_base,
        extra_kwargs=aws_kw or None,
        session=sess,
    )
    return new_store, buf, disabled
