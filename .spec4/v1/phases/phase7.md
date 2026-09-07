---
{
  "phase_number": 7,
  "total_phases": 8,
  "phase_title": "Chat Frame Action Row and Back-Button Removal",
  "phase_summary": "Give the chat frame's action row its register — exactly one filled-green primary per row with every other action a neutral outline and Re-scan in the warn tone — and remove the four now-redundant Back controls, updating each test whose id-order assertions cover them.",
  "features": [
    {
      "id": "chat_frame_register",
      "role": "extended",
      "scope_note": "The action-row emphasis rules and the removal of all Back controls land here; the run-cost strip and the Open buttons land in Phase 8."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "dash",
      "dash-mantine-components",
      "pytest",
      "playwright",
      "ruff",
      "mypy"
    ],
    "configurations": "No new environment variables. Button emphasis comes from the Mantine theme primary set once at the theme level; no component sets a colour locally (D-LR2)."
  },
  "instructions": [
    "Read .spec4/v1/design/mock.html for the action row's intended button emphasis and spacing before editing. Lane assignments, where the mock shows artifacts, come exclusively from _round_tree.ROUND_ARTIFACTS, never from the mock's sample data, which misfiles deployment-plan.md.",
    "In src/spec4/layouts/_chat.py, make the Continue action the single filled primary in its row and render Fast Forward, Download, and Re-scan as neutral outlines, with Re-scan in the warn tone. Keep the 'Continue to Designer' skip beside 'Continue to Agentifier' as an outline, so exactly one strongly emphasised action exists per row as the attached specification's success criteria require.",
    "Do not set a colour on any button component (D-LR2) — emphasis comes from the Mantine theme primary and the existing variant/tone mechanism. Do not introduce a new tone value; use the warn tone already defined in the theme.",
    "Before removing any Back control, walk each chat-frame state reachable today and confirm it remains reachable via the pill bar or the status bar's Project link — this is the mitigation the attached specification's failure modes require. Record the walk as a numbered D-XX comment at the removal site per the existing documentation convention.",
    "Remove btn-chat-back from the pill bar and remove the per-agent Back controls btn-stack-to-designer, btn-phaser-to-stack, and btn-deployer-to-phaser from the action row, together with the callbacks that exist solely to serve them. Leave every other id in place.",
    "Update the id-order assertions in tests/test_code_scanner_progress.py that reference the removed ids, so the expected id sequence matches the new action row.",
    "Update tests/test_callback_co_presence.py to drop the removed ids and their callbacks from the chat-frame screen entry, so co-presence no longer expects components that no longer exist.",
    "Search the whole tests/ tree for the four removed ids and update every remaining assertion that references them; the affected files are at minimum tests/test_code_scanner_progress.py and tests/test_callback_co_presence.py, and any chat-frame layout test that asserts button presence.",
    "Add a test asserting that the chat frame's action row contains exactly one filled primary button and that every other action button uses an outline variant, so the emphasis rule cannot regress.",
    "Add a Playwright end-to-end test that starts at the StackAdvisor chat frame, navigates back to the project view using the status bar's Project link, and then reaches the Designer chat frame via the pill bar — proving the removed Back routes have live equivalents.",
    "Run `uv run ruff check src/ tests/`, `uv run ruff format src/ tests/`, and `uv run mypy src/`, fixing every finding introduced by this phase."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "Removing ids that other tests assert on is the main breakage vector — an incomplete sweep leaves the suite red in files not obviously related to the chat frame. There is also a real functional risk that one run state was only reachable via a Back control, stranding the user. Callbacks whose Output referenced a removed component will raise at registration time rather than at render time, failing app startup.",
    "mitigation_strategy": "Grep the entire tests/ tree for each of the four ids before removing them and fix every hit in the same commit; the phase names the two known files but the sweep is authoritative. Perform and record the reachability walk before deleting anything, and back it with the Playwright navigation test. After removal, start the app once before running the suite — a callback still bound to a deleted id fails loudly at startup, which is the fastest signal."
  },
  "verification": "Run `uv run pytest` — the full suite passes with the updated id-order assertions in tests/test_code_scanner_progress.py and the updated chat-frame entry in tests/test_callback_co_presence.py, and no test references btn-chat-back, btn-stack-to-designer, btn-phaser-to-stack, or btn-deployer-to-phaser. Confirm `grep -r 'btn-chat-back\\|btn-stack-to-designer\\|btn-phaser-to-stack\\|btn-deployer-to-phaser' src/ tests/` returns nothing. Then run `uv run python src/spec4/app.py`: the app starts with no callback-registration error, each action row shows exactly one filled green button with all others as neutral outlines and Re-scan in the warn tone, and every agent's chat frame is reachable via the pill bar and the status bar's Project link. Confirms nfr_the_visual_and_navigational_register_is_fully_consistent_across_every_screen_in_the_app_.",
  "references": [
    {
      "standard": "Dash Mantine Components — Button",
      "url": "https://www.dash-mantine-components.com/components/button"
    },
    {
      "standard": "Dash Mantine Components — theming",
      "url": "https://www.dash-mantine-components.com/theming"
    },
    {
      "standard": "Playwright for Python",
      "url": "https://playwright.dev/python/docs/intro"
    },
    {
      "standard": "pytest",
      "url": "https://docs.pytest.org/"
    }
  ]
}
---

