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

Phase 3 scope, then, is items 1–5 (four containers, three locks, one dict cache) plus the `lru_cache`. Item 1 is the only one with a plausible concurrency gap (unlocked `_STREAMS[stream_id]["text"] +=` on the worker thread while `get_stream` reads under the lock on another); it is not a bug report because CPython's dict/str semantics make the observed effect at worst a stale read, but it should be looked at when the state moves.

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

1. **`test_no_transcript_block_is_filled` fails deterministically** on `look-rework` (§1.1). `.chat-msg` elements on `/chat` resolve to `rgb(18, 18, 26)` (`#12121a`, `app_constants.py:88`) rather than transparent. Either the look rework intends filled transcript blocks and the test needs updating, or a stylesheet change leaked a background onto `.chat-msg`. Decide before Phase 1, since Phase 1 builds the UI safety net on top of this suite.
2. **`agentifier/agentifier.py:2262`: `topics` redefined** (mypy `no-redef`, `line 2221` first definition). Not necessarily a behavior bug, but the two definitions have different types; worth a look when Phase 4 touches `_run_cross_cutting_phase`.
3. **`project_manager.py:1894/1903`: `float` compared with `None`** (mypy `operator`). If the `None` branch is reachable this raises `TypeError` at runtime. Verify in Phase 3 or 5.

## 11. Deferred to later phases (noted here, not acted on)

- Phase 2: `dash-iconify` removal from `[project.dependencies]` + mypy override; `download_button_id`; `CODE_REVIEW_SCHEMA_VERSION`; the `valid_tier_names` parameter; `PatternBase`/`PriorityEdits` visibility; the 15 public zero-importer names in §7; the 22 test-side vulture lines.
- Phase 3: the eight items in §8.
- Phase 4: break the `layouts` ↔ `layouts._chat` cycle; decide the fate of `session.py` as the UI/agent hinge; write the import-assertion test (§6.3); split the eight files over 1,300 lines.
- Phase 5: the 61 C901 functions, starting with the table in §5.1; the 26 small SIM/B hits.
- Phase 6: consolidate `test_deployer_*` / `test_phaser_*` / `test_stack_*`; split `test_agents.py`; run `--durations`; the 162 test-side ARG hits are not targets.
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
