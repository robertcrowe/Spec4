"""Deployer-probe loading helpers (thin extension of ``evals/phaser/_load.py``).

Dev tooling under ``evals/``. Never wired into the pipeline.

The Deployer probes reuse the phaser draw loader and stack/NFR helpers verbatim
(imported below and re-exported) and add only what is Deployer-specific:

* ``load_deployer_draw`` — phaser's ``load_draw`` plus the terminal-stage
  artifacts: the required ``deployment-plan.md`` and the *optional*, dev-only
  ``transcript.md`` (a hand-assembled analysis artifact, never produced during
  normal operation — no probe may hard-depend on it).
* ``plan_sections`` — split a deployment-plan markdown document into a
  ``{heading: body}`` map keyed by its ``##`` / ``###`` headers, the unit the
  structural probes query.

Import path note: the phaser suite's module is *also* named ``_load``, so a bare
``from _load import ...`` from here would resolve to this file (a circular
self-import), not phaser's. We instead load ``evals/phaser/_load.py`` from its
file path under a distinct module name (``_phaser_load``) via ``importlib`` and
re-export the shared surface, so Deployer probes can ``from _load import ...``
everything they need from this one place.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

# Load the sibling phaser loader under a distinct module name to avoid the
# ``_load`` name collision (both suites' shared module is named ``_load``).
_PHASER_LOAD_PATH = Path(__file__).resolve().parent.parent / "phaser" / "_load.py"
_spec = importlib.util.spec_from_file_location("_phaser_load", _PHASER_LOAD_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover - defensive
    raise ImportError(f"cannot load phaser _load from {_PHASER_LOAD_PATH}")
_phaser_load = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_phaser_load)

# Re-export the shared phaser surface so Deployer probes import everything from
# one place (``from _load import ...``) rather than reaching across suites.
AMBIGUOUS = _phaser_load.AMBIGUOUS
CAPABILITY = _phaser_load.CAPABILITY
PRODUCT = _phaser_load.PRODUCT
UNRESOLVED = _phaser_load.UNRESOLVED
capability_ids = _phaser_load.capability_ids
capability_name_to_id = _phaser_load.capability_name_to_id
catalog_nodes = _phaser_load.catalog_nodes
classify_id = _phaser_load.classify_id
derived_nfr_ids = _phaser_load.derived_nfr_ids
load_draw = _phaser_load.load_draw
name_matches = _phaser_load.name_matches
product_features = _phaser_load.product_features
product_ids = _phaser_load.product_ids
slug = _phaser_load.slug
stack_entries = _phaser_load.stack_entries

__all__ = [
    "AMBIGUOUS",
    "CAPABILITY",
    "PRODUCT",
    "UNRESOLVED",
    "capability_ids",
    "capability_name_to_id",
    "catalog_nodes",
    "classify_id",
    "derived_nfr_ids",
    "load_draw",
    "load_deployer_draw",
    "name_matches",
    "plan_sections",
    "product_features",
    "product_ids",
    "slug",
    "stack_entries",
]


def load_deployer_draw(draw_dir: str | Path) -> dict[str, Any]:
    """Load a draw dir with the phaser artifacts plus Deployer's plan/transcript.

    Extends ``load_draw`` (``feature_specs / ai_features / stack / manifest /
    phases``) with:

    * ``plan`` — the raw ``deployment-plan.md`` text, or ``None`` when absent.
      Every structural probe treats ``plan is None`` as UNMEASURABLE rather than
      a failure, so the suite degrades cleanly on a draw that never reached
      Deployer.
    * ``transcript`` — the raw ``transcript.md`` text when a dev-assembled draw
      happens to include it, else ``None``. Dev-only; structural probes never
      read it (only the interactive/``--llm`` conversation-shape checks do).
    """
    root = Path(draw_dir)
    draw = load_draw(root)
    draw["plan"] = _read_text(root / "deployment-plan.md")
    draw["transcript"] = _read_text(root / "transcript.md")
    return draw


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Deployment-plan section parsing
# ---------------------------------------------------------------------------

# A section starts at a ## or ### heading and runs until the next heading of the
# same-or-shallower depth (or EOF). We key by the heading text alone so callers
# can ask for "Environment", "Target", "Deployment Steps", etc. without caring
# about depth. A repeated heading is disambiguated by suffixing " (2)", " (3)".
_HEADING_RE = re.compile(r"^(#{2,3})\s+(.*\S)\s*$", re.MULTILINE)


def plan_sections(plan_md: str | None) -> dict[str, str]:
    """Split a deployment-plan markdown doc into ``{heading: body}``.

    Bodies are the text between a heading and the next ``##``/``###`` heading,
    stripped. Headings are taken verbatim (backticks and inline code preserved).
    Returns ``{}`` for ``None``/empty input. The single top-level ``# Deployment
    Plan`` title is ignored — only ``##``/``###`` sections are captured, which is
    the granularity the probes assert against.
    """
    if not plan_md:
        return {}
    matches = list(_HEADING_RE.finditer(plan_md))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(plan_md)
        body = plan_md[start:end].strip()
        key = heading
        n = 2
        while key in sections:
            key = f"{heading} ({n})"
            n += 1
        sections[key] = body
    return sections


def plan_text(draw: dict[str, Any]) -> str:
    """The full plan markdown as one lowercased string for blunt containment.

    Convenience for probes that ask "does this token appear anywhere in the
    plan" without caring which section. Empty string when no plan is present.
    """
    return (draw.get("plan") or "").lower()
