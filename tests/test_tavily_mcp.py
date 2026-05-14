import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from spec4 import tavily_mcp


class TestUrlBuilder:
    def test_contains_api_key(self) -> None:
        assert "my-key" in tavily_mcp._url("my-key")

    def test_is_https(self) -> None:
        assert tavily_mcp._url("key").startswith("https://")


class TestWebSearchToolSpec:
    def test_type_is_function(self) -> None:
        assert tavily_mcp.WEB_SEARCH_TOOL["type"] == "function"

    def test_name_is_web_search(self) -> None:
        assert tavily_mcp.WEB_SEARCH_TOOL["function"]["name"] == "web_search"

    def test_has_query_parameter(self) -> None:
        params = tavily_mcp.WEB_SEARCH_TOOL["function"]["parameters"]
        assert "query" in params["properties"]
        assert "query" in params["required"]


class TestValidate:
    def test_success_returns_true_with_tools(self) -> None:
        with patch(
            "spec4.tavily_mcp._list_tools_async",
            new_callable=AsyncMock,
            return_value=["search"],
        ):
            ok, tools, err = tavily_mcp.validate("valid-key")
        assert ok is True
        assert tools == ["search"]
        assert err == ""

    def test_failure_returns_false_with_message(self) -> None:
        with patch(
            "spec4.tavily_mcp._list_tools_async",
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused"),
        ):
            ok, tools, err = tavily_mcp.validate("bad-key")
        assert ok is False
        assert tools == []
        assert "Connection refused" in err


class TestSearch:
    def test_returns_result_text(self) -> None:
        with patch(
            "spec4.tavily_mcp._call_search_async",
            new_callable=AsyncMock,
            return_value="Search results here",
        ):
            assert tavily_mcp.search("query", "key") == "Search results here"

    def test_exception_returns_error_string(self) -> None:
        with patch(
            "spec4.tavily_mcp._call_search_async",
            new_callable=AsyncMock,
            side_effect=Exception("timeout"),
        ):
            result = tavily_mcp.search("query", "key")
        assert result.startswith("Search failed:")
        assert "timeout" in result


