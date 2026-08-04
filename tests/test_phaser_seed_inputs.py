"""Seed-assembly tests for Phaser's D-PH1 input re-basing.

The greenfield seed carries the new channels in the D-PH1g order — vision,
product spine, stack paste + digest, AI features, manifest projection + mock
note, instruction — and degrades gracefully: a session without feature specs,
manifest, or stack simply omits the corresponding block, exactly as the
pre-D-PH1 seed did.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from unittest.mock import patch

from spec4.agents import phaser
from spec4.app_constants import STATE_IN_PROGRESS


def _make_session(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "phase": "chat",
        "active_agent": "phaser",
        "working_dir": None,
        "code_review": None,
        "brainstormer_state": STATE_IN_PROGRESS,
        "brainstormer_messages": [],
        "vision_statement": None,
        "stack_advisor_messages": [],
        "stack_advisor_state": STATE_IN_PROGRESS,
        "stack_statement": None,
        "phaser_messages": [],
        "phaser_state": None,
        "phases": [],
        "llm_config": {"model": "gpt-4o-mini", "api_key": "sk-test"},
        "tavily_api_key": None,
    }
    defaults.update(overrides)
    return dict(defaults)


def _collect(gen: Iterable[str]) -> str:
    return "".join(gen)


def _seed_for(session: dict[str, Any]) -> str:
    """Run the opening turn with a stubbed stream and return the seed."""
    with patch("spec4.llm.stream_turn") as stream:
        stream.return_value = iter(["ok"])
        _collect(phaser.run(None, session, session["llm_config"]))
    return session["phaser_messages"][0]["content"]


_VISION = {"name": "FareBox", "vision": "fare calculator"}
_STACK = {
    "stack_spec": {
        "libraries": [
            {"name": "React Hook Form", "serves_features": ["fare_lookup"]}
        ]
    }
}
_SPECS = {
    "features": [{"id": "fare_lookup", "purpose": "look up fares"}],
    "nfr_goals": ["Lookups are fast."],
}


def test_seed_carries_spine_and_digest_in_order() -> None:
    session = _make_session(
        vision_statement=_VISION,
        stack_statement=_STACK,
        feature_specs=_SPECS,
    )
    seed = _seed_for(session)
    spine = seed.index("Feature specifications (from Brainstormer)")
    paste = seed.index("Here is the technology stack spec")
    digest = seed.index("Stack signal digest")
    assert seed.index("vision statement") < spine < paste < digest
    # spine content: behavioural spec + nfr id from the shared slug rule
    assert "id: `fare_lookup`" in seed
    assert "`nfr_lookups_are_fast_`" in seed
    # digest content: the backlink derived from serves_features
    assert "- `fare_lookup`: React Hook Form (libraries)" in seed


def test_seed_without_specs_or_stack_omits_those_blocks() -> None:
    session = _make_session(vision_statement=_VISION)
    seed = _seed_for(session)
    assert "Feature specifications (from Brainstormer)" not in seed
    assert "Stack signal digest" not in seed
    assert "vision statement" in seed


def test_seed_carries_manifest_projection_when_manifest_on_disk(
    tmp_path: Path,
) -> None:
    design = tmp_path / ".spec4" / "v0" / "design"
    design.mkdir(parents=True)
    (design / "manifest.json").write_text(
        json.dumps({
            "surfaces": [
                {
                    "name": "fare_lookup_form",
                    "kind": "non_ai",
                    "screen": "commuter_main",
                    "implements_feature_ids": ["fare_lookup"],
                }
            ]
        }),
        encoding="utf-8",
    )
    session = _make_session(
        vision_statement=_VISION,
        working_dir=str(tmp_path),
        phase_version=0,
    )
    seed = _seed_for(session)
    assert "UI design manifest (from Designer)" in seed
    assert "- `fare_lookup_form` [non_ai]" in seed
    # mock note still rides alongside the projection
    assert "No UI design mock was produced" in seed


def test_seed_without_manifest_keeps_only_the_mock_note(tmp_path: Path) -> None:
    (tmp_path / ".spec4" / "v0" / "design").mkdir(parents=True)
    session = _make_session(
        vision_statement=_VISION,
        working_dir=str(tmp_path),
        phase_version=0,
    )
    seed = _seed_for(session)
    assert "UI design manifest (from Designer)" not in seed
    assert "No UI design mock was produced" in seed


def test_load_design_manifest_tolerates_bad_json(tmp_path: Path) -> None:
    # D-PH5b: the single shared loader (seed projection + save-time attach).
    from spec4.project_manager import load_design_manifest

    design = tmp_path / ".spec4" / "v0" / "design"
    design.mkdir(parents=True)
    (design / "manifest.json").write_text("{not json", encoding="utf-8")
    assert load_design_manifest(tmp_path, 0) is None
    assert load_design_manifest(tmp_path, 1) is None  # missing version dir

# --- D-PH2i: failure observability ------------------------------------------


def test_appears_truncated_detects_unterminated_tail() -> None:
    complete = '```json\n{"phase_number": 1, "total_phases": 1}\n```'
    truncated = complete + '\n```json\n{"phase_number": 2, "instructions": ["cut of'
    assert not phaser._appears_truncated(complete)
    assert phaser._appears_truncated(truncated)


def test_appears_truncated_ignores_mid_text_junk() -> None:
    # Junk braces recovered by a later complete object are not truncation.
    text = 'note {broken \n```json\n{"phase_number": 1, "total_phases": 1}\n```'
    assert not phaser._appears_truncated(text)


def test_final_failure_message_carries_specifics(tmp_path: Path) -> None:
    """When both attempts fail validation, the fallback names the failures."""
    bad_phase = (
        '```json\n{"phase_number": 1, "total_phases": 1, '
        '"phase_title": "T", "phase_summary": "S"}\n```'
    )  # missing most required keys -> schema failures
    session = _make_session(
        vision_statement=_VISION,
        phaser_messages=[
            {"role": "user", "content": "seed"},
            {"role": "assistant", "content": "outline"},
        ],
    )
    with patch("spec4.llm.stream_turn") as stream, patch(
        "spec4.llm.supports_response_format", return_value=False
    ):
        # Both the visible emission and the silent retry return the same bad JSON.
        def fake_stream(system, messages, *a, **k):
            messages.append({"role": "assistant", "content": bad_phase})
            return iter([bad_phase])

        stream.side_effect = fake_stream
        _collect(phaser.run("LGTM", session, session["llm_config"]))
    fallback = session["_display_override"]
    assert "specific failures" in fallback
    assert "required property" in fallback
    # the fallback replaced the bad JSON as the last assistant message, so a
    # later "try again" turn sees the specifics
    assert session["phaser_messages"][-1]["content"] == fallback

def test_silent_retry_yields_status_line_and_prompt_names_coordinators() -> None:
    """D-PH2l: the corrective retry announces itself in the visible stream.
    D-PH6: the declaring rules state the coordinator-declaration rule."""
    assert "wiring members together IS building the coordinator" in (
        phaser.SYSTEM_PROMPT
    )
    bad_phase = (
        '```json\n{"phase_number": 1, "total_phases": 1, '
        '"phase_title": "T", "phase_summary": "S"}\n```'
    )
    session = _make_session(
        vision_statement=_VISION,
        phaser_messages=[
            {"role": "user", "content": "seed"},
            {"role": "assistant", "content": "outline"},
        ],
    )
    with patch("spec4.llm.stream_turn") as stream, patch(
        "spec4.llm.supports_response_format", return_value=False
    ):
        def fake_stream(system, messages, *a, **k):
            messages.append({"role": "assistant", "content": bad_phase})
            return iter([bad_phase])

        stream.side_effect = fake_stream
        visible = _collect(phaser.run("LGTM", session, session["llm_config"]))
    assert "Validating phase structure — re-emitting with corrections" in visible

def test_seed_vision_block_states_supersession() -> None:
    """D-PH7a: the vision paste announces that later inputs supersede it.

    The vision is the one channel that still presents pre-decision text (an
    excluded feature listed as MVP/differentiator induced a live re-ask); the
    framing rides the vision block itself, so it only appears with a vision.
    """
    seed = _seed_for(_make_session(vision_statement=_VISION))
    assert "predates every planning input that follows" in seed
    assert "supersede the vision wherever the two disagree" in seed
    assert "grounds to revisit or re-ask" in seed
    bare = _seed_for(_make_session(vision_statement=None))
    assert "predates every planning input" not in bare


def test_prompt_hardened_exclusion_and_addition_join_keys() -> None:
    """D-PH7b: the exclusion rule governs even against the vision text and
    never offers re-inclusion. D-PH7d: the stack_addition schema carries the
    serves/NFR join keys and instructs filling them."""
    sp = phaser.SYSTEM_PROMPT
    assert "governs even against the vision statement" in sp
    assert "present re-inclusion as an option you can carry out" in sp
    assert "the only path to re-inclusion" in sp
    assert '"serves_features": ["<product feature id>"]' in sp
    assert '"serves_capabilities": ["<AI catalog node id>"]' in sp
    assert '"satisfies_nfr": ["<nfr_... goal id>"]' in sp
    assert "fill every one that applies" in sp
    assert '"serves_features": ["recipe_search"]' in sp


def test_retry_drain_publishes_cumulative_received_count() -> None:
    """D-PH9: the silent validation-retry drain publishes a cumulative
    received-character total on the session, which the token counter reads so
    it climbs with real receipt instead of freezing.

    The total is cumulative — attempt-1 text + status line + every retry
    chunk — never per-attempt (which would visibly reset to ~0 at retry
    start). The drain's JSON body stays swallowed; no heartbeat dots.
    """
    bad_phase = (
        '```json\n{"phase_number": 1, "total_phases": 1, '
        '"phase_title": "T", "phase_summary": "S"}\n```'
    )
    session = _make_session(
        vision_statement=_VISION,
        phaser_messages=[
            {"role": "user", "content": "seed"},
            {"role": "assistant", "content": "outline"},
        ],
    )
    calls = {"n": 0}
    n_retry_chunks = 120

    def fake_stream(system, messages, *a, **k):
        calls["n"] += 1
        messages.append({"role": "assistant", "content": bad_phase})
        if calls["n"] == 1:
            return iter([bad_phase])
        # The drained retry body: content chunks the user must never see.
        return iter(["x"] * n_retry_chunks)

    with patch("spec4.llm.stream_turn", side_effect=fake_stream), patch(
        "spec4.llm.supports_response_format", return_value=False
    ):
        visible = _collect(phaser.run("LGTM", session, session["llm_config"]))
    assert "Validating phase structure" in visible
    assert "xxxxx" not in visible  # the drain's body is still swallowed
    received = session["_stream_received_chars"]
    assert isinstance(received, int)
    # Cumulative: carries the attempt-1 text AND every retry chunk, proving it
    # is not a per-attempt count reset at the retry boundary.
    assert received >= len(bad_phase) + n_retry_chunks
