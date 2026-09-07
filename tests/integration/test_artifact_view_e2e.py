"""The Artifact View in a real browser: click a tree line, read the file.

Everything else about this screen is asserted against a component tree, which
is the right level for almost all of it — but three of its claims are only
true once a browser has run the page, and a Python-side assertion cannot see
any of them:

*The click reaches the callback.* A pattern-matching id is two halves that have
to agree, and when they do not, Dash raises nothing and logs nothing — the line
simply stops doing anything. Only a real click can tell the difference.

*The round selector and the pane are wired together.* The selector writes the
session, the session redraws the page, the page redraws the pane. Each link is
tested on its own; this walks the whole chain the way a developer does.

*The file block actually scrolls.* Its height is a CSS bound on a Mantine
ScrollArea, and whether that produces a scroller or a clipped box is a question
about layout, not about markup. A large artifact is loaded here and the
viewport is measured.

The test drives the app the same way a developer arriving from a bookmark
does: a remembered working directory in ``localStorage`` and a deep URL. That
is a supported entry point in its own right (``on_browser_navigate`` restores
the project for it), so nothing here is set up through a back door the product
does not have.
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

# The artifact the phase's verification opens by name, and what is written into
# it. Compact on disk so that the pretty-printing is visible in the browser as
# a difference from the file rather than as a claim about it.
STACK_JSON = '{"stack":["dash","dash-mantine-components"],"round":1}'

# The mock's own HTML, with a marker only a browser that actually rendered it
# would expose as an element a Playwright locator can read. Viewed as text —
# the content pane's own rendering, line-numbered like every other file — this
# is a string containing the literal characters ``<h1>``; only "Open rendered"
# turns it into a heading.
MOCK_MARKER = "Rendered Mock"
MOCK_HTML = f"<html><body><h1>{MOCK_MARKER}</h1></body></html>"

# Long enough that the block must scroll at any plausible window height, and
# long enough that a per-line component tree would be visible as one.
LARGE_LINES = 4000

_LAUNCH_TIMEOUT_MS = 30_000

# Every wait in this file. Generous enough for a cold first paint, short enough
# that a genuinely broken selector fails the test rather than stalling the
# suite for the default half-minute a time.
_WAIT_MS = 10_000

# How long to give the server subprocess to come up before giving up on it.
_BOOT_TIMEOUT_S = 60.0

# The server, run in a process of its own. It has to be a separate process
# rather than a thread: serving a Dash app drains ``dash._callback`` module
# globals into the app object, and three other test modules in this suite
# inspect exactly those globals to prove a control is wired to a callback.
# Running the app in-process would empty the registry under them and fail
# them, in a different file, for a reason nothing there could explain.
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


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """A two-round project: v1 populated and active, v0 with only ``stack.json``.

    Two rounds because one group of assertions is about switching between
    them, and the interesting case is a file that exists in one and not the
    other — ``phases/phase1.md`` is that file, exactly as it is in the unit
    tests. The *newest* round is the populated one because that is the round
    the screen opens on, and the tests that are not about switching should
    reach the files they name without a detour.
    """
    root = tmp_path_factory.mktemp("artifact-view-e2e")
    older = root / ".spec4" / "v0"
    older.mkdir(parents=True)
    (older / "stack.json").write_text(STACK_JSON, encoding="utf-8")

    active = root / ".spec4" / "v1"
    (active / "phases").mkdir(parents=True)
    (active / "stack.json").write_text(STACK_JSON, encoding="utf-8")
    (active / "phases" / "phase1.md").write_text(
        "# Phase 1\n\nRead this **verbatim**.\n", encoding="utf-8"
    )
    (active / "deployment-plan.md").write_text(
        "\n".join(f"line {n}" for n in range(LARGE_LINES)) + "\n", encoding="utf-8"
    )
    (active / "design").mkdir()
    (active / "design" / "mock.html").write_text(MOCK_HTML, encoding="utf-8")
    return root


def _serving(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return bool(response.status == 200)
    except (urllib.error.URLError, OSError):
        return False


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    """The app, served in its own process for the duration of the module."""
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


@pytest.fixture
def page(browser: Any, base_url: str, project: pathlib.Path) -> Iterator[Page]:
    """A page at ``/artifacts``, with the project already remembered.

    The working directory is seeded into ``localStorage`` under the ``prefs``
    store's own key, which is the same state a developer's browser is in after
    they have opened a project once. Console errors are collected and asserted
    empty at the end of every test that uses this: a Dash callback referencing
    a component that is not on the page fails exactly there and nowhere else.
    """
    context = browser.new_context()
    prefs = json.dumps(json.dumps({"working_dir": str(project)}))
    context.add_init_script(
        f"window.localStorage.setItem('prefs', {prefs});"
        "window.localStorage.setItem('prefs-timestamp', Date.now());"
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
    opened.goto(f"{base_url}/artifacts")
    opened.wait_for_selector("#artifact-view-tree-list li")
    try:
        yield opened
    finally:
        assert errors == [], f"browser console errors: {errors}"
        context.close()


def _open(page: Page, path: str) -> None:
    """Click the tree line for `path` and wait for the pane to catch up."""
    page.click(f"#artifact-view-tree-list button:has-text('{path}')")
    page.wait_for_selector(f"#artifact-view-header:has-text('{path}')")


def _gutter(page: Page) -> str:
    return page.inner_text("#artifact-view-scroll .file-gutter")


def _content(page: Page) -> str:
    return page.inner_text("#artifact-view-scroll .file-content")


# ---------------------------------------------------------------------------
# Opening a file from the tree
# ---------------------------------------------------------------------------


class TestOpeningStackJson:
    """The phase's own verification, driven end to end."""

    def test_the_tree_lists_the_round_s_artifacts(self, page: Page) -> None:
        listing = page.inner_text("#artifact-view-tree-list")
        assert "stack.json" in listing
        assert "phases/phase1.md" in listing

    def test_the_header_shows_the_file_s_path(self, page: Page) -> None:
        _open(page, "stack.json")
        assert ".spec4/v1/stack.json" in page.inner_text("#artifact-view-header")

    def test_the_header_shows_size_modified_and_lane_after_the_path(
        self, page: Page
    ) -> None:
        _open(page, "stack.json")
        header = page.inner_text("#artifact-view-header")
        positions = [
            header.index(".spec4/v1/stack.json"),
            header.index(" B"),
            header.index("modified"),
            header.index("reference for the agent"),
        ]
        assert positions == sorted(positions)

    def test_the_content_pane_shows_pretty_printed_json(self, page: Page) -> None:
        """Pretty-printed, and visibly *not* what is on disk.

        The file is one compact line; the pane shows seven indented ones. The
        assertion is against the re-serialised form rather than against a
        substring, so a pane that had merely echoed the file would fail.
        """
        _open(page, "stack.json")
        assert _content(page) == json.dumps(json.loads(STACK_JSON), indent=2)

    def test_the_content_pane_has_a_line_number_gutter(self, page: Page) -> None:
        _open(page, "stack.json")
        assert _gutter(page).split("\n") == ["1", "2", "3", "4", "5", "6", "7"]

    def test_the_gutter_has_a_line_for_every_line_of_content(self, page: Page) -> None:
        _open(page, "stack.json")
        assert len(_gutter(page).split("\n")) == len(_content(page).split("\n"))

    def test_the_gutter_and_the_content_line_up(self, page: Page) -> None:
        """The alignment the single CSS rule exists to guarantee, measured.

        Two ``<pre>`` elements laid out side by side line up only if they have
        the same line height, and a stylesheet can be wrong about that without
        anything else looking broken. Comparing their rendered heights catches
        a drift the markup cannot show.
        """
        _open(page, "stack.json")
        gutter = page.locator("#artifact-view-scroll .file-gutter").bounding_box()
        content = page.locator("#artifact-view-scroll .file-content").bounding_box()
        assert gutter is not None and content is not None
        assert gutter["height"] == pytest.approx(content["height"], abs=1)
        assert gutter["y"] == pytest.approx(content["y"], abs=1)

    def test_the_selected_line_is_marked_in_the_tree(self, page: Page) -> None:
        _open(page, "stack.json")
        selected = page.locator("#artifact-view-tree-list li.is-selected")
        assert selected.count() == 1
        assert "stack.json" in selected.inner_text()


