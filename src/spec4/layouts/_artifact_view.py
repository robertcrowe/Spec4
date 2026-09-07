"""The Artifact View — a round's files, read in place.

Two panes on one grid, exactly as the design mock draws them: a left pane that
selects a round and lists that round's artifacts, and a right pane that shows
the selected file. The screen sits inside the same shell as every other screen
(``render_page`` puts it in ``page-content``), so it wears the status strip and
the primary navigation without restating either.

``resolve_artifact`` is the only way this app turns a requested path into a
file on disk, and it answers about the reviewed artifact table before it
touches the filesystem at all. Every read on this screen goes through it.

Five rules hold this module together.

*Lanes come from the tree's table, never from the mock's sample data.*
``_round_tree.ROUND_ARTIFACTS`` is the one reviewed artifact-to-lane table in
the app; the mock's own array misfiles ``deployment-plan.md``, and copying it
would put a record in the wrong lane on the one screen built to read records.

*Selection is session state, not layout state.* Which round and which file are
selected live in the browser session store (``selected_round`` /
``selected_file``), so a link from the round tree or the chat frame can set
them before this screen renders, and so nothing about the selection is held on
the server (D-LR2's sibling constraint: provider keys and selections alike stay
in the browser).

*The allow-list decides, then the filesystem.* Every check that can reject a
request is made against the reviewed table and the requested string alone;
only a path that survives all of them is ever joined, resolved or stated. The
ordering is the security property, so it is written as one straight-line
sequence in ``resolve_artifact`` and asserted directly in the tests.

*The round list is read from disk on every render, never cached.* A round
created since the screen was last drawn — by the persist funnel, or by a run
in another tab — has to appear in the selector the next time it draws. That is
the Artifact View's stale-round-list failure mode, and
``project_manager.rounds_on_disk`` is written to have nothing to invalidate.

*Line numbers are two strings, not two thousand components.* The gutter and
the content are one ``html.Pre`` each, side by side; a component per line is
the obvious implementation and is the one that makes a large artifact hang the
browser. See :func:`line_numbered`.
"""

from __future__ import annotations

import json
import os
import stat as stat_module
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

from dash import dcc, html
import dash_mantine_components as dmc

from spec4 import project_manager
from spec4.layouts._agent_rows import AGENT_DISPLAY_NAMES
from spec4.layouts._round_tree import (
    ARTIFACT_GROUPS,
    ARTIFACT_TREE_IDS,
    LANE_LABELS,
    PHASES_DIR,
    _phase_files,
    _round_tree,
)
from spec4.layouts._shared import _sep

__all__ = [
    "BODY_ID",
    "DOWNLOAD_BTN_ID",
    "DOWNLOAD_ID",
    "EMPTY_CONTENT",
    "HEADER_ID",
    "MOCK_HTML_PATH",
    "MOCK_STORE_ID",
    "OPEN_RENDERED_BTN_ID",
    "RESOLUTION_MISSING",
    "RESOLUTION_PRESENT",
    "RESOLUTION_REJECTED",
    "ROUND_SELECT_ID",
    "ROUND_TYPE",
    "SCROLL_ID",
    "UNREADABLE",
    "AllowedArtifact",
    "ArtifactResolution",
    "_artifact_view_layout",
    "_round_select",
    "allowed_artifacts",
    "artifact_controls",
    "artifact_pane",
    "line_numbered",
    "missing_message",
    "mock_html_for_store",
    "rejection_message",
    "rendered_text",
    "resolve_artifact",
    "round_id",
    "round_number_from_value",
    "round_value",
    "selected_round",
]

# What the content pane says with nothing selected. The mock draws it as the
# pane's own empty state rather than as prose above the pane, which is what
# keeps the two-pane shape stable between "nothing chosen yet" and a file.
EMPTY_CONTENT = "Select a file"

# The screen's own ids, named once. The callback in ``spec4.callbacks`` writes
# into the header and the body, and a literal typed twice is a callback that
# silently stops filling a renamed component.
ROUND_SELECT_ID = "artifact-round-select"
HEADER_ID = "artifact-view-header"
BODY_ID = "artifact-view-content-body"
SCROLL_ID = "artifact-view-scroll"
DOWNLOAD_ID = "artifact-download"
DOWNLOAD_BTN_ID = "artifact-download-btn"
OPEN_RENDERED_BTN_ID = "artifact-open-rendered-btn"
MOCK_STORE_ID = "artifact-mock-store"

