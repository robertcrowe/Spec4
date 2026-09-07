from __future__ import annotations

from typing import Any

from dash import dcc, html
import dash_mantine_components as dmc

from spec4 import project_manager
from spec4.app_constants import (
    AGENT_KEYS,
    STATE_AGENTIFIER_COMPLETE,
    STATE_DEPLOYER_COMPLETE,
    STATE_PHASES_COMPLETE,
    STATE_REVIEW_COMPLETE,
    STATE_STACK_COMPLETE,
    STATE_VISION_COMPLETE,
)
from spec4.agentifier.panel_closure import close_selection, pool_from_dicts
from spec4.layouts import _llm_gate
from spec4.layouts._agent_rows import AGENT_DISPLAY_NAMES
from spec4.layouts._round_cost import run_cost_strip
from spec4.layouts._round_tree import PHASES_DIR
from spec4.layouts._shared import PROGRESS_CLASS_NAMES, _render_message
from spec4.session import _validate_agent_preconditions

# The pipeline indicator's four states, as the modifier classes `v3.css`
# draws. The active one takes the theme primary through its class exactly as
# the header nav's active link does (`.sb-nav-link--active`), so the accent is
# reached the one way D-LR2 allows and a re-themed accent moves both at once.
# Every scrap of button chrome is stripped in the stylesheet, for the same
# reason `.sb-dir` and the tree's lines strip theirs: these have to read as
# seven plain labels, not as seven buttons.
_PILL_BASE = "pipeline-agent"
_PILL_ACTIVE = "pipeline-agent--active"
_PILL_DONE = "pipeline-agent--done"
_PILL_UNREACHABLE = "pipeline-agent--unreachable"


def _completed_agents(session: dict[str, Any]) -> dict[str, bool]:
    """Which pipeline agents have already produced their artifact.

    Keyed by the same agent keys ``AGENT_KEYS`` names, so the pill bar can walk
    that tuple and ask this for each entry rather than carrying a second list
    of agents in its own order.

    Designer is the one agent whose completion is not a session flag: it writes
    `design/mock.html` and nothing else records that it ran, so the file's
    existence is the state.
    """
    working_dir = session.get("working_dir", "")
    mock = (
        project_manager.get_version_dir(
            working_dir, project_manager.active_version(working_dir, session)
        )
        / "design"
        / "mock.html"
        if working_dir
        else None
    )
    return {
        "code_scanner": session.get("code_review") is not None,
        "brainstormer": session.get("vision_statement") is not None,
        "agentifier": session.get("agentifier_state") == STATE_AGENTIFIER_COMPLETE,
        "designer": bool(mock and mock.exists()),
        "stack_advisor": session.get("stack_statement") is not None,
        "phaser": session.get("phaser_state") == STATE_PHASES_COMPLETE,
        "deployer": session.get("deployer_state") == STATE_DEPLOYER_COMPLETE,
    }


def _agent_status_bar(session: dict[str, Any]) -> html.Div:
    """The pipeline indicator: seven plain labels, in order, no connectors.

    The order is ``AGENT_KEYS`` itself rather than a list restated here — a
    stage added to the pipeline appears in this bar without anyone editing it,
    and the bar cannot drift from the rows on /agents that walk the same tuple.

    Three states, and the arrows between them are gone: the labels are already
    in pipeline order, so a connector said nothing the sequence did not. The
    active agent is a `<span>` because clicking it would navigate to where the
    developer already is; every other agent keeps the `agent-pill` pattern id
    it has always had, so routing is `on_agent_pill_click` untouched.
    """
    active = session.get("active_agent", "brainstormer")
    done = _completed_agents(session)
    items: list[Any] = []
    for key in AGENT_KEYS:
        label = AGENT_DISPLAY_NAMES[key]
        if key == active:
            items.append(html.Span(label, className=f"{_PILL_BASE} {_PILL_ACTIVE}"))
            continue
        blocked = _validate_agent_preconditions(key, session)
        classes = [_PILL_BASE]
        if blocked is not None:
            classes.append(_PILL_UNREACHABLE)
        elif done.get(key):
            classes.append(_PILL_DONE)
        items.append(
            html.Button(
                label,
                id={"type": "agent-pill", "agent": key},
                n_clicks=0,
                disabled=blocked is not None,
                # Unchanged: the precondition message is the tooltip, and it is
                # the only explanation a dimmed label carries.
                title=blocked,
                className=" ".join(classes),
            )
        )
    return html.Div(
        [
            # D-LR8: the pipeline is the whole bar. A `← Back` button stood
            # to its right and went to `/agents`; the status bar's Project
            # link is that same route, mounted in the app shell, so this was
            # the one control in the app whose destination already had a
            # permanent second door. The full reachability walk behind the
            # four Back removals is recorded at `_chat_action_buttons` below.
            #
            # `mt` on the divider is what the retired Group's `mb` was doing:
            # `.pipeline` draws its own bottom rule, and without the gap the
            # two lines would sit 1px apart.
            html.Div(items, className="pipeline"),
            dmc.Divider(mt="sm", mb="md"),
        ]
    )


