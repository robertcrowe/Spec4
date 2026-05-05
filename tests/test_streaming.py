from __future__ import annotations

import json
from typing import Any

import pytest

from spec4.streaming import _format_error


class FakeRateLimitError(Exception):
    pass


class FakeAPIError(Exception):
    pass


class FakeBadRequestError(Exception):
    pass


class FakeAuthenticationError(Exception):
    pass


class FakeContextWindowExceededError(Exception):
    pass


class FakeServiceUnavailableError(Exception):
    pass


class FakeAPIConnectionError(Exception):
    pass


def _wrap(provider_label: str, payload: dict[str, Any]) -> str:
    """Mimic litellm's `<ProviderException> - b'{...}'` envelope."""
    return f"{provider_label} - b'{json.dumps(payload)}'"


GOOGLE_VERTEX_PAYLOAD: dict[str, Any] = {
    "error": {
        "code": 429,
        "message": (
            "You exceeded your current quota, please check your plan "
            "and billing details. For more information on this error, "
            "head to: https://ai.google.dev/gemini-api/docs/rate-limits.\n"
            " Quota exceeded for metric: foo, limit: 0, model: gemini-3.1-pro\n"
            " Quota exceeded for metric: foo, limit: 0, model: gemini-3.1-pro\n"
            " Please retry in 42.369378153s."
        ),
        "status": "RESOURCE_EXHAUSTED",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.Help",
                "links": {
                    "description": "Learn more",
                    "url": "https://ai.google.dev/gemini-api/docs/rate-limits",
                },
            },
            {
                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                "retryDelay": "42s",
            },
        ],
    }
}

GOOGLE_VERTEX_RATE_LIMIT = (
    "litellm.RateLimitError: litellm.RateLimitError: "
    + _wrap("vertex_ai_betaException", GOOGLE_VERTEX_PAYLOAD)
)


class TestGoogleVertexRateLimit:
    @pytest.fixture
    def out(self) -> str:
        return _format_error(FakeRateLimitError(GOOGLE_VERTEX_RATE_LIMIT))

    def test_heading_includes_class_and_status(self, out: str) -> None:
        assert out.startswith("**Error: FakeRateLimitError**")
        assert "HTTP 429" in out
        assert "RESOURCE_EXHAUSTED" in out

    def test_body_contains_human_message(self, out: str) -> None:
        assert "You exceeded your current quota" in out

    def test_body_dedupes_consecutive_identical_quota_lines(self, out: str) -> None:
        assert out.count("Quota exceeded for metric: foo") == 1

    def test_retry_bullet_present(self, out: str) -> None:
        assert "- Retry after: 42s" in out

    def test_no_giant_json_fence_when_message_extracted(self, out: str) -> None:
        assert "```json" not in out
        assert "@type" not in out

    def test_doc_link_skipped_when_already_in_prose(self, out: str) -> None:
        assert out.count("https://ai.google.dev/gemini-api/docs/rate-limits") == 1

    def test_source_bullet_strips_doubled_prefix(self, out: str) -> None:
        assert "- Source: vertex_ai_betaException" in out
        assert "litellm.RateLimitError: litellm.RateLimitError" not in out


class TestOpenAIShape:
    def test_extracts_message_and_type(self) -> None:
        msg = _wrap(
            "OpenAIException",
            {
                "error": {
                    "message": "Invalid API key.",
                    "type": "invalid_request_error",
                    "code": "invalid_api_key",
                }
            },
        )
        out = _format_error(FakeAPIError(msg))
        assert "**Error: FakeAPIError**" in out
        assert "invalid_request_error" in out
        assert "HTTP invalid_api_key" in out
        assert "Invalid API key." in out
        assert "```json" not in out


class TestAnthropicShape:
    def test_extracts_nested_message(self) -> None:
        msg = _wrap(
            "AnthropicException",
            {
                "type": "error",
                "error": {
                    "type": "rate_limit_error",
                    "message": "Rate limit reached for input tokens.",
                },
            },
        )
        out = _format_error(FakeRateLimitError(msg))
        assert "Rate limit reached for input tokens." in out
        assert "rate_limit_error" in out


class TestCohereStyle:
    def test_extracts_top_level_message(self) -> None:
        msg = _wrap("CohereException", {"message": "too many tokens"})
        out = _format_error(FakeAPIError(msg))
        assert "too many tokens" in out


class TestNoJSON:
    def test_plain_exception_falls_back_cleanly(self) -> None:
        out = _format_error(ValueError("connection reset by peer"))
        assert out.startswith("**Error: ValueError**")
        assert "connection reset by peer" in out
        assert "```" not in out

    def test_empty_exception_does_not_crash(self) -> None:
        out = _format_error(ValueError())
        assert out.startswith("**Error: ValueError**")


