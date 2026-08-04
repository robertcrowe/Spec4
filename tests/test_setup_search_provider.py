"""The web-search setup step: choose a provider, then enter its key.

This step used to be Tavily-only — a single "Tavily API Key" field. It now
offers Tavily or Exa. Two upgrade paths have to keep working: a saved
preference written before Exa existed (``tavily_key``), and a browser session
carrying the old ``tavily_api_key``. Both are read as Tavily, and both are
cleared the moment the developer makes an explicit choice — otherwise "Skip"
or "switch to Exa" would leave the old key quietly in charge.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from dash import no_update

from spec4 import websearch
from spec4.callbacks import (
    on_search_provider_hint,
    on_setup_search_connect,
    on_setup_search_skip,
)
from spec4.layouts._setup import _setup_layout


def _find(component: Any, component_id: str) -> Any:
    """Depth-first search of a Dash component tree for a given id."""
    if getattr(component, "id", None) == component_id:
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    if not isinstance(children, list | tuple):
        children = [children]
    for child in children:
        found = _find(child, component_id)
        if found is not None:
            return found
    return None


def _session(**extra: Any) -> dict[str, Any]:
    # available_models + model set → _setup_layout renders the search step.
    session: dict[str, Any] = {
        "available_models": ["m"],
        "model": "m",
        "provider": "anthropic",
    }
    session.update(extra)
    return session


class TestLayout:
    def test_renders_a_provider_select_with_both_options(self) -> None:
        page = _setup_layout(_session(), {})
        select = _find(page, "setup-search-provider")
        assert select is not None
        assert select.data == ["Tavily", "Exa"]

    def test_defaults_to_tavily(self) -> None:
        page = _setup_layout(_session(), {})
        assert _find(page, "setup-search-provider").value == "Tavily"
        assert _find(page, "setup-search-key").label == "Tavily API Key"

    def test_saved_provider_and_key_are_restored(self) -> None:
        prefs = {"search_provider": "exa", "search_key": "exa-abc"}
        page = _setup_layout(_session(), prefs)
        assert _find(page, "setup-search-provider").value == "Exa"
        key_field = _find(page, "setup-search-key")
        assert key_field.value == "exa-abc"
        assert key_field.label == "Exa API Key"

    def test_pre_exa_saved_key_still_populates_the_field(self) -> None:
        # The old preference name. Without this the developer's saved key
        # appears to have been thrown away by the upgrade.
        page = _setup_layout(_session(), {"tavily_key": "tvly-old"})
        assert _find(page, "setup-search-key").value == "tvly-old"
        assert _find(page, "setup-search-provider").value == "Tavily"

    def test_unknown_saved_provider_falls_back_to_default(self) -> None:
        page = _setup_layout(_session(), {"search_provider": "bing"})
        assert _find(page, "setup-search-provider").value == "Tavily"

    def test_skip_and_connect_buttons_are_present(self) -> None:
        page = _setup_layout(_session(), {})
        assert _find(page, "btn-setup-search-skip") is not None
        assert _find(page, "btn-setup-search-connect") is not None


class TestProviderHint:
    def test_key_field_follows_the_selected_provider(self) -> None:
        label, placeholder, hint = on_search_provider_hint("Exa")
        assert label == "Exa API Key"
        assert placeholder == websearch.PROVIDERS["exa"]["placeholder"]
        assert hint is not None

    def test_tavily_hint(self) -> None:
        label, placeholder, _ = on_search_provider_hint("Tavily")
        assert label == "Tavily API Key"
        assert placeholder == "tvly-…"

    def test_unknown_label_does_not_crash(self) -> None:
        # Fires with prevent_initial_call=False, so it can run before the
        # select has a value.
        label, _, _ = on_search_provider_hint(None)
        assert label == "Tavily API Key"


class TestConnect:
    def _connect(
        self,
        provider_label: str,
        key: str,
        session: dict[str, Any] | None = None,
        prefs: dict[str, Any] | None = None,
        ok: bool = True,
        err: str = "",
    ) -> Any:
        with patch.object(
            websearch, "validate", return_value=(ok, ["search"], err)
        ) as mock_validate:
            result = on_setup_search_connect(
                1, provider_label, key, session or _session(), prefs or {}
            )
        return result, mock_validate

    def test_validates_against_the_chosen_provider(self) -> None:
        (new_session, _, path), mock_validate = self._connect("Exa", "exa-abc")
        mock_validate.assert_called_once_with(
            websearch.SearchConfig("exa", "exa-abc")
        )
        assert new_session["search_provider"] == "exa"
        assert new_session["search_api_key"] == "exa-abc"
        assert new_session["phase"] == "agent_select"
        assert path == "/agents"

    def test_key_is_stripped(self) -> None:
        (new_session, _, _), _ = self._connect("Tavily", "  tvly-abc  ")
        assert new_session["search_api_key"] == "tvly-abc"

    def test_missing_key_names_the_provider(self) -> None:
        (new_session, prefs, path), mock_validate = self._connect("Exa", "  ")
        assert "Exa" in new_session["setup_error"]
        assert prefs is no_update and path is no_update
        mock_validate.assert_not_called()

    def test_failure_names_the_provider(self) -> None:
        (new_session, _, path), _ = self._connect(
            "Exa", "bad", ok=False, err="401 Unauthorized"
        )
        assert new_session["setup_error"].startswith("Exa connection failed")
        assert "401 Unauthorized" in new_session["setup_error"]
        assert path is no_update
        assert "search_api_key" not in new_session or not new_session.get(
            "search_api_key"
        )

    def test_saves_prefs_only_when_asked(self) -> None:
        (_, prefs, _), _ = self._connect("Exa", "k", prefs={"save_prefs": True})
        assert prefs["search_provider"] == "exa"
        assert prefs["search_key"] == "k"

        (_, prefs, _), _ = self._connect("Exa", "k", prefs={"save_prefs": False})
        assert "search_key" not in prefs

    def test_switching_to_exa_clears_the_legacy_tavily_key(self) -> None:
        # `websearch.from_session` falls back to `tavily_api_key`, but only
        # when `search_api_key` is empty — so this matters most on Skip. Clear
        # it here too so no stale credential lingers in the session at all.
        session = _session(tavily_api_key="tvly-old")
        (new_session, prefs, _), _ = self._connect(
            "Exa", "exa-new", session=session, prefs={"save_prefs": True,
                                                      "tavily_key": "tvly-old"}
        )
        assert new_session["tavily_api_key"] is None
        assert prefs["tavily_key"] is None
        assert websearch.from_session(new_session) == websearch.SearchConfig(
            "exa", "exa-new"
        )

    def test_no_clicks_is_a_no_op(self) -> None:
        assert on_setup_search_connect(0, "Exa", "k", _session(), {}) == (
            no_update,
            no_update,
            no_update,
        )


class TestSkip:
    def test_clears_search_and_continues(self) -> None:
        new_session, path = on_setup_search_skip(1, _session(search_api_key="k"))
        assert new_session["search_provider"] is None
        assert new_session["search_api_key"] is None
        assert new_session["phase"] == "agent_select"
        assert path == "/agents"

    def test_skip_really_means_no_search(self) -> None:
        # The regression the legacy fallback invites: leaving `tavily_api_key`
        # set would make `from_session` hand every agent the old key even
        # though the developer just declined web search.
        new_session, _ = on_setup_search_skip(1, _session(tavily_api_key="tvly-old"))
        assert websearch.from_session(new_session) is None

    def test_no_clicks_is_a_no_op(self) -> None:
        assert on_setup_search_skip(0, _session()) == (no_update, no_update)
