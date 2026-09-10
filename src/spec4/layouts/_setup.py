from __future__ import annotations

from typing import Any

from dash import html
import dash_mantine_components as dmc

from spec4 import llm_selection, providers, websearch
from spec4.layouts._shared import (
    PROGRESS_CLASS_NAMES,
    STEP_ACTIVE,
    STEP_DONE,
    STEP_UNREACHABLE,
    StepEntry,
    _card,
    _error,
    step_row,
)

# Component ids for the two places the same fields are rendered: the setup
# wizard (the default) and the per-agent gate (an override). Only one of the
# two is ever on screen, so plain string ids are enough — the gate records
# which agent it is for in the session draft, not in its ids.
SETUP_IDS: dict[str, str] = {
    "provider": "setup-provider",
    "api_key": "setup-api-key",
    "hint": "setup-api-key-hint",
    "model": "setup-model",
    "effort": "setup-effort",
}
GATE_IDS: dict[str, str] = {
    "provider": "agent-llm-provider",
    "api_key": "agent-llm-api-key",
    "hint": "agent-llm-api-key-hint",
    "model": "agent-llm-model",
    "effort": "agent-llm-effort",
}

# The three steps, in order, as the indicator names them. One word each: the
# row is a position report, not a description of what each step does — the
# step's own title says that, once, at the top of the panel it belongs to.
SETUP_STEPS: tuple[str, ...] = ("Provider", "Model", "Search")

# The classes `v3.css` draws the indicator with, named here because
# `_shared.step_row` is handed them and the wizard's own test asserts on them.
SETUP_STEP_CLASS = "setup-step"
SETUP_STEPS_CLASS = "setup-steps"

# The credential fact, at the length a dimmed line can carry. It was an alert
# above the panel; it is now one line under the field it is about, which is
# where a developer typing a key would look for it. It lives in the shared
# builder rather than in the wizard, so the gate's key field says the same
# thing in the same place (the design's expanded gate panel draws it there).
NEVER_STORED_NOTICE = "Stored in this browser only, never on the server or disk."

# What choosing an effort here actually decides. The wizard sets the project
# *default*, which every agent inherits unless its own gate overrides it —
# stated once, beside the control, rather than left for the developer to infer
# from the fact that this screen is called "default model".
EFFORT_SCOPE_NOTICE = (
    "Effort applies to every agent that uses the default; "
    "each agent's gate can override it."
)


def setup_step_row(active: int) -> html.Div:
    """The wizard's position indicator, marked by the shared renderer (D-LR9).

    ``active`` is the index into :data:`SETUP_STEPS` of the step on screen.
    Steps behind it are done and read at full weight; steps ahead of it cannot
    be entered yet, so they are dimmed and disabled and carry the reason as
    their tooltip — exactly the marking the chat frame's pipeline row wears,
    from the same function, because a re-themed accent has to move both.

    No entry carries an id. Moving *back* through the wizard is what the Back
    button does, and it does it by resetting the session field the layout
    branches on; giving a done step the same id would put two components with
    one id on the page, and giving it a second id would be a second route to
    the same place. The row reports where the developer is; it is not a
    control.
    """
    entries: list[StepEntry] = []
    for index, label in enumerate(SETUP_STEPS):
        if index == active:
            entries.append(StepEntry(label, STEP_ACTIVE))
        elif index < active:
            entries.append(StepEntry(label, STEP_DONE))
        else:
            entries.append(
                StepEntry(
                    label,
                    STEP_UNREACHABLE,
                    tooltip=f"Finish {SETUP_STEPS[active]} first",
                )
            )
    return step_row(entries, base_class=SETUP_STEP_CLASS, row_class=SETUP_STEPS_CLASS)


def _step_title(text: str) -> Any:
    """One short line naming the step. No paragraph under it (D-LR7)."""
    return html.H2(text, className="screen-title")


def _dim(text: str, **kwargs: Any) -> Any:
    """A fact, at the weight a fact gets: one dimmed line, never an alert.

    An alert is a frame around a sentence, and the wizard had three of them
    saying things that were never warnings — where the key is kept, which
    provider answered, what the model can do. The frames are gone and the
    sentences stayed.
    """
    return dmc.Text(text, className="dim-line", **kwargs)


def provider_key_hint(provider_label: str) -> Any:
    """Credential-format guidance for the selected provider, or nothing.

    Only Bedrock needs it: its single field encodes an API key or IAM
    credentials *and* the region. Shared so the gate cannot drift into telling
    a developer something different from the setup screen.
    """
    if providers.provider_key_for_label(provider_label or "") == "bedrock":
        return _dim(
            "Bedrock API key: enter KEY:REGION (e.g. bdak_…:us-east-1). "
            "IAM credentials: ACCESS_KEY_ID:SECRET_ACCESS_KEY:REGION[:SESSION_TOKEN]. "
            "Leave blank to use ambient credentials "
            "(env vars, ~/.aws/credentials, IAM role)."
        )
    return html.Div()


