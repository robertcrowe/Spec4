"""D-SC18 — the stack survives a schema-deviant model response.

Two faults, observed together on a live FareBox draw that crashed three attempts
running:

* **Shape.** The pre-D-SC27 schema asked for ``libraries`` keyed by category; a
  frontend-only app has no backend/frontend split to make and the model emitted a
  bare list. ``_format_stack_as_text`` keyed over four top-level blocks with
  unguarded ``.items()``, so the list was an ``AttributeError`` 31 chunks into the
  stream. D-SC18b normalises the shape once at extraction, so every downstream
  consumer — session, ``stack.json``, Phaser, the probes — sees one shape.

  D-SC27 then made the flat list the schema's own shape (category and language are
  values on each entry, not keys above them), so the coercion runs the other way:
  a category-keyed object folds down into the list. FareBox had been emitting the
  right shape all along.

* **Write order.** ``STATE_STACK_COMPLETE`` was set *before* the render that
  threw, and that flag is the sole gate on ``save_stack`` (``session.py``). So a
  crashed turn still wrote its stack to disk: an error to the developer, a
  success to the pipeline. D-SC18a renders first and commits second, in the three
  agents that had the pattern (stack_advisor, code_scanner, phaser).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from spec4.agents import stack_advisor
from spec4.agents.stack_advisor import (
    _extract_stack_json,
    _format_stack_as_text,
    _normalise_stack_shape,
)
from spec4.app_constants import STATE_STACK_COMPLETE

from .test_agents import collect, make_session, mock_litellm_stream

# --- the exact shape that crashed the live draw ----------------------------

_FAREBOX_FLAT = {
    "stack_spec": {
        "name": "FareBox",
        "languages": ["TypeScript"],
        "libraries": [
            {"name": "React", "purpose": "UI framework", "foundational": True},
            {
                "name": "idb",
                "purpose": "IndexedDB persistence",
                "serves_features": ["trip_history", "saved_trips"],
            },
        ],
    }
}


def _fenced(spec: dict[str, Any]) -> str:
    return "Here is the stack.\n```json\n" + json.dumps(spec) + "\n```"


# --- D-SC18b: shape normalisation ------------------------------------------


def test_flat_libraries_list_passes_through_untouched() -> None:
    """D-SC27: the flat list is now the schema's shape, so nothing coerces it."""
    out = _normalise_stack_shape(json.loads(json.dumps(_FAREBOX_FLAT)))
    libs = out["stack_spec"]["libraries"]
    assert isinstance(libs, list)
    assert [entry["name"] for entry in libs] == ["React", "idb"]


def test_flat_libraries_keeps_annotations_intact() -> None:
    out = _normalise_stack_shape(json.loads(json.dumps(_FAREBOX_FLAT)))
    idb = out["stack_spec"]["libraries"][1]
    assert idb["serves_features"] == ["trip_history", "saved_trips"]


def test_keyed_libraries_fold_into_the_flat_list() -> None:
    """The category key becomes the entry's ``category`` value (D-SC27)."""
    spec = {
        "stack_spec": {
            "libraries": {
                "backend": [{"name": "FastAPI", "purpose": "api"}],
                "frontend": [{"name": "React"}],
            }
        }
    }
    libs = _normalise_stack_shape(spec)["stack_spec"]["libraries"]
    assert libs == [
        {"name": "FastAPI", "purpose": "api", "category": "backend"},
        {"name": "React", "category": "frontend"},
    ]


def test_folding_does_not_overwrite_an_explicit_category() -> None:
    spec = {
        "stack_spec": {
            "libraries": {"backend": [{"name": "Pino", "category": "logging"}]}
        }
    }
    libs = _normalise_stack_shape(spec)["stack_spec"]["libraries"]
    assert libs[0]["category"] == "logging"


def test_provider_list_is_keyed_by_name() -> None:
    spec = {
        "stack_spec": {
            "providers": [
                {"name": "Anthropic Claude", "credentials_env": "K"},
                {"provider": "Ollama"},
            ]
        }
    }
    out = _normalise_stack_shape(spec)["stack_spec"]["providers"]
    assert list(out) == ["Anthropic Claude", "Ollama"]
    assert out["Anthropic Claude"]["credentials_env"] == "K"


def test_infrastructure_list_is_keyed() -> None:
    spec = {"stack_spec": {"infrastructure": [{"component": "vector_index"}]}}
    out = _normalise_stack_shape(spec)["stack_spec"]["infrastructure"]
    assert list(out) == ["vector_index"]


