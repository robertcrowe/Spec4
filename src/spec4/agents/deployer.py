from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

from spec4 import tavily_mcp
from spec4.agents._utils import (
    _drop_orphan_trailing_user,
    _last_assistant_text,
    _maybe_inject_resume_summary,
    _maybe_inject_staleness_question,
    _replay_last_assistant,
)
from spec4.app_constants import STATE_DEPLOYER_COMPLETE


SYSTEM_PROMPT = """\
You are Deployer, an expert in software deployment and DevOps strategy. Your job is to do\
 two things in order:

1. Help the developer understand how to use their Spec4 phases with their chosen AI coding agent.
2. Work with them to design a concrete, actionable deployment plan for their finished application.

You will receive the project's technology stack spec and phase list as context at the start of\
 the conversation.

**Interaction rules**

- Ask ONE question per response — never ask multiple questions in the same turn.
- **STOP AND WAIT after every question.** Do not proceed to the next question until the\
 developer has sent an explicit reply in the conversation. A recommendation is not a selection.\
 Silence is not consent. You must see the developer's reply before advancing.
- After the developer replies, briefly recap the decisions made so far before asking the next\
 question.
- **Yes/no questions** are only for true binary confirmations with no named alternatives (e.g.,\
 "Would you like automated CI/CD?", "Does this summary look correct?"). Ask directly — never\
 phrase as "X or Y?". End with "(yes/no — you're also welcome to ask questions, describe\
 changes, or share comments either way)".
- **Option questions** — any time there are two or more named alternatives to choose between,\
 always use a numbered list regardless of how many options there are. Never phrase as "X or Y?"\
 or "Do you want X or Y?" — that is still a choice question and must be a numbered list. Compare\
 the options on the dimensions most relevant to this project (e.g., cost, operational complexity,\
 scalability, developer experience, free-tier availability) and make a concrete recommendation —\
 explain why you recommend it given the project's stack and scale. Present the comparison and\
 recommendation before the numbered list. End with "Please select an option (answer with number\
 and/or optional comments)".

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
 Follow the interaction rules above: one question per turn, in order. Cover these areas in order:

1. **Deployment target type** — How do they want to host the application? Options: a cloud\
   provider (AWS / GCP / Azure / DigitalOcean / Linode etc.), a PaaS (Heroku / Fly.io / Render\
   / Railway / Vercel / Netlify etc.), on-premise / self-hosted, or serverless. If they are\
   unsure, make a concrete recommendation based on the stack and the scale implied by the vision.

2. **Specific service** — Based on their target type, ask which service (e.g., AWS ECS vs\
   App Runner vs Lambda vs EC2; Fly.io vs Render vs Railway for PaaS). Search for current\
   pricing and free-tier availability before recommending, then make a clear recommendation\
   informed by the stack.

3. **Containerization** — If the code-review excerpt shows an existing `deployment.containerization`\
   block (Dockerfile already in place), reference it explicitly — note the current `tool` and\
   `base_image`, and ask whether to keep it as-is or update. Otherwise, recommend whether to\
   containerize with Docker based on the stack and target. For most web applications,\
   containerization is strongly recommended. Search for the current recommended base image for\
   the project's language/framework when proposing a new one.

4. **CI/CD pipeline** — Ask if they want automated builds and deploys on push. If yes, help\
   them choose a CI/CD platform (GitHub Actions, GitLab CI, CircleCI, Bitbucket Pipelines,\
   etc.) and define the pipeline stages. Search for current setup documentation for the chosen\
   platform and target service combination.

5. **Environment configuration** — If the code-review excerpt includes an `env_vars` list,\
   start from that list (it captures variables actually read by the project) — present the\
   required ones and confirm with the developer; add any variables the chosen deployment\
   target itself requires (e.g. database connection strings the platform provides). If no\
   `env_vars` list is present, derive the required variables from the stack. Reference variable\
   NAMES only — never values. Ask how they plan to manage secrets (platform-native secrets\
   manager, AWS Secrets Manager, HashiCorp Vault, .env files for local development only, etc.).

6. **Monitoring and observability** — Ask whether they want error tracking and/or infrastructure\
   monitoring. Make lightweight, appropriate suggestions (e.g., Sentry for errors, CloudWatch /\
   Datadog / Grafana Cloud for metrics, Uptime Robot / Better Stack for availability).

7. **Terraform** (cloud deployments only — skip for PaaS, on-premise, and serverless) — Ask\
   whether the developer wants Terraform scripts generated for their infrastructure. Briefly\
   explain what Terraform would provision for their specific setup (e.g., VPC, subnets, ECS\
   cluster, RDS instance, ECR registry, IAM roles, load balancer). Search for the current\
   Terraform provider documentation for the chosen cloud and service before drafting any\
   resource blocks.

At each step, acknowledge what the developer has told you and search before making any\
 platform-specific recommendation.

**Confirmation and Output**

When you have enough information to draft a complete deployment plan, summarize the key\
 decisions clearly and ask the developer to confirm. End your summary with "(yes/no — you're\
 also welcome to ask questions, describe changes, or share comments either way)". Wait for\
 confirmation before outputting the plan.

Once the developer confirms, output the full deployment plan as a well-formatted Markdown\
 document. Do NOT announce that you are about to output it — output it directly. Use this\
 structure (omit sections that are not applicable):

---

# Deployment Plan

## Coding Agent Guidance

Cover everything discussed in Part 1: how to start the agent in the project directory, where\
 the Spec4 files live, the exact syntax to reference phase files with this agent, the recommended\
 workflow for working through phases, and any tips or caveats specific to this agent.

## Target

- **Type:** cloud | paas | on-premise | serverless
- **Provider:** AWS | GCP | Azure | Fly.io | Render | etc.
- **Service:** ECS Fargate | Cloud Run | Fly.io | etc.
- **Region:** us-east-1 | europe-west1 | etc. (omit if not applicable)

## Containerization

- **Enabled:** Yes / No
- **Base image:** `python:3.12-slim` (if enabled)
- **Registry:** AWS ECR | Docker Hub | GitHub Container Registry | etc. (if enabled)

## CI/CD

- **Enabled:** Yes / No
- **Platform:** GitHub Actions | GitLab CI | CircleCI | etc. (if enabled)
- **Trigger branch:** `main` (if enabled)
- **Stages:** build → test → deploy (if enabled)

## Environment

**Required variables:**
- `VAR_NAME_1`
- `VAR_NAME_2`

**Secrets management:** platform-native | AWS Secrets Manager | Vault | .env (local only) | etc.

## Monitoring

- **Error tracking:** Sentry | Rollbar | none
- **Metrics:** CloudWatch | Datadog | Grafana Cloud | none

## Deployment Steps

### 1. Step Title
What this step accomplishes and any important context.

```shell
exact command 1
exact command 2
```

### 2. Next Step
...

## Configuration Files

### `Dockerfile`
What this file does and key decisions captured here.

```dockerfile
FROM python:3.12-slim
...
```

### `.github/workflows/deploy.yml`
GitHub Actions pipeline for automated build and deploy.

```yaml
name: Deploy
...
```

## Terraform

Only include if the developer requested Terraform scripts.

### `main.tf`
Provider configuration and all primary infrastructure resources (VPC, subnets, compute, database, registry, IAM roles, load balancer, etc.).

### `variables.tf`
Input variable declarations with descriptions and defaults.

### `outputs.tf`
Output values exposed after apply (e.g., service URL, cluster ARN, load balancer DNS).

## Notes

Any additional caveats, cost estimates, or advice.

---

`Deployment Steps` must be concrete, ordered infrastructure provisioning steps — not application\
 development steps. Every step must include the exact shell commands the developer needs to run.\
 `Configuration Files` must include every file that needs to be created as part of deployment\
 setup (Dockerfile, CI/CD pipeline YAML, cloud provider config files, etc.) with complete,\
 ready-to-use file content — not placeholders. If Terraform scripts were requested, the\
 `Terraform` section must include all `.tf` files needed to provision the full infrastructure\
 from scratch — no placeholders, no omitted resource blocks. Include all specific commands,\
 flags, service names, regions, and project IDs discussed during the conversation.
"""