class TestOpeningAPhaseFile:
    def test_markdown_is_shown_as_written(self, page: Page) -> None:
        """No renderer and no highlighter: the phase file is a prompt handed to
        a coding agent verbatim, and this is where a developer checks it."""
        _open(page, "phases/phase1.md")
        assert _content(page) == "# Phase 1\n\nRead this **verbatim**."
        assert _gutter(page).split("\n") == ["1", "2", "3"]

    def test_it_is_not_rendered_as_html(self, page: Page) -> None:
        _open(page, "phases/phase1.md")
        block = page.inner_html("#artifact-view-scroll .file-content")
        assert "<h1" not in block
        assert "<strong" not in block


class TestAMissingArtifact:
    def test_its_line_is_still_in_the_tree(self, page: Page) -> None:
        assert "vision.json" in page.inner_text("#artifact-view-tree-list")

    def test_selecting_it_names_the_agent_that_would_produce_it(
        self, page: Page
    ) -> None:
        page.click("#artifact-view-tree-list button:has-text('vision.json')")
        page.wait_for_selector(".file-missing")
        assert (
            page.inner_text(".file-missing")
            == "vision.json — missing — produced by Brainstormer"
        )


class TestDownload:
    """The control the phase's own verification exercises: a copy of exactly
    the file the pane is showing, offered and disabled in step with it."""

    def test_it_is_disabled_with_nothing_selected(self, page: Page) -> None:
        assert page.is_disabled("#artifact-download-btn")

    def test_it_is_disabled_for_a_missing_artifact(self, page: Page) -> None:
        page.click("#artifact-view-tree-list button:has-text('vision.json')")
        page.wait_for_selector(".file-missing")
        assert page.is_disabled("#artifact-download-btn")

    def test_it_downloads_the_selected_file(self, page: Page) -> None:
        _open(page, "stack.json")
        with page.expect_download() as download_info:
            page.click("#artifact-download-btn")
        download = download_info.value
        assert download.suggested_filename == "stack.json"


