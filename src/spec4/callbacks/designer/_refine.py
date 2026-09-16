"""Refining a drawn mock, and redrawing one that failed.

Cleanup Phase 4h split ``callbacks/designer.py``; this module holds everything
downstream of a finished draw -- the refine panel (step 7) with its reference
images, the regenerate that applies it, the greenfield regeneration a stale
mock offers, and the retry pair: the picker a failed draw opens, and the two
entry points that re-run it -- the Retry button and the one-shot auto-retry
interval -- through the shared ``_rerun_failed_draw``.

Every draw here goes through ``_mock_gen._start_gen``, the launcher the wizard
uses too, so a refine and a first draw cannot diverge.
"""

from __future__ import annotations

import contextlib
from typing import Any

from dash import ALL, Input, Output, State, callback, ctx, no_update

from spec4 import project_manager
from spec4.callbacks._shared import _open_pick_fields
from spec4.callbacks.designer._mock_gen import (
    _llm_params,
    _planning_ctx,
    _start_gen,
    existing_manifest_for_refine,
)


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("btn-designer-refine", "n_clicks"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_refine(n: int | None, store: Any) -> Any:
    if not n or not store:
        return no_update
    return {**store, "step": 7, "refine_text": ""}


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("btn-designer-refine-cancel", "n_clicks"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_refine_cancel(n: int | None, store: Any) -> Any:
    if not n or not store:
        return no_update
    return {**store, "step": 6, "refine_images": [], "refine_text": ""}


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input("designer-refine-upload", "contents"),
    State("designer-refine-upload", "filename"),
    State({"type": "designer-refine-annotation", "index": ALL}, "value"),
    State("designer-refine-input", "value"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_refine_upload(
    contents: str | list[str] | None,
    filename: str | list[str] | None,
    annotations: list[str | None],
    refine_text: str | None,
    store: Any,
) -> Any:
    if not contents or not store:
        return no_update
    images: list[dict[str, str]] = list(store.get("refine_images", []))
    for i, ann in enumerate(annotations or []):
        if i < len(images):
            images[i] = {**images[i], "annotation": ann or ""}
    new_contents = contents if isinstance(contents, list) else [contents]
    new_filenames = filename if isinstance(filename, list) else [filename]
    for data, fname in zip(new_contents, new_filenames, strict=False):
        images.append({"data": data, "filename": fname or "image", "annotation": ""})
    return {**store, "refine_images": images, "refine_text": refine_text or ""}


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Input({"type": "designer-refine-image-delete", "index": ALL}, "n_clicks"),
    State({"type": "designer-refine-annotation", "index": ALL}, "value"),
    State("designer-refine-input", "value"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_designer_refine_image_delete(
    n_clicks_list: list[int | None],
    annotations: list[str | None],
    refine_text: str | None,
    store: Any,
) -> Any:
    if not any(n for n in (n_clicks_list or []) if n):
        return no_update
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        return no_update
    idx: int = triggered["index"]
    images: list[dict[str, str]] = list((store or {}).get("refine_images", []))
    for i, ann in enumerate(annotations or []):
        if i < len(images):
            images[i] = {**images[i], "annotation": ann or ""}
    if 0 <= idx < len(images):
        images.pop(idx)
    return {**(store or {}), "refine_images": images, "refine_text": refine_text or ""}


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Output("mock-stream-buffer", "data", allow_duplicate=True),
    Output("mock-stream-interval", "disabled", allow_duplicate=True),
    Input("btn-designer-regenerate", "n_clicks"),
    State("designer-refine-input", "value"),
    State({"type": "designer-refine-annotation", "index": ALL}, "value"),
    State("designer-session-store", "data"),
    State("session", "data"),
    State("image-support-store", "data"),
    prevent_initial_call=True,
)
def on_designer_regenerate(  # noqa: PLR0913  # parameters are the callback's Input/State list
    n: int | None,
    refine_text: str | None,
    annotations: list[str | None],
    store: Any,
    session: Any,
    image_support: bool | None,
) -> Any:
    if not n or not store:
        return no_update, no_update, no_update
    pref: str = store.get("preference_text", "")
    if refine_text and refine_text.strip():
        pref = f"{pref}\n\n--- Refinement ---\n{refine_text.strip()}"
    refine_images: list[dict[str, str]] = list(store.get("refine_images", []))
    for i, ann in enumerate(annotations or []):
        if i < len(refine_images):
            refine_images[i] = {**refine_images[i], "annotation": ann or ""}
    # Same shape the create path (on_designer_generate_mock) builds for
    # screenshots — {"data", "annotation"} — so build_mock_prompt sends refine
    # images through the identical image_url + "Note: ..." rendering.
    screenshots: list[dict[str, str]] = list(store.get("screenshots", []))
    for img in refine_images:
        screenshots.append(
            {"data": img["data"], "annotation": img.get("annotation", "")}
        )
    existing_html: str | None = store.get("mock_html") or None
    updated = {**store, "preference_text": pref, "screenshots": screenshots}
    sess = session or {}
    model, api_key, search_cfg, wd, support, api_base, aws_kw, effort = _llm_params(
        sess, image_support
    )
    # The manifest the refine updates in place (D-DM9): shown next to the
    # existing HTML so surviving entries keep their names instead of being
    # re-invented from the markup.
    existing_manifest = (
        existing_manifest_for_refine(store, wd, sess) if existing_html else None
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
        updated,
        wd,
        model,
        api_key,
        search_cfg,
        support,
        planning_ctx,
        existing_html=existing_html,
        api_base=api_base,
        extra_kwargs=aws_kw or None,
        session=sess,
        effort=effort,
        existing_manifest=existing_manifest,
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
    n: int | None, store: Any, session: Any, image_support: Any
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
    model, api_key, search_cfg, wd, support, api_base, aws_kw, effort = _llm_params(
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
        regen_store,
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


@callback(
    Output("session", "data", allow_duplicate=True),
    Input("btn-designer-retry-model", "n_clicks"),
    State("designer-session-store", "data"),
    State("mock-stream-buffer", "data"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_designer_retry_model(
    n: int | None, store: Any, buffer_data: Any, session: Any
) -> Any:
    """Open the model picker from a failed draw, keeping the draw recoverable.

    Opening the picker writes `session`, which rebuilds the page and re-creates
    the wizard's memory stores; a failed draw has saved nothing to disk, so
    without a snapshot the developer would come back to the wizard intro with
    their preference text and screenshots gone. Everything `on_designer_retry`
    needs to reproduce the draw goes into `_designer_failed_draw`, and
    `designer_layout` rebuilds the error panel from it.

    Like the chat button, this only opens the fields — Retry still runs the draw.
    """
    if not n or not store:
        return no_update
    session = session or {}
    error = (buffer_data or {}).get("error")
    if not error:
        return no_update
    snapshot = {
        "error": error,
        "preference_text": store.get("preference_text", ""),
        "screenshots": store.get("screenshots", []),
        "_capture_mode": bool(store.get("_capture_mode")),
        "_has_existing_html": bool(store.get("_has_existing_html")),
    }
    return {
        **_open_pick_fields(session, retry=True),
        "_designer_failed_draw": snapshot,
    }


def _rerun_failed_draw(store: Any, session: Any, image_support: Any) -> Any:
    """Reproduce the draw that failed. Returns the three store outputs plus session.

    Shared by the Retry button and by the auto-retry that fires once a different
    model has been chosen, so the two cannot reproduce the draw differently.
    """
    sess = session or {}
    model, api_key, search_cfg, wd, support, api_base, aws_kw, effort = _llm_params(
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
        with contextlib.suppress(OSError, FileNotFoundError):
            existing_html = mock_path.read_text()
    existing_manifest = (
        existing_manifest_for_refine(store, wd, sess) if existing_html else None
    )
    # D-DM8: a retry must reproduce the draw it is retrying. Both the mode and
    # the planning context now come back: refine draws carry planning context
    # too (they always did at the refine call site), and every draw is
    # manifest-bearing, so withholding it here would leave the manifest
    # instruction referencing sections absent from the prompt.
    new_store, buf, disabled = _start_gen(
        store,
        wd,
        model,
        api_key,
        search_cfg,
        support,
        _planning_ctx(sess, wd),
        existing_html=existing_html,
        capture_mode=bool(store.get("_capture_mode")),
        api_base=api_base,
        extra_kwargs=aws_kw or None,
        session=sess,
        effort=effort,
        existing_manifest=existing_manifest,
    )
    # The snapshot existed only to carry this draw across the model picker's
    # page rebuild. Drawing spends it; left behind, a later render would
    # resurrect an error the developer has already acted on — and would re-arm
    # the auto-retry interval, drawing again on every visit.
    cleared = (
        {**sess, "_designer_failed_draw": None}
        if sess.get("_designer_failed_draw")
        else no_update
    )
    return new_store, buf, disabled, cleared


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Output("mock-stream-buffer", "data", allow_duplicate=True),
    Output("mock-stream-interval", "disabled", allow_duplicate=True),
    Output("session", "data", allow_duplicate=True),
    Input("btn-designer-retry", "n_clicks"),
    State("designer-session-store", "data"),
    State("session", "data"),
    State("image-support-store", "data"),
    prevent_initial_call=True,
)
def on_designer_retry(
    n: int | None, store: Any, session: Any, image_support: Any
) -> Any:
    """Re-run the failed draw on the model it already has."""
    if not n or not store:
        return no_update, no_update, no_update, no_update
    return _rerun_failed_draw(store, session, image_support)


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Output("mock-stream-buffer", "data", allow_duplicate=True),
    Output("mock-stream-interval", "disabled", allow_duplicate=True),
    Output("session", "data", allow_duplicate=True),
    Input("designer-autoretry-interval", "n_intervals"),
    State("designer-session-store", "data"),
    State("session", "data"),
    State("image-support-store", "data"),
    prevent_initial_call=True,
)
def on_designer_auto_retry(
    n: int | None, store: Any, session: Any, image_support: Any
) -> Any:
    """Draw again as soon as a different model has been chosen.

    Choosing a model from a failed draw *is* the decision to re-run it, so no
    second click is asked for. It cannot happen in `on_gate_continue` the way
    the chat retry does: Designer's gate replaces its wizard, so the stores this
    writes to are not mounted while the picker is open. `designer_layout` arms a
    one-shot interval on the restored wizard instead — the same pattern the chat
    page uses to fire an agent's opening turn.
    """
    if not n or not store:
        return no_update, no_update, no_update, no_update
    # `or {}` not a default: the key exists and holds None on a clean session,
    # so a default would never be reached.
    failed = (session or {}).get("_designer_failed_draw") or {}
    if not failed.get("auto_retry"):
        return no_update, no_update, no_update, no_update
    return _rerun_failed_draw(store, session, image_support)
