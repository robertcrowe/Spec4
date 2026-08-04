"""Composer sub-agent for Agentifier — replaces the Consolidator.

Reads the Scout graph-contract edges (``composed_under`` / ``requires``) instead
of re-detecting overlap with an LLM, and crowns coordinated groups losslessly
instead of merging destructively:

* groups candidates by ``composed_under``;
* a head-present group passes through — the coordinator is already an emitted
  candidate and its members already point at it;
* a headless group (>=2 members, guaranteed by the parser's integrity pass) gets
  a synthesized coordinator — one LLM call per group to write a vision-grounded
  description (the only generative act). If that call fails, the group presents
  flat: its members are detached to stand alone, so nothing is lost;
* cross-features and standalones pass through untouched;
* every candidate's ``rough_description`` is then enriched, deterministically, to
  surface its membership (``composed_under``, both sides) and its dependencies
  (``requires``) to the reader.

Deterministic whenever every group has a head (the measured norm) — zero LLM
calls. Never drops a candidate; the input's edge integrity is trusted (the
Linker's pass already ran ``_normalize_edges``), so the Composer does not
re-validate.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from spec4.agentifier.scout import Candidate
from spec4.agentifier.subagents import validate_dataclass_input
from spec4.llm import complete

_DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"

_HEAD_SYNTHESIS_SYSTEM_PROMPT = """\
You are the Composer for Agentifier. Scout surfaced a coordinated capability as a
set of member candidates that all compose under one coordinator, but did not emit
the coordinator itself. Write that coordinator.

You are given the coordinator's name, the members it coordinates (name and
description), and the vision feature(s) they serve. Produce ONE or TWO sentences
describing the coordinator as a single capability: what it takes in, what it
produces, and that it coordinates its members to do so. Ground it in the vision
feature(s) named. Do not invent members or steps beyond those given, and do not
list the members verbatim — describe the coordinated whole.

Return ONLY the description text — no preamble, no name, no markdown.
"""


@dataclass
class ComposerInput:
    """Input for the Composer sub-agent."""

    candidates: list[Candidate]
    vision: dict[str, Any]
    llm_config: dict[str, Any]


@dataclass
class Composition:
    """One coordinated group: a coordinator and the members composed under it."""

    coordinator: str
    members: list[str]
    head_present: bool
    synthesized: bool = False


@dataclass
class ComposerOutput:
    """Output from the Composer — candidates crowned and enriched, nothing merged."""

    candidates: list[Candidate]
    compositions: list[Composition] = field(default_factory=list)
    n_synthesized: int = 0


def _group_by_composed_under(
    candidates: list[Candidate],
) -> tuple[dict[str, list[Candidate]], set[str]]:
    """Return (members keyed by coordinator label, set of candidate names)."""
    names = {c.name for c in candidates}
    members_by_label: dict[str, list[Candidate]] = defaultdict(list)
    for c in candidates:
        if c.composed_under:
            members_by_label[c.composed_under].append(c)
    return members_by_label, names


def _union_features(members: list[Candidate]) -> list[str]:
    """Order-preserving union of the members' linked vision features."""
    seen: list[str] = []
    for m in members:
        for f in m.linked_vision_features:
            if f not in seen:
                seen.append(f)
    return seen


