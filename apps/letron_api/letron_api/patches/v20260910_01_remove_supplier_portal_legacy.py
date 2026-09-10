"""Remove the retired Frappe-owned Supplier Portal model.

The portal state is now owned by Next.js/Redis. This patch intentionally drops
the old custom DocTypes and their tables after the deployment backup gate.
"""

from __future__ import annotations

import frappe


LEGACY_DOCTYPES = (
    "Supplier Portal Access",
    "Supplier Portal Submission",
    "Supplier Portal Mail Outbox",
    "Supplier Portal Audit Log",
    "Supplier Procurement Process",
)


def execute() -> None:
    for doctype in LEGACY_DOCTYPES:
        if frappe.db.exists("DocType", doctype):
            frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)
    frappe.clear_cache()
