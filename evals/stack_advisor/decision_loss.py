"""StackAdvisor decision-loss probe (D-SC46).

Why this exists
---------------
``undeclared_keys.py`` measures *improvisation*: key paths a draw wrote that the
prompt's exemplar never demonstrates. It cannot see *omission*, and the two are
the same event seen from opposite sides. When the model has a decision and no slot
for it, it can invent a key or it can drop the content — and ``undeclared_keys``
scores the first and is blind to the second.

Two live draws on tip ``30f417d`` proved this is not theoretical. Same model, same
conversation shape, same content class, opposite fates:

===================================  ==============  ==============
                                     Threadline      Ragmeister
===================================  ==============  ==============
``undeclared_keys``                  0 / 80          6 / 88
conditionality ("optional for MVP")  dropped         invented ``note`` x4
model family (named in prose both)   dropped         invented ``model_family``
``integrations`` after Topic 4 ran   absent          absent
===================================  ==============  ==============

Threadline's zero was the *drop* branch, and the probe printed "no invented keys —
the schema covered every decision made". That sentence was false. This probe exists
to make the drop branch visible.

What this probe is, honestly
----------------------------
A **regression** instrument, not a discovery one. Every loss it detects was found
first by reading the transcript; a deterministic checker cannot find the next one,
only confirm the known ones stop recurring once D-SC48/D-SC49/D-SC53/D-SC54 land.
D-SC46 ruled against an LLM judge (option (c)) for good reasons — cost, and round 3's
finding that draw-to-draw variance swamps most signals — so the ceiling here is real
and is not worked around. Read it as "did the known loss recur", nothing more.

Two checks
----------
1. **Topic -> block presence.** Each of the eight topics owns a block. A topic that
   ran in the conversation and produced no block is a loss. Both draws lost
   ``integrations`` this way, and both narrated the loss as correctness ("No
   integrations block needed") — the model reads an absent block as the encoding of
   a negative decision, which is exactly what D-SC54 denies.

2. **Conditionality.** Scan the transcript for the deferral vocabulary and check it
   against the presence of a conditionality field on the entries. Before D-SC48
   there is no such field, so this reports the whole surface as lost; after, it
   reports coverage. Ragmeister said "Optional performance optimization; not
   required for MVP" of Redis and had to invent ``note`` to say it; Threadline said
   "optional for MVP" of Redis and shipped ``cache_store`` with collections, TTLs
   and ``serves_features`` — every marker of an approved, required store.

Usage:
    cd evals/stack_advisor && python3 decision_loss.py <draw_dir>
    cd evals/stack_advisor && python3 decision_loss.py            # fixtures

``<draw_dir>`` holds ``stack.json`` and, optionally, the transcript as
``transcript.md`` / ``transcript.txt``. Without a transcript, check 2 is skipped
rather than reported as clean — an unrun check is not a pass.

Measurement tooling only — never wired into the pipeline.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

_INFRA_KIND = "infrastructure"

# Topic -> (block path, gate). The eight topics of the current prompt, in order,
# after D-SC28 inserted External integrations at 4 and renumbered.
#
# The gate says when an absent block is a LOSS rather than a decision:
#   "always"   — the topic produces a block on every project; absence is loss.
#   "ai"       — AI-gated; absent is legitimate on a no-AI app (providers, infra).
#   "negative" — absence is itself a valid recorded decision. `integrations` is the
#                case FareBox exposed: a project that genuinely calls no external
#                service correctly emits no block, and Topic 4's own prose tells it
#                to ("add no `integrations` block and say so"). D-SC54 was shelved
#                on exactly this ground -- an absent `integrations` block is a real
#                negative the probe cannot distinguish from a dropped one, so
#                flagging it as loss fires on correct behaviour (D-SC35's rule).
_TOPIC_BLOCKS: list[tuple[str, str, str]] = [
    ("1 Language(s)", "languages", "always"),
    ("2 Deployment", "deployment", "always"),
    ("3 Provider/model", "providers", "ai"),
    ("4 External integrations", "integrations", "negative"),
    ("5 Libraries", "libraries", "always"),
    ("6 Data and persistence", "persistence", "always"),
    ("7 Infrastructure", "infrastructure", "ai"),
    ("8 Coding style", "coding_style", "always"),
]

# Blocks that are not a topic but are part of the contract.
_OTHER_BLOCKS = ("description", "project_structure", "ai_conventions",
                 "additional_decisions", "references")

# The vocabulary the model reaches for when an entry is not unconditionally in the
# MVP. Drawn from the two live draws rather than imagined: every phrase below
# appears verbatim in a Threadline or Ragmeister transcript.
_DEFERRAL_PATTERNS = (
    r"\boptional\b",
    r"\bnot required for MVP\b",
    r"\bnot strictly required\b",
    r"\bskip for now\b",
    r"\badd later\b",
    r"\badd (?:it )?(?:once|when|if)\b",
    r"\bconsider later\b",
    r"\bnot essential for MVP\b",
    r"\bnot recommended for MVP\b",
    r"\bstart with\b.{0,40}\badd\b",
    r"\bpost-launch\b",
    r"\bnice-to-have\b",
    r"\boverkill for MVP\b",
)

# Where D-SC48 puts `status`. The four sites Ragmeister invented `note` in --
# the invention sites are the specification of where the field is needed.
_STATUS_SITES = ("libraries", "providers", "persistence")


def _stack_spec(stack: dict[str, Any]) -> dict[str, Any]:
    return stack.get("stack_spec") or stack.get("stack") or stack


def _has_ai(catalog: dict[str, Any] | None) -> bool:
    """Does this project have any non-infra AI catalog node?

    AI-gated topics legitimately emit nothing on a no-AI app, so an absent
    `providers` block is only a loss when the catalog has something to serve.
    """
    for node in ((catalog or {}).get("ai_features") or []):
        if isinstance(node, dict) and node.get("kind") != _INFRA_KIND:
            return True
    return False


def _block_state(ss: dict[str, Any], key: str) -> str:
    if key not in ss:
        return "absent"
    val = ss[key]
    if val is None:
        return "null"
    if isinstance(val, (list, dict, str)) and len(val) == 0:
        return "empty"
    return "present"


def _status_fields(ss: dict[str, Any]) -> list[str]:
    """Every path carrying a conditionality field, wherever it lives.

    Walks the document rather than the declared sites: D-SC48 has not landed yet,
    and when it does the placement should be *measured*, not assumed. Also counts
    `note`, because on Ragmeister that is where the conditionality actually went --
    a probe that only looked for `status` would score that draw as total loss and
    miss that the model preserved the content and lacked a slot.
    """
    out: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for field in ("status", "note"):
                if isinstance(node.get(field), str) and node[field].strip():
                    out.append(f"{path or '?'}.{field}")
            for key, val in node.items():
                walk(val, f"{path}.{key}" if path else str(key))
        elif isinstance(node, list):
            for i, val in enumerate(node):
                walk(val, f"{path}[{i}]")

    walk(ss, "")
    return out


def _deferral_hits(transcript: str | None) -> list[dict[str, str]]:
    if not transcript:
        return []
    hits: list[dict[str, str]] = []
    for line in transcript.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for pat in _DEFERRAL_PATTERNS:
            if re.search(pat, stripped, flags=re.IGNORECASE):
                hits.append({
                    "pattern": pat,
                    "line": stripped[:120],
                })
                break
    return hits


def measure(
    stack: dict[str, Any],
    catalog: dict[str, Any] | None = None,
    transcript: str | None = None,
) -> dict[str, Any]:
    ss = _stack_spec(stack)
    has_ai = _has_ai(catalog) if catalog is not None else None

    topics: list[dict[str, Any]] = []
    lost: list[str] = []
    for label, key, gate in _TOPIC_BLOCKS:
        state = _block_state(ss, key)
        # An absent block is NOT a loss when the topic is AI-gated on a no-AI app,
        # or when absence is itself a valid recorded decision (`integrations`).
        # `negative` is unconditional: the probe reads only `stack.json` and cannot
        # tell "no external service exists" from "an integration was dropped", and
        # D-SC54 was shelved precisely because that negative is legitimate. Flagging
        # it would fire on correct behaviour.
        ai_gated = gate == "ai"
        gated_off = bool(ai_gated and has_ai is False)
        legally_absent = gated_off or gate == "negative"
        topics.append({
            "topic": label,
            "block": key,
            "state": state,
            "ai_gated": ai_gated,
            "legally_absent": legally_absent,
        })
        if state != "present" and not legally_absent:
            lost.append(f"{label} -> {key} ({state})")

    others = {k: _block_state(ss, k) for k in _OTHER_BLOCKS}

    status_paths = _status_fields(ss)
    hits = _deferral_hits(transcript)
    return {
        "topics": topics,
        "topic_blocks_present": f"{len(_TOPIC_BLOCKS) - len(lost)}/{len(_TOPIC_BLOCKS)}",
        "topic_blocks_missing": lost,
        "other_blocks": others,
        "has_ai": has_ai,
        "transcript_seen": transcript is not None,
        "deferral_phrases_in_prose": len(hits),
        "deferral_examples": hits[:8],
        "conditionality_fields_in_json": status_paths,
        "conditionality_recorded": bool(status_paths),
    }


def fixtures() -> dict[str, dict[str, Any]]:
    """Both live shapes, reduced to the smallest thing that reproduces them.

    `dropped` is Threadline: the model had the conditionality in prose and emitted
    nothing. `invented` is Ragmeister: same prose, and a `note` key it had to make
    up. Both must read as loss -- if only `dropped` did, the probe would report
    Ragmeister as clean, which is the exact mistake `undeclared_keys` makes in
    reverse.
    """
    catalog = {"ai_features": [{"id": "summarise", "kind": "feature",
                               "tier": "single_call"}]}
    prose = (
        "Caching (optional for MVP, but recommended)\n"
        "Async Task Queue: not strictly required yet. Skip for now; add if "
        "latency becomes a concern.\n"
        "Playwright: overkill for MVP; add later if needed.\n"
    )
    dropped = {"stack_spec": {
        "languages": [{"name": "Python"}],
        "deployment": {"targets": [{"kind": "rest_api"}]},
        "providers": {"OpenAI": {"capabilities": []}},
        # Topic 4 ran and decided; the block never arrived. Both live draws.
        "libraries": [{"name": "redis-py", "purpose": "cache client"}],
        "persistence": {"cache_store": {"choice": "Redis"}},
        "infrastructure": {"pipeline_runner": {"choice": "LangChain"}},
        "coding_style": {"patterns": [], "documentation": []},
    }}
    invented = {"stack_spec": {
        **dropped["stack_spec"],
        "libraries": [{"name": "Playwright", "purpose": "e2e",
                       "note": "Start with API tests; add e2e once core flows "
                               "stabilize"}],
        "persistence": {"cache": {"choice": "Redis",
                                  "note": "Optional performance optimization; "
                                          "not required for MVP"}},
    }}
    return {
        "dropped_threadline_shape": {"stack": dropped, "catalog": catalog,
                                     "transcript": prose},
        "invented_ragmeister_shape": {"stack": invented, "catalog": catalog,
                                      "transcript": prose},
    }


def _load(draw_dir: Path) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
    stack = json.loads((draw_dir / "stack.json").read_text(encoding="utf-8"))
    cat_path = draw_dir / "ai_features.json"
    cat = (
        json.loads(cat_path.read_text(encoding="utf-8"))
        if cat_path.exists() else None
    )
    transcript = None
    for name in ("transcript.md", "transcript.txt", "transcript"):
        path = draw_dir / name
        if path.exists():
            transcript = path.read_text(encoding="utf-8")
            break
    return stack, cat, transcript


def _report(name: str, m: dict[str, Any]) -> None:
    print(f"\n[{name}]  topic blocks present: {m['topic_blocks_present']}"
          f"   has_ai={m['has_ai']}")
    for t in m["topics"]:
        mark = "ok " if t["state"] == "present" else (
            "n/a" if t["legally_absent"] else "***"
        )
        gate = "  (AI-gated)" if t["ai_gated"] else ""
        print(f"    {mark} {t['topic']:26s} -> {t['block']:16s} {t['state']}{gate}")
    if m["topic_blocks_missing"]:
        print("  LOST — a topic ran and produced no block:")
        for x in m["topic_blocks_missing"]:
            print(f"      - {x}")
    print("  other blocks: "
          + ", ".join(f"{k}={v}" for k, v in m["other_blocks"].items()))
    print("  --- conditionality ---")
    if not m["transcript_seen"]:
        # An unrun check is not a pass. Say so rather than print a clean line.
        print("  transcript not supplied — conditionality NOT CHECKED")
        return
    print(f"  deferral phrases in prose: {m['deferral_phrases_in_prose']}")
    for h in m["deferral_examples"]:
        print(f"      · {h['line']}")
    paths = m["conditionality_fields_in_json"]
    print(f"  conditionality fields in JSON: {paths or '(none)'}")
    if m["deferral_phrases_in_prose"] and not paths:
        print("  LOST — the conversation deferred entries and the JSON records "
              "no conditionality anywhere")
    elif m["deferral_phrases_in_prose"] and paths:
        print("  conditionality survived into the JSON (check the placement is a "
              "slot, not an invented `note`)")


def main() -> None:
    if len(sys.argv) > 1:
        draw = Path(sys.argv[1])
        stack, cat, transcript = _load(draw)
        _report(draw.name, measure(stack, cat, transcript))
        return
    for name, fx in fixtures().items():
        _report(name, measure(fx["stack"], fx.get("catalog"),
                              fx.get("transcript")))


if __name__ == "__main__":
    main()