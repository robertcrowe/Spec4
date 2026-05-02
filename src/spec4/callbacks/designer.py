from __future__ import annotations

import logging
import os
import pathlib
import re
import sys
import threading
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"

from dash import ALL, Input, Output, State, callback, ctx, no_update

from spec4.agents.designer import (
    DesignerSession,
    collect_ui_source_files,
    generate_mock_streaming,
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

# keyed by gen_id stored in designer-session-store["_gen_id"]
# _run() is the sole writer of buf["text"]; poll callbacks only read it.
# CPython's GIL makes this single-writer pattern safe without a lock.
_MOCK_BUFFERS: dict[str, dict[str, Any]] = {}

# Final HTML keyed by gen_id.  Written by _run() before setting done=True;
# read and popped by on_mock_done (triggered via mock-done-store signal).
# Kept separate from _MOCK_BUFFERS so the large payload never travels through
# the poll callback response, which would race with the next interval tick.
_FINAL_HTML: dict[str, str] = {}


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


def _start_gen(
    store: dict[str, Any],
    working_dir: str | None,
    model: str,
    api_key: str,
    tavily_key: str | None,
    image_support: bool,
    planning_context: dict[str, Any] | None = None,
    existing_html: str | None = None,
    capture_mode: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Launch generation in a background thread.

    Returns (updated_store, cleared_buffer, interval_disabled=False).
    """
    gen_id = str(uuid.uuid4())
    stop_ev = threading.Event()
    buf_entry: dict[str, Any] = {"done": False, "stop": stop_ev, "text": ""}
    _MOCK_BUFFERS[gen_id] = buf_entry

    ds: DesignerSession = {
        "step": store.get("step", 5),
        "preference_text": store.get("preference_text", ""),
        "screenshots": store.get("screenshots", []),
        "mock_html": store.get("mock_html", ""),
        "finalized": False,
    }

    def _run() -> None:
        snippets: list[str] = []
        if not existing_html and working_dir:
            snippets = collect_ui_source_files(pathlib.Path(working_dir))
        if _DEV_MODE:
            print("\n[Designer] Generating mock...", flush=True)
        for chunk in generate_mock_streaming(
            ds, model, api_key, snippets, image_support, tavily_key, stop_ev,
            planning_context=planning_context,
            existing_html=existing_html,
            capture_mode=capture_mode,
        ):
            buf_entry["text"] += chunk
            if _DEV_MODE and not chunk.startswith("__"):
                print(chunk, end="", flush=True, file=sys.stdout)
        if _DEV_MODE:
            print("\n[Designer] Done.", flush=True)
        if gen_id not in _MOCK_BUFFERS:
            return
        # Do the slow work (HTML extraction + disk save) here in the background
        # thread so the poll callback returns instantly and can't race itself.
        accumulated = buf_entry["text"]
        if "__DONE__" in accumulated and "__GENERATION_ERROR__:" not in accumulated:
            html_text = accumulated.replace("__DONE__", "").strip()
            extracted = _extract_html(html_text)
            if extracted is None:
                buf_entry["text"] += (
                    "__GENERATION_ERROR__: The model did not return a valid HTML "
                    "document. Please retry or refine your style description."
                )
            else:
                if len(extracted) > 512_000:
                    extracted = (
                        extracted[:512_000]
                        + "\n<!-- Designer: output truncated at 512 kB -->"
                    )
                if working_dir:
                    design_dir_path = pathlib.Path(working_dir) / ".spec4" / "design"
                    save_ds: DesignerSession = {
                        "step": 6,
                        "preference_text": ds["preference_text"],
                        "screenshots": ds["screenshots"],
                        "mock_html": extracted,
                        "finalized": False,
                    }
                    try:
                        save_session(save_ds, design_dir_path)
                        save_mock(extracted, design_dir_path)
                    except Exception as exc:
                        logger.warning(
                            "Designer: could not persist session to disk: %s", exc
                        )
                _FINAL_HTML[gen_id] = extracted
                buf_entry["final_html"] = extracted
        _MOCK_BUFFERS[gen_id]["done"] = True

    threading.Thread(target=_run, daemon=True).start()

    updated_store = {
        **store, "step": 5, "_gen_id": gen_id, "_existing_html": existing_html
    }
    cleared_buffer: dict[str, Any] = {
        "text": "", "tokens": 0, "progress": 0, "error": None
    }
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
    content: Any
    if step == 1:
        content = _step1_content()
    elif step == 2:
        content = _step2_content(bool(store.get("_has_existing_ui", True)))
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
        content = _step7_content(store)
    else:
        content = _step2_content(bool(store.get("_has_existing_ui", True)))
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
        return {**(store or {}), "step": 3}, no_update, no_update
    # "Modify existing" — capture the project's current look and feel
    sess = session or {}
    model: str = sess.get("model") or ""
    api_key: str = sess.get("api_key") or ""
    tavily_key: str | None = sess.get("tavily_api_key")
    wd: str | None = sess.get("working_dir")
    support: bool = bool(image_support) if image_support is not None else True
    new_store, buf, disabled = _start_gen(
        store or {}, wd, model, api_key, tavily_key, support, capture_mode=True
    )
    return new_store, buf, disabled


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
    model: str = sess.get("model") or ""
    api_key: str = sess.get("api_key") or ""
    tavily_key: str | None = sess.get("tavily_api_key")
    wd: str | None = sess.get("working_dir")
    support: bool = bool(image_support) if image_support is not None else True
    planning_ctx: dict[str, Any] = {
        "vision_statement": sess.get("vision_statement"),
    } if sess.get("vision_statement") else {}
    new_store, buf, disabled = _start_gen(
        updated, wd, model, api_key, tavily_key, support, planning_ctx or None
    )
    return new_store, buf, disabled


@callback(
    Output("mock-stream-buffer", "data", allow_duplicate=True),
    Output("mock-done-store", "data", allow_duplicate=True),
    Output("mock-stream-interval", "disabled", allow_duplicate=True),
    Input("mock-stream-interval", "n_intervals"),
    State("mock-stream-buffer", "data"),
    State("designer-session-store", "data"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_mock_stream_poll(
    n: Any,
    current_buffer: Any,
    store: Any,
    session: Any,
) -> Any:
    gen_id: str | None = (store or {}).get("_gen_id")
    if not gen_id or gen_id not in _MOCK_BUFFERS:
        return no_update, no_update, True  # disable interval

    buf_entry = _MOCK_BUFFERS[gen_id]
    accumulated = buf_entry["text"]

    cb: dict[str, Any] = current_buffer or {
        "text": "", "tokens": 0, "progress": 0, "error": None
    }

    if "__GENERATION_ERROR__:" in accumulated:
        idx = accumulated.index("__GENERATION_ERROR__:")
        error_msg = accumulated[idx + len("__GENERATION_ERROR__:"):].strip()
        # Empty error_msg (e.g. exception with no message) must still surface as an
        # error so the user sees the retry button instead of a frozen progress bar.
        error_msg = error_msg or "Generation failed — check the server log for details."
        _MOCK_BUFFERS.pop(gen_id, None)
        return (
            {**cb, "text": accumulated, "error": error_msg},
            no_update,
            True,
        )

    # _run() pre-computes final_html (extraction + disk save) before setting done.
    # Emit a tiny signal to mock-done-store rather than including the full HTML in
    # this response: the poll callback fires every 250 ms, so a large response risks
    # losing a Dash "latest-trigger-wins" race with the next interval tick.
    # on_mock_done picks up the signal and delivers the HTML in a one-shot response.
    final_html: str | None = buf_entry.get("final_html")
    if final_html is not None:
        _MOCK_BUFFERS.pop(gen_id, None)
        final_buf = {
            **cb,
            "text": "",
            "tokens": len(final_html),
            "progress": 100,
            "error": None,
        }
        return final_buf, {"gen_id": gen_id}, True

    # Generator finished (done flag set) but yielded no recognised sentinel.
    # This happens when the stop-event fires mid-stream.  Disable the interval
    # cleanly rather than polling forever.
    if buf_entry.get("done"):
        _MOCK_BUFFERS.pop(gen_id, None)
        return no_update, no_update, True

    tokens = len(accumulated)
    # 80k tokens × ~4 chars/token = 320k chars for a typical mock; scale to 95%.
    progress = min(95, tokens * 95 // 320_000)
    return (
        {**cb, "text": accumulated, "tokens": tokens, "progress": progress},
        no_update,
        no_update,
    )


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("mock-done-store", "data"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_mock_done(signal: Any, store: Any) -> Any:
    """Deliver the completed mock HTML to the session store.

    Triggered by the tiny completion signal emitted by on_mock_stream_poll,
    this callback is the sole writer of step=6 + mock_html.  Because it fires
    from a unique store-change event (not the recurring interval), it has no
    concurrent racing sibling that could discard its response.
    """
    if not signal or not store:
        return no_update
    gen_id: str | None = signal.get("gen_id")
    if not gen_id or gen_id not in _FINAL_HTML:
        return no_update
    final_html = _FINAL_HTML.pop(gen_id)
    return {**(store or {}), "step": 6, "mock_html": final_html}


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-designer-approve", "n_clicks"),
    State("designer-session-store", "data"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_designer_approve(n: Any, store: Any, session: Any) -> Any:
    if not n or not store:
        return no_update, no_update
    session = session or {}
    working_dir: str | None = session.get("working_dir")
    if working_dir:
        design_dir = pathlib.Path(working_dir) / ".spec4" / "design"
        ds: DesignerSession = {
            "step": store.get("step", 6),
            "preference_text": store.get("preference_text", ""),
            "screenshots": store.get("screenshots", []),
            "mock_html": store.get("mock_html", ""),
            "finalized": True,
        }
        save_session(ds, design_dir)
        save_mock(ds["mock_html"], design_dir)
    return {
        **session,
        "phase": "chat",
        "active_agent": "stack_advisor",
        "stack_advisor_messages": [],
        "messages": [],
        "_initial_turn_done": False,
    }, "/chat"


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
    return {**store, "step": 7}


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("btn-designer-refine-cancel", "n_clicks"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_refine_cancel(n: Any, store: Any) -> Any:
    if not n or not store:
        return no_update
    return {**store, "step": 6, "refine_images": []}


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("designer-refine-upload", "contents"),
    State("designer-refine-upload", "filename"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_refine_upload(contents: Any, filename: Any, store: Any) -> Any:
    if not contents or not store:
        return no_update
    images: list[dict[str, str]] = list(store.get("refine_images", []))
    images.append({"data": contents, "filename": filename or "image"})
    return {**store, "refine_images": images}


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input({"type": "designer-refine-image-delete", "index": ALL}, "n_clicks"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_refine_image_delete(n_clicks_list: Any, store: Any) -> Any:
    if not any(n for n in (n_clicks_list or []) if n):
        return no_update
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        return no_update
    idx: int = triggered["index"]
    images: list[dict[str, str]] = list((store or {}).get("refine_images", []))
    if 0 <= idx < len(images):
        images.pop(idx)
    return {**(store or {}), "refine_images": images}


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
    model: str = sess.get("model") or ""
    api_key: str = sess.get("api_key") or ""
    tavily_key: str | None = sess.get("tavily_api_key")
    wd: str | None = sess.get("working_dir")
    support: bool = bool(image_support) if image_support is not None else True
    new_store, buf, disabled = _start_gen(
        updated, wd, model, api_key, tavily_key, support,
        existing_html=existing_html,
    )
    return new_store, buf, disabled


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
    model: str = sess.get("model") or ""
    api_key: str = sess.get("api_key") or ""
    tavily_key: str | None = sess.get("tavily_api_key")
    wd: str | None = sess.get("working_dir")
    support: bool = bool(image_support) if image_support is not None else True
    existing_html: str | None = store.get("_existing_html")
    planning_ctx: dict[str, Any] = (
        {"vision_statement": sess.get("vision_statement")}
        if not existing_html and sess.get("vision_statement")
        else {}
    )
    new_store, buf, disabled = _start_gen(
        store, wd, model, api_key, tavily_key, support,
        planning_ctx or None,
        existing_html=existing_html,
    )
    return new_store, buf, disabled
