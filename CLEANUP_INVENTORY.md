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
| 4g2 | `callbacks/_chat.py` | 1182 | `_gate` (the per-agent model gate: hint, effort, use-default/keep/pick/chip/back, connect, continue), `_nav` (the agent pills, the inter-agent Continue buttons, and the Deployer pair) | Added by Robert during 4g. The four-way split leaves `_chat.py` the package's largest module by a wide margin; the gate (~340 lines, one self-contained flow with its own draft key) and the navigation buttons (~230) are the two blocks that come out of it cleanly, and neither is what "the chat frame" means. Its own run, after 4g. |
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

## 22. Phase 4g — `callbacks/__init__.py` split into four modules

Recorded 2026-09-08 on branch `look-rework`. Six files under
`src/spec4/callbacks/` changed or added; **thirteen test files edited — patch
targets and module aliases only, no assertion moved.** `pyproject.toml` is
untouched. Nothing was written under `.spec4/`, `.venv/` or `.git/`, and no git
command was run beyond `git show HEAD:…`, `git diff --stat` and `git status`, all
read-only.

Like 4f and unlike 4c–4e this is a **flat sibling split, not a package
conversion** — `callbacks/` is already a package, there is no `_prompt.py`
collision to dodge, and `_shared` / `_setup` / `_chat` / `_artifacts` are the
names §15.3 proposed.

### 22.1 Line counts

| File | Lines | Was |
|---|---:|---:|
| `callbacks/__init__.py` (façade) | 573 | 2460 |
| `callbacks/_shared.py` | 72 | — |
| `callbacks/_setup.py` | 364 | — |
| `callbacks/_chat.py` | 1182 | — |
| `callbacks/_artifacts.py` | 542 | — |
| **total** | **2733** | **2460** |

The +273 is compatibility layer and prose: the façade's 83-name `__all__` and its
four sibling import blocks, five module docstrings, and the import header each
new module needs. No definition grew or shrank by a line — every one moved
byte-for-byte (§22.4), and **no function body changed at all** in this
sub-phase; unlike 4f there was not even a call-site edit.

### 22.2 The names moved to each

All 82 top-level definitions plus the re-exported `FF_PROMPT` are accounted for:
70 moved, 13 stayed. Nothing was dropped, added, or renamed — **no name changed
spelling in 4g**, as in 4b–4f. §15.4's decision 2 (public names plus underscore
aliases) was 4a-specific and does not apply; the underscore names cross a module
boundary only through `_shared`, which exists for exactly that.

**`_shared.py`** — the helpers more than one module needs (3): `_HOME`,
`_gate_agent`, `_open_pick_fields`. `_HOME` is here because the façade's
directory-picker callbacks and `_chat`'s `on_deployer_new_project` both read it.
`_gate_agent` is here because `_open_pick_fields` calls it: leaving it beside the
gate callbacks in `_chat` would make `_shared` import `_chat` and invert the
dependency the module exists to keep straight. It registers **no** callback.

**`_setup.py`** — the wizard's three steps (11, 10 callbacks):
`_prefs_keep_working_dir`, `on_provider_hint`, `on_setup_connect`,
`on_setup_clear`, `on_setup_back_provider`, `on_setup_effort_options`,
`on_setup_model_continue`, `on_setup_back_model`, `on_search_provider_hint`,
`on_setup_search_connect`, `on_setup_search_skip`. `_prefs_keep_working_dir` is
here because its only two callers are: Connect writes the remembered credential,
Clear takes it away, and both must leave the working directory alone.

**`_chat.py`** — turns, gate, retry, breadth, poll, navigation (36, 29
callbacks): `_DEV_MODE`, `on_init_turn`, `on_chat_submit`, `on_fast_forward`,
`_gate_answered`, `on_gate_provider_change`, `on_gate_effort_options`,
`on_gate_use_default`, `on_gate_keep`, `on_gate_pick`, `on_gate_chip`,
`on_chat_retry_model`, `on_gate_back`, `on_gate_connect`, `on_gate_continue`,
`_start_retry_turn`, `on_chat_retry`, `on_ff_info`, `_breadth_summary`,
`on_breadth_submit`, `on_breadth_try_again`, `on_breadth_change`,
`_EMPTY_TURN_NOTICE`, `on_stream_poll`, `_switch_agent`, `on_agent_pill_click`,
`on_project_mode_choice`, `on_rescan_project`, `on_review_to_brainstormer`,
`on_brainstormer_to_designer`, `on_brainstormer_to_agentifier`,
`on_agentifier_to_designer`, `on_stack_to_phaser`, `on_phaser_to_deployer`,
`on_deployer_new_project`, and its own `from spec4.app_constants import
FF_PROMPT  # noqa: E402` (kept mid-file with its comment, so `E402` still
applies and the `noqa` stays live rather than becoming decorative). The "Agent
select" banner — two D-LR8 comment blocks about removed callbacks, no code —
moved here intact, ahead of "Chat — initial turn".

**`_artifacts.py`** — the Artifact View and everything reaching it (20, 12
callbacks + the 6 `_register_open_artifact` closures): `_ARTIFACTS_PHASE`,
`on_round_tree`, `select_artifact`, `on_round_tree_line`, `on_artifact_round`,
`session_round`, `on_artifact_pane`, `on_artifact_download`, `on_round_cost`,
`_send_json`, `_build_phases_zip`, `dl_vision`, `dl_stack`, `dl_code_review`,
`dl_features`, `dl_phases`, `dl_deployment`, `_open_target`,
`_register_open_artifact`, `OPEN_ARTIFACT_CALLBACKS`.

**Stayed in `__init__.py`** (13, 9 callbacks) — the app shell: the status bar
that is on every screen (`on_status_bar`, `on_status_bar_dir`,
`on_status_bar_setup`), the URL router behind it (`_cannot_open`,
`_resolve_root`, `on_browser_navigate`, `_no_change`, `_needs_restoring`), and
the directory picker they both lead to (`on_dir_select`, `on_dir_up`,
`on_dir_path_enter`, `on_subdir_click`, `on_create_folder`). None belongs to a
single agent or a single screen, which is the line the split was drawn on.

**Two placements §15.3 did not spell out.** `dl_deployment` is in `_artifacts`
with the other five `dl_*` rather than under the "Deployer navigation" banner it
used to sit beside: §15.3 assigns downloads to `_artifacts`, it is a download,
and six identical handlers are one concern. `_gate_agent` is in `_shared` rather
than `_chat`, for the dependency reason above.

**Dropped from the façade: 46 imported names, 0 definitions.** They are names
the old module imported for code that moved, and each now lives on the module
that uses it — `dcc`, `dmc`, `html`, `io`, `json`, `zipfile`, `os`, `datetime`,
`timezone`, `streaming`, `providers`, `websearch`, `GATE_IDS`, `SETUP_IDS`,
`provider_key_hint`, `_gate_is_open`, `_get_agent_gen`, `_persist_artifacts`,
`_reset_for_new_project`, `_validate_agent_preconditions`, `close_selection`,
`pool_from_dicts`, the eleven `_artifact_view` ids and helpers, the five
`_round_tree` names, `round_cost_lines`, `ARTIFACTS_PATH`, `CHAT_ARTIFACTS`,
`OPEN_BTN_PREFIX`, `open_button_id`, and the three `app_constants` values only
`_chat` reads. 4c set the precedent for dropping a moved import from the façade,
4e for dropping two, 4f for dropping twenty-two. **21 imported names are kept**,
including `project_manager` (`tests/test_root_routing.py:350` asserts
`cb.project_manager.directory_opens is directory_opens`) and `ctx` (two shell
callbacks still read it). Five of the 46 were reached by name from outside —
`streaming`, `providers`, `_get_agent_gen`, `_persist_artifacts` and `dcc` — and
those, plus `ctx` which was *not* dropped, are the whole of the test edit (§22.5).

`FF_PROMPT` is re-exported from `spec4.app_constants` on the façade rather than
from `_chat`, which is the route the pre-split module used. Taking it off `_chat`
would need an explicit `as`-alias re-export there — `[tool.mypy] strict` implies
`no_implicit_reexport` — and the constant is `app_constants`' either way;
`cb.FF_PROMPT is app_constants.FF_PROMPT` is asserted below.

### 22.3 Rule 4, and the `designer.py` edit §15.2 scheduled

`callbacks/designer.py:14` is now

```python
from spec4.callbacks._shared import _open_pick_fields
```

which retires the one `spec4.callbacks.designer -> spec4.callbacks` edge §15.2
named, and it is the **only** change to `designer.py`. §15.2's rule 4 stops being
vacuous here: four modules now match `spec4.callbacks._*`
(`_artifacts`, `_chat`, `_setup`, `_shared`) and none of them has an edge to the
`spec4.callbacks` package — sibling imports are spelled
`from spec4.callbacks._shared import …`, which §15.1's walk resolves to
`spec4.callbacks._shared` and not to its parent. The rule now enforces what it
was written for rather than passing on an empty set.

`tests/test_import_layering.py` passes **unedited** (7 tests). 4h's scheduled
tightening — widening `_CALLBACKS_PRIVATE` from `spec4.callbacks._` to
`spec4.callbacks.` once `designer` is a package — is still 4h's to make, and is
still one underscore.

Rebuilding the edge set: the four new modules add no cycle. `_shared` imports
only `llm_selection`; `_setup` imports `llm_selection`, `providers`, `websearch`,
`layouts._setup`; `_chat` imports `_shared`, `llm_selection`, `providers`,
`streaming`, `session`, `app_constants`, `layouts._llm_gate`, `layouts._setup`,
`agentifier.panel_closure` (plus the function-body
`agentifier.agentifier` import `on_breadth_try_again` carries); `_artifacts`
imports `project_manager`, `session`, `app_constants` and four `layouts` modules.
Every edge points away from `spec4.callbacks`.

### 22.4 Verification beyond the gate

- **Byte-for-byte.** All 21 moved blocks were compared as raw text against the
  `HEAD` blob at their original line ranges, **after** `ruff format` ran: 2363 of
  the old file's 2460 lines matched exactly. The 97 not in a moved block are the
  62-line import header the five new modules replace, and blank separators; the
  same check confirms **no non-blank line from 63 onwards was left behind**.
  The formatter reported "1 file reformatted, 5 files left unchanged"; the one
  file is the façade, and only its own new import blocks moved.
- **Statement counts add up.** `coverage`'s own parser on the `HEAD` blob: 681
  statements. The five files now: 113 + 21 + 90 + 345 + 140 = **709**, +28. The
  suite-wide total moved 11825 → 11853, also +28, so **no other module's
  statement count changed** and the +28 is entirely the façade's imports and
  `__all__`.
- **Coverage attribution, not coverage loss.** The five files together are
  709 stmts / 157 miss / 78%, against 681 / 157 for the single pre-split file —
  the same 157 missed statements, redistributed. Suite-wide misses unchanged at
  **893**, so no per-module floor moved.
- **Attribute surface: 83 of 83 resolve.** Every one of the old module's 82
  top-level definitions plus `FF_PROMPT` resolves on `spec4.callbacks`, checked
  by importing it and `hasattr`-ing every name the old AST defined;
  `set(__all__) == ` that set exactly. `cb.FF_PROMPT is app_constants.FF_PROMPT`.
  The 46 dropped imports were grepped across `src/`, `tests/`, `evals/` and
  `scripts/` as `spec4.callbacks.<name>`, `from spec4.callbacks import <name>`
  and `cb.<name>` — **zero** hits after the §22.5 edits.
- **Registration, counted per stage.** `_shared` + the package: **66**;
  `designer`: 24; `app`: 2; **total 92**. Per module: shell 9, `_setup` 10,
  `_chat` 29, `_artifacts` 12 + the 6 `_register_open_artifact` closures = 18.
  9 + 10 + 29 + 18 = 66, so every callback registers exactly once and none twice.
- **§15.5 invariants.** `dash._callback.GLOBAL_CALLBACK_MAP` holds **92** after a
  fresh `spec4.app` import. `tests/test_streaming_characterization.py` and
  `tests/test_layout_contract.py` were **not** edited — the first reaches only
  `spec4.callbacks.designer`, the second reaches `callbacks` not at all — and
  they pass unmodified alongside `tests/test_callback_co_presence.py` and
  `tests/test_app_import_smoke.py`: 142 tests. `test_callback_co_presence.py`
  is indifferent to the split by construction: `GLOBAL_CALLBACK_MAP` is keyed by
  output string, not by defining module.

### 22.5 The forced edits outside `src/`

**§15 did not anticipate this one, and §15.4's decision-2 reasoning does not
carry over.** 4a was safe because zero `patch("spec4.agents._utils.…")` string
targets existed. For `callbacks` there are 71, and three kinds of them break when
a callback changes module, because `patch` rebinds a name in *one* module's
namespace and a moved function reads its own:

| Target | Sites | Failure if left | Now |
|---|---:|---|---|
| `spec4.callbacks.streaming.*` | 37 | loud (`AttributeError`) | `spec4.callbacks._chat.streaming.*` |
| `spec4.callbacks._get_agent_gen` | 14 | loud | `spec4.callbacks._chat._get_agent_gen` |
| `spec4.callbacks._persist_artifacts` | 8 | loud | `spec4.callbacks._chat._persist_artifacts` |
| `spec4.callbacks.providers.*` | 3 | loud | `spec4.callbacks._setup.providers.*` |
| `spec4.callbacks.ctx` (string) | 9 | **silent** | `._chat.ctx` (4) / `._artifacts.ctx` (5) |
| `setattr(cb, "ctx", …)` on the package | 3 | **silent** | 2 → `_chat`; 1 was already correct |
| the `artifact_view_callbacks` module alias | 1 line, 6 uses | mixed | `import spec4.callbacks._artifacts as …` |

`ctx` is the dangerous one and the reason each edited file was run on its own
before the suite: it stays bound on the façade (two shell callbacks read it), so
those patches would have kept succeeding and silently stopped taking effect.
`patch("spec4.callbacks.streaming.start")` and its kind resolve to the
`spec4.streaming` *module object* and patch it process-wide, so pointing them at
any importer works; they are aimed at the module that owns the callback under
test.

Thirteen files, **85 insertions / 72 deletions** — the extra 13 are `ruff format`
re-wrapping five lines the longer targets pushed past 88 columns. No assertion
moved, no test was added or removed, no fixture changed. `tests/test_project_mode.py`
is the file the first grep missed: it patches through a `from spec4 import
callbacks as cb` alias rather than a dotted string, and it is why the suite is
run, not just reasoned about.

Checked and **not** forced: `pyproject.toml` (ruff selects only `E,F`;
`callbacks/` has no per-file-ignore to widen and no new module needs one, and
`RUF100` is off so the `FF_PROMPT` `noqa` is never flagged either way),
`README.md:239` (names `callbacks/` as a directory, not its modules),
`tests/README.md` (its `spec4/callbacks.py` row is stale from before the package
existed — Phase 7's, flagged in §0), and `tests/test_setup_wizard_register.py` /
`tests/test_agent_llm_selection.py`, both of which parse source with
`rglob("*.py")` over a directory and so read the new modules without a change.
No test reads `callbacks/__init__.py` off disk.

### 22.6 Deferred / not acted on

- **4g2 — split `_chat.py` into `_gate.py` and `_nav.py`.** Added to §15.3's
  table by Robert during this run. At 1182 lines `_chat.py` is the largest of the
  four new modules by more than double (only `designer.py`, 4h's subject, is
  bigger in the package), and two blocks come out of it cleanly: the per-agent
  model gate (lines 177-537, one flow with its own `agent_llm_draft` key and its
  own surface) and the navigation buttons (957-1182, the agent pills plus the
  inter-agent Continues and the Deployer pair). Its own run, after this one.
  `_open_pick_fields` and `_gate_agent` are already in `_shared`, so the gate
  comes out without a new cross-module private import.
- **`vulture_whitelist.py`'s `# src/spec4/callbacks/__init__.py` section comment
  is now imprecise** — the 60 names under it are unchanged and still whitelisted
  (they are bare names, and no name moved spelling), but 51 of them now live in
  the four siblings and 9 stayed. A comment-only edit, and it belongs with Phase 7's
  regeneration or 4j. Logged, not fixed.
- **§17.5's `_AGENT_SIDE` gap is still open** — 4b's four flat siblings remain
  outside the layering contract's agent-side prefix set. Still a four-string edit
  to `tests/test_import_layering.py` for **4j**.
- **§21.6's fifth layering rule is still blocked** on `layouts/designer.py:11`.
  4g adds nothing to it and removes nothing from it; the `callbacks` half of the
  same idea is rule 4, which is now live.
- **Import-linter, reconsidered as §6.3 and §15.5 require at this point, is still
  not warranted.** The internal layering `callbacks/` gained is one rule with one
  direction — siblings may not import the package — and it is already asserted by
  the `ast` test, non-vacuously, with the offending `importer -> imported` pairs
  named on failure. A declarative contract would restate it, add a dependency and
  a gate command, and catch nothing the test does not.
- **4j owns the importer cleanup for this façade.** There are no aliases to
  retire. The 83 re-exports are all still read from outside except the internals
  `_cannot_open`, `_no_change`, `_needs_restoring`, `_send_json`,
  `_build_phases_zip`, `_open_target`, `_register_open_artifact`,
  `_gate_answered`, `_breadth_summary`, `_switch_agent`, `_start_retry_turn`,
  `_EMPTY_TURN_NOTICE`, `_DEV_MODE`, `_ARTIFACTS_PHASE` and
  `_prefs_keep_working_dir`, whose `__all__` entries exist only to preserve the
  pre-split attribute surface and can be trimmed once 4j confirms it. Logged as
  Phase 2-style candidates, not deleted.
- **`on_stream_poll` (132 lines), `on_gate_continue` (81) and
  `on_breadth_try_again` (81) are the three large functions left in `_chat.py`.**
  Phase 5 findings, logged not fixed — 4g moved them, it did not shrink them.
  Nothing in the other three modules exceeds 63 lines.
- Nothing new for *Bugs found (not fixed)*.

### 22.7 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Layering | `uv run pytest tests/test_import_layering.py -q` | `7 passed` (exit 0) |
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `211 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 84 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 161.94s (0:02:41)` (exit 0) |
| Coverage | same run | `TOTAL 11853 stmts, 893 miss, 92%` |

Test count is unchanged at 4256 — 4g adds no test and removes none; every edited
line is inside an existing test. `211 files already formatted` is §21.7's 207
plus four new modules; `84 source files` is mypy's 80 by the same arithmetic.
Statements rose 11825 → 11853 (+28, the façade's imports and `__all__`) and
misses held at 893, so no per-module floor moved.

## 23. Phase 4h — `callbacks/designer.py` split into the package `callbacks/designer/`

Recorded 2026-09-09 on branch `look-rework`. One file under `src/` deleted and
four created; **four test files edited — one patch target in three of them, and
the scheduled one-constant widening in `tests/test_import_layering.py`.**
`pyproject.toml` is untouched, `src/spec4/app.py` is untouched, and no assertion,
fixture or callback import moved in any test. Nothing was written under
`.spec4/`, `.venv/` or `.git/`, and no git command was run beyond
`git show HEAD:…`, `git diff`, `git status` and `git ls-files`, all read-only.

Like 4c–4e and unlike 4f/4g this is a **package conversion**, which §15.3 chose
for the reason 4c did: the import path `spec4.callbacks.designer` is the string
`app.py:75` and eight test modules already use, and it survives unchanged.

### 23.1 Line counts

| File | Lines | Was |
|---|---:|---:|
| `callbacks/designer/__init__.py` (façade) | 364 | 1399 |
| `callbacks/designer/_mock_gen.py` | 422 | — |
| `callbacks/designer/_wizard.py` | 412 | — |
| `callbacks/designer/_refine.py` | 398 | — |
| **total** | **1596** | **1399** |

The +197 is compatibility layer and prose: the façade's 40-name `__all__` and its
three sibling import blocks, four module docstrings, and the import header each
new module needs. No definition grew or shrank by a line — every one moved
byte-for-byte (§23.4) — and **no function body changed** apart from the one
rename §23.2 describes.

### 23.2 The names moved to each

All 38 top-level definitions are accounted for: 36 moved, 2 stayed. One name
changed spelling, `_MOCK_BUFFERS` → `MOCK_BUFFERS`, and only inside `_mock_gen`
(see below); nothing else was renamed, dropped or added.

**`_mock_gen.py`** — the generation core (12 names, **0 callbacks**): `logger`,
`_DEV_MODE`, `MOCK_BUFFERS`, `_MAX_HTML_BYTES`, `_DEFAULT_EXPECTED_CHARS`,
`_MAX_DELIVERY_TICKS`, `_llm_params`, `_planning_ctx`, `_extract_html`,
`_persist_manifest`, `_expected_stream_chars`, `_start_gen` (with its `_run`
worker). `_llm_params` and `_planning_ctx` are here rather than beside either
set of callbacks because both `_wizard` and `_refine` call them: they are a
draw's *inputs*, and putting them in either module would make one leaf import
the other. `logger` keeps the `logging.getLogger(__name__)` idiom, so its name
becomes `spec4.callbacks.designer._mock_gen` — a child of the old logger, so any
handler or level set on `spec4.callbacks.designer` still applies to it, and
nothing in `src/`, `tests/` or the docs names either string.

**`_wizard.py`** — the wizard's own steps (14 names, 13 callbacks):
`on_designer_add_gui`, `_skip_to_stack_advisor`, `on_designer_skip_1`,
`on_designer_skip_2`, `on_designer_step2_choice`, `on_designer_carry_forward`,
`on_designer_preferences_next`, `on_designer_screenshot_upload`,
`on_designer_screenshot_delete`, `on_designer_generate_mock`,
`on_designer_approve`, `on_designer_continue_stack`, `on_designer_step_back`,
`on_designer_start_over`. Two of them start a draw — the "Modify existing"
capture and Generate — and both go through `_mock_gen._start_gen`.

**`_refine.py`** — everything downstream of a finished or failed draw (10 names,
9 callbacks): `on_designer_refine`, `on_designer_refine_cancel`,
`on_designer_refine_upload`, `on_designer_refine_image_delete`,
`on_designer_regenerate`, `on_designer_revise_stale`, `on_designer_retry_model`,
`_rerun_failed_draw`, `on_designer_retry`, `on_designer_auto_retry`. It carries
the one `spec4.callbacks._shared` edge 4g created (`_open_pick_fields`, read by
`on_designer_retry_model`).

**Stayed in `__init__.py`** (2 names, 2 callbacks) — `render_designer_step` and
`on_mock_stream_poll`: the two callbacks that drive the wizard *shell* rather
than one screen's buttons. Both are store-driven rather than button-driven
(`designer-session-store` / `mock-stream-buffer` / `mock-stream-interval`), one
paints whichever step the store names and the other feeds it while a draw runs
and delivers the finished mock in-band. §15.3 did not place
`render_designer_step`; it renders steps 1–7, so it is not "steps 1–4", and
keeping it here also leaves `tests/test_agent_llm_selection.py` — which patches
`spec4.callbacks.designer.ctx` around it — untouched.

**The one rename.** §15.3 requires `callbacks.designer._MOCK_BUFFERS` to be the
same dict object as `_mock_gen.MOCK_BUFFERS`. `_mock_gen` therefore defines it
public (it is that module's cross-module surface), which renames its 5
references inside `_mock_gen` — the annotated assignment, three uses in
`_start_gen`/`_run`, and one mention in a comment. The two modules that had it
under the old spelling keep their bodies unchanged by importing it as
`MOCK_BUFFERS as _MOCK_BUFFERS`: the façade (for `on_mock_stream_poll`) and
`_wizard` (for `on_designer_start_over`). One dict, three names;
`designer._MOCK_BUFFERS is designer._mock_gen.MOCK_BUFFERS` is asserted in
§23.4.

**Dropped from the façade: 21 imported names, 0 definitions.** `ALL`,
`DesignerSession`, `_default_designer_session`, `_open_pick_fields`,
`build_revision_note`, `collect_ui_source_files`, `enrich_manifest`,
`extract_manifest`, `generate_mock_streaming`, `llm`, `logging`, `os`,
`pathlib`, `re`, `revision_delta`, `save_manifest`, `save_mock`, `save_session`,
`uuid`, `validate_manifest`, `websearch` — each now lives on the module that
uses it, 4g §22.2's precedent. **21 imported names are kept**, including two
that nothing in the façade uses: `project_manager` and `threading`, which stay
bound because tests reach them *through this module* to patch them
(`monkeypatch.setattr(dmod.project_manager, …)` ×6, `dmod.threading` ×1, and
`patch("spec4.callbacks.designer.project_manager.load_prior_mock")`). Patching
an attribute *on a module object* takes effect for every importer, so those
seven sites keep working from here and needed no edit; they are in `__all__`,
which is what keeps `F401` and `no_implicit_reexport` happy about them.

`generate_mock_streaming` and `revision_delta` were deliberately **not** kept
for the same convenience: they are functions, so a patch aimed at the façade
would rebind only the façade's name and silently stop taking effect. Dropped,
the same patch fails loudly with `AttributeError` — which is exactly how two of
the sites in §23.5 were found.

### 23.3 Rule 4, widened, and the resulting import graph

`tests/test_import_layering.py`'s `_CALLBACKS_PRIVATE` went from
`"spec4.callbacks._"` to `"spec4.callbacks."` — the one-underscore tightening
§15.2 scheduled for 4h — plus the comment above it, which described the rule as
not yet biting and named this widening as still to come. That is the whole edit
to the file; the rule body, the guards and the other six tests are unchanged and
pass.

The rule now matches **8** modules instead of 4: `callbacks/_artifacts`,
`_chat`, `_setup`, `_shared` and, new, `designer`, `designer._mock_gen`,
`designer._wizard`, `designer._refine`. None has an edge to the
`spec4.callbacks` package:

- `designer` → `designer._mock_gen`, `designer._wizard`, `designer._refine`
- `designer._wizard` → `designer._mock_gen`
- `designer._refine` → `designer._mock_gen`, `callbacks._shared`
- `designer._mock_gen` → nothing under `spec4.callbacks` at all

so the package's internal graph is a two-level tree with no cycle, and the
`layouts` ↔ `layouts._chat` shape §15.2 was written against is not recreated.
Outside `callbacks/`, the four modules import `spec4.llm`, `llm_selection`,
`project_manager`, `websearch`, `agents._manifest`, `agents.designer` and
`layouts.designer` — every edge pointing away from the Dash side's top, so rules
1–3 are untouched (7 tests pass).

### 23.4 Verification beyond the gate

- **Byte-for-byte.** Every non-blank line of the `HEAD` blob was looked for
  verbatim in the four new files, after `ruff format` ran: **1279 of 1285
  matched**. The six that did not are the five `_MOCK_BUFFERS` → `MOCK_BUFFERS`
  lines of §23.2 and one line of the old import header
  (`        _default_designer_session,`, now a single-line import in `_wizard`).
  Nothing else moved by a character. `ruff format` reported "4 files
  reformatted" on the first pass and the diff was **blank lines only** — the
  two-line separators between the blocks the splitter had stripped.
- **Attribute surface: 38 of 38 resolve.** Every one of the old module's 38
  top-level definitions resolves on `spec4.callbacks.designer`, checked by
  importing it and `hasattr`-ing every name the old AST defined;
  `set(__all__)` is exactly that set plus `project_manager` and `threading`.
  `designer._MOCK_BUFFERS is designer._mock_gen.MOCK_BUFFERS`,
  `designer.project_manager is spec4.project_manager`,
  `designer.threading is threading`, `designer.ctx is dash.ctx`. The 21 dropped
  names were grepped across `src/`, `tests/`, `evals/` and `scripts/` as
  `spec4.callbacks.designer.<name>`, `from spec4.callbacks.designer import
  <name>` and `dmod.<name>` — one hit, `revision_delta`, which is in §23.5.
- **Registration, counted per module.** Static `@callback` decorators:
  `__init__` 2, `_mock_gen` 0, `_wizard` 13, `_refine` 9 = **24**, the count
  §22.4 attributes to `designer`. Importing the package registers 24 (90 with
  `spec4.callbacks`'s 66), and `spec4.app` adds its 2.
- **Statement counts add up.** `coverage`'s parser on the `HEAD` blob: 427
  statements. The four files now: 77 + 131 + 125 + 116 = **449**, +22. The
  suite-wide total moved 11853 → 11875, also +22, so **no other module's
  statement count changed** and the +22 is entirely import headers and `__all__`.
- **Coverage attribution, not coverage loss.** The four files together are
  449 stmts / 109 miss, against 427 / 109 for the single pre-split file — the
  same 109 missed statements, redistributed (façade 91%, `_mock_gen` 88%,
  `_refine` 80%, `_wizard` 50%). Suite-wide misses unchanged at **893**, so no
  per-module floor moved.
- **§15.5 invariants.** `dash._callback.GLOBAL_CALLBACK_MAP` holds **92** after a
  fresh `spec4.app` import in a clean interpreter.
  `tests/test_layout_contract.py` was **not** edited;
  `tests/test_streaming_characterization.py` was edited on one line and the
  reason is §23.5. They pass alongside `tests/test_callback_co_presence.py`,
  `tests/test_app_import_smoke.py`, `tests/test_designer*.py`,
  `tests/test_agent_llm_selection.py` and `tests/test_import_layering.py`:
  598 tests.

### 23.5 The forced edits outside `src/`, and the one that breaks §15.5

Same failure mode as 4g §22.5, one directory down: `patch` rebinds a name in
*one* module's namespace, and a moved function reads its own. A re-export shares
a **value**, not a **binding** — which is why the `_MOCK_BUFFERS` dict survives
the move untouched by 20 test sites while a patched *function* does not survive
it at all.

| Target | Sites | Failure if left | Now |
|---|---:|---|---|
| `setattr/patch.object(dmod, "_start_gen")` | 9 | loud (the real draw runs, `captured` stays empty) | `dmod._wizard` (1) / `dmod._refine` (8) |
| `setattr(dmod, "generate_mock_streaming")` | 5 | loud (`AttributeError`) | `dmod._mock_gen` |
| `setattr/patch.object(dmod, "ctx")` | 4 | loud (`MissingCallbackContextException`) | `dmod._wizard` (3) / `dmod._refine` (1) |
| `patch("spec4.callbacks.designer.revision_delta")` | 1 | loud (`AttributeError`) | `…designer._wizard.revision_delta` |

That is 18 sites in `tests/test_designer.py` and 1 in
`tests/test_designer_fullscreen.py` — **24 insertions / 18 deletions**, the
extra 6 being `ruff format` re-wrapping five calls the longer targets pushed
past 88 columns. Every other designer patch site kept working and was left
alone: the seven `dmod.project_manager` / `dmod.threading` ones (module objects,
§23.2), and the four `ctx` ones aimed at `render_designer_step` and
`on_mock_stream_poll`, which stayed in the façade.

**The §15.5 breach: one line of `tests/test_streaming_characterization.py`.**
Its `TestMockBuffers._start` does
`monkeypatch.setattr(dmod, "generate_mock_streaming", …)` and then calls
`dmod._start_gen(...)`. Once `_start_gen`'s worker lives in `_mock_gen` there is
no arrangement of re-exports that keeps that patch effective — a function
re-export shares the value, and the worker reads its own module's globals — so
the real LLM call would run and the test would time out waiting for a chunk.
The alternatives were to leave `_start_gen` in the façade (which puts
`_wizard` and `_refine` back to importing the package that imports them: exactly
the cycle rule 4 exists to prevent, and it was just widened to cover them), or
not to split at all. Robert was asked and chose the third: retarget that one
`monkeypatch.setattr` to `dmod._mock_gen` — **1 insertion / 1 deletion**, no
other line of the file touched. The state-container assertions the file exists
for — `_MOCK_BUFFERS` contents at every transition, `_DEFAULT_EXPECTED_CHARS`,
`_MAX_DELIVERY_TICKS`, the poll's return shapes — are unchanged and still run
through `spec4.callbacks.designer`, because the dict *is* the same object.

**Grep was not enough to find the sites.** Three of the 20 are multi-line calls
(`monkeypatch.setattr(\n    dmod,\n    "generate_mock_streaming",` and two
`patch.object(\n    dmod, "_start_gen", return_value=…`) that a line-oriented
grep for `dmod, "` cannot see; they were found by the suite failing and then, to
be sure nothing silent was left, by an `ast` walk over all of `tests/` for every
`setattr` / `patch` / `patch.object` call whose first argument mentions
`designer`. That walk is what the "sites" column above counts.

Checked and **not** forced: `pyproject.toml` (ruff selects only `E,F`;
`callbacks/` has no per-file-ignore to widen, and unlike 4c no new module needs
one — nothing here is a frozen prompt), `src/spec4/app.py` (rule 5 / D-LR1:
`import spec4.callbacks.designer` resolves to the package with the import
unchanged), `src/spec4/callbacks/__init__.py` (it never imported `designer`),
`tests/test_agent_llm_selection.py` and `tests/test_designer_wizard_register.py`
(the first patches `spec4.callbacks.designer.ctx` around `render_designer_step`,
which stayed; the second parses source with `rglob("*.py")` over a directory and
so reads the new files as they are), `tests/test_designer.py:1870`'s
`from spec4.callbacks.designer import _extract_html` and every other
`from spec4.callbacks.designer import <callback>` (re-exported), `README.md` and
`CLAUDE.md` (neither names the file).

### 23.6 Deferred / not acted on

- **`vulture_whitelist.py:86`'s `# src/spec4/callbacks/designer.py` section
  comment now names a file that does not exist.** The 24 names under it are bare
  and still correct — no name moved spelling — but they live in three modules
  now. A comment-only edit, and it belongs with Phase 7's regeneration or 4j,
  exactly as 4g logged the same staleness for `callbacks/__init__.py`.
- **4g2 — split `_chat.py` into `_gate.py` and `_nav.py`** — added to §15.3 by
  Robert during 4g, still pending. 4h neither touched it nor changed its shape;
  at 345 statements `callbacks/_chat.py` is now the largest module in
  `callbacks/` by some distance.
- **Phase 5 findings, logged not fixed.** `_start_gen` (197 lines, with its
  `_run` worker) and `on_mock_stream_poll` (150) are the two large functions the
  split moved without shrinking; nothing else in the package exceeds 66 lines
  (`on_designer_regenerate`).
  `on_mock_stream_poll`'s three-part docstring is load-bearing behaviour
  documentation and moved with it intact.
- **The façade's re-exports are 4j's to trim.** Of the 40 `__all__` entries, the
  internals `_skip_to_stack_advisor`, `_rerun_failed_draw`, `_persist_manifest`,
  `_planning_ctx`, `_llm_params`, `_MAX_HTML_BYTES`, `logger`, `_DEV_MODE` and
  `_extract_html` exist to preserve the pre-split attribute surface;
  `_extract_html`, `_persist_manifest`, `_start_gen`, `_expected_stream_chars`,
  `_MOCK_BUFFERS`, `_DEFAULT_EXPECTED_CHARS` and `_MAX_DELIVERY_TICKS` are read
  from outside today, the rest are candidates once 4j confirms it. Logged as
  Phase 2-style candidates, not deleted.
- **§17.5's `_AGENT_SIDE` gap and §21.6's blocked fifth rule are unchanged.**
  4h adds nothing to either; both remain 4j's.
- Nothing new for *Bugs found (not fixed)*.

### 23.7 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Layering | `uv run pytest tests/test_import_layering.py -q` | `7 passed` (exit 0) |
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `214 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 87 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 172.05s (0:02:52)` (exit 0) |
| Coverage | same run | `TOTAL 11875 stmts, 893 miss, 92%` |

Test count is unchanged at 4256 — 4h adds no test and removes none; every edited
line is a patch target inside an existing test. `214 files already formatted` is
§22.7's 211 plus three net new files (one deleted, four created); `87 source
files` is mypy's 84 by the same arithmetic. Statements rose 11853 → 11875 (+22,
the four import headers and `__all__`) and misses held at **893**, so no
per-module floor moved.

## 24. Phase 4i — `agentifier/agentifier.py` split into three siblings

Recorded 2026-09-09 on branch `look-rework`. Four files under
`src/spec4/agentifier/` changed or added; **no file outside that directory was
touched** — no test, no eval, no script, no `pyproject.toml`, no `README.md`,
no `CLAUDE.md`. Nothing was written under `.spec4/`, `.venv/` or `.git/`, and no
git command was run beyond `git status` and `git diff --stat`, both read-only.
`agentifier.py` stays a module (not a package): the three siblings sit beside it,
as 4a and 4f did, so `spec4.agentifier.agentifier` is unchanged for every
importer. The last of the Phase 4 splits.

### 24.1 Line counts of the four resulting files

| File | Lines | Was |
|---|---:|---:|
| `agentifier/agentifier.py` (façade + phase drivers) | 2538 | 3565 |
| `agentifier/_seed.py` | 509 | — |
| `agentifier/_render.py` | 577 | — |
| `agentifier/_ff_review.py` | 212 | — |
| **total** | **3836** | **3565** |

The façade is still the largest module in the repo — that is the outcome §15.3
predicted ("the largest *and* least separable … only the leaf-pure edges come
out; the phase drivers stay"), and `_run_catalog_phase` alone is 654 lines. See
§24.6.

### 24.2 The criterion, and the names moved to each

A name moved only if **both** held:

1. **Leaf** — its whole dependency set is closed under the destination module
   plus sibling packages and stdlib. Nothing it calls stays behind, so the new
   module never imports `agentifier` and no cycle is possible. Checked with an
   `ast` walk over every module-global each candidate references: **zero**
   back-edges, and exactly one cross-module edge (`_ff_review` → `_render`, two
   names).
2. **Not a patch trap** — no test rebinds the name at
   `spec4.agentifier.agentifier.<name>` *from a call site that also moves*. A
   re-export shares a value, not a binding, so a moved function reads its own
   module's globals (the 4g §22.5 / 4h §23.5 lesson).

**`_seed.py`** — §15.3's "sub-agent call wrappers, seed message,
candidate/analysis (de)serialisation, registry" (17 names). Nothing here yields
chat text or writes a session key.

| Name | Why leaf-pure |
|---|---|
| `_build_registry`, `_registry` | Constructs from the seven sub-agent classes only. §14.5's category (a): built once at import, read-only after. |
| `_iter_async_gen` | asyncio/queue/threading only — the async→sync bridge for `_registry.stream`, so it moves with the registry it exists to drive. |
| `_call_scout`, `_call_linker`, `_call_composer`, `_call_prioritizer`, `_call_tier_analyst` | Build an `*Input` from their arguments, `asyncio.run(_registry.run(...))`, return the output. They dispatch to an LLM — which is why §15.3 names them their own group — but read and write nothing outside their arguments. |
| `_vision_purpose`, `_vision_mvp_feature_names` | Shape-guarded reads of a vision dict → `str` / `list[str]`. Pure; used only by the wrappers above. |
| `_graph_placement_lines`, `_build_seed_message` | Arguments → one string. |
| `_candidates_to_dicts`, `_analyses_to_dicts`, `_candidates_from_dicts`, `_candidates_from_session`, `_analyses_from_session` | Pure list comprehensions. The two `_from_session` ones *read* two session keys and write none. |

**`_render.py`** — §15.3's "every `_format_*`, `_build_ai_features`, priority
parsing, revision snapshot" (17 names). Every one derives its result from its
arguments: no session write, no yield, no I/O.

| Name | Why leaf-pure |
|---|---|
| `_format_composition_summary` | `list[Composition]` → Markdown. |
| `_CATALOG_SPEC_PROMPT`, `_format_catalog_as_text` | Catalog dict → Markdown table. Golden-pinned (§12.1). |
| `_format_spec_as_text` | Entry + spec → Markdown. Golden-pinned. |
| `_build_ai_features` | Catalog + specs + candidates → the feature list. Deps `slug` and `build_grounding`, both siblings. |
| `_FEATURES_COMPLETE_TRANSITION`, `_format_ai_features_complete` | ai_features dict → summary table. |
| `_format_cross_cutting_topic` | Topic + analysis → Markdown. Dep `SKIPPABLE_TOPICS` (sibling). |
| `_VALID_PRIORITIES`, `_PRIORITY_EDIT_RE`, `PriorityEdits`, `_parse_priority_edits` | The deterministic priority-edit reader — no LLM turn. |
| `_format_priority_table`, `_format_priority_repairs` | Feature list / three dicts → the table, the repair notes. |
| `_revision_delta`, `_merge_revision_snapshot`, `_removed_feature_heads_up` | Vision/feature dicts in, a new list or a string out; `_merge_revision_snapshot` copies rather than mutating. |

**`_ff_review.py`** — §15.3's "both fast-forward review halves", as far as the
edges reach (7 names).

| Name | Why leaf-pure |
|---|---|
| `_cc_ff_review_prompt`, `_spec_ff_review_prompt` | `list[str]` → prompt string. Pure. |
| `_FF_REVISION_RE`, `_route_ff_revision_lines` | The `name: instruction` router shared by both halves; arguments in, 4-tuple out. Pure. |
| `_present_cc_ff_review` | Leaf: only outward dep is `_format_cross_cutting_topic` (`_render`) plus its own prompt. |
| `_present_spec_ff_review` | Leaf: only outward dep is `_format_spec_as_text` (`_render`) plus its own prompt. |
| `_ff_sweep_cross_cutting` | Leaf: its only dep is `_present_cc_ff_review`, same module. |

The last three record their outcome on the `session` they are handed and yield
the display text, so they are **leaf but not side-effect-free** — the one place
this split reads "leaf" as an import-graph property rather than as purity.
Robert was asked and chose that reading; the alternative left `_ff_review.py` as
three prompt strings and a regex, which is not "both review halves". Moving them
is safe on 4h's evidence: their dependency set is closed, no test patches or
imports them by name, and their only callers all stay in the façade.

### 24.3 What stayed, and why

- **Required by the brief** — `ORCHESTRATOR_SYSTEM_PROMPT`, `_run_catalog_phase`,
  `_run_spec_phase`, `_run_cross_cutting_phase`, `_run_priority_phase`, `run`,
  `reset_agentifier_flow` (with `_RESTART_DEFAULTS` / `_RESTART_POP`).
- **A back-edge that would be a cycle** — `_handle_cc_ff_review`
  (→ `_begin_priority_phase`, `_extract_cross_cutting_analysis`,
  `_is_spec_confirmed`, `_is_skip`), `_handle_spec_ff_review` (→ `_finalize_specs`,
  `_draft_spec`) and `_ff_sweep_specs` (→ `_draft_spec`). Each is independently
  pinned by a string patch in `tests/agentifier/test_ff_sweep.py`:
  `_finalize_specs` (:157) and `_begin_priority_phase` (:300) are rebound on
  `spec4.agentifier.agentifier`, so a moved handler would silently call the real
  one. That is what made these three the boundary of the FF split, not a taste
  call.
- **Not leaf-pure** — `_begin_priority_phase`, `_finalize_specs`, `_draft_spec`,
  `_draft_and_show_spec`, `_complete_agentifier`, `_handle_reentry`,
  `_append_assistant`; `_discovery_guidance` and `_feature_specs_for_session`
  (disk); `_dump_subagent_failure` (disk, and the sole reader of the
  `_DEV_MODE` that test_ff_sweep.py:454/472 patches); `_session_counter` (writes
  `session["_stream_received_chars"]`); `_log_composition` (also reads
  `_DEV_MODE`, prints).
- **Placed in no §15.3 bucket**, so Rule 7 leaves them — `_APPROACHES_OVERVIEW`,
  `_extract_catalog_json`, `_extract_cross_cutting_analysis` (also 12 string-patch
  sites), `_is_spec_confirmed`, `_is_skip`, `_expand_infrastructure`,
  `_linked_features_for_entry`, `_existing_workflow_for_entry`,
  `_breadth_candidates`, `_reselection_pool_from_features`, `_DEV_MODE`, `_log`.

**The patch surface survived intact, with no test edit.** `_call_scout` (30
sites), `_call_tier_analyst` (21), `_call_linker` (4), `_call_composer` (1) and
`_call_prioritizer` (1) are string-patched on `spec4.agentifier.agentifier`, but
every call site — `_run_catalog_phase`, `_begin_priority_phase` — stayed in the
façade and resolves through the façade's globals, which the patch rebinds. The 16
`patch("spec4.agentifier.agentifier._registry.stream")` sites patch an attribute
on the *object*, so they survive the move exactly as 4h's `_MOCK_BUFFERS` did:
`agentifier._registry is _seed._registry` (§24.4).
`patch.object(agentifier, "load_patterns")` (test_reselection.py:212) wraps
`_finalize_specs`, which stayed. Both `_DEV_MODE` readers stayed.

### 24.4 The resulting import graph, and the one deviation from Rule 121

```
agentifier ──► _seed        (17 names)
           ├─► _render      (17 names)
           └─► _ff_review   ( 7 names)  ──► _render  (2 names)
```

Two levels, no cycle, no edge back into the façade. Outside the package the three
modules import only `spec4.agentifier.{composer,cross_cutting_analyst,grounding,
linker,pattern_loader,prioritizer,scout,spec_drafter,subagents,tier_analyst}` and
`spec4.agents._utils` — every edge pointing away from the Dash side, so layering
rules 1–3 are untouched and `tests/test_import_layering.py` is unchanged and
passes (7 tests). Its guards only strengthen: the walk sees 3 more modules and
the `spec4.session` → `spec4.agentifier.agentifier` function-body edge is
unaffected.

**No name changed spelling**, including the cross-module private imports
(`_registry`, `_format_spec_as_text`, `_format_cross_cutting_topic`). That
departs from the plan's Rule 121 ("underscore-prefixed names used across files
get promoted to public names") and follows the 4d–4h precedent (§23.4, "no name
moved spelling") instead, for two reasons this sub-phase makes binding: the brief
requires the functions to move byte-for-byte, and
`spec4.agentifier.agentifier._registry` must keep resolving for 16 patch targets.
Renaming is 4j's call, alongside the 4a aliases.

`__all__` on the façade lists all 41 moved names plus `ORCHESTRATOR_SYSTEM_PROMPT`,
`reset_agentifier_flow` and `run`. It is load-bearing, not decorative: `[tool.mypy]
strict` implies `no_implicit_reexport`, and it is what keeps `F401` quiet about
the re-exports. Each new module carries its own `__all__` for the same reason.

### 24.5 How "no logic changes" was verified

- **Byte-for-byte: 3184 of 3191 non-blank lines matched**, after `ruff format`
  ran. Every one of the seven misses is an import-header or banner line, and all
  seven are accounted for:
  - `    Composition,` / `    CrossCuttingAnalyst,` / `    PRIORITIES,` /
    `    slug,` — each is now a *single-line* import in the module that took the
    code, so the parenthesised-list form no longer exists.
  - `from spec4.agentifier.spec_drafter import SpecDrafterAgent, SpecDrafterInput`
    — split, `SpecDrafterAgent` to `_seed` (the registry) and `SpecDrafterInput`
    kept in the façade (`_draft_spec`).
  - `import re  # noqa: E402 — kept here to avoid circular-import confusion at
    module level` — see below.
  - The `# Async → sync streaming bridge` banner initially moved with an ASCII
    arrow; corrected back to the original glyph, which is why it is *not* in the
    final miss list. No function body moved by a character.
  `ruff format` reported "1 file reformatted" on the first pass; the diff was
  blank-line separators only, as in 4a–4h.
- **Both `import re` statements were removed from the façade** — F401 requires
  it, and it is verifiable: `re` was used at exactly four places in the pre-split
  file (`_PRIORITY_EDIT_RE`, `_parse_priority_edits` ×2 → `_render`;
  `_FF_REVISION_RE` → `_ff_review`). That includes the duplicate
  `import re  # noqa: E402` at old line 3354, which was already dead before this
  split — nothing after it used `re`. `asyncio`, `queue`, `threading` and
  `dataclass`/`field` went the same way, and 19 sibling names the moved code took
  with it (`ComposerAgent`, `ComposerInput`, `Composition`, `CrossCuttingAnalyst`,
  `LinkerAgent`, `LinkerInput`, `LinkerOutput`, `PRIORITIES`, `PrioritizerAgent`,
  `PrioritizerInput`, `PrioritizerOutput`, `ScoutAgent`, `ScoutInput`,
  `ScoutOutput`, `SpecDrafterAgent`, `SubAgentRegistry`, `TierAnalystAgent`,
  `TierAnalystInput`, `slug`). **0 definitions were dropped.** Each was grepped
  as `agentifier.<name>` across `src/`, `tests/`, `evals/` and `scripts/`: no hit.
- **Attribute surface: 77 of 77 resolve.** Every top-level name the pre-split AST
  defined resolves on `spec4.agentifier.agentifier`, checked by importing it and
  `hasattr`-ing the lot. `agentifier._registry is _seed._registry`,
  `agentifier.project_manager is spec4.project_manager`,
  `agentifier.llm is spec4.llm`, `agentifier.websearch is spec4.websearch` — all
  True, so the 11 `patch.object(agentifier.project_manager, …)` sites, the one
  `monkeypatch.setattr(agentifier.llm, "stream_turn")` and the two
  `agentifier._registry` sites keep working untouched. `set(__all__)` is a subset
  of `dir()` and contains no name the pre-split module did not define.
- **Statements add up.** `coverage`'s parser on the `HEAD` blob: 1416. The four
  files now: 951 + 153 + 248 + 93 = **1445**, +29 — the three import headers and
  the four `__all__` blocks. Suite-wide 11875 → 11904, also +29, so **no other
  module's statement count changed**.
- **Coverage attribution, not coverage loss.** 128 + 11 + 13 + 1 = **153** missed
  statements across the four files, against 153 for the single pre-split file
  (façade 87%, `_render` 96%, `_seed` 92%, `_ff_review` 99%). Suite-wide misses
  unchanged at **893**, so no per-module floor moved.
- **§15.5 invariants.** `dash._callback.GLOBAL_CALLBACK_MAP` holds **92** after a
  fresh `spec4.app` import in a clean interpreter. `tests/test_layout_contract.py`
  and `tests/test_streaming_characterization.py` were **not** edited — nor was any
  other test file. `tests/agentifier/` (all 28 modules),
  `tests/test_renderer_goldens.py` and `tests/test_stream_status.py` pass together:
  758 tests.

### 24.6 Deferred / not acted on

- **The façade is still 2538 lines and the repo's largest module** — by design
  (§15.3), and now it is nothing but the orchestrator's generator flow. The Phase 5
  targets inside it are `_run_catalog_phase` (654 lines), `_draft_spec` (101),
  `_finalize_specs` (105), `_complete_agentifier` (86), `_handle_reentry` (93) and
  `_run_cross_cutting_phase` (157). Nothing was shrunk here.
- **The duplicate `_DEV_MODE` assignment** (old lines 95 and 1171; the second
  carries a `#:` comment explaining the session-import cycle) is left as it was —
  both readers stayed in the façade, and de-duplicating a module-level constant is
  a Phase 5 edit, not a move. Logged as a Phase 5 finding.
- **The three FF handlers are 4j/Phase 5's problem, if anyone's.**
  `_handle_cc_ff_review` (94 lines), `_handle_spec_ff_review` (79) and
  `_ff_sweep_specs` (38) could only follow `_ff_review.py` if the two
  string-patched transitions (`_finalize_specs`, `_begin_priority_phase`) were
  retargeted in `tests/agentifier/test_ff_sweep.py` — the 4h §23.5 trade, which
  this sub-phase was told not to take. Logged, not done.
- **`__all__` is 4j's to trim.** Of the 44 entries, `_build_registry`,
  `_graph_placement_lines`, `_vision_purpose`, `_vision_mvp_feature_names`,
  `_cc_ff_review_prompt`, `_spec_ff_review_prompt`, `_FF_REVISION_RE`,
  `_PRIORITY_EDIT_RE`, `_VALID_PRIORITIES`, `_CATALOG_SPEC_PROMPT`,
  `_FEATURES_COMPLETE_TRANSITION` and `PriorityEdits` exist only to preserve the
  pre-split attribute surface and have no importer anywhere. Phase 2-style
  candidates, logged not deleted — 4j moves imports, it does not remove
  definitions.
- **`pyproject.toml` was checked and not forced.** The 4c widening
  `"src/spec4/agentifier/**/*.py" = ["E501"]` already covers the three new
  siblings; ruff selects only `E,F`, and none of the new modules holds a frozen
  prompt (`ORCHESTRATOR_SYSTEM_PROMPT` and `_APPROACHES_OVERVIEW` stayed).
- **`vulture_whitelist.py`, `README.md` and `CLAUDE.md` name none of these
  files**, so none needed the comment-staleness fix 4g/4h logged for `callbacks/`.
- **§17.5's `_AGENT_SIDE` gap, §21.6's blocked fifth rule and 4g2** are unchanged;
  4i adds nothing to any of them. 4g2 (splitting `callbacks/_chat.py` into `_gate`
  and `_nav`) and 4j are what remain of Phase 4.
- Nothing new for *Bugs found (not fixed)*.

### 24.7 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Layering | `uv run pytest tests/test_import_layering.py -q` | `7 passed` (exit 0) |
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `217 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 90 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 169.43s (0:02:49)` (exit 0) |
| Coverage | same run | `TOTAL 11904 stmts, 893 miss, 92%` |

Test count is unchanged at 4256 — 4i adds no test, removes none, and edits none.
`217 files already formatted` is §23.7's 214 plus the three new files; `90 source
files` is mypy's 87 by the same arithmetic. Statements rose 11875 → 11904 (+29,
the import headers and `__all__` blocks) and misses held at **893**, so no
per-module floor moved. `.coverage` was restored after the run.

## 25. Phase 4j — importer cleanup: the 4a–4i compatibility layer retired

Recorded 2026-09-09 on branch `look-rework`. 60 files changed (29 under `src/`,
22 under `tests/`, 9 under `evals/`); nothing was added or deleted, no test
assertion changed, `pyproject.toml` is untouched. Nothing was written under
`.spec4/`, `.venv/` or `.git/`, and no git command was run beyond `git show
HEAD:…`, `git diff`, `git status` and one `git checkout --` that reverted a
first, over-broad pass of step 1 (below). **Importer changes are the work of
this sub-phase** — that is the one line of the per-phase template 4j replaces.

### 25.1 The four steps, in the order §15.4 decision 3 set

| # | Step | Scope |
|---:|---|---|
| 1 | Every `from spec4.agents._utils import _x` rewritten to the public name **imported from its owning module** | 46 files: 17 `src/`, 22 `tests/`, 7 `evals/` |
| 2 | The 49 underscore aliases deleted from `_utils.py` | 1 file |
| 3 | Re-exports with no importer outside the owning module removed from all nine façades | 9 files, 133 names |
| 4 | Each façade's docstring updated to name its sub-modules and state what it still re-exports | 9 files |

Step 1's import target, not just the name, moves: `_extract_json_block` becomes
`from spec4.agents._turn_flow import extract_json_block`, not
`from spec4.agents._utils import extract_json_block`. Robert chose that reading
over the name-only one when it was put to him at the start of the run, and it is
what makes step 3 reach `_utils` at all. `evals/` was included for the same
reason: five of its files import underscore aliases, and step 2 would have broken
them at import time. `scripts/` needed no change — it has no `_utils` import.

### 25.2 Line counts of the resulting files

| Façade | Before | After | Δ |
|---|---:|---:|---:|
| `spec4/agents/_utils.py` | 238 | 18 | −220 |
| `spec4/project_manager.py` | 515 | 480 | −35 |
| `spec4/agents/code_scanner/__init__.py` | 422 | 357 | −65 |
| `spec4/agents/stack_advisor/__init__.py` | 321 | 292 | −29 |
| `spec4/agents/phaser/__init__.py` | 579 | 576 | −3 |
| `spec4/layouts/_chat.py` | 260 | 249 | −11 |
| `spec4/callbacks/__init__.py` | 573 | 505 | −68 |
| `spec4/callbacks/designer/__init__.py` | 364 | 331 | −33 |
| `spec4/agentifier/agentifier.py` | 2538 | 2523 | −15 |
| **total (façades)** | **5810** | **5331** | **−479** |
| the other 51 files (import blocks re-grouped) | 23586 | 23604 | +18 |

The +18 is step 1 splitting one `from spec4.agents._utils import (…)` block into
one block per owning module; the −479 is the compatibility layer coming out.

### 25.3 Step 1 — where each name went

The 38 underscore aliases with an importer resolved to four owning modules:

- **`spec4.agents._turn_flow`** — `extract_json_block`, `last_assistant_text`,
  `replay_last_assistant`, `drop_orphan_or_route_to_fresh_start`,
  `drop_orphan_trailing_user`, `maybe_inject_staleness_question`,
  `maybe_inject_resume_summary`, `build_revision_context`.
- **`spec4.agents._reask`** — `abandon_reask`, `artifact_fallback`,
  `artifact_reask_prompt`, `artifact_reask_status`, `reask_for_artifact`,
  `set_status`, `drain_stream`, `stream_counting`, `stream_suppressing_json`,
  `suppressed_as_artifact`.
- **`spec4.agents._feature_context`** — `slug`, `excluded_feature_ids`,
  `TIER_ORDER_FOR_SUMMARY`, `ai_features_for_stack/_phaser/_deployer/_designer`,
  `feature_specs_for_stack/_phaser/_designer`, `feature_relationship_lines`,
  `explicitly_rejected_lines`, `slim_vision_framing`.
- **`spec4.agents._stack_context`** — `render_references`, `render_coding_style`,
  `stack_for_deployer`, `phases_for_deployer`, `nfr_goals_for_deployer`,
  `stack_digest_for_phaser`, `manifest_for_phaser`, `load_design_manifest`,
  `design_manifest_for_stack`.

`tests/test_stale_ai_features.py` was the one importer that took the module
rather than a name (`from spec4.agents import _utils`, then
`_utils._build_revision_context`); it now imports `build_revision_context` from
`_turn_flow` directly. That is a call-site rename, not an assertion change.

**The one name deliberately not renamed.**
`tests/agentifier/test_chars_counter_seed.py:156` does
`patch.object(agentifier, "_stream_suppressing_json", spy)` — a string patch
target on the *importing* module, which §15.4 decision 2 did not anticipate
(it checked only for `patch("spec4.agents._utils.…")`, of which there are still
zero). `agentifier.py` therefore imports it as
`stream_suppressing_json as _stream_suppressing_json`, keeping the attribute
name the test names. It is the only `as` alias 4j introduces, and the façade
docstring says why. No test file was edited to accommodate a rename.

### 25.4 Step 2 — `_utils.py`

All 49 aliases and the 100-entry `__all__` are gone, and with step 1 having moved
every importer, none of the four sub-module imports had a reader either. What is
left is an 18-line docstring naming the four siblings. **Deleting the file is
not 4j's work** — 4j moves imports, it does not remove definitions or modules —
so it is logged in §25.7 as a Phase 2-style removal for Robert to take or leave.

The four sub-modules' own docstrings said "``_utils`` re-exports every name below
under both this spelling and its original underscore alias", which stopped being
true; each now says the module is the one place its names are imported from.

### 25.5 Step 3 — 133 re-exports removed, by façade

A name was removed when nothing outside its owning module reached it through the
façade: no `from <façade> import <name>`, no `<alias>.<name>` attribute access
under any import spelling, no `<façade>.<name>` string (patch targets included),
no `setattr`/`patch.object(<module>, "<name>")`, and no use in the façade's own
body. `getattr` on a module and f-string patch targets were searched for and do
not occur. Every removal takes the import line *and* the `__all__` entry.

- **`spec4.project_manager` (18)** — `_paths` (3): `RoundsOnDisk`,
  `_PHASE_VERSION_RE`, `_phase_version_dirs`. `_phase_markdown` (4):
  `_PHASE_FRONTMATTER_RE`, `_declared_ids`, `_phase_nfr_lines`,
  `_phase_stack_lines`. `_usage` (11): `USAGE_SCHEMA_VERSION`,
  `_COST_SUMMARY_EMPTY`, `_USAGE_COST_SOURCE`, `_USAGE_LOCK`, `_call_is_unpriced`,
  `_cost_block`, `_usage_float`, `_usage_int`, `_usage_versions`, `_write_atomic`,
  `usage_rollup_name`.
- **`spec4.agents.code_scanner` (33)** — `_scan` (21): the 16 scan budget/skip
  constants plus `_format_ci_block`, `_format_deployment_signals`,
  `_format_readme_block`, `_is_entrypoint_candidate`, `_read_text_safely`.
  `_review_render` (12): `_as_str_list`, `_format_empty_review`, `_name_label`,
  `_normalize_style_for_renderer`, the seven `_render_*` section renderers,
  `_style_value`.
- **`spec4.agents.stack_advisor` (12)** — `_render` (11): `_ID_KEYS`,
  `_ID_LABELS`, `_TOP_LEVEL_HANDLED`, `_as_ids`, `_as_list`, `_label`,
  `_render_any`, `_render_entry_links`, `_render_library_entries`,
  `_render_rest`, `_scalar_text`. `_stack_shape` (1): `_keyed_from_list`.
  Its `_extract_json_block` and `_render_references` re-exports went in step 1:
  §15.4's rename left them bound to names `__all__` no longer listed, which ruff
  F401 caught immediately. The docstring paragraph justifying them went with them.
- **`spec4.agents.phaser` (1)** — `_phase_extract`: `_objects_with_key`.
- **`spec4.layouts._chat` (6)** — `_chat_actions` (4): `_NO_CALLS_RECORDED`,
  `_NO_TOKEN_COUNT`, `_ff_controls`, `_open_button`. `_chat_panels` (1):
  `_RUN_COMPLETE`. `_chat_status` (1): `_completed_agents`.
- **`spec4.callbacks` (34)** — `_artifacts` (11) incl. the six `dl_*` download
  callbacks and `session_round`; `_chat` (17) incl. eleven `on_*` navigation and
  breadth callbacks, `_DEV_MODE`, `_EMPTY_TURN_NOTICE`, `_breadth_summary`,
  `_gate_answered`, `_start_retry_turn`; `_setup` (4); `_shared` (2):
  `_gate_agent` and `_open_pick_fields` — the latter is the tightening §15.2
  scheduled, now that `callbacks/designer/_refine.py` takes it from
  `callbacks._shared` directly.
- **`spec4.callbacks.designer` (18)** — `_wizard` (10), `_refine` (4),
  `_mock_gen` (4): `_MAX_HTML_BYTES`, `_llm_params`, `_planning_ctx`, `logger`.
  `_MOCK_BUFFERS`, `project_manager` and `threading` stay bound: §12.2 and
  `tests/test_designer.py` reach all four through this module.
- **`spec4.agentifier.agentifier` (11)** — `_seed` (3): `_build_registry`,
  `_graph_placement_lines`, `_vision_purpose`. `_render` (5): `PriorityEdits`,
  `_CATALOG_SPEC_PROMPT`, `_FEATURES_COMPLETE_TRANSITION`, `_PRIORITY_EDIT_RE`,
  `_VALID_PRIORITIES`. `_ff_review` (3): `_FF_REVISION_RE`,
  `_cc_ff_review_prompt`, `_spec_ff_review_prompt`. `_registry` stays — it is
  the `patch("spec4.agentifier.agentifier._registry.stream")` target.

Every sub-module still has at least one name imported by its façade, so no
`import` statement disappeared and **the four `callbacks` sub-modules and the
three `callbacks.designer` ones are still imported for their decorator side
effects.** The registry holds **92** callbacks after the change (§15.5).

### 25.6 Step 4 — façade docstrings

All nine already named their sub-modules (4a–4i wrote them that way). What
changed is the sentence each ended on — "every name the split moved is
re-exported below, so no importer changed when the code moved" — which step 3
falsified. Each now says that 4j moved the importers onto the owning module and
that what remains listed is exactly what some importer outside that module still
needs. `callbacks/__init__.py` adds the point that registration does not depend
on `__all__` at all: it is the four imports, not the names they carry, that run
the decorators.

### 25.7 Genuinely dead names, logged not deleted

**None of the 11 aliases that had no importer is a dead definition.** All eleven
(`_AGENT_DELIVERABLE`, `_DEV_MODE`, `_STYLE_LEAF_KEYS`, `_VISION_FRAMING_FIELDS`,
`_ai_served_feature_ids`, `_designer_affordance_hints`,
`_project_feature_for_stack`, `_render_one_style`, `_served_product_feature_ids`,
`_short_text`, `_stale_phrase`) resolve to a public name its own module still
uses; only the alias was dead, and the alias is gone.

Of the 133 re-exports removed in step 3, 29 have no remaining reference anywhere
outside their own `def` line. **All 29 are decorator-registered Dash callbacks**
— the six `dl_*` downloads, eleven `on_*` navigation callbacks, four setup
callbacks, ten Designer wizard/refine callbacks — invoked by the Dash dispatcher,
never by name. They are exactly what `vulture_whitelist.py` exists for, and none
is a removal candidate. The remaining 104 are all still used inside their owning
module or by a sibling that imports them directly.

The one removal candidate 4j produces:

- **`src/spec4/agents/_utils.py` (18 lines, 0 statements) has no importer left.**
  Deleting it is a Phase 2-style file removal, not an import move, so 4j did not
  do it. If it goes, `tests/README.md` and §16 lose their last reference to it.

### 25.8 Deferred / not acted on

- **`vulture_whitelist.py` groups its names under `# src/spec4/…` comments that
  step 3 did not move.** The names are still correct — none of them moved
  modules in 4j — but the comment above e.g. the `dl_*` block says
  `callbacks/__init__.py` when the definitions are in `callbacks/_artifacts.py`
  (true since 4g, not something 4j changed). Regenerating that file is Phase 7's
  measurement pass, per §11.
- **In-source prose naming `agents/_utils.py`** was corrected where it named a
  module that no longer holds the thing: `design_manifest.py`, `stack_routing.py`
  and `feature_specs.py` now say `agents._turn_flow` imports `project_manager`,
  and the three "mirror `spec4.agents._utils.slug`" docstrings
  (`stack_routing.py`, `evals/phaser/_load.py`,
  `evals/designer/manifest_signal_probe.py`) now name `_feature_context`. Broader
  docs — `tests/README.md`'s coverage table, `README.md`'s tree, `CLAUDE.md` —
  stay with Phase 7.
- **`spec4/__init__.py` and `agents/__init__.py`** were not touched: §15.4 puts
  their `__all__` out of 4j's scope.
- **`app.py`** has no import change (Rule 5 / D-LR1). It imports
  `spec4.callbacks` and `spec4.callbacks.designer` as packages; neither name it
  reaches through them was removed.
- **Phase 5** still owns every long function these files contain. 4j moved no
  code and split nothing.
- **`_feature_context.py` at 1185 lines** remains the §16.5 note it was.

### 25.9 One reverted first attempt, recorded for the diff's sake

The first run of step 1 renamed every underscore token that matched an alias,
file-wide, and so also renamed the *locally defined* `_DEV_MODE` in eight modules
that happen to import from `_utils` — `streaming.py`, `session.py`,
`brainstormer.py`, `_seam_check.py`, `agentifier.py`, `composer.py`,
`callbacks/_chat.py`, `callbacks/designer/_mock_gen.py` — none of which imports
`_DEV_MODE` from anywhere. It was caught by reading the diff before running
anything, reverted with `git checkout -- src tests evals scripts` from an
otherwise clean tree, and redone with the rename map restricted per file to the
names that file actually imports from `_utils`. `patch("spec4.agentifier.
agentifier._DEV_MODE", …)` in `tests/agentifier/test_ff_sweep.py` would have
failed loudly on the first version; it is untouched by the second.

### 25.10 Verification beyond the gate

- **No importer of `spec4.agents._utils` remains** in `src/`, `tests/`, `evals/`
  or `scripts/` — checked by `ast`, not grep, so a function-body import counts.
- **`__all__` integrity**: every string in every `__all__` under `src/` resolves
  to a name bound in that module. The check found exactly one break —
  `stack_advisor`'s two step-1 orphans — and it is clean afterwards.
- **No renamed name is reachable from outside under its old spelling**: for each
  of the 46 rewritten files, every name it lost was searched for as
  `<that module>.<old name>` across the repo, under the full dotted path, under
  every import alias, and as a bare string next to a mention of the module.
  One hit, `agentifier._stream_suppressing_json` (§25.3), and it is preserved.
- **Callback registry: 92**, unchanged (§15.5).
- **`tests/test_streaming_characterization.py` and `tests/test_layout_contract.py`
  were not edited** (§15.5). Neither imported from `_utils`.
- The layering test's four rules still hold; 4j adds no import edge that crosses
  a layer, and every new edge points into `spec4.agents._*`, which the rules do
  not constrain.

### 25.11 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Layering | `uv run pytest tests/test_import_layering.py -q` | `7 passed in 0.39s` (exit 0) |
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `217 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 90 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 168.40s (0:02:48)` (exit 0) |
| Coverage | same run | `TOTAL 11865 stmts, 893 miss, 92%` |

Test count is unchanged at 4256 — 4j adds no test and removes none. `217 files`
and `90 source files` are §24.7's, unchanged: 4j creates and deletes no module.
Statements fell 11904 → 11865 (−39, the removed import lines and `__all__`
entries) and misses held at **893**, so no per-module floor moved;
`agents/_utils.py` is now 0 statements / 100%. `.coverage` was restored after
the run.

### 25.12 The `evals/` check the gate does not do

The four gate commands cover `src/` and `tests/` only, so nothing in them would
have caught a mis-rename in the seven `evals/` files step 1 rewrote. Two checks
were run for this sub-phase specifically and are not part of the permanent gate:

| Check | Command | Result |
|---|---|---|
| Ruff on `evals/` | `uv run ruff check evals/` | `All checks passed!` (exit 0) |
| Import each rewritten module | `uv run python -c "import <module>"` | 7 of 7 import (see below) |

`ruff check evals/` runs the same `E`/`F` rule set as the gate, so F401 (a name
imported and never used) and F821 (a name used and never bound) — the two shapes
a mis-rename takes — would both have surfaced. It is clean.

Importing is the stronger check, because it resolves the name against the module
it now names rather than only checking the file is self-consistent:

| Module | Alias it used to import | Result |
|---|---|---|
| `evals.run_tier_eval` | `_TIER_ORDER_FOR_SUMMARY as _TIER_ORDER` | OK |
| `evals.agentifier.mechanism_scoring` | `_TIER_ORDER_FOR_SUMMARY` | OK |
| `evals.agentifier.run_mechanism_probe` | `_extract_json_block` | OK |
| `evals.designer.coverage` | `_ai_features_for_designer` | OK |
| `evals.stack_advisor.projection_baseline` | `_ai_features_for_stack` | OK |
| `evals.stack_advisor.spine_coverage` | `slug` (already public) | OK |
| `evals.scout.join_coverage` | `slug` (already public) | OK, with `evals/scout` on `sys.path` |

The last one is the only entry needing a word. A bare
`python -c "import evals.scout.join_coverage"` fails at its **line 53**,
`from fanout_baseline import …` — a sibling-script import that resolves only when
the script's own directory is on `sys.path`, which is how the file is run. That
import is unchanged since before 4j (`git show HEAD:evals/scout/join_coverage.py`
has the identical line) and it fails *before* reaching the rewritten line 59.
With `evals/scout` on the path the module imports clean, which is what exercises
the rewrite. Not a 4j regression, and not fixed here — making the `evals/` script
dirs importable as packages is neither a Phase 4 concern nor behaviour-preserving
for the way they are invoked. Logged for whoever next touches `evals/`.

The two `evals/` files 4j edited for prose only, `evals/phaser/_load.py` and
`evals/designer/manifest_signal_probe.py`, also import clean. No `__pycache__` or
other artifact was left behind by the check — `git status` shows modifications
only.

## 26. Phase 4g2 — `callbacks/_chat.py` split into `_gate.py` and `_nav.py`

Recorded 2026-09-09 on branch `look-rework`, immediately after 4j. The sub-phase
§15.3 added to the table during 4g and §22.6 deferred; it had not been run. Two
files added under `src/spec4/callbacks/`, three changed there, three test files
edited (§26.5). `pyproject.toml` is untouched, nothing was written under
`.spec4/`, `.venv/` or `.git/`, and no git command was run beyond `git show
HEAD:…`, `git diff` and `git status`, all read-only.

The split is the one §15.3 and §22.6 describe, along the two banner blocks
`_chat.py` already carried: the per-agent model gate (old lines 176–534) and the
navigation buttons (old 956–1182). Nothing else moved.

### 26.1 Line counts

| File | Lines | Was |
|---|---:|---:|
| `callbacks/_chat.py` | 588 | 1182 |
| `callbacks/_gate.py` | 382 | — |
| `callbacks/_nav.py` | 252 | — |
| `callbacks/__init__.py` | 514 | 505 |
| `callbacks/_shared.py` | 74 | 72 |
| **package total** | **2716** | **2665** |

The +51 is two module docstrings, two import headers, and the nine lines
`__init__.py` grows by splitting one `from …_chat import (…)` into three. No
definition changed by a line. `_chat.py` is no longer the package's largest
module — `_artifacts.py` (542) and `__init__.py` (514) are now within 50 lines of
it, which is the shape §22.6 wanted.

### 26.2 The names moved to each

All 35 top-level names are accounted for; none was dropped, added or renamed.
29 of the 35 are `@callback`-decorated, and they partition 9 / 10 / 10.

**`_gate.py`** — the per-agent model gate (11): `_gate_answered`,
`on_gate_provider_change`, `on_gate_effort_options`, `on_gate_use_default`,
`on_gate_keep`, `on_gate_pick`, `on_gate_chip`, `on_chat_retry_model`,
`on_gate_back`, `on_gate_connect`, `on_gate_continue`. `on_chat_retry_model` is
here, not with the retry callbacks, because it is the picker's *entry* point —
it opens the gate on a failed step, and everything after it is a gate answer.
That is the "retry-model path" the sub-phase brief names, and it already sat
inside the gate banner between `on_gate_chip` and `on_gate_back`.

**`_nav.py`** — navigation between agents (11): `_switch_agent`,
`on_agent_pill_click`, `on_project_mode_choice`, `on_rescan_project`,
`on_review_to_brainstormer`, `on_brainstormer_to_designer`,
`on_brainstormer_to_agentifier`, `on_agentifier_to_designer`,
`on_stack_to_phaser`, `on_phaser_to_deployer`, `on_deployer_new_project`. The
"Deployer navigation" sub-banner moved verbatim with the last two.
`on_rescan_project` is here rather than left behind although it is not an
`on_*_to_*`: it sat inside the "Chat — navigation" banner, it writes
`active_agent`-adjacent state the same way the others do, and it is none of the
turn, the breadth panel or the poll. §15.3's line estimate for `_nav` (~230)
counts it; the block is 222 lines.

**Stayed in `_chat.py`** — the turn, breadth and poll core (13): `_DEV_MODE`,
`on_init_turn`, `on_chat_submit`, `on_fast_forward`, `_start_retry_turn`,
`on_chat_retry`, `on_ff_info`, `_breadth_summary`, `on_breadth_submit`,
`on_breadth_try_again`, `on_breadth_change`, `_EMPTY_TURN_NOTICE`,
`on_stream_poll`.

### 26.3 The one new sibling edge, and rule 4

The blocks come apart with **exactly one** cross-block reference:
`_gate.on_gate_continue` ends in `return _start_retry_turn(answered)`, and
`_start_retry_turn` is the retry core, which stays in `_chat`. So:

```
_shared  <-  _chat  <-  _gate
_shared  <-  _nav
```

Acyclic and one-way: `_chat` reads nothing from `_gate` or `_nav`, and `_nav`
reads nothing from either. §22.6 predicted the gate would come out "without a new
cross-module private import" because `_gate_agent` and `_open_pick_fields` were
already in `_shared`; it did not foresee `_start_retry_turn`. The edge is spelled
`from spec4.callbacks._chat import _start_retry_turn` — a sibling, not the
package, so **rule 4 is untouched** and `tests/test_import_layering.py` passes
unedited (7 tests). Six modules now match `spec4.callbacks.*` and none has an
edge to `spec4.callbacks`.

It is left private rather than promoted to `start_retry_turn`. Phase 4's rule is
"underscore-prefixed names used across files get promoted", but 4g already set
the opposite convention inside this package — `_HOME`, `_gate_agent` and
`_open_pick_fields` are imported across modules under their private spellings,
and §22.3 documents the sibling-import spelling as the norm here. Promoting one
of the four would make the package inconsistent with itself, and the name is in
no test's patch string. Logged as a deliberate deviation, not an oversight.

**No re-export façade was left behind.** The brief's fallback applied: with
`__init__.py` retargeted onto the owning modules, every name `_chat.py` would
have re-exported has zero importers, so — as in 4j — none was created. `_chat.py`
exports only what it defines, exactly like `_gate`, `_nav`, `_setup` and
`_artifacts`; no `__all__` is needed in any of them.

`callbacks/__init__.py` now imports 7 names from `._chat`, 9 from `._gate` and 2
from `._nav` (`on_agent_pill_click` and `_switch_agent`, the latter read by
`tests/test_stream_error_recovery.py:24` through the package). Its 49-entry `__all__` is
unchanged: all 18 of those names are in it, and they resolve exactly as before,
just from three modules instead of one.
Its docstring and `_shared.py`'s were updated to name six sub-modules and to say
where the gate callbacks live now.

### 26.4 Verification beyond the gate

- **Byte-for-byte.** Every moved range was compared as raw text against the
  `HEAD` blob: old lines 188–534 appear verbatim in `_gate.py`, 961–1182 verbatim
  in `_nav.py`, and 39–175 and 537–953 verbatim in the new `_chat.py`. Sweeping
  the other way, **22 non-blank lines of the old file are not in any of the
  three** and all 22 are accounted for: the 9-line old module docstring, the 4
  import lines that were split or pruned, and the two outer banner boxes
  (177–185, 957) whose prose moved into the two new module docstrings. **No
  function or constant line is unaccounted for.**
- **Statement counts add up.** `coverage`'s own parser on the `HEAD` blob: 345
  statements. The three files now: 184 + 98 + 74 = **356**, +11 (the two import
  headers). `__init__.py` 113 → 115. Package delta **+13**; the suite-wide total
  moved 11865 → 11878, also +13, so **no other module's statement count changed**.
- **Coverage attribution, not coverage loss.** `_chat.py` was 345 stmts / 86 miss
  / 75%. The three are now 184/50, 98/8 and 74/28 — the same **86** misses,
  redistributed. Suite-wide misses held at **893**.
- **The callback registry holds 92**, unchanged (§15.5): 29 callbacks left
  `_chat.py` and 9 + 10 + 10 = 29 are registered from the three modules. Checked
  by importing `spec4.app` in a subprocess and counting `GLOBAL_CALLBACK_MAP`.
- **`tests/test_callback_co_presence.py` (50), `tests/test_import_layering.py`
  (7), `tests/test_streaming_characterization.py` (16) and
  `tests/test_layout_contract.py` (74) all pass unmodified.** None appears in
  `git diff --name-only`. The first walks the registry against every layout, so
  it is the check that a moved callback still renders with its ids; the last two
  are the Phase 1 net §15.5 protects.

### 26.5 The forced edits outside `src/`

Three test files reach a moved callback through a patch target naming
`spec4.callbacks._chat`. `ctx` is a `dash` module-level object read inside
`on_agent_pill_click` and `on_project_mode_choice`, both of which moved to
`_nav`, so the patch must move with them or silently patch the wrong module's
global. Each is a module-path retarget; **no assertion, fixture or test name
changed.**

| File | Sites | Change |
|---|---:|---|
| `tests/test_agent_pill_click.py` | 2 (l. 35, 137) | `patch("spec4.callbacks._chat.ctx")` → `…_nav.ctx` |
| `tests/test_designer.py` | 1 (l. 2131) | same, around `on_agent_pill_click` |
| `tests/test_project_mode.py` | 2 (l. 234, 250) | `from spec4.callbacks import _chat as cb` → `_nav as cb` |

Each was run alone before the suite: `test_agent_pill_click.py` 15 passed,
`test_project_mode.py` 34 passed, `test_designer.py` 162 passed.

Every other `spec4.callbacks._chat.*` patch target in the suite —
`_get_agent_gen`, `_persist_artifacts` and `streaming.get`/`pop`/`start`, across
`test_stream_error_recovery.py`, `test_callbacks_stream_poll.py`,
`test_usage_capture.py`, `test_agent_llm_selection.py`, `test_fast_forward.py`
and `tests/agentifier/test_try_again.py` — **needs no edit**, and that is not a
coincidence: the gate block uses none of those three names. `on_gate_continue`
reaches them only through `_start_retry_turn`, which stays in `_chat` and
resolves them in `_chat`'s globals. `_chat.py` therefore remains the single patch
surface for the streaming path, which its docstring now says.

### 26.6 Deferred / not acted on

- **`_start_retry_turn` stays private** across the one sibling edge (§26.3). If
  Phase 5 revisits the package's naming it should decide all four (`_HOME`,
  `_gate_agent`, `_open_pick_fields`, `_start_retry_turn`) together, not one.
- **`on_stream_poll` (132 lines) and `on_breadth_try_again` (81) are the two
  large functions left in `_chat.py`**; `on_gate_continue` (81) moved intact into
  `_gate.py` and `on_agent_pill_click` (44) into `_nav.py`. All four remain the
  Phase 5 findings §22.6 logged — 4g2 moved them, it did not shrink them. Nothing
  in `_nav.py` exceeds 44 lines and nothing in `_gate.py` exceeds 81.
- **`vulture_whitelist.py` is unchanged and still correct** — its entries are
  bare names and no name changed spelling. Its `# src/spec4/callbacks/__init__.py`
  section comment was already imprecise after 4g (§22.6); 4g2 spreads the same
  60 names over two more modules without making the comment any less true than it
  already was. Still Phase 7's regeneration.
- **§17.5's `_AGENT_SIDE` gap and §21.6's blocked fifth layering rule** are
  untouched; 4g2 adds nothing to either.
- **Import-linter is still not warranted.** `callbacks/` gains a second internal
  edge (`_gate` → `_chat`) but not a second *rule*: the one direction the
  contract pins — siblings may not import the package — is unchanged and still
  asserted non-vacuously by the `ast` test.
- **§15.3's table row for 4g2 is now done**; §15.3, §22.6, §23.6 and §24.6 all
  carry a forward reference to it that Phase 7 can retire.
- Nothing new for *Bugs found (not fixed)*.

### 26.7 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Layering | `uv run pytest tests/test_import_layering.py -q` | `7 passed in 0.36s` (exit 0) |
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 174.39s (0:02:54)` (exit 0) |
| Coverage | same run | `TOTAL 11878 stmts, 893 miss, 92%` |

Test count is unchanged at 4256 — 4g2 adds no test and removes none; the three
files it edits keep every test they had. `219 files already formatted` is §25.11's
217 plus `_gate.py` and `_nav.py`; `92 source files` is mypy's 90 by the same
arithmetic. Statements rose 11865 → 11878 (+13, §26.4) and misses held at **893**,
so no per-module floor moved. `.coverage` was restored after the run.

## 27. Phase 5 pre-work — fresh complexity inventory and sub-phase order

*Measured 2026-09-09 on `look-rework` at `8ff006d` ("Phases 4j and 4g2"), after Phase 4
completed. Every Phase 0 line reference (§4) is superseded by this section.*

Command: `uv run ruff check --select C90,PLR0912,PLR0913,PLR0915,SIM,B,ARG --statistics src/`

### 27.1 Headline counts

| Rule | Phase 0 | 2026-09-09 |
|---|---:|---:|
| C901 | 61 | 61 |
| PLR0912 | 40 | 40 |
| PLR0915 | 25 | 25 |
| PLR0913 | 12 | 12 |
| ARG001 | 9 | 8 |
| B905 / SIM105 / B904 / SIM117 / B007 / SIM905 | — | 4 / 3 / 2 / 2 / 1 / 1 |
| **Total `src/`** | | **159** |

138 complexity findings over **71 distinct functions**. `tests/`: 236 findings
(ARG 173, SIM117 37, PLR0913 9, B905 8, SIM300 8, SIM105 1).

### 27.2 Rules for every Phase 5 sub-phase

1. **Extract-only.** Named helpers, same call order, same strings. No rewriting, no
   reordering, no changed conditionals, no new behaviour. A helper is a cut, not a
   redesign.
2. **Proof is the existing tests, unmodified.** The golden and characterization files
   listed per sub-phase must pass without a single edit. If a test needs editing, the
   extraction was not behaviour-preserving — revert it.
   **A second exception, any sub-phase:** a test that asserts on `inspect.getsource()`
   output is **structural, not behavioural**, and cannot survive any decomposition of
   the function it inspects. Such a test may be **rewritten in place** — same file, same
   class, same name — to assert the same property through behaviour. The sub-phase
   report lists it as a forced edit with the **old and new assertion** quoted. No other
   test edit. *Added at 5m, where `test_persist_is_not_gated_on_the_draw_kind` asserted
   `"_persist_manifest(" in inspect.getsource(_start_gen)`.*

   **One exception, 5p only:** 5p(f) may make *lint-only* edits under `tests/` — yoda
   comparisons (SIM300) and `strict=False` on `zip` (B905). Nothing else under `tests/`
   is touched in any sub-phase, 5p included: no assertion, fixture, name or import
   changes.
3. **Line accounting (the 4g2 standard, §26.4).** Every line range used for an
   extraction or an accounting pass is **verified against absolute line numbers read
   from the file itself** — never from a renumbered listing (`sed | nl`, a `sed` range
   printed without `NR`, or an editor's relative view). Use
   `awk '{printf "%d\t%s\n", NR, $0}'` or equivalent. *Added after 5h attempt 1, where
   `_orphan_read_findings` was given a range ending 3 lines past its block because the
   bounds were read off a listing renumbered from 1; it swallowed the opening of the
   next statement and produced ~90 syntax errors.*
   After each extraction, compare the function's pre-edit text against the new code and
   account for **every non-blank old line**: present verbatim in a helper, or named in the report with its reason (a `def`
   line replaced by a call, a comment folded into a helper docstring). "No statement line
   is unaccounted for" is the pass condition.
4. **Statement counts add up.** `coverage`'s parser on the `HEAD` blob vs. the new file;
   the delta must equal the added `def`/`return` lines, and suite-wide misses must hold
   at 893.

   **Covered-path preference (5i-5o).** Extraction is coverage-neutral on a path the
   tests execute and coverage-*negative* on one they never reach: the helper's body
   stays missed and the new call statement at the never-executed site is missed too. So
   prefer a covered-path block of equal complexity weight. Where a function cannot reach
   threshold without extracting an uncovered block, the extraction **is permitted** on
   one condition: the only new miss is the **call statement** at the never-executed
   site. Report the total as **893 + N**, listing each of the N sites (file, line, the
   block it calls). A miss from any other cause is still a regression. **Do not add a
   `# noqa` to dodge this** -- the Phase 6 report re-baselines the number. *Added after
   5h, where extracting `stream_suppressing_json`'s never-taken `except` block moved
   misses to 894 (35.6).*
5. **Rule 4 (frozen surfaces) still binds.** Prompt text, artifact strings, component
   ids and `.spec4/` shapes move verbatim into helpers or stay put. Never re-flow a
   string to fit a new indent — helpers take the indent the string already has.
6. **A `# noqa` carries its reason on the same line**, in the form
   `# noqa: C901  # <why splitting would not help>`. Five are pre-approved in 27.4;
   any new one is a finding for review, not a shortcut.
7. Gate at the end of each sub-phase (Rule 6, current ratchet): ruff clean, format
   clean, **mypy 0 errors**, 4256 passed / 1 skipped, coverage ≥ 92%. (`.coverage` is
   untracked and gitignored since Phase 2 — nothing to restore. The Phase 0 note in
   §1 is superseded.)
8. **Nested closures are promoted, never suppressed in place.** Ruff counts a nested
   `def` toward its enclosing function, so a closure inside a flagged function cannot be
   left where it is: it becomes a module-level private helper, with everything it
   captured passed as explicit parameters **in the same order the closure read them**.
   A closure that captures and mutates an accumulator is promoted the same way, taking
   the accumulator as a parameter. *Added after 5d, which hit this: leaving `_field`
   nested kept `_format_spec_as_text` at C901 ~13 no matter how much of its tail was
   extracted, and the only alternative was a second, unapproved noqa. The `_field` row
   in 27.4 is superseded by what 5d did (31.2). The other four noqas are unaffected —
   none of those functions contains a closure.*
9. **Loop-body extraction.** A helper extracted from a loop *body* is dedented to module
   level like any other. A `continue` that ended the iteration becomes `return` (or
   `return None`) at the same point; **that is the one permitted statement rewrite**, and
   the sub-phase report names each site where it was applied. A loop body containing a
   `break`, or a `return` that exits the enclosing function, is **not** extracted as a
   unit: extract the blocks before and after it instead, leave the `break`/`return` in
   the caller's loop, and if the function is still over threshold after that, **stop and
   report** — do not add a noqa and do not introduce a sentinel return value to simulate
   the jump. *Added before 5f, the first sub-phase whose blocks are loop bodies rather
   than top-level sections.*
10. **Mechanical defects may be fixed in place; everything else reverts.** Three defect
    classes may be repaired without spending the sub-phase's retry: an **indentation
    error**; **annotation propagation, parameter or return** — a helper
    annotation that must match the narrowed type at its call site rather than the
    enclosing function's signature; and a **reference to a
    pre-promotion name** left behind by rule 8. The test is all three of: the gate names
    the exact line, the repair touches **no logic, no string and no control flow**, and
    the sub-phase report lists each fix by site. **Cap of five per sub-phase; a sixth is
    a stop.**

    Everything else keeps the original rule — one revert-and-retry, then stop. In
    particular a **failing test, a golden or snapshot mismatch, a changed callback
    count, or any repair that would need a changed conditional or a new statement** is
    never fixed in place: revert immediately, **no retry**, and report. Those mean the
    extraction itself was wrong, not that it was transcribed wrong.

    A fifth mechanical class: **a helper that references a caller local it was not
    given a parameter for**, detected as `F821` at the reference. The repair is adding
    the parameter — typed from the narrowed type at the call site — and passing the
    local at the call site; **no other change**. This is the same class as a
    pre-promotion name reference, caught by a different rule. *Added after 5l, where
    three helpers in `requires_reconciler.py` referenced `feature_specs`, `name_to_node`
    / `slug_to_node` and `nodes`.*

    A fourth mechanical class: **a `# noqa` comment that must be appended to an existing
    `def` line.** The repair is the comment's placement alone — **the signature line is
    never rewritten**, because a signature that fits on one line and one that spans
    several look identical from a range and are not. Append to what is there. If
    appending pushes the line past E501 in a file that lacks the E501 per-file-ignore
    (`project_manager.py` in 5o is the one to check — `agents/**` and `agentifier/**`
    already carry it), add `E501` to that same noqa rather than re-flowing the
    signature. *Added after 5h attempt 2, where `_validate_dependencies`'s single-line
    signature was replaced by a `def name(  # noqa: ...` opener and lost its parameter
    list.*

    *Corollary, and the cheapest way to never need this: type every extracted helper's
    parameters from the narrowed type at the call site, not from the enclosing
    signature. 5g's second attempt failed mypy on exactly that —
    `_deployer_roadmap_extras` took `dict[str, Any] | None` from `stack_for_deployer`'s
    signature, when the only call site sits below that function's
    `if not isinstance(stack, dict) ... return ""` guard.*
11. **Validate in memory, probe on scratch, then write.** Build each edited file's full
    new text in memory and run `ast.parse` on it. Then write it to a **scratch copy**
    and run `ruff check --select F821,F841,C90,PLR` against that copy. **Nothing is
    written to `src/` until the scratch copy is clean.** `ast.parse` catches syntax and
    indentation; only ruff catches an undefined name, an unused read, or a helper that
    is still over threshold — and ruff needs a file. *The scratch-probe step is what
    carried 5i, 5j and 5k through six or seven defects without one reaching the gate;
    5l dropped it and spent both its attempts. Extended after 5l.*

    The original form of the rule: build in memory, `ast.parse`, write only if it
    parses. A range
    slip, a bad dedent or a mangled signature then costs nothing on disk and is not an
    attempt -- it never reaches the gate. *Adopted during 5h, where it caught two
    indentation slips with nothing to revert; the three stops before it were all defects
    this would have held back.*
12. **Yield-bound generators.** For a generator whose complexity is its branch
    structure rather than its block bodies: extract every covered-path block the plan
    lists. If the function is still over threshold, build a **maximal** version in
    memory — every remaining non-yield body extracted as well — and measure it. Then:

    - **If the maximal build reduces C901, land the maximal build.**
    - **If it does not**, and every remaining branch guards a `yield`, a generator
      `return`, **or is an entry guard on the turn** — a branch that decides whether or
      which turn body runs (session-state presence, seed-arm selection, artifact-present
      checks) and **contains no extractable body of its own** — then
      `# noqa: C901, PLR0912, PLR0915` is **pre-approved** with the
      measured reason *"ten-yield generator; every remaining branch guards a yield or a
      generator return, so further extraction needs sub-generators (backlog)"* (with the
      yield count corrected per function). **Land the planned cuts, not the maximal
      build**, and add the function to the shared backlog entry for the `yield from`
      conversion.

    The maximal-build measurement is **required first**; the noqa covers only what
    survives it, and **the reason names which kind each surviving branch is**.

    **Report the measurement either way** — both builds' C901 / PLR0912 / PLR0915, in
    the sub-phase report. This covers `deployer.run` (5i), and `brainstormer.run`,
    `stack_advisor.run`, `code_scanner.run` (5j) and `_run_catalog_phase` (5k), which are
    the same shape. *Added after 5i measured deployer's maximal build at C901 21 — the
    same as the planned build — with statements falling 88 → 79.*

### 27.3 Per-function table

`C` = C901, `Br` = PLR0912 branches, `St` = PLR0915 statements, `Ar` = PLR0913 arguments,
`L` = non-blank lines. `—` = not flagged by that rule. **D** = decompose,
**N** = justified `# noqa`.

**The 16 sub-phases, in order.** Each is its own run and its own commit.

| # | Scope | Fns | Non-blank lines |
|---|---|---:|---:|
| 5a | `agents/stack_advisor/_render.py` — `_format_stack_as_text` | 1 | 224 |
| 5b | `agents/code_scanner/_review_render.py` — 4 renderers | 4 | 287 |
| 5c | `agents/brainstormer.py` — `_format_vision_as_text` | 1 | 61 |
| 5d | `agentifier/_render.py` — `_format_spec_as_text` + `_field` | 2 | 77 |
| 5e | `_phase_markdown.py` — `_phase_spec_preamble`, `render_phase_markdown` | 2 | 261 |
| 5f | `agents/_feature_context.py` | 7 | 743 |
| 5g | `agents/_stack_context.py` | 4 | 483 |
| 5h | `agents/` shared helpers (8 modules) | 10 | 659 |
| 5i | `agents/` orchestrators I — `phaser.run`, `deployer.run` | 2 | 870 |
| 5j | `agents/` orchestrators II — brainstormer, stack_advisor, code_scanner, designer | 5 | 856 |
| 5k | `agentifier/agentifier.py` — the three phase runners | 3 | 857 |
| 5l | `agentifier/` siblings (7 modules) | 10 | 622 |
| 5m | `callbacks/` | 5 | 553 |
| 5n | `layouts/` | 3 | 403 |
| 5o | root modules (8) | 12 | 923 |
| 5p | Cross-cutting sweep + promote the rule sets (27.5) | — | — |

Deviation from the plan's "one sub-phase per source directory": `agents/` holds 34 of
the 71 functions and 4,230 lines — one run cannot hold it and still verify line-for-line
(rule 3). It splits into 5f–5j: two by module, one helper batch, two by orchestrator.
`agentifier/` splits into 5k (the 621-line `_run_catalog_phase` and its two neighbours)
and 5l (the siblings). `callbacks/`, `layouts/` and the root modules stay one run each.
The five golden-pinned renderers lead, `_format_stack_as_text` first, as the plan sets.
Modes per sub-phase are in 27.6.

#### 5a — `agents/stack_advisor/_render.py` (golden-pinned)

| Function | Line | C | Br | St | Ar | L | V |
|---|---:|---:|---:|---:|---:|---:|:-:|
| `_format_stack_as_text` | 147 | 62 | 68 | 181 | — | 224 | D |

The worst function in the repo and the plan's named starting point. It is a flat
sequence of independent block renderers (providers, infrastructure, persistence,
libraries, integrations, project_structure, ai_conventions, additional_decisions…),
each appending to one `lines` list. One `_render_<block>(ss, lines)` per block, called
in the existing order.

**Proof:** `tests/test_renderer_goldens.py::TestStackRenderer` (5 tests) against
`tests/golden/render_stack_full.md`, `render_stack_minimal.md`,
`render_stack_string_blocks.md`.

#### 5b — `agents/code_scanner/_review_render.py` (golden-pinned)

| Function | Line | C | Br | St | Ar | L | V |
|---|---:|---:|---:|---:|---:|---:|:-:|
| `_format_review_as_text` | 100 | 41 | 44 | 128 | — | 149 | D |
| `_render_typed_notes` | 435 | 21 | 23 | 57 | — | 62 | D |
| `_render_persistence` | 268 | 12 | — | — | — | 29 | D |
| `_render_deployment` | 324 | 11 | — | — | — | 47 | D |

The file already uses the `_render_x(value, lines)` shape; `_format_review_as_text` is
the remaining unsplit spine. `_render_persistence` extracts its database loop
(`_database_parts`); `_render_deployment` extracts its four independent blocks
(container / orchestration / paas / iac); `_render_typed_notes` extracts one helper per
note type.

**Proof:** `TestReviewRenderer` (7 tests, incl. a 4-way parametrize) against
`render_review_full.md`, `render_review_strings.md`, `render_review_empty*.md` (4),
`render_review_no_tests.md`, `render_review_skeleton.md`.

#### 5c — `agents/brainstormer.py` (golden-pinned)

| Function | Line | C | Br | St | Ar | L | V |
|---|---:|---:|---:|---:|---:|---:|:-:|
| `_format_vision_as_text` | 506 | 16 | 15 | — | — | 61 | D |

Section-per-vision-key; one helper per section.
**Proof:** `TestVisionRenderer` (4 tests) against `render_vision_full.md`,
`render_vision_strings.md`, `render_vision_no_name.md`, `render_vision_review_footer.md`.

#### 5d — `agentifier/_render.py` (golden-pinned)

| Function | Line | C | Br | St | Ar | L | V |
|---|---:|---:|---:|---:|---:|---:|:-:|
| `_format_spec_as_text` | 102 | 18 | — | 55 | — | 77 | D |
| `_field` (nested) | 115 | 12 | 13 | — | — | 27 | **N** |

`_format_spec_as_text` is `_field(...)` calls plus tail sections; the tail extracts.
`_field` is a closure whose four branches *are* the four JSON value shapes (`None`,
`list`, `dict`, scalar), each 3–6 lines appending to the captured `lines`. Splitting it
yields four helpers that each take and return the accumulator — strictly worse.
→ `# noqa: C901, PLR0912  # four-way dispatch on JSON value shape; each branch is the
shape's rendering and shares the captured accumulator`.

`_format_catalog_as_text` (line 78, 17 lines) is the fifth golden-pinned renderer and is
**already under every threshold** — no work, but its goldens must stay green here.

**Proof:** `TestSpecRenderer` (2) + `TestCatalogRenderer` (3) against `render_spec.md`,
`render_spec_tier_fallback.md`, `render_catalog.md`, `render_catalog_empty.md`.

#### 5e — `_phase_markdown.py` (golden-pinned via `project_manager`)

| Function | Line | C | Br | St | Ar | L | V |
|---|---:|---:|---:|---:|---:|---:|:-:|
| `_phase_spec_preamble` | 47 | 20 | 17 | 65 | — | 176 | D |
| `render_phase_markdown` | 336 | — | — | 58 | — | 85 | D |

The fifth golden-pinned surface. `_phase_spec_preamble` is the largest preamble builder
in the repo: one helper per preamble section (stack routing, NFR threading, feature
context, seams). `render_phase_markdown` splits frontmatter assembly from body assembly.
Frontmatter JSON shape and the attribution footer are frozen (Rule 4).

**Proof:** `tests/test_project_manager_golden.py` (18 tests) against `phase_full.md`,
`phase_full_no_context.md`, `phase_minimal.md`, `phase_final.md`, `README.md`,
`README_moved_footer.md`. Note this file was listed by the original brief as
`project_manager/_phase_markdown.py`; after 4j it is a **root sibling**,
`src/spec4/_phase_markdown.py`, imported by `project_manager.py:75` and `_artifacts.py:26`.

#### 5f — `agents/_feature_context.py`

| Function | Line | C | Br | St | Ar | L | V |
|---|---:|---:|---:|---:|---:|---:|:-:|
| `ai_features_for_designer` | 658 | 23 | 18 | 69 | — | 106 | D |
| `ai_features_for_deployer` | 502 | 20 | 19 | 61 | — | 112 | D |
| `ai_features_for_phaser` | 349 | 16 | 16 | 64 | — | 140 | D |
| `project_feature_for_stack` | 79 | 16 | 15 | — | — | 71 | D |
| `feature_specs_for_stack` | 885 | 16 | 15 | — | — | 107 | D |
| `ai_features_for_stack` | 163 | 11 | — | — | — | 97 | D |
| `feature_specs_for_phaser` | 1069 | 11 | — | — | — | 110 | D |

Seven consumer-shaped renderings of the same two artifacts. Each is a per-feature loop
emitting an optional-field block. Extract `_<consumer>_feature_lines(feature)` per
function first; **only after all seven are extracted** compare the helpers and note
genuine duplicates for 5p — do not lift across consumers inside this sub-phase (Rule 7,
one concern per phase). Prompt text is never lifted.

**Proof:** `tests/test_deployer_phases_context.py`, `test_phaser_feature_specs_context.py`,
`test_deployer_ai_channel.py`, `test_deployer_nfr_channel.py`, `test_feature_specs_pass.py`.

#### 5g — `agents/_stack_context.py`

| Function | Line | C | Br | St | Ar | L | V |
|---|---:|---:|---:|---:|---:|---:|:-:|
| `stack_for_deployer` | 171 | 29 | 28 | 81 | — | 170 | D |
| `stack_digest_for_phaser` | 538 | 24 | 21 | 66 | — | 144 | D |
| `design_manifest_for_stack` | 440 | 17 | 17 | — | — | 88 | D |
| `manifest_for_phaser` | 695 | 11 | — | — | — | 81 | D |

Same shape as 5f, over the stack spec and design manifest. One `_<block>_lines(ss)`
helper per stack block, in the existing emission order.

**Proof:** `tests/test_deployer_stack_digest.py`, `test_phaser_manifest_context.py`,
`test_design_manifest.py`, `test_deployer_env_and_semantics.py`.

#### 5h — `agents/` shared helpers

| File | Function | Line | C | Br | St | Ar | L | V |
|---|---|---:|---:|---:|---:|---:|---:|:-:|
| `_phase_coverage.py` | `check_phase_coverage` | 180 | 26 | 26 | 69 | — | 170 | D |
| `_manifest.py` | `validate_manifest` | 145 | 17 | 17 | — | — | 82 | D |
| `_turn_flow.py` | `build_revision_context` | 74 | 17 | 16 | — | — | 69 | D |
| `_reask.py` | `stream_suppressing_json` | 169 | 15 | 16 | — | — | 96 | D |
| `code_scanner/_scan.py` | `_gather_project_context` | 165 | 15 | 13 | — | — | 62 | D |
| `feature_speccer.py` | `_reconcile_dependencies` | 410 | 12 | — | — | — | 43 | D |
| `_seam_check.py` | `_check_table_provenance` | 208 | 11 | — | — | — | 50 | D |
| `stack_advisor/_stack_shape.py` | `_normalise_stack_shape` | 106 | 11 | — | — | — | 51 | D |
| `feature_speccer.py` | `_validate_dependencies` | 368 | 11 | — | — | — | 35 | **N** |
| `_reask.py` | `reask_for_artifact` | 75 | — | — | — | 10 | 48 | **N** |

- `validate_manifest` — five separately-commented advisory checks, each appending to
  `warnings`; one `_warn_<check>(...)` per comment block. The light-repair pass at the
  end is its own helper.
- `_check_table_provenance` — three sequential passes (build `creators`, check reads,
  report unread); one helper each.
- `_normalise_stack_shape` — four independent block coercions (`libraries` fold,
  keyed-to-list, list-to-keyed, `ai_conventions`); one helper each, same order.
- `_reconcile_dependencies` — two phases: build `implied`, then apply. Extract
  `_implied_producers(features)`.
- `_validate_dependencies` — **N**: one DFS with a recursive inner `dfs` maintaining the
  WHITE/GRAY/BLACK invariant across the whole function; cutting it breaks the invariant.
  → `# noqa: C901  # single DFS back-edge pruning; the WHITE/GRAY/BLACK colour invariant
  spans the whole function, so any split leaves a helper that can only be called at one
  point in the traversal`.
- `reask_for_artifact` — **N**, arity only: 10 parameters are the reask contract
  (agent, artifact, schema, model, callbacks…), all threaded through. A params object is
  a design change, not extract-only. → `# noqa: PLR0913`.

**Proof:** `tests/test_phase_coverage.py`, `test_manifest.py`, `test_seam_check*.py`,
`test_dependency_reconciliation.py`, `test_feature_ids.py`, `test_reask*.py`.

#### 5i — `agents/` orchestrators I

| File | Function | Line | C | Br | St | L | V |
|---|---|---:|---:|---:|---:|---:|:-:|
| `phaser/__init__.py` | `run` | 84 | 33 | 37 | 148 | 472 | D |
| `deployer.py` | `run` | 548 | 24 | 30 | 130 | 398 | D |

The two largest agent turns. Both are linear: load context → build prompt → stream →
parse → validate/reconcile → persist → render. Cut on those seams into
`_load_<agent>_context`, `_build_<agent>_prompt`, `_persist_<agent>_output`. The stream
loop stays whole — it is the characterization surface. Two functions, one run, because
each is a single unbroken sequence that must be accounted for line-for-line.

**Proof:** `tests/test_streaming_characterization.py`, `test_deployer_invariants.py`,
`test_deployer_reentry.py`, `test_deployer_nfr_guidance.py`, `test_fast_forward.py`,
plus `tests/integration/test_pipeline_greenfield.py`.

#### 5j — `agents/` orchestrators II

| File | Function | Line | C | Br | St | Ar | L | V |
|---|---|---:|---:|---:|---:|---:|---:|:-:|
| `brainstormer.py` | `run` | 630 | 20 | 22 | 79 | — | 227 | D |
| `stack_advisor/__init__.py` | `run` | 74 | 12 | 14 | 59 | — | 208 | D |
| `code_scanner/__init__.py` | `run` | 160 | 14 | 16 | 71 | — | 186 | D |
| `designer.py` | `generate_mock_streaming` | 545 | 22 | 21 | 65 | 13 | 139 | D + **N**(Ar) |
| `designer.py` | `build_mock_prompt` | 398 | 16 | 16 | — | 6 | 96 | D + **N**(Ar) |

Same seams as 5i. The two `designer.py` signatures are decomposed for complexity and
carry `# noqa: PLR0913` for arity: 13 and 6 parameters are the mock-generation contract
shared with `callbacks/designer/_mock_gen.py` (5m), and collapsing them into a params
object would change both call sites — a design change, logged for the backlog.

**Proof:** `tests/test_agents.py`, `test_designer.py`, `test_code_scanner_progress.py`,
`test_brainstormer_chars_counter.py`, `test_streaming_characterization.py`.

#### 5k — `agentifier/agentifier.py`

| Function | Line | C | Br | St | L | V |
|---|---:|---:|---:|---:|---:|:-:|
| `_run_catalog_phase` | 1654 | 38 | 41 | 230 | **621** | D |
| `_run_cross_cutting_phase` | 1258 | 13 | 14 | 83 | 145 | D |
| `_handle_cc_ff_review` | 951 | — | — | 54 | 91 | D |

`_run_catalog_phase` is the single largest function in the repo — 621 non-blank lines,
C901 38. It is the Agentifier's multi-step catalog turn (scout → compose → link →
reconcile → prioritize → tier → panel → close), each step already separated by a banner
comment. One `_catalog_step_<n>_<name>` per banner, called in order, threading the same
locals between them. **This sub-phase does nothing else** — expect the line-accounting
pass alone to be substantial.

**How the locals are threaded.** An explicit tuple is the default. A private dataclass
is acceptable as extract-only *only* under all three conditions: module-private
(underscore-prefixed, absent from `__all__`), never persisted, yielded, or returned past
`_run_catalog_phase`, and existing solely so the helpers can share locals that already
exist. Its fields are exactly the locals crossing a banner boundary — nothing added,
nothing renamed. **If the run finds itself designing those fields, it has drifted into
redesign: fall back to the tuple.** Choosing the dataclass requires a justification in
the sub-phase report naming which locals cross which boundaries and why a tuple was
unworkable.

**Proof:** `tests/agentifier/` (whole directory, incl. `test_streaming_e2e.py`),
`tests/test_cross_cutting_relocation.py`, `tests/test_agentifier_chars_counter.py`,
golden `render_catalog.md`.

#### 5l — `agentifier/` siblings

| File | Function | Line | C | Br | St | Ar | L | V |
|---|---|---:|---:|---:|---:|---:|---:|:-:|
| `pattern_loader.py` | `_validate_frontmatter` | 233 | 17 | 17 | — | — | 74 | **N** |
| `composer.py` | `run` | 198 | 15 | 15 | — | — | 95 | D |
| `grounding.py` | `render_grounding_for_prompt` | 102 | 14 | 13 | — | — | 57 | D |
| `_seed.py` | `_build_seed_message` | 333 | 13 | 14 | — | — | 85 | D |
| `linker.py` | `_normalize_edges` | 209 | 13 | — | — | — | 63 | D |
| `requires_reconciler.py` | `directional_signals` | 258 | 13 | 14 | — | — | 46 | D |
| `panel_closure.py` | `close_selection` | 65 | 12 | — | — | — | 60 | D |
| `requires_reconciler.py` | `reconcile_requires` | 421 | 11 | — | — | — | 100 | D |
| `requires_reconciler.py` | `_has_cycle` | 376 | 11 | — | — | — | 40 | **N** |
| `_seed.py` | `_call_scout` | 145 | — | — | — | 7 | 26 | **N**(Ar) |

- `_normalize_edges` — its docstring already lists four contract passes (self-edges,
  dangler degrade, requires cleanup, scope normalisation); one helper per bullet.
- `close_selection` — a fixpoint loop over two named rules; extract
  `_apply_requires_closure(...) -> bool` and `_apply_coordinator_toggle(...) -> bool`,
  both returning `changed`. The `while changed` loop stays.
- `directional_signals` — three documented signals S1/S1b/S2; one helper each.
- `render_grounding_for_prompt` — one `_served_feature_lines(feat)` for the eight
  optional field renderings inside the loop.
- `_validate_frontmatter` — **N**: a flat schema validator, one `if` per frontmatter
  field, each 2–3 lines appending an error. This is the case the plan text names
  ("a schema validator"); helpers here would be a rename, not a decomposition.
  → `# noqa: C901, PLR0912  # flat per-field schema validation; one branch per field`.
- `_has_cycle` — **N**: iterative DFS with an explicit colour stack; the invariant spans
  the loop. → `# noqa: C901  # single iterative-DFS cycle detection`.
- `_call_scout` — **N**, arity only, 7 threaded parameters. → `# noqa: PLR0913`.

**Proof:** `tests/agentifier/`, `tests/test_dependency_reconciliation.py`.

#### 5m — `callbacks/`

| File | Function | Line | C | Br | St | Ar | L | V |
|---|---|---:|---:|---:|---:|---:|---:|:-:|
| `designer/_mock_gen.py` | `_start_gen` | 226 | 20 | — | 64 | 13 | 190 | D + **N**(Ar) |
| `_chat.py` | `on_stream_poll` | 457 | 16 | 15 | — | — | 128 | D |
| `designer/_mock_gen.py` | `_run` | 291 | 15 | 16 | — | — | 107 | D |
| `designer/_refine.py` | `on_designer_regenerate` | 116 | — | — | — | 6 | 66 | **N**(Ar) |
| `_setup.py` | `on_setup_connect` | 60 | — | — | — | 6 | 62 | **N**(Ar) |

`on_stream_poll` is the plan's named target: a poll tick with distinct
running / finished / errored / cancelled arms. One `_poll_<state>(...)` per arm; the
`Output` tuple shape and every component id are frozen (Rule 4). `_start_gen` / `_run`
are the mock-generation launcher and its thread body; cut on the same seams as
`designer.generate_mock_streaming` (5j) but **do not** unify them here — that is 5p.

The three arity-only `# noqa: PLR0913` are Dash callback signatures: the parameter list
is the `Input`/`State` list, so it cannot be shortened without changing the callback
registration. → `# noqa: PLR0913  # parameters are the callback's Input/State list`.

**Proof:** `tests/test_callback_co_presence.py` (walks the registry against every
layout), `test_callbacks_stream_poll.py`, `test_drain_stream.py`,
`test_designer_wizard_register.py`, `test_streaming_characterization.py`. Callback
registry must still count **92** (§15.5) — check by importing `spec4.app` in a
subprocess and counting `GLOBAL_CALLBACK_MAP`.

#### 5n — `layouts/`

| File | Function | Line | C | Br | St | Ar | L | V |
|---|---|---:|---:|---:|---:|---:|---:|:-:|
| `_chat_actions.py` | `_chat_action_buttons` | 241 | 19 | 24 | 54 | — | 213 | D |
| `__init__.py` | `_agent_select_layout` | 301 | 13 | — | — | — | 133 | D |
| `_status_bar.py` | `_status_context` | 186 | — | — | — | 6 | 57 | **N**(Ar) |

Both decompositions are per-button / per-row builders returning a component; the parent
assembles the list in the same order. **Component ids are frozen** — every extracted
builder keeps the id literal it already emits, and
`tests/test_layout_contract.py` (74 tests, the Phase 1 id snapshot) is the proof.

**Proof:** `tests/test_layout_contract.py`, `test_chat_action_row_emphasis.py`,
`test_agent_select_layout.py`, `test_agent_rows.py`, `test_chat_pill_bar.py`,
`test_entry_screens.py`. Also re-run `tests/test_import_layering.py` — 5n must add no
edge out of `layouts`.

#### 5o — root modules

| File | Function | Line | C | Br | St | Ar | L | V |
|---|---|---:|---:|---:|---:|---:|---:|:-:|
| `llm.py` | `stream_turn` | 811 | 25 | 27 | 68 | 7 | 167 | D + **N**(Ar) |
| `_artifacts.py` | `merge_library_additions` | 111 | 14 | 14 | — | — | 78 | D |
| `session.py` | `_persist_artifacts` | 559 | 14 | 13 | — | — | 96 | D |
| `providers.py` | `_fetch_models` | 111 | 13 | — | — | — | 99 | D |
| `feature_specs.py` | `_render_graph_lines` | 474 | 13 | 13 | — | — | 44 | D |
| `feature_specs.py` | `_render_topology` | 419 | 12 | — | — | — | 33 | D |
| `session.py` | `_load_working_dir` | 225 | 12 | — | 51 | — | 114 | D |
| `usage_report.py` | `render_usage_table` | 91 | 12 | — | — | — | 43 | D |
| `project_manager.py` | `_artifact_button_state` | 431 | 13 | — | — | — | 42 | **N** |
| `llm.py` | `_record_usage` | 414 | — | — | — | 9 | 60 | **N**(Ar) |
| `llm.py` | `_iter_with_usage` | 498 | — | — | — | 6 | 46 | **N**(Ar) |
| `llm.py` | `_aiter_with_usage` | 547 | — | — | — | 6 | 41 | **N**(Ar) |

- `stream_turn` — the LLM turn spine; cut into request assembly, the chunk loop, and
  usage/finish handling. The chunk loop stays whole.
- `merge_library_additions` — extract `_libraries_map(merged)` (the wrapped/bare shape
  locate) and `_library_entry(entry)` (the per-addition build incl. the D-PH7d join keys).
- `render_usage_table` — extract the missing/unpriced/notes tail as `_usage_footnotes(data)`.
- `_render_topology` / `_render_graph_lines` — extract the sub-agent loop and the
  `tier_analysis` block respectively.
- `_artifact_button_state` — **N**: the branches *are* the documented state machine
  above the function, each returning a distinct `AGENT_BTN_*` constant. Splitting it
  scatters the machine across helpers and makes the transitions unreadable.
  → `# noqa: C901  # the branches are the documented artifact button state machine`.
- The three arity-only `llm.py` noqas thread the LLM call parameters (model, messages,
  tools, temperature, callbacks…) unchanged; a params object is a design change.

**Proof:** `tests/test_llm.py`, `test_session.py`, `test_project_manager_golden.py`,
`test_agent_button_state.py`, `test_feature_specs.py`, `test_usage*.py`,
`test_cost_summary.py`, `test_streaming_characterization.py`. `project_manager.py` is
also golden-pinned — `tests/golden/README.md` and `phase_*.md` must not move.

### 27.4 The five complexity `# noqa`s, in one place

| File | Function | Rule(s) | Reason |
|---|---|---|---|
| `agentifier/_render.py` | `_spec_field` | C901, PLR0912 | four-way dispatch on JSON value shape; each branch is that shape's rendering. **Superseded in place by 5d** (31.2): promoted out of `_format_spec_as_text` per rule 8, so the accumulator is a parameter and the reason no longer cites capture. |
| `agentifier/pattern_loader.py` | `_validate_frontmatter` | C901, PLR0912 | flat per-field schema validation; one branch per field |
| `agentifier/requires_reconciler.py` | `_has_cycle` | C901 | single iterative-DFS cycle detection; the colour invariant spans the loop |
| `agents/feature_speccer.py` | `_validate_dependencies` | C901 | single DFS back-edge pruning; the WHITE/GRAY/BLACK colour invariant spans the whole function, so any split leaves a helper callable at only one point in the traversal |
| `project_manager.py` | `_artifact_button_state` | C901 | the branches are the documented artifact button state machine |
| `agents/deployer.py` | `run` | C901, PLR0912, PLR0915 | ten-yield generator; every remaining branch guards a yield or a generator return, so further extraction needs sub-generators (backlog). **Sixth pre-approved noqa, added after the 5i measurement (37.5); granted under rule 12.** |
| `agents/brainstormer.py` | `run` | C901, PLR0912 | six-yield generator; after the maximal build the surviving branches are five yield/return guards (staleness, resume, the seed chain's greeting arm, the review reply, the artifact re-ask) and nine entry guards with no extractable body (session-state presence, `user_input is None`, `msgs`, the four-arm seed selection, the review-request gate, two artifact-present checks). **Seventh pre-approved noqa; granted under rule 12 as amended (39.5).** |
| `agents/code_scanner/__init__.py` | `run` | C901, PLR0912, PLR0915 | nine-yield generator; after the maximal build the surviving branches are five yield/return guards (staleness, resume, the re-entry gate, the missing-working-dir exit, the schema-retry re-ask) and seven entry guards with no extractable body (session-state presence, `user_input is None`, `msgs`, three artifact-present checks). **Eighth pre-approved noqa; granted under rule 12 as amended (39.5).** |
| `agentifier/agentifier.py` | `_run_catalog_phase` | C901, PLR0912, PLR0915 | **24-yield** generator, the most yield-dense function in the repo; after the maximal build the surviving branches are yield/return guards on the Scout / Composer / Linker / TierAnalyst sub-agent turns and entry guards with no extractable body. **Ninth pre-approved noqa; rule 12 (41.2).** |
| `agentifier/agentifier.py` | `_run_cross_cutting_phase` | C901, PLR0912, PLR0915 | 12-yield generator; surviving branches are yield/return guards on the per-topic turns and entry guards with no extractable body. **Tenth pre-approved noqa; rule 12 (41.2).** |
| `llm.py` | `stream_turn` | C901, PLR0912, PLR0915, PLR0913 | **entry guards plus the chunk loop, which 27.3 keeps whole as the streaming characterization surface.** Eleventh pre-approved noqa; rule 12 (48.2). **The widening is deliberate and named:** entries 6-10 survive on yield/return guards and entry guards alone, while this one also keeps a stream loop and its per-chunk branches in place *by instruction*, not because they resist extraction — 5o's first attempt proved they can be extracted and that doing so breaks the turn (48.1). |

Plus **12 `# noqa: PLR0913`** — arity cannot be reduced by extraction. Eight are
arity-only (`_seed._call_scout` 7, `_reask.reask_for_artifact` 10,
`callbacks/_setup.on_setup_connect` 6, `callbacks/designer/_refine.on_designer_regenerate` 6,
`layouts/_status_bar._status_context` 6, `llm._record_usage` 9, `llm._iter_with_usage` 6,
`llm._aiter_with_usage` 6); four sit on functions also decomposed for complexity
(`designer.build_mock_prompt` 6, `designer.generate_mock_streaming` 13,
`callbacks/designer/_mock_gen._start_gen` 13, `llm.stream_turn` 7).

**Backlog item (not Phase 5):** the two 13-argument designer signatures and the
10-argument reask signature want a params object. That changes call sites and is a design
change, not cleanup — log under *Bugs found (not fixed)* / backlog.

**Backlog item (not Phase 5): `yield from` sub-generator conversion.** Every agent turn
that is a long generator carries its complexity in branches that each guard a `yield` or
a generator `return`, so extraction cannot reduce it (rule 12). Converting those branches
into sub-generators driven by `yield from` is the real fix and is a redesign of the turn
loop, not cleanup. Functions on this entry: **`deployer.run`** (measured in 37.5), **`brainstormer.run`** and
**`code_scanner.run`** (measured in 39.2 and 40.1). `stack_advisor.run` and
`designer.generate_mock_streaming` cleared under extraction and are **not** on this
entry. **`_run_catalog_phase`** and **`_run_cross_cutting_phase`** joined it in 5k (41.2).
`_handle_cc_ff_review` cleared under extraction and is **not** on it.

### 27.5 — 5p, the cross-cutting sweep

Runs last, after every long function is settled.

**a. Cross-agent duplication.** Phase 4 already lifted reask / turn-flow / stream
helpers into `agents/_reask.py`, `_turn_flow.py`, `_seam_check.py`, so the plan's
premise is partly spent. Measure before lifting: compare the per-consumer helpers 5f and
5g produced, and the mock-generation seams shared between `agents/designer.py` (5j) and
`callbacks/designer/_mock_gen.py` (5m). Lift only exact-shape matches of 10+ lines
differing solely in constants, with the constants as parameters. **Prompt text is never
lifted** — it stays in each agent.

**b. Magic strings.** Artifact file names, session keys, state constants and component
ids appearing as literals in more than one place become constants in
`app_constants.py` (or a sibling). **String values stay byte-identical** — the id
snapshot in `test_layout_contract.py` and the goldens are the check.

**c. Error handling.** 3 × SIM105 (`_artifacts.py:65`, `_usage.py:357`,
`callbacks/designer/_refine.py:316`) → `contextlib.suppress`. 2 × B904
(`agentifier/subagents.py:181,251`) → `raise ... from err`. 1 × B007
(`agents/designer.py:199`) → rename `root` to `_root`. 2 × SIM117
(`websearch.py:180,189`) → merged `with`. 1 × SIM905
(`requires_reconciler.py:84`) → list literal. Any remaining bare `except:` or
`except Exception: pass` gets a specific exception plus a log line, or a comment saying
why swallowing is correct.

**d. `B905` — 4 sites** (`agentifier/_seed.py:380`, `agentifier/pattern_loader.py:160`,
`callbacks/designer/_refine.py:73`, `project_manager.py:468`). Use **`strict=False`**,
which is byte-identical to today's silent truncation. `strict=True` would raise on
unequal lengths — a behaviour change, out of scope. Log each site as a candidate for
`strict=True` in a separate review.

**e. `ARG` — 8 in `src/`.** `agentifier/agentifier.py:1508` (`llm_config`), `:2401`
(`user_input`); `callbacks/_chat.py:106` (`n_clicks`, `n_submit`), `:457` (`n`);
`callbacks/designer/__init__.py:182` (`n`); `layouts/__init__.py:235` (`session`);
`layouts/_setup.py:231` (`session`). Dash binds callback arguments positionally, so
underscore-prefix them; where a name is part of a called-by-keyword contract (check each
call site first), use `# noqa: ARG001` instead.

**f. `tests/` per-file ignores.** 236 findings. Add to `[tool.ruff.lint.per-file-ignores]`:
`"tests/**/*.py" = ["ARG", "SIM117", "PLR0913"]` — 173 ARG are fixture/stub parameters,
37 SIM117 are `pytest.raises` + `patch` stacks whose nesting is deliberate, 9 PLR0913 are
fixture-heavy signatures. Fix mechanically instead of ignoring: 8 SIM300 (yoda), 8 B905
(`strict=False`), 1 SIM105.

**g. Promote the rule sets.** With a–f done, change `pyproject.toml`
`[tool.ruff.lint] select = ["E", "F"]` to `["E", "F", "C90", "PLR", "SIM", "B", "ARG"]`,
carrying the per-file-ignores from (f) and keeping the existing `E501`/`E402` entries —
in particular `"src/spec4/app.py" = ["E501", "E402"]`, which Rule 5 (D-LR1) freezes.
From here on `ruff check src/ tests/` with the full set is the gate. Verify
`uv run ruff check src/ tests/` returns `All checks passed!` before the sub-phase ends.

**h. Type hygiene.** Replace `Any` where the actual type is known from usage. Do **not**
introduce `TypedDict`s for the session dict — that is a design change (plan, Phase 5).

### 27.6 Model and mode per sub-phase

| Sub-phase | Mode | Why |
|---|---|---|
| 5a, 5b | Opus 5, **plan**, high | The first two renderer decompositions set the extract-only discipline for the other fourteen; the pattern they establish is reused verbatim. |
| 5c, 5d, 5e | Opus 5, auto, high | The check that the discipline holds on smaller, fully golden-pinned surfaces before the `agents/` block opens. |
| 5f, 5g, 5h, 5j | Opus 5, auto, high | Many functions, one shape each; mechanical once 5a–5e have set the pattern. |
| 5i | Opus 5, **plan**, high | `phaser.run` (472) and `deployer.run` (398) — the first of the two big linear spines; the cut points need agreeing before the edit. |
| 5k | Opus 5, **plan**, high | `_run_catalog_phase` at 621 lines, plus the tuple-vs-dataclass call above. |
| 5l, 5m, 5n, 5o | Opus 5, auto, high | Bounded per-file work with a named test proof each. |
| 5p | Opus 5, **plan**, high | Promoting the rule sets edits `pyproject.toml` and changes the gate itself, and it is the one sub-phase permitted to touch `tests/`. |

### 27.7 Noted for Phase 7, not Phase 5

**Root modules vs. packages — a 4b leftover.** Phase 4b left `_paths.py`, `_artifacts.py`,
`_phase_markdown.py` and `_usage.py` as siblings at `src/spec4/` root, while 4c–4e gave
the agents real packages. The visible cost is that `src/spec4/_artifacts.py` now sits
next to `src/spec4/callbacks/_artifacts.py`, two unrelated modules one import line apart.
Converting `project_manager` to a package the way 4c–4e did would resolve it. **This is a
Phase 7 audit finding for a later round, not Phase 5 work** — it is a move, and Phase 5
is extract-only. Record it; do not act on it in any sub-phase.

### 27.8 What Phase 5 explicitly does not do

- No rewriting. Every sub-phase is extract-only; a helper that needs a changed
  conditional is a finding, not an edit.
- No prompt-text changes, no artifact-format changes, no component-id changes.
- No signature changes to reduce `PLR0913` — logged for the backlog instead.
- No test edits in 5a–5o. A sub-phase that needs one has broken behaviour. 5p's
  lint-only exception under `tests/` (27.2 rule 2) is the sole carve-out.
- No module moves or renames — including the root-vs-package inconsistency in 27.7.
- No `ruff format` run beyond what the gate already requires (the tree is format-clean
  since 0.5a and has stayed clean through 4j).

## 28. Phase 5a — `_format_stack_as_text` decomposed into 14 block renderers

`src/spec4/agents/stack_advisor/_render.py` only. Extract-only: 12 top-level block
renderers pulled out of the spine in call order, plus 2 nested helpers to bring the two
densest blocks under the C901 threshold. No other file changed.

### 28.1 Before and after

| | C901 | PLR0912 | PLR0915 | non-blank lines |
|---|---:|---:|---:|---:|
| `_format_stack_as_text` before | **62** | **68** | **181** | 224 |
| `_format_stack_as_text` after | 2 | — | — | 26 |

The file's C901/PLR0912/PLR0915 finding count goes **3 → 0**. Largest function in the
file is now `_render_any` (33 lines), which was already there and already clean.

### 28.2 The 14 helpers, in call order

`_format_stack_as_text` is now the `ss` unwrap, `lines = []`, twelve calls, the
`render_references` / `_render_rest` tail and the frozen Continue-to-Phaser footer:

| Helper | Block | Lines |
|---|---|---:|
| `_render_stack_header(ss, lines)` | `name`, `description` | 6 |
| `_render_languages(ss, lines)` | `languages` | 20 |
| `_render_deployment(ss, lines)` | `deployment` + `targets` | 18 |
| `_render_providers(ss, lines)` | `providers` | 18 |
| `_render_integrations(ss, lines)` | `integrations` | 15 |
| `_render_libraries(ss, lines)` | `libraries` (flat D-SC27 or category-keyed) | 17 |
| `_render_persistence(ss, lines)` | `persistence` | 29 |
| `_render_infrastructure(ss, lines)` | `infrastructure` | 16 |
| `_render_ai_conventions(ss, lines)` | `ai_conventions` | 11 |
| `_render_project_structure(ss, lines)` | `project_structure` | 19 |
| `_render_coding_style(ss, lines)` | `coding_style` | 10 |
| `_render_additional_decisions(ss, lines)` | `additional_decisions` | 20 |
| `_render_provider_capabilities(caps, lines)` | nested: one provider's `capabilities` | 13 |
| `_render_store_collections(collections, lines)` | nested: one store's `collections` | 23 |

Every helper takes `(ss, lines)` and opens with the block's own
`x: Any = ss.get(...) or ...` / `if x:` exactly as the spine had it, so the guard, the
`or` default and the falsy-skip are unmoved. The two nested helpers take the already-read
local (`caps`, `collections`) because that is the value the parent had in hand.

No name was added to `__all__`; the package `__init__` re-export list is untouched.

### 28.3 Line accounting (rule 3)

224 non-blank lines in the old `_format_stack_as_text`. **220 appear verbatim** in the
new code. The remaining **4 are accounted for** — both are `ruff format` re-wraps that
became possible when the dedent from 16 to 4 spaces freed horizontal room, with
identical tokens either side:

- `_render_rest(\n cap, {"tier", "capability_class", "role"}, lines, "    "\n)` (3 lines)
  → `_render_rest(cap, {"tier", "capability_class", "role"}, lines, "    ")` (1 line).
- `bits.append("holds "\n + ", ".join(\n _scalar_text(e) for e in _as_list(col["entities"])\n))`
  (4 lines) → the same expression on 3 lines.

**No statement line is unaccounted for.** Nothing was reordered: the twelve calls run in
the order the blocks ran, and the `render_references` → `_render_rest(ss, ...)` → footer
tail is unchanged.

### 28.4 Statement counts add up (rule 4)

Suite-wide statements **11878 → 11906, +28**: 14 new `def` lines + 12 new spine calls +
2 new nested-helper calls. Misses held at **893**, so no per-module floor moved.

### 28.5 Verification beyond the gate

- **`tests/test_renderer_goldens.py` passes unmodified** — 22 tests, including
  `TestStackRenderer`'s 5 against `render_stack_full.md`, `render_stack_minimal.md` and
  `render_stack_string_blocks.md`. The file does not appear in `git status`.
- No test file was edited anywhere (rule 2).
- `tests/test_layout_contract.py` and `tests/test_callback_co_presence.py` pass in the
  full run; 5a touches neither layouts nor callbacks, so the id snapshot and the
  92-callback registry are untouched by construction.
- The frozen Continue-to-Phaser footer string and every `**Header:**` literal moved
  verbatim or stayed in the spine; no string was re-flowed (rule 5).

### 28.6 Deferred / not acted on

- Nothing. 5a needed no `# noqa` — the four blocks that looked borderline
  (`languages`, `libraries`, `additional_decisions`, `project_structure`) all landed
  under C901 10 on the first cut.

### 28.7 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 171.13s` (exit 0) |
| Coverage | same run | `TOTAL 11906 stmts, 893 miss, 92%` |

## 29. Phase 5b — `_review_render.py`: four renderers decomposed into 23 helpers

`src/spec4/agents/code_scanner/_review_render.py`, plus a one-line docstring correction
in the package `__init__.py`. Extract-only. No other file changed.

### 29.1 Before and after

| Function | C901 | PLR0912 | PLR0915 | lines | → C901 | → lines |
|---|---:|---:|---:|---:|---:|---:|
| `_format_review_as_text` | **41** | **44** | **128** | 149 | 3 | 36 |
| `_render_typed_notes` | **21** | **23** | **57** | 62 | 1 | 7 |
| `_render_persistence` | **12** | — | — | 29 | 8 | 20 |
| `_render_deployment` | **11** | — | — | 47 | 4 | 13 |

The file's C901/PLR0912/PLR0915 finding count goes **9 → 0**. Largest function in the
file is now `_render_api_surface` (24 lines), which was already there and already clean.

### 29.2 The 23 helpers

**From `_format_review_as_text` (12).** The spine is now the `code_review` unwrap, the
not-a-software-project early return, the `**Code Review Complete**` header, the
`project_type` line, twenty calls and the frozen Continue-to-Brainstormer footer:
`_render_self_description`, `_render_architecture`,
`_render_languages_and_frameworks`, `_render_protocols`, `_render_runtime_versions`,
`_render_build_system`, `_render_dependencies`, `_render_commands`,
`_render_entrypoints`, `_render_directory_map`, `_render_ui_summary`, `_render_notes`.

**From `_render_persistence` (1).** `_database_parts(dbs) -> list[str]` — the
`engine (role)` loop, per 27.3. The `if db_parts:` guard and the `bits.append` stay in
the parent, because they are the parent's join, not the loop's.

**From `_render_deployment` (4).** `_deployment_container_bits`,
`_deployment_orchestration_bits`, `_deployment_paas_bits`, `_deployment_iac_bits` —
one per independent block, each taking `(deployment, bits)` and appending as before.

**From `_render_typed_notes` (6).** `_render_note_test_coverage`, `_render_note_ci_cd`,
`_render_note_dead_code`, `_render_note_change_risks`, `_render_note_security`,
`_render_note_other` — one per note type, per 27.3.

All twelve `_format_review_as_text` helpers and all six note helpers take
`(value, lines)`, the shape the file's seven pre-existing section renderers already use
(`_render_env_vars`, `_render_api_surface`, `_render_auth`, …), so the new code is
indistinguishable in shape from the old. `_render_languages_and_frameworks` is the one
exception, taking `(langs, frameworks, lines)` because its block reads two keys.

No name was added to `__all__`; the package re-exports only `_format_review_as_text`,
which keeps its name and signature.

### 29.3 Line accounting (rule 3)

| Function | old non-blank | verbatim | accounted otherwise |
|---|---:|---:|---:|
| `_format_review_as_text` | 149 | 136 | 13 |
| `_render_typed_notes` | 62 | 56 | 6 |
| `_render_persistence` | 29 | 29 | 0 |
| `_render_deployment` | 47 | 47 | 0 |

The 19 lines "accounted otherwise" are all the same single pattern: a block's opening
`x = <expr>` assignment folded into the call argument, which is what taking
`(value, lines)` rather than `(cr, lines)` means. **Every one of the 19 right-hand-side
expressions was checked to survive verbatim in the new file** — `cr.get("architecture")`,
`cr.get("dependencies", [])`, `notes.get("change_risks") or []` and so on, including the
`or []` defaults and the two-argument `cr.get(k, [])` forms. Nothing else changed:
no reorder, no changed conditional, no re-flowed string.

**No statement line is unaccounted for.**

### 29.4 Statement counts add up (rule 4)

Suite-wide statements **11906 → 11934, +28**: 23 new `def` lines + 23 new call
statements + 1 `return db_parts` − 19 folded assignments. Misses held at **893**.

### 29.5 Verification beyond the gate

- **`tests/test_renderer_goldens.py` passes unmodified** — 22 tests, `TestReviewRenderer`
  among them, against `render_review_full.md`, `render_review_strings.md`, the four
  `render_review_empty*.md`, `render_review_no_tests.md` and `render_review_skeleton.md`.
- No test file was edited (rule 2). 5b touches neither layouts nor callbacks, so the id
  snapshot and the 92-callback registry are untouched by construction; both suites pass
  in the full run.
- The frozen Continue-to-Brainstormer footer and every `**Header:**` literal moved
  verbatim or stayed in the spine (rule 5).

### 29.6 The one edit outside the target file

`src/spec4/agents/code_scanner/__init__.py` line 14 described `_review_render` as
holding "``_format_review_as_text`` and the seven section renderers". There are now 25.
Changed to "and its section renderers" — a count that cannot go stale again. Docstring
only; no code, no import, no `__all__` entry.

### 29.7 Deferred / not acted on

- Nothing. 5b needed no `# noqa`.

### 29.8 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 170.08s` (exit 0) |
| Coverage | same run | `TOTAL 11934 stmts, 893 miss, 93%` |

## 30. Phase 5c — `_format_vision_as_text` decomposed into 8 section renderers

`src/spec4/agents/brainstormer.py` only. Extract-only. No other file changed.

### 30.1 Before and after

| | C901 | PLR0912 | non-blank lines |
|---|---:|---:|---:|
| `_format_vision_as_text` before | **16** | **15** | 61 |
| `_format_vision_as_text` after | 2 | — | 18 |

The spine is now the `vision_statement` / `vision` unwrap (including the
`isinstance(raw_v, dict)` guard that keeps a string vision working), `lines = []`,
eight calls, `render_references` and the footer.

`brainstormer.py` still reports `run` at C901 20 / PLR0912 22 / PLR0915 79. That is
**5j's** target, untouched here (rule 7).

### 30.2 The 8 helpers, in call order

| Helper | Block | Lines |
|---|---|---:|
| `_render_vision_header(vs, lines)` | the `**Vision Statement**` heading | 6 |
| `_render_vision_purpose(raw_v, v, lines)` | bare-string vision, else `purpose` | 6 |
| `_render_ui_surface(v, lines)` | `ui_surface` | 4 |
| `_render_target_audience(v, lines)` | `target_audience` | 8 |
| `_render_key_features(v, lines)` | `key_features_mvp` | 8 |
| `_render_differentiators(v, lines)` | `differentiators` | 8 |
| `_render_future_enhancements(v, lines)` | `future_enhancements` | 8 |
| `_render_monetization(v, lines)` | `monetization`, string- or dict-shaped | 18 |

Seven take `(v, lines)` — `v` is the value every block reads, so this is the
`_render_x(value, lines)` shape the file already uses for `_render_feature_item` and
`render_references`. Two exceptions, both forced by what the block actually reads:
`_render_vision_header` takes `vs` (the name lives on the outer statement, not on `v`),
and `_render_vision_purpose` takes `(raw_v, v)` because its `isinstance(raw_v, str)`
branch is what makes a string-shaped vision render at all.

### 30.3 Line accounting (rule 3)

61 non-blank lines in the old `_format_vision_as_text`. **All 61 appear verbatim** in
the new code — no re-wrap, no folded assignment, nothing to explain. The eight calls run
in the order the eight blocks ran; `render_references` and `lines.append(footer)` are
still the last two statements of the spine.

### 30.4 Statement counts add up (rule 4)

Suite-wide statements **11934 → 11950, +16**: 8 new `def` lines + 8 new calls. Misses
held at **893**.

### 30.5 Verification beyond the gate

- **`tests/test_renderer_goldens.py` passes unmodified** — `TestVisionRenderer`'s four
  tests against `render_vision_full.md`, `render_vision_strings.md`,
  `render_vision_no_name.md` and `render_vision_review_footer.md`. The last of those
  drives the `footer` parameter, which the spine still threads to `lines.append(footer)`.
- No test file was edited (rule 2). Neither layouts nor callbacks are touched, so the id
  snapshot and the 92-callback registry are untouched by construction.
- `_VISION_TRANSITION` and every `**Header:**` literal moved verbatim (rule 5).

### 30.6 Deferred / not acted on

- `brainstormer.run` (C901 20 / PLR0912 22 / PLR0915 79, 227 lines) — **5j**.
- No `# noqa` was needed.

### 30.7 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 169.51s` (exit 0) |
| Coverage | same run | `TOTAL 11950 stmts, 893 miss, 93%` |

## 31. Phase 5d — `agentifier/_render.py`: `_field` promoted, the spec tail extracted

`src/spec4/agentifier/_render.py` only. Extract-only. Carries the first of the five
pre-approved `# noqa`s (27.4). No other file changed.

### 31.1 Before and after

| | C901 | PLR0912 | PLR0915 | non-blank lines |
|---|---:|---:|---:|---:|
| `_format_spec_as_text` before | **18** | — | **55** | 77 |
| `_format_spec_as_text` after | 1 | — | — | 32 |
| `_field` before (nested) | **12** | **13** | — | 27 |
| `_spec_field` after (module-level) | 12 `# noqa` | 13 `# noqa` | — | 28 |

The file's C901/PLR0912/PLR0915 finding count goes **4 → 0** (2 suppressed on
`_spec_field`, 2 removed). `_format_catalog_as_text`, the fifth golden-pinned renderer,
was already under every threshold and is unchanged.

### 31.2 What moved

**`_field` promoted to module scope as `_spec_field(spec, lines, label, key)`.** The
plan (27.3) proposed leaving it nested and suppressing it in place. That does not work:
ruff counts a nested `def` toward its enclosing function, so with `_field` still inside,
`_format_spec_as_text` stays at C901 ~13 even after its tail is extracted — and a second
`# noqa`, on the outer function, is not pre-approved. Promoting the closure is the only
route that keeps the suppression to the one function 27.4 sanctions. The captured
`spec` and `lines` become the first two parameters; the body is unchanged.

**Consequence for 27.4's wording.** The approved reason for this noqa reads "four-way
dispatch on JSON value shape, sharing a captured accumulator". The accumulator is now a
parameter, so the inline reason is narrowed to the half that is still true: *"four-way
dispatch on JSON value shape; each branch is that shape's rendering"*. Same function,
same two rules (C901, PLR0912), same argument — a `list` / `dict` / `None` / scalar
dispatch where each arm is that shape's rendering, so splitting it produces four helpers
that each take and return the same list.

**Tail extracted:** `_render_spec_mechanisms(spec, lines)` and
`_render_spec_references(spec, lines)`.

### 31.3 Line accounting (rule 3)

77 non-blank lines in the old `_format_spec_as_text`. **60 appear verbatim.** The 17
others are accounted for:

- **1** — `def _field(label: str, key: str) -> None:` became the module-level
  `def _spec_field(spec, lines, label, key) -> None:` carrying the noqa.
- **14** — the `_field("Label", "key")` calls became
  `_spec_field(spec, lines, "Label", "key")`. The 14 `(label, key)` pairs were extracted
  from both files and compared: **identical, and in the same order**. The D-PP2 comment
  about phase priority and the `# Tier-specific` marker sit between the same calls they
  sat between.
- **2** — the `# Mechanisms` and `# References` section comments folded into the two new
  helper docstrings, which is the disposition rule 3 names.

**No statement line is unaccounted for.**

### 31.4 Statement counts add up (rule 4)

Suite-wide statements **11950 → 11954, +4**: 2 new `def` lines + 2 new calls. The
promotion is statement-neutral — one `def` moved out, fourteen calls stayed fourteen
calls. Misses held at **893**.

### 31.5 Verification beyond the gate

- **`tests/test_renderer_goldens.py` passes unmodified** — `TestSpecRenderer` (2 tests,
  `render_spec.md` and `render_spec_tier_fallback.md`) and `TestCatalogRenderer` (3
  tests, `render_catalog.md` and `render_catalog_empty.md`).
- `_format_spec_as_text` keeps its name, its four-parameter signature and its position
  in `agentifier.py`'s import list (`agentifier.py:113`), so the caller at
  `agentifier.py:669` is untouched. `__all__` is unchanged; `_spec_field` is new and
  private and is not exported.
- No test file was edited (rule 2). Neither layouts nor callbacks are touched.

### 31.6 Deferred / not acted on

- Nothing else in this file is over threshold.

### 31.7 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 171.00s` (exit 0) |
| Coverage | same run | `TOTAL 11954 stmts, 893 miss, 93%` |

## 32. Phase 5e — `_phase_markdown.py`: the preamble and the phase body decomposed

`src/spec4/_phase_markdown.py` only. Extract-only. No other file changed. This is the
fifth golden-pinned surface — pinned through `project_manager`, not through
`test_renderer_goldens.py`.

### 32.1 Before and after

| | C901 | PLR0912 | PLR0915 | non-blank lines |
|---|---:|---:|---:|---:|
| `_phase_spec_preamble` before | **20** | **17** | **65** | 176 |
| `_phase_spec_preamble` after | 4 | — | — | 55 |
| `render_phase_markdown` before | — | — | **58** | 85 |
| `render_phase_markdown` after | — | — | 25 | 47 |

The file's C901/PLR0912/PLR0915 finding count goes **4 → 0**.

### 32.2 From `_phase_spec_preamble` (6)

| Helper | What |
|---|---|
| `_phase_declarations(phase)` | the two declaration arrays and the `legacy` era detection |
| `_product_spec_index(context)` | product feature specs from `context`, keyed by id |
| `_decl_heading(name, altitude, decl)` | **promoted**, not new — see below |
| `_product_feature_blocks(feature_decls, product_index)` | the D-PH5a blocks |
| `_ui_surface_blocks(context, declared_feature_ids, declared_capability_ids)` | the D-PH5b/c block |
| `_ai_capability_blocks(capability_decls, ai_index, declared_feature_ids)` | the AI-altitude blocks |

`_decl_heading` was a nested closure. As in 5d, ruff counts a nested `def` toward its
enclosing function, so it had to leave `_phase_spec_preamble` for the spine to come
under threshold. Unlike 5d's `_field`, it captured nothing — it already read only its
three parameters — so the promotion is a straight move with **no signature change and
no call-site change**.

The three block builders each open with the accumulator declaration the block already
had (`product_blocks: list[str] = []` and so on) and close with `return <that list>`;
the spine binds the result to the same name it used before. The two
`declared_*_ids` set comprehensions stay inline in the spine, verbatim — lifting the
two into one shared helper would be duplicate-removal, which is **5p's** call, not 5e's
(rule 7).

The spine keeps the 25-line docstring, the early `return []`, the `ai_index` lookup, the
two id comprehensions, three calls, the second `return []` guard, the
`## Feature Specifications` assembly and the D-PH5 `if ai_blocks:` cross-cutting gate.

### 32.3 From `render_phase_markdown` (5)

`_render_tech_stack_section`, `_render_instructions_section`, `_render_risk_section`,
`_render_verification_section`, `_render_references_section` — one per `##` heading, in
document order. The spine keeps `json.dumps` frontmatter assembly, the thirteen local
reads, the opening `lines` list (frontmatter fence, `# Phase N of M`, summary), the
`_phase_spec_preamble` extend, the five calls and the trailing
`"\n".join(lines).rstrip() + "\n"`.

Frontmatter shape and the `---` fences are untouched (rule 4).

### 32.4 Line accounting (rule 3)

| Function | old non-blank | verbatim | accounted otherwise |
|---|---:|---:|---:|
| `_phase_spec_preamble` | 176 | 173 | 3 |
| `render_phase_markdown` | 85 | 85 | 0 |

The three are the `# --- product feature blocks (D-PH5a) ---`,
`# --- UI surfaces block (D-PH5b/c) ---` and
`# --- AI capability blocks ... ---` banner comments, each folded into the docstring of
the helper cut at that banner — the disposition rule 3 names. Every other line,
including all seven D-PH/D-PS rationale comment blocks, is verbatim.

**No statement line is unaccounted for.**

### 32.5 Statement counts add up (rule 4)

The file's own statements **205 → 230, +25**, and the suite-wide total moved
**11954 → 11979, +25** — so **no other module's statement count changed**. By kind:

| Kind | Δ | Why |
|---|---:|---|
| `def` | +10 | 5 section renderers, 3 block builders, `_phase_declarations`, `_product_spec_index` (`_decl_heading` moved, so it is not new) |
| `return` | +5 | one per new value-returning helper |
| call statement | +5 | the five `_render_*_section(...)` calls |
| assignment | +5 | the five spine bindings that replaced inlined blocks |

Misses held at **893**.

### 32.6 Verification beyond the gate

- **`tests/test_project_manager_golden.py` passes unmodified** — 17 tests against
  `phase_full.md`, `phase_full_no_context.md`, `phase_minimal.md`, `phase_final.md`,
  `README.md` and `README_moved_footer.md`, including
  `test_frontmatter_round_trips_the_phase_verbatim` and
  `test_frontmatter_is_indented_json_with_unicode_kept`.
- `render_phase_markdown` and `parse_phase_markdown` keep their names and signatures;
  both importers (`project_manager.py:75`, `_artifacts.py:26`) are untouched.
- No test file was edited (rule 2). Neither layouts nor callbacks are touched.

### 32.7 Deferred / not acted on

- The two identical `{str(d.get("id")) for d in X if d.get("id")}` comprehensions in
  `_phase_spec_preamble` are left inline. Lifting them is duplicate-removal — **5p(a)**.
- No `# noqa` was needed.

### 32.8 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 169.22s` (exit 0) |
| Coverage | same run | `TOTAL 11979 stmts, 893 miss, 93%` |

## 33. Phase 5f — `agents/_feature_context.py`: seven consumer projections decomposed

`src/spec4/agents/_feature_context.py` only. Extract-only. First sub-phase to apply
rules 8 and 9, both of which were added to 27.2 because of what this file contains.

### 33.1 Before and after

| Function | C901 | Br | St | lines | → C901 | → lines |
|---|---:|---:|---:|---:|---:|---:|
| `project_feature_for_stack` | **16** | **15** | — | 71 | 3 | 27 |
| `ai_features_for_stack` | **11** | — | — | 97 | 6 | 70 |
| `ai_features_for_phaser` | **16** | **16** | **64** | 140 | 4 | 58 |
| `ai_features_for_deployer` | **20** | **19** | **61** | 112 | 2 | 40 |
| `ai_features_for_designer` | **23** | **18** | **69** | 106 | 6 | 33 |
| `feature_specs_for_stack` | **16** | **15** | — | 107 | 7 | 55 |
| `feature_specs_for_phaser` | **11** | — | — | 110 | 7 | 60 |

The file's C901/PLR0912/PLR0915 finding count goes **15 → 0**. Module-level functions
17 → 49; no nested `def` remains anywhere in the file.

### 33.2 The 32 new module-level functions

**From `project_feature_for_stack` (5):** `_stack_feature_header`,
`_stack_knowledge_source_lines`, `_stack_tool_access_lines`, `_stack_mechanism_lines`,
`_stack_quality_lines`.

**From `ai_features_for_stack` (2):** `_stack_infra_lines`, `_stack_cross_cutting_lines`.

**From `ai_features_for_phaser` (6):** `_phaser_revision_partition`,
`_phaser_established_lines`, `_phaser_index_table`, `_phaser_priority_guidance`,
`_phaser_shape_guidance`, `_phaser_catalog_notes`. The phasing-guidance block splits in
two — priority buckets (`steel_thread` / `mvp` / `v2`) and node shape
(`infrastructure` / `cross_feature`) — because all five buckets in one helper is C901 11.

**From `ai_features_for_deployer` (6):** `_deployer_provider_lines`,
`_deployer_provider_entry`, `_provider_roles_and_tiers`, `_deployer_tier_lines`,
`_deployer_budget_lines`, `_deployer_eval_lines`.

**From `ai_features_for_designer` (6):** `_designer_is_infra` and `_designer_edge_state`
(**promoted closures**, rule 8), `_designer_members_by_parent`,
`_designer_surface_lines`, `_designer_input_line`, `_designer_member_lines`.

**From `feature_specs_for_stack` (4):** `_stack_ai_served_ids`,
`_stack_feature_spec_lines`, `_stack_entity_vocabulary`, `_stack_nfr_lines`.

**From `feature_specs_for_phaser` (3):** `_phaser_feature_spec_lines`,
`_phaser_entity_vocabulary`, `_phaser_nfr_lines`.

### 33.3 Rule 8 applied — two closures promoted

`_is_infra` and `_edge_state` were nested in `ai_features_for_designer`. Both are
promoted to module level as `_designer_is_infra` and `_designer_edge_state`; both read
only their single `f` parameter, so nothing had to be threaded and no signature changed.
They are **renamed** on promotion because `_is_infra` / `_edge_state` are too generic at
module scope in a file that serves six different consumers. Three call sites move with
them (two for `_designer_is_infra`, one for `_designer_edge_state`), listed in 33.5.

### 33.4 Rule 9 applied — one `continue` → `return`

**Exactly one site.** Every loop in all seven functions was checked first with `ast`:
**no `break` anywhere, and no `return` inside any loop**, so rule 9's stop clause never
fires in this file. Of the seven `continue` statements, six sit in loops that move into a
helper *whole* (the loop header goes too), where `continue` stays valid and unmodified.
The seventh —

```
for name, prov in providers.items():
    if not isinstance(prov, dict):
        continue          # <- old ai_features_for_deployer:554
```

— is a loop-*body* guard, and the body became `_deployer_provider_entry`. It is now:

```
def _deployer_provider_entry(name: str, prov: Any, lines: list[str]) -> None:
    if not isinstance(prov, dict):
        return
```

Same position, same condition, same effect: skip this provider, continue with the next.
This is the one permitted statement rewrite; the file has no other.

### 33.5 Line accounting (rule 3)

**743 non-blank lines** across the seven functions. **735 appear verbatim.** The 8
others:

| # | Line | Disposition |
|---:|---|---|
| 2 | `def _is_infra(...)`, `def _edge_state(...)` | rule 8 promotions, renamed (33.3) |
| 3 | the `surfaces = [...]` comprehension, the `sub_feature` guard, `edge = _edge_state(f)` | the same rename at the three call sites |
| 3 | two `render_feature_block(...)` calls | `ruff format` re-wraps after the 4-space dedent; identical tokens |

The `continue` → `return` does not appear here: `continue` still occurs elsewhere in the
file, so the counter matches it. It is verified separately and quoted in full in 33.4.

**No statement line is unaccounted for.**

### 33.6 Statement counts add up (rule 4)

The file's own statements **533 → 597, +64**, and the suite-wide total moved
**11979 → 12043, +64** — so **no other module's statement count changed**. By kind:

| Kind | Δ | Why |
|---|---:|---|
| `def` | +30 | 32 new module-level functions, less the 2 closures that stopped being nested defs |
| call statement | +26 | the new spine calls |
| `return` | +5 | `_stack_ai_served_ids`, `_designer_members_by_parent`, `_phaser_revision_partition`, `_provider_roles_and_tiers`, and the rule-9 rewrite |
| assignment | +4 | the spine bindings that replaced inlined blocks |
| `continue` | −1 | the rule-9 rewrite |

Misses held at **893**.

### 33.7 Verification beyond the gate

- The seven public names, their signatures and their defaults are unchanged; every
  importer (`stack_advisor`, `phaser`, `deployer`, `designer`, `_stack_context`) is
  untouched and `__all__` is unchanged. All 32 new names are private and unexported.
- No test file was edited (rule 2). `tests/test_deployer_phases_context.py`,
  `test_phaser_feature_specs_context.py`, `test_deployer_ai_channel.py`,
  `test_deployer_nfr_channel.py`, `test_feature_specs_pass.py`,
  `test_deployer_stack_digest.py` and the greenfield pipeline integration test all pass
  unmodified in the full run.
- Every prompt-bound string — the StackAdvisor base-input header, the Phaser
  spine header and its `features`/`capabilities` declaration instruction, the
  `(AI)` and `(excluded)` tags, the D-PH1c citation rule — moved verbatim (rule 5).

### 33.8 Two failed attempts before this one

Recorded because the rules exist because of them.

1. **Syntax.** Helper bodies lifted out of `for` loops kept their 8-space nesting.
   Reverted with `git checkout --`.
2. **Ruff.** The dedent was right, but `continue` landed in a helper with no loop
   around it, and the two promoted closures were still called by their old names at
   three sites. Reverted; reported as a stop under the original run's retry budget.

Rules 8 and 9 were then added to 27.2 and this attempt applied them. Both defects are
now covered by a rule rather than by care.

### 33.9 Deferred / not acted on

- **`_stack_ai_served_ids` duplicates `ai_served_feature_ids`** (line 1002 of the old
  file), which `feature_specs_for_phaser` already calls. `feature_specs_for_stack` had
  the same logic inline; extracting it made the duplication explicit rather than
  removing it. Collapsing the two is **5p(a)**.
- The entity-collection loop (`for ent in f.get("entities") ...`) is identical in
  `feature_specs_for_stack` and `feature_specs_for_phaser` and is deliberately **left
  inline in both spines** — lifting it is duplicate-removal, **5p(a)**, not 5f's call
  (rule 7). Both spines stay under threshold with it inline.
- The seven per-consumer `_*_feature_spec_lines` / `_*_lines` helpers are now directly
  comparable for the first time. That comparison is **5p(a)**, per 27.3's instruction to
  extract all seven first and compare afterwards.
- No `# noqa` was needed.

### 33.10 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 175.34s` (exit 0) |
| Coverage | same run | `TOTAL 12043 stmts, 893 miss, 93%` |

## 34. Phase 5g — `agents/_stack_context.py`: four stack/manifest projections decomposed

`src/spec4/agents/_stack_context.py` only. Extract-only. No other file changed.

### 34.1 Before and after

| Function | C901 | Br | St | lines | → C901 | → lines |
|---|---:|---:|---:|---:|---:|---:|
| `stack_for_deployer` | **29** | **28** | **81** | 170 | 5 | 63 |
| `stack_digest_for_phaser` | **24** | **21** | **66** | 144 | 6 | 44 |
| `design_manifest_for_stack` | **17** | **17** | — | 88 | 8 | 33 |
| `manifest_for_phaser` | **11** | — | — | 81 | 2 | 30 |

The file's C901/PLR0912/PLR0915 finding count goes **12 → 0**. Module-level functions
10 → 35; no nested `def` remains.

### 34.2 The 25 new module-level functions

**From `stack_for_deployer` (10):** `_stack_field` (**promoted closure**, rule 8),
`_deployer_target_lines` + `_deployer_target_entry`, `_deployer_auth_lines` +
`_deployer_auth_entry`, `_deployer_integrations_note`, `_deployer_provisioning` +
`_provision_entry` + `_provision_extras`, `_deployer_roadmap_extras`.

The targets and auth blocks each split in two: the section header and its loop stay in
one helper, the per-entry body becomes another, because both were C901 12–14 as single
helpers. `_deployer_provisioning` returns the `(provision, roadmap)` pair the two
`if` blocks in the spine then render.

**From `design_manifest_for_stack` (4):** `_manifest_data_model_lines`,
`_manifest_written_and_read`, `_manifest_entity_access_lines`,
`_manifest_screen_shape_lines`.

**From `stack_digest_for_phaser` (7):** `_stack_backlinks` (**promoted closure**,
rule 8), `_digest_feature_backlinks`, `_digest_capability_backlinks`,
`_digest_nfr_lines`, `_digest_status_lines`, `_digest_exposure_lines`,
`_digest_negatives`.

**From `manifest_for_phaser` (4):** `_phaser_manifest_screens`,
`_phaser_manifest_surfaces`, `_phaser_manifest_reading_guide`,
`_phaser_manifest_entities`.

### 34.3 Rule 8 applied — two closures promoted

| Closure | Promoted to | Captured | Passed as |
|---|---|---|---|
| `_field(entry, key, label)` | `_stack_field(entry, key, label)` | nothing | — (signature unchanged) |
| `backlinks(field)` | `_stack_backlinks(entries, field)` | `entries` | first parameter, ahead of `field` |

`_stack_backlinks` takes `entries` first because that is the order the closure read them
— the captured value before the declared parameter, per rule 8. Six call sites move with
the two promotions (three `_field`, three `backlinks`), listed in 34.5.

### 34.4 Rule 9 applied — one `continue` → `return`

The `ast` audit again found **no `break` anywhere and no `return` inside any loop**, so
rule 9's stop clause did not fire. Eight of the nine `continue` statements sit in loops
that move into a helper whole and are unmodified. The ninth is the roadmap branch of the
persistence/infrastructure loop body, now `_provision_entry`:

```
if status in ROADMAP_STATUSES:
    roadmap.append(...)
    return          # was `continue` at old line 314
```

Same branch, same position, same effect: this entry is roadmap, record it and move to
the next. The two `continue`s guarding that loop (`if not isinstance(block, dict)`,
`if not isinstance(entry, dict)`) stay in `_deployer_provisioning`'s own loops,
untouched.

### 34.5 Line accounting (rule 3)

**483 non-blank lines** across the four functions. **473 appear verbatim.** The 10
others:

| # | Disposition |
|---:|---|
| 2 | `def _field(...)` and `def backlinks(...)` — the rule-8 promotions (34.3) |
| 6 | the six call sites those promotions renamed: three `_field(` → `_stack_field(`, three `backlinks(` → `_stack_backlinks(entries, ` |
| 2 | the roadmap `roadmap.append(...)` argument — `ruff format` joined two lines into one after the dedent freed room; identical tokens |

The `continue` → `return` is not in this count because `continue` still occurs elsewhere
in the file; it is verified separately and quoted in 34.4.

**No statement line is unaccounted for.**

### 34.6 Statement counts add up (rule 4)

File statements **354 → 402, +48**; suite-wide **12043 → 12091, +48** — **no other
module's statement count changed**. By kind:

| Kind | Δ | Why |
|---|---:|---|
| `def` | +23 | 25 new module-level functions, less the 2 that were already `def`s as closures |
| call statement | +21 | the new spine calls |
| `return` | +3 | `_manifest_written_and_read`, `_deployer_provisioning`, and the rule-9 rewrite |
| assignment | +2 | the two spine bindings that replaced inlined blocks |
| `continue` | −1 | the rule-9 rewrite |

Misses held at **893**.

### 34.7 Rule 10 — no in-place fixes were needed

**Zero of the allowed five.** The retry that produced this commit typed every extracted
helper's parameters from the narrowed type at the call site rather than from the
enclosing signature (rule 10's corollary), and mypy passed first time. The two places it
mattered:

- `_deployer_roadmap_extras(stack: dict[str, Any], ...)` — **not** `| None`. Its only
  call site is below `stack_for_deployer`'s
  `if not isinstance(stack, dict) or not stack: return ""`. This is the exact annotation
  that failed the previous attempt.
- `_stack_backlinks(entries: list[dict[str, Any]], ...)` and
  `_digest_status_lines(entries: ...)` — `entries` is `stack_signal_entries(stack)`,
  whose declared return is `list[dict[str, Any]]` (`stack_routing.py:83`), so the
  parameter is typed from that rather than left as `list[Any]`.

Where the enclosing signature's `| None` **is** still right it was kept:
`_phaser_manifest_screens` and `_phaser_manifest_entities` take
`manifest: dict[str, Any] | None`, because `manifest_for_phaser`'s guard narrows
`surfaces`, not `manifest`, and both bodies do their own `(manifest or {})`.

### 34.8 Verification beyond the gate

- All four public names, signatures and defaults unchanged; every importer (`deployer`,
  `phaser`, `stack_advisor`) untouched and `__all__` unchanged. All 25 new names are
  private and unexported.
- No test file was edited (rule 2). `tests/test_deployer_stack_digest.py`,
  `test_phaser_manifest_context.py`, `test_design_manifest.py`,
  `test_deployer_env_and_semantics.py`, `test_deployer_invariants.py` all pass
  unmodified in the full run.
- The two load-bearing absence statements — "the stack declares none … do not provision
  an identity provider" and the trustworthy-negatives block — moved verbatim (rule 5),
  as did every `**Header**` and the D-PH1c citation instruction.

### 34.9 One failed attempt before this one

Attempt 1: `_manifest_written_and_read`'s body was dedented by 8 where it needed 4
(the block sits inside `if surfaces:`, so it starts at 8, not 12) → syntax error.
Reverted with `git checkout --`. Attempt 2 failed mypy on the
`_deployer_roadmap_extras` annotation and was reverted and reported as a stop; rule 10
was then added, and this third attempt passed the whole gate without a fix.

### 34.10 Deferred / not acted on

- `_deployer_target_lines` / `_deployer_auth_lines` share the
  header-then-loop-then-blank shape with several 5f helpers. Comparing them is **5p(a)**.
- No `# noqa` was needed.

### 34.11 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 170.63s` (exit 0) |
| Coverage | same run | `TOTAL 12091 stmts, 893 miss, 93%` |

## 35. Phase 5h — `agents/` shared helpers: 8 modules, 10 functions

Eight files under `src/spec4/agents/`. Extract-only. Carries two of the five
pre-approved noqas (27.4). First sub-phase where rule 4's misses invariant actually
bit — see 35.6.

### 35.1 Before and after

| File | Function | C901 | Br | St | lines | → C901 | → lines |
|---|---|---:|---:|---:|---:|---:|---:|
| `_phase_coverage.py` | `check_phase_coverage` | **26** | **26** | **69** | 170 | 5 | 31 |
| `_manifest.py` | `validate_manifest` | **17** | **17** | — | 82 | 7 | 25 |
| `_turn_flow.py` | `build_revision_context` | **17** | **16** | — | 69 | 1 | 14 |
| `_reask.py` | `stream_suppressing_json` | **15** | **16** | — | 96 | 9 | 81 |
| `code_scanner/_scan.py` | `_gather_project_context` | **15** | **13** | — | 62 | 7 | 26 |
| `feature_speccer.py` | `_reconcile_dependencies` | **12** | — | — | 43 | 6 | 31 |
| `_seam_check.py` | `_check_table_provenance` | **11** | — | — | 50 | 1 | 7 |
| `stack_advisor/_stack_shape.py` | `_normalise_stack_shape` | **11** | — | — | 51 | 2 | 20 |
| `feature_speccer.py` | `_validate_dependencies` | **11** | — | — | 35 | **noqa** | 35 |
| `_reask.py` | `reask_for_artifact` | — | — | — | (10 args) | **noqa** | 48 |

All ten findings cleared: **8 decomposed, 2 suppressed** exactly as 27.3 called it.
31 new module-level helpers.

### 35.2 The 31 helpers

| From | Helpers |
|---|---|
| `check_phase_coverage` | `_capability_side_checks`, `_capability_presence`, `_capability_infra_ordering`, `_product_side_checks`, `_product_presence`, `_product_dependency_order` |
| `validate_manifest` | `_warn_catalog_coverage`, `_warn_vision_coverage`, `_warn_audience_validity`, `_repair_dangling_refs` |
| `build_revision_context` | `_revision_artifact_blocks`, `_revision_phase_blocks`, `_revision_design_blocks` |
| `stream_suppressing_json` | `_seed_stream_session`, `_record_received_chars`, `_publish_stream_status`, `_log_suppress_entry`, `_log_suppress_exit` |
| `_gather_project_context` | `_file_tree_lines`, `_manifest_file_lines`, `_is_test_path` (**promoted**), `_priority_source_files`, `_source_sample_lines` |
| `_normalise_stack_shape` | `_fold_library_categories`, `_listify_keyed_blocks`, `_key_listed_blocks`, `_key_ai_conventions` |
| `_check_table_provenance` | `_table_creators`, `_orphan_read_findings`, `_unread_table_findings` |
| `_reconcile_dependencies` | `_implied_producers` |

`check_phase_coverage`'s two banner-marked halves each split into a side-check plus its
presence and ordering passes. `_product_side_checks` takes
`(phases, spine, excluded, failures, advisories)` — five parameters, not six: the
`if spine and revision_version is None:` guard and the `excluded_feature_ids(...)` call
stay in the outer spine, which is what keeps the helper off PLR0913.

### 35.3 Rule 8 — one closure promoted

`_is_test` in `_gather_project_context` captured `root`, so it becomes
`_is_test_path(root, p)` with the captured value first, per rule 8. Its one call site
moves with it. `_validate_dependencies`'s nested `dfs` is **not** promoted: rule 8
applies to closures inside a *flagged* function being brought under threshold, and this
function is being suppressed instead — the noqa covers the nested `def` along with
everything else, which is precisely why the noqa is the right disposition here.

### 35.4 Rule 9 — no rewrites needed

The `ast` audit found one `break` (`_scan.py:224`, in the source-sample loop) and no
`return` inside any loop. Rule 9's stop clause did not fire: the loop containing the
`break` is extracted **whole** into `_source_sample_lines` — header and body together —
so the `break` is still inside its own loop and is unmodified. Every `continue` in all
ten functions likewise sits in a loop that moves whole. **Zero `continue` → `return`
rewrites in this sub-phase.**

### 35.5 Rule 10 — the noqas appended, not rewritten

Both pre-approved noqas were **appended to the existing `def` line**, per the fourth
mechanical class:

- `feature_speccer.py:368` — `def _validate_dependencies(features: ...) -> ...:` is a
  **single-line** signature; the noqa goes on the end of it. (Attempt 2 of the previous
  run replaced this line with a `def name(  # noqa: ...` opener and destroyed the
  parameter list. That is what the rule now forbids.)
- `_reask.py:75` — `def reask_for_artifact(` is a multi-line opener; the noqa goes on
  the opener.

Both files are under `src/spec4/agents/**`, which carries the E501 per-file-ignore, so
neither needed `E501` added to the noqa.

**In-place fixes used: 0 of 5.**

### 35.6 Rule 4 — a real miss regression, and what replaced it

The first passing build of this sub-phase moved suite-wide misses **893 → 894**. Every
other gate was green, so this would have been easy to wave through; it is exactly what
rule 4 exists to catch, so it was chased down instead.

**Cause.** `stream_suppressing_json`'s `except BaseException` block is never taken under
test. Extracting its DEV_MODE trace into `_log_suppress_exception` turned 4 missed
statements into 5: the helper's body statements stay missed *and* the new call statement
at the never-reached call site is missed too. Extraction is coverage-neutral on a
covered path and coverage-negative on a dead one.

**Resolution.** The except block was put back inline and two **covered-path** blocks
were extracted instead — `_log_suppress_entry` (the entry trace, whose `if DEV_MODE:`
runs on every call) and `_record_received_chars` (the per-chunk accounting, D-SC60).
Both are coverage-neutral: the call site and the helper's guard are executed, so the
only missed line is the `print` that was already missed. `stream_suppressing_json` lands
at C901 9 rather than the 10 the entry-trace extraction alone would have given.

Misses are back at **893**. This is worth remembering for 5i–5o: **when a function's
`if DEV_MODE:` / `except` / defensive branch is never executed under test, extracting it
costs a miss.** Prefer a covered-path block of equal complexity weight.

### 35.7 Line accounting (rule 3)

Line ranges were read with `awk '{printf "%d\t%s\n", NR, $0}'` this time, per rule 3 as
amended. **623 non-blank lines** across the ten functions; **616 verbatim.** The 7:

| # | Disposition |
|---:|---|
| 3 | the `# Coverage (approximate): vision MVP features …` comment block, folded into `_warn_vision_coverage`'s docstring (`vs = _unwrap_vision(vision)` moved to the spine, since the audience check needs it too) |
| 2 | `desired = (` and its ternary — `ruff format` rejoined them after the 8→4 dedent; identical tokens |
| 2 | `def _is_test(...)` and its one call site — the rule-8 promotion |

**No statement line is unaccounted for.**

### 35.8 Statement counts add up (rule 4)

Across the eight files: `def` +30, call statement +26, `return` +4, assignment +4 =
**+64**, and the suite-wide total moved **12091 → 12155, +64** — no other module
changed. Misses **893**, unchanged.

### 35.9 Verification beyond the gate

- Every public name, signature and default is unchanged; no importer edited; no `__all__`
  changed. All 31 new names are private.
- No test file edited (rule 2). `tests/test_streaming_characterization.py` passes
  unmodified — it is the pin on `stream_suppressing_json`, whose generator, its three
  `yield`s and its try/except/finally shape are untouched; only non-yielding blocks were
  lifted out.
- `tests/test_phase_coverage.py`, `test_manifest.py`, `test_seam_check*.py`,
  `test_dependency_reconciliation.py`, `test_feature_ids.py` all pass unmodified.

### 35.10 Two failed attempts before this one

1. **Range error.** `_orphan_read_findings` was given lines 220–246 when its block ends
   at 243, because the bounds were read off a listing renumbered from 1. It swallowed
   the opening of `read_keys = {` and produced ~90 syntax errors. Reverted; rule 3 now
   requires absolute line numbers.
2. **Signature destroyed.** The `_validate_dependencies` noqa was written as a `def`
   line replacement against a single-line signature. Reverted; rule 10 now requires
   appending.

This attempt built every file in memory and ran `ast.parse` on it **before writing**,
which caught two further indentation slips with nothing on disk to revert.

### 35.11 Deferred / not acted on

- `_stack_shape.py`'s four coercion helpers and `_manifest.py`'s four `_warn_*` helpers
  are structurally similar to blocks in 5f/5g. Comparison is **5p(a)**.
- No new `# noqa` beyond the two pre-approved.

### 35.12 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 176.34s` (exit 0) |
| Coverage | same run | `TOTAL 12155 stmts, 893 miss, 93%` |

## 36. Phase 5i — cut points for `phaser.run` and `deployer.run` (recorded before the edit)

Both are generators. The binding constraint is not complexity but `yield`: a block
containing one cannot leave the generator without becoming a sub-generator, which is a
structural change, not an extraction. So every cut below is a **yield-free** region, and
**every stream loop stays whole and in place** — `phaser`'s
`yield from llm.stream_turn(...)` and its validation-retry drain, `deployer`'s
`yield from stream_counting(...)`.

Structural audit first (`ast`): **no `break`, no `return` inside any loop, no nested
closure, no `try` block** in either function. Rules 8 and 9 therefore have nothing to do
here; rule 9's stop clause does not fire.

### 36.1 `phaser.run` — 84–576, C901 33 / PLR0912 37 / PLR0915 148, 472 lines

Yields at **135, 137** (staleness / resume prompts), **303** (the stream turn) and
**412** (the retry status line). Those four, and the two stream loops around them, stay.

| # | Helper | Old lines | What it is |
|---|---|---|---|
| P1 | `_phaser_round_flags(session)` | 100–129 | version pin, greenfield and revision gates → `(target_version, is_greenfield, is_revision)` |
| P2 | `_phaser_artifact_blocks(session)` | 149–189 | AI-features, spine, design-note and manifest blocks |
| P3 | `_phaser_vision_and_stack_blocks(...)` | 196–219 | vision block and stack digest |
| P4 | `_phaser_review_instruction(code_review, ...)` | 221–266 | the brownfield/greenfield `extra_block` + `instruction` pair |
| P5 | `_phaser_revision_instruction(...)` | 268–287 | the revision-round override of the same pair |
| P6 | `_phaser_seed_message(...)` | 140–294 | the parent that calls P2–P5 and returns `seed` |
| P7 | `_phaser_turn_additions(messages, pre_len)` | 324–352 | assistant-message cleanup → `(additions, last_text)` |
| P8 | `_phaser_retry_prompt(messages, failures, llm_config)` | 375–411 | truncation note, retry message, response format → `status_line` |
| P9 | `_phaser_retry_outcome(...)` | 443–508 | re-validate after the retry drain |
| P10 | `_phaser_persist_and_render(...)` | 511–561 | marker check, session writes, display assembly |
| P11 | `_phaser_json_recovery_note(...)` | 563–576 | the `elif not phases and "```json" in ...` recovery branch |

`messages.append({"role": "user", "content": seed})` (295) and the `else` at 297 stay in
the spine, as does the whole `if messages:` staleness block (132–138).

### 36.2 `deployer.run` — 548–961, C901 24 / PLR0912 30 / PLR0915 130, 398 lines

Yields at **610, 617, 622, 667, 804, 815, 860, 885, 933, 940** — ten, spread through
almost every branch, which is why deployer's cuts are smaller and more numerous than
phaser's.

| # | Helper | Old lines | What it is |
|---|---|---|---|
| D1 | `_deployer_readme_reply_intent(user_input)` | 569–600 | affirmative/negative word match on the pending-README reply |
| D2 | `_deployer_round_context(session)` | 626–663 | the eight session reads, `is_revision`, `greenfield` |
| D3 | `_deployer_context_blocks(...)` | 670–676 | stack, NFR, phases and existing-infra blocks |
| D4 | `_deployer_seed_message(...)` | 678–755 | existing-plan / revision / fresh seed assembly |
| D5 | `_deployer_plan_reply_intent(user_input)` | 762–793 | same word match, for the pending-plan reply |
| D6 | `_deployer_readme_optin_intent(user_input)` | 821–852 | same word match, for the README opt-in |
| D7 | `_deployer_readme_accept(...)` | 862–875 | the affirmative branch of the opt-in |
| D8 | `_deployer_plan_confirm(session, messages, last_text)` | 907–919 | confirm question, display override, session state |

**D1, D5 and D6 are the same ~30-line shape three times**, differing only in their word
lists. They are extracted as three separate helpers here and **not** unified: that is
duplicate-removal, which is 5p(a)'s call, not 5i's (rule 7). Recorded here so 5p finds
them without re-deriving.

### 36.3 Coverage plan (rule 4, covered-path preference)

Current misses in the two files: `phaser/__init__.py` 135–136, 349, 376, 465, 506, 559,
575; `deployer.py` 617–618 (378 is outside `run`).

Every planned cut is entered under test — the missed lines sit *inside* blocks whose
guard is executed, so each new call statement is on a covered path. The one to watch is
**P11**, whose branch may never be entered; if it is not, 5i reports **893 + 1** with
that site named, per the amended rule 4. Nothing here is suppressed with a noqa to avoid
a miss.

## 37. Phase 5i — `phaser.run` decomposed; `deployer.run` blocked and not attempted

Scope changed during the run. `phaser.run` is done and committed. **`deployer.run` was
found to be unreachable under extract-only** and is left exactly as it was — see 37.5,
which is the substantive finding of this sub-phase.

### 37.1 `phaser.run` — before and after

| | C901 | PLR0912 | PLR0915 | non-blank lines |
|---|---:|---:|---:|---:|
| before | **33** | **37** | **148** | 472 |
| after | 10 | — | — | 91 |

The file's C901/PLR0912/PLR0915 finding count goes **3 → 0**. 16 new module-level
helpers, matching 36.1's plan plus one (`_phaser_count_chunk`, added when the planned
set landed at C901 11 — see 37.3).

### 37.2 The 16 helpers

`_phaser_round_flags`, `_phaser_seed_message` and its four block builders
(`_phaser_artifact_blocks`, `_phaser_vision_and_stack_blocks`,
`_phaser_review_instruction`, `_phaser_revision_instruction`),
`_phaser_turn_additions`, `_phaser_validate`, `_phaser_retry_prompt`,
`_phaser_count_chunk`, `_phaser_retry_exhausted`, `_phaser_completion_marker`,
`_phaser_ready_display`, `_phaser_seam_advisory`, `_phaser_commit_phases`,
`_phaser_json_recovery_note`.

**Both stream loops stay whole and in place**, as instructed: the opening
`yield from llm.stream_turn(...)` and the validation-retry drain
`for _chunk in llm.stream_turn(...)`. All four yields stay in the generator.

### 37.3 Two deviations from 36.1's plan, both forced

1. **`_phaser_count_chunk` added.** The planned eleven cuts left `run` at C901 **11**.
   The retry drain's loop *body* (`if _chunk: _received += ...`) became a helper, which
   removes one branch and — per rule 9 — keeps the loop itself whole and in place. It is
   the same shape as 5h's `_record_received_chars` and is on a covered path.
2. **`_phaser_retry_outcome` was not extracted as planned.** Old lines 443–508 contain a
   `return` that exits the generator (508). Rule 9 forbids extracting a block containing
   such a return as a unit, so the block was split as rule 9 prescribes: the body of
   `if failures:` became `_phaser_retry_exhausted` and **the `return` stayed in the
   caller**. Old 443–454 is an exact re-run of 354–373 and now routes through the same
   `_phaser_validate` — see 37.4 on why that unification is in scope here.

### 37.4 One in-function unification, deliberately not deferred to 5p

Old 354–373 and 443–454 are the same twelve lines — extract, completeness-check,
coverage-check — differing only in whether they read `last_text` or
`last_assistant_text(messages)`. Both now call `_phaser_validate`.

This is a departure from 5f/5g, where similar duplicates were left inline for 5p(a).
The difference is that here it is **load-bearing**: leaving the second copy inline costs
two branches and puts `run` at C901 12, so the sub-phase cannot complete without it.
5p(a)'s remit is lifting duplication *across* modules and agents; collapsing two
identical blocks *inside the one function being decomposed* is the ordinary result of
extracting a repeated block. Recorded here so the distinction is on the record rather
than inferred.

### 37.5 `deployer.run` cannot reach threshold under extract-only

`deployer.run` is C901 24 / PLR0912 30 / PLR0915 130 over 398 lines, with **ten
`yield` sites** (610, 617, 622, 667, 804, 815, 860, 885, 933, 940). A block containing a
`yield` cannot leave a generator without becoming a sub-generator, which is a structural
change, not an extraction.

Two builds were measured, neither written to `src/`:

| Build | C901 | PLR0912 | PLR0915 |
|---|---:|---:|---:|
| the eight cuts planned in 36.2 | 21 | 25 | 88 |
| **maximal** — every remaining non-yield body extracted as well (11 helpers) | **21** | **25** | 79 |

**Extracting three further bodies moved statements 88 → 79 and complexity not at all.**
That is the finding: deployer's complexity is not in its block bodies but in its branch
*structure*, and every one of the 25 branches guards a `yield` or a `return`:

- the README opt-in gate (`if` / `elif` / `else` → reask), 3
- `if user_input is None:` / `else`, and inside it `if messages:` / `else`, 4
- the staleness and resume probes, 2
- the greenfield opt-in question, 1
- the pending-plan reply (`if` / `elif`), and the pending-README reply, 4
- the README decline and accept branches, 2
- the post-turn `if generating_readme:` / `elif "## Deployment Steps"`, 2
- plan-existed / else, and opt-in-done / else, and requested, 5

None of these can move. The available routes are (a) converting the yield-bearing
branches into sub-generators driven by `yield from`, which is a redesign of the turn
loop and well outside extract-only; or (b) a `# noqa`, which is not pre-approved for
this function and which rule 9 and 27.2 rule 6 both forbid inventing.

**So `deployer.py` is untouched by this commit** — not partially extracted, not
suppressed. It needs a decision, and that decision belongs to a person.

### 37.6 Line accounting (rule 3)

472 non-blank lines in the old `phaser.run`. **456 verbatim.** The 16:

| # | Disposition |
|---:|---|
| 11 | old 443–454, the duplicate validate/completeness/coverage block, now routed through `_phaser_validate` (37.4) |
| 3 | `if _chunk:` and its two body lines, now `_phaser_count_chunk`'s body under the parameter names `chunk` / `received` |
| 2 | `extra_block = (` and its f-string continuation — `ruff format` joined them after the dedent; identical tokens |

**No statement line is unaccounted for.** One defect was found by this pass and fixed
before commit: the six-line rationale comment above the version pin (old 100–105) had
been dropped rather than moved. It is now the opening comment of
`_phaser_round_flags`'s body, verbatim.

### 37.7 Statement counts add up (rule 4)

Suite-wide **12155 → 12193, +38**: `def` +16, `return` +12, call statement +4,
assignment +8, less the 2 statements removed by the 37.4 unification. Misses held at
**893** — the covered-path preference was respected: every extraction site is executed
under test, so **no 893 + N reporting is needed for this sub-phase**.

### 37.8 Verification beyond the gate

- `run` keeps its name, its three-parameter signature and its `Generator[str, None, None]`
  return type; the four yields and both stream loops are in their original order.
- No test file edited (rule 2). `tests/test_streaming_characterization.py`,
  `test_fast_forward.py`, `test_phase_coverage.py` and
  `tests/integration/test_pipeline_greenfield.py` all pass unmodified.
- Every prompt string — the vision-supersession framing (D-PH7a), the code-review
  guidance, the revision instruction, the retry status line, the phases-ready message —
  moved verbatim (rule 5).

### 37.9 Rules 10 and 11 in this sub-phase

- **Rule 11 earned its place.** Three separate build errors were caught by the in-memory
  `ast.parse` with nothing written to disk: a spine that dropped the `if` line above a
  call, a helper body cut across an `else:` at line 916, and a bad range at 568.
  None reached the gate and none counted as an attempt.
- **Rule 11's limit, worth recording.** One error it *cannot* catch: six helper bodies
  were dedented to column 0, which is valid module-level Python and parses fine. It was
  caught by `ruff` (F821 × 35) after writing, and the file was reverted and rebuilt with
  the dedent **computed** from the block's own minimum indentation rather than assumed.
  That fix is now in the build method, not in a rule.
- **Rule 10 in-place fixes used: 0 of 5.**

### 37.10 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 170.98s` (exit 0) |
| Coverage | same run | `TOTAL 12193 stmts, 893 miss, 93%` |

## 38. Phase 5i (continued) — `deployer.run`: eight cuts landed, rule-12 noqa applied

Follows the 37.5 measurement and the rule-12 decision. `src/spec4/agents/deployer.py`
only.

### 38.1 What landed

The **eight cuts planned in 36.2**, not the maximal build — rule 12's disposition when
the maximal build does not reduce C901:

`_deployer_readme_reply_intent`, `_deployer_seed_context`, `_deployer_seed_message`,
`_deployer_plan_reply_intent`, `_deployer_readme_optin_intent`,
`_deployer_readme_accept`, `_deployer_plan_confirm` — seven helpers (36.2's D3 folded
into `_deployer_seed_message`, which reads the four context blocks itself).

`run` goes from **398 non-blank lines to 173**. Its C901 24 / PLR0912 30 / PLR0915 130
are suppressed by the sixth pre-approved noqa (27.4), appended to the existing `def`
line per rule 10:

```
def run(  # noqa: C901, PLR0912, PLR0915  # ten-yield generator; every remaining branch
guards a yield or a generator return, so further extraction needs sub-generators (backlog)
```

`agents/**` carries the E501 per-file-ignore, so no `E501` was needed on the noqa.

### 38.2 The measurement, restated for the record (rule 12)

| Build | C901 | PLR0912 | PLR0915 | Disposition |
|---|---:|---:|---:|---|
| planned (36.2's eight cuts) | 21 | 25 | 88 | **landed**, then suppressed |
| maximal (every remaining non-yield body, 11 helpers) | 21 | 25 | 79 | measured only, discarded |

The maximal build's three extra helpers (`_deployer_plan_saved`, `_deployer_plan_kept`,
`_deployer_trailing_readme_offer`) bought 9 statements and **zero** complexity. Landing
them would have added three helpers to a function that stays suppressed either way.

`deployer.run` is now on the backlog entry for the `yield from` sub-generator
conversion (27.4).

### 38.3 Duplication surfaced, not removed

`_deployer_readme_reply_intent`, `_deployer_plan_reply_intent` and
`_deployer_readme_optin_intent` are the **same ~30-line shape three times**, differing
only in their word lists. Extracted separately here, per rule 7; unifying them is
**5p(a)**. This is the clearest duplicate the phase has surfaced so far.

### 38.4 Line accounting (rule 3)

398 non-blank lines in the old `deployer.run`. **386 verbatim.** The 12:

| # | Disposition |
|---:|---|
| 10 | `ruff format` re-wraps after the dedent — the `ai_features_for_deployer(...)` ternary, the two `load_deployment_plan` / `load_prior_deployment_plan` calls and the `load_existing_readme` ternary each collapsed onto one line; identical tokens, verified at deployer.py:813, 828 and 984 |
| 1 | `def run(` — now carries the noqa (rule 10: appended, not rewritten) |
| 1 | `messages.append({"role": "user", "content": seed})` — now the same append with `_deployer_seed_message(session, is_revision)` as the content expression |

**No statement line is unaccounted for.**

### 38.5 Statement counts and coverage (rule 4)

Suite-wide **12193 → 12214, +21**: 7 new `def`s, 7 new call/assignment sites, 7 new
`return`s. Misses held at **893** — every cut is on a covered path, so no `893 + N`
reporting is needed.

### 38.6 One failed attempt

`_deployer_seed_context` was built from lines 631–633 when it needs only 631 and 633;
line 632 (`feature_specs = session.get("feature_specs")`) is used by
`_deployer_seed_message`, not by the context helper, and ruff caught it as F841. Reverted
with `git checkout --` and rebuilt with the range split. Rule 10's four classes do not
cover an unused-read, so this went through the ordinary revert-and-retry.

### 38.7 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 175.31s` (exit 0) |
| Coverage | same run | `TOTAL 12214 stmts, 893 miss, 93%` |

## 39. Phase 5j — `agents/` orchestrators II: four files, 21 helpers, two functions left over threshold

`designer.py`, `brainstormer.py`, `stack_advisor/__init__.py`,
`code_scanner/__init__.py`. Extract-only. Rule 12 applied to all four `run`-shaped
functions; **it resolved two of them and left two unresolved** — see 39.5, which is the
finding.

### 39.1 Before and after

| File | Function | C901 | Br | St | → C901 | → Br | → St |
|---|---|---:|---:|---:|---:|---:|---:|
| `designer.py` | `build_mock_prompt` | **16** | **16** | — | **clear** | — | — |
| `designer.py` | `generate_mock_streaming` | **22** | **21** | **65** | **clear** | **clear** | **clear** |
| `stack_advisor/__init__.py` | `run` | **12** | **14** | **59** | **clear** | **clear** | **clear** |
| `code_scanner/__init__.py` | `run` | **14** | **16** | **71** | 12 | 13 | 59 |
| `brainstormer.py` | `run` | **20** | **22** | **79** | 14 | 16 | **clear** |

21 new module-level helpers: 8 in `designer.py`, 7 in `brainstormer.py`, 4 in
`code_scanner`, 2 in `stack_advisor`.

### 39.2 Rule 12 measurements

| Function | planned | maximal | Disposition |
|---|---|---|---|
| `generate_mock_streaming` | C901 16 | **C901 clear** | maximal reduces → **maximal landed** |
| `code_scanner.run` | C901 12 / Br 13 / St 59 | C901 12 / Br 13 / St 57 | maximal buys 2 statements, no complexity → **planned landed** |
| `brainstormer.run` | C901 14 | (planned is maximal) | **landed**, still over |
| `stack_advisor.run` | clear on the planned two cuts | not needed | **planned landed** |

`generate_mock_streaming` is the case rule 12 was written to catch going the *other*
way: its `while True:` retry loop looked yield-bound, but extracting the streamed
tool-call accumulator (`_designer_accumulate_tool_calls`, 12 lines, 7 branches) took it
from C901 16 to clear. Measuring beat assuming.

### 39.3 The 21 helpers

**`designer.py` (8).** `build_mock_prompt` → `_mock_existing_html_part`,
`_mock_planning_parts`, `_mock_preference_and_screenshots`, `_mock_source_snippets`,
`_mock_manifest_text`. `generate_mock_streaming` → `_designer_llm_config`,
`_designer_accumulate_tool_calls`, `_designer_tool_call_followup`.

**`brainstormer.py` (7).** `_brainstormer_seed_context`, the three seed arms
(`_brainstormer_seed_from_vision`, `_brainstormer_seed_from_prior`,
`_brainstormer_seed_from_review`), `_brainstormer_review_text`,
`_brainstormer_reask_abandoned`, `_brainstormer_commit`.

**`stack_advisor` (2).** `_stack_seed_message` (119 lines of seed assembly, entirely
yield-free), `_stack_commit`.

**`code_scanner` (4).** `_scanner_seed`, `_scanner_retry_prompt`,
`_scanner_reask_failed`, `_scanner_commit`.

Both `designer.py` PLR0913 signatures (13 and 6 arguments) carry the pre-approved arity
noqa from 27.4, appended to the existing `def` line per rule 10.

Rule 9: `generate_mock_streaming`'s `while True:` keeps its `break`, and the
`continue` at the end of the tool-call branch stays in the caller's loop — the helper
holds only the yield-free body above it. **No `continue` → `return` rewrite in 5j.**

### 39.4 Coverage: 893 + 2 (rule 4, permitted case)

| Site | Block it calls |
|---|---|
| `agents/designer.py:738` | `_designer_accumulate_tool_calls(...)`, inside `if tc_deltas:` |
| `agents/designer.py:747` | `_designer_tool_call_followup(...)`, inside `if tool_call_acc:` |

Both are **call statements at never-executed sites** — the two tool-call branches of the
mock-generation stream are not exercised by the suite. That is exactly the case the
amended rule 4 permits: the helper bodies were already missed, and the only new miss is
the call statement. No other miss moved. The Phase 6 report re-baselines.

Neither extraction was avoidable by preferring a covered-path block: they are the two
that take `generate_mock_streaming` under threshold, and rule 4 explicitly forbids
reaching for a noqa to dodge the count.

### 39.5 Two functions remain over threshold, and rule 12 does not cover them

| Function | after | why it is stuck |
|---|---|---|
| `brainstormer.run` | C901 14 / Br 16 | 4-arm seed chain whose `else` yields a greeting and returns; 5 guards that each front a yield+return |
| `code_scanner.run` | C901 12 / Br 13 / St 59 | 4 guards fronting yield+return, plus a scan narration of interleaved yields with almost no extractable block between them |

Rule 12 grants its noqa only when **both** conditions hold: the maximal build does not
reduce C901 **and** every remaining branch guards a `yield` or a generator `return`.

- `brainstormer.run` fails the second condition: `if "brainstormer_messages" not in
  session:`, the three seed arms and the final `if vision:` guard no yield.
- `code_scanner.run` fails the second condition too, for the same kind of branch, and
  its maximal build does not reduce C901 either.

So neither gets a noqa, and neither reaches threshold. **This matters for 5p**: the
permanent ruff config is still `select = ["E", "F"]`, so C901 is not in the gate today —
which is why `uv run ruff check src/ tests/` passes with both functions at 12 and 14.
**The moment 5p promotes `C90` and `PLR`, these two fail.** 5p cannot complete without a
decision on them.

Three options, recorded here rather than chosen unilaterally: extend rule 12's second
condition to "every remaining branch guards a yield, a generator return, **or is an
entry guard on a generator turn**"; grant these two functions the same noqa explicitly
as 27.4 entries seven and eight; or convert both to sub-generators under the existing
backlog entry alongside `deployer.run`.

### 39.6 Line accounting (rule 3)

**856 non-blank lines** across the five functions; **831 verbatim**; 25 accounted:

| Function | nb | verbatim | other |
|---|---:|---:|---:|
| `build_mock_prompt` | 96 | 95 | 1 — the `def` line, now carrying the arity noqa |
| `generate_mock_streaming` | 139 | 138 | 1 — same |
| `brainstormer.run` | 227 | 210 | 17 |
| `stack_advisor.run` | 208 | 202 | 6 |
| `code_scanner.run` | 186 | 186 | 0 |

`brainstormer.run`'s 17: the `vision`/`prior_vision`/`code_review`/`code_review_block`
reads now returned as a tuple from `_brainstormer_seed_context` and unpacked at the call
site (4 + the unpack), the three seed-arm bodies' call lines, and `ruff format` re-wraps
of the `msgs.append(...)` calls after dedent. `stack_advisor.run`'s 6: the
`messages.append({"role": "user", "content": seed})` line, now taking
`_stack_seed_message(session)` as its content expression, plus five re-wraps.

**No statement line is unaccounted for.**

### 39.7 Statement counts (rule 4)

Suite-wide **12214 → 12263, +49**: 21 new `def`s, 21 new call/assignment sites, 7 new
`return`s. Misses **895 = 893 + 2**, both accounted in 39.4.

### 39.8 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 171.62s` (exit 0) |
| Coverage | same run | `TOTAL 12263 stmts, 895 miss, 93%` |

## 40. Phase 5j (continued) — rule 12 amended; `brainstormer.run` and `code_scanner.run` granted

### 40.1 The required maximal-build measurement

Rule 12 as amended requires the maximal build **before** the noqa. For both functions the
maximal build **is** the landed build — there is nothing left to extract:

| Function | landed | maximal | what remains |
|---|---|---|---|
| `brainstormer.run` | C901 14 / Br 16 | C901 14 / Br 16 | `if vision is None and suppressed_as_artifact(...)` (holds a `yield from`), and three single statements |
| `code_scanner.run` | C901 12 / Br 13 / St 59 | C901 12 / Br 13 / St 59 | `if review is None and not errors and suppressed_as_artifact(...)`, whose body is one `errors = [...]` assignment behind a comment |

Extracting either removes **zero** branches. Both were inspected statement by statement
after 5j's cuts; no block with a body of its own survives.

### 40.2 Branch classification (what the reasons name)

**`brainstormer.run` — 5 yield/return guards, 9 entry guards.**
Yield/return: the staleness question, the resume summary, the seed chain's greeting arm,
the review-request reply, the artifact re-ask. Entry guards with no extractable body:
`if "brainstormer_messages" not in session:`, `if user_input is None:` / `else`,
`if msgs:` / `else`, the four-arm seed selection, the review-request gate, and the two
artifact-present checks (`if vision is None:`, `if vision:`).

**`code_scanner.run` — 5 yield/return guards, 7 entry guards.**
Yield/return: staleness, resume, the re-entry gate, the missing-working-dir exit, the
schema-retry re-ask. Entry guards: `if "code_scanner_messages" not in session:`,
`if user_input is None:` / `else`, `if msgs:` / `else`, and the three artifact-present
checks.

### 40.3 What this closes

`src/spec4/agents/**` is now **entirely clean** for C90 / PLR0912 / PLR0913 / PLR0915 —
every finding either decomposed or carrying one of the eight pre-approved noqas. 5p can
promote `C90` and `PLR` without tripping on `agents/`.

All three granted generators (`deployer.run`, `brainstormer.run`, `code_scanner.run`)
are on the sub-generator backlog entry in 27.4. `stack_advisor.run` and
`designer.generate_mock_streaming` cleared under extraction and are **not** on it — the
same shape does not always reach the same verdict, which is why rule 12 requires the
measurement rather than a judgment call.

### 40.4 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 -q` | `4256 passed, 1 skipped` (exit 0) |

## 41. Phase 5k — `agentifier/agentifier.py`: the three phase runners

Extract-only. Nine new helpers. Two rule-12 grants (27.4 entries nine and ten), one
function cleared outright.

### 41.1 Before and after

| Function | C901 | Br | St | lines | → C901 | → Br | → St |
|---|---:|---:|---:|---:|---:|---:|---:|
| `_run_catalog_phase` | **38** | **41** | **230** | 621 | 33 **noqa** | 35 **noqa** | 171 **noqa** |
| `_run_cross_cutting_phase` | **13** | **14** | **83** | 145 | 12 **noqa** | 13 **noqa** | 68 **noqa** |
| `_handle_cc_ff_review` | — | — | **54** | 91 | — | — | **clear** |

The file's finding count goes **7 → 0** (6 suppressed on two functions, 1 cleared).

### 41.2 Rule 12 measurements

| Function | planned | maximal | Disposition |
|---|---|---|---|
| `_run_catalog_phase` | C901 33 / Br 35 / St 171 | C901 **33** / Br 35 / St 164 | maximal buys 7 statements, no complexity → **planned landed**, noqa |
| `_run_cross_cutting_phase` | C901 12 / Br 13 / St 68 | C901 **12** / Br 13 / St 68 | maximal buys nothing → **planned landed**, noqa |
| `_handle_cc_ff_review` | St clear on one cut | not needed | **planned landed**, no noqa |

`_run_catalog_phase` went 38 → 33 on four large yield-free extractions
(`_catalog_scout_prep` 73 lines, `_catalog_breadth_intro` 47, `_catalog_apply_selection`
40, `_catalog_finalize_breadth` 18) and 230 → 171 statements. The maximal build added a
fifth (`_catalog_commit`) and moved C901 not at all. **At 24 yields it is the most
yield-dense function in the repo** — every one of its 35 surviving branches either
fronts a sub-agent turn that yields a banner and drains a stream, or is an entry guard
choosing which turn body runs.

### 41.3 The nine helpers

**`_run_catalog_phase` (4).** `_catalog_scout_prep` (revision scope, project name, Scout
banner, retry guidance), `_catalog_breadth_intro` (record the composed pool, build the
breadth-selection intro), `_catalog_apply_selection` (close the developer's selection
over the pool and split it), `_catalog_finalize_breadth` (persist analysed candidates,
append the seed).

**`_run_cross_cutting_phase` (4).** `_cc_store_analysis`, `_cc_record_decision`,
`_cc_revise_input`, `_cc_apply_revision`.

**`_handle_cc_ff_review` (1).** `_cc_ff_prepare` — the working copies of the analysis and
decisions plus the pattern inputs. One cut took it under PLR0915.

The plan (27.3) proposed `_catalog_step_<n>_<name>` per banner comment, with a
tuple-or-dataclass decision for the locals crossing each boundary. **Neither was needed
and no state object was built**: the function has no banner comments, and the four cuts
that mattered are the yield-free spans *between* the sub-agent turns, each returning two
to five values as a plain tuple. Rule 12's dataclass tripwire never fired.

### 41.4 Coverage: 893 + 3 (rule 4, permitted case)

One new site in 5k, bringing the running total to three:

| Site | Block it calls |
|---|---|
| `agents/designer.py:738` | `_designer_accumulate_tool_calls(...)` (5j) |
| `agents/designer.py:747` | `_designer_tool_call_followup(...)` (5j) |
| `agentifier/agentifier.py:1315` | `_cc_store_analysis(...)`, inside the `if analysis is None:` first-pass branch |

All three are **call statements at never-executed sites**. No other miss moved.

### 41.5 Line accounting (rule 3)

**857 non-blank lines** across the three functions; **848 verbatim**; 9 accounted: the
two `def` lines now carrying noqas, and seven `ruff format` re-wraps after dedent (the
`_guidance_notes` comprehension, the `_analyses_to_dicts(...)` call, and the
`decisions[current_topic]` ternary). **No statement line is unaccounted for.**

### 41.6 Statement counts (rule 4)

Suite-wide **12263 → 12288, +25**: 9 new `def`s, 9 call/assignment sites, 7 `return`s.

### 41.7 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 172.38s` (exit 0) |
| Coverage | same run | `TOTAL 12288 stmts, 896 miss (893 + 3), 93%` |

## 42. Phase 5l — `agentifier/` siblings: 7 modules, 19 helpers, 3 noqas

Extract-only. All ten 27.3 findings cleared — **7 decomposed, 3 suppressed** with the
pre-approved noqas. `src/spec4/agentifier/**` is now entirely clean for
C90 / PLR0912 / PLR0913 / PLR0915.

### 42.1 Before and after

| File | Function | C901 | Br | → |
|---|---|---:|---:|---|
| `pattern_loader.py` | `_validate_frontmatter` | **17** | **17** | **noqa** |
| `composer.py` | `run` | **15** | **15** | clear |
| `grounding.py` | `render_grounding_for_prompt` | **14** | **13** | clear |
| `_seed.py` | `_build_seed_message` | **13** | **14** | clear |
| `linker.py` | `_normalize_edges` | **13** | — | clear |
| `requires_reconciler.py` | `directional_signals` | **13** | **14** | clear |
| `panel_closure.py` | `close_selection` | **12** | — | clear |
| `requires_reconciler.py` | `reconcile_requires` | **11** | — | clear |
| `requires_reconciler.py` | `_has_cycle` | **11** | — | **noqa** |
| `_seed.py` | `_call_scout` | — | (7 args) | **noqa** |

### 42.2 The 19 helpers

`linker.py` (4) — one per contract pass named in the docstring:
`_clear_self_and_dangling_labels`, `_valid_requires_targets`, `_clean_requires_edges`,
`_normalize_scope`, with `_break_requires_cycles` (already a function) called between
them. The spine is now five named passes in the order the docstring lists them.

`requires_reconciler.py` (5) — `_s1_signals` / `_s2_signals` (the two documented signal
families), `_reconcile_inputs`, `_inversion_candidates`, `_records_from_candidates`.

`panel_closure.py` (2) — `_apply_requires_closure` and `_apply_coordinator_toggle`,
each returning whether it changed anything; the `while changed:` fixpoint loop stays.

`composer.py` (3) — `_insert_synthesized_heads`, `_derive_final_scope`, `_log_composer`.

`_seed.py` (3) — `_seed_mode_note`, `_candidate_head_lines`,
`_candidate_analysis_lines`. The per-candidate block splits in two because one helper
would need six parameters.

`grounding.py` (2) — `_served_feature_lines` and `_served_feature_detail`; one was not
enough (C901 12 on the first cut).

### 42.3 Rule 9

`directional_signals`'s three `break`s stay inside the loops that carry them —
both S1b's input scan and S2's two producer scans move into their helpers **whole**.
`grounding.py`'s loop-body `continue` became a `return` in `_served_feature_lines`
(the one rewrite in 5l); `_clean_requires_edges` keeps its two `continue`s because the
loop moved with them.

### 42.4 Rule 10 — two in-place fixes (of five)

Both are the annotation class, both named exactly by mypy, both annotation-only:

| # | Site | Fix |
|---:|---|---|
| 1 | `requires_reconciler.py` `_reconcile_inputs` **return** type | `dict[str, str]` → `dict[str, str] | None` for `prod_map` |
| 2 | `requires_reconciler.py` `_inversion_candidates` `prod_map` parameter | same, propagated from (1) |

**Note for the rule's wording:** class 2 says "a helper *parameter* annotation". Fix 1 is
a **return** annotation. It is the same defect — a declared type that does not match the
actual — and the repair touched nothing else, so it was taken as covered. Tighten or
broaden the class's wording as preferred.

### 42.5 Rule 11 earned its extension immediately

The extended rule (build in memory → `ast.parse` → scratch copy → `ruff check`) caught
**one real defect before anything reached `src/`**: `_s2_signals` at six parameters
(PLR0913). It was fixed by moving `producer_id`'s computation into the helper, which is
where it belongs now that nothing else uses it. Under the old rule that would have been
an attempt.

### 42.6 A finding for 5p: `PLR` is wider than Phase 5 measured

The probe's initial selector was `PLR`, which surfaced nine **PLR2004**
(magic-value-comparison) in these three files — all **pre-existing**, confirmed against
`HEAD`. Phase 0 and 27.1 only ever measured `PLR0912`, `PLR0913` and `PLR0915`.

Repo-wide `--select PLR` today:

| Rule | Count | In Phase 5's scope? |
|---|---:|---|
| PLR2004 magic-value-comparison | **49** | **no** |
| PLR0912 too-many-branches | 12 | yes |
| PLR0913 too-many-arguments | 9 | yes |
| PLR0911 too-many-return-statements | **7** | **no** |
| PLR0915 too-many-statements | 4 | yes |
| PLR1714 repeated-equality-comparison | **1** | **no** |

**27.5(g) as written promotes `"PLR"` wholesale, which would add 57 unmeasured findings
to the gate on 5p's first run.** Either promote the three measured rules by name
(`PLR0912`, `PLR0913`, `PLR0915`), or promote `PLR` and handle the 57 — PLR2004 in
particular overlaps 5p(b)'s magic-strings work and might be folded into it deliberately.
Flagged now rather than discovered at 5p.

### 42.7 Line accounting (rule 3)

**646 non-blank lines** across the ten functions; **639 verbatim**; 7 accounted: the
three `def` lines now carrying noqas, and four in `close_selection` where the two rule
bodies' `changed = True` assignments became the helpers' return values, folded into
`changed = _apply_x(...) or changed` at the call sites. **No statement line is
unaccounted for.**

### 42.8 Statement counts and coverage (rule 4)

Suite-wide **12288 → 12338, +50**. Misses **896 = 893 + 3**, unchanged — every 5l
extraction site is on a covered path.

### 42.9 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 170.89s` (exit 0) |
| Coverage | same run | `TOTAL 12338 stmts, 896 miss (893 + 3), 93%` |

## 43. Source-text assertions in `tests/` (Phase 6 layout-coupling item)

Swept before 5n and 5o, per the rule-2 exception. Every test that reads source as text
or inspects it structurally, and whether decomposition can break it.

| Test | What it reads | Survives decomposition? |
|---|---|---|
| `test_designer.py:999` | `inspect.getsource(_start_gen)`, asserts `"_persist_manifest(" in src` | **No** — the only fatal one. Rewritten at 5m (44.4). |
| `test_agent_llm_selection.py:526` | every `src/spec4/**/*.py`, regex `agent_name=["'](...)["']` | **Yes** — the literals move with the code, and the sweep is repo-wide |
| `test_setup_wizard_register.py:200` | every `callbacks/**/*.py`, `ast.parse` for `@callback` decorators carrying `Input(...)` | **Yes** — decorators stay on the callback; extraction moves bodies, not decorators |
| `test_deployer_invariants.py:43` | `deployer.__file__` as text | **Yes in practice** — it asserts on prompt strings, which move verbatim; passed unmodified through 5i's 398→173-line decomposition |
| `test_chat_transcript_blocks.py:31` | `app.py` as text | Untested by Phase 5 — `app.py` is frozen by rule 5 and is not a 5n/5o target |
| `test_agent_llm_selection.py:813`, `test_chat_action_row_emphasis.py:279`, `test_chat_pill_bar.py:427`, `test_entry_screens.py:199`, `test_artifact_view.py:1470`, `test_chat_input_asset.py:9` | `assets/v3.css`, `assets/chat_input.js` | **Yes** — stylesheets and JS, not Python |
| `test_import_layering.py:31` | every `src/spec4/**/*.py`, `ast.parse` for import edges | **Yes** — by design; it is the layering contract |

**Conclusion for 5n and 5o:** none of the remaining source-text tests targets a function
either sub-phase decomposes. The `inspect.getsource` pattern occurs exactly once in the
suite. Per the standing instruction the rewrite rule is applied *at the point it blocks*,
not pre-emptively — and on this evidence it will not be needed again.

**For Phase 6:** the CSS/JS readers are legitimate (they pin rendered appearance to the
stylesheet, which no Python refactor touches). The one to revisit is
`test_chat_transcript_blocks.py`'s `app.py` text read, which is the only Python-source
text assertion left after 5m and is only safe because rule 5 freezes `app.py`.

## 44. Phase 5m — `callbacks/`: 11 helpers, 3 arity noqas, one forced test rewrite

Extract-only. All five 27.3 findings cleared. `src/spec4/callbacks/**` is now clean for
C90 / PLR0912 / PLR0913 / PLR0915.

### 44.1 Before and after

| File | Function | C901 | Br | St | Ar | → |
|---|---|---:|---:|---:|---:|---|
| `designer/_mock_gen.py` | `_start_gen` | **20** | — | **64** | 13 | **10**, St clear, Ar noqa |
| `_chat.py` | `on_stream_poll` | **16** | **15** | — | — | clear |
| `designer/_mock_gen.py` | `_run` (nested) | **15** | **16** | — | — | folded into `_start_gen`'s 10 |
| `_setup.py` | `on_setup_connect` | — | — | — | 6 | noqa |
| `designer/_refine.py` | `on_designer_regenerate` | — | — | — | 6 | noqa |

### 44.2 The 11 helpers

**`_chat.on_stream_poll` (5)** — one per poll arm, as 27.3 called for:
`_poll_missing_stream`, `_poll_running`, `_poll_dev_trace`, `_poll_finalise`,
`_poll_substitute_empty_turn`. Every `Output` tuple shape and component id is unchanged.

**`designer/_mock_gen.py` (6)** — `_mock_stop_previous`, `_mock_design_dir`,
`_mock_collect_snippets`, `_mock_finalise_draw`, `_mock_report_failure`,
`_mock_persist_session`.

### 44.3 Rule 8 was *not* applied to `_run`, and why

`_run` is a nested closure, so rule 8 says promote it. **It captures 17 locals**
(`api_base`, `api_key`, `buf_entry`, `capture_mode`, `design_dir_path`, `ds`, `effort`,
`existing_html`, `extra_kwargs`, `gen_id`, `image_support`, `model`,
`planning_context`, `search_cfg`, `session`, `stop_ev`, `working_dir` — measured with
`symtable`, not guessed). Promoting it produces a 17-parameter function needing its own
PLR0913 noqa, which is not pre-approved.

Instead its *body* was extracted into six module-level helpers, which drops `_run`'s
contribution to its enclosing function's count without moving `_run` itself.
`_start_gen` lands at **C901 10** — exactly at the threshold, which is why the last two
cuts (`_mock_stop_previous`, `_mock_design_dir`) were needed. Rule 8's purpose is served:
no closure complexity is being suppressed, it is decomposed.

### 44.4 Forced test edit (rule 2's structural exception) — the only one

`tests/test_designer.py::TestRefinePersistsManifest::test_persist_is_not_gated_on_the_draw_kind`

**Old (structural):**
```python
src = inspect.getsource(_dmod()._start_gen)
assert "_persist_manifest(" in src
assert "if existing_html is None:" not in src
```

**New (behavioural):** runs `_start_gen` on a **refine** draw (`existing_html` set) with
a synchronous `Thread` stand-in and `_persist_manifest` patched, then
`assert calls, "a refine draw must still persist the manifest"`.

Same file, same class, same name. It fails if the persist is ever gated on the draw kind
again — which is D-DM9, the property the test exists for — and unlike the old form it
does not fail merely because the call moved into a helper. A `_SyncThread` stand-in was
added beside the existing `_NoThread` so the generation body runs inline.

**This is the only test edit in 5a–5m.** The sweep in §43 confirms `inspect.getsource`
occurs exactly once in the suite, so the exception should not be needed again.

### 44.5 Line accounting (rule 3)

**446 non-blank lines**; **441 verbatim**; 5 accounted: three `def` lines now carrying
arity noqas, and two lines of the `_persist_manifest(...)` call re-wrapped by
`ruff format` when it moved into `_mock_finalise_draw` (identical tokens and arguments —
`accumulated, planning_context, design_dir_path`). **No statement line is unaccounted
for.**

### 44.6 Statement counts and coverage (rule 4)

Suite-wide **12338 → 12363, +25**. Misses **896 = 893 + 3**, unchanged.

### 44.7 One reverted attempt

The first 5m build passed ruff, format, mypy and the callbacks complexity check, then
failed `test_persist_is_not_gated_on_the_draw_kind`. Per the stop condition a failing
test is reverted immediately with **no retry** — it was, and reported. The rule-2
structural exception was then granted and this build is the result.

### 44.8 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 174.98s` (exit 0) |
| Coverage | same run | `TOTAL 12363 stmts, 896 miss (893 + 3), 93%` |

## 45. Phase 5n — `layouts/`: 9 helpers, 1 arity noqa

Extract-only. All three 27.3 findings cleared. `src/spec4/layouts/**` is now clean for
C90 / PLR0912 / PLR0913 / PLR0915.

### 45.1 Before and after

| File | Function | C901 | Br | St | Ar | → |
|---|---|---:|---:|---:|---:|---|
| `_chat_actions.py` | `_chat_action_buttons` | **19** | **24** | **54** | — | clear |
| `__init__.py` | `_agent_select_layout` | **13** | — | — | — | clear |
| `_status_bar.py` | `_status_context` | — | — | — | 6 | noqa |

### 45.2 The 9 helpers

**`_chat_action_buttons` (6)** — the function is a six-arm dispatch on `active_agent`,
so it becomes one helper per arm: `_code_scanner_action_buttons`,
`_brainstormer_action_buttons`, `_agentifier_action_buttons`,
`_stack_advisor_action_buttons`, `_phaser_action_buttons`,
`_deployer_action_buttons`. Each opens with `buttons: list[Any] = []` — the accumulator
the arm inherited from the spine — and returns it. The spine keeps the `if/elif` chain,
the elapsed readout, the counter-position search and the turn-token insert.

**`_agent_select_layout` (3)** — `_agent_select_loaded_items`,
`_append_new_round_children`, `_append_loaded_children`. The three `*_loaded` flags moved
into the first helper, which is the only place they are read.

### 45.3 Component ids are provably unchanged (rule 4 / rule 5)

`_chat_action_buttons` emits 20 component ids and every one is frozen. Checked three
ways:

1. **Id-set equality:** the `id="..."` literals extracted from the file before and after
   — **20 before, 20 after, symmetric difference empty**.
2. **`tests/test_layout_contract.py` passes unmodified** — 74 tests, the Phase 1 id
   snapshot, which walks every rendered layout and compares the id set to a checked-in
   file.
3. **`tests/test_callback_co_presence.py` (50) and `test_import_layering.py` (7) pass
   unmodified** — the first walks the callback registry against every layout, so a
   moved button that lost its id would fail there too.

### 45.4 Line accounting (rule 3)

**403 non-blank lines**; **396 verbatim**; 7 accounted:

- **6** in `_chat_action_buttons` — four `dmc.Button(...)` calls that `ruff format`
  collapsed onto one line when the arm bodies dedented from 8 to 4 spaces, plus the two
  orphan `dmc.Button(` opener lines those collapses consumed. Identical tokens; the id
  literals are among them and are covered by 45.3.
- **1** — `_status_context`'s `def` line, now carrying the arity noqa.

**No statement line is unaccounted for.**

### 45.5 Statement counts and coverage (rule 4)

Suite-wide **12363 → 12395, +32**. Misses **896 = 893 + 3**, unchanged.

### 45.6 Deferred

The two `ARG001` unused `session` parameters (`layouts/__init__.py:235`,
`layouts/_setup.py:231`) are **5p(e)**, not 5n.

### 45.7 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 175.05s` (exit 0) |
| Coverage | same run | `TOTAL 12395 stmts, 896 miss (893 + 3), 93%` |

## 46. Phase 5o — root modules: six of seven, 15 helpers, 1 noqa

`_artifacts.py`, `feature_specs.py`, `providers.py`, `usage_report.py`, `session.py`,
`project_manager.py`. **`llm.py` is not in this commit** — its first attempt failed seven
tests and was reverted; it returns as **5o2** (47, 48).

### 46.1 Before and after

| File | Function | C901 | Br | St | → |
|---|---|---:|---:|---:|---|
| `session.py` | `_persist_artifacts` | **14** | **13** | — | clear |
| `_artifacts.py` | `merge_library_additions` | **14** | **14** | — | clear |
| `feature_specs.py` | `_render_graph_lines` | **13** | **13** | — | clear |
| `providers.py` | `_fetch_models` | **13** | — | — | clear |
| `project_manager.py` | `_artifact_button_state` | **13** | — | — | **noqa** |
| `feature_specs.py` | `_render_topology` | **12** | — | — | clear |
| `session.py` | `_load_working_dir` | **12** | — | **51** | clear |
| `usage_report.py` | `render_usage_table` | **12** | — | — | clear |

### 46.2 The 15 helpers

`_artifacts.py` — `_libraries_map`, `_library_entry`.
`feature_specs.py` — `_subagent_lines`, `_tier_analysis_lines`.
`providers.py` — `_fetch_openai`, `_fetch_bedrock`, `_fetch_openrouter` (the three
largest of eight provider arms; the five short ones stay inline and the function lands
under threshold).
`usage_report.py` — `_usage_row` (**promoted closure**, rule 8), `_usage_missing_counts`,
`_usage_footnotes`.
`session.py` — `_load_round_artifacts`, `_load_ai_features`, `_load_deployment_state`,
`_persist_spec_artifacts`, `_persist_plan_artifacts`.

### 46.3 Rule 10 class 4 — the E501 case it was written for

`project_manager.py` is the file 27.2 rule 10 names: it carries **no** per-file `E501`
ignore, unlike `agents/**` and `agentifier/**`. Appending the state-machine reason to
`def _artifact_button_state(` takes the line past 88, so `E501` joins the noqa on the
same line, exactly as the rule prescribes:

```
def _artifact_button_state(  # noqa: C901, E501  # the branches are the documented
artifact button state machine; E501 because project_manager.py carries no per-file
E501 ignore
```

This is the first and only use of that clause in Phase 5.

### 46.4 Coverage: 893 + 4 (rule 4, permitted case)

| Site | Block it calls | Sub-phase |
|---|---|---|
| `agents/designer.py:738` | `_designer_accumulate_tool_calls(...)` | 5j |
| `agents/designer.py:747` | `_designer_tool_call_followup(...)` | 5j |
| `agentifier/agentifier.py:1315` | `_cc_store_analysis(...)` | 5k |
| **`feature_specs.py:433`** | **`_subagent_lines(...)`, inside `_render_topology`** | **5o** |

`_render_topology`'s body is never entered by the suite (lines 420–434 were already
missed), so the call statement added at 433 is a new miss and nothing else moved. Same
permitted shape as the other three.

### 46.5 Line accounting (rule 3)

**549 non-blank lines**; **543 verbatim**; 6 accounted:

- **4** in `render_usage_table` — the `def _line(...)` closure line and its three call
  sites, which rule 8's promotion turned into `_usage_row(cells, widths, right)`. The
  captured `widths` and `right` became parameters, so each call site gained two
  arguments; the alignment expression itself is verbatim.
- **1** — `tier_libs.append(new_lib)` became `tier_libs.append(_library_entry(entry, name))`.
- **1** — `def _artifact_button_state(`, now carrying the noqa.

**No statement line is unaccounted for.**

### 46.6 Statement counts (rule 4)

Suite-wide **12395 → 12426, +31**. Misses **897 = 893 + 4**, the fourth accounted in 46.4.

### 46.7 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 174.40s` (exit 0) |
| Coverage | same run | `TOTAL 12426 stmts, 897 miss (893 + 4), 93%` |

## 47. Why 5o's first `llm.py` attempt failed — diagnosis (read-only)

Seven tests failed and the attempt was reverted. The cause is **not** a helper rebinding
a caller local; both extracted helpers mutate in place (`tool_call_acc` is a dict,
`messages` a list) and neither rebinds anything the caller reads afterwards.

**The cause is an indentation mismatch at the call site.** The block replaced was

```
894             for chunk in response:          <- indent 12, body at 16
...
916                 if choice.delta.tool_calls: <- indent 16, the block
931                     ...                        replaced (916-931)
```

and the replacement call was written at **indent 12**:

```
            _accumulate_tool_calls(tool_call_acc, choice)
```

Indent 12 is the indentation of `for chunk in response:` itself, so the call became a
**sibling of the loop rather than part of its body**. It therefore ran **once, after the
stream was exhausted**, with `choice` bound to the final chunk — so tool-call deltas were
never accumulated across chunks. Every one of the seven failures is a tool-call or search
path, which is exactly what that predicts.

`_append_tool_call_turn` was fine: it replaced lines 938-954, which start at indent 12,
and its call was written at indent 12.

**The code was valid Python throughout.** `ast.parse` accepted it, `ruff` accepted it,
`mypy` accepted it. Only the suite caught it — the same blind spot recorded at 37.9,
where six helper bodies dedented to column 0 parsed cleanly and had to be caught by
`ruff`. Here the wrong indent is one level in, so even ruff sees nothing wrong.

**The check that would have caught it** is mechanical and cheap: *the replacement line's
indentation must equal the indentation of the first line of the range it replaces.* It
was added to the build method for 5o2 as an assertion that runs before `ast.parse`, and
it passed on both of 5o2's edits. Whether it becomes rule 13 is a call for the plan
owner; the rebinding guard proposed alongside it is a real hazard too (5k's
`_cc_apply_revision` and 5i's `_phaser_count_chunk` both had to return a rebound local),
but it is not what happened here.

## 48. Phase 5o2 — `llm.py`

### 48.1 What landed

Per 27.3, **request assembly only**; the chunk loop and the tool round stay whole and in
place. Two helpers:

- `_stream_turn_tools(messages, search_config, response_format)` — the web-search tool,
  unless a JSON-format turn has to suppress it.
- `_stream_request_kwargs(system_prompt, messages, llm_config, response_format, tools)` —
  one tool-loop round's completion kwargs.

Nothing inside `try:` / `for chunk in response:` / `if tool_call_acc:` was touched. 5o's
first attempt is the evidence for why: those blocks *can* be extracted — the resulting
code is valid and lints clean — and extracting them broke the turn.

### 48.2 Rule 12 and the eleventh noqa

`stream_turn` after the two cuts is **C901 24 / PLR0912 26 / PLR0915 66 / PLR0913 7**, and
takes the rule-12 noqa as 27.4 entry eleven. The reason is written to say what actually
survives — *"entry guards plus the chunk loop, which 27.3 keeps whole as the streaming
characterization surface"* — rather than reusing entries 6-10's wording, because the
grant is genuinely wider: those functions keep their branches because extraction cannot
move them, this one keeps its chunk loop because the plan says to.

The prior measurement stands on the record: 5o's aggressive build reached **C901 17**, so
the chunk loop is worth 7 complexity points — and its cost is a broken turn.

The three other `llm.py` arity noqas (`_record_usage` 9, `_iter_with_usage` 6,
`_aiter_with_usage` 6) are the pre-approved 27.4 entries, appended per rule 10.

### 48.3 Line accounting (rule 3)

**314 non-blank lines** across the four functions; **310 verbatim**; 4 accounted — the
four `def` lines now carrying noqas. **No statement line is unaccounted for.**

### 48.4 `src/` is now clean for the whole Phase 5 rule set

```
$ uv run ruff check --select C90,PLR0912,PLR0913,PLR0915 --statistics src/
(no output)
```

**Zero findings** across `src/spec4/**` — down from 138 at 27.1. Every one either
decomposed or carrying one of the eleven pre-approved noqas.

### 48.5 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 172.34s` (exit 0) |
| Coverage | same run | `TOTAL 12432 stmts, 897 miss (893 + 4), 93%` |

## 49. Phase 5p — cross-cutting sweep and the rule-set promotion

Closes Phase 5. `uv run ruff check src/ tests/` now runs the promoted rule sets and
passes.

### 49.1 (a) Duplication — two lifts, both proven exact

**`_stack_ai_served_ids` deleted.** It was byte-identical to the public
`ai_served_feature_ids` in the same module apart from the accumulator's name and the
docstring — surfaced by 5f, which extracted it and flagged it here rather than unifying
mid-sub-phase. `feature_specs_for_stack` now calls the public function.

**The three Deployer yes/no matchers collapsed to one.** `_deployer_readme_reply_intent`
and `_deployer_readme_optin_intent` were **identical apart from the name and docstring**;
`_deployer_plan_reply_intent` differed **only in its word lists**. All three become
`_yes_no_intent(user_input, yes_words, no_words)` with the lists as the module constants
`_YES_WORDS` / `_NO_WORDS` and `_YES_WORDS_PLAN` / `_NO_WORDS_PLAN`. This is exactly the
shape 27.5(a) describes — "the same 10+ lines with different constants, lift with the
constants as parameters" — and 5i surfaced it deliberately (38.3).

The other candidates logged along the way were **left alone** because they are not exact
matches: the seven per-consumer `_*_feature_lines` helpers (5f) render different field
sets, and the entity-collection loop appears twice but is four lines.

### 49.2 (b) Magic strings — 68 occurrences, 7 constants

The seven artifact file names appearing in more than one file are now
`ARTIFACT_VISION`, `ARTIFACT_STACK`, `ARTIFACT_CODE_REVIEW`, `ARTIFACT_AI_FEATURES`,
`ARTIFACT_MANIFEST`, `ARTIFACT_FEATURE_SPECS`, `ARTIFACT_USAGE` in `app_constants.py`,
replacing **68 literal occurrences across 14 files** (`project_manager.py` alone held 28).

**String values are provably unchanged.** Every file was parsed before and after and
every string constant's value compared as a multiset. The only permitted delta is a
standalone filename literal disappearing; **anything that merely *contains* a filename —
a prompt, a docstring, an f-string template — had to be identical**. Result: **zero
violations**. That check is what makes this safe: a `"vision.json"` sitting inside a
triple-quoted prompt would otherwise have been silently rewritten.

`.spec4/` and `.spec4/v{round_number}/` are **not** extracted: they appear inside
f-strings whose surrounding text differs, so there is no single literal to name.

### 49.3 (c)(d)(e) The mechanical items — all 13 in `src/`

| Item | Sites | Done |
|---|---|---|
| SIM105 | `_artifacts.py`, `_usage.py`, `callbacks/designer/_refine.py` | `contextlib.suppress` |
| SIM117 | `websearch.py` ×2 | merged `async with (...)` |
| SIM905 | `requires_reconciler.py` `_STOPWORDS` | tuple literal; **the resulting frozenset was compared to the old one and is identical — 59 words** |
| B904 | `agentifier/subagents.py` ×2 | `raise ... from exc` |
| B007 | `agents/designer.py` | `root` → `_root` |
| B905 | 4 sites | **`strict=False`** — byte-identical to today's silent truncation. `strict=True` would raise on unequal lengths, a behaviour change; each site stays logged for a separate review |
| ARG | 12 sites | 3 were parameters my own 5m/5n/5o helpers never read → **removed outright**; the rest are uniform-signature or Dash-callback parameters → underscore-prefixed, every call site verified positional first |

### 49.4 (g) The promotion — and the deliberate narrowing of `PLR`

```toml
select = ["E", "F", "C90", "PLR0912", "PLR0913", "PLR0915", "SIM", "B", "ARG"]
```

27.5(g) called for `"PLR"` wholesale. **It is promoted as three named rules instead**,
for the reason recorded at 42.6: bare `PLR` also carries **PLR2004 (49 in `src/`),
PLR0911 (7) and PLR1714 (1)** — 57 findings Phase 0 never measured and Phase 5 never
touched. Promoting them would put 57 unreviewed findings into the gate on day one.
Phase 5 measured and cleared PLR0912/0913/0915; those are what it earns the right to
enforce. **PLR2004 overlaps 5p(b)'s magic-value work and is the natural Phase 7 follow-up.**

Per-file ignores added:

- `"tests/**/*.py" = ["ARG", "SIM117", "PLR0913"]` — 224 findings that are test shape,
  not test smell: fixture/stub/lambda parameters a test must accept but need not read,
  deliberate `pytest.raises` + `patch` nesting, fixture-heavy signatures.
- `"evals/**/*.py"` and `"scripts/**/*.py"` — the same plus the long-function rules.
  Both are outside the Rule 6 gate and were never measured by Phase 5.

The mechanical `tests/` findings were **fixed, not ignored**: 8 SIM300 (yoda), 8 B905
(`strict=False`), 1 SIM105. That is 5p(f)'s lint-only exception to rule 2 and the only
`tests/` edit in this sub-phase.

### 49.5 (h) Type hygiene — measured and deferred

`src/spec4/**` carries **290 `Any` annotations**. Replacing them where the real type is
knowable is genuine work with real regression risk, and it is the one 5p item with no
mechanical check behind it — mypy is already clean, so nothing fails if a replacement is
wrong in a way the tests do not reach. **Deferred to Phase 7 with the count on record.**
27.5(h)'s prohibition stands regardless: no `TypedDict` for the session dict, that is a
design change.

### 49.6 Coverage is back at the Phase 0 baseline

Misses **893** — not 893 + 4. The four permitted call sites from 5j/5k/5o are still
missed, and are exactly offset by four previously-missed statements that this sub-phase
removed: the `except: pass` bodies that became `contextlib.suppress` (one statement each
instead of two on a never-taken path) and the unused parameters that were deleted.

| | Phase 0 | after 5p |
|---|---:|---:|
| Statements | 11,676 | 12,421 |
| Misses | **893** | **893** |
| Coverage | 91% | 93% |

### 49.7 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) — **with the promoted rule sets** |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 170.46s` (exit 0) |
| Coverage | same run | `TOTAL 12421 stmts, 893 miss, 93%` |

`uv run ruff check .` reports 13 findings, all `E501` in `scripts/e2e_agentifier.py`.
They **predate Phase 5** — `E` was always selected and `scripts/` never carried an
ignore — and sit outside the Rule 6 gate. Left for Phase 7.

## 50. Phase 6 pre-work — measurement and coupling inventory (read-only)

Recorded 2026-09-09 on branch `look-rework`, at `a86a2ee` (Phase 5p). Nothing under
`src/` or `tests/` was written. No formatter ran, no `noqa` changed. The only artifact
is this section. Phase 6 does not start until §50 is approved.

Everything measured here was measured mechanically; the scripts lived in the session
scratchpad and are described inline so each number can be re-derived.

### 50.0 Where this run's directive and the record disagree

Four disagreements. In each the record wins, per the standing rule.

**(a) The Phase 1 figures.** The directive gives Phase 1 as *3028 passed, ~65 s*.
§12.6 records `4249 passed, 1 skipped in 172.63s`, and §12.3 restates it as "4249
passed + 1 skipped in ~176 s". 3028/65 s matches nothing in §1–§49. **§12.6 is used
throughout §50.1.**

**(b) "Confirm zero skips and zero xfails as at the Phase 1 baseline."** The Phase 1
baseline was **not** zero skips — §12.6 records one, and it is the same one today.
There is therefore nothing to attribute to Phases 2–5. Zero xfails is correct and
confirmed: the suite contains no `xfail` marker of any kind. Detail in §50.1.

**(c) "Sum the `sleep` seconds separately; that is the cheapest runtime to recover and
Phase 6 will want it first."** Measured, and it is not. The whole suite sleeps
**12.97 s across 171 calls**, and none of it appears in the 40 slowest tests. The
cheapest recoverable runtime by a wide margin is a per-character `MagicMock` chunk
factory in two test modules, measured at **48–49 s** of a 139 s run. §50.1 reports the
sleep sum as asked and then reports what actually dominates.

**(d) `inspect.getsource` is no longer in the suite.** The directive names
`tests/test_designer.py::TestRefinePersistsManifest::test_persist_is_not_gated_on_the_draw_kind`
as a known instance. It was rewritten at 5m under rule 2's structural exception
(§44.4), and §43 already recorded that the pattern "occurs exactly once in the suite".
An AST sweep of all 127 Python files under `tests/` finds **zero** `inspect.getsource`
calls. Kind 3 of §50.2 is empty and the behaviour question it asks is answered
from §44.4.

**(e) `evals/` is not actually outside the suite.** The directive holds `evals/`
outside this run, and §49.4 records `evals/**` as outside the Rule 6 gate for linting.
But there is **no `[tool.pytest.ini_options]` block in `pyproject.toml`** and no
`pytest.ini`, `setup.cfg` or `tox.ini` — so a bare `uv run pytest` collects from the
repo root, and **four modules under `evals/` contribute 82 of the 4,257 collected
tests**: `evals/agentifier/test_mechanism_scoring.py` (25),
`evals/scout/test_relevance_judge.py` (20), `evals/scout/test_phantom_link_check.py`
(19), `evals/phaser/test_requires_inversion.py` (18). They run in 2.59 s and pass.
`tests/conftest.py:65` already puts `evals/scout/` on `sys.path` for
`tests/agentifier/test_fanout_baseline.py`, so the two trees are entangled by import as
well as by collection. **Nothing under `evals/` was read, written, or reasoned about
beyond this measurement**, and §50.2's sweep is `tests/`-only as instructed — verified
harmless: an AST pass over the four files finds **zero** patches, zero `patch.object`,
and zero private-name imports, so no coupling row is missing. Phase 6 needs to know
that "the suite" and "`tests/`" are not the same 4,257 tests. **Recorded, not acted on.**

**Untouched, as instructed:** 5p(h) type hygiene (290 `Any`, §49.5); the six
sub-generator backlog entries (§27.4); the `project_manager` root-siblings
inconsistency; `evals/` beyond the count above. §27.4's eleven complexity `noqa`s are
still eleven —
`grep -rn "noqa: \(C901\|PLR09\)" src/` returns the same eleven functions §27.4 names,
plus the twelve arity-only `PLR0913`s.

### 50.1 Baseline measurement and targets

#### Counts

Three runs of `uv run pytest -q --durations=40 -p no:cacheprovider`, back to back:

| Run | Result | pytest-reported | wall |
|---|---|---:|---:|
| 1 | `4256 passed, 1 skipped` | 139.14 s | 144.17 s |
| 2 | `4256 passed, 1 skipped` | 139.91 s | 144.27 s |
| 3 | `4256 passed, 1 skipped` | 140.98 s | 145.12 s |
| **median** | | **139.91 s** | **144.27 s** |

`--collect-only` reports **4257 collected** — of which **4,175 are under `tests/` and
82 under `evals/`** (§50.0(e)). Zero xfailed, zero deselected, zero errors. Wall exceeds pytest's own figure by a constant ~4.2 s — that is `uv`
resolution plus interpreter and conftest import, measured separately as 4.23 s for a
one-file `--collect-only`.

**The one skip**, unchanged since Phase 1:

```
SKIPPED [1] tests/test_session.py:721: Designer has no chat turn; it draws from its wizard
```

It is a `pytest.skip()` inside a parametrization over `AGENT_KEYS`; the Designer arm
has no chat turn to exercise. Four other `pytest.skip()` calls exist and did not fire:
`tests/test_root_routing.py:373` (skips when the test runs as a user that can read
mode-000 directories) and one per browser-E2E module (skips when no browser is
available — all three found one here).

**Zero xfails**: `grep -rn "xfail" tests/` returns nothing.

#### Delta against Phase 1

| | Phase 1 (§12.6) | now | delta |
|---|---:|---:|---:|
| passed | 4249 | 4256 | **+7** |
| skipped | 1 | 1 | 0 |
| collected | 4250 | 4257 | **+7** |
| runtime (with `--cov`) | 172.63 s | 174.98 s | +2.35 s |
| runtime (no `--cov`) | — | 139.91 s | — |

The +7 is attributable exactly, not estimated. Comparing the set of test-function
qualified names in `git show 8b277fd:<file>` against `HEAD` for every one of the 45
test files touched between *Phase 1 followup* and `a86a2ee`:

| Sub-phase | File | Tests added | Tests removed |
|---|---|---:|---:|
| Phase 4 pre-work (§15.3) | `tests/test_import_layering.py` | **+7** | 0 |
| everything else in Phases 2–5 | 44 files | 0 | 0 |

**No test was deleted anywhere in Phases 2–5.** The other 44 files were modified in
place — import-path updates from the 4a–4j splits, and 5p(f)'s lint-only fixes (8
SIM300, 8 B905, 1 SIM105, §49.4). One test *body* was rewritten: §44.4's
`getsource` case, same name, same file.

#### The 40 slowest

From run 1. Cause categories are as the directive defines them, with one addition:
`mock`, for time spent constructing `unittest.mock` objects. It is not in the
directive's list because the directive did not anticipate it dominating.

| s | phase | node id | cause |
|---:|---|---|---|
| 5.15 | setup | `integration/test_page_slot_e2e.py::TestClickingTheChatBoxAfterTheArtifactView::test_the_frame_is_still_there` | subprocess |
| 4.60 | call | `test_agents.py::TestPhaseCompleteness::test_fresh_incomplete_set_triggers_retry_then_completes` | mock |
| 4.46 | setup | `integration/test_chat_frame_e2e.py::TestTheTranscriptScrollsIndependently::test_the_transcript_overflows_its_own_box` | subprocess |
| 4.40 | setup | `integration/test_artifact_view_e2e.py::TestOpeningStackJson::test_the_tree_lists_the_round_s_artifacts` | subprocess |
| 4.35 | call | `integration/test_page_slot_e2e.py::TestClickingTheChatBoxAfterTheArtifactView::test_the_frame_is_still_there` | subprocess |
| 3.63 | call | `test_app_import_smoke.py::TestAppImportsCleanly::test_the_app_constructs_and_registers_everything` | subprocess |
| 3.57 | call | `test_agents.py::TestPhaserCoverageEnforcement::test_infra_after_consumer_triggers_retry` | mock |
| 3.38 | call | `test_app_import_smoke.py::TestAppImportsCleanly::test_version_flag_prints_and_exits_zero` | subprocess |
| 3.25 | call | `test_agents.py::TestPhaseCompleteness::test_completeness_applies_with_prior_phases` | mock |
| 2.62 | call | `test_agents.py::TestPhaserCoverageEnforcement::test_missing_mvp_feature_triggers_retry_then_completes` | mock |
| 1.88 | call | `test_agents.py::TestPhaserImplementedMarker::test_marker_appended_to_last_phase_only` | mock |
| 1.85 | call | `test_agents.py::TestPhaserImplementedMarker::test_marker_not_duplicated_when_already_present` | mock |
| 1.72 | call | `test_agents.py::TestPhaserValidationRetry::test_retry_uses_response_format_when_supported` | mock |
| 1.71 | call | `test_agents.py::TestPhaserValidationRetry::test_invalid_phase_triggers_retry` | mock |
| 1.19 | call | `test_agents.py::TestPhaserCoverageEnforcement::test_complete_coverage_completes_the_set` | mock |
| 1.19 | call | `test_agents.py::TestPhaserCoverageEnforcement::test_no_catalog_leaves_coverage_inert` | mock |
| 1.15 | call | `test_agents.py::TestPhaserCoverageEnforcement::test_deferred_feature_is_surfaced_as_advisory` | mock |
| 1.01 | call | `test_agents.py::TestPhaserValidationRetry::test_retry_failure_drops_exchange_and_emits_fallback` | mock |
| 0.99 | call | `test_agents.py::TestPhaserValidationRetry::test_valid_phase_does_not_retry` | mock |
| 0.97 | call | `test_agents.py::TestPhaserValidationRetry::test_display_override_is_rendered_markdown` | mock |
| 0.93 | call | `test_agents.py::TestPhaserStackAdditionCaptureAcrossTurn::test_block_before_search_is_captured_stripped_and_concatenated` | mock |
| 0.87 | setup | `integration/test_chat_frame_e2e.py::TestTheBackRoutesHaveLiveEquivalents::test_no_back_control_is_left_on_the_frame` | subprocess |
| 0.80 | call | `test_agents.py::TestPhaser::test_phases_json_sets_state_complete` | mock |
| 0.76 | setup | `integration/test_chat_frame_e2e.py::TestTheCompletedRunsCostStrip::test_it_is_three_lines_labelled_an_estimate` | subprocess |
| 0.75 | setup | `integration/test_chat_frame_e2e.py::TestTheCompletedRunsCostStrip::test_the_figures_render_in_monospace` | subprocess |
| 0.73 | call | `test_stack_shape_resilience.py::test_render_failure_leaves_no_display_override` | mock |
| 0.71 | call | `test_stack_shape_resilience.py::test_flat_libraries_no_longer_crashes_the_turn` | mock |
| 0.70 | setup | `integration/test_chat_frame_e2e.py::TestTheRenderedFrame::test_the_model_name_renders_in_monospace` | subprocess |
| 0.68 | setup | `integration/test_chat_frame_e2e.py::TestTheRenderedFrame::test_the_active_agent_is_marked` | subprocess |
| 0.67 | setup | `integration/test_chat_frame_e2e.py::TestTheTranscriptScrollsIndependently::test_it_scrolls_rather_than_clipping` | subprocess |
| 0.66 | setup | `integration/test_chat_frame_e2e.py::TestTheCompletedRunsCostStrip::test_it_wears_the_same_class_as_the_project_view_s` | subprocess |
| 0.66 | setup | `integration/test_chat_frame_e2e.py::TestTheRenderedFrame::test_user_turns_are_filled_and_agent_turns_are_not` | subprocess |
| 0.66 | call | `integration/test_chat_frame_e2e.py::TestAtAShortViewport::test_it_still_scrolls_itself` | subprocess |
| 0.65 | setup | `integration/test_chat_frame_e2e.py::TestTheCompletedRunsCostStrip::test_it_renders_under_the_transcript` | subprocess |
| 0.65 | setup | `integration/test_artifact_view_e2e.py::TestALargeArtifact::test_the_whole_file_is_four_dom_nodes_not_four_thousand` | subprocess |
| 0.65 | setup | `integration/test_artifact_view_e2e.py::TestALargeArtifact::test_every_line_is_numbered` | subprocess |
| 0.64 | setup | `integration/test_chat_frame_e2e.py::TestTheRenderedFrame::test_the_pipeline_reads_as_seven_plain_labels` | subprocess |
| 0.64 | setup | `integration/test_artifact_view_e2e.py::TestOpeningAPhaseFile::test_markdown_is_shown_as_written` | subprocess |
| 0.64 | setup | `integration/test_chat_frame_e2e.py::TestTheTranscriptScrollsIndependently::test_the_composer_is_still_on_screen_under_it` | subprocess |
| 0.64 | setup | `integration/test_artifact_view_e2e.py::TestDownload::test_it_is_disabled_with_nothing_selected` | subprocess |

Top-40 total **67.16 s**, 48% of a 139 s run.

| Cause | seconds in the top 40 |
|---|---:|
| `mock` | **30.87** |
| `subprocess` (browser E2E: server subprocess + webdriver) | 29.28 |
| `subprocess` (`test_app_import_smoke.py`, the D-LR1 startup probe) | 7.01 |
| `sleep` | **0.00** |
| `network`, `tmp_path` I/O, `import`, `unknown` | 0.00 |

#### The `sleep` category, as asked

`grep -rn "time\.sleep(" tests/` finds **17 call sites in 13 files**. Measured by
wrapping `time.sleep` in a pytest plugin loaded from the scratchpad (no tree edit) and
running exactly those 13 files: **171 calls, 12.97 s slept**, out of 64.31 s for that
subset. The sites are polling loops around daemon threads (0.005–0.05 s) and three
0.2 s webdriver settles in the E2E modules.

12.97 s is 9% of the run and every second of it is a real wait on another thread or a
browser. It is **not** the cheapest recoverable runtime; recovering it means replacing
poll loops with `threading.Event` waits, which is a rewrite of the concurrency harness.

#### What actually dominates, and what it costs to remove

`tests/test_agents.py:49`:

```python
def make_stream_chunk(content: str, finish_reason: str | None = None) -> MagicMock:
    chunk = MagicMock()
    chunk.choices[0].delta.content = content
    ...
```

and `mock_litellm_stream` / `_chunkify_stream` built on it produce **one `MagicMock`
per character** of streamed text. Each one, on those three attribute chains, spawns
four or five auto-child mocks. A phase-block fixture is several thousand characters,
streamed twice.

Three measurements:

1. **A warm `cProfile` of the single slowest test.** 20,713 `MagicMock` children
   created; 4.29 s of the 7.08 s profiled sample inside `mock._mock_set_magics`, 2.23 s
   inside `NonCallableMock.__init__`. No `spec4` frame appears in the top 20.
2. **Suite-wide count**, same plugin technique: **216,428 mock instantiations** in one
   full run.
3. **The direct experiment.** A scratchpad pytest plugin replaces `make_stream_chunk`
   with a `SimpleNamespace` of the same shape, in memory, at
   `pytest_collection_finish`. Nothing on disk changes, no assertion changes.

| | tests | result | pytest time |
|---|---:|---|---:|
| `tests/test_agents.py` baseline | 293 | passed | **40.65 s** |
| `tests/test_agents.py` with plain-namespace chunks | 293 | passed | **0.64 s** |
| full suite baseline | 4257 | `4256 passed, 1 skipped` | **139.14 s** |
| full suite with plain-namespace chunks | 4257 | `4256 passed, 1 skipped` | **90.83 s** |

A micro-benchmark of the two chunk shapes over 5,000 chunks, built and read exactly as
`llm.stream_turn` reads them: **MagicMock 4.253 s, SimpleNamespace 0.008 s.**

**48.3 s of a 139 s run is the cost of `MagicMock`'s auto-child machinery, in two test
modules** (`tests/test_agents.py:49` and
`tests/agentifier/test_agentifier_orchestrator.py:119`, which defines the same factory).
Same tests, same assertions, same pass/skip counts.

#### Per-file test counts

126 collected files — **122 under `tests/`, 4 under `evals/`** (§50.0(e)).
`pytest --collect-only -q | cut -d: -f1 | sort | uniq -c | sort -rn`:

| Tests | File | Over 150? |
|---:|---|---|
| 293 | `tests/test_agents.py` | **split candidate** |
| 215 | `tests/test_stack_render_totality.py` | **split candidate** |
| 213 | `tests/test_artifact_view.py` | **split candidate** |
| 162 | `tests/test_designer.py` | **split candidate** |
| 155 | `tests/test_agent_llm_selection.py` | **split candidate** |
| 125 | `tests/test_designer_wizard_register.py` | |
| 118 | `tests/test_project_manager.py` | |
| 90 | `tests/agentifier/test_prioritizer.py` | |
| 77 | `tests/test_usage_capture.py` | |
| 77 | `tests/test_agent_rows.py` | |
| 75 | `tests/test_round_tree.py` | |
| 74 | `tests/test_layout_contract.py` | |
| 71 | `tests/test_session.py` | |
| 67 | `tests/test_status_bar.py` | |
| 67 | `tests/agentifier/test_agentifier_orchestrator.py` | |

Five files over 150, holding **1,038 tests — 24% of the suite in 4% of the files.**
`tests/test_agents.py` alone is 40.65 s of a 139 s run today (7% of the tests, 29% of
the runtime), which is the mock finding above and not a reason to split it.
`tests/test_stack_render_totality.py` and `tests/test_artifact_view.py`, the next two
largest, cost 0.5 s and 1.4 s respectively — they are large but not slow.

Measured wall time by directory and largest file (each includes the ~4.2 s startup):

| Target | wall | tests |
|---|---:|---:|
| `tests/integration/` | 61.70 s | 86 |
| `tests/test_agents.py` | 44.91 s | 293 |
| `tests/agentifier/` | 14.54 s | 721 |
| `tests/test_usage_capture.py` | 6.82 s | 77 |
| `tests/test_designer.py` | 5.81 s | 162 |
| `tests/test_artifact_view.py` | 5.57 s | 213 |
| `tests/test_agent_llm_selection.py` | 5.01 s | 155 |
| `tests/test_stack_render_totality.py` | 4.66 s | 215 |
| `evals/` (all four modules) | 4.21 s | 82 |

#### Proposed targets (proposals only — Phase 6 does not set them here)

> **Superseded by §50.5.** Both proposals below were amended on approval. The floor is
> **456**, not 273 — §50.5(a) adopted the tier-B reading. The runtime target is
> restated against the post-`testpaths` baseline — §50.5(b). This subsection is left as
> written because it is the reasoning the amendments were made against; **§50.5 is what
> Phase 6 runs under.**

**Count floor: 273.**

Below this number Phase 6 may not take the suite. It is the union of §50.3's three
sources, de-duplicated (a test counted once even when it qualifies twice):

| Component | Tests |
|---|---:|
| The five Phase 1 modules, whole-file (§12.1; still exactly the 131 Phase 1 wrote) | 131 |
| `tests/test_callback_co_presence.py`, whole-file (the id contract) | 50 |
| `tests/test_import_layering.py`, whole-file (Phase 4's layering contract, §15.3) | 7 |
| Tests whose own name or docstring cites a D-number, outside the above | 73 |
| The named co-presence/ordering assertions in three further files | 12 |
| **Floor** | **273** |

*Justification:* it is the Phase 1 net (131) plus every standing contract file (57)
plus every invariant test that names the decision it guards (85), and nothing else. It
is 6.4% of the suite, so it constrains Phase 6 almost not at all — which is the point:
the floor exists to make one specific mistake impossible, not to cap the pruning.

A second reading is available and **not** proposed: including tests whose *class*
docstring cites a D-number adds 183, giving **456**. §50.3 lists that tier separately
so Robert can raise the floor to 456 with one word if he prefers the wider net.

**Runtime target: median ≤ 95 s, pytest-reported, no `--cov`.**

*Justification:* from 139.91 s, a single change to two chunk factories was measured at
**−48.3 s** (139.14 → 90.83, same 4256/1). That one change alone clears the target with
5 s of headroom. It touches `tests/test_agents.py:49` and
`tests/agentifier/test_agentifier_orchestrator.py:119` — neither is in §50.3, and
neither assertion changes.

The recoverable-seconds breakdown behind the figure:

| Source | seconds | in §50.3? |
|---|---:|---|
| Per-character `MagicMock` chunk factories → plain namespaces | **48.3** | no |
| `tests/integration/` browser E2E (57.5 s of the residue) | 0 — **not proposed** | no, but see below |
| `test_app_import_smoke.py` subprocess (7.0 s) | 0 — **not proposed** | **yes** — Phase 1 net |
| `time.sleep` poll loops | 0 — **not proposed** (12.97 s, and a concurrency rewrite) | mixed |
| **Total proposed** | **48.3** | |

Two of those are deliberately left at zero. `test_app_import_smoke.py` is Phase 1 net
and is a subprocess *on purpose* — it exists to exercise D-LR1's import ordering as at
startup (§12.1), which an in-process import cannot do. `tests/integration/` is the
largest single block left (57.5 s) but its server must stay a subprocess: an in-process
Dash server drains the callback registry and breaks three other test modules. Neither
is proposed, so the target does not require touching anything in §50.3.

After the one proposed change the suite is ~91 s, of which ~57.5 s is
`tests/integration/`. **A documented `-m "not slow"` inner loop (the plan's own Phase 6
bullet) then costs ~33 s, not ~82 s** — the marker is worth more after the chunk fix
than before it.

### 50.2 Layout-coupling list

Every way `tests/` reaches into module layout by string, found by AST-walking all 127
Python files under it rather than by grep, so multi-line and decorator forms are
included. The table is keyed by **target string** with its sites listed, not one row
per site: 599 patch-string sites collapse to 61 distinct targets, and the per-site rows
would carry no information the site list does not.

`resolves-today` was checked by executing mock's own resolution algorithm — import the
longest importable dotted prefix, then walk the remaining attributes.

#### Kind 1 — `patch("spec4.…")` string-path patches

**599 sites, 61 distinct targets. All 61 resolve.** 60 are `spec4.*`; one is
`litellm.acompletion` (18 sites), patched by its own name.

Beyond resolution, each target was checked for **liveness**: does any production code
read that attribute off that object at call time? A patch whose attribute nothing reads
still passes — silently, forever.

| Target (sites) | Resolves | Owner if not the named module | 5-sub-phase | Disposition |
|---|---|---|---|---|
| `spec4.llm.litellm.completion` (163) | yes | `litellm.completion` | 5o2 | keep |
| `spec4.agentifier.agentifier._call_scout` (25) | yes | — | 5k | keep |
| `spec4.agentifier.agentifier._call_tier_analyst` (21) | yes | — | 5k | keep |
| `spec4.agentifier.scout.complete_stream` (20) | yes | — | none | keep |
| `spec4.agentifier.tier_analyst.complete_stream` (20) | yes | — | none | keep |
| `spec4.callbacks._chat.streaming.start` (18) | yes | `spec4.streaming.start` | 5m | keep |
| `spec4.llm.search` (18) | yes | — | 5o2 | keep |
| `spec4.agentifier.spec_drafter.acomplete` (17) | yes | — | none | keep |
| `spec4.callbacks._chat.streaming.get` (17) | yes | `spec4.streaming.get` | 5m | keep |
| `spec4.agentifier.agentifier._registry.stream` (16) | yes | `SubAgentRegistry.stream` (instance attr) | 5k | keep |
| `spec4.session.project_manager` (16) | yes | — | 5o | keep |
| `spec4.llm_selection.probe_image_support` (15) | yes | — | none | keep |
| `spec4.llm_selection.probe_tool_support` (15) | yes | — | none | keep |
| `spec4.agentifier.cross_cutting_analyst.acomplete` (14) | yes | — | none | keep |
| `spec4.callbacks._chat._get_agent_gen` (14) | yes | — | 5m | keep |
| `spec4.llm_selection.supports_reasoning_effort` (14) | yes | — | none | keep |
| `spec4.agentifier.agentifier._extract_cross_cutting_analysis` (12) | yes | — | 5k | keep |
| `spec4.llm.litellm.get_supported_openai_params` (11) | yes | `litellm.…` | 5o2 | keep |
| `spec4.providers._json_get` (11) | yes | — | 5o | keep |
| `spec4.llm.litellm.acompletion` (8) | yes | `litellm.acompletion` | 5o2 | keep |
| `spec4.agents.phaser.run_seam_check` (8) | yes | — | 5i | keep |
| `spec4.callbacks._chat._persist_artifacts` (8) | yes | — | 5m | keep |
| `spec4.agentifier.composer.complete_stream` (7) | yes | — | 5l | keep |
| `spec4.agentifier.prioritizer.complete_stream` (6) | yes | — | none | keep |
| `spec4.callbacks._artifacts.ctx` (6) | yes | — | 5m | keep |
| `spec4.agentifier.linker.complete_stream` (5) | yes | — | 5l | keep |
| `spec4.session.brainstormer.run` (5) | yes | `spec4.agents.brainstormer.run` | 5j | keep |
| `spec4.session.stack_advisor.run` (5) | yes | `spec4.agents.stack_advisor.run` | 5j | keep |
| `spec4.websearch._list_tools_async` (5) | yes | — | 5p | keep |
| `spec4.agentifier.agentifier._call_linker` (4) | yes | — | 5k | keep |
| `spec4.llm.complete_stream` (4) | yes | — | 5o2 | keep |
| `spec4.llm.stream_turn` (4) | yes | — | 5o2 | keep |
| `spec4.callbacks._nav.ctx` (3) | yes | — | 5m | keep |
| `spec4.callbacks._setup.providers.list_models` (3) | yes | `spec4.providers.list_models` | 5m | keep |
| `spec4.callbacks.designer.ctx` (3) | yes | — | 5m | keep |
| `spec4.llm.supports_response_format` (3) | yes | — | 5o2 | keep |
| `spec4.providers._fetch_models` (3) | yes | — | 5o | keep |
| `spec4.providers.boto3.client` (3) | yes | `boto3.client` | 5o | keep |
| `spec4.session.phaser.run` (3) | yes | `spec4.agents.phaser.run` | 5i | keep |
| `spec4.websearch._call_search_async` (3) | yes | — | 5p | keep |
| `spec4.agentifier.agentifier._DEV_MODE` (2) | yes | — | 5k | keep |
| `spec4.agents.deployer.llm.stream_turn` (2) | yes | `spec4.llm.stream_turn` | 5i | keep |
| `spec4.agents.phaser.llm.stream_turn` (2) | yes | `spec4.llm.stream_turn` | 5i | keep |
| `spec4.agents.stack_advisor.llm.stream_turn` (2) | yes | `spec4.llm.stream_turn` | 5j | keep |
| **`spec4.callbacks._chat.streaming.pop` (2)** | yes | `spec4.streaming.pop` | 5m / 4g2 | **drop as dead** |
| `spec4.agentifier.agentifier._begin_priority_phase` (1) | yes | — | 5k | keep |
| `spec4.agentifier.agentifier._call_composer` (1) | yes | — | 5k | keep |
| `spec4.agentifier.agentifier._call_prioritizer` (1) | yes | — | 5k | keep |
| `spec4.agentifier.agentifier._finalize_specs` (1) | yes | — | 5k | keep |
| `spec4.agents.brainstormer._format_vision_as_text` (1) | yes | — | 5c | keep |
| `spec4.callbacks.designer._wizard.revision_delta` (1) | yes | — | 5m | keep |
| **`spec4.callbacks.designer.project_manager.load_prior_mock` (1)** | yes | `spec4.project_manager.load_prior_mock` | 4h / 5m | **rewrite to public seam** |
| `spec4.llm._usage_fields` (1) | yes | — | 5o2 | keep |
| `spec4.llm.litellm.completion_cost` (1) | yes | `litellm.completion_cost` | 5o2 | keep |
| `spec4.project_manager.load_feature_specs` (1) | yes | façade re-export (`_artifacts`) | 4b / 5o | keep |
| **`spec4.project_manager.os.fdopen` (1)** | yes | `os.fdopen` (stdlib, globally) | **4b** | **rewrite to public seam** |
| **`spec4.project_manager.os.replace` (1)** | yes | `os.replace` (stdlib, globally) | **4b** | **rewrite to public seam** |
| `spec4.project_manager.save_usage` (1) | yes | façade re-export (`_usage`) | 4b / 5o | keep |
| `spec4.session.code_scanner.run` (1) | yes | `spec4.agents.code_scanner.run` | 5j | keep |
| `spec4.session.project_manager.load_spec4_artifacts` (1) | yes | `spec4.project_manager.load_spec4_artifacts` | 5o | keep |
| `litellm.acompletion` (18) | yes | third-party, by its own name | — | keep |

**Twenty-one targets are indirect** — the string names one module and the patch lands
on an attribute of another, because the named module did `import X` and the test is
patching where the name is looked up. That is the correct mock idiom and is **not**
a defect; the `Owner` column records it so Phase 6 does not mistake it for one. The
four flagged rows are the cases where the named module no longer looks the name up at
all:

- **`spec4.callbacks._chat.streaming.pop` — the one dead patch in the suite.**
  `src/spec4/callbacks/_chat.py` contains no reference to `streaming.pop`; the done
  branch reads via `get()` and eviction moved into `start()`. Both sites
  (`tests/test_callbacks_stream_poll.py:53` and `:148`) exist only to assert
  `mock_pop.assert_not_called()` — an assertion that **cannot fail**, because nothing
  calls it through that module. §12.4 item 9 already recorded that `streaming.pop` has
  no production caller and (in Phase 3) that the function itself stays. The two
  `patch`/`assert_not_called` pairs go; the surrounding tests keep every other
  assertion and both remain meaningful.
- **`spec4.project_manager.os.fdopen` / `os.replace`.** After 4b the atomic writer
  lives in `src/spec4/_usage.py:346–359`; `project_manager.py` has no `os.fdopen` or
  `os.replace`. Both strings resolve to the **stdlib `os` module** and patch it
  process-wide, so the tests still exercise the writer — by accident of `os` being
  shared, not by design. Rewriting to `spec4._usage.os.replace` scopes the patch to the
  module that performs the write. Sites: `tests/test_usage_capture.py:815, 838`.
- **`spec4.callbacks.designer.project_manager.load_prior_mock`.** The readers after
  4h are `callbacks/designer/_mock_gen.py:211` and `_wizard.py:161`; the package
  `__init__` neither calls it nor is on the path between them. The patch works only
  because both names bind the same `spec4.project_manager` module object. Site:
  `tests/test_designer_fullscreen.py:97`.

`spec4.project_manager.load_feature_specs` and `.save_usage` sit in the same shape but
are **keep**: `project_manager.py` is a deliberate façade after 4b (§17), re-exporting
both in `__all__`, and five production modules read them off it by that name. The
façade is the public seam.

#### Kind 2 — `patch.object(…)`

**111 sites, 32 distinct (object, attribute) pairs. All 32 resolve.** The object is a
local name; it was resolved through the test module's own import table.

| Object.attribute (sites) | Resolves to | 5-sub-phase | Disposition |
|---|---|---|---|
| `providers.list_models` (13) | `spec4.providers.list_models` | 5o | keep |
| `code_scanner.llm.stream_turn` (11) | `spec4.llm.stream_turn` | 5j / 5o2 | keep |
| `agentifier._call_scout` (5) | `spec4.agentifier.agentifier._call_scout` | 5k | keep |
| `agentifier.project_manager.load_prior_ai_features` (5) | `spec4.project_manager.…` | 5k / 5o | keep |
| `dmod._refine._start_gen` (5) | `spec4.callbacks.designer._refine._start_gen` | 5m | keep |
| `llm_selection.offered_efforts` (5) | `spec4.llm_selection.offered_efforts` | none | keep |
| `artifact_view_callbacks.ctx` (4) | `spec4.callbacks._artifacts.ctx` | 5m | keep |
| `brainstormer.llm.build_system_prompt` (4) | `spec4.llm.build_system_prompt` | 5c/5j / 5o2 | keep |
| `deployer.llm.build_system_prompt` (4) | `spec4.llm.build_system_prompt` | 5i / 5o2 | keep |
| `deployer.llm.stream_turn` (4) | `spec4.llm.stream_turn` | 5i / 5o2 | keep |
| `_seam_check.complete_stream` (4) | `spec4.agents._seam_check.complete_stream` | 5h | keep |
| `version_check.urllib.request.urlopen` (4) | `urllib.request.urlopen` | none | keep |
| `agentifier.project_manager.detect_stale_inputs` (3) | `spec4.project_manager.…` | 5k / 5o | keep |
| `agentifier.project_manager.resolve_phase_version` (3) | `spec4.project_manager.…` | 5k / 5o | keep |
| `agentifier.project_manager.latest_implemented_version` (3) | `spec4.project_manager.…` | 5k / 5o | keep |
| `brainstormer.llm.stream_turn` (3) | `spec4.llm.stream_turn` | 5c/5j / 5o2 | keep |
| `_seam_check._extract_graph` (3) | `spec4.agents._seam_check._extract_graph` | 5h | keep |
| `_seam_check.supports_response_format` (3) | `spec4.agents._seam_check.…` | 5h | keep |
| `brainstormer.run` (3) | `spec4.agents.brainstormer.run` | 5j | keep |
| `version_check.fetch_latest_version` (3) | `spec4.version_check.…` | none | keep |
| `version_check.check_for_update` (3) | `spec4.version_check.…` | none | keep |
| `agentifier._run_catalog_phase` (2) | `spec4.agentifier.agentifier._run_catalog_phase` | 5k | keep |
| `code_scanner._collect_files` (2) | `spec4.agents.code_scanner._collect_files` | 5h/5j | keep |
| `deployer.project_manager.load_deployment_plan` (2) | `spec4.project_manager.…` | 5i / 5o | keep |
| `dmod.ctx` (2) | `spec4.callbacks.designer.ctx` | 5m | keep |
| `stack_advisor._format_stack_as_text` (2) | `spec4.agents.stack_advisor.…` | 5a | keep |
| `agentifier._stream_suppressing_json` (1) | `spec4.agentifier.agentifier.…` | 5k | keep |
| `agentifier.load_patterns` (1) | `spec4.agentifier.agentifier.load_patterns` | 5l | keep |
| `agentifier._registry.stream` (1) | `SubAgentRegistry.stream` | 5k | keep |
| `code_scanner.llm.supports_response_format` (1) | `spec4.llm.…` | 5j / 5o2 | keep |
| `websearch.validate` (1) | `spec4.websearch.validate` | 5p | keep |
| `llm_selection.default_provider_model` (1) | `spec4.llm_selection.…` | none | keep |

No dead entries and nothing stale. `patch.object` is structurally safer than the string
form here: the object is imported, so a moved name fails at import time rather than
resolving to something that no longer matters. **That is the shape kind 1's rewrites
should move toward.**

#### Kind 3 — `inspect.getsource(`

**Zero uses.** See §50.0(d). The one instance §43 recorded —
`tests/test_designer.py`'s `TestRefinePersistsManifest`, asserting
`"_persist_manifest(" in inspect.getsource(_start_gen)` — was rewritten at 5m (§44.4).
The behaviour it stood in for is **D-DM9** — *a refine draw must still persist the
manifest; persistence is not gated on the draw kind*. §44.4 replaced the two source
substrings with a behavioural assertion in the same file, class and test name: run
`_start_gen` on a refine draw with `_persist_manifest` patched and assert it was called.
So the answer to "is a behavioural test already covering it elsewhere in the file" is
that the rewrite **is** that test — there was no second one, and there is no residue to
clean up. Nothing else in the suite reads Python source through `inspect`.

#### Kind 4 — private-name imports and private attribute access

`from spec4.<x> import _<name>` plus `<module>._<name>` on an imported module,
excluding dunders and excluding names that are themselves modules.

**583 sites, 176 distinct private names, across 35 target modules.** Grouped by target
module; a module with more than five private names imported by tests is one
`rewrite to public seam` **cluster**, not five individual rewrites.

| Target module | Names | Sites | 5-sub-phase | Disposition |
|---|---:|---:|---|---|
| `spec4.agentifier.agentifier` | **34** | 87 | 5k | **cluster** |
| `spec4.layouts._chat` | **14** | 43 | 5n / 4f | **cluster** |
| `spec4.session` | **10** | 57 | 5o | **cluster** |
| `spec4.callbacks.designer` | **10** | 90 | 5m / 4h | **cluster** |
| `spec4.project_manager` | **8** | 22 | 5o / 4b | **cluster** |
| `spec4.agents.brainstormer` | **8** | 26 | 5c, 5j | **cluster** |
| `spec4.layouts` | **7** | 18 | 5n | **cluster** |
| `spec4.agents.code_scanner` | **7** | 44 | 5b, 5h, 5j / 4c | **cluster** |
| `spec4.layouts.designer` | **7** | 24 | 5n | **cluster** |
| `spec4.agents._seam_check` | **6** | 6 | 5h | **cluster** |
| `spec4.llm` | **6** | 25 | 5o2 | **cluster** |
| `spec4.agents.phaser` | 5 | 24 | 5i / 4e | keep |
| `spec4.agents.feature_speccer` | 4 | 19 | 5h | keep |
| `spec4.agentifier.linker` | 4 | 4 | 5l | keep |
| `spec4.agentifier.scout` | 4 | 7 | none | keep |
| `spec4.agentifier.tier_analyst` | 4 | 4 | none | keep |
| `spec4.agentifier.spec_drafter` | 3 | 4 | none | keep |
| `spec4.layouts._agent_rows` | 3 | 3 | 5n | keep |
| `spec4.agents.deployer` | 3 | 9 | 5i | keep |
| `spec4.layouts._status_bar` | 3 | 4 | 5n | keep |
| `spec4.agents.stack_advisor` | 3 | 9 | 5a, 5j / 4d | keep |
| `spec4.streaming` | 2 | 25 | Phase 3 | **keep — §50.3** |
| `spec4.agentifier.composer` | 2 | 2 | 5l | keep |
| `spec4.agentifier.cross_cutting_analyst` | 2 | 2 | none | keep |
| `spec4.agentifier.prioritizer` | 2 | 2 | none | keep |
| `spec4.callbacks` | 2 | 2 | 5m / 4g | keep |
| `spec4.layouts._shared` | 2 | 2 | 5n | keep |
| `spec4.feature_specs` | 2 | 2 | 5o | keep |
| `spec4.layouts._artifact_view` | 2 | 2 | 5n | keep |
| `spec4.websearch` | 2 | 8 | 5p | keep |
| `spec4.agentifier.pattern_loader` | 1 | 2 | 5l | keep |
| `spec4.agents._phase_coverage` | 1 | 1 | 5h | keep |
| `spec4.layouts._round_cost` | 1 | 1 | 5n | keep |
| `spec4.layouts._round_tree` | 1 | 1 | 5n | keep |
| `spec4.layouts._setup` | 1 | 2 | 5n | keep |

**Eleven clusters**, covering 117 of the 176 names and 442 of the 583 sites. Every one
sits on a module a Phase 4 split or a Phase 5 sub-phase moved, which is why they are
clusters: each is a module whose *internal shape* the tests have memorised. Three are
worth naming:

- **`spec4.agentifier.agentifier` — 34 private names.** The single largest coupling in
  the suite. 5k decomposed its three phase runners and 5l its siblings; the tests reach
  past all of it. The public seam is `run()` and the sub-agent registry.
- **`spec4.callbacks.designer` — 10 names, 90 sites.** 4h turned this module into a
  package and 5m decomposed it; three of the ten "names" are the *submodules*
  (`_mock_gen`, `_refine`, `_wizard`) reached through the package `__init__`.
- **`spec4.layouts._chat` — 14 names, 43 sites.** 4f split this file into three
  siblings; the tests import pill constants and panel builders by private name.

`spec4.streaming` is marked **keep** despite the count: its two names are `_STREAMS`
and `_USAGE_RECORDS`, and 25 of its sites are in
`tests/test_streaming_characterization.py`, which is Phase 1 net (§50.3). The net wins.

#### Kind 5 — `sys.modules[` and `importlib.reload(`

**One `sys.modules` use, zero `importlib.reload` uses.**

| Site | Target | Reason given | Disposition |
|---|---|---|---|
| `tests/test_cost_summary.py:624` (`TestOneRenderer::test_both_surfaces_call_the_one_renderer`) | `sys.modules["spec4.layouts._round_cost"]` | **Stated, in a comment above the line:** "By `sys.modules`, not `import … as`: `spec4.layouts` re-exports the `_round_cost` *function*, which shadows the submodule of that name on the package." | keep |

The reason is exact and still true: `spec4.layouts` exports a function named
`_round_cost`, so `from spec4.layouts import _round_cost` cannot reach the module. The
test then `monkeypatch.setattr`s `cost_strip_lines` on it to prove both screens call the
one renderer. A rename of either the function or the submodule would remove the need
for the idiom — a Phase 7 naming note, not a Phase 6 rewrite. **No reload anywhere**,
which also means no test depends on import-order side effects.

#### Kind 6 — assertions on `__name__` / `__module__` / `__qualname__` / `__file__`

**49 sites. 45 are `type(component).__name__` or `.__module__` on Dash components** —
that is component-class identity ("this row is a `Group`, not a `Stack`"), which is
rendered-output assertion, not module layout. `keep`, all of them; two of the 45 are
`type(c).__module__.startswith("dash_mantine_components")` in the two wizard-register
modules, same category.

**Four read `__file__` on a production module:**

| Site | Expression | What it reads | 5-sub-phase | Disposition |
|---|---|---|---|---|
| `tests/test_deployer_invariants.py:43` | `Path(deployer.__file__).read_text()` | `deployer.py` **source text**, asserted for prompt strings | 5i | keep |
| `tests/agentifier/test_try_again.py:44,74,79` | `Path(agentifier.__file__).read_text()`, regex `"(agentifier_[a-z_]+)"` | `agentifier.py` **source text**, for the set of session keys it names | **5k** | keep, with a note |
| `tests/test_artifact_view.py:1467` | `Path(artifact_view.__file__).parent.parent / "assets" / "v3.css"` | locates the **stylesheet**, not Python | 5n | keep |
| `tests/test_status_bar.py:338` | `Path(app_module.__file__).parent / "assets" / "v3.css"` | locates the **stylesheet**, not Python | — | keep |

The last two use `__file__` only as a path anchor and read CSS; §43 already ruled that
category legitimate. The first is §43's row, which passed unmodified through 5i's
398→173-line decomposition because prompt strings move verbatim.

**The `test_try_again.py` reader is new since §43 was written** and belongs on that
list: it regexes `agentifier.py`'s source for `"agentifier_*"` session-key literals and
asserts the set. It survives today because 5k moved code *within* `agentifier.py`. It
would break silently — as a shrinking set, not an error — if a future split moved a
phase runner into a sibling, exactly the way 4c–4i moved code. Phase 6 should note it;
the assertion is better expressed against `app_constants` or a key registry than
against a file's text.

#### Counts per kind

| Kind | Distinct targets | Sites | Resolve today | Flagged |
|---|---:|---:|---|---|
| 1 `patch("spec4.…")` | 61 | 599 | **61 / 61** | 1 dead, 3 stale |
| 2 `patch.object(…)` | 32 | 111 | **32 / 32** | 0 |
| 3 `inspect.getsource(` | 0 | 0 | — | 0 |
| 4 private names | 176 | 583 | n/a (import-time) | 11 clusters |
| 5 `sys.modules[` / `reload` | 1 / 0 | 1 | 1 / 1 | 0 (reason stated) |
| 6 dunder on production objects | 4 | 49 | 4 / 4 | 1 note |
| **Total** | | **1,343** | | |

**Nothing in the suite is broken and nothing resolves to a name that has moved.**
Phase 5 moved 250+ helpers without leaving a single unresolvable patch string — the
per-sub-phase gates caught them as they happened. The staleness that did accumulate is
the quieter kind: one patch that can no longer fail, three that name a module which no
longer performs the operation, and 583 sites that have memorised private layout.

#### The ten test files with the highest coupling totals

| Total | patch-string | patch.object | private-name | dunder | File | In §50.3? |
|---:|---:|---:|---:|---:|---|---|
| 142 | 79 | 0 | 63 | 0 | `tests/test_agents.py` | no |
| 85 | 10 | 9 | 66 | 0 | `tests/test_designer.py` | no |
| **58** | 1 | 0 | 57 | 0 | `tests/test_streaming_characterization.py` | **yes — keep** |
| 57 | 41 | 7 | 9 | 0 | `tests/test_agent_llm_selection.py` | partly (4 node ids) |
| 56 | 21 | 0 | 35 | 0 | `tests/agentifier/test_agentifier_orchestrator.py` | no |
| 55 | 40 | 0 | 15 | 0 | `tests/test_llm.py` | no |
| 50 | 32 | 1 | 17 | 0 | `tests/test_usage_capture.py` | no |
| 37 | 26 | 0 | 10 | 1 | `tests/agentifier/test_try_again.py` | no |
| 34 | 30 | 0 | 4 | 0 | `tests/agentifier/test_streaming_e2e.py` | no |
| 34 | 0 | 14 | 20 | 0 | `tests/test_code_scanner_progress.py` | partly (6 node ids) |

86 of 122 test modules carry at least one coupling row. **96 of the 1,343 rows land on
a §50.3 file** (`test_streaming_characterization.py` 58, `test_layout_contract.py` 14,
`test_callback_co_presence.py` 14, `test_renderer_goldens.py` 6,
`test_project_manager_golden.py` 4; `test_app_import_smoke.py` and
`test_import_layering.py` carry none). **All 96 are `keep` regardless of what the
coupling analysis says about them** — the net wins over decoupling.

### 50.3 Phase 1 net: the off-limits list

Phase 6 may prune and reshape tests. The net that made Phases 2–5 safe is not prunable.
Enumerated here so the exclusion is checkable by `git diff --stat` rather than by
argument.

Built from three sources and unioned. **Amended by §50.5: the floor is the tier-A +
tier-B union, 456 tests across 53 files.** The tier-A subset — 273 tests across 42
files — is retained below as written and is no longer the floor on its own. (The
as-committed text read "273 tests across 53 files"; 53 is the A+B file count, 42 the
tier-A one. Corrected here, nothing else in §50.3 changes.)

#### Source 1 — added or extended by Phase 1

`git diff --stat aff7246..8b277fd -- tests/` (*Phase 0 complete* → *Phase 1 followup*):
**52 files changed, 4,706 insertions, 0 deletions.** Phase 1 added only; it edited no
existing test file, exactly as §12 claims.

| File | Tests today | Source | Invariant guarded |
|---|---:|---|---|
| `tests/test_layout_contract.py` | 74 | 1 | The component-id snapshot over 72 screens — Rule 4 for component ids, in the direction `test_callback_co_presence.py` does not cover. Plus a smoke assertion that every layout serialises. |
| `tests/test_renderer_goldens.py` | 22 | 1 | Byte-exact output of all five artifact renderers. This is what let 5a/5b/5c/5d/5e decompose 60+ render functions with a mechanical check. |
| `tests/test_project_manager_golden.py` | 17 | 1 | `render_phase_markdown` / `parse_phase_markdown` round-trip, frontmatter format, `save_phases` file set and stale-file removal, `save_readme` footer idempotence. |
| `tests/test_streaming_characterization.py` | 16 | 1 | Contents of the three Phase 3 state containers at every transition (§12.2). This is the test that made Phase 3 possible. |
| `tests/test_app_import_smoke.py` | 2 | 1 | **D-LR1** as at startup, in a subprocess whose first import is `spec4.app`: litellm env, both callback modules imported, registry populated, `page-content` carrying `disable_n_clicks`, and `--version`. |
| `tests/_golden.py` | (helper) | 1 | `assert_golden` / `load_fixture` and the `SPEC4_UPDATE_GOLDENS` escape hatch. |
| `tests/snapshots/component_ids.json` | (data) | 1 | The checked-in id contract: 72 screens, reviewed by eye. |
| `tests/golden/*.md` (25), `tests/golden/fixtures/*.json` (20) | (data) | 1 | The pinned outputs and their inputs. |

**131 tests.** Still exactly the 131 Phase 1 wrote — no test was added to or removed
from these five files in Phases 2–5.

#### Source 2 — standing contract files and ordering assertions

| File / node id | Tests | Source | Invariant guarded |
|---|---:|---|---|
| `tests/test_callback_co_presence.py` — **whole file** | 50 | 2 | The id contract. Walks the real callback registry against every layout the app can render and fails any callback that is *half* present. Dash silences this class of bug at definition time; only the rendered tree shows it. It caught the model-gate/chip bug. |
| `test_code_scanner_progress.py::TestScanIsNarrated::test_first_chunk_arrives_before_the_walk` | 1 | 2 | The intro is yielded **before** the slow directory walk. |
| `test_code_scanner_progress.py::TestScanIsNarrated::test_narration_closes_before_the_llm_text` | 1 | 2 | `out.index("Scan complete") < out.index("DRAFT-BODY")`. |
| `test_code_scanner_progress.py::TestLayout::test_complete_state_keeps_its_buttons_and_gains_the_counter` | 1 | 2 | Open sits immediately before the Download it belongs to. |
| `test_code_scanner_progress.py::TestLayout::test_elapsed_sits_beside_the_counter_in_the_action_row` | 1 | 2 | `ids.index("chat-elapsed") == ids.index("chat-token-count") + 1`. |
| `test_code_scanner_progress.py::TestLayout::test_pre_panel_agentifier_pairs_counter_with_elapsed` | 1 | 2 | Same adjacency on the Agentifier pre-panel. |
| `test_code_scanner_progress.py::TestElapsedTicker::test_ticker_repaints_after_every_render` | 1 | 2 | The ticker is not short-circuited between renders. |
| `test_cost_summary.py::TestStripNumbers::test_it_mounts_all_three_lines` | 1 | 2 | The three cost-strip lines and their order. |
| `test_cost_summary.py::TestChatPlacement::test_sits_between_the_transcript_and_the_action_row` | 1 | 2 | `chat-scroll-area < cost-summary-card < chat-token-count`. |
| `test_cost_summary.py::TestDesignerPlacement::test_preview_step_shows_the_strip` | 1 | 2 | `mock-iframe < cost-summary-card`. |
| `test_agent_llm_selection.py::TestAgentKeys::test_seven_user_facing_agents` | 1 | 2 | `len(AGENT_KEYS) == 7`. |
| `test_agent_llm_selection.py::TestAgentKeys::test_matches_the_agent_select_rows` | 1 | 2 | `tuple(key for key, *_ in _AGENT_ROWS) == AGENT_KEYS` — row order **is** key order. |
| `test_agent_llm_selection.py::TestModelChipPlacement::test_it_shares_a_row_with_the_status_line_and_comes_first` | 1 | 2 | `ids == ["btn-agent-llm-chip", "chat-status-line"]`. |
| `test_agent_llm_selection.py::TestModelChipPlacement::test_the_gate_still_suppresses_it` | 1 | 2 | The chip is suppressed while the gate is open — the other half of the co-presence bug. |

**62 tests** (50 + 12).

#### Source 2 (continued) — every test whose own name or docstring cites a D-number

**105 distinct D-numbers are referenced across `tests/`.** Attribution was computed by
AST, at three tiers, so the boundary is a fact rather than a judgement:

| Tier | Definition | Tests | Files |
|---|---|---:|---:|
| **A** | The **test's own** name or docstring cites a D-number | **73** | 34 |
| B | Its **class's** name or docstring cites one; the test's own does not | 183 | 19 |
| C | Only its **module** docstring cites one | 698 | 39 |

**Tiers A and B are both in the net** — §50.5 adopted the wider reading, so the floor
is 456. Tier A is enumerated per test below; tier B is enumerated per class, which is
its natural granularity (the class docstring names the D-number and every test under it
inherits the attribution). Tier C is **not** in the net: a module docstring citing a
D-number does not make each of its 698 tests a lock on it, and including it would
freeze 22% of the suite against a phase whose purpose is to prune.

| File | Node id | D-number(s) |
|---|---|---|
| `agentifier/test_chars_counter_seed.py` | `TestBreadthTurnSeedsTheCounter::test_counter_does_not_dip_below_the_progress_text` | D-AT3 |
| `agentifier/test_ff_sweep.py` | `TestSweepFailureHandling::test_failure_dump_written_in_dev_mode` | D-AF7 |
| `agentifier/test_ff_sweep.py` | `TestSweepFailureHandling::test_ff_press_resumes_after_pause` | D-AF5 |
| `agentifier/test_ff_sweep.py` | `TestSweepFailureHandling::test_loop_path_failure_appends_error_to_messages` | D-AF5 |
| `agentifier/test_ff_sweep.py` | `TestSweepFailureHandling::test_persistent_failure_pauses_with_partial_review` | D-AF5 |
| `agentifier/test_ff_sweep.py` | `TestSweepFailureHandling::test_retry_once_recovers_transient_failure` | D-AF6 |
| `agentifier/test_try_again.py` | `TestPanelButton::test_hidden_once_the_panel_is_submitted` | D-TA6 |
| `agentifier/test_try_again.py` | `TestPanelButton::test_panel_offers_the_guidance_box` | D-TA7 |
| `test_agent_llm_selection.py` | `TestGateButtonEmphasis::test_no_gate_component_names_a_colour_beyond_neutral` | D-LR2 |
| `test_agent_llm_selection.py` | `TestGateEffortOptions::test_it_keys_on_the_draft_provider_not_the_default_s` | D-EF4 |
| `test_agent_pill_click.py` | `TestNoEnabledButtonIsRefused::test_every_enabled_button_navigates` | D-BB3 |
| `test_agent_rows.py` | `TestLastModelEffort::test_an_agent_that_has_not_run_is_still_blank` | D-AR3 |
| `test_agent_rows.py` | `TestTheButtonRoutesLikeTheOldOnes::test_the_action_carries_the_existing_agent_select_id` | D-AR2 |
| `test_agent_rows.py` | `TestTheSixActionVariants::test_continue_is_the_same_button_as_start` | D-AR1 |
| `test_agent_rows.py` | `TestTheSixActionVariants::test_no_button_names_a_colour_but_needs_update` | D-LR2 |
| `test_agentifier_chars_counter.py` | `TestLayoutGate::test_first_post_panel_turn_shows_the_counter` | D-AT2 |
| `test_agentifier_chars_counter.py` | `TestLayoutGate::test_pre_panel_build_shows_the_counter` | D-AT5 |
| `test_app_constants.py` | `TestDarkTheme::test_primary_color_is_the_registered_accent` | D-LR2 |
| `test_artifact_view.py` | `TestArtifactControls::test_neither_button_names_a_colour_of_its_own` | D-LR2 |
| `test_artifact_view.py` | `TestTheAllowedSet::test_usage_json_has_no_producer` | D-LR3 |
| `test_artifact_view.py` | `TestTheHeader::test_it_names_no_colour_of_its_own` | D-LR2 |
| `test_artifact_view.py` | `TestTheMissingMessage::test_usage_json_names_no_producer` | D-LR3 |
| `test_artifact_view.py` | `TestTheNavEntry::test_it_is_plain_text_with_no_colour_of_its_own` | D-LR2 |
| `test_artifact_view.py` | `TestTheRoundSelector::test_it_names_no_colour_of_its_own` | D-LR2 |
| `test_chat_action_row_emphasis.py` | `TestTheWarnTone::test_re_scan_is_the_row_s_only_coloured_action` | D-LR2 |
| `test_chat_pill_bar.py` | `TestTheIdsAreUnchanged::test_the_bar_holds_no_control_but_the_pills` | D-LR8 |
| `test_chat_pill_bar.py` | `TestTheStylesheetDrawsThem::test_the_active_state_uses_the_navs_mechanism` | D-LR2 |
| `test_chat_transcript_blocks.py` | `TestMonospaceFigures::test_none_of_them_carries_a_colour` | D-LR2 |
| `test_code_scanner_progress.py` | `TestLayout::test_elapsed_renders_even_when_the_agent_has_no_buttons` | D-AT5 |
| `test_code_scanner_progress.py` | `TestLayout::test_pre_panel_agentifier_pairs_counter_with_elapsed` | D-AT5 |
| `test_cross_cutting_relocation.py` | `TestDeployerContextDropsRelocatedKeys::test_catalog_provider_recommendation_not_surfaced` | D-DE7 |
| `test_deployer_ai_channel.py` | `test_catalog_provider_strategy_is_not_rendered` | D-DE7 |
| `test_deployer_env_and_semantics.py` | `TestEnvironmentIsAssembledNotAsked::test_brownfield_code_review_keeps_precedence` | D-DE9 |
| `test_designer.py` | `TestManifestInstruction::test_capture_manifest_directive_has_its_planning_inputs` | D-DM7 |
| `test_designer.py` | `TestManifestInstruction::test_refine_includes_manifest_directive` | D-DM9 |
| `test_designer.py` | `TestMockDeliveryAck::test_delivery_preserves_prior_store_keys` | D-DM8 |
| `test_designer_wizard_register.py` | `TestOnePrimaryPerStep::test_the_primary_takes_the_theme_accent` | D-LR2 |
| `test_designer_wizard_register.py` | `TestStepRow::test_the_row_comes_from_the_shared_renderer` | D-LR9 |
| `test_entry_screens.py` | `TestThePickerHasOneEmphasis::test_select_is_the_only_filled_action` | D-LR2 |
| `test_feature_speccer_generative.py` | `TestReceiptCounter::test_counter_climbs_and_seeds_from_pre_call_value` | D-BS10 |
| `test_phaser_seed_inputs.py` | `test_prompt_hardened_exclusion_and_addition_join_keys` | D-PH7 |
| `test_phaser_seed_inputs.py` | `test_retry_drain_publishes_cumulative_received_count` | D-PH9 |
| `test_phaser_seed_inputs.py` | `test_seed_vision_block_states_supersession` | D-PH7 |
| `test_phaser_seed_inputs.py` | `test_silent_retry_yields_status_line_and_prompt_names_coordinators` | D-PH2, D-PH6 |
| `test_project_manager.py` | `TestPhaseSpecPreamble::test_budgets_and_eval_approach_never_reach_the_coder` | D-PS13 |
| `test_round_cost.py` | `TestPlacement::test_it_sits_between_the_rows_and_the_tree` | D-LR11 |
| `test_round_cost.py` | `TestUnknownIsNotZero::test_an_empty_round_says_no_activity_not_unknown_price` | D-RC1 |
| `test_round_tree.py` | `TestItClosesTheProjectView::test_the_tree_is_the_last_of_the_three` | D-LR11 |
| `test_round_tree.py` | `TestRendering::test_no_line_names_a_colour` | D-LR2 |
| `test_round_tree.py` | `TestTheCallbackRecomputes::test_it_sees_a_file_written_after_the_last_render` | D-LR4 |
| `test_session.py` | `TestLoadWorkingDir::test_picking_a_directory_reopens_the_question` | D-PM1 |
| `test_setup_wizard_register.py` | `TestEffortSelect::test_the_value_is_keyed_on_the_resolved_provider_and_model` | D-EF4 |
| `test_setup_wizard_register.py` | `TestOnePrimaryPerStep::test_the_primary_takes_the_theme_accent` | D-LR2 |
| `test_setup_wizard_register.py` | `TestStepIndicator::test_the_indicator_comes_from_the_shared_renderer` | D-LR9 |
| `test_stack_ai_features_context.py` | `test_rejected_block_preserves_the_spine_features_ordinary_stack` | D-SC56 |
| `test_stack_exemplar_demonstrates_linkage.py` | `test_every_licensed_field_is_demonstrated_where_its_prose_licenses_it` | D-SC50 |
| `test_stack_exemplar_demonstrates_linkage.py` | `test_every_project_specific_exemplar_id_is_domain_loaded` | D-SC52 |
| `test_stack_persistence_block.py` | `test_at_least_one_exemplar_collection_holds_no_entity` | D-SC50 |
| `test_stack_persistence_block.py` | `test_every_exemplar_collection_says_what_it_holds_or_what_it_is_for` | D-SC51 |
| `test_stack_persistence_block.py` | `test_every_exemplar_library_carries_a_purpose` | D-SC27 |
| `test_stack_persistence_block.py` | `test_exemplar_infra_entry_points_at_its_library` | D-SC22, D-SC36 |
| `test_stack_persistence_block.py` | `test_exemplar_nfr_ids_are_domain_loaded` | D-SC23 |
| `test_stack_render_totality.py` | `test_legacy_string_languages_still_render` | D-SC26 |
| `test_stack_render_totality.py` | `test_unknown_top_level_key_still_renders` | D-SC33 |
| `test_stack_shape_resilience.py` | `test_flat_libraries_list_passes_through_untouched` | D-SC27 |
| `test_stack_shape_resilience.py` | `test_keyed_libraries_fold_into_the_flat_list` | D-SC27 |
| `test_stale_ai_features.py` | `test_stale_mock_allows_stack_advisor` | D-BB1, D-SC5 |
| `test_status_bar.py` | `TestOnlyThePathEverGivesUpSpace::test_the_path_keeps_its_monospace_and_names_no_colour` | D-LR2 |
| `test_status_bar.py` | `TestStatusBarLayout::test_no_nav_entry_names_a_colour` | D-LR2 |
| `test_status_bar.py` | `TestTheBarOpensSetup::test_it_is_dressed_as_the_directory_is` | D-LR2 |
| `test_status_bar.py` | `TestTheModelSlotCarriesTheEffort::test_the_suffixed_slot_still_refuses_to_truncate` | D-LR10 |
| `test_visual_register.py` | `TestNoMarketingChrome::test_the_exception_is_one_line` | D-LR2 |
| `test_visual_register.py` | `TestSingleAccent::test_no_layout_module_hard_codes_the_accent` | D-LR2 |

**73 tests.**

#### Source 2 (continued) — tier B: tests whose *class* cites a D-number

Adopted into the net by §50.5. Enumerated per class, because that is where the
attribution lives: the class docstring or name cites the D-number and every test
under it is in the net. **All tests in each class listed here are off-limits**, so a
`git diff --stat` over the class is the check, the same as for the whole-file entries.

**`test_project_manager.py`** — 29 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestPhaseSpecPreamble` | 13 | D-PS2, D-PS4 |
| `TestPreambleTwoAltitudesAndSurfaces` | 6 | D-PH5 |
| `TestRenderPhaseStackRoutingAndNfr` | 5 | D-PH3, D-PH4 |
| `TestSessionIsBrownfield` | 5 | D-PM1 |

**`test_agent_rows.py`** — 22 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestAMissingUsageEntry` | 7 | D-AR3 |
| `TestItLeadsTheProjectView` | 6 | D-LR11 |
| `TestTheSixActionVariants` | 9 | D-AR1 |

**`test_seam_check.py`** — 18 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestDeclarationAlignment` | 9 | D-PS15 |
| `TestDeclarationAlignmentTwoArraySchema` | 5 | D-PH2 |
| `TestExtractGraphTransport` | 4 | D-PH9 |

**`test_agents.py`** — 16 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestAiFeaturesForPhaserFullSurface` | 8 | D-PS3 |
| `TestLoadDesignManifest` | 4 | D-SC5 |
| `TestPhaserSpecReferenceDirective` | 4 | D-PS14 |

**`test_status_bar.py`** — 16 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestOnlyThePathEverGivesUpSpace` | 7 | D-LR10 |
| `TestTheStylesheetPinsWhatTheLayoutMarks` | 9 | D-LR10 |

**`test_stack_advisor_token_counter.py`** — 15 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestCounterGate` | 8 | D-SC62 |
| `TestSuppressedStreamPublishesReceipt` | 7 | D-SC60 |

**`test_designer.py`** — 12 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestCapturePassesPlanningContext` | 5 | D-DM7 |
| `TestRefinePersistsManifest` | 2 | D-DM9 |
| `TestRetryReproducesTheDraw` | 5 | D-DM8 |

**`test_agent_llm_selection.py`** — 10 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestOfferedEfforts` | 10 | D-EF2 |

**`test_phase_coverage.py`** — 7 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestExcludedDisposition` | 3 | D-PH1, D-PH2 |
| `TestProductDependencyOrdering` | 4 | D-PH2 |

**`test_stream_error_recovery.py`** — 6 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestEmptyTurnBackstop` | 6 | D-ER2 |

**`test_designer_wizard_register.py`** — 5 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestNoBackToTheProjectView` | 5 | D-LR8 |

**`test_feature_specs.py`** — 5 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestPhaseSpecFields` | 5 | D-PS13 |

**`test_stack_routing.py`** — 5 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestDerivedNfrIds` | 5 | D-SC2 |

**`test_project_mode.py`** — 4 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestDesignerFollowsTheAnswer` | 4 | D-PM1 |

**`integration/test_chat_frame_e2e.py`** — 3 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestTheBackRoutesHaveLiveEquivalents` | 3 | D-LR8 |

**`test_callbacks_stream_poll.py`** — 3 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestStreamedTokenCounter` | 3 | D-PH9 |

**`test_round_tree.py`** — 3 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestUsageIsNeverStale` | 3 | D-LR3 |

**`test_chat_open_links.py`** — 2 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestTheOpenButtonsRegister` | 2 | D-LR2 |

**`test_deployer_env_and_semantics.py`** — 2 tests

| Class (all its tests) | Tests | D-number(s) |
|---|---:|---|
| `TestEarlierGuidanceSurvives` | 2 | D-DE8 |

**183 tests in 19 files, across 33 classes.**

#### Source 3 — regression locks added during Phases 2–5

Collected by comparing test-function names in `8b277fd` against `HEAD` for every
touched test file. **Seven tests, one file, one sub-phase.**

| File / node id | Tests | Source | Invariant guarded |
|---|---:|---|---|
| `tests/test_import_layering.py` — **whole file** | 7 | 3 | The `ast`-based layering contract §6.3 chose over import-linter (§15.3): `layouts` never imports `callbacks`; the agent side never imports the Dash side; nothing imports `app`; a private callback module never imports its own package. Plus three tests of the walk itself, so the contract cannot pass by finding nothing. |

Nothing else in Phases 2–5 added a test. §44.4's `getsource` rewrite replaced a test
body in place — same file, class and name — and is **not** a source-3 addition; the
test it replaced was not Phase 1 net and the rewritten form is not net either. It is
listed here only so the diff over §50.3 is not surprised by it.

#### The rule for Phase 6

> **The files, classes and node ids in §50.3 may not be edited, renamed, moved, or
> deleted.** **Phase 6 may not lower the floor.** If a specific net test should be
> pruned or rewritten, petition by node id with the reason and **stop for approval
> before touching it** (§50.5).

**How the check is run** (refined on approval — `--stat` is file-shaped and cannot see
a class):

| Entry kind | Check at each sub-phase commit | On a hit |
|---|---|---|
| The 7 whole-file entries | `git diff --stat` over the file — must be absent | **stop** |
| The 19 tier-B files, 33 classes | **diff *hunks* against the listed classes' line ranges** — no hunk may land inside a listed class | **stop** |
| The 85 tier-A / ordering node ids | still collect under their current ids | **stop** |

A tier-B file touched **outside** its listed classes is **allowed, and reported** in the
sub-phase report — those files are not whole-file entries and the rest of them is
ordinary Phase 6 scope. Class line ranges are re-read from the working tree at check
time, not cached from §50.3, so a legitimate edit above a class cannot silently shift
the range out from under the next check.

Where a §50.2 row lands on a §50.3 file it is marked **keep** — 96 coupling rows,
listed at the end of §50.2. The net wins over decoupling. Notably
`tests/test_streaming_characterization.py` is the third-most-coupled file in the suite
(58 rows, 57 of them private-name access to `spec4.streaming`) and is nonetheless
untouchable: reaching into `_STREAMS` and `_USAGE_RECORDS` **is** what it is for.

The floor as a number and as a list:

| Component | Tests | Files |
|---|---:|---:|
| Source 1 — the five Phase 1 modules, whole-file | 131 | 5 |
| Source 2 — `test_callback_co_presence.py`, whole-file | 50 | 1 |
| Source 3 — `test_import_layering.py`, whole-file | 7 | 1 |
| Source 2 — tier-A D-numbered tests outside the above | 73 | 34 |
| Source 2 — named co-presence/ordering tests, less one already in tier A | 12 | 3 |
| *tier-A subtotal* | *273* | *42* |
| Source 2 — tier-B classes outside the above (33 classes) | 183 | 19 |
| **Count floor (§50.5)** | **456** | **53** |

456 is **10.7%** of the 4,257 collected tests. One test —
`test_code_scanner_progress.py::TestLayout::test_pre_panel_agentifier_pairs_counter_with_elapsed`
— qualifies as both a named ordering test and a tier-A D-number test, and is counted
once; that is why the ordering row reads 12 and not 13.

### 50.4 Gate check

The promoted gate as it stood at 5p, run on the tree as found.

| Gate | Command | Result | §49.7 | Match |
|---|---|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) | same | ✅ |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) | same | ✅ |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) | same | ✅ |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4256 passed, 1 skipped in 174.98s` (exit 0) | `4256 passed, 1 skipped in 170.46s` | ✅ (counts) |
| Coverage | same run | `TOTAL 12421 stmts, 893 miss, 93%` | same | ✅ |

Every figure matches the end of §49 exactly. The only difference is wall-clock
(174.98 s vs 170.46 s, 2.6%), which is machine variance on the same 4,257 tests — the
three uninstrumented runs in §50.1 spread 139.14–140.98 s across the same tree.

`git status --porcelain` is empty before and after: the three `pytest` runs, the two
instrumented runs and the two experiment runs wrote only `.coverage`, which is
gitignored and was restored from the pre-run copy.

**Nothing changed between 5p and this run.** Phase 6 starts from `a86a2ee` as recorded.

#### What Phase 6 inherits, in one paragraph

4,257 tests in 126 files (4,175 in `tests/`, 82 in `evals/` — §50.0(e)), 139.9 s
median. No broken coupling — all 61 patch strings and
all 32 `patch.object` targets resolve, and Phase 5 moved 250+ helpers without leaving
one stale. One patch that can no longer fail, three that name a module which no longer
performs the operation, and 583 private-name sites in eleven clusters. Zero
`inspect.getsource`, zero `importlib.reload`, one documented `sys.modules`. **48 s of
the 140 is `MagicMock` auto-child construction in two chunk factories**, recoverable
with no assertion change and nothing in the net touched. The net itself is **456 tests
in 53 files — 10.7% of the suite** (§50.5 raised it from the tier-A 273; that subset
spans 42 files).

### 50.5 Amendments on approval — the terms Phase 6 runs under

§50 approved 2026-09-09 with five amendments. They are binding on Phase 6 and take
precedence over §50.1's proposals where the two differ. §50.1's targets were
*proposals*; what follows are the *terms*.

#### (a) The floor is 456, not 273

The tier-B reading is adopted as **both the count floor and the off-limits set**:
a test whose *class* name or docstring cites a D-number is in the net, the same as one
that cites it itself. §50.3's enumeration now covers all 456 — tier A per test (73),
tier B per class (183 tests in 33 classes), plus the 200 whole-file and ordering
entries. The 273 tier-A list stands unchanged as the subset it always was.

**Phase 6 may not lower the floor.** Not by argument in a sub-phase report, and not by
a collection count that happens to land above it. If a specific net test should be
pruned or rewritten:

1. Petition **by node id**, with the reason.
2. **Stop for approval before touching it.**

That is a hard stop, not a notification. It applies to a rename and a move as much as
to a deletion — the check is `git diff --stat` over the list, and a moved test fails it
the same way a deleted one does.

#### (b) `testpaths` goes first, and alone

**Phase 6's first commit adds `testpaths = ["tests"]` to `pyproject.toml` and nothing
else.** No `src/` change, no test change, no factory change, no coupling rewrite.

`pyproject.toml` has no `[tool.pytest.ini_options]` block at all today, so the first
commit creates it holding that one key.

Then, before anything else is touched, re-run §50.1's three-pass measurement:

```
uv run pytest -q --durations=40 -p no:cacheprovider
```

and record, as a **§50.1 addendum**:

- the re-baselined collected / passed / skipped counts,
- the median wall-clock over the three runs,
- the count floor and the runtime target **restated against those numbers**.

The arithmetic to expect, so a surprise is visible as a surprise: 4,257 − 82 = **4,175
collected**, of which 4,174 pass and 1 skips; ~139.9 s − ~2.6 s ≈ **137 s median**. The
floor is unchanged at 456 — every one of those 456 is under `tests/` — but as a share
of the suite it goes from 10.7% of 4,257 to **10.9% of 4,175**, and the runtime target
of 95 s should be restated as **≤ 92 s** to keep the same headroom. **If the
re-baselined numbers do not match that arithmetic, stop and report rather than
reconcile**, exactly as §50.4 required.

`evals/` remains outside the Rule 6 gate and is now outside collection too. Note that
`tests/conftest.py:65` still puts `evals/scout/` on `sys.path` for
`tests/agentifier/test_fanout_baseline.py` — **that import stays**; `testpaths` scopes
collection, not the path, and removing it would break a passing test.

**Nothing else moves until the addendum is written.**

#### (c) The chunk factory mirrors the real litellm type, not the tests' reach

The `SimpleNamespace` swap is approved in principle. The hazard it must not carry
forward: **a `MagicMock` auto-child satisfies an attribute the real object never has**,
so a test can pass today against a field litellm does not send. A namespace built only
from the attributes the tests happen to reach for would preserve that — silently, and
with the mock gone there would be nothing left to blame.

So the replacement mirrors **`litellm.types.utils.ModelResponseStream`** and its
`StreamingChoices` / `Delta` members — every field the real type carries, and no
others. Verified against the installed litellm by constructing a real
`ModelResponseStream` and reading its fields:

| Type | Fields the namespace must carry |
|---|---|
| `ModelResponseStream` | `id`, `created`, `model`, `object`, `system_fingerprint`, `provider_specific_fields`, `choices` (+ `usage`, which litellm attaches under `include_usage`) |
| `StreamingChoices` | `index`, `delta`, `finish_reason`, `logprobs`, `enhancements` |
| `Delta` | `content`, `role`, `function_call`, `tool_calls`, `audio`, `images`, `reasoning_content`, `thinking_blocks`, `provider_specific_fields` |

What production actually reads off a chunk, for the record — the namespace must satisfy
all of it, and an `AttributeError` anywhere else is the point:

| Site | Read |
|---|---|
| `llm.py:713` | `chunk.choices` (truthiness), `chunk.choices[0].delta.content` |
| `llm.py:887–892` | `chunk.choices[0]`, `choice.delta.tool_calls`, `choice.delta.content` |
| `llm.py:908–920` | `tc.index`, `tc.id`, `tc.function`, `tc.function.name`, `tc.function.arguments` |
| `llm.py:477–487` (`_chunk_usage`) | `chunk.usage`, filtered through `_usage_fields` |
| `llm.py:489–495` (`_hidden_usage`) | `chunk._hidden_params`, gated on `isinstance(hidden, dict)` |

The last two are why the swap is safe on the usage path and why it must still be
checked: under `MagicMock`, `chunk.usage` and `chunk._hidden_params` are truthy
auto-children today, and both helpers already reject them — `_usage_fields` returns
`None` for anything without real counts, and `_hidden_usage` requires an actual `dict`.

**Refined on approval: give `usage` and `_hidden_params` the real litellm defaults.**
The namespace must be rejected by these two helpers *for the reason the real object is
rejected*, not because a `SimpleNamespace` happens to be missing a field. So the
defaults were read off a constructed `ModelResponseStream` rather than assumed, and one
of them is not what it looks like:

| Field | Real default on a chunk with no usage block | Namespace must carry |
|---|---|---|
| `_hidden_params` | **`{}`** — the dict litellm always attaches | `{}` |
| `usage` | **absent** — `hasattr(chunk, "usage")` is `False`; litellm adds it only on the usage chunk under `include_usage` | absent |

So for `usage`, **absence *is* the faithful mirror** — and the refinement's point still
holds, because it is now absence-by-fidelity rather than absence-by-accident, checked
against the real type and recorded here. `_hidden_usage` then rejects `{}` for holding
no `"usage"` key, exactly as it rejects a real chunk; `_chunk_usage` reads
`_get(chunk, "usage")`, whose `getattr(obj, name, None)` fallback yields `None`, and
`_usage_fields(None)` returns `None` on its first line — the same path a real
no-usage chunk takes.

**The usage chunk is a second shape, and the factory needs it.** Under `include_usage`
litellm appends a final chunk that *does* carry `usage` with real counts; that is the
chunk `_record_usage` exists to consume. A factory that can only emit the no-usage
shape would satisfy every negative assertion while quietly severing `_record_usage`
from its input — which is what the positive-path test below is for.

**Confirm with the usage tests specifically**, not by the suite's green alone. **And
additionally run one usage test with a chunk carrying real counts**, to prove the
positive path still reaches the helper and that `_usage_fields` returns a populated
dict rather than `None`.

**State the shape in a comment on the factory and cite the litellm type it mirrors**,
so the next person to add a field knows where the list came from. Both factories change
together — `tests/test_agents.py:49` and
`tests/agentifier/test_agentifier_orchestrator.py:119` define the same one.

#### (d) §50.2 work happens in this order

Three steps, in sequence, each its own sub-phase commit.

**1. The three `spec4.project_manager.os.*` strings — first.** `patch(...)` on
`spec4.project_manager.os.replace` and `.os.fdopen` resolves to the **stdlib `os`
module** and patches it **process-wide**: for the duration, every other file write in
that test — `tmp_path` fixtures, the golden writer, pytest's own bookkeeping — runs
through the mock. That the tests pass is not evidence the blast radius is empty. Rewrite
to the call site's seam. After 4b the atomic writer is `src/spec4/_usage.py:346–359`, so
the seam is `spec4._usage.os.replace` / `spec4._usage.os.fdopen`. Sites:
`tests/test_usage_capture.py:815` and `:838`. The third string —
`spec4.callbacks.designer.project_manager.load_prior_mock`
(`tests/test_designer_fullscreen.py:97`) — is the same rewrite-to-the-seam shape but
carries no process-wide risk; it goes in this commit for coherence, not urgency.

**2. `patch("spec4.callbacks._chat.streaming.pop")` — second, and it is a question
before it is an edit.** The assertion is vacuous: `_chat.py` never references
`streaming.pop`, so `mock_pop.assert_not_called()` cannot fail. **The invariant it
guarded may not be vacuous.** So, in order:

- Determine whether the chat path is **still required not to pop the stream**. §12.2
  and §14 are the evidence: the entry must survive the done-poll so a second racing poll
  returns an `==` terminal store and `finalised` latches once. If popping would break
  that, the requirement is live.
- **If yes:** rewrite to a real assertion at the seam — one that fails if the chat path
  ever pops. Assert on the observable consequence (the entry still present and
  `finalised` after the done branch), not on a mock's call count, so it cannot go vacuous
  again the next time the call site moves.
- **If no:** drop it, and **record why in the sub-phase report** — which requirement was
  checked, against which section, and what made it dead.

Either way the surrounding tests keep every other assertion.

**3. The eleven private-name clusters — last, `spec4.agentifier.agentifier` first.**
34 names, 87 sites, the largest coupling in the suite. Nothing in this step starts
before steps 1 and 2 are committed green.

#### (e) Rule 1 is relaxed for Phase 6, as it was for Phase 5

- **Commit per sub-phase.** Not one commit for the phase.
- **Report per sub-phase**, in `CLEANUP_INVENTORY.md` **§51 onward**.
- **Gate green at each commit** — `ruff check`, `ruff format --check`, `mypy src/`,
  `pytest --cov=spec4`, all four, every commit.
- **The floor and the off-limits list are checked by `git diff --stat` at each commit**,
  not once at the close-out. A sub-phase that touches a net file is not a sub-phase to
  be reconciled later; it stops there.

#### What is unchanged

Everything else in §50 stands as written: §50.0's five disagreements, §50.1's
measurements and the 48.3 s finding, §50.2's full coupling inventory and its
dispositions, §50.3's sources and enumeration, §50.4's gate. The deferred items stay
deferred — 5p(h) type hygiene, the six sub-generator backlog entries, the
`project_manager` root-siblings inconsistency.

## 51. Phase 6a — `testpaths`, and the §50.1 addendum

Commit `fe356ea`. One key added to `pyproject.toml`, nothing else, per §50.5(b).
`git diff --stat` touches no file under `tests/`.

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

The file had no `[tool.pytest.ini_options]` block at all, so this commit creates it.

### 51.1 §50.1 addendum — the re-baseline

Three runs of `uv run pytest -q --durations=40 -p no:cacheprovider`, as §50.1:

| Run | Result | pytest-reported | wall |
|---|---|---:|---:|
| 1 | `4174 passed, 1 skipped` | 143.29 s | 145.08 s |
| 2 | `4174 passed, 1 skipped` | 143.63 s | 144.63 s |
| 3 | `4174 passed, 1 skipped` | 144.84 s | 145.79 s |
| **median** | | **143.63 s** | **145.08 s** |

`--collect-only` reports **4175 collected**.

**Counts match §50.5(b) exactly.**

| | predicted | measured | |
|---|---:|---:|---|
| collected | 4,175 | **4,175** | ✅ |
| passed | 4,174 | **4,174** | ✅ |
| skipped | 1 | **1** | ✅ |

The one skip is still `tests/test_session.py:721`. Zero xfails.

**The median does not match, and §50.5(b)'s prediction was wrong on its own terms.**
Predicted ~137 s; measured 143.63 s. Rather than reconcile, I measured the control —
the pre-`testpaths` collection, on the machine as it is now, by passing the paths
explicitly (which overrides `testpaths`):

| Configuration | tests | median |
|---|---:|---:|
| §50.1, this morning, `tests/` + `evals/` | 4,257 | 139.91 s |
| **control, now**, `tests/` + `evals/` (2 runs: 143.17, 144.91) | 4,257 | **~144.04 s** |
| **after `testpaths`, now**, `tests/` only | 4,175 | **143.63 s** |

Two separate things were folded into one number, and both are now visible:

1. **The machine is ~4 s slower than it was this morning.** The control reproduces the
   *old* configuration at ~144 s where §50.1 measured 139.91 s. No code explains that;
   it is ambient. Every figure in §50.1 was taken in one sitting and is internally
   consistent, but it is not comparable to a figure taken hours later.
2. **My −2.6 s estimate for removing `evals/` was wrong; the true saving is ~0.4 s.**
   Like-for-like on the current machine: 144.04 → 143.63. `evals/` measured 2.59 s
   *standalone*, and I subtracted that figure directly. Most of those 2.59 s are module
   import and interpreter warm-up that `tests/` has already paid inside a full run, so
   the marginal cost of the 82 tests is a fraction of their standalone cost. **82 tests
   removed bought 0.4 s.** The lesson generalises to Phase 6's pruning: *a test's
   standalone time is an upper bound on what deleting it saves, and for cheap tests it
   is a wild one.* Runtime will come from the 50 s finding, not from the count.

**Restated targets.**

| | §50.1 proposal | §50.5(b) restatement | **now, measured** |
|---|---|---|---|
| Count floor | 273 | 456 | **456** — unchanged; 10.9% of 4,175 |
| Runtime target | ≤ 95 s | ≤ 92 s | **≤ 96 s** |

The floor is unchanged and needs no restatement beyond its share: all 456 are under
`tests/`, so `testpaths` cannot have moved it. Verified — the collected count fell by
exactly the 82 `evals/` tests and by nothing else.

The runtime target is restated **upward**, to ≤ 96 s. §50.5(b) derived ≤ 92 s by
subtracting the phantom 2.6 s; with the saving measured at 0.4 s that derivation is
void. Re-measuring the §50.1 experiment on the current tree and current machine — the
scratchpad plugin swapping the chunk factory for a namespace, nothing on disk changed:

| | tests | result | pytest time |
|---|---:|---|---:|
| baseline, post-`testpaths` | 4,175 | `4174 passed, 1 skipped` | **143.63 s** (median) |
| with plain-namespace chunks | 4,175 | `4174 passed, 1 skipped` | **92.88 s** |

**−50.75 s**, up from the 48.3 s measured this morning — the same change, measured on a
slower machine, so it recovers more absolute seconds. 92.88 s is the honest post-fix
figure; **≤ 96 s** is that plus a ~3 s band for the inter-session drift this addendum
just measured. A tighter target would fail on machine weather rather than on the work.

### 51.2 Coverage fell, and it is not noise — Rule 6 needs a ruling

**Misses 893 → 909.** Percentage still rounds to 93%, so the summary line hides it.

No test was deleted. The 16 statements are `src/spec4` lines whose **only** coverage
anywhere in the repo came from the four `evals/` modules that are no longer collected.
Traced by diffing the covered-line sets of two coverage databases — the full
`tests/`-only run, and `evals/` alone:

| Module | stmts | with `evals/` | `tests/` only | lost |
|---|---:|---|---|---:|
| `agentifier/requires_reconciler.py` | 261 | 11 miss (**95%**) | 26 miss (**90%**) | **15** |
| `agents/brainstormer.py` | 314 | 9 miss (**97%**) | 10 miss (**96%**) | **1** |

The 15 are not incidental lines. They are the dependency-inversion signal logic:
`_norm_chunk`'s stemming (156), the stem-length guard (263), the producer-margin
tie-break (306, 353), the **S3 dominant/reverse-overlap classification** including the
"reverse lean, uncorroborated, not classified" arm (363–369), and the **S1/S2 trigger
matching** with its selective vision-feature cap (488, 518–525). `evals/phaser/
test_requires_inversion.py` is the only thing in the repo that exercises them.

**This is a Rule 6 stop, and I have not reconciled it.** Two readings, and they lead to
different actions:

- **The baseline was inflated.** Phase 0's 893 was measured with `evals/` collected, so
  it was never a `tests/`-only figure. On this reading nothing regressed; the correct
  `tests/`-only baseline is **909**, Rule 6 ratchets against that from here, and the 16
  statements become a logged coverage gap.
- **The coverage was real and is now gone.** On this reading `testpaths` must not stand
  until `tests/` covers those 15 statements itself.

**I recommend the first**, with a condition: re-baseline to 909, and log the 15
`requires_reconciler.py` statements as a gap to close with real tests under `tests/` —
Phase 6's own scope if you want it there, otherwise Phase 7. The gap is worth naming
either way. Whichever way it went, the useful fact is the one this commit surfaced:
**a substantive block of `requires_reconciler.py` has never been tested by the test
suite, only by an eval script**, and the pre-`testpaths` 893 was concealing that.

**No pruning, no factory change, no coupling rewrite has started**, per §50.5(b).
Phase 6b does not begin until this addendum and the Rule 6 ruling are approved.

### 51.3 The `evals/` import that survives, and why it is not a leak

`tests/conftest.py:65` puts `evals/scout/` on `sys.path`:

```python
_EVAL_SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "evals" / "scout"
if _EVAL_SCRIPTS.is_dir() and str(_EVAL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_EVAL_SCRIPTS))
```

**This stays, and it is not a collection leak.** `testpaths` scopes *collection*;
`sys.path` is a separate dependency. `tests/agentifier/test_fanout_baseline.py` imports
`fanout_baseline` from `evals/scout/`, which is a script directory rather than a
package; without the insert, that one unimportable module aborts collection for the
whole run — the conftest comment says exactly this and is still accurate. The import is
`tests/` depending on `evals/`, which is a different question from `evals/` being
collected, and it is not this phase's problem.

Recorded here so nobody later reads a surviving `evals/` reference as evidence that
`testpaths` did not take.

### 51.4 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4174 passed, 1 skipped in 178.61s` (exit 0) |
| Coverage | same run | `TOTAL 12421 stmts, 909 miss, 93%` — **see §51.2** |
| Off-limits | §50.5(a) check, all three kinds | **pass** — see below |

### 51.5 The off-limits check, as actually run

| Kind | Result |
|---|---|
| 7 whole-file entries | `git diff --stat` — **no file under `tests/` touched** (this commit changes only `pyproject.toml`) |
| 19 tier-B files, 33 classes | no diff hunk anywhere under `tests/`, so none inside a listed class |
| 188 + 85 + 183 node ids | **456 / 456 still collect**, 0 failures |

The node-id half was run against a fresh `pytest --collect-only -q`, which matters this
commit specifically: `testpaths` changes *collection*, so "does the floor still collect"
is the question it could most plausibly have broken. It did not — the collected count
fell by exactly the 82 `evals/` node ids and by nothing under `tests/`.

**One property of the check worth recording, because getting it wrong produces
convincing false failures.** A listed node id is a *test function*; a parametrized one
collects as `…::test_name[param]` and never as the bare name. The check must therefore
match `nid` **or** any collected id beginning with `nid + "["`. Six of the 456 are
parametrized and failed a first, exact-match version of this check —
`test_agent_rows.py::TestTheSixActionVariants::test_every_state_renders_a_button` and
five others. Nothing was wrong with the tree. Related: a node id must not be truncated
at whitespace when parsing collect output, because parameter ids contain spaces
(`test_layout_contract.py` has `[working_dir: browsing a directory]`); doing so collapses
distinct ids and undercounts the whole-file entries — 125 instead of 188, in the first
version of this check.

### 51.6 Ruling — Rule 6 amended, and two new standing rules

Ruled 2026-09-09 on §51.2. Binding from here.

#### Rule 6, amended: the `tests/`-only baseline is 909

Phase 0's 893 was measured with `evals/` collected and was **never a `tests/`-only
figure**. The gate now measures what it claims to measure.

- **The Rule 6 baseline is 909 misses**, on `tests/` alone, `--cov=spec4`.
- **No sub-phase commit may exceed it.** Same ratchet as before, new number.
- The per-module Phase 0 / Phase 1 floors are unchanged **except** for the two modules
  §51.2 names, which re-baseline to their `tests/`-only figures:
  `agentifier/requires_reconciler.py` **90%** (26 miss) and `agents/brainstormer.py`
  **96%** (10 miss).

#### And the 15 statements come back under test before Phase 6 closes

The second reading of §51.2 was right about the thing that matters. A substantive block
of `requires_reconciler.py` is guarded **only by an eval script outside the gate**. Phase
6 does not touch `src/`, so it is not urgent — but the moment a `src`-touching phase
begins, that block is unprotected. It is therefore a **Phase 6 exit condition**, not a
Phase 7 backlog item.

**Sub-phase 6z, last.** It ports the eval's assertions on those statements into
`tests/agentifier/` as characterisation tests, **named per arm**:

| Arm | Statements |
|---|---|
| `_norm_chunk` stemming | 156 |
| the stem-length guard | 263 |
| the producer-margin tie-break | 306, 353 |
| the S3 **dominant** overlap arm | 363, 365, 366 |
| the S3 **reverse** arms, including **uncorroborated-not-classified** | 368, 369 |
| S1 trigger matching | 488 |
| S2 trigger matching with the **vision-feature cap** | 518–523, 525 |
| plus the one `agents/brainstormer.py` statement | 284 |

**Exit check: misses ≤ 893 on `tests/` alone** — the number the old gate was pretending
to have, now earned.

**Do not pull 6z earlier.** The coupling work is the phase; 6z depends on nothing in it
and would only serialise against it.

#### New rule: runtime is measured in pairs, and the figure is the delta

Every runtime comparison from here on is a **paired measurement — baseline and candidate
in the same session** — and **the recorded figure is the delta, not the absolute.**
§51.1's control run is the pattern; it is now the rule. An absolute figure compared
against a number taken hours earlier is machine weather, and §51.1 is the worked example
of it costing an afternoon's confidence: 4 s of the 6.6 s "regression" was the machine,
and the rest was my own arithmetic.

The ≤ 96 s target stands, read as *"the paired delta must reach ≤ 96 s from that
session's own baseline"*.

#### New rule: the mutation check is part of every 6x report

Ruled after 6c. **Every coupling rewrite states the mutation it survived.** Break the
invariant, re-run, show the old assertion passing and the new one failing — §53.3 is the
template. A rewrite that cannot be shown to fail for the defect it replaces is not
evidence of anything; §53 exists because an assertion that could not fail sat in the
suite for a phase and a half without anyone noticing.

One mutation per **seam**, not per site.

#### New rule: the tier-B allowed-and-reported entry has a template

§53.4's last paragraph is the shape: name the tier-B file, its listed class, that
class's **current line range**, the line ranges of every hunk, and the conclusion that
none of them intersect. Every later sub-phase that touches a tier-B file outside its
listed classes reports in that form.

#### New rule: pruning is never justified by seconds

**A test is dropped for redundancy, coupling, or vacuity. Never for being slow.**

A test's standalone time is an **upper bound** on what deleting it saves, and usually a
loose one — §51.1 measured 82 tests whose standalone cost was 2.59 s and whose marginal
cost inside a full run was **0.4 s**, because the rest was import warm-up the suite had
already paid.

**Any 6x report citing runtime as a reason to drop a test gets that reason struck.**
Runtime is an outcome of this phase, not an argument within it.

## 52. Phase 6b — the three patch strings that named the wrong seam

§50.5(d) step 1. Two files, three strings, no production change. Neither file is in
§50.3: `tests/test_usage_capture.py` and `tests/test_designer_fullscreen.py` carry no
whole-file entry, no tier-A test and no tier-B class.

### 52.1 The `os` pair — and why `spec4._usage.os.replace` was *not* the fix

The obvious rewrite is wrong, and it is worth recording why before the right one.

After 4b the atomic writer is `src/spec4/_usage.py:345` (`_write_atomic`), not
`project_manager.py`. So the tempting correction is
`patch("spec4._usage.os.replace")`. **That changes nothing.** `spec4._usage.os` *is* the
stdlib `os` module object; patching an attribute on it patches it for the whole process,
exactly as `spec4.project_manager.os.replace` did. Renaming the prefix would have moved
the string closer to the truth while leaving the defect entirely intact.

Measured, rather than argued:

```
with patch("spec4.project_manager.os.replace", side_effect=OSError("boom")):
    os.replace is real_replace   ->  False        # process-wide
```

For the duration of that patch **every** `os.replace` in the process raised — the
`tmp_path` fixture's own bookkeeping, any other write the test triggered, pytest's
internals. The two assertions could not see it.

**The fix is to rebind the module's `os` name, not to mutate the module it points at.**
A small proxy delegates everything to the real `os` except the calls a test overrides:

```python
class _OsSeam:
    def __init__(self, **overrides): self._overrides = overrides
    def __getattr__(self, name):
        overrides = object.__getattribute__(self, "_overrides")
        return overrides[name] if name in overrides else getattr(os, name)
```

```python
with patch("spec4._usage.os", _OsSeam(replace=_failing_replace)):
```

`_write_atomic` uses four `os` calls — `fdopen`, `fsync`, `replace`, `unlink` — and the
proxy passes the three it is not overriding straight through, so the writer's real
behaviour on the success path is untouched.

**Verified three ways, because "the tests still pass" proves nothing about a patch that
was already vacuous in a different sense:**

| Check | Result |
|---|---|
| `_OsSeam()` overriding **nothing** — writer must succeed | no raise; delegation works |
| `_OsSeam(replace=boom)` — writer must be **reached** | `OSError: boom` raised through `save_usage` |
| stdlib `os.replace` **during** the patch | **still the real function** — blast radius gone |
| `spec4._usage.os` after the patch | the real module again; clean restore |

The `fdopen` test drops its `real_fdopen = os.fdopen` capture: with the seam scoped to
`spec4._usage`, the stdlib `os.fdopen` the wrapper calls *is* the real one, so the
save-a-reference-first dance is no longer needed.

### 52.2 The designer string — a clarity fix, not a behaviour fix

`tests/test_designer_fullscreen.py:97` patched
`spec4.callbacks.designer.project_manager.load_prior_mock`. The package `__init__`
neither calls it nor sits on the path to it; after 4h the caller is
`callbacks/designer/_wizard.py:161`, inside `on_designer_carry_forward` — the very
function the test invokes. The patch worked only because both names bind the same
`spec4.project_manager` module object.

Rewritten to the call site: `spec4.callbacks.designer._wizard.project_manager.load_prior_mock`.
The same `with` block already patches `spec4.callbacks.designer._wizard.revision_delta`,
so the two now name one seam instead of two.

Verified the new target reaches the branch it is supposed to steer:

| `load_prior_mock` returns | resulting `store["step"]` |
|---|---|
| a mock | **7** (the refine view — what the test asserts) |
| `None` | **3** (the fallback arm) |

### 52.3 What this sub-phase did not do

No production file changed. No test was dropped, renamed or moved; three patch target
strings changed and one now-redundant local was removed. No runtime claim is made or
implied — per §51.6, seconds are not a currency in this phase.

### 52.4 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4174 passed, 1 skipped in 176.79s` (exit 0) |
| Coverage | same run | `TOTAL 12421 stmts, 909 miss, 93%` — **at the §51.6 baseline, not over it** |

**Off-limits check**, both halves, run for real:

| Kind | Result |
|---|---|
| 7 whole-file entries | absent from the diff |
| 19 tier-B files / 33 classes | **0 files with hunks**; no hunk inside a listed class; nothing to report as touched-outside |
| 456 node ids | **456 / 456 collect**, 0 failures |

Collected count unchanged at **4,175**.

### 52.5 Addendum — the seam is a fixture, and the proxy is scaffolding

Two directives applied after 6b was approved.

#### The proxy now lives once, in `tests/conftest.py`

`_OsSeam` is gone from `tests/test_usage_capture.py`. `tests/conftest.py` gains
`_ModuleSeam` and the **`module_seam`** fixture, which resolves the real module from the
target string and rebinds the name:

```python
with module_seam("spec4._usage.os", replace=_failing_replace):
    ...
```

Both atomicity tests take the fixture. The four-way verification of §52.1 was re-run
through it and holds unchanged: empty seam transparent; writer reached; stdlib
`os.replace` untouched during the patch; clean restore after.

The fixture's docstring carries the rule — **every** patch that would otherwise reach an
attribute of a stdlib or third-party module through a `spec4` module goes through it,
and no test rebinds a module's `os` by hand.

#### The grep, for the record

`patch("spec4.<module>.<stdlib>.<fn>")` across `tests/`, over `os`, `sys`, `shutil`,
`pathlib`, `subprocess`, `time`, `urllib`, `socket`, `tempfile`:

| Hits | |
|---|---|
| **0** | 6b removed the only two that existed (`spec4.project_manager.os.replace`, `.os.fdopen`) |

The two `module_seam` call sites in `test_usage_capture.py` are the only places any test
rebinds a module attribute of this kind. Nothing is pending and nothing is scheduled.

**Three siblings share the shape but not the hazard**, and are deliberately untouched —
§50.2 marks all of them `keep`:

| Target | Sites | Why it is not the same problem |
|---|---:|---|
| `spec4.llm.litellm.completion` / `.acompletion` / `.completion_cost` / `.get_supported_openai_params` | 183 | `litellm` is the seam under test, not collateral. Nothing else in the process calls it during a test, so a process-wide patch has no blast radius to speak of |
| `spec4.providers.boto3.client` | 3 | same |
| `version_check.urllib.request.urlopen` (`patch.object`) | 4 | same |

The `os` case was different in kind: `os.replace` and `os.fdopen` are called constantly
by code that has nothing to do with the test — which is exactly what made the old patch
dangerous and invisible.

#### The honest fix is a production seam, and Phase 6 cannot build it

**`module_seam` is scaffolding, not the design.** The right shape is a module-level
alias in the calling module, patched by name:

```python
# src/spec4/_usage.py
_replace = os.replace          # module-level seam
...
    _replace(tmp_name, path)   # in _write_atomic
```

```python
with patch("spec4._usage._replace", side_effect=OSError("boom")):
```

That needs no proxy, no delegation, and no fixture: the patched name is spec4's own, so
the scoping is a property of the code rather than of the test's cleverness. It also
documents in `src/` that this call is a designed test seam.

**Phase 6 does not touch `src/`**, so it cannot be done here. Logged as a **Phase 7
candidate**:

> **Phase 7 candidate — production seams for stdlib calls under test.** Give
> `_usage._write_atomic`'s `os.replace` and `os.fdopen` module-level aliases and patch
> those by name; then delete `module_seam` and `_ModuleSeam` from `tests/conftest.py`
> and the fixture argument from the two atomicity tests. The proxy exists only because
> Phase 6 is test-only. Audit at the same time whether any other production module has a
> stdlib call that tests need to fail on demand.

## 53. Phase 6c — `streaming.pop`: the question, then the assertion

§50.5(d) step 2. One file, `tests/test_callbacks_stream_poll.py`. No production change.

### 53.1 The question: is the chat path still required not to pop?

**Yes.** The evidence is not inferential — the requirement is written down in three
places in `src/`, and §12.2 pins the container behaviour it depends on.

| Source | What it says |
|---|---|
| `callbacks/_chat.py:487` | *"Read (do NOT pop) the agent-mutated session from the live entry. Eviction happens at the next `start()`; leaving the entry in place means two polls racing into this branch both read the same authoritative session and return a byte-identical terminal store"* |
| `streaming.start:238` | *"Done-branch polls now READ the entry (get) without removing it, so finalisation is idempotent across racing polls — eviction therefore has to happen here at `start()`, not in `pop()`"* |
| `streaming.claim_finalise` docstring | why re-entrancy is safe only for idempotent work: the persist funnel drains the process-global usage sink, so a second run would wipe the turn's token readout |
| §12.2 (Phase 1 net) | *"The next `start()` evicts every `done` entry and only those"*; *"`claim_finalise` is True once then False; it does not evict"* |

The invariant is live, load-bearing, and has a named failure mode: pop here and a racing
poll falls to the missing-entry path, returning `no_update` instead of the terminal
store. So this is the **"if yes"** branch of §50.5(d) — rewrite to a real assertion, not
a deletion.

### 53.2 What was vacuous, and what replaced it

Two sites patched `spec4.callbacks._chat.streaming.pop`. `callbacks/_chat.py` holds no
reference to `streaming.pop` at all, so `mock_pop.assert_not_called()` could not fail.

**`TestStreamPollMissingEntry::test_missing_entry_returns_no_update`** — the patch and
its assertion are **dropped**. That test's subject is the missing-entry path returning
`no_update`; its own assertions cover it, and the pop assertion added nothing even in
principle, because that branch returns before reaching any container call. No rename.

**`TestStreamPollDoneFinalisation::test_done_branch_does_not_pop`** → renamed
**`test_done_branch_leaves_the_entry_for_a_racing_poll`** and rewritten against the
**real container**. The old form patched `streaming.get` to return a fake dict, so the
entry's survival was not observable even in principle. The new form calls the real
`streaming.start()`, waits for `done`, then runs two polls and asserts the consequences:

| Assertion | Guards |
|---|---|
| `streaming.get(id)` is not None after the first poll | the entry survives the branch |
| `first[0] == second[0]` | a racing poll returns an **equal terminal store** |
| `first[0]["_stream_id"] is None`, `vision_statement` carried | it is the *terminal* store, not `no_update` |
| `entry["finalised"] is True` | the first poll latched the finalise |
| `claim_finalise(id) is False` | the latch is **one-shot across racing polls** |

**A second test was added**, `test_the_next_start_is_what_evicts_the_finished_entry`,
because "never pop" is only half the contract: satisfied alone, it is also satisfied by
never evicting at all, which leaks every finished stream for the life of the process.
It asserts the finished entry is gone after the next `start()` and the new one is live.

A class-scoped autouse fixture clears `_STREAMS` before and after, so using the real
container leaks no state into the rest of the module.

### 53.3 Both new assertions were mutation-tested

Passing is not evidence, given what was just replaced. Each invariant was broken and the
tests re-run. No `src/` edit: the callback's `streaming` name is rebound to a stand-in
whose `get()` also removes — the observable consequence of a pop in the branch.

| Test | Under the mutation |
|---|---|
| **old** `test_done_branch_does_not_pop` | **passed** — confirming it was vacuous |
| **new** `test_done_branch_leaves_the_entry_for_a_racing_poll` | **failed**: *"the done branch removed the entry; a racing poll would fall to the missing-entry path…"* |

And for the eviction half, with `_STREAMS` replaced by a dict whose `__delitem__` is a
no-op (i.e. `start()` stops evicting):

| Test | Under the mutation |
|---|---|
| **new** `test_the_next_start_is_what_evicts_the_finished_entry` | **failed** |

### 53.4 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4175 passed, 1 skipped in 171.91s` (exit 0) |
| Coverage | same run | `TOTAL 12421 stmts, 909 miss, 93%` — **at the §51.6 baseline** |

Collected **4,176**, up 1: one test renamed and rewritten, one added, none removed. The
count floor of 456 is untouched.

**Off-limits check:**

| Kind | Result |
|---|---|
| 7 whole-file entries | absent from the diff |
| 456 node ids | **456 / 456 collect**, 0 failures |
| 19 tier-B files / 33 classes | **1 file with hunks — 0 failures** |

`tests/test_callbacks_stream_poll.py` **is** a tier-B file, and this is the first
exercise of §50.5(a)'s allowed-and-reported case. Its listed class is
`TestStreamedTokenCounter` (D-PH9), **lines 735–755**. The nine hunks land at lines 5–6,
10, 13, 55, 62, 139–145, 147–175, 177–178 and 180–227 — all far above it, none inside
it, and the three D-PH9 tests are byte-identical. **Reported, as the rule requires.**

## 54. Phase 6d, first cluster — `agentifier.agentifier`, and a finding about 6d itself

§50.5(d) step 3, first cluster. **No test was changed.** Rule 4 of the 6d directive says
to open with the split and stop if the Phase 7 list is most of the cluster. It is all of
it, and the reason is not local to this cluster.

### 54.1 The split

| | Names | Sites |
|---|---:|---:|
| Rewrite to an existing public seam, now | **0** | **0** |
| Phase 7 promote-candidates | **34** | **87** |

Rule 1 is what decides it: *"rewrite to public seam" means a seam that already exists.*

**`agentifier.py`'s entire public surface is two functions — `run` and
`reset_agentifier_flow`.** `run` is the 24-yield generator turn that §27.4 grants a
rule-12 noqa; reaching a helper through it is an integration test, not isolation, and
rule 2 forbids trading granularity for a public path. That leaves
`reset_agentifier_flow`, and **16 of the 34 names are not defined in `agentifier.py` at
all** — they are imported from `spec4.agentifier._seed`, `spec4.agentifier._render` and
`spec4.agents._reask`, artifacts of the 5k/5l splits.

**Both sibling modules have zero public functions.** So for the sibling-owned 16 there is
no public seam to rewrite toward either; re-pointing the import from
`agentifier.agentifier` to `_seed` would change a string without changing what the test
knows or what it would catch — and under the new §51.6 rule it would have **no mutation
to demonstrate**, because behaviour would be identical. That is churn, not a rewrite.

**The one case with a public caller is still not a rewrite.** `_RESTART_DEFAULTS` and
`_RESTART_POP` are read by `reset_agentifier_flow`, which is public — but the four tests
that import them are *drift guards on the collections themselves*, not on the reset's
behaviour:

| Test | Why the public path cannot express it |
|---|---|
| `test_every_session_key_is_accounted_for` | asks whether any `agentifier_*` key is **missing** from the collections. A key that is missing is precisely one the reset does not touch, so calling the reset cannot reveal it |
| `test_no_dead_entries` | the converse — a listed key no longer used anywhere |
| `test_the_two_collections_are_disjoint` | a structural property of the two collections, invisible in the merged result |
| `test_defaults_match_the_session_defaults` | compares the **declared** values against `_default_session()`, key by key |

Rewriting these through `reset_agentifier_flow` would replace a drift guard with an
output check — rule 2's definition of a loss. `test_revision_block_is_cleared`, in the
same class, is already behavioural and needs nothing. **Here the private-name access is
the correct design: the collection is the test's subject.**

### 54.2 The finding: 6d is smaller than §50.2 sized it

Rule 4 says that if this happens the plan should say so rather than the reports. It is
not specific to `agentifier.agentifier`. Public-function count for all eleven clusters:

| Cluster module | Private names | Sites | Public fns | Public surface |
|---|---:|---:|---:|---|
| `spec4.agentifier.agentifier` | 34 | 87 | 2 | `run`, `reset_agentifier_flow` |
| `spec4.layouts._chat` | 14 | 43 | **0** | — none — |
| `spec4.session` | 10 | 57 | **0** | — none — |
| `spec4.callbacks.designer` | 10 | 90 | 2 | `render_designer_step`, `on_mock_stream_poll` |
| `spec4.project_manager` | 8 | 22 | **6** | `detect_stale_inputs`, `brownfield_new_round_pending`, … |
| `spec4.agents.brainstormer` | 8 | 26 | 1 | `run` |
| `spec4.layouts` | 7 | 18 | **0** | — none — |
| `spec4.agents.code_scanner` | 7 | 44 | 1 | `run` |
| `spec4.layouts.designer` | 7 | 24 | 3 | `stepper_index`, `designer_step_row`, `designer_layout` |
| `spec4.agents._seam_check` | 6 | 6 | 1 | `run_seam_check` |
| `spec4.llm` | 6 | 25 | **9** | `build_system_prompt`, `complete`, `complete_stream`, … |

**Three clusters have no public function at all.** Four more expose only `run` or
`run_seam_check` — a turn, not a seam. Only `project_manager` (6) and `llm` (9) have a
surface worth rewriting toward, and they are the two **smallest** clusters by name count.

§50.2 called these eleven `rewrite to public seam`, and the disposition was sound as a
*description of what the tests need*. What it did not check — because §50 was read-only
and scoped to `tests/` — is **whether the seams exist**. Mostly they do not, and Phase 6
cannot create them, because creating them means touching `src/`.

**So 6d is not a rewrite pass. It is a Phase 7 promote-candidate inventory**, with the
possible exception of `project_manager` and `llm`, which are worth a look on their own
terms once this is agreed.

### 54.3 The promote-candidate list — `spec4.agentifier.agentifier`

Left exactly as-is, per rule 1. Proposed public names are the private name without its
underscore unless noted; the owner column says which module would do the promoting.

| Private name | Owner | Sites | Test files | Proposed public name |
|---|---|---:|---|---|
| `_APPROACHES_OVERVIEW` | `agentifier.py` | 5 | agentifier/test_agentifier_orchestrator.py | `APPROACHES_OVERVIEW` |
| `_RESTART_DEFAULTS` | `agentifier.py` | 1 | agentifier/test_try_again.py | `RESTART_DEFAULTS` |
| `_RESTART_POP` | `agentifier.py` | 1 | agentifier/test_try_again.py | `RESTART_POP` |
| `_analyses_to_dicts` | `_seed` | 3 | agentifier/test_agentifier_orchestrator.py | `analyses_to_dicts` |
| `_begin_priority_phase` | `agentifier.py` | 1 | agentifier/test_prioritizer.py | `begin_priority_phase` |
| `_breadth_candidates` | `agentifier.py` | 1 | agentifier/test_search_level.py | `breadth_candidates` |
| `_build_ai_features` | `_render` | 15 | agentifier/test_agentifier_orchestrator.py, agentifier/test_edge_persistence.py, agentifier/test_vision_grounding.py | `build_ai_features` |
| `_build_seed_message` | `_seed` | 18 | agentifier/test_agentifier_orchestrator.py, agentifier/test_revision.py, integration/test_pipeline_brownfield.py | `build_seed_message` |
| `_candidates_from_dicts` | `_seed` | 1 | agentifier/test_edge_persistence.py | `candidates_from_dicts` |
| `_candidates_to_dicts` | `_seed` | 1 | agentifier/test_edge_persistence.py | `candidates_to_dicts` |
| `_complete_agentifier` | `agentifier.py` | 6 | agentifier/test_revision.py, agentifier/test_try_again.py | `complete_agentifier` |
| `_existing_workflow_for_entry` | `agentifier.py` | 1 | agentifier/test_vision_grounding.py | `existing_workflow_for_entry` |
| `_extract_cross_cutting_analysis` | `agentifier.py` | 4 | agentifier/test_cross_cutting_analyst.py | `extract_cross_cutting_analysis` |
| `_feature_specs_for_session` | `agentifier.py` | 1 | agentifier/test_vision_grounding.py | `feature_specs_for_session` |
| `_finalize_specs` | `agentifier.py` | 2 | agentifier/test_reselection.py, agentifier/test_search_level.py | `finalize_specs` |
| `_format_catalog_as_text` | `_render` | 1 | test_renderer_goldens.py **(net)** | `format_catalog_as_text` |
| `_format_priority_table` | `_render` | 1 | agentifier/test_prioritizer.py | `format_priority_table` |
| `_format_spec_as_text` | `_render` | 1 | test_renderer_goldens.py **(net)** | `format_spec_as_text` |
| `_handle_reentry` | `agentifier.py` | 3 | agentifier/test_reselection.py | `handle_reentry` |
| `_is_spec_confirmed` | `agentifier.py` | 1 | agentifier/test_spec_drafter.py | `is_spec_confirmed` |
| `_iter_async_gen` | `_seed` | 1 | agentifier/test_streaming_e2e.py | `iter_async_gen` |
| `_linked_features_for_entry` | `agentifier.py` | 1 | agentifier/test_vision_grounding.py | `linked_features_for_entry` |
| `_merge_revision_snapshot` | `_render` | 1 | agentifier/test_revision.py | `merge_revision_snapshot` |
| `_parse_priority_edits` | `_render` | 1 | agentifier/test_prioritizer.py | `parse_priority_edits` |
| `_registry` | `_seed` | 1 | agentifier/test_reselection.py | `registry` |
| `_removed_feature_heads_up` | `_render` | 1 | agentifier/test_revision.py | `removed_feature_heads_up` |
| `_reselection_pool_from_features` | `agentifier.py` | 2 | agentifier/test_edge_persistence.py, agentifier/test_reselection.py | `reselection_pool_from_features` |
| `_revision_delta` | `_render` | 1 | agentifier/test_revision.py | `revision_delta` |
| `_run_catalog_phase` | `agentifier.py` | 5 | agentifier/test_revision.py | `run_catalog_phase` |
| `_run_cross_cutting_phase` | `agentifier.py` | 1 | agentifier/test_ff_sweep.py | `run_cross_cutting_phase` |
| `_run_priority_phase` | `agentifier.py` | 1 | agentifier/test_prioritizer.py | `run_priority_phase` |
| `_run_spec_phase` | `agentifier.py` | 1 | agentifier/test_ff_sweep.py | `run_spec_phase` |
| `_stream_suppressing_json` | `agents/_reask` | 1 | agentifier/test_chars_counter_seed.py | `stream_suppressing_json` |
| `_vision_mvp_feature_names` | `_seed` | 1 | agentifier/test_prioritizer.py | `vision_mvp_feature_names` |

**Two sites are Phase 1 net and are `keep` regardless of what Phase 7 decides**:
`_format_catalog_as_text` and `_format_spec_as_text` are reached by
`tests/test_renderer_goldens.py`, a whole-file §50.3 entry. Promoting the names in `src/`
would require editing that file to follow, which §50.3 forbids — so either Phase 7
promotes them and petitions for that one edit, or it leaves these two alone. **Flagged
now so Phase 7 does not discover it mid-rename.**

The natural grouping for a Phase 7 promotion, if it happens:

| Group | Names | Note |
|---|---|---|
| `_seed.py` seed construction | `_build_seed_message`, `_candidates_to_dicts`, `_candidates_from_dicts`, `_analyses_to_dicts`, `_vision_mvp_feature_names`, `_iter_async_gen`, `_registry` | 18 of the 87 sites are `_build_seed_message` alone, called directly with candidates and analyses and asserted on the message text — textbook unit tests of a helper with no public route |
| `_render.py` renderers | `_build_ai_features`, `_format_catalog_as_text`, `_format_priority_table`, `_format_spec_as_text`, `_merge_revision_snapshot`, `_parse_priority_edits`, `_removed_feature_heads_up`, `_revision_delta` | golden-pinned by 5d; two are net |
| the phase runners | `_run_catalog_phase`, `_run_cross_cutting_phase`, `_run_priority_phase`, `_run_spec_phase`, `_handle_reentry` | all carry rule-12 noqas or feed `run`; promoting these is a design question, not a rename |
| session/state helpers | `_complete_agentifier`, `_begin_priority_phase`, `_finalize_specs`, `_feature_specs_for_session`, `_is_spec_confirmed`, `_extract_cross_cutting_analysis`, `_breadth_candidates`, `_reselection_pool_from_features`, `_existing_workflow_for_entry`, `_linked_features_for_entry` | |
| the restart collections | `_RESTART_DEFAULTS`, `_RESTART_POP`, `_APPROACHES_OVERVIEW` | **do not promote for the tests' sake** — §54.1 shows the private access is correct here |

### 54.4 What this sub-phase did not do

No test was changed, so there is no mutation check to report — §51.6's rule applies to
rewrites, and there is no rewrite. No `src/` change, no `noqa` change. The suite is
byte-identical to 6c's.

### 54.5 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | — | **not re-run, and the reason is checkable**: `git diff --stat` against 6c shows `CLEANUP_INVENTORY.md` as the only changed file, so §53.4's `4175 passed, 1 skipped` stands unaltered |
| Coverage | — | likewise `TOTAL 12421 stmts, 909 miss, 93%`, at the §51.6 baseline |
| Per-file (rule 3) | — | `agentifier/agentifier.py` coverage cannot have moved: no test was added, removed or re-pointed |

Ruff, ruff-format and mypy **were** re-run, since the report edits a tracked file.

**Off-limits check:**

| Kind | Result |
|---|---|
| 7 whole-file entries | absent from the diff (only `CLEANUP_INVENTORY.md` changed) |
| 19 tier-B files / 33 classes | 0 files with hunks |
| 456 node ids | **456 / 456 collect**, 0 failures |

### 54.7 The golden petition, pre-shaped

§54.3 flags that `_format_catalog_as_text` and `_format_spec_as_text` are reached by
`tests/test_renderer_goldens.py`, a whole-file §50.3 entry. Promoting those names in
`src/` requires that file's import lines to follow, which §50.3 forbids. Rather than
leave Phase 7 to discover it mid-rename and improvise, the exception is defined **now**,
mechanically, so it is a check rather than a judgment call.

> **Petition — Phase 7 may edit a §50.3 whole-file entry for a seam promotion if and
> only if all three hold:**
>
> 1. **The diff is import lines alone.** Every changed line is inside an `import` or
>    `from … import` statement. No test body, no assertion, no fixture, no docstring.
> 2. **Every golden file is byte-identical.** `git diff --stat -- tests/golden/
>    tests/snapshots/` is empty. A promotion that changes rendered output is not a
>    promotion.
> 3. **The off-limits check passes on the rest of the file.** Every node id in the file
>    still collects under its current id, and the file's test count is unchanged.
>
> Any one of the three failing means it is not this petition — stop and ask.

The same shape covers any other §50.3 file a promotion reaches; nothing about it is
specific to the two renderers. It is deliberately narrow: an import-only diff cannot
change what a test asserts, and the golden check proves the rename did not disturb the
output the net exists to pin.

### 54.6 Stopping here, as rule 4 requires

The Phase 7 list is the whole cluster, and §54.2 shows the cause is structural rather
than particular to this module. **Not proceeding to `layouts._chat`** — which has zero
public functions and would produce the same report with different names.

Two questions for the plan, not for the next report:

1. **Should 6d continue at all?** Ten clusters remain; on the evidence, eight of them
   end the same way. Continuing would produce eight inventories and no rewrites.
2. **Should `project_manager` (6 public) and `llm` (9 public) be attempted?** They are
   the only two clusters with a real public surface. They are also the two smallest, so
   the ceiling is 14 names across 47 sites — worth doing if the seams turn out to fit,
   and quick to abandon if they do not.

A third option, if the promote-candidate inventory is the actual deliverable: **run the
§54.3 analysis over the remaining ten clusters in one pass**, producing one Phase 7
document rather than ten sub-phase reports, and close 6d there.

## 55. Phase 6d, folded — the Phase 7 seam document

The fold of §54.6's option 3, run over **all eleven clusters** including
`agentifier.agentifier`, so this section is the single Phase 7 document and §54 is the
reasoning behind it. **No test was changed.**

The plan now carries the redefinition: 6d produces this document and performs no
rewrites.

### 55.1 Method, and a correction to §50.2's site count

Sites were re-derived by AST over all 127 Python files under `tests/`, counting **every
use**, not every import. §50.2 reported 583 sites; it counted import statements and
`module._name` attribute access but **not bare uses of a from-imported private name** —
so `_default_session()`, called 248 times, contributed one site to §50.2 and contributes
248 here.

| | §50.2 | §55 |
|---|---:|---:|
| Sites | 583 | **1,361** |
| Names | 176 | 120 (the eleven clusters only; §50.2's figure spans all 35 modules) |

The correction does not change any disposition. It changes what "87 sites" meant in §54
— the true figure for `agentifier.agentifier` is 208.

Each site carries its **syntactic role** (called / compared / subscripted / iterated /
import-only / passed-as-arg), and each name's object was resolved at runtime rather than
guessed from the AST, so a constant imported from a sibling is classified as data rather
than as an import.

### 55.2 The four dispositions, and the rule that assigns each

| Disposition | Rule | Names | Sites |
|---|---|---:|---:|
| **`promote`** | Phase 7 creates the public seam, the test follows. Assigned when the object is callable and no thin public function isolates it | **94** | **1,171** |
| **`keep: subject is the private object`** | the object is data and no site calls it — the collection *is* what is under test, so private access is the right design and **Phase 7 must not promote these** | **24** | **183** |
| **`churn`** | re-pointing would change a string and nothing else | **2** | **7** |
| **`rewrite now`** | a public function already isolates the helper and a mutation would demonstrate it | **0** | **0** |
| | | **120** | **1,361** |

Dispositions are assigned per site. Within every name in this document the sites agree,
so the tables list one row per name with its site count; had any name split, it would be
listed twice. The `· net` marker means at least one site is in a §50.3 whole-file entry
and is frozen regardless — §54.7 is the petition shape for those.

### 55.3 `rewrite now` is zero, and why that is a finding rather than an omission

Every public function in all eleven clusters was checked against every private name it
calls. **Eighteen (name, public-caller) pairings exist in total**, and they are these:

| Cluster | Names reached | Public caller | Statements in the caller |
|---|---|---|---:|
| `agentifier.agentifier` | `_handle_reentry`, `_run_catalog_phase`, `_run_cross_cutting_phase`, `_run_priority_phase`, `_run_spec_phase` | `run` | 15 |
| `agents.brainstormer` | `_rehydrate_vision_from_disk` | `run` | 45 |
| `agents.code_scanner` | `_approx_tokens`, `_collect_files`, `_format_review_as_text` | `run` | 62 |
| `agents._seam_check` | the six `_check_*` / `_extract_graph` / `_format_advisory` | `run_seam_check` | 21 |
| `llm` | `_is_tool_incompatible_error` | `stream_turn` | 63 |
| `llm` | `_record_usage` | `complete`, `acomplete` | 10 |

Every caller but the last is a **turn** — `run`, `stream_turn`, `run_seam_check` — and
routing a helper's tests through one is an integration test, which rule 2 forbids
trading granularity for. `run_seam_check` is the closest call at 21 statements, but it
dispatches to **six** checkers and `_check_declaration_alignment` alone has 15 sites;
driving 15 cases of one checker through a six-way dispatcher couples each of them to the
other five.

**The last row is the only genuinely thin isolator in the codebase, and it is still not a
rewrite.** `llm._record_usage` has two sites. One is in `test_streaming_characterization.py`
(net, frozen). The other, `test_usage_capture.py:1340`, calls it **inside a generator
that simulates an agent writing a usage record mid-stream** — it is seeding the sink at a
controlled point, not testing the recorder. Driving it through `complete` would change
what the test does, not how it reaches it.

So: **zero `rewrite now` sites. 6e does not exist.**

Notably `project_manager` — 6 public functions, the largest public surface among the
clusters after `llm` — has **none** of its private names called by any of them. Its
eight names are five constants (all `keep`) and three helpers.

### 55.4 The `keep: subject is the private object` list — Phase 7 must not promote these

24 names, 183 sites. Each is data whose *structure* is the assertion: a drift guard, a
declared-set comparison, or a container a test inspects directly. Promoting them would
invite a rewrite that replaces a completeness check with an output check — §54.1 works
the `_RESTART_DEFAULTS` case through in full, and the reasoning transfers.

### 55.5 The `churn` list

| Name | Cluster | Sites | Why |
|---|---|---:|---|
| `_iter_async_gen` | `agentifier.agentifier` | 6 | async-generator plumbing, owned by `_seed`; re-pointing the import changes a string and nothing a test would catch |
| `_registry` | `agentifier.agentifier` | 1 | the sub-agent registry instance, owned by `_seed`; same |

### 55.6 Per-cluster tables

#### `spec4.agentifier.agentifier` — 34 names, 208 sites, 2 public fn(s)

| Private name | Kind | Owner | Sites | Test files | Disposition |
|---|---|---|---:|---|---|
| `_APPROACHES_OVERVIEW` | data | `self` | 5 | agentifier/test_agentifier_orchestrator.py | `keep: subject is the private object` |
| `_RESTART_DEFAULTS` | data | `self` | 6 | agentifier/test_try_again.py | `keep: subject is the private object` |
| `_RESTART_POP` | data | `self` | 4 | agentifier/test_try_again.py | `keep: subject is the private object` |
| `_analyses_to_dicts` | func | `agentifier._seed` | 3 | agentifier/test_agentifier_orchestrator.py | `promote` |
| `_begin_priority_phase` | func | `self` | 2 | agentifier/test_prioritizer.py | `promote` |
| `_breadth_candidates` | func | `self` | 5 | agentifier/test_search_level.py | `promote` |
| `_build_ai_features` | func | `agentifier._render` | 26 | agentifier/test_agentifier_orchestrator.py, agentifier/test_edge_persistence.py, agentifier/test_vision_grounding.py | `promote` |
| `_build_seed_message` | func | `agentifier._seed` | 25 | agentifier/test_agentifier_orchestrator.py, agentifier/test_revision.py, integration/test_pipeline_brownfield.py | `promote` |
| `_candidates_from_dicts` | func | `agentifier._seed` | 7 | agentifier/test_edge_persistence.py | `promote` |
| `_candidates_to_dicts` | func | `agentifier._seed` | 6 | agentifier/test_edge_persistence.py | `promote` |
| `_complete_agentifier` | func | `self` | 6 | agentifier/test_revision.py, agentifier/test_try_again.py | `promote` |
| `_existing_workflow_for_entry` | func | `self` | 4 | agentifier/test_vision_grounding.py | `promote` |
| `_extract_cross_cutting_analysis` | func | `self` | 8 | agentifier/test_cross_cutting_analyst.py | `promote` |
| `_feature_specs_for_session` | func | `self` | 4 | agentifier/test_vision_grounding.py | `promote` |
| `_finalize_specs` | func | `self` | 3 | agentifier/test_reselection.py, agentifier/test_search_level.py | `promote` |
| `_format_catalog_as_text` | func | `agentifier._render` | 5 | test_renderer_goldens.py | `promote` **· net** |
| `_format_priority_table` | func | `agentifier._render` | 2 | agentifier/test_prioritizer.py | `promote` |
| `_format_spec_as_text` | func | `agentifier._render` | 3 | test_renderer_goldens.py | `promote` **· net** |
| `_handle_reentry` | func | `self` | 3 | agentifier/test_reselection.py | `promote` |
| `_is_spec_confirmed` | func | `self` | 6 | agentifier/test_spec_drafter.py | `promote` |
| `_iter_async_gen` | func | `agentifier._seed` | 6 | agentifier/test_streaming_e2e.py | `churn` |
| `_linked_features_for_entry` | func | `self` | 3 | agentifier/test_vision_grounding.py | `promote` |
| `_merge_revision_snapshot` | func | `agentifier._render` | 7 | agentifier/test_revision.py | `promote` |
| `_parse_priority_edits` | func | `agentifier._render` | 2 | agentifier/test_prioritizer.py | `promote` |
| `_registry` | data | `agentifier._seed` | 1 | agentifier/test_reselection.py | `churn` |
| `_removed_feature_heads_up` | func | `agentifier._render` | 5 | agentifier/test_revision.py | `promote` |
| `_reselection_pool_from_features` | func | `self` | 10 | agentifier/test_edge_persistence.py, agentifier/test_reselection.py | `promote` |
| `_revision_delta` | func | `agentifier._render` | 7 | agentifier/test_revision.py | `promote` |
| `_run_catalog_phase` | func | `self` | 5 | agentifier/test_revision.py | `promote` |
| `_run_cross_cutting_phase` | func | `self` | 8 | agentifier/test_ff_sweep.py | `promote` |
| `_run_priority_phase` | func | `self` | 2 | agentifier/test_prioritizer.py | `promote` |
| `_run_spec_phase` | func | `self` | 16 | agentifier/test_ff_sweep.py | `promote` |
| `_stream_suppressing_json` | func | `agents._reask` | 1 | agentifier/test_chars_counter_seed.py | `promote` |
| `_vision_mvp_feature_names` | func | `agentifier._seed` | 2 | agentifier/test_prioritizer.py | `promote` |

#### `spec4.layouts._chat` — 14 names, 217 sites, 0 public fn(s)

| Private name | Kind | Owner | Sites | Test files | Disposition |
|---|---|---|---:|---|---|
| `_PILL_ACTIVE` | data | `layouts._chat_status` | 9 | test_chat_pill_bar.py | `keep: subject is the private object` |
| `_PILL_BASE` | data | `layouts._chat_status` | 14 | test_chat_pill_bar.py | `keep: subject is the private object` |
| `_PILL_DONE` | data | `layouts._chat_status` | 11 | test_chat_pill_bar.py | `keep: subject is the private object` |
| `_PILL_UNREACHABLE` | data | `layouts._chat_status` | 6 | test_chat_pill_bar.py | `keep: subject is the private object` |
| `_TOKEN_COUNTER_AGENTS` | data | `layouts._chat_actions` | 13 | test_agentifier_chars_counter.py, test_brainstormer_chars_counter.py, test_code_scanner_progress.py, test_stack_advisor_token_counter.py | `keep: subject is the private object` |
| `_agent_status_bar` | func | `layouts._chat_status` | 4 | test_chat_pill_bar.py | `promote` |
| `_breadth_panel` | func | `layouts._chat_panels` | 21 | agentifier/test_try_again.py, test_callbacks_stream_poll.py | `promote` |
| `_chat_action_buttons` | func | `layouts._chat_actions` | 39 | test_agent_llm_selection.py, test_agentifier_chars_counter.py, test_brainstormer_chars_counter.py, test_chat_action_row_emphasis.py, test_chat_open_links.py, test_code_scanner_progress.py, test_fast_forward.py, test_usage_capture.py | `promote` |
| `_chat_layout` | func | `self` | 37 | test_agent_llm_selection.py, test_callbacks_stream_poll.py, test_chat_transcript_blocks.py, test_code_scanner_progress.py, test_cost_summary.py, test_stream_error_recovery.py | `promote` |
| `_cost_summary` | func | `layouts._chat_panels` | 13 | test_cost_summary.py | `promote` |
| `_retry_panel` | func | `layouts._chat_panels` | 15 | test_agent_llm_selection.py, test_stream_error_recovery.py | `promote` |
| `_streamed_token_count` | func | `layouts._chat_actions` | 8 | test_callbacks_stream_poll.py, test_deployer_chars_counter.py, test_stack_advisor_token_counter.py | `promote` |
| `_token_count_text` | func | `layouts._chat_actions` | 16 | test_agentifier_chars_counter.py, test_brainstormer_chars_counter.py, test_code_scanner_progress.py, test_deployer_chars_counter.py, test_stack_advisor_token_counter.py, test_usage_capture.py | `promote` |
| `_turn_token_text` | func | `layouts._chat_actions` | 11 | test_usage_capture.py | `promote` |

#### `spec4.session` — 10 names, 367 sites, 0 public fn(s)

| Private name | Kind | Owner | Sites | Test files | Disposition |
|---|---|---|---:|---|---|
| `_AGENT_STATUS_SEED` | data | `self` | 3 | test_callbacks_stream_poll.py | `keep: subject is the private object` |
| `_PRESERVED_SETUP_KEYS` | data | `self` | 4 | test_agent_llm_selection.py | `keep: subject is the private object` |
| `_default_session` | func | `self` | 248 | agentifier/test_search_level.py, agentifier/test_streaming_e2e.py, agentifier/test_try_again.py, integration/test_pipeline_brownfield.py, integration/test_pipeline_greenfield.py, test_agent_llm_selection.py, test_agent_rows.py, test_agent_select_layout.py, test_artifact_view.py, test_callback_co_presence.py, test_callbacks_stream_poll.py, test_chat_open_links.py, test_cost_summary.py, test_designer.py, test_designer_wizard_register.py, test_entry_screens.py, test_feature_specs_pass.py, test_layout_contract.py, test_project_manager.py, test_project_mode.py, test_root_routing.py, test_round_cost.py, test_round_tree.py, test_session.py, test_status_bar.py, test_stream_error_recovery.py, test_streaming_characterization.py, test_usage_capture.py | `promote` **· net** |
| `_get_agent_gen` | func | `self` | 20 | test_agent_llm_selection.py, test_callbacks_stream_poll.py, test_session.py | `promote` |
| `_load_working_dir` | func | `self` | 24 | test_agent_select_layout.py, test_feature_specs_pass.py, test_project_mode.py, test_session.py | `promote` |
| `_persist_artifacts` | func | `self` | 35 | agentifier/test_try_again.py, test_project_manager.py, test_project_mode.py, test_session.py, test_usage_capture.py | `promote` |
| `_reset_for_new_project` | func | `self` | 14 | test_agent_llm_selection.py, test_callback_co_presence.py, test_session.py | `promote` **· net** |
| `_run_agent_blocking` | func | `self` | 8 | test_session.py | `promote` |
| `_summarize_turn_usage` | func | `self` | 4 | test_usage_capture.py | `promote` |
| `_validate_agent_preconditions` | func | `self` | 7 | test_chat_pill_bar.py, test_stale_ai_features.py | `promote` |

#### `spec4.callbacks.designer` — 7 names, 75 sites, 2 public fn(s)

| Private name | Kind | Owner | Sites | Test files | Disposition |
|---|---|---|---:|---|---|
| `_DEFAULT_EXPECTED_CHARS` | data | `callbacks.designer._mock_gen` | 5 | test_designer.py, test_streaming_characterization.py | `keep: subject is the private object` **· net** |
| `_MAX_DELIVERY_TICKS` | data | `callbacks.designer._mock_gen` | 2 | test_designer.py, test_streaming_characterization.py | `keep: subject is the private object` **· net** |
| `_MOCK_BUFFERS` | data | `callbacks.designer._mock_gen` | 47 | test_designer.py, test_streaming_characterization.py | `keep: subject is the private object` **· net** |
| `_expected_stream_chars` | func | `callbacks.designer._mock_gen` | 4 | test_designer.py | `promote` |
| `_extract_html` | func | `callbacks.designer._mock_gen` | 8 | test_designer.py | `promote` |
| `_persist_manifest` | func | `callbacks.designer._mock_gen` | 1 | test_designer.py | `promote` |
| `_start_gen` | func | `callbacks.designer._mock_gen` | 8 | test_designer.py, test_streaming_characterization.py | `promote` **· net** |

#### `spec4.layouts` — 12 names, 177 sites, 0 public fn(s)

| Private name | Kind | Owner | Sites | Test files | Disposition |
|---|---|---|---:|---|---|
| `_AGENT_ROWS` | data | `layouts._agent_rows` | 4 | test_agent_llm_selection.py, test_callback_co_presence.py | `keep: subject is the private object` **· net** |
| `_agent_rows` | func | `layouts._agent_rows` | 15 | test_agent_rows.py | `promote` |
| `_agent_select_layout` | func | `self` | 41 | test_agent_rows.py, test_agent_select_layout.py, test_callback_co_presence.py, test_entry_screens.py, test_layout_contract.py, test_project_mode.py, test_round_cost.py, test_round_tree.py | `promote` **· net** |
| `_artifact_view_layout` | func | `layouts._artifact_view` | 26 | test_artifact_view.py, test_layout_contract.py | `promote` **· net** |
| `_chat_layout` | func | `layouts._chat` | 7 | test_layout_contract.py | `promote` **· net** |
| `_round_cost` | func | `layouts._round_cost` | 4 | test_round_cost.py | `promote` |
| `_round_tree` | func | `layouts._round_tree` | 23 | test_round_tree.py | `promote` |
| `_setup_layout` | func | `layouts._setup` | 6 | test_layout_contract.py | `promote` **· net** |
| `_shared` | data | `self` | 21 | test_designer_wizard_register.py, test_setup_wizard_register.py | `keep: subject is the private object` |
| `_status_bar` | func | `layouts._status_bar` | 20 | test_layout_contract.py, test_status_bar.py | `promote` **· net** |
| `_status_context` | func | `layouts._status_bar` | 3 | test_layout_contract.py | `promote` **· net** |
| `_working_dir_layout` | func | `self` | 7 | test_entry_screens.py, test_layout_contract.py, test_root_routing.py | `promote` **· net** |

#### `spec4.layouts.designer` — 7 names, 100 sites, 3 public fn(s)

| Private name | Kind | Owner | Sites | Test files | Disposition |
|---|---|---|---:|---|---|
| `_step1_content` | func | `self` | 6 | test_callback_co_presence.py, test_designer_wizard_register.py, test_layout_contract.py | `promote` **· net** |
| `_step2_content` | func | `self` | 14 | test_callback_co_presence.py, test_designer_wizard_register.py, test_layout_contract.py | `promote` **· net** |
| `_step3_content` | func | `self` | 8 | test_callback_co_presence.py, test_designer_wizard_register.py, test_layout_contract.py | `promote` **· net** |
| `_step4_content` | func | `self` | 13 | test_callback_co_presence.py, test_designer_wizard_register.py, test_layout_contract.py | `promote` **· net** |
| `_step5_content` | func | `self` | 11 | test_callback_co_presence.py, test_designer_wizard_register.py, test_layout_contract.py | `promote` **· net** |
| `_step6_content` | func | `self` | 28 | test_callback_co_presence.py, test_cost_summary.py, test_designer_fullscreen.py, test_designer_wizard_register.py, test_layout_contract.py | `promote` **· net** |
| `_step7_content` | func | `self` | 20 | test_callback_co_presence.py, test_designer_fullscreen.py, test_designer_wizard_register.py, test_layout_contract.py | `promote` **· net** |

#### `spec4.agents.code_scanner` — 7 names, 82 sites, 1 public fn(s)

| Private name | Kind | Owner | Sites | Test files | Disposition |
|---|---|---|---:|---|---|
| `_approx_tokens` | func | `agents.code_scanner._scan` | 5 | test_code_scanner_progress.py | `promote` |
| `_build_fresh_scan_seed` | func | `self` | 2 | test_code_scanner_progress.py | `promote` |
| `_build_update_scan_seed` | func | `self` | 2 | test_agents.py | `promote` |
| `_collect_files` | func | `agents.code_scanner._scan` | 7 | test_code_scanner_progress.py | `promote` |
| `_extract_review_json` | func | `self` | 6 | test_agents.py | `promote` |
| `_format_review_as_text` | func | `agents.code_scanner._review_render` | 40 | test_agents.py, test_renderer_goldens.py | `promote` **· net** |
| `_gather_project_context` | func | `agents.code_scanner._scan` | 20 | test_agents.py, test_code_scanner_progress.py | `promote` |

#### `spec4.agents.brainstormer` — 8 names, 46 sites, 1 public fn(s)

| Private name | Kind | Owner | Sites | Test files | Disposition |
|---|---|---|---:|---|---|
| `_VISION_REVIEW_FOOTER` | data | `self` | 2 | test_renderer_goldens.py | `keep: subject is the private object` **· net** |
| `_VISION_TRANSITION` | data | `self` | 2 | test_agents.py | `keep: subject is the private object` |
| `_apply_revision_history` | func | `self` | 10 | test_agents.py, test_revision_change_classification.py | `promote` |
| `_assign_feature_ids` | func | `self` | 9 | test_feature_ids.py | `promote` |
| `_feature_names` | func | `self` | 6 | test_revision_change_classification.py | `promote` |
| `_format_vision_as_text` | func | `self` | 11 | test_agents.py, test_renderer_goldens.py | `promote` **· net** |
| `_rehydrate_vision_from_disk` | func | `self` | 4 | test_vision_disk_reconciliation.py | `promote` |
| `_stamp_revision_block` | func | `self` | 2 | test_agents.py | `promote` |

#### `spec4.agents._seam_check` — 7 names, 39 sites, 1 public fn(s)

| Private name | Kind | Owner | Sites | Test files | Disposition |
|---|---|---|---:|---|---|
| `_check_declaration_alignment` | func | `self` | 15 | test_seam_check.py | `promote` |
| `_check_endpoint_provenance` | func | `self` | 3 | test_seam_check.py | `promote` |
| `_check_feature_coverage` | func | `self` | 4 | test_seam_check.py | `promote` |
| `_check_table_provenance` | func | `self` | 5 | test_seam_check.py | `promote` |
| `_extract_graph` | func | `self` | 3 | test_seam_check.py | `promote` |
| `_format_advisory` | func | `self` | 4 | test_seam_check.py | `promote` |
| `_parse_graph` | func | `self` | 5 | test_seam_check.py | `promote` |

#### `spec4.project_manager` — 8 names, 25 sites, 6 public fn(s)

| Private name | Kind | Owner | Sites | Test files | Disposition |
|---|---|---|---:|---|---|
| `_NON_ARTIFACT_FILES` | data | `self` | 5 | test_usage_capture.py | `keep: subject is the private object` |
| `_PIPELINE_ARTIFACT_ORDER` | data | `self` | 1 | test_usage_capture.py | `keep: subject is the private object` |
| `_REQUIRED_INPUTS` | data | `self` | 2 | test_deployer_invariants.py, test_usage_capture.py | `keep: subject is the private object` |
| `_STALE_DEPENDENCIES` | data | `self` | 4 | test_deployer_invariants.py, test_round_tree.py, test_usage_capture.py | `keep: subject is the private object` |
| `_USAGE_ROLLUP_PARENT` | data | `_usage` | 4 | test_agent_llm_selection.py | `keep: subject is the private object` |
| `_phase_spec_preamble` | func | `_phase_markdown` | 1 | test_project_manager.py | `promote` |
| `_with_readme_attribution` | func | `_artifacts` | 4 | test_project_manager_golden.py | `promote` **· net** |
| `_write_text_if_changed` | func | `_artifacts` | 4 | test_project_manager.py | `promote` |

#### `spec4.llm` — 6 names, 25 sites, 9 public fn(s)

| Private name | Kind | Owner | Sites | Test files | Disposition |
|---|---|---|---:|---|---|
| `_DEFAULT_EFFORT` | data | `self` | 1 | test_llm.py | `keep: subject is the private object` |
| `_USAGE_RECORDS` | data | `self` | 8 | test_streaming_characterization.py | `keep: subject is the private object` **· net** |
| `_history_has_tool_use` | func | `self` | 4 | test_llm.py | `promote` |
| `_is_effort_rejected_error` | func | `self` | 5 | test_llm.py | `promote` |
| `_is_tool_incompatible_error` | func | `self` | 5 | test_llm.py | `promote` |
| `_record_usage` | func | `self` | 2 | test_streaming_characterization.py, test_usage_capture.py | `promote` **· net** |


#### Totals

| Disposition | Names | Sites |
|---|---:|---:|
| `promote` | 94 | 1171 |
| `keep: subject is the private object` | 24 | 183 |
| `churn` | 2 | 7 |
| `rewrite now` | 0 | 0 |
| **total** | **120** | **1361** |

### 55.7 What Phase 6 has left

With 6d closed as a document, the phase's remaining work is:

1. **The `drop as duplicate` / `drop as dead` rows from §50.2**, under §51.6's rule —
   redundancy, coupling or vacuity, never seconds. §50.2's only `drop as dead` row was
   `streaming.pop`, already resolved in 6c as a rewrite rather than a drop. The two
   duplicate candidates §12.5 named are mostly, **but not entirely**, frozen:

   | §12.5 pair | Status |
   |---|---|
   | `test_layout_contract.py`'s screen registry vs `test_callback_co_presence.py::_phase_screens` | **fully frozen** — both sides are §50.3 whole-file entries, so neither can be consolidated |
   | `TestMockBuffers` (`test_streaming_characterization.py`) vs `TestMockDeliveryAck` (`test_designer.py`) | **partly frozen** — the first is a whole-file entry; the second is not, but one of its six tests, `test_delivery_preserves_prior_store_keys`, is **tier-A** and in the floor |

   So the duplicate-coverage bullet in the plan has far less scope than it looks: of the
   two candidates Phase 1 nominated, the only genuinely available material is the five
   non-floor tests of `TestMockDeliveryAck` (`test_designer.py:1435–1551`) — and those
   would have to be shown redundant against `TestMockBuffers` on the merits, not merely
   overlapping in subject.
2. **The chunk-factory swap** — §50.5(c)'s shape, with `_hidden_params = {}`, `usage`
   absent by fidelity, the usage tests confirmed specifically, and one positive-path
   assertion proving `_usage_fields` still returns a populated dict.
3. **6z, last** — §51.6's exit condition.

### 55.8 Gate results (verbatim)

Documentation only; no `src/`, no `tests/`, no `noqa` change. `pyproject.toml` is edited
only in the plan's sense — the *plan file* changed, not the project config.

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | — | not re-run; `git diff --stat` against 6d shows only `CLEANUP_INVENTORY.md` and `SPEC4_CLEANUP_PLAN.md`, so §53.4's `4175 passed, 1 skipped` and `909 miss` stand |

**Off-limits check:**

| Kind | Result |
|---|---|
| 7 whole-file entries | absent from the diff |
| 19 tier-B files / 33 classes | 0 files with hunks |
| 456 node ids | **456 / 456 collect**, 0 failures |

### 55.9 `promote`, split by kind — the two Phase 7 items

94 names and 1,171 sites is not one work item. Split by whether promoting requires a
decision:

| Kind | Names | Sites | What Phase 7 does |
|---|---:|---:|---|
| **`rename`** | **81** | **1,042** | drop the underscore, re-point the sites. No design decision |
| **`design seam`** | **13** | **129** | decide the public contract first — this is Untangle work, not renaming |

**The rule that assigns the kind**, applied mechanically to each name's definition:

- a **generator** → `design seam`. Making it public commits to a yield protocol, and
  every one of these is a phase of a turn.
- **mutates `session`** (subscript assignment, `pop`/`update`/`setdefault`/`clear`, or
  `del`) → `design seam`. It is a step in a turn, not a function of its inputs.
- takes an **`on_chunk` callback** → `design seam`; the contract is the protocol.
- otherwise → `rename`.

A `session` parameter alone is **not** enough. A layout builder that *reads* the session
and returns a component tree is a function of its argument and renames mechanically —
an earlier version of this rule classified all nine of `layouts._chat`'s names as seams
on the parameter name alone, which would have sized 164 sites of pure formatting work as
design judgment.

#### The rename half, ordered by sites-per-name

Phase 7 starts at the top: one edit retires the most coupling.

| Cluster | Names | Sites | Sites/name |
|---|---:|---:|---:|
| `session` | 5 | 281 | **56.2** |
| `layouts._chat` | 9 | 164 | 18.2 |
| `layouts` | 10 | 152 | 15.2 |
| `layouts.designer` | 7 | 100 | 14.3 |
| `agents.code_scanner` | 7 | 82 | 11.7 |
| `agents.brainstormer` | 5 | 38 | 7.6 |
| `agentifier.agentifier` | 20 | 140 | 7.0 |
| `agents._seam_check` | 7 | 39 | 5.6 |
| `callbacks.designer` | 4 | 21 | 5.2 |
| `llm` | 4 | 16 | 4.0 |
| `project_manager` | 3 | 9 | 3.0 |

`session._default_session` alone is **248 of the 281** — the single highest-leverage
rename in the repo, and a `sed` once the name is public.

#### The design-seam half — all 13

| Name | Cluster | Sites | Why a seam, not a rename |
|---|---|---:|---|
| `_persist_artifacts` | `session` | 35 | mutates `session` — a turn step, not a function of its inputs |
| `_load_working_dir` | `session` | 24 | mutates `session` — a turn step, not a function of its inputs |
| `_get_agent_gen` | `session` | 20 | mutates `session` — a turn step, not a function of its inputs |
| `_run_spec_phase` | `agentifier.agentifier` | 16 | generator — promoting commits to a yield protocol |
| `_run_cross_cutting_phase` | `agentifier.agentifier` | 8 | generator — promoting commits to a yield protocol |
| `_complete_agentifier` | `agentifier.agentifier` | 6 | generator — promoting commits to a yield protocol |
| `_run_catalog_phase` | `agentifier.agentifier` | 5 | generator — promoting commits to a yield protocol |
| `_rehydrate_vision_from_disk` | `agents.brainstormer` | 4 | mutates `session` — a turn step, not a function of its inputs |
| `_handle_reentry` | `agentifier.agentifier` | 3 | generator — promoting commits to a yield protocol |
| `_finalize_specs` | `agentifier.agentifier` | 3 | generator — promoting commits to a yield protocol |
| `_begin_priority_phase` | `agentifier.agentifier` | 2 | generator — promoting commits to a yield protocol |
| `_run_priority_phase` | `agentifier.agentifier` | 2 | generator — promoting commits to a yield protocol |
| `_stream_suppressing_json` | `agentifier.agentifier` | 1 | generator — promoting commits to a yield protocol |

Nine of the thirteen are `agentifier.agentifier` phase runners, five of which already
carry rule-12 complexity `noqa`s (§27.4). **Promoting these is the same work as the
`yield from` sub-generator backlog item** — the public contract and the sub-generator
split are one decision, not two. Phase 7 should take them together or not at all.

The three `session` mutators (`_persist_artifacts` 35, `_load_working_dir` 24,
`_get_agent_gen` 20 — 79 sites) are the other cluster of judgment: each mutates the
session dict in place, so the public contract has to say what it may touch.

## 56. Phase 6f — the duplicate and dead rows: nothing qualifies

**6e does not exist** (§55.3: zero `rewrite now` sites). This is the next sub-phase in
the plan's remaining order. **No test was pruned, and that is the finding.**

### 56.1 The standard: the mutation check, inverted

§51.6 gives the forward form — a rewrite must be shown to fail for the defect it
replaces. The pruning form is its inverse:

> **A test is redundant only if every mutation it catches is also caught by a test that
> stays.** A test that catches a mutation alone is kept, whatever its subject overlap.

Subject overlap is what §12.5 recorded, and subject overlap is not redundancy.

### 56.2 The candidates

| §50.2 / §12.5 row | Status |
|---|---|
| `drop as dead` — `patch("spec4.callbacks._chat.streaming.pop")` | already resolved in **6c** as a rewrite, not a drop: the assertion was vacuous but the invariant was live (§53.1) |
| duplicate — `test_layout_contract.py` screen registry vs `test_callback_co_presence.py::_phase_screens` | **not testable**: both sides are §50.3 whole-file entries, frozen |
| duplicate — `TestMockBuffers` vs `TestMockDeliveryAck` | **tested below.** `TestMockBuffers` is frozen (net); `TestMockDeliveryAck` has six tests, one of them tier-A, five nominally available |

So the entire pruning surface Phase 1 nominated comes down to five tests at
`tests/test_designer.py:1435–1551`.

### 56.3 The catch matrix

Nine mutations to the delivery/acknowledgement logic in
`callbacks/designer/__init__.py::on_mock_stream_poll`, each applied to the working tree,
both classes run, then reverted.

| Mutation | `TestMockBuffers` (stays) | `TestMockDeliveryAck` (candidate) |
|---|---|---|
| M1 pop the buffer on the delivery tick — kills re-delivery | FAIL | FAIL |
| M3 acknowledge on `step != 6` instead of `!= 5` — bounces a Refine click | FAIL | FAIL |
| M4 never pop on acknowledgement — leaks the buffer | FAIL | FAIL |
| M5 runaway valve never fires | FAIL | FAIL |
| M6 progress is 99, not 100, on completion | FAIL | FAIL |
| M9 delivery payload built from scratch, not spread over the store (D-DM8) | FAIL | FAIL |
| **M7 reinstate the old fixed 6-tick re-delivery window** | **PASS** | **FAIL** |
| M8 runaway-valve message loses its saved-mock guidance | PASS | PASS |

### 56.4 The verdict: not redundant

**M7 is caught by the candidate and missed by the test that stays.** Sole catcher:
`TestMockDeliveryAck::test_redelivers_far_beyond_the_old_fixed_window`.

That is not an incidental difference. M7 restores **the exact defect the class was
written for** — its docstring: *"The previous fixed re-delivery window counted requests
sent, not deliveries applied, and could expire before the first response ever reached the
browser, stranding the UI at step 5 with the interval off."* The production comment at
note 2 says *"Don't reintroduce one."* `TestMockBuffers` drives a generation from start
to acknowledged delivery and never polls far enough for a six-tick window to matter.

Under §56.1 the class is **kept in full**. Six of the eight mutations are caught by both,
which is real overlap — and overlap is not the standard.

**Pruned in this sub-phase: nothing.** Per §51.6, a sub-phase that prunes nothing is a
finding rather than a failure, and the seconds rule forbids the alternative argument.

### 56.5 A gap the matrix found on the way

**M8 is caught by neither class.** The runaway valve's user-facing message — *"The mock
was generated and saved, but this page stopped receiving updates… Refresh the page to
load the saved mock, or click Retry"* — can be replaced with anything and the suite stays
green. The *branch* is covered (M5 fails both); the *text the user reads at the one dead
end this feature has* is not.

Recorded, not fixed: adding an assertion is out of scope for a pruning sub-phase and
would be new coverage rather than rationalisation. **Logged for Phase 7** alongside the
seam work.

### 56.6 Gate results (verbatim)

No file changed. Every mutation was reverted and `git status --porcelain` was empty
before and after the matrix.

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `219 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | — | unchanged from §53.4: `4175 passed, 1 skipped`, `909 miss` |

**Off-limits:** nothing under `tests/` touched; 456/456 collect.

## 57. Phase 6g — the chunk factory

§50.5(c). The one change in Phase 6 that moves the runtime.

### 57.1 What landed

`tests/_chunks.py` — a new shared helper, following `tests/_golden.py`'s convention
(`from tests._chunks import …`) rather than a fixture, because the factory is called
from module-level helpers and list comprehensions, not only from test bodies.

Both per-character `MagicMock` factories are deleted and both modules import it:
`tests/test_agents.py:49` and `tests/agentifier/test_agentifier_orchestrator.py:119`.
They were byte-identical.

### 57.2 The shape mirrors the real type, and one default is not what it looks like

Fields were read off a constructed `litellm.types.utils.ModelResponseStream`, not
assumed:

| Type | Fields carried |
|---|---|
| `ModelResponseStream` | `id`, `created`, `model`, `object`, `system_fingerprint`, `provider_specific_fields`, `choices` |
| `StreamingChoices` | `index`, `delta`, `finish_reason`, `logprobs`, `enhancements` |
| `Delta` | `content`, `role`, `function_call`, `tool_calls`, `audio`, `images`, `reasoning_content`, `thinking_blocks`, `provider_specific_fields` |

And the two §50.5(c) singled out:

| Field | Real default | Stand-in |
|---|---|---|
| `_hidden_params` | `{}` — LiteLLM always attaches the dict | `{}` |
| `usage` | **absent** — `hasattr(chunk, "usage")` is `False` | **absent**; attached only when the caller passes one |

So the stand-ins are rejected by `llm._chunk_usage` and `llm._hidden_usage` **for the
reason the real object is rejected**: `_get`'s `getattr(…, None)` yields `None` and
`_usage_fields(None)` returns `None` on its first line; `_hidden_usage` sees a `{}` with
no `"usage"` key. Not because a `SimpleNamespace` happens to lack a field.

`make_usage()` supplies the other shape — the usage chunk LiteLLM appends under
`include_usage`.

### 57.3 The usage confirmation, both halves

`uv run pytest tests/test_usage_capture.py tests/test_streaming_characterization.py
tests/test_llm.py` → **155 passed**. All three already used their own `SimpleNamespace`
helpers and never touched the `MagicMock` factories, so this confirms the swap disturbed
nothing rather than that it was exercised.

Which is exactly why §50.5(c) asked for the positive path separately. Two tests added to
`tests/test_usage_capture.py::TestStreamCapture`:

| Test | Asserts |
|---|---|
| `test_shared_factory_content_chunk_carries_no_usage` | `not hasattr(chunk, "usage")`, and the record comes back `usage_missing: True` — the negative half, via the real `complete_stream` |
| `test_shared_factory_usage_chunk_reaches_record_usage` | a chunk carrying **real counts** produces `usage_missing: False` and `(120, 30, 150)` — the positive half |

**Mutation check.** With `make_stream_chunk` altered to ignore its `usage` argument:

| | Result |
|---|---|
| `TestStreamCapture` before the mutation | 16 passed |
| after | **1 failed** — `test_shared_factory_usage_chunk_reaches_record_usage` |

A stand-in that could only ever produce the no-usage shape would otherwise have passed
every negative assertion in the module while severing `_record_usage` from its input.

`test_magicmock_chunks_never_look_like_usage` is **kept**: it guards the hazard for
whatever still builds a `MagicMock` chunk, and remains true.

### 57.4 Runtime — paired, per §51.6

Baseline and candidate measured back to back in one session, two runs each; the recorded
figure is the delta.

| | Runs | Median |
|---|---|---:|
| Baseline (`HEAD`, `MagicMock` chunks) | 139.21 s, 138.74 s | **138.98 s** |
| Candidate (shared namespace factory) | 87.25 s, 87.78 s | **87.52 s** |
| | | **−51.46 s** |

**87.5 s against the ≤ 96 s target** (§51.1), with 8.5 s of headroom. No absolute figure
from an earlier session is used or needed.

`tests/test_agents.py` alone went from 40.65 s to 1.31 s together with the orchestrator
module (§50.1 measured the file at 40.65 s on its own).

**No test was pruned for this**, and none could have been — §51.6 forbids seconds as a
pruning argument. The runtime came from changing what a stand-in costs, not from removing
anything.

### 57.5 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `220 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4177 passed, 1 skipped in 105.23s` (exit 0) |
| Coverage | same run | `TOTAL 12421 stmts, 909 miss, 93%` — **at the §51.6 baseline** |

Collected **4,178**, up 2: the two usage tests. Nothing removed.

**Off-limits check:**

| Kind | Result |
|---|---|
| 7 whole-file entries | absent from the diff |
| 456 node ids | **456 / 456 collect**, 0 failures |
| 19 tier-B files / 33 classes | **1 file with hunks — 0 failures** |

`tests/test_agents.py` is a tier-B file. Its listed classes and current ranges:
`TestLoadDesignManifest` **2271–2298**, `TestAiFeaturesForPhaserFullSurface`
**4962–5060**, `TestPhaserSpecReferenceDirective` **5227–5268**. The three hunks land at
lines **18**, **49** and **3565** — the import, the deleted factory, and
`_chunkify_stream`'s return annotation. None intersects a listed range, and the file
carries no tier-A test. **Reported, per §51.6's template.**

## 58. Phase 6z — the eval-only assertions, ported

§51.6's exit condition. One new file, `tests/agentifier/test_requires_inversion_arms.py`,
22 tests. Nothing else changed.

### 58.1 Why this was an exit condition

Phase 6a's `testpaths` moved four `evals/` modules out of collection, and with them the
**only** coverage in the repo of 15 statements in
`spec4.agentifier.requires_reconciler` and one in `spec4.agents.brainstormer` (§51.2).
The logic is the D-RI signal classification — what decides whether a declared `requires`
edge points the wrong way. Phase 6 does not touch `src/`, so it was not urgent; the
moment a `src`-touching phase begins, it is.

### 58.2 One test per arm

| Class | Arm | Statements |
|---|---|---|
| `TestStemming` | `_norm_chunk`'s minimal stemming — `ing` above five characters, `s` above three, both in order, short chunks left alone | 154–156 |
| `TestStemLengthGuard` | D-RI13: a single-chunk stem never matches; a sub-six-character stem never matches; a long enough one matches as a prefix | 263 |
| `TestProducerMarginTieBreak` | the production map declines a close runner-up, takes a clear leader, rejects overlap below the floor, and returns `None` with no specs | 304, 306 |
| `TestS3OverlapArms` | forward-dominant overlap; reverse-dominant **with** forward signals (D-RI11); reverse with **zero** forward counter (D-RI12); and the **reverse lean, uncorroborated, not classified** arm that classifies nothing | 353, 363–369 |
| `TestTriggerMatching` | S1 fires when the trigger awaits the producer by name; S2's selective vision-feature fallback fires under the link cap and is skipped above it | 488, 518–525 |
| `TestFeatureNamesGuards` | `_feature_names` returns `[]` for a non-dict vision and a non-dict `vision_statement` | brainstormer 284 |

Two classes also pin the constants the arms are defined against — `PROD_FLOOR`/
`PROD_MARGIN` at 3/2 and `S3_FLOOR`/`S3_DOMINANCE` at 4/2 — so a silent retune of a
threshold fails here rather than shifting behaviour under the arms.

These are **characterisation** tests: they pin what the code does today.

### 58.3 Three shape errors worth recording

The first draft failed four tests, all because the constructed nodes did not match the
real ones. Recorded because the next person writing against this module will hit them:

| Assumed | Actually |
|---|---|
| `node["trigger"]` | `node["invocation"]["trigger"]` — `_trigger_text` reads nothing else |
| a spec is `{"id", "name", "description"}` | `build_production_map` scores against `spec["outputs"]["primary"]` + `schema_notes`; a spec with no `outputs` contributes no tokens and is skipped |
| `build_production_map(nodes, specs)` | `build_production_map(specs, nodes)` |

The middle one is the dangerous shape: a spec with the wrong key produces an **empty**
map rather than an error, so a test built that way passes its "no producer named"
assertion for entirely the wrong reason. Both negative assertions in
`TestProducerMarginTieBreak` are therefore paired with a positive one
(`test_a_clear_leader_names_the_producer`), so an empty map cannot satisfy the class.

### 58.4 The exit check

| | Before 6z | After 6z | Pre-`testpaths` (with `evals/`) |
|---|---:|---:|---:|
| `agentifier/requires_reconciler.py` | 26 miss (90%) | **9 miss (97%)** | 11 miss (95%) |
| `agents/brainstormer.py` | 10 miss (97%) | **9 miss (97%)** | 9 miss (97%) |
| **suite total** | 909 | **891** | 893 |

**891 ≤ 893.** §51.6's exit condition is met — and `requires_reconciler.py` is now
**two statements better than the eval ever left it**, because the arms are tested
individually rather than incidentally through a probe.

The 9 remaining misses in `requires_reconciler.py` (179, 215, 227, 233, 248, 288, 294,
299, 571) were never covered by `evals/` either; they are outside 6z's scope, which was
the 16 statements the `testpaths` change cost.

### 58.5 Gate results (verbatim)

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| Ruff format | `uv run ruff format --check src/ tests/` | `221 files already formatted` (exit 0) |
| Mypy | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4199 passed, 1 skipped in 106.54s` (exit 0) |
| Coverage | same run | `TOTAL 12421 stmts, 891 miss, 93%` — **below the §51.6 baseline of 909, and below 893** |

Collected **4,200**, up 22. Nothing removed.

**Off-limits check:**

| Kind | Result |
|---|---|
| 7 whole-file entries | absent from the diff |
| 19 tier-B files / 33 classes | 0 files with hunks — the only change is a new file |
| 456 node ids | **456 / 456 collect**, 0 failures |

## 59. Phase 6 close-out

### 59.1 What the phase did, sub-phase by sub-phase

| Sub-phase | § | Change | Tests |
|---|---|---|---|
| **6a** | §51 | `testpaths = ["tests"]` — the only `pyproject.toml` edit | −82 (`evals/` out of collection) |
| **6b** | §52 | three patch strings re-aimed at their call-site seams | 0 |
| **6b addendum** | §52.5 | the `os` proxy moved to `conftest.py` as the `module_seam` fixture | 0 |
| **6c** | §53 | `streaming.pop`'s vacuous assertion replaced by two real ones | +1 |
| **6d** | §54–§55 | the Phase 7 seam document — **no rewrites**, by design | 0 |
| **6e** | — | **does not exist** (§55.3: zero `rewrite now` sites) | — |
| **6f** | §56 | duplicate/dead rows — **nothing qualified for pruning** | 0 |
| **6g** | §57 | the chunk factory: `tests/_chunks.py` replaces two `MagicMock` factories | +2 |
| **6z** | §58 | the eval-only D-RI arms ported into `tests/agentifier/` | +22 |

**Nine commits. No production file was changed at any point.** The single
non-test edit in the entire phase is one `pyproject.toml` key.

### 59.2 Counts

| | Phase 5p | Phase 6 close | |
|---|---:|---:|---|
| Collected | 4,257 | **4,200** | −57 |
| — of which `evals/` | 82 | 0 | moved out of collection, not deleted |
| — under `tests/` | 4,175 | **4,200** | **+25** |
| Passed / skipped | 4,256 / 1 | 4,199 / 1 | |

**No test was deleted in Phase 6.** The suite under `tests/` grew by 25: one rewrite
split into two (6c), two usage tests (6g), and 6z's 22.

### 59.3 Runtime — paired, in one session

| | Runs | Median |
|---|---|---:|
| Phase 5p baseline (`tests/` + `evals/`, 4,257) | 139.20 s, 139.76 s | **139.48 s** |
| Phase 6 close-out (`tests/`, 4,200) | 86.70 s, 87.32 s, 86.79 s | **86.79 s** |
| | | **−52.69 s** |

**86.8 s against the ≤ 96 s target** (§51.1, restated in §51.6), with 9.2 s of headroom.
Both halves measured back to back on the same machine, per §51.6 — the baseline was
reconstructed by checking `pyproject.toml` and `tests/` out at `a86a2ee` and running
`tests/ evals/` explicitly.

Essentially all of it is 6g. `testpaths` was worth ~0.4 s (§51.1), and nothing was
pruned for speed, because §51.6 forbids it.

### 59.4 Coverage

| | Misses | |
|---|---:|---|
| Phase 0 / 5p baseline (with `evals/` collected) | 893 | never a `tests/`-only figure |
| After 6a (`tests/` only) | 909 | the 16 statements `evals/` had been carrying |
| **Phase 6 close** | **891** | **below both** |

`agentifier/requires_reconciler.py` ends at **97%** (9 misses) against 95% when `evals/`
was carrying it and 90% immediately after `testpaths`. The gate now measures what it
claims to, and measures more of it.

### 59.5 Final gate and off-limits

| Gate | Result |
|---|---|
| `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) |
| `uv run ruff format --check src/ tests/` | `221 files already formatted` (exit 0) |
| `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) |
| `uv run pytest --cov=spec4 …` | `4199 passed, 1 skipped`; `12421 stmts, 891 miss, 93%` |

**The floor held at every one of the nine commits.** 456/456 node ids collect; no
whole-file entry was ever in a diff; two sub-phases touched a tier-B file outside its
listed classes and both are reported in the §51.6 template (§53.4, §57.5).

§27.4's eleven complexity `noqa`s are still eleven.

### 59.6 Phase 7 candidates, consolidated

Everything Phase 6 logged, in the order it should be taken.

| # | Item | Source | Size |
|---|---|---|---|
| 1 | **Promote seams — the `rename` half.** Drop the underscore, re-point the sites. Start at `session` (56.2 sites/name; `_default_session` alone is 248), then `layouts._chat`, `layouts`, `layouts.designer`, `code_scanner`, … | §55.9 | **81 names, 1,042 sites** |
| 2 | **Promote seams — the `design seam` half.** Nine are `agentifier` phase runners and **are the same decision as** the `yield from` sub-generator backlog item — take them together. Three are `session` mutators (`_persist_artifacts` 35, `_load_working_dir` 24, `_get_agent_gen` 20) | §55.9, §27.4 | **13 names, 129 sites** |
| 3 | **Do not promote the 24 `keep: subject is the private object` names.** The collection is the test's subject; promoting invites a rewrite that replaces a drift guard with an output check | §54.1, §55.4 | 24 names, 183 sites |
| 4 | **The golden petition** applies to any promotion whose tests live in a §50.3 whole-file entry — import lines alone, goldens byte-identical, off-limits passes on the rest | §54.7 | pre-shaped |
| 5 | **Production seams for stdlib calls under test.** `_usage._write_atomic`'s `os.replace`/`os.fdopen` get module-level aliases, patched by name; then **delete `module_seam` and `_ModuleSeam` from `tests/conftest.py`** and the fixture argument from the two atomicity tests | §52.5 | small |
| 6 | **The runaway-valve message is asserted by nothing.** Its branch is covered; the text the user reads at the feature's one dead end is not — it can be replaced with anything and the suite stays green | §56.5 | one test |
| 7 | **Type hygiene** — 290 `Any` in `src/spec4/**` | §49.5 | large |
| 8 | **`project_manager` root-siblings inconsistency** | §27.7 | medium |
| 9 | **PLR2004** (49 in `src/`) — the natural follow-up to 5p(b)'s magic-value work | §49.4 | medium |
| 10 | **13 `E501` in `scripts/e2e_agentifier.py`** — predate Phase 5, outside the Rule 6 gate | §49.7 | trivial |
| 11 | **`tests/agentifier/test_try_again.py` reads `agentifier.py` as text** for `"agentifier_*"` session keys. Survives today only because 5k moved code *within* the file; a future split breaks it **silently, as a shrinking set** | §50.2 kind 6 | one test |
| 12 | **`spec4.layouts` exports a function named `_round_cost`, shadowing the submodule of that name** — forcing `sys.modules[...]` in `test_cost_summary.py`. A rename retires the idiom | §50.2 kind 5 | small |
| 13 | **`tests/README.md`** is stale, and now also omits the golden/snapshot mechanism, the two env vars, `testpaths`, and `tests/_chunks.py` | §12.5, plan | small |

Item 1 is the largest single input Phase 7 has and the cheapest per site; item 2 is where
the judgment is. They are separable, and item 1 does not depend on item 2.

## 60. Phase 7 pre-work — impact inventory before the first `src/` edit

Recorded 2026-09-10 on branch `look-rework`, at `f862f65` (Phase 6 close-out). **Nothing
under `src/`, `tests/` or `pyproject.toml` was written.** Everything that had to execute —
the rename proof, a dry run of every rename that is not a stop, the mutation runs — ran in
throwaway clones under the session scratchpad and was never committed; the repo's
`git status --porcelain` was empty before and after. The only artifact is this section.
**§60 proposes; Phase 7 decides**, and begins only on approval of §60.

The scripts lived in the scratchpad and are described inline so every number can be
re-derived. The rename check is given in full (§60.2), because Phase 7 runs it at every
rename commit.

### 60.0 Where this run's directive and the record disagree

Nine points. In each the record or the plan wins, per the standing rule; where the
directive's intent survives the correction, it is kept.

**(a) The 81 live in §55.9, not §54.** The directive places the 81 rename names, their
sites-per-name order and "§54's corrected count" in §54. §54 covers one cluster (34 names,
and 87 sites that §55.1 corrected to 208); the 81, the split rule and the order are
§55.9's, and the corrected count is §55.1's AST count. **§55.9 is used throughout.**
Re-derived at `f862f65` with §55's own scripts: **1,364 sites** (§55: 1,361); rename half
**81 rows, 1,045 sites** (§55: 1,042). All three extra sites are `_feature_names`, 6 → 9,
added by 6z's `TestFeatureNamesGuards` (§58.2). No disposition, kind or cluster order
changes — `agents.brainstormer` goes from 7.6 to 8.2 sites per name and stays sixth.

**(b) 81 rows are 80 functions.** `_chat_layout` is listed under two clusters —
`layouts._chat` (37 sites) and `layouts` (7) — because tests import it by both paths. One
rename covers both; it sits in batch 2, and batch 3 carries nine names, not ten.

**(c) The `Any` count is not a mypy count.** The directive asks for "the `mypy --strict`
`Any` count that 5p(h) deferred (expected 290)". `mypy --strict` has no such count —
explicit `Any` is legal under strict, which is why the gate is green;
`--disallow-any-explicit` reports **1,009** errors in 84 files. The 290 is the second line
of the survey 5p ran before writing §49.5 (recovered from that session's command log):
`grep -rc ': Any' src/spec4/ --include=*.py`, summed — **lines containing `: Any`**. It
reproduces exactly. The survey's first line, `grep -c ': Any\b\|-> Any\b'
src/spec4/**/*.py`, printed 171 because bash expands `**` as `*` without `globstar` (57 of
92 files, no root module) — it is not the figure 5p recorded. **Record wins: 290 stands,
named for what it measures.** §60.5 classifies exactly those 290 lines and sizes the two
populations the grep cannot see.

**(d) "§59.6 item 14" is item 6, and §56.3 has a row that never ran.** §59.6 has thirteen
items; the runaway-valve message is item 6. §56.3 announces nine mutations and tabulates
eight: **M2 was never measured.** Its anchor, `return final_buf, new_store, no_update`,
does not exist — the line is `return deliver_buf, new_store, no_update`
(`callbacks/designer/__init__.py:312`) — and §56's harness printed
`-- anchor not found --` and moved on. Measured here, M2 is caught by both classes
(§60.5). And §56.5 / §59.6 item 6 overstate M8: the message "can be replaced with anything
and the suite stays green" is **not** true — replacing the whole message fails two tests
that assert `"Refresh the page"`. What nothing asserts is the *"was generated and saved"*
clause, which is exactly what M8 removed. Corrected in §60.5.

**(e) The net has three kinds.** The directive's "net references" counts sites in
whole-file entries and tier-B classes. §50.3's rule covers the 85 tier-A and ordering node
ids as well ("may not be edited"), though its check is collection. **Record wins:** §60.2
counts all three (W/B/A). The rename half changes the bodies of **23 tier-A nodes** (19
once the stops are held).

**(f) Whole-file entries take §54.7, not the new petition.** The plan's Phase 7 text: *"a
promotion whose tests live in a §50.3 whole-file entry needs the pre-shaped petition in
§54.7."* The directive places only `test_renderer_goldens.py` under §54.7 and the other
whole-file entries under the new rename petition, whose first check admits identifier
substitution in test bodies. **Plan wins.** Every whole-file entry a rename reaches stays
under §54.7 as written — import lines alone — and a rename can meet it by importing the
public name under the old local one (`from spec4.session import default_session as
_default_session`), so that no body line changes. Proven on one name and across 74
(§60.2). The §60.3 petition covers what the plan does not name: tier-B classes and tier-A
node ids. Where a whole-file entry reaches a name *by attribute*, no import can help and
§54.7 cannot be met: three names, all stops (§60.3).

**(g) A substitution rewrites string references; what it gets wrong is elsewhere.** The
directive says string references "survive a mechanical rename silently broken". That is
true of an AST or IDE rename, which leaves strings alone — and the break is then loud:
`patch()` raises `AttributeError`, `monkeypatch.setattr` raises by default, a stale
`__all__` entry trips ruff's F822, a stale `sys.modules` key raises `KeyError`. The
mechanism §60.2 defines is a word-boundary substitution, which rewrites all 96 literal
string references along with the code. What *it* gets wrong is different, and §60.2 lists
each: an old name that is also a module name (4), a new name already bound where the old
one is used (3 collisions), code outside the gate that nothing would run (`evals/`,
`scripts/`), and tracked `.spec4/` files it must not write (Rule 2).

**(h) One of the "nine agentifier phase runners" is neither.** `_stream_suppressing_json`
is `spec4.agents._reask.stream_suppressing_json` — already public at its owner, and the
`yield from` target of three other agents' `run` as well as agentifier's — imported into
`agentifier.py:89` under the private alias its module docstring calls "its pre-4j name"
(`agentifier.py:26`). §60.4 gives it its own row. The other eight are agentifier
generators, and §60.4 writes their proposal once.

**(i) The sequence omits the plan's audit.** The directive's §60.6 order ends at type
hygiene and root-siblings. The plan's Phase 7 also carries the Phase 0 re-measurement and
`CLEANUP_REPORT.md`, the symptom checklist, the docs and the inventory fold, and §59.6
items 9–13 have no slot. **Plan wins:** §60.6 places them.

**Untouched, as instructed:** 5p(h) type hygiene (sized in §60.5; no annotation changed);
the `yield from` sub-generator backlog (§27.4 — sized with the agentifier seams in §60.4);
the `project_manager` root-siblings inconsistency (§60.5); `evals/` (read for references
only, §60.5). §27.4's eleven complexity `noqa`s are still eleven, beside the twelve
arity-only `PLR0913`s.

### 60.1 Baseline at the Phase 6 close

Measured on `f862f65`, clean tree, before anything else.

| Gate | Command | Result | §59 | |
|---|---|---|---|---|
| Ruff — promoted set `E, F, C90, PLR0912, PLR0913, PLR0915, SIM, B, ARG` | `uv run ruff check src/ tests/` | `All checks passed!` (exit 0) | same | ✅ |
| Ruff format | `uv run ruff format --check src/ tests/` | `221 files already formatted` (exit 0) | same | ✅ |
| Mypy, strict | `uv run mypy src/` | `Success: no issues found in 92 source files` (exit 0) | same | ✅ |
| Tests | `uv run pytest --cov=spec4 --cov-report=term-missing -q` | `4199 passed, 1 skipped` (exit 0); **4,200 collected** | 4,200 / 1 | ✅ |
| Coverage | same run | `TOTAL 12421 stmts, 891 miss, 93%` | 891 | ✅ |
| Off-limits | §50.3, all three kinds, fresh `--collect-only` | 188 + 85 + 183 = **456 / 456** collect, 0 failures; 0 tier-B files with hunks; no whole-file entry in the diff | 456 | ✅ |
| `Any` — 5p(h)'s figure | `grep -rc ': Any' src/spec4/ --include=*.py`, summed | **290** lines in 47 files | 290 | ✅ |

**Every figure matches §59; nothing moved between the Phase 6 close and this run.** The
wall-clock (120.71 s) is not a comparison figure under §51.6, and none is made.

The 290 by file: `agents/code_scanner/_review_render.py` 27 · `llm.py` 21 ·
`feature_specs.py` 19 · `callbacks/designer/_wizard.py` 18 ·
`agents/stack_advisor/_render.py` 17 · `callbacks/_artifacts.py` 16 ·
`callbacks/designer/_refine.py` 15 · `callbacks/_setup.py`, `_gate.py`, `_chat.py` 11 each ·
`callbacks/_nav.py` 10 · `callbacks/__init__.py` 9 · `streaming.py`,
`callbacks/designer/_mock_gen.py` 7 each · `agents/phaser/__init__.py`,
`agents/feature_speccer.py`, `agents/brainstormer.py`, `agentifier/subagents.py`,
`_phase_markdown.py` 6 each · `session.py`, `layouts/designer.py`, `_usage.py` 5 each ·
`layouts/_shared.py`, `callbacks/designer/__init__.py`, `agents/designer.py`,
`agentifier/_seed.py` 4 each · `usage_report.py`, `app.py` 3 each ·
`layouts/_agent_rows.py`, `agents/code_scanner/__init__.py`, `agents/_feature_context.py`,
`agentifier/reference_verifier.py`, `agentifier/agentifier.py` 2 each · and 1 each in
`stack_routing.py`, `layouts/_setup.py`, `layouts/_round_cost.py`,
`layouts/_artifact_view.py`, `agents/phaser/_phase_extract.py`, `agents/_tool_probe.py`,
`agents/_stack_context.py`, `agents/_seam_check.py`, `agents/_reask.py`,
`agents/_phase_schema.py`, `agents/_image_probe.py`, `agents/_code_review_schema.py`,
`agentifier/requires_reconciler.py`, `agentifier/grounding.py`. By area: `callbacks/` 112,
`agents/` 78, root modules 70, `agentifier/` 16, `layouts/` 14.

Around it, for scale — none of these is a gate figure:

| Population | Count | Measure |
|---|---:|---|
| `: Any` lines — the 290 | 290 | 5p's grep |
| `-> Any` return lines | 148 | `grep -rn -- '-> Any\b' src/spec4` |
| `dict[str, Any]` | 891 lines, 972 occurrences | grep |
| every `Any` token, imports included | 1,741 | `grep -rwo Any` |
| `mypy --disallow-any-explicit` | 1,009 errors in 84 files | not part of the gate |

Re-derived for §60.2 with §55's scripts: 1,364 sites; 81 rows / 1,045 sites `rename`;
13 / 129 `design seam` — the only change is §60.0(a)'s +3.

### 60.2 The rename half — per-name dry run

Every tracked text file (`git ls-files`, minus this record) was scanned for each of the 80
names — the tokenizer to tell code from string from comment, the AST for bindings, scopes
and the §50.3 line ranges. Then the plan was **executed in a scratch clone and checked**:
one name end to end as the proof, the 74 names that are not stops as a dry run, and each
stop alone. Every finding below that bears on whether a rename works was confirmed by
executing it.

**The columns.**

- **Proposed public name** — the private name without its underscore, §54.3's rule. None is
  overridden here: where that name collides, the row is a stop and Phase 7 picks.
- **Collision** — `yes` is a stop. The public name is already bound at module level in
  the owner, in any module that re-exports the private name, **or in any scope that also
  uses the private name** (the case a module-level check misses: a local variable the
  rename would turn into `x = x(...)`); or it equals a string literal used as a component
  id or session key. There are no star imports in `src/`. *Clash* marks a public name that
  already exists **elsewhere** — not a Python collision and not a stop under the
  directive's definition, but two public functions with one name; flagged for Phase 7's
  naming review.
- **String refs** — literal strings that reach the name: `patch("…")` targets,
  `patch.object` / `monkeypatch.setattr` attribute strings, `__all__` entries,
  `sys.modules` keys. Listed by file:line under each batch.
- **Net refs W/B/A** — occurrences inside a §50.3 whole-file entry / a listed tier-B
  class / a tier-A or ordering node, ranges read from the tree (an occurrence counts once,
  in that order of precedence).
- **D-refs** — a comment block or docstring that holds both the name and a D-number
  (`D-[A-Z]{2,3}\d+`). The substitution updates them in the same commit.
- **Sites** — §55's AST count at `f862f65` (§55's figure in brackets where it differs).

#### What the scan found

1. **Three collisions — stops.** `_breadth_panel` and `_retry_panel`: `_chat_layout` keeps
   both panels in locals of the public names' spelling (`layouts/_chat.py:103–104`), so
   the renamed lines read `breadth_panel = breadth_panel(session)`. `_agent_rows`:
   `layouts/_agent_rows.py:302` already defines a different public `agent_rows` — the
   data function the layout builder calls at `:425`. **All three confirmed by applying
   them alone:** the two panels trip ruff F823 at `_chat.py:103` / `:104` and fail 34
   tests each with `UnboundLocalError` — **mypy passes both**, so ruff and the suite are
   what catch it; `_agent_rows` trips F811 three times and mypy `no-redef`
   (`_agent_rows.py:407`), and the renamed builder calls itself — 34 × `RecursionError` in
   `test_agent_rows.py`.
2. **Three names §54.7 cannot carry — stops.** A whole-file entry reaches them by
   attribute, where no import alias helps: `llm._record_usage(`
   (`test_streaming_characterization.py:344`), `dmod._start_gen(` (`:402`), and
   `project_manager._with_readme_attribution(` through the façade
   (`test_project_manager_golden.py:168, 169, 172, 173`). Options in §60.3.
3. **Three clashes, not collisions.** `_cost_summary` → `cost_summary` beside
   `spec4._usage.cost_summary`; `_round_cost` → `round_cost` beside `_usage.round_cost`,
   which the same module calls (`layouts/_round_cost.py:243`); `_revision_delta` →
   `revision_delta` beside four per-agent public `revision_delta`s (`deployer.py:397`,
   `stack_advisor/_stack_shape.py:27`, `designer.py:265`, `phaser/_revision.py:36`). None
   shares a scope with the other; all three renamed cleanly in the dry run.
4. **Four old names are also module names** — `_round_tree`, `_status_bar`, `_agent_rows`
   and `_round_cost` are each the function *and* the submodule of that name. A plain
   substitution would rewrite import paths and patch-string components too (loudly:
   `ModuleNotFoundError` the moment `spec4.layouts` imports) — and, silently, eight
   docstring and comment lines that name the module, such as `_round_tree.ROUND_ARTIFACTS`
   (`layouts/_artifact_view.py:16, 139, 166, 358`, `_chat_actions.py:127`,
   `_chat_panels.py:50`, `test_artifact_view.py:973`, `test_chat_open_links.py:173`). The
   forward rename below leaves every module-path occurrence alone — **31** in the dry run.
   And the rename flips what `spec4.layouts._X` means: today the package attribute is the
   function (the re-export shadows the submodule); afterwards it is the submodule, so a
   site the rename missed would get a module and fail when called — loud, and the dry run
   found none. It also retires §59.6 item 12: once the function is `round_cost`,
   `spec4.layouts._round_cost` resolves to the submodule again, so
   `test_cost_summary.py:624`'s `sys.modules` idiom is no longer needed. Its key is a module
   path and the rename leaves it; simplifying the test is a separate commit.
5. **Code outside the gate.** `evals/` holds 7 of the names in 4 files
   (`agentifier/run_mechanism_probe.py`, `agentifier/README.md`,
   `phaser/declaration_alignment.py`, `scout/phantom_link_check.py`) and
   `scripts/e2e_agentifier.py` holds `_default_session`. Nothing runs either, so a rename
   that skipped them would break them **silently**. The substitution covers them: 5
   files, 20 lines in the dry run. **Tracked `.spec4/` files** name 7 of the functions in
   15 files — the dogfood rounds' phase prompts and artifacts. Rule 2 forbids writing
   there; they are skipped and go stale by design.
6. **`app.py` and `AGENT_KEYS`.** Batches 1–3 touch `app.py`: the imports at `:26` and
   `:29–34`, the uses at `:92, 127, 387, 403–413`. The `from spec4.layouts import (…)`
   block is exploded with a trailing comma, so ruff keeps its shape, and the two
   `# noqa: E402, F401` lines D-LR1 keeps (`:74–75`, the callback imports) are not
   touched by any batch. **In the dry run `app.py`
   changed 15 lines, every one a name in place — no line moved, no import reordered
   (D-LR1).** No batch touches `app_constants.py`: `AGENT_KEYS` is never in a diff.
7. **String references: 96**, all literal — 67 `__all__` entries in `src/` (each
   re-exporting module lists its private names), 13 `patch()` targets, 10 `patch.object`
   attributes, 5 `monkeypatch.setattr` attributes, 1 `sys.modules` key (a module path, left
   alone). **Dynamic references: none** — no `getattr`/`hasattr` on these names, no
   `dir()`, `getmembers()`, `vars()` or `globals()`, no `startswith("_")` filter over
   module members, no name built by f-string or concatenation, no star import. **An
   independent hunt** — a separate agent, told what this scan had found and asked only for
   what it would miss — checked 22 further patterns (registries keyed by `__name__`,
   parametrize ids, thread names, autospec lists, entry points, clientside JS, pickling,
   `logging` `funcName`, negative `hasattr` assertions, same-named definitions) and found
   none that applies. Its real findings are folded in above: the module paths and the
   dotted docstring mentions of item 4, the shadow flip, `evals/`, `.spec4/`, and a
   measurement §60.2's check is built around — a reverse substitution applied to the
   candidate alone differs from `HEAD` on **243 lines in 50 files**, because
   underscore-free tokens already exist.
8. **D-number references: 25** (name, line) pairs on 17 names, all in comments or
   docstrings the substitution updates with the code. Three sit in net regions —
   `test_callbacks_stream_poll.py:736` (D-PH9, `TestStreamedTokenCounter`),
   `test_seam_check.py:386` (D-PH9, `TestExtractGraphTransport`), `test_designer.py:797`
   (D-DM7, a `_start_gen` stop) — and are §60.3's to admit. None is in a whole-file entry.
9. **Two text edits that are not code.** A DEV_MODE-only print names a function —
   `agents/brainstormer.py:918`, `"[brainstormer] _format_vision_as_text failed: "` — and
   the substitution changes that console line (not a Rule 4 surface; flagged so the diff is
   no surprise). And `_phase_spec_preamble` is named in the module docstring of a
   whole-file entry that imports nothing by that name (`test_project_manager_golden.py:11`);
   §54.7 forbids the edit, so the mention goes stale.

#### The forward rename

As the proof and the dry run applied it. **The check, not the tool, is the contract** —
Phase 7 may implement this any way it likes, because the check below verifies the result:

1. Word-boundary substitution `old → new` in every tracked text file except
   `CLEANUP_INVENTORY.md`, `.spec4/` (Rule 2), and `tests/golden/`, `tests/snapshots/`
   (frozen data — no name occurs there).
2. Leave module-path occurrences alone: the module part of `from X import`, an
   `import X` line, a `spec4.…` string component followed by `.`, a `sys.modules` key —
   and, for the four names that are also module names, **any** occurrence followed by `.`,
   in code, string or comment.
3. In the seven whole-file entries, rewrite **only** the `from … import` binding, to
   `new as old` (§54.7). Every other line stays.
4. `uv run ruff format src/ tests/`.

#### The rename check, run at every rename commit

For a rename commit `C` with parent `P`, and the batch's `old<TAB>new` list: export both
trees; on **both**, substitute `new → old` at word boundaries in every text file except the
record, fold `X as X` to `X`, and format with magic trailing commas ignored; then diff.
**The diff must be empty.** A non-empty diff means the commit did more than rename.

```bash
# Run from the repo root.  P = parent, C = rename commit (unset: the working tree),
# MAP = file of "old<TAB>new" lines for the batch.
rename_check() {
  local W; W=$(mktemp -d); mkdir "$W/p" "$W/c"
  git archive "$P" | tar -x -C "$W/p"
  if [ -n "${C:-}" ]; then git archive "$C" | tar -x -C "$W/c"
  else git ls-files -co --exclude-standard | tar -cT - | tar -x -C "$W/c"; fi
  for d in "$W/p" "$W/c"; do
    while IFS=$'\t' read -r old new; do          # 1. new -> old, both sides
      grep -rlIZw --exclude=CLEANUP_INVENTORY.md -- "$new" "$d" |
        xargs -0r perl -pi -e "s/(?<![A-Za-z0-9_])\Q$new\E(?![A-Za-z0-9_])/$old/g"
    done < "$MAP"
    find "$d" -name '*.py' -print0 |               # 2. fold §54.7's `x as x`
      xargs -0 perl -pi -e 's/\b([A-Za-z_]\w*) as \1\b/$1/g'
    uv run ruff format -q --no-cache \
      --config 'format.skip-magic-trailing-comma = true' "$d"   # 3. layout-blind
  done
  diff -ru --exclude=CLEANUP_INVENTORY.md "$W/p" "$W/c" && echo "rename check: EMPTY"
  local rc=$?; rm -rf "$W"; return $rc
}
```

Why each normalisation, since each is a place a false result could hide:

- **The substitution runs on `P` too**, so a `new` token that existed before the rename —
  `project_manager.round_cost`, the four `revision_delta`s — cancels instead of showing
  as a diff. Without it, every clash in item 3 is a false stop.
- **The alias fold** undoes §54.7's `new as old` import form. It also matches five lines
  that were there before any rename — `import spec4.llm as llm` and three like it, and one
  docstring's "leave it as it was found" — and folds them identically on both sides, so
  they cancel.
- **The formatter pass.** Dropping an underscore shortens lines, and ruff joins what it had
  split — 8 files in the dry run. Formatting both sides with magic trailing commas ignored
  compares content, not layout.

What it does **not** prove is that the substitution was right — only that the commit *is*
a substitution. Rightness is the gate's job: a module path renamed by mistake reverses
cleanly and fails at import; a collision reverses cleanly and fails in ruff and the suite
(item 1).

#### The proof — `_default_session`, uncommitted, in a scratch clone at `f862f65`

Batch 1's first and largest name: 248 sites, three whole-file entries, two tier-A nodes,
three `app.py` lines.

| Step | What | Result |
|---|---|---|
| 1 | forward rename, the rules above | 35 files, 263 lines; 3 whole-file entries by import alias; `.spec4/v0/phases/phase1-notes.md` left (Rule 2); nothing blocked |
| 2 | `ruff format src/ tests/` | `221 files left unchanged` |
| 3 | rename check | **EMPTY** |
| 4 | negative A — `"search_provider": None` → `"tavily"` smuggled into `session.py` | **not empty**: the diff is that one line |
| 5 | negative B — `>` → `>=` smuggled into an assertion inside a tier-A node the rename touches (`test_round_tree.py:773`) | **not empty**, that one line — and §60.3's checks 1 and 2 **fail** on the file |
| 6 | both reverted | **EMPTY** |
| 7 | the shell function above, same tree | EMPTY; with negative A re-applied, exactly that line |
| 8 | full gate on the renamed tree | ruff ✅ · `221 files already formatted` ✅ · `no issues found in 92 source files` ✅ · `4199 passed, 1 skipped` · `12421 stmts, 891 miss, 93%` — **identical to §60.1** |
| 9 | off-limits | 4,200 collected, **456 / 456**; §54.7 passes on all three whole-file entries (import lines alone, goldens identical, node ids unchanged); §60.3 passes on `test_round_tree.py` (two tier-A nodes) |
| 10 | `app.py` | 3 lines — `:26`, `:92`, `:387` — names in place |

Run unchanged, Phase 6's hunk check **fails** on the proof tree — *whole-file entry
modified*, for the three entries — as it was built to. Phase 7 needs the adapted form
(§60.3): a whole-file entry in the diff must pass §54.7.

#### The same, over every rename that is not a stop — 74 names at once

| | Result |
|---|---|
| forward rename | 102 files, 1,346 lines; **31** import-alias edits in 4 whole-file entries; **31** module-path occurrences left alone; 0 frozen-data hits; nothing blocked |
| `ruff format` | 8 files re-wrapped; 2 of the re-wrapped lines are assertions, neither in a net region |
| rename check | **EMPTY** |
| petitions | §54.7 passes on 4 whole-file entries; §60.3 passes on 17 files (11 tier-B classes, 19 tier-A nodes) |
| gate | ruff ✅ · format ✅ · mypy ✅ · `4199 passed, 1 skipped` · `891 miss` — **identical** |
| `app.py` | 15 lines: one import, six names in the `layouts` import block, eight uses; nothing moved |
| `app_constants.py` | untouched |
| `evals/`, `scripts/` | 5 files, 20 lines |
| each stop, alone | item 1's failures, and §54.7 blocked at item 2's exact lines |

#### The batches

Eleven, one per cluster, in §55.9's sites-per-name order — one commit each; a stop is held
out of its batch rather than holding the batch. *Footprint* is occurrences rewritten.
⛔ = a stop §54.7 cannot carry; ⏸ = waits for the root-siblings decision (§60.5).

| Batch | Cluster | Names | Sites | Footprint tests / src / evals+scripts | Files | Touches `app.py` | `AGENT_KEYS` | Net: whole / tier-B / tier-A | Stops |
|---:|---|---:|---:|---|---:|---|---|---|---|
| 1 | `session` | 5 | 281 | 283 / 31 / 2 | 42 | **yes** — 26, 92, 387 | no | 3 / 0 / 3 | — |
| 2 | `layouts._chat` | 9 | 164 | 180 / 56 / 0 | 26 | **yes** — 33, 409 | no | 1 / 4 / 9 | `_breadth_panel`, `_retry_panel` |
| 3 | `layouts` | 9 | 145 | 197 / 78 / 0 | 35 | **yes** — 29, 30, 31, 32, 34, 127, 403, 405, 407, 413 | no | 2 / 3 / 8 | `_agent_rows` |
| 4 | `layouts.designer` | 7 | 100 | 100 / 23 / 0 | 8 | no | no | 2 / 1 / 1 | — |
| 5 | `agents.code_scanner` | 7 | 82 | 87 / 33 / 0 | 6 | no | no | 1 / 0 / 1 | — |
| 6 | `agents.brainstormer` | 5 | 41 | 46 / 15 / 5 | 8 | no | no | 1 / 0 / 0 | — |
| 7 | `agentifier.agentifier` | 20 | 140 | 173 / 106 / 8 | 22 | no | no | 1 / 0 / 0 | — |
| 8 | `agents._seam_check` | 7 | 39 | 44 / 15 / 6 | 3 | no | no | 0 / 3 / 0 | — |
| 9 | `callbacks.designer` | 4 | 21 | 36 / 29 / 0 | 6 | no | no | 1 / 3 / 1 | `_start_gen` |
| 10 | `llm` | 4 | 16 | 17 / 13 / 0 | 4 | no | no | 1 / 0 / 0 | `_record_usage` |
| 11 | `project_manager` | 3 | 9 | 11 / 24 / 0 | 6 | no | no | 1 / 1 / 0 | `_with_readme_attribution` |

#### Batch 1 — `session` (5 names, 281 sites)

| Owner module | Private → public | Collision | String refs | Net refs (W/B/A) | D-refs | Sites |
|---|---|---|---|---|---:|---:|
| `session.py` | `_default_session` → `default_session` | no | 0 | 6/0/2 | 2 | 248 |
| `session.py` | `_reset_for_new_project` → `reset_for_new_project` | no | 0 | 2/0/0 | 1 | 14 |
| `session.py` | `_run_agent_blocking` → `run_agent_blocking` | no | 0 | 0/0/0 | 0 | 8 |
| `session.py` | `_validate_agent_preconditions` → `validate_agent_preconditions` | no | 0 | 0/0/1 | 2 | 7 |
| `session.py` | `_summarize_turn_usage` → `summarize_turn_usage` | no | 0 | 0/0/0 | 0 | 4 |

*Net references:* `_default_session`: whole-file `test_callback_co_presence.py`, `test_layout_contract.py`, `test_streaming_characterization.py` — by import → `new as old` (§54.7); tier-A `test_round_tree.py::TestItClosesTheProjectView::test_the_tree_is_the_last_of_the_three`, `test_round_tree.py::TestTheCallbackRecomputes::test_it_sees_a_file_written_after_the_last_render` · `_reset_for_new_project`: whole-file `test_callback_co_presence.py` — by import → `new as old` (§54.7) · `_validate_agent_preconditions`: tier-A `test_stale_ai_features.py::test_stale_mock_allows_stack_advisor`

*D-number references:* `_default_session`: agentifier/agentifier.py:2334 (D-TA1); agentifier/agentifier.py:2337 (D-TA1) · `_reset_for_new_project`: session.py:292 (D-PM1) · `_validate_agent_preconditions`: layouts/_chat_actions.py:232 (D-AR1,D-BB1,D-LR2,D-LR8); test_agent_pill_click.py:4 (D-BB1,D-BB2)

*Outside `src/`+`tests/`:* `_default_session`: scripts/e2e_agentifier.py:32,392; `.spec4/` × 1 file (left — Rule 2)

#### Batch 2 — `layouts._chat` (9 names, 164 sites)

| Owner module | Private → public | Collision | String refs | Net refs (W/B/A) | D-refs | Sites |
|---|---|---|---|---|---:|---:|
| `layouts/_chat_actions.py` | `_chat_action_buttons` → `chat_action_buttons` | no | 2 (`__all__` ×2) | 0/0/2 | 2 | 39 |
| `layouts/_chat.py` | `_chat_layout` → `chat_layout` | no | 2 (`__all__` ×2) | 7/0/4 | 0 | 37 |
| `layouts/_chat_panels.py` | `_breadth_panel` → `breadth_panel` | **yes** — `_chat_layout` binds a local `breadth_panel` (`layouts/_chat.py:103`); renamed, that line reads `breadth_panel = breadth_panel(session)` → `UnboundLocalError` | 1 (`__all__` ×1) | 0/0/5 | 0 | 21 |
| `layouts/_chat_actions.py` | `_token_count_text` → `token_count_text` | no | 1 (`__all__` ×1) | 0/3/0 | 0 | 16 |
| `layouts/_chat_panels.py` | `_retry_panel` → `retry_panel` | **yes** — same, `layouts/_chat.py:104` binds a local `retry_panel` | 1 (`__all__` ×1) | 0/1/0 | 0 | 15 |
| `layouts/_chat_panels.py` | `_cost_summary` → `cost_summary` | no — *clash*: `spec4._usage.cost_summary` is public and re-exported by `project_manager` | 1 (`__all__` ×1) | 0/0/0 | 0 | 13 |
| `layouts/_chat_actions.py` | `_turn_token_text` → `turn_token_text` | no | 1 (`__all__` ×1) | 0/0/0 | 0 | 11 |
| `layouts/_chat_actions.py` | `_streamed_token_count` → `streamed_token_count` | no | 1 (`__all__` ×1) | 0/5/0 | 1 | 8 |
| `layouts/_chat_status.py` | `_agent_status_bar` → `agent_status_bar` | no | 2 (`__all__` ×2) | 0/0/1 | 1 | 4 |

*String references (file:line):* `_chat_action_buttons`: layouts/__init__.py:102; layouts/_chat.py:68 · `_chat_layout`: layouts/__init__.py:103; layouts/_chat.py:69 · `_breadth_panel`: layouts/_chat.py:67 · `_token_count_text`: layouts/_chat.py:81 · `_retry_panel`: layouts/_chat.py:79 · `_cost_summary`: layouts/_chat.py:71 · `_turn_token_text`: layouts/_chat.py:83 · `_streamed_token_count`: layouts/_chat.py:80 · `_agent_status_bar`: layouts/__init__.py:101; layouts/_chat.py:66

*Net references:* `_chat_action_buttons`: tier-A `test_agentifier_chars_counter.py::TestLayoutGate::test_first_post_panel_turn_shows_the_counter`, `test_agentifier_chars_counter.py::TestLayoutGate::test_pre_panel_build_shows_the_counter` · `_chat_layout`: whole-file `test_layout_contract.py` — by import → `new as old` (§54.7); tier-A `test_agent_llm_selection.py::TestModelChipPlacement::test_it_shares_a_row_with_the_status_line_and_comes_first`, `test_agent_llm_selection.py::TestModelChipPlacement::test_the_gate_still_suppresses_it`, `test_code_scanner_progress.py::TestLayout::test_elapsed_sits_beside_the_counter_in_the_action_row`, `test_cost_summary.py::TestChatPlacement::test_sits_between_the_transcript_and_the_action_row` · `_breadth_panel`: tier-A `agentifier/test_try_again.py::TestPanelButton::test_hidden_once_the_panel_is_submitted`, `agentifier/test_try_again.py::TestPanelButton::test_panel_offers_the_guidance_box` · `_token_count_text`: tier-B `test_stack_advisor_token_counter.py::TestCounterGate` · `_retry_panel`: tier-B `test_stream_error_recovery.py::TestEmptyTurnBackstop` · `_streamed_token_count`: tier-B `test_callbacks_stream_poll.py::TestStreamedTokenCounter`, `test_stack_advisor_token_counter.py::TestSuppressedStreamPublishesReceipt` · `_agent_status_bar`: tier-A `test_chat_pill_bar.py::TestTheIdsAreUnchanged::test_the_bar_holds_no_control_but_the_pills`

*D-number references:* `_chat_action_buttons`: callbacks/_chat.py:48 (D-LR8); layouts/_chat_status.py:140 (D-LR8) · `_streamed_token_count`: test_callbacks_stream_poll.py:736 (D-PH9) [net] · `_agent_status_bar`: layouts/_shared.py:60 (D-LR2,D-LR9)

*Outside `src/`+`tests/`:* `_chat_action_buttons`: `.spec4/` × 1 file (left — Rule 2) · `_agent_status_bar`: `.spec4/` × 2 files (left — Rule 2)

#### Batch 3 — `layouts` (9 names, 145 sites)

| Owner module | Private → public | Collision | String refs | Net refs (W/B/A) | D-refs | Sites |
|---|---|---|---|---|---:|---:|
| `layouts/__init__.py` | `_agent_select_layout` → `agent_select_layout` | no | 1 (`__all__` ×1) | 7/5/2 | 0 | 41 |
| `layouts/_artifact_view.py` | `_artifact_view_layout` → `artifact_view_layout` | no | 2 (`__all__` ×2) | 4/0/0 | 0 | 26 |
| `layouts/_round_tree.py` | `_round_tree` → `round_tree` | no | 2 (`__all__` ×2) | 0/0/1 | 2 | 23 |
| `layouts/_status_bar.py` | `_status_bar` → `status_bar` | no | 2 (`__all__` ×2) | 3/2/2 | 0 | 20 |
| `layouts/_agent_rows.py` | `_agent_rows` → `agent_rows` | **yes** — `layouts/_agent_rows.py:302` already defines a public `agent_rows` (a different function), re-exported by `layouts/__init__.py:45,88` and imported by `test_agent_rows.py:30` | 2 (`__all__` ×2) | 0/2/1 | 1 | 15 |
| `layouts/__init__.py` | `_working_dir_layout` → `working_dir_layout` | no | 1 (`__all__` ×1) | 4/0/0 | 0 | 7 |
| `layouts/_setup.py` | `_setup_layout` → `setup_layout` | no | 1 (`__all__` ×1) | 7/0/0 | 0 | 6 |
| `layouts/_round_cost.py` | `_round_cost` → `round_cost` | no — *clash*: `spec4._usage.round_cost` is public (re-exported by `project_manager`) and is called from the same module, `layouts/_round_cost.py:243` | 3 (`__all__` ×2, sys.modules key ×1) | 0/0/0 | 0 | 4 |
| `layouts/_status_bar.py` | `_status_context` → `status_context` | no | 2 (`__all__` ×2) | 5/3/2 | 0 | 3 |

*String references (file:line):* `_agent_select_layout`: layouts/__init__.py:106 · `_artifact_view_layout`: layouts/__init__.py:107; layouts/_artifact_view.py:87 · `_round_tree`: layouts/__init__.py:92; layouts/_round_tree.py:63 · `_status_bar`: layouts/__init__.py:98; layouts/_status_bar.py:56 · `_agent_rows`: layouts/__init__.py:86; layouts/_agent_rows.py:54 · `_working_dir_layout`: layouts/__init__.py:105 · `_setup_layout`: layouts/__init__.py:104 · `_round_cost`: layouts/__init__.py:89; layouts/_round_cost.py:64; test_cost_summary.py:624 · `_status_context`: layouts/__init__.py:99; layouts/_status_bar.py:57

*Net references:* `_agent_select_layout`: whole-file `test_callback_co_presence.py`, `test_layout_contract.py` — by import → `new as old` (§54.7); tier-B `test_agent_rows.py::TestItLeadsTheProjectView`; tier-A `test_round_cost.py::TestPlacement::test_it_sits_between_the_rows_and_the_tree`, `test_round_tree.py::TestItClosesTheProjectView::test_the_tree_is_the_last_of_the_three` · `_artifact_view_layout`: whole-file `test_layout_contract.py` — by import → `new as old` (§54.7) · `_round_tree`: tier-A `test_round_tree.py::TestRendering::test_no_line_names_a_colour` · `_status_bar`: whole-file `test_callback_co_presence.py`, `test_layout_contract.py` — by import → `new as old` (§54.7); tier-B `test_status_bar.py::TestOnlyThePathEverGivesUpSpace`; tier-A `test_artifact_view.py::TestTheNavEntry::test_it_is_plain_text_with_no_colour_of_its_own`, `test_status_bar.py::TestStatusBarLayout::test_no_nav_entry_names_a_colour` · `_agent_rows`: tier-B `test_agent_rows.py::TestAMissingUsageEntry`; tier-A `test_agent_rows.py::TestTheButtonRoutesLikeTheOldOnes::test_the_action_carries_the_existing_agent_select_id` · `_working_dir_layout`: whole-file `test_layout_contract.py` — by import → `new as old` (§54.7) · `_setup_layout`: whole-file `test_callback_co_presence.py`, `test_layout_contract.py` — by import → `new as old` (§54.7) · `_status_context`: whole-file `test_callback_co_presence.py`, `test_layout_contract.py` — by import → `new as old` (§54.7); tier-B `test_status_bar.py::TestOnlyThePathEverGivesUpSpace`; tier-A `test_status_bar.py::TestTheBarOpensSetup::test_it_is_dressed_as_the_directory_is`, `test_status_bar.py::TestTheModelSlotCarriesTheEffort::test_the_suffixed_slot_still_refuses_to_truncate`

*D-number references:* `_round_tree`: layouts/_artifact_view.py:16 (D-LR2); layouts/_artifact_view.py:868 (D-LR4) · `_agent_rows`: layouts/_artifact_view.py:139 (D-LR3)

*Outside `src/`+`tests/`:* `_agent_select_layout`: `.spec4/` × 1 file (left — Rule 2) · `_round_tree`: `.spec4/` × 11 files (left — Rule 2) · `_agent_rows`: `.spec4/` × 4 files (left — Rule 2) · `_round_cost`: `.spec4/` × 4 files (left — Rule 2)

*Hazards:* `_round_tree` is also the module `spec4.layouts._round_tree` — module-path occurrences must be left alone · `_status_bar` is also the module `spec4.layouts._status_bar` — module-path occurrences must be left alone · `_agent_rows` is also the module `spec4.layouts._agent_rows` — module-path occurrences must be left alone · `_round_cost` is also the module `spec4.layouts._round_cost` — module-path occurrences must be left alone

#### Batch 4 — `layouts.designer` (7 names, 100 sites)

| Owner module | Private → public | Collision | String refs | Net refs (W/B/A) | D-refs | Sites |
|---|---|---|---|---|---:|---:|
| `layouts/designer.py` | `_step6_content` → `step6_content` | no | 0 | 8/0/1 | 0 | 28 |
| `layouts/designer.py` | `_step7_content` → `step7_content` | no | 0 | 6/1/0 | 0 | 20 |
| `layouts/designer.py` | `_step2_content` → `step2_content` | no | 0 | 10/0/0 | 0 | 14 |
| `layouts/designer.py` | `_step4_content` → `step4_content` | no | 0 | 6/1/0 | 0 | 13 |
| `layouts/designer.py` | `_step5_content` → `step5_content` | no | 0 | 6/0/0 | 0 | 11 |
| `layouts/designer.py` | `_step3_content` → `step3_content` | no | 0 | 4/1/0 | 0 | 8 |
| `layouts/designer.py` | `_step1_content` → `step1_content` | no | 0 | 4/0/0 | 0 | 6 |

*Net references:* `_step6_content`: whole-file `test_callback_co_presence.py`, `test_layout_contract.py` — by import → `new as old` (§54.7); tier-A `test_cost_summary.py::TestDesignerPlacement::test_preview_step_shows_the_strip` · `_step7_content`: whole-file `test_callback_co_presence.py`, `test_layout_contract.py` — by import → `new as old` (§54.7); tier-B `test_designer_wizard_register.py::TestNoBackToTheProjectView` · `_step2_content`: whole-file `test_callback_co_presence.py`, `test_layout_contract.py` — by import → `new as old` (§54.7) · `_step4_content`: whole-file `test_callback_co_presence.py`, `test_layout_contract.py` — by import → `new as old` (§54.7); tier-B `test_designer_wizard_register.py::TestNoBackToTheProjectView` · `_step5_content`: whole-file `test_callback_co_presence.py`, `test_layout_contract.py` — by import → `new as old` (§54.7) · `_step3_content`: whole-file `test_callback_co_presence.py`, `test_layout_contract.py` — by import → `new as old` (§54.7); tier-B `test_designer_wizard_register.py::TestNoBackToTheProjectView` · `_step1_content`: whole-file `test_callback_co_presence.py`, `test_layout_contract.py` — by import → `new as old` (§54.7)

#### Batch 5 — `agents.code_scanner` (7 names, 82 sites)

| Owner module | Private → public | Collision | String refs | Net refs (W/B/A) | D-refs | Sites |
|---|---|---|---|---|---:|---:|
| `agents/code_scanner/_review_render.py` | `_format_review_as_text` → `format_review_as_text` | no | 1 (`__all__` ×1) | 7/0/0 | 0 | 40 |
| `agents/code_scanner/_scan.py` | `_gather_project_context` → `gather_project_context` | no | 1 (`__all__` ×1) | 0/0/0 | 0 | 20 |
| `agents/code_scanner/_scan.py` | `_collect_files` → `collect_files` | no | 3 (`__all__` ×1, patch.object attr ×2) | 0/0/1 | 0 | 7 |
| `agents/code_scanner/__init__.py` | `_extract_review_json` → `extract_review_json` | no | 1 (`__all__` ×1) | 0/0/0 | 0 | 6 |
| `agents/code_scanner/_scan.py` | `_approx_tokens` → `approx_tokens` | no | 1 (`__all__` ×1) | 0/0/0 | 0 | 5 |
| `agents/code_scanner/__init__.py` | `_build_update_scan_seed` → `build_update_scan_seed` | no | 1 (`__all__` ×1) | 0/0/0 | 0 | 2 |
| `agents/code_scanner/__init__.py` | `_build_fresh_scan_seed` → `build_fresh_scan_seed` | no | 1 (`__all__` ×1) | 0/0/0 | 0 | 2 |

*String references (file:line):* `_format_review_as_text`: agents/code_scanner/__init__.py:67 · `_gather_project_context`: agents/code_scanner/__init__.py:68 · `_collect_files`: agents/code_scanner/__init__.py:64; test_code_scanner_progress.py:88,117 · `_extract_review_json`: agents/code_scanner/__init__.py:66 · `_approx_tokens`: agents/code_scanner/__init__.py:61 · `_build_update_scan_seed`: agents/code_scanner/__init__.py:63 · `_build_fresh_scan_seed`: agents/code_scanner/__init__.py:62

*Net references:* `_format_review_as_text`: whole-file `test_renderer_goldens.py` — by import → `new as old` (§54.7) · `_collect_files`: tier-A `test_code_scanner_progress.py::TestScanIsNarrated::test_first_chunk_arrives_before_the_walk`

#### Batch 6 — `agents.brainstormer` (5 names, 41 sites)

| Owner module | Private → public | Collision | String refs | Net refs (W/B/A) | D-refs | Sites |
|---|---|---|---|---|---:|---:|
| `agents/brainstormer.py` | `_format_vision_as_text` → `format_vision_as_text` | no | 1 (patch target ×1) | 5/0/0 | 0 | 11 |
| `agents/brainstormer.py` | `_apply_revision_history` → `apply_revision_history` | no | 0 | 0/0/0 | 0 | 10 |
| `agents/brainstormer.py` | `_feature_names` → `feature_names` | no — `"feature_names"` occurs only as dict-key strings in `evals/scout/run_scout_probe.py:306,382,413` | 0 | 0/0/0 | 0 | 9 (§55: 6) |
| `agents/brainstormer.py` | `_assign_feature_ids` → `assign_feature_ids` | no | 0 | 0/0/0 | 1 | 9 |
| `agents/brainstormer.py` | `_stamp_revision_block` → `stamp_revision_block` | no | 0 | 0/0/0 | 0 | 2 |

*String references (file:line):* `_format_vision_as_text`: test_agents.py:992

*Net references:* `_format_vision_as_text`: whole-file `test_renderer_goldens.py` — by import → `new as old` (§54.7)

*D-number references:* `_assign_feature_ids`: test_feature_ids.py:3 (D-BS2)

*Outside `src/`+`tests/`:* `_feature_names`: evals/scout/phantom_link_check.py:23,38,62,77,84

#### Batch 7 — `agentifier.agentifier` (20 names, 140 sites)

| Owner module | Private → public | Collision | String refs | Net refs (W/B/A) | D-refs | Sites |
|---|---|---|---|---|---:|---:|
| `agentifier/_render.py` | `_build_ai_features` → `build_ai_features` | no | 2 (`__all__` ×2) | 0/0/0 | 3 | 26 |
| `agentifier/_seed.py` | `_build_seed_message` → `build_seed_message` | no | 2 (`__all__` ×2) | 0/0/0 | 0 | 25 |
| `agentifier/agentifier.py` | `_reselection_pool_from_features` → `reselection_pool_from_features` | no | 0 | 0/0/0 | 2 | 10 |
| `agentifier/agentifier.py` | `_extract_cross_cutting_analysis` → `extract_cross_cutting_analysis` | no | 12 (patch target ×12) | 0/0/0 | 0 | 8 |
| `agentifier/_seed.py` | `_candidates_from_dicts` → `candidates_from_dicts` | no | 2 (`__all__` ×2) | 0/0/0 | 1 | 7 |
| `agentifier/_render.py` | `_merge_revision_snapshot` → `merge_revision_snapshot` | no | 2 (`__all__` ×2) | 0/0/0 | 0 | 7 |
| `agentifier/_render.py` | `_revision_delta` → `revision_delta` | no — *clash*: four per-agent public `revision_delta`s already exist (`deployer.py:397`, `stack_advisor/_stack_shape.py:27`, `designer.py:265`, `phaser/_revision.py:36`) | 2 (`__all__` ×2) | 0/0/0 | 0 | 7 |
| `agentifier/_seed.py` | `_candidates_to_dicts` → `candidates_to_dicts` | no | 2 (`__all__` ×2) | 0/0/0 | 1 | 6 |
| `agentifier/agentifier.py` | `_is_spec_confirmed` → `is_spec_confirmed` | no | 0 | 0/0/0 | 0 | 6 |
| `agentifier/_render.py` | `_removed_feature_heads_up` → `removed_feature_heads_up` | no | 2 (`__all__` ×2) | 0/0/0 | 0 | 5 |
| `agentifier/agentifier.py` | `_breadth_candidates` → `breadth_candidates` | no | 0 | 0/0/0 | 0 | 5 |
| `agentifier/_render.py` | `_format_catalog_as_text` → `format_catalog_as_text` | no | 2 (`__all__` ×2) | 5/0/0 | 0 | 5 |
| `agentifier/agentifier.py` | `_existing_workflow_for_entry` → `existing_workflow_for_entry` | no | 0 | 0/0/0 | 0 | 4 |
| `agentifier/agentifier.py` | `_feature_specs_for_session` → `feature_specs_for_session` | no | 0 | 0/0/0 | 0 | 4 |
| `agentifier/_seed.py` | `_analyses_to_dicts` → `analyses_to_dicts` | no | 2 (`__all__` ×2) | 0/0/0 | 0 | 3 |
| `agentifier/agentifier.py` | `_linked_features_for_entry` → `linked_features_for_entry` | no | 0 | 0/0/0 | 0 | 3 |
| `agentifier/_render.py` | `_format_spec_as_text` → `format_spec_as_text` | no | 2 (`__all__` ×2) | 3/0/0 | 0 | 3 |
| `agentifier/_render.py` | `_parse_priority_edits` → `parse_priority_edits` | no | 2 (`__all__` ×2) | 0/0/0 | 0 | 2 |
| `agentifier/_render.py` | `_format_priority_table` → `format_priority_table` | no | 2 (`__all__` ×2) | 0/0/0 | 0 | 2 |
| `agentifier/_seed.py` | `_vision_mvp_feature_names` → `vision_mvp_feature_names` | no | 2 (`__all__` ×2) | 0/0/0 | 0 | 2 |

*String references (file:line):* `_build_ai_features`: agentifier/_render.py:31; agentifier/agentifier.py:148 · `_build_seed_message`: agentifier/_seed.py:58; agentifier/agentifier.py:149 · `_extract_cross_cutting_analysis`: agentifier/test_streaming_e2e.py:357,386,523,572,648,655,683,689,788; integration/test_pipeline_greenfield.py:348,374,403 · `_candidates_from_dicts`: agentifier/_seed.py:64; agentifier/agentifier.py:155 · `_merge_revision_snapshot`: agentifier/_render.py:40; agentifier/agentifier.py:167 · `_revision_delta`: agentifier/_render.py:42; agentifier/agentifier.py:173 · `_candidates_to_dicts`: agentifier/_seed.py:66; agentifier/agentifier.py:157 · `_removed_feature_heads_up`: agentifier/_render.py:41; agentifier/agentifier.py:172 · `_format_catalog_as_text`: agentifier/_render.py:33; agentifier/agentifier.py:160 · `_analyses_to_dicts`: agentifier/_seed.py:56; agentifier/agentifier.py:147 · `_format_spec_as_text`: agentifier/_render.py:38; agentifier/agentifier.py:165 · `_parse_priority_edits`: agentifier/_render.py:39; agentifier/agentifier.py:168 · `_format_priority_table`: agentifier/_render.py:37; agentifier/agentifier.py:164 · `_vision_mvp_feature_names`: agentifier/_seed.py:70; agentifier/agentifier.py:175

*Net references:* `_format_catalog_as_text`: whole-file `test_renderer_goldens.py` — by import → `new as old` (§54.7) · `_format_spec_as_text`: whole-file `test_renderer_goldens.py` — by import → `new as old` (§54.7)

*D-number references:* `_build_ai_features`: agentifier/test_edge_persistence.py:133 (D-EP2); agentifier/test_edge_persistence.py:6 (D-EP1,D-EP2,D-EP3,D-EP4); agentifier/test_vision_grounding.py:204 (D-AC1) · `_reselection_pool_from_features`: agentifier/test_edge_persistence.py:209 (D-EP3); agentifier/test_edge_persistence.py:8 (D-EP1,D-EP2,D-EP3,D-EP4) · `_candidates_from_dicts`: agentifier/test_edge_persistence.py:5 (D-EP1,D-EP2,D-EP3,D-EP4) · `_candidates_to_dicts`: agentifier/test_edge_persistence.py:5 (D-EP1,D-EP2,D-EP3,D-EP4)

*Outside `src/`+`tests/`:* `_build_ai_features`: evals/agentifier/README.md:42; evals/agentifier/run_mechanism_probe.py:13,66,229 · `_candidates_to_dicts`: evals/agentifier/run_mechanism_probe.py:71,232 · `_analyses_to_dicts`: evals/agentifier/run_mechanism_probe.py:72,233

#### Batch 8 — `agents._seam_check` (7 names, 39 sites)

| Owner module | Private → public | Collision | String refs | Net refs (W/B/A) | D-refs | Sites |
|---|---|---|---|---|---:|---:|
| `agents/_seam_check.py` | `_check_declaration_alignment` → `check_declaration_alignment` | no | 0 | 0/14/0 | 0 | 15 |
| `agents/_seam_check.py` | `_check_table_provenance` → `check_table_provenance` | no | 0 | 0/0/0 | 0 | 5 |
| `agents/_seam_check.py` | `_parse_graph` → `parse_graph` | no | 0 | 0/0/0 | 0 | 5 |
| `agents/_seam_check.py` | `_check_feature_coverage` → `check_feature_coverage` | no | 0 | 0/2/0 | 0 | 4 |
| `agents/_seam_check.py` | `_format_advisory` → `format_advisory` | no | 0 | 0/1/0 | 0 | 4 |
| `agents/_seam_check.py` | `_check_endpoint_provenance` → `check_endpoint_provenance` | no | 0 | 0/0/0 | 0 | 3 |
| `agents/_seam_check.py` | `_extract_graph` → `extract_graph` | no | 3 (patch.object attr ×3) | 0/4/0 | 1 | 3 |

*String references (file:line):* `_extract_graph`: test_seam_check.py:148,153,162

*Net references:* `_check_declaration_alignment`: tier-B `test_seam_check.py::TestDeclarationAlignment`, `test_seam_check.py::TestDeclarationAlignmentTwoArraySchema` · `_check_feature_coverage`: tier-B `test_seam_check.py::TestDeclarationAlignment` · `_format_advisory`: tier-B `test_seam_check.py::TestDeclarationAlignment` · `_extract_graph`: tier-B `test_seam_check.py::TestExtractGraphTransport`

*D-number references:* `_extract_graph`: test_seam_check.py:386 (D-PH9) [net]

*Outside `src/`+`tests/`:* `_check_declaration_alignment`: evals/phaser/declaration_alignment.py:65,197 · `_check_feature_coverage`: evals/phaser/declaration_alignment.py:66,197 · `_extract_graph`: evals/phaser/declaration_alignment.py:67,239

#### Batch 9 — `callbacks.designer` (4 names, 21 sites)

| Owner module | Private → public | Collision | String refs | Net refs (W/B/A) | D-refs | Sites |
|---|---|---|---|---|---:|---:|
| `callbacks/designer/_mock_gen.py` | `_extract_html` → `extract_html` | no | 1 (`__all__` ×1) | 0/0/0 | 0 | 8 |
| `callbacks/designer/_mock_gen.py` | `_start_gen` → `start_gen` ⛔ | no | 10 (`__all__` ×1, setattr attr ×4, patch.object attr ×5) | 1/5/1 | 2 | 8 |
| `callbacks/designer/_mock_gen.py` | `_expected_stream_chars` → `expected_stream_chars` | no | 1 (`__all__` ×1) | 0/0/0 | 0 | 4 |
| `callbacks/designer/_mock_gen.py` | `_persist_manifest` → `persist_manifest` | no | 2 (`__all__` ×1, setattr attr ×1) | 0/2/0 | 1 | 1 |

*String references (file:line):* `_extract_html`: callbacks/designer/__init__.py:88 · `_start_gen`: callbacks/designer/__init__.py:90; test_designer.py:820,918,1146,1200,2140,2269,2283,2297,2307 · `_expected_stream_chars`: callbacks/designer/__init__.py:87 · `_persist_manifest`: callbacks/designer/__init__.py:89; test_designer.py:1019

*Net references:* `_start_gen`: whole-file `test_streaming_characterization.py` — **by attribute — §54.7 cannot be met**; tier-B `test_designer.py::TestCapturePassesPlanningContext`, `test_designer.py::TestRefinePersistsManifest`, `test_designer.py::TestRetryReproducesTheDraw`; tier-A `test_designer.py::TestMockDeliveryAck::test_delivery_preserves_prior_store_keys` · `_persist_manifest`: tier-B `test_designer.py::TestRefinePersistsManifest`

*D-number references:* `_start_gen`: callbacks/designer/__init__.py:290 (D-DM8); test_designer.py:797 (D-DM7) [net] · `_persist_manifest`: callbacks/designer/_wizard.py:121 (D-DM7)

#### Batch 10 — `llm` (4 names, 16 sites)

| Owner module | Private → public | Collision | String refs | Net refs (W/B/A) | D-refs | Sites |
|---|---|---|---|---|---:|---:|
| `llm.py` | `_is_effort_rejected_error` → `is_effort_rejected_error` | no | 0 | 0/0/0 | 0 | 5 |
| `llm.py` | `_is_tool_incompatible_error` → `is_tool_incompatible_error` | no | 0 | 0/0/0 | 0 | 5 |
| `llm.py` | `_history_has_tool_use` → `history_has_tool_use` | no | 0 | 0/0/0 | 0 | 4 |
| `llm.py` | `_record_usage` → `record_usage` ⛔ | no | 0 | 1/0/0 | 0 | 2 |

*Net references:* `_record_usage`: whole-file `test_streaming_characterization.py` — **by attribute — §54.7 cannot be met**

#### Batch 11 — `project_manager` (3 names, 9 sites)

| Owner module | Private → public | Collision | String refs | Net refs (W/B/A) | D-refs | Sites |
|---|---|---|---|---|---:|---:|
| `_artifacts.py` | `_write_text_if_changed` → `write_text_if_changed` ⏸ | no | 1 (`__all__` ×1) | 0/0/0 | 0 | 4 |
| `_artifacts.py` | `_with_readme_attribution` → `with_readme_attribution` ⛔ | no | 1 (`__all__` ×1) | 4/0/0 | 0 | 4 |
| `_phase_markdown.py` | `_phase_spec_preamble` → `phase_spec_preamble` ⏸ | no | 1 (`__all__` ×1) | 1/1/0 | 1 | 1 |

*String references (file:line):* `_write_text_if_changed`: project_manager.py:166 · `_with_readme_attribution`: project_manager.py:165 · `_phase_spec_preamble`: project_manager.py:140

*Net references:* `_with_readme_attribution`: whole-file `test_project_manager_golden.py` — **by attribute — §54.7 cannot be met** · `_phase_spec_preamble`: whole-file `test_project_manager_golden.py` — a docstring mention only — no import to re-bind; goes stale; tier-B `test_project_manager.py::TestPreambleTwoAltitudesAndSurfaces`

*D-number references:* `_phase_spec_preamble`: agents/_seam_check.py:341 (D-PH2)

### 60.3 Net-file impact and the rename petition

#### What the rename half cannot avoid editing

Summed from §60.2's net columns, and checked by the dry run's petition pass.

| | All 80 names | Without the six stops (74) |
|---|---:|---:|
| Names that reach the net | 39 | 33 |
| Whole-file entries (of 7) | **5** — 116 occurrences | **4** — import lines only: 31 alias edits |
| Tier-B classes (of 33) | **15** in 9 files — 53 occurrences | **11** in 8 files |
| Tier-A / ordering nodes (of 85) | **23** in 13 files | **19** (one inside a touched tier-B class) |
| Floor files touched (of 53) | 24 | 21 |

The whole-file entries, one by one:

| Entry | Names | How it reaches them | Under §54.7 |
|---|---:|---|---|
| `test_layout_contract.py` | 15 | `from spec4.… import _x`, bare uses | import alias — passes |
| `test_callback_co_presence.py` | 13 | same | import alias — passes |
| `test_renderer_goldens.py` | 4 | same (`_format_{catalog,spec,review,vision}_as_text`) | import alias — passes (§54.7 as already defined) |
| `test_streaming_characterization.py` | 3 | `_default_session` by import; `llm._record_usage(` `:344` and `dmod._start_gen(` `:402` **by attribute** | alias for the first; **cannot be met** for the other two |
| `test_project_manager_golden.py` | 2 | `project_manager._with_readme_attribution(` `:168–173` **by attribute**; `_phase_spec_preamble` only in the module docstring (`:11`) | **cannot be met** for the first; the docstring goes stale |
| `test_app_import_smoke.py`, `test_import_layering.py` | 0 | — | untouched |

#### The rename petition

In §54.7's shape, three mechanical checks, for the net entries the plan's §54.7 rule does
not already govern:

> **Rename petition — Phase 7 may edit a §50.3 tier-B class or tier-A / ordering node for
> a rename on the §60.2 list if and only if all three hold, file by file:**
>
> 1. **The diff inside the net file is identifier substitution alone.** §60.2's rename
>    check, restricted to that file, is empty.
> 2. **Every assertion is identical under the substitution.** Every `assert` statement and
>    every call to an `assert*` method in the file, with the batch's `new → old`
>    substitution applied, is token-for-token the one at the parent commit, in the same
>    order.
> 3. **The off-limits check passes for every other entry.** 456 / 456 node ids collect;
>    every whole-file entry in the diff passes §54.7; and no whole-file entry, tier-B class
>    or tier-A node that holds none of the batch's old names at the parent commit has a
>    hunk.
>
> Any one of the three failing means it is not this petition — stop and ask.

**Whole-file entries are outside this petition.** They stay under §54.7 as written — the
plan's Phase 7 rule — `tests/test_renderer_goldens.py` included, not redefined. A rename
meets §54.7 by re-binding the import (`from m import new as _old`), so no line but the
import changes.

**Why tokens rather than bytes in check 2.** The directive's word is "byte-identical".
Shortening a name lets ruff re-join a line it had wrapped, so a byte comparison would stop
a rename whose assertion changed only in layout. In the dry run no assertion inside a net
region was re-wrapped, so bytes would have passed too — but two assertions outside the
net were (`test_vision_grounding.py`, `test_chat_pill_bar.py`), and the next batch's may
not be outside. Tokens compare what an assertion *says*.

**It has been run, both ways.** On the proof it passes, and it fails — checks 1 and 2 —
on the smuggled `>=` (§60.2, step 5). On the 74-name dry run it passes on all 17 files it
applies to, with §54.7 passing on the four whole-file entries.

**The off-limits check needs one adaptation for Phase 7.** Phase 6's hunk half stops on
*any* whole-file entry in the diff. Phase 7's reads: a whole-file entry in the diff must
pass §54.7; a tier-B class or tier-A node with a hunk must pass this petition; and a hunk
in any net entry that holds none of the batch's old names is a stop, as before.

#### The three names §54.7 cannot carry — options, not a decision

`_start_gen`, `_record_usage` and `_with_readme_attribution` are reached by attribute from
Phase 1 files. Three ways through, each with its cost:

| Option | What changes | Cost |
|---|---|---|
| **Leave them private** | nothing; they stay on §55's list as *promote, blocked by the net* | the tests keep their private reach; no petition |
| **Petition by node id** (§50.5(a)) | `llm._record_usage(` → `llm.record_usage(` at `test_streaming_characterization.py:344`; `dmod._start_gen(` → `dmod.start_gen(` at `:402`; four `project_manager._with_readme_attribution(` lines in `test_project_manager_golden.py` | six assertion-bearing or setup lines in two Phase 1 files — outside both petitions' shape, so a ruling per node |
| **Keep a private alias in `src/`** (`_start_gen = start_gen`) | one line per name in the owner | reintroduces the compatibility aliasing Phase 4j retired, for the net's sake |

### 60.4 The seam half — one proposal per seam, no decisions

The thirteen `design seam` names of §55.9 and the `_usage.py` production seam of §52.5.
**§60.4 proposes; Phase 7 decides.** Each row gives the current caller and its size, the
public seam the code would support, what it would stop depending on, the test sites that
would move, and the one mutation check the Phase 7 commit would run (§51.6). Sizes are
`ast.stmt` counts with the `def` included — the convention that reproduces §55.3's 45 for
`brainstormer.run` and 15 for `agentifier.run` — and physical lines from `def` to the end.
The mutation outcomes were derived by reading code and tests; **none was run here**.

**Two of the thirteen are not what §55.9's rule made them.**

- **`_load_working_dir` does not mutate its argument.** Line 239 rebinds the local
  `session` to the fresh dict `_reset_for_new_project` returns, and every later write
  lands on that dict — §55.9's syntactic rule matched those writes on the rebound name.
  Run here: after the call the input equals its deep copy, and the result is a new dict.
  It is a function of its inputs, which is the rename half's rule.
- **`_stream_suppressing_json` is a private alias** of a generator already public at its
  owner, whose yield protocol four callers already rely on. Promoting it is dropping the
  alias.

On this reading the design-seam half is **eleven** seams and the rename half could take
two more names. Phase 7 decides both.

**The session mutators and the brainstormer seam share one shape.** For each, the honest
proposal is *promote as-is*, with a documented contract naming exactly the session keys it
may write — no `TypedDict` (the plan forbids it), no key renamed (Rule 4) — pinned by a new
key-set test, which is also its mutation check. None would stop depending on anything in
production; the tests stop depending on the private name. The alternative each could
take — returning a delta instead of writing — is recorded in its row with its cost.

| Seam | Owner — statements / lines | Caller(s) — statements / lines | Proposal | Sites that move | Mutation check |
|---|---|---|---|---|---|
| `_persist_artifacts` | `session.py:519` — 15 / 37 | `_poll_finalise` (`callbacks/_chat.py:576`, 13 / 31) — sole | promote as-is; five-key contract | 35 direct; 8 `_chat` patch strings stay | append `session["project_mode"] = None` → a new key-set test fails |
| `_get_agent_gen` | `session.py:363` — 29 / 81 | six turn-starters in `callbacks/_chat.py` (8–25 st) and `_run_agent_blocking` (tests only) — no sole caller | promote as-is; one eager write, session identity | 20 direct; 14 `_chat` patch strings stay | pass `dict(session)` to `brainstormer.run` (`:427`) → a new identity test fails |
| `_load_working_dir` | `session.py:225` — 12 / 75 | `_resolve_root` (10 / 31), `on_browser_navigate` (11 / 26), `on_dir_select` (12 / 19) — no sole caller | promote as-is: returns a new dict, never mutates — **rename half** | 24 direct | load in place at `:239` → a new non-mutation test fails |
| `_rehydrate_vision_from_disk` | `agents/brainstormer.py:634` — 13 / 27 | `brainstormer.run` (`:663`, 45 / 101) — sole | promote as-is; three-key contract | 4 | `session["feature_specs"] = None` before `:651`'s return → a whole-dict test fails |
| `_stream_suppressing_json` | `agents/_reask.py:169`, public — 33 / 85 | `_run_catalog_phase` (via the alias) and `run` in `stack_advisor`, `brainstormer`, `code_scanner` | drop the alias — a rename | none; 2 lines re-pointed, patch-shaped | `seed=pre_stream_chars` → `seed=0` (`agentifier.py:2062`) → 5 tests fail |
| `_run_catalog_phase` | `agentifier.py:1624` — 178 / 486 | `run` (`:2525`), `_handle_reentry` (`:2454`) | (a), or the main case for (b) | 5; 2 `patch.object` stay | `:1727` → `if False:` → 1 test fails |
| `_run_spec_phase` | `:1056` — 36 / 66 | `run` — sole | (a); already (b)-shaped | 16 | the FF branch moved past the review check (D-AF1) → 2 fail |
| `_run_cross_cutting_phase` | `:1255` — 73 / 130 | `run` — sole | (a) or (b) | 8 | `:1335` → `if False:` → 3 fail |
| `_run_priority_phase` | `:1475` — 47 / 82 | `run` — sole | (a) | 2 | confirmation read before edits (`:1504`) → 1 fails |
| `_handle_reentry` | `:2410` — 37 / 93 | `run` — sole | (a); a transition | 3 | the reset moved below the delegation → 1 fails |
| `_finalize_specs` | `:691` — 51 / 105 | three functions in `agentifier.py` | (a); a transition | 3; 1 `patch()` stays | preserved features appended, not prepended (`:715`) → 1 fails |
| `_begin_priority_phase` | `:1387` — 34 / 81 | three functions, four sites | (a); a transition | 2; 1 `patch()` stays | an empty overlay at `:1441` → 3 fail |
| `_complete_agentifier` | `:841` — 33 / 86 | three functions, five sites | (a), or a plain `-> str` | 6 | `:902` dropped from the pop tuple → 1 fails |
| `_usage._write_atomic` — §52.5's production seam | `_usage.py:345` — 12 / 19 | `save_usage` (`:438`, 30 / 73) — sole | module-level `_replace`, `_fdopen`; `module_seam` deleted | none; 2 patches re-pointed | `:359` back to `os.replace(…)` → the new test fails `DID NOT RAISE`, the old form passes |

#### The session mutators

**`_persist_artifacts`** (`session.py:519`; 15 statements, 37 lines; not a generator). Its
sole production caller is `_poll_finalise` (`callbacks/_chat.py:576`; 13 statements, 31
lines), which reaches it through `_chat`'s import binding once per turn, behind
`streaming.claim_finalise`. In place it may write five keys — `phase_version` (only when
`None`), `_turn_usage`, `_deployer_plan_existed`, `_deployer_plan_markdown`,
`_deployer_readme_markdown` — and it drains the process-global usage sink and writes
`.spec4/` files. **Proposal:** promote as-is, `persist_artifacts(session: dict[str, Any]) ->
None`, with that key set as the documented contract (the name under-describes the usage
flush — Phase 7's call). It would stop depending on nothing. Taking `usage_records` as a
parameter would remove the sink dependency but changes behaviour: with no `working_dir`
the records would be drained and discarded instead of left for the next turn. **Sites:**
all 35 direct ones move (6 imports, 29 calls); the 8
`spec4.callbacks._chat._persist_artifacts` patch strings stay patch-shaped, re-pointed —
they isolate the poll, not the seam. **Mutation:** append `session["project_mode"] = None`,
a write outside the contract that would wipe D-PM1's session-only answer every turn. A new
key-set test beside `TestPersistArtifacts` fails; the 29 direct calls pass.

**`_get_agent_gen`** (`session.py:363`; 29 statements, 81 lines). It contains no `yield`:
it runs at call time and returns the agent's `run()` generator. Seven production callers,
so no sole caller — six turn-starters in `callbacks/_chat.py` (`on_init_turn`,
`on_chat_submit`, `on_fast_forward`, `_start_retry_turn`, `on_breadth_submit`,
`on_breadth_try_again`; 8–25 statements) and `_run_agent_blocking` (`session.py:466`),
which only tests reach. Its one eager write is `_stream_status` (`:404`), after the model
check and before the unknown-agent `ValueError` (`:439`); the returned generator mutates
the same dict later. **Proposal:** promote as-is, `get_agent_gen(user_input: str | None,
session: dict[str, Any]) -> Generator[str, None, None]`, documenting that write and the
session identity. It would stop depending on nothing; returning the seed instead of
writing it would push the write into seven call sites. One wrinkle for Phase 7: the
`ValueError` fires after the seed is written. **Sites:** all 20 direct ones move; the 14
`_chat` patch strings stay — the mock is their assertion. **Mutation:** pass `dict(session)`
to `brainstormer.run` (`:427`), so the agent mutates a copy and every Brainstormer write is
lost at finalise. A new identity test — `run.call_args[0][1] is session`, over the six
dispatch arms — fails. **No test pins that identity today:** the seed and dispatch tests
all pass under the mutation.

**`_load_working_dir`** (`session.py:225`; 12 statements, 75 lines). Three callers in
`callbacks/__init__.py`, so no sole caller: `_resolve_root` (`:325`; 10, 31),
`on_browser_navigate` (`:365`; 11, 26), `on_dir_select` (`:436`; 12, 19). **It does not
mutate its argument** (above): it reads only the ten `_PRESERVED_SETUP_KEYS` and returns a
new dict. The non-mutation is load-bearing — `on_browser_navigate`'s `_no_change` compares
the result with the input (`callbacks/__init__.py:393–395`). **Proposal:** promote as-is,
`load_working_dir(path: str, session: dict[str, Any]) -> dict[str, Any]`, documented as
returning a new dict and never mutating its input; a `Mapping[str, Any]` parameter would
make that mypy-checked. It would stop depending on nothing — it already depends only on the
ten keys — and on this reading it belongs in the rename half. **Sites:** all 24 move (4
imports, 20 calls), no patch strings; one sits in a tier-A node
(`test_session.py::TestLoadWorkingDir::test_picking_a_directory_reopens_the_question`,
D-PM1) — §60.3 for a rename, §50.5(a) for anything more. **Mutation:** load in place at
`:239` (`session.clear(); session.update(fresh)`). A new non-mutation test fails, as would
a `/setup` deep-link router test through `_no_change`; the existing tests pass.

#### The brainstormer seam

**`_rehydrate_vision_from_disk`** (`agents/brainstormer.py:634`; 13 statements, 27 lines;
not a generator). Sole caller `brainstormer.run` (`:678`; `run` is 45 statements, 101
lines, carries a C901/PLR0912 `noqa` and is on §27.4's backlog), itself reached through
`session._get_agent_gen`. With a truthy `working_dir` it writes exactly
`vision_statement`, `brainstormer_state` and `feature_specs`, all three on every call; with
none it writes nothing and reads no disk. No disk write, LLM call, sink or registry.
**Proposal:** promote as-is, `rehydrate_vision_from_disk(session: dict[str, Any]) -> None`,
with that three-key contract. It is not tied to the `yield from` decision: it is not a
generator, and `run` changes only by the renamed call. The alternative — a pure reader
returning `(vision, state, specs)`, with the guard and the writes moved into `run` — would
add a branch and three statements to a `noqa`'d function; recorded, not proposed.
**Sites:** all four move (`test_vision_disk_reconciliation.py:90, 103, 114, 124`); no patch
strings. **Mutation:** insert `session["feature_specs"] = None` before the early `return` at
`:651`, breaking "no working dir leaves the session as it is". Today's `:108` test passes —
it checks two keys, and its fixture's `feature_specs` is already `None`; a whole-dict
assertion with seeded specs fails. **Recorded, not acted on:** the vision resolves through
`active_version`, which prefers `session["phase_version"]`, and `feature_specs` through
`latest_phase_version`, which ignores it; with `phase_version` pinned below the newest
round, the two come from different rounds. Whether that state is reachable was not
checked, so it is not logged as a bug.

#### The alias

**`_stream_suppressing_json`** → `stream_suppressing_json` (`agents/_reask.py:169`; 33
statements, 85 lines; 3 `yield`). Already public at its owner, with four production
callers, each by `yield from`: agentifier's `_run_catalog_phase` (`:2052`, through the
alias; 178 statements, 486 lines) and `run` in `stack_advisor` (`:113`), `brainstormer`
(`:728`) and `code_scanner` (`:271`). Its yield protocol is committed already — a
shared-helper seam, not a ninth agentifier phase runner. **Proposal:** nothing to design:
document the contract it already keeps (it writes only `_stream_received_chars` and
`_stream_status`, and always exhausts `chunks`) and drop the alias — `agentifier.py:89`
imports the public name and `:2052` calls it. That is a rename §60.2's check verifies, and
it could ride with batch 7. **Sites:** none move; `test_chars_counter_seed.py:150, 156`
stay patch-shaped, re-pointed — they spy the `seed` `_run_catalog_phase` passes, which is
visible only where agentifier looks the name up. The site is inside the tier-A node
`TestBreadthTurnSeedsTheCounter::test_counter_does_not_dip_below_the_progress_text`
(D-AT3), so §60.3 applies. **Mutation:** `seed=pre_stream_chars` → `seed=0` at
`agentifier.py:2062`, breaking D-AT3; `:159` fails, and so do `:107`, `:114`, `:143` and
`:217`.

#### The eight agentifier generators — one proposal, written against the sub-generator backlog

**The protocol today.** All eight are `Generator[str, None, None]`, as are
`agentifier.run` (`:2505`; 15 statements) and the backlog's three turns — `deployer.run`,
`brainstormer.run`, `code_scanner.run` — which share its `(user_input, session,
llm_config)` signature. They yield display text only: progress banners, error strings,
streamed deltas (through `stream_suppressing_json`), the final display block. No sentinel,
nothing sent in, every `return` bare; `streaming.start` concatenates the chunks and ignores
the return value (`streaming.py:259–262`). **Nothing flows back to `run`:** state travels
only through the live session — the done-flags `run` routes on (`:2524–2533`),
`agentifier_messages`, `_display_override` (applied by the poll, `callbacks/_chat.py:596–599`),
`_stream_status`, `_stream_received_chars`. And the phases chain *past* `run` inside one
turn: spec → `_finalize_specs` → `_begin_priority_phase` → `_complete_agentifier`, each by
`yield from`.

**One decision, two shapes it could take.**

- **(a) Promote as-is.** Signatures and `Generator[str, None, None]` stay; each function
  documents the session keys it may write; the tests re-point by identifier substitution,
  with §60.3 covering the tier-A sites. No `src/` dependency changes — and the backlog
  stays open.
- **(b) The backlog split.** Step sub-generators typed `Generator[str, None, int]`,
  returning the turn's received-character total, driven as `total = yield from step(...)`.
  The shape is already in the repo: `_reask.stream_counting` (`:305–335`), consumed by
  `deployer.run` at `:664` — the only value-returning `yield from` in any turn today. Under
  (b), `_run_catalog_phase` stops hand-threading its `pre_stream_chars` local (17 lines)
  through four `_session_counter` sites, and the rule-12 `noqa`s at `:1255` and `:1624` are
  re-measured.

**What (b) shares with the backlog's three turns:** the entry guards (`user_input is None`
→ `replay_last_assistant`), the three sub-generators every turn is built from (replay;
`stream_suppressing_json` / `stream_counting` over `llm.stream_turn`;
`reask_for_artifact`), and the session side-channels. That is why §55.9 calls it one
decision: a contract published now under (a) is the contract (b) would then have to
change. Session keys stay byte-identical either way (Rule 4); no `TypedDict`.

**Four of the eight are not phase runners.** `_run_catalog_phase`, `_run_spec_phase`,
`_run_cross_cutting_phase` and `_run_priority_phase` are the phases `run` dispatches to.
`_handle_reentry` is the re-entry transition; `_finalize_specs` (spec → cross-cutting) and
`_begin_priority_phase` (cross-cutting → priority) are transitions; `_complete_agentifier`
is the terminal completion step. All callers are inside `agentifier.py`; a promotion would
also extend its `__all__` (`:145`), whose comment today lists "the three names the
orchestrator itself publishes". And §55.9's "five of which already carry rule-12
complexity `noqa`s" is **two**: `_run_catalog_phase` (`:1624`) and
`_run_cross_cutting_phase` (`:1255`). Five is the size of §27.4's backlog entry — those
two plus `deployer.run`, `brainstormer.run` and `code_scanner.run`.

**`_run_catalog_phase`** (`agentifier.py:1624`; 178 statements, 486 lines; 17 `yield`, 7
`yield from`; §27.4 entry nine). Two callers: `run` (`:2525`) and `_handle_reentry`
(`:2454`, the stale rediscovery). **Seam:** `run_catalog_phase(user_input, session,
llm_config) -> Generator[str, None, None]` under (a). It is the main case for (b): six
blocks would become steps returning the character total — Scout (`:1686–1716`), the
zero-candidate completion (`:1717–1798`), Linker (`:1805–1867`), Composer (`:1872–1916`),
the breadth-selection turn (`:1934–2044`), the tier-review stream (`:2049–2109`). Its
`agentifier_messages` seeds are LLM prompt text and stay frozen (Rule 4). **Sites:** the 5
in `test_revision.py` move; `test_reselection.py:136, 178` (`patch.object`) stay
patch-shaped, re-pointed — they isolate `_handle_reentry`'s stale branch from the real
phase. **Mutation:** `:1727` `if session.get("agentifier_revision"):` → `if False:`;
`test_zero_new_candidates_finalises_carried_forward` fails,
`test_non_revision_zero_completes_empty` passes.

**`_run_spec_phase`** (`:1056`; 36 statements, 66 lines; 1 `yield`, 5 `yield from`; no
`noqa`). Sole caller `run` (`:2527`). Already split into sub-generators
(`_ff_sweep_specs`, `_handle_spec_ff_review`, `_draft_and_show_spec`, `_finalize_specs`) —
the repo's working example of (b), minus a return value. **Seam:**
`run_spec_phase(user_input, session, llm_config) -> Generator[str, None, None]`.
**Sites:** all 16 in `test_ff_sweep.py` move (the import and 15 calls); six sit in five
tier-A nodes of `TestSweepFailureHandling` (D-AF5, D-AF6, D-AF7) — §60.3 under (a),
§50.5(a) if a call changes shape. **Mutation:** move the FF branch (`:1086–1088`) into the
not-pending `else` arm, so FF is honoured only after the review check — breaking D-AF1;
`test_ff_while_pending_sweeps_instead_of_revising` and `test_ff_press_resumes_after_pause`
fail, the other six FF tests pass.

**`_run_cross_cutting_phase`** (`:1255`; 73 statements, 130 lines; 7 `yield`, 5 `yield
from`; §27.4 entry ten). Sole caller `run` (`:2529`). **Seam:** `run_cross_cutting_phase(…)`
under (a). Under (b), the analyst-rerun block (`:1279–1320`) and the topic-revision block
(`:1358–1380`) become steps beside `_handle_cc_ff_review` — and the rerun block is the same
step as `_finalize_specs:755–790` except for its UI strings, which a shared step would take
as parameters. **Sites:** all 8 in `test_ff_sweep.py` move. **Mutation:** `:1335` `if
session.get("agentifier_cross_cutting_ff_review"):` → `if False:`;
`test_review_confirm_begins_priority`, `test_review_revision_reruns_named_topic` and
`test_review_locked_topic_rejected` fail, the three FF-sweep tests pass.

**`_run_priority_phase`** (`:1475`; 47 statements, 82 lines; 2 `yield`, 2 `yield from`; no
`noqa`). Sole caller `run` (`:2531`). Deterministic — no LLM call, network or disk. Its
`_llm_config` is unused, kept only for `run`'s uniform three-argument dispatch, which a
documented phase-runner signature would record. **Seam:** `run_priority_phase(user_input,
session, _llm_config) -> Generator[str, None, None]`. **Sites:** both in
`test_prioritizer.py` move (one helper serving ten tests). **Mutation:** at `:1504`, read
confirmation before edits (`if not edits.saw_pair or _is_spec_confirmed(user_input):`) — the
defect the comment at `:1501–1503` names; `test_edit_wins_over_affirmative_prefix_collision`
fails, the other nine pass.

**`_handle_reentry`** (`:2410`; 37 statements, 93 lines; 1 `yield`, 2 `yield from`) — the
re-entry transition `run` (`:2533`, the sole caller) takes once all four done-flags are
set. It demotes `agentifier_state`, then either resets and delegates to
`_run_catalog_phase(None, …)` (stale inputs) or arms the reselection panel; its
`_user_input` is unused (§27.5e). **Seam:** `handle_reentry(…)` as-is; if
`_run_catalog_phase` is promoted, the module-global lookup at `:2454` and the two
`patch.object` strings follow it. **Sites:** all 3 in `test_reselection.py` move.
**Mutation:** move `:2446–2447` (the reset and the acknowledgement write) below the `yield
from` at `:2454`; `test_stale_reentry_clears_candidate_pool` fails,
`test_vision_newer_resets_and_rediscovers` passes.

**`_finalize_specs`** (`:691`; 51 statements, 105 lines; 4 `yield`, 1 `yield from`) — the
spec → cross-cutting transition: it stores the six-key `ai_features` (a frozen shape, Rule
4), sets `agentifier_spec_done`, runs the Cross-Cutting Analyst and yields the first topic,
or chains to `_begin_priority_phase`. Three callers: `_run_spec_phase` (`:1108`),
`_handle_spec_ff_review` (`:1202`), `_run_catalog_phase` (`:1977`). **Seam:**
`finalize_specs(session, llm_config)` as-is; under (b) its analyst block (`:755–795`) shares
a step with the cross-cutting rerun. **Sites:** the 3 direct ones move
(`test_reselection.py:219`, `test_search_level.py:529, 557`); `test_ff_sweep.py:158`'s
`patch()` stays, re-pointed. **Mutation:** `:715` `list(preserved) + features` →
`features + list(preserved)`; `test_preserved_prepended_and_flags_cleared` fails.

**`_begin_priority_phase`** (`:1387`; 34 statements, 81 lines; 2 `yield`, 1 `yield from`) —
the cross-cutting → priority transition: one Prioritizer draw, the overlay and
normalisation, the table — or `_complete_agentifier` when there are no features. Callers:
`_finalize_specs` (`:752`), `_handle_cc_ff_review` (`:972`), `_run_cross_cutting_phase`
(`:1291`, `:1350`). **Seam:** `begin_priority_phase(session, llm_config)` as-is. **Sites:**
both in `test_prioritizer.py` move (one helper, seven tests); `test_ff_sweep.py:301`'s
`patch()` stays, re-pointed; `conftest.py:52` patches the collaborator `_call_prioritizer`
and is unaffected. **Mutation:** pass `{}` as the overlay at `:1441`; the three overlay
tests fail, the four banner and short-circuit tests pass.

**`_complete_agentifier`** (`:841`; 33 statements, 86 lines; 1 `yield`, no `yield from`) —
the terminal completion step and the single finalisation locus. It mutates `ai_features`
in place and re-stores it, writes `agentifier_state`, `agentifier_stale_acknowledged`,
`agentifier_priority_done`, `_display_override` and `agentifier_artifact_msg_count`, appends
to `agentifier_messages`, and pops the six `agentifier_revision*` /
`agentifier_carried_forward` keys. Five call sites: `_begin_priority_phase` (`:1403`),
`_run_priority_phase` (`:1506`), `_run_catalog_phase` (`:1765`, `:1787`, `:1959`).
**Seam:** `complete_agentifier(session, display=None)` as-is — or, the one case where the
generator protocol is incidental (it yields once and never delegates), a plain `-> str` with
callers writing `yield complete_agentifier(…)`: a contract change, Phase 7's to take.
**Sites:** all 6 move (`test_revision.py:206, 217, 224, 230, 248`; `test_try_again.py:534`).
**Mutation:** drop `"agentifier_revision_delta",` from the pop tuple (`:902`);
`test_revision_state_cleared` fails, `test_carried_forward_merged_and_stamped` passes.

#### The `_usage.py` production seam (§52.5)

**`_usage._write_atomic`** (`_usage.py:345`; 12 statements, 19 lines) has one caller,
`save_usage` (`:438`; 30 statements, 73 lines, under `_USAGE_LOCK`), and is not
re-exported. It makes four `os` calls — `fdopen` (`:355`), `fsync` (`:358`), `replace`
(`:359`), `unlink` (`:362`) — and no other module in `src/spec4` writes atomically.
**Seam:** `_write_atomic` stays private and unchanged; two module-level aliases,
`_replace = os.replace` and `_fdopen = os.fdopen`, are called at `:359` and `:355`. Both
are needed, as §52.5's candidate text says (its code example shows only `_replace`):
`test_partial_content_write_never_reaches_the_file` fails `fdopen` mid-write, and nothing
else could inject that without patching a stdlib attribute. The underscores stay — they
are module-private test seams, and a bare `replace` on `spec4._usage` would read as API.
**What the tests stop depending on:** `spec4._usage` binding `os` as a module name, and
`module_seam` / `_ModuleSeam` — `tests/conftest.py:57–114` goes, with `import importlib`
(`:25`) and `Callable` (`:28`), which only that code used. No other test uses the fixture.
**Sites:** none move to a direct call — failing a stdlib call is patch-shaped by nature;
`test_usage_capture.py:854` becomes `patch("spec4._usage._replace",
side_effect=OSError("boom"))` and `:878` `patch("spec4._usage._fdopen",
side_effect=_broken_fdopen)`. **Mutation:** revert `:359` to `os.replace(tmp_name, path)`,
bypassing the alias — the new test fails `DID NOT RAISE` while the old `module_seam` form
passes; and on the unmutated new code the old form fails, so the test form pins the binding.
The companion for the second alias is `:355` back to `os.fdopen(`. The `src/` and test
edits must land in one commit. Strict mypy is clean on a scratch copy with the aliases;
coverage gains two statements, both executed at import.

**§52.5's audit clause, answered: one unrecorded case, and two of a neighbouring kind.**
`tests/test_root_routing.py:384` — `monkeypatch.setattr(pathlib.Path, "is_dir", boom)` —
makes `project_manager.directory_opens` (`project_manager.py:364`) fail on demand by
replacing `Path.is_dir` **for the whole process** while the test runs: §52.1's hazard
class, and not in the record. It is a method call, so a module-level alias does not fit;
the in-repo precedent is `layouts/_artifact_view.py`'s function-wrapper seams (`_resolve`
`:251`, `_stat` `:263`), which tests patch by name. And `test_designer.py:967` and `:1012`
set `Thread` on the stdlib `threading` module through `spec4.callbacks.designer` and
`._mock_gen` — process-global as well, though they suppress or inline the worker thread
rather than fail a call. §52.5's grep checked only the `patch("…")` string form, which is
why it saw none of the three. Sized here, not scheduled: one candidate seam
(`directory_opens`) and two sites to classify. In passing, `_usage.py:3–5`'s docstring
still says `project_manager` "re-exports every name defined here"; since 4j it re-exports
9 of them.

### 60.5 Sizing the deferrals

#### Type hygiene — the 290

**What the 290 lines hold.** 454 annotated targets — a Dash callback declares every
parameter on one line — of which **440 are bare `Any`**; the other 14 are
`dict[str, Any]`-shaped parameters sharing a line with one. By kind: 416 parameters, 22
variables, 14 `**kwargs`, 2 `*args`. **233 of the 454 are Dash callback parameters.** The
commonest names: `session` 80, `n` 53, `value` 37, `store` 22, `prefs` 11,
`image_support` 10, `working_dir` 8.

**How they were classified — by reading, re-checked adversarially, cross-checked by rule.**
One agent per area (`agents/` + `agentifier/`, top-level `callbacks/`, `callbacks/designer/`
+ `layouts/`, root modules) classified every line after reading the function and its
producers: its callers and, for a callback, the `Input`/`State` prop bound to each
parameter. A second agent per area was told to refute every "genuinely typeable" type
against those producers — Dash passes `None` before the first interaction;
pattern-matching inputs arrive as lists — and every "load-bearing" reason, and returned the
corrected set. Each area's rows match its grep lines one for one: **290 of 290, none
missing, none extra.** The verifiers changed **10** rows. Four changed class —
`stack_advisor/_render.py:64` (JSON edge → typeable, `str`), `app.py:391` (load-bearing →
typeable, `html.Div | list[Any]`), `llm.py:499` and `:548` (load-bearing → typeable,
`Iterable[Any]` / `AsyncIterable[Any]`) — and six corrected a reason or a citation. Two
verifiers applied **every** proposed annotation in their area to a scratch copy and ran
strict mypy: **0 errors** (27 edits across 16 files; 45 annotations), and a deliberately
wrong type produced the expected `arg-type` error. Separately, a mechanical pass classified
each bare-`Any` target by rule — a callback parameter by the prop it is bound to, anything
else by name and by what a local is read from. It agrees with the reading on **237 of
290** lines; where they differ the rule was the naive one (`search_config` is a
`SearchConfig` dataclass, not a session dict; `agentifier/subagents.py`'s protocol members
are heterogeneous by design).

**A premise corrected on the way.** Both passes were told that Dash and litellm objects are
`Any` because pyproject's `ignore_missing_imports` override covers them. **They are not:**
dash 4.1.0 and litellm 1.82.0 ship `py.typed`, and the override only silences a module mypy
cannot find — the mypy cache shows it analysing both. Of the overridden packages the
verifiers checked, only `dash_mantine_components`, `boto3` and `jsonschema` ship no types.
So "no stubs" is no reason for a Dash or litellm row.
The load-bearing litellm rows stand on duck-typed reading instead (`_get`, `getattr`), and
the one first-party place that erases litellm's typed return to `Any` is
`_send_with_effort_fallback`'s `tuple[Any, str | None]` (`llm.py:170`, `:189–191`) —
outside the 290, because 5p's grep matches `: Any`, not `tuple[Any`.

| Class | Lines | Where they sit | Proposal |
|---|---:|---|---|
| **session-dict edge** | **90** | Dash callback signatures in `callbacks/` (89) — the store and session payloads they are bound to — and `app.py:372` | **Phase 8.** Typing it is the session `TypedDict` the plan bars from cleanup (§27.5(h)) |
| **JSON artifact edge** | **107** | the renderers and artifact readers — `agents/` 61, root modules 40, `layouts/` 4, one each in `agentifier/` and `callbacks/` | **Phase 8.** `TypedDict`s for the artifact schemas, where the schema *is* the design |
| **genuinely typeable** | **58** | `callbacks/` 20, `agents/` 14, root modules 12, `agentifier/` 10, `layouts/` 2 | **Phase 7** |
| **load-bearing** | **35** | root 17 (litellm usage, response and chunk values read through `_get`/`getattr`; `**extra_kwargs` passthroughs), `layouts/` 8 (`**kwargs` into the untyped `dmc`), `agentifier/` 5 (the `SubAgent` protocol's heterogeneous inputs), `agents/` 3, `callbacks/` 2 | **Stays**, with its reason beside it where it is not obvious |

**The 58, by proposed type:** `str | None` 11 · `dict[str, Any]` 5 · `int | None` 5 · `str`
5 · `SearchConfig | None` 4 · `SearchConfig | str | None` 3 · `dict[str, Any] | None` 3 ·
`bool | None` 3 · `list[str | None]` 2 · `int` 2 · one each of `ComposerOutput`,
`Candidate`, `TierAnalystOutput`, `DesignerSession`, `AsyncIterable[str]`,
`Iterable[Any]`, `AsyncIterable[Any]`, `html.Div | list[Any]`, `pathlib.Path | None`,
`float | None`, `str | dict[str, str] | None` and `Awaitable[_T] -> _T` · and three lines
that carry several parameters (`agents/designer.py:601`, `app.py:427`, `llm.py:356`). They
come from three places: Dash callback inputs bound to a fixed-type prop (`n_clicks` → `int
| None`; `provider_label`, `refine_text` → `str | None`; `annotations` → `list[str |
None]`; `image_support` → `bool | None`, stale `localStorage` values included, since every
writer the store ever had emitted `bool | None`); first-party types that already exist
(`SearchConfig`, `Candidate`, `ComposerOutput`, `TierAnalystOutput`, `DesignerSession`);
and values with a single writer type (`working_dir`, `version`, `agent`).

**Caveats the verifiers kept, for the Phase 7 commit.** `received`, `status` and
`working_dir` read straight out of the live session type cleanly without a `TypedDict`, but
the type rests on today's writer set rather than being enforced where the value is made.
The two schema validators' `data: dict[str, Any]` (`_code_review_schema.py:516`,
`_phase_schema.py:131`) narrows a check that accepts any JSON — true of today's producers.
And strict does not enable `warn_unreachable`, so an `isinstance` branch that a narrower
type makes dead goes dead silently (`_review_render.py:57`).

**Beyond the 58.** Another 81 lines are callback signatures classed by their store
parameter, and on them sit **107 prop-bound inputs** the mechanical pass types by their
prop — `n` ×51, `n_clicks_list` ×6, `n_clicks` ×5, `model` ×5, `provider_label` ×4 and so
on. Typing them is the same work, but each line keeps its `Any` for the store, so the 290
would not move. In `callbacks/designer/` and `layouts/` the verifier applied those partial
annotations as well — mypy-clean; elsewhere they are unverified.

**The proposal.** Phase 7 takes the **genuinely typeable** class — the 58 lines, which takes
5p's figure from 290 to 232 — and, if it chooses, the 107 prop-bound inputs beside them.
Its check is strict mypy after each replacement; because mypy is already clean, a narrower
type is only as good as the producer evidence behind it, which the verify pass supplies
line by line. The session-dict and JSON-artifact edges defer to **Phase 8**, where the
question is a `TypedDict` design, not cleanup. One scope question Phase 7 can settle first:
13 of `callbacks/designer/`'s session-edge rows carry only the Designer wizard's own store,
which `agents/designer.py:132–137` already partly models as the `DesignerSession`
`TypedDict` — whether §27.5(h)'s prohibition, written for "the session dict", reaches that
store is a ruling, not a measurement. Load-bearing stays.

**Where it goes in the order** (§60.6): after the seam decisions and before root-siblings,
the plan's order, and nothing forces it earlier — the typeable lines are overwhelmingly
callback signatures and helpers that no rename or seam proposal touches. Before
root-siblings has a reason of its own: 11 of the 290 sit in two of the four modules the
move would relocate (`_phase_markdown.py` 6, `_usage.py` 5), and annotating before the move
keeps each diff to one concern.

**Outside the 290**, for Phase 8's sizing and not classified here: **148** `-> Any` return
lines, the same four shapes on the return side; and **891** `dict[str, Any]` lines (972
occurrences), session-dict or JSON artifact edges by construction.

#### The `project_manager` root-siblings inconsistency

**The inconsistency.** Phase 4b split `project_manager.py` into four concern modules and
left them at the package root — `src/spec4/_paths.py` (199 lines), `_artifacts.py` (580),
`_phase_markdown.py` (518), `_usage.py` (438) — with `project_manager.py` (487) as the
façade whose `__all__` is load-bearing under strict mypy's no-implicit-re-export. Phases
4c–4e did the same kind of split the other way: `agents/code_scanner/`,
`agents/stack_advisor/`, `agents/phaser/` became packages with their pieces inside. So one
concern's four modules sit loose among unrelated root modules, and
`src/spec4/_artifacts.py` sits one import line from the unrelated
`src/spec4/callbacks/_artifacts.py` (548 lines of Dash callbacks) — the cost §27.7 named.
Converting `project_manager` to a package the way 4c–4e did is a move, no logic.

**The sites** — every tracked reference to the four modules by path, **16 lines in 5
files**: `project_manager.py:8, 10, 12, 13` (its docstring) and `:42, 70, 82, 87` (its
imports); `_artifacts.py:28, 35`; `_usage.py:24`; `tests/conftest.py:84, 85, 95` (the
`module_seam` docstring and example); `tests/test_usage_capture.py:854, 878` (the two
`module_seam("spec4._usage.os", …)` calls). Nothing in `evals/`, `scripts/` or the docs.
None of the five is a §50.3 entry. For contrast, `callbacks/_artifacts.py` — which would
*not* move — is reached from `callbacks/__init__.py:17, 89` and seven test lines in three
files.

**It interacts, so batch 11 waits.** All three `project_manager` rename names live in root
siblings — `_write_text_if_changed` and `_with_readme_attribution` in `_artifacts.py`,
`_phase_spec_preamble` in `_phase_markdown.py` — so the rename and the move edit the same
definitions and the same import lines in `project_manager.py`. **Batch 11 waits for the
root-siblings decision, as the directive requires**; and it is one of the three
`_with_readme_attribution` stops anyway. The `_usage.py` seam (§60.4) touches a root
sibling too: after a conversion its patch target `spec4._usage._replace` becomes
`spec4.project_manager._usage._replace` — one string at two sites, which the move would
re-point in the same commit. That is the smaller churn, so the seam is not held back.

#### M8, M2 and the caught-by-neither cells

Re-run at `f862f65` in a scratch clone, each mutation against both classes and the full
suite, `callbacks/designer/__init__.py` restored byte-identical after each:

| Mutation | `TestMockBuffers` (net) | `TestMockDeliveryAck` | Full suite |
|---|---|---|---|
| none — the control | | | `4199 passed, 1 skipped` |
| **M2**, the corrected anchor: the delivery tick returns `True` (interval off) instead of `no_update` | **FAIL** — `test_a_generation_from_start_to_acknowledged_delivery` | **FAIL** — `test_delivers_step6_payload_while_store_is_at_step_5` | 2 failed |
| **M8**, exactly as §56 defined it: `"The mock was generated and saved, but this page "` → `"Generation failed. "` | PASS | PASS | **`4199 passed`** — caught by nothing |
| M8b: the whole four-fragment message → `"Generation failed."` | FAIL | FAIL | 2 failed |
| M8c: only `"Refresh the page … Retry to regenerate."` removed | FAIL | FAIL | 2 failed |

So **§56.3's M2 row reads FAIL | FAIL**, and **M8 is the only caught-by-neither cell — in
the whole suite, not just the two classes.** The two tests that do catch M8b/M8c are
`test_designer.py::TestMockDeliveryAck::test_runaway_valve_reports_the_saved_mock` (`:1543`)
and its twin in `test_streaming_characterization.py` (`:559`); both assert only
`"Refresh the page" in buf["error"]`.

**The acceptance check for the test that pins M8:**

1. Under **M8**, the new test fails and nothing else does — the suite goes from 0 to 1
   failure.
2. Under M8b and M8c, the new test fails alongside the two that already catch them.
3. Unmutated, the suite is green.
4. Positive paired with negative (§51.6): it asserts the saved-mock clause is **present**
   in the error, beside what the existing test already asserts is absent afterwards — the
   buffer popped, the interval off.

It belongs in `tests/test_designer.py::TestMockDeliveryAck`, which is neither a whole-file
entry nor a tier-B class; its one tier-A node, `test_delivery_preserves_prior_store_keys`,
is untouched. The twin in `test_streaming_characterization.py` is whole-file net and stays
as it is.

**One harness rule, proposed for Phase 7's mutation checks:** an anchor that does not match
is an **error**, not a skip. §56's harness printed `-- anchor not found --` and continued,
and a mutation that never ran sat in a matrix titled "nine mutations" for a sub-phase and
a close-out.

#### `evals/`

**Still outside the gate and outside collection.** `testpaths = ["tests"]`
(`pyproject.toml:81`); **0 of the 4,200** collected node ids is under `evals/`; the gate's
`ruff check src/ tests/` and `mypy src/` do not reach it. The `tests/conftest.py`
dependency §51.3 recorded is **unchanged in content** — `_EVAL_SCRIPTS` still puts
`evals/scout/` on `sys.path` for `tests/agentifier/test_fanout_baseline.py` — but it now
sits at **`:124–126`**, not `:65`: 6b's addendum added `module_seam` above it. The only
line removed from `conftest.py` since `a86a2ee` is an import.

**New since §51: `evals/` imports seven of the rename names** (§60.2 item 5). Outside
collection, nothing would notice them break — which is why §60.2's substitution covers
`evals/` and `scripts/` rather than trusting the gate to.

### 60.6 Proposed sub-phase order and the gate per commit

**What every sub-phase inherits.** The full gate green at its commit — `ruff check` with the
promoted set, `ruff format --check`, `mypy src/` strict, `pytest --cov=spec4`; the floor at
**456** and the off-limits check in both halves, in §60.3's adapted form; coverage
**≤ 891 misses** on `tests/` alone; the tier-B allowed-and-reported template (§51.6);
runtime claimed only as a paired same-session delta; nothing pruned for seconds; negative
assertions paired with positive; one mutation per seam. It also assumes Rule 1 as relaxed
for Phases 5 and 6 (§50.5(e)) — one commit and one report per sub-phase — which needs
confirming for Phase 7.

| # | Sub-phase | Scope | Commits | The check that proves it | Petition |
|---|---|---|---:|---|---|
| 7a | Rename batch 1 — `session` | 5 names, 281 sites (6 with `_load_working_dir`, if §60.4's reading is taken); `app.py:26, 92, 387` | 1 | rename check; gate | §54.7 × 3 whole-file entries; §60.3 × 2 files (3 tier-A nodes; +1 in `test_session.py` with `_load_working_dir`) |
| 7b | batch 2 — `layouts._chat` | 7 of 9 — the two panel collisions held | 1 | rename check; `app.py:33, 409` | §54.7 × 1; §60.3 × 7 files |
| 7c | batch 3 — `layouts` | 8 of 9 — `_agent_rows` held; three module-shadow names | 1 | rename check; `app.py` 8 lines; import-layering test | §54.7 × 2; §60.3 × 5 files |
| 7d | batch 4 — `layouts.designer` | 7 | 1 | rename check | §54.7 × 2; §60.3 × 2 files |
| 7e | batch 5 — `agents.code_scanner` | 7 | 1 | rename check | §54.7 (`test_renderer_goldens.py`); §60.3 × 1 file |
| 7f | batch 6 — `agents.brainstormer` | 5 | 1 | rename check | §54.7 (`test_renderer_goldens.py`) |
| 7g | batch 7 — `agentifier.agentifier` | 20 — 21 if §60.4's reading of `_stream_suppressing_json` (drop the alias) is taken | 1 | rename check | §54.7 (`test_renderer_goldens.py`); §60.3 for the alias's one tier-A site |
| 7h | batch 8 — `agents._seam_check` | 7 | 1 | rename check | §60.3 × 1 file (3 tier-B classes) |
| 7i | batch 9 — `callbacks.designer` | 3 of 4 — `_start_gen` held | 1 | rename check | §60.3 × 1 file (`TestRefinePersistsManifest`) |
| 7j | batch 10 — `llm` | 3 of 4 — `_record_usage` held | 1 | rename check | none |
| — | the six stops | a ruling: another name for each collision; one of §60.3's three options for each blocked name | 0 until ruled | per ruling | §50.5(a), by node id, if a blocked name is to move |
| 7k | `_usage.py` production seam | §60.4's last row | 1 | §60.4's mutation check; coverage per file (`_usage.py`); `module_seam` gone from `conftest.py` | none — no §50.3 entry touched |
| 7l | M8 pinned | one test in `TestMockDeliveryAck` | 1 | §60.5's acceptance check | none |
| 7m | §59.6 item 11 — `test_try_again.py`'s source-text reader re-expressed against a key registry | one test | 1 | a key literal moved out of `agentifier.py` must still be seen — today the set shrinks silently | none |
| 7n | the seam decisions | §60.4 — the two session mutators, the brainstormer seam, the eight agentifier generators with the `yield from` backlog | 4 under shape (a) — one per mutator, one for the brainstormer seam, one for the agentifier eight; under (b), one per converted turn | one mutation per seam (§60.4's column); coverage per touched file | §60.3 where a site changes by identifier substitution alone (`test_ff_sweep.py` × 5 tier-A nodes); §50.5(a), by node id, where a call changes shape |
| 7o | type hygiene | §60.5's 58 genuinely typeable lines (the 290 → 232); optionally the 107 prop-bound callback inputs on mixed lines | 2 — `callbacks/`, then the rest | strict mypy clean with each replacement (already shown on a scratch copy for two of the four areas); gate; coverage unchanged | none |
| 7p | root-siblings | the decision; if converting, `project_manager/` becomes a package — 4 modules moved, 16 reference lines | 1 | `git diff -M` shows four pure moves plus import lines; the import-layering test; gate | none — none of the 5 files is a §50.3 entry |
| 7q | batch 11 — `project_manager` | 2 of 3 — `_with_readme_attribution` held | 1 | rename check | §60.3 × 1 file (`TestPreambleTwoAltitudesAndSurfaces`) |
| 7r | §59.6 items 9–10 | PLR2004 (49 in `src/`); 13 E501 in `scripts/e2e_agentifier.py` | 1–2 | each rule's own count, to zero or a justified `noqa` | none |
| 7z | the plan's audit | Phase 0's measurements re-run (vulture, deptry, rule-set statistics, layering); `CLEANUP_REPORT.md`; the seven symptoms; `README.md`'s tree, `tests/README.md` (item 13), `CLAUDE.md`; the inventory folded into `BACKLOG.md` | 1+ | the report's before/after | — |

**Where the order departs from a straight reading of the list, and why.**

- **Renames first, in batch order** — the cheapest work per site, with no dependency on
  the seams (§59.6: "item 1 does not depend on item 2"). A stop is held out of its batch,
  never holding the batch.
- **§59.6 item 11 immediately before the seam decisions.** The agentifier seam decision is
  the one change likely to move code *out of* `agentifier.py` — a sub-generator split —
  and item 11's reader breaks silently, as a shrinking set, the moment that happens.
  Everything before it keeps code in place: the renames change identifiers, never an
  `"agentifier_*"` literal.
- **Type hygiene after the seams, before root-siblings** — the plan's order, argued in
  §60.5: nothing forces it earlier, since the typeable lines are overwhelmingly callback
  signatures no rename or seam touches, and 11 of the 290 sit in two modules the
  root-siblings move would relocate.
- **Root-siblings after type hygiene** — the plan's order — **and batch 11 after
  root-siblings** (§60.5).
- **The audit last**, because it measures the result.

**Mode.** The renames fit the plan's "Sonnet 5, auto": every step is mechanical and
checked by the rename check and the petitions. The seam decisions and the stop rulings are
judgment — plan mode.

**Stopping here.** Committed as `cleanup: Phase 7 pre-work (§60)`, `CLEANUP_INVENTORY.md`
only. Phase 7 begins on approval of §60.

### 60.7 Approved — the rulings Phase 7 runs under

§60 approved 2026-09-10. The rulings below are binding on Phase 7 and win over §60's
proposals wherever the two differ; §60's findings otherwise stand as written.

#### (a) The 290 is a grep of `: Any` lines

Carried as exactly that: 5p's `grep -rc ': Any' src/spec4/ --include=*.py`, summed —
**lines containing `: Any`**. Phase 7 reports it only in those terms ("`: Any` lines by 5p's
grep: 290 → 232"), **never as a type-checker number**: `mypy --strict` has no such count,
and the gate's figure stays "no issues found in 92 source files". The directive's "§59.6
item 14" was the directive's slip; §60.0(d) stands — it is item 6.

#### (b) The three collisions get new names

| Private | Public | Left untouched |
|---|---|---|
| `_breadth_panel` | `render_breadth_panel` | the local `breadth_panel` in `_chat_layout` (`layouts/_chat.py:103`) |
| `_retry_panel` | `render_retry_panel` | the local `retry_panel` (`layouts/_chat.py:104`) |
| `_agent_rows` | `build_agent_rows` | the existing public `agent_rows` (`layouts/_agent_rows.py:302`) |

Checked before recording, with §60.2's net cast again for the replacements: none of the
three — nor `load_working_dir`, item (d) — occurs anywhere in the tracked tree as a token,
in its hyphenated component-id form, or inside any string literal (component ids,
session-store keys, patch targets, `__all__` entries, docstrings). A rename that also renamed
a local fails the rename check by construction, because the reverse substitution does not
restore it. If the module turns out to have a stronger convention than `render_` /
`build_`, the batch uses it and says so in its report. With new names the three are no
longer stops: batch 2 carries all nine of its names, batch 3 all nine of its.

#### (c) The three net-blocked names stay private — *rename blocked by net attribute access*

| Name | Owner | Net entry, where it is reached by attribute | Would become |
|---|---|---|---|
| `_record_usage` | `llm.py` | `tests/test_streaming_characterization.py:344` — `llm._record_usage(` | `record_usage` |
| `_start_gen` | `callbacks/designer/_mock_gen.py` | `tests/test_streaming_characterization.py:402` — `dmod._start_gen(` | `start_gen` |
| `_with_readme_attribution` | `_artifacts.py` | `tests/test_project_manager_golden.py:168, 169, 172, 173` — `project_manager._with_readme_attribution(` | `with_readme_attribution` |

No compatibility alias in `src/`, no petition: three names are not worth either. When one
of those net files is next legitimately opened, the rename comes with it. Batch 9 carries
three names, batch 10 three.

#### (d) `_load_working_dir` and the alias join the rename half

- **`_load_working_dir` → `load_working_dir`** is a `spec4.session` name, so it rides in
  **batch 1**, which becomes six names and 305 sites (50.8 per name, still the first
  batch). Scanned as §60.2 scans: no collision, no string reference, no D-number
  citation, no module of that name; one tier-A site
  (`test_session.py::TestLoadWorkingDir::test_picking_a_directory_reopens_the_question`,
  §60.3); one docstring mention (`agents/_turn_flow.py:241`); one tracked `.spec4/` line,
  left (Rule 2). The contract §60.4 proposed documenting is not part of a rename commit.
- **`_stream_suppressing_json`**: the alias is deleted and its sites point at the public
  `stream_suppressing_json` — in **batch 7**. What the rename check shows for it is that
  batch's one documented exception, reported verbatim. Under §60.2's normalisation the
  import line itself may cancel (the `x as x` fold); the module-docstring sentence that
  explains the alias (`agentifier.py:26–28`) will not, and it goes in the same commit,
  since it would otherwise describe a spelling that no longer exists.

#### (e) The agentifier eight: the split and the promotion, taken once

Not promote-as-is. Promoting generators the backlog already says need splitting would be
two public-name churns for one decision. The `yield from` sub-generator split (§27.4) and
the promotion are **one item**, taken once and supervised: the **last Phase 7 sub-phase**,
in plan mode with `ultrathink`, after the rename half and the small seams. If it does not
fit Phase 7 it carries to Phase 8 **whole**, never half-done. The other three seams —
`_persist_artifacts`, `_get_agent_gen`, `_rehydrate_vision_from_disk` — proceed on their
§60.4 proposals.

#### (f) Root-siblings: no-go for Phase 7

To Phase 8, with whatever seams remain. The `project_manager` rename batch still runs, last
in the rename order, renaming only names not involved in the inconsistency. **By §60.5's own
finding that is none of them:** all three are defined in root siblings and re-exported by
`project_manager`'s `__all__` — `_write_text_if_changed` and `_with_readme_attribution` in
`_artifacts.py`, `_phase_spec_preamble` in `_phase_markdown.py` — and
`_with_readme_attribution` is net-blocked besides, (c). **Batch 11 therefore renames
nothing in Phase 7 and makes no commit.** Deferred with root-siblings, to Phase 8:

| Name | Would become | Sites | Why it waits |
|---|---|---:|---|
| `_write_text_if_changed` | `write_text_if_changed` | 4 | defined in `_artifacts.py`, a root sibling |
| `_phase_spec_preamble` | `phase_spec_preamble` | 1 | defined in `_phase_markdown.py`, a root sibling; its tier-B class `TestPreambleTwoAltitudesAndSurfaces` |
| `_with_readme_attribution` | `with_readme_attribution` | 4 | defined in `_artifacts.py`; and blocked by net attribute access, (c) |

The `_usage.py` seam still runs in Phase 7 (item (i)2); Phase 8's move would re-point its
two patch strings.

#### (g) The Designer wizard store: out

The plan's no-`TypedDict` rule covers it. The two-store session model is one design;
typing one store and not the other is an asymmetry, and a `TypedDict` is a design change,
not the hygiene Phase 7 scoped. The 13 designer-store rows stay session-dict edge,
deferred with the rest.

#### (h) Rule 1, relaxed, carries into Phase 7

One commit per rename batch and per sub-phase; the gate green at each; the floor and the
off-limits check in both halves at each, in §60.3's adapted form; and **the
reverse-substitution diff recorded in every rename commit's report**.

#### (i) Three additions to §60.6

1. **Type hygiene takes the 58, on two conditions.** (i) The two areas not yet run through
   mypy — top-level `callbacks/` and the root modules — are run before the batch is
   committed. The gate does this anyway; the report says so. (ii) The 35 load-bearing rows
   are re-read for any whose reason was "no stubs": that reason is void, and a row that
   relied on it moves to the 58 or gets a real reason. Sized now: nine of the 35 reasons
   mention stubs, the override or "untyped". Two were already corrected by the verifiers
   (`agents/designer.py:584`, `llm.py:296`); four rest on `dash_mantine_components`,
   which genuinely ships no types (`callbacks/designer/__init__.py:147`;
   `layouts/designer.py:75, 147, 209`); one is a false match — the "stub" at
   `agentifier/subagents.py:144` is a function's stub body; and **two lean on Dash or
   litellm being untyped and are the re-read**: `layouts/_artifact_view.py:764` (Dash's
   `ctx.triggered_id`) and `llm.py:489` (litellm's `_hidden_params`).
2. **`test_root_routing.py:384` joins the `_usage.py` seam sub-phase.** Replacing
   `pathlib.Path.is_dir` process-wide is the old `os.replace` hazard and gets the same
   treatment: a production seam in `project_manager.directory_opens`
   (`project_manager.py:364`), patched by name, and §52.1's four-way verification — the
   seam transparent when nothing overrides it; the patched seam reached; the stdlib
   `Path.is_dir` real for the whole patch; a clean restore after.
3. **M8's acceptance mutation, restated:** everything in the valve message replaced except
   the "Refresh the page" phrase the two existing tests pin. **Run before recording, at
   `7f969a9`, full suite: `4199 passed, 1 skipped`.** Nothing pins more of the message than
   those two tests — a grep of `tests/` for every clause of it finds only
   `test_designer.py:1549` and `test_streaming_characterization.py:568`, both asserting
   that one phrase. So M8 is a real gap, and item 6 gets its test rather than a closing
   note. The new test pins the **whole** message. Its acceptance: it fails under this
   mutation (and under M8, M8b and M8c) while the rest of the suite stays green; unmutated,
   everything passes. It sits in `test_designer.py::TestMockDeliveryAck` (not net), beside
   `test_runaway_valve_reports_the_saved_mock`; the twin in
   `test_streaming_characterization.py` is whole-file net and stays as it is.

#### (j) The order Phase 7 runs in

Replaces §60.6's table where they differ; its per-commit inheritance stands, as amended by
(h).

| # | Sub-phase | Scope | Mode |
|---|---|---|---|
| 7a | rename batch 1 — `session` | 6 names, 305 sites, `_load_working_dir` included | default, under the rename check |
| 7b | batch 2 — `layouts._chat` | 9, `render_breadth_panel` and `render_retry_panel` among them | default |
| 7c | batch 3 — `layouts` | 9, `build_agent_rows` among them | default |
| 7d–7h | batches 4–8 | as §60.2; batch 7 also drops the alias, (d) | default |
| 7i | batch 9 — `callbacks.designer` | 3; `_start_gen` blocked, (c) | default |
| 7j | batch 10 — `llm` | 3; `_record_usage` blocked, (c) | default |
| — | batch 11 — `project_manager` | nothing to rename, (f); no commit | — |
| 7k | the `_usage.py` seam, with `directory_opens` | (i)2 | plan mode, `ultrathink` |
| 7l | M8 | (i)3 | not ruled |
| 7m | §59.6 item 11 — `test_try_again.py`'s source-text reader | must precede 7q, which may move code out of `agentifier.py` | not ruled |
| 7n | the three non-agentifier seams | §60.4, one commit each | plan mode, `ultrathink` |
| 7o | type hygiene — the 58 | (i)1 | not ruled |
| 7p | §59.6 items 9–10 | PLR2004; the 13 E501 in `scripts/e2e_agentifier.py` | not ruled |
| 7q | **the agentifier eight with the `yield from` backlog — last** | (e) | plan mode, `ultrathink` |
| close-out | the plan's audit | `CLEANUP_REPORT.md`, docs, the inventory fold; root-siblings, batch 11's three names and (c)'s three recorded for Phase 8 | — |
