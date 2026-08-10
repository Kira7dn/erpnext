
import uuid
from threading import Lock
from typing import Any, cast

app_name = "letron_api"
app_title = "Letron API"
app_publisher = "Letron"
app_description = "Technical API integration surface for the ERPNext bench"
app_email = "engineering@letron.local"
app_license = "MIT"

required_apps = ["frappe", "erpnext"]

_ROUTE_CACHE: dict[tuple[str, str], str] = {}
_ROUTE_CACHE_LOCK = Lock()
PUBLIC_RESOURCE_ROUTES = {
    ("selling", "customers"): "Customer",
    ("selling", "quotations"): "Quotation",
    ("selling", "sales-orders"): "Sales Order",
    ("selling", "delivery-notes"): "Delivery Note",
    ("accounts", "sales-invoices"): "Sales Invoice",
    ("accounts", "purchase-invoices"): "Purchase Invoice",
    ("accounts", "payment-entries"): "Payment Entry",
    ("buying", "suppliers"): "Supplier",
    ("buying", "purchase-orders"): "Purchase Order",
    ("stock", "items"): "Item",
    ("stock", "warehouses"): "Warehouse",
}
DOCUMENT_ACTIONS = {
    ("accounts", "sales-invoices"): {"submit", "cancel"},
    ("accounts", "purchase-invoices"): {"submit", "cancel"},
    ("selling", "sales-orders"): {"submit", "cancel"},
    ("buying", "purchase-orders"): {"submit", "cancel"},
}



def rewrite_public_routes() -> None:
    """Rewrite public business aliases to native Frappe resource routes."""

    import frappe

    request = frappe.local.request
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    frappe.local.letron_request_id = request_id
    request.environ["LETRON_REQUEST_ID"] = request_id
    path = request.path
    parts = path.strip("/").split("/")
    if len(parts) not in {4, 5, 6} or parts[:2] != ["api", "v1"]:
        return
    module_slug, doctype_slug = parts[2:4]
    if not module_slug or not doctype_slug:
        return
    if (module_slug, doctype_slug) not in PUBLIC_RESOURCE_ROUTES:
        return
    if frappe.session.user in {"Guest", ""}:
        frappe.throw("Authentication required", exc=frappe.AuthenticationError)
    cache_key = (module_slug, doctype_slug)
    with _ROUTE_CACHE_LOCK:
        doctype = _ROUTE_CACHE.get(cache_key) or PUBLIC_RESOURCE_ROUTES[(module_slug, doctype_slug)]
        _ROUTE_CACHE[cache_key] = doctype
    if not doctype:
        return
    meta = frappe.get_meta(doctype)
    if meta.istable:
        return
    if len(parts) == 6:
        name, action = parts[4:6]
        if action not in DOCUMENT_ACTIONS.get((module_slug, doctype_slug), set()):
            return
        from urllib.parse import urlencode

        target = "/api/method/letron_api.api.document_action"
        query = urlencode({"doctype": doctype, "name": name, "action": action})
        request.environ["QUERY_STRING"] = query
        # Frappe builds form_dict before running before_request hooks, so also
        # update the parsed arguments when rewriting an already-open request.
        frappe.local.form_dict.update({"doctype": doctype, "name": name, "action": action})
    else:
        target = f"/api/resource/{doctype}"
        if len(parts) == 5:
            # PATH_INFO follows WSGI's latin-1 transport convention. Preserve
            # the original UTF-8 bytes so Frappe's router decodes the name once.
            name = parts[4].encode("utf-8").decode("latin-1")
            target += f"/{name}"
    request.environ["PATH_INFO"] = target
    request.__dict__["path"] = target

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        idempotency_key = request.headers.get("X-Idempotency-Key")
        if idempotency_key:
            cache_key = f"letron:idempotency:{frappe.local.site}:{frappe.session.user}:{request.method}:{path}:{idempotency_key}"
            cache = cast(Any, frappe.cache)()
            with cache.lock(f"{cache_key}:reservation", timeout=10, blocking_timeout=10):
                if cache.get_value(cache_key, use_local_cache=False):
                    frappe.throw("Duplicate X-Idempotency-Key for this request", exc=frappe.DuplicateEntryError)
                cache.set_value(cache_key, "in-flight", expires_in_sec=86400)
            frappe.local.letron_idempotency_cache_key = cache_key


def add_request_headers(response=None, request=None) -> None:
    """Propagate request IDs and finalize idempotency reservations."""
    if response is None:
        return
    import frappe

    request_id = getattr(frappe.local, "letron_request_id", None)
    if request_id:
        response.headers["X-Request-Id"] = request_id
    cache_key = getattr(frappe.local, "letron_idempotency_cache_key", None)
    if cache_key:
        cache = cast(Any, frappe.cache)()
        if response.status_code >= 400:
            cache.delete_value(cache_key)
        else:
            cache.set_value(cache_key, "completed", expires_in_sec=86400)


before_request = ["letron_api.hooks.rewrite_public_routes"]
after_request = ["letron_api.hooks.add_request_headers"]

doc_events = {
    doctype: {
        "after_insert": "letron_api.delivery.capture_create",
        "on_update": "letron_api.delivery.capture_update",
        "on_submit": "letron_api.delivery.capture_submit",
        "on_cancel": "letron_api.delivery.capture_cancel",
    }
    for doctype in PUBLIC_RESOURCE_ROUTES.values()
}

scheduler_events = {
    "all": ["letron_api.delivery.process_pending_outbox"],
}
