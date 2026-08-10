"""Pure helpers for the outbound delivery protocol."""

from __future__ import annotations

import hashlib
import hmac


def webhook_signature(secret: str, body: bytes) -> str:
    """Return the signature header value for the exact transmitted bytes."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def response_disposition(status: int) -> str:
    """Map an HTTP acknowledgement to delivered, retry, or permanent failure."""
    if 200 <= status < 300:
        return "Delivered"
    if status >= 500:
        return "Retry"
    return "Failed"
