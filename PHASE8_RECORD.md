# Phase 8: the record

Phase 8 is the cleanup's continuation: `BACKLOG.md` Part 1, taken under the rules
`CLEANUP_REPORT.md` §3 states. `CLEANUP_INVENTORY.md` is history (its §81), and this file
is Phase 8's record in its place.

- **§1 is the pre-work.** It opened this file.
- **Each Phase 8 sub-phase appends one section, §2 onward,** through
  `scripts/cleanup/append_section.py`, and each commit is checked with its `--guard`. The
  prior bytes of this file are never rewritten.
- **References.** A bare §N is this file. "Inventory §N" is `CLEANUP_INVENTORY.md`,
  "report §N" is `CLEANUP_REPORT.md`, and "BACKLOG 1.N" is a section of `BACKLOG.md`'s
  Part 1. Rows are named P1–P32 (§1.2) and sub-phases 8a–8i3 and D1–D15 (§1.5).

## 1. Phase 8 pre-work: Part 1, sized into two halves

This is the pre-work, not Phase 8. It sizes every item in `BACKLOG.md` Part 1, splits the
items into a mechanical half and a decision half, proposes the proofs that do not exist
yet, and proposes the order.
- **Measured at the fold, `2214ce9`,** on `look-rework`, in one session on 2026-09-11.
  The tree was clean before and after.
- **It changed nothing under `src/`, `tests/`, `pyproject.toml` or `scripts/cleanup/`.**
  It is one commit, this file only: Rule 1, strict. The committed tools ran as committed.
  Scratch measurements ran from the session scratchpad and wrote nothing in the repo.
- **It stops at its commit.** Phase 8 begins on approval.

### 1.1 Baseline at the fold

Every figure was measured at `2214ce9` and compared with `CLEANUP_REPORT.md`. None
differs, so nothing here is a stop.

| Check | Command | At `2214ce9` | Report | |
|---|---|---|---|---|
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | 4,211 collected; `4210 passed, 1 skipped` (exit 0) | §1: 4,211; 4,210 / 1 | ✅ |
| Coverage | same run | `TOTAL 12459 876 93%` | §1: 12,459 / 876 | ✅ |
| Ruff, the promoted set | `uv run ruff check src/ tests/`; `uv run ruff check .` | `All checks passed!`, both | §1 | ✅ |
| Format | `uv run ruff format --check src/ tests/` | `221 files already formatted` | §7.3: 221 | ✅ |
| mypy, strict | `uv run mypy src/` | `Success: no issues found in 92 source files` | §1 | ✅ |
| `: Any` lines, 5p's grep | `grep -rc ': Any' src/spec4/ --include=*.py`, summed | 232 | §1: 232 | ✅ |
| Complexity `noqa`s | `grep -rn 'noqa: C901' src/` | 9 | §1: 9 | ✅ |
| Floor | `uv run python scripts/cleanup/floor_check.py` | 188 / 85 / 183; 456; `FAILURES: 0` | 456 / 456 | ✅ |

- **Coverage matches row for row.** The run's 92 per-module rows equal
  `scripts/cleanup/data/coverage_85a9cb6.txt` in statements, misses, percentages, and
  every missing-line list.
- **Why the trees agree.** Since `6956aca`, the tree that coverage file describes, `src/`,
  `tests/` and `pyproject.toml` differ only in `tests/README.md` (`git diff --stat 6956aca
  HEAD`).
- **No runtime is recorded.** A lone figure pairs nothing (report §3), and ruff, mypy and
  the floor check ran beside the suite.

**`remeasure.py` reproduces §7's current-tree column:**

```sh
uv run python scripts/cleanup/remeasure.py 6956aca HEAD \
    --cov-base scripts/cleanup/data/coverage_85a9cb6.txt --cov-head <scratch>/cov_head.txt
```

- **`--cov-head` is the gate run above.** It is the same `pytest --cov=spec4
  --cov-report=term-missing` output that `--run-coverage` would have produced in the
  export, taken once rather than twice.
- **Every table's two columns are identical,** and the base column is report §7's "Now"
  column:
  - the gate: 4,210 / 1; 12,459 / 876 / 93.0%; ruff and format clean; mypy, 92 checked;
  - coverage per module: 92 at the same path, 0 rose, 92 unchanged, 0 fell, and the ten
    lowest as §7.4 lists them;
  - dead code: vulture 60 and 26; `ARG` 0 in `src/` and 178 in `tests/`; 1,093
    definitions, 513 / 457 / 56 / 32 / 24, and 135;
  - dependencies: 347, of which DEP001 314 + 29 + 1, DEP002 0 and DEP004 3;
  - complexity: 9 / 6 / 12 / 3, 30 in all; the nine over C901, from `stream_turn` 24 to
    `_has_cycle` 11;
  - size: 92 files and 40,284 lines; the same two files over 1,300; `deployer.run` 185
    and `code_scanner.run` 175 the longest; `tests/` 129 files and 56,534 lines;
    `test_agents.py` 5,268 lines and 332 functions;
  - the import graph: 92 modules, 0 cycles, 0 layer violations, 21 / 23 importers, 3
    `TYPE_CHECKING` edges, 0 `global`.

**The proving tools, re-run at HEAD.** §1.2's rows lean on four of them, so each ran once
here first. Every run exited 0 with `4210 passed, 1 skipped`.

| Tool | Run | Result |
|---|---|---|
| Trace identity, the default family | full suite, `--basetemp` fixed | 151 tests traced, 199 invocations, 1,081 events; tests, invocations, events and entry counts equal 7q0's baseline meta (inventory §79.0); 142 tests on the main thread, 9 in workers |
| Trace identity, `TRACE_MODULE=spec4.agents.brainstormer TRACE_FAMILY=run` | as above | 47 tests, 47 invocations, all on the main thread |
| … `spec4.agents.code_scanner` | as above | 42 tests, 43 invocations, all on the main thread |
| … `spec4.agents.deployer` | as above | 32 tests, 32 invocations, all on the main thread |
| `trace_diff.py`, each run against itself | — | identical; 0 escalated |
| Width sweep | full suite | `targets 63; reached 58; never reached 5; rejected by a real value 0`, as 7o5 recorded (inventory §77.9) |

- **The race fired in this run too.** One of the nine,
  `TestGuidedRedraw::test_notes_accumulate_across_retries`, reached the real Scout from its
  worker (`sub-agent 'scout' raised`).

**One sizing figure has moved since the report, and it is not a gate figure.** PLR2004 in
`scripts/` measures 20. Report §1, BACKLOG 1.3 and `pyproject.toml`'s comment say 6.
- **Measured** with `ruff check --isolated --select PLR2004` on `git archive` exports:
  `90d75c7` 6, `85a9cb6` 16, `18a271c` 20.
- **The 14 new findings are all in `scripts/cleanup/`.** The two tools commits added them,
  under the `scripts/**` ignore. The gate never reads them, and `uv run ruff check .`
  passes.
- **The report's 6 was right for the tree it measured,** `90d75c7`, before the tools. P25
  carries 20. §1.1's stop is read as covering the gate figures above, so this one is
  flagged for review rather than taken as a stop.

### 1.2 Every Part 1 item, one row

How to read the columns:
- **Proof:** the tool from the twelve (report §4) that proves it, or `none — needs a
  proof designed`, which §1.4 then proposes.
- **Floor:** what the item edits in `data/floor.json`: whole-file entries by file, tier-B
  entries by class node id with its count of ids, and tier-A entries by node id. "None"
  means it edits none of them. A file that holds entries the item leaves alone is named
  where it matters, because its hunks go in §51.6's allowed-and-reported template.
- **Size:** measured at `2214ce9`. A figure that is quoted rather than measured says so,
  and why.
- **Half:** by §1.3's rule.

**BACKLOG 1.1, names and seams**

| # | Item | Source | Kind | Proof | Floor | Depends on | Size | Half |
|---|---|---|---|---|---|---|---|---|
| P1 | `_start_gen` and `_record_usage`, net-blocked renames | inventory §60.7(c), §69.2, §70.2 | code | rename check, token check, check 4; the attribute sites fit no petition shape (inventory §60.3's options table) | whole-file `tests/test_streaming_characterization.py` (`:344`, `:402`, by attribute); tier-B `tests/test_designer.py::TestCapturePassesPlanningContext` (2 sites), `::TestRetryReproducesTheDraw` (2), `::TestRefinePersistsManifest` (1); tier-A `tests/test_designer.py::TestMockDeliveryAck::test_delivery_preserves_prior_store_keys` (1) | P29: the next legitimate opening of the whole-file entry | `_start_gen`: 38 occurrences in 6 files; `src/` 16 in 4, `tests/` 22 (`test_designer.py` 21, the entry 1). `_record_usage`: 9 in 3; `llm.py` 6, `test_usage_capture.py` 2, the entry 1 | decision |
| P2 | `_with_readme_attribution`, net-blocked | inventory §60.7(c) | code | as P1 | whole-file `tests/test_project_manager_golden.py` (`:168`, `:169`, `:172`, `:173`, by attribute) | P3, P4 | 8 occurrences in 3 files: `src/` 4, and all 4 test sites in the entry | decision |
| P3 | Root-siblings: `project_manager` as a package | inventory §27.7, §60.5, §60.7(f) | code | inventory §60.6's check: `git diff -M` shows four pure moves and import lines; the layering test; check 4 on the two `spec4._usage` patch strings. Only check 4 is one of the twelve | none | — | 4 modules, 1,746 lines (`_paths.py` 199, `_artifacts.py` 580, `_phase_markdown.py` 518, `_usage.py` 449) behind the 498-line façade. 13 reference lines in 4 files: `project_manager.py` 8, `_artifacts.py` 2, `_usage.py` 1, `tests/test_usage_capture.py:851`, `:873`. §60.5 had 16 in 5; `conftest.py`'s three left with `module_seam` at 7k | decision |
| P4 | Batch 11's three names | inventory §60.7(f) | code | rename tools; petitions | tier-B `tests/test_project_manager.py::TestPreambleTwoAltitudesAndSurfaces` (`_phase_spec_preamble`, 1 site); whole-file `tests/test_project_manager_golden.py` (P2's four sites, and its docstring at `:11`) | P3 | `_write_text_if_changed`: 19 occurrences in 3 files; `src/` 14, `test_project_manager.py` 5, in `TestIdempotentWrites` and `TestProjectReadme`. `_phase_spec_preamble`: 8 in 5. `_with_readme_attribution`: as P2 | decision |
| P5 | `brainstormer.run`, a backlog turn | inventory §27.4, §79 | code | trace identity re-baselined on `spec4.agents.brainstormer`; frozen strings on the module; the mutation harness, one mutation per turn; complexity with `--ignore-noqa` | none: no test is edited | P8, only if a step must tell two ending causes apart | 101 lines (`brainstormer.py:667–767`); C901 14, PLR0912 16; 6 yields; 47 tests traced, all on the main thread | mechanical |
| P6 | `code_scanner.run` | as P5 | code | as P5, on `spec4.agents.code_scanner` | none | as P5 | 175 lines (`code_scanner/__init__.py:160–334`); C901 12, PLR0912 13, PLR0915 59; 9 yields; 42 tests, 43 invocations, main thread | mechanical |
| P7 | `deployer.run` | as P5 | code | as P5, on `spec4.agents.deployer` | none | as P5; it shares `deployer.py` with P10 | 185 lines (`deployer.py:548–732`); C901 21, PLR0912 25, PLR0915 88; 10 yields; 32 tests, main thread | mechanical |
| P8 | The step sentinel, the alternative not taken | inventory §60.7(j)'s Phase 8 list, §79 | code | trace identity, if taken | none | P5–P7 | 0 steps need it today. If taken: agentifier's 10 generator steps and their 24 `yield from _` sites | decision |
| P9 | The 24 `keep: subject is the private object` names, not promote targets | inventory §54.1, §55.4 | code | — | — | — | no work: a standing ruling | neither: no sub-phase |
| P10 | `revision_delta`'s five copies, one lift | inventory §67.11 | code | the five bodies' token identity, re-run now by a scratch script as §67.11's was; the mutation harness, one mutation on the one body; check 4 on `spec4.callbacks.designer._wizard.revision_delta` | none, if each module keeps its binding | its home (§1.3) | 5 definitions and one body, 69 tokens each, docstrings 434–650 characters: `agentifier/_render.py:292–306`, `agents/deployer.py:397–414`, `agents/designer.py:268–283`, `agents/phaser/_revision.py:36–53`, `agents/stack_advisor/_stack_shape.py:27–43`. 10 call sites; 4 `__all__` entries; tests in five groups, none in the floor; 1 patch string (`tests/test_designer_fullscreen.py:100`) | decision, moved (§1.3) |
| P11 | The mechanism-summary trim, written twice | inventory §78.2 | code | the mutation harness: the trim removed from the one helper fails a test on each side; frozen strings | none | — | 3 identical lines, twice: `agentifier/tier_analyst.py:332–334` and `feature_specs.py:332–334`, under two constants of 200, `_PROMPT_DESCRIPTION_CHARS` and `_MECHANISM_SUMMARY_CHARS`. A third, near-copy at `tier_analyst.py:312–314` strips rather than collapsing whitespace, so it is not an exact match. The six library descriptions run 436–504 characters, so the trim fires on each | mechanical, with a stated home (§1.3) |
| P12 | The `sys.modules` idiom in `test_cost_summary.py` | inventory §64; §60.7(j)'s note | test | check 4, the setattr form, on `monkeypatch.setattr(module, "cost_strip_lines", …)` | none: `TestOneRenderer` holds no entry, and the file's three tier-A nodes are untouched | its scheduling: ruled "not scheduled" at 7d | 1 test: the lookup and its 3-line comment (`:621–624`), and `import sys` (`:24`), its only use | decision |

**BACKLOG 1.2, types**

| # | Item | Source | Kind | Proof | Floor | Depends on | Size | Half |
|---|---|---|---|---|---|---|---|---|
| P13 | The session-dict edge (90 `: Any` lines) and the JSON-artifact edge (107) | inventory §60.5, §77.8 | type | — | — | — | a design limit, recorded once below | neither: not a Phase 8 item |
| P14 | The prop-bound callback inputs on mixed lines | inventory §60.5, §77.8 | type | strip check; width sweep on a new row map; strict mypy: 7o2's and 7o3's shape | none | — | 221 `Any`-annotated parameters on 87 Dash callbacks, on 85 lines. 103 are named as the store (`session` 72, `store` 21, `prefs` 10) and 118 are not (`n` 51, `n_clicks_list` 6, `image_support` 6, `n_clicks` 5, …). §60.5's prop rule found 107 on 81 lines. The rules differ, so the row map reads each parameter's prop, as §60.5 did. Each line keeps its `Any` for the store, so 5p's grep does not move | mechanical |
| P15 | The `-> Any` return lines outside the grep | inventory §60.5, §77.8 | type | strip check and mypy for the annotation half; the width rule's return side: `none — needs a proof designed` | none | a classification first, as §60.5 made for the 290 | 148 lines in 24 files, as §60.5 counted; unclassified | decision |
| P16 | `object` for `_as_int` and `round_number_from_value`: two of the 35 load-bearing rows | inventory §77.3, §77.8 | type | strip check; strict mypy; the width sweep, which holds trivially since `object` admits every value | none | — | 2 lines in 2 files, `llm.py:299` and `layouts/_artifact_view.py:764`. Applied to a scratch export: strict mypy `Success: no issues found in 92 source files`; the strip check `files changed: 2; files with residue: 0`; 5p's grep 232 → 230. The other 33 rows stay on §77.3's reasons | mechanical |
| P17 | `run_with_timeout`'s generic form | inventory §77.1, §77.8 | type | strip check, which erases PEP 695 type parameters; strict mypy | none | — | 1 line, `agentifier/subagents.py:239`. The PEP 695 form, `async def run_with_timeout[T](coro: Awaitable[T], *, timeout: float, name: str) -> T:`, needs no runtime `TypeVar` (`requires-python >= 3.12`; mypy 1.20.2). On a scratch export: strict mypy clean; the strip check `files changed: 1; files with residue: 0`. No caller in `src/`; two in `tests/agentifier/test_subagents.py` | mechanical |
| P18 | A question: should `_fmt_usd` accept `str`? | inventory §60.7(j)'s Phase 8 list, §77.9 | type | — (a question); the width sweep is its evidence | none: `test_cost_summary.py::TestFormat` holds no entry | — | 1 annotation (`layouts/_shared.py:195`) and 1 assertion (`tests/test_cost_summary.py:160`). The one caller in `src/`, `_cost_figure` (`_shared.py:248`), passes `block.get("cost_usd")`, read from the usage rollup | decision, moved (§1.3) |

**The design limit, recorded once (P13).**
- **5p's grep stands at 232: 90 session-dict edge, 107 JSON-artifact edge and 35
  load-bearing,** by §60.5's classification as §77.8 closed it. The total is re-measured.
  The split is the record's: no committed file holds the classification, and
  `data/rows_7o.json` carries only 7o's 58 typeable rows and 9 of the load-bearing.
- **It is not a Phase 8 item.** Typing either edge is the `TypedDict` design the plan
  keeps out of cleanup (inventory §27.5(h), §60.7(g)), and the session-typing rule stands.
  Phase 8 does not size it further.
- **The map a future decision would size from:**
  - the eleven contract docstrings, each stating the session keys its function writes:
    the eight agentifier generators (`agentifier.py`, "Its contract on ``session``"),
    `get_agent_gen` (`session.py:375`), `persist_artifacts` (`session.py:535`) and
    `rehydrate_vision_from_disk` (`agents/brainstormer.py:649`);
  - `default_session()`, which declares 74 keys;
  - the partial `DesignerSession` `TypedDict` in `agents/designer.py`;
  - for the artifact edge, the two schema validators (`agents/_code_review_schema.py`,
    `agents/_phase_schema.py`) and the goldens.

**BACKLOG 1.3, tests**

| # | Item | Source | Kind | Proof | Floor | Depends on | Size | Half |
|---|---|---|---|---|---|---|---|---|
| P19 | The nine racing tests: wait for the stream | inventory §79.0, §79.2 | test | `none — needs a proof designed` (§1.4). It would use the mutation harness and trace identity's worker classification | none: the nine are in `TestDiskIsUntouched`, `TestCallback` and `TestGuidedRedraw`. The file's two tier-A nodes, in `TestPanelButton`, are untouched | — | 9 tests in `tests/agentifier/test_try_again.py`: `TestDiskIsUntouched::test_implemented_round_survives_a_full_try_again`, `TestCallback::test_starts_a_stream_and_records_the_action` and `::test_prior_transcript_is_preserved`, and six `TestGuidedRedraw` tests through its `_run`. The edits: `_run`, three test bodies and one wait helper | mechanical, once §1.4's proof is approved |
| P20 | The Prioritizer banner | inventory §79.0 | test | the mutation harness, with `probe_A`'s anchor from `data/cases_7q.json`, which still matches once. The new test must fail under it | none: `tests/agentifier/test_prioritizer.py` holds no entry | — | 1 assertion, on `"### Prioritizer\n\n"` at `agentifier.py:1532`. No test names the banner today | mechanical |
| P21 | The 31 documented contract keys the suite never saw change | inventory §79.3 | test | the mutation harness, one mutation per contract test: 7n1's key-set shape. The closure, "all 31 now seen", was a scratch step at 7q3 and is not among the twelve (§1.4) | none, if the tests go in classes without entries; `test_revision.py`, `test_reselection.py` and `test_streaming_e2e.py` hold none | — | 4 tests, one per generator: `run_catalog_phase` 11 keys, `run_cross_cutting_phase` 1, `handle_reentry` 13, `finalize_specs` 6. **Quoted from §79.3:** the committed trace records no snapshot at a generator's entry, so the unseen set cannot be re-derived with the twelve | mechanical |
| P22 | Five annotated targets no test reaches | inventory §77.9 | test | the width sweep, reached 58 → 63 and rejected 0; the mutation harness, one mutation per function | none, if the tests go in new classes outside every entry | — | 3 functions, 5 targets: `on_designer_generate_mock` (57 lines, `callbacks/designer/_wizard.py:225–281`; `n`, `annotations`, `image_support`), `on_provider_hint` (13, `callbacks/_setup.py:34–46`) and `_designer_tool_call_followup` (40, `agents/designer.py:544–583`). 0 references in `tests/`. The sweep at HEAD: 5 never reached | mechanical |
| P23a | The `> 2` guard: does real output reach it? | inventory §78.2, §78.4 | test | `none — needs a proof designed` (§1.4). It would use the mutation harness and the goldens | none | — | 3 builders, 82 lines (`feature_specs.py:339–424`), guards at `:367`, `:393` and `:424`; the siblings' `> 3` at `:214` and `:281`. Evidence in the tree: one golden fixture carries the three keys (`tests/golden/fixtures/spec_full.json`); none of the 16 JSON files under `evals/` does; 51 files are tracked under `.spec4/`, which Rule 2 covers | mechanical, once §1.4's proof is approved |
| P23b | …and is flipping it to `> 3` a fix? | inventory §78.4 | code | the evidence P23a records | none; a golden update if a golden changes | P23a | 3 characters in 1 file | decision |
| P24 | `tests/test_agents.py`, split by source module | inventory §2, §50, §80.1 | test | the floor and petition checks (§80.1). A moved node id fits neither petition, so: `none — needs a proof designed` (§1.4) | tier-B `tests/test_agents.py::TestAiFeaturesForPhaserFullSurface` (8), `::TestLoadDesignManifest` (4) and `::TestPhaserSpecReferenceDirective` (4): 16 ids that would change file | after P5–P7, 83 of whose traced tests live here (`deployer.run` 25, `brainstormer.run` 33, `code_scanner.run` 25); after P10 | 5,268 lines; 293 tests collected; 36 classes; 332 functions. It imports five agent modules: `brainstormer`, `code_scanner`, `deployer`, `phaser` and `stack_advisor` | decision |
| P25 | PLR2004, deferred with a size | inventory §78.4 | test | the inline check, 7p2's shape, for each named value; a changed literal in a whole-file entry fits no petition | in `tests/`: 11 findings in 3 whole-file entries; 75 in the 16 files holding tier-B classes; 39 in the 16 holding tier-A nodes only; 105 in the 33 holding none | P26, for `scripts/cleanup/` | `tests/` 230 in 68 files; `evals/` 25; `scripts/` 20, not 6 (§1.1) | decision |

**BACKLOG 1.4, the tooling**

| # | Item | Source | Kind | Proof | Floor | Depends on | Size | Half |
|---|---|---|---|---|---|---|---|---|
| P26 | The twelve tools: inside the gate, and under mypy | report §5.4 | tooling | — : the question is the gate itself | none | — | 16 files in `scripts/cleanup/`. `uv run mypy scripts/cleanup/`, under the project's strict configuration: `Found 224 errors in 15 files (checked 16 source files)`. ruff check and format are clean; PLR2004 has 14 under the `scripts/**` ignore; no test covers a tool | decision |

**BACKLOG 1.5, named and never ruled**

| # | Item | Source | Kind | Proof | Floor | Depends on | Size | Half |
|---|---|---|---|---|---|---|---|---|
| P27 | Consolidate `test_deployer_*`, `test_phaser_*` and `test_stack_*` | inventory §9, §11 | test | the move petition (§1.4) | 10 of the 24 files hold entries: tier-A, 18 ids in 8 files; tier-B, `tests/test_deployer_env_and_semantics.py::TestEarlierGuidanceSurvives` (2), `tests/test_stack_advisor_token_counter.py::TestCounterGate` (8) and `::TestSuppressedStreamPublishesReceipt` (7), `tests/test_stack_routing.py::TestDerivedNfrIds` (5) | the move petition | 24 files, 616 tests: `test_stack_*` 11 files and 462 tests, `test_deployer_*` 9 and 106, `test_phaser_*` 4 and 48 | decision |
| P28 | §50's four other files over 150 tests | inventory §50 | test | the move petition (§1.4) | `test_stack_render_totality.py`: tier-A 2. `test_artifact_view.py`: tier-A 6. `test_designer.py`: tier-A 3; tier-B `::TestCapturePassesPlanningContext` (5), `::TestRefinePersistsManifest` (2), `::TestRetryReproducesTheDraw` (5). `test_agent_llm_selection.py`: tier-A 6; tier-B `::TestOfferedEfforts` (10) | the move petition; it overlaps P27 on `test_stack_render_totality.py` | 215, 213, 163 and 155 collected. §50 had 162 for `test_designer.py`, and 7l added one | decision |
| P29 | `TestMockBuffers` overlaps `TestMockDeliveryAck` | inventory §12.5 | test | a petition by node id (inventory §50.5(a)) | whole-file `tests/test_streaming_characterization.py` (`TestMockBuffers`); tier-A `tests/test_designer.py::TestMockDeliveryAck::test_delivery_preserves_prior_store_keys` | —; P1 rides on it | 2 classes, of 6 tests and 7 | decision |
| P30 | `tests/_golden.py` could absorb per-file golden idioms | inventory §12.5 | test | — | whole-file `tests/test_renderer_goldens.py` and `tests/test_project_manager_golden.py`, the only users of `_golden.py`, and `tests/test_layout_contract.py`, the one other update-env idiom (`SPEC4_UPDATE_SNAPSHOTS`) | — | Its condition has not come about: there is no golden idiom outside `_golden.py` | decision |

**Not in Part 1: found in the record**

| # | Item | Source | Kind | Proof | Floor | Depends on | Size | Half |
|---|---|---|---|---|---|---|---|---|
| P31 | `persist_artifacts`' name | inventory §73.2, sized there for Phase 8; the directive names it | code | rename check, token check, check 4 on 8 patch strings | none: every test site, re-checked, is outside the entries | — | 62 occurrences in 14 files, where §73.2 had 60: `tests/` 51, of them 8 patch strings; `src/` 10; `scripts/` 1 | decision |
| P32 | Sleeps before an mtime comparison | inventory §62.8, §66.8: "logged for the close-out's backlog"; the fold did not carry it | test | none of the twelve | helpers outside every entry, which floor nodes call: `_stale_mock_project` feeds tier-A `tests/test_agent_pill_click.py::TestNoEnabledButtonIsRefused::test_every_enabled_button_navigates`; the helpers in `test_stale_ai_features.py` feed tier-A `tests/test_stale_ai_features.py::test_stale_mock_allows_stack_advisor`; `two_state_project` feeds tier-B `tests/test_agent_rows.py::TestAMissingUsageEntry` and `::TestItLeadsTheProjectView` | — | 7 sleeps in 4 files: `test_agent_pill_click.py:51`; `test_stale_ai_features.py:19`, `:67`; `test_agent_rows.py:105`, `:107`; `test_deployer_invariants.py:88`, `:92` | decision: Phase 8, Part 2, or drop |

### 1.3 The two halves

**The rule.** An item is mechanical when all three of these hold:
- the tool that proves it exists, and has been used on the same shape before;
- it opens no floor file and no tier-B class;
- it needs no ruling beyond "do it as the report describes".

Everything else is a decision. "Opens" is read as editing a whole-file entry, a tier-B
class or a tier-A node. A hunk elsewhere in a file that holds entries is §51.6's
allowed-and-reported case and does not open the file. P19 is the one mechanical item that
certainly has such hunks; P21 and P22 have them only if a test lands in such a file.

**Mechanical, 12 items:** P5, P6 and P7, the three turns; P11; P14; P16; P17; P19; P20;
P21; P22; P23a. P19 and P23a hold on one condition, below.

**Decision, 19 items:** P1, P2, P3, P4, P8, P10, P12, P15, P18, P23b, P24, P25, P26, P27,
P28, P29 and P30 from Part 1, and P31 and P32 from the record.

**Neither: P9 and P13.** One is a standing ruling and the other a design limit, and
neither has a sub-phase.

**Where the measurement moved an item against the directive's expected lists:**
1. **`revision_delta` (P10) moves to decision.** Everything but its home is mechanical:
   - one body, token-identical again when re-measured;
   - every module can keep its binding, so no test changes;
   - one mutation on the one body, predicted in all five test groups;
   - check 4 on the one patch string.

   But the home the report names, `agents/_utils.py`, is a retired façade. It has 0
   statements, and its docstring says "Nothing is defined, imported or re-exported here any
   more": it was kept only so that 4j was an import-only change. Doing the lift as
   described revives what 4j retired, and that is a ruling.
2. **`_fmt_usd` and `str` (P18) moves to decision.** It is a question, and no measurement
   answers it. Inventory §60.7 calls it "a design question".
3. **"The 35 load-bearing rows" is two rows of work.** Only `_as_int` and
   `round_number_from_value` have a Phase 8 form, `object` (P16). The other 33 stay on
   §77.3's reasons, and there is nothing to take.
4. **`run_with_timeout` (P17) stays mechanical, and is smaller than recorded.** The record
   says its generic form needs a runtime `TypeVar` (inventory §77.1). The PEP 695 form does
   not: the strip check erases type parameters, and the form is strict-clean on a scratch
   export. Nothing in `src/` calls the function.
5. **The racing nine (P19) and the `> 2` check (P23a) stay mechanical on one condition.**
   By the rule as written they are decisions until their proofs exist. §1.4 proposes both;
   approving §1 approves the proofs, and the rule then holds.
6. **The `> 2` item is two rows.** The check is mechanical (P23a). Whether flipping the
   guard is a fix is the ruling inventory §78.4 deferred until the evidence exists (P23b).
7. **The trim (P11) stays mechanical, with a stated home.** The report names none. The
   home proposed is one helper beside `MechanismPattern` in `agentifier/pattern_loader.py`,
   which both callers already import. It takes each caller's limit as a parameter, so both
   constants stay.
   - Removing the trim from that helper fails a test on each side. The untrimmed
     absorption lines run 459–531 characters, against the `< 260` in
     `test_tier_analyst.py::TestBuildMechanismAbsorptionList::test_descriptions_are_trimmed`.
     The untrimmed definitions fail the `<= 201` in `test_feature_specs.py`.
   - If that home is not wanted, P11 moves to decision beside P10.
8. **Items the expected lists did not place:**
   - the prop-bound inputs (P14) are mechanical: 7o's shape, with 7o's tools;
   - the 148 `-> Any` lines (P15) are a decision: they want a classification, and a width
     check for returns that does not exist;
   - PLR2004 (P25) is a decision: 11 of its findings sit in whole-file entries, and
     `scripts/`'s share is P26's question.

### 1.4 Proofs to design

