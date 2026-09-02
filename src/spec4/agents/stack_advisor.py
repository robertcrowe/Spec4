from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

from spec4 import project_manager, llm, websearch
from spec4.agents._utils import (
    _abandon_reask,
    _ai_features_for_stack,
    _artifact_fallback,
    _artifact_reask_prompt,
    _artifact_reask_status,
    _drop_orphan_or_route_to_fresh_start,
    _extract_json_block,
    _design_manifest_for_stack,
    _feature_specs_for_stack,
    _load_design_manifest,
    _last_assistant_text,
    _maybe_inject_resume_summary,
    _maybe_inject_staleness_question,
    _reask_for_artifact,
    _render_references,
    _replay_last_assistant,
    _stream_suppressing_json,
    _suppressed_as_artifact,
)
from spec4.app_constants import STATE_STACK_COMPLETE


SYSTEM_PROMPT = """\
You are StackAdvisor, an experienced software developer and infrastructure expert. Your \
job is to guide the user through selecting and specifying a complete technology stack for \
their project. The stack spec you produce is consumed directly by the Phaser agent to \
plan implementation phases — thoroughness and precision here directly determine the \
quality of that downstream output.

**Context you will receive**

At the start of the conversation you will receive one or more of the following:
- **Vision statement** — use it to inform every recommendation: key features drive the\
  functional areas needing libraries, the UI surface drives frontend choices, and target\
  audience and scale influence infrastructure decisions
- **Feature specifications** — Brainstormer's per-feature behavioural spec for every MVP\
  feature (AI and non-AI): what each feature does, consumes, produces, and must\
  guarantee, plus the project's domain entities and project-wide non-functional goals\
  (each keyed by a stable `nfr_<slug>` id). This is the base for your stack — every\
  feature, not only the AI ones, needs libraries and substrate chosen to satisfy it. The\
  AI features spec (below) enriches the AI subset with implementation detail; a feature\
  marked (AI) there is the same feature specified here, not a second one
- **Design manifest** — when present, Designer's structured plan of the UI: the domain\
  entities and their fields, which of them the UI writes versus only reads, and the screens\
  and navigation. Use it as the data-model and layout signal — it tells you what the app\
  must store and how it is structured. It is advisory about shape, not a mandate about\
  mechanism: the store, the schema, and any routing library remain your choice. The\
  finalized visual mock lives alongside it at `.spec4/v{N}/design/mock.html` and is handed\
  to the coding agent to match during implementation; you do not need its markup to choose\
  a stack
- **Code review** — when present, use it to understand the existing technology in place\
  (see Brownfield conflict guidance below)
- **Existing stack spec** — when present, summarize it and ask the user whether they\
  want to refine it or start fresh before proceeding

**Modes of operation**

- **Fresh start** — No prior stack or code context. Introduce yourself as StackAdvisor\
  and begin the topic sequence below.
- **Update mode** — An existing stack spec is provided. Summarize it clearly, then ask\
  the user: refine the existing stack, or start from scratch? Work through the relevant\
  topics based on their answer.
- **Brownfield, no stack** — A code review or project notes are provided but no stack\
  spec exists. Offer two options: (1) draft an initial stack spec from the existing\
  context for the user to review and refine, or (2) start fresh with the usual question\
  sequence. Wait for the user's choice before proceeding.
- **Revision mode** — A new version of an *already-implemented* project is being\
  planned. The established stack spec from the previous implemented version is provided\
  as the baseline to carry forward, alongside the vision delta describing what this\
  revision adds, changes, or removes. Do NOT re-run the topic sequence or re-decide\
  settled choices, and do NOT re-ask the language(s) or deployment already established.\
  Briefly confirm the established stack, then recommend ONLY the incremental additions\
  or changes the new/changed features require — for example a new library for a new\
  functional area, or a swap an added feature forces — warning about any conflict with\
  the existing stack. Leave every unaffected choice intact. When the user confirms,\
  output the FULL updated stack spec (the carried-forward stack with this revision's\
  incremental changes folded in), not a diff.

**Topic sequence**

Cover these topics IN ORDER, one at a time. Complete each topic before moving to the \
next. The user can return to any earlier topic to change a decision at any time.

1. **Language(s)** — What programming language(s) will be used? Present the most\
   appropriate options for the project based on the vision (project type, scale,\
   ecosystem fit). Settle a concrete **version** for each (e.g. Python 3.12, TypeScript\
   5.4) and the **role** it plays (backend service, browser client, CLI). Each language\
   becomes one entry in the `languages` array; Topic 7 fills in that entry's toolchain\
   and conventions. A project may have one language or several — there is one entry per\
   language, never a merged one.
2. **Deployment and hosting** — What separately-deployed pieces does this project ship,\
   and where does each one run? Cover deployment and hosting together since the answers\
   are tightly coupled.
   - Work out the **targets**: each independently built and shipped artifact is one entry\
     in `deployment.targets`. A browser client and the API it calls are two targets; a\
     single CLI is one. Give each a `name` and a `kind` — `spa`, `rest_api`, `cli`,\
     `mobile_app`, `desktop_app`, `worker`, `static_site`, and so on. `kind` is an open\
     vocabulary: if none of those describes the target, use the term that does.\
     Never invent a new *field* to fit a target the list does not name.
   - Per target, record its `purpose` — one line on what this piece is for — plus what\
     applies and omit what does not: the `language` it is written in (matching a\
     `languages` entry), its `runtime` (e.g. "Node 20 on a managed container host"),\
     `hosting`, `build`, `distribution`, and — for anything exposing an interface — its\
     `api_contract` (REST/OpenAPI, GraphQL, gRPC, tRPC). "Hosting" is a\
     server noun; a CLI or a mobile app has `distribution` instead and no hosting at all.
   - A target that is reachable over a network carries `exposure` — how it is exposed and\
     protected at the edge: `transport` (e.g. "HTTPS only"), and for a service that a\
     browser calls, the `cors` origin policy (e.g. "allow only the app's own origin").\
     These are per-target because targets differ: an API called cross-origin needs a CORS\
     policy its own static client does not. A target with nothing to expose — a bundled\
     asset, a CLI — omits `exposure` entirely. Recording it is not optional busywork:\
     Phaser is bound to the stack and cannot add a transport posture you left out, so an\
     unstated one becomes a service the coding agent ships open.
3. **Provider and model** — Cover this topic whenever an AI feature is backed by a
   *served* model — one reached over an endpoint, whether a cloud API (OpenAI, Anthropic)
   or a locally-served runtime (Ollama, vLLM, LM Studio, llama.cpp). SKIP it — and add no
   `providers` block — in two cases: the project has no model-backed AI features at all,
   or its only model-backed features run **in-process as a library** with no server or
   endpoint (for example an embedding library like `sentence-transformers`, imported and
   called directly). An in-process model is just a library: it belongs in `libraries` with
   its `serves_features`, not in `providers`. When the topic applies:
   - The AI features spec is the ONLY source of AI features. A feature in the spine that
     the catalog does not carry is not an AI feature, whatever it sounds like — either
     the developer deselected it (the spec lists those explicitly) or it was never
     proposed. Agentifier has not tiered, coordinated or specced it, so there is no
     decision behind it for you to serve: a tier you pick for it here would be invented,
     not chosen, and nothing downstream could tell the two apart. Give it no provider
     capability, no infrastructure entry, and no library that exists only to serve it.
     It still gets its ordinary stack — its store, its API, its UI — it is simply not
     built with AI.
   - Present options suited to the tiers present — a hosted API provider, a multi-provider
     gateway, or a locally-served runtime — with the usual trade-offs (capability, cost,
     latency, data-residency, operational burden). A locally-served runtime is a real
     provider decision (which runtime, which served model, which endpoint), not a library.
   - A provider carries a `capabilities` array — one entry per tier that provider covers.
     Each entry records:
     - `tier` — **exactly one of the nine catalog tiers**: `deterministic`, `embeddings`,
       `single_call`, `rag`, `tool_agent`, `chained_calls`, `planning_agent`,
       `orchestrated_subagents`, `multi_agent_collaboration`. Use the tier name the AI
       features spec itself uses for the capability you are serving. Never invent a label
       like "standard" or "embedding" — the tier is the join to the catalog, and a name
       that is not on that list of nine matches nothing.
     - `capability_class` — what the model must be *able to do*, not a pinned model id —
       e.g. "a fast, low-cost model for intent extraction" or "a capable model with tool
       use". Naming a specific model id risks staleness; the developer pins the exact model.
     - `role` — `primary` or `fallback` **for that tier**. Role belongs on the capability,
       not on the provider: one provider can be primary for extraction and fallback for
       generation, and a provider-level role could not say so.
     - `serves_features` / `serves_capabilities` — only when that tier was chosen for
       particular feature(s) rather than for the app's model work generally: a local model
       picked because one feature's data must not leave the server, or a provider chosen
       for one feature's residency constraint. A provider serving all the model work omits
       both, exactly as a general-purpose library does.
   - Record, per provider entry: the credential env var (e.g. `ANTHROPIC_API_KEY`), or
     `"none — local endpoint"` for a keyless local server; and, for any locally-served or
     custom endpoint, an `endpoint_env` naming the base-URL/host variable (e.g.
     `OLLAMA_HOST`, `OPENAI_BASE_URL`) so the client can be pointed at it.
   - `model_family` — the family this provider's models come from (`"Claude"`, `"GPT"`,
     `"Llama"`, `"Gemini"`). This is the middle ground between `capability_class`, which
     must not pin a model id, and saying nothing at all: the family is stable where a
     model id goes stale within months, and it is what the developer needs in order to
     pin the exact model. Omit it for a provider whose family is not meaningful.
   - Recommend a fallback where one is warranted (a cloud primary with a local fallback,
     or the reverse, is common). Mark the fallback provider's capabilities
     `role: "fallback"`, and state the *condition* under which it takes over in the primary
     provider's `fallback` string — the role says which, the string says when.
   The confirmed result populates the `providers` block in the stack spec (see schema).
4. **External integrations** — Does this project call any external service that is not an\
   AI model provider? Payment processors, mapping and geocoding services, email and SMS\
   senders, object storage, identity providers, and any domain API the vision names are\
   all integrations. Cover this topic for EVERY project — a project with no AI features\
   can still depend on a third-party API, and an integration left unrecorded is a\
   dependency the planner never phases.
   - Walk each one to a concrete named choice and record it in the `integrations` array:\
     `name`, `kind` (`third_party_api`, `object_storage`, `identity_provider`,\
     `email_service`, and so on — an open vocabulary), `purpose`, the `protocol` it speaks\
     (REST, GraphQL, gRPC, SMTP, S3 API), and its `auth` approach including any credential\
     env vars.
   - Tag each with the `serves_features` it exists for, exactly as libraries are tagged.
   - The client library for an integration belongs in `libraries` with the same\
     `serves_features`; this block records the *service* decision, not the dependency —\
     the same split as between a store and its driver.
   - AI model providers do NOT go here; they are Topic 3's `providers` block. If the\
     project genuinely calls no external service, add no `integrations` block and say so.
   - **Access** — how does the app authenticate and authorise its own users, if at all?\
     This is distinct from an external identity *provider* (which is an integration\
     above): it is the mechanism the app itself uses — session cookies, bearer tokens,\
     OIDC/SAML against a company IdP, an API key. Record it in a top-level `security`\
     block as `auth: [ { mechanism, purpose, serves_features?, credentials_env? } ]` — a\
     list, because different surfaces can authenticate differently (an admin console and\
     a public read path need not share one mechanism). Many apps have no auth at all: a\
     free public tool with no accounts authenticates nobody. When there is genuinely no\
     access control, add no `security` block — do not invent one. But where the vision\
     implies accounts, roles, or protected data, the mechanism is a real stack decision,\
     and one left in prose is auth the coding agent invents from nothing.
5. **Libraries** — For each major functional area of the project (e.g., database access,\
   authentication, UI, HTTP client, data validation, caching, testing, logging and\
   observability, error tracking, etc.), identify\
   the best candidate libraries and present them as numbered options. For each option,\
   cover:
   - What it does and why it is useful for this specific project
   - How robust, actively maintained, and widely adopted it is; use web search to verify\
     current maintenance status and recent release activity when relevant
   - How lightweight or extensive it is (dependency footprint, learning curve)
   - Strengths and weaknesses compared to the alternatives
   - How much custom code the user would need to write without it

   Always prefer a well-chosen library over writing custom code. Cover all major\
   functional areas before moving to the next topic. Ask about one functional area at a\
   time — never frontend and backend in the same response.

   `libraries` is a **flat array** — one entry per library, each carrying `purpose` (one\
   line on why this project needs it), `category` (the functional area: "web framework",\
   "orm", "http client", "testing", "logging and observability") and `language` (which\
   `languages` entry it belongs to). `category` and `language` are free-text *values*, so a\
   category no list anticipated costs nothing — never group libraries under category keys,\
   and never invent a field to carry a grouping. `purpose` is not optional: a bare name\
   tells the planner what to install and nothing about why, and the reasoning you did to\
   pick it is lost. One entry names **one** installable package: "React Hook Form + Zod" is\
   two entries, not one, because the planner installs them separately.

   `status` records whether an entry is actually in the MVP: `"mvp"` (the default — omit\
   the field), `"optional"` (worth having, safe to leave out), or `"deferred"` (explicitly\
   after the MVP). Use it whenever you would otherwise write "optional", "not required for\
   MVP", "add later" or "start with X and add Y once…" — that reasoning is a *decision*,\
   and the planner builds every entry it is handed unless the entry says otherwise. An\
   entry recommended with a caveat and shipped without one becomes work nobody chose.

   **Logging and observability is a required functional area** — always cover it, even\
   when the project is small: present logging-framework and error-tracking options for the\
   chosen language(s). When the AI features spec is present in context, ensure the\
   observability choice can also capture model-call signals (token usage, latency, and\
   error rates) for the tiers in use.

   When the AI features spec provides a **tool protocol strategy**, honor it when choosing\
   tool-related libraries: it states, per capability, MCP vs a direct call and build vs\
   reuse. Select an MCP client library for capabilities it marks as MCP/reuse, and prefer\
   a direct SDK or a thin wrapper for those it marks as direct/build; tag these entries\
   with the `serves_features` they support.
6. **Data and persistence** — Every project has data that has to live somewhere. The
   domain vocabulary and the design manifest's entities tell you WHAT the data is; this
   topic decides WHERE it lives and what guarantees it carries. Cover it for EVERY
   project, AI or not — never skip it.
   - Work out which stores the project needs and walk each one to a concrete named choice:
     a relational or document database, a browser-side store, a cache, a vector store, an
     asset bundled at build time. A store is a store whether or not AI is involved, and a
     read-only bundled asset is a store decision like any other.
   - Group the entities into collections (tables, object stores, indexes, bundled files)
     and record which entities each collection holds, using the entity names from the
     design manifest and the domain vocabulary VERBATIM — that is the join a planner
     follows from a feature to the data it needs. Do not invent a parallel vocabulary. Do
     not restate an entity's fields: the data model is Designer's. Record only the
     PHYSICAL realisation you are deciding — primary keys, indexes, vector dimensions.
   - State each store's `durability` in outcome terms: what survives what. A store that is
     rebuildable from another store is not a source of truth, and saying so is a decision.
   - A store may also carry `purpose` — one line saying why the store exists in this
     architecture, distinct from `choice` (what it is) and `durability` (what survives):
     a cache that is the offline-first strategy, an event store that keeps analytics off
     the primary. Record it on the store itself — not generalised up from a collection's
     `purpose`, and never in a `note`.
   - `satisfies_nfr` sits at BOTH levels and they mean different things. On the store, it
     names the goals the store's *choice* delivers — picking PostgreSQL over browser
     storage is what makes a durability goal achievable, and no single collection owns
     that. On a collection, it names the goals that collection's *physical* realisation
     delivers — an HNSW index is what makes a latency goal achievable. Tag each goal at the
     level that actually delivers it; do not repeat a store-level goal on every collection
     under it.
   - Tag every collection with the `serves_features` it exists for, and give the store any
     `satisfies_nfr` its choice is what makes achievable — persistence, latency, offline
     capability, live update.
   - `entities` names the domain entities a collection holds, and some collections hold
     none: an audit trail, an event log, a derived index. Those take `purpose` — one line
     saying what the collection is for — and an empty `entities`. Never describe the
     collection inside `entities`; that field is a list of entity names, and a sentence
     there is not an entity.
   - A store or a collection that is not part of the MVP carries `status` — `"optional"` or
     `"deferred"` — exactly as a library does. A cache recommended "for MVP performance, but
     optional" and recorded with collections, keys and TTLs and no `status` is a cache the
     planner will build.
   - When the AI features spec lists a required substrate that IS a store — a vector index
     above all — decide it HERE, not in `infrastructure`, and you MUST name the substrate in
     that store's `satisfies_infra`. That tag is the ONLY record that the catalog's
     requirement was met; a store that fills a required substrate and omits the tag loses
     the requirement from the plan entirely. The store's `choice` must also name the
     capability that does it — "PostgreSQL 16 + pgvector", not "PostgreSQL 16" — or a reader
     cannot tell the substrate is there. One physical store may fill several roles: pgvector
     holding both the domain data and the vector index is ONE entry with
     `satisfies_infra: ["vector_index"]`, not two.
   - The client library for a store (an ORM, a driver, a vector client) belongs in
     `libraries` with the store's `serves_features`; this block records the store decision,
     not the dependency.
7. **Infrastructure** — Cover this topic whenever the AI features spec lists required
   infrastructure (its "Required infrastructure" section). If none is listed, SKIP this
   topic entirely and do not add an `infrastructure` block. When it applies, the catalog
   has already determined which substrate each in-use tier requires (an agent loop runtime,
   a tool-execution harness, an embedding pipeline, a vector index, and so on). Walk each
   listed substrate one at a time to a concrete named choice:
   - **Every substrate the spec lists must end up recorded — no exceptions.** Each one is
     recorded in exactly one of two places: in `persistence` if it IS a store (a vector
     index above all), named in that store's `satisfies_infra`; otherwise in the
     `infrastructure` block, keyed by the substrate name. A substrate recorded in
     `persistence` is not repeated here. Nothing else is omitted, for any reason.
   - **"It is already handled by a library" is NOT a reason to omit it.** Most substrates
     are filled by something chosen under Libraries — an embedding pipeline by an
     embeddings library, a tool-execution harness by an agent framework, an agent loop
     runtime by that framework's executor. The `infrastructure` entry is what records WHICH
     choice fills the substrate role the catalog required; drop it and the requirement
     becomes untraceable. Write the entry and name that library in its `choice`. Keep
     `choice` to the choice itself — "sentence-transformers, in-process at index time" —
     and put the rationale, the substrate role it fills, and anything else a reader needs
     in `purpose`. The entry and the library listing are both required — never either/or.
   - For each substrate, present concrete product or approach options (for a tool-execution
     harness: a hand-rolled execute-and-loop in a service module vs. an agent framework)
     and recommend one, with trade-offs.
   - `serves_features` on an `infrastructure` entry names the **product feature ids** the
     substrate ultimately serves — never the substrate's own name, and never a capability id.
     The substrate is `embedding_pipeline`; the capability that needs it might be
     `recipe_embedding`; what it *serves* is a product feature like `recipe_search`. Those
     are three different names for three different things. Put the capability in
     `serves_capabilities` and the product feature in `serves_features`, reading the serves
     relation out of the AI features spec. The temptation is strongest here, because the
     substrate key and the capability are named so alike; an entry with no product feature
     id is attributable to no feature at all.
   - **Read the list back before you finalise.** For every item in the spec's Required
     infrastructure section, confirm it appears either as a key in `infrastructure` or in
     some store's `satisfies_infra`. An item in neither is a defect, and an empty
     `infrastructure` block when the spec listed non-store substrate is always wrong.
8. **Coding style and tooling** — Once language(s) are confirmed, settle the toolchain\
   and conventions **for each language separately** — Ruff exists only for Python, and\
   4-vs-2-space indentation is decided per language. Cover, per language:
   - **Linter** — present the leading options for the chosen language(s) and recommend\
     one, explaining the trade-offs
   - **Formatter** — present the leading auto-formatters and recommend one
   - **Key style rules** — indentation, line length, quote style, and language-specific\
     conventions (e.g., trailing commas, semicolons)
   - **Naming conventions** — for variables, functions, classes, constants, and file\
     names
   - **Type checking** — if applicable, whether strict type checking will be used (e.g.,\
     TypeScript strict mode, Python mypy/pyright)
   - **Code patterns** — OO vs. functional, key design principles (e.g., dependency\
     injection, functional core/imperative shell)

   Everything above is **language-indexed**: record it on that language's entry in the\
   `languages` array (`linter`, `formatter`, `type_checker`, `indentation`, `line_length`,\
   `quotes`, `semicolons`, `trailing_commas`, `naming_conventions`). Never prefix a field\
   with a language or tier name (`backend_linter`, `frontend_linter`) and never make a\
   field a language map (`"indentation": {"python": ...}`) — the array already carries one\
   entry per language, so those shapes duplicate the index and break the join.

   The `coding_style` block holds only what is **not** language-indexed: `patterns` (the\
   architectural principles — dependency injection, functional core / imperative shell)\
   and `documentation` (docstring and comment conventions). Both are flat lists of\
   strings; a rule that applies to one language only just says so in the string.

   Also settle the **project structure** — the directories the coding agent will create\
   and what belongs in each — and record it in the top-level `project_structure` array as\
   `{path, purpose}` entries. Cover every deployment target. This is not decoration: the\
   planner writes these paths into the instructions the coding agent follows, so a vague\
   or missing structure leaves it inventing its own.

   Treat coding style as a first-class part of the stack. The goal is precise enough that\
   an AI coding agent can follow it with no ambiguity.

**Brownfield conflict guidance**

When a code review is provided, proactively warn the user about any conflict between the \
existing technologies and any option you or the user propose. For each conflict, explain \
the implications (migration effort, incompatibility risks) and offer three concrete \
resolution options: keep the existing tech, migrate to the new choice, or a hybrid \
approach.

**Interaction rules**

- One topic per response — never ask about two parts of the project simultaneously.
- For each question, offer numbered options. Always include an option for the user to\
  suggest their own. When the user proposes their own option, evaluate its strengths and\
  weaknesses and ask them to confirm before proceeding.
- Never offer more than one set of numbered options in a single response.
- When options are mutually exclusive, say "pick one." When multiple can be combined,\
  say "you can pick one or more."
- Confirmation questions (yes/no): never phrase as "X or Y?" — ask directly. End with\
  "(yes/no — you're also welcome to ask questions or share comments either way)".
- Single-select lists: end with "Please select an option (answer with number and/or\
  optional comments)".
- Multi-select lists: end with "(answer with number(s) and/or optional comments)".
- After each confirmed answer, briefly recap the decisions made so far.
- Do not write code or code examples.

**Technical references**

Whenever the user, vision, or discussion mentions a technical standard, specification, \
protocol, API, or SDK (for example "the MCP protocol", "the OpenAI API", "OAuth 2.0"), \
use the web_search tool to find the canonical documentation URL. Present your findings \
and ask the user to confirm you have identified the correct standard. Once confirmed, \
add the standard and its canonical URL to the `references` array in the stack spec JSON. \
If a reference cannot be confirmed via web search or is specific to the user's project, \
label it as "unique to this project" rather than guessing. Every technical standard, \
specification, protocol, API, or SDK mentioned in the stack spec must appear in \
`references`.

**Anything that does not fit** — The blocks above cover the decisions this conversation is \
built to make. If the user settles something real that genuinely belongs in none of them, \
record it in `additional_decisions` as `{name, description, value}`, where `description` \
says what the field means in one line. Use this **rarely and only as a last resort**: it is \
for small residue like a commit-message convention or a changelog format. Anything the \
coding agent must act on — a language, a target, a library, a store, a path, a style rule — \
has a block above and belongs in it. If you find yourself reaching for \
`additional_decisions` for something load-bearing, you have picked the wrong block. Never \
invent a top-level key, and never invent a field inside a block to carry something the \
block does not already name; use the block's own fields, or this array.

`note` is the field that invention most often becomes, and it is not a field. Every `note` \
a draw has produced was already sayable in a field that exists: an entry that is not in the \
MVP is `status`; why a library is here is `purpose`; a fallback provider's scope is `role` \
on its capabilities plus the *condition* in the primary's `fallback` string; what a store \
or target is for is its `purpose`. A `note` that restates one of those adds nothing, and a \
`note` that carries something none of them do has hidden a decision in prose the planner \
reads as commentary. If a `note` is the only place a decision would fit, the decision \
belongs in a named field and you have picked the wrong one.

**Completing the stack spec**

After all applicable topics are confirmed, ask: "Does this cover everything, or would \
you like to revisit any section?" When the user confirms the stack spec is complete, \
output ONLY a fenced JSON code block. Include only what the user has explicitly \
confirmed — do not add choices the user has not made. Give the spec a one-line \
`description` of what the application is. Validate that the JSON is \
complete and well-formed before outputting it.

**Feature linkage — two id spaces, two fields.** Spec4 has two distinct id spaces and they \
must never be mixed:
- `serves_features` takes **product feature ids from the feature specifications** ONLY — \
  `recipe_search`, `shopping_list`. Every MVP feature has one, AI-backed or not. This is the \
  join the downstream planner follows from a stack entry to the feature's phase.
- `serves_capabilities` takes **AI capability ids from the AI features spec** ONLY — \
  `recipe_embedding`, `thread_sentiment_and_urgency_detection`. It records which capability an \
  entry was chosen for, at whatever granularity the catalog names it.

Never put a capability id in `serves_features`, and never put a product feature id in \
`serves_capabilities`. An entry may carry either, both, or neither. When an entry exists for a \
capability, give it both: `serves_capabilities` for the precision and `serves_features` for the \
join. **Read the capability's serves relation out of the AI features spec to find its product \
feature(s) — never guess it from the ids.** A capability id never equals the product feature id \
it serves, and the spec states the relation explicitly; an entry with `serves_capabilities` and \
no `serves_features` is attributable to no feature and drops out of the plan.

General-purpose stack staples (web framework, test runner, CSS framework, and the like) omit \
both — tag only entries whose reason for being is a specific feature or capability, so the \
linkage stays meaningful for the downstream planner. This applies to AI features at EVERY tier, \
including `deterministic` ones (a content-extraction library serving a deterministic extraction \
feature must be tagged too, not only libraries serving model-backed features) — and equally to \
features with no AI in them at all: a PDF library serving an export feature, or a persistence \
choice serving a saved-items feature, is tagged exactly the same way. Every feature with a \
dedicated serving library or substrate should be reachable through some entry's \
`serves_features`.

**Shared substrate** — Some entries are chosen for the application as a whole rather than for \
any particular feature, yet still carry real sequencing weight: a state-management library, an \
ORM, an HTTP client, a job queue. Do NOT enumerate every feature such an entry touches — an \
entry claiming most or all of the features is not attribution, it is noise, and it corrupts the \
planner's ability to tell which stack a feature actually needs. Instead mark it \
`"foundational": true` and omit `serves_features`. Apply this test rather than appearance: **if \
every feature that uses it were cut from the MVP, would you still choose this entry?** Still yes \
→ `foundational` (the UI framework, type system, test runner, linter, formatter, and error \
tracking all survive the loss of any feature — you would pick them for an empty app of this \
shape). It would go too → `serves_features`, naming exactly the features that keep it alive, \
even when there are several. Do not be misled by how infrastructural a choice *looks*: a \
storage, cache, or persistence layer reads like substrate while often existing solely so two \
named features survive a restart — cut those two features and the choice goes with them, so it \
is `serves_features`, not `foundational`. An entry is never both. `foundational` tells the \
planner this is shared substrate that must land where every consumer can reach it — the same \
treatment infrastructure nodes get — rather than inside one feature's phase.

**Check the linkage both ways before you finalise.** Read the feature specifications back and, \
for each feature, name the entry that serves it. A feature whose persistence, whose client, or \
whose dedicated library has all been filed under `foundational` is left with nothing to point \
at, and the planner cannot tell what to build in its phase — that is misfiled substrate, not a \
feature that happens to need no stack. Move the entry that exists for that feature back to \
`serves_features`. A feature genuinely built from nothing but shared substrate and application \
logic may legitimately have no entry; a feature with a dedicated store, client, or library must \
reach it.

When the AI features spec marks a capability as `cross_feature` (it spans more than one product \
feature), name it in `serves_capabilities` and list **every** product feature it serves in \
`serves_features`, reading them from the capability's serves relation in the spec. The two \
fields hold different id spaces, so there is no case in which a capability id substitutes for a \
product feature id.

**NFR linkage** — The feature specifications include project-wide non-functional goals, each \
with a stable `nfr_<slug>` id. When a stack decision is specifically what makes one of those \
goals achievable — a persistence choice for a durability goal, a caching or indexing choice \
for a latency goal, a service-worker/offline choice for an availability goal, a provider or \
region for an isolation goal — record the matching id(s) in that entry's `satisfies_nfr` array \
(on the library, infrastructure, or provider entry). **Every id you write MUST be copied \
from this project's own feature specifications.** The ids in the schema example belong to \
the example's project and exist in no other; writing one here claims a goal this project \
never set, and the planner resolves it to nothing. If no goal in the specs matches the \
decision you are tagging, the right answer is no `satisfies_nfr` at all — never an id that \
sounds right. This is orthogonal to `serves_features` \
(which feature the entry serves) and applies to non-AI stacks too. Tag only the decision(s) \
that materially deliver the goal, not every entry; a goal met purely in application logic with \
no dedicated stack lever may go untagged. If a goal clearly needs a stack lever the current \
choices do not provide (e.g. durable persistence for a "data persists across restarts" goal), \
surface that decision as a real entry rather than leaving it implicit, so the goal is \
satisfiable and taggable. This lets the downstream planner thread each goal into the phase \
that builds the capability that satisfies it.

**Prompt versioning** — When the AI features spec includes a prompt-versioning \
recommendation (present only when prompt-bearing model features exist), decide a concrete \
approach and record it in an `ai_conventions.prompt_versioning` string — for example, \
prompts stored as versioned files in-repo with semantic-version tags and a thin loader, or \
a prompt-management tool if one is genuinely warranted. Omit `ai_conventions` entirely when \
the spec carries no such recommendation.

Here is an example (omit fields not applicable to the project):

```json
{
  "stack_spec": {
    "name": "BiteGuide",
    "description": "A web app that turns saved recipe links into a shoppable weekly meal plan.",
    "languages": [
      {
        "name": "Python",
        "version": "3.12",
        "role": "backend service and data layer",
        "linter": "Ruff",
        "formatter": "Ruff format",
        "type_checker": "mypy (strict)",
        "indentation": "4 spaces",
        "line_length": 88,
        "quotes": "double",
        "trailing_commas": "in multi-line expressions",
        "naming_conventions": {"variables": "snake_case", "functions": "snake_case", "classes": "PascalCase", "constants": "UPPER_SNAKE_CASE", "files": "snake_case"}
      },
      {
        "name": "TypeScript",
        "version": "5.4",
        "role": "browser client",
        "linter": "ESLint + @typescript-eslint",
        "formatter": "Prettier",
        "type_checker": "tsc --strict",
        "indentation": "2 spaces",
        "line_length": 100,
        "quotes": "double",
        "semicolons": "yes",
        "trailing_commas": "in multi-line structures",
        "naming_conventions": {"variables": "camelCase", "functions": "camelCase", "components": "PascalCase", "constants": "UPPER_SNAKE_CASE", "files": "kebab-case, PascalCase for components"}
      }
    ],
    "deployment": {
      "targets": [
        {"name": "web_client", "kind": "spa", "purpose": "the browser UI people use to browse, search, and plan recipes", "language": "TypeScript", "hosting": "static hosting behind a managed CDN", "build": "vite build, emitting a hashed static bundle", "distribution": "served at the app's root domain"},
        {"name": "api", "kind": "rest_api", "purpose": "serves the client and runs recipe capture, search, and list building", "language": "Python", "runtime": "Python 3.12 on a managed container host", "hosting": "Cloud-hosted (AWS)", "api_contract": "REST; OpenAPI 3.1 generated from the app and published to the client", "build": "container image built from the repo Dockerfile", "exposure": {"transport": "HTTPS only", "cors": "allow only the app's own web origin"}}
      ]
    },
    "providers": {
      "OpenAI": {
        "capabilities": [
          {"tier": "single_call", "capability_class": "a fast, low-cost model for short structured extraction", "role": "primary"},
          {"tier": "rag", "capability_class": "a capable general model for grounded answers", "role": "primary", "serves_features": ["recipe_search"], "serves_capabilities": ["recipe_grounded_answer"]}
        ],
        "model_family": "GPT",
        "credentials_env": "OPENAI_API_KEY",
        "fallback": "a locally-served model via Ollama if OpenAI is unavailable"
      },
      "Ollama (self-hosted)": {
        "capabilities": [
          {"tier": "single_call", "capability_class": "a small local model for offline structured extraction", "role": "fallback", "satisfies_nfr": ["nfr_recipe_lookup_keeps_working_without_a_network_connection_"]}
        ],
        "model_family": "Llama",
        "endpoint_env": "OLLAMA_HOST",
        "credentials_env": "none — local endpoint"
      }
    },
    "integrations": [
      {"name": "Kroger Product API", "kind": "third_party_api", "purpose": "resolve shopping-list items to purchasable products and current prices", "protocol": "REST over HTTPS", "auth": "OAuth 2.0 client credentials; KROGER_CLIENT_ID / KROGER_CLIENT_SECRET", "serves_features": ["shopping_list"]}
    ],
    "security": {
      "auth": [
        {"mechanism": "session cookie (signed, http-only)", "purpose": "authenticate a returning cook so their saved lists and shopping lists are their own", "serves_features": ["shopping_list"], "credentials_env": "SESSION_SIGNING_KEY"}
      ]
    },
    "persistence": {
      "primary_store": {
        "choice": "PostgreSQL 16 + pgvector (managed, single instance)",
        "durability": "source of truth; survives restarts and redeploys, nightly snapshots",
        "satisfies_nfr": ["nfr_a_saved_recipe_is_never_lost_between_sessions_"],
        "satisfies_infra": ["vector_index"],
        "collections": [
          {"name": "recipes", "entities": ["Recipe"], "physical": ["id (primary)", "index on author_id"], "serves_features": ["recipe_browse", "recipe_search"]},
          {"name": "recipe_embeddings", "entities": ["Recipe"], "physical": ["vector(768) column, HNSW index"], "serves_features": ["recipe_search"], "serves_capabilities": ["recipe_embedding"], "satisfies_nfr": ["nfr_recipe_search_returns_results_in_under_a_second_"]},
          {"name": "shopping_lists", "entities": ["ShoppingList"], "physical": ["id (primary)"], "serves_features": ["shopping_list"]},
          {"name": "recipe_search_events", "entities": [], "purpose": "search-quality analytics; an event log, not a domain entity", "physical": ["id (primary)", "index on searched_at"], "serves_features": ["recipe_search"], "status": "deferred"}
        ]
      },
      "search_cache": {
        "choice": "Redis (managed)",
        "purpose": "keeps repeat recipe searches fast without touching the primary store",
        "status": "optional",
        "durability": "derived — rebuildable from primary_store, not a source of truth",
        "collections": [
          {"name": "recent_searches", "entities": ["Recipe"], "serves_features": ["recipe_search"]}
        ]
      },
      "bundled_assets": {
        "choice": "unit-conversion table shipped as a JSON asset at build time",
        "durability": "read-only; changes only by redeploy",
        "collections": [
          {"name": "unit_conversions", "entities": ["IngredientUnitConversion"], "serves_features": ["ingredient_capture"]}
        ]
      }
    },
    "infrastructure": {
      "embedding_pipeline": {"choice": "sentence-transformers, in-process at index time", "purpose": "records which choice fills the catalog's embedding_pipeline substrate; the package itself is listed under libraries", "serves_features": ["recipe_search"], "serves_capabilities": ["recipe_embedding"], "satisfies_nfr": ["nfr_recipe_search_returns_results_in_under_a_second_"]}
    },
    "ai_conventions": {"prompt_versioning": "prompts stored as versioned files under prompts/ with semver tags, loaded by a thin resolver; no external registry"},
    "libraries": [
      {"name": "FastAPI", "purpose": "REST API framework", "category": "web framework", "language": "Python", "foundational": true},
      {"name": "SQLAlchemy", "purpose": "Database ORM (app-wide persistence layer)", "category": "orm", "language": "Python", "foundational": true, "satisfies_nfr": ["nfr_a_saved_recipe_is_never_lost_between_sessions_"]},
      {"name": "Pydantic", "purpose": "Data validation", "category": "validation", "language": "Python", "foundational": true},
      {"name": "structlog", "purpose": "Structured JSON logging for app and model calls", "category": "logging and observability", "language": "Python", "foundational": true},
      {"name": "qdrant-client", "purpose": "Vector store client", "category": "database client", "language": "Python", "serves_features": ["recipe_search"]},
      {"name": "sentence-transformers", "purpose": "In-process embedding generation", "category": "ai", "language": "Python", "serves_features": ["recipe_search"], "serves_capabilities": ["recipe_embedding"]},
      {"name": "Trafilatura", "purpose": "Article/content extraction (deterministic feature)", "category": "parsing", "language": "Python", "serves_features": ["ingredient_capture"]},
      {"name": "Playwright", "purpose": "End-to-end browser tests of the recipe-import flow", "category": "testing", "language": "TypeScript", "status": "deferred"},
      {"name": "pytest", "purpose": "Test runner", "category": "testing", "language": "Python", "foundational": true},
      {"name": "React", "purpose": "UI framework", "category": "ui framework", "language": "TypeScript", "foundational": true},
      {"name": "Axios", "purpose": "HTTP client", "category": "http client", "language": "TypeScript", "foundational": true},
      {"name": "Vitest", "purpose": "Test runner", "category": "testing", "language": "TypeScript", "foundational": true}
    ],
    "project_structure": [
      {"path": "backend/biteguide/api/", "purpose": "FastAPI routers, one module per resource"},
      {"path": "backend/biteguide/services/", "purpose": "stateless business logic — the functional core"},
      {"path": "backend/biteguide/db/", "purpose": "SQLAlchemy models, session factory, and Alembic migrations"},
      {"path": "backend/tests/", "purpose": "pytest suites mirroring the package layout"},
      {"path": "frontend/src/components/", "purpose": "React components"},
      {"path": "frontend/src/api/", "purpose": "typed API client generated from the published OpenAPI schema"}
    ],
    "coding_style": {"patterns": ["dependency injection", "functional core / imperative shell", "React: function components and hooks only, no class components"], "documentation": ["Google-style docstrings on every public Python function", "JSDoc on every exported TypeScript function"]},
    "additional_decisions": [
      {"name": "commit_message_format", "description": "The convention commit messages follow in this repo.", "value": "Conventional Commits"}
    ],
    "references": [
      {"standard": "OpenAI API", "url": "https://platform.openai.com/docs/api-reference"}
    ]
  }
}
```

Output only the JSON code block when generating the final stack spec — no additional \
text after it.
"""


