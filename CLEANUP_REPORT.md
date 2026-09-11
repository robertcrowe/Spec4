# Spec4 cleanup: the report

This report is for a reader who was not there. Spec4's cleanup ran as the phases of
`SPEC4_CLEANUP_PLAN.md`, on the branch `look-rework`. It is recorded, step by step, in
`CLEANUP_INVENTORY.md`, and every `§` below points into that record.

**The cleanup changed no observable behaviour. Frozen throughout:**
- component ids and the `PATH_TO_PHASE` keys;
- the `.spec4/` artifact shapes and every session key;
- every LLM prompt string;
- `app.py`'s import order, which is load-bearing (D-LR1).

**Status.** The figures are measured at Phase 7's last commit, `90d75c7`, in one session on
2026-09-11, unless a section says otherwise. The plan's last step, folding the record into
a backlog and the final audit (§6), follows after this report is reviewed.

## 1. The gate, paired

Phase 5p's commit (`a86a2ee`) and Phase 7's last commit (`90d75c7`) were measured in the
same session, on the same machine, with the same interpreter, run back to back.
- **How 5p was run:** its tree was extracted with `git archive` into a scratch directory,
  and its own `src/` was put first on the path. A preflight confirmed that each side
  imported its own `spec4`: 5p's has no `run_catalog_phase`, and HEAD's does.
- **What each side collected:** each used its own default. 5p had no `testpaths`, so it
  collects `evals/` too; HEAD has `testpaths = ["tests"]`.

| | Phase 5p, `a86a2ee` | Phase 7 close, `90d75c7` | |
|---|---:|---:|---|
| Tests collected | 4,257 (4,175 `tests/` + 82 `evals/`) | **4,211** (`tests/`) | on the same `tests/` scope: **+36** |
| Passed / skipped | 4,256 / 1 | 4,210 / 1 | |
| Coverage misses | 893 with `evals/` collected; **909** on `tests/` alone | **876** | −33 on the same scope |
| Statements | 12,421 | 12,459 | +38, the new functions and constants of 7k–7q |
| Runtime, pytest-reported, two runs each | 156.18 s, 155.58 s (median **155.88 s**) | 94.88 s, 95.60 s (median **95.24 s**) | **−60.64 s** |
| Ruff, each tree under its own rules | `All checks passed!` | `All checks passed!` | |
| Ruff, both trees under today's promoted rules | 49 findings, all PLR2004 in `src/` | `All checks passed!` | the 49 that 7p cleared |
| mypy `--strict` | `Success: no issues found in 92 source files` | same | |
| `: Any` lines, by 5p's grep | 290 | **232** | −58, Phase 7o |
| Complexity `noqa`s (`C901`) in `src/` | 11 | **9** | §27.4's entries nine and ten, retired by 7q |

**Why the count fell: a change of scope, not a loss.** Phase 6a set
`testpaths = ["tests"]` (§51), so a bare `pytest` stopped collecting the 82 tests under
`evals/`. They were never under the lint gate, and they were not deleted: they still run
when named by path.
- **On the same scope the suite grew:** 4,175 under `tests/` at 5p, and 4,211 now. Phase 6
  added 25 (§59.2) and Phase 7 added 11. No test was deleted in either phase.
- **The misses moved the same way.** 5p's 893 was measured with `evals/` collected, and
  those modules were carrying 16 statements nothing under `tests/` reached. On `tests/`
  alone 5p stands at 909, measured in this session. Phase 6z (§58) brought the 16 back
  under `tests/`, and Phase 7q1's dedupe (§79.1) took the figure from 891 to 876.

**Where the runtime came from.** Nearly all of it came from Phase 6g's chunk factory (§57),
measured on its own at −51.46 s. The `testpaths` change was worth about 0.4 s (§51.1). No
test was pruned for speed: that is forbidden (§3).

**The promoted rules.** Today's rule set is 5p's (E, F, C90, PLR0912, PLR0913, PLR0915,
SIM, B, ARG) plus PLR2004, which was promoted at 7p3. PLR2004 is enforced in `src/`, and
deferred with a recorded size in `tests/` (230 findings), `evals/` (25) and `scripts/` (6).
`uv run ruff check .` passes on the whole repo.

