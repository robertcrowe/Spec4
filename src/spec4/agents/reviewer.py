from __future__ import annotations

import pathlib
from collections.abc import Generator
from typing import Any

from spec4 import tavily_mcp
from spec4.agents._utils import (
    _extract_json_block,
    _last_assistant_text,
    _replay_last_assistant,
)
from spec4.app_constants import STATE_REVIEW_COMPLETE


_SKIP_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "venv",
    ".env",
    "env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    ".cargo",
    ".spec4",
}

_MANIFEST_FILES = {
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "requirements-dev.txt",
    "Pipfile",
    "package.json",
    "package-lock.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".eslintrc",
    ".eslintrc.json",
    ".eslintrc.js",
    ".eslintrc.yaml",
    ".prettierrc",
    ".prettierrc.json",
    "tsconfig.json",
    "babel.config.js",
    "ruff.toml",
    ".ruff.toml",
    "mypy.ini",
    ".mypy.ini",
    "tox.ini",
    ".flake8",
    "pylintrc",
    ".pylintrc",
    "README.md",
    "README.rst",
    "README.txt",
}

_MAX_TREE_FILES = 150
_MAX_MANIFEST_CHARS = 10_000
_MAX_MANIFEST_FILE_CHARS = 3_000
_MAX_PRIORITY_SOURCE_FILES = 8
_MAX_SOURCE_SAMPLE_CHARS = 8_000
_MAX_SOURCE_SAMPLE_LINES = 80

_SOURCE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".swift",
    ".cs",
    ".cpp",
    ".c",
    ".h",
    ".rb",
    ".php",
    ".scala",
    ".r",
    ".R",
    ".lua",
    ".ex",
    ".exs",
}