# When a chat agent's run is complete: the same predicates the action row and
# the status bar use, so the cost card appears exactly when the Download /
# Continue buttons do. Designer is not here — it has no chat turn; its card
# renders on the mock preview step (layouts.designer).
_RUN_COMPLETE: dict[str, tuple[str, str]] = {
    "code_scanner": ("code_scanner_state", STATE_REVIEW_COMPLETE),
    "brainstormer": ("brainstormer_state", STATE_VISION_COMPLETE),
    "agentifier": ("agentifier_state", STATE_AGENTIFIER_COMPLETE),
    "stack_advisor": ("stack_advisor_state", STATE_STACK_COMPLETE),
    "phaser": ("phaser_state", STATE_PHASES_COMPLETE),
    "deployer": ("deployer_state", STATE_DEPLOYER_COMPLETE),
}

def _cost_summary(session: dict[str, Any]) -> Any | None:
    """The cost strip for the active agent, on the turn that ended its run.

    The strip itself is ``_round_cost.run_cost_strip`` — the same three-line
    renderer the project view closes with, handed this run's figures instead
    of the round's. Sourcing both from one renderer is the mitigation for the
    chat frame's "the completion cost strip fails to match the round-cost
    presentation" failure mode: there is no second wording to drift.

    What is decided *here* is only whether a run has ended. Two gates, both
    needed. The completion state says the agent has produced its artifact at
    some point; on a Modify run of a completed agent that state stays set
    through every conversational turn, so on its own it put the strip after
    each step. The artifact stamp (``<agent>_artifact_msg_count``, written by
    every agent at the moment it emits its artifact — the same signal the
    resume helper reads) says the artifact is the *last* message: chatting
    past it grows the history and the strip leaves; re-emitting it stamps the
    new length and the strip returns. Never mid-stream.
    """
    if session.get("_stream_id"):
        return None
    # `or ""` rather than a cast: the lookup below is what narrows this to a
    # real agent key — a session with no active agent, or one naming Designer
    # (which has no chat turn), misses `_RUN_COMPLETE` and leaves here.
    active: str = session.get("active_agent") or ""
    gate = _RUN_COMPLETE.get(active)
    if gate is None or session.get(gate[0]) != gate[1]:
        return None
    history = session.get(f"{active}_messages") or []
    stamp = session.get(f"{active}_artifact_msg_count")
    if isinstance(stamp, bool) or not isinstance(stamp, int) or stamp != len(history):
        return None
    return run_cost_strip(session.get("working_dir"), session, active)


_TOKEN_COUNTER_AGENTS = (
    "code_scanner",
    "brainstormer",
    "agentifier",
    "stack_advisor",
    "phaser",
    "deployer",
)


def _streamed_token_count(session: dict[str, Any]) -> int:
    """Characters received so far, used as a token-count proxy.

    D-PH9: during the phaser validation-retry drain the visible assistant
    message stops growing (the retry body is swallowed), so the length of the
    displayed message freezes. When the generator has published a cumulative
    received-character total, prefer it so the counter tracks real receipt;
    otherwise fall back to the in-flight assistant message length.
    """
    received = session.get("_stream_received_chars")
    if isinstance(received, int):
        return received
    messages = session.get("messages") or []
    if not messages:
        return 0
    last = messages[-1]
    if last.get("role") != "assistant":
        return 0
    return len(last.get("content") or "")


def _token_count_text(session: dict[str, Any]) -> str:
    """Render text for the chars counter, or empty when it shouldn't show."""
    if session.get("active_agent") not in _TOKEN_COUNTER_AGENTS:
        return ""
    if not session.get("_stream_id") and _streamed_token_count(session) == 0:
        return ""
    return f"Chars received: {_streamed_token_count(session)}"