class TestStreamTurn:
    def _chunk(
        self,
        content: str | None,
        finish_reason: str | None = None,
        tool_calls: Any = None,
    ) -> MagicMock:
        chunk = MagicMock()
        chunk.choices[0].delta.content = content
        chunk.choices[0].delta.tool_calls = tool_calls
        chunk.choices[0].finish_reason = finish_reason
        return chunk

    def test_yields_text_chunks(self) -> None:
        chunks = [
            self._chunk("Hello "),
            self._chunk("world"),
            self._chunk("", finish_reason="stop"),
        ]
        messages: list[Any] = []
        with patch("spec4.tavily_mcp.litellm.completion", return_value=iter(chunks)):
            output = "".join(
                tavily_mcp.stream_turn(
                    "sys", messages, {"model": "m", "api_key": "k"}, None
                )
            )
        assert output == "Hello world"

    def test_appends_assistant_message(self) -> None:
        chunks = [self._chunk("Hi"), self._chunk("", finish_reason="stop")]
        messages: list[Any] = []
        with patch("spec4.tavily_mcp.litellm.completion", return_value=iter(chunks)):
            list(
                tavily_mcp.stream_turn(
                    "sys", messages, {"model": "m", "api_key": "k"}, None
                )
            )
        assert messages[-1] == {"role": "assistant", "content": "Hi"}

    def test_no_tools_kwarg_when_no_tavily_key(self) -> None:
        chunks = [self._chunk("Hi"), self._chunk("", finish_reason="stop")]
        with patch(
            "spec4.tavily_mcp.litellm.completion", return_value=iter(chunks)
        ) as mock_llm:
            list(
                tavily_mcp.stream_turn("sys", [], {"model": "m", "api_key": "k"}, None)
            )
        assert "tools" not in mock_llm.call_args[1]

    def test_tools_kwarg_present_when_tavily_key_given(self) -> None:
        chunks = [self._chunk("Hi"), self._chunk("", finish_reason="stop")]
        with patch(
            "spec4.tavily_mcp.litellm.completion", return_value=iter(chunks)
        ) as mock_llm:
            list(
                tavily_mcp.stream_turn(
                    "sys", [], {"model": "m", "api_key": "k"}, "tavily-key"
                )
            )
        assert mock_llm.call_args[1]["tools"] == [tavily_mcp.WEB_SEARCH_TOOL]

    def test_system_prompt_prepended(self) -> None:
        chunks = [self._chunk("Hi"), self._chunk("", finish_reason="stop")]
        messages = [{"role": "user", "content": "Hello"}]
        with patch(
            "spec4.tavily_mcp.litellm.completion", return_value=iter(chunks)
        ) as mock_llm:
            list(
                tavily_mcp.stream_turn(
                    "my-system", messages, {"model": "m", "api_key": "k"}, None
                )
            )
        sent = mock_llm.call_args[1]["messages"]
        assert sent[0] == {"role": "system", "content": "my-system"}
        assert sent[1] == {"role": "user", "content": "Hello"}

    def test_tool_call_triggers_search_and_loops(self) -> None:
        tc = MagicMock()
        tc.index = 0
        tc.id = "call-1"
        tc.function.name = "web_search"
        tc.function.arguments = json.dumps({"query": "test search"})

        tool_chunk = self._chunk(None, tool_calls=[tc])
        call_count = 0

        def fake_completion(**kwargs: Any) -> Iterator[MagicMock]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return iter([tool_chunk, self._chunk("", finish_reason="stop")])
            return iter([self._chunk("Answer"), self._chunk("", finish_reason="stop")])

        messages: list[Any] = []
        with patch("spec4.tavily_mcp.litellm.completion", side_effect=fake_completion):
            with patch(
                "spec4.tavily_mcp.search", return_value="search results"
            ) as mock_search:
                output = "".join(
                    tavily_mcp.stream_turn(
                        "sys", messages, {"model": "m", "api_key": "k"}, "tv-key"
                    )
                )

        mock_search.assert_called_once_with("test search", "tv-key")
        assert "Answer" in output
        assert call_count == 2

    def test_response_format_suppresses_tools_on_clean_history(self) -> None:
        """Fresh json_object call with no prior tool use: no tools= sent."""
        chunks = [self._chunk("{}"), self._chunk("", finish_reason="stop")]
        with patch(
            "spec4.tavily_mcp.litellm.completion", return_value=iter(chunks)
        ) as mock_llm:
            list(
                tavily_mcp.stream_turn(
                    "sys",
                    [{"role": "user", "content": "ok"}],
                    {"model": "m", "api_key": "k"},
                    "tv-key",
                    response_format={"type": "json_object"},
                )
            )
        assert "tools" not in mock_llm.call_args[1]
        assert mock_llm.call_args[1]["response_format"] == {"type": "json_object"}

    def test_response_format_keeps_tools_when_history_has_tool_use(self) -> None:
        """Regression — Anthropic rejects tool_use/tool_result in history
        without `tools=` even when the caller wants response_format-only
        output. This was the UnsupportedParamsError seen on CodeScanner
        validation retries after the model had already web-searched."""
        chunks = [self._chunk("{}"), self._chunk("", finish_reason="stop")]
        messages = [
            {"role": "user", "content": "search and answer"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": '{"query": "x"}',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "results"},
            {"role": "assistant", "content": "First draft of JSON…"},
            {"role": "user", "content": "Re-emit, schema failed"},
        ]
        with patch(
            "spec4.tavily_mcp.litellm.completion", return_value=iter(chunks)
        ) as mock_llm:
            list(
                tavily_mcp.stream_turn(
                    "sys",
                    messages,
                    {"model": "m", "api_key": "k"},
                    "tv-key",
                    response_format={"type": "json_object"},
                )
            )
        # Must include tools= so Anthropic accepts the request.
        assert mock_llm.call_args[1]["tools"] == [tavily_mcp.WEB_SEARCH_TOOL]
        assert mock_llm.call_args[1]["response_format"] == {"type": "json_object"}

    def test_response_format_without_tavily_key_sends_no_tools(self) -> None:
        """No tavily key → no tools= ever, regardless of history."""
        chunks = [self._chunk("{}"), self._chunk("", finish_reason="stop")]
        messages = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "x", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "r"},
        ]
        with patch(
            "spec4.tavily_mcp.litellm.completion", return_value=iter(chunks)
        ) as mock_llm:
            list(
                tavily_mcp.stream_turn(
                    "sys",
                    messages,
                    {"model": "m", "api_key": "k"},
                    None,
                    response_format={"type": "json_object"},
                )
            )
        assert "tools" not in mock_llm.call_args[1]

    def test_history_has_tool_use_detects_both_shapes(self) -> None:
        assert tavily_mcp._history_has_tool_use([]) is False
        assert (
            tavily_mcp._history_has_tool_use(
                [{"role": "user", "content": "hi"}]
            )
            is False
        )
        # Tool-result message detected.
        assert (
            tavily_mcp._history_has_tool_use(
                [{"role": "tool", "tool_call_id": "x", "content": "r"}]
            )
            is True
        )
        # Assistant message with tool_calls detected.
        assert (
            tavily_mcp._history_has_tool_use(
                [
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{"id": "x", "type": "function"}],
                    }
                ]
            )
            is True
        )

    def test_tool_call_yields_search_indicator(self) -> None:
        tc = MagicMock()
        tc.index = 0
        tc.id = "call-1"
        tc.function.name = "web_search"
        tc.function.arguments = json.dumps({"query": "my query"})

        call_count = 0

        def fake_completion(**kwargs: Any) -> Iterator[MagicMock]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return iter(
                    [
                        self._chunk(None, tool_calls=[tc]),
                        self._chunk("", finish_reason="stop"),
                    ]
                )
            return iter([self._chunk("Done"), self._chunk("", finish_reason="stop")])

        with patch("spec4.tavily_mcp.litellm.completion", side_effect=fake_completion):
            with patch("spec4.tavily_mcp.search", return_value="results"):
                chunks = list(
                    tavily_mcp.stream_turn(
                        "sys", [], {"model": "m", "api_key": "k"}, "tv-key"
                    )
                )

        combined = "".join(chunks)
        assert "my query" in combined


