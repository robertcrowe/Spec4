from __future__ import annotations

import litellm


def probe_image_support(model: str, api_key: str) -> bool:
    """Return True if litellm's model database indicates the model supports vision."""
    try:
        return bool(litellm.supports_vision(model=model))
    except Exception:
        return False
