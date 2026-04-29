from __future__ import annotations

from unittest.mock import patch

import pytest

from spec4.agents._image_probe import probe_image_support


class TestProbeImageSupport:
    def test_returns_true_when_supports_vision(self) -> None:
        with patch("spec4.agents._image_probe.litellm.supports_vision", return_value=True):
            assert probe_image_support("claude-sonnet-4-6", "sk-test") is True

    def test_returns_false_when_not_supports_vision(self) -> None:
        with patch("spec4.agents._image_probe.litellm.supports_vision", return_value=False):
            assert probe_image_support("command-r", "sk-test") is False

    def test_returns_false_on_unknown_model(self) -> None:
        with patch(
            "spec4.agents._image_probe.litellm.supports_vision",
            side_effect=Exception("Unknown model"),
        ):
            assert probe_image_support("unknown-model", "sk-test") is False

    def test_api_key_param_accepted(self) -> None:
        with patch("spec4.agents._image_probe.litellm.supports_vision", return_value=True):
            assert probe_image_support("gpt-4o", "sk-test") is True
