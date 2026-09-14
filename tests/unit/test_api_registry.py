import json
from pathlib import Path

from lib.api_generator.registry import build_registry, registry_document

ROOT = Path(__file__).resolve().parents[2]


def test_generated_registry_covers_only_public_business_operations():
    catalog = json.loads((ROOT / "contracts/generated/catalog.json").read_text(encoding="utf-8"))
    registry = catalog["operations"]
    assert len(registry) == 323
    assert {item["operation"] for item in registry} == {"list", "read", "create", "update", "delete"}
    assert not any("/api/resource/" in item["path"] or "/api/method/" in item["path"] for item in registry)
    assert not any(item["resource"] in {"User", "Role", "Custom DocPerm"} for item in registry)


def test_registry_has_native_targets_and_read_only_dependencies():
    catalog = json.loads((ROOT / "contracts/generated/catalog.json").read_text(encoding="utf-8"))
    receipt = next(item for item in catalog["operations"] if item["operation_id"] == "createPurchaseReceipt")
    assert receipt["target"] == {"doctype": "Purchase Receipt"}
    assert receipt["dependencies"] == ["Account"]
    assert receipt["risk"] == "medium"
    action = next(item for item in catalog["operations"] if item["operation_id"] == "submitPurchaseReceipt")
    assert action["target"] == {"doctype": "Purchase Receipt", "action": "submit"}
    assert action["risk"] == "high"


def test_registry_builder_matches_committed_catalog():
    catalog = json.loads((ROOT / "contracts/generated/catalog.json").read_text(encoding="utf-8"))
    spec = json.loads((ROOT / "contracts/generated/openapi.json").read_text(encoding="utf-8"))
    import yaml

    contract = yaml.safe_load((ROOT / "contracts/erpnext-integration.yml").read_text(encoding="utf-8"))
    assert build_registry(spec, contract) == catalog["operations"]


def test_registry_action_comes_from_operation_metadata_not_url_suffix():
    spec = {"paths": {"/api/v1/buying/orders/{name}/whatever": {"post": {
        "operationId": "submitOrder", "x-public-operation": "update", "x-frappe-action": "submit",
    }}}}
    contract = {"runtime": {"public_resources": [{"doctype": "Purchase Order", "path": "/api/v1/buying/orders"}]}}
    result = build_registry(spec, contract)
    assert result[0]["target"] == {"doctype": "Purchase Order", "action": "submit"}
    assert registry_document(result)["version"] == 1
