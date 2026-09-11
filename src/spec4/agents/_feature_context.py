"""Feature and AI-feature seed blocks, one renderer per downstream consumer.

Stack Advisor, Phaser, Deployer and Designer each need the same two artifacts —
the Brainstormer feature spine (``feature_specs.json``) and the Agentifier AI
catalog (``ai_features.json``) — at a different altitude and with a different
join. The ``ai_features_for_*`` and ``feature_specs_for_*`` pairs are those
per-consumer projections; ``slug`` is the id derivation that lets the two
artifacts join at all, and ``excluded_feature_ids`` is the shared read of which
spine features the developer's Agentifier selection took out of scope.

Split out of ``_utils.py`` in Phase 4a; Phase 4j moved every importer here and
retired the ``_utils`` facade, so this module is now the one place these names
are imported from.
"""

from __future__ import annotations

import re
from typing import Any

from spec4.agentifier.infra_expander import INFRA_KIND
from spec4.feature_specs import (
    DESIGNER_SPEC_FIELDS,
    PHASER_PRODUCT_SPEC_FIELDS,
    STACK_SPEC_FIELDS,
    render_cross_cutting,
    render_feature_block,
)


def slug(name: str) -> str:
    """Canonical feature-id derivation shared across the pipeline.

    ``id = slug(name)`` — lowercase, with every character outside ``[a-z0-9_]``
    collapsed to ``_``. This mirrors the derivation already used by the
    Agentifier feature builder (``agentifier.py``) and the Phaser coverage check
    (``_phase_coverage._slug``), so a feature's Brainstormer-assigned id and its
    Agentifier id coincide by construction on matching names — the join key the
    downstream agents key off. Empty input yields ``""``.
    """
    return re.sub(r"[^a-z0-9_]", "_", name.lower()) if name else ""


# ---------------------------------------------------------------------------
# AI features context blocks (for downstream agent seed injection)
# ---------------------------------------------------------------------------

TIER_ORDER_FOR_SUMMARY = {
    "deterministic": 1,
    "embeddings": 2,
    "single_call": 3,
    "rag": 4,
    "tool_agent": 5,
    "chained_calls": 6,
    "planning_agent": 7,
    "orchestrated_subagents": 8,
    "multi_agent_collaboration": 9,
}


def served_product_feature_ids(node: dict[str, Any]) -> list[str]:
    """Product-feature ids an AI node serves, from its ``vision_grounding``.

    The serves relation (D-AC1) is the only sound capability→product-feature
    mapping: an AI node's id is a capability-*surface* id and never equals the
    product feature id it serves. Ids are returned in grounding order, de-duped.
    Empty for infrastructure and cross-cutting nodes, which ground nothing.
    """
    grounding = node.get("vision_grounding") or {}
    out: list[str] = []
    for sf in grounding.get("served_features") or []:
        if isinstance(sf, dict) and sf.get("id"):
            fid = str(sf["id"])
            if fid not in out:
                out.append(fid)
    return out


def project_feature_for_stack(
    f: dict[str, Any], current_version: int | None, lines: list[str]
) -> None:
    """Append one feature's stack-driving fields to ``lines`` (D-SA1(c)).

    Tier-agnostic: every field here can force a concrete library choice with no
    model in sight — a ``deterministic`` feature may declare a ``document_store``
    knowledge source or a ``scheduled`` invocation. So the projection surfaces
    the same fields regardless of tier rather than gating them behind a model
    threshold (the histogram's bias, which dropped exactly this detail).

    ``scope`` and the serves relation are rendered because the stack prompt's
    linkage rules condition on them (D-SC14): ``serves_features`` must carry the
    product feature id a capability serves, and the ``cross_feature`` lane fires
    on scope. Both were computed upstream and dropped here, leaving the model to
    infer the capability→product mapping from name similarity — which is exactly
    how a catalog node id reaches ``serves_features`` in place of a product id.
    """
    _stack_feature_header(f, current_version, lines)

    mode = (f.get("invocation") or {}).get("mode")
    if mode:
        lines.append(f"    - invocation: {mode}")

    fmt = (f.get("outputs") or {}).get("format")
    if fmt:
        lines.append(f"    - output format: {fmt}")
    _stack_knowledge_source_lines(f, lines)
    _stack_tool_access_lines(f, lines)
    _stack_mechanism_lines(f, lines)
    _stack_quality_lines(f, lines)


def _stack_feature_header(
    f: dict[str, Any], current_version: int | None, lines: list[str]
) -> None:
    """The feature's header line and its serves-relation line."""
    name = f.get("name") or f.get("id") or "unnamed"
    tier = f.get("tier", "single_call")
    scope = f.get("scope")
    header = f"- **{name}** ({tier}"
    header += f", scope: {scope})" if scope else ")"
    if current_version and f.get("introduced_in_version") == current_version:
        header += " — NEW this revision"
    lines.append(header)

    served = served_product_feature_ids(f)
    if served:
        lines.append(f"    - serves product feature(s): {', '.join(served)}")


def _stack_knowledge_source_lines(f: dict[str, Any], lines: list[str]) -> None:
    """One line per declared knowledge source."""
    for ks in f.get("knowledge_sources") or []:
        if not isinstance(ks, dict):
            continue
        ks_name = ks.get("name") or "source"
        ks_type = ks.get("type") or "unspecified"
        desc = (ks.get("content_description") or "").strip()
        line = f"    - knowledge source: {ks_name} ({ks_type})"
        if desc:
            line += f" — {desc[:100]}"
        lines.append(line)


def _stack_tool_access_lines(f: dict[str, Any], lines: list[str]) -> None:
    """One line per needed tool-access capability."""
    for cap in (f.get("tool_access") or {}).get("capabilities_needed") or []:
        if not isinstance(cap, dict):
            continue
        purpose = (cap.get("purpose") or "capability").strip()
        detail = f"source={cap.get('source') or 'unspecified'}"
        if cap.get("protocol"):
            detail += f", protocol={cap['protocol']}"
        if cap.get("mcp_server"):
            detail += f", server={cap['mcp_server']}"
        lines.append(f"    - tool access: {purpose[:80]} [{detail}]")


def _stack_mechanism_lines(f: dict[str, Any], lines: list[str]) -> None:
    """The mechanisms line."""
    raw_mechs = [
        (m.get("name") if isinstance(m, dict) else str(m))
        for m in (f.get("mechanisms") or [])
    ]
    mechs: list[str] = [m for m in raw_mechs if m]
    if mechs:
        lines.append(f"    - mechanisms: {', '.join(mechs)}")


