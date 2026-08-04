"""Layer-2 relevance judge for the Scout confabulation signal (dev tooling).

Classifies each Scout candidate on the *relevance* axis only:

    grounded    — named by a vision feature, OR necessary to deliver a named
                  feature's stated outcome (necessity, not mere enhancement).
    adjacent    — a genuine fit for the vision's stated purpose / audience /
                  domain, but no feature requires it. Useful expansion.
    off_domain  — serves a need the vision's purpose does not imply.

It does NOT rule on membership (is this AI at all?) — that is the Tier Analyst's
deterministic floor, measured separately. Feeding the judge a deterministic
candidate is out of scope; membership is assumed handled upstream.

This is development / evaluation tooling. It does NOT run in the Agentifier
pipeline. The system prompt and parser are deterministic and unit-tested; the
``judge_*`` runners make real LLM calls (no temperature is pinned, so judge
models that reject the parameter run cleanly) and are exercised by the
calibration harness.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from spec4.llm import complete

LABELS = ("grounded", "adjacent", "off_domain")
VARIANTS = ("drop_domain", "audience_goal")

# --- shared blocks (identical across variants) -------------------------------

_INTRO = """\
You are the Relevance Judge. You are given a project vision and ONE candidate AI
feature that another system proposed for that vision. Your only job is to decide
how the candidate relates to THIS vision — nothing else.

Assume the candidate is already a genuine AI feature. Do NOT judge whether it
needs an LLM, whether it is a good idea, or how it would be built. Judge only
relevance to the vision in front of you."""

_GROUNDED = """\
1. grounded — the candidate is named by one of the vision's features, OR it is
   NECESSARY to deliver a named feature's stated outcome. Necessity test: would a
   stated feature be unable to produce its described result without this
   candidate? If the candidate merely improves, enriches, or extends a feature
   that already works without it, it is NOT grounded — it only enhances.
   To claim grounded you must cite the specific feature (or explicit goal) it
   serves."""

_SKEPTICAL = """\
Be skeptical and literal. Judge against what the vision actually STATES, not what
products in this space usually do. "Apps like this often have X" is never grounds
for grounded or adjacent.

Set "borderline": true whenever the adjacent-vs-off_domain decision is genuinely
close. (Grounded decisions are not borderline.)"""

# --- variant A: drop_domain --------------------------------------------------
# Adjacency rides on stated purpose + audience only. "Domain" never appears.

_DROP_STEPS = """\
Classify into exactly one of three classes, tested IN ORDER. Stop at the first
that holds.

{grounded}

2. adjacent — (only if not grounded) the candidate serves the vision's stated
   PURPOSE for its stated AUDIENCE — the kind of thing a builder of this product
   might sensibly add — but no stated feature requires it. To claim adjacent you
   must cite the specific purpose or audience phrase in the vision it fits.

3. off_domain — (only if neither) the candidate serves a need the vision's stated
   purpose and audience do not imply. It may be plausible for some other product,
   but not this one. Cite nothing; state what the vision does not ask for."""

_DROP_SCHEMA = """\
Respond with ONLY a single JSON object, no prose, no code fences:

{"classification": "grounded" | "adjacent" | "off_domain",
 "cited_support": "<feature/goal, or the purpose/audience phrase; empty for off_domain>",
 "borderline": true | false,
 "reason": "<one sentence>"}"""

# --- variant B: audience_goal ------------------------------------------------
# Derive the job(s) first (feature-bounded), then judge adjacency against them.

_JOB_STEPS = """\
FIRST, derive the JOB(S) this product exists to do for its audience. List AT MOST
ONE job per feature in the vision, each derived from that feature and phrased as
narrowly as its description supports (e.g. "cook something tonight from a saved
recipe collection", not "food"). Do NOT invent jobs that no listed feature backs.
Emit this list as "stated_jobs".

THEN classify into exactly one of three classes, tested IN ORDER. Stop at the
first that holds.

{grounded}

2. adjacent — (only if not grounded) the candidate would plausibly help the
   stated audience accomplish one of the stated_jobs, though no feature requires
   it. To claim adjacent you must cite WHICH job it serves.

3. off_domain — (only if neither) the candidate does not serve any of the
   stated_jobs. Cite nothing; name the job(s) it fails to serve."""

_JOB_SCHEMA = """\
Respond with ONLY a single JSON object, no prose, no code fences:

{"stated_jobs": ["<job>", ...],
 "classification": "grounded" | "adjacent" | "off_domain",
 "cited_support": "<feature/goal for grounded; the job served for adjacent; empty for off_domain>",
 "borderline": true | false,
 "reason": "<one sentence>"}"""


def judge_system_prompt(variant: str) -> str:
    """Assemble the system prompt for a bake-off variant.

    The intro, the grounded (necessity) step, and the skeptical posture are
    identical across variants — only the adjacency / off_domain definition and
    the output schema differ, so the experiment isolates that boundary.
    """
    if variant == "drop_domain":
        steps, schema = _DROP_STEPS.format(grounded=_GROUNDED), _DROP_SCHEMA
    elif variant == "audience_goal":
        steps, schema = _JOB_STEPS.format(grounded=_GROUNDED), _JOB_SCHEMA
    else:
        raise ValueError(f"unknown variant: {variant!r} (expected one of {VARIANTS})")
    return "\n\n".join([_INTRO, steps, _SKEPTICAL, schema])


@dataclass
class Verdict:
    """One relevance judgement for one candidate."""

    candidate_name: str
    classification: str  # one of LABELS, or "error" if unparseable
    cited_support: str = ""
    borderline: bool = False
    reason: str = ""
    stated_jobs: list[str] = field(default_factory=list)  # audience_goal variant only

    @property
    def ok(self) -> bool:
        return self.classification in LABELS


# ---------------------------------------------------------------------------
# Vision rendering (deterministic)
# ---------------------------------------------------------------------------

def _find_key_features(vision: dict[str, Any]) -> list[Any]:
    """Locate the key_features_mvp list across the shapes Scout is fed."""
    if not isinstance(vision, dict):
        return []
    vs = vision.get("vision_statement")
    for container in (
        vs.get("vision") if isinstance(vs, dict) else None,
        vs if isinstance(vs, dict) else None,
        vision.get("vision") if isinstance(vision.get("vision"), dict) else None,
        vision,
    ):
        if isinstance(container, dict) and isinstance(
            container.get("key_features_mvp"), list
        ):
            return container["key_features_mvp"]
    return []


def _feature_lines(vision: dict[str, Any]) -> list[str]:
    """Render 'name — description' for each vision feature."""
    lines: list[str] = []
    for entry in _find_key_features(vision):
        if isinstance(entry, dict) and len(entry) == 1:
            name, body = next(iter(entry.items()))
            desc = ""
            if isinstance(body, dict):
                desc = str(body.get("description", "")).strip()
            lines.append(f"- {name}" + (f" — {desc}" if desc else ""))
        elif isinstance(entry, str):
            lines.append(f"- {entry}")
    return lines


def _vision_meta(vision: dict[str, Any]) -> dict[str, Any]:
    """Pull purpose / audience / differentiators from whatever shape."""
    root: dict[str, Any] = vision
    vs = vision.get("vision_statement") if isinstance(vision, dict) else None
    if isinstance(vs, dict):
        root = vs.get("vision") if isinstance(vs.get("vision"), dict) else vs
    elif isinstance(vision.get("vision"), dict):
        root = vision["vision"]
    return {
        "purpose": str(root.get("purpose", "")).strip(),
        "audience": root.get("target_audience") or [],
        "differentiators": root.get("differentiators") or [],
    }


def build_judge_user_prompt(vision: dict[str, Any], candidate: Any) -> str:
    """Deterministically render the vision + one candidate for the judge."""
    meta = _vision_meta(vision)
    if isinstance(candidate, dict):
        cname = str(candidate.get("name", ""))
        cdesc = str(candidate.get("rough_description", "")).strip()
    else:
        cname = str(getattr(candidate, "name", ""))
        cdesc = str(getattr(candidate, "rough_description", "")).strip()

    parts = ["VISION", "======"]
    if meta["purpose"]:
        parts.append(f"Purpose: {meta['purpose']}")
    if meta["audience"]:
        parts.append("Target audience: " + "; ".join(str(a) for a in meta["audience"]))
    if meta["differentiators"]:
        parts.append(
            "Differentiators: " + "; ".join(str(d) for d in meta["differentiators"])
        )
    parts.append("")
    parts.append("Vision features:")
    parts.extend(_feature_lines(vision) or ["(none listed)"])
    parts.append("")
    parts.append("CANDIDATE")
    parts.append("=========")
    parts.append(f"Name: {cname}")
    if cdesc:
        parts.append(f"Description: {cdesc}")
    parts.append("")
    parts.append("Classify this candidate's relevance to the vision above.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Parsing (deterministic)
# ---------------------------------------------------------------------------

def parse_judge_response(text: str, candidate_name: str) -> Verdict:
    """Extract a Verdict from the model's response.

    Tolerates code fences and surrounding prose by taking the outermost {...}.
    An unparseable or invalid response yields a Verdict with classification
    "error" (never silently coerced to a real class).
    """
    raw = (text or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return Verdict(candidate_name, "error", reason="no JSON object found")
    try:
        obj = json.loads(raw[start : end + 1])
    except (ValueError, TypeError):
        return Verdict(candidate_name, "error", reason="invalid JSON")
    cls = str(obj.get("classification", "")).strip().lower()
    if cls not in LABELS:
        return Verdict(candidate_name, "error", reason=f"bad classification: {cls!r}")
    jobs_raw = obj.get("stated_jobs") or []
    jobs = [str(j).strip() for j in jobs_raw if str(j).strip()] if isinstance(
        jobs_raw, list
    ) else []
    return Verdict(
        candidate_name=candidate_name,
        classification=cls,
        cited_support=str(obj.get("cited_support", "")).strip(),
        borderline=bool(obj.get("borderline", False)),
        reason=str(obj.get("reason", "")).strip(),
        stated_jobs=jobs,
    )


# ---------------------------------------------------------------------------
# Runner (real LLM calls — needs a provider key)
# ---------------------------------------------------------------------------

def _candidate_name(candidate: Any) -> str:
    if isinstance(candidate, dict):
        return str(candidate.get("name", ""))
    return str(getattr(candidate, "name", ""))


def judge_candidate(
    vision: dict[str, Any],
    candidate: Any,
    llm_config: dict[str, Any],
    variant: str = "drop_domain",
) -> Verdict:
    """Judge one candidate.

    Temperature is NOT pinned — ``spec4.llm`` no longer sends the parameter on
    any path, since a growing number of judge-class models reject it outright.
    Every judge call takes the model's default sampling settings, at the cost of
    bit-reproducible re-runs.
    """
    messages = [
        {"role": "system", "content": judge_system_prompt(variant)},
        {"role": "user", "content": build_judge_user_prompt(vision, candidate)},
    ]
    resp = complete(llm_config=llm_config, messages=messages, agent_name=None)
    content = resp.choices[0].message.content or ""
    return parse_judge_response(content, _candidate_name(candidate))


def judge_candidates(
    vision: dict[str, Any],
    candidates: list[Any],
    llm_config: dict[str, Any],
    variant: str = "drop_domain",
) -> list[Verdict]:
    """Judge every candidate for a vision (sequential)."""
    return [judge_candidate(vision, c, llm_config, variant) for c in candidates]