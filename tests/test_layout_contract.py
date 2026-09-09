"""Every layout renders, and the component ids it mounts are a checked-in contract.

Cleanup Rule 4 freezes component ids: callbacks address them by string, the
CSS selects on them, and the browser tests click them. Renaming one is a
behaviour change that no unit test of the callback itself can see. This
module makes the rule mechanical in the direction
``tests/test_callback_co_presence.py`` does not cover — that file checks that
every callback's ids are on screen together; this one checks that the set of
ids each screen mounts has not changed at all.

Two tests over one registry of screens:

* **smoke** — every public layout function returns a Dash component tree for
  a representative session, and the tree serialises the way dash-renderer
  will receive it.
* **snapshot** — the sorted string ids and pattern-matching id ``type``s per
  screen equal ``tests/snapshots/component_ids.json``.

A diff in the snapshot is a question, not a verdict. Regenerate deliberately:

    SPEC4_UPDATE_SNAPSHOTS=1 uv run pytest tests/test_layout_contract.py

and read the diff before checking it in.
"""

from __future__ import annotations

import json
import os
import pathlib
from collections.abc import Callable
from typing import Any

import pytest
from dash import html
from dash.development.base_component import Component

from spec4 import project_manager
from spec4.app_constants import STATE_VISION_COMPLETE
from spec4.layouts import (
    _agent_select_layout,
    _artifact_view_layout,
    _chat_layout,
    _setup_layout,
    _status_bar,
    _status_context,
    _working_dir_layout,
)
from spec4.layouts.designer import (
    _step1_content,
    _step2_content,
    _step3_content,
    _step4_content,
    _step5_content,
    _step6_content,
    _step7_content,
    designer_layout,
)
from spec4.session import _default_session

SNAPSHOT = pathlib.Path(__file__).resolve().parent / "snapshots" / "component_ids.json"
_UPDATE_ENV = "SPEC4_UPDATE_SNAPSHOTS"

Builder = Callable[[pathlib.Path], Any]

_CHAT_AGENTS = (
    "code_scanner",
    "brainstormer",
    "agentifier",
    "stack_advisor",
    "phaser",
    "deployer",
)

# The terminal-state keys that put every "done" control on the chat frame,
# as `tests/test_callback_co_presence.py` builds them.
_COMPLETE_KEYS: dict[str, Any] = {
    "messages": [{"role": "assistant", "content": "done"}],
    "_initial_turn_done": True,
    "vision_statement": {"app_name": "x"},
    "brainstormer_state": STATE_VISION_COMPLETE,
    "code_review": {"summary": "x"},
    "code_scanner_state": "review_complete",
    "stack_statement": {"stack": []},
    "stack_advisor_state": "stack_complete",
    "phases": [{"name": "p"}],
    "phaser_state": "phases_complete",
    "agentifier_state": "agentifier_complete",
    "deployer_state": "deployer_complete",
    "ai_features": {"ai_features": []},
}


# ---------------------------------------------------------------------------
# Session and disk fixtures
# ---------------------------------------------------------------------------


def _session(**extra: Any) -> dict[str, Any]:
    session = _default_session()
    session.update(
        {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "api_key": "k",
            "llm_config": {"model": "claude-sonnet-4-6", "api_key": "k"},
            "project_mode": "new",
        }
    )
    session.update(extra)
    return session


def _answered(session: dict[str, Any], *agents: str) -> dict[str, Any]:
    return {
        **session,
        "agent_llm_asked": {
            **(session.get("agent_llm_asked") or {}),
            **{a: True for a in agents},
        },
    }


def _project(tmp_path: pathlib.Path, **extra: Any) -> dict[str, Any]:
    return _session(working_dir=str(tmp_path), **extra)


def _round_on_disk(tmp_path: pathlib.Path) -> None:
    """A brownfield project: one implemented round with a vision and a mock."""
    version_dir = project_manager.ensure_version_dir(tmp_path, 1)
    (version_dir / "vision.json").write_text(json.dumps({"vision_statement": {}}))
    (version_dir / "code_review.json").write_text("{}")
    (version_dir / "design").mkdir(exist_ok=True)
    (version_dir / "design" / "mock.html").write_text("<html></html>")
    (version_dir / "IMPLEMENTED").write_text("")
    (tmp_path / "existing.py").write_text("print('hi')\n")


