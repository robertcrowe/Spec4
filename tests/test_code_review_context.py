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
from spec4.agents import brainstormer, phaser
from spec4.agents._code_review_context import (
    BRAINSTORMER_FIELD_GUIDANCE,
    BRAINSTORMER_REVIEW_FIELDS,
    EXCLUDED_PATHS,
    FIELD_GUIDANCE,
    PHASER_FIELD_GUIDANCE,
    PHASER_REVIEW_FIELDS,
    SCAN_PREFIX,
    SCOUT_REVIEW_FIELDS,
    STACK_FIELD_GUIDANCE,
    STACK_REVIEW_FIELDS,
    render_code_review,
    unwrap_review,
    unwrap_scan,
)
from tests._agent_helpers import collect, make_session, mock_litellm_stream
from tests._chunks import make_stream_chunk
from tests._golden import assert_golden, load_fixture
from tests._review_helpers import review_envelope as _review


# ---------------------------------------------------------------------------
# render_code_review
# ---------------------------------------------------------------------------


class TestRenderCodeReview:
    def test_absent_review_renders_empty(self) -> None:
        assert render_code_review(None, STACK_REVIEW_FIELDS) == ""
        assert render_code_review({}, STACK_REVIEW_FIELDS) == ""
        assert render_code_review({"code_review": {}}, STACK_REVIEW_FIELDS) == ""
        assert render_code_review("not a dict", STACK_REVIEW_FIELDS) == ""

    def test_only_the_envelope_shape_is_read(self) -> None:
        # D-EV5: by path only. A bare review dict, a bare ``review`` block
        # and the schema-1 envelope all render nothing; the envelope renders.
        fields = {"languages": [{"name": "Go"}]}
        assert render_code_review(fields, ("languages",)) == ""
        assert render_code_review({"review": fields}, ("languages",)) == ""
        v1 = {"code_review": {"schema_version": 1, **fields}}
        assert render_code_review(v1, ("languages",)) == ""
        assert "**Go**" in render_code_review(_review(**fields), ("languages",))

    def test_unwrap_by_path(self) -> None:
        env = _review(
            languages=[{"name": "Go"}], scan={"inventory": {"files_total": 1}}
        )
        assert unwrap_review(env) == {
            "is_software_project": True,
            "languages": [{"name": "Go"}],
        }
        assert unwrap_scan(env) == {"inventory": {"files_total": 1}}
        for wrong in (
            None,
            "x",
            {},
            {"code_review": "x"},
            {"code_review": {"review": "x"}},
        ):
            assert unwrap_review(wrong) == {}
            assert unwrap_scan(wrong) == {}

    def test_not_a_software_project_renders_empty(self) -> None:
        review = _review(
            is_software_project=False,
            summary="only a bare manifest",
            languages=[{"name": "Python"}],
        )
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
        assert review["code_review"]["review"]["entrypoints"]["ui_root"] == "index.html"

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

    def test_brainstormer_tuple_is_product_facing(self) -> None:
        for field in (
            "existing_self_description",
            "api_surface",
            "ai_capabilities",
            "ui_summary",
            "notes.incomplete_or_dead_code",
        ):
            assert field in BRAINSTORMER_REVIEW_FIELDS
        for field in ("coding_style", "dependencies", "commands", "directory_map"):
            assert field not in BRAINSTORMER_REVIEW_FIELDS
        assert set(BRAINSTORMER_FIELD_GUIDANCE) <= set(BRAINSTORMER_REVIEW_FIELDS)

    def test_scout_tuple_is_identity_plus_the_ai_inventory(self) -> None:
        # D-EV7: what Scout catalogues against, and not Phaser's or the stack's.
        for field in ("ai_capabilities", "frameworks", "dependencies", "api_surface"):
            assert field in SCOUT_REVIEW_FIELDS
        for field in ("commands", "directory_map", "coding_style", "env_vars"):
            assert field not in SCOUT_REVIEW_FIELDS
        assert_golden(
            "code_review_scout_view.md",
            render_code_review(load_fixture("review_full.json"), SCOUT_REVIEW_FIELDS),
        )

    def test_golden_full_review_brainstormer_view(self) -> None:
        assert_golden(
            "code_review_brainstormer_view.md",
            render_code_review(
                load_fixture("review_full.json"),
                BRAINSTORMER_REVIEW_FIELDS,
                guidance=BRAINSTORMER_FIELD_GUIDANCE,
            ),
        )

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
            render_code_review(
                load_fixture("review_full.json"),
                STACK_REVIEW_FIELDS,
                guidance=STACK_FIELD_GUIDANCE,
            ),
        )