# The one file this screen can also open rendered rather than as text. Not
# drawn from ``ROUND_ARTIFACTS`` — nothing there marks a path as renderable,
# and the only thing that would makes a second table for one entry to live in.
MOCK_HTML_PATH = "design/mock.html"


# ---------------------------------------------------------------------------
# The allowed set
# ---------------------------------------------------------------------------


class AllowedArtifact(NamedTuple):
    """One entry of the reviewed artifact table, resolved for a round.

    ``agent`` is the pipeline key that writes the file — ``"stack_advisor"``,
    not ``"StackAdvisor"``. The key is the identity the rest of the app indexes
    by (it is one of ``AGENT_KEYS``, and it is what ``detect_stale_inputs``
    answers about); turning it into something a developer reads is the render
    side's job, through ``_agent_rows.AGENT_DISPLAY_NAMES``. Carrying the
    display string here instead would put a fourth copy of that mapping in the
    app and would make this data layer answer a question about presentation.

    It is ``None`` for an artifact no agent owns. That is not an oversight:
    ``usage.json`` is written by every agent and owned by none (D-LR3), so
    there is no single producer to name, and a caller rendering "produced by"
    has to handle its absence rather than be handed a plausible lie.
    """

    path: str
    lane: str
    agent: str | None


def allowed_artifacts(
    working_dir: str | Path | None, round_number: int | None
) -> dict[str, AllowedArtifact]:
    """The files that may be opened for a round, keyed by relative path.

    Built from ``ARTIFACT_GROUPS`` rather than ``ROUND_ARTIFACTS`` because the
    groups are what carry the owning agent — ``TreeArtifact`` is a path and a
    lane and nothing else. Walking the groups also takes the pipeline order for
    free, which is the same reason the tree walks them.

    ``phases/`` is the one entry that stands for many files, and it is expanded
    here exactly as ``rendered_tree_lines`` expands it: through
    ``_round_tree._phase_files``, from disk, on every call. Sharing that one
    function is the point. A separate glob here — for ``*.md``, say — would let
    the tree draw a line the resolver then refuses, and a tree line that opens
    nothing is a dead link with no error anywhere to explain it.

    When the expansion is empty the directory's own entry stays in the set,
    owned by Phaser. That mirrors the tree, which keeps drawing the ``phases/``
    line while the folder is empty so the developer can still see what Phaser
    is meant to produce. Because the line is drawn it is clickable, so it has
    to resolve — as allowed-but-missing, which names its producer, rather than
    as a rejection, which would read as though the app had something to hide.

    The resulting key set is exactly the set of paths
    ``rendered_tree_lines`` draws for the same round. That equality is the
    invariant tying the two together and is asserted directly in the tests.
    """
    phase_files: list[str] = []
    if working_dir and round_number is not None:
        phase_files = _phase_files(
            project_manager.get_version_dir(working_dir, round_number)
        )

    allowed: dict[str, AllowedArtifact] = {}
    for agent, artifacts in ARTIFACT_GROUPS:
        for artifact in artifacts:
            paths = (
                (phase_files or [PHASES_DIR])
                if artifact.path == PHASES_DIR
                else [artifact.path]
            )
            for path in paths:
                allowed[path] = AllowedArtifact(path, artifact.lane, agent)
    return allowed


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

# The three outcomes. ``rejected`` is deliberately not called "denied" or
# "forbidden": see ``resolve_artifact`` on why the ordinary case for it is a
# stale selection rather than an attack.
RESOLUTION_PRESENT = "present"
RESOLUTION_MISSING = "missing"
RESOLUTION_REJECTED = "rejected"