def test_ai_conventions_list_is_keyed() -> None:
    spec = {"stack_spec": {"ai_conventions": [{"name": "prompt_versioning"}]}}
    out = _normalise_stack_shape(spec)["stack_spec"]["ai_conventions"]
    assert list(out) == ["prompt_versioning"]


def test_nameless_entries_get_positional_keys() -> None:
    spec = {"stack_spec": {"providers": [{"x": 1}, {"y": 2}]}}
    out = _normalise_stack_shape(spec)["stack_spec"]["providers"]
    assert list(out) == ["provider_1", "provider_2"]


def test_duplicate_names_do_not_collide() -> None:
    spec = {"stack_spec": {"providers": [{"name": "X", "i": 1}, {"name": "X", "i": 2}]}}
    out = _normalise_stack_shape(spec)["stack_spec"]["providers"]
    assert len(out) == 2
    assert sorted(v["i"] for v in out.values()) == [1, 2]


def test_unwrapped_spec_is_normalised_too() -> None:
    spec = {"stack": {"libraries": {"frontend": [{"name": "React"}]}}}
    assert _normalise_stack_shape(spec)["stack"]["libraries"] == [
        {"name": "React", "category": "frontend"}
    ]


def test_non_dict_body_is_left_alone() -> None:
    spec = {"stack": "not a mapping"}
    assert _normalise_stack_shape(spec) == {"stack": "not a mapping"}


def test_extract_normalises_and_formatter_survives() -> None:
    """The end-to-end regression: this pair is what crashed the live draw."""
    spec = _extract_stack_json(_fenced(_FAREBOX_FLAT))
    assert spec is not None
    out = _format_stack_as_text(spec)  # raised AttributeError before D-SC18b
    assert "React" in out and "idb" in out


def test_extract_still_rejects_a_non_stack_payload() -> None:
    assert _extract_stack_json("```json\n{\"unrelated\": 1}\n```") is None


# --- D-SC18a: state is committed only after the render succeeds -------------


def _stack_session() -> dict[str, Any]:
    return make_session(
        active_agent="stack_advisor",
        vision_statement={"name": "FareBox", "vision": "fares"},
        stack_advisor_messages=[{"role": "user", "content": "seed"}],
    )


def test_flat_libraries_no_longer_crashes_the_turn() -> None:
    session = _stack_session()
    with mock_litellm_stream(_fenced(_FAREBOX_FLAT)):
        collect(stack_advisor.run("go", session, session["llm_config"]))
    assert session["stack_advisor_state"] == STATE_STACK_COMPLETE
    libs = session["stack_statement"]["stack_spec"]["libraries"]
    assert [entry["name"] for entry in libs] == ["React", "idb"]


def test_render_failure_leaves_no_completion_state() -> None:
    """A crashed render must not leave the save gate open (session.py)."""
    session = _stack_session()
    with mock_litellm_stream(_fenced(_FAREBOX_FLAT)):
        with patch.object(
            stack_advisor, "_format_stack_as_text", side_effect=RuntimeError("boom")
        ):
            with pytest.raises(RuntimeError):
                collect(stack_advisor.run("go", session, session["llm_config"]))
    assert session.get("stack_advisor_state") != STATE_STACK_COMPLETE
    assert not session.get("stack_statement")


def test_render_failure_leaves_no_display_override() -> None:
    session = _stack_session()
    with mock_litellm_stream(_fenced(_FAREBOX_FLAT)):
        with patch.object(
            stack_advisor, "_format_stack_as_text", side_effect=RuntimeError("boom")
        ):
            with pytest.raises(RuntimeError):
                collect(stack_advisor.run("go", session, session["llm_config"]))
    assert not session.get("_display_override")
    assert not session.get("stack_advisor_artifact_msg_count")


def test_successful_render_still_commits_everything() -> None:
    session = _stack_session()
    keyed = {
        "stack_spec": {"name": "X", "libraries": {"frontend": [{"name": "React"}]}}
    }
    with mock_litellm_stream(_fenced(keyed)):
        collect(stack_advisor.run("go", session, session["llm_config"]))
    assert session["stack_advisor_state"] == STATE_STACK_COMPLETE
    assert session["stack_statement"]["stack_spec"]["name"] == "X"
    assert session["_display_override"]
    assert session["stack_advisor_artifact_msg_count"]
