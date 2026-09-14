"""Git-backed ERPNext policy configuration owned by ``letron_api``.

The YAML file is the source of truth.  This module deliberately does not
implement business policy: it validates, compares and applies native Frappe
documents through their normal controllers.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
import re
import sys
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import yaml
from yaml.resolver import BaseResolver

POLICY_VERSION = 3
POLICY_SCOPE_VERSION = 1
POLICY_STATUS_CACHE_KEY = "letron:business-policy:status"
POLICY_ASSET_FOLDER = "Home/Letron Policy Assets"

SCOPE_REQUIRED_FIELDS = {
    "name",
    "classification",
    "source_type",
    "owner",
    "selector",
    "dependency",
    "standard_record_rule",
    "schema_fingerprint",
}
SCOPE_ACCEPTANCE_FIELDS = {
    "fixture_builder",
    "structural_test",
    "cleanup_handler",
    "dependency_prerequisites",
    "controller_effect_assertion",
}
SCOPE_CLASSIFICATIONS = {
    "managed",
    "conditional",
    "entity",
    "transaction",
    "system",
    "secret",
    "transient",
    "excluded",
}

# This is an administrative allowlist, not a generic DocType proxy.  It covers
# every persistent ERPNext Single used as business configuration in the pinned
# ERPNext release, plus the native non-Single policy documents below.  Ephemeral
# Desk tools are classified separately so a new upstream Single cannot silently
# fall outside the bundle.
POLICY_DOCTYPES = (
    "Role",
    "Role Profile",
    "Workflow State",
    "Workflow Action Master",
    "Company",
    "Finance Book",
    "Fiscal Year",
    "Accounting Dimension",
    "Accounting Dimension Filter",
    "Accounting Period",
    "Accounts Settings",
    "Buying Settings",
    "Currency Exchange Settings",
    "Delivery Settings",
    "Item Variant Settings",
    "Ledger Health Monitor",
    "Pegged Currencies",
    "Selling Settings",
    "Stock Settings",
    "Stock Reposting Settings",
    "Global Defaults",
    "Bank",
    "Bank Account",
    "Bank Transaction Rule",
    "Supplier Scorecard",
    "Inventory Dimension",
    "Putaway Rule",
    "Quality Inspection Template",
    "Shipment Parcel Template",
    "Stock Entry Type",
    "Cheque Print Template",
    "Cost Center",
    "Cost Center Allocation",
    "Dunning Type",
    "Financial Report Template",
    "Item Tax Template",
    "Journal Entry Template",
    "Loyalty Program",
    "Monthly Distribution",
    "Payment Term",
    "Payment Terms Template",
    "Pricing Rule",
    "Promotional Scheme",
    "Purchase Taxes and Charges Template",
    "Sales Taxes and Charges Template",
    "Shipping Rule",
    "Tax Category",
    "Tax Rule",
    "Tax Withholding Category",
    "Tax Withholding Group",
    "Terms and Conditions",
    "Custom DocPerm",
    "Workflow",
    "Assignment Rule",
    "Document Naming Rule",
    "Print Settings",
    "Print Format",
    "Letter Head",
    "Email Template",
    "Notification",
)

SINGLE_DOCTYPES = {
    "Accounts Settings",
    "Appointment Booking Settings",
    "Buying Settings",
    "CRM Settings",
    "Currency Exchange Settings",
    "Delivery Settings",
    "Item Variant Settings",
    "Ledger Health Monitor",
    "Manufacturing Settings",
    "Pegged Currencies",
    "Plaid Settings",
    "Projects Settings",
    "Selling Settings",
    "Print Settings",
    "Stock Settings",
    "Stock Reposting Settings",
    "Subscription Settings",
    "Support Settings",
    "Video Settings",
    "Global Defaults",
}

# Only settings used by the currently deployed operational modules are exported
# automatically. Other supported Singles can still be declared explicitly when
# their module is enabled.
AUTO_EXPORT_SINGLE_DOCTYPES = {
    "Accounts Settings",
    "Buying Settings",
    "Currency Exchange Settings",
    "Delivery Settings",
    "Global Defaults",
    "Item Variant Settings",
    "Ledger Health Monitor",
    "Pegged Currencies",
    "POS Settings",
    "Selling Settings",
    "Stock Reposting Settings",
    "Stock Settings",
}

# Native defaults/entities are supported for explicit policy dependencies but
# are not blindly copied into a tenant policy bundle.
AUTO_EXPORT_NON_SINGLE_DOCTYPES = {
    "Accounting Dimension",
    "Accounting Dimension Filter",
    "Accounting Period",
    "Authorization Rule",
    "Bank Transaction Rule",
    "Supplier Scorecard",
    "Inventory Dimension",
    "Putaway Rule",
    "Quality Inspection Template",
    "Shipment Parcel Template",
    "Stock Entry Type",
    "Budget",
    "Cheque Print Template",
    "Cost Center Allocation",
    "Custom DocPerm",
    "Dunning Type",
    "Assignment Rule",
    "Document Naming Rule",
    "Print Format",
    "Letter Head",
    "Email Template",
    "Notification",
    "Item Tax Template",
    "Journal Entry Template",
    "Loyalty Program",
    "Monthly Distribution",
    "Payment Term",
    "Payment Terms Template",
    "POS Profile",
    "Pricing Rule",
    "Promotional Scheme",
    "Purchase Taxes and Charges Template",
    "Sales Taxes and Charges Template",
    "Shipping Rule",
    "Subscription Plan",
    "Tax Category",
    "Tax Rule",
    "Tax Withholding Category",
    "Tax Withholding Group",
    "Terms and Conditions",
    "Workflow",
}

# Native ERPNext Singles that are request-local Desk tools, not persistent
# configuration. Their values are user input/result state and must remain in the
# database rather than becoming Git policy.
TRANSIENT_SINGLE_DOCTYPES = {
    "Authorization Control",
    "Bank Clearance",
    "Bank Reconciliation Tool",
    "Bisect Accounting Statements",
    "BOM Update Tool",
    "Chart of Accounts Importer",
    "Opening Invoice Creation Tool",
    "Payment Reconciliation",
    "Quick Stock Balance",
    "Rename Tool",
    "SMS Center",
    "POS Settings",
}

FRAPPE_SINGLE_DOCTYPES = {"Print Settings"}

DEPENDENCY_ORDER = {doctype: index for index, doctype in enumerate(POLICY_DOCTYPES)}

SYSTEM_FIELDS = {
    "_assign",
    "_comments",
    "_liked_by",
    "_seen",
    "_user_tags",
    "creation",
    "docstatus",
    "doctype",
    "idx",
    "modified",
    "modified_by",
    "name",
    "owner",
    "parent",
    "parentfield",
    "parenttype",
}

LAYOUT_FIELDS = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading"}
EXECUTABLE_CODE_OPTIONS = {"Javascript"}
TABLE_FIELD_TYPES = {"Table", "Table MultiSelect"}
PUBLIC_SELECTOR_FIELDS = {
    "Assignment Rule": "document_type",
    "Document Naming Rule": "document_type",
    "Notification": "document_type",
    "Print Format": "doc_type",
    "Workflow": "document_type",
}

# User identity and credentials are not policy.  These exact native fields are
# the access-control subset managed when a User entry is present in the YAML.
USER_POLICY_FIELDS = {
    "bypass_restrict_ip_check_if_2fa_enabled",
    "enabled",
    "login_after",
    "login_before",
    "restrict_ip",
    "role_profile_name",
    "roles",
    "simultaneous_sessions",
    "user_type",
}

# ERPNext has a small number of credentials stored in Data fields rather than
# Password fields. They remain runtime secrets and are intentionally never
# exported to policy.yaml.
SECRET_FIELDS = {
    ("Currency Exchange Settings", "access_key"),
    ("Video Settings", "api_key"),
}


class PolicyError(ValueError):
    """Raised when the policy bundle is malformed or cannot converge."""


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise PolicyError(f"Duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _plain(value: Any) -> Any:
    """Return a deterministic JSON/YAML-compatible value."""

    if isinstance(value, Mapping):
        return {str(key): _plain(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "as_dict"):
        return _plain(value.as_dict())
    return value


_COMPANY_FIELDS = ("name", "abbreviation", "country", "currency", "domain", "chart_of_accounts")


def _validate_company_config(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != set(_COMPANY_FIELDS):
        raise PolicyError(
            f"{label} must contain name, abbreviation, country, currency, domain and chart_of_accounts"
        )
    normalized: dict[str, str] = {}
    for fieldname in _COMPANY_FIELDS:
        field_value = value[fieldname]
        if not isinstance(field_value, str) or not field_value.strip():
            raise PolicyError(f"{label}.{fieldname} must be a non-empty string")
        normalized[fieldname] = field_value.strip()
    return normalized


def _normalize_bootstrap(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PolicyError("bootstrap must be a mapping")

    # Keep the old shape readable for migration tooling and older candidate
    # files. New Holding policies must include the group and company list.
    if set(value) == {"company"}:
        return {"company": _validate_company_config(value["company"], "bootstrap.company")}

    if set(value) != {"company", "group", "companies"}:
        raise PolicyError("bootstrap must contain company, group and companies")

    primary = _validate_company_config(value["company"], "bootstrap.company")
    group = value["group"]
    if not isinstance(group, Mapping) or set(group) != {"name", "abbreviation"}:
        raise PolicyError("bootstrap.group must contain name and abbreviation")
    normalized_group: dict[str, str] = {}
    for fieldname in ("name", "abbreviation"):
        field_value = group[fieldname]
        if not isinstance(field_value, str) or not field_value.strip():
            raise PolicyError(f"bootstrap.group.{fieldname} must be a non-empty string")
        normalized_group[fieldname] = field_value.strip()

    companies = value["companies"]
    if not isinstance(companies, list) or not companies:
        raise PolicyError("bootstrap.companies must be a non-empty list")
    normalized_companies = [_validate_company_config(item, f"bootstrap.companies[{index}]") for index, item in enumerate(companies)]
    names = [item["name"] for item in normalized_companies]
    abbreviations = [item["abbreviation"] for item in normalized_companies]
    if len(set(names)) != len(names):
        raise PolicyError("bootstrap.companies names must be unique")
    if len(set(abbreviations)) != len(abbreviations):
        raise PolicyError("bootstrap.companies abbreviations must be unique")
    if primary["name"] not in names or primary["abbreviation"] not in abbreviations:
        raise PolicyError("bootstrap.company must identify one entry in bootstrap.companies")
    return {"company": primary, "group": normalized_group, "companies": normalized_companies}


def _validate_fiscal_year_definition(value: Any, path: str) -> dict[str, Any]:
    """Validate one native calendar Fiscal Year definition."""
    if not isinstance(value, Mapping):
        raise PolicyError(f"{path} must be a mapping")
    required = {"name", "start_date", "end_date", "calendar_year", "companies"}
    unknown = set(value) - required
    if unknown:
        raise PolicyError(f"{path} has unsupported keys: " + ", ".join(sorted(unknown)))
    missing = required - set(value)
    if missing:
        raise PolicyError(f"{path} lacks required keys: " + ", ".join(sorted(missing)))
    if not isinstance(value["name"], str) or not re.fullmatch(r"[0-9]{4}", value["name"]):
        raise PolicyError(f"{path}.name must be a four-digit year")
    if value["calendar_year"] is not True:
        raise PolicyError(f"{path}.calendar_year must be true")
    dates: dict[str, str] = {}
    for fieldname in ("start_date", "end_date"):
        fiscal_value = value[fieldname]
        if not isinstance(fiscal_value, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", fiscal_value
        ):
            raise PolicyError(f"{path}.{fieldname} must use YYYY-MM-DD")
        dates[fieldname] = fiscal_value
    if dates["start_date"] >= dates["end_date"]:
        raise PolicyError(f"{path}.start_date must be before end_date")
    if (dates["start_date"], dates["end_date"]) != (
        f"{value['name']}-01-01",
        f"{value['name']}-12-31",
    ):
        raise PolicyError(f"{path} calendar_year must run from YYYY-01-01 to YYYY-12-31")
    companies = value["companies"]
    if (
        not isinstance(companies, list)
        or not companies
        or any(not isinstance(company, str) or not company.strip() for company in companies)
        or len(companies) != len(set(companies))
    ):
        raise PolicyError(f"{path}.companies must be a unique non-empty list")
    return dict(value)


def _normalize_shared(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PolicyError("shared must be a mapping")
    allowed = {
        "fiscal_year",
        "comparative_fiscal_years",
        "coa_template",
        "function_codes",
        "master_data_policy",
        "cost_centers",
        "consolidation",
    }
    unknown = set(value) - allowed
    if unknown:
        raise PolicyError("Unsupported shared keys: " + ", ".join(sorted(unknown)))

    function_codes = value.get("function_codes", [])
    if not isinstance(function_codes, list) or any(
        not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9]{1,7}", code)
        for code in function_codes
    ):
        raise PolicyError("shared.function_codes must be a list of uppercase codes")
    if len(set(function_codes)) != len(function_codes):
        raise PolicyError("shared.function_codes must be unique")

    cost_centers = value.get("cost_centers", [])
    if not isinstance(cost_centers, list):
        raise PolicyError("shared.cost_centers must be a list")
    normalized_cost_centers = []
    for index, item in enumerate(cost_centers):
        if not isinstance(item, Mapping) or set(item) != {"company", "code", "functions"}:
            raise PolicyError(f"shared.cost_centers[{index}] must contain company, code and functions")
        company = item["company"]
        code = item["code"]
        functions = item["functions"]
        if not isinstance(company, str) or not company.strip() or not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9]{1,7}", code):
            raise PolicyError(f"shared.cost_centers[{index}] has invalid company or code")
        if not isinstance(functions, list) or any(function not in function_codes for function in functions):
            raise PolicyError(f"shared.cost_centers[{index}].functions must reference shared.function_codes")
        if len(set(functions)) != len(functions):
            raise PolicyError(f"shared.cost_centers[{index}].functions must be unique")
        normalized_cost_centers.append({"company": company.strip(), "code": code, "functions": list(functions)})

    coa_template = _plain(value.get("coa_template", {}))
    coa_codes: set[str] = set()
    if coa_template:
        accounts = coa_template.get("accounts", [])
        if accounts:
            if not isinstance(accounts, list):
                raise PolicyError("shared.coa_template.accounts must be a list")
            codes: list[str] = []
            root_types = {"Asset", "Liability", "Equity", "Income", "Expense"}
            for index, account in enumerate(accounts):
                if not isinstance(account, Mapping):
                    raise PolicyError(f"shared.coa_template.accounts[{index}] must be a mapping")
                code = account.get("code")
                name = account.get("name")
                root_type = account.get("root_type")
                if not isinstance(code, str) or not re.fullmatch(r"[0-9]{3,6}", code):
                    raise PolicyError(f"shared.coa_template.accounts[{index}].code is invalid")
                if not isinstance(name, str) or not name.strip() or root_type not in root_types:
                    raise PolicyError(f"shared.coa_template.accounts[{index}] has invalid name or root_type")
                codes.append(code)
            if len(codes) != len(set(codes)):
                raise PolicyError("shared.coa_template.accounts codes must be unique")
            coa_codes = set(codes)
            code_set = set(codes)
            account_types = coa_template.get("account_types", {})
            native_account_types = {
                "Accumulated Depreciation",
                "Asset Received But Not Billed",
                "Bank",
                "Cash",
                "Chargeable",
                "Capital Work in Progress",
                "Cost of Goods Sold",
                "Current Asset",
                "Current Liability",
                "Depreciation",
                "Direct Expense",
                "Direct Income",
                "Equity",
                "Expense Account",
                "Expenses Included In Asset Valuation",
                "Expenses Included In Valuation",
                "Fixed Asset",
                "Income Account",
                "Indirect Expense",
                "Indirect Income",
                "Liability",
                "Payable",
                "Receivable",
                "Round Off",
                "Round Off for Opening",
                "Stock",
                "Stock Adjustment",
                "Stock Received But Not Billed",
                "Service Received But Not Billed",
                "Tax",
                "Temporary",
            }
            if not isinstance(account_types, Mapping):
                raise PolicyError("shared.coa_template.account_types must be a mapping")
            for account_code, account_type in account_types.items():
                if str(account_code) not in coa_codes:
                    raise PolicyError(
                        "shared.coa_template.account_types references unknown Account code "
                        + str(account_code)
                    )
                if account_type not in native_account_types:
                    raise PolicyError(
                        "shared.coa_template.account_types["
                        + str(account_code)
                        + "] is not a native ERPNext Account Type"
                    )
            for index, account in enumerate(accounts):
                parent_code = account.get("parent_code")
                if parent_code is not None and parent_code not in code_set:
                    raise PolicyError(f"shared.coa_template.accounts[{index}].parent_code is unknown")
        mapping = coa_template.get("bctc_mapping", {})
        if mapping:
            if not isinstance(mapping, Mapping):
                raise PolicyError("shared.coa_template.bctc_mapping must be a mapping")
            unknown_mapping = set(mapping) - {"version", "statements", "statutory_forms"}
            if unknown_mapping:
                raise PolicyError(
                    "shared.coa_template.bctc_mapping has unsupported keys: "
                    + ", ".join(sorted(unknown_mapping))
                )
            statements = mapping.get("statements", {})
            if not isinstance(statements, Mapping):
                raise PolicyError("shared.coa_template.bctc_mapping.statements must be a mapping")
            for statement, lines in statements.items():
                if not isinstance(lines, list) or any(
                    not isinstance(line, Mapping)
                    or not isinstance(line.get("code"), str)
                    or not isinstance(line.get("name"), str)
                    or not isinstance(line.get("account_codes"), list)
                    for line in lines
                ):
                    raise PolicyError(f"shared.coa_template.bctc_mapping.statements.{statement} is invalid")
                seen_codes: dict[str, str] = {}
                for line in lines:
                    line_code = str(line["code"])
                    for account_code in line["account_codes"]:
                        normalized_code = str(account_code)
                        if coa_codes and normalized_code not in coa_codes:
                            raise PolicyError(
                                "shared.coa_template.bctc_mapping.statements."
                                f"{statement}.{line_code} references unknown Account code {normalized_code}"
                            )
                        for previous_code, previous_line in seen_codes.items():
                            if previous_line != line_code and (
                                normalized_code.startswith(previous_code)
                                or previous_code.startswith(normalized_code)
                            ):
                                raise PolicyError(
                                    "shared.coa_template.bctc_mapping.statements."
                                    f"{statement} has overlapping Account code ranges "
                                    f"{previous_code} ({previous_line}) and "
                                    f"{normalized_code} ({line_code})"
                                )
                        seen_codes[normalized_code] = line_code

            statutory_forms = mapping.get("statutory_forms")
            if statutory_forms is not None:
                if not isinstance(statutory_forms, Mapping) or set(statutory_forms) != {
                    "version",
                    "regulation",
                    "forms",
                }:
                    raise PolicyError(
                        "shared.coa_template.bctc_mapping.statutory_forms has an invalid shape"
                    )
                if statutory_forms["version"] != 1 or statutory_forms["regulation"] != "Thông tư 99/2025/TT-BTC":
                    raise PolicyError(
                        "shared.coa_template.bctc_mapping.statutory_forms must use TT99 version 1"
                    )
                forms = statutory_forms["forms"]
                if not isinstance(forms, Mapping) or set(forms) != {"B01-DN", "B02-DN", "B03-DN", "B09-DN"}:
                    raise PolicyError(
                        "shared.coa_template.bctc_mapping.statutory_forms must define B01-DN, B02-DN, B03-DN and B09-DN"
                    )
                formula_token = re.compile(r"[0-9]+[a-z]?")
                form_code_pattern = re.compile(r"[0-9]{2,3}[a-z]?")
                note_code_pattern = re.compile(r"N[0-9]{2}")
                allowed_line_types = {"account", "subtotal", "metric", "note"}
                allowed_sources = {
                    "consolidation_only",
                    "not_in_coa",
                    "subledger_classification_required",
                }
                for form_code, form in forms.items():
                    if not isinstance(form, Mapping) or set(form) != {
                        "name",
                        "statement",
                        "columns",
                        "lines",
                    }:
                        raise PolicyError(
                            f"statutory form {form_code} has an invalid shape"
                        )
                    if form["statement"] not in {"balance_sheet", "profit_and_loss", "cash_flow", "notes"}:
                        raise PolicyError(f"statutory form {form_code} has an invalid statement")
                    if not isinstance(form["columns"], list) or len(form["columns"]) != 2 or any(
                        not isinstance(column, str) or not column.strip() for column in form["columns"]
                    ):
                        raise PolicyError(f"statutory form {form_code}.columns is invalid")
                    lines = form["lines"]
                    if not isinstance(lines, list) or not lines:
                        raise PolicyError(f"statutory form {form_code}.lines must be a non-empty list")
                    line_codes: set[str] = set()
                    for index, line in enumerate(lines):
                        if not isinstance(line, Mapping) or not {
                            "code",
                            "name",
                            "line_type",
                        } <= set(line):
                            raise PolicyError(f"statutory form {form_code}.lines[{index}] is invalid")
                        line_code = line["code"]
                        line_type = line["line_type"]
                        code_pattern = note_code_pattern if line_type == "note" else form_code_pattern
                        if not isinstance(line_code, str) or not code_pattern.fullmatch(line_code):
                            raise PolicyError(f"statutory form {form_code}.lines[{index}].code is invalid")
                        if line_code in line_codes:
                            raise PolicyError(f"statutory form {form_code} line codes must be unique")
                        line_codes.add(line_code)
                        if not isinstance(line["name"], str) or not line["name"].strip() or line_type not in allowed_line_types:
                            raise PolicyError(f"statutory form {form_code}.lines[{index}] has invalid name or line_type")
                        if line_type == "account":
                            if set(line) - {
                                "code",
                                "name",
                                "line_type",
                                "source_account_codes",
                                "maturity",
                                "source",
                            }:
                                raise PolicyError(f"statutory form {form_code}.lines[{index}] has unsupported account keys")
                            account_codes = line.get("source_account_codes")
                            if not isinstance(account_codes, list) or any(
                                not isinstance(account_code, str) or not re.fullmatch(r"[0-9]{3,6}", account_code)
                                for account_code in account_codes
                            ):
                                raise PolicyError(f"statutory form {form_code}.lines[{index}].source_account_codes is invalid")
                            if coa_codes and any(account_code not in coa_codes for account_code in account_codes):
                                raise PolicyError(
                                    f"statutory form {form_code}.lines[{index}] references an unknown Account code"
                                )
                            source = line.get("source")
                            if source is not None and source not in allowed_sources:
                                raise PolicyError(f"statutory form {form_code}.lines[{index}].source is invalid")
                            if not account_codes and source not in {"consolidation_only", "not_in_coa"}:
                                raise PolicyError(
                                    f"statutory form {form_code}.lines[{index}] needs source_account_codes or an explicit source"
                                )
                            if line.get("maturity") not in {None, "current", "non_current"}:
                                raise PolicyError(f"statutory form {form_code}.lines[{index}].maturity is invalid")
                        elif line_type == "subtotal":
                            formula = line.get("formula")
                            if not isinstance(formula, str) or not re.fullmatch(r"[0-9a-z+\-]+", formula):
                                raise PolicyError(f"statutory form {form_code}.lines[{index}].formula is invalid")
                            if set(formula_token.findall(formula)) - line_codes:
                                # Forward references are valid, so defer the complete check below.
                                continue
                        elif line_type == "metric":
                            if not isinstance(line.get("metric"), str) or not line["metric"].strip():
                                raise PolicyError(f"statutory form {form_code}.lines[{index}].metric is invalid")
                        elif line_type == "note":
                            if set(line) - {"code", "name", "line_type", "source", "required"}:
                                raise PolicyError(
                                    f"statutory form {form_code}.lines[{index}] has unsupported note keys"
                                )
                            if not isinstance(line.get("source"), str) or not line["source"].strip():
                                raise PolicyError(
                                    f"statutory form {form_code}.lines[{index}].source is invalid"
                                )
                            if line.get("required") is not None and not isinstance(line["required"], bool):
                                raise PolicyError(
                                    f"statutory form {form_code}.lines[{index}].required is invalid"
                                )
                    for line in lines:
                        if line["line_type"] == "subtotal" and set(formula_token.findall(line["formula"])) - line_codes:
                            raise PolicyError(
                                f"statutory form {form_code}.lines[{line['code']}] formula references an unknown line"
                            )
        reporting = coa_template.get("reporting", {})
        if reporting:
            if not isinstance(reporting, Mapping):
                raise PolicyError("shared.coa_template.reporting must be a mapping")
            allowed_reporting = {
                "cash_flow_categories",
                "cash_flow",
                "currency",
                "assets",
                "current_non_current",
                "statement_classification",
                "disclosure_notes",
                "effective_from",
                "effective_to",
            }
            unknown_reporting = set(reporting) - allowed_reporting
            if unknown_reporting:
                raise PolicyError(
                    "shared.coa_template.reporting has unsupported keys: "
                    + ", ".join(sorted(unknown_reporting))
                )

            categories = reporting.get("cash_flow_categories")
            if categories is not None and (
                not isinstance(categories, list)
                or categories != ["operating", "investing", "financing"]
            ):
                raise PolicyError(
                    "shared.coa_template.reporting.cash_flow_categories must be "
                    "[operating, investing, financing]"
                )

            cash_flow = reporting.get("cash_flow")
            if cash_flow is not None:
                if not isinstance(cash_flow, Mapping):
                    raise PolicyError("shared.coa_template.reporting.cash_flow must be a mapping")
                if cash_flow.get("standard") != "VAS 24" or cash_flow.get("method") != "indirect":
                    raise PolicyError(
                        "shared.coa_template.reporting.cash_flow must use VAS 24 indirect method"
                    )
                flow_categories = cash_flow.get("categories")
                expected_categories = {"operating", "investing", "financing"}
                if not isinstance(flow_categories, Mapping) or set(flow_categories) != expected_categories:
                    raise PolicyError(
                        "shared.coa_template.reporting.cash_flow.categories must define operating, investing and financing"
                    )
                for category, definition in flow_categories.items():
                    if not isinstance(definition, Mapping) or set(definition) != {
                        "native_account_types",
                        "account_codes",
                    }:
                        raise PolicyError(
                            "shared.coa_template.reporting.cash_flow.categories."
                            f"{category} must contain native_account_types and account_codes"
                        )
                    account_types = definition["native_account_types"]
                    account_codes = definition["account_codes"]
                    if not isinstance(account_types, list) or not account_types or any(
                        not isinstance(item, str) or not item.strip() for item in account_types
                    ):
                        raise PolicyError(
                            "shared.coa_template.reporting.cash_flow native_account_types is invalid"
                        )
                    if not isinstance(account_codes, list) or not account_codes or any(
                        not isinstance(item, str) or not re.fullmatch(r"[0-9]{3,6}", item)
                        for item in account_codes
                    ):
                        raise PolicyError(
                            "shared.coa_template.reporting.cash_flow account_codes is invalid"
                        )

                metric_sources = cash_flow.get("metric_sources")
                if metric_sources is not None:
                    if not isinstance(metric_sources, Mapping) or not metric_sources:
                        raise PolicyError(
                            "shared.coa_template.reporting.cash_flow.metric_sources must be a non-empty mapping"
                        )
                    for metric, account_codes in metric_sources.items():
                        if not isinstance(metric, str) or not metric.strip():
                            raise PolicyError(
                                "shared.coa_template.reporting.cash_flow.metric_sources has an invalid metric"
                            )
                        if not isinstance(account_codes, list) or not account_codes or any(
                            not isinstance(item, str) or not re.fullmatch(r"[0-9]{3,6}", item)
                            for item in account_codes
                        ):
                            raise PolicyError(
                                "shared.coa_template.reporting.cash_flow.metric_sources account codes are invalid"
                            )
                        if coa_codes and any(item not in coa_codes for item in account_codes):
                            raise PolicyError(
                                "shared.coa_template.reporting.cash_flow.metric_sources references an unknown Account code"
                            )

                event_rules = cash_flow.get("event_rules")
                if event_rules is not None:
                    if not isinstance(event_rules, list) or not event_rules:
                        raise PolicyError(
                            "shared.coa_template.reporting.cash_flow.event_rules must be a non-empty list"
                        )
                    for index, rule in enumerate(event_rules):
                        if not isinstance(rule, Mapping):
                            raise PolicyError(
                                f"shared.coa_template.reporting.cash_flow.event_rules[{index}] is invalid"
                            )
                        required_rule_keys = {
                            "metric",
                            "category",
                            "counterpart_account_codes",
                            "direction",
                        }
                        if not required_rule_keys <= set(rule) or set(rule) - required_rule_keys - {"include_in_indirect"}:
                            raise PolicyError(
                                f"shared.coa_template.reporting.cash_flow.event_rules[{index}] is invalid"
                            )
                        if "include_in_indirect" in rule and not isinstance(rule["include_in_indirect"], bool):
                            raise PolicyError(
                                f"shared.coa_template.reporting.cash_flow.event_rules[{index}].include_in_indirect is invalid"
                            )
                        if not isinstance(rule["metric"], str) or not str(rule["metric"]).strip():
                            raise PolicyError(
                                f"shared.coa_template.reporting.cash_flow.event_rules[{index}].metric is invalid"
                            )
                        if rule["metric"] not in cash_flow["metric_sources"]:
                            raise PolicyError(
                                f"shared.coa_template.reporting.cash_flow.event_rules[{index}].metric is unknown"
                            )
                        if rule["category"] not in {"operating", "investing", "financing"}:
                            raise PolicyError(
                                f"shared.coa_template.reporting.cash_flow.event_rules[{index}].category is invalid"
                            )
                        account_codes = rule["counterpart_account_codes"]
                        if not isinstance(account_codes, list) or not account_codes or any(
                            not isinstance(item, str) or not re.fullmatch(r"[0-9]{3,6}", item)
                            for item in account_codes
                        ):
                            raise PolicyError(
                                f"shared.coa_template.reporting.cash_flow.event_rules[{index}].counterpart_account_codes is invalid"
                            )
                        if rule["direction"] not in {"inflow", "outflow"}:
                            raise PolicyError(
                                f"shared.coa_template.reporting.cash_flow.event_rules[{index}].direction is invalid"
                            )

            currency = reporting.get("currency")
            if currency is not None:
                if not isinstance(currency, Mapping) or set(currency) != {
                    "reporting_currency",
                    "allowed_accounting_currencies",
                    "foreign_currency_transactions",
                    "exchange_rate_source",
                    "revaluation_required_at_close",
                    "translation",
                }:
                    raise PolicyError(
                        "shared.coa_template.reporting.currency has an invalid shape"
                    )
                if not isinstance(currency["reporting_currency"], str) or not re.fullmatch(
                    r"[A-Z]{3}", currency["reporting_currency"]
                ):
                    raise PolicyError(
                        "shared.coa_template.reporting.currency.reporting_currency is invalid"
                    )
                allowed_currencies = currency["allowed_accounting_currencies"]
                if not isinstance(allowed_currencies, list) or not allowed_currencies or any(
                    not isinstance(item, str) or not re.fullmatch(r"[A-Z]{3}", item)
                    for item in allowed_currencies
                ):
                    raise PolicyError(
                        "shared.coa_template.reporting.currency.allowed_accounting_currencies is invalid"
                    )
                if currency["foreign_currency_transactions"] not in {"enabled", "disabled"}:
                    raise PolicyError(
                        "shared.coa_template.reporting.currency.foreign_currency_transactions is invalid"
                    )
                if currency["exchange_rate_source"] != "native_exchange_rate":
                    raise PolicyError(
                        "shared.coa_template.reporting.currency.exchange_rate_source must be native_exchange_rate"
                    )
                if not isinstance(currency["revaluation_required_at_close"], bool):
                    raise PolicyError(
                        "shared.coa_template.reporting.currency.revaluation_required_at_close must be boolean"
                    )
                if currency["translation"] not in {"not_configured", "native_exchange_rate"}:
                    raise PolicyError(
                        "shared.coa_template.reporting.currency.translation is invalid"
                    )

            assets = reporting.get("assets")
            if assets is not None:
                if not isinstance(assets, Mapping) or set(assets) != {
                    "default_depreciation_method",
                    "default_frequency_months",
                    "require_cost_center",
                    "accounts",
                }:
                    raise PolicyError("shared.coa_template.reporting.assets has an invalid shape")
                if assets["default_depreciation_method"] not in {
                    "Straight Line",
                    "Double Declining Balance",
                    "Written Down Value",
                    "Manual",
                }:
                    raise PolicyError(
                        "shared.coa_template.reporting.assets.default_depreciation_method is invalid"
                    )
                if not isinstance(assets["default_frequency_months"], int) or assets[
                    "default_frequency_months"
                ] <= 0:
                    raise PolicyError(
                        "shared.coa_template.reporting.assets.default_frequency_months must be positive"
                    )
                if not isinstance(assets["require_cost_center"], bool):
                    raise PolicyError(
                        "shared.coa_template.reporting.assets.require_cost_center must be boolean"
                    )
                asset_accounts = assets["accounts"]
                if not isinstance(asset_accounts, Mapping) or set(asset_accounts) != {
                    "fixed_asset",
                    "accumulated_depreciation",
                    "depreciation_expense",
                    "capital_work_in_progress",
                } or any(
                    not isinstance(item, str) or not re.fullmatch(r"[0-9]{3,6}", item)
                    for item in asset_accounts.values()
                ):
                    raise PolicyError(
                        "shared.coa_template.reporting.assets.accounts is invalid"
                    )

            disclosure_notes = reporting.get("disclosure_notes")
            if disclosure_notes is not None:
                if not isinstance(disclosure_notes, list) or any(
                    not isinstance(note, Mapping)
                    or not set(note) <= {"code", "name", "source", "required"}
                    or not {"code", "name", "source"} <= set(note)
                    or not isinstance(note["code"], str)
                    or not re.fullmatch(r"N[0-9]{2}", note["code"])
                    or not isinstance(note["name"], str)
                    or not isinstance(note["source"], str)
                    or ("required" in note and not isinstance(note["required"], bool))
                    for note in disclosure_notes
                ):
                    raise PolicyError(
                        "shared.coa_template.reporting.disclosure_notes is invalid"
                    )
                note_codes = [note["code"] for note in disclosure_notes]
                if len(note_codes) != len(set(note_codes)):
                    raise PolicyError(
                        "shared.coa_template.reporting.disclosure_notes codes must be unique"
                    )

            for fieldname in ("effective_from", "effective_to"):
                reporting_value = reporting.get(fieldname)
                if reporting_value is not None and (
                    not isinstance(reporting_value, str)
                    or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", reporting_value)
                ):
                    raise PolicyError(
                        f"shared.coa_template.reporting.{fieldname} must use YYYY-MM-DD or null"
                    )
            effective_from = reporting.get("effective_from")
            effective_to = reporting.get("effective_to")
            if effective_from and effective_to and effective_from >= effective_to:
                raise PolicyError(
                    "shared.coa_template.reporting.effective_from must be before effective_to"
                )
    fiscal_year = _plain(value.get("fiscal_year", {}))
    if fiscal_year:
        fiscal_year = _validate_fiscal_year_definition(fiscal_year, "shared.fiscal_year")
    comparative_fiscal_years = _plain(value.get("comparative_fiscal_years", []))
    if not isinstance(comparative_fiscal_years, list):
        raise PolicyError("shared.comparative_fiscal_years must be a list")
    normalized_comparative_fiscal_years = [
        _validate_fiscal_year_definition(item, f"shared.comparative_fiscal_years[{index}]")
        for index, item in enumerate(comparative_fiscal_years)
    ]
    fiscal_names = [str(item["name"]) for item in normalized_comparative_fiscal_years]
    if len(set(fiscal_names)) != len(fiscal_names):
        raise PolicyError("shared.comparative_fiscal_years names must be unique")
    if fiscal_year:
        if fiscal_year["name"] in fiscal_names:
            raise PolicyError("shared.comparative_fiscal_years must not contain shared.fiscal_year")
        expected_companies = set(fiscal_year["companies"])
        if any(set(item["companies"]) != expected_companies for item in normalized_comparative_fiscal_years):
            raise PolicyError(
                "shared.comparative_fiscal_years.companies must match shared.fiscal_year.companies"
            )
    elif normalized_comparative_fiscal_years:
        raise PolicyError("shared.fiscal_year is required when comparative years are configured")

    consolidation = _plain(value.get("consolidation", {}))
    if consolidation:
        if not isinstance(consolidation, Mapping):
            raise PolicyError("shared.consolidation must be a mapping")
        allowed_consolidation = {"holding_company", "companies", "finance_book", "reporting_currency", "elimination_rules", "require_closed_period", "intercompany_marker"}
        required = {"holding_company", "companies", "finance_book", "reporting_currency", "elimination_rules"}
        if set(consolidation) - allowed_consolidation:
            raise PolicyError("shared.consolidation has unsupported keys: " + ", ".join(sorted(set(consolidation) - allowed_consolidation)))
        if not required <= set(consolidation):
            raise PolicyError("shared.consolidation lacks required keys: " + ", ".join(sorted(required - set(consolidation))))
        if not isinstance(consolidation.get("holding_company"), str) or not consolidation["holding_company"].strip():
            raise PolicyError("shared.consolidation.holding_company must be a non-empty string")
        companies = consolidation.get("companies")
        if not isinstance(companies, list) or not companies or any(not isinstance(item, str) or not item.strip() for item in companies):
            raise PolicyError("shared.consolidation.companies must be a non-empty list of Company names")
        if consolidation["holding_company"] not in companies or len(companies) != len(set(companies)):
            raise PolicyError("shared.consolidation.companies must uniquely include holding_company")
        if not isinstance(consolidation.get("finance_book"), str) or not consolidation["finance_book"].strip():
            raise PolicyError("shared.consolidation.finance_book must be a non-empty string")
        if not isinstance(consolidation.get("reporting_currency"), str) or not consolidation["reporting_currency"].strip():
            raise PolicyError("shared.consolidation.reporting_currency must be a non-empty string")
        marker = consolidation.get("intercompany_marker")
        if marker is not None:
            if not isinstance(marker, str) or not marker.strip():
                raise PolicyError("shared.consolidation.intercompany_marker must be a non-empty string")
            marker_fields = {
                "matching_id",
                "source_company",
                "counterparty_company",
                "transaction_type",
            }
            placeholder_values = re.findall(r"\{([a-z][a-z0-9_]*)\}", marker)
            placeholders = set(placeholder_values)
            if placeholders != marker_fields or any(
                placeholder_values.count(field) != 1 for field in marker_fields
            ):
                raise PolicyError(
                    "shared.consolidation.intercompany_marker must contain exactly: "
                    + ", ".join(sorted(marker_fields))
                )
        if "require_closed_period" in consolidation and not isinstance(
            consolidation["require_closed_period"], bool
        ):
            raise PolicyError("shared.consolidation.require_closed_period must be boolean")
        rules = consolidation.get("elimination_rules")
        if not isinstance(rules, list):
            raise PolicyError("shared.consolidation.elimination_rules must be a list")
        for index, rule in enumerate(rules):
            if not isinstance(rule, Mapping):
                raise PolicyError(f"shared.consolidation.elimination_rules[{index}] must be a mapping")
            allowed_rule = {
                "code",
                "label",
                "source_account_codes",
                "counterparty_account_codes",
                "debit_account_code",
                "credit_account_code",
                "posting_mode",
            }
            unsupported_rule_keys = set(rule) - allowed_rule
            if unsupported_rule_keys:
                raise PolicyError(
                    f"shared.consolidation.elimination_rules[{index}] has unsupported keys: "
                    + ", ".join(sorted(unsupported_rule_keys))
                )
            required_rule = {"code", "source_account_codes", "counterparty_account_codes", "debit_account_code", "credit_account_code"}
            if not required_rule <= set(rule):
                raise PolicyError(f"shared.consolidation.elimination_rules[{index}] lacks required fields")
            if not isinstance(rule["code"], str) or not re.fullmatch(r"[A-Z][A-Z0-9_-]{2,31}", rule["code"]):
                raise PolicyError(f"shared.consolidation.elimination_rules[{index}].code is invalid")
            for fieldname in ("source_account_codes", "counterparty_account_codes"):
                codes = rule[fieldname]
                if not isinstance(codes, list) or not codes or any(not isinstance(code, str) or not re.fullmatch(r"[0-9]{3,6}", code) for code in codes):
                    raise PolicyError(f"shared.consolidation.elimination_rules[{index}].{fieldname} is invalid")
            for fieldname in ("debit_account_code", "credit_account_code"):
                if not isinstance(rule[fieldname], str) or not re.fullmatch(r"[0-9]{3,6}", rule[fieldname]):
                    raise PolicyError(f"shared.consolidation.elimination_rules[{index}].{fieldname} is invalid")
            posting_mode = rule.get("posting_mode", "policy_accounts")
            if posting_mode not in {"policy_accounts", "mirror_actual_accounts"}:
                raise PolicyError(
                    f"shared.consolidation.elimination_rules[{index}].posting_mode is invalid"
                )
            if coa_codes:
                referenced_codes = [
                    *rule["source_account_codes"],
                    *rule["counterparty_account_codes"],
                    rule["debit_account_code"],
                    rule["credit_account_code"],
                ]
                unknown_codes = sorted(
                    {str(code) for code in referenced_codes if str(code) not in coa_codes}
                )
                if unknown_codes:
                    raise PolicyError(
                        f"shared.consolidation.elimination_rules[{index}] references "
                        "unknown COA Account code(s): " + ", ".join(unknown_codes)
                    )

    return {
        "fiscal_year": fiscal_year,
        "comparative_fiscal_years": normalized_comparative_fiscal_years,
        "coa_template": coa_template,
        "function_codes": list(function_codes),
        "master_data_policy": _plain(value.get("master_data_policy", {})),
        "cost_centers": normalized_cost_centers,
        "consolidation": consolidation,
    }


def _expand_shared_cost_centers(documents: list[dict[str, Any]], policy: Mapping[str, Any]) -> list[dict[str, Any]]:
    shared = policy.get("shared", {})
    bootstrap = policy.get("bootstrap", {})
    configured_companies = bootstrap.get("companies") or ([bootstrap["company"]] if bootstrap.get("company") else [])
    companies = {item["name"]: item for item in configured_companies}
    generated_names: set[str] = set()
    for item in shared.get("cost_centers", []):
        company = companies.get(item["company"])
        if not company:
            raise PolicyError(f"shared.cost_centers references unknown Company: {item['company']}")
        abbreviation = company["abbreviation"]
        generated_names.add(f"{item['code']} - {abbreviation}")
        generated_names.update(
            f"{item['code']}-{function} - {abbreviation}"
            for function in item["functions"]
        )
    # Regenerate this declared projection deterministically. This also repairs
    # bundles produced by the earlier layout where a subsidiary's native root
    # was duplicated as a second group.
    expanded = [
        entry
        for entry in documents
        if not (entry["doctype"] == "Cost Center" and entry["name"] in generated_names)
    ]
    existing = {(item["doctype"], item["name"]) for item in expanded}
    for item in shared.get("cost_centers", []):
        company = companies.get(item["company"])
        if not company:
            raise PolicyError(f"shared.cost_centers references unknown Company: {item['company']}")
        abbreviation = company["abbreviation"]
        # ERPNext creates each Company's native root Cost Center as
        # ``<Company> - <abbr>``.  The database document name is that value,
        # while ``cost_center_name`` remains the human label.
        root_name = f"{company['name']} - {abbreviation}"
        # For subsidiaries the native Company root already is the requested
        # company cost-center group. HoldCo uses an additional HLD group below
        # its native root so the legal-entity root remains intact.
        uses_native_root = item["code"] == abbreviation
        group_name = root_name if uses_native_root else f"{item['code']} - {abbreviation}"
        group_label = company["name"] if uses_native_root else item["code"]
        group_parent = None if uses_native_root else root_name
        generated = [
            (group_name, group_label, group_parent, 1),
            *[(f"{item['code']}-{function} - {abbreviation}", f"{item['code']}-{function}", group_name, 0) for function in item["functions"]],
        ]
        for name, cost_center_name, parent, is_group in generated:
            key = ("Cost Center", name)
            if key in existing:
                continue
            expanded.append({
                "doctype": "Cost Center",
                "name": name,
                "state": "present",
                "fields": {
                    "cost_center_name": cost_center_name,
                    "company": company["name"],
                    "parent_cost_center": parent,
                    "is_group": is_group,
                    "disabled": 0,
                },
            })
            existing.add(key)
    return expanded


def _policy_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path).resolve()
    from letron_api.control.system_config import policy_path

    return policy_path().resolve()


def _scope_path(policy_path: Path) -> Path:
    adjacent = policy_path.parent.parent / "contracts" / "scope.yml"
    if adjacent.is_file():
        return adjacent
    return Path(__file__).resolve().parents[4] / "contracts" / "scope.yml"


def _load_scope(policy_path: Path) -> dict[str, Any]:
    source = _scope_path(policy_path)
    if not source.is_file():
        raise PolicyError(f"Missing policy scope contract: {source}")
    try:
        value = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise PolicyError(f"Invalid policy scope YAML: {error}") from error
    if not isinstance(value, dict) or value.get("scope_version") != POLICY_SCOPE_VERSION:
        raise PolicyError(f"Policy scope version must be {POLICY_SCOPE_VERSION}")
    raw_entries = value.get("sources")
    if not isinstance(raw_entries, list):
        raise PolicyError("policy scope sources must be a list")
    entries: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_entries):
        if not isinstance(raw_item, dict) or not raw_item.get("name"):
            raise PolicyError(f"policy scope source[{index}] must have a name")
        entries.append(cast(dict[str, Any], raw_item))
    allowed = {str(item.get("name")): item.get("classification") for item in entries if isinstance(item, dict)}
    if len(allowed) != len(entries):
        raise PolicyError("policy scope source names must be unique")
    required = {"managed", "conditional"}
    for item in entries:
        missing_fields = SCOPE_REQUIRED_FIELDS - set(item)
        if missing_fields:
            raise PolicyError(
                f"policy scope source {item['name']} lacks fields: {', '.join(sorted(missing_fields))}"
            )
        classification = str(item.get("classification", "unknown"))
        if classification not in SCOPE_CLASSIFICATIONS:
            raise PolicyError(f"policy scope source {item['name']} has invalid classification")
        if not isinstance(item.get("dependency"), list):
            raise PolicyError(f"policy scope source {item['name']}.dependency must be a list")
        fingerprint = item.get("schema_fingerprint")
        if (
            not isinstance(fingerprint, dict)
            or fingerprint.get("algorithm") != "frappe-json-v1"
            or not re.fullmatch(r"[0-9a-f]{64}", str(fingerprint.get("sha256", "")))
        ):
            raise PolicyError(f"policy scope source {item['name']} lacks schema fingerprint")
        if classification in required:
            raw_acceptance = item.get("acceptance")
            if not isinstance(raw_acceptance, dict) or SCOPE_ACCEPTANCE_FIELDS - set(raw_acceptance):
                raise PolicyError(f"policy scope source {item['name']} lacks acceptance mapping")
            acceptance = cast(dict[str, Any], raw_acceptance)
            if any(
                not isinstance(acceptance[field], str) or not acceptance[field].strip()
                for field in SCOPE_ACCEPTANCE_FIELDS - {"dependency_prerequisites"}
            ):
                raise PolicyError(f"policy scope source {item['name']} has invalid acceptance mapping")
            if acceptance["dependency_prerequisites"] != item["dependency"]:
                raise PolicyError(
                    f"policy scope source {item['name']} acceptance dependencies differ from scope"
                )
    return value


def _scope_completeness(policy_path: Path) -> dict[str, int]:
    scope = _load_scope(policy_path)
    entries = [item for item in scope["sources"] if isinstance(item, Mapping)]
    policy_entries = [item for item in entries if item.get("classification") in {"managed", "conditional"}]
    return {
        "unclassified_sources": sum(item.get("classification") in {None, "unknown", "unclassified"} for item in entries),
        "managed_entries_without_acceptance": sum(
            not isinstance(item.get("acceptance"), Mapping) for item in policy_entries
        ),
        "schema_drift": 0,
    }


def _asset_source_path(policy_path: Path, source: str) -> Path:
    """Resolve an asset only inside the fixed bind-mounted assets directory."""

    assets_root = (policy_path.parent / "assets").resolve()
    candidate = (assets_root / source).resolve()
    if candidate != assets_root and assets_root not in candidate.parents:
        raise PolicyError(f"Asset path traversal is forbidden: {source}")
    return candidate


def _fill_missing(primary: Any, fallback: Any) -> Any:
    """Merge a compact override onto defaults while preserving explicit values."""

    if isinstance(primary, Mapping) and isinstance(fallback, Mapping):
        result = copy.deepcopy(dict(fallback))
        for key, value in primary.items():
            result[key] = (
                _fill_missing(value, fallback[key])
                if key in fallback
                else copy.deepcopy(value)
            )
        return result
    # Lists are declarative collections. An explicit list replaces the default
    # list as a whole; positional merging makes child tables and company lists
    # silently inherit unrelated rows.
    return copy.deepcopy(primary)


def _load_policy_defaults(source: Path) -> dict[str, Any] | None:
    """Load the adjacent parent policy used to expand compact overrides."""

    if source.name == "policy-defaults.yaml":
        return None
    defaults_source = source.with_name("policy-defaults.yaml")
    if not defaults_source.is_file():
        return None
    try:
        defaults = yaml.load(
            defaults_source.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader
        )
    except yaml.YAMLError as error:
        raise PolicyError(f"Invalid policy defaults YAML: {error}") from error
    if not isinstance(defaults, dict) or not isinstance(defaults.get("documents"), list):
        raise PolicyError("policy-defaults.yaml must contain a documents list")
    return defaults


def _merge_policy_defaults(raw: dict[str, Any], source: Path) -> dict[str, Any]:
    """Build the effective policy from a compact child and complete parent.

    ``policy.yaml`` is a strict subset of ``policy-defaults.yaml`` at document
    identity level. A child document may override fields, or use ``state:
    absent`` to suppress a default document. New document identities must be
    added to the parent first so a compact policy cannot silently introduce an
    unmanaged configuration object.
    """

    defaults = _load_policy_defaults(source)
    if defaults is None:
        return raw
    merged = copy.deepcopy(defaults)
    for key, value in raw.items():
        if key == "documents":
            continue
        if key in defaults and isinstance(value, Mapping) and isinstance(defaults[key], Mapping):
            merged[key] = _fill_missing(value, defaults[key])
        else:
            merged[key] = copy.deepcopy(value)

    default_documents = {
        (item.get("doctype"), item.get("name")): item
        for item in defaults["documents"]
        if isinstance(item, Mapping)
    }
    effective_documents = copy.deepcopy(defaults["documents"])
    default_indexes = {
        key: index for index, key in enumerate(default_documents)
    }
    for item in raw.get("documents", []):
        if not isinstance(item, Mapping):
            raise PolicyError("policy.yaml documents must contain mappings")
        key = (item.get("doctype"), item.get("name"))
        if key not in default_indexes:
            raise PolicyError(
                "policy.yaml document is not declared in policy-defaults.yaml: "
                + "/".join(str(value) for value in key)
            )
        index = default_indexes[key]
        if item.get("state") == "absent":
            effective_documents[index] = copy.deepcopy(item)
        else:
            effective_documents[index] = _fill_missing(item, default_documents[key])
    merged["documents"] = effective_documents
    return merged


def _validate_assets(policy_path: Path, assets: Mapping[str, Any]) -> None:
    filenames: dict[str, str] = {}
    for key, manifest in assets.items():
        if not isinstance(key, str) or not key or not isinstance(manifest, Mapping):
            raise PolicyError("assets entries must be named mappings")
        allowed = {"source", "filename", "privacy", "sha256"}
        unknown = set(manifest) - allowed
        if unknown:
            raise PolicyError(f"Asset {key} has unsupported keys: {', '.join(sorted(unknown))}")
        source = manifest.get("source")
        filename = manifest.get("filename")
        privacy = manifest.get("privacy")
        checksum = manifest.get("sha256")
        if not all(isinstance(value, str) and value.strip() for value in (source, filename, checksum)):
            raise PolicyError(f"Asset {key} requires source, filename and sha256")
        if privacy not in {"public", "private"}:
            raise PolicyError(f"Asset {key}.privacy must be public or private")
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise PolicyError(f"Asset {key}.sha256 must be a lowercase SHA-256")
        if Path(filename).name != filename or filename in {".", ".."}:
            raise PolicyError(f"Asset {key}.filename must be a native basename")
        previous = filenames.setdefault(filename.casefold(), key)
        if previous != key:
            raise PolicyError(f"Asset filename collision: {previous} and {key}")
        source_path = _asset_source_path(policy_path, source)
        if not source_path.is_file():
            raise PolicyError(f"Missing policy asset: {source}")
        actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if actual != checksum:
            raise PolicyError(f"Asset checksum mismatch: {key}")


def _file_content_bytes(file_doc: Any) -> bytes:
    content = file_doc.get_content()
    return content.encode() if isinstance(content, str) else bytes(content)


class _AssetTransaction:
    def __init__(self, *, delete_folder: bool = False) -> None:
        self.created_paths: list[Path] = []
        self.stale: list[tuple[Any, Path, bytes]] = []
        self.applied = 0
        self.delete_folder = delete_folder

    def delete_stale(self) -> None:
        import frappe

        for file_doc, _path, _content in self.stale:
            frappe.delete_doc("File", file_doc.name, ignore_permissions=True, force=True)
            self.applied += 1
        if self.delete_folder and frappe.db.exists("File", POLICY_ASSET_FOLDER):
            frappe.delete_doc("File", POLICY_ASSET_FOLDER, ignore_permissions=True, force=True)

    def compensate(self) -> None:
        for path in self.created_paths:
            path.unlink(missing_ok=True)
        for _doc, path, content in self.stale:
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)


def _owned_asset_files() -> list[Any]:
    frappe = _frappe()
    names = frappe.get_all(
        "File",
        filters={"folder": POLICY_ASSET_FOLDER, "is_folder": 0},
        pluck="name",
        limit_page_length=0,
    )
    return [frappe.get_doc("File", name) for name in names]


def _plan_assets(assets: Mapping[str, Any]) -> list[dict[str, Any]]:
    frappe = _frappe()
    owned = {str(doc.file_name).casefold(): doc for doc in _owned_asset_files()}
    changes: list[dict[str, Any]] = []
    for key, manifest in assets.items():
        filename = str(manifest["filename"])
        is_private = str(manifest["privacy"]) == "private"
        expected_url = f"/{'private/' if is_private else ''}files/{filename}"
        collisions = frappe.get_all(
            "File",
            filters={"file_name": filename},
            fields=["name", "file_url", "is_private", "attached_to_field"],
        )
        for collision in collisions:
            collision_doc = frappe.get_doc("File", collision.get("name"))
            if collision_doc.folder != POLICY_ASSET_FOLDER:
                raise PolicyError(f"Asset {key} collides with unmanaged File {collision.get('name')}")
        file_doc = owned.get(filename.casefold())
        if file_doc is None:
            changes.append({"document": f"asset/{key}", "operation": "create-asset"})
            continue
        if file_doc.file_url != expected_url or bool(file_doc.is_private) != is_private:
            raise PolicyError(f"Asset {key} native URL/privacy differs")
        actual = hashlib.sha256(_file_content_bytes(file_doc)).hexdigest()
        if actual != manifest["sha256"]:
            raise PolicyError(f"Asset {key} collides with an existing File checksum")
    desired_filenames = {
        str(manifest["filename"]).casefold() for manifest in assets.values()
    }
    for filename in sorted(set(owned) - desired_filenames):
        changes.append({"document": f"asset/{filename}", "operation": "delete-asset"})
    return changes


def _materialize_assets(
    policy_path: Path, assets: Mapping[str, Any]
) -> _AssetTransaction:
    """Create native owned File rows and stage stale owned files for deletion."""

    frappe = _frappe()
    transaction = _AssetTransaction(delete_folder=not assets)
    owned = {str(doc.file_name).casefold(): doc for doc in _owned_asset_files()}
    if assets and not frappe.db.exists("File", POLICY_ASSET_FOLDER):
        frappe.get_doc(
            {
                "doctype": "File",
                "name": POLICY_ASSET_FOLDER,
                "file_name": "Letron Policy Assets",
                "is_folder": 1,
                "folder": "Home",
            }
        ).insert(ignore_permissions=True)
    for manifest in assets.values():
        filename = str(manifest["filename"])
        if filename.casefold() in owned:
            continue
        source_path = _asset_source_path(policy_path, str(manifest["source"]))
        is_private = str(manifest["privacy"]) == "private"
        file_doc = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": filename,
                "is_private": int(is_private),
                "content": source_path.read_bytes(),
                "folder": POLICY_ASSET_FOLDER,
            }
        )
        file_doc.insert(ignore_permissions=True)
        transaction.created_paths.append(Path(file_doc.get_full_path()))
        transaction.applied += 1
    desired_filenames = {
        str(manifest["filename"]).casefold() for manifest in assets.values()
    }
    for filename in sorted(set(owned) - desired_filenames):
        file_doc = owned[filename]
        transaction.stale.append(
            (file_doc, Path(file_doc.get_full_path()), _file_content_bytes(file_doc))
        )
    return transaction


def load_policy(path: str | Path | None = None) -> dict[str, Any]:
    source = _policy_path(path)
    if not source.is_file():
        raise PolicyError(f"Missing policy YAML: {source}")
    try:
        raw = yaml.load(source.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except yaml.YAMLError as error:
        raise PolicyError(f"Invalid policy YAML: {error}") from error
    if not isinstance(raw, dict):
        raise PolicyError("Policy YAML root must be a mapping")
    raw = _merge_policy_defaults(raw, source)
    unknown_top_level = set(raw) - {"version", "scope_version", "erpnext_version", "bootstrap", "shared", "assets", "documents"}
    if unknown_top_level:
        raise PolicyError("Unsupported top-level policy keys: " + ", ".join(sorted(unknown_top_level)))
    if raw.get("version") != POLICY_VERSION:
        raise PolicyError(f"Policy version must be {POLICY_VERSION}")
    if raw.get("scope_version") != POLICY_SCOPE_VERSION:
        raise PolicyError(f"Policy scope version must be {POLICY_SCOPE_VERSION}")
    if not isinstance(raw.get("erpnext_version"), str) or not raw["erpnext_version"].strip():
        raise PolicyError("erpnext_version must be a non-empty string")
    assets = raw.get("assets", {})
    if not isinstance(assets, dict):
        raise PolicyError("assets must be a mapping")
    _validate_assets(source, assets)
    documents = raw.get("documents")
    if not isinstance(documents, list):
        raise PolicyError("documents must be a list")
    scope = _load_scope(source)
    scoped_names = {
        str(item["name"]): item["classification"]
        for item in scope["sources"]
        if isinstance(item, dict) and "name" in item
    }
    if any(scoped_names.get(doctype) in {None, "unknown"} for doctype in POLICY_DOCTYPES):
        missing = [doctype for doctype in POLICY_DOCTYPES if scoped_names.get(doctype) in {None, "unknown"}]
        raise PolicyError("Policy scope does not manage allowlisted DocTypes: " + ", ".join(missing))

    bootstrap = raw.get("bootstrap")
    if bootstrap is not None:
        bootstrap = _normalize_bootstrap(bootstrap)

    has_shared = "shared" in raw
    shared = _normalize_shared(raw.get("shared", {}))
    if bootstrap and has_shared:
        configured_companies = {
            str(item["name"])
            for item in bootstrap.get("companies", [])
            if isinstance(item, Mapping) and item.get("name")
        }
        fiscal_year = shared.get("fiscal_year", {})
        if fiscal_year and set(fiscal_year.get("companies", [])) != configured_companies:
            raise PolicyError(
                "shared.fiscal_year.companies must match bootstrap.companies"
            )
        for index, comparative in enumerate(shared.get("comparative_fiscal_years", [])):
            if set(comparative.get("companies", [])) != configured_companies:
                raise PolicyError(
                    f"shared.comparative_fiscal_years[{index}].companies must match bootstrap.companies"
                )
        consolidation = shared.get("consolidation", {})
        if consolidation and set(consolidation.get("companies", [])) != configured_companies:
            raise PolicyError(
                "shared.consolidation.companies must match bootstrap.companies"
            )

    seen: set[tuple[str, str]] = set()
    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(documents):
        if not isinstance(entry, dict):
            raise PolicyError(f"documents[{index}] must be a mapping")
        unknown = set(entry) - {"doctype", "name", "state", "fields"}
        if unknown:
            raise PolicyError(f"documents[{index}] has unsupported keys: {', '.join(sorted(unknown))}")
        raw_doctype = entry.get("doctype")
        raw_name = entry.get("name")
        raw_state = entry.get("state", "present")
        fields = entry.get("fields", {})
        if not isinstance(raw_doctype, str) or raw_doctype not in POLICY_DOCTYPES:
            raise PolicyError(f"documents[{index}] uses unsupported DocType: {raw_doctype}")
        if not isinstance(raw_name, str) or not raw_name:
            raise PolicyError(f"documents[{index}].name must be a non-empty string")
        if not isinstance(raw_state, str):
            raise PolicyError(f"documents[{index}].state must be present or absent")
        doctype = raw_doctype
        name = raw_name
        state = raw_state
        if doctype in SINGLE_DOCTYPES and name != doctype:
            raise PolicyError(f"Single DocType {doctype} must use name {doctype}")
        if state not in {"present", "absent"}:
            raise PolicyError(f"documents[{index}].state must be present or absent")
        if state == "present" and not isinstance(fields, dict):
            raise PolicyError(f"documents[{index}].fields must be a mapping")
        if state == "absent" and fields:
            raise PolicyError(f"documents[{index}] cannot define fields when state is absent")
        key = (doctype, name)
        if key in seen:
            raise PolicyError(f"Duplicate policy document: {doctype}/{name}")
        seen.add(key)
        normalized.append(
            {"doctype": doctype, "name": name, "state": state, "fields": _plain(fields)}
        )

    fiscal_year = shared.get("fiscal_year", {})
    fiscal_definitions = ([fiscal_year] if fiscal_year else []) + list(
        shared.get("comparative_fiscal_years", [])
    )
    if fiscal_definitions:
        fiscal_documents = [
            entry
            for entry in normalized
            if entry["doctype"] == "Fiscal Year" and entry["state"] == "present"
        ]
        expected_names = {str(item["name"]) for item in fiscal_definitions}
        actual_names = {str(item["name"]) for item in fiscal_documents}
        if actual_names != expected_names or len(fiscal_documents) != len(expected_names):
            raise PolicyError(
                "shared.fiscal_year definitions must have exactly matching present Fiscal Year documents"
            )
        for definition in fiscal_definitions:
            fiscal_document = next(
                entry for entry in fiscal_documents if entry["name"] == definition["name"]
            )
            fiscal_fields = fiscal_document["fields"]
            if (
                fiscal_fields.get("year") != definition["name"]
                or fiscal_fields.get("year_start_date") != definition["start_date"]
                or fiscal_fields.get("year_end_date") != definition["end_date"]
            ):
                path = (
                    "shared.fiscal_year"
                    if definition["name"] == fiscal_year.get("name")
                    else "shared.comparative_fiscal_years"
                )
                raise PolicyError(f"Fiscal Year document must match {path} name and dates")
            fiscal_document_companies = {
                str(row.get("company"))
                for row in fiscal_fields.get("companies", [])
                if isinstance(row, Mapping) and row.get("company")
            }
            if fiscal_document_companies != set(definition["companies"]):
                path = (
                    "shared.fiscal_year"
                    if definition["name"] == fiscal_year.get("name")
                    else "shared.comparative_fiscal_years"
                )
                raise PolicyError(f"Fiscal Year document companies must match {path}.companies")

    normalized_policy = {
        "version": POLICY_VERSION,
        "scope_version": POLICY_SCOPE_VERSION,
        "erpnext_version": raw["erpnext_version"],
        "assets": _plain(assets),
        "documents": normalized,
    }
    if has_shared:
        normalized_policy["shared"] = shared
    if bootstrap is not None:
        normalized_policy["bootstrap"] = bootstrap
    normalized_policy["documents"] = _expand_shared_cost_centers(
        normalized_policy["documents"], normalized_policy
    )
    return normalized_policy


def policy_sha256(policy: Mapping[str, Any]) -> str:
    payload = json.dumps(_plain(policy), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dump_policy(policy: Mapping[str, Any]) -> str:
    """Serialize in stable UTF-8 YAML while preserving native names."""

    return yaml.safe_dump(
        _plain(policy),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )


def validate_file(path: str | Path | None = None) -> dict[str, Any]:
    policy = load_policy(path)
    scope_completeness = _scope_completeness(_policy_path(path))
    result = {
        "ok": True,
        "path": str(_policy_path(path)),
        "version": policy["version"],
        "schema_version": policy["version"],
        "scope_version": policy["scope_version"],
        "erpnext_version": policy["erpnext_version"],
        "documents": len(policy["documents"]),
        "sha256": policy_sha256(policy),
        "completeness": {
            **scope_completeness,
            "secret_executable_leakage": 0,
        },
    }
    if "bootstrap" in policy:
        result["bootstrap_company"] = policy["bootstrap"]["company"]["name"]
        result["bootstrap_companies"] = [
            company["name"]
            for company in policy["bootstrap"].get("companies", [policy["bootstrap"]["company"]])
        ]
        result["bootstrap_group"] = policy["bootstrap"].get("group")
    return result


def _is_standard_policy_record(policy_path: Path, doctype: str, name: str) -> bool:
    """Exclude upstream fixtures; tenant-created records remain policy-owned."""

    scope = _load_scope(policy_path)
    configured = scope.get("standard_records", {})
    if name in set(configured.get(doctype, []) or []):
        return True
    frappe = _frappe()
    if doctype == "Print Format" and frappe.db.get_value(doctype, name, "standard") == "Yes":
        return True
    if doctype == "Notification":
        document_type = frappe.db.get_value(doctype, name, "document_type")
        if document_type not in set(scope.get("public_resources", []) or []):
            return True
    return bool(
        doctype == "Pricing Rule"
        and frappe.db.get_value(doctype, name, "promotional_scheme")
    )


def _is_global_portal_rbac_record(doctype: str, name: str) -> bool:
    """RBAC DocPerm rows are owned by the Global Portal policy publisher."""

    if doctype != "Custom DocPerm":
        return False
    role = _frappe().db.get_value(doctype, name, "role")
    return isinstance(role, str) and role.startswith("Letron Policy - ")


def _is_holding_native_default(doctype: str, name: str) -> bool:
    """Allow tax templates generated by ERPNext for configured Holding entities."""

    if doctype not in {
        "Item Tax Template",
        "Purchase Taxes and Charges Template",
        "Sales Taxes and Charges Template",
    }:
        return False
    frappe = _frappe()
    company = frappe.db.get_value(doctype, name, "company")
    if not isinstance(company, str):
        return False
    bootstrap = load_policy().get("bootstrap", {})
    companies = {
        str(item["name"])
        for item in bootstrap.get("companies", [bootstrap.get("company", {})])
        if isinstance(item, Mapping) and item.get("name")
    }
    group = bootstrap.get("group") or {}
    if isinstance(group, Mapping) and group.get("name"):
        companies.add(str(group["name"]))
    return company in companies and name.startswith("Vietnam ")


def _frappe() -> Any:
    import frappe

    return frappe


def _runtime_erpnext_version() -> str:
    import erpnext

    return str(getattr(erpnext, "__version__", ""))


def _field_map(meta: Any) -> dict[str, Any]:
    return {field.fieldname: field for field in meta.fields if field.fieldname}


def _account_reference(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if value.startswith("account://"):
        code = value.removeprefix("account://")
        return code if re.fullmatch(r"[0-9]{3,6}", code) else None
    match = re.match(r"^([0-9]{3,6})(?:\s+-|\s)", value)
    return match.group(1) if match else None


def _resolve_policy_link(target: str, value: Any, context: Mapping[str, Any]) -> Any:
    """Resolve stable finance references to the native per-Company name."""
    if target != "Account" or value in (None, ""):
        return value
    code = _account_reference(value)
    if not code:
        return value
    company = context.get("company")
    if not isinstance(company, str) or not company:
        raise PolicyError(f"Account reference {value} requires a Company context")
    account_name = _frappe().db.get_value(
        "Account", {"company": company, "account_number": code}, "name"
    )
    if not account_name:
        raise PolicyError(f"Account reference {value} is not materialized for Company {company}")
    return account_name


def _resolve_policy_fields(doctype: str, fields: Mapping[str, Any]) -> dict[str, Any]:
    """Convert stable policy links before native validation/apply/readback."""
    frappe = _frappe()
    meta_fields = _field_map(frappe.get_meta(doctype))
    resolved = dict(fields)
    context = dict(fields)
    for fieldname, value in fields.items():
        field = meta_fields.get(fieldname)
        if field is None:
            continue
        if field.fieldtype == "Link":
            resolved[fieldname] = _resolve_policy_link(str(field.options), value, context)
        elif field.fieldtype in TABLE_FIELD_TYPES and isinstance(value, list):
            child_fields = _field_map(frappe.get_meta(field.options))
            rows = []
            for row in value:
                child = dict(row)
                for child_name, child_value in row.items():
                    child_field = child_fields.get(child_name)
                    if child_field and child_field.fieldtype == "Link":
                        child[child_name] = _resolve_policy_link(
                            str(child_field.options), child_value, context
                        )
                rows.append(child)
            resolved[fieldname] = rows
    return resolved


def _validate_native_value(doctype: str, field: Any, value: Any) -> None:
    fieldtype = str(field.fieldtype)
    label = f"{doctype}.{field.fieldname}"
    if fieldtype in TABLE_FIELD_TYPES:
        if not isinstance(value, list):
            raise PolicyError(f"Child table must be a list: {label}")
        if any(not isinstance(row, Mapping) for row in value):
            raise PolicyError(f"Child table rows must be mappings: {label}")
        return
    if value is None:
        return
    if fieldtype in {"Check", "Int"} and (isinstance(value, bool) or not isinstance(value, int)):
        raise PolicyError(f"Invalid integer type: {label}")
    if fieldtype in {"Float", "Currency", "Percent"} and (
        isinstance(value, bool) or not isinstance(value, (int, float))
    ):
        raise PolicyError(f"Invalid numeric type: {label}")
    if fieldtype in {
        "Data",
        "Small Text",
        "Long Text",
        "Text",
        "Text Editor",
        "HTML Editor",
        "Code",
        "Link",
        "Dynamic Link",
        "Select",
        "Attach",
        "Attach Image",
        "Date",
        "Datetime",
        "Time",
    } and not isinstance(value, str):
        raise PolicyError(f"Invalid string type: {label}")
    if fieldtype == "Select" and value not in {"", None}:
        options = [line.strip() for line in str(field.options or "").splitlines()]
        if options and value not in options:
            raise PolicyError(f"Invalid Select option: {label}={value}")


def _validate_public_selector(
    policy_path: Path, doctype: str, fields: Mapping[str, Any]
) -> None:
    selector = PUBLIC_SELECTOR_FIELDS.get(doctype)
    if not selector:
        return
    selected = fields.get(selector)
    public = set(_load_scope(policy_path).get("public_resources", []) or [])
    if selected not in public:
        raise PolicyError(f"{doctype}.{selector} must reference a public resource")


def _validate_runtime(policy: Mapping[str, Any], path: str | Path | None = None) -> None:
    frappe = _frappe()
    installed = _runtime_erpnext_version()
    if installed != policy["erpnext_version"]:
        raise PolicyError(
            f"ERPNext version mismatch: YAML={policy['erpnext_version']} runtime={installed}"
        )
    desired_names = {(str(entry["doctype"]), str(entry["name"])) for entry in policy["documents"] if entry["state"] == "present"}
    policy_path = _policy_path(path)
    for entry in policy["documents"]:
        doctype = entry["doctype"]
        meta = frappe.get_meta(doctype)
        if doctype in SINGLE_DOCTYPES and not meta.issingle:
            raise PolicyError(f"Expected native Single DocType: {doctype}")
        if entry["state"] == "absent":
            continue
        _validate_public_selector(policy_path, doctype, entry["fields"])
        fields = _field_map(meta)
        resolved_values = _resolve_policy_fields(doctype, entry["fields"])
        for fieldname, value in resolved_values.items():
            if fieldname in SYSTEM_FIELDS and not (
                doctype == "Custom DocPerm" and fieldname == "parent"
            ):
                raise PolicyError(f"System field cannot be managed: {doctype}.{fieldname}")
            field = fields.get(fieldname)
            if field is None:
                raise PolicyError(f"Unknown native field: {doctype}.{fieldname}")
            if field.fieldtype == "Password":
                raise PolicyError(f"Secret field cannot be managed: {doctype}.{fieldname}")
            if field.fieldtype == "Code" and str(field.options or "") in EXECUTABLE_CODE_OPTIONS and value not in (None, ""):
                raise PolicyError(f"Executable field cannot be managed: {doctype}.{fieldname}")
            if getattr(field, "is_virtual", False) or field.fieldtype in LAYOUT_FIELDS:
                raise PolicyError(f"Non-persisted field cannot be managed: {doctype}.{fieldname}")
            _validate_native_value(doctype, field, value)
            if field.fieldtype == "Link" and value not in (None, ""):
                target = str(field.options)
                if (target, str(value)) not in desired_names and not frappe.db.exists(target, value):
                    raise PolicyError(f"Invalid Link: {doctype}.{fieldname} -> {target}/{value}")
            if field.fieldtype in TABLE_FIELD_TYPES:
                child_fields = _field_map(frappe.get_meta(field.options))
                for row in value:
                    for child_name, child_value in row.items():
                        child_field = child_fields.get(child_name)
                        if child_field is None:
                            raise PolicyError(
                                f"Unknown native child field: {doctype}.{fieldname}.{child_name}"
                            )
                        if child_field.fieldtype == "Password":
                            raise PolicyError(
                                f"Secret child field cannot be managed: {doctype}.{fieldname}.{child_name}"
                            )
                        _validate_native_value(str(field.options), child_field, child_value)
                        if child_field and child_field.fieldtype == "Link" and child_value not in (None, ""):
                            target = str(child_field.options)
                            if (target, str(child_value)) not in desired_names and not frappe.db.exists(target, child_value):
                                raise PolicyError(f"Invalid child Link: {doctype}.{fieldname}.{child_name} -> {target}/{child_value}")


def _exists(doctype: str, name: str) -> bool:
    frappe = _frappe()
    if doctype in SINGLE_DOCTYPES:
        return True
    return bool(frappe.db.exists(doctype, name))


def _current_fields(entry: Mapping[str, Any]) -> dict[str, Any] | None:
    frappe = _frappe()
    doctype = str(entry["doctype"])
    name = str(entry["name"])
    if not _exists(doctype, name):
        return None
    doc = frappe.get_single(doctype) if doctype in SINGLE_DOCTYPES else frappe.get_doc(doctype, name)
    field_map = _field_map(frappe.get_meta(doctype))
    current: dict[str, Any] = {}
    for fieldname in entry["fields"]:
        field = field_map[fieldname]
        value = doc.get(fieldname)
        if field.fieldtype in TABLE_FIELD_TYPES:
            desired_rows = entry["fields"].get(fieldname) or []
            projected = []
            for index, row in enumerate(value or []):
                if index < len(desired_rows):
                    projected.append(
                        {
                            child_name: _plain(row.get(child_name))
                            for child_name in desired_rows[index]
                        }
                    )
                else:
                    projected.append(_export_child(row, field.options))
            value = projected
        current[fieldname] = _plain(value)
    return current


def plan(path: str | Path | None = None) -> dict[str, Any]:
    policy = load_policy(path)
    _validate_runtime(policy, path)
    scope_completeness = _scope_completeness(_policy_path(path))
    changes: list[dict[str, Any]] = []
    changes.extend(_plan_assets(policy.get("assets", {})))
    for entry in policy["documents"]:
        current = _current_fields(entry)
        key = f"{entry['doctype']}/{entry['name']}"
        if entry["state"] == "absent":
            if current is not None:
                changes.append({"document": key, "operation": "delete"})
            continue
        if current is None:
            changes.append({"document": key, "operation": "create", "fields": sorted(entry["fields"])})
            continue
        desired_fields = _resolve_policy_fields(str(entry["doctype"]), entry["fields"])
        field_changes = {
            fieldname: {"current": current.get(fieldname), "desired": desired}
            for fieldname, desired in desired_fields.items()
            if _plain(current.get(fieldname)) != _plain(desired)
        }
        if field_changes:
            changes.append({"document": key, "operation": "update", "changes": field_changes})

    expected = {
        doctype: {entry["name"] for entry in policy["documents"] if entry["doctype"] == doctype}
        for doctype in AUTO_EXPORT_NON_SINGLE_DOCTYPES
    }
    frappe = _frappe()
    for doctype, expected_names in expected.items():
        current_names = set(frappe.get_all(doctype, pluck="name", limit_page_length=0))
        for name in sorted(current_names - expected_names):
            if (
                _is_acceptance_fixture(name)
                or _is_standard_policy_record(_policy_path(path), doctype, name)
                or _is_global_portal_rbac_record(doctype, name)
                or _is_holding_native_default(doctype, name)
            ):
                continue
            changes.append(
                {"document": f"{doctype}/{name}", "operation": "unexpected-native-document"}
            )
    return {
        "ok": not changes,
        "version": policy["version"],
        "schema_version": policy["version"],
        "scope_version": policy["scope_version"],
        "erpnext_version": policy["erpnext_version"],
        "sha256": policy_sha256(policy),
        "documents": len(policy["documents"]),
        "drift_count": len(changes),
        "completeness": {
            **scope_completeness,
            "unmanaged_policy_records": sum(
                change["operation"] == "unexpected-native-document"
                for change in changes
            ),
            "runtime_drift": len(changes),
            "roundtrip_diff": 0,
        },
        "changes": changes,
    }


@contextmanager
def _applying_policy() -> Iterator[None]:
    frappe = _frappe()
    previous = getattr(frappe.flags, "in_letron_policy_apply", False)
    frappe.flags.in_letron_policy_apply = True
    try:
        yield
    finally:
        frappe.flags.in_letron_policy_apply = previous


def _dependency_order(policy_path: Path) -> dict[str, int]:
    scope = _load_scope(policy_path)
    names = {str(item["name"]) for item in scope["sources"] if isinstance(item, Mapping)}
    graph: dict[str, set[str]] = {}
    for item in scope["sources"]:
        if not isinstance(item, Mapping) or "name" not in item:
            continue
        name = str(item["name"])
        dependencies = {str(value) for value in (item.get("dependency") or [])}
        missing = dependencies - names
        if missing:
            raise PolicyError(f"Policy scope dependency missing: {name} -> {', '.join(sorted(missing))}")
        graph[name] = dependencies
    result: dict[str, int] = {}
    while graph:
        ready = sorted(name for name, dependencies in graph.items() if not dependencies)
        if not ready:
            raise PolicyError("Policy scope dependency cycle: " + ", ".join(sorted(graph)))
        for name in ready:
            result[name] = len(result)
            graph.pop(name)
        for dependencies in graph.values():
            dependencies.difference_update(ready)
    return result


def _sorted_entries(entries: Iterable[Mapping[str, Any]], *, reverse: bool = False, path: str | Path | None = None) -> list[Mapping[str, Any]]:
    order = _dependency_order(_policy_path(path))
    return sorted(entries, key=lambda entry: (order.get(str(entry["doctype"]), DEPENDENCY_ORDER.get(str(entry["doctype"]), 9999)), str(entry["name"])), reverse=reverse)


def apply(
    path: str | Path | None = None,
    *,
    commit: bool = True,
    require_convergence: bool = True,
    _failure_step: str | None = None,
) -> dict[str, Any]:
    frappe = _frappe()
    policy = load_policy(path)
    _validate_runtime(policy, path)
    before = plan(path)
    if not before["changes"]:
        result = {**before, "applied": 0}
        _cache_status(result)
        return result

    unexpected = [
        change for change in before["changes"] if change["operation"] == "unexpected-native-document"
    ]
    if unexpected:
        raise PolicyError(
            "Policy contains unexpected native documents; export or declare them before apply"
        )
    changed_documents = {change["document"] for change in before["changes"]}
    present = [
        entry
        for entry in policy["documents"]
        if entry["state"] == "present"
        and f"{entry['doctype']}/{entry['name']}" in changed_documents
    ]
    absent = [
        entry
        for entry in policy["documents"]
        if entry["state"] == "absent"
        and f"{entry['doctype']}/{entry['name']}" in changed_documents
    ]
    applied = 0
    asset_transaction = _AssetTransaction()
    cache = frappe.cache()
    previous_policy_cache = cache.get_value(POLICY_STATUS_CACHE_KEY)
    try:
        with _applying_policy():
            asset_transaction = _materialize_assets(
                _policy_path(path),
                policy.get("assets", {}),
            )
            _inject_acceptance_failure(_failure_step, "after-assets")
            for entry in _sorted_entries(present, path=path):
                doctype = str(entry["doctype"])
                name = str(entry["name"])
                creating = False
                if doctype in SINGLE_DOCTYPES:
                    doc = frappe.get_single(doctype)
                elif frappe.db.exists(doctype, name):
                    doc = frappe.get_doc(doctype, name)
                else:
                    doc = frappe.get_doc({"doctype": doctype, "name": name})
                    creating = True
                doc.update(_resolve_policy_fields(str(entry["doctype"]), entry["fields"]))
                doc.flags.ignore_permissions = True
                if creating or doc.is_new():
                    # Policy names are fixed identifiers. Native autoname and
                    # naming-series counters must not replace them or mutate
                    # tabSeries during declarative apply.
                    doc.flags.name_set = True
                    doc.insert(ignore_permissions=True)
                else:
                    doc.save(ignore_permissions=True)
                applied += 1
            _inject_acceptance_failure(_failure_step, "after-documents")

            for entry in _sorted_entries(absent, reverse=True, path=path):
                doctype = str(entry["doctype"])
                name = str(entry["name"])
                if doctype in SINGLE_DOCTYPES:
                    raise PolicyError(f"Single DocType cannot be absent: {doctype}")
                if frappe.db.exists(doctype, name):
                    frappe.delete_doc(doctype, name, ignore_permissions=True)
                    applied += 1
            asset_transaction.delete_stale()
            _inject_acceptance_failure(_failure_step, "after-deletes")
        # Cache invalidation and canonical readback are part of the transaction
        # boundary.  They must succeed before commit so a failure can still
        # roll back native documents and compensate materialized files.
        _inject_acceptance_failure(_failure_step, "before-cache")
        frappe.clear_cache()
        after = plan(path)
        if after["changes"] and require_convergence:
            summary = "; ".join(
                f"{change['document']}:{change['operation']}"
                for change in after["changes"]
            )
            raise PolicyError(
                f"Policy readback still has {after['drift_count']} drift entries: {summary}"
            )
        _inject_acceptance_failure(_failure_step, "before-commit")
        if commit:
            frappe.db.commit()
        result = {**after, "applied": applied + asset_transaction.applied}
        _cache_status(result)
        return result
    except Exception:
        frappe.db.rollback()
        asset_transaction.compensate()
        if previous_policy_cache is None:
            cache.delete_value(POLICY_STATUS_CACHE_KEY)
        else:
            cache.set_value(POLICY_STATUS_CACHE_KEY, previous_policy_cache, expires_in_sec=3600)
        raise


def _inject_acceptance_failure(actual: str | None, expected: str) -> None:
    """Private, test-runtime-only transaction boundary fault injection."""

    if actual != expected:
        return
    if not _is_test_runtime():
        raise PolicyError("Policy failure injection requires an acceptance runtime")
    raise PolicyError(f"Injected policy acceptance failure: {expected}")


def status(path: str | Path | None = None) -> dict[str, Any]:
    try:
        result = plan(path)
        result["status"] = "in-sync" if result["ok"] else "drifted"
        result.pop("changes", None)
        return result
    except Exception as error:  # noqa: BLE001 - health must expose fail-closed state
        return {
            "ok": False,
            "status": "invalid",
            "error": type(error).__name__,
            "message": str(error),
        }


def _cache_status(result: Mapping[str, Any]) -> None:
    frappe = _frappe()
    cache = frappe.cache()
    cached = {
        key: result[key]
        for key in ("ok", "version", "erpnext_version", "sha256", "documents", "drift_count")
        if key in result
    }
    cached["status"] = "in-sync" if cached.get("ok") else "drifted"
    cache.set_value(POLICY_STATUS_CACHE_KEY, cached, expires_in_sec=3600)


def cached_status() -> dict[str, Any]:
    """Return the last applied/audited state for lightweight health checks."""

    frappe = _frappe()
    cached = frappe.cache().get_value(POLICY_STATUS_CACHE_KEY)
    if isinstance(cached, dict):
        return cached
    result = status()
    _cache_status(result)
    return result


def _managed_field_names(meta: Any, doctype: str) -> list[str]:
    names: list[str] = []
    for field in meta.fields:
        if not field.fieldname or field.fieldname in SYSTEM_FIELDS:
            continue
        if (
            field.fieldtype in LAYOUT_FIELDS
            or field.fieldtype == "Password"
            or (doctype, field.fieldname) in SECRET_FIELDS
        ):
            continue
        if getattr(field, "is_virtual", False):
            continue
        if doctype == "User" and field.fieldname not in USER_POLICY_FIELDS:
            continue
        names.append(field.fieldname)
    return names


def _export_child(row: Any, child_doctype: str) -> dict[str, Any]:
    frappe = _frappe()
    meta = frappe.get_meta(child_doctype)
    return {
        fieldname: _plain(row.get(fieldname))
        for fieldname in _managed_field_names(meta, child_doctype)
    }


def _export_doc(doc: Any) -> dict[str, Any]:
    frappe = _frappe()
    meta = frappe.get_meta(doc.doctype)
    fields: dict[str, Any] = {}
    field_map = _field_map(meta)
    for fieldname in _managed_field_names(meta, doc.doctype):
        field = field_map[fieldname]
        value = doc.get(fieldname)
        if field.fieldtype in TABLE_FIELD_TYPES:
            value = [_export_child(row, field.options) for row in value or []]
        fields[fieldname] = _plain(value)
    return {"doctype": doc.doctype, "name": doc.name, "state": "present", "fields": fields}


def export_current_bundle(path: str | Path | None = None) -> dict[str, Any]:
    """Return the installed native configuration with bootstrap metadata."""

    source_policy = load_policy(path)
    desired = [
        entry for entry in source_policy["documents"] if entry["state"] == "present"
    ]
    documents: list[dict[str, Any]] = []
    for entry in desired:
        doctype = str(entry["doctype"])
        name = str(entry["name"])
        current = _current_fields(entry)
        if current is not None:
            documents.append(
                {
                    "doctype": doctype,
                    "name": name,
                    "state": "present",
                    "fields": current,
                }
            )
    bundle: dict[str, Any] = {
        "version": POLICY_VERSION,
        "scope_version": POLICY_SCOPE_VERSION,
        "erpnext_version": _runtime_erpnext_version(),
        "assets": source_policy.get("assets", {}),
    }
    if "bootstrap" in source_policy:
        bundle["bootstrap"] = source_policy["bootstrap"]
    if "shared" in source_policy:
        bundle["shared"] = source_policy["shared"]
    bundle["documents"] = documents
    return bundle


def export_current() -> str:
    """Export the installed native configuration as a canonical YAML string."""

    return dump_policy(export_current_bundle())


def materialize_native_defaults() -> dict[str, Any]:
    """Merge native bootstrap output only when it adds real policy data.

    Tenant bootstrap runs before the generic policy sync.  Rewriting the source
    YAML on every bootstrap used to be harmless-looking, but it reordered every
    declared document and stripped its comments even when the native state was
    already fully declared.  That made the policy hash change across a restart
    and turned the source file into a runtime-generated artifact.  Keep the
    declarative source byte-stable unless the native export actually contains a
    document or field that is not already represented by the policy.
    """

    source = _policy_path()
    desired = load_policy(source)
    runtime = export_current_bundle()
    documents = {
        (entry["doctype"], entry["name"]): entry for entry in runtime["documents"]
    }
    documents.update(
        {(entry["doctype"], entry["name"]): entry for entry in desired["documents"]}
    )
    merged: dict[str, Any] = {
        "version": POLICY_VERSION,
        "scope_version": POLICY_SCOPE_VERSION,
        "erpnext_version": _runtime_erpnext_version(),
        "assets": desired.get("assets", {}),
    }
    if "bootstrap" in desired:
        merged["bootstrap"] = desired["bootstrap"]
    if "shared" in desired:
        merged["shared"] = desired["shared"]
    merged["documents"] = _sorted_entries(documents.values())
    desired_documents = {
        (entry["doctype"], entry["name"]): entry for entry in desired["documents"]
    }
    merged_documents = {
        (entry["doctype"], entry["name"]): entry for entry in merged["documents"]
    }
    if merged_documents == desired_documents:
        return {
            "ok": True,
            "documents": len(desired["documents"]),
            "sha256": policy_sha256(desired),
            "changed": False,
        }
    content = dump_policy(merged)
    temporary = source.with_name(f".{source.name}.{os.getpid()}.bootstrap")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        validate_file(temporary)
        os.replace(temporary, source)
    finally:
        temporary.unlink(missing_ok=True)
    reset_policy_cache()
    return {
        "ok": True,
        "documents": len(merged["documents"]),
        "sha256": policy_sha256(merged),
        "changed": True,
    }


def export_current_base64() -> str:
    """Bench-safe transport for the canonical UTF-8 export."""

    return base64.b64encode(export_current().encode("utf-8")).decode("ascii")


@lru_cache(maxsize=1)
def _managed_entries() -> dict[tuple[str, str], frozenset[str] | None]:
    policy = load_policy()
    return {
        (entry["doctype"], entry["name"]): (
            frozenset(entry["fields"]) if entry["state"] == "present" else None
        )
        for entry in policy["documents"]
    }


def reset_policy_cache() -> None:
    """Reload managed document ownership after an atomic policy file update."""

    _managed_entries.cache_clear()


def _is_acceptance_fixture(name: str) -> bool:
    """Allow disposable runtime fixtures only on developer test sites."""

    try:
        frappe = _frappe()
        if not frappe.conf.get("developer_mode") or not frappe.conf.get("allow_tests"):
            return False
    except Exception:  # noqa: BLE001 - pure host calls have no Frappe context
        return False
    return bool(re.match(r"(?i)^acceptance-local-(?:[0-9a-f]{8}-)?", str(name)))


def _contains_acceptance_fixture(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_acceptance_fixture(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_acceptance_fixture(item) for item in value)
    return isinstance(value, str) and bool(
        re.search(r"(?i)acceptance-local-(?:[0-9a-f]{8}-)?", value)
    )


def protect_managed_configuration(doc: Any, method: str | None = None) -> None:
    """Prevent Desk/API edits from bypassing the Git-backed YAML SOT."""

    frappe = _frappe()
    flags = frappe.flags
    if any(
        getattr(flags, name, False)
        for name in (
            "in_install",
            "in_migrate",
            "in_patch",
            "in_letron_bootstrap",
            "in_letron_policy_apply",
        )
    ):
        return
    key = (doc.doctype, doc.name)
    entries = _managed_entries()
    if _is_acceptance_fixture(doc.name):
        return
    managed = entries.get(key)
    if key not in entries:
        return
    if managed is None:
        frappe.throw(
            f"{doc.doctype} {doc.name} is declared absent in config/policy.yaml",
            exc=frappe.PermissionError,
        )
        return
    assert managed is not None
    if method == "on_trash":
        frappe.throw(
            f"{doc.doctype} {doc.name} is managed by config/policy.yaml",
            exc=frappe.PermissionError,
        )
    before = doc.get_doc_before_save()
    if before is None:
        frappe.throw(
            f"{doc.doctype} {doc.name} must be created through the Letron policy sync",
            exc=frappe.PermissionError,
        )
    meta_fields = _field_map(frappe.get_meta(doc.doctype))

    def comparable(source: Any, fieldname: str) -> Any:
        field = meta_fields[fieldname]
        value = source.get(fieldname)
        if field.fieldtype in TABLE_FIELD_TYPES:
            value = [_export_child(row, field.options) for row in value or []]
        return _plain(value)

    changed = [
        fieldname
        for fieldname in managed
        if comparable(before, fieldname) != comparable(doc, fieldname)
    ]
    if changed and _is_test_runtime() and any(
        _contains_acceptance_fixture(comparable(before, fieldname))
        or _contains_acceptance_fixture(comparable(doc, fieldname))
        for fieldname in changed
    ):
        return
    if changed:
        frappe.throw(
            f"Managed policy fields can only be changed in config/policy.yaml: {', '.join(sorted(changed))}",
            exc=frappe.PermissionError,
        )


def _is_test_runtime() -> bool:
    try:
        frappe = _frappe()
        return bool(frappe.conf.get("developer_mode") and frappe.conf.get("allow_tests"))
    except Exception:  # noqa: BLE001 - host validation has no site context
        return False


def _ensure_policy_companies() -> None:
    """Materialize the Company tree declared by policy before finance sync."""
    frappe = _frappe()
    desired = load_policy()
    bootstrap = desired["bootstrap"]
    primary = dict(bootstrap["company"])
    group_config = dict(bootstrap.get("group") or {"name": primary["name"], "abbreviation": primary["abbreviation"]})

    if not frappe.db.exists("Warehouse Type", "Transit"):
        frappe.get_doc({"doctype": "Warehouse Type", "name": "Transit"}).insert(ignore_permissions=True)

    group_name = str(group_config["name"])
    if frappe.db.exists("Company", group_name):
        group = frappe.get_doc("Company", group_name)
        if not group.is_group or group.abbr != group_config["abbreviation"]:
            raise PolicyError(f"Existing Company {group_name} is not the configured Holding group")
    else:
        frappe.get_doc({
            "doctype": "Company",
            "company_name": group_name,
            "abbr": group_config["abbreviation"],
            "country": primary["country"],
            "default_currency": primary["currency"],
            "domain": primary["domain"],
            "is_group": 1,
            "create_chart_of_accounts_based_on": "Standard Template",
            "chart_of_accounts": primary["chart_of_accounts"],
        }).insert(ignore_permissions=True)

    for config in bootstrap.get("companies", [primary]):
        name = str(config["name"])
        if frappe.db.exists("Company", name):
            company = frappe.get_doc("Company", name)
            if company.is_group or company.abbr != config["abbreviation"] or company.parent_company != group_name:
                raise PolicyError(f"Existing Company {name} does not match policy")
            continue
        frappe.get_doc({
            "doctype": "Company",
            "company_name": name,
            "abbr": config["abbreviation"],
            "country": config["country"],
            "default_currency": config["currency"],
            "domain": config["domain"],
            "parent_company": group_name,
            "create_chart_of_accounts_based_on": "Standard Template",
            "chart_of_accounts": config["chart_of_accounts"],
        }).insert(ignore_permissions=True)


def _ensure_policy_shared_masters() -> None:
    """Ensure the minimal native shared masters required by transactions.

    These are ERPNext's shared operational defaults, not tenant data and not a
    second bootstrap controller.  They converge only as part of the single
    policy sync transaction so a clean site can execute the public APIs.
    """
    frappe = _frappe()
    if not frappe.db.exists("Item Group", "All Item Groups"):
        frappe.get_doc(
            {
                "doctype": "Item Group",
                "item_group_name": "All Item Groups",
                "name": "All Item Groups",
                "is_group": 1,
            }
        ).insert(ignore_permissions=True)
    if not frappe.db.exists("Item Group", "General"):
        frappe.get_doc(
            {
                "doctype": "Item Group",
                "item_group_name": "General",
                "name": "General",
                "parent_item_group": "All Item Groups",
                "is_group": 0,
            }
        ).insert(ignore_permissions=True)
    if not frappe.db.exists("UOM", "Nos"):
        frappe.get_doc(
            {
                "doctype": "UOM",
                "uom_name": "Nos",
                "name": "Nos",
                "must_be_whole_number": 1,
            }
        ).insert(ignore_permissions=True)


def _complete_policy_setup() -> None:
    """Complete native headless setup as part of policy convergence."""
    frappe = _frappe()
    import frappe.defaults as frappe_defaults

    for app_name in ("frappe", "erpnext", "letron_api"):
        installed = frappe.db.get_value("Installed Application", {"app_name": app_name}, "name")
        if installed:
            frappe.db.set_value("Installed Application", installed, "is_setup_complete", 1, update_modified=False)
    frappe_defaults.set_global_default("desktop:home_page", "desk")
    frappe_defaults.set_user_default("desktop:home_page", "desk", "Administrator")
    frappe.clear_cache()


def tenant_status() -> dict[str, object]:
    """Report policy-owned tenant readiness without a parallel controller."""
    desired = load_policy()
    bootstrap = desired.get("bootstrap", {})
    configured = bootstrap.get("company", {})
    configured_companies = bootstrap.get("companies", [configured])
    names = {str(item["name"]) for item in configured_companies}
    companies = _frappe().get_all("Company", fields=["name", "is_group", "parent_company"], limit_page_length=0)
    runtime = {str(item.name): item for item in companies}
    group = bootstrap.get("group") or {}
    group_matches = bool(group.get("name") in runtime and runtime[group["name"]].is_group)
    company_matches = bool(names and names.issubset(runtime) and all(
        not runtime[name].is_group and runtime[name].parent_company == group.get("name") for name in names
    ))
    import frappe.defaults as frappe_defaults

    setup_complete = bool(_frappe().is_setup_complete())
    return {
        "ok": bool(group_matches and company_matches and setup_complete),
        "company": configured.get("name"),
        "group": group,
        "companies": sorted(names),
        "company_count": len(companies),
        "transaction_company_count": len([item for item in companies if not item.is_group]),
        "company_matches": company_matches,
        "group_matches": group_matches,
        "setup_complete": setup_complete,
        "home_page": frappe_defaults.get_global_default("desktop:home_page"),
    }


def sync() -> dict[str, Any]:
    """Apply the complete policy, including declarative finance masters."""
    # Startup and an operator-triggered policy-apply share the same Account,
    # Company and tax-template tables.  Serialize the whole sync so a second
    # bench execute cannot hold row locks while the first one is converging.
    frappe = _frappe()
    cache = frappe.cache()
    with cache.lock("letron:business-policy:sync", timeout=600, blocking_timeout=30):
        from letron_api.control.holding_finance import apply as apply_finance

        with _applying_policy():
            # Company creation invokes ERPNext's native default Cost Center
            # creation.  Keep that side effect inside the same policy-owned
            # guard as the declarative finance materializer.
            _ensure_policy_companies()
            _ensure_policy_shared_masters()

            # Policy documents may contain Link values to finance masters (for
            # example Item Tax Template -> Account 33311).  Create/converge
            # those native masters before policy validation resolves links.
            finance_result = apply_finance()
        policy_result = apply()
        _complete_policy_setup()
        return {
            "ok": bool(policy_result.get("ok", True)) and bool(finance_result.get("ok", True)),
            "policy": policy_result,
            "holding_finance": finance_result,
        }


def audit() -> None:
    """Raise a scheduler-visible error when native configuration has drifted."""

    result = plan()
    _cache_status(result)
    if not result["ok"]:
        raise PolicyError(f"Letron business policy drift detected: {result['drift_count']} documents")


def acceptance_force_drift() -> dict[str, Any]:
    """Create one scoped direct-DB drift for Docker acceptance only."""

    frappe = _frappe()
    if not _is_test_runtime() or frappe.session.user != "Administrator":
        frappe.throw(
            "Policy drift probe is restricted to local Administrator runtime",
            exc=frappe.PermissionError,
        )
    entry = next(
        item
        for item in load_policy()["documents"]
        if item["doctype"] == "Accounts Settings"
    )
    fieldname = "check_supplier_invoice_uniqueness"
    desired = int(entry["fields"][fieldname])
    frappe.db.set_single_value("Accounts Settings", fieldname, 0 if desired else 1)
    frappe.db.commit()
    result = plan()
    if result["ok"]:
        raise PolicyError("Acceptance drift probe did not create detectable drift")
    return {"fieldname": fieldname, "desired": desired, "drift_count": result["drift_count"]}


def _main() -> int:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Validate the Letron ERPNext policy YAML")
    parser.add_argument("command", choices=("validate",))
    parser.add_argument("--path")
    args = parser.parse_args()
    if args.command == "validate":
        print(json.dumps(validate_file(args.path), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
