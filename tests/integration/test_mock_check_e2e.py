"""The mock preview reports the mock's runtime errors, in a real browser.

The saved mock is loaded into the Designer preview, whose iframe runs it with
the error shim (``layouts.designer.MOCK_ERROR_SHIM``); the shim posts to the
page, ``assets/mock_errors.js`` writes the ``mock-render-errors`` store, and
the clientside painter rewrites the status line above the preview. Two
mocks: one that throws, one that does not.

The server is a subprocess — serving Dash in-process drains the callback
registry other test modules read. No LLM call is made: the mock is already
on disk, so the wizard opens at the preview step.
"""

from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import Page, sync_playwright  # noqa: E402

from spec4.agents.designer import save_mock, save_session  # noqa: E402

_LAUNCH_TIMEOUT_MS = 30_000
_WAIT_MS = 15_000
_BOOT_TIMEOUT_S = 60.0

_BROKEN_MOCK = (
    "<!DOCTYPE html><html><head><title>t</title></head>"
    "<body><p>hi</p>\n<script>\nnoSuchFunction();\n</script></body></html>"
)
_CLEAN_MOCK = (
    "<!DOCTYPE html><html><head><title>t</title></head>"
    "<body><p>hi</p><script>document.title = 'ok';</script></body></html>"
)

_SERVER = """
import logging, sys
import spec4.app as app_module
logging.getLogger("werkzeug").setLevel(logging.ERROR)
app_module.app.run(
    host="127.0.0.1", port=int(sys.argv[1]), debug=False, threaded=True
)
"""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


def _serving(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return bool(response.status == 200)
    except (urllib.error.URLError, OSError):
        return False


def _project(root: pathlib.Path, mock: str) -> pathlib.Path:
    """A project whose current round has ``mock`` saved as its design."""
    version = root / ".spec4" / "v0"
    version.mkdir(parents=True)
    (version / "code_review.json").write_text(
        json.dumps({"schema_version": 1, "is_software_project": True}),
        encoding="utf-8",
    )
    (version / "vision.json").write_text(
        json.dumps({"app_name": "Thing", "purpose": "x"}), encoding="utf-8"
    )
    design = version / "design"
    save_session(
        {
            "step": 6,
            "preference_text": "",
            "screenshots": [],
            "mock_html": mock,
            "finalized": False,
        },
        design,
    )
    save_mock(mock, design)
    return root


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [sys.executable, "-c", _SERVER, str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + _BOOT_TIMEOUT_S
        while not _serving(url):
            if server.poll() is not None:
                pytest.fail(f"server exited during startup:\n{server.communicate()[0]}")
            if time.monotonic() > deadline:
                pytest.fail(f"server did not start within {_BOOT_TIMEOUT_S:.0f}s")
            time.sleep(0.2)
        yield url
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - a wedged server
            server.kill()


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    with sync_playwright() as playwright:
        try:
            launched = playwright.chromium.launch(timeout=_LAUNCH_TIMEOUT_MS)
        except Exception as exc:  # pragma: no cover - environment, not code
            pytest.skip(f"no browser available: {exc}")
        try:
            yield launched
        finally:
            launched.close()


def _session(project: pathlib.Path) -> dict[str, Any]:
    """Designer, model already chosen, on a project with a saved mock."""
    return {
        "phase": "designer",
        "working_dir": str(project),
        "browser_path": str(project),
        "provider": "openai",
        "model": "gpt-4o-mini",
        "llm_config": {"model": "gpt-4o-mini", "api_key": "k"},
        "code_review": {"schema_version": 1, "is_software_project": True},
        "code_scanner_state": "review_complete",
        "vision_statement": {"app_name": "Thing", "purpose": "x"},
        "brainstormer_state": "vision_complete",
        "project_mode": "existing",
        "active_agent": "designer",
        "messages": [],
        "agent_llm": {},
        "agent_llm_asked": {"designer": True},
    }


def _open_preview(browser: Any, base_url: str, project: pathlib.Path) -> Page:
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    session = json.dumps(json.dumps(_session(project)))
    prefs = json.dumps(json.dumps({"working_dir": str(project)}))
    context.add_init_script(
        f"window.localStorage.setItem('prefs', {prefs});"
        "window.localStorage.setItem('prefs-timestamp', Date.now());"
        f"window.sessionStorage.setItem('session', {session});"
        "window.sessionStorage.setItem('session-timestamp', Date.now());"
    )
    opened = context.new_page()
    opened.set_default_timeout(_WAIT_MS)
    opened.goto(f"{base_url}/design")
    opened.wait_for_selector("#mock-iframe")
    return opened


def _status(page: Page) -> str:
    return str(page.text_content("#mock-check-status"))


def _fix_button_visible(page: Page) -> bool:
    return bool(page.is_visible("#btn-designer-fix-errors"))


def _status_color(page: Page) -> str:
    """The status line's rendered colour: the theme variable, resolved."""
    return str(
        page.evaluate(
            "() => getComputedStyle(document.querySelector('#mock-check-status')).color"
        )
    )


# Mantine's red shade 6 and the app's accent (SPEC4_GREEN, #39FF14), as the
# browser reports them.
_RED = "rgb(250, 82, 82)"
_GREEN = "rgb(57, 255, 20)"


class TestTheBrokenMock:
    def test_the_error_is_reported_and_the_fix_offered(
        self, browser: Any, base_url: str, tmp_path: pathlib.Path
    ) -> None:
        page = _open_preview(browser, base_url, _project(tmp_path, _BROKEN_MOCK))
        try:
            page.wait_for_function(
                "() => document.querySelector('#mock-check-status')"
                ".textContent.includes('error')"
            )
            assert _status(page) == "1 error in the mock — the model can fix them"
            assert _status_color(page) == _RED
            assert _fix_button_visible(page)
        finally:
            page.context.close()


class TestTheCleanMock:
    def test_the_preview_is_reported_clean_and_no_fix_offered(
        self, browser: Any, base_url: str, tmp_path: pathlib.Path
    ) -> None:
        page = _open_preview(browser, base_url, _project(tmp_path, _CLEAN_MOCK))
        try:
            page.wait_for_function(
                "() => document.querySelector('#mock-check-status')"
                ".textContent === 'Rendered cleanly'"
            )
            assert _status(page) == "Rendered cleanly"
            assert _status_color(page) == _GREEN
            assert not _fix_button_visible(page)
        finally:
            page.context.close()
