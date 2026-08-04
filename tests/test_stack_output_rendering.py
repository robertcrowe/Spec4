"""Unit tests for StackAdvisor output shape (D-SA4 / D-SA5 / D-SA6).

Two things are asserted here, both pure and LLM-independent:

* ``_format_stack_as_text`` renders the three new blocks — ``providers``,
  ``infrastructure``, and per-entry ``serves_features`` — and, crucially, omits
  them entirely for a stack that carries none (the no-AI / deterministic-only
  invariant: a non-AI stack spec looks exactly as it did before).
* The SYSTEM_PROMPT carries the new gated topics and the feature-linkage
  directive. The model's actual emission is an in-app draw, not asserted here;
  these guard against accidental removal of the instructions that drive it.
"""

from __future__ import annotations

from typing import Any

from spec4.agents.stack_advisor import SYSTEM_PROMPT, _format_stack_as_text


def _wrap(spec: dict[str, Any]) -> dict[str, Any]:
    return {"stack_spec": spec}


# --- rendering the new blocks ----------------------------------------------


def test_providers_block_renders() -> None:
    out = _format_stack_as_text(
        _wrap(
            {
                "name": "X",
                "providers": {
                    "OpenAI": {
                        "capabilities": [
                            {
                                "tier": "single_call",
                                "capability_class": "fast cheap model",
                                "role": "primary",
                            }
                        ],
                        "credentials_env": "OPENAI_API_KEY",
                        "fallback": "Claude",
                    }
                },
            }
        )
    )
    assert "**Providers:**" in out
    assert "OpenAI" in out
    assert "single_call: fast cheap model (primary)" in out
    assert "Credentials Env: OPENAI_API_KEY" in out
    assert "Fallback: Claude" in out


def test_infrastructure_block_renders_with_serves() -> None:
    out = _format_stack_as_text(
        _wrap(
            {
                "name": "X",
                "infrastructure": {
                    "vector_index": {
                        "choice": "Qdrant",
                        "serves_features": ["meaning_search"],
                    }
                },
            }
        )
    )
    assert "**Infrastructure:**" in out
    assert "vector_index: Qdrant" in out
    assert "Serves Features: `meaning_search`" in out


def test_library_serves_features_renders() -> None:
    out = _format_stack_as_text(
        _wrap(
            {
                "name": "X",
                "libraries": [
                    {
                        "name": "qdrant-client",
                        "purpose": "vector client",
                        "language": "Python",
                        "category": "database client",
                        "serves_features": ["meaning_search"],
                    }
                ],
            }
        )
    )
    assert "qdrant-client — vector client [Python, database client]" in out
    assert "Serves Features: `meaning_search`" in out


# --- omit-when-empty invariant (no-AI / deterministic-only) ----------------


def test_non_ai_stack_has_no_provider_or_infra_sections() -> None:
    out = _format_stack_as_text(
        _wrap(
            {
                "name": "X",
                "languages": ["Python"],
                "libraries": {"backend": [{"name": "FastAPI", "purpose": "api"}]},
            }
        )
    )
    assert "**Providers:**" not in out
    assert "**Infrastructure:**" not in out
    assert "(serves:" not in out
    assert "FastAPI — api" in out


def test_general_library_without_serves_renders_plain() -> None:
    out = _format_stack_as_text(
        _wrap(
            {"name": "X", "libraries": {"backend": [{"name": "pytest",
             "purpose": "tests"}]}}
        )
    )
    assert "pytest — tests" in out
    assert "serves:" not in out


# --- prompt-shape guards ----------------------------------------------------


def test_prompt_has_gated_provider_topic() -> None:
    assert "3. **Provider and model**" in SYSTEM_PROMPT
    assert "served" in SYSTEM_PROMPT
    assert "in-process" in SYSTEM_PROMPT
    assert "endpoint_env" in SYSTEM_PROMPT
    assert "capability_class" in SYSTEM_PROMPT
    # D-SC39: the tier is a checkable value, and the nine names are stated.
    assert "exactly one of the nine catalog tiers" in SYSTEM_PROMPT
    assert 'Never invent a label' in SYSTEM_PROMPT
    # D-SC38: role sits on the capability, not the provider.
    assert "Role belongs on the capability" in SYSTEM_PROMPT


def test_prompt_has_gated_infrastructure_topic() -> None:
    # 5 -> 6 (D-SC9 inserted `Data and persistence`), 6 -> 7 (D-SC28 inserted
    # `External integrations`).
    assert "7. **Infrastructure**" in SYSTEM_PROMPT
    assert "Required infrastructure" in SYSTEM_PROMPT


def test_prompt_topics_renumbered() -> None:
    assert "4. **External integrations**" in SYSTEM_PROMPT
    assert "5. **Libraries**" in SYSTEM_PROMPT
    assert "6. **Data and persistence**" in SYSTEM_PROMPT
    assert "8. **Coding style and tooling**" in SYSTEM_PROMPT


def test_prompt_has_feature_linkage_directive() -> None:
    assert "serves_features" in SYSTEM_PROMPT
    assert "serves_capabilities" in SYSTEM_PROMPT
    assert "**Feature linkage — two id spaces, two fields.**" in SYSTEM_PROMPT


def test_prompt_schema_example_carries_new_blocks() -> None:
    assert '"providers"' in SYSTEM_PROMPT
    assert '"infrastructure"' in SYSTEM_PROMPT
    assert '"capabilities"' in SYSTEM_PROMPT
    assert '"tier": "single_call"' in SYSTEM_PROMPT


# --- ai_conventions block (prompt_versioning) -------------------------------


def test_ai_conventions_block_renders() -> None:
    out = _format_stack_as_text(
        _wrap(
            {
                "name": "X",
                "ai_conventions": {
                    "prompt_versioning": "versioned files under prompts/, semver"
                },
            }
        )
    )
    assert "**AI conventions:**" in out
    assert "Prompt Versioning: versioned files under prompts/, semver" in out


def test_non_ai_stack_has_no_ai_conventions_section() -> None:
    out = _format_stack_as_text(
        _wrap({"name": "X", "libraries": {"backend": [{"name": "FastAPI"}]}})
    )
    assert "**AI conventions:**" not in out


def test_prompt_has_prompt_versioning_directive() -> None:
    assert "**Prompt versioning**" in SYSTEM_PROMPT
    assert "ai_conventions.prompt_versioning" in SYSTEM_PROMPT


def test_prompt_has_tool_protocol_directive() -> None:
    assert "tool protocol strategy" in SYSTEM_PROMPT.lower()


def test_prompt_schema_example_carries_ai_conventions() -> None:
    assert '"ai_conventions"' in SYSTEM_PROMPT
