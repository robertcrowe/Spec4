"""Shared loading and id-resolution for the D-PH0 Phaser probe suite.

Dev tooling under ``evals/``. Never wired into the pipeline.

Every probe in this suite reads a saved draw directory holding some subset of
``feature_specs.json``, ``ai_features.json``, ``stack.json``, ``manifest.json``,
and generated phase files (``phases/phase*.md``, or ``phase*.md`` at the top
level). This module owns the parts that must stay consistent across the four
probes:

* **Frontmatter parsing** — mirrors ``project_manager.parse_phase_markdown``
  (JSON frontmatter only; the prose body is a deterministic rendering of the
  same fields).
* **Dual-space id resolution (D-PH0b).** Phase ``features[]`` declarations are
  free-formed by the model today: FareBox declares product-feature ids while
  Threadline declares AI catalog-node ids, and nothing enforces either. Each
  declared id is therefore resolved against *both* id sets per draw and
  classified ``PRODUCT`` / ``CAPABILITY`` / ``AMBIGUOUS`` (resolves in both —
  observed live on Threadline, where ``thread_summarization`` is both the
  product feature and the catalog node Scout named after it) / ``UNRESOLVED``.
  Probes must report AMBIGUOUS as ambiguous, never silently assign a space,
  and must report an unmeasurable side as UNMEASURABLE, never silently pass.
* **The slug convention** — ``re.sub(r"[^a-z0-9_]", "_", name.lower())``,
  identical to ``spec4.agents._utils.slug``, used for the ``nfr_<slug>`` ids
  (D-SC2) and the ``requires`` name→id fallback.
* **Blunt name matching.** Stack entry names are joined to phase text by a
  word-boundary, punctuation-tolerant string match (``name_matches``). This is
  deliberately blunt — a lexical join, not a semantic one — and every probe
  that uses it says so in its report header.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

PRODUCT = "PRODUCT"
CAPABILITY = "CAPABILITY"
AMBIGUOUS = "AMBIGUOUS"
UNRESOLVED = "UNRESOLVED"

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def slug(name: str) -> str:
    """Mirror ``spec4.agents._utils.slug``."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower()) if name else ""


# ---------------------------------------------------------------------------
# Draw loading
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _parse_phase_markdown(text: str) -> dict[str, Any] | None:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def load_draw(draw_dir: str | Path) -> dict[str, Any]:
    """Load a draw directory into a dict of artifacts + parsed phases.

    Returns ``{feature_specs, ai_features, stack, manifest, phases}`` where any
    absent artifact is ``None`` (``phases`` is ``[]``). ``stack`` is unwrapped
    to the ``stack_spec`` object when that envelope is present.
    """
    root = Path(draw_dir)
    draw: dict[str, Any] = {
        "feature_specs": _load_json(root / "feature_specs.json"),
        "ai_features": _load_json(root / "ai_features.json"),
        "stack": _load_json(root / "stack.json"),
        "manifest": _load_json(root / "manifest.json"),
        "phases": [],
    }
    if isinstance(draw["stack"], dict) and "stack_spec" in draw["stack"]:
        inner = draw["stack"]["stack_spec"]
        draw["stack"] = inner if isinstance(inner, dict) else None

    phase_files = sorted(
        (root / "phases").glob("phase*.md") if (root / "phases").is_dir()
        else root.glob("phase*.md"),
        key=lambda p: (
            int(m.group(1)) if (m := re.match(r"phase(\d+)", p.stem)) else 0
        ),
    )
    for pf in phase_files:
        text = pf.read_text(encoding="utf-8")
        phase = _parse_phase_markdown(text)
        if phase is not None:
            # D-PH34e: retain the markdown body so probes can see renderer-
            # added content (routed stack, threaded NFRs). The body mirrors
            # every frontmatter field, so a body-ONLY hit is renderer-added.
            match = _FRONTMATTER_RE.match(text)
            phase["_body"] = text[match.end():] if match else ""
            draw["phases"].append(phase)
    return draw


# ---------------------------------------------------------------------------
# Id sets and dual-space declaration resolution (D-PH0b)
# ---------------------------------------------------------------------------


def product_features(draw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        f
        for f in ((draw.get("feature_specs") or {}).get("features") or [])
        if isinstance(f, dict)
    ]


def catalog_nodes(draw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        n
        for n in ((draw.get("ai_features") or {}).get("ai_features") or [])
        if isinstance(n, dict)
    ]


