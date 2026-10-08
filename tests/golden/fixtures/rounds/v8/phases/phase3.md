---
{
  "phase_number": 3,
  "total_phases": 6,
  "phase_title": "Caddy Edge \u2014 HTTPS, Single-Origin SPA + API on bwtemp.spec4.ai",
  "phase_summary": "Stand up Caddy 2 on the VPS as the public edge for the temporary validation hostname bwtemp.spec4.ai: serving the Vite dist/ bundle as static files with SPA history fallback, reverse-proxying /api/* to Uvicorn on localhost with response buffering explicitly disabled so all four server-sent-event apps stream progressively, and obtaining a trusted Let's Encrypt certificate with automatic renewal. Re",
  "features": [
    {
      "id": "self_hosted_deployment",
      "role": "extended",
      "scope_note": "Delivers the trusted HTTPS edge, single-origin static-plus-API serving and progressive streaming through the proxy on the temporary validation hostname; behaviour-preservation acceptance is Phase 5 and the canonical bw.spec4.ai cutover with earlier addresses retired is Phase 6."
    },
    {
      "id": "landing_page",
      "role": "introduced",
      "scope_note": "Makes the existing landing page and every example app route publicly reachable through the new edge via SPA history fallback; no landing-page content, roster or navigation is changed by this phase."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "Caddy 2",
      "systemd",
      "Vite",
      "React",
      "React Router",
      "Node 20",
      "uvicorn",
      "sse-starlette",
      "@microsoft/fetch-event-source",
      "@sentry/react"
    ]
  },
  "verification": "All of the following must hold, checked from outside the VPS. (1) `dig +short bwtemp.spec4.ai` resolves to the VPS IP, while `dig +short bw.spec4.ai` still resolves to Render. (2) `caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile` passes, `systemctl is-active caddy` reports active and `systemctl is-enabled caddy` reports enabled. (3) `curl -sS -I https://bwtemp.spec4.ai/` returns H"
}
---
# Phase 3: Caddy Edge — HTTPS, Single-Origin SPA + API on bwtemp.spec4.ai

_Trimmed fixture: frontmatter only; the prose body of the real phase is not reproduced._
