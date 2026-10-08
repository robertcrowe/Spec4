---
{
  "phase_number": 2,
  "total_phases": 6,
  "phase_title": "Process Supervision \u2014 systemd Unit, Warm-at-Boot, Restart Survival",
  "phase_summary": "Place the single-worker Uvicorn process under a systemd service unit with Restart=always, boot enablement, and an EnvironmentFile pointing at the root-owned 0600 secrets file, then prove the embedding model and fitted PCA projection are rebuilt warm and retained for the process lifetime across both a crash and a full host reboot. This replaces the retired managed platform's process lifecycle and i",
  "features": [
    {
      "id": "self_hosted_deployment",
      "role": "extended",
      "scope_note": "Adds continuous availability and crash/reboot survival via systemd supervision; the trusted public HTTPS origin lands in Phase 3 and the canonical-address cutover in Phase 6."
    },
    {
      "id": "shared_framework_services",
      "role": "extended",
      "scope_note": "Proves the shared embedding capability's readiness is established once at boot and retained for the whole process lifetime under supervision, so no visitor pays a warm-up cost; no service behaviour is altered."
    }
  ],
  "capabilities": [],
  "tech_stack_spec": {
    "dependencies": [
      "systemd",
      "uv",
      "uvicorn",
      "FastAPI",
      "Python 3.12",
      "sentence-transformers",
      "torch",
      "scikit-learn",
      "numpy",
      "structlog",
      "sentry-sdk",
      "pydantic-settings"
    ]
  },
  "verification": "All of the following must hold. (1) `systemctl is-active bws4-api` reports active and `systemctl is-enabled bws4-api` reports enabled. (2) `journalctl -u bws4-api --no-pager` contains structlog JSON records including an explicit embedding-model-load and PCA-projection-fit success for the current boot, with no swallowed warm-up exception \u2014 satisfying nfr_immediately_responsive_on_a_visitor_s_first_"
}
---
# Phase 2: Process Supervision — systemd Unit, Warm-at-Boot, Restart Survival

_Trimmed fixture: frontmatter only; the prose body of the real phase is not reproduced._
