"""Git-backed ERPNext policy configuration owned by ``letron_api``.

The YAML file is the source of truth.  This module deliberately does not
implement business policy: it validates, compares and applies native Frappe
documents through their normal controllers.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from yaml.resolver import BaseResolver

POLICY_VERSION = 1
POLICY_STATUS_CACHE_KEY = "letron:business-policy:status"

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
    "POS Settings",
    "Projects Settings",
    "Selling Settings",
    "Stock Settings",
    "Stock Reposting Settings",
    "Subscription Settings",
    "Support Settings",
    "Video Settings",
    "Global Defaults",
    "Bank Transaction Rule",
    "Budget",
    "Cheque Print Template",
    "Cost Center Allocation",
    "Dunning Type",
    "Financial Report Template",
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
    "Custom DocPerm",
    "User Permission",
    "Authorization Rule",
    "Workflow",
    "User",
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
    "POS Settings",
    "Projects Settings",
    "Selling Settings",
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
    "Budget",
    "Cheque Print Template",
    "Cost Center Allocation",
    "Custom DocPerm",
    "Dunning Type",
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
    "User Permission",
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
}

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
    if raw.get("version") != POLICY_VERSION:
        raise PolicyError(f"Policy version must be {POLICY_VERSION}")
    if not isinstance(raw.get("erpnext_version"), str) or not raw["erpnext_version"].strip():
        raise PolicyError("erpnext_version must be a non-empty string")
    documents = raw.get("documents")
    if not isinstance(documents, list):
        raise PolicyError("documents must be a list")

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
        doctype = entry.get("doctype")
        name = entry.get("name")
        state = entry.get("state", "present")
        fields = entry.get("fields", {})
        if doctype not in POLICY_DOCTYPES:
            raise PolicyError(f"documents[{index}] uses unsupported DocType: {doctype}")
        if not isinstance(name, str) or not name:
            raise PolicyError(f"documents[{index}].name must be a non-empty string")
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
        "erpnext_version": raw["erpnext_version"],
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
    result = {
        "ok": True,
        "path": str(_policy_path(path)),
        "version": policy["version"],
        "erpnext_version": policy["erpnext_version"],
        "documents": len(policy["documents"]),
        "sha256": policy_sha256(policy),
    }
    if "bootstrap" in policy:
        result["bootstrap_company"] = policy["bootstrap"]["company"]["name"]
    return result


def _frappe() -> Any:
    import frappe

    return frappe


def _runtime_erpnext_version() -> str:
    import erpnext

    return str(getattr(erpnext, "__version__", ""))


def _field_map(meta: Any) -> dict[str, Any]:
    return {field.fieldname: field for field in meta.fields if field.fieldname}


def _validate_runtime(policy: Mapping[str, Any]) -> None:
    frappe = _frappe()
    installed = _runtime_erpnext_version()
    if installed != policy["erpnext_version"]:
        raise PolicyError(
            f"ERPNext version mismatch: YAML={policy['erpnext_version']} runtime={installed}"
        )
    for entry in policy["documents"]:
        doctype = entry["doctype"]
        meta = frappe.get_meta(doctype)
        if doctype in SINGLE_DOCTYPES and not meta.issingle:
            raise PolicyError(f"Expected native Single DocType: {doctype}")
        fields = _field_map(meta)
        for fieldname, value in entry["fields"].items():
            if fieldname in SYSTEM_FIELDS:
                raise PolicyError(f"System field cannot be managed: {doctype}.{fieldname}")
            field = fields.get(fieldname)
            if field is None:
                raise PolicyError(f"Unknown native field: {doctype}.{fieldname}")
            if field.fieldtype == "Password":
                raise PolicyError(f"Secret field cannot be managed: {doctype}.{fieldname}")
            if getattr(field, "is_virtual", False) or field.fieldtype in LAYOUT_FIELDS:
                raise PolicyError(f"Non-persisted field cannot be managed: {doctype}.{fieldname}")
            if field.fieldtype == "Table" and not isinstance(value, list):
                raise PolicyError(f"Child table must be a list: {doctype}.{fieldname}")


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
        if field.fieldtype == "Table":
            value = [_export_child(row, field.options) for row in value or []]
        current[fieldname] = _plain(value)
    return current


def plan(path: str | Path | None = None) -> dict[str, Any]:
    policy = load_policy(path)
    _validate_runtime(policy)
    changes: list[dict[str, Any]] = []
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
            if _is_acceptance_fixture(name):
                continue
            changes.append(
                {"document": f"{doctype}/{name}", "operation": "unexpected-native-document"}
            )
    return {
        "ok": not changes,
        "version": policy["version"],
        "erpnext_version": policy["erpnext_version"],
        "sha256": policy_sha256(policy),
        "documents": len(policy["documents"]),
        "drift_count": len(changes),
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


def _sorted_entries(entries: Iterable[Mapping[str, Any]], *, reverse: bool = False) -> list[Mapping[str, Any]]:
    return sorted(
        entries,
        key=lambda entry: (DEPENDENCY_ORDER[str(entry["doctype"])], str(entry["name"])),
        reverse=reverse,
    )


def apply(path: str | Path | None = None) -> dict[str, Any]:
    frappe = _frappe()
    policy = load_policy(path)
    _validate_runtime(policy)
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
    try:
        with _applying_policy():
            for entry in _sorted_entries(present):
                doctype = str(entry["doctype"])
                name = str(entry["name"])
                if doctype in SINGLE_DOCTYPES:
                    doc = frappe.get_single(doctype)
                elif frappe.db.exists(doctype, name):
                    doc = frappe.get_doc(doctype, name)
                else:
                    doc = frappe.get_doc({"doctype": doctype, "name": name})
                doc.update(entry["fields"])
                doc.flags.ignore_permissions = True
                if doc.is_new():
                    doc.insert(ignore_permissions=True)
                else:
                    doc.save(ignore_permissions=True)
                applied += 1

            for entry in _sorted_entries(absent, reverse=True):
                doctype = str(entry["doctype"])
                name = str(entry["name"])
                if doctype in SINGLE_DOCTYPES:
                    raise PolicyError(f"Single DocType cannot be absent: {doctype}")
                if frappe.db.exists(doctype, name):
                    frappe.delete_doc(doctype, name, ignore_permissions=True)
                    applied += 1
        frappe.clear_cache()
        after = plan(path)
        if after["changes"]:
            raise PolicyError(f"Policy readback still has {after['drift_count']} drift entries")
        frappe.db.commit()
        result = {**after, "applied": applied}
        _cache_status(result)
        return result
    except Exception:
        frappe.db.rollback()
        raise


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
        if field.fieldtype == "Table":
            value = [_export_child(row, field.options) for row in value or []]
        fields[fieldname] = _plain(value)
    return {"doctype": doc.doctype, "name": doc.name, "state": "present", "fields": fields}


def export_current_bundle() -> dict[str, Any]:
    """Return the installed native configuration with bootstrap metadata."""

    frappe = _frappe()
    documents: list[dict[str, Any]] = []
    for doctype in POLICY_DOCTYPES:
        if doctype in SINGLE_DOCTYPES:
            if doctype not in AUTO_EXPORT_SINGLE_DOCTYPES:
                continue
            documents.append(_export_doc(frappe.get_single(doctype)))
            continue
        if doctype not in AUTO_EXPORT_NON_SINGLE_DOCTYPES:
            continue
        for name in frappe.get_all(doctype, pluck="name", order_by="name asc", limit_page_length=0):
            documents.append(_export_doc(frappe.get_doc(doctype, name)))
    source_policy = load_policy()
    bundle: dict[str, Any] = {
        "version": POLICY_VERSION,
        "erpnext_version": _runtime_erpnext_version(),
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
        "erpnext_version": _runtime_erpnext_version(),
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
        if field.fieldtype == "Table":
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
    parser = argparse.ArgumentParser(description="Validate the Letron ERPNext policy YAML")
    parser.add_argument("command", choices=("validate",))
    parser.add_argument("--path")
    args = parser.parse_args()
    if args.command == "validate":
        print(json.dumps(validate_file(args.path), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
