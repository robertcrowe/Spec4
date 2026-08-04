"""Unit tests for Phaser stack write-back: the shared merge helper and the
acknowledgment-turn block extractor/stripper (pure logic only).

The prompt-driven emission of ``stack_addition`` blocks is LLM-dependent and
verified by an in-app Haiku draw, not here.
"""

from __future__ import annotations

from spec4.agents.phaser import _extract_and_strip_stack_additions
from spec4.project_manager import merge_library_additions


# --- merge_library_additions -----------------------------------------------


def test_merge_adds_entry_to_tier_in_wrapped_stack():
    stack = {"stack_spec": {"libraries": {"backend": [{"name": "FastAPI"}]}}}
    out = merge_library_additions(
        stack,
        [{"name": "APScheduler", "tier": "backend",
          "category": "scheduler", "purpose": "jobs"}],
    )
    backend = out["stack_spec"]["libraries"]["backend"]
    names = [lib["name"] for lib in backend]
    assert names == ["FastAPI", "APScheduler"]
    added = backend[-1]
    assert added["category"] == "scheduler" and added["purpose"] == "jobs"


def test_merge_dedup_by_name_case_insensitive():
    stack = {"stack_spec": {"libraries": {"backend": [{"name": "httpx"}]}}}
    out = merge_library_additions(
        stack, [{"name": "HTTPX", "tier": "backend", "purpose": "client"}]
    )
    assert len(out["stack_spec"]["libraries"]["backend"]) == 1


def test_merge_keeps_same_category_different_name():
    # Two external_api entries (Open Food Facts + Spoonacular) are both legit.
    stack = {
        "stack_spec": {
            "libraries": {
                "backend": [
                    {"name": "Open Food Facts API", "category": "external_api"}
                ]
            }
        }
    }
    out = merge_library_additions(
        stack,
        [{"name": "Spoonacular API", "tier": "backend", "category": "external_api"}],
    )
    names = [lib["name"] for lib in out["stack_spec"]["libraries"]["backend"]]
    assert names == ["Open Food Facts API", "Spoonacular API"]


def test_merge_is_idempotent():
    stack = {"stack_spec": {"libraries": {"frontend": []}}}
    add = [{"name": "axios", "tier": "frontend"}]
    once = merge_library_additions(stack, add)
    twice = merge_library_additions(once, add)
    assert twice == once
    assert len(twice["stack_spec"]["libraries"]["frontend"]) == 1


def test_merge_does_not_mutate_input():
    stack = {"stack_spec": {"libraries": {"backend": [{"name": "FastAPI"}]}}}
    before = len(stack["stack_spec"]["libraries"]["backend"])
    merge_library_additions(stack, [{"name": "New", "tier": "backend"}])
    assert len(stack["stack_spec"]["libraries"]["backend"]) == before


def test_merge_creates_missing_tier():
    stack = {"stack_spec": {"libraries": {}}}
    out = merge_library_additions(
        stack, [{"name": "expo-notifications", "tier": "frontend"}]
    )
    assert out["stack_spec"]["libraries"]["frontend"][0]["name"] == "expo-notifications"


def test_merge_handles_bare_stack_without_wrapper():
    stack = {"libraries": {"backend": []}}
    out = merge_library_additions(stack, [{"name": "X", "tier": "backend"}])
    assert out["libraries"]["backend"][0]["name"] == "X"


def test_merge_skips_malformed_additions():
    stack = {"stack_spec": {"libraries": {"backend": []}}}
    out = merge_library_additions(
        stack,
        [
            {"name": "", "tier": "backend"},          # no name
            {"name": "Y", "tier": "nonsense"},        # bad tier
            {"tier": "backend"},                      # missing name
            "not a dict",                             # wrong type
            {"name": "Good", "tier": "backend"},      # the only valid one
        ],
    )
    names = [lib["name"] for lib in out["stack_spec"]["libraries"]["backend"]]
    assert names == ["Good"]


