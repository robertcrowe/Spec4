"""Deployment-plan probe: status / roadmap discipline (D-DE1 / D-DE9).

Dev tooling under ``evals/``. Never wired into the pipeline.

StackAdvisor marks each provisionable entry with ``status``: ``mvp`` (build
now), ``optional``, or ``deferred`` (roadmap, not this build). A deployment
plan that provisions a ``deferred`` store recreates the pre-D-SC48 defect one
stage downstream. This probe checks the discipline in both directions:

**[1] MVP ENTRIES** — every ``status: mvp`` entry that carries a name; these
*should* be reachable in the plan (informational — low coverage here is a
signal-not-consumed gap, not a violation).

**[2] DEFERRED / OPTIONAL ENTRIES** — every ``status: deferred`` or ``status:
optional`` entry. For each, whether its name appears in a *provisioning*
context in the plan. "Provisioning context" is approximated by presence in the
Deployment Steps, Terraform, or Configuration Files sections (where build items
live); appearance only in a Notes / roadmap section is fine and is reported as
CORRECTLY RECORDED. A deferred entry appearing in a provisioning section is a
⚠ VIOLATION to inspect — the plan is building something the stack said to defer.

This is a blunt containment check, so a VIOLATION is a flag for human review,
not a proof; but a deferred store named inside a Terraform block is exactly the
failure the probe exists to catch.

Usage::

    python3 status_roadmap.py <draw_dir>
"""

from __future__ import annotations

import sys

from _load import load_deployer_draw, name_matches, plan_sections, stack_entries

# Sections where a named resource means "we are building/provisioning this".
_PROVISIONING_SECTIONS = (
    "deployment steps", "terraform", "configuration files", "containerization",
)
# Sections where a named resource means "recorded for later", which is correct.
_ROADMAP_SECTIONS = ("notes",)


def _sections_lower(draw: dict) -> dict[str, str]:
    return {k.lower(): v.lower() for k, v in plan_sections(draw.get("plan")).items()}


def _in_any(name: str, sections: dict[str, str], prefixes: tuple[str, ...]) -> bool:
    for key, body in sections.items():
        if any(key.startswith(p) for p in prefixes) and name_matches(name, body):
            return True
    return False


def report(draw_dir: str) -> None:
    draw = load_deployer_draw(draw_dir)
    print(f"status_roadmap: {draw_dir}")

    if not draw.get("stack"):
        print("  UNMEASURABLE — no stack.json in draw")
        return
    if draw.get("plan") is None:
        print("  UNMEASURABLE — no deployment-plan.md in draw")
        return

    sections = _sections_lower(draw)
    mvp: list[str] = []
    roadmap: list[tuple[str, str]] = []
    for e in stack_entries(draw):
        status = str(e["entry"].get("status") or "").lower()
        name = e["name"]
        if status == "mvp":
            mvp.append(name)
        elif status in ("deferred", "optional"):
            roadmap.append((name, status))

    print(f"\n[1] MVP ENTRIES ({len(mvp)})")
    if not mvp:
        print("  (no status:mvp entries)")
    for name in sorted(set(mvp)):
        hit = name_matches(name, (draw.get("plan") or "").lower())
        print(f"  [{'x' if hit else ' '}] {name}")

    print(f"\n[2] DEFERRED / OPTIONAL ENTRIES ({len(roadmap)})")
    if not roadmap:
        print("  (no deferred/optional entries — nothing to keep out of the build)")
    violations = 0
    for name, status in sorted(set(roadmap)):
        in_build = _in_any(name, sections, _PROVISIONING_SECTIONS)
        in_roadmap = _in_any(name, sections, _ROADMAP_SECTIONS)
        if in_build:
            violations += 1
            print(f"  ⚠ VIOLATION  {name} ({status}) — named in a provisioning "
                  f"section; the stack said to defer this")
        elif in_roadmap:
            print(f"  CORRECTLY RECORDED  {name} ({status}) — in Notes/roadmap only")
        else:
            print(f"  ABSENT  {name} ({status}) — not provisioned (fine)")

    print(f"\nVIOLATIONS: {violations} deferred/optional entr"
          f"{'y' if violations == 1 else 'ies'} provisioned as build item"
          f"{'' if violations == 1 else 's'}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python3 status_roadmap.py <draw_dir>")
        raise SystemExit(2)
    report(sys.argv[1])
