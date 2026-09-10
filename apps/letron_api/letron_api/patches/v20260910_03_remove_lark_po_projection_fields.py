"""Remove fields that only supported the deleted Lark PO projection."""

from __future__ import annotations

import frappe


def execute() -> None:
    for fieldname in (
        "custom_lark_draft_id",
        "custom_lark_approval_attempt",
        "custom_lark_payload_hash",
    ):
        name = frappe.db.get_value("Custom Field", {"dt": "Purchase Order", "fieldname": fieldname})
        if name:
            frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
    frappe.db.commit()