def test_merge_none_stack_is_safe():
    out = merge_library_additions(None, [{"name": "X", "tier": "backend"}])
    assert out["libraries"]["backend"][0]["name"] == "X"


# --- _extract_and_strip_stack_additions ------------------------------------


def test_extract_pulls_block_and_strips_it():
    text = (
        "Got it — I'll add Spoonacular for recipe lookups.\n\n"
        '{"stack_addition": {"name": "Spoonacular API", "tier": "backend", '
        '"category": "external_api", "purpose": "recipe suggestions"}}\n\n'
        "Anything else before I draft the phases?"
    )
    additions, cleaned = _extract_and_strip_stack_additions(text)
    assert len(additions) == 1
    assert additions[0]["name"] == "Spoonacular API"
    assert "stack_addition" not in cleaned
    assert "Spoonacular API" not in cleaned
    assert "I'll add Spoonacular" in cleaned
    assert "draft the phases" in cleaned


def test_extract_multiple_blocks():
    text = (
        '{"stack_addition": {"name": "A", "tier": "backend"}}\n'
        '{"stack_addition": {"name": "B", "tier": "frontend"}}'
    )
    additions, cleaned = _extract_and_strip_stack_additions(text)
    assert [a["name"] for a in additions] == ["A", "B"]
    assert cleaned == ""


def test_extract_ignores_phase_objects():
    text = '{"phase_number": 1, "phase_title": "Steel Thread"}'
    additions, cleaned = _extract_and_strip_stack_additions(text)
    assert additions == []
    assert cleaned == text


def test_extract_no_block_returns_text_unchanged():
    text = "Just a normal clarifying question. (yes/no)"
    additions, cleaned = _extract_and_strip_stack_additions(text)
    assert additions == []
    assert cleaned == text


def test_extract_tolerates_prose_around_block():
    text = (
        "Sure.\n"
        '{"stack_addition": {"name": "APScheduler", "tier": "backend"}}\n'
        "Done."
    )
    additions, cleaned = _extract_and_strip_stack_additions(text)
    assert additions[0]["name"] == "APScheduler"
    assert "Sure." in cleaned and "Done." in cleaned
    assert "APScheduler" not in cleaned


def test_extracted_additions_feed_merge_cleanly():
    text = '{"stack_addition": {"name": "APScheduler", "tier": "backend", "category": "scheduler"}}'  # noqa: E501
    additions, _ = _extract_and_strip_stack_additions(text)
    out = merge_library_additions({"stack_spec": {"libraries": {}}}, additions)
    assert out["stack_spec"]["libraries"]["backend"][0]["name"] == "APScheduler"


def test_extract_unwraps_wrapped_stack_addition():
    # The same wrapper pathology as phases: the model nests the block inside an
    # outer object/array. A top-level-only check misses it, so the library never
    # reaches the stack.
    text = (
        "Adding the toast library.\n"
        '{"additions": [{"stack_addition": {"name": "toastify-js", '
        '"tier": "frontend", "category": "notifications"}}]}\n'
        "Drafting phases now."
    )
    additions, cleaned = _extract_and_strip_stack_additions(text)
    assert [a["name"] for a in additions] == ["toastify-js"]
    assert "toastify-js" not in cleaned
    assert "stack_addition" not in cleaned
    assert "Adding the toast library." in cleaned
    assert "Drafting phases now." in cleaned


def test_extract_wrapper_with_phases_is_collected_but_not_stripped():
    # A combined wrapper carrying both a stack_addition and phase blocks must
    # still yield the addition, but must NOT be stripped — stripping it would
    # delete the phase blocks before the phase extractor runs on the same text.
    text = (
        '{"stack_addition": {"name": "toastify-js", "tier": "frontend"}, '
        '"phases": [{"phase_number": 1, "phase_title": "Wire toast"}]}'
    )
    additions, cleaned = _extract_and_strip_stack_additions(text)
    assert [a["name"] for a in additions] == ["toastify-js"]
    # Untouched: the phase blocks survive in the text for downstream extraction.
    assert cleaned == text
    assert '"phase_number": 1' in cleaned