def _synthesize_head_description(
    coordinator: str,
    members: list[Candidate],
    vision_features: list[str],
    llm_config: dict[str, Any],
) -> str | None:
    """The one generative act: write a headless coordinator's description.

    Returns the description text, or None on any failure (caller presents the
    group flat).
    """
    member_block = "\n".join(f"- {m.name}: {m.rough_description}" for m in members)
    feat = ", ".join(vision_features) if vision_features else "(none named)"
    user_content = (
        f"Coordinator name: {coordinator}\n"
        f"Vision feature(s) served: {feat}\n"
        f"Members it coordinates:\n{member_block}\n\n"
        "Write the coordinator's description."
    )
    try:
        response = complete(
            llm_config=llm_config,
            messages=[
                {"role": "system", "content": _HEAD_SYNTHESIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            agent_name="composer",
            stream=False,
        )
        text = (response.choices[0].message.content or "").strip()
        return text or None
    except Exception:
        return None


def _enrich_descriptions(
    candidates: list[Candidate],
    members_by_label: dict[str, list[Candidate]],
) -> None:
    """Surface composed_under (both sides) and requires in each description (C9).

    A coordinator is a head with >=2 members (C-series): a single-member group
    is a normal candidate plus a normal member, so neither the head's
    "Coordinates" sentence nor the lone member's "Part of" sentence is emitted
    for it. This mirrors the panel's close_selection >=2 rule.

    Deterministic and idempotent: each sentence is computed from the base
    description and appended only if not already present, so a re-run cannot
    double it.
    """
    coordinator_members = {
        label: [m.name for m in members]
        for label, members in members_by_label.items()
        if len(members) >= 2
    }
    for c in candidates:
        desc = c.rough_description.rstrip()
        additions: list[str] = []
        if c.composed_under in coordinator_members:
            s = f"Part of the {c.composed_under} capability."
            if s not in desc:
                additions.append(s)
        if c.name in coordinator_members:
            s = f"Coordinates {', '.join(coordinator_members[c.name])}."
            if s not in desc:
                additions.append(s)
        if c.requires:
            s = f"Depends on {', '.join(c.requires)}."
            if s not in desc:
                additions.append(s)
        if additions:
            joined = " ".join(additions)
            c.rough_description = f"{desc} {joined}".strip() if desc else joined


class ComposerAgent:
    """Request/response sub-agent that crowns coordinated groups from edges.

    Replaces the Consolidator: reads ``composed_under`` rather than re-detecting
    overlap, and keeps members under a coordinator node rather than merging them
    away. Deterministic unless a headless group needs its head synthesized.
    """

    name = "composer"

    async def run(self, input: ComposerInput) -> ComposerOutput:  # noqa: A002
        validate_dataclass_input(input, ComposerInput)

        candidates = list(input.candidates)
        if not candidates:
            return ComposerOutput(candidates=[], compositions=[], n_synthesized=0)

        members_by_label, names = _group_by_composed_under(candidates)
        compositions: list[Composition] = []
        synthesized_heads: dict[str, Candidate] = {}
        n_synthesized = 0

        for label, members in members_by_label.items():
            if label in names:
                # A coordinator has >=2 members (C-series). A single-member
                # head-present group is a normal candidate plus a normal member,
                # so record no composition — no surface should crown it.
                if len(members) >= 2:
                    compositions.append(
                        Composition(
                            coordinator=label,
                            members=[m.name for m in members],
                            head_present=True,
                        )
                    )
                continue

            # Headless group (>=2 guaranteed by the parser). Crown it.
            vision_features = _union_features(members)
            desc = _synthesize_head_description(
                label, members, vision_features, input.llm_config
            )
            if desc is None:
                # Present flat — detach so the members stand alone. Nothing lost.
                for m in members:
                    m.composed_under = ""
                    m.scope = "feature"
                if _DEV_MODE:
                    print(
                        f"[agentifier] composer: head synthesis failed for "
                        f"'{label}'; group presents flat",
                        flush=True,
                    )
                continue

            synthesized_heads[label] = Candidate(
                name=label,
                linked_vision_features=vision_features,
                scope="feature",
                rough_description=desc,
                composed_under="",
                requires=[],
            )
            n_synthesized += 1
            compositions.append(
                Composition(
                    coordinator=label,
                    members=[m.name for m in members],
                    head_present=False,
                    synthesized=True,
                )
            )

        # Build the augmented list: insert each synthesized head just before its
        # first member, preserving original order otherwise. Nothing is dropped.
        inserted: set[str] = set()
        out: list[Candidate] = []
        for c in candidates:
            label = c.composed_under
            if label in synthesized_heads and label not in inserted:
                out.append(synthesized_heads[label])
                inserted.add(label)
            out.append(c)

        # Final scope derivation (contract §8) — composed_under is now settled,
        # so scope is a pure function of the finalized graph and no longer a Scout
        # guess: a member is a sub_feature; a coordinator (referenced under
        # composed_under) is a feature; a remaining standalone that relates to more
        # than one vision feature is cross_feature; anything else is a feature.
        referenced = {c.composed_under for c in out if c.composed_under}
        for c in out:
            if c.composed_under:
                c.scope = "sub_feature"
            elif c.name in referenced:
                c.scope = "feature"
            elif len(c.linked_vision_features) > 1:
                c.scope = "cross_feature"
            else:
                c.scope = "feature"

        # Enrich over the final list so synthesized heads get their coordinator
        # sentence too.
        members_by_label_final, _ = _group_by_composed_under(out)
        _enrich_descriptions(out, members_by_label_final)

        if _DEV_MODE:
            print(
                f"[agentifier] composer: {len(candidates)} in → {len(out)} out, "
                f"{len(compositions)} composition(s), {n_synthesized} synthesized head(s)",
                flush=True,
            )

        return ComposerOutput(
            candidates=out, compositions=compositions, n_synthesized=n_synthesized
        )