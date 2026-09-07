"""The chat frame's transcript, counters and progress signal, after the restyle.

The load-bearing claim in this file is the first one. ``chat-bubble-user``
looks like a CSS class describing a fill that no longer exists, and it is
actually the selector the auto-scroll clientside callback in ``app.py`` uses to
find the last user turn. Renaming it — the obvious tidy-up once the bubble is
gone — breaks transcript auto-scroll silently: no exception, no console error,
the transcript simply stops following new messages. So the name is pinned here,
against the JavaScript that reads it, rather than left to a comment.

The rest of the file pins what the restyle put in its place: a dimmed one-word
speaker label above each block, no fill on either speaker's turn, a neutral
left rule on the user's, a viewport-relative transcript height set in the
stylesheet where the window can answer it, monospace counters carrying no
colour of their own, and a progress bar that is the only thing on the screen
that moves.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

from spec4.layouts._chat import _chat_layout
from spec4.layouts._llm_gate import model_chip
from spec4.layouts._shared import _render_message

_SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "spec4"
_STYLESHEET = _SRC / "assets" / "v3.css"
_APP = _SRC / "app.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _walk(node: Any) -> list[Any]:
    found = [node]
    children = getattr(node, "children", None)
    if children is None:
        return found
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if isinstance(child, str):
            found.append(child)
        else:
            found.extend(_walk(child))
    return found


def _classes(node: Any) -> set[str]:
    return set((getattr(node, "className", "") or "").split())


def _find_class(root: Any, name: str) -> list[Any]:
    return [n for n in _walk(root) if name in _classes(n)]


def _find_id(root: Any, node_id: str) -> Any | None:
    return next((n for n in _walk(root) if getattr(n, "id", None) == node_id), None)


def _stylesheet() -> str:
    """The stylesheet with its comments removed.

    The prose in this file has commas and colons in it, and a selector split
    on commas would otherwise match half a sentence.
    """
    return re.sub(r"/\*.*?\*/", "", _STYLESHEET.read_text(encoding="utf-8"), flags=re.S)


def _rules(selector: str) -> list[str]:
    """Every rule whose selector list names `selector`, as its declarations."""
    return [
        block.group(2)
        for block in re.finditer(r"([^{}]+)\{([^}]*)\}", _stylesheet())
        if selector in [s.strip() for s in block.group(1).split(",")]
    ]


def _rule(selector: str) -> str:
    """Everything the stylesheet declares for `selector`, in one string."""
    found = _rules(selector)
    assert found, f"no rule for {selector!r} in v3.css"
    return "\n".join(found)


def _session(**extra: Any) -> dict[str, Any]:
    return {
        "active_agent": "brainstormer",
        "working_dir": "",
        "vision_statement": None,
        "llm_config": {"model": "claude-sonnet-5", "api_key": "k"},
        "agent_llm_asked": {"brainstormer": True},
        "messages": [
            {"role": "user", "content": "A local-first planning pipeline."},
            {"role": "assistant", "content": "Tell me who it is for."},
        ],
        **extra,
    }


# ---------------------------------------------------------------------------
# The selector contract
# ---------------------------------------------------------------------------


class TestTheUserBlockKeepsItsClassName:
    """`chat-bubble-user` is JavaScript, not CSS. It does not get renamed."""

    def test_the_user_block_carries_it(self) -> None:
        block = _render_message({"role": "user", "content": "hi"})
        assert "chat-bubble-user" in _classes(_find_class(block, "chat-bubble-user")[0])

    def test_the_assistant_block_does_not(self) -> None:
        """The selector has to pick out the user's turns and only those."""
        block = _render_message({"role": "assistant", "content": "hi"}, "Brainstormer")
        assert _find_class(block, "chat-bubble-user") == []

    def test_the_class_is_on_a_child_of_the_wrapper_not_the_wrapper(self) -> None:
        """The scroll callback scrolls the matched element's *parent* to the
        top of the viewport. Hoisting the class onto the wrapper would make
        that parent the whole message column, and every scroll would land at
        the top of the transcript instead of on the last turn."""
        block = _render_message({"role": "user", "content": "hi"})
        assert "chat-bubble-user" not in _classes(block)
        assert len(_find_class(block, "chat-bubble-user")) == 1

    def test_the_rendered_transcript_still_matches_it(self) -> None:
        layout = _chat_layout(_session())
        area = _find_id(layout, "chat-scroll-area")
        assert area is not None
        assert len(_find_class(area, "chat-bubble-user")) == 1

    def test_the_scroll_callback_is_the_thing_that_reads_it(self) -> None:
        """The other half of the contract, quoted from where it lives."""
        app = _APP.read_text(encoding="utf-8")
        assert "querySelectorAll('.chat-bubble-user')" in app
        assert "getElementById('chat-scroll-area')" in app