def _stack_quality_lines(f: dict[str, Any], lines: list[str]) -> None:
    """Privacy/safety, online eval signal and references."""
    privacy = [
        str(p).strip() for p in (f.get("privacy_safety") or []) if str(p).strip()
    ]
    if privacy:
        lines.append(f"    - privacy/safety: {'; '.join(privacy)[:120]}")

    online = (f.get("eval_approach") or {}).get("online")
    if online:
        lines.append(f"    - online eval signal: {str(online)[:100]}")

    refs = [str(r).strip() for r in (f.get("references") or []) if str(r).strip()]
    if refs:
        lines.append(f"    - references: {'; '.join(refs)[:160]}")


def ai_features_for_stack(
    ai_features: dict[str, Any], current_version: int | None = None
) -> str:
    """Per-feature stack-driving projection for StackAdvisor (D-SA1(c), D-SA2).

    Replaces the prior tier-histogram + boolean-hint summary. The histogram
    framed every signal through model tiers, which (a) scored infrastructure
    nodes — whose sentinel ``tier="infrastructure"`` defaulted to the
    ``single_call`` order — as generative, emitting a phantom "LLM-backed"
    instruction on catalogs with zero generative features, and (b) gated the
    vector-store hint above the ``embeddings`` tier, so an embeddings feature's
    vector substrate was never surfaced (the D-PS5b mechanism). Deleting the
    hint layer retires both defects together (D-SA3(a)); the replacement
    surfaces, per feature and regardless of tier, exactly the fields that force
    a concrete library choice (D-SA1(c)).

    Infrastructure nodes (``kind == INFRA_KIND``) are split out of the
    per-feature projection and rendered as an explicit required-infrastructure
    section (D-SA2), each reverse-mapped to the feature(s) that ``require`` it,
    so StackAdvisor knows each substrate needs a concrete library or service
    choice. The provider *gate* itself (D-SA6 / D-SA10) is consumed by the topic
    sequence and schema in ``stack_advisor.py`` and is not computed here.

    ``current_version`` is the revision round being planned. When it identifies
    a revision (truthy / > 0), features whose ``introduced_in_version`` equals it
    are tagged ``NEW this revision`` inline, plus a single note that carries the
    "not yet in the carried-forward stack" instruction so revision-mode
    StackAdvisor does not mistake a brand-new feature for existing capability.
    Greenfield builds (version 0) tag nothing — every feature is new there.
    """
    all_nodes: list[dict[str, Any]] = ai_features.get("ai_features") or []
    cross: dict[str, Any] = ai_features.get("cross_cutting") or {}
    if not all_nodes:
        return ""

    features = [f for f in all_nodes if f.get("kind") != INFRA_KIND]
    infra = [f for f in all_nodes if f.get("kind") == INFRA_KIND]

    lines = [
        "**AI features spec (from Agentifier) — tailor your stack "
        "recommendations to these:**\n"
    ]

    any_new = False
    for f in features:
        project_feature_for_stack(f, current_version, lines)
        if current_version and f.get("introduced_in_version") == current_version:
            any_new = True

    if any_new:
        lines.append(
            '- Features tagged "NEW this revision" are NOT yet implemented in '
            "the carried-forward stack; treat each as a new functional area "
            "requiring stack support, not pre-existing capability."
        )

    _stack_infra_lines(infra, features, lines)
    _stack_cross_cutting_lines(cross, lines)

    # D-SC55a. StackAdvisor could not see the rejection list, and Phaser always
    # could (`ai_features_for_phaser` calls the same helper) -- the asymmetry ran
    # exactly the wrong way, since StackAdvisor is where the provider decision is
    # made and Phaser only inherits it as authoritative.
    #
    # The cost was measured on both validated draws. Threadline's developer
    # deselected the whole reply cluster; StackAdvisor provisioned an OpenAI
    # primary AND an Anthropic fallback for `suggested_replies_in_three_tones` and
    # called it "a single_call feature" -- assigning a tier, which is Agentifier's
    # job, with none of Agentifier's machinery. Ragmeister's developer deselected
    # `policy_gap_identification`; StackAdvisor rebuilt it as a sub-agent of
    # `subagent_orchestration_runtime` with its own `inquiry_log` table. In both
    # cases D-SC14's spine-as-base was doing its job with one input missing: it saw
    # a need in the spine, saw no catalog node, and filled the hole.
    #
    # Deselection is the panel's only act of developer agency, and it was being
    # reversed two agents downstream on a receipt the developer then ratified.
    lines.extend(explicitly_rejected_lines(ai_features, consumer="stack"))

    lines.append("")
    return "\n".join(lines)


def _stack_infra_lines(
    infra: list[dict[str, Any]], features: list[dict[str, Any]], lines: list[str]
) -> None:
    """Required-infrastructure section (D-SA2), reverse-mapped to consumers."""
    if infra:
        lines.append(
            "\n**Required infrastructure (tier-derived — each needs a concrete "
            "library or service choice in the stack):**"
        )
        for node in infra:
            comp = node.get("name") or node.get("id") or "unnamed"
            consumers = [
                (c.get("name") or c.get("id") or "unnamed")
                for c in features
                if comp in (c.get("requires") or [])
            ]
            if consumers:
                lines.append(f"- {comp} — required by: {', '.join(consumers)}")
            else:
                lines.append(f"- {comp}")


def _stack_cross_cutting_lines(cross: dict[str, Any], lines: list[str]) -> None:
    """Cross-cutting strategies the analyst produced for stack selection."""
    # Cross-cutting strategies the analyst produced for stack selection. Provider
    # strategy is ratified into the providers block; tool-protocol strategy informs
    # tool/MCP library selection; prompt versioning is recorded as a convention.
    # (observability / eval are owned by StackAdvisor and Deployer natively.)
    if cross.get("provider_strategy", {}).get("recommendation"):
        rec = cross["provider_strategy"]["recommendation"][:120]
        lines.append(f"\n- Provider strategy: {rec}")
    if (cross.get("tool_protocol_strategy") or {}).get("recommendation"):
        rec = cross["tool_protocol_strategy"]["recommendation"][:200]
        lines.append(f"- Tool protocol strategy (MCP vs direct, build vs reuse): {rec}")
    if (cross.get("prompt_versioning") or {}).get("recommendation"):
        rec = cross["prompt_versioning"]["recommendation"][:200]
        lines.append(f"- Prompt versioning: {rec}")


