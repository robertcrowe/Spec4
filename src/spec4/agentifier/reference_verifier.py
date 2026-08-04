"""Reference Verifier: resolves reference strings to canonical documentation URLs.

Shared utility callable from any Spec4 sub-agent that mentions a pattern,
framework, or technical standard. Searches the developer's configured web
search provider for canonical URLs and returns an enriched reference list.

The sub-agent never talks to the user directly — the orchestrator presents
candidates to the user for confirmation via its own conversational surface.

Usage::

    from spec4.agentifier.reference_verifier import enrich_references

    enriched = enrich_references(
        ["Anthropic — Building Effective Agents", "OpenAI Structured Outputs"],
        search_config=SearchConfig("tavily", "tvly-..."),
    )
    # enriched[0] may now contain the canonical URL appended in parentheses
"""

from __future__ import annotations

import re
from typing import Any

_URL_PATTERN = re.compile(r"https?://[^\s\)\"\']+")


def is_url_present(text: str) -> bool:
    """Return True if ``text`` already contains an http(s) URL."""
    return bool(_URL_PATTERN.search(text))


def lookup_reference_url(reference_text: str, search_config: Any) -> str | None:
    """Search for the canonical URL of a reference string.

    Returns the first HTTPS URL found in the search result, or None if the
    search fails or returns no URLs.

    Args:
        reference_text: A human-readable reference, e.g. "Anthropic Tool Use".
        search_config: A `websearch.SearchConfig` (a bare Tavily key also works).

    Returns:
        A URL string, or None.
    """
    from spec4 import llm  # local import — avoids circular deps and import cost

    query = f"official documentation {reference_text}"
    try:
        result = llm.search(query, search_config)
    except Exception:
        return None

    if not result or result.startswith("Search failed:") or result.startswith("No search"):
        return None

    urls = _URL_PATTERN.findall(result)
    # Prefer docs/reference URLs over generic landing pages
    for url in urls:
        lower = url.lower()
        if any(kw in lower for kw in ("docs", "reference", "guide", "spec", "api")):
            return url.rstrip(".,;)")
    return urls[0].rstrip(".,;)") if urls else None


def enrich_references(
    references: list[str],
    search_config: Any,
) -> list[str]:
    """Add canonical URLs to references that don't already contain one.

    Searches the configured provider for each reference string that lacks an
    embedded URL.
    Returns a new list; does not mutate the input.

    Args:
        references: List of reference strings (may already contain URLs).
        search_config: The web-search provider and key. When None the list is
            returned unchanged.

    Returns:
        A new list of the same length with URLs appended where found.
    """
    if not search_config or not references:
        return list(references)

    enriched: list[str] = []
    for ref in references:
        if is_url_present(ref):
            enriched.append(ref)
        else:
            url = lookup_reference_url(ref, search_config)
            enriched.append(f"{ref} ({url})" if url else ref)
    return enriched


def extract_references_from_spec(spec: dict[str, Any]) -> list[str]:
    """Return the references list from a spec dict, or [] if absent."""
    refs = spec.get("references")
    if isinstance(refs, list):
        return [str(r) for r in refs if r]
    return []
