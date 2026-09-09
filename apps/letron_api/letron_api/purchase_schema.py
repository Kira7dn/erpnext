"""ERPNext schema helpers for the Purchase MR -> RFQ orchestration.

The orchestration itself remains an internal BFF concern.  These fields make
the correlation durable on the two official business documents so a lost
response can be reconciled without inventing another public business API.
"""

from __future__ import annotations

import frappe


CORRELATION_FIELD = "custom_letron_orchestration_id"


def ensure_schema() -> None:
    """Install the non-user-facing correlation fields idempotently."""

    for doctype, insert_after in (
        ("Material Request", "title"),
        ("Request for Quotation", "subject"),
    ):
        if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": CORRELATION_FIELD}):
            continue
        field = frappe.get_doc(
            {
                "doctype": "Custom Field",
                "dt": doctype,
                "fieldname": CORRELATION_FIELD,
                "label": "Letron Orchestration ID",
                "fieldtype": "Data",
                "insert_after": insert_after,
                "hidden": 1,
                "read_only": 1,
                "no_copy": 1,
                "description": "Internal correlation key for the MR to RFQ action.",
            }
        )
        field.insert(ignore_permissions=True)
    for fieldname, fieldtype in (
        ("custom_lark_draft_id", "Data"),
        ("custom_lark_approval_instance_code", "Data"),
        ("custom_lark_approval_attempt", "Int"),
        ("custom_lark_payload_hash", "Data"),
    ):
        if frappe.db.exists(
            "Custom Field", {"dt": "Purchase Order", "fieldname": fieldname}
        ):
            continue
        field = frappe.get_doc(
            {
                "doctype": "Custom Field",
                "dt": "Purchase Order",
                "fieldname": fieldname,
                "label": fieldname.removeprefix("custom_").replace("_", " ").title(),
                "fieldtype": fieldtype,
                "insert_after": "supplier",
                "hidden": 1,
                "read_only": 1,
                "no_copy": 1,
                "unique": 1 if fieldname == "custom_lark_approval_instance_code" else 0,
                "description": "Immutable metadata from the approved Lark PO handoff.",
            }
        )
        field.insert(ignore_permissions=True)
    frappe.db.commit()


def schema_status() -> dict[str, bool]:
    """Return a non-sensitive runtime readback for migration verification."""

    status = {
        doctype: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": doctype, "fieldname": CORRELATION_FIELD},
            )
        )
        for doctype in ("Material Request", "Request for Quotation")
    }
    status["Purchase Order"] = all(
        frappe.db.exists(
            "Custom Field", {"dt": "Purchase Order", "fieldname": fieldname}
        )
        for fieldname in (
            "custom_lark_draft_id",
            "custom_lark_approval_instance_code",
            "custom_lark_approval_attempt",
            "custom_lark_payload_hash",
        )
    )
    return status
