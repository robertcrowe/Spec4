"""Loader and validator for the Agentifier pattern library.

This module reads the Markdown-with-YAML-frontmatter pattern files under
``patterns/tiers/`` and ``patterns/mechanisms/`` (see ``patterns/SCHEMA.md``),
validates them against the schema, and returns typed :class:`TierPattern` and
:class:`MechanismPattern` dataclasses.

It is a pure library module: importing it performs no file I/O and has no side
effects. All reads happen inside :func:`load_patterns`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

__all__ = [
    "PatternValidationError",
    "PatternBase",
    "TierPattern",
    "MechanismPattern",
    "load_patterns",
]

# Number of tiers on the ladder (deterministic = 1 … multi_agent_collaboration = 9).
_TIER_COUNT = 9

# Required frontmatter fields shared by every pattern.
_REQUIRED_COMMON_FIELDS = (
    "name",
    "category",
    "library_version",
    "last_reviewed",
    "references",
)

# Frontmatter fields required for tier patterns and forbidden for mechanisms.
_TIER_ONLY_FIELDS = (
    "tier_order",
    "cost_range_usd",
    "latency_range_seconds",
    "required_infrastructure",
)

# Prose sections, in their required order. The four list-shaped sections are
# parsed into lists of bullet strings; Description is a single paragraph;
# References falls back to the frontmatter list when it has no bullets.
_DESCRIPTION_HEADING = "Description"
_REFERENCES_HEADING = "References"
_LIST_HEADINGS = (
    "When it works",
    "When it doesn't",
    "Over-engineering signs",
    "Under-engineering signs",
)
_REQUIRED_SECTION_ORDER = (
    _DESCRIPTION_HEADING,
    *_LIST_HEADINGS,
    _REFERENCES_HEADING,
)

# Maps a prose heading to the dataclass field it populates.
_HEADING_TO_FIELD = {
    "Description": "description",
    "When it works": "when_works",
    "When it doesn't": "when_doesnt",
    "Over-engineering signs": "over_engineering_signs",
    "Under-engineering signs": "under_engineering_signs",
    "References": "references",
}

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)
# Strips an optional ``NN_`` ordering prefix from a tier filename stem.
_PREFIX_RE = re.compile(r"^\d+_")


class PatternValidationError(ValueError):
    """Raised when a pattern file violates the schema in ``SCHEMA.md``."""


@dataclass
class PatternBase:
    """Fields common to every pattern, tier or mechanism."""

    name: str
    category: Literal["tier", "mechanism"]
    library_version: str
    last_reviewed: str
    description: str
    when_works: list[str]
    when_doesnt: list[str]
    over_engineering_signs: list[str]
    under_engineering_signs: list[str]
    references: list[str]
    source_path: Path = field(compare=False)


@dataclass
class TierPattern(PatternBase):
    """A tier pattern: what *shape* an AI feature is. Adds ladder metadata."""

    tier_order: int
    cost_range_usd: str
    latency_range_seconds: str
    # Tier-required enabling infrastructure (D-I1): a closed, enumerated list of
    # structural-substrate component ids that the *tier* implies, independent of
    # the specific vision. Empty for tiers with no tier-specific substrate
    # (deterministic, single_call). Injected downstream as ``kind: infrastructure``
    # nodes by the deterministic expansion pass (see ``infra_expander``); this is
    # a registry lookup, never LLM invention.
    required_infrastructure: list[str] = field(default_factory=list)


@dataclass
class MechanismPattern(PatternBase):
    """A mechanism pattern: *how* an AI feature is built."""


def _patterns_root() -> Path:
    """Return the ``patterns/`` directory shipped alongside this module."""
    return Path(__file__).resolve().parent / "patterns"


def _split_frontmatter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    """Split a pattern file into its parsed frontmatter dict and Markdown body."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise PatternValidationError(
            f"{path.name}: file must begin with a YAML frontmatter block "
            "delimited by '---' lines."
        )
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise PatternValidationError(
            f"{path.name}: frontmatter is not valid YAML: {exc}"
        ) from exc
    if not isinstance(meta, dict):
        raise PatternValidationError(
            f"{path.name}: frontmatter must be a YAML mapping."
        )
    return meta, match.group(2)


