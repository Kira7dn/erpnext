from __future__ import annotations

import hashlib
import json
from typing import Any

import frappe

RESOURCE_DOCTYPES = {
    "accounts/purchase-invoices": "Purchase Invoice",
    "accounts/sales-invoices": "Sales Invoice",
    "accounts/payment-entries": "Payment Entry",
    "accounts/journal-entries": "Journal Entry",
    "buying/purchase-orders": "Purchase Order",
    "selling/sales-orders": "Sales Order",
    "stock/items": "Item",
    "stock/warehouses": "Warehouse",
    "stock/material-requests": "Material Request",
    "stock/purchase-receipts": "Purchase Receipt",
    "stock/stock-entries": "Stock Entry",
    "assets/assets": "Asset",
}

POLICY_RESOURCE_DOCTYPES = {
    "accounts/bank-reconciliation": "Bank Transaction",
    "accounts/reports": "GL Entry",
    "accounts/statement-imports": "Bank Statement Import Log",
    "accounts/settings": "Accounts Settings",
    "assets/actions": "Asset",
    "assets/dashboard": "Asset",
    "assets/reports": "Asset",
}

POLICY_REPORTS = {
    "assets/reports": (
        "Fixed Asset Register",
        "Asset Depreciation Ledger",
        "Asset Depreciations and Balances",
        "Asset Maintenance",
        "Asset Activity",
    ),
}

POLICY_REPORT_DOCTYPES = {
    "assets/reports": (
        "Asset Maintenance",
        "Asset Activity",
        "Asset Repair",
        "Asset Movement",
        "Asset Value Adjustment",
    ),
}

OPERATION_FIELDS = {
    "list": "read", "read": "read", "create": "create", "update": "write",
    "delete": "delete", "report": "report",
}


def _authorized() -> None:
    from letron_api.gateway import verify_control_plane_request
    verify_control_plane_request()


def _role_name(value: str) -> str:
    if not value.startswith("Letron Policy - "):
        frappe.throw("Policy role must use the managed Letron Policy prefix", exc=frappe.ValidationError)
    return value


@frappe.whitelist(allow_guest=True)
def publish() -> dict[str, Any]:
    _authorized()
    raw = frappe.local.request.get_data(as_text=True)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        frappe.throw("Invalid access policy JSON", exc=frappe.ValidationError)
        raise exc
    policy = payload.get("policy")
    if not isinstance(policy, dict) or policy.get("schemaVersion") != 1:
        frappe.throw("Unsupported access policy", exc=frappe.ValidationError)
    version = payload.get("version")
    sha256 = payload.get("sha256")
    if not isinstance(version, int) or not isinstance(sha256, str):
        frappe.throw("Policy version/hash missing", exc=frappe.ValidationError)
    canonical = json.dumps(policy, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if not hmac.compare_digest(hashlib.sha256(canonical.encode()).hexdigest(), sha256):
        frappe.throw("Policy hash mismatch", exc=frappe.ValidationError)
    roles: set[str] = set()
    desired_permissions: dict[tuple[str, str], dict[str, int]] = {}
    desired_report_roles: dict[str, set[str]] = {}
    from letron_api.hooks import DOCUMENT_ACTIONS, PUBLIC_RESOURCE_ROUTES
    for entitlement in policy.get("entitlements", []):
        if not isinstance(entitlement, dict):
            frappe.throw("Invalid entitlement", exc=frappe.ValidationError)
        entitlement_id = entitlement.get("id")
        if not isinstance(entitlement_id, str) or not entitlement_id.startswith("group-"):
            frappe.throw("Policy role must be derived from a Lark User Group", exc=frappe.ValidationError)
        role = _role_name(f"Letron Policy - {entitlement_id}")
        roles.add(role)
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 0}).insert(ignore_permissions=True)
        for rule in entitlement.get("rules", []):
            key = f"{rule.get('module')}/{rule.get('resource')}"
            doctype = PUBLIC_RESOURCE_ROUTES.get((rule.get("module"), rule.get("resource"))) or POLICY_RESOURCE_DOCTYPES.get(key)
            if key == "erp/workspace":
                continue
            if not doctype:
                frappe.throw(f"Unregistered policy resource: {key}", exc=frappe.ValidationError)
            permission_key = (doctype, role)
            fields = desired_permissions.setdefault(permission_key, {name: 0 for name in ("read", "write", "create", "delete", "submit", "cancel", "report")})
            for operation in rule.get("operations", []):
                native = OPERATION_FIELDS.get(operation)
                if native:
                    fields[native] = 1
                # Frappe Query Reports use a separate DocPerm flag. The public
                # API models report access as read on the virtual reports
                # resource, so keep the two authorization layers aligned.
                if operation == "read" and key.endswith("/reports"):
                    fields["report"] = 1
                    for report_name in POLICY_REPORTS.get(key, ()):
                        desired_report_roles.setdefault(report_name, set()).add(role)
                    for report_doctype in POLICY_REPORT_DOCTYPES.get(key, ()):
                        report_fields = desired_permissions.setdefault((report_doctype, role), {name: 0 for name in ("read", "write", "create", "delete", "submit", "cancel", "report")})
                        report_fields["read"] = 1
                        report_fields["report"] = 1
                if operation == "update" and (
                    (rule.get("module"), rule.get("resource")) in DOCUMENT_ACTIONS
                ):
                    fields["submit"] = 1
                if operation == "delete" and (
                    (rule.get("module"), rule.get("resource")) in DOCUMENT_ACTIONS
                ):
                    fields["cancel"] = 1
    for (doctype, role), fields in desired_permissions.items():
        existing = frappe.db.get_value("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}, "name")
        values = {"doctype": "Custom DocPerm", "parent": doctype, "role": role, "permlevel": 0, **fields}
        if existing:
            doc = frappe.get_doc("Custom DocPerm", existing)
            for field, value in fields.items(): setattr(doc, field, value)
            doc.save(ignore_permissions=True)
        else:
            frappe.get_doc(values).insert(ignore_permissions=True)
    for report_name, report_roles in desired_report_roles.items():
        existing = frappe.db.get_value("Custom Role", {"report": report_name}, "name")
        values = {"doctype": "Custom Role", "report": report_name, "roles": [{"role": role} for role in sorted(report_roles)]}
        if existing:
            doc = frappe.get_doc("Custom Role", existing)
            preserved = [item.role for item in doc.roles if not item.role.startswith("Letron Policy - ")]
            doc.set("roles", [{"role": role} for role in preserved] + [{"role": role} for role in sorted(report_roles)])
            doc.save(ignore_permissions=True)
        else:
            frappe.get_doc(values).insert(ignore_permissions=True)
    desired_keys = set(desired_permissions)
    stale = frappe.db.get_all("Custom DocPerm", filters={"role": ["like", "Letron Policy - %"]}, fields=["name", "parent", "role", "permlevel"])
    for item in stale:
        if (item.parent, item.role) not in desired_keys and item.permlevel == 0:
            frappe.delete_doc("Custom DocPerm", item.name, ignore_permissions=True, force=True)
    frappe.clear_cache()
    return {"ok": True, "version": version, "sha256": sha256, "roles": sorted(roles), "rules": len(desired_permissions)}
