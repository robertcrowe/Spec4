"""Stack, phase, NFR and design-manifest digests, plus the style renderers.

The counterpart to ``_feature_context``: where that module projects *what* is
being built, this one projects the decisions already made about *how* — the
chosen stack as Deployer and Phaser each need to read it, the phase plan, the
derived NFR goals, and the design manifest a Designer round produced. The
``render_*_style`` helpers are here because the coding-style block is part of
the stack digest rather than a surface of its own.

Split out of ``_utils.py`` in Phase 4a; Phase 4j moved every importer here and
retired the ``_utils`` facade, so this module is now the one place these names
are imported from.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec4.agents._feature_context import slug
from spec4.design_manifest import surface_summary_line
from spec4.stack_routing import (
    ROADMAP_STATUSES,
    derived_nfr_ids,
    stack_signal_entries,
)


def render_references(refs: list[dict[str, str]], lines: list[str]) -> None:
    """Append a **References:** section to lines in-place. No-op if refs is empty."""
    if not refs:
        return
    lines.append("**References:**")
    for ref in refs:
        standard = ref.get("standard", "")
        url = ref.get("url", "")
        lines.append(f"- {standard}: {url}" if url else f"- {standard}")
    lines.append("")


STYLE_LEAF_KEYS = (
    "linter",
    "formatter",
    "type_checker",
    "type_checking",
    "language",
    "indentation",
    "line_length",
    "quotes",
)


def render_one_style(style: dict[str, Any], lines: list[str], indent: str = "") -> None:
    """Append one style block's fields. Shared by the flat and nested shapes."""
    for key in STYLE_LEAF_KEYS:
        if key in style:
            lines.append(f"{indent}- {key.replace('_', ' ').title()}: {style[key]}")
    naming: dict[str, str] = style.get("naming_conventions", {})
    if naming:
        naming_str = ", ".join(f"{k}: {v}" for k, v in naming.items())
        lines.append(f"{indent}- Naming: {naming_str}")
    other_rules: list[str] = style.get("other_rules", [])
    if other_rules:
        lines.append(f"{indent}- Other rules: {'; '.join(other_rules)}")
    patterns: list[str] = style.get("patterns", [])
    if patterns:
        lines.append(f"{indent}- Patterns: {'; '.join(patterns)}")


def render_coding_style(style: dict[str, Any], lines: list[str]) -> None:
    """Append a **Coding Style:** section to lines in-place. No-op if style is empty.

    Handles both shapes the model emits (D-SC23). A single-language project gives a
    flat block; a two-language one nests by tier — ``{"backend": {...}, "frontend":
    {...}}`` or ``{"python": {...}, "typescript": {...}}``. Probing only for flat
    keys printed the heading and nothing else, so a developer who had just
    negotiated linter, formatter, type checker, naming and patterns across two
    turns saw an empty section.
    """
    if not style:
        return
    lines.append("**Coding Style:**")
    if any(k in style for k in (*STYLE_LEAF_KEYS, "naming_conventions", "patterns")):
        render_one_style(style, lines)
    else:
        for tier, sub in style.items():
            label = str(tier).replace("_", " ").title()
            if isinstance(sub, dict):
                lines.append(f"- {label}:")
                render_one_style(sub, lines, indent="  ")
            else:
                lines.append(f"- {label}: {sub}")
    lines.append("")


