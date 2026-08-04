"""Deterministic coverage checks over Phaser's declared phase mappings.

Phases declare what they build in two arrays with two id spaces (D-PH2a):
``features[]`` declares **product-feature ids** from the Brainstormer spine
(``feature_specs.json``), and ``capabilities[]`` declares **AI catalog-node
ids** (``ai_features.json``, including infrastructure). The array determines
the id space, dissolving name collisions between the two (a capability named
after the feature it serves is a real, observed shape).

That declaration makes these properties checkable in code, with no model call:

* **Product presence** (D-PH2b) — every spine feature is built by some phase.
  The spine is MVP by construction, so undeclared is a hard failure — except
  features **excluded** by the developer's Agentifier selection (rejected AI
  implementation, empty serves-join; see ``excluded_feature_ids``), which pass
  undeclared with an advisory naming the Agentifier path. A phase that
  *declares* an excluded feature is a hard failure: the plan contradicting the
  developer's selection.

* **Capability presence** — every ``steel_thread``/``mvp`` catalog node is
  built by some phase. ``v2``/``future`` nodes are legitimately deferred and
  only ever produce advisories.

* **Infrastructure ordering** — infrastructure is a *source node*: features
  ``requires`` it, never the reverse. A phase that builds a consumer before
  any phase stands up its substrate is a broken build order (hard failure).

* **Product-dependency ordering** (D-PH2f, advisory) — the spine's
  ``dependencies`` say a producer is built no later than its consumer. Sound
  in principle but reconciliation on branching graphs is young, so violations
  surface as advisories, promotable once post-round draws show the base rate.

Failures are emitted in the ``(phase_number, errors)`` shape that
``format_validation_errors_for_retry`` already consumes, so they fold into the
existing schema-validation retry loop rather than adding a second one.

Gating is the caller's job: this runs on **fresh generations only**. A
brownfield or revision round deliberately emits a subset of phases, and its
partial graph would false-positive. Product-side checks additionally skip
revision rounds entirely: the product spine carries no version partition yet
(deferred; the AI side partitions via ``introduced_in_version`` as before).

Edge-key note: ``requires`` and ``composed_under`` hold feature *names*, while
declarations hold slugs (``id = slug(name)``). All joins here go through an
explicit name→id map rather than assuming the two coincide. Spine
``dependencies`` already hold product ids.
"""

from __future__ import annotations

import re
from typing import Any

from spec4.agentifier.infra_expander import INFRA_KIND
from spec4.agents._utils import excluded_feature_ids

__all__ = ["ENFORCED_PRIORITIES", "check_phase_coverage"]


# Priorities a phase set must actually build. `v2`/`future` are deferrable by
# design (D-PS7 iii) and only ever produce advisories.
ENFORCED_PRIORITIES: tuple[str, ...] = ("steel_thread", "mvp")


def _slug(name: str) -> str:
    """Mirror ``_build_ai_features``' id derivation."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower()) if name else ""


def _declarations(
    phases: list[dict[str, Any]],
    key: str,
) -> list[tuple[int | None, dict[str, Any]]]:
    """Flatten every phase's ``key`` array into (phase_number, decl) pairs."""
    out: list[tuple[int | None, dict[str, Any]]] = []
    for phase in phases:
        raw = phase.get("phase_number")
        number = raw if isinstance(raw, int) else None
        for decl in phase.get(key) or []:
            if isinstance(decl, dict):
                out.append((number, decl))
    return out


def _to_phase_nodes(
    ai_features: dict[str, Any] | None,
    revision_version: int | None,
) -> list[dict[str, Any]]:
    """The catalog nodes this round is responsible for building."""
    nodes = [
        n for n in ((ai_features or {}).get("ai_features") or []) if isinstance(n, dict)
    ]
    if revision_version is None:
        return nodes
    return [n for n in nodes if n.get("introduced_in_version") == revision_version]


