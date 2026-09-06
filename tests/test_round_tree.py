"""The round tree tells the truth about the round's folder, every time.

Three things can go wrong here and each has its own class below. The lane
table can misfile an artifact — so the lanes are asserted against the reviewed
table rather than against whatever the code happens to produce. The line list
can drift from the pipeline — so the order is checked against ``AGENT_KEYS``,
the pipeline's one definition. And status can lie: a file can be missing, a
file can be stale, and ``usage.json`` must never read as stale no matter what
else has moved, because it is written by every agent and read by none.

The status cases build their fixtures by writing real files and setting real
mtimes, because that is what ``detect_stale_inputs`` reads. Nothing here mocks
the dependency graph — the point is that the tree agrees with it.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any

import pytest

from spec4 import project_manager
from spec4.app_constants import AGENT_KEYS
from spec4.callbacks import on_round_tree
from spec4.layouts import _agent_select_layout, _round_tree, round_tree_lines
from spec4.layouts._round_tree import (
    ARTIFACT_LANES,
    LANE_PROMPT,
    LANE_RECORD,
    LANE_REF,
    LANES,
    ROUND_ARTIFACTS,
    STATUS_MISSING,
    STATUS_NEEDS_UPDATE,
    STATUS_PRESENT,
    _ARTIFACTS_BY_AGENT,
)
from spec4.session import _default_session

# The whole round, oldest first. Writing them in this order and then bumping
# one file's mtime is how a "the upstream moved" fixture is built.
_ALL_ARTIFACTS = tuple(a.path for a in ROUND_ARTIFACTS)


def _write(base: pathlib.Path, rel: str, mtime: float) -> pathlib.Path:
    """Write an artifact at `rel` with an exact mtime.

    A trailing slash means a directory, and a directory artifact is only real
    when it holds a file — so ``phases/`` gets one.
    """
    if rel.endswith("/"):
        path = base / rel.rstrip("/")
        path.mkdir(parents=True, exist_ok=True)
        member = path / "phase1.md"
        member.write_text("# phase 1\n")
        os.utime(member, (mtime, mtime))
    else:
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def round_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """A working directory with a complete, internally consistent round 0.

    Every artifact exists and every one is older than the files downstream of
    it, so nothing is stale until a test deliberately moves something.
    """
    base = project_manager.ensure_version_dir(tmp_path, 0)
    for index, rel in enumerate(_ALL_ARTIFACTS):
        _write(base, rel, 1_000_000 + index)
    return tmp_path


def _by_path(lines: list[Any]) -> dict[str, Any]:
    return {line.path: line for line in lines}


# ---------------------------------------------------------------------------
# The reviewed table
# ---------------------------------------------------------------------------


class TestTheLaneTable:
    def test_every_artifact_appears_exactly_once(
        self, round_dir: pathlib.Path
    ) -> None:
        paths = [line.path for line in round_tree_lines(round_dir, 0)]
        assert sorted(paths) == sorted(_ALL_ARTIFACTS)
        assert len(paths) == len(set(paths))

    def test_the_table_covers_every_pipeline_agent(self) -> None:
        """A new agent has to declare what it writes, or fail here.

        The table is keyed by agent precisely so that adding a pipeline stage
        cannot silently leave its output off the tree.
        """
        assert set(_ARTIFACTS_BY_AGENT) == set(AGENT_KEYS)

    def test_every_line_carries_one_of_the_three_lanes(
        self, round_dir: pathlib.Path
    ) -> None:
        assert LANES == (LANE_PROMPT, LANE_REF, LANE_RECORD)
        assert all(line.lane in LANES for line in round_tree_lines(round_dir, 0))

    def test_every_line_matches_the_reviewed_mapping(
        self, round_dir: pathlib.Path
    ) -> None:
        """Lanes come from the table, never from the filename.

        The assertion is against the declared mapping rather than a
        recomputation, so an inference path added later — extension, parent
        directory — would have to disagree with the table to pass.
        """
        for line in round_tree_lines(round_dir, 0):
            assert line.lane == ARTIFACT_LANES[line.path]

    def test_the_two_files_a_pattern_would_misfile(self) -> None:
        """`design/mock.html` and `deployment-plan.md` are the named failure.

        One is an HTML file inside a `design/` folder that is nonetheless
        reference material for an agent; the other is a markdown file that is
        not a prompt at all. Any lane rule based on extension or directory gets
        both of these wrong.
        """
        assert ARTIFACT_LANES["design/mock.html"] == LANE_REF
        assert ARTIFACT_LANES["deployment-plan.md"] == LANE_RECORD

    def test_the_phases_folder_is_the_prompt_lane(self) -> None:
        assert ARTIFACT_LANES["phases/"] == LANE_PROMPT

    def test_usage_is_a_record_for_you(self) -> None:
        assert ARTIFACT_LANES["usage.json"] == LANE_RECORD


# ---------------------------------------------------------------------------
# Pipeline order
# ---------------------------------------------------------------------------


class TestPipelineOrder:
    def test_the_lines_follow_agent_keys(self, round_dir: pathlib.Path) -> None:
        """Order is derived from ``AGENT_KEYS``, so the two cannot drift.

        Rebuilt here from the pipeline definition rather than hand-listed: a
        reordered pipeline must reorder the tree, and this test must not need
        editing when it does.
        """
        expected = [
            artifact.path
            for agent in AGENT_KEYS
            for artifact in _ARTIFACTS_BY_AGENT[agent]
        ]
        expected.append("usage.json")
        assert [line.path for line in round_tree_lines(round_dir, 0)] == expected

    def test_the_first_line_is_the_first_agents_output(
        self, round_dir: pathlib.Path
    ) -> None:
        assert round_tree_lines(round_dir, 0)[0].path == "code_review.json"

    def test_the_record_of_the_round_comes_last(
        self, round_dir: pathlib.Path
    ) -> None:
        assert round_tree_lines(round_dir, 0)[-1].path == "usage.json"


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_a_complete_consistent_round_is_all_present(
        self, round_dir: pathlib.Path
    ) -> None:
        lines = round_tree_lines(round_dir, 0)
        assert {line.status for line in lines} == {STATUS_PRESENT}

    def test_an_absent_file_is_missing_not_omitted(
        self, round_dir: pathlib.Path
    ) -> None:
        """The line stays; only its status changes.

        Dropping the line would hide the fact that the artifact is expected at
        all, which is the whole reason a developer looks at this list.
        """
        (project_manager.get_version_dir(round_dir, 0) / "stack.json").unlink()
        lines = round_tree_lines(round_dir, 0)
        assert len(lines) == len(_ALL_ARTIFACTS)
        assert _by_path(lines)["stack.json"].status == STATUS_MISSING

    def test_an_empty_directory_is_not_a_produced_artifact(
        self, round_dir: pathlib.Path
    ) -> None:
        """`phases/` can exist before Phaser has written into it."""
        base = project_manager.get_version_dir(round_dir, 0)
        for child in (base / "phases").iterdir():
            child.unlink()
        assert _by_path(round_tree_lines(round_dir, 0))["phases/"].status == (
            STATUS_MISSING
        )

    def test_a_newer_upstream_makes_the_downstream_need_an_update(
        self, round_dir: pathlib.Path
    ) -> None:
        """The case the dependency graph exists for.

        `stack.json` is StackAdvisor's output and `vision.json` one of its
        inputs; touching the vision after the stack was written means the stack
        was chosen against a vision that has since changed.
        """
        base = project_manager.get_version_dir(round_dir, 0)
        stack_mtime = (base / "stack.json").stat().st_mtime
        newer = stack_mtime + 1000
        os.utime(base / "vision.json", (newer, newer))

        statuses = _by_path(round_tree_lines(round_dir, 0))
        assert statuses["stack.json"].status == STATUS_NEEDS_UPDATE
        # Only the stale one moves: `code_review.json` has no upstream at all.
        assert statuses["code_review.json"].status == STATUS_PRESENT

    def test_a_missing_file_reads_missing_even_when_it_is_also_stale(
        self, round_dir: pathlib.Path
    ) -> None:
        """Absence outranks staleness — there is nothing there to update."""
        base = project_manager.get_version_dir(round_dir, 0)
        newer = (base / "deployment-plan.md").stat().st_mtime + 1000
        os.utime(base / "stack.json", (newer, newer))
        (base / "deployment-plan.md").unlink()
        statuses = _by_path(round_tree_lines(round_dir, 0))
        assert statuses["deployment-plan.md"].status == STATUS_MISSING

    def test_the_tree_agrees_with_the_dependency_graph(
        self, round_dir: pathlib.Path
    ) -> None:
        """The graph is the authority; the tree only reports it.

        If these two ever disagree, the tree has started doing its own mtime
        comparison — which is the thing this phase is explicitly not allowed to
        do.
        """
        base = project_manager.get_version_dir(round_dir, 0)
        newer = (base / "design" / "mock.html").stat().st_mtime + 1000
        os.utime(base / "vision.json", (newer, newer))

        assert project_manager.detect_stale_inputs(round_dir, "designer")
        assert _by_path(round_tree_lines(round_dir, 0))["design/mock.html"].status == (
            STATUS_NEEDS_UPDATE
        )


class TestUsageIsNeverStale:
    """D-LR3, as a test.

    ``usage.json`` is appended to by every agent and read by none. It is kept
    out of the dependency graph for that reason: were it an input, any agent
    finishing would mark everything downstream stale. The tree has to hold the
    same line, and a "compute every status the same way" refactor is exactly
    what would break it — so the case is stated on its own rather than folded
    into the status tests above.
    """

    def test_usage_stays_present_when_every_other_artifact_is_newer(
        self, round_dir: pathlib.Path
    ) -> None:
        base = project_manager.get_version_dir(round_dir, 0)
        usage_mtime = (base / "usage.json").stat().st_mtime
        newer = usage_mtime + 10_000
        for rel in _ALL_ARTIFACTS:
            if rel == "usage.json":
                continue
            target = base / rel.rstrip("/")
            for path in ([target] if target.is_file() else target.rglob("*")):
                if path.is_file():
                    os.utime(path, (newer, newer))

        assert _by_path(round_tree_lines(round_dir, 0))["usage.json"].status == (
            STATUS_PRESENT
        )

    def test_usage_is_still_reported_missing_when_absent(
        self, round_dir: pathlib.Path
    ) -> None:
        """Presence-only means presence — not "always present"."""
        (project_manager.get_version_dir(round_dir, 0) / "usage.json").unlink()
        assert _by_path(round_tree_lines(round_dir, 0))["usage.json"].status == (
            STATUS_MISSING
        )

    def test_usage_is_absent_from_the_dependency_graph(self) -> None:
        """The tree must not have been made to work by editing the graph."""
        for output, inputs in project_manager._STALE_DEPENDENCIES.values():
            assert output != "usage.json"
            assert all(rel != "usage.json" for _, rel in inputs)


# ---------------------------------------------------------------------------
# Only this round, and no other
# ---------------------------------------------------------------------------


class TestScope:
    def test_another_rounds_files_do_not_appear(
        self, round_dir: pathlib.Path
    ) -> None:
        """A round 1 folder alongside round 0 changes nothing about round 0."""
        other = project_manager.ensure_version_dir(round_dir, 1)
        _write(other, "vision.json", 2_000_000)
        before = round_tree_lines(round_dir, 0)
        assert [line.path for line in before] == list(_ALL_ARTIFACTS)
        assert all(line.status == STATUS_PRESENT for line in before)

    def test_a_round_with_nothing_on_disk_is_all_missing(
        self, tmp_path: pathlib.Path
    ) -> None:
        lines = round_tree_lines(tmp_path, 0)
        assert [line.path for line in lines] == list(_ALL_ARTIFACTS)
        assert {line.status for line in lines} == {STATUS_MISSING}

    def test_no_working_directory_is_not_an_error(self) -> None:
        """Before a project is opened there is no round — every line is missing."""
        lines = round_tree_lines(None, None)
        assert [line.path for line in lines] == list(_ALL_ARTIFACTS)
        assert {line.status for line in lines} == {STATUS_MISSING}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _ids(component: Any) -> set[str]:
    found: set[str] = set()
    stack = [component]
    while stack:
        node = stack.pop()
        node_id = getattr(node, "id", None)
        if isinstance(node_id, str):
            found.add(node_id)
        children = getattr(node, "children", None)
        if children is None:
            continue
        if not isinstance(children, (list, tuple)):
            children = [children]
        stack.extend(children)
    return found


def _class_names(component: Any) -> list[str]:
    found: list[str] = []
    stack = [component]
    while stack:
        node = stack.pop()
        name = getattr(node, "className", None)
        if isinstance(name, str):
            found.append(name)
        children = getattr(node, "children", None)
        if children is None:
            continue
        if not isinstance(children, (list, tuple)):
            children = [children]
        stack.extend(children)
    return found


def _text(node: Any) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, (list, tuple)):
        return " ".join(_text(child) for child in node)
    inner = getattr(node, "children", None)
    return _text(inner) if inner is not None else ""


class TestRendering:
    def test_it_renders_its_ids(self, round_dir: pathlib.Path) -> None:
        assert {"round-tree", "round-tree-head", "round-tree-list"} <= _ids(
            _round_tree(round_dir, 0)
        )

    def test_the_heading_names_the_round_folder(
        self, round_dir: pathlib.Path
    ) -> None:
        tree = _round_tree(round_dir, 3)
        assert ".spec4/v3/" in _text(tree)

    def test_one_line_per_artifact(self, round_dir: pathlib.Path) -> None:
        tree = _round_tree(round_dir, 0)
        listing = next(
            node
            for node in tree.children
            if getattr(node, "id", "") == "round-tree-list"
        )
        assert len(listing.children) == len(_ALL_ARTIFACTS)

    def test_every_path_is_monospace(self, round_dir: pathlib.Path) -> None:
        classes = _class_names(_round_tree(round_dir, 0))
        assert classes.count("mono") == len(_ALL_ARTIFACTS)

    def test_each_line_carries_its_lane_class(
        self, round_dir: pathlib.Path
    ) -> None:
        classes = _class_names(_round_tree(round_dir, 0))
        for path, lane in ARTIFACT_LANES.items():
            assert f"name lane-{lane}" in classes, path

    def test_the_legend_names_all_three_lanes(
        self, round_dir: pathlib.Path
    ) -> None:
        tree = _round_tree(round_dir, 0)
        legend = next(
            node
            for node in tree.children
            if getattr(node, "id", "") == "round-tree-legend"
        )
        text = _text(legend)
        assert len(legend.children) == 3
        for phrase in (
            "prompts for the agent",
            "reference for the agent",
            "a record for you",
        ):
            assert phrase in text

    def test_the_legend_uses_the_same_lane_classes_as_the_lines(
        self, round_dir: pathlib.Path
    ) -> None:
        """Legend and lines cannot drift: one class list, used twice."""
        classes = set(_class_names(_round_tree(round_dir, 0)))
        for lane in LANES:
            assert f"swatch lane-{lane}" in classes

    def test_present_is_the_unlabelled_resting_state(
        self, round_dir: pathlib.Path
    ) -> None:
        """Only the exceptions get a token, per the design mock."""
        assert "present" not in _text(_round_tree(round_dir, 0))

    def test_the_exceptions_are_labelled_in_words(
        self, round_dir: pathlib.Path
    ) -> None:
        base = project_manager.get_version_dir(round_dir, 0)
        (base / "stack.json").unlink()
        newer = (base / "design" / "mock.html").stat().st_mtime + 1000
        os.utime(base / "vision.json", (newer, newer))

        text = _text(_round_tree(round_dir, 0))
        assert STATUS_MISSING in text
        assert STATUS_NEEDS_UPDATE in text

    def test_it_uses_no_icon_and_no_emoji(self, round_dir: pathlib.Path) -> None:
        """Status is a text token — the mock draws no glyphs here."""
        tree = _round_tree(round_dir, 0)
        stack = [tree]
        names = []
        while stack:
            node = stack.pop()
            names.append(type(node).__name__)
            children = getattr(node, "children", None)
            if children is None:
                continue
            if not isinstance(children, (list, tuple)):
                children = [children]
            stack.extend(children)
        assert not any("Icon" in name for name in names)
        assert all(ord(char) < 128 for char in _text(tree))

    def test_the_lines_are_not_clickable(self, round_dir: pathlib.Path) -> None:
        """Opening a file is the Artifact View's job, in v1."""
        tree = _round_tree(round_dir, 0)
        stack = [tree]
        while stack:
            node = stack.pop()
            assert type(node).__name__ not in ("A", "Link", "Button", "Anchor")
            children = getattr(node, "children", None)
            if children is None:
                continue
            if not isinstance(children, (list, tuple)):
                children = [children]
            stack.extend(children)


