"""The per-consumer ``code_review`` view (D-CR series).

Brownfield's input used to be a raw ``json.dumps(code_review)`` paste; the
probe (``evals/code_scanner/review_reach.py``) showed StackAdvisor copying the
prompt exemplar's toolchain over the review's in eight rounds out of eight.
These tests pin the deterministic view that replaces the paste: a tuple
renders only its fields, in order; unknown shapes fall through to the generic
walker (renderer totality); an absent, empty or not-a-software-project review
renders nothing; provenance rides along; and one representative review is
golden-pinned. The seed tests then check that StackAdvisor's brownfield seed
carries the view — with the review's own linter in it — and not the JSON.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from spec4.agents import stack_advisor
from spec4.agents import phaser
from spec4.agents._code_review_context import (
    EXCLUDED_PATHS,
    FIELD_GUIDANCE,
    PHASER_FIELD_GUIDANCE,
    PHASER_REVIEW_FIELDS,
    STACK_REVIEW_FIELDS,
    render_code_review,
)
from tests._agent_helpers import collect, make_session, mock_litellm_stream
from tests._chunks import make_stream_chunk
from tests._golden import assert_golden, load_fixture


def _review(**fields: Any) -> dict[str, Any]:
    return {"code_review": {"schema_version": 1, "is_software_project": True, **fields}}


# ---------------------------------------------------------------------------
# render_code_review
# ---------------------------------------------------------------------------


class TestRenderCodeReview:
    def test_absent_review_renders_empty(self) -> None:
        assert render_code_review(None, STACK_REVIEW_FIELDS) == ""
        assert render_code_review({}, STACK_REVIEW_FIELDS) == ""
        assert render_code_review({"code_review": {}}, STACK_REVIEW_FIELDS) == ""
        assert render_code_review("not a dict", STACK_REVIEW_FIELDS) == ""

    def test_not_a_software_project_renders_empty(self) -> None:
        review = {
            "code_review": {
                "is_software_project": False,
                "summary": "only a bare manifest",
                "languages": [{"name": "Python"}],
            }
        }
        assert render_code_review(review, STACK_REVIEW_FIELDS) == ""

    def test_renders_only_the_tuple_fields_in_tuple_order(self) -> None:
        review = _review(
            commands={"test": "pytest", "deploy": "fly deploy"},
            languages=[{"name": "Python"}],
            entrypoints={"main": "app.py"},
            directory_map=[{"path": "src/", "role": "package"}],
        )
        out = render_code_review(review, ("commands.deploy", "languages"))
        assert out.index("**Existing deploy command**") < out.index(
            "**Existing languages**"
        )
        assert "fly deploy" in out
        assert "pytest" not in out  # commands.test is not in the tuple
        assert "app.py" not in out
        assert "src/" not in out

    def test_bare_review_without_envelope_is_accepted(self) -> None:
        out = render_code_review({"languages": [{"name": "Go"}]}, ("languages",))
        assert "**Go**" in out

    def test_absent_and_empty_fields_are_skipped(self) -> None:
        review = _review(
            languages=[], frameworks=None, auth={}, build_system={"tool": ""}
        )
        assert render_code_review(review, STACK_REVIEW_FIELDS) == ""

    def test_guidance_line_follows_the_heading(self) -> None:
        out = render_code_review(
            _review(coding_style={"linter": "ruff"}), ("coding_style",)
        )
        lines = out.splitlines()
        assert lines[0] == "**Existing coding style**"
        assert lines[1] == f"_{FIELD_GUIDANCE['coding_style']}_"
        assert lines[2] == "- linter: ruff"

    def test_field_without_guidance_has_no_italic_line(self) -> None:
        out = render_code_review(_review(ui_summary={"kind": "spa"}), ("ui_summary",))
        assert out.splitlines() == ["**Existing ui summary**", "- kind: spa"]

    def test_annotated_scalar_unwraps_with_provenance(self) -> None:
        review = _review(
            coding_style={
                "linter": {"value": "oxlint", "source": "frontend/package.json"},
                "indentation": {"value": "2 spaces", "inferred_from": "src/App.tsx"},
            }
        )
        out = render_code_review(review, ("coding_style",))
        assert "- linter: oxlint [frontend/package.json]" in out
        assert "- indentation: 2 spaces [src/App.tsx]" in out
        assert '"value"' not in out

    def test_list_entries_promote_the_primary_key(self) -> None:
        review = _review(
            api_surface=[
                {
                    "protocol": "http",
                    "path_or_method": "GET /health",
                    "handler": "api.health",
                    "source": "main.py",
                }
            ],
            persistence={
                "databases": [{"engine": "PostgreSQL", "role": "primary"}],
                "orm": {"name": "SQLAlchemy", "source": "pyproject.toml"},
                "migrations_path": "db/migrations/",
            },
        )
        out = render_code_review(review, ("api_surface", "persistence"))
        assert (
            "- **GET /health** — protocol: http; handler: api.health [main.py]" in out
        )
        assert "  - **PostgreSQL** — role: primary" in out
        assert "- orm: **SQLAlchemy** [pyproject.toml]" in out
        assert "- migrations path: db/migrations/" in out

    def test_nested_dicts_render_as_nested_bullets(self) -> None:
        review = _review(
            coding_style={
                "naming_conventions": {
                    "functions": "snake_case",
                    "classes": "PascalCase",
                }
            }
        )
        out = render_code_review(review, ("coding_style",))
        assert (
            "- naming conventions:\n  - functions: snake_case\n  - classes: PascalCase"
            in out
        )

    def test_unknown_shapes_fall_through_to_the_generic_walker(self) -> None:
        # Renderer totality: a key the module knows nothing about, holding a
        # shape the schema never described, still reaches the output verbatim.
        review = _review(
            mystery={"depth": {"deeper": [1, True, "three", {"name": "four", "n": 4}]}}
        )
        out = render_code_review(review, ("mystery",))
        assert out.splitlines() == [
            "**Existing mystery**",
            "- depth:",
            "  - deeper:",
            "    - 1",
            "    - yes",
            "    - three",
            "    - **four** — n: 4",
        ]

    def test_bare_string_entries_in_lists_render(self) -> None:
        review = _review(languages=["Python", {"name": "Rust"}, ""])
        out = render_code_review(review, ("languages",))
        assert "- Python" in out
        assert "- **Rust**" in out

    def test_runtime_versions_underscore_source_is_provenance(self) -> None:
        review = _review(
            runtime_versions={"python": ">=3.12", "_source": "pyproject.toml"}
        )
        out = render_code_review(review, ("runtime_versions",))
        assert out.splitlines()[-1] == "- python: >=3.12 [pyproject.toml]"
        assert "_source" not in out

    def test_values_are_verbatim(self) -> None:
        text = "README states the chains 'rot as providers retire slugs'; refresh them"
        review = _review(notes={"change_risks": [{"area": "registry", "risk": text}]})
        out = render_code_review(review, ("notes.change_risks",))
        assert text in out

    def test_stack_tuple_covers_what_the_stack_must_carry_forward(self) -> None:
        # The fields the BWS4 baseline showed as lost or at risk in stack.json.
        for field in (
            "coding_style",
            "runtime_versions",
            "architecture",
            "api_surface",
        ):
            assert field in STACK_REVIEW_FIELDS
        for field in ("commands", "entrypoints", "directory_map", "ui_summary"):
            assert field not in STACK_REVIEW_FIELDS

    def test_guidance_override_replaces_the_shared_line_per_field(self) -> None:
        review = _review(
            persistence={"orm": {"name": "SQLAlchemy"}}, auth={"model": "none"}
        )
        out = render_code_review(
            review,
            ("persistence", "auth"),
            guidance={"persistence": "Phase 1 verifies it."},
        )
        assert "_Phase 1 verifies it._" in out
        assert f"_{FIELD_GUIDANCE['persistence']}_" not in out
        assert f"_{FIELD_GUIDANCE['auth']}_" in out  # untouched by the override

    def test_excluded_sub_keys_are_dropped_from_every_view(self) -> None:
        assert "entrypoints.ui_root" in EXCLUDED_PATHS
        review = _review(entrypoints={"main": "app.py", "ui_root": "index.html"})
        out = render_code_review(review, ("entrypoints",))
        assert "- main: app.py" in out
        assert "index.html" not in out
        # The exclusion never mutates the review itself.
        assert review["code_review"]["entrypoints"]["ui_root"] == "index.html"

    def test_block_of_only_excluded_keys_renders_nothing(self) -> None:
        review = _review(entrypoints={"ui_root": "index.html"})
        assert render_code_review(review, ("entrypoints",)) == ""

    def test_phaser_tuple_covers_the_planning_rules(self) -> None:
        for field in (
            "commands",
            "entrypoints",
            "directory_map",
            "persistence",
            "env_vars",
            "api_surface",
            "protocols_implemented",
            "architecture",
            "notes.incomplete_or_dead_code",
            "notes.change_risks",
        ):
            assert field in PHASER_REVIEW_FIELDS
        assert "coding_style" not in PHASER_REVIEW_FIELDS
        # Every Phaser rule names a field Phaser renders.
        assert set(PHASER_FIELD_GUIDANCE) <= set(PHASER_REVIEW_FIELDS)

    def test_golden_full_review_phaser_view(self) -> None:
        assert_golden(
            "code_review_phaser_view.md",
            render_code_review(
                load_fixture("review_full.json"),
                PHASER_REVIEW_FIELDS,
                guidance=PHASER_FIELD_GUIDANCE,
            ),
        )

    def test_golden_full_review_stack_view(self) -> None:
        assert_golden(
            "code_review_stack_view.md",
            render_code_review(load_fixture("review_full.json"), STACK_REVIEW_FIELDS),
        )


# ---------------------------------------------------------------------------
# StackAdvisor seed
# ---------------------------------------------------------------------------


def _seed_after_run(session: dict[str, Any]) -> str:
    with patch("spec4.llm.litellm.completion") as mock_llm:
        mock_llm.return_value = iter(
            [make_stream_chunk("Ok"), make_stream_chunk("", finish_reason="stop")]
        )
        collect(stack_advisor.run(None, session, session["llm_config"]))
    return session["stack_advisor_messages"][0]["content"]


class TestStackAdvisorSeed:
    def test_brownfield_seed_carries_the_view_not_the_json(self) -> None:
        review = _review(
            languages=[{"name": "TypeScript", "source": "package.json"}],
            coding_style={"linter": {"value": "oxlint", "source": "package.json"}},
        )
        session = make_session(
            active_agent="stack_advisor",
            vision_statement={"vision_statement": {"name": "App"}},
            code_review=review,
            stack_statement=None,
        )
        seed = _seed_after_run(session)
        assert "**Existing coding style**" in seed
        assert "- linter: oxlint [package.json]" in seed
        assert json.dumps(review, indent=2) not in seed
        assert '```json\n{\n  "code_review"' not in seed
        # The conflict-warning instruction and the brownfield ask are kept.
        assert "proactively warn me about the conflict" in seed
        assert "draft an initial stack spec" in seed

    def test_not_a_software_project_review_uses_the_greenfield_seed(self) -> None:
        review = {
            "code_review": {"is_software_project": False, "summary": "bare manifest"}
        }
        session = make_session(
            active_agent="stack_advisor",
            vision_statement={"vision_statement": {"name": "App"}},
            code_review=review,
            stack_statement=None,
        )
        seed = _seed_after_run(session)
        assert "bare manifest" not in seed
        assert "draft an initial stack spec" not in seed
        assert "begin guiding" in seed

    def test_greenfield_seed_has_no_review_block(self) -> None:
        session = make_session(
            active_agent="stack_advisor",
            vision_statement={"vision_statement": {"name": "App"}},
            stack_statement=None,
        )
        seed = _seed_after_run(session)
        assert "**Existing" not in seed
        assert "code review" not in seed


# ---------------------------------------------------------------------------
# Phaser seed
# ---------------------------------------------------------------------------


class TestPhaserSeed:
    def _seed(self, code_review: Any) -> str:
        session = make_session(
            active_agent="phaser",
            vision_statement={"vision_statement": {"name": "App"}},
            stack_statement={"stack_spec": {"name": "App"}},
            code_review=code_review,
        )
        with mock_litellm_stream("Planning."):
            collect(phaser.run(None, session, session["llm_config"]))
        return session["phaser_messages"][0]["content"]

    def test_brownfield_seed_keeps_the_raw_block_and_adds_the_view(self) -> None:
        review = _review(
            commands={"test": "uv run pytest"},
            persistence={"databases": [{"engine": "PostgreSQL"}]},
            protocols_implemented=[{"name": "A2A"}],
            entrypoints={"main": "app/main.py", "ui_root": "index.html"},
        )
        seed = self._seed(review)
        raw = json.dumps(review, indent=2)
        assert raw in seed  # D-CR1 keep-alongside
        view_at = seed.index("Read it through these blocks")
        assert seed.index(raw) < view_at
        # The rules sit under the data they govern.
        assert f"_{PHASER_FIELD_GUIDANCE['persistence']}_" in seed
        assert f"_{PHASER_FIELD_GUIDANCE['protocols_implemented']}_" in seed
        assert "- test: uv run pytest" in seed
        assert "- **PostgreSQL**" in seed
        # The old paragraphs are gone; the raw JSON still carries ui_root.
        assert "If `persistence` is present" not in seed
        assert "index.html" not in seed[view_at:]
        assert "integration/validation thread for the existing code" in seed

    def test_rule_for_an_absent_block_is_not_emitted(self) -> None:
        seed = self._seed(_review(commands={"test": "pytest"}))
        assert PHASER_FIELD_GUIDANCE["commands"] in seed
        assert PHASER_FIELD_GUIDANCE["env_vars"] not in seed
        assert PHASER_FIELD_GUIDANCE["api_surface"] not in seed

    def test_greenfield_seed_has_no_review_blocks(self) -> None:
        seed = self._seed(None)
        assert "code review" not in seed
        assert "**Existing" not in seed
