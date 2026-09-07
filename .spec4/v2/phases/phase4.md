---
{
  "phase_number": 4,
  "total_phases": 7,
  "phase_title": "Per-Agent Effort — Selection Field, Capability Probe, Call Path, and Usage Record",
  "phase_summary": "Add reasoning effort as a stored value alongside the model on every per-agent entry and on the project default, resolved through the single llm_selection.py read/write path, derived from the existing capability probe, passed to every LLM call as LiteLLM's reasoning_effort with drop_params enabled, and recorded per call in usage.json. This phase adds no UI — the gate and setup controls in Phases 5 and 6 sit on top of this field.",
  "features": [
    {
      "id": "per_agent_effort",
      "role": "introduced",
      "scope_note": "The stored field, resolution/inheritance, supported-value derivation, LiteLLM call path, fallback, and usage.json recording land here; the gate select, setup select, status-bar suffix, model chip, and agent-row suffix land in Phases 5 and 6."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "litellm",
      "pytest"
    ],
    "configurations": "No new configuration. Effort is stored beside the model: the project default in the prefs dcc.Store (localStorage) alongside the default provider/model, and each agent's chosen effort in the session dcc.Store (localStorage/sessionStorage as the existing GateSelection uses), both read via callback State. Provider credentials remain in the browser stores only and never reach the server or disk. usage.json (one per round, under .spec4/v{N}/) gains a per-call effort field and stays out of the artifact dependency graph."
  },
  "instructions": [
    "In src/spec4/llm_selection.py, extend the stored per-agent selection record and the project default record so each carries an effort value beside its model. Use the domain vocabulary term Effort; do not introduce a synonym. Keep this the single read/write path — the gate, model chip, retry panel, and setup wizard must all go through it, and nothing parallel may be added.",
    "Extend the existing resolution functions (`resolve`, the per-agent `entry` accessor, and `default_provider_model`) so each returns the (model, effort) pair together rather than the model alone. An agent left on 'default' inherits the default's effort exactly as it already inherits the default's model — implement inheritance in the same code path as the model's, not as a parallel branch.",
    "Confirm that a sub-agent inherits its parent agent's effort by the same mechanism it already inherits the parent's model, and do not add a second inheritance rule.",
    "Add a function in llm_selection.py that returns the effort values offered for a resolved model. Call the existing capability probe (`probe_capabilities`) which uses `litellm.get_supported_openai_params` to determine ONLY whether 'reasoning_effort' is an accepted parameter for that model — never which levels it accepts. When accepted, offer 'default', 'low', 'medium', 'high'. When the probe cannot answer (error, unknown model, no result), fall back to those same four base values. Never assume a level list from a model name.",
    "Add a provider-keyed table in llm_selection.py naming extra effort levels beyond the base four, seeded exactly as: anthropic -> ['max'], openai -> ['xhigh'], and no entry for any other provider. Look the resolved model's provider up in this table and append its extra levels to the offered values; a provider with no entry offers exactly the four base values. Record a numbered design-decision comment (D-XX) at the table naming it as the extension point for provider-specific effort levels, and noting that a level a specific model rejects is handled by the fallback retry rather than by pruning this table.",
    "In src/spec4/llm.py, pass the resolved effort to every LLM call as LiteLLM's `reasoning_effort` parameter with `drop_params=True`, so a model that does not accept the parameter silently ignores it and never raises. When the resolved effort is 'default', omit the parameter entirely — do not send the string 'default'.",
    "Never construct a provider-specific thinking/budget parameter directly. `reasoning_effort` with drop_params is the only mechanism, per the project's standing constraint.",
    "Implement the rejected-value fallback in the existing retry path in llm.py: when the parameter is accepted for the model but the specific level is rejected by the provider, retry the call exactly once with no effort parameter, and record that call's effort as the literal string `default (fallback from <value>)` where <value> is the rejected level. Do not retry more than once and do not fall back through intermediate levels.",
    "Extend the per-call record written to usage.json so each call carries an effort field holding either the effort actually used or the `default (fallback from <value>)` string. Do not change usage.json's per-agent model/token/cost totals structure otherwise, and do not add usage.json to project_manager's dependency graph or pipeline artifact order — its tree status stays presence-only.",
    "Update src/spec4/usage_report.py so the spec4-usage CLI output shows the effort recorded for each call alongside its model, rendering the fallback string as recorded.",
    "Ensure an older usage.json whose call records have no effort field still loads and reports without error — treat a missing effort as 'default' when reading.",
    "In tests/test_agent_llm_selection.py, add a test that an agent with an explicit effort resolves to that effort, and an agent left on 'default' resolves to the project default's effort.",
    "In tests/test_agent_llm_selection.py, add a test that a sub-agent inherits its parent's effort exactly as it inherits the parent's model.",
    "Add a test asserting the offered effort values for a provider with no table entry are exactly 'default', 'low', 'medium', 'high', and a second test asserting an anthropic-provider model additionally offers 'max' and an openai-provider model additionally offers 'xhigh'.",
    "Add a test asserting that when the capability probe cannot determine support, the offered values still fall back to the four base values rather than raising or returning an empty list.",
    "Add a test for the no-op path: a call with an effort against a model that does not accept `reasoning_effort` completes successfully with drop_params enabled and does not raise (mock the litellm call boundary rather than making a network request).",
    "Add a test that a call with effort 'default' sends no reasoning_effort parameter at all, and a test that a rejected level triggers exactly one no-effort retry and records `default (fallback from <value>)` in the usage record."
  ],
  "risk_assessment": {
    "potential_bottlenecks": "This is the phase most exposed to hallucinated third-party behaviour: an AI coder is likely to invent a per-model list of supported effort levels, or to build provider-specific thinking/budget parameters (Anthropic's thinking dict, Gemini's thinking_budget) instead of using reasoning_effort. A second bottleneck is the two distinct failure shapes — parameter not accepted at all (handled silently by drop_params) versus parameter accepted but level rejected (needs the one-shot retry) — which are easy to conflate into one broken branch. Third, changing the return shape of resolve/entry/default_provider_model from a model to a (model, effort) pair will break every existing call site at once.",
    "mitigation_strategy": "Use litellm.get_supported_openai_params strictly as a yes/no check on whether 'reasoning_effort' is accepted, and derive levels only from the base four plus the seeded provider table — write this rule as a D-XX comment at the probe call site so it is not 'improved' later. Implement the two failure shapes as separately named and separately tested code paths. When widening the resolution return shape, grep for every call site of resolve, entry, and default_provider_model across src/ and update them in the same change, then run `uv run pytest` before touching llm.py at all. Mock the litellm boundary in all tests — no test may make a network call."
  },
  "verification": "`uv run pytest` passes, including the new tests in tests/test_agent_llm_selection.py for per-agent resolution, default and sub-agent inheritance, the four base values for an unseeded provider, the seeded anthropic 'max' and openai 'xhigh' entries, the probe-unavailable fallback, the unsupported-parameter no-op, the omitted parameter for 'default', and the one-shot rejected-level retry recorded as `default (fallback from <value>)`. `uv run mypy` (strict) is clean over llm_selection.py, llm.py, and usage_report.py. Run any agent end to end and confirm the round's usage.json records an effort for each call and that `uv run spec4-usage` displays it; an unpriced call is still named and excluded rather than shown as zero (nfr_cost_and_token_figures_stay_accurate_and_reflect_the_latest_completed_run__never_showing_an_unknown_cost_as_zero). Credentials remain in the browser stores only, with no server-side or on-disk key (nfr_provider_credentials_remain_visible_only_to_the_user_s_own_browser_and_are_never_transmitted_elsewhere_or_written_to_disk).",
  "references": [
    {
      "standard": "LiteLLM reasoning_effort / reasoning content",
      "url": "https://docs.litellm.ai/docs/reasoning_content"
    },
    {
      "standard": "LiteLLM drop_params (dropping unsupported params)",
      "url": "https://docs.litellm.ai/docs/completion/drop_params"
    },
    {
      "standard": "LiteLLM Anthropic effort parameter",
      "url": "https://docs.litellm.ai/docs/providers/anthropic_effort"
    },
    {
      "standard": "pytest",
      "url": "https://docs.pytest.org/"
    }
  ]
}
---

