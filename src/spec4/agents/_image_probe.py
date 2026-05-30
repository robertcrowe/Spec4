from __future__ import annotations

from typing import Any

import litellm

# Minimal 1×1 red (0xFF0000) PNG — used to ask a verifiable vision question.
_1PX_RED_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"


def probe_image_support(
    model: str, api_key: str, api_base: str | None = None, **extra: Any
) -> bool:
    """Return True if the model accepts image inputs.

    Sends a real (minimal) API call with a 1×1 PNG.  A successful response
    means the model processed the image; any exception means it didn't.
    Extra kwargs (e.g. aws_access_key_id) are forwarded to litellm.completion.
    """
    try:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{_1PX_RED_PNG_B64}"
                            },
                        },
                        {"type": "text", "text": "Is this image red?"},
                    ],
                }
            ],
            "max_tokens": 5,
            "stream": False,
        }
        if api_key:
            kwargs["api_key"] = api_key
        if api_base is not None:
            kwargs["api_base"] = api_base
        kwargs.update(extra)
        litellm.completion(**kwargs)
        return True
    except Exception:
        return False
