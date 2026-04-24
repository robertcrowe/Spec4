import json
from unittest.mock import MagicMock, patch

from spec4 import tavily_mcp


class TestUrlBuilder:
    def test_contains_api_key(self):
        assert "my-key" in tavily_mcp._url("my-key")

    def test_is_https(self):
        assert tavily_mcp._url("key").startswith("https://")


class TestWebSearchToolSpec:
    def test_type_is_function(self):
        assert tavily_mcp.WEB_SEARCH_TOOL["type"] == "function"

    def test_name_is_web_search(self):
        assert tavily_mcp.WEB_SEARCH_TOOL["function"]["name"] == "web_search"

    def test_has_query_parameter(self):
        params = tavily_mcp.WEB_SEARCH_TOOL["function"]["parameters"]
        assert "query" in params["properties"]
        assert "query" in params["required"]


class TestValidate:
    def test_success_returns_true_with_tools(self):
        with patch("spec4.tavily_mcp._run_async", return_value=["search"]):
            ok, tools, err = tavily_mcp.validate("valid-key")
        assert ok is True
        assert tools == ["search"]
        assert err == ""

    def test_failure_returns_false_with_message(self):
        with patch("spec4.tavily_mcp._run_async", side_effect=Exception("Connection refused")):
            ok, tools, err = tavily_mcp.validate("bad-key")
        assert ok is False
        assert tools == []
        assert "Connection refused" in err


class TestSearch:
    def test_returns_result_text(self):
        with patch("spec4.tavily_mcp._run_async", return_value="Search results here"):
            assert tavily_mcp.search("query", "key") == "Search results here"

    def test_exception_returns_error_string(self):
        with patch("spec4.tavily_mcp._run_async", side_effect=Exception("timeout")):
            result = tavily_mcp.search("query", "key")
        assert result.startswith("Search failed:")
        assert "timeout" in result


class TestStreamTurn:
    def _chunk(self, content, finish_reason=None, tool_calls=None):
        chunk = MagicMock()
        chunk.choices[0].delta.content = content
        chunk.choices[0].delta.tool_calls = tool_calls
        chunk.choices[0].finish_reason = finish_reason
        return chunk

    def test_yields_text_chunks(self):
        chunks = [self._chunk("Hello "), self._chunk("world"), self._chunk("", finish_reason="stop")]
        messages = []
        with patch("spec4.tavily_mcp.litellm.completion", return_value=iter(chunks)):
            output = "".join(tavily_mcp.stream_turn("sys", messages, {"model": "m", "api_key": "k"}, None))
        assert output == "Hello world"

    def test_appends_assistant_message(self):
        chunks = [self._chunk("Hi"), self._chunk("", finish_reason="stop")]
        messages = []
        with patch("spec4.tavily_mcp.litellm.completion", return_value=iter(chunks)):
            list(tavily_mcp.stream_turn("sys", messages, {"model": "m", "api_key": "k"}, None))
        assert messages[-1] == {"role": "assistant", "content": "Hi"}

    def test_no_tools_kwarg_when_no_tavily_key(self):
        chunks = [self._chunk("Hi"), self._chunk("", finish_reason="stop")]
        with patch("spec4.tavily_mcp.litellm.completion", return_value=iter(chunks)) as mock_llm:
            list(tavily_mcp.stream_turn("sys", [], {"model": "m", "api_key": "k"}, None))
        assert "tools" not in mock_llm.call_args[1]

    def test_tools_kwarg_present_when_tavily_key_given(self):
        chunks = [self._chunk("Hi"), self._chunk("", finish_reason="stop")]
        with patch("spec4.tavily_mcp.litellm.completion", return_value=iter(chunks)) as mock_llm:
            list(tavily_mcp.stream_turn("sys", [], {"model": "m", "api_key": "k"}, "tavily-key"))
        assert mock_llm.call_args[1]["tools"] == [tavily_mcp.WEB_SEARCH_TOOL]

    def test_system_prompt_prepended(self):
        chunks = [self._chunk("Hi"), self._chunk("", finish_reason="stop")]
        messages = [{"role": "user", "content": "Hello"}]
        with patch("spec4.tavily_mcp.litellm.completion", return_value=iter(chunks)) as mock_llm:
            list(tavily_mcp.stream_turn("my-system", messages, {"model": "m", "api_key": "k"}, None))
        sent = mock_llm.call_args[1]["messages"]
        assert sent[0] == {"role": "system", "content": "my-system"}
        assert sent[1] == {"role": "user", "content": "Hello"}

    def test_tool_call_triggers_search_and_loops(self):
        tc = MagicMock()
        tc.index = 0
        tc.id = "call-1"
        tc.function.name = "web_search"
        tc.function.arguments = json.dumps({"query": "test search"})

        tool_chunk = self._chunk(None, tool_calls=[tc])
        call_count = 0

        def fake_completion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return iter([tool_chunk, self._chunk("", finish_reason="stop")])
            return iter([self._chunk("Answer"), self._chunk("", finish_reason="stop")])

        messages = []
        with patch("spec4.tavily_mcp.litellm.completion", side_effect=fake_completion):
            with patch("spec4.tavily_mcp.search", return_value="search results") as mock_search:
                output = "".join(
                    tavily_mcp.stream_turn("sys", messages, {"model": "m", "api_key": "k"}, "tv-key")
                )

        mock_search.assert_called_once_with("test search", "tv-key")
        assert "Answer" in output
        assert call_count == 2

    def test_tool_call_yields_search_indicator(self):
        tc = MagicMock()
        tc.index = 0
        tc.id = "call-1"
        tc.function.name = "web_search"
        tc.function.arguments = json.dumps({"query": "my query"})

        call_count = 0

        def fake_completion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return iter([self._chunk(None, tool_calls=[tc]), self._chunk("", finish_reason="stop")])
            return iter([self._chunk("Done"), self._chunk("", finish_reason="stop")])

        with patch("spec4.tavily_mcp.litellm.completion", side_effect=fake_completion):
            with patch("spec4.tavily_mcp.search", return_value="results"):
                chunks = list(
                    tavily_mcp.stream_turn("sys", [], {"model": "m", "api_key": "k"}, "tv-key")
                )

        combined = "".join(chunks)
        assert "my query" in combined
