"""Phase-set probe: ``status`` semantics (D-PH0e).

Dev tooling under ``evals/``. Never wired into the pipeline.

``status: mvp|optional|deferred`` (StackAdvisor D-SC48) marks a stack entry as
roadmap rather than build item when it is ``optional`` or ``deferred``. A phase
set that turns such an entry into a build instruction has recreated the
pre-D-SC48 defect downstream. This probe reads a saved draw directory and
reports, for every status-bearing stack entry (libraries, persistence stores,
collections, integrations, infrastructure — anything the walker finds):

* ``VIOLATION`` — an ``optional``/``deferred`` entry whose name appears in a
  phase's build surface (``tech_stack_spec.dependencies`` + ``instructions``).
  The name join is the suite's blunt lexical match; each hit names the phases.
* ``CLEAN`` — an ``optional``/``deferred`` entry mentioned by no phase's build
  surface.
* ``mvp``-status entries are counted but not checked (mvp is a build item).

Known limit, carried from the D-SC48 drop-branch inverse: an entry the model
*dropped from the JSON* instead of shipping with ``status`` is invisible here —
its deferral exists only in the transcript. This probe checks what the stack
declares; the conditionality check (``evals/stack_advisor/decision_loss.py``)
owns the drop branch. Until that defect class is closed upstream, a CLEAN
report does not mean ``status`` coverage is complete.

Usage::

    python3 status_check.py <draw_dir>
"""

from __future__ import annotations

import sys

from _load import load_draw, name_matches, phase_build_text, stack_entries

ROADMAP_STATUSES = ("optional", "deferred")


def report(draw_dir: str) -> None:
    draw = load_draw(draw_dir)
    print(f"status_check: {draw_dir}")
    if not draw.get("stack"):
        print("  UNMEASURABLE — no stack.json in draw")
        return
    if not draw["phases"]:
        print("  UNMEASURABLE — no phase files in draw")
        return

    bearing = [e for e in stack_entries(draw) if e["entry"].get("status")]
    if not bearing:
        print("  no status-bearing stack entries")
        return

    mvp = [e for e in bearing if str(e["entry"]["status"]) not in ROADMAP_STATUSES]
    roadmap = [e for e in bearing if str(e["entry"]["status"]) in ROADMAP_STATUSES]
    print(
        f"  status-bearing entries: {len(bearing)} "
        f"({len(roadmap)} optional/deferred, {len(mvp)} other)"
    )

    violations = 0
    for e in roadmap:
        status = e["entry"]["status"]
        hit = sorted({
            p["phase_number"]
            for p in draw["phases"]
            if isinstance(p.get("phase_number"), int)
            and name_matches(e["name"], phase_build_text(p))
        })
        if hit:
            print(
                f"  VIOLATION  {e['label']} (status: {status}) appears in the "
                f"build surface of phases {hit}"
            )
            violations += 1
        else:
            print(f"  CLEAN      {e['label']} (status: {status})")
    print(f"  violations: {violations}/{len(roadmap)} roadmap entries built")
    print(
        "  note: entries dropped from the JSON instead of shipped with status "
        "are invisible here (D-SC48 drop-branch inverse; see decision_loss.py)"
    )


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    report(sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())