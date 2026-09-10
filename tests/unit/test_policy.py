from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from letron_api.control import policy
from letron_api.procurement.einvoice_handoff import (
    EInvoiceHandoffError,
    idempotency_key,
    load_contract,
    validate_handoff,
    validate_provider_result,
)
from letron_api.control.policy_acceptance import (
    CONTROLLER_EFFECT_ASSERTIONS,
    resolve_builder,
    resolve_controller_effect_assertion,
)


def write_policy(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_repository_policy_is_valid_and_deterministic() -> None:
    first = policy.load_policy()
    second = policy.load_policy()

    assert first == second
    assert policy.policy_sha256(first) == policy.policy_sha256(second)
    assert policy.validate_file()["documents"] == len(first["documents"])
    assert {entry["doctype"] for entry in first["documents"]} <= set(
        policy.POLICY_DOCTYPES
    )
    assert first["bootstrap"]["company"] == {
        "name": "Letron Việt Nam",
        "abbreviation": "LTVN",
        "country": "Vietnam",
        "currency": "VND",
        "domain": "Distribution",
        "chart_of_accounts": "Standard",
    }


def test_scope_ownership_and_einvoice_boundary_are_explicit() -> None:
    root = Path(__file__).parents[2]
    scope = yaml.safe_load((root / "contracts" / "scope.yml").read_text(encoding="utf-8"))
    sources = {entry["name"]: entry for entry in scope["sources"]}
    assert sources["Global Defaults"]["classification"] == "system"
    assert sources["Global Defaults"]["owner"] == "bootstrap"
    assert sources["Accounting Period"]["classification"] == "managed"

    handoff = yaml.safe_load(
        (root / "contracts" / "einvoice-handoff.yml").read_text(encoding="utf-8")
    )
    assert handoff["kind"] == "letron-einvoice-handoff-contract"
    assert "credentials_and_certificates_must_not_be_stored_in_policy" in handoff[
        "invariants"
    ]


def test_compact_policy_fills_only_declared_documents_from_full_defaults(tmp_path: Path) -> None:
    compact = write_policy(
        tmp_path / "policy.yaml",
        """version: 2
scope_version: 1
erpnext_version: 16.31.1
documents:
  - doctype: Accounts Settings
    name: Accounts Settings
    state: present
    fields:
      allow_stale: 0
  - doctype: Buying Settings
    name: Buying Settings
    state: present
    fields: {}
""",
    )
    write_policy(
        tmp_path / "policy-full.yaml",
        """version: 2
scope_version: 1
erpnext_version: 16.31.1
documents:
  - doctype: Accounts Settings
    name: Accounts Settings
    state: present
    fields:
      allow_stale: 1
      stale_days: 7
  - doctype: Buying Settings
    name: Buying Settings
    state: present
    fields:
      po_required: "Yes"
  - doctype: Selling Settings
    name: Selling Settings
    state: present
    fields:
      so_required: "Yes"
""",
    )

    loaded = policy.load_policy(compact)
    by_doctype = {entry["doctype"]: entry for entry in loaded["documents"]}
    assert set(by_doctype) == {"Accounts Settings", "Buying Settings"}
    assert by_doctype["Accounts Settings"]["fields"] == {"allow_stale": 0, "stale_days": 7}
    assert by_doctype["Buying Settings"]["fields"] == {}


def test_candidate_policy_uses_adjacent_full_fallback(tmp_path: Path) -> None:
    candidate = write_policy(
        tmp_path / ".policy.yaml.123.candidate",
        """version: 2
scope_version: 1
erpnext_version: 16.31.1
documents:
  - doctype: Accounts Settings
    name: Accounts Settings
    state: present
    fields:
      allow_stale: 0
""",
    )
    write_policy(
        tmp_path / "policy-full.yaml",
        """version: 2
scope_version: 1
erpnext_version: 16.31.1
documents:
  - doctype: Accounts Settings
    name: Accounts Settings
    state: present
    fields:
      allow_stale: 1
      stale_days: 7
""",
    )

    loaded = policy.load_policy(candidate)
    fields = loaded["documents"][0]["fields"]
    assert fields == {"allow_stale": 0, "stale_days": 7}


def test_policy_fallback_preserves_explicit_falsy_values(tmp_path: Path) -> None:
    candidate = write_policy(
        tmp_path / "policy.yaml",
        """version: 2
scope_version: 1
erpnext_version: 16.31.1
documents:
  - doctype: Accounts Settings
    name: Accounts Settings
    state: present
    fields: {zero: 0, null_value: null, empty: '', mapping: {}, sequence: []}
""",
    )
    write_policy(
        tmp_path / "policy-full.yaml",
        """version: 2
scope_version: 1
erpnext_version: 16.31.1
documents:
  - doctype: Accounts Settings
    name: Accounts Settings
    state: present
    fields: {zero: 1, null_value: fallback, empty: fallback, mapping: {x: 1}, sequence: [x]}
""",
    )
    fields = policy.load_policy(candidate)["documents"][0]["fields"]
    assert fields == {"zero": 0, "null_value": None, "empty": "", "mapping": {}, "sequence": []}


def test_policy_full_loaded_directly_does_not_merge_itself() -> None:
    full = policy.load_policy(Path(__file__).parents[2] / "config" / "policy-full.yaml")
    assert len(full["documents"]) == 15


def test_einvoice_handoff_contract_is_provider_neutral() -> None:
    contract = load_contract()
    assert contract["provider"]["name"] == "MISA"
    source = {
        "company": "Letron Việt Nam",
        "doctype": "Sales Invoice",
        "name": "ACC-SINV-0001",
        "posting_date": "2026-08-14",
        "currency": "VND",
        "conversion_rate": 1,
    }
    payload = {
        "seller": {"company": "Letron Việt Nam", "tax_id": "TAX-SELLER", "company_address": "A"},
        "buyer": {"party": "Customer", "tax_id": "TAX-BUYER", "party_address": "B"},
        "lines": {"item_code": "ITEM", "description": "Service", "qty": 1, "uom": "Unit", "rate": 100, "amount": 100},
        "taxes": {"account_head": "VAT - LTVN", "charge_type": "On Net Total", "rate": 10, "tax_amount": 10},
        "totals": {"net_total": 100, "total_taxes_and_charges": 10, "grand_total": 110, "base_grand_total": 110},
    }
    envelope = validate_handoff(source, payload)
    assert envelope["idempotency_key"] == idempotency_key(source)
    assert "credentials" not in envelope and "certificate" not in envelope


def test_einvoice_handoff_rejects_incomplete_payload_section() -> None:
    source = {
        "company": "Letron Việt Nam",
        "doctype": "Sales Invoice",
        "name": "SINV-1",
        "posting_date": "2026-08-14",
        "currency": "VND",
        "conversion_rate": 1,
    }
    payload = {
        "seller": {},
        "buyer": {},
        "lines": {},
        "taxes": {},
        "totals": {},
    }
    with pytest.raises(EInvoiceHandoffError, match="payload section seller is missing"):
        validate_handoff(source, payload)


def test_einvoice_provider_status_validation_and_idempotency() -> None:
    issued = validate_provider_result(
        {"status": "issued", "received_at": "2026-08-14T00:00:00Z", "provider_invoice_id": "MISA-1"}
    )
    assert issued["status"] == "issued"
    with pytest.raises(EInvoiceHandoffError):
        validate_provider_result({"status": "issued", "received_at": "now"})
    with pytest.raises(EInvoiceHandoffError):
        validate_provider_result({"status": "unknown", "received_at": "now"})


def test_scope_registry_has_explicit_fingerprints_and_concrete_acceptance_builders() -> (
    None
):
    scope = policy._load_scope(policy._policy_path())
    assert scope["sources"]
    for source in scope["sources"]:
        fingerprint = source["schema_fingerprint"]
        assert fingerprint["algorithm"] == "frappe-json-v1"
        assert re.fullmatch(r"[0-9a-f]{64}", fingerprint["sha256"])
        if source["classification"] in {"managed", "conditional"}:
            kind, doctype = resolve_builder(source["acceptance"]["fixture_builder"])
            assert doctype == source["name"]
            assert kind in {"native-single", "native-document"}
            method_name, kwargs = resolve_controller_effect_assertion(
                source["acceptance"]["controller_effect_assertion"]
            )
            assert isinstance(kwargs, dict)
            assert callable(
                getattr(
                    __import__("letron_api.control.policy_acceptance", fromlist=[method_name]),
                    method_name,
                )
            )


def test_required_controller_effect_assertions_are_executable() -> None:
    from letron_api.control import policy_acceptance

    required = {
        "Payment Terms Template",
        "Pricing Rule",
        "Promotional Scheme",
        "Shipping Rule",
        "Stock Entry Type",
        "Quality Inspection Template",
        "Supplier Scorecard",
        "Workflow",
        "Custom DocPerm",
        "Document Naming Rule",
        "Print Format",
        "Letter Head",
        "Email Template",
        "Notification",
        "Assignment Rule",
        "Sales Taxes and Charges Template",
        "Purchase Taxes and Charges Template",
        "Item Tax Template",
        "Tax Category",
        "Tax Rule",
    }
    assert set(CONTROLLER_EFFECT_ASSERTIONS) == required
    for method_name in CONTROLLER_EFFECT_ASSERTIONS.values():
        assert callable(getattr(policy_acceptance, method_name))


def test_every_native_erpnext_single_is_managed_or_explicitly_transient() -> None:
    erpnext_root = Path(__file__).parents[2] / "apps" / "erpnext" / "erpnext"
    native_singles: set[str] = set()
    for path in erpnext_root.glob("**/doctype/*/*.json"):
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if (
            isinstance(metadata, dict)
            and metadata.get("issingle") == 1
            and not metadata.get("istable")
        ):
            native_singles.add(metadata.get("name") or path.stem)

    assert native_singles <= policy.SINGLE_DOCTYPES | policy.TRANSIENT_SINGLE_DOCTYPES
    assert policy.SINGLE_DOCTYPES.isdisjoint(policy.TRANSIENT_SINGLE_DOCTYPES)


def test_non_password_native_credentials_are_excluded() -> None:
    class Field:
        fieldname = "access_key"
        fieldtype = "Data"
        is_virtual = False

    class Meta:
        def __init__(self) -> None:
            self.fields = [Field()]

    assert policy._managed_field_names(Meta(), "Currency Exchange Settings") == []


def test_business_configuration_inventory_tracks_bundle_and_in_scope_single_sources() -> (
    None
):
    root = Path(__file__).parents[2]
    inventory_path = root / "docs" / "Configuration_Inventory.md"
    inventory = inventory_path.read_text(encoding="utf-8")
    bundle = policy.load_policy()

    assert f"{len(bundle['documents'])} document" in inventory
    assert "\ufffd" not in inventory

    in_scope_single_files: set[str] = set()
    for path in (root / "apps" / "erpnext" / "erpnext").glob("**/doctype/*/*.json"):
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(metadata, dict)
            or metadata.get("issingle") != 1
            or metadata.get("istable")
        ):
            continue
        if metadata.get("module") in {
            "Accounts",
            "Buying",
            "Selling",
            "Stock",
        } and metadata.get("name") not in {
            "POS Settings",
            "Subscription Settings",
        }:
            in_scope_single_files.add(path.name)
        if metadata.get("name") == "Global Defaults":
            in_scope_single_files.add(path.name)
    assert in_scope_single_files
    assert all(filename in inventory for filename in in_scope_single_files)

    for target in re.findall(r"]\(([^)]+)\)", inventory):
        if "://" not in target and not target.startswith("#"):
            assert (inventory_path.parent / target).resolve().exists(), target