def feature_relationship_lines(features: list[dict[str, Any]]) -> list[str]:
    """Render the Scout graph-contract edges as a data-only relationships block.

    Two edge kinds are surfaced verbatim for Phaser to read; no build-order or
    coordinated-feature directives are added here — interpreting the edges is
    Phaser's own logic (a later lever). ``composed_under`` groups members beneath
    their coordinator; ``requires`` names the producers a feature consumes. Edges
    are rendered exactly as persisted (D-EP2 option A), including any that dangle.
    Returns ``[]`` when no edges are present.
    """
    groups: dict[str, list[str]] = {}
    for f in features:
        parent = f.get("composed_under") or ""
        if parent:
            groups.setdefault(parent, []).append(f.get("name", ""))
    req_edges: list[tuple[str, list[str]]] = []
    for f in features:
        reqs = [r for r in (f.get("requires") or []) if r]
        if reqs:
            req_edges.append((f.get("name", ""), reqs))
    if not groups and not req_edges:
        return []
    lines = ["**Feature relationships (from Agentifier's graph contract):**\n"]
    if groups:
        lines.append("- `composed_under` (coordinator → members):")
        for coord in sorted(groups):
            members = ", ".join(m for m in groups[coord] if m)
            lines.append(f"  - {coord}: {members}")
    if req_edges:
        lines.append("- `requires` (feature → producers it consumes):")
        for name, reqs in req_edges:
            lines.append(f"  - {name}: {', '.join(reqs)}")
    lines.append("")
    return lines


def explicitly_rejected_lines(
    ai_features: dict[str, Any], consumer: str = "phaser"
) -> list[str]:
    """Name the candidates the developer deselected, so they are not re-added.

    The instruction differs by consumer because the failure differs. Phaser must
    not *phase* a rejected candidate. StackAdvisor must not *provision a mechanism*
    for one — and, crucially, must still give the product feature its ordinary
    stack: `source_citations` is a Ragmeister spine feature with no catalog node
    that correctly carries stores, an API and a UI and no provider. Telling
    StackAdvisor "do not plan phases for these" would say nothing about the
    decision it actually makes; telling it to drop the feature entirely would strip
    a spine feature of the persistence it needs (D-SC56).
    """
    rejected = ai_features.get("explicitly_rejected") or []
    names = [
        r.get("name", "") for r in rejected if isinstance(r, dict) and r.get("name")
    ]
    if not names:
        return []
    if consumer == "stack":
        return [
            "\n**Explicitly rejected by the developer — these are NOT AI features:** "
            + ", ".join(names),
            "Agentifier never tiered, coordinated or specced these, so there is no "
            "decision behind them to honour. Do NOT give any of them a provider "
            "capability, an infrastructure entry, or a library that exists to serve "
            "them — a mechanism you pick here would be invented, not chosen. Where a "
            "rejected name is also an MVP feature in the spine, it still needs its "
            "ordinary stack (its store, its API, its UI); it just is not built with "
            "AI.",
            "",
        ]
    return [
        "**Explicitly rejected by the developer — do NOT plan phases for these:** "
        + ", ".join(names),
        "",
    ]


def ai_features_for_phaser(
    ai_features: dict[str, Any], revision_version: int | None = None
) -> str:
    """Full AI features context for Phaser: index table, complete specs, edges.

    Phaser is the agent that sequences the build and authors the per-phase
    ``features[]`` declaration, so it receives the *entire* Agentifier surface
    (D-PS3 option B): every Spec Drafter field, the tier analysis behind each
    tier, graph edges, scope (including ``cross_feature``), infrastructure
    substrate, cross-cutting decisions, and the rejected set. It cannot curate
    what it has not been shown — and it cannot write an honest per-phase
    ``scope_note`` about part of a feature whose parts it never saw.

    Spec bodies are rendered by ``spec4.feature_specs`` — the same renderer the
    phase-file preamble uses — so what Phaser reads and what the coding agent
    receives cannot drift.

    Note the asymmetry with the phase files: Phaser sees ``provider_strategy``
    here, but it is excluded from the rendered phases (D-PS6 A'), where
    StackAdvisor's ratified ``tech_stack_spec`` is the authority.

    In a revision round (``revision_version`` set to the active round's version),
    the feature set is partitioned by the deterministic ``introduced_in_version``
    stamp: features introduced in this round are rendered as the phase/priority
    table to plan, while features from earlier rounds are listed as already-built
    context the agent must not re-phase. ``introduced_in_version`` is the hard
    phase/don't-phase split (code-owned, deterministic); the vision delta's
    ``modified`` set stays soft context in the seed's revision note, kept out of
    this partition to avoid the brittle ``linked_vision_features`` name-join. With
    ``revision_version`` left ``None`` (greenfield or plain brownfield), the output
    is unchanged.
    """
    features: list[dict[str, Any]] = ai_features.get("ai_features") or []
    if not features:
        return ""
    # Full feature set for the relationships block below — captured before the
    # revision partition reassigns ``features`` to the to-phase slice, so the
    # graph-contract edges render completely regardless of the partition.
    all_feats = list(features)

    features, established = _phaser_revision_partition(features, revision_version)

    lines: list[str] = []
    _phaser_established_lines(established, lines)

    if not features:
        # Revision round whose delta touched no AI features: established context
        # only, nothing new to phase.
        return "\n".join(lines)

    _phaser_index_table(features, revision_version, lines)
    _phaser_priority_guidance(features, lines)
    _phaser_shape_guidance(features, lines)
    lines.append("")
    lines.extend(feature_relationship_lines(all_feats))

    # Full spec bodies — the artifact the phase files attach verbatim.
    lines.append("**Full implementation specs (from Agentifier's Spec Drafter):**\n")
    for f in features:
        name = f.get("name", "")
        fid = f.get("id", "")
        lines.append(f"### {name} (`{fid}`)\n")
        lines.extend(render_feature_block(f))
    lines.extend(render_cross_cutting(ai_features.get("cross_cutting")))
    lines.extend(explicitly_rejected_lines(ai_features))
    _phaser_catalog_notes(ai_features, lines)
    return "\n".join(lines)


