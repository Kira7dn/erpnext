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
from letron_api.delivery_protocol import webhook_signature

from .api_runtime_harness import (
    ApiClient,
    RuntimeUnavailable,
    cleanup,
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
            "fields": json.dumps(["name"]),
            "filters": json.dumps([["name", "=", name]]),
            "order_by": "modified desc",
            "limit_start": 0,
            "limit_page_length": 1,
        }
    )
    listed = client.public("GET", f"{route}?{query}", expected={200})
    assert listed.data["data"] == [{"name": name}]


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
    except RuntimeUnavailable as error:
        pytest.fail(f"blocked runtime: {error}")

    prefix = f"ACCEPTANCE-LOCAL-{uuid.uuid4().hex[:8]}-"
    abbr = f"F{uuid.uuid4().hex[:3].upper()}"
    created: list[tuple[str, str]] = []
    consumer_event_ids: list[str] = []

    # Runtime APIs remain authenticated; health is explicitly guest-safe.
    guest = ApiClient()
    guest.request("GET", "/api/method/letron_api.api.health", expected={200})
    guest.request("GET", "/api/method/letron_api.api.runtime_info", expected={401, 403})
    client.request("GET", "/api/method/letron_api.api.runtime_info", expected={200})
    client.request("GET", "/api/method/letron_api.api.runtime_snapshot", expected={200})

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
    token.request("GET", "/api/method/letron_api.api.runtime_info", expected={200})
    wrong = ApiClient()
    wrong.authorization = "token invalid-key:invalid-secret"
    wrong.request("GET", "/api/method/letron_api.api.runtime_info", expected={401, 403})
    client.evidence.extend(token.evidence)
    client.evidence.extend(wrong.evidence)

    newly_covered_routes = (
        "/api/v1/selling/delivery-notes",
        "/api/v1/accounts/purchase-invoices",
        "/api/v1/accounts/payment-entries",
        "/api/v1/buying/suppliers",
        "/api/v1/buying/purchase-orders",
        "/api/v1/stock/items",
        "/api/v1/stock/warehouses",
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
        # roles. A write probe is the stable permission boundary for this
        # restricted user and must fail before payload validation.
        limited.public("POST", route, {}, expected={403})
    client.evidence.extend(guest.evidence)
    client.evidence.extend(limited.evidence)

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

    def finalize() -> None:
        client.document("PUT", "Fiscal Year", "2026", {"companies": original_companies}, expected={200})
        cleanup(client, created, prefix)
        if all(os.environ.get(name) for name in DELIVERY_ENV):
            time.sleep(2)
            realtime_url = _host_consumer_url(os.environ["LETRON_REALTIME_URL"])
            cleanup_status, _ = _consumer_request(
                "DELETE",
                realtime_url.replace("/realtime", "/events"),
                body=json.dumps({"event_ids": consumer_event_ids, "prefix": prefix}).encode(),
                headers={
                    "Authorization": f"Bearer {os.environ['LETRON_REALTIME_TOKEN']}",
                    "Content-Type": "application/json",
                },
            )
            assert cleanup_status == 200
        client.write_evidence()

    request.addfinalizer(finalize)

    group = create_or_reuse(client, "Customer Group", {"name": prefix + "Customer Group", "customer_group_name": prefix + "Customer Group", "is_group": 0}, created)
    territory = create_or_reuse(client, "Territory", {"name": prefix + "Territory", "territory_name": prefix + "Territory", "is_group": 0}, created)
    item_group = create_or_reuse(client, "Item Group", {"name": prefix + "Item Group", "item_group_name": prefix + "Item Group", "is_group": 0}, created)
    supplier_group = create_or_reuse(client, "Supplier Group", {"name": prefix + "Supplier Group", "supplier_group_name": prefix + "Supplier Group", "is_group": 0}, created)
    create_or_reuse(client, "UOM", {"name": "Nos", "uom_name": "Nos", "enabled": 1}, created)
    price_list = create_or_reuse(client, "Price List", {"name": prefix + "Price List", "price_list_name": prefix + "Price List", "enabled": 1, "buying": 1, "selling": 1, "currency": "VND"}, created)
    cost_center = create_or_reuse(client, "Cost Center", {"name": prefix + f"Cost Center - {abbr}", "cost_center_name": prefix + "Cost Center", "company": company, "parent_cost_center": f"{company} - {abbr}", "is_group": 0}, created)

    warehouse = str(_create(client, "/api/v1/stock/warehouses", {"warehouse_name": prefix + "Warehouse", "company": company}, created, "Warehouse")["name"])
    item = str(_create(client, "/api/v1/stock/items", {"item_code": prefix + "Item", "item_name": "Lốp xe Đà Nẵng", "item_group": item_group, "stock_uom": "Nos", "is_stock_item": 0}, created, "Item")["name"])
    customer = str(_create(client, "/api/v1/selling/customers", {"customer_name": prefix + "Khách hàng", "customer_group": group, "territory": territory, "customer_type": "Company"}, created, "Customer")["name"])
    supplier = str(_create(client, "/api/v1/buying/suppliers", {"supplier_name": prefix + "Nhà cung cấp", "supplier_group": supplier_group, "supplier_type": "Company"}, created, "Supplier")["name"])

    # Updates must persist through the fields that belong to each native
    # DocType; accepting a validation error is not runtime coverage.
    _update_and_assert(client, "/api/v1/stock/warehouses", warehouse, "warehouse_type", "Transit")
    _update_and_assert(client, "/api/v1/stock/items", item, "item_name", "Lốp xe Đà Nẵng - cập nhật")
    _update_and_assert(client, "/api/v1/buying/suppliers", supplier, "supplier_details", "Nhà cung cấp Đà Nẵng - cập nhật")
    _update_and_assert(client, "/api/v1/selling/customers", customer, "customer_name", prefix + "Khách hàng cập nhật")
    for route, name in (
        ("/api/v1/stock/warehouses", warehouse),
        ("/api/v1/stock/items", item),
        ("/api/v1/selling/customers", customer),
        ("/api/v1/buying/suppliers", supplier),
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
    purchase_invoice_payload = {"supplier": supplier, "company": company, "posting_date": "2026-08-10", "currency": "VND", "conversion_rate": 1, "items": lines}
    draft_pi = _create(client, "/api/v1/accounts/purchase-invoices", purchase_invoice_payload, created, "Purchase Invoice")
    draft_pi_name = str(draft_pi["name"])
    _assert_list_controls(client, "/api/v1/accounts/purchase-invoices", draft_pi_name)
    assert response_data(client.public("GET", _path("/api/v1/accounts/purchase-invoices", draft_pi_name), expected={200}))["name"] == draft_pi_name
    _update_and_assert(client, "/api/v1/accounts/purchase-invoices", draft_pi_name, "remarks", "Acceptance purchase invoice draft")
    delete_pi = str(_create(client, "/api/v1/accounts/purchase-invoices", purchase_invoice_payload, created, "Purchase Invoice")["name"])
    _delete_and_assert(client, "/api/v1/accounts/purchase-invoices", delete_pi)

    purchase_invoice = _create(client, "/api/v1/accounts/purchase-invoices", {**purchase_invoice_payload, "items": [{**lines[0], "purchase_order": po_name, "po_detail": po_item["name"]}]}, created, "Purchase Invoice")
    pi_name = str(purchase_invoice["name"])
    assert response_data(client.public("POST", _path("/api/v1/accounts/purchase-invoices", pi_name) + "/submit", expected={200}))["docstatus"] == 1
    assert response_data(client.public("POST", _path("/api/v1/accounts/purchase-invoices", pi_name) + "/cancel", expected={200}))["docstatus"] == 2
    assert response_data(client.public("POST", _path("/api/v1/buying/purchase-orders", po_name) + "/cancel", expected={200}))["docstatus"] == 2

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
        concurrent_client.login()
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
    uploaded = client.upload(upload_name, "Nội dung UTF-8 acceptance".encode(), expected={200})
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
    assert len({row["event_id"] for row in outbox}) == len(outbox)
    for row in outbox:
        payload = json.loads(row["payload"])
        assert payload["event_id"] == row["event_id"]
        assert payload["request_id"] and payload["occurred_at"]
        assert payload["resource_url"].startswith("/api/v1/")

    if all(os.environ.get(name) for name in DELIVERY_ENV):
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
        assert streamed_event_ids.count(sample["event_id"]) == 1
        reconnect_status, reconnect = _consumer_request(
            "GET",
            realtime_url + "?" + urlencode({"after": stream["cursor"], "wait_ms": 100}),
            headers=token_header,
        )
        assert reconnect_status == 200 and reconnect["events"] == []


@pytest.mark.external_delivery
def test_external_delivery_gate_is_configured() -> None:
    missing = [name for name in DELIVERY_ENV if not os.environ.get(name)]
    if missing:
        pytest.fail("blocked external: staging delivery configuration is missing: " + ", ".join(missing))
