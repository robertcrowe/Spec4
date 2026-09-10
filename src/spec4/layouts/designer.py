from __future__ import annotations

import pathlib
from typing import Any

from dash import dcc, html
import dash_mantine_components as dmc

from spec4 import project_manager
from spec4.app_constants import PROJECT_MODE_NEW
from spec4.layouts import _llm_gate
from spec4.layouts._round_cost import run_cost_strip
from spec4.layouts._shared import (
    PROGRESS_CLASS_NAMES,
    STEP_ACTIVE,
    STEP_DONE,
    STEP_UNREACHABLE,
    StepEntry,
    step_row,
)
from spec4.agents.designer import (
    detect_has_ui_source,
    detect_no_ui,
    load_session,
    revision_delta,
)

_PLACEHOLDER_HTML = (
    "<!DOCTYPE html><html><head><meta charset='utf-8'>"
    "<title>Mock Preview</title><style>"
    "body{margin:0;background:#1a1a24;color:#f5f5f7;"
    "font-family:Inter,sans-serif;display:flex;"
    "align-items:center;justify-content:center;height:100vh}"
    ".card{background:#2a2a3a;border-radius:12px;"
    "padding:2rem;text-align:center}"
    "h1{color:#f5f5f7;margin-bottom:.5rem}</style></head>"
    "<body><div class='card'><h1>Mock Preview</h1>"
    "<p>Your mock will appear here after generation.</p>"
    "</div></body></html>"
)


# The six positions the wizard reports, in order. Seven steps, six labels:
# refining (step 7) is the preview step seen with changes not yet drawn, so it
# reuses Preview's label rather than adding a position the developer can never
# be "before".
DESIGNER_STEPS: tuple[str, ...] = (
    "No-UI check",
    "Start / Resume",
    "Preferences",
    "Screenshots",
    "Generate",
    "Preview",
)

# The classes `v3.css` draws the row with — the same rule the setup wizard's
# row takes, restated at this wizard's names. Named here because
# `_shared.step_row` is handed them and this screen's tests assert on them.
DESIGNER_STEP_CLASS = "designer-step"
DESIGNER_STEPS_CLASS = "designer-steps"

# The container the row is rendered into, and the id `render_designer_step`
# writes to. It was a `dmc.Stepper` whose `active` the callback set; the plain
# text row has no such property, so the callback re-renders the row into this
# container instead (its Output moved with it, in the same change).
DESIGNER_STEPPER_ID = "designer-stepper"

# The two facts the preview used to frame. Both are one dimmed line now: a box
# around a sentence that is neither a warning nor an error is chrome, and the
# yellow disclaimer was the loudest thing on the screen it was disclaiming.
MOCK_DISCLAIMER = "Look-and-feel reference only; not the final UI."
MOCK_APPROVED = "Mock approved and saved."


def _dim(text: str, **kwargs: Any) -> Any:
    """One dimmed line: an instruction, or a fact — never an alert.

    The setup wizard's ``_dim`` says the same thing on its own screen. What
    the two share is the ``dim-line`` class, which is where the styling
    actually lives, so a reworded register moves both.
    """
    return dmc.Text(text, className="dim-line", **kwargs)


def stepper_index(step: int) -> int:
    """Which of the six labels a wizard step (1-7) stands at.

    Steps 6 and 7 both stand at Preview. Clamped rather than trusted: the
    store is memory-resident state a stale page can hand back out of range,
    and an index off the end would raise inside the row builder.
    """
    return max(0, min(step - 1, len(DESIGNER_STEPS) - 1))


def designer_step_row(active: int) -> html.Div:
    """The wizard's position row, marked by the shared renderer (D-LR9).

    ``active`` indexes :data:`DESIGNER_STEPS`. Steps behind it are done and
    read at full weight; steps ahead cannot be entered yet, so they are dimmed
    and disabled and carry the reason as their tooltip — the same marking the
    chat frame's pipeline row and the setup wizard's indicator wear, from the
    same function, because the active mark is the accent and a re-themed
    accent has to move all three at once.

    No entry carries an id: the row reports where the developer is, and every
    move through the wizard is made by the controls under it.
    """
    entries: list[StepEntry] = []
    for index, label in enumerate(DESIGNER_STEPS):
        if index == active:
            entries.append(StepEntry(label, STEP_ACTIVE))
        elif index < active:
            entries.append(StepEntry(label, STEP_DONE))
        else:
            entries.append(
                StepEntry(
                    label,
                    STEP_UNREACHABLE,
                    tooltip=f"Finish {DESIGNER_STEPS[active]} first",
                )
            )
    return step_row(
        entries, base_class=DESIGNER_STEP_CLASS, row_class=DESIGNER_STEPS_CLASS
    )