Each paragraph proposes; none of them decides. They cover the three rows marked `none —
needs a proof designed` (P19, P23a, P15's return side), P24's move petition, which P27
and P28 share, and P21's closure, which needs a tool the twelve lack.

**P19, the racing nine: waiting on the stream, asserted so that the test cannot pass by
timing.**
- **The mechanism, read at HEAD.**
  - `on_breadth_try_again` copies the session shallowly (`callbacks/_chat.py:344`,
    `dict(session or {})`), hands the copy to `streaming.start` (`:378`), and returns a new
    top-level dict built from it (`:379`).
  - The worker is a daemon thread (`streaming.py:295`). It marks its entry `done` under
    `_lock` (`:290–291`).
  - `_mocked_draw()` exits as soon as the callback returns, so the worker can run on
    after the patches are gone.
  - The returned store and the worker's session share every nested container, so a live
    worker can still change what a store holds.
- **The proposal: wait on the stream's own entry, inside the patches.** A test helper
  polls `streaming.get(stream_id)["done"]` until it is true, against a bounded deadline
  that fails the test if it passes. That is a wait on a condition, not a fixed sleep. It
  runs inside `with _mocked_draw():`, in `TestGuidedRedraw._run` (six tests) and in the
  three other bodies. The existing assertions on the returned store stay as they are.
  Patching `streaming.start`, the other option §79.0 named, is not taken, as the directive
  says.
- **The assertion that makes timing irrelevant, positive with negative.** After the wait,
  on the entry:
  - `entry["error"]` is false, and the text carries what only the mocks produce: the
    mocked stream's `"Hello!"`;
  - no chunk carries `"raised:"`.

  A worker that escaped the patches then fails the test every time. Today it passes.
- **Two mutations, in the harness:**
  - *M-late:* the worker sleeps before it starts, one anchored line in `streaming.py`'s
    `_run`. The nine must still pass: the wait carries them, not the timing.
  - *M-escape:* M-late, plus the wait helper made a no-op, one anchor in the test file.
    The nine's new assertions must fail. If only older tests fail, that is the failure
    condition (report §3).
- **The timing evidence:** five traced runs of the fixed tree, with the default family and
  a fixed `--basetemp`, show no worker divergence and no network reach in any of the nine.
  The unchanged tree fired in three of five traced runs at 7q2, and once in §1.1's run.
- **To re-read before the edit:** the three tests that chain redraws,
  `test_every_click_is_one_history_event`, `test_notes_accumulate_across_retries` and
  `test_blank_note_keeps_prior_notes_and_refreshes_the_set`. With the wait, the second
  redraw always starts after a finished first worker. Today it may not.
- **Tools:** the mutation harness and trace identity, both unchanged. No production seam is
  proposed: a `streaming.wait()` would be a `src/` change, and the entry already carries
  its `done` flag.

**P23a, the `> 2` guard: does real output reach the header-only case?**
- **What it shows:** whether any output the app renders reaches the case. The case is a
  non-empty `mechanisms` or `knowledge_sources` list whose entries are all skipped (not a
  dict, or no `name`), or a `tool_access.capabilities_needed` whose entries all lack a
  `purpose`. The builders then return the header alone, for example `['**Mechanisms**',
  '', '']`.
- **No live call. Three parts:**
  1. *The path.* Every step from the Spec Drafter's output to `render_feature_block` that
     could drop or reshape an entry is read, and cited by file and line. So far only one
     thing is measured: `spec_drafter.py` defines no entry-level normaliser. Its functions
     are the prompt builders and `stream`.
  2. *The fixtures.* Every tracked JSON that carries the three keys goes through the three
     builders, and each result is classified as empty, header-only, or with entries. Today
     that is one file, `tests/golden/fixtures/spec_full.json`, which was written by hand.
  3. *The candidate fix, as a mutation.* The harness flips the three guards to `> 3` and
     runs the full suite. The prediction is that no test fails and every golden stays
     byte-identical, so no pinned output reaches the case. Any failure is evidence that one
     does, and it names the output.
- **Showing the check bites:** a probe with an all-skipped list, such as `["reflection"]`,
  must classify as header-only at HEAD and as empty under the flip. A list of strings is
  the shape behind inventory §12.4's item 1: the same empty-heading case in
  `_render_inputs`, which a golden fixture reached and which was fixed after Phase 1 with a
  golden update.
- **What it cannot show:** whether live model output ever takes that shape. The one
  recorded real output in the tree is the 51 files tracked under `.spec4/`. Rule 2 bars
  writes there, and the cleanup never read it. A read-only pass over its
  `ai_features.json` would be the direct evidence, and whether to take it is a ruling (D1).
- **Tools:** the mutation harness and the goldens. The classifier is a scratch probe, and
  no new tool is needed.

**P21's closure: every documented key seen changing.**
- **The per-test proof needs no new tool.** Each of the four contract tests is proven by
  one mutation that drops one documented write: the new test fails. That is the mutation
  harness, in 7n1's shape.
- **The closure does.** 7q3 found the 31 with a scratch contract check (inventory §79.3).
  The committed trace records no session snapshot at a generator's entry, because its
  start event leaves the session out, so "never seen changing" cannot be re-derived from
  it.
- **Proposed:**
  - an opt-in entry snapshot in `trace_identity.py`, off by default so that existing
    baselines still compare;
  - a contract report beside `trace_diff.py`. It parses each family function's "Its
    contract on ``session``" paragraph, and lists the documented keys observed and those
    never seen changing.
- **Its bite:** delete one documented write that a test does observe. The report must then
  list that key as never seen changing.
- **Scope:** it is a change under `scripts/cleanup/`, so it is also P26's question.

**P15's return side: the width rule for `-> Any`.**
- **What it shows:** a narrowed return annotation is no narrower than any value a test sees
  returned. That is the width rule (report §3), applied to returns.
- **Proposed:** extend the width sweep to hook `PY_RETURN` on each target's code object. It
  already reads one local there, `app.py`'s `content` (inventory §77.9). A row gains a
  return kind, and each returned value is checked against the return annotation.
- **Its bite:** narrow one return to a type that a test's returned value violates. The
  sweep must report it rejected, as 7o5's run reported `_fmt_usd`'s `str`.
- **Before any of it:** the 148 need classifying as edge, typeable or load-bearing, as
  §60.5 classified the 290. That is P15's ruling.

**P24, P27, P28: a petition for a moved test.**
- **What it shows:** a split or a merge moved tests and changed nothing else:
  - every node id collected before is collected after exactly once, under a new file with
    the same class and function names;
  - each moved test's body is token-identical, its assertions included: §60.3's check 2,
    applied to a move;
  - moved helpers and fixtures are token-identical;
  - the collected count is unchanged;
  - `floor.json` changes by exactly the moved ids, old to new, and the floor check passes
    456 / 456 on the amended file.
- **Proposed:** a `move_check.py` beside `petition_check.py`, taking an old-id → new-id
  map. The floor amendment is data, committed with the move.
- **Its bite:** smuggle one change into a moved assertion, as §60.2's smuggled `>=` did,
  and the check must fail on that node. Drop one test in the move, and the count must
  fail.

### 1.5 Proposed order and stops

**The gate at every commit, in both halves:**
- **The full gate:** `uv run ruff check src/ tests/` with the promoted set; `uv run ruff
  format --check src/ tests/`; `uv run mypy src/`, strict; and `uv run pytest --cov=spec4
  --cov-report=term-missing -q`, with any change to the 4,211 stated.
- **The floor at 456 / 456,** and the off-limits check in both halves, in §60.3's adapted
  form. `data/floor.json` is the off-limits list. New tests do not join the floor.
  §54.7's and §60.3's petition shapes stand, as amended.
- **Misses ≤ 876** on `tests/` alone.
- **The standing rules, unchanged:**
  - pruning by redundancy, coupling or vacuity, never by seconds;
  - runtime only as a paired same-session delta;
  - negative assertions paired with positive;
  - one mutation per seam, with the amended failure condition;
  - annotations no narrower than what a test exercises;
  - whole or carry;
  - the record carries only ruled changes.
- **This file is appended through `append_section.py`,** with `--guard` at each commit.
- **At the close of each half,** `remeasure.py 6956aca HEAD --cov-base
  scripts/cleanup/data/coverage_85a9cb6.txt --run-coverage /outside/dir`, with every moved
  cell explained.

**The mechanical half: dependency first, then size ascending.**

| Sub-phase | Item(s) | Half | Commits | The check that proves it | Petition |
|---|---|---|---:|---|---|
| 8a | P23a: the `> 2` reachability evidence | mechanical | 1, record only | §1.4: the path read; the fixtures classified; the flip as a mutation | none |
| 8b | P16, P17: three annotation rows | mechanical | 1 | strip check; strict mypy; width sweep; 5p's grep 232 → 230 | none |
| 8c | P20: the Prioritizer banner | mechanical | 1 | `probe_A`'s anchor: the new test fails | none |
| 8d | P11: the trim, as one helper | mechanical | 1 | one mutation fails a test on each side; frozen strings | none |
| 8e | P22: the five unreached targets | mechanical | 1 | the sweep reaches 63 of 63, 0 rejected; one mutation per function | none |
| 8f | P19: the racing nine | mechanical | 1 | §1.4: M-late passes; M-escape fails the new assertions; five traced runs without a network reach | none; hunks in `test_try_again.py` outside its tier-A nodes are allowed and reported |
| 8g | P21: four contract tests | mechanical | 1 | one mutation per test; the closure, if §1.4's extension is ruled in | none |
| 8h | P14: the prop-bound inputs | mechanical | 2: top-level `callbacks/`, then `callbacks/designer/` | strip check; width sweep on a new row map; strict mypy | none |
| 8i0 | P5–P7: baselines and probes | mechanical | 1, record only | three baselines per module, identical on the main thread; one probe per module, shown to bite | none |
| 8i1 | P5: `brainstormer.run` | mechanical | 1 | trace identity; frozen strings; one mutation; under the thresholds with `--ignore-noqa`, and its `noqa` deleted | none |
| 8i2 | P6: `code_scanner.run` | mechanical | 1 | as 8i1 | none |
| 8i3 | P7: `deployer.run` | mechanical | 1 | as 8i1 | none |
| **stop** | the half closes: `remeasure.py`, then review | | 0 | | |

That is 13 commits.
- **8a comes first.** It is record-only, and it means D1 can be ruled at the half's stop
  with its evidence in hand.
- **8b–8h follow by size.** The three turns come last: they are the largest, and they
  precede any decision that moves `test_agents.py` (D9), which holds 83 of their traced
  tests.
- **Each turn is its own item.** A turn whose proof fails carries whole to the next stop,
  and the other two go on.
  - 7q2's lesson stands: a step whose failure path no test reaches adds a miss. The misses
    inside the turns today are `deployer.py:586–587` and `brainstormer.py:688–689`.
  - A turn whose step must tell two ending causes apart stops there, and P8 is ruled
    first.

**The decision half: one sub-phase per ruling, each put as a question.**

| Sub-phase | Item(s) | The ruling asked | Commits if taken | The check that proves it | Petition |
|---|---|---|---:|---|---|
| D1 | P23b | With 8a's evidence, is flipping the three guards to `> 3` a fix? If yes: one commit, with a golden update if 8a shows a golden changes. If no: the three `noqa` reasons are rewritten to say that the header-only section is intended. And may 8a read `.spec4/`, read-only, for the direct evidence? | 1 | 8a's evidence; the goldens | none: a golden update is not a test-file edit |
| D2 | P18 | Does `_fmt_usd` accept `str`? If yes, the test pins a contract; the annotation stays, and the question closes with no edit. If no, the test is wrong: `test_cost_summary.py:160` is rewritten and the annotation narrows to `float \| None` | 0–1 | the width sweep; strict mypy | none |
| D3 | P10 | Where does the one `revision_delta` live: `agents/_utils.py`, reviving the façade 4j retired, or a named module the five import from? | 1 | one mutation, predicted in all five test groups; check 4 | none |
| D4 | P12 | Schedule the `sys.modules` simplification, which 7d ruled "not scheduled", or leave it? | 0–1 | check 4, setattr form | none |
| D5 | P31 | Keep `persist_artifacts`, or rename it, and to what? | 0–1 | rename check, token check, check 4 on 8 patch strings | none |
| D6 | P8 | Does the sentinel stay not taken, with 8i stopping on any turn that needs it? | 0 | — | — |
| D7 | P3, P4, P2 | Go or no-go on converting `project_manager` to a package? If go: the move, then batch 11's renames. `_with_readme_attribution`'s four sites in the golden whole-file entry go by a petition per node, or the name stays private | 2 | inventory §60.6's move check; rename tools; check 4 on the two `spec4._usage` strings | none for the move; §60.3 for `TestPreambleTwoAltitudesAndSurfaces`; by node id for the golden entry |
| D8 | P29, P1 | Consolidate `TestMockBuffers` with `TestMockDeliveryAck`? That opens `test_streaming_characterization.py`, and `_start_gen` and `_record_usage` ride with it. If not, both stay private (inventory §60.7(c)) | 1–2 | the move petition (§1.4); rename tools | by node id (inventory §50.5(a)); §60.3 for `test_designer.py`'s three tier-B classes and its one tier-A node |
| D9 | P24 | Split `test_agents.py` by source module, after 8i? | 1 or more | the move petition (§1.4) | a move petition for 16 tier-B ids |
| D10 | P27, P28 | The consolidation and the four large files: Phase 8, Part 2, or drop? | per ruling | the move petition | per ruling |
| D11 | P30 | `_golden.py`'s idioms: drop them, since the condition has not come about, or carry them to Part 2? | 0 | — | — |
| D12 | P25 | PLR2004 in `tests/`, `evals/` and `scripts/`: clear it, keep it deferred with the sizes corrected, or turn a deferral into an exemption? | per ruling | the inline check | the 11 in whole-file entries fit no petition |
| D13 | P26 | Bring the twelve tools inside the gate and under mypy, at 224 errors in 15 files? | 1–2 | the gate itself | none |
| D14 | P15 | Classify the 148 `-> Any` lines now, with §1.4's return-side sweep, or leave them with the design limit? | 0 until ruled | §1.4 | none |
| D15 | P32 | The mtime sleeps (inventory §62.8): Phase 8, Part 2, or drop? | 0–1 | `os.utime` makes the order a fact of the fixture; one mutation per fixture | none: the helpers sit outside every entry, and their hunks are allowed and reported |
| **stop** | the half closes: `remeasure.py`, then review | | 0 | | |

- **D1 comes first,** since 8a delivered its evidence. D2–D6 are small, and nothing waits
  on them.
- **D7's move precedes its renames.** D8, D9 and D10 share the move petition, and the first
  of them to be ruled in builds it.
- **D13 comes last.** Taken earlier, it would change the gate under every commit after it.

### 1.6 Mode per sub-phase

The pattern is the cleanup's (inventory §27.6, §60.7(j)): plan mode and `ultrathink` only
where a seam or a split is designed, and default mode at medium effort where a proven tool
carries the proof.

| Sub-phase | Mode | Effort | Auto | Why |
|---|---|---|---|---|
| 8a | default | medium | on | record only; the harness and the goldens carry the check |
| 8b | default | medium | on | 7o's pattern: annotations under the strip check |
| 8c | default | medium | on | one assertion, and `probe_A`'s anchor exists |
| 8d | default | medium | on | a lift to a stated home, proven by one mutation |
| 8e | default | medium | on | the sweep and the harness carry it |
| 8f | default | high | off | the proof is designed in §1.4, but its traced runs are judged at a stop before the commit, and the chained redraws are re-read first |
| 8g | default | medium | on | 7n1's key-set shape |
| 8h | default | medium | on | 7o's pattern; the row map is the work |
| 8i0 | default | high | off | record only, but each probe's prediction is written before it runs |
| 8i1–8i3 | plan, `ultrathink` | high | off | each turn's cut points into steps are a split designed: 7q's pattern |
| D1–D6, D11 | default | medium | on | a ruling, then an edit that a proven tool carries |
| D7 | plan, `ultrathink` | high | off | a package conversion is a move designed, beside a load-bearing `__all__` and a golden entry |
| D8, D9, D10 | plan, `ultrathink` | high | off | a merge or split designed, and the move petition built |
| D12 | default | medium | on | the inline check carries it, apart from whatever the ruling excludes |
| D13 | plan | high | off | it changes the gate itself: 5p's reason (inventory §27.6) |
| D14 | plan | high | off | a classification and a return-side sweep, designed |
| D15 | default | medium | on | fixtures set with `os.utime`, one mutation per fixture |

**Stopping here.** Committed as `phase8: pre-work (§1)`, this file only. Phase 8 begins on
approval of §1.

## 2. §1 approved: the rulings Phase 8 runs under, and 8a0, the stale PLR2004 figures

§1 was approved on 2026-09-11. The rulings below bind Phase 8, and where they differ from
§1's proposals they win. §1's findings otherwise stand as written.

### 2.1 The rulings

**(a) PLR2004 in `scripts/`.** It is not a stop: §1.1's stop covered the gate. The three
stale figures, in the report, in BACKLOG 1.3 and in `pyproject.toml`'s comment, are
corrected as the mechanical half's first commit, 8a0 (§2.3). The pre-work could not
touch two of those three files. The 14 findings belong to the tools and are settled by
D13. Until then the ignore carries a size of 20.

**(b) `revision_delta`'s home.** It is not `agents/_utils.py`: 4j's retirement of the
façade stands. The home is a new leaf module, `agents/_revision.py`, which holds the one
function and which the five import from. That is the leaf-pure-sibling shape the splits
used.
- **The proof:** the token-identical finding, plus the layering test passing with the new
  edge.
- **If the new edge makes a cycle,** stop and report.
- P10 is mechanical with that home, as sub-phase 8d2.

**(c) `_fmt_usd` and `str`: decided by measurement, not by asking.** The width sweep runs
over `src/`'s callers.
- **If no production caller passes a string,** the test's string case is dead behaviour.
  The annotation narrows, and the test line changes, with a petition if it is a floor
  node.
- **If one does,** the widened annotation is correct, and the question closes.
- P18 is mechanical with that rule, in 8b.

**(d) P16 and `run_with_timeout`.** Both of P16's rows are taken. For `run_with_timeout`,
"nothing in `src/` calls it" is a dead-code question before it is a typing one:
- if nothing in `src/`, `tests/`, `scripts/` or `evals/` calls it, it is deleted under
  Phase 2's rule, not typed;
- if tests call it, the PEP 695 form is approved as annotation-only.

**Measured on recording:** `tests/agentifier/test_subagents.py:181` and `:195` call it, and
nothing in `src/`, `scripts/` or `evals/` does. So P17's PEP 695 form is approved, in 8b.

**(e) §1.4's two proofs are approved, with one condition each.**
- **The racing nine (P19):** the proof asserts the stream's terminal state, the entry's
  `finalised` latch or `claim_finalise`'s one-shot. It never uses a sleep or a timeout, so
  it cannot pass by timing.
- **The `> 2` reachability check (P23a):** it reads `.spec4/` read-only, and records which
  files it read. Rule 2 forbade editing the tracked output; reading the only real model
  output in the repo is what that output is there for. D1 remains a decision after the
  check answers.

**(f) The trim's home.** It goes in `agentifier/pattern_loader.py`, beside
`MechanismPattern`, if both `tier_analyst` and `feature_specs` already import from it.
If either does not, it is a new edge and gets the same layering check as `_revision.py`.

**Measured on recording:** both already do (`agentifier/tier_analyst.py:17`,
`feature_specs.py:34`), so there is no new edge.

**(g) The 31 contract keys.** The tool extension that re-derives the write sets is
approved. It lands with the contract-test sub-phase, 8g, and the tests are written from
the re-derived set, not from §79.3's quote.

**(h) The rest.**
- The mtime sleeps (P32) join the mechanical half, under `os.utime`, as 8e2.
- `persist_artifacts`' name (P31) stays a decision (D5).
- The turns-before-topology dependency stands: 8i before D9.

### 2.2 The mechanical half, as ruled

This table replaces §1.5's where the two differ. §1.5's per-commit gate and §1.6's modes
stand, and the new sub-phases take the mode of the one beside them.

| Sub-phase | Item(s) | Commits | The check that proves it | What changed from §1.5 |
|---|---|---:|---|---|
| 8a0 | the three stale PLR2004 figures | 1 | the parsed `pyproject.toml` is unchanged; the ruff counts re-measured | new, (a) |
| 8a | P23a: the `> 2` reachability evidence | 1, record only | §1.4, reading `.spec4/` read-only, with the files read listed | (e) |
| 8b | P16, P17, P18: the type rows | 1 | strip check; strict mypy; the width sweep, with each value's caller recorded for P18 | P18 joins, (c); P17's form settled, (d) |
| 8c | P20: the Prioritizer banner | 1 | `probe_A`'s anchor | — |
| 8d | P11: the trim, as one helper in `pattern_loader.py` | 1 | one mutation fails a test on each side; frozen strings; no new edge | (f) |
| 8d2 | P10: `revision_delta`, one body in `agents/_revision.py` | 1 | token identity; the layering test with the new edge; one mutation on the one body; check 4 | new, (b) |
| 8e | P22: the five unreached targets | 1 | the sweep; one mutation per function | — |
| 8e2 | P32: mtimes set with `os.utime` | 1 | one mutation per fixture | new, (h) |
| 8f | P19: the racing nine | 1 | the terminal-state assertion, with no sleep and no timeout; the traced runs | (e) |
| 8g | P21: four contract tests, and the write-set extension | 1–2 | the extension shown to bite; one mutation per test | (g) |
| 8h | P14: the prop-bound inputs | 2 | as §1.5 | — |
| 8i0–8i3 | P5–P7: the three turns | 4 | as §1.5 | — |
| **stop** | the half closes: `remeasure.py`, then review | 0 | | |

The decision half loses D2 (P18), D3 (P10) and D15 (P32), which are now mechanical.

### 2.3 Commit 8a0: the three stale PLR2004 figures

| File | Was | Now |
|---|---|---|
| `CLEANUP_REPORT.md` §1 | `scripts/` (6) | `scripts/` (20: 6 at promotion, and 14 in `scripts/cleanup/` since the tools were committed, which go with Phase 8's tools decision) |
| `CLEANUP_REPORT.md` §5.3 | 6 in `scripts/` | 20 in `scripts/`, 6 at promotion, the 14 going with §5.4 |
| `BACKLOG.md` 1.3 | 6 in `scripts/` | 20 in `scripts/`, 6 at promotion, the 14 going with the tools (1.4) |
| `pyproject.toml`, the per-file-ignores comment | "6 in scripts/. Those counts are the size of the later work." | the same, then: `scripts/` carries 20 since the tools were committed, and the 14 go with the tools decision |

**The proof.**
- **`pyproject.toml` changes in a comment alone.** Parsed with `tomllib`, HEAD's file and
  the new one are equal: `parsed pyproject.toml identical to HEAD: True`.
- **The figures are the ones measured.** `ruff check --isolated --select PLR2004` gives
  `tests/` 230, `evals/` 25, `scripts/` 20 and `src/` 0.
- **Footprint:** 3 files, 8 insertions and 4 deletions, plus this section.

| Gate | Result |
|---|---|
| Ruff, `src/ tests/` and `.` / format / mypy | `All checks passed!` twice · `221 files already formatted` · `Success: no issues found in 92 source files` |
| Tests | `4210 passed, 1 skipped` (exit 0) |
| Coverage | `TOTAL 12459 876 93%`; every per-module row identical to `coverage_85a9cb6.txt` |
| Floor / off-limits | **456 / 456** (`FAILURES: 0`); no test file touched |

## 3. 8a: the `> 2` guard, and what reaches it (P23a) — record only

§1.4's proof, under §2.1(e)'s condition. Nothing under `src/` or `tests/` changed, and
nothing was written under `.spec4/`: the tree was clean after every read.

### 3.1 What was read

- **`.spec4/`, read-only: all 51 tracked files.**
  - 21 JSON, 7 per round in `v0`–`v2` (`code_review.json`, `design/manifest.json`,
    `design/session.json`, `feature_specs.json`, `stack.json`, `usage.json`,
    `vision.json`), each parsed and walked for the three keys.
  - 24 phase files, read for the section headings: `phases/phase1.md`–`phase7.md` in
    each round, `v1/phases/phase8.md`, and `v0/phases/phase1-notes.md` and
    `phase7-notes.md`.
  - 6 more, searched only: `IMPLEMENTED` and `design/mock.html` in each round.
  - One JSON would not parse: `.spec4/v1/design/manifest.json`, an invalid control
    character at line 428, column 46. A text search of it finds none of the three keys.
- **The fixtures:** the 20 JSON files under `tests/golden/fixtures/`, and the 16 under
  `evals/`.

### 3.2 The path, read

| Step | Where | What happens to an entry |
|---|---|---|
| The request | `agentifier/spec_drafter.py:114–135`; `:251` | the schema asks for objects; `mechanisms` is optional and empty by default |
| The draw | `agentifier/agentifier.py:562`, `_draft_spec` | `extract_json_block` (`:624`), with `json.loads` as the fallback; the parsed dict is stored whole in `agentifier_spec_results` (`:661`) |
| The merge | `agentifier/_render.py:233`, `build_ai_features` | `feature.update(spec)`: the drafter's keys pass through untouched |
| The render | `_phase_markdown.py:184`, `:272`; `agents/_feature_context.py:445`, `:983`, `:1090`, `:1286` | `render_feature_block`, which dispatches by field name and filters nothing (`feature_specs.py:521–552`). `PHASE_SPEC_FIELDS` includes all three fields (`feature_specs.py:88–92`) |

**No step between the model's output and the three builders drops or reshapes an
entry.** An all-skipped list reaches them as the model wrote it.

### 3.3 What reaches the case

**Real output: 24 phase files, and not one of the three sections.**
- The files render AI-capability blocks: 38 **Inputs** and 38 **Failure modes**, every one
  with entries.
- **Mechanisms**, **Knowledge sources** and **Tool access** appear 0 times, neither
  populated nor header-only.
- **The renderer that wrote them had all five guards at `> 2`.** The phase files were
  written on 2026-09-06 and 2026-09-07 (`e4b0aa1`, `47d4b0c`). The three builders date
  from `72a23d8` (1.0.0, 2026-08-04), and their guards have not changed since. The
  siblings moved to `> 3` in `8b277fd` (2026-09-08), after the files. So a header-only
  section from any of the five builders would show, and none does.
- **What the files cannot show:** whether the specs behind them carried the three fields
  at all, because `ai_features.json` is not tracked. The headings' absence means only
  that each value was absent, empty, or not a list, which is the builders' first guard.
  No value was a non-empty list of skipped entries.

**The JSON: 57 files, and one carries the keys.** It is `tests/golden/fixtures/spec_full.json`:

| Key | Value | Builder's result |
|---|---|---|
| `mechanisms` | `[{"name": "RAG", "rationale": "grounding"}, "reranking"]` | entries |
| `knowledge_sources` | `["policy library", "glossary"]` | **header-only** |
| `tool_access` | `[{"tool": "search_policies", "scope": "read"}]`, a list where a dict is read | empty |

The fixture is hand-written, and one test reads it: `test_renderer_goldens.py:163`,
through `_format_spec_as_text` in `agentifier/_render.py`. That renderer takes these
fields through its own `_spec_field`, not through the three builders, so no pinned output
reaches the case.

**The probe bites.** `probe_8a.py`, a scratch probe, classes each builder's result as
empty, header-only, or with entries. With one all-skipped list per builder:

```
at HEAD:           bite mechanisms: header-only ['**Mechanisms**', '', '']
                   bite knowledge_sources: header-only ['**Knowledge sources**', '', '']
                   bite tool_access: header-only ['**Tool access**', '', '']
under the flip:    bite mechanisms: empty []
                   bite knowledge_sources: empty []
                   bite tool_access: empty []
```

Under the flip, applied to a `git archive` export and imported from it, `spec_full.json`'s
`knowledge_sources` goes from header-only to empty.

**The candidate fix as a mutation,** on the full suite. The case:

```json
{"label": "the candidate fix: the three section guards > 2 -> > 3 (8a, P23a)",
 "edits": [three anchored edits in src/spec4/feature_specs.py, each ending
           "return lines if len(lines) > 2 else []" -> "... > 3 else []", anchored on the
           line before the guard: "lines.append(f\"  - {key}: {detail}\")",
           "head += f\" [updates: {freq}]\"" and "lines.append(f\"  - Rationale: {rationale}\")"],
 "fail": []}
```

```
restore: 1 file(s) byte-identical by sha256; tree clean
M 8a_flip (the candidate fix: the three section guards > 2 -> > 3 (8a, P23a)): predicted 0, failed 0; must-pass 0, failed 0; A WRONG PREDICTION
   other failures: 0
   summary: 4210 passed, 1 skipped in 96.63s (0:01:36)
```

- **No test fails, so no pinned output reaches the case.** Every golden stays byte-identical:
  a golden mismatch is a test failure.
- **"A WRONG PREDICTION" is the harness's construction, not the result.** `mutate.py`'s suite
  verdict needs at least one predicted failure (`ok = not missed and not broke and
  bool(hit)`), so a case that predicts none can never read "as predicted". The verdict is
  read from the lines it prints: 0 other failures, and 4,210 passed.

### 3.4 The answer, for D1

- **Nothing the app has written reaches the header-only case,** across 24 real phase files,
  and nothing the suite pins reaches it: the flip fails no test.
- **The one input in the tree that reaches it** is a hand-written list of strings in a
  golden fixture, which its test feeds to a different renderer.
- **It is still reachable in principle.** The Spec Drafter's schema asks for objects, but
  nothing between its output and the builders reshapes an entry. A model that answered
  with strings, as the siblings' case once did (inventory §12.4, item 1), would reach it.
- **D1 stays a decision, with this evidence:** is the flip a fix, when it changes no pinned
  output and the case needs malformed drafter output to occur, or is the header-only
  section intended?

| Gate | Result |
|---|---|
| Ruff / format / mypy | re-run: `All checks passed!` · `221 files already formatted` · `Success: no issues found in 92 source files` |
| Tests | not re-run, and the reason is checkable: against `578cf22` the diff is this file alone, so 8a0's `4210 passed, 1 skipped` stands. The flip's run above is the suite under the mutation |
| Coverage | 8a0's `TOTAL 12459 876 93%` stands, for the same reason |
| Floor / off-limits | re-run: **456 / 456** (`FAILURES: 0`); no test file touched |

## 4. 8b: the type rows (P16, P17, P18), and the width sweep's callers

§2.1(c) and (d). `src/` changes in annotations alone. There is one test line, as ruled, and
one tool extension.

### 4.1 What landed

| File | Change |
|---|---|
| `src/spec4/llm.py:299` | `_as_int(value: Any)` → `value: object` (P16) |
| `src/spec4/layouts/_artifact_view.py:764` | `round_number_from_value(value: Any)` → `value: object` (P16) |
| `src/spec4/agentifier/subagents.py:239` | `run_with_timeout(coro: Awaitable[Any], …) -> Any` → `run_with_timeout[T](coro: Awaitable[T], …) -> T`, the PEP 695 form (P17) |
| `src/spec4/layouts/_shared.py:195` | `_fmt_usd(value: float \| str \| None)` → `value: float \| None` (P18, decided by measurement) |
| `tests/test_cost_summary.py:160` | `assert _fmt_usd("0.5") == "not available"` removed (P18's test line) |
| `scripts/cleanup/width_sweep.py` | each observed value's caller is recorded, per target (§4.4) |

Footprint: 6 files, 28 insertions and 8 deletions, plus this section.

### 4.2 P18: no production caller passes a string

**The measurement.** The extended sweep, run before P18's edit, saw `_fmt_usd`'s argument
66 times, from these callers:

```
spec4.layouts._shared:_cost_figure builtins.float ok=True x60
tests.test_cost_summary:TestFormat.test_four_decimals_with_thousands builtins.float ok=True x2
tests.test_cost_summary:TestFormat.test_four_decimals_with_thousands builtins.int ok=True x1
tests.test_cost_summary:TestFormat.test_none_and_non_numbers_read_as_not_available builtins.NoneType ok=True x1
tests.test_cost_summary:TestFormat.test_none_and_non_numbers_read_as_not_available builtins.bool ok=True x1
tests.test_cost_summary:TestFormat.test_none_and_non_numbers_read_as_not_available builtins.str ok=True x1
```

- **The one caller in `src/`, `_cost_figure`, passed a float on all 60 calls.** The one
  string is the test's own direct call.
- **So, by §2.1(c), the string case is dead behaviour.** The annotation narrows to
  `float | None`, and the test line goes.
- **The body is unchanged,** so a stray value still reads "not available" at runtime. The
  strip check below shows it.
- **Not a floor node.** The hunk is in
  `TestFormat::test_none_and_non_numbers_read_as_not_available`. The file's three tier-A
  nodes (`TestChatPlacement::test_sits_between_the_transcript_and_the_action_row`,
  `TestDesignerPlacement::test_preview_step_shows_the_strip`,
  `TestStripNumbers::test_it_mounts_all_three_lines`) are untouched, so the hunk is allowed
  and reported (§51.6), and no petition applies.
- **The pairing holds.** `TestFormat` still pairs the positive cases (`$0.0123`,
  `$1,234.5000`, `$0.0000`) with the negative ones (`None` and `True`).
- **The width rule, on the narrowed annotation:** the sweep re-run at 8b's final tree
  reads `targets 63; reached 58; never reached 5; rejected by a real value 0 []`.
  `_fmt_usd` saw 65 values, `float` ×62 and `int`, `bool` and `None` once each, and
  `float | None` accepted every one.
- **BACKLOG 1.2's question closes: `_fmt_usd` does not accept `str`.**

### 4.3 P16 and P17: annotation-only

- **The strip check against HEAD:** `files changed: 4; files with residue: 0`. Each of
  `llm.py`, `_artifact_view.py`, `subagents.py` and `_shared.py` is empty after the strip.
  The check erases PEP 695 type parameters, so P17's `[T]` is annotation material.
- **Strict mypy:** `Success: no issues found in 92 source files`.
- **5p's grep: 232 → 230.** The two `object` rows take the load-bearing rows from 35 to 33.
  P17's line held no `: Any`.
- **The `-> Any` return lines outside the grep: 148 → 147,** P17's return (P15's count).
- **P17's callers are the two tests** in `tests/agentifier/test_subagents.py` (§2.1(d)). The
  sweep's target for its `coro` now reads `Awaitable[T]`, and it accepted every value it
  saw.
- **P16's two rows are not sweep targets,** because they are load-bearing rows. `object`
  admits every value, so the width rule holds for them trivially.

### 4.4 The sweep's extension: callers, per target

- **What it adds:** for each observed value, the calling frame's module and qualified name
  (`_caller`), counted per target and written as a `callers` field. The summary line is
  unchanged.
- **Shown to change nothing else.** Run on 8b's tree before P18's edit and compared with
  §1.1's run:
  - the same 63 targets;
  - the observed types and call counts identical for every target;
  - the only annotation that differs is P17's own edit, `Awaitable[Any]` → `Awaitable[T]`;
  - the same summary line: `targets 63; reached 58; never reached 5; rejected by a real
    value 0 []; by stand-ins only 0; checker errors 0 []`.
- **What it shows beyond P18:** 45 of the 58 reached targets have at least one caller in
  `src/`, and 13 are reached only from tests.
- **The tools stay outside mypy (D13).** ruff and ruff format are clean on
  `scripts/cleanup/`.

| Gate | Result |
|---|---|
| Ruff, `src/ tests/` and `.` / format / mypy | `All checks passed!` twice · `237 files already formatted` (`src/`, `tests/` and `scripts/cleanup/`) · `Success: no issues found in 92 source files` |
| Tests | `4210 passed, 1 skipped` (exit 0); 4,211 collected, since a removed assertion removes no test |
| Coverage | `TOTAL 12459 876 93%`: every per-module row identical to 8a0's, since annotations add no statement |
| Floor / off-limits | **456 / 456** (`FAILURES: 0`); the one test hunk sits outside every entry |

## 5. 8c: the Prioritizer banner, asserted whole (P20)

This is inventory §79.0's finding closed. Probe A changed one character of the banner the
developer reads at every priority turn, and every test still passed. One test is added,
and nothing under `src/` changes.

### 5.1 What landed

`tests/agentifier/test_prioritizer.py::TestBeginPriorityPhase::test_the_turn_opens_with_the_prioritizer_banner`
asserts that the turn's output opens with the whole banner, all three of its parts:

```python
assert self._run(session).startswith(
    "### Prioritizer\n\n"
    "Working out what belongs in the steel thread, and what can wait…\n\n"
    "_This usually takes a few seconds._\n\n"
)
```

- **The draw is stubbed** by the autouse `stub_prioritizer` fixture (`tests/conftest.py:36`),
  as it is for the class's other tests, so no model is reached.
- **Floor:** `test_prioritizer.py` holds no floor entry.
- **Footprint:** 1 file, 13 insertions, plus this section.

### 5.2 The mutation: `probe_A`'s anchor, as a suite case

The anchor is `probe_A`'s from `data/cases_7q.json`, which still matches once at HEAD. The
prediction is that the new test fails, and nothing else does.

```
restore: 1 file(s) byte-identical by sha256; tree clean
M 8c_banner (one banner character: the Prioritizer banner (7q0's probe A, as a suite case)): predicted 1, failed 1; must-pass 0, failed 0; as predicted
   FAILED (predicted)       tests/agentifier/test_prioritizer.py::TestBeginPriorityPhase::test_the_turn_opens_with_the_prioritizer_banner
   other failures: 0
   summary: 1 failed, 4210 passed, 1 skipped in 94.68s (0:01:34)
```

**As predicted: the new test fails, and nothing else does.** The banner is now pinned by the suite, where 7q0 found it pinned only by the trace.

| Gate | Result |
|---|---|
| Ruff / format / mypy | `All checks passed!` · `221 files already formatted` · `Success: no issues found in 92 source files` |
| Tests | `4211 passed, 1 skipped` (exit 0): one more than 8b, the new test |
| Coverage | `TOTAL 12459 876 93%`; every per-module row identical to 8a0's |
| Floor / off-limits | **456 / 456** (`FAILURES: 0`); the file holds no entry |

The commit was made before the mutation ran, because the harness refuses a dirty tree.
This section was then appended and amended in, under the standing rule for unpushed
commits (inventory §64.10, §73.10).

## 6. 8d: the mechanism-summary trim, one helper in `pattern_loader.py` (P11)

The dedupe inventory §78.2 found, placed as §2.1(f) ruled: beside `MechanismPattern`, since
both callers already import from `pattern_loader`. No new import edge.

### 6.1 What landed

| File | Change |
|---|---|
| `src/spec4/agentifier/pattern_loader.py` | `trimmed_description(pattern: MechanismPattern, limit: int) -> str`, right after `MechanismPattern`, and in `__all__`. It collapses the whitespace, and if the result is over `limit` it cuts it, strips the trailing space and appends "…" |
| `src/spec4/agentifier/tier_analyst.py` | `_build_mechanism_absorption_list`'s three lines become `trimmed_description(m, _PROMPT_DESCRIPTION_CHARS)`, and the import gains the name |
| `src/spec4/feature_specs.py` | `_mechanism_definitions`'s three lines become `trimmed_description(m, _MECHANISM_SUMMARY_CHARS)`, and the import gains the name |

- **Both constants stay.** Each caller passes its own limit, and each limit is its own
  tunable quantity (inventory §78.2's criterion). They share a value, not a meaning.
- **The near-copy stays too.** `_build_tier_descriptions` at `tier_analyst.py:312–314`
  strips rather than collapsing whitespace, so it is not an exact match and is not
  lifted.
- **Footprint:** 3 files, 18 insertions and 8 deletions, plus this section.

### 6.2 The proofs

**Token identity.** `trim_tokens.py`, a scratch script, reads each caller's three lines from the parent commit, substitutes the caller's names (`m` → `pattern`, the caller's constant → `limit`), and compares `tokenize` tokens, with comments and layout dropped, against the helper's first three statements. This is §67.11's method.

```
src/spec4/agentifier/tier_analyst.py: 35 tokens; identical to the helper's first three statements: True
src/spec4/feature_specs.py: 35 tokens; identical to the helper's first three statements: True
helper's first three statements: 35 tokens
```

**No new edge.** `tier_analyst.py` and `feature_specs.py` already imported from `pattern_loader`, and each import line only gains the name. `tests/test_import_layering.py` passes, with the two callers' own test files: `69 passed`.

**Frozen strings (Rule 4).** Only the two literals of the trim move, and `__all__` gains a name. No prompt text changes.

```
src/spec4/agentifier/pattern_loader.py: string constants 134 -> 137; distinct 77 -> 79
  gone: 0; added: 2; count changes: 1
  ADDED 'trimmed_description'
  ADDED '…'
  COUNT 2 -> 3  ' '
src/spec4/agentifier/tier_analyst.py: string constants 132 -> 130; distinct 100 -> 99
  gone: 1; added: 0; count changes: 1
  GONE  ' '
  COUNT 2 -> 1  '…'
src/spec4/feature_specs.py: string constants 262 -> 260; distinct 145 -> 144
  gone: 1; added: 0; count changes: 1
  GONE  '…'
  COUNT 2 -> 1  ' '
```

- **Across the three files, `' '` and `'…'` each fall by one.** Two copies of the trim became one.
- **`tier_analyst.py` keeps one `'…'`,** in `_build_tier_descriptions`, the near-copy that stays.
- **`feature_specs.py` keeps one `' '`,** in an unrelated join.

**The mutation: the trim removed from the helper.** The prediction is that the two tests
that pin each side fail.

```
restore: 1 file(s) byte-identical by sha256; tree clean
M 8d_trim (the one trim removed from the shared helper (8d, P11)): predicted 2, failed 2; must-pass 0, failed 0; as predicted
   FAILED (predicted)       tests/agentifier/test_tier_analyst.py::TestBuildMechanismAbsorptionList::test_descriptions_are_trimmed
   FAILED (predicted)       tests/test_feature_specs.py::TestMechanismGlossary::test_all_library_mechanisms_have_definitions
   other failures: 0
   summary: 2 failed, 4209 passed, 1 skipped in 95.05s (0:01:35)
```

**As predicted: both sides fail, and nothing else does.** Both callers now reach the one helper, and each side's own test pins the trim. The untrimmed absorption lines run 459–531 characters, against `< 260`, and the untrimmed definitions fail `<= 201` (§1.3). The commit was made before the mutation ran, because the harness refuses a dirty tree. This section was then amended in, under the standing rule for unpushed commits.

| Gate | Result |
|---|---|
| Ruff / format / mypy | `All checks passed!` twice (`src/ tests/`, `.`) · `221 files already formatted` · `Success: no issues found in 92 source files` |
| Tests | `4211 passed, 1 skipped` (exit 0) |
| Coverage | `TOTAL 12459 876 93%`, unchanged in total. Three rows moved, as a lift moves them: `pattern_loader.py` 159 → 164 statements, `tier_analyst.py` 132 → 130 and `feature_specs.py` 344 → 341, each with its misses unchanged (18, 3, 80) |
| Floor / off-limits | **456 / 456** (`FAILURES: 0`); no test file touched |

## 7. 8d2: `revision_delta`, one body in `agents/_revision.py` (P10)

Inventory §67.11's dedupe, homed as §2.1(b) ruled: a new leaf module that the five import
from. 4j's retirement of `agents/_utils.py` stands.

### 7.1 What landed

| File | Change |
|---|---|
| `src/spec4/agents/_revision.py` | new: `revision_delta`, the one body, with the five docstrings merged into one, and `__all__`. It imports nothing from `spec4` |
| `src/spec4/agentifier/_render.py` | the copy dropped; `from spec4.agents._revision import revision_delta`, which stays in `__all__` for `agentifier.py`'s import |
| `src/spec4/agents/deployer.py` | the copy dropped; a plain import, since four call sites in the module use it |
| `src/spec4/agents/designer.py` | the copy dropped; `import revision_delta as revision_delta`, the explicit re-export strict mypy needs for `layouts/designer.py` and `callbacks/designer/_wizard.py` |
| `src/spec4/agents/phaser/_revision.py` | the copy dropped; the `as` re-export for the package `__init__`; one docstring sentence says where the function now lives |
| `src/spec4/agents/stack_advisor/_stack_shape.py` | the same, for the package `__init__`; one docstring sentence |

- **Every existing import path still resolves,** so no test and no other `src/` file
  changes. That covers `stack_advisor.revision_delta`, `phaser.revision_delta`,
  `deployer.revision_delta`, the `agentifier` re-export, and `agents.designer`'s.
- **The merged docstring** keeps the text the five shared, and the envelope sentence
  three of them carried. It drops the "twin of …" sentences, which no longer describe
  anything.
- **Footprint:** 6 files. `agents/_revision.py` is new, at 32 lines, and the five edited files take 11 insertions and 96 deletions.

### 7.2 The proofs

**Token identity, re-run against the parent commit.** `delta_tokens.py`, a scratch script using §67.11's method, sets the docstring aside and compares `tokenize` tokens:

```
new: agents/_revision.py, 69 body tokens, signature (vision: dict[str, Any] | None -> dict[str, Any] | None)
src/spec4/agentifier/_render.py: 69 tokens; body identical: True; signature identical: True
src/spec4/agents/deployer.py: 69 tokens; body identical: True; signature identical: True
src/spec4/agents/designer.py: 69 tokens; body identical: True; signature identical: True
src/spec4/agents/phaser/_revision.py: 69 tokens; body identical: True; signature identical: True
src/spec4/agents/stack_advisor/_stack_shape.py: 69 tokens; body identical: True; signature identical: True
```

**Frozen strings.** Each of the five modules loses exactly its copy's two literals. In `deployer.py` and `designer.py` the count of `'vision_statement'` falls by one, because other code in them still uses it; elsewhere the literals are gone. No prompt text changes.

```
src/spec4/agentifier/_render.py: GONE 'revision_history', 'vision_statement'
src/spec4/agents/deployer.py: GONE 'revision_history'; COUNT 5 -> 4 'vision_statement'
src/spec4/agents/designer.py: GONE 'revision_history'; COUNT 4 -> 3 'vision_statement'
src/spec4/agents/phaser/_revision.py: GONE 'revision_history', 'vision_statement'
src/spec4/agents/stack_advisor/_stack_shape.py: GONE 'revision_history', 'vision_statement'
```

**The layering test passes with the new edge, and there is no cycle.** `agents/_revision.py` imports nothing from `spec4`, so it cannot close a cycle. Its one importer outside `agents/` is `agentifier/_render.py`, an agent-side module importing an agent-side one, which the layering rules allow. `tests/test_import_layering.py` passes, with the five test files that reach `revision_delta` through each old binding: `496 passed`.

**Check 4 on the one patch string** (`patch_resolve.py`, with the map `[["revision_delta", "revision_delta"]]`):

```
PASS tests/test_designer_fullscreen.py:100 [path] spec4.callbacks.designer._wizard.revision_delta
     (1) function revision_delta  (2) src/spec4/callbacks/designer/_wizard.py re-exports it from spec4.agents._revision; calls it at on_designer_carry_forward@164
targets ending in a batch name (new side): 1; FAIL: 0; fourth-form candidates: 0
```

**The mutation: the one body never returns the history's last entry.** The prediction is
that the five tests asserting a returned delta fail: one per former copy, each reaching
the body through its own module's binding.

```
restore: 1 file(s) byte-identical by sha256; tree clean
M 8d2_delta (the one revision_delta never returns the history's last entry (8d2, P10)): predicted 5, failed 5; must-pass 0, failed 0; as predicted
   FAILED (predicted)       tests/agentifier/test_revision.py::TestRevisionDelta::test_returns_last_history_entry
   FAILED (predicted)       tests/test_designer.py::TestRevisionDelta::test_returns_last_history_entry
   FAILED (predicted)       tests/test_agents.py::TestStackAdvisorRevisionMode::test_delta_returns_last_history_entry
   FAILED (predicted)       tests/test_agents.py::TestPhaserRevisionMode::test_delta_returns_last_history_entry
   FAILED (predicted)       tests/test_agents.py::TestDeployerRevisionMode::test_delta_returns_last_history_entry
   FAILED (other, to explain) tests/agentifier/test_revision.py::TestFreshStartRevisionDetection::test_detects_revision_and_informs_scout
   FAILED (other, to explain) tests/agentifier/test_revision.py::TestFreshStartRevisionDetection::test_zero_prior_ai_features_still_revision
   FAILED (other, to explain) tests/agentifier/test_revision.py::TestRevisionScoutZeroNew::test_zero_new_candidates_finalises_carried_forward
   FAILED (other, to explain) tests/agentifier/test_try_again.py::TestRevisionRound::test_revision_block_is_re_derived_from_disk
   FAILED (other, to explain) tests/agentifier/test_try_again.py::TestRevisionRound::test_scout_is_told_it_is_a_revision
   FAILED (other, to explain) tests/test_agents.py::TestDeployerRevisionMode::test_revision_seed_carries_prior_plan_and_scopes_delta
   FAILED (other, to explain) tests/test_agents.py::TestDeployerRevisionMode::test_revision_seed_keeps_ai_features_whole
   FAILED (other, to explain) tests/test_agents.py::TestDeployerRevisionMode::test_revision_seed_without_prior_plan_skipped_predecessor
   FAILED (other, to explain) tests/test_agents.py::TestPhaserRevisionMode::test_revision_seed_used_when_prior_round_and_delta_exist
   FAILED (other, to explain) tests/test_agents.py::TestStackAdvisorRevisionMode::test_revision_seed_used_when_prior_stack_and_delta_exist
   FAILED (other, to explain) tests/test_designer.py::TestCarryForwardCallback::test_seeds_prior_mock_and_note_into_refine
   other failures: 11
   summary: 16 failed, 4195 passed, 1 skipped in 95.52s (0:01:35)
```

**As predicted: all five fail, one per former copy.** Each reaches the one body through its own module's binding: the `agentifier` re-export, `agents.designer`'s re-export, and `stack_advisor`, `phaser` and `deployer` as package or module attributes.

**The 11 others are the same harm, reached through the real callers.** Under §60.6's amended failure condition they are evidence, not a defect. Every one is a revision-mode path that reads the delta:
- the Agentifier's fresh-start revision detection, its zero-new-candidates round, and Try Again's revision round (`test_revision.py` ×3, `test_try_again.py` ×2);
- the Deployer's, Phaser's and StackAdvisor's revision seeds (`test_agents.py` ×5);
- the Designer's carry-forward callback (`test_designer.py` ×1).

So every caller of the five former copies, the module's own tests and the real flows alike, now runs the one body. The commit was made before the mutation ran, because the harness refuses a dirty tree. This section was then amended in, under the standing rule for unpushed commits.

| Gate | Result |
|---|---|
| Ruff / format / mypy | `All checks passed!` twice · `222 files already formatted` · `Success: no issues found in 93 source files`: one more file, the new module |
| Tests | `4211 passed, 1 skipped` (exit 0) |
| Coverage | `TOTAL 12439 876 93%`. Statements fall by 20, since four of the five copies are gone, and misses stay at 876. The rows that moved: `agentifier/_render.py` 253 → 247 statements, misses 11 → 11; `agents/_revision.py` new, 10 statements, 0 missed; `agents/deployer.py` 213 → 207 statements, misses 3 → 3; `agents/designer.py` 273 → 267 statements, misses 33 → 33; `agents/phaser/_revision.py` 35 → 29 statements, misses 0 → 0; `agents/stack_advisor/_stack_shape.py` 87 → 81 statements, misses 2 → 2 |
| Floor / off-limits | **456 / 456** (`FAILURES: 0`); no test file touched |

## 8. 8e: the five annotated targets no test reached (P22)

Inventory §77.9's gap, closed. The coverage percentage hid it, because a percentage names
no function. There is one test class per function, each driving the function's
annotated inputs with its props' own values, and each pairing a positive case with a
negative one. Nothing under `src/` changes.

### 8.1 What landed

| Function | Targets | Tests | File |
|---|---|---|---|
| `callbacks/_setup.py:on_provider_hint` | `provider_label` | `TestProviderHintCallback`: Bedrock gets the shared credential hint; no provider yet gets the empty slot | `tests/test_setup_search_provider.py`, which holds no floor entry |
| `callbacks/designer/_wizard.py:on_designer_generate_mock` | `n`, `annotations`, `image_support` | `TestGenerateMockCallback`: each annotation lands on its screenshot, and the flag and planning context reach `_start_gen`; no click starts nothing | `tests/test_designer.py`, a new class |
| `agents/designer.py:_designer_tool_call_followup` | `search_config` | `TestToolCallFollowup`: a web search is answered with the configured search; another tool gets the turn but no search | `tests/test_designer.py`, a new class |

- **Floor.** `test_designer.py` holds floor entries, three tier-B classes and three tier-A
  nodes. The two new classes are appended after every one of them, with their imports
  inside the tests, so the one hunk is outside every entry: allowed and reported (§51.6).
- **Footprint:** 2 files, 123 insertions, plus this section. One assertion was corrected before the commit: an empty `html.Div()` serialises as `{"children": None}`, not as no props.

### 8.2 The proofs

**The width sweep reaches every target:** `targets 63; reached 63; never reached 0; rejected by a real value 0 []`. 7o5 left 5 never reached (§1.1). Each newly reached target saw a value of its annotated type, and `None` or the other bool too, and every value was accepted:

```
agents/designer.py:545:search_config        SearchConfig | None     SearchConfig x1, None x1
callbacks/_setup.py:39:provider_label        str | None              str x1, None x1
callbacks/designer/_wizard.py:237:n          int | None              int x1, None x1
callbacks/designer/_wizard.py:238:annotations list[str | None]       list x2
callbacks/designer/_wizard.py:241:image_support bool | None          bool x2
```

Each value's caller is one of the new tests, as the sweep's caller record shows (§4.4).

**Check 4 on the two new patch targets** (`patch_resolve.py`, with the map `[["web_search", "web_search"], ["_start_gen", "_start_gen"]]`; the other ten `_start_gen` targets it lists are existing ones, and all pass):

```
PASS tests/test_designer.py:2434 [setattr] spec4.callbacks.designer._wizard._start_gen
     (1) function _start_gen  (2) src/spec4/callbacks/designer/_wizard.py re-exports it from spec4.callbacks.designer._mock_gen; calls it at on_designer_step2_choice@123, on_designer_generate_mock@268
     other callers: {'src/spec4/callbacks/designer/_refine.py': ['on_designer_regenerate@168', 'on_designer_revise_stale@244', '_rerun_failed_draw@324']}
FAIL tests/test_designer.py:2495 [path] spec4.agents.designer.web_search
     (1) NOT the function: function  (2) src/spec4/agents/designer.py re-exports it from spec4.websearch; calls it at _designer_tool_call_followup@559
FAIL tests/test_designer.py:2509 [path] spec4.agents.designer.web_search
     (1) NOT the function: function  (2) src/spec4/agents/designer.py re-exports it from spec4.websearch; calls it at _designer_tool_call_followup@559
targets ending in a batch name (new side): 12; FAIL: 2; fourth-form candidates: 0
```

- **The `_start_gen` setattr passes.**
- **The two `web_search` strings fail condition (1) by construction, not by landing in the wrong place.** `agents/designer.py` binds `from spec4.websearch import search as web_search`, so the patched object is the function `search`, whose `__name__` is not the target's name. The tool's condition (1) was written for a rename, where the two names agree.
- **Condition (2) holds.** The module the string names is the one that calls it, at `_designer_tool_call_followup@559`.
- **The patch lands where the caller looks.** The positive test asserts `ws.assert_called_once_with("pricing pages", cfg)` and the `RESULTS` tool message, and neither could hold if the real `search` ran. The `8e_followup` mutation fails exactly that test.
- **For ruling, since a check-4 failure is a stop for its string (inventory §60.3):** accept the alias as explained, or teach check 4 to read an import alias (P26's tools question).

**One mutation per function:**

```
restore: 1 file(s) byte-identical by sha256; tree clean
M 8e_generate (on_designer_generate_mock drops the annotations (8e, P22)): predicted 1, failed 1; must-pass 0, failed 0; as predicted
   FAILED (predicted)       tests/test_designer.py::TestGenerateMockCallback::test_each_annotation_lands_on_its_screenshot
   other failures: 0
   summary: 1 failed, 4216 passed, 1 skipped in 95.46s (0:01:35)
restore: 1 file(s) byte-identical by sha256; tree clean
M 8e_hint (on_provider_hint ignores the chosen provider (8e, P22)): predicted 1, failed 1; must-pass 0, failed 0; as predicted
   FAILED (predicted)       tests/test_setup_search_provider.py::TestProviderHintCallback::test_bedrock_gets_the_shared_credential_hint
   other failures: 0
   summary: 1 failed, 4216 passed, 1 skipped in 94.69s (0:01:34)
restore: 1 file(s) byte-identical by sha256; tree clean
M 8e_followup (the designer's tool follow-up searches without the configured search (8e, P22)): predicted 1, failed 1; must-pass 0, failed 0; as predicted
   FAILED (predicted)       tests/test_designer.py::TestToolCallFollowup::test_a_web_search_is_answered_with_the_configured_search
   other failures: 0
   summary: 1 failed, 4216 passed, 1 skipped in 96.21s (0:01:36)
```

**As predicted: each mutation fails its function's positive test, and nothing else fails.** Each function is now pinned by a test that bites, where before no test named any of the three. The commit was made before the mutations ran, because the harness refuses a dirty tree. This section was then amended in, under the standing rule for unpushed commits.

| Gate | Result |
|---|---|
| Ruff / format / mypy | `All checks passed!` twice · `222 files already formatted`; `ruff format` reflowed two long lines in the new blocks before the commit · mypy unchanged: no `src/` file changed |
| Tests | `4217 passed, 1 skipped` (exit 0): six more, the new tests |
| Coverage | `TOTAL 12439 852 93%`: **misses fall from 876 to 852.** The three functions' bodies are now run as well as reached. The rows that moved: `agents/designer.py` 33 → 24 missed (88% → 91%); `callbacks/_setup.py` 16 → 15 missed (82% → 83%); `callbacks/designer/_wizard.py` 63 → 50 missed (50% → 60%); `providers.py` 15 → 14 missed (84% → 85%) |
| Floor / off-limits | **456 / 456** (`FAILURES: 0`). `test_setup_search_provider.py`'s hunk (`@@ -206,0 +207,24 @@`) follows `TestSkip`, and the file holds no entry. `test_designer.py`'s (`@@ -2413,0 +2414,99 @@`) follows its last class, after all 15 of its entries |

## 9. 8e2: mtimes set with `os.utime`, not raced with a sleep (P32)

Inventory §62.8's fix, which the fold did not carry. §2.1(h) brought it into the
mechanical half. Five fixtures slept before an mtime comparison. On this WSL2 host a file
can be written with an mtime seconds ahead of the clock (§66.8), so no sleep length made
the order certain. Each fixture now sets every file's mtime explicitly, so the order is a
fact of the fixture. Nothing under `src/` changes.

### 9.1 What landed

| File | Fixture | The order set |
|---|---|---|
| `tests/test_agent_pill_click.py` | `_stale_mock_project` | vision 1000; mock, manifest and stack 2000; AI features 3000 |
| `tests/test_stale_ai_features.py` | `_make_project` | stack, phase 1 and plan 1000; AI features 2000 |
| `tests/test_stale_ai_features.py` | `_designer_project` | vision and AI features 1000; mock 2000; the `newer` input, when given, 3000 |
| `tests/test_agent_rows.py` | `two_state_project` | code review and feature specs 1000; AI features 2000; vision 3000 |
| `tests/test_deployer_invariants.py` | `TestStalenessRegistry::test_editing_feature_specs_marks_the_plan_stale` | phases and feature specs 1000; the plan 2000; the edited feature specs 3000 |

- **Each file's `import time` becomes `import os`.** Nothing else in the four files used
  `time`.
- **The re-writes that existed only to bump an mtime are gone,** with the sleeps before
  them: `two_state_project`'s second `vision.json` write, and the plan-then-edit spacing in
  the Deployer test. The content each wrote was identical to what was already on disk.
- **Floor.** The four helpers sit outside every entry, but floor nodes call them:
  - `_stale_mock_project` feeds tier-A
    `tests/test_agent_pill_click.py::TestNoEnabledButtonIsRefused::test_every_enabled_button_navigates`;
  - `_designer_project` feeds tier-A
    `tests/test_stale_ai_features.py::test_stale_mock_allows_stack_advisor`;
  - `two_state_project` feeds tier-B `tests/test_agent_rows.py::TestAMissingUsageEntry`
    and `::TestItLeadsTheProjectView`.

  Their hunks are allowed and reported (§51.6). `test_deployer_invariants.py` holds no
  entry.
- **Footprint:** 4 files, 40 insertions and 14 deletions, plus this section. The four files' own tests pass: `110 passed`.

### 9.2 One mutation per fixture: the order flipped

```
restore: 1 file(s) byte-identical by sha256; tree clean
M 8e2_pill_click (_stale_mock_project: the AI features set older than the mock (8e2, P32)): predicted 2, failed 2; must-pass 0, failed 0; as predicted
   FAILED (predicted)       tests/test_agent_pill_click.py::TestStackAdvisorReachable::test_button_and_click_agree
   FAILED (predicted)       tests/test_agent_pill_click.py::TestBlockedClickSurfacesError::test_phaser_stale_mock_sets_error
   other failures: 0
   summary: 2 failed, 4215 passed, 1 skipped in 93.05s (0:01:33)
restore: 1 file(s) byte-identical by sha256; tree clean
M 8e2_make_project (_make_project: the AI features set older than downstream (8e2, P32)): predicted 1, failed 1; must-pass 0, failed 0; as predicted
   FAILED (predicted)       tests/test_stale_ai_features.py::test_ai_features_change_flags_all_downstream
   other failures: 0
   summary: 1 failed, 4216 passed, 1 skipped in 91.84s (0:01:31)
restore: 1 file(s) byte-identical by sha256; tree clean
M 8e2_designer_project (_designer_project: the 'newer' input set older than the mock (8e2, P32)): predicted 3, failed 3; must-pass 0, failed 0; as predicted
   FAILED (predicted)       tests/test_stale_ai_features.py::test_designer_flags_ai_features_change
   FAILED (predicted)       tests/test_stale_ai_features.py::test_designer_flags_vision_change
   FAILED (predicted)       tests/test_stale_ai_features.py::test_stale_mock_blocks_phaser
   other failures: 0
   summary: 3 failed, 4214 passed, 1 skipped in 91.28s (0:01:31)
restore: 1 file(s) byte-identical by sha256; tree clean
M 8e2_two_state_project (two_state_project: the vision set back before the Agentifier's output (8e2, P32)): predicted 0, failed 0; must-pass 0, failed 0; A WRONG PREDICTION
   FAILED (other, to explain) tests/test_agent_rows.py::TestContinueForAnInProgressAgent::test_no_other_state_is_touched_by_a_transcript[agentifier-needs_update]
   other failures: 1
   summary: 1 failed, 4216 passed, 1 skipped in 91.96s (0:01:31)
restore: 1 file(s) byte-identical by sha256; tree clean
M 8e2_deployer (the deployer staleness test: the edited feature specs set older than the plan (8e2, P32)): predicted 1, failed 1; must-pass 0, failed 0; as predicted
   FAILED (predicted)       tests/test_deployer_invariants.py::TestStalenessRegistry::test_editing_feature_specs_marks_the_plan_stale
   other failures: 0
   summary: 1 failed, 4216 passed, 1 skipped in 93.86s (0:01:33)
```

**Each flip fails the tests that read its order, and nothing else.** So in every fixture the order now carries an assertion as a fact of the fixture, where before it rested on a sleep.

**One prediction was wrong, and it is recorded as made.** For `two_state_project` I predicted that no test would fail. The read behind that prediction found only `test_the_fixture_exercises_more_than_one_state`, which asserts more than one state and survives a flip. It missed a parametrized case: `TestContinueForAnInProgressAgent::test_no_other_state_is_touched_by_a_transcript[agentifier-needs_update]` pins Agentifier's `needs_update` state directly, and it fails under the flip. So the fixture is pinned. The harness's "A WRONG PREDICTION" is right twice over: a case that predicts no failures can never read "as predicted" (§3.3), and this prediction was also wrong.

**The first chain was killed for low memory,** by the session's harness during the gate suite. The commit and the floor check had finished; no mutation had started, the tree was clean, and no process survived. The gate and the five mutations were then re-run from the committed tree, and those are the results above. The commit was made before the mutations ran, because the harness refuses a dirty tree. This section was then amended in, under the standing rule for unpushed commits.

| Gate | Result |
|---|---|
| Ruff / format / mypy | `All checks passed!` · `222 files already formatted` · mypy unchanged: no `src/` file changed |
| Tests | `4217 passed, 1 skipped` (exit 0) |
| Coverage | `TOTAL 12439 852 93%`; every per-module row identical to 8e's |
| Floor / off-limits | **456 / 456** (`FAILURES: 0`). Every hunk sits in an import line, a module-level helper, or the Deployer test, and none is inside a floor entry. The floor nodes that call the helpers are listed in §9.1 |

## 10. 8f: the racing nine wait for their worker (P19), and the rulings from review of 8a–8e2

### 10.1 The rulings from review of 8a–8e2

8a–8e2 were approved. The rulings below bind the rest of Phase 8.

**(a) Misses: 852 is the new working ceiling.** 8e's reason is recorded in §8's gate
table: the three functions' bodies are now run as well as reached. The rule stays "misses
≤ the ceiling", from 8f on at 852.

**(b) 8e2's wrong prediction is the right kind.** A fixture turned out to be pinned, and
that is the finding.

**(c) The racing nine: §1.4's option (a), with a bounded join.**
- **The join is bounded:** join the worker with a long timeout, 60 s, then `assert not
  worker.is_alive()` before any terminal-state assertion. A join that times out then fails
  the assertion, loudly and with the thread named, rather than letting the test pass or
  hanging the suite.
- **Condition 1:** the thread discovery asserts exactly one new daemon thread, so a second
  spawn is a failure, not a wrong join.
- **Condition 2:** the terminal assertions after the join are `done`, the text, the error
  flag, and `claim_finalise` returning True and then False.
- **Option (b), a production seam** (an Event in the stream entry, or `streaming.wait()`),
  may be the right long-term answer. It is a `src/` change for a test's convenience, so it
  goes to the decisions half as an option beside D13, not into 8f.

**(d) Check 4 and the alias: accepted as explained.**
- **Why:** the two `web_search` strings land where the designer calls the function. The
  test's own assertions would fail on a real search, and the follow-up mutation fails
  exactly that test. That is the proof check 4 exists to stand in for, supplied directly.
- **Recorded in check 4's definition,** in this commit: the alias case is written into
  `scripts/cleanup/README.md` as a known limit, with the mutation as the substitute proof.
- **"Check 4 learns `import … as`"** goes with D13, so the tools decision sizes it.
- **The stop-for-that-string rule** (inventory §60.3) is satisfied by the ruling, not
  bypassed.

**(e) Modes.**
- 8g and 8h run in default mode.
- At 8i1 the session switches to plan mode, with `ultrathink`, high effort and auto on:
  7q's reasoning. The plan and the trace harness are the review, and the plan is read
  before any edit lands.

**The decisions half gains two entries:** option (b), the streaming seam, beside D13;
and "check 4 learns `import … as`", with D13.

### 10.2 Why "exactly one new daemon thread" needed a hold

The ruling's discovery lists the threads alive after the click, and asserts exactly one
new daemon thread. But nothing stops the worker from finishing first: a thread that has
exited is not listed, so the discovery would find none. That is a spurious failure, and it
turns on timing.

**Measured before any edit,** with a scratch probe that imported the test module's own
helpers. Without a hold, over 200 clicks under `_mocked_draw()`, the worker had already
exited when the threads were listed in **6 of 200**. The ruled check would have failed on
timing about 3% of the time.

**So the worker is held at the start of its generator until it has been identified.**
- **How:** the hold wraps `get_agent_gen` in `callbacks/_chat.py`. The real function
  builds the real generator, and the worker runs it; the wrapper only waits on a
  `threading.Event` before its first `next()`.
- **It is not the option not taken:** `streaming.start` still runs the draw in a real
  daemon thread.
- **The test releases the hold** as soon as the discovery has run, or has failed. On the
  failure path it still joins every new thread while the patches are in place, so no
  worker can outlive them.
- **It makes the discovery deterministic.** Across 20 held clicks: 1 new daemon thread
  every time, one final text, one pool (`smart_search`, the mocked Scout's), and one
  returned store key set.
- **It removes 7q0's leak between chained redraws (§1.4).** The callback snapshots the
  session into the returned store after `streaming.start`. With the worker held, the
  snapshot always precedes the worker's first write. So a chained redraw no longer starts
  from a store that may or may not carry the first worker's `_display_override` or
  `_stream_status`.

### 10.3 What landed

| File | Change |
|---|---|
| `tests/agentifier/test_try_again.py` | `_click_and_wait(session, note)`: the hold, the discovery (exactly one new daemon thread), the bounded join, and the terminal assertions. The nine call it: `TestDiskIsUntouched`'s test, `TestCallback`'s two, and `TestGuidedRedraw._run`, which serves six. Three imports (`threading`, `streaming`, `_chat`) |
| `scripts/cleanup/README.md` | check 4's known limit, the import alias, as §10.1(d) ruled |

**The terminal assertions, after `assert not worker.is_alive()`:**
- `done` is True;
- the error flag is False;
- the text opens with the draw's own `### Scout` banner, and carries no `raised:` (the
  signature of a real sub-agent call);
- the pool holds only the mocked Scout's candidate;
- `claim_finalise` returns True, and then False.

This turn streams no model text, so there is no `"Hello!"` to assert: the text the turn
produces is what is pinned.

- **Nothing else in the file started a worker it left running.** The one remaining
  `_mocked_draw()` block drives `agentifier.run` on the main thread. The other
  `on_breadth_try_again` calls are either the no-op and refused cases, which start no
  stream, or tests that patch `streaming.start`.
- **Floor:** the file's two tier-A nodes, both in `TestPanelButton`, are untouched. Every
  hunk sits outside every entry: allowed and reported (§51.6).
- **Determinism before the commit:** `test_try_again.py` ran five times in a row, `44
  passed` each time.
- **Footprint:** 2 files, 69 insertions and 9 deletions, plus this section.

### 10.4 The proofs

**Check 4 on the hold's target**, `patch.object(_chat, "get_agent_gen", …)`:

```
PASS tests/agentifier/test_try_again.py:334 [object] spec4.callbacks._chat.get_agent_gen
     (1) function get_agent_gen  (2) src/spec4/callbacks/_chat.py re-exports it from spec4.session; calls it at on_init_turn@77, on_chat_submit@116, on_fast_forward@161, _start_retry_turn@200, on_breadth_submit@286, on_breadth_try_again@377
targets ending in a batch name (new side): 15; FAIL: 0; fourth-form candidates: 0
```

**The two mutations, as §1.4 designed them:**

```
restore: 1 file(s) byte-identical by sha256; tree clean
M 8f_late (M-late: the worker waits 0.5 s before it starts (8f, P19)): predicted 0, failed 0; must-pass 9, failed 0; A WRONG PREDICTION
   PASSED (must pass)       tests/agentifier/test_try_again.py::TestDiskIsUntouched::test_implemented_round_survives_a_full_try_again
   PASSED (must pass)       tests/agentifier/test_try_again.py::TestCallback::test_starts_a_stream_and_records_the_action
   PASSED (must pass)       tests/agentifier/test_try_again.py::TestCallback::test_prior_transcript_is_preserved
   PASSED (must pass)       tests/agentifier/test_try_again.py::TestGuidedRedraw::test_note_survives_the_reset_with_the_rejected_set
   PASSED (must pass)       tests/agentifier/test_try_again.py::TestGuidedRedraw::test_user_bubble_quotes_the_note
   PASSED (must pass)       tests/agentifier/test_try_again.py::TestGuidedRedraw::test_blank_note_is_the_plain_redraw
   PASSED (must pass)       tests/agentifier/test_try_again.py::TestGuidedRedraw::test_every_click_is_one_history_event
   PASSED (must pass)       tests/agentifier/test_try_again.py::TestGuidedRedraw::test_notes_accumulate_across_retries
   PASSED (must pass)       tests/agentifier/test_try_again.py::TestGuidedRedraw::test_blank_note_keeps_prior_notes_and_refreshes_the_set
   other failures: 0
   summary: 4217 passed, 1 skipped in 111.59s (0:01:51)
restore: 2 file(s) byte-identical by sha256; tree clean
M 8f_escape (M-escape: M-late, and the helper's join removed (8f, P19)): predicted 9, failed 9; must-pass 0, failed 0; as predicted
   FAILED (predicted)       tests/agentifier/test_try_again.py::TestDiskIsUntouched::test_implemented_round_survives_a_full_try_again
   FAILED (predicted)       tests/agentifier/test_try_again.py::TestCallback::test_starts_a_stream_and_records_the_action
   FAILED (predicted)       tests/agentifier/test_try_again.py::TestCallback::test_prior_transcript_is_preserved
   FAILED (predicted)       tests/agentifier/test_try_again.py::TestGuidedRedraw::test_note_survives_the_reset_with_the_rejected_set
   FAILED (predicted)       tests/agentifier/test_try_again.py::TestGuidedRedraw::test_user_bubble_quotes_the_note
   FAILED (predicted)       tests/agentifier/test_try_again.py::TestGuidedRedraw::test_blank_note_is_the_plain_redraw
   FAILED (predicted)       tests/agentifier/test_try_again.py::TestGuidedRedraw::test_every_click_is_one_history_event
   FAILED (predicted)       tests/agentifier/test_try_again.py::TestGuidedRedraw::test_notes_accumulate_across_retries
   FAILED (predicted)       tests/agentifier/test_try_again.py::TestGuidedRedraw::test_blank_note_keeps_prior_notes_and_refreshes_the_set
   other failures: 0
   summary: 9 failed, 4208 passed, 1 skipped in 104.63s (0:01:44)
```

- **M-late: the worker waits half a second before it starts,** and all nine pass with nothing else failing. The join carries them, not the timing. The harness prints "A WRONG PREDICTION" because the case predicts no failure, which it can never call "as predicted" (§3.3). The verdict is in its must-pass lines: 9 of 9 passed.
- **M-escape: the same delay, with the helper's join removed.** Exactly the nine fail, as predicted, and nothing else does. The new assertions bite when the worker runs outside the patches, which is what the old tests could not see.
- **Both restores were verified by sha256, and the tree was clean after each.** The commit was made before the mutations ran, because the harness refuses a dirty tree. This section was then amended in, under the standing rule for unpushed commits.

**The timing evidence: five traced runs of the fixed tree,** with the default family and
§1.1's `--basetemp`, each compared with the first, and §1.1's pre-fix run compared with the
first:

```
-- t8f_1 vs t8f_2
tests traced: base 143, new 143; identical 143; diverging 0 (key order only: 0)
worker-thread invocations: tests 9; differing 0: advisory (timing) 0, escalated (content) 0
-- t8f_1 vs t8f_3
tests traced: base 143, new 143; identical 143; diverging 0 (key order only: 0)
worker-thread invocations: tests 9; differing 0: advisory (timing) 0, escalated (content) 0
-- t8f_1 vs t8f_4
tests traced: base 143, new 143; identical 143; diverging 0 (key order only: 0)
worker-thread invocations: tests 9; differing 0: advisory (timing) 0, escalated (content) 0
-- t8f_1 vs t8f_5
tests traced: base 143, new 143; identical 143; diverging 0 (key order only: 0)
worker-thread invocations: tests 9; differing 0: advisory (timing) 0, escalated (content) 0
-- §1.1's pre-fix run vs t8f_1
tests traced: base 142, new 143; identical 142; diverging 1 (key order only: 0)
worker-thread invocations: tests 9; differing 3: advisory (timing) 2, escalated (content) 1
  ADVISORY  tests/agentifier/test_try_again.py::TestGuidedRedraw::test_blank_note_keeps_prior_notes_and_refreshes_the_set: timing: ordering -- the recorded states, at different points between worker and main; nothing novel
  ADVISORY  tests/agentifier/test_try_again.py::TestGuidedRedraw::test_every_click_is_one_history_event: timing: ordering -- the recorded states, at different points between worker and main; nothing novel
  ESCALATED tests/agentifier/test_try_again.py::TestGuidedRedraw::test_notes_accumulate_across_retries: CONTENT (a state no baseline run recorded): _stream_received_chars = 660
  DIVERGES tests/agentifier/test_prioritizer.py::TestBeginPriorityPhase::test_the_turn_opens_with_the_prioritizer_banner: traced in only one run: new
```

- **The nine are deterministic now.** Across five runs of the fixed tree, every main-thread trace is identical, 143 of 143 each time. The nine's worker traces differ in none of the four comparisons, not even by timing. Before the fix, the same comparisons always showed worker divergences (§79.0, §79.2).
- **No network reach in any of the five runs.** `trace_diff.py`'s known-race rule never fired. The unchanged tree fired it in three of five traced runs at 7q2, and once in §1.1's run. The rule is now dead for the nine; retiring it is a change to the tools, and it goes with D13.
- **Against §1.1's pre-fix run,** every one of the 142 shared main-thread traces is identical. So nothing from 8b to 8f changed what the agentifier family's consumer sees. Three differences remain, each explained:
  - **The one "diverging" test** is 8c's banner test, which exists only in the new run.
  - **Two worker traces are timing,** the pre-fix race's own states in a different order.
  - **One is content:** `_stream_received_chars = 660` in `TestGuidedRedraw::test_notes_accumulate_across_retries`. In §1.1's run, that test's worker reached the real Scout and failed (§1.1), so the pre-fix reference never saw the completed draw's counter. With the fix, the second redraw completes under the mocks every time. This is the fix's state, not a regression.

| Gate | Result |
|---|---|
| Ruff / format / mypy | `All checks passed!` · `238 files already formatted` (`src/`, `tests/` and `scripts/cleanup/`) · mypy unchanged: no `src/` file changed |
| Tests | `4217 passed, 1 skipped` (exit 0); the nine are the same nine, now waiting |
| Coverage | `TOTAL 12439 852 93%`; every per-module row identical to 8e2's, at the new ceiling of 852 |
| Floor / off-limits | **456 / 456** (`FAILURES: 0`); every hunk in `test_try_again.py` sits outside its two tier-A nodes |

## 11. 8g: the 31 contract keys (P21) — the report, then the tests

§2.1(g) approved the tool extension that re-derives the write sets, and ruled that the
tests be written from the re-derived set, not from §79.3's quote. 8g lands in two
commits: 8g1, the report, and 8g2, the tests. This section is appended in two parts,
one per commit.

### 11.1 A correction to §1: the trace already records the entry snapshot

§1.2's P21 row and §1.4's closure paragraph said the committed trace records no session
snapshot at a generator's entry, so the unseen set could not be re-derived with the
twelve tools. **That is wrong.**
- **`trace_identity.py` stores `"start"` on every invocation:** the session as the
  invocation found it (`trace_identity.py:153–156`). Its comment says 7q3 used it to
  measure the keys each generator writes.
- **What misled the pre-work:** the module docstring, which lists the start event as "the
  entry's name and its arguments (session and llm_config excluded)". That is true of the
  arguments, and it says nothing of the snapshot kept beside them.
- **So the approved extension is smaller than §1.4 proposed.** No entry snapshot has to be
  added. The extension is the report alone, and 8g1 corrects the docstring. §1 stays as
  written, and the record stays add-only.

### 11.2 Commit 8g1: `contract_check.py`, the thirteenth tool

**What it reports.** For each of the eight agentifier generators:
- its documented keys, read from the "Its contract on ``session``" paragraph. Named
  collections (`_RESTART_DEFAULTS`, `_RESTART_POP`) are expanded, and named hand-offs
  add their own documented keys;
- the keys observed changing under its own traced entry: every later snapshot of each
  invocation, diffed against its start snapshot, so a key written and then popped
  within a turn still counts;
- any observed key that nothing documents, which exits 1;
- the documented own keys never seen changing: the contract-test list.

The two stand-in keys, `_finalized` and `_priority_begun`, are set aside by name, as 7q3
did.

**Shown to reproduce 7q3's report exactly.** It was run on §1.1's trace of `2214ce9`, and
again on 8f's first traced run. Both print the same report as §79.3, line for line:

```
run_catalog_phase: documented 27 own (+10 via complete_agentifier, finalize_specs); observed 20; UNDOCUMENTED none
    documented, never seen changing: agentifier_breadth_chosen, agentifier_breadth_groups, agentifier_breadth_intro, agentifier_breadth_nonce, agentifier_compositions, agentifier_explicitly_rejected, agentifier_preserved_selected, agentifier_scout_pool, agentifier_spec_index, agentifier_spec_results, ai_catalog
run_spec_phase: documented 8 own (+20 via finalize_specs); observed 8; UNDOCUMENTED none
    documented, never seen changing: none
run_cross_cutting_phase: documented 11 own (+11 via begin_priority_phase); observed 10; UNDOCUMENTED none
    documented, never seen changing: agentifier_cross_cutting_topics
run_priority_phase: documented 3 own (+10 via complete_agentifier); observed 7; UNDOCUMENTED none
    documented, never seen changing: none
handle_reentry: documented 40 own (+3 via run_catalog_phase); observed 27; UNDOCUMENTED none
    documented, never seen changing: agentifier_artifact_msg_count, agentifier_carried_forward, agentifier_cc_ff_locked, agentifier_compositions, agentifier_cross_cutting_ff_review, agentifier_preserved_selected, agentifier_revision, agentifier_revision_cross_cutting, agentifier_revision_delta, agentifier_revision_prior_version, agentifier_revision_version, agentifier_spec_ff_locked, agentifier_spec_ff_review
finalize_specs: documented 14 own (+10 via begin_priority_phase); observed 11; UNDOCUMENTED none
    documented, never seen changing: _stream_received_chars, agentifier_cross_cutting_analysis, agentifier_cross_cutting_decisions, agentifier_cross_cutting_index, agentifier_cross_cutting_topics, agentifier_preserved_features
begin_priority_phase: documented 5 own (+10 via complete_agentifier); observed 9; UNDOCUMENTED none
    documented, never seen changing: none
complete_agentifier: documented 13 own (+0 via no hand-off); observed 13; UNDOCUMENTED none
    documented, never seen changing: none
never seen changing, in all: 31; contracts failing: 0
```

- **The documented counts match:** 27, 8, 11, 3, 40, 14, 5 and 13 own, and the hand-off
  additions.
- **The observed counts match:** 20, 8, 10, 7, 27, 11, 9 and 13.
- **No key is undocumented.**
- **The 31 never seen changing are §79.3's 31,** generator by generator.

**Shown to bite.** The case `8g_tool_bite` drops `finalize_specs`' write of `agentifier_spec_done`. `mutate.py` then runs the traced suite under it, against 8f's five traces as baselines, with their `--basetemp`:

```
restore: 1 file(s) byte-identical by sha256; tree clean
probe 8g_tool_bite (finalize_specs no longer writes agentifier_spec_done: the contract report must list it (8g, the tool's bite)): as predicted
  suite under the probe: 6 failed, 4211 passed, 1 skipped in 95.95s (0:01:35)
  traces diverging: 10; predicted 1, of which diverged 1; predicted but NOT diverging: none
  tests traced: base 143, new 143; identical 133; diverging 10 (key order only: 0); identical to a recorded variant other than the first: 0
```

The report on that run's trace lists the dropped key:

```
finalize_specs: documented 14 own (+10 via begin_priority_phase); observed 10; UNDOCUMENTED none
    documented, never seen changing: _stream_received_chars, agentifier_cross_cutting_analysis, agentifier_cross_cutting_decisions, agentifier_cross_cutting_index, agentifier_cross_cutting_topics, agentifier_preserved_features, agentifier_spec_done
never seen changing, in all: 32; contracts failing: 0
```

- **`finalize_specs` is observed changing 10 keys, not 11,** and `agentifier_spec_done` joins the keys never seen changing. The total goes from 31 to 32.
- **The six tests that failed under the mutation** are ones that assert the key. They are the mutation's harm, not the check's.
- **The restore was verified by sha256,** and the tree was clean after.

**Also carried in this commit:**
- the `start` line of `trace_identity.py`'s docstring now names the snapshot, as §11.1
  found;
- `scripts/cleanup/README.md` gains the thirteenth tool.

| Gate | Result |
|---|---|
| Ruff / format / mypy | `All checks passed!` · `239 files already formatted` (`src/`, `tests/` and `scripts/cleanup/`) · mypy unchanged: no `src/` file changed |
| Tests | `4217 passed, 1 skipped` (exit 0) |
| Coverage | `TOTAL 12439 852 93%`; every per-module row identical to 8f's |
| Floor / off-limits | **456 / 456** (`FAILURES: 0`); no test file touched |

**Footprint:** 3 files, 170 insertions and 2 deletions: the tool, one docstring line in `trace_identity.py`, and the README entry, plus this section.

### 11.3 Commit 8g2: the contract tests, written from the re-derived set

**The set they are written from** is the report on 8f's first traced run (§11.2): the same
31 keys as §79.3, generator by generator. The tests name those keys literally, so a
mutation that removes a key from the collection that writes it cannot also remove it from
what the test expects.

**What landed:** `tests/agentifier/test_generator_contracts.py`, one class per generator,
five tests.

| Class | Path, driven from the generator's own entry | The keys it pins | The key it must not write |
|---|---|---|---|
| `TestHandleReentryContract` | the stale path: the reset, then a stubbed rediscovery | the 13, every `_RESTART_POP` key the traced re-entries never had set | `ai_features`, left for the redraw to replace |
| `TestFinalizeSpecsContract` | a re-selection whose feature warrants topics; the analyst's stream replaced | the 6: the counter, the stored analysis and cursor, and the popped `agentifier_preserved_features` | `agentifier_cross_cutting_done` |
| `TestCrossCuttingPhaseContract` | a reply with no stored analysis: the reload re-run | the 1: `agentifier_cross_cutting_topics` | `agentifier_cross_cutting_done` |
| `TestCatalogPhaseContract` ×2 | a fresh start; then a re-selection that adds nothing and hands off to `finalize_specs` | the 11: the six breadth keys, and the selection's and the reply's five | `ai_catalog` on the fresh start; `agentifier_breadth_intro` on the re-selection |

- **How a write is seen.** `_written` diffs the session at every yield, and at the end,
  against the session the generator was given. So a key written and then popped inside
  the turn counts, as it does in the report.
- **Why the start values differ from the defaults.** Three of the 31 went unseen because
  their writes left the value the session already held: `agentifier_breadth_chosen`,
  `agentifier_cross_cutting_index` and `agentifier_cross_cutting_decisions`. Each test
  starts from the state a real turn inherits: a panel an earlier draw left chosen, or the
  topic cursor and the spec walk a previous round left part-way. So each write shows.
- **The converse is the report's job.** The tests pin that each documented write happens.
  The report pins that nothing undocumented is written, over the whole suite.
- **Floor:** a new file; it holds no entry.
- **Before the commit:** the five passed in a `git archive` export of 8f's tree, with the
  export's own `src/` first on the path.
- **Footprint:** `git show --stat e7ef31e` gives one file, `tests/agentifier/test_generator_contracts.py`, 292
  insertions. Nothing under `src/` changed, and no existing test did.

### 11.4 The proofs

**One mutation per test,** each dropping the one write its test pins:

```
restore: 1 file(s) byte-identical by sha256; tree clean
M 8g_reentry (the restart no longer pops agentifier_revision_delta (8g, handle_reentry)): predicted 1, failed 1; must-pass 0, failed 0; as predicted
   FAILED (predicted)       tests/agentifier/test_generator_contracts.py::TestHandleReentryContract::test_the_stale_path_resets_every_restart_key
   FAILED (other, to explain) tests/agentifier/test_try_again.py::TestResetCompleteness::test_every_session_key_is_accounted_for
   FAILED (other, to explain) tests/agentifier/test_try_again.py::TestResetCompleteness::test_revision_block_is_cleared
   FAILED (other, to explain) tests/agentifier/test_try_again.py::TestRevisionRound::test_revision_block_is_re_derived_from_disk
   other failures: 3
   summary: 4 failed, 4218 passed, 1 skipped in 94.48s (0:01:34)

restore: 1 file(s) byte-identical by sha256; tree clean
M 8g_finalize (the stored analysis no longer resets the topic cursor (8g, finalize_specs)): predicted 1, failed 1; must-pass 0, failed 0; as predicted
   FAILED (predicted)       tests/agentifier/test_generator_contracts.py::TestFinalizeSpecsContract::test_a_warranted_topic_draws_and_stores_the_analysis
   other failures: 0
   summary: 1 failed, 4221 passed, 1 skipped in 93.36s (0:01:33)

restore: 1 file(s) byte-identical by sha256; tree clean
M 8g_crosscut (the reload re-run no longer derives the warranted topics (8g, run_cross_cutting_phase)): predicted 1, failed 1; must-pass 0, failed 0; as predicted
   FAILED (predicted)       tests/agentifier/test_generator_contracts.py::TestCrossCuttingPhaseContract::test_the_reload_rerun_stores_the_warranted_topics
   other failures: 0
   summary: 1 failed, 4221 passed, 1 skipped in 95.88s (0:01:35)

restore: 1 file(s) byte-identical by sha256; tree clean
M 8g_catalog_fresh (the breadth question no longer writes a fresh nonce (8g, run_catalog_phase)): predicted 1, failed 1; must-pass 0, failed 0; as predicted
   FAILED (predicted)       tests/agentifier/test_generator_contracts.py::TestCatalogPhaseContract::test_a_fresh_start_writes_the_breadth_question
   other failures: 0
   summary: 1 failed, 4221 passed, 1 skipped in 92.61s (0:01:32)

restore: 1 file(s) byte-identical by sha256; tree clean
M 8g_catalog_reselect (a re-selection that adds nothing no longer resets the spec index (8g, run_catalog_phase)): predicted 1, failed 1; must-pass 0, failed 0; as predicted
   FAILED (predicted)       tests/agentifier/test_generator_contracts.py::TestCatalogPhaseContract::test_a_reselection_that_adds_nothing_writes_the_catalog
   other failures: 0
   summary: 1 failed, 4221 passed, 1 skipped in 92.00s (0:01:31)
```

- **`8g_reentry`: as predicted, and three older tests fail with it.** They are
  `TestResetCompleteness::test_every_session_key_is_accounted_for`,
  `::test_revision_block_is_cleared` and
  `TestRevisionRound::test_revision_block_is_re_derived_from_disk`, in
  `tests/agentifier/test_try_again.py`. The first reads `_RESTART_POP` itself (`:100`). The
  other two call `reset_agentifier_flow` directly (`:145`, `:812`), the helper
  `handle_reentry`'s stale path shares with Try Again (`agentifier.py:2641–2655`).
  - So the pop was already pinned, but never through `handle_reentry`'s own entry, and the
    report reads that entry. This is 7q3's "reached only through another entry", met in the
    mutation.
  - The new test is the one that fails on `handle_reentry`'s path.
- **`8g_finalize`: as predicted, the new test alone.** Nothing else in the suite noticed the
  topic cursor left where a previous round put it.
- **`8g_crosscut`, `8g_catalog_fresh` and `8g_catalog_reselect`: as predicted, each its
  new test alone.** These are the reload re-run's topics, the breadth question's fresh
  nonce, and the reset of a spec walk an earlier round left part-way.
- **Every restore was byte-identical by sha256, and the tree was clean after each.**

**The closure: the report, on a traced run of 8g2's tree:**

```
run_catalog_phase: documented 27 own (+10 via complete_agentifier, finalize_specs); observed 33; UNDOCUMENTED none
    documented, never seen changing: none
run_spec_phase: documented 8 own (+20 via finalize_specs); observed 8; UNDOCUMENTED none
    documented, never seen changing: none
run_cross_cutting_phase: documented 11 own (+11 via begin_priority_phase); observed 11; UNDOCUMENTED none
    documented, never seen changing: none
run_priority_phase: documented 3 own (+10 via complete_agentifier); observed 7; UNDOCUMENTED none
    documented, never seen changing: none
handle_reentry: documented 40 own (+3 via run_catalog_phase); observed 40; UNDOCUMENTED none
    documented, never seen changing: none
finalize_specs: documented 14 own (+10 via begin_priority_phase); observed 17; UNDOCUMENTED none
    documented, never seen changing: none
begin_priority_phase: documented 5 own (+10 via complete_agentifier); observed 9; UNDOCUMENTED none
    documented, never seen changing: none
complete_agentifier: documented 13 own (+0 via no hand-off); observed 13; UNDOCUMENTED none
    documented, never seen changing: none
never seen changing, in all: 0; contracts failing: 0
```

- **Every documented key is now seen changing under its generator's own entry: 31 → 0.**
  No generator writes a key its contract leaves out, so the converse holds too.
- **Four generators' observed counts moved against the report on 8f's first trace
  (§11.2):** `run_catalog_phase` 20 → 33; `run_cross_cutting_phase` 10 → 11; `handle_reentry` 27 → 40; `finalize_specs` 11 → 17. The others are unchanged: `run_spec_phase`, `run_priority_phase`, `begin_priority_phase`, `complete_agentifier`.
  The counts include hand-off keys, which is why some exceed the documented own count.
- **The traced run passed:** `4222 passed, 1 skipped`, the same as the gate.

| Gate | Result |
|---|---|
| Ruff / format / mypy | `All checks passed!`; `240 files already formatted`; `Success: no issues found in 93 source files` |
| Tests | `4222 passed, 1 skipped`: 8g1's 4,217 + 5, exit 0 |
| Coverage | `TOTAL 12439 834 93%`: misses 852 → 834, all in `agentifier/agentifier.py` |
| Floor / off-limits | `456 (expect 456)`, `0` failures; the one file is new and holds no entry |

## 12. 8h: the prop-bound callback inputs (P14)

Every Dash callback parameter that is bound to a component prop other than a store's
`data`, and annotated bare `Any`, gets the type that prop delivers. It is 7o's shape: a row
map, the strip check, strict mypy and the width sweep. It is two commits, top-level
`callbacks/` and then `callbacks/designer/`, as §1.5 set.

### 12.1 The row map

**How a row is found.** Dash binds a callback's parameters positionally to the `Input` and
`State` dependencies its decorator lists. A scratch script walks every `@callback` in
`src/spec4`, pairs each parameter with its (component id, prop), and finds the
component's class where an `id=` keyword creates that id.
- **87 callbacks; 0 whose dependency count differs from its parameter count.**
- **107 prop-bound `Any` parameters on 78 lines.** Store parameters (`data`) sit on 85
  lines, and they stay `Any`: the session-dict edge (§1.2, P13).
- **§1.2 quoted §60.5's prop rule as 107 on 81 lines.** The parameter count is the same.
  The line count is 78 here, measured on the tree 8h edits.

**The prop gives the type.** The 105 rows applied, as they stand at 8h2:

| Prop | Type | Rows |
|---|---|---:|
| `n_clicks`, `n_submit`, `n_intervals` | `int \| None` | 66 |
| `n_clicks`, on an id pattern-matched with `ALL` | `list[int \| None]` | 6 |
| `value` of `dmc.Select`, `PasswordInput`, `TextInput`, `Textarea` | `str \| None` | 20 |
| `value` of an ALL-matched `dmc.Textarea` | `list[str \| None]` | 3 |
| `value` of `dmc.CheckboxGroup` | `list[str] \| None` | 2 |
| `pathname`; `contents` of the single-file `dcc.Upload` | `str \| None` | 2 |
| `contents`, `filename` of the `dcc.Upload` declared `multiple=True` | `str \| list[str] \| None` | 2 |
| `checked` | `bool \| None` | 1 |
| `id` | `str` | 3 |

- **Seventeen rows were resolved by reading, not by the script.** In 14, the id is a
  computed expression (`GATE_IDS["model"]`, `ids["provider"]`), and the component was
  read at `layouts/_setup.py:152–153`, `:164–165`, `:200–201` and `:211–212`. In 3, an
  `Input` on the `id` prop receives the id itself: `round-tree`, `artifact-view-content`
  and `round-cost`, each a string.
- **The three `annotations` rows are ALL-matched `dmc.Textarea`s**
  (`layouts/designer.py:297`, `:537`), so each receives a list of values.
- **The two `multiple=True` rows were `str | None` in the map as first applied.** The width
  sweep rejected them at 8h2's first commit, and §12.4 records that.
- **The row map is not committed.** It lives in the session scratchpad, as 105 rows in
  `rows_7o.json`'s shape, with the two rows that came out beside them. 7o's map is committed
  as `scripts/cleanup/data/rows_7o.json`, so 7o5's sweep can be re-run from the repo. 8h's
  cannot, until its map is committed beside it. That is a change under `scripts/cleanup/`,
  and it is put to review, not taken.

**Two rows come out, on 7o's rule (inventory §77.2):**

| Row | Why it stays `Any` |
|---|---|
| `callbacks/_setup.py:61`, `on_setup_connect`'s `provider_label` | It goes bare to `providers.provider_key_for_label(label: str)` (`:65`). `str \| None` is not a `str`, so the type the prop gives fails mypy there |
| `callbacks/_gate.py:240`, `on_gate_connect`'s `provider_label` | The same call, bare, at `:252` |

- **Typing them would need `or ""` at the call, a runtime change.** The strip check
  forbids that here. The two other `provider_label` rows, `on_gate_provider_change` and
  `on_setup_search_connect`, already pass `provider_label or ""`, so they are typed.

**The map was wrong in the dry run, and the dry run caught it.** Applied to a `git
archive` export of 8g2's tree, the first map failed strict mypy with 12 errors:
- **10 were the six `ALL`-matched `n_clicks` rows, typed `int | None`.** An id naming `ALL`
  is a Python name, so the script's literal evaluation left the id as source text and
  missed the pattern. The script now finds the pattern in that text, and the six rows are
  `list[int | None]`.
- **2 were the two `provider_label` rows above.**

The second map, 105 rows, is the one applied. On two exports of 8g2's tree, one with
8h1's 76 rows and one with all 105, each after `ruff format`:
- strict mypy: `Success: no issues found in 93 source files`, both;
- the strip check against 8g2: `files changed: 6; files with residue: 0`, then
  `files changed: 9; files with residue: 0`;
- `ruff check`: `All checks passed!`, both. Before formatting, the widened signatures gave
  17 E501s, all in files the format then rewrote.

### 12.2 Commit 8h1: top-level `callbacks/`

**`3d046e9`: 76 rows in six files.** `__init__.py` 11, `_artifacts.py` 13, `_chat.py` 12,
`_gate.py` 14, `_nav.py` 11 and `_setup.py` 15.
- **How it was applied.** A scratch script replaced exactly `name: Any` with `name: <type>`
  on each row's line, requiring one match per row. `ruff format` then ran on the six files,
  and reformatted five.
- **The six files are byte-identical to the dry run's export** (`cmp`, file by file).
- **Footprint:** `6 files changed, 82 insertions(+), 57 deletions(-)`, all under
  `src/spec4/callbacks/`. No test and no floor file changed.

### 12.3 Commit 8h2: `callbacks/designer/`

**`ba46e15`: 29 rows in three files.** `designer/__init__.py` 1, `_refine.py` 13 and
`_wizard.py` 15.
- **Applied as 8h1 was, then formatted.** At the first commit, `7dfb44f`, the three files
  were byte-identical to the dry run's full export. So were 8h1's six, so the two commits
  together are the export.
- **Amended once,** before its proof passed: `on_designer_refine_upload`'s `contents` and
  `filename` were widened to `str | list[str] | None` (§12.4). Nothing else changed.
- **Footprint, amended:** `3 files changed, 42 insertions(+), 21 deletions(-)`, all under
  `src/spec4/callbacks/designer/`. No test and no floor file changed.

### 12.4 The proofs

**The strip check, per commit, against the commit before:**

```
8h1, 3d046e9 against 676246d: files changed: 6; files with residue: 0
8h2, ba46e15 against 3d046e9: files changed: 3; files with residue: 0
```

**The width sweep met a limit, at 8h1's first run.** One of the 105 rows is a closure:
`on_open_artifact` (`callbacks/_artifacts.py:516` at `676246d`). `_register_open_artifact(key)`
defines it and registers it once per artifact key.
- **The committed sweep resolves a target by attribute from its module,** and a nested def
  is not a module attribute. The run stopped with an internal error at that row:
  `AttributeError: 'function' object has no attribute 'on_open_artifact'`. It had
  registered 23 targets and reached none.
- **An AST scan found no other such row.** Of the 105, it is the only one whose enclosing
  chain at `676246d` is longer than its own name.
- **Recorded as the sweep's known limit, beside check 4's alias case (§10.1).** "The sweep
  learns nested defs" goes with D13, since changing the committed tool is D13's question.
- **So 8h1's proof is taken in two parts:**
  - the committed sweep, on the 75 module-level rows;
  - a scratch copy on the one closure row. It differs from the committed tool only in
    this: when a qualified name does not resolve, it takes the nested def's code object
    from the enclosing function's `co_consts`. Every registration shares that code object.
- **Two attempts were killed by the environment for "low memory".** A sampler, reading
  every 10 seconds through the second attempt, never saw less than 14.2 GB available. The
  second kill landed after the committed sweep had finished and written its output. The
  closure run was then taken in the foreground, and so was everything after. The sweep
  writes nothing in the repo, and the tree was clean each time.

**The width sweep on the new row map.** `WIDTH_SWEEP_BASE` is `676246d`, the tree the
rows' lines were read on. Each run passed `4222 passed, 1 skipped`, and each peaked at
284–292 MB:

```
8h1, the committed tool, 75 rows, at 3d046e9:
width_sweep: targets 75; reached 49; never reached 26; rejected by a real value 0 []; by stand-ins only 0; checker errors 0 []
8h1, the scratch copy, the closure row, at 3d046e9:
width_sweep: targets 1; reached 1; never reached 0; rejected by a real value 0 []; by stand-ins only 0; checker errors 0 []
8h2, the committed tool, 29 rows, at ba46e15:
width_sweep: targets 29; reached 16; never reached 13; rejected by a real value 0 []; by stand-ins only 0; checker errors 0 []
```

- **On the final trees: 105 targets, 66 reached, 39 never reached, 0 rejected.**
- **Every value came from a test calling the callback directly,** 669 in all (549, 19 and
  101). Dash's dispatch does not run in-process. There were 0 stand-ins.
- **Each arriving type is a member of its annotation:**
  - `int` and `None` at `int | None`;
  - `str` and `None` at `str | None`;
  - `str` at `str`;
  - `list` at the list types;
  - `bool` at `bool | None`;
  - both `str` and `list` at the two `str | list[str] | None` rows.
- **The 39 never reached rest on the prop's contract alone,** as every row's type was drawn
  from it. The sweep shows only that no test passes a value outside a reached row's type.
  - 8h1's 26 are in 23 functions: the six `dl_*` downloads; eight navigation hand-offs;
    the folder browser's `on_dir_up`, `on_dir_path_enter`, `on_subdir_click` and
    `on_create_folder`; `on_breadth_change` and `on_breadth_submit`; `on_gate_back`;
    `on_setup_back_model` and `on_setup_clear`. The eight hand-offs are
    `on_brainstormer_to_agentifier`, `on_brainstormer_to_designer`,
    `on_agentifier_to_designer`, `on_review_to_brainstormer`, `on_stack_to_phaser`,
    `on_phaser_to_deployer`, `on_deployer_new_project` and `on_rescan_project`.
  - 8h2's 13 are in 11 functions: `on_designer_add_gui`, `on_designer_approve`,
    `on_designer_continue_stack`, `on_designer_preferences_next`, `on_designer_refine`,
    `on_designer_refine_cancel`, `on_designer_revise_stale`,
    `on_designer_screenshot_delete`, `on_designer_screenshot_upload`,
    `on_designer_skip_1` and `on_designer_skip_2`.
  - Tests for them are not P14's work, and none were written.

**The sweep rejected two of 8h2's rows on real values, and the rows were wrong.** At the
first 8h2 commit, `7dfb44f`, the sweep over the 29 designer rows gave:

```
width_sweep: targets 29; reached 16; never reached 13; rejected by a real value 2 ['callbacks/designer/_refine.py:64:contents', 'callbacks/designer/_refine.py:64:filename']; by stand-ins only 0; checker errors 0 []
```

- **Both rejections are in `on_designer_refine_upload`** (`callbacks/designer/_refine.py:64`
  at `676246d`): `contents` and `filename`, typed `str | None`.
  `TestRefineImageAnnotations::test_multiple_files_selected_at_once_are_all_appended`
  passes lists: `['data:image/png;base64,a', 'data:image/png;base64,b']` and
  `['a.png', 'b.png']`. `::test_upload_syncs_existing_annotation_and_appends_new_image`
  passes a `str`.
- **The row map's prop rule was wrong for this component.** It gave `contents` and
  `filename` the single-file type and never read `dcc.Upload`'s `multiple`. The refine
  upload is declared `multiple=True` (`layouts/designer.py:579–582`), so Dash delivers a
  list. The body already takes both shapes: `contents if isinstance(contents, list) else
  [contents]`, and the same for `filename`.
- **So the width the tests exercise is `str | list[str] | None`.** Both rows were widened
  to it, the annotation only. The screenshot upload is `multiple=False`
  (`layouts/designer.py:330–333`), so its `contents: str | None` stands. No test reaches it.
- **The fix was amended into 8h2,** since it was unpushed and its proof had not yet passed:
  whole or carry. It passed strict mypy, and the strip check against 8h1 gave
  `files changed: 3; files with residue: 0`. The gate and the sweep were then re-run on
  the amended commit, `ba46e15`, as above.
- **This is the sweep doing its job.** Strict mypy passed the narrow rows, both in the dry
  run and at the first commit. mypy checks the body against the annotation, not the values
  Dash sends in, so only the sweep could catch it.

**5p's grep moved, and §1.2 said it would not: 230 → 234 → 236.** That was a wrong
prediction about a line count. The annotations fell as predicted:
- **`Any`-annotated parameters, by AST, fell by exactly the rows.** In 8h1's six files, 148
  → 72, which is −76. In 8h2's three, 75 → 46, which is −29.
- **The grep counts lines, and `ruff format` split four signatures one parameter per
  line.** The widened annotations pushed each past 88 characters. Store parameters that
  shared a line then each got a line of their own:
  - 8h1, `_setup.py`, 9 → 13: `on_setup_connect` +2, `on_setup_model_continue` +1,
    `on_setup_search_connect` +1;
  - 8h2, `designer/_wizard.py`, 15 → 17: `on_designer_step2_choice` +2.
- **§1.2's reasoning held for every line it looked at.** Each of the 78 lines keeps an `Any`
  for its store. It did not foresee the format pass adding lines.
- **So 5p's grep is a count of lines, not of annotations.** When a format pass splits a
  signature, the grep rises even though annotations fall. §12's AST count is the figure
  that measures the work.

| Gate | 8h1, `3d046e9` | 8h2, `ba46e15` |
|---|---|---|
| Ruff / format / mypy | `All checks passed!` (`src/ tests/` and `.`); `240 files already formatted`; `Success: no issues found in 93 source files` | the same, at `7dfb44f` and again with the fix before the amend |
| Tests | `4222 passed, 1 skipped`, exit 0: unchanged, as annotations should leave it | `4222 passed, 1 skipped`, exit 0, at `7dfb44f` and at `ba46e15` |
| Coverage | `TOTAL 12439 834 93%`: unchanged | `TOTAL 12439 834 93%`: unchanged, at both |
| Floor / off-limits | `456 (expect 456)`, `FAILURES: 0`; no file under `tests/` touched | the same, at both |

## 13. 8i0: the three turns' baselines and probes (P5–P7), record only

Before any turn is split, each module's `run` gets three traced baselines, which must be
identical to one another, and one probe, shown to bite. This is 7q0's shape (inventory
§79.0), with `TRACE_MODULE` naming the module and `TRACE_FAMILY=run`. Nothing under
`src/`, `tests/` or `scripts/cleanup/` changed; this section is the commit.

### 13.1 The baselines, three per module, at `08e83a2`

Each run:

```sh
TRACE_OUT=<scratch>/tr8i/<m>_<i>.json TRACE_MODULE=spec4.agents.<module> TRACE_FAMILY=run \
    PYTHONHASHSEED=0 PYTHONPATH=scripts/cleanup \
    uv run pytest -p trace_identity -q -p no:cacheprovider --basetemp=<scratch>/tr8i/tmp_<m>
```

| Module | Each run's meta | Run 1 vs 2, 1 vs 3 (`trace_diff.py`) | Suite |
|---|---|---|---|
| `spec4.agents.brainstormer` | 47 tests, 47 invocations, 968 events, 807 distinct snapshots; entries `run` 47 | identical 47 of 47; diverging 0; worker-thread invocations 0 | `4222 passed, 1 skipped`, each |
| `spec4.agents.code_scanner` | 42 tests, 43 invocations, 241 events, 206 distinct snapshots; entries `run` 43 | identical 42 of 42; diverging 0; worker-thread invocations 0 | the same |
| `spec4.agents.deployer` | 32 tests, 32 invocations, 821 events, 838 distinct snapshots; entries `run` 32 | identical 32 of 32; diverging 0; worker-thread invocations 0 | the same |

- **The test and invocation counts equal §1.1's** at the fold: 47 / 47, 42 / 43, 32 / 32.
  Every invocation is on the main thread, so trace identity's verdict covers every one.
- **The baselines are the scratch files `tr8i/<m>_{1,2,3}.json`.** Each `--basetemp` is
  fixed per module, and each probe below reused its module's.

### 13.2 The probes: one character in a string `run` yields

Each probe is 7q0's probe A in shape: one character changed in a string that the turn
yields, so the trace must show it wherever that string reaches the consumer. Each swap is
one character for one, so no length changes. Otherwise a probe could reach the chars
counters and diverge beyond its prediction.

**Written before any probe ran.** The prediction is computed from the first baseline:
every traced test with a yield carrying the string. The cases file is scratch
`cases_8i.json`, sha256 `0f5b51ec0b35e7aad225ad2bfc6492222d825b299288695b6bf9e15ccac3c6c6`, and
each anchor occurs once in its file.

| Probe | The edit | Predicted to diverge |
|---|---|---|
| `8i0_brainstormer` | the fresh-start greeting: `"Hello! I'm the **Brainstormer**…"` → `"Hello. …"` | 6 of 47: `TestBrainstormer::test_opening_asks_for_idea`, `::test_opening_does_not_call_llm`, `TestBrainstormerBranches::test_reentry_drops_orphan_user_and_falls_through`, `TestOrphanTurnRecovery::test_user_submit_after_failure_routes_to_fresh_start`, `TestResumeSummary::test_empty_messages_skips_recap_branch` (all `tests/test_agents.py`), and `tests/test_vision_disk_reconciliation.py::TestRunEntryDecision::test_stale_session_no_disk_is_greenfield` |
| `8i0_code_scanner` | the scan intro line: `` f"**{mode}** `{working_dir}`…\n\n" `` → `` …`.\n\n" `` | 15 of 42: `tests/test_agents.py::TestCodeScanner::test_rescan_enters_update_mode_when_review_exists`, and 14 in `tests/test_code_scanner_progress.py` (`TestCharsTotal` 4, `TestScanIsNarrated` 5, `TestWaitIsNamed` 5) |
| `8i0_deployer` | the saved-plan confirmation: `"Your new deployment plan has been saved. "` → `"… saved! "` | 2 of 32: `tests/test_agents.py::TestDeployerExistingPlanGuard::test_yes_reply_preserves_markdown_for_persist`, `::TestDeployerReadme::test_offer_appended_after_replace_confirmation_accepted` |

**The results:**

```
restore: 1 file(s) byte-identical by sha256; tree clean
probe 8i0_brainstormer (one greeting character: brainstormer.run's fresh-start greeting (8i0 probe)): as predicted
  suite under the probe: 4222 passed, 1 skipped in 97.91s (0:01:37)
  traces diverging: 6; predicted 6, of which diverged 6; predicted but NOT diverging: none
  tests traced: base 47, new 47; identical 41; diverging 6 (key order only: 0); identical to a recorded variant other than the first: 0

restore: 1 file(s) byte-identical by sha256; tree clean
probe 8i0_code_scanner (one intro character: code_scanner.run's scan intro line (8i0 probe)): as predicted
  suite under the probe: 4222 passed, 1 skipped in 98.47s (0:01:38)
  traces diverging: 15; predicted 15, of which diverged 15; predicted but NOT diverging: none
  tests traced: base 42, new 42; identical 27; diverging 15 (key order only: 0); identical to a recorded variant other than the first: 0

restore: 1 file(s) byte-identical by sha256; tree clean
probe 8i0_deployer (one confirmation character: deployer.run's saved-plan confirmation (8i0 probe)): as predicted
  suite under the probe: 4222 passed, 1 skipped in 94.30s (0:01:34)
  traces diverging: 2; predicted 2, of which diverged 2; predicted but NOT diverging: none
  tests traced: base 32, new 32; identical 30; diverging 2 (key order only: 0); identical to a recorded variant other than the first: 0
```

- **Each probe bit exactly as predicted,** and nothing else diverged: 6 of 47, 15 of 42, 2 of 32.
  Every restore was byte-identical by sha256, and the tree was clean after each.
- **The suite passed under all three,** `4222 passed, 1 skipped`: no test pins those characters.
  The trace catches a change the suite does not. That is what a turn's split leans on: a
  step that changes what the consumer receives shows as a divergence, even where no test
  asserts it.
- **The lengths held, so no chars counter moved,** and no test outside the predictions diverged
  through `_stream_received_chars`. That includes code_scanner's `TestCharsTotal`, which
  diverged only because the intro text itself changed.

### 13.3 What 8i1 starts from

Measured at `08e83a2`, with `ruff check --select C901,PLR0912,PLR0915 --ignore-noqa`:

| Turn | Span | Yields | C901 | PLR0912 | PLR0915 | Misses inside it (8h2's gate) |
|---|---|---:|---|---|---|---|
| `brainstormer.run` | `brainstormer.py:667–767`, 101 lines | 6 | 14 > 10 | 16 > 12 | under | `688–689` |
| `code_scanner.run` | `code_scanner/__init__.py:160–334`, 175 lines | 9 | 12 > 10 | 13 > 12 | 59 > 50 | none (the module's three, `103–104` and `110`, are outside it) |
| `deployer.run` | `deployer.py:529–713`, 185 lines | 10 | 21 > 10 | 25 > 12 | 88 > 50 | `567–568` |

- **The spans are §1.2's, except that `deployer.run` moved up 19 lines.** 8d2 lifted
  `revision_delta` out of `deployer.py`, above it. Its body and figures are unchanged.
- **The two turns with misses carry them into the split:** `brainstormer.py:688–689` and
  `deployer.py:567–568`, as §1.5 named. A step whose failure path no test reaches must not
  add a miss: 7q2's lesson.
- **8i1 is next, and the mode changes there,** as ruled at review of 8a–8e2 (§10.1): plan mode,
  `ultrathink`, high effort, auto on. The plan and the trace harness are the review, and no
  edit lands before the plan is read. 8i1's proof is `brainstormer.run`'s three baselines
  above: the split's traced run must be identical to them.

## 14. 8i1: `brainstormer.run` as a driver over four steps (P5)

This ran in plan mode, as ruled at review of 8a–8e2 (§10.1). The plan was read and approved
before any edit, with one amendment: `Literal` goes on the existing runtime `typing` import,
since `brainstormer.py` already imports from `typing` there. 7o's `if TYPE_CHECKING:` form
applies only where a module does not.

### 14.1 The cut

**It is 7q's shape, as `agentifier.py:807–823` states it (inventory §79).**
- A step is a private generator, typed `Generator[str, None, R]`.
- It yields exactly its block's text.
- It returns `None` only when the turn ended inside it.
- The driver returns at once on `None`.
- No sentinel is used. P8 stays not taken: each `None` below has one cause.

**What landed** (`src/spec4/agents/brainstormer.py` only): `1 file changed, 81 insertions(+),
41 deletions(-)`.
- **`run` is the driver.** Its signature, docstring and entry are unchanged: the
  `brainstormer_messages` init, `drop_orphan_or_route_to_fresh_start`, and
  `rehydrate_vision_from_disk`. It then does one dispatch:
  `user_input is not None` → `_brainstormer_take_input`; `msgs` → `_brainstormer_resume`;
  else `_brainstormer_seed`.
  - It returns on `None`. The dispatch order inverts the original's `if user_input is
    None:` nesting, and is equivalent to it: the conditions are exclusive and have no side
    effects.
  - It keeps `search_cfg`, `system` and the `stream_suppressing_json` call in place, with
    their comment. It ends with `yield from _brainstormer_settle(...)`.
- **The four steps, each body moved verbatim:**

| Step | Block | Returns |
|---|---|---|
| `_brainstormer_take_input(user_input, session, msgs)` | the review-request reply; the user message appended | `None` after the review text; `True` after the append |
| `_brainstormer_resume(session, msgs)` | the staleness question, the replay, the resume summary | `None` after the question or the replay; `True` when the summary was injected |
| `_brainstormer_seed(session, msgs)` | `_brainstormer_seed_context`, and the four-arm seed chain with the fresh-start greeting | `None` after the greeting; `True` after a seed |
| `_brainstormer_settle(session, msgs, system, search_cfg, llm_config)` | the extract, the re-ask, the abandon, the commit | `None`: a terminal step |

- **`run`'s `# noqa: C901, PLR0912  # six-yield generator…` is deleted.** §27.4's seventh
  entry, `agents/brainstormer.py` `run`, is retired by this commit.
- **A two-line comment above the steps** points at agentifier's convention.

**A step with no product returns `Literal[True] | None`** (ruled at plan review). This is
now the convention for such steps.
- Every agentifier step that goes on returns a product. The three opening steps here have
  none: the driver needs only "go on to the draw".
- `Literal[True]` is single-valued. So `None` keeps its one meaning, and no `False` can
  become a third.
- 8i2 and 8i3 follow it, where a step has no product.

### 14.2 The proofs

**Strict mypy, ruff and format.** `Success: no issues found in 93 source files`; `All
checks passed!` on `src/ tests/` and on `.`; `240 files already formatted`.
- **`ruff format` rewrapped one assignment in `_brainstormer_seed`** (lines 758–759) after
  the traced run and the gate had run. The format pass left the AST identical (`ast.dump`,
  before and after). No line moved, so every line number and figure below holds for the
  committed text.

**Complexity.** With `--ignore-noqa`, `brainstormer.py` flags nothing. The exact figures,
with the thresholds lowered so that every function reports:

```
  run                        C901  5  branches  5  statements 17
  _brainstormer_take_input   C901  3  branches  2  statements  7
  _brainstormer_resume       C901  3  branches  2  statements  6
  _brainstormer_seed         C901  4  branches  4  statements 10
  _brainstormer_settle       C901  4  branches  3  statements 11
```

Before, at `d23cf37`, `run` measured C901 14 and 16 branches, with statements under 50.

**Frozen strings (Rule 4):** predicted identical, with 0 count changes.

```
src/spec4/agents/brainstormer.py: string constants 186 -> 186; distinct 87 -> 87
  gone: 0; added: 0; count changes: 0
strings-exit=0
```

**Trace identity, against 8i0's three baselines,** with the steps named in `TRACE_STEPS`:

```
base: {"tests_traced": 47, "invocations": 47, "events": 968, "distinct_snapshots": 807, "exitstatus": 0, "entries": {"run": 47}}
new:  {"tests_traced": 47, "invocations": 47, "events": 968, "distinct_snapshots": 807, "exitstatus": 0, "entries": {"run": 47}}
tests traced: base 47, new 47; identical 47; diverging 0 (key order only: 0); identical to a recorded variant other than the first: 0
worker-thread invocations: tests 0; differing 0: advisory (timing) 0, escalated (content) 0
```

- **Every step is entered under a traced `run` by at least one test,** coverage's second
  condition. The committed `trace_diff.py` does not print step reach, so the counts come
  from the trace file's `steps`:
  - `_brainstormer_take_input` 30: the 28 that reach the append, and the 2 review replies;
  - `_brainstormer_seed` 14;
  - `_brainstormer_settle` 37;
  - `_brainstormer_resume` 3.

**Coverage, both conditions.** `brainstormer.py` stays at `327 9 97%`, with 9 misses before
and after. The staleness exit's two misses moved with their block: `688–689` became
`743–744`, inside `_brainstormer_resume`. Every `return True` is reached. The total is
`TOTAL 12452 834 93%`: statements rise by 13 for the new definitions and returns, and misses
are unchanged.

**One mutation, under §60.6's rule: the forbidden `None`.** `_brainstormer_take_input`
reports its continue as "the turn ended": `return True` became `return None`, after the
append.
- **It ran as a `diverge` case, against the three baselines.**
- **The prediction was written before it ran.** It is every traced test whose effective path
  reaches the append.
- **The prediction came from a scratch script,** which replays the driver's real entry
  decision on each baseline start snapshot. It uses `drop_orphan_or_route_to_fresh_start`
  and `_is_review_request`, because two tests pass an input that the routing turns into a
  fresh start.
- **The result: 28 of 47,** as the plan estimated. The prediction file `diverge_8i1.json`
  has sha256 `b92872d1f96fc0ff50fed651ff73b74e26224d0116c11d0f44e2962b967e7dff`, and the case file `cases_8i1.json` has sha256 `1591c08c20241111d6af337c130b9599200d90f765d3e1fa314d72eaa238df58`.

```
restore: 1 file(s) byte-identical by sha256; tree clean
probe 8i1_take_input (_brainstormer_take_input reports its continue as the turn ended (8i1, the forbidden None)): as predicted
  suite under the probe: 24 failed, 4198 passed, 1 skipped in 96.20s (0:01:36)
  traces diverging: 28; predicted 28, of which diverged 28; predicted but NOT diverging: none
  tests traced: base 47, new 47; identical 19; diverging 28 (key order only: 0); identical to a recorded variant other than the first: 0
```

- **As predicted: 28 of 28 diverged, and no other trace diverged.** The restore was
  byte-identical, and the tree was clean after.
- **The suite failed 24 tests under it.** A `diverge` case prints only the count. So the same
  edit was run once more as a case with `fail: []`, which prints every failure as "other, to
  explain" and reads "A WRONG PREDICTION" by construction (as at §11.2). It gave
  `summary: 24 failed, 4198 passed, 1 skipped in 95.24s (0:01:35)`.
  - All 24 are among the 28 that diverged, and none is outside them.
- **Four diverged and passed. Each asserts only a state or an absence, which a turn that ends
  before the draw also leaves:**
  - `TestBrainstormer::test_non_vision_response_stays_in_progress`: the state is in
    progress, and there is no vision;
  - `TestBrainstormer::test_initialises_brainstormer_messages_if_missing`: the key exists;
    the driver writes it before the dispatch;
  - `TestBrainstormerUnparseableArtifact::test_failed_reask_leaves_no_dead_end_user_turn`:
    no user message says the vision "could not be read";
  - `TestBrainstormerUnparseableArtifact::test_state_is_not_advanced_when_both_attempts_fail`:
    the state is not complete, and there is no vision.

  Their positives, in the same classes, failed: `test_user_input_streams_llm_output`,
  `test_truncated_block_is_re_asked` and `test_turn_never_ends_silently`. As with 8i0's
  probes (§13.2), the trace pins what these four do not. They are not 8i1's to change;
  they are recorded here as found.

| Gate | Result |
|---|---|
| Ruff / format / mypy | as above |
| Tests | `4222 passed, 1 skipped`, exit 0 |
| Coverage | `TOTAL 12452 834 93%`: misses unchanged, statements +13 |
| Floor / off-limits | `456 (expect 456)`, `FAILURES: 0`; no test file touched |

### 14.3 A correction to §13.3

§13.3 gives `deployer.py:567–568` as the misses inside `deployer.run`, "as §1.5 named".
§1.5 named them `586–587`, at the fold. They are the same two lines, moved up 19 lines by
8d2, which lifted `revision_delta` out of the module above them. The figure was right, and
the attribution misquoted §1.5's numbers.

### 14.4 Stop

8i1 stops here for review. 8i2, `code_scanner.run`, returns to plan mode with its own plan.

## 15. Rulings from review of 8g–8i1, and 8h's row map committed

The review read the progress through 8i0 and the 8i1 plan, and approved the work. Its
rulings arrived after 8i1's commit, `cb3e059`, had landed with §14 amended in, so they are
recorded here rather than there.

This commit is record-only:
- this file;
- `BACKLOG.md`;
- `scripts/cleanup/README.md`;
- `scripts/cleanup/data/rows_8h.json`.

Nothing under `src/` or `tests/` changed.

### 15.1 The rulings

**1. The measure of `Any`, from here: the AST count of `Any`-annotated parameters.** 5p's
grep stays only as the continuity column against 5p.
- **§1.2's "no change" was right about the annotations and wrong about the ruler.**
  `ruff format` moved the grep 230 → 236 while the annotations fell by exactly the 105
  rows (§12.4).
- **The count is taken over every `.py` under `src/spec4`,** read at each commit with
  `git show`. It counts every parameter, including `*args`, `**kwargs` and lambda
  parameters, whose annotation is the bare name `Any`. `dict[str, Any]` and the like are
  not counted.

| Commit | `Any`-annotated parameters (AST) | 5p's grep (continuity) |
|---|---:|---:|
| `676246d`, before 8h | 355 | 230 |
| `3d046e9`, 8h1 | 279 (−76) | 234 |
| `08e83a2`, 8h2 | 250 (−29) | 236 |
| `cb3e059`, 8i1 | 250 | 236 |

- **The review's "148 → 72 → 46" chains two file sets.** 148 → 72 is 8h1's six files and
  75 → 46 is 8h2's three (§12.4). The table above is the one series across the tree.

**2. 8h's row map is committed, as `scripts/cleanup/data/rows_8h.json`.** This is the
record-only commit §12.1 asked for.
- **It holds 107 rows, with line numbers at `676246d`:**
  - the 105 applied, "genuinely typeable";
  - the two `provider_label` rows, as "load-bearing" with a null `ptype` and their reason.
    That is `rows_7o.json`'s vocabulary for a row that stays `Any`.
- **Two rows carry `ptype_first`:** the refine upload's `contents` and `filename`, whose
  first type the sweep rejected (§12.4).
- **The closure row, `on_open_artifact`, is marked `closure`,** and the command in the
  README stops on it until D13 lifts the sweep's limit. The README records that limit
  under the sweep, as it records check 4's alias case.
- **Verified before the commit:** three collect-only sweeps (`--co`), each registering its targets and running no test:

```
committed tool, the map less its closure row:  width_sweep: 104 targets on 77 code objects
scratch copy, the map whole:                   width_sweep: 105 targets on 78 code objects
committed tool, the map whole:                 INTERNALERROR> AttributeError: 'function' object has no attribute 'on_open_artifact'
```

  The third is the known limit, stopping where the README says it does.

**3. The unreached targets go on BACKLOG 2.1,** the UI-callback known-limit entry, with
their counts.
- **They are 8e's kind of finding:** parameters no test exercises, so the width rule holds
  for them only vacuously.
- **The ruling named 8h1's 26.** 8h2's 13 are the same finding, and they were placed by the
  same rule.
- **The rule's condition is met for all 39.** `data/families_phase4.json` maps the
  entry's two families:
  - `callbacks/__init__.py` became `__init__`, `_artifacts`, `_chat`, `_gate`, `_nav`,
    `_setup` and `_shared`. That is 8h1's six modules, plus `_shared`, which holds no
    callback. The 26 split `__init__` 6, `_artifacts` 6, `_chat` 3, `_gate` 1, `_nav` 8
    and `_setup` 2.
  - `callbacks/designer.py` became `callbacks/designer/`, which holds the 13: `_wizard` 10
    and `_refine` 3.
- **None lies outside the entry's families, so none is a Phase 8 test row.**

**4. The tool limits go with D13.**
- The width sweep cannot resolve a target defined inside a function (§12.4).
- Check 4 cannot see `import … as` (§10.1).
- **Raised at §14.2, and not ruled:** the committed `trace_diff.py` does not print step
  reach. §14's counts came from the trace file.

**5. The upload rejection is the width rule doing its job** (the review's words).
`multiple=True` was a real narrowing, caught before it shipped (§12.4).

**6. For the remaining turns, 8i2 and 8i3, the mutations run before the commit,** once the
suite is already green. A commit is amended only for its record.
- **Why:** mutations after the commit have produced a rewrite every time. It is correct
  while nothing is pushed, but the amend count is rising: 8g1, 8g2, 8h2 twice, and 8i1.
- **How it is carried out, with the harness as committed.** `mutate.py` refuses a dirty
  tree: a case's edits must be the only change. So a mutation cannot run while the turn's
  edit sits uncommitted in the tree. Before each commit:
  1. the gate, trace identity, frozen strings and complexity run on the edited tree;
  2. the turn's edit is copied to the scratchpad, with its sha256 taken;
  3. each mutation case carries the whole turn. Its anchor is the HEAD text, and its
     replacement is the turn's text with the one line mutated;
  4. the tree is returned to HEAD for the harness, and the case runs and restores it;
  5. the turn's edit is copied back and checked byte-identical by sha256;
  6. one commit then carries the code and the record together.
- **No tool changes. The harness's clean-tree rule stands.** This sequence is recorded as
  the reading of ruling 6, and is open to review.

### 15.2 Next

8i2, `code_scanner.run`, in plan mode with its own plan. `Literal[True] | None` is the
convention for a step with no product (§14.1), and ruling 6 sets the order of its proofs.

## 16. 8i2: `code_scanner.run` as a driver over two steps (P6), and the rulings from review of 8i1

This ran in plan mode, as ruled for 8i2 at review of 8i1. The plan was read and approved
before any edit, with one amendment: the recap fall-through, reached in 0 of 43 invocations,
is recorded as a path no test reaches (§16.2). It also joins BACKLOG 1.3's test row (§16.4).

This is one commit, code and record together, with no amend. That is §15's ruling 6.

### 16.1 The rulings from review of 8i1

1. **8i1 is approved as `cb3e059`.**
2. **The four tests that diverge under 8i1's mutation yet pass** (§14.2) are the finding
   7q0 and 8i0 made: the trace pins what the assertions don't.
   - **They go on the report's list** of invariants the suite assumed rather than pinned,
     beside the racing nine's origin. That is `CLEANUP_REPORT.md` §2.4a, numbered so that
     §2.5–§2.8, which the record cites, keep their numbers.
   - **They are a Phase 8 test row if 8i2 or 8i3 adds to the count.**
3. **§15's mutation sequence is accepted for 8i2 and 8i3,** with its checks:
   - the edit's sha256, taken before it leaves the tree and after it returns;
   - the tree, verified clean at HEAD before the first case runs.

   It is the harness's own restore discipline applied one level up, and it gives one commit
   per turn instead of an amend.
4. **"Mutate on top of a working-tree edit" goes to D13** with the other tool changes. Three
   tool limits have now landed there:
   - the sweep cannot resolve a closure;
   - check 4 cannot see `import … as`;
   - the harness cannot mutate on top of a working-tree edit.

   The decision is one about the tools' maturity, not three fixes.
5. **The report's figure is the bare-`Any` series across `src/spec4`: 355 → 279 → 250.**
   §12's per-file chains stay as the per-commit proof.
6. **BACKLOG 2.1's family split is right, and the limit's shape gets one sentence there.**
   The review worded it as every one lying inside Phase 4's split of
   `callbacks/__init__.py`. That holds for the 26. The 13 lie in Phase 4's split of
   `callbacks/designer.py` (`data/families_phase4.json`), so the sentence names both
   splits.
7. **At plan review of 8i2:** the recap fall-through is recorded as a path no test reaches,
   and it joins BACKLOG 1.3's test row beside any diverge-but-pass tests the mutation names.

### 16.2 The cut

**The entry decision, replayed on each baseline start snapshot,** splits the 43 invocations:

| Path | Invocations |
|---|---:|
| first entry, narrated scan | 15 |
| first entry, no working dir | 4 |
| first entry, existing review shown | 2 |
| re-entry, review re-displayed | 2 |
| re-entry, replay | 1 |
| re-entry, recap that falls through to the draw | **0** |
| input appended | 19 |

**The recap fall-through is a path no test reaches.** It is a re-entry with history, where
`maybe_inject_resume_summary` injects the recap request and the turn goes on to the draw.
- **At HEAD the path has no statement of its own,** so line coverage cannot see the gap.
- **As a step, its `return True` would be a new line no test reaches,** and misses would rise
  by one. That is 7q2's departure (§79.2), where misses rose 876 → 877 and the block was
  folded back into its caller.
- **Here the re-entry arm stays inline in the driver from the start,** verbatim, one level
  out.

**What landed** (`src/spec4/agents/code_scanner/__init__.py` only): `1 file changed, 122 insertions(+), 85 deletions(-)`.

- **`run` is the driver.**
  - Its signature, docstring and entry are unchanged: the init, the orphan routing,
    `pre_stream_chars = 0` with the D-SC-P1 comment, and the hoisted `search_cfg` /
    `system` with the D-SC-P2 comment.
  - It then dispatches. `user_input is not None` appends the message; `msgs` runs the
    re-entry arm, inline; anything else goes to `_scanner_first_entry`, which returns
    `None` or the new running total.
  - The stream call stays in place. It ends with `yield from _scanner_settle(...)`.
  - The dispatch order is inverted, as at 8i1, and is equivalent: the conditions are
    exclusive and have no side effects.
- **The steps:**

| Step | Block | Returns |
|---|---|---|
| `_scanner_first_entry(session, msgs, system, llm_config, pre_stream_chars)` | the existing review shown; the no-working-dir exit; the narrated scan | `None` after either exit; else the new running total, per D-AT3's convention |
| `_scanner_settle(session, system, search_cfg, llm_config, pre_stream_chars)` | the extract, the D-SC-P3 block, the schema-retry re-ask, the D-SC18a commit | `None`: a terminal step |

- **`_scanner_settle` reads `msgs = session["code_scanner_messages"]` itself.**
  - *Why:* the tail needs six values, and PLR0913's limit is five.
  - *Precedent:* 7q1's steps read `agentifier_messages` themselves (§79.1).
  - *Safe:* the list is never rebound. `:171` is the only assignment in `src/`, and
    `_turn_flow` assigns none.
- **How it was applied: verbatim by construction.** A scratch script sliced the original
  lines, guarded by assertions on the text at `def9464`. It moved the re-entry arm out one
  level and the first-entry block out two. It changed only the first-entry block's two
  terminal `return`s, to `return None`. `ruff format` then rewrapped the driver's settle
  call.
- **`run`'s `# noqa: C901, PLR0912, PLR0915` is deleted.** §27.4's eighth entry,
  `agents/code_scanner/__init__.py` `run`, is retired by this commit.
- **No `Literal` import is needed:** each step either has a product or is terminal.

### 16.3 The proofs

**Strict mypy, ruff and format.** `Success: no issues found in 93 source files`; `All
checks passed!` on `src/ tests/` and on `.`; `240 files already formatted`.

**Complexity.** With `--ignore-noqa`, `code_scanner/__init__.py` flags nothing,
PLR0913 included. The exact figures, with the thresholds lowered so that every function
reports:

```
  run                     C901  7  branches  7  statements 24
  _scanner_first_entry    C901  3  branches  2  statements 27
  _scanner_settle         C901  5  branches  4  statements 14
```

Before, at `def9464`, `run` measured C901 12, 13 branches and 59 statements.

**Frozen strings (Rule 4):** predicted identical, with exactly one count change.

```
src/spec4/agents/code_scanner/__init__.py: string constants 78 -> 79; distinct 51 -> 51
  gone: 0; added: 0; count changes: 1
  COUNT 3 -> 4  'code_scanner_messages'
strings-exit=0
```

The one change is `_scanner_settle`'s own read of the message list, the precedent 7q1 set.

**Trace identity, against 8i0's three baselines,** with `TRACE_STEPS=_scanner_first_entry,_scanner_settle`:

```
base: {"tests_traced": 42, "invocations": 43, "events": 241, "distinct_snapshots": 206, "exitstatus": 0, "entries": {"run": 43}}
new:  {"tests_traced": 42, "invocations": 43, "events": 241, "distinct_snapshots": 206, "exitstatus": 0, "entries": {"run": 43}}
tests traced: base 42, new 42; identical 42; diverging 0 (key order only: 0); identical to a recorded variant other than the first: 0
worker-thread invocations: tests 0; differing 0: advisory (timing) 0, escalated (content) 0
```

- **Both steps are entered under a traced `run`,** coverage's second condition. The counts
  come from the trace file's `steps`, and they match the classification in §16.2:
  - `_scanner_first_entry` by 21 tests: 15 narrated, 4 with no working dir, and 2 showing
    the existing review;
  - `_scanner_settle` by 34: the 15 narrated scans and the 19 input turns. No recap
    reaches it.

**Coverage, both conditions.** `code_scanner/__init__.py` is `134 3 98%   103-104, 110`:
the same three misses, all outside `run`. Statements rose from 125 to 134. The total is
`TOTAL 12461 834 93%`: misses unchanged, statements +9.

**One mutation, before the commit: the forbidden `None`.** `_scanner_first_entry` returns
`None` in place of its running total, so the turn ends after the done line.
- **The prediction was fixed before the run:** the 15 narrated-scan tests, from the
  classification. It is the same set as §13.2's probe. The file `diverge_8i2.json` has
  sha256 `f611e369ac5914a6e2da8da436cc0170ff1deadf99bd4ca45f320e45c37c125e`.

**§15's sequence, as it ran.** Three files were modified: the code, `BACKLOG.md` and
`CLEANUP_REPORT.md`. All three left the tree together.

```
15709ec317c8e101c5e776df56af86b84609a98cc6dc22fa32d82405bf1cc19d  src/spec4/agents/code_scanner/__init__.py
f57688e139218bcbfe0f543c9ee4f41a7d07e7dcc02b12a79edd0ba735d4e1bb  BACKLOG.md
74f2de24c23db8bbb54eafc866dcd69cf276b0f5769453fd679f2919a3c86105  CLEANUP_REPORT.md
cases_8i2.json sha256 24b291214172016a463116f677a4595fb811762729e0a458262435bd02990008
cases_8i2_names.json sha256 541b847db9bef1137f0c04de35fdb8d5de93bda1f8d5aadb36cfbce9911f34fa
anchor: HEAD lines 160-285 (126 lines), once; replacement 163 lines; predicted diverging 15
tree verified clean at HEAD (def9464)
```

- **Each case carries the whole turn.** Its anchor is HEAD's text of the changed region,
  and its replacement is the turn's text with `return pre_stream_chars` made
  `return None`. The anchor ends at line 285, not 334, because `run`'s tail moved into
  `_scanner_settle` byte-identical and was absorbed as common suffix.
- **The tree was clean after each case,** and then:

```
restored: all three sha256 identical to before
```

**The `diverge` case:**

```
restore: 1 file(s) byte-identical by sha256; tree clean
probe 8i2_first_entry (_scanner_first_entry returns None in place of its running total (8i2, the forbidden None; the case carries the whole turn)): as predicted
  suite under the probe: 9 failed, 4213 passed, 1 skipped in 95.08s (0:01:35)
  traces diverging: 15; predicted 15, of which diverged 15; predicted but NOT diverging: none
  tests traced: base 42, new 42; identical 27; diverging 15 (key order only: 0); identical to a recorded variant other than the first: 0
```

- **As predicted: 15 of 15 diverged, and no other trace diverged.**
- **The same edit, run as a `fail: []` case to name the failures** (as at §14.2), gave
  `summary: 9 failed, 4213 passed, 1 skipped in 97.38s (0:01:37)`.
  - All 9 are among the 15. They are `TestCharsTotal` ×3, `TestWaitIsNamed` ×5 and
    `TestScanIsNarrated::test_narration_closes_before_the_llm_text`, all in
    `tests/test_code_scanner_progress.py`.
- **Six diverged and passed.** Each asserts only what the turn does before the mutated
  return:
  - `tests/test_agents.py::TestCodeScanner::test_rescan_enters_update_mode_when_review_exists`
    asserts the seed.
  - `TestScanIsNarrated::test_first_chunk_arrives_before_the_walk`,
    `::test_narration_names_the_directory`, `::test_narration_reports_the_file_count` and
    `::test_rescan_says_rescanning` assert the narration. Each asserts no more than its
    name claims.
  - `TestCharsTotal::test_total_is_monotonic_across_the_handover` passes vacuously. Its
    claim is the counter across the stream's opening, and under the mutation the stream
    never opens.
- **8i2 adds to ruling 1's count,** so the finding becomes a Phase 8 test row (§16.4). It
  joins the report's §2.4a beside 8i1's four.

| Gate | Result |
|---|---|
| Ruff / format / mypy | as above |
| Tests | `4222 passed, 1 skipped`, exit 0 |
| Coverage | `TOTAL 12461 834 93%`: misses unchanged, statements +9 |
| Floor / off-limits | `456 (expect 456)`, `FAILURES: 0`; no test file touched |

### 16.4 BACKLOG 1.3's test row

BACKLOG 1.3 gains one row, beside the racing nine and the Prioritizer banner:
- **Tests that assert less than their path: 10.** 8i1's four in `brainstormer`, and
  8i2's six in `code_scanner` (§14.2, §16.3).
- **A path no test reaches: 1.** `code_scanner.run`'s recap fall-through, 0 of 43
  traced invocations (§16.2).
- **8i3 extends the row.**

`CLEANUP_REPORT.md` gains §2.4a, "Tests that assert less than their path", naming the ten.
- **Where it sits:** beside §2.4, the racing nine, and numbered so that §2.5–§2.8 keep
  their numbers.
- **The two counts that name the report's four invariants now note it:** §2's intro, and
  the line in the close-out summary's "Left" list.
- **§2.4a and the row were written after the mutation sequence, from its result.** The
  sha256 lines in §16.3 are `BACKLOG.md` and `CLEANUP_REPORT.md` as they stood before
  those two edits.

BACKLOG 2.1 gains the sentence on the limit's shape (§16.1, ruling 6).

### 16.5 Stop

8i2 stops here for review. 8i3, `deployer.run`, is the last turn. It returns to plan mode
with its own plan and runs the same sequence.

## 17. 8i3: `deployer.run` as a driver over four steps (P7), and the rulings from review of 8i2

This ran in plan mode, as ruled for 8i3 at review of 8i2. The plan was read and approved
before any edit, without amendment.

It is one commit, code and record together, with no amend (§15, ruling 6).

### 17.1 The rulings from review of 8i2

1. **8i2 is approved as `d711942`.** The mutation-before-commit sequence worked as ruled. One
   commit per turn is what the last three should have looked like.
2. **BACKLOG 1.3's row holds only the tests that assert less than they claim.**
   - **A test row is work,** and the work is fixing tests that claim more than they assert.
     `test_total_is_monotonic_across_the_handover` is one. It names a property across the
     handover, and it passes when the handover never happens.
   - **8i2's other five assert what their names say.** They happen to sit on a path that
     goes further. That is a fact about coverage-by-path, not a defect in the test, and
     there is nothing to fix.
   - **`CLEANUP_REPORT.md` §2.4a keeps naming all of them, with the distinction stated.** The
     finding is every diverge-but-pass test. The work is the subset.
3. **The same test, applied to 8i1's four before the row is final.** "Asserting only a state
   or an absence" describes what a test does, not whether its name promises more. As
   classified at plan review of 8i3:
   - **`TestBrainstormer::test_non_vision_response_stays_in_progress` survives.** Its name
     presumes a non-vision response. Under the mutation there is no response at all, and it
     never asserts one arrived. That is the monotonic test's shape.
   - **`TestBrainstormer::test_initialises_brainstormer_messages_if_missing` does not.** The
     initialisation it names happens before the mutated return, and it asserts exactly that.
   - **`TestBrainstormerUnparseableArtifact::test_failed_reask_leaves_no_dead_end_user_turn`
     survives, the strongest of them.**
     - Under the mutation the turn ends right after the user's message is appended. That
       leaves exactly the dead-end user turn its name rules out.
     - It passes because it looks only for the "could not be read" re-ask message. Its
       helper `_run` asserts nothing.
   - **`TestBrainstormerUnparseableArtifact::test_state_is_not_advanced_when_both_attempts_fail`
     survives.** Neither attempt happens, and neither is asserted.
4. **The recap fall-through stays on the row regardless.** A path that 0 of 43 invocations
   reach is a gap, not a classification question.

### 17.2 The cut

**Reach.** The entry decision was replayed on each baseline start snapshot, using the
module's own `_yes_no_intent` and word lists. The 32 invocations:

| Path | Invocations |
|---|---:|
| opt-in gate, ambiguous: the re-ask | 1 |
| opt-in gate, a clear answer, then the seed arm | 2 |
| resume arm: the recap, falling through / the replay / the staleness question | 1 / 1 / **0** |
| seed arm: the opt-in question / the seed appended | 1 / 13 (+2 after the gate) |
| input: plan confirmed / plan kept / README declined, each ending the turn | 2 / 1 / 1 |
| input: continues to the draw | 9 |

Every step's continue path is reached.
- **The resume arm can be a step here.** Unlike code_scanner's (§16.2), its recap falls
  through in a traced test: `TestResumeSummary::test_deployer_first_reentry_calls_llm_for_recap`.
- **The staleness question is reached by none of the 32,** as at the fold. Its two lines are
  the misses it carries.

**What landed** (`src/spec4/agents/deployer.py` only): `1 file changed, 116 insertions(+), 75
deletions(-)`.
- **`run` is the driver.** Unchanged: its signature, docstring and entry.
- **The README opt-in gate stays inline, verbatim, as an entry guard.** A clear answer
  rewrites `user_input` to `None` and falls through. A step cannot return that `None`,
  because `None` means "the turn ended".
- **Then one dispatch,** returning on `None`: input → `_deployer_take_input`; history →
  `_deployer_resume`; else `_deployer_seed`. It inverts the original's order, as at 8i1 and
  8i2, and is equivalent to it.
- **Then, in place:** `search_cfg`, `system` and `_received = yield from stream_counting(...)`,
  with its comment. It ends on `yield from _deployer_settle(...)`.
- **The steps:**

| Step | Block | Returns |
|---|---|---|
| `_deployer_take_input(user_input, session, messages)` | the append; the pending-plan answer; the pending-README answer | `None` after a confirm, a keep or a decline; `True` otherwise |
| `_deployer_resume(session, messages)` | the staleness question; the replay; the recap | `None` after the question or the replay; `True` after the recap |
| `_deployer_seed(session, messages)` | the greenfield opt-in question; the seed appended | `None` after the question; `True` after the seed |
| `_deployer_settle(session, system, search_cfg, llm_config, _received)` | the README and plan staging; the confirm; the completion; the greenfield README beat; the closing offer | `None`: terminal |

- **The three opening steps return `Literal[True] | None`,** §14.1's convention.
- **`Literal` joins the existing runtime import:** `from typing import Any, Literal, cast`.
- **`_deployer_settle` reads `messages = session["deployer_messages"]` itself.**
  - *Why:* the tail needs six values, and PLR0913's limit is five.
  - *Precedent:* 7q1 and 8i2.
  - *Safe:* `:540` is the only assignment in `src/`, and neither `_deployer_readme_accept`
    nor `_deployer_plan_confirm` rebinds the list.
  - Its parameter keeps the name `_received`, so the tail moved byte-for-byte.
- **How it was applied: verbatim by construction, as at 8i2.**
  - A scratch script sliced the original lines, with every boundary asserted against the
    text at `d711942`.
  - It changed exactly the six terminal `return`s to `return None`. Each was asserted by
    line and indentation first.
  - `ruff format` then left the file unchanged.
- **`run`'s `# noqa: C901, PLR0912, PLR0915` is deleted,** and §27.4's sixth entry,
  `agents/deployer.py` `run`, is retired.
  - With 8i1 and 8i2, all three backlog turns are off rule 12.
  - `noqa: C901` lines in `src/` fall from §1.1's 9 to **6**.

### 17.3 The proofs

**Strict mypy, ruff and format.** `Success: no issues found in 93 source files`; `All
checks passed!` on `src/ tests/` and on `.`; `240 files already formatted`.

**Complexity.** With `--ignore-noqa`, `deployer.py` flags nothing, PLR0913 included. The
exact figures, with the thresholds lowered so that every function reports:

```
  run                     C901  8  branches  9  statements 28
  _deployer_take_input    C901  7  branches  6  statements 27
  _deployer_resume        C901  3  branches  2  statements  6
  _deployer_seed          C901  2  branches  1  statements  7
  _deployer_settle        C901  6  branches  7  statements 29
```

Before, at `d711942`, `run` measured C901 21, 25 branches and 88 statements.

**Frozen strings (Rule 4):** predicted identical, with exactly one count change.

```
src/spec4/agents/deployer.py: string constants 200 -> 201; distinct 104 -> 104
  gone: 0; added: 0; count changes: 1
  COUNT 3 -> 4  'deployer_messages'
strings-exit=0
```

**Trace identity, against 8i0's three baselines,** with all four steps in `TRACE_STEPS`:

```
base: {"tests_traced": 32, "invocations": 32, "events": 821, "distinct_snapshots": 838, "exitstatus": 0, "entries": {"run": 32}}
new:  {"tests_traced": 32, "invocations": 32, "events": 821, "distinct_snapshots": 838, "exitstatus": 0, "entries": {"run": 32}}
tests traced: base 32, new 32; identical 32; diverging 0 (key order only: 0); identical to a recorded variant other than the first: 0
worker-thread invocations: tests 0; differing 0: advisory (timing) 0, escalated (content) 0
```

- **Every step is entered, in exactly the predicted counts,** taken from the trace file's
  `steps`:
  - `_deployer_take_input` 13;
  - `_deployer_resume` 2;
  - `_deployer_seed` 16;
  - `_deployer_settle` 25.

  Each of the 32 tests has one invocation, so each count is both tests and invocations.

**Coverage, both conditions.**
- **`deployer.py` is `221 3 99%   379, 658-659`.** At `d711942` it was `207 3 99%   379,
  567-568`.
- **The staleness exit's two misses moved with their block, into `_deployer_resume`.**
- **The total is `TOTAL 12475 834 93%`:** misses unchanged, statements +14.

**One mutation, before the commit: the forbidden `None`.** `_deployer_take_input` reports its
continue as "the turn ended", with `return True` made `return None`.
- **The prediction was fixed before the run:** the 9 input turns that continue to the draw.
  - It came from replaying the entry decision, using the helpers of HEAD's own
    `deployer.py`, so the working-tree edit could not reach it.
  - It is the same nine as the table in §17.2.
  - The file `diverge_8i3.json` has sha256
    `6babad91e177c9aec9e39c6a8245a748c483b0250e3fa904c3fe82b4e52c281e`.

**§15's sequence, as it ran.** Only the code file left the tree. The BACKLOG and report
edits were made after the sequence, from its result.

```
07c2b1042c850882e0460c5e573bc65c2808e9876645709e675b1bef841f3ff8  src/spec4/agents/deployer.py
cases_8i3.json sha256 bde4e5d9c05af0ddfb71fb7c0cfa3f42e2c247f984ad66c42d7e7cd7fe53fda8
cases_8i3_names.json sha256 7085a493d0e068e87b82e6cdfa4effa8894623c824aea2d897d6bb1b50511196
edit 1: the typing import, once; edit 2: anchor HEAD lines 529-656 (128 lines), once; replacement 169 lines; predicted diverging 9
tree verified clean at HEAD (d711942)
```

- **Each case carries the whole turn, as two edits.**
  - The first is the `typing` import line.
  - The second is the changed region of `run`, anchored by its common prefix and suffix
    with HEAD. It ends at line 656, because the tail moved into `_deployer_settle`
    byte-identical.
- **The mutated line is found by its context.** `return True` occurs three times in the new
  text, once per opening step. So the edit keys on `_deployer_take_input`'s own
  "Ambiguous reply" comment line, asserted unique.
- **The tree was clean after each case,** and then:

```
restored: sha256 identical to before
```

**The `diverge` case:**

```
restore: 1 file(s) byte-identical by sha256; tree clean
probe 8i3_take_input (_deployer_take_input reports its continue as the turn ended (8i3, the forbidden None; the case carries the whole turn)): as predicted
  suite under the probe: 8 failed, 4214 passed, 1 skipped in 89.16s (0:01:29)
  traces diverging: 9; predicted 9, of which diverged 9; predicted but NOT diverging: none
  tests traced: base 32, new 32; identical 23; diverging 9 (key order only: 0); identical to a recorded variant other than the first: 0
```

- **As predicted: 9 of 9 diverged, and no other trace diverged.**
- **The same edit, run as a `fail: []` case to name the failures,** gave `summary: 8 failed, 4214 passed, 1 skipped in 87.77s (0:01:27)`.
  All 8 are among the 9.
- **One diverged and passed:** `tests/test_agents.py::TestDeployerReadme::test_accept_uses_existing_readme_as_baseline`.
  - It asserts that the README request, which `_deployer_readme_accept` builds before the
    mutated return, carries the old README and "update it in place". Its name claims
    exactly that.
  - By ruling 2 it is coverage-by-path, not a defect, so it joins the finding and not the
    row.
  - Its sibling `test_accept_generates_and_stages_readme` asserts the staged README, and it
    failed.

| Gate | Result |
|---|---|
| Ruff / format / mypy | as above |
| Tests | `4222 passed, 1 skipped`, exit 0 |
| Coverage | `TOTAL 12475 834 93%`: misses unchanged, statements +14 |
| Floor / off-limits | `456 (expect 456)`, `FAILURES: 0`; no test file touched |

### 17.4 The row, as it stands after the three turns

**The row is final for the half. BACKLOG 1.3's row holds 4 tests and 1 path:**
- **The four tests claim more than they assert.** Each names an event and still passes when
  that event never happens:
  - `tests/test_agents.py::TestBrainstormer::test_non_vision_response_stays_in_progress`;
  - `::TestBrainstormerUnparseableArtifact::test_failed_reask_leaves_no_dead_end_user_turn`;
  - `::TestBrainstormerUnparseableArtifact::test_state_is_not_advanced_when_both_attempts_fail`;
  - `tests/test_code_scanner_progress.py::TestCharsTotal::test_total_is_monotonic_across_the_handover`.
- **The path:** `code_scanner.run`'s recap fall-through, reached by 0 of 43 traced
  invocations (§16.2).

**The finding is eleven tests: 4 + 6 + 1 across the three turns.**
- 8i3 added one to the finding and none to the work.
- `CLEANUP_REPORT.md` §2.4a is rewritten to name all eleven, with the distinction stated.
  The four that are the work each carry their reason. The seven that assert what their
  names say are marked as coverage-by-path.

### 17.5 Stop, and the half's close next

8i3 stops here for review. It is the last mechanical sub-phase. The half then closes as
§1.5 set:

```sh
uv run python scripts/cleanup/remeasure.py 6956aca HEAD \
    --cov-base scripts/cleanup/data/coverage_85a9cb6.txt --run-coverage /outside/dir
```

Every moved cell is explained, and the review stop follows.

## 18. The mechanical half closes

**Ruled at review of 8i3.** 8i3 is approved as `dd9b8ab`, and with it the mechanical half.
- **The three turns are off rule 12 under the same shape.** Each has trace identity against
  its own baseline, and a mutation the suite alone would not have caught.
- **The row is what the classification test made it:** four tests whose names promise more
  than they assert, and one path.
- **The half's close runs as planned (§1.5),** with two additions to its section:
  - the complexity `noqa`s, 9 → 6, each remaining one with its reason and shape;
  - the half's own finding list, gathered from §2–§17 into one place.
- **Then the stop.** The decisions half is laid out whole, with its sizes from §1.2 (§18.4),
  rather than one ruling at a time.

This section is record-only.

### 18.1 The remeasure: `6956aca` against HEAD

**How it ran.** §1.5's command, with HEAD's coverage output reused from a first attempt:

```sh
uv run python scripts/cleanup/remeasure.py 6956aca HEAD \
    --cov-base scripts/cleanup/data/coverage_85a9cb6.txt --cov-head <scratch>/coverage_HEAD.txt
```

- **The first attempt added `--families scripts/cleanup/data/families_phase4.json`,** which
  §1.5's command does not carry.
  - That file maps Phase 0's modules to Phase 4's splits. `6956aca` is already
    post-Phase 4, so the comparison looked up `agents/code_scanner.py`.
  - It stopped with a `KeyError` in the report step, after measuring.
- **That attempt's `--run-coverage` had already run the suite** in a `git archive` export of
  HEAD. It gave `4222 passed, 1 skipped` and `TOTAL 12475 834 93%`, the same as 8i3's gate,
  and that saved output is the `--cov-head` above.
- **The tree was clean throughout.**

| Check | Base | Head |
|---|---|---|
| Tests | 4210 passed, 1 skipped | 4222 passed, 1 skipped |
| Coverage | 12,459 / 876 / 93.0% | 12,475 / 834 / 93.3% |
| `ruff check src/ tests/` | All checks passed! | All checks passed! |
| `ruff format --check src/ tests/` | 221 files already formatted | 223 files already formatted |
| `mypy src/` | Success: no issues found in 92 source files | Success: no issues found in 93 source files |

Same path: 92 modules; 9 rose, 80 unchanged, 3 fell.
- fell: `agentifier/_render.py` 253 / 11 / 95.7% -> 247 / 11 / 95.5%
- fell: `agents/stack_advisor/_stack_shape.py` 87 / 2 / 97.7% -> 81 / 2 / 97.5%
- fell: `feature_specs.py` 344 / 80 / 76.7% -> 341 / 80 / 76.5%
- new at head, outside any family: agents/_revision.py

| Measure | Base | Head |
|---|---|---|
| vulture, no whitelist | 60 (src 37, tests 23) | 58 (src 35, tests 23) |
| vulture, with `vulture_whitelist.py` | 26 (src 3, tests 23) | 26 (src 3, tests 23) |
| ruff F401/F811/F841/ARG, `src/` | 0 | 0 |
| ruff F401/F811/F841/ARG, `tests/` | 178 | 183 |
| Top-level definitions | 1093 | 1100 |
| No reference outside own file | 513 | 521 |
|   of which private | 457 | 466 |
|   of which public | 56 | 55 |
|   public: Dash callbacks | 32 | 31 |
|   public: the review list | 24 | 24 |
| Referenced only from tests/evals/scripts | 135 | 137 |

| deptry | Base | Head |
|---|---|---|
| DEP001 own | 314 | 319 |
| DEP001 evals | 29 | 29 |
| DEP001 other | 1 | 1 |
| DEP002 | 0 | 0 |
| DEP003 | 0 | 0 |
| DEP004 | 3 | 3 |
| Total | 347 | 352 |

| Rule (noqa ignored) | Base | Head |
|---|---|---|
| C901 | 9 | 6 |
| PLR0912 | 6 | 3 |
| PLR0913 | 12 | 12 |
| PLR0915 | 3 | 1 |
| Total | 30 | 22 |

Over C901's threshold at head: 24 stream_turn (llm.py), 17 _validate_frontmatter (agentifier/pattern_loader.py), 13 _artifact_button_state (project_manager.py), 12 _spec_field (agentifier/_render.py), 11 _validate_dependencies (agents/feature_speccer.py), 11 _has_cycle (agentifier/requires_reconciler.py)

|  | Base | Head |
|---|---|---|
| `src/spec4/` | 92 files, 40,284 lines | 93 files, 40,405 lines |
| Files over 1,300 lines | `src/spec4/agentifier/agentifier.py` 2,874, `src/spec4/agents/_feature_context.py` 1,329 | `src/spec4/agentifier/agentifier.py` 2,874, `src/spec4/agents/_feature_context.py` 1,329 |
| Longest functions | `spec4.agents.deployer.run` 185, `spec4.agents.code_scanner.run` 175, `spec4.llm.stream_turn` 174, `spec4.layouts._chat.chat_layout` 163, `spec4.callbacks.designer.on_mock_stream_poll` 150 | `spec4.llm.stream_turn` 174, `spec4.layouts._chat.chat_layout` 163, `spec4.callbacks.designer.on_mock_stream_poll` 150, `spec4.layouts.designer.designer_layout` 148, `spec4.session.default_session` 136 |
| `tests/` | 129 files, 56,534 lines | 130 files, 57,039 lines |
| Largest test file | `tests/test_agents.py` 5,268 lines, 332 functions | `tests/test_agents.py` 5,268 lines, 332 functions |

|  | Base | Head |
|---|---|---|
| Modules | 92 | 93 |
| Cycles | 0 | 0 |
| Layer violations | 0 | 0 |
| Importers of `llm` / `project_manager` | 21 / 23 | 21 / 23 |
| TYPE_CHECKING-only edges | 3 | 3 |
| `global` statements | 0 | 0 |

The report's unchanged lists are left out here:
- the 26 whitelisted vulture lines, identical;
- the 24-name review list, identical;
- the lazy couplings, which are in the saved output.

**Every moved cell, explained.** The per-item lists were re-derived with `remeasure.py`'s own
functions, on `git archive` exports of both trees. That covers the cross-reference rows, the
ARG findings and deptry's DEP001s, since the JSON keeps only their counts.

- **Tests, 4210 → 4222 (+12):** 8c +1 (§5), 8e +6 (§8) and 8g2 +5 (§11).
- **Misses, 876 → 834 (−42):**
  - 8e, −24: `agents/designer.py` −9, `callbacks/designer/_wizard.py` −13,
    `callbacks/_setup.py` −1, and `providers.py` −1. The `providers.py` line is `:180`,
    `provider_key_for_label`'s fallback. 8e's `on_provider_hint` test reaches it through
    `layouts/_setup.py:122`'s `provider_key_hint`.
  - 8g2, −18: `agentifier/agentifier.py` (§11.4).
- **Statements, 12,459 → 12,475 (+16):**
  - 8d2, −20: five `revision_delta` bodies of 6 statements each, −30, in `_render.py`,
    `_stack_shape.py`, `phaser/_revision.py`, `designer.py` and `deployer.py`; and
    `agents/_revision.py` +10.
  - 8d, 0: `pattern_loader.py` +5, `feature_specs.py` −3 and `tier_analyst.py` −2.
  - The three turns, +36: `brainstormer.py` +13, `code_scanner/__init__.py` +9 and
    `deployer.py` +14. `deployer.py` nets +8, with 8d2's −6.
- **Format, 221 → 223 files, and mypy, 92 → 93 source files:** `agents/_revision.py` (8d2),
  and `tests/agentifier/test_generator_contracts.py` (8g2) for the format count.
- **Per module: 9 rose, 3 fell, 80 unchanged, 1 new.**
  - *Rose by fewer misses:* `agentifier.py`, `_setup.py`, `_wizard.py`, `designer.py` and
    `providers.py`.
  - *Rose by more statements with the same misses:* `brainstormer.py`,
    `code_scanner/__init__.py`, `deployer.py` and `pattern_loader.py`.
  - *Fell by fewer statements with the same misses:* `_render.py` and `_stack_shape.py`
    (8d2), and `feature_specs.py` (8d). **No module lost a covered line.** Each percentage
    fell by arithmetic.
  - `tier_analyst.py` (−2, 8d) and `phaser/_revision.py` (−6, 8d2) moved in statements, but
    not at one decimal, so the report counts them unchanged.
  - *New:* `agents/_revision.py`, 10 statements, 0 missed.
  - Among the lowest-covered, `_wizard.py` went 49.6% → 60.0% (8e), and `feature_specs.py`
    76.7% → 76.5% (8d, by arithmetic).
- **Vulture, `src` 37 → 35:** `on_provider_hint` and `on_designer_generate_mock`, which 8e's
  tests now call. The whitelisted run is unchanged.
- **ARG, `tests/` 178 → 183:** five ARG001s, all in `test_designer.py`. They are the unused
  parameters of 8e's fakes: `api_key`, `kwargs`, `model`, `search_cfg` and `wd`.
- **Definitions, 1093 → 1100 (+7):** the five `revision_delta` copies went (8d2). Twelve
  arrived:
  - `agents/_revision.revision_delta`;
  - `pattern_loader.trimmed_description`;
  - the ten steps: `_brainstormer_{take_input,resume,seed,settle}`,
    `_scanner_{first_entry,settle}` and `_deployer_{take_input,resume,seed,settle}`.
- **No reference outside its own file, 513 → 521:**
  - +10 for the steps, each private and called only by its driver;
  - −2 for `designer._designer_tool_call_followup` and `callbacks._setup.on_provider_hint`,
    which 8e's tests now reference. Both moved to "referenced only from
    tests/evals/scripts", 135 → 137.

  So private goes 457 → 466; public 56 → 55; and public callbacks 32 → 31, all three for
  `on_provider_hint`. `on_designer_generate_mock` never counted as unreferenced, so it moves
  no cross-reference cell.
- **deptry, DEP001 own 314 → 319, total 347 → 352:** the five
  `from spec4.agents._revision import revision_delta` lines 8d2 added. There is one each in
  `_render.py`, `deployer.py`, `designer.py`, `phaser/_revision.py` and `_stack_shape.py`.
- **Complexity, 30 → 22:** C901 9 → 6, PLR0912 6 → 3 and PLR0915 3 → 1. All of it is the
  three turns: 8i1 took a C901 and a PLR0912, and 8i2 and 8i3 took one of each of the three
  rules. PLR0913 is unchanged at 12.
- **`src/`, 40,284 → 40,405 lines (+121),** by `git diff --numstat` per file:
  - the turns, 8i1 +40, 8i2 +37 and 8i3 with 8d2 +22;
  - `_revision.py` +32;
  - 8d2's four other modules −16, −17, −16 and −17;
  - 8d: `pattern_loader.py` +14, `tier_analyst.py` −1 and `feature_specs.py` −3;
  - 8h's callback files +46, the signatures `ruff format` split;
  - 8b's annotation-only files, ±0.
- **Longest functions:** `deployer.run` (185) and `code_scanner.run` (175) left the top five.
  `layouts.designer.designer_layout` (148) and `session.default_session` (136) entered it.
- **`tests/`, 129 → 130 files and 56,534 → 57,039 lines (+505):**
  - `test_generator_contracts.py` +292 (8g2);
  - `test_designer.py` +99 and `test_setup_search_provider.py` +24 (8e);
  - `test_try_again.py` +52 (8f);
  - `test_prioritizer.py` +13 (8c);
  - 8e2's four fixture files +26;
  - `test_cost_summary.py` −1 (8b).

  `tests/README.md`'s +148 is not a `.py` file, so it is not in the count.
- **Imports:** 92 → 93 modules, for `_revision.py`. Cycles, layer violations, importers,
  TYPE_CHECKING edges and `global`s are unchanged.

### 18.2 The complexity `noqa`s: 9 → 6

`git grep -c 'noqa: C901' <rev> -- src/`, summed: `2214ce9` 9, HEAD **6**. The three that went are
§27.4's sixth, seventh and eighth entries, the backlog turns (§14, §16, §17).

The six that remain. Figures are with `--ignore-noqa`, and each reason is quoted from its
`noqa`:

| Function | Where | C901 / branches / statements | Shape | The reason its `noqa` carries |
|---|---|---|---|---|
| `stream_turn` | `llm.py:814` | 24 / 26 / 64, and PLR0913 7 | a generator, 174 lines, 4 loops | "entry guards plus the chunk loop, which 27.3 keeps whole as the streaming characterization surface" |
| `_validate_frontmatter` | `agentifier/pattern_loader.py:247` | 17 / 17 / under | a plain function, 77 lines | "flat per-field schema validation; one branch per frontmatter field, each two or three lines appending an error" |
| `_artifact_button_state` | `project_manager.py:449` | 13 / under / under | a plain function, 50 lines | "the branches are the documented artifact button state machine" |
| `_spec_field` | `agentifier/_render.py:146` | 12 / 13 / under | a plain function, 30 lines | "four-way dispatch on JSON value shape; each branch is that shape's rendering" |
| `_validate_dependencies` | `agents/feature_speccer.py:368` | 11 / under / under | a plain function, 40 lines, 5 loops | "single DFS back-edge pruning; the WHITE/GRAY/BLACK colour invariant spans the whole function, so any split leaves a helper callable at only one point in the traversal" |
| `_has_cycle` | `agentifier/requires_reconciler.py:405` | 11 / under / under | a plain function, 43 lines, 3 loops | "single iterative-DFS cycle detection; the colour invariant spans the whole function, so any split leaves a helper callable at only one point in the traversal" |

**None is a shape 7q's driver fits as it stands.** The driver splits a generator turn into
steps at its yield-and-return guards. Five of the six are not generators.
- **Load-bearing by algorithm: `_validate_dependencies` and `_has_cycle`.** Their `noqa`s
  say why: a split breaks the colour invariant.
- **Load-bearing by ruling: `stream_turn`.** It is the only generator. Its entry guards are
  the driver's kind of guard, but inventory §27.3 keeps it whole as the characterization
  surface, and 5o's attempt to extract its chunk loop broke the turn (inventory §48.1).
  - Taking it would be a ruling on §27.3, not a Phase 8 item.
- **Flat dispatch or validation: `_validate_frontmatter`, `_artifact_button_state` and
  `_spec_field`.** Each is one branch per case: a field, a state or a JSON shape.
  - The shape that would fit them is a table, not a driver. A table would rewrite the
    form the logic is written in, where the driver only moves blocks.
  - So it is not a mechanical item. It is listed here only so the decisions half can see
    it, and no ruling is asked for.

### 18.3 The mechanical half's findings, in one place

**1. Tests that assert less than their path** (§14.2, §16.3, §17.3; `CLEANUP_REPORT.md` §2.4a).
Under the three forbidden-`None` mutations, eleven tests diverged and still passed:
4 in `brainstormer`, 6 in `code_scanner` and 1 in `deployer`.
- **The work is the four whose names claim more than they assert** (§17.1). They are
  BACKLOG 1.3's row:
  - `test_agents.py::TestBrainstormer::test_non_vision_response_stays_in_progress`;
  - `::TestBrainstormerUnparseableArtifact::test_failed_reask_leaves_no_dead_end_user_turn`;
  - `::TestBrainstormerUnparseableArtifact::test_state_is_not_advanced_when_both_attempts_fail`;
  - `test_code_scanner_progress.py::TestCharsTotal::test_total_is_monotonic_across_the_handover`.
- **The other seven assert what their names say.** That is coverage-by-path, not a defect.
- **8i0 found the same thing by probe (§13.2).** One character changed in a string each turn
  yields. The suite passed all three probes, and the trace diverged in 6, 15 and 2 tests.

**2. Paths no test reaches:**
- **`code_scanner.run`'s recap fall-through:** 0 of 43 traced invocations (§16.2). It is on
  BACKLOG 1.3's row.
- **The staleness exits of `brainstormer.run` and `deployer.run`:** 0 of 47 and 0 of 32
  (§14.2, §17.2). Their two lines each are the misses the turns carry, now
  `brainstormer.py:743–744` and `deployer.py:658–659`.
- **The `> 2` guard's header-only case (§3.4).** Nothing the app has written reaches it,
  across 24 real phase files. One hand-written list of strings in the tree does, and it
  stays reachable in principle. That is D1's evidence.
- **39 typed callback parameters no test exercises** (§12.4; BACKLOG 2.1). 26 are in the
  `callbacks/__init__` family and 13 in the `callbacks/designer` family, so the width rule
  holds for them only vacuously.
- **Closed:** 8e's five annotated targets, which no test had reached. The sweep now reaches
  63 of 63 (§8.2).

**3. The tool limits, sent to D13** (§16.1, ruling 4):
- the width sweep cannot resolve a target defined inside a function (§12.4). The closure
  `on_open_artifact` was proved with a scratch copy;
- check 4 cannot see `import … as` (§8.2, §10.1). That is the `web_search` alias, accepted
  as explained;
- the harness cannot mutate on top of a working-tree edit (§16.1). 8i2 and 8i3 met it by
  carrying the whole turn in each case;
- **raised, and not ruled:** `trace_diff.py` does not print step reach (§14.2).

**4. The upload rejection (§12.4).** The prop rule typed `on_designer_refine_upload`'s
`contents` and `filename` as `str | None`.
- The component is declared `multiple=True`, so it delivers lists.
- Strict mypy passed the narrow type. The width sweep rejected it on real values.
- It was widened to `str | list[str] | None` before it shipped. It is the width rule doing
  its job (§16.1, ruling 5).

**5. The contract keys (§11): 31 → 0.**
- 31 documented session keys were never seen changing under their generator's own entry
  (inventory §79.3).
- `contract_check.py`, the thirteenth tool, reproduced 7q3's report line for line. Its bite
  was shown.
- Five contract tests, one per path, drove each key from its generator's own entry.
- On a traced run of 8g2's tree: never seen changing 0, nothing undocumented.

**Also recorded across §2–§17:**
- `_fmt_usd` accepted a string only for a test. No production caller passes one, so the
  annotation was narrowed (§4.2).
- The Prioritizer banner (report §2.3) is now asserted whole (§5).
- The racing nine (report §2.4) wait for their worker (§10). Identifying the worker needed
  a hold (§10.2).
- 5p's `: Any` grep proved a ruler of lines, not of annotations (§12.4). The figure is the
  AST series, 355 → 279 → 250 (§15.1, §16.1).
- **Wrong predictions, recorded as made:**
  - `two_state_project`'s flip (§9.2);
  - 5p's grep "does not move" (§12.4);
  - the row map's prop rule for `multiple=True` (§12.4).
- **A correction to §1:** the trace already records each invocation's entry snapshot
  (§11.1).
- **Runs killed by the environment for "low memory":** at 8e2 (§9.2) and twice at 8h1's
  sweep (§12.4), while at least 14.2 GB stayed available. Long runs have been in the
  foreground since.

### 18.4 The decisions half, laid out

- **Three were settled inside the mechanical half, by ruling:**
  - D2, `_fmt_usd`, narrowed at 8b (§4.2);
  - D3, `revision_delta`, lifted into `agents/_revision.py` at 8d2 (§7);
  - D15, the mtime sleeps, replaced by `os.utime` at 8e2 (§9).
- **Twelve remain.** Sizes are §1.2's. A "HEAD" figure is re-measured at `dd9b8ab`, and is
  shown only where it moved.

| D | Item | The ruling asked (§1.5) | Size (§1.2) | Since §1.2 |
|---|---|---|---|---|
| D7 | P3, P4, P2: root-siblings and batch 11 | Convert `project_manager` to a package, or not? If so, the move, then batch 11's renames. `_with_readme_attribution`'s four sites in the golden whole-file entry go by a petition per node, or the name stays private | P3: 4 modules, 1,746 lines, behind the 498-line façade; 13 reference lines in 4 files. P4: `_write_text_if_changed` 19 in 3; `_phase_spec_preamble` 8 in 5. P2: `_with_readme_attribution` 8 in 3, all 4 test sites in the whole-file `test_project_manager_golden.py` | unchanged (2,244 lines; the same counts) |
| D8 | P29, P1: `TestMockBuffers` against `TestMockDeliveryAck`, and the net-blocked `_start_gen` and `_record_usage` | Consolidate them? That opens `test_streaming_characterization.py`, and the two names ride with it. If not, both stay private | P29: 2 classes, 6 tests and 7. P1: `_start_gen` 38 in 6; `_record_usage` 9 in 3. Floor: whole-file `test_streaming_characterization.py` (`:344`, `:402`); tier-B `test_designer.py` `TestCapturePassesPlanningContext` (2), `TestRetryReproducesTheDraw` (2), `TestRefinePersistsManifest` (1); tier-A `TestMockDeliveryAck::test_delivery_preserves_prior_store_keys` | `_start_gen` 39 in 6 (+1, 8e's new test in `test_designer.py`) |
| D6 | P8: the step sentinel | Does it stay not taken? | 0 steps need it; the agentifier's 10 steps and their 24 `yield from` sites if taken | Evidence from 8i1–8i3: every step's `None`s end the turn, and no driver tells them apart |
| D4 | P12: the `sys.modules` idiom in `test_cost_summary.py` | Schedule the simplification 7d ruled "not scheduled", or leave it? | 1 test: the lookup, its 3-line comment, and `import sys` | unchanged |
| D5 | P31: `persist_artifacts`' name | Keep it, or rename it, and to what? | 62 occurrences in 14 files: `tests/` 51, of them 8 patch strings; `src/` 10; `scripts/` 1 | unchanged |
| D9 | P24: split `tests/test_agents.py` by source module | Split it? It was to come after 8i | 5,268 lines; 293 tests; 36 classes; 16 tier-B ids would change file | unchanged. Its precondition is met: P5–P7 (8i1–8i3) and P10 (8d2) are done |
| D10 | P27, P28: the test-family consolidation and the four large files | Phase 8, Part 2, or drop? | P27: 24 files, 616 tests. P28: 215, 213, 163 and 155 collected | `test_designer.py` 167 (+4, 8e) |
| D11 | P30: `tests/_golden.py` could absorb golden idioms | Drop it, or carry it to Part 2? | its condition has not come about | unchanged |
| D12 | P25: PLR2004 | Clear it, keep it deferred with the sizes corrected, or turn a deferral into an exemption? | `tests/` 230; `evals/` 25; `scripts/` 20 | unchanged |
| D13 | P26: the tools, inside the gate and under mypy | Bring them in, at what cost? It is now a decision about the tools' maturity, not a set of fixes (§16.1) | 16 files; mypy 224 errors in 15 | 17 files (`contract_check.py`); mypy 230 errors in 16. Three limits have landed there (§18.3 item 3), and one more is raised |
| D14 | P15: the `-> Any` returns | Classify them now, with a return-side sweep, or leave them with the design limit? | 148 lines in 24 files | 147 in 24 (`run_with_timeout` returns `T`, 8b) |
| D1 | P23b: the `> 2` guards | With 8a's evidence (§3.4), is flipping them to `> 3` a fix? | 3 characters in 1 file | the evidence: §3.4 |

**The order §1.5 proposed still holds:**
- D1 first, since its evidence is in hand.
- D2–D6 are small, and of those D4, D5 and D6 remain.
- D7's move comes before its renames.
- D8, D9 and D10 share the move petition, and the first of them ruled in builds it.
- D13 comes last, because it changes the gate under everything after it.

**Carried from the mechanical half. These are work, not rulings:**
- BACKLOG 1.3's new row, 4 tests and 1 path (§17.4);
- BACKLOG 2.1's 39 unreached callback parameters, which are product work (§15.1).

### 18.5 Stop

The mechanical half is closed. Phase 8 stops here for the decisions half's rulings.

## 19. The decisions half, ruled; D1: the three section guards at `> 3`

### 19.1 The rulings on the decisions half

All twelve were ruled at once, from §18.4's table. They are recorded here as ruled, and the
order follows them.

| D | Ruling | Reason, as ruled |
|---|---|---|
| D1 | **Fix.** Flip the three guards to `> 3`, and pin it: one test that a section with every entry skipped renders nothing, paired with one that a section with entries renders them | Nothing written reaches the header-only case, and the flip fails no test (§3). So consistency with the two siblings is the only argument left, and it is sufficient. The pair gives the guard a reason the next reader can run |
| D4 | **Remove.** Delete the `sys.modules` line and keep the assertions. No mutation | One test carrying scaffolding for a problem 7c retired. The shadow is gone, and the test's own pass proves the plain import resolves |
| D5 | **Keep `persist_artifacts`. Closed** | The contract docstring names the flush. 62 occurrences and 8 patch strings for a verb nobody has proposed is churn |
| D6 | **The sentinel stays not taken. Closed** | No step generator in the four turns split so far needed two ending causes: agentifier's 10 from 7q, and 8i's 10 across `brainstormer`, `code_scanner` and `deployer`. It reopens if one does, and the plan says how (inventory §79; §1.5) |
| D7 | **Do it:** `project_manager` as a package, then batch 11's renames. Plan mode, `ultrathink`, high | The inconsistency has been carried since Phase 5, and the size is one package move with three renames behind it. The proofs are: substitution for the imports; check 4 on every `project_manager.*` patch string; the layering test with the new edges; goldens byte-identical; and §54.7's import-only petition on the golden floor file for `_with_readme_attribution`'s four sites. **If that file needs anything beyond import lines, the name stays private** and the other two proceed |
| D8 | **Closed. `_start_gen` and `_record_usage` stay private** | `TestMockBuffers` was closed under 6f's standard, and nothing has changed. The two names would open a Phase 1 characterization file to change two spellings, and that file's job is to be untouched |
| D9 | **Split `test_agents.py`** | The precondition is met. The 16 tier-B ids that change file are exactly the move petition: bodies byte-identical, `floor.json` updated in the same commit with old and new ids, and the floor 456 / 456 after. It is split by the class structure already there, not by count |
| D10 | **The consolidation goes to Part 2. The large-files item is dropped** | Merging 24 files for tidiness is what the pruning rule forbids, by analogy: it happens only when a structural reason arrives, and Part 2 is where that waits. Files of 155–215 tests are not a problem, so that item closes |
| D11 | **Drop** | The condition never arose |
| D12 | **Tests are exempt by policy. The rest stays deferred** | Magic numbers in tests are the assertions, and that is recorded as the reason `tests/**` is ignored permanently, not deferred. `evals/**` stays ignored while `evals/` is outside the gate. `scripts/**` follows D13 |
| D13 | **Ruff yes, mypy no** | `ruff check .` is already the standing requirement, and it stays. 230 strict-mypy errors in scaffolding is a lift with no consumer until the next refactor phase, and none is planned. The three limits are documented in the README as limits: the sweep's closure resolution, check 4's aliases, and mutating on a working-tree edit. Fixing them is Part 2, "when next used". The tools' maturity: proven on this codebase, typed by nobody, and honest about what they cannot see |
| D14 | **Classify the `-> Any` returns, and take the typeable ones** | The same pass as 7o. The classes are source-edge, session-edge, JSON-edge, genuinely typeable and load-bearing. The typeable subset is taken under annotations-only and the width rule. The edges join the design limit's count |

**The order:**
1. D1, D4 and D14, as three small default-mode commits.
2. D7, in plan mode.
3. D9, under the move petition.
4. One record-only commit closing D5, D6, D8, D10, D11, D12 and D13, with the reasons above.
5. Phase 8's close-out, which is the last stop.

No page is to be published: §18.4's table is the record.

**Carried from §18.3, a correction.** "While at least 14.2 GB stayed available" holds for the
kills at 8h1's sweep, where memory was sampled every 10 seconds. At 8e2's kill (§9.2) no
memory was sampled.

### 19.2 D1: what landed

**What landed:** `2 files changed, 56 insertions(+), 6 deletions(-)`.
- **`src/spec4/feature_specs.py`: the three guards.** `_render_mechanisms` (`:364`),
  `_render_knowledge_sources` (`:390`) and `_render_tool_access` (`:421`) now read
  `return lines if len(lines) > 3 else []`, as the two siblings at `:214` and `:281` do.
- **Each `noqa` reason is now the siblings' own:** "a two-line header and a closing blank, so
  > 3 is one entry". It fits all three exactly. Each builder opens its lines with the
  heading and a blank, and appends a closing blank, so a section with every entry skipped
  is three lines. `> 2` let that through, and `> 3` requires one entry.
- **`tests/test_feature_specs.py`: the pair,** as `TestSectionGuards`, appended after
  `TestMechanismGlossary`.
  - The pair goes through the public `render_feature_block(feature, fields=(field,),
    include_graph=False)`, as the file's other tests do. It loops over the three fields,
    with the field as each assertion's message.
  - **`test_a_section_whose_entries_are_all_skipped_renders_nothing`** feeds each builder
    only skipped entries: a bare string, and an object without the field its builder
    names the entry by (`name`, or `purpose` for tools). It asserts `== []`.
  - **`test_a_section_with_entries_renders_them`** feeds the same skipped entries plus one
    that survives. It asserts the exact lines: the heading, a blank, the one entry, and
    the closing blank.
  - So the pair shows that the skipped entries are ignored, not just that a single entry
    renders.
- **Floor:** the file's entries are `TestPhaseSpecFields`' five ids, which are untouched.
  The hunk is an append after the file's last class, which is §51.6's allowed-and-reported
  case.

### 19.3 D1: the proofs

**Strict mypy, ruff and format.** `Success: no issues found in 93 source files`; `All
checks passed!` on `src/ tests/` and on `.`; `240 files already formatted`.

**The mutation, run before the commit (§15, ruling 6): the fix undone.**
- **The case needs no source edit.** HEAD's guards are the mutated state, so the case
  carries only the new pair, and runs it against `> 2`.
- **Predicted:** the skipped-entries test fails, and the with-entries test is must-pass.
- **The sequence ran with the review's checks:**

```
e2d976f567745c98f12ebc0830c0805246807ae8a3c9a10655d3e02aed24905b  src/spec4/feature_specs.py
b290a2234a20afeff7403d9a941d2d421557b6b4f50edc8fc81d35b30a4f9d06  tests/test_feature_specs.py
cases_d1.json sha256 a09c50daecabda2165cc307c74a5eaee035622695a2d7cd3458b5bb5c0c7602c
tree verified clean at HEAD (0da5745)
restore: 1 file(s) byte-identical by sha256; tree clean
M d1_unflipped (D1: the three section guards left at > 2, with the new pair added (the fix undone)): predicted 1, failed 1; must-pass 1, failed 0; as predicted
   FAILED (predicted)       tests/test_feature_specs.py::TestSectionGuards::test_a_section_whose_entries_are_all_skipped_renders_nothing
   PASSED (must pass)       tests/test_feature_specs.py::TestSectionGuards::test_a_section_with_entries_renders_them
   other failures: 0
   summary: 1 failed, 4223 passed, 1 skipped in 87.96s (0:01:27)
restored: both sha256 identical to before
```

- **As predicted.** The pin fails exactly when the guard admits a header-only section. The
  with-entries half holds under both guards, so the flip removes only the empty section.
  Nothing else in the suite noticed. That is 8a's measurement (§3.3) again, now from the
  other side.

| Gate | Result |
|---|---|
| Ruff / format / mypy | as above |
| Tests | `4224 passed, 1 skipped`, exit 0: the two new tests |
| Coverage | `TOTAL 12475 808 94%`. **Misses fall from 834 to 808,** all 26 in `feature_specs.py` (80 → 54). The pair is the first thing in the suite to run the three builders' entry paths |
| Floor / off-limits | `456 (expect 456)`, `FAILURES: 0`; the one test hunk is outside every entry |

## 20. D4: the `sys.modules` idiom removed from `test_cost_summary.py`

**Ruled at §19.1:** remove it. Delete the `sys.modules` line, keep the assertions, and run no
mutation. The shadow the lookup worked around is gone, and the test's own pass proves the
plain import resolves.

**What landed** (`tests/test_cost_summary.py` only): `1 file changed, 3 insertions(+), 7
deletions(-)`.
- **`test_both_surfaces_call_the_one_renderer`** (`TestOneRenderer`) loses the lookup
  `module = sys.modules["spec4.layouts._round_cost"]` and its three-line comment. The
  comment explained the lookup as a workaround for `spec4.layouts` re-exporting a
  `_round_cost` function that shadowed the submodule.
- **The test now patches the module by name:**
  `monkeypatch.setattr(_round_cost, "cost_strip_lines", lambda figures: _round_cost.RoundCost(...))`.
  `from spec4.layouts import _round_cost` sits beside the file's other `spec4.layouts`
  imports.
- **`import sys` goes with it.** It had no other use in the file.
- **Every assertion is unchanged.**

**Why the plain import is sound, checked before the edit:**
- `spec4/layouts/__init__.py` imports only `round_cost` and `round_cost_lines` from the
  submodule. Nothing binds `_round_cost`, so the package attribute is the submodule.
- The test file uses no other name `_round_cost`.
- **The test's pass is the proof.** Its assertions read the stub's wording through both
  renderers, `round_cost_lines` and `run_cost_lines`. A patch on any other object would
  leave them reading the real `cost_strip_lines`, and the test would fail.

**Floor.** `TestOneRenderer` holds no entry. The file's three tier-A nodes are in
`TestChatPlacement`, `TestDesignerPlacement` and `TestStripNumbers`, and are untouched. The
import hunk sits at the top of the file, outside every entry.

| Gate | Result |
|---|---|
| Ruff / format / mypy | `All checks passed!` on `src/ tests/` and on `.`; `240 files already formatted`; `Success: no issues found in 93 source files` |
| Tests | `4224 passed, 1 skipped`, exit 0; the file's 57 all pass, `test_both_surfaces_call_the_one_renderer` among them |
| Coverage | `TOTAL 12475 808 94%`: unchanged, as a test-only edit should leave it |
| Floor / off-limits | `456 (expect 456)`, `FAILURES: 0` |

**BACKLOG 1.1's `sys.modules` item (P12) is closed.**

## 21. D14: the `-> Any` returns, classified, and the typeable fourteen taken

**Ruled at §19.1.** Classify the returns in the same pass as 7o, into source-edge,
session-edge, JSON-edge, genuinely typeable and load-bearing. Take the typeable subset
under annotations-only and the width rule, and let the edges join the design limit's count.

### 21.1 The rows

**144 functions in 23 files return a bare `Any`,** counted by AST. That is every function
whose return annotation is the name `Any`.
- §1.2's 148, and §18.4's 147, were a grep for the text `-> Any`. It also matches lines
  that are not a bare return.
- 87 of the 144 are Dash callbacks, and none is a generator.

### 21.2 How they were classified

**The classes are 7o's (inventory §77), plus source-edge.** 7o's four were session-dict
edge, JSON-artifact edge, genuinely typeable and load-bearing. Source-edge is the ruling's
fifth. It is read here as a value whose type comes from a library mypy sees as untyped,
so that no annotation narrower than `Any` can pass strict mypy without a cast. A cast is a
runtime change. Two measurements, both in a scratch probe, fix what that covers:
- **`dash_mantine_components` 2.6.1 ships no `py.typed`,** so every `dmc.*(...)` is `Any`.
  `-> Component` on a function returning a `dmc` component fails with `Returning Any from
  function declared to return "Component"`.
  - `dash` 4.1.0 is typed. A wrong annotation on an `html.*` return is caught (`got "Div",
    expected "int"`).
  - `dash.NoUpdate` is exported publicly, and `-> bool | NoUpdate` returning `no_update`
    passes.
- **Two first-party wrappers inherit an untyped source:**
  - `dcc.send_string` and `dcc.send_bytes` carry no return annotation;
  - `@callback` hands back `Any` (`reveal_type` says so).

**The rule for taking a row.** Strict mypy accepts a narrower annotation with no runtime
change. No top-level member and no tuple element is a bare `Any`. A container of Dash
children may hold `Any`, as 7o's `html.Div | list[Any]` did. Rows were placed by the
callee's declared type where one decides it, never by name.

| Class | Rows | What they are |
|---|---:|---|
| **session-edge** | **82** | 78 callbacks with a store (`data`) output, whose return is the session or store payload; and `_no_change`, `_poll_running`, `_rerun_failed_draw` and `_skip_to_stack_advisor`, which return that payload for their callbacks |
| **source-edge** | **40** | 32 layout builders returning `dmc` components, or passing one through (`artifact_body`'s file path; `provider_key_hint`); 5 callbacks whose output is or holds a `dmc` value (`on_provider_hint`, `render_designer_step`, `on_gate_provider_change`, `on_search_provider_hint`, and `on_artifact_pane` through `artifact_body`); `_send_json` and `_build_phases_zip`, through the unannotated `dcc.send_*`; `_register_open_artifact`, returning an `@callback` closure |
| **load-bearing** | **8** | the `SubAgent` protocol: `SubAgent.run`, `SubAgentRegistry.lookup` (it reads `_agents: dict[str, Any]`) and `SubAgentRegistry.run`, which are heterogeneous by design (7o's reason); and `llm.py`'s `_get`, `_chunk_usage`, `_hidden_usage`, `complete` and `acomplete`, litellm values read duck-typed, or a stream-or-response |
| **JSON-edge** | **0** | no return in the 144 is an artifact payload |
| **genuinely typeable** | **14** | all taken (§21.3) |

The table, row by row, with each reason, is scratch `d14/classified.json`.

### 21.3 The fourteen taken

| Function | Where | Type |
|---|---|---|
| `artifact_controls` | `layouts/_artifact_view.py` | `html.Div` |
| `_round_select` | `layouts/_artifact_view.py` | `html.Div` |
| `designer_layout` | `layouts/designer.py` | `html.Div` |
| `_line_children` | `layouts/_round_tree.py` | `html.Li` |
| `_step_title` | `layouts/_setup.py` | `html.H2` |
| `_sep` | `layouts/_shared.py` | `html.Span` |
| `_dir_field` | `layouts/_status_bar.py` | `html.Button \| html.Span` |
| `on_ff_info` | `callbacks/_chat.py` | `bool \| NoUpdate` |
| `_poll_missing_stream` | `callbacks/_chat.py` | `tuple[NoUpdate, int]` |
| `on_round_tree` | `callbacks/_artifacts.py` | `tuple[str, list[Any]]`, from `_round_tree_head -> str` and `_round_tree_lines_children -> list[Any]` |
| `on_round_cost` | `callbacks/_artifacts.py` | `tuple[str, ...]`, `tuple()` of the `RoundCost` NamedTuple's three `str` fields |
| `on_status_bar` | `callbacks/__init__.py` | `tuple[list[Any], str, str, str]`, from `status_context -> list[Any]` and three `_status_nav_class -> str` |
| `_cc_revise_input` | `agentifier/agentifier.py` | `CrossCuttingInput` |
| `_run_async` | `websearch.py` | PEP 695: `def _run_async[T](coro: Coroutine[Any, Any, T]) -> T`, as 8b took `run_with_timeout` |

**`NoUpdate` is imported under `if TYPE_CHECKING:` in `callbacks/_chat.py`,** not added to its
runtime `from dash import …` line.
- **7o's rule (inventory §77.1).** A row needing a name its module does not bind at runtime
  imports it "under `if TYPE_CHECKING:` only", because "a runtime import would be residue".
  The strip check is the standing check for annotation work (§77.1's confirmations).
- **The dry run showed it.** The runtime-line form left exactly one line of strip residue:
  the import itself. The guarded form leaves none.
- **§14's `Literal` ruling does not govern here.** It placed a `typing` name on an existing
  runtime line, in a turn that ran no strip check. D14 is annotation work.
- **The block sits after the last leading import,** as `llm.py`'s does, and the module carries
  `from __future__ import annotations`. It is the seventh block in `src/`.

### 21.4 The proofs

**Applied as dry-run.** The fourteen edits and the guarded block went first onto a `git
archive` export of `dc6495f`, as the second dry run. Then they went onto the tree by the
same scripts, followed by `ruff format`.
- **All 11 changed files are byte-identical to the dry run's** (`cmp`, file by file).
- **Footprint:** `11 files changed, 18 insertions(+), 15 deletions(-)`, all in `src/`. No
  test changed.

**Strict mypy, ruff and format.** `Success: no issues found in 93 source files`; `All
checks passed!` on `src/ tests/` and on `.`; `240 files already formatted`.
- **mypy checks each of the fourteen against its body.** So a return type narrower than what
  the function returns is caught here.
- The PEP 695 `_run_async` is checked at its callers' types.

**The strip check, against `dc6495f`:** `files changed: 11; files with residue: 0`.
- **The first dry run put `NoUpdate` on `_chat.py`'s runtime `from dash import …` line,** and
  left exactly that one line of residue:

```
RESIDUE: src/spec4/callbacks/_chat.py
    -from dash import ALL, Input, Output, State, callback, ctx, no_update
    +from dash import ALL, Input, NoUpdate, Output, State, callback, ctx, no_update
```

- **7o's rule placed it under `if TYPE_CHECKING:` instead** (§21.3), and the residue is gone.

**The width rule, on returns.** The committed `width_sweep.py` checks the values that arrive
at parameters. So a scratch plugin, `d14/ret_sweep.py`, monitors `PY_RETURN` on each of the
fourteen and checks every returned value against the return annotation in the tree.
- **It reuses the committed sweep's `accepts`,** adding `tuple[...]`, PEP 695 type parameters,
  and a direct `isinstance` for `NoUpdate`. `NoUpdate` is not in `_chat.py`'s runtime
  namespace, since it is imported under `TYPE_CHECKING`.
- **The committed tool is unchanged,** as D13 rules. A return-side sweep is on the Part 2 list
  with the other tool work, "when next used".

```
ret_sweep: targets 14; reached 14; never reached 0; rejected 0 []
4224 passed, 1 skipped
```

| Target | Annotation | Calls | Returned |
|---|---|---:|---|
| `agentifier/agentifier.py:_cc_revise_input` | `CrossCuttingInput` | 3 | spec4.agentifier.cross_cutting_analyst.CrossCuttingInput x3 |
| `callbacks/__init__.py:on_status_bar` | `tuple[list[Any], str, str, str]` | 39 | builtins.tuple x39 |
| `callbacks/_artifacts.py:on_round_tree` | `tuple[str, list[Any]]` | 10 | builtins.tuple x10 |
| `callbacks/_artifacts.py:on_round_cost` | `tuple[str, ...]` | 7 | builtins.tuple x7 |
| `callbacks/_chat.py:on_ff_info` | `bool | NoUpdate` | 2 | builtins.bool x1, dash._no_update.NoUpdate x1 |
| `callbacks/_chat.py:_poll_missing_stream` | `tuple[NoUpdate, int]` | 2 | builtins.tuple x2 |
| `layouts/_artifact_view.py:artifact_controls` | `html.Div` | 96 | dash.html.Div.Div x96 |
| `layouts/_artifact_view.py:_round_select` | `html.Div` | 87 | dash.html.Div.Div x87 |
| `layouts/_round_tree.py:_line_children` | `html.Li` | 1773 | dash.html.Li.Li x1773 |
| `layouts/_setup.py:_step_title` | `html.H2` | 117 | dash.html.H2.H2 x117 |
| `layouts/_shared.py:_sep` | `html.Span` | 2760 | dash.html.Span.Span x2760 |
| `layouts/_status_bar.py:_dir_field` | `html.Button | html.Span` | 888 | dash.html.Button.Button x840, dash.html.Span.Span x48 |
| `layouts/designer.py:designer_layout` | `html.Div` | 76 | dash.html.Div.Div x76 |
| `websearch.py:_run_async` | `T` | 5 | builtins.list x3, builtins.str x2 |

- **Every target is reached, and every returned value is accepted:** 5,865 calls.
- **The two unions are exercised on both members.** `_dir_field` returned `html.Button`
  840 times and `html.Span` 48 times. `on_ff_info` returned `True` once and `NoUpdate`
  once.

**The figures.** From §15.1, the AST count is the figure, and 5p's grep is the continuity
column:
- **bare `-> Any` returns across `src/spec4`: 144 → 130;**
- the bare-`Any` parameter series: 250, unchanged. `_run_async`'s parameter became
  `Coroutine[Any, Any, T]`, which was never a bare `Any`;
- 5p's grep: 236, unchanged. It counts `: Any`, which no return annotation contains.

**The design limit's count gains the edges.** 82 session-edge returns and 40 source-edge
returns join §1.2's design limit, beside its 90 session-dict and 107 JSON-artifact
parameter lines. The 8 load-bearing returns stay, each with its reason in §21.2.

| Gate | Result |
|---|---|
| Ruff / format / mypy | as above |
| Tests | `4224 passed, 1 skipped`, exit 0: unchanged |
| Coverage | `TOTAL 12475 808 94%`: unchanged, as annotations add no statement |
| Floor / off-limits | `456 (expect 456)`, `FAILURES: 0`; no test file touched |

## 22. D7a: `project_manager` as a package

This ran in plan mode, as ruled at §19.1. The plan was read and approved before any edit,
without amendment. That approval also accepted the one choice it put for review:
`_phase_spec_preamble` proceeds at D7b, and the golden floor file's docstring mention of it
is left stale (§23).

**This commit is the move.** D7b carries the renames.

### 22.1 What landed

**Five renames, with their import references re-pointed:**

| From | To |
|---|---|
| `src/spec4/project_manager.py` | `src/spec4/project_manager/__init__.py` |
| `src/spec4/_paths.py` | `src/spec4/project_manager/_paths.py` |
| `src/spec4/_artifacts.py` | `src/spec4/project_manager/_artifacts.py` |
| `src/spec4/_phase_markdown.py` | `src/spec4/project_manager/_phase_markdown.py` |
| `src/spec4/_usage.py` | `src/spec4/project_manager/_usage.py` |

- **The 13 reference lines,** `spec4._x` → `spec4.project_manager._x`, each asserted to occur
  once:
  - the façade's four docstring `:mod:` lines, and its four imports;
  - `_artifacts.py`'s two imports;
  - `_usage.py`'s one;
  - `tests/test_usage_capture.py`'s two patch strings, `spec4._usage._replace` and
    `spec4._usage._fdopen`.
- **Layout beyond the 13, a departure from the plan's "no other byte changes",** named
  here and proven in §22.2:
  - **The docstring's first two bullets reflow onto their continuation lines.** At the new
    path they exceed 88 characters, and `project_manager`'s file carries no per-file E501
    ignore, as its own `noqa` at `_artifact_button_state` says.
  - **`ruff format` wraps two lines:** `_artifacts.py`'s `_phase_markdown` import, now 93
    characters, and the two re-pointed patch strings.
- **Nothing else changed.** `git diff -M --stat`: `6 files changed, 20 insertions(+), 15 deletions(-)`: the façade 20 lines, `_artifacts.py` 7, `_usage.py` 2, `_paths.py` and `_phase_markdown.py` 0 (pure renames), `tests/test_usage_capture.py` 6.
- **Nothing in `src/` or `tests/` names an old path any more.**

### 22.2 The proofs

**1. Substitution for the imports: a scratch move check.**
- **`rename_check.py` diffs same-path trees, so it cannot see a move.** So `d7/move_check.py`
  applies its idea to one:
  - every file tracked at HEAD is found at its new path, or its own;
  - its text, with `spec4.project_manager._x` reversed to `spec4._x`, must match HEAD's;
  - Python files compare by AST, with each string constant's whitespace collapsed, so that
    `ruff format`'s wraps and the docstring reflow read as layout and nothing else does;
  - every other file compares byte for byte.

```
-- the move check: 455 files at BASE
   added beyond the moves: none
   lost: none
   byte-identical: 451; changed: 4, of which equal under the substitution: 4
   changed files: ['src/spec4/project_manager/_artifacts.py', 'src/spec4/project_manager/_usage.py', 'src/spec4/project_manager/__init__.py', 'tests/test_usage_capture.py']
   NOT equal under the substitution: none
```

- **`git diff -M` records the five as renames:** `R  src/spec4/project_manager.py ->
  src/spec4/project_manager/__init__.py`, and the four siblings.

**2. The layering test, and the new edges.** The test passes in the suite. Its own
`_module_name` and `_import_edges` were run as its `graph` fixture runs them, over a
`git archive` export of HEAD and over the tree:

```
   modules: base 93, head 93; the same under the substitution: True
   spec4.project_manager -> ['spec4.app_constants', 'spec4.project_manager._artifacts', 'spec4.project_manager._paths', 'spec4.project_manager._phase_markdown', 'spec4.project_manager._usage']
   spec4.project_manager._artifacts -> ['spec4.app_constants', 'spec4.project_manager._paths', 'spec4.project_manager._phase_markdown']
   spec4.project_manager._paths -> ['spec4.app_constants']
   spec4.project_manager._phase_markdown -> ['spec4.design_manifest', 'spec4.feature_specs', 'spec4.stack_routing']
   spec4.project_manager._usage -> ['spec4', 'spec4.app_constants', 'spec4.project_manager._paths']
   edges from the package into the Dash side: none
   importers of the package from outside it: 23
```

- **The graph is the same graph under the substitution.** The four siblings are now inside
  `spec4.project_manager`, which `test_import_layering.py` already lists on the agent side
  by name or name-plus-dot.
- **Their edges run to the package and to root modules only.** The package has no
  internal cycle: no sibling imports it.

**3. Check 4, on every patch string that reaches the package.**
- **`patch_resolve.py` gives the same verdicts before and after the move.** It was run on
  the tree, and on a `git archive` export of HEAD with its own scratch `git init`,
  imported through `PYTHONPATH`. Both give `targets 9; FAIL: 8`, with the same shape and
  reason for every target and only the module paths differing.
- **So the move changes no check-4 verdict.** Each FAIL is a limit of the tool's form, met
  as follows:

| Target | `patch_resolve` | The proof that the patch lands |
|---|---|---|
| `spec4.project_manager._is_dir` (`test_root_routing.py:387`) | PASS: defined in the package's `__init__`, and called at `directory_opens@375` | — |
| `spec4.project_manager.load_feature_specs` (`test_vision_grounding.py:276`) | FAIL (2): a re-export, with no call inside the module the string names | `check4_attr.py`: **PASS**. `feature_specs_for_session` reads `project_manager.load_feature_specs@458`, through `spec4.agentifier.agentifier`'s binding of the package |
| `spec4.project_manager.save_usage` (`test_usage_capture.py:1003`) | FAIL (2): the same form | `check4_attr.py`: **PASS**. `persist_artifacts` reads `project_manager.save_usage@574`, through `spec4.session`'s binding |
| `setattr(_dmod().project_manager, "load_feature_specs", …)` (`test_designer.py:841`, `:851`, `:864`) and `setattr(dmod.project_manager, …)` (`:920`) | not statically resolvable: "check by hand" | **By hand:** `spec4.callbacks.designer.project_manager`, `_mock_gen.project_manager` and `_refine.project_manager` are each `spec4.project_manager`, the same object `agentifier` and `session` bind. So each `setattr` lands on the module object every designer caller reads |
| `spec4.project_manager._usage._replace` and `._fdopen` (`test_usage_capture.py:852`, `:875`) | FAIL (1): not a function named so; (2) holds: `_write_atomic@370` and `@366` call them | **These are 7k's seams:** `_usage._replace is os.replace` and `_usage._fdopen is os.fdopen`, so condition (1) fails by construction, check 4's alias shape (README §3). Condition (2) holds. The two tests that patch them assert the failure the patch injects, and both pass |

- **None of these tests is edited.** The four `setattr` sites sit in `test_designer.py`'s
  tier-B classes, and they were read, not touched.

**4. Goldens byte-identical.** `git diff --stat -- tests/golden tests/snapshots` is empty, and
the golden tests pass.

**5. Coverage, module by module at the new paths:**

| Module | At `90d6137` | At the new path |
|---|---|---|
| `project_manager.py` → `project_manager/__init__.py` | 110 / 1 | 110 / 1 |
| `_paths.py` → `project_manager/_paths.py` | 60 / 0 | 60 / 0 |
| `_artifacts.py` → `project_manager/_artifacts.py` | 257 / 17 | 257 / 17 |
| `_phase_markdown.py` → `project_manager/_phase_markdown.py` | 230 / 0 | 230 / 0 |
| `_usage.py` → `project_manager/_usage.py` | 160 / 2 | 160 / 2 |

- **Every other module's row is identical.**
- **`_artifacts.py`'s missed line numbers shift by 3:** the wrapped import grew from one line
  to four.

| Gate | Result |
|---|---|
| Ruff / format / mypy | `All checks passed!` on `src/ tests/` and on `.`; `240 files already formatted`; `Success: no issues found in 93 source files` |
| Tests | `4224 passed, 1 skipped`, exit 0: unchanged |
| Coverage | `TOTAL 12475 808 94%`: unchanged |
| Floor / off-limits | `456 (expect 456)`, `FAILURES: 0`. No floor file is edited; `test_usage_capture.py` holds no entry |

**No mutation.** A move is proven by substitution, as 7p's proof was planned (inventory
§60.6).

**BACKLOG 1.1's root-siblings item (P3) is done.** Batch 11 follows at D7b.

## 23. D7b: batch 11's two renames

The plan approved at §22 carries this commit.
- **`_write_text_if_changed` → `write_text_if_changed`.**
- **`_phase_spec_preamble` → `phase_spec_preamble`.**
- **`_with_readme_attribution` stays private, by the ruling (§19.1).**
  - Its four sites in the golden floor file, `test_project_manager_golden.py:168`, `:169`,
    `:172` and `:173`, are attribute calls: `project_manager._with_readme_attribution(...)`.
  - They are not import lines, so §54.7's import-only petition cannot be met there. That is
    inventory §60.2's ⛔.
  - So the golden floor file needs no edit, and no §54.7 petition runs.

### 23.1 What landed

**`rename_apply.py`, with the map `[["_write_text_if_changed", "write_text_if_changed"],
["_phase_spec_preamble", "phase_spec_preamble"]]`, on the clean tree at `72fd462`:**

```
files changed: 8, lines changed: 31
whole-file alias edits: 0 in 0 files
module-path occurrences left alone: 0
frozen-data hits: none
BLOCKED (§54.7 cannot be met): none
```

- **The code, 26 lines in 5 files:**
  - `project_manager/_artifacts.py` 12: the definition, its uses, and two docstring mentions;
  - `tests/test_project_manager.py` 6: `TestIdempotentWrites`' four calls, `TestProjectReadme`'s
    docstring at `:655`, and `TestPreambleTwoAltitudesAndSurfaces`' call at `:1138`;
  - `project_manager/__init__.py` 4: the two import lines and the two `__all__` entries,
    which now list the public names;
  - `project_manager/_phase_markdown.py` 3;
  - the `agents/_seam_check.py:341` docstring (D-PH2), 1.

  `ruff format` then left all five files unchanged: `5 files changed, 26 insertions(+), 26 deletions(-)`.
- **The tool also rewrote three documents,** since it spares only `CLEANUP_INVENTORY.md`, the
  Phase 7 record: `BACKLOG.md` 1 line, `CLEANUP_REPORT.md` 1 and `PHASE8_RECORD.md` 3. All
  three were restored from HEAD, and each one's `git hash-object` equals HEAD's blob. The
  record stays add-only, and BACKLOG's P2 and P4 close by hand in the record-only commit.
- **The golden floor file is byte-untouched,** as the plan said. `rename_apply.py` excludes
  docstrings from its blocking scan, and a whole-file entry gets only import rebinding. The
  file imports neither name.
  - **Its module docstring keeps the old name, as the plan's one choice accepted.** The
    mention is at `:10–11`: "The full-phase fixture is built to drive every branch of ``_phase_spec_preamble``".
  - It names `_phase_spec_preamble`, which is now `phase_spec_preamble`. That is inventory
    §60.2's "goes stale", recorded here with its line.

**A §22 claim, verified after the fact.** §22 said the two tests that patch `_usage._replace`
and `_fdopen` "assert the failure the patch injects". They do:
- `TestSaveUsageAtomicity::test_failed_write_leaves_original_intact_and_no_temp_file`
  patches `_replace` to raise. It asserts `pytest.raises(OSError)`, the file unchanged, and
  no temp file left.
- `::test_partial_content_write_never_reaches_the_file` patches `_fdopen` to fail mid-write,
  and asserts the same three.

### 23.2 The proofs

**Strict mypy, ruff and format.** `Success: no issues found in 93 source files`, with
`__all__` now listing `write_text_if_changed` and `phase_spec_preamble`. `All checks passed!`
on `src/ tests/` and on `.`; `240 files already formatted`.

**The rename check (§60.2), against `72fd462`:**

```
rename check: EMPTY -- the change is identifier substitution alone
```

**The token check:**

```
hunks 26; old->new token substitutions 26; layout 0; §54.7 aliases 0; OTHER 0
```

**§60.3's rename petition, for the one floor entry the rename reaches:**

```
§60.3  tests/test_project_manager.py [tierB:TestPreambleTwoAltitudesAndSurfaces]: (1) reverse diff empty inside the net entry PASS  (2) assertions identical under substitution PASS
off-limits (floor): FAILURES             : 0
net files in the diff: whole=[]
PETITION: PASS
```

- No whole-file entry is in the diff: `test_project_manager_golden.py` is untouched.
- `TestIdempotentWrites` and `TestProjectReadme` hold no entry, so their hunks are §51.6's
  allowed-and-reported case.

**Check 4.** No patch string names either new name:

```
targets ending in a batch name (new side): 0; FAIL: 0; fourth-form candidates: 0
```

**Goldens and the golden floor file.** `git diff` names nothing under `tests/golden`,
`tests/snapshots` or `tests/test_project_manager_golden.py`.

| Gate | Result |
|---|---|
| Ruff / format / mypy | as above |
| Tests | `4224 passed, 1 skipped`, exit 0: unchanged |
| Coverage | `TOTAL 12475 808 94%`: unchanged |
| Floor / off-limits | `456 (expect 456)`, `FAILURES: 0`; the petition above |

**BACKLOG 1.1's batch 11 item (P4) is done for two of its three names.** P2,
`_with_readme_attribution`, stays private by the ruling. Both close in the record-only
commit. D9 follows, in plan mode.

## 24. D9a: the move petition, as the fourteenth tool

This ran in plan mode (§1.6). The plan was read and approved before any edit, without
amendment.
- **D9 is two commits:** this one adds the check that proves a move, and D9b (§25) makes the
  split.
- **Committing the check was the plan's one choice of its own,** not the ruling's. It is
  §1.4's proposal for "a petition for a moved test", and D10's consolidation can use it
  again when it reaches Part 2. D13's ruling covers it: it is ruff-clean, and untyped like
  the other thirteen.

### 24.1 What landed

- **`scripts/cleanup/move_check.py BASE_DIR NEW_DIR MAP.json`.** It compares two trees,
  before and after, given a map of which top-level nodes left a source file and where each
  went. It makes four checks:
  1. **Collection:** `pytest --collect-only -q` in each tree, importing that tree's own
     `src/`. Every node id from before must be collected after, exactly once, at its mapped
     file, with the same class and function names and any parametrised suffix. Nothing may
     be unaccounted for.
  2. **Byte-identity:** every top-level node of each source file, moved or staying, must
     have a byte-identical source segment after, decorators included. The files' headers
     are regenerated, and not compared.
  3. **The floor:** `floor.json` must change by exactly the moved classes' ids, old → new.
     The new tree's own `floor_check.py` must pass on the new tree's collection.
  4. **Nothing else:** every other `tests/` file must be byte-identical, and every new file
     must be a destination.
- **Why check 3 hands over the collection.** `floor_check.py` otherwise asks git for the
  repo root, which a `git archive` export lacks. So the tool writes the new tree's
  collected ids to a temp file and passes it. That was learned on the first scratch run,
  where check 3 failed on exactly that, before any floor id was compared.
- **The README** gains "The fourteenth tool: the move petition" and its row under
  "Replayed when committed".
- **`ruff check` and `ruff format --check` pass on the tool,** and so does `uv run ruff
  check .`.

### 24.2 The proof: the real split, built in scratch, and the tool's bite

**On the real split.** A scratch script sliced a `git archive` export of `a0cf8c1` into the
six files and the helper module, and rewrote the 16 floor ids. This is the split D9b makes
(§25):

```
collected: BASE 4225, NEW 4225
check 1 (collection): PASS
top-level nodes compared: 45
check 2 (byte-identity): PASS
floor ids rewritten old -> new: 16; NEW's floor_check: ['floor total          : 456 (expect 456)', 'FAILURES             : 0']
check 3 (the floor): PASS
other tests/ files compared: 180
check 4 (nothing else): PASS
MOVE PETITION: PASS
```

**Its bite.** One fault per scratch copy of that split, each meant to trip one check:

| Bite | The fault | Verdicts |
|---|---|---|
| (a) | `TestPhaser`, line 34 of `tests/test_phaser.py`: `assert len(phases) == 1 and …` → `>=` | FAIL: check 2; PASS: 1, 3, 4 |
| (b) | `tests/test_deployer.py` imports `_no_such_helper`, a name that does not exist, inside its parenthesised import. The file parses, and only its import fails | FAIL: check 1; PASS: 2, 3, 4 |
| (c) | `TestDeployerReadme::test_decline_skips_readme_no_llm_call` removed | FAIL: checks 1, 2; PASS: 3, 4 |
| (d) | one `TestPhaserSpecReferenceDirective` id left at `tests/test_agents.py` in `floor.json` | FAIL: check 3; PASS: 1, 2, 4 |
| (e) | `tests/test_session.py` gains a stray line | FAIL: check 4; PASS: 1, 2, 3 |
| (b2) | `_no_such_helper, ` spliced in front of the import's `(`, so `tests/test_deployer.py` no longer parses | FAIL: checks 1, 2; PASS: 3, 4 |

- **Each of the four checks bites alone:** (a) check 2, (b) check 1, (d) check 3, (e) check 4.
  The tool's own lines name the fault:
  - (a) `TestPhaser: not byte-identical in tests/test_phaser.py`;
  - (b) `collection exit 2`, with `test_deployer.py`'s 38 ids `not collected at its new place`;
  - (d) `floor.json['tier_b'] is not BASE's with the moved ids rewritten`, and `floor_check.py exit 1`;
  - (e) `changed but not in the map: tests/test_session.py`.
- **(c) is the plan's dropped test, and it trips checks 1 and 2 together.** Removing a test also
  changes its class, so both checks see it.
- **(b2) caught a defect in the tool, and the tool was fixed before this commit.**
  - My first run of bite (b) spliced the name in front of the parenthesised import's `(`.
    That made the file unparseable, which is not the fault I meant to plant.
  - The tool then crashed in check 2's `ast.parse` with a `SyntaxError`, after reporting
    check 1 and before checks 2 to 4.
  - `segments()` now records a parse failure instead of raising, and check 2 reports it:
    `tests/test_deployer.py: does not parse (line 12: invalid syntax)`.
  - That tree is kept as (b2), and the tool now gives all four verdicts on it.
  - Bite (b) was redone as intended. The clean pass and all six bites above are this
    commit's tool, re-run after the fix. The earlier runs are discarded.

| Gate | Result |
|---|---|
| Ruff / format | `All checks passed!` on the tool and on `.`; `1 file already formatted` |
| Tests, coverage, mypy | unaffected: no file under `src/` or `tests/` changed, and the tools stay outside mypy (D13) |
| Floor / off-limits | `456 (expect 456)`, `FAILURES: 0`, as the petition's own run shows |

## 25. D9b: `tests/test_agents.py` split by source module

The plan approved at §24 carries this commit. §24's tool is its proof.

### 25.1 What landed

**Five new files and a helper module, split by the class structure already there:**

| File | Classes | Test functions |
|---|---|---:|
| `tests/test_brainstormer.py` | 5 | 39 |
| `tests/test_stack_advisor.py` | 6, with `_stack_revision_vision` | 37 |
| `tests/test_code_scanner.py` | 5 | 69 |
| `tests/test_phaser.py` | 13, with `_valid_phase` and `_phase_block` | 84 |
| `tests/test_deployer.py` | 5 | 38 |
| `tests/test_agents.py`, which stays | 2: `TestResumeSummary` and `TestSuppressedAsArtifact` | 11 |
| `tests/_agent_helpers.py` | none: the six shared helpers `make_session`, `collect`, `mock_litellm_stream`, `_chunkify_stream`, `_reply_sequence` and `_phaser_revision_vision` | 0 |

- **The totals are the file's at `a0cf8c1`:** 36 classes, 278 test functions and 293
  collected ids.
- **`test_agents.py` goes from 5,268 lines to 171.** The seven files hold 5,363 lines. The
  95 extra are the new headers and docstrings.
- **Built by the scratch script behind §24's proof,** run on the clean tree. The script:
  - copies every top-level node byte for byte, with the banner above it;
  - generates each file's imports from the original header, filtered to the names that
    file's nodes use;
  - gives each file a docstring naming its subject and origin.
- **`ruff format` wrapped one line in each of five files.** That line is the generated
  `from tests._agent_helpers import …`, which was over 88 characters. No moved body
  changed (check 2). After the format, all seven files are byte-identical to §24's scratch
  split, which passed the petition there.
- **The pointers, updated in the same commit:**
  - **`floor.json`:** the 16 tier-B ids, old → new, rewritten in place. Of these, 8 are
    `TestAiFeaturesForPhaserFullSurface` and 4 `TestPhaserSpecReferenceDirective`, now in
    `tests/test_phaser.py`. The other 4 are `TestLoadDesignManifest`, now in
    `tests/test_stack_advisor.py`. The result is identical to the scratch copy's.
  - **BACKLOG 1.3's test row:** its first id → `test_brainstormer.py::`. Its two `::`
    continuations follow it, since both classes moved there.
  - **`CLEANUP_REPORT.md` §2.4a:** four id lines, to `test_brainstormer.py` (two),
    `test_code_scanner.py` and `test_deployer.py`.
- **Unchanged, as planned:**
  - the record and `CLEANUP_INVENTORY.md`;
  - the report's historical statements about `test_agents.py`, at `:157`, `:309`, `:380`,
    `:606`, `:612`, `:666` and `:676`;
  - `.spec4/`, under Rule 2. Its `v0/code_review.json:279` names `test_agents.py`, and stays.
- **BACKLOG's split row (`:65`) closes by hand in the record-only commit,** like P2 and P4
  (§23).

### 25.2 A claim in the plan that was wrong: one other test imports from `test_agents.py`

- **The plan said "No other test imports from it."** In fact
  `tests/test_stack_shape_resilience.py:41` does:
  `from .test_agents import collect, make_session, mock_litellm_stream`.
  - It has been there since `72a23d8`, the 1.0.0 release.
  - The plan's survey missed it. A search for the relative form, `from .test_agents`,
    finds it.
- **It still resolves, unchanged.**
  - `test_agents.py` keeps `TestResumeSummary`, which uses all three helpers. So its
    generated header imports them from `tests._agent_helpers` (`:13`).
  - The relative import therefore gets the same three objects.
  - The file collects, and its tests pass in the suite below.
- **The petition covers this dependency.**
  - Had the header dropped any of the three, `test_stack_shape_resilience.py` would fail
    to collect, and check 1 would fail on its ids.
  - Check 4 holds the file byte-identical.
- **Re-pointing the import is not taken here.**
  - `test_stack_shape_resilience.py` now gets the helpers through a file that only
    re-exports them, not from the file that defines them.
  - The file holds two tier-B ids (`floor.json:89–90`), so re-pointing its import to
    `._agent_helpers` would be a floor-file edit. That needs §54.7's import-only petition,
    and it is outside D9's ruling.
  - It goes to the close-out stop, for a ruling: re-point it under §54.7, or leave it and
    keep this record of the dependency.
- **One docstring goes slightly stale.**
  - `tests/test_renderer_goldens.py:13`, a whole-file floor entry, names "``test_stack_*``,
    ``test_agents``" as the existing behavioural tests. The per-agent ones are now the five
    new files.
  - That is inventory §60.2's "goes stale", recorded here with its line, like the golden
    file's docstring at §23. No edit.

### 25.3 The proofs

**The move petition.** `move_check.py` (§24) ran against a `git archive` export of
`298c54b`, with the working tree as NEW:

```
collected: BASE 4225, NEW 4225
check 1 (collection): PASS
top-level nodes compared: 45
check 2 (byte-identity): PASS
floor ids rewritten old -> new: 16; NEW's floor_check: ['floor total          : 456 (expect 456)', 'FAILURES             : 0']
check 3 (the floor): PASS
other tests/ files compared: 180
check 4 (nothing else): PASS
MOVE PETITION: PASS
```

This is §24's scratch result, on the repo.

**Coverage, file by file.** The suite ran twice on the same venv:
- on the split tree;
- on the HEAD export, with `PYTHONPATH` pointing at the export's `src/`. `spec4.__file__`
  resolved there.

Both gave `4224 passed, 1 skipped` and `TOTAL 12475 808 94%`. The two term-missing tables,
97 rows each, are identical.

**No mutation.** The plan made the petition the proof of a move. No source line changed.

| Gate | Result |
|---|---|
| Ruff / format / mypy | `All checks passed!` on `src/ tests/` and on `.`; `247 files already formatted`; `Success: no issues found in 93 source files` |
| Tests | `4224 passed, 1 skipped`, exit 0: unchanged, with the same 4225 ids collected |
| Coverage | `TOTAL 12475 808 94%`: unchanged, and identical file by file |
| Floor / off-limits | tier-B `183 (expect 183)`, `456 (expect 456)`, `FAILURES: 0` |
| Goldens | `git diff` names nothing under `tests/golden`, `tests/snapshots` or `tests/test_project_manager_golden.py` |

**D9 is done.** Next is the record-only commit closing D5, D6, D8, D10, D11, D12 and D13.
After it comes Phase 8's close-out, the last stop, which takes 25.2's open question.

## 26. The record-only commit: D5, D6, D8, D10, D11, D12 and D13 closed

This is fourth in §19.1's order, and it carries the rulings' own reasons. No file under
`src/` or `tests/` changes. `pyproject.toml` changes in one comment, which D12's ruling
makes wrong as it stood.

### 26.1 The seven, closed

| D | Item | Closed as ruled | Where it lands |
|---|---|---|---|
| D5 | P31 | `persist_artifacts` keeps its name. The contract docstring names the flush, and 62 occurrences and 8 patch strings for a verb nobody has proposed is churn | Here only. P31 came from the directive, and BACKLOG never carried it |
| D6 | P8 | The step sentinel stays not taken. No step generator in the four turns split so far needed two ending causes. It reopens if one does, and the plan says how | BACKLOG 1.1's turns bullet |
| D8 | P29, P1 | `TestMockBuffers` was closed under 6f's standard, and nothing has changed. `_start_gen` and `_record_usage` stay private, since renaming them would open a Phase 1 characterization file whose job is to be untouched | BACKLOG 1.1's renames bullet, and 1.5 |
| D10 | P27, P28 | The consolidation waits in Part 2 for a structural reason; merging for tidiness is what the pruning rule forbids, by analogy. The four large files are dropped: 155–215 tests is not a problem | BACKLOG 1.5, and a new 2.6 |
| D11 | P30 | Dropped: the condition never arose | BACKLOG 1.5 |
| D12 | P25 | `tests/**` is exempt by policy, permanently: a test's magic numbers are its assertions. `evals/**` stays ignored while `evals/` is outside the gate. `scripts/**` follows D13 | BACKLOG 1.3 and a new 2.7; `pyproject.toml`'s comment |
| D13 | P26 | Ruff yes, mypy no. `ruff check .` stays the standing requirement. 230 strict-mypy errors are a lift with no consumer, and no refactor phase is planned. The three limits are documented as limits, and fixing them is Part 2's, "when next used" | BACKLOG 1.4 and 2.7; the README |

### 26.2 What landed

**`BACKLOG.md`:**
- **1.1, the renames bullet, now says all five are settled.**
  - The root-siblings inconsistency, P3, is resolved (D7a, §22).
  - P4's two names are renamed (D7b, §23).
  - `_with_readme_attribution`, P2, stays private (D7, §23), and so do `_start_gen` and
    `_record_usage`, P1 (D8).
  - This keeps §23's word that P2 and P4 close by hand here.
- **1.1, the turns bullet, now records P5–P7 as done** (8i1–8i3: §14, §16, §17), and the
  sentinel closed (D6).
  - Its "noqas deleted" was checked before it was written.
  - `grep noqa` finds none in `agents/brainstormer.py`, `agents/code_scanner/__init__.py`
    or `agents/deployer.py`.
  - At `6956aca`, `brainstormer.run` carried `# noqa: C901, PLR0912`.
- **1.3:** the split row and the PLR2004 row leave the table. A two-line note under it says
  where each went. This keeps §25's word about the split row.
- **1.4:** D13's ruling, in place of the question.
- **1.5:** the four items, each with its ruling. This section is where the fold listed the
  items that had never been ruled.
- **2.6, new: test-family consolidation** (D10). P27's sizes from §1.2, D9's three
  per-agent files, and the move petition as its proof.
- **2.7, new: the tools, and PLR2004 outside `tests/`** (D13, D12).
  - It holds the three limits and a return-side width sweep.
  - §21 said the sweep "is on the Part 2 list with the other tool work". It was not on it
    until this commit, so that sentence was ahead of the file, and it is true now.
- **Record references made explicit.** BACKLOG's convention is that a bare §N means the
  inventory, so every new reference to this record is written `PHASE8_RECORD.md` §N.

**`scripts/cleanup/README.md`:**
- **The introduction now names the fourteenth tool.** D9a (§24) added its section, but
  left the introduction saying the thirteenth "is described last".
- **The introduction also carries D13's ruling,** in place of "Whether to bring them inside
  is Phase 8's question".
- **Check 4's alias limit and the sweep's closure limit now point to BACKLOG 2.7.**
- **The harness gains its limit: a working-tree edit.** The entry gives §15's four-step
  sequence, as accepted at §16.1.

**`pyproject.toml`, one comment.**
- It said PLR2004 "is deferred in the next three entries, not exempted". D12 reverses that
  for `tests/`.
- The new comment states the policy and the current sizes.

**A size that moved: `scripts/` has 21 PLR2004 findings, not 20.** The counts are measured
with the per-file ignores lifted (`ruff check --select PLR2004 --config
'lint.per-file-ignores = {}'`):

```
tests/           230
evals/           25
scripts/         21
scripts/cleanup/ 15
```

- The new one is `move_check.py`'s, from D9a: `move_check.py:51`, `if len(problems) > 20:`, the cap on printed problems.
- `contract_check.py`, from 8g, has none.
- `tests/` and `evals/` are unchanged from §1.2.

### 26.3 Left for the close-out

**Items Phase 8 finished that BACKLOG still lists as open.** The record states each one's
closure. This commit leaves them, since they are not among its seven, and the close-out
reconciles Part 1 as a whole:
- **1.1:**
  - `revision_delta`'s copies (P10, 8d2, §7);
  - the trim written twice (P11, 8d);
  - the `sys.modules` item (P12, D4, §20).
- **1.2:**
  - the prop-bound inputs (P14, 8h);
  - the `-> Any` returns (P15, D14, §21): 14 taken, and the edges join the design limit;
  - `object` and `run_with_timeout` (P16, P17, 8b, §4);
  - `_fmt_usd`'s question (P18, 8b, §4.2).
- **1.3:**
  - the racing nine (P19, 8f);
  - the banner (P20, 8c);
  - the 31 keys (P21, 8g);
  - the five targets (P22, 8e);
  - the guards (P23, 8a and D1, §3, §19).
  - 1.3's test row from 8i stays open: it is work (§17).

**Two questions for the close-out stop, unruled:**
- **§25.2's relative import.** `test_stack_shape_resilience.py:41` takes its helpers
  through `test_agents.py`. It could be re-pointed under §54.7, or left as it is, with
  this record of the dependency.
- **`trace_diff.py` does not print step reach.** This was raised at §14.2 and never ruled
  (§18.3, item 3). D13's ruling named three limits, and this would be a fourth of the
  same kind.

### 26.4 The proofs

**Configuration unchanged.** `pyproject.toml` parses to the same data before and after
(`tomllib`):

```
tomllib: HEAD == working tree: True
```

**A side effect, recorded.**
- The first `uv run` after the comment edit rebuilt the editable `spec4` and reinstalled it
  into `.venv/`: `Building spec4 …`, `Uninstalled 1 package`, `Installed 1 package`.
- uv does that whenever `pyproject.toml` changes. `uv.lock` is unchanged, and no
  dependency moved.
- Rule 2 forbids writes under `.venv/`. This one was uv's, caused by the ruled comment
  edit, and it is named here rather than passed over.

| Gate | Result |
|---|---|
| Changed files | `BACKLOG.md`, `pyproject.toml` (the comment), `scripts/cleanup/README.md` and this record; nothing under `src/` or `tests/`. Before the record: `3 files changed, 116 insertions(+), 45 deletions(-)` |
| Ruff / format | `All checks passed!` on `src/ tests/` and on `.`; `247 files already formatted` |
| Tests, coverage, mypy | unaffected: no file under `src/` or `tests/` changed, and the configuration parses equal |
| Floor / off-limits | tier-B `183 (expect 183)`, `456 (expect 456)`, `FAILURES: 0` |

**Next is Phase 8's close-out, the last stop.** Its remeasure maps `project_manager`'s
paths as a family.
