"""The Designer wizard's own steps -- the questions, and the way out of them.

Cleanup Phase 4h split ``callbacks/designer.py``; this module holds the
button-driven wizard: the "add a GUI" and modify/create choices (steps 1-2),
the style preferences and the reference screenshots (steps 3-4), the two skips
into Stack Advisor, and the three that close the wizard -- Approve, the
one-step Back, and Start Over.

Two of these start a draw -- ``on_designer_step2_choice``'s "Modify existing"
capture and ``on_designer_generate_mock`` -- and both go through
``_mock_gen._start_gen``, where the buffer and the thread live. Refining a
drawn mock belongs to ``_refine``, and painting the step content to the package
``__init__``.
"""

from __future__ import annotations

from typing import Any

from dash import ALL, Input, Output, State, callback, ctx, no_update

from spec4 import project_manager
from spec4.agents.designer import (
    DesignerSession,
    build_revision_note,
    revision_delta,
    save_mock,
    save_session,
)
from spec4.callbacks.designer._mock_gen import (
    MOCK_BUFFERS as _MOCK_BUFFERS,
)
from spec4.callbacks.designer._mock_gen import (
    _llm_params,
    _planning_ctx,
    _start_gen,
)
from spec4.layouts.designer import _default_designer_session


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
        "_designer_failed_draw": None,
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
    model, api_key, search_cfg, wd, support, api_base, aws_kw, effort = _llm_params(
        sess, image_support
    )
    # D-DM7: this generation carries the manifest instruction (it is the only
    # non-refine draw in the brownfield path, so it is the sole chance to
    # produce manifest.json — every later refinement passes existing_html,
    # which skips both the instruction and _persist_manifest). It therefore
    # needs the same planning context as every other manifest-bearing draw.
    new_store, buf, disabled = _start_gen(
        store or {},
        wd,
        model,
        api_key,
        search_cfg,
        support,
        _planning_ctx(sess, wd),
        capture_mode=True,
        api_base=api_base,
        extra_kwargs=aws_kw or None,
        session=sess,
        effort=effort,
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
    model, api_key, search_cfg, wd, support, api_base, aws_kw, effort = _llm_params(
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
        updated,
        wd,
        model,
        api_key,
        search_cfg,
        support,
        planning_ctx,
        api_base=api_base,
        extra_kwargs=aws_kw or None,
        session=sess,
        effort=effort,
    )
    return new_store, buf, disabled


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
        "_designer_failed_draw": None,
    }, "/chat"


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("btn-designer-step-back", "n_clicks"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_step_back(n: Any, store: Any) -> Any:
    """One step back inside the wizard — never out of it.

    The button is rendered by the two steps that have somewhere to go back to
    (Preferences and Screenshots) and by no others, so decrementing is the
    whole rule; the floor is step 2, the wizard's first question in every flow
    that does not open on the no-UI check. Leaving Designer is the status bar's
    Project link, not a button in here.
    """
    if not n or not store:
        return no_update
    return {**store, "step": max(2, int(store.get("step", 2)) - 1)}


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Output("mock-stream-buffer", "data", allow_duplicate=True),
    Output("mock-stream-interval", "disabled", allow_duplicate=True),
    Output("session", "data", allow_duplicate=True),
    Input("btn-designer-start-over", "n_clicks"),
    State("designer-session-store", "data"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_designer_start_over(n: Any, store: Any, session: Any) -> Any:
    """Discard the mock and start Designer again from its first question.

    Which model to draw with *is* Designer's first question, so starting over
    re-asks it — landing on the wizard intro with the previous choice silently
    still in force is not starting over. The override itself is kept, so the
    gate offers it back as "Keep …" alongside the default rather than making
    the developer re-enter a key (see the gate's carried-forward shape).

    Writing `session` re-renders the page and so re-creates the wizard's
    stores. That is safe precisely here: the generation is already stopped and
    its buffer dropped just above, so there is nothing in flight to orphan.
    """
    if not n:
        return no_update, no_update, no_update, no_update
    gen_id: str | None = (store or {}).get("_gen_id")
    if gen_id:
        entry = _MOCK_BUFFERS.pop(gen_id, None)
        if entry:
            entry["stop"].set()
    session = session or {}
    asked = {
        agent: answered
        for agent, answered in (session.get("agent_llm_asked") or {}).items()
        if agent != "designer"
    }
    return (
        {
            **_default_designer_session(step=2),
            "_has_existing_ui": (store or {}).get("_has_existing_ui", False),
        },
        {"text": "", "tokens": 0, "progress": 0, "error": None},
        True,
        {
            **session,
            "agent_llm_asked": asked,
            "agent_llm_draft": None,
            "_designer_failed_draw": None,
        },
    )