def provider_key_fields(
    ids: dict[str, str],
    *,
    provider_label: str,
    api_key: str,
    labels: list[str],
) -> list[Any]:
    """Provider select, credential field, and the hint slot the two feed.

    Shared with the per-agent gate through :data:`GATE_IDS`, and restyled here
    once rather than copied: the gate renders whatever this returns, so the two
    screens cannot end up with two field registers. Nothing about the fields
    themselves moved — same ids, same order, same values — only their density
    and the notice under the key.

    The hint is a slot rather than rendered content because it updates as the
    provider changes; each flow owns a small callback that fills it via
    :func:`provider_key_hint`.
    """
    return [
        dmc.Select(
            id=ids["provider"],
            label="Provider",
            data=labels,
            value=provider_label,
            size="xs",
            mb="xs",
        ),
        # The key is an opaque token, so it is set in the app's one monospace
        # face for the same reason paths and model names are — and `classNames`
        # rather than `className`, because Mantine puts the font on the
        # `<input>` itself and a class on the root would reach everything but it.
        dmc.PasswordInput(
            id=ids["api_key"],
            label="API key",
            value=api_key,
            size="xs",
            classNames={"input": "mono"},
        ),
        _dim(NEVER_STORED_NOTICE, mt=4),
        html.Div(id=ids["hint"], style={"marginTop": "4px"}),
    ]


def model_field(
    ids: dict[str, str],
    *,
    available: list[str],
    value: str | None,
    provider_key: str | None = None,
    effort: str = llm_selection.DEFAULT_EFFORT,
) -> Any:
    """The model picker and the effort beside it, on one row.

    The two are one decision — which model, and how hard it thinks — so they
    are one control group, and they are built here rather than at the two call
    sites so the setup wizard's default and the gate's override offer the same
    thing. The effort's values come from
    :func:`llm_selection.offered_efforts` keyed on the *resolved* provider and
    model (D-EF2/D-EF4); they are never inferred from the model name here, and
    a model that does not accept the parameter at all collapses the list to
    ``"default"`` alone, which is what the disabled control means.
    """
    offered = llm_selection.offered_efforts(provider_key, value or "")
    selected = effort if effort in offered else llm_selection.DEFAULT_EFFORT
    return dmc.Group(
        [
            html.Div(
                dmc.Select(
                    id=ids["model"],
                    label="Model",
                    data=available,
                    value=value,
                    size="xs",
                    classNames={"input": "mono"},
                ),
                className="model-field",
            ),
            html.Div(
                dmc.Select(
                    id=ids["effort"],
                    label="Effort",
                    data=offered,
                    value=selected,
                    size="xs",
                    disabled=len(offered) <= 1,
                    classNames={"input": "mono"},
                ),
                className="effort-field",
            ),
        ],
        gap="xs",
        wrap="nowrap",
        align="flex-end",
        className="model-effort-row",
    )


def _setup_provider_layout(
    _session: dict[str, Any],
    prefs: dict[str, Any],
    labels: list[str],
    setup_error: str | None,
) -> html.Div:
    saved_prov = prefs.get("provider")
    default_label = (
        providers.PROVIDERS[saved_prov]["label"]
        if saved_prov in providers.PROVIDERS
        else labels[0]
    )
    return html.Div(
        [
            setup_step_row(0),
            _step_title("Default provider"),
            _card(
                *provider_key_fields(
                    SETUP_IDS,
                    provider_label=default_label,
                    api_key=prefs.get("api_key") or "",
                    labels=labels,
                ),
                dmc.Checkbox(
                    id="setup-save-prefs",
                    label="Remember provider and keys in this browser",
                    checked=bool(prefs.get("save_prefs")),
                    size="xs",
                    mt="xs",
                ),
                _error(setup_error) if setup_error else html.Div(),
            ),
            # One filled action, and it is the one the step is for. Clear saved
            # credentials is a neutral outline in the warn tone — destructive,
            # but not the thing to press — and it takes that tone from
            # `.btn-warn` in the theme rather than from a `color` prop, so a
            # re-themed warn moves it (D-LR2).
            dmc.Group(
                [
                    dmc.Button(
                        "Clear saved credentials",
                        id="btn-setup-clear",
                        variant="outline",
                        size="compact-sm",
                        className="btn-warn",
                        disabled=not bool(prefs),
                    ),
                    dmc.Button("Connect", id="btn-setup-connect", size="compact-sm"),
                ],
                justify="flex-end",
                gap="xs",
                className="btn-row",
            ),
        ],
        className="setup-view",
    )