def phases_for_deployer(phases: list[dict[str, Any]], version: Any) -> str:
    """Deployment-shaped projection of the phase plan for Deployer (D-DE4).

    Deployer previously received phase numbers and titles only, discarding the
    rest of a payload it already held. Two things in that payload are
    deployment-shaped and reach Deployer through no other channel:

    * the **build order**, which is both the sequence a coding agent executes
      (pointing the agent at these files is Deployer's first job, so the paths
      stay) and the order infrastructure has to come up in;
    * each phase's ``tech_stack_spec.configurations`` — the environment
      variables, ports, and config files that phase's code actually reads. Their
      union is the factual basis for the plan's Environment section, which
      otherwise gets derived from a brownfield code review or asked for cold.

    ``configurations`` is projected **verbatim** rather than mined for variable
    names. The prose carries the example values, the local-versus-production
    split, and what each variable is *for*; a name-only extraction would drop all
    three and would have to guess at naming conventions besides. Phases that add
    no new variables still get their line, so silence reads as "nothing new here"
    rather than as an omission.

    Verification text and per-phase dependency lists are deliberately not
    projected. Verification is overwhelmingly the local dev loop (bring compose
    up, curl the health endpoint, run the tests) and the dependency lists are
    package installs the stack spec already owns — neither is a deployment
    decision, and together they cost several times the whole projection above.

    Returns ``""`` when there are no phases, so a project without a phase plan
    contributes nothing rather than an empty heading.
    """
    if not phases:
        return ""

    lines: list[str] = [
        f"**Development phases (from Phaser) — the {len(phases)} phases a coding agent "
        f"will execute, in order. The deployment has to accommodate what these phases "
        f"configure and stand up.**\n"
    ]

    lines.append(f"**Build order** (saved under `.spec4/v{version}/phases/`):")
    for p in phases:
        num = p.get("phase_number")
        title = str(p.get("phase_title") or "").strip()
        lines.append(
            f"- Phase {num}: {title} (`.spec4/v{version}/phases/phase{num}.md`)"
        )
    lines.append("")

    config_lines: list[str] = []
    for p in phases:
        tech: dict[str, Any] = p.get("tech_stack_spec") or {}
        raw = tech.get("configurations")
        if isinstance(raw, list):
            cfg = "; ".join(str(c).strip() for c in raw if str(c).strip())
        else:
            cfg = str(raw or "").strip()
        if cfg:
            config_lines.append(f"- Phase {p.get('phase_number')}: {cfg}")

    if config_lines:
        lines.append(
            "**Per-phase configuration** — the environment variables, ports, and config "
            "files each phase expects, verbatim from its tech stack spec. Their union is "
            "the factual starting point for this plan's Environment section: confirm and "
            "correct them with the developer rather than asking cold, and read a phase "
            "that adds nothing as exactly that."
        )
        lines.extend(config_lines)
        lines.append("")

    return "\n".join(lines)


