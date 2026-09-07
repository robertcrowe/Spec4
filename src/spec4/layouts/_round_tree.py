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
    "ARTIFACT_TREE_IDS",
    "LINE_TYPE",
    "LANE_PROMPT",
    "LANE_RECORD",
    "LANE_REF",
    "LANES",
    "LANE_LABELS",
    "LANE_LEGEND",
    "PROJECT_TREE_IDS",
    "TreeIds",
    "ARTIFACT_GROUPS",
    "ARTIFACT_LANES",
    "ROUND_ARTIFACTS",
    "PHASES_DIR",
    "STATUS_MISSING",
    "STATUS_NEEDS_UPDATE",
    "STATUS_PRESENT",
    "TreeArtifact",
    "TreeLine",
    "_round_tree",
    "_round_tree_head",
    "_round_tree_lines_children",
    "line_id",
    "round_tree_lines",
    "rendered_tree_lines",
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

# The same three phrases, indexed by lane, for a surface that names one lane
# rather than listing all three — the Artifact View's file header. Derived from
# the legend rather than restated, so the header and the swatch beside the file
# it describes cannot end up calling the same lane two different things.
LANE_LABELS: dict[str, str] = dict(LANE_LEGEND)

# ---------------------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------------------

STATUS_PRESENT = "present"
STATUS_NEEDS_UPDATE = "needs update"
STATUS_MISSING = "missing"

# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------

# The ``type`` half of a linked line's pattern-matching id. Named once so that
# the render side (``line_id``) and the click callback's Input pattern are the
# same string by construction rather than by two people typing it.
LINE_TYPE = "round-tree-line"


# ---------------------------------------------------------------------------
# Id sets
# ---------------------------------------------------------------------------


class TreeIds(NamedTuple):
    """The four string ids one rendered tree carries.

    Two screens draw this tree, and each needs its *own* ids rather than a
    shared set. Dash keys a callback to a component id, so two trees sharing
    ``round-tree-list`` would mean ``on_round_tree`` — which recomputes the
    project view's tree for the *active* round — writing over the Artifact
    View's tree, which is drawn for whichever round the developer selected.
    The developer would pick v1, watch its files appear, and see them replaced
    by v3's a moment later with nothing logged anywhere.

    So the ids are a parameter instead, and the renderer stays one function.
    Forking the renderer would have solved the collision too and cost the
    thing that matters more: the two screens' lines, lanes, statuses and
    legend are identical because they are literally the same code.
    """

    root: str
    head: str
    lines: str
    legend: str


# The project view's tree, and the ids every existing caller and callback
# already names. This is the default, so no existing call site changes.
PROJECT_TREE_IDS = TreeIds(
    "round-tree", "round-tree-head", "round-tree-list", "round-tree-legend"
)

# The Artifact View's tree. Its lines are recomputed by the screen's own
# layout on every render (``render_page`` redraws the page whenever the
# session changes, and the round selector writes the session), so no callback
# writes into these — which is exactly why they must not be the ids above.
ARTIFACT_TREE_IDS = TreeIds(
    "artifact-view-tree",
    "artifact-view-tree-head",
    "artifact-view-tree-list",
    "artifact-view-tree-legend",
)


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
# The phase files, expanded
# ---------------------------------------------------------------------------

# The one directory artifact in the reviewed table. It is the only entry whose
# single line stands for many files, which is why it is the only one that
# expands below — and why it is named here rather than detected by looking for
# a trailing slash, so a second directory artifact added later has to decide
# what it wants rather than inherit this.
PHASES_DIR = "phases/"


def _phase_file_order(name: str) -> tuple[int, str]:
    """Sort key for a phase filename: by phase number, then by name.

    ``phase10.md`` sorts after ``phase9.md``, which a plain lexicographic sort
    gets backwards — and the tree's whole claim is that it lists the round in
    pipeline order. A name with no digits sorts last, by name, rather than
    being dropped.
    """
    digits = "".join(ch for ch in name if ch.isdigit())
    return (int(digits) if digits else 10**9, name)


def _phase_files(base: Path) -> list[str]:
    """The round's phase files, as paths relative to the round folder.

    Read from disk on every call, like everything else here (D-LR4): Phaser
    writing a new phase file while the page is open has to change the tree the
    next time it draws.
    """
    directory = base / PHASES_DIR.rstrip("/")
    if not directory.is_dir():
        return []
    names = sorted(
        (child.name for child in directory.iterdir() if child.is_file()),
        key=_phase_file_order,
    )
    return [f"{PHASES_DIR}{name}" for name in names]


def rendered_tree_lines(
    working_dir: str | Path | None, round_number: int | None
) -> list[TreeLine]:
    """The lines a *screen* lists: ``round_tree_lines`` with ``phases/`` opened.

    ``round_tree_lines`` answers about the reviewed table — one line per
    artifact, ``phases/`` included, which is the contract the lane and status
    tests hold it to. A screen needs something slightly different: a developer
    clicking a line means "open this file", and ``phases/`` is not a file. So
    the directory's line is replaced here by one line per phase file on disk,
    each carrying the directory's lane and status — the lane still comes from
    ``ROUND_ARTIFACTS`` and the status still comes from the dependency graph,
    because both are taken from the line being replaced rather than recomputed.

    An empty or absent ``phases/`` expands to nothing, so the directory's own
    line stays and reports ``missing``. That is deliberate: a line that
    vanished would tell the developer nothing about what Phaser is supposed to
    produce, which is the same reason ``round_tree_lines`` never drops an
    absent artifact.
    """
    lines = round_tree_lines(working_dir, round_number)
    if not working_dir or round_number is None:
        return lines
    base = project_manager.get_version_dir(working_dir, round_number)
    files = _phase_files(base)
    if not files:
        return lines
    expanded: list[TreeLine] = []
    for line in lines:
        if line.path == PHASES_DIR:
            expanded.extend(TreeLine(path, line.lane, line.status) for path in files)
        else:
            expanded.append(line)
    return expanded


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _round_tree_head(round_number: int | None) -> str:
    """The folder the tree is showing, as its own heading."""
    return f".spec4/v{round_number}/" if round_number is not None else ".spec4/"