def _design_dir(working_dir: str | None, version: int) -> pathlib.Path:
    return pathlib.Path(working_dir or ".") / ".spec4" / f"v{version}" / "design"


def _default_designer_session(step: int = 2) -> dict[str, Any]:
    return {
        "step": step,
        "preference_text": "",
        "screenshots": [],
        "mock_html": _PLACEHOLDER_HTML,
        "finalized": False,
    }


# Every step's controls sit in one of these: the step's own action filled, and
# everything beside it a neutral outline. Neutral is a bare `variant="outline"`
# with no `color` — per D-AR1 that takes the theme primary and washes to
# near-white in this dark scheme, which is the mock's `.btn-outline` — so the
# one green thing in the row is reached by omitting `variant` entirely and no
# button here names a colour that is not a semantic (D-LR2).
def _button_row(*buttons: Any, **kwargs: Any) -> Any:
    return dmc.Group(list(buttons), gap="xs", className="btn-row", **kwargs)


def _primary(label: str, button_id: str) -> Any:
    """The one filled action a step carries."""
    return dmc.Button(label, id=button_id, size="compact-sm")


def _neutral(label: str, button_id: str, **kwargs: Any) -> Any:
    return dmc.Button(
        label, id=button_id, variant="outline", size="compact-sm", **kwargs
    )


def _warn(label: str, button_id: str, **kwargs: Any) -> Any:
    """A neutral outline in the warn tone, for the destructive choice.

    The tone comes from `.btn-warn` in the stylesheet — the app's one warn,
    already worn by the agent rows' Needs Update and the chat frame's Re-scan —
    never from a `color` prop, so a re-themed warn moves it (D-LR2).
    """
    return _neutral(label, button_id, className="btn-warn", **kwargs)


def _step_back() -> Any:
    """Back, within the wizard: one step, never out of Designer.

    One id for both steps that render it — only one step is ever on screen —
    and the callback simply decrements. The button that *left* the wizard for
    the project view is gone; the status bar's Project link is that route.
    """
    return _neutral("Back", "btn-designer-step-back")


def _step1_content() -> Any:
    return dmc.Stack(
        [
            _dim(
                "No user interface detected — this looks like a CLI, terminal "
                "or headless project."
            ),
            _button_row(
                _primary("Add a GUI", "btn-designer-add-gui"),
                _neutral("Skip Designer", "btn-designer-skip-1"),
            ),
        ],
        gap="xs",
    )


def _step2_content(has_existing_ui: bool = True, is_revision: bool = False) -> Any:
    if is_revision:
        prompt = "Carry this project's design forward and update it, or start over?"
    elif has_existing_ui:
        prompt = "Modify the existing look and feel, or create a brand-new design?"
    else:
        prompt = "Create a brand-new design for your application?"

    # The slot the two flows disagree about: a revision round opens with
    # carry-forward, every other round with the option to capture the look and
    # feel already in the project.
    first: Any
    if is_revision:
        first = _primary("Carry design forward & update", "btn-designer-carry-forward")
    else:
        first = _neutral(
            "Modify existing look and feel",
            "btn-designer-modify-existing",
            style={"display": "none"} if not has_existing_ui else {},
        )
    controls: list[Any] = [first]
    if is_revision:
        # `on_designer_step2_choice` takes both this button and
        # btn-designer-create-new as Inputs, and Dash refuses to dispatch a
        # callback unless every Input is on screen. The revision branch shows
        # carry-forward in this slot instead, so without a hidden stand-in here
        # clicking "Create new design" on a revision round throws
        # ("A nonexistent object was used in an Input") and does nothing. Same
        # mounted-but-hidden trick the no-existing-UI case above uses.
        controls.append(
            _neutral(
                "Modify existing look and feel",
                "btn-designer-modify-existing",
                style={"display": "none"},
            )
        )
    # The filled action is whichever choice this branch is really offering: a
    # revision round is here to carry its design forward, every other round to
    # draw one. The other choice stays available beside it, as an outline.
    controls.append(
        _neutral("Create new design", "btn-designer-create-new")
        if is_revision
        else _primary("Create new design", "btn-designer-create-new")
    )
    controls.append(_neutral("Skip Designer", "btn-designer-skip-2"))
    return dmc.Stack([_dim(prompt), _button_row(*controls)], gap="xs")


