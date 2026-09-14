import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from lib.api_generator.cli import collect, expand_typed_modules
from lib.api_generator.contract import load_contract
from lib.api_generator.handoff import build_control_plane
from lib.api_generator.openapi import build_openapi

ROOT = Path(__file__).resolve().parents[2]


def test_controller_contracts_are_applied_to_generated_write_schema():
    doctypes, methods = collect(ROOT)
    contract = expand_typed_modules(load_contract(ROOT / "contracts/erpnext-integration.yml"), doctypes)
    spec = build_openapi(contract, doctypes, methods)
    schema = spec["components"]["schemas"]["RequestforQuotationItemWrite"]
    assert schema["properties"]["conversion_factor"] == {"type": "number"}
    assert schema["properties"]["stock_uom"] == {"type": "string"}
    assert {"conversion_factor", "stock_uom"}.issubset(schema["required"])


def test_catalog_discovers_erpnext_and_custom_method():
    doctypes, methods = collect(ROOT)
    assert len(doctypes) > 100
    assert any(item.name == "Payment Entry" for item in doctypes)
    assert any(item.dotted_path == "letron_api.control.api.health" for item in methods)


def test_openapi_contains_frappe_contract_paths():
    doctypes, methods = collect(ROOT)
    contract = expand_typed_modules(load_contract(ROOT / "contracts/erpnext-integration.yml"), doctypes)
    spec = build_openapi(contract, doctypes, methods)
    assert spec["openapi"] == "3.1.0"
    assert "/api/resource/{doctype}" not in spec["paths"]
    assert "/api/resource/{doctype}/{name}" not in spec["paths"]
    assert "/api/method/{method}" not in spec["paths"]
    assert "/api/method/letron_api.control.api.health" in spec["paths"]
    assert "/api/method/upload_file" not in spec["paths"]
    assert "/api/v1/files/attachments" in spec["paths"]
    assert "frappeToken" in spec["components"]["securitySchemes"]
    assert "/api/v1/accounts/sales-invoices/{name}/submit" in spec["paths"]
    expected = {
        "/api/v1/crm/leads",
        "/api/v1/crm/opportunities",
        "/api/v1/crm/request-for-quotations",
        "/api/v1/crm/supplier-quotations",
        "/api/v1/selling/customers",
        "/api/v1/selling/quotations",
        "/api/v1/selling/sales-orders",
        "/api/v1/selling/delivery-notes",
        "/api/v1/accounts/sales-invoices",
        "/api/v1/accounts/purchase-invoices",
        "/api/v1/accounts/payment-entries",
        "/api/v1/accounts/banks",
        "/api/v1/accounts/bank-accounts",
        "/api/v1/accounts/modes-of-payment",
        "/api/v1/accounts/cost-centers",
        "/api/v1/accounts/journal-entries",
        "/api/v1/accounts/payment-requests",
        "/api/v1/accounts/bank-transactions",
        "/api/v1/accounts/payment-orders",
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
        "/api/v1/stock/stock-reconciliations",
        "/api/v1/stock/serial-nos",
        "/api/v1/stock/batches",
        "/api/v1/stock/quality-inspections",
        "/api/v1/stock/pick-lists",
        "/api/v1/stock/shipments",
        "/api/v1/stock/landed-cost-vouchers",
        "/api/v1/stock/stock-reservation-entries",
    }
    assert expected.issubset(spec["paths"])
    assert "/api/v1/accounts/purchase-invoices/{name}/cancel" in spec["paths"]
    assert "/api/v1/accounts/report-packages/{name}/issue" in spec["paths"]
    assert "/api/v1/accounts/companies" in spec["paths"]
    assert "/api/v1/accounts/accounts/{name}" in spec["paths"]
    assert "/api/v1/accounts/shareholders/{name}" in spec["paths"]
    assert "/api/v1/accounts/period-closing-vouchers/{name}/submit" in spec["paths"]
    assert set(spec["paths"]["/api/v1/accounts/cost-centers"]) == {"get"}
    assert set(spec["paths"]["/api/v1/accounts/settings"]) == {"get"}
    consolidation_create = spec["paths"]["/api/v1/accounts/consolidation/adjustments"]["post"]
    assert consolidation_create["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConsolidationAdjustmentRequest"
    }
    assert consolidation_create["responses"]["200"]["content"]["application/json"]["schema"]["properties"]["message"] == {
        "$ref": "#/components/schemas/ConsolidationAdjustmentResponse"
    }
    package_get = spec["paths"]["/api/v1/accounts/consolidation/package"]["get"]
    assert package_get["responses"]["200"]["content"]["application/json"]["schema"]["properties"]["message"] == {
        "$ref": "#/components/schemas/ConsolidationPackageResponse"
    }
    assert {item["name"] for item in package_get["parameters"] if "name" in item} >= {"filters"}
    assert "/api/v1/selling/sales-orders/{name}/submit" in spec["paths"]
    assert "/api/v1/buying/purchase-orders/{name}/cancel" in spec["paths"]
    assert "/api/v1/stock/material-requests/{name}/submit" in spec["paths"]
    assert "/api/v1/stock/purchase-receipts/{name}/cancel" in spec["paths"]
    assert "/api/v1/stock/stock-entries/{name}/submit" in spec["paths"]
    assert "/api/v1/accounts/journal-entries/{name}/submit" in spec["paths"]
    assert "/api/v1/accounts/payment-requests/{name}/cancel" in spec["paths"]
    assert "/api/v1/accounts/payment-orders/{name}/submit" in spec["paths"]
    assert "/api/v1/accounts/payment-orders/{name}/cancel" in spec["paths"]
    assert "/api/v1/accounts/bank-transactions/{name}/reconcile" in spec["paths"]
    assert "/api/v1/accounts/bank-transactions/{name}/unreconcile" in spec["paths"]
    assert not any("dynamic-links" in path for path in spec["paths"])
    assert "/api/v1/stock/stock-reconciliations" in spec["paths"]
    assert "token api_key:api_secret" in spec["components"]["securitySchemes"]["frappeToken"]["description"]
    list_parameters = spec["paths"]["/api/v1/stock/items"]["get"]["parameters"]
    assert {item.get("name") for item in list_parameters if "name" in item} >= {
        "fields", "filters", "order_by", "limit_page_length", "limit_start"
    }
    item_response = spec["paths"]["/api/v1/stock/items/{name}"]["get"]["responses"]["200"]
    assert "data" in item_response["content"]["application/json"]["schema"]["properties"]
    assert not any(path.startswith("/api/v1/core/") for path in spec["paths"])
    operations = [
        operation
        for path_item in spec["paths"].values()
        for verb, operation in path_item.items()
        if verb in {"get", "post", "put", "patch", "delete"}
    ]
    assert len(contract["runtime"]["public_resources"]) == 50
    assert {
        item.module
        for item in doctypes
        if item.name in {resource["doctype"] for resource in contract["runtime"]["public_resources"]}
    } == {"Accounts", "Assets", "Buying", "Contacts", "Selling", "Stock", "CRM"}
    assert len(operations) == 348
    status_counts = {
        status: sum(operation["x-test-status"] == status for operation in operations)
        for status in ("passed", "partial", "not-tested", "blocked")
    }
    assert status_counts == {"passed": 211, "partial": 0, "not-tested": 137, "blocked": 0}
    assert all(operation["x-test-level"] == "docker-runtime" for operation in operations)
    assert all(operation.get("x-test-evidence", {}).get("test") for operation in operations)
    assert spec["x-acceptance-summary"] == status_counts
    assert spec["paths"]["/api/v1/accounts/sales-invoices"]["post"]["x-test-status"] == "passed"
    assert spec["paths"]["/api/v1/accounts/purchase-invoices"]["get"]["x-test-status"] == "passed"
    assert spec["paths"]["/api/v1/accounts/payment-entries/{name}"]["put"]["x-test-status"] == "passed"
    expected_errors = {"400", "401", "403", "404", "409", "417", "429", "500"}
    assert expected_errors.issubset(
        spec["paths"]["/api/v1/accounts/journal-entries"]["post"]["responses"]
    )
    list_headers = spec["paths"]["/api/v1/stock/items"]["get"]["parameters"]
    create_headers = spec["paths"]["/api/v1/stock/items"]["post"]["parameters"]
    assert not any(item.get("$ref", "").endswith("IdempotencyKey") for item in list_headers)
    assert any(item.get("$ref", "").endswith("IdempotencyKey") for item in create_headers)
    assert spec["paths"]["/api/method/letron_api.control.api.health"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/HealthResponse"}

    aggregate_status = {
        operation["operationId"]: (
            operation["x-test-status"],
            operation["x-test-level"],
            operation["x-test-evidence"],
        )
        for operation in operations
    }
    public_names = {item["doctype"] for item in contract["runtime"]["public_resources"]}
    for module in {item.module for item in doctypes if item.name in public_names}:
        selected = [item for item in doctypes if item.name in public_names and item.module == module]
        module_spec = build_openapi(contract, selected, methods, module)
        module_operations = [
            operation
            for path_item in module_spec["paths"].values()
            for verb, operation in path_item.items()
            if verb in {"get", "post", "put", "patch", "delete"}
        ]
        for operation in module_operations:
            assert aggregate_status[operation["operationId"]] == (
                operation["x-test-status"],
                operation["x-test-level"],
                operation["x-test-evidence"],
            )


def test_openapi_rejects_unknown_acceptance_operation_id():
    doctypes, methods = collect(ROOT)
    contract = expand_typed_modules(load_contract(ROOT / "contracts/erpnext-integration.yml"), doctypes)
    contract["acceptance"]["operations"]["operationThatDoesNotExist"] = {
        "status": "passed",
        "suite": "public-api",
    }
    with pytest.raises(ValueError, match="unknown operationId: operationThatDoesNotExist"):
        build_openapi(contract, doctypes, methods)


def test_contract_rejects_wrong_transport_type():
    source = (ROOT / "contracts/erpnext-integration.yml").read_text(encoding="utf-8")
    source = source.replace("  webhook: true", '  webhook: "yes"')
    with TemporaryDirectory() as directory:
        path = Path(directory) / "bad.yml"
        path.write_text(source, encoding="utf-8")
        with pytest.raises(TypeError, match="transport.webhook"):
            load_contract(path)


def test_control_plane_is_typed_and_separate_from_business_operations():
    spec = build_control_plane("http://127.0.0.1:8080")

    assert set(spec["paths"]) == {
        "/api/method/letron_api.control.config_control.get_configuration",
        "/api/method/letron_api.control.config_control.put_configuration",
    }
    put = spec["paths"]["/api/method/letron_api.control.config_control.put_configuration"]["put"]
    assert put["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PutConfigurationRequest"
    }
    assert {"409", "417", "500"}.issubset(put["responses"])


def test_committed_handoff_manifest_keeps_business_and_control_counts_separate():
    manifest = json.loads((ROOT / "contracts" / "openapi" / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["artifacts"]["public"]["operations"] == 348
    assert manifest["artifacts"]["control-plane"]["operations"] == 2
