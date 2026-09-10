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

    for fieldname, fieldtype in (
        ("custom_lark_draft_id", "Data"),
        ("custom_lark_approval_instance_code", "Data"),
        ("custom_lark_approval_attempt", "Int"),
        ("custom_lark_payload_hash", "Data"),
    ):
        _custom_field(
            "Purchase Order",
            fieldname,
            fieldtype,
            "supplier",
            unique=1 if fieldname == "custom_lark_approval_instance_code" else 0,
            description="Immutable metadata from the approved Lark PO handoff.",
        )
    _custom_field(
        "Purchase Order",
        "custom_lark_approval_status",
        "Select",
        "supplier",
        options="Draft\nPending Approval\nApproved\nRejected\nERP Failed\nERP Submitted",
    )
    _custom_field("Purchase Order", "custom_lark_error", "Small Text", "supplier")
    _ensure_supplier_portal_indexes()
    frappe.db.commit()


def _ensure_supplier_portal_indexes() -> None:
    """Backfill deterministic keys and create lookup/uniqueness indexes."""
    if frappe.db.has_column("Supplier Portal Access", "access_key"):
        duplicates = frappe.db.sql(
            """SELECT procurement_process, supplier, COUNT(*) AS total
               FROM `tabSupplier Portal Access`
              GROUP BY procurement_process, supplier HAVING COUNT(*) > 1""",
            as_dict=True,
        )
        if duplicates:
            frappe.throw("Duplicate Supplier Portal Access rows exist; resolve them before migration", exc=frappe.ValidationError)
        frappe.db.sql("UPDATE `tabSupplier Portal Access` SET access_key=CONCAT(procurement_process, ':', supplier) WHERE IFNULL(access_key, '')='' ")
    if frappe.db.has_column("Supplier Portal Submission", "submission_key"):
        duplicates = frappe.db.sql(
            """SELECT access, submission_type, idempotency_key, COUNT(*) AS total
               FROM `tabSupplier Portal Submission`
              GROUP BY access, submission_type, idempotency_key HAVING COUNT(*) > 1""",
            as_dict=True,
        )
        if duplicates:
            frappe.throw("Duplicate Supplier Portal Submission rows exist; resolve them before migration", exc=frappe.ValidationError)
        frappe.db.sql("UPDATE `tabSupplier Portal Submission` SET submission_key=CONCAT(access, ':', submission_type, ':', idempotency_key) WHERE IFNULL(submission_key, '')='' ")
    index_specs = (
        ("tabSupplier Portal Access", "idx_spa_session_hash", "session_hash"),
        ("tabSupplier Portal Access", "idx_spa_process_supplier", "procurement_process, supplier"),
        ("tabSupplier Portal Access", "idx_spa_quotation", "supplier_quotation"),
        ("tabSupplier Portal Access", "idx_spa_purchase_order", "purchase_order"),
        ("tabSupplier Portal Submission", "idx_sps_access_type", "access, submission_type"),
        ("tabSupplier Portal Submission", "idx_sps_purchase_order", "purchase_order"),
        ("tabSupplier Procurement Process", "idx_spp_status_deadline", "approval_status, deadline_at"),
    )
    for table, index_name, columns in index_specs:
        if not frappe.db.sql(f"SHOW INDEX FROM `{table}` WHERE Key_name=%s", index_name):
            frappe.db.sql_ddl(f"CREATE INDEX `{index_name}` ON `{table}` ({columns})")


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
            CASE_FIELD,
            "custom_lark_approval_status",
        )
    )
    return status
