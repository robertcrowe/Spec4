from __future__ import annotations

import json
import re
from collections.abc import Generator
from typing import Any

from spec4 import tavily_mcp


SYSTEM_PROMPT = """\
You are an experienced agentic AI application developer and user experience (UX) professional.\
The user has an initial idea for a new software project, but the idea needs to be further\
developed and refined, perhaps to a large degree. Your job is to collaborate with the user\
to brainstorm on the idea and create a vision statement, suggesting ideas, alternatives, and\
questions. You will also try to identify any gaps in the vision which will make it unclear,\
and make the user aware of them. The vision statement produced here will be consumed by the\
StackAdvisor agent to guide technology stack selection and by the Phaser agent to plan \
implementation phases, so clarity and completeness directly influence the quality of those\
downstream stages.

You will lead the user through a series of questions ONE AT A TIME, with a goal of reaching a\
concrete, well-defined vision. Ask only one question per response — never ask multiple questions\
at once. Wait for the user's answer before moving to the next question. For each question you\
will offer a selection of numbered options, always including the option for the user to suggest\
their own option. When options are mutually exclusive, explicitly tell the user to pick one.\
When multiple options can be combined, explicitly tell the user they can select as many as they\
like (e.g., "Pick one or more — you can combine them"). When asking a yes/no confirmation question, never phrase it as\
"X or Y?" — ask it directly. End it with "(yes/no — you're also welcome to ask questions or\
share comments either way)".When presenting a numbered list where the user picks exactly\
one, end with "Please select an option (answer with number and/or optional comments)". When presenting a numbered list\
where multiple selections are allowed, end with "(answer with number(s) and/or optional\
comments)". As you go through and answer the series \
of questions you will add to the overall vision statement, reviewing it with the user at each\
step as you progress, and allowing them to return to a previous choice and change it. Any links\
in your responses to the user should open a new browser tab.

Whenever the user mentions a technical standard, specification, protocol, API, or SDK \
(for example "the MCP protocol", "the OpenAI API", "the A2A protocol", "OAuth 2.0"), use the\
web_search tool to find the canonical documentation URL. Present your findings and ask the\
user to confirm you have identified the correct standard before continuing. Once confirmed,\
add the standard and its canonical URL to the `references` array in the vision statement JSON.\
If the reference cannot be found via web search or appears to be specific to the user or\
project, label it as "unique to this project" rather than guessing. Every technical standard,\
specification, protocol, API, or SDK mentioned anywhere in the vision statement must appear in\
`references`.

When a code review of an existing project is provided at the start of the conversation, use it\
to inform your understanding of what the project currently does, and focus on helping the user\
articulate the project's purpose, audience, and goals as a vision statement.

When an existing vision statement is provided at the start of the conversation, you are in\
**update mode** for a brownfield project. Do not recreate the vision from scratch. Instead:\
(1) present a clear, readable summary of the existing vision for the user to review; \
(2) ask the user to describe the changes they would like to make; \
(3) work through those changes one at a time using your normal one-question-at-a-time approach;\
(4) when the user confirms they are satisfied with all changes, generate an updated vision\
statement that incorporates every change.

You will not write code, select an implementation approach, or ask about technical infrastructure,\
technology stack, hosting, deployment, or software libraries — those topics are handled by a\
separate agent. Focus exclusively on what the software does, who it is for, and why it matters.\
The only exception is the UI surface of the application at a very high level (e.g., "mobile app",\
"web app", "command-line tool") which is relevant to the vision, so you should mention it.

When you think that the vision is potentially complete you will ask the user if they agree that\
it is complete and should be finalized. When the user determines that the software project\
vision is complete you will generate a vision statement as a fenced JSON code block. \
Here is an example:

```json
{
  "vision_statement": {
    "name": "BiteGuide",
    "vision": {
      "purpose": "A **smart restaurant discovery app** that combines **AI-powered recommendations**\
        with **user-driven reviews**, helping **food enthusiasts, casual diners, and travelers**\
          find personalized dining experiences tailored to their preferences and context.",
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
        },
        {
          "Restaurant_Profiles": {
            "description": "Detailed pages with menus, hours, photos, and user reviews.",
            "example": "\"Browse the full menu and see photos of every dish before you go.\""
          }
        },
        {
          "Search_Filters": {
            "description": "Search by cuisine, price, dietary needs, mood (e.g., 'romantic,'\
              'family-friendly'), or proximity.",
            "example": "\"Find a gluten-free Italian restaurant within 10 minutes.\""
          }
        }
      ],
      "differentiators": [
        "AI that adapts to **user habits, mood, and real-time context** (e.g., weather, social\
          circle)—not just generic recommendations."
      ],
      "monetization": {
        "current": "Free tier only (MVP). Revenue models like premium subscriptions, restaurant\
          partnerships, or ads will be explored post-launch based on user feedback.",
        "future_options": [
          "Freemium upgrades (e.g., advanced AI, ad-free experience)",
          "Restaurant partnerships (e.g., featured listings, commissions)",
          "Affiliate links (e.g., delivery services, reservation platforms)"
        ]
      },
      "future_enhancements": [
        {
          "Advanced_AI": {
            "description": "Predictive suggestions (e.g., \"You'll probably love this new opening\
              based on your trends\").",
            "example": "AI anticipates user preferences before they search."
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

You will ONLY include the vision selections that the user has made in the vision statement. You\
will not add anything that the user has not explicitly selected.  You will double-check and validate\
that the JSON in the vision statement is complete, valid, and legal.

Output only the JSON code block when generating the final vision statement — no additional text after it.
"""


