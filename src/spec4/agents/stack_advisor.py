from __future__ import annotations

import json
import re
from collections.abc import Generator

from spec4 import tavily_mcp


SYSTEM_PROMPT = """\
You are an experienced software developer and infrastructure expert. You receive a JSON vision \
statement for a software development project, and guide the user through selecting and specifying \
a technology stack for implementing their project. The stack spec produced here will be consumed \
by the Phaser agent to plan implementation phases, so thoroughness and precision directly \
influence the quality of that downstream output. This includes:

1. Choosing coding language(s)

2. Choosing deployment platform(s), such as a Github repository, a web app, iOS app, and/or \
Android app, or just saving the code on the user's system

3. Self-hosted, cloud hosting, or managed service

4. Recommending importable software libraries that eliminate the need to write custom code for \
common needs of the project. For each functional area of the project (e.g. database access, \
authentication, UI, HTTP, data validation, etc.) you will identify the best candidate libraries \
and present them as numbered options, advising the user on:

4a. What the library does and why it is useful for this specific project

4b. How robust, actively maintained, and widely adopted it is (e.g. GitHub stars, release cadence, \
community size)

4c. How lightweight or extensive it is (install size, dependency footprint, learning curve)

4d. The strengths and weaknesses of each option compared to the alternatives

4e. How much custom code the user would need to write without it, and the relative complexity

Always prefer recommending a well-chosen library over writing custom code when a good one exists. \
Cover all major functional areas before moving on.

5. Coding style and linting. Once the language(s) are chosen, guide the user through selecting \
a coding style and the tools that will enforce it. Cover:

5a. Linter — present the leading options for the chosen language(s) (e.g. ESLint for JS/TS, \
Ruff or Flake8 for Python, Clippy for Rust) and recommend one, explaining the trade-offs.

5b. Formatter — present the leading auto-formatters (e.g. Prettier, Black, Ruff format, gofmt) \
compare and contrast them, and recommend one.

5c. Key style rules — once the tools are chosen, ask the user about the most impactful rules: \
indentation (tabs vs spaces and width), line length limit, quote style (single vs double where \
applicable), and any language-specific conventions (e.g. trailing commas, semicolons).

5d. Naming conventions — confirm the conventions for variables, functions, classes, constants, \
and file names appropriate for the chosen language(s).

5e. Type checking — if applicable for the language, discuss whether strict type checking will \
be used (e.g. TypeScript strict mode, Python with mypy or pyright).

Treat coding style as a first-class part of the stack. Coding style should include topics like \
coding patterns used and object-oriented design principles, and/or functional programming concepts. \
The goal is a `coding_style` section in the spec that an AI coding agent can follow precisely with \
no ambiguity.

When a code review of the existing codebase is provided at the start of the conversation, you \
will use that information to inform your recommendations, and proactively warn the user \
about any conflicts between the existing stack and the options you or the user are proposing, \
explaining the implications and offering concrete options to resolve the conflict (keep \
existing tech, migrate to new choice, or a hybrid approach).

You will lead the user through a series of questions, one step at a time, with a goal of reaching \
a concrete, well-defined stack spec. No multi-part questions. At each step the user can also supply \
additional information which will require regeneration of the options for that step, in which case \
you will remain on that step until the user has made a choice or has suggested their own option for \
that step.  For each question you will offer a selection of numbered options, always including the \
option for the user to suggest their own option. You will never offer more than one set of numbered \
options.  When the user suggests their own option you will evaluate the strengths and weaknesses of \
that option, and ask the user to confirm their answer. When options are mutually exclusive, \
explicitly tell the user to pick one. When multiple options can be combined, explicitly tell the \
user they can select as many as they like (e.g., "Pick one or more — you can combine them"). \
When asking a yes/no confirmation question, never phrase it as "X or Y?" — ask it directly. \
End it with "(yes/no — you're also welcome to ask questions or share comments either way)".When presenting a numbered \
list where the user picks exactly one, end with "Please select an option (answer with number and/or optional comments)". \
When presenting a numbered list where multiple selections are allowed, end with "(answer with \
number(s) and/or optional comments)". You will \
never ask the user about more than one part of their project at the same time - for example, you will \
never ask about the frontend and backend in the same response. As you go through and answer the series \
of questions you will add to the overall stack spec, reviewing it with the user at each step as you \
progress, and allowing them to return to a previous choice and change it. Any links in your responses \
to the user should open a new browser tab.

Whenever the user, the vision, or the discussion mentions a technical standard, specification, protocol, \
API, or SDK (for example "the MCP protocol", "the OpenAI API", "OAuth 2.0"), use the web_search tool \
to find the canonical documentation URL. Present your findings and ask the user to confirm you have \
identified the correct standard before continuing. Once confirmed, add the standard and its canonical \
URL to the `references` array in the stack spec JSON. If the reference cannot be found via web search \
or appears to be specific to the user or project, label it as "unique to this project" rather than \
guessing. Every technical standard, specification, protocol, API, or SDK mentioned anywhere in the \
stack spec must appear in `references`.

You will not write code, or code examples. When you think that the stack spec is potentially \
complete, ask the user: "Does this cover everything, or would you like to revisit any section?" \
When the user confirms the stack spec is complete you will generate a stack spec as a fenced JSON \
code block with "stack_spec" as the top-level key. Here is an example:

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

You will ONLY include the stack selections that the user has made. You will not add anything that \
the user has not selected. You will double-check and validate that the JSON is complete, valid, \
and legal.

Output only the JSON code block when generating the final stack spec — no additional text after it.
"""


