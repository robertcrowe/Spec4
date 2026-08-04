"""Advisory cross-phase data-flow seam check for Phaser (Phase-0 prototype).

Extraction-based (Architecture B): the phase generation schema is unchanged.

After Phaser emits a validated phase set, this module asks the model to extract
a structured data-flow graph (tables / endpoints / feature-coverage per phase)
from the phases' prose, then runs deterministic Python checks over that graph.

Phase-0 posture (deliberately conservative):

  * ADVISORY ONLY — findings are logged (DEV_MODE) and surfaced to the developer
    alongside the ready phases. They NEVER block, mutate state, or trigger a retry.

  * Greenfield full-set only — the caller skips this on brownfield updates where
    only newly-added phases are present (an incomplete graph would false-positive).

  * Never raises — any extraction/parse failure degrades to "" (no advisory) so
    the phases are never stranded.

This is instrumentation to gather precision/recall across draws before deciding
whether any check graduates to driving Phaser's retry loop.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from spec4.llm import complete, supports_response_format

_DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"


_EXTRACTOR_SYSTEM_PROMPT = """\
You are a data-flow extractor for a software project's development plan. You are
given an ordered set of development phases (each with its instructions and
configuration) and a list of AI feature ids. Your ONLY job is to read what each
phase's instructions concretely specify and report the data-flow facts as JSON.

For EACH phase, extract:
- creates_tables: database tables/collections the phase's instructions CREATE
  (a migration, DDL, an ORM model definition, "create the X table"). Bare names
  as written (e.g. "inventory_item").
- reads_tables: tables the phase QUERIES, UPDATES, or otherwise uses but does NOT
  create in this phase.
- creates_endpoints: API endpoints the phase DEFINES/IMPLEMENTS, as "METHOD /path"
  (e.g. "POST /inventory/add").
- consumes_endpoints: endpoints the phase's client/frontend CALLS but does not
  define in this phase.
- covers_features: which of the provided feature ids this phase implements. Use
  the EXACT ids given. Empty list if none.

Rules:
- Report ONLY what the instructions concretely state. Do NOT infer tables,
  endpoints, or coverage that "should" exist but is not described. Faithfully
  reporting an omission is the point — do not paper over gaps.
- Use names exactly as they appear in the instructions.

