"""The page slot survives a click, in a real browser.

The sequence this walks blanked the chat frame: open an existing project,
start Brainstormer on the default model, open `vision.json` in the Artifact
View, return to the project view, continue Brainstormer, then click in the
chat box. Everything under the status bar vanished and did not come back, with
nothing in the browser console and nothing in the server log.

The cause is in dash-renderer (4.1), not in a callback. Every screen's root
sits at the one path under `page-content`, so the renderer reuses one wrapper
instance for all of them, and that wrapper keeps a cached snapshot of "the
component at this path" that only refreshes when the path's own render hash
moves. Selecting a file in the Artifact View moves it: the click bubbles to
`artifact-view-root`, an html.Div with an id, which counts the click as a prop
change on the shared path. Later screens are drawn correctly because a
children update hands the wrapper the new component directly — but the cached
snapshot is left pointing at a screen that is no longer there. The click in
the chat box then bubbles to `page-content` itself, whose click count is a
non-children prop change on the slot, and for that kind of change the renderer
re-hydrates the slot's child from the stale snapshot: an old project view,
drawn with none of its callback-filled sections, which is the empty frame.

`page-content` therefore carries `disable_n_clicks=True` (see app.py), so a
click can never be a prop change on the slot and the slot only re-renders for
new children. This test walks the exact sequence so that a future rework of
the shell cannot quietly drop the flag; the unit assertion beside it says why
the flag is there, this says what happens without it.

The LLM is stubbed inside the server process: Brainstormer's turn streams a
few sentences and returns, which is enough for the frame to reach its resting
state. Nothing here reaches the network. The server is a subprocess for the
reason the other browser tests give — serving the app in-process drains the
callback registry that three other modules inspect.
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

_LAUNCH_TIMEOUT_MS = 30_000
_WAIT_MS = 15_000
_BOOT_TIMEOUT_S = 60.0
_STREAM_IDLE_S = 30.0

VIEWPORT = {"width": 1280, "height": 800}

# The app with its LLM entry points stubbed. `stream_turn` is the one call the
# Brainstormer's opening turn makes; `complete` covers the feature-spec pass
# that can follow a vision. Both are patched on the `spec4.llm` module object,
# which is what the agents import, so no agent module needs touching.
_SERVER = """
import logging, sys, time
import spec4.llm as llm

def fake_stream_turn(system_prompt, messages, llm_config, search_config,
                     agent_name=None, response_format=None, session=None):
    words = ("Here is the existing vision, summarised for review. " * 6).split()
    out = []
    for w in words:
        time.sleep(0.01)
        out.append(w)
        yield w + " "
    messages.append({"role": "assistant", "content": " ".join(out)})

llm.stream_turn = fake_stream_turn
llm.complete = lambda *a, **k: "{}"

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


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """An existing project: a code review and a vision already on disk.

    The vision is what the Artifact View opens; the code review is what makes
    this the brownfield entry the report describes.
    """
    root = tmp_path_factory.mktemp("page-slot-e2e")
    version = root / ".spec4" / "v0"
    version.mkdir(parents=True)
    (version / "code_review.json").write_text(
        json.dumps({"schema_version": 1, "is_software_project": True}),
        encoding="utf-8",
    )
    (version / "vision.json").write_text(
        json.dumps({"app_name": "Thing", "purpose": "x"}), encoding="utf-8"
    )
    (root / "main.py").write_text("print('hi')\n", encoding="utf-8")
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
    """The project view of an existing project, connected, mode answered.

    Brainstormer has *not* been asked about its model yet, so the gate opens
    on the first click exactly as it did in the report.
    """
    return {
        "phase": "agent_select",
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
        "active_agent": "brainstormer",
        "messages": [],
        "agent_llm": {},
        "agent_llm_asked": {},
    }