def _check_declared(
    phases: list[dict[str, Any]],
    key: str,
    valid_ids: set[str],
    id_source: str,
) -> tuple[list[tuple[int | None, list[str]]], dict[str, dict[int | None, str]]]:
    """Validity, duplication, and role sanity for one declaration array.

    Returns ``(failures, declared)`` where ``declared`` maps id ->
    {phase_number: role} for ids that resolved in ``valid_ids``.
    """
    failures: list[tuple[int | None, list[str]]] = []
    seen_in_phase: dict[int | None, set[str]] = {}
    declared: dict[str, dict[int | None, str]] = {}

    for number, decl in _declarations(phases, key):
        fid = str(decl.get("id") or "")
        errors: list[str] = []
        if fid not in valid_ids:
            errors.append(
                f"{key}: declared id '{fid}' does not match any id in "
                f"{id_source}. Use the exact `id` shown there."
            )
        else:
            bucket = seen_in_phase.setdefault(number, set())
            if fid in bucket:
                errors.append(
                    f"{key}: id '{fid}' is declared more than once in this phase."
                )
            bucket.add(fid)
            declared.setdefault(fid, {})[number] = str(decl.get("role") or "")
        if errors:
            failures.append((number, errors))

    # Exactly one `introduced`, and it must sit at the earliest declaring phase.
    for fid, roles in declared.items():
        numbered = {n: r for n, r in roles.items() if isinstance(n, int)}
        if not numbered:
            continue
        introduced = [n for n, r in numbered.items() if r == "introduced"]
        earliest = min(numbered)
        if not introduced:
            failures.append((
                earliest,
                [
                    f"{key}: '{fid}' is declared only as 'extended' and never "
                    "'introduced'. The phase that first builds it must "
                    "declare role 'introduced'."
                ],
            ))
        elif len(introduced) > 1:
            where = ", ".join(str(n) for n in sorted(introduced))
            failures.append((
                min(introduced),
                [
                    f"{key}: '{fid}' is declared 'introduced' in more than one "
                    f"phase (phases {where}). Exactly one phase introduces it."
                ],
            ))
        elif introduced[0] != earliest:
            failures.append((
                earliest,
                [
                    f"{key}: '{fid}' is declared 'introduced' in phase "
                    f"{introduced[0]} but is already declared in earlier phase "
                    f"{earliest}. The earliest phase to build it introduces it."
                ],
            ))
    return failures, declared


def _first_phase(
    declared: dict[str, dict[int | None, str]], fid: str
) -> int | None:
    numbered = [n for n in declared.get(fid, {}) if isinstance(n, int)]
    return min(numbered) if numbered else None


