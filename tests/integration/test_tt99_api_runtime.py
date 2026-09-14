"""TT99 API acceptance through the Letron API Gateway.

These tests deliberately use the existing Gateway harness.  The harness sends
``LETRON_INTERNAL_API_SECRET`` as the integration credential and never calls
ERPNext or Lark directly.  Mutating fixtures are not created here: the tests
first prove the route authorization and validation boundaries without leaving
report packages, shareholders, or closing vouchers behind.
"""

from __future__ import annotations

import pytest

from .test_api_runtime_harness import ApiClient, RuntimeUnavailable

pytestmark = pytest.mark.integration


def _authenticated_client() -> ApiClient:
    client = ApiClient()
    try:
        client.health_and_login()
        client.start_app_session("accounts")
    except RuntimeUnavailable as error:
        pytest.fail(f"blocked Gateway runtime: {error}")
    return client


def test_tt99_master_data_is_readable_through_gateway() -> None:
    client = _authenticated_client()
    try:
        for route in (
            "/api/v1/accounts/companies",
            "/api/v1/accounts/accounts",
            "/api/v1/accounts/finance-books",
            "/api/v1/accounts/fiscal-years",
            "/api/v1/accounts/cost-centers",
            "/api/v1/accounts/settings",
        ):
            response = client.public("GET", route, expected={200})
            assert isinstance(response.data, dict)
    finally:
        client.close_app_session()


def test_tt99_write_endpoints_reach_native_validation() -> None:
    client = _authenticated_client()
    try:
        invalid_requests = (
            ("POST", "/api/v1/accounts/report-packages", {}),
            ("POST", "/api/v1/accounts/shareholders", {}),
            ("POST", "/api/v1/accounts/period-closing-vouchers", {}),
        )
        for method, route, payload in invalid_requests:
            response = client.public(method, route, payload, expected={400, 417})
            assert isinstance(response.data, dict)
    finally:
        client.close_app_session()


def test_tt99_policy_owned_resources_reject_public_writes() -> None:
    client = _authenticated_client()
    try:
        denied_requests = (
            ("POST", "/api/v1/accounts/companies", {}),
            ("POST", "/api/v1/accounts/accounts", {}),
            ("POST", "/api/v1/accounts/finance-books", {}),
            ("POST", "/api/v1/accounts/fiscal-years", {}),
            ("POST", "/api/v1/accounts/cost-centers", {}),
            ("PUT", "/api/v1/accounts/settings", {}),
        )
        for method, route, payload in denied_requests:
            response = client.public(method, route, payload, expected={401, 403, 404})
            assert response.status in {401, 403, 404}
    finally:
        client.close_app_session()