def _pill_agents(component: Any) -> set[str]:
    """The agent keys behind the project view's pattern-matching action buttons."""
    found: set[str] = set()
    stack = [component]
    while stack:
        node = stack.pop()
        node_id = getattr(node, "id", None)
        if isinstance(node_id, dict) and node_id.get("type") == "agent-pill":
            found.add(node_id["agent"])
        children = getattr(node, "children", None)
        if children is None:
            continue
        if not isinstance(children, (list, tuple)):
            children = [children]
        stack.extend(children)
    return found


class TestItSitsFirstInTheProjectView:
    def test_the_tree_is_the_first_element(self, round_dir: pathlib.Path) -> None:
        session = {**_default_session(), "working_dir": str(round_dir)}
        view = _agent_select_layout(session)
        assert getattr(view.children[0], "id", None) == "round-tree"

    def test_the_existing_project_view_ids_survive(
        self, round_dir: pathlib.Path
    ) -> None:
        session = {**_default_session(), "working_dir": str(round_dir)}
        view = _agent_select_layout(session)
        assert "btn-agent-change-provider" in _ids(view)
        # The seven action buttons carry pattern-matching ids, so they are
        # collected by shape rather than by name.
        assert _pill_agents(view) == set(AGENT_KEYS)


# ---------------------------------------------------------------------------
# The callback
# ---------------------------------------------------------------------------


