from __future__ import annotations

import json
import os
import traceback
from collections.abc import Generator
from typing import Any

from spec4 import project_manager, llm, websearch
from spec4.agents import feature_speccer
from spec4.agents._utils import (
    _abandon_reask,
    _artifact_fallback,
    _artifact_reask_prompt,
    _artifact_reask_status,
    _drop_orphan_or_route_to_fresh_start,
    _extract_json_block,
    _last_assistant_text,
    _maybe_inject_resume_summary,
    _maybe_inject_staleness_question,
    _reask_for_artifact,
    _render_references,
    _replay_last_assistant,
    _stream_suppressing_json,
    _suppressed_as_artifact,
    slug,
)
from spec4.app_constants import STATE_IN_PROGRESS, STATE_VISION_COMPLETE

_DEV_MODE = os.environ.get("DASH_DEBUG", "").lower() == "true"


SYSTEM_PROMPT = """\
You are a skilled product collaborator. Your job is to help the user develop a clear, \
concrete, technology-agnostic vision for their software project — describing what the \
software does, who it is for, and why it matters. The vision statement you produce is \
consumed by three downstream agents; completeness and clarity here directly determine \
the quality of their output:
- **StackAdvisor** — aligns the technology stack with the project's goals and constraints
- **Phaser** — plans implementation phases and milestones
- **Designer** — generates a visual mock-up of the starting screen (UI projects only)

**Modes of operation**

Select the appropriate mode based on what context is available at the start of the \
conversation:

- **Fresh start** — No prior context. Ask the user for their initial idea and lead them\
  through the topic sequence below.
- **Existing project, no vision** — A code review or project notes have been provided.\
  Briefly summarize your understanding of the existing project, then lead the user through\
  the topic sequence, framing questions around the project's existing purpose and goals.
- **Update mode** — An existing vision statement has been provided. Present it as a clear,\
  readable summary. Ask the user what changes they would like to make. Work through those\
  changes one at a time using your normal one-question-at-a-time approach. When the user\
  confirms they are satisfied, generate an updated vision statement incorporating every\
  change.
- **Revision mode** — A new version of an *already-implemented* project is being planned.\
  The vision from the previous implemented version is provided as read-only reference,\
  alongside a code review of the current code. The project's identity is already\
  established — do NOT re-run the topic sequence and do NOT re-ask the project name.\
  Instead: state the established identity (name and purpose) and one line on what is\
  already built; ask what the goal of this revision is and what to add, change, or\
  remove; then work the requested changes one at a time. Frame everything as changes to\
  the existing product — do NOT push changes into "future enhancements." When the user\
  confirms, produce the updated full vision plus this round's revision block (see\
  "Revision output" below).

**Topic sequence**

Cover these topics IN ORDER, one at a time. Skip a topic only if it is clearly not \
applicable (e.g., monetization for a personal tool). Do not advance to the next topic \
until the user has confirmed their answer to the current one. After each confirmed answer, \
briefly recap the decisions made so far so the user can see progress and change anything \
they want to revisit.

1. **Project name** — What will the project be called? Always ask this, even if the user\
   has not mentioned a name yet. If the user does not have a name, offer to suggest\
   several options based on what they have described — present them as a numbered list\
   and let the user pick one, combine ideas, or propose their own.
2. **Purpose** — What is the core problem this project solves, or the need it serves?\
   Who experiences this problem today?
3. **Target audience** — Who are the primary users? Are there secondary users or\
   stakeholders?
4. **Core features (MVP)** — What is the smallest set of features that delivers real\
   value? What must be present on day one?
5. **UI surface** — Will this be a web app, mobile app, desktop app, CLI tool,\
   API/service, or something else? (This is the only implementation-surface question you\
   ask — it shapes what Designer and Phaser produce.)
6. **Differentiators** — What makes this different from existing solutions?
7. **Future enhancements** — What features or improvements would follow a successful MVP?
8. **Monetization** — How will this project be sustained or monetized?
9. **Technical standards and integrations** — Does the project rely on any specific\
   protocols, APIs, SDKs, or compliance standards? (See web search rule below.)

After covering all applicable topics, present a full, readable summary of the vision and \
ask: "Does this capture everything, or would you like to revisit any part?" When the \
user confirms the vision is complete, generate the JSON.

**Interaction rules**

- Ask ONE question per response — never multiple questions at once.
- For each question, offer numbered options. Always include an option for the user to\
  suggest their own. When options are mutually exclusive, say "pick one." When multiple\
  can be combined, say "you can pick one or more."
- Confirmation questions (yes/no): never phrase as "X or Y?" — ask directly. End with\
  "(yes/no — you're also welcome to ask questions or share comments either way)".
- Single-select lists: end with "Please select an option (answer with number and/or\
  optional comments)".
- Multi-select lists: end with "(answer with number(s) and/or optional comments)".

**Technical references**

Whenever the user mentions a technical standard, specification, protocol, API, or SDK \
(for example "the MCP protocol", "the OpenAI API", "the A2A protocol", "OAuth 2.0"), use \
the web_search tool to find the canonical documentation URL. Present your findings and \
ask the user to confirm you have identified the correct standard before continuing. Once \
confirmed, add the standard and its canonical URL to the `references` array in the vision \
statement JSON. If a reference cannot be confirmed via web search or appears to be \
specific to the user's project, label it as "unique to this project" rather than guessing. \
Every technical standard, specification, protocol, API, or SDK mentioned anywhere in the \
vision statement must appear in `references`.

**Scope**

You will not write code, select an implementation approach, or ask about technology stack, \
hosting, deployment, infrastructure, or software libraries — those are handled by a \
separate agent. The only implementation-surface question you ask is topic 4 (UI surface), \
which is required because it shapes what the downstream agents produce.

**Generating the vision statement**

When the user confirms the vision is complete, output ONLY a fenced JSON code block. \
Include only what the user has explicitly confirmed — do not add features, goals, or \
details the user has not agreed to. Validate that the JSON is complete and well-formed \
before outputting it.

Here is an example (omit fields not applicable to the project):

```json
{
  "vision_statement": {
    "name": "BiteGuide",
    "vision": {
      "purpose": "A **smart restaurant discovery app** that combines **AI-powered recommendations**\
        with **user-driven reviews**, helping **food enthusiasts, casual diners, and travelers**\
          find personalized dining experiences tailored to their preferences and context.",
      "ui_surface": "Mobile app (iOS and Android)",
      "target_audience": [
        "Food enthusiasts seeking hidden gems and trending spots",
        "Casual diners looking for reliable, everyday options",
        "Travelers exploring local favorites in new cities"
      ],
      "key_features_mvp": [
        {
          "AI_Recommendations": {
            "description": "Personalized suggestions based on user preferences, past visits, and\
              context (e.g., time of day, location, mood).",
            "example": "\"Since you loved the spicy noodles last time, here's a new Sichuan spot\
              nearby.\""
          }
        },
        {
          "User_Reviews": {
            "description": "Verified user-generated reviews, photos, and ratings with tags (e.g.,\
              'vegan-friendly,' 'great for groups').",
            "example": "\"See what real diners say—no fake reviews here.\""
          }
        }
      ],
      "differentiators": [
        "AI that adapts to **user habits, mood, and real-time context** — not just generic\
          recommendations."
      ],
      "monetization": {
        "current": "Free tier only (MVP).",
        "future_options": [
          "Freemium upgrades (e.g., advanced AI, ad-free experience)",
          "Restaurant partnerships (e.g., featured listings, commissions)"
        ]
      },
      "future_enhancements": [
        {
          "Advanced_AI": {
            "description": "Predictive suggestions before the user searches.",
            "example": "AI anticipates user preferences based on past trends."
          }
        }
      ],
      "references": [
        {
          "standard": "OAuth 2.0",
          "url": "https://oauth.net/2/"
        }
      ]
    }
  }
}
```

Output only the JSON code block when generating the final vision statement — no additional \
text after it.

**Revision output (revision mode only)**

In revision mode, output the SAME single fenced JSON block, with two top-level keys: \
`vision_statement` (the FULL updated vision) and `revision` (this round's delta).

Carry every unchanged section of `vision_statement` forward VERBATIM from the prior \
vision; modify only the parts this revision actually changes. The result must be a \
complete, standalone vision describing the project as it will be after this revision — \
never a diff or a partial.

The `revision` block records this round's delta:

```json
{
  "vision_statement": { "...": "the full updated vision (see schema above)" },
  "revision": {
    "goal": "One or two sentences: the purpose of this revision.",
    "changes": {
      "added": ["Exact name of each NEW key_features_mvp entry"],
      "modified": ["Exact name of each CHANGED key_features_mvp entry"],
      "removed": ["Exact name of each feature dropped from key_features_mvp"]
    },
    "rationale": "One or two sentences: why these changes were made."
  }
}
```

Each name in `changes` MUST exactly match the name/key you use for that entry in \
`key_features_mvp`, so each change can be matched to its feature later. Do NOT include \
`version` or `based_on_version` — those are recorded automatically. Include the \
`revision` block ONLY in revision mode.
"""