# ---------------------------------------------------------------------------
# Blocks rather than bubbles
# ---------------------------------------------------------------------------


class TestBlocks:
    def test_each_message_carries_a_one_word_speaker_label(self) -> None:
        user = _render_message({"role": "user", "content": "hi"}, "Brainstormer")
        agent = _render_message({"role": "assistant", "content": "hi"}, "Brainstormer")
        assert _find_class(user, "msg-label")[0].children == "You"
        assert _find_class(agent, "msg-label")[0].children == "Brainstormer"

    def test_the_assistant_label_names_the_active_agent(self) -> None:
        layout = _chat_layout(_session(active_agent="stack_advisor"))
        labels = [n.children for n in _find_class(layout, "msg-label")]
        assert labels == ["You", "StackAdvisor"]

    def test_the_label_is_dimmed_and_small(self) -> None:
        rule = _rule(".msg-label")
        assert "color: #a0a0b0" in rule
        assert "font-size: 11px" in rule

    def test_neither_block_is_filled(self) -> None:
        rule = _rule(".chat-msg.chat-bubble-user")
        assert "background: none !important" in rule
        assert "border: 0" in rule

    def test_the_user_block_has_a_neutral_left_rule(self) -> None:
        """Neutral, not the accent: it marks a turn, it does not emphasise it."""
        rule = _rule(".chat-msg.chat-bubble-user")
        assert "border-left: 2px solid #3a3a4a" in rule

    def test_the_blocks_are_not_paper_panels(self) -> None:
        """A `dmc.Paper` brings a surface and a radius back with it."""
        block = _render_message({"role": "user", "content": "hi"})
        assert "Paper" not in {type(n).__name__ for n in _walk(block)}


# ---------------------------------------------------------------------------
# Height and scrolling
# ---------------------------------------------------------------------------


class TestTheTranscriptHeight:
    def test_the_height_is_viewport_relative_and_set_in_css(self) -> None:
        rule = _rule("#chat-scroll-area")
        assert "height: 60vh" in rule
        assert "overflow-y: auto" in rule

    def test_the_layout_sets_no_height_of_its_own(self) -> None:
        """An inline height would win over the stylesheet, which is the whole
        point of moving it: 60vh answers to the window, 450px did not."""
        area = _find_id(_chat_layout(_session()), "chat-scroll-area")
        assert area is not None
        assert "height" not in (area.style or {})
        assert "overflowY" not in (area.style or {})

    def test_it_still_has_a_floor_for_a_short_window(self) -> None:
        assert "min-height: 200px" in _rule("#chat-scroll-area")


# ---------------------------------------------------------------------------
# Monospace counters and model chip
# ---------------------------------------------------------------------------


class TestMonospaceFigures:
    def _row(self) -> Any:
        return _chat_layout(
            _session(
                _stream_id=None,
                _stream_received_chars=8291,
                _turn_usage={
                    "agent": "brainstormer",
                    "calls": 2,
                    "missing": 0,
                    "input": 4180,
                    "output": 312,
                },
            )
        )

    def test_the_three_counters_are_monospace(self) -> None:
        layout = self._row()
        for node_id in ("chat-token-count", "chat-turn-tokens", "chat-elapsed"):
            node = _find_id(layout, node_id)
            assert node is not None, node_id
            assert node.className == "mono", node_id

    def test_none_of_them_carries_a_colour(self) -> None:
        """D-LR2: the dimming is a stylesheet rule keyed on the three ids."""
        layout = self._row()
        for node_id in ("chat-token-count", "chat-turn-tokens", "chat-elapsed"):
            node = _find_id(layout, node_id)
            assert getattr(node, "c", None) is None, node_id
        rule = _rule("#chat-elapsed")
        assert "color: #a0a0b0" in rule

    def test_the_model_chip_s_model_name_is_monospace(self) -> None:
        """The name is an identifier; the words around it are prose."""
        chip = model_chip(_session(), "brainstormer")
        mono = [n for n in _walk(chip) if _classes(n) == {"mono"}]
        assert len(mono) == 1
        assert mono[0].children == "claude-sonnet-5"

    def test_the_mono_class_is_the_one_the_stylesheet_already_had(self) -> None:
        assert "'JetBrains Mono'" in _rule(".mono")


