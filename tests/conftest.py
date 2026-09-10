"""Suite-wide fixtures.

``_begin_priority_phase`` draws the Prioritizer over the closed feature set, so
every orchestrator test that walks from cross-cutting into the priority phase
would otherwise attempt a live completion and be rescued by the pass's
degrade-to-``mvp`` path — passing while silently reaching for the network and
never exercising the overlay.

The autouse fixture below stubs the orchestrator's ``_call_prioritizer`` helper
with an all-``mvp`` overlay. Normalization still runs for real on top of it.

It lives at the suite root rather than under ``tests/agentifier/`` because the
integration tests reach the same code path: they patch ``litellm.acompletion``,
while the Prioritizer draws through the synchronous ``complete``, so a package
-scoped fixture would leave that seam open.

Tests that exercise the Prioritizer itself patch
``spec4.agentifier.prioritizer.complete`` directly and are untouched by this;
tests that want a different overlay can take the fixture and reassign
``return_value``.
"""

from __future__ import annotations

import importlib
import pathlib
import sys
from collections.abc import Callable, Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from spec4.agentifier.prioritizer import PrioritizerOutcome, PrioritizerOutput


@pytest.fixture(autouse=True)
def stub_prioritizer() -> Iterator[MagicMock]:
    """Patch out the Prioritizer draw; assign every feature ``mvp``."""

    def _stub(
        features: list[dict[str, Any]],
        vision: dict[str, Any],
        llm_config: dict[str, Any],
        carried_forward: list[dict[str, Any]],
        on_chunk: Any = None,
    ) -> PrioritizerOutput:
        overlay = {f["name"]: "mvp" for f in features if f.get("name")}
        return PrioritizerOutput(overlay=overlay, outcome=PrioritizerOutcome.OK)

    with patch(
        "spec4.agentifier.agentifier._call_prioritizer", side_effect=_stub
    ) as mock:
        yield mock


# ---------------------------------------------------------------------------
# Module seams
# ---------------------------------------------------------------------------


class _ModuleSeam:
    """Stands in for a module object, with named attributes replaced.

    Everything not overridden delegates to the real module, so code running
    through the seam behaves normally except at the call the test named.
    """

    def __init__(self, module: Any, overrides: dict[str, Any]) -> None:
        self._module = module
        self._overrides = overrides

    def __getattr__(self, name: str) -> Any:
        overrides = object.__getattribute__(self, "_overrides")
        if name in overrides:
            return overrides[name]
        return getattr(object.__getattribute__(self, "_module"), name)


@pytest.fixture
def module_seam() -> Callable[..., Any]:
    """Patch the module *name* a production module bound, not the module itself.

    ``patch("spec4._usage.os.replace", ...)`` looks scoped and is not:
    ``spec4._usage.os`` *is* the stdlib ``os`` module object, so replacing an
    attribute on it replaces that function for the whole process. Every other
    write while the patch is open — the ``tmp_path`` fixture, pytest's own
    bookkeeping — goes through the stub as well, a blast radius the test's
    assertions cannot see. Renaming the prefix to match wherever the code moved
    does not help; only rebinding the name does.

    This rebinds the name to a delegating stand-in, so only the module under
    test sees the replacement::

        with module_seam("spec4._usage.os", replace=_failing_replace):
            ...

    Use it for **every** patch that would otherwise reach an attribute of a
    stdlib or third-party module through a ``spec4`` module. No test should
    rebind a module's ``os`` by hand.

    See CLEANUP_INVENTORY.md §52.1 for the measurement behind this, and §52.5
    for the production seam that makes the stand-in unnecessary — which Phase 6
    cannot build, because it does not touch ``src/``.
    """

    def _seam(target: str, **overrides: Any) -> Any:
        module_path, _, attr = target.rpartition(".")
        real = getattr(importlib.import_module(module_path), attr)
        return patch(target, _ModuleSeam(real, overrides))

    return _seam


# ---------------------------------------------------------------------------
# The eval scripts, importable
# ---------------------------------------------------------------------------

# ``tests/agentifier/test_fanout_baseline.py`` imports ``fanout_baseline`` from
# ``evals/scout/``, which is a script directory rather than a package and so is
# not on ``sys.path`` by default. Without this, a bare ``uv run pytest`` stops
# at collection — one unimportable module aborts the whole run — and the rest
# of the suite never gets a chance to say anything.
_EVAL_SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "evals" / "scout"
if _EVAL_SCRIPTS.is_dir() and str(_EVAL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_EVAL_SCRIPTS))
