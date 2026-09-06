"""The round tree — the current round's ``.spec4/v{N}/`` folder, as a list.

One line per artifact, in pipeline order, each carrying a lane and a live
status. It is the first thing on the project view because it answers the
question the developer actually arrives with: what has this round produced,
and what is out of date?

Two rules hold this module together.

*Lanes are declared, never inferred.* ``_ARTIFACTS_BY_AGENT`` below is the
reviewed table: which files each pipeline agent writes, and which of the three
lanes each one belongs to. Nothing here looks at a file extension or a parent
directory to decide a lane — ``design/mock.html`` and ``deployment-plan.md``
are exactly the two files a pattern would misfile, and both are named in the
table instead.

*Status is read from disk, every time.* ``round_tree_lines`` stats the round's
files on each call and asks ``project_manager.detect_stale_inputs`` — the
pipeline's one freshness authority — whether each agent's output has fallen
behind its inputs. Nothing is memoised and nothing is stashed in a store
(D-LR4), because an agent that finishes mid-session changes the answer and a
cached tree would keep showing the old one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from dash import html

from spec4 import project_manager
from spec4.app_constants import AGENT_KEYS

__all__ = [
    "LANE_PROMPT",
    "LANE_RECORD",
    "LANE_REF",
    "LANES",
    "LANE_LEGEND",
    "ARTIFACT_GROUPS",
    "ARTIFACT_LANES",
    "ROUND_ARTIFACTS",
    "STATUS_MISSING",
    "STATUS_NEEDS_UPDATE",
    "STATUS_PRESENT",
    "TreeArtifact",
    "TreeLine",
    "_round_tree",
    "_round_tree_head",
    "_round_tree_lines_children",
    "round_tree_lines",
]

# ---------------------------------------------------------------------------
# Lanes
# ---------------------------------------------------------------------------

# The three lanes, as the design mock names them. A lane says who a file is
# *for*, which is the one thing a developer cannot read off the filename.
LANE_PROMPT = "prompt"
LANE_REF = "ref"
LANE_RECORD = "record"

LANES: tuple[str, ...] = (LANE_PROMPT, LANE_REF, LANE_RECORD)

# The legend, in lane order. The lines and the legend read their colour from
# the same ``lane-{value}`` class, so a recolour cannot leave the two
# disagreeing about what orange means.
LANE_LEGEND: tuple[tuple[str, str], ...] = (
    (LANE_PROMPT, "prompts for the agent"),
    (LANE_REF, "reference for the agent"),
    (LANE_RECORD, "a record for you"),
)

# ---------------------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------------------

STATUS_PRESENT = "present"
STATUS_NEEDS_UPDATE = "needs update"
STATUS_MISSING = "missing"


class TreeArtifact(NamedTuple):
    """One row of the reviewed lane table.

    ``path`` is relative to ``.spec4/v{N}/`` and is also what the line renders,
    so a directory carries its trailing slash here (``pathlib`` drops it when
    the path is joined, and the developer sees that it is a folder).
    """

    path: str
    lane: str


class TreeLine(NamedTuple):
    """A rendered line: the manifest's ``TreeLine`` entity."""

    path: str
    lane: str
    status: str


# The reviewed artifact-to-lane table, keyed by the agent that writes each
# file. Keying it by agent does two jobs at once: it gives the tree its
# pipeline order for free (the keys are walked in ``AGENT_KEYS`` order, so the
# tree cannot drift from the pipeline definition), and it names the agent whose
# ``detect_stale_inputs`` entry governs the file's freshness.
#
# Every one of the seven agents appears, even when it writes nothing yet, so
# that adding a pipeline stage fails the coverage test rather than silently
# dropping its artifacts off the tree.
_ARTIFACTS_BY_AGENT: dict[str, tuple[TreeArtifact, ...]] = {
    "code_scanner": (TreeArtifact("code_review.json", LANE_REF),),
    # Brainstormer writes both of these in the same persist step: the vision
    # and the per-feature specs behind it.
    "brainstormer": (
        TreeArtifact("vision.json", LANE_REF),
        TreeArtifact("feature_specs.json", LANE_REF),
    ),
    "agentifier": (TreeArtifact("ai_features.json", LANE_REF),),
    # The mock is what a coding agent is handed; the manifest is the same
    # design as data. Both are reference, and both land together.
    "designer": (
        TreeArtifact("design/mock.html", LANE_REF),
        TreeArtifact("design/manifest.json", LANE_REF),
    ),
    "stack_advisor": (TreeArtifact("stack.json", LANE_REF),),
    # The one prompt lane: the phase files are the instructions the coding
    # agent is given, verbatim.
    "phaser": (TreeArtifact("phases/", LANE_PROMPT),),
    "deployer": (TreeArtifact("deployment-plan.md", LANE_RECORD),),
}

