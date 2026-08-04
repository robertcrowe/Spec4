"""D-SC9/10/11 — storage gets a topic and a slot.

Across five draws the storage decision landed in five different places: an
invented ``data_model`` block, nowhere at all, homeless behind a ``foundational``
ORM, smuggled into ``infrastructure.vector_index``, and finally PostgreSQL filed
as a *library* beside Fastify and Pino. Nothing in the schema said where data
lives, so whether the decision got made at all was a coin flip — and on a
model-agnostic product that spread is widest at the bottom of the model range,
which is exactly where it must not be.

* **D-SC9(a)** — a `Data and persistence` topic AND a `persistence` block. A slot
  with no topic gets filled incidentally; a topic with no slot gets discarded.
* **D-SC10(b)** — keyed by store, two levels (store -> collections), because one
  store can hold two collections serving two different features. A flat
  store-keyed block cannot say that without a blanket claim. `entities` joins
  Designer's vocabulary; `physical` is the realisation StackAdvisor owns.
* **D-SC11(c)** — the split is store-ness, not AI-ness. pgvector is the domain
  store AND the vector index; a domain/AI split would duplicate or arbitrarily
  assign it. Stores live in `persistence` with `satisfies_infra` naming the
  catalog requirement they meet; `infrastructure` keeps non-store AI substrate.
"""

from __future__ import annotations

import json
import re
from typing import Any

from spec4.agents.stack_advisor import (
    SYSTEM_PROMPT,
    _extract_stack_json,
    _format_stack_as_text,
    _normalise_stack_shape,
)


def _topics() -> list[str]:
    return re.findall(r"^(\d+)\. \*\*([^*]+)\*\*", SYSTEM_PROMPT, re.M)


# --- D-SC9(a): the topic exists, in order, and is never skipped -------------


def test_persistence_topic_exists_and_is_numbered_in_sequence() -> None:
    nums = [int(n) for n, _ in _topics()]
    assert nums == sorted(nums) and nums == list(range(1, len(nums) + 1))
    names = [t.strip() for _, t in _topics()]
    assert "Data and persistence" in names


def test_persistence_topic_sits_between_libraries_and_infrastructure() -> None:
    names = [t.strip() for _, t in _topics()]
    assert names.index("Libraries") < names.index("Data and persistence")
    assert names.index("Data and persistence") < names.index("Infrastructure")


def test_persistence_topic_is_not_ai_gated() -> None:
    """Infrastructure is gated on the AI catalog; persistence must never be."""
    body = SYSTEM_PROMPT.split("**Data and persistence**")[1].split(
        "**Infrastructure**"
    )[0]
    flat = " ".join(body.split())  # the prompt wraps; assertions must not care
    assert "EVERY project" in flat
    assert "never skip" in flat.lower()


def test_infrastructure_defers_stores_to_persistence() -> None:
    # D-SC22 reworded: the deferral is now scoped to stores and immediately
    # fenced, because "do not repeat" generalised and emptied the block.
    flat = _infra_topic()
    assert "satisfies_infra" in flat
    assert "recorded in `persistence` is not repeated here" in flat


# --- D-SC10(b): the exemplar anchors every field it wants used --------------
#
# A specified-but-unexemplified field is not reliably produced: `satisfies_nfr`
# is in the schema and still came back 0/5, while `foundational` (6 mentions)
# came back on 13 entries. So the block ships with worked examples, not a stub.


def _schema() -> dict[str, Any]:
    block = re.search(r"```json\n(\{.*?\n\})\n```", SYSTEM_PROMPT, re.S)
    assert block, "no JSON schema example in the prompt"
    return json.loads(block.group(1))


def _persistence() -> dict[str, Any]:
    ss = _schema().get("stack_spec") or _schema()
    return ss["persistence"]


def test_schema_example_has_a_persistence_block() -> None:
    assert _persistence()


def test_exemplar_shows_more_than_one_store() -> None:
    assert len(_persistence()) >= 2


def test_exemplar_shows_a_store_with_two_collections_serving_two_features() -> None:
    """The shape a flat store-keyed block could not express."""
    multi = [
        s for s in _persistence().values() if len(s.get("collections") or []) >= 2
    ]
    assert multi, "no multi-collection store in the exemplar"
    served = {
        f
        for col in multi[0]["collections"]
        for f in (col.get("serves_features") or [])
    }
    assert len(served) >= 2


def test_every_exemplar_collection_carries_serves_features() -> None:
    for store in _persistence().values():
        for col in store.get("collections") or []:
            assert col.get("serves_features"), col


