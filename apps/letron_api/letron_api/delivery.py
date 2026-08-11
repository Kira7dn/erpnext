"""Durable delivery of public-resource changes to configured consumers."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import frappe

from letron_api.delivery_protocol import response_disposition, webhook_signature

MAX_ATTEMPTS = 3
OUTBOX_DOCTYPE = "Letron Event Outbox"
PUBLIC_RESOURCE_PATHS = {
    "Customer": "/api/v1/selling/customers",
    "Quotation": "/api/v1/selling/quotations",
    "Sales Order": "/api/v1/selling/sales-orders",
    "Delivery Note": "/api/v1/selling/delivery-notes",
    "Sales Invoice": "/api/v1/accounts/sales-invoices",
    "Purchase Invoice": "/api/v1/accounts/purchase-invoices",
    "Payment Entry": "/api/v1/accounts/payment-entries",
    "Bank": "/api/v1/accounts/banks",
    "Bank Account": "/api/v1/accounts/bank-accounts",
    "Mode of Payment": "/api/v1/accounts/modes-of-payment",
    "Cost Center": "/api/v1/accounts/cost-centers",
    "Journal Entry": "/api/v1/accounts/journal-entries",
    "Payment Request": "/api/v1/accounts/payment-requests",
    "Supplier": "/api/v1/buying/suppliers",
    "Purchase Order": "/api/v1/buying/purchase-orders",
    "Item": "/api/v1/stock/items",
    "Warehouse": "/api/v1/stock/warehouses",
    "Address": "/api/v1/contacts/addresses",
    "Contact": "/api/v1/contacts/contacts",
    "Material Request": "/api/v1/stock/material-requests",
    "Purchase Receipt": "/api/v1/stock/purchase-receipts",
    "Stock Entry": "/api/v1/stock/stock-entries",
    "Item Price": "/api/v1/stock/item-prices",
}


def _setting(name: str) -> str | None:
    value = os.environ.get(name) or frappe.conf.get(name.lower())
    return str(value) if value not in (None, "") else None


def _timeout_seconds() -> float:
    raw = _setting("LETRON_WEBHOOK_TIMEOUT_MS") or "5000"
    try:
        return max(0.1, min(float(raw) / 1000, 120.0))
    except ValueError:
        return 5.0


def _request_id() -> str:
    return str(getattr(frappe.local, "letron_request_id", None) or uuid.uuid4())


def _payload(doc: Any, event_id: str, event_type: str, occurred_at: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "request_id": _request_id(),
        "event_type": event_type,
        "doctype": doc.doctype,
        "document_name": doc.name,
        "occurred_at": occurred_at,
        "resource": doc.as_dict(no_nulls=True),
        "resource_url": f"{PUBLIC_RESOURCE_PATHS[doc.doctype]}/{quote(doc.name, safe='')}",
    }


def capture_event(doc: Any, event_type: str) -> None:
    """Persist an event in the business transaction, then queue delivery after commit."""
    if (_setting("DELIVERY_ENABLED") or "false").lower() not in {"1", "true", "yes"}:
        return
    if getattr(frappe.flags, "in_letron_outbox", False):
        return
    event_id = str(uuid.uuid4())
    occurred = datetime.now(UTC)
    occurred_at = occurred.isoformat()
    body = json.dumps(
        _payload(doc, event_id, event_type, occurred_at),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    frappe.flags.in_letron_outbox = True
    try:
        outbox = frappe.get_doc(
            {
                "doctype": OUTBOX_DOCTYPE,
                "event_id": event_id,
                "event_type": event_type,
                "resource_doctype": doc.doctype,
                "document_name": doc.name,
                "occurred_at": occurred.replace(tzinfo=None),
                "payload": body,
                "webhook_state": "Pending",
                "realtime_state": "Pending",
                "delivery_state": "Pending",
            }
        )
        outbox.insert(ignore_permissions=True)
    finally:
        frappe.flags.in_letron_outbox = False
    frappe.enqueue(
        "letron_api.delivery.process_outbox_event",
        queue="short",
        enqueue_after_commit=True,
        job_id=f"letron-outbox-{event_id}",
        event_id=event_id,
    )


def capture_create(doc: Any, method: str | None = None) -> None:
    capture_event(doc, "create")


def capture_update(doc: Any, method: str | None = None) -> None:
    capture_event(doc, "update")


def capture_submit(doc: Any, method: str | None = None) -> None:
    capture_event(doc, "submit")


def capture_cancel(doc: Any, method: str | None = None) -> None:
    capture_event(doc, "cancel")


def _post(url: str, body: bytes, headers: dict[str, str], timeout: float) -> int:
    request = Request(url, data=body, method="POST", headers={"Content-Type": "application/json", **headers})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status
    except HTTPError as error:
        return error.code


def _deliver_webhook(payload: str, event_id: str) -> tuple[str, str | None]:
    url = _setting("LETRON_WEBHOOK_URL")
    secret = _setting("LETRON_WEBHOOK_SECRET")
    if not url or not secret:
        return "Blocked", "webhook configuration is incomplete"
    body = payload.encode("utf-8")
    signature = webhook_signature(secret, body)
    status = _post(url, body, {"X-Letron-Signature": signature, "X-Event-Id": event_id}, _timeout_seconds())
    state = response_disposition(status)
    return state, None if state == "Delivered" else f"HTTP {status}"


def _deliver_realtime(payload: str, event_id: str) -> tuple[str, str | None]:
    url = _setting("LETRON_REALTIME_URL")
    token = _setting("LETRON_REALTIME_TOKEN")
    if not url or not token:
        return "Blocked", "realtime configuration is incomplete"
    message = json.loads(payload)
    frappe.publish_realtime("letron_resource_event", message)
    if url.startswith(("ws://", "wss://")):
        # LETRON_REALTIME_URL/TOKEN belong to the staging client in native
        # Socket.IO mode. The acceptance client verifies connect/reconnect.
        return "Delivered", None
    status = _post(url, payload.encode("utf-8"), {"Authorization": f"Bearer {token}", "X-Event-Id": event_id}, _timeout_seconds())
    state = response_disposition(status)
    return state, None if state == "Delivered" else f"HTTP {status}"


def _attempt(channel: str, row: Any) -> None:
    state_field = f"{channel}_state"
    attempts_field = f"{channel}_attempts"
    if row.get(state_field) in {"Delivered", "Failed"}:
        return
    if row.get(state_field) == "Blocked":
        required = ("LETRON_WEBHOOK_URL", "LETRON_WEBHOOK_SECRET") if channel == "webhook" else ("LETRON_REALTIME_URL", "LETRON_REALTIME_TOKEN")
        if not all(_setting(name) for name in required):
            return
    deliver = _deliver_webhook if channel == "webhook" else _deliver_realtime
    try:
        state, error = deliver(row.payload, row.event_id)
    except (TimeoutError, URLError, OSError) as exc:
        state, error = "Retry", type(exc).__name__
    if state == "Blocked":
        row.db_set(state_field, state, update_modified=False)
        row.db_set("last_error", error, update_modified=False)
        return
    attempts = int(row.get(attempts_field) or 0) + 1
    row.db_set(attempts_field, attempts, update_modified=False)
    if state == "Retry" and attempts >= MAX_ATTEMPTS:
        state = "Failed"
    row.db_set(state_field, state, update_modified=False)
    row.db_set("last_error", error, update_modified=False)


def process_outbox_event(event_id: str) -> None:
    name = frappe.db.get_value(OUTBOX_DOCTYPE, {"event_id": event_id}, "name")
    if not name:
        return
    row = frappe.get_doc(OUTBOX_DOCTYPE, name)
    _attempt("webhook", row)
    _attempt("realtime", row)
    row.reload()
    states = {row.get("webhook_state"), row.get("realtime_state")}
    if states == {"Delivered"}:
        final = "Delivered"
    elif "Pending" in states or "Retry" in states:
        final = "Pending"
    elif "Blocked" in states:
        final = "Blocked"
    else:
        final = "Failed"
    if row.get("delivery_state") != final:
        row.db_set("delivery_state", final, update_modified=False)
    frappe.db.commit()
    if "Retry" in states:
        frappe.enqueue(
            "letron_api.delivery.process_outbox_event",
            queue="short",
            enqueue_after_commit=True,
            event_id=event_id,
        )


def process_pending_outbox() -> None:
    if (_setting("DELIVERY_ENABLED") or "false").lower() not in {"1", "true", "yes"}:
        return
    for event_id in frappe.get_all(
        OUTBOX_DOCTYPE,
        filters={"delivery_state": ["in", ["Pending", "Blocked"]]},
        pluck="event_id",
        order_by="creation asc",
        limit_page_length=100,
    ):
        process_outbox_event(event_id)
