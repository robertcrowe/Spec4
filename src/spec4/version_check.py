"""Startup version check against PyPI.

On the first page load after startup, the app asks PyPI for the latest
released spec4 version and shows a dismissible info dialog when the running
version is older. The check is best-effort by design: any network failure,
unexpected payload, or unparseable version silently disables the dialog —
an upgrade notice must never break, delay, or nag a working app.

Set ``SPEC4_FAKE_PYPI_VERSION`` (e.g. ``99.0.0``) to skip the network call
and treat that version as the latest release — the testing hook for
``make dev``.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from spec4 import __version__

_PYPI_URL = "https://pypi.org/pypi/spec4/json"
_TIMEOUT_SECONDS = 3.0

# Process-lifetime cache: "on startup" means once per server process, not
# once per page load — later page loads reuse the first answer.
_cache: dict[str, Any] = {"checked": False, "result": None}


def fetch_latest_version() -> str | None:
    """Latest released version on PyPI, or None when unavailable."""
    fake = os.environ.get("SPEC4_FAKE_PYPI_VERSION")
    if fake:
        return fake.strip()
    try:
        with urllib.request.urlopen(_PYPI_URL, timeout=_TIMEOUT_SECONDS) as resp:
            data = json.load(resp)
        latest = data["info"]["version"]
        return str(latest) if latest else None
    except Exception:
        return None


def _version_tuple(version: str) -> tuple[int, ...] | None:
    """Dotted-integer parse; None for anything fancier (rc/dev/unknown)."""
    try:
        return tuple(int(part) for part in version.strip().split("."))
    except (AttributeError, ValueError):
        return None


def is_outdated(current: str, latest: str | None) -> bool:
    """True only when both versions parse and latest is strictly newer.

    Unparseable versions (dev builds, the "unknown" fallback, pre-releases)
    never trigger the dialog — false silence is acceptable, a false nag is
    not.
    """
    if not latest:
        return False
    cur = _version_tuple(current)
    lat = _version_tuple(latest)
    if cur is None or lat is None:
        return False
    return lat > cur


def check_for_update() -> dict[str, str] | None:
    """``{"current": …, "latest": …}`` when an upgrade exists, else None.

    Fetches at most once per process; later calls return the cached answer.
    """
    if not _cache["checked"]:
        latest = fetch_latest_version()
        _cache["result"] = (
            {"current": __version__, "latest": str(latest)}
            if is_outdated(__version__, latest)
            else None
        )
        _cache["checked"] = True
    return _cache["result"]


def _reset_cache() -> None:
    """Test hook: forget the cached answer so the next call re-fetches."""
    _cache["checked"] = False
    _cache["result"] = None
