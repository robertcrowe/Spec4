from __future__ import annotations

from unittest.mock import MagicMock, patch

from spec4.agents._image_probe import probe_image_support

_PATCH = "spec4.agents._image_probe.litellm.completion"


class TestProbeImageSupport:
    def test_returns_true_when_completion_succeeds(self) -> None:
        with patch(_PATCH, return_value=MagicMock()):
            assert probe_image_support("claude-sonnet-4-6", "sk-test") is True

    def test_returns_false_when_completion_raises(self) -> None:
        with patch(_PATCH, side_effect=Exception("vision not supported")):
            assert probe_image_support("command-r", "sk-test") is False

    def test_returns_false_on_unknown_model(self) -> None:
        with patch(_PATCH, side_effect=Exception("Unknown model")):
            assert probe_image_support("unknown-model", "sk-test") is False

    def test_api_base_passed_through(self) -> None:
        with patch(_PATCH, return_value=MagicMock()) as mock_completion:
            probe_image_support(
                "openai/llama-3", "sk-test", api_base="https://example.com/v1/"
            )
            call_kwargs = mock_completion.call_args[1]
            assert call_kwargs["api_base"] == "https://example.com/v1/"

    def test_api_base_omitted_when_none(self) -> None:
        with patch(_PATCH, return_value=MagicMock()) as mock_completion:
            probe_image_support("gpt-4o", "sk-test")
            call_kwargs = mock_completion.call_args[1]
            assert "api_base" not in call_kwargs

    def test_sends_image_in_message(self) -> None:
        with patch(_PATCH, return_value=MagicMock()) as mock_completion:
            probe_image_support("gpt-4o", "sk-test")
            messages = mock_completion.call_args[1]["messages"]
            content = messages[0]["content"]
            types = [part["type"] for part in content]
            assert "image_url" in types
            assert "text" in types

    def test_uses_low_max_tokens(self) -> None:
        with patch(_PATCH, return_value=MagicMock()) as mock_completion:
            probe_image_support("gpt-4o", "sk-test")
            assert mock_completion.call_args[1]["max_tokens"] <= 10
