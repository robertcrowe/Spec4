# scripts/cleanup — the cleanup's mechanical checks

These are the eleven checks behind the proofs in `CLEANUP_INVENTORY.md`, the checks that
`CLEANUP_REPORT.md` §4 names as tools. Each proves one property of a change mechanically,
so that a claim like "this commit only renamed" or "this refactor changed nothing
observable" rests on an empty diff or a matching trace, not on reading.

A twelfth tool, `remeasure.py`, proves nothing about a change. It re-runs Phase 0's
measurements on two revisions, and it is described after the eleven.

**They sit outside the gate.** `uv run ruff check .` and `ruff format` cover them. mypy
(`uv run mypy src/`), pytest (`testpaths = ["tests"]`), coverage and vulture do not.
Whether to bring them inside is Phase 8's question (`CLEANUP_REPORT.md` §5.4).

## Ground rules

- **Run from the repo root,** with `uv run python`, so `spec4` is importable. The tools
  use the standard library, `spec4` and pytest, nothing else.
- **Each tool is one file, and none imports another.** deptry reads an import of a
  sibling module as a missing dependency, as it already does for `evals/`.
- **Outputs go outside the repo.** The two harnesses that write refuse an output path
  inside it.
- **Mapping files** (`MAP.json`) are `[[old, new], ...]`. The shell form of the rename
  check takes the same pairs as `old<TAB>new` lines.

## The two tools that write to `src/` and `tests/`

A harness left half-applied is a worse artifact than none, so both guard the tree.

**`mutate.py`** changes a file, runs the suite, and puts the file back.
- **It refuses to start (exit 2) unless `git status --porcelain` is empty.** The case's
  edits are then the only change on disk while the suite runs.
- **It writes nothing if any anchor fails.** Every anchor must match exactly once, and
  all of them are checked before the first write.
- **The restore runs in a `finally`.** SIGTERM and SIGHUP are turned into an exit so it
  runs for them too.
- **The restore is verified:** each file's sha256 must equal the one taken before the
  edit, and the tree must be clean again. If either fails, it exits 3.
- **The suite runs in its own process group,** and any exit kills the whole group. An
  interrupted run leaves nothing behind: no pytest, and no server a test started.

**`rename_apply.py`** keeps its change, so it has no restore to verify.
- **It refuses a dirty tree (exit 2).** The rename is then the tree's only change, and
  `git checkout -- .` undoes it exactly.
- **Every new text is computed before anything is written.**
- **Each write is read back and its sha256 compared** with the bytes intended.
- **A failed write rolls back every file already written.** The rollback is itself
  verified by sha256 and a clean tree, or the tool exits 3.

Every other tool only reads the repo. The two that need trees to compare, the rename
check and the petition, work on `git archive` copies in a temporary directory and
delete them afterwards.

## The eleven checks

### 1. Substitution (rename) check

**Proves:** a rename commit changed nothing but identifiers. Both trees are
reverse-substituted new → old, the `x as x` aliases are folded, and both are
re-formatted with ruff, so the diff is layout-blind. An empty diff means the change is
substitution alone.

```sh
uv run python scripts/cleanup/rename_apply.py . MAP.json /outside/report.json   # make the rename
uv run python scripts/cleanup/rename_check.py . BASE MAP.json [COMMIT]          # check it
source scripts/cleanup/rename_check.sh; P=BASE C=COMMIT MAP=map.tsv rename_check
```

Without `COMMIT`, the check compares against the working tree. `rename_apply.py`
leaves `tests/golden/` and `tests/snapshots/` alone. It also leaves module-path
components alone. In the seven whole-file floor entries, it rebinds imports as
`new as old` (§54.7). A whole-file entry that reaches a name any other way is reported
as BLOCKED and left untouched.

