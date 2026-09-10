"""ERPNext schema helpers for the Purchase MR -> RFQ orchestration.

The orchestration itself remains an internal BFF concern.  These fields make
the correlation durable on the two official business documents so a lost
response can be reconciled without inventing another public business API.
"""

from __future__ import annotations

import frappe

CORRELATION_FIELD = "custom_letron_orchestration_id"
CASE_FIELD = "custom_letron_case_id"


def _custom_field(doctype: str, fieldname: str, fieldtype: str, insert_after: str, *, unique: int = 0, description: str = "", options: str = "") -> None:
    if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname}):
        return
    field = frappe.get_doc(
        {
            "doctype": "Custom Field",
            "dt": doctype,
            "fieldname": fieldname,
            "label": fieldname.removeprefix("custom_").replace("_", " ").title(),
            "fieldtype": fieldtype,
            "options": options,
            "insert_after": insert_after,
            "hidden": 1,
            "read_only": 1,
            "no_copy": 1,
            "unique": unique,
            "description": description or "Letron SSOT correlation metadata.",
        }
    )
    field.insert(ignore_permissions=True)


def ensure_schema() -> None:
    """Install the non-user-facing correlation fields idempotently."""

    for doctype, insert_after in (
        ("Material Request", "title"),
        ("Request for Quotation", "subject"),
    ):
        _custom_field(
            doctype,
            CORRELATION_FIELD,
            "Data",
            insert_after,
            unique=1,
            description="Internal correlation key for the MR to RFQ action.",
        )
        _custom_field(doctype, CASE_FIELD, "Data", insert_after)

    for doctype, insert_after in (
        ("Supplier Quotation", "supplier"),
        ("Purchase Order", "supplier"),
        ("Purchase Receipt", "supplier"),
        ("Purchase Invoice", "supplier"),
    ):
        _custom_field(doctype, CASE_FIELD, "Data", insert_after)

    for doctype, insert_after in (
        ("Purchase Order", "supplier"),
        ("Supplier Quotation", "supplier"),
        ("Purchase Receipt", "supplier"),
        ("Purchase Invoice", "supplier"),
    ):
        _custom_field(doctype, CORRELATION_FIELD, "Data", insert_after)

    for fieldname, fieldtype in (("custom_lark_approval_instance_code", "Data"),):
        _custom_field(
            "Purchase Order",
            fieldname,
            fieldtype,
            "supplier",
            unique=1,
            description="Lark approval instance linked to the native ERPNext Purchase Order.",
        )
    _custom_field(
        "Purchase Order",
        "custom_lark_approval_status",
        "Select",
        "supplier",
        options="Draft\nPending Approval\nApproved\nRejected\nERP Failed\nERP Submitted",
    )
    _custom_field("Purchase Order", "custom_lark_error", "Small Text", "supplier")
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
            "custom_lark_approval_instance_code",
            CASE_FIELD,
            "custom_lark_approval_status",
        )
    )
    return status
