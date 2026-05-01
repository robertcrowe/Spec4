from __future__ import annotations

from typing import Any

from dash import html
import dash_mantine_components as dmc

from spec4 import providers
from spec4.layouts._shared import _card, _error


def _setup_provider_layout(
    session: dict[str, Any],
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
            dmc.Title("Connect to an LLM provider", order=3, mb="sm"),
            dmc.Text(
                "Spec4 works with a wide variety of LLM providers and models. "
                "Choose the one that works best for you.",
                c="dimmed",
                mb="sm",
            ),
            dmc.Alert(
                "Note: Your API key is never stored outside of your system.",
                color="blue",
                variant="light",
                mb="lg",
            ),
            _card(
                dmc.Select(
                    id="setup-provider",
                    label="Provider",
                    data=labels,
                    value=default_label,
                    mb="md",
                ),
                dmc.PasswordInput(
                    id="setup-api-key",
                    label="API Key",
                    value=prefs.get("api_key") or "",
                    mb="md",
                ),
                dmc.Checkbox(
                    id="setup-save-prefs",
                    label="Remember provider and keys in this browser? (stored in localStorage only)",  # noqa: E501
                    checked=bool(prefs.get("save_prefs")),
                    mb="md",
                ),
                _error(setup_error) if setup_error else html.Div(),
                dmc.Group(
                    [
                        dmc.Button(
                            "← Back",
                            id="btn-setup-back-to-dir",
                            variant="outline",
                            color="gray",
                        ),
                        dmc.Button("Connect", id="btn-setup-connect"),
                        dmc.Button(
                            "Clear saved credentials",
                            id="btn-setup-clear",
                            variant="outline",
                            color="red",
                            disabled=not bool(prefs),
                        ),
                    ],
                    mt="sm",
                ),
            ),
        ]
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
    provider_label = providers.PROVIDERS[session["provider"]]["label"]
    return html.Div(
        [
            dmc.Title("Select a Model", order=3, mb="sm"),
            dmc.Text(
                "Now that you have a provider, please select one of the models that this provider provides. "  # noqa: E501
                "Remember that different models have different capabilities and different costs.",  # noqa: E501
                c="dimmed",
                mb="lg",
            ),
            _card(
                dmc.Alert(f"Connected to {provider_label}", color="green", mb="md"),
                dmc.Select(
                    id="setup-model",
                    label="Model",
                    data=available,
                    value=default_model,
                    mb="md",
                ),
                _error(setup_error) if setup_error else html.Div(),
                dmc.Group(
                    [
                        dmc.Button(
                            "← Change Provider",
                            id="btn-setup-back-provider",
                            variant="outline",
                            color="gray",
                        ),
                        dmc.Button("Continue →", id="btn-setup-model-continue"),
                    ],
                    mt="sm",
                ),
            ),
        ]
    )


def _setup_tavily_layout(
    session: dict[str, Any],
    prefs: dict[str, Any],
    setup_error: str | None,
    image_support: bool | None = None,
) -> html.Div:
    if image_support is True:
        image_alert: Any = dmc.Alert(
            "This model supports image input — screenshot examples are available "
            "in the Designer step.",
            title="Image Support",
            color="green",
            variant="light",
            mb="md",
        )
    elif image_support is False:
        image_alert = dmc.Alert(
            "This model does not support image input — screenshot upload will be "
            "disabled in the Designer step. Go back to choose a different model if "
            "you need image support.",
            title="No Image Support",
            icon="⚠️",
            color="yellow",
            variant="filled",
            styles={"title": {"color": "#212121"}, "message": {"color": "#212121"}},
            mb="md",
        )
    else:
        image_alert = html.Div()
    return html.Div(
        [
            dmc.Title("Connect to Tavily Web Search", order=3, mb="sm"),
            dmc.Text(
                "Web search tends to be fairly useful when you're creating a spec for an application. "  # noqa: E501
                "It will allow Spec4 to do things like look up the features of a library you might want "  # noqa: E501
                "to use, or compare and contrast two different protocols that you're considering.",  # noqa: E501
                c="dimmed",
                mb="lg",
            ),
            _card(
                dmc.Alert(f"LLM: {session['model']}", color="green", mb="md"),
                image_alert,
                dmc.Text(
                    "Enables all agents to search the web for current information. "
                    "Optional — skip if you don't have a Tavily key.",
                    c="dimmed",
                    mb="md",
                ),
                dmc.PasswordInput(
                    id="setup-tavily-key",
                    label="Tavily API Key",
                    placeholder="tvly-…",
                    value=prefs.get("tavily_key") or "",
                    mb="md",
                ),
                _error(setup_error) if setup_error else html.Div(),
                dmc.Group(
                    [
                        dmc.Button(
                            "← Change Model",
                            id="btn-setup-back-model",
                            variant="outline",
                            color="gray",
                        ),
                        dmc.Button(
                            "Skip →", id="btn-setup-tavily-skip", variant="outline"
                        ),
                        dmc.Button("Connect & Start →", id="btn-setup-tavily-connect"),
                    ],
                    mt="sm",
                ),
            ),
        ]
    )


def _setup_layout(
    session: dict[str, Any],
    prefs: dict[str, Any],
    image_support: bool | None = None,
) -> html.Div:
    labels = providers.all_provider_labels()
    setup_error = session.get("setup_error")
    if session.get("available_models") is None:
        return _setup_provider_layout(session, prefs, labels, setup_error)
    if session.get("model") is None:
        return _setup_model_layout(session, prefs, setup_error)
    return _setup_tavily_layout(session, prefs, setup_error, image_support)