**First used:** Phase 7 pre-work (§60.2's per-name dry run). Then every rename commit,
7a–7j and 7q3.

### 2. Token check

**Proves:** every changed token run is an old → new substitution, a layout change, or a
§54.7 alias. It catches what reverse substitution folds away, such as a new name that
already existed. Anything else is printed as `OTHER`. On a seam commit its exit status
is informational (§60.6).

```sh
uv run python scripts/cleanup/forward_token_check.py . BASE MAP.json    # BASE vs working tree
```

**First used:** 7g (§67).

### 3. Check 4, in three forms and an attribute form

**Proves:** every rewritten patch target resolves to the function itself, in the module
whose code calls it. `patch_resolve.py` covers three forms: `patch("…")` path strings,
`patch.object`, and `setattr`/`monkeypatch.setattr`. `check4_attr.py` covers targets
that a function reaches as a module attribute or through an in-function import.

```sh
uv run python scripts/cleanup/patch_resolve.py . MAP.json [--side new|old] [--base REV]
uv run python scripts/cleanup/check4_attr.py . spec4.session:get_agent_gen run \
    spec4.session.brainstormer.run spec4.agentifier.agentifier.run
```

**First used:** 7g. The third form was added at 7i, and the attribute form at 7n2
(§70.11, §74).

### 4. Strip-and-compare

**Proves:** an annotation-only change is annotation-only. Annotations, PEP 695 type
parameters and `if TYPE_CHECKING:` blocks are erased from both sides, and the ASTs must
be identical. It is standing for annotation work (§60.2).

```sh
uv run python scripts/cleanup/strip_check.py BASE ROOT    # ROOT: `.` or an exported tree
```

**First used:** 7o1 (§77.1).

### 5. Inline check

**Proves:** a named magic value is that value. Each added module constant is inlined back
to its literal, and the AST must be identical to BASE's.

```sh
uv run python scripts/cleanup/inline_check.py BASE ROOT [REL_PATH...]
```

**First used:** 7p1 (§78.1).

### 6. Frozen strings

**Proves:** no prompt, status, label or display fragment appeared or disappeared (Rule
4). The set of string constants in a module, docstrings excluded, is compared.
Changes in count are listed, because a shared step can collapse duplicated labels.

```sh
uv run python scripts/cleanup/frozen_strings.py BASE [PATH]   # PATH defaults to agentifier.py
```

**First used:** 7q1 (§79.1).

### 7. Trace identity

**Proves:** a refactor changed nothing the consumer sees. `trace_identity.py`, a pytest
plugin, records every chunk delivered at the outermost generator frame, with an
insertion-ordered session snapshot at each chunk, for every test. `trace_diff.py`
requires each main-thread trace to be identical to the baseline. It classifies
worker-thread divergences:
- timing: advisory;
- content: escalated, and fails the run;
- a network reach in the nine known racing tests: recorded as a known defect.

```sh
TRACE_OUT=/outside/run.json PYTHONHASHSEED=0 PYTHONPATH=scripts/cleanup \
    uv run pytest -p trace_identity -q -p no:cacheprovider --basetemp=/outside/tmp
python scripts/cleanup/trace_diff.py BASE1.json[,BASE2.json,...] /outside/run.json [--list]
```

- **`--basetemp` must be the same** for the baseline and every run compared with it:
  `tmp_path` leaks into session values.
- **`TRACE_MODULE` and `TRACE_FAMILY`** choose what is traced. The default is the
  agentifier's eight generators and `run`.
- **`TRACE_STEPS`** names step functions whose entry is recorded.

**First used:** 7q0 (§79.0). Its worker rules were ruled at review of 7q1 and at the 7q2
stop (§79.2).

### 8. Width sweep

**Proves:** no annotation is narrower than what a test exercises. `width_sweep.py`, a
pytest plugin, records every value that reaches each annotated target during the full
suite. It checks each value against the annotation the way mypy would accept it, and
marks mock and `SimpleNamespace` stand-ins as such.

```sh
WIDTH_SWEEP_OUT=/outside/sweep.json PYTHONPATH=scripts/cleanup \
    uv run pytest -p width_sweep -q -p no:cacheprovider
```

The targets are `data/rows_7o.json`, 7o's row map, located at `4acdffd`. Override them
with `WIDTH_SWEEP_ROWS` and `WIDTH_SWEEP_BASE`.

**First used:** 7o5 (§77.9).

### 9. Floor and off-limits, in both halves

**Proves:** all 456 protected node ids still collect:
- tier A, 273: the seven whole-file entries, which collect 188, plus 85 named ids;
- tier B, 183, in 33 classes.

A change that touches the floor must pass the matching petition:
- §54.7's golden petition, for a whole-file entry: import lines alone, goldens
  byte-identical, node ids unchanged;
- §60.3's rename petition, for a tier-A or tier-B entry: the reverse diff is empty
  inside the entry, and its assertions are token-identical.

```sh
uv run python scripts/cleanup/floor_check.py [COLLECTED.txt]    # collects itself if not given
uv run python scripts/cleanup/petition_check.py . BASE MAP.json
```

**First used:** the floor at 6a (§51.5, from §50.3 and §50.5(a)); the golden petition at
6d (§54.7); the rename petition with Phase 7's renames (§60.3).

### 10. The add-only append, and its guard

**Proves:** a record section was appended byte for byte, and the prior record is an
exact prefix of the new one. `--guard` lists every hunk that deletes lines against BASE,
and fails on a deleted blank line.

```sh
python scripts/cleanup/append_section.py CLEANUP_INVENTORY.md SECTION.md
python scripts/cleanup/append_section.py --guard BASE CLEANUP_INVENTORY.md
```

**First used:** 7d (§64.10). The guard has been standing since 7e.

### 11. The mutation harness

**Proves:** a seam is pinned. One anchored mutation must make its predicted tests fail,
while the named must-pass tests pass. Every other failure is listed, to be explained
(§60.5, §60.6). A case that predicts `diverge` is judged by trace identity instead, as
7q0's probes were.

```sh
uv run python scripts/cleanup/mutate.py scripts/cleanup/data/cases_7q.json CASE
uv run python scripts/cleanup/mutate.py scripts/cleanup/data/cases_7q.json probe_A \
    --trace B1.json,B2.json,B3.json --basetemp /outside/tmp --out /outside/probe.json
```

**First used:** 7k (§71), under §60.5's harness rule. Every seam and split through 7q
used it.

## The twelfth tool: Phase 0, re-measured

**Proves:** nothing about a single change. It re-runs Phase 0's measurements
(`CLEANUP_INVENTORY.md` §1–§8) on two revisions and prints them side by side, as the
tables of `CLEANUP_REPORT.md` §7:
- the gate;
- coverage per module;
- dead code;
- dependencies;
- complexity and size;
- the import graph.

Both revisions are exported with `git archive`, so the working tree is only read. Each
measurement is taken on both with the same tool: vulture and deptry pinned to Phase 0's
versions, and the repo's ruff and mypy.

```sh
uv run python scripts/cleanup/remeasure.py 1d1dcbd 6956aca \
    --cov-base scripts/cleanup/data/coverage_1d1dcbd.txt \
    --cov-head scripts/cleanup/data/coverage_85a9cb6.txt \
    --families scripts/cleanup/data/families_phase4.json
```

- **Coverage comes from saved output** of `pytest --cov=spec4 --cov-report=term-missing`.
  `--run-coverage DIR` runs the suite in any export that has none, and saves the output
  in DIR.
- **`--families` compares split modules** as the sum of what each became.
- **Phase 8's close-out** is the same comparison against this tree:
  `remeasure.py 6956aca HEAD --cov-base scripts/cleanup/data/coverage_85a9cb6.txt
  --run-coverage /outside/dir`.
- **On `1d1dcbd` it reproduces Phase 0's recorded figures,** with one exception: vulture
  finds 70 lines where §3.1 recorded 71. The Phase 0 tree has no whitelist, so its
  whitelisted vulture cell is §3.1's 32, from the record.
- **`--run-coverage` on `1d1dcbd` re-runs Phase 0's own suite, and reproduces §1
  exactly:** 1 failed (§1.1's test), 4116 passed, 1 skipped; 11,676 statements and
  1,020 missed; every per-module row of §1.3.

**First used:** the Phase 7 close-out, for `CLEANUP_REPORT.md` §7. There it ran from
the scratchpad as `phase0_measure.py`, and the tool calls were run by hand.

## Data

| File | What it is |
|---|---|
| `data/floor.json` | The floor: the seven whole-file entries, the 85 named tier-A and ordering ids, and the 183 tier-B ids. It was derived at this commit from the Phase 6 check's data (`dnum.json` and its fixed lists), with the same selection. Verified equal: the same 188 / 85 / 183 / 456, and the petition's tier maps identical |
| `data/cases_7q.json` | 7q's ten mutation cases (§79.1–79.4) and 7q0's two probes (§79.0). Anchors are text on the tree each case was written for, and a stale anchor is refused, never approximated. `probe_B`'s anchor is 7q0's tree and matches nothing at HEAD. `7q1` still lists `test_ai_features_json_schema_complete`, a misprediction that was accepted at review of 7q1 |
| `data/coverage_1d1dcbd.txt` | Phase 0's test summary and per-module coverage, verbatim from `CLEANUP_INVENTORY.md` §1 and §1.3 |
| `data/coverage_85a9cb6.txt` | The same output at `85a9cb6`, whose `src/` and `tests/` are also `6956aca`'s. It is the base for Phase 8's comparison |
| `data/families_phase4.json` | Phase 4's splits (§16–§26): each Phase 0 module, and the modules it became |
| `data/rows_7o.json` | 7o's row map: 67 rows, 58 of them "genuinely typeable", with line numbers at `4acdffd` |

## Replayed when committed

Every check was run against a recorded result before this commit:

| Check | Run | Result, as recorded |
|---|---|---|
| Substitution check | 7q3, both forms | 97 non-substitution lines |
| Token check | 7q3, at `92941d4` | `hunks 107; old->new token substitutions 99; …; OTHER 12` |
| Check 4 | 7q3 | 4/4 |
| Check 4, attribute form | 7n2's six targets | 6/6 |
| Strip check | 7o5 against `1a2b860` | `files changed: 1; files with residue: 0` |
| Strip check | 7p2 against `ac20ced` | residue in 7 files, so the check bites |
| Inline check | 7p2 | `files changed: 20; files with residue: 0` |
| Frozen strings | against 7q0 | the eight `__all__` names 7q3 added |
| Trace identity | HEAD against 7q0's baselines | 142/142 identical, 0 escalated |
| Width sweep | 63 targets | 58 reached, 5 never reached, 0 rejected |
| Floor | HEAD | 456/456 |
| Petition | 7q3 | PASS |
| Add-only append and guard | the record | 0 deleting hunks; a blank-line run refused |
| Phase 0, re-measured | `1d1dcbd` against `6956aca` | every table in `CLEANUP_REPORT.md` §7 |

The two writers were run for real in a scratch clone:
- refusal on a dirty tree, on a stale anchor, and on an output inside the repo;
- one real mutation, `finalize_specs`: its one predicted test failed and nothing else did,
  and the restore was verified;
- a SIGTERM mid-suite: the restore was verified, and no descendant was left alive;
- probe A under the trace verdict: 13 traces diverging, all 6 predicted among them, as
  recorded in §79.0;
- 7q3's rename reversed: 13 files changed, and the rename check came back EMPTY;
- a forced write failure: 12 files rolled back, verified.