def product_ids(draw: dict[str, Any]) -> set[str]:
    return {str(f["id"]) for f in product_features(draw) if f.get("id")}


def capability_ids(draw: dict[str, Any]) -> set[str]:
    return {str(n["id"]) for n in catalog_nodes(draw) if n.get("id")}


def capability_name_to_id(draw: dict[str, Any]) -> dict[str, str]:
    """``requires``/``composed_under`` hold names, ``id`` holds the slug."""
    return {
        str(n["name"]): str(n["id"])
        for n in catalog_nodes(draw)
        if n.get("name") and n.get("id")
    }


def classify_id(fid: str, draw: dict[str, Any]) -> str:
    in_product = fid in product_ids(draw)
    in_capability = fid in capability_ids(draw)
    if in_product and in_capability:
        return AMBIGUOUS
    if in_product:
        return PRODUCT
    if in_capability:
        return CAPABILITY
    return UNRESOLVED


def declarations(draw: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten every phase's declarations with id-space classification.

    Two schema eras (D-PH0b cross-shape tolerance):

    * **Two-array schema (D-PH2)** — detected when any phase carries a
      ``capabilities`` key. The array determines the space: ``features[]``
      entries are PRODUCT when the id resolves in the spine (else UNRESOLVED —
      a cross-space mistake is a defect, not an ambiguity), ``capabilities[]``
      entries are CAPABILITY when the id resolves in the catalog (else
      UNRESOLVED). AMBIGUOUS never occurs in this era.
    * **Legacy single-array schema** — ``features[]`` free-formed by the
      model; each id is resolved against both sets and classified PRODUCT /
      CAPABILITY / AMBIGUOUS / UNRESOLVED.

    Each record: ``{phase, id, role, space, scope_note}``.
    """
    out: list[dict[str, Any]] = []
    two_array = any("capabilities" in p for p in draw["phases"])
    prod = product_ids(draw)
    caps = capability_ids(draw)
    for phase in draw["phases"]:
        raw = phase.get("phase_number")
        number = raw if isinstance(raw, int) else None
        for key in ("features", "capabilities"):
            for decl in phase.get(key) or []:
                if not isinstance(decl, dict):
                    continue
                fid = str(decl.get("id") or "")
                if two_array:
                    if key == "features":
                        space = PRODUCT if fid in prod else UNRESOLVED
                    else:
                        space = CAPABILITY if fid in caps else UNRESOLVED
                else:
                    space = classify_id(fid, draw)
                out.append({
                    "phase": number,
                    "id": fid,
                    "role": str(decl.get("role") or ""),
                    "space": space,
                    "scope_note": str(decl.get("scope_note") or "").strip(),
                })
    return out


def first_declaring_phase(
    decls: list[dict[str, Any]], fid: str, spaces: tuple[str, ...]
) -> int | None:
    """Earliest phase number declaring ``fid`` in any of ``spaces``.

    AMBIGUOUS declarations count for both spaces (annotated by callers), so
    callers include AMBIGUOUS in ``spaces`` when either side may own the id.
    """
    numbers = [
        d["phase"]
        for d in decls
        if d["id"] == fid and d["space"] in spaces and isinstance(d["phase"], int)
    ]
    return min(numbers) if numbers else None


def last_declaring_phase(
    decls: list[dict[str, Any]], fid: str, spaces: tuple[str, ...]
) -> int | None:
    """Latest phase number declaring ``fid`` in any of ``spaces``.

    The consumer of a dependency wires it in during its final extension: the
    phase schema guarantees exactly one phase *introduces* an item (the shell)
    and every later touch *extends* it, so the dependency-consuming phase is
    the consumer's *last* declaring phase, not its first. Mirrors
    ``first_declaring_phase`` with ``max``.
    """
    numbers = [
        d["phase"]
        for d in decls
        if d["id"] == fid and d["space"] in spaces and isinstance(d["phase"], int)
    ]
    return max(numbers) if numbers else None


# ---------------------------------------------------------------------------
# Stack entry inventory
# ---------------------------------------------------------------------------


#: Container keys that never identify an entry on their own. An unnamed entry
#: (a provider ``capabilities[]`` item; persistence stores are keyed, and the
#: store key IS the identity) takes the nearest ancestor key *outside* this
#: set as its name — e.g. ``providers.OpenAI.capabilities[0]`` names ``OpenAI``.
_GENERIC_KEYS = frozenset({
    "capabilities",
    "collections",
    "libraries",
    "integrations",
    "infrastructure",
    "targets",
    "auth",
    "providers",
    "persistence",
    "deployment",
    "security",
})


def stack_entries(draw: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield every stack object carrying at least one probe-relevant field.

    Walks the whole stack; an entry is any dict carrying ``serves_features``,
    ``serves_capabilities``, ``satisfies_nfr``, ``satisfies_infra``, or
    ``status``. Each yield: ``{name, label, path, entry}`` where ``name`` is
    the entry's own ``name`` when present, else the nearest non-generic
    ancestor key (see ``_GENERIC_KEYS``) — the *matchable* identity — and
    ``label`` is the display form (name plus ``tier`` when the name was a
    fallback and the entry carries one, so sibling provider capabilities stay
    distinguishable in reports).
    """
    fields = (
        "serves_features",
        "serves_capabilities",
        "satisfies_nfr",
        "satisfies_infra",
        "status",
    )

    def walk(obj: Any, path: str, key_name: str) -> Iterator[dict[str, Any]]:
        if isinstance(obj, dict):
            if any(f in obj for f in fields):
                own = obj.get("name")
                name = str(own or key_name or path)
                label = name
                if not own and obj.get("tier"):
                    label = f"{name} [{obj['tier']}]"
                yield {"name": name, "label": label, "path": path, "entry": obj}
            for k, v in obj.items():
                child_key = str(k) if str(k) not in _GENERIC_KEYS else key_name
                yield from walk(v, f"{path}.{k}" if path else str(k), child_key)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                yield from walk(v, f"{path}[{i}]", key_name)

    stack = draw.get("stack") or {}
    yield from walk(stack, "", "")


# ---------------------------------------------------------------------------
# Blunt name matching against phase text
# ---------------------------------------------------------------------------


def _name_pattern(name: str) -> re.Pattern[str] | None:
    chunks = re.findall(r"[a-z0-9]+", name.lower())
    if not chunks:
        return None
    body = r"[^a-z0-9]*".join(re.escape(c) for c in chunks)
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])")


