"""Agentifier orchestrator agent.

Phase 1 — Catalog: coordinates Scout and Tier Analyst sub-agents, then conducts
an opinionated-with-override conversation to lock tier decisions into ai_catalog.

Phase 2 — Spec drafting: for each accepted feature, invokes Spec Drafter
(StreamingSubAgent), enriches references via Reference Verifier, and produces
the final ai_features.json.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import os
import pathlib
import queue
import re
import threading
import uuid
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

from spec4 import project_manager, llm, websearch
from spec4.agentifier.composer import (
    ComposerAgent,
    ComposerInput,
    ComposerOutput,
    Composition,
)
from spec4.agentifier.cross_cutting_analyst import (
    CROSS_CUTTING_TOPICS,
    SKIPPABLE_TOPICS,
    CrossCuttingAnalyst,
    CrossCuttingInput,
    warranted_topics,
)
from spec4.agentifier.linker import (
    LinkerAgent,
    LinkerInput,
    LinkerOutcome,
    apply_overlay,
)
from spec4.agentifier.grounding import build_grounding
from spec4.agentifier.infra_expander import expand_infrastructure
from spec4.agentifier.panel_closure import close_selection
from spec4.agentifier.pattern_loader import load_patterns
from spec4.agentifier.requires_reconciler import reconcile_requires
from spec4.agentifier.prioritizer import (
    PRIORITIES,
    PrioritizerAgent,
    PrioritizerInput,
    PrioritizerOutcome,
    normalize_priorities,
)
from spec4.agentifier.prioritizer import apply_overlay as apply_priority_overlay
from spec4.agentifier.scout import (
    Candidate,
    ScoutAgent,
    ScoutInput,
    ScoutOutcome,
    ScoutOutput,
)
from spec4.agentifier.spec_drafter import SpecDrafterAgent, SpecDrafterInput
from spec4.agentifier.subagents import SubAgentRegistry
from spec4.agentifier.tier_analyst import (
    TierAnalystAgent,
    TierAnalystInput,
    TierAnalystOutput,
    _existing_ai_context,
)
from spec4.agents._utils import (
    _abandon_reask,
    _artifact_fallback,
    _artifact_reask_prompt,
    _artifact_reask_status,
    _drop_orphan_or_route_to_fresh_start,
    _extract_json_block,
    _last_assistant_text,
    _reask_for_artifact,
    _replay_last_assistant,
    _stream_suppressing_json,
    _suppressed_as_artifact,
    slug,
)
from spec4.app_constants import FF_PROMPT, STATE_AGENTIFIER_COMPLETE, STATE_IN_PROGRESS

_DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"
_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sub-agent registry
# ---------------------------------------------------------------------------

_registry = SubAgentRegistry()
_registry.register(ScoutAgent())
_registry.register(LinkerAgent())
_registry.register(ComposerAgent())
_registry.register(TierAnalystAgent())
_registry.register(SpecDrafterAgent())
_registry.register(CrossCuttingAnalyst())
_registry.register(PrioritizerAgent())

# ---------------------------------------------------------------------------
# Async → sync streaming bridge
# ---------------------------------------------------------------------------


def _iter_async_gen(async_gen: Any) -> Generator[str, None, None]:
    """Bridge an async generator to a synchronous generator.

    Runs the async generator in a dedicated daemon thread and drains it
    into a queue, yielding each chunk in the calling thread. Thread-safe.
    """
    q: queue.Queue[str | BaseException | None] = queue.Queue()

    async def _drain() -> None:
        try:
            async for chunk in async_gen:
                q.put(chunk)
        except BaseException as exc:
            q.put(exc)
        finally:
            q.put(None)  # sentinel

    t = threading.Thread(target=asyncio.run, args=(_drain(),), daemon=True)
    t.start()
    try:
        while True:
            item = q.get()
            if item is None:
                break
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        t.join()


# ---------------------------------------------------------------------------
# Phase 1 — Catalog: system prompt
# ---------------------------------------------------------------------------

ORCHESTRATOR_SYSTEM_PROMPT = """\
You are Agentifier, an AI integration advisor embedded in the Spec4 planning
pipeline. Scout and Tier Analyst have already analysed the project; you have
been pre-loaded with a list of candidates and their tier recommendations. Your
job is to walk the developer through each candidate ONE AT A TIME, record their
decisions, and produce the final ai_catalog JSON.

**The tier ladder (cheapest → most complex):**
1. deterministic — rule-based logic, no model inference
2. embeddings — semantic similarity / classification via vector representations
3. single_call — one LLM invocation, prompt in / completion out
4. rag — retrieval-augmented generation: grounded in a knowledge source
5. tool_agent — LLM that calls tools or external APIs
6. chained_calls — multiple sequential LLM calls, output of one feeds the next
7. planning_agent — LLM that produces a plan and self-directs execution
8. orchestrated_subagents — coordinator LLM dispatches specialised sub-agents
9. multi_agent_collaboration — multiple peer agents with shared state/memory

**Conversation rules:**

1. Present ONE candidate per response — never two.
2. For each candidate present, in order:
   a) The candidate name, scope, and description (one sentence).
   b) Where the candidate sits among the other features — ONLY when the seed \
lists these relationships. State whether it is a sub-feature of a coordinator, \
which sub-features it coordinates, and what it uses the output of or its output \
feeds, so the developer sees it in relation to the others rather than in \
isolation. Present these relationships exactly as the seed gives them; do not \
infer or invent edges, and do not mention relationships the seed omits.
   c) Tier Analyst's recommendation in bold, followed by the rationale paragraph.
   d) The compared_to_next_tier_down articulation — phrased as "Going with \
[cheaper_tier] instead would mean…" — so the developer can push back if they \
think the recommendation over-engineers.
   e) If borderline=true, surface the seams: "This is a borderline call — watch \
for [seams]. If [trigger], escalate to [next tier]."
   f) A numbered list of all nine tiers as alternatives. Always include a final \
option: "10. Suggest your own (describe it)." End the list with: "Please select \
an option (answer with number and/or optional comments)."

3. Opinionated-with-override:
   - If the developer picks the recommended tier: acknowledge and record it; move \
to the next candidate.
   - If the developer picks a different tier: generate a BRIEF (1–2 sentence), \
NON-PREACHY challenge that names the SPECIFIC risk (e.g. "Going with \
planning_agent here means you'll need an eval approach for adaptive replanning, \
which is significantly harder than evaluating chained_calls"). Never lecture. \
End with "(confirm? yes/no)".
   - On yes: record their choice with their explanation as tier_decision_rationale.
   - On no: ask what they'd prefer.

4. Running catalog:
   After each decision, show the updated catalog as a compact Markdown table:
   | # | Feature | Recommended | Decided |
   with one row per decided candidate so the developer sees progress.

5. Revision:
   The developer can say "revise [candidate name]" at any time to go back. Re-\
present that candidate with the same recommendation and re-record their choice.

6. Completion:
   When all candidates have been decided, present the full catalog table and ask:
   "Does this look right, or would you like to revise anything? (yes, it's ready \
/ revise [name])"
   When the developer confirms, output ONLY a fenced JSON block — no additional \
text after it — using this exact schema:

```json
{
  "ai_catalog": [
    {
      "name": "candidate_name",
      "scope": "feature",
      "rough_description": "one sentence",
      "linked_existing_workflow": "",
      "tier_recommendation": "single_call",
      "tier_decision": "single_call",
      "tier_decision_rationale": ""
    }
  ]
}
```

   The `tier_decision_rationale` field is empty when the decision matches the \
recommendation; otherwise it contains the developer's explanation.
   The `linked_existing_workflow` field echoes the "Existing implementation \
this would replace" line from the candidate presentation, verbatim; leave it \
"" for candidates that have none.

**Technical references:**
When the developer mentions a technical standard, protocol, or SDK, use \
web_search to find the canonical documentation URL and present your findings.
"""


# User-facing overview of the nine approaches, shown once after the
# Scout→Composer progress sequence and before the developer reviews
# features.  Deterministic / hardcoded on purpose — we never rely on the model
# to recite the ladder accurately.  This copy says "approaches" (not "tiers");
# the internal tier_* schema keys are unchanged and downstream consumers still
# read them by name.
_APPROACHES_OVERVIEW = """### 🧭 How I'll size each feature

I'm **Agentifier**. For each AI opportunity Scout surfaced, I recommend the *simplest approach that meets the actual need* — simpler approaches cost less and have less to go wrong; more complex ones add capability but also more to build, test, and operate.

Here are the nine approaches I choose from, cheapest → most complex:

1. **deterministic** — rule-based logic, no model inference. *Use when* the rules are fully known and stable and no judgement or language understanding is needed.
2. **embeddings** — semantic similarity / classification via vector representations. *Use when* you need to match, group, or classify by meaning rather than exact wording.
3. **single_call** — one LLM invocation, prompt in / completion out. *Use when* a single self-contained prompt can produce the answer with no external lookup or follow-up.
4. **rag** — retrieval-augmented generation grounded in a knowledge source. *Use when* answers must be grounded in your own documents or data the model wasn't trained on.
5. **tool_agent** — an LLM that calls tools or external APIs. *Use when* the task needs live data or actions in other systems (search, fetch, update).
6. **chained_calls** — multiple sequential LLM calls, output of one feeds the next. *Use when* the work splits into fixed, ordered stages (e.g. extract → transform → summarise).
7. **planning_agent** — an LLM that produces a plan and self-directs execution. *Use when* the steps aren't known up front and the model must decide them at runtime.
8. **orchestrated_subagents** — a coordinator LLM dispatches specialised sub-agents. *Use when* distinct sub-tasks need different specialised skills under one coordinator.
9. **multi_agent_collaboration** — multiple peer agents with shared state/memory. *Use when* several agents must work concurrently on shared state, negotiating or iterating together.
"""


# ---------------------------------------------------------------------------
# Phase 1 — Sub-agent dispatch helpers
# ---------------------------------------------------------------------------


def _call_scout(
    vision: dict[str, Any],
    code_review: dict[str, Any] | None,
    llm_config: dict[str, Any],
    revision: dict[str, Any] | None = None,
) -> ScoutOutput:
    """Invoke Scout synchronously via the registry."""
    scout_input = ScoutInput(
        vision=vision,
        code_review=code_review,
        llm_config=llm_config,
        revision=revision,
    )
    return asyncio.run(_registry.run("scout", scout_input))


def _vision_purpose(vision: dict[str, Any]) -> str:
    """Best-effort one-line project purpose for the Linker's context."""
    vs = vision.get("vision_statement") if isinstance(vision, dict) else None
    inner = vs.get("vision") if isinstance(vs, dict) else None
    if isinstance(inner, dict):
        return str(inner.get("purpose") or inner.get("description") or "")
    if isinstance(vs, dict):
        return str(vs.get("purpose") or vs.get("description") or vs.get("name") or "")
    return ""


def _vision_mvp_feature_names(vision: dict[str, Any]) -> list[str]:
    """Names from the vision's ``key_features_mvp``, shape-guarded.

    The Brainstormer emits each entry as a single-key mapping
    (``{"Order_Help_Chat": {...}}``), but hand-edited visions carry plain
    strings or ``{"name": ...}`` mappings. Anything unrecognised is skipped:
    these names feed a prompt annotation (D-PP14), so a miss costs an unmarked
    feature, never a crash.
    """
    vs = vision.get("vision_statement") if isinstance(vision, dict) else None
    inner = vs.get("vision") if isinstance(vs, dict) else vs
    entries = inner.get("key_features_mvp") if isinstance(inner, dict) else None
    if not isinstance(entries, list):
        return []

    names: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            names.append(entry)
        elif isinstance(entry, dict):
            if isinstance(entry.get("name"), str):
                names.append(entry["name"])
            elif len(entry) == 1:
                names.append(next(iter(entry)))
    return [n for n in names if n]


def _call_linker(
    candidates: list[Candidate],
    vision: dict[str, Any],
    llm_config: dict[str, Any],
):
    """Invoke the Linker synchronously via the registry, returning its output."""
    li = LinkerInput(
        candidates=candidates,
        vision_purpose=_vision_purpose(vision),
        llm_config=llm_config,
    )
    return asyncio.run(_registry.run("linker", li))


def _call_composer(
    candidates: list[Candidate],
    vision: dict[str, Any],
    llm_config: dict[str, Any],
) -> ComposerOutput:
    """Invoke Composer synchronously via the registry."""
    ci = ComposerInput(candidates=candidates, vision=vision, llm_config=llm_config)
    return asyncio.run(_registry.run("composer", ci))


def _call_prioritizer(
    features: list[dict[str, Any]],
    vision: dict[str, Any],
    llm_config: dict[str, Any],
    carried_forward: list[dict[str, Any]],
):
    """Invoke the Prioritizer synchronously via the registry, returning its output."""
    pi = PrioritizerInput(
        features=features,
        vision_purpose=_vision_purpose(vision),
        llm_config=llm_config,
        carried_forward=carried_forward,
        mvp_vision_features=_vision_mvp_feature_names(vision),
    )
    return asyncio.run(_registry.run("prioritizer", pi))


def _format_composition_summary(compositions: list[Composition]) -> str:
    """Render a short composition summary — coordinators and their members.

    Nothing is merged; members are kept beneath their coordinator. A synthesized
    head (Scout did not emit one) is tagged so the reader can tell it apart.
    """
    n_groups = len(compositions)
    n_members = sum(len(c.members) for c in compositions)
    header = (
        f"### 🧬 Composer — {n_members} sub-feature"
        f"{'' if n_members == 1 else 's'} grouped under {n_groups} "
        f"coordinator{'' if n_groups == 1 else 's'}\n"
    )
    lines = [header]
    for comp in compositions:
        members_str = ", ".join(f"`{m}`" for m in comp.members)
        tag = " *(synthesized)*" if comp.synthesized else ""
        lines.append(f"- **`{comp.coordinator}`**{tag} coordinates {members_str}")
    return "\n".join(lines)


def _log_composition(
    input_candidates: list[Candidate],
    composed: ComposerOutput,
) -> None:
    """Print DEV_MODE diagnostics after a composition pass.

    Logs counts, an integrity check (the Composer may add synthesized heads but
    must never drop a candidate), per-composition detail, and a before/after
    candidate dump. Returns immediately when _DEV_MODE is False.
    """
    if not _DEV_MODE:
        return

    out_candidates = composed.candidates
    n_in = len(input_candidates)
    n_out = len(out_candidates)
    print(
        f"[agentifier] composer: {n_in} in → {n_out} out, "
        f"{len(composed.compositions)} composition(s), "
        f"{composed.n_synthesized} synthesized head(s)",
        flush=True,
    )

    input_names = {c.name for c in input_candidates}
    output_names = {c.name for c in out_candidates}
    for name in sorted(input_names - output_names):
        print(f"[agentifier] composer: WARNING dropped candidate '{name}'", flush=True)

    if composed.compositions:
        for comp in composed.compositions:
            kind = "synthesized" if comp.synthesized else "present"
            members_str = "[" + ", ".join(comp.members) + "]"
            print(
                f"[agentifier] composer: group  coordinator='{comp.coordinator}'"
                f"  head={kind}  members={members_str}",
                flush=True,
            )
    else:
        print(
            f"[agentifier] composer: no compositions ({n_in} candidates unchanged)",
            flush=True,
        )

    print(f"[agentifier] composer: --- output ({n_out}) ---", flush=True)
    for i, c in enumerate(out_candidates, 1):
        desc = (c.rough_description or "")[:80]
        print(
            f"[agentifier] composer:   {i}. {c.name} [{c.scope}] — {desc}",
            flush=True,
        )


