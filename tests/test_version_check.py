"""The startup version check and its upgrade dialog.

No test here touches the network: the PyPI fetch is either bypassed via the
``SPEC4_FAKE_PYPI_VERSION`` hook, mocked, or asserted not to run at all.
"""

from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import patch

import pytest
from dash import no_update

from spec4 import version_check
from spec4.app import app, on_version_check
from spec4.version_check import (
    check_for_update,
    fetch_latest_version,
    is_outdated,
)


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.delenv("SPEC4_FAKE_PYPI_VERSION", raising=False)
    version_check._reset_cache()
    yield
    version_check._reset_cache()


class TestIsOutdated:
    def test_strictly_newer_release_is_outdated(self) -> None:
        assert is_outdated("1.0.0", "1.0.1")
        assert is_outdated("1.0.0", "2.0.0")
        assert is_outdated("1.0", "1.0.1")

    def test_equal_or_older_release_is_not(self) -> None:
        assert not is_outdated("1.0.0", "1.0.0")
        assert not is_outdated("2.0.0", "1.9.9")

    def test_uncertainty_never_nags(self) -> None:
        # Unknown local version, pre-release strings, missing latest: an
        # upgrade dialog on bad data is worse than silence.
        assert not is_outdated("unknown", "1.0.0")
        assert not is_outdated("1.0.0", "1.0.1rc1")
        assert not is_outdated("1.0.0", None)
        assert not is_outdated("1.0.0", "")


class TestFetchLatestVersion:
    def test_fake_version_bypasses_the_network(self) -> None:
        with (
            patch.dict("os.environ", {"SPEC4_FAKE_PYPI_VERSION": "99.0.0"}),
            patch.object(
                version_check.urllib.request,
                "urlopen",
                side_effect=AssertionError("network call attempted"),
            ),
        ):
            assert fetch_latest_version() == "99.0.0"

    def test_network_failure_reads_as_unavailable(self) -> None:
        with patch.object(
            version_check.urllib.request, "urlopen", side_effect=OSError("down")
        ):
            assert fetch_latest_version() is None

    def test_parses_the_pypi_payload(self) -> None:
        payload = io.BytesIO(json.dumps({"info": {"version": "3.2.1"}}).encode())
        payload.__enter__ = lambda *a: payload  # type: ignore[attr-defined]
        payload.__exit__ = lambda *a: None  # type: ignore[attr-defined]
        with patch.object(
            version_check.urllib.request, "urlopen", return_value=payload
        ):
            assert fetch_latest_version() == "3.2.1"

    def test_malformed_payload_reads_as_unavailable(self) -> None:
        payload = io.BytesIO(b"not json")
        payload.__enter__ = lambda *a: payload  # type: ignore[attr-defined]
        payload.__exit__ = lambda *a: None  # type: ignore[attr-defined]
        with patch.object(
            version_check.urllib.request, "urlopen", return_value=payload
        ):
            assert fetch_latest_version() is None


class TestCheckForUpdate:
    def test_outdated_reports_both_versions(self) -> None:
        with patch.object(
            version_check, "fetch_latest_version", return_value="99.0.0"
        ):
            info = check_for_update()
        assert info is not None
        assert info["latest"] == "99.0.0"
        assert info["current"] == version_check.__version__

    def test_up_to_date_reports_nothing(self) -> None:
        with patch.object(
            version_check,
            "fetch_latest_version",
            return_value=version_check.__version__,
        ):
            assert check_for_update() is None

    def test_fetches_once_per_process(self) -> None:
        with patch.object(
            version_check, "fetch_latest_version", return_value="99.0.0"
        ) as mock_fetch:
            check_for_update()
            check_for_update()
            check_for_update()
        assert mock_fetch.call_count == 1


class TestDialogCallback:
    def test_outdated_opens_the_dialog_with_both_versions(self) -> None:
        with patch.object(
            version_check,
            "check_for_update",
            return_value={"current": "1.0.0", "latest": "9.9.9"},
        ):
            opened, body, shown = on_version_check(1, already_shown=False)
        assert opened is True
        assert shown is True  # marks this browser session as notified
        text = str(body)
        assert "1.0.0" in text
        assert "9.9.9" in text
        assert "uv tool upgrade spec4" in text

    def test_up_to_date_leaves_the_dialog_alone(self) -> None:
        with patch.object(version_check, "check_for_update", return_value=None):
            opened, body, shown = on_version_check(1, already_shown=False)
        assert opened is no_update
        assert body is no_update
        assert shown is no_update

    def test_shows_at_most_once_per_browser_session(self) -> None:
        """A reload in the same tab must not re-nag — and must not even
        re-consult the checker."""
        with patch.object(
            version_check,
            "check_for_update",
            side_effect=AssertionError("checker consulted despite guard"),
        ):
            opened, body, shown = on_version_check(1, already_shown=True)
        assert opened is no_update
        assert body is no_update
        assert shown is no_update


class TestLayoutWiring:
    def _ids(self) -> set[str]:
        found: set[str] = set()

        def walk(node: Any) -> None:
            if isinstance(node, (list, tuple)):
                for item in node:
                    walk(item)
                return
            node_id = getattr(node, "id", None)
            if isinstance(node_id, str):
                found.add(node_id)
            children = getattr(node, "children", None)
            if children is not None:
                walk(children)

        walk(app.layout)
        return found

    def test_interval_modal_and_session_guard_are_in_the_root_layout(self) -> None:
        ids = self._ids()
        assert "version-check-interval" in ids
        assert "version-check-modal" in ids
        assert "version-notice-shown" in ids

    def test_modal_has_a_white_outline(self) -> None:
        modal = self._find("version-check-modal")
        assert modal is not None
        border = (modal.styles or {}).get("content", {}).get("border", "")
        assert "solid" in border
        assert "#ffffff" in border.lower()

    def test_session_guard_uses_session_storage(self) -> None:
        store = self._find("version-notice-shown")
        assert store is not None
        assert store.storage_type == "session"

    def _find(self, target_id: str) -> Any:
        def walk(node: Any) -> Any:
            if isinstance(node, (list, tuple)):
                for item in node:
                    hit = walk(item)
                    if hit is not None:
                        return hit
                return None
            if getattr(node, "id", None) == target_id:
                return node
            children = getattr(node, "children", None)
            return walk(children) if children is not None else None

        return walk(app.layout)

    def test_interval_fires_exactly_once(self) -> None:
        def find(node: Any) -> Any:
            if isinstance(node, (list, tuple)):
                for item in node:
                    hit = find(item)
                    if hit is not None:
                        return hit
                return None
            if getattr(node, "id", None) == "version-check-interval":
                return node
            children = getattr(node, "children", None)
            return find(children) if children is not None else None

        interval = find(app.layout)
        assert interval is not None
        assert interval.max_intervals == 1