Return ONLY this JSON object, no prose, no code fences:
{
  "phases": [
    {
      "phase_number": 1,
      "creates_tables": [],
      "reads_tables": [],
      "creates_endpoints": [],
      "consumes_endpoints": [],
      "covers_features": []
    }
  ]
}
"""


@dataclass
class SeamFinding:
    """A single advisory seam finding."""

    check: str   # "table" | "endpoint" | "coverage" | "declaration"
    severity: str  # "high" | "medium" | "info"
    message: str


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def _phases_for_extractor(phases: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for p in phases:
        instr = "\n".join(f"  - {s}" for s in (p.get("instructions") or []))
        tech = p.get("tech_stack_spec") or {}
        configs = tech.get("configurations") or ""
        blocks.append(
            f"### Phase {p.get('phase_number')}: {p.get('phase_title', '')}\n"
            f"Summary: {p.get('phase_summary', '')}\n"
            f"Configurations: {configs}\n"
            f"Instructions:\n{instr}\n"
            f"Verification: {p.get('verification', '')}"
        )
    return "\n\n".join(blocks)


def _feature_lines(
    ai_features: dict[str, Any] | None,
) -> tuple[str, list[dict[str, Any]]]:
    features = (ai_features or {}).get("ai_features") or []
    if not features:
        return "(no AI features provided)", []
    lines = [
        f"- {f.get('id', '')} — {f.get('name', '')} "
        f"(priority: {f.get('phase_priority') or 'mvp'})"
        for f in features
    ]
    return "\n".join(lines), features


def _parse_graph(raw: str) -> dict[str, Any] | None:
    """Tolerant parse of the extractor's JSON object. None on failure.

    Mirrors the sub-agent parse discipline: try the whole string, then a
    regex-extracted object; normalise each phase entry to the expected keys
    with empty-list defaults; return None on any unrecoverable failure.
    """
    candidates = [raw.strip()]
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        candidates.append(match.group())

    for attempt in candidates:
        try:
            data = json.loads(attempt)
        except (json.JSONDecodeError, ValueError):
            continue

        if isinstance(data, dict) and isinstance(data.get("phases"), list):
            norm_phases: list[dict[str, Any]] = []
            for entry in data["phases"]:
                if not isinstance(entry, dict):
                    continue
                num = entry.get("phase_number")
                norm_phases.append(
                    {
                        "phase_number": num if isinstance(num, int) else None,
                        "creates_tables": [
                            str(t) for t in (entry.get("creates_tables") or [])
                        ],
                        "reads_tables": [
                            str(t) for t in (entry.get("reads_tables") or [])
                        ],
                        "creates_endpoints": [
                            str(e) for e in (entry.get("creates_endpoints") or [])
                        ],
                        "consumes_endpoints": [
                            str(e) for e in (entry.get("consumes_endpoints") or [])
                        ],
                        "covers_features": [
                            str(c) for c in (entry.get("covers_features") or [])
                        ],
                    }
                )
            return {"phases": norm_phases}

    return None


def _extract_graph(
    phases: list[dict[str, Any]],
    ai_features: dict[str, Any] | None,
    llm_config: dict[str, Any],
) -> dict[str, Any] | None:
    feature_text, _ = _feature_lines(ai_features)
    user_content = (
        f"AI feature ids:\n{feature_text}\n\n"
        f"Development phases:\n\n{_phases_for_extractor(phases)}\n\n"
        "Extract the data-flow graph as the specified JSON object."
    )
    response_format = (
        {"type": "json_object"}
        if supports_response_format(llm_config.get("model", ""))
        else None
    )
    response = complete(
        llm_config=llm_config,
        messages=[
            {"role": "system", "content": _EXTRACTOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        agent_name="phaser_seam",
        response_format=response_format,
        stream=False,
    )
    raw = (response.choices[0].message.content or "").strip()
    return _parse_graph(raw)


def _check_table_provenance(graph: dict[str, Any]) -> list[SeamFinding]:
    """Every read table must be created earlier-or-same; flag orphans."""
    findings: list[SeamFinding] = []
    creators: dict[str, int] = {}
    for p in graph["phases"]:
        n = p["phase_number"]
        order = n if isinstance(n, int) else 10**9
        for t in p["creates_tables"]:
            key = _norm(t)
            if key:
                creators[key] = min(creators.get(key, 10**9), order)

    for p in graph["phases"]:
        n = p["phase_number"]
        for t in p["reads_tables"]:
            key = _norm(t)
            if not key:
                continue
            if key not in creators:
                findings.append(
                    SeamFinding(
                        "table",
                        "high",
                        f"Table `{t}` is read in Phase {n} but never created "
                        f"in any phase.",
                    )
                )
            elif isinstance(n, int) and creators[key] > n:
                findings.append(
                    SeamFinding(
                        "table",
                        "medium",
                        f"Table `{t}` is read in Phase {n} but first created "
                        f"in Phase {creators[key]} (created after it is needed).",
                    )
                )

    read_keys = {
        _norm(t) for p in graph["phases"] for t in p["reads_tables"] if _norm(t)
    }
    for key, n in sorted(creators.items()):
        if key not in read_keys:
            label = n if n < 10**9 else "?"
            findings.append(
                SeamFinding(
                    "table",
                    "info",
                    f"Table `{key}` (created Phase {label}) is never read by "
                    f"any phase.",
                )
            )

    return findings


def _check_endpoint_provenance(graph: dict[str, Any]) -> list[SeamFinding]:
    """Every consumed endpoint should be defined by some phase."""
    findings: list[SeamFinding] = []
    producers = {
        _norm(e)
        for p in graph["phases"]
        for e in p["creates_endpoints"]
        if _norm(e)
    }
    for p in graph["phases"]:
        n = p["phase_number"]
        for e in p["consumes_endpoints"]:
            key = _norm(e)
            if key and key not in producers:
                findings.append(
                    SeamFinding(
                        "endpoint",
                        "medium",
                        f"Endpoint `{e}` is called in Phase {n} but defined "
                        f"by no phase.",
                    )
                )
    return findings


def _check_feature_coverage(
    graph: dict[str, Any], ai_features: dict[str, Any] | None
) -> list[SeamFinding]:
    """Every selected (steel_thread/mvp) feature must be covered by a phase."""
    findings: list[SeamFinding] = []
    _, features = _feature_lines(ai_features)
    if not features:
        return findings

    covered = {
        _norm(c)
        for p in graph["phases"]
        for c in p["covers_features"]
        if _norm(c)
    }
    for f in features:
        priority = (f.get("phase_priority") or "mvp").lower()
        if priority not in ("steel_thread", "mvp"):
            continue
        fid = _norm(f.get("id", ""))
        name = f.get("name") or f.get("id") or "(unnamed)"
        if fid and fid not in covered:
            findings.append(
                SeamFinding(
                    "coverage",
                    "high",
                    f"Feature `{name}` ({priority}) is implemented by no phase.",
                )
            )

    return findings


def _declared_by_phase(phases: list[dict[str, Any]]) -> dict[int, set[str]]:
    """Map phase_number -> the set of AI-capability ids that phase declares.

    D-PH2k: AI declarations live in ``capabilities[]`` under the two-array
    schema (D-PH2a); ``features[]`` now holds product-feature ids, which must
    NOT be read against the AI catalog — a product declaration that happens to
    share an id with a catalog node (the observed Threadline collision) would
    otherwise be misread as a capability claim. Falls back to ``features[]``
    only for pre-D-PH2 phase sets, where AI ids lived there (mirroring
    ``_phase_spec_preamble``).
    """
    out: dict[int, set[str]] = {}
    for p in phases:
        number = p.get("phase_number")
        if not isinstance(number, int):
            continue
        # Key-presence era detection (not truthiness): present-but-empty
        # `capabilities` means "no capabilities declared", never "fall back
        # to features[]" — that would read product ids against the catalog.
        source = (
            p.get("features") if "capabilities" not in p else p.get("capabilities")
        )
        ids = {
            _norm(d.get("id"))
            for d in (source or [])
            if isinstance(d, dict) and _norm(d.get("id"))
        }
        out[number] = ids
    return out


def _check_declaration_alignment(
    graph: dict[str, Any],
    phases: list[dict[str, Any]],
    ai_features: dict[str, Any] | None,
) -> list[SeamFinding]:
    """Compare what each phase *declares* against what its prose actually implements.

    Phaser declares its phase → feature mapping in ``features[]`` (D-PS1), and the
    verbatim spec is attached to exactly the phases named there. So a phase whose
    instructions build a feature it did not declare gets **no spec for that
    feature** — spec starvation surviving inside the very mechanism built to end
    it. Nothing else catches this: the deterministic presence check in
    ``_phase_coverage`` only asks whether each feature is built by *some* phase,
    which is silent on under-declaration.

    Observed live: a phase built a search feature's entire frontend (its page, its
    hook, its endpoint calls) while declaring only the sibling feature it also
    touched. The search spec never reached the coder who needed it.

    This is the one place the extractor's ``covers_features`` becomes a
    *cross-check* rather than a reconstruction, now that the mapping is declared.
    Note ``_phases_for_extractor`` deliberately does not show the extractor the
    ``features[]`` declaration — if it did, the extractor would echo it back and
    the comparison would be vacuous. Keep it that way.

    Advisory only (both directions), because the extractor is an LLM reading
    prose: a phase that merely *calls* a feature's endpoint can look like it
    implements it, and a one-line integration step can be missed.
    """
    findings: list[SeamFinding] = []
    _, features = _feature_lines(ai_features)
    if not features:
        return findings

    catalog: dict[str, str] = {
        _norm(f.get("id", "")): (f.get("name") or f.get("id") or "")
        for f in features
        if _norm(f.get("id", ""))
    }
    declared = _declared_by_phase(phases)

    extracted: dict[int, set[str]] = {}
    for p in graph["phases"]:
        number = p.get("phase_number")
        if not isinstance(number, int):
            continue
        extracted[number] = {
            _norm(c) for c in p["covers_features"] if _norm(c) in catalog
        }

    # A feature implemented by no phase at all is already reported by
    # _check_feature_coverage; don't also accuse its declaring phase of
    # over-declaring it.
    implemented_anywhere: set[str] = set()
    for ids in extracted.values():
        implemented_anywhere |= ids

    for number in sorted(set(declared) | set(extracted)):
        d = declared.get(number, set())
        e = extracted.get(number, set())

        for fid in sorted(e - d):
            findings.append(
                SeamFinding(
                    "declaration",
                    "high",
                    f"Phase {number} implements `{catalog[fid]}` but does not "
                    f"declare it in `capabilities`, so that capability's "
                    f"specification is not attached to phase {number}.",
                )
            )

        for fid in sorted((d - e) & implemented_anywhere):
            findings.append(
                SeamFinding(
                    "declaration",
                    "medium",
                    f"Phase {number} declares `{catalog[fid]}` but its "
                    f"instructions do not appear to implement it; the attached "
                    f"specification may be spurious.",
                )
            )

    return findings


def _format_advisory(findings: list[SeamFinding]) -> str:
    surfaced = [f for f in findings if f.severity in ("high", "medium")]
    if not surfaced:
        return ""

    rank = {"high": 0, "medium": 1}
    surfaced.sort(key=lambda f: rank.get(f.severity, 9))

    lines = [
        "⚠️ **Possible data-flow seams to review** — advisory only; "
        "these did **not** block your phases and may include false positives.",
        "",
    ]
    for f in surfaced:
        lines.append(f"- **[{f.check}]** {f.message}")

    return "\n".join(lines)


def run_seam_check(
    phases: list[dict[str, Any]],
    ai_features: dict[str, Any] | None,
    llm_config: dict[str, Any],
) -> str:
    """Extract → check → format. Returns advisory markdown, or "" for none.

    Never raises: any failure degrades to "" so the phases are never stranded.
    """
    try:
        if not phases:
            return ""

        graph = _extract_graph(phases, ai_features, llm_config)
        if graph is None:
            if _DEV_MODE:
                print(
                    "[phaser-seam] extraction failed or unparseable; no advisory",
                    flush=True,
                )
            return ""

        findings = (
            _check_table_provenance(graph)
            + _check_endpoint_provenance(graph)
            + _check_feature_coverage(graph, ai_features)
            + _check_declaration_alignment(graph, phases, ai_features)
        )

        if _DEV_MODE:
            print(f"[phaser-seam] extracted graph: {json.dumps(graph)}", flush=True)
            for f in findings:
                print(
                    f"[phaser-seam] {f.severity.upper()} [{f.check}] {f.message}",
                    flush=True,
                )
            if not findings:
                print("[phaser-seam] no findings", flush=True)

        return _format_advisory(findings)

    except Exception as exc:  # never strand the phases
        if _DEV_MODE:
            print(f"[phaser-seam] seam check error ({exc}); no advisory", flush=True)
        return ""
