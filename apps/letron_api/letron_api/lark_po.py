"""ERPNext SSOT handoff for the Lark PO approval workflow."""

from __future__ import annotations

import json
import re
from typing import Any

import frappe

LARK_FIELDS = (
    "custom_letron_case_id",
    "custom_letron_orchestration_id",
    "custom_lark_draft_id",
    "custom_lark_approval_instance_code",
    "custom_lark_approval_attempt",
    "custom_lark_payload_hash",
    "custom_lark_approval_status",
    "custom_lark_error",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _authorized(path: str) -> None:
    from letron_api.gateway import verify_control_plane_request

    verify_control_plane_request(path)


def _number(value: Any, field: str, *, positive: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        frappe.throw(f"{field} must be numeric", exc=frappe.ValidationError)
    if result < 0 or (positive and result <= 0):
        frappe.throw(f"{field} must be positive", exc=frappe.ValidationError)
    return result


def _require_source(doctype: str, name: str, label: str) -> None:
    if not name or not frappe.db.exists(doctype, name):
        frappe.throw(f"{label} does not exist", exc=frappe.ValidationError)


def _require_child(doctype: str, name: str, parent: str, label: str) -> None:
    if not name or not frappe.db.exists(doctype, {"name": name, "parent": parent}):
        frappe.throw(f"{label} does not belong to {parent}", exc=frappe.ValidationError)


def _validate_payload(payload: Any, *, require_instance: bool = True) -> tuple[str, str, int, dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        frappe.throw("Approved Lark PO payload must be an object", exc=frappe.ValidationError)
    instance = _text(payload.get("approval_instance_code"))
    snapshot_hash = _text(payload.get("snapshot_hash"))
    attempt = payload.get("attempt")
    draft = payload.get("draft")
    raw_items = payload.get("items")
    if (
        (require_instance and not instance)
        or not re.fullmatch(r"[0-9a-f]{64}", snapshot_hash)
        or not isinstance(attempt, int)
        or attempt <= 0
        or not isinstance(draft, dict)
        or not isinstance(raw_items, list)
        or not raw_items
    ):
        frappe.throw("Approved Lark PO payload is incomplete", exc=frappe.ValidationError)
    items: list[dict[str, Any]] = []
    material_request = _text(draft.get("material_request_name"))
    rfq = _text(draft.get("request_for_quotation_name"))
    quotation = _text(draft.get("supplier_quotation_name"))
    _require_source("Material Request", material_request, "Material Request")
    if rfq:
        _require_source("Request for Quotation", rfq, "Request for Quotation")
        # The current Lark Base schema stores the canonical RFQ in
        # request_for_quotation_name; rfq_number is an approval-form alias.
        if _text(draft.get("rfq_number") or rfq) != rfq:
            frappe.throw("Approved Lark PO RFQ number mismatch", exc=frappe.ValidationError)
    if quotation:
        _require_source("Supplier Quotation", quotation, "Supplier Quotation")
        quotation_doc = frappe.get_doc("Supplier Quotation", quotation)
        if quotation_doc.docstatus != 1:
            frappe.throw("Selected Supplier Quotation must be submitted", exc=frappe.ValidationError)
        if _text(draft.get("quotation_status") or "Submitted") != "Submitted":
            frappe.throw("Approved Lark PO quotation status must be Submitted", exc=frappe.ValidationError)
        if _text(quotation_doc.supplier) != _text(draft.get("supplier")):
            frappe.throw("Selected Supplier Quotation supplier mismatch", exc=frappe.ValidationError)
        quotation_rfq = _text(getattr(quotation_doc, "request_for_quotation", ""))
        if quotation_rfq and quotation_rfq != rfq:
            frappe.throw("Selected Supplier Quotation RFQ mismatch", exc=frappe.ValidationError)
        if not quotation_rfq and not any(_text(getattr(item, "request_for_quotation", "")) == rfq for item in quotation_doc.items):
            frappe.throw("Selected Supplier Quotation is not linked to the RFQ", exc=frappe.ValidationError)
    for raw in raw_items:
        if not isinstance(raw, dict):
            frappe.throw("Approved Lark PO item is invalid", exc=frappe.ValidationError)
        item_code = _text(raw.get("item_code"))
        material_request_item = _text(raw.get("material_request_item"))
        rfq_item = _text(raw.get("request_for_quotation_item"))
        sq_item = _text(raw.get("supplier_quotation_item"))
        if not item_code:
            frappe.throw("Approved Lark PO item_code is required", exc=frappe.ValidationError)
        _number(raw.get("qty"), "qty", positive=True)
        _number(raw.get("rate"), "rate")
        _require_child("Material Request Item", material_request_item, material_request, "Material Request Item")
        if rfq:
            _require_child("Request for Quotation Item", rfq_item, rfq, "Request for Quotation Item")
        if quotation:
            _require_child("Supplier Quotation Item", sq_item, quotation, "Supplier Quotation Item")
        if _text(raw.get("material_request")) != material_request:
            frappe.throw("Material Request item link mismatch", exc=frappe.ValidationError)
        if rfq and _text(raw.get("request_for_quotation")) != rfq:
            frappe.throw("Request for Quotation item link mismatch", exc=frappe.ValidationError)
        if quotation and _text(raw.get("supplier_quotation")) != quotation:
            frappe.throw("Supplier Quotation item link mismatch", exc=frappe.ValidationError)
        items.append(raw)
    return instance, snapshot_hash, attempt, draft, items


def _case_metadata(draft: dict[str, Any]) -> tuple[str, str]:
    material_request = _text(draft.get("material_request_name"))
    process = frappe.db.get_value(
        "Supplier Procurement Process",
        {"material_request": material_request},
        ["name", "case_id", "orchestration_id"],
        as_dict=True,
    )
    if not process:
        frappe.throw("Supplier procurement process does not exist", exc=frappe.ValidationError)
    if _text(process.orchestration_id) != _text(draft.get("orchestration_id")):
        frappe.throw("Purchase Order orchestration mismatch", exc=frappe.ValidationError)
    return _text(process.name), _text(process.case_id)


def _purchase_order_doc(draft: dict[str, Any], items: list[dict[str, Any]], *, snapshot_hash: str, attempt: int, approval_instance: str = "") -> Any:
    _, case_id = _case_metadata(draft)
    po = frappe.get_doc({
        "doctype": "Purchase Order",
        "naming_series": "PO-.YYYYMMDD.-.####",
        "supplier": _text(draft.get("supplier")),
        "company": _text(draft.get("company")),
        "transaction_date": _text(draft.get("transaction_date")),
        "schedule_date": _text(draft.get("schedule_date")),
        "currency": _text(draft.get("currency")),
        "conversion_rate": _number(draft.get("conversion_rate"), "conversion_rate", positive=True),
        "custom_letron_case_id": case_id,
        "custom_letron_orchestration_id": _text(draft.get("orchestration_id")),
        "custom_lark_draft_id": _text(draft.get("draft_id")),
        # This field has a unique index. NULL is required for multiple PO
        # drafts that have not received a Lark approval instance yet; an empty
        # string would collide on the second draft in MariaDB.
        "custom_lark_approval_instance_code": approval_instance or None,
        "custom_lark_approval_attempt": attempt,
        "custom_lark_payload_hash": snapshot_hash,
        "custom_lark_approval_status": "Pending Approval" if not approval_instance else "Approved",
        "custom_lark_error": "",
        "items": [
            {
                "item_code": _text(item.get("item_code")),
                "qty": _number(item.get("qty"), "qty", positive=True),
                "uom": _text(item.get("uom")) or None,
                "schedule_date": _text(item.get("schedule_date")) or _text(draft.get("schedule_date")),
                "warehouse": _text(item.get("warehouse")) or None,
                "rate": _number(item.get("rate"), "rate"),
                "material_request": _text(item.get("material_request")) or _text(draft.get("material_request_name")),
                "material_request_item": _text(item.get("material_request_item")) or None,
                "request_for_quotation": _text(item.get("request_for_quotation")) or _text(draft.get("request_for_quotation_name")) or None,
                "request_for_quotation_item": _text(item.get("request_for_quotation_item")) or None,
                "supplier_quotation": _text(item.get("supplier_quotation")) or _text(draft.get("supplier_quotation_name")) or None,
                "supplier_quotation_item": _text(item.get("supplier_quotation_item")) or None,
            }
            for item in items
        ],
    })
    if not po.supplier or not po.company or not po.transaction_date or not po.schedule_date or not po.currency:
        frappe.throw("Purchase Order header is incomplete", exc=frappe.ValidationError)
    return po


def _link_process_and_access(po_name: str, draft: dict[str, Any], *, status: str) -> None:
    material_request = _text(draft.get("material_request_name"))
    process_name = frappe.db.get_value("Supplier Procurement Process", {"material_request": material_request}, "name")
    if not process_name:
        return
    process = frappe.get_doc("Supplier Procurement Process", process_name)
    process.purchase_order = po_name
    process.purchase_order_status = status
    if status == "Rejected":
        process.approval_status = "Rejected"
    elif status == "Submitted":
        process.approval_status = "Approved"
    process.save(ignore_permissions=True)
    for access_name in frappe.get_all(
        "Supplier Portal Access",
        filters={"procurement_process": process.name, "supplier": _text(draft.get("supplier"))},
        pluck="name",
    ):
        frappe.db.set_value("Supplier Portal Access", access_name, "purchase_order", po_name, update_modified=False)


def _json_payload() -> dict[str, Any]:
    try:
        payload = json.loads(frappe.local.request.get_data(as_text=True))
    except (TypeError, json.JSONDecodeError):
        frappe.throw("Invalid Lark PO JSON", exc=frappe.ValidationError)
    if not isinstance(payload, dict):
        frappe.throw("Lark PO payload must be an object", exc=frappe.ValidationError)
    return payload


@frappe.whitelist(allow_guest=True, methods=["POST"])
def create_draft() -> dict[str, Any]:
    """Create the one real ERPNext PO Draft before the Lark approval exists."""
    path = "/api/method/letron_api.lark_po.create_draft"
    _authorized(path)
    payload = _json_payload()
    _, snapshot_hash, attempt, draft, items = _validate_payload(payload, require_instance=False)
    if not all(frappe.db.has_column("Purchase Order", field) for field in LARK_FIELDS):
        frappe.throw("Lark PO metadata fields are not migrated", exc=frappe.ValidationError)
    orchestration_id = _text(draft.get("orchestration_id"))
    if not orchestration_id:
        frappe.throw("Purchase Order orchestration is required", exc=frappe.ValidationError)
    with frappe.cache().lock(f"letron:lark-po-draft:{orchestration_id}", timeout=60, blocking_timeout=30):
        existing = frappe.db.get_value("Purchase Order", {"custom_letron_orchestration_id": orchestration_id}, ["name", "docstatus", "custom_lark_payload_hash", "custom_lark_approval_attempt"], as_dict=True)
        if existing:
            if _text(existing.custom_lark_payload_hash) != snapshot_hash or int(existing.custom_lark_approval_attempt or 0) != attempt:
                frappe.throw("Purchase Order draft replay has a different snapshot", exc=frappe.ValidationError)
            if int(existing.docstatus or 0) != 0:
                frappe.throw("Purchase Order is no longer a draft", exc=frappe.ValidationError)
            return {"name": existing.name, "status": "Draft", "idempotent": True}
        from letron_api.supplier_portal import _internal_execution
        po = _purchase_order_doc(draft, items, snapshot_hash=snapshot_hash, attempt=attempt)
        with _internal_execution():
            po.insert(ignore_permissions=True)
        _link_process_and_access(po.name, draft, status="Pending Approval")
        return {"name": po.name, "status": "Draft", "idempotent": False}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def from_approved() -> dict[str, Any]:
    """Submit the already-created ERPNext PO Draft after Lark approval."""
    path = "/api/method/letron_api.lark_po.from_approved"
    _authorized(path)
    payload = _json_payload()
    instance, snapshot_hash, attempt, draft, _items = _validate_payload(payload)
    if not all(frappe.db.has_column("Purchase Order", field) for field in LARK_FIELDS):
        frappe.throw("Lark PO metadata fields are not migrated", exc=frappe.ValidationError)
    po_name = _text(draft.get("erp_purchase_order_name"))
    if not po_name:
        frappe.throw("Approved payload must contain the ERPNext Purchase Order name", exc=frappe.ValidationError)
    with frappe.cache().lock(f"letron:lark-po:{instance}", timeout=60, blocking_timeout=30):
        existing = frappe.db.get_value("Purchase Order", {"custom_lark_approval_instance_code": instance}, ["name", "custom_lark_payload_hash", "custom_lark_approval_attempt"], as_dict=True)
        if existing:
            if _text(existing.custom_lark_payload_hash) != snapshot_hash or int(existing.custom_lark_approval_attempt or 0) != attempt:
                frappe.throw("Lark approval replay has a different snapshot", exc=frappe.ValidationError)
            return {"name": existing.name, "idempotent": True}
        po = frappe.get_doc("Purchase Order", po_name)
        if int(po.docstatus or 0) != 0:
            if _text(getattr(po, "custom_lark_approval_instance_code", "")) == instance:
                return {"name": po.name, "idempotent": True}
            frappe.throw("ERPNext Purchase Order is not a draft", exc=frappe.ValidationError)
        if _text(po.custom_letron_orchestration_id) != _text(draft.get("orchestration_id")):
            frappe.throw("ERPNext Purchase Order correlation mismatch", exc=frappe.ValidationError)
        if _text(po.custom_lark_payload_hash) != snapshot_hash or int(po.custom_lark_approval_attempt or 0) != attempt:
            frappe.throw("ERPNext Purchase Order snapshot mismatch", exc=frappe.ValidationError)
        if _text(po.supplier) != _text(draft.get("supplier")) or _text(po.company) != _text(draft.get("company")):
            frappe.throw("ERPNext Purchase Order source mismatch", exc=frappe.ValidationError)
        po.custom_lark_approval_instance_code = instance
        po.custom_lark_approval_status = "Approved"
        po.custom_lark_error = ""
        from letron_api.supplier_portal import _internal_execution
        with _internal_execution():
            po.save(ignore_permissions=True)
            po.submit()
        _link_process_and_access(po.name, draft, status="Submitted")
        return {"name": po.name, "idempotent": False}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def update_approval_state() -> dict[str, Any]:
    """Persist rejection/failure on the same native PO Draft for audit/retry."""
    path = "/api/method/letron_api.lark_po.update_approval_state"
    _authorized(path)
    payload = _json_payload()
    po_name = _text(payload.get("erp_purchase_order_name"))
    status = _text(payload.get("status"))
    material_request_name = _text(payload.get("material_request_name"))
    orchestration_id = _text(payload.get("orchestration_id"))
    if status not in {"Rejected", "ERP Failed"} or not po_name or not material_request_name or not orchestration_id:
        frappe.throw("ERP Purchase Order, Material Request, orchestration and status are required", exc=frappe.ValidationError)
    po = frappe.get_doc("Purchase Order", po_name)
    if int(po.docstatus or 0) != 0:
        frappe.throw("Only a Purchase Order Draft can be marked for retry", exc=frappe.ValidationError)
    if _text(getattr(po, "custom_letron_orchestration_id", "")) != orchestration_id:
        frappe.throw("ERP Purchase Order correlation mismatch", exc=frappe.ValidationError)
    po.custom_lark_approval_status = status
    po.custom_lark_error = _text(payload.get("error"))[:500]
    po.save(ignore_permissions=True)
    _link_process_and_access(po.name, {"material_request_name": material_request_name, "orchestration_id": orchestration_id}, status=status)
    return {"name": po.name, "status": status, "idempotent": True}
