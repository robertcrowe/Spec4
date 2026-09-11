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
documentation"). Its first item is done, and §7 holds the results. The other three are not.
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

## 7. Phase 0, re-measured

These are Phase 0's measurements (`CLEANUP_INVENTORY.md` §1–§8) re-run at `85a9cb6`, with
the same commands and the same tool versions, and compared with the Phase 0 tree
(`1d1dcbd`). They show whether the cleanup did what Phase 0 said it needed to.

### 7.1 The conclusion

**On every measure Phase 0 took, the cleanup did what Phase 0 said was needed, except
one. That one is the weakness Phase 0 found first.**

- **The gate is green where Phase 0 found it red on three of five checks.** Phase 0 had
  one failing test, 130 unformatted files and 30 mypy errors. The gate now also enforces
  complexity, branch, argument, statement, magic-value, `SIM`, `B` and `ARG` rules. At
  Phase 0 it enforced only `E` and `F`.
- **Complexity is down to reasoned exceptions.**
  - The findings fell from 151 to 30, and every one of the 30 carries a reasoned `noqa`.
  - The worst cyclomatic complexity fell from 61 to 24.
  - Files over 1,300 lines went from 8 to 2.
  - The longest function went from 659 lines to 185.
- **Dead code is zero or justified.**
  - Every remaining vulture line has its reason in the record.
  - So does every public name with no reference outside its file.
  - deptry has no real finding left.
- **The one import cycle is gone,** and a test pins the layering.
- **Coverage rose from 91% to 93%,** with misses down from 1,020 to 876. Every family of
  split modules rose. Of the 51 modules at the same path, one fell: `pattern_loader.py`,
  by 0.2 points, because three of its covered statements were deleted.
- **The exception: the UI callbacks are still the least-covered code.**
  - Phase 0's six lowest-covered modules are still the six lowest families, at 76.5% to
    83.9%.
  - `callbacks/designer/_wizard.py` is at 49.6%.
  - Phase 1's net for this layer was contract tests: the component-id snapshot, goldens,
    and state containers. They pin the layer's shape, not its branches. No later phase
    targeted the gap.
- **Two things are still open.**
  - `tests/test_agents.py` is 5,268 lines. Phase 0 named it a split candidate, and §50 did
    again. No phase took it up or ruled on it.
  - §27.4's three backlog turns are on Phase 8's list (§5.1).

### 7.2 How it was measured

- **The tool versions are Phase 0's:** ruff 0.15.12, vulture 2.16 and deptry 0.25.1, all
  run through `uvx` as Phase 0 ran them. Each tool was run on both trees, so each
  before/after pair comes from the same tool; the Phase 0 tree was extracted with
  `git archive 1d1dcbd`. Run on that tree, both reproduce Phase 0's recorded figures:
  - deptry: 246 findings (240 / 3 / 3);
  - ruff's complexity statistics: 151;
  - ruff's `ARG` statistics: 171, read with `noqa` respected as Phase 0 read them.
- **§2, §6, §7 and §8 were ast and grep walks, and were re-implemented.** The
  re-implementation was checked first on the Phase 0 tree, where it reproduces every
  recorded figure:
  - 60 files and 36,535 lines;
  - the one cycle;
  - the importer counts, 21 and 18;
  - the cross-reference counts: 279, 228, 51, 33, 18 and 214.

  Two conventions had to be matched to get there:
  - an empty file counts as one line;
  - `from P import m` is an edge to P as well as to `P.m`.
- **One figure does not reproduce exactly.** Vulture finds 70 lines on the Phase 0 tree
  without the whitelist, where §3.1 recorded 71.
