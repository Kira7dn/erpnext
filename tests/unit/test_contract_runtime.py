import json
from pathlib import Path

import pytest
from letron_api.contract_runtime import contract_metadata, public_route_maps, validate_request, validate_response

ROOT = Path(__file__).resolve().parents[2]


def _minimal(schema: dict, schemas: dict) -> object:
    if "$ref" in schema:
        return _minimal(schemas[schema["$ref"].rsplit("/", 1)[-1]], schemas)
    if schema.get("type") == "object":
        return {name: _minimal(schema["properties"][name], schemas) for name in schema.get("required", [])}
    if schema.get("type") == "array":
        return []
    if schema.get("type") in {"integer", "number"}:
        return 0
    if schema.get("type") == "boolean":
        return False
    if schema.get("enum"):
        return schema["enum"][0]
    return "test"


def test_generated_contract_validates_public_write_and_rejects_unknown_field():
    contract = json.loads((ROOT / "contracts/generated/runtime-contract.json").read_text(encoding="utf-8"))
    request_schema = next(item["request_schema"] for item in contract["registry"] if item["operation_id"] == "createPurchaseReceipt")
    valid = _minimal(request_schema, contract["schemas"])
    assert isinstance(valid, dict)
    validate_request("POST", "/api/v1/stock/purchase-receipts", json.dumps(valid).encode())
    with pytest.raises(ValueError, match="schema_validation_failed"):
        validate_request("POST", "/api/v1/stock/purchase-receipts", json.dumps({**valid, "not_a_field": 1}).encode())


def test_generated_contract_validates_response_and_ignores_unknown_route():
    contract = json.loads((ROOT / "contracts/generated/runtime-contract.json").read_text(encoding="utf-8"))
    response_schema = next(item["response_schema"] for item in contract["registry"] if item["operation_id"] == "getPurchaseReceipt")
    validate_response("GET", "/api/v1/stock/purchase-receipts/PR-1", _minimal(response_schema, contract["schemas"]))
    with pytest.raises(ValueError, match="schema_validation_failed"):
        validate_response("GET", "/api/v1/stock/purchase-receipts/PR-1", {"wrong": True})
    # Control/native routes are outside the business contract and are not
    # accidentally validated by the business validator.
    validate_request("POST", "/api/method/frappe.auth.login", b"{}")


def test_generated_registry_drives_supplier_quotation_actions():
    routes, document_actions, custom_actions = public_route_maps()

    assert routes[("crm", "supplier-quotations")] == "Supplier Quotation"
    assert document_actions[("crm", "supplier-quotations")] == {"submit", "cancel"}
    assert custom_actions[("crm", "supplier-quotations", "make-purchase-order")] == "letron_api.control.api.make_purchase_order"


def test_generated_contract_has_registry_metadata():
    version, sha256 = contract_metadata()
    assert version == 1
    assert len(sha256) == 64