def stack_for_deployer(stack: dict[str, Any] | None) -> str:
    """Deployment-shaped digest of the stack spec for Deployer (D-DE5).

    Deployer previously received the whole stack as a raw ``json.dumps`` paste —
    tens of thousands of characters in which every deployment decision the stack
    had already made was present but never legible. Measured against three
    drawn plans, most of it never arrived: transport never once reached a plan,
    one of two targets and both auth mechanisms went unmentioned, and the
    substrate to provision was largely missed.

    This replaces the paste with the deployment-shaped view, rendered
    deterministically and verbatim:

    * **targets** — every ``deployment.targets[]`` entry with the fields that
      *are* the Target, Containerization, and Environment sections: kind,
      purpose, language, runtime, hosting, build, distribution, api_contract,
      and ``exposure`` (transport and CORS). ``build`` and ``hosting`` are what
      carry, e.g., the service-worker/PWA and CDN stories;
    * **auth** — every ``security.auth[]`` mechanism with its purpose, what it
      serves, and its ``credentials_env``, which is a source of required
      environment variables independent of the phase configurations;
    * **provisioning** — the persistence stores and ``infrastructure`` entries
      this build stands up, each with its ratified choice and why;
    * **roadmap** — entries carrying ``status: optional``/``deferred``, named so
      they are recorded rather than built.

    Two absences are load-bearing and stated rather than left silent: an absent
    or empty ``security.auth`` means the project has no accounts, and an absent
    ``integrations`` block means no external services. Deployer must not read
    either as an omission and re-ask.

    Providers and ``model_family`` are deliberately not rendered here: provider
    and model deployment is the AI channel's to own, and surfacing it in both
    places would give one decision two owners.

    Returns ``""`` when the stack is absent or empty.
    """
    if not isinstance(stack, dict) or not stack:
        return ""
    inner = stack.get("stack_spec")
    spec = inner if isinstance(inner, dict) else stack

    lines: list[str] = [
        "**Technology stack — deployment signals (from StackAdvisor). This is the "
        "deployment-shaped view of the ratified stack: what to host, how to expose "
        "it, what to provision, and what to keep out of this build. These decisions "
        "are already settled — build on them rather than re-asking.**\n"
    ]

    def _field(entry: dict[str, Any], key: str, label: str) -> str | None:
        val = entry.get(key)
        text = str(val or "").strip()
        return f"  - {label}: {text}" if text else None

    targets = [
        t
        for t in ((spec.get("deployment") or {}).get("targets") or [])
        if isinstance(t, dict)
    ]
    if targets:
        lines.append(
            f"**Deployment targets** — {len(targets)} surface(s) to host. Each is a "
            f"distinct hosting decision; its `exposure` is literal transport and CORS "
            f"configuration:"
        )
        for t in targets:
            name = str(t.get("name") or "target").strip()
            kind = str(t.get("kind") or "").strip()
            purpose = str(t.get("purpose") or "").strip()
            head = f"- `{name}`" + (f" ({kind})" if kind else "")
            lines.append(f"{head} — {purpose}" if purpose else head)
            for key, label in (
                ("language", "language"),
                ("runtime", "runtime"),
                ("hosting", "hosting"),
                ("build", "build"),
                ("distribution", "distribution"),
                ("api_contract", "API contract"),
            ):
                row = _field(t, key, label)
                if row:
                    lines.append(row)
            exposure = t.get("exposure")
            if isinstance(exposure, dict):
                for key, label in (("transport", "transport"), ("cors", "CORS")):
                    row = _field(exposure, key, label)
                    if row:
                        lines.append(row)
        lines.append("")

    security = spec.get("security")
    auth = (
        [a for a in ((security or {}).get("auth") or []) if isinstance(a, dict)]
        if isinstance(security, dict)
        else []
    )
    if auth:
        lines.append(
            f"**Authentication** — {len(auth)} mechanism(s). Their credentials are "
            f"required environment variables and belong in the Environment section:"
        )
        for a in auth:
            mech = str(a.get("mechanism") or a.get("name") or "auth").strip()
            purpose = str(a.get("purpose") or "").strip()
            lines.append(f"- {mech}" + (f" — {purpose}" if purpose else ""))
            serves = [str(s) for s in (a.get("serves_features") or []) if str(s)]
            if serves:
                lines.append(f"  - serves: {', '.join(serves)}")
            creds = [str(c) for c in (a.get("credentials_env") or []) if str(c)]
            if creds:
                lines.append(f"  - credentials (environment): {', '.join(creds)}")
        lines.append("")
    else:
        lines.append(
            "**Authentication** — the stack declares none. This project has no user "
            "accounts: do not provision an identity provider, do not plan auth "
            "secrets, and do not ask the developer to choose one.\n"
        )

    if not (spec.get("integrations") or []):
        lines.append(
            "**External integrations** — the stack declares none. There are no "
            "third-party services to configure credentials or network egress for.\n"
        )

    provision: list[str] = []
    roadmap: list[str] = []
    for section in ("persistence", "infrastructure"):
        block = spec.get(section)
        if not isinstance(block, dict):
            continue
        for key, entry in block.items():
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or key).strip()
            status = str(entry.get("status") or "").strip()
            choice = str(entry.get("choice") or "").strip()
            purpose = str(entry.get("purpose") or "").strip()
            if status in ROADMAP_STATUSES:
                roadmap.append(
                    f"- `{name}` ({section}, {status})"
                    + (f" — {purpose}" if purpose else "")
                )
                continue
            row = f"- `{name}` ({section})" + (f": {choice}" if choice else "")
            if purpose:
                row += f" — {purpose}"
            provision.append(row)
            for key_name, label in (
                ("durability", "durability"),
                ("implementation", "implementation"),
            ):
                extra = _field(entry, key_name, label)
                if extra:
                    provision.append(extra)
            sat = [str(s) for s in (entry.get("satisfies_infra") or []) if str(s)]
            if sat:
                provision.append(f"  - satisfies infrastructure need: {', '.join(sat)}")

    if provision:
        lines.append(
            "**To provision** — the stores and infrastructure this build stands up. "
            "Each choice is ratified; the deployment plan's job is to say how it gets "
            "created and configured, not to re-choose it:"
        )
        lines.extend(provision)
        lines.append("")

    for e in stack_signal_entries(stack):
        entry = e["entry"]
        if str(entry.get("status") or "") not in ROADMAP_STATUSES:
            continue
        if e["section"] in ("persistence", "infrastructure"):
            continue  # already captured above, with its section context
        roadmap.append(f"- `{e['label']}` ({e['section']}, {entry.get('status')})")

    if roadmap:
        lines.append(
            "**Roadmap — recorded, not provisioned.** These carry a non-MVP `status`. "
            "Note them in the plan so they are not lost, but do not build, provision, "
            "or configure them in this deployment:"
        )
        lines.extend(roadmap)
        lines.append("")

    return "\n".join(lines)