# Files in the round folder that no agent owns. ``usage.json`` is written by
# every agent and read by none, which is exactly why it is here and not above:
# it has no freshness edges at all (D-LR3).
_UNOWNED_ARTIFACTS: tuple[TreeArtifact, ...] = (
    TreeArtifact("usage.json", LANE_RECORD),
)

# D-LR3: ``usage.json`` is never Needs Update. It is deliberately absent from
# the dependency graph (``project_manager._NON_ARTIFACT_FILES``) because every
# agent appends to it — were it an input, finishing any agent would immediately
# mark every downstream agent stale, and the whole pipeline would read as out
# of date the moment it was used. Its status is file presence, and nothing
# else. The exemption is restated here, at the point of use, so that a later
# "compute every line the same way" refactor has to delete a named rule rather
# than merely forget one.
_STALENESS_EXEMPT: frozenset[str] = frozenset({"usage.json"})


def _artifact_groups() -> tuple[tuple[str | None, tuple[TreeArtifact, ...]], ...]:
    """``(owning agent, its artifacts)`` in pipeline order, then the unowned.

    The order is taken from the pipeline definition rather than restated, so a
    reordered pipeline reorders the tree and a new agent cannot be added
    without deciding what it writes. ``None`` is the group no agent owns, and
    it comes last because a record of the round is written after the round.
    """
    groups: list[tuple[str | None, tuple[TreeArtifact, ...]]] = [
        (agent, _ARTIFACTS_BY_AGENT.get(agent, ())) for agent in AGENT_KEYS
    ]
    groups.append((None, _UNOWNED_ARTIFACTS))
    return tuple(groups)


ARTIFACT_GROUPS = _artifact_groups()

ROUND_ARTIFACTS: tuple[TreeArtifact, ...] = tuple(
    artifact for _, artifacts in ARTIFACT_GROUPS for artifact in artifacts
)

# path -> lane, for the callers (and the tests) that only need the lane.
ARTIFACT_LANES: dict[str, str] = {a.path: a.lane for a in ROUND_ARTIFACTS}


# ---------------------------------------------------------------------------
# Status, from disk
# ---------------------------------------------------------------------------


def _exists(path: Path) -> bool:
    """Whether the artifact at `path` has actually been produced.

    A directory counts only when it holds a file: ``phases/`` can exist as an
    empty folder before Phaser has written anything into it, and an empty
    folder is not a produced artifact. This mirrors ``_path_mtime``, which
    reports no mtime for exactly the same case.
    """
    if not path.exists():
        return False
    if path.is_file():
        return True
    return any(child.is_file() for child in path.rglob("*"))


def _stale_agents(working_dir: str | Path, round_number: int) -> frozenset[str]:
    """The agents whose output has fallen behind its inputs, from the graph.

    ``detect_stale_inputs`` is the pipeline's one staleness authority and is
    used exactly as it stands — no mtime comparison is repeated here, and no
    artifact is added to the graph to make the tree nicer.

    It resolves the round itself (``active_version``), which is the round the
    project view is showing in every ordinary case. When it is not — a session
    pinned to an earlier round than the newest on disk — the graph would be
    answering about a different folder than the one being drawn, so the tree
    falls back to presence alone rather than reporting a status it cannot
    stand behind.
    """
    if project_manager.active_version(working_dir) != round_number:
        return frozenset()
    return frozenset(
        agent
        for agent in AGENT_KEYS
        if project_manager.detect_stale_inputs(working_dir, agent)
    )