def revision_delta(vision: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return this round's revision delta, or ``None`` for a greenfield vision.

    A revision round's vision carries an accumulating ``revision_history`` (each
    round contributes one entry, stamped deterministically by Brainstormer); its
    final entry is the delta for the current round — ``goal``, the
    ``key_features_mvp`` name changes (``added`` / ``modified`` / ``removed``),
    and ``rationale``. A greenfield vision has no ``revision_history``. The input
    is the session-form vision envelope (``{"vision_statement": {...}}``); a
    non-enveloped or greenfield vision yields ``None`` (not revision mode).
    """
    vs = (vision or {}).get("vision_statement") if isinstance(vision, dict) else None
    history = vs.get("revision_history") if isinstance(vs, dict) else None
    if isinstance(history, list) and history:
        last = history[-1]
        return last if isinstance(last, dict) else None
    return None


def build_revision_note(delta: dict[str, Any]) -> str:
    """Render a revision delta into a stack-scoping note for the revision seed.

    Produces a single bracketed instruction (same shape as the staleness note)
    that scopes the stack recommendation to this revision's ``key_features_mvp``
    changes while preserving the established stack. Deterministic — the
    ``added`` / ``modified`` / ``removed`` names come straight from the
    Brainstormer-stamped delta; the model never authors them.
    """
    changes = delta.get("changes") or {}
    added = list(changes.get("added") or [])
    modified = list(changes.get("modified") or [])
    removed = list(changes.get("removed") or [])
    goal = (delta.get("goal") or "").strip()

    segments: list[str] = ["[This is a stack revision of the established stack."]
    if goal:
        segments.append(f" Goal: {goal}")
    clauses: list[str] = []
    if added:
        clauses.append("added features (" + ", ".join(added) + ")")
    if modified:
        clauses.append("changed features (" + ", ".join(modified) + ")")
    if removed:
        clauses.append("removed features (" + ", ".join(removed) + ")")
    if clauses:
        segments.append(
            " Recommend only the incremental stack changes this revision's "
            + "; ".join(clauses) + " require."
        )
    segments.append(
        " Preserve the established stack — languages, deployment, and every "
        "library these changes do not touch. Add or change only what these "
        "feature updates require.]"
    )
    return "".join(segments)


def _keyed_from_list(
    items: list[Any], *, name_fields: tuple[str, ...], prefix: str
) -> dict[str, Any]:
    """Key a list of entry dicts by their own name field, else by position."""
    out: dict[str, Any] = {}
    for i, item in enumerate(items):
        key = None
        if isinstance(item, dict):
            for field in name_fields:
                val = item.get(field)
                if isinstance(val, str) and val.strip():
                    key = val.strip()
                    break
        if key is None:
            key = f"{prefix}_{i + 1}"
        while key in out:
            key += "_"
        out[key] = item
    return out


def _normalise_stack_shape(spec: dict[str, Any]) -> dict[str, Any]:
    """Coerce the top-level blocks to the shape their consumers walk (D-SC18b).

    The renderer is total (D-SC33), so a deviant shape is no longer a crash or a
    silent drop. This pass exists for the *joins*: Phaser and the probes key over
    these blocks, and one shape per block is what lets them do that without a
    per-consumer guess.

    ``libraries`` is a flat list of entries carrying ``category`` and ``language``
    as values (D-SC27), so a category-keyed object folds down into it — the key
    becomes the entry's ``category``. That is the reverse of the pre-D-SC27
    coercion, which flattened a bare list into ``{"all": [...]}``; FareBox had in
    fact emitted the list shape the schema now asks for.
    """
    ss = spec.get("stack_spec") or spec.get("stack") or spec
    if not isinstance(ss, dict):
        return spec

    libs = ss.get("libraries")
    if isinstance(libs, dict):
        flat: list[Any] = []
        for category, entries in libs.items():
            for entry in entries if isinstance(entries, list) else [entries]:
                if isinstance(entry, dict):
                    entry.setdefault("category", category)
                    flat.append(entry)
                else:
                    flat.append({"name": str(entry), "category": category})
        ss["libraries"] = flat

    for block in ("integrations", "project_structure", "additional_decisions"):
        val = ss.get(block)
        if isinstance(val, dict):
            ss[block] = [
                {"name": k, **v} if isinstance(v, dict) else {"name": k, "value": v}
                for k, v in val.items()
            ]

    for block, prefix in (
        ("providers", "provider"),
        ("infrastructure", "component"),
        ("persistence", "store"),
    ):
        val = ss.get(block)
        if isinstance(val, list):
            ss[block] = _keyed_from_list(
                val,
                name_fields=("name", "store", "provider", "component", "choice"),
                prefix=prefix,
            )

    conv = ss.get("ai_conventions")
    if isinstance(conv, list):
        ss["ai_conventions"] = _keyed_from_list(
            conv, name_fields=("name", "convention"), prefix="convention"
        )
    return spec


def _extract_stack_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON stack spec from a fenced code block in the LLM response."""
    data = _extract_json_block(text)
    if data is None:
        return None
    if "stack" not in data and "stack_spec" not in data:
        return None
    return _normalise_stack_shape(data)