def _gather_project_context(working_dir: str) -> str:
    root = pathlib.Path(working_dir)
    lines: list[str] = [f"## Project Directory: `{root}`\n"]

    all_files: list[pathlib.Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        all_files.append(path)

    if not all_files:
        lines.append("The directory appears to be empty (no non-hidden files found).\n")
        return "\n".join(lines)

    lines.append("### File Tree\n```")
    for f in all_files[:_MAX_TREE_FILES]:
        lines.append(str(f.relative_to(root)))
    if len(all_files) > _MAX_TREE_FILES:
        lines.append(
            f"... and {len(all_files) - _MAX_TREE_FILES} more files (truncated)"
        )
    lines.append("```\n")

    lines.append("### Config and Manifest Files\n")
    manifest_chars = 0
    for f in all_files:
        if f.name in _MANIFEST_FILES and manifest_chars < _MAX_MANIFEST_CHARS:
            try:
                content = f.read_text(errors="replace")[:_MAX_MANIFEST_FILE_CHARS]
                lines.append(f"#### `{f.relative_to(root)}`\n```\n{content}\n```\n")
                manifest_chars += len(content)
            except OSError:
                pass

    lines.append("### Source File Samples\n")
    source_files = [f for f in all_files if f.suffix in _SOURCE_EXTENSIONS]

    def _is_test(p: pathlib.Path) -> bool:
        parts = [x.lower() for x in p.relative_to(root).parts]
        return any(x in ("test", "tests", "spec", "specs") for x in parts)

    priority_files = [f for f in source_files if not _is_test(f)][
        :_MAX_PRIORITY_SOURCE_FILES
    ]
    source_chars = 0
    for f in priority_files:
        if source_chars >= _MAX_SOURCE_SAMPLE_CHARS:
            break
        try:
            content = f.read_text(errors="replace")
            sample_lines = content.splitlines()[:_MAX_SOURCE_SAMPLE_LINES]
            sample = "\n".join(sample_lines)
            lines.append(
                f"#### `{f.relative_to(root)}` (first {len(sample_lines)} lines)\n"
                f"```\n{sample}\n```\n"
            )
            source_chars += len(sample)
        except OSError:
            pass

    return "\n".join(lines)


SYSTEM_PROMPT = """\
You are an expert software architect and code reviewer. You have been given the file listing and\
selected contents of a software project directory. Your job is to analyze it and produce a\
structured code review for Spec4, a project planning tool. This review will be consumed by the\
StackAdvisor agent to guide technology stack selection and flag conflicts with any proposed changes,\
so the level of detail in each section directly influences the quality of that downstream guidance.

**Empty directory:** If the directory contains no files, briefly tell the user that the\
directory appears to be empty and that you are recording a minimal code review to reflect\
that (one or two sentences), then immediately output the minimal code review JSON \
(see format below, with `"is_software_project": false` and a note that the directory is\
empty). Do not ask any follow-up questions.

**Scope:** Your job is strictly limited to describing what already exists in the project\
directory. You will never ask the user about technology choices, language preferences, \
frameworks, hosting, deployment, libraries, or any other implementation decision — those\
topics are handled by the StackAdvisor agent. If the user volunteers such information, \
thank them and let them know those choices will be explored with StackAdvisor.

Cover these sections IN ORDER, one at a time:
1. **Project Type** — Is this a software project? If so, what kind (web app, CLI, library,\
   API, data pipeline, etc.)? If it is not a software project, say so clearly and note what\
   you found instead.
2. **Architecture** — Describe the high-level architecture (e.g., MVC, layered, microservices,\
   monolith, serverless, event-driven, etc.)
3. **Languages and Frameworks** — What programming languages and frameworks are in use?
4. **Build System and Dependencies** — What build tool and package manager is used? List the\
   key dependencies and their purpose.
5. **Coding Style** — What indentation, naming conventions, linter, and formatter are in use?\
   Look for config files (ruff.toml, .eslintrc, pyproject.toml [tool.ruff], etc.) and infer\
   from the source samples when config files are absent.
6. **Notable Observations** — Any other important characteristics (e.g., test coverage, CI\
   setup, notable patterns, areas that will affect new development).

For each section, present your findings clearly, then ask the user to confirm or correct them\
before moving to the next section. Confirmation questions must never be phrased as "X or Y?" — ask them directly. End them\
with "(yes/no — you're also welcome to ask questions or share comments either way)". When you\
offer numbered options, end with "Please select an option (answer with number and/or optional comments)". Update your\
understanding if the user provides corrections before moving on. Any links in your responses\
should open a new browser tab.

After all sections are confirmed, ask the user: "Does this cover everything, or would you like\
to revisit any section?" When the user confirms the review is complete, output ONLY a fenced\
JSON code block with this structure (omit fields that are not applicable):

```json
{
  "code_review": {
    "is_software_project": true,
    "project_type": "web application",
    "architecture": "layered (presentation / business logic / data)",
    "languages": ["Python"],
    "frameworks": ["FastAPI", "Streamlit"],
    "build_system": "uv / pyproject.toml",
    "dependencies": [
      {"name": "streamlit", "purpose": "UI framework"},
      {"name": "litellm", "purpose": "LLM provider abstraction"}
    ],
    "coding_style": {
      "linter": "ruff",
      "formatter": "ruff format",
      "type_checker": "none detected",
      "indentation": "4 spaces",
      "quotes": "double",
      "line_length": 88,
      "naming_conventions": {
        "functions": "snake_case",
        "classes": "PascalCase",
        "variables": "snake_case",
        "constants": "UPPER_SNAKE_CASE"
      }
    },
    "notes": ["test coverage is minimal", "no CI configuration found"]
  }
}
```

Output only the JSON code block when generating the final code review — no additional text after it.
"""


def _extract_review_json(text: str) -> dict[str, Any] | None:
    data = _extract_json_block(text)
    return data if data is not None and "code_review" in data else None


def run(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Reviewer — analyzes the project directory and creates a structured code review.

    Yields text chunks consumed by session._run_agent_blocking.
    Mutates `session` to track conversation state and review output.
    """
    if "reviewer_messages" not in session:
        session["reviewer_messages"] = []

    msgs = session["reviewer_messages"]

    if user_input is None:
        if msgs:
            # Re-entry: replay last assistant response without calling LLM
            yield from _replay_last_assistant(msgs)
            return

        working_dir = session.get("working_dir")
        if not working_dir:
            yield (
                "I'm the **Reviewer**. I analyze your project directory to understand "
                "the existing codebase.\n\n"
                "⚠️ No project directory has been selected. Please go back and select "
                "a working directory first."
            )
            return

        context = _gather_project_context(working_dir)
        msgs.append(
            {
                "role": "user",
                "content": (
                    "Please introduce yourself as Reviewer, then analyze this project "
                    "directory section by section as instructed.\n\n"
                    f"{context}"
                ),
            }
        )
    else:
        msgs.append({"role": "user", "content": user_input})

    tavily_api_key = session.get("tavily_api_key")
    system = SYSTEM_PROMPT + (tavily_mcp.WEB_SEARCH_ADDENDUM if tavily_api_key else "")

    yield from tavily_mcp.stream_turn(system, msgs, llm_config, tavily_api_key)

    review = _extract_review_json(_last_assistant_text(msgs))
    if review:
        session["reviewer_state"] = STATE_REVIEW_COMPLETE
        session["code_review"] = review
