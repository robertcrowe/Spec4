from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

from spec4 import project_manager, llm, websearch
from spec4.agents._utils import (
    _ai_features_for_deployer,
    _drop_orphan_or_route_to_fresh_start,
    _last_assistant_text,
    _maybe_inject_resume_summary,
    _maybe_inject_staleness_question,
    _nfr_goals_for_deployer,
    _phases_for_deployer,
    _replay_last_assistant,
    _stack_for_deployer,
    _stream_counting,
)
from spec4.app_constants import STATE_DEPLOYER_COMPLETE


SYSTEM_PROMPT = """\
You are Deployer, an expert in software deployment and DevOps strategy. Your job is to do\
 two things in order:

1. Help the developer understand how to use their Spec4 phases with their chosen AI coding agent.
2. Work with them to design a concrete, actionable deployment plan for their finished application.

You will receive the project's technology stack spec and phase list as context at the start of\
 the conversation. Spec4 itself generated every planning artifact and already wrote it to the\
 developer's working directory before this conversation began — the `.spec4/` directory and all\
 of the phase files listed below already exist on disk. Treat their existence as a given: never\
 ask the developer whether the files exist, and never offer to create, generate, or regenerate\
 them, because Spec4 already produced them. You hold the stack spec and the phase list directly\
 in this conversation, so you do not need to open the on-disk files to do your job — and you must\
 never tell the developer that you cannot see their file system or cannot read the phase files.\
 Your Part 1 role is to explain how the developer points their coding agent at files that are\
 already in place, not to inspect those files or question whether they are present.

**Revision mode**

When the planning context states this is a revision of an already-implemented,\
 already-deployed project, do NOT re-derive the whole deployment plan. If a prior\
 deployment plan is provided, treat it as the established baseline: the provider,\
 service, containerization, CI/CD, environment, and infrastructure it describes are\
 already provisioned and in place. Scope your work to what this revision's new or\
 changed surface (named in the revision note) requires — typically new environment\
 variables or API keys, any new infrastructure for the new surface, and observability\
 for newly introduced AI features. Still give Part 1 coding-agent guidance for this\
 revision's phase files, but in Part 2 update the existing plan incrementally rather\
 than re-asking settled decisions. If no prior deployment plan is provided (the\
 previous round did not produce one), build a plan for this revision's surface from\
 the stack and phases as usual. The final document still uses the full output\
 structure below, carrying the established sections forward unchanged and revising\
 only what this revision touches.

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
   directory. Every planning artifact is version-scoped under `.spec4/v{N}/`, where `{N}` is the\
   current round's version (shown in the phases list below). Use these paths verbatim, do not\
   invent variants:
   - `.spec4/v{N}/vision.json` — the project vision statement
   - `.spec4/v{N}/stack.json` — the technology stack spec
   - `.spec4/v{N}/code_review.json` — the code review (brownfield projects only; may be absent)
   - `.spec4/v{N}/phases/phase1.md`, `.spec4/v{N}/phases/phase2.md`, … — one Markdown file per development\
     phase in the current set (highest version `v{N}`), each pairing a JSON frontmatter block (full structured payload) with a prose body the\
     coding agent reads directly
   - `.spec4/v{N}/design/mock.html` — finalized UI design mock (only when Designer was used; may be\
     absent)

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

The deployment signals above record decisions already made with the developer — do not reopen\
 them. Every entry marked `optional` or `deferred` is roadmap: note it in `Notes` so it is not\
 lost, and do not provision, configure, or build it. Each target's `exposure` is literal\
 configuration — `transport` is the protocol that target accepts and `cors` is the policy to\
 apply, not advice to weigh. Read the absences as decisions too: when no authentication is\
 declared the project has no user accounts, so do not provision an identity provider, plan auth\
 secrets, or ask the developer to choose one; when no external integrations are declared there\
 are no third-party services to configure. Asking about something the context has already\
 answered wastes the developer's turn.

Before you start, read the project's non-functional goals in the context above. Each is marked\
 with whether a stack component claims to satisfy it. They are requirements on this deployment,\
 not commentary about it, so let them shape the decisions below rather than treating them as a\
 separate topic.

Some are settled by deployment and nothing else. Latency and responsiveness goals bear on region\
 choice, CDN and caching, and whether instances stay warm. Working offline bears on static\
 hosting, the service worker, and cache headers. Updating without interrupting users bears on\
 zero-downtime deploys — blue-green or rolling. Scale and concurrency goals bear on autoscaling\
 and connection pooling. Durability goals bear on backup policy and retention. Confidentiality\
 goals bear on network isolation, secrets handling, and tenant separation. Where a goal bears on\
 a decision, say so in the section where you record that decision: a region chosen because of a\
 latency goal should say that is why.

Others are not yours to satisfy. Answer correctness, citation verifiability, refusal behaviour,\
 tone, and coherence come from the code the agent writes, not from infrastructure. Recognise\
 those and leave them to it.

Be honest about which is which. Never write that infrastructure satisfies a goal it does not —\
 no hosting choice makes a citation verifiable. In `Notes`, briefly record which goals this\
 deployment addresses and which belong to the coding agent, so that none is silently dropped. A\
 goal that no stack component claims may still be deployment-relevant: address it on its own\
 terms and say the stack did not claim it.

1. **Deployment target type** — The stack declares the surfaces this project deploys, and each\
   needs its own hosting decision: a static frontend and an API are two surfaces, not one. Ask\
   how they want to host them. Options: a cloud\
   provider (AWS / GCP / Azure / DigitalOcean / Linode etc.), a PaaS (Heroku / Fly.io / Render\
   / Railway / Vercel / Netlify etc.), on-premise / self-hosted, or serverless. Carry each\
   surface's declared hosting, build, and `exposure` into its own Target block. If they are\
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

5. **Environment configuration** — Assemble the required variables from every source in context\
   before you ask anything, then present the assembled list for confirmation rather than asking\
   cold. The sources: the code-review excerpt's `env_vars` list when present, which captures\
   what the deployed project actually reads, so start there; the union of every phase's\
   `tech_stack_spec.configurations`, which names what the phases about to be built will\
   configure; each declared authentication mechanism's `credentials_env`; each AI provider's\
   `credentials_env`, and for a self-hosted provider its `endpoint_env`; and any variable the\
   chosen deployment target itself requires (e.g. a database connection string the platform\
   provides). Present that union, say where a variable came from where it is not obvious, and\
   let the developer correct it. In revision mode, assemble the same union but\
   present only what this revision adds — the established variables are already\
   configured. Reference variable\
   NAMES only — never values. Ask how they plan to manage secrets (platform-native secrets\
   manager, AWS Secrets Manager, HashiCorp Vault, .env files for local development only, etc.).

6. **Monitoring and observability** — Ask whether they want error tracking and/or infrastructure\
   monitoring. Make lightweight, appropriate suggestions (e.g., Sentry for errors, CloudWatch /\
   Datadog / Grafana Cloud for metrics, Uptime Robot / Better Stack for availability).

   **When the AI features spec is present in context**, additionally — one question at a time,\
   sized to the feature tiers in use, never over-engineering a thin AI footprint — cover:
   - **Model observability** — capturing token usage, latency, and error rates for model calls\
     (often an extension of the error/metrics tooling already chosen).
   - **Evaluation cadence** — whether and how often to run offline and/or online evals, and what\
     should trigger them (e.g., before a prompt or model change).
   - **Feedback loop** — how to collect production signal (thumbs, corrections, escalations) to\
     improve prompts and model choices over time.
   - **Safety and guardrails** — output filtering, content/abuse policy, and escalation paths,\
     for user-facing generative features.

   Make these proportionate: a single low-tier feature may warrant only lightweight error\
   tracking, while higher tiers (rag, tool_agent, and above) justify eval cadence and feedback.

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

One block per deployment surface the stack declares — a static frontend and an API are two\
 surfaces, not one. Repeat this block for each:

### `surface_name`

- **Type:** cloud | paas | on-premise | serverless
- **Provider:** AWS | GCP | Azure | Fly.io | Render | etc.
- **Service:** ECS Fargate | Cloud Run | Static Site | etc.
- **Region:** us-east-1 | europe-west1 | etc. (omit if not applicable)
- **Transport:** HTTPS only | etc.
- **CORS:** the policy this surface applies (omit if it serves no browser origin)

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
- **Model observability:** token usage / latency / error rates — tooling | none (AI features only)
- **Eval cadence:** offline/online schedule and triggers | none (AI features only)
- **Feedback loop:** production-signal collection approach | none (AI features only)
- **Safety/guardrails:** output filtering / abuse policy / escalation | none (user-facing generative features only)

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

Any additional caveats, cost estimates, or advice. Include a short record of the project's\
 non-functional goals: which ones this deployment addresses and where, and which are the coding\
 agent's to satisfy rather than the deployment's.

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


def revision_delta(vision: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return this round's revision delta, or ``None`` for a greenfield vision.

    A revision round's vision carries an accumulating ``revision_history`` (each
    round contributes one entry, stamped deterministically by Brainstormer); its
    final entry is the delta for the current round — ``goal``, the
    ``key_features_mvp`` name changes (``added`` / ``modified`` / ``removed``),
    and ``rationale``. A greenfield vision has no ``revision_history``. The input
    is the session-form vision envelope (``{"vision_statement": {...}}``); a
    non-enveloped or greenfield vision yields ``None`` (not revision mode). Twin
    of StackAdvisor's / Phaser's reader of the same name.
    """
    vs = (vision or {}).get("vision_statement") if isinstance(vision, dict) else None
    history = vs.get("revision_history") if isinstance(vs, dict) else None
    if isinstance(history, list) and history:
        last = history[-1]
        return last if isinstance(last, dict) else None
    return None


