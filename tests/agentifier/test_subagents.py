"""Tests for spec4.agentifier.subagents dispatch module."""

import asyncio
from dataclasses import dataclass

import pytest

from spec4.agentifier.subagents import (
    RegistryLookupError,
    StreamingSubAgent,
    SubAgent,
    SubAgentError,
    SubAgentRegistry,
    SubAgentTimeoutError,
    run_with_timeout,
    validate_dataclass_input,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@dataclass
class EchoInput:
    text: str


@dataclass
class WrongInput:
    number: int


class EchoAgent:
    """Trivial request/response agent that returns its input text."""

    name = "echo"

    async def run(self, input: EchoInput) -> str:  # noqa: A002
        validate_dataclass_input(input, EchoInput)
        return input.text


class TokenStreamer:
    """Trivial streaming agent that yields one word at a time."""

    name = "token_streamer"

    async def stream(self, input: EchoInput):  # type: ignore[override]
        validate_dataclass_input(input, EchoInput)
        for word in input.text.split():
            yield word


class ExplodingAgent:
    """Agent that always raises."""

    name = "exploder"

    async def run(self, input: EchoInput) -> str:  # noqa: A002
        raise ValueError("boom")


class SlowAgent:
    """Agent that never completes."""

    name = "slow"

    async def run(self, input: EchoInput) -> str:  # noqa: A002
        await asyncio.sleep(9999)
        return "never"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRequestResponse:
    def test_request_response_with_mock_subagent(self) -> None:
        async def _run() -> None:
            registry = SubAgentRegistry()
            registry.register(EchoAgent())
            result = await registry.run("echo", EchoInput(text="hello world"))
            assert result == "hello world"

        asyncio.run(_run())

    def test_protocol_structural_compatibility(self) -> None:
        # EchoAgent satisfies the SubAgent Protocol structurally.
        assert isinstance(EchoAgent(), SubAgent)

    def test_streaming_protocol_structural_compatibility(self) -> None:
        assert isinstance(TokenStreamer(), StreamingSubAgent)


class TestStreamingSubAgent:
    def test_streaming_subagent_chunks_arrive_incrementally(self) -> None:
        async def _run() -> None:
            registry = SubAgentRegistry()
            registry.register(TokenStreamer())

            chunks: list[str] = []
            inp = EchoInput(text="a b c")
            async for chunk in registry.stream("token_streamer", inp):
                chunks.append(chunk)

            assert chunks == ["a", "b", "c"]

        asyncio.run(_run())

    def test_streaming_order_preserved(self) -> None:
        async def _run() -> None:
            registry = SubAgentRegistry()
            registry.register(TokenStreamer())

            received: list[str] = []
            inp = EchoInput(text="one two three four")
            async for chunk in registry.stream("token_streamer", inp):
                received.append(chunk)

            assert received == ["one", "two", "three", "four"]

        asyncio.run(_run())


class TestErrorHandling:
    def test_subagent_exception_propagates_as_subagenterror(self) -> None:
        async def _run() -> None:
            registry = SubAgentRegistry()
            registry.register(ExplodingAgent())

            with pytest.raises(SubAgentError) as exc_info:
                await registry.run("exploder", EchoInput(text="x"))

            err = exc_info.value
            assert err.name == "exploder"
            assert isinstance(err.cause, ValueError)
            assert str(err.cause) == "boom"

        asyncio.run(_run())

    def test_subagent_error_message_is_descriptive(self) -> None:
        async def _run() -> None:
            registry = SubAgentRegistry()
            registry.register(ExplodingAgent())
            with pytest.raises(SubAgentError) as exc_info:
                await registry.run("exploder", EchoInput(text="x"))
            assert "exploder" in str(exc_info.value)

        asyncio.run(_run())

    def test_pre_wrapped_subagent_error_passes_through_unchanged(self) -> None:
        """A SubAgentError raised inside an agent is not double-wrapped."""

        class DoubleRaiser:
            name = "double_raiser"

            async def run(self, input: EchoInput) -> str:  # noqa: A002
                raise SubAgentError("inner", RuntimeError("already wrapped"))

        async def _run() -> None:
            registry = SubAgentRegistry()
            registry.register(DoubleRaiser())
            with pytest.raises(SubAgentError) as exc_info:
                await registry.run("double_raiser", EchoInput(text="x"))
            # The name on the error should be the one set by the agent, not
            # overwritten by the registry's own wrapping.
            assert exc_info.value.name == "inner"

        asyncio.run(_run())


class TestTimeout:
    def test_timeout_cancels_subagent(self) -> None:
        async def _run() -> None:
            agent = SlowAgent()
            coro = agent.run(EchoInput(text="x"))
            with pytest.raises(SubAgentTimeoutError) as exc_info:
                await run_with_timeout(coro, timeout=0.05, name="slow")

            err = exc_info.value
            assert err.name == "slow"
            assert err.timeout == pytest.approx(0.05)

        asyncio.run(_run())

    def test_timeout_error_is_subclass_of_subagent_error(self) -> None:
        assert issubclass(SubAgentTimeoutError, SubAgentError)

    def test_fast_coro_completes_within_timeout(self) -> None:
        async def _run() -> None:
            agent = EchoAgent()
            result = await run_with_timeout(
                agent.run(EchoInput(text="fast")), timeout=5.0, name="echo"
            )
            assert result == "fast"

        asyncio.run(_run())


class TestTypedPayloadValidation:
    def test_typed_payload_validation_rejects_bad_input(self) -> None:
        """validate_dataclass_input raises TypeError for a wrong type."""
        with pytest.raises(TypeError) as exc_info:
            validate_dataclass_input(WrongInput(number=42), EchoInput)
        assert "EchoInput" in str(exc_info.value)
        assert "WrongInput" in str(exc_info.value)

    def test_validate_passes_for_correct_type(self) -> None:
        # Must not raise.
        validate_dataclass_input(EchoInput(text="ok"), EchoInput)

    def test_agent_propagates_type_error_on_bad_input(self) -> None:
        """TypeError from validate_dataclass_input surfaces to the caller."""

        async def _run() -> None:
            agent = EchoAgent()
            with pytest.raises(TypeError):
                await agent.run(WrongInput(number=1))  # type: ignore[arg-type]

        asyncio.run(_run())


class TestRegistry:
    def test_registry_lookup_returns_registered_subagent(self) -> None:
        registry = SubAgentRegistry()
        agent = EchoAgent()
        registry.register(agent)
        assert registry.lookup("echo") is agent

    def test_registry_lookup_unknown_name_raises(self) -> None:
        registry = SubAgentRegistry()
        with pytest.raises(RegistryLookupError) as exc_info:
            registry.lookup("no_such_agent")
        assert "no_such_agent" in str(exc_info.value)

    def test_registry_lookup_error_is_subclass_of_key_error(self) -> None:
        assert issubclass(RegistryLookupError, KeyError)

    def test_registry_run_raises_registry_lookup_error_for_unknown(self) -> None:
        async def _run() -> None:
            registry = SubAgentRegistry()
            with pytest.raises(RegistryLookupError):
                await registry.run("missing", EchoInput(text="x"))

        asyncio.run(_run())

    def test_registry_re_register_overwrites(self) -> None:
        registry = SubAgentRegistry()
        agent1 = EchoAgent()
        agent2 = EchoAgent()
        registry.register(agent1)
        registry.register(agent2)
        assert registry.lookup("echo") is agent2

    def test_registry_stream_raises_registry_lookup_error_for_unknown(self) -> None:
        async def _run() -> None:
            registry = SubAgentRegistry()
            with pytest.raises(RegistryLookupError):
                async for _ in registry.stream("missing", EchoInput(text="x")):
                    pass

        asyncio.run(_run())