def test_every_exemplar_collection_says_what_it_holds_or_what_it_is_for() -> None:
    """D-SC51(b) supersedes "every collection names its entities".

    That guard's premise -- every collection is an entity table -- is false, and a
    live Ragmeister draw is what disproved it: `policy_audit_log` and `inquiry_log`
    hold no domain entity, and with nowhere to put the description the model
    narrated *into* `entities` ("Policy change history"), which the renderer then
    iterated one character at a time onto the developer's receipt.

    So the rule is now the disjunction, and it is STRONGER rather than weaker: a
    collection must say what it holds (`entities`) or what it is for (`purpose`),
    and a collection with neither -- previously impossible to express and therefore
    never guarded -- now fails.
    """
    for store in _persistence().values():
        for col in store.get("collections") or []:
            assert col.get("entities") or col.get("purpose"), col


def test_at_least_one_exemplar_collection_holds_no_entity() -> None:
    """The entity-less case must be demonstrated, not merely permitted.

    D-SC50's law: the prose licenses `purpose` on an entity-less collection, and a
    field the exemplar withholds is a field the model does not write. Six instances
    and no counter-example.
    """
    entity_less = [
        col
        for store in _persistence().values()
        for col in store.get("collections") or []
        if not col.get("entities")
    ]
    assert entity_less, (
        "no exemplar collection demonstrates the entity-less shape (an audit "
        "trail, an event log, a derived index). Without one, the model has only "
        "entity-table collections to copy and will keep narrating into `entities`."
    )


def test_exemplar_anchors_satisfies_nfr_not_just_foundational() -> None:
    nfr = [
        col
        for store in _persistence().values()
        for col in (store.get("collections") or [])
        if col.get("satisfies_nfr")
    ]
    assert nfr, "satisfies_nfr must be exemplified, not merely specified"


def test_every_exemplar_store_states_durability() -> None:
    for name, store in _persistence().items():
        assert store.get("durability"), name


def test_exemplar_covers_a_bundled_read_only_asset() -> None:
    """FareBox's bundled fare table had no home and vanished from a draw."""
    joined = json.dumps(_persistence()).lower()
    assert "build time" in joined or "bundled" in joined


def test_exemplar_does_not_restate_entity_field_lists() -> None:
    """The data model is Designer's; only physical realisation is ours."""
    for store in _persistence().values():
        for col in store.get("collections") or []:
            assert "fields" not in col
            assert "schema" not in col


# --- D-SC11(c): store-ness, not AI-ness ------------------------------------


def test_vector_index_is_decided_in_persistence_not_infrastructure() -> None:
    ss = _schema().get("stack_spec") or _schema()
    assert "vector_index" not in (ss.get("infrastructure") or {})
    claimed = {
        role
        for store in ss["persistence"].values()
        for role in (store.get("satisfies_infra") or [])
    }
    assert "vector_index" in claimed


def test_infrastructure_keeps_non_store_substrate() -> None:
    ss = _schema().get("stack_spec") or _schema()
    assert "embedding_pipeline" in (ss.get("infrastructure") or {})


def test_prompt_names_the_co_located_store_case() -> None:
    """pgvector is one entry, not two — the case that killed the AI/domain split."""
    body = SYSTEM_PROMPT.split("**Data and persistence**")[1]
    assert "pgvector" in body


# --- rendering + shape resilience ------------------------------------------

_DRAW = {
    "stack_spec": {
        "name": "RecipeBox",
        "persistence": {
            "primary_store": {
                "choice": "PostgreSQL 16",
                "durability": "source of truth; survives restarts",
                "collections": [
                    {
                        "name": "recipes",
                        "entities": ["Recipe"],
                        "physical": ["id (primary)"],
                        "serves_features": ["recipe_browse"],
                        "satisfies_nfr": ["nfr_saved_data_persists"],
                    }
                ],
            },
            "vector_store": {
                "choice": "Qdrant",
                "durability": "derived",
                "satisfies_infra": ["vector_index"],
                "collections": [
                    {
                        "name": "recipe_embeddings",
                        "entities": ["Recipe"],
                        "serves_features": ["recipe_semantic_search"],
                    }
                ],
            },
        },
    }
}


def test_render_shows_stores_entities_and_served_features() -> None:
    out = _format_stack_as_text(_DRAW)
    assert "**Data & persistence:**" in out
    assert "primary_store — PostgreSQL 16" in out
    assert "holds Recipe" in out
    assert "serves `recipe_browse`" in out  # D-SC21: code span