## 2. The findings

These are defects in the safety net itself: places where the suite looked as if it
guarded something and did not. The first four are properties the design depends on that
nothing in the suite would have noticed losing (the record's heading for them is
"invariants the suite assumed rather than pinned"). Each entry names the phase that found
it, and the mutation or measurement that proved it.

### 2.1 `get_agent_gen` passing a copy of the session was caught by nothing

**Found in Phase 7n2 (§74).**
- **What it guards:** every agent turn mutates the one live session dict it is handed; the
  poll later reads those mutations and persists them. If `get_agent_gen` handed an agent
  `dict(session)` instead, every write the turn made would be lost at finalise. That is
  the two-store session model's most basic invariant.
- **Proved by mutation:** 7n2's mutation passed `dict(session)` to the brainstormer's `run`.
  Before 7n2's identity test existed, no test failed. The test now asserts, for all six
  agents, that `run` receives the same session object, and under the mutation it fails.

### 2.2 A session key written from a sibling module was invisible to the whole suite

**Found in Phase 7m (§76).**
- **What it guards:** a restart must leave no Agentifier session key behind (D-TA1). A
  drift guard checked this by reading `agentifier.py`'s source for `"agentifier_*"` keys, so
  a key written from any other module fell outside it. Splitting that file, as 7q was about
  to, would move exactly such writers.
- **Proved by mutation:**
  - **The mutation:** a helper in `_seed.py` writes a key named in neither restart
    collection, called from the draw path.
  - **Against the old tests:** all 4,209 passed, not only the two source-text scans.
  - **Against the new tests:** a scan of the whole package plus a behavioural test at the
    reset seam, and both fail.

### 2.3 No test asserts the Prioritizer banner

**Found in Phase 7q0 (§79.0).**
- **The measurement:** a probe changed one character in `_begin_priority_phase`'s banner,
  text the developer reads at every priority turn. The trace check diverged in 13 tests,
  including all 6 predicted, and all 4,210 tests still passed.
- **Where it went:** the Phase 8 list, as a test item.

### 2.4 Nine tests race their own streaming worker

**Found in Phase 7q0 (§79.0).** It was classified at 7q2 (§79.2).
- **The mechanism:** nine `test_try_again.py` tests call `on_breadth_try_again` without
  patching `streaming.start`, so the draw runs in a worker thread the test never waits for.
  That worker can outlive the test's patches.
- **The measurement:** the first redraw's display state leaks into the second, or does not,
  depending on timing. On the unchanged tree, in three of five traced runs, a second redraw
  reached the **real** Scout and failed on authentication. They are tests with a network
  dependency on a bad day. They pass anyway, because they assert only on the store returned
  synchronously.
- **Where it went:** the Phase 8 list, as a defect.

### 2.5 The per-character `MagicMock` chunk factory cost about 50 seconds

**Found in the Phase 6 pre-work (§50.1). Fixed in 6g (§57).**
- **The cost:** two byte-identical test factories built each streamed LLM chunk as a
  `MagicMock`, one per character. `test_agents.py` alone took 40.65 s.
- **The fix:** `tests/_chunks.py`, a plain-namespace chunk whose fields were read off a real
  `litellm` `ModelResponseStream`. In particular it leaves `usage` absent, as the real type
  does.
- **The measurement:** a paired delta of −51.46 s.
- **And a mutation:** a new test pins that a real usage chunk still reaches
  `_record_usage`. With the factory mutated to ignore `usage`, it fails. Without that
  positive half, a stand-in that could only produce the no-usage shape would have passed
  every negative assertion in the module.

### 2.6 A `streaming.pop` patch whose assertion could not fail

**Found in the Phase 6 pre-work (§50.2). Rewritten in 6c (§53).**
- **The defect:** two tests patched `spec4.callbacks._chat.streaming.pop` and asserted
  `assert_not_called()`. `_chat.py` never calls `pop`, so the assertion could not fail.
- **The invariant it pretended to guard is real,** and written down in `src/` three times:
  the done branch must read the stream entry, not pop it, so that two racing polls return
  the same terminal store.
