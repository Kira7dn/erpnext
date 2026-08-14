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

POLICY_VERSION = 2
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


def _policy_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path).resolve()
    from letron_api.system_config import policy_path

    return policy_path().resolve()


def _scope_path(policy_path: Path) -> Path:
    adjacent = policy_path.parent.parent / "contracts" / "scope.yml"
    if adjacent.is_file():
        return adjacent
    return Path(__file__).resolve().parents[3] / "contracts" / "scope.yml"


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
    """Fill only absent values while preserving every explicit primary value."""

    if isinstance(primary, Mapping) and isinstance(fallback, Mapping):
        if not primary:
            return copy.deepcopy(primary)
        result = copy.deepcopy(dict(fallback))
        for key, value in primary.items():
            result[key] = _fill_missing(value, fallback[key]) if key in fallback else copy.deepcopy(value)
        return result
    if isinstance(primary, list) and isinstance(fallback, list):
        result = copy.deepcopy(primary)
        for index, value in enumerate(primary):
            if index < len(fallback):
                result[index] = _fill_missing(value, fallback[index])
        return result
    return copy.deepcopy(primary)


def _load_full_defaults(source: Path) -> dict[str, Any] | None:
    """Load the optional adjacent full policy used only as packaging fallback."""

    if source.name == "policy-full.yaml":
        return None
    full_source = source.with_name("policy-full.yaml")
    if not full_source.is_file():
        return None
    try:
        full = yaml.load(full_source.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except yaml.YAMLError as error:
        raise PolicyError(f"Invalid full policy YAML: {error}") from error
    if not isinstance(full, dict) or not isinstance(full.get("documents"), list):
        raise PolicyError("policy-full.yaml must contain a documents list")
    return full


def _merge_full_defaults(raw: dict[str, Any], source: Path) -> dict[str, Any]:
    """Build the effective policy without expanding its declared DocType scope."""

    full = _load_full_defaults(source)
    if full is None:
        return raw
    full_documents = {
        (item.get("doctype"), item.get("name")): item
        for item in full["documents"]
        if isinstance(item, Mapping)
    }
    merged = copy.deepcopy(raw)
    effective_documents: list[Any] = []
    for item in raw.get("documents", []):
        if not isinstance(item, Mapping):
            effective_documents.append(copy.deepcopy(item))
            continue
        fallback = full_documents.get((item.get("doctype"), item.get("name")))
        if fallback is None or item.get("state") == "absent" or item.get("fields") == {}:
            effective_documents.append(copy.deepcopy(item))
            continue
        effective_documents.append(_fill_missing(item, fallback))
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
    raw = _merge_full_defaults(raw, source)
    unknown_top_level = set(raw) - {"version", "scope_version", "erpnext_version", "bootstrap", "assets", "documents"}
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
        if not isinstance(bootstrap, dict) or set(bootstrap) != {"company"}:
            raise PolicyError("bootstrap must contain exactly one company mapping")
        company = bootstrap["company"]
        required_company_fields = (
            "name",
            "abbreviation",
            "country",
            "currency",
            "domain",
            "chart_of_accounts",
        )
        if not isinstance(company, dict) or set(company) != set(required_company_fields):
            raise PolicyError(
                "bootstrap.company must contain name, abbreviation, country, currency, "
                "domain and chart_of_accounts"
            )
        for fieldname in required_company_fields:
            value = company[fieldname]
            if not isinstance(value, str) or not value.strip():
                raise PolicyError(f"bootstrap.company.{fieldname} must be a non-empty string")
        bootstrap = {"company": {key: company[key].strip() for key in required_company_fields}}

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

    normalized_policy = {
        "version": POLICY_VERSION,
        "scope_version": POLICY_SCOPE_VERSION,
        "erpnext_version": raw["erpnext_version"],
        "assets": _plain(assets),
        "documents": normalized,
    }
    if bootstrap is not None:
        normalized_policy["bootstrap"] = bootstrap
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


def _frappe() -> Any:
    import frappe

    return frappe


def _runtime_erpnext_version() -> str:
    import erpnext

    return str(getattr(erpnext, "__version__", ""))


def _field_map(meta: Any) -> dict[str, Any]:
    return {field.fieldname: field for field in meta.fields if field.fieldname}


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
        for fieldname, value in entry["fields"].items():
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
        field_changes = {
            fieldname: {"current": current.get(fieldname), "desired": desired}
            for fieldname, desired in entry["fields"].items()
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
            if _is_acceptance_fixture(name) or _is_standard_policy_record(_policy_path(path), doctype, name):
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
                doc.update(entry["fields"])
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
    bundle["documents"] = documents
    return bundle


def export_current() -> str:
    """Export the installed native configuration as a canonical YAML string."""

    return dump_policy(export_current_bundle())


def materialize_native_defaults() -> dict[str, Any]:
    """Merge native bootstrap output into YAML without replacing declared policy."""

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
    merged["documents"] = _sorted_entries(documents.values())
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


def sync() -> dict[str, Any]:
    """Bench/Compose entrypoint."""

    return apply()


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