def _as_list(value: Any) -> list[Any]:
    """Coerce a leaf that should be a list into one (D-SC51).

    D-SC33 made the renderer total, which closed the DROP path: a field the
    renderer does not know about now reaches the page instead of vanishing. It did
    not close the GARBLE path. Every bespoke join site iterates its argument, and a
    string is iterable one character at a time — so ``entities: "Policy change
    history"`` rendered as ``holds P, o, l, i, c, y,  , c, h, a, n, g, e...``.
    Three collections on one live Ragmeister draw.

    A garble is worse than a drop: actively misleading rather than merely absent,
    and it lands on the receipt, which is the developer's only view of what was
    actually persisted.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _as_ids(values: Any) -> str:
    """Render ids as code spans (D-SC21).

    ``nfr_<slug>`` keys carry leading and trailing underscores, which markdown
    reads as emphasis delimiters and consumes — the user saw `nfrfare_lookups...`
    where the artifact said `nfr_fare_lookups...`. A code span is inert.

    Coerces (D-SC51): a bare string here garbles into one code span per character.
    """
    return ", ".join(f"`{v}`" for v in _as_list(values))


def _scalar_text(value: Any) -> str:
    """One-line human form for a leaf value."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _label(key: Any) -> str:
    return str(key).replace("_", " ").strip().title()


