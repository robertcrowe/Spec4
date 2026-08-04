"""Feature Speccer — Brainstormer's post-vision feature-spec pass (Lever 2).

Produces ``feature_specs.json``: a per-feature behavioral spec for every
``key_features_mvp`` feature, keyed by the stable id Lever 1 stamps, plus a
project-level ``nfr_goals`` block (D-BS7=A). The behavioral field set is the
technology-agnostic subset of the Agentifier spec, using the same field names
(``purpose`` / ``invocation`` / ``inputs`` / ``outputs`` / ``success_criteria``
/ ``failure_modes`` / ``references``) so a downstream consumer round can render
these through the shared ``feature_specs.render_feature_block``; ``dependencies``
and ``entities`` are the two additions nothing at vision level carries today.

Shape (D-BS3): a deterministic scaffold is the floor, one blocking generative
call enriches the judgment fields on top of it, and a deterministic pass
normalises the model's output and prunes the dependency graph to a DAG. If the
model call fails or returns nothing usable, the scaffold is returned unchanged,
so vision completion never breaks.
"""

from __future__ import annotations

import re
from typing import Any

from spec4 import llm
from spec4.agents._utils import _extract_json_block, slug

FEATURE_SPECS_VERSION = 1

# Behavioral fields the generative pass fills, aligned with the Spec Drafter /
# render_feature_block field names. `id`/`name` stay code-owned.
_LIST_FIELDS = ("inputs", "success_criteria", "failure_modes", "dependencies", "entities")


# ---------------------------------------------------------------------------
# Vision → feature list
# ---------------------------------------------------------------------------


def _vision_features(vision: dict[str, Any]) -> list[tuple[str, str]]:
    """Ordered ``(name, description)`` for each ``key_features_mvp`` entry.

    Mirrors ``brainstormer._feature_names``' container lookup and the entry
    shapes it handles (canonical ``{Name: {...}}``, flat ``{name, description}``,
    bare string). Returns ``[]`` when no feature list is present.
    """
    if not isinstance(vision, dict):
        return []
    vs = vision.get("vision_statement")
    if not isinstance(vs, dict):
        return []
    inner = vs.get("vision")
    kf = inner.get("key_features_mvp") if isinstance(inner, dict) else None
    if kf is None:
        kf = vs.get("key_features_mvp")
    if not isinstance(kf, list):
        return []
    out: list[tuple[str, str]] = []
    for item in kf:
        if isinstance(item, str):
            out.append((item, ""))
        elif isinstance(item, dict) and item:
            if "name" in item and "description" in item:
                out.append((str(item["name"]), str(item.get("description", ""))))
            else:
                name = next(iter(item))
                val = item[name]
                desc = val.get("description", "") if isinstance(val, dict) else ""
                out.append((str(name), str(desc)))
    return out


def _scaffold_feature(name: str, description: str) -> dict[str, Any]:
    """Deterministic per-feature skeleton — the floor the generative pass fills.

    ``id`` and ``name`` are code-owned; ``purpose`` seeds from the vision's
    feature description. The remaining behavioral fields are present but empty so
    the schema shape is stable whether or not the generative pass runs.
    """
    return {
        "id": slug(name),
        "name": name,
        "purpose": description,
        "invocation": {},
        "inputs": [],
        "outputs": {},
        "success_criteria": [],
        "failure_modes": [],
        "dependencies": [],
        "entities": [],
        "references": [],
    }


