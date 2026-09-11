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
