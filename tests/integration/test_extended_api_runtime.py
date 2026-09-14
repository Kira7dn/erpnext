"""Extended public API and business-flow acceptance on the Docker runtime."""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import pytest
from letron_api.delivery.delivery_protocol import webhook_signature

from .test_api_runtime_harness import (
    ApiClient,
    HealthUnavailable,
    cleanup,
    cleanup_consumer_events,
    create_or_reuse,
    response_data,
)

pytestmark = pytest.mark.integration

DELIVERY_ENV = (
    "LETRON_WEBHOOK_URL",
    "LETRON_WEBHOOK_SECRET",
    "LETRON_WEBHOOK_TIMEOUT_MS",
    "LETRON_REALTIME_URL",
    "LETRON_REALTIME_TOKEN",
)


def _path(base: str, name: str) -> str:
    return f"{base}/{quote(name, safe='')}"


def _host_consumer_url(url: str) -> str:
    port = os.environ.get("LETRON_CONSUMER_PORT", "8091")
    return url.replace("http://event-consumer:8090", f"http://127.0.0.1:{port}")


def _consumer_request(method: str, url: str, *, body: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    request = Request(url, data=body, method=method, headers={"Accept": "application/json", **(headers or {})})
    try:
        with urlopen(request, timeout=35) as response:
            return response.status, json.loads(response.read().decode())
    except HTTPError as error:
        return error.code, json.loads(error.read().decode())


def _create(client: ApiClient, route: str, payload: Mapping[str, object], created: list[tuple[str, str]], doctype: str) -> dict[str, Any]:
    document = response_data(client.public("POST", route, dict(payload), expected={200}))
    created.append((doctype, str(document["name"])))
    return document


def _assert_list_controls(client: ApiClient, route: str, name: str) -> None:
    query = urlencode(
        {
            "fields": json.dumps(["name", "modified"]),
            "filters": json.dumps([["name", "=", name]]),
            "order_by": "modified desc",
            "limit_start": 0,
            "limit_page_length": 1,
        }
    )
    listed = client.public("GET", f"{route}?{query}", expected={200})
    assert len(listed.data["data"]) == 1
    assert listed.data["data"][0]["name"] == name
    assert "modified" in listed.data["data"][0]

    no_match_query = urlencode(
        {
            "fields": json.dumps(["name"]),
            "filters": json.dumps([["name", "=", f"{name}-NO-MATCH"]]),
            "limit_start": 0,
            "limit_page_length": 1,
        }
    )
    no_match = client.public("GET", f"{route}?{no_match_query}", expected={200})
    assert no_match.data["data"] == []


def _update_and_assert(client: ApiClient, route: str, name: str, field: str, value: object) -> None:
    updated = response_data(client.public("PUT", _path(route, name), {field: value}, expected={200}))
    assert updated[field] == value
    persisted = response_data(client.public("GET", _path(route, name), expected={200}))
    assert persisted[field] == value


def _delete_and_assert(client: ApiClient, route: str, name: str) -> None:
    client.public("DELETE", _path(route, name), expected={200, 202})
    client.public("GET", _path(route, name), expected={404})


def test_extended_auth_system_resources_and_business_flows(request: pytest.FixtureRequest) -> None:
    client = ApiClient()
    try:
        client.health_and_login()
    except HealthUnavailable as error:
        pytest.skip(f"blocked runtime: {error}")

    prefix = f"ACCEPTANCE-LOCAL-{uuid.uuid4().hex[:8]}-"
    abbr = f"F{uuid.uuid4().hex[:3].upper()}"
    created: list[tuple[str, str]] = []
    consumer_event_ids: list[str] = []
    original_companies: list[dict[str, Any]] | None = None

    def finalize() -> None:
        if original_companies is not None:
            client.document("PUT", "Fiscal Year", "2026", {"companies": original_companies}, expected={200})
        cleanup(client, created, prefix)
        cleanup_consumer_events(prefix, consumer_event_ids)
        client.write_evidence()

    request.addfinalizer(finalize)

    # Runtime APIs remain authenticated; health is explicitly guest-safe.
    guest = ApiClient()
    guest.request("GET", "/api/method/letron_api.control.api.health", expected={200})
    guest.request("GET", "/api/method/letron_api.control.api.runtime_info", expected={401, 403})
    client.request("GET", "/api/method/letron_api.control.api.runtime_info", expected={200})
    client.request("GET", "/api/method/letron_api.control.api.runtime_snapshot", expected={200})

    # A run-scoped User gets native Frappe API keys. Evidence redaction excludes both values.
    token_user = prefix.lower() + "token@example.com"
    create_or_reuse(
        client,
        "User",
        {
            "name": token_user,
            "email": token_user,
            "first_name": "Acceptance",
            "enabled": 1,
            "send_welcome_email": 0,
            "roles": [{"role": "System Manager"}],
        },
        created,
    )
    keys = client.request(
        "POST",
        "/api/method/frappe.core.doctype.user.user.generate_keys",
        {"user": token_user},
        expected={200},
    ).data["message"]
    token = ApiClient()
    token.authorization = f"token {keys['api_key']}:{keys['api_secret']}"
    token.request("GET", "/api/method/letron_api.control.api.runtime_info", expected={200})
    wrong = ApiClient()
    wrong.authorization = "token invalid-key:invalid-secret"
    wrong.request("GET", "/api/method/letron_api.control.api.runtime_info", expected={401, 403})
    client.evidence.extend(token.evidence)
    client.evidence.extend(wrong.evidence)

    newly_covered_routes = (
        "/api/v1/selling/delivery-notes",
        "/api/v1/accounts/purchase-invoices",
        "/api/v1/accounts/payment-entries",
        "/api/v1/accounts/banks",
        "/api/v1/accounts/bank-accounts",
        "/api/v1/accounts/modes-of-payment",
        "/api/v1/accounts/cost-centers",
        "/api/v1/accounts/journal-entries",
        "/api/v1/accounts/payment-requests",
        "/api/v1/buying/suppliers",
        "/api/v1/buying/purchase-orders",
        "/api/v1/stock/items",
        "/api/v1/stock/warehouses",
        "/api/v1/contacts/addresses",
        "/api/v1/contacts/contacts",
        "/api/v1/stock/material-requests",
        "/api/v1/stock/purchase-receipts",
        "/api/v1/stock/stock-entries",
        "/api/v1/stock/item-prices",
    )
    for route in newly_covered_routes:
        guest.public("GET", route, expected={401, 403})

    limited_email = prefix.lower() + "restricted@example.com"
    limited_password = "Acceptance-local-user-2026!"
    create_or_reuse(
        client,
        "User",
        {
            "name": limited_email,
            "email": limited_email,
            "first_name": "Restricted",
            "new_password": limited_password,
            "enabled": 1,
            "send_welcome_email": 0,
            "roles": [{"role": "Employee"}],
        },
        created,
    )
    limited = ApiClient()
    limited.username = limited_email
    limited.password = limited_password
    limited.login()
    for route in newly_covered_routes:
        # Some ERPNext master data is intentionally readable by broad Desk
        # roles. Contacts also permits Employee creation natively: Address
        # reaches required-field validation and an empty Contact is valid.
        # Stock and the remaining modules reject before payload validation.
        if route == "/api/v1/contacts/contacts":
            restricted_contact = response_data(limited.public("POST", route, {}, expected={200}))
            created.append(("Contact", str(restricted_contact["name"])))
        elif route == "/api/v1/contacts/addresses":
            limited.public("POST", route, {}, expected={400, 417})
        else:
            limited.public("POST", route, {}, expected={403})
    client.evidence.extend(guest.evidence)
    client.evidence.extend(limited.evidence)

    accounts_user_email = prefix.lower() + "accounts-user@example.com"
    accounts_manager_email = prefix.lower() + "accounts-manager@example.com"
    accounts_password = "Acceptance-local-accounts-2026!"
    for email, role in (
        (accounts_user_email, "Accounts User"),
        (accounts_manager_email, "Accounts Manager"),
    ):
        create_or_reuse(
            client,
            "User",
            {
                "name": email,
                "email": email,
                "first_name": role,
                "new_password": accounts_password,
                "enabled": 1,
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            },
            created,
        )
    accounts_user = ApiClient()
    accounts_user.username = accounts_user_email
    accounts_user.password = accounts_password
    accounts_user.login()
    accounts_manager = ApiClient()
    accounts_manager.username = accounts_manager_email
    accounts_manager.password = accounts_password
    accounts_manager.login()

    # Native Accounts permissions remain authoritative behind public aliases.
    accounts_user.public("POST", "/api/v1/accounts/banks", {}, expected={403})
    accounts_manager.public("POST", "/api/v1/accounts/banks", {}, expected={403})
    accounts_user.public("POST", "/api/v1/accounts/modes-of-payment", {}, expected={403})
    accounts_manager.public("POST", "/api/v1/accounts/modes-of-payment", {}, expected={400, 417})
    accounts_user.public("POST", "/api/v1/accounts/cost-centers", {}, expected={403})
    accounts_user.public("POST", "/api/v1/accounts/journal-entries", {}, expected={400, 417})
    accounts_user.public("POST", "/api/v1/accounts/payment-requests", {}, expected={400, 417})
    client.evidence.extend(accounts_user.evidence)
    client.evidence.extend(accounts_manager.evidence)

    create_or_reuse(client, "Warehouse Type", {"name": "Transit", "warehouse_type_name": "Transit"}, created)
    company = create_or_reuse(
        client,
        "Company",
        {
            "name": prefix + "Company",
            "company_name": prefix + "Company",
            "abbr": abbr,
            "country": "Vietnam",
            "default_currency": "VND",
            "domain": "Distribution",
        },
        created,
    )
    fiscal_year = response_data(client.document("GET", "Fiscal Year", "2026", expected={200}))
    original_companies = [
        row
        for row in fiscal_year.get("companies", [])
        if row.get("company") and client.document("GET", "Company", row["company"], expected={200, 404}).status == 200
    ]
    if not any(row.get("company") == company for row in original_companies):
        client.document("PUT", "Fiscal Year", "2026", {"companies": [*original_companies, {"company": company}]}, expected={200})

    group = create_or_reuse(client, "Customer Group", {"name": prefix + "Customer Group", "customer_group_name": prefix + "Customer Group", "is_group": 0}, created)
    territory = create_or_reuse(client, "Territory", {"name": prefix + "Territory", "territory_name": prefix + "Territory", "is_group": 0}, created)
    item_group = create_or_reuse(client, "Item Group", {"name": prefix + "Item Group", "item_group_name": prefix + "Item Group", "is_group": 0}, created)
    supplier_group = create_or_reuse(client, "Supplier Group", {"name": prefix + "Supplier Group", "supplier_group_name": prefix + "Supplier Group", "is_group": 0}, created)
    create_or_reuse(client, "UOM", {"name": "Nos", "uom_name": "Nos", "enabled": 1}, created)
    price_list = create_or_reuse(client, "Price List", {"name": prefix + "Price List", "price_list_name": prefix + "Price List", "enabled": 1, "buying": 1, "selling": 1, "currency": "VND"}, created)
    fixture_country = "Vietnam"
    create_or_reuse(
        client,
        "Address Template",
        {"name": fixture_country, "country": fixture_country, "is_default": 1, "template": f"<!-- {prefix} -->{{{{ address_line1 }}}}<br>{{{{ city }}}}<br>{{{{ country }}}}"},
        created,
    )
    stock_entry_type = create_or_reuse(
        client,
        "Stock Entry Type",
        {"name": prefix + "Material Transfer", "purpose": "Material Transfer"},
        created,
    )
    cost_center = create_or_reuse(client, "Cost Center", {"name": prefix + f"Cost Center - {abbr}", "cost_center_name": prefix + "Cost Center", "company": company, "parent_cost_center": f"{company} - {abbr}", "is_group": 0}, created)

    warehouse = str(_create(client, "/api/v1/stock/warehouses", {"warehouse_name": prefix + "Warehouse", "company": company}, created, "Warehouse")["name"])
    target_warehouse = str(_create(client, "/api/v1/stock/warehouses", {"warehouse_name": prefix + "Target Warehouse", "company": company}, created, "Warehouse")["name"])
    item = str(_create(client, "/api/v1/stock/items", {"item_code": prefix + "Item", "item_name": "Lốp xe Đà Nẵng", "item_group": item_group, "stock_uom": "Nos", "is_stock_item": 0}, created, "Item")["name"])
    stock_item = str(_create(client, "/api/v1/stock/items", {"item_code": prefix + "Stock Item", "item_name": "Phụ tùng tồn kho Đà Nẵng", "item_group": item_group, "stock_uom": "Nos", "is_stock_item": 1, "valuation_rate": 1000}, created, "Item")["name"])
    customer = str(_create(client, "/api/v1/selling/customers", {"customer_name": prefix + "Khách hàng", "customer_group": group, "territory": territory, "customer_type": "Company"}, created, "Customer")["name"])
    supplier = str(_create(client, "/api/v1/buying/suppliers", {"supplier_name": prefix + "Nhà cung cấp", "supplier_group": supplier_group, "supplier_type": "Company"}, created, "Supplier")["name"])

    account_query = urlencode(
        {
            "filters": json.dumps([["company", "=", company], ["is_group", "=", 0]]),
            "fields": json.dumps(["name", "account_type", "root_type"]),
            "order_by": "name asc",
            "limit_page_length": 200,
        }
    )
    account_rows = client.request("GET", f"/api/resource/Account?{account_query}", expected={200}).data["data"]
    eligible_accounts = [
        row
        for row in account_rows
        if row.get("account_type") not in {"Receivable", "Payable", "Stock"}
        and row.get("root_type") in {"Asset", "Liability", "Equity"}
    ]
    eligible_accounts.sort(key=lambda row: (row.get("account_type") not in {"Bank", "Cash"}, row["name"]))
    assert len(eligible_accounts) >= 2, "native Company chart did not create two eligible ledger Accounts"
    primary_ledger_account = str(eligible_accounts[0]["name"])
    secondary_ledger_account = str(eligible_accounts[1]["name"])

    bank = _create(
        client,
        "/api/v1/accounts/banks",
        {"bank_name": prefix + "Ngân hàng Đà Nẵng", "swift_number": f"LT{abbr}01"},
        created,
        "Bank",
    )
    bank_name = str(bank["name"])
    _assert_list_controls(client, "/api/v1/accounts/banks", bank_name)
    assert response_data(client.public("GET", _path("/api/v1/accounts/banks", bank_name), expected={200}))["name"] == bank_name
    _update_and_assert(client, "/api/v1/accounts/banks", bank_name, "swift_number", f"LT{abbr}02")
    disposable_bank = str(
        _create(
            client,
            "/api/v1/accounts/banks",
            {"bank_name": prefix + "Ngân hàng xóa", "swift_number": f"LT{abbr}03"},
            created,
            "Bank",
        )["name"]
    )
    _delete_and_assert(client, "/api/v1/accounts/banks", disposable_bank)

    accounts_user_bank_account = response_data(
        accounts_user.public(
            "POST",
            "/api/v1/accounts/bank-accounts",
            {"account_name": prefix + "Accounts User permission", "bank": bank_name},
            expected={200},
        )
    )
    accounts_user_bank_account_name = str(accounts_user_bank_account["name"])
    created.append(("Bank Account", accounts_user_bank_account_name))
    accounts_user.public(
        "DELETE",
        _path("/api/v1/accounts/bank-accounts", accounts_user_bank_account_name),
        expected={200, 202},
    )
    accounts_user.public(
        "GET",
        _path("/api/v1/accounts/bank-accounts", accounts_user_bank_account_name),
        expected={404},
    )

    bank_account_payload = {
        "account_name": prefix + "Tài khoản ngân hàng",
        "bank": bank_name,
        "is_company_account": 1,
        "company": company,
        "account": primary_ledger_account,
        "branch_code": "DAD-01",
    }
    bank_account = _create(client, "/api/v1/accounts/bank-accounts", bank_account_payload, created, "Bank Account")
    bank_account_name = str(bank_account["name"])
    _assert_list_controls(client, "/api/v1/accounts/bank-accounts", bank_account_name)
    assert response_data(client.public("GET", _path("/api/v1/accounts/bank-accounts", bank_account_name), expected={200}))["name"] == bank_account_name
    _update_and_assert(client, "/api/v1/accounts/bank-accounts", bank_account_name, "branch_code", "DAD-02")
    disposable_bank_account = str(
        _create(
            client,
            "/api/v1/accounts/bank-accounts",
            {
                **bank_account_payload,
                "account_name": prefix + "Tài khoản ngân hàng xóa",
                "account": secondary_ledger_account,
            },
            created,
            "Bank Account",
        )["name"]
    )
    _delete_and_assert(client, "/api/v1/accounts/bank-accounts", disposable_bank_account)

    mode_payload = {
        "mode_of_payment": prefix + "Chuyển khoản",
        "type": "Bank",
        "enabled": 1,
        "accounts": [{"company": company, "default_account": primary_ledger_account}],
    }
    mode = _create(client, "/api/v1/accounts/modes-of-payment", mode_payload, created, "Mode of Payment")
    mode_name = str(mode["name"])
    _assert_list_controls(client, "/api/v1/accounts/modes-of-payment", mode_name)
    assert response_data(client.public("GET", _path("/api/v1/accounts/modes-of-payment", mode_name), expected={200}))["name"] == mode_name
    _update_and_assert(client, "/api/v1/accounts/modes-of-payment", mode_name, "enabled", 0)
    disposable_mode = str(
        _create(
            client,
            "/api/v1/accounts/modes-of-payment",
            {**mode_payload, "mode_of_payment": prefix + "Phương thức xóa"},
            created,
            "Mode of Payment",
        )["name"]
    )
    _delete_and_assert(client, "/api/v1/accounts/modes-of-payment", disposable_mode)

    cost_center_root = f"{company} - {abbr}"
    account_group = _create(
        client,
        "/api/v1/accounts/cost-centers",
        {"cost_center_name": prefix + "Khối vận hành", "company": company, "parent_cost_center": cost_center_root, "is_group": 1},
        created,
        "Cost Center",
    )
    account_group_name = str(account_group["name"])
    account_leaf = _create(
        client,
        "/api/v1/accounts/cost-centers",
        {"cost_center_name": prefix + "Chi nhánh Đà Nẵng", "company": company, "parent_cost_center": account_group_name, "is_group": 0},
        created,
        "Cost Center",
    )
    account_leaf_name = str(account_leaf["name"])
    _assert_list_controls(client, "/api/v1/accounts/cost-centers", account_leaf_name)
    assert response_data(client.public("GET", _path("/api/v1/accounts/cost-centers", account_leaf_name), expected={200}))["parent_cost_center"] == account_group_name
    _update_and_assert(client, "/api/v1/accounts/cost-centers", account_leaf_name, "disabled", 1)
    disposable_cost_group = str(
        _create(
            accounts_manager,
            "/api/v1/accounts/cost-centers",
            {"cost_center_name": prefix + "Nhóm xóa", "company": company, "parent_cost_center": cost_center_root, "is_group": 1},
            created,
            "Cost Center",
        )["name"]
    )
    disposable_cost_leaf = str(
        _create(
            accounts_manager,
            "/api/v1/accounts/cost-centers",
            {"cost_center_name": prefix + "Lá xóa", "company": company, "parent_cost_center": disposable_cost_group, "is_group": 0},
            created,
            "Cost Center",
        )["name"]
    )
    _delete_and_assert(accounts_manager, "/api/v1/accounts/cost-centers", disposable_cost_leaf)
    _delete_and_assert(accounts_manager, "/api/v1/accounts/cost-centers", disposable_cost_group)

    # Link and tree validation must stay native; no generic fallback sanitizes bad input.
    client.public("POST", "/api/v1/accounts/banks", {}, expected={400, 417})
    client.public("POST", "/api/v1/accounts/bank-accounts", {**bank_account_payload, "account_name": prefix + "Invalid Bank", "bank": prefix + "Missing Bank"}, expected={400, 404, 417})
    client.public("POST", "/api/v1/accounts/bank-accounts", {**bank_account_payload, "account_name": prefix + "Invalid Company", "company": prefix + "Missing Company"}, expected={400, 404, 417})
    client.public("POST", "/api/v1/accounts/bank-accounts", {**bank_account_payload, "account_name": prefix + "Invalid Account", "account": prefix + "Missing Account"}, expected={400, 404, 417})
    client.public("POST", "/api/v1/accounts/modes-of-payment", {"mode_of_payment": prefix + "Invalid Mode", "accounts": [{"company": company, "default_account": prefix + "Missing Account"}]}, expected={400, 404, 417})
    client.public("POST", "/api/v1/accounts/cost-centers", {"cost_center_name": prefix + "Invalid Parent", "company": company, "parent_cost_center": account_leaf_name, "is_group": 0}, expected={400, 417})

    address = _create(
        client,
        "/api/v1/contacts/addresses",
        {
            "address_title": prefix + "Khách hàng Đà Nẵng",
            "address_type": "Billing",
            "address_line1": "01 Đường Biển",
            "city": "Đà Nẵng",
            "country": fixture_country,
            "links": [{"link_doctype": "Customer", "link_name": customer}],
        },
        created,
        "Address",
    )
    address_name = str(address["name"])
    contact = _create(
        client,
        "/api/v1/contacts/contacts",
        {
            "first_name": prefix + "Liên hệ",
            "last_name": "Nhà cung cấp",
            "links": [{"link_doctype": "Supplier", "link_name": supplier}],
        },
        created,
        "Contact",
    )
    contact_name = str(contact["name"])

    # Updates must persist through the fields that belong to each native
    # DocType; accepting a validation error is not runtime coverage.
    _update_and_assert(client, "/api/v1/stock/warehouses", warehouse, "warehouse_type", "Transit")
    _update_and_assert(client, "/api/v1/stock/items", item, "item_name", "Lốp xe Đà Nẵng - cập nhật")
    _update_and_assert(client, "/api/v1/buying/suppliers", supplier, "supplier_details", "Nhà cung cấp Đà Nẵng - cập nhật")
    _update_and_assert(client, "/api/v1/selling/customers", customer, "customer_name", prefix + "Khách hàng cập nhật")
    _update_and_assert(client, "/api/v1/contacts/addresses", address_name, "city", "Hội An")
    _update_and_assert(client, "/api/v1/contacts/contacts", contact_name, "last_name", "Nhà cung cấp cập nhật")
    for route, name in (
        ("/api/v1/stock/warehouses", warehouse),
        ("/api/v1/stock/items", item),
        ("/api/v1/selling/customers", customer),
        ("/api/v1/buying/suppliers", supplier),
        ("/api/v1/contacts/addresses", address_name),
        ("/api/v1/contacts/contacts", contact_name),
    ):
        _assert_list_controls(client, route, name)

    disposable_supplier = str(
        _create(
            client,
            "/api/v1/buying/suppliers",
            {"supplier_name": prefix + "Delete Supplier", "supplier_group": supplier_group, "supplier_type": "Company"},
            created,
            "Supplier",
        )["name"]
    )
    _delete_and_assert(client, "/api/v1/buying/suppliers", disposable_supplier)
    disposable_item = str(
        _create(
            client,
            "/api/v1/stock/items",
            {"item_code": prefix + "Delete Item", "item_name": prefix + "Delete Item", "item_group": item_group, "stock_uom": "Nos", "is_stock_item": 0},
            created,
            "Item",
        )["name"]
    )
    _delete_and_assert(client, "/api/v1/stock/items", disposable_item)
    disposable_warehouse = str(
        _create(
            client,
            "/api/v1/stock/warehouses",
            {"warehouse_name": prefix + "Delete Warehouse", "company": company},
            created,
            "Warehouse",
        )["name"]
    )
    _delete_and_assert(client, "/api/v1/stock/warehouses", disposable_warehouse)
    disposable_address = str(
        _create(
            client,
            "/api/v1/contacts/addresses",
            {"address_title": prefix + "Delete Address", "address_type": "Billing", "address_line1": "02 Đường Biển", "city": "Huế", "country": fixture_country},
            created,
            "Address",
        )["name"]
    )
    _delete_and_assert(client, "/api/v1/contacts/addresses", disposable_address)
    disposable_contact = str(
        _create(
            client,
            "/api/v1/contacts/contacts",
            {"first_name": prefix + "Delete Contact", "last_name": "Disposable"},
            created,
            "Contact",
        )["name"]
    )
    _delete_and_assert(client, "/api/v1/contacts/contacts", disposable_contact)

    # Contacts keep native Dynamic Link validation; Dynamic Link itself is a
    # child schema and has no public CRUD route.
    client.public(
        "POST",
        "/api/v1/contacts/addresses",
        {"address_title": prefix + "Invalid Link", "address_type": "Billing", "address_line1": "03 Đường Biển", "city": "Huế", "country": fixture_country, "links": [{"link_doctype": "Customer", "link_name": prefix + "Missing"}]},
        expected={400, 404, 417},
    )
    client.public("POST", "/api/v1/contacts/addresses", {"address_type": "Billing"}, expected={400, 417})

    lines = [{"item_code": item, "qty": 1, "rate": 1000, "warehouse": warehouse}]
    quotation = _create(client, "/api/v1/selling/quotations", {"quotation_to": "Customer", "party_name": customer, "customer": customer, "company": company, "currency": "VND", "conversion_rate": 1, "selling_price_list": price_list, "price_list_currency": "VND", "plc_conversion_rate": 1, "transaction_date": "2026-08-10", "items": lines}, created, "Quotation")
    quote_item = quotation["items"][0]
    order_lines = [{**lines[0], "prevdoc_docname": quotation["name"], "quotation_item": quote_item["name"]}]
    sales_order = _create(client, "/api/v1/selling/sales-orders", {"customer": customer, "company": company, "currency": "VND", "conversion_rate": 1, "selling_price_list": price_list, "price_list_currency": "VND", "plc_conversion_rate": 1, "transaction_date": "2026-08-10", "delivery_date": "2026-08-10", "items": order_lines}, created, "Sales Order")
    so_name = str(sales_order["name"])
    submitted_order = response_data(client.public("POST", _path("/api/v1/selling/sales-orders", so_name) + "/submit", expected={200}))
    assert submitted_order["docstatus"] == 1
    so_item = submitted_order["items"][0]

    delivery_note = _create(client, "/api/v1/selling/delivery-notes", {"customer": customer, "company": company, "posting_date": "2026-08-10", "currency": "VND", "conversion_rate": 1, "selling_price_list": price_list, "price_list_currency": "VND", "plc_conversion_rate": 1, "items": [{**lines[0], "against_sales_order": so_name, "so_detail": so_item["name"]}]}, created, "Delivery Note")
    delivery_name = str(delivery_note["name"])
    _assert_list_controls(client, "/api/v1/selling/delivery-notes", delivery_name)
    assert response_data(client.public("GET", _path("/api/v1/selling/delivery-notes", delivery_name), expected={200}))["name"] == delivery_name
    client.public("PUT", _path("/api/v1/selling/delivery-notes", str(delivery_note["name"])), {"remarks": "Acceptance delivery draft"}, expected={200})

    sales_invoice = _create(client, "/api/v1/accounts/sales-invoices", {"customer": customer, "company": company, "posting_date": "2026-08-10", "currency": "VND", "conversion_rate": 1, "cost_center": cost_center, "items": [{**lines[0], "sales_order": so_name, "so_detail": so_item["name"]}]}, created, "Sales Invoice")
    si_name = str(sales_invoice["name"])
    assert response_data(client.public("POST", _path("/api/v1/accounts/sales-invoices", si_name) + "/submit", expected={200}))["docstatus"] == 1
    client.public("PUT", _path("/api/v1/accounts/sales-invoices", si_name), {"remarks": "forbidden"}, expected={400, 403, 417})
    assert response_data(client.public("POST", _path("/api/v1/accounts/sales-invoices", si_name) + "/cancel", expected={200}))["docstatus"] == 2
    client.public("POST", _path("/api/v1/accounts/sales-invoices", si_name) + "/cancel", expected={400, 417})
    client.public("DELETE", _path("/api/v1/selling/delivery-notes", str(delivery_note["name"])), expected={200, 202})
    assert response_data(client.public("POST", _path("/api/v1/selling/sales-orders", so_name) + "/cancel", expected={200}))["docstatus"] == 2

    purchase_order_payload = {"supplier": supplier, "company": company, "currency": "VND", "conversion_rate": 1, "buying_price_list": price_list, "price_list_currency": "VND", "plc_conversion_rate": 1, "transaction_date": "2026-08-10", "schedule_date": "2026-08-10", "items": lines}
    draft_po = _create(client, "/api/v1/buying/purchase-orders", purchase_order_payload, created, "Purchase Order")
    draft_po_name = str(draft_po["name"])
    _assert_list_controls(client, "/api/v1/buying/purchase-orders", draft_po_name)
    assert response_data(client.public("GET", _path("/api/v1/buying/purchase-orders", draft_po_name), expected={200}))["name"] == draft_po_name
    updated_schedule_date = "2026-08-11"
    updated_po_item = {**draft_po["items"][0], "schedule_date": updated_schedule_date}
    updated_po = response_data(
        client.public(
            "PUT",
            _path("/api/v1/buying/purchase-orders", draft_po_name),
            {
                "schedule_date": updated_schedule_date,
                "items": [updated_po_item],
            },
            expected={200},
        )
    )
    assert updated_po["schedule_date"] == updated_schedule_date
    persisted_po = response_data(client.public("GET", _path("/api/v1/buying/purchase-orders", draft_po_name), expected={200}))
    assert persisted_po["schedule_date"] == updated_schedule_date
    delete_po = str(_create(client, "/api/v1/buying/purchase-orders", purchase_order_payload, created, "Purchase Order")["name"])
    _delete_and_assert(client, "/api/v1/buying/purchase-orders", delete_po)

    purchase_order = _create(client, "/api/v1/buying/purchase-orders", purchase_order_payload, created, "Purchase Order")
    po_name = str(purchase_order["name"])
    submitted_po = response_data(client.public("POST", _path("/api/v1/buying/purchase-orders", po_name) + "/submit", expected={200}))
    assert submitted_po["docstatus"] == 1
    po_item = submitted_po["items"][0]
    purchase_invoice_items = [{**lines[0], "purchase_order": po_name, "po_detail": po_item["name"]}]
    purchase_invoice_payload = {"supplier": supplier, "company": company, "posting_date": "2026-08-10", "currency": "VND", "conversion_rate": 1, "items": purchase_invoice_items}
    draft_pi = _create(client, "/api/v1/accounts/purchase-invoices", purchase_invoice_payload, created, "Purchase Invoice")
    draft_pi_name = str(draft_pi["name"])
    _assert_list_controls(client, "/api/v1/accounts/purchase-invoices", draft_pi_name)
    assert response_data(client.public("GET", _path("/api/v1/accounts/purchase-invoices", draft_pi_name), expected={200}))["name"] == draft_pi_name
    _update_and_assert(client, "/api/v1/accounts/purchase-invoices", draft_pi_name, "remarks", "Acceptance purchase invoice draft")
    delete_pi = str(_create(client, "/api/v1/accounts/purchase-invoices", purchase_invoice_payload, created, "Purchase Invoice")["name"])
    _delete_and_assert(client, "/api/v1/accounts/purchase-invoices", delete_pi)

    purchase_invoice = _create(client, "/api/v1/accounts/purchase-invoices", purchase_invoice_payload, created, "Purchase Invoice")
    pi_name = str(purchase_invoice["name"])
    assert response_data(client.public("POST", _path("/api/v1/accounts/purchase-invoices", pi_name) + "/submit", expected={200}))["docstatus"] == 1
    assert response_data(client.public("POST", _path("/api/v1/accounts/purchase-invoices", pi_name) + "/cancel", expected={200}))["docstatus"] == 2
    assert response_data(client.public("POST", _path("/api/v1/buying/purchase-orders", po_name) + "/cancel", expected={200}))["docstatus"] == 2

    material_request_payload = {
        "material_request_type": "Purchase",
        "company": company,
        "transaction_date": "2026-08-10",
        "schedule_date": "2026-08-12",
        "items": [{"item_code": stock_item, "qty": 5, "warehouse": warehouse, "schedule_date": "2026-08-12"}],
    }
    draft_material_request = _create(client, "/api/v1/stock/material-requests", material_request_payload, created, "Material Request")
    material_request_name = str(draft_material_request["name"])
    _assert_list_controls(client, "/api/v1/stock/material-requests", material_request_name)
    assert response_data(client.public("GET", _path("/api/v1/stock/material-requests", material_request_name), expected={200}))["name"] == material_request_name
    material_request_item = {**draft_material_request["items"][0], "schedule_date": "2026-08-13"}
    updated_material_request = response_data(
        client.public(
            "PUT",
            _path("/api/v1/stock/material-requests", material_request_name),
            {"schedule_date": "2026-08-13", "items": [material_request_item]},
            expected={200},
        )
    )
    assert updated_material_request["items"][0]["schedule_date"] == "2026-08-13"
    persisted_material_request = response_data(client.public("GET", _path("/api/v1/stock/material-requests", material_request_name), expected={200}))
    assert persisted_material_request["items"][0]["schedule_date"] == "2026-08-13"
    delete_material_request = str(_create(client, "/api/v1/stock/material-requests", material_request_payload, created, "Material Request")["name"])
    _delete_and_assert(client, "/api/v1/stock/material-requests", delete_material_request)
    lifecycle_material_request = _create(client, "/api/v1/stock/material-requests", material_request_payload, created, "Material Request")
    lifecycle_material_request_name = str(lifecycle_material_request["name"])
    assert response_data(client.public("POST", _path("/api/v1/stock/material-requests", lifecycle_material_request_name) + "/submit", expected={200}))["docstatus"] == 1
    assert response_data(client.public("POST", _path("/api/v1/stock/material-requests", lifecycle_material_request_name) + "/cancel", expected={200}))["docstatus"] == 2

    stock_po_payload = {
        "supplier": supplier,
        "company": company,
        "currency": "VND",
        "conversion_rate": 1,
        "buying_price_list": price_list,
        "price_list_currency": "VND",
        "plc_conversion_rate": 1,
        "transaction_date": "2026-08-10",
        "schedule_date": "2026-08-12",
        "items": [{"item_code": stock_item, "qty": 5, "rate": 1000, "warehouse": warehouse, "schedule_date": "2026-08-12"}],
    }
    stock_po = _create(client, "/api/v1/buying/purchase-orders", stock_po_payload, created, "Purchase Order")
    stock_po_name = str(stock_po["name"])
    submitted_stock_po = response_data(client.public("POST", _path("/api/v1/buying/purchase-orders", stock_po_name) + "/submit", expected={200}))
    stock_po_item = submitted_stock_po["items"][0]

    receipt_payload = {
        "supplier": supplier,
        "company": company,
        "posting_date": "2026-08-10",
        "supplier_delivery_note": prefix + "Supplier Delivery Note",
        "currency": "VND",
        "conversion_rate": 1,
        "buying_price_list": price_list,
        "price_list_currency": "VND",
        "plc_conversion_rate": 1,
        "items": [{"item_code": stock_item, "qty": 5, "rate": 1000, "warehouse": warehouse, "purchase_order": stock_po_name, "purchase_order_item": stock_po_item["name"]}],
    }
    draft_receipt = _create(client, "/api/v1/stock/purchase-receipts", receipt_payload, created, "Purchase Receipt")
    draft_receipt_name = str(draft_receipt["name"])
    assert draft_receipt["supplier_delivery_note"] == prefix + "Supplier Delivery Note"
    _assert_list_controls(client, "/api/v1/stock/purchase-receipts", draft_receipt_name)
    assert response_data(client.public("GET", _path("/api/v1/stock/purchase-receipts", draft_receipt_name), expected={200}))["name"] == draft_receipt_name
    _update_and_assert(client, "/api/v1/stock/purchase-receipts", draft_receipt_name, "remarks", "Phiếu nhận hàng cập nhật")
    delete_receipt = str(_create(client, "/api/v1/stock/purchase-receipts", receipt_payload, created, "Purchase Receipt")["name"])
    _delete_and_assert(client, "/api/v1/stock/purchase-receipts", delete_receipt)
    lifecycle_receipt = _create(client, "/api/v1/stock/purchase-receipts", receipt_payload, created, "Purchase Receipt")
    lifecycle_receipt_name = str(lifecycle_receipt["name"])
    assert response_data(client.public("POST", _path("/api/v1/stock/purchase-receipts", lifecycle_receipt_name) + "/submit", expected={200}))["docstatus"] == 1

    stock_entry_payload = {
        "stock_entry_type": stock_entry_type,
        "purpose": "Material Transfer",
        "company": company,
        "from_warehouse": warehouse,
        "to_warehouse": target_warehouse,
        "posting_date": "2026-08-10",
        "items": [{"item_code": stock_item, "qty": 1, "s_warehouse": warehouse, "t_warehouse": target_warehouse}],
    }
    draft_stock_entry = _create(client, "/api/v1/stock/stock-entries", stock_entry_payload, created, "Stock Entry")
    draft_stock_entry_name = str(draft_stock_entry["name"])
    _assert_list_controls(client, "/api/v1/stock/stock-entries", draft_stock_entry_name)
    assert response_data(client.public("GET", _path("/api/v1/stock/stock-entries", draft_stock_entry_name), expected={200}))["name"] == draft_stock_entry_name
    _update_and_assert(client, "/api/v1/stock/stock-entries", draft_stock_entry_name, "remarks", "Điều chuyển kho cập nhật")
    delete_stock_entry = str(_create(client, "/api/v1/stock/stock-entries", stock_entry_payload, created, "Stock Entry")["name"])
    _delete_and_assert(client, "/api/v1/stock/stock-entries", delete_stock_entry)
    lifecycle_stock_entry = _create(client, "/api/v1/stock/stock-entries", stock_entry_payload, created, "Stock Entry")
    lifecycle_stock_entry_name = str(lifecycle_stock_entry["name"])
    assert response_data(client.public("POST", _path("/api/v1/stock/stock-entries", lifecycle_stock_entry_name) + "/submit", expected={200}))["docstatus"] == 1
    assert response_data(client.public("POST", _path("/api/v1/stock/stock-entries", lifecycle_stock_entry_name) + "/cancel", expected={200}))["docstatus"] == 2
    assert response_data(client.public("POST", _path("/api/v1/stock/purchase-receipts", lifecycle_receipt_name) + "/cancel", expected={200}))["docstatus"] == 2
    assert response_data(client.public("POST", _path("/api/v1/buying/purchase-orders", stock_po_name) + "/cancel", expected={200}))["docstatus"] == 2

    item_price_payload = {"item_code": stock_item, "uom": "Nos", "price_list": price_list, "currency": "VND", "price_list_rate": 1500}
    item_price = _create(client, "/api/v1/stock/item-prices", item_price_payload, created, "Item Price")
    item_price_name = str(item_price["name"])
    _assert_list_controls(client, "/api/v1/stock/item-prices", item_price_name)
    assert response_data(client.public("GET", _path("/api/v1/stock/item-prices", item_price_name), expected={200}))["name"] == item_price_name
    _update_and_assert(client, "/api/v1/stock/item-prices", item_price_name, "price_list_rate", 1750)
    delete_price_list = create_or_reuse(client, "Price List", {"name": prefix + "Delete Price List", "price_list_name": prefix + "Delete Price List", "enabled": 1, "buying": 1, "selling": 1, "currency": "VND"}, created)
    delete_item_price = str(_create(client, "/api/v1/stock/item-prices", {**item_price_payload, "price_list": delete_price_list}, created, "Item Price")["name"])
    _delete_and_assert(client, "/api/v1/stock/item-prices", delete_item_price)
    client.public("POST", "/api/v1/stock/item-prices", {"item_code": stock_item}, expected={400, 417})

    journal_payload = {
        "voucher_type": "Journal Entry",
        "posting_date": "2026-08-10",
        "company": company,
        "custom_remark": 0,
        "user_remark": prefix + "Bút toán cân bằng",
        "accounts": [
            {"account": primary_ledger_account, "debit_in_account_currency": 1000},
            {"account": secondary_ledger_account, "credit_in_account_currency": 1000},
        ],
    }
    journal = _create(client, "/api/v1/accounts/journal-entries", journal_payload, created, "Journal Entry")
    journal_name = str(journal["name"])
    _assert_list_controls(client, "/api/v1/accounts/journal-entries", journal_name)
    assert response_data(client.public("GET", _path("/api/v1/accounts/journal-entries", journal_name), expected={200}))["name"] == journal_name
    journal_remark = prefix + "Bút toán đã cập nhật"
    updated_journal = response_data(
        client.public(
            "PUT",
            _path("/api/v1/accounts/journal-entries", journal_name),
            {"custom_remark": 1, "remark": journal_remark},
            expected={200},
        )
    )
    assert updated_journal["custom_remark"] == 1 and updated_journal["remark"] == journal_remark
    persisted_journal = response_data(client.public("GET", _path("/api/v1/accounts/journal-entries", journal_name), expected={200}))
    assert persisted_journal["custom_remark"] == 1 and persisted_journal["remark"] == journal_remark
    disposable_journal = str(
        _create(
            client,
            "/api/v1/accounts/journal-entries",
            {**journal_payload, "user_remark": prefix + "Bút toán xóa"},
            created,
            "Journal Entry",
        )["name"]
    )
    _delete_and_assert(client, "/api/v1/accounts/journal-entries", disposable_journal)
    lifecycle_journal = _create(
        client,
        "/api/v1/accounts/journal-entries",
        {**journal_payload, "user_remark": prefix + "Bút toán lifecycle"},
        created,
        "Journal Entry",
    )
    lifecycle_journal_name = str(lifecycle_journal["name"])

    def active_gl_entries(voucher_no: str) -> list[dict[str, Any]]:
        query = urlencode(
            {
                "filters": json.dumps(
                    [
                        ["voucher_type", "=", "Journal Entry"],
                        ["voucher_no", "=", voucher_no],
                        ["is_cancelled", "=", 0],
                    ]
                ),
                "fields": json.dumps(["name", "account", "debit", "credit"]),
                "limit_page_length": 100,
            }
        )
        return client.request("GET", f"/api/resource/GL%20Entry?{query}", expected={200}).data["data"]

    assert active_gl_entries(lifecycle_journal_name) == []
    submitted_journal = response_data(
        accounts_user.public(
            "POST",
            _path("/api/v1/accounts/journal-entries", lifecycle_journal_name) + "/submit",
            expected={200},
        )
    )
    assert submitted_journal["docstatus"] == 1
    submitted_gl_entries = active_gl_entries(lifecycle_journal_name)
    assert submitted_gl_entries, "Journal Entry submit did not create active GL rows"
    client.public(
        "PUT",
        _path("/api/v1/accounts/journal-entries", lifecycle_journal_name),
        {"remark": prefix + "Mutation after submit"},
        expected={400, 403, 417},
    )
    cancelled_journal = response_data(
        accounts_user.public(
            "POST",
            _path("/api/v1/accounts/journal-entries", lifecycle_journal_name) + "/cancel",
            expected={200},
        )
    )
    assert cancelled_journal["docstatus"] == 2
    cancelled_gl_entries = active_gl_entries(lifecycle_journal_name)
    assert cancelled_gl_entries, "Journal Entry cancel did not create reversal GL rows"
    assert {row["name"] for row in cancelled_gl_entries} != {row["name"] for row in submitted_gl_entries}
    assert sum(float(row["debit"] or 0) for row in cancelled_gl_entries) == sum(
        float(row["credit"] or 0) for row in cancelled_gl_entries
    )
    client.public("POST", _path("/api/v1/accounts/journal-entries", journal_name) + "/amend", expected={404, 405})
    client.public("POST", "/api/v1/accounts/journal-entries", {}, expected={400, 417})
    unbalanced_journal = _create(
        client,
        "/api/v1/accounts/journal-entries",
        {
            **journal_payload,
            "user_remark": prefix + "Bút toán lệch",
            "accounts": [
                {"account": primary_ledger_account, "debit_in_account_currency": 1000},
                {"account": secondary_ledger_account, "credit_in_account_currency": 900},
            ],
        },
        created,
        "Journal Entry",
    )
    unbalanced_journal_name = str(unbalanced_journal["name"])
    client.public(
        "POST",
        _path("/api/v1/accounts/journal-entries", unbalanced_journal_name) + "/submit",
        expected={400, 417},
    )
    _delete_and_assert(client, "/api/v1/accounts/journal-entries", unbalanced_journal_name)
    client.public(
        "POST",
        "/api/v1/accounts/journal-entries",
        {
            **journal_payload,
            "user_remark": prefix + "Bút toán account lỗi",
            "accounts": [
                {"account": prefix + "Missing Account", "debit_in_account_currency": 1000},
                {"account": secondary_ledger_account, "credit_in_account_currency": 1000},
            ],
        },
        expected={400, 404, 417},
    )
    client.public("POST", "/api/v1/accounts/journal-entries", {**journal_payload, "company": prefix + "Missing Company"}, expected={400, 404, 417})

    def submitted_purchase_invoice(label: str, rate: int) -> dict[str, Any]:
        invoice = _create(
            client,
            "/api/v1/accounts/purchase-invoices",
            {
                "supplier": supplier,
                "company": company,
                "posting_date": "2026-08-10",
                "currency": "VND",
                "conversion_rate": 1,
                "remarks": prefix + label,
                "items": [{"item_code": item, "qty": 1, "rate": rate, "warehouse": warehouse}],
            },
            created,
            "Purchase Invoice",
        )
        return response_data(
            client.public(
                "POST",
                _path("/api/v1/accounts/purchase-invoices", str(invoice["name"])) + "/submit",
                expected={200},
            )
        )

    def payment_request_payload(invoice: Mapping[str, object], subject: str) -> dict[str, object]:
        return {
            "payment_request_type": "Outward",
            "transaction_date": "2026-08-10",
            "reference_doctype": "Purchase Invoice",
            "reference_name": invoice["name"],
            "grand_total": invoice["outstanding_amount"],
            "currency": invoice["currency"],
            "party_account_currency": invoice["party_account_currency"],
            "company": company,
            "party_type": "Supplier",
            "party": supplier,
            "subject": subject,
            "mute_email": 1,
        }

    draft_pr_invoice = submitted_purchase_invoice("Payment Request draft reference", 2100)
    payment_request = _create(
        client,
        "/api/v1/accounts/payment-requests",
        payment_request_payload(draft_pr_invoice, prefix + "Yêu cầu thanh toán Đà Nẵng"),
        created,
        "Payment Request",
    )
    payment_request_name = str(payment_request["name"])
    _assert_list_controls(client, "/api/v1/accounts/payment-requests", payment_request_name)
    assert response_data(client.public("GET", _path("/api/v1/accounts/payment-requests", payment_request_name), expected={200}))["status"] == "Draft"
    payment_request_subject = prefix + "Yêu cầu thanh toán cập nhật"
    _update_and_assert(client, "/api/v1/accounts/payment-requests", payment_request_name, "subject", payment_request_subject)

    delete_pr_invoice = submitted_purchase_invoice("Payment Request delete reference", 2200)
    disposable_payment_request = str(
        _create(
            client,
            "/api/v1/accounts/payment-requests",
            payment_request_payload(delete_pr_invoice, prefix + "Yêu cầu thanh toán xóa"),
            created,
            "Payment Request",
        )["name"]
    )
    _delete_and_assert(client, "/api/v1/accounts/payment-requests", disposable_payment_request)

    lifecycle_pr_invoice = submitted_purchase_invoice("Payment Request lifecycle reference", 2300)
    lifecycle_payment_request = _create(
        client,
        "/api/v1/accounts/payment-requests",
        payment_request_payload(lifecycle_pr_invoice, prefix + "Yêu cầu thanh toán lifecycle"),
        created,
        "Payment Request",
    )
    lifecycle_payment_request_name = str(lifecycle_payment_request["name"])
    accounts_user.public(
        "POST",
        _path("/api/v1/accounts/payment-requests", lifecycle_payment_request_name) + "/submit",
        expected={403},
    )
    submitted_payment_request = response_data(
        accounts_manager.public(
            "POST",
            _path("/api/v1/accounts/payment-requests", lifecycle_payment_request_name) + "/submit",
            expected={200},
        )
    )
    assert submitted_payment_request["docstatus"] == 1 and submitted_payment_request["status"] == "Initiated"
    accounts_manager.public(
        "PUT",
        _path("/api/v1/accounts/payment-requests", lifecycle_payment_request_name),
        {"subject": prefix + "Mutation after submit"},
        expected={400, 403, 417},
    )
    cancelled_payment_request = response_data(
        accounts_manager.public(
            "POST",
            _path("/api/v1/accounts/payment-requests", lifecycle_payment_request_name) + "/cancel",
            expected={200},
        )
    )
    assert cancelled_payment_request["docstatus"] == 2 and cancelled_payment_request["status"] == "Cancelled"
    client.public("POST", _path("/api/v1/accounts/payment-requests", payment_request_name) + "/amend", expected={404, 405})
    client.public("POST", "/api/v1/accounts/payment-requests", {}, expected={400, 417})
    client.public(
        "POST",
        "/api/v1/accounts/payment-requests",
        {
            **payment_request_payload(draft_pr_invoice, prefix + "Invalid reference"),
            "reference_name": prefix + "Missing Purchase Invoice",
        },
        expected={400, 404, 417},
    )

    client.evidence.extend(accounts_user.evidence)
    client.evidence.extend(accounts_manager.evidence)

    # Payment Entry exercises Link and child-table persistence without inventing a lifecycle action.
    company_doc = response_data(client.document("GET", "Company", company, expected={200}))
    cash_query = urlencode({"filters": json.dumps([["company", "=", company], ["account_type", "=", "Cash"], ["is_group", "=", 0]]), "fields": json.dumps(["name"]), "limit_page_length": 1})
    cash_rows = client.request("GET", f"/api/resource/Account?{cash_query}", expected={200}).data["data"]
    assert cash_rows, "native Company chart did not create a usable Cash account"
    cash_account = cash_rows[0]["name"]
    payment = _create(client, "/api/v1/accounts/payment-entries", {"payment_type": "Receive", "party_type": "Customer", "party": customer, "company": company, "posting_date": "2026-08-10", "paid_from": company_doc["default_receivable_account"], "paid_to": cash_account, "paid_amount": 1000, "received_amount": 1000, "reference_no": prefix + "Payment", "reference_date": "2026-08-10", "references": []}, created, "Payment Entry")
    payment_name = str(payment["name"])
    _assert_list_controls(client, "/api/v1/accounts/payment-entries", payment_name)
    client.public("GET", _path("/api/v1/accounts/payment-entries", payment_name), expected={200})
    payment_remarks = "Acceptance payment draft"
    updated_payment = response_data(
        client.public(
            "PUT",
            _path("/api/v1/accounts/payment-entries", payment_name),
            {"custom_remarks": 1, "remarks": payment_remarks},
            expected={200},
        )
    )
    assert updated_payment["remarks"] == payment_remarks
    persisted_payment = response_data(client.public("GET", _path("/api/v1/accounts/payment-entries", payment_name), expected={200}))
    assert persisted_payment["remarks"] == payment_remarks
    delete_payment_payload = {"payment_type": "Receive", "party_type": "Customer", "party": customer, "company": company, "posting_date": "2026-08-10", "paid_from": company_doc["default_receivable_account"], "paid_to": cash_account, "paid_amount": 2000, "received_amount": 2000, "reference_no": prefix + "Delete Payment", "reference_date": "2026-08-10", "references": []}
    delete_payment = str(_create(client, "/api/v1/accounts/payment-entries", delete_payment_payload, created, "Payment Entry")["name"])
    _delete_and_assert(client, "/api/v1/accounts/payment-entries", delete_payment)

    # Invalid links and unexposed actions fail through native error mapping.
    client.public("POST", "/api/v1/selling/sales-orders", {"customer": prefix + "Missing", "company": company, "items": lines}, expected={400, 404, 417})
    client.public("POST", _path("/api/v1/accounts/purchase-invoices", pi_name) + "/amend", expected={404, 405})

    concurrent_payload = {"customer_name": prefix + "Concurrent", "customer_group": group, "territory": territory, "customer_type": "Company"}
    concurrent_key = f"acceptance-concurrent-{uuid.uuid4()}"
    concurrent_clients = [ApiClient(), ApiClient()]
    for concurrent_client in concurrent_clients:
        concurrent_client.authenticate()
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda concurrent_client: concurrent_client.public(
                    "POST",
                    "/api/v1/selling/customers",
                    concurrent_payload,
                    headers={"X-Idempotency-Key": concurrent_key},
                ),
                concurrent_clients,
            )
        )
    assert sorted(response.status for response in responses) == [200, 409]
    concurrent_name = str(response_data(next(response for response in responses if response.status == 200))["name"])
    created.append(("Customer", concurrent_name))

    upload_name = prefix + "upload-đà-nẵng.txt"
    uploaded = client.upload(upload_name, "Nội dung UTF-8 acceptance".encode(), attached_to_doctype="Supplier", attached_to_name=supplier, expected={200})
    assert uploaded.data["message"]["file_name"] == upload_name
    file_query = urlencode({"filters": json.dumps([["file_name", "=", upload_name]]), "fields": json.dumps(["name"])})
    files = client.request("GET", f"/api/resource/File?{file_query}", expected={200})
    assert files.data["data"]
    created.append(("File", files.data["data"][0]["name"]))

    # The outbox is persisted in the same transaction as each business change.
    outbox_query = urlencode({"filters": json.dumps([["payload", "like", f"%{prefix}%"]]), "fields": json.dumps(["event_id", "event_type", "resource_doctype", "document_name", "delivery_state", "webhook_attempts", "realtime_attempts", "payload"]), "limit_page_length": 500})
    outbox = client.request("GET", f"/api/resource/Letron%20Event%20Outbox?{outbox_query}", expected={200}).data["data"]
    assert outbox
    consumer_event_ids.extend(str(row["event_id"]) for row in outbox)
    assert {row["event_type"] for row in outbox} >= {"create", "update", "submit", "cancel"}
    assert {row["resource_doctype"] for row in outbox} >= {
        "Bank",
        "Bank Account",
        "Mode of Payment",
        "Cost Center",
        "Journal Entry",
        "Payment Request",
    }
    assert len({row["event_id"] for row in outbox}) == len(outbox)
    for row in outbox:
        payload = json.loads(row["payload"])
        assert payload["event_id"] == row["event_id"]
        assert payload["request_id"] and payload["occurred_at"]
        assert payload["resource_url"].startswith("/api/v1/")

    delivery_enabled = str(os.environ.get("LETRON_DELIVERY_ENABLED", "false")).lower() in {
        "1",
        "true",
        "yes",
    }
    if delivery_enabled and all(os.environ.get(name) for name in DELIVERY_ENV):
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            outbox = client.request("GET", f"/api/resource/Letron%20Event%20Outbox?{outbox_query}", expected={200}).data["data"]
            if outbox and all(row["delivery_state"] == "Delivered" for row in outbox):
                break
            time.sleep(0.5)
        assert outbox and all(row["delivery_state"] == "Delivered" for row in outbox)
        assert all(1 <= row["webhook_attempts"] <= 3 for row in outbox)
        assert all(1 <= row["realtime_attempts"] <= 3 for row in outbox)

        sample = outbox[0]
        raw_body = sample["payload"].encode("utf-8")
        webhook_url = _host_consumer_url(os.environ["LETRON_WEBHOOK_URL"])
        invalid_status, _ = _consumer_request(
            "POST",
            webhook_url,
            body=raw_body,
            headers={"Content-Type": "application/json", "X-Letron-Signature": "sha256=invalid"},
        )
        assert invalid_status == 401
        signature = webhook_signature(os.environ["LETRON_WEBHOOK_SECRET"], raw_body)
        for _ in range(2):
            status, acknowledgement = _consumer_request(
                "POST",
                webhook_url,
                body=raw_body,
                headers={"Content-Type": "application/json", "X-Letron-Signature": signature},
            )
            assert status == 200 and acknowledgement["acknowledged"] is True

        token_header = {"Authorization": f"Bearer {os.environ['LETRON_REALTIME_TOKEN']}"}
        realtime_url = _host_consumer_url(os.environ["LETRON_REALTIME_URL"])
        probe_status, probe = _consumer_request(
            "GET",
            realtime_url.replace("/realtime", "/probe") + "?" + urlencode({"event_id": sample["event_id"]}),
            headers=token_header,
        )
        assert probe_status == 200
        assert probe["channels"] == ["realtime", "webhook"]
        assert probe["business_effect_count"] == 1

        sequence = int(probe["sequence"])
        stream_status, stream = _consumer_request(
            "GET",
            realtime_url + "?" + urlencode({"after": max(0, sequence - 1), "wait_ms": 100}),
            headers=token_header,
        )
        assert stream_status == 200
        streamed_event_ids = [event["payload"]["event_id"] for event in stream["events"]]
        assert streamed_event_ids[0] == sample["event_id"]
        cursor = stream["cursor"]
        for _ in range(10):
            reconnect_status, reconnect = _consumer_request(
                "GET",
                realtime_url + "?" + urlencode({"after": cursor, "wait_ms": 100}),
                headers=token_header,
            )
            assert reconnect_status == 200
            if not reconnect["events"]:
                break
            streamed_event_ids.extend(event["payload"]["event_id"] for event in reconnect["events"])
            cursor = reconnect["cursor"]
        else:
            pytest.fail("realtime reconnect did not drain within 10 cursor pages")
        assert streamed_event_ids.count(sample["event_id"]) == 1


@pytest.mark.external_delivery
def test_external_delivery_gate_is_configured() -> None:
    missing = [name for name in DELIVERY_ENV if not os.environ.get(name)]
    if missing:
        pytest.fail("blocked external: staging delivery configuration is missing: " + ", ".join(missing))