# ---------------------------------------------------------------------------
# Generative pass — prompt
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = """\
You are Feature Speccer, embedded in Spec4's Brainstormer. Given a confirmed
project vision and its list of MVP features, you produce a concise BEHAVIORAL
spec for each feature — what it does and how you would know it works — plus a
small set of project-level quality goals.

You describe BEHAVIOR and GUARANTEES, never implementation. In NO field —
including input types, descriptions, mitigations, success criteria, and
nfr_goals — may you name a language, framework, library, database, backend,
server, API, file format, or UI control, nor any storage, persistence, caching,
session, or deployment mechanism. In particular, never say HOW data is stored or
kept (no "local storage", "cookies", "cache", "database", "backend", "account"),
never name a UI control (no "dropdown", "autocomplete", "button"), and never
prescribe an operational mechanism (no "checksum", "version number", "code
deployment", "redeployment", "restart", "downtime"). State the guarantee, not
the mechanism:
- NOT "persisted in local storage or a backend" -> "persists across sessions"
- NOT "use a dropdown to prevent typos" -> "only a valid network station can be
  chosen"
- NOT "implement a checksum to detect corruption" -> "a stale or corrupted fare
  table can be detected"
- NOT "updated without redeployment, restart, or downtime" -> "can be updated
  while the app keeps running, without interrupting users"
How something is stored, cached, validated, presented, or deployed is decided by
later agents. Stay at the level of what the user experiences and what each
feature must guarantee.

For EACH feature you are given (identified by its id), produce:
- purpose: one or two sentences on what the feature does and why it exists.
- invocation.trigger: what causes the feature to run (a user action, a schedule,
  or another feature's output).
- inputs: the information the feature consumes. Each has name, type (a
  plain-language kind such as "text", "image", "list of items" — NOT a
  programming type), description, and required (true/false).
- outputs: what the feature produces, as {primary, format, schema_notes} in
  plain language.
- success_criteria: observable signals that the feature is working correctly.
- failure_modes: ways it can go wrong. Each has mode, likelihood
  ("low"/"medium"/"high"), and mitigation.
- dependencies: the ids of OTHER features in the provided list that must exist
  first for this one to work (build order). This MUST match the data flow you
  describe elsewhere in this feature: if this feature's trigger fires on, or its
  inputs consume, another feature's output, then this feature depends on that
  feature — the consumer depends on the producer, never the reverse. (Example: if
  feature B's trigger is "A produces a result", or B's inputs include A's output,
  then B depends on A, and A does not depend on B.) Use only ids from the list,
  never a feature's own id, and never create a cycle. Omit when the feature
  depends on nothing.
- entities: the core domain nouns this feature reads or writes (e.g. "User",
  "Order", "Recipe"), shared across features where they overlap.

Also produce nfr_goals: a short list of project-level non-functional goals as
technology-agnostic targets (e.g. "sub-second search results", "works offline",
"supports thousands of concurrent users"). The mechanism rule above applies here
too — state each goal as an outcome, never by naming the mechanism it avoids
(NOT "updates without redeployment or downtime" -> "the content library can be
updated live while the app keeps running"). Infer only what the vision genuinely
implies; an empty list is correct when nothing is implied.

Output rules:
1. Output ONLY a single ```json ... ``` fenced block — no prose before or after.
2. Include every feature id you were given, exactly once, under "features".
3. Never invent a feature or id that was not provided; use the exact id strings.

Schema:

```json
{
  "features": [
    {
      "id": "<provided id>",
      "purpose": "...",
      "invocation": {"trigger": "..."},
      "inputs": [
        {"name": "...", "type": "...", "description": "...", "required": true}
      ],
      "outputs": {"primary": "...", "format": "...", "schema_notes": "..."},
      "success_criteria": ["..."],
      "failure_modes": [
        {"mode": "...", "likelihood": "low", "mitigation": "..."}
      ],
      "dependencies": ["<other id>"],
      "entities": ["..."]
    }
  ],
  "nfr_goals": ["..."]
}
```
"""


def _vision_context(vision: dict[str, Any]) -> dict[str, Any]:
    vs = vision.get("vision_statement") if isinstance(vision, dict) else None
    vs = vs if isinstance(vs, dict) else {}
    inner = vs.get("vision")
    v = inner if isinstance(inner, dict) else {}
    return {
        "name": str(vs.get("name", "") or ""),
        "purpose": str(v.get("purpose", "") if isinstance(inner, dict) else inner or ""),
        "ui_surface": str(v.get("ui_surface", "") or ""),
        "audience": [str(a) for a in v.get("target_audience", []) if a],
    }


def _build_user_content(vision: dict[str, Any], scaffold: list[dict[str, Any]]) -> str:
    ctx = _vision_context(vision)
    lines = [f"Project: {ctx['name']}"]
    if ctx["purpose"]:
        lines.append(f"Purpose: {ctx['purpose']}")
    if ctx["ui_surface"]:
        lines.append(f"UI surface: {ctx['ui_surface']}")
    if ctx["audience"]:
        lines.append(f"Target audience: {'; '.join(ctx['audience'])}")
    lines.append("")
    lines.append("MVP features to spec (use these exact ids):")
    for feat in scaffold:
        lines.append(
            f"- id: {feat['id']} | name: {feat['name']} | "
            f"description: {feat.get('purpose', '')}"
        )
    lines.append("")
    lines.append(
        "Produce the behavioral spec for every feature id above, plus nfr_goals."
    )
    return "\n".join(lines)


def _response_text(response: Any) -> str:
    try:
        return response.choices[0].message.content or ""
    except (AttributeError, IndexError, TypeError):
        return ""