class TestTemperatureWiring:
    """Per-agent temperature routing in stream_turn."""

    def _chunks(self) -> list[MagicMock]:
        chunk = MagicMock()
        chunk.choices[0].delta.content = "Hi"
        chunk.choices[0].delta.tool_calls = None
        chunk.choices[0].finish_reason = None
        stop = MagicMock()
        stop.choices[0].delta.content = ""
        stop.choices[0].delta.tool_calls = None
        stop.choices[0].finish_reason = "stop"
        return [chunk, stop]

    def test_no_temperature_when_agent_name_omitted(self) -> None:
        with patch(
            "spec4.tavily_mcp.litellm.completion", return_value=iter(self._chunks())
        ) as mock_llm:
            list(
                tavily_mcp.stream_turn(
                    "sys", [], {"model": "m", "api_key": "k"}, None
                )
            )
        assert "temperature" not in mock_llm.call_args[1]

    def test_no_temperature_for_unmapped_agent(self) -> None:
        with patch(
            "spec4.tavily_mcp.litellm.completion", return_value=iter(self._chunks())
        ) as mock_llm:
            list(
                tavily_mcp.stream_turn(
                    "sys",
                    [],
                    {"model": "m", "api_key": "k"},
                    None,
                    agent_name="brainstormer",
                )
            )
        assert "temperature" not in mock_llm.call_args[1]

    def test_code_scanner_uses_0_2(self) -> None:
        with patch(
            "spec4.tavily_mcp.litellm.completion", return_value=iter(self._chunks())
        ) as mock_llm:
            list(
                tavily_mcp.stream_turn(
                    "sys",
                    [],
                    {"model": "m", "api_key": "k"},
                    None,
                    agent_name="code_scanner",
                )
            )
        assert mock_llm.call_args[1]["temperature"] == 0.2

    def test_phaser_uses_0_2(self) -> None:
        with patch(
            "spec4.tavily_mcp.litellm.completion", return_value=iter(self._chunks())
        ) as mock_llm:
            list(
                tavily_mcp.stream_turn(
                    "sys",
                    [],
                    {"model": "m", "api_key": "k"},
                    None,
                    agent_name="phaser",
                )
            )
        assert mock_llm.call_args[1]["temperature"] == 0.2

    def test_deployer_uses_0_3(self) -> None:
        with patch(
            "spec4.tavily_mcp.litellm.completion", return_value=iter(self._chunks())
        ) as mock_llm:
            list(
                tavily_mcp.stream_turn(
                    "sys",
                    [],
                    {"model": "m", "api_key": "k"},
                    None,
                    agent_name="deployer",
                )
            )
        assert mock_llm.call_args[1]["temperature"] == 0.3

    def test_explicit_llm_config_temperature_overrides_agent_mapping(self) -> None:
        with patch(
            "spec4.tavily_mcp.litellm.completion", return_value=iter(self._chunks())
        ) as mock_llm:
            list(
                tavily_mcp.stream_turn(
                    "sys",
                    [],
                    {"model": "m", "api_key": "k", "temperature": 0.9},
                    None,
                    agent_name="code_scanner",
                )
            )
        assert mock_llm.call_args[1]["temperature"] == 0.9

    def test_explicit_none_temperature_disables_mapping(self) -> None:
        # An explicit `temperature: None` in llm_config should suppress the
        # per-agent mapping (user opt-out, e.g. provider that rejects the kwarg).
        with patch(
            "spec4.tavily_mcp.litellm.completion", return_value=iter(self._chunks())
        ) as mock_llm:
            list(
                tavily_mcp.stream_turn(
                    "sys",
                    [],
                    {"model": "m", "api_key": "k", "temperature": None},
                    None,
                    agent_name="code_scanner",
                )
            )
        assert "temperature" not in mock_llm.call_args[1]


