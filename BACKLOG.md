# Backlog

This file was folded from `CLEANUP_INVENTORY.md` at the end of the cleanup
(`SPEC4_CLEANUP_PLAN.md`, Phase 7). From the fold on, the record is history and this file
is live. It has two parts:
- **Part 1, Phase 8:** the cleanup's continuation. It is the list `CLEANUP_REPORT.md` §5
  consolidated, plus what has been ruled since.
- **Part 2, Backlog:** product and design work the cleanup found or named, but which is not
  cleanup.

Section numbers (§N) refer to `CLEANUP_INVENTORY.md`. The tools named below are in
`scripts/cleanup/`, and its README gives their invocations.

## Part 1: Phase 8

### 1.1 Names and seams

- **The five held-back renames are settled** (Phase 8: `PHASE8_RECORD.md` §19.1, §22,
  §23). The other 76 were renamed across ten batches (§61–§70).
  - **The root-siblings inconsistency is resolved** (§27.7, §60.7(f)). D7a made
    `project_manager` a package, with its four siblings inside it.
  - **Two were renamed at D7b:** `write_text_if_changed` and `phase_spec_preamble`.
  - **Three stay private, by ruling. Closed:**
    - `_with_readme_attribution` (D7). Its four sites in
      `tests/test_project_manager_golden.py`, a whole-file entry, are attribute calls,
      not import lines, so §54.7's import-only petition cannot be met.
    - `_start_gen` and `_record_usage` (D8). Renaming them would open
      `tests/test_streaming_characterization.py`, a Phase 1 characterization file whose
      job is to be untouched.
- **§27.4's three backlog turns are done** (8i1–8i3: `PHASE8_RECORD.md` §14, §16, §17).
  `brainstormer.run`, `code_scanner.run` and `deployer.run` are each a driver over steps,
  in 7q's shape (§79), and their rule-12 `noqa`s are deleted.
  - **The step sentinel stays not taken. Closed (D6).** No step generator in the four
    turns split so far needed two ending causes: agentifier's 10 from 7q, and 8i's 10.
  - It reopens if one does, and the plan says how (§79; `PHASE8_RECORD.md` §1.5).
- **Not promote targets:** the 24 `keep: subject is the private object` names (§54.1,
  §55.4). The collection is each test's subject.
- **The two dedupes are done:**
  - `revision_delta`'s five copies (§67.11) are one body in `agents/_revision.py`, which
    the five import (8d2: `PHASE8_RECORD.md` §7);
  - the mechanism-summary trim (§78.2) is one helper, `pattern_loader.trimmed_description`
    (8d: `PHASE8_RECORD.md` §6).
- **The `sys.modules` lookup in `test_cost_summary.py` is removed** (§64; D4:
  `PHASE8_RECORD.md` §20).

### 1.2 Types (§77.8)

- **The session-dict edge** (90 `: Any` lines) and **the JSON-artifact edge** (107), as
  `TypedDict` design. D14 added the returns' edges to this count: 82 session-edge and 40
  source-edge returns (`PHASE8_RECORD.md` §21.2).

**Done in Phase 8:**
- **the 107 prop-bound callback inputs:** 105 typed by their prop, and 2 load-bearing (8h:
  `PHASE8_RECORD.md` §12). The 39 that no test reaches are in 2.1.
- **the `-> Any` returns, counted by AST:** 144 bare returns (the 148 was a grep of lines).
  - 14 were typeable, and were taken, so 130 remain (D14: `PHASE8_RECORD.md` §21).
  - The 130 are the 122 edges above and 8 load-bearing.
- **`object` for `_as_int` and `round_number_from_value`, and `run_with_timeout`'s PEP 695
  form** (8b: `PHASE8_RECORD.md` §4).
- **`_fmt_usd`:** no production caller passes a string, so its annotation was narrowed (8b:
  `PHASE8_RECORD.md` §4.2).

### 1.3 Tests

| Item | Size | Source |
|---|---|---|
| Tests that assert less than they claim, and a path no test reaches. Four tests name an event and still pass when it never happens, each under a turn's forbidden-`None` mutation: `test_brainstormer.py::TestBrainstormer::test_non_vision_response_stays_in_progress`, `::TestBrainstormerUnparseableArtifact::test_failed_reask_leaves_no_dead_end_user_turn`, `::TestBrainstormerUnparseableArtifact::test_state_is_not_advanced_when_both_attempts_fail`, and `test_code_scanner_progress.py::TestCharsTotal::test_total_is_monotonic_across_the_handover`. The path is `code_scanner.run`'s recap fall-through, reached by 0 of 43 traced invocations | 4 tests, 1 path | `PHASE8_RECORD.md` §14.2, §16, §17; `CLEANUP_REPORT.md` §2.4a |

