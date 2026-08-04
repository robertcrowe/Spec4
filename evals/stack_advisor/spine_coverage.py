"""StackAdvisor spine-coverage probe (D-SC round: D-SC2 / D-SC3).

Measures the two *output-visible* levers of the StackAdvisor consumer round on a
produced ``stack.json`` — the changes that only become observable once the agent
consumes the Brainstormer ``feature_specs.json`` spine and the project-level
``nfr_goals``:

* D-SC3 full-spine ``serves_features`` — with the id spine, a component may now
  be attributed to ANY MVP feature id (AI-backed *or* non-AI), not only to an AI
  capability-surface id. The probe resolves every ``serves_features`` reference
  against the full id universe (feature_specs product ids ∪ AI-catalog surface
  ids) and reports how many references land on a *product* feature id
  (``product_serves_refs`` — the signal the lever moves), how many still cite a
  surface id only (the pre-lever lane), how many land on a *non-AI* feature
  specifically, plus any reference that resolves to no known id (a typo that would
  silently drop stack from a phase). "AI-backed" is derived from the serves
  relation (``vision_grounding.served_features``), never from node-id equality —
  a node's own id is a surface id and never equals the product id it serves.

* D-SC2 nfr → ``satisfies_nfr`` — each provider / infrastructure / library entry
  may record the project ``nfr_goal(s)`` it satisfies, keyed by ``nfr_<slug>`` so
  the reference survives paraphrase. The probe derives the same keys from
  ``feature_specs.nfr_goals`` and reports which goals are reached by ≥1 entry
  (the traceability Phaser threads into phase acceptance criteria) and any
  ``satisfies_nfr`` key that matches no goal.

* D-SC4 shared substrate — an entry chosen for the app as a whole (state manager,
  ORM, HTTP client) should carry ``foundational: true`` and omit
  ``serves_features``. The probe reports ``foundational_entries``,
  ``blanket_claim_entries`` (an entry naming every spine feature), and
  ``foundational_conflicts`` (both markers on one entry, which is never correct).

  D-SC16: claiming every feature is not itself the fault, and the original rule
  (claims-everything ⇒ should be foundational) could not tell over-claiming from
  legitimately universal service. On an all-AI spine the LLM SDK, the tracing lib
  and the agent runtime *do* serve every feature; the prompt's own counterfactual
  agrees — cut the AI features and none of them survive, so they are correctly not
  ``foundational``. Every over-attribution case on record (Zustand, Zod) was
  instead a *general staple* on a deterministic app. A counting heuristic cannot
  separate those; substrate-linkage can. So blanket claims are split into
  ``blanket_substrate_linked`` (in the AI-gated ``infrastructure`` block, or named
  for a selected provider — and only when every spine feature is AI-backed, since
  an AI library claiming a non-AI feature is over-claiming however AI it is) and
  ``blanket_unlinked`` (not derivably AI-specific — the band to read).
  ``coverage_excluding_unlinked_blanket`` discounts only the unlinked band;
  discounting a true universal manufactures a false negative, which is exactly
  what the Digger draw produced (2/3 reported where 3/3 was real).

This is the measure-before/after instrument for those two levers: run it on a
*pre-lever* draw to establish the baseline (expect ``non_ai_refs=0`` and
``nfr_coverage=0/K``), and on a post-implementation draw to confirm the levers
moved the metric. The landed D-SA probes (``output_baseline.py``,
``projection_baseline.py``) are unaffected and still measure the prior round.

Reads a draw directory holding ``stack.json`` (required), ``feature_specs.json``
(the id spine + ``nfr_goals``), and optionally ``ai_features.json`` (to split AI
vs non-AI ids). Run from ``evals/stack_advisor/`` so the src import resolves:

    cd evals/stack_advisor && python3 spine_coverage.py            # fixtures
    cd evals/stack_advisor && python3 spine_coverage.py <draw_dir> # real draw

Measurement tooling only — never wired into the pipeline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from spec4.agents._utils import slug

_INFRA_KIND = "infrastructure"


def _stack_spec(stack: dict[str, Any]) -> dict[str, Any]:
    return stack.get("stack_spec") or stack.get("stack") or stack


def _spine_ids(feature_specs: dict[str, Any] | None) -> set[str]:
    """All MVP feature ids from the Brainstormer spine (AI and non-AI)."""
    out: set[str] = set()
    for f in ((feature_specs or {}).get("features") or []):
        fid = f.get("id")
        if fid:
            out.add(str(fid))
    return out


def _ai_node_ids(catalog: dict[str, Any] | None) -> set[str]:
    """Non-infra AI-catalog *node* ids — capability-surface ids.

    These are the ids a stack entry may cite when it serves a specific AI
    capability surface (the catalog-node lane, D-SC4a). A node id is NEVER a
    product-feature id, so these count only toward reference *resolution*, never
    toward deciding which product features are AI-backed (see ``_ai_served_ids``).
    """
    out: set[str] = set()
    for f in ((catalog or {}).get("ai_features") or []):
        if f.get("kind") == _INFRA_KIND:
            continue
        for key in ("id", "name"):
            if f.get(key):
                out.add(str(f[key]))
    return out


def _ai_served_ids(catalog: dict[str, Any] | None) -> set[str]:
    """Product-feature ids that some AI node *serves* (vision_grounding).

    The serves relation — never identity: an AI node's own id is a capability
    surface id (``adaptive_investigation_orchestration``) distinct from the
    product-feature id it serves (``adaptive_investigation``). Deriving
    "AI-backed" from node ids would classify every spine feature as non-AI, since
    the two id spaces never intersect.
    """
    out: set[str] = set()
    for f in ((catalog or {}).get("ai_features") or []):
        if not isinstance(f, dict) or f.get("kind") == _INFRA_KIND:
            continue
        for sf in ((f.get("vision_grounding") or {}).get("served_features") or []):
            if isinstance(sf, dict):
                for key in ("id", "name"):
                    if sf.get(key):
                        out.add(str(sf[key]))
    return out


def _required_substrates(catalog: dict[str, Any] | None) -> list[str]:
    """Substrate ids the AI catalog requires — the ``kind: infrastructure`` nodes.

    These are what StackAdvisor's Infrastructure topic must walk to a concrete
    choice. ``infra_expander`` injects them deterministically per tier, so the list
    is authoritative: every id here has to be answered somewhere in the stack.
    """
    out: list[str] = []
    for f in ((catalog or {}).get("ai_features") or []):
        if isinstance(f, dict) and f.get("kind") == _INFRA_KIND:
            fid = f.get("id") or f.get("name")
            if fid and str(fid) not in out:
                out.append(str(fid))
    return out


def _substrate_coverage(
    ss: dict[str, Any], catalog: dict[str, Any] | None
) -> dict[str, Any]:
    """Where each required substrate was answered — or that it wasn't (D-SC22).

    A prompt lever has no floor: D-SC9's no-repeat clause generalised and Digger
    came back with ``infrastructure: {}``, silently dropping all five catalog
    requirements from the artifact Phaser is bound by. Nothing detected it; the
    coverage numbers all read clean. This makes the omission measurable.

    A substrate is answered in exactly one of two places: as a key in
    ``infrastructure``, or in some store's ``satisfies_infra`` (D-SC11(c), for
    substrates that ARE stores — a vector index above all).

    **D-SC58** — and in exactly ONE of them. The prompt says so explicitly
    (``satisfies_infra: ["vector_index"]``, *not two*), and a live Ragmeister draw
    ignored it: PostgreSQL+pgvector AND Qdrant both claimed ``vector_index``, and
    the model then invented a ``note`` on the primary store to explain the
    contradiction it had just created ("pgvector extension available but Qdrant is
    primary vector store"). This function read ``substrate coverage: 5/5`` on that
    draw, because ``via_store`` used ``setdefault`` — the first claimant won and the
    second was silently discarded. The blindness was one word, not an omission.
    Double-claiming is not cosmetic: the tag is the only record of which store fills
    a catalog requirement, so two claims leave Phaser unable to tell which.
    """
    required = _required_substrates(catalog)
    infra = ss.get("infrastructure")
    infra_keys = set(infra) if isinstance(infra, dict) else set()
    claims: dict[str, list[str]] = {}
    persistence = ss.get("persistence")
    if isinstance(persistence, dict):
        for store_name, store in persistence.items():
            if not isinstance(store, dict):
                continue
            for role in (store.get("satisfies_infra") or []):
                claims.setdefault(str(role), []).append(str(store_name))

    where: dict[str, str] = {}
    missing: list[str] = []
    for sub in required:
        if sub in infra_keys:
            where[sub] = "infrastructure"
        elif sub in claims:
            where[sub] = f"persistence.{claims[sub][0]} (satisfies_infra)"
        else:
            missing.append(sub)

    # Two stores claiming the same substrate, or a store claiming one that
    # `infrastructure` also keys. Both are the D-SC58 defect: the requirement is
    # answered twice and the plan cannot tell which answer is real.
    contested: list[dict[str, Any]] = []
    for sub, stores in sorted(claims.items()):
        holders = list(stores)
        if sub in infra_keys:
            holders = holders + ["infrastructure (block key)"]
        if len(holders) > 1:
            contested.append({"substrate": sub, "claimed_by": holders})

    return {
        "required_substrates": required,
        "substrate_where": where,
        "substrate_missing": missing,
        "substrate_coverage": f"{len(where)}/{len(required)}" if required else "0/0",
        # A satisfies_infra tag naming nothing the catalog asked for is a typo or
        # an invention; either way the join it was meant to carry does not land.
        "substrate_unrequested": sorted(set(claims) - set(required)),
        "substrate_contested": contested,
    }


def _nfr_keys(feature_specs: dict[str, Any] | None) -> dict[str, str]:
    """Map ``nfr_<slug>`` -> original goal text, derived from feature_specs.

    Keying by slug lets a stack entry's ``satisfies_nfr`` reference survive the
    LLM paraphrasing the goal wording, the same way slug ids join elsewhere.
    """
    out: dict[str, str] = {}
    for g in ((feature_specs or {}).get("nfr_goals") or []):
        if isinstance(g, str) and g.strip():
            out[f"nfr_{slug(g.strip())}"] = g.strip()
    return out


_ANNOTATIONS = ("serves_features", "satisfies_nfr", "foundational")


def _annotated_entries(ss: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Every dict anywhere in the stack spec carrying a linkage annotation.

    Walks the whole document rather than a fixed list of blocks. StackAdvisor
    demonstrably invents top-level blocks the schema does not define — ``data_model``
    and ``persistence`` have both appeared — and puts real attribution inside them.
    A block-scoped probe reads that as *zero* attribution and is simply wrong: one
    FareBox draw attributed all three features inside ``data_model`` while the probe
    reported 0/3. Recursion makes the measurement immune to schema drift, and the
    path is kept so the drift is visible rather than silent.
    """
    out: list[tuple[str, dict[str, Any]]] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if any(k in node for k in _ANNOTATIONS):
                out.append((path, node))
            for key, val in node.items():
                walk(val, f"{path}.{key}" if path else str(key))
        elif isinstance(node, list):
            for i, val in enumerate(node):
                walk(val, f"{path}[{i}]")

    walk(ss, "")
    return out


def _entry_name(path: str, entry: dict[str, Any]) -> str:
    """Best display name: an explicit name, else the key it hangs under."""
    for key in ("name", "choice", "type"):
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    tail = path.split(".")[-1] if path else "?"
    return tail or "?"


def _serves_entries(ss: dict[str, Any]) -> list[dict[str, Any]]:
    """Entries that may carry ``serves_features`` — anywhere in the document."""
    return [e for _, e in _annotated_entries(ss)]


_CATALOG_TIERS = (
    "deterministic", "embeddings", "single_call", "rag", "tool_agent",
    "chained_calls", "planning_agent", "orchestrated_subagents",
    "multi_agent_collaboration",
)


def _catalog_tiers(catalog: dict[str, Any] | None) -> set[str]:
    """Tiers the catalog actually uses (excluding injected infrastructure)."""
    out: set[str] = set()
    for f in ((catalog or {}).get("ai_features") or []):
        if not isinstance(f, dict) or f.get("kind") == _INFRA_KIND:
            continue
        if f.get("tier"):
            out.add(str(f["tier"]))
    return out


def _provider_tier_check(
    ss: dict[str, Any], catalog: dict[str, Any] | None
) -> dict[str, Any]:
    """D-SC39 — every provider capability's ``tier`` must name a real tier.

    Before D-SC39 the tier was a KEY in ``capability_by_tier``, so an invented
    label was structurally indistinguishable from a real one and nothing could
    check it. Two consecutive Threadline draws wrote ``standard`` — which is not
    one of the nine — and one wrote ``embedding`` for ``embeddings``; the prompt's
    own exemplar showed valid names in both draws and was copied in neither. That
    is why this is a deterministic check and not another prompt lever.

    ``unused`` is reported but is not a defect: a provider need not cover every
    tier the catalog uses (an in-process embeddings library covers one with no
    provider at all).
    """
    used = _catalog_tiers(catalog)
    invalid: list[dict[str, str]] = []
    declared: set[str] = set()
    for prov_name, prov in (ss.get("providers") or {}).items():
        if not isinstance(prov, dict):
            continue
        for cap in (prov.get("capabilities") or []):
            if not isinstance(cap, dict):
                continue
            tier = str(cap.get("tier", ""))
            declared.add(tier)
            if tier not in _CATALOG_TIERS:
                invalid.append({"provider": str(prov_name), "tier": tier})
    return {
        "provider_tiers_declared": sorted(t for t in declared if t),
        "provider_tiers_invalid": invalid,
        "provider_tiers_unused_by_catalog": sorted(declared - used - {""}) if used else [],
        "catalog_tiers_in_use": sorted(used),
    }


def _rejected_slugs(catalog: dict[str, Any] | None) -> dict[str, str]:
    """``slug(name)`` -> original name for every explicitly-rejected candidate.

    ``explicitly_rejected`` carries ``name``, not ``id`` — the panel records what
    the developer deselected, and Agentifier never tiered, coordinated, or specced
    it. Both validated draws happen to carry slug-shaped names
    (``suggested_replies_in_three_tones``, ``policy_gap_identification``), but the
    join is on ``slug(name)`` like every other join in the pipeline rather than on
    that coincidence.
    """
    out: dict[str, str] = {}
    for entry in ((catalog or {}).get("explicitly_rejected") or []):
        name = entry.get("name") if isinstance(entry, dict) else entry
        if name:
            out[slug(str(name))] = str(name)
    return out


def _linkage_refs(ss: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Every ``(path, field, id)`` linkage reference, in both id spaces.

    Collected by its own walk rather than by widening ``_ANNOTATIONS``, which also
    gates the D-SC4 foundational tally and the D-SC3 coverage numbers: adding a key
    there would silently move metrics this function is not measuring. That is
    D-SC33's lesson one probe over — a metric's meaning is contingent on the code
    it rides on, so do not change that code as a side effect.
    """
    out: list[tuple[str, str, str]] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for field in ("serves_features", "serves_capabilities"):
                val = node.get(field)
                if isinstance(val, list):
                    for ref in val:
                        if isinstance(ref, str) and ref.strip():
                            out.append((path or "?", field, ref.strip()))
            for key, val in node.items():
                walk(val, f"{path}.{key}" if path else str(key))
        elif isinstance(node, list):
            for i, val in enumerate(node):
                walk(val, f"{path}[{i}]")

    walk(ss, "")
    return out


def _is_ai_mechanism(path: str) -> bool:
    """Is this entry an AI mechanism by construction, or merely app stack?

    D-SC56 forbids provisioning an *AI mechanism* for a deselected candidate; it
    does not strip the product feature of its ordinary stack. On the Threadline
    draw the rejected ``suggested_replies_in_three_tones`` is referenced at eight
    sites, and only the two provider capabilities are mechanisms — the other six
    are ``email_threads``, ``email_messages``, ``draft_replies``, ``reply_cache``
    and ``redis-py``, which are correct and must survive. ``source_citations`` is
    the precedent already shipping: a spine feature with no catalog node that
    carries stores, an API and a UI, and no provider.

    Only two blocks are mechanisms by construction: a provider capability is
    always a model call, and an ``infrastructure`` entry is always AI substrate
    (the catalog's ``kind: infrastructure`` nodes are what open that topic).
    ``libraries`` cannot be decided structurally — LangChain and redis-py are the
    same shape and differ only in meaning — so it is reported descriptively rather
    than flagged. That is D-SC35's precedent: a flag that fires on correct
    behaviour gets retired to a tally, and it is cheaper to never ship it.
    """
    return path.startswith("providers.") or path.startswith("infrastructure.")


def _linkage_ref_check(
    ss: dict[str, Any], catalog: dict[str, Any] | None
) -> dict[str, Any]:
    """D-SC47 + D-SC56 — the two rules over the catalog id space.

    **D-SC47** — every ``serves_capabilities`` id must name a real catalog node.
    D-SC31 split the id spaces to make the product/catalog confusion structurally
    impossible, and shipped the new space with no check at all; ``serves_features``
    has been validated against the spine since D-SC3. A live Ragmeister draw
    carries ``policy_embedding`` — plausible, domain-shaped, and not a node (the
    catalog has ``embedding_pipeline`` and ``policy_document_indexing``). The same
    draw's prose emitted the exemplar's own ``recipe_embedding`` verbatim for a
    policy app, which is where the invented id came from: D-SC52's class, and proof
    that domain-loading demotes an exemplar leak from JSON to prose rather than
    preventing it.

    **D-SC56** — no reference in EITHER space may name an explicitly-rejected
    candidate. Agentifier has not tiered, coordinated, or specced a deselected
    feature, so a stack entry serving it is not an approximation of a decision but
    a fabricated one — and a fabricated tier is indistinguishable from a decided
    one. Binds on ``serves_features`` (Threadline resurrected
    ``suggested_replies_in_three_tones`` with an OpenAI primary and an Anthropic
    fallback) and on ``serves_capabilities`` (Ragmeister rebuilt
    ``policy_gap_identification`` as a sub-agent with its own ``inquiry_log``
    table). Non-AI attribution to a spine feature is untouched: ``source_citations``
    carries stores, an API, and a UI with no provider, and that is correct.
    """
    nodes = _ai_node_ids(catalog)
    rejected = _rejected_slugs(catalog)
    refs = _linkage_refs(ss)

    unresolved: list[dict[str, str]] = []
    resurrected: list[dict[str, str]] = []
    rejected_elsewhere: list[dict[str, str]] = []
    for path, field, ref in refs:
        if field == "serves_capabilities" and catalog is not None and ref not in nodes:
            unresolved.append({"path": path, "id": ref})
        if slug(ref) not in rejected:
            continue
        hit = {
            "path": path,
            "field": field,
            "id": ref,
            "rejected_as": rejected[slug(ref)],
        }
        (resurrected if _is_ai_mechanism(path) else rejected_elsewhere).append(hit)
    cap_refs = [r for r in refs if r[1] == "serves_capabilities"]
    return {
        "capability_refs_total": len(cap_refs),
        "capability_refs_resolved": f"{len(cap_refs) - len(unresolved)}/{len(cap_refs)}",
        "capability_refs_unresolved": unresolved,
        "rejected_candidates": sorted(rejected.values()),
        "resurrected_rejected": resurrected,
        "rejected_refs_outside_ai_mechanisms": rejected_elsewhere,
    }


def _provider_slugs(ss: dict[str, Any]) -> set[str]:
    """Slugs of the AI model providers this stack selected (D-SC16).

    Used to tell an AI-specific library (``anthropic``, ``langchain-anthropic``)
    from a general staple. The ``providers`` block is AI-model-oriented by
    construction, so anything named after a provider exists to talk to a model.
    """
    out: set[str] = set()

    def add(val: Any) -> None:
        if isinstance(val, str) and val.strip():
            out.add(slug(val))

    def harvest(node: Any) -> None:
        if isinstance(node, dict):
            for key, val in node.items():
                add(key)
                if isinstance(val, dict):
                    for k in ("name", "provider", "choice"):
                        add(val.get(k))
        elif isinstance(node, list):
            for item in node:
                add(item)
                if isinstance(item, dict):
                    for k in ("name", "provider", "choice"):
                        add(item.get(k))

    harvest(ss.get("providers"))
    return {s for s in out if s}


def _substrate_link(
    path: str, entry: dict[str, Any], provider_slugs: set[str]
) -> str | None:
    """Why this entry is tied to the AI substrate, or ``None`` if not derivable.

    The discriminator D-SC16 rests on. Two signals are sound; nothing else is
    claimed. ``infrastructure`` is AI-gated by ratified decision, so every entry
    in it is AI substrate. A name in a token-subset relation with a selected
    provider exists to reach a model — ``anthropic`` against a provider keyed
    ``Anthropic Claude`` clears; ``azure-storage`` against ``Azure OpenAI`` does
    not, which bare token overlap would wrongly clear.

    Deliberately conservative: it under-clears rather than over-clears
    (``langchain-anthropic`` will not match, nor will a tracing lib like
    ``langsmith``). That is why the coverage it feeds is a *floor* and not a
    verdict — see ``coverage_excluding_unlinked_blanket``.
    """
    block = path.split(".")[0].split("[")[0]
    if block == "infrastructure":
        return "infrastructure block (AI-gated)"
    if block == "providers":
        # Providers ARE AI model providers. The name match below would clear these
        # too, but circularly — a provider entry matching its own key. Say the real
        # reason instead.
        return "providers block (AI model providers)"
    tokens = set(slug(_entry_name(path, entry)).split("_")) - {""}
    for ps in sorted(provider_slugs):
        ptokens = set(ps.split("_")) - {""}
        if tokens and ptokens and (tokens <= ptokens or ptokens <= tokens):
            return f"named for provider `{ps}`"
    return None


def _nfr_entries(ss: dict[str, Any]) -> list[dict[str, Any]]:
    """Entries that may carry ``satisfies_nfr`` — anywhere in the document.

    A confidentiality goal may be satisfied by a provider, a latency goal by an
    infra or data-model choice, a durability goal by a library or a store; every
    annotated entry is eligible, so the same recursive set serves both metrics.
    """
    return [e for _, e in _annotated_entries(ss)]

def measure(
    stack: dict[str, Any],
    feature_specs: dict[str, Any] | None,
    catalog: dict[str, Any] | None,
) -> dict[str, Any]:
    ss = _stack_spec(stack)
    spine_ids = _spine_ids(feature_specs)
    ai_node_ids = _ai_node_ids(catalog)
    ai_served = _ai_served_ids(catalog)
    # A reference resolves against product ids OR AI capability-surface ids (the
    # catalog-node lane stays legal, D-SC4a).
    known_ids = spine_ids | ai_node_ids
    # "non-AI" means a product feature no AI node serves — derived from the serves
    # relation, never from node-id difference (the id spaces never intersect).
    non_ai_spine = spine_ids - ai_served
    nfr_keys = _nfr_keys(feature_specs)
    tier_check = _provider_tier_check(ss, catalog)

    # --- D-SC3 full-spine serves_features resolution ---
    serves_refs: list[str] = []
    for e in _serves_entries(ss):
        for x in (e.get("serves_features") or []):
            serves_refs.append(str(x))
    resolved = [r for r in serves_refs if r in known_ids]
    unresolved = sorted({r for r in serves_refs if r not in known_ids})
    # The D-SC3 signal: references that land on a *product* feature id (the spine).
    # This is what the lever moves — on an all-AI project there are no non-AI
    # features, so non-AI refs alone cannot tell success from failure.
    product_refs = sorted({r for r in serves_refs if r in spine_ids})
    # References that cite only an AI capability-surface id (the pre-lever lane).
    surface_only_refs = sorted(
        {r for r in serves_refs if r in ai_node_ids and r not in spine_ids}
    )
    non_ai_refs = sorted({r for r in serves_refs if r in non_ai_spine})

    # --- D-SC4 shared substrate: foundational vs blanket claiming ---
    # An entry chosen for the app as a whole should carry ``foundational: true`` and
    # omit ``serves_features``. The failure mode it replaces is an entry claiming
    # most/all features — attribution noise that tells the planner nothing about
    # which stack a feature actually needs.
    #
    # D-SC16: claiming every feature is NOT itself the fault. On an all-AI spine the
    # LLM SDK, the tracing lib and the agent runtime genuinely do serve every
    # feature, and the prompt's own counterfactual agrees — cut the AI features and
    # you keep none of them, so they are correctly not ``foundational``. The earlier
    # rule (claims-everything ⇒ should be foundational) could not tell that from a
    # general staple over-claiming, and on Digger it subtracted three true positives.
    # The real discriminator is whether the claimer is tied to the AI substrate.
    all_spine_ai_backed = bool(spine_ids) and spine_ids <= ai_served
    provider_slugs = _provider_slugs(ss)
    foundational: list[str] = []
    blanket_linked: list[str] = []
    blanket_unlinked: list[str] = []
    blanket_reasons: dict[str, str] = {}
    conflicted: list[str] = []
    attribution_blocks: list[str] = []
    for path, e in _annotated_entries(ss):
        name = _entry_name(path, e)
        refs = {str(x) for x in (e.get("serves_features") or [])}
        if refs:
            block = path.split(".")[0].split("[")[0] or "?"
            if block not in attribution_blocks:
                attribution_blocks.append(block)
        if e.get("foundational"):
            foundational.append(name)
            if refs:
                conflicted.append(name)  # never both
        elif spine_ids and refs and refs >= spine_ids:
            # D-SC35: RETIRED as a flag. Kept only as a descriptive tally.
            #
            # The heuristic scored 0 true positives in 6 flags across two draws, and
            # the mixed spine it was built for falsifies its premise rather than
            # exercising it. FareBox's `idb` genuinely serves all three features;
            # Threadline's OpenAI SDK, Ollama client, Playwright, `email_threads` and
            # `redis` genuinely serve both. Threadline's "non-AI" feature is non-AI
            # only because the user DESELECTED it at the breadth panel — it still
            # plainly needs an LLM — so `all_spine_ai_backed` being False says
            # nothing about whether claiming those features is over-claiming.
            #
            # The floor (`coverage_excluding_unlinked_blanket`) is unaffected either
            # way: it read the same on both draws with and without the discount. The
            # tally still prints, because an entry naming every feature is worth a
            # human glance; it is no longer split into a band that implies a verdict.
            reason = _substrate_link(path, e, provider_slugs)
            if reason:
                blanket_linked.append(name)
                blanket_reasons[name] = reason
            else:
                blanket_unlinked.append(name)
    blanket = blanket_linked + blanket_unlinked

    # Coverage discounting *unlinked* blanket claims only, giving a conservative
    # FLOOR rather than a verdict: raw coverage is the ceiling, this is the floor,
    # and the truth is between them. An unlinked entry may be a staple over-claiming
    # (discount it) or an AI specialist the linkage rule cannot prove (keep it) —
    # so when floor and ceiling disagree, read ``blanket_unlinked`` rather than
    # trusting either number. Discounting every blanket claim, as the pre-D-SC16
    # rule did, collapses that bracket onto the floor and reports false negatives.
    # Entries carrying ONLY capability ids (D-SC14 leak). The linkage rule permits
    # an AI capability id *additionally* — "never in place of the product feature
    # id it ultimately serves" — so a per-ref tally cannot judge this: it flags a
    # compliant entry (product id + capability id) exactly like an unattributable
    # one. The defect is per-ENTRY: no product id at all, so the entry attaches to
    # no feature and the downstream join dead-ends.
    unattributable: list[dict[str, Any]] = []
    for path, e in _annotated_entries(ss):
        refs = [str(x) for x in (e.get("serves_features") or [])]
        if not refs:
            continue
        if not any(r in spine_ids for r in refs) and any(
            r in ai_node_ids for r in refs
        ):
            unattributable.append(
                {
                    "entry": _entry_name(path, e),
                    "block": path.split(".")[0].split("[")[0] or "?",
                    "capability_ids": [r for r in refs if r in ai_node_ids],
                }
            )

    discounted = set(blanket_unlinked)
    real_linked: set[str] = set()
    for path, e in _annotated_entries(ss):
        if _entry_name(path, e) in discounted:
            continue
        for x in (e.get("serves_features") or []):
            if str(x) in spine_ids:
                real_linked.add(str(x))
    real_covered = sorted(fid for fid in spine_ids if fid in real_linked)
    real_uncovered = sorted(fid for fid in spine_ids if fid not in real_linked)
    # attribution coverage over the whole spine (soft: staples legitimately omit)
    linked = {r for r in serves_refs if r in spine_ids}
    covered = sorted(fid for fid in spine_ids if fid in linked)
    uncovered = sorted(fid for fid in spine_ids if fid not in linked)
    # --- D-SC2 nfr -> satisfies_nfr coverage ---
    referenced: set[str] = set()
    for e in _nfr_entries(ss):
        for k in (e.get("satisfies_nfr") or []):
            referenced.add(str(k))
    nfr_covered = sorted(k for k in nfr_keys if k in referenced)
    nfr_orphaned = sorted(k for k in nfr_keys if k not in referenced)
    nfr_unknown = sorted(referenced - set(nfr_keys))  # keys matching no goal

    return {
        **tier_check,
        **_linkage_ref_check(ss, catalog),
        "spine_features": len(spine_ids),
        "ai_surfaces": len(ai_node_ids),
        "ai_backed_spine_features": sorted(ai_served & spine_ids),
        "non_ai_spine_features": sorted(non_ai_spine),
        "nfr_goals": len(nfr_keys),
        # D-SC3
        "serves_refs_total": len(serves_refs),
        "serves_resolved": f"{len(resolved)}/{len(serves_refs)}",
        "serves_unresolved": unresolved,
        "product_serves_refs": product_refs,
        "surface_only_serves_refs": surface_only_refs,
        "non_ai_serves_refs": non_ai_refs,
        "full_spine_attribution_active": bool(product_refs),
        # D-SC4
        "attribution_blocks": attribution_blocks,
        "unattributable_entries": unattributable,
        **_substrate_coverage(ss, catalog),
        "foundational_entries": sorted(foundational),
        "blanket_claim_entries": sorted(blanket),
        "blanket_substrate_linked": sorted(blanket_linked),
        "blanket_unlinked": sorted(blanket_unlinked),
        "blanket_link_reasons": blanket_reasons,
        "all_spine_ai_backed": all_spine_ai_backed,
        "foundational_conflicts": sorted(conflicted),
        "coverage_excluding_unlinked_blanket": (
            f"{len(real_covered)}/{len(spine_ids)}" if spine_ids else "0/0"
        ),
        "uncovered_excluding_unlinked_blanket": real_uncovered,
        "serves_all_resolve": not unresolved,
        "spine_attribution_coverage": (
            f"{len(covered)}/{len(spine_ids)}" if spine_ids else "0/0"
        ),
        "spine_uncovered": uncovered,
        # D-SC2
        "nfr_annotation_active": bool(referenced),
        "nfr_coverage": f"{len(nfr_covered)}/{len(nfr_keys)}",
        "nfr_orphaned": [nfr_keys[k] for k in nfr_orphaned],
        "nfr_unknown_keys": nfr_unknown,
    }


def fixtures() -> dict[str, dict[str, Any]]:
    """A pre-lever and a post-lever synthetic draw over the same spine.

    Same feature_specs (two AI-backed + two non-AI features, two nfr_goals) and the
    same catalog under both; only the ``stack.json`` differs, so the metric delta is
    attributable purely to the lever. The catalog mirrors reality: an AI node's own
    id is a capability-*surface* id, and the product feature it serves is named in
    ``vision_grounding.served_features``.

    Pre-lever the stack cites surface ids only (attribution never reaches a product
    feature). Post-lever it cites product ids — AI-backed and non-AI alike — and
    records ``satisfies_nfr``.
    """
    feature_specs = {
        "features": [
            {"id": "semantic_search"},       # AI-backed (served by a catalog node)
            {"id": "answer_synthesis"},      # AI-backed (served by a catalog node)
            {"id": "saved_items"},           # non-AI (spine only)
            {"id": "export_report"},         # non-AI (spine only)
        ],
        "nfr_goals": [
            "semantic search returns results in sub-second time",
            "saved items persist reliably and are never lost",
        ],
    }
    catalog = {
        "ai_features": [
            {
                "id": "semantic_retrieval_capability",
                "name": "semantic_retrieval_capability",
                "tier": "rag",
                "vision_grounding": {
                    "served_features": [{"id": "semantic_search"}]
                },
            },
            {
                "id": "answer_synthesis_capability",
                "name": "answer_synthesis_capability",
                "tier": "single_call",
                "vision_grounding": {
                    "served_features": [{"id": "answer_synthesis"}]
                },
            },
        ]
    }
    key_latency = "nfr_" + slug("semantic search returns results in sub-second time")
    key_persist = "nfr_" + slug("saved items persist reliably and are never lost")

    pre = {
        "stack_spec": {
            "libraries": {
                "backend": [
                    {"name": "FastAPI", "purpose": "web framework"},
                    {"name": "qdrant-client", "purpose": "vector client",
                     "serves_features": ["semantic_retrieval_capability"]},
                    # the D-SC4 failure mode: shared substrate claiming everything
                    {"name": "Zustand", "purpose": "app-wide state",
                     "serves_features": ["semantic_search", "answer_synthesis",
                                         "saved_items", "export_report"]},
                ]
            },
            "infrastructure": {
                "vector_index": {
                    "choice": "Qdrant",
                    "serves_features": ["semantic_retrieval_capability"],
                }
            },
        }
    }
    post = {
        "stack_spec": {
            "providers": {
                # D-SC39: real tier names, and one invented label ("standard") of
                # exactly the kind two live Threadline draws produced -- a fixture
                # built only from valid data would let the check ship green and
                # misfire on every real stack.
                "OpenAI": {"capabilities": [
                    {"tier": "rag", "capability_class": "a capable model",
                     "role": "primary"},
                    {"tier": "standard", "capability_class": "extraction",
                     "role": "primary"},
                ],
                    "credentials_env": "OPENAI_API_KEY"}
            },
            "libraries": {
                "backend": [
                    {"name": "FastAPI", "purpose": "web framework"},
                    {"name": "Zustand", "purpose": "app-wide state",
                     "foundational": True},
                    {"name": "qdrant-client", "purpose": "vector client",
                     "serves_features": ["semantic_search"],
                     "satisfies_nfr": [key_latency]},
                    {"name": "SQLAlchemy", "purpose": "durable ORM",
                     "serves_features": ["saved_items"],
                     "satisfies_nfr": [key_persist]},
                    {"name": "ReportLab", "purpose": "PDF export",
                     "serves_features": ["export_report"]},
                ]
            },
            "infrastructure": {
                "vector_index": {"choice": "Qdrant",
                                 "serves_features": ["semantic_search"],
                                 "satisfies_nfr": [key_latency]}
            },
        }
    }
    all_ai_specs = {
        "features": [
            {"id": "semantic_search"},
            {"id": "answer_synthesis"},
        ],
        "nfr_goals": ["semantic search returns results in sub-second time"],
    }
    # Every spine feature AI-backed (Digger's shape). The LLM SDK, the tracing lib
    # and the agent runtime each serve all of them — true, not over-claiming. The
    # pre-D-SC16 rule flagged all three and reported 1/2 where 2/2 was real.
    all_ai = {
        "stack_spec": {
            # real draws key providers by model family ("Anthropic Claude"),
            # not by bare vendor — the fixture must not idealise the name away
            "providers": {
                "Anthropic Claude": {"credentials_env": "ANTHROPIC_API_KEY"}
            },
            "libraries": {
                "backend": [
                    {"name": "anthropic", "purpose": "LLM SDK",
                     "serves_features": ["semantic_search", "answer_synthesis"]},
                    {"name": "langsmith", "purpose": "LLM tracing",
                     "serves_features": ["semantic_search", "answer_synthesis"]},
                    {"name": "qdrant-client", "purpose": "vector client",
                     "serves_features": ["semantic_search"]},
                    {"name": "FastAPI", "purpose": "web framework",
                     "foundational": True},
                ]
            },
            "infrastructure": {
                "pipeline_runner": {
                    "choice": "Celery workers",
                    "serves_features": ["semantic_search", "answer_synthesis"],
                }
            },
        }
    }
    # A catalog that actually requires substrate, so D-SC22's check is exercised.
    # Digger's shape: five required substrates, one of which is a store.
    infra_catalog = {
        "ai_features": [
            {"id": "semantic_search_ranking", "kind": "feature",
             "vision_grounding": {"served_features": [{"id": "semantic_search"}]}},
            {"id": "vector_index", "kind": "infrastructure"},
            {"id": "agent_loop_runtime", "kind": "infrastructure"},
            {"id": "tool_execution_harness", "kind": "infrastructure"},
        ],
    }
    infra_specs = {"features": [{"id": "semantic_search"}], "nfr_goals": []}
    infra_stack = {
        "stack_spec": {
            # vector_index answered in persistence; agent_loop_runtime in
            # infrastructure; tool_execution_harness answered NOWHERE (the D-SC22
            # regression), and one entry tagged only with a capability id.
            "persistence": {
                "primary_store": {
                    "choice": "PostgreSQL 16 + pgvector",
                    "durability": "source of truth",
                    "satisfies_infra": ["vector_index"],
                    "collections": [
                        {"name": "docs", "entities": ["Doc"],
                         "serves_features": ["semantic_search"]}
                    ],
                },
                # D-SC58 true positive: a SECOND store claiming the same substrate.
                # Ragmeister's shape verbatim -- PostgreSQL+pgvector and Qdrant both
                # claiming `vector_index`, which the model then papered over with an
                # invented `note` ("pgvector extension available but Qdrant is
                # primary vector store"). Note this does NOT move D-SC22's numbers:
                # a contested substrate is still a covered one, so `substrate_missing`
                # and `substrate_coverage` are untouched and the fixture's original
                # purpose is intact.
                "vector_store": {
                    "choice": "Qdrant",
                    "durability": "derived — rebuildable from primary_store",
                    "satisfies_infra": ["vector_index"],
                    "collections": [
                        {"name": "doc_embeddings", "entities": ["Doc"],
                         "serves_features": ["semantic_search"]}
                    ],
                },
            },
            "infrastructure": {
                "agent_loop_runtime": {
                    "choice": "LangGraph (see libraries)",
                    "serves_features": ["semantic_search"],
                },
                "embedding_pipeline": {
                    "choice": "sentence-transformers",
                    "serves_features": ["semantic_search_ranking"],
                },
            },
        }
    }
    # --- D-SC47 / D-SC56 --------------------------------------------------
    # Its own fixture rather than an addition to post_lever. pre/post exist so the
    # D-SC3 delta is attributable purely to that lever, and a rejected candidate in
    # `serves_features` is legitimately an unresolved product-id ref -- putting one
    # in post_lever moved `serves resolved` to 5/7 and `all_resolve` to False for
    # reasons with nothing to do with D-SC3. Same reasoning as substrate_gap
    # standing apart for D-SC22.
    rejected_specs = {
        "features": [
            {"id": "policy_answers"},        # AI-backed
            # Rejected name == spine id, which is the Threadline shape exactly:
            # `suggested_replies_in_three_tones` is BOTH an MVP spine feature and
            # the candidate the panel deselected. That identity is what makes the
            # case hard -- the id resolves cleanly under D-SC3, so nothing upstream
            # of D-SC56 can see anything wrong.
            {"id": "answer_confidence_scoring"},
        ],
        "nfr_goals": [],
    }
    rejected_catalog = {
        "ai_features": [
            {
                "id": "policy_retrieval_capability",
                "name": "policy_retrieval_capability",
                "tier": "rag",
                "vision_grounding": {"served_features": [{"id": "policy_answers"}]},
            },
        ],
        # The panel records what the developer deselected under `name`, not `id`,
        # and it is name-cased here on purpose: both live draws happen to carry
        # slug-shaped names, so a fixture built from them alone would let an
        # exact-match implementation ship green and miss every real rejection.
        "explicitly_rejected": [
            {"name": "Answer_Confidence_Scoring",
             "rough_description": "scores answer confidence"},
        ],
    }
    rejected_stack = {
        "stack_spec": {
            "providers": {
                "OpenAI": {
                    "capabilities": [
                        {"tier": "rag", "capability_class": "a capable model",
                         "role": "primary",
                         "serves_features": ["policy_answers"]},
                        # D-SC56 DEFECT: a provider capability is an AI mechanism by
                        # construction, and this one serves a deselected candidate.
                        # The Threadline shape verbatim -- OpenAI single_call for
                        # suggested_replies_in_three_tones, which Agentifier never
                        # tiered, coordinated or specced.
                        {"tier": "single_call", "capability_class": "confidence",
                         "role": "primary",
                         "serves_features": ["answer_confidence_scoring"]},
                    ],
                    "credentials_env": "OPENAI_API_KEY",
                }
            },
            "libraries": [
                # D-SC47 true positive: a near-miss capability id. The node is
                # `policy_retrieval_capability`; this drops the suffix, exactly as a
                # live Threadline draw wrote `sentiment_urgency_detection` for
                # `thread_sentiment_and_urgency_detection` while that same draw's
                # infrastructure entries spelled the node correctly.
                {"name": "instructor", "purpose": "structured outputs",
                 "serves_features": ["policy_answers"],
                 "serves_capabilities": ["policy_retrieval"]},
                {"name": "langchain", "purpose": "rag orchestration",
                 "serves_features": ["policy_answers"],
                 "serves_capabilities": ["policy_retrieval_capability"]},
                # D-SC56 DESCRIPTIVE: ordinary app stack serving the product feature
                # whose AI node was rejected. Correct, and must NOT be flagged --
                # `source_citations` ships exactly this way on the live Ragmeister
                # draw: stores, an API and a UI, and no provider.
                {"name": "SQLAlchemy", "purpose": "durable ORM",
                 "serves_features": ["answer_confidence_scoring"]},
            ],
        }
    }

    return {
        "pre_lever": {"stack": pre, "feature_specs": feature_specs,
                      "catalog": catalog},
        "substrate_gap": {"stack": infra_stack, "feature_specs": infra_specs,
                          "catalog": infra_catalog},
        "post_lever": {"stack": post, "feature_specs": feature_specs,
                       "catalog": catalog},
        "all_ai_spine": {"stack": all_ai, "feature_specs": all_ai_specs,
                         "catalog": catalog},
        "rejected_and_caps": {"stack": rejected_stack,
                              "feature_specs": rejected_specs,
                              "catalog": rejected_catalog},
    }


def _load(draw_dir: Path) -> tuple[
    dict[str, Any], dict[str, Any] | None, dict[str, Any] | None
]:
    stack = json.loads((draw_dir / "stack.json").read_text(encoding="utf-8"))
    fs_path = draw_dir / "feature_specs.json"
    fs = (
        json.loads(fs_path.read_text(encoding="utf-8"))
        if fs_path.exists() else None
    )
    cat_path = draw_dir / "ai_features.json"
    cat = (
        json.loads(cat_path.read_text(encoding="utf-8"))
        if cat_path.exists() else None
    )
    return stack, fs, cat


def _report(name: str, m: dict[str, Any]) -> None:
    print(f"\n[{name}]  spine={m['spine_features']}  ai_surfaces={m['ai_surfaces']}  "
          f"nfr_goals={m['nfr_goals']}")
    print(f"  AI-backed spine features: {m['ai_backed_spine_features'] or '(none)'}")
    print(f"  non-AI spine features:    {m['non_ai_spine_features'] or '(none)'}")
    print("  --- D-SC3 full-spine serves_features ---")
    print(f"  serves resolved: {m['serves_resolved']}")
    print(f"  product-id refs:  {m['product_serves_refs'] or '(none)'}")
    print(f"  surface-only refs: {m['surface_only_serves_refs'] or '(none)'}")
    print(f"  non-AI refs:      {m['non_ai_serves_refs'] or '(none)'}")
    print(f"  full_spine_attribution_active: {m['full_spine_attribution_active']}"
          f"   all_resolve: {m['serves_all_resolve']}")
    if m["serves_unresolved"]:
        print(f"  UNRESOLVED (typos): {m['serves_unresolved']}")
    print(f"  spine attribution coverage: {m['spine_attribution_coverage']}   "
          f"uncovered: {m['spine_uncovered'] or '(none)'}")
    if m["blanket_unlinked"]:
        print(f"  coverage EXCLUDING unlinked blanket: "
              f"{m['coverage_excluding_unlinked_blanket']}   "
              f"uncovered: {m['uncovered_excluding_unlinked_blanket'] or '(none)'}")
    if m["unattributable_entries"]:
        print("  UNATTRIBUTABLE entries (capability ids only, no product id):")
        for u in m["unattributable_entries"]:
            print(f"      - {u['entry']}  [{u['block']}]  {u['capability_ids']}")
    print(f"  attribution lives in: {m['attribution_blocks'] or '(nowhere)'}")
    if m["required_substrates"]:
        print("  --- D-SC22 required substrate ---")
        print(f"  substrate coverage: {m['substrate_coverage']}   "
              f"missing: {m['substrate_missing'] or '(none)'}")
        for sub in m["required_substrates"]:
            print(f"      {sub:26s} -> {m['substrate_where'].get(sub, '*** MISSING ***')}")
        if m["substrate_unrequested"]:
            print(f"  satisfies_infra naming nothing the catalog required: "
                  f"{m['substrate_unrequested']}")
    if m["substrate_contested"]:
        print("  CONTESTED — a substrate answered in more than one place (D-SC58; "
              "the prompt says `satisfies_infra: [\"vector_index\"]`, not two):")
        for c in m["substrate_contested"]:
            print(f"      - {c['substrate']}  claimed by {c['claimed_by']}")
    print("  --- D-SC47 serves_capabilities -> catalog nodes ---")
    print(f"  capability refs resolved: {m['capability_refs_resolved']}")
    if m["capability_refs_unresolved"]:
        print("  UNRESOLVED capability ids (name no catalog node):")
        for u in m["capability_refs_unresolved"]:
            print(f"      - {u['id']}   at {u['path']}")
    print("  --- D-SC56 explicitly-rejected resurrection ---")
    print(f"  rejected candidates: {m['rejected_candidates'] or '(none)'}")
    if m["resurrected_rejected"]:
        print("  RESURRECTED — an AI mechanism is provisioned for a deselected "
              "candidate:")
        for r in m["resurrected_rejected"]:
            print(f"      - {r['id']}   via {r['field']}   at {r['path']}")
    elif m["rejected_candidates"]:
        print("  no AI mechanism serves a rejected candidate")
    if m["rejected_refs_outside_ai_mechanisms"]:
        # Descriptive, not a defect: the product feature keeps its ordinary stack.
        print("  rejected candidates referenced outside AI mechanisms "
              "(descriptive — persistence/libraries legitimately serve the "
              "product feature):")
        for r in m["rejected_refs_outside_ai_mechanisms"]:
            print(f"    - {r['id']}   at {r['path']}")
    print("  --- D-SC4 shared substrate ---")
    print(f"  foundational entries: {m['foundational_entries'] or '(none)'}")
    if m["blanket_claim_entries"]:
        # D-SC35: descriptive tally, not a flag. 0 true positives in 6 flags across
        # two draws; the floor below is unaffected by it either way.
        print("  entries naming every spine feature (descriptive — not a defect):")
        for n in m["blanket_claim_entries"]:
            reason = m["blanket_link_reasons"].get(n)
            print(f"    - {n}" + (f"  [{reason}]" if reason else ""))
    if m["foundational_conflicts"]:
        print(f"  CONFLICT (foundational AND serves_features): "
              f"{m['foundational_conflicts']}")
    if m["provider_tiers_declared"] or m["provider_tiers_invalid"]:
        print("  --- D-SC39 provider tiers ---")
        print(f"  declared: {m['provider_tiers_declared'] or '(none)'}   "
              f"catalog in use: {m['catalog_tiers_in_use'] or '(none)'}")
        if m["provider_tiers_invalid"]:
            print("  INVALID — not one of the nine catalog tiers "
                  "(the join to the catalog dead-ends):")
            for bad in m["provider_tiers_invalid"]:
                print(f"    - {bad['provider']}: {bad['tier']!r}")
        else:
            print("  all provider tiers are real catalog tiers")
        if m["provider_tiers_unused_by_catalog"]:
            print(f"  declared but not used by the catalog (not a defect): "
                  f"{m['provider_tiers_unused_by_catalog']}")
    print("  --- D-SC2 nfr -> satisfies_nfr ---")
    print(f"  nfr_annotation_active: {m['nfr_annotation_active']}   "
          f"coverage: {m['nfr_coverage']}")
    if m["nfr_orphaned"]:
        print(f"  orphaned goals (no stack entry): {m['nfr_orphaned']}")
    if m["nfr_unknown_keys"]:
        print(f"  UNKNOWN satisfies_nfr keys: {m['nfr_unknown_keys']}")


def main() -> int:
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            d = Path(arg)
            stack, fs, cat = _load(d)
            _report(d.name, measure(stack, fs, cat))
        return 0

    print("=== StackAdvisor spine-coverage — built-in fixtures ===")
    for name, fx in fixtures().items():
        _report(name, measure(fx["stack"], fx["feature_specs"], fx["catalog"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
