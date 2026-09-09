# Spec4 Cleanup Inventory (Phase 0 baseline)

Recorded 2026-09-08 on branch `look-rework` at commit `1d1dcbd` ("Update to v1.5.0").
No project files were changed in this phase. The only outputs are this file and
`vulture_whitelist.py`.

Tool versions: pytest 9.0.2, ruff 0.15.12, mypy 1.20.2, vulture 2.16 (via `uvx`),
deptry 0.25.1 (via `uvx`). Nothing was added to `pyproject.toml`.

## 1. Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `1 failed, 4116 passed, 1 skipped in 166.64s` (exit 1) |
| Coverage | same run | `TOTAL 11676 stmts, 1020 miss, 91%` |

**Coverage baseline note (2026-09-08, before Phase 1).** The Phase 0.5b report quoted 96%; the baseline above says 91%. Both are correct for what they measured. The baseline run used `--cov=spec4`, which measures `src/` only (11,676 statements). The 0.5b run used the bare `--cov` from the plan's gate line, which without a `[tool.coverage]` section in `pyproject.toml` measures every imported module, `tests/` included (37,176 statements, of which the test files are near 100% and lift the total). Not stale `.coverage` data and no config change. **The number Rule 6 ratchets against is the `--cov=spec4` figure: 91% at Phase 0.** Re-measured with `--cov=spec4` after 0.5c and the Bug 4 fix: `TOTAL 11684 stmts, 1023 miss, 91%` (4118 passed, 1 skipped), so Phase 1 starts from 91%. Always run the gate as `uv run pytest --cov=spec4 --cov-report=term-missing -q`.
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `130 files would be reformatted, 50 files already formatted` (exit 1); 41 of the 130 are under `src/` |
| Mypy | `uv run mypy src/` (strict per pyproject) | `Found 30 errors in 13 files (checked 60 source files)` (exit 1) |

Notes:

- 4118 tests collected (4116 + 1 + 1). The static count of `def test_*` functions is 3538; parametrization accounts for the difference.
- The one skip is `tests/test_session.py:725` ("Designer has no chat turn"). The three browser E2E modules under `tests/integration/` did run (a browser was available).
- `ruff format --check` fails at baseline. Per the memory note and the plan's Rule 6, `ruff format` is **not** to be run during cleanup; the gate for later phases is "no new files would be reformatted", not "0 files". The baseline list of 130 files is reproducible with the command above.
- Mypy fails at baseline with 30 errors. Rule 6 says "mypy (strict)" must pass; since it does not pass now, the Phase 1+ gate is "≤ 30 errors, no new files". The 30 are listed in §1.2.

### 1.1 Failing test (pre-existing, not fixed)

`tests/integration/test_chat_frame_e2e.py::TestTheRenderedFrame::test_no_transcript_block_is_filled`

```
>       assert set(backgrounds) == {"rgba(0, 0, 0, 0)"}
E       AssertionError: assert {'rgb(18, 18,...(0, 0, 0, 0)'} == {'rgba(0, 0, 0, 0)'}
E         Extra items in the left set:
E         'rgb(18, 18, 26)'
```

Deterministic: fails again when the file is run alone (`1 failed, 21 passed in 21.07s`).
`rgb(18, 18, 26)` is `#12121a`, which appears in `src/spec4/app_constants.py:88` (the dark theme palette). Some `.chat-msg` elements on `/chat` now resolve to a filled background. This is either an intended look change on `look-rework` that the test was not updated for, or a regression; either way it is out of scope for the cleanup. See *Bugs found (not fixed)*, §10.

### 1.2 Mypy errors at baseline (30)

| File | Count |
|---|---:|
| `src/spec4/agentifier/agentifier.py` | 8 |
| `src/spec4/project_manager.py` | 6 |
| `src/spec4/agents/deployer.py` | 3 |
| `src/spec4/callbacks/designer.py` | 2 |
| `src/spec4/agents/brainstormer.py` | 2 |
| `src/spec4/agentifier/cross_cutting_analyst.py` | 2 |
| `src/spec4/version_check.py`, `layouts/designer.py`, `agents/stack_advisor.py`, `agents/phaser.py`, `agents/_utils.py`, `agents/_manifest.py`, `agentifier/reference_verifier.py` | 1 each |

```
src/spec4/version_check.py:82: error: Returning Any from function declared to return "dict[str, str] | None"  [no-any-return]
src/spec4/project_manager.py:323: error: Returning Any from function declared to return "dict[str, Any] | None"  [no-any-return]
src/spec4/project_manager.py:407: error: Item "None" of "dict[str, Any] | None" has no attribute "get"  [union-attr]
src/spec4/project_manager.py:1894: error: Unsupported operand types for > ("float" and "None")  [operator]
src/spec4/project_manager.py:1894: error: Unsupported operand types for < ("float" and "None")  [operator]
src/spec4/project_manager.py:1894: error: Unsupported left operand type for > ("None")  [operator]
src/spec4/project_manager.py:1903: error: Unsupported operand types for >= ("float" and "None")  [operator]
src/spec4/agents/_utils.py:803: error: Argument 1 to "join" of "str" has incompatible type "list[Any | str | None]"; expected "Iterable[str]"  [arg-type]
src/spec4/agentifier/reference_verifier.py:63: error: Returning Any from function declared to return "str | None"  [no-any-return]
src/spec4/agents/stack_advisor.py:1244: error: Argument 2 to "get_version_dir" has incompatible type "int | None"; expected "int"  [arg-type]
src/spec4/agents/deployer.py:654: error: Argument 1 to "load_deployment_plan" has incompatible type "Any | None"; expected "str | Path"  [arg-type]
src/spec4/agents/deployer.py:685: error: Argument 1 to "load_prior_deployment_plan" has incompatible type "Any | None"; expected "str | Path"  [arg-type]
src/spec4/agents/deployer.py:711: error: Argument 1 to "build_revision_note" has incompatible type "dict[str, Any] | None"; expected "dict[str, Any]"  [arg-type]
src/spec4/agents/_manifest.py:130: error: Argument 1 to "get" of "dict" has incompatible type "Any | None"; expected "str"  [arg-type]
src/spec4/agents/brainstormer.py:822: error: Argument 1 to "resolve_phase_version" has incompatible type "Any | None"; expected "str | Path"  [arg-type]
src/spec4/agents/brainstormer.py:824: error: Argument 1 to "latest_implemented_version" has incompatible type "Any | None"; expected "str | Path"  [arg-type]
src/spec4/agents/phaser.py:1085: error: Argument 1 to "build_revision_note" has incompatible type "dict[str, Any] | None"; expected "dict[str, Any]"  [arg-type]
src/spec4/agentifier/cross_cutting_analyst.py:36: error: Argument 1 to "get" of "dict" has incompatible type "Any | None"; expected "str"  [arg-type]
src/spec4/agentifier/cross_cutting_analyst.py:42: error: Argument 1 to "get" of "dict" has incompatible type "Any | None"; expected "str"  [arg-type]
src/spec4/agentifier/agentifier.py:319: error: Returning Any from function declared to return "ScoutOutput"  [no-any-return]
src/spec4/agentifier/agentifier.py:360: error: Function is missing a return type annotation  [no-untyped-def]
src/spec4/agentifier/agentifier.py:389: error: Returning Any from function declared to return "ComposerOutput"  [no-any-return]
src/spec4/agentifier/agentifier.py:392: error: Function is missing a return type annotation  [no-untyped-def]
src/spec4/agentifier/agentifier.py:506: error: Returning Any from function declared to return "TierAnalystOutput"  [no-any-return]
src/spec4/agentifier/agentifier.py:2262: error: Name "topics" already defined on line 2221  [no-redef]
src/spec4/agentifier/agentifier.py:2694: error: Argument 1 to "load_prior_ai_features" has incompatible type "Any | None"; expected "str | Path"  [arg-type]
src/spec4/agentifier/agentifier.py:2702: error: Argument 1 to "resolve_phase_version" has incompatible type "Any | None"; expected "str | Path"  [arg-type]
src/spec4/layouts/designer.py:641: error: Argument 1 to "active_version" has incompatible type "str | None"; expected "str | Path"  [arg-type]
src/spec4/callbacks/designer.py:168: error: Returning Any from function declared to return "str | None"  [no-any-return]
src/spec4/callbacks/designer.py:173: error: Returning Any from function declared to return "str | None"  [no-any-return]
```

By category: `arg-type` 15 (almost all `Any | None` passed where `str | Path` or `dict` is required), `no-any-return` 7, `operator` 4 (`project_manager.py:1894/1903`, `float` vs `None`), `union-attr` 1, `no-untyped-def` 2, `no-redef` 1 (`agentifier.py:2262`, `topics` defined twice).

### 1.3 Coverage per module

```
Name                                            Stmts   Miss  Cover   Missing
-----------------------------------------------------------------------------
src/spec4/__init__.py                               5      2    60%   5-6
src/spec4/agentifier/__init__.py                    0      0   100%
src/spec4/agentifier/agentifier.py               1413    165    88%   310-319, 328-330, 400-408, 417-429, 445-478, 496-506, 758, 791, 795-796, 824-832, 836-839, 1151, 1159-1160, 1219-1223, 1254-1255, 1388-1395, 1552, 1659-1667, 1671, 1718-1720, 1727, 1752, 1771, 1818, 1909-1920, 1994, 2125-2134, 2205-2210, 2230-2260, 2323-2328, 2372, 2390, 2569, 2766, 2834, 2892, 2905-2911, 2961-2968, 2985, 3008, 3032, 3099-3103, 3128-3140, 3151, 3195-3197, 3415, 3428-3429, 3464, 3487, 3501
src/spec4/agentifier/composer.py                  126      3    98%   141, 236, 294
src/spec4/agentifier/cross_cutting_analyst.py     118      1    99%   261
src/spec4/agentifier/grounding.py                  85      3    96%   75, 99, 122
src/spec4/agentifier/infra_expander.py             42      0   100%
src/spec4/agentifier/linker.py                    156      0   100%
src/spec4/agentifier/panel_closure.py              53      2    96%   123-124
src/spec4/agentifier/pattern_loader.py            162     18    89%   132, 143, 170, 185, 194, 202, 230, 245, 254, 260, 267, 289, 295, 326, 358, 407-408, 412
src/spec4/agentifier/prioritizer.py               178      3    98%   230, 238, 491
src/spec4/agentifier/reference_verifier.py         36      0   100%
src/spec4/agentifier/requires_reconciler.py       247     11    96%   126, 162, 174, 180, 195, 235, 241, 246, 251, 344, 464
src/spec4/agentifier/scout.py                     136      0   100%
src/spec4/agentifier/spec_drafter.py              101      1    99%   320
src/spec4/agentifier/subagents.py                  73      1    99%   224
src/spec4/agentifier/tier_analyst.py              131      3    98%   233, 257, 379
src/spec4/agents/__init__.py                        0      0   100%
src/spec4/agents/_code_review_schema.py            28      0   100%
src/spec4/agents/_image_probe.py                   16      0   100%
src/spec4/agents/_manifest.py                     119      6    95%   64, 69-71, 127, 209
src/spec4/agents/_phase_coverage.py               132      2    98%   136, 338
src/spec4/agents/_phase_schema.py                  27      2    93%   165, 169
src/spec4/agents/_seam_check.py                   173     11    94%   144, 225, 336, 397, 476, 490-497, 503
src/spec4/agents/_tool_probe.py                    16      0   100%
src/spec4/agents/_utils.py                       1092     71    93%   82, 85-87, 118-120, 125-127, 132-137, 139-149, 151-166, 246, 440, 514, 544-552, 555, 675, 678, 697-703, 773, 777, 783, 788, 809, 813, 817, 1104, 1134-1136, 1139-1141, 1197, 1474, 1701, 1814, 1911, 1949, 2027, 2121, 2134, 2205, 2386, 2460, 2474
src/spec4/agents/brainstormer.py                  279     26    91%   313, 490-491, 500, 522, 526-529, 540-543, 561-567, 647-648, 762-763, 844-849
src/spec4/agents/code_scanner.py                  622     68    89%   154-155, 193, 208, 235, 238-239, 263-264, 284, 291, 313-314, 997-998, 1004, 1017, 1023, 1028, 1042-1045, 1051, 1062, 1073-1080, 1107, 1117, 1129, 1145, 1166, 1181, 1209, 1261, 1266-1267, 1289-1290, 1293, 1321-1325, 1353-1354, 1386-1387, 1406, 1418, 1420, 1427-1428, 1434-1437, 1452, 1457-1460
src/spec4/agents/deployer.py                      195      3    98%   376, 591-592
src/spec4/agents/designer.py                      252     31    88%   243-244, 525-526, 570, 572, 597-598, 616-626, 634-660
src/spec4/agents/feature_speccer.py               224      6    97%   47, 296, 436-437, 516, 541
src/spec4/agents/phaser.py                        301      8    97%   943-944, 1154, 1181, 1272, 1317, 1371, 1387
src/spec4/agents/stack_advisor.py                 399     35    91%   769, 775, 826, 874, 891, 901-903, 924, 940-941, 958-959, 976-977, 983-984, 1000-1001, 1020, 1027-1028, 1031-1032, 1077-1078, 1081-1082, 1095, 1111-1113, 1122, 1139, 1177-1178
src/spec4/app.py                                   72      8    89%   461-468, 472
src/spec4/app_constants.py                         23      0   100%
src/spec4/callbacks/__init__.py                   681    157    77%   77, 655, 669-670, 681-684, 695-700, 710-712, 723-731, 751, 769, 772, 813-821, 837-839, 850, 908, 954-956, 1104, 1141, 1143, 1317, 1338, 1395, 1454-1456, 1480, 1552, 1696-1702, 1714-1726, 1844-1873, 1910, 1952, 1974-1976, 1982, 1993, 2013, 2086, 2150-2152, 2173-2175, 2186-2188, 2199-2201, 2212-2214, 2224-2226, 2235, 2241-2254, 2264-2266, 2276-2278, 2288-2290, 2300-2302, 2312-2314, 2428-2430, 2441-2449, 2459-2466
src/spec4/callbacks/designer.py                   427    113    74%   171-173, 191-199, 304, 316, 318, 333, 340, 365-366, 444, 468, 470, 475, 486, 500-502, 506-507, 526-528, 539-541, 559, 629-631, 642-649, 659-668, 689-721, 777, 803, 857, 866-867, 898-918, 930-932, 959, 990-992, 1022-1024, 1034-1036, 1052, 1076, 1079, 1111, 1193-1224, 1255, 1337, 1365
src/spec4/design_manifest.py                       80      0   100%
src/spec4/feature_specs.py                        339     83    76%   167, 178, 182, 194, 198, 218, 223, 262, 266, 269, 284, 296, 318-319, 331, 335, 338, 361, 365, 368, 385-411, 415-446, 509, 512, 562, 592
src/spec4/layouts/__init__.py                      70      7    90%   137-138, 327, 329, 331, 375, 421
src/spec4/layouts/_agent_rows.py                   86      3    97%   203, 224, 231
src/spec4/layouts/_artifact_view.py               196      7    96%   589, 773-778
src/spec4/layouts/_chat.py                        181      2    99%   222, 307
src/spec4/layouts/_llm_gate.py                     55      0   100%
src/spec4/layouts/_round_cost.py                   70      0   100%
src/spec4/layouts/_round_tree.py                  113      0   100%
src/spec4/layouts/_setup.py                        70      2    97%   373, 375
src/spec4/layouts/_shared.py                       83      0   100%
src/spec4/layouts/_status_bar.py                   45      0   100%
src/spec4/layouts/designer.py                     158     12    92%   342, 670-685, 687-688, 693
src/spec4/llm.py                                  342     17    95%   309, 335, 355, 390, 490-491, 564-569, 656, 962-963, 973, 980
src/spec4/llm_selection.py                        101      0   100%
src/spec4/project_manager.py                      758     30    96%   147-148, 209-210, 321, 575, 603, 605, 697, 758, 850-851, 891, 912, 972-973, 1028-1029, 1056-1057, 1094-1095, 1151-1152, 1435-1436, 1547, 1583-1584, 1881
src/spec4/providers.py                             87     15    83%   80, 105-108, 124-128, 171-174, 212-223, 236
src/spec4/session.py                              185     34    82%   211-222, 298-299, 301-303, 309-316, 320-321, 327, 449-452, 484, 491-505, 609
src/spec4/stack_routing.py                        101      2    98%   116, 178
src/spec4/streaming.py                            192     20    90%   26-27, 31-34, 87, 93, 111, 175-176, 196, 235, 244, 254-260, 270, 310-311
src/spec4/usage_report.py                          93      7    92%   30, 35, 39, 52, 63, 129, 178
src/spec4/version_check.py                         42      0   100%
src/spec4/websearch.py                             89     19    79%   179-184, 188-206
-----------------------------------------------------------------------------
TOTAL                                           11676   1020    91%
```

Lowest-covered modules (the Phase 1 targets): `callbacks/designer.py` 74%, `feature_specs.py` 76%, `callbacks/__init__.py` 77%, `websearch.py` 79%, `session.py` 82%, `providers.py` 83%. Everything under `layouts/` is already ≥ 90%. `tests/README.md` claims `app.py`/`layouts`/`callbacks`/`streaming` are at 0%; that is stale (see §9).

**Phase 1+ floor:** non-UI modules may not drop below the per-module figures above.

## 2. File-size table

Lines, top-level and nested function count, class count, and the longest function (by line span) per file. Generated with `ast`; files under `__pycache__` excluded.

### src/spec4  (60 files, 36535 lines)
| File | Lines | Functions | Classes | Longest function (lines) |
|---|---:|---:|---:|---|
| `src/spec4/agentifier/agentifier.py` | 3501 | 67 | 1 | `_run_catalog_phase (659)` |
| `src/spec4/agents/_utils.py` | 2514 | 50 | 0 | `_stack_for_deployer (181)` |
| `src/spec4/callbacks/__init__.py` | 2466 | 78 | 0 | `on_stream_poll (132)` |
| `src/spec4/project_manager.py` | 1905 | 68 | 1 | `_phase_spec_preamble (189)` |
| `src/spec4/agents/code_scanner.py` | 1718 | 27 | 0 | `run (195)` |
| `src/spec4/agents/stack_advisor.py` | 1409 | 15 | 0 | `_format_stack_as_text (232)` |
| `src/spec4/agents/phaser.py` | 1388 | 11 | 0 | `run (499)` |
| `src/spec4/callbacks/designer.py` | 1371 | 33 | 0 | `_start_gen (194)` |
| `src/spec4/layouts/_chat.py` | 1014 | 14 | 0 | `_chat_action_buttons (221)` |
| `src/spec4/llm.py` | 997 | 28 | 0 | `stream_turn (189)` |
| `src/spec4/layouts/_artifact_view.py` | 932 | 28 | 2 | `resolve_artifact (91)` |
| `src/spec4/agents/deployer.py` | 885 | 5 | 0 | `run (343)` |
| `src/spec4/agents/brainstormer.py` | 861 | 13 | 0 | `run (236)` |
| `src/spec4/layouts/designer.py` | 766 | 22 | 0 | `designer_layout (147)` |
| `src/spec4/agents/designer.py` | 674 | 13 | 1 | `generate_mock_streaming (139)` |
| `src/spec4/session.py` | 660 | 11 | 1 | `_default_session (136)` |
| `src/spec4/feature_specs.py` | 617 | 24 | 0 | `_render_graph_lines (45)` |
| `src/spec4/agents/_code_review_schema.py` | 563 | 2 | 0 | `format_validation_errors_for_retry (31)` |
| `src/spec4/layouts/_round_tree.py` | 560 | 13 | 3 | `_line_children (51)` |
| `src/spec4/agentifier/scout.py` | 543 | 6 | 5 | `run (48)` |
| `src/spec4/agents/feature_speccer.py` | 541 | 17 | 0 | `_reconcile_dependencies (46)` |
| `src/spec4/agentifier/requires_reconciler.py` | 515 | 18 | 0 | `reconcile_requires (95)` |
| `src/spec4/agents/_seam_check.py` | 504 | 12 | 1 | `_check_declaration_alignment (84)` |
| `src/spec4/agentifier/prioritizer.py` | 497 | 11 | 4 | `_format_features_block (59)` |
| `src/spec4/app.py` | 472 | 3 | 0 | `render_page (45)` |
| `src/spec4/layouts/_setup.py` | 471 | 11 | 0 | `_setup_search_layout (76)` |
| `src/spec4/layouts/__init__.py` | 444 | 3 | 0 | `_agent_select_layout (144)` |
| `src/spec4/layouts/_agent_rows.py` | 440 | 12 | 3 | `agent_rows (37)` |
| `src/spec4/agentifier/pattern_loader.py` | 415 | 10 | 4 | `_validate_frontmatter (75)` |
| `src/spec4/agentifier/tier_analyst.py` | 401 | 6 | 3 | `run (83)` |
| `src/spec4/llm_selection.py` | 399 | 12 | 0 | `default_provider_model (47)` |
| `src/spec4/agentifier/linker.py` | 393 | 8 | 5 | `_normalize_edges (69)` |
| `src/spec4/agentifier/spec_drafter.py` | 389 | 5 | 2 | `_build_system_prompt (107)` |
| `src/spec4/agents/_phase_coverage.py` | 347 | 6 | 0 | `check_phase_coverage (172)` |
| `src/spec4/layouts/_status_bar.py` | 340 | 6 | 0 | `_status_bar (86)` |
| `src/spec4/layouts/_round_cost.py` | 340 | 9 | 3 | `run_cost_lines (33)` |
| `src/spec4/layouts/_shared.py` | 320 | 13 | 1 | `step_row (38)` |
| `src/spec4/agentifier/cross_cutting_analyst.py` | 318 | 11 | 2 | `_build_system_prompt (46)` |
| `src/spec4/streaming.py` | 311 | 15 | 0 | `start (67)` |
| `src/spec4/agentifier/composer.py` | 302 | 5 | 4 | `run (105)` |
| `src/spec4/layouts/_llm_gate.py` | 289 | 9 | 0 | `_pick_card (80)` |
| `src/spec4/agentifier/subagents.py` | 274 | 13 | 6 | `stream (22)` |
| `src/spec4/stack_routing.py` | 267 | 10 | 0 | `nfr_threads (61)` |
| `src/spec4/providers.py` | 236 | 7 | 0 | `_fetch_models (113)` |
| `src/spec4/websearch.py` | 232 | 12 | 1 | `_call_search_async (20)` |
| `src/spec4/agents/_manifest.py` | 232 | 6 | 0 | `validate_manifest (88)` |
| `src/spec4/agents/_phase_schema.py` | 201 | 2 | 0 | `format_validation_errors_for_retry (57)` |
| `src/spec4/design_manifest.py` | 186 | 8 | 0 | `surface_detail_lines (39)` |
| `src/spec4/usage_report.py` | 178 | 7 | 0 | `render_usage_table (45)` |
| `src/spec4/agentifier/infra_expander.py` | 166 | 4 | 0 | `expand_infrastructure (57)` |
| `src/spec4/agentifier/grounding.py` | 159 | 4 | 0 | `render_grounding_for_prompt (58)` |
| `src/spec4/agentifier/panel_closure.py` | 157 | 3 | 1 | `close_selection (66)` |
| `src/spec4/app_constants.py` | 152 | 0 | 0 | `-` |
| `src/spec4/agentifier/reference_verifier.py` | 103 | 4 | 0 | `lookup_reference_url (31)` |
| `src/spec4/version_check.py` | 88 | 5 | 0 | `is_outdated (14)` |
| `src/spec4/agents/_tool_probe.py` | 50 | 1 | 0 | `probe_tool_support (27)` |
| `src/spec4/agents/_image_probe.py` | 48 | 1 | 0 | `probe_image_support (38)` |
| `src/spec4/agentifier/__init__.py` | 7 | 0 | 0 | `-` |
| `src/spec4/__init__.py` | 6 | 0 | 0 | `-` |
| `src/spec4/agents/__init__.py` | 1 | 0 | 0 | `-` |

