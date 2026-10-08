---
{
  "phase_number": 6,
  "total_phases": 6,
  "phase_title": "Cutover \u2014 Repoint bw.spec4.ai, Retire Render, Single Canonical Origin",
  "phase_summary": "Move the canonical hostname bw.spec4.ai to the VPS, flip CORS_ORIGIN to it, remove the bwtemp.spec4.ai site block so exactly one address serves the gallery, and retire Render entirely by deleting render.yaml and shutting down its services. This completes the migration: one canonical public HTTPS origin, always warm, with the previous host serving nothing.",
  "features": [
    {
      "id": "self_hosted_deployment",
      "role": "extended",
      "scope_note": "Completes the feature by delivering the single canonical public address with earlier addresses no longer serving, and retiring the previous host entirely; all prior scope was established in Phases 1 through 5."
    },
    {
      "id": "landing_page",
      "role": "extended",
      "scope_note": "Confirms the gallery is reached at the canonical bw.spec4.ai origin with its roster and navigation intact; no landing-page content is changed."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "Caddy 2",
      "systemd",
      "uvicorn",
      "Vite",
      "React Router",
      "sse-starlette",
      "@microsoft/fetch-event-source"
    ]
  },
  "verification": "All of the following must hold, checked from outside the VPS. (1) deploy/ACCEPTANCE.md records a PASS for every Phase 5 section with no open FAIL. (2) `dig +short bw.spec4.ai` returns the VPS IP from at least two independent public resolvers. (3) `curl -sS -I https://bw.spec4.ai/` returns HTTP 200 with a valid publicly trusted certificate and no warning, and `curl -sS -I http://bw.spec4.ai/` retur"
}
---
# Phase 6: Cutover — Repoint bw.spec4.ai, Retire Render, Single Canonical Origin

_Trimmed fixture: frontmatter only; the prose body of the real phase is not reproduced._
