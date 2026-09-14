from __future__ import annotations

import frappe


@frappe.whitelist(allow_guest=True)
def publish() -> None:
    """Compatibility denial: Auth Portal is the authorization SSOT."""
    frappe.throw(
        "ERP policy projection is disabled; Auth Portal is the authorization SSOT",
        exc=frappe.PermissionError,
    )