### tests  (120 files, 53708 lines)
| File | Lines | Functions | Classes | Longest function (lines) |
|---|---:|---:|---:|---|
| `tests/test_agents.py` | 5284 | 333 | 36 | `test_full_realistic_review_passes (121)` |
| `tests/test_designer.py` | 2351 | 198 | 33 | `test_saves_into_session_pinned_version_dir (40)` |
| `tests/test_artifact_view.py` | 2179 | 205 | 25 | `test_the_two_pres_take_their_metrics_from_one_css_rule (27)` |
| `tests/test_agent_llm_selection.py` | 1714 | 181 | 35 | `test_setup_flow_leaves_overrides_intact (28)` |
| `tests/test_usage_capture.py` | 1494 | 103 | 16 | `test_prior_session_file_is_extended_by_a_real_turn_on_another_model (57)` |
| `tests/test_project_manager.py` | 1261 | 136 | 18 | `_context (52)` |
| `tests/test_round_tree.py` | 1116 | 88 | 14 | `test_every_line_in_the_view_is_a_link (27)` |
| `tests/agentifier/test_agentifier_orchestrator.py` | 1099 | 84 | 12 | `test_cleans_orphan_trailing_user_and_re_runs_sub_agents (31)` |
| `tests/test_callback_co_presence.py` | 1017 | 53 | 8 | `_phase_screens (210)` |
| `tests/test_agent_rows.py` | 972 | 76 | 10 | `two_state_project (20)` |
| `tests/test_status_bar.py` | 916 | 83 | 8 | `test_connect_is_where_the_old_connection_ends (31)` |
| `tests/test_llm.py` | 916 | 82 | 12 | `test_response_format_keeps_tools_when_history_has_tool_use (41)` |
| `tests/agentifier/test_try_again.py` | 851 | 59 | 9 | `test_revision_block_is_re_derived_from_disk (33)` |
| `tests/agentifier/test_prioritizer.py` | 849 | 104 | 14 | `test_prompt_carries_edges_and_carried_context (21)` |
| `tests/test_setup_wizard_register.py` | 808 | 65 | 9 | `_wizard_callbacks (31)` |
| `tests/test_session.py` | 775 | 68 | 7 | `test_clears_previous_project_state (39)` |
| `tests/agentifier/test_streaming_e2e.py` | 739 | 58 | 8 | `test_full_pipeline_reaches_complete_state (33)` |
| `tests/test_designer_wizard_register.py` | 694 | 57 | 7 | `test_the_row_comes_from_the_shared_renderer (25)` |
| `tests/test_callbacks_stream_poll.py` | 677 | 53 | 11 | `test_two_done_polls_return_identical_terminal_store (23)` |
| `tests/test_cost_summary.py` | 674 | 43 | 8 | `test_the_figure_is_the_agent_s_own_rollup (27)` |
| `tests/test_stream_error_recovery.py` | 662 | 59 | 8 | `_choose (25)` |
| `tests/test_code_scanner_progress.py` | 638 | 60 | 7 | `test_total_climbs_through_the_retry_drain (38)` |
| `tests/test_stack_persistence_block.py` | 625 | 56 | 0 | `test_exemplar_nfr_ids_are_domain_loaded (24)` |
| `tests/integration/test_chat_frame_e2e.py` | 620 | 36 | 6 | `finished_project (35)` |
| `tests/agentifier/test_scout.py` | 563 | 53 | 9 | `test_edges_are_not_parsed_from_scout_output (20)` |
| `tests/test_root_routing.py` | 540 | 48 | 7 | `_picker_path (25)` |
| `tests/test_round_cost.py` | 539 | 42 | 7 | `_partly_unpriced (20)` |
| `tests/agentifier/test_cross_cutting_analyst.py` | 529 | 58 | 7 | `test_prior_decision_in_user_message_when_set (28)` |
| `tests/integration/test_artifact_view_e2e.py` | 525 | 42 | 7 | `page (32)` |
| `tests/agentifier/test_tier_analyst.py` | 521 | 37 | 6 | `test_framing_rules_present (28)` |
| `tests/test_completion_helpers.py` | 520 | 47 | 5 | `test_cross_cutting_analyst_passes_agent_name (35)` |
| `tests/integration/test_pipeline_brownfield.py` | 520 | 30 | 6 | `test_tier_analyst_user_message_includes_ai_hint (38)` |
| `tests/test_phase_coverage.py` | 505 | 45 | 7 | `_catalog (38)` |
| `tests/test_entry_screens.py` | 497 | 29 | 6 | `test_the_subdirectories_are_one_per_line (30)` |
| `tests/agentifier/test_spec_drafter.py` | 496 | 59 | 5 | `test_passes_tier_to_system_prompt (25)` |
| `tests/agentifier/test_ff_sweep.py` | 471 | 37 | 4 | `_spec_session (19)` |
| `tests/agentifier/test_search_level.py` | 460 | 34 | 5 | `_run_finalize (31)` |
| `tests/test_chat_pill_bar.py` | 436 | 30 | 6 | `test_the_whole_row_is_unchanged_prop_for_prop (43)` |
| `tests/test_seam_check.py` | 433 | 41 | 8 | `test_capability_in_capabilities_array_is_aligned (22)` |
| `tests/test_stack_ai_features_context.py` | 425 | 38 | 0 | `test_feature_surfaces_tool_access_detail (22)` |
| `tests/agentifier/test_revision.py` | 415 | 31 | 7 | `test_zero_new_candidates_finalises_carried_forward (30)` |
| `tests/test_stack_exemplar_demonstrates_linkage.py` | 406 | 19 | 0 | `_demonstrated (23)` |
| `tests/test_stream_status.py` | 405 | 26 | 4 | `test_search_round_trip_publishes_both_statuses (49)` |
| `tests/test_visual_register.py` | 401 | 23 | 4 | `_progress_calls (22)` |
| `tests/test_project_mode.py` | 393 | 45 | 8 | `test_new_project_still_sees_a_saved_spec4_mock (18)` |
| `tests/integration/test_pipeline_greenfield.py` | 387 | 23 | 4 | `test_ai_features_json_schema_complete (30)` |
| `tests/test_chat_open_links.py` | 382 | 32 | 7 | `test_both_doors_write_the_same_two_keys (13)` |
| `tests/test_feature_speccer_generative.py` | 377 | 26 | 8 | `test_enriches_scaffold_fields (50)` |
| `tests/test_feature_specs.py` | 366 | 31 | 6 | `_rag_feature (73)` |
| `tests/test_chat_transcript_blocks.py` | 363 | 36 | 6 | `test_it_is_the_only_animation_in_the_chat_frame_s_rules (24)` |
| `tests/agentifier/test_vision_grounding.py` | 361 | 40 | 7 | `_product_spec (17)` |
| `tests/test_streaming.py` | 347 | 23 | 21 | `test_shows_message_and_code_without_retry_bullet (25)` |
| `tests/agentifier/test_edge_persistence.py` | 328 | 27 | 5 | `_c (16)` |
| `tests/test_utils.py` | 310 | 22 | 4 | `_surface (34)` |
| `tests/integration/test_page_slot_e2e.py` | 306 | 12 | 2 | `test_the_frame_is_still_there (35)` |
| `tests/test_agent_pill_click.py` | 298 | 19 | 5 | `test_every_enabled_button_navigates (30)` |
| `tests/agentifier/test_requires_reconciler.py` | 297 | 14 | 0 | `test_s2_production_map_drives_flip_with_feature_specs (38)` |
| `tests/test_stack_additions.py` | 294 | 21 | 0 | `test_merged_keyed_addition_routes_instead_of_stapling (32)` |
| `tests/agentifier/test_linker.py` | 294 | 28 | 5 | `test_exposes_linked_vision_features (17)` |
| `tests/test_phaser_seed_inputs.py` | 293 | 18 | 0 | `test_retry_drain_publishes_cumulative_received_count (42)` |
| `tests/agentifier/test_panel_closure.py` | 292 | 28 | 6 | `_candidate (15)` |
| `tests/agentifier/test_composer.py` | 283 | 21 | 4 | `_c (17)` |
| `tests/test_chat_action_row_emphasis.py` | 282 | 14 | 2 | `_rows (65)` |
| `tests/test_websearch.py` | 271 | 40 | 7 | `_turn (25)` |
| `tests/agentifier/test_subagents.py` | 265 | 36 | 13 | `test_pre_wrapped_subagent_error_passes_through_unchanged (19)` |
| `tests/test_agent_button_state.py` | 257 | 19 | 0 | `test_equal_upstream_mtimes_are_in_order (16)` |
| `tests/test_stack_feature_specs_context.py` | 255 | 22 | 0 | `_catalog (19)` |
| `tests/agentifier/test_linker_edges.py` | 245 | 25 | 4 | `_candidate (15)` |
| `tests/test_manifest.py` | 242 | 20 | 4 | `test_pins_feature_ids_via_vision_map (45)` |
| `tests/test_deployer_stack_digest.py` | 241 | 18 | 0 | `_stack (37)` |
| `tests/test_agentifier_chars_counter.py` | 239 | 22 | 3 | `test_counter_component_is_a_text_node (20)` |
| `tests/test_stack_shape_resilience.py` | 227 | 19 | 0 | `test_keyed_libraries_fold_into_the_flat_list (15)` |
| `tests/test_version_check.py` | 221 | 23 | 5 | `_ids (17)` |
| `tests/test_fast_forward.py` | 221 | 22 | 5 | `test_modal_text_names_agent_and_explains_review (17)` |
| `tests/agentifier/test_chars_counter_seed.py` | 218 | 10 | 3 | `test_counter_climbs_across_candidate_drains_without_dipping (51)` |
| `tests/test_stack_routing.py` | 215 | 19 | 5 | `test_served_claim_targets_served_ids (17)` |
| `tests/test_providers.py` | 212 | 20 | 2 | `test_bedrock_includes_on_demand_models (20)` |
| `tests/test_step_row.py` | 209 | 27 | 5 | `_entries (9)` |
| `tests/test_setup_search_provider.py` | 206 | 22 | 4 | `_connect (16)` |
| `tests/test_stack_output_rendering.py` | 204 | 16 | 0 | `test_providers_block_renders (26)` |
| `tests/test_brainstormer_chars_counter.py` | 204 | 20 | 4 | `test_completion_buttons_survive (22)` |
| `tests/test_feature_specs_pass.py` | 203 | 18 | 4 | `test_scaffold_shape (19)` |
| `tests/test_phaser_feature_specs_context.py` | 202 | 18 | 0 | `test_every_feature_renders_with_id_and_behavioural_fields (16)` |
| `tests/test_stack_render_totality.py` | 193 | 15 | 0 | `_garbled_stack (19)` |
| `tests/test_dependency_reconciliation.py` | 189 | 13 | 4 | `test_build_corrects_inverted_edge (26)` |
| `tests/test_deployer_ai_channel.py` | 186 | 18 | 0 | `test_provider_renders_model_family_role_and_tiers (14)` |
| `tests/test_phaser_stack_digest.py` | 182 | 15 | 0 | `test_serves_features_backlinks_group_entries_by_feature (20)` |
| `tests/agentifier/test_infra_expander.py` | 180 | 19 | 6 | `test_shared_components_collapse_by_id (12)` |
| `tests/test_feature_ids.py` | 179 | 18 | 3 | `test_completion_hook_stamps_ids (14)` |
| `tests/agentifier/test_infra_registry.py` | 179 | 12 | 3 | `_tier_fm (15)` |
| `tests/agentifier/test_reference_verifier.py` | 173 | 22 | 4 | `test_preserves_list_length (10)` |
| `tests/agentifier/test_reselection.py` | 165 | 11 | 4 | `test_opens_reselection_panel_with_prechecks (28)` |
| `tests/test_revision_change_classification.py` | 162 | 16 | 0 | `test_reentry_path_is_also_reconciled (20)` |
| `tests/test_vision_disk_reconciliation.py` | 161 | 14 | 3 | `test_stale_session_no_disk_is_greenfield (15)` |
| `tests/test_deployer_chars_counter.py` | 160 | 16 | 3 | `_run (20)` |
| `tests/test_deployer_phases_context.py` | 152 | 13 | 0 | `_phase (13)` |
| `tests/test_stack_advisor_token_counter.py` | 149 | 17 | 2 | `test_counter_climbs_during_suppression (15)` |
| `tests/agentifier/test_pattern_loader.py` | 145 | 17 | 3 | `test_tier_order_matches_ladder (9)` |
| `tests/test_deployer_nfr_channel.py` | 139 | 13 | 0 | `test_claimed_goal_names_its_claiming_entries (12)` |
| `tests/test_design_manifest.py` | 138 | 11 | 3 | `test_detail_lines_carry_build_facing_fields (20)` |
| `tests/test_stack_design_manifest_context.py` | 133 | 11 | 0 | `_manifest (24)` |
| `tests/test_phaser_manifest_context.py` | 127 | 9 | 0 | `test_feature_surface_line_carries_both_join_keys (22)` |
| `tests/test_app_constants.py` | 126 | 26 | 4 | `test_all_phases_covered (10)` |
| `tests/test_stale_ai_features.py` | 114 | 11 | 0 | `test_stale_mock_allows_stack_advisor (12)` |
| `tests/test_deployer_env_and_semantics.py` | 113 | 16 | 4 | `test_frontend_and_api_are_named_as_two_surfaces (5)` |
| `tests/test_deployer_invariants.py` | 110 | 10 | 3 | `test_editing_feature_specs_marks_the_plan_stale (17)` |
| `tests/test_deployer_nfr_guidance.py` | 109 | 16 | 5 | `test_notes_spec_asks_for_the_goal_record (5)` |
| `tests/test_designer_fullscreen.py` | 107 | 8 | 3 | `test_button_id_matches_the_clientside_handler (16)` |
| `tests/test_cross_cutting_relocation.py` | 94 | 8 | 4 | `test_catalog_provider_recommendation_not_surfaced (5)` |
| `tests/test_agent_select_layout.py` | 91 | 8 | 1 | `_alert_texts (15)` |
| `tests/test_drain_stream.py` | 77 | 9 | 1 | `test_publishes_monotonically_per_chunk (12)` |
| `tests/conftest.py` | 67 | 2 | 0 | `stub_prioritizer (17)` |
| `tests/agentifier/test_fanout_baseline.py` | 63 | 6 | 0 | `test_fanout_counts_fragmentation (15)` |
| `tests/test_deployer_reentry.py` | 52 | 2 | 0 | `test_reentry_seed_embeds_existing_plan (21)` |
| `tests/test_tool_probe.py` | 50 | 8 | 1 | `test_sends_tools_in_call (6)` |
| `tests/test_image_probe.py` | 47 | 7 | 1 | `test_sends_image_in_message (8)` |
| `tests/test_chat_input_asset.py` | 45 | 6 | 1 | `test_shift_enter_stops_propagation_without_preventing_the_newline (10)` |
| `tests/integration/__init__.py` | 1 | 0 | 0 | `-` |
| `tests/agentifier/__init__.py` | 1 | 0 | 0 | `-` |
| `tests/__init__.py` | 1 | 0 | 0 | `-` |


Observations for Phase 4:

- Six source files exceed 1,300 lines: `agentifier/agentifier.py` (3501), `agents/_utils.py` (2514), `callbacks/__init__.py` (2466), `project_manager.py` (1905), `agents/code_scanner.py` (1718), `agents/stack_advisor.py` (1409), `agents/phaser.py` (1388), `callbacks/designer.py` (1371).
- Longest functions: `_run_catalog_phase` (659 lines, `agentifier.py`), `phaser.run` (499), `deployer.run` (343), `brainstormer.run` (236), `_format_stack_as_text` (232), `_chat_action_buttons` (221).
- `tests/test_agents.py` is 5,284 lines / 333 functions; `tests/test_designer.py` 2,351; `tests/test_artifact_view.py` 2,179. These are Phase 6 candidates for splitting by source module.

## 3. Dead-code pass

### 3.1 vulture (`uvx vulture src/ tests/ --min-confidence 60`)

71 lines before the whitelist. 47 of them were `@callback`-decorated functions (registered by decorator, invoked only by Dash) plus two Dash `app` attributes. `vulture_whitelist.py` at the repo root lists all 89 decorator-registered callbacks (2 in `app.py`, 62 in `callbacks/__init__.py`, 25 in `callbacks/designer.py`) and the two attributes.

Quiet invocation for later phases:

```
uvx vulture src/ tests/ vulture_whitelist.py --min-confidence 60
```

**Remaining candidates in `src/` after the whitelist (10):**

| Location | Finding | Confidence | Assessment |
|---|---|---:|---|
| `agentifier/pattern_loader.py:99` | unused variable `source_path` | 60% | dataclass field; check whether any reader uses it |
| `agentifier/pattern_loader.py:107` | unused variable `cost_range_usd` | 60% | dataclass field, same |
| `agentifier/pattern_loader.py:108` | unused variable `latency_range_seconds` | 60% | dataclass field, same |
| `agentifier/tier_analyst.py:294` | unused variable `valid_tier_names` | 100% | unused function parameter (also ruff ARG001). Callers pass it; removing changes a call signature, Phase 2 |
| `agents/code_scanner.py:28` | unused variable `CODE_REVIEW_SCHEMA_VERSION` | 60% | module constant with no readers; likely dead or meant for the artifact frontmatter |
| `agents/designer.py:131` | unused variable `preference_text` | 60% | dataclass field |
| `agents/designer.py:133` | unused variable `mock_html` | 60% | dataclass field |
| `agents/designer.py:134` | unused variable `finalized` | 60% | dataclass field |
| `callbacks/__init__.py:1139` | unused variable `n_submit` | 100% | callback positional arg bound to an `Input`; cannot be removed without changing the `Input` list. **Not dead.** |
| `layouts/_chat.py:306` | unused function `download_button_id` | 60% | zero references anywhere (see §5). Real candidate |

**Remaining candidates in `tests/` (22):**

```
tests/agentifier/test_prioritizer.py:501: unused attribute 'side_effect' (60% confidence)
tests/agentifier/test_prioritizer.py:511: unused attribute 'side_effect' (60% confidence)
tests/agentifier/test_prioritizer.py:526: unused attribute 'side_effect' (60% confidence)
tests/agentifier/test_prioritizer.py:534: unused attribute 'side_effect' (60% confidence)
tests/agentifier/test_prioritizer.py:550: unused attribute 'side_effect' (60% confidence)
tests/agentifier/test_streaming_e2e.py:176: unreachable code after 'return' (100% confidence)
tests/integration/test_pipeline_greenfield.py:95: unused function '_make_sync_mock' (60% confidence)
tests/test_designer.py:811: unused variable 'tavily_key' (100% confidence)
tests/test_designer.py:909: unused variable 'tavily_key' (100% confidence)
tests/test_designer.py:1112: unused variable 'tavily_key' (100% confidence)
tests/test_designer.py:1159: unused variable 'tavily_key' (100% confidence)
tests/test_phaser_seed_inputs.py:185: unused attribute 'side_effect' (60% confidence)
tests/test_phaser_seed_inputs.py:218: unused attribute 'side_effect' (60% confidence)
tests/test_providers.py:208: unused attribute 'side_effect' (60% confidence)
tests/test_usage_capture.py:41: unused function '_clean_sink' (60% confidence)
tests/test_usage_capture.py:75: unused attribute 'cache_creation_input_tokens' (60% confidence)
tests/test_usage_capture.py:77: unused attribute 'cache_read_input_tokens' (60% confidence)
tests/test_version_check.py:26: unused function '_clean_state' (60% confidence)
tests/test_version_check.py:73: unused attribute '__enter__' (60% confidence)
tests/test_version_check.py:74: unused attribute '__exit__' (60% confidence)
tests/test_version_check.py:82: unused attribute '__enter__' (60% confidence)
tests/test_version_check.py:83: unused attribute '__exit__' (60% confidence)
```

Most of these are `MagicMock` attribute assignments (`side_effect`, `__enter__`, `cache_read_input_tokens`) that vulture cannot see being read; not dead. Real candidates: `tests/agentifier/test_streaming_e2e.py:176` (unreachable code after `return`, 100%), the four `tavily_key` unpacked-but-unused locals in `tests/test_designer.py`, `_make_sync_mock` in `test_pipeline_greenfield.py`, and the `_clean_sink` / `_clean_state` fixtures (verify they are autouse fixtures before treating as dead).

### 3.2 ruff `--select F401,F811,F841,ARG` on `src/ tests/`

`Found 171 errors`: ARG001 122, ARG005 36, ARG002 13. **Zero** F401/F811/F841 (the permanent `E,F` config already keeps those clean).

In `src/` (9):

```
src/spec4/agentifier/agentifier.py:2460:5: ARG001 Unused function argument: `llm_config`
src/spec4/agentifier/agentifier.py:3377:5: ARG001 Unused function argument: `user_input`
src/spec4/agentifier/tier_analyst.py:294:29: ARG001 Unused function argument: `valid_tier_names`
src/spec4/callbacks/__init__.py:1139:20: ARG001 Unused function argument: `n_clicks`
src/spec4/callbacks/__init__.py:1139:35: ARG001 Unused function argument: `n_submit`
src/spec4/callbacks/__init__.py:1902:20: ARG001 Unused function argument: `n`
src/spec4/callbacks/designer.py:732:25: ARG001 Unused function argument: `n`
src/spec4/layouts/__init__.py:235:26: ARG001 Unused function argument: `session`
src/spec4/layouts/_setup.py:233:5: ARG001 Unused function argument: `session`
```

The four `n`/`n_clicks`/`n_submit` cases are Dash callback inputs and are not removable. `layouts/__init__.py:235` and `layouts/_setup.py:233` take an unused `session`; both are called through a uniform signature, check before removing. `agentifier.py:2460` (`llm_config`) and `:3377` (`user_input`) are worth a look in Phase 2.

In `tests/` (162): `test_designer.py` 50, `integration/test_pipeline_greenfield.py` 13, `test_agents.py` 11, `test_phaser_seed_inputs.py` 10, `test_stream_status.py` 8, then a long tail. Nearly all are stub signatures (`def fake_complete(*args, **kwargs)`) and fixture parameters requested for their side effect. Not cleanup targets; if `ARG` is ever added to the permanent config it will need `per-file-ignores` for `tests/`.

## 4. deptry (`uvx deptry .`)

Exit 1. 246 findings: DEP001 240, DEP002 3, DEP004 3, DEP003 0.

**Real findings (3):**

| Rule | Package | Assessment |
|---|---|---|
| DEP002 | `dash-iconify` | **Genuinely unused.** No `dash_iconify` / `DashIconify` reference anywhere in `src/`. Also present in the mypy `ignore_missing_imports` override. Phase 2 candidate (removal from `[project.dependencies]` and the mypy override; verify no `dash-mantine-components` transitive need). |
| DEP002 | `gunicorn` | Not imported by Python; used only as a process (`Makefile` `serve` target, README). Keep; false positive for deptry's purposes. |
| DEP002 | `pyyaml` | False positive: deptry did not map `pyyaml` → `yaml` because the package is not installed in the `uvx` environment. `import yaml` is at `agentifier/pattern_loader.py:19`. |
| DEP004 | `playwright` (dev) | `scripts/screenshot_ui.py:4` imports a dev-only dependency. Scripts are not shipped; acceptable, but note it. |
| DEP004 | `pytest` (dev) | `evals/scout/test_phantom_link_check.py`, `evals/agentifier/test_mechanism_scoring.py`. Same reasoning as above. |

**Noise (240 DEP001):** every `spec4` import is reported "missing from the dependency definitions" (210 occurrences) because the package is not installed in the isolated `uvx` cache; plus 30 sibling-module imports inside `evals/` (`_load`, `fanout_baseline`, `relevance_judge`, `scout_granularity`, `mechanism_scoring`, `phantom_link_check`, `relevance_scoring`, `requires_inversion`, `scout_edge_metrics`, `confab_baseline`) which are `sys.path`-relative script imports. For the Phase 2/7 reruns, `uvx --with . deptry . --ignore DEP001` or a `[tool.deptry] known_first_party = ["spec4"]` entry would remove the noise, but the plan forbids adding to `pyproject.toml`, so filter with `--ignore DEP001` and read the DEP002/DEP003/DEP004 lines only.

## 5. Complexity ("spaghetti") measurement

`uv run ruff check --select C90,PLR0912,PLR0913,PLR0915,SIM,B --statistics src/`:

```
61	C901   	complex-structure
40	PLR0912	too-many-branches
25	PLR0915	too-many-statements
12	PLR0913	too-many-arguments
 4	B905   	zip-without-explicit-strict
 3	SIM105 	suppressible-exception
 2	B904   	raise-without-from-inside-except
 2	SIM117 	multiple-with-statements
 1	B007   	unused-loop-control-variable
 1	SIM905 	split-static-string
Found 151 errors.
```

Findings per file (top): `agents/_utils.py` 29, `agentifier/agentifier.py` 15, `agents/code_scanner.py` 13, `project_manager.py` 10, `callbacks/designer.py` 8, `agents/designer.py` 8, `llm.py` 7, `agents/stack_advisor.py` 7.

### 5.1 Ten worst functions by cyclomatic complexity (C901, threshold 10)

| Complexity | Function | Location | Statements (PLR0915 > 50) | Branches (PLR0912 > 12) |
|---:|---|---|---:|---:|
| 61 | `_format_stack_as_text` | `src/spec4/agents/stack_advisor.py:921` | 179 | 67 |
| 39 | `_format_review_as_text` | `src/spec4/agents/code_scanner.py:1091` | 125 | 42 |
| 38 | `_run_catalog_phase` | `src/spec4/agentifier/agentifier.py:2623` | 230 | 41 |
| 33 | `run` | `src/spec4/agents/phaser.py:890` | 148 | 37 |
| 29 | `_stack_for_deployer` | `src/spec4/agents/_utils.py:1344` | 81 | 28 |
| 26 | `check_phase_coverage` | `src/spec4/agents/_phase_coverage.py:176` | — | 26 |
| 25 | `stream_turn` | `src/spec4/llm.py:809` | — | 27 |
| 24 | `run` | `src/spec4/agents/deployer.py:543` | 130 | 30 |
| 24 | `_stack_digest_for_phaser` | `src/spec4/agents/_utils.py:2271` | — | — |
| 23 | `_ai_features_for_designer` | `src/spec4/agents/_utils.py:1621` | 69 | — |

Next in line: `generate_mock_streaming` 22 (`agents/designer.py:536`, also 13 arguments), `_render_typed_notes` 21, `brainstormer.run` 20, `callbacks/designer._start_gen` 20 (13 arguments), `_phase_spec_preamble` 20, `_ai_features_for_deployer` 20.

Full C901 list (complexity | function | location):

```
61 | _format_stack_as_text | src/spec4/agents/stack_advisor.py:921
39 | _format_review_as_text | src/spec4/agents/code_scanner.py:1091
38 | _run_catalog_phase | src/spec4/agentifier/agentifier.py:2623
33 | run | src/spec4/agents/phaser.py:890
29 | _stack_for_deployer | src/spec4/agents/_utils.py:1344
26 | check_phase_coverage | src/spec4/agents/_phase_coverage.py:176
25 | stream_turn | src/spec4/llm.py:809
24 | run | src/spec4/agents/deployer.py:543
24 | _stack_digest_for_phaser | src/spec4/agents/_utils.py:2271
23 | _ai_features_for_designer | src/spec4/agents/_utils.py:1621
22 | generate_mock_streaming | src/spec4/agents/designer.py:536
21 | _render_typed_notes | src/spec4/agents/code_scanner.py:1401
20 | run | src/spec4/agents/brainstormer.py:626
20 | _start_gen | src/spec4/callbacks/designer.py:231
20 | _phase_spec_preamble | src/spec4/project_manager.py:475
20 | _ai_features_for_deployer | src/spec4/agents/_utils.py:1145
19 | _chat_action_buttons | src/spec4/layouts/_chat.py:409
18 | _format_spec_as_text | src/spec4/agentifier/agentifier.py:762
17 | validate_manifest | src/spec4/agents/_manifest.py:145
17 | _validate_frontmatter | src/spec4/agentifier/pattern_loader.py:236
17 | _design_manifest_for_stack | src/spec4/agents/_utils.py:1867
17 | _build_revision_context | src/spec4/agents/_utils.py:90
16 | on_stream_poll | src/spec4/callbacks/__init__.py:1902
16 | build_mock_prompt | src/spec4/agents/designer.py:398
16 | _project_feature_for_stack | src/spec4/agents/_utils.py:736
16 | _format_vision_as_text | src/spec4/agents/brainstormer.py:504
16 | _feature_specs_for_stack | src/spec4/agents/_utils.py:1963
16 | _ai_features_for_phaser | src/spec4/agents/_utils.py:1008
15 | run | src/spec4/agentifier/composer.py:198
15 | _stream_suppressing_json | src/spec4/agents/_utils.py:458
15 | _run | src/spec4/callbacks/designer.py:298
15 | _gather_project_context | src/spec4/agents/code_scanner.py:176
14 | run | src/spec4/agents/code_scanner.py:1524
14 | render_grounding_for_prompt | src/spec4/agentifier/grounding.py:102
14 | merge_library_additions | src/spec4/project_manager.py:170
14 | _persist_artifacts | src/spec4/session.py:563
13 | directional_signals | src/spec4/agentifier/requires_reconciler.py:258
13 | _run_cross_cutting_phase | src/spec4/agentifier/agentifier.py:2192
13 | _render_graph_lines | src/spec4/feature_specs.py:469
13 | _normalize_edges | src/spec4/agentifier/linker.py:209
13 | _fetch_models | src/spec4/providers.py:111
13 | _build_seed_message | src/spec4/agentifier/agentifier.py:546
13 | _artifact_button_state | src/spec4/project_manager.py:1856
13 | _agent_select_layout | src/spec4/layouts/__init__.py:301
12 | run | src/spec4/agents/stack_advisor.py:1193
12 | render_usage_table | src/spec4/usage_report.py:91
12 | close_selection | src/spec4/agentifier/panel_closure.py:65
12 | _render_topology | src/spec4/feature_specs.py:414
12 | _render_persistence | src/spec4/agents/code_scanner.py:1252
12 | _reconcile_dependencies | src/spec4/agents/feature_speccer.py:402
12 | _load_working_dir | src/spec4/session.py:225
12 | _field | src/spec4/agentifier/agentifier.py:775
11 | reconcile_requires | src/spec4/agentifier/requires_reconciler.py:421
11 | _validate_dependencies | src/spec4/agents/feature_speccer.py:360
11 | _render_deployment | src/spec4/agents/code_scanner.py:1302
11 | _normalise_stack_shape | src/spec4/agents/stack_advisor.py:742
11 | _manifest_for_phaser | src/spec4/agents/_utils.py:2427
11 | _has_cycle | src/spec4/agentifier/requires_reconciler.py:376
11 | _feature_specs_for_phaser | src/spec4/agents/_utils.py:2149
11 | _check_table_provenance | src/spec4/agents/_seam_check.py:208
11 | _ai_features_for_stack | src/spec4/agents/_utils.py:820
```

Note for Phase 5: `_format_stack_as_text`, `_format_review_as_text`, `_format_vision_as_text`, `_format_spec_as_text` and the `_render_*` family are text renderers whose output ends up in `.spec4/` artifacts and LLM prompts (frozen surfaces, Rule 4). Decomposing them is allowed but must be verified with golden-output tests, not just unit tests.

### 5.2 Other rule hits (26, all small)

```
src/spec4/agentifier/agentifier.py:294:5: PLR0913 Too many arguments in function definition (7 > 5)
src/spec4/agentifier/agentifier.py:593:42: B905 `zip()` without an explicit `strict=` parameter
src/spec4/agentifier/pattern_loader.py:163:29: B905 `zip()` without an explicit `strict=` parameter
src/spec4/agentifier/requires_reconciler.py:84:5: SIM905 [*] Consider using a list literal instead of `str.split`
src/spec4/agentifier/subagents.py:181:13: B904 Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling
src/spec4/agentifier/subagents.py:249:9: B904 Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling
src/spec4/agents/_utils.py:364:5: PLR0913 Too many arguments in function definition (10 > 5)
src/spec4/agents/designer.py:199:9: B007 Loop control variable `root` not used within loop body
src/spec4/agents/designer.py:398:5: PLR0913 Too many arguments in function definition (6 > 5)
src/spec4/agents/designer.py:536:5: PLR0913 Too many arguments in function definition (13 > 5)
src/spec4/callbacks/__init__.py:765:5: PLR0913 Too many arguments in function definition (6 > 5)
src/spec4/callbacks/designer.py:231:5: PLR0913 Too many arguments in function definition (13 > 5)
src/spec4/callbacks/designer.py:1059:24: B905 `zip()` without an explicit `strict=` parameter
src/spec4/callbacks/designer.py:1102:5: PLR0913 Too many arguments in function definition (6 > 5)
src/spec4/callbacks/designer.py:1292:9: SIM105 Use `contextlib.suppress(OSError, FileNotFoundError)` instead of `try`-`except`-`pass`
src/spec4/layouts/_status_bar.py:186:5: PLR0913 Too many arguments in function definition (6 > 5)
src/spec4/llm.py:410:5: PLR0913 Too many arguments in function definition (9 > 5)
src/spec4/llm.py:494:5: PLR0913 Too many arguments in function definition (6 > 5)
src/spec4/llm.py:543:11: PLR0913 Too many arguments in function definition (6 > 5)
src/spec4/llm.py:809:5: PLR0913 Too many arguments in function definition (7 > 5)
src/spec4/project_manager.py:116:9: SIM105 Use `contextlib.suppress(OSError, json.JSONDecodeError)` instead of `try`-`except`-`pass`
src/spec4/project_manager.py:1433:9: SIM105 Use `contextlib.suppress(OSError)` instead of `try`-`except`-`pass`
src/spec4/project_manager.py:1893:37: B905 `zip()` without an explicit `strict=` parameter
src/spec4/websearch.py:180:5: SIM117 Use a single `with` statement with multiple contexts instead of nested `with` statements
src/spec4/websearch.py:189:5: SIM117 Use a single `with` statement with multiple contexts instead of nested `with` statements
```

## 6. Import-graph inventory

Direct imports of other `spec4` modules per module, split into top-level and lazy (inside a function body). Built from `ast`; `from spec4.x import y` where `spec4.x.y` is itself a module counts as an edge to the submodule.

