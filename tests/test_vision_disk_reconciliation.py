"""D-BR — Brainstormer's entry decision reads disk, agreeing with the button.

The agent button state reads the current ``vision.json`` from disk; ``run()``'s
cold-open branch previously read in-memory ``session['vision_statement']``, so a
stale session (e.g. after ``.spec4`` was deleted out of band) could drive update
mode while the button showed "Start". These tests cover ``load_vision`` (the
button-matching disk read), ``_rehydrate_vision_from_disk`` (the reconciliation),
and the end-to-end entry decision through ``run()``.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from spec4 import project_manager
from spec4.agents import brainstormer
from spec4.app_constants import STATE_IN_PROGRESS, STATE_VISION_COMPLETE

_BROWNFIELD_MARKER = "existing vision statement from a previous planning session"


def _vision(name: str = "App") -> dict[str, Any]:
    return {"vision_statement": {"name": name, "vision": {"purpose": "p"}}}


def _specs() -> dict[str, Any]:
    return {"version": 1, "features": [], "nfr_goals": []}


def _session(**overrides: Any) -> dict[str, Any]:
    session: dict[str, Any] = {
        "working_dir": None,
        "vision_statement": None,
        "feature_specs": None,
        "brainstormer_state": STATE_IN_PROGRESS,
        "brainstormer_messages": [],
        "code_review": None,
        "llm_config": {"model": "test-model", "api_key": "test-key"},
    }
    session.update(overrides)
    return session


def _mock_stream(text: str = "ok") -> Any:
    def _chunk(content: str, finish: str | None = None) -> MagicMock:
        c = MagicMock()
        c.choices[0].delta.content = content
        c.choices[0].delta.tool_calls = None
        c.choices[0].finish_reason = finish
        return c

    chunks = [_chunk(ch) for ch in text] + [_chunk("", "stop")]
    return patch("spec4.llm.litellm.completion", return_value=iter(chunks))


# ---------------------------------------------------------------------------
# load_vision — the button-matching disk read
# ---------------------------------------------------------------------------


class TestLoadVision:
    def test_reads_current_vision(self, tmp_path: Path) -> None:
        project_manager.save_vision(tmp_path, _vision(), 0)
        assert project_manager.load_vision(tmp_path) == _vision()

    def test_absent_returns_none(self, tmp_path: Path) -> None:
        assert project_manager.load_vision(tmp_path) is None

    def test_uses_active_version_like_the_button(self, tmp_path: Path) -> None:
        # The button resolves via active_version; load_vision must match, so a
        # vision saved for the active round is the one found.
        project_manager.save_vision(tmp_path, _vision("Active"), 0)
        session = {"phase_version": 0}
        assert project_manager.load_vision(tmp_path, session)[
            "vision_statement"
        ]["name"] == "Active"


# ---------------------------------------------------------------------------
# _rehydrate_vision_from_disk — the reconciliation
# ---------------------------------------------------------------------------


class TestRehydrate:
    def test_disk_vision_present_sets_pair_and_specs(self, tmp_path: Path) -> None:
        project_manager.save_vision(tmp_path, _vision(), 0)
        project_manager.save_feature_specs(tmp_path, _specs(), 0)
        session = _session(working_dir=str(tmp_path))
        brainstormer._rehydrate_vision_from_disk(session)
        assert session["vision_statement"] == _vision()
        assert session["brainstormer_state"] == STATE_VISION_COMPLETE
        assert session["feature_specs"] == _specs()

    def test_stale_session_cleared_when_disk_empty(self, tmp_path: Path) -> None:
        # The core fix: session holds a vision the disk does not — clear it.
        session = _session(
            working_dir=str(tmp_path),
            vision_statement=_vision("Stale"),
            feature_specs=_specs(),
            brainstormer_state=STATE_VISION_COMPLETE,
        )
        brainstormer._rehydrate_vision_from_disk(session)
        assert session["vision_statement"] is None
        assert session["brainstormer_state"] == STATE_IN_PROGRESS
        assert session["feature_specs"] is None

    def test_no_working_dir_leaves_session_untouched(self) -> None:
        session = _session(
            working_dir=None,
            vision_statement=_vision("Ephemeral"),
            brainstormer_state=STATE_VISION_COMPLETE,
        )
        brainstormer._rehydrate_vision_from_disk(session)
        assert session["vision_statement"] == _vision("Ephemeral")
        assert session["brainstormer_state"] == STATE_VISION_COMPLETE

    def test_messages_are_untouched(self, tmp_path: Path) -> None:
        session = _session(
            working_dir=str(tmp_path),
            vision_statement=_vision("Stale"),
            brainstormer_messages=[{"role": "user", "content": "mid-brainstorm"}],
        )
        brainstormer._rehydrate_vision_from_disk(session)
        assert session["brainstormer_messages"] == [
            {"role": "user", "content": "mid-brainstorm"}
        ]


# ---------------------------------------------------------------------------
# run() entry decision — tracks disk, not the stale session
# ---------------------------------------------------------------------------


class TestRunEntryDecision:
    def test_stale_session_no_disk_is_greenfield(self, tmp_path: Path) -> None:
        # Stale in-memory vision, but disk is clean -> must NOT enter update mode.
        session = _session(
            working_dir=str(tmp_path),
            vision_statement=_vision("Stale"),
            brainstormer_state=STATE_VISION_COMPLETE,
        )
        with _mock_stream():
            "".join(brainstormer.run(None, session, session["llm_config"]))
        assert session["vision_statement"] is None
        assert session["brainstormer_state"] == STATE_IN_PROGRESS
        assert not any(
            _BROWNFIELD_MARKER in m.get("content", "")
            for m in session["brainstormer_messages"]
        )

    def test_disk_vision_no_session_enters_update_mode(self, tmp_path: Path) -> None:
        # Fresh session, but a vision exists on disk -> update mode from disk.
        project_manager.save_vision(tmp_path, _vision(), 0)
        session = _session(working_dir=str(tmp_path))
        with _mock_stream():
            "".join(brainstormer.run(None, session, session["llm_config"]))
        assert session["vision_statement"] == _vision()
        assert any(
            _BROWNFIELD_MARKER in m.get("content", "")
            for m in session["brainstormer_messages"]
        )