def check_phase_coverage(
    phases: list[dict[str, Any]],
    ai_features: dict[str, Any] | None,
    *,
    feature_specs: dict[str, Any] | None = None,
    revision_version: int | None = None,
) -> tuple[list[tuple[int | None, list[str]]], list[str]]:
    """Check declared coverage and build order over both declaration arrays.

    Returns ``(failures, advisories)``. ``failures`` is retry-triggering and
    uses the same shape as schema validation; ``advisories`` are surfaced to
    the developer but never block.

    Capability-side checks run when the catalog has nodes (over
    ``capabilities[]``); product-side checks run when the spine has features
    and this is not a revision round (over ``features[]``). With neither,
    there is nothing to check.
    """
    if not phases:
        return [], []

    failures: list[tuple[int | None, list[str]]] = []
    advisories: list[str] = []

    # ======================= capability side (AI catalog) ===================
    nodes = _to_phase_nodes(ai_features, revision_version)
    if nodes:
        by_id = {n["id"]: n for n in nodes if n.get("id")}
        name_to_id = {
            n["name"]: n["id"] for n in nodes if n.get("name") and n.get("id")
        }
        cap_failures, cap_declared = _check_declared(
            phases, "capabilities", set(by_id), "the AI features context"
        )
        failures.extend(cap_failures)

        # presence
        missing: list[str] = []
        for fid, node in by_id.items():
            if fid in cap_declared:
                continue
            priority = str(node.get("phase_priority") or "")
            label = node.get("name") or fid
            if priority in ENFORCED_PRIORITIES:
                kind = (
                    "infrastructure"
                    if node.get("kind") == INFRA_KIND
                    else f"'{priority}' capability"
                )
                missing.append(f"{label} ({kind}, id: {fid})")
            else:
                advisories.append(
                    f"'{label}' (priority: {priority or 'unset'}) is not built "
                    "by any phase — deferred."
                )
        if missing:
            failures.append((
                None,
                [
                    "capabilities: these must be built by some phase but no "
                    "phase declares them: " + "; ".join(sorted(missing))
                    + ". Add each to the `capabilities` array of the phase "
                    "that builds it."
                ],
            ))

        # infrastructure ordering (hard)
        for fid, node in by_id.items():
            consumer_phase = _first_phase(cap_declared, fid)
            if consumer_phase is None:
                continue  # undeclared: presence check owns it
            for req_name in node.get("requires") or []:
                req_id = name_to_id.get(req_name) or _slug(str(req_name))
                req_node = by_id.get(req_id)
                if req_node is None or req_node.get("kind") != INFRA_KIND:
                    continue  # feature→feature edges are not order-checked here
                infra_phase = _first_phase(cap_declared, req_id)
                if infra_phase is None:
                    continue  # presence check owns it
                if infra_phase > consumer_phase:
                    consumer_label = node.get("name") or fid
                    infra_label = req_node.get("name") or req_id
                    failures.append((
                        consumer_phase,
                        [
                            f"capabilities: phase {consumer_phase} builds "
                            f"'{consumer_label}', which requires the "
                            f"infrastructure '{infra_label}' — but that "
                            f"substrate is not stood up until phase "
                            f"{infra_phase}. Build infrastructure in the same "
                            "phase as its first consumer, or earlier."
                        ],
                    ))

    # ======================= product side (Brainstormer spine) ==============
    spine = [
        f
        for f in ((feature_specs or {}).get("features") or [])
        if isinstance(f, dict) and f.get("id")
    ]
    if spine and revision_version is None:
        spine_ids = {str(f["id"]) for f in spine}
        prod_failures, prod_declared = _check_declared(
            phases, "features", spine_ids, "the Feature specifications"
        )
        failures.extend(prod_failures)

        excluded = excluded_feature_ids(feature_specs, ai_features)

        # presence with the excluded disposition (D-PH2b)
        missing = []
        for f in spine:
            fid = str(f["id"])
            label = f.get("name") or fid
            if fid in prod_declared:
                if fid in excluded:
                    failures.append((
                        _first_phase(prod_declared, fid),
                        [
                            f"features: '{fid}' is excluded from this plan by "
                            "the developer's Agentifier selection (its AI "
                            "implementation was rejected) but a phase declares "
                            "it. Remove the declaration — to include the "
                            "feature, the developer must revisit the "
                            "Agentifier selection."
                        ],
                    ))
                continue
            if fid in excluded:
                advisories.append(
                    f"'{label}' is excluded from this plan via the Agentifier "
                    "selection (AI implementation rejected). To include it, "
                    "return to Agentifier and modify the AI feature selection."
                )
                continue
            missing.append(f"{label} (id: {fid})")
        if missing:
            failures.append((
                None,
                [
                    "features: these product features must be built by some "
                    "phase but no phase declares them: "
                    + "; ".join(sorted(missing))
                    + ". Add each to the `features` array of the phase that "
                    "builds it."
                ],
            ))

        # product-dependency ordering (D-PH2f — advisory)
        for f in spine:
            fid = str(f["id"])
            if fid in excluded:
                continue
            consumer_phase = _first_phase(prod_declared, fid)
            if consumer_phase is None:
                continue  # presence owns it
            for dep in f.get("dependencies") or []:
                dep_id = str(dep).strip()
                if not dep_id or dep_id in excluded:
                    continue
                producer_phase = _first_phase(prod_declared, dep_id)
                if producer_phase is None:
                    continue
                if producer_phase > consumer_phase:
                    advisories.append(
                        f"Build order: '{fid}' is first built in phase "
                        f"{consumer_phase} but its dependency '{dep_id}' is "
                        f"not built until phase {producer_phase} — the spine "
                        "says a producer is built no later than its consumer."
                    )

    return failures, advisories