def _phaser_revision_partition(
    features: list[dict[str, Any]], revision_version: int | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split by ``introduced_in_version``: to-phase now, already established."""
    established: list[dict[str, Any]] = []
    if revision_version is not None:
        to_phase: list[dict[str, Any]] = []
        for f in features:
            iv = f.get("introduced_in_version")
            if isinstance(iv, int) and iv == revision_version:
                to_phase.append(f)
            else:
                established.append(f)
        features = to_phase
    return features, established


def _phaser_established_lines(
    established: list[dict[str, Any]], lines: list[str]
) -> None:
    """The do-NOT-re-phase note for features from earlier rounds."""
    if established:
        names = ", ".join(f.get("name", "") for f in established)
        lines.append(
            "**Already-implemented AI features — in place, do NOT create phases "
            f"for these:** {names}\n"
        )


def _phaser_index_table(
    features: list[dict[str, Any]], revision_version: int | None, lines: list[str]
) -> None:
    """The feature index table and the exact-id instruction."""
    header = (
        "**New/changed AI features for this revision — plan phases for these:**\n"
        if revision_version is not None
        else "**AI features spec (from Agentifier) — use phase_priority to decide when to implement each:**\n"
    )
    lines.extend(
        [
            header,
            "| Feature | id | Kind | Tier | Scope | Phase Priority |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for f in features:
        name = f.get("name", "")
        fid = f.get("id", "")
        kind = "infrastructure" if f.get("kind") == INFRA_KIND else "feature"
        tier = f.get("tier", "")
        scope = f.get("scope", "")
        priority = f.get("phase_priority", "mvp")
        lines.append(f"| {name} | `{fid}` | {kind} | {tier} | {scope} | {priority} |")
    lines.append("")
    lines.append(
        "The `id` column is the exact key to use in each phase's `features` array."
    )


def _phaser_priority_guidance(features: list[dict[str, Any]], lines: list[str]) -> None:
    """Phasing guidance by ``phase_priority``: steel_thread, mvp, v2/future."""
    lines.append("\nPhasing guidance:")
    steel = [
        f.get("name", "") for f in features if f.get("phase_priority") == "steel_thread"
    ]
    if steel:
        lines.append(
            f"- **steel_thread** features belong in Phase 1 or Phase 2: {', '.join(steel)}"
        )
    mvp = [f.get("name", "") for f in features if f.get("phase_priority") == "mvp"]
    if mvp:
        lines.append(
            f"- **mvp** features must be implemented before the first release: {', '.join(mvp)}"
        )
    v2 = [
        f.get("name", "")
        for f in features
        if f.get("phase_priority") in ("v2", "future")
    ]
    if v2:
        lines.append(
            f"- **v2/future** features may be deferred post-MVP: {', '.join(v2)}"
        )


def _phaser_shape_guidance(features: list[dict[str, Any]], lines: list[str]) -> None:
    """Phasing guidance by node shape: infrastructure and cross_feature."""
    infra = [f.get("name", "") for f in features if f.get("kind") == INFRA_KIND]
    if infra:
        lines.append(
            "- **infrastructure** nodes are shared substrate, not user-selected "
            "capabilities. Each must be stood up in the same phase as its first "
            f"consumer or earlier: {', '.join(infra)}"
        )
    cross_feat = [
        f.get("name", "") for f in features if f.get("scope") == "cross_feature"
    ]
    if cross_feat:
        lines.append(
            "- **cross_feature** features span more than one vision feature. Treat "
            "them as shared surface — sequence them where every consumer can reach "
            f"them, not inside one consumer's phase: {', '.join(cross_feat)}"
        )


def _phaser_catalog_notes(ai_features: dict[str, Any], lines: list[str]) -> None:
    """Consolidation notes and catalog references."""
    consolidation = ai_features.get("consolidation") or []
    if consolidation:
        lines.append("**Consolidation notes:**\n")
        lines.extend(f"- {c}" for c in consolidation if c)
        lines.append("")
    references = ai_features.get("references") or []
    if references:
        lines.append("**Catalog references:**\n")
        lines.extend(f"- {r}" for r in references if r)
        lines.append("")


def ai_features_for_deployer(
    ai_features: dict[str, Any] | None,
    stack: dict[str, Any] | None = None,
) -> str:
    """AI deployment context for Deployer: providers, tiers, budgets (D-DE7).

    What a deployment plan needs about the AI side is narrow and specific: which
    providers it must configure access to, what latency and cost the features are
    budgeted for, and whether evals and guardrails need a home. This renders
    exactly that.

    **Providers come from the stack, not the catalog.** The stack's ``providers``
    block is the ratified decision (D-PH6 A′); the catalog's
    ``cross_cutting.provider_strategy`` is a recommendation it supersedes, and
    rendering both would give one decision two owners — so the recommendation is
    no longer surfaced here. Each provider renders as its ``model_family`` — the
    family is the decision, and a plan must never pin a specific model id — with
    the roles and tiers it serves, its ``credentials_env``, and its
    ``endpoint_env``. A provider carrying ``endpoint_env`` is self-hosted: it is
    infrastructure to run, not a key to hold, which is a materially different
    deployment.

    **Budgets** (``p95_latency``, ``cost_per_call``) are per-feature targets the
    deployment has to meet — they drive timeouts, autoscaling, and capacity
    planning, and reach Deployer through no other channel.

    **Evals and safety** are reported as counts only. Deployer's job is to give
    them a cadence and an enforcement point; the approaches and constraints
    themselves (gold-standard datasets, redaction rules) are the coding agent's
    to implement, and would cost several times this whole projection to carry.

    Infrastructure nodes are deliberately absent: the catalog's infrastructure
    ids are the same substrate the stack digest already lists for provisioning.

    Returns ``""`` when the project has no AI features.
    """
    features: list[dict[str, Any]] = (ai_features or {}).get("ai_features") or []
    if not features:
        return ""

    lines = ["**AI features spec — deployment context:**\n"]

    _deployer_provider_lines(stack, lines)
    _deployer_tier_lines(features, lines)
    _deployer_budget_lines(features, lines)
    _deployer_eval_lines(features, lines)

    lines.append("")
    return "\n".join(lines)


def _deployer_provider_lines(stack: dict[str, Any] | None, lines: list[str]) -> None:
    """Providers to configure access to, from the ratified stack (D-PH6 A')."""
    inner = (stack or {}).get("stack_spec") if isinstance(stack, dict) else None
    spec = inner if isinstance(inner, dict) else (stack or {})
    providers = spec.get("providers") if isinstance(spec, dict) else None
    if isinstance(providers, dict) and providers:
        lines.append(
            "**Providers to configure access to** (from the ratified stack). The "
            "family is the decision — do not pin a specific model id in the plan:"
        )
        for name, prov in providers.items():
            _deployer_provider_entry(name, prov, lines)
        lines.append("")


def _deployer_provider_entry(name: str, prov: Any, lines: list[str]) -> None:
    """One provider: model family, roles, tiers, credentials, endpoint, fallback."""
    if not isinstance(prov, dict):
        return
    family = str(prov.get("model_family") or "").strip()
    roles, tiers = _provider_roles_and_tiers(prov)
    head = f"- {name}"
    if family:
        head += f" — model family: {family}"
    if roles:
        head += f" ({', '.join(roles)})"
    lines.append(head)
    if tiers:
        lines.append(f"  - serves tiers: {', '.join(tiers)}")
    creds = str(prov.get("credentials_env") or "").strip()
    if creds:
        lines.append(f"  - credentials (environment): {creds}")
    endpoint = str(prov.get("endpoint_env") or "").strip()
    if endpoint:
        lines.append(
            f"  - self-hosted: reachable at `{endpoint}` — this is a model "
            f"host to run and size, not a third-party key to hold"
        )
    fallback = str(prov.get("fallback") or "").strip()
    if fallback:
        lines.append(f"  - fallback: {fallback}")


def _provider_roles_and_tiers(prov: dict[str, Any]) -> tuple[list[str], list[str]]:
    """The sorted role and tier sets a provider's capabilities declare."""
    caps = [c for c in (prov.get("capabilities") or []) if isinstance(c, dict)]
    roles = sorted({str(c.get("role")) for c in caps if c.get("role")})
    tiers = sorted({str(c.get("tier")) for c in caps if c.get("tier")})
    return roles, tiers


def _deployer_tier_lines(features: list[dict[str, Any]], lines: list[str]) -> None:
    """AI feature tiers in use, and the tool-calling key requirement."""
    tiers_in_use = sorted({str(f.get("tier")) for f in features if f.get("tier")})
    if tiers_in_use:
        lines.append(f"- AI feature tiers in use: {', '.join(tiers_in_use)}")
    if any(
        TIER_ORDER_FOR_SUMMARY.get(str(f.get("tier") or ""), 0) >= 5  # noqa: PLR2004  # tool_agent and up (TIER_ORDER_FOR_SUMMARY)
        for f in features
    ):
        lines.append(
            "- Tool-calling features require LLM API keys in environment configuration"
        )


def _deployer_budget_lines(features: list[dict[str, Any]], lines: list[str]) -> None:
    """Per-feature ``p95_latency`` / ``cost_per_call`` targets."""
    budget_lines: list[str] = []
    for f in features:
        budgets = f.get("budgets")
        if not isinstance(budgets, dict):
            continue
        parts = []
        p95 = str(budgets.get("p95_latency") or "").strip()
        cost = str(budgets.get("cost_per_call") or "").strip()
        if p95:
            parts.append(f"p95 latency {p95}")
        if cost:
            parts.append(f"cost/call {cost}")
        if parts:
            budget_lines.append(f"- {f.get('id') or f.get('name')}: {'; '.join(parts)}")
    if budget_lines:
        lines.append("")
        lines.append(
            "**Per-feature budgets** — the latency and cost targets this deployment "
            "has to meet; they drive timeouts, autoscaling, and capacity planning:"
        )
        lines.extend(budget_lines)


def _deployer_eval_lines(features: list[dict[str, Any]], lines: list[str]) -> None:
    """Eval and safety counts (counts only, by design)."""
    n_eval = sum(1 for f in features if f.get("eval_approach"))
    n_safety = sum(1 for f in features if f.get("privacy_safety"))
    if n_eval or n_safety:
        lines.append("")
        lines.append(
            f"**Evals and safety** — {n_eval} of {len(features)} AI features declare "
            f"an eval approach and {n_safety} declare safety constraints. The plan "
            f"needs an eval cadence and a place where guardrails are enforced; the "
            f"approaches and constraints themselves are the coding agent's to build."
        )


def designer_affordance_hints(mode: str, authority: str, tier_order: int) -> list[str]:
    """UX affordance hints for a surface, from its invocation mode / authority / tier.

    Mode drives the wait model (streaming vs. blocking vs. background), authority
    drives whether the user confirms or can dismiss, and multi-step tiers
    (chained_calls and up) warrant visible progress.
    """
    hints: list[str] = []
    if mode == "streaming":
        hints.append("stream the output progressively (streaming/typing indicator)")
    elif mode == "asynchronous":
        hints.append(
            "runs in the background — surface results as a notification, alert, or "
            "status badge rather than a blocking wait"
        )
    if authority == "confirm":
        hints.append("require explicit confirmation before the action commits")
    elif authority == "suggest":
        hints.append("present as a suggestion the user can accept or dismiss")
    if tier_order >= 6:  # noqa: PLR2004  # chained_calls and up are inherently multi-step
        hints.append("show multi-step progress/status while it runs")
    return hints


def short_text(text: str, limit: int = 220) -> str:
    """Collapse whitespace and truncate ``text`` to ``limit`` chars for prompts."""
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def ai_features_for_designer(ai_features: dict[str, Any]) -> str:
    """User-facing surface graph for Designer.

    Projects the catalog into the surfaces Designer must actually build, rather
    than a flat list of affordance hints. Each top-level ``scope == "feature"``
    (non-infrastructure) node is a user-facing *surface* carrying the substance
    needed to design it for real: the vision feature(s) it serves, its trigger,
    the inputs the user provides, the result to show, and a UX affordance derived
    from its invocation mode / decision authority / tier. Each surface's
    ``composed_under`` members are nested beneath it as in-surface affordances
    (citations, verification, routing, related items), never standalone screens.
    Infrastructure nodes and unparented internal steps never surface.

    Returns ``""`` when the catalog has no user-facing AI surface, so a no-AI or
    deterministic-only build designs from the vision alone.
    """
    features: list[dict[str, Any]] = ai_features.get("ai_features") or []
    if not features:
        return ""

    surfaces = [
        f for f in features if f.get("scope") == "feature" and not _designer_is_infra(f)
    ]
    if not surfaces:
        return ""

    members_by_parent = _designer_members_by_parent(features)

    lines: list[str] = [
        "**User-facing AI surfaces** — each entry below is a real interaction the "
        "user has with an AI feature. Design each as a working surface on the "
        "appropriate screen: build its inputs into real controls, show its output "
        "as a real result, trigger it as described, and apply the noted affordance. "
        "These are surfaces to build, not features to advertise.\n"
    ]

    for f in surfaces:
        _designer_surface_lines(f, members_by_parent, lines)

    return "\n".join(lines)


def _designer_is_infra(f: dict[str, Any]) -> bool:
    """Infrastructure by tier or kind -- never a user-facing surface."""
    return f.get("tier") == "infrastructure" or f.get("kind") == "infrastructure"


def _designer_edge_state(f: dict[str, Any]) -> str:
    """The user-visible failure condition to design an empty/error state for."""
    fails = f.get("failure_modes")
    if isinstance(fails, list) and fails and isinstance(fails[0], dict):
        mode = fails[0].get("mode")
        if isinstance(mode, str) and mode.strip():
            return mode
    esc = f.get("escalation")
    return esc if isinstance(esc, str) else ""


def _designer_members_by_parent(
    features: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """``composed_under`` members grouped by parent surface name."""
    members_by_parent: dict[str, list[dict[str, Any]]] = {}
    for f in features:
        if f.get("scope") == "sub_feature" and not _designer_is_infra(f):
            parent = f.get("composed_under") or ""
            if parent:
                members_by_parent.setdefault(parent, []).append(f)
    return members_by_parent


def _designer_surface_lines(
    f: dict[str, Any],
    members_by_parent: dict[str, list[dict[str, Any]]],
    lines: list[str],
) -> None:
    """One user-facing surface: header, purpose, inputs, result, affordance."""
    name = f.get("name", "")
    tier = f.get("tier", "")
    tier_order = TIER_ORDER_FOR_SUMMARY.get(tier, 0)
    inv = f.get("invocation") or {}
    mode = inv.get("mode", "synchronous")
    trigger = inv.get("trigger", "")
    authority = f.get("decision_authority", "autonomous")
    served = f.get("linked_vision_features") or []

    header = f"### `{name}` (tier: {tier}, {mode})"
    if served:
        header += " — serves vision feature(s): " + ", ".join(served)
    lines.append(header)

    purpose = f.get("purpose", "")
    if purpose:
        lines.append(f"- Purpose: {short_text(purpose)}")
    if trigger:
        lines.append(f"- Triggered when: {short_text(trigger, 160)}")

    _designer_input_line(f, lines)
    outputs = f.get("outputs")
    primary_out = outputs.get("primary", "") if isinstance(outputs, dict) else ""
    if primary_out:
        lines.append(f"- Result to show: {short_text(primary_out)}")

    hints = designer_affordance_hints(mode, authority, tier_order)
    if hints:
        lines.append("- Affordance: " + "; ".join(hints))

    edge = _designer_edge_state(f)
    if edge:
        lines.append(f"- Edge state to design for: {short_text(edge, 160)}")

    members = members_by_parent.get(name) or []
    if members:
        _designer_member_lines(members, lines)
    lines.append("")


def _designer_input_line(f: dict[str, Any], lines: list[str]) -> None:
    """The ``User provides:`` line for one surface."""
    inputs = f.get("inputs")
    if isinstance(inputs, list) and inputs:
        rendered: list[str] = []
        for i in inputs:
            if not isinstance(i, dict):
                continue
            iname = i.get("name", "")
            idesc = short_text(i.get("description", ""), 90)
            req = "" if i.get("required", True) else " (optional)"
            rendered.append(f"{iname}{req}: {idesc}" if idesc else f"{iname}{req}")
        if rendered:
            lines.append("- User provides: " + "; ".join(rendered))


def _designer_member_lines(members: list[dict[str, Any]], lines: list[str]) -> None:
    """In-surface affordances nested under a surface."""
    lines.append(
        "- Within this surface, also design the user-visible output of its "
        "component steps — only those producing something the user sees "
        "(citations, confidence, routing, related items):"
    )
    for m in members:
        mname = m.get("name", "")
        mtier = m.get("tier", "")
        m_out = m.get("outputs")
        m_primary = m_out.get("primary", "") if isinstance(m_out, dict) else ""
        detail = short_text(m_primary or m.get("purpose", ""), 130)
        mauth = m.get("decision_authority", "autonomous")
        aff = (
            " [suggestion]"
            if mauth == "suggest"
            else (" [confirm]" if mauth == "confirm" else "")
        )
        lines.append(f"    - `{mname}` ({mtier}){aff}: {detail}")


# Framing fields kept in Designer's vision block (DR2). The per-feature substance
# now rides in the feature-specs block, so the raw vision dump is slimmed to the
# project-wide framing that shapes global design (name, one-line purpose, the UI
# surface, audiences, and differentiators for tone). `key_features_mvp`,
# monetization, references, and revision history are dropped as noise or
# duplication of the richer feature specs.
VISION_FRAMING_FIELDS: tuple[str, ...] = (
    "purpose",
    "ui_surface",
    "target_audience",
    "target_audiences",
    "differentiators",
)


def slim_vision_framing(vision: dict[str, Any] | None) -> dict[str, Any]:
    """Project the vision envelope to the framing fields Designer needs (DR2).

    Accepts any of the shapes Designer sees: the full envelope
    (``{"vision_statement": {"name", "vision": {...}}}``), the inner statement,
    or an already-flat framing dict. Returns ``{}`` when nothing usable is
    present, so the caller can skip the section.
    """
    if not isinstance(vision, dict):
        return {}
    inner = vision.get("vision_statement")
    if not isinstance(inner, dict):
        inner = vision
    vblock = inner.get("vision")
    if not isinstance(vblock, dict):
        vblock = inner
    out: dict[str, Any] = {}
    name = inner.get("name") or vblock.get("name")
    if name:
        out["name"] = name
    for key in VISION_FRAMING_FIELDS:
        val = vblock.get(key)
        if val:
            out[key] = val
    return out


def feature_specs_for_designer(feature_specs: dict[str, Any] | None) -> str:
    """Render Brainstormer's ``feature_specs.json`` as a Designer prompt block (DR1/DR3).

    Emits one behavioural block per vision feature (the ``DESIGNER_SPEC_FIELDS``
    subset, no graph lines), the project-wide non-functional goals, and — as an
    advisory domain vocabulary (DR3, soft grounding) — the union of the features'
    ``entities``. The vocabulary is offered for the model to reflect in its
    manifest entities where the concept is data the UI presents or edits; it is
    deliberately not a deterministic overwrite, since these are conceptual domain
    nouns, not UI data entities. Returns ``""`` when no specs are present.
    """
    feats = (feature_specs or {}).get("features") or []
    if not feats:
        return ""

    lines: list[str] = [
        "**Feature specifications** — the authoritative behavioural spec for each "
        "product feature. Design each feature's surface(s) to satisfy these: build "
        "its inputs as real controls, show its outputs as a real result, trigger it "
        "as described, and design its failure modes as empty/error states.\n"
    ]

    entities: list[str] = []
    seen: set[str] = set()
    for f in feats:
        if not isinstance(f, dict):
            continue
        name = f.get("name") or f.get("id") or ""
        lines.append(f"### `{name}`")
        lines.extend(
            render_feature_block(f, fields=DESIGNER_SPEC_FIELDS, include_graph=False)
        )
        lines.append("")
        for ent in f.get("entities") or []:
            if isinstance(ent, str) and ent not in seen:
                seen.add(ent)
                entities.append(ent)

    nfr = (feature_specs or {}).get("nfr_goals") or []
    if isinstance(nfr, list) and nfr:
        lines.append("**Non-functional goals (project-wide):**")
        for goal in nfr:
            if isinstance(goal, str) and goal.strip():
                lines.append(f"- {goal.strip()}")
        lines.append("")

    if entities:
        lines.append(
            "**Domain vocabulary** — the concepts these features operate on: "
            + ", ".join(entities)
            + ". Reflect these in your manifest `entities` where they are data the "
            "UI presents or edits; you may add UI-specific entities (a list item, a "
            "form record) as needed. This is a vocabulary to honour, not a "
            "replacement for UI-appropriate entities."
        )
        lines.append("")

    return "\n".join(lines)


def feature_specs_for_stack(
    feature_specs: dict[str, Any] | None,
    ai_features: dict[str, Any] | None = None,
) -> str:
    """Render Brainstormer's ``feature_specs.json`` as a StackAdvisor block (D-SC1).

    The product-feature spine is StackAdvisor's *base* input: one behavioural
    block per MVP feature — AI *and* non-AI — so every feature, not only the AI
    ones, gets stack coverage. The AI catalog projection
    (``ai_features_for_stack``) is enrichment layered on the AI subset; a feature
    an AI-catalog node *serves* is tagged ``(AI)`` here so the two views connect
    without the reader mistaking one feature for two. The serves relation is read
    from each node's ``vision_grounding.served_features[].id`` — never identity, as
    an AI node's own id (a capability surface id like
    ``adaptive_investigation_orchestration``) is distinct from the product-feature
    id it serves (``adaptive_investigation``). Per D-SC7 the product *signal* comes
    from this direct spine — each feature exactly once — not from vision_grounding's
    embedded feature copies (which repeat a product spec across every AI node that
    serves it); vision_grounding is consulted here only for the id join, not for
    content.

    Surfaces per feature the behavioural fields that force a component choice
    (``STACK_SPEC_FIELDS``) and the product-level ``dependencies`` (a chain signal,
    distinct from the AI ``requires`` DAG). The union of ``entities`` is offered as
    an advisory data model (D-SC6): a vocabulary and persistence signal, never a
    deterministic store mapping — the mechanism stays StackAdvisor's to choose.
    Finally, the project-wide ``nfr_goals`` are listed each keyed by a stable
    ``nfr_<slug>`` id (D-SC2), for the model to reference in an entry's
    ``satisfies_nfr`` when a stack decision is what makes a goal achievable.
    Returns ``""`` when no specs are present.
    """
    feats = (feature_specs or {}).get("features") or []
    if not feats:
        return ""

    ai_served = ai_served_feature_ids(ai_features)

    lines: list[str] = [
        "**Feature specifications (from Brainstormer) — the authoritative "
        "behavioural spec for every product feature. This is the base for your "
        "stack: choose libraries, persistence, and infrastructure that satisfy "
        "each feature's inputs, outputs, trigger, and reliability needs. Features "
        "tagged (AI) are also specified as AI capabilities below, where their "
        "implementation detail lives — treat that as enrichment on the same "
        "feature, not a second one.**\n"
    ]

    entities: list[str] = []
    seen: set[str] = set()
    for f in feats:
        if not isinstance(f, dict):
            continue
        _stack_feature_spec_lines(f, ai_served, lines)
        for ent in f.get("entities") or []:
            if isinstance(ent, str) and ent not in seen:
                seen.add(ent)
                entities.append(ent)

    _stack_entity_vocabulary(entities, lines)
    _stack_nfr_lines(feature_specs, lines)

    return "\n".join(lines)


def _stack_feature_spec_lines(
    f: dict[str, Any], ai_served: set[str], lines: list[str]
) -> None:
    """One product feature's spine block for StackAdvisor, tagged (AI)."""
    fid = str(f.get("id") or "")
    name = f.get("name") or fid or "unnamed"
    tag = " (AI)" if (fid and fid in ai_served) or name in ai_served else ""
    header = f"### `{name}`"
    if fid:
        # The linkage rules instruct the model to tag entries with these ids
        # (D-SC3); rendering only the name left it to infer them (D-SC14).
        header += f" — id: `{fid}`"
    lines.append(f"{header}{tag}")
    lines.extend(render_feature_block(f, fields=STACK_SPEC_FIELDS, include_graph=False))
    deps = [str(d).strip() for d in (f.get("dependencies") or []) if str(d).strip()]
    if deps:
        lines.append(f"- depends on: {', '.join(deps)}")
    lines.append("")


def _stack_entity_vocabulary(entities: list[str], lines: list[str]) -> None:
    """The advisory domain-vocabulary note (D-SC6)."""
    if entities:
        lines.append(
            "**Domain vocabulary** — the data model these features operate on: "
            + ", ".join(entities)
            + ". These domain nouns are the persistence signal: features sharing "
            "entities read and write shared data, which drives your data-store and "
            "schema choices. Honour them as the vocabulary for stack decisions; the "
            "mechanism (which store, which schema) is yours to choose."
        )
        lines.append("")


def _stack_nfr_lines(feature_specs: dict[str, Any] | None, lines: list[str]) -> None:
    """Project-wide ``nfr_goals`` keyed by ``nfr_<slug>`` (D-SC2)."""
    nfr_lines = [
        f"- `nfr_{slug(g.strip())}`: {g.strip()}"
        for g in ((feature_specs or {}).get("nfr_goals") or [])
        if isinstance(g, str) and g.strip()
    ]
    if nfr_lines:
        lines.append(
            "**Non-functional goals (project-wide)** — operational, performance, and "
            "reliability targets the stack must make achievable, each with a stable "
            "`nfr_<slug>` id. When a stack decision is what makes one of these achievable, "
            "record the id in that entry's `satisfies_nfr` (see the NFR linkage "
            "instruction), so the downstream planner can thread the goal into the phase "
            "that builds it:"
        )
        lines.extend(nfr_lines)
        lines.append("")


def ai_served_feature_ids(ai_features: dict[str, Any] | None) -> set[str]:
    """Product-feature ids/names some surfaced AI node serves.

    Derived from ``vision_grounding.served_features`` on non-infrastructure
    catalog nodes — the only sound "is this feature AI-backed" signal without
    the manifest. Used for the spine's ``(AI)`` tag and as the guard in
    ``excluded_feature_ids`` (a served feature is never excluded).
    """
    served: set[str] = set()
    for node in (ai_features or {}).get("ai_features") or []:
        if not isinstance(node, dict) or node.get("kind") == INFRA_KIND:
            continue
        grounding = node.get("vision_grounding") or {}
        for sf in grounding.get("served_features") or []:
            if isinstance(sf, dict):
                for key in ("id", "name"):
                    if sf.get(key):
                        served.add(str(sf[key]))
    return served


def excluded_feature_ids(
    feature_specs: dict[str, Any] | None,
    ai_features: dict[str, Any] | None,
) -> set[str]:
    """Spine feature ids excluded from the plan by the Agentifier selection.

    D-PH1i / D-PH2b — the single source of truth for the excluded disposition,
    shared by the spine renderer (which tags) and ``check_phase_coverage``
    (which enforces), so the tag and the enforcement can never drift.

    Computed, not judged: a spine feature is excluded when a name in the AI
    catalog's ``explicitly_rejected`` matches its id/name (or their slugs)
    AND no surfaced AI node serves it via ``vision_grounding``. Rejected
    *members* (deselected sub-capabilities) match no spine id and never
    exclude anything; the serves-join wins over a same-named rejection.
    """
    feats = (feature_specs or {}).get("features") or []
    if not feats:
        return set()
    rejected: set[str] = set()
    for entry in (ai_features or {}).get("explicitly_rejected") or []:
        name = entry.get("name") if isinstance(entry, dict) else entry
        if name:
            rejected.add(str(name))
            rejected.add(slug(str(name)))
    if not rejected:
        return set()
    served = ai_served_feature_ids(ai_features)
    out: set[str] = set()
    for f in feats:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("id") or "")
        name = str(f.get("name") or fid)
        if not fid or fid in served or name in served:
            continue
        if (
            fid in rejected
            or slug(fid) in rejected
            or name in rejected
            or slug(name) in rejected
        ):
            out.add(fid)
    return out


def feature_specs_for_phaser(
    feature_specs: dict[str, Any] | None,
    ai_features: dict[str, Any] | None = None,
) -> str:
    """Render Brainstormer's ``feature_specs.json`` as Phaser's spine block (D-PH1a).

    The product-feature spine is Phaser's *base* input: one behavioural block per
    MVP feature — AI *and* non-AI — so every feature the phases must build is on
    the table, including every feature of a no-AI app (which previously reached
    Phaser only as vision prose). The AI catalog block remains enrichment on the
    AI subset; a feature an AI-catalog node *serves* is tagged ``(AI)`` here so
    the two views connect without the reader mistaking one feature for two. Per
    the D-SC7 discipline the product signal comes from this direct spine — each
    feature exactly once — and ``vision_grounding`` is consulted only for the
    serves id join, never for content.

    Surfaces per feature the behavioural fields Phaser turns into phase content
    (``PHASER_PRODUCT_SPEC_FIELDS``: success criteria are verification raw
    material, failure modes are risk raw material, inputs/outputs anchor
    instructions), plus the product-level ``dependencies`` stated as build-order
    guidance (producer no later than consumer — a distinct graph from the AI
    ``requires`` DAG). The union of ``entities`` is offered as the shared domain
    vocabulary so phases name the same nouns consistently. Project-wide
    ``nfr_goals`` are listed with stable ``nfr_<slug>`` ids (D-SC2) and the
    Phaser-side citation rule (D-PH1c): cite the id in the verification criteria
    of the phases that build the claiming entries' features; never invent a
    stack claim for an unclaimed goal. Returns ``""`` when no specs are present.
    """
    feats = (feature_specs or {}).get("features") or []
    if not feats:
        return ""

    ai_served = ai_served_feature_ids(ai_features)
    excluded = excluded_feature_ids(feature_specs, ai_features)

    lines: list[str] = [
        "**Feature specifications (from Brainstormer) — the authoritative "
        "behavioural spec for every product feature. This is the base of your "
        "plan: sequence phases so that ALL of these features are built — "
        "except any feature tagged (excluded), which the developer removed "
        "from this plan via the Agentifier selection — using "
        "each feature's success criteria as verification raw material and its "
        "failure modes as risk-assessment raw material. `depends on` means the "
        "named feature must be built no later than the feature that depends on "
        "it. Features tagged (AI) are also specified as AI capabilities in the "
        "AI features context below, where their implementation detail lives — "
        "treat that as enrichment on the same feature, not a second one. "
        "Declare each product feature a phase builds in that phase's "
        "`features` array using these exact ids; AI capabilities are declared "
        "separately in `capabilities` using the AI catalog ids.**\n"
    ]

    entities: list[str] = []
    seen: set[str] = set()
    for f in feats:
        if not isinstance(f, dict):
            continue
        _phaser_feature_spec_lines(f, ai_served, excluded, lines)
        for ent in f.get("entities") or []:
            if isinstance(ent, str) and ent not in seen:
                seen.add(ent)
                entities.append(ent)

    _phaser_entity_vocabulary(entities, lines)
    _phaser_nfr_lines(feature_specs, lines)

    return "\n".join(lines)


def _phaser_feature_spec_lines(
    f: dict[str, Any], ai_served: set[str], excluded: set[str], lines: list[str]
) -> None:
    """One product feature's spine block for Phaser, tagged (AI) or (excluded)."""
    fid = str(f.get("id") or "")
    name = f.get("name") or fid or "unnamed"
    served = (fid and fid in ai_served) or name in ai_served
    if fid in excluded:
        tag = (
            " (excluded — AI implementation rejected at the Agentifier "
            "panel; to include it, revisit the Agentifier selection)"
        )
    else:
        tag = " (AI)" if served else ""
    header = f"### `{name}`"
    if fid:
        header += f" — id: `{fid}`"
    lines.append(f"{header}{tag}")
    lines.extend(
        render_feature_block(f, fields=PHASER_PRODUCT_SPEC_FIELDS, include_graph=False)
    )
    deps = [str(d).strip() for d in (f.get("dependencies") or []) if str(d).strip()]
    if deps:
        lines.append(
            f"- depends on: {', '.join(deps)} (build these no later than "
            f"`{fid or name}`)"
        )
    lines.append("")


def _phaser_entity_vocabulary(entities: list[str], lines: list[str]) -> None:
    """The shared domain-vocabulary note."""
    if entities:
        lines.append(
            "**Domain vocabulary** — the data model these features operate on: "
            + ", ".join(entities)
            + ". Use these nouns consistently across every phase's instructions "
            "so phase N names the same concepts as phase 1; do not invent "
            "synonyms or parallel schemas for concepts already named here."
        )
        lines.append("")


def _phaser_nfr_lines(feature_specs: dict[str, Any] | None, lines: list[str]) -> None:
    """Project-wide ``nfr_goals`` with the D-PH1c citation rule."""
    nfr_lines = [
        f"- `nfr_{slug(g.strip())}`: {g.strip()}"
        for g in ((feature_specs or {}).get("nfr_goals") or [])
        if isinstance(g, str) and g.strip()
    ]
    if nfr_lines:
        lines.append(
            "**Non-functional goals (project-wide)** — each with a stable "
            "`nfr_<slug>` id. The stack spec's `satisfies_nfr` fields record "
            "which stack choices make each goal achievable (the stack signal "
            "digest below indexes them). Cite the `nfr_<slug>` id in the "
            "verification criteria of the phases that build the claiming "
            "entries' features, so each goal is checked where it is delivered. "
            "A goal no stack entry claims must be surfaced to the developer as "
            "unclaimed — never invent a stack claim for it:"
        )
        lines.extend(nfr_lines)
        lines.append("")
