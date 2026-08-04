"""Unit tests for ``_stack_for_deployer`` — the stack's deployment signals as
Deployer input (D-DE5).

Deployer previously received the whole stack as a raw JSON paste in which every
deployment decision was present but illegible. This digest renders the
deployment-shaped view verbatim: the targets to host with their exposure, the
auth mechanisms with the credentials they need in the environment, the stores
and infrastructure to provision, and the roadmap entries to record rather than
build.

Two absences are load-bearing and asserted here: an absent or empty
``security.auth`` states that the project has no accounts, and an absent
``integrations`` block states there are no external services — neither may read
as an omission that invites a re-ask.

Providers and ``model_family`` are deliberately absent: provider and model
deployment belongs to the AI channel, and rendering it here too would give one
decision two owners.

Pure rendering assertions; whether the live model then writes a better Target or
Environment section is an in-app behavioural draw, not asserted here.
"""

from __future__ import annotations

from typing import Any

from spec4.agents._utils import _stack_for_deployer


def _stack(**over: Any) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "name": "Demo",
        "deployment": {
            "targets": [
                {
                    "name": "web_client",
                    "kind": "spa",
                    "purpose": "Browser UI",
                    "language": "TypeScript",
                    "hosting": "static hosting behind a managed CDN",
                    "build": "Vite build emitting a hashed bundle + service worker",
                    "distribution": "served at the app's root domain",
                    "api_contract": "REST",
                    "exposure": {
                        "transport": "HTTPS only",
                        "cors": "allow only the backend's origin",
                    },
                }
            ]
        },
        "persistence": {
            "primary_store": {
                "choice": "PostgreSQL 16",
                "purpose": "Source of truth",
                "durability": "survives restarts; nightly backup",
            },
            "cache": {
                "choice": "Redis",
                "purpose": "Hot path cache",
                "status": "optional",
            },
        },
        "libraries": [{"name": "Playwright", "status": "deferred"}],
    }
    spec.update(over)
    return {"stack_spec": spec}


# --- empty / absent --------------------------------------------------------


def test_absent_stack_renders_nothing() -> None:
    assert _stack_for_deployer(None) == ""
    assert _stack_for_deployer({}) == ""


def test_bare_and_wrapped_shapes_both_work() -> None:
    wrapped = _stack_for_deployer(_stack())
    bare = _stack_for_deployer(_stack()["stack_spec"])
    assert "web_client" in wrapped
    assert wrapped == bare


# --- targets ---------------------------------------------------------------


def test_target_fields_are_rendered_verbatim() -> None:
    out = _stack_for_deployer(_stack())
    assert "`web_client` (spa) — Browser UI" in out
    assert "hosting: static hosting behind a managed CDN" in out
    # ``build`` is what carries the service-worker/PWA story.
    assert "service worker" in out
    assert "distribution: served at the app's root domain" in out
    assert "API contract: REST" in out


def test_exposure_transport_and_cors_are_rendered() -> None:
    """Transport reached no drawn plan at baseline; it must be legible here."""
    out = _stack_for_deployer(_stack())
    assert "transport: HTTPS only" in out
    assert "CORS: allow only the backend's origin" in out


def test_every_target_is_rendered() -> None:
    stack = _stack()
    stack["stack_spec"]["deployment"]["targets"].append(
        {"name": "api", "kind": "rest_api", "purpose": "Serves the client"}
    )
    out = _stack_for_deployer(stack)
    assert "2 surface(s) to host" in out
    assert "`web_client`" in out
    assert "`api` (rest_api)" in out


# --- auth ------------------------------------------------------------------


def test_auth_renders_mechanism_serves_and_credentials() -> None:
    stack = _stack(
        security={
            "auth": [
                {
                    "mechanism": "OIDC against company IdP",
                    "purpose": "Authenticate employees",
                    "serves_features": ["policy_qa"],
                    "credentials_env": ["OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET"],
                }
            ]
        }
    )
    out = _stack_for_deployer(stack)
    assert "1 mechanism(s)" in out
    assert "OIDC against company IdP — Authenticate employees" in out
    assert "serves: policy_qa" in out
    assert "credentials (environment): OIDC_CLIENT_ID, OIDC_CLIENT_SECRET" in out


def test_absent_security_states_the_trustworthy_negative() -> None:
    out = _stack_for_deployer(_stack())
    assert "the stack declares none" in out
    assert "no user accounts" in out


def test_present_but_empty_auth_is_also_a_trustworthy_negative() -> None:
    """``{"auth": []}`` is a decision recorded by absence, not a gap."""
    out = _stack_for_deployer(_stack(security={"auth": []}))
    assert "no user accounts" in out


def test_absent_integrations_states_the_trustworthy_negative() -> None:
    out = _stack_for_deployer(_stack())
    assert "no third-party services" in out


def test_present_integrations_suppress_the_negative() -> None:
    out = _stack_for_deployer(_stack(integrations=[{"name": "SendGrid"}]))
    assert "no third-party services" not in out


# --- provisioning ----------------------------------------------------------


def test_persistence_store_is_listed_to_provision_with_its_choice() -> None:
    out = _stack_for_deployer(_stack())
    assert "`primary_store` (persistence): PostgreSQL 16 — Source of truth" in out
    assert "durability: survives restarts; nightly backup" in out


def test_infrastructure_entries_are_listed_to_provision() -> None:
    """Infrastructure is a dict keyed by name and carries no ``kind`` field."""
    stack = _stack(
        infrastructure={
            "chunking_pipeline": {
                "choice": "LangChain splitter",
                "purpose": "Chunk documents",
                "implementation": "In-service Python",
            }
        }
    )
    out = _stack_for_deployer(stack)
    assert "`chunking_pipeline` (infrastructure): LangChain splitter" in out
    assert "implementation: In-service Python" in out


def test_satisfies_infra_is_surfaced_on_the_provisioning_entry() -> None:
    stack = _stack(
        persistence={
            "primary_store": {
                "choice": "PostgreSQL + pgvector",
                "satisfies_infra": ["vector_index"],
            }
        }
    )
    out = _stack_for_deployer(stack)
    assert "satisfies infrastructure need: vector_index" in out


# --- roadmap ---------------------------------------------------------------


def test_roadmap_entries_are_separated_from_provisioning() -> None:
    out = _stack_for_deployer(_stack())
    provision = out.split("**To provision**")[1].split("**Roadmap")[0]
    roadmap = out.split("**Roadmap")[1]
    assert "primary_store" in provision
    # The optional cache is recorded, never provisioned.
    assert "cache" not in provision
    assert "`cache` (persistence, optional)" in roadmap


def test_roadmap_sweeps_statuses_outside_persistence_and_infrastructure() -> None:
    out = _stack_for_deployer(_stack())
    assert "`Playwright` (libraries, deferred)" in out


def test_roadmap_section_is_omitted_when_everything_is_mvp() -> None:
    stack = _stack(
        persistence={"primary_store": {"choice": "PostgreSQL"}},
        libraries=[{"name": "fastapi"}],
    )
    out = _stack_for_deployer(stack)
    assert "**Roadmap" not in out


# --- deliberate omissions --------------------------------------------------


def test_providers_and_model_family_are_not_rendered() -> None:
    """Provider/model deployment is the AI channel's to own (single ownership)."""
    stack = _stack(
        providers={
            "Anthropic": {
                "model_family": "Claude",
                "capabilities": [{"tier": "rag", "serves_features": ["policy_qa"]}],
            }
        }
    )
    out = _stack_for_deployer(stack)
    assert "Claude" not in out
    assert "model_family" not in out