class TestOpenRendered:
    """The mock, opened rendered rather than as the text every other artifact
    gets — the one control this phase adds beyond Download.

    The content pane's own rendering of ``design/mock.html`` is exactly what
    every other file gets: line-numbered text, ``<`` and all. Only a real
    browser can tell that apart from a page that actually rendered the markup
    — a component-tree assertion sees the same string either way — which is
    why this is here and not in the unit suite.
    """

    def test_the_button_is_present_for_the_mock(self, page: Page) -> None:
        _open(page, "design/mock.html")
        assert page.locator("#artifact-open-rendered-btn").count() == 1

    def test_the_button_is_absent_for_every_other_artifact(self, page: Page) -> None:
        _open(page, "stack.json")
        assert page.locator("#artifact-open-rendered-btn").count() == 0

    def test_the_content_pane_shows_the_mock_as_text_first(self, page: Page) -> None:
        """The raw source, line-numbered like any other file — the claim the
        rendered-tab assertion below depends on to mean anything."""
        _open(page, "design/mock.html")
        assert f"<h1>{MOCK_MARKER}</h1>" in _content(page)

    def test_clicking_it_opens_a_new_tab_with_the_mock_rendered(
        self, page: Page
    ) -> None:
        _open(page, "design/mock.html")
        with page.expect_popup() as new_page_info:
            page.click("#artifact-open-rendered-btn")
        rendered = new_page_info.value
        rendered.wait_for_load_state()
        assert rendered.locator("h1").inner_text() == MOCK_MARKER
        rendered.close()


# ---------------------------------------------------------------------------
# Switching rounds
# ---------------------------------------------------------------------------