def _extract_vision_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON vision statement from a fenced code block in the LLM response."""
    data = _extract_json_block(text)
    return data if data is not None and "vision_statement" in data else None


def _stamp_revision_block(
    block: dict[str, Any], version: int, based_on_version: int
) -> dict[str, Any]:
    """Normalize a model-emitted revision block into the stored schema.

    Code owns ``version`` / ``based_on_version`` (the model never authors the
    integers) and the three change arrays are coerced to lists so a downstream
    consumer (Phaser, a later round) can always join them against
    ``key_features_mvp`` without shape-guarding.
    """
    raw = block.get("changes")
    raw = raw if isinstance(raw, dict) else {}
    return {
        "version": version,
        "based_on_version": based_on_version,
        "goal": block.get("goal", ""),
        "changes": {
            "added": list(raw.get("added") or []),
            "modified": list(raw.get("modified") or []),
            "removed": list(raw.get("removed") or []),
        },
        "rationale": block.get("rationale", ""),
    }


def _feature_names(vision: dict[str, Any] | None) -> list[str]:
    """Ordered ``key_features_mvp`` entry names from a vision envelope.

    Handles the canonical single-key-dict entries (``{Name: {...}}``) and the
    bare-string shape some fixtures use. Looks under
    ``vision_statement.vision.key_features_mvp`` first, then falls back to
    ``vision_statement.key_features_mvp``. Returns ``[]`` when none is present.
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
    names: list[str] = []
    for item in kf:
        if isinstance(item, dict) and item:
            names.append(next(iter(item)))
        elif isinstance(item, str):
            names.append(item)
    return names