| Module | Top-level imports of spec4 modules | Lazy (function-body) imports |
|---|---|---|
| `spec4` | — | — |
| `spec4.agentifier` | — | — |
| `spec4.agentifier.agentifier` | `spec4`, `spec4.agentifier.composer`, `spec4.agentifier.cross_cutting_analyst`, `spec4.agentifier.grounding`, `spec4.agentifier.infra_expander`, `spec4.agentifier.linker`, `spec4.agentifier.panel_closure`, `spec4.agentifier.pattern_loader`, `spec4.agentifier.prioritizer`, `spec4.agentifier.requires_reconciler`, `spec4.agentifier.scout`, `spec4.agentifier.spec_drafter`, `spec4.agentifier.subagents`, `spec4.agentifier.tier_analyst`, `spec4.agents._utils`, `spec4.app_constants`, `spec4.llm`, `spec4.project_manager`, `spec4.websearch` | `spec4.agentifier.reference_verifier` |
| `spec4.agentifier.composer` | `spec4.agentifier.scout`, `spec4.agentifier.subagents`, `spec4.llm` | — |
| `spec4.agentifier.cross_cutting_analyst` | `spec4.agentifier.pattern_loader`, `spec4.agentifier.spec_drafter`, `spec4.agentifier.subagents`, `spec4.llm` | `spec4.agentifier.tier_analyst` |
| `spec4.agentifier.grounding` | `spec4.agents._utils` | — |
| `spec4.agentifier.infra_expander` | — | — |
| `spec4.agentifier.linker` | `spec4.agentifier.scout`, `spec4.agentifier.subagents`, `spec4.llm` | — |
| `spec4.agentifier.panel_closure` | `spec4.agentifier.scout` | — |
| `spec4.agentifier.pattern_loader` | — | — |
| `spec4.agentifier.prioritizer` | `spec4.agentifier.subagents`, `spec4.llm` | — |
| `spec4.agentifier.reference_verifier` | — | `spec4`, `spec4.llm` |
| `spec4.agentifier.requires_reconciler` | `spec4.agents._utils` | — |
| `spec4.agentifier.scout` | `spec4.agentifier.subagents`, `spec4.llm` | — |
| `spec4.agentifier.spec_drafter` | `spec4.agentifier.grounding`, `spec4.agentifier.pattern_loader`, `spec4.agentifier.subagents`, `spec4.llm` | — |
| `spec4.agentifier.subagents` | — | — |
| `spec4.agentifier.tier_analyst` | `spec4.agentifier.pattern_loader`, `spec4.agentifier.scout`, `spec4.agentifier.subagents`, `spec4.llm` | — |
| `spec4.agents` | — | — |
| `spec4.agents._code_review_schema` | — | — |
| `spec4.agents._image_probe` | — | — |
| `spec4.agents._manifest` | `spec4.agents._utils` | — |
| `spec4.agents._phase_coverage` | `spec4.agentifier.infra_expander`, `spec4.agents._utils` | — |
| `spec4.agents._phase_schema` | — | — |
| `spec4.agents._seam_check` | `spec4.agents._utils`, `spec4.llm` | — |
| `spec4.agents._tool_probe` | — | — |
| `spec4.agents._utils` | `spec4`, `spec4.agentifier.infra_expander`, `spec4.design_manifest`, `spec4.feature_specs`, `spec4.project_manager`, `spec4.stack_routing` | `spec4.llm` |
| `spec4.agents.brainstormer` | `spec4`, `spec4.agents`, `spec4.agents._utils`, `spec4.agents.feature_speccer`, `spec4.app_constants`, `spec4.llm`, `spec4.project_manager`, `spec4.websearch` | — |
| `spec4.agents.code_scanner` | `spec4`, `spec4.agents._code_review_schema`, `spec4.agents._utils`, `spec4.app_constants`, `spec4.llm`, `spec4.websearch` | — |
| `spec4.agents.deployer` | `spec4`, `spec4.agents._utils`, `spec4.app_constants`, `spec4.llm`, `spec4.project_manager`, `spec4.websearch` | — |
| `spec4.agents.designer` | `spec4`, `spec4.agents._manifest`, `spec4.llm`, `spec4.websearch` | `spec4.agents._utils` |
| `spec4.agents.feature_speccer` | `spec4`, `spec4.agents._utils`, `spec4.llm` | — |
| `spec4.agents.phaser` | `spec4`, `spec4.agents._phase_coverage`, `spec4.agents._phase_schema`, `spec4.agents._seam_check`, `spec4.agents._utils`, `spec4.app_constants`, `spec4.llm`, `spec4.project_manager`, `spec4.websearch` | — |
| `spec4.agents.stack_advisor` | `spec4`, `spec4.agents._utils`, `spec4.app_constants`, `spec4.llm`, `spec4.project_manager`, `spec4.websearch` | — |
| `spec4.app` | `spec4`, `spec4.app_constants`, `spec4.callbacks`, `spec4.callbacks.designer`, `spec4.layouts`, `spec4.layouts._status_bar`, `spec4.layouts.designer`, `spec4.project_manager`, `spec4.session`, `spec4.version_check` | — |
| `spec4.app_constants` | — | — |
| `spec4.callbacks` | `spec4`, `spec4.agentifier.panel_closure`, `spec4.app_constants`, `spec4.layouts._artifact_view`, `spec4.layouts._chat`, `spec4.layouts._llm_gate`, `spec4.layouts._round_cost`, `spec4.layouts._round_tree`, `spec4.layouts._setup`, `spec4.layouts._status_bar`, `spec4.llm_selection`, `spec4.project_manager`, `spec4.providers`, `spec4.session`, `spec4.streaming`, `spec4.websearch` | `spec4.agentifier.agentifier` |
| `spec4.callbacks.designer` | `spec4`, `spec4.agents._manifest`, `spec4.agents.designer`, `spec4.callbacks`, `spec4.layouts.designer`, `spec4.llm`, `spec4.llm_selection`, `spec4.project_manager`, `spec4.websearch` | — |
| `spec4.design_manifest` | — | — |
| `spec4.feature_specs` | `spec4.agentifier.infra_expander`, `spec4.agentifier.pattern_loader` | — |
| `spec4.layouts` | `spec4`, `spec4.app_constants`, `spec4.layouts._agent_rows`, `spec4.layouts._artifact_view`, `spec4.layouts._chat`, `spec4.layouts._round_cost`, `spec4.layouts._round_tree`, `spec4.layouts._setup`, `spec4.layouts._shared`, `spec4.layouts._status_bar`, `spec4.project_manager` | — |
| `spec4.layouts._agent_rows` | `spec4`, `spec4.app_constants`, `spec4.layouts._round_tree`, `spec4.llm_selection`, `spec4.project_manager` | — |
| `spec4.layouts._artifact_view` | `spec4`, `spec4.layouts._agent_rows`, `spec4.layouts._round_tree`, `spec4.layouts._shared`, `spec4.project_manager` | — |
| `spec4.layouts._chat` | `spec4`, `spec4.agentifier.panel_closure`, `spec4.app_constants`, `spec4.layouts`, `spec4.layouts._agent_rows`, `spec4.layouts._llm_gate`, `spec4.layouts._round_cost`, `spec4.layouts._round_tree`, `spec4.layouts._shared`, `spec4.llm_selection`, `spec4.project_manager`, `spec4.session` | — |
| `spec4.layouts._llm_gate` | `spec4`, `spec4.layouts._setup`, `spec4.layouts._shared`, `spec4.llm_selection`, `spec4.providers` | — |
| `spec4.layouts._round_cost` | `spec4`, `spec4.layouts._agent_rows`, `spec4.layouts._shared`, `spec4.project_manager` | — |
| `spec4.layouts._round_tree` | `spec4`, `spec4.app_constants`, `spec4.project_manager` | — |
| `spec4.layouts._setup` | `spec4`, `spec4.layouts._shared`, `spec4.llm_selection`, `spec4.providers`, `spec4.websearch` | — |
| `spec4.layouts._shared` | — | — |
| `spec4.layouts._status_bar` | `spec4`, `spec4.app_constants`, `spec4.layouts._shared`, `spec4.llm_selection` | — |
| `spec4.layouts.designer` | `spec4`, `spec4.agents.designer`, `spec4.app_constants`, `spec4.layouts`, `spec4.layouts._llm_gate`, `spec4.layouts._round_cost`, `spec4.layouts._shared`, `spec4.project_manager` | — |
| `spec4.llm` | `spec4.websearch` | — |
| `spec4.llm_selection` | `spec4`, `spec4.agents._image_probe`, `spec4.agents._tool_probe`, `spec4.app_constants`, `spec4.llm`, `spec4.providers` | — |
| `spec4.project_manager` | `spec4`, `spec4.app_constants`, `spec4.design_manifest`, `spec4.feature_specs`, `spec4.stack_routing` | — |
| `spec4.providers` | — | — |
| `spec4.session` | `spec4`, `spec4.agents`, `spec4.agents.brainstormer`, `spec4.agents.code_scanner`, `spec4.agents.deployer`, `spec4.agents.phaser`, `spec4.agents.stack_advisor`, `spec4.app_constants`, `spec4.llm`, `spec4.llm_selection`, `spec4.project_manager` | `spec4.agentifier.agentifier` |
| `spec4.stack_routing` | — | — |
| `spec4.streaming` | — | — |
| `spec4.usage_report` | `spec4`, `spec4.project_manager` | — |
| `spec4.version_check` | `spec4` | — |
| `spec4.websearch` | — | — |


### 6.1 Cycles

Exactly one, and it is intra-package:

- `spec4.layouts` → `spec4.layouts._chat` → `spec4.layouts` (both at top level). `layouts/__init__.py` imports `_chat` for re-export while `_chat` imports the package for shared names. It works today because of import ordering; Phase 4 should break it by moving whatever `_chat` needs into `layouts/_shared.py`.

No other cycle exists, even counting lazy imports.

### 6.2 Layer edges

- `agents/*`, `agentifier/*`, `project_manager` → `layouts`: **none.**
- `agents/*`, `agentifier/*`, `project_manager` → `callbacks` / `app` / `session`: **none.**
- `spec4.app` is imported by **nothing** (top-only holds).
- `spec4.callbacks` is imported only by `spec4.app` and `spec4.callbacks.designer`.
- `spec4.session` (the Dash-side session/agent runner) is imported by `app`, `callbacks`, and `layouts._chat`, and itself imports every `agents.*` module plus (lazily) `agentifier.agentifier`. It is the hinge between the UI and the agent layer.
- Lazy edges that hide layer coupling: `callbacks` → `agentifier.agentifier` (function body), `session` → `agentifier.agentifier`, `agents._utils` → `llm`, `agents.designer` → `agents._utils`, `agentifier.reference_verifier` → `llm`, `agentifier.agentifier` → `reference_verifier`, `agentifier.cross_cutting_analyst` → `tier_analyst`. None of these is a cycle at top level; several look like they exist only to dodge one, which is worth confirming in Phase 4.
- `spec4.llm` is imported by 21 modules; `spec4.project_manager` by 18. Both are true foundation modules.

### 6.3 import-linter decision

**Recommendation: do not install import-linter. Write a single import-assertion test in Phase 4.**

Reasoning against the plan's threshold ("more than two or three boundaries worth guarding"):

1. Only three boundaries are worth stating, and all three already hold: (a) `agents`, `agentifier`, `project_manager`, `llm`, `feature_specs`, `design_manifest`, `stack_routing`, `streaming` never import `layouts`, `callbacks`, `app`, or `session`; (b) `layouts` never imports `callbacks` or `app`; (c) nothing imports `app`.
2. There is one cycle to eliminate, not a family of them.
3. The `ast`-based walk that produced §6 is about 40 lines; the assertion test is a subset of it and needs no new dependency, no `pyproject.toml` section, and no extra gate command.

Revisit if Phase 4 splits `agents/_utils.py` or `callbacks/__init__.py` into packages with their own internal layering. That would be the point where a declarative contract pays for itself.

## 7. Grep-based cross-reference (zero-importer candidates)

Method: for every top-level `def`/`class` in `src/spec4`, count files other than its own that mention the name as a whole word, across `src/`, `tests/`, `evals/`, `scripts/`.

- Names with **zero references outside their own file**: 279. Of these, 228 are underscore-private helpers used only inside their module, which is the intended state and not dead code (vulture, which does see intra-file use, flags only one of them: `download_button_id`).
- **Public names (no leading underscore) with zero references outside their file: 51.** These are the Phase 2 review list. 33 of them are `@callback` functions (invoked by Dash, not dead). The remaining 18:

| Module | Name | Note |
|---|---|---|
| `spec4.agentifier.agentifier` | `PriorityEdits` | dataclass used internally only; could be private |
| `spec4.agentifier.pattern_loader` | `PatternBase` | base class, internal |
| `spec4.agentifier.requires_reconciler` | `directional_signals` | public function, no external caller; also C901=13 |
| `spec4.callbacks` | `session_round` | helper; only used inside `callbacks/__init__.py` |
| `spec4.design_manifest` | `implements_ids` | exported in `__all__`; no caller outside the module |
| `spec4.design_manifest` | `catalog_id` | exported in `__all__`; no caller outside the module |
| `spec4.layouts._agent_rows` | `AgentRowSpec`, `AgentRow` | typed containers used internally; `AgentRow` is in `__all__` |
| `spec4.layouts._artifact_view` | `AllowedArtifact`, `artifact_header`, `artifact_body` | not in `__all__`; `artifact_header`/`artifact_body` are only called by the wrapper at `:666` and could be private |
| `spec4.layouts._chat` | `download_button_id` | **also flagged by vulture; strongest single candidate** |
| `spec4.layouts._llm_gate` | `naming_line` | |
| `spec4.layouts._round_cost` | `CostStripIds` | in `__all__` |
| `spec4.layouts._round_tree` | `TreeLine` | in `__all__` |
| `spec4.layouts._setup` | `setup_step_row` | |
| `spec4.project_manager` | `RoundsOnDisk`, `usage_rollup_name` | `usage_rollup_name` has an internal caller only |

- Names referenced **only from tests/evals/scripts** (never from another `src` module): 214. That is the expected shape for private helpers under test and for `@callback` functions the register tests invoke directly. It is listed in full below so Phase 2 and Phase 6 can check that test-only public names are deliberate.

### 7.1 Definitions referenced only from tests/evals/scripts (never from other src modules)
| Module | Name | Referencing non-src files |
|---|---|---:|
| `spec4.agentifier.agentifier` | `_iter_async_gen` | 1 |
| `spec4.agentifier.agentifier` | `_call_scout` | 6 |
| `spec4.agentifier.agentifier` | `_vision_mvp_feature_names` | 1 |
| `spec4.agentifier.agentifier` | `_call_linker` | 3 |
| `spec4.agentifier.agentifier` | `_call_composer` | 2 |
| `spec4.agentifier.agentifier` | `_call_prioritizer` | 1 |
| `spec4.agentifier.agentifier` | `_call_tier_analyst` | 5 |
| `spec4.agentifier.agentifier` | `_build_seed_message` | 3 |
| `spec4.agentifier.agentifier` | `_candidates_to_dicts` | 2 |
| `spec4.agentifier.agentifier` | `_analyses_to_dicts` | 2 |
| `spec4.agentifier.agentifier` | `_is_spec_confirmed` | 2 |
| `spec4.agentifier.agentifier` | `_feature_specs_for_session` | 1 |
| `spec4.agentifier.agentifier` | `_linked_features_for_entry` | 1 |
| `spec4.agentifier.agentifier` | `_existing_workflow_for_entry` | 1 |
| `spec4.agentifier.agentifier` | `_expand_infrastructure` | 1 |
| `spec4.agentifier.agentifier` | `_revision_delta` | 1 |
| `spec4.agentifier.agentifier` | `_merge_revision_snapshot` | 1 |
| `spec4.agentifier.agentifier` | `_removed_feature_heads_up` | 1 |
| `spec4.agentifier.agentifier` | `_draft_spec` | 1 |
| `spec4.agentifier.agentifier` | `_finalize_specs` | 3 |
| `spec4.agentifier.agentifier` | `_extract_cross_cutting_analysis` | 3 |
| `spec4.agentifier.agentifier` | `_parse_priority_edits` | 1 |
| `spec4.agentifier.agentifier` | `_format_priority_table` | 1 |
| `spec4.agentifier.agentifier` | `_run_spec_phase` | 1 |
| `spec4.agentifier.agentifier` | `_run_cross_cutting_phase` | 1 |
| `spec4.agentifier.agentifier` | `_begin_priority_phase` | 3 |
| `spec4.agentifier.agentifier` | `_run_priority_phase` | 1 |
| `spec4.agentifier.agentifier` | `_breadth_candidates` | 1 |
| `spec4.agentifier.agentifier` | `_reselection_pool_from_features` | 2 |
| `spec4.agentifier.agentifier` | `_candidates_from_dicts` | 1 |
| `spec4.agentifier.agentifier` | `_handle_reentry` | 2 |
| `spec4.agentifier.composer` | `_group_by_composed_under` | 1 |
| `spec4.agentifier.composer` | `_enrich_descriptions` | 1 |
| `spec4.agentifier.cross_cutting_analyst` | `_feature_digest` | 1 |
| `spec4.agentifier.grounding` | `spec_by_id` | 2 |
| `spec4.agentifier.infra_expander` | `_infra_node` | 2 |
| `spec4.agentifier.linker` | `EdgeOverlay` | 1 |
| `spec4.agentifier.linker` | `LinkerOutput` | 3 |
| `spec4.agentifier.linker` | `_format_candidates_block` | 1 |
| `spec4.agentifier.panel_closure` | `ClosureResult` | 1 |
| `spec4.agentifier.pattern_loader` | `PatternValidationError` | 2 |
| `spec4.agentifier.pattern_loader` | `_build_pattern` | 2 |
| `spec4.agentifier.prioritizer` | `PrioritizerOutput` | 2 |
| `spec4.agentifier.prioritizer` | `_format_features_block` | 1 |
| `spec4.agentifier.reference_verifier` | `is_url_present` | 1 |
| `spec4.agentifier.reference_verifier` | `lookup_reference_url` | 1 |
| `spec4.agentifier.reference_verifier` | `extract_references_from_spec` | 1 |
| `spec4.agentifier.requires_reconciler` | `_chunks` | 6 |
| `spec4.agentifier.requires_reconciler` | `_name_pattern` | 1 |
| `spec4.agentifier.requires_reconciler` | `name_matches` | 8 |
| `spec4.agentifier.requires_reconciler` | `_stem_prefix_match` | 2 |
| `spec4.agentifier.requires_reconciler` | `build_production_map` | 3 |
| `spec4.agentifier.requires_reconciler` | `classify_edge` | 1 |
| `spec4.agentifier.scout` | `_build_scout_system_prompt` | 2 |
| `spec4.agentifier.scout` | `_parse_candidates` | 3 |
| `spec4.agentifier.scout` | `_format_scout_revision_block` | 1 |
| `spec4.agentifier.scout` | `_format_scout_guidance_block` | 1 |
| `spec4.agentifier.spec_drafter` | `_tier_extra_fields` | 1 |
| `spec4.agentifier.subagents` | `SubAgentError` | 2 |
| `spec4.agentifier.subagents` | `SubAgentTimeoutError` | 1 |
| `spec4.agentifier.subagents` | `RegistryLookupError` | 1 |
| `spec4.agentifier.subagents` | `SubAgent` | 1 |
| `spec4.agentifier.subagents` | `run_with_timeout` | 1 |
| `spec4.agentifier.tier_analyst` | `_build_tier_descriptions` | 1 |
| `spec4.agentifier.tier_analyst` | `_build_mechanism_absorption_list` | 1 |
| `spec4.agentifier.tier_analyst` | `_parse_output` | 1 |
| `spec4.agents._seam_check` | `SeamFinding` | 1 |
| `spec4.agents._seam_check` | `_feature_lines` | 2 |
| `spec4.agents._seam_check` | `_parse_graph` | 1 |
| `spec4.agents._seam_check` | `_extract_graph` | 2 |
| `spec4.agents._seam_check` | `_check_table_provenance` | 1 |
| `spec4.agents._seam_check` | `_check_endpoint_provenance` | 1 |
| `spec4.agents._seam_check` | `_check_feature_coverage` | 2 |
| `spec4.agents._seam_check` | `_check_declaration_alignment` | 2 |
| `spec4.agents._seam_check` | `_format_advisory` | 1 |
| `spec4.agents._utils` | `_build_revision_context` | 1 |
| `spec4.agents._utils` | `_drop_orphan_trailing_user` | 1 |
| `spec4.agents._utils` | `_feature_relationship_lines` | 1 |
| `spec4.agents._utils` | `_explicitly_rejected_lines` | 1 |
| `spec4.agents.brainstormer` | `_stamp_revision_block` | 1 |
| `spec4.agents.brainstormer` | `_assign_feature_ids` | 1 |
| `spec4.agents.brainstormer` | `_reclassify_changes` | 1 |
| `spec4.agents.brainstormer` | `_apply_revision_history` | 2 |
| `spec4.agents.brainstormer` | `_format_vision_as_text` | 1 |
| `spec4.agents.brainstormer` | `_rehydrate_vision_from_disk` | 1 |
| `spec4.agents.code_scanner` | `_collect_files` | 1 |
| `spec4.agents.code_scanner` | `_gather_project_context` | 2 |
| `spec4.agents.code_scanner` | `_extract_review_json` | 1 |
| `spec4.agents.code_scanner` | `_extract_and_validate_review` | 1 |
| `spec4.agents.code_scanner` | `_format_review_as_text` | 1 |
| `spec4.agents.code_scanner` | `_approx_tokens` | 1 |
| `spec4.agents.code_scanner` | `_build_fresh_scan_seed` | 1 |
| `spec4.agents.code_scanner` | `_build_update_scan_seed` | 1 |
| `spec4.agents.deployer` | `_build_existing_infra_block` | 1 |
| `spec4.agents.deployer` | `build_readme_request` | 1 |
| `spec4.agents.designer` | `clear_session` | 1 |
| `spec4.agents.feature_speccer` | `_vision_features` | 1 |
| `spec4.agents.feature_speccer` | `_scaffold_feature` | 1 |
| `spec4.agents.feature_speccer` | `_validate_dependencies` | 2 |
| `spec4.agents.feature_speccer` | `_reconcile_dependencies` | 1 |
| `spec4.agents.phaser` | `_load_phaser_design_note` | 1 |
| `spec4.agents.phaser` | `_extract_and_strip_stack_additions` | 1 |
| `spec4.agents.phaser` | `_extract_phases` | 1 |
| `spec4.agents.phaser` | `_appears_truncated` | 1 |
| `spec4.agents.phaser` | `_phase_completeness_failure` | 1 |
| `spec4.agents.stack_advisor` | `_normalise_stack_shape` | 2 |
| `spec4.agents.stack_advisor` | `_extract_stack_json` | 3 |
| `spec4.agents.stack_advisor` | `_as_list` | 1 |
| `spec4.agents.stack_advisor` | `_label` | 1 |
| `spec4.agents.stack_advisor` | `_format_stack_as_text` | 5 |
| `spec4.app` | `on_version_check` | 1 |
| `spec4.callbacks` | `select_artifact` | 1 |
| `spec4.callbacks` | `on_round_tree_line` | 3 |
| `spec4.callbacks` | `on_artifact_round` | 1 |
| `spec4.callbacks` | `on_artifact_download` | 1 |
| `spec4.callbacks` | `on_setup_connect` | 3 |
| `spec4.callbacks` | `on_setup_back_provider` | 1 |
| `spec4.callbacks` | `on_setup_effort_options` | 1 |
| `spec4.callbacks` | `on_setup_model_continue` | 2 |
| `spec4.callbacks` | `on_search_provider_hint` | 1 |
| `spec4.callbacks` | `on_setup_search_connect` | 1 |
| `spec4.callbacks` | `on_setup_search_skip` | 1 |
| `spec4.callbacks` | `on_gate_provider_change` | 1 |
| `spec4.callbacks` | `on_gate_effort_options` | 1 |
| `spec4.callbacks` | `on_gate_use_default` | 1 |
| `spec4.callbacks` | `on_gate_keep` | 1 |
| `spec4.callbacks` | `on_gate_pick` | 2 |
| `spec4.callbacks` | `on_gate_chip` | 3 |
| `spec4.callbacks` | `on_chat_retry_model` | 1 |
| `spec4.callbacks` | `on_gate_connect` | 4 |
| `spec4.callbacks` | `on_chat_retry` | 1 |
| `spec4.callbacks` | `on_ff_info` | 1 |
| `spec4.callbacks` | `on_stream_poll` | 3 |
| `spec4.callbacks` | `_switch_agent` | 1 |
| `spec4.callbacks` | `on_project_mode_choice` | 1 |
| `spec4.callbacks` | `on_rescan_project` | 1 |
| `spec4.callbacks` | `_open_target` | 1 |
| `spec4.callbacks.designer` | `_extract_html` | 1 |
| `spec4.callbacks.designer` | `_persist_manifest` | 1 |
| `spec4.callbacks.designer` | `_expected_stream_chars` | 1 |
| `spec4.callbacks.designer` | `_start_gen` | 1 |
| `spec4.callbacks.designer` | `on_designer_carry_forward` | 2 |
| `spec4.callbacks.designer` | `on_designer_step_back` | 1 |
| `spec4.callbacks.designer` | `on_designer_start_over` | 1 |
| `spec4.callbacks.designer` | `on_designer_refine_upload` | 1 |
| `spec4.callbacks.designer` | `on_designer_refine_image_delete` | 1 |
| `spec4.callbacks.designer` | `on_designer_regenerate` | 1 |
| `spec4.callbacks.designer` | `on_designer_retry` | 1 |
| `spec4.callbacks.designer` | `on_designer_auto_retry` | 1 |
| `spec4.design_manifest` | `_surfaces` | 1 |
| `spec4.design_manifest` | `screens_of` | 1 |
| `spec4.feature_specs` | `_clean` | 1 |
| `spec4.feature_specs` | `_mechanism_definitions` | 1 |
| `spec4.layouts._agent_rows` | `_action_class` | 1 |
| `spec4.layouts._agent_rows` | `RowUsage` | 1 |
| `spec4.layouts._agent_rows` | `round_usage` | 1 |
| `spec4.layouts._artifact_view` | `ArtifactResolution` | 1 |
| `spec4.layouts._artifact_view` | `_rejected` | 1 |
| `spec4.layouts._artifact_view` | `_missing` | 1 |
| `spec4.layouts._artifact_view` | `_stat` | 1 |
| `spec4.layouts._artifact_view` | `_read` | 1 |
| `spec4.layouts._artifact_view` | `rendered_text` | 1 |
| `spec4.layouts._artifact_view` | `line_numbered` | 1 |
| `spec4.layouts._artifact_view` | `missing_message` | 1 |
| `spec4.layouts._artifact_view` | `rejection_message` | 1 |
| `spec4.layouts._artifact_view` | `artifact_controls` | 1 |
| `spec4.layouts._artifact_view` | `mock_html_for_store` | 1 |
| `spec4.layouts._artifact_view` | `round_id` | 1 |
| `spec4.layouts._artifact_view` | `round_value` | 1 |
| `spec4.layouts._chat` | `_cost_summary` | 1 |
| `spec4.layouts._chat` | `_streamed_token_count` | 3 |
| `spec4.layouts._chat` | `_token_count_text` | 6 |
| `spec4.layouts._chat` | `_turn_token_text` | 1 |
| `spec4.layouts._chat` | `_retry_panel` | 2 |
| `spec4.layouts._chat` | `_breadth_panel` | 2 |
| `spec4.layouts._round_cost` | `RoundCost` | 1 |
| `spec4.layouts._round_cost` | `CostFigures` | 1 |
| `spec4.layouts._round_cost` | `_unpriced_name` | 1 |
| `spec4.layouts._round_cost` | `cost_strip_lines` | 1 |
| `spec4.layouts._round_cost` | `run_cost_lines` | 1 |
| `spec4.layouts._shared` | `_fmt_usd` | 1 |
| `spec4.layouts._status_bar` | `_slot` | 1 |
| `spec4.layouts._status_bar` | `_dir_field` | 1 |
| `spec4.layouts.designer` | `_fullscreen_row` | 1 |
| `spec4.llm` | `_history_has_tool_use` | 1 |
| `spec4.llm` | `_is_tool_incompatible_error` | 1 |
| `spec4.llm` | `_is_effort_rejected_error` | 1 |
| `spec4.llm` | `_get` | 1 |
| `spec4.llm` | `_usage_fields` | 1 |
| `spec4.llm` | `_record_usage` | 1 |
| `spec4.project_manager` | `get_spec4_dir` | 1 |
| `spec4.project_manager` | `ensure_spec4_dir` | 1 |
| `spec4.project_manager` | `ensure_version_dir` | 6 |
| `spec4.project_manager` | `_write_text_if_changed` | 1 |
| `spec4.project_manager` | `_declared_ids` | 1 |
| `spec4.project_manager` | `parse_phase_markdown` | 4 |
| `spec4.project_manager` | `usage_totals` | 2 |
| `spec4.project_manager` | `unpriced_calls` | 1 |
| `spec4.providers` | `_json_get` | 2 |
| `spec4.providers` | `_fetch_models` | 1 |
| `spec4.session` | `NoModelConnectedError` | 1 |
| `spec4.session` | `_run_agent_blocking` | 1 |
| `spec4.session` | `_summarize_turn_usage` | 1 |
| `spec4.stack_routing` | `_spec` | 3 |
| `spec4.streaming` | `_format_error` | 1 |
| `spec4.usage_report` | `_rows` | 2 |
| `spec4.usage_report` | `render_usage_table` | 1 |
| `spec4.version_check` | `fetch_latest_version` | 1 |
| `spec4.version_check` | `is_outdated` | 1 |
| `spec4.version_check` | `_reset_cache` | 1 |
| `spec4.websearch` | `_endpoint` | 1 |
| `spec4.websearch` | `_url` | 1 |
| `spec4.websearch` | `_list_tools_async` | 1 |
| `spec4.websearch` | `_call_search_async` | 1 |

Total: 214

## 8. Module-level mutable state

`global` statements: **0** in `src/spec4`.

