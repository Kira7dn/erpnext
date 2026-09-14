"""Bounded Accounts endpoint and native reconciliation acceptance."""

from __future__ import annotations

import json
import uuid
from urllib.parse import quote, urlencode

import pytest

from .test_api_runtime_harness import ApiClient, RuntimeUnavailable, response_data

pytestmark = pytest.mark.integration


def _path(route: str, name: str) -> str:
    return f"{route}/{quote(name, safe='')}"


def test_accounts_endpoint_contract() -> None:
    client = ApiClient()
    try:
        client.health_and_login()
    except RuntimeUnavailable as error:
        pytest.fail(f"blocked runtime: {error}")

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


def test_accounts_real_user_permission() -> None:
    admin = ApiClient()
    try:
        admin.health_and_login()
    except RuntimeUnavailable as error:
        pytest.fail(f"blocked runtime: {error}")
    email = f"accounts-permission-{uuid.uuid4().hex[:8]}@example.invalid"
    password = "Acceptance-local-accounts-2026!"
    admin.document(
        "POST",
        "User",
        payload={
            "name": email,
            "email": email,
            "first_name": "Accounts Permission",
            "new_password": password,
            "enabled": 1,
            "send_welcome_email": 0,
            "roles": [{"role": "Accounts User"}],
        },
        expected={200},
    )
    restricted = ApiClient()
    restricted.username = email
    restricted.password = password
    try:
        restricted.login()
        restricted.public("GET", "/api/v1/accounts/payment-orders", expected={200})
        restricted.public("POST", "/api/v1/accounts/payment-orders", {}, expected={403, 417})
        created_transaction = restricted.public("POST", "/api/v1/accounts/bank-transactions", {}, expected={200})
        transaction_name = str(response_data(created_transaction)["name"])
        admin.public("DELETE", _path("/api/v1/accounts/bank-transactions", transaction_name), expected={200, 202, 404, 417})
    finally:
        admin.document("DELETE", "User", email, expected={200, 202, 404, 417})


