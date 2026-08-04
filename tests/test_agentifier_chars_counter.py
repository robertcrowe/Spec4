"""D-AT1/D-AT2/D-AT3/D-AT4: the Agentifier chars counter.

Most of Agentifier's post-panel time yields visible text, so the counter's
displayed-character fallback already serves it. The gap is the suppressed
artifact turn, where `_stream_suppressing_json` swallows the whole response and
the visible message never grows — the same D-SC60 case already fixed for
StackAdvisor. Two wrinkles come with closing it: the layout renders no button
bar during the first post-panel turn, and seeding the published total at zero
would make the counter drop mid-turn.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import dash_mantine_components as dmc

from spec4.agents._utils import _stream_suppressing_json
from spec4.app_constants import STATE_AGENTIFIER_COMPLETE
from spec4.layouts._chat import (
    _TOKEN_COUNTER_AGENTS,
    _chat_action_buttons,
    _token_count_text,
)


def _chunks(*parts: str) -> Generator[str, None, None]:
    yield from parts


def _counter_texts(rendered: Any) -> list[str]:
    """Collect the text of every counter component in a rendered button bar."""
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, list | tuple):
            for item in node:
                walk(item)
            return
        children = getattr(node, "children", None)
        if getattr(node, "id", None) == "chat-token-count":
            found.append(children if isinstance(children, str) else "")
        if children is not None:
            walk(children)

    walk(rendered)
    return found


def _agentifier_session(**overrides: Any) -> dict[str, Any]:
    session: dict[str, Any] = {
        "active_agent": "agentifier",
        "messages": [{"role": "assistant", "content": "x" * 120}],
    }
    session.update(overrides)
    return session


# ---------------------------------------------------------------------------
# D-AT4 — the label
# ---------------------------------------------------------------------------


class TestLabel:
    def test_reads_chars_not_tokens(self) -> None:
        session = _agentifier_session(_stream_id="abc", _stream_received_chars=4200)
        assert _token_count_text(session) == "Chars received: 4200"

    def test_no_agent_still_reports_tokens(self) -> None:
        for agent in _TOKEN_COUNTER_AGENTS:
            session = {
                "active_agent": agent,
                "_stream_id": "abc",
                "messages": [{"role": "assistant", "content": ""}],
                "_stream_received_chars": 7,
            }
            assert _token_count_text(session).startswith("Chars received:")


# ---------------------------------------------------------------------------
# D-AT3 — the counter must not dip when the stream opens
# ---------------------------------------------------------------------------


class TestSeed:
    def test_seed_is_published_before_the_first_chunk(self) -> None:
        session: dict[str, Any] = {}
        seen: list[int] = []

        def watched() -> Generator[str, None, None]:
            for part in ("```", "abcd"):
                seen.append(session.get("_stream_received_chars", -1))
                yield part

        list(_stream_suppressing_json(watched(), session, seed=300))
        assert seen == [300, 303]
        assert session["_stream_received_chars"] == 307

    def test_counter_never_drops_across_the_handover(self) -> None:
        """The defect: progress text raises the fallback count, then the stream
        opens and the published total resets it to zero."""
        displayed = "\n\nContinuing with **3 selected features**…\n\n"
        session: dict[str, Any] = {
            "messages": [{"role": "assistant", "content": displayed}]
        }
        before = len(displayed)

        list(_stream_suppressing_json(_chunks("```json\n", "{}"), session, seed=before))

        assert session["_stream_received_chars"] >= before

    def test_unseeded_behaviour_is_unchanged(self) -> None:
        session: dict[str, Any] = {"_stream_received_chars": 99999}
        assert list(_stream_suppressing_json(_chunks(), session)) == []
        assert session["_stream_received_chars"] == 0

    def test_seed_does_not_leak_without_a_session(self) -> None:
        out = list(_stream_suppressing_json(_chunks("Hi"), None, seed=500))
        assert "".join(out) == "Hi"


# ---------------------------------------------------------------------------
# D-AT2 / D-AT5 — where the counter renders
# ---------------------------------------------------------------------------


class TestLayoutGate:
    def test_pre_panel_build_stays_bare(self) -> None:
        """D-AT5: no counter before the panel. The pre-panel build has a live
        stream but has not yet populated breadth_groups."""
        session = _agentifier_session(_stream_id="abc")
        assert _counter_texts(_chat_action_buttons(session)) == []

    def test_first_post_panel_turn_shows_the_counter(self) -> None:
        """D-AT2: breadth_chosen is set by the generator but does not reach the
        layout mid-stream, so groups + a live stream is the usable signal."""
        session = _agentifier_session(
            _stream_id="abc",
            agentifier_breadth_groups=[{"name": "a"}],
            _stream_received_chars=5150,
        )
        assert _counter_texts(_chat_action_buttons(session)) == ["Chars received: 5150"]

    def test_first_post_panel_turn_does_not_gain_fast_forward(self) -> None:
        """The FF gate is unchanged: it still requires breadth_chosen or
        catalog_done, so the counter-only branch must carry no FF button."""
        session = _agentifier_session(
            _stream_id="abc",
            agentifier_breadth_groups=[{"name": "a"}],
        )
        rendered = _chat_action_buttons(session)
        ids = _component_ids(rendered)
        assert "chat-token-count" in ids
        assert not any(isinstance(i, str) and "ff" in i.lower() for i in ids)

    def test_later_turns_show_counter_alongside_fast_forward(self) -> None:
        session = _agentifier_session(
            agentifier_breadth_chosen=True,
            _stream_id="abc",
            _stream_received_chars=88,
        )
        assert _counter_texts(_chat_action_buttons(session)) == ["Chars received: 88"]

    def test_complete_state_shows_the_counter(self) -> None:
        session = _agentifier_session(
            agentifier_state=STATE_AGENTIFIER_COMPLETE,
            agentifier_breadth_chosen=True,
        )
        assert _counter_texts(_chat_action_buttons(session)) == ["Chars received: 120"]

    def test_exactly_one_counter_per_bar(self) -> None:
        """Duplicate ids in one layout are a Dash error, not a cosmetic issue."""
        for overrides in (
            {"_stream_id": "abc", "agentifier_breadth_groups": [{"name": "a"}]},
            {"agentifier_breadth_chosen": True},
            {"agentifier_state": STATE_AGENTIFIER_COMPLETE},
        ):
            session = _agentifier_session(**overrides)
            assert len(_counter_texts(_chat_action_buttons(session))) == 1


def _component_ids(node: Any, acc: list[Any] | None = None) -> list[Any]:
    acc = [] if acc is None else acc
    if isinstance(node, list | tuple):
        for item in node:
            _component_ids(item, acc)
        return acc
    node_id = getattr(node, "id", None)
    if node_id is not None:
        acc.append(node_id)
    children = getattr(node, "children", None)
    if children is not None and not isinstance(children, str):
        _component_ids(children, acc)
    return acc


def test_counter_component_is_a_text_node() -> None:
    """Guards the walker above against silently matching nothing."""
    session = _agentifier_session(
        agentifier_breadth_chosen=True, _stream_received_chars=3
    )
    rendered = _chat_action_buttons(session)

    def find(node: Any) -> Any:
        if isinstance(node, list | tuple):
            for item in node:
                hit = find(item)
                if hit is not None:
                    return hit
            return None
        if getattr(node, "id", None) == "chat-token-count":
            return node
        children = getattr(node, "children", None)
        return find(children) if children is not None else None

    assert isinstance(find(rendered), dmc.Text)
