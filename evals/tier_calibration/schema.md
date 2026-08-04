# Tier Calibration Fixture Schema

Each fixture file is a JSON object with the following top-level fields:

## Top-level fields

| Field | Type | Required | Description |
|---|---|---|---|
| `project` | string | yes | Short project name (e.g. `"shelflife"`) — for display only |
| `search_level` | string | yes | Scout breadth level used (`"focused"`, `"balanced"`, `"exhaustive"`) |
| `fidelity` | string | no | `"verbatim"` if candidate descriptions are exact Scout output; `"representative_descriptions"` if they were written to match the intent |
| `note` | string | no | Free-text provenance note — describe the run date, model, and any caveats |
| `candidates` | array | yes | List of labeled candidate entries (see below) |

## Candidate entry

Each element of `candidates` is an object with:

| Field | Type | Required | Description |
|---|---|---|---|
| `candidate` | object | yes | The candidate as it would be fed to Tier Analyst (matches `Candidate` dataclass) |
| `expected_tier` | string | yes | The ground-truth tier label for this candidate |

## `candidate` object fields

Matches the `Candidate` dataclass in `src/spec4/agentifier/scout.py`:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Snake-case candidate name — use VERBATIM Scout output when fidelity matters |
| `scope` | string | yes | `"feature"`, `"sub_feature"`, or `"cross_feature"` |
| `rough_description` | string | yes | 1–2 sentence description of what the integration does |
| `linked_vision_features` | array[string] | yes | Vision features this candidate relates to (may be empty) |
| `linked_existing_workflow` | string | no | Brownfield only: existing workflow this would replace |

## Valid `expected_tier` values

Must be one of the nine tier names from the ladder (in order):

1. `deterministic`
2. `embeddings`
3. `single_call`
4. `rag`
5. `tool_agent`
6. `chained_calls`
7. `planning_agent`
8. `orchestrated_subagents`
9. `multi_agent_collaboration`

## Example

```json
{
  "project": "myapp",
  "search_level": "balanced",
  "fidelity": "verbatim",
  "note": "From Scout run 2026-06-01, claude-sonnet-4-6, balanced breadth.",
  "candidates": [
    {
      "candidate": {
        "name": "smart_expiry_prediction",
        "scope": "feature",
        "rough_description": "Given a purchase date and category, compute expected expiry.",
        "linked_vision_features": ["expiry_tracking"]
      },
      "expected_tier": "deterministic"
    }
  ]
}
```

## Fidelity note

For the highest eval accuracy, the `rough_description` and `name` fields should be **verbatim** Scout output. Aspirational naming (`smart_`, `intelligent_`, `optimized_`, `engine`) is a key part of what the Tier Analyst framing-strip rule is tested against — a sanitised description removes the signal.

When adding a new fixture from a real run, paste the Scout JSON array output directly rather than paraphrasing.
