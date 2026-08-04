"""Unit tests for ``_nfr_goals_for_deployer`` — the project's non-functional
goals as Deployer input (D-DE6).

Several of a project's ``nfr_goals`` are deployment decisions and nothing else:
they are settled by region, caching, scaling posture, backup policy, and network
isolation. Deployer received none of them, so they evaporated between the vision
and the plan.

This channel renders every goal with its stack claim status. The honesty
constraint is the load-bearing part and is asserted here: a goal that no stack
entry claims is marked unclaimed and left that way. Goals satisfied by
*features* rather than by stack components correctly have no claimer, and
inventing one would put a false infrastructure claim in a deployment plan.

Ids come from the shared ``derived_nfr_ids`` derivation, so a goal carries the
same id here as everywhere else in the pipeline.

Pure rendering assertions; whether the live model then threads the
deployment-relevant goals into the plan is an in-app behavioural draw, not
asserted here.
"""

from __future__ import annotations

from typing import Any

from spec4.agents._utils import _nfr_goals_for_deployer


def _specs(*goals: str) -> dict[str, Any]:
    return {"nfr_goals": list(goals)}


def _stack(**over: Any) -> dict[str, Any]:
    spec: dict[str, Any] = {"name": "Demo"}
    spec.update(over)
    return {"stack_spec": spec}


# --- empty / absent --------------------------------------------------------


def test_no_goals_renders_nothing() -> None:
    assert _nfr_goals_for_deployer(_stack(), None) == ""
    assert _nfr_goals_for_deployer(_stack(), {}) == ""
    assert _nfr_goals_for_deployer(_stack(), _specs()) == ""


def test_goals_render_even_with_no_stack() -> None:
    """The goals are the vision's; an absent stack makes them all unclaimed."""
    out = _nfr_goals_for_deployer(None, _specs("Works offline"))
    assert "Works offline" in out
    assert "no stack component" in out


# --- claims ----------------------------------------------------------------


def test_claimed_goal_names_its_claiming_entries() -> None:
    stack = _stack(
        persistence={
            "browser_storage": {
                "choice": "IndexedDB",
                "satisfies_nfr": ["nfr_works_offline"],
            }
        },
        libraries=[{"name": "Workbox", "satisfies_nfr": ["nfr_works_offline"]}],
    )
    out = _nfr_goals_for_deployer(stack, _specs("Works offline"))
    assert "- claimed by: Workbox, browser_storage" in out


def test_claimers_are_deduplicated_and_sorted() -> None:
    stack = _stack(
        libraries=[
            {"name": "Workbox", "satisfies_nfr": ["nfr_works_offline"]},
            {"name": "Workbox", "satisfies_nfr": ["nfr_works_offline"]},
            {"name": "Alpha", "satisfies_nfr": ["nfr_works_offline"]},
        ]
    )
    out = _nfr_goals_for_deployer(stack, _specs("Works offline"))
    assert "claimed by: Alpha, Workbox" in out


def test_every_goal_is_rendered_with_its_id_and_text() -> None:
    out = _nfr_goals_for_deployer(_stack(), _specs("Fast answers", "Stays up"))
    assert '`nfr_fast_answers` — "Fast answers"' in out
    assert '`nfr_stays_up` — "Stays up"' in out


def test_goal_order_follows_the_source_list() -> None:
    out = _nfr_goals_for_deployer(_stack(), _specs("Zebra", "Apple", "Mango"))
    assert out.index("Zebra") < out.index("Apple") < out.index("Mango")


# --- honesty: orphans ------------------------------------------------------


def test_unclaimed_goal_is_surfaced_not_dropped() -> None:
    """The orphan is the interesting case for deployment; it must not vanish."""
    stack = _stack(libraries=[{"name": "Lib", "satisfies_nfr": ["nfr_fast_answers"]}])
    out = _nfr_goals_for_deployer(
        stack, _specs("Fast answers", "Users can edit and send without leaving")
    )
    assert "Users can edit and send without leaving" in out


def test_unclaimed_goal_carries_the_no_invention_instruction() -> None:
    out = _nfr_goals_for_deployer(_stack(), _specs("Citations are verifiable"))
    assert "no stack component" in out
    assert "Do not invent an infrastructure claim" in out


def test_claimed_and_unclaimed_goals_are_distinguishable() -> None:
    stack = _stack(libraries=[{"name": "Redis", "satisfies_nfr": ["nfr_fast_answers"]}])
    out = _nfr_goals_for_deployer(stack, _specs("Fast answers", "Refuses bad asks"))
    claimed = out.split("`nfr_fast_answers`")[1].split("- `")[0]
    orphan = out.split("`nfr_refuses_bad_asks`")[1]
    assert "claimed by: Redis" in claimed
    assert "no stack component" in orphan


def test_claim_matching_no_derived_goal_is_ignored() -> None:
    """An unknown claim id is stack-side drift, not a goal to render."""
    stack = _stack(libraries=[{"name": "Lib", "satisfies_nfr": ["nfr_does_not_exist"]}])
    out = _nfr_goals_for_deployer(stack, _specs("Fast answers"))
    assert "nfr_does_not_exist" not in out
    assert "no stack component" in out


# --- shape -----------------------------------------------------------------


def test_bare_and_wrapped_stack_shapes_both_work() -> None:
    spec = {"libraries": [{"name": "Redis", "satisfies_nfr": ["nfr_fast_answers"]}]}
    wrapped = _nfr_goals_for_deployer({"stack_spec": spec}, _specs("Fast answers"))
    bare = _nfr_goals_for_deployer(spec, _specs("Fast answers"))
    assert "claimed by: Redis" in wrapped
    assert wrapped == bare
