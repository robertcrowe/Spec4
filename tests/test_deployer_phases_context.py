"""Unit tests for ``_phases_for_deployer`` — Phaser's phase plan as Deployer
input (D-DE4).

Deployer previously saw phase numbers and titles only. Two things in the phase
payload are deployment-shaped: the build order (which is also the coding agent's
execution sequence, so the file paths stay) and each phase's
``tech_stack_spec.configurations`` — the environment variables, ports, and
config files that phase's code reads. The union of those configurations is the
factual basis for the plan's Environment section.

``configurations`` is projected verbatim: the prose carries example values, the
local-versus-production split, and what each variable is for, none of which
survives a name-only extraction. Verification text and per-phase dependency
lists are deliberately not projected — the dev loop and package installs are not
deployment decisions.

Pure rendering assertions; whether the live model then writes a better
Environment section is an in-app behavioural draw, not asserted here.
"""

from __future__ import annotations

from typing import Any

from spec4.agents._utils import _phases_for_deployer


def _phase(num: int, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "phase_number": num,
        "total_phases": 3,
        "phase_title": f"Phase {num} Work",
        "tech_stack_spec": {
            "dependencies": ["fastapi", "sqlalchemy"],
            "configurations": f"VAR_{num} env var; API listens on PORT 800{num}",
        },
        "verification": "Run `docker-compose up` and curl the health endpoint.",
    }
    base.update(over)
    return base


# --- empty / absent --------------------------------------------------------


def test_no_phases_renders_nothing() -> None:
    assert _phases_for_deployer([], 0) == ""


def test_phase_without_configurations_still_lists_in_build_order() -> None:
    phases = [_phase(1, tech_stack_spec={"dependencies": []})]
    out = _phases_for_deployer(phases, 0)
    assert "Phase 1: Phase 1 Work" in out
    # No configuration section at all when nothing declares any.
    assert "Per-phase configuration" not in out


# --- build order -----------------------------------------------------------


def test_build_order_lists_every_phase_with_its_path() -> None:
    phases = [_phase(1), _phase(2), _phase(3)]
    out = _phases_for_deployer(phases, 2)
    for n in (1, 2, 3):
        assert f"- Phase {n}: Phase {n} Work" in out
        assert f"`.spec4/v2/phases/phase{n}.md`" in out


def test_build_order_preserves_given_order() -> None:
    phases = [_phase(1), _phase(2), _phase(3)]
    out = _phases_for_deployer(phases, 0)
    assert out.index("Phase 1: ") < out.index("Phase 2: ") < out.index("Phase 3: ")


def test_phase_count_is_stated() -> None:
    out = _phases_for_deployer([_phase(1), _phase(2)], 0)
    assert "the 2 phases" in out


# --- configurations --------------------------------------------------------


def test_configurations_are_projected_verbatim() -> None:
    cfg = (
        "DATABASE_URL env var (e.g., postgresql://user:pass@localhost:5432/db); "
        "VITE_API_BASE_URL (https://api.example.com for production)"
    )
    phases = [_phase(1, tech_stack_spec={"configurations": cfg})]
    out = _phases_for_deployer(phases, 0)
    # The whole string survives — example values and the production split included.
    assert cfg in out


def test_every_phase_declaring_configuration_gets_a_line() -> None:
    phases = [_phase(1), _phase(2), _phase(3)]
    out = _phases_for_deployer(phases, 0)
    section = out.split("Per-phase configuration")[1]
    for n in (1, 2, 3):
        assert f"- Phase {n}: VAR_{n} env var" in section


def test_no_new_variables_phrasing_is_preserved_not_dropped() -> None:
    """A phase that adds nothing still gets its line, so silence is not ambiguous."""
    phases = [
        _phase(1),
        _phase(2, tech_stack_spec={"configurations": "No new environment variables."}),
    ]
    out = _phases_for_deployer(phases, 0)
    assert "- Phase 2: No new environment variables." in out


def test_configurations_as_list_is_tolerated() -> None:
    """The schema says string; a list is joined rather than rendered as a repr."""
    phases = [_phase(1, tech_stack_spec={"configurations": ["A_VAR", "B_VAR"]})]
    out = _phases_for_deployer(phases, 0)
    assert "- Phase 1: A_VAR; B_VAR" in out
    assert "['A_VAR'" not in out


def test_blank_configurations_omits_only_that_phases_line() -> None:
    phases = [_phase(1, tech_stack_spec={"configurations": "   "}), _phase(2)]
    out = _phases_for_deployer(phases, 0)
    section = out.split("Per-phase configuration")[1]
    assert "- Phase 1:" not in section
    assert "- Phase 2: VAR_2 env var" in section
    # Phase 1 is still in the build order — it exists, it just configures nothing.
    assert "- Phase 1: Phase 1 Work" in out


# --- deliberate omissions --------------------------------------------------


def test_verification_text_is_not_projected() -> None:
    phases = [_phase(1, verification="Run `pytest -v` and confirm all tests pass.")]
    out = _phases_for_deployer(phases, 0)
    assert "pytest" not in out
    assert "docker-compose" not in out


def test_dependency_lists_are_not_projected() -> None:
    phases = [
        _phase(
            1,
            tech_stack_spec={
                "dependencies": ["uvicorn", "psycopg"],
                "configurations": "VAR_1 env var",
            },
        )
    ]
    out = _phases_for_deployer(phases, 0)
    assert "uvicorn" not in out
    assert "psycopg" not in out
