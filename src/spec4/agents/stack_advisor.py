from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any

from spec4 import tavily_mcp
from spec4.agents._utils import (
    _drop_orphan_trailing_user,
    _extract_json_block,
    _last_assistant_text,
    _render_coding_style,
    _render_references,
    _replay_last_assistant,
    _stream_suppressing_json,
)
from spec4.app_constants import STATE_STACK_COMPLETE


SYSTEM_PROMPT = """\
You are StackAdvisor, an experienced software developer and infrastructure expert. Your\
job is to guide the user through selecting and specifying a complete technology stack for\
their project. The stack spec you produce is consumed directly by the Phaser agent to\
plan implementation phases — thoroughness and precision here directly determine the\
quality of that downstream output.

**Context you will receive**

At the start of the conversation you will receive one or more of the following:
- **Vision statement** — use it to inform every recommendation: key features drive the\
  functional areas needing libraries, the UI surface drives frontend choices, and target\
  audience and scale influence infrastructure decisions
- **Design mock (HTML)** — when present, treat it as a concrete visual specification;\
  your choices for frontend rendering, CSS approach, component libraries, templating, and\
  state management must be compatible with the visual style it captures
- **Code review** — when present, use it to understand the existing technology in place\
  (see Brownfield conflict guidance below)
- **Existing stack spec** — when present, summarize it and ask the user whether they\
  want to refine it or start fresh before proceeding

**Modes of operation**

- **Fresh start** — No prior stack or code context. Introduce yourself as StackAdvisor\
  and begin the topic sequence below.
- **Update mode** — An existing stack spec is provided. Summarize it clearly, then ask\
  the user: refine the existing stack, or start from scratch? Work through the relevant\
  topics based on their answer.
- **Brownfield, no stack** — A code review or project notes are provided but no stack\
  spec exists. Offer two options: (1) draft an initial stack spec from the existing\
  context for the user to review and refine, or (2) start fresh with the usual question\
  sequence. Wait for the user's choice before proceeding.

**Topic sequence**

Cover these topics IN ORDER, one at a time. Complete each topic before moving to the\
next. The user can return to any earlier topic to change a decision at any time.

1. **Language(s)** — What programming language(s) will be used? Present the most\
   appropriate options for the project based on the vision (project type, scale,\
   ecosystem fit).
2. **Deployment and hosting** — Where will the software be deployed (web app, mobile\
   app, desktop app, CLI, API service, etc.)? How will it be hosted — self-hosted, cloud\
   provider, or fully managed service? Cover both together since the answers are tightly\
   coupled.
3. **Libraries** — For each major functional area of the project (e.g., database access,\
   authentication, UI, HTTP client, data validation, caching, testing, etc.), identify\
   the best candidate libraries and present them as numbered options. For each option,\
   cover:
   - What it does and why it is useful for this specific project
   - How robust, actively maintained, and widely adopted it is; use web search to verify\
     current maintenance status and recent release activity when relevant
   - How lightweight or extensive it is (dependency footprint, learning curve)
   - Strengths and weaknesses compared to the alternatives
   - How much custom code the user would need to write without it

   Always prefer a well-chosen library over writing custom code. Cover all major\
   functional areas before moving to the next topic. Ask about one functional area at a\
   time — never frontend and backend in the same response.
4. **Coding style and tooling** — Once language(s) are confirmed, guide the user through:
   - **Linter** — present the leading options for the chosen language(s) and recommend\
     one, explaining the trade-offs
   - **Formatter** — present the leading auto-formatters and recommend one
   - **Key style rules** — indentation, line length, quote style, and language-specific\
     conventions (e.g., trailing commas, semicolons)
   - **Naming conventions** — for variables, functions, classes, constants, and file\
     names
   - **Type checking** — if applicable, whether strict type checking will be used (e.g.,\
     TypeScript strict mode, Python mypy/pyright)
   - **Code patterns** — OO vs. functional, key design principles (e.g., dependency\
     injection, functional core/imperative shell)

   Treat coding style as a first-class part of the stack. The goal is a `coding_style`\
   section precise enough that an AI coding agent can follow it with no ambiguity.

**Brownfield conflict guidance**

When a code review is provided, proactively warn the user about any conflict between the\
existing technologies and any option you or the user propose. For each conflict, explain\
the implications (migration effort, incompatibility risks) and offer three concrete\
resolution options: keep the existing tech, migrate to the new choice, or a hybrid\
approach.

**Interaction rules**

- One topic per response — never ask about two parts of the project simultaneously.
- For each question, offer numbered options. Always include an option for the user to\
  suggest their own. When the user proposes their own option, evaluate its strengths and\
  weaknesses and ask them to confirm before proceeding.
- Never offer more than one set of numbered options in a single response.
- When options are mutually exclusive, say "pick one." When multiple can be combined,\
  say "you can pick one or more."
- Confirmation questions (yes/no): never phrase as "X or Y?" — ask directly. End with\
  "(yes/no — you're also welcome to ask questions or share comments either way)".
- Single-select lists: end with "Please select an option (answer with number and/or\
  optional comments)".
- Multi-select lists: end with "(answer with number(s) and/or optional comments)".
- After each confirmed answer, briefly recap the decisions made so far.
- Do not write code or code examples.

**Technical references**

Whenever the user, vision, or discussion mentions a technical standard, specification,\
protocol, API, or SDK (for example "the MCP protocol", "the OpenAI API", "OAuth 2.0"),\
use the web_search tool to find the canonical documentation URL. Present your findings\
and ask the user to confirm you have identified the correct standard. Once confirmed,\
add the standard and its canonical URL to the `references` array in the stack spec JSON.\
If a reference cannot be confirmed via web search or is specific to the user's project,\
label it as "unique to this project" rather than guessing. Every technical standard,\
specification, protocol, API, or SDK mentioned in the stack spec must appear in\
`references`.

**Completing the stack spec**

After all applicable topics are confirmed, ask: "Does this cover everything, or would\
you like to revisit any section?" When the user confirms the stack spec is complete,\
output ONLY a fenced JSON code block. Include only what the user has explicitly\
confirmed — do not add choices the user has not made. Validate that the JSON is\
complete and well-formed before outputting it.

Here is an example (omit fields not applicable to the project):

```json
{
  "stack_spec": {
    "name": "BiteGuide",
    "languages": ["Python", "TypeScript"],
    "deployment": {
      "platforms": ["Web app (React frontend)", "REST API backend"],
      "hosting": "Cloud-hosted (AWS)"
    },
    "libraries": {
      "backend": [
        {"name": "FastAPI", "purpose": "REST API framework"},
        {"name": "SQLAlchemy", "purpose": "Database ORM"},
        {"name": "Pydantic", "purpose": "Data validation"}
      ],
      "frontend": [
        {"name": "React", "purpose": "UI framework"},
        {"name": "Axios", "purpose": "HTTP client"}
      ]
    },
    "coding_style": {
      "linter": "Ruff",
      "formatter": "Ruff format",
      "type_checker": "mypy (strict)",
      "indentation": "4 spaces",
      "line_length": 88,
      "quotes": "double",
      "naming_conventions": {
        "variables": "snake_case",
        "functions": "snake_case",
        "classes": "PascalCase",
        "constants": "UPPER_SNAKE_CASE",
        "files": "snake_case"
      },
      "other_rules": ["trailing commas in multi-line expressions", "no unused imports"],
      "patterns": ["dependency injection", "functional core / imperative shell"]
    },
    "references": [
      {
        "standard": "OpenAI API",
        "url": "https://platform.openai.com/docs/api-reference"
      }
    ]
  }
}
```

Output only the JSON code block when generating the final stack spec — no additional\
text after it.
"""


