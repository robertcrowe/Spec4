# Pattern file schema

Every pattern in the Agentifier pattern library is a single Markdown file with
a YAML frontmatter block. The frontmatter holds structured, typed metadata; the
Markdown body holds the long-form prose sections that do the real work. This
split was chosen because the prose (`When it works`, `When it doesn't`, …) is
long-form and benefits from Markdown formatting, while the metadata
(`last_reviewed`, `references`, `library_version`, …) is structured and benefits
from typed parsing. Frontmatter is parsed with PyYAML.

The library has two categories of pattern:

- **Tier patterns** (`patterns/tiers/`) describe *what shape* an AI feature is —
  a single LLM call, RAG, a tool-using agent, and so on. There is one pattern
  per tier, and a given feature has exactly one tier.
- **Mechanism patterns** (`patterns/mechanisms/`) describe *how* an AI feature
  is built — MCP for tool access, parallel fan-out, reflection, and so on.
  Mechanisms combine orthogonally with tiers; a feature has zero or more.

## File layout

```
src/spec4/agentifier/patterns/
├── SCHEMA.md              # this file
├── tiers/
│   ├── 01_deterministic.md
│   ├── 02_embeddings.md
│   └── … (nine total)
└── mechanisms/
    ├── mcp.md
    └── … (six total)
```

Tier filenames carry a numeric prefix (`01_`, `02_`, …) for visual ordering
only. The loader ignores the prefix; the `name` frontmatter field is the
identifier, and it must match the filename stem with any leading `NN_` prefix
stripped (so `01_deterministic.md` must declare `name: deterministic`).

## Frontmatter

### Required for every pattern

| Field | Type | Notes |
|---|---|---|
| `name` | string | Pattern identifier (e.g. `single_call`, `mcp`). Must match the filename stem (after stripping any `NN_` prefix). |
| `category` | `tier` \| `mechanism` | Must match the subdirectory the file lives in. |
| `library_version` | string | Semantic version. `"1.0.0"` for all Phase 1 files. |
| `last_reviewed` | ISO date string | `YYYY-MM-DD`. The date the content was last reviewed. |
| `references` | list of strings | Each a citation or URL to canonical documentation. May be empty. |

### Required for tier patterns only

| Field | Type | Notes |
|---|---|---|
| `tier_order` | integer 1–9 | Position on the tier ladder. `deterministic` is 1, `multi_agent_collaboration` is 9. Must be unique across tiers. |
| `cost_range_usd` | string | Rough cost per invocation, e.g. `"$0.001–$0.05"`. |
| `latency_range_seconds` | string | Rough latency, e.g. `"1–5"`. |
| `required_infrastructure` | list of strings | Enabling-substrate component ids that this *tier* implies, independent of the specific vision (a closed registry, not LLM invention). May be empty (`[]`) for tiers with no tier-specific substrate, e.g. `deterministic` and `single_call`. Consumed by the deterministic infrastructure-expansion pass, which injects one `kind: infrastructure` node per unique component (dedup by id) after tier analysis. |

Mechanism patterns must NOT declare the tier-only fields.

`required_infrastructure` names **structural substrate only** — never
project-wide `cross_cutting` concerns (provider/model access, tool-protocol
choice, prompt versioning). Those are cross-cutting, not tier infrastructure, and
a test asserts they never appear here. Component ids have stable identity and
dedup across tiers (e.g. `embedding_pipeline` + `vector_index` are shared by
`embeddings` and `rag`); injection collapses by component, not by tier.

## Prose sections

Each of the following must appear as a top-level (`##`) Markdown heading, in
this exact order, with non-empty content. No other top-level headings are
permitted (a typo'd heading is treated as an error so it cannot silently hide
content from the loader).

1. `## Description` — one-paragraph description of the pattern.
2. `## When it works` — bulleted list of specific situations where this pattern
   is the right choice.
3. `## When it doesn't` — bulleted list of specific situations where this
   pattern is the wrong choice.
4. `## Over-engineering signs` — concrete signals that the user reached for this
   pattern when a simpler one would do.
5. `## Under-engineering signs` — concrete signals that the user settled for
   this pattern when a more complex one is genuinely needed. (For
   `deterministic`, this section captures cases where the user is avoiding AI
   but should consider it.)
6. `## References` — canonical sources, papers, or post-mortems supporting the
   claims above. May restate frontmatter `references` in reader-friendly form.

The loader parses the four list-shaped sections (`When it works`,
`When it doesn't`, `Over-engineering signs`, `Under-engineering signs`) into
lists of strings, one entry per top-level Markdown bullet (`-`). `Description`
is kept as a single string. `References` is parsed into a list of bullet
strings; if a file's References section has no bullets it falls back to the
frontmatter `references` list.

## Validation rules enforced by the loader

`pattern_loader.load_patterns()` raises `PatternValidationError` (a subclass of
`ValueError`) with a message naming the offending file when:

- a required frontmatter field is missing or has the wrong type;
- a tier file is missing one of the tier-only fields, or a mechanism file
  declares a tier-only field;
- `tier_order` is not an integer in 1–9, or is duplicated across tiers;
- `category` does not match the subdirectory the file was found in;
- the `name` frontmatter field does not match the filename stem;
- a required prose section is missing or empty;
- an unknown top-level section heading appears;
- the prose sections appear out of order.

The loader performs no file I/O at import time — all reads happen inside
`load_patterns()`.
