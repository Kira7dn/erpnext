from __future__ import annotations

import json
import uuid
from urllib.parse import quote, urlencode

import pytest

from .api_runtime_harness import ApiClient, RuntimeUnavailable, cleanup, response_data

pytestmark = pytest.mark.integration


def _path(route: str, name: str) -> str:
    return f"{route}/{quote(name, safe='')}"


def _list_names(client: ApiClient, route: str, name: str) -> list[str]:
    query = urlencode(
        {
            "fields": json.dumps(["name"]),
            "filters": json.dumps([["name", "=", name]]),
            "order_by": "modified desc",
            "limit_start": 0,
            "limit_page_length": 1,
        }
    )
    response = client.public("GET", f"{route}?{query}", expected={200})
    return [item["name"] for item in response.data.get("data", [])]


def test_crm_preorder_contract_and_lifecycle(request: pytest.FixtureRequest) -> None:
    client = ApiClient()
    try:
        client.health_and_login()
    except RuntimeUnavailable as error:
        pytest.fail(f"blocked runtime: {error}")

    prefix = f"ACCEPTANCE-LOCAL-{uuid.uuid4().hex[:8]}-"
    created: list[tuple[str, str]] = []

    def finalize() -> None:
        cleanup(client, created, prefix)
        client.write_evidence()

    request.addfinalizer(finalize)

    company = response_data(
        client.document(
            "POST",
            "Company",
            payload={
                "name": prefix + "Company",
                "company_name": prefix + "Company",
                "abbr": f"C{uuid.uuid4().hex[:4].upper()}",
                "country": "Vietnam",
                "default_currency": "VND",
                "domain": "Distribution",
            },
        ),
    )["name"]
    created.append(("Company", company))

    customer_group = response_data(
        client.document("POST", "Customer Group", payload={"name": prefix + "Customer Group", "customer_group_name": prefix + "Customer Group", "is_group": 0})
    )["name"]
    created.append(("Customer Group", customer_group))
    territory = response_data(
        client.document("POST", "Territory", payload={"name": prefix + "Territory", "territory_name": prefix + "Territory", "is_group": 0})
    )["name"]
    created.append(("Territory", territory))

    customer = response_data(
        client.public(
            "POST",
            "/api/v1/selling/customers",
            {"customer_name": prefix + "Customer", "customer_type": "Company", "customer_group": customer_group, "territory": territory},
            expected={200},
        )
    )["name"]
    created.append(("Customer", customer))

    supplier_group = response_data(
        client.document(
            "POST",
            "Supplier Group",
            payload={"name": prefix + "Supplier Group", "supplier_group_name": prefix + "Supplier Group", "is_group": 0},
        )
    )["name"]
    created.append(("Supplier Group", supplier_group))
    supplier = response_data(
        client.document(
            "POST",
            "Supplier",
            payload={
                "name": prefix + "Supplier",
                "supplier_name": prefix + "Supplier",
                "supplier_group": supplier_group,
                "supplier_type": "Company",
            },
        )
    )["name"]
    created.append(("Supplier", supplier))

    item_group = response_data(
        client.document("POST", "Item Group", payload={"name": prefix + "Item Group", "item_group_name": prefix + "Item Group", "is_group": 0})
    )["name"]
    created.append(("Item Group", item_group))
    item = response_data(
        client.public(
            "POST",
            "/api/v1/stock/items",
            {"item_code": prefix + "Item", "item_name": prefix + "Item", "item_group": item_group, "stock_uom": "Nos", "is_stock_item": 0},
            expected={200},
        )
    )["name"]
    created.append(("Item", item))

    opportunity_type = response_data(
        client.document("POST", "Opportunity Type", payload={"name": prefix + "Sales", "description": "Acceptance sales type"})
    )["name"]
    created.append(("Opportunity Type", opportunity_type))

    sales_stage = response_data(
        client.document("POST", "Sales Stage", payload={"stage_name": prefix + "Sales Stage"})
    )["name"]
    created.append(("Sales Stage", sales_stage))

    lead = response_data(
        client.public(
            "POST",
            "/api/v1/crm/leads",
            {"name": prefix + "Lead", "status": "Open", "company_name": prefix + "Lead Co"},
            expected={200},
        )
    )
    lead_name = lead["name"]
    created.append(("Lead", lead_name))
    assert _list_names(client, "/api/v1/crm/leads", lead_name) == [lead_name]
    lead = response_data(client.public("GET", _path("/api/v1/crm/leads", lead_name), expected={200}))
    assert lead["name"] == lead_name
    response = response_data(client.public("PUT", _path("/api/v1/crm/leads", lead_name), {"status": "Interested"}, expected={200}))
    assert response["status"] == "Interested"
    client.public("DELETE", _path("/api/v1/crm/leads", lead_name), expected={200, 202, 404, 417})

    opportunity = response_data(
        client.public(
            "POST",
            "/api/v1/crm/opportunities",
            {
                "name": prefix + "Opportunity",
                "status": "Open",
            "naming_series": "CRM-OPP-.YYYY.-",
                "opportunity_from": "Customer",
                "party_name": customer,
                "company": company,
                "opportunity_type": opportunity_type,
                "sales_stage": sales_stage,
                "transaction_date": "2026-08-13",
                },
            expected={200},
        )
    )
    opportunity_name = opportunity["name"]
    created.append(("Opportunity", opportunity_name))
    assert _list_names(client, "/api/v1/crm/opportunities", opportunity_name) == [opportunity_name]
    opportunity = response_data(client.public("GET", _path("/api/v1/crm/opportunities", opportunity_name), expected={200}))
    assert opportunity["name"] == opportunity_name
    response = response_data(
        client.public(
            "PUT",
            _path("/api/v1/crm/opportunities", opportunity_name),
            {"status": "Quotation"},
            expected={200},
        )
    )
    assert response["status"] == "Quotation"
    client.public("DELETE", _path("/api/v1/crm/opportunities", opportunity_name), expected={200, 202, 404, 417})

    request_for_quotation = response_data(
        client.public(
            "POST",
            "/api/v1/crm/request-for-quotations",
            {
                "name": prefix + "RFQ",
            "naming_series": "PUR-RFQ-.YYYY.-",
            "status": "Draft",
            "company": company,
            "subject": "Acceptance RFQ",
            "suppliers": [{"supplier": supplier, "name": prefix + "RFQ-Supplier"}],
            "items": [
                {
                    "name": prefix + "RFQ-Item",
                    "item_code": item,
                    "qty": 1,
                    "uom": "Nos",
                    "stock_uom": "Nos",
                    "conversion_factor": 1,
                    "schedule_date": "2026-08-13",
                }
            ],
                "transaction_date": "2026-08-13",
            },
            expected={200},
        )
    )
    request_name = request_for_quotation["name"]
    created.append(("Request for Quotation", request_name))
    assert _list_names(client, "/api/v1/crm/request-for-quotations", request_name) == [request_name]
    request_for_quotation = response_data(client.public("GET", _path("/api/v1/crm/request-for-quotations", request_name), expected={200}))
    assert request_for_quotation["name"] == request_name
    response = response_data(
        client.public(
            "PUT",
            _path("/api/v1/crm/request-for-quotations", request_name),
            {"subject": "Acceptance RFQ updated"},
            expected={200},
        )
    )
    assert response["subject"] == "Acceptance RFQ updated"
    client.public("DELETE", _path("/api/v1/crm/request-for-quotations", request_name), expected={200, 202, 404, 417})

    supplier_quotation = response_data(
        client.public(
            "POST",
            "/api/v1/crm/supplier-quotations",
            {
                "name": prefix + "SQ",
                "naming_series": "PUR-SQTN-.YYYY.-",
                "status": "Draft",
                "supplier": supplier,
                "company": company,
                "currency": "VND",
                "conversion_rate": 1,
                "items": [
                    {
                        "name": prefix + "SQ-Item",
                        "item_code": item,
                        "qty": 1,
                        "uom": "Nos",
                        "stock_uom": "Nos",
                        "conversion_factor": 1,
                        "base_rate": 100000,
                        "base_amount": 100000,
                    }
                ],
                "transaction_date": "2026-08-13",
            },
            expected={200},
        )
    )
    supplier_quotation_name = str(supplier_quotation["name"])
    created.append(("Supplier Quotation", supplier_quotation_name))
    assert _list_names(client, "/api/v1/crm/supplier-quotations", supplier_quotation_name) == [supplier_quotation_name]
    persisted_supplier_quotation = response_data(
        client.public("GET", _path("/api/v1/crm/supplier-quotations", supplier_quotation_name), expected={200})
    )
    assert persisted_supplier_quotation["name"] == supplier_quotation_name
    response = response_data(
        client.public(
            "PUT",
            _path("/api/v1/crm/supplier-quotations", supplier_quotation_name),
            {"title": prefix + "SQ Updated"},
            expected={200},
        )
    )
    assert response["title"] == prefix + "SQ Updated"
    client.public("DELETE", _path("/api/v1/crm/supplier-quotations", supplier_quotation_name), expected={200, 202, 404, 417})