Module-level containers: 67 UPPERCASE containers (dicts, lists, sets, frozensets) were found; a grep for `.append/.update/.pop/.clear/.setdefault/.add/[k] =` against each name shows that **only the items below are mutated after import**. Everything else is a constant table.

| # | Location | Item | Kind | Mutation sites | Guard |
|---|---|---|---|---|---|
| 1 | `streaming.py:12-13` | `_STREAMS: dict[str, dict]`, `_lock = threading.Lock()` | registry of in-flight LLM streams | `:230-232` (evict done + insert), `:242/251/252` (text/error append from worker thread), `:311` pop | `_lock` on insert/get/pop; per-chunk appends at `:242-252` happen **without** the lock (worker thread writes, poll thread reads) |
| 2 | `llm.py:274-277` | `_USAGE_RECORDS: list[dict]`, `_USAGE_LOCK = threading.Lock()` | buffer of per-call usage records drained by `session` | `:468` append, `:284` clear | `_USAGE_LOCK` |
| 3 | `project_manager.py:1127` | `_USAGE_LOCK = threading.Lock()` | serializes usage-file read/modify/write | `:1468` | lock only; no container |
| 4 | `version_check.py:28` | `_cache: dict = {"checked": False, "result": None}` | once-per-process version check | `:76/81`, reset at `:87-88` (`_reset_cache`, test-only) | none (single-writer) |
| 5 | `callbacks/designer.py:54` | `_MOCK_BUFFERS: dict[str, dict]` | per-generation streaming buffers for the Designer mock | `:255/267` insert, `:786/801/821/866/990` pop | none, by documented design (single writer, GIL); comment at `:50-53` |
| 6 | `agentifier/agentifier.py:100-107` | `_registry = SubAgentRegistry()` | sub-agent registry | seven `.register()` calls at import; read-only afterwards | n/a (import-time only) |
| 7 | `feature_specs.py:305` | `@lru_cache(maxsize=1) _mechanism_definitions()` | process-lifetime cache of the pattern library | implicit | n/a; note it caches disk state for the process lifetime |
| 8 | `app.py:14-17, 41-65` | `os.environ.setdefault("LITELLM_LOG", "ERROR")`, `_litellm.suppress_debug_info = True`, `app = dash.Dash(...)`, `server = app.server` | import-time side effects and singletons | import only | load-bearing ordering (D-LR1, Rule 5). **Do not touch.** |

Also import-built but never mutated afterwards: `callbacks/__init__.py:2411 OPEN_ARTIFACT_CALLBACKS` (dict of registered callbacks, keyed for tests), `layouts/_chat.py:291 CHAT_ARTIFACTS`, and the `__all__` lists.

Phase 3 scope, then, is items 1–5 (four containers, three locks, one dict cache) plus the `lru_cache`. **Phase 1 (2026-09-08):** items 1, 2 and 5 are now pinned transition-by-transition by `tests/test_streaming_characterization.py`; see §12.2 for what the move must preserve and §12.4 items 8–12 for the oddities observed. Item 1 is the only one with a plausible concurrency gap (unlocked `_STREAMS[stream_id]["text"] +=` on the worker thread while `get_stream` reads under the lock on another); it is not a bug report because CPython's dict/str semantics make the observed effect at worst a stale read, but it should be looked at when the state moves. **Phase 3 (2026-09-08):** all eight items classified — every one is category (a) and stays module-scoped, each with a comment saying why and what guards it; the unlocked writes in item 1 are fixed. See §14.

## 9. Test inventory

116 test files under `tests/`, 3538 statically counted `test_*` functions (4118 collected after parametrization). Per file: the `spec4` modules imported (its targets) and the test count. A resolver check of every `patch("spec4...")` / `monkeypatch.setattr("spec4...")` string found **no target that no longer exists**. Tests exercising names in the §3 dead-code list: four files (`tests/agentifier/test_chars_counter_seed.py`, `test_try_again.py`, `test_search_level.py`, `test_agentifier_orchestrator.py`) plus `evals/agentifier/run_mechanism_probe.py` reference `_call_tier_analyst`, whose `valid_tier_names` parameter is the vulture 100% hit; `download_button_id` has no test.

| Test file | Tests | Targets (spec4 modules imported) |
|---|---:|---|
| `tests/agentifier/test_agentifier_orchestrator.py` | 67 | `spec4`, `spec4.agentifier`, `spec4.agentifier.agentifier`, `spec4.agentifier.scout`, `spec4.agentifier.tier_analyst`, `spec4.app_constants` |
| `tests/agentifier/test_chars_counter_seed.py` | 5 | `spec4.agentifier`, `spec4.agentifier.linker`, `spec4.agentifier.scout`, `spec4.agentifier.tier_analyst`, `spec4.app_constants` |
| `tests/agentifier/test_composer.py` | 16 | `spec4.agentifier.composer`, `spec4.agentifier.scout` |
| `tests/agentifier/test_cross_cutting_analyst.py` | 32 | `spec4.agentifier.agentifier`, `spec4.agentifier.cross_cutting_analyst`, `spec4.agentifier.pattern_loader`, `spec4.llm` |
| `tests/agentifier/test_edge_persistence.py` | 22 | `spec4.agentifier.agentifier`, `spec4.agentifier.scout`, `spec4.agents._utils` |
| `tests/agentifier/test_fanout_baseline.py` | 5 | — (no spec4 import) |
| `tests/agentifier/test_ff_sweep.py` | 22 | `spec4.agentifier.agentifier`, `spec4.app_constants`, `spec4.callbacks` |
| `tests/agentifier/test_infra_expander.py` | 16 | `spec4.agentifier.infra_expander` |
| `tests/agentifier/test_infra_registry.py` | 10 | `spec4.agentifier.pattern_loader` |
| `tests/agentifier/test_linker.py` | 25 | `spec4.agentifier.linker`, `spec4.agentifier.scout` |
| `tests/agentifier/test_linker_edges.py` | 23 | `spec4.agentifier.linker`, `spec4.agentifier.scout` |
| `tests/agentifier/test_panel_closure.py` | 25 | `spec4.agentifier.panel_closure`, `spec4.agentifier.scout` |
| `tests/agentifier/test_pattern_loader.py` | 17 | `spec4.agentifier.pattern_loader` |
| `tests/agentifier/test_prioritizer.py` | 90 | `spec4.agentifier.agentifier`, `spec4.agentifier.prioritizer` |
| `tests/agentifier/test_reference_verifier.py` | 22 | `spec4.agentifier.reference_verifier` |
| `tests/agentifier/test_requires_reconciler.py` | 11 | `spec4.agentifier.requires_reconciler` |
| `tests/agentifier/test_reselection.py` | 8 | `spec4.agentifier`, `spec4.agentifier.agentifier`, `spec4.app_constants` |
| `tests/agentifier/test_revision.py` | 26 | `spec4.agentifier`, `spec4.agentifier.agentifier`, `spec4.agentifier.scout`, `spec4.agentifier.tier_analyst` |
| `tests/agentifier/test_scout.py` | 45 | `spec4.agentifier.scout` |
| `tests/agentifier/test_search_level.py` | 23 | `spec4.agentifier.agentifier`, `spec4.agentifier.composer`, `spec4.agentifier.linker`, `spec4.agentifier.scout`, `spec4.agentifier.tier_analyst`, `spec4.session` |
| `tests/agentifier/test_spec_drafter.py` | 33 | `spec4.agentifier.agentifier`, `spec4.agentifier.pattern_loader`, `spec4.agentifier.spec_drafter`, `spec4.llm` |
| `tests/agentifier/test_streaming_e2e.py` | 30 | `spec4.agentifier.agentifier`, `spec4.agentifier.pattern_loader`, `spec4.agentifier.spec_drafter`, `spec4.agentifier.subagents`, `spec4.app_constants`, `spec4.session` |
| `tests/agentifier/test_subagents.py` | 20 | `spec4.agentifier.subagents` |
| `tests/agentifier/test_tier_analyst.py` | 34 | `spec4.agentifier.pattern_loader`, `spec4.agentifier.scout`, `spec4.agentifier.tier_analyst` |
| `tests/agentifier/test_try_again.py` | 43 | `spec4.agentifier`, `spec4.agentifier.agentifier`, `spec4.agentifier.scout`, `spec4.agentifier.tier_analyst`, `spec4.app_constants`, `spec4.callbacks`, `spec4.layouts._chat`, `spec4.session` |
| `tests/agentifier/test_vision_grounding.py` | 34 | `spec4.agentifier.agentifier`, `spec4.agentifier.grounding`, `spec4.agentifier.spec_drafter` |
| `tests/integration/test_artifact_view_e2e.py` | 31 | — (no spec4 import) |
| `tests/integration/test_chat_frame_e2e.py` | 22 | `spec4` |
| `tests/integration/test_page_slot_e2e.py` | 2 | `spec4.app` |
| `tests/integration/test_pipeline_brownfield.py` | 20 | `spec4.agentifier.agentifier`, `spec4.agentifier.cross_cutting_analyst`, `spec4.agentifier.pattern_loader`, `spec4.agentifier.scout`, `spec4.agentifier.spec_drafter`, `spec4.agentifier.tier_analyst`, `spec4.session` |
| `tests/integration/test_pipeline_greenfield.py` | 11 | `spec4.agentifier.agentifier`, `spec4.agents.deployer`, `spec4.agents.phaser`, `spec4.agents.stack_advisor`, `spec4.app_constants`, `spec4.session` |
| `tests/test_agent_button_state.py` | 17 | `spec4`, `spec4.project_manager` |
| `tests/test_agent_llm_selection.py` | 153 | `spec4`, `spec4.app_constants`, `spec4.callbacks`, `spec4.callbacks.designer`, `spec4.layouts`, `spec4.layouts._chat`, `spec4.layouts._llm_gate`, `spec4.layouts._setup`, `spec4.layouts._status_bar`, `spec4.layouts.designer`, `spec4.project_manager`, `spec4.session` |
| `tests/test_agent_pill_click.py` | 15 | `spec4`, `spec4.callbacks` |
| `tests/test_agent_rows.py` | 62 | `spec4`, `spec4.app_constants`, `spec4.layouts`, `spec4.layouts._agent_rows`, `spec4.session` |
| `tests/test_agent_select_layout.py` | 4 | `spec4.layouts`, `spec4.session` |
| `tests/test_agentifier_chars_counter.py` | 15 | `spec4.agents._utils`, `spec4.app_constants`, `spec4.layouts._chat` |
| `tests/test_agents.py` | 278 | `spec4`, `spec4.agents`, `spec4.agents._code_review_schema`, `spec4.agents._phase_schema`, `spec4.agents._utils`, `spec4.agents.brainstormer`, `spec4.agents.code_scanner`, `spec4.agents.deployer`, `spec4.agents.phaser`, `spec4.app_constants` |
| `tests/test_app_constants.py` | 26 | `spec4.app_constants` |
| `tests/test_artifact_view.py` | 164 | `spec4`, `spec4.app`, `spec4.app_constants`, `spec4.callbacks`, `spec4.layouts`, `spec4.layouts._agent_rows`, `spec4.layouts._artifact_view`, `spec4.layouts._round_tree`, `spec4.layouts._status_bar`, `spec4.session` |
| `tests/test_brainstormer_chars_counter.py` | 11 | `spec4.agents`, `spec4.app_constants`, `spec4.layouts._chat` |
| `tests/test_callback_co_presence.py` | 44 | `spec4`, `spec4.app`, `spec4.app_constants`, `spec4.callbacks`, `spec4.layouts`, `spec4.layouts._chat`, `spec4.layouts._status_bar`, `spec4.layouts.designer`, `spec4.session` |
| `tests/test_callbacks_stream_poll.py` | 42 | `spec4.callbacks`, `spec4.layouts._chat`, `spec4.session` |
| `tests/test_chat_action_row_emphasis.py` | 10 | `spec4.app_constants`, `spec4.layouts._chat` |
| `tests/test_chat_input_asset.py` | 6 | — (no spec4 import) |
| `tests/test_chat_open_links.py` | 26 | `spec4`, `spec4.callbacks`, `spec4.layouts._artifact_view`, `spec4.layouts._chat`, `spec4.layouts._round_tree`, `spec4.session` |
| `tests/test_chat_pill_bar.py` | 21 | `spec4.app_constants`, `spec4.layouts._agent_rows`, `spec4.layouts._chat`, `spec4.layouts._shared`, `spec4.session` |
| `tests/test_chat_transcript_blocks.py` | 26 | `spec4.layouts._chat`, `spec4.layouts._llm_gate`, `spec4.layouts._shared` |
| `tests/test_code_scanner_progress.py` | 44 | `spec4.agents`, `spec4.app`, `spec4.app_constants`, `spec4.layouts._chat` |
| `tests/test_completion_helpers.py` | 29 | `spec4.agentifier.cross_cutting_analyst`, `spec4.agentifier.pattern_loader`, `spec4.agentifier.scout`, `spec4.agentifier.spec_drafter`, `spec4.agentifier.tier_analyst`, `spec4.llm` |
| `tests/test_cost_summary.py` | 37 | `spec4`, `spec4.app_constants`, `spec4.layouts._chat`, `spec4.layouts._round_cost`, `spec4.layouts._shared`, `spec4.layouts.designer`, `spec4.session` |
| `tests/test_cross_cutting_relocation.py` | 8 | `spec4.agents._utils`, `spec4.agents.deployer`, `spec4.agents.stack_advisor` |
| `tests/test_dependency_reconciliation.py` | 9 | `spec4.agents` |
| `tests/test_deployer_ai_channel.py` | 15 | `spec4.agents._utils` |
| `tests/test_deployer_chars_counter.py` | 8 | `spec4.agents`, `spec4.agents._utils`, `spec4.app_constants`, `spec4.layouts._chat` |
| `tests/test_deployer_env_and_semantics.py` | 16 | `spec4.agents.deployer` |
| `tests/test_deployer_invariants.py` | 9 | `spec4`, `spec4.agents`, `spec4.agents.deployer` |
| `tests/test_deployer_nfr_channel.py` | 11 | `spec4.agents._utils` |
| `tests/test_deployer_nfr_guidance.py` | 16 | `spec4.agents.deployer` |
| `tests/test_deployer_phases_context.py` | 12 | `spec4.agents._utils` |
| `tests/test_deployer_reentry.py` | 2 | `spec4.agents` |
| `tests/test_deployer_stack_digest.py` | 17 | `spec4.agents._utils` |
| `tests/test_design_manifest.py` | 10 | `spec4.design_manifest` |
| `tests/test_designer.py` | 161 | `spec4`, `spec4.agents._manifest`, `spec4.agents.designer`, `spec4.callbacks`, `spec4.callbacks.designer`, `spec4.layouts._shared`, `spec4.layouts.designer`, `spec4.session` |
| `tests/test_designer_fullscreen.py` | 7 | `spec4.app`, `spec4.callbacks.designer`, `spec4.layouts.designer` |
| `tests/test_designer_wizard_register.py` | 41 | `spec4`, `spec4.app`, `spec4.callbacks.designer`, `spec4.layouts`, `spec4.layouts._round_cost`, `spec4.layouts.designer`, `spec4.session` |
| `tests/test_drain_stream.py` | 8 | `spec4.agents._utils` |
| `tests/test_entry_screens.py` | 21 | `spec4`, `spec4.app_constants`, `spec4.layouts`, `spec4.session` |
| `tests/test_fast_forward.py` | 18 | `spec4.app_constants`, `spec4.callbacks`, `spec4.layouts._chat` |
| `tests/test_feature_ids.py` | 13 | `spec4.agents`, `spec4.agents._phase_coverage`, `spec4.agents._utils`, `spec4.app_constants` |
| `tests/test_feature_speccer_generative.py` | 17 | `spec4.agents`, `spec4.app_constants` |
| `tests/test_feature_specs.py` | 28 | `spec4.feature_specs` |
| `tests/test_feature_specs_pass.py` | 13 | `spec4`, `spec4.agents`, `spec4.agents._utils`, `spec4.app_constants`, `spec4.session` |
| `tests/test_image_probe.py` | 7 | `spec4.agents._image_probe` |
| `tests/test_llm.py` | 62 | `spec4` |
| `tests/test_manifest.py` | 18 | `spec4.agents._manifest` |
| `tests/test_phase_coverage.py` | 37 | `spec4.agents._phase_coverage` |
| `tests/test_phaser_feature_specs_context.py` | 14 | `spec4.agents._utils` |
| `tests/test_phaser_manifest_context.py` | 8 | `spec4.agents._utils` |
| `tests/test_phaser_seed_inputs.py` | 12 | `spec4.agents`, `spec4.app_constants`, `spec4.project_manager` |
| `tests/test_phaser_stack_digest.py` | 14 | `spec4.agents._utils` |
| `tests/test_project_manager.py` | 118 | `spec4`, `spec4.app_constants`, `spec4.session` |
| `tests/test_project_mode.py` | 34 | `spec4`, `spec4.app_constants`, `spec4.layouts`, `spec4.layouts.designer`, `spec4.session` |
| `tests/test_providers.py` | 19 | `spec4.providers` |
| `tests/test_revision_change_classification.py` | 13 | `spec4.agents.brainstormer` |
| `tests/test_root_routing.py` | 42 | `spec4.app`, `spec4.app_constants`, `spec4.callbacks`, `spec4.layouts`, `spec4.project_manager`, `spec4.session` |
| `tests/test_round_cost.py` | 33 | `spec4`, `spec4.callbacks`, `spec4.layouts`, `spec4.layouts._round_cost`, `spec4.layouts._shared`, `spec4.session` |
| `tests/test_round_tree.py` | 75 | `spec4`, `spec4.app_constants`, `spec4.callbacks`, `spec4.layouts`, `spec4.layouts._round_tree`, `spec4.session` |
| `tests/test_seam_check.py` | 36 | `spec4.agents`, `spec4.agents._seam_check` |
| `tests/test_session.py` | 61 | `spec4`, `spec4.agents`, `spec4.app_constants`, `spec4.session` |
| `tests/test_setup_search_provider.py` | 19 | `spec4`, `spec4.callbacks`, `spec4.layouts._setup` |
| `tests/test_setup_wizard_register.py` | 50 | `spec4`, `spec4.app_constants`, `spec4.callbacks`, `spec4.layouts`, `spec4.layouts._llm_gate`, `spec4.layouts._setup` |
| `tests/test_stack_additions.py` | 21 | `spec4.agents.phaser`, `spec4.project_manager`, `spec4.stack_routing` |
| `tests/test_stack_advisor_token_counter.py` | 15 | `spec4.agents._utils`, `spec4.layouts._chat` |
| `tests/test_stack_ai_features_context.py` | 34 | `spec4.agents._utils` |
| `tests/test_stack_design_manifest_context.py` | 10 | `spec4.agents._utils` |
| `tests/test_stack_exemplar_demonstrates_linkage.py` | 9 | `spec4.agents.stack_advisor` |
| `tests/test_stack_feature_specs_context.py` | 19 | `spec4.agents._utils` |
| `tests/test_stack_output_rendering.py` | 15 | `spec4.agents.stack_advisor` |
| `tests/test_stack_persistence_block.py` | 49 | `spec4.agents.stack_advisor` |
| `tests/test_stack_render_totality.py` | 10 | `spec4.agents.stack_advisor` |
| `tests/test_stack_routing.py` | 18 | `spec4.stack_routing` |
| `tests/test_stack_shape_resilience.py` | 17 | `spec4.agents`, `spec4.agents.stack_advisor`, `spec4.app_constants` |
| `tests/test_stale_ai_features.py` | 9 | `spec4`, `spec4.agents`, `spec4.session` |
| `tests/test_status_bar.py` | 67 | `spec4`, `spec4.app`, `spec4.app_constants`, `spec4.callbacks`, `spec4.layouts`, `spec4.layouts._status_bar`, `spec4.session` |
| `tests/test_step_row.py` | 22 | `spec4.layouts._shared` |
| `tests/test_stream_error_recovery.py` | 49 | `spec4`, `spec4.callbacks`, `spec4.layouts._chat`, `spec4.session` |
| `tests/test_stream_status.py` | 15 | `spec4`, `spec4.agentifier`, `spec4.agents`, `spec4.agents._utils` |
| `tests/test_streaming.py` | 21 | `spec4`, `spec4.streaming` |
| `tests/test_tool_probe.py` | 8 | `spec4.agents._tool_probe` |
| `tests/test_usage_capture.py` | 77 | `spec4`, `spec4.agents`, `spec4.agents.designer`, `spec4.app_constants`, `spec4.callbacks`, `spec4.layouts._chat`, `spec4.session` |
| `tests/test_utils.py` | 21 | `spec4.agents._utils` |
| `tests/test_version_check.py` | 17 | `spec4`, `spec4.app`, `spec4.version_check` |
| `tests/test_vision_disk_reconciliation.py` | 9 | `spec4`, `spec4.agents`, `spec4.app_constants` |
| `tests/test_visual_register.py` | 18 | `spec4.app_constants`, `spec4.layouts._shared` |
| `tests/test_websearch.py` | 36 | `spec4`, `spec4.agents`, `spec4.websearch` |

Total test files: 116; total test functions (static count): 3538

Observations for Phase 6:

- Test files with no `spec4` import at all (pure fixture or helper modules) are marked "— (no spec4 import)" above.
- Heavy overlap on `spec4.agents` + `spec4.app_constants` + `spec4.session` across the many `test_deployer_*`, `test_phaser_*`, `test_stack_*` files: fifteen-plus files target the same three modules. Candidates for consolidation by source module.
- `tests/test_agents.py` (5,284 lines, 333 tests) is the single largest file in the repo and targets several agents at once.
- `--durations` was not run in Phase 0 (it belongs to Phase 6). Wall-clock for the full suite is 166 s; the three browser E2E modules in `tests/integration/` each start a subprocess Dash server (see memory note: in-process servers break other modules).

### 9.1 `tests/README.md` is stale (flag for Phase 7)

- Dated 2026-04-28, "Phase 1", "Total 96% (1435 statements)". Current: 11,676 statements, 91%.
- Refers to `spec4/layouts.py` and `spec4/callbacks.py` as single files at 0%; both are now packages (`layouts/` 10 modules at 90–100%, `callbacks/` 2 modules at 74–77%). `streaming.py` is listed at 0%; it is at 90%.
- Line-number references (e.g. `phaser.py` lines 255-262) predate every agent rewrite and are meaningless now.
- Says `llm.py` was "formerly `tavily_mcp.py`"; still true historically but the module is now 997 lines and 95% covered.
- Rewrite in Phase 7 from the §1.3 table, or replace with a pointer to `uv run pytest --cov`.

## 10. Bugs found (not fixed)

1. ~~**`test_no_transcript_block_is_filled` fails deterministically** on `look-rework` (§1.1). `.chat-msg` elements on `/chat` resolve to `rgb(18, 18, 26)` (`#12121a`, `app_constants.py:88`) rather than transparent. Either the look rework intends filled transcript blocks and the test needs updating, or a stylesheet change leaked a background onto `.chat-msg`. Decide before Phase 1, since Phase 1 builds the UI safety net on top of this suite.~~ **Resolved in Phase 0.5c (2026-09-08):** the filled user turns are the intended look. The test was replaced by `test_user_turns_are_filled_and_agent_turns_are_not`, which asserts the intended styling.
2. ~~**`agentifier/agentifier.py:2262`: `topics` redefined** (mypy `no-redef`, `line 2221` first definition). Not necessarily a behavior bug, but the two definitions have different types; worth a look when Phase 4 touches `_run_cross_cutting_phase`.~~ **Resolved in Phase 0.5b (2026-09-08):** not a bug. Both assignments hold a `list[str]`; the first was inferred as `Any` from `session.get`. Annotation moved to the first assignment, no logic change.
3. ~~**`project_manager.py:1894/1903`: `float` compared with `None`** (mypy `operator`). If the `None` branch is reachable this raises `TypeError` at runtime. Verify in Phase 3 or 5.~~ **Resolved in Phase 0.5b (2026-09-08):** not a bug. The `None` branch is unreachable: the preceding comprehension filters `m is not None`, mypy just could not see it through the rebinding of `chain`. The filtered list is now bound to an annotated `chain: list[tuple[str, float]]`, no logic change.
4. ~~**`layouts/designer.py:629`: `active_version(working_dir, session)` called with `working_dir: str | None`** (mypy `arg-type`, the one Phase 0.5b error left in place). When the session has no `working_dir` and no pinned `phase_version`, `active_version` falls through to `latest_phase_version(None)` → `get_spec4_dir(None)` → `Path(None)`, which raises `TypeError`. `_design_dir` on the next line already accepts `None`, so the surrounding code expects the no-project case to render. Fixing it needs a guard (a logic change), so it is logged here rather than fixed. Mypy is ratcheted to 1 error until this is decided.~~ **Resolved after Phase 0.5c (2026-09-08):** the round lookup is now skipped when there is no `working_dir` (version `0`, which only names a path every later read already guards on). Reproduced and covered by `tests/test_designer.py::TestDesignerLayoutWithoutProject`. Mypy is at 0 errors.

## 11. Deferred to later phases (noted here, not acted on)

- Resolved before Phase 2: `.coverage` is untracked (commit `f859376`) and listed in `.gitignore`; the pytest rewrite-in-place no longer dirties the tree.
- Phase 2: `dash-iconify` removal from `[project.dependencies]` + mypy override; `download_button_id`; `CODE_REVIEW_SCHEMA_VERSION`; the `valid_tier_names` parameter; `PatternBase`/`PriorityEdits` visibility; the 15 public zero-importer names in §7; the 22 test-side vulture lines.
- ~~Phase 3: the eight items in §8.~~ **Done (2026-09-08), §14.** All eight are category (a); the one (c) found was `version_check._reset_cache`, which moved to a fixture.
- Phase 4: ~~break the `layouts` ↔ `layouts._chat` cycle~~ **done (2026-09-08), §21** — the package import in `_chat.py` became a sibling import of `_llm_gate`; the whole of `src/spec4/` is now acyclic; ~~decide the fate of `session.py` as the UI/agent hinge~~ **decided (2026-09-08, §15.3): keep it, not a Phase 4 split — its issue is layering, not size**; ~~write the import-assertion test (§6.3)~~ **done (2026-09-08), `tests/test_import_layering.py`, §15**; split the eight files over 1,300 lines (order proposed in §15.3, starting at 4a).
- Phase 5: the 61 C901 functions, starting with the table in §5.1; the 26 small SIM/B hits; the remaining renderer/artifact cosmetics in §12.4 (items 2, 3, 6, 7 and the open halves of 4 and 5) (goldens in `tests/golden/` pin the current output, so each fix is a deliberate golden update).
- Phase 6: consolidate `test_deployer_*` / `test_phaser_*` / `test_stack_*`; split `test_agents.py`; run `--durations`; the 162 test-side ARG hits are not targets; the screen-registry overlap in §12.5.
- Phase 7: rewrite `tests/README.md`; rerun every command in this file and diff against the numbers here.

## Appendix A. Commands used

```
uv run pytest --cov=spec4 --cov-report=term-missing -q
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
uvx vulture src/ tests/ --min-confidence 60
uvx vulture src/ tests/ vulture_whitelist.py --min-confidence 60
uv run ruff check --select F401,F811,F841,ARG --statistics src/ tests/
uvx deptry .
uv run ruff check --select C90,PLR0912,PLR0913,PLR0915,SIM,B --statistics src/
uv run ruff check --select C90,PLR0912,PLR0913,PLR0915,SIM,B --output-format concise src/
```

The file-size table, import graph, cross-reference and test inventory were produced by throwaway `ast`-based scripts run from the session scratchpad; they are not part of the repo.


## 12. Phase 1 report — regression safety net for the UI layer

Recorded 2026-09-08 on branch `look-rework`. Tests only: nothing under `src/` changed, `pyproject.toml` is untouched, no existing test file was edited. Nothing was written under `.spec4/`, `.venv/` or `.git/`, and no git command was run.

**Premise correction.** The plan's Phase 1 text says `app.py`, `layouts/`, `callbacks` and `streaming.py` are at 0%. §1.3 and §9.1 already showed that to be stale (89%, 90–100%, 74–77%, 90%). Phase 1 therefore added *contract* tests — an id snapshot, goldens, and container-contents characterization — rather than first-time coverage. The per-module numbers below are the Phase 1 baseline for Rule 6 regardless.

### 12.1 Files added