- **The fix:** the test is rewritten against the real container, with a second test for the
  other half of the contract, that the next `start()` evicts.
- **Proved by mutation:** a stand-in whose `get()` also removes the entry. The old test
  passed under it, which confirmed it was vacuous; the new one failed.

### 2.7 Tests patched stdlib functions for the whole process

**Found in Phase 6b (§52.1). Fixed at the source in 7k (§71).**
- **The defect:** `patch("spec4.project_manager.os.replace")` patches the stdlib `os`
  module's own attribute, so for the duration every `os.replace` in the process raised,
  pytest's own included.
- **The measurement:** during the patch, `os.replace is real_replace` was `False`.
- **The interim fix, 6b:** the patch was scoped through a proxy fixture, `module_seam`.
- **The real fix, 7k:** production seams, the module-level aliases `_replace` and `_fdopen`
  in `_usage.py` and the wrapper `_is_dir` in `project_manager.py`, patched by name. A
  four-way check ran 12/12: transparent unpatched, reached when patched, stdlib real during
  the patch, clean restore. Three mutations each bypass one seam and fail exactly one test.
  `module_seam` was deleted.
- **The same sub-phase found a vacuous assertion:** `test_root_routing.py`'s
  `not directory_opens("/mnt/gone")` held with no patch at all. It now asserts a real
  directory opens, then does not open with the seam raising.

### 2.8 Part of `requires_reconciler` was tested only by an eval

**Found in Phase 6a (§51.2). Fixed in 6z (§58).**
- **The finding:** moving `evals/` out of collection took away the only coverage in the
  repo of 15 statements in `agentifier/requires_reconciler.py` and one in `brainstormer.py`.
  The 15 are the D-RI signal classification, the logic that decides whether a declared
  `requires` edge points the wrong way.
- **The measurement:** coverage. Misses rose from 893 to 909 under `tests/`, and the
  module fell to 90%.
- **The fix:** 22 characterisation tests, one per arm, each paired with a positive
  assertion, so an empty production map cannot satisfy a negative one. `requires_reconciler`
  ends at 97%, two statements better than the eval ever left it.

## 3. The rules

These bound every change the cleanup made. Each is listed with the sub-phase that produced
it.

| Rule | What it says | Produced by |
|---|---|---|
| **Pruning is never justified by seconds** | A test is dropped for redundancy, coupling or vacuity, never for being slow. A test's standalone time is an upper bound on what deleting it saves, and a loose one | §51.6, ruled after 6a. 6a's 82 `evals/` tests cost 2.59 s standalone and 0.4 s inside a full run |
| **Runtime is a paired delta** | Baseline and candidate are measured in the same session, and the recorded figure is the delta. An absolute figure against one from hours earlier is machine weather | §51.6, ruled after 6a's re-baseline, where 4 s of an apparent regression was the machine |
| **Negative assertions are paired with positive ones** | A "does not" assertion needs a "does" beside it, so the negative cannot pass for the wrong reason | Applied in 6g (§57.3) and 6z (§58.3); a standing gate item from §60.6; the worked example is 7k's `:384` test (§71.4) |
| **One mutation per seam, with the amended failure condition** | Every rewrite states the mutation it survives. Under it, the new test must fail and every other failure is listed and explained. A mutation that fails only pre-existing tests is the failure condition | §51.6, ruled after 6c (one per seam, not per site); the failure condition amended at review of 7n1 (§60.6, §73) |
| **An annotation is no narrower than what a test exercises** | A passing test that feeds a value the annotation excludes is a claim the suite disproves. Either the annotation widens, or the question goes to Phase 8 | Ruled at review of 7o; §60.2; applied by 7o5's width sweep (§77.9) |
| **Commits to the record carry only ruled changes** | The record's diff is the audit trail. It is appended through an add-only step that never rewrites existing bytes, and guarded against deleted blank lines | Ruled at review of 7d, after an append collapsed four blank lines (§64.10) |
| **Whole or carry** | An item ruled as one decision is taken whole in its phase, or carried whole to the next, never half-done. A revert keeps the record add-only | §60.7(e), for 7q; confirmed at plan review of 7q |

