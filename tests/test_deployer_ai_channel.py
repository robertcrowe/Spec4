"""Unit tests for ``_ai_features_for_deployer`` — AI deployment context (D-DE7).

What a deployment plan needs about the AI side is narrow: which providers to
configure access to, what latency and cost the features are budgeted for, and
whether evals and guardrails need a home.

Three boundaries are asserted here because each is an ownership decision:

* **providers come from the stack**, whose ``providers`` block is the ratified
  decision (D-PH6 A'). The catalog's ``cross_cutting.provider_strategy`` is a
  recommendation it supersedes and is no longer rendered — two sources for one
  decision is the double-owner defect;
* **``model_family`` only** — the family is the decision, and a plan must never
  pin a specific model id;
* **no infrastructure nodes** — the catalog's infrastructure ids name the same
  substrate the stack digest already lists for provisioning.

Evals and safety are counted, not quoted: Deployer gives them a cadence and an
enforcement point, while the approaches themselves are the coding agent's.

Pure rendering assertions; whether the live model then plans provider access
well is an in-app behavioural draw, not asserted here.
"""

from __future__ import annotations

from typing import Any

from spec4.agents._utils import _ai_features_for_deployer


def _features(*nodes: dict[str, Any]) -> dict[str, Any]:
    return {"ai_features": list(nodes)}


def _node(fid: str = "summarize", **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"id": fid, "name": fid, "kind": "feature", "tier": "rag"}
    base.update(over)
    return base


def _stack(**providers: Any) -> dict[str, Any]:
    return {"stack_spec": {"name": "Demo", "providers": dict(providers)}}


# --- empty / absent --------------------------------------------------------


def test_no_ai_features_renders_nothing() -> None:
    assert _ai_features_for_deployer(None) == ""
    assert _ai_features_for_deployer({}) == ""
    assert _ai_features_for_deployer(_features()) == ""


def test_works_without_a_stack() -> None:
    """Tiers and budgets still render when no stack is supplied."""
    out = _ai_features_for_deployer(_features(_node()))
    assert "AI feature tiers in use: rag" in out
    assert "Providers to configure access to" not in out


# --- providers -------------------------------------------------------------


def test_provider_renders_model_family_role_and_tiers() -> None:
    stack = _stack(
        Anthropic={
            "model_family": "Claude",
            "credentials_env": "ANTHROPIC_API_KEY",
            "capabilities": [
                {"role": "primary", "tier": "rag"},
                {"role": "primary", "tier": "single_call"},
            ],
        }
    )
    out = _ai_features_for_deployer(_features(_node()), stack)
    assert "- Anthropic — model family: Claude (primary)" in out
    assert "serves tiers: rag, single_call" in out


def test_provider_credentials_env_is_surfaced() -> None:
    stack = _stack(
        OpenAI={"model_family": "GPT", "credentials_env": "OPENAI_API_KEY"}
    )
    out = _ai_features_for_deployer(_features(_node()), stack)
    assert "credentials (environment): OPENAI_API_KEY" in out


def test_endpoint_env_marks_a_self_hosted_provider() -> None:
    """``endpoint_env`` is the structural self-hosted signal — a host to run."""
    stack = _stack(
        Ollama={
            "model_family": "Llama",
            "endpoint_env": "OLLAMA_HOST",
            "credentials_env": "none — local endpoint",
        }
    )
    out = _ai_features_for_deployer(_features(_node()), stack)
    assert "self-hosted: reachable at `OLLAMA_HOST`" in out
    assert "not a third-party key to hold" in out


def test_provider_fallback_is_surfaced() -> None:
    stack = _stack(
        Anthropic={"model_family": "Claude", "fallback": "Ollama if unavailable"}
    )
    out = _ai_features_for_deployer(_features(_node()), stack)
    assert "fallback: Ollama if unavailable" in out


def test_plan_is_told_not_to_pin_a_model_id() -> None:
    stack = _stack(Anthropic={"model_family": "Claude"})
    out = _ai_features_for_deployer(_features(_node()), stack)
    assert "do not pin a specific model id" in out.lower()


def test_catalog_provider_strategy_is_not_rendered() -> None:
    """The stack supersedes it; rendering both is a double owner (D-DE7a)."""
    spec = _features(_node())
    spec["cross_cutting"] = {
        "provider_strategy": {"recommendation": "SUPERSEDED_RECOMMENDATION"}
    }
    out = _ai_features_for_deployer(spec, _stack(Anthropic={"model_family": "Claude"}))
    assert "SUPERSEDED_RECOMMENDATION" not in out


def test_bare_and_wrapped_stack_shapes_both_work() -> None:
    spec = {"providers": {"OpenAI": {"model_family": "GPT"}}}
    wrapped = _ai_features_for_deployer(_features(_node()), {"stack_spec": spec})
    bare = _ai_features_for_deployer(_features(_node()), spec)
    assert "model family: GPT" in wrapped
    assert wrapped == bare


# --- budgets ---------------------------------------------------------------


def test_budgets_render_latency_and_cost_per_feature() -> None:
    node = _node(budgets={"p95_latency": "2000ms", "cost_per_call": "$0.003"})
    out = _ai_features_for_deployer(_features(node))
    assert "- summarize: p95 latency 2000ms; cost/call $0.003" in out


def test_partial_budgets_render_what_is_present() -> None:
    node = _node(budgets={"p95_latency": "200ms"})
    out = _ai_features_for_deployer(_features(node))
    assert "- summarize: p95 latency 200ms" in out
    assert "cost/call" not in out


def test_budget_section_omitted_when_no_feature_declares_one() -> None:
    out = _ai_features_for_deployer(_features(_node()))
    assert "Per-feature budgets" not in out


# --- evals and safety ------------------------------------------------------


def test_eval_and_safety_are_counted_not_quoted() -> None:
    nodes = [
        _node("a", eval_approach={"offline": "GOLD_DATASET_METHODOLOGY"}),
        _node("b", privacy_safety=["REDACTION_RULE"]),
    ]
    out = _ai_features_for_deployer(_features(*nodes))
    assert "1 of 2 AI features declare an eval approach and 1 declare safety" in out
    # The methodology itself is the coding agent's, and must not be carried.
    assert "GOLD_DATASET_METHODOLOGY" not in out
    assert "REDACTION_RULE" not in out


def test_eval_safety_section_omitted_when_nothing_declares_either() -> None:
    out = _ai_features_for_deployer(_features(_node()))
    assert "Evals and safety" not in out


# --- deliberate omissions --------------------------------------------------


def test_infrastructure_nodes_are_not_rendered() -> None:
    """The stack digest already lists this substrate for provisioning."""
    nodes = [
        _node("policy_qa"),
        _node("vector_index", kind="infrastructure", tier="infrastructure"),
    ]
    out = _ai_features_for_deployer(_features(*nodes))
    assert "vector_index" not in out