def test_bank_transaction_native_readback_and_reconcile(request: pytest.FixtureRequest) -> None:
    client = ApiClient()
    try:
        client.health_and_login()
    except RuntimeUnavailable as error:
        pytest.fail(f"blocked runtime: {error}")

    prefix = f"ACCEPTANCE-LOCAL-{uuid.uuid4().hex[:8]}-"
    created: list[tuple[str, str]] = []

    def finalize() -> None:
        routes = {
            "Bank Transaction": "/api/v1/accounts/bank-transactions",
            "Bank Account": "/api/v1/accounts/bank-accounts",
            "Bank": "/api/v1/accounts/banks",
            "Payment Entry": "/api/v1/accounts/payment-entries",
            "Customer": "/api/v1/selling/customers",
            "Customer Group": "/api/resource/Customer%20Group",
            "Territory": "/api/resource/Territory",
            "Account": "/api/resource/Account",
            "Payment Order": "/api/v1/accounts/payment-orders",
        }
        for doctype, name in reversed(created):
            if doctype in {"Bank Transaction", "Payment Entry", "Payment Order"}:
                client.public("POST", _path(routes[doctype], name) + "/cancel", expected={200, 400, 404, 417})
            route = routes.get(doctype)
            if not route:
                continue
            client.public("DELETE", _path(route, name), expected={200, 202, 404, 417})

    request.addfinalizer(finalize)
    company = "Letron Holding"
    account_query = urlencode(
        {
                "filters": json.dumps([["company", "=", company]]),
                "fields": json.dumps(["name", "account_type", "root_type", "is_group"]),
            "order_by": "name asc",
            "limit_page_length": 200,
        }
    )
    accounts = client.request("GET", f"/api/resource/Account?{account_query}", expected={200}).data["data"]
    asset_groups = [row for row in accounts if row.get("root_type") == "Asset" and row.get("is_group")]
    if not asset_groups:
        pytest.fail("tenant has no Asset parent account for disposable Accounts fixture")
    account_name = prefix + "Bank Ledger"
    account_created = client.request("POST", "/api/resource/Account", {"account_name": account_name, "company": company, "parent_account": asset_groups[0]["name"], "account_type": "Bank", "root_type": "Asset", "is_group": 0}, expected={200}).data["data"]
    account_name = str(account_created["name"])
    created.append(("Account", account_name))
    bank = response_data(
        client.public(
            "POST",
            "/api/v1/accounts/banks",
            {"bank_name": prefix + "Bank", "swift_number": "P9BANK01"},
            expected={200},
        )
    )
    bank_name = str(bank["name"])
    created.append(("Bank", bank_name))
    bank_account_created = response_data(
        client.public(
            "POST",
            "/api/v1/accounts/bank-accounts",
            {
                "account_name": prefix + "Bank Account",
                "bank": bank_name,
                "company": company,
                    "account": account_name,
                "is_company_account": 1,
            },
            expected={200},
        )
    )
    bank_account_created_name = str(bank_account_created["name"])
    created.append(("Bank Account", bank_account_created_name))
    bank_account_query = urlencode(
        {
            "filters": json.dumps([["name", "=", bank_account_created_name]]),
            "fields": json.dumps(["name", "bank", "account"]),
            "limit_page_length": 1,
        }
    )
    bank_accounts_read = client.request(
        "GET", f"/api/resource/Bank%20Account?{bank_account_query}", expected={200}
    ).data["data"]
    if not bank_accounts_read:
        pytest.skip("tenant has no Bank Account linked to a bank ledger account")
    bank_account = bank_accounts_read[0]["name"]

    company_doc = response_data(client.document("GET", "Company", company, expected={200}))
    customer_group = prefix + "Customer Group"
    territory = prefix + "Territory"
    client.request("POST", "/api/resource/Customer%20Group", {"customer_group_name": customer_group, "is_group": 0}, expected={200})
    created.append(("Customer Group", customer_group))
    client.request("POST", "/api/resource/Territory", {"territory_name": territory, "is_group": 0}, expected={200})
    created.append(("Territory", territory))
    customer = response_data(
        client.public(
            "POST",
            "/api/v1/selling/customers",
            {"customer_name": prefix + "Customer", "customer_group": customer_group, "territory": territory, "customer_type": "Company"},
            expected={200},
        )
    )
    customer_name = str(customer["name"])
    created.append(("Customer", customer_name))
    payment = response_data(
        client.public(
            "POST",
            "/api/v1/accounts/payment-entries",
            {"payment_type": "Receive", "party_type": "Customer", "party": customer_name, "company": company, "posting_date": "2026-08-12", "paid_from": company_doc["default_receivable_account"], "paid_to": bank_accounts_read[0]["account"], "paid_amount": 1000, "received_amount": 1000, "reference_no": prefix + "Payment", "reference_date": "2026-08-12", "references": []},
            expected={200},
        )
    )
    payment_name = str(payment["name"])
    created.append(("Payment Entry", payment_name))
    client.public("POST", _path("/api/v1/accounts/payment-entries", payment_name) + "/submit", expected={200})
    payment_order = response_data(
        client.public(
            "POST",
            "/api/v1/accounts/payment-orders",
            {"company": company, "payment_order_type": "Payment Entry", "company_bank_account": bank_account, "posting_date": "2026-08-12", "references": [{"reference_doctype": "Payment Entry", "reference_name": payment_name, "amount": 1000, "bank_account": bank_account}]},
            expected={200},
        )
    )
    payment_order_name = str(payment_order["name"])
    created.append(("Payment Order", payment_order_name))
    assert response_data(client.public("GET", _path("/api/v1/accounts/payment-orders", payment_order_name), expected={200}))["name"] == payment_order_name
    client.public("PUT", _path("/api/v1/accounts/payment-orders", payment_order_name), {"posting_date": "2026-08-12"}, expected={200})
    client.public("POST", _path("/api/v1/accounts/payment-orders", payment_order_name) + "/submit", expected={200})
    client.public("POST", _path("/api/v1/accounts/payment-orders", payment_order_name) + "/cancel", expected={200})

    bank_transaction = response_data(
        client.public(
            "POST",
            "/api/v1/accounts/bank-transactions",
            {
                "date": "2026-08-12",
                "bank_account": bank_account,
                "currency": "VND",
                "deposit": 1000,
                "description": prefix + "bank statement",
                "reference_number": prefix + "reference",
            },
            expected={200},
        )
    )
    bank_transaction_name = str(bank_transaction["name"])
    created.append(("Bank Transaction", bank_transaction_name))
    assert response_data(
        client.public("GET", _path("/api/v1/accounts/bank-transactions", bank_transaction_name), expected={200})
    )["name"] == bank_transaction_name
    client.public(
        "PUT",
        _path("/api/v1/accounts/bank-transactions", bank_transaction_name),
        {"description": prefix + "updated"},
        expected={200},
    )
    before_failed_reconcile = response_data(
        client.public("GET", _path("/api/v1/accounts/bank-transactions", bank_transaction_name), expected={200})
    )
    client.public(
        "POST",
        _path("/api/v1/accounts/bank-transactions", bank_transaction_name) + "/reconcile",
        {"allocations": [{"payment_document": "Payment Entry", "payment_entry": prefix + "Missing"}]},
        expected={400, 404, 417},
    )
    after_failed_reconcile = response_data(
        client.public("GET", _path("/api/v1/accounts/bank-transactions", bank_transaction_name), expected={200})
    )
    assert after_failed_reconcile["docstatus"] == before_failed_reconcile["docstatus"]
    assert after_failed_reconcile.get("payment_entries", []) == before_failed_reconcile.get("payment_entries", [])
    reconciled = response_data(client.public("POST", _path("/api/v1/accounts/bank-transactions", bank_transaction_name) + "/reconcile", {"allocations": [{"payment_document": "Payment Entry", "payment_entry": payment_name}]}, expected={200}))
    assert reconciled["status"] == "Reconciled"
    assert reconciled["payment_entries"]
    unreconciled = response_data(client.public("POST", _path("/api/v1/accounts/bank-transactions", bank_transaction_name) + "/unreconcile", expected={200}))
    assert unreconciled["status"] == "Unreconciled"
    assert not unreconciled["payment_entries"]