def nfr_goals_for_deployer(
    stack: dict[str, Any] | None,
    feature_specs: dict[str, Any] | None,
) -> str:
    """Every project non-functional goal, with its stack claim status (D-DE6).

    The project's ``nfr_goals`` are outcome-phrased statements of what the built
    system must be like — fast, available offline, durable across restarts,
    updatable without interrupting users, confidential between parties. Several
    of those are deployment decisions and nothing else: they are settled by
    region, caching, replica and scaling posture, backup policy, and network
    isolation. Deployer received none of them, and they evaporated between the
    vision and the plan.

    This renders all of them, each marked with whether any stack entry claims to
    satisfy it (``satisfies_nfr``):

    * **claimed** — the claiming entries are named, so the plan can say how that
      component's deployment actually delivers the goal;
    * **unclaimed** — surfaced honestly rather than dropped. An unclaimed goal is
      not a defect: goals satisfied by *features* rather than by stack components
      correctly have no claimer. What must never happen is inventing a claim, so
      an unclaimed goal is marked as unclaimed and left that way.

    Ids follow the shared ``nfr_<slug>`` derivation (D-SC2) via
    ``derived_nfr_ids``, so a goal has the same id here as everywhere else in the
    pipeline. Goal order follows the source list.

    Returns ``""`` when the project declares no goals.
    """
    derived = derived_nfr_ids(feature_specs)
    if not derived:
        return ""

    claimers: dict[str, list[str]] = {}
    if isinstance(stack, dict) and stack:
        for rec in stack_signal_entries(stack):
            for raw in rec["entry"].get("satisfies_nfr") or []:
                nid = str(raw)
                if nid in derived:
                    claimers.setdefault(nid, []).append(rec["label"])

    lines: list[str] = [
        "**Non-functional goals (from the vision).** These state what the built "
        "system has to be like. Some are settled by deployment and nothing else — "
        "where a goal is, the plan is where it gets delivered, so say how. Each "
        "goal below is marked with whether any stack component claims to satisfy "
        "it; a goal no component claims must be left unclaimed rather than given "
        "an invented one.\n"
    ]
    for nid, goal in derived.items():
        lines.append(f'- `{nid}` — "{goal}"')
        named = sorted(set(claimers.get(nid, [])))
        if named:
            lines.append(f"  - claimed by: {', '.join(named)}")
        else:
            lines.append(
                "  - claimed by: no stack component. Do not invent an "
                "infrastructure claim for this goal."
            )
    lines.append("")
    return "\n".join(lines)