class TestTheCallbackRecomputes:
    def test_it_returns_a_heading_and_a_line_per_artifact(
        self, round_dir: pathlib.Path
    ) -> None:
        session = {**_default_session(), "working_dir": str(round_dir)}
        head, lines = on_round_tree("round-tree", session)
        assert head == ".spec4/v0/"
        assert len(lines) == len(_ALL_ARTIFACTS)

    def test_it_sees_a_file_written_after_the_last_render(
        self, round_dir: pathlib.Path
    ) -> None:
        """Nothing is cached (D-LR4), so the second call is not the first one.

        This is the failure the no-cache rule exists for: an agent finishes and
        writes its artifact while the page is open, and a tree computed once
        would keep reporting it missing.
        """
        base = project_manager.get_version_dir(round_dir, 0)
        (base / "stack.json").unlink()
        session = {**_default_session(), "working_dir": str(round_dir)}

        _, before = on_round_tree("round-tree", session)
        assert STATUS_MISSING in _text(before)

        _write(base, "stack.json", 1_000_000)
        _, after = on_round_tree("round-tree", session)
        assert STATUS_MISSING not in _text(after)

    def test_it_follows_the_session_to_another_project(
        self, tmp_path: pathlib.Path
    ) -> None:
        full = tmp_path / "full"
        empty = tmp_path / "empty"
        empty.mkdir()
        base = project_manager.ensure_version_dir(full, 0)
        for index, rel in enumerate(_ALL_ARTIFACTS):
            _write(base, rel, 1_000_000 + index)

        _, populated = on_round_tree(
            "round-tree", {**_default_session(), "working_dir": str(full)}
        )
        _, blank = on_round_tree(
            "round-tree", {**_default_session(), "working_dir": str(empty)}
        )
        assert STATUS_MISSING not in _text(populated)
        assert _text(blank).count(STATUS_MISSING) == len(_ALL_ARTIFACTS)

    def test_it_follows_the_round(self, round_dir: pathlib.Path) -> None:
        session = {
            **_default_session(),
            "working_dir": str(round_dir),
            "phase_version": 1,
        }
        head, _ = on_round_tree("round-tree", session)
        assert head == ".spec4/v1/"

    def test_it_survives_an_empty_session(self) -> None:
        head, lines = on_round_tree("round-tree", None)
        assert head is not None
        assert len(lines) == len(_ALL_ARTIFACTS)