# Phase 4 of 7: Per-Agent Effort — Selection Field, Capability Probe, Call Path, and Usage Record

Add reasoning effort as a stored value alongside the model on every per-agent entry and on the project default, resolved through the single llm_selection.py read/write path, derived from the existing capability probe, passed to every LLM call as LiteLLM's reasoning_effort with drop_params enabled, and recorded per call in usage.json. This phase adds no UI — the gate and setup controls in Phases 5 and 6 sit on top of this field.

## Feature Specifications

These specifications are authoritative for this phase. Implement to them; the instructions below tell you how and in what order.

### Per-Agent Effort — product feature — introduced in this phase

*Scope for this phase: The stored field, resolution/inheritance, supported-value derivation, LiteLLM call path, fallback, and usage.json recording land here; the gate select, setup select, status-bar suffix, model chip, and agent-row suffix land in Phases 5 and 6.*

Lets a reasoning-effort level be chosen per agent alongside its model, so agents that need deeper reasoning can use it while others stay fast and cheap.

**Invocation**

- Trigger: A model is resolved for an agent, in the gate panel or the setup wizard's model step.

**Inputs**

- `resolved_model_capabilities` (list of items, required) — The effort levels the chosen model actually supports.
- `chosen_effort` (text, required) — The effort level selected for the agent, or for the default.