def load_design_manifest(design_dir: Path | None) -> dict[str, Any] | None:
    """Read Designer's ``manifest.json`` from ``design_dir``. None when absent.

    Tolerant by design: Designer is optional, and a project that never ran it (or
    ran an older round) simply has no manifest. Unreadable or malformed content is
    treated the same as absent rather than raising into an agent turn.
    """
    if design_dir is None:
        return None
    path = design_dir / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def design_manifest_for_stack(manifest: dict[str, Any] | None) -> str:
    """Render Designer's manifest as a StackAdvisor block (D-SC5c).

    Designer is authoritative about two things a stack must accommodate: the data
    model the UI is built on (entities *with their fields*, where the feature spine
    carries only bare entity names) and the screen structure. Both are surfaced as
    advisory *shape* — never a mechanism mandate. Which store, which schema, which
    router remain StackAdvisor's call, exactly as the feature-spec entity
    vocabulary does (D-SC6).

    Deliberately omits the surface→feature join fields (``implements_feature_ids``,
    ``catalog_surface_id``). StackAdvisor already has a sound feature join, via the
    Brainstormer spine and the AI catalog's serves relation; the manifest's join is
    a second, redundant path that is known to over-attribute (surfaces claiming
    features they do not implement), so importing it would risk corrupting the very
    attribution this round exists to produce. Take the data model, leave the joins.

    The visual mock is not projected here at all: it is the coding agent's
    reference, handed downstream by path, and no stack decision needs its markup.
    Returns ``""`` when the manifest carries nothing usable.
    """
    man = manifest or {}
    entities = [e for e in (man.get("entities") or []) if isinstance(e, dict)]
    surfaces = [s for s in (man.get("surfaces") or []) if isinstance(s, dict)]
    screens = [s for s in (man.get("screens") or []) if isinstance(s, dict)]
    if not (entities or surfaces or screens):
        return ""

    lines: list[str] = [
        "**Design manifest (from Designer) — the structured plan behind the UI. It "
        "is authoritative about the *shape* of what the app stores and how it is "
        "laid out; the mechanism for both remains your decision.**\n"
    ]

    if entities:
        lines.append(
            "**Data model** — the entities the UI is built on, with the fields it "
            "expects. These are the UI's view of the domain, so treat them as the "
            "shape your persistence and validation choices must accommodate, not as "
            "a schema to adopt verbatim:"
        )
        for e in entities:
            name = str(e.get("name") or "").strip()
            if not name:
                continue
            fields = [str(f) for f in (e.get("fields") or []) if str(f).strip()]
            lines.append(
                f"- `{name}`: {', '.join(fields)}" if fields else f"- `{name}`"
            )
        lines.append("")

    if surfaces:
        written: list[str] = []
        read: list[str] = []
        for s in surfaces:
            for ent in s.get("writes") or []:
                if isinstance(ent, str) and ent not in written:
                    written.append(ent)
            for ent in s.get("reads") or []:
                if isinstance(ent, str) and ent not in read:
                    read.append(ent)
        read_only = [e for e in read if e not in written]
        if written or read_only:
            lines.append(
                "**Entity access** — which entities the UI writes versus only reads. "
                "An entity the app writes must survive whatever durability its "
                "feature promises; an entity only ever read may be static, bundled, "
                "or fetched rather than stored:"
            )
            if written:
                lines.append(f"- written: {', '.join(written)}")
            if read_only:
                lines.append(f"- read-only: {', '.join(read_only)}")
            lines.append("")

    if screens:
        ids = [str(s.get("id") or s.get("name") or "") for s in screens]
        ids = [i for i in ids if i]
        nav = (man.get("shared_layout") or {}).get("nav")
        if isinstance(nav, dict):
            nav_desc = str(nav.get("type") or "navigation")
        elif isinstance(nav, str) and nav.strip():
            nav_desc = nav.strip()
        else:
            nav_desc = ""
        tail = f", with `{nav_desc}` navigation" if nav_desc else ""
        lines.append(
            f"**Screens** — the app has {len(ids)} screen(s){tail}: "
            + ", ".join(f"`{i}`" for i in ids)
            + ". Distinct screens the user moves between are a routing and "
            "code-splitting signal; how you route (or whether a library is warranted "
            "at all) is your call."
        )
        lines.append("")

    return "\n".join(lines)


