"""Public API acceptance against the actual ERPNext/Frappe Docker runtime."""

from __future__ import annotations

import json

import pytest

from .test_api_runtime_harness import ApiClient

pytestmark = pytest.mark.integration


def test_health_contract() -> None:
    client = ApiClient()
    health = client.request("GET", "/api/method/letron_api.control.api.health", expected={200})
    message = health.data.get("message") if isinstance(health.data, dict) else None
    assert isinstance(message, dict), "health response must contain a message object"
    assert message.get("app") == "letron_api"
    components = {
        name: message.get(name)
        for name in ("bootstrap", "policy", "config", "configuration_bundle")
    }
    assert all(isinstance(value, dict) for value in components.values()), components
    failed = {
        name: value
        for name, value in components.items()
        if isinstance(value, dict) and value.get("ok") is not True
    }
    assert message.get("ok") is True, json.dumps(failed, indent=2, default=str)