# Phase 7 of 8: Chat Frame Action Row and Back-Button Removal

Give the chat frame's action row its register — exactly one filled-green primary per row with every other action a neutral outline and Re-scan in the warn tone — and remove the four now-redundant Back controls, updating each test whose id-order assertions cover them.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Chat Frame Register — product feature — extended in this phase

*Scope for this phase: The action-row emphasis rules and the removal of all Back controls land here; the run-cost strip and the Open buttons land in Phase 8.*

Restyles the existing chat/run interaction surface to match the developer-tool register — a plain-text pipeline indicator, block-style transcript, consistent cost reporting, and outline-style secondary actions — while preserving every existing function.

**Invocation**

- Trigger: The user is on the chat frame for any agent's run.

**Inputs**

- `agent_pipeline_state` (structured data, required) — The seven agents in order along with which is active, completed, or unreachable.
- `transcript_messages` (list of items, required) — The messages exchanged during the run.
- `live_progress_signal` (structured data, required) — Elapsed time and character counters reflecting live activity.
- `turn_token_counts` (structured data, required) — Token counts for the current turn.
- `run_cost_on_completion` (structured data, optional) — The completed run's usage/cost summary.
- `retry_and_breadth_panel_state` (structured data, optional) — State needed to show retry and breadth options.

**Outputs**

- Primary: A rendered chat frame with restyled pipeline indicator, transcript, action row, composer, and progress signal.
- Format: Interactive screen
- Schema notes: Pipeline indicator lists all seven agents in order with active/completed/unreachable states; transcript is a sequence of speaker-labelled blocks; completed-run cost uses the same three-line summary as round cost.

**Success criteria**

- All prior functions remain reachable and working: pipeline indicator, transcript, progress signal, turn tokens, fast-forward with its explanatory panel, retry, breadth, downloads, continue, composer, model indicator, status line.
- The pipeline indicator shows plain text with no connecting arrows and correctly reflects active/completed/unreachable state.
- No per-agent or pipeline-level back control remains, since equivalent navigation exists via the pipeline indicator and the status strip.
- Transcript blocks show a dimmed one-word speaker label and no filled background.
- The transcript's default height is noticeably taller than before while remaining independently scrollable.
- On run completion, cost is shown in the same three-line form used elsewhere.
- Exactly one strongly emphasized action exists per row (the continue action); all others are neutral outlines, except the rescan action shown in a warning tone.
- The live-activity signal is the only moving element on the screen.
- Chars, turn-token and elapsed counters, and the model name in the model chip, render in monospace.

**Failure modes**

- Removing back controls leaves a run state unreachable from the pipeline indicator. (likelihood: medium) — mitigation: Verify every navigable state remains reachable via the pipeline indicator or status strip before removing legacy controls.
- Transcript height change breaks scroll behavior at small viewport sizes. (likelihood: low) — mitigation: Keep the transcript independently scrollable regardless of viewport size.
- The completion cost strip fails to match the round-cost presentation. (likelihood: low) — mitigation: Source both from the same cost-estimation output.

- depends on: round_cost, development_tool_shell (build these no later than `chat_frame_register`)
- entities: Agent, ChatSession, Message, UsageRecord, CostEstimate

## Tech Stack

**Dependencies:**

- dash
- dash-mantine-components
- pytest
- playwright
- ruff
- mypy

**Configurations:** No new environment variables. Button emphasis comes from the Mantine theme primary set once at the theme level; no component sets a colour locally (D-LR2).

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- usage_records (persistence): per-round usage/cost rollup; deliberately excluded from the artifact dependency graph and never marked needs-update; also now the source for the chat frame's on-completion cost strip — serves `chat_frame_register`

