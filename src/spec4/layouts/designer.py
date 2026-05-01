from __future__ import annotations

import pathlib
from typing import Any

from dash import dcc, html
import dash_mantine_components as dmc

from spec4.agents.designer import detect_no_ui, load_session

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


def _design_dir(working_dir: str | None) -> pathlib.Path:
    return pathlib.Path(working_dir or ".") / ".spec4" / "design"


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


def _step2_content() -> Any:
    return dmc.Stack(
        [
            dmc.Text(
                "Would you like to modify an existing look and feel, "
                "or create a brand-new design?",
                c="dimmed",
            ),
            dmc.Group(
                [
                    dmc.Button(
                        "Modify existing look and feel",
                        id="btn-designer-modify-existing",
                        variant="outline",
                    ),
                    dmc.Button(
                        "Create new design",
                        id="btn-designer-create-new",
                    ),
                    dmc.Button(
                        "Skip Designer",
                        id="btn-designer-skip-2",
                        variant="outline",
                        color="gray",
                    ),
                ]
            ),
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


def _step5_content(buffer_data: dict[str, Any] | None = None) -> Any:
    bd = buffer_data or {}
    error: str | None = bd.get("error")
    tokens: int = bd.get("tokens", 0)
    progress_val: int = bd.get("progress", 0)
    children: list[Any] = [
        dmc.Alert(error, color="red", variant="light", title="Generation Error")
        if error
        else dmc.Alert(
            "Generating your mock — this may take several minutes.",
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
            f"Tokens received: {tokens}",
            id="mock-token-count",
            c="dimmed",
            size="sm",
        ),
    ]
    if error:
        children.append(
            dmc.Button("↺ Retry", id="btn-designer-retry", variant="outline")
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


def _step6_content(store: dict[str, Any]) -> Any:
    return dmc.Stack(
        [
            dmc.Group(
                [
                    dmc.Button(
                        "⛶ Full Screen",
                        id="mock-fullscreen-btn",
                        variant="outline",
                        size="sm",
                    ),
                ],
                justify="flex-end",
            ),
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
            ),
        ],
        gap="sm",
    )


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


def _step7_content(store: dict[str, Any]) -> Any:
    refine_images: list[dict[str, str]] = store.get("refine_images", [])
    children: list[Any] = [
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
        ),
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
        ),
    ]
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


def designer_layout(session: dict[str, Any] | None = None) -> Any:
    session = session or {}
    working_dir: str | None = session.get("working_dir")
    vision: dict[str, Any] = session.get("vision_statement") or {}
    code_review: dict[str, Any] = session.get("code_review") or {}
    design_dir = _design_dir(working_dir)
    saved = load_session(design_dir) if working_dir else None

    if saved and saved["mock_html"]:
        initial_step = 6
        initial_store: dict[str, Any] = {
            "step": 6,
            "preference_text": saved["preference_text"],
            "screenshots": saved["screenshots"],
            "mock_html": saved["mock_html"],
            "finalized": saved["finalized"],
        }
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
                data={"text": "", "tokens": 0, "progress": 0, "error": None},
            ),
            dcc.Store(
                id="mock-done-store",
                storage_type="memory",
                data=None,
            ),
            dcc.Interval(
                id="mock-stream-interval",
                interval=250,
                disabled=True,
            ),
            dmc.Title("Designer", order=3, mb="sm"),
            dmc.Text(
                "Create a visual mock-up for your application's starting screen.",
                c="dimmed",
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