def stack_digest_for_phaser(
    stack: dict[str, Any] | None,
    feature_specs: dict[str, Any] | None = None,
) -> str:
    """Deterministic join-key digest of the stack spec (D-PH1b option A).

    The raw stack JSON stays in the seed as the authoritative approved-
    components list; this digest rides alongside it and makes the join keys
    legible as structure instead of prose-in-a-paste: which stack entries serve
    which product features (``serves_features``) and AI capabilities
    (``serves_capabilities``), which entries claim which non-functional goals
    (``satisfies_nfr``, with unclaimed goals named honestly), which entries are
    roadmap rather than build items (``status``), what each deployment target
    exposes (``exposure``), and the trustworthy negatives — the decisions the
    stack records by *absence*, which must not be re-asked or re-invented.

    Purely an index of the paste: it renders only what the stack carries and
    derives nothing except the ``nfr_<slug>`` ids (from ``feature_specs``, when
    supplied, so orphaned goals can be named). Returns ``""`` when the stack is
    absent or empty.
    """
    if not isinstance(stack, dict) or not stack:
        return ""
    inner = stack.get("stack_spec")
    spec = inner if isinstance(inner, dict) else stack
    entries = stack_signal_entries(stack)

    lines: list[str] = [
        "**Stack signal digest — a deterministic index of the join keys in the "
        "stack spec above. The JSON above remains the authoritative "
        "approved-components list; use this digest to route stack entries to "
        "the right phases.**\n"
    ]

    def backlinks(field: str) -> dict[str, list[str]]:
        links: dict[str, list[str]] = {}
        for e in entries:
            for target in e["entry"].get(field) or []:
                label = e["label"]
                if e["section"] and e["section"] not in label:
                    label = f"{label} ({e['section']})"
                links.setdefault(str(target), []).append(label)
        return links

    by_feature = backlinks("serves_features")
    if by_feature:
        lines.append(
            "Feature → stack backlinks (entries whose `serves_features` names "
            "the feature; make each entry available in the phases that build "
            "its feature):"
        )
        for fid in sorted(by_feature):
            lines.append(f"- `{fid}`: {', '.join(by_feature[fid])}")
        lines.append("")

    by_capability = backlinks("serves_capabilities")
    if by_capability:
        lines.append(
            "AI capability → stack backlinks (entries whose "
            "`serves_capabilities` names the AI catalog node):"
        )
        for cid in sorted(by_capability):
            lines.append(f"- `{cid}`: {', '.join(by_capability[cid])}")
        lines.append("")

    nfr_claims = backlinks("satisfies_nfr")
    derived: dict[str, str] = {}
    for g in (feature_specs or {}).get("nfr_goals") or []:
        if isinstance(g, str) and g.strip():
            derived[f"nfr_{slug(g.strip())}"] = g.strip()
    if nfr_claims or derived:
        lines.append(
            "Non-functional goals — stack claims (`satisfies_nfr`). Cite the "
            "`nfr_<slug>` id in the verification criteria of the phases that "
            "build the claiming entries' features:"
        )
        for nid in sorted(set(nfr_claims) | set(derived)):
            claimers = nfr_claims.get(nid)
            if claimers:
                unknown = (
                    ""
                    if (not derived or nid in derived)
                    else (" [matches no project goal]")
                )
                lines.append(
                    f"- `{nid}`{unknown}: claimed by {', '.join(sorted(set(claimers)))}"
                )
            else:
                lines.append(
                    f"- `{nid}`: UNCLAIMED — no stack entry claims this goal. "
                    "Surface it to the developer as unclaimed; do NOT invent a "
                    "stack claim or an implementation for it."
                )
        lines.append("")

    status_entries = [e for e in entries if e["entry"].get("status")]
    lines.append(
        "Status semantics: entries with `status: optional` or `status: "
        "deferred` are ROADMAP, not build items — never place them in a "
        "phase's dependencies or instructions."
    )
    if status_entries:
        for e in status_entries:
            label = e["label"]
            if e["section"] and e["section"] not in label:
                label = f"{label} ({e['section']})"
            lines.append(f"- {label}: status `{e['entry']['status']}`")
    else:
        lines.append(
            "- No entry carries a status in this stack: every entry is a build item."
        )
    lines.append("")

    targets = (spec.get("deployment") or {}).get("targets") or []
    exposure_lines = []
    for t in targets:
        if not isinstance(t, dict):
            continue
        exp = t.get("exposure")
        if isinstance(exp, dict) and exp:
            detail = "; ".join(f"{k}={v}" for k, v in exp.items())
            exposure_lines.append(f"- {t.get('name') or 'target'}: {detail}")
    if exposure_lines:
        lines.append(
            "Deployment exposure per target (wire these into the phases that "
            "set up each target):"
        )
        lines.extend(exposure_lines)
        lines.append("")

    lines.append(
        "Trustworthy negatives — absence in the stack is a recorded decision, "
        "not an omission; do not re-ask for or re-invent what is absent:"
    )
    security = spec.get("security")
    no_auth = security is None or (
        isinstance(security, dict) and not any(v for v in security.values())
    )
    if no_auth:
        lines.append(
            "- `security` is absent or empty: this app has no accounts or "
            "authentication. Plan no auth, login, or user-management work."
        )
    if not spec.get("integrations"):
        lines.append(
            "- `integrations` is absent or empty: this app uses no external "
            "integrations beyond any AI providers listed above."
        )
    lines.append(
        "- An entry with no `serves_features` is a global staple serving the "
        "whole app, not any single feature."
    )
    lines.append("")

    return "\n".join(lines)


