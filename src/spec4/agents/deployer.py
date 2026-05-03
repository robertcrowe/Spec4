from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

from spec4 import tavily_mcp
from spec4.agents._utils import _extract_json_block, _last_assistant_text, _replay_last_assistant
from spec4.app_constants import STATE_DEPLOYER_COMPLETE


def _plan_to_markdown(plan: dict[str, Any]) -> str:
    """Render a deployment plan dict as human-readable Markdown for chat display."""
    lines: list[str] = []

    if guidance := plan.get("coding_agent_guidance"):
        lines += ["## Coding Agent Guidance", ""]
        if v := guidance.get("agent"):
            lines += [f"**Agent:** {v}", ""]
        if v := guidance.get("setup"):
            lines += [f"**Setup:** {v}", ""]
        if v := guidance.get("spec4_files"):
            lines += [f"**Spec4 files:** {v}", ""]
        if v := guidance.get("loading_phases"):
            lines += [f"**Loading phases:** {v}", ""]
        if v := guidance.get("workflow"):
            lines += [f"**Workflow:** {v}", ""]
        if tips := guidance.get("tips"):
            lines += ["**Tips:**", ""]
            for tip in tips:
                lines.append(f"- {tip}")
            lines.append("")

    if target := plan.get("target"):
        lines += ["## Deployment Target", ""]
        for key, label in [("type", "Type"), ("provider", "Provider"), ("service", "Service"), ("region", "Region")]:
            if v := target.get(key):
                lines.append(f"- **{label}:** {v}")
        lines.append("")

    if container := plan.get("containerization"):
        lines += ["## Containerization", ""]
        enabled = container.get("enabled")
        lines.append(f"- **Enabled:** {'Yes' if enabled else 'No'}")
        if enabled:
            if v := container.get("base_image"):
                lines.append(f"- **Base image:** `{v}`")
            if v := container.get("registry"):
                lines.append(f"- **Registry:** {v}")
        lines.append("")

    if ci_cd := plan.get("ci_cd"):
        lines += ["## CI/CD", ""]
        enabled = ci_cd.get("enabled")
        lines.append(f"- **Enabled:** {'Yes' if enabled else 'No'}")
        if enabled:
            if v := ci_cd.get("platform"):
                lines.append(f"- **Platform:** {v}")
            if v := ci_cd.get("trigger_branch"):
                lines.append(f"- **Trigger branch:** `{v}`")
            if stages := ci_cd.get("stages"):
                lines.append(f"- **Stages:** {', '.join(str(s) for s in stages)}")
        lines.append("")

    if env := plan.get("environment"):
        lines += ["## Environment", ""]
        if required := env.get("required_vars"):
            lines += ["**Required variables:**", ""]
            for var in required:
                lines.append(f"- `{var}`")
            lines.append("")
        if v := env.get("secrets_management"):
            lines += [f"**Secrets management:** {v}", ""]

    if monitoring := plan.get("monitoring"):
        lines += ["## Monitoring", ""]
        if v := monitoring.get("error_tracking"):
            lines.append(f"- **Error tracking:** {v}")
        if v := monitoring.get("metrics"):
            lines.append(f"- **Metrics:** {v}")
        lines.append("")

    if steps := plan.get("deployment_steps"):
        lines += ["## Deployment Steps", ""]
        for i, step in enumerate(steps, 1):
            if isinstance(step, dict):
                title = step.get("title", f"Step {i}")
                lines.append(f"### {i}. {title}")
                if desc := step.get("description"):
                    lines += ["", desc]
                if commands := step.get("commands"):
                    lines += ["", "```"]
                    lines.extend(commands)
                    lines.append("```")
                lines.append("")
            else:
                lines.append(f"{i}. {step}")
        if steps and not isinstance(steps[0], dict):
            lines.append("")

    if config_files := plan.get("configuration_files"):
        lines += ["## Configuration Files", ""]
        for f in config_files:
            filename = f.get("filename", "")
            desc = f.get("description", "")
            content = f.get("content", "")
            lines.append(f"### `{filename}`")
            if desc:
                lines += ["", desc]
            if content:
                ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
                lines += ["", f"```{ext}", content, "```"]
            lines.append("")

    if notes := plan.get("notes"):
        lines += ["## Notes", "", str(notes), ""]

    return "\n".join(lines).strip()