# ---------------------------------------------------------------------------
# The screens
# ---------------------------------------------------------------------------


def _chat_screens() -> list[tuple[str, Builder]]:
    screens: list[tuple[str, Builder]] = []
    for agent in _CHAT_AGENTS:

        def gate(p: pathlib.Path, agent: str = agent) -> Any:
            return _chat_layout(_project(p, phase="chat", active_agent=agent), {})

        def opening(p: pathlib.Path, agent: str = agent) -> Any:
            return _chat_layout(
                _answered(_project(p, phase="chat", active_agent=agent), agent), {}
            )

        def streaming(p: pathlib.Path, agent: str = agent) -> Any:
            s = _answered(_project(p, phase="chat", active_agent=agent), agent)
            s.update(
                messages=[{"role": "assistant", "content": "…"}],
                _stream_id="live",
                _initial_turn_done=True,
            )
            return _chat_layout(s, {})

        def complete(p: pathlib.Path, agent: str = agent) -> Any:
            s = _answered(_project(p, phase="chat", active_agent=agent), agent)
            s.update(_COMPLETE_KEYS)
            return _chat_layout(s, {})

        def retry(p: pathlib.Path, agent: str = agent) -> Any:
            s = _answered(_project(p, phase="chat", active_agent=agent), agent)
            s.update(
                _stream_error=True,
                _initial_turn_done=True,
                messages=[{"role": "assistant", "content": "boom"}],
            )
            return _chat_layout(s, {})

        screens.extend(
            [
                (f"chat {agent}: gate", gate),
                (f"chat {agent}: opening", opening),
                (f"chat {agent}: streaming", streaming),
                (f"chat {agent}: complete", complete),
                (f"chat {agent}: retry panel", retry),
            ]
        )

    def breadth(p: pathlib.Path) -> Any:
        s = _answered(
            _project(p, phase="chat", active_agent="agentifier"), "agentifier"
        )
        s.update(
            _initial_turn_done=True,
            agentifier_breadth_groups=[{"name": "g", "description": "d"}],
            agentifier_breadth_intro="pick some",
        )
        return _chat_layout(s, {})

    screens.append(("chat agentifier: breadth panel", breadth))
    return screens


def _designer_screens() -> list[tuple[str, Builder]]:
    store = {
        "step": 6,
        "preference_text": "",
        "screenshots": [{"data": "data:image/png;base64,x", "annotation": ""}],
        "refine_images": [{"filename": "b.png", "data": "data:image/png;base64,x"}],
        "mock_html": "<html></html>",
        "finalized": False,
        "_has_existing_ui": True,
        "_is_revision": False,
    }
    buffer = {"tokens": 0, "progress": 0, "error": None}
    steps: list[tuple[str, Callable[[], Any]]] = [
        ("1", lambda: _step1_content()),
        ("2", lambda: _step2_content(True, False)),
        ("2 (no existing ui)", lambda: _step2_content(False, False)),
        ("2 (revision)", lambda: _step2_content(True, True)),
        ("3", lambda: _step3_content()),
        ("4", lambda: _step4_content(store, True)),
        ("4 (no image support)", lambda: _step4_content(store, False)),
        ("5", lambda: _step5_content(buffer)),
        ("5 (error)", lambda: _step5_content({**buffer, "error": "boom"})),
        ("6", lambda: _step6_content(store)),
        ("6 (finalized)", lambda: _step6_content({**store, "finalized": True})),
        (
            "6 (stale)",
            lambda: _step6_content({**store, "_stale_inputs": ["vision.json"]}),
        ),
        ("7", lambda: _step7_content(store, True)),
        ("7 (no image support)", lambda: _step7_content(store, False)),
    ]
    screens: list[tuple[str, Builder]] = [
        (
            "designer: gate",
            lambda p: designer_layout(_project(p, phase="designer"), {}),
        ),
        (
            "designer: wizard",
            lambda p: designer_layout(
                _answered(_project(p, phase="designer"), "designer"), {}
            ),
        ),
        (
            "designer: wizard, brownfield",
            lambda p: (
                _round_on_disk(p),
                designer_layout(
                    _answered(_project(p, phase="designer"), "designer"), {}
                ),
            )[1],
        ),
        (
            "designer: wizard, no project",
            lambda p: designer_layout(
                _answered(_session(phase="designer"), "designer"), {}
            ),
        ),
    ]
    for name, build in steps:
        screens.append((f"designer: step {name}", lambda p, b=build: b()))
    return screens


