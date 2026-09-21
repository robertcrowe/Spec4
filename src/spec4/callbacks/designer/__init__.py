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

The callbacks that stay are the ones driving the wizard *shell* rather than
one screen's buttons: ``render_designer_step`` paints whichever step the store
names, ``on_mock_stream_poll`` feeds it while a draw runs and delivers the
finished mock in-band, and ``on_designer_intro_toggle`` opens and closes the
usage notes that stand above every step (D-LR12).

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
from typing import TYPE_CHECKING, Any

from dash import Input, Output, State, callback, no_update

from spec4 import llm_selection, project_manager
from spec4.callbacks._shared import toggle_disclosure
from spec4.callbacks.designer._mock_gen import (
    MOCK_BUFFERS as _MOCK_BUFFERS,
)
from spec4.callbacks.designer._mock_gen import (
    _DEFAULT_EXPECTED_CHARS,
    _DEV_MODE,
    _MAX_DELIVERY_TICKS,
    DELIVERY_MS,
    _mock_design_dir,
    expected_stream_chars,
    extract_html,
    find_live_draw,
    persist_manifest,
    _start_gen,
    stream_progress,
)
from spec4.callbacks.designer._refine import (
    on_designer_auto_retry,
    on_designer_fix_errors,
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
    DESIGNER_INTRO_BODY_ID,
    DESIGNER_INTRO_TOGGLE_ID,
    DESIGNER_STEPPER_ID,
    POLL_MS,
    step1_content,
    step2_content,
    step3_content,
    step4_content,
    step5_content,
    step6_content,
    step7_content,
    designer_step_row,
    stepper_index,
)

if TYPE_CHECKING:
    from dash import NoUpdate