def _step3_content() -> Any:
    return dmc.Stack(
        [
            _dim(
                "Describe the visual direction; the vision and feature specs "
                "are already in context."
            ),
            dmc.Textarea(
                id="designer-preference-input",
                placeholder=(
                    "e.g. dark, dense, one accent colour, no gradients, "
                    "1px rules instead of cards"
                ),
                minRows=4,
                autosize=True,
            ),
            _button_row(
                _step_back(),
                _primary("Next", "btn-designer-preferences-next"),
            ),
        ],
        gap="xs",
    )


def _screenshot_card(idx: int, shot: dict[str, str]) -> Any:
    """One uploaded screenshot: the image, its note, and Remove.

    A bordered row rather than a card — no fill, no radius, no hover — and
    Remove is a neutral outline like every other secondary control in the
    wizard. What it removes is a file the developer just added and can add
    again, so it is not the row's warn.
    """
    return dmc.Paper(
        [
            dmc.Group(
                [
                    html.Img(
                        src=shot["data"],
                        style={"maxHeight": "120px", "maxWidth": "100%"},
                    ),
                    dmc.Button(
                        "Remove",
                        id={"type": "designer-screenshot-delete", "index": idx},
                        variant="outline",
                        size="compact-sm",
                    ),
                ],
                justify="space-between",
                align="flex-start",
            ),
            dmc.Textarea(
                id={"type": "designer-screenshot-annotation", "index": idx},
                placeholder="What to take from this image, or avoid",
                value=shot.get("annotation", ""),
                minRows=2,
                autosize=True,
                mt="xs",
            ),
        ],
        withBorder=True,
        p="xs",
        radius=0,
    )


def _step4_content(
    store: dict[str, Any],
    image_support: bool | None,
) -> Any:
    screenshots: list[dict[str, str]] = store.get("screenshots", [])
    children: list[Any] = [
        _dim("Add reference images for style guidance, or generate without them.")
    ]

    if image_support is False:
        children.append(
            _dim(
                "The selected model takes no image input, so upload is off — "
                "your description still stands."
            )
        )
    else:
        children.append(
            dcc.Upload(
                id="designer-screenshot-upload",
                accept="image/*",
                multiple=False,
                children=_dim("Drag and drop a screenshot, or click to upload"),
                className="designer-upload-zone",
            )
        )

    if len(screenshots) > 5:
        children.append(
            _dim(
                "More than 5 screenshots — too many examples can produce "
                "conflicting guidance."
            )
        )

    for idx, shot in enumerate(screenshots):
        children.append(_screenshot_card(idx, shot))

    children.append(
        _button_row(
            _step_back(),
            _primary("Generate", "btn-designer-generate-mock"),
        )
    )
    return dmc.Stack(children, gap="xs")