def _generate(
    vision: dict[str, Any], scaffold: list[dict[str, Any]], llm_config: dict[str, Any]
) -> dict[str, Any] | None:
    """One blocking generative call; returns the parsed JSON dict or None."""
    response = llm.complete(
        llm_config=llm_config,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_content(vision, scaffold)},
        ],
        agent_name="feature_speccer",
    )
    return _extract_json_block(_response_text(response))


# ---------------------------------------------------------------------------
# Deterministic normalisation
# ---------------------------------------------------------------------------


def _coerce_inputs(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return out
    for item in value:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "name": str(item.get("name", "") or ""),
                "type": str(item.get("type", "") or ""),
                "description": str(item.get("description", "") or ""),
                "required": bool(item.get("required", False)),
            }
        )
    return out


def _coerce_outputs(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out = {
        k: str(value.get(k, "") or "")
        for k in ("primary", "format", "schema_notes")
        if value.get(k)
    }
    return out


def _coerce_failure_modes(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return out
    for item in value:
        if not isinstance(item, dict):
            continue
        mode = str(item.get("mode", "") or "")
        if not mode:
            continue
        out.append(
            {
                "mode": mode,
                "likelihood": str(item.get("likelihood", "") or ""),
                "mitigation": str(item.get("mitigation", "") or ""),
            }
        )
    return out


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x) for x in value if isinstance(x, (str, int, float)) and str(x)]


def _coerce_invocation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    trigger = str(value.get("trigger", "") or "")
    return {"trigger": trigger} if trigger else {}


def _merge(
    scaffold: list[dict[str, Any]], enriched: Any
) -> list[dict[str, Any]]:
    """Overlay the model's enriched fields onto the code-owned scaffold, by id.

    id/name stay code-owned; every judgment field is taken from the model when
    present and coerced to its canonical shape, else left at the scaffold value.
    Enriched entries whose id is not in the scaffold (hallucinated features) are
    ignored — the scaffold defines the feature set.
    """
    by_id: dict[str, dict[str, Any]] = {}
    if isinstance(enriched, list):
        for item in enriched:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                by_id[item["id"]] = item

    merged: list[dict[str, Any]] = []
    for feat in scaffold:
        e = by_id.get(feat["id"])
        if not e:
            merged.append(feat)
            continue
        out = dict(feat)
        purpose = str(e.get("purpose", "") or "")
        if purpose:
            out["purpose"] = purpose
        out["invocation"] = _coerce_invocation(e.get("invocation"))
        out["inputs"] = _coerce_inputs(e.get("inputs"))
        out["outputs"] = _coerce_outputs(e.get("outputs"))
        out["success_criteria"] = _coerce_str_list(e.get("success_criteria"))
        out["failure_modes"] = _coerce_failure_modes(e.get("failure_modes"))
        out["dependencies"] = _coerce_str_list(e.get("dependencies"))
        out["entities"] = _coerce_str_list(e.get("entities"))
        merged.append(out)
    return merged