class TestSupportsResponseFormat:
    def test_returns_true_when_param_listed(self) -> None:
        with patch(
            "spec4.tavily_mcp.litellm.get_supported_openai_params",
            return_value=["temperature", "response_format", "tools"],
        ):
            assert tavily_mcp.supports_response_format("gpt-4o-mini") is True

    def test_returns_false_when_param_absent(self) -> None:
        with patch(
            "spec4.tavily_mcp.litellm.get_supported_openai_params",
            return_value=["temperature"],
        ):
            assert tavily_mcp.supports_response_format("some-model") is False

    def test_returns_false_on_exception(self) -> None:
        with patch(
            "spec4.tavily_mcp.litellm.get_supported_openai_params",
            side_effect=Exception("unknown model"),
        ):
            assert tavily_mcp.supports_response_format("mystery") is False

    def test_returns_false_on_empty_model(self) -> None:
        assert tavily_mcp.supports_response_format("") is False


class TestResponseFormatPassthrough:
    """response_format kwarg flows from stream_turn into the litellm call."""

    def _chunks(self) -> list[MagicMock]:
        chunk = MagicMock()
        chunk.choices[0].delta.content = "Hi"
        chunk.choices[0].delta.tool_calls = None
        chunk.choices[0].finish_reason = None
        stop = MagicMock()
        stop.choices[0].delta.content = ""
        stop.choices[0].delta.tool_calls = None
        stop.choices[0].finish_reason = "stop"
        return [chunk, stop]

    def test_response_format_forwarded_to_litellm(self) -> None:
        with patch(
            "spec4.tavily_mcp.litellm.completion", return_value=iter(self._chunks())
        ) as mock_llm:
            list(
                tavily_mcp.stream_turn(
                    "sys",
                    [],
                    {"model": "m", "api_key": "k"},
                    None,
                    response_format={"type": "json_object"},
                )
            )
        assert mock_llm.call_args[1]["response_format"] == {"type": "json_object"}

    def test_no_response_format_kwarg_when_unset(self) -> None:
        with patch(
            "spec4.tavily_mcp.litellm.completion", return_value=iter(self._chunks())
        ) as mock_llm:
            list(
                tavily_mcp.stream_turn(
                    "sys", [], {"model": "m", "api_key": "k"}, None
                )
            )
        assert "response_format" not in mock_llm.call_args[1]

    def test_tools_suppressed_when_response_format_set(self) -> None:
        # Mixing web_search tool calls with structured-output mode is
        # rejected by most providers; stream_turn drops tools on those calls.
        with patch(
            "spec4.tavily_mcp.litellm.completion", return_value=iter(self._chunks())
        ) as mock_llm:
            list(
                tavily_mcp.stream_turn(
                    "sys",
                    [],
                    {"model": "m", "api_key": "k"},
                    "tavily-key",
                    response_format={"type": "json_object"},
                )
            )
        assert "tools" not in mock_llm.call_args[1]
        assert mock_llm.call_args[1]["response_format"] == {"type": "json_object"}