def _step5_content(
    buffer_data: dict[str, Any] | None = None,
    image_support: bool | None = None,
) -> Any:
    bd = buffer_data or {}
    error: str | None = bd.get("error")
    tokens: int = bd.get("tokens", 0)
    progress_val: int = bd.get("progress", 0)
    children: list[Any] = [
        # A failed draw is the one thing on this screen that is genuinely an
        # alert, and it is the retry panel's frame — it stays. The line above
        # a running draw was never a warning, so it is a line.
        dmc.Alert(error, color="red", variant="light", title="Generation Error")
        if error
        else _dim("Generating the mock — this can take several minutes."),
        dmc.Progress(
            value=progress_val,
            id="mock-progress",
            animated=not error,
            striped=True,
            classNames=PROGRESS_CLASS_NAMES,
            **({"color": "red"} if error else {}),
        ),
        dmc.Text(
            f"Chars received: {tokens}",
            id="mock-token-count",
            c="dimmed",
            size="sm",
        ),
    ]
    if image_support is False:
        # Same notice step 4 gives, on the screen the developer is actually
        # watching: a draw handed a different model mid-flight never passes
        # back through step 4 to be told there.
        children.insert(
            0,
            _dim(
                "The selected model takes no image input, so screenshot "
                "examples are not going with this draw."
            ),
        )
    if error:
        # Retrying the same model is the right move for an overload and useless
        # for an unreachable provider or a rejected key, so the failure offers
        # both doors. Picking a model does not draw by itself — it comes back
        # here, and Retry runs the same draw on the new model.
        children.append(
            _button_row(
                _neutral("Retry", "btn-designer-retry"),
                _neutral("Try a different provider/model", "btn-designer-retry-model"),
            )
        )
    return dmc.Stack(children, gap="xs")


def _fullscreen_row() -> Any:
    """Full Screen control for a mock preview.

    Shared by the preview (step 6) and refine (step 7) views. Both render a
    ``mock-iframe`` at 600px, and both need the escape hatch — a brownfield
    revision round enters at step 7 by way of carry-forward, so the refine view
    is the first (and until the regenerate finishes, only) place the developer
    sees the carried mock. Only one step renders at a time, so the shared button
    id is unambiguous; the clientside handler reads ``mock_html`` from the
    designer store, which both steps populate.
    """
    return dmc.Group(
        [
            dmc.Button(
                "Full Screen",
                id="mock-fullscreen-btn",
                variant="outline",
                size="sm",
            ),
        ],
        justify="flex-end",
    )


def _stale_banner(stale: list[str]) -> Any:
    """Banner shown above the mock preview when the vision is newer than the mock."""
    parts = (
        "the project " + ", the project ".join(stale)
        if len(stale) > 1
        else f"the project {stale[0]}"
    )
    # Still an alert: this one is a warning, and the developer is about to
    # approve a mock that no longer matches its inputs. Its action is a warn
    # outline rather than a second filled button — regenerating discards the
    # mock on screen, which is Start Over's kind of decision, and the step's
    # one primary is Approve.
    return dmc.Alert(
        [
            dmc.Text(
                f"The mock is out of date: {parts} has been updated since it "
                "was generated. Regenerating will discard this mock and create "
                "an entirely new one from the current vision and AI features.",
                mb="sm",
            ),
            _warn("Regenerate mock", "btn-designer-revise-stale"),
        ],
        title="Upstream changes detected",
        color="yellow",
        variant="light",
    )


def _step6_content(store: dict[str, Any], session: dict[str, Any] | None = None) -> Any:
    stale_inputs: list[str] = store.get("_stale_inputs") or []
    children: list[Any] = []
    if stale_inputs:
        children.append(_stale_banner(stale_inputs))
    children.extend(
        [
            _fullscreen_row(),
            _dim(MOCK_DISCLAIMER),
            html.Iframe(
                id="mock-iframe",
                srcDoc=store.get("mock_html", ""),
                sandbox="allow-scripts",
                style={
                    "width": "100%",
                    "height": "600px",
                    "border": "none",
                    "borderRadius": "8px",
                },
            ),
        ]
    )
    # The Designer run ends here — every draw and refine lands on this
    # preview, and the generation thread has flushed its usage by the time
    # the poll delivers it. The same three-line strip the chat agents show
    # under their last message and the project view closes with; omitted when
    # the caller has no session (no project dir).
    cost_strip = run_cost_strip((session or {}).get("working_dir"), session, "designer")
    if cost_strip is not None:
        children.append(cost_strip)
    if store.get("finalized"):
        children.append(_dim(MOCK_APPROVED))
        children.append(
            _button_row(
                _primary("Continue to Stack Advisor", "btn-designer-continue-stack"),
                _neutral("Refine", "btn-designer-refine"),
                _warn("Start Over", "btn-designer-start-over"),
            )
        )
    else:
        children.append(
            _button_row(
                _primary("Approve", "btn-designer-approve"),
                _neutral("Refine", "btn-designer-refine"),
                _warn("Start Over", "btn-designer-start-over"),
            )
        )
    return dmc.Stack(children, gap="xs")