class ArtifactResolution(NamedTuple):
    """What a request for one artifact resolved to.

    ``outcome`` is one of the three constants above and is the only field a
    caller may branch on. The rest are filled in as far as the outcome allows:

    - ``rejected`` — everything else is ``None``. Nothing was read, nothing was
      stated, and there is nothing truthful to say about a path the app does
      not recognise for this round.
    - ``missing`` — ``lane`` and ``agent`` are set, so the view can say which
      lane the artifact belongs to and who produces it. ``resolved``, ``size``
      and ``modified`` are ``None``; there is no file.
    - ``present`` — every field is set. ``modified`` is a POSIX timestamp
      (``st_mtime``), left as a float for the render side to format, since this
      layer has no business deciding what a date looks like.
    """

    outcome: str
    path: str
    lane: str | None
    agent: str | None
    resolved: Path | None
    size: int | None
    modified: float | None


def _rejected(path: str) -> ArtifactResolution:
    """The one shape a refusal takes, built in one place."""
    return ArtifactResolution(RESOLUTION_REJECTED, path, None, None, None, None, None)


def _missing(entry: AllowedArtifact) -> ArtifactResolution:
    """An artifact that is listed for this round but is not on disk."""
    return ArtifactResolution(
        RESOLUTION_MISSING, entry.path, entry.lane, entry.agent, None, None, None
    )


def _resolve(path: Path) -> Path:
    """``Path.resolve``, behind a seam.

    Named so the tests can assert it was never reached. Resolving is already a
    filesystem operation — it reads symlinks along the whole path — so "the
    filesystem was not touched for a rejected request" is a claim about this
    function as much as about ``_stat``, and a test that watched only the stat
    would miss a resolve that had crept above the allow-list check.
    """
    return path.resolve()


def _stat(path: Path) -> os.stat_result | None:
    """One ``os.stat``, or ``None`` if there is nothing there to stat.

    The single filesystem read of the requested path, and the only one: size
    and mtime both come off this one result rather than from an ``exists()``
    followed by two more calls. ``OSError`` covers the file being deleted
    between the resolve and the stat, a broken symlink, and a directory
    component that has stopped being a directory — none of which are errors
    here, they are all just "no file".
    """
    try:
        return os.stat(path)
    except OSError:
        return None


def resolve_artifact(
    working_dir: str | Path | None,
    round_number: int | None,
    requested: str | None,
) -> ArtifactResolution:
    """Resolve a requested path within a round, or refuse it.

    The one door between a path the app was handed and a file it will read.
    Every artifact read goes through here, which is what makes the confinement
    claim checkable in one place instead of at every call site.

    The checks are ordered, and the order is the security property. In sequence
    — no early returns interleaved with filesystem work, no shortcuts:

    1. An absolute path is refused.
    2. A path with any ``..`` segment is refused.
    3. A path not in this round's allowed set is refused.
    4. Only now is the path joined under the round's directory and resolved,
       and the result must be inside that directory. This last check is what
       catches a listed entry that is a symlink pointing out of the folder: its
       relative path is impeccable and steps 1–3 pass it. It is
       ``is_relative_to`` against both resolved paths, never a string prefix
       test — ``.spec4/v1`` is a prefix of ``.spec4/v10`` as text, and a
       symlink defeats the comparison outright.

    Steps 1 and 2 read the requested string and nothing else. Step 3 does touch
    the filesystem, but only the round's own ``phases/`` directory, never the
    requested path — so a refused request is refused with the requested path
    unread, unresolved and unstated, which the tests assert by watching
    ``_resolve`` and ``_stat``.

    **A rejection is a normal outcome, not only an attack.** It is what the app
    should expect when a selection has gone stale: the developer had a phase
    file open and switched to a round that never had one, or an agent rewrote
    the round and the file is simply gone, or a bookmarked selection is being
    restored into a project it does not match. Traversal attempts land here
    too, but they are the rare case. A view should therefore render it as "no
    such artifact in v{N}" — a statement about this round, and an invitation to
    pick something else — rather than as an error, a warning, or an accusation.
    Only an artifact that is listed for the round and genuinely absent gets the
    missing treatment, because only that one has a producer to name.

    A request with no round to resolve against — no working directory, or no
    round selected — is not an error either. Every listed artifact is missing,
    which is the truth about a project that has not been opened, and the same
    answer ``round_tree_lines`` gives for the same state.
    """
    if not requested:
        return _rejected("")

    # 1 and 2: the requested string, on its own terms. `PurePosixPath` is pure
    # by design — it is the pathlib type that cannot reach a filesystem even by
    # accident, which is exactly what is wanted above the allow-list check.
    pure = PurePosixPath(requested)
    if pure.is_absolute():
        return _rejected(requested)
    if ".." in pure.parts:
        return _rejected(requested)

    # 3: the reviewed table for this round. An exact key match — a path that is
    # merely equivalent (`./stack.json`) is not listed and is not opened.
    entry = allowed_artifacts(working_dir, round_number).get(requested)
    if entry is None:
        return _rejected(requested)

    if not working_dir or round_number is None:
        return _missing(entry)

    # 4: the filesystem, at last.
    base = _resolve(project_manager.get_version_dir(working_dir, round_number))
    target = _resolve(base / requested)
    if not target.is_relative_to(base):
        return _rejected(requested)

    info = _stat(target)
    if info is None or not stat_module.S_ISREG(info.st_mode):
        # Not a regular file: absent, or a directory. `phases/` reaches this
        # when the folder exists but holds nothing, and it is missing rather
        # than present — an empty folder is not a produced artifact, the same
        # judgement `_round_tree._exists` makes about the same directory.
        return _missing(entry)

    return ArtifactResolution(
        RESOLUTION_PRESENT,
        requested,
        entry.lane,
        entry.agent,
        target,
        info.st_size,
        info.st_mtime,
    )


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

