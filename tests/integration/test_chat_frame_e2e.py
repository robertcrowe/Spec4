"""The chat frame in a real browser: does it scroll, and do its links work?

Two claims, and neither can be made by a Python-side assertion.

*The transcript scrolls itself.* ``height: 60vh`` plus ``overflow-y: auto`` is
markup that looks correct whether or not it produces a scroller: whether a
taller transcript scrolls inside its own box or simply pushes the composer off
the bottom of the window is a question about layout, and only a browser can
answer it. The failure mode the phase names — the transcript growing the page
instead of scrolling at a small viewport — is invisible everywhere else.

*An Open button in the action row lands on the artifact.* The click has to
reach a callback, the callback has to write the session store, the store change
has to redraw the page at ``/artifacts``, and the Artifact View has to resolve
and render the file the selection names. Every link in that chain is tested on
its own; only a browser walks the whole thing, and a callback whose Input is
not on the page fails there and nowhere else.

The window is deliberately a mid-size one rather than the default: 60vh of a
1280x720 laptop window is the case the developer is actually in, and it is the
case where a transcript long enough to overflow has to stay inside its box.
The same measurements are then repeated at a short window, where 60vh is
smaller than the ``min-height`` floor — the point at which a bad rule would
overflow the page rather than the transcript.

The app is driven the way the Artifact View's own end-to-end test drives it:
the session store is seeded in ``sessionStorage``, exactly as it would be after
the developer had opened this agent, and the deep URL is a supported entry
point (``on_browser_navigate``).
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

from spec4 import project_manager  # noqa: E402

# Enough turns that the transcript must scroll in any window this test uses.
TURNS = 30

_LAUNCH_TIMEOUT_MS = 30_000
_WAIT_MS = 10_000
_BOOT_TIMEOUT_S = 60.0

# A laptop window, and a short one. 60vh of the short window is under the
# 200px floor, which is the case where a transcript that had been allowed to
# grow the page instead of scrolling would show it.
MID_VIEWPORT = {"width": 1280, "height": 720}
SHORT_VIEWPORT = {"width": 1024, "height": 600}

# The server, in a process of its own — serving a Dash app in-process drains
# the `dash._callback` module globals that three other test modules inspect.
# The same reason, and the same shape, as the Artifact View's harness.
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


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """A project mid-round: Brainstormer is running and has a vision on disk."""
    root = tmp_path_factory.mktemp("chat-frame-e2e")
    version = root / ".spec4" / "v1"
    version.mkdir(parents=True)
    (version / "vision.json").write_text('{"purpose": "x"}', encoding="utf-8")
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
    """A Brainstormer session part-way through a run, with a long transcript.

    ``phase`` is already ``chat``, which is what stops the router treating this
    as a fresh browser session and re-opening the project behind it; the model
    config is present so the per-agent gate is answered and the transcript,
    rather than the gate card, is what the frame draws.
    """
    return {
        "phase": "chat",
        "working_dir": str(project),
        "active_agent": "brainstormer",
        "vision_statement": {"purpose": "x"},
        "provider": "anthropic",
        "model": "claude-sonnet-5",
        "llm_config": {"model": "claude-sonnet-5", "api_key": "k"},
        "agent_llm_asked": {"brainstormer": True},
        "_initial_turn_done": True,
        "messages": [
            {
                "role": "user" if n % 2 == 0 else "assistant",
                "content": f"Turn {n}. " + "Something said at some length. " * 6,
            }
            for n in range(TURNS)
        ],
    }


def _page_at(browser: Any, base_url: str, project: pathlib.Path, viewport: Any) -> Any:
    context = browser.new_context(viewport=viewport)
    session = json.dumps(json.dumps(_session(project)))
    prefs = json.dumps(json.dumps({"working_dir": str(project)}))
    context.add_init_script(
        f"window.localStorage.setItem('prefs', {prefs});"
        "window.localStorage.setItem('prefs-timestamp', Date.now());"
        f"window.sessionStorage.setItem('session', {session});"
        "window.sessionStorage.setItem('session-timestamp', Date.now());"
    )
    return context


@pytest.fixture
def page(browser: Any, base_url: str, project: pathlib.Path) -> Iterator[Page]:
    """The chat frame at a mid viewport, with the transcript already long."""
    context = _page_at(browser, base_url, project, MID_VIEWPORT)
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
    opened.goto(f"{base_url}/chat")
    opened.wait_for_selector("#chat-scroll-area .chat-bubble-user")
    try:
        yield opened
    finally:
        assert errors == [], f"browser console errors: {errors}"
        context.close()


def _metrics(page: Page) -> dict[str, Any]:
    return page.eval_on_selector(
        "#chat-scroll-area",
        """el => {
            el.scrollTop = 200;
            const doc = document.documentElement;
            return {
                clientHeight: el.clientHeight,
                scrollHeight: el.scrollHeight,
                moved: el.scrollTop,
                windowHeight: window.innerHeight,
                pageOverflows: doc.scrollHeight > doc.clientHeight + 1,
            };
        }""",
    )


# ---------------------------------------------------------------------------
# The transcript scrolls itself
# ---------------------------------------------------------------------------


class TestTheTranscriptScrollsIndependently:
    def test_the_transcript_overflows_its_own_box(self, page: Page) -> None:
        """The precondition for everything else here: thirty turns do not fit."""
        metrics = _metrics(page)
        assert metrics["clientHeight"] > 0
        assert metrics["scrollHeight"] > metrics["clientHeight"] + 1

    def test_it_scrolls_rather_than_clipping(self, page: Page) -> None:
        assert _metrics(page)["moved"] > 0

    def test_the_page_itself_does_not_scroll(self, page: Page) -> None:
        """The whole point of the bound: the transcript moves, the frame around
        it — pipeline above, composer and model chip below — stays put."""
        assert not _metrics(page)["pageOverflows"]

    def test_the_height_is_roughly_sixty_percent_of_the_viewport(
        self, page: Page
    ) -> None:
        """Noticeably taller than the 450px it was, and stated as a share of
        the window rather than as a number, so it is the same share at every
        size. The tolerance covers the border and padding around the content
        box the browser reports."""
        metrics = _metrics(page)
        share = metrics["clientHeight"] / metrics["windowHeight"]
        assert 0.55 < share < 0.65, metrics

    def test_the_composer_is_still_on_screen_under_it(self, page: Page) -> None:
        """A transcript that had grown the page would have pushed it off."""
        box = page.locator("#chat-input").bounding_box()
        assert box is not None
        assert box["y"] + box["height"] <= page.viewport_size["height"] + 1


class TestAtAShortViewport:
    """Where 60vh falls under the 200px floor — the regression the phase's
    mitigation is aimed at. A rule that only worked on a tall window would
    overflow the page here instead of the transcript."""

    def test_it_still_scrolls_itself(
        self, browser: Any, base_url: str, project: pathlib.Path
    ) -> None:
        context = _page_at(browser, base_url, project, SHORT_VIEWPORT)
        opened = context.new_page()
        opened.set_default_timeout(_WAIT_MS)
        try:
            opened.goto(f"{base_url}/chat")
            opened.wait_for_selector("#chat-scroll-area .chat-bubble-user")
            metrics = _metrics(opened)
            assert metrics["clientHeight"] > 0
            assert metrics["scrollHeight"] > metrics["clientHeight"] + 1
            assert metrics["moved"] > 0
        finally:
            context.close()


# ---------------------------------------------------------------------------
# What the frame looks like once it has rendered
# ---------------------------------------------------------------------------


class TestTheRenderedFrame:
    def test_the_pipeline_reads_as_seven_plain_labels(self, page: Page) -> None:
        labels = page.locator(".pipeline .pipeline-agent")
        assert labels.count() == 7
        assert "→" not in page.inner_text(".pipeline")

    def test_the_active_agent_is_marked(self, page: Page) -> None:
        active = page.locator(".pipeline .pipeline-agent--active")
        assert active.count() == 1
        assert active.inner_text() == "Brainstormer"

    def test_each_turn_carries_a_speaker_label(self, page: Page) -> None:
        labels = page.locator("#chat-scroll-area .msg-label")
        assert labels.count() == TURNS
        assert labels.first.inner_text() == "You"
        assert labels.nth(1).inner_text() == "Brainstormer"

    def test_no_transcript_block_is_filled(self, page: Page) -> None:
        """Measured as the browser resolves it, not as the stylesheet reads."""
        backgrounds = page.eval_on_selector_all(
            "#chat-scroll-area .chat-msg",
            "els => els.map(el => getComputedStyle(el).backgroundColor)",
        )
        assert backgrounds
        assert set(backgrounds) == {"rgba(0, 0, 0, 0)"}

    def test_the_model_name_renders_in_monospace(self, page: Page) -> None:
        font = page.eval_on_selector(
            "#btn-agent-llm-chip .mono",
            "el => getComputedStyle(el).fontFamily",
        )
        assert "Mono" in font or "monospace" in font


# ---------------------------------------------------------------------------
# The removed Back controls have live equivalents
# ---------------------------------------------------------------------------


def _stack_advisor_session(project: pathlib.Path) -> dict[str, Any]:
    """A StackAdvisor run part-way through, with every gate already answered.

    The gates matter here in a way they do not for the transcript tests: this
    walks *between* screens, so an unanswered gate on the far side would draw
    a model card instead of the thing being navigated to. `_initial_turn_done`
    keeps the frame from opening a real turn on arrival, which would be a
    network call this test has no business making.
    """
    return {
        "phase": "chat",
        "working_dir": str(project),
        "active_agent": "stack_advisor",
        "vision_statement": {"purpose": "x"},
        "stack_statement": {"stack": []},
        "provider": "anthropic",
        "model": "claude-sonnet-5",
        "llm_config": {"model": "claude-sonnet-5", "api_key": "k"},
        "agent_llm_asked": {
            "stack_advisor": True,
            "designer": True,
            "brainstormer": True,
        },
        "_initial_turn_done": True,
        "messages": [{"role": "assistant", "content": "Which database?"}],
    }


@pytest.fixture
def stack_advisor(browser: Any, base_url: str, project: pathlib.Path) -> Iterator[Page]:
    """The StackAdvisor chat frame, which is where both walks start."""
    context = browser.new_context(viewport=MID_VIEWPORT)
    session = json.dumps(json.dumps(_stack_advisor_session(project)))
    prefs = json.dumps(json.dumps({"working_dir": str(project)}))
    context.add_init_script(
        f"window.localStorage.setItem('prefs', {prefs});"
        "window.localStorage.setItem('prefs-timestamp', Date.now());"
        f"window.sessionStorage.setItem('session', {session});"
        "window.sessionStorage.setItem('session-timestamp', Date.now());"
    )
    opened = context.new_page()
    opened.set_default_timeout(_WAIT_MS)
    try:
        opened.goto(f"{base_url}/chat")
        opened.wait_for_selector(".pipeline .pipeline-agent--active")
        assert opened.inner_text(".pipeline .pipeline-agent--active") == "StackAdvisor"
        yield opened
    finally:
        context.close()


class TestTheBackRoutesHaveLiveEquivalents:
    """D-LR8, in a browser. The four Back controls are gone; the claim that let
    them go is that every screen they reached is still one click away, and that
    claim is about live routing rather than about a rendered id.

    Two of the four are walked here — the two whose replacement is a *different*
    control rather than the same pill the bar has always had. `← Back` went to
    the project view, which is now the status bar's Project link; `← Back to
    Designer` went to the Designer, which is now that agent's pill. The other
    two (Phaser → StackAdvisor, Deployer → Phaser) are replaced by pills for
    agents already in the bar, and whether those pills are live is a question
    about preconditions that `test_chat_pill_bar.py` asks directly.

    Note what the second walk lands on: `/design`, the Designer wizard. Designer
    is the one pipeline stage with no chat turn, so there is no Designer chat
    frame to reach — the pill routes to the wizard, and that is the screen the
    removed button went to as well.
    """

    def test_the_project_link_reaches_the_project_view(
        self, stack_advisor: Page, project: pathlib.Path
    ) -> None:
        """What `← Back` did, from a link that is mounted on every screen."""
        stack_advisor.click("#status-bar-nav-project")
        stack_advisor.wait_for_url("**/agents")
        stack_advisor.wait_for_selector("#agent-rows")
        assert stack_advisor.locator("#round-tree").count() == 1

    def test_the_designer_pill_reaches_the_designer(self, stack_advisor: Page) -> None:
        """What `← Back to Designer` did, from the bar that was always there."""
        pill = stack_advisor.locator(".pipeline .pipeline-agent", has_text="Designer")
        assert pill.count() == 1
        assert not pill.is_disabled()
        pill.click()
        stack_advisor.wait_for_url("**/design")
        stack_advisor.wait_for_selector("#designer-stepper")

    def test_no_back_control_is_left_on_the_frame(self, stack_advisor: Page) -> None:
        """The other half of the criterion: the routes survived, the buttons
        did not. Asserted on the rendered text, because a button removed from
        one agent's branch and left in another's would still pass a test that
        only looked at StackAdvisor's ids."""
        buttons = stack_advisor.eval_on_selector_all(
            "button", "els => els.map(el => el.innerText.trim())"
        )
        assert buttons
        assert not [text for text in buttons if text.startswith("\u2190 Back")]


# ---------------------------------------------------------------------------
# Open, in the action row
# ---------------------------------------------------------------------------

# What the finished run's artifact holds on disk, written compact so the
# Artifact View's pretty-printing is visible in the browser as a difference
# from the file rather than as a claim about it.
VISION_JSON = '{"app_name":"Spec4","purpose":"x"}'


def _finished_run_session(project: pathlib.Path) -> dict[str, Any]:
    """A Brainstormer run that has completed and emitted its vision.

    The completion state *and* the artifact stamp, because the action row and
    the cost strip both key off the pair: the state says the agent produced its
    artifact at some point, the stamp says the artifact is the last message.
    `_initial_turn_done` keeps the frame from opening a real turn on arrival,
    which would be a network call this test has no business making.
    """
    messages = [
        {"role": "user", "content": "Build me something."},
        {"role": "assistant", "content": "Here is the vision."},
    ]
    return {
        "phase": "chat",
        "working_dir": str(project),
        "active_agent": "brainstormer",
        "vision_statement": {"app_name": "Spec4"},
        "brainstormer_state": "vision_complete",
        "brainstormer_messages": messages,
        "brainstormer_artifact_msg_count": len(messages),
        "provider": "anthropic",
        "model": "claude-sonnet-5",
        "llm_config": {"model": "claude-sonnet-5", "api_key": "k"},
        "agent_llm_asked": {"brainstormer": True},
        "_initial_turn_done": True,
        "messages": messages,
    }


@pytest.fixture(scope="module")
def finished_project(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """A project whose newest round has a vision and a usage record on disk.

    Separate from the module's other project because this one must be
    *finished*: the round's `vision.json` is what the Open button opens, and
    `usage.json` is what the completed run's cost strip reports on.
    """
    root = tmp_path_factory.mktemp("chat-open-e2e")
    version = root / ".spec4" / "v0"
    version.mkdir(parents=True)
    (version / "vision.json").write_text(VISION_JSON, encoding="utf-8")
    project_manager.save_usage(
        root,
        [
            {
                "timestamp": "2026-09-02T00:00:00+00:00",
                "agent": "brainstormer",
                "model": "gpt-4o-mini",
                "provider": "openai",
                "streamed": True,
                "duration_s": 1.0,
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
                "cached_tokens": None,
                "cache_creation_input_tokens": None,
                "cache_read_input_tokens": None,
                "computed_cost_usd": 0.0042,
                "usage_missing": False,
                "error": None,
            }
        ],
        0,
    )
    return root


@pytest.fixture
def finished(
    browser: Any, base_url: str, finished_project: pathlib.Path
) -> Iterator[Page]:
    """The chat frame for a run that has already completed."""
    context = browser.new_context(viewport=MID_VIEWPORT)
    session = json.dumps(json.dumps(_finished_run_session(finished_project)))
    prefs = json.dumps(json.dumps({"working_dir": str(finished_project)}))
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
    try:
        opened.goto(f"{base_url}/chat")
        opened.wait_for_selector("#btn-dl-vision")
        yield opened
    finally:
        assert errors == [], f"browser console errors: {errors}"
        context.close()


class TestOpenLeadsIntoTheArtifactView:
    """The phase's own verification, driven end to end."""

    def test_every_download_has_an_open_beside_it(self, finished: Page) -> None:
        """The rendered row, not the component tree: a button that failed to
        mount would still be in the tree the unit test walks."""
        downloads = finished.locator("button[id^='btn-dl-']")
        opens = finished.locator("button[id^='btn-open-']")
        assert downloads.count() == 1
        assert opens.count() == downloads.count()
        assert opens.first.inner_text() == "Open vision.json"

    def test_clicking_it_opens_that_artifact(self, finished: Page) -> None:
        finished.click("#btn-open-vision")
        finished.wait_for_url("**/artifacts")
        finished.wait_for_selector("#artifact-view-scroll")
        assert ".spec4/v0/vision.json" in finished.inner_text(
            "#artifact-view-header"
        )

    def test_the_file_s_content_is_rendered(self, finished: Page) -> None:
        """Not merely selected: the pane shows the file, pretty-printed, with
        its line-number gutter beside it."""
        finished.click("#btn-open-vision")
        finished.wait_for_selector("#artifact-view-scroll")
        content = finished.inner_text("#artifact-view-scroll .file-content")
        assert content == json.dumps(json.loads(VISION_JSON), indent=2)
        gutter = finished.inner_text("#artifact-view-scroll .file-gutter")
        assert gutter.split("\n") == ["1", "2", "3", "4"]

    def test_the_tree_beside_it_marks_the_same_line(self, finished: Page) -> None:
        """The selection is one fact, shown in both panes."""
        finished.click("#btn-open-vision")
        finished.wait_for_selector("#artifact-view-tree-list li.is-selected")
        selected = finished.locator("#artifact-view-tree-list li.is-selected")
        assert selected.count() == 1
        assert "vision.json" in selected.inner_text()


class TestTheCompletedRunsCostStrip:
    """The other half of the phase: a finished run reports its cost in the
    same three lines the project view closes with."""

    def test_it_renders_under_the_transcript(self, finished: Page) -> None:
        strip = finished.locator("#cost-summary-card")
        assert strip.count() == 1
        transcript = finished.locator("#chat-scroll-area").bounding_box()
        box = strip.bounding_box()
        assert transcript is not None and box is not None
        assert transcript["y"] < box["y"]

    def test_it_is_three_lines_labelled_an_estimate(self, finished: Page) -> None:
        lines = [
            finished.inner_text(f"#{name}")
            for name in ("run-cost-line", "run-cost-unpriced", "run-cost-note")
        ]
        assert lines[0].startswith("Estimated cost, this run: $0.0042")
        assert lines[1] == "all 1 call priced"
        assert "your provider's billing is authoritative" in lines[2].lower()
        assert "$0.0000" not in "\n".join(lines)

    def test_it_wears_the_same_class_as_the_project_view_s(
        self, finished: Page
    ) -> None:
        """One renderer, one rule in the stylesheet — so the two strips cannot
        drift into looking like two different components."""
        assert "cost-strip" in (
            finished.get_attribute("#cost-summary-card", "class") or ""
        )
        finished.click("#status-bar-nav-project")
        finished.wait_for_selector("#round-cost")
        assert "cost-strip" in (
            finished.get_attribute("#round-cost", "class") or ""
        )

    def test_the_figures_render_in_monospace(self, finished: Page) -> None:
        font = finished.eval_on_selector(
            "#run-cost-line", "el => getComputedStyle(el).fontFamily"
        )
        assert "Mono" in font or "monospace" in font