# ---------------------------------------------------------------------------
# step 3b: scan. paths and the three arrays in the consumer views (D-SC3-11)
# ---------------------------------------------------------------------------


_STEP3 = "review_with_step3.json"


def _scan_review(scan: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return _review(scan=scan, languages=[{"name": "Go"}], **fields)


class TestScanPaths:
    def test_scan_fields_resolve_against_the_scan_layer_not_the_review(self) -> None:
        # The review carries a ``plan_drift`` key of its own (the walker would
        # happily render it); the scan path must read the scan's.
        review = _scan_review(
            {"plan_drift": {"planned_unmatched": [{"name": "Alembic"}]}},
            plan_drift={"planned_unmatched": [{"name": "WRONG"}]},
        )
        out = render_code_review(review, ("scan.plan_drift.planned_unmatched",))
        assert "**Alembic**" in out
        assert "WRONG" not in out
        # And a review field never reads the scan.
        out = render_code_review(review, ("plan_drift",))
        assert "WRONG" in out
        assert "Alembic" not in out

    def test_scan_headings_say_measured_not_existing(self) -> None:
        review = _scan_review(
            {
                "plan_drift": {
                    "planned_unmatched": [{"name": "Alembic", "sources": ["stack"]}],
                    "declared_not_planned": [{"name": "oxlint", "manifest": "p.json"}],
                },
                "delta": {"dependencies": {"pyproject.toml": {"added": ["x"]}}},
                "coverage": {"source_files_sampled": 2, "source_files_total": 9},
                "inventory": {"files_total": 3},
            }
        )
        fields = (
            "scan.plan_drift.planned_unmatched",
            "scan.plan_drift.declared_not_planned",
            "scan.delta.dependencies",
            "scan.coverage",
            "scan.inventory",
        )
        out = render_code_review(review, fields)
        for heading in (
            "**Planned last round, not found in the code**",
            "**Declared in a manifest, not planned**",
            "**Dependency changes since the prior scan**",
            "**Scan coverage**",
            "**Scan inventory**",  # no override: the generic "Scan <label>"
        ):
            assert heading in out
        assert "**Existing" not in out
        # Every named scan path carries its guidance line, in tuple order.
        for field in fields[:4]:
            assert f"_{FIELD_GUIDANCE[field]}_" in out
        positions = [out.index(FIELD_GUIDANCE[f]) for f in fields[:4]]
        assert positions == sorted(positions)
        assert "- files total: 3" in out

    def test_scan_prefix_is_the_routing_rule(self) -> None:
        assert SCAN_PREFIX == "scan."
        for tup in (PHASER_REVIEW_FIELDS, STACK_REVIEW_FIELDS):
            assert any(f.startswith(SCAN_PREFIX) for f in tup)
        for tup in (BRAINSTORMER_REVIEW_FIELDS, SCOUT_REVIEW_FIELDS):
            assert not any(f.startswith(SCAN_PREFIX) for f in tup)

    def test_absent_scan_or_absent_path_skips_the_field(self) -> None:
        fields = ("languages", "scan.coverage", "scan.plan_drift.planned_unmatched")
        out = render_code_review(_review(languages=[{"name": "Go"}]), fields)
        assert out.splitlines() == [
            "**Existing languages**",
            f"_{FIELD_GUIDANCE['languages']}_",
            "- **Go**",
        ]
        review = _scan_review({"plan_drift": {"planned_unmatched": []}})
        assert "Planned" not in render_code_review(review, fields)
        # A review that is not a software project renders nothing, scan or no.
        review = _review(is_software_project=False, scan={"coverage": {"x": 1}})
        assert render_code_review(review, fields) == ""

    def test_coverage_is_one_line_of_counts(self) -> None:
        cov = {
            "source_files_sampled": 4,
            "source_files_total": 2292,
            "sampled": ["src/app/main.py", "src/app/models.py"],
            "signatures_shown": ["a.py", "b.py", "c.py"],
            "evidence_tokens": 22814,
        }
        out = render_code_review(_scan_review({"coverage": cov}), ("scan.coverage",))
        assert out.splitlines()[-1] == (
            "- 4 of 2292 source files shown as bodies; 3 more as signature "
            "blocks; ~22,814 tokens of evidence"
        )
        assert "src/app/main.py" not in out  # the paths are not the coder's
        # Older scans without the 2.4.0 keys: the two counts alone.
        lean = {"source_files_sampled": 0, "source_files_total": 7, "sampled": []}
        out = render_code_review(_scan_review({"coverage": lean}), ("scan.coverage",))
        assert out.splitlines()[-1] == "- 0 of 7 source files shown as bodies"
        # No counts at all: nothing, not a half line.
        for cov in (
            {"sampled": ["x"]},
            {"source_files_sampled": "4"},
            {"source_files_sampled": 4},  # one count alone is not a line
            {"source_files_total": 9},
            "text",
        ):
            review = _scan_review({"coverage": cov})
            assert render_code_review(review, ("scan.coverage",)) == ""

    def test_dependency_delta_lists_only_the_manifests_that_changed(self) -> None:
        deps = {
            "pyproject.toml": {
                "added": ["pydantic-ai", "structlog"],
                "removed": [],
                "bumped": ["fastapi"],
                "truncated": False,
            },
            "web/package.json": {
                "added": [],
                "removed": [],
                "bumped": [],
                "truncated": False,
            },
            "Cargo.toml": {"added": [], "removed": ["serde"], "truncated": True},
        }
        field = ("scan.delta.dependencies",)
        out = render_code_review(_scan_review({"delta": {"dependencies": deps}}), field)
        lines = out.splitlines()[2:]
        assert lines == [
            "- **pyproject.toml** — added: pydantic-ai, structlog; bumped: fastapi",
            "- **Cargo.toml** — removed: serde; truncated: yes",
        ]
        assert "package.json" not in out
        # Nothing changed anywhere: the block is skipped.
        quiet = {"pyproject.toml": {"added": [], "removed": [], "bumped": []}}
        review = _scan_review({"delta": {"dependencies": quiet}})
        assert render_code_review(review, field) == ""
        # Totality: a manifest whose value is not a dict still renders.
        odd = {"Makefile": "rewritten", "x": None}
        out = render_code_review(_scan_review({"delta": {"dependencies": odd}}), field)
        assert out.splitlines()[-1] == "- **Makefile** — rewritten"
        # ... and a delta that is not a dict at all walks as it stands.
        out = render_code_review(
            _scan_review({"delta": {"dependencies": ["httpx", "boto3"]}}), field
        )
        assert out.splitlines()[2:] == ["- httpx", "- boto3"]


class TestStep3ArraysInTheViews:
    def test_load_bearing_renders_the_contract_beneath_its_module(self) -> None:
        entries = [
            {
                "module": "src/app/llm.py",
                "symbol": "stream_turn",
                "role": "every model call",
                "contract": {
                    "inputs": ["messages", "config"],
                    "outputs": ["chunks"],
                    "invariants": [],
                    "side_effects": ["network"],
                },
                "consumers": ["a.py", "b.py", "c.py"],
                "inferred_from": "src/app/llm.py",
            },
            {"module": "src/app/k.py", "role": "keys", "contract": {"outputs": ["s"]}},
            "raw",
            "",
            None,
        ]
        out = render_code_review(_review(load_bearing=entries), ("load_bearing",))
        assert out.splitlines() == [
            "**Existing load-bearing modules**",
            f"_{FIELD_GUIDANCE['load_bearing']}_",
            "- **src/app/llm.py** · `stream_turn` (consumers: 3) — every model call "
            "[src/app/llm.py]",
            "  - inputs: messages; config",
            "  - outputs: chunks",
            "  - side effects: network",
            "- **src/app/k.py** — keys",
            "  - outputs: s",
            "- raw",
        ]
        assert "a.py" not in out  # consumers is a count, the list stays in the JSON
        # Totality: a non-list value still walks.
        out = render_code_review(_review(load_bearing={"k": "v"}), ("load_bearing",))
        assert "- k: v" in out

    def test_implemented_and_integrations_walk_with_their_primary_key(self) -> None:
        review = _review(
            implemented=[
                {
                    "id": "code_review",
                    "name": "Code review",
                    "status": "complete",
                    "paths": ["src/app/scanner/"],
                    "prior_feature_ids": ["round_tree"],
                }
            ],
            integrations=[
                {
                    "name": "OpenRouter",
                    "kind": "llm_provider",
                    "client_module": "src/app/llm.py",
                    "config_env_vars": ["OPENROUTER_API_KEY"],
                }
            ],
        )
        out = render_code_review(review, ("implemented", "integrations"))
        assert "**Existing implemented capabilities**" in out
        assert (
            "- **Code review** — id: code_review; status: complete; paths: "
            "src/app/scanner/; prior feature ids: round_tree" in out
        )
        assert "**Existing integrations**" in out
        assert (
            "- **OpenRouter** — kind: llm_provider; client module: src/app/llm.py; "
            "config env vars: OPENROUTER_API_KEY" in out
        )

    def test_each_consumer_tuple_gained_what_the_decision_names(self) -> None:
        # D-SC3-11, tuple by tuple.
        for field in ("load_bearing", "implemented", "scan.coverage"):
            assert field in PHASER_REVIEW_FIELDS
        assert PHASER_REVIEW_FIELDS[-1] == "scan.coverage"
        assert "integrations" not in PHASER_REVIEW_FIELDS
        for field in (
            "integrations",
            "scan.plan_drift.planned_unmatched",
            "scan.plan_drift.declared_not_planned",
            "scan.delta.dependencies",
        ):
            assert field in STACK_REVIEW_FIELDS
        for field in ("load_bearing", "implemented"):
            assert field not in STACK_REVIEW_FIELDS
        assert "implemented" in BRAINSTORMER_REVIEW_FIELDS
        for field in ("load_bearing", "integrations"):
            assert field not in BRAINSTORMER_REVIEW_FIELDS
        # Scout is untouched by 3b.
        for field in ("load_bearing", "implemented", "integrations"):
            assert field not in SCOUT_REVIEW_FIELDS

    def test_guidance_lines_are_the_decision_s_words(self) -> None:
        assert PHASER_FIELD_GUIDANCE["load_bearing"] == (
            "A phase that touches a load-bearing module names, in its instructions "
            "and verification, the contract it preserves."
        )
        assert STACK_FIELD_GUIDANCE["integrations"] == (
            "`llm_provider` entries are Topic 3's `providers`; the rest are your "
            "`integrations`, already in place."
        )
        assert BRAINSTORMER_FIELD_GUIDANCE["implemented"] == (
            "Already built, with status. Never propose a `complete` one as new; a "
            "`partial`/`stub` one is a finish-or-remove question."
        )
        assert "implemented" in PHASER_FIELD_GUIDANCE
        # Each override names a field its tuple renders, and replaces the
        # shared line in that view.
        assert set(STACK_FIELD_GUIDANCE) <= set(STACK_REVIEW_FIELDS)
        assert set(PHASER_FIELD_GUIDANCE) <= set(PHASER_REVIEW_FIELDS)
        assert set(BRAINSTORMER_FIELD_GUIDANCE) <= set(BRAINSTORMER_REVIEW_FIELDS)
        fx = load_fixture(_STEP3)
        stack = render_code_review(
            fx, STACK_REVIEW_FIELDS, guidance=STACK_FIELD_GUIDANCE
        )
        assert f"_{STACK_FIELD_GUIDANCE['integrations']}_" in stack
        assert f"_{FIELD_GUIDANCE['integrations']}_" not in stack
        brain = render_code_review(
            fx, BRAINSTORMER_REVIEW_FIELDS, guidance=BRAINSTORMER_FIELD_GUIDANCE
        )
        assert f"_{BRAINSTORMER_FIELD_GUIDANCE['implemented']}_" in brain
        assert f"_{FIELD_GUIDANCE['implemented']}_" not in brain

    def test_old_fixture_without_the_fields_renders_as_before(self) -> None:
        # The 2a fixture has no step-3 arrays and an empty scan: the three
        # pinned goldens above are unchanged, so no heading of 3b's appears.
        fx = load_fixture("review_full.json")
        for fields, guidance in (
            (PHASER_REVIEW_FIELDS, PHASER_FIELD_GUIDANCE),
            (STACK_REVIEW_FIELDS, STACK_FIELD_GUIDANCE),
            (BRAINSTORMER_REVIEW_FIELDS, BRAINSTORMER_FIELD_GUIDANCE),
        ):
            out = render_code_review(fx, fields, guidance=guidance)
            for heading in (
                "**Existing load-bearing modules**",
                "**Existing implemented capabilities**",
                "**Existing integrations**",
                "**Scan",
                "**Planned",
                "**Declared",
                "**Dependency changes",
            ):
                assert heading not in out
            assert "**Existing architecture**" in out  # paired positive

    def test_golden_step3_views(self) -> None:
        fx = load_fixture(_STEP3)
        assert_golden(
            "code_review_phaser_view_step3.md",
            render_code_review(
                fx, PHASER_REVIEW_FIELDS, guidance=PHASER_FIELD_GUIDANCE
            ),
        )
        assert_golden(
            "code_review_stack_view_step3.md",
            render_code_review(fx, STACK_REVIEW_FIELDS, guidance=STACK_FIELD_GUIDANCE),
        )
        assert_golden(
            "code_review_brainstormer_view_step3.md",
            render_code_review(
                fx, BRAINSTORMER_REVIEW_FIELDS, guidance=BRAINSTORMER_FIELD_GUIDANCE
            ),
        )
        assert_golden(
            "code_review_scout_view_step3.md",
            render_code_review(fx, SCOUT_REVIEW_FIELDS),
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
        assert '```json\n{\n  "review"' not in seed
        # The conflict-warning instruction and the brownfield ask are kept.
        assert "proactively warn me about the conflict" in seed
        assert "draft an initial stack spec" in seed

    def test_brownfield_seed_carries_integrations_and_the_measured_blocks(
        self,
    ) -> None:
        # 3b (D-SC3-11): the integrations index with the stack's own routing
        # line, and the scan's plan drift and dependency delta.
        review = _review(
            scan={
                "plan_drift": {
                    "planned_unmatched": [{"name": "Alembic", "sources": ["stack"]}],
                    "declared_not_planned": [
                        {"name": "oxlint", "manifest": "web/package.json"}
                    ],
                },
                "delta": {"dependencies": {"pyproject.toml": {"added": ["httpx"]}}},
            },
            integrations=[
                {"name": "OpenRouter", "kind": "llm_provider", "client_module": "l.py"}
            ],
        )
        session = make_session(
            active_agent="stack_advisor",
            vision_statement={"vision_statement": {"name": "App"}},
            code_review=review,
            stack_statement=None,
        )
        seed = _seed_after_run(session)
        assert "**Existing integrations**" in seed
        assert f"_{STACK_FIELD_GUIDANCE['integrations']}_" in seed
        assert "- **OpenRouter** — kind: llm_provider" in seed
        assert "**Planned last round, not found in the code**" in seed
        assert "- **Alembic** — sources: stack" in seed
        assert "**Declared in a manifest, not planned**" in seed
        assert "- **oxlint** — manifest: web/package.json" in seed
        assert "- **pyproject.toml** — added: httpx" in seed
        assert "Scan coverage" not in seed  # Phaser's, not the stack's

    def test_not_a_software_project_review_uses_the_greenfield_seed(self) -> None:
        review = _review(is_software_project=False, summary="bare manifest")
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

    def test_brownfield_seed_carries_the_view_not_the_json(self) -> None:
        review = _review(
            commands={"test": "uv run pytest"},
            persistence={"databases": [{"engine": "PostgreSQL"}]},
            protocols_implemented=[{"name": "A2A"}],
            entrypoints={"main": "app/main.py", "ui_root": "index.html"},
        )
        seed = self._seed(review)
        # D-EV6: the raw block D-CR1 kept alongside the view is gone.
        assert json.dumps(review, indent=2) not in seed
        assert '```json\n{\n  "code_review"' not in seed
        assert "existing codebase, by block" in seed
        # The rules sit under the data they govern.
        assert f"_{PHASER_FIELD_GUIDANCE['persistence']}_" in seed
        assert f"_{PHASER_FIELD_GUIDANCE['protocols_implemented']}_" in seed
        assert "- test: uv run pytest" in seed
        assert "- **PostgreSQL**" in seed
        assert "- main: app/main.py" in seed
        # The old paragraphs are gone; ui_root is excluded and now reaches nothing.
        assert "If `persistence` is present" not in seed
        assert "index.html" not in seed
        assert "integration/validation thread for the existing code" in seed

    def test_brownfield_seed_carries_contracts_and_the_coverage_line(self) -> None:
        # 3b (D-SC3-11): load_bearing and implemented with Phaser's rules, and
        # one coverage line from the scan — never the sampled paths.
        review = _review(
            scan={
                "coverage": {
                    "source_files_sampled": 3,
                    "source_files_total": 40,
                    "sampled": ["src/secret_path.py"],
                }
            },
            load_bearing=[
                {
                    "module": "src/app/llm.py",
                    "role": "every call",
                    "contract": {"invariants": ["messages ends with the turn"]},
                    "consumers": ["a.py"],
                }
            ],
            implemented=[
                {"id": "x", "name": "Export", "status": "partial", "paths": ["e.py"]}
            ],
        )
        seed = self._seed(review)
        assert f"_{PHASER_FIELD_GUIDANCE['load_bearing']}_" in seed
        assert "- **src/app/llm.py** (consumers: 1) — every call" in seed
        assert "  - invariants: messages ends with the turn" in seed
        assert f"_{PHASER_FIELD_GUIDANCE['implemented']}_" in seed
        assert "- **Export** — id: x; status: partial; paths: e.py" in seed
        assert "**Scan coverage**" in seed
        assert "- 3 of 40 source files shown as bodies" in seed
        assert "src/secret_path.py" not in seed

    def test_review_with_nothing_in_the_tuple_still_names_itself(self) -> None:
        seed = self._seed(_review(languages=[{"name": "Go"}]))
        assert "none of its blocks relevant to phasing carry content" in seed
        assert "**Existing" not in seed
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


# ---------------------------------------------------------------------------
# Brainstormer seeds — both paste sites
# ---------------------------------------------------------------------------


class TestBrainstormerSeeds:
    def _run(self, session: dict[str, Any]) -> tuple[str, bool]:
        with patch("spec4.llm.litellm.completion") as mock_llm:
            mock_llm.return_value = iter(
                [make_stream_chunk("Ok"), make_stream_chunk("", finish_reason="stop")]
            )
            collect(brainstormer.run(None, session, session["llm_config"]))
            called = mock_llm.called
        msgs = session["brainstormer_messages"]
        return (msgs[0]["content"] if msgs else ""), called

    def _review(self) -> dict[str, Any]:
        return _review(
            existing_self_description={
                "text": "A recipe planner.",
                "source": "README.md",
            },
            api_surface=[{"protocol": "http", "path_or_method": "GET /recipes"}],
            commands={"test": "pytest"},
            notes={"incomplete_or_dead_code": ["half-built export"]},
        )

    def test_review_only_seed_carries_the_view_not_the_json(self) -> None:
        review = self._review()
        session = make_session(code_review=review, vision_statement=None)
        seed, called = self._run(session)
        assert called
        assert "**Existing self-description**" in seed
        assert f"_{BRAINSTORMER_FIELD_GUIDANCE['api_surface']}_" in seed
        assert "- **GET /recipes**" in seed
        assert "- half-built export" in seed
        assert "pytest" not in seed  # commands are Phaser's, not the vision's
        assert json.dumps(review, indent=2) not in seed
        assert "Use the code review as context" in seed

    def test_review_only_seed_carries_implemented_with_the_vision_rule(self) -> None:
        # 3b (D-SC3-11): what is already built, so the vision never re-proposes it.
        review = _review(
            existing_self_description={"text": "A planner.", "source": "README.md"},
            implemented=[
                {"id": "exp", "name": "Export", "status": "complete", "paths": ["e.py"]}
            ],
            load_bearing=[
                {"module": "m.py", "role": "r", "contract": {"outputs": ["o"]}}
            ],
        )
        session = make_session(code_review=review, vision_statement=None)
        seed, _ = self._run(session)
        assert f"_{BRAINSTORMER_FIELD_GUIDANCE['implemented']}_" in seed
        assert "- **Export** — id: exp; status: complete; paths: e.py" in seed
        assert "load-bearing" not in seed  # Phaser's, not the vision's

    def test_existing_vision_seed_carries_the_same_view(self) -> None:
        review = self._review()
        session = make_session(
            code_review=review,
            vision_statement={"vision_statement": {"name": "Planner"}},
        )
        seed, _ = self._run(session)
        assert "**Existing self-description**" in seed
        assert "existing vision statement from a previous planning" in seed
        assert json.dumps(review, indent=2) not in seed
        assert "treat structured fields" not in seed  # the old paragraph

    def test_not_a_software_project_review_is_a_fresh_start(self) -> None:
        review = _review(is_software_project=False, summary="bare manifest")
        session = make_session(code_review=review, vision_statement=None)
        seed, called = self._run(session)
        assert not called  # the static greeting, no LLM turn
        assert seed == "" or "bare manifest" not in seed

    def test_greenfield_has_no_review_block(self) -> None:
        session = make_session(
            vision_statement={"vision_statement": {"name": "Planner"}}
        )
        seed, _ = self._run(session)
        assert "**Existing" not in seed
        assert "code review" not in seed