def line_id(path: str) -> dict[str, str]:
    """The pattern-matching id of a linked line, built in exactly one place.

    A pattern id is two halves that have to agree: the dict written into the
    tree here, and the ``Input({"type": LINE_TYPE, "index": ALL}, ...)`` the
    click callback registers. When they disagree Dash raises nothing and logs
    nothing — the line simply stops doing anything — so the render side is a
    function rather than a literal, the Input side names ``LINE_TYPE``, and the
    tests ask this for the ids they look for.

    ``index`` is the artifact's path within the round folder, which is what
    makes the target resolvable at click time from the triggered id alone.
    """
    return {"type": LINE_TYPE, "index": path}


def _line_children(
    line: TreeLine, *, linked: bool = False, selected: str | None = None
) -> Any:
    """One ``<li>``: the path in its lane colour, the status at the right.

    ``present`` is the resting state and is left unlabelled — the design mock
    draws a status token only for the two exceptions, so the eye lands on the
    handful of lines that need something rather than on a column of the word
    "present". The span itself is always rendered, so the row's shape does not
    change as a status does.

    ``linked`` wraps those same two spans in a control rather than building a
    second kind of row: the lane class, the status token, the missing and stale
    modifiers and the ``mono`` class are computed once above and are identical
    in both forms, so a linked tree and a plain one cannot drift in anything
    but whether the row can be clicked. The mock draws the wrapper as an
    anchor; it is a button here for the same reason the status bar's directory
    field is one (``.sb-dir``) — it moves the app rather than the document, and
    a button is the control that is focusable and keyboard-operable without
    inventing an href. Its chrome is stripped in the stylesheet, so the row
    still reads as a line of a listing.

    ``selected`` marks the current file with the shell's active-state
    mechanism: a modifier class, never a ``color`` prop (D-LR2). The accent it
    picks up is the Mantine theme primary, exactly as ``sb-nav-link--active``
    does in the header.
    """
    label = "" if line.status == STATUS_PRESENT else line.status
    classes = ["mono"]
    if line.status == STATUS_MISSING:
        classes.append("is-missing")
    elif line.status == STATUS_NEEDS_UPDATE:
        classes.append("is-stale")
    if selected is not None and line.path == selected:
        classes.append("is-selected")
    row: list[Any] = [
        html.Span(line.path, className=f"name lane-{line.lane}"),
        html.Span(label, className="status"),
    ]
    return html.Li(
        html.Button(
            row,
            id=line_id(line.path),
            n_clicks=0,
            className="tree-link",
            title=f"Open {line.path}",
        )
        if linked
        else row,
        className=" ".join(classes),
    )


def _round_tree_lines_children(
    lines: list[TreeLine], *, linked: bool = False, selected: str | None = None
) -> list[Any]:
    """The ``<ol>``'s children — what the callback writes on every render.

    The callback passes the same ``linked`` and ``selected`` the first paint
    used. It has to: this replaces the list wholesale on every render, so a
    recompute that forgot the link form would silently un-link a tree that
    drew as clickable a moment earlier.
    """
    return [_line_children(line, linked=linked, selected=selected) for line in lines]


def _legend(legend_id: str = PROJECT_TREE_IDS.legend) -> html.Ul:
    """One item per lane, drawn from the same table the lines use."""
    return html.Ul(
        [
            html.Li([html.Span(className=f"swatch lane-{lane}"), label])
            for lane, label in LANE_LEGEND
        ],
        id=legend_id,
        className="legend",
        # Dash passes unknown props straight through to the DOM; its stubs
        # only know the documented ones, hence the ignore for a plain
        # accessibility attribute the design mock also carries.
        **{"aria-label": "Lanes"},  # type: ignore[arg-type]
    )


def _round_tree(
    working_dir: str | Path | None,
    round_number: int | None,
    *,
    linked: bool = False,
    selected: str | None = None,
    ids: TreeIds = PROJECT_TREE_IDS,
) -> html.Section:
    """The round tree, rendered for a round. One renderer, two screens.

    The first paint computes its own lines so the project view is never briefly
    empty; the callback in ``spec4.callbacks`` recomputes them from disk on
    every render after that.

    ``linked`` is keyword-only and defaults to the plain form, so every
    existing call site keeps the behaviour it had and a new one has to ask for
    links by name. It switches the rows into controls that open the Artifact
    View; ``selected`` marks one of them as the file currently being read.
    Neither forks the renderer — this is the app's only round tree, and the
    project view and the Artifact View are the same tree drawn with different
    arguments, which is what keeps the two screens' registers identical.

    ``ids`` is the one thing the two screens cannot share; see :class:`TreeIds`
    for why. It defaults to the project view's set, so nothing that already
    calls this changes and a second tree has to name its own.
    """
    return html.Section(
        [
            html.H2(
                _round_tree_head(round_number),
                id=ids.head,
                className="section-head mono",
            ),
            html.Ol(
                _round_tree_lines_children(
                    rendered_tree_lines(working_dir, round_number),
                    linked=linked,
                    selected=selected,
                ),
                id=ids.lines,
                className="tree-list",
            ),
            _legend(ids.legend),
        ],
        id=ids.root,
        className="round-tree",
    )