# Two distinct silences, told apart on screen. "no token count" means calls
# were made and the provider reported nothing for them; "no calls recorded"
# means the turn ended without a single captured call — either a genuinely
# call-free turn or a break in the capture path. Neither renders as blank
# space: a missing element is indistinguishable from a bug, which is how a
# double-drain of the usage sink once hid in plain sight.
_NO_TOKEN_COUNT = "no token count"
_NO_CALLS_RECORDED = "no calls recorded"


def _turn_token_text(session: dict[str, Any]) -> str:
    """Token readout for the turn that just finished, or empty.

    Fed by ``session["_turn_usage"]``, which the persist funnel writes from
    the provider-reported usage of the finished turn's calls. Shows only once
    the stream has completed and only for the agent that ran it; while a
    turn streams there is nothing to show, because usage arrives with the
    end of each call and nothing here is estimated from characters. A turn
    whose calls all came back without usage shows a marker instead of a zero,
    and so does a turn that recorded no calls at all. A turn where only some
    calls reported usage shows the counted part, flagged as partial.
    """
    if session.get("_stream_id"):
        return ""
    usage = session.get("_turn_usage")
    if not isinstance(usage, dict) or usage.get("agent") != session.get("active_agent"):
        return ""
    calls = int(usage.get("calls") or 0)
    missing = int(usage.get("missing") or 0)
    if calls == 0:
        return _NO_CALLS_RECORDED
    if missing >= calls:
        return _NO_TOKEN_COUNT
    text = (
        f"Tokens: {int(usage.get('input') or 0):,} in / "
        f"{int(usage.get('output') or 0):,} out"
    )
    return f"{text} (partial)" if missing else text


# ---------------------------------------------------------------------------
# Downloadable artifacts, and the Open control beside each Download
# ---------------------------------------------------------------------------

# The action row's downloadable artifacts, keyed by the suffix the row's
# existing Download button already carries: `btn-dl-vision` downloads
# `vision.json`, so `btn-open-vision` opens it. Keying it that way is what
# makes the pairing checkable — `tests/test_chat_open_links.py` walks every
# row the frame can draw and fails if a Download has no Open beside it — and
# it is why no existing id is renamed here.
#
# The paths are the round tree's, not a second list: every value is a path
# `_round_tree.ROUND_ARTIFACTS` lists, which is what makes an Open button land
# on a file the Artifact View will actually resolve. The design mock's own
# sample data misfiles `deployment-plan.md`, so the tree's reviewed table is
# the only table this may be built from, and the pairing test checks it.
CHAT_ARTIFACTS: dict[str, str] = {
    "review": "code_review.json",
    "vision": "vision.json",
    "features": "ai_features.json",
    "stack": "stack.json",
    "phases": PHASES_DIR,
    "deployment": "deployment-plan.md",
}

# The two id prefixes, named once so the render side and the click callbacks
# are the same strings by construction rather than by two people typing them.
DOWNLOAD_BTN_PREFIX = "btn-dl-"
OPEN_BTN_PREFIX = "btn-open-"


def download_button_id(key: str) -> str:
    return f"{DOWNLOAD_BTN_PREFIX}{key}"


def open_button_id(key: str) -> str:
    return f"{OPEN_BTN_PREFIX}{key}"


def _open_button(key: str) -> Any:
    """``Open <path>`` for one artifact, as a neutral outline.

    A bare ``variant="outline"`` and no ``color`` (D-LR2): the row already has
    its one emphasis — the continue at the end — and an Open that named a
    colour would be a second thing shouting in a row whose whole rule is that
    only one thing does.

    The label names the file rather than saying "Open", because the row can
    carry two artifact controls at once and "Open" beside "Download
    vision.json" reads as an ambiguity the mock does not have.
    """
    return dmc.Button(
        f"Open {CHAT_ARTIFACTS[key]}",
        id=open_button_id(key),
        variant="outline",
    )


def _ff_controls(agent_label: str) -> list[Any]:
    """Fast Forward button, (i) icon, and info dialog for one agent.

    The same component ids serve every agent because only the active agent's
    buttons render at a time; ``on_fast_forward`` routes via ``active_agent``
    in session, so extending FF to an agent is purely a layout change.
    """
    return [
        dmc.Button(
            "Fast Forward",
            id="btn-chat-fast-forward",
            variant="outline",
        ),
        dmc.Button(
            "About Fast Forward",
            id="btn-ff-info",
            variant="subtle",
            size="sm",
            color="gray",
        ),
        dmc.Modal(
            dmc.Text(
                f"Fast Forward asks {agent_label} to work through all "
                "remaining topics on its own, adopting its best "
                "recommendation for each instead of pausing to ask "
                "you topic by topic. Before anything is finalized, "
                "the complete set of recommendations is presented "
                "for your review, and you can still change any of "
                "them.",
                size="sm",
            ),
            id="ff-info-modal",
            title="What does Fast Forward do?",
            opened=False,
        ),
    ]


