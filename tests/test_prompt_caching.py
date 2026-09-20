"""The prompt-cache markers: who gets them, how many, and who must never.

``llm._build_completion_kwargs`` adds LiteLLM's
``cache_control_injection_points`` — one ephemeral mark on the system turn —
only for the providers whose LiteLLM integration translates it. The interesting
half of that is the exclusions: on ``gemini`` the marker switches Vertex
explicit context caching on (extra live round-trips per request), and on
``openai`` with a custom ``api_base`` — Spec4's Nebius provider — it is
forwarded verbatim to a server that may well answer 400. Those two are
regression tests, not completeness.

``llm._stream_request_kwargs`` then adds a second point, on the last message,
for conversation turns only: the system prompt alone is below the 4,096-token
caching floor of some models, where the whole conversation is not. The one-shot
helpers keep the single point — their last message is a user turn that differs
every call, so a mark there could only ever be a write.

Everything is driven through the public entry points with LiteLLM patched at
the module seam, the way ``test_llm.py::TestEffortRejectionFallback`` does it,
so what is asserted is the kwargs a real call would carry.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import litellm
import pytest
from litellm.exceptions import BadRequestError as LiteLLMBadRequestError

from spec4 import llm
from spec4.providers import PROVIDERS
from tests._chunks import make_stream_chunk, make_usage

_ANTHROPIC = "anthropic/claude-sonnet-4-5"
_BEDROCK = "bedrock/converse/anthropic.claude-3-5-sonnet-20240620-v1:0"
_NEBIUS_MODEL = "openai/deepseek-ai/DeepSeek-V3"
_NEBIUS_API_BASE = PROVIDERS["nebius"]["api_base"]

_KEY = "cache_control_injection_points"

# The exact value Lever 1 sends. Written out rather than imported from the
# module under test, so a change to the point's shape fails here.
_LEVER_1 = [
    {
        "location": "message",
        "role": "system",
        "index": None,
        "control": {"type": "ephemeral"},
    }
]

# What a conversation round sends: the same system point, then the last
# message. Order is load-bearing — the points are honoured in list order
# against a budget of four, and Anthropic's prefix runs tools → system →
# messages.
_LAST_MESSAGE_POINT = {
    "location": "message",
    "role": None,
    "index": -1,
    "control": {"type": "ephemeral"},
}
_LEVER_2 = [_LEVER_1[0], _LAST_MESSAGE_POINT]


@pytest.fixture(autouse=True)
def _neutral_switch(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Start every test from the default (kill switch unset), leave no usage.

    The usage sink is process-global; these calls all go through it, so they
    are drained rather than left for whatever runs next.
    """
    monkeypatch.delenv(llm._PROMPT_CACHING_ENV, raising=False)
    yield
    llm.drain_usage_records()


def _messages() -> list[dict[str, Any]]:
    return [{"role": "user", "content": "hi"}]


def _response() -> SimpleNamespace:
    """A non-streamed response with real counts, so usage capture stays quiet."""
    response = SimpleNamespace(usage=make_usage(10, 5))
    response._hidden_params = {}
    return response


def _chunks() -> Iterator[Any]:
    return iter([make_stream_chunk(content="Hi", finish_reason="stop")])


def _recorder(calls: list[dict[str, Any]], *, stream: bool) -> Any:
    def fake_completion(**kwargs: Any) -> Any:
        calls.append(dict(kwargs))
        return _chunks() if stream else _response()

    return fake_completion


def _sent(
    llm_config: dict[str, Any], *, stream: bool = False, **extra: Any
) -> dict[str, Any]:
    """The kwargs one public call hands LiteLLM."""
    calls: list[dict[str, Any]] = []
    recorder = _recorder(calls, stream=stream)
    with patch("spec4.llm.litellm.completion", side_effect=recorder):
        if stream:
            list(
                llm.stream_completion(
                    llm_config=llm_config, messages=_messages(), **extra
                )
            )
        else:
            llm.complete(llm_config=llm_config, messages=_messages(), **extra)
    assert len(calls) == 1
    return calls[0]


