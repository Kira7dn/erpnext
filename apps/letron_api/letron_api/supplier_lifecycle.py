"""Keep the single Supplier Portal process linked to native purchase documents."""

from __future__ import annotations

from typing import Any

import frappe

from letron_api.supplier_portal import _text


def _accesses_for_po(po_name: str) -> list[str]:
    return frappe.get_all("Supplier Portal Access", filters={"purchase_order": po_name}, pluck="name")


def _accesses_for_supplier(supplier: str) -> list[str]:
    return frappe.get_all("Supplier Portal Access", filters={"supplier": supplier}, pluck="name")


def on_purchase_order_submit(doc: Any, method: str | None = None) -> None:
    quotation_names = {item.supplier_quotation for item in doc.items if _text(getattr(item, "supplier_quotation", ""))}
    names = set(_accesses_for_po(doc.name))
    for quotation in quotation_names:
        names.update(frappe.get_all("Supplier Portal Access", filters={"supplier_quotation": quotation}, pluck="name"))
    processes: set[str] = set()
    for name in names:
        access = frappe.get_doc("Supplier Portal Access", name)
        if access.supplier == doc.supplier:
            access.purchase_order = doc.name
            access.save(ignore_permissions=True)
            if _text(access.procurement_process):
                processes.add(_text(access.procurement_process))
    for process_name in processes:
        process = frappe.get_doc("Supplier Procurement Process", process_name)
        if process.approval_status in {"Opening", "Opened"}:
            process.approval_status = "Approved"
            process.purchase_order = doc.name
            process.purchase_order_status = "Submitted"
            process.save(ignore_permissions=True)


def on_purchase_receipt_submit(doc: Any, method: str | None = None) -> None:
    for item in doc.items:
        po_name = _text(getattr(item, "purchase_order", ""))
        if not po_name:
            continue
        for name in _accesses_for_po(po_name):
            access = frappe.get_doc("Supplier Portal Access", name)
            access.purchase_receipt = doc.name
            access.save(ignore_permissions=True)


def on_purchase_invoice_submit(doc: Any, method: str | None = None) -> None:
    po_names = {_text(getattr(item, "purchase_order", "")) for item in doc.items}
    for po_name in po_names - {""}:
        for name in _accesses_for_po(po_name):
            access = frappe.get_doc("Supplier Portal Access", name)
            access.purchase_invoice = doc.name
            access.save(ignore_permissions=True)