class TestTheRoundSelector:
    """The strip of rounds, and what a round switch does to the screen.

    Every case here switches at least once *after* the page has been rebuilt
    by an earlier interaction. That is the sequence that matters: a control
    whose value is re-asserted by the rebuild works exactly once and then
    silently sticks, which is why the strip is buttons carrying ``n_clicks``
    and why these assertions are made in a browser rather than against a
    component tree.
    """

    def _choose(self, page: Page, label: str) -> None:
        page.click(f"#artifact-round-select button:text-is('{label}')")
        page.wait_for_selector(f"#artifact-view-tree-head:has-text('.spec4/{label}/')")

    def test_it_offers_every_round_on_disk(self, page: Page) -> None:
        rounds = page.locator("#artifact-round-select button")
        assert rounds.count() == 2
        assert rounds.nth(0).inner_text() == "v0"
        assert rounds.nth(1).inner_text() == "v1"

    def test_the_active_round_is_marked(self, page: Page) -> None:
        marked = page.locator("#artifact-round-select button.is-active")
        assert marked.count() == 1
        assert marked.inner_text() == "v1"

    def test_the_mark_moves_with_the_selection(self, page: Page) -> None:
        self._choose(page, "v0")
        marked = page.locator("#artifact-round-select button.is-active")
        assert marked.count() == 1
        assert marked.inner_text() == "v0"

    def test_it_keeps_switching_after_the_page_has_been_rebuilt(
        self, page: Page
    ) -> None:
        """Four switches in a row, both directions, each after a rebuild.

        The failure this closes is not a wrong render — it is a control that
        stops responding after the first use, with nothing raised and nothing
        logged. One switch would pass against exactly that.
        """
        for label in ("v0", "v1", "v0", "v1"):
            self._choose(page, label)
            assert f".spec4/{label}/" in page.inner_text("#artifact-view-tree-head")

    def test_it_keeps_switching_after_a_file_has_been_opened(self, page: Page) -> None:
        """A tree click rebuilds the page too, so it must not jam the strip."""
        _open(page, "stack.json")
        self._choose(page, "v0")
        self._choose(page, "v1")
        assert ".spec4/v1/" in page.inner_text("#artifact-view-tree-head")

    def test_switching_rounds_updates_the_tree(self, page: Page) -> None:
        assert "phases/phase1.md" in page.inner_text("#artifact-view-tree-list")
        self._choose(page, "v0")
        assert "phases/phase1.md" not in page.inner_text("#artifact-view-tree-list")

    def test_a_file_the_new_round_lacks_is_dropped_rather_than_refused(
        self, page: Page
    ) -> None:
        """The clearing rule, as the developer meets it.

        Open a v1-only file, switch to v0, and the pane returns to its empty
        state — not to a rejection for a line the tree is no longer drawing.
        """
        _open(page, "phases/phase1.md")
        self._choose(page, "v0")
        page.wait_for_selector(".file-empty")
        assert page.inner_text(".file-empty") == "Select a file"

    def test_a_file_both_rounds_have_survives_the_switch(self, page: Page) -> None:
        _open(page, "stack.json")
        self._choose(page, "v0")
        page.wait_for_selector("#artifact-view-header:has-text('.spec4/v0/stack.json')")
        assert _content(page) == json.dumps(json.loads(STACK_JSON), indent=2)


# ---------------------------------------------------------------------------
# A large artifact
# ---------------------------------------------------------------------------


class TestALargeArtifact:
    """The failure mode the two-``<pre>`` structure exists to avoid."""

    def _open_large(self, page: Page) -> None:
        page.click("#artifact-view-tree-list button:has-text('deployment-plan.md')")
        page.wait_for_selector("#artifact-view-scroll")

    def test_every_line_is_numbered(self, page: Page) -> None:
        self._open_large(page)
        assert _gutter(page).split("\n")[-1] == str(LARGE_LINES)

    def test_the_whole_file_is_four_dom_nodes_not_four_thousand(
        self, page: Page
    ) -> None:
        """Counted in the browser, where the cost actually lands.

        A component per line would put two elements per line into the DOM for
        Dash to serialise, ship and diff on every render. This is the same
        claim the component-tree test makes, made against the thing that
        renders it.
        """
        self._open_large(page)
        nodes = page.eval_on_selector(
            "#artifact-view-scroll .file-lines",
            "el => el.querySelectorAll('*').length",
        )
        assert nodes == 2

    def test_the_block_scrolls_rather_than_clipping(self, page: Page) -> None:
        """A ``max-height`` that clips instead of scrolling looks identical in
        the markup and loses the developer every line past the fold."""
        self._open_large(page)
        metrics = page.eval_on_selector(
            "#artifact-view-scroll",
            """el => {
                const view = el.querySelector('[class*="ScrollArea-viewport"]') || el;
                view.scrollTop = 400;
                return {
                    scrollable: view.scrollHeight > view.clientHeight + 1,
                    moved: view.scrollTop,
                    clientHeight: view.clientHeight,
                };
            }""",
        )
        assert metrics["clientHeight"] > 0
        assert metrics["scrollable"]
        assert metrics["moved"] > 0

    def test_the_page_itself_does_not_scroll(self, page: Page) -> None:
        """The pane scrolls; the header above it stays put."""
        self._open_large(page)
        overflowing = page.evaluate(
            "document.documentElement.scrollHeight >"
            " document.documentElement.clientHeight + 1"
        )
        assert not overflowing