def _parse_sections(body: str, path: Path) -> dict[str, Any]:
    """Parse the Markdown body into a mapping of field name -> value.

    Validates that every required section is present, non-empty, in the
    expected order, and that no unknown top-level heading appears.
    """
    # Split on top-level (``## ``) headings, capturing the heading text.
    parts = re.split(r"(?m)^##[ \t]+(.+?)[ \t]*$", body)
    # parts[0] is any preamble before the first heading; ignore it.
    headings = [h.strip() for h in parts[1::2]]
    contents = parts[2::2]

    seen_order = []
    section_text: dict[str, str] = {}
    for heading, content in zip(headings, contents):
        if heading not in _REQUIRED_SECTION_ORDER:
            raise PatternValidationError(
                f"{path.name}: unknown top-level section '## {heading}'. "
                f"Allowed sections: {', '.join(_REQUIRED_SECTION_ORDER)}."
            )
        if heading in section_text:
            raise PatternValidationError(
                f"{path.name}: duplicate section '## {heading}'."
            )
        section_text[heading] = content
        seen_order.append(heading)

    missing = [h for h in _REQUIRED_SECTION_ORDER if h not in section_text]
    if missing:
        raise PatternValidationError(
            f"{path.name}: missing required section(s): "
            f"{', '.join('## ' + h for h in missing)}."
        )

    expected_order = [h for h in _REQUIRED_SECTION_ORDER if h in section_text]
    if seen_order != expected_order:
        raise PatternValidationError(
            f"{path.name}: sections out of order. Expected "
            f"{', '.join(expected_order)} but found {', '.join(seen_order)}."
        )

    fields: dict[str, Any] = {}
    for heading in _LIST_HEADINGS:
        items = _parse_bullets(section_text[heading])
        if not items:
            raise PatternValidationError(
                f"{path.name}: section '## {heading}' must contain at least "
                "one bullet ('- ...')."
            )
        fields[_HEADING_TO_FIELD[heading]] = items

    description = section_text[_DESCRIPTION_HEADING].strip()
    if not description:
        raise PatternValidationError(
            f"{path.name}: section '## {_DESCRIPTION_HEADING}' is empty."
        )
    fields["description"] = description

    # References come from the section bullets, falling back to the frontmatter
    # list when the section has no bullets. Emptiness is validated by the caller
    # once the frontmatter fallback is available.
    fields["_references_section"] = _parse_bullets(section_text[_REFERENCES_HEADING])
    return fields


def _parse_bullets(text: str) -> list[str]:
    """Return the top-level Markdown bullets in ``text`` as stripped strings.

    Continuation lines (indented under a bullet) are folded into the preceding
    bullet so multi-line items stay intact. Nested/indented bullets are treated
    as continuations rather than separate items.
    """
    items: list[str] = []
    current: list[str] | None = None
    for raw in text.splitlines():
        bullet = re.match(r"^[-*][ \t]+(.*)$", raw)
        if bullet:
            if current is not None:
                items.append(" ".join(current).strip())
            current = [bullet.group(1).strip()]
        elif current is not None and raw.strip():
            current.append(raw.strip())
    if current is not None:
        items.append(" ".join(current).strip())
    return [item for item in items if item]


def _validate_frontmatter(meta: dict[str, Any], path: Path, category: str) -> None:
    """Validate frontmatter fields and types for a pattern of ``category``."""
    for required in _REQUIRED_COMMON_FIELDS:
        if required not in meta:
            raise PatternValidationError(
                f"{path.name}: missing required frontmatter field '{required}'."
            )

    if not isinstance(meta["name"], str) or not meta["name"].strip():
        raise PatternValidationError(
            f"{path.name}: frontmatter 'name' must be a non-empty string."
        )
    if meta["category"] != category:
        raise PatternValidationError(
            f"{path.name}: frontmatter 'category' is '{meta['category']}' but "
            f"the file lives under the '{category}' directory."
        )
    if not isinstance(meta["library_version"], str) or not meta["library_version"]:
        raise PatternValidationError(
            f"{path.name}: frontmatter 'library_version' must be a non-empty string."
        )
    if not isinstance(meta["last_reviewed"], str) or not _is_iso_date(
        meta["last_reviewed"]
    ):
        raise PatternValidationError(
            f"{path.name}: frontmatter 'last_reviewed' must be an ISO date string "
            "(YYYY-MM-DD)."
        )
    if not isinstance(meta["references"], list) or not all(
        isinstance(r, str) for r in meta["references"]
    ):
        raise PatternValidationError(
            f"{path.name}: frontmatter 'references' must be a list of strings."
        )

    expected_stem = _PREFIX_RE.sub("", path.stem)
    if meta["name"] != expected_stem:
        raise PatternValidationError(
            f"{path.name}: frontmatter 'name' is '{meta['name']}' but must match "
            f"the filename stem '{expected_stem}'."
        )

    if category == "tier":
        for tier_field in _TIER_ONLY_FIELDS:
            if tier_field not in meta:
                raise PatternValidationError(
                    f"{path.name}: tier pattern missing required frontmatter "
                    f"field '{tier_field}'."
                )
        order = meta["tier_order"]
        if not isinstance(order, int) or isinstance(order, bool) or not (
            1 <= order <= _TIER_COUNT
        ):
            raise PatternValidationError(
                f"{path.name}: 'tier_order' must be an integer between 1 and "
                f"{_TIER_COUNT}, got {order!r}."
            )
        for tier_field in ("cost_range_usd", "latency_range_seconds"):
            if not isinstance(meta[tier_field], str) or not meta[tier_field]:
                raise PatternValidationError(
                    f"{path.name}: '{tier_field}' must be a non-empty string."
                )
        infra = meta["required_infrastructure"]
        if not isinstance(infra, list) or not all(isinstance(c, str) for c in infra):
            raise PatternValidationError(
                f"{path.name}: 'required_infrastructure' must be a list of "
                "strings (may be empty)."
            )
    else:
        present = [f for f in _TIER_ONLY_FIELDS if f in meta]
        if present:
            raise PatternValidationError(
                f"{path.name}: mechanism pattern must not declare tier-only "
                f"field(s): {', '.join(present)}."
            )