def _validate_dependencies(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prune ``dependencies`` to a DAG over known feature ids, deterministically.

    Drops self-edges and edges to unknown ids (dangling), then removes back-edges
    via a DFS in vision order so no cycle survives. Feature order is fixed, so the
    pruning is deterministic.
    """
    ids = [f["id"] for f in features]
    id_set = set(ids)
    dep_map: dict[str, list[str]] = {}
    for f in features:
        seen: list[str] = []
        for d in f.get("dependencies", []):
            if isinstance(d, str) and d in id_set and d != f["id"] and d not in seen:
                seen.append(d)
        dep_map[f["id"]] = seen

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {fid: WHITE for fid in ids}

    def dfs(u: str) -> None:
        color[u] = GRAY
        kept: list[str] = []
        for v in dep_map[u]:
            if color[v] == GRAY:
                # back-edge → would close a cycle; drop it
                continue
            if color[v] == WHITE:
                dfs(v)
            kept.append(v)
        dep_map[u] = kept
        color[u] = BLACK

    for fid in ids:
        if color[fid] == WHITE:
            dfs(fid)

    for f in features:
        f["dependencies"] = dep_map[f["id"]]
    return features


def _reconcile_dependencies(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Correct dependency edges that contradict the trigger's data flow (D-FS).

    If feature F's ``invocation.trigger`` names another feature G's id, F is
    triggered by G's output, so F depends on G (consumer depends on producer).
    When the declared edges contradict that — F's trigger names G but F does not
    already depend on G — the trigger is treated as authoritative (D-FS2=B): G is
    added to F's dependencies and the contradicting reverse edge (G depending on
    F) is removed, unless G's trigger likewise names F (a mutual reference, left
    for the DAG pruner to resolve). Already-consistent graphs are left untouched.
    Only the trigger is consulted (D-FS1=A); ids are matched whole-word,
    case-insensitively, excluding a feature's own id (D-FS3).
    """
    ids = [f["id"] for f in features]
    by_id = {f["id"]: f for f in features}

    # implied[F.id] = producer ids named in F's trigger, in vision order.
    implied: dict[str, list[str]] = {}
    for f in features:
        inv = f.get("invocation")
        trigger = str(inv.get("trigger", "") or "") if isinstance(inv, dict) else ""
        named: list[str] = []
        if trigger:
            for gid in ids:
                if gid == f["id"]:
                    continue
                if re.search(rf"\b{re.escape(gid)}\b", trigger, re.IGNORECASE):
                    named.append(gid)
        implied[f["id"]] = named

    for f in features:
        fid = f["id"]
        deps = f.get("dependencies")
        if not isinstance(deps, list):
            deps = []
            f["dependencies"] = deps
        for gid in implied[fid]:
            if gid in deps:
                continue  # already consistent — leave untouched
            deps.append(gid)  # trigger says F depends on G; add the missing edge
            if fid not in implied.get(gid, []):
                # remove the contradicting reverse edge G -> F (unless mutual)
                g_deps = by_id[gid].get("dependencies")
                if isinstance(g_deps, list) and fid in g_deps:
                    g_deps.remove(fid)
    return features


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def build_feature_specs(
    vision: dict[str, Any], llm_config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build ``feature_specs`` from a completed vision.

    Emits a deterministic scaffold for every ``key_features_mvp`` feature (keyed
    by id, in vision order) plus a project-level ``nfr_goals`` block. When
    ``llm_config`` is supplied and there are features, one blocking generative
    call enriches the scaffold; its output is normalised and its dependency graph
    pruned to a DAG. Any failure falls back to the scaffold — vision completion
    never breaks on this pass.
    """
    scaffold = [_scaffold_feature(name, desc) for name, desc in _vision_features(vision)]
    result: dict[str, Any] = {
        "version": FEATURE_SPECS_VERSION,
        "features": scaffold,
        "nfr_goals": [],
    }
    if not llm_config or not scaffold:
        return result

    try:
        parsed = _generate(vision, scaffold, llm_config)
    except Exception:
        parsed = None
    if not isinstance(parsed, dict):
        return result

    result["features"] = _validate_dependencies(
        _reconcile_dependencies(_merge(scaffold, parsed.get("features")))
    )
    result["nfr_goals"] = _coerce_str_list(parsed.get("nfr_goals"))
    return result


# ---------------------------------------------------------------------------
# Review render (compact summary for the Brainstormer chat)
# ---------------------------------------------------------------------------


def render_feature_specs(feature_specs: dict[str, Any] | None) -> str:
    """A compact, readable summary of the drafted specs for the review turn.

    The full detail lives in ``feature_specs.json``; the chat shows a digest so
    the user can sanity-check structure. Corrections flow through the vision —
    adjusting a feature there regenerates its spec.
    """
    if not isinstance(feature_specs, dict):
        return ""
    features = feature_specs.get("features") or []
    if not features:
        return ""
    lines = [
        "**Feature specs** (drafted from your vision — these guide the build plan):",
        "",
    ]
    for feat in features:
        if not isinstance(feat, dict):
            continue
        name = feat.get("name") or feat.get("id") or "(unnamed)"
        purpose = str(feat.get("purpose", "") or "").strip()
        head = f"- **{name}**" + (f" — {purpose}" if purpose else "")
        deps = feat.get("dependencies") or []
        if deps:
            dep_names = [_display_name(features, d) for d in deps]
            head += f" _(depends on: {', '.join(dep_names)})_"
        lines.append(head)
    nfr = feature_specs.get("nfr_goals") or []
    if nfr:
        lines.append("")
        lines.append("**Quality goals:** " + "; ".join(str(g) for g in nfr))
    lines.append("")
    lines.append(
        "To change a spec, tell me how the feature should change and I'll update "
        "the vision — the specs regenerate from it."
    )
    return "\n".join(lines)


def _display_name(features: list[Any], feature_id: str) -> str:
    for feat in features:
        if isinstance(feat, dict) and feat.get("id") == feature_id:
            return str(feat.get("name") or feature_id)
    return feature_id