# What the pane says about a file the resolver allowed and the filesystem then
# refused to hand over — deleted between the stat and the read, permissions
# changed, a mount gone. Rare, and not an error worth taking the screen down
# for: the tree, the header and the selector are all still true.
UNREADABLE = "could not be read"


def _read(path: Path) -> str | None:
    """The artifact's text, or ``None`` if it cannot be read.

    ``errors="replace"`` rather than a raised ``UnicodeDecodeError``: every
    entry in the reviewed table is a text artifact, but one written by a
    half-finished agent run can hold a truncated multi-byte sequence, and a
    developer looking at a partially written file wants to see how far it got.

    A seam of its own, like ``_stat`` and ``_resolve``, so the tests can assert
    that a rejected request never reaches it.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def rendered_text(path: str, raw: str) -> str:
    """The artifact's text as the pane shows it: JSON pretty-printed, else raw.

    ``.json`` is re-serialised through the stdlib at two-space indent so that a
    round's machine-written artifacts — which agents persist compactly — read
    as structure rather than as one very long line.
    ``ensure_ascii=False`` keeps a feature name written in a non-Latin script
    legible instead of turning it into escape sequences.

    Anything else, Markdown included, is returned exactly as it was written.
    This round adds no Markdown renderer and no syntax highlighter: a phase
    file is a prompt handed to a coding agent verbatim, and the developer
    reading it here is checking the literal text.

    A ``.json`` file that does not parse falls back to its raw text rather than
    raising. A partially written artifact is the ordinary reason for it — an
    agent is mid-persist, or a run died — and that is exactly the moment the
    developer most wants to see the file.
    """
    if not path.endswith(".json"):
        return raw
    try:
        return json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
    except ValueError:
        return raw


def line_numbered(text: str) -> tuple[str, str]:
    """``(gutter, content)`` — two strings with exactly the same line count.

    This is the whole line-numbering implementation, and it is two strings on
    purpose. The obvious version builds a component per line, and on a 4,000
    line artifact that is 8,000 React nodes for Dash to serialise, ship and
    diff on every render — which is the "viewing a very large file makes the
    screen unresponsive" failure mode, arrived at by the most natural route
    there is. Two ``<pre>`` elements are two nodes whatever the file's size,
    and the browser's own text layout does the rest.

    The two are kept in lockstep by construction: the gutter is generated from
    the very lines it numbers, so it cannot be short by one. Their *visual*
    alignment is the other half, and that is one CSS rule (``.file-lines pre``
    in ``v3.css``) setting the font and line height for both — two rules could
    drift by a pixel and slide the numbers off their lines.

    One trailing newline is dropped. ``"a\\nb\\n"`` is two lines, the count
    every editor and every diff agrees on; splitting it naively yields a third,
    empty, numbered line that is not in the file. Any *further* trailing blank
    lines are real content and are kept.
    """
    body = text[:-1] if text.endswith("\n") else text
    count = body.count("\n") + 1
    width = len(str(count))
    gutter = "\n".join(str(n).rjust(width) for n in range(1, count + 1))
    return gutter, body


# ---------------------------------------------------------------------------
# The header
# ---------------------------------------------------------------------------

# Ordered largest first so the first unit the size reaches is the one used.
_SIZE_UNITS: tuple[tuple[str, int], ...] = (
    ("GB", 1024**3),
    ("MB", 1024**2),
    ("KB", 1024),
)


def _fmt_size(size: int) -> str:
    """``512 B`` / ``4.2 KB`` / ``1.3 MB`` — the mock's figure.

    Bytes are exact below a kilobyte because a 0-byte artifact and a 40-byte
    one are different facts, and ``0.0 KB`` hides the difference.
    """
    for unit, scale in _SIZE_UNITS:
        if size >= scale:
            return f"{size / scale:.1f} {unit}"
    return f"{size} B"


def _fmt_modified(mtime: float) -> str:
    """``2026-01-15 09:12`` — local time, to the minute.

    The developer is reading their own filesystem, so local time is the one
    that answers "did that run before or after the edit I just made". Seconds
    are noise at this density.
    """
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


def _round_folder(round_number: int | None) -> str:
    """``.spec4/v3/`` — the same heading the tree above the pane carries."""
    return f".spec4/v{round_number}/" if round_number is not None else ".spec4/"


def _joined(fields: list[Any]) -> list[Any]:
    """The header's fields with the dimmed ``·`` between each pair.

    The separator comes from ``_shared._sep`` — the same helper and the same
    ``.sb-sep`` rule the status bar's context line uses — so the app's two
    one-line mono strips cannot end up with different dots.
    """
    out: list[Any] = []
    for field in fields:
        if out:
            out.append(_sep())
        out.append(field)
    return out


def artifact_header(round_number: int | None, result: ArtifactResolution) -> list[Any]:
    """The one-line header: path, size, last modified, lane — in that order.

    The order is fixed and is the specification's, not a preference: the path
    says which file, the size and the timestamp say whether it is the one the
    last run produced, and the lane says who it is for. It is the same order
    the design mock draws, and it is the order asserted in the tests.

    A **missing** artifact has no size and no timestamp to state, so the two
    metadata fields collapse to the word ``missing`` and the lane still
    follows — the header keeps its shape and every field in it stays true.

    A **rejected** request renders no header at all. The resolution carries no
    lane, no producer and no metadata by design, and echoing back the path that
    was asked for would put an unrecognised string on screen dressed as a fact
    about this round. The body says what happened instead.
    """
    if result.outcome == RESOLUTION_REJECTED:
        return []
    lane = LANE_LABELS.get(result.lane or "", "")
    path = html.Span(f"{_round_folder(round_number)}{result.path}", className="path")
    if result.outcome == RESOLUTION_MISSING:
        return _joined([path, RESOLUTION_MISSING, lane])
    return _joined(
        [
            path,
            _fmt_size(result.size or 0),
            f"modified {_fmt_modified(result.modified or 0.0)}",
            lane,
        ]
    )


# ---------------------------------------------------------------------------
# The body
# ---------------------------------------------------------------------------


def _missing_suffix(agent: str | None) -> str:
    """`` — missing — produced by Deployer``: everything after the path.

    Split from the path so the rendered form can put the filename in its own
    span — the mock draws it brighter than the sentence around it — without
    the sentence being written twice.
    """
    if agent is None:
        return f" — {RESOLUTION_MISSING}"
    return f" — {RESOLUTION_MISSING} — produced by {AGENT_DISPLAY_NAMES[agent]}"


def missing_message(path: str, agent: str | None) -> str:
    """``deployment-plan.md — missing — produced by Deployer``.

    The producing agent is named through ``AGENT_DISPLAY_NAMES`` — the app's
    one pipeline-key-to-name mapping — because the resolver deals in keys
    (``deployer``) and this is the sentence a developer reads. A key with no
    entry there would surface raw, which is why the resolver's tests pin that
    every producer it can name has one.

    ``usage.json`` has no producer at all: every agent appends to it and none
    owns it (D-LR3). The clause is dropped rather than filled with a guess —
    naming an agent that did not write the file would be a plausible lie on the
    one screen built to tell the developer where a file comes from.
    """
    return f"{path}{_missing_suffix(agent)}"


def rejection_message(round_number: int | None) -> str:
    """What the pane says about a path this round does not recognise.

    A statement about the round and an invitation to pick something else, not
    an error and not an accusation. The ordinary way to arrive here is a stale
    selection — a phase file was open and the developer switched to a round
    that never had one, or a bookmarked selection is being restored into a
    different project. Traversal attempts land here too and get the same
    sentence: there is nothing to tell an attacker, and nothing to alarm a
    developer with.
    """
    if round_number is None:
        return "No such artifact."
    return f"No such artifact in v{round_number}."


def _file_block(text: str, path: str) -> Any:
    """The scrolling file block: a gutter ``<pre>`` and a content ``<pre>``.

    Two elements, side by side inside one scroller, so that scrolling the
    content scrolls the numbers with it and a long line scrolls both
    horizontally against a gutter that stays pinned to its own column. See
    :func:`line_numbered` for why this is two strings rather than a component
    per line.
    """
    gutter, content = line_numbered(text)
    return dmc.ScrollArea(
        html.Div(
            [
                html.Pre(gutter, className="file-gutter"),
                html.Pre(content, className="file-content"),
            ],
            className="file-lines",
        ),
        id=SCROLL_ID,
        className="file-block",
        type="auto",
        # The mock labels the block with the file it holds, so a screen reader
        # lands on a named region rather than an unexplained scroller.
        **{"aria-label": path},
    )


def artifact_body(round_number: int | None, result: ArtifactResolution) -> Any:
    """The content pane's body for one resolution.

    Four outcomes, and the file is read in exactly one of them. ``present`` is
    the only branch that reaches the filesystem, and it reaches it through the
    resolved path the resolver handed back — never through the requested
    string, which by then has been checked and superseded.
    """
    if result.outcome == RESOLUTION_REJECTED:
        return html.Div(rejection_message(round_number), className="file-empty mono")
    if result.outcome == RESOLUTION_MISSING:
        return html.Div(
            [
                html.Span(result.path, className="path"),
                _missing_suffix(result.agent),
            ],
            className="file-missing mono",
        )
    assert result.resolved is not None  # `present` carries every field
    raw = _read(result.resolved)
    if raw is None:
        return html.Div(
            [html.Span(result.path, className="path"), f" — {UNREADABLE}"],
            className="file-missing mono",
        )
    return _file_block(rendered_text(result.path, raw), result.path)


def artifact_pane(
    working_dir: str | Path | None,
    round_number: int | None,
    requested: str | None,
) -> tuple[list[Any], Any]:
    """``(header children, body children)`` for one selection. One renderer.

    Both the first paint and the callback that redraws the pane call this, so
    what the screen shows on arrival and what it shows after a round switch are
    the same code rather than two implementations that agree today.

    Nothing selected is not an empty file: the header is blank and the body is
    the pane's own empty state, so the frame on screen is the same shape it
    will be once something is chosen.
    """
    if not requested:
        return [], html.Div(EMPTY_CONTENT, className="file-empty mono")
    result = resolve_artifact(working_dir, round_number, requested)
    return artifact_header(round_number, result), artifact_body(round_number, result)


# ---------------------------------------------------------------------------
# The pane's controls: Download, and — for the mock — Open rendered
# ---------------------------------------------------------------------------


def artifact_controls(result: ArtifactResolution | None) -> Any:
    """Download, always; Open rendered, only for a present ``design/mock.html``.

    Beside the header, not inside it (D-LR2's sibling concern: the header is
    a fact about the file, the controls are actions on it, and folding a
    button into ``artifact_header`` would make ``header == []`` — the shape a
    rejected or empty selection relies on — stop being true the moment a
    control needed to survive that case).

    ``result`` is ``None`` for "nothing selected", which Download must survive
    without disappearing: a control that vanishes and reappears as a file is
    chosen moves under the developer's cursor. It stays on screen and simply
    disables, which is also the treatment a rejected or missing selection
    gets — there is nothing to send in any of the three cases, and the reason
    differs but the button does not need to say which.

    Open rendered is narrower: it is not merely disabled but entirely absent
    for every path but the mock, because there is no "disabled" reading of a
    control that could never apply to the file on screen.

    Neither button names a colour (D-LR2): both are the theme's neutral
    outline, like every other control this screen draws.
    """
    present = result is not None and result.outcome == RESOLUTION_PRESENT
    children: list[Any] = [
        dmc.Button(
            "Download",
            id=DOWNLOAD_BTN_ID,
            variant="outline",
            disabled=not present,
            n_clicks=0,
        )
    ]
    if result is not None and result.path == MOCK_HTML_PATH:
        children.append(
            dmc.Button(
                "Open rendered",
                id=OPEN_RENDERED_BTN_ID,
                variant="outline",
                disabled=not present,
                n_clicks=0,
            )
        )
    return html.Div(children, className="file-controls")


def mock_html_for_store(result: ArtifactResolution | None) -> str:
    """The mock's raw text for the clientside Open-rendered handler, or ``""``.

    Read through the resolver's own ``resolved`` path — the same gate
    ``artifact_body`` reads through for the content pane — never through the
    session-store string directly, so the clientside blob can only ever hold
    text this screen already confirmed it may show. Empty for every outcome
    but a present mock: an empty string is also exactly what the clientside
    handler's own ``!store_data.mock_html`` guard treats as "do nothing", so
    a stale store from a prior selection can never open a stale tab.
    """
    if (
        result is None
        or result.path != MOCK_HTML_PATH
        or result.outcome != RESOLUTION_PRESENT
    ):
        return ""
    assert result.resolved is not None  # `present` carries every field
    return _read(result.resolved) or ""


# ---------------------------------------------------------------------------
# The round selector
# ---------------------------------------------------------------------------


# The ``type`` half of a round button's pattern-matching id, named once so the
# render side (:func:`round_id`) and the callback's Input pattern are the same
# string by construction — the same arrangement the tree's lines use, and for
# the same reason: when the two disagree Dash raises nothing and the control
# simply stops working.
ROUND_TYPE = "artifact-round"


def round_id(round_number: int) -> dict[str, Any]:
    """The pattern-matching id of one round's button."""
    return {"type": ROUND_TYPE, "index": round_number}