@pytest.fixture
def page(browser: Any, base_url: str, project: pathlib.Path) -> Iterator[Page]:
    context = browser.new_context(viewport=VIEWPORT)
    session = json.dumps(json.dumps(_session(project)))
    prefs = json.dumps(json.dumps({"working_dir": str(project)}))
    context.add_init_script(
        f"window.localStorage.setItem('prefs', {prefs});"
        "window.localStorage.setItem('prefs-timestamp', Date.now());"
        f"window.sessionStorage.setItem('session', {session});"
        "window.sessionStorage.setItem('session-timestamp', Date.now());"
    )
    opened = context.new_page()
    errors: list[str] = []
    opened.on(
        "console",
        lambda message: (
            errors.append(message.text) if message.type == "error" else None
        ),
    )
    opened.on("pageerror", lambda exc: errors.append(str(exc)))
    opened.set_default_timeout(_WAIT_MS)
    opened.goto(f"{base_url}/agents")
    opened.wait_for_selector("#agent-rows")
    try:
        yield opened
    finally:
        assert errors == [], f"browser console errors: {errors}"
        context.close()


def _wait_stream_idle(page: Page) -> None:
    """Until the session store says the turn has finished."""
    deadline = time.monotonic() + _STREAM_IDLE_S
    while time.monotonic() < deadline:
        raw = page.evaluate("() => window.sessionStorage.getItem('session')")
        data = json.loads(raw) if raw else {}
        if not data.get("_stream_id") and data.get("_initial_turn_done"):
            return
        time.sleep(0.1)
    pytest.fail("the Brainstormer turn never went idle")


def _frame_children(page: Page) -> int:
    """How many elements the page slot's root has under it."""
    return int(
        page.evaluate(
            "() => document.querySelector('#page-content > *').children.length"
        )
    )


class TestClickingTheChatBoxAfterTheArtifactView:
    """The reported walk, step for step."""

    def test_the_frame_is_still_there(self, page: Page) -> None:
        # 3–4. Start Brainstormer on the default model.
        page.click("#agent-row-brainstormer button")
        page.wait_for_selector("#btn-agent-llm-default")
        page.click("#btn-agent-llm-default")
        page.wait_for_selector("#chat-input")
        _wait_stream_idle(page)

        # 5. Open vision.json in the Artifact View.
        page.click("#status-bar-nav-artifacts")
        page.wait_for_selector("#artifact-view-tree-list")
        page.click("#artifact-view-tree-list button:has-text('vision.json')")
        page.wait_for_selector("#artifact-view-tree-list li.is-selected")

        # 6. Back to the project, continue Brainstormer.
        page.click("#status-bar-nav-project")
        page.wait_for_selector("#agent-rows")
        page.click("#agent-row-brainstormer button")
        page.wait_for_selector("#chat-input")
        _wait_stream_idle(page)
        page.wait_for_selector("#chat-scroll-area .chat-msg")
        before = _frame_children(page)
        assert before > 1

        # 7. Click in the chat box. The frame must be exactly what it was.
        page.click("#chat-input")
        # Long enough for a click-driven re-render to land; the failure was
        # immediate and permanent, so a settled frame after this is the claim.
        page.wait_for_timeout(1500)
        assert _frame_children(page) == before
        assert page.locator("#chat-scroll-area").count() == 1
        assert page.locator("#chat-input").count() == 1
        assert page.locator(".pipeline .pipeline-agent--active").inner_text() == (
            "Brainstormer"
        )


class TestTheSlotDoesNotCountClicks:
    """The flag itself, read off the layout, so the reason survives even where
    no browser is available to run the walk above."""

    def test_page_content_has_n_clicks_disabled(self) -> None:
        from spec4.app import app

        def find(node: Any) -> Any:
            if getattr(node, "id", None) == "page-content":
                return node
            children = getattr(node, "children", None)
            if children is None:
                return None
            if not isinstance(children, (list, tuple)):
                children = [children]
            for child in children:
                found = find(child)
                if found is not None:
                    return found
            return None

        slot = find(app.layout)
        assert slot is not None
        assert getattr(slot, "disable_n_clicks", False) is True