__all__ = [
    "_DEFAULT_EXPECTED_CHARS",
    "_DEV_MODE",
    "_MAX_DELIVERY_TICKS",
    "_MOCK_BUFFERS",
    "expected_stream_chars",
    "extract_html",
    "find_live_draw",
    "stream_progress",
    "persist_manifest",
    "_start_gen",
    "on_designer_auto_retry",
    "on_designer_carry_forward",
    "on_designer_fix_errors",
    "on_designer_intro_toggle",
    "on_designer_refine_image_delete",
    "on_designer_refine_upload",
    "on_designer_regenerate",
    "on_designer_retry",
    "on_designer_retry_model",
    "on_designer_start_over",
    "on_designer_step2_choice",
    "on_designer_step_back",
    "on_mock_stream_poll",
    "on_mock_stream_watchdog",
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
    # State, never Input. A buffer tick arrives twice a second for the length
    # of a draw; as an Input each one cost a server round trip carrying the
    # whole session, which is what pushed the poll's own round trip past its
    # period and froze the counter (see `on_mock_stream_poll`). Progress is
    # painted clientside (app.py), and a failed draw's error rides the store
    # (`_draw_error`), so nothing here needs a buffer change to fire on.
    State("mock-stream-buffer", "data"),
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
    content: Any
    if step == 1:
        content = step1_content()
    elif step == 2:  # noqa: PLR2004  # wizard step 2 (step2_content)
        content = step2_content(
            bool(store.get("_has_existing_ui", True)),
            bool(store.get("_is_revision", False)),
        )
    elif step == 3:  # noqa: PLR2004  # wizard step 3 (step3_content)
        content = step3_content()
    elif step == 4:  # noqa: PLR2004  # wizard step 4 (step4_content)
        support: bool | None = image_support
        content = step4_content(store, support)
    elif step == 5:  # noqa: PLR2004  # wizard step 5 (step5_content)
        # The error is the store's; the buffer's count and progress are the
        # values the clientside painter will overwrite on its next tick.
        content = step5_content(
            {**(buffer_data or {}), "error": store.get("_draw_error")},
            image_support,
        )
    elif step == 6:  # noqa: PLR2004  # wizard step 6 (step6_content)
        content = step6_content(store, session)
    elif step == 7:  # noqa: PLR2004  # wizard step 7 (step7_content)
        content = step7_content(store, image_support)
    else:
        content = step2_content(
            bool(store.get("_has_existing_ui", True)),
            bool(store.get("_is_revision", False)),
        )
    return content, designer_step_row(stepper_index(step))


@callback(
    Output(DESIGNER_INTRO_BODY_ID, "opened"),
    Input(DESIGNER_INTRO_TOGGLE_ID, "n_clicks"),
    State(DESIGNER_INTRO_BODY_ID, "opened"),
    prevent_initial_call=True,
)
def on_designer_intro_toggle(n: int | None, opened: bool) -> bool | NoUpdate:
    """Open or close "How to use Designer" (D-LR12).

    The state is the Collapse's own ``opened`` and never the session's: the
    notes are a reading aid, not a fact about the project or the round, and a
    rebuilt page reasonably starts with them closed. Nothing here reads or
    writes the session, so a click cannot rebuild the page it was made on.

    The flip itself is ``_shared.toggle_disclosure``, shared with the project
    view's introduction (D-LR13): two callbacks, one body.
    """
    return toggle_disclosure(n, opened)


@callback(
    Output("mock-stream-buffer", "data", allow_duplicate=True),
    Output("designer-session-store", "data", allow_duplicate=True),
    Output("mock-stream-interval", "disabled", allow_duplicate=True),
    Output("mock-stream-interval", "interval"),
    Input("mock-stream-interval", "n_intervals"),
    State("designer-session-store", "data"),
    prevent_initial_call=True,
)
def on_mock_stream_poll(_n: int | None, store: Any) -> Any:
    """Poll the mock generation thread and deliver completion in-band.

    On each tick this updates mock-stream-buffer with token/progress info.
    When the background thread finishes and stores the extracted HTML on
    buf_entry["final_html"], this same callback writes the completed mock
    straight into designer-session-store (step=6, mock_html=...) and disables
    the interval. The fourth output is the poll's own cadence: ``POLL_MS``
    while text streams, ``DELIVERY_MS`` from the finished mock to its ack.

    Three pieces of load-bearing weirdness — preserve all of them:

    1. **In-band delivery.**  Earlier this fanned out through a separate
       mock-done-store dcc.Store + on_mock_done callback.  That chain failed
       silently when the user attached a screenshot to a refine: the signal
       store updated but on_mock_done never fired.  Cause never fully nailed
       down; consolidating delivery into this callback bypasses it entirely.
       Don't reintroduce a chained completion callback.

    2. **The period must exceed the round trip.**  dash-renderer keeps the
       newer of two in-flight requests of the same callback and discards the
       older one's response when it arrives (`requestedCallbacks`, "give
       precedence to newer callbacks over older ones"; the `executing`
       observer drops a result whose callback is no longer watched).  So a
       response slower than the interval period never lands, nor does any
       after it while that holds.  The delivery response carries the whole
       mock, which at 250 ms never fit, and every re-delivery was superseded
       by the next tick: the server printed "mock delivered" over and over
       while the page stayed at step 5.  Hence the two cadences: the first
       tick that sees ``final_html`` sends a small response that slows the
       interval to ``DELIVERY_MS``, and only the ticks after it, now that far
       apart, carry the payload.  Don't deliver on the tick that slows down,
       and don't shorten ``DELIVERY_MS`` below what a 512 kB response plus
       the step-6 render it triggers take to apply.

    3. **Acknowledgement-based re-delivery.**  The poll request itself is
       the acknowledgement channel: its designer-session-store State is the
       value the browser has *applied* at dispatch time.  While that still
       reads step 5, the payload has not landed — keep the buffer alive and
       re-emit the identical step=6 / mock_html payload every tick.  Only a
       poll whose store has moved off step 5 proves delivery (or that the
       user already moved on), and only then is the buffer popped and the
       interval disabled and returned to ``POLL_MS``.  The ack writes nothing
       to the buffer.  A fixed-count window (formerly 6 ticks) counted
       requests *sent*, not deliveries *applied*; don't reintroduce one.  The
       only counter here is the ~2-minute runaway valve
       (_MAX_DELIVERY_TICKS).

    A failed draw's error is written to both outputs: the buffer for the
    retry snapshot and the buffer-shaped tests, the store (``_draw_error``)
    because that is what re-renders the step now that the buffer is its State.
    """
    gen_id: str | None = (store or {}).get("_gen_id")
    if not gen_id or gen_id not in _MOCK_BUFFERS:
        return no_update, no_update, True, POLL_MS

    buf_entry = _MOCK_BUFFERS[gen_id]
    accumulated = buf_entry["text"]

    if "__GENERATION_ERROR__:" in accumulated:
        idx = accumulated.index("__GENERATION_ERROR__:")
        error_msg = accumulated[idx + len("__GENERATION_ERROR__:") :].strip()
        error_msg = error_msg or "Generation failed — check the server log for details."
        _MOCK_BUFFERS.pop(gen_id, None)
        return _poll_failed(store or {}, error_msg)

    final_html: str | None = buf_entry.get("final_html")
    if final_html is not None:
        return _poll_deliver(gen_id, buf_entry, final_html, store or {})

    # Generator finished without a recognised sentinel — stop event fired mid-stream.
    if buf_entry.get("done"):
        _MOCK_BUFFERS.pop(gen_id, None)
        return no_update, no_update, True, POLL_MS

    return stream_progress(buf_entry), no_update, no_update, POLL_MS


def _poll_failed(s: dict[str, Any], error_msg: str) -> Any:
    """The poll's four outputs for a draw that failed: stop, and show the error."""
    return {"error": error_msg}, {**s, "_draw_error": error_msg}, True, POLL_MS


def _poll_deliver(
    gen_id: str, buf_entry: dict[str, Any], final_html: str, s: dict[str, Any]
) -> Any:
    """The poll's four outputs once the draw has a mock to deliver (notes 2–3)."""
    # Acknowledgement: this request's State is the store the browser has
    # actually applied.  Any step other than 5 means the completion payload
    # landed (or the user has already moved past the preview — e.g. clicked
    # Refine between ticks, which must not be bounced back to step 6).
    # Either way delivery is finished: drop the buffer and stop the interval.
    if s.get("step") != 5:  # noqa: PLR2004  # wizard step 5, the mock preview
        _MOCK_BUFFERS.pop(gen_id, None)
        if _DEV_MODE:
            print(
                f"[Designer] mock delivery acknowledged "
                f"(store step={s.get('step')}): gen_id={gen_id[:8]}",
                flush=True,
            )
        return no_update, no_update, True, POLL_MS

    # First sight of the finished mock: slow the poll down before sending
    # anything large. This response is small, so it lands within the running
    # period; the next tick, DELIVERY_MS later, is the first to deliver.
    if not buf_entry.get("slowed"):
        buf_entry["slowed"] = True
        return stream_progress(buf_entry), no_update, no_update, DELIVERY_MS

    # Unacknowledged — (re-)deliver the identical payload.
    delivered = buf_entry.get("delivered", 0) + 1
    buf_entry["delivered"] = delivered

    if delivered > _MAX_DELIVERY_TICKS:
        # ~2 minutes of re-delivery with no acknowledgement: the page is not
        # applying updates.  The generation thread already saved the mock to
        # disk before setting final_html, so nothing is lost — tell the user
        # how to get at it instead of spinning forever.
        _MOCK_BUFFERS.pop(gen_id, None)
        return _poll_failed(
            s,
            "The mock was generated and saved, but this page "
            "stopped receiving updates and could not display it. "
            "Refresh the page to load the saved mock, or click "
            "Retry to regenerate.",
        )

    # Spread the acknowledged store so flags like _capture_mode, _is_revision,
    # _stale_inputs and refine_text survive delivery (a from-scratch payload
    # here regressed D-DM8: Retry after a capture draw lost the mode and
    # regenerated greenfield). screenshots and refine_images stay empty —
    # their base64 payload must never re-enter the store (see the note in
    # _start_gen).
    new_store: Any = {
        **s,
        "step": 6,
        "mock_html": final_html,
        "screenshots": [],
        "refine_images": [],
        "finalized": False,
        # The document's static defects, for the preview's status line and
        # the fix draw; the browser adds the runtime ones.
        "_mock_errors": list(buf_entry.get("static_errors", [])),
    }
    if _DEV_MODE:
        print(
            f"[Designer] mock delivered (tick {delivered}, awaiting ack): "
            f"gen_id={gen_id[:8]} mock_html_len={len(final_html)}",
            flush=True,
        )
    final_buf = {"tokens": len(final_html), "progress": 100, "error": None}
    # DELIVERY_MS again rather than no_update: a page rebuilt between the
    # slow-down tick and this one mounts its interval at POLL_MS, and the
    # watchdog re-arms it there. Re-sending an unchanged value costs nothing
    # (dcc.Interval resets its timer only when the value differs).
    return final_buf, new_store, no_update, DELIVERY_MS


# Watchdog cadence: the layout mounts it at `WATCHDOG_FIRST_MS` so a rebuilt
# page re-arms its poll within half a second, and the first tick slows it to
# one cheap request every five seconds for as long as the page is open.
WATCHDOG_MS = 5000


@callback(
    Output("designer-session-store", "data", allow_duplicate=True),
    Output("mock-stream-buffer", "data", allow_duplicate=True),
    Output("mock-stream-interval", "disabled", allow_duplicate=True),
    Output("mock-stream-watchdog", "interval"),
    Input("mock-stream-watchdog", "n_intervals"),
    State("designer-session-store", "data"),
    State("mock-stream-interval", "disabled"),
    State("session", "data"),
    prevent_initial_call=True,
)
def on_mock_stream_watchdog(
    _n: int | None, store: Any, poll_disabled: Any, session: Any
) -> Any:
    """Re-arm the poll when a draw is alive and nothing is polling it.

    There is no connection to keep alive: every poll tick is its own request.
    What loses a draw is the page being rebuilt around it. ``render_page``
    recreates ``designer-session-store`` and ``mock-stream-interval`` on every
    ``session`` write and every browser load (a reload, a tab the browser
    discarded during a long wait), and the rebuilt store has no ``_gen_id``
    while the rebuilt interval is disabled -- the thread keeps drawing and
    saves the mock, but no component on the page ever hears about it. The
    retry after a model change does this to itself: it writes ``session`` in
    the response that starts the draw. This tick is the recovery. It also
    covers the one browser-side failure the poll's docstring records, a
    response whose ``disabled`` output never lands.

    It acts only when the poll is off and ``find_live_draw`` finds a buffer for
    this store or this round: it turns the poll back on, and if the store does
    not already name that draw at the preview step it writes the store the
    draw's start would have written (``_start_gen``'s shape, screenshots and
    refine images empty for the same reason) and the buffer's current count so
    the re-rendered step shows it at once. The poll's own ack and delivery
    logic then finishes the job on its next tick. Never writes ``session``:
    that would rebuild the page again.
    """
    interval = WATCHDOG_MS
    if not poll_disabled:
        return no_update, no_update, no_update, interval
    s = store or {}
    sess = session or {}
    live = find_live_draw(s, _mock_design_dir(sess.get("working_dir"), sess))
    if live is None:
        return no_update, no_update, no_update, interval
    gen_id, entry = live
    # PLR2004: wizard step 5, the mock preview.
    if s.get("_gen_id") == gen_id and s.get("step") == 5:  # noqa: PLR2004
        return no_update, no_update, False, interval
    rearmed: dict[str, Any] = {
        **s,
        "step": 5,
        "_gen_id": gen_id,
        "mock_html": "",
        "screenshots": [],
        "refine_images": [],
        "finalized": False,
        "_draw_error": None,
        "_mock_errors": [],
    }
    return rearmed, stream_progress(entry), False, interval
