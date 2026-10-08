---
{
  "phase_number": 4,
  "total_phases": 6,
  "phase_title": "Release Delivery \u2014 Deploy Script and Provisioning Runbook",
  "phase_summary": "Codify the entire release procedure as one readable, version-controlled shell script run on the VPS \u2014 git pull, uv sync, npm ci and npm run build, alembic upgrade head, systemctl restart \u2014 followed by a post-restart warm-readiness check that fails the deploy loudly rather than leaving a silently cold process serving visitors. Completed by a first-time provisioning README that reproduces Phases 1 t",
  "features": [
    {
      "id": "self_hosted_deployment",
      "role": "extended",
      "scope_note": "Replaces the retired managed platform's build-and-deploy pipeline with a single version-controlled release procedure and a provisioning runbook; behaviour-preservation acceptance is Phase 5 and the canonical-hostname cutover is Phase 6."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "uv",
      "Node 20",
      "Alembic",
      "systemd",
      "Caddy 2",
      "uvicorn",
      "Vite",
      "pytest",
      "Ruff",
      "mypy",
      "Vitest",
      "@sentry/react"
    ]
  },
  "verification": "All of the following must hold. (1) `bash -n deploy/deploy.sh` passes and the script is committed and executable. (2) Running `deploy/deploy.sh` on the VPS completes every step in order \u2014 git pull, uv sync, npm ci and npm run build, `alembic -c backend/alembic.ini upgrade head`, systemctl restart \u2014 and exits zero. (3) The post-restart gate proves warmth, not just liveness: it polls http://127.0.0."
}
---
# Phase 4: Release Delivery — Deploy Script and Provisioning Runbook

_Trimmed fixture: frontmatter only; the prose body of the real phase is not reproduced._
