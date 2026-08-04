"""Tests for the Reference Verifier utility."""

from __future__ import annotations

from unittest.mock import patch

from spec4.agentifier.reference_verifier import (
    enrich_references,
    extract_references_from_spec,
    is_url_present,
    lookup_reference_url,
)

# ---------------------------------------------------------------------------
# is_url_present
# ---------------------------------------------------------------------------


class TestIsUrlPresent:
    def test_detects_https_url(self) -> None:
        assert is_url_present("See docs at https://example.com") is True

    def test_detects_http_url(self) -> None:
        assert is_url_present("http://example.com/path") is True

    def test_returns_false_for_plain_text(self) -> None:
        assert is_url_present("Anthropic Tool Use") is False

    def test_returns_false_for_empty(self) -> None:
        assert is_url_present("") is False


# ---------------------------------------------------------------------------
# lookup_reference_url
# ---------------------------------------------------------------------------


class TestLookupReferenceUrl:
    def test_returns_url_from_search(self) -> None:
        with patch("spec4.llm.search") as mock_search:
            mock_search.return_value = (
                "Result: Anthropic tool use docs at https://docs.anthropic.com/tool-use. "
                "Build powerful AI tools."
            )
            url = lookup_reference_url("Anthropic Tool Use", "tvly-test")
        assert url is not None
        assert "anthropic.com" in url

    def test_returns_none_when_search_fails(self) -> None:
        with patch("spec4.llm.search") as mock_search:
            mock_search.return_value = "Search failed: connection timeout"
            url = lookup_reference_url("Some Reference", "tvly-test")
        assert url is None

    def test_returns_none_when_no_urls_in_result(self) -> None:
        with patch("spec4.llm.search") as mock_search:
            mock_search.return_value = "This result contains no URLs at all"
            url = lookup_reference_url("Some Reference", "tvly-test")
        assert url is None

    def test_prefers_docs_url_over_generic(self) -> None:
        with patch("spec4.llm.search") as mock_search:
            mock_search.return_value = (
                "Visit https://example.com first. "
                "Official docs: https://docs.example.com/reference"
            )
            url = lookup_reference_url("Example Reference", "tvly-test")
        assert url is not None
        assert "docs.example.com" in url

    def test_strips_trailing_punctuation_from_url(self) -> None:
        with patch("spec4.llm.search") as mock_search:
            mock_search.return_value = "See https://example.com/docs."
            url = lookup_reference_url("Example", "tvly-test")
        assert url is not None
        assert not url.endswith(".")

    def test_handles_exception_gracefully(self) -> None:
        with patch(
            "spec4.llm.search",
            side_effect=RuntimeError("network error"),
        ):
            url = lookup_reference_url("Example", "tvly-test")
        assert url is None


# ---------------------------------------------------------------------------
# enrich_references
# ---------------------------------------------------------------------------


class TestEnrichReferences:
    def test_adds_url_to_bare_reference(self) -> None:
        with patch("spec4.llm.search") as mock_search:
            mock_search.return_value = (
                "Official reference: https://docs.example.com/api"
            )
            result = enrich_references(["OpenAI Structured Outputs"], "tvly-test")
        assert len(result) == 1
        assert "https://docs.example.com/api" in result[0]

    def test_leaves_existing_url_unchanged(self) -> None:
        ref = "Anthropic docs (https://docs.anthropic.com/en/docs)"
        result = enrich_references([ref], "tvly-test")
        assert result == [ref]

    def test_returns_unchanged_when_no_tavily_key(self) -> None:
        refs = ["Some Reference Without URL"]
        result = enrich_references(refs, None)
        assert result == refs

    def test_handles_empty_list(self) -> None:
        result = enrich_references([], "tvly-test")
        assert result == []

    def test_handles_search_failure(self) -> None:
        with patch("spec4.llm.search") as mock_search:
            mock_search.return_value = "Search failed: timeout"
            result = enrich_references(["Some Reference"], "tvly-test")
        assert result == ["Some Reference"]

    def test_preserves_list_length(self) -> None:
        refs = [
            "Reference A (https://a.example.com)",
            "Reference B",
            "Reference C (https://c.example.com)",
        ]
        with patch("spec4.llm.search") as mock_search:
            mock_search.return_value = "https://b.example.com/docs"
            result = enrich_references(refs, "tvly-test")
        assert len(result) == 3

    def test_does_not_mutate_input(self) -> None:
        refs = ["Reference A", "Reference B"]
        original = list(refs)
        with patch("spec4.llm.search") as mock_search:
            mock_search.return_value = "https://example.com"
            enrich_references(refs, "tvly-test")
        assert refs == original

    def test_mixed_refs_enriches_only_bare_ones(self) -> None:
        refs = [
            "Has URL (https://example.com)",
            "Bare Reference",
        ]
        with patch("spec4.llm.search") as mock_search:
            mock_search.return_value = "Found at https://found.example.com/docs"
            result = enrich_references(refs, "tvly-test")
        assert result[0] == refs[0]  # URL-bearing ref unchanged
        assert "https://found.example.com/docs" in result[1]  # bare one enriched


# ---------------------------------------------------------------------------
# extract_references_from_spec
# ---------------------------------------------------------------------------


class TestExtractReferencesFromSpec:
    def test_returns_references_list(self) -> None:
        spec = {"references": ["Ref A", "Ref B"]}
        assert extract_references_from_spec(spec) == ["Ref A", "Ref B"]

    def test_returns_empty_for_missing_key(self) -> None:
        assert extract_references_from_spec({}) == []

    def test_returns_empty_for_non_list(self) -> None:
        assert extract_references_from_spec({"references": "not a list"}) == []

    def test_filters_empty_strings(self) -> None:
        spec = {"references": ["Ref A", "", "Ref B"]}
        result = extract_references_from_spec(spec)
        assert "" not in result
        assert len(result) == 2