# The emphasis rule this row is built to, from the design manifest's Action
# Row entry: the continue action is the only filled button, everything else is
# a neutral outline, and Re-scan carries the warn tone. Neutral is a bare
# `variant="outline"` with no `color` — per D-AR1 that takes the theme primary
# and washes to near-white in this dark scheme, which is the mock's
# `.btn-outline`. The one green thing per row is therefore reached by omitting
# `variant` entirely, and no button here names a colour that is not a
# semantic (D-LR2).
#
# D-LR8, the reachability walk that let the four Back controls go. They are
# named by their labels rather than their ids because the ids are meant to be
# ungreppable now — that grep returning nothing is how the removal is checked.
# Each state they served, and what serves it now:
#
#   1. `← Back`, in the pill bar of every agent → `/agents`. The status bar's
#      Project link is the same route and is mounted in the app shell, so it
#      is present on every one of these screens rather than on the chat frame
#      alone.
#   2. `← Back to Designer`, StackAdvisor → `phase="designer"`. The Designer
#      pill routes there (`on_agent_pill_click`), and it is never disabled
#      from here: Designer's only precondition is a vision, which StackAdvisor
#      also requires, so reaching this screen at all guarantees the pill is
#      live.
#   3. `← Back to Stack Advisor`, Phaser → StackAdvisor. The StackAdvisor pill
#      switches to the same agent. StackAdvisor is deliberately ungated in
#      `_validate_agent_preconditions` (D-SC5c), so the pill cannot be the
#      disabled one.
#   4. `← Back to Phaser`, Deployer → Phaser. The Phaser pill covers it, with
#      one gap: Phaser is blocked while the mock is stale
#      (`detect_stale_inputs`), where the button switched regardless. Not a
#      strand — the Project link reaches `/agents`, where `agent_button_state`
#      is a separate authority that renders Phaser enabled and needing an
#      update (the divergence D-BB1 already names).
#
# Two of the pill routes also send an unconnected session to `/setup` instead
# of switching. That is the entry check in `on_agent_pill_click`, and it is a
# fix rather than a loss: a session with no connection cannot run the turn the
# Back button would have landed on.
def _chat_action_buttons(session: dict[str, Any]) -> html.Div:
    active = session.get("active_agent")
    buttons = []

    if active == "code_scanner":
        token_counter = dmc.Text(
            _token_count_text(session),
            id="chat-token-count",
            className="mono",
            size="sm",
        )
        if session.get("code_scanner_state") == STATE_REVIEW_COMPLETE:
            buttons = [
                token_counter,
                _open_button("review"),
                dmc.Button(
                    "Download code_review.json",
                    id="btn-dl-review",
                    variant="outline",
                ),
                dmc.Button(
                    "Re-scan Project",
                    id="btn-rescan-project",
                    variant="outline",
                    # The warn tone the agent rows already define for Needs
                    # Update, not a second warn of this row's own: same
                    # `color="yellow"`, same `.btn-warn` weight in `v3.css`,
                    # because Mantine's yellow outline washes out to the same
                    # near-white as the neutral buttons beside it.
                    color="yellow",
                    className="btn-warn",
                ),
                dmc.Button(
                    "Continue to Brainstormer →", id="btn-review-to-brainstormer"
                ),
            ]
        elif _token_count_text(session):
            # Mid-scan CodeScanner has no other controls, so the bar exists
            # only to carry the counter — render it only once there is a count
            # to show, otherwise the divider would sit above an empty row.
            buttons = [token_counter]
        else:
            buttons = []
    elif active == "brainstormer":
        token_counter = dmc.Text(
            _token_count_text(session),
            id="chat-token-count",
            className="mono",
            size="sm",
        )
        if session.get("brainstormer_state") == STATE_VISION_COMPLETE:
            buttons = [
                token_counter,
                _open_button("vision"),
                dmc.Button(
                    "Download vision.json", id="btn-dl-vision", variant="outline"
                ),
                dmc.Button(
                    # The skip, drawn as the same neutral outline as Download
                    # beside it — the mock gives both `.btn-outline`, and the
                    # filled one in this row is the continue below.
                    "Continue to Designer →",
                    id="btn-brainstormer-to-designer",
                    variant="outline",
                ),
                dmc.Button(
                    "Continue to Agentifier →", id="btn-brainstormer-to-agentifier"
                ),
            ]
        elif _token_count_text(session):
            # Like mid-scan CodeScanner, Brainstormer has no other controls
            # before the vision lands, so the bar exists only to carry the
            # counter — render it once there is a count, not before, or the
            # divider would sit above an empty row.
            buttons = [token_counter]
        else:
            buttons = []
    elif active == "agentifier":
        token_counter = dmc.Text(
            _token_count_text(session),
            id="chat-token-count",
            className="mono",
            size="sm",
        )
        if session.get("agentifier_state") == STATE_AGENTIFIER_COMPLETE:
            buttons = [
                token_counter,
                _open_button("features"),
                dmc.Button(
                    "Download ai_features.json",
                    id="btn-dl-features",
                    variant="outline",
                ),
                dmc.Button(
                    "Continue to Designer →",
                    id="btn-agentifier-to-designer",
                ),
            ]
        elif session.get("agentifier_breadth_chosen") or session.get(
            "agentifier_catalog_done"
        ):
            # Fast Forward only after the breadth panel has completed: the
            # pre-panel catalog build has nothing to sweep, and the panel
            # itself is a hard UI stop. catalog_done covers resumed sessions
            # that load past the panel without replaying it.
            buttons = [token_counter, *_ff_controls("Agentifier")]
        elif session.get("_stream_id"):
            # Any live Agentifier stream gets the counter. Two cases land here:
            # the first post-panel turn (D-AT2 — agentifier_breadth_chosen is
            # set by the generator, but mid-stream the poll merges only
            # messages and the char total, so the flag does not reach the
            # layout until the turn ends), and the pre-panel build or Try
            # Again redraw (D-AT5, revised — the Scout banner points the
            # developer at "the character counter below", and Scout, Linker
            # and Composer all publish live totals through _session_counter,
            # so the gate that kept this bare was the only missing piece).
            # Counter only — the Fast Forward gate above is unchanged.
            buttons = [token_counter]
        else:
            buttons = []
    elif active == "stack_advisor":
        token_counter = dmc.Text(
            _token_count_text(session),
            id="chat-token-count",
            className="mono",
            size="sm",
        )
        if session.get("stack_advisor_state") == STATE_STACK_COMPLETE:
            buttons = [
                token_counter,
                _open_button("stack"),
                dmc.Button(
                    "Download stack.json", id="btn-dl-stack", variant="outline"
                ),
                dmc.Button("Send to Phaser →", id="btn-stack-to-phaser"),
            ]
        else:
            buttons = [token_counter, *_ff_controls("StackAdvisor")]
    elif active == "phaser":
        token_counter = dmc.Text(
            _token_count_text(session),
            id="chat-token-count",
            className="mono",
            size="sm",
        )
        if session.get("phases"):
            buttons = [
                token_counter,
                _open_button("phases"),
                dmc.Button(
                    "Download phases.zip", id="btn-dl-phases", variant="outline"
                ),
                dmc.Button("Continue to Deployer →", id="btn-phaser-to-deployer"),
            ]
        else:
            buttons = [token_counter, *_ff_controls("Phaser")]
    elif active == "deployer":
        token_counter = dmc.Text(
            _token_count_text(session),
            id="chat-token-count",
            className="mono",
            size="sm",
        )
        if session.get("deployer_state") == STATE_DEPLOYER_COMPLETE:
            buttons = [
                token_counter,
                _open_button("deployment"),
                dmc.Button(
                    "Download deployment plan (Markdown)",
                    id="btn-dl-deployment",
                    variant="outline",
                ),
                # The last row in the pipeline has no next agent, so Start New
                # Project *is* its continue — the one filled button, reached
                # by omitting `variant` like every other continue. It was a
                # `light` chip, which left the terminal row the only completed
                # row on the screen with nothing emphasised in it.
                dmc.Button("Start New Project", id="btn-deployer-new-project"),
            ]
        else:
            buttons = [token_counter, *_ff_controls("Deployer")]

    # D-SC-P2: the elapsed readout shares this row with the chars counter
    # instead of sitting under the progress bar. The two describe the same
    # in-flight turn and read as a pair, so it goes immediately after the
    # counter when there is one — otherwise a Fast Forward button lands between
    # them. Its text is always empty here; the client-side ticker owns it for
    # the life of the stream (see the ticker in app.py).
    # `size="sm"` matches the chars counter: the two sit side by side now, and
    # the xs it carried under the progress bar read as a footnote next to it.
    elapsed = dmc.Text("", id="chat-elapsed", className="mono", size="sm")
    if not buttons and not session.get("_stream_id"):
        return html.Div()
    # A live stream renders the row even when the agent contributes no buttons
    # (pre-panel Agentifier, D-AT5), so the elapsed readout is never homeless
    # mid-turn — the same guarantee it had inside the progress container.
    row = list(buttons)
    counter_at = next(
        (
            i
            for i, b in enumerate(row)
            if getattr(b, "id", None) == "chat-token-count"
        ),
        None,
    )
    row.insert(len(row) if counter_at is None else counter_at + 1, elapsed)
    # The finished turn's token readout sits right after the chars counter it
    # describes. Rendered only when there is something to say (post-stream,
    # usage captured or known-missing) so the live row is untouched.
    turn_tokens = _turn_token_text(session)
    if turn_tokens and counter_at is not None:
        row.insert(
            counter_at + 1,
            dmc.Text(turn_tokens, id="chat-turn-tokens", className="mono", size="sm"),
        )
    return html.Div(
        [
            dmc.Divider(mb="xs"),
            dmc.Group(row, mb="md"),
        ]
    )


