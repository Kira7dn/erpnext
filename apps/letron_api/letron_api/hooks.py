
import re
import uuid
from threading import Lock

app_name = "letron_api"
app_title = "Letron API"
app_publisher = "Letron"
app_description = "Technical API integration surface for the ERPNext bench"
app_email = "engineering@letron.local"
app_license = "MIT"

required_apps = ["frappe", "erpnext"]

_ROUTE_CACHE: dict[tuple[str, str], str] = {}
_ROUTE_CACHE_LOCK = Lock()
PUBLIC_MODULE_SLUGS = {
    "accounts", "assets", "buying", "crm", "communication", "contacts",
    "maintenance", "manufacturing", "projects", "quality-management",
    "selling", "stock", "subcontracting", "support",
}
DOCUMENT_ACTIONS = {("accounts", "sales-invoices"): {"submit", "cancel"}}



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
    if module_slug not in PUBLIC_MODULE_SLUGS:
        return
    module = module_slug.replace("-", " ").title()
    def slug(value: str) -> str:
        result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        if result.endswith("y") and not result.endswith(("ay", "ey", "iy", "oy", "uy")):
            return result[:-1] + "ies"
        if result.endswith(("s", "x", "ch", "sh")):
            return result + "es" if not result.endswith("s") else result
        return result + "s"

    cache_key = (module_slug, doctype_slug)
    with _ROUTE_CACHE_LOCK:
        doctype = _ROUTE_CACHE.get(cache_key)
    if doctype is None:
        doctype = "Sales Invoice" if module_slug == "accounts" and doctype_slug == "sales-invoices" else next(
            (name for name in frappe.get_all("DocType", filters={"module": module, "istable": 0}, pluck="name") if slug(name) == doctype_slug),
            None,
        )
        if doctype:
            with _ROUTE_CACHE_LOCK:
                _ROUTE_CACHE[cache_key] = doctype
    if not doctype:
        return
    meta = frappe.get_meta(doctype)
    if meta.istable or frappe.scrub(meta.module) != frappe.scrub(module):
        return
    if len(parts) == 6:
        action, name = parts[4:6]
        if action not in DOCUMENT_ACTIONS.get((module_slug, doctype_slug), set()):
            return
        from urllib.parse import urlencode

        target = "/api/method/letron_api.api.document_action"
        query = urlencode({"doctype": doctype, "name": name, "action": action})
        request.environ["QUERY_STRING"] = query
    else:
        target = f"/api/resource/{doctype}"
        if len(parts) == 5:
            target += f"/{parts[4]}"
    request.environ["PATH_INFO"] = target
    request.__dict__["path"] = target

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        idempotency_key = request.headers.get("X-Idempotency-Key")
        if idempotency_key:
            cache_key = f"letron:idempotency:{frappe.local.site}:{frappe.session.user}:{request.method}:{path}:{idempotency_key}"
            cache = frappe.cache()
            if cache.get_value(cache_key):
                frappe.throw("Duplicate X-Idempotency-Key for this request")
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
        cache = frappe.cache()
        if response.status_code >= 400:
            cache.delete_value(cache_key)
        else:
            cache.set_value(cache_key, "completed", expires_in_sec=86400)


before_request = ["letron_api.hooks.rewrite_public_routes"]
after_request = ["letron_api.hooks.add_request_headers"]