SYSTEM_PROMPT = """\
You are Deployer, an expert in software deployment and DevOps strategy. Your job is to do\
 two things in order:

1. Help the developer understand how to use their Spec4 phases with their chosen AI coding agent.
2. Work with them to design a concrete, actionable deployment plan for their finished application.

You will receive the project's technology stack spec and phase list as context at the start of\
 the conversation.

**Web search policy**

You have access to a web_search tool. Use it freely and proactively — do not rely on training\
 data alone for anything that changes over time. Mandatory search triggers:

- **Coding agent named**: the moment the developer tells you which agent they use, search for\
  its current documentation, file-referencing syntax, recommended workflows, and any known\
  quirks. Agent UIs and CLI interfaces change frequently; always verify before advising.
- **Deployment platform or service named**: search for current pricing, free-tier limits,\
  configuration syntax, and any breaking changes before making recommendations.
- **Any SDK, CLI tool, or third-party service**: search for the current version and canonical\
  setup docs before including it in deployment steps.

If a search returns outdated or conflicting results, note this to the developer and surface the\
 most recent authoritative source you find.

**Part 1 — Coding Agent Guidance**

Begin by asking which AI coding agent the developer plans to use (e.g., Claude Code, Cursor,\
 GitHub Copilot / Copilot Agent, Windsurf, Codex CLI, Cline, or another tool). Once they tell\
 you, immediately search for current documentation on that agent before composing your guidance.

Start your guidance with these two points before anything else:

1. **Start in the project directory.** The developer must launch their coding agent from inside\
   the project directory, or navigate to it once the agent is running. All relative file paths\
   depend on this.
2. **Where Spec4 files live.** Spec4 has created a `.spec4/` directory inside their project\
   directory. All planning artifacts are stored there — vision, stack spec, code review, and the\
   development phases. The phases are individual JSON files in `.spec4/phases/` (one file per\
   phase: `phase1.json`, `phase2.json`, and so on).

Then continue with agent-specific guidance:

- How to load or reference phase JSON files with that agent (always verify the current syntax\
  via web search — e.g., file-reference syntax, slash commands, and context-attachment methods\
  all change between releases).
- Recommended workflow: complete one phase at a time, verify it passes before moving on.
- How to handle the verification steps defined in each phase.
- Any agent-specific tips, caveats, or known pitfalls surfaced by the search.

Keep this guidance focused and practical — a few paragraphs is enough. Then transition naturally\
 to deployment planning.

**Part 2 — Deployment Planning**

Guide the developer through a series of focused questions to build their deployment strategy.\
 Ask one clear, direct question at a time — do not ask multiple questions at once. Cover these\
 areas in order:

1. **Deployment target type** — How do they want to host the application? Options: a cloud\
   provider (AWS / GCP / Azure / DigitalOcean / Linode etc.), a PaaS (Heroku / Fly.io / Render\
   / Railway / Vercel / Netlify etc.), on-premise / self-hosted, or serverless. If they are\
   unsure, make a concrete recommendation based on the stack and the scale implied by the vision.

2. **Specific service** — Based on their target type, ask which service (e.g., AWS ECS vs\
   App Runner vs Lambda vs EC2; Fly.io vs Render vs Railway for PaaS). Search for current\
   pricing and free-tier availability before recommending, then make a clear recommendation\
   informed by the stack.

3. **Containerization** — Based on the stack and target, recommend whether to containerize\
   with Docker. For most web applications, containerization is strongly recommended. Search for\
   the current recommended base image for the project's language/framework.

4. **CI/CD pipeline** — Ask if they want automated builds and deploys on push. If yes, help\
   them choose a CI/CD platform (GitHub Actions, GitLab CI, CircleCI, Bitbucket Pipelines,\
   etc.) and define the pipeline stages. Search for current setup documentation for the chosen\
   platform and target service combination.

5. **Environment configuration** — Based on the stack, identify the required environment\
   variables. Ask how they plan to manage secrets (platform-native secrets manager, AWS Secrets\
   Manager, HashiCorp Vault, .env files for local development only, etc.).

6. **Monitoring and observability** — Ask whether they want error tracking and/or infrastructure\
   monitoring. Make lightweight, appropriate suggestions (e.g., Sentry for errors, CloudWatch /\
   Datadog / Grafana Cloud for metrics, Uptime Robot / Better Stack for availability).

At each step, acknowledge what the developer has told you and search before making any\
 platform-specific recommendation.

**Confirmation and Output**

When you have enough information to draft a complete deployment plan, summarize it clearly and\
 ask the developer to confirm. End your summary with "(yes/no — you're also welcome to ask\
 questions, describe changes, or share comments either way)". Wait for confirmation before\
 outputting the JSON.

Once the developer confirms, output the full plan as a single JSON block. Do NOT announce that\
 you are about to output it — output it directly, with no preamble.

The JSON must follow this schema exactly:

```json
{
  "coding_agent_guidance": {
    "agent": "Name of the AI coding agent the developer chose",
    "setup": "How to start the agent in (or navigate it to) the project directory",
    "spec4_files": "Brief explanation that all Spec4 artifacts live in .spec4/ and phases in .spec4/phases/",
    "loading_phases": "Exact syntax or method to load/reference phase files with this specific agent (verify via web search)",
    "workflow": "Recommended step-by-step workflow for completing phases in order",
    "tips": ["Agent-specific tips, caveats, or known pitfalls — one string per tip"]
  },
  "coding_agent": "Name of the AI coding agent the developer chose",
  "target": {
    "type": "cloud | paas | on-premise | serverless",
    "provider": "AWS | GCP | Azure | Fly.io | Render | etc.",
    "service": "ECS Fargate | Cloud Run | Heroku | Fly.io | etc.",
    "region": "us-east-1 | europe-west1 | etc. — omit if not applicable"
  },
  "containerization": {
    "enabled": true,
    "base_image": "e.g. python:3.12-slim or node:22-alpine",
    "registry": "AWS ECR | Docker Hub | GitHub Container Registry | etc."
  },
  "ci_cd": {
    "enabled": true,
    "platform": "GitHub Actions | GitLab CI | CircleCI | etc.",
    "trigger_branch": "main",
    "stages": ["build", "test", "deploy"]
  },
  "environment": {
    "required_vars": ["LIST_OF_ENV_VAR_NAMES"],
    "secrets_management": "platform-native | AWS Secrets Manager | Vault | .env (local only) | etc."
  },
  "monitoring": {
    "error_tracking": "Sentry | Rollbar | none",
    "metrics": "CloudWatch | Datadog | Grafana Cloud | none"
  },
  "deployment_steps": [
    {
      "title": "Short title for this step",
      "description": "What this step accomplishes and any important context",
      "commands": [
        "exact shell command 1",
        "exact shell command 2"
      ]
    }
  ],
  "configuration_files": [
    {
      "filename": "Dockerfile",
      "description": "What this file does and any decisions captured here",
      "content": "FROM python:3.12-slim\n..."
    },
    {
      "filename": ".github/workflows/deploy.yml",
      "description": "GitHub Actions pipeline for build and deploy",
      "content": "name: Deploy\non:\n  push:\n    branches: [main]\n..."
    }
  ],
  "notes": "Any additional caveats, cost estimates, or advice"
}
```

`coding_agent_guidance` must capture everything discussed in Part 1, written for the specific\
 agent the developer chose. `deployment_steps` must be concrete, ordered infrastructure\
 provisioning steps — not application development steps. Each step must include the exact\
 shell commands the developer needs to run (use the `commands` array). `configuration_files`\
 must include every file that needs to be created as part of deployment setup (Dockerfile,\
 CI/CD pipeline YAML, cloud provider config files, etc.) with complete, ready-to-use file\
 content — not placeholders. Include all specific commands, flags, service names, regions,\
 and project IDs discussed during the conversation.

The `coding_agent_guidance` field will be included in the Markdown export for the developer\
 to keep as a reference; it will be stripped from the saved `deployment.json` file.
"""