**Outputs**

- Primary: The stored effort choice for an agent, or for the default.
- Format: One value alongside the model in the same selection record.
- Schema notes: Allowed values are always 'default' plus low, medium, high, with xhigh or max appearing only when the resolved model supports them.

**Success criteria**

- The offered effort values always match what the resolved model actually supports
- An agent left on 'default' inherits the default's effort exactly as it inherits its model
- The effort appears after the model name wherever the model is shown, but only when it isn't 'default'
- Every run records which effort was actually used
- An unsupported effort value never causes a run to fail
- The gate, the model indicator, the retry flow, and the setup wizard all read and write the same stored value

**Failure modes**

- A model's supported effort levels are misreported (likelihood: medium) — mitigation: Trust only the resolved capability check, never an assumed list
- An unsupported effort value is sent to a model that rejects it (likelihood: low) — mitigation: Drop the parameter silently rather than let the run fail
- Gate and wizard fall out of sync on the stored value (likelihood: low) — mitigation: Keep one single read/write path for the field

- depends on: gate_card_register, setup_wizard_register, chat_frame_register, development_tool_shell (build these no later than `per_agent_effort`)
- entities: Agent, Model, Effort, RunRecord

### UI surfaces for this phase (from the design)

- **`Agent Rows`** [non_ai]
  - screens: project-view
  - inputs: action button per agent: Start, Continue and Required are filled green (one variant); Modify a neutral outline with green text; Needs Update a warn outline; Not Ready a disabled outline. Activating a button routes to that agent as today; Continue resumes an in-progress conversation
  - output: Seven rows in pipeline order: agent, produced artifact, last model (with effort when not default), tokens in/out, one action
  - states: Start, Continue, Required, Modify, Needs Update, Not Ready (disabled), not run (blank model/tokens)
  - reads: Agent, Model, Effort, TokenCount, RunState
  - writes: RunState
  - after (advisory UI ordering): Status Bar & Nav
- **`Gate Panel`** [non_ai]
  - screens: chat-view
  - inputs: Use default (filled), Pick a model (outline), Keep <model> (outline; only when the agent already has an override from a previous entry — the three-button shape)
  - output: One mono naming line 'Model for <agent>: <model> · <effort>' plus the action row. Exactly one gate state is on screen at a time, and the gate precedes the run: while it shows, the transcript, cost strip, action row and composer are not rendered. The mock draws both gate states above a transcript only so both are visible
  - states: no entry: Use default · Pick a model, entry present: Keep <model> · Use default · Pick a model, expanded (see Gate Panel — Expanded)
  - reads: GateSelection, Agent, Model, Effort
  - writes: GateSelection
  - after (advisory UI ordering): Agent Pipeline Row
- **`Gate Panel — Expanded`** [non_ai]
  - screens: chat-view
  - inputs: Provider select, API key field, Model select, Effort select, Use this model, Cancel
  - output: The setup wizard's own fields revealed inline, with effort beside the model
  - states: expanded, effort overridden, model without effort support (Effort shows only "default", disabled)
  - reads: Provider, Credential, Model, Effort, GateSelection
  - writes: GateSelection, Effort, Credential
  - after (advisory UI ordering): Gate Panel
