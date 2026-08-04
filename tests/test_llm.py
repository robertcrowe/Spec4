import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from litellm.exceptions import BadRequestError as LiteLLMBadRequestError

from spec4 import llm


class TestWebSearchToolSpec:
    def test_type_is_function(self) -> None:
        assert llm.WEB_SEARCH_TOOL["type"] == "function"

    def test_name_is_web_search(self) -> None:
        assert llm.WEB_SEARCH_TOOL["function"]["name"] == "web_search"

    def test_has_query_parameter(self) -> None:
        params = llm.WEB_SEARCH_TOOL["function"]["parameters"]
        assert "query" in params["properties"]
        assert "query" in params["required"]


class TestBuildSystemPrompt:
    """The addendum is gated on "is search configured", not on any one
    provider — it must appear for Exa exactly as it does for Tavily."""

    def test_addendum_added_for_either_provider(self) -> None:
        for provider in ("tavily", "exa"):
            out = llm.build_system_prompt(
                "BASE", llm.SearchConfig(provider, "k")
            )
            assert out.startswith("BASE")
            assert llm.WEB_SEARCH_ADDENDUM in out

    def test_addendum_added_for_a_bare_key(self) -> None:
        out = llm.build_system_prompt("BASE", "tvly-abc")
        assert llm.WEB_SEARCH_ADDENDUM in out

    def test_no_addendum_without_search(self) -> None:
        assert llm.build_system_prompt("BASE", None) == "BASE"
        assert llm.build_system_prompt("BASE", "") == "BASE"


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
        with patch("spec4.llm.litellm.completion", return_value=iter(chunks)):
            output = "".join(
                llm.stream_turn(
                    "sys", messages, {"model": "m", "api_key": "k"}, None
                )
            )
        assert output == "Hello world"

    def test_appends_assistant_message(self) -> None:
        chunks = [self._chunk("Hi"), self._chunk("", finish_reason="stop")]
        messages: list[Any] = []
        with patch("spec4.llm.litellm.completion", return_value=iter(chunks)):
            list(
                llm.stream_turn(
                    "sys", messages, {"model": "m", "api_key": "k"}, None
                )
            )
        assert messages[-1] == {"role": "assistant", "content": "Hi"}

    def test_no_tools_kwarg_when_no_tavily_key(self) -> None:
        chunks = [self._chunk("Hi"), self._chunk("", finish_reason="stop")]
        with patch(
            "spec4.llm.litellm.completion", return_value=iter(chunks)
        ) as mock_llm:
            list(
                llm.stream_turn("sys", [], {"model": "m", "api_key": "k"}, None)
            )
        assert "tools" not in mock_llm.call_args[1]

    def test_tools_kwarg_present_when_tavily_key_given(self) -> None:
        chunks = [self._chunk("Hi"), self._chunk("", finish_reason="stop")]
        with patch(
            "spec4.llm.litellm.completion", return_value=iter(chunks)
        ) as mock_llm:
            list(
                llm.stream_turn(
                    "sys", [], {"model": "m", "api_key": "k"}, "tavily-key"
                )
            )
        assert mock_llm.call_args[1]["tools"] == [llm.WEB_SEARCH_TOOL]

    def test_system_prompt_prepended(self) -> None:
        chunks = [self._chunk("Hi"), self._chunk("", finish_reason="stop")]
        messages = [{"role": "user", "content": "Hello"}]
        with patch(
            "spec4.llm.litellm.completion", return_value=iter(chunks)
        ) as mock_llm:
            list(
                llm.stream_turn(
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
        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            with patch(
                "spec4.llm.search", return_value="search results"
            ) as mock_search:
                output = "".join(
                    llm.stream_turn(
                        "sys", messages, {"model": "m", "api_key": "k"}, "tv-key"
                    )
                )

        mock_search.assert_called_once_with("test search", "tv-key")
        assert "Answer" in output
        assert call_count == 2

    def test_search_config_reaches_the_search_call_unchanged(self) -> None:
        """The tool loop must not flatten the config back to a key string —
        `search` needs the provider to know which endpoint to call."""
        cfg = llm.SearchConfig("exa", "exa-key")
        tc = MagicMock()
        tc.index = 0
        tc.id = "call-1"
        tc.function.name = "web_search"
        tc.function.arguments = json.dumps({"query": "dash docs"})

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
            return iter([self._chunk("Answer"), self._chunk("", finish_reason="stop")])

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            with patch("spec4.llm.search", return_value="hits") as mock_search:
                list(
                    llm.stream_turn(
                        "sys", [], {"model": "m", "api_key": "k"}, cfg
                    )
                )
        mock_search.assert_called_once_with("dash docs", cfg)

    def test_search_config_enables_the_tool(self) -> None:
        chunks = [self._chunk("hi"), self._chunk("", finish_reason="stop")]
        with patch(
            "spec4.llm.litellm.completion", return_value=iter(chunks)
        ) as mock_llm:
            list(
                llm.stream_turn(
                    "sys",
                    [{"role": "user", "content": "ok"}],
                    {"model": "m", "api_key": "k"},
                    llm.SearchConfig("exa", "k"),
                )
            )
        assert mock_llm.call_args[1]["tools"] == [llm.WEB_SEARCH_TOOL]

    def test_response_format_suppresses_tools_on_clean_history(self) -> None:
        """Fresh json_object call with no prior tool use: no tools= sent."""
        chunks = [self._chunk("{}"), self._chunk("", finish_reason="stop")]
        with patch(
            "spec4.llm.litellm.completion", return_value=iter(chunks)
        ) as mock_llm:
            list(
                llm.stream_turn(
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
            "spec4.llm.litellm.completion", return_value=iter(chunks)
        ) as mock_llm:
            list(
                llm.stream_turn(
                    "sys",
                    messages,
                    {"model": "m", "api_key": "k"},
                    "tv-key",
                    response_format={"type": "json_object"},
                )
            )
        # Must include tools= so Anthropic accepts the request.
        assert mock_llm.call_args[1]["tools"] == [llm.WEB_SEARCH_TOOL]
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
            "spec4.llm.litellm.completion", return_value=iter(chunks)
        ) as mock_llm:
            list(
                llm.stream_turn(
                    "sys",
                    messages,
                    {"model": "m", "api_key": "k"},
                    None,
                    response_format={"type": "json_object"},
                )
            )
        assert "tools" not in mock_llm.call_args[1]

    def test_history_has_tool_use_detects_both_shapes(self) -> None:
        assert llm._history_has_tool_use([]) is False
        assert (
            llm._history_has_tool_use(
                [{"role": "user", "content": "hi"}]
            )
            is False
        )
        # Tool-result message detected.
        assert (
            llm._history_has_tool_use(
                [{"role": "tool", "tool_call_id": "x", "content": "r"}]
            )
            is True
        )
        # Assistant message with tool_calls detected.
        assert (
            llm._history_has_tool_use(
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

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            with patch("spec4.llm.search", return_value="results"):
                chunks = list(
                    llm.stream_turn(
                        "sys", [], {"model": "m", "api_key": "k"}, "tv-key"
                    )
                )

        combined = "".join(chunks)
        assert "my query" in combined


class TestNoTemperature:
    """stream_turn never sends `temperature` — the kwarg was removed outright.

    A growing number of models reject the parameter, so no call path sets it
    any more, including when the user's llm_config happens to carry one.
    """

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
            "spec4.llm.litellm.completion", return_value=iter(self._chunks())
        ) as mock_llm:
            list(
                llm.stream_turn(
                    "sys", [], {"model": "m", "api_key": "k"}, None
                )
            )
        assert "temperature" not in mock_llm.call_args[1]

    def test_no_temperature_for_a_named_agent(self) -> None:
        with patch(
            "spec4.llm.litellm.completion", return_value=iter(self._chunks())
        ) as mock_llm:
            list(
                llm.stream_turn(
                    "sys",
                    [],
                    {"model": "m", "api_key": "k"},
                    None,
                    agent_name="code_scanner",
                )
            )
        assert "temperature" not in mock_llm.call_args[1]

    def test_llm_config_temperature_is_not_forwarded(self) -> None:
        with patch(
            "spec4.llm.litellm.completion", return_value=iter(self._chunks())
        ) as mock_llm:
            list(
                llm.stream_turn(
                    "sys",
                    [],
                    {"model": "m", "api_key": "k", "temperature": 0.9},
                    None,
                    agent_name="code_scanner",
                )
            )
        assert "temperature" not in mock_llm.call_args[1]

    def test_module_defines_no_temperature_helpers(self) -> None:
        # Drift guard: the per-agent mapping and the rejection-fallback
        # helpers are gone and must not quietly come back.
        assert not hasattr(llm, "_AGENT_TEMPERATURE")
        assert not hasattr(llm, "_temperature_for")
        assert not hasattr(llm, "_is_temperature_rejected_error")


class TestSupportsResponseFormat:
    def test_returns_true_when_param_listed(self) -> None:
        with patch(
            "spec4.llm.litellm.get_supported_openai_params",
            return_value=["temperature", "response_format", "tools"],
        ):
            assert llm.supports_response_format("gpt-4o-mini") is True

    def test_returns_false_when_param_absent(self) -> None:
        with patch(
            "spec4.llm.litellm.get_supported_openai_params",
            return_value=["temperature"],
        ):
            assert llm.supports_response_format("some-model") is False

    def test_returns_false_on_exception(self) -> None:
        with patch(
            "spec4.llm.litellm.get_supported_openai_params",
            side_effect=Exception("unknown model"),
        ):
            assert llm.supports_response_format("mystery") is False

    def test_returns_false_on_empty_model(self) -> None:
        assert llm.supports_response_format("") is False


class TestIsToolIncompatibleError:
    def test_detects_not_support_auto_tool(self) -> None:
        exc = Exception(
            "This model does not support auto tool, please use tool_choice."
        )
        assert llm._is_tool_incompatible_error(exc) is True

    def test_detects_tool_choice_phrase(self) -> None:
        exc = Exception("Invalid request: tool_choice not allowed for this model")
        assert llm._is_tool_incompatible_error(exc) is True

    def test_detects_unsupported_tool(self) -> None:
        exc = Exception("unsupported parameter: tool")
        assert llm._is_tool_incompatible_error(exc) is True

    def test_ignores_unrelated_error(self) -> None:
        exc = Exception("rate limit exceeded")
        assert llm._is_tool_incompatible_error(exc) is False

    def test_requires_tool_keyword(self) -> None:
        exc = Exception("not support this feature")
        assert llm._is_tool_incompatible_error(exc) is False


class TestStreamTurnToolFallback:
    """stream_turn retries without tools when the model rejects tool_choice: auto."""

    def _chunk(
        self, content: str | None, finish_reason: str | None = None
    ) -> MagicMock:
        chunk = MagicMock()
        chunk.choices[0].delta.content = content
        chunk.choices[0].delta.tool_calls = None
        chunk.choices[0].finish_reason = finish_reason
        return chunk

    def test_retries_without_tools_on_tool_incompatible_error(self) -> None:
        ok_chunks = [self._chunk("Hello"), self._chunk("", finish_reason="stop")]
        call_count = 0

        def fake_completion(**kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise LiteLLMBadRequestError(
                    message=(
                        "This model does not support auto tool, please use "
                        "tool_choice."
                    ),
                    model="qwen",
                    llm_provider="openai",
                )
            return iter(ok_chunks)

        messages: list[Any] = []
        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            output = "".join(
                llm.stream_turn(
                    "sys", messages, {"model": "m", "api_key": "k"}, "tv-key"
                )
            )

        assert call_count == 2
        assert "Hello" in output
        assert "Web search disabled" in output

    def test_retry_call_omits_tools(self) -> None:
        ok_chunks = [self._chunk("OK"), self._chunk("", finish_reason="stop")]
        call_args_list: list[dict[str, Any]] = []

        def fake_completion(**kwargs: Any) -> Any:
            call_args_list.append(kwargs)
            if len(call_args_list) == 1:
                raise LiteLLMBadRequestError(
                    message="does not support auto tool",
                    model="qwen",
                    llm_provider="openai",
                )
            return iter(ok_chunks)

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            list(
                llm.stream_turn(
                    "sys", [], {"model": "m", "api_key": "k"}, "tv-key"
                )
            )

        assert "tools" in call_args_list[0]
        assert "tools" not in call_args_list[1]

    def test_unrelated_bad_request_reraises(self) -> None:
        def fake_completion(**kwargs: Any) -> Any:
            raise LiteLLMBadRequestError(
                message="context window exceeded",
                model="m",
                llm_provider="openai",
            )

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            with pytest.raises(LiteLLMBadRequestError):
                list(
                    llm.stream_turn(
                        "sys", [], {"model": "m", "api_key": "k"}, "tv-key"
                    )
                )

    def test_no_fallback_when_no_tools_configured(self) -> None:
        """Without Tavily, tools=None — error should propagate normally."""
        def fake_completion(**kwargs: Any) -> Any:
            raise LiteLLMBadRequestError(
                message="does not support auto tool",
                model="m",
                llm_provider="openai",
            )

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            with pytest.raises(LiteLLMBadRequestError):
                list(
                    llm.stream_turn(
                        "sys", [], {"model": "m", "api_key": "k"}, None
                    )
                )


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
            "spec4.llm.litellm.completion", return_value=iter(self._chunks())
        ) as mock_llm:
            list(
                llm.stream_turn(
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
            "spec4.llm.litellm.completion", return_value=iter(self._chunks())
        ) as mock_llm:
            list(
                llm.stream_turn(
                    "sys", [], {"model": "m", "api_key": "k"}, None
                )
            )
        assert "response_format" not in mock_llm.call_args[1]

    def test_tools_suppressed_when_response_format_set(self) -> None:
        # Mixing web_search tool calls with structured-output mode is
        # rejected by most providers; stream_turn drops tools on those calls.
        with patch(
            "spec4.llm.litellm.completion", return_value=iter(self._chunks())
        ) as mock_llm:
            list(
                llm.stream_turn(
                    "sys",
                    [],
                    {"model": "m", "api_key": "k"},
                    "tavily-key",
                    response_format={"type": "json_object"},
                )
            )
        assert "tools" not in mock_llm.call_args[1]
        assert mock_llm.call_args[1]["response_format"] == {"type": "json_object"}