def manifest_for_phaser(manifest: dict[str, Any] | None) -> str:
    """Deterministic projection of Designer's ``manifest.json`` (D-PH1d).

    Surfaces the manifest's structure with its join keys legible: screens
    (audience, purpose, surface membership) and one line per surface carrying
    the two id-space keys — ``implements_feature_ids`` (product-feature ids,
    pinned deterministically by ``enrich_manifest``) and ``catalog_surface_id``
    (AI catalog-node id, on AI surfaces) — plus the entity footprint
    (``reads``/``writes``) and the within-mock ordering hint (``depends_on``,
    advisory). The three surface dispositions are annotated inline: a feature
    surface joins its feature's phases; an empty-``implements`` surface is
    scaffolding (not covered by any feature's phases — it must be planned
    deliberately); a ``screen: null`` surface is internal, non-UI work for its
    feature. ``screen`` may be a string or a list across draws; both render.
    Surface *names and counts* are non-deterministic across mock regens — ids
    and dispositions are the stable join surface, which is why this projection
    leads with them. Returns ``""`` when no manifest or no surfaces.
    """
    surfaces = (manifest or {}).get("surfaces") or []
    if not surfaces:
        return ""

    lines: list[str] = [
        "**UI design manifest (from Designer) — screens and surfaces with "
        "their join keys. `implements` holds product-feature ids; `catalog` "
        "holds the AI catalog-node id realized by the surface.**\n"
    ]

    screens = (manifest or {}).get("screens") or []
    if screens:
        lines.append("Screens:")
        for s in screens:
            if not isinstance(s, dict):
                continue
            sid = s.get("id") or "screen"
            audience = s.get("audience") or "unspecified audience"
            purpose = s.get("purpose") or ""
            members = ", ".join(str(x) for x in (s.get("surfaces") or []))
            line = f"- `{sid}` ({audience}): {purpose}"
            if members:
                line += f" — surfaces: {members}"
            lines.append(line)
        lines.append("")

    lines.append("Surfaces:")
    for s in surfaces:
        if not isinstance(s, dict):
            continue
        lines.append(surface_summary_line(s))
    lines.append("")

    lines.append("How to read the surfaces:")
    lines.append(
        "- Group surfaces by product-feature id when attaching UI work to a "
        "feature's phases — one feature may be realized by several surfaces."
    )
    lines.append(
        "- Several surfaces may realize ONE AI capability (same `catalog` id): "
        "the capability is one unit of work; its surfaces are views onto it."
    )
    lines.append(
        "- A surface with empty `implements` is scaffolding: no feature's "
        "phases cover it, so place it deliberately (a foundational phase, or "
        "defer it) and say which."
    )
    lines.append(
        "- `after` is the mock's within-UI ordering hint (advisory), not a "
        "build-order constraint."
    )
    lines.append("")

    entity_list = (manifest or {}).get("entities") or []
    ent_lines = []
    for ent in entity_list:
        if isinstance(ent, dict) and ent.get("name"):
            fields = ", ".join(str(x) for x in (ent.get("fields") or []))
            ent_lines.append(
                f"- {ent['name']}: {fields}" if fields else f"- {ent['name']}"
            )
    if ent_lines:
        lines.append(
            "Design entities (the design's data vocabulary; align phase data "
            "models with these fields):"
        )
        lines.extend(ent_lines)
        lines.append("")

    return "\n".join(lines)