| Path | Purpose |
|---|---|
| `tests/_golden.py` | `assert_golden(name, text)` and `load_fixture(name)`. Goldens live in `tests/golden/`, fixtures in `tests/golden/fixtures/`. `SPEC4_UPDATE_GOLDENS=1` rewrites goldens; otherwise a mismatch fails with a unified diff. |
| `tests/test_layout_contract.py` | 74 tests. A registry of 72 screens built by calling every public layout function directly (`_working_dir_layout`, `_setup_layout` ×5, `_agent_select_layout` ×5, `_chat_layout` ×31 across the six chat agents, `designer_layout` ×4 plus the seven `_stepN_content` builders ×14, `_artifact_view_layout` ×7, `_status_bar`/`_status_context` ×3). **Smoke:** each returns a Dash component tree and `to_plotly_json()` serialises it. **Snapshot:** per screen, the sorted string ids and pattern-matching id `type`s equal `tests/snapshots/component_ids.json` (`SPEC4_UPDATE_SNAPSHOTS=1` regenerates). This is Rule 4 for component ids, enforced in the direction `test_callback_co_presence.py` does not cover. |
| `tests/snapshots/component_ids.json` | The checked-in id contract: 72 screens, reviewed by eye — every id is recognisable from `src/spec4/layouts/`. |
| `tests/test_app_import_smoke.py` | 2 tests. A subprocess whose *first* import is `spec4.app` (D-LR1 exercised as at startup) reports: `LITELLM_LOG=ERROR` set, `litellm.suppress_debug_info` True, both callback modules imported, the callback registry populated with `render_page`'s output present, `app.layout` a `MantineProvider`, the `page-content` slot carrying `disable_n_clicks=True`; and `main()` with `--version` prints `spec4 <__version__>` and exits 0. |
| `tests/test_streaming_characterization.py` | 16 tests over the three Phase 3 containers, asserting **contents** at each transition (see 12.2). |
| `tests/test_project_manager_golden.py` | 17 tests. `render_phase_markdown` with and without a context against `phase_full.md` / `phase_final.md` / `phase_full_no_context.md` / `phase_minimal.md`; frontmatter round-trip through `parse_phase_markdown`; frontmatter format (`json.dumps(indent=2, ensure_ascii=False)`); `save_phases` file set, stale-file removal, `IMPLEMENTED` marker untouched, unchanged re-save keeps mtime; `save_readme` footer exactly once, idempotent re-save, mid-document footer moved to the end, footer-only and empty inputs; `load_existing_readme`. The `phase_context.json` fixture drives every branch of `_phase_spec_preamble`, `_phase_stack_lines` and `_phase_nfr_lines` (known and unknown product/capability ids, plain and catalog-backed surfaces, dependency and entities lines, the served-features relation, cross-cutting with the excluded `provider_strategy`, global-NFR-in-final-phase). |
| `tests/test_renderer_goldens.py` | 22 tests. Goldens for all five renderers: `_format_stack_as_text` (full, minimal, bare-string blocks, non-dict input, `stack`/bare-key aliases), `_format_review_as_text` (full v1 schema, string-shaped fields, `is_software_project: false` ×4 variants, typed notes with no tests/no CI, empty input), `_format_vision_as_text` (full, vision-as-string, no name + string monetization, review footer), `_format_catalog_as_text` (mixed decisions and a >60-char rationale, empty, missing key), `_format_spec_as_text` (every `_field` shape, `tier` fallback). |
| `tests/golden/*.md` (25 files), `tests/golden/fixtures/*.json` (20 files) | The pinned outputs and their inputs. |

Total: 131 new tests, all deterministic (the streaming module was run repeatedly with no flake; its generators are gated on `threading.Event`s, not sleeps).

### 12.2 What the streaming characterization pins (Phase 3 must keep every line)

`streaming._STREAMS`
- `start()` inserts exactly `{"text": "", "done": False, "session": <the same dict object>, "error": False, "finalised": False}` before the worker yields; `get()` returns that object by identity.
- `text` accumulates chunk by chunk with `done` still False; on exhaustion `done` flips True, `error` stays False, `finalised` stays False.
- `claim_finalise` is True once then False; it does not evict. A missing id is False.
- The next `start()` evicts every `done` entry and only those; a live entry survives a second `start()`.
- `pop()` removes and returns; a second `pop`/`get` is None.
- An exception after partial output leaves `text == partial + _format_error(exc)` and `error True` (both the JSON-bodied litellm shape and a plain `RuntimeError`).
- Agent writes to the session dict (`_stream_status`, `_stream_received_chars`) are visible through `entry["session"]` — the poll's channel.

`llm._USAGE_RECORDS` (through a real `stream_turn` with `litellm.completion` patched, and the real `on_stream_poll` done branch)
- One record per call with exactly these 16 keys: `timestamp, agent, model, provider, effort, streamed, duration_s, prompt_tokens, completion_tokens, total_tokens, cached_tokens, cache_creation_input_tokens, cache_read_input_tokens, computed_cost_usd, usage_missing, error`.
- The first done-poll drains the sink to `[]`, writes `.spec4/v0/usage.json` (greenfield pins round **0**), returns `_stream_id None`, `_stream_error None`, `_turn_usage == {"agent","input":120,"output":30,"calls":1,"missing":0}`, interval 0; the entry stays in `_STREAMS` with `finalised True`.
- The second done-poll returns an `==` store, drains nothing, and leaves `usage.json` byte-identical.
- A call with no usage is still recorded (`usage_missing True`, token fields None, `error` carried).
- An error stream finalises with `_stream_error True` and a zero-call turn summary.

`callbacks.designer._MOCK_BUFFERS` (through the real `_start_gen` with `generate_mock_streaming` patched)
- `_start_gen` inserts exactly `{"done": False, "stop": Event(unset), "text": "", "expected_chars": 70000}` and returns a step-5 store with `_gen_id`; the buffer returned is `{"tokens": 0, "progress": 0, "error": None}`.
- Mid-stream poll: `(progress buffer, no_update, no_update)` with `progress == min(99, tokens*100//expected)` — **0 for a short stream**.
- On `__DONE__`: the worker sets `final_html`, `done True`, and saves `design/mock.html` under the session-pinned version.
- Step-5 poll: `(final_buf + {"complete": store6}, store6, no_update)`, `delivered` increments each tick, buffer kept; identical payload on every tick.
- Poll with the store off step 5: `(final_buf, no_update, True)` and the buffer is popped; a poll for a gone id is `(no_update, no_update, True)`.
- `__GENERATION_ERROR__: bad` → `({"error": "bad"}, no_update, True)`, popped. No HTML document → the worker appends the "did not return a valid HTML document" sentinel and the poll reports it.
- A stopped stream with no sentinel → `done True`, no `final_html`, poll pops and disables.
- A new `_start_gen` pops the previous gen's entry and sets its `stop` event; the orphaned worker finishes without writing back.
- `delivered > _MAX_DELIVERY_TICKS` → the "Refresh the page" error, popped.

### 12.3 Coverage after Phase 1 (`uv run pytest --cov=spec4`)

The four UI targets (Phase 1 baseline; Rule 6 ratchets against the last column from here):

| Module | Stmts | Miss | Phase 0 | Phase 1 |
|---|---:|---:|---:|---:|
| `src/spec4/app.py` | 72 | 8 | 89% | **89%** |
| `src/spec4/callbacks/__init__.py` | 681 | 157 | 77% | **77%** |
| `src/spec4/callbacks/designer.py` | 427 | 109 | 74% | **74%** |
| `src/spec4/layouts/__init__.py` | 70 | 3 | 90% | **96%** |
| `src/spec4/layouts/_agent_rows.py` | 86 | 3 | 97% | **97%** |
| `src/spec4/layouts/_artifact_view.py` | 196 | 7 | 96% | **96%** |
| `src/spec4/layouts/_chat.py` | 181 | 2 | 99% | **99%** |
| `src/spec4/layouts/_llm_gate.py` | 55 | 0 | 100% | **100%** |
| `src/spec4/layouts/_round_cost.py` | 70 | 0 | 100% | **100%** |
| `src/spec4/layouts/_round_tree.py` | 113 | 0 | 100% | **100%** |
| `src/spec4/layouts/_setup.py` | 70 | 1 | 97% | **99%** |
| `src/spec4/layouts/_shared.py` | 83 | 0 | 100% | **100%** |
| `src/spec4/layouts/_status_bar.py` | 45 | 0 | 100% | **100%** |
| `src/spec4/layouts/designer.py` | 159 | 12 | 92% | **92%** |
| `src/spec4/streaming.py` | 192 | 18 | 90% | **91%** |

No non-UI module dropped below its §1.3 figure. Modules that moved: `agentifier/agentifier.py` 88→89, `agents/brainstormer.py` 91→97, `agents/code_scanner.py` 89→97, `agents/stack_advisor.py` 91→98, `feature_specs.py` 76→77, `layouts/__init__.py` 90→96, `layouts/_setup.py` 97→99, `project_manager.py` 96→97, `streaming.py` 90→91. Everything else is unchanged. **TOTAL 91% → 92%.**

Pinned-function line coverage, measured from the full suite: `_format_stack_as_text` (935–1171), `_format_review_as_text` (1089–1251), `_format_empty_review`, `_render_typed_notes`, `_format_vision_as_text` (504–574), `_format_catalog_as_text` (737–753), `_format_spec_as_text` (794–872), `_phase_spec_preamble` (468–654), `_phase_stack_lines`, `_phase_nfr_lines`, `render_phase_markdown`, `save_phases`, `_with_readme_attribution` — **no unhit lines in any of them.** Phase 5 can decompose against the goldens with nothing unmeasured.

Other numbers for later phases: the subprocess import registers **92 callbacks** in `GLOBAL_CALLBACK_MAP` (Phase 2 must not change this; the smoke test asserts only `> 0`). The full suite is 4249 passed + 1 skipped in ~176 s; the three browser E2E modules ran.

### 12.4 Oddities captured as-is (not fixed; candidates for later phases)

Renderer and artifact output (visible in the goldens):
1. ~~`phase_full.md`: the AI-capability block renders `**Inputs**` and `**Failure modes**` headings with empty bodies when `ai_features[].inputs` / `failure_modes` are lists of strings — `feature_specs.render_feature_block` evidently expects another shape. The product-feature block renders its `success_criteria` list fine. Phase 5 (`feature_specs.render_feature_block`).~~ **Resolved after Phase 1 (2026-09-08):** the empty-body guard in `_render_inputs` / `_render_failure_modes` (`feature_specs.py`) compared against the wrong length (the heading plus two blank lines is already three lines), so a heading with no items was never dropped. Guard corrected; string-shaped items are still skipped as before. Golden `phase_full.md` updated (the two empty headings gone, nothing else).
2. `phase_full.md`: in the UI-surfaces block, the sentence "The following surface(s) realize…" follows a list item with no blank line, so Markdown reads it as a lazy continuation of the bullet. Cosmetic; Phase 5.
3. `phase_*.md`: two blank lines between the NFR block and `## References` (`_phase_nfr_lines` ends with `""` and `render_phase_markdown` appends another). Cosmetic; Phase 5.
4. ~~`render_stack_full.md`: a library category whose list is empty (`"deferred": []`) still emits its `*Deferred:*` heading; a category given as a string renders as `*Frontend:*` / `- Frontend: …` (label doubled).~~ **Resolved after Phase 1 (2026-09-08):** empty categories are skipped and a scalar category renders as a single library entry (`_format_stack_as_text`, two lines). Golden `render_stack_full.md` updated (the doubled label and the orphan heading, nothing else). **Still open, Phase 5:** the top-level fall-through (`_render_rest(ss, _TOP_LEVEL_HANDLED, …)`) is emitted after `**References:**` and the closing `---` is glued to its last line with no blank line.
5. ~~`render_review_full.md`: a `directory_map` entry with no `path` renders as the Python repr `{'role': 'no path'}`.~~ **Resolved after Phase 1 (2026-09-08):** a path-less entry now renders its role alone, and an entry with neither is skipped (`code_scanner._format_review_as_text`). Golden `render_review_full.md` updated (that one line). **Still open, Phase 5:** an `api_surface` entry renders `— → \`handler\`` (dash then arrow).
6. `render_catalog.md`: an entry with no `name`/`tier_decision` renders `|  | none |  (mismatch) |`. Phase 5, or a schema question.
7. `agentifier.py:800–801`: `_format_spec_as_text` has its docstring twice (two identical string literals). Phase 5.

State containers (add to §8):
8. ~~`streaming.py:242/251/252`: the worker thread's `_STREAMS[stream_id]["text"] += chunk` and `["error"] = True` run **without** `_lock`, while `get()` and `claim_finalise()` take it. Observed effect is at worst a stale read; noted again here because the characterization test now reads `entry["text"]` from the test thread exactly this way. Phase 3.~~ **Fixed in Phase 3 (2026-09-08):** the worker writes through the `entry` already in its closure, under `_lock`, and the error path applies text + flag as one critical section. It no longer touches the `_STREAMS` dict at all. What this does *not* close is stated in §14.3.
9. ~~`streaming.pop` has no production caller (`on_stream_poll` reads and never pops); `tests/test_callbacks_stream_poll.py` patches it. Phase 2 candidate once Phase 3 has decided the container's API.~~ **Decided in Phase 3 (2026-09-08): it stays.** `tests/test_streaming_characterization.py::test_pop_removes_and_returns_the_entry` calls it, and `agents/code_scanner.py:684` names it inside frozen LLM prompt text (Rule 4). Not a Phase 2 candidate any more.
10. `_STREAMS[id]["session"]` is the live session dict by identity — agents mutate it and the poll reads those mutations. The move in Phase 3 must keep the reference, not copy.
11. `_MOCK_BUFFERS`: the `expected_chars` denominator makes `progress` an integer percent floored to 0 for the first ~700 characters; and the acknowledged-delivery pop depends on the *browser's* store State moving off step 5, which the test drives by hand. Both by design (comments in `on_mock_stream_poll`); recorded so Phase 3 does not "fix" them.
12. ~~`resolve_phase_version` pins round **0** for a greenfield project with no rounds on disk, so the first `usage.json` lands in `.spec4/v0/`. Documented in the function; recorded because it surprised the test author.~~ **Struck in Phase 2 (2026-09-08):** intended behaviour, not an oddity — greenfield projects start at v0 by design. Not a bug, not actioned.

### 12.5 Deferred

- Phase 6: `tests/test_layout_contract.py`'s screen registry overlaps `tests/test_callback_co_presence.py::_phase_screens` (same sessions, different assertions); consolidate into one shared screen registry then. `TestMockBuffers` in the new streaming module overlaps `tests/test_designer.py::TestMockDeliveryAck` for the ack/valve branches.
- Phase 6: `tests/_golden.py` could absorb the per-file golden idioms if more goldens appear.
- Phase 7: `tests/README.md` is still stale (§9.1) and now also omits the golden/snapshot mechanism and the two env vars.
- Not touched, per Rule 7: none of the items in §11.

### 12.6 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `186 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 60 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4249 passed, 1 skipped in 172.63s (0:02:52)` (exit 0) |
| Coverage | same run | `TOTAL                                           11684    894    92%` |

## 13. Phase 2 report — dead code and unused files

Recorded 2026-09-08 on branch `look-rework`. Deletion only, per the phase rule: no renames, no moves, no refactors. Nothing written under `.spec4/`, `.venv/`, or `.git/`, and no git command was run. Every removal below was confirmed with a grep across `src/`, `tests/`, `evals/`, `scripts/`, `pyproject.toml`, and (for the two component-id names touched) the Dash callback `Input`/`Output`/`State` string ids, before deletion.

### 13.1 Files touched

| File | Change |
|---|---|
| `src/spec4/agents/code_scanner.py` | Removed `CODE_REVIEW_SCHEMA_VERSION` |
| `src/spec4/agentifier/pattern_loader.py` | Removed three unread dataclass fields |
| `src/spec4/agentifier/tier_analyst.py` | Removed one unused parameter from `_parse_output` |
| `src/spec4/layouts/_chat.py` | Removed `download_button_id` |
| `tests/agentifier/test_tier_analyst.py` | Updated 3 call sites for the `_parse_output` signature change |
| `tests/integration/test_pipeline_greenfield.py` | Removed `_make_sync_mock` |
| `pyproject.toml` | Removed `dash-iconify` dependency + mypy override; added `[tool.deptry.per_rule_ignores]` |
| `uv.lock` | Regenerated by `uv sync` after the `dash-iconify` removal |

No orphan modules or orphan test files were found — every candidate was a name inside an otherwise-live file, not a whole file. `README.md`'s project-structure tree and dependency mentions needed no edit (nothing at file granularity was deleted, and `dash-iconify` was never named there). No `CLAUDE.md` exists anywhere in the repository (checked with `find . -iname "CLAUDE.md"`), so there was nothing to fix there.

### 13.2 Removed, with evidence

1. **`CODE_REVIEW_SCHEMA_VERSION = 1`** (`agents/code_scanner.py:28`, Phase 0 §3.1 vulture 60%). `grep -rn "CODE_REVIEW_SCHEMA_VERSION" src/ tests/ evals/ scripts/ pyproject.toml README.md` returned only the definition line itself. Zero readers anywhere.
2. **`PatternBase.source_path`** (`agentifier/pattern_loader.py`, Phase 0 §3.1 vulture 60%). Populated at construction (`source_path=path` in `_build_pattern`) but `grep -rn "\.source_path\b"` across `src/`, `tests/`, `evals/` found no reader. Not part of the frontmatter schema (`patterns/SCHEMA.md` doesn't mention it — it's loader-internal bookkeeping), not constructed directly anywhere in tests. Removed the field and its one assignment.
3. **`TierPattern.cost_range_usd`, `TierPattern.latency_range_seconds`** (same file, Phase 0 §3.1 vulture 60% each). Both are required frontmatter fields — `_validate_frontmatter` checks `meta["cost_range_usd"]`/`meta["latency_range_seconds"]` directly against the parsed YAML dict (lines ~294-299), independent of the dataclass — so removing the *dataclass fields* does not touch the validation contract. `grep -rn "\.cost_range_usd\b\|\.latency_range_seconds\b"` across `src/`, `tests/`, `evals/` found no reader; `_build_tier_descriptions` (the only place `TierPattern` instances feed a prompt) uses only `tier_order`, `name`, `description`, `when_works`, `when_doesnt`. Removed both fields and their two constructor kwargs; the frontmatter requirement itself is untouched.
4. **`download_button_id`** (`layouts/_chat.py:307`, Phase 0 §3.1 vulture 60% and §7 cross-reference — the strongest candidate in the inventory). `grep -rn "download_button_id"` across `src/`, `tests/`, `evals/`, `scripts/` found only its own definition. Its sibling `open_button_id` *is* imported and called (`callbacks/__init__.py:30`, used in an `Input(...)` at `:2371`, and referenced by three tests), but every download-button id in the app (`btn-dl-vision`, `btn-dl-stack`, `btn-dl-review`, `btn-dl-features`, `btn-dl-phases`, `btn-dl-deployment`) is a hardcoded string literal in both the layout (`_chat.py`) and the callback decorators (`callbacks/__init__.py`) and in `tests/snapshots/component_ids.json` — never built through this helper. `DOWNLOAD_BTN_PREFIX`, which the dead function referenced, stays: it's imported directly by `tests/test_chat_open_links.py`.
5. **`_parse_output`'s `valid_tier_names` parameter** (`agentifier/tier_analyst.py:336`, Phase 0 §3.1 vulture 100% / §3.2 ruff ARG001, explicitly flagged "Phase 2" in the inventory's own assessment). The parameter is never read inside the function body — confirmed by reading the full function. Unlike the four other ARG001 `src/` findings (see §13.3), `_parse_output` is not called through a uniform dispatch table: it has exactly one production call site (`tier_analyst.py:425`, inside `TierAnalystAgent.run`, which already has `valid_names` in scope and uses it elsewhere) and three test call sites, all updated in the same diff.
6. **`_make_sync_mock`** (`tests/integration/test_pipeline_greenfield.py:116`, Phase 0 §3.1 vulture 60%). `grep -rn "_make_sync_mock"` across `tests/` found only the definition. Its neighbor `_make_streaming_mock` is what every test in the file actually patches `litellm.acompletion`/`litellm.completion` with; `_make_sync_mock` is a leftover with no caller.
7. **`dash-iconify`** (`pyproject.toml` dependency + mypy `ignore_missing_imports` override; Phase 0 §4 deptry DEP002, the plan's own instruction). `grep -rn "dash_iconify\|DashIconify"` across `src/`, `tests/`, `evals/`, `scripts/` found zero imports (three test docstrings/comments *describe* it as intentionally unused — `test_visual_register.py:84`, `test_status_bar.py:217`, `test_artifact_view.py:499` — left as-is, they're documentation of a design decision, not references to the package). Removed from `[project.dependencies]` and from the `tool.mypy.overrides` module list; `uv sync` updated `uv.lock` (dash-iconify uninstalled) with no other dependency changes.

### 13.3 Reviewed and kept, with reasoning

Every one of these was checked with the same grep discipline as §13.2 and found to have a live reader, or to be structurally unsafe to remove without a signature change to more than one call site (a refactor, which this phase forbids):