**Closed in Phase 8, and out of this table:**
- the nine racing tests (§79.0, §79.2), which now wait for their worker (8f:
  `PHASE8_RECORD.md` §10);
- the Prioritizer banner (§79.0), now asserted whole (8c: `PHASE8_RECORD.md` §5);
- the 31 documented contract keys (§79.3), each now driven from its generator's own entry
  by five tests (8g: `PHASE8_RECORD.md` §11);
- the annotated targets no test reached (§77.9), with one test per function. The sweep now
  reaches 63 of 63 (8e: `PHASE8_RECORD.md` §8);
- the feature-spec section guards (§78.2), now at `> 3` and pinned both ways (8a and D1:
  `PHASE8_RECORD.md` §3, §19);
- the `tests/test_agents.py` split (D9: `PHASE8_RECORD.md` §25);
- PLR2004 (D12): `tests/**` is exempt by policy, and the rest waits in Part 2 (2.7).

### 1.4 The tooling

**Ruled at D13: ruff yes, mypy no** (`PHASE8_RECORD.md` §19.1). Closed.
- `uv run ruff check .` is the standing requirement for the tools, and it stays.
- Strict mypy's 230 errors in the scaffolding are a lift with no consumer until the next
  refactor phase, and none is planned.
- The tools' known limits are documented in `scripts/cleanup/README.md`. Fixing them is
  Part 2's (2.7), when next used.

### 1.5 Named, never ruled: all four now ruled

The record named these four and never ruled on them. The fold listed them here so they
would not be buried. Phase 8 ruled all four (`PHASE8_RECORD.md` §19.1):
- **Consolidating `test_deployer_*`, `test_phaser_*` and `test_stack_*` goes to Part 2
  (D10),** to wait for a structural reason (2.6).
- **§50's four other test files over 150 tests: dropped (D10).** Files of 155–215 tests are
  not a problem.
- **`TestMockBuffers` against `test_designer.py::TestMockDeliveryAck`: closed (D8).** It
  was closed under 6f's standard, and nothing has changed.
- **`tests/_golden.py` absorbing the per-file golden idioms: dropped (D11).** The
  condition never arose.

## Part 2: Backlog

### 2.1 The cleanup's known limit: UI-callback coverage

This was ruled at review of the close-out (§80.2): it is not cleanup.
- **Raising callback coverage is product work.** It means writing tests for behaviour
  nobody has pinned.
- **The cleanup made that work possible.** `trace_identity.py` and `mutate.py` are what it
  hands over for it.
- **39 typed callback parameters that no test exercises** (Phase 8, 8h: `PHASE8_RECORD.md`
  §12.4, §15). 8h typed 105 prop-bound callback inputs, and the width sweep found that no
  test reaches 39 of them. For those, the width rule holds only vacuously, as it did for
  8e's five before their tests.
  - **26 are in the `callbacks/__init__` family:** `__init__.py` 6, `_artifacts.py` 6,
    `_chat.py` 3, `_gate.py` 1, `_nav.py` 8 and `_setup.py` 2.
  - **13 are in the `callbacks/designer` family:** `_wizard.py` 10 and `_refine.py` 3.
  - **Every one sits in a family this entry names,** so none is a Phase 8 test row. The row
    map is `scripts/cleanup/data/rows_8h.json`.
  - **The limit has a shape, not just a count:** every one of the 39 lies in a module that
    Phase 4 carved out of `callbacks/__init__.py` (26) or `callbacks/designer.py` (13).

The figures below were measured at `85a9cb6`, and `tests/README.md` carries the full table.

| Module | Phase 0 | At the close-out |
|---|---:|---:|
| `callbacks/designer/_wizard.py` | within `callbacks/designer.py` | 49.6% |
| `callbacks/designer` family (was `callbacks/designer.py`) | 73.5% | 76.5% |
| `feature_specs.py` | 75.5% | 76.7% |
| `callbacks/__init__` family (was `callbacks/__init__.py`) | 76.9% | 78.6% |
| `websearch.py` | 78.7% | 80.5% |
| `session.py` | 81.6% | 82.7% |
| `providers.py` | 82.8% | 83.9% |

### 2.2 Renderer cosmetics (§12.4)

Phase 1 logged these, and they were deferred to Phase 5, which never took them up. Each
was still visible in the goldens at the fold. Each fix changes artifact output, so it is a
deliberate golden update.
- **`phase_full.md`, the UI-surfaces block:** "The following surface(s) realize…"
  follows a list item with no blank line, so Markdown reads it as part of the bullet
  (item 2).
- **`phase_full.md`:** two blank lines between the NFR block and `## References`
  (item 3).
