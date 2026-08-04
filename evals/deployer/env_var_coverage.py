"""Deployment-plan probe: environment-variable coverage (D-DE1 / D-DE9).

Dev tooling under ``evals/``. Never wired into the pipeline.

Pre-redesign Deployer derives the Environment section from ``code_review`` (or
asks the developer), never from the phases — even though every phase's
``tech_stack_spec.configurations`` already names the variables that phase's
build reads. This probe measures the gap:

**[1] PHASE-DECLARED VARS** — the union of ``SCREAMING_SNAKE_CASE`` names
extracted from every phase's ``tech_stack_spec.configurations`` (a free-form
string like ``"DATABASE_URL, REDIS_URL"`` or ``"PORT=8000"``; occasionally a
list — both tolerated). These are the authoritative "vars the code reads" set.

**[2] STACK-IMPLIED VARS (advisory)** — soft signals the plan's Environment
section should also account for: an AI ``model_family`` implies a provider API
key; a ``security.auth[]`` mechanism implies auth secrets; a
``deployment.targets[]`` with ``exposure`` implies host/CORS config. Reported
as advisory hints (their exact names are the developer's to confirm), not
counted in the hard metric.

**[3] COVERAGE** — for each phase-declared var, whether its name appears in the
plan's Environment section (falling back to the whole plan if no Environment
section is found). A phase-declared var missing from the plan is a silently
dropped requirement — the gap the round closes by seeding Environment from the
phase union.

Usage::

    python3 env_var_coverage.py <draw_dir>
"""

from __future__ import annotations

import re
import sys

from _load import catalog_nodes, load_deployer_draw, plan_sections, stack_entries

# Conventional env-var token: an uppercase identifier of 3+ chars, allowing
# digits and underscores after the first letter. Excludes trivially short
# all-caps words to cut noise (e.g. "AI", "ID" alone).
_ENV_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")

# Uppercase words that are not env vars but pass the token shape. Pruned so the
# coverage denominator is not inflated by prose.
_ENV_STOPWORDS = frozenset({
    "TODO", "FIXME", "NOTE", "HTTP", "HTTPS", "JSON", "YAML", "HTML", "URL",
    "API", "SDK", "CLI", "AWS", "GCP", "AND", "OR", "THE", "FOR", "USD",
})


def _config_text(phase: dict) -> str:
    tech = phase.get("tech_stack_spec") or {}
    configs = tech.get("configurations")
    if isinstance(configs, list):
        return " ".join(str(c) for c in configs)
    return str(configs or "")


def _extract_vars(text: str) -> set[str]:
    return {
        tok for tok in _ENV_TOKEN_RE.findall(text)
        if tok not in _ENV_STOPWORDS
    }


def _environment_section(draw: dict) -> str:
    sections = plan_sections(draw.get("plan"))
    for key in sections:
        if key.strip().lower().startswith("environment"):
            return sections[key].lower()
    # No Environment section — fall back to the whole plan so a var mentioned
    # elsewhere still counts as surfaced (blunt, favors the plan).
    return (draw.get("plan") or "").lower()


def report(draw_dir: str) -> None:
    draw = load_deployer_draw(draw_dir)
    print(f"env_var_coverage: {draw_dir}")

    phases = draw.get("phases") or []
    if not phases:
        print("  UNMEASURABLE — no phases in draw")
        return
    if draw.get("plan") is None:
        print("  UNMEASURABLE — no deployment-plan.md in draw")
        return

    declared: dict[str, list[int]] = {}
    for p in phases:
        num = p.get("phase_number", "?")
        for var in _extract_vars(_config_text(p)):
            declared.setdefault(var, []).append(num)

    print(f"\n[1] PHASE-DECLARED VARS ({len(declared)})")
    if not declared:
        print("  (no configurations named any env vars across the phase set)")
    for var, phase_nums in sorted(declared.items()):
        pn = ", ".join(str(n) for n in sorted(set(phase_nums), key=str))
        print(f"  {var}  (phase {pn})")

    print("\n[2] STACK-IMPLIED VARS (advisory)")
    hints: list[str] = []
    families = sorted({
        str(n.get("model_family")) for n in catalog_nodes(draw)
        if n.get("model_family")
    })
    if families:
        hints.append(f"AI model_family in use ({', '.join(families)}) → provider "
                     f"API key(s) expected in Environment")
    stack = draw.get("stack") or {}
    auth = (stack.get("security") or {}).get("auth") or []
    if auth:
        hints.append(f"{len(auth)} auth mechanism(s) → auth secret(s)/key(s) expected")
    for e in stack_entries(draw):
        if e["entry"].get("kind") == "infrastructure":
            hints.append(f"infra node '{e['name']}' → connection/credentials likely")
    if not hints:
        print("  (no AI/auth/infra signals implying additional vars)")
    for h in hints:
        print(f"  - {h}")

    print("\n[3] COVERAGE (phase-declared vars vs plan Environment)")
    if not declared:
        print("  no phase-declared vars to measure")
        return
    env = _environment_section(draw)
    covered = 0
    for var in sorted(declared):
        hit = var.lower() in env
        covered += int(hit)
        print(f"  [{'x' if hit else ' '}] {var}")
    print(f"\nCOVERAGE: {covered}/{len(declared)} phase-declared vars appear in the plan")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python3 env_var_coverage.py <draw_dir>")
        raise SystemExit(2)
    report(sys.argv[1])
