"""Public API acceptance against the actual ERPNext/Frappe Docker runtime."""

from __future__ import annotations

import uuid
from urllib.parse import quote

import pytest

from .test_api_runtime_harness import (
    ApiClient,
    RuntimeUnavailable,
    cleanup,
    cleanup_consumer_events,
    create_or_reuse,
    response_data,
)

pytestmark = pytest.mark.integration


def test_public_contract_and_lifecycle(request: pytest.FixtureRequest) -> None:
    client = ApiClient()
    try:
        client.health_and_login()
    except RuntimeUnavailable as error:
        pytest.fail(f"blocked runtime: {error}")
    snapshot = client.request("GET", "/api/method/letron_api.control.api.runtime_snapshot", expected={200})
    installed_apps = snapshot.data.get("message", {}).get("installed_apps", [])
    assert {"frappe", "erpnext", "letron_api"}.issubset(installed_apps)
    unauthenticated = ApiClient()
    unauthenticated.public("GET", "/api/v1/selling/customers", expected={401})
    client.evidence.extend(unauthenticated.evidence)
    explicit = client.request("GET", "/api/method/letron_api.control.api.health", expected={200}, headers={"X-Request-Id": "acceptance-explicit-request-id"})
    assert explicit.request_id == "acceptance-explicit-request-id"

    created: list[tuple[str, str]] = []
    prefix = f"ACCEPTANCE-LOCAL-{uuid.uuid4().hex[:8]}-"
    abbr = f"P{uuid.uuid4().hex[:3].upper()}"
    original_companies: list[dict[str, object]] | None = None

    def finalize() -> None:
        if original_companies is not None:
            client.document("PUT", "Fiscal Year", "2026", {"companies": original_companies}, expected={200})
        cleanup(client, created, prefix)
        cleanup_consumer_events(prefix)
        client.write_evidence()

    request.addfinalizer(finalize)
    create_or_reuse(client, "Warehouse Type", {"name": "Transit", "warehouse_type_name": "Transit"}, created)
    company = create_or_reuse(client, "Company", {"name": prefix + "Company", "company_name": prefix + "Company", "abbr": abbr, "country": "Vietnam", "default_currency": "VND", "domain": "Distribution"}, created)
    fiscal_year = response_data(client.document("GET", "Fiscal Year", "2026", expected={200}))
    original_companies = []
    for row in fiscal_year.get("companies", []):
        if row.get("company") and client.document("GET", "Company", row["company"], expected={200, 404}).status == 200:
            original_companies.append(row)
    if not any(row.get("company") == company for row in original_companies):
        client.document("PUT", "Fiscal Year", "2026", {"companies": [*original_companies, {"company": company}]}, expected={200})
    cost_center = create_or_reuse(client, "Cost Center", {"name": prefix + f"Cost Center - {abbr}", "cost_center_name": prefix + "Cost Center", "company": company, "parent_cost_center": f"{company} - {abbr}", "is_group": 0}, created)
    warehouse = create_or_reuse(client, "Warehouse", {"name": prefix + "Warehouse - P4", "warehouse_name": prefix + "Warehouse", "company": company}, created)
    group = create_or_reuse(client, "Customer Group", {"name": prefix + "Customer Group", "customer_group_name": prefix + "Customer Group", "is_group": 0}, created)
    territory = create_or_reuse(client, "Territory", {"name": prefix + "Territory", "territory_name": prefix + "Territory", "is_group": 0}, created)
    item_group = create_or_reuse(client, "Item Group", {"name": prefix + "Item Group", "item_group_name": prefix + "Item Group", "is_group": 0}, created)
    create_or_reuse(client, "UOM", {"name": "Nos", "uom_name": "Nos", "enabled": 1}, created)
    item = create_or_reuse(client, "Item", {"item_code": prefix + "Item", "item_name": prefix + "Item", "item_group": item_group, "stock_uom": "Nos", "is_stock_item": 0}, created)
    price_list = create_or_reuse(client, "Price List", {"name": prefix + "Price List", "price_list_name": prefix + "Price List", "enabled": 1, "buying": 0, "selling": 1, "currency": "VND"}, created)
    customer = {"name": prefix + "Customer", "customer_name": prefix + "Customer", "customer_group": group, "territory": territory, "customer_type": "Company"}
    limited_email = prefix.lower() + "user@example.com"
    limited_password = "Acceptance-local-user-2026!"
    create_or_reuse(client, "User", {"name": limited_email, "email": limited_email, "first_name": "Acceptance", "new_password": limited_password, "enabled": 1, "send_welcome_email": 0, "roles": [{"role": "Employee"}]}, created)
    limited = ApiClient()
    limited.username = limited_email
    limited.password = limited_password
    limited.login()
    limited.public("POST", "/api/v1/selling/customers", customer, expected={403})
    client.evidence.extend(limited.evidence)

    # The four public routes are exercised with native Link and child-table fields.
    customer_name = response_data(client.public("POST", "/api/v1/selling/customers", customer, expected={200}, headers={"X-Idempotency-Key": f"acceptance-customer-{prefix}"}))["name"]
    customer_path = quote(customer_name, safe="")
    created.append(("Customer", customer_name))
    duplicate = client.public("POST", "/api/v1/selling/customers", customer, expected={409}, headers={"X-Idempotency-Key": f"acceptance-customer-{prefix}"})
    assert duplicate.status == 409
    assert client.document("GET", "Customer", customer_name, expected={200}).request_id
    client.public("GET", "/api/v1/selling/customers", expected={200})
    client.public("PUT", f"/api/v1/selling/customers/{customer_path}", {"customer_name": prefix + "Customer Updated"}, expected={200})
    deletable_customer = response_data(client.public("POST", "/api/v1/selling/customers", {**customer, "name": prefix + "Delete Customer", "customer_name": prefix + "Delete Customer"}, expected={200}))["name"]
    created.append(("Customer", deletable_customer))
    deleted_customer = client.public("DELETE", f"/api/v1/selling/customers/{quote(deletable_customer, safe='')}", expected={200, 202, 417})
    if deleted_customer.status in {200, 202}:
        client.public("GET", f"/api/v1/selling/customers/{quote(deletable_customer, safe='')}", expected={404})

    lines = [{"item_code": item, "qty": 1, "rate": 1000, "warehouse": warehouse}]
    quotation = response_data(client.public("POST", "/api/v1/selling/quotations", {"customer": customer_name, "company": company, "selling_price_list": price_list, "transaction_date": "2026-08-10", "items": lines}, expected={200}))["name"]
    client.public("GET", "/api/v1/selling/quotations", expected={200})
    client.public("GET", f"/api/v1/selling/quotations/{quotation}", expected={200})
    client.public("PUT", f"/api/v1/selling/quotations/{quotation}", {"remarks": "acceptance"}, expected={200})
    client.public("DELETE", f"/api/v1/selling/quotations/{quotation}", expected={200, 202, 417})

    order = response_data(client.public("POST", "/api/v1/selling/sales-orders", {"customer": customer_name, "company": company, "transaction_date": "2026-08-10", "delivery_date": "2026-08-10", "items": lines}, expected={200}))["name"]
    client.public("GET", "/api/v1/selling/sales-orders", expected={200})
    client.public("GET", f"/api/v1/selling/sales-orders/{order}", expected={200})
    client.public("PUT", f"/api/v1/selling/sales-orders/{order}", {"remarks": "acceptance"}, expected={200})
    client.public("DELETE", f"/api/v1/selling/sales-orders/{order}", expected={200, 202, 417})

    invoice = response_data(client.public("POST", "/api/v1/accounts/sales-invoices", {"customer": customer_name, "company": company, "posting_date": "2026-08-10", "currency": "VND", "items": lines, "cost_center": cost_center}, expected={200}))["name"]
    assert client.reconcile(f"/api/v1/accounts/sales-invoices/{invoice}", expected={200}).status == 200
    assert client.public("GET", "/api/v1/accounts/sales-invoices", expected={200}).data["data"]
    detail = response_data(client.public("GET", f"/api/v1/accounts/sales-invoices/{invoice}", expected={200}))
    assert detail["name"] == invoice and detail["items"][0]["item_code"] == item
    client.public("PUT", f"/api/v1/accounts/sales-invoices/{invoice}", {"remarks": "acceptance"}, expected={200})
    submitted = response_data(client.public("POST", f"/api/v1/accounts/sales-invoices/{invoice}/submit", expected={200}))
    assert submitted["docstatus"] == 1
    cancelled = response_data(client.public("POST", f"/api/v1/accounts/sales-invoices/{invoice}/cancel", expected={200}))
    assert cancelled["docstatus"] == 2
    client.public("POST", f"/api/v1/accounts/sales-invoices/{invoice}/amend", expected={404, 405})
    deleted_invoice = client.public("DELETE", f"/api/v1/accounts/sales-invoices/{invoice}", expected={200, 202, 417})
    if deleted_invoice.status in {200, 202}:
        client.public("GET", f"/api/v1/accounts/sales-invoices/{invoice}", expected={404})

    # Error contract and retry policy: validation is not retried, and its key is released.
    bad_key = f"acceptance-bad-{uuid.uuid4()}"
    client.public("POST", "/api/v1/selling/customers", {"customer_name": ""}, expected={400, 417}, headers={"X-Idempotency-Key": bad_key})
    client.public("POST", "/api/v1/selling/customers", {"customer_name": "acceptance-retry", "customer_group": group, "territory": territory, "customer_type": "Company"}, expected={200}, headers={"X-Idempotency-Key": bad_key})
    assert client.request_with_retry("GET", "/api/v1/selling/customers/ACCEPTANCE-NOT-FOUND", attempts=1).status == 404
    client.public("GET", "/api/v1/selling/customers/ACCEPTANCE-NOT-FOUND", expected={404})