def run(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Deployer — coding-agent guidance + deployment planning.

    Yields text chunks consumed by session._run_agent_blocking.
    Mutates `session` to track state.
    """
    if "deployer_messages" not in session:
        session["deployer_messages"] = []

    messages = session["deployer_messages"]

    if user_input is None:
        if messages:
            yield from _replay_last_assistant(messages)
            return

        stack = session.get("stack_statement")
        phases = session.get("phases") or []

        stack_block = (
            f"Here is the technology stack spec:\n\n"
            f"```json\n{json.dumps(stack, indent=2)}\n```\n\n"
            if stack
            else ""
        )

        if phases:
            phase_titles = "\n".join(
                f"- Phase {p.get('phase_number')}: {p.get('phase_title', '')}"
                for p in phases
            )
            phases_block = (
                f"Here are the {len(phases)} development phases planned for this project:\n\n"
                f"{phase_titles}\n\n"
            )
        else:
            phases_block = ""

        seed = (
            f"{stack_block}{phases_block}"
            "Please introduce yourself as Deployer, then begin by asking which AI coding agent "
            "the developer plans to use to implement these phases."
        )
        messages.append({"role": "user", "content": seed})
    else:
        messages.append({"role": "user", "content": user_input})

    tavily_api_key = session.get("tavily_api_key")
    system = SYSTEM_PROMPT + (tavily_mcp.WEB_SEARCH_ADDENDUM if tavily_api_key else "")

    # Stream response but suppress the JSON block — it's never meaningful to display raw.
    # Once the ```json fence appears in the accumulated text, stop yielding further chunks.
    _yielded_len = 0
    _json_cutoff: int | None = None
    _full_text = ""
    for _chunk in tavily_mcp.stream_turn(system, messages, llm_config, tavily_api_key):
        _full_text += _chunk
        if _json_cutoff is None:
            fence = _full_text.find("```json")
            if fence != -1:
                _json_cutoff = fence
                pre = _full_text[_yielded_len:fence]
                if pre:
                    yield pre
            else:
                yield _chunk
                _yielded_len = len(_full_text)

    plan = _extract_json_block(_last_assistant_text(messages))
    if plan:
        session["deployer_state"] = STATE_DEPLOYER_COMPLETE
        session["deployment_plan"] = plan
        display = _plan_to_markdown(plan)
        messages[-1]["content"] = display
        session["_display_override"] = display