def round_value(round_number: int) -> str:
    """A round as the selector labels it: ``v3``."""
    return f"v{round_number}"


def round_number_from_value(value: Any) -> int | None:
    """A selector label back to a round number, or ``None`` if it is not one.

    Defensive on purpose: the value arrives from the browser, and a store
    written by an older build could hold anything at all. Neither is worth an
    exception on a read-only screen.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value.removeprefix("v"))
        except ValueError:
            return None
    return None


def selected_round(
    working_dir: str | Path | None, session: dict[str, Any]
) -> int | None:
    """The round this screen is showing: the session's choice, or the active one.

    The session's ``selected_round`` wins only while it names a round that is
    actually on disk. A round can be deleted, and a session store survives the
    project it was written against, so a selection that no longer resolves
    falls back to the active round rather than drawing a tree of nothing and a
    selector with no value.

    Read from disk on every call, through ``rounds_on_disk``, which is the
    stale-round-list mitigation: there is no cached list here to go out of date
    and nothing to invalidate when a run creates a round.
    """
    rounds, active = project_manager.rounds_on_disk(working_dir, session)
    chosen = session.get("selected_round")
    if isinstance(chosen, int) and not isinstance(chosen, bool) and chosen in rounds:
        return chosen
    return active


def _round_select(
    working_dir: str | Path | None,
    session: dict[str, Any],
    round_number: int | None,
) -> Any:
    """Every round on disk as one strip of controls, the current one marked.

    The list is rebuilt here on every render rather than read from a store, so
    a round created since the last visit is simply there the next time the
    screen draws — the mitigation the stale-round-list failure mode asks for.

    **Why buttons and not a ``dmc.Select``.** Choosing a round writes the
    session, and every session write rebuilds the page (``render_page``). A
    Mantine ``Select`` does not survive that: after the page has been rebuilt
    once, the next selection is re-asserted back to the value the rebuild gave
    it, and the write that the selection triggered is dropped as stale. The
    screen then sticks on one round with nothing logged anywhere. A button has
    ``n_clicks``, which is monotonic and survives a remount — the same property
    the round tree's own lines rely on, and the reason its links work across
    the very same rebuilds. The design mock draws this control as a strip of
    round links rather than a dropdown, so the robust option is also the one
    the design asks for.

    ``ROUND_SELECT_ID`` stays on the strip itself, which is the element the
    mock gives that id and the one a test looks for.

    No ``color`` prop and no ``style`` (D-LR2): the current round takes the
    theme primary through the ``is-active`` class, exactly as the header nav's
    current entry does.
    """
    rounds, _ = project_manager.rounds_on_disk(working_dir, session)
    return html.Div(
        [
            html.Button(
                round_value(number),
                id=round_id(number),
                n_clicks=0,
                className="is-active" if number == round_number else "",
                title=f"Show {round_value(number)}",
                **(
                    {"aria-current": "true"}  # type: ignore[arg-type]
                    if number == round_number
                    else {}
                ),
            )
            for number in rounds
        ],
        id=ROUND_SELECT_ID,
        className="round-select mono",
        **{"aria-label": "Round"},  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# The screen
# ---------------------------------------------------------------------------


def _artifact_view_layout(session: dict[str, Any]) -> html.Div:
    """The Artifact View screen: a selector pane and a content pane.

    The left pane is the round selector above the app's round tree, drawn in
    its linked form with the current file marked. It is the *same* tree the
    project view draws — one renderer, called with different arguments — so the
    two screens cannot disagree about a lane or a status. It carries its own
    ids (``ARTIFACT_TREE_IDS``); see :class:`~spec4.layouts._round_tree.TreeIds`
    for why sharing the project view's would let that screen's callback write
    the wrong round's files into this one.

    The right pane is the one-line header and the content body, both filled
    here on the first paint and refilled by ``on_artifact_pane`` afterwards,
    through the same :func:`artifact_pane` call.

    Everything on this screen is recomputed from disk on every render. There is
    no cache and no ``dcc.Store`` behind any of it (D-LR4), which is what makes
    the screen true about a round that an agent changed a moment ago.
    """
    session = session or {}
    working_dir = session.get("working_dir")
    round_number = selected_round(working_dir, session)
    requested = session.get("selected_file")
    header, body = artifact_pane(working_dir, round_number, requested)
    # A second resolve, deliberately: the controls and the mock-html store
    # need the outcome itself (present / missing / rejected), which
    # `artifact_pane` computes but does not hand back, and this module has no
    # cache for either call to share (D-LR4).
    result = (
        resolve_artifact(working_dir, round_number, requested) if requested else None
    )
    return html.Div(
        [
            html.Aside(
                [
                    _round_select(working_dir, session, round_number),
                    _round_tree(
                        working_dir,
                        round_number,
                        linked=True,
                        selected=requested,
                        ids=ARTIFACT_TREE_IDS,
                    ),
                ],
                id="artifact-view-sidebar",
                # Dash passes unknown props straight through to the DOM; its
                # stubs only know the documented ones, hence the ignore for a
                # plain accessibility attribute the design mock also carries.
                **{"aria-label": "Rounds and artifacts"},  # type: ignore[arg-type]
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(header, id=HEADER_ID, className="file-meta mono"),
                            artifact_controls(result),
                        ],
                        className="file-head",
                    ),
                    html.Div(body, id=BODY_ID),
                    dcc.Store(
                        id=MOCK_STORE_ID,
                        data={"mock_html": mock_html_for_store(result)},
                    ),
                    dcc.Download(id=DOWNLOAD_ID),
                ],
                id="artifact-view-content",
            ),
        ],
        id="artifact-view-root",
        className="artifact-layout",
    )
