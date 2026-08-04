"""Sub-agent dispatch for Agentifier.

This module provides the typed interfaces, error classes, and registry that
Agentifier's orchestrator uses to invoke in-process sub-agents.  Everything
here is plain Python/asyncio — no network transport, no protocol framing,
no retries.  Sub-agents are Python coroutines that share the same trust
boundary and process; native async/await is the right abstraction.

Quick reference::

    from spec4.agentifier.subagents import SubAgentRegistry, SubAgentError

    registry = SubAgentRegistry()
    registry.register(my_agent)

    result = await registry.run("my_agent", MyInput(query="hello"))

    async for chunk in registry.stream("my_streaming_agent", MyInput(query="hi")):
        print(chunk)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any, Protocol, runtime_checkable

__all__ = [
    # Protocols
    "SubAgent",
    "StreamingSubAgent",
    # Errors
    "SubAgentError",
    "SubAgentTimeoutError",
    "RegistryLookupError",
    # Registry
    "SubAgentRegistry",
    # Helpers
    "run_with_timeout",
    "validate_dataclass_input",
]

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------


class SubAgentError(Exception):
    """A sub-agent invocation failed.

    Wraps the original exception so the orchestrator can log or recover
    without losing the root cause.
    """

    def __init__(self, name: str, cause: BaseException) -> None:
        super().__init__(f"sub-agent '{name}' raised: {cause!r}")
        self.name = name
        self.cause = cause


class SubAgentTimeoutError(SubAgentError):
    """A sub-agent did not complete within its allocated time budget.

    Attributes:
        timeout: The budget (seconds) that was exceeded.
    """

    def __init__(self, name: str, timeout: float) -> None:
        # Bypass SubAgentError.__init__ — cause is synthetic, not an upstream exc.
        Exception.__init__(self, f"sub-agent '{name}' timed out after {timeout}s")
        self.name = name
        self.timeout = timeout
        self.cause: BaseException = asyncio.TimeoutError(f"timed out after {timeout}s")


class RegistryLookupError(KeyError):
    """A sub-agent name was not found in the registry."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.agent_name = name

    def __str__(self) -> str:
        return f"no sub-agent registered under name '{self.agent_name}'"


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class SubAgent(Protocol):
    """Request/response sub-agent interface.

    Implementations must expose a ``name`` attribute used as the registry key
    and a ``run`` coroutine that accepts typed input and returns typed output.
    Exceptions propagate to the caller; the dispatch layer wraps them in
    :class:`SubAgentError`.

    Example::

        @dataclass
        class EchoInput:
            text: str

        class EchoAgent:
            name = "echo"

            async def run(self, input: EchoInput) -> str:
                validate_dataclass_input(input, EchoInput)
                return input.text
    """

    name: str

    async def run(self, input: Any) -> Any:  # noqa: A002
        ...


@runtime_checkable
class StreamingSubAgent(Protocol):
    """Streaming sub-agent interface.

    ``stream`` is an async generator: it yields typed chunks as they are
    produced.  The caller iterates with ``async for``.

    Example::

        class TokenStreamer:
            name = "token_streamer"

            async def stream(self, input: MyInput) -> AsyncIterator[str]:
                for token in input.text.split():
                    yield token
    """

    name: str

    async def stream(self, input: Any) -> AsyncIterator[Any]:  # noqa: A002
        ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class SubAgentRegistry:
    """Central lookup table for sub-agents.

    The registry centralises logging and error wrapping.  Sub-agents may also
    be imported and invoked directly when the orchestrator doesn't need
    registry semantics — the registry is not mandatory middleware.
    """

    def __init__(self) -> None:
        self._agents: dict[str, Any] = {}

    def register(self, agent: Any) -> None:
        """Add *agent* to the registry under ``agent.name``.

        Re-registering the same name overwrites the previous entry.
        """
        self._agents[agent.name] = agent
        _log.debug("registered sub-agent '%s'", agent.name)

    def lookup(self, name: str) -> Any:
        """Return the sub-agent registered under *name*.

        Raises:
            RegistryLookupError: if *name* has not been registered.
        """
        try:
            return self._agents[name]
        except KeyError:
            raise RegistryLookupError(name)

    async def run(self, name: str, input: Any) -> Any:  # noqa: A002
        """Invoke a request/response sub-agent by name.

        Exceptions from the sub-agent are re-raised wrapped in
        :class:`SubAgentError`.  An already-wrapped :class:`SubAgentError`
        passes through unchanged so the original context is preserved.

        Raises:
            RegistryLookupError: if *name* is not registered.
            SubAgentError: wrapping any exception the sub-agent raises.
        """
        agent = self.lookup(name)
        _log.debug("invoking sub-agent '%s'", name)
        try:
            result = await agent.run(input)
        except SubAgentError:
            raise
        except Exception as exc:
            raise SubAgentError(name, exc) from exc
        _log.debug("sub-agent '%s' completed", name)
        return result

    async def stream(
        self, name: str, input: Any  # noqa: A002
    ) -> AsyncGenerator[Any, None]:
        """Invoke a streaming sub-agent by name, yielding its chunks.

        Iterate the return value with ``async for``.  Exceptions from the
        sub-agent are wrapped in :class:`SubAgentError` (same rules as
        :meth:`run`).

        Raises:
            RegistryLookupError: if *name* is not registered.
            SubAgentError: wrapping any exception the sub-agent raises.
        """
        agent = self.lookup(name)
        _log.debug("streaming sub-agent '%s'", name)
        try:
            async for chunk in agent.stream(input):
                yield chunk
        except SubAgentError:
            raise
        except Exception as exc:
            raise SubAgentError(name, exc) from exc


# ---------------------------------------------------------------------------
# Timeout helper
# ---------------------------------------------------------------------------


async def run_with_timeout(coro: Any, *, timeout: float, name: str) -> Any:
    """Await *coro*, cancelling it if it exceeds *timeout* seconds.

    Args:
        coro: Coroutine returned by a sub-agent's ``run()`` method.
        timeout: Wall-clock budget in seconds.
        name: Sub-agent name included in the error for debuggability.

    Raises:
        SubAgentTimeoutError: if the coroutine doesn't complete in time.
    """
    try:
        async with asyncio.timeout(timeout):
            return await coro
    except TimeoutError:
        raise SubAgentTimeoutError(name, timeout)


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------


def validate_dataclass_input(value: object, expected_type: type) -> None:
    """Assert that *value* is an instance of *expected_type*.

    Call this at the top of a sub-agent's ``run()`` or ``stream()`` method to
    enforce typed inputs at the boundary.  Raises :class:`TypeError` on
    mismatch so callers get a clear message rather than a cryptic AttributeError
    deep inside the agent.

    Example::

        async def run(self, input: MyInput) -> str:
            validate_dataclass_input(input, MyInput)
            return input.text.upper()
    """
    if not isinstance(value, expected_type):
        raise TypeError(
            f"expected {expected_type.__name__}, got {type(value).__name__!r}"
        )
