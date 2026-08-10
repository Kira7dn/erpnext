"""Non-business health and runtime endpoints for the Letron ERPNext app."""

from __future__ import annotations

import frappe


def _runtime_info() -> dict[str, object]:
    installed_apps = frappe.get_installed_apps()
    return {
        "site": frappe.local.site,
        "frappe_version": getattr(frappe, "__version__", None),
        "installed_apps": installed_apps,
    }


@frappe.whitelist(allow_guest=True)
def health() -> dict[str, object]:
    """Return a lightweight authenticated application health response."""

    return {"ok": True, "app": "letron_api", **_runtime_info()}


@frappe.whitelist()
def runtime_info() -> dict[str, object]:
    """Return runtime metadata used by Phase 1 verification tooling."""

    return _runtime_info()


@frappe.whitelist()
def runtime_snapshot() -> dict[str, object]:
    """Return runtime metadata used by integration verification, not business logic."""

    snapshot: dict[str, object] = {**_runtime_info(), "doctype_metadata": {}}
    for doctype in ("Company", "Currency", "User"):
        try:
            meta = frappe.get_meta(doctype)
            snapshot["doctype_metadata"][doctype] = {
                "fields": [
                    {"fieldname": field.fieldname, "fieldtype": field.fieldtype, "reqd": field.reqd}
                    for field in meta.fields
                ],
                "permissions": [
                    {"role": permission.role, "read": permission.read, "write": permission.write, "create": permission.create}
                    for permission in meta.permissions
                ],
                "has_permission": frappe.has_permission(doctype, ptype="read"),
            }
        except Exception as error:  # noqa: BLE001 - snapshot must report metadata errors without masking runtime state
            snapshot["doctype_metadata"][doctype] = {"error": type(error).__name__}
    return snapshot


@frappe.whitelist(methods=["POST"])
def document_action(doctype: str, name: str, action: str) -> dict[str, object]:
    """Run an explicitly supported document lifecycle action.

    The route hook supplies the DocType and name from the clean module URL.
    Document methods enforce the normal Frappe permission and validation rules.
    """
    if (doctype, action) not in {("Sales Invoice", "submit"), ("Sales Invoice", "cancel")}:
        frappe.throw(f"Unsupported document action: {action}")
    document = frappe.get_doc(doctype, name)
    if action == "submit":
        document.submit()
    else:
        document.cancel()
    return document.as_dict()