def test_render_shows_durability_and_satisfied_substrate() -> None:
    out = _format_stack_as_text(_DRAW)
    assert "Durability: source of truth; survives restarts" in out
    assert "Satisfies required substrate: `vector_index`" in out  # D-SC21


def test_render_survives_a_persistence_block_of_junk() -> None:
    junk = {"stack_spec": {"persistence": {"s": {"collections": ["not a dict"]}}}}
    assert "**Data & persistence:**" in _format_stack_as_text(junk)


def test_render_omits_the_block_when_absent() -> None:
    assert "**Data & persistence:**" not in _format_stack_as_text(
        {"stack_spec": {"name": "X"}}
    )


def test_persistence_emitted_as_a_list_is_normalised(  # D-SC18b applies here too
) -> None:
    spec = {
        "stack_spec": {
            "persistence": [
                {"name": "primary_store", "choice": "PostgreSQL"},
                {"choice": "Qdrant"},
            ]
        }
    }
    out = _normalise_stack_shape(spec)["stack_spec"]["persistence"]
    assert list(out) == ["primary_store", "Qdrant"]


def test_extraction_normalises_persistence_end_to_end() -> None:
    payload = "```json\n" + json.dumps(
        {"stack_spec": {"persistence": [{"name": "s", "choice": "PostgreSQL"}]}}
    ) + "\n```"
    spec = _extract_stack_json(payload)
    assert spec is not None
    assert isinstance(spec["stack_spec"]["persistence"], dict)
    _format_stack_as_text(spec)  # must not raise


# --- D-SC22: the no-repeat clause must not eat substrate completeness --------
#
# D-SC9 shipped "Any required substrate that IS a store ... Do not repeat it
# here." On the Digger draw the model generalised "do not repeat" from *stores*
# to *anything already chosen elsewhere*: embedding_pipeline -> "already chosen
# under Libraries", tool_execution_harness -> likewise, then agent_loop_runtime
# and pipeline_runner -> "no new infrastructure". It emitted `infrastructure: {}`
# and no `satisfies_infra`, so all five catalog requirements — including the
# vector index that pre-D-SC9 draws recorded — vanished from the artifact Phaser
# is bound by. The rule against duplication ate the rule that matters.


def _infra_topic() -> str:
    body = SYSTEM_PROMPT.split("**Infrastructure**")[1].split("**Coding style")[0]
    return " ".join(body.split())


def _persistence_topic() -> str:
    body = SYSTEM_PROMPT.split("**Data and persistence**")[1].split(
        "**Infrastructure**"
    )[0]
    return " ".join(body.split())


def test_no_repeat_clause_is_scoped_to_stores_only() -> None:
    flat = _infra_topic()
    assert "not repeated here" in flat or "not be repeated here" in flat
    # ...and is immediately fenced so it cannot generalise
    assert "Nothing else is omitted, for any reason." in flat


def test_a_library_filled_substrate_still_needs_its_entry() -> None:
    flat = _infra_topic()
    assert "already handled by a library" in flat
    assert "NOT a reason to omit" in flat
    assert "never either/or" in flat


def test_infra_topic_demands_a_readback_of_the_required_list() -> None:
    flat = _infra_topic()
    assert "Read the list back" in flat
    assert "satisfies_infra" in flat


def test_empty_infrastructure_is_named_as_a_defect() -> None:
    assert "empty `infrastructure` block" in _infra_topic()


def test_infra_topic_is_no_longer_gated_on_non_store_substrate() -> None:
    """The gate is whether the spec lists infrastructure, not what kind."""
    assert "lists required infrastructure" in _infra_topic()
    assert "that is NOT a store" not in _infra_topic()


def test_satisfies_infra_is_mandatory_not_advisory() -> None:
    flat = _persistence_topic()
    assert "MUST name the substrate" in flat
    assert "ONLY record" in flat


def test_store_choice_must_name_the_capability_not_just_the_engine() -> None:
    """Digger emitted "PostgreSQL 16 (RDS managed)" — pgvector nowhere."""
    flat = _persistence_topic()
    assert 'PostgreSQL 16 + pgvector", not "PostgreSQL 16"' in flat


# --- D-SC22: the exemplar must anchor the co-located store ------------------


def test_exemplar_anchors_the_co_located_store() -> None:
    """Digger chose one store for both roles; the old exemplar showed two."""
    stores = _persistence()
    co = [
        s
        for s in stores.values()
        if s.get("satisfies_infra") and len(s.get("collections") or []) > 1
    ]
    assert co, "no co-located store (satisfies_infra + multiple collections)"
    assert "pgvector" in co[0]["choice"]


