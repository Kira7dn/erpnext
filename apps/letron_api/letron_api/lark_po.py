"""Trusted, idempotent handoff from Global Portal after Lark PO approval."""

from __future__ import annotations

import json
import re
from typing import Any

import frappe


LARK_FIELDS = (
    "custom_lark_draft_id",
    "custom_lark_approval_instance_code",
    "custom_lark_approval_attempt",
    "custom_lark_payload_hash",
)


def _authorized() -> None:
    from letron_api.gateway import verify_control_plane_request

    verify_control_plane_request("/api/method/letron_api.lark_po.from_approved")


def _text(value: Any) -> str:
    return str(value or "").strip()


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


def _validate_payload(payload: Any) -> tuple[str, str, int, dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        frappe.throw("Approved Lark PO payload must be an object", exc=frappe.ValidationError)
    instance = _text(payload.get("approval_instance_code"))
    snapshot_hash = _text(payload.get("snapshot_hash"))
    attempt = payload.get("attempt")
    draft = payload.get("draft")
    raw_items = payload.get("items")
    if (
        not instance
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
    if quotation:
        _require_source("Supplier Quotation", quotation, "Supplier Quotation")
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


@frappe.whitelist(allow_guest=True, methods=["POST"])
def from_approved() -> dict[str, Any]:
    _authorized()
    try:
        payload = json.loads(frappe.local.request.get_data(as_text=True))
    except (TypeError, json.JSONDecodeError):
        frappe.throw("Invalid approved Lark PO JSON", exc=frappe.ValidationError)
    instance, snapshot_hash, attempt, draft, items = _validate_payload(payload)
    if not all(frappe.db.has_column("Purchase Order", field) for field in LARK_FIELDS):
        frappe.throw("Lark PO metadata fields are not migrated", exc=frappe.ValidationError)

    existing = frappe.db.get_value(
        "Purchase Order",
        {"custom_lark_approval_instance_code": instance},
        ["name", "custom_lark_payload_hash", "custom_lark_approval_attempt"],
        as_dict=True,
    )
    if existing:
        if (
            _text(existing.custom_lark_payload_hash) != snapshot_hash
            or int(existing.custom_lark_approval_attempt or 0) != attempt
        ):
            frappe.throw("Lark approval replay has a different snapshot", exc=frappe.ValidationError)
        return {"name": existing.name, "idempotent": True}

    po = frappe.get_doc(
        {
            "doctype": "Purchase Order",
            "supplier": _text(draft.get("supplier")),
            "company": _text(draft.get("company")),
            "transaction_date": _text(draft.get("transaction_date")),
            "schedule_date": _text(draft.get("schedule_date")),
            "currency": _text(draft.get("currency")),
            "conversion_rate": _number(draft.get("conversion_rate"), "conversion_rate", positive=True),
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
            "custom_lark_draft_id": _text(draft.get("draft_id")),
            "custom_lark_approval_instance_code": instance,
            "custom_lark_approval_attempt": attempt,
            "custom_lark_payload_hash": snapshot_hash,
        }
    )
    if not po.supplier or not po.company or not po.transaction_date or not po.schedule_date or not po.currency:
        frappe.throw("Approved Lark PO header is incomplete", exc=frappe.ValidationError)
    po.insert(ignore_permissions=True)
    po.submit()
    return {"name": po.name, "idempotent": False}
