"""Unit tests for ``_stack_digest_for_phaser`` — the deterministic join-key
digest that rides alongside the raw stack paste in Phaser's seed (D-PH1b A).

The digest is an *index* of the paste, never a replacement: it surfaces
``serves_features`` / ``serves_capabilities`` backlinks, ``satisfies_nfr``
claims (with unclaimed goals named honestly), ``status`` semantics, per-target
``exposure``, and the trustworthy negatives the stack records by absence.
Unnamed entries (provider ``capabilities[]`` items) take the nearest
non-container ancestor key as identity, suffixed with their tier.
"""

from __future__ import annotations

from typing import Any

from spec4.agents._utils import _stack_digest_for_phaser, slug

_HEAD = "Stack signal digest"


def _wrap(spec: dict[str, Any]) -> dict[str, Any]:
    return {"stack_spec": spec}


# --- empty / absent --------------------------------------------------------


def test_absent_or_empty_stack_returns_empty() -> None:
    assert _stack_digest_for_phaser(None) == ""
    assert _stack_digest_for_phaser({}) == ""


def test_wrapped_and_bare_shapes_render_identically() -> None:
    spec = {"libraries": [{"name": "Lib", "serves_features": ["f1"]}]}
    assert _stack_digest_for_phaser(_wrap(spec)) == _stack_digest_for_phaser(spec)


# --- backlinks -------------------------------------------------------------


def test_serves_features_backlinks_group_entries_by_feature() -> None:
    spec = {
        "libraries": [{"name": "React Hook Form", "serves_features": ["fare_lookup"]}],
        "persistence": {
            "primary_store": {
                "collections": [
                    {"name": "fare_table", "serves_features": ["fare_lookup"]},
                    {"name": "saved_trips", "serves_features": ["saved_trips"]},
                ]
            }
        },
    }
    out = _stack_digest_for_phaser(_wrap(spec))
    assert _HEAD in out
    fare_line = next(
        line for line in out.splitlines() if line.startswith("- `fare_lookup`")
    )
    assert "React Hook Form (libraries)" in fare_line
    assert "fare_table (persistence)" in fare_line
    assert "saved_trips" not in fare_line


def test_serves_capabilities_backlinks_render_in_own_section() -> None:
    spec = {
        "infrastructure": {
            "vector_store": {"serves_capabilities": ["sentiment_detection"]}
        }
    }
    out = _stack_digest_for_phaser(_wrap(spec))
    assert "AI capability → stack backlinks" in out
    assert "- `sentiment_detection`: vector_store (infrastructure)" in out


def test_unnamed_provider_capability_named_from_provider_and_tier() -> None:
    spec = {
        "providers": {
            "OpenAI": {
                "capabilities": [
                    {"tier": "single_call", "serves_capabilities": ["extract"]}
                ]
            }
        }
    }
    out = _stack_digest_for_phaser(_wrap(spec))
    assert "OpenAI [single_call]" in out


# --- nfr claims and orphans ------------------------------------------------


def test_claimed_and_unclaimed_goals_both_render() -> None:
    claimed_goal = "Lookups are fast."
    orphan_goal = "Users can send replies in-app."
    spec = {
        "libraries": [
            {"name": "Lib", "satisfies_nfr": [f"nfr_{slug(claimed_goal)}"]}
        ]
    }
    specs = {"features": [], "nfr_goals": [claimed_goal, orphan_goal]}
    out = _stack_digest_for_phaser(_wrap(spec), specs)
    assert f"- `nfr_{slug(claimed_goal)}`: claimed by Lib (libraries)" in out
    assert f"- `nfr_{slug(orphan_goal)}`: UNCLAIMED" in out
    assert "do NOT invent a stack claim" in out


def test_unknown_claim_flagged_against_derived_goals() -> None:
    spec = {"libraries": [{"name": "Lib", "satisfies_nfr": ["nfr_made_up"]}]}
    specs = {"features": [], "nfr_goals": ["A real goal."]}
    out = _stack_digest_for_phaser(_wrap(spec), specs)
    assert "`nfr_made_up` [matches no project goal]" in out


def test_claims_render_without_feature_specs() -> None:
    spec = {"libraries": [{"name": "Lib", "satisfies_nfr": ["nfr_x"]}]}
    out = _stack_digest_for_phaser(_wrap(spec))
    assert "- `nfr_x`: claimed by Lib (libraries)" in out
    assert "UNCLAIMED" not in out  # no derived set to orphan against


# --- status ----------------------------------------------------------------


def test_status_roster_lists_roadmap_entries() -> None:
    spec = {"libraries": [{"name": "Playwright", "status": "deferred"}]}
    out = _stack_digest_for_phaser(_wrap(spec))
    assert "ROADMAP, not build items" in out
    assert "- Playwright (libraries): status `deferred`" in out


def test_status_rule_stated_even_when_no_entry_carries_status() -> None:
    spec = {"libraries": [{"name": "Lib", "serves_features": ["f"]}]}
    out = _stack_digest_for_phaser(_wrap(spec))
    assert "ROADMAP, not build items" in out
    assert "every entry is a build item" in out


# --- exposure --------------------------------------------------------------


def test_exposure_renders_per_target() -> None:
    spec = {
        "libraries": [{"name": "Lib", "serves_features": ["f"]}],
        "deployment": {
            "targets": [
                {
                    "name": "api",
                    "exposure": {"transport": "HTTPS only", "cors": "own origin"},
                }
            ]
        },
    }
    out = _stack_digest_for_phaser(_wrap(spec))
    assert "Deployment exposure per target" in out
    assert "- api: transport=HTTPS only; cors=own origin" in out


# --- trustworthy negatives -------------------------------------------------


def test_absent_and_present_empty_security_read_as_no_auth() -> None:
    base = {"libraries": [{"name": "Lib", "serves_features": ["f"]}]}
    absent = _stack_digest_for_phaser(_wrap(dict(base)))
    present_empty = _stack_digest_for_phaser(
        _wrap({**base, "security": {"auth": []}})
    )
    for out in (absent, present_empty):
        assert "no accounts or authentication" in out


def test_present_security_suppresses_the_no_auth_negative() -> None:
    spec = {
        "libraries": [{"name": "Lib", "serves_features": ["f"]}],
        "security": {"auth": [{"mechanism": "oauth"}]},
    }
    out = _stack_digest_for_phaser(_wrap(spec))
    assert "no accounts or authentication" not in out


def test_staple_rule_always_stated() -> None:
    spec = {"libraries": [{"name": "Lib", "serves_features": ["f"]}]}
    out = _stack_digest_for_phaser(_wrap(spec))
    assert "global staple" in out