def _artifact_screens() -> list[tuple[str, Builder]]:
    def with_round(p: pathlib.Path, **extra: Any) -> Any:
        _round_on_disk(p)
        return _artifact_view_layout(_project(p, phase="artifacts", **extra))

    return [
        (
            "artifacts: no project",
            lambda p: _artifact_view_layout(_session(phase="artifacts")),
        ),
        (
            "artifacts: project, no rounds",
            lambda p: _artifact_view_layout(_project(p, phase="artifacts")),
        ),
        ("artifacts: round, nothing selected", lambda p: with_round(p)),
        (
            "artifacts: file selected",
            lambda p: with_round(p, selected_round=1, selected_file="vision.json"),
        ),
        (
            "artifacts: mock selected",
            lambda p: with_round(p, selected_round=1, selected_file="design/mock.html"),
        ),
        (
            "artifacts: missing file selected",
            lambda p: with_round(p, selected_round=1, selected_file="stack.json"),
        ),
        (
            "artifacts: rejected path",
            lambda p: with_round(p, selected_round=1, selected_file="../secret"),
        ),
    ]


def _setup_screens() -> list[tuple[str, Builder]]:
    base: dict[str, Any] = {"phase": "setup"}
    return [
        (
            "setup: provider",
            lambda p: _setup_layout(
                _project(p, **base, available_models=None, model=None), {}
            ),
        ),
        (
            "setup: provider, with error",
            lambda p: _setup_layout(
                _project(
                    p, **base, available_models=None, model=None, setup_error="bad"
                ),
                {},
            ),
        ),
        (
            "setup: model",
            lambda p: _setup_layout(
                _project(p, **base, available_models=["a", "b"], model=None), {}
            ),
        ),
        (
            "setup: web search",
            lambda p: _setup_layout(
                _project(p, **base, available_models=["a", "b"]), {}
            ),
        ),
        (
            "setup: web search, probes answered",
            lambda p: _setup_layout(
                _project(p, **base, available_models=["a", "b"]), {}, True, False
            ),
        ),
    ]


def _project_view_screens() -> list[tuple[str, Builder]]:
    def brownfield(p: pathlib.Path, **extra: Any) -> Any:
        _round_on_disk(p)
        return _agent_select_layout(
            _project(
                p,
                phase="agent_select",
                project_mode="existing",
                vision_statement={"vision_statement": {}},
                stack_statement={"stack": []},
                phases=[{"name": "p"}],
                **extra,
            )
        )

    return [
        (
            "project_mode question",
            lambda p: (
                (p / "existing.py").write_text("print('hi')\n"),
                _agent_select_layout(
                    _project(p, phase="agent_select", project_mode=None)
                ),
            )[1],
        ),
        (
            "project view: greenfield",
            lambda p: _agent_select_layout(_project(p, phase="agent_select")),
        ),
        (
            "project view: greenfield, with error",
            lambda p: _agent_select_layout(
                _project(p, phase="agent_select", agent_select_error="nope")
            ),
        ),
        ("project view: brownfield", lambda p: brownfield(p)),
        (
            "project view: brownfield, pinned round",
            lambda p: brownfield(p, phase_version=1),
        ),
    ]