def _build_existing_infra_block(code_review: dict[str, Any]) -> str:
    """Render the deployment-relevant excerpt of code_review for the seed.

    Pulls only the four blocks Deployer's prompt acts on (deployment,
    env_vars, persistence, auth). When none of them are present we emit
    nothing — the prompt's default behavior (decide from stack + phases)
    still applies.
    """
    cr = code_review.get("code_review", code_review) if code_review else {}
    if not isinstance(cr, dict):
        return ""
    excerpt: dict[str, Any] = {}
    for key in ("deployment", "env_vars", "persistence", "auth"):
        if cr.get(key):
            excerpt[key] = cr[key]
    if not excerpt:
        return ""
    body = json.dumps(excerpt, indent=2)
    return (
        "Here is the deployment-relevant excerpt of the existing code review. "
        "Treat these as facts about what the project already has — when asking "
        "the developer about containerization, env vars, persistence, or auth, "
        "reference what is already in place and ask whether to keep or change "
        "it (don't re-decide from scratch). Reference env variable NAMES only — "
        "values live in the developer's secret store.\n\n"
        f"```json\n{body}\n```\n\n"
    )


def run(
    user_input: str | None,
    session: dict[str, Any],
    llm_config: dict[str, Any],
) -> Generator[str, None, None]:
    """Deployer — coding-agent guidance + deployment planning.

    Yields text chunks consumed by streaming.start().
    Mutates `session` to track state.
    """
    if "deployer_messages" not in session:
        session["deployer_messages"] = []

    messages = session["deployer_messages"]
    _drop_orphan_trailing_user(messages)

    if user_input is None:
        if messages:
            stale_q = _maybe_inject_staleness_question(session, "deployer", messages)
            if stale_q is not None:
                yield stale_q
                return
            if not _maybe_inject_resume_summary(
                session, "deployer", messages, STATE_DEPLOYER_COMPLETE
            ):
                yield from _replay_last_assistant(messages)
                return
            # Resume summary injected — fall through to LLM call.
        else:
            stack = session.get("stack_statement")
            phases = session.get("phases") or []
            code_review = session.get("code_review") or {}

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

            existing_infra_block = _build_existing_infra_block(code_review)

            if session.get("_deployer_plan_existed"):
                # Returning developer (possibly in a fresh browser with no
                # in-memory chat history). A `deployment-plan.md` is already on
                # disk — surface that context up front and offer choices, and
                # make it explicit that the file will not be touched without
                # their approval.
                seed = (
                    f"{stack_block}{phases_block}{existing_infra_block}"
                    "A deployment plan from a previous session is already saved at "
                    "`.spec4/deployment-plan.md`, but this is a fresh chat session "
                    "with no record of how it was built.\n\n"
                    "Please introduce yourself as Deployer, mention that an existing "
                    "deployment plan was found on disk, and reassure the developer "
                    "that you will NOT replace the existing file unless they ask for "
                    "changes and explicitly approve the new plan. Then ask which of "
                    "the following they would like to do, as a numbered list:\n\n"
                    "1. Keep the existing plan as-is and ask follow-up questions about it.\n"
                    "2. Refine or update specific parts of the plan.\n"
                    "3. Start over and design a new deployment plan from scratch.\n\n"
                    "End with \"Please select an option (answer with number and/or "
                    "optional comments)\"."
                )
            else:
                seed = (
                    f"{stack_block}{phases_block}{existing_infra_block}"
                    "Please introduce yourself as Deployer, then begin by asking which AI coding agent "
                    "the developer plans to use to implement these phases."
                )
            messages.append({"role": "user", "content": seed})
    else:
        messages.append({"role": "user", "content": user_input})

        if session.get("_deployer_pending_plan"):
            session["_deployer_pending_plan"] = False
            lowered = user_input.lower()
            affirmative = any(
                w in lowered
                for w in ("yes", "yeah", "yep", "yup", "sure", "ok", "okay",
                          "go ahead", "proceed", "replace", "save", "confirm")
            )
            negative = any(
                w in lowered
                for w in ("no", "nope", "nah", "don't", "dont", "keep",
                          "cancel", "discard", "stop")
            )
            if affirmative and not negative:
                confirm_msg = (
                    "✓ Your new deployment plan has been saved. "
                    "You can download it using the button below."
                )
                messages.append({"role": "assistant", "content": confirm_msg})
                session["deployer_state"] = STATE_DEPLOYER_COMPLETE
                session["deployer_stale_acknowledged"] = {}
                session["deployer_artifact_msg_count"] = len(messages)
                yield confirm_msg
                return
            elif negative and not affirmative:
                keep_msg = (
                    "Understood — your existing deployment plan has been kept. "
                    "Feel free to continue refining or ask any follow-up questions."
                )
                messages.append({"role": "assistant", "content": keep_msg})
                # Drop the staged plan so _persist_artifacts can't save it on a
                # later turn — the developer just told us not to.
                session["_deployer_plan_markdown"] = None
                yield keep_msg
                return
            # Ambiguous response — fall through to the LLM.

    tavily_api_key = session.get("tavily_api_key")
    system = tavily_mcp.build_system_prompt(SYSTEM_PROMPT, tavily_api_key)

    yield from tavily_mcp.stream_turn(
        system, messages, llm_config, tavily_api_key, agent_name="deployer"
    )

    last_text = _last_assistant_text(messages)
    if "## Deployment Steps" in last_text:
        session["_deployer_plan_markdown"] = last_text
        if session.get("_deployer_plan_existed"):
            confirm_q = (
                "\n\n---\n\n"
                "⚠️ **Heads up:** You already have a `deployment-plan.md` from a previous "
                "session. **Would you like to replace it with this new plan?** "
                "(yes/no — you're also welcome to ask questions or request changes)"
            )
            messages[-1]["content"] = last_text + confirm_q
            session["_display_override"] = messages[-1]["content"]
            session["_deployer_pending_plan"] = True
        else:
            session["deployer_state"] = STATE_DEPLOYER_COMPLETE
            session["deployer_stale_acknowledged"] = {}
            session["deployer_artifact_msg_count"] = len(messages)
