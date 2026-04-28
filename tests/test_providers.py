import http.client
import urllib.error
from typing import Any
from unittest.mock import patch

from spec4.providers import PROVIDERS, list_models


class TestProvidersRegistry:
    def test_five_providers(self) -> None:
        assert len(PROVIDERS) == 5

    def test_provider_keys(self) -> None:
        assert set(PROVIDERS.keys()) == {
            "openai",
            "anthropic",
            "gemini",
            "cohere",
            "mistral",
        }

    def test_each_provider_has_required_keys(self) -> None:
        for key, info in PROVIDERS.items():
            assert "label" in info, f"{key} missing 'label'"
            assert "env_var" in info, f"{key} missing 'env_var'"
            assert "models" in info, f"{key} missing 'models'"
            assert isinstance(info["models"], list), f"{key} 'models' should be a list"
            assert len(info["models"]) > 0, f"{key} should have at least one model"

    def test_labels_are_strings(self) -> None:
        for key, info in PROVIDERS.items():
            assert isinstance(info["label"], str) and info["label"], (
                f"{key} label should be non-empty string"
            )

    def test_env_var_format(self) -> None:
        for key, info in PROVIDERS.items():
            assert "_API_KEY" in info["env_var"], (
                f"{key} env_var should contain _API_KEY"
            )


class TestListModels:
    def _patch_fetch(self, models: list[str]) -> Any:
        return patch("spec4.providers._fetch_models", return_value=models)

    def test_returns_fetched_models(self) -> None:
        with self._patch_fetch(["gpt-4o", "gpt-4o-mini"]):
            models, err = list_models("openai", "sk-test")
        assert models == ["gpt-4o", "gpt-4o-mini"]
        assert err == ""

    def test_falls_back_to_hardcoded_when_empty(self) -> None:
        with self._patch_fetch([]):
            models, err = list_models("openai", "sk-test")
        assert models == PROVIDERS["openai"]["models"]
        assert err == ""

    def test_http_error_returns_empty_and_message(self) -> None:
        hdrs = http.client.HTTPMessage()
        exc = urllib.error.HTTPError("", 401, "Unauthorized", hdrs, None)
        with patch("spec4.providers._fetch_models", side_effect=exc):
            models, err = list_models("openai", "bad-key")
        assert models == []
        assert "401" in err

    def test_network_error_returns_empty_and_message(self) -> None:
        with patch(
            "spec4.providers._fetch_models", side_effect=Exception("connection refused")
        ):
            models, err = list_models("anthropic", "bad-key")
        assert models == []
        assert "connection refused" in err

    def test_openai_filters_chat_models(self) -> None:
        raw = {
            "data": [
                {"id": "gpt-4o"},
                {"id": "gpt-4o-mini"},
                {"id": "text-embedding-ada-002"},
                {"id": "whisper-1"},
                {"id": "o1-preview"},
            ]
        }
        with patch("spec4.providers._json_get", return_value=raw):
            models, _ = list_models("openai", "sk-test")
        assert "gpt-4o" in models
        assert "gpt-4o-mini" in models
        assert "o1-preview" in models
        assert "text-embedding-ada-002" not in models
        assert "whisper-1" not in models

    def test_gemini_adds_prefix_and_filters_capability(self) -> None:
        raw = {
            "models": [
                {
                    "name": "models/gemini-1.5-pro",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/embedding-001",
                    "supportedGenerationMethods": ["embedContent"],
                },
            ]
        }
        with patch("spec4.providers._json_get", return_value=raw):
            models, _ = list_models("gemini", "key")
        assert models == ["gemini/gemini-1.5-pro"]

    def test_mistral_excludes_embed_models(self) -> None:
        raw = {
            "data": [
                {"id": "mistral-large-latest"},
                {"id": "mistral-embed"},
            ]
        }
        with patch("spec4.providers._json_get", return_value=raw):
            models, _ = list_models("mistral", "key")
        assert "mistral/mistral-large-latest" in models
        assert "mistral/mistral-embed" not in models