- **`Model & Status Line`** [non_ai]
  - screens: chat-view
  - inputs: change
  - output: Model chip with effort when not default, and the run status line
  - states: idle, replying
  - reads: Model, Effort, RunProgress
  - after (advisory UI ordering): Composer
- **`Default Model Panel`** [non_ai]
  - screens: setup-view
  - inputs: Model select, Effort select
  - output: The default model and effort for the project, with one dimmed connection line and one dimmed effort-scope line
  - states: connected, effort default, effort chosen, model without effort support (Effort shows only "default", disabled)
  - reads: Model, Effort, Provider
  - writes: Model, Effort
  - after (advisory UI ordering): Setup Stepper

## Tech Stack

**Dependencies:**

- litellm
- pytest

**Configurations:** No new configuration. Effort is stored beside the model: the project default in the prefs dcc.Store (localStorage) alongside the default provider/model, and each agent's chosen effort in the session dcc.Store (localStorage/sessionStorage as the existing GateSelection uses), both read via callback State. Provider credentials remain in the browser stores only and never reach the server or disk. usage.json (one per round, under .spec4/v{N}/) gains a per-call effort field and stays out of the artifact dependency graph.

**Approved stack for this phase's declared work** (deterministic, from the stack spec):

- usage_records (persistence): per-round usage/cost rollup; deliberately excluded from the artifact dependency graph and never marked needs-update; now also the durable record of which reasoning effort was actually used per call, including fallback-from-rejected-value outcomes — serves `per_agent_effort`
- session_store (persistence) — serves `per_agent_effort`
- prefs_store (persistence) — serves `per_agent_effort`

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

1. In src/spec4/llm_selection.py, extend the stored per-agent selection record and the project default record so each carries an effort value beside its model. Use the domain vocabulary term Effort; do not introduce a synonym. Keep this the single read/write path — the gate, model chip, retry panel, and setup wizard must all go through it, and nothing parallel may be added.
2. Extend the existing resolution functions (`resolve`, the per-agent `entry` accessor, and `default_provider_model`) so each returns the (model, effort) pair together rather than the model alone. An agent left on 'default' inherits the default's effort exactly as it already inherits the default's model — implement inheritance in the same code path as the model's, not as a parallel branch.
3. Confirm that a sub-agent inherits its parent agent's effort by the same mechanism it already inherits the parent's model, and do not add a second inheritance rule.
4. Add a function in llm_selection.py that returns the effort values offered for a resolved model. Call the existing capability probe (`probe_capabilities`) which uses `litellm.get_supported_openai_params` to determine ONLY whether 'reasoning_effort' is an accepted parameter for that model — never which levels it accepts. When accepted, offer 'default', 'low', 'medium', 'high'. When the probe cannot answer (error, unknown model, no result), fall back to those same four base values. Never assume a level list from a model name.
5. Add a provider-keyed table in llm_selection.py naming extra effort levels beyond the base four, seeded exactly as: anthropic -> ['max'], openai -> ['xhigh'], and no entry for any other provider. Look the resolved model's provider up in this table and append its extra levels to the offered values; a provider with no entry offers exactly the four base values. Record a numbered design-decision comment (D-XX) at the table naming it as the extension point for provider-specific effort levels, and noting that a level a specific model rejects is handled by the fallback retry rather than by pruning this table.
6. In src/spec4/llm.py, pass the resolved effort to every LLM call as LiteLLM's `reasoning_effort` parameter with `drop_params=True`, so a model that does not accept the parameter silently ignores it and never raises. When the resolved effort is 'default', omit the parameter entirely — do not send the string 'default'.
7. Never construct a provider-specific thinking/budget parameter directly. `reasoning_effort` with drop_params is the only mechanism, per the project's standing constraint.
8. Implement the rejected-value fallback in the existing retry path in llm.py: when the parameter is accepted for the model but the specific level is rejected by the provider, retry the call exactly once with no effort parameter, and record that call's effort as the literal string `default (fallback from <value>)` where <value> is the rejected level. Do not retry more than once and do not fall back through intermediate levels.
9. Extend the per-call record written to usage.json so each call carries an effort field holding either the effort actually used or the `default (fallback from <value>)` string. Do not change usage.json's per-agent model/token/cost totals structure otherwise, and do not add usage.json to project_manager's dependency graph or pipeline artifact order — its tree status stays presence-only.
10. Update src/spec4/usage_report.py so the spec4-usage CLI output shows the effort recorded for each call alongside its model, rendering the fallback string as recorded.
11. Ensure an older usage.json whose call records have no effort field still loads and reports without error — treat a missing effort as 'default' when reading.
12. In tests/test_agent_llm_selection.py, add a test that an agent with an explicit effort resolves to that effort, and an agent left on 'default' resolves to the project default's effort.
13. In tests/test_agent_llm_selection.py, add a test that a sub-agent inherits its parent's effort exactly as it inherits the parent's model.
14. Add a test asserting the offered effort values for a provider with no table entry are exactly 'default', 'low', 'medium', 'high', and a second test asserting an anthropic-provider model additionally offers 'max' and an openai-provider model additionally offers 'xhigh'.
15. Add a test asserting that when the capability probe cannot determine support, the offered values still fall back to the four base values rather than raising or returning an empty list.
16. Add a test for the no-op path: a call with an effort against a model that does not accept `reasoning_effort` completes successfully with drop_params enabled and does not raise (mock the litellm call boundary rather than making a network request).
17. Add a test that a call with effort 'default' sends no reasoning_effort parameter at all, and a test that a rejected level triggers exactly one no-effort retry and records `default (fallback from <value>)` in the usage record.

