# AGENTS.md — Spec4

Spec4 finished a nine-phase cleanup (Phases 0–8). These rules keep it clean.
They apply to every edit, not only refactors.

The cleanup's records — `CLEANUP_INVENTORY.md`, `PHASE8_RECORD.md`,
`CLEANUP_REPORT.md`, `SPEC4_CLEANUP_PLAN.md` — live at tag `cleanup-complete`
(`git show cleanup-complete:<file>`). Comments in the code cite them by
section (`§54.7`) or sub-phase (`7g`, `pre-4j`) as the reason code is the way
it is; those references resolve at the tag. New comments may cite the same
way; don't put a filename in every comment. What the product still depends on
is folded into `scripts/cleanup/README.md` (the floor, the tools).

## The gate is the definition of done

A change is done when all of these pass, and not before:

    uv run ruff check .
    uv run ruff format --check src/ tests/
    uv run mypy src/            # strict
    uv run pytest --cov=spec4 --cov-report=term-missing -q
    uv run python scripts/cleanup/floor_check.py

- Coverage misses may not rise above the figure at HEAD. New code arrives
  with its tests; a new line no test reaches is not done.
- `floor_check.py` must report 456/456 with no failures. The node ids in
  `scripts/cleanup/data/floor.json` are the regression net. They are not
  edited, renamed, moved, or deleted without a petition — the shapes are in
  `scripts/cleanup/README.md`.
- Never push a red tree. Never skip, xfail, or delete a test to get green.

## Lint findings are decisions, not noise

- The promoted ruff rules stay promoted. A rule already at zero stays at zero.
- A `noqa` needs a reason on the same line saying why the code is that way.
  A `noqa` without a reason is a defect.
- Complexity limits: C901 ≤ 10, branches ≤ 12, statements ≤ 50, arguments ≤ 5.
  A long turn generator that can't meet them is split as a *driver over
  steps* — see `agentifier.py` above `run_catalog_phase` for the convention
  (`yield from _step(...)`; `None` means only "the turn ended inside the
  step"; a step with no product returns `Literal[True] | None`). Don't add a
  complexity waiver; use the shape.
- Magic numbers in `src/` become named constants (PLR2004). Structural
  numbers (a tier's index, a wizard step) get a reasoned `noqa`.

## Typing

- Strict mypy, always. No new `Any` on a parameter or return unless the value
  is `Any` at its source in a dependency's own signature — say so in a comment.
- The session dict stays untyped (design limit). Don't add
  a TypedDict for it or for the Designer store.
- Type-only imports go under `if TYPE_CHECKING:`. Generic functions use
  PEP 695 syntax, not a module-level `TypeVar`.
- An annotation may not be narrower than what an existing test exercises.

## Session keys and state

- No new module-level mutable state. Anything that must survive across turns
  goes in the session, and the writing function's contract docstring says
  which keys it writes, where it hands off, and how it counts characters.
- A new `agentifier_*` key joins `_RESTART_DEFAULTS` or `_RESTART_POP` in
  `agentifier.py`, or the drift guard in `tests/agentifier/test_try_again.py`
  fails. That failure is correct; fix the collection, not the test.
- The two-store session model is one design. Never hand an agent a copy of
  the session; `get_agent_gen`'s identity test pins this.

## Tests

- A negative assertion over a map, list, or set is paired with a positive
  one, so an empty result can't satisfy the test.
- A test's name may not promise more than its assertions check.
- Never patch a stdlib function process-wide (`os.replace`, `Path.is_dir`,
  `time.sleep`). Patch the module-level seam by name (`_usage._replace`,
  `project_manager._is_dir`). If the seam doesn't exist, add one in `src/`
  beside the call, following those two.
- Never patch `streaming.start` to avoid a worker. Wait on the worker thread
  with a bounded join and assert it finished before asserting terminal state.
- Set file mtimes with `os.utime`; never sleep and hope.
- No `inspect.getsource` or source-text regex except the drift guards that
  already exist.
- `patch("…")` and `patch.object` strings name the module that *calls* the
  function, not one that re-exports it.
- New test files follow the per-module split (`tests/test_<module>.py`).
  Shared helpers live in `tests/_agent_helpers.py` and `tests/_chunks.py`.
  Don't merge test files for tidiness.

## Layout

- Concern modules live inside their package (`project_manager/_usage.py`),
  not as root siblings.
- Public names have no underscore. A private name reached by a test is a
  smell: either the test uses the public seam or the helper gets promoted.
  The exception is a designed patch point (`_replace`, `_is_dir`) or a
  collection that is itself the subject under test (`_RESTART_DEFAULTS`).
- Don't touch `.spec4/` (recorded model output) or `evals/` (outside the
  gate) in a code change.

## Refactors

Anything that moves, renames, or splits code uses the tools in
`scripts/cleanup/` — substitution check, token check, patch-string
resolution, strip-and-compare for annotations, frozen strings, trace
identity, the move petition — and records the proof in the commit message
or PR. Read `scripts/cleanup/README.md` first, including its known limits.
Behaviour-preserving means byte-identical yielded strings, session writes,
and call order; the trace harness is how that's shown, not the suite alone.
Trace baselines are commit-bound; re-baseline before comparing.

## Don't

- Don't re-add `module_seam`, the `sys.modules` idiom in tests, or a
  `TypeVar` where PEP 695 syntax works.
- Don't justify deleting a test by runtime. Redundancy, coupling, or vacuity
  only — and redundancy is shown by a mutation caught by another test.