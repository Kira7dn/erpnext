"""Assets public API surface acceptance on the Docker runtime."""

from __future__ import annotations

import json

import pytest

from .test_api_runtime_harness import ApiClient, RuntimeUnavailable

pytestmark = pytest.mark.integration


ASSET_ROUTES = (
    "/api/v1/assets/assets",
    "/api/v1/assets/asset-categories",
    "/api/v1/assets/asset-capitalizations",
    "/api/v1/assets/asset-maintenance",
    "/api/v1/assets/asset-movements",
    "/api/v1/assets/asset-repairs",
    "/api/v1/assets/asset-value-adjustments",
    "/api/v1/assets/locations",
)


def test_assets_contract_surface() -> None:
    """Verify the runtime exposes Assets aliases to authenticated users only."""

    client = ApiClient()
    try:
        client.health_and_login()
    except RuntimeUnavailable as error:
        pytest.fail(f"blocked runtime: {error}")

    guest = ApiClient()
    for route in ASSET_ROUTES:
        guest.public("GET", route, expected={401, 403})
        client.public(
            "GET",
            f"{route}?fields={json.dumps(['name'])}",
            expected={200},
        )