## Risk Assessment

**Potential bottlenecks:**

This is the phase most exposed to hallucinated third-party behaviour: an AI coder is likely to invent a per-model list of supported effort levels, or to build provider-specific thinking/budget parameters (Anthropic's thinking dict, Gemini's thinking_budget) instead of using reasoning_effort. A second bottleneck is the two distinct failure shapes — parameter not accepted at all (handled silently by drop_params) versus parameter accepted but level rejected (needs the one-shot retry) — which are easy to conflate into one broken branch. Third, changing the return shape of resolve/entry/default_provider_model from a model to a (model, effort) pair will break every existing call site at once.

**Mitigation strategy:**

Use litellm.get_supported_openai_params strictly as a yes/no check on whether 'reasoning_effort' is accepted, and derive levels only from the base four plus the seeded provider table — write this rule as a D-XX comment at the probe call site so it is not 'improved' later. Implement the two failure shapes as separately named and separately tested code paths. When widening the resolution return shape, grep for every call site of resolve, entry, and default_provider_model across src/ and update them in the same change, then run `uv run pytest` before touching llm.py at all. Mock the litellm boundary in all tests — no test may make a network call.

## Verification

`uv run pytest` passes, including the new tests in tests/test_agent_llm_selection.py for per-agent resolution, default and sub-agent inheritance, the four base values for an unseeded provider, the seeded anthropic 'max' and openai 'xhigh' entries, the probe-unavailable fallback, the unsupported-parameter no-op, the omitted parameter for 'default', and the one-shot rejected-level retry recorded as `default (fallback from <value>)`. `uv run mypy` (strict) is clean over llm_selection.py, llm.py, and usage_report.py. Run any agent end to end and confirm the round's usage.json records an effort for each call and that `uv run spec4-usage` displays it; an unpriced call is still named and excluded rather than shown as zero (nfr_cost_and_token_figures_stay_accurate_and_reflect_the_latest_completed_run__never_showing_an_unknown_cost_as_zero). Credentials remain in the browser stores only, with no server-side or on-disk key (nfr_provider_credentials_remain_visible_only_to_the_user_s_own_browser_and_are_never_transmitted_elsewhere_or_written_to_disk).

**Non-functional acceptance** (deterministic, from the stack spec):

- `nfr_cost_and_token_figures_stay_accurate_and_reflect_the_latest_completed_run__never_showing_an_unknown_cost_as_zero`: Cost and token figures stay accurate and reflect the latest completed run, never showing an unknown cost as zero — delivered by usage_records


## References

- [LiteLLM reasoning_effort / reasoning content](https://docs.litellm.ai/docs/reasoning_content)
- [LiteLLM drop_params (dropping unsupported params)](https://docs.litellm.ai/docs/completion/drop_params)
- [LiteLLM Anthropic effort parameter](https://docs.litellm.ai/docs/providers/anthropic_effort)
- [pytest](https://docs.pytest.org/)