**Project-wide stack** (applies to every phase):

- Dash
- Dash Mantine Components
- dash-iconify
- litellm
- mcp
- boto3
- httpx
- jsonschema
- gunicorn
- pyyaml
- mypy
- types-pyyaml
- pytest
- pytest-cov
- Playwright
- Ruff

## Instructions

1. Read .spec4/v1/design/mock.html for the action row's intended button emphasis and spacing before editing. Lane assignments, where the mock shows artifacts, come exclusively from _round_tree.ROUND_ARTIFACTS, never from the mock's sample data, which misfiles deployment-plan.md.
2. In src/spec4/layouts/_chat.py, make the Continue action the single filled primary in its row and render Fast Forward, Download, and Re-scan as neutral outlines, with Re-scan in the warn tone. Keep the 'Continue to Designer' skip beside 'Continue to Agentifier' as an outline, so exactly one strongly emphasised action exists per row as the attached specification's success criteria require.
3. Do not set a colour on any button component (D-LR2) — emphasis comes from the Mantine theme primary and the existing variant/tone mechanism. Do not introduce a new tone value; use the warn tone already defined in the theme.
4. Before removing any Back control, walk each chat-frame state reachable today and confirm it remains reachable via the pill bar or the status bar's Project link — this is the mitigation the attached specification's failure modes require. Record the walk as a numbered D-XX comment at the removal site per the existing documentation convention.
5. Remove btn-chat-back from the pill bar and remove the per-agent Back controls btn-stack-to-designer, btn-phaser-to-stack, and btn-deployer-to-phaser from the action row, together with the callbacks that exist solely to serve them. Leave every other id in place.
6. Update the id-order assertions in tests/test_code_scanner_progress.py that reference the removed ids, so the expected id sequence matches the new action row.
7. Update tests/test_callback_co_presence.py to drop the removed ids and their callbacks from the chat-frame screen entry, so co-presence no longer expects components that no longer exist.
8. Search the whole tests/ tree for the four removed ids and update every remaining assertion that references them; the affected files are at minimum tests/test_code_scanner_progress.py and tests/test_callback_co_presence.py, and any chat-frame layout test that asserts button presence.
9. Add a test asserting that the chat frame's action row contains exactly one filled primary button and that every other action button uses an outline variant, so the emphasis rule cannot regress.
10. Add a Playwright end-to-end test that starts at the StackAdvisor chat frame, navigates back to the project view using the status bar's Project link, and then reaches the Designer chat frame via the pill bar — proving the removed Back routes have live equivalents.
11. Run `uv run ruff check src/ tests/`, `uv run ruff format src/ tests/`, and `uv run mypy src/`, fixing every finding introduced by this phase.

## Risk Assessment

**Potential bottlenecks:**

Removing ids that other tests assert on is the main breakage vector — an incomplete sweep leaves the suite red in files not obviously related to the chat frame. There is also a real functional risk that one run state was only reachable via a Back control, stranding the user. Callbacks whose Output referenced a removed component will raise at registration time rather than at render time, failing app startup.

**Mitigation strategy:**

Grep the entire tests/ tree for each of the four ids before removing them and fix every hit in the same commit; the phase names the two known files but the sweep is authoritative. Perform and record the reachability walk before deleting anything, and back it with the Playwright navigation test. After removal, start the app once before running the suite — a callback still bound to a deleted id fails loudly at startup, which is the fastest signal.

## Verification

Run `uv run pytest` — the full suite passes with the updated id-order assertions in tests/test_code_scanner_progress.py and the updated chat-frame entry in tests/test_callback_co_presence.py, and no test references btn-chat-back, btn-stack-to-designer, btn-phaser-to-stack, or btn-deployer-to-phaser. Confirm `grep -r 'btn-chat-back\|btn-stack-to-designer\|btn-phaser-to-stack\|btn-deployer-to-phaser' src/ tests/` returns nothing. Then run `uv run python src/spec4/app.py`: the app starts with no callback-registration error, each action row shows exactly one filled green button with all others as neutral outlines and Re-scan in the warn tone, and every agent's chat frame is reachable via the pill bar and the status bar's Project link. Confirms nfr_the_visual_and_navigational_register_is_fully_consistent_across_every_screen_in_the_app_.

## References

- [Dash Mantine Components — Button](https://www.dash-mantine-components.com/components/button)
- [Dash Mantine Components — theming](https://www.dash-mantine-components.com/theming)
- [Playwright for Python](https://playwright.dev/python/docs/intro)
- [pytest](https://docs.pytest.org/)
