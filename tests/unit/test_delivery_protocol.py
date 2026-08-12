from __future__ import annotations

import hashlib
import hmac

import pytest
from letron_api.delivery_protocol import response_disposition, webhook_signature


def test_webhook_signature_covers_exact_raw_utf8_body() -> None:
    body = '{"document_name":"Khách hàng Đà Nẵng","event_id":"evt-1"}'.encode()
    expected = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    assert webhook_signature("test-secret", body) == f"sha256={expected}"
    assert webhook_signature("test-secret", body + b"\n") != f"sha256={expected}"


@pytest.mark.parametrize("status", [200, 201, 202, 204, 299])
def test_any_2xx_acknowledges_delivery(status: int) -> None:
    assert response_disposition(status) == "Delivered"


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_only_server_failures_are_retried(status: int) -> None:
    assert response_disposition(status) == "Retry"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 408, 409, 429])
def test_client_failures_are_not_retried(status: int) -> None:
    assert response_disposition(status) == "Failed"