def test_exemplar_store_choice_names_the_vector_capability() -> None:
    claimer = next(
        s
        for s in _persistence().values()
        if "vector_index" in (s.get("satisfies_infra") or [])
    )
    assert "pgvector" in claimer["choice"]


def test_exemplar_infra_entry_points_at_its_library() -> None:
    """D-SC22's pointer survives; D-SC36 moved it from `choice` into `purpose`.

    `choice` carries the choice and nothing else now, so the note that the package
    is also listed under libraries — the thing that keeps the substrate traceable —
    lives in the field that exists for exactly that.
    """
    ss = _schema().get("stack_spec") or _schema()
    entry = ss["infrastructure"]["embedding_pipeline"]
    assert "libraries" in entry["purpose"]
    assert "libraries" not in entry["choice"]


# --- D-SC21: ids render as code spans ---------------------------------------


def test_served_feature_ids_render_as_code_spans() -> None:
    out = _format_stack_as_text(_DRAW)
    assert "serves `recipe_browse`" in out


def test_nfr_ids_render_as_code_spans() -> None:
    """Bare `nfr_..._` is eaten by markdown emphasis; the user saw a broken id."""
    out = _format_stack_as_text(_DRAW)
    assert "Satisfies: `nfr_saved_data_persists`" in out


def test_satisfied_substrate_renders_as_a_code_span() -> None:
    out = _format_stack_as_text(_DRAW)
    assert "Satisfies required substrate: `vector_index`" in out


# --- D-SC23: coding_style renders whatever shape the model nests it in -------
#
# A single-language project emits a flat block; a two-language one nests by tier.
# `_render_coding_style` probed only for flat keys, so Digger — which negotiated
# backend and frontend style across two turns — printed the heading and nothing.
# The JSON had it all; the developer saw an empty section, twice.

_FLAT_STYLE = {
    "stack_spec": {
        "coding_style": {
            "linter": "ESLint",
            "formatter": "Prettier",
            "indentation": "2 spaces",
            "naming_conventions": {"variables": "camelCase"},
            "patterns": ["Functional core / imperative shell"],
        }
    }
}

_NESTED_STYLE = {
    "stack_spec": {
        "coding_style": {
            "backend": {
                "language": "Python",
                "linter": "Ruff",
                "type_checker": "Pyright (strict)",
                "indentation": "4 spaces",
                "naming_conventions": {"variables": "snake_case"},
                "patterns": ["Dependency injection"],
            },
            "frontend": {
                "language": "TypeScript",
                "linter": "ESLint",
                # note: `type_checking`, not `type_checker` — the model uses both
                "type_checking": "TypeScript strict mode",
                "indentation": "2 spaces",
                "other_rules": ["No implicit any"],
            },
        }
    }
}


def test_flat_coding_style_still_renders() -> None:
    out = _format_stack_as_text(_FLAT_STYLE)
    assert "**Coding Style:**" in out
    assert "- Linter: ESLint" in out
    assert "- Naming Conventions:" in out
    assert "  - Variables: camelCase" in out


def test_nested_coding_style_renders_each_tier() -> None:
    out = _format_stack_as_text(_NESTED_STYLE)
    assert "- Backend:" in out
    assert "- Frontend:" in out


def test_nested_coding_style_renders_the_fields_under_each_tier() -> None:
    out = _format_stack_as_text(_NESTED_STYLE)
    assert "  - Linter: Ruff" in out
    assert "  - Type Checker: Pyright (strict)" in out
    assert "  - Naming Conventions:" in out
    assert "    - Variables: snake_case" in out
    assert "  - Patterns: Dependency injection" in out


def test_nested_coding_style_renders_both_type_check_spellings() -> None:
    """Digger's backend used `type_checker`; its frontend used `type_checking`."""
    out = _format_stack_as_text(_NESTED_STYLE)
    assert "Pyright (strict)" in out
    assert "TypeScript strict mode" in out


def test_nested_coding_style_survives_a_non_dict_tier() -> None:
    junk = {"stack_spec": {"coding_style": {"backend": "Ruff, 4 spaces"}}}
    out = _format_stack_as_text(junk)
    assert "- Backend: Ruff, 4 spaces" in out


def test_empty_coding_style_renders_no_heading() -> None:
    assert "**Coding Style:**" not in _format_stack_as_text(
        {"stack_spec": {"coding_style": {}}}
    )


