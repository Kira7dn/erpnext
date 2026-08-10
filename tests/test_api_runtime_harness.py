from __future__ import annotations

from tests.integration.api_runtime_harness import (
    ApiClient,
    Response,
    RuntimeUnavailable,
    retryable_status,
)


def test_retry_policy_is_transient_only() -> None:
    assert not retryable_status(400)
    assert not retryable_status(401)
    assert not retryable_status(403)
    assert not retryable_status(404)
    assert retryable_status(408)
    assert retryable_status(429)
    assert retryable_status(500)


def test_request_with_retry_is_bounded_and_retries_timeout(monkeypatch) -> None:
    client = object.__new__(ApiClient)
    calls = 0

    def fake_request(*args, **kwargs) -> Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeUnavailable("simulated timeout")
        return Response(200, {}, {"data": {"name": "ok"}}, "request-id")

    monkeypatch.setattr(client, "request", fake_request)
    response = client.request_with_retry("GET", "/api/resource/Customer", attempts=3)
    assert response.status == 200
    assert calls == 3


def test_request_with_retry_does_not_retry_business_error(monkeypatch) -> None:
    client = object.__new__(ApiClient)
    calls = 0

    def fake_request(*args, **kwargs) -> Response:
        nonlocal calls
        calls += 1
        return Response(404, {}, {"exc_type": "DoesNotExistError"}, "request-id")

    monkeypatch.setattr(client, "request", fake_request)
    response = client.request_with_retry("GET", "/api/resource/Customer/missing", attempts=3)
    assert response.status == 404
    assert calls == 1


def test_write_timeout_reconciles_by_readback(monkeypatch) -> None:
    client = object.__new__(ApiClient)

    def fake_request(*args, **kwargs) -> Response:
        raise RuntimeUnavailable("simulated write timeout")

    monkeypatch.setattr(client, "request", fake_request)
    monkeypatch.setattr(client, "reconcile", lambda path, expected=None: Response(200, {}, {"data": {"name": "recovered"}}, "request-id"))
    response = client.write_with_reconciliation("POST", "/api/v1/selling/customers", {"customer_name": "x"}, "/api/v1/selling/customers/recovered", attempts=1)
    assert response.status == 200