def build_revision_note(delta: dict[str, Any]) -> str:
    """Render a revision delta into a deployment-scoping note for the revision seed.

    Produces a single bracketed instruction (same shape as the staleness note)
    that scopes the deployment-plan update to this revision's ``key_features_mvp``
    changes while treating the rest of the deployment as already provisioned and
    in place. Deterministic — the ``added`` / ``modified`` / ``removed`` names come
    straight from the Brainstormer-stamped delta; the model never authors them.
    """
    changes = delta.get("changes") or {}
    added = list(changes.get("added") or [])
    modified = list(changes.get("modified") or [])
    removed = list(changes.get("removed") or [])
    goal = (delta.get("goal") or "").strip()

    segments: list[str] = ["[This is a revision of an already-deployed project."]
    if goal:
        segments.append(f" Goal: {goal}")
    clauses: list[str] = []
    if added:
        clauses.append("added features (" + ", ".join(added) + ")")
    if modified:
        clauses.append("changed features (" + ", ".join(modified) + ")")
    if removed:
        clauses.append("removed features (" + ", ".join(removed) + ")")
    if clauses:
        segments.append(
            " Update the deployment plan only for what this revision's "
            + "; ".join(clauses)
            + " require — e.g. new environment variables or API keys, new "
            "infrastructure for the new surface, and observability for any "
            "newly introduced AI features."
        )
    segments.append(
        " Treat the rest of the deployment as already provisioned and in place — "
        "keep the established provider, service, containerization, CI/CD, "
        "environment, and infrastructure, and do not re-ask settled deployment "
        "decisions or re-derive the whole plan.]"
    )
    return "".join(segments)


