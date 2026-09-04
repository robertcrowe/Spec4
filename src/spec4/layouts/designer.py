from __future__ import annotations

import pathlib
from typing import Any

from dash import dcc, html
import dash_mantine_components as dmc

from spec4 import project_manager
from spec4.app_constants import PROJECT_MODE_NEW
from spec4.layouts import _llm_gate
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
    "h1{color:#42a5f5;margin-bottom:.5rem}</style></head>"
    "<body><div class='card'><h1>Mock Preview</h1>"
    "<p>Your mock will appear here after generation.</p>"
    "</div></body></html>"
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


def _step1_content() -> Any:
    return dmc.Stack(
        [
            dmc.Alert(
                "This project does not appear to have a graphical user interface "
                "(CLI / terminal / headless). Would you like to add a GUI?",
                color="blue",
                variant="light",
                title="No UI Detected",
            ),
            dmc.Group(
                [
                    dmc.Button("Add a GUI →", id="btn-designer-add-gui"),
                    dmc.Button(
                        "Skip Designer",
                        id="btn-designer-skip-1",
                        variant="outline",
                        color="gray",
                    ),
                ]
            ),
        ],
        gap="sm",
    )


def _step2_content(has_existing_ui: bool = True, is_revision: bool = False) -> Any:
    if is_revision:
        prompt = (
            "This revision updates your project. Carry your existing design "
            "forward and update it for these changes, or start over with a "
            "brand-new design?"
        )
    elif has_existing_ui:
        prompt = (
            "Would you like to modify an existing look and feel, "
            "or create a brand-new design?"
        )
    else:
        prompt = "Would you like to create a brand-new design for your application?"

    primary: Any
    if is_revision:
        primary = dmc.Button(
            "Carry design forward & update",
            id="btn-designer-carry-forward",
        )
    else:
        primary = dmc.Button(
            "Modify existing look and feel",
            id="btn-designer-modify-existing",
            variant="outline",
            style={"display": "none"} if not has_existing_ui else {},
        )
    create_kwargs: dict[str, Any] = {"variant": "outline"} if is_revision else {}
    controls: list[Any] = [primary]
    if is_revision:
        # `on_designer_step2_choice` takes both this button and
        # btn-designer-create-new as Inputs, and Dash refuses to dispatch a
        # callback unless every Input is on screen. The revision branch shows
        # carry-forward in this slot instead, so without a hidden stand-in here
        # clicking "Create new design" on a revision round throws
        # ("A nonexistent object was used in an Input") and does nothing. Same
        # mounted-but-hidden trick the no-existing-UI case above uses.
        controls.append(
            dmc.Button(
                "Modify existing look and feel",
                id="btn-designer-modify-existing",
                variant="outline",
                style={"display": "none"},
            )
        )
    controls.append(
        dmc.Button(
            "Create new design",
            id="btn-designer-create-new",
            **create_kwargs,
        )
    )
    controls.append(
        dmc.Button(
            "Skip Designer",
            id="btn-designer-skip-2",
            variant="outline",
            color="gray",
        )
    )
    return dmc.Stack(
        [
            dmc.Text(prompt, c="dimmed"),
            dmc.Group(controls),
        ],
        gap="sm",
    )


def _step3_content() -> Any:
    return dmc.Stack(
        [
            dmc.Textarea(
                id="designer-preference-input",
                label="Describe the look and feel you have in mind",
                placeholder=(
                    "e.g. Modern dark theme with a clean minimal layout, "
                    "blueprint-style grid background..."
                ),
                minRows=4,
                autosize=True,
            ),
            dmc.Button("Next →", id="btn-designer-preferences-next"),
        ],
        gap="sm",
    )


def _screenshot_card(idx: int, shot: dict[str, str]) -> Any:
    return dmc.Paper(
        [
            dmc.Group(
                [
                    html.Img(
                        src=shot["data"],
                        style={
                            "maxHeight": "120px",
                            "maxWidth": "100%",
                            "borderRadius": "4px",
                        },
                    ),
                    dmc.ActionIcon(
                        "✕",
                        id={"type": "designer-screenshot-delete", "index": idx},
                        color="red",
                        variant="subtle",
                        size="sm",
                    ),
                ],
                justify="space-between",
                align="flex-start",
            ),
            dmc.Textarea(
                id={"type": "designer-screenshot-annotation", "index": idx},
                label="What do you like or dislike about this?",
                value=shot.get("annotation", ""),
                minRows=2,
                autosize=True,
                mt="xs",
            ),
        ],
        withBorder=True,
        p="sm",
        mb="xs",
        radius="sm",
    )