def _setup_model_layout(
    session: dict[str, Any],
    prefs: dict[str, Any],
    setup_error: str | None,
) -> html.Div:
    available = session["available_models"]
    saved_model = prefs.get("model")
    default_model = (
        saved_model
        if saved_model in available
        else (available[0] if available else None)
    )
    provider_key = session["provider"]
    provider_label = providers.PROVIDERS[provider_key]["label"]
    # The default's effort, read by the one path everything else reads it by —
    # never a store key of this screen's own.
    _, _, effort = llm_selection.default_provider_model(session, prefs)
    return html.Div(
        [
            setup_step_row(1),
            _step_title("Default model"),
            _dim(f"Connected to {provider_label}"),
            _card(
                model_field(
                    SETUP_IDS,
                    available=available,
                    value=default_model,
                    provider_key=provider_key,
                    effort=effort,
                ),
                _dim(EFFORT_SCOPE_NOTICE, mt=8),
                _error(setup_error) if setup_error else html.Div(),
                html.Div(
                    [
                        _dim("Checking model capabilities…", mt=8, mb=4),
                        dmc.Progress(
                            value=100,
                            animated=True,
                            striped=True,
                            size="sm",
                            classNames=PROGRESS_CLASS_NAMES,
                        ),
                    ],
                    id="setup-probe-progress-container",
                    style={"display": "none"},
                ),
                mt=12,
            ),
            dmc.Group(
                [
                    dmc.Button(
                        "Back",
                        id="btn-setup-back-provider",
                        variant="outline",
                        size="compact-sm",
                    ),
                    dmc.Button(
                        "Continue",
                        id="btn-setup-model-continue",
                        size="compact-sm",
                    ),
                ],
                justify="space-between",
                className="btn-row",
            ),
        ],
        className="setup-view",
    )


def _capability_notice(
    model: str, image_support: bool | None, tool_support: bool | None
) -> str:
    """The model and what it cannot do, as one line.

    The two capability answers used to be two alerts, and a ``False`` from
    either is worth saying — an agent that cannot take a screenshot or cannot
    call a tool is a step the developer will otherwise meet the hard way. A
    ``None`` is *unknown*, not a negative (see ``llm_selection``), so it says
    nothing at all rather than warning about a probe that could not answer.
    """
    parts = [f"Model: {model}"]
    if image_support is False:
        parts.append("no image input, so Designer screenshots are unavailable")
    if tool_support is False:
        parts.append("no tool calling, so web search will be unavailable")
    return " · ".join(parts)


def _setup_search_layout(
    session: dict[str, Any],
    prefs: dict[str, Any],
    setup_error: str | None,
    image_support: bool | None = None,
    tool_support: bool | None = None,
) -> html.Div:
    # `tavily_key` is the pre-Exa preference name. Read as a fallback so a
    # developer upgrading does not find their saved key gone from the field.
    saved_provider = prefs.get("search_provider")
    if saved_provider not in websearch.PROVIDERS:
        saved_provider = websearch.DEFAULT_PROVIDER
    saved_key = prefs.get("search_key") or prefs.get("tavily_key") or ""
    spec = websearch.PROVIDERS[saved_provider]

    return html.Div(
        [
            setup_step_row(2),
            _step_title("Web search"),
            _dim(
                _capability_notice(str(session["model"]), image_support, tool_support)
            ),
            _card(
                dmc.Select(
                    id="setup-search-provider",
                    label="Search provider",
                    data=websearch.all_provider_labels(),
                    value=spec["label"],
                    size="xs",
                    mb="xs",
                ),
                dmc.PasswordInput(
                    id="setup-search-key",
                    label=spec["key_label"],
                    placeholder=spec["placeholder"],
                    value=saved_key,
                    size="xs",
                    classNames={"input": "mono"},
                ),
                html.Div(id="setup-search-hint", style={"marginTop": "4px"}),
                _error(setup_error) if setup_error else html.Div(),
                mt=12,
            ),
            dmc.Group(
                [
                    dmc.Button(
                        "Back",
                        id="btn-setup-back-model",
                        variant="outline",
                        size="compact-sm",
                    ),
                    dmc.Group(
                        [
                            dmc.Button(
                                "Skip",
                                id="btn-setup-search-skip",
                                variant="outline",
                                size="compact-sm",
                            ),
                            dmc.Button(
                                "Finish",
                                id="btn-setup-search-connect",
                                size="compact-sm",
                            ),
                        ],
                        gap="xs",
                    ),
                ],
                justify="space-between",
                className="btn-row",
            ),
        ],
        className="setup-view",
    )


def _setup_layout(
    session: dict[str, Any],
    prefs: dict[str, Any],
    image_support: bool | None = None,
    tool_support: bool | None = None,
) -> html.Div:
    labels = providers.all_provider_labels()
    setup_error = session.get("setup_error")
    if session.get("available_models") is None:
        return _setup_provider_layout(session, prefs, labels, setup_error)
    if session.get("model") is None:
        return _setup_model_layout(session, prefs, setup_error)
    return _setup_search_layout(
        session, prefs, setup_error, image_support, tool_support
    )