def _turn_calls(
    llm_config: dict[str, Any],
    *,
    messages: list[dict[str, Any]] | None = None,
    search_config: str | None = None,
    completion: Any = None,
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    """Drive one ``stream_turn`` and return (kwargs per call, output, messages).

    The kwargs are shallow-copied, so a captured list value is still the very
    object the call was handed — the identity tests below depend on that.
    """
    calls: list[dict[str, Any]] = []

    def default_completion(**kwargs: Any) -> Any:
        calls.append(dict(kwargs))
        return _chunks()

    fake = completion(calls) if completion is not None else default_completion
    history = [] if messages is None else messages
    with patch("spec4.llm.litellm.completion", side_effect=fake):
        out = "".join(llm.stream_turn("sys", history, llm_config, search_config))
    return calls, out, history


def _tool_call(query: str) -> SimpleNamespace:
    """One streamed ``tool_calls`` entry, field for field as the loop reads it."""
    return SimpleNamespace(
        index=0,
        id="call-1",
        function=SimpleNamespace(
            name="web_search", arguments=json.dumps({"query": query})
        ),
    )


def _holds_cache_control(value: Any) -> bool:
    """Whether ``cache_control`` appears anywhere in a nested structure."""
    if isinstance(value, dict):
        return "cache_control" in value or any(
            _holds_cache_control(v) for v in value.values()
        )
    if isinstance(value, list):
        return any(_holds_cache_control(v) for v in value)
    return False


class TestProviderAllowlist:
    """The marker follows the provider LiteLLM resolves, nothing else."""

    @pytest.mark.parametrize("stream", [False, True])
    @pytest.mark.parametrize("model", [_ANTHROPIC, _BEDROCK])
    def test_a_translating_provider_carries_the_exact_point(
        self, model: str, stream: bool
    ) -> None:
        sent = _sent({"model": model, "api_key": "k"}, stream=stream)
        assert sent[_KEY] == _LEVER_1

    @pytest.mark.parametrize(
        "model",
        [
            "gemini/gemini-2.5-pro",
            "mistral/mistral-large-latest",
            "openai/gpt-4o",
            "openrouter/openai/gpt-4o",
            "openrouter/anthropic/claude-3.5-sonnet",
        ],
    )
    def test_an_excluded_provider_never_carries_it(self, model: str) -> None:
        sent = _sent({"model": model, "api_key": "k"})
        assert sent["model"] == model
        assert _KEY not in sent

    def test_openrouter_claude_is_excluded_with_the_rest(self) -> None:
        """LiteLLM *would* translate it there; the allowlist still says no.

        Pinned separately from the loop above because it is the one exclusion
        that is a routing decision rather than a safety one — no Claude traffic
        goes through OpenRouter. Adding it to ``_CACHE_MARKER_PROVIDERS`` should
        fail here, deliberately, so the change is made on purpose.
        """
        assert "openrouter" not in llm._CACHE_MARKER_PROVIDERS
        model = "openrouter/anthropic/claude-3.5-sonnet"
        sent = _sent({"model": model, "api_key": "k"})
        assert sent["model"] == model
        assert _KEY not in sent

    def test_nebius_openai_with_a_custom_api_base_is_never_marked(self) -> None:
        """The 400 risk: a marker LiteLLM forwards verbatim to a strict server."""
        sent = _sent(
            {
                "model": _NEBIUS_MODEL,
                "api_key": "k",
                "api_base": _NEBIUS_API_BASE,
            }
        )
        assert sent["api_base"] == _NEBIUS_API_BASE
        assert _KEY not in sent

    def test_an_unresolvable_model_is_not_marked_and_does_not_raise(self) -> None:
        sent = _sent({"model": "no-such-model-anywhere", "api_key": "k"})
        assert sent["model"] == "no-such-model-anywhere"
        assert _KEY not in sent

    def test_the_predicate_reads_none_as_not_allowed(self) -> None:
        """``_resolve_provider`` returning None must be a plain False."""
        with patch("spec4.llm._resolve_provider", return_value=None) as resolve:
            assert llm._prompt_caching_enabled({"model": _ANTHROPIC}) is False
        assert resolve.call_count == 1

    def test_the_allowlist_holds_both_translating_providers(self) -> None:
        allowlist = set(llm._CACHE_MARKER_PROVIDERS)
        assert allowlist == {"anthropic", "bedrock"}


class TestKillSwitch:
    """``SPEC4_PROMPT_CACHING`` is read at call time, not at import."""

    @pytest.mark.parametrize("value", ["0", "false", "OFF", "False", " off "])
    def test_an_off_value_suppresses_the_marker(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv(llm._PROMPT_CACHING_ENV, value)
        sent = _sent({"model": _ANTHROPIC, "api_key": "k"})
        assert sent["model"] == _ANTHROPIC
        assert _KEY not in sent

    @pytest.mark.parametrize("value", ["1", "true", "on", "yes", ""])
    def test_anything_else_leaves_it_on(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv(llm._PROMPT_CACHING_ENV, value)
        assert _sent({"model": _ANTHROPIC, "api_key": "k"})[_KEY] == _LEVER_1

    def test_unset_means_on(self) -> None:
        assert _sent({"model": _ANTHROPIC, "api_key": "k"})[_KEY] == _LEVER_1

    def test_a_flip_between_two_calls_is_seen_by_the_second(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = {"model": _ANTHROPIC, "api_key": "k"}
        assert _sent(config)[_KEY] == _LEVER_1
        monkeypatch.setenv(llm._PROMPT_CACHING_ENV, "0")
        second = _sent(config)
        assert second["model"] == _ANTHROPIC
        assert _KEY not in second


class TestCallerOverride:
    def test_an_explicit_value_through_extra_wins(self) -> None:
        mine = [{"location": "message", "role": "user", "index": 0}]
        sent = _sent({"model": _ANTHROPIC, "api_key": "k"}, **{_KEY: mine})
        assert sent[_KEY] == mine

    def test_an_explicit_value_survives_on_an_excluded_provider(self) -> None:
        """setdefault only ever adds; it never removes what a caller passed."""
        mine = [{"location": "message", "role": "user", "index": 0}]
        sent = _sent({"model": "gemini/gemini-2.5-pro", "api_key": "k"}, **{_KEY: mine})
        assert sent[_KEY] == mine


class TestFreshPointsEachCall:
    def test_mutating_one_calls_points_does_not_reach_the_next(self) -> None:
        config = {"model": _ANTHROPIC, "api_key": "k"}
        first = _sent(config)
        first[_KEY].clear()
        second = _sent(config)
        assert first[_KEY] == []
        assert second[_KEY] == _LEVER_1

    def test_two_calls_do_not_share_the_list_object(self) -> None:
        config = {"model": _ANTHROPIC, "api_key": "k"}
        first = _sent(config)
        second = _sent(config)
        assert first[_KEY] == second[_KEY]
        assert first[_KEY] is not second[_KEY]
        assert first[_KEY][0] is not second[_KEY][0]


class TestDropParamsUnaffected:
    """The marker must not drag ``drop_params`` in with it."""

    def test_absent_when_no_effort_is_sent(self) -> None:
        sent = _sent({"model": _ANTHROPIC, "api_key": "k"})
        assert sent[_KEY] == _LEVER_1
        assert "drop_params" not in sent

    def test_present_when_an_effort_is_sent(self) -> None:
        sent = _sent({"model": _ANTHROPIC, "api_key": "k", "effort": "high"})
        assert sent[_KEY] == _LEVER_1
        assert sent["drop_params"] is True


class TestAsyncPath:
    """``acomplete`` builds its kwargs through the same helper."""

    def _sent(self, model: str) -> dict[str, Any]:
        calls: list[dict[str, Any]] = []

        async def fake_acompletion(**kwargs: Any) -> Any:
            calls.append(dict(kwargs))
            return _response()

        async def _run() -> None:
            await llm.acomplete(
                llm_config={"model": model, "api_key": "k"}, messages=_messages()
            )

        with patch("spec4.llm.litellm.acompletion", side_effect=fake_acompletion):
            asyncio.run(_run())
        assert len(calls) == 1
        return calls[0]

    def test_anthropic_carries_the_marker(self) -> None:
        assert self._sent(_ANTHROPIC)[_KEY] == _LEVER_1

    def test_gemini_does_not(self) -> None:
        sent = self._sent("gemini/gemini-2.5-pro")
        assert sent["model"] == "gemini/gemini-2.5-pro"
        assert _KEY not in sent


class TestThroughRealLiteLLM:
    """One end-to-end pass through LiteLLM's own hook, offline.

    ``mock_response`` short-circuits the transport, so the request is built for
    real — the AnthropicCacheControlHook runs — without a network call. What
    this pins that a patched seam cannot: LiteLLM accepts the kwarg and leaves
    the caller's ``messages`` alone (it deep-copies its own).
    """

    def test_the_kwarg_is_accepted_and_the_caller_s_messages_are_untouched(
        self,
    ) -> None:
        messages = [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "hi"},
        ]
        before = [dict(m) for m in messages]
        response = litellm.completion(
            model=_ANTHROPIC,
            messages=messages,
            api_key="sk-test",
            mock_response="ok",
            **{_KEY: _LEVER_1},
        )
        assert response.choices[0].message.content == "ok"
        assert messages == before
        assert all(isinstance(m["content"], str) for m in messages)

    def test_the_two_point_value_leaves_a_tool_history_alone(self) -> None:
        """The same proof for the shape the tool loop actually sends.

        The last message is a ``tool`` result, which is where the second point
        lands. LiteLLM's hook deep-copies before marking, so nothing reaches
        the history ``stream_turn`` hands back to the session.
        """
        messages = [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "web_search", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "hits"},
        ]
        before = json.loads(json.dumps(messages))
        response = litellm.completion(
            model=_ANTHROPIC,
            messages=messages,
            api_key="sk-test",
            mock_response="ok",
            **{_KEY: _LEVER_2},
        )
        assert response.choices[0].message.content == "ok"
        assert messages == before
        assert not _holds_cache_control(messages)


class TestStreamTurnPoints:
    """A conversation round marks the system turn *and* the last message."""

    @pytest.mark.parametrize("model", [_ANTHROPIC, _BEDROCK])
    def test_a_translating_provider_sends_exactly_two_points(self, model: str) -> None:
        calls, out, _ = _turn_calls({"model": model, "api_key": "k"})
        assert out == "Hi"
        assert len(calls) == 1
        assert calls[0][_KEY] == _LEVER_2
        assert len(calls[0][_KEY]) == 2
        assert calls[0][_KEY][0]["role"] == "system"
        assert calls[0][_KEY][1] == _LAST_MESSAGE_POINT

    @pytest.mark.parametrize(
        "model",
        [
            "gemini/gemini-2.5-pro",
            "openai/gpt-4o",
            "openrouter/anthropic/claude-3.5-sonnet",
        ],
    )
    def test_an_excluded_provider_sends_no_points_at_all(self, model: str) -> None:
        calls, out, _ = _turn_calls({"model": model, "api_key": "k"})
        assert out == "Hi"
        assert calls[0]["model"] == model
        assert _KEY not in calls[0]

    def test_nebius_openai_with_a_custom_api_base_sends_none(self) -> None:
        calls, _, _ = _turn_calls(
            {
                "model": _NEBIUS_MODEL,
                "api_key": "k",
                "api_base": _NEBIUS_API_BASE,
            }
        )
        assert calls[0]["api_base"] == _NEBIUS_API_BASE
        assert _KEY not in calls[0]

    def test_the_kill_switch_suppresses_both_points(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(llm._PROMPT_CACHING_ENV, "0")
        calls, _, _ = _turn_calls({"model": _ANTHROPIC, "api_key": "k"})
        assert calls[0]["model"] == _ANTHROPIC
        assert _KEY not in calls[0]

    def test_the_upgrade_does_not_disturb_the_rest_of_the_kwargs(self) -> None:
        calls, _, _ = _turn_calls(
            {"model": _ANTHROPIC, "api_key": "k", "effort": "high"}
        )
        assert calls[0][_KEY] == _LEVER_2
        assert calls[0]["reasoning_effort"] == "high"
        assert calls[0]["drop_params"] is True
        assert calls[0]["stream"] is True


class TestOneShotKeepsOnePoint:
    """The single-point paths stay single-point: a mark there never reads."""

    def test_complete_sends_only_the_system_point(self) -> None:
        sent = _sent({"model": _ANTHROPIC, "api_key": "k"})
        assert sent[_KEY] == _LEVER_1
        assert len(sent[_KEY]) == 1

    def test_stream_completion_sends_only_the_system_point(self) -> None:
        sent = _sent({"model": _ANTHROPIC, "api_key": "k"}, stream=True)
        assert sent[_KEY] == _LEVER_1
        assert len(sent[_KEY]) == 1


class TestStreamCallerOverride:
    """``stream_turn`` takes no ``**extra``, so the seam is tested directly.

    ``_stream_request_kwargs`` is the only builder ``stream_turn`` uses and the
    only place the upgrade happens; a caller value reaching it has to survive.
    """

    def test_a_caller_value_through_extra_is_passed_through_untouched(self) -> None:
        mine = [{"location": "message", "role": "user", "index": 0}]
        kwargs = llm._stream_request_kwargs(
            "sys", [], {"model": _ANTHROPIC, "api_key": "k"}, None, None, **{_KEY: mine}
        )
        assert kwargs[_KEY] is mine
        assert kwargs[_KEY] != _LEVER_2

    def test_without_a_caller_value_the_same_call_is_upgraded(self) -> None:
        kwargs = llm._stream_request_kwargs(
            "sys", [], {"model": _ANTHROPIC, "api_key": "k"}, None, None
        )
        assert kwargs[_KEY] == _LEVER_2


class TestToolLoopRounds:
    """Every round of the loop sends both points, and the history stays clean."""

    def test_both_rounds_carry_both_points(self) -> None:
        def completion(calls: list[dict[str, Any]]) -> Any:
            def fake_completion(**kwargs: Any) -> Any:
                calls.append(dict(kwargs))
                if len(calls) == 1:
                    return iter(
                        [
                            make_stream_chunk(
                                None, tool_calls=[_tool_call("dash docs")]
                            ),
                            make_stream_chunk("", finish_reason="stop"),
                        ]
                    )
                return iter([make_stream_chunk("Answer", finish_reason="stop")])

            return fake_completion

        with patch("spec4.llm.search", return_value="hits") as search:
            calls, out, history = _turn_calls(
                {"model": _ANTHROPIC, "api_key": "k"},
                messages=[{"role": "user", "content": "hello"}],
                search_config="tv-key",
                completion=completion,
            )

        search.assert_called_once_with("dash docs", "tv-key")
        assert "Answer" in out
        assert len(calls) == 2
        assert calls[0][_KEY] == _LEVER_2
        assert calls[1][_KEY] == _LEVER_2
        assert calls[1][_KEY] is not calls[0][_KEY]

        roles = [m["role"] for m in history]
        assert roles == ["user", "assistant", "tool", "assistant"]
        assert history[-2]["content"] == "hits"
        assert not _holds_cache_control(history)

    def test_the_last_message_of_each_round_is_the_one_marked(self) -> None:
        """What ``index: -1`` resolves to, round by round.

        The second round's last message is the tool result, which is the shape
        the point is designed for; the first round's is the user turn.
        """
        seen: list[str] = []

        def completion(calls: list[dict[str, Any]]) -> Any:
            def fake_completion(**kwargs: Any) -> Any:
                calls.append(dict(kwargs))
                seen.append(kwargs["messages"][-1]["role"])
                if len(calls) == 1:
                    return iter(
                        [
                            make_stream_chunk(None, tool_calls=[_tool_call("q")]),
                            make_stream_chunk("", finish_reason="stop"),
                        ]
                    )
                return iter([make_stream_chunk("Answer", finish_reason="stop")])

            return fake_completion

        with patch("spec4.llm.search", return_value="hits"):
            calls, _, _ = _turn_calls(
                {"model": _ANTHROPIC, "api_key": "k"},
                messages=[{"role": "user", "content": "hello"}],
                search_config="tv-key",
                completion=completion,
            )

        assert seen == ["user", "tool"]
        assert all(call[_KEY] == _LEVER_2 for call in calls)


class TestStreamRetriesKeepBothPoints:
    """Both retry paths re-send the same kwargs dict, upgrade included."""

    def test_the_effort_fallback_retry_still_carries_both(self) -> None:
        def completion(calls: list[dict[str, Any]]) -> Any:
            def fake_completion(**kwargs: Any) -> Any:
                calls.append(dict(kwargs))
                if len(calls) == 1:
                    raise LiteLLMBadRequestError(
                        message="max only works on Opus 4.6",
                        model=_ANTHROPIC,
                        llm_provider="anthropic",
                    )
                return _chunks()

            return fake_completion

        calls, out, _ = _turn_calls(
            {"model": _ANTHROPIC, "api_key": "k", "effort": "max"},
            completion=completion,
        )
        assert out == "Hi"
        assert len(calls) == 2
        assert calls[0][_KEY] == _LEVER_2
        assert calls[1][_KEY] == _LEVER_2
        assert "reasoning_effort" not in calls[1]

    def test_the_tool_rejection_retry_still_carries_both(self) -> None:
        def completion(calls: list[dict[str, Any]]) -> Any:
            def fake_completion(**kwargs: Any) -> Any:
                calls.append(dict(kwargs))
                if len(calls) == 1:
                    raise LiteLLMBadRequestError(
                        message=(
                            "This model does not support auto tool, "
                            "please use tool_choice."
                        ),
                        model=_ANTHROPIC,
                        llm_provider="anthropic",
                    )
                return _chunks()

            return fake_completion

        calls, out, _ = _turn_calls(
            {"model": _ANTHROPIC, "api_key": "k"},
            search_config="tv-key",
            completion=completion,
        )
        assert "Web search disabled" in out
        assert len(calls) == 2
        assert "tools" in calls[0]
        assert "tools" not in calls[1]
        assert calls[1]["model"] == _ANTHROPIC
        assert calls[0][_KEY] == _LEVER_2
        assert calls[1][_KEY] == _LEVER_2


class TestFreshStreamPointsEachCall:
    def test_two_turns_share_no_list_and_no_point_dict(self) -> None:
        config = {"model": _ANTHROPIC, "api_key": "k"}
        first, _, _ = _turn_calls(config)
        second, _, _ = _turn_calls(config)
        assert first[0][_KEY] == second[0][_KEY] == _LEVER_2
        assert first[0][_KEY] is not second[0][_KEY]
        assert first[0][_KEY][0] is not second[0][_KEY][0]
        assert first[0][_KEY][1] is not second[0][_KEY][1]

    def test_mutating_one_turns_points_does_not_reach_the_next(self) -> None:
        config = {"model": _ANTHROPIC, "api_key": "k"}
        first, _, _ = _turn_calls(config)
        first[0][_KEY].clear()
        second, _, _ = _turn_calls(config)
        assert first[0][_KEY] == []
        assert second[0][_KEY] == _LEVER_2

    def test_the_helper_does_not_hand_out_lever_ones_objects(self) -> None:
        """The two builders share the system point's *shape*, not its object."""
        one = llm._cache_injection_points()
        two = llm._stream_cache_injection_points()
        assert two[0] == one[0]
        assert two[0] is not one[0]
        assert two[1] == _LAST_MESSAGE_POINT
