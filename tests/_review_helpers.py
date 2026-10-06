"""Builders for the two shapes a CodeScanner review takes (schema_version 2).

``review_block(**fields)`` is what the LLM emits — ``{"review": {...}}`` —
and what ``validate_review_block`` / ``_extract_and_validate_review`` read.
``review_envelope(**fields)`` is what is stored in ``session["code_review"]``
and written to ``code_review.json`` — ``{"code_review": {"schema_version",
"scan", "review"}}`` — and what every consumer unwraps by path.

``is_software_project`` defaults to ``True`` in both; pass it explicitly to
build the empty-project shape. ``schema_version`` and ``scan`` on the
envelope are overridable for staleness fixtures.
"""

from __future__ import annotations

import json
from typing import Any

from spec4.agents._code_review_schema import CODE_REVIEW_SCHEMA_VERSION


def review_fields(**fields: Any) -> dict[str, Any]:
    """The bare ``review`` dict: ``is_software_project`` plus ``fields``."""
    return {"is_software_project": True, **fields}


def review_block(**fields: Any) -> dict[str, Any]:
    """The LLM-emitted shape."""
    return {"review": review_fields(**fields)}


def review_envelope(
    *,
    schema_version: int = CODE_REVIEW_SCHEMA_VERSION,
    scan: dict[str, Any] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """The stored shape."""
    return {
        "code_review": {
            "schema_version": schema_version,
            "scan": {} if scan is None else scan,
            "review": review_fields(**fields),
        }
    }


def review_block_text(**fields: Any) -> str:
    """``review_block`` as the fenced JSON an assistant turn would carry."""
    return f"```json\n{json.dumps(review_block(**fields))}\n```"