def _refine_image_row(idx: int, img: dict[str, str]) -> Any:
    return dmc.Paper(
        [
            dmc.Group(
                [
                    dmc.Text(
                        img.get("filename", ""),
                        size="sm",
                        style={"flex": 1},
                        truncate="end",
                    ),
                    dmc.Button(
                        "Remove",
                        id={"type": "designer-refine-image-delete", "index": idx},
                        variant="outline",
                        size="compact-sm",
                    ),
                ],
                justify="space-between",
                wrap="nowrap",
            ),
            dmc.Textarea(
                id={"type": "designer-refine-annotation", "index": idx},
                placeholder="What to take from this image, or avoid",
                value=img.get("annotation", ""),
                minRows=2,
                autosize=True,
                mt="xs",
            ),
        ],
        withBorder=True,
        p="xs",
        radius=0,
    )


def _step7_content(store: dict[str, Any], image_support: bool | None = None) -> Any:
    refine_images: list[dict[str, str]] = store.get("refine_images", [])
    children: list[Any] = [
        _fullscreen_row(),
        _dim(MOCK_DISCLAIMER),
        html.Iframe(
            id="mock-iframe",
            srcDoc=store.get("mock_html", ""),
            sandbox="allow-scripts",
            style={
                "width": "100%",
                "height": "600px",
                "border": "none",
                "borderRadius": "8px",
            },
        ),
        _dim("Describe the changes you'd like."),
        dmc.Textarea(
            id="designer-refine-input",
            placeholder=("e.g. a larger opening block, a warmer palette, tighter rows"),
            minRows=3,
            autosize=True,
            value=store.get("refine_text", ""),
        ),
    ]
    if image_support is not False:
        children.append(
            dcc.Upload(
                id="designer-refine-upload",
                accept="image/*",
                multiple=True,
                children=_dim("Drag and drop a reference image, or click to upload"),
                className="designer-upload-zone",
            )
        )
    else:
        children.append(
            html.Div(id="designer-refine-upload", style={"display": "none"})
        )
    if refine_images:
        children.append(
            dmc.Stack(
                [_refine_image_row(i, img) for i, img in enumerate(refine_images)],
                gap="xs",
            )
        )
    children.append(
        _button_row(
            _neutral("Cancel", "btn-designer-refine-cancel"),
            _primary("Regenerate", "btn-designer-regenerate"),
        )
    )
    return dmc.Stack(children, gap="xs")