def _is_iso_date(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


def _build_pattern(path: Path, category: str) -> PatternBase:
    """Parse and validate a single pattern file into a dataclass."""
    text = path.read_text(encoding="utf-8")
    meta, body = _split_frontmatter(text, path)
    _validate_frontmatter(meta, path, category)
    sections = _parse_sections(body, path)

    references = sections.pop("_references_section") or list(meta["references"])
    if not references:
        raise PatternValidationError(
            f"{path.name}: '## References' section is empty and frontmatter "
            "'references' is also empty."
        )

    common = dict(
        name=meta["name"],
        category=category,
        library_version=meta["library_version"],
        last_reviewed=meta["last_reviewed"],
        description=sections["description"],
        when_works=sections["when_works"],
        when_doesnt=sections["when_doesnt"],
        over_engineering_signs=sections["over_engineering_signs"],
        under_engineering_signs=sections["under_engineering_signs"],
        references=references,
        source_path=path,
    )

    if category == "tier":
        return TierPattern(
            tier_order=meta["tier_order"],
            cost_range_usd=meta["cost_range_usd"],
            latency_range_seconds=meta["latency_range_seconds"],
            required_infrastructure=list(meta["required_infrastructure"]),
            **common,
        )
    return MechanismPattern(**common)


def _load_dir(directory: Path, category: str) -> list[PatternBase]:
    if not directory.is_dir():
        raise PatternValidationError(
            f"pattern directory not found: {directory}"
        )
    patterns = [
        _build_pattern(path, category)
        for path in sorted(directory.glob("*.md"))
    ]
    return patterns


def load_patterns(
    patterns_dir: str | Path | None = None,
) -> tuple[list[TierPattern], list[MechanismPattern]]:
    """Load, validate, and return all tier and mechanism patterns.

    Args:
        patterns_dir: Optional override for the patterns root. Defaults to the
            ``patterns/`` directory shipped with this module.

    Returns:
        A ``(tiers, mechanisms)`` tuple. Tiers are sorted by ``tier_order``;
        mechanisms are sorted by ``name``.

    Raises:
        PatternValidationError: if any file violates the schema (see
            ``SCHEMA.md``), or if tier ordering is non-contiguous/duplicated.
    """
    root = Path(patterns_dir) if patterns_dir is not None else _patterns_root()

    tiers = [
        p for p in _load_dir(root / "tiers", "tier") if isinstance(p, TierPattern)
    ]
    mechanisms = [
        p
        for p in _load_dir(root / "mechanisms", "mechanism")
        if isinstance(p, MechanismPattern)
    ]

    _validate_tier_ladder(tiers, root)

    tiers.sort(key=lambda p: p.tier_order)
    mechanisms.sort(key=lambda p: p.name)
    return tiers, mechanisms


def _validate_tier_ladder(tiers: list[TierPattern], root: Path) -> None:
    """Ensure tier_order values are unique and cover 1..N with no gaps."""
    orders = sorted(p.tier_order for p in tiers)
    if len(set(orders)) != len(orders):
        dupes = sorted({o for o in orders if orders.count(o) > 1})
        raise PatternValidationError(
            f"{root / 'tiers'}: duplicate tier_order value(s): {dupes}."
        )
    if orders and orders != list(range(1, len(orders) + 1)):
        raise PatternValidationError(
            f"{root / 'tiers'}: tier_order values must be contiguous starting "
            f"at 1; got {orders}."
        )
