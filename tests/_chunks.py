"""Streaming-chunk stand-ins that mirror LiteLLM's real chunk types.

Why not ``MagicMock``: a mock answers *every* attribute with a truthy auto-child,
so a test can pass against a field the real object never has, and the production
code's ``getattr(chunk, ...)`` guards are never actually exercised. It is also
extravagantly slow — the factory below replaced ~216,000 mock instantiations
across the suite (CLEANUP_INVENTORY.md §50.1).

The shape mirrors ``litellm.types.utils.ModelResponseStream`` and its
``StreamingChoices`` / ``Delta`` members, field for field, as constructed and
read off a real instance:

* ``ModelResponseStream``: ``id``, ``created``, ``model``, ``object``,
  ``system_fingerprint``, ``provider_specific_fields``, ``choices`` —
  plus ``usage``, which LiteLLM attaches **only** to the final chunk under
  ``include_usage``.
* ``StreamingChoices``: ``index``, ``delta``, ``finish_reason``, ``logprobs``,
  ``enhancements``.
* ``Delta``: ``content``, ``role``, ``function_call``, ``tool_calls``, ``audio``,
  ``images``, ``reasoning_content``, ``thinking_blocks``,
  ``provider_specific_fields``.

Two defaults are deliberate and were read off a real chunk rather than assumed:
``_hidden_params`` is ``{}`` (LiteLLM always attaches the dict), and ``usage`` is
**absent** — ``hasattr(chunk, "usage")`` is ``False`` on a chunk with no usage
block. So ``llm._chunk_usage`` and ``llm._hidden_usage`` reject these stand-ins
by the same route they reject the real object, not because the namespace happens
to be missing a field.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def make_delta(
    content: str | None = None,
    tool_calls: Any = None,
    role: str | None = None,
) -> SimpleNamespace:
    """One ``Delta``, with every field the real type carries."""
    return SimpleNamespace(
        content=content,
        role=role,
        function_call=None,
        tool_calls=tool_calls,
        audio=None,
        images=None,
        reasoning_content=None,
        thinking_blocks=None,
        provider_specific_fields=None,
    )


def make_stream_chunk(
    content: str | None = None,
    finish_reason: str | None = None,
    tool_calls: Any = None,
    usage: Any = None,
) -> SimpleNamespace:
    """One ``ModelResponseStream``.

    ``usage`` is attached only when given, mirroring LiteLLM: a content chunk has
    no ``usage`` attribute at all, and the final chunk under ``include_usage``
    carries one.
    """
    chunk = SimpleNamespace(
        id="chatcmpl-test",
        created=0,
        model="gpt-4o-mini",
        object="chat.completion.chunk",
        system_fingerprint=None,
        provider_specific_fields=None,
        choices=[
            SimpleNamespace(
                index=0,
                delta=make_delta(content=content, tool_calls=tool_calls),
                finish_reason=finish_reason,
                logprobs=None,
                enhancements=None,
            )
        ],
    )
    chunk._hidden_params = {}
    if usage is not None:
        chunk.usage = usage
    return chunk


def make_usage(prompt_tokens: int, completion_tokens: int) -> SimpleNamespace:
    """A LiteLLM ``Usage`` block with real counts, for the usage chunk."""
    return SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        prompt_tokens_details=None,
        completion_tokens_details=None,
    )
