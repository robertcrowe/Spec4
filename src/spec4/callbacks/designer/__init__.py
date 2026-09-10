"""Designer's callbacks -- the wizard that draws an HTML mock of the product.

Cleanup Phase 4h turned this module into a package and moved the three
self-contained concerns into siblings, one module each:

* :mod:`spec4.callbacks.designer._mock_gen` -- the generation core:
  ``MOCK_BUFFERS``, ``_start_gen`` and its worker thread, and the helpers that
  resolve a draw's parameters, extract its HTML, persist it and size its
  progress bar.
* :mod:`spec4.callbacks.designer._wizard` -- the wizard's own steps, from the
  modify/create choice through Approve, Back and Start Over.
* :mod:`spec4.callbacks.designer._refine` -- refining a drawn mock, and
  redrawing a failed one.

The two callbacks that stay are the ones driving the wizard *shell* rather than
one screen's buttons: ``render_designer_step`` paints whichever step the store
names, and ``on_mock_stream_poll`` feeds it while a draw runs and delivers the
finished mock in-band.

The import path ``spec4.callbacks.designer`` is unchanged -- ``app.py`` imports
it to register these callbacks. Phase 4j then moved every importer onto the
owning module and dropped the re-exports nothing reached through here, so what
is listed below is exactly the set some importer outside the owning module
still needs. ``__all__`` is
load-bearing rather than decorative: ``[tool.mypy] strict`` implies
``no_implicit_reexport``, so without it a re-exported name could not be
imported from this module at all. It is also what keeps ``F401``
off the sibling imports that exist to register.

``_MOCK_BUFFERS`` below is the same dict object as ``_mock_gen.MOCK_BUFFERS``.
``project_manager`` and ``threading`` stay bound here because they are reached
through this module from outside to be patched.
"""

from __future__ import annotations

import threading
from typing import Any

from dash import Input, Output, State, callback, ctx, no_update

from spec4 import llm_selection, project_manager
from spec4.callbacks.designer._mock_gen import (
    MOCK_BUFFERS as _MOCK_BUFFERS,
)
from spec4.callbacks.designer._mock_gen import (
    _DEFAULT_EXPECTED_CHARS,
    _DEV_MODE,
    _MAX_DELIVERY_TICKS,
    _expected_stream_chars,
    _extract_html,
    _persist_manifest,
    _start_gen,
)
from spec4.callbacks.designer._refine import (
    on_designer_auto_retry,
    on_designer_refine_image_delete,
    on_designer_refine_upload,
    on_designer_regenerate,
    on_designer_retry,
    on_designer_retry_model,
)
from spec4.callbacks.designer._wizard import (
    on_designer_carry_forward,
    on_designer_start_over,
    on_designer_step_back,
    on_designer_step2_choice,
)
from spec4.layouts.designer import (
    DESIGNER_STEPPER_ID,
    _step1_content,
    _step2_content,
    _step3_content,
    _step4_content,
    _step5_content,
    _step6_content,
    _step7_content,
    designer_step_row,
    stepper_index,
)

__all__ = [
    "_DEFAULT_EXPECTED_CHARS",
    "_DEV_MODE",
    "_MAX_DELIVERY_TICKS",
    "_MOCK_BUFFERS",
    "_expected_stream_chars",
    "_extract_html",
    "_persist_manifest",
    "_start_gen",
    "on_designer_auto_retry",
    "on_designer_carry_forward",
    "on_designer_refine_image_delete",
    "on_designer_refine_upload",
    "on_designer_regenerate",
    "on_designer_retry",
    "on_designer_retry_model",
    "on_designer_start_over",
    "on_designer_step2_choice",
    "on_designer_step_back",
    "on_mock_stream_poll",
    "project_manager",
    "render_designer_step",
    "threading",
]


@callback(
    Output("designer-step-content", "children"),
    # The step row, re-rendered rather than re-indexed. This was
    # `designer-stepper.active`, a `dmc.Stepper` property; the plain-text row
    # that replaced the Stepper has no such property, so the Output moved to
    # the row container's children in the same change (see
    # `tests/test_designer_wizard_register.py`, which pins that it resolves).
    Output(DESIGNER_STEPPER_ID, "children"),
    Input("designer-session-store", "data"),
    Input("mock-stream-buffer", "data"),
    State("image-support-store", "data"),
    State("session", "data"),
)
def render_designer_step(
    store: Any, buffer_data: Any, image_support: Any, session: Any = None
) -> Any:
    if not store:
        return no_update, no_update
    # Screenshot upload is gated on image support, and that is a property of the
    # model *Designer* runs on — not of the default. With a default that handles
    # images and a Designer override that does not, the store-wide flag says yes
    # and the wizard keeps offering an upload the model cannot use. The override
    # is probed exactly like the default (`llm_selection.probe_capabilities`);
    # this is the other half of that, reading the answer back.
    image_support = llm_selection.capability(
        session or {}, "designer", "image_support", image_support
    )
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
        content = _step5_content(buffer_data, image_support)
    elif step == 6:
        content = _step6_content(store, session)
    elif step == 7:
        content = _step7_content(store, image_support)
    else:
        content = _step2_content(
            bool(store.get("_has_existing_ui", True)),
            bool(store.get("_is_revision", False)),
        )
    return content, designer_step_row(stepper_index(step))


@callback(
    Output("mock-stream-buffer", "data", allow_duplicate=True),
    Output("designer-session-store", "data", allow_duplicate=True),
    Output("mock-stream-interval", "disabled", allow_duplicate=True),
    Input("mock-stream-interval", "n_intervals"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_mock_stream_poll(_n: Any, store: Any) -> Any:
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
        error_msg = accumulated[idx + len("__GENERATION_ERROR__:") :].strip()
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
    # Capped at 99 while the stream is live: the estimate is made before a
    # single character arrives, and a model that writes a draft and then a whole
    # second document blows past it. A bar sitting at 100% while text is still
    # arriving reads as a finished generation that failed to display — the one
    # thing the developer must not be told wrongly. 100 means delivered.
    progress = min(99, tokens * 100 // expected)
    return (
        {"tokens": tokens, "progress": progress, "error": None},
        no_update,
        no_update,
    )
