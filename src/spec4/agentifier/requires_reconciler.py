"""Assembly-time ``requires``-direction reconciliation (D-RC series).

The Linker sets ``requires`` direction before the Spec Drafter runs, deciding
from Scout's one-line ``rough_description`` alone, so edges sometimes encode
the wrong direction for the graph's consumers. On iterative-refinement
products, data flows *both* ways between a builder and its analyzers — the
analyzer consumes the artifact on the **build path**, the builder consumes the
analyzer's recommendations on the **revision path**. ``requires`` is a DAG and
can hold only one direction; its consumers (panel closure, Phaser)
semantically need the build path. An *inversion* is an edge encoding the
revision path instead.

This module holds the deterministic signal core calibrated by the D-RI probe
series (``evals/phaser/requires_inversion.py``, which imports it back — single
source of truth, D-RC4/D-RC5) plus the reconciler entry point invoked from the
Agentifier assembly pass (D-RC6).

Signal doctrine (final, D-RI1–D-RI13): for the directed test "X consumes Y's
output" —

- **S1** — Y's node name in X's *trigger* counts only with a completion/output
  qualifier ("after Y completes", "Y produces the ruleset"); a bare trigger
  mention is participation. Y's name in X's input names/descriptions counts
  bare: an input naming a producer is consumption by construction.
- **S1b** — an X input name, stripped of a generic trailing suffix
  (output/result/data/…), of >= 2 chunks (D-RI13), whose chunks are a
  suffix-normalised prefix of Y's name chunks.
- **S2** — X's trigger names a product feature, completion-qualified, whose
  *producer* is Y. Producer via the production map (node outputs vs the
  product feature's declared artifact; unique max, margin >= 2, floor >= 3)
  when feature specs are available; else the selectivity fallback gate
  (feature linked by <= 2 nodes). Membership is not production.
- **S3** — pairwise token overlap, asymmetric: fires only when one direction
  dominates (>= 4 shared tokens and >= 2x the other). Supports the declared
  direction alone; contradicts it **only** when forward overlap is exactly
  zero (D-RI12) — otherwise reverse S3 merely corroborates structural reverse
  evidence or is annotated as an uncorroborated lean (D-RI11).

Classification per edge ``A requires B``: SUPPORTED (fwd only),
SUSPECTED-INVERSION (rev only), CONFLICTING (both), NO-EVIDENCE (neither).
The compressed doctrine: structural evidence (S1/S1b/S2, or zero-counter S3)
carries the burden of contradicting a Linker decision; prose overlap
otherwise only confirms or annotates.

The reconciler (D-RC scope) flips an edge **iff** it classifies
SUSPECTED-INVERSION — structural reverse evidence or zero-counter reverse S3,
with no forward structural evidence. Mutual, lean, and conflicting edges stay
declared. Candidate flips apply in sorted order with a cycle check after each
(D-RC7 A); a flip that would create a cycle is reverted and recorded
(D-RC2 a). Every applied or reverted flip is recorded in the top-level
``reconciliation`` block of ``ai_features.json`` (D-RC1 C), keyed by the
*declared* (pre-flip) edge so the pre-reconciliation graph reconstructs from
records alone.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from spec4.agents._utils import slug

_log = logging.getLogger(__name__)

INFRA_KIND = "infrastructure"

SUPPORTED = "SUPPORTED"
INVERSION = "SUSPECTED-INVERSION"
CONFLICTING = "CONFLICTING"
NO_EVIDENCE = "NO-EVIDENCE"

S3_FLOOR = 4       # minimum shared tokens for a directional S3 (D-RI10)
S3_DOMINANCE = 2   # directional side must be >= this multiple of the other
S2_MAX_LINKED = 2  # fallback gate: vision feature must be this selective
PROD_MARGIN = 2    # production map: unique max must lead runner-up by this
PROD_FLOOR = 3     # production map: minimum overlap to name a producer

_GENERIC_INPUT_SUFFIXES = frozenset(
    {"output", "outputs", "result", "results", "data", "response", "artifact"}
)

_STOPWORDS = frozenset(
    """
    a an and are as at be by for from has have if in into is it its of on or
    that the this to via when which will with within each all any per
    not non
    data report reports output outputs result results user users system
    content information list lists item items feature features generated
    based including provided
    """.split()
)


def _norm_chunk(chunk: str) -> str:
    """Light suffix normalisation for chunk comparison (S1b, sub-decision).

    Strips trailing "ing" (len > 5) then trailing "s" (len > 3) so
    "modeling" meets "model" and "assumptions" meets "assumption". Not
    stemming; deliberately minimal.
    """
    if len(chunk) > 5 and chunk.endswith("ing"):
        chunk = chunk[:-3]
    if len(chunk) > 3 and chunk.endswith("s"):
        chunk = chunk[:-1]
    return chunk


def _tokens(text: str) -> set[str]:
    """Lowercased content tokens: len >= 3, stopworded, suffix-normalised."""
    out: set[str] = set()
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        if len(tok) < 3 or tok in _STOPWORDS:
            continue
        out.add(_norm_chunk(tok))
    return out


def _chunks(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _name_pattern(name: str) -> re.Pattern[str] | None:
    chunks = re.findall(r"[a-z0-9]+", name.lower())
    if not chunks:
        return None
    body = r"[^a-z0-9]*".join(re.escape(c) for c in chunks)
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])")


def name_matches(name: str, text: str) -> bool:
    """Word-boundary, punctuation-tolerant match of ``name`` in ``text``.

    Deliberately blunt: alphanumeric chunks of the name must appear in order,
    separated only by non-alphanumerics ("React Hook Form" matches
    "react-hook-form" but not "@tanstack/react-router"). A lexical join;
    reports built on it must say so.
    """
    pat = _name_pattern(name)
    return bool(pat and pat.search(text.lower()))


_COMPLETION_TAIL = (
    r"\s+(?:completes?|completed|has\s+completed|is\s+complete[d]?|"
    r"finishes|finished|is\s+finished|concludes|is\s+done|"
    r"produces?|produced|has\s+produced|returns?|returned|"
    r"delivers?|delivered|emits?|emitted)"
)


def _names_as_completed(feature_id: str, text: str) -> bool:
    """Whole-word feature mention immediately qualified by a completion verb.

    Distinguishes consumption ("after deck_build completes") from
    participation ("Called by Deck_Build", "as step 4 in the Deck_Build
    pipeline"): a specialist's trigger names the feature it runs *inside*,
    which says nothing about consuming its finished artifact. Also accepts
    the prefix form "completion of <feature>".
    """
    chunks = re.findall(r"[a-z0-9]+", feature_id.lower())
    if not chunks:
        return False
    body = r"[^a-z0-9]*".join(re.escape(c) for c in chunks)
    lowered = text.lower()
    if re.search(rf"(?<![a-z0-9]){body}{_COMPLETION_TAIL}", lowered):
        return True
    return bool(re.search(rf"completion\s+of\s+(?:the\s+)?{body}(?![a-z0-9])", lowered))


def _trigger_text(node: dict[str, Any]) -> str:
    inv = node.get("invocation")
    if isinstance(inv, dict):
        return str(inv.get("trigger") or "")
    return ""


def _input_entries(node: dict[str, Any]) -> list[dict[str, Any]]:
    ins = node.get("inputs")
    if not isinstance(ins, list):
        return []
    return [i for i in ins if isinstance(i, dict)]


def _inputs_text(node: dict[str, Any]) -> str:
    parts: list[str] = []
    for entry in _input_entries(node):
        parts.append(str(entry.get("name") or ""))
        parts.append(str(entry.get("description") or ""))
    return " ".join(p for p in parts if p)


def _outputs_text(node: dict[str, Any]) -> str:
    outs = node.get("outputs")
    if not isinstance(outs, dict):
        return ""
    parts = [str(outs.get("primary") or ""), str(outs.get("schema_notes") or "")]
    return " ".join(p for p in parts if p)


def _stem_prefix_match(input_name: str, producer_name: str) -> bool:
    """S1b: input-name stem is a chunk-prefix of the producer name.

    D-RI13: the stem must be >= 2 chunks — single-chunk stems ("question"
    matching any question_* node) are coincidence-prone by construction.
    """
    stem = _chunks(input_name)
    while stem and stem[-1] in _GENERIC_INPUT_SUFFIXES:
        stem = stem[:-1]
    if len(stem) < 2 or sum(len(c) for c in stem) < 6:
        return False
    prod = [_norm_chunk(c) for c in _chunks(producer_name)]
    stem = [_norm_chunk(c) for c in stem]
    return len(stem) <= len(prod) and prod[: len(stem)] == stem


def build_production_map(
    specs: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
) -> dict[str, str] | None:
    """Product-feature id -> producing AI node id, or None without specs.

    A node produces a product feature when it is linked to it and its outputs
    best overlap the feature's declared artifact (outputs.primary+schema_notes)
    — unique max with margin >= PROD_MARGIN over the runner-up and overlap >=
    PROD_FLOOR. Features with no clear unique producer get no entry
    (conservative).
    """
    if not specs:
        return None
    nodes = [n for n in nodes if n.get("kind") != INFRA_KIND]
    prod_map: dict[str, str] = {}
    for f in specs:
        fid = str(f.get("id") or "")
        if not fid:
            continue
        f_out = f.get("outputs") or {}
        f_tokens = _tokens(
            str(f_out.get("primary") or "") + " " + str(f_out.get("schema_notes") or "")
        )
        if not f_tokens:
            continue
        scored: list[tuple[int, str]] = []
        for n in nodes:
            linked = {slug(str(v)) for v in n.get("linked_vision_features") or []}
            if fid not in linked:
                continue
            score = len(_tokens(_outputs_text(n)) & f_tokens)
            scored.append((score, str(n.get("id") or "")))
        scored.sort(reverse=True)
        if not scored or scored[0][0] < PROD_FLOOR:
            continue
        if len(scored) > 1 and scored[0][0] - scored[1][0] < PROD_MARGIN:
            continue
        prod_map[fid] = scored[0][1]
    return prod_map


def directional_signals(
    consumer: dict[str, Any],
    producer: dict[str, Any],
    prod_map: dict[str, str] | None,
    vf_link_counts: dict[str, int],
) -> list[str]:
    """S1/S1b/S2 signals that ``consumer`` consumes ``producer``'s output."""
    signals: list[str] = []
    trigger = _trigger_text(consumer)
    inputs_text = _inputs_text(consumer)
    producer_name = str(producer.get("name") or "")
    producer_id = str(producer.get("id") or "")

    if producer_name:
        # Trigger mentions carry the participation/consumption ambiguity
        # ("Called by Thread_Summarization" vs "after X produces the
        # ruleset") — require a completion/output qualifier, same as S2.
        # Input mentions are consumption by construction and stay bare.
        if trigger and _names_as_completed(producer_name, trigger):
            signals.append(f"S1 trigger awaits '{producer_name}'")
        elif inputs_text and name_matches(producer_name, inputs_text):
            signals.append(f"S1 inputs name '{producer_name}'")
        else:
            for entry in _input_entries(consumer):
                in_name = str(entry.get("name") or "")
                if in_name and _stem_prefix_match(in_name, producer_name):
                    signals.append(f"S1b input stem '{in_name}'")
                    break

    if trigger:
        if prod_map is not None:
            for fid, nid in prod_map.items():
                if nid == producer_id and _names_as_completed(fid, trigger):
                    signals.append(
                        f"S2 trigger awaits completion of produced feature '{fid}'"
                    )
                    break
        else:
            for vf in producer.get("linked_vision_features") or []:
                vf = str(vf)
                if not vf or vf_link_counts.get(slug(vf), 0) > S2_MAX_LINKED:
                    continue
                if _names_as_completed(vf, trigger):
                    signals.append(
                        f"S2 trigger awaits completion of vision feature '{vf}' (selective)"
                    )
                    break

    return signals


def classify_edge(
    consumer: dict[str, Any],
    producer: dict[str, Any],
    prod_map: dict[str, str] | None,
    vf_link_counts: dict[str, int],
) -> dict[str, Any]:
    """Classify one declared edge ``consumer requires producer``.

    Returns ``{"class", "fwd", "rev", "notes"}`` — the per-edge core shared
    by the reconciler and the D-RI probe (which adds draw I/O and reporting
    around it).
    """
    fwd = directional_signals(consumer, producer, prod_map, vf_link_counts)
    rev = directional_signals(producer, consumer, prod_map, vf_link_counts)
    notes: list[str] = []

    shared_fwd = sorted(
        _tokens(_inputs_text(consumer)) & _tokens(_outputs_text(producer))
    )
    shared_rev = sorted(
        _tokens(_inputs_text(producer)) & _tokens(_outputs_text(consumer))
    )
    nf, nr = len(shared_fwd), len(shared_rev)
    if nf >= S3_FLOOR and nf >= S3_DOMINANCE * nr:
        fwd.append(f"S3 dominant overlap {nf} vs {nr}: {shared_fwd}")
    elif nr >= S3_FLOOR and nr >= S3_DOMINANCE * nf:
        # D-RI11: reverse-dominant S3 alone never drives INVERSION —
        # conversation/revision loops make reverse prose flow real
        # (Haggler control: protocol_message IS assistant output).
        # Contradicting a declared edge takes structural evidence.
        # D-RI12 exception: zero forward overlap means the spec pair
        # offers nothing at all for the declared direction — the
        # asymmetric prior loses its footing, and reverse S3 may
        # classify alone (the analyzer-with-no-counter-flow shape).
        if rev:
            rev.append(f"S3 dominant overlap {nr} vs {nf}: {shared_rev}")
        elif nf == 0:
            rev.append(f"S3 reverse with zero counter ({nr} vs 0): {shared_rev}")
        else:
            notes.append(
                f"S3 reverse lean ({nr} vs {nf}) — uncorroborated, not classified"
            )
    elif nf and nr:
        notes.append(f"S3 mutual ({nf} vs {nr}) — both paths flow")
    elif nf or nr:
        notes.append(f"S3 below floor ({nf} vs {nr})")

    if fwd and rev:
        cls = CONFLICTING
    elif fwd:
        cls = SUPPORTED
    elif rev:
        cls = INVERSION
    else:
        cls = NO_EVIDENCE
    return {"class": cls, "fwd": fwd, "rev": rev, "notes": notes}


def _resolve(
    req_name: str,
    name_to_node: dict[str, dict[str, Any]],
    slug_to_node: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Resolve a ``requires`` entry to a node (name first, slug fallback)."""
    return name_to_node.get(req_name) or slug_to_node.get(slug(req_name))


def _has_cycle(features: list[dict[str, Any]]) -> bool:
    """True if the feature->feature ``requires`` graph holds a cycle.

    Unresolvable entries are sinks and cannot participate. Iterative DFS
    (explicit stack) mirroring the Linker's ``_break_requires_cycles`` shape.
    """
    name_to_node = {str(f["name"]): f for f in features if f.get("name")}
    slug_to_node = {str(f["id"]): f for f in features if f.get("id")}
    ids = [str(f.get("id") or "") for f in features]
    white, grey, black = 0, 1, 2
    colour = {i: white for i in ids if i}
    by_id = {str(f.get("id") or ""): f for f in features}

    def edges_of(fid: str) -> list[str]:
        out: list[str] = []
        for req in by_id[fid].get("requires") or []:
            target = _resolve(str(req), name_to_node, slug_to_node)
            if target is not None:
                tid = str(target.get("id") or "")
                if tid and tid != fid:
                    out.append(tid)
        return out

    for start in colour:
        if colour[start] != white:
            continue
        stack: list[tuple[str, int]] = [(start, 0)]
        colour[start] = grey
        while stack:
            node, i = stack[-1]
            targets = edges_of(node)
            if i >= len(targets):
                colour[node] = black
                stack.pop()
                continue
            stack[-1] = (node, i + 1)
            target = targets[i]
            if colour.get(target) == grey:
                return True
            if colour.get(target) == white:
                colour[target] = grey
                stack.append((target, 0))
    return False


def reconcile_requires(
    features: list[dict[str, Any]],
    feature_specs: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Flip ``requires`` edges classified SUSPECTED-INVERSION, in place.

    Runs post-spec-merge on the assembled feature list, before infra
    expansion, so every edge is feature->feature (D-RC6 A). Returns the
    ``reconciliation`` records (D-RC1 C): one per flip attempt, keyed by the
    *declared* (pre-flip) edge —

        {"from": <consumer id>, "to": <producer id>,
         "direction": "flipped" | "reverted-cycle",
         "signals": [<reverse-evidence strings>]}

    Candidate flips apply in sorted ``(from, to)`` order with a cycle check
    after each (D-RC7 A); a flip that creates a cycle under the previously
    applied set is reverted and recorded ``reverted-cycle`` (D-RC2 a).
    Mutual, lean, CONFLICTING, and NO-EVIDENCE edges are never touched.
    """
    nodes = [f for f in features if f.get("kind", "feature") != INFRA_KIND]
    name_to_node = {str(n["name"]): n for n in nodes if n.get("name")}
    slug_to_node = {str(n["id"]): n for n in nodes if n.get("id")}
    specs = [
        f
        for f in ((feature_specs or {}).get("features") or [])
        if isinstance(f, dict)
    ]
    prod_map = build_production_map(specs, nodes)
    vf_link_counts: dict[str, int] = {}
    for n in nodes:
        for vf in n.get("linked_vision_features") or []:
            key = slug(str(vf))
            vf_link_counts[key] = vf_link_counts.get(key, 0) + 1

    candidates: list[tuple[str, str, dict[str, Any], dict[str, Any], str, list[str]]] = []
    for consumer in nodes:
        for req_name in list(consumer.get("requires") or []):
            req_name = str(req_name)
            producer = _resolve(req_name, name_to_node, slug_to_node)
            if producer is None or producer is consumer:
                continue
            if producer.get("kind", "feature") == INFRA_KIND:
                continue
            verdict = classify_edge(consumer, producer, prod_map, vf_link_counts)
            if verdict["class"] != INVERSION:
                continue
            candidates.append((
                str(consumer.get("id") or ""),
                str(producer.get("id") or ""),
                consumer,
                producer,
                req_name,
                list(verdict["rev"]),
            ))

    records: list[dict[str, Any]] = []
    for from_id, to_id, consumer, producer, req_name, signals in sorted(
        candidates, key=lambda c: (c[0], c[1])
    ):
        consumer_reqs = list(consumer.get("requires") or [])
        producer_reqs = list(producer.get("requires") or [])
        consumer["requires"] = [r for r in consumer_reqs if str(r) != req_name]
        already = any(
            _resolve(str(r), name_to_node, slug_to_node) is consumer
            for r in producer["requires"]
        ) if (producer.get("requires")) else False
        producer.setdefault("requires", [])
        if not already:
            producer["requires"] = list(producer["requires"]) + [
                str(consumer.get("name") or "")
            ]
        if _has_cycle(nodes):
            consumer["requires"] = consumer_reqs
            producer["requires"] = producer_reqs
            records.append({
                "from": from_id,
                "to": to_id,
                "direction": "reverted-cycle",
                "signals": signals,
            })
            _log.warning(
                "Reconciler: flip %r -> %r reverted (would create cycle)",
                from_id,
                to_id,
            )
            continue
        records.append({
            "from": from_id,
            "to": to_id,
            "direction": "flipped",
            "signals": signals,
        })
        _log.info("Reconciler: flipped requires edge %r -> %r", from_id, to_id)
    return records
