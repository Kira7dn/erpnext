from pathlib import Path

from workspace_api.cli import collect
from workspace_api.contract import load_contract
from workspace_api.openapi import build_openapi

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_discovers_erpnext_and_custom_method():
    doctypes, methods = collect(ROOT)
    assert len(doctypes) > 100
    assert any(item.name == "Payment Entry" for item in doctypes)
    assert any(item.dotted_path == "letron_api.api.health" for item in methods)


def test_openapi_contains_frappe_contract_paths():
    contract = load_contract(ROOT / "contracts/erpnext-integration.yml")
    doctypes, methods = collect(ROOT)
    spec = build_openapi(contract, doctypes, methods)
    assert spec["openapi"] == "3.1.0"
    assert "/api/resource/{doctype}" in spec["paths"]
    assert "/api/method/letron_api.api.health" in spec["paths"]