def _step4_content(
    store: dict[str, Any],
    image_support: bool | None,
) -> Any:
    screenshots: list[dict[str, str]] = store.get("screenshots", [])
    children: list[Any] = []

    if image_support is False:
        children.append(
            dmc.Alert(
                "The selected model does not support image input — screenshot "
                "upload is disabled. You can still proceed using your text "
                "description.",
                color="orange",
                variant="light",
            )
        )
    else:
        children.append(
            dcc.Upload(
                id="designer-screenshot-upload",
                accept="image/*",
                multiple=False,
                children=dmc.Stack(
                    [
                        dmc.Text(
                            "Drag & drop a screenshot, or click to upload",
                            ta="center",
                            c="dimmed",
                        ),
                        dmc.Text(
                            "(Optional — add reference images for style guidance)",
                            size="xs",
                            ta="center",
                            c="dimmed",
                        ),
                    ],
                    gap="xs",
                    align="center",
                    py="md",
                ),
                className="designer-upload-zone",
            )
        )

    if len(screenshots) > 5:
        children.append(
            dmc.Alert(
                "You have supplied more than 5 screenshots — too many examples "
                "may produce conflicting guidance.",
                color="yellow",
                variant="light",
            )
        )

    for idx, shot in enumerate(screenshots):
        children.append(_screenshot_card(idx, shot))

    children.append(dmc.Button("Generate Mock →", id="btn-designer-generate-mock"))
    return dmc.Stack(children, gap="sm")