def _assign_feature_ids(vision: dict[str, Any]) -> dict[str, Any]:
    """Stamp a stable ``id`` (= ``slug(name)``) onto each ``key_features_mvp`` entry.

    Deterministic and in-place per D-BS3: the model authors feature names, code
    owns the ids. Runs on the final feature set (after any revision fold), so the
    id enforces the ``id == slug(name)`` invariant the downstream agents assume
    when they join by id. Always (re)derives from the current name rather than
    preserving a carried-forward id, so a folded or re-emitted vision stays
    consistent. Only the canonical ``{Name: {...}}`` and flat ``{name, ...}``
    entry shapes can hold an id; bare-string fixtures are left untouched.
    """
    if not isinstance(vision, dict):
        return vision
    vs = vision.get("vision_statement")
    if not isinstance(vs, dict):
        return vision
    inner = vs.get("vision")
    kf = inner.get("key_features_mvp") if isinstance(inner, dict) else None
    if kf is None:
        kf = vs.get("key_features_mvp")
    if not isinstance(kf, list):
        return vision
    for item in kf:
        if not isinstance(item, dict) or not item:
            continue
        if "name" in item and "description" in item:
            item["id"] = slug(str(item["name"]))
            continue
        name = next(iter(item))
        val = item[name]
        if isinstance(val, dict):
            val["id"] = slug(str(name))
    return vision