def name_matches(name: str, text: str) -> bool:
    """Word-boundary, punctuation-tolerant match of ``name`` in ``text``.

    Deliberately blunt: alphanumeric chunks of the name must appear in order,
    separated only by non-alphanumerics ("React Hook Form" matches
    "react-hook-form" but not "@tanstack/react-router"). A lexical join;
    reports built on it must say so.
    """
    pat = _name_pattern(name)
    return bool(pat and pat.search(text.lower()))


def phase_dependency_text(phase: dict[str, Any]) -> str:
    deps = (phase.get("tech_stack_spec") or {}).get("dependencies") or []
    return "\n".join(str(d) for d in deps)


def phase_build_text(phase: dict[str, Any]) -> str:
    """The phase's build-item surface: dependencies + instructions."""
    instructions = phase.get("instructions") or []
    return phase_dependency_text(phase) + "\n" + "\n".join(
        str(s) for s in instructions
    )


def phase_full_text(phase: dict[str, Any]) -> str:
    """Everything a threading check may scan: build text + verification +
    summary + risk + configurations."""
    tech = phase.get("tech_stack_spec") or {}
    risk = phase.get("risk_assessment") or {}
    parts = [
        phase_build_text(phase),
        str(phase.get("phase_summary") or ""),
        str(tech.get("configurations") or ""),
        str(phase.get("verification") or ""),
        str(risk.get("potential_bottlenecks") or ""),
        str(risk.get("mitigation_strategy") or ""),
    ]
    return "\n".join(parts)


def phase_rendered_body(phase: dict[str, Any]) -> str:
    """The phase file's markdown body (everything after the frontmatter).

    Mirrors all frontmatter fields plus renderer-added blocks; combined with
    the frontmatter-only text helpers, a body-only hit isolates code-routed
    signal from model-authored signal (D-PH34e).
    """
    return str(phase.get("_body") or "")


def phase_numbers(draw: dict[str, Any]) -> list[int]:
    return [
        p["phase_number"]
        for p in draw["phases"]
        if isinstance(p.get("phase_number"), int)
    ]


def derived_nfr_ids(draw: dict[str, Any]) -> dict[str, str]:
    """``nfr_<slug>`` id → goal text, per the D-SC2 derivation."""
    specs = draw.get("feature_specs") or {}
    goals = specs.get("nfr_goals") or []
    return {
        f"nfr_{slug(g.strip())}": g.strip()
        for g in goals
        if isinstance(g, str) and g.strip()
    }
