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
    assert "/api/resource/{doctype}" in spec["paths"]
    assert "/api/method/letron_api.api.health" in spec["paths"]
    assert "/api/method/upload_file" in spec["paths"]
    assert "frappeToken" in spec["components"]["securitySchemes"]
    assert "/api/v1/accounts/sales-invoices/{name}/submit" in spec["paths"]
    assert not any(path.startswith("/api/v1/core/") for path in spec["paths"])


def test_contract_rejects_wrong_transport_type():
    source = (ROOT / "contracts/erpnext-integration.yml").read_text(encoding="utf-8")
    source = source.replace("  webhook: true", '  webhook: "yes"')
    with TemporaryDirectory() as directory:
        path = Path(directory) / "bad.yml"
        path.write_text(source, encoding="utf-8")
        with pytest.raises(TypeError, match="transport.webhook"):
            load_contract(path)