def _call_tier_analyst(
    candidate: Candidate,
    llm_config: dict[str, Any],
    code_review: dict[str, Any] | None = None,
) -> TierAnalystOutput:
    """Invoke TierAnalyst synchronously via the registry."""
    tiers, mechanisms = load_patterns()
    ta_input = TierAnalystInput(
        candidate=candidate,
        llm_config=llm_config,
        tier_patterns=tiers,
        code_review=code_review,
        mechanism_patterns=mechanisms,
    )
    return asyncio.run(_registry.run("tier_analyst", ta_input))


# ---------------------------------------------------------------------------
# Phase 1 — Seed-message builder
# ---------------------------------------------------------------------------


def _graph_placement_lines(
    cand: Candidate,
    present: set[str],
    members_by_coordinator: dict[str, list[str]],
    required_by: dict[str, list[str]],
) -> list[str]:
    """Human-facing lines locating a candidate in the feature graph.

    Feature→feature only: infrastructure substrate is injected post-assembly by
    the expander, so no substrate edge exists at tier-review time. Every
    reference is trimmed to the reviewed set (``present``) so a closure-dropped
    coordinator or a deselected producer/consumer is never named to the
    developer.
    """
    lines: list[str] = []
    coordinator = cand.composed_under
    if coordinator and coordinator in present:
        lines.append(f"A sub-feature of `{coordinator}`.")
    members = [m for m in members_by_coordinator.get(cand.name, []) if m in present]
    if members:
        listed = ", ".join(f"`{m}`" for m in members)
        plural = "" if len(members) == 1 else "s"
        lines.append(f"Coordinates {len(members)} sub-feature{plural}: {listed}.")
    uses = [r for r in cand.requires if r in present]
    if uses:
        lines.append("Uses the output of: " + ", ".join(f"`{r}`" for r in uses) + ".")
    feeds = [c for c in required_by.get(cand.name, []) if c in present]
    if feeds:
        lines.append("Its output feeds: " + ", ".join(f"`{c}`" for c in feeds) + ".")
    return lines


def _build_seed_message(
    candidates: list[Candidate],
    analyses: list[TierAnalystOutput],
    brownfield: bool = False,
    revision_goal: str = "",
) -> str:
    """Build the first user message injected into the orchestrator conversation."""
    if revision_goal:
        mode_note = (
            " This is a REVISION round of an already-built project — the developer "
            "is extending the existing AI surface, not starting fresh, so do NOT "
            "ask whether they are adding AI for the first time. The goal of this "
            f"revision: {revision_goal} The candidates below are only the NEW AI "
            "opportunities introduced by this revision's changes; already-built AI "
            "features are carried forward automatically and are not shown here. "
            "Present the first new candidate, framing the conversation around this "
            "revision's goal."
        )
    elif brownfield:
        mode_note = (
            " This is a BROWNFIELD project (an existing codebase was reviewed). "
            "Before presenting the first candidate, briefly ask the developer: "
            "'Are we adding AI features for the first time, extending existing AI "
            "features, or rethinking how AI is used overall?' — then proceed with "
            "presenting candidates based on their answer."
        )
    else:
        mode_note = ""
    intro = (
        f"[Spec4 system note: Scout found {len(candidates)} AI opportunity "
        f"candidate(s) in the project vision. Tier Analyst has provided a "
        f"recommendation for each.{mode_note} Begin by presenting the first "
        f"candidate recommendation to the developer. Follow the conversation "
        f"rules in your system prompt exactly.]"
    )
    # Reverse-edge maps over the reviewed set, so each candidate block can show
    # its members (reverse of composed_under) and consumers (reverse of requires)
    # in pool order. Feature→feature only at this stage; infra is injected later.
    present = {c.name for c in candidates}
    members_by_coordinator: dict[str, list[str]] = {}
    required_by: dict[str, list[str]] = {}
    for c in candidates:
        if c.composed_under:
            members_by_coordinator.setdefault(c.composed_under, []).append(c.name)
        for r in c.requires:
            required_by.setdefault(r, []).append(c.name)
    parts = [intro]
    for i, (cand, analysis) in enumerate(zip(candidates, analyses), 1):
        lines = [
            f"\n---\n**Candidate {i}: {cand.name}** (scope: {cand.scope})",
            f"Description: {cand.rough_description}",
        ]
        if cand.linked_existing_workflow:
            lines.append(
                "Existing implementation this would replace: "
                f"{cand.linked_existing_workflow}"
            )
        lines.extend(
            _graph_placement_lines(cand, present, members_by_coordinator, required_by)
        )
        if cand.linked_vision_features:
            lines.append(
                f"Linked vision features: {', '.join(cand.linked_vision_features)}"
            )
        lines.append(f"Recommended tier: **{analysis.recommended_tier}**")
        lines.append(f"Rationale: {analysis.rationale}")
        if analysis.compared_to_next_tier_down:
            lines.append(
                f"Compared to next cheaper tier: {analysis.compared_to_next_tier_down}"
            )
        if analysis.borderline:
            seams = ", ".join(analysis.borderline_seams)
            lines.append(f"Borderline: YES — watch for: {seams}")
        else:
            lines.append("Borderline: NO")
        if analysis.risks_of_going_higher:
            lines.append("Risks of going higher: " + "; ".join(analysis.risks_of_going_higher))
        if analysis.risks_of_going_lower:
            lines.append("Risks of going lower: " + "; ".join(analysis.risks_of_going_lower))
        parts.append("\n".join(lines))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Phase 1 — Session serialisation helpers
# ---------------------------------------------------------------------------


def _candidates_to_dicts(candidates: list[Candidate]) -> list[dict[str, Any]]:
    return [
        {
            "name": c.name,
            "linked_vision_features": c.linked_vision_features,
            "scope": c.scope,
            "rough_description": c.rough_description,
            "linked_existing_workflow": c.linked_existing_workflow,
            # Scout graph contract (D-EP): carry the edges through serialization so
            # they survive into the breadth pool and downstream into ai_features.
            "composed_under": c.composed_under,
            "requires": list(c.requires),
            # Node classification (D-I5); "feature" for everything Scout produces.
            "kind": c.kind,
        }
        for c in candidates
    ]


def _analyses_to_dicts(
    analyses: list[TierAnalystOutput], candidates: list[Candidate]
) -> list[dict[str, Any]]:
    return [
        {
            "name": candidates[i].name,
            "recommended_tier": a.recommended_tier,
            "rationale": a.rationale,
            "risks_of_going_higher": a.risks_of_going_higher,
            "risks_of_going_lower": a.risks_of_going_lower,
            "borderline": a.borderline,
            "borderline_seams": a.borderline_seams,
            "compared_to_next_tier_down": a.compared_to_next_tier_down,
        }
        for i, a in enumerate(analyses)
    ]


def _candidates_from_session(session: dict[str, Any]) -> list[Candidate]:
    data = session.get("agentifier_candidates") or []
    return [
        Candidate(
            name=d["name"],
            linked_vision_features=d.get("linked_vision_features", []),
            scope=d.get("scope", "feature"),
            rough_description=d.get("rough_description", ""),
            linked_existing_workflow=d.get("linked_existing_workflow", ""),
            composed_under=d.get("composed_under", ""),
            requires=list(d.get("requires") or []),
            kind=d.get("kind", "feature"),
        )
        for d in data
    ]


def _analyses_from_session(session: dict[str, Any]) -> list[TierAnalystOutput]:
    data = session.get("agentifier_analyses") or []
    return [
        TierAnalystOutput(
            recommended_tier=d.get("recommended_tier", "deterministic"),
            rationale=d.get("rationale", ""),
            risks_of_going_higher=d.get("risks_of_going_higher", []),
            risks_of_going_lower=d.get("risks_of_going_lower", []),
            borderline=d.get("borderline", False),
            borderline_seams=d.get("borderline_seams", []),
            compared_to_next_tier_down=d.get("compared_to_next_tier_down", ""),
        )
        for d in data
    ]


# ---------------------------------------------------------------------------
# Phase 1 — Artifact helpers
# ---------------------------------------------------------------------------


def _extract_catalog_json(text: str) -> dict[str, Any] | None:
    """Extract the ai_catalog JSON block from the LLM response, or None."""
    data = _extract_json_block(text)
    return data if data is not None and "ai_catalog" in data else None


_CATALOG_SPEC_PROMPT = (
    "---\n\n"
    "Tier decisions locked. Reply **yes** to begin drafting per-feature specs, "
    "or ask to revise any catalog entry first."
)


def _format_catalog_as_text(catalog: dict[str, Any]) -> str:
    """Render ai_catalog to a readable Markdown display with spec-phase prompt."""
    entries: list[dict[str, Any]] = catalog.get("ai_catalog") or []
    lines: list[str] = ["**AI Integration Catalog**\n"]
    lines.append("| # | Feature | Recommended | Decided | Notes |")
    lines.append("| --- | --- | --- | --- | --- |")
    for i, entry in enumerate(entries, 1):
        name = entry.get("name", "")
        rec = entry.get("tier_recommendation", "")
        dec = entry.get("tier_decision", "")
        rationale = entry.get("tier_decision_rationale", "") or ""
        note = rationale[:60] + "…" if len(rationale) > 60 else rationale
        match_marker = "" if dec == rec else " ⚠️"
        lines.append(f"| {i} | {name} | {rec} | {dec}{match_marker} | {note} |")
    lines.append("")
    lines.append(_CATALOG_SPEC_PROMPT)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 2 — Spec helpers
# ---------------------------------------------------------------------------


def _is_spec_confirmed(text: str) -> bool:
    """Return True when the user's reply is an affirmative confirmation."""
    t = text.lower().strip().rstrip(".,!?")
    affirmatives = {
        "yes", "y", "ok", "okay", "lgtm", "good", "next",
        "continue", "proceed", "confirm", "done", "approved", "accept",
        "looks good", "ship it", "go ahead", "move on", "yes please",
    }
    if t in affirmatives:
        return True
    for word in affirmatives:
        if t.startswith(word) and (len(t) == len(word) or not t[len(word) : len(word) + 1].isalpha()):
            return True
    return False


def _format_spec_as_text(
    entry: dict[str, Any],
    spec: dict[str, Any],
    index: int,
    total: int,
) -> str:
    """Render one feature spec as readable Markdown."""
    name = entry.get("name", "")
    tier = entry.get("tier_decision") or entry.get("tier", "")
    lines: list[str] = [
        f"### Feature {index + 1}/{total}: `{name}` — tier: **{tier}**\n"
    ]

    def _field(label: str, key: str) -> None:
        val = spec.get(key)
        if val is None:
            return
        if isinstance(val, list):
            if not val:
                return
            lines.append(f"**{label}:**")
            for item in val:
                if isinstance(item, dict):
                    lines.append("- " + ", ".join(f"{k}: {v}" for k, v in item.items()))
                else:
                    lines.append(f"- {item}")
            lines.append("")
        elif isinstance(val, dict):
            if not val:
                return
            lines.append(f"**{label}:**")
            for k, v in val.items():
                if isinstance(v, list):
                    if v:
                        lines.append(f"- {k}: " + "; ".join(str(i) for i in v))
                elif v:
                    lines.append(f"- {k}: {v}")
            lines.append("")
        else:
            lines.append(f"**{label}:** {val}\n")

    _field("Purpose", "purpose")
    _field("Invocation", "invocation")
    _field("Inputs", "inputs")
    _field("Outputs", "outputs")
    _field("Decision authority", "decision_authority")
    _field("Success criteria", "success_criteria")
    _field("Failure modes", "failure_modes")
    _field("Escalation", "escalation")
    _field("Eval approach", "eval_approach")
    _field("Budgets", "budgets")
    _field("Privacy / safety", "privacy_safety")
    # Phase priority is deliberately absent: it is assigned by the Prioritizer
    # (D-PP2), which runs after spec review. Showing it here would display a
    # value nobody has set yet.
    # Tier-specific
    _field("Knowledge sources", "knowledge_sources")
    _field("Tool access", "tool_access")
    _field("Topology", "topology")
    # Mechanisms
    mechanisms = spec.get("mechanisms") or []
    if mechanisms:
        lines.append("**Mechanisms:**")
        for m in mechanisms:
            if isinstance(m, dict):
                mname = m.get("name", "")
                mrationale = m.get("rationale", "")
                lines.append(f"- **{mname}**: {mrationale}")
            else:
                lines.append(f"- {m}")
        lines.append("")
    # References
    references = spec.get("references") or []
    if references:
        lines.append("**References:**")
        for r in references:
            lines.append(f"- {r}")
        lines.append("")
    return "\n".join(lines)


def _feature_specs_for_session(session: dict[str, Any]) -> dict[str, Any]:
    """Brainstormer's per-product-feature specs, for grounding (D-AC1 B).

    Prefers the in-session copy; falls back to disk via ``load_feature_specs`` so
    a session rebuilt from disk (the ``render_page`` store-clobber footgun) still
    grounds against the confirmed vision. Returns ``{}`` when neither is present —
    grounding then degrades to empty, the intended safety net, and the Spec
    Drafter falls back to the ``rough_description`` path.
    """
    specs = session.get("feature_specs")
    if isinstance(specs, dict) and specs.get("features"):
        return specs
    working_dir = session.get("working_dir")
    if working_dir:
        loaded = project_manager.load_feature_specs(working_dir)
        if isinstance(loaded, dict):
            return loaded
    return specs if isinstance(specs, dict) else {}


def _linked_features_for_entry(
    entry: dict[str, Any], candidates_data: list[dict[str, Any]]
) -> list[str]:
    """The vision-feature names an entry serves, read from its candidate.

    ``linked_vision_features`` lives on the Scout/Composer candidate (the
    candidate is authoritative — D-EP), joined to the catalog entry by name; a
    coordinator's list is already the union of its members' links.
    """
    name = entry.get("name", "")
    for c in candidates_data or []:
        if c.get("name") == name:
            return list(c.get("linked_vision_features") or [])
    return []


