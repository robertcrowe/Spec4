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

import pathlib
import sys
from collections.abc import Iterator
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
