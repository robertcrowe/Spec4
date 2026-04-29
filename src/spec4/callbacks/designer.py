from __future__ import annotations

import pathlib
import re
import threading
import uuid
from typing import Any

from dash import ALL, Input, Output, State, callback, ctx, no_update

from spec4.agents.designer import (
    DesignerSession,
    clear_session,
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


def _extract_html(text: str) -> str:
    """Extract an HTML document from model output, falling back to raw text."""
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
    return f"<!-- Designer: raw output, no HTML wrapper detected -->\n{text.strip()}"


def _start_gen(
    store: dict[str, Any],
    working_dir: str | None,
    model: str,
    api_key: str,
    tavily_key: str | None,
    image_support: bool,
    planning_context: dict[str, Any] | None = None,
    existing_html: str | None = None,
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
        for chunk in generate_mock_streaming(
            ds, model, api_key, snippets, image_support, tavily_key, stop_ev,
            planning_context=planning_context,
            existing_html=existing_html,
        ):
            buf_entry["text"] += chunk
        if gen_id in _MOCK_BUFFERS:
            _MOCK_BUFFERS[gen_id]["done"] = True

    threading.Thread(target=_run, daemon=True).start()

    updated_store = {**store, "step": 5, "_gen_id": gen_id}
    cleared_buffer: dict[str, Any] = {
        "text": "",
        "tokens": 0,
        "progress": 0,
        "error": None,
        "_debug_events": ["Generation started"],
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
        content = _step2_content()
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
        content = _step2_content()
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
    Input("btn-designer-modify-existing", "n_clicks"),
    Input("btn-designer-create-new", "n_clicks"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_step2_choice(n_modify: Any, n_create: Any, store: Any) -> Any:
    if not ctx.triggered_id or not (n_modify or n_create):
        return no_update
    return {**(store or {}), "step": 3}


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
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_screenshot_upload(contents: Any, store: Any) -> Any:
    if not contents or not store:
        return no_update
    screenshots: list[dict[str, str]] = list(store.get("screenshots", []))
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
    Output("designer-session-store", "data", allow_duplicate=True),
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
        "text": "",
        "tokens": 0,
        "progress": 0,
        "error": None,
        "_debug_events": [],
    }
    debug_events: list[str] = list(cb.get("_debug_events") or [])

    _SENTINELS = {
        "__DBG_INPUT_START__": "Sending input to model...",
        "__DBG_INPUT_END__": "Input sent — awaiting first output token",
        "__DBG_OUTPUT_START__": "First output token received",
    }
    for sentinel, label in _SENTINELS.items():
        if sentinel in accumulated:
            accumulated = accumulated.replace(sentinel, "")
            if label not in debug_events:
                debug_events.append(label)

    if "__GENERATION_ERROR__:" in accumulated:
        idx = accumulated.index("__GENERATION_ERROR__:")
        error_msg = accumulated[idx + len("__GENERATION_ERROR__:") :].strip()
        debug_events.append(f"Error: {error_msg}")
        _MOCK_BUFFERS.pop(gen_id, None)
        return (
            {
                **cb,
                "text": accumulated,
                "error": error_msg,
                "_debug_events": debug_events,
            },
            no_update,
            True,
        )

    if "__DONE__" in accumulated:
        debug_events.append("Output complete")
        html_text = accumulated.replace("__DONE__", "").strip()
        extracted = _extract_html(html_text)
        if len(extracted) > 512_000:
            extracted = (
                extracted[:512_000] + "\n<!-- Designer: output truncated at 512 kB -->"
            )
        sess = session or {}
        working_dir: str | None = sess.get("working_dir")
        if working_dir:
            design_dir = pathlib.Path(working_dir) / ".spec4" / "design"
            ds: DesignerSession = {
                "step": 6,
                "preference_text": (store or {}).get("preference_text", ""),
                "screenshots": (store or {}).get("screenshots", []),
                "mock_html": extracted,
                "finalized": False,
            }
            save_session(ds, design_dir)
            save_mock(extracted, design_dir)
        _MOCK_BUFFERS.pop(gen_id, None)
        updated_store = {**(store or {}), "step": 6, "mock_html": extracted}
        final_buf = {
            **cb,
            "text": extracted,
            "tokens": len(extracted),
            "progress": 100,
            "error": None,
            "_debug_events": debug_events,
        }
        return final_buf, updated_store, True

    tokens = len(accumulated)
    progress = min(95, tokens // 50)
    updated_buf = {
        **cb,
        "text": accumulated,
        "tokens": tokens,
        "progress": progress,
        "_debug_events": debug_events,
    }
    return updated_buf, no_update, no_update


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
    State("session", "data"),
    prevent_initial_call=True,
)
def on_designer_start_over(n: Any, store: Any, session: Any) -> Any:
    if not n:
        return no_update, no_update, no_update
    gen_id: str | None = (store or {}).get("_gen_id")
    if gen_id:
        entry = _MOCK_BUFFERS.pop(gen_id, None)
        if entry:
            entry["stop"].set()
    working_dir: str | None = (session or {}).get("working_dir")
    if working_dir:
        design_dir = pathlib.Path(working_dir) / ".spec4" / "design"
        clear_session(design_dir)
    cleared_buffer: dict[str, Any] = {
        "text": "",
        "tokens": 0,
        "progress": 0,
        "error": None,
    }
    return _default_designer_session(step=2), cleared_buffer, True


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
