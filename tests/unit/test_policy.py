from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from letron_api.control import policy
from letron_api.control.policy_acceptance import (
    CONTROLLER_EFFECT_ASSERTIONS,
    resolve_builder,
    resolve_controller_effect_assertion,
)
from letron_api.procurement.einvoice_handoff import (
    EInvoiceHandoffError,
    idempotency_key,
    load_contract,
    validate_handoff,
    validate_provider_result,
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
        "name": "Letron Holding",
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


def test_compact_policy_inherits_and_overrides_policy_defaults(tmp_path: Path) -> None:
    compact = write_policy(
        tmp_path / "policy.yaml",
        """version: 3
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
        tmp_path / "policy-defaults.yaml",
        """version: 3
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
    assert set(by_doctype) == {"Accounts Settings", "Buying Settings", "Selling Settings"}
    assert by_doctype["Accounts Settings"]["fields"] == {"allow_stale": 0, "stale_days": 7}
    assert by_doctype["Buying Settings"]["fields"] == {"po_required": "Yes"}


def test_candidate_policy_uses_adjacent_full_fallback(tmp_path: Path) -> None:
    candidate = write_policy(
        tmp_path / ".policy.yaml.123.candidate",
            """version: 3
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
        tmp_path / "policy-defaults.yaml",
            """version: 3
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
            """version: 3
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
        tmp_path / "policy-defaults.yaml",
            """version: 3
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
    assert fields == {"zero": 0, "null_value": None, "empty": "", "mapping": {"x": 1}, "sequence": []}


def test_policy_defaults_loaded_directly_does_not_merge_itself() -> None:
    defaults = policy.load_policy(Path(__file__).parents[2] / "config" / "policy-defaults.yaml")
    assert len(defaults["documents"]) == 90


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
        "version": 3,
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
                "version: 3\nversion: 3\nscope_version: 1\nerpnext_version: 16.31.1\ndocuments: []\n",
            "Duplicate YAML key",
        ),
        (
                "version: 3\nscope_version: 1\nerpnext_version: 16.31.1\ndocuments:\n  - doctype: Account\n    name: Cash\n    fields: {}\n",
            "unsupported DocType",
        ),
        (
                "version: 3\nscope_version: 1\nerpnext_version: 16.31.1\ndocuments:\n  - doctype: Accounts Settings\n    name: Wrong\n    fields: {}\n",
            "must use name Accounts Settings",
        ),
        (
                "version: 3\nscope_version: 1\nerpnext_version: 16.31.1\ndocuments:\n  - doctype: Role\n    name: Test\n    state: absent\n    fields: {disabled: 1}\n",
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
        """version: 3
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


def test_consolidation_marker_contract_is_validated() -> None:
    shared = deepcopy(policy.load_policy()["shared"])
    shared["consolidation"]["intercompany_marker"] = "IC|id={matching_id}|counterparty={counterparty_company}"

    with pytest.raises(policy.PolicyError, match="intercompany_marker must contain exactly"):
        policy._normalize_shared(shared)


def test_consolidation_rules_must_reference_shared_coa_accounts() -> None:
    shared = deepcopy(policy.load_policy()["shared"])
    shared["consolidation"]["elimination_rules"][0]["debit_account_code"] = "999999"

    with pytest.raises(policy.PolicyError, match="unknown COA Account code"):
        policy._normalize_shared(shared)


def test_holding_policy_aligns_fiscal_year_and_consolidation_companies() -> None:
    bundle = policy.load_policy()
    configured = {item["name"] for item in bundle["bootstrap"]["companies"]}
    assert set(bundle["shared"]["fiscal_year"]["companies"]) == configured
    assert set(bundle["shared"]["consolidation"]["companies"]) == configured


def test_accounting_period_is_not_used_as_fiscal_year_placeholder() -> None:
    bundle = policy.load_policy()
    periods = [
        entry
        for entry in bundle["documents"]
        if entry["doctype"] == "Accounting Period"
    ]

    assert len(periods) == 1
    assert periods[0]["state"] == "absent"
    assert periods[0]["fields"] == {}
    assert bundle["shared"]["fiscal_year"] == {
        "name": "2026",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "calendar_year": True,
        "companies": ["Letron Holding", "LeSC", "LeSM", "LeDB", "LeSE", "LeSB", "LeGM"],
    }
    assert bundle["shared"]["comparative_fiscal_years"] == [{
        "name": "2025",
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "calendar_year": True,
        "companies": ["Letron Holding", "LeSC", "LeSM", "LeDB", "LeSE", "LeSB", "LeGM"],
    }]


def test_comparative_fiscal_year_must_cover_same_companies(tmp_path: Path) -> None:
    bundle = deepcopy(policy.load_policy())
    bundle["shared"]["comparative_fiscal_years"][0]["companies"] = ["LeSC"]
    path = write_policy(tmp_path / "policy.yaml", policy.dump_policy(bundle))

    with pytest.raises(policy.PolicyError, match="comparative_fiscal_years.companies"):
        policy.load_policy(path)


def test_fiscal_year_rejects_non_calendar_boundaries(tmp_path: Path) -> None:
    bundle = deepcopy(policy.load_policy())
    bundle["shared"]["fiscal_year"]["start_date"] = "2026-04-01"
    path = write_policy(tmp_path / "policy.yaml", policy.dump_policy(bundle))

    with pytest.raises(policy.PolicyError, match="calendar_year"):
        policy.load_policy(path)


def test_fiscal_year_native_document_cannot_drift_from_shared_policy(tmp_path: Path) -> None:
    bundle = deepcopy(policy.load_policy())
    fiscal_year = next(
        entry for entry in bundle["documents"] if entry["doctype"] == "Fiscal Year"
    )
    fiscal_year["fields"]["year_end_date"] = "2026-11-30"
    path = write_policy(tmp_path / "policy.yaml", policy.dump_policy(bundle))

    with pytest.raises(policy.PolicyError, match="must match shared.fiscal_year"):
        policy.load_policy(path)


def test_vas_reporting_contract_is_explicit_and_versioned() -> None:
    reporting = policy.load_policy()["shared"]["coa_template"]["reporting"]

    assert reporting["cash_flow"]["standard"] == "VAS 24"
    assert reporting["cash_flow"]["method"] == "indirect"
    assert set(reporting["cash_flow"]["categories"]) == {
        "operating",
        "investing",
        "financing",
    }
    assert reporting["currency"] == {
        "reporting_currency": "VND",
        "allowed_accounting_currencies": ["VND"],
        "foreign_currency_transactions": "disabled",
        "exchange_rate_source": "native_exchange_rate",
        "revaluation_required_at_close": True,
        "translation": "not_configured",
    }
    assert reporting["assets"]["default_depreciation_method"] == "Straight Line"
    assert reporting["assets"]["require_cost_center"] is True


def test_vas_balance_sheet_mapping_is_non_overlapping_and_uses_tt99_accounts() -> None:
    mapping = policy.load_policy()["shared"]["coa_template"]["bctc_mapping"]
    assert mapping["version"] == 2

    seen: dict[str, str] = {}
    for line in mapping["statements"]["balance_sheet"]:
        for account_code in line["account_codes"]:
            code = str(account_code)
            assert all(
                previous_line == line["code"]
                or not (code.startswith(previous) or previous.startswith(code))
                for previous, previous_line in seen.items()
            )
            seen[code] = line["code"]

    lines = {
        line["code"]: set(line["account_codes"])
        for line in mapping["statements"]["balance_sheet"]
    }
    assert lines["A3"] == {"131", "136"}
    assert lines["A5"] == {"133", "138", "141"}


def test_tt99_statutory_forms_have_official_codes_and_formulas() -> None:
    forms = policy.load_policy()["shared"]["coa_template"]["bctc_mapping"]["statutory_forms"]

    assert forms["version"] == 1
    assert set(forms["forms"]) == {"B01-DN", "B02-DN", "B03-DN", "B09-DN"}
    b01 = {line["code"]: line for line in forms["forms"]["B01-DN"]["lines"]}
    b02 = {line["code"]: line for line in forms["forms"]["B02-DN"]["lines"]}
    b03 = {line["code"]: line for line in forms["forms"]["B03-DN"]["lines"]}
    b09 = {line["code"]: line for line in forms["forms"]["B09-DN"]["lines"]}

    assert b01["100"]["formula"] == "110+120+130+140+150+160"
    assert b01["200"]["formula"] == "210+220+230+240+250+260+270"
    assert b01["280"]["formula"] == "100+200"
    assert set(b01) == {
        "100", "110", "111", "112", "120", "121", "122", "123", "124", "125", "126",
        "130", "131", "132", "133", "134", "135", "136", "137", "140", "141", "142",
        "150", "151", "152", "153", "160", "161", "162", "163", "164", "165", "200",
        "210", "211", "212", "213", "214", "215", "216", "220", "221", "222", "223",
        "224", "225", "226", "227", "228", "229", "230", "231", "232", "233", "234",
        "235", "236", "237", "238", "240", "241", "242", "250", "251", "252", "260",
        "261", "262", "263", "264", "265", "266", "270", "271", "272", "273", "274",
        "280", "300", "310", "311", "312", "313", "314", "315", "316", "317", "318",
        "319", "320", "321", "322", "323", "324", "325", "330", "331", "332", "333",
        "334", "335", "336", "337", "338", "339", "340", "341", "342", "343", "344",
        "400", "411", "411a", "411b", "412", "413", "414", "415", "416", "417", "418",
        "419", "420", "420a", "420b", "440",
    }
    assert not ({"410", "421", "421a", "421b", "422", "429", "430"} & set(b01))
    assert b01["120"]["formula"] == "121+122+123+124+125+126"
    assert b01["130"]["formula"] == "131+132+133+134+135+136+137"
    assert b01["160"]["formula"] == "161+162+163+164+165"
    assert b01["210"]["formula"] == "211+212+213+214+215+216"
    assert b01["230"]["formula"] == "231+236+237+238"
    assert b01["310"]["formula"] == "311+312+313+314+315+316+317+318+319+320+321+322+323+324+325"
    assert b01["330"]["formula"] == "331+332+333+334+335+336+337+338+339+340+341+342+343+344"
    assert b01["400"]["formula"] == "411+412+413+414+415+416+417+418+419+420"
    assert b01["420"]["formula"] == "420a+420b"
    assert b02["10"]["formula"] == "01-02"
    assert b02["30"]["formula"] == "20+21+22-23-25-26"
    assert b02["60"]["formula"] == "50-51-52"
    assert forms["forms"]["B03-DN"]["statement"] == "cash_flow"
    assert forms["forms"]["B09-DN"]["statement"] == "notes"
    assert set(b09) == {f"N{index:02d}" for index in range(1, 11)}
    assert all(line["line_type"] == "note" for line in b09.values())
    assert b03["08"]["formula"] == "01+02+03+04+05+06+07"
    assert b03["20"]["formula"] == "08+09+10+11+12+13+14+15+16+17"
    assert b03["70"]["formula"] == "50+60+61"


def test_statutory_form_validation_rejects_unknown_formula_line(tmp_path: Path) -> None:
    bundle = deepcopy(policy.load_policy())
    lines = bundle["shared"]["coa_template"]["bctc_mapping"]["statutory_forms"]["forms"]["B02-DN"]["lines"]
    next(line for line in lines if line["code"] == "10")["formula"] = "01-99"
    path = write_policy(tmp_path / "invalid-statutory-form.yaml", policy.dump_policy(bundle))

    with pytest.raises(policy.PolicyError, match="formula references an unknown line"):
        policy.load_policy(path)


def test_bctc_mapping_rejects_overlapping_account_ranges(tmp_path: Path) -> None:
    bundle = deepcopy(policy.load_policy())
    lines = bundle["shared"]["coa_template"]["bctc_mapping"]["statements"]["balance_sheet"]
    lines[1]["account_codes"].append("131")
    path = write_policy(tmp_path / "overlapping.yaml", policy.dump_policy(bundle))

    with pytest.raises(policy.PolicyError, match="overlapping Account code ranges"):
        policy.load_policy(path)


def test_account_type_catalog_is_native_and_references_existing_accounts(tmp_path: Path) -> None:
    bundle = deepcopy(policy.load_policy())
    bundle["shared"]["coa_template"]["account_types"]["999999"] = "Cash"
    path = write_policy(tmp_path / "unknown-account-type-code.yaml", policy.dump_policy(bundle))

    with pytest.raises(policy.PolicyError, match="references unknown Account code"):
        policy.load_policy(path)

    bundle = deepcopy(policy.load_policy())
    bundle["shared"]["coa_template"]["account_types"]["111"] = "Not Native"
    path = write_policy(tmp_path / "unknown-account-type.yaml", policy.dump_policy(bundle))

    with pytest.raises(policy.PolicyError, match="not a native ERPNext Account Type"):
        policy.load_policy(path)