# --- D-PH7d: join-key preservation ------------------------------------------


def test_merge_preserves_join_keys():
    merged = merge_library_additions(
        {"stack_spec": {"libraries": {"backend": []}}},
        [{
            "name": "SendGrid",
            "tier": "backend",
            "category": "external_api",
            "purpose": "transactional email for approved replies",
            "serves_features": ["reply_flow"],
            "serves_capabilities": ["draft_reply_generation"],
            "satisfies_nfr": ["nfr_send_replies_without_leaving_the_app"],
        }],
    )
    lib = merged["stack_spec"]["libraries"]["backend"][0]
    assert lib["serves_features"] == ["reply_flow"]
    assert lib["serves_capabilities"] == ["draft_reply_generation"]
    assert lib["satisfies_nfr"] == [
        "nfr_send_replies_without_leaving_the_app"
    ]


def test_merge_sanitizes_join_keys():
    # Non-string items and blanks are dropped; a key with nothing surviving
    # (or a non-list value) is omitted rather than carried as noise.
    merged = merge_library_additions(
        {},
        [{
            "name": "Lib",
            "tier": "backend",
            "serves_features": ["  ok  ", "", 7, None],
            "serves_capabilities": [],
            "satisfies_nfr": "nfr_not_a_list",
        }],
    )
    lib = merged["libraries"]["backend"][0]
    assert lib["serves_features"] == ["ok"]
    assert "serves_capabilities" not in lib
    assert "satisfies_nfr" not in lib


def test_extract_carries_join_keys_through_merge():
    text = (
        "Approved.\n"
        '{"stack_addition": {"name": "SendGrid", "tier": "backend", '
        '"category": "external_api", "purpose": "sending approved replies", '
        '"serves_features": ["reply_flow"], "satisfies_nfr": ["nfr_x"]}}\n'
    )
    additions, cleaned = _extract_and_strip_stack_additions(text)
    assert additions[0]["satisfies_nfr"] == ["nfr_x"]
    assert "stack_addition" not in cleaned
    merged = merge_library_additions({"stack_spec": {}}, additions)
    lib = merged["stack_spec"]["libraries"]["backend"][0]
    assert lib["serves_features"] == ["reply_flow"]
    assert lib["satisfies_nfr"] == ["nfr_x"]


def test_merged_keyed_addition_routes_instead_of_stapling():
    # The SendGrid defect class (D-PH7 finding 2): with the join keys
    # preserved through the merge, the addition no longer classifies as a
    # baseline staple rendered into every phase, and its NFR claim is seen
    # by the threading walk — the every-phase misrender and the forever-
    # orphaned goal both close.
    from spec4.stack_routing import (
        baseline_library_names,
        nfr_threads,
        stack_signal_entries,
    )

    stack = merge_library_additions(
        {"stack_spec": {"libraries": {"backend": [{"name": "FastAPI"}]}}},
        [{
            "name": "SendGrid",
            "tier": "backend",
            "serves_features": ["reply_flow"],
            "satisfies_nfr": ["nfr_send_replies_without_leaving_the_app"],
        }],
    )
    staples = baseline_library_names(stack)
    assert "FastAPI" in staples
    assert "SendGrid" not in staples
    assert "SendGrid" in [e["label"] for e in stack_signal_entries(stack)]
    threads = nfr_threads(
        stack, {"nfr_goals": ["Send replies without leaving the app"]}
    )
    assert len(threads) == 1
    assert threads[0]["claimers"] == ["SendGrid"]
    assert threads[0]["serves_features"] == {"reply_flow"}
    assert threads[0]["global"] is False