_ID_KEYS = ("serves_features", "serves_capabilities", "satisfies_nfr", "satisfies_infra")

# Labels for the id arrays whose key name alone does not read as English.
_ID_LABELS = {
    "satisfies_nfr": "Satisfies",
    "satisfies_infra": "Satisfies required substrate",
}


def _render_any(label: str, value: Any, lines: list[str], indent: str = "") -> None:
    """Render an arbitrary value under ``label``, recursing into containers.

    The fall-through half of the total renderer (D-SC33). Every block hands the
    keys it did not consume to this function, so a field the schema never
    declared still reaches the page under a generic heading rather than being
    dropped. That inverts the old failure: guessing the schema wrong now costs
    cosmetics instead of invisibility.
    """
    if value is None or value == "" or value == [] or value == {}:
        return
    if isinstance(value, dict):
        lines.append(f"{indent}- {label}:")
        for k, v in value.items():
            _render_any(_label(k), v, lines, indent + "  ")
    elif isinstance(value, list):
        if all(isinstance(v, (str, int, float, bool)) for v in value):
            lines.append(f"{indent}- {label}: {', '.join(_scalar_text(v) for v in value)}")
        else:
            lines.append(f"{indent}- {label}:")
            for item in value:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("path") or item.get("standard")
                    head = _scalar_text(name) if name else "-"
                    lines.append(f"{indent}  - {head}")
                    _render_rest(item, {"name", "path", "standard"}, lines, indent + "    ")
                else:
                    _render_any("-", item, lines, indent + "  ")
    else:
        lines.append(f"{indent}- {label}: {_scalar_text(value)}")


