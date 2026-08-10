from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from lib.api_generator.cli import collect, expand_typed_modules
from lib.api_generator.contract import load_contract
from lib.api_generator.openapi import build_openapi

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_discovers_erpnext_and_custom_method():
    doctypes, methods = collect(ROOT)
    assert len(doctypes) > 100
    assert any(item.name == "Payment Entry" for item in doctypes)
    assert any(item.dotted_path == "letron_api.api.health" for item in methods)


def test_openapi_contains_frappe_contract_paths():
    doctypes, methods = collect(ROOT)
    contract = expand_typed_modules(load_contract(ROOT / "contracts/erpnext-integration.yml"), doctypes)
    spec = build_openapi(contract, doctypes, methods)
    assert spec["openapi"] == "3.1.0"
    assert "/api/resource/{doctype}" not in spec["paths"]
    assert "/api/resource/{doctype}/{name}" not in spec["paths"]
    assert "/api/method/{method}" not in spec["paths"]
    assert "/api/method/letron_api.api.health" in spec["paths"]
    assert "/api/method/upload_file" in spec["paths"]
    assert "frappeToken" in spec["components"]["securitySchemes"]
    assert "/api/v1/accounts/sales-invoices/{name}/submit" in spec["paths"]
    expected = {
        "/api/v1/selling/customers",
        "/api/v1/selling/quotations",
        "/api/v1/selling/sales-orders",
        "/api/v1/selling/delivery-notes",
        "/api/v1/accounts/sales-invoices",
        "/api/v1/accounts/purchase-invoices",
        "/api/v1/accounts/payment-entries",
        "/api/v1/buying/suppliers",
        "/api/v1/buying/purchase-orders",
        "/api/v1/stock/items",
        "/api/v1/stock/warehouses",
    }
    assert expected.issubset(spec["paths"])
    assert "/api/v1/accounts/purchase-invoices/{name}/cancel" in spec["paths"]
    assert "/api/v1/selling/sales-orders/{name}/submit" in spec["paths"]
    assert "/api/v1/buying/purchase-orders/{name}/cancel" in spec["paths"]
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
    assert len(operations) == 67
    assert all(operation["x-test-status"] == "passed" for operation in operations)
    assert all(operation["x-test-level"] == "docker-runtime" for operation in operations)
    assert all(operation["x-test-evidence"]["test"] for operation in operations)
    assert spec["x-acceptance-summary"] == {"passed": 67, "partial": 0, "not-tested": 0, "blocked": 0}
    assert spec["paths"]["/api/v1/accounts/sales-invoices"]["post"]["x-test-status"] == "passed"
    assert spec["paths"]["/api/v1/accounts/purchase-invoices"]["get"]["x-test-status"] == "passed"
    assert spec["paths"]["/api/v1/accounts/payment-entries/{name}"]["put"]["x-test-status"] == "passed"

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
