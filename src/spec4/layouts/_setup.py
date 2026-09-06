from __future__ import annotations

from typing import Any

from dash import html
import dash_mantine_components as dmc

from spec4 import providers, websearch
from spec4.layouts._shared import _card, _error

# Component ids for the two places the same fields are rendered: the setup
# wizard (the default) and the per-agent gate (an override). Only one of the
# two is ever on screen, so plain string ids are enough — the gate records
# which agent it is for in the session draft, not in its ids.
SETUP_IDS: dict[str, str] = {
    "provider": "setup-provider",
    "api_key": "setup-api-key",
    "hint": "setup-api-key-hint",
    "model": "setup-model",
}
GATE_IDS: dict[str, str] = {
    "provider": "agent-llm-provider",
    "api_key": "agent-llm-api-key",
    "hint": "agent-llm-api-key-hint",
    "model": "agent-llm-model",
}


def provider_key_hint(provider_label: str) -> Any:
    """Credential-format guidance for the selected provider, or nothing.

    Only Bedrock needs it: its single field encodes an API key or IAM
    credentials *and* the region. Shared so the gate cannot drift into telling
    a developer something different from the setup screen.
    """
    if providers.provider_key_for_label(provider_label or "") == "bedrock":
        return dmc.Text(
            "Bedrock API key: enter KEY:REGION (e.g. bdak_…:us-east-1). "
            "IAM credentials: ACCESS_KEY_ID:SECRET_ACCESS_KEY:REGION[:SESSION_TOKEN]. "
            "Leave blank to use ambient credentials "
            "(env vars, ~/.aws/credentials, IAM role).",
            size="xs",
            c="dimmed",
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
            mb="md",
        ),
        dmc.PasswordInput(
            id=ids["api_key"],
            label="API Key",
            value=api_key,
            mb="xs",
        ),
        html.Div(
            id=ids["hint"],
            style={"marginBottom": "var(--mantine-spacing-md)"},
        ),
    ]


def model_field(
    ids: dict[str, str], *, available: list[str], value: str | None
) -> Any:
    """The model picker, populated from a successful model-list fetch."""
    return dmc.Select(
        id=ids["model"],
        label="Model",
        data=available,
        value=value,
        mb="md",
    )


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
            dmc.Title("Connect to a default LLM provider", order=3, mb="sm"),
            dmc.Text(
                "Spec4 works with a wide variety of LLM providers and models. "
                "You can choose different providers and models for each agent, "
                "but first we need a default. "
                "Choose the one that works best for you.",
                c="dimmed",
                mb="sm",
            ),
            dmc.Alert(
                "Note: Your API key is never stored outside of your system.",
                variant="light",
                mb="lg",
            ),
            _card(
                *provider_key_fields(
                    SETUP_IDS,
                    provider_label=default_label,
                    api_key=prefs.get("api_key") or "",
                    labels=labels,
                ),
                dmc.Checkbox(
                    id="setup-save-prefs",
                    label="Remember provider and keys in this browser? One key per provider, stored in localStorage only.",  # noqa: E501
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
            dmc.Title("Select a Default Model", order=3, mb="sm"),
            dmc.Text(
                "Now that you have a default provider, please select one of the models that this provider provides. "  # noqa: E501
                "Remember that different models have different capabilities and different costs.",  # noqa: E501
                c="dimmed",
                mb="lg",
            ),
            _card(
                dmc.Alert(f"Connected to {provider_label}", mb="md"),
                dmc.Alert(
                    "Please be aware that the Google free tier has recently "
                    "excluded the Pro models. "
                    "Selecting a Pro model when using the free tier may throw "
                    "an error (or not, if that's changed recently). "
                    "If that happens your best bet is probably to close and restart.",
                    color="yellow",
                    variant="light",
                    mb="md",
                )
                if session["provider"] == "gemini"
                else html.Div(),
                model_field(SETUP_IDS, available=available, value=default_model),
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
                html.Div(
                    [
                        dmc.Text(
                            "Checking model capabilities…",
                            size="sm",
                            c="dimmed",
                            mb="xs",
                            mt="md",
                        ),
                        dmc.Progress(
                            value=100,
                            animated=True,
                            striped=True,
                            size="sm",
                        ),
                    ],
                    id="setup-probe-progress-container",
                    style={"display": "none"},
                ),
            ),
        ]
    )


def _setup_search_layout(
    session: dict[str, Any],
    prefs: dict[str, Any],
    setup_error: str | None,
    image_support: bool | None = None,
    tool_support: bool | None = None,
) -> html.Div:
    if image_support is True:
        image_alert: Any = dmc.Alert(
            "This model supports image input — screenshot examples are available "
            "in the Designer step.",
            title="Image Support",
            variant="light",
            mb="md",
        )
    elif image_support is False:
        image_alert = dmc.Alert(
            "This model does not support image input — screenshot upload will be "
            "disabled in the Designer step. Go back to choose a different model if "
            "you need image support.",
            title="No Image Support",
            color="yellow",
            variant="filled",
            styles={"title": {"color": "#212121"}, "message": {"color": "#212121"}},
            mb="md",
        )
    else:
        image_alert = html.Div()

    if tool_support is False:
        tool_alert: Any = dmc.Alert(
            "This model does not support tool calling — web search will be "
            "unavailable even if you enter a key. Go back to choose a "
            "different model if you need web search.",
            title="No Tool Support",
            color="yellow",
            variant="filled",
            styles={"title": {"color": "#212121"}, "message": {"color": "#212121"}},
            mb="md",
        )
    else:
        tool_alert = html.Div()
    # `tavily_key` is the pre-Exa preference name. Read as a fallback so a
    # developer upgrading does not find their saved key gone from the field.
    saved_provider = prefs.get("search_provider")
    if saved_provider not in websearch.PROVIDERS:
        saved_provider = websearch.DEFAULT_PROVIDER
    saved_key = prefs.get("search_key") or prefs.get("tavily_key") or ""
    spec = websearch.PROVIDERS[saved_provider]

    return html.Div(
        [
            dmc.Title("Connect a Web Search Provider", order=3, mb="sm"),
            dmc.Text(
                "Web search tends to be fairly useful when you're creating a spec for an application. "  # noqa: E501
                "It will allow Spec4 to do things like look up the features of a library you might want "  # noqa: E501
                "to use, or compare and contrast two different protocols that you're considering.",  # noqa: E501
                c="dimmed",
                mb="lg",
            ),
            _card(
                dmc.Alert(f"LLM: {session['model']}", mb="md"),
                image_alert,
                tool_alert,
                dmc.Text(
                    "Enables all agents to search the web for current information. "
                    "Choose a provider and enter its API key — or skip if you "
                    "don't have one.",
                    c="dimmed",
                    mb="md",
                ),
                dmc.Select(
                    id="setup-search-provider",
                    label="Search Provider",
                    data=websearch.all_provider_labels(),
                    value=spec["label"],
                    mb="md",
                ),
                dmc.PasswordInput(
                    id="setup-search-key",
                    label=spec["key_label"],
                    placeholder=spec["placeholder"],
                    value=saved_key,
                    mb="xs",
                ),
                html.Div(
                    id="setup-search-hint",
                    style={"marginBottom": "var(--mantine-spacing-md)"},
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
                            "Skip →", id="btn-setup-search-skip", variant="outline"
                        ),
                        dmc.Button("Connect & Start →", id="btn-setup-search-connect"),
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