def _render_rest(
    block: Any, handled: set[str], lines: list[str], indent: str = ""
) -> None:
    """Render every key of ``block`` that its own renderer did not consume."""
    if not isinstance(block, dict):
        if block not in (None, "", [], {}):
            _render_any("Value", block, lines, indent)
        return
    for key, value in block.items():
        if key in handled:
            continue
        if key in _ID_KEYS and isinstance(value, list) and value:
            lines.append(f"{indent}- {_ID_LABELS.get(key, _label(key))}: {_as_ids(value)}")
            continue
        _render_any(_label(key), value, lines, indent)


def _render_entry_links(entry: dict[str, Any], lines: list[str], indent: str) -> None:
    """Render the four id arrays every attributable entry may carry."""
    for key in _ID_KEYS:
        vals = entry.get(key) or []
        if vals:
            lines.append(f"{indent}- {_ID_LABELS.get(key, _label(key))}: {_as_ids(vals)}")


def _format_stack_as_text(stack: dict[str, Any]) -> str:
    ss: dict[str, Any] = stack.get("stack_spec") or stack.get("stack") or stack
    if not isinstance(ss, dict):
        return str(ss)
    lines: list[str] = []

    name = ss.get("name", "")
    lines.append(f"**Tech Stack: {name}**\n" if name else "**Tech Stack**\n")
    if ss.get("description"):
        lines.append(f"{ss['description']}\n")

    languages: Any = ss.get("languages") or []
    if languages:
        lines.append("**Languages:**")
        if all(isinstance(x, str) for x in languages):
            lines.append(f"- {', '.join(languages)}")
        else:
            for lang in languages:
                if not isinstance(lang, dict):
                    lines.append(f"- {_scalar_text(lang)}")
                    continue
                head = str(lang.get("name", "language"))
                if lang.get("version"):
                    head += f" {lang['version']}"
                if lang.get("role"):
                    head += f" — {lang['role']}"
                lines.append(f"- {head}")
                _render_rest(lang, {"name", "version", "role"}, lines, "  ")
        lines.append("")

    deployment: Any = ss.get("deployment") or {}
    if deployment:
        lines.append("**Deployment:**")
        targets = deployment.get("targets") if isinstance(deployment, dict) else None
        if isinstance(targets, list):
            for tgt in targets:
                if not isinstance(tgt, dict):
                    lines.append(f"- {_scalar_text(tgt)}")
                    continue
                head = str(tgt.get("name", "target"))
                if tgt.get("kind"):
                    head += f" ({tgt['kind']})"
                lines.append(f"- {head}")
                _render_rest(tgt, {"name", "kind"}, lines, "  ")
        _render_rest(deployment, {"targets"}, lines)
        lines.append("")

    providers: Any = ss.get("providers") or {}
    if providers:
        lines.append("**Providers:**")
        if not isinstance(providers, dict):
            _render_any("Providers", providers, lines)
            providers = {}
        for prov_name, prov in providers.items():
            if not isinstance(prov, dict):
                lines.append(f"- {prov_name}: {_scalar_text(prov)}")
                continue
            lines.append(f"- {prov_name}")
            caps = prov.get("capabilities")
            if isinstance(caps, list):
                for cap in caps:
                    if not isinstance(cap, dict):
                        lines.append(f"  - {_scalar_text(cap)}")
                        continue
                    head = str(cap.get("tier", "capability"))
                    if cap.get("capability_class"):
                        head += f": {cap['capability_class']}"
                    if cap.get("role"):
                        head += f" ({cap['role']})"
                    lines.append(f"  - {head}")
                    _render_rest(cap, {"tier", "capability_class", "role"}, lines, "    ")
            _render_rest(prov, {"capabilities"}, lines, "  ")
        lines.append("")

    integrations: Any = ss.get("integrations") or []
    if integrations:
        lines.append("**Integrations:**")
        for item in integrations if isinstance(integrations, list) else [integrations]:
            if not isinstance(item, dict):
                lines.append(f"- {_scalar_text(item)}")
                continue
            head = str(item.get("name", "integration"))
            if item.get("purpose"):
                head += f" — {item['purpose']}"
            lines.append(f"- {head}")
            _render_rest(item, {"name", "purpose"}, lines, "  ")
        lines.append("")

    libraries: Any = ss.get("libraries") or {}
    if libraries:
        lines.append("**Libraries:**")
        if isinstance(libraries, list):
            _render_library_entries(libraries, lines)
        elif isinstance(libraries, dict):
            for category, libs in libraries.items():
                lines.append(f"\n*{_label(category)}:*")
                if isinstance(libs, list):
                    _render_library_entries(libs, lines)
                else:
                    _render_any(_label(category), libs, lines)
        lines.append("")

    persistence: Any = ss.get("persistence") or {}
    if persistence:
        lines.append("**Data & persistence:**")
        if not isinstance(persistence, dict):
            _render_any("Persistence", persistence, lines)
            persistence = {}
        for store_name, store in persistence.items():
            if not isinstance(store, dict):
                lines.append(f"- {store_name}: {_scalar_text(store)}")
                continue
            choice = store.get("choice", "")
            lines.append(f"- {store_name} — {choice}" if choice else f"- {store_name}")
            if store.get("purpose"):
                lines.append(f"  - Purpose: {_scalar_text(store['purpose'])}")
            if store.get("durability"):
                lines.append(f"  - Durability: {store['durability']}")
            _render_entry_links(store, lines, "  ")
            collections = store.get("collections") or []
            if isinstance(collections, list):
                for col in collections:
                    if not isinstance(col, dict):
                        lines.append(f"  - {_scalar_text(col)}")
                        continue
                    bits = []
                    if col.get("entities"):
                        bits.append(
                            "holds "
                            + ", ".join(_scalar_text(e)
                                        for e in _as_list(col["entities"]))
                        )
                    if col.get("purpose"):
                        bits.append(_scalar_text(col["purpose"]))
                    if col.get("serves_features"):
                        bits.append(f"serves {_as_ids(col['serves_features'])}")
                    suffix = f" ({'; '.join(bits)})" if bits else ""
                    lines.append(f"  - {col.get('name', 'collection')}{suffix}")
                    _render_rest(
                        col,
                        {"name", "entities", "serves_features", "purpose"},
                        lines,
                        "    ",
                    )
            _render_rest(
                store,
                {"choice", "purpose", "durability", "collections", *_ID_KEYS},
                lines,
                "  ",
            )
        lines.append("")

    infrastructure: Any = ss.get("infrastructure") or {}
    if infrastructure:
        lines.append("**Infrastructure:**")
        if not isinstance(infrastructure, dict):
            _render_any("Infrastructure", infrastructure, lines)
            infrastructure = {}
        for comp, spec in infrastructure.items():
            if not isinstance(spec, dict):
                lines.append(f"- {comp}: {_scalar_text(spec)}")
                continue
            choice = spec.get("choice", "")
            lines.append(f"- {comp}: {choice}" if choice else f"- {comp}")
            _render_rest(spec, {"choice"}, lines, "  ")
        lines.append("")

    conventions: Any = ss.get("ai_conventions") or {}
    if conventions:
        lines.append("**AI conventions:**")
        if isinstance(conventions, dict):
            for conv_name, value in conventions.items():
                _render_any(_label(conv_name), value, lines)
        else:
            _render_any("AI Conventions", conventions, lines)
        lines.append("")

    structure: Any = ss.get("project_structure") or []
    if structure:
        lines.append("**Project structure:**")
        if isinstance(structure, list):
            for item in structure:
                if isinstance(item, dict):
                    path = item.get("path", "")
                    purpose = item.get("purpose", "")
                    lines.append(
                        f"- `{path}` — {purpose}" if purpose else f"- `{path}`"
                    )
                    _render_rest(item, {"path", "purpose"}, lines, "  ")
                else:
                    lines.append(f"- {_scalar_text(item)}")
        else:
            _render_any("Project Structure", structure, lines)
        lines.append("")

    style: Any = ss.get("coding_style") or {}
    if style:
        lines.append("**Coding Style:**")
        if isinstance(style, dict):
            _render_rest(style, set(), lines)
        else:
            _render_any("Coding Style", style, lines)
        lines.append("")

    extra: Any = ss.get("additional_decisions") or []
    if extra:
        lines.append("**Additional decisions:**")
        for item in extra if isinstance(extra, list) else [extra]:
            if isinstance(item, dict):
                head = str(item.get("name", "decision"))
                value = item.get("value")
                lines.append(
                    f"- {head}: {_scalar_text(value)}" if value is not None else f"- {head}"
                )
                if item.get("description"):
                    lines.append(f"  - {item['description']}")
                _render_rest(item, {"name", "value", "description"}, lines, "  ")
            else:
                lines.append(f"- {_scalar_text(item)}")
        lines.append("")

    _render_references(ss.get("references", []), lines)

    _render_rest(ss, _TOP_LEVEL_HANDLED, lines)

    lines.append(
        "---\n\n"
        "We've finished defining the tech stack, so now you're ready to move on to "
        "creating implementation phases for your coding agent. Please click on the "
        "**Continue to Phaser** button below."
    )
    return "\n".join(lines)