_README_OFFER = (
    "\n\n---\n\n"
    "Would you like me to create a comprehensive **README.md** in your project "
    "root — covering the vision, key features, install/setup, and usage — so "
    "anyone (or any coding agent) opening the repository has the full picture in "
    "one place? (yes/no — you're also welcome to ask questions or request changes)"
)

_README_OPTIN_QUESTION = (
    "I'm **Deployer**, the final stage. I'll help you set up your AI coding "
    "agent and produce a deployment plan for this project.\n\n"
    "One question before we begin: once your deployment plan is ready, would you "
    "like me to also author a comprehensive **README.md** for your project root "
    "— covering the vision, key features, install/setup, and usage — so anyone "
    "(or any coding agent) opening the repository has the full picture in one "
    "place?\n\n"
    "(yes/no — you're also welcome to ask questions either way)"
)

_README_OPTIN_REASK = (
    "Sorry, I didn't catch that. Once your deployment plan is ready, would you "
    "like me to also author a comprehensive **README.md** for your project "
    "root? (yes/no)"
)

_README_AUTHORING_NOTE = (
    "\n\n---\n\n"
    "Your deployment plan is ready and saved. As you requested, I'll now "
    "author your **README.md** using the finished plan…\n\n"
)


def build_readme_request(
    existing_readme: str | None, delta: dict[str, Any] | None
) -> str:
    """Build the user-turn seed instructing Deployer to author the project README.

    The model already holds the vision, stack, phases, and the deployment plan it
    just finalized in this same conversation, so this seed adds only the task
    framing, the required structure, and — when a README already exists at the
    project root — that README as a baseline to update in place. In a revision
    round (``delta`` present) it names the changed features so the update stays
    scoped. Deterministic scaffolding only; the model authors the prose.
    """
    parts: list[str] = [
        "The developer has asked for a comprehensive project README. Using the "
        "project vision, the technology stack, the development phases, and the "
        "deployment plan we finalized in this conversation, write a complete, "
        "polished README.md for the project root.\n\n"
        "Cover, as Markdown sections: a top-level project title and a one- to "
        "two-paragraph overview drawn from the vision; key features; the "
        "technology stack; prerequisites and installation/setup steps; how to "
        "run and use the application; and configuration (environment variable "
        "NAMES only, never values) plus deployment pointers consistent with the "
        "deployment plan. Write for someone opening the repository for the first "
        "time — self-contained, not a reference to the .spec4 planning files.\n\n"
    ]
    if existing_readme:
        parts.append(
            "A README already exists at the project root. Here is its full "
            "current contents — treat it as the baseline and update it in place, "
            "preserving the sections that are still accurate and revising only "
            "what this version changes:\n\n"
            f"```markdown\n{existing_readme}\n```\n\n"
        )
    if delta:
        changes = delta.get("changes") or {}
        named: list[str] = []
        for label, key in (("added", "added"), ("changed", "modified"),
                           ("removed", "removed")):
            vals = list(changes.get(key) or [])
            if vals:
                named.append(f"{label} {', '.join(vals)}")
        if named:
            parts.append(
                "This is a revision round. Focus the README updates on this "
                "version's feature changes (" + "; ".join(named) + ") and leave "
                "the rest of the document intact.\n\n"
            )
    parts.append(
        "Output the README directly as a single Markdown document, with no "
        "preamble, no surrounding code fence, and no commentary before or after."
    )
    return "".join(parts)


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
    user_input = _drop_orphan_or_route_to_fresh_start(messages, user_input)

    # Up-front README opt-in (greenfield only): the very first turn is a
    # standalone yes/no gate, handled deterministically and kept out of the LLM
    # history entirely. A clear answer records the choice and falls through to
    # the normal opening (user_input := None); an ambiguous reply re-asks.
    if user_input is not None and session.get("_deployer_pending_readme_optin"):
        lowered = user_input.lower()
        affirmative = any(
            w in lowered
            for w in ("yes", "yeah", "yep", "yup", "sure", "ok", "okay",
                      "go ahead", "proceed", "please", "create", "do it")
        )
        negative = any(
            w in lowered
            for w in ("no", "nope", "nah", "don't", "dont", "skip",
                      "later", "cancel", "stop")
        )
        if affirmative and not negative:
            session["_deployer_pending_readme_optin"] = False
            session["_deployer_readme_requested"] = True
            user_input = None
        elif negative and not affirmative:
            session["_deployer_pending_readme_optin"] = False
            session["_deployer_readme_requested"] = False
            user_input = None
        else:
            yield _README_OPTIN_REASK
            return

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
            version = session.get("phase_version", 0)
            code_review = session.get("code_review") or {}
            ai_features = session.get("ai_features")
            vision = session.get("vision_statement")
            feature_specs = session.get("feature_specs")
            working_dir = session.get("working_dir")
            ai_features_block = (
                _ai_features_for_deployer(ai_features, stack) + "\n"
                if ai_features else ""
            )

            # Revision mode: a prior version of this project has already been
            # implemented and this round's vision carries a delta. A deployment
            # plan describes the whole running system, so the revision update is
            # whole-system-scoped: carry the prior plan forward as the baseline
            # (when one exists — the prior round may have skipped Deployer) and
            # scope the update to the delta rather than re-deriving the plan. The
            # ai_features context stays whole (no introduced_in_version partition).
            # The gate is an existence probe (implemented predecessor + delta), not
            # gated on the prior plan loading.
            delta = revision_delta(vision)
            is_revision = (
                delta is not None
                and working_dir is not None
                and project_manager.latest_implemented_version(working_dir)
                is not None
            )

            # Greenfield (no existing plan, not a revision): ask the standalone
            # README opt-in as the very first turn, before any plan work, so the
            # decision is prominent rather than buried at the end of the plan.
            # The question is asked once; `_deployer_readme_optin_done` both
            # guards against re-asking and, downstream, marks this run as a
            # greenfield opt-in flow (so plan finalization auto-authors or skips
            # instead of appending the trailing offer).
            greenfield = not session.get("_deployer_plan_existed") and not is_revision
            if greenfield and not session.get("_deployer_readme_optin_done"):
                session["_deployer_readme_optin_done"] = True
                session["_deployer_pending_readme_optin"] = True
                yield _README_OPTIN_QUESTION
                return

            stack_block = _stack_for_deployer(stack)

            nfr_block = _nfr_goals_for_deployer(stack, feature_specs)

            phases_block = _phases_for_deployer(phases, version)

            existing_infra_block = _build_existing_infra_block(code_review)

            if session.get("_deployer_plan_existed"):
                existing_plan = (
                    project_manager.load_deployment_plan(session.get("working_dir"))
                    or ""
                )
                existing_plan_block = (
                    "Here is the full contents of the existing deployment plan, "
                    f"loaded from `.spec4/v{version}/deployment-plan.md`:\n\n"
                    f"```markdown\n{existing_plan}\n```\n\n"
                    if existing_plan
                    else ""
                )
                seed = (
                    f"{stack_block}{nfr_block}{phases_block}{existing_infra_block}{ai_features_block}"
                    f"{existing_plan_block}"
                    "The deployment plan above was saved in a previous session, but "
                    "this is a fresh chat session with no record of how it was built. "
                    "You already have its full contents above, so you can answer "
                    "questions about it directly — do NOT ask the developer to paste "
                    "the file.\n\n"
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
            elif is_revision:
                prior_plan = (
                    project_manager.load_prior_deployment_plan(working_dir) or ""
                )
                prior_plan_block = (
                    "Here is the deployment plan from the previous implemented "
                    "version, to carry forward as the established baseline:\n\n"
                    f"```markdown\n{prior_plan}\n```\n\n"
                    if prior_plan
                    else ""
                )
                if prior_plan_block:
                    intro_line = (
                        "Please introduce yourself as Deployer and briefly confirm "
                        "the established deployment you are carrying forward from the "
                        "baseline above. "
                    )
                else:
                    intro_line = (
                        "Please introduce yourself as Deployer and note that this is "
                        "a revision of an already-deployed project. "
                    )
                seed = (
                    f"{stack_block}{nfr_block}{phases_block}{existing_infra_block}{ai_features_block}"
                    f"{prior_plan_block}"
                    "I am starting a REVISION round on an existing, already-implemented "
                    "and already-deployed version of this project. Operate in REVISION "
                    "mode.\n\n"
                    f"{build_revision_note(delta)}\n\n"
                    f"{intro_line}"
                    "Then begin by asking which AI coding agent the developer plans to "
                    "use to implement this revision's phases. When you reach deployment "
                    "planning, update the deployment only for what this revision changed "
                    "— do not re-ask settled infrastructure decisions or re-derive the "
                    "whole plan."
                )
            else:
                seed = (
                    f"{stack_block}{nfr_block}{phases_block}{existing_infra_block}{ai_features_block}"
                    "You have already greeted the developer, so do not re-introduce "
                    "yourself. Begin directly by asking which AI coding agent the "
                    "developer plans to use to implement these phases."
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
                    "Your new deployment plan has been saved. "
                    "You can download it using the button below."
                    + _README_OFFER
                )
                messages.append({"role": "assistant", "content": confirm_msg})
                session["deployer_state"] = STATE_DEPLOYER_COMPLETE
                session["deployer_stale_acknowledged"] = {}
                session["deployer_artifact_msg_count"] = len(messages)
                session["_deployer_pending_readme"] = True
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

        if session.get("_deployer_pending_readme"):
            session["_deployer_pending_readme"] = False
            lowered = user_input.lower()
            affirmative = any(
                w in lowered
                for w in ("yes", "yeah", "yep", "yup", "sure", "ok", "okay",
                          "go ahead", "proceed", "please", "create", "do it")
            )
            negative = any(
                w in lowered
                for w in ("no", "nope", "nah", "don't", "dont", "skip",
                          "later", "cancel", "stop")
            )
            if negative and not affirmative:
                decline_msg = (
                    "No problem — I haven't created a README. Your deployment "
                    "plan is saved and you're all set; feel free to ask any "
                    "follow-up questions."
                )
                messages.append({"role": "assistant", "content": decline_msg})
                yield decline_msg
                return
            if affirmative and not negative:
                working_dir = session.get("working_dir")
                existing = (
                    project_manager.load_existing_readme(working_dir)
                    if working_dir
                    else None
                )
                delta = revision_delta(session.get("vision_statement"))
                # Replace the bare confirmation with the authoring instruction so
                # the LLM turn below produces the README. Mutating the just-
                # appended user message (rather than appending a second user
                # message) keeps role alternation valid.
                messages[-1]["content"] = build_readme_request(existing, delta)
                session["_deployer_generating_readme"] = True
            # Ambiguous reply — fall through to a normal conversational turn.

    search_cfg = websearch.from_session(session)
    system = llm.build_system_prompt(SYSTEM_PROMPT, search_cfg)

    # Deployer's replies are shown verbatim, so the chars counter's displayed-
    # message fallback would mostly work — but not on the greenfield README beat
    # below, which yields a note and opens a second stream in the same turn.
    # Publish a running total instead; `_received` seeds that second stream.
    _received = yield from _stream_counting(
        llm.stream_turn(
            system, messages, llm_config, search_cfg, agent_name="deployer",
            session=session,
        ),
        session,
    )

    last_text = _last_assistant_text(messages)
    if session.get("_deployer_generating_readme"):
        # This turn authored the project README (set by the pending-readme
        # handler above). Stage it for _persist_artifacts to write to the
        # project root; the deployment plan is already complete and saved.
        session["_deployer_generating_readme"] = False
        session["_deployer_readme_markdown"] = last_text
    elif "## Deployment Steps" in last_text:
        session["_deployer_plan_markdown"] = last_text
        if session.get("_deployer_plan_existed"):
            confirm_q = (
                "\n\n---\n\n"
                "**Heads up:** You already have a `deployment-plan.md` from a previous "
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
            if session.get("_deployer_readme_optin_done"):
                # Greenfield: the README decision was already made up front.
                if session.get("_deployer_readme_requested"):
                    # Opted in → author the README now, in this same turn, using
                    # the finished plan (the prior assistant message) as context.
                    session["_deployer_readme_requested"] = False
                    working_dir = session.get("working_dir")
                    existing = (
                        project_manager.load_existing_readme(working_dir)
                        if working_dir
                        else None
                    )
                    readme_delta = revision_delta(session.get("vision_statement"))
                    yield _README_AUTHORING_NOTE
                    messages.append(
                        {
                            "role": "user",
                            "content": build_readme_request(existing, readme_delta),
                        }
                    )
                    yield from _stream_counting(
                        llm.stream_turn(
                            system, messages, llm_config, search_cfg,
                            agent_name="deployer",
                            session=session,
                        ),
                        session,
                        seed=_received + len(_README_AUTHORING_NOTE),
                    )
                    session["_deployer_readme_markdown"] = _last_assistant_text(
                        messages
                    )
                    session["deployer_artifact_msg_count"] = len(messages)
                # Opted out → nothing further; the plan stands on its own with no
                # trailing offer.
            else:
                # No up-front opt-in for this run (e.g. a revision round) — keep
                # the closing README offer as the final beat.
                messages[-1]["content"] = last_text + _README_OFFER
                session["_display_override"] = messages[-1]["content"]
                session["_deployer_pending_readme"] = True