## 4. The checks, as tools

These are the mechanical checks behind the proofs above.

**They are committed under `scripts/cleanup/`,** whose README gives each one's invocation.
They sit outside the gate and outside mypy. The two that write to `src/` or `tests/` refuse
to run on a dirty tree. `mutate.py` restores what it wrote and verifies the restore by
sha256. `rename_apply.py` keeps its change, but rolls back a failed write and verifies the
rollback the same way. The record's proofs were run from the session's scratchpad, under the
names given in parentheses.

| Check | Tool | What it proves | From |
|---|---|---|---|
| **Substitution (rename) check** | `rename_check.sh`, and `rename_check.py` beside it; `rename_apply.py` makes the rename | Reverse-substitute new → old names on both trees, fold `x as x`, format, diff. Empty means a rename changed nothing else | §60.2; used by every rename commit, 7a–7j and 7q3 |
| **Token check** | `forward_token_check.py` | Every changed token run is an old → new substitution, a layout change or a documented alias; anything else is OTHER. Catches what reverse substitution folds away. Its exit status is informational on seam commits (§60.6) | 7g (§67) |
| **Check 4, in three forms** | `patch_resolve.py`, plus `check4_attr.py` for attribute and lazy-import targets | Every rewritten patch string, whether a `patch("…")` path, a `patch.object`, or a `setattr` / `monkeypatch.setattr`, resolves to the function itself, in the module whose code calls it | Added at 7g; its third form at 7i; the attribute form at 7n2 (§70.11, §74) |
| **Strip-and-compare** | `strip_check.py` | With annotations, PEP 695 type parameters and `if TYPE_CHECKING:` blocks erased from both sides, the ASTs are identical: an annotation-only change is annotation-only | 7o (§77.1); standing for annotation work (§60.2) |
| **Inline check** | `inline_check.py` | With each added constant inlined back to its literal, the AST is identical: a named magic value is that value | 7p (§78) |
| **Frozen strings** | `frozen_strings.py` (`strings_7q.py`) | The set of string constants in a module (prompts, statuses, labels) is unchanged; count changes are listed | 7q1 (§79.1) |
| **Trace identity** | `trace_identity.py` (a pytest plugin; `trace_7q.py`) and `trace_diff.py` | For every test: every chunk delivered, and an insertion-ordered session snapshot at each chunk, is identical to the baseline, at the outermost generator frame. Worker-thread divergences are classified as timing or content | 7q0 (§79.0); its worker rules were ruled at review of 7q1 and at the 7q2 stop (§79.2) |
| **Width sweep** | `width_sweep.py` (a pytest plugin; `sweep_7o.py`) | Every value that reaches an annotated target in the full suite is accepted by its annotation | 7o5 (§77.9) |
| **Floor and off-limits, in both halves** | `floor_check.py` with `data/floor.json` (`floorcheck2.py` with `dnum.json`); `petition_check.py` | The floor: all 456 protected node ids still collect. They are tier A (273, the seven whole-file entries among them) and tier B (183, in 33 classes). A change touching them passes §54.7's golden petition or §60.3's rename petition | §50.3, §50.5(a); petitions §54.7 (6d) and §60.3 |
| **The add-only append and its guard** | `append_section.py` | A record section is appended byte-for-byte, and the prior record is verified as a prefix. `--guard` lists every deleting hunk and fails on a deleted blank line | 7d (§64.10); the guard standing from 7e |
| **Mutation harnesses** | `mutate.py` with `data/cases_7q.json` (`mutate_7*.py`, and 7q0's `probe_7q.py`) | One anchored mutation that must match exactly once, the full suite, predicted failures, a sha256-checked restore | the §60.5 harness rule; the form in 7k–7q |

## 5. Phase 8's list

This is consolidated from the record's Phase 8 list and the deferrals across Phase 7.

### 5.1 Names and seams

- **The rename half is done: 76 names renamed** across ten batches, with one alias dropped
  (§70.11). **Five are held back**, making 81:
  - **Three are net-blocked,** each held by the file that reaches it by attribute:
    - `_start_gen` and `_record_usage`, by `tests/test_streaming_characterization.py`, a
      whole-file entry. Both go in one petition, when that file is next legitimately
      opened;
    - `_with_readme_attribution`, by `tests/test_project_manager_golden.py`, a whole-file
      entry.
  - **Three wait on the `project_manager` root-siblings inconsistency** (§27.7, §60.7(f)):
    `_write_text_if_changed` (4 sites), `_phase_spec_preamble` (1) and
    `_with_readme_attribution` (4). The last is in both lists.
- **The seam shapes are proven, and one application remains.**
  - **The shapes:**
    - production aliases for stdlib calls under test (7k, three seams);
    - promotion with a session contract (7n, three seams);
    - the driver-over-steps generator with a single-meaning `None` (7q, eight generators).
  - **The remaining application: §27.4's three other backlog turns,** `deployer.run` (185
    lines), `brainstormer.run` (101) and `code_scanner.run` (175). Each still carries a
    rule-12 `noqa`, and `trace_identity.py` is ready to trace them: `TRACE_MODULE` and
    `TRACE_FAMILY` name the module and its functions.
  - **The alternative not taken:** a step sentinel that tells a step's ending causes apart.
