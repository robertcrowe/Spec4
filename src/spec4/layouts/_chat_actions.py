"""The action row under the transcript, and the ids its controls carry.

Cleanup Phase 4f moved it out of :mod:`spec4.layouts._chat`. The row is the
one place that decides what a given agent offers when its turn ends, so the
Download/Open id prefixes and the counters that ride in the row live with it
rather than beside the pipeline indicator
(:mod:`spec4.layouts._chat_status`) or the optional blocks
(:mod:`spec4.layouts._chat_panels`).

Every name here is re-exported from ``spec4.layouts._chat``, so importing from
either module reaches the same object.
"""

from __future__ import annotations

from typing import Any

from dash import html
import dash_mantine_components as dmc

from spec4.app_constants import (
    STATE_AGENTIFIER_COMPLETE,
    STATE_DEPLOYER_COMPLETE,
    STATE_REVIEW_COMPLETE,
    STATE_STACK_COMPLETE,
    STATE_VISION_COMPLETE,
)
from spec4.layouts._round_tree import PHASES_DIR


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
        buttons = _code_scanner_action_buttons(session)
    elif active == "brainstormer":
        buttons = _brainstormer_action_buttons(session)
    elif active == "agentifier":
        buttons = _agentifier_action_buttons(session)
    elif active == "stack_advisor":
        buttons = _stack_advisor_action_buttons(session)
    elif active == "phaser":
        buttons = _phaser_action_buttons(session)
    elif active == "deployer":
        buttons = _deployer_action_buttons(session)

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
        (i for i, b in enumerate(row) if getattr(b, "id", None) == "chat-token-count"),
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


def _code_scanner_action_buttons(session: dict[str, Any]) -> list[Any]:
    """The chat action row for the code scanner agent."""
    buttons: list[Any] = []
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
            dmc.Button("Continue to Brainstormer →", id="btn-review-to-brainstormer"),
        ]
    elif _token_count_text(session):
        # Mid-scan CodeScanner has no other controls, so the bar exists
        # only to carry the counter — render it only once there is a count
        # to show, otherwise the divider would sit above an empty row.
        buttons = [token_counter]
    else:
        buttons = []
    return buttons


def _brainstormer_action_buttons(session: dict[str, Any]) -> list[Any]:
    """The chat action row for the brainstormer agent."""
    buttons: list[Any] = []
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
            dmc.Button("Download vision.json", id="btn-dl-vision", variant="outline"),
            dmc.Button(
                # The skip, drawn as the same neutral outline as Download
                # beside it — the mock gives both `.btn-outline`, and the
                # filled one in this row is the continue below.
                "Continue to Designer →",
                id="btn-brainstormer-to-designer",
                variant="outline",
            ),
            dmc.Button("Continue to Agentifier →", id="btn-brainstormer-to-agentifier"),
        ]
    elif _token_count_text(session):
        # Like mid-scan CodeScanner, Brainstormer has no other controls
        # before the vision lands, so the bar exists only to carry the
        # counter — render it once there is a count, not before, or the
        # divider would sit above an empty row.
        buttons = [token_counter]
    else:
        buttons = []
    return buttons


def _agentifier_action_buttons(session: dict[str, Any]) -> list[Any]:
    """The chat action row for the agentifier agent."""
    buttons: list[Any] = []
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
    return buttons


def _stack_advisor_action_buttons(session: dict[str, Any]) -> list[Any]:
    """The chat action row for the stack advisor agent."""
    buttons: list[Any] = []
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
            dmc.Button("Download stack.json", id="btn-dl-stack", variant="outline"),
            dmc.Button("Send to Phaser →", id="btn-stack-to-phaser"),
        ]
    else:
        buttons = [token_counter, *_ff_controls("StackAdvisor")]
    return buttons


def _phaser_action_buttons(session: dict[str, Any]) -> list[Any]:
    """The chat action row for the phaser agent."""
    buttons: list[Any] = []
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
            dmc.Button("Download phases.zip", id="btn-dl-phases", variant="outline"),
            dmc.Button("Continue to Deployer →", id="btn-phaser-to-deployer"),
        ]
    else:
        buttons = [token_counter, *_ff_controls("Phaser")]
    return buttons


def _deployer_action_buttons(session: dict[str, Any]) -> list[Any]:
    """The chat action row for the deployer agent."""
    buttons: list[Any] = []
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
    return buttons
