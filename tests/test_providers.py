import http.client
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch

from spec4.providers import PROVIDERS, list_models


class TestProvidersRegistry:
    def test_seven_providers(self) -> None:
        assert len(PROVIDERS) == 7

    def test_provider_keys(self) -> None:
        assert set(PROVIDERS.keys()) == {
            "openai",
            "anthropic",
            "gemini",
            "cohere",
            "mistral",
            "nebius",
            "bedrock",
        }

    def test_each_provider_has_required_keys(self) -> None:
        for key, info in PROVIDERS.items():
            assert "label" in info, f"{key} missing 'label'"
            assert "env_var" in info, f"{key} missing 'env_var'"

    def test_labels_are_strings(self) -> None:
        for key, info in PROVIDERS.items():
            assert isinstance(info["label"], str) and info["label"], (
                f"{key} label should be non-empty string"
            )

    def test_env_var_format(self) -> None:
        for key, info in PROVIDERS.items():
            if key == "bedrock":
                assert info["env_var"] == "AWS_ACCESS_KEY_ID"
            else:
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

    def test_returns_empty_when_api_returns_nothing(self) -> None:
        with self._patch_fetch([]):
            models, err = list_models("openai", "sk-test")
        assert models == []
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

    def test_models_are_sorted(self) -> None:
        raw = {"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-3.5-turbo"}, {"id": "gpt-4o"}]}
        with patch("spec4.providers._json_get", return_value=raw):
            models, _ = list_models("openai", "sk-test")
        assert models == sorted(models)

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

    def test_bedrock_includes_on_demand_models(self) -> None:
        fake_response = {
            "modelSummaries": [
                {
                    "modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0",
                    "inferenceTypesSupported": ["ON_DEMAND"],
                },
                {
                    "modelId": "anthropic.claude-3-opus-20240229-v1:0",
                    "inferenceTypesSupported": ["PROVISIONED"],
                },
            ]
        }
        mock_client = MagicMock()
        mock_client.list_foundation_models.return_value = fake_response
        with patch("spec4.providers.boto3.client", return_value=mock_client):
            models, err = list_models("bedrock", "")
        assert "bedrock/converse/anthropic.claude-3-5-sonnet-20241022-v2:0" in models
        assert "bedrock/converse/anthropic.claude-3-opus-20240229-v1:0" not in models
        assert err == ""

    def test_bedrock_new_api_key_uses_bearer_token(self) -> None:
        fake_response = {
            "modelSummaries": [
                {"modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0", "inferenceTypesSupported": ["ON_DEMAND"]},
            ]
        }
        with patch("spec4.providers._json_get", return_value=fake_response) as mock_get:
            models, err = list_models("bedrock", "bdak_mykey:us-east-1")
        url, headers = mock_get.call_args[0]
        assert "bedrock.us-east-1.amazonaws.com" in url
        assert headers["Authorization"] == "Bearer bdak_mykey"
        assert "bedrock/converse/anthropic.claude-3-5-sonnet-20241022-v2:0" in models
        assert err == ""

    def test_bedrock_iam_key_uses_boto3(self) -> None:
        mock_client = MagicMock()
        mock_client.list_foundation_models.return_value = {"modelSummaries": []}
        with patch("spec4.providers.boto3.client", return_value=mock_client) as mock_boto:
            list_models("bedrock", "AKIAKEY:mysecret:eu-west-1")
        call_kwargs = mock_boto.call_args[1]
        assert call_kwargs["aws_access_key_id"] == "AKIAKEY"
        assert call_kwargs["aws_secret_access_key"] == "mysecret"
        assert call_kwargs["region_name"] == "eu-west-1"

    def test_bedrock_falls_back_to_hardcoded_on_api_error(self) -> None:
        mock_client = MagicMock()
        mock_client.list_foundation_models.side_effect = Exception("no credentials")
        with patch("spec4.providers.boto3.client", return_value=mock_client):
            models, err = list_models("bedrock", "")
        assert models == []
        assert "no credentials" in err