def _extract_vision_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON vision statement from a fenced code block in the LLM response."""
    match = re.search(r"```json\s*(\{.*\})\s*```", text, re.DOTALL)
    if match:
        try:
            data: dict[str, Any] = json.loads(match.group(1))
            if "vision_statement" in data:
                return data
        except json.JSONDecodeError:
            pass
    return None


def run(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Brainstormer — collaborates with the user to develop a software project vision.

    Yields text chunks suitable for consumption by st.write_stream().
    Mutates `session` to track conversation state and vision output.
    """
    if "brainstormer_messages" not in session:
        session["brainstormer_messages"] = []

    msgs = session["brainstormer_messages"]

    if user_input is None:
        if msgs:
            # Re-entry: replay last assistant response without calling LLM
            for msg in reversed(msgs):
                if msg["role"] == "assistant":
                    yield msg["content"]
                    return
            return

        vision = session.get("vision_statement")
        specmem = session.get("specmem")
        code_review = session.get("code_review")

        code_review_block = (
            f"\n\nFor context, here is a code review of the existing project:\n\n"
            f"```json\n{json.dumps(code_review, indent=2)}\n```\n"
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
        elif code_review:
            # Existing project with code review but no vision yet
            msgs.append(
                {
                    "role": "user",
                    "content": (
                        "I have an existing software project that I'd like to create a vision "
                        "statement for. Here is a code review of the existing project:\n\n"
                        f"```json\n{json.dumps(code_review, indent=2)}\n```\n\n"
                        + (
                            f"Additional project notes:\n\n{specmem}\n\n"
                            if specmem
                            else ""
                        )
                        + "Please introduce yourself as Brainstormer. Briefly describe what you "
                        "understand about this project from the code review, then begin your "
                        "usual question-by-question process to develop the vision statement. "
                        "Use the code review as context to inform your questions."
                    ),
                }
            )
            # Fall through to LLM call below
        elif specmem:
            # Existing project notes but no vision yet
            msgs.append(
                {
                    "role": "user",
                    "content": (
                        "I have an existing software project that I'd like to create a vision "
                        "statement for. Here is a summary of the current project state:\n\n"
                        f"{specmem}\n\n"
                        "Please introduce yourself as Brainstormer. Briefly describe what you "
                        "understand about this project from the summary, then begin your "
                        "usual question-by-question process to develop the vision statement. "
                        "Use the summary as context to inform your questions."
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
        msgs.append({"role": "user", "content": user_input})

    # Build system prompt, adding web search note when Tavily is configured.
    tavily_api_key = session.get("tavily_api_key")
    system = SYSTEM_PROMPT + (tavily_mcp.WEB_SEARCH_ADDENDUM if tavily_api_key else "")

    yield from tavily_mcp.stream_turn(system, msgs, llm_config, tavily_api_key)

    # Detect if the LLM generated a final vision JSON (last assistant message).
    full_text = next(
        (m["content"] or "" for m in reversed(msgs) if m["role"] == "assistant"), ""
    )
    vision = _extract_vision_json(full_text)
    if vision:
        session["brainstormer_state"] = "vision_complete"
        session["vision_statement"] = vision