# ---------------------------------------------------------------------------
# The one moving thing
# ---------------------------------------------------------------------------


class TestTheProgressSignal:
    def _bar(self) -> Any:
        layout = _chat_layout(_session(_stream_id="live"))
        container = _find_id(layout, "chat-progress-container")
        assert container is not None
        return next(n for n in _walk(container) if type(n).__name__ == "Progress")

    def test_it_is_thin_striped_and_animated(self) -> None:
        bar = self._bar()
        assert bar.size == "xs"
        assert bar.striped is True
        assert bar.animated is True

    def test_it_keeps_the_readable_stripe(self) -> None:
        assert self._bar().classNames == {"section": "progress-stripe"}

    def test_it_is_the_only_animation_in_the_chat_frame_s_rules(self) -> None:
        """No transition, no keyframe, no hover motion anywhere the chat frame
        reaches — the stripe is the live-activity signal, and a second moving
        thing would compete with it for the meaning "still running"."""
        css = _stylesheet()
        selectors = (
            "#chat-scroll-area",
            ".chat-msg",
            ".msg-label",
            ".msg-row",
            ".pipeline",
            ".pipeline-agent",
            "#btn-chat-submit",
            "#btn-agent-llm-chip",
            "#chat-token-count",
        )
        offenders = []
        for block in re.finditer(r"([^{}]+)\{([^}]*)\}", css):
            head, body = block.group(1), block.group(2)
            if not any(sel in head for sel in selectors):
                continue
            if re.search(r"\b(transition|animation|transform)\s*:", body):
                offenders.append(head.strip())
        assert not offenders, f"animated chat-frame rules: {offenders}"

    def test_there_are_no_keyframes_at_all(self) -> None:
        """The stripe's motion is Mantine's own; the app declares none."""
        assert "@keyframes" not in _STYLESHEET.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Nothing lost in the restyle
# ---------------------------------------------------------------------------


class TestEveryFunctionIsStillReachable:
    """The success criterion the phase asks be verified by inspection, as a
    list of the component ids each function is reached through. A restyle that
    dropped one of these would still render, which is why it is asserted."""

    def test_the_completed_run_s_controls_are_all_present(
        self, tmp_path: pathlib.Path
    ) -> None:
        session = _session(
            vision_statement={"purpose": "x"},
            brainstormer_state="vision_complete",
            _stream_id=None,
        )
        ids = [getattr(n, "id", None) for n in _walk(_chat_layout(session))]
        for expected in (
            "chat-scroll-area",
            "chat-token-count",
            "chat-elapsed",
            "chat-progress-container",
            "chat-input",
            "btn-chat-submit",
            "btn-agent-llm-chip",
            "chat-status-line",
            "btn-dl-vision",
            "btn-brainstormer-to-agentifier",
        ):
            assert expected in ids, expected

    def test_the_fast_forward_controls_survive(self) -> None:
        session = _session(
            active_agent="phaser",
            vision_statement={"purpose": "x"},
            stack_statement={"stack": []},
            agent_llm_asked={"phaser": True},
        )
        ids = [getattr(n, "id", None) for n in _walk(_chat_layout(session))]
        assert "btn-chat-fast-forward" in ids
        assert "btn-ff-info" in ids
        assert "ff-info-modal" in ids

    def test_the_retry_panel_survives(self) -> None:
        session = _session(
            _stream_error="overloaded",
            messages=[{"role": "assistant", "content": "half a"}],
        )
        ids = [getattr(n, "id", None) for n in _walk(_chat_layout(session))]
        assert "btn-chat-retry" in ids
        assert "btn-chat-retry-model" in ids