def _retry_panel(session: dict[str, Any]) -> Any | None:
    """Recovery affordance for a turn that died on a provider error (D-ER1).

    Renders only once the failed stream has been finalised — mid-stream the
    progress bar owns the space, and a retry button there would compete with a
    turn that may still succeed. Returns None when there is nothing to recover
    so the caller can omit it from the tree.

    The wording is deliberately concrete about what is and isn't lost: provider
    overloads are transient and the same request usually succeeds on a second
    attempt, but the user has no way to know that from the exception text alone.
    """
    if not session.get("_stream_error") or session.get("_stream_id"):
        return None
    # The panel retries the assistant turn at the end of the transcript, so it
    # only makes sense while that turn is still on screen. This also makes the
    # panel immune to a flag that outlived its turn: every path that starts the
    # chat over (agent switch, re-scan, skip-into-agent) empties `messages`, so
    # a leftover flag renders nothing regardless of who forgot to clear it.
    messages = session.get("messages") or []
    if not messages or messages[-1].get("role") != "assistant":
        return None
    return dmc.Alert(
        [
            dmc.Text(
                "That request didn't complete. Nothing already saved is lost. "
                "An overload or rate limit is usually temporary, so running "
                "the same step again often works — but a provider that is "
                "unreachable, a key that was rejected, or a model that cannot "
                "do this step will fail the same way every time. For those, "
                "choose a different provider or model and the step re-runs "
                "on it straight away.",
                size="sm",
                mb="sm",
            ),
            dmc.Group(
                [
                    dmc.Button(
                        "↺ Try Again",
                        id="btn-chat-retry",
                        variant="outline",
                        color="orange",
                        size="sm",
                    ),
                    dmc.Button(
                        "↺ Try a different provider/model",
                        id="btn-chat-retry-model",
                        variant="outline",
                        color="orange",
                        size="sm",
                    ),
                ],
                gap="sm",
            ),
        ],
        title="The last step failed",
        color="orange",
        variant="light",
        mb="md",
    )