# --- exemplar id-space: serves_features must model PRODUCT ids ---------------
#
# The exemplar tagged entries with `recipe_semantic_search` / `ingredient_extraction`
# — names that read as AI capabilities. Digger copied the style: 3 of 4 tagged
# entries came back carrying only capability ids (`data_source_relevance_ranking`,
# `contextual_follow_up_interpretation`), attributable to no product feature at all.


def test_exemplar_ids_do_not_read_as_ai_capabilities() -> None:
    served = {
        f
        for store in _persistence().values()
        for col in (store.get("collections") or [])
        for f in (col.get("serves_features") or [])
    }
    ss = _schema().get("stack_spec") or _schema()
    for entry in (ss.get("infrastructure") or {}).values():
        served.update(entry.get("serves_features") or [])
    for lib in ss.get("libraries") or []:
        served.update(lib.get("serves_features") or [])
    # capability-shaped names the model demonstrably copies
    banned = {"recipe_semantic_search", "ingredient_extraction"}
    assert not (served & banned), f"exemplar teaches capability ids: {served & banned}"


# --- exemplar hygiene: every id in the example must be un-copyable ------------

# BiteGuide's domain nouns. An id carrying one of these is obviously the
# example's and cannot be pasted into another project without looking wrong.
_EXEMPLAR_DOMAIN_TOKENS = ("recipe", "shopping", "ingredient", "unit", "meal")


def _exemplar_nfr_ids() -> set[str]:
    out: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "satisfies_nfr" and isinstance(value, list):
                    out.update(str(v) for v in value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(_schema())
    return out


def test_exemplar_nfr_ids_are_domain_loaded() -> None:
    """Exemplar nfr ids must name the example's domain, so they cannot be copied.

    A live Ragmeister draw tagged two entries with
    ``nfr_saved_data_persists_across_restarts`` -- an id belonging to no goal that
    project ever set. It is the exemplar's, and the draw carried it in exactly the
    two places the exemplar puts it, so the model copied the positions AND the
    value. A tag naming a goal the project never set resolves to nothing
    downstream, which is worse than no tag at all.

    Every other id class in the exemplar is already immune because it is
    domain-loaded: `recipe_search`, `recipe_embedding`, `Recipe`. Only the nfr ids
    were domain-neutral, and domain-neutral is exactly what makes an id look
    reusable. This is the same defect D-SC23 fixed for capability ids, one field
    over.
    """
    ids = _exemplar_nfr_ids()
    assert ids, "exemplar should demonstrate satisfies_nfr somewhere"
    for nfr_id in ids:
        assert any(tok in nfr_id.lower() for tok in _EXEMPLAR_DOMAIN_TOKENS), (
            f"exemplar nfr id {nfr_id!r} is domain-neutral, so it reads as reusable "
            f"and a draw will copy it into a project that never set that goal. "
            f"Name the example's domain in it (one of {_EXEMPLAR_DOMAIN_TOKENS})."
        )


def test_prompt_forbids_copying_nfr_ids_from_the_example() -> None:
    assert (
        "Every id you write MUST be copied from this project's own feature "
        "specifications." in SYSTEM_PROMPT
    )
    assert "never an id that sounds right" in SYSTEM_PROMPT


def test_every_exemplar_library_carries_a_purpose() -> None:
    """A bare library name reaches the planner with no reason for being.

    A Ragmeister draw gave 21 of 21 libraries no `purpose`: the D-SC27 sentence
    named only `category` and `language`, which read as the whole field set.
    """
    ss = _schema().get("stack_spec") or _schema()
    missing = [lib.get("name") for lib in ss["libraries"] if not lib.get("purpose")]
    assert not missing, f"exemplar libraries without a purpose: {missing}"


def test_prompt_requires_library_purpose() -> None:
    assert "`purpose` is not optional" in SYSTEM_PROMPT


def test_exemplar_demonstrates_serves_capabilities_on_a_capability() -> None:
    """The prose promises both link fields; the example must show both.

    Showing only `serves_features` is why a Ragmeister draw's
    `capabilities[].serves_capabilities` read as an invented key -- the model was
    right and the exemplar was incomplete. Prose licenses, exemplars teach.
    """
    ss = _schema().get("stack_spec") or _schema()
    caps = [
        cap
        for prov in ss["providers"].values()
        for cap in (prov.get("capabilities") or [])
    ]
    assert any(cap.get("serves_features") for cap in caps)
    assert any(cap.get("serves_capabilities") for cap in caps)


def test_infra_topic_forbids_capability_only_tagging() -> None:
    flat = _infra_topic()
    assert "never the substrate's own name" in flat
    assert "attributable to no feature at all" in flat