def round_tree_lines(
    working_dir: str | Path | None, round_number: int | None
) -> list[TreeLine]:
    """The current round's artifacts as ``TreeLine`` records, in pipeline order.

    Every artifact in the reviewed table yields exactly one line on every call,
    whether or not the file is on disk — an absent file is reported as
    ``missing``, never dropped, because a line that vanishes tells the
    developer nothing about what is supposed to be there.

    No round (no working directory yet, or no round resolved) is not an error:
    every artifact is simply missing, which is the truth about an unopened
    project.
    """
    if not working_dir or round_number is None:
        return [
            TreeLine(a.path, a.lane, STATUS_MISSING) for a in ROUND_ARTIFACTS
        ]

    base = project_manager.get_version_dir(working_dir, round_number)
    stale = _stale_agents(working_dir, round_number)

    lines: list[TreeLine] = []
    for agent, artifacts in ARTIFACT_GROUPS:
        for artifact in artifacts:
            if not _exists(base / artifact.path):
                status = STATUS_MISSING
            elif artifact.path in _STALENESS_EXEMPT:
                # D-LR3, above: presence and nothing else.
                status = STATUS_PRESENT
            elif agent is not None and agent in stale:
                status = STATUS_NEEDS_UPDATE
            else:
                status = STATUS_PRESENT
            lines.append(TreeLine(artifact.path, artifact.lane, status))
    return lines


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _round_tree_head(round_number: int | None) -> str:
    """The folder the tree is showing, as its own heading."""
    return f".spec4/v{round_number}/" if round_number is not None else ".spec4/"


def _line_children(line: TreeLine) -> Any:
    """One ``<li>``: the path in its lane colour, the status at the right.

    ``present`` is the resting state and is left unlabelled — the design mock
    draws a status token only for the two exceptions, so the eye lands on the
    handful of lines that need something rather than on a column of the word
    "present". The span itself is always rendered, so the row's shape does not
    change as a status does.
    """
    label = "" if line.status == STATUS_PRESENT else line.status
    classes = ["mono"]
    if line.status == STATUS_MISSING:
        classes.append("is-missing")
    elif line.status == STATUS_NEEDS_UPDATE:
        classes.append("is-stale")
    return html.Li(
        [
            html.Span(line.path, className=f"name lane-{line.lane}"),
            html.Span(label, className="status"),
        ],
        className=" ".join(classes),
    )


def _round_tree_lines_children(lines: list[TreeLine]) -> list[Any]:
    """The ``<ol>``'s children — what the callback writes on every render."""
    return [_line_children(line) for line in lines]


def _legend() -> html.Ul:
    """One item per lane, drawn from the same table the lines use."""
    return html.Ul(
        [
            html.Li([html.Span(className=f"swatch lane-{lane}"), label])
            for lane, label in LANE_LEGEND
        ],
        id="round-tree-legend",
        className="legend",
        # Dash passes unknown props straight through to the DOM; its stubs
        # only know the documented ones, hence the ignore for a plain
        # accessibility attribute the design mock also carries.
        **{"aria-label": "Lanes"},  # type: ignore[arg-type]
    )


def _round_tree(
    working_dir: str | Path | None, round_number: int | None
) -> html.Section:
    """The round tree, rendered for a round.

    The first paint computes its own lines so the project view is never briefly
    empty; the callback in ``spec4.callbacks`` recomputes them from disk on
    every render after that. Lines are not clickable — opening a file is the
    Artifact View's job, in v1.
    """
    return html.Section(
        [
            html.H2(
                _round_tree_head(round_number),
                id="round-tree-head",
                className="section-head mono",
            ),
            html.Ol(
                _round_tree_lines_children(
                    round_tree_lines(working_dir, round_number)
                ),
                id="round-tree-list",
                className="tree-list",
            ),
            _legend(),
        ],
        id="round-tree",
        className="round-tree",
    )
