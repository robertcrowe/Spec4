"""Golden-file and fixture helpers for the Phase 1 contract tests.

A golden pins a frozen surface byte for byte: a rendered artifact, a phase
file, a README. The tests that use them are characterization tests — they
say what the code does today, not what it should do — so a diff here is a
question ("did this change on purpose?") rather than a verdict.

Regenerate deliberately, never by accident:

    SPEC4_UPDATE_GOLDENS=1 uv run pytest tests/test_renderer_goldens.py ...

then read the diff before checking it in.
"""

from __future__ import annotations

import difflib
import json
import os
import pathlib
from typing import Any

GOLDEN_DIR = pathlib.Path(__file__).resolve().parent / "golden"
FIXTURE_DIR = GOLDEN_DIR / "fixtures"

_UPDATE_ENV = "SPEC4_UPDATE_GOLDENS"


def updating() -> bool:
    return os.environ.get(_UPDATE_ENV, "") == "1"


def load_fixture(name: str) -> Any:
    """A JSON fixture under ``tests/golden/fixtures/``."""
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def assert_golden(name: str, actual: str) -> None:
    """``actual`` equals the golden at ``tests/golden/<name>`` exactly.

    With ``SPEC4_UPDATE_GOLDENS=1`` the golden is (re)written instead and the
    assertion passes, so a first run creates the file for review.
    """
    path = GOLDEN_DIR / name
    if updating():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
        return
    assert path.exists(), (
        f"golden {path} is missing; run with {_UPDATE_ENV}=1 to create it"
    )
    expected = path.read_text(encoding="utf-8")
    if actual == expected:
        return
    diff = "\n".join(
        difflib.unified_diff(
            expected.splitlines(),
            actual.splitlines(),
            fromfile=f"golden/{name}",
            tofile="actual",
            lineterm="",
        )
    )
    raise AssertionError(
        f"output differs from golden {name} "
        f"(set {_UPDATE_ENV}=1 to regenerate after review):\n{diff}"
    )
