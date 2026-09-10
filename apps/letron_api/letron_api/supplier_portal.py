"""Public Supplier Portal boundary: OTP, scoped access and quotation intake."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterator

import frappe
from frappe.utils.file_manager import save_file


def _text(value: Any) -> str:
    return str(value or "").strip()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _payload_hash(value: Any) -> str:
    return _hash(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str))


def _portal_config() -> dict[str, Any]:
    path = Path(os.environ.get("LETRON_CONFIG_DIR", "config")) / "supplier_portal.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _portal_secret() -> str:
    return _text(os.environ.get("LETRON_SUPPLIER_PORTAL_SECRET") or os.environ.get("LETRON_SSO_SYNC_SECRET"))


def _frappe_datetime(value: str) -> str:
    try:
        return frappe.utils.get_datetime(value).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OverflowError):
        frappe.throw("deadline_at must be a valid datetime", exc=frappe.ValidationError)


def _json() -> dict[str, Any]:
    try:
        value = json.loads(frappe.local.request.get_data(as_text=True) or "{}")
    except (TypeError, json.JSONDecodeError):
        frappe.throw("Invalid supplier portal JSON", exc=frappe.ValidationError)
    if not isinstance(value, dict):
        frappe.throw("Supplier portal payload must be an object", exc=frappe.ValidationError)
    return value


def _form() -> dict[str, Any]:
    """Read scalar fields from a multipart request without treating it as JSON."""
    form = getattr(frappe.local.request, "form", None)
    if form is None:
        frappe.throw("Invalid supplier portal form", exc=frappe.ValidationError)
    return {key: form.get(key) for key in form.keys()}


def _audit(action: str, access: Any | None = None, *, status: str = "Success", metadata: dict[str, Any] | None = None) -> None:
    try:
        frappe.get_doc({
            "doctype": "Supplier Portal Audit Log",
            "action": action,
            "status": status,
            "procurement_process": _text(getattr(access, "procurement_process", "")) or None,
            "access": _text(getattr(access, "name", "")) or None,
            "supplier": _text(getattr(access, "supplier", "")) or None,
            "metadata": json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Supplier Portal audit failure")


def _rate_limit(scope: str, value: str, seconds: int) -> None:
    cache = frappe.cache()
    key = f"letron:supplier-portal:rate:{scope}:{_hash(value)}"
    if cache.get_value(key, use_local_cache=False):
        frappe.throw("Supplier portal request is temporarily limited", exc=frappe.ValidationError)
    cache.set_value(key, "1", expires_in_sec=seconds)


@contextmanager
def _internal_execution() -> Iterator[str]:
    previous_user = frappe.session.user
    previous_ignore_permissions = frappe.flags.ignore_permissions
    user = _text(_portal_config().get("review_user")) or "Administrator"
    if not frappe.db.exists("User", user):
        frappe.throw("Supplier portal internal execution user is not configured", exc=frappe.ValidationError)
    frappe.set_user(user)
    frappe.flags.ignore_permissions = True
    try:
        yield user
    finally:
        frappe.flags.ignore_permissions = previous_ignore_permissions
        frappe.set_user(previous_user)


def _send_supplier_mail(email: str, subject: str, message: str) -> None:
    config = _portal_config()
    auth_base = _text(config.get("auth_base_url"))
    api_key = os.environ.get("LETRON_API_KEY", "")
    if not auth_base or not api_key:
        frappe.throw("Lark Mail provider is not configured", exc=frappe.ValidationError)
    body_html = "<p>" + message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>") + "</p>"
    request = urllib.request.Request(
        f"{auth_base.rstrip('/')}/api/internal/lark-mail/send",
        data=json.dumps({"to": email, "subject": subject, "body_html": body_html, "body_plain_text": message}).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError("provider rejected email")
    except (urllib.error.URLError, TimeoutError, RuntimeError) as error:
        frappe.throw(f"Lark Mail provider failed: {error}", exc=frappe.ValidationError)


def _authorized(method_name: str) -> None:
    headers = frappe.local.request.headers
    secret = _portal_secret()
    timestamp = headers.get("X-Letron-Supplier-Timestamp", "")
    expires = headers.get("X-Letron-Supplier-Expires-At", "")
    request_id = headers.get("X-Letron-Supplier-Request-Id", "")
    signature = headers.get("X-Letron-Supplier-Signature", "")
    path = f"/api/method/letron_api.supplier_portal.{method_name}"
    if not secret or not timestamp or not expires or not request_id or not signature:
        frappe.throw("Supplier portal authorization required", exc=frappe.AuthenticationError)
    try:
        issued = int(timestamp)
        expiry = int(expires)
    except ValueError:
        frappe.throw("Invalid supplier portal timestamp", exc=frappe.AuthenticationError)
    if abs(time.time() - issued) > 60 or expiry < time.time() or expiry <= issued:
        frappe.throw("Expired supplier portal authorization", exc=frappe.AuthenticationError)
    payload = f"{timestamp}.{expires}.POST.{path}.{request_id}"
    expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        frappe.throw("Invalid supplier portal authorization", exc=frappe.AuthenticationError)


def _access_by_token(token: str, *, session: bool = False) -> Any:
    field = "session_hash" if session else "magic_token_hash"
    access_name = frappe.db.get_value("Supplier Portal Access", {field: _hash(token)}, "name")
    if not access_name:
        frappe.throw("Supplier portal access is invalid", exc=frappe.PermissionError)
    access = frappe.get_doc("Supplier Portal Access", access_name)
    now = frappe.utils.now_datetime()
    if access.status in {"Revoked", "Expired"}:
        frappe.throw("Supplier portal access is no longer active", exc=frappe.PermissionError)
    if access.magic_expires_at and now > access.magic_expires_at:
        access.status = "Expired"
        access.save(ignore_permissions=True)
        frappe.throw("Supplier portal access has expired", exc=frappe.PermissionError)
    if session and (not access.session_expires_at or now > access.session_expires_at):
        frappe.throw("Supplier portal session has expired", exc=frappe.PermissionError)
    return access


def _lock_access(access: Any) -> Any:
    frappe.db.sql(
        "SELECT name FROM `tabSupplier Portal Access` WHERE name=%s FOR UPDATE",
        access.name,
    )
    return frappe.get_doc("Supplier Portal Access", access.name)


def _supplier_in_rfq(rfq: Any, supplier: str) -> bool:
    return any(_text(row.supplier) == supplier for row in (rfq.suppliers or []))


def _process_for(material_request: str, orchestration_id: str, deadline_at: str, supplier_count: int) -> Any:
    process_name = frappe.db.get_value("Supplier Procurement Process", {"material_request": material_request}, "name")
    if process_name:
        process = frappe.get_doc("Supplier Procurement Process", process_name)
        if _text(process.orchestration_id) != orchestration_id:
            frappe.throw("Material Request orchestration correlation mismatch", exc=frappe.ValidationError)
        if process.approval_status in {"Waiting", "Ready"}:
            process.deadline_at = deadline_at
            process.supplier_count = max(int(process.supplier_count or 0), supplier_count)
            process.save(ignore_permissions=True)
        return process
    process = frappe.get_doc({
        "doctype": "Supplier Procurement Process",
        "material_request": material_request,
        "orchestration_id": orchestration_id,
        "deadline_at": deadline_at,
        "supplier_count": supplier_count,
        "submitted_count": 0,
        "approval_status": "Waiting",
    })
    process.insert(ignore_permissions=True)
    return process


@frappe.whitelist(allow_guest=True, methods=["POST"])
def issue_access() -> dict[str, Any]:
    _authorized("issue_access")
    payload = _json()
    material_request = _text(payload.get("material_request"))
    rfq_name = _text(payload.get("request_for_quotation"))
    supplier = _text(payload.get("supplier"))
    email = _text(payload.get("email_snapshot")).lower()
    deadline_at = _text(payload.get("deadline_at"))
    orchestration_id = _text(payload.get("orchestration_id"))
    if not material_request or not rfq_name or not supplier or not orchestration_id:
        frappe.throw("material_request, request_for_quotation, supplier and orchestration_id are required", exc=frappe.ValidationError)
    if not frappe.db.exists("Material Request", material_request) or not frappe.db.exists("Request for Quotation", rfq_name):
        frappe.throw("Supplier portal source document does not exist", exc=frappe.ValidationError)
    rfq = frappe.get_doc("Request for Quotation", rfq_name)
    if not _supplier_in_rfq(rfq, supplier):
        frappe.throw("Supplier is not part of the RFQ", exc=frappe.ValidationError)
    if not any(_text(getattr(item, "material_request", "")) == material_request for item in (rfq.items or [])):
        frappe.throw("Request for Quotation is not linked to the Material Request", exc=frappe.ValidationError)
    if not email:
        contact = _text(payload.get("contact")) or _text(frappe.db.get_value("Supplier", supplier, "supplier_primary_contact"))
        if contact:
            email = _text(frappe.db.get_value("Contact Email", {"parent": contact, "is_primary": 1}, "email_id"))
            if not email:
                email = _text(frappe.db.get_value("Contact Email", {"parent": contact}, "email_id"))
    if not email:
        frappe.throw("Supplier email is required", exc=frappe.ValidationError)
    material_doc = frappe.get_doc("Material Request", material_request)
    actual_deadline = frappe.utils.add_to_date(material_doc.creation, days=3)
    process = _process_for(material_request, orchestration_id, str(actual_deadline), len(rfq.suppliers or []))
    existing_name = frappe.db.get_value("Supplier Portal Access", {"procurement_process": process.name, "supplier": supplier}, "name")
    if existing_name:
        access = frappe.get_doc("Supplier Portal Access", existing_name)
        return {"access_id": access.name, "idempotent": True}
    token = secrets.token_urlsafe(32)
    portal_base = _text(payload.get("portal_url_base")) or _text(payload.get("portal_url"))
    portal_url = f"{portal_base.rstrip('/')}/{token}" if portal_base else token
    access = frappe.get_doc({
        "doctype": "Supplier Portal Access",
        "procurement_process": process.name,
        "orchestration_id": process.orchestration_id,
        "supplier": supplier,
        "contact": _text(payload.get("contact")) or None,
        "email_snapshot": email,
        "request_for_quotation": rfq_name,
        "magic_token_hash": _hash(token),
        "magic_expires_at": frappe.utils.add_to_date(frappe.utils.now_datetime(), days=90),
        "status": "Issued",
    })
    access.insert(ignore_permissions=True)
    _send_supplier_mail(email, "Letron Supplier Portal access", f"Supplier portal access for RFQ {rfq_name}. Open this link and request an OTP: {portal_url}")
    _audit("Magic Link issued", access, metadata={"request_for_quotation": rfq_name})
    return {"access_id": access.name, "idempotent": False}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def request_otp() -> dict[str, Any]:
    _authorized("request_otp")
    payload = _json()
    access = _lock_access(_access_by_token(_text(payload.get("magic_token"))))
    now = frappe.utils.now_datetime()
    if access.otp_sent_at and (now - access.otp_sent_at).total_seconds() < 60:
        frappe.throw("OTP resend is temporarily limited", exc=frappe.ValidationError)
    remote_addr = _text(getattr(frappe.local.request, "remote_addr", "unknown"))
    _rate_limit("otp-ip", remote_addr, 60)
    _rate_limit("otp-email", _text(access.email_snapshot).lower(), 60)
    code = f"{secrets.randbelow(1_000_000):06d}"
    access.otp_hash = _hash(code)
    access.otp_expires_at = now + timedelta(minutes=5)
    access.otp_attempts = 0
    access.otp_sent_at = now
    access.status = "OtpSent"
    access.save(ignore_permissions=True)
    _send_supplier_mail(access.email_snapshot, "Letron Supplier Portal OTP", f"Your one-time Supplier Portal code is {code}. It expires in 5 minutes.")
    _audit("OTP issued", access)
    return {"status": "sent", "expires_in_seconds": 300}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def verify_otp() -> dict[str, Any]:
    _authorized("verify_otp")
    payload = _json()
    access = _lock_access(_access_by_token(_text(payload.get("magic_token"))))
    code = _text(payload.get("otp"))
    if not access.otp_hash or not access.otp_expires_at or frappe.utils.now_datetime() > access.otp_expires_at:
        frappe.throw("OTP is invalid or expired", exc=frappe.PermissionError)
    access.otp_attempts = int(access.otp_attempts or 0) + 1
    if access.otp_attempts > 5 or not hmac.compare_digest(access.otp_hash, _hash(code)):
        access.save(ignore_permissions=True)
        _audit("OTP rejected", access, status="Rejected")
        frappe.throw("OTP is invalid or expired", exc=frappe.PermissionError)
    session = secrets.token_urlsafe(32)
    access.session_hash = _hash(session)
    access.session_expires_at = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=2)
    access.status = "Active"
    access.last_used_at = frappe.utils.now_datetime()
    access.save(ignore_permissions=True)
    _audit("OTP verified", access)
    return {"session_token": session, "expires_in_seconds": 7200}


def _summary(access: Any) -> dict[str, Any]:
    frappe.db.sql(
        "SELECT name FROM `tabSupplier Procurement Process` WHERE name=%s FOR UPDATE",
        access.procurement_process,
    )
    process = frappe.get_doc("Supplier Procurement Process", access.procurement_process)
    rfq = frappe.get_doc("Request for Quotation", access.request_for_quotation)
    quotation = frappe.get_doc("Supplier Quotation", access.supplier_quotation) if access.supplier_quotation else None
    purchase_order = frappe.get_doc("Purchase Order", access.purchase_order) if access.purchase_order else None
    purchase_receipt = frappe.get_doc("Purchase Receipt", access.purchase_receipt) if access.purchase_receipt else None
    purchase_invoice = frappe.get_doc("Purchase Invoice", access.purchase_invoice) if access.purchase_invoice else None
    return {
        "process": process.name,
        "material_request": process.material_request,
        "supplier": access.supplier,
        "rfq": {
            "name": rfq.name,
            "status": _text(rfq.status),
            "transaction_date": _text(rfq.transaction_date),
            "items": [{"name": item.name, "item_code": item.item_code, "description": item.description, "qty": item.qty, "uom": item.uom, "warehouse": item.warehouse} for item in (rfq.items or [])],
        },
        "quotation": {"name": quotation.name, "status": "Submitted"} if quotation else None,
        "purchase_order": {
            "name": purchase_order.name,
            "status": "Submitted" if purchase_order.docstatus == 1 else "Draft",
            "transaction_date": _text(purchase_order.transaction_date),
            "schedule_date": _text(purchase_order.schedule_date),
            "currency": _text(purchase_order.currency),
            "items": [{
                "name": item.name,
                "item_code": item.item_code,
                "qty": item.qty,
                "uom": item.uom,
                "rate": item.rate,
                "amount": item.amount,
                "has_serial_no": frappe.db.get_value("Item", item.item_code, "has_serial_no"),
                "has_batch_no": frappe.db.get_value("Item", item.item_code, "has_batch_no"),
            } for item in (purchase_order.items or [])],
        } if purchase_order else None,
        "purchase_receipt": {"name": purchase_receipt.name, "status": "Submitted" if purchase_receipt.docstatus == 1 else "Draft"} if purchase_receipt else None,
        "purchase_invoice": {"name": purchase_invoice.name, "status": "Submitted" if purchase_invoice.docstatus == 1 else "Draft"} if purchase_invoice else None,
        "payment_status": "Paid" if purchase_invoice and purchase_invoice.outstanding_amount == 0 else ("Invoiced" if purchase_invoice else "Not Invoiced"),
        "submissions": {
            "delivery": _submission_rows(access, "Delivery Confirmation"),
            "xml_invoice": _submission_rows(access, "XML Invoice"),
        },
        "access_status": access.status,
        "approval_status": process.approval_status,
        "deadline_at": str(process.deadline_at or ""),
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
def get_process_summary() -> dict[str, Any]:
    _authorized("get_process_summary")
    access = _access_by_token(_text(_json().get("session_token")), session=True)
    return _summary(access)


def _idempotency(payload: dict[str, Any]) -> str:
    value = _text(payload.get("idempotency_key"))
    if not value or len(value) > 128:
        frappe.throw("idempotency_key is required", exc=frappe.ValidationError)
    return value


def _submission_rows(access: Any, submission_type: str) -> list[dict[str, Any]]:
    names = frappe.get_all("Supplier Portal Submission", filters={"access": access.name, "submission_type": submission_type}, pluck="name")
    return [
        {
            "name": submission.name,
            "submission_type": submission.submission_type,
            "purchase_order": submission.purchase_order,
            "status": submission.status,
            "file_name": submission.file_name,
            "reviewed_at": str(submission.reviewed_at or ""),
            "result_document": submission.result_document,
        }
        for name in names
        for submission in [frappe.get_doc("Supplier Portal Submission", name)]
    ]


@frappe.whitelist(allow_guest=True, methods=["POST"])
def get_purchase_order() -> dict[str, Any]:
    _authorized("get_purchase_order")
    access = _access_by_token(_text(_json().get("session_token")), session=True)
    if not access.purchase_order:
        frappe.throw("Purchase Order is not available", exc=frappe.ValidationError)
    return _summary(access)["purchase_order"]


@frappe.whitelist(allow_guest=True, methods=["POST"])
def get_payment_status() -> dict[str, Any]:
    _authorized("get_payment_status")
    access = _access_by_token(_text(_json().get("session_token")), session=True)
    summary = _summary(access)
    return {"purchase_invoice": summary["purchase_invoice"], "payment_status": summary["payment_status"]}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def create_delivery_confirmation() -> dict[str, Any]:
    _authorized("create_delivery_confirmation")
    payload = _json()
    access = _lock_access(_access_by_token(_text(payload.get("session_token")), session=True))
    if not access.purchase_order:
        frappe.throw("Purchase Order is not available", exc=frappe.ValidationError)
    key = _idempotency(payload)
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        frappe.throw("Delivery items are required", exc=frappe.ValidationError)
    po = frappe.get_doc("Purchase Order", access.purchase_order)
    po_items = {item.name: item for item in po.items or []}
    normalized = []
    for raw in items:
        if not isinstance(raw, dict) or _text(raw.get("purchase_order_item")) not in po_items:
            frappe.throw("Delivery item is not part of the Purchase Order", exc=frappe.ValidationError)
        qty = float(raw.get("delivered_qty") or 0)
        item_name = _text(raw.get("purchase_order_item"))
        ordered_qty = float(po_items[item_name].qty or 0)
        if qty < 0 or qty > ordered_qty:
            frappe.throw("Delivered quantity exceeds Purchase Order quantity", exc=frappe.ValidationError)
        submitted_uom = _text(raw.get("uom"))
        if submitted_uom and submitted_uom != _text(po_items[item_name].uom):
            frappe.throw("Delivery UOM does not match Purchase Order", exc=frappe.ValidationError)
        item_flags = frappe.db.get_value("Item", po_items[item_name].item_code, ["has_serial_no", "has_batch_no"], as_dict=True) or {}
        serial_no = _text(raw.get("serial_no"))
        batch_no = _text(raw.get("batch_no"))
        if item_flags.get("has_serial_no") and not serial_no:
            frappe.throw("Serial numbers are required for this item", exc=frappe.ValidationError)
        if item_flags.get("has_batch_no") and not batch_no:
            frappe.throw("Batch number is required for this item", exc=frappe.ValidationError)
        if serial_no and not item_flags.get("has_serial_no"):
            frappe.throw("Serial numbers are not allowed for this item", exc=frappe.ValidationError)
        if batch_no and not item_flags.get("has_batch_no"):
            frappe.throw("Batch number is not allowed for this item", exc=frappe.ValidationError)
        rejected_qty = float(raw.get("rejected_qty") or 0)
        if rejected_qty < 0 or rejected_qty > qty:
            frappe.throw("Rejected quantity must be between zero and delivered quantity", exc=frappe.ValidationError)
        normalized.append({
            "purchase_order_item": item_name,
            "delivered_qty": qty,
            "rejected_qty": rejected_qty,
            "uom": submitted_uom or _text(po_items[item_name].uom),
            "serial_no": serial_no,
            "batch_no": batch_no,
        })
    normalized_payload = {"delivery_date": _text(payload.get("delivery_date")), "items": normalized}
    payload_hash = _payload_hash(normalized_payload)
    existing = frappe.db.get_value("Supplier Portal Submission", {"access": access.name, "submission_type": "Delivery Confirmation", "idempotency_key": key}, ["name", "payload_hash"], as_dict=True)
    if existing:
        if existing.payload_hash and existing.payload_hash != payload_hash:
            frappe.throw("Idempotency key was used with a different payload", exc=frappe.ValidationError)
        return {"submission": existing.name, "idempotent": True}
    prior_delivered: dict[str, float] = {}
    prior_submissions = frappe.get_all(
        "Supplier Portal Submission",
        filters={"access": access.name, "submission_type": "Delivery Confirmation", "status": ["in", ["Pending", "Approved"]]},
        fields=["payload"],
    )
    for prior in prior_submissions:
        try:
            prior_payload = json.loads(prior.payload or "{}")
        except (TypeError, json.JSONDecodeError):
            prior_payload = {}
        for prior_item in prior_payload.get("items", []):
            prior_name = _text(prior_item.get("purchase_order_item")) if isinstance(prior_item, dict) else ""
            if prior_name:
                prior_delivered[prior_name] = prior_delivered.get(prior_name, 0) + float(prior_item.get("delivered_qty") or 0)
    for row in normalized:
        if prior_delivered.get(row["purchase_order_item"], 0) + row["delivered_qty"] > float(po_items[row["purchase_order_item"]].qty or 0):
            frappe.throw("Delivered quantity exceeds remaining Purchase Order quantity", exc=frappe.ValidationError)
    if not any(row["delivered_qty"] > 0 for row in normalized):
        frappe.throw("At least one delivered quantity is required", exc=frappe.ValidationError)
    submission = frappe.get_doc({"doctype": "Supplier Portal Submission", "procurement_process": access.procurement_process, "access": access.name, "supplier": access.supplier, "submission_type": "Delivery Confirmation", "purchase_order": po.name, "status": "Pending", "payload": json.dumps(normalized_payload), "payload_hash": payload_hash, "idempotency_key": key})
    submission.insert(ignore_permissions=True)
    _audit("Delivery submitted", access, metadata={"submission": submission.name})
    return {"submission": submission.name, "status": submission.status, "idempotent": False}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def get_submissions() -> dict[str, Any]:
    _authorized("get_submissions")
    access = _access_by_token(_text(_json().get("session_token")), session=True)
    return {"delivery": _submission_rows(access, "Delivery Confirmation"), "xml_invoice": _submission_rows(access, "XML Invoice")}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def upload_xml_invoice() -> dict[str, Any]:
    _authorized("upload_xml_invoice")
    payload = _form()
    access = _lock_access(_access_by_token(_text(payload.get("session_token")), session=True))
    if not access.purchase_order:
        frappe.throw("Purchase Order is not available", exc=frappe.ValidationError)
    key = _idempotency(payload)
    uploaded = frappe.request.files.get("file")
    filename = _text(getattr(uploaded, "filename", ""))
    if not uploaded or not filename.lower().endswith(".xml"):
        frappe.throw("An XML file is required", exc=frappe.ValidationError)
    content = uploaded.read()
    max_size = int(frappe.conf.get("max_file_size") or 10 * 1024 * 1024)
    if len(content) > max_size:
        frappe.throw("XML file is too large", exc=frappe.ValidationError)
    try:
        from xml.etree import ElementTree

        ElementTree.fromstring(content)
    except Exception:
        frappe.throw("XML file is malformed", exc=frappe.ValidationError)
    digest = hashlib.sha256(content).hexdigest()
    normalized_payload = {"invoice_number": _text(payload.get("invoice_number")), "invoice_date": _text(payload.get("invoice_date")), "supplier_tax_id": _text(payload.get("supplier_tax_id")), "invoice_total": payload.get("invoice_total"), "sha256": digest}
    payload_hash = _payload_hash(normalized_payload)
    existing = frappe.db.get_value("Supplier Portal Submission", {"access": access.name, "submission_type": "XML Invoice", "idempotency_key": key}, ["name", "payload_hash"], as_dict=True)
    if existing:
        if existing.payload_hash and existing.payload_hash != payload_hash:
            frappe.throw("Idempotency key was used with a different payload", exc=frappe.ValidationError)
        return {"submission": existing.name, "idempotent": True}
    if frappe.db.exists("Supplier Portal Submission", {"access": access.name, "submission_type": "XML Invoice", "sha256": digest}):
        frappe.throw("XML file was already submitted", exc=frappe.ValidationError)
    submission = frappe.get_doc({"doctype": "Supplier Portal Submission", "procurement_process": access.procurement_process, "access": access.name, "supplier": access.supplier, "submission_type": "XML Invoice", "purchase_order": access.purchase_order, "status": "Pending", "payload": json.dumps(normalized_payload), "payload_hash": payload_hash, "file_name": filename, "sha256": digest, "idempotency_key": key})
    submission.insert(ignore_permissions=True)
    file_doc = save_file(filename, content, "Supplier Portal Submission", submission.name, is_private=1)
    submission.file_url = file_doc.file_url
    submission.save(ignore_permissions=True)
    _audit("XML invoice submitted", access, metadata={"submission": submission.name, "sha256": digest})
    return {"submission": submission.name, "status": submission.status, "sha256": digest, "idempotent": False}


def _review_user() -> str:
    user = _text(_portal_config().get("review_user")) or "Administrator"
    if user and not frappe.db.exists("User", user):
        user = ""
    if not user:
        frappe.throw("Internal reviewer authentication required", exc=frappe.AuthenticationError)
    return user


@frappe.whitelist(allow_guest=True, methods=["POST"])
def review_submission() -> dict[str, Any]:
    from letron_api.gateway import verify_control_plane_request

    verify_control_plane_request("/api/method/letron_api.supplier_portal.review_submission")
    payload = _json()
    submission_name = _text(payload.get("submission"))
    decision = _text(payload.get("decision"))
    if decision not in {"Approved", "Rejected"}:
        frappe.throw("decision must be Approved or Rejected", exc=frappe.ValidationError)
    submission = frappe.get_doc("Supplier Portal Submission", submission_name)
    frappe.db.sql(
        "SELECT name FROM `tabSupplier Portal Submission` WHERE name=%s FOR UPDATE",
        submission.name,
    )
    submission = frappe.get_doc("Supplier Portal Submission", submission.name)
    access = frappe.get_doc("Supplier Portal Access", submission.access)
    reviewer = _review_user()
    if submission.status != "Pending":
        return {"submission": submission.name, "status": submission.status, "result_document": submission.result_document, "idempotent": True}
    if decision == "Rejected":
        submission.status = "Rejected"
        _audit("Submission reviewed", access, status="Rejected", metadata={"submission": submission.name, "reviewer": reviewer})
    elif submission.submission_type == "Delivery Confirmation":
        po = frappe.get_doc("Purchase Order", submission.purchase_order)
        data = json.loads(submission.payload or "{}")
        receipt = frappe.get_doc({"doctype": "Purchase Receipt", "supplier": po.supplier, "company": po.company, "items": [{"item_code": item.item_code, "qty": row["delivered_qty"], "uom": item.uom, "rate": item.rate, "purchase_order": po.name, "purchase_order_item": row["purchase_order_item"], "warehouse": item.warehouse, "serial_no": row.get("serial_no"), "batch_no": row.get("batch_no")} for row in data.get("items", []) for item in po.items if item.name == row["purchase_order_item"] and row["delivered_qty"] > 0]})
        with _internal_execution():
            receipt.insert(ignore_permissions=True)
            receipt.submit()
        submission.result_doctype = "Purchase Receipt"
        submission.result_document = receipt.name
        submission.status = "Approved"
    else:
        po = frappe.get_doc("Purchase Order", submission.purchase_order)
        receipt_rows = frappe.get_all(
            "Purchase Receipt Item",
            filters={"purchase_order": po.name, "docstatus": 1},
            fields=["parent", "name", "purchase_order_item", "item_code"],
            order_by="creation asc",
        )
        receipt_by_po_item = {
            _text(row.purchase_order_item): row
            for row in receipt_rows
            if _text(row.purchase_order_item)
        }
        invoice_items = []
        for item in po.items:
            receipt_row = receipt_by_po_item.get(_text(item.name))
            if not receipt_row:
                frappe.throw(
                    f"Purchase Receipt is required before invoicing item {item.item_code}",
                    exc=frappe.ValidationError,
                )
            invoice_items.append({
                "item_code": item.item_code,
                "qty": item.qty,
                "uom": item.uom,
                "rate": item.rate,
                "purchase_order": po.name,
                "purchase_order_item": item.name,
                "purchase_receipt": receipt_row.parent,
                "purchase_receipt_item": receipt_row.name,
            })
        invoice = frappe.get_doc({"doctype": "Purchase Invoice", "supplier": po.supplier, "company": po.company, "items": invoice_items})
        with _internal_execution():
            invoice.insert(ignore_permissions=True)
            invoice.submit()
        submission.result_doctype = "Purchase Invoice"
        submission.result_document = invoice.name
        submission.status = "Approved"
    submission.reviewed_by = reviewer
    submission.reviewed_at = frappe.utils.now_datetime()
    submission.review_note = _text(payload.get("review_note"))
    submission.save(ignore_permissions=True)
    _audit("Submission reviewed", access, metadata={"submission": submission.name, "reviewer": reviewer, "result_document": submission.result_document})
    return {"submission": submission.name, "status": submission.status, "result_document": submission.result_document, "idempotent": False}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def logout_session() -> dict[str, Any]:
    _authorized("logout_session")
    access = _access_by_token(_text(_json().get("session_token")), session=True)
    access.session_hash = None
    access.session_expires_at = None
    access.save(ignore_permissions=True)
    return {"status": "logged_out"}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def submit_quotation() -> dict[str, Any]:
    _authorized("submit_quotation")
    payload = _json()
    access = _lock_access(_access_by_token(_text(payload.get("session_token")), session=True))
    if access.supplier_quotation:
        return {"supplier_quotation": access.supplier_quotation, "idempotent": True}
    process = frappe.get_doc("Supplier Procurement Process", access.procurement_process)
    if process.approval_status not in {"Waiting", "Ready"}:
        frappe.throw("Quotation submission window is closed", exc=frappe.ValidationError)
    rfq = frappe.get_doc("Request for Quotation", access.request_for_quotation)
    if not _supplier_in_rfq(rfq, access.supplier):
        frappe.throw("Supplier is not part of the RFQ", exc=frappe.ValidationError)
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        frappe.throw("At least one quotation item is required", exc=frappe.ValidationError)
    rfq_items = {item.name: item for item in (rfq.items or [])}
    items = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            frappe.throw("Invalid quotation item", exc=frappe.ValidationError)
        source = rfq_items.get(_text(raw.get("request_for_quotation_item")))
        if not source:
            frappe.throw("Quotation item is not part of the RFQ", exc=frappe.ValidationError)
        qty = float(raw.get("qty") or source.qty or 0)
        rate = float(raw.get("rate") or 0)
        if qty <= 0 or rate < 0:
            frappe.throw("Quotation quantity/rate is invalid", exc=frappe.ValidationError)
        items.append({"item_code": source.item_code, "qty": qty, "uom": source.uom, "warehouse": source.warehouse, "rate": rate, "request_for_quotation": rfq.name, "request_for_quotation_item": source.name, "material_request": source.material_request, "material_request_item": source.material_request_item})
    quotation = frappe.get_doc({
        "doctype": "Supplier Quotation",
        "supplier": access.supplier,
        "company": rfq.company,
        "transaction_date": frappe.utils.nowdate(),
        "request_for_quotation": rfq.name,
        "items": items,
    })
    with _internal_execution():
        quotation.insert(ignore_permissions=True)
        quotation.submit()
    access.supplier_quotation = quotation.name
    access.status = "Submitted"
    access.save(ignore_permissions=True)
    _audit("Quotation submitted", access, metadata={"supplier_quotation": quotation.name})
    return {"supplier_quotation": quotation.name, "idempotent": False}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def evaluate_approval_gate() -> dict[str, Any]:
    _authorized("evaluate_approval_gate")
    payload = _json()
    material_request = _text(payload.get("material_request"))
    process_name = frappe.db.get_value("Supplier Procurement Process", {"material_request": material_request}, "name")
    if not process_name:
        frappe.throw("Supplier procurement process was not found", exc=frappe.ValidationError)
    frappe.db.sql("SELECT name FROM `tabSupplier Procurement Process` WHERE name=%s FOR UPDATE", process_name)
    process = frappe.get_doc("Supplier Procurement Process", process_name)
    access_rows = frappe.get_all("Supplier Portal Access", filters={"procurement_process": process.name}, fields=["name", "supplier", "supplier_quotation", "request_for_quotation", "status"])
    submitted = [row for row in access_rows if row.supplier_quotation]
    quoted = []
    for row in submitted:
        quotation = frappe.get_doc("Supplier Quotation", row.supplier_quotation)
        quoted.append({
            "row": row,
            "name": quotation.name,
            "supplier": row.supplier,
            "grand_total": float(quotation.grand_total or quotation.net_total or 0),
            "submitted_at": str(quotation.modified or quotation.creation or ""),
        })
    deadline_reached = frappe.utils.now_datetime() >= process.deadline_at
    rfq_name = frappe.db.get_value("Supplier Portal Access", {"procurement_process": process.name}, "request_for_quotation")
    rfq = frappe.get_doc("Request for Quotation", rfq_name) if rfq_name else None
    expected_suppliers = max(int(process.supplier_count or 0), len(rfq.suppliers or []) if rfq else 0)
    all_suppliers_quoted = expected_suppliers > 0 and len(access_rows) == expected_suppliers and len(submitted) == expected_suppliers
    ready = bool(submitted) and (all_suppliers_quoted or deadline_reached)
    if process.approval_status == "Waiting" and int(process.submitted_count or 0) != len(submitted):
        process.submitted_count = len(submitted)
        process.save(ignore_permissions=True)
    if ready and process.approval_status == "Waiting":
        selected = min(quoted, key=lambda item: (item["grand_total"], item["submitted_at"], item["supplier"]))
        process.approval_status = "Ready"
        process.submitted_count = len(submitted)
        process.selected_supplier_quotation = selected["name"]
        process.save(ignore_permissions=True)
    return {"process": process.name, "orchestration_id": process.orchestration_id, "material_request": process.material_request, "ready": ready, "deadline_reached": deadline_reached, "submitted_count": len(submitted), "supplier_count": len(access_rows), "approval_status": process.approval_status, "selected_supplier_quotation": process.selected_supplier_quotation, "suppliers": access_rows}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def evaluate_due_processes() -> dict[str, Any]:
    _authorized("evaluate_due_processes")
    now = frappe.utils.now_datetime()
    due = frappe.get_all("Supplier Procurement Process", filters={"approval_status": "Waiting", "deadline_at": ["<=", now]}, pluck="name")
    ready: list[dict[str, Any]] = []
    for name in due:
        process = frappe.get_doc("Supplier Procurement Process", name)
        access_rows = frappe.get_all("Supplier Portal Access", filters={"procurement_process": name}, fields=["supplier", "supplier_quotation"])
        quoted = []
        for row in access_rows:
            if not row.supplier_quotation:
                continue
            quotation = frappe.get_doc("Supplier Quotation", row.supplier_quotation)
            quoted.append((float(quotation.grand_total or quotation.net_total or 0), str(quotation.modified or quotation.creation or ""), row.supplier, quotation.name))
        process.submitted_count = len(quoted)
        if quoted:
            process.selected_supplier_quotation = min(quoted)[3]
            process.approval_status = "Ready"
            process.save(ignore_permissions=True)
            ready.append({
                "process": process.name,
                "orchestration_id": process.orchestration_id,
                "selected_supplier_quotation": process.selected_supplier_quotation,
                "submitted_count": process.submitted_count,
            })
    return {"evaluated": len(due), "ready": ready}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def claim_approval_opening() -> dict[str, Any]:
    _authorized("claim_approval_opening")
    payload = _json()
    process_name = _text(payload.get("process"))
    if not process_name:
        frappe.throw("process is required", exc=frappe.ValidationError)
    frappe.db.sql("SELECT name FROM `tabSupplier Procurement Process` WHERE name=%s FOR UPDATE", process_name)
    process = frappe.get_doc("Supplier Procurement Process", process_name)
    if process.approval_status == "Ready" and process.selected_supplier_quotation:
        process.approval_status = "Opening"
        process.save(ignore_permissions=True)
        return {"process": process.name, "claimed": True, "approval_status": process.approval_status}
    return {"process": process.name, "claimed": False, "approval_status": process.approval_status, "approval_id": process.approval_id}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def mark_approval_opened() -> dict[str, Any]:
    _authorized("mark_approval_opened")
    payload = _json()
    process_name = _text(payload.get("process"))
    approval_id = _text(payload.get("approval_id"))
    if not process_name or not approval_id:
        frappe.throw("process and approval_id are required", exc=frappe.ValidationError)
    process = frappe.get_doc("Supplier Procurement Process", process_name)
    if process.approval_status not in {"Ready", "Opening", "Opened"}:
        frappe.throw("Approval gate has not passed", exc=frappe.ValidationError)
    process.approval_status = "Opened"
    process.approval_id = approval_id
    process.approval_opened_at = frappe.utils.now_datetime()
    process.save(ignore_permissions=True)
    return {"process": process.name, "approval_status": process.approval_status, "approval_id": approval_id}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def read_approval_source() -> dict[str, Any]:
    from letron_api.gateway import verify_control_plane_request

    verify_control_plane_request("/api/method/letron_api.supplier_portal.read_approval_source")
    payload = _json()
    orchestration_id = _text(payload.get("orchestration_id"))
    quotation_name = _text(payload.get("supplier_quotation_name"))
    if not orchestration_id and not quotation_name:
        frappe.throw("Approval source correlation is required", exc=frappe.ValidationError)
    material_name = frappe.db.get_value("Material Request", {"custom_letron_orchestration_id": orchestration_id}, "name") if orchestration_id else ""
    rfq_name = frappe.db.get_value("Request for Quotation", {"custom_letron_orchestration_id": orchestration_id}, "name") if orchestration_id else ""
    if quotation_name and (not material_name or not rfq_name):
        quotation = frappe.get_doc("Supplier Quotation", quotation_name)
        rfq_name = _text(getattr(quotation, "request_for_quotation", "")) or _text((quotation.items or [])[0].request_for_quotation)
        rfq_meta = frappe.get_meta("Request for Quotation")
        if rfq_meta.has_field("custom_material_request"):
            material_name = _text(frappe.db.get_value("Request for Quotation", rfq_name, "custom_material_request"))
        if not material_name and rfq_name:
            material_name = _text((frappe.get_doc("Request for Quotation", rfq_name).items or [])[0].material_request)
    if not material_name or not rfq_name:
        frappe.throw("Approval source correlation was not found", exc=frappe.ValidationError)
    result: dict[str, Any] = {
        "material_request": frappe.get_doc("Material Request", material_name).as_dict(),
        "rfq": frappe.get_doc("Request for Quotation", rfq_name).as_dict(),
    }
    if quotation_name:
        quotation = frappe.get_doc("Supplier Quotation", quotation_name)
        result["supplier_quotation"] = quotation.as_dict()
    return result
