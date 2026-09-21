"""Agentifier sub-agent dispatch, seed message, and (de)serialisation.

Cleanup Phase 4i moved the leaf-pure edges of ``agentifier.py`` here: the
sub-agent registry and the async->sync bridge that drives it, the five
``_call_*`` wrappers, the orchestrator seed message and its graph-placement
lines, and the candidate/analysis (de)serialisers.

Nothing here yields chat text or writes a session key, and nothing here imports
``spec4.agentifier.agentifier`` -- this module is a leaf, so the split cannot
create a cycle. Every name is re-exported from ``agentifier`` and keeps its
spelling, so ``spec4.agentifier.agentifier._registry`` still resolves to the
one registry object and ``patch(".._registry.stream")`` still reaches it.
"""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import Callable, Generator
from typing import TYPE_CHECKING, Any

from spec4.agentifier.composer import (
    ComposerAgent,
    ComposerInput,
    ComposerOutput,
)
from spec4.agentifier.cross_cutting_analyst import CrossCuttingAnalyst
from spec4.agentifier.linker import (
    LinkerAgent,
    LinkerInput,
    LinkerOutput,
)
from spec4.agentifier.pattern_loader import load_patterns
from spec4.agentifier.prioritizer import (
    PrioritizerAgent,
    PrioritizerInput,
    PrioritizerOutput,
)
from spec4.agentifier.scout import (
    Candidate,
    ScoutAgent,
    ScoutInput,
    ScoutOutput,
)
from spec4.agentifier.spec_drafter import SpecDrafterAgent
from spec4.agentifier.subagents import SubAgentRegistry
from spec4.agentifier.tier_analyst import (
    TierAnalystAgent,
    TierAnalystInput,
    TierAnalystOutput,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterable

__all__ = [
    "_analyses_from_session",
    "analyses_to_dicts",
    "_build_registry",
    "build_seed_message",
    "_call_composer",
    "_call_linker",
    "_call_prioritizer",
    "_call_scout",
    "_call_tier_analyst",
    "candidates_from_dicts",
    "_candidates_from_session",
    "candidates_to_dicts",
    "_graph_placement_lines",
    "_iter_async_gen",
    "_registry",
    "vision_mvp_feature_names",
    "_vision_purpose",
]

# ---------------------------------------------------------------------------
# Sub-agent registry
# ---------------------------------------------------------------------------


def _build_registry() -> SubAgentRegistry:
    """Every sub-agent the orchestrator can dispatch to, in registration order.

    Built once at module import and read-only afterwards, so it needs no guard.
    Deliberately *not* initialised from ``app.py``: this module is imported
    lazily from ``callbacks`` and ``session`` and never from ``app``, so an
    init call there would make a deferred import eager and add an
    ``app`` → ``agentifier`` edge the layering does not have.
    """
    registry = SubAgentRegistry()
    for agent in (
        ScoutAgent(),
        LinkerAgent(),
        ComposerAgent(),
        TierAnalystAgent(),
        SpecDrafterAgent(),
        CrossCuttingAnalyst(),
        PrioritizerAgent(),
    ):
        registry.register(agent)
    return registry


_registry = _build_registry()

# ---------------------------------------------------------------------------
# Async → sync streaming bridge
# ---------------------------------------------------------------------------


def _iter_async_gen(async_gen: AsyncIterable[str]) -> Generator[str, None, None]:
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
# Sub-agent dispatch wrappers
# ---------------------------------------------------------------------------


def _call_scout(  # noqa: PLR0913  # the Scout call contract, threaded straight through
    vision: dict[str, Any],
    code_review: dict[str, Any] | None,
    llm_config: dict[str, Any],
    revision: dict[str, Any] | None = None,
    on_chunk: Callable[[str], None] | None = None,
    on_thinking: Callable[[str], None] | None = None,
    brownfield: bool = False,
    guidance: dict[str, Any] | None = None,
) -> ScoutOutput:
    """Invoke Scout synchronously via the registry.

    ``brownfield`` is the developer's answer, not an inference from
    ``code_review`` — see the note on :class:`ScoutInput`. ``guidance`` is the
    developer's redraw guidance from the breadth panel's Try Again (D-TA7),
    ``None`` for a first draw or an un-guided redraw.
    """
    scout_input = ScoutInput(
        vision=vision,
        code_review=code_review,
        llm_config=llm_config,
        revision=revision,
        on_chunk=on_chunk,
        on_thinking=on_thinking,
        brownfield=brownfield,
        guidance=guidance,
    )
    scout_output: ScoutOutput = asyncio.run(_registry.run("scout", scout_input))
    return scout_output


def _vision_purpose(vision: dict[str, Any]) -> str:
    """Best-effort one-line project purpose for the Linker's context."""
    vs = vision.get("vision_statement") if isinstance(vision, dict) else None
    inner = vs.get("vision") if isinstance(vs, dict) else None
    if isinstance(inner, dict):
        return str(inner.get("purpose") or inner.get("description") or "")
    if isinstance(vs, dict):
        return str(vs.get("purpose") or vs.get("description") or vs.get("name") or "")
    return ""


def vision_mvp_feature_names(vision: dict[str, Any]) -> list[str]:
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
    on_chunk: Callable[[str], None] | None = None,
    on_thinking: Callable[[str], None] | None = None,
) -> LinkerOutput:
    """Invoke the Linker synchronously via the registry, returning its output."""
    li = LinkerInput(
        candidates=candidates,
        vision_purpose=_vision_purpose(vision),
        llm_config=llm_config,
        on_chunk=on_chunk,
        on_thinking=on_thinking,
    )
    linker_output: LinkerOutput = asyncio.run(_registry.run("linker", li))
    return linker_output


