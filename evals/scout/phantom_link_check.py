"""Layer-1 phantom-link checker for the Scout relevance signal (dev tooling).

A deterministic, no-LLM integrity check on Scout's ``linked_vision_features``.
A *phantom link* is a candidate that cites a vision feature name which does not
exist in the vision — the crudest form of confabulation, catchable for free by
set membership against the canonical feature-name extractor.

This is development / evaluation tooling. It does NOT run inside the Agentifier
pipeline; it is invoked by the Scout probe when tuning Scout.

Semantics
---------
- Only *non-empty* ``linked_vision_features`` are checked. An empty list is
  expected — cross-cutting concerns, and the Pass-2 "adjacent" candidates that
  are not drawn from the vision — and is never a phantom.
- A link is CLEAN if it matches a real feature name exactly.
- A link is a NEAR-MISS if it matches a real feature only after normalization
  (case / whitespace / separator drift). That is a formatting bug, not
  confabulation, so it is reported separately and never counted as a phantom.
- A link is a PHANTOM if it matches no real feature name, even normalized.

Feature-name truth is resolved from the vision *as Scout receives it* (see
``_resolve_feature_names``), reusing ``spec4.agents.brainstormer._feature_names``
for the actual entry parsing so the check uses exactly the same feature universe
as the rest of the system and stays correct if the vision schema evolves.

The checker is provenance-agnostic: it takes a flat candidate list. When the
two-pass Scout emits provenance, the probe can slice reports/summary by pass
(phantom links are a Pass-1 concern; Pass-2 candidates are expected to have empty
links), but nothing here needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from spec4.agents.brainstormer import _feature_names


def _normalize(name: str) -> str:
    """Lowercase; collapse any run of non-alphanumerics to a single space.

    Makes ``AI_Recs``, ``ai recs`` and ``AI-Recs`` compare equal for near-miss
    detection, while keeping genuinely different names distinct.
    """
    out: list[str] = []
    prev_sep = False
    for ch in name.strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_sep = False
        elif not prev_sep:
            out.append(" ")
            prev_sep = True
    return "".join(out).strip()


def _resolve_feature_names(vision: dict[str, Any]) -> list[str]:
    """Feature names from the vision *as Scout actually receives it*.

    ``_feature_names`` only parses the full envelope
    (``vision_statement.vision.key_features_mvp`` or
    ``vision_statement.key_features_mvp``). But Scout is fed flatter dicts:

    - pipeline: ``{"name": ..., "vision": {"key_features_mvp": [...]}}``
      (``session["vision_statement"]``, the envelope already unwrapped)
    - probe:    ``{"purpose": ..., "key_features_mvp": [...]}``

    Try the canonical extractor first; if it finds nothing, re-wrap the flatter
    shapes so the *same* single-key-dict / bare-string parsing applies — no
    duplicated logic, so the check can never disagree with the framework about
    what a feature name is.
    """
    if not isinstance(vision, dict):
        return []
    names = _feature_names(vision)
    if names:
        return names
    for container in (vision.get("vision"), vision):
        if isinstance(container, dict) and isinstance(
            container.get("key_features_mvp"), list
        ):
            return _feature_names({"vision_statement": {"vision": container}})
    return []


def _extract(candidate: Any) -> tuple[str, list[str]]:
    """Return (name, linked_vision_features) from a Candidate object or a dict."""
    if isinstance(candidate, dict):
        name = str(candidate.get("name", ""))
        links = candidate.get("linked_vision_features") or []
    else:
        name = str(getattr(candidate, "name", ""))
        links = getattr(candidate, "linked_vision_features", None) or []
    return name, [str(x) for x in links]


@dataclass
class CandidateLinkReport:
    """Per-candidate result of the phantom-link check."""

    candidate_name: str
    links: list[str]
    phantom_links: list[str] = field(default_factory=list)
    # each near-miss: (emitted_link, [real feature name(s) it normalizes to])
    near_miss_links: list[tuple[str, list[str]]] = field(default_factory=list)

    @property
    def has_phantom(self) -> bool:
        return bool(self.phantom_links)

    @property
    def has_near_miss(self) -> bool:
        return bool(self.near_miss_links)


def check_phantom_links(
    candidates: list[Any], vision: dict[str, Any]
) -> list[CandidateLinkReport]:
    """Check each candidate's linked_vision_features against the vision.

    Accepts ``Candidate`` objects or plain dicts. Returns one report per
    candidate, in input order.
    """
    real_names = _resolve_feature_names(vision)
    real_set = set(real_names)
    norm_index: dict[str, list[str]] = {}
    for rn in real_names:
        norm_index.setdefault(_normalize(rn), []).append(rn)

    reports: list[CandidateLinkReport] = []
    for cand in candidates:
        name, links = _extract(cand)
        report = CandidateLinkReport(candidate_name=name, links=list(links))
        for link in links:
            if link in real_set:
                continue  # exact match — clean
            matches = norm_index.get(_normalize(link))
            if matches:
                report.near_miss_links.append((link, list(matches)))
            else:
                report.phantom_links.append(link)
        reports.append(report)
    return reports


def phantom_link_summary(reports: list[CandidateLinkReport]) -> dict[str, Any]:
    """Aggregate counts across candidate reports.

    ``phantom_rate`` is over candidates that actually carried links, since
    empty-link candidates are out of scope for this check by design.
    """
    total = len(reports)
    with_links = sum(1 for r in reports if r.links)
    phantom_flagged = sum(1 for r in reports if r.has_phantom)
    near_miss_flagged = sum(1 for r in reports if r.has_near_miss)
    fully_clean = sum(
        1 for r in reports if r.links and not r.has_phantom and not r.has_near_miss
    )
    return {
        "candidates": total,
        "candidates_with_links": with_links,
        "fully_clean": fully_clean,
        "phantom_flagged": phantom_flagged,
        "near_miss_flagged": near_miss_flagged,
        "total_phantom_links": sum(len(r.phantom_links) for r in reports),
        "total_near_miss_links": sum(len(r.near_miss_links) for r in reports),
        "phantom_rate": (phantom_flagged / with_links) if with_links else 0.0,
    }


def format_phantom_report(reports: list[CandidateLinkReport]) -> str:
    """Human-readable dump for a probe verbose mode (`--show-grounding`)."""
    summary = phantom_link_summary(reports)
    lines = [
        "Phantom-link check (Layer 1):",
        f"  candidates: {summary['candidates']}  "
        f"with_links: {summary['candidates_with_links']}  "
        f"fully_clean: {summary['fully_clean']}",
        f"  phantom_flagged: {summary['phantom_flagged']}  "
        f"(rate {summary['phantom_rate']:.2f}, "
        f"{summary['total_phantom_links']} links)  "
        f"near_miss_flagged: {summary['near_miss_flagged']} "
        f"({summary['total_near_miss_links']} links)",
    ]
    for r in reports:
        if not r.has_phantom and not r.has_near_miss:
            continue
        lines.append(f"  - {r.candidate_name}:")
        if r.phantom_links:
            lines.append(f"      PHANTOM: {', '.join(r.phantom_links)}")
        for link, matched in r.near_miss_links:
            lines.append(f"      near-miss: {link!r} -> {', '.join(matched)}")
    return "\n".join(lines)