- **`render_stack_full.md`:** the top-level fall-through is emitted after
  `**References:**`, and the closing `---` is glued to its last line (item 4, the open
  half).
- **`render_review_full.md`:** an `api_surface` entry renders `— → `, a dash and then an
  arrow (item 5, the open half).
- **`render_catalog.md`:** an entry with no `name` or `tier_decision` renders
  `|  | none |  (mismatch) |`. Phase 1 called this "Phase 5, or a schema question"
  (item 6).

### 2.3 A params object for the three long signatures

- **`_start_gen` and `generate_mock_streaming` take 13 parameters each:** the
  mock-generation contract they share.
- **`reask_for_artifact` takes 10.**

Each carries a reasoned `# noqa: PLR0913`. Collapsing them into a params object changes
their call sites, which makes it a design change, not cleanup (§27, §39).

### 2.4 The two horizon items

The cleanup plan names two existing horizon items: **CodeScanner incremental scan** and
**Designer mock capture**. Neither is described anywhere in the repo, so their
descriptions are for their owner to write here.

### 2.5 Bugs found during the cleanup

The record's *Bugs found (not fixed)* list (§10) held four entries, and all four were
resolved in Phase 0.5:
1. **`test_no_transcript_block_is_filled` failed.** The filled user turns were the
   intended look, and the test was replaced (0.5c).
2. **`topics` was redefined in `agentifier.py`.** Not a bug: an annotation moved (0.5b).
3. **`float` was compared with `None` in `project_manager.py`.** Not a bug: the `None`
   branch was unreachable (0.5b).
4. **`active_version(None)` raised `TypeError`** on the Designer layout with no project.
   Fixed after 0.5c, with a test: `TestDesignerLayoutWithoutProject`.

§10 was not extended after Phase 0.5. The one later defect the record names is a test
defect, the nine racing tests. Phase 8 fixed it (8f: `PHASE8_RECORD.md` §10).

### 2.6 Test-family consolidation, when a structural reason arrives

This was ruled at Phase 8's D10 (`PHASE8_RECORD.md` §19.1).
- **Why it waits:** merging `test_deployer_*`, `test_phaser_*` and `test_stack_*` for
  tidiness is what the pruning rule forbids, by analogy. It waits here until a
  structural reason arrives.
- **Its size, as Phase 8 sized it:** 24 files and 616 tests (`PHASE8_RECORD.md` §1.2,
  P27).
  - `test_stack_*` is 11 files and 462 tests;
  - `test_deployer_*` is 9 files and 106 tests;
  - `test_phaser_*` is 4 files and 48 tests.
  - 10 of the 24 files hold floor entries, so a merge moves floor ids, as D9's split did.
- **D9's split has since added one file per agent** (`PHASE8_RECORD.md` §25):
  `test_stack_advisor.py`, `test_phaser.py` and `test_deployer.py`.
- **Its proof is built:** `move_check.py`, the move petition (`PHASE8_RECORD.md` §24).

### 2.7 The cleanup tools, and PLR2004 outside `tests/`

This was ruled at Phase 8's D13 and D12 (`PHASE8_RECORD.md` §19.1).
- **The tools stay under `ruff check .`, and outside mypy.**
- **Each limit below is fixed when a tool is next used for it,** and not before. The first
  three are documented as limits in `scripts/cleanup/README.md`.

**The limits:**
- **The width sweep cannot resolve a target defined inside a function.** 8h proved its one
  such row, `on_open_artifact`, with a scratch copy that reads the enclosing function's
  `co_consts` (`PHASE8_RECORD.md` §12.4).
- **Check 4 cannot see `import … as`.** An aliased patch string is accepted when condition
  (2) holds and a mutation of the call fails the test that patches it
  (`PHASE8_RECORD.md` §10).
- **The mutation harness cannot mutate on top of a working-tree edit.** It refuses to start
  on a tree that is not clean. 8i2 and 8i3 met this with §15's sequence, carrying the
  whole turn in each case (`PHASE8_RECORD.md` §15, §16.1).

**A return-side width sweep, not yet committed.**
- The committed sweep checks the values that arrive at parameters.
- D14's scratch plugin checked the fourteen returns D14 typed, by monitoring `PY_RETURN`
  (`PHASE8_RECORD.md` §21). A committed form would prove the width rule for returns.

**PLR2004 outside `tests/`.** `tests/**` is exempt by policy, since a test's magic numbers
are its assertions (D12). The other two stay ignored:
- `evals/**`, with 25, while `evals/` is outside the gate;
- `scripts/**`, with 21, which follow the tools.
  - 15 of the 21 are in `scripts/cleanup/`.
  - One of those 15 is in `move_check.py`, which came after the sizing.