def _step5_content(
    buffer_data: dict[str, Any] | None = None,
    image_support: bool | None = None,
) -> Any:
    bd = buffer_data or {}
    error: str | None = bd.get("error")
    tokens: int = bd.get("tokens", 0)
    progress_val: int = bd.get("progress", 0)
    children: list[Any] = [
        dmc.Alert(error, color="red", variant="light", title="Generation Error")
        if error
        else dmc.Alert(
            "Generating your mock — this may take several minutes. "
            "If you think it may have finished but did not display "
            "your mock, try refreshing the page.",
            color="blue",
            variant="light",
        ),
        dmc.Progress(
            value=progress_val,
            id="mock-progress",
            animated=not error,
            striped=True,
            color="red" if error else "blue",
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
            dmc.Alert(
                "The selected model does not support image input — screenshot "
                "examples are not being sent with this draw.",
                color="orange",
                variant="light",
            ),
        )
    if error:
        # Retrying the same model is the right move for an overload and useless
        # for an unreachable provider or a rejected key, so the failure offers
        # both doors. Picking a model does not draw by itself — it comes back
        # here, and Retry runs the same draw on the new model.
        children.append(
            dmc.Group(
                [
                    dmc.Button(
                        "↺ Retry", id="btn-designer-retry", variant="outline"
                    ),
                    dmc.Button(
                        "↺ Try a different provider/model",
                        id="btn-designer-retry-model",
                        variant="outline",
                    ),
                ],
                gap="sm",
            )
        )
    return dmc.Stack(children, gap="sm")


_MOCK_DISCLAIMER = dmc.Alert(
    "This mock-up illustrates the intended look and feel only. "
    "It is not intended to represent or match the final application UI.",
    title="Design Mock-up — Look & Feel Reference Only",
    color="yellow",
    variant="filled",
    styles={"title": {"color": "#212121"}, "message": {"color": "#212121"}},
)


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
                "⛶ Full Screen",
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
    return dmc.Alert(
        [
            dmc.Text(
                f"The mock is out of date: {parts} has been updated since it "
                "was generated. Regenerating will discard this mock and create "
                "an entirely new one from the current vision and AI features.",
                mb="sm",
            ),
            dmc.Button(
                "Regenerate mock",
                id="btn-designer-revise-stale",
                color="blue",
                size="sm",
            ),
        ],
        title="Upstream changes detected",
        color="yellow",
        variant="light",
    )


def _step6_content(store: dict[str, Any]) -> Any:
    stale_inputs: list[str] = store.get("_stale_inputs") or []
    children: list[Any] = []
    if stale_inputs:
        children.append(_stale_banner(stale_inputs))
    children.extend(
        [
            _fullscreen_row(),
            _MOCK_DISCLAIMER,
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
    if store.get("finalized"):
        children.append(
            dmc.Alert(
                "Mock approved and saved. You can now continue to Stack Advisor.",
                color="green",
                variant="light",
            )
        )
        children.append(
            dmc.Group(
                [
                    dmc.Button(
                        "Continue to Stack Advisor →",
                        id="btn-designer-continue-stack",
                        color="green",
                    ),
                    dmc.Button(
                        "✏ Refine",
                        id="btn-designer-refine",
                        color="blue",
                        variant="outline",
                    ),
                    dmc.Button(
                        "↺ Start Over",
                        id="btn-designer-start-over",
                        variant="outline",
                        color="red",
                    ),
                ],
                gap="sm",
            )
        )
    else:
        children.append(
            dmc.Group(
                [
                    dmc.Button(
                        "✓ Approve",
                        id="btn-designer-approve",
                        color="green",
                    ),
                    dmc.Button(
                        "✏ Refine",
                        id="btn-designer-refine",
                        color="blue",
                    ),
                    dmc.Button(
                        "↺ Start Over",
                        id="btn-designer-start-over",
                        variant="outline",
                        color="red",
                    ),
                ],
                gap="sm",
            )
        )
    return dmc.Stack(children, gap="sm")


def _refine_image_row(idx: int, filename: str) -> Any:
    return dmc.Paper(
        dmc.Group(
            [
                dmc.Text(filename, size="sm", style={"flex": 1}, truncate="end"),
                dmc.ActionIcon(
                    "✕",
                    id={"type": "designer-refine-image-delete", "index": idx},
                    color="red",
                    variant="subtle",
                    size="sm",
                ),
            ],
            justify="space-between",
            wrap="nowrap",
        ),
        withBorder=True,
        p="xs",
        radius="sm",
    )


def _step7_content(store: dict[str, Any], image_support: bool | None = None) -> Any:
    refine_images: list[dict[str, str]] = store.get("refine_images", [])
    children: list[Any] = [
        _fullscreen_row(),
        _MOCK_DISCLAIMER,
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
        dmc.Textarea(
            id="designer-refine-input",
            label="Describe the changes you'd like",
            placeholder=(
                "e.g. Make the hero section larger, use a warmer color palette..."
            ),
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
                multiple=False,
                children=dmc.Text(
                    "Drag & drop a reference image (optional)",
                    ta="center",
                    c="dimmed",
                    py="sm",
                ),
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
                [
                    _refine_image_row(i, img["filename"])
                    for i, img in enumerate(refine_images)
                ],
                gap="xs",
            )
        )
    children.append(
        dmc.Group(
            [
                dmc.Button(
                    "↺ Cancel",
                    id="btn-designer-refine-cancel",
                    variant="outline",
                    color="gray",
                ),
                dmc.Button(
                    "Regenerate Mock →",
                    id="btn-designer-regenerate",
                ),
            ]
        )
    )
    return dmc.Stack(children, gap="sm")


def designer_layout(
    session: dict[str, Any] | None = None, prefs: dict[str, Any] | None = None
) -> Any:
    session = session or {}
    # Designer has no chat turn, so its gate stands in front of the whole
    # wizard rather than in front of an opening message. Rendering it instead
    # of the wizard also keeps the wizard's stores from initialising against a
    # model the developer has not chosen yet; answering re-renders the page,
    # since `render_page` is driven by the session store.
    if _llm_gate.is_open(session, "designer") or (
        session.get("agent_llm_draft") or {}
    ).get("agent") == "designer":
        return html.Div(
            [
                dmc.Title("🎨 Designer", order=3, mb="md"),
                _llm_gate.gate_card(session, prefs, "designer"),
            ]
        )
    working_dir: str | None = session.get("working_dir")
    vision: dict[str, Any] = session.get("vision_statement") or {}
    code_review: dict[str, Any] = session.get("code_review") or {}
    design_dir = _design_dir(
        working_dir, project_manager.active_version(working_dir, session)
    )
    saved = load_session(design_dir) if working_dir else None
    # D-PM1: "Modify existing" only makes sense for a project the developer has
    # said is theirs. When they told us this is a new project, UI files in the
    # directory are scaffolding, and offering to reproduce their look and feel
    # would capture a starter template as the design baseline. A mock already
    # saved under .spec4/ is Spec4's own output and still counts either way.
    if session.get("project_mode") == PROJECT_MODE_NEW:
        has_existing_ui = bool(
            working_dir and (design_dir / "mock.html").exists()
        )
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
            # `_chat_layout` fires an agent's opening turn.
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
            dmc.Group(
                [
                    dmc.Title("Designer", order=3),
                    dmc.Button(
                        "← Back",
                        id="btn-designer-back",
                        variant="filled",
                        size="xs",
                        color="blue",
                    ),
                ],
                justify="space-between",
                align="center",
                mb="sm",
            ),
            dmc.Text(
                [
                    "Hello! I'm the ",
                    html.Strong("Designer"),
                    ". I'll generate a self-contained HTML mock-up of your "
                    "application's starting screen — a visual design reference "
                    "ready to hand off to your coding agent.",
                ],
                c="dimmed",
                mb="md",
            ),
            dmc.Accordion(
                dmc.AccordionItem(
                    [
                        dmc.AccordionControl(
                            dmc.Text(
                                "ℹ️ How to use Designer",
                                fw=600,
                                c="blue.4",
                            )
                        ),
                        dmc.AccordionPanel(
                            dcc.Markdown(
                                "Designer works in a few short steps:\n\n"
                                "1. **Choose your starting point** — create a "
                                "fresh design, or let Designer scan your existing "
                                "project files and capture their current look "
                                "and feel.\n"
                                "2. **Describe the style** — enter your visual "
                                "preferences: theme (light/dark), colors, layout "
                                "style, mood, typography, or any other design "
                                "direction you have in mind.\n"
                                "3. **Add reference screenshots** *(optional)* — "
                                "upload images of designs you like. For each one "
                                "you can add a note describing what you want to "
                                "take from it or avoid.\n"
                                "4. **Review the mock** — Designer generates a "
                                "complete, self-contained HTML file. You can "
                                "**Approve** it to move on, **Refine** it with a "
                                "description of changes (and optional reference "
                                "images), or **Start Over** from scratch.\n\n"
                                "The finished mock is saved to "
                                "`.spec4/v{N}/design/mock.html` (the current "
                                "round's version) in your project directory. "
                                "Phaser will direct your coding agent "
                                "to reference it during implementation.\n\n"
                                "**Tips for better results:**\n"
                                "- Be specific — *\"dark navy background, orange "
                                "accent, card-based layout\"* produces better "
                                "output than *\"modern\"*.\n"
                                "- The mock covers the starting screen only, not "
                                "every page.\n"
                                "- Use the Refine step rather than Start Over "
                                "when you just want to tweak details.",
                                style={"color": "var(--mantine-color-dark-1)"},
                            )
                        ),
                    ],
                    value="how-to",
                ),
                variant="contained",
                radius="md",
                styles={
                    "item": {"border": "1px solid var(--mantine-color-blue-4)"},
                    "control": {
                        "borderRadius": "var(--mantine-radius-md)",
                        "borderLeft": "3px solid var(--mantine-color-blue-4)",
                    },
                },
                mb="lg",
            ),
            dmc.Stepper(
                id="designer-stepper",
                active=initial_step - 1,
                size="sm",
                mb="xl",
                children=[
                    dmc.StepperStep(label="No-UI Check"),
                    dmc.StepperStep(label="Start / Resume"),
                    dmc.StepperStep(label="Preferences"),
                    dmc.StepperStep(label="Screenshots"),
                    dmc.StepperStep(label="Generate"),
                    dmc.StepperStep(label="Preview"),
                ],
            ),
            html.Div(id="designer-step-content"),
        ]
    )