SCREENS: list[tuple[str, Builder]] = [
    ("working_dir", lambda p: _working_dir_layout(_session(phase="working_dir"))),
    (
        "working_dir: unopenable remembered directory",
        lambda p: _working_dir_layout(
            _session(
                phase="working_dir",
                dir_error="Could not open /gone. Select a project directory.",
            )
        ),
    ),
    (
        "working_dir: browsing a directory",
        lambda p: (
            (p / "sub").mkdir(),
            _working_dir_layout(_session(phase="working_dir", browser_path=str(p))),
        )[1],
    ),
    *_setup_screens(),
    *_project_view_screens(),
    *_chat_screens(),
    *_designer_screens(),
    *_artifact_screens(),
    ("status bar", lambda p: _status_bar()),
    (
        "status bar: context filled",
        lambda p: html.Span(_status_context(str(p), 2, "anthropic", "m", True)),
    ),
    (
        "status bar: context empty",
        lambda p: html.Span(_status_context(None, None, None, None, False)),
    ),
]

_LABELS = [label for label, _ in SCREENS]
assert len(_LABELS) == len(set(_LABELS)), "screen labels must be unique"


# ---------------------------------------------------------------------------
# Walking a rendered tree
# ---------------------------------------------------------------------------


def _walk(component: Any) -> tuple[set[str], set[str]]:
    """(string ids, pattern-matching id types) of every component in a tree."""
    ids: set[str] = set()
    types: set[str] = set()
    stack = [component]
    while stack:
        node = stack.pop()
        if isinstance(node, (list, tuple)):
            stack.extend(node)
            continue
        node_id = getattr(node, "id", None)
        if isinstance(node_id, str):
            ids.add(node_id)
        elif isinstance(node_id, dict) and isinstance(node_id.get("type"), str):
            types.add(node_id["type"])
        children = getattr(node, "children", None)
        if children is not None:
            stack.append(children)
    return ids, types


def _is_component_tree(node: Any) -> bool:
    if isinstance(node, Component):
        return True
    if isinstance(node, (list, tuple)):
        return all(_is_component_tree(n) or isinstance(n, str) for n in node)
    return False


def _serialisable(node: Any) -> None:
    """dash-renderer receives ``to_plotly_json`` of every node; it must not raise."""
    if isinstance(node, (list, tuple)):
        for n in node:
            _serialisable(n)
        return
    if isinstance(node, Component):
        json.dumps(node.to_plotly_json(), default=_json_default)


def _json_default(value: Any) -> Any:
    if isinstance(value, Component):
        return value.to_plotly_json()
    raise TypeError(f"unserialisable {type(value).__name__} in a layout")


# ---------------------------------------------------------------------------
# The tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "build"), SCREENS, ids=_LABELS)
def test_every_layout_renders_a_serialisable_component_tree(
    label: str, build: Builder, tmp_path: pathlib.Path
) -> None:
    tree = build(tmp_path)
    assert _is_component_tree(tree), f"{label}: {type(tree).__name__}"
    _serialisable(tree)


def _snapshot(tmp_path: pathlib.Path) -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = {}
    for index, (label, build) in enumerate(SCREENS):
        screen_dir = tmp_path / f"screen{index}"
        screen_dir.mkdir()
        ids, types = _walk(build(screen_dir))
        out[label] = {"ids": sorted(ids), "pattern_types": sorted(types)}
    return out


def test_component_ids_match_the_checked_in_snapshot(tmp_path: pathlib.Path) -> None:
    actual = _snapshot(tmp_path)
    if os.environ.get(_UPDATE_ENV, "") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")
        return
    assert SNAPSHOT.exists(), f"missing {SNAPSHOT}; run with {_UPDATE_ENV}=1"
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    problems: list[str] = []
    for label in sorted(set(actual) | set(expected)):
        if label not in expected:
            problems.append(f"{label}: screen not in snapshot")
            continue
        if label not in actual:
            problems.append(f"{label}: screen in snapshot but no longer rendered")
            continue
        for key in ("ids", "pattern_types"):
            got = set(actual[label][key])
            want = set(expected[label][key])
            if got != want:
                problems.append(
                    f"{label} [{key}]: added {sorted(got - want)}, "
                    f"removed {sorted(want - got)}"
                )
    assert not problems, (
        "component ids changed (set "
        f"{_UPDATE_ENV}=1 to regenerate after review):\n" + "\n".join(problems)
    )


def test_every_screen_mounts_at_least_one_id() -> None:
    """A screen with no ids at all is a registry mistake, not a layout."""
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert [label for label, entry in expected.items() if not entry["ids"]] == []