def _breadth_panel(session: dict[str, Any]) -> Any | None:
    """Checkbox panel for Agentifier breadth selection.

    Renders only when agentifier_breadth_groups is set and the user has not yet
    submitted their selection. Returns None when inactive so the caller can
    omit it from the component tree.
    """
    candidates: list[dict[str, str]] | None = session.get(
        "agentifier_breadth_groups"
    )
    if not candidates:
        return None
    if session.get("agentifier_breadth_chosen"):
        return None
    if session.get("_stream_id"):
        # The selection has just been submitted and a stream is running. Hide
        # the panel immediately on Continue instead of waiting for the backend
        # to flip agentifier_breadth_chosen mid-stream.
        return None

    # First paint already reflects panel closure: pre-checked features (the
    # reselection path seeds these) pull in their producers and turn on their
    # coordinators, and the derived/required set is locked. The live callback
    # keeps this in sync as the developer toggles.
    pool = pool_from_dicts(session.get("agentifier_scout_pool") or [])
    closure = close_selection(pool, session.get("agentifier_breadth_selection") or [])
    locked = closure.locked

    # One flat list — there is no relevance ranking to band on, so candidates
    # appear in pool (Composer) order.
    checkboxes: list[Any] = [
        dmc.Checkbox(
            id={"type": "breadth-cb", "name": item["name"]},
            value=item["name"],
            label=html.Strong(item["name"]),
            description=item.get("description", ""),
            disabled=item["name"] in locked,
            # Name and description both render as ordinary chat text:
            # chat-text size (md matches the unstyled Markdown body) and
            # the bubble's own colour, picked up via `inherit` from the
            # enclosing .chat-bubble-assistant so the two never drift.
            # `inherit` also keeps an auto-selected (disabled) candidate
            # readable — the disabled state greys label/description via a
            # zero-specificity rule that these inline styles override, so
            # only the checkbox box shows the disabled cue. The name's
            # weight comes from the <strong> wrapper on the label; the
            # description pins 400 rather than inheriting, since it sits
            # inside the same <label> element and would otherwise pick up
            # whatever weight the cascade lands on.
            styles={
                "label": {
                    "fontSize": "var(--mantine-font-size-md)",
                    "color": "inherit",
                },
                "description": {
                    "fontSize": "var(--mantine-font-size-md)",
                    "fontWeight": 400,
                    "color": "inherit",
                },
            },
            mb="xs",
        )
        for item in candidates
    ]

    return dmc.Paper(
        [
            dmc.CheckboxGroup(
                id="breadth-checkbox-group",
                value=sorted(closure.selected),
                children=checkboxes,
                mb="md",
            ),
            dmc.Group(
                [dmc.Button("Next Step", id="btn-breadth-submit")],
                justify="center",
                mb="md",
            ),
            # Guided redraw (D-TA7). The note is optional: a blank box with Try
            # Again is the plain redraw it always was. Text typed here reaches
            # Scout (and, after Continue, the Tier Analyst) via
            # session["agentifier_retry_guidance"]; see on_breadth_try_again.
            # The main chat-input row is hidden while this panel is up, so this
            # is the only text box on screen. Typed text survives checkbox
            # toggles because on_breadth_change never re-renders the layout.
            # The label lives outside the Textarea (rather than its `label`
            # prop) so the row below can stretch Try Again to the field's
            # height alone, exactly as the Send button matches chat-input —
            # same flex row, same stretch rule in v3.css.
            html.Label(
                "Tell me what to change (optional)",
                htmlFor="breadth-retry-input",
                style={
                    "display": "block",
                    "fontSize": "var(--mantine-font-size-sm)",
                    "fontWeight": 500,
                    "marginBottom": "calc(var(--mantine-spacing-xs) / 2)",
                },
            ),
            html.Div(
                [
                    dmc.Textarea(
                        id="breadth-retry-input",
                        placeholder=(
                            "e.g. Too many — keep only the 3 that matter most "
                            "for the MVP, and prefer simpler approaches."
                        ),
                        autosize=True,
                        minRows=2,
                        style={"flex": "1"},
                    ),
                    dmc.Button(
                        "↺ Try Again",
                        id="btn-breadth-try-again",
                        variant="outline",
                        color="gray",
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "stretch",
                    "gap": "var(--mantine-spacing-sm)",
                    "width": "100%",
                },
            ),
        ],
        p="md",
        radius="md",
        className="chat-bubble-assistant",
        mb="md",
    )


def _chat_layout(
    session: dict[str, Any], prefs: dict[str, Any] | None = None
) -> html.Div:
    messages = session.get("messages", [])
    active = session.get("active_agent", "brainstormer")
    # The model gate stands between entering an agent and its opening turn. The
    # interval below stays mounted while it is open — `on_init_turn` takes it as
    # an Input, so the component has to exist — but disabled, so the turn cannot
    # start until the choice is made.
    gate_open = _llm_gate.is_open(session, active)
    needs_init = (
        not messages and not session.get("_initial_turn_done") and not gate_open
    )
    # The one-word label above each assistant block. The agent naming itself
    # is what tells the two speakers apart now that neither block is filled.
    speaker = AGENT_DISPLAY_NAMES.get(active, "Agent")
    breadth_panel = _breadth_panel(session)
    retry_panel = _retry_panel(session)
    cost_card = _cost_summary(session)
    # Mid-agent, the chip re-opens the same card. `agent_llm_draft` marks it
    # open; a resting chip renders nothing extra.
    chip_open = bool(
        not gate_open and (session.get("agent_llm_draft") or {}).get("agent") == active
    )
    gate = (
        _llm_gate.gate_card(session, prefs, active)
        if gate_open or chip_open
        else None
    )

    return html.Div(
        [
            # Trigger initial agent turn once on first render.
            # max_intervals=0 disables the interval (never fires) when not needed,
            # but keeps n_intervals available as a callback input.
            dcc.Interval(
                id="init-turn-interval",
                interval=300,
                max_intervals=1 if needs_init else 0,
            ),
            # Always-present download triggers (invisible)
            dcc.Download(id="dl-vision"),
            dcc.Download(id="dl-stack"),
            dcc.Download(id="dl-code-review"),
            dcc.Download(id="dl-phases"),
            dcc.Download(id="dl-deployment"),
            dcc.Download(id="dl-features"),
            _agent_status_bar(session),
            *([gate] if gate is not None else []),
            html.Div(
                html.Div(
                    [_render_message(m, speaker) for m in messages]
                    + (
                        [dmc.Text("Thinking…", c="dimmed", size="sm")]
                        if needs_init
                        else []
                    ),
                    style={"display": "flex", "flexDirection": "column"},
                ),
                id="chat-scroll-area",
                # Height and scrolling are in `v3.css` (60vh, `overflow-y:
                # auto`) rather than here: an inline height would win over the
                # stylesheet, and the whole point of the viewport-relative
                # value is that it answers to the window rather than to a
                # number written into the layout.
                style={
                    # Tight against the action row below: the divider that opens
                    # that row already reads as the separator, so md here just
                    # stranded the buttons.
                    "marginBottom": "var(--mantine-spacing-xs)",
                },
            ),
            # The run's cost, under its last message and above the row that
            # moves on from it. Renders only once the run is complete.
            *([cost_card] if cost_card is not None else []),
            _chat_action_buttons(session),
            *([retry_panel] if retry_panel is not None else []),
            *([breadth_panel] if breadth_panel is not None else []),
            html.Div(
                [
                    dmc.Progress(
                        value=100,
                        animated=True,
                        striped=True,
                        # Thin, at the mock's 4px: the live-activity signal is
                        # the only motion on this screen, and it says "still
                        # running" from the edge of vision rather than from a
                        # bar the eye has to land on.
                        size="xs",
                        classNames=PROGRESS_CLASS_NAMES,
                    ),
                    # The elapsed readout that used to sit here now rides in the
                    # action row, next to the chars counter — see
                    # _chat_action_buttons.
                ],
                id="chat-progress-container",
                style={
                    "display": "block" if session.get("_stream_id") else "none",
                    "marginBottom": "12px",
                },
            ),
            html.Div(
                [
                    dmc.Textarea(
                        id="chat-input",
                        placeholder="Type your message…",
                        style={"flex": "1"},
                        autosize=True,
                        minRows=2,
                        n_submit=0,
                    ),
                    dmc.Button("Send", id="btn-chat-submit"),
                ],
                style={
                    # Hide the text input + Send button while the breadth
                    # checkbox panel is active — the user acts via checkboxes at
                    # this step. Components stay mounted (display:none) so
                    # on_chat_submit's State references remain valid under
                    # suppress_callback_exceptions.
                    "display": "none" if breadth_panel is not None else "flex",
                    "alignItems": "stretch",
                    "gap": "var(--mantine-spacing-sm)",
                    "width": "100%",
                },
            ),
            # The footer row under the composer. The model chip is the standing
            # answer to "what is this agent running on" and the only way to
            # change it without re-entering the agent, so it sits where the
            # developer is actually typing rather than up in the action row.
            # To its right, the one-line status says what that model is doing
            # right now, published by agents via session["_stream_status"] and
            # cleared when the stream finalises. The status keeps its reserved
            # line of height so the input row doesn't shift when the first
            # message lands mid-turn; each new message replaces the previous.
            # The chip is suppressed while the gate is open, where the card is
            # already asking the question.
            html.Div(
                [
                    *(
                        []
                        if gate_open
                        else [_llm_gate.model_chip(session, active)]
                    ),
                    dmc.Text(
                        session.get("_stream_status") or "",
                        id="chat-status-line",
                        c="dimmed",
                        size="xs",
                        style={
                            # Takes the rest of the row so a long status still
                            # ellipsises instead of pushing the chip; minWidth
                            # is what lets a flex child shrink below its
                            # content width at all.
                            "flex": "1",
                            "minWidth": "0",
                            "minHeight": "1.4em",
                            "whiteSpace": "nowrap",
                            "overflow": "hidden",
                            "textOverflow": "ellipsis",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "var(--mantine-spacing-sm)",
                    "marginTop": "4px",
                },
            ),
        ]
    )
