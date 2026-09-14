"""Extended public API and business-flow acceptance on the Docker runtime."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

DELIVERY_ENV = (
    "LETRON_WEBHOOK_URL",
    "LETRON_WEBHOOK_SECRET",
    "LETRON_WEBHOOK_TIMEOUT_MS",
    "LETRON_REALTIME_URL",
    "LETRON_REALTIME_TOKEN",
)


def test_external_delivery_gate_is_configured() -> None:
    missing = [name for name in DELIVERY_ENV if not os.environ.get(name)]
    if missing:
        pytest.skip("blocked external: staging delivery configuration is missing: " + ", ".join(missing))