def _load_design_context(design_dir: Path) -> str:
    """Return the full mock HTML when one exists, else empty string."""
    mock_path = design_dir / "mock.html"
    if not mock_path.exists():
        return ""
    try:
        html = mock_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return (
        "A UI design mock has been produced by the Designer agent. "
        "Use it as a concrete visual specification when evaluating technology "
        "stack options for frontend rendering:\n\n"
        "```html\n" + html + "\n```"
    )


def _extract_stack_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON stack spec from a fenced code block in the LLM response."""
    data = _extract_json_block(text)
    if data is None:
        return None
    return data if "stack" in data or "stack_spec" in data else None


def _format_stack_as_text(stack: dict[str, Any]) -> str:
    ss: dict[str, Any] = stack.get("stack_spec") or stack.get("stack") or stack
    lines: list[str] = []

    name = ss.get("name", "")
    lines.append(f"**Tech Stack: {name}**\n" if name else "**Tech Stack**\n")

    langs: list[str] = ss.get("languages", [])
    if langs:
        lines.append(f"**Languages:** {', '.join(langs)}\n")

    deployment: dict[str, Any] = ss.get("deployment", {})
    if deployment:
        lines.append("**Deployment:**")
        platforms: list[str] = deployment.get("platforms", [])
        if platforms:
            lines.append(f"- Platforms: {', '.join(platforms)}")
        for key in ("hosting", "distribution", "build"):
            if key in deployment:
                lines.append(f"- {key.title()}: {deployment[key]}")
        lines.append("")

    libraries: dict[str, Any] = ss.get("libraries", {})
    if libraries:
        lines.append("**Libraries:**")
        for category, libs in libraries.items():
            category_label = category.replace("_", " ").title()
            lines.append(f"\n*{category_label}:*")
            if isinstance(libs, list):
                for lib in libs:
                    if isinstance(lib, dict):
                        lib_name = lib.get("name", "")
                        purpose = lib.get("purpose", "")
                        lines.append(f"- {lib_name} — {purpose}" if purpose else f"- {lib_name}")
                    else:
                        lines.append(f"- {lib}")
        lines.append("")

    _render_coding_style(ss.get("coding_style", {}), lines)
    _render_references(ss.get("references", []), lines)

    lines.append(
        "---\n\n"
        "We've finished defining the tech stack, so now you're ready to move on to "
        "creating implementation phases for your coding agent. Please click on the "
        "**Continue to Phaser** button below."
    )
    return "\n".join(lines)


def run(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Stack Advisor — guides the user through technology stack selection.

    Yields text chunks consumed by streaming.start().
    Mutates `session` to track conversation state and stack output.
    """
    if "stack_advisor_messages" not in session:
        session["stack_advisor_messages"] = []

    messages = session["stack_advisor_messages"]
    _drop_orphan_trailing_user(messages)

    if user_input is None:
        if messages:
            yield from _replay_last_assistant(messages)
            return

        # Seed with available context, then call LLM
        vision = session.get("vision_statement")
        stack = session.get("stack_statement")
        specmem = session.get("specmem")
        code_review = session.get("code_review")

        working_dir = session.get("working_dir")
        design_dir = Path(working_dir) / ".spec4" / "design" if working_dir else None
        design_ctx = _load_design_context(design_dir) if design_dir else ""
        design_block = f"{design_ctx}\n\n" if design_ctx else ""

        vision_block = (
            f"Here is my project vision statement:\n\n```json\n{json.dumps(vision, indent=2)}\n```\n\n"
            if vision
            else ""
        )
        code_review_block = (
            f"For context, here is a code review of the existing project:\n\n"
            f"```json\n{json.dumps(code_review, indent=2)}\n```\n\n"
            "**Important:** If any stack choices proposed during our conversation conflict with "
            "the existing technologies above (different language, incompatible framework, etc.), "
            "proactively warn me about the conflict, explain the implications (migration effort, "
            "incompatibility risks), and offer concrete options: keep existing tech, migrate to "
            "new choice, or a hybrid approach.\n\n"
            if code_review
            else ""
        )

        if stack:
            seed = (
                f"{vision_block}"
                f"{design_block}"
                f"{code_review_block}"
                f"I also have an existing stack spec:\n\n"
                f"```json\n{json.dumps(stack, indent=2)}\n```\n\n"
                "Please introduce yourself as StackAdvisor and briefly summarize the existing "
                "stack spec. Then ask me: would I like to **continue refining this existing "
                "stack**, or would I prefer to **start with a completely new stack** from "
                "scratch? Wait for my answer before proceeding."
            )
        elif code_review:
            seed = (
                f"{vision_block}"
                f"{design_block}"
                f"{code_review_block}"
                "Please introduce yourself as StackAdvisor. Briefly describe what you understand "
                "about the project's existing technology from the code review, then offer me two "
                "options: (1) you draft an initial stack spec based on what you found for me to "
                "review and refine, or (2) we start fresh and you guide me through the usual "
                "stack selection questions. Ask me which I'd prefer."
            )
        elif specmem:
            seed = (
                f"{vision_block}"
                f"{design_block}"
                "Here is a summary of the current project state:\n\n"
                f"{specmem}\n\n"
                "Please introduce yourself as StackAdvisor. Briefly describe what you understand "
                "about the project's technology from the summary, then offer me two options: "
                "(1) you draft an initial stack spec based on the summary for me to review and "
                "refine, or (2) we start fresh and you guide me through the usual stack selection "
                "questions. Ask me which I'd prefer."
            )
        else:
            seed = (
                f"{vision_block}"
                f"{design_block}"
                "Please introduce yourself as StackAdvisor, greet the user, and begin guiding "
                "me through the technology stack selection."
            )

        messages.append({"role": "user", "content": seed})
    else:
        messages.append({"role": "user", "content": user_input})

    tavily_api_key = session.get("tavily_api_key")
    system = tavily_mcp.build_system_prompt(SYSTEM_PROMPT, tavily_api_key)

    yield from _stream_suppressing_json(
        tavily_mcp.stream_turn(system, messages, llm_config, tavily_api_key)
    )

    stack_spec = _extract_stack_json(_last_assistant_text(messages))
    if stack_spec:
        session["stack_advisor_state"] = STATE_STACK_COMPLETE
        session["stack_statement"] = stack_spec
        display = _format_stack_as_text(stack_spec)
        messages[-1]["content"] = display
        session["_display_override"] = display
