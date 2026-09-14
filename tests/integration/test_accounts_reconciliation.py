"""Bounded Accounts endpoint and native reconciliation acceptance."""

from __future__ import annotations

import uuid
from urllib.parse import quote

import pytest

from .test_api_runtime_harness import (
    ApiClient,
    HealthUnavailable,
    response_data,
)

pytestmark = pytest.mark.integration


def _path(route: str, name: str) -> str:
    return f"{route}/{quote(name, safe='')}"


def test_accounts_endpoint_contract() -> None:
    client = ApiClient()
    try:
        client.health_and_login()
    except HealthUnavailable as error:
        pytest.skip(f"blocked runtime: {error}")

    guest = ApiClient()
    for route in (
        "/api/v1/accounts/bank-transactions",
        "/api/v1/accounts/payment-orders",
    ):
        guest.public("GET", route, expected={401, 403})
        client.public("GET", route, expected={200})

    client.public("POST", "/api/v1/accounts/payment-orders", {}, expected={400, 417})
    client.public(
        "POST",
        "/api/v1/accounts/bank-transactions/MISSING/reconcile",
        {"allocations": []},
        expected={400, 404, 417},
    )

    idempotency_name = f"ACCEPTANCE-IDEMPOTENCY-{uuid.uuid4().hex[:8]}"
    first = client.public(
        "POST",
        "/api/v1/accounts/banks",
        {"bank_name": idempotency_name, "swift_number": "P9IDEMP01"},
        expected={200},
        headers={"X-Idempotency-Key": f"accounts-{idempotency_name}"},
    )
    bank_name = str(response_data(first)["name"])
    try:
        client.public(
            "POST",
            "/api/v1/accounts/banks",
            {"bank_name": idempotency_name, "swift_number": "P9IDEMP01"},
            expected={409},
            headers={"X-Idempotency-Key": f"accounts-{idempotency_name}"},
        )
    finally:
        client.public("DELETE", _path("/api/v1/accounts/banks", bank_name), expected={200, 202, 404, 417})
