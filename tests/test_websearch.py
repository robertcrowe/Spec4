"""Web search providers: Tavily and Exa.

Search used to be Tavily-only, and the credential travelled through every agent
as a bare key string. With two providers the key alone no longer says which
service to call, so it travels as a `SearchConfig`. A bare string is still
accepted everywhere and read as Tavily — that is what a session, a saved
preference, or an older test written before Exa is holding.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from spec4 import websearch
from spec4.websearch import DEFAULT_PROVIDER, SearchConfig


class TestRegistry:
    def test_both_providers_present(self) -> None:
        assert set(websearch.PROVIDERS) == {"tavily", "exa"}

    def test_default_is_tavily(self) -> None:
        # Not cosmetic: `coerce` reads a bare key as this provider, so changing
        # it would silently re-route every pre-Exa key to the wrong service.
        assert DEFAULT_PROVIDER == "tavily"

    def test_every_provider_has_the_fields_the_setup_page_renders(self) -> None:
        for key, spec in websearch.PROVIDERS.items():
            for field in ("label", "key_label", "placeholder", "signup_url", "blurb"):
                assert spec.get(field), f"{key} is missing {field}"

    def test_labels_are_offered_in_registry_order(self) -> None:
        assert websearch.all_provider_labels() == ["Tavily", "Exa"]

    def test_label_round_trips(self) -> None:
        for key, spec in websearch.PROVIDERS.items():
            assert websearch.provider_key_for_label(spec["label"]) == key
            assert websearch.label_for_provider(key) == spec["label"]

    def test_unknown_label_falls_back_to_default(self) -> None:
        assert websearch.provider_key_for_label("Bing") == DEFAULT_PROVIDER
        assert websearch.provider_key_for_label("") == DEFAULT_PROVIDER

    def test_unknown_provider_label_falls_back_to_default(self) -> None:
        assert websearch.label_for_provider("nope") == "Tavily"


class TestEndpoint:
    """The one place the two providers actually differ."""

    def test_tavily_carries_the_key_in_the_query_string(self) -> None:
        url, headers = websearch._endpoint(SearchConfig("tavily", "tvly-abc"))
        assert url == "https://mcp.tavily.com/mcp/?tavilyApiKey=tvly-abc"
        assert headers is None

    def test_exa_carries_the_key_in_a_header(self) -> None:
        # Exa documents the x-api-key header, not a query parameter — and a key
        # in a URL leaks into logs and history.
        url, headers = websearch._endpoint(SearchConfig("exa", "exa-abc"))
        assert url == "https://mcp.exa.ai/mcp"
        assert headers == {"x-api-key": "exa-abc"}

    def test_both_endpoints_are_https(self) -> None:
        for provider in websearch.PROVIDERS:
            url, _ = websearch._endpoint(SearchConfig(provider, "k"))
            assert url.startswith("https://")

    def test_unknown_provider_falls_back_to_default(self) -> None:
        url, _ = websearch._endpoint(SearchConfig("nope", "k"))
        assert "tavily" in url

    def test_legacy_url_helper_still_builds_the_tavily_url(self) -> None:
        assert "my-key" in websearch._url("my-key")
        assert websearch._url("k").startswith("https://")


class TestCoerce:
    def test_bare_string_is_read_as_tavily(self) -> None:
        assert websearch.coerce("tvly-abc") == SearchConfig("tavily", "tvly-abc")

    def test_string_is_stripped(self) -> None:
        assert websearch.coerce("  k  ") == SearchConfig("tavily", "k")

    def test_config_passes_through(self) -> None:
        cfg = SearchConfig("exa", "k")
        assert websearch.coerce(cfg) is cfg

    def test_none_stays_none(self) -> None:
        assert websearch.coerce(None) is None

    def test_empty_means_no_search_not_a_blank_tavily_key(self) -> None:
        assert websearch.coerce("") is None
        assert websearch.coerce("   ") is None
        assert websearch.coerce(SearchConfig("exa", "")) is None

    def test_config_is_truthy_so_if_search_checks_still_read_right(self) -> None:
        # Every `if search_cfg:` in the agents used to test a key string.
        assert bool(SearchConfig("exa", "k")) is True


class TestFromSession:
    def test_reads_provider_and_key(self) -> None:
        session = {"search_provider": "exa", "search_api_key": "k"}
        assert websearch.from_session(session) == SearchConfig("exa", "k")

    def test_no_key_means_no_search(self) -> None:
        assert websearch.from_session({}) is None
        assert websearch.from_session({"search_provider": "exa"}) is None
        assert websearch.from_session({"search_api_key": ""}) is None

    def test_missing_provider_defaults_to_tavily(self) -> None:
        session = {"search_api_key": "k"}
        assert websearch.from_session(session) == SearchConfig("tavily", "k")

    def test_unknown_provider_defaults_to_tavily(self) -> None:
        session = {"search_provider": "bing", "search_api_key": "k"}
        assert websearch.from_session(session) == SearchConfig("tavily", "k")

    def test_pre_exa_session_keeps_working(self) -> None:
        # `session` is sessionStorage, so it survives the upgrade that renamed
        # this key. Without the fallback web search would silently switch off.
        session = {"tavily_api_key": "tvly-old"}
        assert websearch.from_session(session) == SearchConfig("tavily", "tvly-old")

    def test_new_key_outranks_the_legacy_one(self) -> None:
        session = {
            "search_provider": "exa",
            "search_api_key": "exa-new",
            "tavily_api_key": "tvly-old",
        }
        assert websearch.from_session(session) == SearchConfig("exa", "exa-new")


class TestValidate:
    def test_success_returns_true_with_tools(self) -> None:
        with patch(
            "spec4.websearch._list_tools_async",
            new_callable=AsyncMock,
            return_value=["search"],
        ):
            ok, tools, err = websearch.validate(SearchConfig("exa", "valid-key"))
        assert ok is True
        assert tools == ["search"]
        assert err == ""

    def test_failure_returns_false_with_message(self) -> None:
        with patch(
            "spec4.websearch._list_tools_async",
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused"),
        ):
            ok, tools, err = websearch.validate(SearchConfig("tavily", "bad-key"))
        assert ok is False
        assert tools == []
        assert "Connection refused" in err

    def test_accepts_a_bare_key(self) -> None:
        with patch(
            "spec4.websearch._list_tools_async",
            new_callable=AsyncMock,
            return_value=["search"],
        ):
            ok, _, _ = websearch.validate("valid-key")
        assert ok is True

    def test_blank_key_fails_without_a_network_call(self) -> None:
        with patch(
            "spec4.websearch._list_tools_async", new_callable=AsyncMock
        ) as mock_list:
            ok, tools, err = websearch.validate("")
        assert ok is False
        assert err
        mock_list.assert_not_called()

    def test_validates_against_the_selected_provider(self) -> None:
        seen: list[SearchConfig] = []

        async def _capture(config: SearchConfig) -> list[str]:
            seen.append(config)
            return ["web_search_exa"]

        with patch("spec4.websearch._list_tools_async", _capture):
            websearch.validate(SearchConfig("exa", "k"))
        assert seen == [SearchConfig("exa", "k")]


class TestSearch:
    def test_returns_result_text(self) -> None:
        with patch(
            "spec4.websearch._call_search_async",
            new_callable=AsyncMock,
            return_value="Search results here",
        ):
            assert websearch.search("query", "key") == "Search results here"

    def test_exception_returns_error_string(self) -> None:
        with patch(
            "spec4.websearch._call_search_async",
            new_callable=AsyncMock,
            side_effect=Exception("timeout"),
        ):
            result = websearch.search("query", "key")
        assert result.startswith("Search failed:")
        assert "timeout" in result

    def test_routes_to_the_configured_provider(self) -> None:
        seen: list[Any] = []

        async def _capture(query: str, config: SearchConfig) -> str:
            seen.append((query, config))
            return "ok"

        with patch("spec4.websearch._call_search_async", _capture):
            assert websearch.search("dash docs", SearchConfig("exa", "k")) == "ok"
        assert seen == [("dash docs", SearchConfig("exa", "k"))]

    def test_no_provider_reports_a_failure_rather_than_raising(self) -> None:
        # `stream_turn` guards against this, but the designer agent's own tool
        # loop calls straight through; it must get a string back either way.
        result = websearch.search("query", None)
        assert result.startswith("Search failed:")


class TestAgentWiring:
    """The developer's choice has to survive the trip from session to endpoint.

    Agents read the session once and hand the result to `stream_turn`; the
    provider is only consulted at the endpoint. A break anywhere along that
    chain shows up as searches silently going to the wrong service (or to
    Tavily with an Exa key), which no unit test of either end would catch.
    """

    def _turn(self, session: dict[str, Any]) -> Any:
        from spec4.agents import brainstormer

        seen: list[Any] = []

        def _stream(*args: Any, **kwargs: Any) -> Any:
            seen.append(args[3])
            args[1].append({"role": "assistant", "content": "hi"})
            return iter(("hi",))

        session.setdefault(
            "brainstormer_messages",
            [
                {"role": "user", "content": "an app"},
                {"role": "assistant", "content": "Tell me more."},
            ],
        )
        with (
            patch.object(
                brainstormer.llm, "build_system_prompt", return_value=""
            ),
            patch.object(brainstormer.llm, "stream_turn", _stream),
        ):
            list(brainstormer.run("go", session, {"model": "x"}))
        return seen[0]

    def test_exa_session_reaches_the_turn_as_an_exa_config(self) -> None:
        cfg = self._turn({"search_provider": "exa", "search_api_key": "exa-k"})
        assert cfg == SearchConfig("exa", "exa-k")
        assert websearch._endpoint(cfg)[1] == {"x-api-key": "exa-k"}

    def test_tavily_session_reaches_the_turn_as_a_tavily_config(self) -> None:
        cfg = self._turn({"search_provider": "tavily", "search_api_key": "tvly-k"})
        assert cfg == SearchConfig("tavily", "tvly-k")
        assert "tavilyApiKey=tvly-k" in websearch._endpoint(cfg)[0]

    def test_no_key_reaches_the_turn_as_none(self) -> None:
        assert self._turn({}) is None