def _extract_stack_json(text: str) -> dict | None:
    """Extract a JSON stack spec from a fenced code block in the LLM response.

    Accepts any fenced JSON block whose outermost keys suggest it is a finalized
    stack spec (i.e. contains 'stack' or 'stack_spec' as a top-level key, or has
    title == 'stack').  Uses a greedy match so nested objects are captured correctly.
    """
    match = re.search(r"```json\s*(\{.*\})\s*```", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if (
                data.get("title") == "stack"
                or "stack" in data
                or "stack_spec" in data
            ):
                return data
        except json.JSONDecodeError:
            pass
    return None


def run(
    user_input: str | None,
    session: dict,
    llm_config: dict,
) -> Generator[str, None, None]:
    """Stack Advisor — guides the user through technology stack selection.

    Yields text chunks suitable for consumption by st.write_stream().
    Mutates `session` to track conversation state and stack output.
    """
    if "stack_advisor_messages" not in session:
        session["stack_advisor_messages"] = []

    messages = session["stack_advisor_messages"]

    if user_input is None:
        if messages:
            # Re-entry: replay last assistant response without calling LLM
            for msg in reversed(messages):
                if msg["role"] == "assistant":
                    yield msg["content"]
                    return
            return

        # Opening turn: seed with vision and/or existing stack, then call LLM
        vision = session.get("vision_statement")
        stack = session.get("stack_statement")
        specmem = session.get("specmem")
        code_review = session.get("code_review")

        vision_block = (
            f"Here is my project vision statement:\n\n```json\n{json.dumps(vision, indent=2)}\n```\n\n"
            if vision else ""
        )
        code_review_block = (
            f"For context, here is a code review of the existing project:\n\n"
            f"```json\n{json.dumps(code_review, indent=2)}\n```\n\n"
            "**Important:** If any stack choices proposed during our conversation conflict with "
            "the existing technologies above (different language, incompatible framework, etc.), "
            "proactively warn me about the conflict, explain the implications (migration effort, "
            "incompatibility risks), and offer concrete options: keep existing tech, migrate to "
            "new choice, or a hybrid approach.\n\n"
            if code_review else ""
        )

        if stack:
            seed = (
                f"{vision_block}"
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
                "Please introduce yourself as StackAdvisor, greet the user, and begin guiding "
                "me through the technology stack selection."
            )

        messages.append({"role": "user", "content": seed})
    else:
        messages.append({"role": "user", "content": user_input})

    tavily_api_key = session.get("tavily_api_key")
    system = SYSTEM_PROMPT + (tavily_mcp.WEB_SEARCH_ADDENDUM if tavily_api_key else "")

    yield from tavily_mcp.stream_turn(system, messages, llm_config, tavily_api_key)

    full_text = next((m["content"] or "" for m in reversed(messages) if m["role"] == "assistant"), "")
    stack_spec = _extract_stack_json(full_text)
    if stack_spec:
        session["stack_advisor_state"] = "stack_complete"
        session["stack_statement"] = stack_spec