def _existing_workflow_for_entry(
    entry: dict[str, Any], candidates_data: list[dict[str, Any]]
) -> str:
    """The existing implementation an entry replaces, read from its candidate.

    ``linked_existing_workflow`` lives on the Scout candidate (the candidate
    is authoritative — D-EP), joined to the catalog entry by name — the
    catalog LLM's echo of the field is never trusted.
    """
    name = entry.get("name", "")
    for c in candidates_data or []:
        if c.get("name") == name:
            return str(c.get("linked_existing_workflow") or "")
    return ""


def _build_ai_features(
    catalog_entries: list[dict[str, Any]],
    spec_results: list[dict[str, Any]],
    candidates_data: list[dict[str, Any]],
    analyses_data: list[dict[str, Any]] | None = None,
    feature_specs: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Merge catalog entries + spec results into ai_features schema.

    When ``feature_specs`` is supplied, each node also carries a
    ``vision_grounding`` block (D-AC1 B): the Brainstormer product-feature specs
    it serves, resolved from the candidate's ``linked_vision_features`` by the
    canonical ``slug()`` join. Absent/empty grounding leaves the key off.
    """
    candidates_by_name = {c["name"]: c for c in candidates_data}
    analysis_by_name = {a["name"]: a for a in (analyses_data or []) if a.get("name")}
    features: list[dict[str, Any]] = []
    for i, entry in enumerate(catalog_entries):
        name = entry.get("name", "")
        spec = spec_results[i] if i < len(spec_results) else {}
        cand = candidates_by_name.get(name, {})
        feature: dict[str, Any] = {
            "id": slug(name) if name else f"feature_{i}",
            "name": name,
            "linked_vision_features": cand.get("linked_vision_features", []),
            "scope": entry.get("scope", "feature"),
            "tier": entry.get("tier_decision", "single_call"),
            "tier_recommendation": entry.get("tier_recommendation", ""),
            "tier_decision_rationale": entry.get("tier_decision_rationale", ""),
            "rough_description": entry.get("rough_description", ""),
        }
        feature.update(spec)  # merge spec drafter output
        # Candidate is the authoritative source for rough_description: it carries
        # Composer-enriched text that the catalog agent may have reverted.
        # Falls back to the entry value, then to whatever spec supplied.
        feature["rough_description"] = (
            cand.get("rough_description")
            or entry.get("rough_description", "")
            or feature.get("rough_description", "")
        )
        # Scout graph contract (D-EP): the candidate is authoritative for the
        # edges too — re-assert them after the spec merge so a spec drafter that
        # echoes these keys cannot clobber the Composer-set values. Persisted raw
        # (D-EP2 option A): referential trimming of dangling edges is deferred.
        feature["composed_under"] = cand.get("composed_under", "")
        feature["requires"] = list(cand.get("requires") or [])
        # Brownfield linkage (candidate-authoritative, like the edges): without
        # this, _reselection_pool_from_features' read of the key is always ""
        # and re-selection rounds silently lose the replaced-workflow context.
        feature["linked_existing_workflow"] = cand.get("linked_existing_workflow", "")
        # Node classification (D-I5): selectable features are explicitly
        # "feature"; tier-derived substrate is stamped "infrastructure" by the
        # expansion pass. Makes the distinction explicit rather than by absence.
        feature["kind"] = cand.get("kind", "feature")
        # Vision grounding (D-AC1 B): the product-feature specs this AI feature
        # serves, joined from the candidate's linked_vision_features. Attached
        # after the spec merge so a Spec Drafter that echoes the key cannot
        # clobber it. Gated on feature_specs actually being present so the
        # safety-net path (no specs) attaches nothing rather than tagging every
        # node with noise-only unresolved links; when specs exist, an all-missed
        # node keeps its unresolved_links as a genuine mis-link signal.
        if (feature_specs or {}).get("features"):
            grounding = build_grounding(
                feature_specs, cand.get("linked_vision_features") or []
            )
            if grounding:
                feature["vision_grounding"] = grounding
        a = analysis_by_name.get(name, {})
        feature["tier_analysis"] = (
            {
                "recommended_tier": a.get("recommended_tier", ""),
                "rationale": a.get("rationale", ""),
                "compared_to_next_tier_down": a.get("compared_to_next_tier_down", ""),
                "borderline": a.get("borderline", False),
                "borderline_seams": a.get("borderline_seams", []),
                "risks_of_going_higher": a.get("risks_of_going_higher", []),
                "risks_of_going_lower": a.get("risks_of_going_lower", []),
            }
            if a
            else {}
        )
        features.append(feature)
    return features


def _expand_infrastructure(
    features: list[dict[str, Any]],
    introduced_in_version: int | None = None,
) -> list[dict[str, Any]]:
    """Deterministic tier-required infrastructure expansion (D-I2 option B).

    Reads the tier registry (``required_infrastructure`` per tier) and injects
    ``kind: infrastructure`` substrate nodes implied by the *tiers* of the
    selected features. A registry lookup, never an LLM call. Called at the single
    finalisation locus (``_complete_agentifier``), so infrastructure is added
    after cross-cutting analysis and the priority-review loop and is excluded
    from both by construction.
    """
    tiers, _ = load_patterns()
    tier_infrastructure = {t.name: list(t.required_infrastructure) for t in tiers}
    return expand_infrastructure(features, tier_infrastructure, introduced_in_version)


# ---------------------------------------------------------------------------
# Revision mode — pure helpers (deterministic; no LLM)
# ---------------------------------------------------------------------------


def _revision_delta(vision: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return this round's revision delta, or ``None`` for a greenfield vision.

    A revision round's vision carries an accumulating ``revision_history`` (each
    round contributes one entry, stamped deterministically by Brainstormer); its
    final entry is the delta for the current round — ``goal``, the
    ``key_features_mvp`` name changes (``added`` / ``modified`` / ``removed``),
    and ``rationale``. A greenfield vision has no ``revision_history``.
    """
    vs = (vision or {}).get("vision_statement") if isinstance(vision, dict) else None
    history = vs.get("revision_history") if isinstance(vs, dict) else None
    if isinstance(history, list) and history:
        last = history[-1]
        return last if isinstance(last, dict) else None
    return None


def _merge_revision_snapshot(
    carried_forward: list[dict[str, Any]],
    new_features: list[dict[str, Any]],
    current_version: int,
    prior_version: int,
) -> list[dict[str, Any]]:
    """Assemble a revision round's complete feature snapshot with provenance.

    Returns the carried-forward implemented features (kept verbatim aside from a
    backfilled ``introduced_in_version``) followed by this round's newly selected
    features. Code owns ``introduced_in_version`` — the model never authors it:

    - new features → ``current_version`` (this planning round).
    - carried-forward → their existing ``introduced_in_version``; backfilled to
      ``prior_version`` when a feature predates the marker (e.g. greenfield
      features built before this field existed).

    Carried-forward names win on collision: if Scout re-surfaces an already-built
    feature as a "new" candidate despite the delta-informed scoping, the built
    entry is kept and the duplicate dropped — never double-listed or downgraded.
    """
    carried_names = {f.get("name") for f in carried_forward if f.get("name")}
    out: list[dict[str, Any]] = []
    for f in carried_forward:
        g = dict(f)
        if g.get("introduced_in_version") is None:
            g["introduced_in_version"] = prior_version
        out.append(g)
    for f in new_features:
        if f.get("name") in carried_names:
            continue
        g = dict(f)
        g["introduced_in_version"] = current_version
        out.append(g)
    return out


def _removed_feature_heads_up(
    carried_forward: list[dict[str, Any]],
    delta: dict[str, Any] | None,
) -> str:
    """Informational note (no action) when a built feature is linked to a feature
    this revision removed.

    Carried-forward features are NEVER auto-dropped — the code is already built,
    and deprecation/removal is downstream coding work, out of scope for
    Agentifier discovery. This surfaces the situation so the developer stays in
    control. Returns ``""`` when nothing applies.
    """
    removed = set((delta or {}).get("changes", {}).get("removed") or [])
    if not removed:
        return ""
    hits: list[str] = []
    for f in carried_forward:
        linked = set(f.get("linked_vision_features") or [])
        overlap = linked & removed
        if overlap:
            hits.append(f"- **{f.get('name', '')}** (built for: {', '.join(sorted(overlap))})")
    if not hits:
        return ""
    return (
        "\n\n> ℹ️ **Heads-up:** these already-built AI features are linked to "
        "product features you removed this revision. They are carried forward "
        "unchanged — removing the underlying code is a separate, manual step:\n"
        + "\n".join(hits)
        + "\n"
    )


_FEATURES_COMPLETE_TRANSITION = (
    "---\n\n"
    "Your AI feature catalog is complete. "
    "Click **💾 Download ai_features.json** below, "
    "or use the pipeline pills to continue."
)


def _format_ai_features_complete(ai_features: dict[str, Any]) -> str:
    """Render a summary display for completed ai_features."""
    entries = ai_features.get("ai_features") or []
    lines = ["**AI Feature Catalog — Complete**\n"]
    lines.append("| # | Feature | Tier | Phase Priority |")
    lines.append("| --- | --- | --- | --- |")
    for i, f in enumerate(entries, 1):
        name = f.get("name", "")
        tier = f.get("tier", "")
        priority = f.get("phase_priority", "—")
        lines.append(f"| {i} | {name} | {tier} | {priority} |")
    lines.append("")
    lines.append(_FEATURES_COMPLETE_TRANSITION)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 2 — Spec drafting
# ---------------------------------------------------------------------------


#: Mirrors session.py's definition; a session->agentifier import would be
#: circular, so the flag is derived locally from the same variable.
_DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"


def _append_assistant(session: dict[str, Any], text: str) -> None:
    """Record text as the turn's assistant message (D-AF5).

    Failure paths previously yielded error text without appending it, leaving
    the history ending on a user turn; replay and next-turn routing both
    misbehave from that state.
    """
    session["agentifier_messages"].append({"role": "assistant", "content": text})
    session["_display_override"] = text


def _dump_subagent_failure(
    session: dict[str, Any],
    kind: str,
    name: str,
    raw: str,
) -> None:
    """D-AF7: persist the full raw output of a failed extraction (dev mode).

    The error display truncates to 800 chars, which is why the root cause of
    the first live sweep failure (truncation vs malformed tail) could not be
    determined. Instrument before any lever: an explicit max_tokens change is
    only warranted if these dumps show mid-token cutoffs. Never raises.
    """
    if not _DEV_MODE:
        return
    working_dir = session.get("working_dir")
    if not working_dir:
        return
    try:
        failures = pathlib.Path(working_dir) / ".spec4" / "failures"
        failures.mkdir(parents=True, exist_ok=True)
        n = len(list(failures.glob(f"{kind}_{name}_*.txt")))
        (failures / f"{kind}_{name}_{n + 1}.txt").write_text(
            raw, encoding="utf-8"
        )
    except Exception:  # noqa: BLE001 - diagnostics must never break the turn
        _log.exception("failure dump failed for %s/%s", kind, name)


def _draft_spec(
    spec_index: int,
    revision_instruction: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Draft (or revise) the spec at spec_index and store it in session.

    Yields only progress/error text — no spec display and no reply prompt —
    so it can serve both the one-at-a-time loop (via _draft_and_show_spec)
    and the D-AF2 Fast Forward sweep. Success is observable in session:
    ``agentifier_spec_results[spec_index]`` is truthy iff the draft landed.
    """
    catalog_entries = (session.get("ai_catalog") or {}).get("ai_catalog", [])
    n = len(catalog_entries)
    entry = catalog_entries[spec_index]
    feature_name = entry.get("name", f"feature {spec_index + 1}")
    action = "Revising" if revision_instruction else "Drafting"

    header = f"\n\n{action} spec for **`{feature_name}`** ({spec_index + 1}/{n})…\n\n"
    yield header

    tiers, mechanisms = load_patterns()
    candidates_data = session.get("agentifier_candidates") or []
    grounding = build_grounding(
        _feature_specs_for_session(session),
        _linked_features_for_entry(entry, candidates_data),
    )
    code_review = session.get("code_review")
    spec_input = SpecDrafterInput(
        catalog_entry=entry,
        llm_config=llm_config,
        tier_patterns=tiers,
        mechanism_patterns=mechanisms,
        revision_instruction=revision_instruction,
        vision_grounding=grounding,
        linked_existing_workflow=_existing_workflow_for_entry(entry, candidates_data),
        existing_ai_context=_existing_ai_context(code_review) if code_review else "",
    )

    spec: dict[str, Any] | None = None
    spec_text = ""
    for attempt in (1, 2):  # D-AF6: one automatic retry on unreadable output
        try:
            spec_text = ""
            for chunk in _iter_async_gen(_registry.stream("spec_drafter", spec_input)):
                spec_text += chunk
        except Exception as exc:
            error = f"Spec Drafter failed for `{feature_name}`: {exc}. Please try again."
            _append_assistant(session, error)
            yield error
            return

        spec = _extract_json_block(spec_text)
        if not spec:
            # If the LLM output raw JSON without fences, try parsing directly
            import json as _json
            try:
                spec = _json.loads(spec_text.strip())
            except Exception:
                spec = None
        if spec:
            break
        _dump_subagent_failure(session, "spec_drafter", feature_name, spec_text)
        if attempt == 1:
            yield f"Draft output for `{feature_name}` was unreadable — retrying…\n\n"

    if not spec:
        error = (
            f"Could not extract spec JSON for `{feature_name}` (after a retry).\n\n"
            f"Raw response (first 800 chars):\n```\n{spec_text[:800]}\n```"
        )
        _append_assistant(session, error)
        yield error
        return

    # Enrich references via web search when a provider is configured
    ref_search = websearch.from_session(session)
    if ref_search and spec.get("references"):
        from spec4.agentifier.reference_verifier import enrich_references
        spec["references"] = enrich_references(spec["references"], ref_search)

    # Store or replace spec result for this index
    results: list[dict[str, Any]] = list(session.get("agentifier_spec_results") or [])
    # Ensure list is big enough
    while len(results) <= spec_index:
        results.append({})
    results[spec_index] = spec
    session["agentifier_spec_results"] = results


def _draft_and_show_spec(
    spec_index: int,
    revision_instruction: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Draft (or revise) the spec for catalog entry at spec_index, then display it."""
    msgs = session["agentifier_messages"]
    catalog_entries = (session.get("ai_catalog") or {}).get("ai_catalog", [])
    n = len(catalog_entries)
    entry = catalog_entries[spec_index]

    yield from _draft_spec(spec_index, revision_instruction, session, llm_config)
    results = session.get("agentifier_spec_results") or []
    if not (len(results) > spec_index and results[spec_index]):
        return  # draft failed; error text already yielded

    spec = results[spec_index]
    is_last = spec_index >= n - 1
    spec_display = _format_spec_as_text(entry, spec, spec_index, n)
    if is_last:
        spec_display += (
            "\n\n---\nAll feature specs drafted. "
            "Reply **yes** to save `ai_features.json`, or tell me what to revise."
        )
    else:
        spec_display += (
            "\n\n---\nReply **yes** to continue to the next feature's spec, "
            "or tell me what to revise."
        )

    msgs.append({"role": "assistant", "content": spec_display})
    session["_display_override"] = spec_display
    yield spec_display


def _finalize_specs(
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Complete spec phase: build features list, run CrossCuttingAnalyst, show first topic."""
    catalog_entries = (session.get("ai_catalog") or {}).get("ai_catalog", [])
    spec_results: list[dict[str, Any]] = session.get("agentifier_spec_results") or []
    candidates_data: list[dict[str, Any]] = session.get("agentifier_candidates") or []
    analyses_data: list[dict[str, Any]] = session.get("agentifier_analyses") or []
    msgs = session["agentifier_messages"]

    feature_specs = _feature_specs_for_session(session)
    features = _build_ai_features(
        catalog_entries,
        spec_results,
        candidates_data,
        analyses_data,
        feature_specs,
    )
    if session.get("agentifier_reselection"):
        # Re-selection: prepend the still-selected features kept verbatim, then
        # the newly spec-drafted ones. Cross-cutting (below) and priority re-run
        # over this union. Clear the re-selection state now that it's assembled.
        preserved = session.get("agentifier_preserved_selected") or []
        features = list(preserved) + features
        for key in (
            "agentifier_reselection",
            "agentifier_preserved_features",
            "agentifier_preserved_selected",
        ):
            session.pop(key, None)
    # Requires-direction reconciliation (D-RC6 A): runs on the complete
    # feature->feature graph (post-reselection union, pre-infra-expansion),
    # flipping only SUSPECTED-INVERSION edges per the D-RI calibrated signal
    # doctrine. Records land in the top-level ``reconciliation`` block
    # (D-RC1 C). In revision mode, an edge naming a carried-forward feature
    # is unresolvable here (the snapshot merges later, in
    # ``_complete_agentifier``) and is conservatively left untouched.
    reconciliation = reconcile_requires(features, feature_specs)
    ai_features: dict[str, Any] = {
        "ai_features": features,
        "cross_cutting": {},
        "explicitly_rejected": list(session.get("agentifier_explicitly_rejected") or []),
        "references": [],
        "consolidation": [],
        "reconciliation": reconciliation,
    }
    session["ai_features"] = ai_features
    session["agentifier_spec_done"] = True

    yield "\n\nAll feature specs complete! Analysing cross-cutting system concerns…\n\n"

    topics = warranted_topics(features)
    if not topics:
        # No cross-cutting concern applies (e.g. all deterministic, no tools).
        session["agentifier_cross_cutting_topics"] = []
        session["agentifier_cross_cutting_decisions"] = {}
        session["agentifier_cross_cutting_done"] = True
        yield from _begin_priority_phase(session, llm_config)
        return

    _, mechanisms = load_patterns()
    cc_input = CrossCuttingInput(
        ai_features=features,
        mechanism_patterns=mechanisms,
        llm_config=llm_config,
        topics=topics,
        code_review=session.get("code_review"),
    )
    try:
        raw = ""
        for chunk in _iter_async_gen(_registry.stream("cross_cutting_analyst", cc_input)):
            raw += chunk
    except Exception as exc:
        err = f"Cross-Cutting Analyst failed: {exc}. Reply **retry** to try again or continue."
        msgs.append({"role": "assistant", "content": err})
        session["_display_override"] = err
        yield err
        return

    analysis = _extract_cross_cutting_analysis(raw)
    if not analysis:
        err = (
            "Could not parse cross-cutting analysis JSON. "
            "Reply **retry** to try again."
        )
        msgs.append({"role": "assistant", "content": err})
        session["_display_override"] = err
        yield err
        return

    session["agentifier_cross_cutting_topics"] = topics
    session["agentifier_cross_cutting_analysis"] = analysis
    session["agentifier_cross_cutting_index"] = 0
    session["agentifier_cross_cutting_decisions"] = {}

    display = _format_cross_cutting_topic(topics[0], 0, analysis, len(topics))
    msgs.append({"role": "assistant", "content": display})
    session["_display_override"] = display
    yield display


def _complete_agentifier(
    session: dict[str, Any],
    display: str | None = None,
) -> Generator[str, None, None]:
    """True finalization: populate cross_cutting block, set STATE_AGENTIFIER_COMPLETE.

    ``display`` overrides the completion message. When None, the standard
    AI-feature-catalog summary is shown; a caller passes an override for the
    no-AI-surface case, where the empty catalog table would be misleading.
    """
    msgs = session["agentifier_messages"]
    ai_features = session.get("ai_features") or {}
    # Project-level non-functional goals (D-AC7) are join-independent — stamped
    # here at the single finalization locus so every completion path (greenfield,
    # revision, no-AI-surface) carries the confirmed vision's nfr_goals through
    # to the Agentifier output.
    ai_features["nfr_goals"] = list(
        _feature_specs_for_session(session).get("nfr_goals") or []
    )
    decisions = session.get("agentifier_cross_cutting_decisions") or {}
    # Captured before the revision branch pops the version key: drives the
    # ``introduced_in_version`` stamp on newly injected infrastructure (S6).
    _infra_version = (
        session.get("agentifier_revision_version")
        if session.get("agentifier_revision")
        else None
    )

    ai_features["cross_cutting"] = decisions

    heads_up = ""
    if session.get("agentifier_revision"):
        # Revision round finalisation — the single locus where the already-built
        # AI surface is folded back in. New features have already passed through
        # this round's tier review, cross-cutting, and priority passes; the
        # carried-forward built features are merged in here, AFTER those passes,
        # so the developer is never re-prompted to set phase priority (or
        # re-decide cross-cutting) for features that already exist. Code owns the
        # introduced_in_version provenance stamp on every feature.
        carried = session.get("agentifier_carried_forward") or []
        cur_v = session.get("agentifier_revision_version") or 0
        prior_v = session.get("agentifier_revision_prior_version") or 0
        prior_cc = session.get("agentifier_revision_cross_cutting") or {}
        new_feats = ai_features.get("ai_features") or []
        ai_features["ai_features"] = _merge_revision_snapshot(
            carried, new_feats, cur_v, prior_v
        )
        # Prior cross-cutting decisions carry forward; this round's decisions (if
        # any topics were warranted by the new features) override per-topic.
        ai_features["cross_cutting"] = {**prior_cc, **decisions}
        heads_up = _removed_feature_heads_up(
            carried, session.get("agentifier_revision_delta")
        )
        for key in (
            "agentifier_revision",
            "agentifier_carried_forward",
            "agentifier_revision_version",
            "agentifier_revision_prior_version",
            "agentifier_revision_delta",
            "agentifier_revision_cross_cutting",
        ):
            session.pop(key, None)

    # Tier-required infrastructure expansion (D-I2 option B): the final locus,
    # after cross-cutting and priority review, before Phaser consumes the graph.
    # Injected substrate is thus excluded from both interactive passes; the edges
    # are additive on the existing graph contract Phaser already reads.
    ai_features["ai_features"] = _expand_infrastructure(
        ai_features.get("ai_features") or [], _infra_version
    )

    session["ai_features"] = ai_features
    session["agentifier_state"] = STATE_AGENTIFIER_COMPLETE
    session["agentifier_stale_acknowledged"] = {}
    session["agentifier_priority_done"] = True

    if display is None:
        display = _format_ai_features_complete(ai_features)
    display = display + heads_up
    msgs.append({"role": "assistant", "content": display})
    session["_display_override"] = display
    session["agentifier_artifact_msg_count"] = len(msgs)
    yield display


# ---------------------------------------------------------------------------
# Cross-cutting helpers
# ---------------------------------------------------------------------------


def _extract_cross_cutting_analysis(text: str) -> dict[str, Any] | None:
    """Extract cross-cutting JSON. Handles full-analysis and single-topic formats."""
    import json as _json
    data = _extract_json_block(text)
    if data is None:
        try:
            data = _json.loads(text.strip())
        except Exception:
            return None
    if not isinstance(data, dict):
        return None
    # Single-topic revision format: {"topic": "observability", "recommendation": ...}
    if "topic" in data and data.get("topic") in CROSS_CUTTING_TOPICS:
        topic = data["topic"]
        return {topic: {k: v for k, v in data.items() if k != "topic"}}
    # Full analysis: has at least one known topic key
    if any(t in data for t in CROSS_CUTTING_TOPICS):
        return data
    return None


def _cc_ff_review_prompt(locked_topics: list[str]) -> str:
    prompt = (
        "\n\n---\n**Comprehensive review.** Reply **yes** to accept all "
        "cross-cutting decisions as shown, or give revisions one per line "
        "as `topic: instruction` (`topic: skip` to drop a skippable topic)."
    )
    if locked_topics:
        prompt += (
            "\nLocked (decided earlier, not revisable here): "
            + ", ".join(f"`{t}`" for t in locked_topics)
            + "."
        )
    return prompt


def _present_cc_ff_review(
    session: dict[str, Any],
    only_topics: list[str] | None = None,
) -> Generator[str, None, None]:
    """Render the comprehensive cross-cutting review (or revised topics)."""
    msgs = session["agentifier_messages"]
    topics: list[str] = session.get("agentifier_cross_cutting_topics") or []
    analysis = session.get("agentifier_cross_cutting_analysis") or {}
    decisions = session.get("agentifier_cross_cutting_decisions") or {}
    locked = session.get("agentifier_cc_ff_locked") or 0
    locked_topics = topics[:locked]

    shown = only_topics if only_topics is not None else topics
    parts: list[str] = []
    if only_topics is None:
        parts.append("## Comprehensive cross-cutting review\n")
    for t in shown:
        i = topics.index(t)
        # Show the recorded decision, falling back to the analysis view.
        view = {t: decisions.get(t) or analysis.get(t) or {}}
        body = _format_cross_cutting_topic(t, i, view, len(topics), include_prompt=False)
        if i < locked:
            parts.append(f"*(locked — decided earlier)*\n{body}")
        elif not (decisions.get(t) or {}):
            parts.append(f"{body}\n*(skipped)*")
        else:
            parts.append(body)
    display = "\n\n".join(parts) + _cc_ff_review_prompt(locked_topics)
    msgs.append({"role": "assistant", "content": display})
    session["_display_override"] = display
    yield display


def _ff_sweep_cross_cutting(
    session: dict[str, Any],
    analysis: dict[str, Any],
) -> Generator[str, None, None]:
    """D-AF3/D-AF4: adopt the analysis for all remaining topics, one review.

    The analyst has already computed every topic upfront, so the sweep makes
    no model calls: it records the recommendations (including skippable
    topics — accepting is the recommendation, skipping is a user
    prerogative) and presents the batch. Topics decided before the sweep
    are locked and kept verbatim.
    """
    topics: list[str] = session.get("agentifier_cross_cutting_topics") or []
    index: int = session.get("agentifier_cross_cutting_index") or 0
    decisions: dict[str, Any] = dict(
        session.get("agentifier_cross_cutting_decisions") or {}
    )
    for t in topics[index:]:
        decisions[t] = analysis.get(t) or {}
    session["agentifier_cross_cutting_decisions"] = decisions
    session["agentifier_cc_ff_locked"] = index
    session["agentifier_cross_cutting_ff_review"] = True
    yield from _present_cc_ff_review(session)


def _handle_cc_ff_review(
    user_input: str,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """One comprehensive review turn: confirm-all, or named topic revisions."""
    msgs = session["agentifier_messages"]
    topics: list[str] = session.get("agentifier_cross_cutting_topics") or []
    locked = session.get("agentifier_cc_ff_locked") or 0
    locked_topics = topics[:locked]
    valid_topics = topics[locked:]

    if _is_spec_confirmed(user_input):
        session["agentifier_cross_cutting_ff_review"] = False
        session["agentifier_cross_cutting_index"] = len(topics)
        session["agentifier_cross_cutting_done"] = True
        yield from _begin_priority_phase(session, llm_config)
        return

    routed, unknown, locked_hits, saw_pair = _route_ff_revision_lines(
        user_input, valid_topics, locked_topics
    )
    if not saw_pair:
        display = (
            "I couldn't read that as revisions. Give one per line as "
            "`topic: instruction`, or reply **yes** to accept all. "
            "Revisable topics: " + ", ".join(f"`{t}`" for t in valid_topics)
        )
        msgs.append({"role": "assistant", "content": display})
        session["_display_override"] = display
        yield display
        return
    if unknown or locked_hits:
        problems: list[str] = []
        if unknown:
            problems.append("unknown: " + ", ".join(f"`{t}`" for t in unknown))
        if locked_hits:
            problems.append(
                "locked (decided earlier): "
                + ", ".join(f"`{t}`" for t in locked_hits)
            )
        display = (
            "No changes applied — " + "; ".join(problems) + ". "
            "Revisable topics: " + ", ".join(f"`{t}`" for t in valid_topics)
        )
        msgs.append({"role": "assistant", "content": display})
        session["_display_override"] = display
        yield display
        return

    analysis: dict[str, Any] = dict(
        session.get("agentifier_cross_cutting_analysis") or {}
    )
    decisions: dict[str, Any] = dict(
        session.get("agentifier_cross_cutting_decisions") or {}
    )
    _, mechanisms = load_patterns()
    features = (session.get("ai_features") or {}).get("ai_features") or []
    revised: list[str] = []
    for topic, instruction in routed.items():
        if topic in SKIPPABLE_TOPICS and _is_skip(instruction):
            decisions[topic] = {}
            revised.append(topic)
            continue
        cc_input = CrossCuttingInput(
            ai_features=features,
            mechanism_patterns=mechanisms,
            llm_config=llm_config,
            topic=topic,
            revision_instruction=instruction,
            prior_decisions=decisions,
            code_review=session.get("code_review"),
        )
        yield f"\n\nRevising **{topic}**…\n\n"
        try:
            raw = ""
            for chunk in _iter_async_gen(
                _registry.stream("cross_cutting_analyst", cc_input)
            ):
                raw += chunk
        except Exception as exc:
            yield f"Cross-Cutting Analyst revision failed for `{topic}`: {exc}. Please try again."
            continue
        new_analysis = _extract_cross_cutting_analysis(raw)
        if new_analysis and topic in new_analysis:
            analysis[topic] = new_analysis[topic]
            decisions[topic] = new_analysis[topic]
            revised.append(topic)
        else:
            yield f"Could not parse revised analysis for `{topic}`. Please try again."
    session["agentifier_cross_cutting_analysis"] = analysis
    session["agentifier_cross_cutting_decisions"] = decisions
    yield from _present_cc_ff_review(session, only_topics=revised)


def _format_cross_cutting_topic(
    topic: str,
    index: int,
    analysis: dict[str, Any],
    total: int,
    include_prompt: bool = True,
) -> str:
    """Render one cross-cutting topic recommendation for review."""
    data = analysis.get(topic) or {}
    rec = data.get("recommendation", "")
    rationale = data.get("rationale", "")
    patterns = data.get("cited_patterns") or []

    lines = [
        f"### Cross-cutting decision {index + 1}/{total}: **{topic}**\n",
        f"**Recommendation:** {rec}\n",
        f"**Rationale:** {rationale}\n",
    ]
    if patterns:
        lines.append(f"**Patterns cited:** {', '.join(patterns)}\n")
    if not include_prompt:
        return "\n".join(lines)
    if topic in SKIPPABLE_TOPICS:
        lines.append(
            "---\nReply **yes** to accept, **skip** if this isn't needed, "
            "or describe what to change."
        )
    else:
        lines.append(
            "---\nReply **yes** to accept this recommendation, "
            "or describe what to change."
        )
    return "\n".join(lines)


def _is_skip(text: str | None) -> bool:
    """True when the user's reply asks to skip the current (skippable) topic."""
    if not text:
        return False
    return text.lower().strip().rstrip(".,!?") in {"skip", "skip it", "n/a", "none"}


# ---------------------------------------------------------------------------
# Phase priority helpers
# ---------------------------------------------------------------------------

_VALID_PRIORITIES = PRIORITIES

#: `name: priority` — also accepts `=`, `->` and `→`, with an optional bullet.
_PRIORITY_EDIT_RE = re.compile(
    r"^\s*(?:[-*•]\s*)?(?:\*\*)?([A-Za-z0-9_][A-Za-z0-9_.\-]*)(?:\*\*)?"
    r"\s*(?::|=|->|→)\s*(?:\*\*|`)?([A-Za-z0-9_ \-]+?)(?:\*\*|`)?\s*$"
)


@dataclass
class PriorityEdits:
    """The result of reading one free-text reply at the priority checkpoint."""

    assignments: dict[str, str] = field(default_factory=dict)
    unknown_names: list[str] = field(default_factory=list)
    bad_values: list[tuple[str, str]] = field(default_factory=list)

    @property
    def saw_pair(self) -> bool:
        """True when the reply contained anything shaped like an assignment.

        Distinguishes "the user tried to edit and got it wrong" from "the user
        said something else entirely". Only the latter may be read as a
        confirmation.
        """
        return bool(self.assignments or self.unknown_names or self.bad_values)


def _parse_priority_edits(text: str, valid_names: set[str]) -> PriorityEdits:
    """Read ``name: priority`` assignments out of a free-text reply.

    Deterministic — no LLM turn. Values are normalised for whitespace and
    hyphens, so ``steel thread`` and ``steel-thread`` both reach
    ``steel_thread``: the display writes the underscore form, but people type
    what they read.
    """
    edits = PriorityEdits()
    for segment in re.split(r"[\n;]+", text):
        if not segment.strip():
            continue
        match = _PRIORITY_EDIT_RE.match(segment)
        if not match:
            continue
        name, raw_value = match.group(1), match.group(2)
        value = re.sub(r"[\s\-]+", "_", raw_value.strip().lower())
        if value not in _VALID_PRIORITIES:
            edits.bad_values.append((name, raw_value.strip()))
        elif name not in valid_names:
            edits.unknown_names.append(name)
        else:
            edits.assignments[name] = value
    return edits


def _format_priority_table(features: list[dict[str, Any]]) -> str:
    """Render the whole feature set as one priority table.

    Priority is a property of the *set* — which features form the thinnest
    end-to-end path, what ships first, what waits — so the checkpoint shows the
    set. A per-feature walk hid the distribution until it was too late to see it.
    """
    rank = {p: i for i, p in enumerate(_VALID_PRIORITIES)}
    ordered = sorted(
        enumerate(features),
        key=lambda t: (rank.get(t[1].get("phase_priority") or "mvp", 1), t[0]),
    )
    grouped = any(f.get("composed_under") for f in features)

    header = "| Priority | Feature | Tier | Requires |"
    divider = "|---|---|---|---|"
    if grouped:
        header = "| Priority | Feature | Tier | Part of | Requires |"
        divider = "|---|---|---|---|---|"

    lines = ["### Phase priority\n", header, divider]
    for _, f in ordered:
        priority = f.get("phase_priority") or "mvp"
        requires = ", ".join(f.get("requires") or []) or "—"
        row = [f"`{priority}`", f"**{f.get('name', '')}**", f.get("tier", ""), requires]
        if grouped:
            row.insert(3, f.get("composed_under") or "—")
        lines.append("| " + " | ".join(row) + " |")

    thread = [f.get("name", "") for f in features if f.get("phase_priority") == "steel_thread"]
    lines.append("")
    if thread:
        lines.append(
            "**Steel thread** — built first, end to end: " + ", ".join(f"`{n}`" for n in thread)
        )
    else:
        lines.append("**Steel thread** — nothing assigned yet.")

    deferred = [f.get("name", "") for f in features if f.get("phase_priority") in ("v2", "future")]
    if deferred:
        lines.append(f"**Deferred past the first release:** {len(deferred)}.")

    # Name a feature that is not already in the thread, so the example does not
    # read as a no-op. Falls back safely on an empty or all-steel_thread set.
    example = next(
        (f.get("name", "") for f in features if f.get("phase_priority") != "steel_thread"),
        features[0].get("name", "feature_name") if features else "feature_name",
    )
    lines.append(
        "\n---\nReply **yes** to accept, or reassign any number of features, one per line:\n\n"
        "```\n"
        f"{example}: steel_thread\n"
        "another_feature: v2\n"
        "```\n\n"
        "Values: `steel_thread` / `mvp` / `v2` / `future`. "
        "I'll re-check the build order after each change."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 2 — Spec review conversation
# ---------------------------------------------------------------------------


def _run_spec_phase(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Handle spec-drafting phase turns."""
    msgs = session["agentifier_messages"]
    catalog_entries = (session.get("ai_catalog") or {}).get("ai_catalog", [])
    n_features = len(catalog_entries)

    if user_input is None:
        if msgs:
            yield from _replay_last_assistant(msgs)
        else:
            # Reload with ai_catalog but no message history — start fresh
            names = ", ".join(e.get("name", "") for e in catalog_entries)
            intro = (
                f"Catalog loaded ({n_features} features: {names}). "
                "Reply **yes** to begin drafting per-feature specs."
            )
            msgs.append({"role": "assistant", "content": intro})
            yield intro
        return

    # User submitted something
    msgs.append({"role": "user", "content": user_input})

    # D-AF1: a Fast Forward request sweeps the remaining specs. Checked
    # before the pending/revision branches so a press can never be read as
    # a revision instruction for the current spec.
    if user_input.strip() == FF_PROMPT:
        yield from _ff_sweep_specs(session, llm_config)
        return

    # D-AF2: comprehensive review turn after a sweep.
    if session.get("agentifier_spec_ff_review"):
        yield from _handle_spec_ff_review(user_input, session, llm_config)
        return

    spec_index: int = session.get("agentifier_spec_index") or 0
    spec_results: list[dict[str, Any]] = list(session.get("agentifier_spec_results") or [])

    # Pending = we already have a spec draft for spec_index (stored, awaiting confirm)
    is_pending = len(spec_results) > spec_index and bool(spec_results[spec_index])

    if is_pending:
        if _is_spec_confirmed(user_input):
            spec_index += 1
            session["agentifier_spec_index"] = spec_index
            if spec_index >= n_features:
                yield from _finalize_specs(session, llm_config)
                return
            revision = None
        else:
            # Treat entire user input as revision instruction
            # Clear the pending spec so _draft_and_show_spec re-drafts it
            spec_results[spec_index] = {}
            session["agentifier_spec_results"] = spec_results
            revision = user_input
    else:
        # Not pending — first draft for spec_index (user just said "yes" to begin)
        revision = None

    yield from _draft_and_show_spec(spec_index, revision, session, llm_config)


# ---------------------------------------------------------------------------
# Fast Forward sweep (D-AF series)
# ---------------------------------------------------------------------------

#: `name: instruction` — same shape as the priority-edit reader: an optional
#: bullet, an optional bold/backtick-wrapped name, a colon, free instruction.
_FF_REVISION_RE = re.compile(
    r"^\s*(?:[-*•]\s*)?(?:\*\*|`)?([A-Za-z0-9_][A-Za-z0-9_.\-]*)(?:\*\*|`)?"
    r"\s*:\s*(.+?)\s*$"
)


def _route_ff_revision_lines(
    user_input: str,
    valid_names: list[str],
    locked_names: list[str],
) -> tuple[dict[str, str], list[str], list[str], bool]:
    """Deterministically route review-turn revision lines by name.

    Returns (routed, unknown, locked_hits, saw_pair). Routing is atomic at
    the call site: any unknown or locked name means nothing is applied.
    ``saw_pair`` distinguishes "tried to give revisions and got the format
    wrong" from free-form input, mirroring the priority-edit reader.
    """
    routed: dict[str, str] = {}
    unknown: list[str] = []
    locked_hits: list[str] = []
    saw_pair = False
    for line in user_input.splitlines():
        if not line.strip():
            continue
        m = _FF_REVISION_RE.match(line)
        if not m:
            continue
        saw_pair = True
        name, instruction = m.group(1), m.group(2)
        if name in locked_names:
            locked_hits.append(name)
        elif name not in valid_names:
            unknown.append(name)
        else:
            routed[name] = instruction
    return routed, unknown, locked_hits, saw_pair


def _spec_ff_review_prompt(locked_names: list[str]) -> str:
    prompt = (
        "\n\n---\n**Comprehensive review.** Reply **yes** to save "
        "`ai_features.json` with all specs as shown, or give revisions one "
        "per line as `feature_name: instruction`."
    )
    if locked_names:
        prompt += (
            "\nLocked (confirmed earlier, not revisable here): "
            + ", ".join(f"`{n}`" for n in locked_names)
            + "."
        )
    return prompt


def _present_spec_ff_review(
    session: dict[str, Any],
    only_indices: list[int] | None = None,
    failure_note: str = "",
) -> Generator[str, None, None]:
    """Render the comprehensive spec review (or just re-drafted entries)."""
    msgs = session["agentifier_messages"]
    catalog_entries = (session.get("ai_catalog") or {}).get("ai_catalog", [])
    n = len(catalog_entries)
    results = session.get("agentifier_spec_results") or []
    locked = session.get("agentifier_spec_ff_locked") or 0
    locked_names = [e.get("name", "") for e in catalog_entries[:locked]]

    indices = only_indices if only_indices is not None else list(range(n))
    parts: list[str] = []
    if only_indices is None:
        parts.append("## Comprehensive spec review\n")
    for i in indices:
        entry = catalog_entries[i]
        spec = results[i] if len(results) > i else {}
        if i < locked:
            parts.append(
                f"*(locked — confirmed earlier)*\n"
                f"{_format_spec_as_text(entry, spec, i, n)}"
            )
        elif not spec:
            parts.append(
                f"### Feature {i + 1}/{n}: `{entry.get('name', '')}` — "
                "*(not yet drafted)*"
            )
        else:
            parts.append(_format_spec_as_text(entry, spec, i, n))
    display = (
        "\n\n".join(parts) + _spec_ff_review_prompt(locked_names) + failure_note
    )
    msgs.append({"role": "assistant", "content": display})
    session["_display_override"] = display
    yield display


def _ff_sweep_specs(
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """D-AF2/D-AF4: draft every remaining spec, then present one review.

    Same N Spec Drafter calls as the one-at-a-time loop, just unpaced. A
    pending (drafted, unconfirmed) spec is kept as-is and joins the review;
    specs confirmed before the sweep are locked. If a draft fails mid-sweep
    the sweep aborts with the error surfaced; drafts already made are kept,
    so pressing Fast Forward again resumes where it stopped.
    """
    catalog_entries = (session.get("ai_catalog") or {}).get("ai_catalog", [])
    n = len(catalog_entries)
    spec_index: int = session.get("agentifier_spec_index") or 0
    session["agentifier_spec_ff_locked"] = spec_index

    for i in range(spec_index, n):
        results = session.get("agentifier_spec_results") or []
        if len(results) > i and results[i]:
            continue  # pending draft kept as-is (D-AF4)
        yield from _draft_spec(i, None, session, llm_config)
        results = session.get("agentifier_spec_results") or []
        if not (len(results) > i and results[i]):
            # D-AF5: pause coherently — partial review, review flag set, so
            # the next input routes through the review handler whatever it is.
            failed_name = catalog_entries[i].get("name", f"feature {i + 1}")
            session["agentifier_spec_ff_review"] = True
            note = (
                f"\n\n**Sweep paused:** the spec for `{failed_name}` could not "
                "be drafted. Press ⏩ **Fast Forward** to resume drafting the "
                "remaining specs, or revise with `feature_name: instruction`."
            )
            yield from _present_spec_ff_review(session, failure_note=note)
            return

    session["agentifier_spec_ff_review"] = True
    yield from _present_spec_ff_review(session)


def _handle_spec_ff_review(
    user_input: str,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """One comprehensive review turn: confirm-all, or named revisions."""
    msgs = session["agentifier_messages"]
    catalog_entries = (session.get("ai_catalog") or {}).get("ai_catalog", [])
    n = len(catalog_entries)
    locked = session.get("agentifier_spec_ff_locked") or 0
    locked_names = [e.get("name", "") for e in catalog_entries[:locked]]
    valid_names = [e.get("name", "") for e in catalog_entries[locked:]]

    if _is_spec_confirmed(user_input):
        results = session.get("agentifier_spec_results") or []
        missing = [
            catalog_entries[i].get("name", "")
            for i in range(n)
            if not (len(results) > i and results[i])
        ]
        if missing:
            display = (
                "Cannot finalize: no spec is stored for "
                + ", ".join(f"`{m}`" for m in missing)
                + " (a revision draft failed). Revise as "
                "`feature_name: instruction` to re-draft."
            )
            msgs.append({"role": "assistant", "content": display})
            session["_display_override"] = display
            yield display
            return
        session["agentifier_spec_ff_review"] = False
        session["agentifier_spec_index"] = n
        yield from _finalize_specs(session, llm_config)
        return

    routed, unknown, locked_hits, saw_pair = _route_ff_revision_lines(
        user_input, valid_names, locked_names
    )
    if not saw_pair:
        display = (
            "I couldn't read that as revisions. Give one per line as "
            "`feature_name: instruction`, or reply **yes** to save. "
            "Revisable features: " + ", ".join(f"`{n_}`" for n_ in valid_names)
        )
        msgs.append({"role": "assistant", "content": display})
        session["_display_override"] = display
        yield display
        return
    if unknown or locked_hits:
        problems: list[str] = []
        if unknown:
            problems.append("unknown: " + ", ".join(f"`{n_}`" for n_ in unknown))
        if locked_hits:
            problems.append(
                "locked (confirmed earlier): "
                + ", ".join(f"`{n_}`" for n_ in locked_hits)
            )
        display = (
            "No changes applied — " + "; ".join(problems) + ". "
            "Revisable features: " + ", ".join(f"`{n_}`" for n_ in valid_names)
        )
        msgs.append({"role": "assistant", "content": display})
        session["_display_override"] = display
        yield display
        return

    name_to_index = {
        e.get("name", ""): i for i, e in enumerate(catalog_entries)
    }
    revised: list[int] = []
    for name, instruction in routed.items():
        i = name_to_index[name]
        results = list(session.get("agentifier_spec_results") or [])
        results[i] = {}
        session["agentifier_spec_results"] = results
        yield from _draft_spec(i, instruction, session, llm_config)
        results = session.get("agentifier_spec_results") or []
        if len(results) > i and results[i]:
            revised.append(i)
    yield from _present_spec_ff_review(session, only_indices=revised)


# ---------------------------------------------------------------------------
# Phase 3 — Cross-cutting conversation
# ---------------------------------------------------------------------------


def _run_cross_cutting_phase(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Handle cross-cutting review turns (one topic at a time)."""
    msgs = session["agentifier_messages"]
    analysis: dict[str, Any] | None = session.get("agentifier_cross_cutting_analysis")

    if user_input is None:
        if analysis is not None:
            yield from _replay_last_assistant(msgs)
        else:
            intro = (
                "All feature specs are locked. "
                "Reply to begin cross-cutting system analysis across all features."
            )
            msgs.append({"role": "assistant", "content": intro})
            yield intro
        return

    msgs.append({"role": "user", "content": user_input})

    # If no analysis yet (e.g. page reload lost it), re-run analyst
    if analysis is None:
        yield "\n\nRunning cross-cutting analysis…\n\n"
        _, mechanisms = load_patterns()
        features = (session.get("ai_features") or {}).get("ai_features") or []
        topics = session.get("agentifier_cross_cutting_topics") or warranted_topics(
            features
        )
        if not topics:
            session["agentifier_cross_cutting_topics"] = []
            session["agentifier_cross_cutting_decisions"] = {}
            session["agentifier_cross_cutting_done"] = True
            yield from _begin_priority_phase(session, llm_config)
            return
        cc_input = CrossCuttingInput(
            ai_features=features,
            mechanism_patterns=mechanisms,
            llm_config=llm_config,
            topics=topics,
            code_review=session.get("code_review"),
        )
        try:
            raw = ""
            for chunk in _iter_async_gen(_registry.stream("cross_cutting_analyst", cc_input)):
                raw += chunk
        except Exception as exc:
            err = f"Cross-Cutting Analyst failed: {exc}. Please try again."
            msgs.append({"role": "assistant", "content": err})
            session["_display_override"] = err
            yield err
            return
        analysis = _extract_cross_cutting_analysis(raw)
        if not analysis:
            err = "Could not parse cross-cutting analysis. Please try again."
            msgs.append({"role": "assistant", "content": err})
            session["_display_override"] = err
            yield err
            return
        session["agentifier_cross_cutting_topics"] = topics
        session["agentifier_cross_cutting_analysis"] = analysis
        session["agentifier_cross_cutting_index"] = 0
        session["agentifier_cross_cutting_decisions"] = {}

    topics: list[str] = session.get("agentifier_cross_cutting_topics") or list(
        CROSS_CUTTING_TOPICS
    )
    index: int = session.get("agentifier_cross_cutting_index") or 0

    # D-AF1/D-AF3: a Fast Forward request adopts the already-computed
    # analysis for every remaining topic and presents one review. Checked
    # before the confirm/revision branches so it is never read as a
    # revision instruction for the current topic.
    if user_input.strip() == FF_PROMPT:
        yield from _ff_sweep_cross_cutting(session, analysis)
        return

    if session.get("agentifier_cross_cutting_ff_review"):
        yield from _handle_cc_ff_review(user_input, session, llm_config)
        return

    current_topic = topics[index]

    if _is_spec_confirmed(user_input) or (
        _is_skip(user_input) and current_topic in SKIPPABLE_TOPICS
    ):
        # Record the decision for this topic (empty dict when skipped), then advance.
        skipped = current_topic in SKIPPABLE_TOPICS and _is_skip(user_input)
        decisions: dict[str, Any] = dict(session.get("agentifier_cross_cutting_decisions") or {})
        decisions[current_topic] = {} if skipped else (analysis.get(current_topic) or {})
        session["agentifier_cross_cutting_decisions"] = decisions
        index += 1
        session["agentifier_cross_cutting_index"] = index

        if index >= len(topics):
            # All topics reviewed — transition to priority tagging
            session["agentifier_cross_cutting_done"] = True
            yield from _begin_priority_phase(session, llm_config)
            return

        current_topic = topics[index]
        display = _format_cross_cutting_topic(current_topic, index, analysis, len(topics))
    else:
        # Revision — re-run analyst for this topic only
        _, mechanisms = load_patterns()
        features = (session.get("ai_features") or {}).get("ai_features") or []
        prior = session.get("agentifier_cross_cutting_decisions") or {}
        cc_input = CrossCuttingInput(
            ai_features=features,
            mechanism_patterns=mechanisms,
            llm_config=llm_config,
            topic=current_topic,
            revision_instruction=user_input,
            prior_decisions=prior,
            code_review=session.get("code_review"),
        )
        yield f"\n\nRevising **{current_topic}**…\n\n"
        try:
            raw = ""
            for chunk in _iter_async_gen(_registry.stream("cross_cutting_analyst", cc_input)):
                raw += chunk
        except Exception as exc:
            err = f"Cross-Cutting Analyst revision failed: {exc}. Please try again."
            msgs.append({"role": "assistant", "content": err})
            session["_display_override"] = err
            yield err
            return
        revised = _extract_cross_cutting_analysis(raw)
        if revised and current_topic in revised:
            merged = dict(analysis)
            merged[current_topic] = revised[current_topic]
            session["agentifier_cross_cutting_analysis"] = merged
            analysis = merged

        display = _format_cross_cutting_topic(current_topic, index, analysis, len(topics))

    msgs.append({"role": "assistant", "content": display})
    session["_display_override"] = display
    yield display


def _begin_priority_phase(
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Transition from cross-cutting to phase-priority tagging.

    The Prioritizer assigns ``phase_priority`` over the closed feature set in one
    draw, then a deterministic pass repairs the assignment against the wired
    graph (D-PP1 option B). The review turn that follows confirms or modifies
    that assignment over the whole set at once; it no longer originates it.
    """
    msgs = session["agentifier_messages"]
    ai_features = dict(session.get("ai_features") or {})
    features = ai_features.get("ai_features") or []

    if not features:
        yield from _complete_agentifier(session)
        return

    carried = session.get("agentifier_carried_forward") or []
    carried_names = frozenset(f.get("name", "") for f in carried if f.get("name"))

    yield (
        "### 🎚️ Prioritizer\n\n"
        "Working out what belongs in the steel thread, and what can wait…\n\n"
        "_This usually takes a few seconds._\n\n"
    )
    if _DEV_MODE:
        print("[agentifier] calling Prioritizer…", flush=True)

    outcome = PrioritizerOutcome.UNREADABLE
    overlay: dict[str, str] = {}
    try:
        out = _call_prioritizer(
            features, session.get("vision_statement") or {}, llm_config, carried
        )
        overlay, outcome = out.overlay, out.outcome
    except Exception as exc:
        if _DEV_MODE:
            print(
                f"[agentifier] Prioritizer failed ({exc}); defaulting to mvp",
                flush=True,
            )

    # Degrades safely either way: an omitted or off-enum feature becomes mvp, and
    # normalization still repairs the graph (D-PP10).
    features = apply_priority_overlay(features, overlay, carried_names)
    ai_features["ai_features"] = features
    session["ai_features"] = ai_features

    prelude = ""
    if outcome is not PrioritizerOutcome.OK:
        _log.warning(
            "Prioritizer: %s over %d features; defaulting to mvp",
            outcome.value,
            len(features),
        )
        prelude = (
            "### ⚠️ Priority analysis unavailable\n\n"
            "I couldn't read the priority analysis this time, so every feature "
            "starts at **mvp**. Adjust anything that belongs in the steel thread "
            "or can wait.\n\n"
        )

    intro = (
        "Cross-cutting decisions locked. "
        "Here's the build order for your AI features "
        "(steel_thread → mvp → v2 → future).\n\n"
    )
    full = prelude + intro + _format_priority_table(features)
    msgs.append({"role": "assistant", "content": full})
    session["_display_override"] = full
    yield full


# ---------------------------------------------------------------------------
# Phase 4 — Phase priority conversation
# ---------------------------------------------------------------------------


def _format_priority_repairs(
    before: dict[str, str],
    after: dict[str, str],
    requested: dict[str, str],
) -> list[str]:
    """Describe every priority the normalization pass moved on its own.

    A feature the developer set explicitly is only reported when normalization
    overrode them — otherwise the echo is noise.
    """
    notes: list[str] = []
    for name, new_value in after.items():
        old_value = before.get(name)
        if old_value == new_value:
            continue
        if name in requested and requested[name] == new_value:
            continue  # exactly what was asked for
        reason = (
            "overriding your change, to keep the build order valid"
            if name in requested
            else "to keep the build order valid"
        )
        notes.append(f"- `{name}`: {old_value} → **{new_value}** ({reason})")
    return notes


def _run_priority_phase(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Handle the phase-priority review turn over the whole feature set.

    The Prioritizer has already assigned every priority; this turn confirms or
    reassigns them. Replies are parsed deterministically — no LLM turn — and an
    unrecognised reply re-prompts rather than advancing, so a correction can
    never be silently discarded.
    """
    msgs = session["agentifier_messages"]
    features: list[dict[str, Any]] = list(
        (session.get("ai_features") or {}).get("ai_features") or []
    )

    if user_input is None:
        yield from _replay_last_assistant(msgs)
        return

    msgs.append({"role": "user", "content": user_input})

    by_name = {f["name"]: f for f in features if f.get("name")}
    edits = _parse_priority_edits(user_input, set(by_name))

    # Edits are read BEFORE confirmation. `_is_spec_confirmed` matches on a
    # prefix, so a reply like "next_step_planner: v2" would otherwise read as
    # the affirmative "next" and silently end the phase.
    if not edits.saw_pair:
        if _is_spec_confirmed(user_input):
            yield from _complete_agentifier(session)
            return
        display = (
            "I couldn't read that as a priority change.\n\n"
            "Reply **yes** to accept the table below, or reassign features one "
            "per line, like `feature_name: steel_thread`.\n\n"
            + _format_priority_table(features)
        )
        msgs.append({"role": "assistant", "content": display})
        session["_display_override"] = display
        yield display
        return

    carried = session.get("agentifier_carried_forward") or []
    carried_names = frozenset(f.get("name", "") for f in carried if f.get("name"))

    before = {name: f.get("phase_priority") or "mvp" for name, f in by_name.items()}
    for name, value in edits.assignments.items():
        by_name[name]["phase_priority"] = value
    normalize_priorities(features, carried_names)
    after = {name: f["phase_priority"] for name, f in by_name.items()}

    ai_features = dict(session.get("ai_features") or {})
    ai_features["ai_features"] = features
    session["ai_features"] = ai_features

    problems: list[str] = []
    if edits.unknown_names:
        problems.append(
            "No such feature: " + ", ".join(f"`{n}`" for n in edits.unknown_names)
        )
    if edits.bad_values:
        problems.append(
            "Not a priority: "
            + ", ".join(f"`{v}` (for `{n}`)" for n, v in edits.bad_values)
        )

    parts: list[str] = []
    if problems:
        parts.append("⚠️ " + " · ".join(problems) + "\n")
    repairs = _format_priority_repairs(before, after, edits.assignments)
    if repairs:
        parts.append("**Adjusted:**\n" + "\n".join(repairs) + "\n")
    elif edits.assignments:
        parts.append("Updated.\n")
    parts.append(_format_priority_table(features))

    display = "\n".join(parts)
    msgs.append({"role": "assistant", "content": display})
    session["_display_override"] = display
    yield display


# ---------------------------------------------------------------------------
# Phase 1 — Breadth-selection helpers
# ---------------------------------------------------------------------------


def _breadth_candidates(pool: list[Candidate]) -> list[dict[str, str]]:
    """Flatten the pool into the checkbox-panel candidate list, in pool order.

    The panel shows one flat list — there is no relevance ranking to band on,
    so candidates appear in Composer order. Stored under the session key
    ``agentifier_breadth_groups`` (name retained for continuity).
    """
    return [{"name": c.name, "description": c.rough_description} for c in pool]


def _reselection_pool_from_features(ai_features: dict[str, Any]) -> list[Candidate]:
    """Rebuild the candidate pool for re-selection from a completed ai_features.

    Pool = previously-selected features (``ai_features``) followed by the
    previously-deselected ones (``explicitly_rejected``). Order preserves the
    prior selection order, then rejected order; enough fields are carried for
    the breadth panel and (for newly-checked items) the Tier Analyst.
    """
    pool: list[Candidate] = []
    seen: set[str] = set()
    for f in ai_features.get("ai_features") or []:
        name = f.get("name", "")
        if not name or name in seen:
            continue
        seen.add(name)
        pool.append(
            Candidate(
                name=name,
                linked_vision_features=list(f.get("linked_vision_features") or []),
                scope=str(f.get("scope", "feature")),
                rough_description=str(f.get("rough_description", "")),
                linked_existing_workflow=str(f.get("linked_existing_workflow") or ""),
                # D-EP3: rehydrate the graph-contract edges from persisted
                # ai_features so a re-selection round preserves them.
                composed_under=str(f.get("composed_under", "")),
                requires=list(f.get("requires") or []),
            )
        )
    for r in ai_features.get("explicitly_rejected") or []:
        name = r.get("name", "")
        if not name or name in seen:
            continue
        seen.add(name)
        pool.append(
            Candidate(
                name=name,
                linked_vision_features=[],
                scope="feature",
                rough_description=str(r.get("rough_description", "")),
                linked_existing_workflow="",
            )
        )
    return pool


def _candidates_from_dicts(data: list[dict[str, Any]]) -> list[Candidate]:
    """Reconstruct Candidate objects from a serialised dict list."""
    return [
        Candidate(
            name=d["name"],
            linked_vision_features=d.get("linked_vision_features", []),
            scope=d.get("scope", "feature"),
            rough_description=d.get("rough_description", ""),
            linked_existing_workflow=d.get("linked_existing_workflow", ""),
            composed_under=d.get("composed_under", ""),
            requires=list(d.get("requires") or []),
            kind=d.get("kind", "feature"),
        )
        for d in data
    ]


# ---------------------------------------------------------------------------
# Phase 1 — Catalog conversation
# ---------------------------------------------------------------------------


def _run_catalog_phase(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Handle catalog-building phase turns.

    Sub-states (tracked by session flags):
      1. True fresh start: run Scout with progress, then (for any non-empty pool)
         cache the ranked pool, yield the breadth question, and return.
      2. Breadth pending (scout_pool set, breadth_chosen False):
         user_input=None → replay breadth question.
         user_input=answer → parse level, run TierAnalyst on survivors, fall through to LLM.
      3. Candidates already cached: rebuild seed, fall through to LLM.
      4. Normal conversation turn: append user message, fall through to LLM.
    """
    msgs = session["agentifier_messages"]
    # D-AT3: characters this turn yields as progress text before the LLM stream
    # opens. Seeds the stream helper's published total so the chars counter
    # stays monotonic instead of dropping to zero when the stream starts. Only
    # the breadth-selection branch yields before falling through to the stream;
    # every other path leaves this at 0, which is the prior behaviour.
    pre_stream_chars = 0

    if user_input is None:
        if msgs:
            yield from _replay_last_assistant(msgs)
            return

        # Breadth selection pending (Scout already ran, awaiting developer's selection)
        if (
            session.get("agentifier_scout_pool") is not None
            and not session.get("agentifier_breadth_chosen")
        ):
            intro = session.get("agentifier_breadth_intro") or ""
            yield intro
            return

        # True fresh start — no prior conversation, no pending breadth question
        candidates_data = session.get("agentifier_candidates")
        if candidates_data is None:
            vision = session.get("vision_statement")
            code_review = session.get("code_review")
            if not vision:
                yield (
                    "Agentifier requires a vision statement. "
                    "Please run Brainstormer first."
                )
                return

            # --- Revision mode detection ---------------------------------------
            # A revision round's vision carries a non-empty revision_history (its
            # last entry is this round's delta) AND an implemented predecessor
            # exists. When both hold, scope discovery to the delta: carry any
            # already-built features forward silently and inform Scout so it
            # surfaces only the new/changed surface. The trigger is the implemented
            # predecessor (mirroring Brainstormer/Designer/Phaser), NOT whether
            # that predecessor itself had AI features — a revision that introduces
            # the first AI features onto a previously AI-free project is still a
            # revision, and its new features still need the introduced_in_version
            # stamp. In that case carried-forward is simply empty. Greenfield
            # discovery is untouched (delta is None, or no implemented predecessor
            # → not a revision).
            working_dir = session.get("working_dir")
            _delta = _revision_delta(vision)
            _prior_v = (
                project_manager.latest_implemented_version(working_dir)
                if working_dir and _delta
                else None
            )
            _prior_ai = (
                project_manager.load_prior_ai_features(working_dir)
                if _prior_v is not None
                else None
            )
            _scout_revision: dict[str, Any] | None = None
            if _delta and _prior_v is not None:
                _carried = list((_prior_ai or {}).get("ai_features") or [])
                _cur_v = project_manager.resolve_phase_version(
                    working_dir, bool(code_review)
                )[0]
                session["agentifier_revision"] = True
                session["agentifier_carried_forward"] = _carried
                session["agentifier_revision_version"] = _cur_v
                session["agentifier_revision_prior_version"] = _prior_v
                session["agentifier_revision_delta"] = _delta
                session["agentifier_revision_cross_cutting"] = dict(
                    (_prior_ai or {}).get("cross_cutting") or {}
                )
                _scout_revision = {
                    "goal": _delta.get("goal", ""),
                    "changes": dict(_delta.get("changes") or {}),
                    "existing_ai_features": [
                        {
                            "name": f.get("name", ""),
                            "linked_vision_features": list(
                                f.get("linked_vision_features") or []
                            ),
                        }
                        for f in _carried
                    ],
                }

            # --- Progress: Scout -----------------------------------------------
            _vs = vision.get("vision_statement") if isinstance(vision, dict) else vision
            _project_name = (_vs.get("name", "") if isinstance(_vs, dict) else "") or ""
            _project_note = f" for **{_project_name}**" if _project_name else ""

            yield (
                f"### 🔍 Scout\n\n"
                f"Scanning your vision{_project_note} for AI/LLM integration opportunities…\n\n"
                f"Scout reads your vision statement and identifies every place where an LLM, "
                f"embedding model, or AI agent could add meaningful value. "
                f"It maps each candidate back to the vision features that motivated it, "
                f"and — on brownfield projects — notes which existing workflows it would replace.\n\n"
                f"_This usually takes 15–30 seconds._\n\n"
            )

            if _DEV_MODE:
                print("[agentifier] calling Scout…", flush=True)
            try:
                scout_output = _call_scout(
                    vision, code_review, llm_config, revision=_scout_revision
                )
            except Exception as exc:
                yield f"\n\nScout failed to analyse the vision: {exc}. Please try again."
                return
            candidates = scout_output.candidates
            if not candidates:
                if scout_output.outcome is ScoutOutcome.UNREADABLE:
                    # Soft parse failure — the model's response carried no
                    # readable candidate array. Mirror the hard-failure path
                    # rather than reporting this as a deterministic-core vision
                    # (greenfield) or a presentation-only tweak (revision).
                    yield (
                        "Scout's analysis couldn't be read this time. "
                        "Please try again."
                    )
                    return
                if session.get("agentifier_revision"):
                    # A revision whose changes introduce no NEW AI surface (e.g. a
                    # presentation-only tweak to an already-built feature). Don't
                    # bail as if greenfield — carry the established AI surface
                    # forward unchanged and finalise. _complete_agentifier folds in
                    # agentifier_carried_forward under its revision block; there is
                    # no new feature to spec-draft, so go straight there (mirroring
                    # the zero-selection completion path).
                    session["agentifier_candidates"] = []
                    session["agentifier_analyses"] = []
                    session["ai_features"] = {
                        "ai_features": [],
                        "cross_cutting": {},
                        "explicitly_rejected": [],
                        "references": [],
                        "consolidation": [],
                        "reconciliation": [],
                    }
                    session["agentifier_catalog_done"] = True
                    session["agentifier_spec_done"] = True
                    session["agentifier_cross_cutting_done"] = True
                    _n_carried = len(session.get("agentifier_carried_forward") or [])
                    if _n_carried:
                        _noun = "feature" if _n_carried == 1 else "features"
                        _verb = "is" if _n_carried == 1 else "are"
                        yield (
                            "This revision's changes don't introduce any new AI "
                            f"integration. Your **{_n_carried} already-built AI "
                            f"{_noun}** {_verb} carried forward unchanged — continue "
                            "to Designer or StackAdvisor when you're ready.\n\n"
                        )
                    else:
                        yield (
                            "This revision's changes don't introduce any new AI "
                            "integration, and there are no existing AI features to "
                            "carry forward. You can continue to Designer or "
                            "StackAdvisor.\n\n"
                        )
                    yield from _complete_agentifier(session)
                    return
                # Greenfield vision with no AI surface (e.g. a purely
                # deterministic system). Finalise the agentifier stage with an
                # empty catalog so the developer reaches STATE_AGENTIFIER_COMPLETE
                # — and gets the Continue button plus the pipeline pills — instead
                # of being stranded with no way forward. Mirrors the revision
                # no-new-AI path above, but shows a plain message rather than an
                # empty catalog table.
                session["agentifier_candidates"] = []
                session["agentifier_analyses"] = []
                session["ai_features"] = {
                    "ai_features": [],
                    "cross_cutting": {},
                    "explicitly_rejected": [],
                    "references": [],
                    "consolidation": [],
                    "reconciliation": [],
                }
                session["agentifier_catalog_done"] = True
                session["agentifier_spec_done"] = True
                session["agentifier_cross_cutting_done"] = True
                yield from _complete_agentifier(
                    session,
                    display=(
                        "Scout did not find any AI-integration opportunities in "
                        "your vision. This usually means the system is purely "
                        "deterministic, or the vision is still early-stage — so "
                        "there's no AI feature catalog to build here. You can "
                        "still continue to **Designer** or **StackAdvisor** using "
                        "the button below or the pipeline pills."
                    ),
                )
                return

            # Dependency pass — the Linker wires the graph contract
            # (composed_under / requires) over Scout's candidate set before the
            # Composer groups by it. Scout surfaces nodes; the Linker owns edges;
            # the Composer materialises coordinators from the labels. Skipped
            # below two candidates — no edge is possible, so no draw.
            if len(candidates) >= 2:
                yield (
                    "### 🔗 Linker\n\n"
                    "Mapping how these features depend on each other…\n\n"
                    "_This usually takes a few seconds._\n\n"
                )
                if _DEV_MODE:
                    print("[agentifier] calling Linker…", flush=True)
                try:
                    linker_out = _call_linker(candidates, vision, llm_config)
                    overlay, linker_outcome = linker_out.overlay, linker_out.outcome
                except Exception as exc:
                    if _DEV_MODE:
                        print(
                            f"[agentifier] Linker failed ({exc}); proceeding edgeless",
                            flush=True,
                        )
                    overlay, linker_outcome = {}, LinkerOutcome.UNREADABLE
                candidates = apply_overlay(candidates, overlay)
                if linker_outcome is LinkerOutcome.UNREADABLE:
                    # Genuine failure (unreadable even after one reparse) — an
                    # alarm is warranted, in the log and in the chat.
                    _log.warning(
                        "Linker edge: dependency analysis unreadable over %d "
                        "candidates; proceeding edgeless",
                        len(candidates),
                    )
                    yield (
                        "### ⚠️ Dependency analysis unavailable\n\n"
                        "I couldn't read the dependency analysis this time, so the "
                        "panel below won't auto-include related features. Select "
                        "interdependent features together, or re-run to try again."
                        "\n\n"
                    )
                elif not any(c.composed_under or c.requires for c in candidates):
                    # No surviving edges — legitimate for a flat feature set, so
                    # the chat note is informational, not an alarm; the log stays
                    # a WARN so a silent under-emission is still visible in
                    # telemetry (the failure mode this whole pass exists to end).
                    _log.warning(
                        "Linker edge: no edges inferred over %d candidates",
                        len(candidates),
                    )
                    yield (
                        "These features were assessed as independent — nothing "
                        "will be auto-selected for you below. If some of them feed "
                        "each other, select them together.\n\n"
                    )

            # Composition pass — group coordinated candidates under their
            # coordinators (synthesizing a head only when Scout emitted none) —
            # runs ONCE before breadth selection and before any Tier Analyst call.
            yield (
                "### 🧬 Composer\n\n"
                "Grouping coordinated candidates under their coordinators…\n\n"
                "_This usually takes a few seconds._\n\n"
            )
            _input_candidates = list(candidates)  # snapshot for diagnostics
            if _DEV_MODE:
                print("[agentifier] calling Composer…", flush=True)
                print(
                    f"[agentifier] composer: --- input ({len(_input_candidates)}) ---",
                    flush=True,
                )
                for _i, _c in enumerate(_input_candidates, 1):
                    _desc = (_c.rough_description or "")[:80]
                    print(
                        f"[agentifier] composer:   {_i}. {_c.name} [{_c.scope}] — {_desc}",
                        flush=True,
                    )
            try:
                composed = _call_composer(candidates, vision, llm_config)
            except Exception as exc:
                if _DEV_MODE:
                    print(
                        f"[agentifier] Composer failed ({exc}); using Scout output unchanged",
                        flush=True,
                    )
                composed = ComposerOutput(candidates=candidates)

            _log_composition(_input_candidates, composed)

            candidates = composed.candidates
            session["agentifier_compositions"] = [
                {
                    "coordinator": comp.coordinator,
                    "members": comp.members,
                    "head_present": comp.head_present,
                    "synthesized": comp.synthesized,
                }
                for comp in composed.compositions
            ]

            _merge_summary = ""
            if composed.compositions:
                _merge_summary = _format_composition_summary(composed.compositions)

            n_cands = len(candidates)

            # Any non-empty pool goes through the breadth panel so the developer
            # chooses which candidates to include — any, all, or none. (The
            # zero-candidate case is handled earlier.) The panel shows regardless
            # of pool size, and Tier Analyst runs on the survivors in the
            # breadth-selection turn.
            session["agentifier_scout_pool"] = _candidates_to_dicts(candidates)
            session["agentifier_breadth_chosen"] = False
            # New panel instance: the live-lock intent store keys off this nonce,
            # so a fresh panel starts from an empty developer intent.
            session["agentifier_breadth_nonce"] = uuid.uuid4().hex
            session["agentifier_breadth_groups"] = _breadth_candidates(candidates)

            _project_note_b = f" for **{_project_name}**" if _project_name else ""
            intro = (
                f"✅ Scout surfaced **{n_cands} AI "
                f"opportunit{'y' if n_cands == 1 else 'ies'}{_project_note_b}**."
                f" Select which features to include below — choose any, all, or none."
                f" Nothing is pre-selected."
            )
            if _merge_summary:
                intro = _merge_summary + "\n\n---\n\n" + intro
            # Approaches overview goes on top — the first conversational thing the
            # developer sees after Scout→Composer, ahead of the merge
            # summary and the breadth-selection prompt.  Stored in the breadth intro
            # so it also shows on the breadth-question replay path.
            intro = _APPROACHES_OVERVIEW + "\n\n---\n\n" + intro
            session["agentifier_breadth_intro"] = intro
            session["_display_override"] = intro
            yield intro
            return  # wait for developer's breadth selection
        else:
            candidates = _candidates_from_session(session)
            analyses = _analyses_from_session(session)
        brownfield = session.get("code_review") is not None
        _rev_goal = (
            (session.get("agentifier_revision_delta") or {}).get("goal", "")
            if session.get("agentifier_revision")
            else ""
        )
        seed = _build_seed_message(
            candidates, analyses, brownfield=brownfield, revision_goal=_rev_goal
        )
        msgs.append({"role": "user", "content": seed})

    elif (
        not session.get("agentifier_breadth_chosen")
        and session.get("agentifier_scout_pool") is not None
    ):
        # --- Breadth selection turn ---------------------------------------------
        # agentifier_breadth_selection is set by the checkbox callback before
        # calling _get_agent_gen; user_input is a human-readable summary only.
        pool = _candidates_from_dicts(session["agentifier_scout_pool"])
        selected_names = session.get("agentifier_breadth_selection") or []
        session["agentifier_breadth_chosen"] = True

        # Panel closure: resolve the developer's checked set under the requires
        # (auto-select producers) and coordinator (>=2 members -> on) rules to a
        # fixpoint. Authoritative and idempotent — it also repairs a raw
        # selection that somehow bypassed the panel's live lock.
        closure = close_selection(pool, selected_names)
        selected_set = closure.selected
        survivors = [c for c in pool if c.name in selected_set]
        rejected = [c for c in pool if c.name not in selected_set]

        session["agentifier_explicitly_rejected"] = [
            {
                "name": c.name,
                "rough_description": c.rough_description,
                # A coordinator only reaches here when closure turned it off
                # (< 2 selected members and not required); everything else the
                # developer left unchecked.
                "reason": (
                    "closure_coordinator_off"
                    if c.name in closure.coordinators
                    else "deselected_by_user"
                ),
            }
            for c in rejected
        ]

        # Re-selection: preserve still-selected features verbatim; only newly
        # checked (previously-rejected) features need tier review + spec drafting.
        reselection = bool(session.get("agentifier_reselection"))
        if reselection:
            preserved_map = session.get("agentifier_preserved_features") or {}
            session["agentifier_preserved_selected"] = [
                preserved_map[c.name] for c in survivors if c.name in preserved_map
            ]
            to_analyze = [c for c in survivors if c.name not in preserved_map]
        else:
            to_analyze = survivors

        if not survivors:
            # Zero-selection path: persist empty artifact and complete.
            session["agentifier_candidates"] = []
            session["agentifier_analyses"] = []
            session["ai_features"] = {
                "ai_features": [],
                "cross_cutting": {},
                "explicitly_rejected": list(session["agentifier_explicitly_rejected"]),
                "references": [],
                "consolidation": [],
                "reconciliation": [],
            }
            session["agentifier_spec_done"] = True
            session["agentifier_cross_cutting_done"] = True
            yield from _complete_agentifier(session)
            return

        if reselection and not to_analyze:
            # No new features — keep the preserved set verbatim, skip tier review
            # and spec drafting, and go straight to assembly + cross-cutting +
            # priority (which re-run over the preserved union via _finalize_specs).
            session["ai_catalog"] = {"ai_catalog": []}
            session["agentifier_catalog_done"] = True
            session["agentifier_spec_index"] = 0
            session["agentifier_spec_results"] = []
            session["agentifier_candidates"] = []
            session["agentifier_analyses"] = []
            n_p = len(session.get("agentifier_preserved_selected") or [])
            yield (
                f"\n\nKeeping **{n_p} feature{'s' if n_p != 1 else ''}** — "
                "re-checking cross-cutting concerns…\n\n"
            )
            yield from _finalize_specs(session, llm_config)
            return

        n_s = len(to_analyze)
        _intro_line = (
            f"\n\nContinuing with **{n_s} selected feature{'s' if n_s != 1 else ''}** "
            f"— running Tier Analyst…\n\n"
        )
        pre_stream_chars += len(_intro_line)
        yield _intro_line

        if _DEV_MODE:
            print(
                f"[agentifier] breadth selection: survivors={len(survivors)}/{len(pool)}; "
                f"analyzing={n_s}; calling TierAnalyst…",
                flush=True,
            )

        code_review = session.get("code_review")
        breadth_analyses: list[TierAnalystOutput] = []
        try:
            for _i, _cand in enumerate(to_analyze, 1):
                _progress_line = f"- Analysing **`{_cand.name}`** ({_i}/{n_s})…\n"
                pre_stream_chars += len(_progress_line)
                yield _progress_line
                breadth_analyses.append(_call_tier_analyst(_cand, llm_config, code_review))
        except Exception as exc:
            yield f"\nTier Analyst failed: {exc}. Please try again."
            return

        _done_line = "\n✅ Tier analysis complete.\n\n---\n\n_Preparing your briefing…_\n\n"
        pre_stream_chars += len(_done_line)
        yield _done_line

        session["agentifier_candidates"] = _candidates_to_dicts(to_analyze)
        session["agentifier_analyses"] = _analyses_to_dicts(breadth_analyses, to_analyze)

        brownfield = session.get("code_review") is not None
        _rev_goal = (
            (session.get("agentifier_revision_delta") or {}).get("goal", "")
            if session.get("agentifier_revision")
            else ""
        )
        seed = _build_seed_message(
            to_analyze, breadth_analyses, brownfield=brownfield, revision_goal=_rev_goal
        )
        msgs.append({"role": "user", "content": seed})

    else:
        msgs.append({"role": "user", "content": user_input})

    search_cfg = websearch.from_session(session)
    system = llm.build_system_prompt(ORCHESTRATOR_SYSTEM_PROMPT, search_cfg)

    yield from _stream_suppressing_json(
        llm.stream_turn(
            system, msgs, llm_config, search_cfg, agent_name="agentifier"
        ),
        session,
        seed=pre_stream_chars,
    )

    raw_reply = _last_assistant_text(msgs)
    catalog = _extract_catalog_json(raw_reply)
    if catalog is None and _suppressed_as_artifact(raw_reply):
        # D-AT-P3 (the D-SC-P3 fix, applied here). The symptom differs from the
        # other agents': the catch-all override below would set the display to
        # the raw assistant text, so an unreadable catalog block lands in the
        # chat as a wall of broken JSON rather than a blank bubble — with
        # agentifier_catalog_done still False and no way forward. Re-ask once,
        # and if that fails say so instead of showing the developer the wreckage.
        correction = _artifact_reask_prompt("AI feature catalog")
        yield from _reask_for_artifact(
            system=system,
            msgs=msgs,
            llm_config=llm_config,
            search_config=search_cfg,
            agent_name="agentifier",
            correction=correction,
            status_line=_artifact_reask_status("catalog"),
            session=session,
            seed=pre_stream_chars + len(raw_reply),
        )
        catalog = _extract_catalog_json(_last_assistant_text(msgs))
        if catalog is None:
            _abandon_reask(
                msgs, correction, _artifact_fallback("AI feature catalog"), session
            )
    if catalog:
        session["ai_catalog"] = catalog
        session["agentifier_catalog_done"] = True
        session["agentifier_spec_index"] = 0
        session["agentifier_spec_results"] = []
        catalog_display = _format_catalog_as_text(catalog)
        msgs[-1]["content"] = catalog_display
        session["_display_override"] = catalog_display

    # Always clear progress messages from the window — show only the LLM's response.
    # (The catalog case above already sets _display_override; this covers greeting turns.)
    if not session.get("_display_override"):
        _assistant_text = _last_assistant_text(msgs)
        if _assistant_text:
            session["_display_override"] = _assistant_text


# ---------------------------------------------------------------------------
# Main agent entry point
# ---------------------------------------------------------------------------

import re  # noqa: E402 — kept here to avoid circular-import confusion at module level


# --- Full-restart reset (D-TA1) --------------------------------------------
#
# One list, two consumers: the stale-input rediscovery inside _handle_reentry,
# and the developer-initiated "Try Again" on the breadth panel. Both need the
# flow returned to the state a fresh Scout draw expects, so they must not drift
# apart — an earlier partial list left agentifier_revision* behind, which would
# carry a prior round's revision framing into a draw that no longer qualifies as
# one.
#
# Keys with a _default_session entry are restored to that value rather than
# popped, so the session keeps its documented shape for callers that index them
# directly. tests/agentifier/test_try_again.py asserts this map agrees with
# _default_session on every key the two share, and that no agentifier_* key
# escapes both collections.
_RESTART_DEFAULTS: dict[str, Any] = {
    "agentifier_messages": [],
    "agentifier_scout_pool": None,
    "agentifier_breadth_chosen": False,
    "agentifier_breadth_groups": None,
    "agentifier_breadth_intro": None,
    "agentifier_breadth_selection": None,
    "agentifier_explicitly_rejected": None,
    "agentifier_candidates": None,
    "agentifier_analyses": None,
    "ai_catalog": None,
    "agentifier_catalog_done": False,
    "agentifier_spec_index": 0,
    "agentifier_spec_results": [],
    "agentifier_spec_done": False,
    "agentifier_cross_cutting_analysis": None,
    "agentifier_cross_cutting_topics": [],
    "agentifier_cross_cutting_index": 0,
    "agentifier_cross_cutting_decisions": {},
    "agentifier_cross_cutting_done": False,
    "agentifier_priority_done": False,
    "agentifier_stale_acknowledged": {},
}

# Keys with no _default_session entry: popped outright. The revision block is
# re-derived from disk by _run_catalog_phase's fresh-start branch (it reads the
# vision's revision_history and the latest *implemented* round), so clearing it
# here is what lets a Try Again inside a revision round draw a genuinely new
# candidate set while still being recognised as a revision.
_RESTART_POP: tuple[str, ...] = (
    "agentifier_reselection",
    "agentifier_preserved_features",
    "agentifier_preserved_selected",
    "agentifier_compositions",
    "agentifier_breadth_nonce",
    "agentifier_artifact_msg_count",
    "agentifier_carried_forward",
    "agentifier_revision",
    "agentifier_revision_version",
    "agentifier_revision_prior_version",
    "agentifier_revision_delta",
    "agentifier_revision_cross_cutting",
    # D-AF: a restart must not resurrect a dead FF review state.
    "agentifier_spec_ff_review",
    "agentifier_spec_ff_locked",
    "agentifier_cross_cutting_ff_review",
    "agentifier_cc_ff_locked",
)


def reset_agentifier_flow(session: dict[str, Any]) -> None:
    """Return the Agentifier flow to the state a fresh Scout draw expects.

    Session-only: no artifact on disk is read, written, or deleted. The current
    round's ``ai_features.json`` survives because ``_persist_artifacts`` writes
    it solely under ``STATE_AGENTIFIER_COMPLETE``, which this demotes; earlier
    implemented rounds are never a write target at all. ``session["ai_features"]``
    is deliberately left in place so session and disk stay consistent while the
    redraw runs — ``_complete_agentifier`` replaces it at the new terminal.
    """
    for key, value in _RESTART_DEFAULTS.items():
        session[key] = copy.deepcopy(value)
    for key in _RESTART_POP:
        session.pop(key, None)
    session["agentifier_state"] = STATE_IN_PROGRESS


def _handle_reentry(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Re-entry into a completed Agentifier.

    If the vision (or code review) is newer than ai_features.json, reset to a
    fresh discovery run so Scout→Composer re-run. Otherwise open the
    re-selection panel: rebuild the candidate pool from the completed
    ai_features, pre-check the previously-selected features, and let the
    developer toggle the set without re-running discovery. Newly-checked
    features flow through the normal tier-review + spec drafting; still-checked
    ones are preserved verbatim (handled at breadth-submit / _finalize_specs).
    """
    # Re-entry re-opens the flow (reselection panel or, when inputs are stale, a
    # full rediscovery). Demote the completion state so the "Continue to Designer"
    # / "Download ai_features" buttons — gated on STATE_AGENTIFIER_COMPLETE — stop
    # rendering against the pre-revision ai_features. _complete_agentifier restores
    # STATE_AGENTIFIER_COMPLETE at the true terminal, and every completion path
    # (new features, no-new-features, zero-selection, stale rediscovery) routes
    # through it, so the buttons reappear exactly when the flow re-completes.
    session["agentifier_state"] = STATE_IN_PROGRESS

    working_dir = session.get("working_dir")
    stale = (
        project_manager.detect_stale_inputs(working_dir, "agentifier")
        if working_dir
        else {}
    )

    if stale:
        # Vision / code review changed since the features were generated →
        # discard the completed state and re-run discovery from scratch. Shares
        # its reset with the panel's Try Again (D-TA1): both need exactly the
        # state a fresh Scout draw expects, so there is one list, not two.
        reset_agentifier_flow(session)
        session["agentifier_stale_acknowledged"] = dict(stale)
        if _DEV_MODE:
            print(
                f"[agentifier] re-entry: vision newer ({list(stale)}); "
                "re-running discovery",
                flush=True,
            )
        yield from _run_catalog_phase(None, session, llm_config)
        return

    # Not stale → re-selection from the existing pool, no Scout/Composer.
    ai_features = session.get("ai_features") or {}
    pool = _reselection_pool_from_features(ai_features)
    if not pool:
        # Nothing to re-select (shouldn't happen for a complete project).
        yield from _replay_last_assistant(session["agentifier_messages"])
        return

    selected = [
        f for f in (ai_features.get("ai_features") or []) if f.get("name")
    ]
    selected_names = [f["name"] for f in selected]
    session["agentifier_preserved_features"] = {f["name"]: f for f in selected}
    session["agentifier_scout_pool"] = _candidates_to_dicts(pool)
    session["agentifier_breadth_groups"] = _breadth_candidates(pool)
    session["agentifier_breadth_selection"] = selected_names
    session["agentifier_breadth_chosen"] = False
    # New panel instance: seed the live-lock intent store from the pre-checked
    # set (see the nonce handling in on_breadth_change).
    session["agentifier_breadth_nonce"] = uuid.uuid4().hex
    session["agentifier_reselection"] = True
    for flag in (
        "agentifier_catalog_done",
        "agentifier_spec_done",
        "agentifier_cross_cutting_done",
        "agentifier_priority_done",
    ):
        session[flag] = False
    session["agentifier_messages"] = []

    n = len(pool)
    intro = (
        f"**Revising your AI features.** You previously selected "
        f"{len(selected_names)} of {n} candidate{'s' if n != 1 else ''}. The "
        "previously-selected features are checked below — uncheck any you want "
        "to drop, and check any you'd like to add. Newly-added features go "
        "through tier review and spec drafting; unchanged ones are kept as-is."
    )
    session["agentifier_breadth_intro"] = intro
    session["_display_override"] = intro
    if _DEV_MODE:
        print(
            f"[agentifier] re-entry: re-selection panel "
            f"({len(selected_names)}/{n} pre-checked)",
            flush=True,
        )
    yield intro
    return


def run(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Agentifier orchestrator — catalog + spec-drafting conversation.

    Phase 1: Scout + TierAnalyst + LLM-driven tier review → ai_catalog
    Phase 2: SpecDrafter (StreamingSubAgent) per feature → ai_features.json

    Yields text chunks consumed by streaming.start().
    Mutates `session` to track conversation state and artifacts.
    """
    if "agentifier_messages" not in session:
        session["agentifier_messages"] = []

    msgs = session["agentifier_messages"]
    user_input = _drop_orphan_or_route_to_fresh_start(msgs, user_input)

    if not session.get("agentifier_catalog_done"):
        yield from _run_catalog_phase(user_input, session, llm_config)
    elif not session.get("agentifier_spec_done"):
        yield from _run_spec_phase(user_input, session, llm_config)
    elif not session.get("agentifier_cross_cutting_done"):
        yield from _run_cross_cutting_phase(user_input, session, llm_config)
    elif not session.get("agentifier_priority_done"):
        yield from _run_priority_phase(user_input, session, llm_config)
    else:
        yield from _handle_reentry(user_input, session, llm_config)
