"""Typed Accounts reconciliation actions backed by native ERPNext controllers."""

from __future__ import annotations

from typing import Any

import frappe


def _payload_value(name: str, default: Any = None) -> Any:
    value = frappe.form_dict.get(name)
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return frappe.parse_json(value)
        except (TypeError, ValueError):
            return value
    return value


def _assert_permission(doctype: str, name: str, ptype: str = "write") -> Any:
    document = frappe.get_doc(doctype, name)
    document.check_permission(ptype)
    return document


def _readback(document: Any) -> dict[str, Any]:
    document.reload()
    return document.as_dict(no_nulls=True)


@frappe.whitelist(methods=["POST"])
def reconcile_bank_transaction(name: str, allocations: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Allocate a submitted Bank Transaction through ERPNext's native controller."""

    try:
        document = _assert_permission("Bank Transaction", name)
        if document.docstatus == 2:
            frappe.throw("A cancelled Bank Transaction cannot be reconciled", exc=frappe.ValidationError)
        rows = allocations if allocations is not None else _payload_value("allocations", [])
        if not isinstance(rows, list) or not rows:
            frappe.throw("allocations must be a non-empty list", exc=frappe.ValidationError)
        if document.docstatus == 1 and document.payment_entries:
            frappe.throw("Bank Transaction is already reconciled or has allocations", exc=frappe.ValidationError)

        vouchers = []
        for row in rows:
            if not isinstance(row, dict):
                frappe.throw("Each allocation must be an object", exc=frappe.ValidationError)
            payment_document = row.get("payment_document") or row.get("voucher_type")
            payment_entry = row.get("payment_entry") or row.get("voucher_name")
            if not isinstance(payment_document, str) or not isinstance(payment_entry, str):
                frappe.throw("Allocation requires payment_document and payment_entry", exc=frappe.ValidationError)
            if not frappe.db.exists(payment_document, payment_entry):
                frappe.throw(f"Missing allocation voucher: {payment_document}/{payment_entry}", exc=frappe.DoesNotExistError)
            vouchers.append({"payment_doctype": payment_document, "payment_name": payment_entry})

        document.add_payment_entries(vouchers)
        if document.docstatus == 0:
            document.submit()
        else:
            document.save()
        return _readback(document)
    except Exception:
        frappe.db.rollback()
        raise


@frappe.whitelist(methods=["POST"])
def unreconcile_bank_transaction(name: str, **kwargs: Any) -> dict[str, Any]:
    """Remove all Bank Transaction allocations through ERPNext's native helper."""

    try:
        document = _assert_permission("Bank Transaction", name)
        if document.docstatus != 1:
            frappe.throw("Only a submitted Bank Transaction can be unreconciled", exc=frappe.ValidationError)
        from erpnext.accounts.doctype.bank_transaction.bank_transaction import (
            unreconcile_transaction,
        )

        unreconcile_transaction(name)
        return _readback(document)
    except Exception:
        frappe.db.rollback()
        raise
