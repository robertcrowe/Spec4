# Agentifier

Agentifier walks the developer through choosing the right AI agent architecture for their project. It analyses the codebase, maps the feature against the pattern ladder, and drafts an implementation spec.

The pipeline mirrors the main Spec4 pipeline (Scout → Tier Analyst → Spec Drafter → Cross-Cutting Analyst), but all sub-agents are in-process Python coroutines — no network transport, no protocol framing.

---

## Pattern library

The `patterns/` directory ships a curated, versioned library of tier and mechanism patterns (see `patterns/SCHEMA.md`). `pattern_loader.load_patterns()` reads and validates every file at call time; importing the module has no side effects.

```python
from spec4.agentifier.pattern_loader import load_patterns

tiers, mechanisms = load_patterns()
print(tiers[0].name)          # "deterministic"
print(mechanisms[2].name)     # "parallel_fanout"
```

---

## Sub-agent dispatch

`subagents.py` provides the typed interfaces, error classes, and registry that the Agentifier orchestrator uses to invoke sub-agents. Sub-agents are plain Python classes with an async `run()` or `stream()` method.

### Registering a sub-agent

A sub-agent needs a `name` attribute and an async `run()` method:

```python
from dataclasses import dataclass
from spec4.agentifier.subagents import SubAgentRegistry, validate_dataclass_input

@dataclass
class ScoutInput:
    working_dir: str

class ScoutAgent:
    name = "scout"

    async def run(self, input: ScoutInput) -> dict:
        validate_dataclass_input(input, ScoutInput)
        # ... gather project context ...
        return {"languages": ["Python"], "has_tests": True}

registry = SubAgentRegistry()
registry.register(ScoutAgent())
```

`validate_dataclass_input(value, ExpectedType)` raises `TypeError` immediately when a caller passes the wrong type, giving a clear error rather than a cryptic `AttributeError` inside the agent.

### Invoking in request/response mode

```python
result = await registry.run("scout", ScoutInput(working_dir="/my/project"))
# or invoke directly (no registry required):
result = await ScoutAgent().run(ScoutInput(working_dir="/my/project"))
```

Exceptions from the agent are re-raised wrapped in `SubAgentError`, which carries `.name` (the sub-agent name) and `.cause` (the original exception). An already-wrapped `SubAgentError` passes through unchanged.

### Invoking in streaming mode

Streaming sub-agents are async generators:

```python
from spec4.agentifier.subagents import StreamingSubAgent

class DraftStreamer:
    name = "spec_drafter"

    async def stream(self, input: ScoutInput):
        validate_dataclass_input(input, ScoutInput)
        for chunk in _generate_draft_chunks(input):
            yield chunk

registry.register(DraftStreamer())

async for chunk in registry.stream("spec_drafter", ScoutInput(working_dir="/my/project")):
    print(chunk, end="", flush=True)
```

### Applying a timeout

Use `run_with_timeout` to cancel a sub-agent that exceeds its budget:

```python
from spec4.agentifier.subagents import run_with_timeout, SubAgentTimeoutError

agent = ScoutAgent()
try:
    result = await run_with_timeout(
        agent.run(ScoutInput(working_dir="/my/project")),
        timeout=30.0,
        name="scout",
    )
except SubAgentTimeoutError as exc:
    print(f"{exc.name} timed out after {exc.timeout}s")
```

`SubAgentTimeoutError` is a subclass of `SubAgentError`, so callers that catch the base class handle both.