class TestUnparseableStructured:
    def test_keeps_json_dump_when_no_message_field(self) -> None:
        msg = _wrap("Weird", {"foo": "bar", "baz": 1})
        out = _format_error(Exception(msg))
        assert "```json" in out
        assert '"foo": "bar"' in out


# ---------------------------------------------------------------------------
# Non-rate-limit error categories — confirm the formatter is shape-agnostic
# and never injects rate-limit-specific decorations (Retry after, RetryInfo,
# Help links) when the underlying error doesn't carry them.
# ---------------------------------------------------------------------------


class TestContextWindowExceeded:
    """OpenAI-style context-length-exceeded error."""

    def test_shows_message_and_code_without_retry_bullet(self) -> None:
        msg = _wrap(
            "OpenAIException",
            {
                "error": {
                    "message": (
                        "This model's maximum context length is 128000 tokens, "
                        "however you requested 142318 tokens. "
                        "Please reduce your prompt."
                    ),
                    "type": "invalid_request_error",
                    "code": "context_length_exceeded",
                    "param": "messages",
                }
            },
        )
        out = _format_error(FakeContextWindowExceededError(msg))
        assert "**Error: FakeContextWindowExceededError**" in out
        assert "HTTP context_length_exceeded" in out
        assert "invalid_request_error" in out
        assert "maximum context length is 128000 tokens" in out
        # No retry / docs / source-style decorations apply here.
        assert "Retry after" not in out
        assert "Docs:" not in out
        assert "```json" not in out


class TestAnthropicInvalidRequest:
    """Anthropic-shape error that is *not* rate-limited."""

    def test_invalid_request_with_no_retry_bullet(self) -> None:
        msg = _wrap(
            "AnthropicException",
            {
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "messages: at least one message is required",
                },
            },
        )
        out = _format_error(FakeBadRequestError(msg))
        assert "**Error: FakeBadRequestError**" in out
        assert "invalid_request_error" in out
        assert "messages: at least one message is required" in out
        assert "Retry after" not in out


class TestServerError:
    """5xx / transient infra error from any provider."""

    def test_500_renders_message_and_status_only(self) -> None:
        msg = _wrap(
            "OpenAIException",
            {
                "error": {
                    "message": "The server had an error while processing your request.",
                    "type": "server_error",
                    "code": 500,
                }
            },
        )
        out = _format_error(FakeServiceUnavailableError(msg))
        assert "**Error: FakeServiceUnavailableError**" in out
        assert "HTTP 500" in out
        assert "server_error" in out
        assert "had an error while processing" in out
        assert "Retry after" not in out


class TestRetryInProseTriggers:
    """A non-rate-limit error mentioning retry-in-prose still surfaces it."""

    def test_retry_phrase_in_prose_yields_bullet(self) -> None:
        msg = _wrap(
            "MistralException",
            {
                "message": (
                    "Service is temporarily unavailable. "
                    "Please retry in 5 seconds."
                ),
            },
        )
        out = _format_error(FakeServiceUnavailableError(msg))
        assert "Service is temporarily unavailable" in out
        assert "- Retry after: 5 seconds" in out


class TestAuthErrorNoBody:
    """litellm raises some errors before hitting the wire — no JSON envelope at all."""

    def test_plain_authentication_error_renders_cleanly(self) -> None:
        out = _format_error(
            FakeAuthenticationError(
                "AuthenticationError: anthropic API key is invalid"
            )
        )
        assert out.startswith("**Error: FakeAuthenticationError**")
        assert "anthropic API key is invalid" in out
        # No body to parse → no JSON fence, no decoration bullets.
        assert "```" not in out
        assert "Retry after" not in out


class TestNetworkError:
    """A urllib/httpx style connection error wrapped by litellm."""

    def test_connection_error_renders_message(self) -> None:
        out = _format_error(
            FakeAPIConnectionError(
                "APIConnectionError: Connection error.  HTTPSConnectionPool"
                "(host='api.openai.com', port=443): Max retries exceeded"
            )
        )
        assert out.startswith("**Error: FakeAPIConnectionError**")
        assert "Max retries exceeded" in out
        assert "```" not in out


class TestGoogleNonRateLimit:
    """Google/Vertex error envelope WITHOUT RetryInfo or Help details — confirms
    the rate-limit-specific bullets only appear when those fields are present.
    """

    def test_invalid_argument_no_retry_no_docs(self) -> None:
        msg = _wrap(
            "vertex_ai_betaException",
            {
                "error": {
                    "code": 400,
                    "message": "Request contains an invalid argument.",
                    "status": "INVALID_ARGUMENT",
                }
            },
        )
        out = _format_error(FakeBadRequestError(msg))
        assert "**Error: FakeBadRequestError**" in out
        assert "HTTP 400" in out
        assert "INVALID_ARGUMENT" in out
        assert "Request contains an invalid argument." in out
        assert "Retry after" not in out
        assert "Docs:" not in out
