---
{
  "phase_number": 6,
  "total_phases": 8,
  "phase_title": "Chat Frame Register — Pill Bar, Block Transcript, Progress Signal, and Counters",
  "phase_summary": "Bring the chat frame's presentation surfaces into the dev-tool register: a plain-text seven-agent pill bar with no arrows, a block-style transcript with dimmed speaker labels and no fills, a taller but independently scrollable transcript, monospace counters and model chip, and a thin striped progress bar as the only motion on screen. Every existing function is preserved; the action row and Back-button removal follow in Phase 7.",
  "features": [
    {
      "id": "chat_frame_register",
      "role": "introduced",
      "scope_note": "Pill bar, transcript, progress bar, counters, and model chip land here; the action row, Back-button removal, and the run-cost strip land in Phases 7 and 8."
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
    "configurations": "No new environment variables. Chat-frame styling lands in the single existing stylesheet src/spec4/assets/v3.css. The agent order comes from app_constants.AGENT_KEYS."
  },
  "instructions": [
    "Read .spec4/v1/design/mock.html for the chat frame's intended register — pill bar, transcript blocks, counters, and progress bar — before editing layout code. Lane assignments, where the mock shows artifacts, come exclusively from _round_tree.ROUND_ARTIFACTS, never from the mock's sample data, which misfiles deployment-plan.md.",
    "In src/spec4/layouts/_chat.py, restyle the pill bar to plain text: render the seven agents in order derived from app_constants.AGENT_KEYS (never a locally re-declared list), remove every arrow or connector element between them, mark the active agent with the same active-state mechanism the nav uses, render completed agents at full weight, and dim unreachable ones while keeping their existing tooltip text unchanged.",
    "Keep every existing pill-bar component id exactly as it is — ids are a test contract this phase does not change. The pill bar's Back button is NOT removed in this phase; it is removed in Phase 7 together with its test updates.",
    "Restyle transcript messages as blocks rather than bubbles: remove every filled background, add a dimmed one-word speaker label above each message, and give the user's block a neutral left rule.",
    "Keep the user block's className as 'chat-bubble-user' — the scroll clientside callback in src/spec4/app.py selects on that class, and renaming it silently breaks transcript auto-scroll. Change its appearance in v3.css only.",
    "Raise the transcript's default height to approximately 60% of the viewport while keeping it independently scrollable at every viewport size, using a viewport-relative height with overflow scrolling in v3.css. Do not make the transcript grow the page instead of scrolling.",
    "Apply the existing 'mono' class to the chars counter, the turn-token counter, the elapsed counter, and the model chip's model name. Set no colour on any of these components (D-LR2).",
    "Restyle the progress bar as thin, striped, and animated, and confirm it is the only animated element remaining on the chat frame — remove any residual transition, hover animation, or glow from chat-frame rules in v3.css.",
    "Verify by inspection that every function listed in the attached Chat Frame Register specification's success criteria is still reachable after the restyle, and leave each one's component id untouched.",
    "Add a test asserting the pill bar renders exactly the agents in app_constants.AGENT_KEYS, in that order, with no connector elements, and that the active/completed/unreachable states are applied to the correct entries.",
    "Add a test asserting the user transcript block still carries className 'chat-bubble-user', so the clientside scroll selector contract cannot regress silently.",
    "Add a Playwright end-to-end test that opens the chat frame at a mid-viewport size and asserts the transcript scrolls independently of the page.",
    "Run `uv run ruff check src/ tests/`, `uv run ruff format src/ tests/`, and `uv run mypy src/`, fixing every finding introduced by this phase."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "The chat frame is the app's densest surface, and a restyle can silently break a function whose id or class is load-bearing — 'chat-bubble-user' in particular is a CSS-looking name that is actually a JavaScript selector contract. Changing the transcript height is the most likely source of a small-viewport scroll regression, where the transcript grows the page instead of scrolling internally. Re-declaring the agent list locally in the pill bar would drift from AGENT_KEYS.",
    "mitigation_strategy": "Change appearance in v3.css and leave class names and component ids alone; the explicit test on 'chat-bubble-user' locks the selector contract. Set the transcript height with a viewport-relative value plus overflow scrolling on the transcript container itself and verify at a small viewport with Playwright. Derive the pill bar strictly from app_constants.AGENT_KEYS and assert that derivation in a test."
  },
  "verification": "Run `uv run pytest` — the full suite plus the new pill-bar, class-contract, and scroll tests pass. Then run `uv run python src/spec4/app.py`, open a chat frame, and confirm: the pill bar reads as seven plain labels in pipeline order with no arrows and correct active/completed/dimmed states with tooltips intact; transcript messages are unfilled blocks with dimmed speaker labels and a neutral left rule on the user's; the transcript fills roughly 60% of the viewport and scrolls independently; chars, turn tokens, elapsed, and the model chip render in monospace; the striped progress bar is the only moving element during a run; auto-scroll still follows new messages. Confirms nfr_the_visual_and_navigational_register_is_fully_consistent_across_every_screen_in_the_app_ and nfr_screens_render_fast_enough_to_feel_instantaneous_for_local_file_and_round_data__sub_second_.",
  "references": [
    {
      "standard": "Dash Mantine Components",
      "url": "https://www.dash-mantine-components.com"
    },
    {
      "standard": "Dash Mantine Components — Progress",
      "url": "https://www.dash-mantine-components.com/components/progress"
    },
    {
      "standard": "Dash clientside callbacks",
      "url": "https://dash.plotly.com/clientside-callbacks"
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

# Phase 6 of 8: Chat Frame Register — Pill Bar, Block Transcript, Progress Signal, and Counters

Bring the chat frame's presentation surfaces into the dev-tool register: a plain-text seven-agent pill bar with no arrows, a block-style transcript with dimmed speaker labels and no fills, a taller but independently scrollable transcript, monospace counters and model chip, and a thin striped progress bar as the only motion on screen. Every existing function is preserved; the action row and Back-button removal follow in Phase 7.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Chat Frame Register — product feature — introduced in this phase

*Scope for this phase: Pill bar, transcript, progress bar, counters, and model chip land here; the action row, Back-button removal, and the run-cost strip land in Phases 7 and 8.*

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

**Configurations:** No new environment variables. Chat-frame styling lands in the single existing stylesheet src/spec4/assets/v3.css. The agent order comes from app_constants.AGENT_KEYS.

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

1. Read .spec4/v1/design/mock.html for the chat frame's intended register — pill bar, transcript blocks, counters, and progress bar — before editing layout code. Lane assignments, where the mock shows artifacts, come exclusively from _round_tree.ROUND_ARTIFACTS, never from the mock's sample data, which misfiles deployment-plan.md.
2. In src/spec4/layouts/_chat.py, restyle the pill bar to plain text: render the seven agents in order derived from app_constants.AGENT_KEYS (never a locally re-declared list), remove every arrow or connector element between them, mark the active agent with the same active-state mechanism the nav uses, render completed agents at full weight, and dim unreachable ones while keeping their existing tooltip text unchanged.
3. Keep every existing pill-bar component id exactly as it is — ids are a test contract this phase does not change. The pill bar's Back button is NOT removed in this phase; it is removed in Phase 7 together with its test updates.
4. Restyle transcript messages as blocks rather than bubbles: remove every filled background, add a dimmed one-word speaker label above each message, and give the user's block a neutral left rule.
5. Keep the user block's className as 'chat-bubble-user' — the scroll clientside callback in src/spec4/app.py selects on that class, and renaming it silently breaks transcript auto-scroll. Change its appearance in v3.css only.
6. Raise the transcript's default height to approximately 60% of the viewport while keeping it independently scrollable at every viewport size, using a viewport-relative height with overflow scrolling in v3.css. Do not make the transcript grow the page instead of scrolling.
7. Apply the existing 'mono' class to the chars counter, the turn-token counter, the elapsed counter, and the model chip's model name. Set no colour on any of these components (D-LR2).
8. Restyle the progress bar as thin, striped, and animated, and confirm it is the only animated element remaining on the chat frame — remove any residual transition, hover animation, or glow from chat-frame rules in v3.css.
9. Verify by inspection that every function listed in the attached Chat Frame Register specification's success criteria is still reachable after the restyle, and leave each one's component id untouched.
10. Add a test asserting the pill bar renders exactly the agents in app_constants.AGENT_KEYS, in that order, with no connector elements, and that the active/completed/unreachable states are applied to the correct entries.
11. Add a test asserting the user transcript block still carries className 'chat-bubble-user', so the clientside scroll selector contract cannot regress silently.
12. Add a Playwright end-to-end test that opens the chat frame at a mid-viewport size and asserts the transcript scrolls independently of the page.
13. Run `uv run ruff check src/ tests/`, `uv run ruff format src/ tests/`, and `uv run mypy src/`, fixing every finding introduced by this phase.

## Risk Assessment

**Potential bottlenecks:**

The chat frame is the app's densest surface, and a restyle can silently break a function whose id or class is load-bearing — 'chat-bubble-user' in particular is a CSS-looking name that is actually a JavaScript selector contract. Changing the transcript height is the most likely source of a small-viewport scroll regression, where the transcript grows the page instead of scrolling internally. Re-declaring the agent list locally in the pill bar would drift from AGENT_KEYS.

**Mitigation strategy:**

Change appearance in v3.css and leave class names and component ids alone; the explicit test on 'chat-bubble-user' locks the selector contract. Set the transcript height with a viewport-relative value plus overflow scrolling on the transcript container itself and verify at a small viewport with Playwright. Derive the pill bar strictly from app_constants.AGENT_KEYS and assert that derivation in a test.

## Verification

Run `uv run pytest` — the full suite plus the new pill-bar, class-contract, and scroll tests pass. Then run `uv run python src/spec4/app.py`, open a chat frame, and confirm: the pill bar reads as seven plain labels in pipeline order with no arrows and correct active/completed/dimmed states with tooltips intact; transcript messages are unfilled blocks with dimmed speaker labels and a neutral left rule on the user's; the transcript fills roughly 60% of the viewport and scrolls independently; chars, turn tokens, elapsed, and the model chip render in monospace; the striped progress bar is the only moving element during a run; auto-scroll still follows new messages. Confirms nfr_the_visual_and_navigational_register_is_fully_consistent_across_every_screen_in_the_app_ and nfr_screens_render_fast_enough_to_feel_instantaneous_for_local_file_and_round_data__sub_second_.

## References

- [Dash Mantine Components](https://www.dash-mantine-components.com)
- [Dash Mantine Components — Progress](https://www.dash-mantine-components.com/components/progress)
- [Dash clientside callbacks](https://dash.plotly.com/clientside-callbacks)
- [Playwright for Python](https://playwright.dev/python/docs/intro)
- [pytest](https://docs.pytest.org/)