- **Coverage was not re-run on the Phase 0 tree.** Its per-module figures are §1.3's.
- **Runtime is not compared with Phase 0.** The Phase 0 figure is from another session
  and the comparison would not be paired (§3's rule). §1's paired delta is the runtime
  figure.

### 7.3 The gate

| Check | Phase 0 (`1d1dcbd`) | Now (`85a9cb6`) |
|---|---|---|
| Tests | 1 failed, 4,116 passed, 1 skipped (4,118 collected) | 4,210 passed, 1 skipped (4,211) |
| Coverage, `--cov=spec4` | 11,676 statements, 1,020 missed, 91% | 12,459 statements, 876 missed, 93% |
| `ruff check src/ tests/` | clean under `E`, `F` | clean under `E`, `F`, `C90`, `PLR0912`/`0913`/`0915`, `PLR2004`, `SIM`, `B`, `ARG` |
| `ruff format --check src/ tests/` | 130 would be reformatted, 50 formatted | 221 formatted, none to reformat |
| `mypy src/` (strict) | 30 errors in 13 files, 60 checked | no errors, 92 checked |

### 7.4 Coverage per module

**The modules Phase 4 split, compared as families:** each Phase 0 module against the sum
of the modules it became.

| Phase 0 module | Phase 0 | Now | Became |
|---|---|---|---|
| `agentifier/agentifier.py` | 1,413 / 165 / 88.3% | 1,509 / 139 / 90.8% | 4 modules (4i) |
| `agents/_utils.py` | 1,092 / 71 / 93.5% | 1,222 / 71 / 94.2% | 5 modules (4a) |
| `project_manager.py` | 758 / 30 / 96.0% | 817 / 20 / 97.6% | 5 modules (4b) |
| `callbacks/__init__.py` | 681 / 157 / 76.9% | 734 / 157 / 78.6% | 7 modules (4g, 4g2) |
| `agents/code_scanner.py` | 622 / 68 / 89.1% | 682 / 21 / 96.9% | a package of 4 (4c) |
| `callbacks/designer.py` | 427 / 113 / 73.5% | 463 / 109 / 76.5% | a package of 4 (4h) |
| `agents/stack_advisor.py` | 399 / 35 / 91.2% | 455 / 8 / 98.2% | a package of 4 (4d) |
| `agents/phaser.py` | 301 / 8 / 97.3% | 355 / 8 / 97.7% | a package of 4 (4e) |
| `layouts/_chat.py` | 181 / 2 / 98.9% | 224 / 1 / 99.6% | 4 modules (4f) |

(Statements / missed / cover.) Every family rose.

**The 51 modules at the same path:** 20 rose, 30 are unchanged, and one fell.
- **The one that fell** is `agentifier/pattern_loader.py`, from 88.9% to 88.7%. Its misses
  stayed at 18. Its statements fell from 162 to 159, because Phase 2 deleted three covered
  statements: the unread dataclass fields in §13.2's items 2 and 3.
- **The largest rises:**
  - `agents/brainstormer.py`, 90.7% to 97.1%;
  - `layouts/__init__.py`, 90.0% to 96.2%.

**The lowest-covered code now:**

| Module | Cover |
|---|---:|
| `callbacks/designer/_wizard.py` | 49.6% |
| `spec4/__init__.py` (5 statements) | 60.0% |
| `callbacks/_nav.py` | 62.2% |
| `callbacks/_chat.py` | 74.5% |
| `agents/_turn_flow.py` | 75.4% |
| `feature_specs.py` | 76.7% |
| `callbacks/__init__.py` | 78.3% |
| `callbacks/_artifacts.py` | 78.6% |
| `callbacks/designer/_refine.py` | 80.0% |
| `websearch.py` | 80.5% |

Phase 0's six lowest, the Phase 1 targets, are all still below 84%:

| Module | Phase 0 | Now |
|---|---:|---:|
| `callbacks/designer` family | 73.5% | 76.5% |
| `feature_specs.py` | 75.5% | 76.7% |
| `callbacks/__init__` family | 76.9% | 78.6% |
| `websearch.py` | 78.7% | 80.5% |
| `session.py` | 81.6% | 82.7% |
| `providers.py` | 82.8% | 83.9% |

### 7.5 Dead code

**vulture** (`uvx vulture src/ tests/ --min-confidence 60`):

| | Phase 0 | Now |
|---|---:|---:|
| Without the whitelist | 70 (`src/` 48, `tests/` 22) | 60 (`src/` 37, `tests/` 23) |
| With `vulture_whitelist.py` | 32 (`src/` 10, `tests/` 22) | 26 (`src/` 3, `tests/` 23) |

**Every one of the 26 is justified in the record:**
- **`src/`, 3:** the `DesignerSession` TypedDict keys `preference_text`, `mock_html` and
  `finalized`. They are read by subscript, which vulture cannot see (§13.3).
- **`tests/`, 14:** mock attribute assignments (§13.3).
- **`tests/`, 4:** the `tavily_key` slots in stubs that match `_start_gen`'s positional
  signature (§13.3).
- **`tests/`, 1:** the `return; yield` empty-async-generator idiom (§13.3).
- **`tests/`, 4:** autouse fixtures.
  - `_clean_sink`, `_clean_state` and `_clean_containers` are justified in §13.3.
  - `_clean_streams` is new since Phase 2 (`tests/test_callbacks_stream_poll.py:149`). It
    is `@pytest.fixture(autouse=True)`, the same pattern.

**ruff `--select F401,F811,F841,ARG`**, with `noqa` respected as Phase 0 read it:
- **`src/`:** 9 → 0.
- **`tests/`:** 162 → 178 (`ARG001` 113, `ARG005` 48, `ARG002` 17). Test-side `ARG` is stub
  and fixture signatures. It is not a cleanup target (§3.2, §13.6), and it sits under
  `tests/`'s per-file ignore.
- **`F401`, `F811`, `F841`:** none at either end. Three re-export `F401`s carry a `noqa`
  in both trees.

**§7's cross-reference:** every top-level `def` and `class`, against the files that mention
it.

| | Phase 0 | Now |
|---|---:|---:|
| Top-level definitions | 829 | 1,093 |
| With no reference outside their own file | 279 | 513 |
| of which private | 228 | 457 |
| of which public | 51 | 56 |
| of the public ones: Dash callbacks | 33 | 32 |
| of the public ones: the review list | 18 | 24 |
| Referenced only from `tests/`, `evals/` or `scripts/` | 214 | 135 |

**None of the 24 on the review list is dead.**
- 17 are Phase 0's list. Phase 2 re-grepped each one and found callers in its own module
  (§13.3). The splits moved some, for example `RoundsOnDisk` to `_paths.py` and
  `PriorityEdits` to `agentifier/_render.py`.
- Phase 0's eighteenth, `download_button_id`, was deleted (§13.2).
- The 7 new names are public functions of 4a's split, each used by its own module
  (§25.7): `ai_served_feature_ids`, `designer_affordance_hints`,
  `project_feature_for_stack`, `served_product_feature_ids`, `short_text`,
  `render_one_style` and `stale_phrase`.

Making any of the 24 private would be a rename.

### 7.6 Dependencies

**`uvx deptry .`, Phase 0's form:** 246 findings then, 347 now.

| Rule | Phase 0 | Now |
|---|---:|---:|
| DEP001: the project's own `spec4` imports | 210 | 314 |
| DEP001: `evals/` sibling imports | 29 | 29 |
| DEP001: `yaml` | 1 | 1 |
| DEP002 | 3 | 0 |
| DEP004 | 3 | 3 |

- **There is no real finding left.**
  - DEP002 is gone. `dash-iconify` was removed (§13.2). `gunicorn` and `pyyaml` are
    suppressed in `pyproject.toml`, each with its reason.
  - DEP004 is the same three dev-only imports Phase 0 accepted: `pytest` in two
    `evals/scout/` files, and `playwright` in `scripts/screenshot_ui.py`.
- **Most of DEP001 is noise.** deptry run from an isolated cache cannot see `spec4`
  installed, so each of the project's own imports is reported. There are more of them now
  because there are more modules. `yaml` is the pyyaml name-mapping false positive §4
  noted: §4 counted "30 sibling-module imports inside `evals/`", and one of the 30 is this
  line.
- **The plan's Phase 7 form, `uv run --with deptry deptry .`,** reports the same findings
  with the noise moved: DEP001 29 (`evals/` only), DEP003 314, DEP004 3.
- **`scripts/cleanup/` adds nothing.** deptry's output was byte-identical before and after
  the tools went in.

### 7.7 Complexity and size

**ruff `--select C90,PLR0912,PLR0913,PLR0915,SIM,B src/`,** with `noqa` ignored so that
what the gate accepts still counts:

| Rule | Phase 0 | Now |
|---|---:|---:|
| `C901` complexity | 61 | 9 |
| `PLR0912` branches | 40 | 6 |
| `PLR0915` statements | 25 | 3 |
| `PLR0913` arguments | 12 | 12 |
| `B` (`B905`, `B904`, `B007`) | 7 | 0 |
| `SIM` (`SIM105`, `SIM117`, `SIM905`) | 6 | 0 |
| **Total** | **151** | **30** |

- **Every one of the 30 carries a reasoned `noqa`.**
- **`PLR0913` is the same twelve signatures,** most of them moved by the splits. Their
  argument counts match one for one.
- **The most complex functions:**
  - At Phase 0, the ten worst ran from 61 (`_format_stack_as_text`) down through 39, 38
    (`_run_catalog_phase`) and 33 to 23.
  - Now, nine functions are over the threshold: `stream_turn` 24, `deployer.run` 21,
    `_validate_frontmatter` 17, `brainstormer.run` 14, `_artifact_button_state` 13,
    `code_scanner.run` 12, `_spec_field` 12, `_validate_dependencies` 11 and `_has_cycle`
    11.

**File sizes** (§2's table, same method):

| | Phase 0 | Now |
|---|---|---|
| `src/spec4/` | 60 files, 36,535 lines | 92 files, 40,284 lines |
| Files over 1,300 lines | 8 | 2: `agentifier/agentifier.py` 2,874, `agents/_feature_context.py` 1,329 |
| Longest functions | `_run_catalog_phase` 659, `phaser.run` 499, `deployer.run` 343, `brainstormer.run` 236 | `deployer.run` 185, `code_scanner.run` 175, `stream_turn` 174, `chat_layout` 163 |
| `tests/` | 120 files, 53,705 lines | 129 files, 56,534 lines |
| Largest test file | `test_agents.py`, 5,284 lines, 333 functions | `test_agents.py`, 5,268 lines, 332 functions |

- **`agentifier/agentifier.py` is still the largest file.** 4i kept the generator flow
  there, and 7q moved no code out of it (§79).
- **The two longest functions are two of §27.4's backlog turns,** which are on Phase 8's
  list.
- **`tests/test_agents.py` was never split.** Phase 0 named it a split candidate, and §50
  did again, noting that its runtime was the chunk factory (fixed in 6g) and "not a reason
  to split it". No sub-phase took it up or ruled on it.

### 7.8 The import graph and module state

| | Phase 0 | Now |
|---|---|---|
| Modules | 60 | 92 |
| Cycles | 1: `layouts` ↔ `layouts._chat` | 0, closed at 4f (§21) |
| Layer violations: lower layers → UI; `layouts` → `callbacks`/`app`; anything → `app` | 0 | 0, pinned since Phase 4 by `tests/test_import_layering.py` |
| Importers of `llm` / `project_manager` | 21 / 18 | 21 / 23 |
| Import edges only under `TYPE_CHECKING` | 0 | 3 (7o) |
| `global` statements | 0 | 0 |

- **§6.2's seven lazy couplings are all still there,** relocated by the splits. For
  example, `callbacks` → `agentifier.agentifier` is now `callbacks._chat` →
  `agentifier.agentifier`.
- **Phase 3 classified §8's eight module-state items** and fixed item 1's unlocked writes
  (§14).