- **Not promote targets:** the 24 `keep: subject is the private object` names (§54.1,
  §55.4). The collection is each test's subject.
- **Dedupes:**
  - `revision_delta`'s five copies, a straight lift to `_utils` (§67.11);
  - the mechanism-summary trim, written twice (§78.2).
- **Not scheduled:** the `sys.modules` lookup in `test_cost_summary.py`, now scaffolding
  for a shadow that no longer exists (§64).

### 5.2 Types (§77.8)

- the session-dict edge (90 `: Any` lines) and the JSON-artifact edge (107), as `TypedDict`
  design;
- the 107 prop-bound callback inputs on mixed lines;
- the 148 `-> Any` return lines outside the grep;
- `object` for `_as_int` and `round_number_from_value`, and `run_with_timeout`'s generic
  form, which needs a runtime TypeVar;
- **a question:** should `_fmt_usd` accept `str`? A passing test pins that it does
  (`tests/test_cost_summary.py:160`).

### 5.3 Tests

| Item | Size | Source |
|---|---|---|
| The nine racing tests: patch `streaming.start`, or wait for the stream | 9 tests; a defect | §79.0, §79.2 |
| The Prioritizer banner | 1 assertion | §79.0 |
| Documented contract keys the suite never saw change | 31 keys across 4 generators: one contract test each | §79.3 |
| Annotated targets no test reaches: `on_designer_generate_mock` ×3, `on_provider_hint`, `_designer_tool_call_followup` | 3 functions | §77.9 |
| Feature-spec section guards: `> 2` against its siblings' `> 3`. Check that real output reaches it before deciding | 3 builders | §78.2 |
| PLR2004, deferred with a size | 230 in `tests/`, 25 in `evals/`, 6 in `scripts/` | §78.4 |

### 5.4 The tooling itself

Whether to bring §4's checks inside: into the gate, and under mypy. They are committed under
`scripts/cleanup/`, outside both.

## 6. Still to do, after review: the fold and the final audit

This is the plan's last phase (`SPEC4_CLEANUP_PLAN.md`, Phase 7 "Final audit and
documentation"). It is not yet done.
- **Re-run Phase 0's measurements:** `uvx vulture`, `uv run --with deptry deptry .`, the ruff
  rule-set statistics and the layering contract. Add them here as before/after: the
  file-size table, coverage per module, and dead-code candidates, which should be zero or
  justified.
- **Walk the seven original symptom categories** as a checklist, each with what was found
  and what was done.
- **Update `tests/README.md`:** a coverage table without line numbers, the golden and
  snapshot mechanism, the two environment variables, `testpaths` and `tests/_chunks.py`.
  Also update `README.md`'s project tree, and `CLAUDE.md` if the repo carries one.
- **Fold `CLEANUP_INVENTORY.md`** into a `BACKLOG.md`: §5 above, the record's bugs-found
  entries, and the two existing horizon items (CodeScanner incremental scan, Designer mock
  capture).