def designer_layout(
    session: dict[str, Any] | None = None, prefs: dict[str, Any] | None = None
) -> Any:
    session = session or {}
    # Designer has no chat turn, so its gate stands in front of the whole
    # wizard rather than in front of an opening message. Rendering it instead
    # of the wizard also keeps the wizard's stores from initialising against a
    # model the developer has not chosen yet; answering re-renders the page,
    # since `render_page` is driven by the session store.
    if (
        _llm_gate.is_open(session, "designer")
        or (session.get("agent_llm_draft") or {}).get("agent") == "designer"
    ):
        # No heading above it. The gate's own first line reads "Model for
        # Designer: …", so a title saying "Designer" over it named the agent
        # twice on a screen whose whole content is one panel — and the status
        # bar names the model this route is about as well.
        return html.Div(_llm_gate.gate_card(session, prefs, "designer"))
    working_dir: str | None = session.get("working_dir")
    vision: dict[str, Any] = session.get("vision_statement") or {}
    code_review: dict[str, Any] = session.get("code_review") or {}
    # Without a project there is no round on disk to look up; the version only
    # names a path, and every read of ``design_dir`` below guards on
    # ``working_dir``.
    version = project_manager.active_version(working_dir, session) if working_dir else 0
    design_dir = _design_dir(working_dir, version)
    saved = load_session(design_dir) if working_dir else None
    # D-PM1: "Modify existing" only makes sense for a project the developer has
    # said is theirs. When they told us this is a new project, UI files in the
    # directory are scaffolding, and offering to reproduce their look and feel
    # would capture a starter template as the design baseline. A mock already
    # saved under .spec4/ is Spec4's own output and still counts either way.
    if session.get("project_mode") == PROJECT_MODE_NEW:
        has_existing_ui = bool(working_dir and (design_dir / "mock.html").exists())
    else:
        has_existing_ui = (
            detect_has_ui_source(pathlib.Path(working_dir), design_dir)
            if working_dir
            else False
        )
    # Revision round: a prior *implemented* round left an approved mock to carry
    # forward, and the vision carries this round's delta. When both hold, step 2
    # offers carry-forward-and-update as the default. The prior mock itself is
    # loaded lazily in the carry-forward callback, not here (keeps the store lean).
    is_revision = bool(
        working_dir
        and project_manager.load_prior_mock(working_dir) is not None
        and revision_delta(vision) is not None
    )

    if saved and saved["mock_html"]:
        initial_step = 6
        initial_store: dict[str, Any] = {
            "step": 6,
            "preference_text": saved["preference_text"],
            "screenshots": saved["screenshots"],
            "mock_html": saved["mock_html"],
            "finalized": saved["finalized"],
        }
        if working_dir:
            stale = project_manager.detect_stale_inputs(working_dir, "designer")
            ack: dict[str, float] = session.get("designer_stale_acknowledged") or {}
            unacknowledged = [
                name for name, mtime in stale.items() if ack.get(name) != mtime
            ]
            if unacknowledged:
                initial_store["_stale_inputs"] = unacknowledged
    elif detect_no_ui(vision, code_review):
        initial_step = 1
        initial_store = _default_designer_session(step=1)
    else:
        initial_step = 2
        initial_store = _default_designer_session(step=2)
        if saved:
            initial_store = {
                **initial_store,
                "preference_text": saved["preference_text"],
                "screenshots": saved["screenshots"],
            }

    initial_store["_has_existing_ui"] = has_existing_ui
    initial_store["_is_revision"] = is_revision

    # A draw that failed and then sent the developer to the model picker: the
    # picker writes `session`, which rebuilds this page and re-creates the two
    # memory stores below from scratch, and a failed draw has saved nothing to
    # disk to rebuild from. The snapshot `on_designer_retry_model` left behind
    # is what brings the error panel — and the developer's own inputs — back.
    # Only the fields the retry needs to reproduce the draw are carried.
    failed = session.get("_designer_failed_draw") or {}
    buffer_data: dict[str, Any] = {"tokens": 0, "progress": 0, "error": None}
    if failed.get("error"):
        initial_step = 5
        initial_store = {
            **initial_store,
            "step": 5,
            "preference_text": failed.get("preference_text", ""),
            "screenshots": failed.get("screenshots", []),
            "mock_html": "",
            "finalized": False,
            "_capture_mode": bool(failed.get("_capture_mode")),
            "_has_existing_html": bool(failed.get("_has_existing_html")),
        }
        buffer_data = {"tokens": 0, "progress": 0, "error": failed["error"]}

    return html.Div(
        [
            dcc.Store(
                id="designer-session-store",
                storage_type="memory",
                data=initial_store,
            ),
            dcc.Store(
                id="mock-stream-buffer",
                storage_type="memory",
                data=buffer_data,
            ),
            # Fires once when a failed draw has just been given a different
            # model, re-running it without asking for another click. Disabled
            # otherwise. `on_gate_continue` cannot start the draw itself — the
            # gate replaces this wizard, so these stores are not mounted while
            # the picker is open — which is why the trigger lives here, the way
            # `chat_layout` fires an agent's opening turn.
            dcc.Interval(
                id="designer-autoretry-interval",
                interval=300,
                max_intervals=1 if failed.get("auto_retry") else 0,
            ),
            dcc.Interval(
                id="mock-stream-interval",
                interval=250,
                disabled=True,
            ),
            # No title, no introduction, no usage accordion. The step row says
            # where the developer is, the step's own instruction line says what
            # it wants, and the status bar names the route and the model — the
            # paragraph that introduced the Designer said none of that twice
            # over, and the accordion explained a wizard while standing in
            # front of it. The route back is the status bar's Project link,
            # which is mounted on every screen, so this one carries no Back of
            # its own out of the wizard.
            html.Div(
                designer_step_row(stepper_index(initial_step)),
                id=DESIGNER_STEPPER_ID,
            ),
            html.Div(id="designer-step-content"),
        ]
    )
