"""Docker acceptance for the Phase 11 stock traceability surface."""

from __future__ import annotations

import uuid
import json
from urllib.parse import quote, urlencode

import pytest

from .api_runtime_harness import ApiClient, RuntimeUnavailable, cleanup, create_or_reuse, response_data

pytestmark = pytest.mark.integration


def _path(route: str, name: str) -> str:
    return f"{route}/{quote(name, safe='')}"


def _crud(client: ApiClient, route: str, doctype: str, payload: dict[str, object], created: list[tuple[str, str]]) -> str:
    created_doc = response_data(client.public("POST", route, payload, expected={200}))
    name = str(created_doc["name"])
    created.append((doctype, name))
    assert response_data(client.public("GET", _path(route, name), expected={200}))["name"] == name
    assert client.public("GET", route, expected={200}).status == 200
    update_field = "description" if "description" in payload else next(
        field for field in ("remarks", "purpose", "status", "reserved_qty", "posting_date", "description_of_content") if field in payload
    )
    updated_value: object = "Phase 11 readback" if update_field in {"description", "remarks", "description_of_content"} else payload[update_field]
    client.public("PUT", _path(route, name), {update_field: updated_value}, expected={200})
    updated = response_data(client.public("GET", _path(route, name), expected={200}))
    assert updated["name"] == name
    if updated.get(update_field) is not None:
        assert updated[update_field] == updated_value
    deleted = client.public("DELETE", _path(route, name), expected={200, 202, 417})
    if deleted.status in {200, 202}:
        client.public("GET", _path(route, name), expected={404})
    return name