- **`DesignerSession` TypedDict keys** `preference_text`, `mock_html`, `finalized` (`agents/designer.py:131-134`; Phase 0 flagged these as "dataclass fields," but the class is a `TypedDict`, not a `@dataclass`). Vulture can't see a `TypedDict` annotation being read back via `session["key"]` subscript, so this is a false positive. All three are read as dict keys across `src/spec4/agents/designer.py`, `layouts/designer.py`, `callbacks/designer.py`, and asserted on in `tests/test_designer.py`, `test_streaming_characterization.py`, `test_designer_fullscreen.py`.
- **`_run_priority_phase`'s `llm_config`** and **`_handle_reentry`'s `user_input`** (`agentifier/agentifier.py`, Phase 0 §3.2 ARG001, "worth a look"). Both are called through the same uniform 3-positional-argument dispatch (`agentifier.py:3539-3548`: `_run_catalog_phase`/`_run_spec_phase`/`_run_cross_cutting_phase`/`_run_priority_phase`/`_handle_reentry` — all `(user_input, session, llm_config)`). Removing either parameter would special-case one of five sibling handlers inconsistently with the other four, which is a signature refactor of the dispatch contract, not a deletion. Left in place; noted again for whoever does Phase 5 (or Phase 4, if `agentifier.py`'s split touches this dispatcher).
- **`_project_mode_layout`'s `session`** (`layouts/__init__.py:235`) and **`_setup_provider_layout`'s `session`** (`layouts/_setup.py:230`, Phase 0 §3.2 ARG001, "check before removing"). `_setup_provider_layout` is one of three sibling step-layout functions (`_setup_provider_layout`, `_setup_model_layout`, `_setup_search_layout`) all dispatched from `_setup_layout` with `session` as the first positional argument; removing it from one would break the shared calling convention. `_project_mode_layout` has a single caller today, but is the same kind of `(session) -> html.Div` shape as every other layout function in the module (and in `test_layout_contract.py`'s registry, which the Phase 1 report describes as calling "every public layout function directly" — this one is private and not yet in that registry, but changing its shape is exactly the kind of signature churn Phase 2 is not supposed to do). Left in place.
- **`PriorityEdits`, `PatternBase`, `directional_signals`, `session_round`, `implements_ids`, `catalog_id`, `AgentRowSpec`, `AgentRow`, `AllowedArtifact`, `artifact_header`, `artifact_body`, `naming_line`, `CostStripIds`, `TreeLine`, `setup_step_row`, `RoundsOnDisk`, `usage_rollup_name`** — the full §7 zero-external-importer list. Re-grepped every one individually: all 17 have real callers *inside their own module* (that's exactly what "zero external importers" meant in §7 — vulture doesn't flag them because intra-file use is real use). Making any of them private (a leading underscore) would resolve the inventory note, but renaming is explicitly out of scope for this phase. None deleted.
- **`tavily_key`** in four `fake_start_gen`/`fake_complete` stub signatures in `tests/test_designer.py` (lines 811, 909, 1112, 1159; Phase 0 §3.1 vulture 100%, listed there as a "real candidate" — on inspection it is not). Each is a positional parameter in a `monkeypatch.setattr` replacement function matching `_start_gen`'s real positional signature; the stub body ignores it but needs the slot to keep every later positional parameter aligned. Same category as the plan's own "not cleanup targets" call on test-side `ARG` stub signatures (§3.2). Not touched.
- **`tests/agentifier/test_streaming_e2e.py:176` "unreachable code after `return`"** (vulture 100%). This is `async def _gen(): return; yield` — the standard idiom for constructing an *empty async generator* in a test (a function needs a `yield` somewhere in its body to be a generator at all). Deleting the `yield` would change `_gen` from an async generator into a plain coroutine and break `_iter_async_gen`'s contract. Not touched.
- **`_clean_sink`** (`tests/test_usage_capture.py:41`) and **`_clean_state`** (`tests/test_version_check.py:26`) — both `@pytest.fixture(autouse=True)`, invoked by pytest for every test in the module with no by-name reference for vulture to see. Verified as instructed in §3.1. Not touched. (`tests/test_streaming_characterization.py`'s `_clean_containers`, added in Phase 1 after the Phase 0 vulture pass, is the same pattern — checked as a matter of course, also an autouse fixture, also correctly not flagged as a Phase 1 removal candidate since Phase 1 tests are out of scope for this phase anyway.)
- The five `MagicMock`-attribute and `side_effect` vulture lines (`test_prioritizer.py` ×5, `test_phaser_seed_inputs.py` ×2, `test_providers.py` ×1, `test_usage_capture.py` ×2, `test_version_check.py` ×4) — mock attribute assignments vulture can't trace back to a read. Same as Phase 0's own assessment; not touched.

### 13.4 deptry

Ran as instructed: `uv sync` (to drop `dash-iconify` from the environment) then `uv run --with deptry deptry .`.

```
Found 242 dependency issues.
```
DEP001 29 (all `evals/*` sys.path-relative sibling-script imports — `_load`, `fanout_baseline`, `mechanism_scoring`, `relevance_judge`, `relevance_scoring`, `requires_inversion`, `scout_granularity`, `scout_edge_metrics`, `phantom_link_check`, `confab_baseline`; same shape as Phase 0's noise, just fewer because dash-iconify's own DEP002 line is gone), DEP002 **0** (`dash-iconify` genuinely removed; `gunicorn`/`pyyaml` now suppressed by `[tool.deptry.per_rule_ignores]`), DEP003 210 (every internal `spec4.*` import, reported "transitive" because running deptry against the project's own environment via `uv run --with deptry` sees `spec4` as installed but the project doesn't list itself in its own `[project.dependencies]` — expected self-reference noise from invoking deptry this way, not a real finding; the alternative, `uvx deptry .`, trades this for ~240 DEP001 lines instead per Phase 0 — there is no invocation that reports zero noise here), DEP004 3 (`playwright` in `scripts/screenshot_ui.py`, `pytest` in two `evals/scout/` files — dev-only scripts, unchanged from Phase 0, acceptable per Phase 0's own assessment).

No missing dependencies to add (DEP003 in this run's sense is not "missing," and the true DEP001 findings are all `evals/`-internal, not external packages).

### 13.5 vulture (`uvx vulture src/ tests/ vulture_whitelist.py --min-confidence 60`)

26 lines remain (down from 32 at the equivalent point in Phase 0's §3.1, i.e. after the 6 items in §13.2 were removed). Every remaining line was individually re-verified in §13.3 above and is a false positive (TypedDict keys read by subscript, a uniform-dispatch or uniform-sibling parameter, mock attributes, an autouse fixture, or the deliberate empty-async-generator idiom). None are actionable without a rename or a signature refactor, both out of scope for this phase.

### 13.6 ruff ARG (`uv run ruff check --select F401,F811,F841,ARG src/ tests/ --statistics`)

`src/`: **8** (down from 9 — `tier_analyst.py`'s `valid_tier_names` is gone). The remaining 8 are exactly the four Dash-callback `Input`-bound arguments (`n`/`n_clicks`/`n_submit` in `callbacks/__init__.py` ×3, `callbacks/designer.py` ×1 — not removable, they're bound positionally to `Input(...)` declarations) and the four uniform-signature cases from §13.3 (`agentifier.py` ×2, `layouts/__init__.py` ×1, `layouts/_setup.py` ×1).

`tests/`: 181 total (ARG001 121, ARG005 45, ARG002 15) vs. Phase 0's 162. The +19 is not new noise from this phase — it's Phase 1's five new test files (`test_layout_contract.py`, `test_streaming_characterization.py`, and three others), which weren't part of the Phase 0 baseline scan and account for 11 of the extra lines by direct file-level grep; the rest is normal variance in stub/fixture signatures across pre-existing files. Zero F401/F811/F841 in either tree, same as Phase 0. Test-side `ARG` remains explicitly out of scope (per-file-ignore is a Phase 5 decision).

### 13.7 Callback count

The Phase 1 report recorded **92 callbacks** registered in `dash._callback.GLOBAL_CALLBACK_MAP` after a fresh `spec4.app` import. Re-checked the same way at the end of this phase: **still 92.** Nothing in this phase touched a `@callback`-decorated function, an `Input`/`Output`/`State` string id, or `app.py`'s import ordering.

### 13.8 Deferred / not acted on

- The four uniform-signature ARG001 cases and the 17-name §7 list (§13.3) — genuinely not dead, only "could be made private/simplified," which belongs to Phase 4/5 if it belongs anywhere.
- `streaming.pop` (§8/§12.4 item 9) — the inventory itself gates this on "Phase 3 has decided the container's API." Left for Phase 3.
- Everything else already listed in Plan §11 for Phases 3-7 (module state, large-file splits, complexity, test rationalization, docs) — untouched, per Rule 7.

### 13.9 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `186 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 60 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4249 passed, 1 skipped in 172.67s (0:02:52)` (exit 0) |
| Coverage | same run | `TOTAL 11683 stmts, 893 miss, 92%` (was 11684/894/92% at the end of Phase 1; -1 statement from the three field/parameter/function removals whose bodies were themselves counted, no per-module figure dropped below its Phase 1 floor) |

No regression on any of the four gates. `.coverage` remains untracked and gitignored (untouched, per the phase instruction that this item is already done).

## 14. Phase 3 report — module-level state and globals

Recorded 2026-09-08 on branch `look-rework`. Nothing was written under `.spec4/`,
`.venv/` or `.git/`, and no git command was run. `tests/test_streaming_characterization.py`
was **not edited** (`git diff --stat` on it is empty) — it is the phase's definition
of unchanged behaviour and it passes as-is.

### 14.1 Classification of all eight items

The plan's Phase 3 text predicted that "the three streaming containers and
`version_check._cache` are the real work" — i.e. category (b), session state that
leaked to module scope. That prediction did not survive contact with the code.
**All eight items are category (a).** There are no (b) items at all, and the one
(c) item is a function rather than state.

| # | Item | Class | Basis |
|---|---|---|---|
| 1 | `streaming._STREAMS` + `_lock` | **(a)** | The entry is the handoff between a daemon worker thread and the 500 ms poll: it holds the live session dict *by identity* (agents mutate it, the poll reads those mutations — §12.4 item 10) plus a buffer the worker appends to between polls. Nothing in it survives a round trip through a `dcc.Store`, and Spec4 has no server-side session to move it to. The *key* already lives in the browser store as `session["_stream_id"]`, which is exactly the (b) pattern applied correctly: per-session half in the store, process half in the process. |
| 2 | `llm._USAGE_RECORDS` + `_USAGE_LOCK` | **(a)** | Already argued in the comment at `llm.py:255-271`: Agentifier sub-agents receive only `llm_config` (no session) and run on an asyncio-bridge thread that does not inherit contextvars, so no session is reachable at the capture point. Process-global is the design decision, not a leak. |
| 3 | `project_manager._USAGE_LOCK` | **(a)** | A lock serialising a read-modify-write of `.spec4/v{N}/usage.json` between the chat persist funnel and the Designer thread. The shared resource is the file, not a session. The plan names this exact shape as (a). |
| 4 | `version_check._cache` | **(a)** | Caches "what is the latest release on PyPI" — the same answer for every session, deliberately fetched once per server process. Not session state under any reading. |
| 4b | `version_check._reset_cache` | **(c)** | The phase's only (c): a function whose sole purpose was to let a test forget the cached answer. Zero callers in `src/`, `evals/`, `scripts/`. Moved to the fixture (§14.4). |
| 5 | `callbacks.designer._MOCK_BUFFERS` | **(a)** | Same shape as item 1 — a `threading.Event`, an accumulating buffer and up to 512 kB of HTML — keyed by `_gen_id`, which already lives in `designer-session-store`. |
| 6 | `agentifier._registry` | **(a)** | Populated by seven `.register()` calls at import, read-only afterwards. |
| 7 | `feature_specs._mechanism_definitions` (`lru_cache(1)`) | **(a)** | Process-lifetime memo of the on-disk pattern library, which ships with the package. |
| 8 | `app.py` import side effects + `app` / `server` | **(a)** | D-LR1 / Rule 5. Already documented at `app.py:7-13`. Not touched. |

Two structural reasons there is no (b) work here, both independent:

1. **The remedy has no target.** Plan bullet (b) says session state "moves to the
   session dict or the browser `dcc.Store` payload … no new server-side session
   mechanism". In Spec4 the session dict *is* the browser store payload. All three
   containers hold live thread handles, `threading.Event`s and a dict shared by
   identity with a running worker; none of it is JSON-serialisable, so there is
   nowhere for it to go that does not mean inventing the server-side session
   mechanism the plan forbids.
2. **The contract test pins the shape.** `tests/test_streaming_characterization.py`
   reaches into all three containers *by module-level name*, asserts each entry's
   exact key set (`set(entry) == {"text","done","session","error","finalised"}`,
   `{"done","stop","text","expected_chars"}`), and asserts identity
   (`streaming.get(sid) is entry`, `entry["session"] is session`). Any move out of
   module scope, and any change to an entry's key set, fails it.

**No registry work in `providers.py` / `websearch.py`.** The plan's registry bullet
names those two modules. Both `providers.PROVIDERS` and `websearch.PROVIDERS` are
constant tables never mutated after import — §8's own sweep confirms only items 1–8
are mutated — so there was nothing there to make idempotent. The only import-time
registry in the codebase is item 6.

### 14.2 Files touched

| File | Change |
|---|---|
| `src/spec4/streaming.py` | Lock fix in `_run()` (§14.3); category-(a) comment on `_STREAMS` / `_lock` |
| `src/spec4/llm.py` | Comment only: what `_USAGE_LOCK` guards |
| `src/spec4/project_manager.py` | Comment only: what `_USAGE_LOCK` serialises |
| `src/spec4/version_check.py` | Comment on `_cache`; `_reset_cache` removed |
| `src/spec4/feature_specs.py` | Docstring only: the cache is never invalidated |
| `src/spec4/agentifier/agentifier.py` | Seven bare `.register()` calls → `_build_registry()` |
| `tests/test_version_check.py` | `_clean_state` resets via `monkeypatch` instead of `_reset_cache` |
| `CLEANUP_INVENTORY.md` | This report; §8, §11 and §12.4 items 8–9 marked resolved |

Not touched: `tests/test_streaming_characterization.py`, `src/spec4/app.py`,
`src/spec4/callbacks/designer.py` (items 5 and 8 already carry adequate comments —
`designer.py:50-53` states the single-writer/GIL discipline, `app.py:7-13` states
D-LR1 — so re-commenting them would have been churn, not clarity).

### 14.3 The lock fix (§12.4 item 8) — and what it does not close

Before, `_run()` wrote through the shared dict on every chunk, unlocked, while
`start()` deleted keys from that same dict under `_lock` and the `finally` block
already set `done` under it:

```python
_STREAMS[stream_id]["text"] += chunk        # :242
_STREAMS[stream_id]["text"] += formatted    # :251
_STREAMS[stream_id]["error"] = True         # :252
```

After, the worker writes through the `entry` object already captured in its
closure, under `_lock`, and the error path is a single critical section:

```python
with _lock:
    entry["text"] += chunk
...
with _lock:
    entry["text"] += formatted
    entry["error"] = True
```

Three things this changes: the worker no longer touches the `_STREAMS` dict at all,
so it cannot race `start()`'s eviction loop; `text` and `error` now land together,
so a reader cannot see `error=True` without the message that explains it; and every
worker write now takes the same lock as the `done` latch it is ordered against.
Every remaining `_STREAMS` access in the module is inside `with _lock`.

**What it does not close, stated plainly.** It does not synchronise the *reader*.
`get()` returns the entry by identity and `on_stream_poll` reads `stream["text"]`,
`["done"]` and `["session"]` outside the lock. That is not an oversight and it is
not fixable here: handing back the live entry is the channel agent mutations travel
on (§12.4 item 10), and both `streaming.get(sid) is entry` and
`entry["session"] is session` are pinned by the characterization test. The observed
effect therefore remains exactly what §8 said it was — under CPython, at worst a
stale read of a field, never a torn one. A design that closed it would have to
replace `get()` with a snapshot API, which is a Phase 4/5 interface change, not a
Phase 3 lock fix.

### 14.4 The one (c): `version_check._reset_cache` → the fixture

`_reset_cache` existed only so `tests/test_version_check.py`'s autouse `_clean_state`
fixture could forget the cached answer; a grep across `src/`, `tests/`, `evals/` and
`scripts/` found no other caller. Removed from `src/`; the fixture now does

```python
monkeypatch.setattr(version_check, "_cache", {"checked": False, "result": None})
```

`check_for_update` reads the module global by name at call time, so rebinding the
attribute works, and monkeypatch *restores* the module's own cache on teardown
rather than wiping it — so the process-lifetime cache is now never written by this
test module at all, which is stricter isolation than the two `_reset_cache()` calls
it replaces. `version_check.py` stays at 100% coverage.

### 14.5 Item 6: `_build_registry()`

The plan asks that an import-time registry be made "idempotent and explicit (a
function called once from `app.py` after construction), respecting D-LR1". The
`app.py` half is infeasible for this registry and was not done: `agentifier.agentifier`
is imported *lazily*, from function bodies in `callbacks` and `session`, and never
from `app.py` at all (§6). An init call from `app.py` would make a deliberately
deferred import eager and add a top-level `app` → `agentifier` edge the layering
does not have — a layering change, not a cleanup. The "explicit and idempotent"
half is done: the seven bare `.register()` calls became a named
`_build_registry() -> SubAgentRegistry`, called once at module scope, whose
docstring records why it is not called from `app.py`. Same seven agents, same
registration order. `_registry` remains a module attribute, so the ten
`patch("spec4.agentifier.agentifier._registry.stream")` calls in
`tests/agentifier/test_ff_sweep.py` are unaffected.

### 14.6 Deferred / not acted on

- **`streaming.get()` handing out the live entry** (§14.3). The reason the reader
  stays unsynchronised. Changing it is an API change the pinned contract test
  forbids; if it is ever wanted, it belongs to whichever later phase is allowed to
  edit `tests/test_streaming_characterization.py`.
- **`streaming.pop`** — decided, not deferred: it stays (§12.4 item 9, now struck).
- **`version_check._cache` is unguarded.** Two first page loads racing into
  `check_for_update` can both fetch. The cost is one duplicate best-effort HTTP
  request converging on the same answer; a lock on the render path is the wrong
  trade. Recorded in the comment rather than "fixed", so the next reader does not
  mistake absence of a guard for absence of thought.
- **`feature_specs._mechanism_definitions` is never invalidated.** Nothing calls
  `cache_clear()`, so a pattern-library edit on disk needs a restart. Intended
  (the library ships with the package); now stated in the docstring.
- Everything else already listed in §11 for Phases 4–7 — untouched, per Rule 7.

### 14.7 Statement-count accounting

`TOTAL` moved 11683 → 11680 (−3), which reconciles exactly:
`streaming.py` +2 (the two `with _lock:` statements), `agentifier.py` −2 (eight
module-level statements became six), `version_check.py` −3 (`_reset_cache`).
The comment-only and docstring-only edits add no statements.

### 14.8 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `186 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 60 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4249 passed, 1 skipped in 171.97s (0:02:51)` (exit 0) |
| Coverage | same run | `TOTAL 11680 stmts, 893 miss, 92%` |

No per-module figure dropped below its floor (§1.3 for non-UI, §12.3 for UI).
Spot-checked against the containers this phase touched: `streaming.py` 91% (Phase 1
floor 91%), `version_check.py` 100% (100%), `feature_specs.py` 77% (77%),
`llm.py` 95% (95%), `project_manager.py` 97% (97%),
`agentifier/agentifier.py` 89% (89%), `callbacks/designer.py` 74% (74%),
`app.py` 89% (89%).

A fresh `spec4.app` import still registers **92** callbacks in
`dash._callback.GLOBAL_CALLBACK_MAP` — the §13.7 invariant, re-checked because both
`agentifier` and `app.py` were in this phase's scope.

## 15. Phase 4 pre-work — the layering contract test, and the sub-phase order

Recorded 2026-09-08 on branch `look-rework`. One test file added; **nothing under
`src/` changed**, `pyproject.toml` is untouched, no existing test was edited.
Nothing was written under `.spec4/`, `.venv/` or `.git/`, and no git command was
run. No file was split — each split is its own run, starting at 4a.

### 15.1 The file added

| Path | Purpose |
|---|---|
| `tests/test_import_layering.py` | 7 tests. The `ast`-based layering contract §6.3 chose instead of import-linter. Named for imports, not "layering contract", to stay distinct from `tests/test_layout_contract.py` (Dash layouts, Phase 1). |

It walks `src/spec4/**/*.py` with `ast` and rebuilds the edge set §6 was built
from, then asserts four rules against it. The walk, not `importlib`: it sees
function-body imports (§6.2 lists seven, and a lazy import is where an upward
edge would hide), it imports nothing to run, and it can read a module that would
fail to import.

- `import spec4.x` → an edge to `spec4.x`.
- `from spec4.x import y` → an edge to `spec4.x`, plus one to `spec4.x.y` when
  that is itself a module in the walked set — §6's own rule.
- Relative imports are resolved against the importing module's package, so a
  sub-phase that converts a module to a package and switches to `from . import x`
  is still covered.
- Layer membership is "the name itself, or the name plus a dot". `spec4.app_constants`
  is therefore **not** part of the `spec4.app` layer, and a `project_manager.py`
  that becomes `project_manager/` in 4b is still matched by `spec4.project_manager`.

### 15.2 The four rules

| # | Rule | Status today |
|---:|---|---|
| 1 | No module under `spec4.agents*`, `spec4.agentifier*` or `spec4.project_manager*` imports anything under `spec4.layouts*`, `spec4.callbacks*`, `spec4.app` or `spec4.session*`. | holds (0 edges) |
| 2 | No module in `src/` imports `spec4.app`. Scoped to `src/` — tests import it, and `[project.scripts]`'s `spec4.app:main` is an entry point, not an import. | holds (0 edges) |
| 3 | No module under `spec4.layouts*` imports anything under `spec4.callbacks*` (§6.3 boundary (b)). | holds (0 edges) |
| 4 | No module named `spec4.callbacks._*` imports the `spec4.callbacks` package itself. | **vacuous today** |

Rule 4 is forward-looking by design. `callbacks/` currently holds only
`__init__.py` and `designer.py`, so nothing matches `spec4.callbacks._*`; the rule
starts biting in 4g, when the private sub-modules appear and must take their shared
helpers from `callbacks/_shared.py` rather than from the package `__init__` that
imports them for registration — i.e. so the `layouts` ↔ `layouts._chat` cycle
(§6.1) is not recreated one directory over. It is deliberately excluded from the
non-emptiness guards below, and the test says so in a comment, so that "no modules
matched" is not later read as "rule removed". Two scheduled tightenings: 4g moves
`_open_pick_fields` into `callbacks/_shared.py`, which removes the one existing
`callbacks.designer` → `spec4.callbacks` edge (`callbacks/designer.py:14`); 4h then
widens rule 4 from `spec4.callbacks._` to `spec4.callbacks.` — one underscore
deleted from `_CALLBACKS_PRIVATE`.

Three guards keep the test from passing for the wrong reason: the walk must find
≥ 55 modules with both layer sets non-empty, and it must still see two known edges
— `spec4.app` → `spec4.callbacks` (top level) and `spec4.session` →
`spec4.agentifier.agentifier` (function body). If the second stops being seen the
walk has gone shallow and every rule is passing vacuously. Each rule reports the
offending `importer -> imported` pairs, sorted, so a failure names the file to fix.

All four were also checked against a synthetic graph containing one violation of
each; all four reported it.

### 15.3 Proposed sub-phase order

Line counts are current (Phase 0's table plus the §14.7 deltas). "Largest first"
alone would start at `agentifier/agentifier.py`, which is the largest *and* least
separable file in the repo; this order weighs size against how cleanly each file
already comes apart. Every sub-phase keeps the module's name and import path,
re-exports every public name, changes no logic, and re-runs the layering test.

| # | File | Lines | Splits into | Why here |
|---|---|---:|---|---|
| 4a | `agents/_utils.py` | 2528 | `_turn_flow` (conversation-history surgery for the shared turn loop), `_reask` (artifact-reask protocol + the stream wrappers), `_feature_context` (feature/AI-feature seed blocks per consumer), `_stack_context` (stack/phases/NFR/manifest digests + the style renderers) | Second largest; five banner-delimited blocks of pure functions, no Dash, no shared mutable state. Best payoff per unit of risk. |
| 4b | `project_manager.py` | 1897 | `_paths` (where an artifact lives: dirs, versioning, rounds), `_artifacts` (read/write every `.spec4/` artifact + README assembly), `_phase_markdown` (phase-file assembly and parsing), `_usage` (usage log + cost rollup) | Foundation module, 18 importers; banner-delimited; phase markdown and README already golden-pinned (§12.1). Staleness + button state (~220 lines) stays in the façade. |
| 4c | `agents/code_scanner.py` | 1741 | package `code_scanner/`: `_scan` (repo walk + context gathering + budgets), `_prompt` (the frozen ~646-line `SYSTEM_PROMPT`), `_review_render` (`_format_review_as_text` + the seven section renderers) | ~646 lines are one frozen prompt; the renderer is golden-pinned. Separates almost by inspection. |
| 4d | `agents/stack_advisor.py` | 1432 | package `stack_advisor/`: `_prompt`, `_stack_shape` (normalisation/extraction + revision note), `_render` (`_format_stack_as_text` and friends) | Same shape. Isolating `_format_stack_as_text` (C901 61, the repo's worst) is what makes Phase 5's first decomposition tractable. |
| 4e | `agents/phaser.py` | 1378 | package `phaser/`: `_prompt`, `_phase_extract` (extraction, truncation and completeness checks), `_revision` (`revision_delta`, `build_revision_note`, design note) | Same shape again; `run` (493 lines) stays whole — shrinking it is Phase 5. |
| 4f | `layouts/_chat.py` | 997 | `_chat_status` (the strip above the transcript), `_chat_actions` (`_chat_action_buttons` + open/download ids), `_chat_panels` (`_retry_panel`, `_breadth_panel`) | Under the 1,300 line, included because the plan's "resolve the `layouts` ↔ `layouts._chat` cycle in whichever sub-phase touches `layouts/`" otherwise has no home. |
| 4g | `callbacks/__init__.py` | 2460 | `_shared` (the cross-module helpers, incl. `_open_pick_fields`), `_setup` (the three wizard steps), `_chat` (turn, gate, retry, breadth, stream poll, navigation), `_artifacts` (round tree, artifact view, cost, downloads, open-in-view) | Cleanly banner-grouped, but 78 decorator-registered callbacks must still register exactly once on `import spec4.callbacks`. Late, once the mechanical splits have proven the process. |
| 4h | `callbacks/designer.py` | 1399 | package `designer/`: `_mock_gen` (`_start_gen`, the worker, `_MOCK_BUFFERS`), `_wizard` (steps 1–4 and approve/back/start-over), `_refine` (regenerate, refine, revise-stale, retry) | Same registration constraint, plus §12.2 pins `_MOCK_BUFFERS` by module-level name on `spec4.callbacks.designer`; the re-export must bind the same dict object. |
| 4i | `agentifier/agentifier.py` | 3565 | `_seed` (sub-agent call wrappers, seed message, candidate/analysis (de)serialisation, registry), `_render` (every `_format_*`, `_build_ai_features`, priority parsing, revision snapshot), `_ff_review` (both fast-forward review halves) | Largest and least separable: one generator flow, every `_run_*_phase` yields UI updates and mutates the shared `session`. Only the leaf-pure edges come out; the phase drivers stay. Last of the splits, deliberately. |
| 4j | *(no file)* | — | — | Importer cleanup: retire the compatibility layer the eight splits leave behind. |

**`session.py` (654) is not proposed for a split.** It is smaller than every
candidate above, and its actual problem — being the UI/agent hinge (§6.2) — is a
layering decision, not a file-size one. §11's "decide the fate of `session.py`" is
answered: keep it, out of Phase 4 scope.

### 15.4 Three decisions the order depends on

1. **The `_prompt.py` collision (4c/4d/4e) → package conversion.** Three siblings
   under `agents/` cannot all be `_prompt.py`. Each of `code_scanner`,
   `stack_advisor` and `phaser` becomes a package (`__init__.py` + its private
   modules) rather than gaining prefixed flat files, so the import path
   `spec4.agents.code_scanner` is unchanged — the same string every importer,
   every `session.py` dispatch entry and every test already uses. One consequence
   handled inside 4c: `pyproject.toml`'s ruff per-file-ignore is
   `"src/spec4/agents/*.py" = ["E501"]` and ruff's `*` does not cross a directory
   separator, so a nested `_prompt.py` would lose the exemption and the ruff gate
   would fail on the frozen prompt lines. 4c changes that pattern (and the
   `agentifier` one) to `**/*.py`. Config forced by the split; no rule set changes.
2. **Underscore aliases in 4a.** `_utils`'s private names are imported by name
   across files — 20+ test modules do `from spec4.agents._utils import
   _stack_for_deployer` and friends. The new modules use public names and
   `_utils.py` re-exports *both* the public name and the underscore alias, so no
   importer changes while the code is moving. Zero `patch("spec4.agents._utils.…")`
   string targets exist, so only the direct imports matter.
3. **4j retires that layer**, in order: the 4a aliases (importers move to the
   public names, then the aliases are deleted), then re-exports with no importer
   anywhere in `src/`, `tests/`, `evals/`, `scripts/`, then a docstring on each
   façade saying what its sub-modules own. Names that turn out to be genuinely
   dead are logged here as Phase 2-style candidates, not deleted — 4j moves
   imports, it does not remove definitions. Not in scope: anything a test patches
   by string, `__all__` in `spec4/__init__.py` or `agents/__init__.py`, or any
   import in `app.py` (Rule 5, D-LR1).

### 15.5 Two invariants to re-check per sub-phase, beyond the gate

- The callback registry still holds **92** callbacks (§13.7, §14.8) — the check
  that catches a callback registering twice or not at all when `callbacks/` is
  split in 4g/4h.
- `tests/test_streaming_characterization.py` and `tests/test_layout_contract.py`
  are not edited. They are the Phase 1 net, and 4f/4g/4h are exactly the
  sub-phases that would be tempted to edit them.

Per §6.3, 4g is also the point to reconsider import-linter: it is where `callbacks/`
gains internal layering, which is the case §6.3 named as the one that would justify
a declarative contract.

### 15.6 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `187 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 60 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 177.41s (0:02:57)` (exit 0) |
| Coverage | same run | `TOTAL 11680 stmts, 893 miss, 92%` |

4249 → 4256 tests (+7, all in the new file). `187 files already formatted` is
§14.8's 186 plus the new test. Coverage is byte-for-byte §14.8's — the file adds
no statements under `src/`, so no per-module floor can have moved.

## 16. Phase 4a — `agents/_utils.py` split into four modules

Recorded 2026-09-08 on branch `look-rework`. Five files under `src/spec4/agents/`
changed or added; **no importer anywhere changed**, no test file was edited,
`pyproject.toml` is untouched. Nothing was written under `.spec4/`, `.venv/` or
`.git/`, and no git command was run beyond `git show HEAD:…` and `git status`,
both read-only.

### 16.1 Line counts of the five resulting files

| File | Lines | Was |
|---|---:|---:|
| `agents/_utils.py` (façade) | 238 | 2528 |
| `agents/_turn_flow.py` | 290 | — |
| `agents/_reask.py` | 345 | — |
| `agents/_feature_context.py` | 1185 | — |
| `agents/_stack_context.py` | 781 | — |
| **total** | **2839** | **2528** |

The +311 is entirely compatibility layer and prose: the façade's 49 alias
assignments and 100-name `__all__`, four module docstrings, and the import
headers each new module needs. No definition grew by a line.

### 16.2 The names moved to each

All 51 top-level names moved; none was dropped, added, or renamed away. Per
§15.4 decision 2 the new modules use **public** names — applied uniformly,
constants included (`_TIER_ORDER_FOR_SUMMARY` → `TIER_ORDER_FOR_SUMMARY`,
`_DEV_MODE` → `DEV_MODE`, `_AGENT_DELIVERABLE` → `AGENT_DELIVERABLE`,
`_STYLE_LEAF_KEYS` → `STYLE_LEAF_KEYS`, `_VISION_FRAMING_FIELDS` →
`VISION_FRAMING_FIELDS`). `slug` and `excluded_feature_ids` were already public
and gain no alias.

**`_turn_flow.py`** — conversation-history surgery for the shared turn loop (10):
`AGENT_DELIVERABLE`, `extract_json_block`, `replay_last_assistant`,
`last_assistant_text`, `stale_phrase`, `build_revision_context`,
`maybe_inject_staleness_question`, `maybe_inject_resume_summary`,
`drop_orphan_trailing_user`, `drop_orphan_or_route_to_fresh_start`.

**`_reask.py`** — the artifact re-ask protocol and the stream wrappers (11):
`DEV_MODE`, `suppressed_as_artifact`, `artifact_reask_prompt`,
`artifact_reask_status`, `artifact_fallback`, `reask_for_artifact`,
`abandon_reask`, `set_status`, `stream_suppressing_json`, `stream_counting`,
`drain_stream`. `reask_for_artifact`'s function-body `from spec4 import llm`
(§6.2's lazy edge) moved with it unchanged.

**`_feature_context.py`** — feature / AI-feature seed blocks per consumer (19):
`slug`, `TIER_ORDER_FOR_SUMMARY`, `served_product_feature_ids`,
`project_feature_for_stack`, `ai_features_for_stack`,
`feature_relationship_lines`, `explicitly_rejected_lines`,
`ai_features_for_phaser`, `ai_features_for_deployer`,
`designer_affordance_hints`, `short_text`, `ai_features_for_designer`,
`VISION_FRAMING_FIELDS`, `slim_vision_framing`, `feature_specs_for_designer`,
`feature_specs_for_stack`, `ai_served_feature_ids`, `excluded_feature_ids`,
`feature_specs_for_phaser`. Both banner comments in this range (old lines
698–700, 1763–1768) moved with their blocks.

**`_stack_context.py`** — stack / phase / NFR / manifest digests and the style
renderers (11): `render_references`, `STYLE_LEAF_KEYS`, `render_one_style`,
`render_coding_style`, `phases_for_deployer`, `stack_for_deployer`,
`nfr_goals_for_deployer`, `load_design_manifest`, `design_manifest_for_stack`,
`stack_digest_for_phaser`, `manifest_for_phaser`.

`slug` went to `_feature_context` because it is the feature-id derivation the
spine/catalog join is built on; `_stack_context` imports it for
`stack_digest_for_phaser`.

### 16.3 The resulting import graph, and why `__all__` is load-bearing

```
_feature_context  ←  _stack_context  ←  _turn_flow  ←  _reask
                  all four  ←  _utils (façade, defines nothing)
```

Acyclic, and every edge is inside `spec4.agents`, so §15.2's four rules are
untouched. Only three cross-module edges exist: `_stack_context` → `slug`,
`_turn_flow` → `load_design_manifest`/`design_manifest_for_stack` (
`build_revision_context` reads the design manifest), `_reask` →
`AGENT_DELIVERABLE`.

`_utils.py` re-exports each name under both spellings. The underscore aliases are
plain assignments, which bind real module attributes; the public names arrive by
import, and `[tool.mypy] strict` implies `no_implicit_reexport`, so without
`__all__` the six `src/` modules doing `from spec4.agents._utils import slug`
would not type-check. `__all__` also keeps ruff F401 quiet on the façade. It is
already the convention here (`feature_specs.py`, `llm.py`, `stack_routing.py`,
`design_manifest.py`).

### 16.4 How "no logic changes" was verified

- **AST equality per definition.** Each of the 51 definitions was re-parsed from
  its new module, its identifiers and string constants mapped back through the
  inverse rename, and `ast.dump`-compared against the same definition in
  `HEAD:src/spec4/agents/_utils.py`. All 51 matched exactly.
- **The rename touched no prompt text.** Every renamed identifier's occurrences
  were enumerated by token; the only occurrences outside code are in docstrings
  and `#` comments (8 of them, e.g. ``:func:`_abandon_reask` `` at old line 374).
  Zero occur in a non-docstring string literal, so no string that reaches an LLM
  changed — rule 4 holds.
- **Export superset.** Every name bound at module level in the pre-split file is
  still reachable as an attribute of `spec4.agents._utils`; all 100 `__all__`
  entries resolve.
- **Coverage attribution, not coverage loss.** §5's baseline for the file was
  1092 stmts / 71 miss / 93%. The five files together are 1159 / 71 / 94% — the
  same 71 missed lines, plus 67 always-executed façade statements. Suite-wide
  misses are unchanged at 893.

### 16.5 Deferred (noted, not done)

- **4j** owns retiring the compatibility layer: moving the 39 externally-imported
  underscore names onto their public spellings across `src/`, `tests/`, `evals/`
  and `scripts/`, then deleting the 49 aliases and trimming `__all__`.
- **Phase 5** owns every long function that moved intact: `stack_for_deployer`
  (186 lines, C901 29 — the file's worst), `ai_features_for_phaser` (151),
  `stack_digest_for_phaser` (155), `ai_features_for_deployer` (124),
  `ai_features_for_designer` (123), `feature_specs_for_stack` (115). 4a moved
  them; it did not touch them. §9's per-function complexity rows for
  `agents/_utils.py` now point at the new owning modules.
- **`_feature_context.py` is 1185 lines** — under the 1,300 threshold, but the
  largest of the four. If Phase 5's decomposition does not bring it down, a
  further split (the `ai_features_for_*` renderers vs. the `feature_specs_for_*`
  ones) is a candidate for a later round. Not opened here: §15.3 agreed four
  modules, and one file per sub-phase is the rule.
- **`tests/README.md`** still lists `spec4/agents/_utils.py | 100%` (a stale row
  Phase 0 already flagged; the real figure was 93%) and does not know about the
  four new modules. Phase 7's docs pass, per §11.
- **`vulture_whitelist.py`** needed no change — none of its entries is in this
  file.

### 16.6 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Layering | `uv run pytest tests/test_import_layering.py -q` | `7 passed in 0.35s` (exit 0) |
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `191 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 64 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 166.19s (0:02:46)` (exit 0) |
| Coverage | same run | `TOTAL 11747 stmts, 893 miss, 92%` |

Test count is unchanged at 4256 — 4a adds no test and removes none. `191 files
already formatted` is §15.6's 187 plus the four new modules; `64 source files` is
mypy's 60 plus the same four. Statements rose 11680 → 11747 (+67, the façade) and
misses held at 893, so no per-module floor moved. `.coverage` was restored after
the run.

## 17. Phase 4b — `project_manager.py` split into four modules

Recorded 2026-09-08 on branch `look-rework`. Five files under `src/spec4/`
changed or added; **no importer anywhere changed**, no test file was edited,
`pyproject.toml` is untouched. Nothing was written under `.spec4/`, `.venv/` or
`.git/`, and no git command was run beyond `git show HEAD:…` and `git status`,
both read-only.

Unlike 4a, this is a **partial** façade: `project_manager.py` still defines the
staleness and button-state block (§15.3's "~220 lines stays in the façade"),
and re-exports the 66 names that moved out.

### 17.1 Line counts of the five resulting files

| File | Lines | Was |
|---|---:|---:|
| `project_manager.py` (façade + staleness/button state) | 515 | 1897 |
| `_paths.py` | 199 | — |
| `_artifacts.py` | 555 | — |
| `_phase_markdown.py` | 442 | — |
| `_usage.py` | 436 | — |
| **total** | **2147** | **1897** |

The +250 is compatibility layer and prose: the façade's four import blocks and
85-name `__all__` (+24 statements, see §17.5), four module docstrings, and the
import header each new module needs. No definition grew or shrank by a line —
every one moved byte-for-byte, and §17.4 shows how that was checked.

### 17.2 The names moved to each

All 85 top-level names are accounted for: 66 moved, 19 stayed. Nothing was
dropped, added, or renamed — **no name changed spelling in 4b.** §15.4's
decision 2 (public names in the new module, underscore aliases in the façade)
was 4a-specific and does not apply here: the split has **zero cross-module
private references**, so the plan's "no cross-module private imports" rule is
satisfied without a single rename. Every name one new module needs from another
(`get_version_dir`, `ensure_version_dir`, `active_version`,
`latest_phase_version`, `latest_implemented_version`, `parse_phase_markdown`,
`render_phase_markdown`, `USAGE_FILENAME`) was already public.

**`_paths.py`** — where an artifact lives: dirs, versioning, rounds (13):
`get_spec4_dir`, `ensure_spec4_dir`, `get_version_dir`, `ensure_version_dir`,
`_PHASE_VERSION_RE`, `_phase_version_dirs`, `latest_phase_version`,
`latest_implemented_version`, `active_version`, `RoundsOnDisk`,
`rounds_on_disk`, `session_is_brownfield`, `resolve_phase_version`. Both banner
comments in this range ("Directory helpers", "Phase-set versioning") moved with
their blocks.

**`_artifacts.py`** — read/write every `.spec4/` artifact, plus README assembly
(26): `load_spec4_artifacts`, `_write_text_if_changed`, `save_vision`,
`save_stack`, `merge_library_additions`, `save_code_review`,
`load_prior_vision`, `save_phases`, `save_ai_catalog`, `load_ai_catalog`,
`save_ai_features`, `load_ai_features`, `save_feature_specs`,
`load_design_manifest`, `load_feature_specs`, `load_vision`,
`save_deployment_plan`, `load_prior_ai_features`, `load_prior_mock`,
`load_prior_stack`, `load_deployment_plan`, `load_prior_deployment_plan`,
`SPEC4_README_ATTRIBUTION`, `_with_readme_attribution`, `save_readme`,
`load_existing_readme`.

`load_prior_vision` and `save_phases` sat inside the "Phase-set versioning"
banner in the old file but are artifact reads/writes, and moved here rather
than to `_paths`; the README trio sat inside the "LLM usage log" banner and
moved here rather than to `_usage`. Those are the only three places where the
old banner boundaries and the concern boundaries disagreed.

**`_phase_markdown.py`** — phase-file assembly and parsing (7):
`_PHASE_FRONTMATTER_RE` (with its explaining comment, old lines 39–45),
`_phase_spec_preamble`, `_declared_ids`, `_phase_stack_lines`,
`_phase_nfr_lines`, `render_phase_markdown`, `parse_phase_markdown`.

**`_usage.py`** — usage log and cost rollup (20): `USAGE_FILENAME`,
`USAGE_SCHEMA_VERSION`, `_USAGE_COST_SOURCE`, `_USAGE_ROLLUP_PARENT`,
`_USAGE_LOCK`, `_usage_int`, `_usage_float`, `usage_rollup_name`,
`_usage_versions`, `summarize_usage`, `usage_totals`, `load_usage`,
`_COST_SUMMARY_EMPTY`, `_cost_block`, `cost_summary`, `_call_is_unpriced`,
`unpriced_calls`, `round_cost`, `_write_atomic`, `save_usage`. `_USAGE_LOCK`
keeps its §14.1 category-(a) comment verbatim, and the façade re-export binds
the same `threading.Lock` object.

**Stayed in `project_manager.py`** (19): `_NON_ARTIFACT_FILES`,
`_STALE_DEPENDENCIES`, `_path_mtime`, `detect_stale_inputs`,
`_PIPELINE_ARTIFACT_ORDER`, `_REQUIRED_INPUTS`, the six `AGENT_BTN_*`
constants, `brownfield_new_round_pending`, `directory_has_content`,
`directory_opens`, `needs_project_mode`, `_has_transcript`,
`agent_button_state`, `_artifact_button_state`. Both are decided from artifact
mtimes across the whole pipeline rather than from any one concern.

### 17.3 The resulting import graph

```
_phase_markdown  ←  _artifacts  →  _paths  ←  _usage
             all four  ←  project_manager (façade)
```

Acyclic. `_artifacts` → `_paths` (5 names) and → `_phase_markdown` (2);
`_usage` → `_paths` (2); `_phase_markdown` and `_paths` import nothing from the
split. No new edge leaves `spec4`'s existing dependency set —
`design_manifest`, `stack_routing` and `feature_specs` are now imported by
`_phase_markdown` alone, `app_constants` by `_paths` (`PROJECT_MODE_EXISTING`)
and the façade (`PROJECT_MODES`), and the `spec4.__version__` import by
`_usage` alone.

The `project_manager` ↔ `layouts` cycle the plan warns about is not
reintroduced: none of the four imports `layouts`, `callbacks`, `app` or
`session`.

### 17.4 How "no logic changes" was verified

- **AST equality per definition.** All 85 top-level definitions were re-parsed
  from their new home and `ast.dump`-compared against the same definition in
  `HEAD:src/spec4/project_manager.py`. **85 matched exactly, 0 missing, 0
  added** — no inverse-rename step was needed, because nothing was renamed. No
  string constant moved, so no string that reaches an LLM changed (rule 4).
- **Attribute surface.** Every `project_manager.<name>` / `pm.<name>`
  attribute reference in `src/`, `tests/`, `evals/` and `scripts/` was
  enumerated and resolved against the imported façade: **all resolve.** That
  includes the three patch targets — `spec4.project_manager.load_feature_specs`
  (`tests/agentifier/test_vision_grounding.py:276`, a re-exported attribute,
  and every caller reaches it as `project_manager.load_feature_specs`) and
  `spec4.project_manager.os.replace` / `.os.fdopen`
  (`tests/test_usage_capture.py:815,838`, which patch the shared `os` module
  object, so `_usage._write_atomic` sees them; the façade still imports `os`
  for `directory_opens`).
- **Private names imported by name elsewhere.** Only one:
  `from spec4.project_manager import _USAGE_ROLLUP_PARENT`
  (`tests/test_agent_llm_selection.py`). It is re-exported and listed in
  `__all__`; the importer did not change.
- **Coverage attribution, not coverage loss.** The five files together are
  783 stmts / 22 miss / 97%, against 759 / 22 / 97% for the single pre-split
  file. Same 22 missed lines; the +24 statements are the façade's imports and
  `__all__`. Suite-wide misses unchanged at 893.
- **§15.5 invariants.** The callback registry still holds **92** callbacks;
  `tests/test_streaming_characterization.py` and `tests/test_layout_contract.py`
  were not edited (no test file was).
- `tests/test_project_manager_golden.py` (17 tests) and
  `tests/test_project_manager.py` pass unmodified.

### 17.5 Deferred (noted, not done)

- **The layering contract no longer covers the moved code, and should be
  widened.** `tests/test_import_layering.py`'s `_AGENT_SIDE` is
  `("spec4.agents", "spec4.agentifier", "spec4.project_manager")`. §15.2
  anticipated a `project_manager.py` that became a *package*, whose sub-modules
  would still match the `spec4.project_manager` prefix; 4b instead produced
  flat siblings, per §15.3's table (which reserves "package `X/`" wording for
  4c–4e and 4h) and the sub-phase brief. Rule 1 therefore still holds — all
  seven tests pass, and none of the four new modules imports `layouts`,
  `callbacks`, `app` or `session` — but it no longer *guards* them. The fix is
  four strings: add `"spec4._paths"`, `"spec4._artifacts"`,
  `"spec4._phase_markdown"` and `"spec4._usage"` to `_AGENT_SIDE`. Left undone
  because editing the contract test is not this sub-phase's scope (rule 7).
  **This should be closed before 4c**, or the same gap will accumulate.
- **4j** owns the importer cleanup. For 4b that is narrower than for 4a — there
  are no aliases to retire — and amounts to: point the 18 importers of
  `spec4.project_manager` at the owning module where they use only one
  concern's names, then trim `__all__` to what is still re-exported. Two names
  worth revisiting there: `_USAGE_ROLLUP_PARENT` (imported by name from a test,
  the one cross-file private) and `_with_readme_attribution` (reached as a
  façade attribute by `test_project_manager_golden.py:168-173`).
- **Phase 5** owns every long function that moved intact. Re-measuring §5's
  rule sets over the five files (`ruff check --select C90,PLR0912,PLR0913,
  PLR0915,SIM,B`) gives the same 10 findings the single file had, re-homed:

  | Finding | Function | Now in |
  |---|---|---|
  | C901 20, PLR0912 17, PLR0915 65 | `_phase_spec_preamble` (187 lines) | `_phase_markdown.py` |
  | PLR0915 58 | `render_phase_markdown` | `_phase_markdown.py` |
  | C901 14, PLR0912 14 | `merge_library_additions` (85 lines) | `_artifacts.py` |
  | SIM105 | `load_spec4_artifacts` | `_artifacts.py` |
  | SIM105 | `_write_atomic` | `_usage.py` |
  | C901 13 | `_artifact_button_state` | `project_manager.py` (stayed) |
  | B905 (`zip` without `strict=`) | `_artifact_button_state` | `project_manager.py` (stayed) |

  §9's per-function complexity rows for `project_manager.py` now point at the
  new owning modules.
- **The banner comments were kept where a module now has only one.**
  `_artifacts.py`, `_phase_markdown.py` and `_usage.py` each open with the
  section banner that delimited the block in the old file, which duplicates the
  new module docstring. Kept for byte-fidelity with 4a (§16.2, "both banner
  comments moved with their blocks"); removing the three redundant ones is a
  Phase 5 cosmetic, not a 4b decision.
- **`tests/README.md`** does not know about the four new modules and still
  carries its stale `project_manager.py` row. Phase 7's docs pass, per §11.
  `README.md`'s project-structure tree lists `project_manager.py`; the path is
  unchanged, so it is still correct, just incomplete.
- **`vulture_whitelist.py`** needed no change — none of its entries is in this
  file.

### 17.6 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Layering | `uv run pytest tests/test_import_layering.py -q` | `7 passed in 0.35s` (exit 0) |
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `195 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 68 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 164.37s (0:02:44)` (exit 0) |
| Coverage | same run | `TOTAL 11771 stmts, 893 miss, 92%` |

Test count is unchanged at 4256 — 4b adds no test and removes none. `195 files
already formatted` is §16.6's 191 plus the four new modules; `68 source files`
is mypy's 64 plus the same four. Statements rose 11747 → 11771 (+24, the
façade's imports and `__all__`) and misses held at 893, so no per-module floor
moved. Per-module: `_paths.py` 60/0/100%, `_artifacts.py` 252/17/93%,
`_phase_markdown.py` 205/0/100%, `_usage.py` 158/4/97%, `project_manager.py`
108/1/99% — against 759/22/97% for the pre-split file.

## 18. Phase 4c — `agents/code_scanner.py` split into the package `agents/code_scanner/`

Recorded 2026-09-08 on branch `look-rework`. One module became a four-file
package; **no importer anywhere changed**, no test file was edited. The only
config change is the one §15.4 decision 1 forced (two ruff glob patterns).
Nothing was written under `.spec4/`, `.venv/` or `.git/`, and no git command
that mutates the repo was run.

This is the first sub-phase to use the **package** form. `code_scanner.py` was
deleted and `code_scanner/` created in its place, so the import path
`spec4.agents.code_scanner` — the string `session.py`'s dispatch, `test_agents.py`,
`test_code_scanner_progress.py`, `test_renderer_goldens.py` and
`test_stream_status.py` all use — is unchanged, and `from spec4.agents import
code_scanner` still binds the same name to the same qualified module.

### 18.1 Line counts of the four resulting files

| File | Lines | Owns |
|---|---:|---|
| `agents/code_scanner/__init__.py` | 422 | façade + the agent turn loop: `run`, the two seeds, the extract/validate pair, the re-exports and `__all__` |
| `agents/code_scanner/_prompt.py` | 655 | the frozen `SYSTEM_PROMPT` and nothing else |
| `agents/code_scanner/_review_render.py` | 501 | `_format_review_as_text` + the seven section renderers + four coercion helpers |
| `agents/code_scanner/_scan.py` | 321 | repo walk, project-context gathering, the size budgets |
| **total** | **1899** | was **1741** in one file (+158: three docstrings, three import blocks, the façade's re-export block and `__all__`) |

The largest file in the package is now the prompt, which is data. The largest
*code* file is 501 lines, down from 1741 — and `_review_render.py` is exactly
the file Phase 5 will decompose, now isolated from everything else.

### 18.2 The names moved to each

All 43 top-level names are accounted for: 38 moved, 5 stayed. Nothing was
dropped, added, or renamed — **no name changed spelling in 4c**, as in 4b.
§15.4's decision 2 (public names, underscore aliases in the façade) was
4a-specific: the split has exactly **one cross-module private reference**
(`_review_render` importing `_render_coding_style` from `spec4.agents._utils`),
and that name is not one 4c created — it is a pre-existing `_utils` import that
travelled with the renderer that uses it. The plan's "no cross-module private
imports" rule is otherwise satisfied without a rename, because the four modules
have no other reference to each other's privates that the façade does not make.

**`_scan.py`** — repo walk, context gathering, budgets (24):
`_SKIP_DIRS`, `_MANIFEST_FILES`, `_DEPLOY_SIGNAL_FILES`, `_README_NAMES`,
`_CI_DIR_PARTS`, `_CI_FILE_BASENAMES`, `_TERRAFORM_DIRS`, `_MAX_TREE_FILES`,
`_MAX_MANIFEST_CHARS`, `_MAX_MANIFEST_FILE_CHARS`, `_MAX_README_LINES`,
`_MAX_PRIORITY_SOURCE_FILES`, `_MAX_SOURCE_SAMPLE_CHARS`,
`_MAX_SOURCE_SAMPLE_LINES`, `_SOURCE_EXTENSIONS`, `_ENTRYPOINT_NAME_STEMS`,
`_is_entrypoint_candidate`, `_read_text_safely`, `_collect_files`,
`_gather_project_context`, `_format_readme_block`, `_format_ci_block`,
`_format_deployment_signals`, `_approx_tokens`.

`_approx_tokens` is here rather than beside `run` because §15.3 assigns
"budgets" to `_scan`: it is display-only sizing (D-SC-P2) of the same evidence
the `_MAX_*` constants bound. It is reached as `code_scanner._approx_tokens` by
`test_code_scanner_progress.py:496,499,523,535` and resolves through the façade.

**`_prompt.py`** — the frozen prompt (1): `SYSTEM_PROMPT`.

**`_review_render.py`** — review → transcript text (13): `_as_str_list`,
`_name_label`, `_style_value`, `_normalize_style_for_renderer`,
`_format_empty_review`, `_format_review_as_text`, `_render_persistence`,
`_render_env_vars`, `_render_deployment`, `_render_api_surface`, `_render_auth`,
`_render_ai_capabilities`, `_render_typed_notes`.

**`__init__.py`** — stayed (5): `_extract_review_json`,
`_extract_and_validate_review`, `_build_fresh_scan_seed`,
`_build_update_scan_seed`, `run`. The extract/validate pair stayed because it is
the turn loop's own step — it is called twice from `run` and nowhere else, and it
is the only code that touches `_code_review_schema`.

### 18.3 The resulting import graph

```
_prompt   _scan   _review_render → spec4.agents._utils (_render_coding_style)
     \      |      /
      code_scanner/__init__  (façade + run)
```

Acyclic; `_prompt` and `_scan` import nothing from `spec4` at all (`_scan` needs
only `pathlib`, `_prompt` nothing). Every edge stays inside `spec4.agents`, so
§15.2's four rules hold — and unlike 4b, they hold *because they are enforced*:
`spec4.agents.code_scanner._scan` and its siblings all match the
`spec4.agents` prefix already in `_AGENT_SIDE`, which is exactly the
package-conversion case §15.2 anticipated. `tests/test_import_layering.py` was
not edited and all 7 tests pass.

No module in the package imports `layouts`, `callbacks`, `app` or `session`.

### 18.4 How "no logic changes" was verified

- **AST equality per definition.** All 43 top-level definitions were re-parsed
  from their new home and `ast.dump`-compared against the same definition in
  `HEAD:src/spec4/agents/code_scanner.py`: **43 matched exactly, 0 missing,
  0 added, 0 renamed.**
- **`SYSTEM_PROMPT` byte-for-byte.** Compared as raw text (not AST), from
  `SYSTEM_PROMPT = """\` through its closing `"""`, old file vs `_prompt.py`:
  **identical**. It is the only string constant that moved, so rule 4's
  "every string that ends up in an LLM prompt" is closed by that one comparison.
- **Attribute surface.** Every `code_scanner.<name>` reference in `src/`,
  `tests/`, `evals/` and `scripts/` was enumerated and resolved against the
  imported package: **all resolve.** That includes `code_scanner.llm`, which
  `test_code_scanner_progress.py` (11 sites) and `test_stream_status.py:289`
  reach with `patch.object` — `llm` is still imported into `__init__.py`, where
  `run` lives, so the patch reaches the same binding `run` reads.
- **§15.5 invariants.** `dash._callback.GLOBAL_CALLBACK_MAP` still holds **92**
  callbacks after a fresh `spec4.app` import; `tests/test_streaming_characterization.py`
  and `tests/test_layout_contract.py` were not edited (no test file was).
- **`tests/test_renderer_goldens.py` passes unmodified** — 22 passed. It imports
  `_format_review_as_text` from `spec4.agents.code_scanner` by name, through the
  re-export, and every golden byte matches.
- **Coverage attribution, not coverage loss.** The four files together are
  634 stmts / 21 miss / 97%, against 624 / 21 / 97% for the single pre-split
  file. Same 21 missed lines; the +10 statements are the façade's imports and
  `__all__`. Suite-wide misses unchanged at 893.

### 18.5 The one config change, and why it was forced

`pyproject.toml`, two lines, exactly as §15.4 decision 1 specified:

```
-"src/spec4/agents/*.py" = ["E501"]
-"src/spec4/agentifier/*.py" = ["E501"]
+"src/spec4/agents/**/*.py" = ["E501"]
+"src/spec4/agentifier/**/*.py" = ["E501"]
```

Ruff's `*` does not cross a directory separator, so `_prompt.py` — which has
**14 lines over 88 characters**, all inside the frozen prompt — would have lost
the exemption and failed the ruff gate. Verified both directions:
`uv run ruff check --select E501 src/spec4/agents/code_scanner/_prompt.py`
passes under the project config, and the same file under
`ruff check --isolated --select E501 --line-length 88` reports `Found 14 errors`.
`**/*.py` still matches the flat siblings (`agents/_utils.py`,
`agentifier/agentifier.py`), so no file lost its exemption. The `agentifier`
pattern was widened at the same time per §15.4, ahead of 4i. No rule set
changed; `select = ["E", "F"]` is untouched.

### 18.6 Deferred / not acted on

- **§17.5's `_AGENT_SIDE` gap is still open, and 4c does not widen it.** 4b's
  four flat siblings (`spec4._paths`, `spec4._artifacts`, `spec4._phase_markdown`,
  `spec4._usage`) are still outside the layering contract's agent-side prefix
  set. 4c does not inherit the problem — a package under `spec4.agents` is
  covered by the existing prefix — so nothing here forced the fix, and editing
  the contract test is not this sub-phase's scope (rule 7). It remains a
  four-string edit and should be closed in 4d or in 4j.
- **`run` is 198 lines and `_format_review_as_text` is 168.** Both are Phase 5
  decomposition targets (§5.1 lists `_format_review_as_text` at C901). 4c moved
  them; it did not shrink them.
- **4j** owns the importer cleanup for this package. There are no aliases to
  retire. The candidates: no importer outside the package reaches `_scan`'s
  16 constants or `_review_render`'s four coercion helpers by name, so those
  20 entries in `__all__` exist only to preserve the pre-split attribute
  surface and can be trimmed once 4j confirms it. `_format_empty_review`,
  `_is_entrypoint_candidate`, `_read_text_safely`, `_format_readme_block`,
  `_format_ci_block` and `_format_deployment_signals` are in the same position.
  Logged as Phase 2-style candidates, not deleted — 4j moves imports, it does
  not remove definitions.
- Nothing new for *Bugs found (not fixed)*.

### 18.7 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Layering | `uv run pytest tests/test_import_layering.py -q` | `7 passed in 0.36s` (exit 0) |
| Goldens | `uv run pytest tests/test_renderer_goldens.py -q` | `22 passed in 0.08s` (exit 0) |
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `198 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 71 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 166.43s (0:02:46)` (exit 0) |
| Coverage | same run | `TOTAL 11781 stmts, 893 miss, 92%` |

Test count is unchanged at 4256 — 4c adds no test and removes none. `198 files
already formatted` is §17.6's 195 plus four new modules minus the deleted one;
`71 source files` is mypy's 68 by the same arithmetic. Statements rose
11771 → 11781 (+10, the façade's imports and `__all__`) and misses held at 893,
so no per-module floor moved.

## 19. Phase 4d — `agents/stack_advisor.py` split into the package `agents/stack_advisor/`

Recorded 2026-09-08 on branch `look-rework`. One module became a four-file
package; **no importer anywhere changed** and `pyproject.toml` is untouched.
One test file changed by one line, and that line is a filesystem path, not an
import — see §19.5. Nothing was written under `.spec4/`, `.venv/` or `.git/`,
and no git command that mutates the repo was run.

The second sub-phase to use the **package** form, following 4c exactly.
`stack_advisor.py` was deleted and `stack_advisor/` created in its place, so the
import path `spec4.agents.stack_advisor` — the string `session.py`'s dispatch,
`test_agents.py`, `test_stack_shape_resilience.py`, `test_stack_persistence_block.py`,
`test_stack_render_totality.py`, `test_stack_output_rendering.py`,
`test_renderer_goldens.py`, `test_cross_cutting_relocation.py`,
`test_stream_status.py`, `test_pipeline_greenfield.py` and five `evals/stack_advisor/`
harnesses all use — is unchanged, and `from spec4.agents import stack_advisor`
still binds the same name to the same qualified module.

### 19.1 Line counts of the four resulting files

| File | Lines | Owns |
|---|---:|---|
| `agents/stack_advisor/__init__.py` | 321 | façade + the agent turn loop: `run`, the four seeds, the re-exports and `__all__` |
| `agents/stack_advisor/_prompt.py` | 641 | the frozen `SYSTEM_PROMPT` and nothing else |
| `agents/stack_advisor/_render.py` | 423 | `_format_stack_as_text` + the two fall-through renderers + the id/coercion helpers |
| `agents/stack_advisor/_stack_shape.py` | 172 | revision delta and note, shape normalisation, JSON extraction |
| **total** | **1557** | was **1432** in one file (+125: four docstrings, four import blocks, the façade's re-export block and `__all__`) |

As in 4c the largest file in the package is now the prompt, which is data. The
largest *code* file is 423 lines, down from 1432 — and `_render.py` is exactly
the file Phase 5 opens with, now isolated from the prompt, the seeds and the
turn loop.

### 19.2 The names moved to each

All 19 top-level names are accounted for: 18 moved, 1 stayed. Nothing was
dropped, added, or renamed — **no name changed spelling in 4d**, as in 4b and 4c.
§15.4's decision 2 (public names plus underscore aliases) was 4a-specific and
does not apply: the split creates **zero cross-module private references between
the three new siblings**. `_stack_shape` and `_render` do not import each other,
and neither imports the façade. Each has exactly one pre-existing private import
from `spec4.agents._utils` — `_extract_json_block` and `_render_references`
respectively — and both travelled with the function that already used them, so
the plan's "no cross-module private imports" rule is satisfied without a rename.

**`_prompt.py`** — the frozen prompt (1): `SYSTEM_PROMPT`.

**`_stack_shape.py`** — reply → walkable `stack_spec` (5): `revision_delta`,
`build_revision_note`, `_keyed_from_list`, `_normalise_stack_shape`,
`_extract_stack_json`.

`revision_delta` and `build_revision_note` are here rather than beside `run`
because §15.3 assigns "revision note" to `_stack_shape`: both are deterministic
reads of the vision's Brainstormer-stamped `revision_history`, they call nothing
in the turn loop, and `run` reaches them the same way it reaches
`_extract_stack_json`. They are the only two public names in the package besides
`run`, and `test_agents.py:670-740` reaches both as `stack_advisor.<name>`
through the façade.

**`_render.py`** — `stack_spec` → transcript text (12): `_as_list`, `_as_ids`,
`_scalar_text`, `_label`, `_ID_KEYS`, `_ID_LABELS`, `_render_any`,
`_render_rest`, `_render_entry_links`, `_format_stack_as_text`,
`_TOP_LEVEL_HANDLED`, `_render_library_entries`. Definition order inside the
file is the pre-split order untouched, including `_TOP_LEVEL_HANDLED` and
`_render_library_entries` sitting *after* the function that reads them — both
are resolved at call time, and reordering them would not have been a byte-for-byte
move.

**`__init__.py`** — stayed (1): `run`. Everything `run` does is the turn loop:
the staleness/resume/replay branch, the four seed variants, the stream, the
artifact re-ask, and the D-SC18a render-before-commit tail.

Two `_utils` names are re-exported from the façade without being used there —
`_extract_json_block` and `_render_references`. They were attributes of the
pre-split module, the code that used them moved to a sibling, and listing them
in `__all__` keeps `spec4.agents.stack_advisor.<name>` resolving exactly as
before (and keeps ruff from reading them as dead imports). Logged as 4j
candidates in §19.6.

### 19.3 The resulting import graph

```
_prompt   _stack_shape → spec4.agents._utils (_extract_json_block)
     \         |
      \        |         _render → spec4.agents._utils (_render_references)
       \       |        /
        stack_advisor/__init__  (façade + run)
                → spec4.{project_manager, llm, websearch}, spec4.agents._utils,
                  spec4.app_constants
```

Acyclic; `_prompt` imports nothing at all, and the three siblings have no edge
to each other or to the façade. Every edge stays inside `spec4`, and the three
new modules all match the `spec4.agents` prefix already in `_AGENT_SIDE`, so
§15.2's four rules cover them without a change — the package-conversion case
§15.2 anticipated and 4c first exercised. `tests/test_import_layering.py` was not
edited and all 7 tests pass.

No module in the package imports `layouts`, `callbacks`, `app` or `session`.

### 19.4 How "no logic changes" was verified

- **AST equality per definition.** All 19 top-level definitions were re-parsed
  from their new home and `ast.dump`-compared against the same definition in
  `HEAD:src/spec4/agents/stack_advisor.py`: **19 matched exactly, 0 missing,
  0 added, 0 renamed, 0 defined twice.**
- **`SYSTEM_PROMPT` byte-for-byte.** Compared as raw text (not AST), from
  `SYSTEM_PROMPT = """\` through its closing `"""`, old file vs `_prompt.py`:
  **identical, 46,476 characters.** It is the only string constant that moved,
  so rule 4's "every string that ends up in an LLM prompt" is closed by that one
  comparison. `test_stack_exemplar_demonstrates_linkage.py` (49 tests, all of
  them prompt-text assertions) and `test_cross_cutting_relocation.py` agree.
- **Attribute surface.** All **44** attributes of the pre-split module — the 19
  definitions plus every name its import block bound — were enumerated from
  `HEAD` and resolved against the imported package: **all 44 resolve.** Every
  `stack_advisor.<name>` reference in `src/`, `tests/`, `evals/` and `scripts/`
  was then enumerated and resolved the same way: `run`, `revision_delta`,
  `build_revision_note`, `_format_stack_as_text` and `llm` — **all resolve.**
  (The only unresolved matches are `stack_advisor.click`, `.locator`,
  `.wait_for_url`, `.wait_for_selector` and `.eval_on_selector_all` in
  `tests/integration/test_chat_frame_e2e.py`, where `stack_advisor` is a
  Playwright `Page` fixture, not this module.)
- **The two patch targets still bind what `run` reads.** `llm` is still imported
  into `__init__.py`, so `patch("spec4.agents.stack_advisor.llm.stream_turn")`
  (`test_pipeline_greenfield.py:190,267`) reaches the same object; and
  `_format_stack_as_text` is imported into `__init__.py` as a bare global, so
  `patch.object(stack_advisor, "_format_stack_as_text", …)`
  (`test_stack_shape_resilience.py:197,209`) still intercepts the call `run`
  makes. Both test files pass unedited.
- **§15.5 invariants.** `dash._callback.GLOBAL_CALLBACK_MAP` still holds **92**
  callbacks after a fresh `spec4.app` import; `tests/test_streaming_characterization.py`
  and `tests/test_layout_contract.py` were not edited.
- **`tests/test_renderer_goldens.py` passes unmodified** — 22 passed. It imports
  `_format_stack_as_text` from `spec4.agents.stack_advisor` by name, through the
  re-export, and every golden byte matches.
- **Coverage attribution, not coverage loss.** The four files together are
  412 stmts / 8 miss / 98%, against 401 / 8 / 98% for the single pre-split file.
  Same 8 missed lines; the +11 statements are the façade's imports and `__all__`.
  Suite-wide misses unchanged at 893.

### 19.5 The one forced edit outside `src/`, and why

`tests/test_stack_exemplar_demonstrates_linkage.py`, one line:

```
-        .joinpath("src/spec4/agents/stack_advisor.py")
+        .joinpath("src/spec4/agents/stack_advisor/_prompt.py")
```

`_welded_folds()` does not import the prompt — it reads the *source file* off
disk and regexes `SYSTEM_PROMPT = """(.*?)"""` out of it, so that it can see the
backslash line-continuations as written rather than the folded string. A path,
not an import: the split moved the file, so the path had to follow or the test
raised `FileNotFoundError` (it did, once, before the edit). The regex, the
assertions and every other line of the file are untouched, and it passes 49/49
against `_prompt.py` — which is the same argument as §18.5's ruff-glob change:
a mechanical consequence of the file moving, not a change of scope.

No other test, and no file under `src/`, references a `stack_advisor` path or
import that the split invalidated. **`pyproject.toml` needed no change** — 4c
already widened the ruff per-file-ignore to `"src/spec4/agents/**/*.py"`, which
covers the nested `_prompt.py`. Verified both directions: it passes
`uv run ruff check --select E501 …` under the project config, and the same file
under `ruff check --isolated --select E501 --line-length 88` reports
`Found 208 errors`.

### 19.6 Deferred / not acted on

- **`_format_stack_as_text` is 239 lines** (C901 61, §5.1's worst function in the
  repo) **and `run` is 219.** 4d moved them; it did not shrink them. Decomposing
  `_format_stack_as_text` is Phase 5's opening move and is now a single-file job
  in `_render.py`, which is what §15.3 wanted from this sub-phase.
- **§17.5's `_AGENT_SIDE` gap is still open.** 4b's four flat siblings
  (`spec4._paths`, `spec4._artifacts`, `spec4._phase_markdown`, `spec4._usage`)
  remain outside the layering contract's agent-side prefix set. §18.6 offered
  4d or 4j as its home; 4d did not force it — a package under `spec4.agents` is
  already covered by the existing prefix, exactly as in 4c — so under rule 7 it
  stays a four-string edit to `tests/test_import_layering.py` for **4j**.
- **Two documentation references to the deleted filename.** `README.md:225`'s
  project-structure tree still lists `agents/stack_advisor.py` (it also still
  lists `agents/code_scanner.py` from 4c), and `agents/_feature_context.py:183`'s
  docstring points at ``stack_advisor.py``. Phase 7 owns the README tree; the
  docstring is a 4j-or-Phase-7 one-word fix. Neither is load-bearing.
- **4j owns the importer cleanup for this package.** There are no aliases to
  retire. The candidates: nothing outside the package imports or reaches
  `_as_ids`, `_as_list`, `_scalar_text`, `_label`, `_ID_KEYS`, `_ID_LABELS`,
  `_render_any`, `_render_rest`, `_render_entry_links`, `_render_library_entries`,
  `_TOP_LEVEL_HANDLED`, `_keyed_from_list`, `_extract_json_block` or
  `_render_references` by name, so those 14 `__all__` entries exist only to
  preserve the pre-split attribute surface and can be trimmed once 4j confirms
  it. The five names that *are* reached from outside — `SYSTEM_PROMPT`,
  `_format_stack_as_text`, `_extract_stack_json`, `_normalise_stack_shape`,
  `run` — plus the two public ones reached by attribute (`revision_delta`,
  `build_revision_note`) stay. Logged as Phase 2-style candidates, not deleted.
- Nothing new for *Bugs found (not fixed)*.

### 19.7 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Layering | `uv run pytest tests/test_import_layering.py -q` | `7 passed` (exit 0) |
| Goldens | `uv run pytest tests/test_renderer_goldens.py -q` | `22 passed` (exit 0) |
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `201 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 74 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 167.28s (0:02:47)` (exit 0) |
| Coverage | same run | `TOTAL 11792 stmts, 893 miss, 92%` |

Test count is unchanged at 4256 — 4d adds no test and removes none. `201 files
already formatted` is §18.7's 198 plus four new modules minus the deleted one;
`74 source files` is mypy's 71 by the same arithmetic. Statements rose
11781 → 11792 (+11, the façade's imports and `__all__`) and misses held at 893,
so no per-module floor moved.

## 20. Phase 4e — `agents/phaser.py` split into the package `agents/phaser/`

Recorded 2026-09-08 on branch `look-rework`. One module became a four-file
package; **no importer anywhere changed, no test file was edited, and
`pyproject.toml` is untouched** — the first package sub-phase to need no edit at
all outside `src/spec4/agents/phaser/`. Nothing was written under `.spec4/`,
`.venv/` or `.git/`, and no git command that mutates the repo was run.

The third sub-phase to use the **package** form, following 4c and 4d exactly.
`phaser.py` was deleted and `phaser/` created in its place, so the import path
`spec4.agents.phaser` — the string `session.py:8,475` dispatches through, that
`tests/test_agents.py`, `tests/test_stack_additions.py`,
`tests/test_stream_status.py`, `tests/test_agent_llm_selection.py` and
`evals/phaser/` use — is unchanged, and `from spec4.agents import phaser` still
binds the same name to the same qualified module.

### 20.1 Line counts of the four resulting files

| File | Lines | Owns |
|---|---:|---|
| `agents/phaser/__init__.py` | 579 | façade + the agent turn loop: `run`, the seeds, the retry protocol, the re-exports and `__all__` |
| `agents/phaser/_prompt.py` | 552 | the frozen `SYSTEM_PROMPT` and nothing else |
| `agents/phaser/_phase_extract.py` | 261 | the JSON walk, both extractors, truncation/schema/completeness checks, the display renderer |
| `agents/phaser/_revision.py` | 90 | the design-mock note, the revision delta and its phase-scoping note |
| **total** | **1482** | was **1378** in one file (+104: four docstrings, four import blocks, the façade's re-export block and `__all__`) |

As in 4c and 4d the largest file in the package is now the prompt, which is
data. The largest *code* file is the façade at 579 lines, of which `run` is 493
— and per §15.3 `run` stays whole; shrinking it is Phase 5's job, now with the
prompt, the extractors and the revision helpers out of the file.

### 20.2 The names moved to each

All 12 top-level names are accounted for: 11 moved, 1 stayed. Nothing was
dropped, added, renamed or defined twice — **no name changed spelling in 4e**,
as in 4b, 4c and 4d. §15.4's decision 2 (public names plus underscore aliases)
was 4a-specific and does not apply: the split creates **zero cross-module
references between the three new siblings**. `_phase_extract` and `_revision` do
not import each other, neither imports `_prompt`, and none imports the façade.

**`_prompt.py`** — the frozen prompt (1): `SYSTEM_PROMPT`.

**`_phase_extract.py`** — reply text → validated phase list (7):
`_objects_with_key`, `_extract_and_strip_stack_additions`, `_extract_phases`,
`_appears_truncated`, `_extract_and_validate_phases`,
`_phase_completeness_failure`, `_format_phases_for_display`.

`_format_phases_for_display` is the one placement §15.3's three-word summaries
did not decide. It is neither extraction nor revision: it renders the extracted
list as Markdown. It went here because it is the tail of the same pipeline —
its argument is exactly `_extract_and_validate_phases`'s first return value, and
`run` calls the two within four lines of each other — and because the
alternative (leaving a three-line pure renderer in the façade) would have put
the only non-turn-loop function back in the file the split exists to thin. Its
one dependency, `project_manager.render_phase_markdown`, is the sole reason
`_phase_extract` imports `project_manager`; that edge already existed in the
pre-split module.

**`_revision.py`** — deterministic seed material (3): `_load_phaser_design_note`,
`revision_delta`, `build_revision_note`.

`_load_phaser_design_note` is grouped with the revision pair, rather than left
beside the seeds it feeds, because §15.3 assigns "design note" to `_revision`
and because all three share the same shape: pure, deterministic reads of input
that exists before the model is called, returning a bracketed note the seed
builder concatenates. It is also the only filesystem read in the package.
`revision_delta` and `build_revision_note` are the only public names in the
package besides `run`; `test_agents.py` reaches `_load_phaser_design_note`
through the façade at lines 2314-2333.

**`__init__.py`** — stayed (1): `run`. Everything `run` does is the turn loop:
the staleness/replay branch, the four seed variants, the stream, the
stack-addition strip, the validation-retry drain (D-PH9), the seam check and
coverage advisories, and the commit tail.

`validate_phase` is re-exported from the façade without being used there. It was
an attribute of the pre-split module, the code that used it
(`_extract_and_validate_phases`) moved to a sibling, and listing it in `__all__`
keeps `spec4.agents.phaser.validate_phase` resolving exactly as before (and
keeps ruff from reading it as a dead import). Logged as a 4j candidate in §20.6.

### 20.3 The resulting import graph

```
_prompt   _revision      _phase_extract → spec4.project_manager,
     \        |          /                spec4.agents._phase_schema
      \       |         /
       phaser/__init__  (façade + run)
           → spec4.{project_manager, llm, websearch}, spec4.agents._utils,
             spec4.agents._phase_coverage, spec4.agents._phase_schema,
             spec4.agents._seam_check, spec4.app_constants
```

Acyclic; `_prompt` imports nothing at all and `_revision` imports only stdlib.
Every edge stays inside `spec4`, and the three new modules all match the
`spec4.agents` prefix already in `_AGENT_SIDE`, so §15.2's four rules cover them
without a change — the package-conversion case §15.2 anticipated, now exercised
a third time. `tests/test_import_layering.py` was not edited and all 7 tests
pass.

No module in the package imports `layouts`, `callbacks`, `app` or `session`.

### 20.4 How "no logic changes" was verified

- **AST equality per definition.** All 12 top-level definitions were re-parsed
  from their new home and `ast.dump`-compared against the same definition in
  `HEAD:src/spec4/agents/phaser.py`: **12 matched exactly, 0 differing,
  0 missing, 0 added, 0 renamed, 0 defined twice.** Definition order inside each
  new file is the pre-split order untouched.
- **`SYSTEM_PROMPT` byte-for-byte.** Compared as raw text (not AST), from
  `SYSTEM_PROMPT = """\` through its closing `"""`, old file vs `_prompt.py`:
  **identical, 32,614 characters.** It is the only string constant that moved,
  so rule 4's "every string that ends up in an LLM prompt" is closed by that one
  comparison.
- **Attribute surface: 34 of the pre-split module's 36 attributes resolve.** The
  36 are the 12 definitions plus every name the old import block bound. The two
  that do not are `re` and `Path` — stdlib module objects that were imported
  only for code that moved (`re.sub` in `_extract_and_strip_stack_additions`,
  the `Path` annotation on `_load_phaser_design_note`), and that now live on the
  sibling that needs them. Nothing in `src/`, `tests/`, `evals/` or `scripts/`
  writes `phaser.re`, `phaser.Path`, or imports either name from the module —
  grepped, zero hits. Every *`spec4`* name is preserved, which is why
  `validate_phase` is re-exported (§20.2) rather than dropped with them; 4c set
  the precedent for dropping a moved import from the façade
  (`_render_coding_style`, §18) and 4d for keeping one (`_extract_json_block`,
  §19.2), and 4e keeps the spec4 ones and drops the two stdlib ones.
- **Both patch targets still bind what `run` reads.** `run_seam_check` is
  imported into `__init__.py` as a bare global, so
  `patch("spec4.agents.phaser.run_seam_check", …)` (8 sites in
  `tests/test_agents.py`) still intercepts the call `run` makes; and `llm` is
  still imported there, so `patch("spec4.agents.phaser.llm.stream_turn", …)`
  (`tests/integration/test_pipeline_greenfield.py:202,289`) reaches the same
  object. Both files pass unedited.
- **§15.5 invariants.** `dash._callback.GLOBAL_CALLBACK_MAP` still holds **92**
  callbacks after a fresh `spec4.app` import; `tests/test_streaming_characterization.py`
  and `tests/test_layout_contract.py` were not edited.
- **Formatting.** `ruff format` touched the two new sibling modules once, adding
  a single blank line each after the import block (two lines before the first
  `def`). Diffed before/after: **the only change in either file is that blank
  line** — no code line moved, so the byte-for-byte claim survives the
  formatter. Re-verified by re-running the AST comparison after formatting.
- **Coverage attribution, not coverage loss.** The four files together are
  313 stmts / 8 miss / 97%, against 301 / 8 / 97% for the single pre-split file.
  Same 8 missed lines; the +12 statements are the façade's imports and `__all__`.
  Suite-wide misses unchanged at 893.

### 20.5 No forced edit outside `src/`

Unlike 4c (a ruff glob in `pyproject.toml`) and 4d (a filesystem path in
`test_stack_exemplar_demonstrates_linkage.py`), 4e forced nothing outside the
package. Checked explicitly:

- **No test reads `phaser.py` off disk.** The only prompt-source-reading test is
  `test_stack_exemplar_demonstrates_linkage.py`, and it reads StackAdvisor's
  prompt, not Phaser's. Grepped for `phaser.py` and `agents/phaser` across all
  of `src/`, `tests/`, `evals/` and `scripts/`: zero path references.
- **`pyproject.toml` needed no change.** 4c already widened the ruff
  per-file-ignore to `"src/spec4/agents/**/*.py"`, which covers the nested
  `_prompt.py`; `uv run ruff check src/ tests/` passes with the frozen prompt's
  long lines in place.
- Every `phaser.<name>` reference in the repo resolves through the façade, so no
  import statement anywhere changed.

### 20.6 Deferred / not acted on

- **`run` is 493 lines** (§5.1 lists it at C901 33, the repo's fourth worst
  function, with 148 statements and 37 branches).
  4e moved everything around it; it did not shrink it, per §15.3's "`run` stays
  whole — shrinking it is Phase 5". It is now the only function in
  `__init__.py`, which is what this sub-phase was for.
- **§17.5's `_AGENT_SIDE` gap is still open.** 4b's four flat siblings
  (`spec4._paths`, `spec4._artifacts`, `spec4._phase_markdown`, `spec4._usage`)
  remain outside the layering contract's agent-side prefix set. As in 4c and 4d,
  a package under `spec4.agents` is already covered by the existing prefix, so
  4e did not force it either; under rule 7 it stays a four-string edit to
  `tests/test_import_layering.py` for **4j**.
- **`README.md:226`'s project-structure tree still lists `agents/phaser.py`**,
  alongside the `agents/code_scanner.py` and `agents/stack_advisor.py` entries
  §18.6 and §19.6 already flagged. Phase 7 owns the tree; three lines, one edit.
  `tests/README.md:12` also lists `spec4/agents/phaser.py` with stale line
  numbers — already flagged for Phase 7 at §11 and line 1092.
- **4j owns the importer cleanup for this package.** There are no aliases to
  retire. The candidates: nothing outside the package imports or reaches
  `_objects_with_key`, `_extract_and_validate_phases`, `_format_phases_for_display`
  or `validate_phase` by name, so those four `__all__` entries exist only to
  preserve the pre-split attribute surface and can be trimmed once 4j confirms
  it. The names that *are* reached from outside — `run`, `_extract_phases`,
  `_extract_and_strip_stack_additions`, `_appears_truncated`,
  `_load_phaser_design_note`, `_phase_completeness_failure` (all from `tests/`;
  all by direct `from spec4.agents.phaser import …` except `_appears_truncated`,
  which `test_phaser_seed_inputs.py:155,156,162` reaches as an attribute on the
  façade — as it does `SYSTEM_PROMPT` at :201,247), plus the two public ones
  (`revision_delta`, `build_revision_note`) and `SYSTEM_PROMPT` — stay. Logged
  as Phase 2-style candidates, not deleted.
- Nothing new for *Bugs found (not fixed)*.

### 20.7 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Layering | `uv run pytest tests/test_import_layering.py -q` | `7 passed` (exit 0) |
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `204 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 77 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 163.71s (0:02:43)` (exit 0) |
| Coverage | same run | `TOTAL 11804 stmts, 893 miss, 92%` |

Test count is unchanged at 4256 — 4e adds no test and removes none. `204 files
already formatted` is §19.7's 201 plus four new modules minus the deleted one;
`77 source files` is mypy's 74 by the same arithmetic. Statements rose
11792 → 11804 (+12, the façade's imports and `__all__`) and misses held at 893,
so no per-module floor moved.

## 21. Phase 4f — `layouts/_chat.py` split into three siblings, and the cycle closed

Recorded 2026-09-08 on branch `look-rework`. Four files under `src/spec4/layouts/`
changed or added; **one test file edited — two import paths in
`tests/test_chat_pill_bar.py`, the edit §15.3's 4f entry anticipated and the task
permitted.** No other importer anywhere changed, `pyproject.toml` is untouched.
Nothing was written under `.spec4/`, `.venv/` or `.git/`, and no git command was
run.

Unlike 4c–4e, this is a **flat sibling split, not a package conversion** — the
`_prompt.py` collision that forced packages under `agents/` has no analogue here,
`layouts/` is already a package, and `_chat_status` / `_chat_actions` /
`_chat_panels` are the names §15.3 proposed.

### 21.1 Line counts

| File | Lines | Before |
|---|---:|---:|
| `_chat.py` (façade) | 260 | 997 |
| `_chat_status.py` | 148 | — |
| `_chat_actions.py` | 455 | — |
| `_chat_panels.py` | 289 | — |
| **total** | **1152** | **997** |

The +155 is compatibility layer and prose: the façade's three import blocks and
24-name `__all__`, four module docstrings, and the import header each new module
needs. No definition grew or shrank by a line — every one moved byte-for-byte
(§21.4), and the only body edit in the whole sub-phase is the three call sites
the cycle fix required (§21.3).

### 21.2 The names moved to each

All 24 top-level definitions are accounted for: 23 moved, 1 stayed. Nothing was
dropped, added, or renamed — **no name changed spelling in 4f**, as in 4b–4e.
§15.4's decision 2 (public names plus underscore aliases) was 4a-specific and
does not apply: the split creates **zero cross-module private references between
the three new siblings** — none of them imports either of the others, and none
imports the façade. The only private imports are the façade's own re-exports,
which is the same shape 4b–4e shipped.

**`_chat_status.py`** — the strip above the transcript (6): `_PILL_BASE`,
`_PILL_ACTIVE`, `_PILL_DONE`, `_PILL_UNREACHABLE`, `_completed_agents`,
`_agent_status_bar`. The 11-line comment block above the four `_PILL_*`
constants moved with them.

**`_chat_actions.py`** — the action row and the ids its controls carry (13):
`_TOKEN_COUNTER_AGENTS`, `_streamed_token_count`, `_token_count_text`,
`_NO_TOKEN_COUNT`, `_NO_CALLS_RECORDED`, `_turn_token_text`, `CHAT_ARTIFACTS`,
`DOWNLOAD_BTN_PREFIX`, `OPEN_BTN_PREFIX`, `open_button_id`, `_open_button`,
`_ff_controls`, `_chat_action_buttons`. The four token/counter helpers are here
rather than in `_chat_status` because `_chat_action_buttons` is their only
caller — the counter is a component *of* the row, and §15.3's "the strip above
the transcript" is the pill bar, which reads none of them. The banner comment
"Downloadable artifacts, and the Open control beside each Download" moved with
its block, as did the 38-line D-AR1/D-LR8 comment above `_chat_action_buttons`.

**`_chat_panels.py`** — the optional blocks between transcript and composer (4):
`_RUN_COMPLETE`, `_cost_summary`, `_retry_panel`, `_breadth_panel`.
§15.3's three-word summary for this module names only the last two; `_cost_summary`
(and the `_RUN_COMPLETE` table only it reads) is placed here because it has the
identical contract — `(session) -> Any | None`, `None` when inactive, spliced by
the frame with `*([x] if x is not None else [])` — and because the task's
"`_chat.py` keeps `_chat_layout` and the re-exports" leaves it nowhere else to
go. It is the one placement in 4f not spelled out in advance.

**Stayed in `_chat.py`** (1): `_chat_layout`. It is the one function that
assembles the three into a screen and belongs to none of them.

**Dropped from the façade: 22 imported names, 0 definitions.** They are names
`_chat.py` imported for code that moved, and each now lives on the sibling that
uses it: `AGENT_KEYS`, `PHASES_DIR`, the six `STATE_*_COMPLETE` constants, the
four `STEP_*` constants, `StepEntry`, `step_modifier_class`, `step_row`,
`_validate_agent_preconditions`, `project_manager`, `llm_selection`,
`run_cost_strip`, `close_selection`, `pool_from_dicts`, and `_llm_gate` itself.
4c set the precedent for dropping a moved import from the façade
(`_render_coding_style`, §18) and 4e for dropping two (`re`, `Path`, §20.4).
Two of the 22 are reached by name from outside — `AGENT_KEYS` and `step_row`,
both monkeypatched — and that is the whole of the test edit (§21.5).
`AGENT_DISPLAY_NAMES` and `PROGRESS_CLASS_NAMES` are *not* in the 22:
`_chat_layout` still reads both, so they stay bound on the façade.

### 21.3 The cycle, and what replaced it

§6.1's one cycle was a single line: `_chat.py:19`, `from spec4.layouts import
_llm_gate`, against `layouts/__init__.py:42`'s import of `_chat`. It is now

```python
from spec4.layouts._llm_gate import gate_card, is_open, model_chip
```

and the three call sites lost their module prefix — `_llm_gate.is_open(…)` →
`is_open(…)`, and likewise `gate_card` and `model_chip`. That is the **only**
change to a function body in this sub-phase; diffed against `HEAD`,
`_chat_layout` differs in exactly those three lines plus the one expression
`ruff format` re-joined once `_llm_gate.` no longer pushed it over 88 columns.

Rebuilding §6's edge set with the same `ast` walk afterwards: **`src/spec4/` is
now acyclic — zero cycles across all 80 modules**, counting lazy imports.
`spec4.layouts._chat` no longer has an edge to `spec4.layouts` at all, and the
three new siblings add none: `_chat_status` → `_agent_rows`, `_shared`,
`app_constants`, `project_manager`, `session`; `_chat_actions` →
`app_constants`, `_round_tree`; `_chat_panels` → `app_constants`,
`panel_closure`, `_round_cost`, `llm_selection`.

`tests/test_import_layering.py` passes unedited (7 tests). It has no cycle rule
— §15.2's four rules are about layer direction — so the acyclicity above is
asserted here by measurement, not by the suite. Making it a fifth rule is
**deferred**, and §21.6 says why it cannot be added today.

### 21.4 Verification beyond the gate

- **Byte-for-byte.** Every moved block was compared as raw text against the
  `HEAD` blob at its original line range: `_chat_status.py` = old lines 36–50,
  53–82, 85–144; `_chat_actions.py` = old lines 196–620 (one contiguous run —
  the token helpers and the artifact/action block were already adjacent);
  `_chat_panels.py` = old lines 147–193, 623–699, 702–830. All three matched
  exactly, **after** `ruff format` ran. The formatter reported "1 file
  reformatted, 3 files left unchanged" — the one file is the façade, for the
  expression named in §21.3.
- **Statement counts add up.** `coverage`'s own parser on the `HEAD` blob:
  179 statements. The four files now: 23 + 34 + 100 + 43 = **200**, +21. The
  suite-wide total moved 11804 → 11825, also +21, so **no other module's
  statement count changed** and the +21 is entirely the façade's imports and
  `__all__`.
- **Coverage attribution, not coverage loss.** The four files together are
  200 stmts / 1 miss / 99.5%, against 179 / 1 for the single pre-split file.
  The one missed line is the same one: the empty-`messages` `return 0` in
  `_streamed_token_count` (old `_chat.py:213`, now `_chat_actions.py:58`).
  Suite-wide misses unchanged at **893**, so no per-module floor moved.
- **Attribute surface: 24 of the pre-split module's 24 definitions resolve** on
  `spec4.layouts._chat`, checked by importing it and `hasattr`-ing every
  top-level name the old AST defined. The 22 that do not are the imports of
  §21.2; grepped across `src/`, `tests/`, `evals/` and `scripts/` for every one
  of them as `_chat.<name>` or `from spec4.layouts._chat import <name>` — two
  hits, both the monkeypatch sites of §21.5, zero elsewhere.
- **No importer changed.** The 18 names reached from outside the module
  (`src/spec4/layouts/__init__.py`, `src/spec4/callbacks/__init__.py`, and 17
  test modules) all resolve through the façade's `__all__`; `mypy --strict`
  implies `no_implicit_reexport`, so that list is load-bearing rather than
  decorative, exactly as in 4b.
- **§15.5 invariants.** `dash._callback.GLOBAL_CALLBACK_MAP` still holds **92**
  callbacks after a fresh `spec4.app` import; `tests/test_streaming_characterization.py`
  and `tests/test_layout_contract.py` were **not** edited, and
  `tests/test_layout_contract.py` (with the component-id snapshot it checks),
  `tests/test_callback_co_presence.py`, `tests/test_chat_open_links.py` and
  `tests/test_visual_register.py` pass unmodified — 175 tests.

### 21.5 The one forced edit outside `src/`

`tests/test_chat_pill_bar.py`, two lines, both the same statement:

```
-        import spec4.layouts._chat as chat
+        import spec4.layouts._chat_status as chat
```

at `:145` and `:309`. Both tests monkeypatch a *module global* that
`_agent_status_bar` reads — `AGENT_KEYS` and `AGENT_DISPLAY_NAMES` in the first
(the bar must walk the tuple rather than carry its own list), `step_row` in the
second (the bar must go through the shared renderer, D-LR9) — so the patch has
to land on the module the function now lives in. Nothing else in the file
changed: the top-level `from spec4.layouts._chat import _PILL_*,
_agent_status_bar` still resolves through the façade and was left alone, no
assertion moved, and the local alias stays `chat` so the diff is the import path
and nothing more. This is the "if a layout test needs an import path change"
case the task named, and §15.3 anticipated for 4f.

Checked and *not* forced: `pyproject.toml` (`layouts/` has no per-file-ignore to
widen — and no new file needs one), `README.md:240` (the tree names `layouts/`
as a directory, not its modules, so unlike 4c/4d/4e it does not go stale), and
`tests/README.md` (no `_chat` entry). No test reads `_chat.py` off disk.

### 21.6 Deferred / not acted on

- **A fifth layering rule — "no module under `spec4.layouts.*` imports the
  `spec4.layouts` package" — cannot be added yet.** One edge is left:
  `layouts/designer.py:11`, `from spec4.layouts import _llm_gate`, the same
  spelling 4f just removed from `_chat.py`. It is **not** a cycle today
  (`layouts/__init__.py` does not import `designer`), which is why 4f did not
  touch it under rule 7 — but it is the one line standing between the package
  and a mechanically-enforced acyclicity. One-line change plus one rule, and it
  belongs with `layouts/designer.py`'s own sub-phase or with **4j**. This is the
  `layouts` analogue of §15.2's rule 4, which does the same job for `callbacks/`
  from 4g.
- **§17.5's `_AGENT_SIDE` gap is still open.** 4b's four flat siblings
  (`spec4._paths`, `spec4._artifacts`, `spec4._phase_markdown`, `spec4._usage`)
  remain outside the layering contract's agent-side prefix set — unchanged by
  4f, which added no module under `spec4.agents`. Still a four-string edit to
  `tests/test_import_layering.py` for **4j**.
- **`_chat_action_buttons` is 215 lines** and is the sub-phase's largest moved
  definition: six near-identical `elif active == …` arms, each rebuilding the
  same `token_counter` `dmc.Text`. That is a Phase 5 finding (`C901`/`PLR0912`
  shaped), logged not fixed — 4f moved it, it did not shrink it, exactly as
  §15.3 says of `phaser.run`. It is now the only large function in its module.
- **4j owns the importer cleanup for this façade.** There are no aliases to
  retire. Two `src/` importers could move to the owning module —
  `src/spec4/callbacks/__init__.py:30` (`CHAT_ARTIFACTS`, `OPEN_BTN_PREFIX`,
  `open_button_id` → `_chat_actions`) and `src/spec4/layouts/__init__.py:42`
  (`_agent_status_bar` → `_chat_status`, `_chat_action_buttons` →
  `_chat_actions`) — and 17 test modules likewise. `_completed_agents`,
  `_open_button`, `_ff_controls`, `_RUN_COMPLETE`, `_NO_TOKEN_COUNT` and
  `_NO_CALLS_RECORDED` have no reader outside their own module at all, so those
  six `__all__` entries exist only to preserve the pre-split attribute surface
  and can be trimmed once 4j confirms it. Logged as Phase 2-style candidates,
  not deleted.
- Nothing new for *Bugs found (not fixed)*.

### 21.7 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Layering | `uv run pytest tests/test_import_layering.py -q` | `7 passed` (exit 0) |
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `207 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 80 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 164.63s (0:02:44)` (exit 0) |
| Coverage | same run | `TOTAL 11825 stmts, 893 miss, 92%` |

Test count is unchanged at 4256 — 4f adds no test and removes none; the two
edited lines are inside two existing tests. `207 files already formatted` is
§20.7's 204 plus three new modules; `80 source files` is mypy's 77 by the same
arithmetic. Statements rose 11804 → 11825 (+21, the façade's imports and
`__all__`) and misses held at 893, so no per-module floor moved.
