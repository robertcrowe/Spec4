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