def test_policy_round_trips_unicode_and_native_child_rows(tmp_path: Path) -> None:
    bundle = {
        "version": 2,
        "scope_version": 1,
        "erpnext_version": "16.31.1",
        "assets": {},
        "documents": [
            {
                "doctype": "Workflow",
                "name": "Duyệt Đà Nẵng",
                "state": "present",
                "fields": {
                    "document_type": "Purchase Invoice",
                    "transitions": [
                        {"state": "Nháp", "action": "Duyệt", "next_state": "Đã duyệt"}
                    ],
                },
            }
        ],
    }
    path = tmp_path / "policy.yaml"
    path.write_text(policy.dump_policy(bundle), encoding="utf-8")

    assert policy.load_policy(path) == bundle


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            "version: 2\nversion: 2\nscope_version: 1\nerpnext_version: 16.31.1\ndocuments: []\n",
            "Duplicate YAML key",
        ),
        (
            "version: 2\nscope_version: 1\nerpnext_version: 16.31.1\ndocuments:\n  - doctype: Account\n    name: Cash\n    fields: {}\n",
            "unsupported DocType",
        ),
        (
            "version: 2\nscope_version: 1\nerpnext_version: 16.31.1\ndocuments:\n  - doctype: Accounts Settings\n    name: Wrong\n    fields: {}\n",
            "must use name Accounts Settings",
        ),
        (
            "version: 2\nscope_version: 1\nerpnext_version: 16.31.1\ndocuments:\n  - doctype: Role\n    name: Test\n    state: absent\n    fields: {disabled: 1}\n",
            "cannot define fields",
        ),
    ],
)
def test_invalid_policy_fails_closed(tmp_path: Path, body: str, message: str) -> None:
    path = write_policy(tmp_path / "invalid.yaml", body)

    with pytest.raises(policy.PolicyError, match=message):
        policy.load_policy(path)


def test_duplicate_policy_document_is_rejected(tmp_path: Path) -> None:
    path = write_policy(
        tmp_path / "duplicate.yaml",
        """version: 2
scope_version: 1
erpnext_version: 16.31.1
documents:
  - doctype: Role
    name: Accounts User
    fields: {}
  - doctype: Role
    name: Accounts User
    fields: {}
""",
    )

    with pytest.raises(policy.PolicyError, match="Duplicate policy document"):
        policy.load_policy(path)