def _reclassify_changes(
    entry: dict[str, Any],
    prior_vision: dict[str, Any] | None,
    emitted: dict[str, Any],
) -> dict[str, Any]:
    """Reconcile a revision entry's change lists against feature membership.

    The model authors ``changes`` and can mislabel a brand-new feature as
    ``modified`` — e.g. when it was added and then edited within the same
    revision session, so the model categorizes against the intermediate vision
    rather than the prior *implemented* baseline. This recomputes the split
    deterministically from ``key_features_mvp`` membership:

    - ``added``    = features in this revision but not in the prior baseline
      (ordered by the new vision; complete even if the model omitted one).
    - ``removed``  = features in the prior baseline but gone from this revision.
    - ``modified`` = features the model flagged as touched (its ``added`` +
      ``modified``), kept only when present in *both* versions; a touched
      feature absent from the baseline is new, so it lands in ``added``.

    A rename therefore reads as remove + add (names are the downstream join
    keys). When this revision has no parseable ``key_features_mvp`` there is no
    ground truth to reconcile against, so the model's lists are left untouched.
    """
    v1_names = _feature_names(emitted)
    if not v1_names:
        return entry
    v0_names = _feature_names(prior_vision)
    v0_set = set(v0_names)
    v1_set = set(v1_names)
    in_both = v0_set & v1_set

    changes = entry.get("changes")
    changes = changes if isinstance(changes, dict) else {}
    touched = list(changes.get("added") or []) + list(changes.get("modified") or [])

    def _dedup(seq: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for n in seq:
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out

    reconciled = dict(entry)
    reconciled["changes"] = {
        "added": _dedup([n for n in v1_names if n not in v0_set]),
        "modified": _dedup([n for n in touched if n in in_both]),
        "removed": _dedup([n for n in v0_names if n not in v1_set]),
    }
    return reconciled


def _apply_revision_history(
    emitted: dict[str, Any],
    prior_vision: dict[str, Any],
    current_vision: dict[str, Any] | None,
    version: int,
    based_on_version: int,
) -> dict[str, Any]:
    """Fold this revision round's delta into an accumulating ``revision_history``.

    In revision mode the model emits a top-level ``revision`` block (this
    round's goal, the feature-name changes that join into ``key_features_mvp``,
    and rationale) alongside ``vision_statement``. This function is
    deterministic — no LLM trust for the lineage:

    - The base is the prior *implemented* round's history (every entry for a
      version <= the implemented one). Each round contributes exactly one entry.
    - This round's entry is the freshly-emitted block (stamped), or — on a
      re-entry where the model did not re-emit one — the existing entry already
      recorded for this ``version`` in the current session vision, so editing a
      revision before it is implemented never drops its lineage entry.
    - The merged history is written onto the new vision and the transient
      top-level ``revision`` key is dropped.
    - This round's change categorization is reconciled against feature-name
      membership, so a feature absent from the prior implemented baseline is
      recorded as ``added`` even if the model (or an add-then-edit within this
      session) labelled it ``modified`` (see :func:`_reclassify_changes`).
    """
    block = emitted.pop("revision", None)
    base = list(
        prior_vision.get("vision_statement", {}).get("revision_history", [])
    )
    this_entry: dict[str, Any] | None = None
    if isinstance(block, dict):
        this_entry = _stamp_revision_block(block, version, based_on_version)
    else:
        cur_history = (current_vision or {}).get("vision_statement", {}).get(
            "revision_history", []
        )
        for entry in cur_history:
            if isinstance(entry, dict) and entry.get("version") == version:
                this_entry = entry
                break
    if this_entry is not None:
        this_entry = _reclassify_changes(this_entry, prior_vision, emitted)
    merged = base + ([this_entry] if this_entry is not None else [])
    vs = emitted.setdefault("vision_statement", {})
    if isinstance(vs, dict):
        vs["revision_history"] = merged
    return emitted


_REVIEW_OFFER_MARKER = "Would you like to review the current vision?"

_VISION_TRANSITION = (
    "---\n\n"
    "We've finished brainstorming the vision, so now you're ready to move on to "
    "identifying the AI features for your project. Please click on the "
    "**Continue to Agentifier** button below.\n\n"
    "If you'd like to make any changes to the vision first, just tell me what "
    "you'd like to adjust and we'll work through it together.\n\n"
    f"{_REVIEW_OFFER_MARKER} (yes/no)"
)

_VISION_REVIEW_FOOTER = (
    "---\n\n"
    "That's the current vision. If you'd like to change anything, just tell me "
    "what you'd like to adjust. Otherwise, click the **Continue to Agentifier** "
    "button below to move on."
)


def _is_review_request(
    user_input: str | None,
    session: dict[str, Any],
    msgs: list[dict[str, Any]],
) -> bool:
    """True when the user affirmatively answers the post-vision review offer.

    Fires only when the vision is already complete, the input is a bare
    affirmative ("yes"/"y", case-insensitive and trimmed), and the most recent
    assistant message actually carried the review offer. The last condition
    keeps a "yes" that confirms a pending revision — where the latest assistant
    turn is a proposal rather than the offer — falling through to the LLM.
    """
    if session.get("brainstormer_state") != STATE_VISION_COMPLETE:
        return False
    if (user_input or "").strip().lower() not in {"yes", "y"}:
        return False
    return _REVIEW_OFFER_MARKER in _last_assistant_text(msgs)


def _render_feature_item(feat: Any, lines: list[str]) -> None:
    """Render a single feature/enhancement entry in any of the shapes the LLM emits.

    Three shapes seen in practice:
    - bare string ("AI Recommendations")
    - canonical {Name: {description, example}} from the system prompt
    - flat dict with explicit "name"/"description" keys
    """
    if isinstance(feat, str):
        lines.append(f"- {feat}")
        return
    if not isinstance(feat, dict):
        lines.append(f"- {feat}")
        return
    if "name" in feat and "description" in feat:
        lines.append(f"- **{feat['name']}** — {feat['description']}")
        return
    for feat_name, feat_val in feat.items():
        label = str(feat_name).replace("_", " ")
        if isinstance(feat_val, dict):
            desc = feat_val.get("description", "")
        else:
            desc = str(feat_val)
        lines.append(f"- **{label}** — {desc}")


def _format_vision_as_text(
    vision: dict[str, Any], footer: str = _VISION_TRANSITION
) -> str:
    vs = vision.get("vision_statement", {})
    raw_v = vs.get("vision", {})
    # vision may be a plain string in minimal/test JSON
    v: dict[str, Any] = raw_v if isinstance(raw_v, dict) else {}
    lines: list[str] = []

    name = vs.get("name", "")
    lines.append(f"**Vision Statement: {name}**\n" if name else "**Vision Statement**\n")

    if isinstance(raw_v, str):
        lines.append(f"**Vision:** {raw_v}\n")
    elif "purpose" in v:
        lines.append(f"**Purpose:** {v['purpose']}\n")

    if "ui_surface" in v:
        lines.append(f"**UI Surface:** {v['ui_surface']}\n")

    audience: list[str] = v.get("target_audience", [])
    if audience:
        lines.append("**Target Audience:**")
        for item in audience:
            lines.append(f"- {item}")
        lines.append("")

    features: list[Any] = v.get("key_features_mvp", [])
    if features:
        lines.append("**Core Features (MVP):**")
        for feat in features:
            _render_feature_item(feat, lines)
        lines.append("")

    differentiators: list[str] = v.get("differentiators", [])
    if differentiators:
        lines.append("**Differentiators:**")
        for item in differentiators:
            lines.append(f"- {item}")
        lines.append("")

    future: list[Any] = v.get("future_enhancements", [])
    if future:
        lines.append("**Future Enhancements:**")
        for feat in future:
            _render_feature_item(feat, lines)
        lines.append("")

    raw_monetization = v.get("monetization", {})
    monetization: dict[str, Any] = (
        raw_monetization if isinstance(raw_monetization, dict) else {}
    )
    if isinstance(raw_monetization, str) and raw_monetization:
        lines.append("**Monetization:**")
        lines.append(f"- {raw_monetization}")
        lines.append("")
    elif monetization:
        lines.append("**Monetization:**")
        if "current" in monetization:
            lines.append(f"- Current: {monetization['current']}")
        future_opts: list[str] = monetization.get("future_options", [])
        for opt in future_opts:
            lines.append(f"- Future: {opt}")
        lines.append("")

    _render_references(v.get("references", []), lines)

    lines.append(footer)
    return "\n".join(lines)


def _vision_fallback_display(vision: dict[str, Any]) -> str:
    """Minimal display used when `_format_vision_as_text` raises on an unexpected shape.

    Guarantees the user sees the project name and the transition message instead
    of a raw JSON dump leaking through the chat.
    """
    name = ""
    vs = vision.get("vision_statement")
    if isinstance(vs, dict):
        name = str(vs.get("name", "") or "")
    heading = (
        f"**Vision Statement saved for {name}.**\n\n"
        if name
        else "**Vision Statement saved.**\n\n"
    )
    return (
        heading
        + "Your vision has been saved to `.spec4/vision.json`.\n\n"
        + _VISION_TRANSITION
    )


def _rehydrate_vision_from_disk(session: dict[str, Any]) -> None:
    """Re-sync the Brainstormer's vision artifacts to disk at the start of a turn.

    The agent button state reads disk (the current ``vision.json`` for the active
    round); ``run()``'s entry decision must agree, so we reload from the same
    version the button checks (via ``load_vision`` / ``active_version``) and set
    the vision, brainstormer state, and derived feature specs to match. This
    prevents an in-memory ``vision_statement`` left over from a prior draw — for
    example after the project's ``.spec4`` directory is deleted out of band — from
    driving ``run()`` into update mode while the button correctly shows "Start".

    Guarded on ``working_dir``: with no project directory there is no disk and the
    in-memory session stands. Messages are deliberately left untouched, so an
    in-progress brainstorm (messages present, no vision on disk yet) is preserved.
    """
    working_dir = session.get("working_dir")
    if not working_dir:
        return
    vision = project_manager.load_vision(working_dir, session)
    if vision is not None:
        session["vision_statement"] = vision
        session["brainstormer_state"] = STATE_VISION_COMPLETE
        session["feature_specs"] = project_manager.load_feature_specs(working_dir)
    else:
        session["vision_statement"] = None
        session["brainstormer_state"] = STATE_IN_PROGRESS
        session["feature_specs"] = None


def run(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Brainstormer — collaborates with the user to develop a software project vision.

    Yields text chunks consumed by streaming.start().
    Mutates `session` to track conversation state and vision output.
    """
    if "brainstormer_messages" not in session:
        session["brainstormer_messages"] = []

    msgs = session["brainstormer_messages"]
    user_input = _drop_orphan_or_route_to_fresh_start(msgs, user_input)
    _rehydrate_vision_from_disk(session)

    if user_input is None:
        if msgs:
            stale_q = _maybe_inject_staleness_question(session, "brainstormer", msgs)
            if stale_q is not None:
                yield stale_q
                return
            if not _maybe_inject_resume_summary(
                session, "brainstormer", msgs, STATE_VISION_COMPLETE
            ):
                yield from _replay_last_assistant(msgs)
                return
            # Resume summary injected — fall through to LLM call.
        else:
            vision = session.get("vision_statement")
            code_review = session.get("code_review")
            working_dir = session.get("working_dir")
            prior_vision = (
                project_manager.load_prior_vision(working_dir)
                if working_dir
                else None
            )

            code_review_block = (
                f"\n\nFor context, here is a code review of the existing project:\n\n"
                f"```json\n{json.dumps(code_review, indent=2)}\n```\n\n"
                "Within the review, treat structured fields (`commands`, "
                "`entrypoints`, `ui_summary`, `runtime_versions`, "
                "`protocols_implemented`, `existing_self_description`) as "
                "authoritative facts about the project. The `notes` block is "
                "typed observations — respect `notes.change_risks` and "
                "`notes.incomplete_or_dead_code` when asking about future "
                "features.\n"
                if code_review
                else ""
            )

            if vision:
                # Brownfield update mode: present the existing vision and ask for changes
                vision_text = json.dumps(vision, indent=2)
                msgs.append(
                    {
                        "role": "user",
                        "content": (
                            f"I have an existing vision statement from a previous planning "
                            f"session:{code_review_block}\n\n"
                            f"```json\n{vision_text}\n```\n\n"
                            "Please introduce yourself as Brainstormer, then present this existing "
                            "vision to me as a clear, readable summary. Ask me to review it and "
                            "describe the changes I would like to make, then work through my "
                            "requested changes one at a time. When I confirm I am satisfied, "
                            "generate an updated vision statement."
                        ),
                    }
                )
                # Fall through to LLM call below
            elif prior_vision is not None:
                # Revision mode: a previous version of this project has been
                # implemented. Build the next version as a delta against the
                # established identity rather than rebuilding a vision from
                # scratch (the greenfield topic sequence).
                prior_text = json.dumps(prior_vision, indent=2)
                msgs.append(
                    {
                        "role": "user",
                        "content": (
                            "I am starting a new REVISION round on an existing, "
                            "already-implemented version of this project. Operate "
                            f"in REVISION mode.{code_review_block}\n\n"
                            "Here is the vision from the previous implemented "
                            "version, as read-only reference for the project's "
                            "established identity and its prior feature set:\n\n"
                            f"```json\n{prior_text}\n```\n\n"
                            "Please introduce yourself as Brainstormer, state the "
                            "project's established identity (its name and purpose) "
                            "and a one-line summary of what is already built, then "
                            "ask what the goal of this revision is and what I want "
                            "to add, change, or remove. Do not re-ask the project "
                            "name or re-derive the whole vision. Work through the "
                            "requested changes one at a time. When I confirm, "
                            "generate the updated full vision statement plus this "
                            "round's revision block."
                        ),
                    }
                )
                # Fall through to LLM call below
            elif code_review:
                # Existing project with code review but no vision yet
                msgs.append(
                    {
                        "role": "user",
                        "content": (
                            "I have an existing software project that I'd like to create a vision "
                            "statement for. Here is a code review of the existing project:\n\n"
                            f"```json\n{json.dumps(code_review, indent=2)}\n```\n\n"
                            "Please introduce yourself as Brainstormer. Briefly describe what you "
                            "understand about this project from the code review, then begin your "
                            "usual question-by-question process to develop the vision statement. "
                            "Use the code review as context to inform your questions."
                        ),
                    }
                )
                # Fall through to LLM call below
            else:
                # Fresh start: static greeting
                yield (
                    "Hello! I'm the **Brainstormer**. I'll help you develop a clear, "
                    "well-defined vision for your software project.\n\n"
                    "What's your initial idea for the project? It can be rough — "
                    "we'll refine it together."
                )
                return
    else:
        if _is_review_request(user_input, session, msgs):
            vision = session.get("vision_statement")
            if vision:
                try:
                    review = _format_vision_as_text(
                        vision, footer=_VISION_REVIEW_FOOTER
                    )
                except Exception:
                    review = _vision_fallback_display(vision)
                yield review
                return
        msgs.append({"role": "user", "content": user_input})

    search_cfg = websearch.from_session(session)
    system = llm.build_system_prompt(SYSTEM_PROMPT, search_cfg)

    # `session` is threaded in so the chars counter tracks real receipt rather
    # than displayed text: the vision-finalize turn is suppressed on its way to
    # the screen (see below), so without this the counter reads 0 for the whole
    # multi-minute draw — the D-SC60 failure, which applies here identically.
    yield from _stream_suppressing_json(
        llm.stream_turn(
            system, msgs, llm_config, search_cfg, agent_name="brainstormer"
        ),
        session,
    )

    raw_reply = _last_assistant_text(msgs)
    vision = _extract_vision_json(raw_reply)
    if vision is None and _suppressed_as_artifact(raw_reply):
        # D-BR-P3 (the D-SC-P3 fix, applied here): a reply that opened with a
        # fence was suppressed on its way to the screen, so an unreadable vision
        # block ends the turn with an empty bubble, no VISION_COMPLETE, and no
        # vision.json — indistinguishable to the developer from the app hanging.
        # Re-ask once, then explain rather than finishing silently.
        correction = _artifact_reask_prompt("vision statement")
        yield from _reask_for_artifact(
            system=system,
            msgs=msgs,
            llm_config=llm_config,
            search_config=search_cfg,
            agent_name="brainstormer",
            correction=correction,
            status_line=_artifact_reask_status("vision statement"),
            session=session,
            seed=len(raw_reply),
        )
        vision = _extract_vision_json(_last_assistant_text(msgs))
        if vision is None:
            _abandon_reask(
                msgs, correction, _artifact_fallback("vision statement"), session
            )
    if vision:
        working_dir = session.get("working_dir")
        prior_vision = (
            project_manager.load_prior_vision(working_dir) if working_dir else None
        )
        if prior_vision is not None:
            # Revision round: deterministically fold this round's delta into the
            # accumulating revision_history. Code owns the version integers.
            version = project_manager.resolve_phase_version(
                working_dir, bool(session.get("code_review"))
            )[0]
            based_on = project_manager.latest_implemented_version(working_dir)
            vision = _apply_revision_history(
                vision,
                prior_vision,
                session.get("vision_statement"),
                version,
                based_on if based_on is not None else 0,
            )
        vision = _assign_feature_ids(vision)
        session["brainstormer_state"] = STATE_VISION_COMPLETE
        session["vision_statement"] = vision
        session["feature_specs"] = feature_speccer.build_feature_specs(
            vision, llm_config, session
        )
        session["brainstormer_stale_acknowledged"] = {}
        footer_included = False
        try:
            display = _format_vision_as_text(vision, footer="")
        except Exception as exc:
            if _DEV_MODE:
                print(
                    f"[brainstormer] _format_vision_as_text failed: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
                traceback.print_exc()
            display = _vision_fallback_display(vision)
            footer_included = True
        specs_display = feature_speccer.render_feature_specs(
            session["feature_specs"]
        )
        if specs_display:
            display = f"{display}\n\n{specs_display}"
        if not footer_included:
            display = f"{display}\n\n{_VISION_TRANSITION}"
        msgs[-1]["content"] = display
        session["_display_override"] = display
        session["brainstormer_artifact_msg_count"] = len(msgs)