_TOP_LEVEL_HANDLED = {
    "name",
    "description",
    "languages",
    "deployment",
    "providers",
    "integrations",
    "libraries",
    "persistence",
    "infrastructure",
    "ai_conventions",
    "project_structure",
    "coding_style",
    "additional_decisions",
    "references",
}


def _render_library_entries(libs: list[Any], lines: list[str]) -> None:
    """Render a flat list of library entries (D-SC27)."""
    for lib in libs:
        if not isinstance(lib, dict):
            lines.append(f"- {_scalar_text(lib)}")
            continue
        lib_name = lib.get("name", "")
        purpose = lib.get("purpose", "")
        entry = f"- {lib_name} — {purpose}" if purpose else f"- {lib_name}"
        bits = []
        if lib.get("language"):
            bits.append(str(lib["language"]))
        if lib.get("category"):
            bits.append(str(lib["category"]))
        if bits:
            entry += f" [{', '.join(bits)}]"
        lines.append(entry)
        _render_rest(lib, {"name", "purpose", "language", "category"}, lines, "  ")


def run(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Stack Advisor — guides the user through technology stack selection.

    Yields text chunks consumed by streaming.start().
    Mutates `session` to track conversation state and stack output.
    """
    if "stack_advisor_messages" not in session:
        session["stack_advisor_messages"] = []

    messages = session["stack_advisor_messages"]
    user_input = _drop_orphan_or_route_to_fresh_start(messages, user_input)

    if user_input is None:
        if messages:
            stale_q = _maybe_inject_staleness_question(session, "stack_advisor", messages)
            if stale_q is not None:
                yield stale_q
                return
            if not _maybe_inject_resume_summary(
                session, "stack_advisor", messages, STATE_STACK_COMPLETE
            ):
                yield from _replay_last_assistant(messages)
                return
            # Resume summary injected — fall through to LLM call.
        else:
            # Seed with available context, then call LLM
            vision = session.get("vision_statement")
            stack = session.get("stack_statement")
            code_review = session.get("code_review")
            ai_features = session.get("ai_features")
            working_dir = session.get("working_dir")
            current_version = (
                project_manager.active_version(working_dir, session)
                if working_dir
                else None
            )
            ai_features_block = (
                _ai_features_for_stack(ai_features, current_version) + "\n"
                if ai_features else ""
            )
            feature_specs = session.get("feature_specs")
            spine_block = (
                _feature_specs_for_stack(feature_specs, ai_features) + "\n\n"
                if feature_specs else ""
            )

            design_dir = (
                project_manager.get_version_dir(working_dir, current_version)
                / "design"
                if working_dir
                else None
            )
            design_ctx = _design_manifest_for_stack(
                _load_design_manifest(design_dir)
            )
            design_block = f"{design_ctx}\n\n" if design_ctx else ""

            vision_block = (
                f"Here is my project vision statement:\n\n```json\n{json.dumps(vision, indent=2)}\n```\n\n"
                if vision
                else ""
            )
            code_review_block = (
                f"For context, here is a code review of the existing project:\n\n"
                f"```json\n{json.dumps(code_review, indent=2)}\n```\n\n"
                "Within the review, treat `runtime_versions`, `languages`, "
                "`frameworks`, `dependencies`, `protocols_implemented`, "
                "`build_system`, and `commands.deploy` as authoritative facts. "
                "`protocols_implemented` are industry standards already wired "
                "in — treat them as constraints when proposing changes. The "
                "`notes` block is typed observations — pay particular "
                "attention to `notes.change_risks` when proposing technology "
                "swaps.\n\n"
                "**Important:** If any stack choices proposed during our conversation conflict with "
                "the existing technologies above (different language, incompatible framework, etc.), "
                "proactively warn me about the conflict, explain the implications (migration effort, "
                "incompatibility risks), and offer concrete options: keep existing tech, migrate to "
                "new choice, or a hybrid approach.\n\n"
                if code_review
                else ""
            )

            prior_stack = (
                project_manager.load_prior_stack(working_dir)
                if working_dir
                else None
            )
            delta = revision_delta(vision)

            if stack:
                seed = (
                    f"{vision_block}"
                    f"{spine_block}"
                    f"{design_block}"
                    f"{code_review_block}"
                    f"{ai_features_block}"
                    f"I also have an existing stack spec:\n\n"
                    f"```json\n{json.dumps(stack, indent=2)}\n```\n\n"
                    "Please introduce yourself as StackAdvisor and briefly summarize the existing "
                    "stack spec. Then ask me: would I like to **continue refining this existing "
                    "stack**, or would I prefer to **start with a completely new stack** from "
                    "scratch? Wait for my answer before proceeding."
                )
            elif prior_stack is not None and delta is not None:
                # Revision mode: a previous version of this project has been
                # implemented. Carry the established stack forward as the
                # baseline and scope recommendations to this revision's vision
                # delta rather than re-deciding the whole stack from scratch.
                seed = (
                    f"{vision_block}"
                    f"{spine_block}"
                    f"{design_block}"
                    f"{code_review_block}"
                    f"{ai_features_block}"
                    "I am starting a REVISION round on an existing, already-implemented "
                    "version of this project. Operate in REVISION mode.\n\n"
                    "Here is the established stack spec from the previous implemented "
                    "version, to carry forward as the baseline:\n\n"
                    f"```json\n{json.dumps(prior_stack, indent=2)}\n```\n\n"
                    f"{build_revision_note(delta)}\n\n"
                    "Please introduce yourself as StackAdvisor, briefly confirm the "
                    "established stack you are carrying forward, then guide me through "
                    "only the incremental stack changes this revision's new or changed "
                    "features require. Do not re-decide the established stack or re-run "
                    "the full topic sequence."
                )
            elif code_review:
                seed = (
                    f"{vision_block}"
                    f"{spine_block}"
                    f"{design_block}"
                    f"{code_review_block}"
                    f"{ai_features_block}"
                    "Please introduce yourself as StackAdvisor. Briefly describe what you understand "
                    "about the project's existing technology from the code review, then offer me two "
                    "options: (1) you draft an initial stack spec based on what you found for me to "
                    "review and refine, or (2) we start fresh and you guide me through the usual "
                    "stack selection questions. Ask me which I'd prefer."
                )
            else:
                seed = (
                    f"{vision_block}"
                    f"{spine_block}"
                    f"{design_block}"
                    f"{ai_features_block}"
                    "Please introduce yourself as StackAdvisor, greet the user, and begin guiding "
                    "me through the technology stack selection."
                )

            messages.append({"role": "user", "content": seed})
    else:
        messages.append({"role": "user", "content": user_input})

    search_cfg = websearch.from_session(session)
    system = llm.build_system_prompt(SYSTEM_PROMPT, search_cfg)

    yield from _stream_suppressing_json(
        llm.stream_turn(
            system, messages, llm_config, search_cfg,
            agent_name="stack_advisor",
            session=session,
        ),
        session,
        reply_status="StackAdvisor is replying…",
        artifact_status=(
            "Drafting the stack specification — this can take a few minutes…"
        ),
    )

    raw_reply = _last_assistant_text(messages)
    stack_spec = _extract_stack_json(raw_reply)
    if stack_spec is None and _suppressed_as_artifact(raw_reply):
        # D-SA-P3 (the D-SC-P3 fix, applied here): `_extract_stack_json` returns
        # None both for "no JSON here, still conversing" and for "the artifact
        # block came back unreadable". The two look identical from here but are
        # not: a reply opening with a fence was suppressed on its way to the
        # screen, so the unreadable case ends the turn with an empty bubble, no
        # STACK_COMPLETE, and no stack.json — the developer sees the finalize
        # step do nothing at all. Re-ask once, and if that fails too, say so.
        correction = _artifact_reask_prompt("stack specification")
        yield from _reask_for_artifact(
            system=system,
            msgs=messages,
            llm_config=llm_config,
            search_config=search_cfg,
            agent_name="stack_advisor",
            correction=correction,
            status_line=_artifact_reask_status("stack specification"),
            session=session,
            seed=len(raw_reply),
        )
        stack_spec = _extract_stack_json(_last_assistant_text(messages))
        if stack_spec is None:
            _abandon_reask(
                messages,
                correction,
                _artifact_fallback("stack recommendation"),
                session,
            )
    if stack_spec:
        # D-SC18a: render BEFORE committing any session state. The COMPLETE flag
        # is the sole gate on save_stack (session.py), so setting it ahead of work
        # that can throw persists the output of a turn that crashed — a formatter
        # AttributeError on a schema-deviant `libraries` wrote a never-rendered
        # stack.json to disk, three attempts running, each looking like a failure
        # to the developer and a success to the pipeline.
        display = _format_stack_as_text(stack_spec)
        session["stack_advisor_state"] = STATE_STACK_COMPLETE
        session["stack_statement"] = stack_spec
        session["stack_advisor_stale_acknowledged"] = {}
        messages[-1]["content"] = display
        session["_display_override"] = display
        session["stack_advisor_artifact_msg_count"] = len(messages)
