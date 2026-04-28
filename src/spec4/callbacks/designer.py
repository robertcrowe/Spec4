from __future__ import annotations

import pathlib
from typing import Any

from dash import ALL, Input, Output, State, callback, ctx, no_update

from spec4.agents.designer import (
    DesignerSession,
    clear_session,
    save_mock,
    save_session,
)
from spec4.layouts.designer import (
    _PLACEHOLDER_HTML,
    _default_designer_session,
    _step1_content,
    _step2_content,
    _step3_content,
    _step4_content,
    _step5_content,
    _step6_content,
    _step7_content,
)


@callback(
    Output("designer-step-content", "children"),
    Output("designer-stepper", "active"),
    Input("designer-session-store", "data"),
    State("image-support-store", "data"),
)
def render_designer_step(store: Any, image_support: Any) -> Any:
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
        content = _step5_content()
    elif step == 6:
        content = _step6_content(store)
    elif step == 7:
        content = _step7_content()
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


@callback(
    Output("session", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("btn-designer-skip-1", "n_clicks"),
    Input("btn-designer-skip-2", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_designer_skip(n1: Any, n2: Any, session: Any) -> Any:
    if not n1 and not n2:
        return no_update, no_update
    session = session or {}
    return {**session, "phase": "agent_select"}, "/agents"


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("btn-designer-modify-existing", "n_clicks"),
    Input("btn-designer-create-new", "n_clicks"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_step2_choice(
    n_modify: Any, n_create: Any, store: Any
) -> Any:
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
    Input("btn-designer-generate-mock", "n_clicks"),
    State({"type": "designer-screenshot-annotation", "index": ALL}, "value"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_generate_mock(n: Any, annotations: Any, store: Any) -> Any:
    if not n or not store:
        return no_update
    screenshots: list[dict[str, str]] = list(store.get("screenshots", []))
    for i, ann in enumerate(annotations or []):
        if i < len(screenshots):
            screenshots[i] = {**screenshots[i], "annotation": ann or ""}
    return {
        **store,
        "screenshots": screenshots,
        "step": 6,
        "mock_html": _PLACEHOLDER_HTML,
    }


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
        "phase": "agent_select",
    }, "/agents"


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("btn-designer-start-over", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_designer_start_over(n: Any, session: Any) -> Any:
    if not n:
        return no_update
    working_dir: str | None = (session or {}).get("working_dir")
    if working_dir:
        design_dir = pathlib.Path(working_dir) / ".spec4" / "design"
        clear_session(design_dir)
    return _default_designer_session(step=2)


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
    return {**store, "step": 6}


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("btn-designer-regenerate", "n_clicks"),
    State("designer-refine-input", "value"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_regenerate(n: Any, refine_text: Any, store: Any) -> Any:
    if not n or not store:
        return no_update
    pref: str = store.get("preference_text", "")
    if refine_text and refine_text.strip():
        pref = f"{pref}\n\nRefinements: {refine_text.strip()}"
    return {
        **store,
        "preference_text": pref,
        "step": 6,
        "mock_html": _PLACEHOLDER_HTML,
    }