def _call_composer(
    candidates: list[Candidate],
    vision: dict[str, Any],
    llm_config: dict[str, Any],
    on_chunk: Callable[[str], None] | None = None,
    on_thinking: Callable[[str], None] | None = None,
) -> ComposerOutput:
    """Invoke Composer synchronously via the registry."""
    ci = ComposerInput(
        candidates=candidates,
        vision=vision,
        llm_config=llm_config,
        on_chunk=on_chunk,
        on_thinking=on_thinking,
    )
    composer_output: ComposerOutput = asyncio.run(_registry.run("composer", ci))
    return composer_output


def _call_prioritizer(  # noqa: PLR0913  # the Prioritizer call contract, threaded straight through
    features: list[dict[str, Any]],
    vision: dict[str, Any],
    llm_config: dict[str, Any],
    carried_forward: list[dict[str, Any]],
    on_chunk: Callable[[str], None] | None = None,
    on_thinking: Callable[[str], None] | None = None,
) -> PrioritizerOutput:
    """Invoke the Prioritizer synchronously via the registry, returning its output."""
    pi = PrioritizerInput(
        features=features,
        vision_purpose=_vision_purpose(vision),
        llm_config=llm_config,
        carried_forward=carried_forward,
        mvp_vision_features=vision_mvp_feature_names(vision),
        on_chunk=on_chunk,
        on_thinking=on_thinking,
    )
    prioritizer_output: PrioritizerOutput = asyncio.run(
        _registry.run("prioritizer", pi)
    )
    return prioritizer_output


def _call_tier_analyst(  # noqa: PLR0913  # the TierAnalyst call contract, threaded straight through
    candidate: Candidate,
    llm_config: dict[str, Any],
    code_review: dict[str, Any] | None = None,
    on_chunk: Callable[[str], None] | None = None,
    on_thinking: Callable[[str], None] | None = None,
    guidance: list[str] | None = None,
) -> TierAnalystOutput:
    """Invoke TierAnalyst synchronously via the registry.

    ``guidance`` is the developer's redraw notes (D-TA7), when the panel that
    produced this candidate was reached through a guided Try Again.
    """
    tiers, mechanisms = load_patterns()
    ta_input = TierAnalystInput(
        candidate=candidate,
        llm_config=llm_config,
        tier_patterns=tiers,
        code_review=code_review,
        mechanism_patterns=mechanisms,
        guidance=list(guidance or []),
        on_chunk=on_chunk,
        on_thinking=on_thinking,
    )
    tier_output: TierAnalystOutput = asyncio.run(
        _registry.run("tier_analyst", ta_input)
    )
    return tier_output


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


def build_seed_message(
    candidates: list[Candidate],
    analyses: list[TierAnalystOutput],
    brownfield: bool = False,
    revision_goal: str = "",
) -> str:
    """Build the first user message injected into the orchestrator conversation."""
    mode_note = _seed_mode_note(revision_goal, brownfield)
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
    for i, (cand, analysis) in enumerate(zip(candidates, analyses, strict=False), 1):
        lines = _candidate_head_lines(
            i, cand, present, members_by_coordinator, required_by
        )
        _candidate_analysis_lines(analysis, lines)
        parts.append("\n".join(lines))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Phase 1 — Session serialisation helpers
# ---------------------------------------------------------------------------


def candidates_to_dicts(candidates: list[Candidate]) -> list[dict[str, Any]]:
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


def analyses_to_dicts(
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


def candidates_from_dicts(data: list[dict[str, Any]]) -> list[Candidate]:
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


def _seed_mode_note(revision_goal: str, brownfield: bool) -> str:
    """The revision / brownfield / greenfield framing note for the seed intro."""
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
    return mode_note


def _candidate_head_lines(
    i: int,
    cand: Candidate,
    present: set[str],
    members_by_coordinator: dict[str, list[str]],
    required_by: dict[str, list[str]],
) -> list[str]:
    """One candidate's heading, description, graph placement and vision links."""
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
    return lines


def _candidate_analysis_lines(analysis: TierAnalystOutput, lines: list[str]) -> None:
    """The Tier Analyst recommendation, rationale and risk lines for one candidate."""
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
        lines.append(
            "Risks of going higher: " + "; ".join(analysis.risks_of_going_higher)
        )
    if analysis.risks_of_going_lower:
        lines.append(
            "Risks of going lower: " + "; ".join(analysis.risks_of_going_lower)
        )