def test_stock_traceability_contract_and_lifecycle(request: pytest.FixtureRequest) -> None:
    client = ApiClient()
    try:
        client.health_and_login()
    except RuntimeUnavailable as error:
        pytest.fail(f"blocked runtime: {error}")

    unauthenticated = ApiClient()
    for route in (
        "/api/v1/stock/stock-reconciliations",
        "/api/v1/stock/serial-nos",
        "/api/v1/stock/batches",
        "/api/v1/stock/quality-inspections",
        "/api/v1/stock/pick-lists",
        "/api/v1/stock/shipments",
        "/api/v1/stock/landed-cost-vouchers",
        "/api/v1/stock/stock-reservation-entries",
    ):
        unauthenticated.public("GET", route, expected={401})
    client.evidence.extend(unauthenticated.evidence)

    prefix = f"ACCEPTANCE-LOCAL-{uuid.uuid4().hex[:8]}-"
    created: list[tuple[str, str]] = []
    policy_snapshot = client.request(
        "GET",
        "/api/method/letron_api.config_control.get_configuration?kind=policy",
        expected={200},
    ).data["message"]
    policy_content = str(policy_snapshot.get("content", ""))
    policy_hash = str(policy_snapshot.get("source_sha256", ""))
    policy_modified = False
    stock_reservation_enabled = bool(
        response_data(client.document("GET", "Stock Settings", "Stock Settings", expected={200})).get(
            "enable_stock_reservation"
        )
    )
    if not stock_reservation_enabled and "enable_stock_reservation: 0" in policy_content:
        modified_content = policy_content.replace("enable_stock_reservation: 0", "enable_stock_reservation: 1", 1)
        try:
            policy_response = client.request(
                "PUT",
                "/api/method/letron_api.config_control.put_configuration",
                {
                    "kind": "policy",
                    "content": modified_content,
                    "expected_source_sha256": policy_hash,
                    "apply_now": 1,
                },
                expected={200},
            ).data["message"]
            policy_modified = True
            policy_hash = str(policy_response.get("source_sha256", policy_hash))
            stock_reservation_enabled = True
        except Exception:
            stock_reservation_enabled = False

    def finalize() -> None:
        if policy_modified:
            try:
                current_policy = client.request(
                    "GET",
                    "/api/method/letron_api.config_control.get_configuration?kind=policy",
                    expected={200},
                ).data["message"]
                client.request(
                    "PUT",
                    "/api/method/letron_api.config_control.put_configuration",
                    {
                        "kind": "policy",
                        "content": str(policy_snapshot.get("content", "")),
                        "expected_source_sha256": str(current_policy.get("source_sha256", policy_hash)),
                        "apply_now": 1,
                    },
                    expected={200},
                )
            except Exception:
                # Best-effort rollback: do not mask the primary test result on teardown.
                pass
        cleanup(client, created, prefix)
        client.write_evidence()

    request.addfinalizer(finalize)

    company = create_or_reuse(
        client,
        "Company",
        {"name": prefix + "Company", "company_name": prefix + "Company", "abbr": "P" + uuid.uuid4().hex[:3].upper(), "country": "Vietnam", "default_currency": "VND", "domain": "Distribution"},
        created,
    )
    company_abbr = response_data(client.document("GET", "Company", company, expected={200}))["abbr"]
    company_doc = response_data(client.document("GET", "Company", company, expected={200}))
    company_stock_adjustment_account = company_doc.get("stock_adjustment_account") or company_doc.get("default_inventory_account")
    cost_center = create_or_reuse(client, "Cost Center", {"name": prefix + "Cost Center", "cost_center_name": prefix + "Cost Center", "company": company, "parent_cost_center": f"{company} - {company_abbr}", "is_group": 0}, created)
    account_query = urlencode({"fields": json.dumps(["name", "report_type"]), "filters": json.dumps([["company", "=", company], ["report_type", "=", "Balance Sheet"]]), "limit_page_length": 1})
    accounts = client.request("GET", f"/api/resource/Account?{account_query}", expected={200}).data["data"]
    assert accounts, "fixture company must have a balance-sheet account for stock reconciliation"
    stock_adjustment_account = accounts[0]["name"]
    lcv_account_query = urlencode(
        {"fields": json.dumps(["name", "account_type"]), "filters": json.dumps([["company", "=", company], ["account_type", "=", "Temporary"]]), "limit_page_length": 1}
    )
    lcv_expense_accounts = client.request(
        "GET",
        f"/api/resource/Account?{lcv_account_query}",
        expected={200},
    ).data["data"]
    lcv_expense_account = (
        lcv_expense_accounts[0]["name"]
        if lcv_expense_accounts
        else company_stock_adjustment_account
        or stock_adjustment_account
    )
    assert lcv_expense_account, "fixture company must have an expense account for landed cost"
    item_group = create_or_reuse(client, "Item Group", {"name": prefix + "Item Group", "item_group_name": prefix + "Item Group", "is_group": 0}, created)
    create_or_reuse(client, "UOM", {"name": "Nos", "uom_name": "Nos", "enabled": 1}, created)
    item = create_or_reuse(client, "Item", {"item_code": prefix + "Item", "item_name": prefix + "Item", "item_group": item_group, "stock_uom": "Nos", "is_stock_item": 1}, created)
    trace_item = create_or_reuse(client, "Item", {"item_code": prefix + "Trace Item", "item_name": prefix + "Trace Item", "item_group": item_group, "stock_uom": "Nos", "is_stock_item": 1, "has_batch_no": 1, "has_serial_no": 1}, created)
    reserved_item = create_or_reuse(
        client,
        "Item",
        {"item_code": prefix + "Reserved Item", "item_name": prefix + "Reserved Item", "item_group": item_group, "stock_uom": "Nos", "is_stock_item": 1},
        created,
    )
    price_list = create_or_reuse(
        client,
        "Price List",
        {"name": prefix + "Price List", "price_list_name": prefix + "Price List", "enabled": 1, "buying": 0, "selling": 1, "currency": "VND"},
        created,
    )
    warehouse = create_or_reuse(client, "Warehouse", {"name": prefix + "Warehouse", "warehouse_name": prefix + "Warehouse", "company": company}, created)
    customer_group = create_or_reuse(
        client,
        "Customer Group",
        {"name": prefix + "Customer Group", "customer_group_name": prefix + "Customer Group", "is_group": 0},
        created,
    )
    territory = create_or_reuse(client, "Territory", {"name": prefix + "Territory", "territory_name": prefix + "Territory", "is_group": 0}, created)
    customer = create_or_reuse(client, "Customer", {"name": prefix + "Customer", "customer_name": prefix + "Customer", "customer_group": customer_group, "territory": territory, "customer_type": "Company"}, created)
    create_or_reuse(client, "Address Template", {"name": "Vietnam", "country": "Vietnam", "is_default": 1, "template": f"<!-- {prefix} -->{{{{ address_line1 }}}}<br>{{{{ city }}}}<br>{{{{ country }}}}"}, created)
    address = create_or_reuse(client, "Address", {"name": prefix + "Address", "address_title": prefix + "Address", "address_type": "Billing", "address_line1": "1 Acceptance Street", "city": "Ho Chi Minh City", "country": "Vietnam", "links": [{"link_doctype": "Customer", "link_name": customer}]}, created)
    stock_entry_type = create_or_reuse(client, "Stock Entry Type", {"name": prefix + "Material Receipt", "purpose": "Material Receipt"}, created)
    reference_stock_entry = create_or_reuse(
        client,
        "Stock Entry",
        {
            "name": prefix + "Reference",
            "stock_entry_type": stock_entry_type,
            "company": company,
            "posting_date": "2026-08-13",
            "items": [
            {
                "item_code": item,
                "qty": 1,
                "uom": "Nos",
                "stock_uom": "Nos",
                "conversion_factor": 1,
                "t_warehouse": warehouse,
                "basic_rate": 100,
            }
        ],
        },
        created,
    )
    client.public("POST", f"/api/v1/stock/stock-entries/{quote(reference_stock_entry, safe='')}/submit", expected={200})

    supplier_group = create_or_reuse(
        client,
        "Supplier Group",
        {"name": prefix + "Supplier Group", "supplier_group_name": prefix + "Supplier Group", "is_group": 0},
        created,
    )
    supplier = create_or_reuse(
        client,
        "Supplier",
        {"name": prefix + "Supplier", "supplier_name": prefix + "Supplier", "supplier_group": supplier_group},
        created,
    )
    purchase_order = create_or_reuse(
        client,
        "Purchase Order",
        {
            "name": prefix + "Reference Purchase Order",
            "company": company,
            "transaction_date": "2026-08-13",
            "schedule_date": "2026-08-13",
            "supplier": supplier,
            "currency": "VND",
            "items": [
                {"item_code": item, "qty": 1, "schedule_date": "2026-08-13", "warehouse": warehouse, "rate": 100},
                {"item_code": reserved_item, "qty": 1, "schedule_date": "2026-08-13", "warehouse": warehouse, "rate": 100},
            ],
        },
        created,
    )
    client.public("POST", f"/api/v1/buying/purchase-orders/{quote(purchase_order, safe='')}/submit", expected={200})
    purchase_order_doc = response_data(client.public("GET", f"/api/v1/buying/purchase-orders/{quote(purchase_order, safe='')}", expected={200}))
    purchase_receipt = create_or_reuse(
        client,
        "Purchase Receipt",
        {
            "name": prefix + "Reference Purchase Receipt",
            "company": company,
            "posting_date": "2026-08-13",
            "supplier": supplier,
            "supplier_warehouse": warehouse,
            "items": [
                {
                    "item_code": item,
                    "qty": 1,
                    "received_qty": 1,
                    "stock_uom": "Nos",
                    "uom": "Nos",
                    "conversion_factor": 1,
                    "rate": 100,
                    "warehouse": warehouse,
                    "cost_center": cost_center,
                    "purchase_order": purchase_order,
                    "purchase_order_item": purchase_order_doc["items"][0]["name"],
                },
                {
                    "item_code": reserved_item,
                    "qty": 1,
                    "received_qty": 1,
                    "stock_uom": "Nos",
                    "uom": "Nos",
                    "conversion_factor": 1,
                    "rate": 100,
                    "warehouse": warehouse,
                    "cost_center": cost_center,
                    "purchase_order": purchase_order,
                    "purchase_order_item": purchase_order_doc["items"][1]["name"],
                }
            ],
        },
        created,
    )
    client.public("POST", f"/api/v1/stock/purchase-receipts/{quote(purchase_receipt, safe='')}/submit", expected={200})

    # These are draft documents and therefore remain disposable even when a
    # native controller rejects a later dependent operation.
    _crud(client, "/api/v1/stock/serial-nos", "Serial No", {"name": prefix + "Serial", "serial_no": prefix + "Serial", "item_code": trace_item, "company": company, "description": "Phase 11 serial"}, created)
    _crud(client, "/api/v1/stock/batches", "Batch", {"name": prefix + "Batch", "batch_id": prefix + "Batch", "item": trace_item, "description": "Phase 11 batch"}, created)
    _crud(client, "/api/v1/stock/quality-inspections", "Quality Inspection", {"name": prefix + "Inspection", "inspection_type": "Incoming", "reference_type": "Stock Entry", "reference_name": reference_stock_entry, "item_code": item, "sample_size": 1, "inspected_by": "Administrator", "status": "Accepted", "remarks": "Phase 11"}, created)
    _crud(client, "/api/v1/stock/pick-lists", "Pick List", {"name": prefix + "Pick List", "company": company, "naming_series": "STO-PICK-.YYYY.-", "status": "Draft", "for_qty": 1, "locations": [{"item_code": item, "warehouse": warehouse, "qty": 1, "stock_uom": "Nos", "uom": "Nos", "conversion_factor": 1}]}, created)
    _crud(client, "/api/v1/stock/shipments", "Shipment", {"name": prefix + "Shipment", "pickup_address_name": address, "delivery_address_name": address, "value_of_goods": 1, "pickup_date": "2026-08-13", "pickup_from": "09:00:00", "pickup_to": "17:00:00", "description_of_content": "Phase 11"}, created)
    stock_reconciliation = _crud(
        client,
        "/api/v1/stock/stock-reconciliations",
        "Stock Reconciliation",
        {
            "name": prefix + "Stock Reconciliation",
            "company": company,
            "posting_date": "2026-08-13",
            "posting_time": "09:00:00",
            "purpose": "Stock Reconciliation",
            "set_posting_time": 1,
            "expense_account": lcv_expense_account,
            "cost_center": cost_center,
            "items": [{"item_code": item, "warehouse": warehouse, "qty": 1, "valuation_rate": 100}],
            "remarks": "Phase 11",
        },
        created,
    )
    client.public(
        "POST",
        "/api/v1/stock/stock-reconciliations",
        {"name": prefix + "Stock Reconciliation Invalid", "company": company, "purpose": "Stock Reconciliation"},
        expected={400, 417},
    )
    _ = stock_reconciliation
    _crud(
        client,
        "/api/v1/stock/landed-cost-vouchers",
        "Landed Cost Voucher",
        {
            "name": prefix + "LCV",
            "company": company,
            "posting_date": "2026-08-13",
            "distribute_charges_based_on": "Amount",
            "purchase_receipts": [
                {
                    "receipt_document_type": "Purchase Receipt",
                    "receipt_document": purchase_receipt,
                    "supplier": supplier,
                    "posting_date": "2026-08-13",
                    "grand_total": 100,
                }
            ],
            "taxes": [
                {
                    "description": "Freight",
                    "expense_account": lcv_expense_account,
                    "amount": 1,
                }
            ],
        },
        created,
    )

    if stock_reservation_enabled:
        sales_order = response_data(
            client.public(
                "POST",
                "/api/v1/selling/sales-orders",
                {
                    "customer": customer,
                    "company": company,
                    "currency": "VND",
                    "conversion_rate": 1,
                    "selling_price_list": price_list,
                    "price_list_currency": "VND",
                    "plc_conversion_rate": 1,
                    "transaction_date": "2026-08-13",
                    "delivery_date": "2026-08-13",
                    "items": [{"item_code": reserved_item, "qty": 1, "rate": 100, "warehouse": warehouse}],
                },
                expected={200},
            )
        )
        so_name = str(sales_order["name"])
        so_item = str(sales_order["items"][0]["name"])
        _ = client.public("POST", f"/api/v1/selling/sales-orders/{quote(so_name, safe='')}/submit", expected={200})

        stock_reservation = _crud(
            client,
            "/api/v1/stock/stock-reservation-entries",
            "Stock Reservation Entry",
            {
                "name": prefix + "Stock Reservation Entry",
                "company": company,
                "item_code": reserved_item,
                "warehouse": warehouse,
                "stock_uom": "Nos",
                "voucher_type": "Sales Order",
                "voucher_no": so_name,
                "voucher_detail_no": so_item,
                "available_qty": 1,
                "voucher_qty": 1,
                "reserved_qty": 1,
                "remarks": "Phase 11",
            },
            created,
        )
        _ = stock_reservation
        client.public(
            "POST",
            "/api/v1/stock/stock-reservation-entries",
            {"name": prefix + "Stock Reservation Entry Invalid", "company": company, "item_code": trace_item},
            expected={400, 404, 417},
        )
