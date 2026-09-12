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

- **Five renames are held back.** The other 76 were renamed across ten batches (§61–§70).
  - **Three are net-blocked,** each held by the file that reaches it by attribute:
    - `_start_gen` and `_record_usage`, by `tests/test_streaming_characterization.py`, a
      whole-file entry. Both go in one petition, the next time that file is legitimately
      opened.
    - `_with_readme_attribution`, by `tests/test_project_manager_golden.py`, a whole-file
      entry.
  - **Three wait on the `project_manager` root-siblings inconsistency** (§27.7,
    §60.7(f)): `_write_text_if_changed` (4 sites), `_phase_spec_preamble` (1) and
    `_with_readme_attribution` (4). The last is in both lists.
- **§27.4's three remaining backlog turns:** `deployer.run` (185 lines),
  `brainstormer.run` (101) and `code_scanner.run` (175).
  - Each still carries a rule-12 `noqa`.
  - The shape is proven by 7q: a driver over steps, where a step's `None` has one
    meaning (§79).
  - `trace_identity.py` is ready to trace them; `TRACE_MODULE` and `TRACE_FAMILY` name
    the module and its functions.
  - The alternative not taken is a step sentinel that tells a step's ending causes apart.
- **Not promote targets:** the 24 `keep: subject is the private object` names (§54.1,
  §55.4). The collection is each test's subject.
- **Dedupes:**
  - `revision_delta`'s five copies, a straight lift to `_utils` (§67.11);
  - the mechanism-summary trim, which is written twice (§78.2).
- **Not scheduled:** the `sys.modules` lookup in `test_cost_summary.py`. It is now
  scaffolding for a shadow that no longer exists (§64).

### 1.2 Types (§77.8)

- **The session-dict edge** (90 `: Any` lines) and **the JSON-artifact edge** (107), as
  `TypedDict` design.
- **The 107 prop-bound callback inputs** on mixed lines.
- **The 148 `-> Any` return lines** outside the grep.
- **`object` for `_as_int` and `round_number_from_value`,** and `run_with_timeout`'s
  generic form, which needs a runtime TypeVar.
- **A question: should `_fmt_usd` accept `str`?** A passing test pins that it does
  (`tests/test_cost_summary.py:160`).

### 1.3 Tests

| Item | Size | Source |
|---|---|---|
| The nine racing tests: patch `streaming.start`, or wait for the stream | 9 tests; a defect | §79.0, §79.2 |
| The Prioritizer banner | 1 assertion | §79.0 |
| Tests that assert less than their path, and a path no test reaches. Ten tests pass while the trace diverges under a turn's forbidden-`None` mutation: 8i1's 4, in `brainstormer`, and 8i2's 6, in `code_scanner`. `code_scanner.run`'s recap fall-through is reached by 0 of 43 traced invocations. 8i3 extends the row | 10 tests, 1 path | `PHASE8_RECORD.md` §14.2, §16; `CLEANUP_REPORT.md` §2.4a |
| Documented contract keys the suite never saw change | 31 keys across 4 generators: one contract test each | §79.3 |
| Annotated targets no test reaches: `on_designer_generate_mock` ×3, `on_provider_hint`, `_designer_tool_call_followup` | 3 functions | §77.9 |
| Feature-spec section guards: `> 2` against its siblings' `> 3`. Check that real output reaches it before deciding | 3 builders | §78.2 |
| `tests/test_agents.py`: split it by source module, a test-structure item. The floor and petition checks make the split provable | 5,268 lines, 293 tests | §2, §50; ruled in §80.1 |
| PLR2004, deferred with a size | 230 in `tests/`, 25 in `evals/`, 20 in `scripts/` (6 at promotion; the 14 in `scripts/cleanup/` go with the tools, 1.4) | §78.4; `PHASE8_RECORD.md` §1.1 |

### 1.4 The tooling

Whether to bring `scripts/cleanup/`'s twelve tools inside: into the gate, and under mypy.
Today they are outside both.

### 1.5 Named, never ruled: rule on these before Phase 8 starts

The record named these items and never ruled on them. They are listed here so that the
fold does not bury them. Each needs a ruling: Phase 8, Part 2, or drop.

| Item | Size | Source |
|---|---|---|
| Consolidate `test_deployer_*`, `test_phaser_*` and `test_stack_*`: fifteen-plus files target the same three modules | 15+ files | §9; deferred to Phase 6 in §11, and not carried by §59.6 |
| §50's four other test files over 150 tests: `test_stack_render_totality.py` (215), `test_artifact_view.py` (213), `test_designer.py` (162) and `test_agent_llm_selection.py` (155) | 4 files | §50 |
| `TestMockBuffers` overlaps `test_designer.py::TestMockDeliveryAck` on the ack and valve branches. `TestMockBuffers` is in `test_streaming_characterization.py`, a whole-file floor entry. That is how the screen-registry overlap came to be ruled frozen (§55, §56) | 2 classes | §12.5 |
| `tests/_golden.py` could absorb the per-file golden idioms, if more goldens appear | conditional | §12.5 |

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
defect, the nine racing tests, and it is on the Phase 8 list (1.3).
