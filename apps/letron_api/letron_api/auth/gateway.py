from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any, cast

import frappe


@frappe.whitelist(allow_guest=True, methods=["GET"])
def csrf_token() -> str:
    """Issue the native Frappe CSRF token for the private JIT handshake."""
    from frappe.sessions import get_csrf_token

    return get_csrf_token()


def _signature_payload(headers: Any) -> str:
    return ".".join(
        str(headers.get(name, ""))
        for name in (
            "X-Letron-Gateway-Timestamp",
            "X-Letron-Gateway-Expires-At",
            "X-Letron-Gateway-Method",
            "X-Letron-Gateway-Path",
            "X-Letron-Gateway-User",
            "X-Letron-Gateway-Email",
            "X-Letron-Gateway-Tenant",
            "X-Letron-Gateway-Subject",
            "X-Letron-Gateway-Subject-Type",
            "X-Letron-Gateway-Policy-Version",
            "X-Letron-Gateway-Request-Id",
            "X-Letron-Gateway-Query",
            "X-Letron-Gateway-Body-Sha256",
        )
    )


def verify_gateway_request() -> str:
    headers = frappe.local.request.headers
    secret = os.environ.get("LETRON_AUTH_GATEWAY_SECRET", "")
    timestamp = headers.get("X-Letron-Gateway-Issued-At", "") or headers.get("X-Letron-Gateway-Timestamp", "")
    expires_at = headers.get("X-Letron-Gateway-Expires-At", "")
    signature = headers.get("X-Letron-Gateway-Signature", "")
    path = headers.get("X-Letron-Gateway-Path", "")
    query = headers.get("X-Letron-Gateway-Query", "")
    body_hash = headers.get("X-Letron-Gateway-Body-Sha256", "")
    if not secret or not timestamp or not expires_at or not signature or not path.startswith("/api/v1/"):
        frappe.throw("Gateway authorization required", exc=frappe.AuthenticationError)
    try:
        issued_at = int(timestamp)
        expiry = int(expires_at)
        age = abs(time.time() - issued_at)
    except ValueError:
        frappe.throw("Invalid gateway timestamp", exc=frappe.AuthenticationError)
    if age > 60 or expiry < time.time() or expiry <= issued_at:
        frappe.throw("Expired gateway authorization", exc=frappe.AuthenticationError)
    expected = hmac.new(secret.encode(), _signature_payload(headers).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        frappe.throw("Invalid gateway authorization", exc=frappe.AuthenticationError)
    if headers.get("X-Letron-Gateway-Method", "") != frappe.local.request.method:
        frappe.throw("Gateway method mismatch", exc=frappe.AuthenticationError)
    if path != frappe.local.request.path:
        frappe.throw("Gateway path mismatch", exc=frappe.AuthenticationError)
    actual_query = frappe.local.request.query_string.decode("utf-8") if frappe.local.request.query_string else ""
    if query != (f"?{actual_query}" if actual_query else ""):
        frappe.throw("Gateway query mismatch", exc=frappe.AuthenticationError)
    actual_body_hash = hashlib.sha256(frappe.local.request.get_data(cache=True)).hexdigest() if frappe.local.request.method not in {"GET", "HEAD"} else ""
    if not hmac.compare_digest(body_hash, actual_body_hash):
        frappe.throw("Gateway body mismatch", exc=frappe.AuthenticationError)
    email = headers.get("X-Letron-Gateway-Email", "").strip().lower()
    tenant = headers.get("X-Letron-Gateway-Tenant", "").strip()
    subject = headers.get("X-Letron-Gateway-Subject", "").strip()
    subject_type = headers.get("X-Letron-Gateway-Subject-Type", "").strip()
    if not email or not tenant or not subject or subject_type != "union_id" or not headers.get("X-Letron-Gateway-User", "").strip() or not headers.get("X-Letron-Gateway-Request-Id", "").strip():
        frappe.throw("Gateway identity missing", exc=frappe.AuthenticationError)
    cache = cast(Any, frappe.cache)()
    replay_key = f"letron:gateway:request:{headers.get('X-Letron-Gateway-Request-Id', '')}"
    with cache.lock(f"{replay_key}:lock", timeout=5, blocking_timeout=5):
        if cache.get_value(replay_key):
            frappe.throw("Gateway request replayed", exc=frappe.AuthenticationError)
        cache.set_value(replay_key, "1", expires_in_sec=60)
    # Auth Portal is the sole authorization source. The JIT handshake creates
    # this exact ERP User before a Gateway session is issued; never fall back to
    # Administrator or another technical principal.
    if not frappe.db.exists("User", email):
        frappe.throw("Gateway identity is not provisioned in ERP", exc=frappe.AuthenticationError)
    frappe.set_user(email)
    frappe.local.letron_authz_granted = True
    frappe.local.letron_gateway_actor = {
        "id": headers.get("X-Letron-Gateway-User", "").strip(),
        "email": email,
        "tenant_key": tenant,
        "subject": subject,
        "subject_type": subject_type,
    }
    frappe.local.letron_gateway_policy_version = headers.get("X-Letron-Gateway-Policy-Version", "")
    frappe.local.letron_gateway_user = email
    return email


def verify_internal_api_request() -> str:
    """Authenticate the single private automation principal.

    This lane is for server-side automation only.  It is deliberately
    separate from the Portal gateway and never accepts an actor identity from
    the request.
    """

    headers = frappe.local.request.headers
    secret = os.environ.get("LETRON_INTERNAL_API_SECRET", "")
    timestamp = headers.get("X-Letron-Control-Timestamp", "")
    expires_at = headers.get("X-Letron-Control-Expires-At", "")
    request_id = headers.get("X-Letron-Control-Request-Id", "")
    signature = headers.get("X-Letron-Control-Signature", "")
    path = frappe.local.request.path
    method = frappe.local.request.method
    if not secret or not timestamp or not expires_at or not request_id or not signature:
        frappe.throw("Internal API authorization required", exc=frappe.AuthenticationError)
    try:
        issued_at = int(timestamp)
        expiry = int(expires_at)
        age = abs(time.time() - issued_at)
    except ValueError:
        frappe.throw("Invalid internal API timestamp", exc=frappe.AuthenticationError)
    if age > 60 or expiry < time.time() or expiry <= issued_at:
        frappe.throw("Expired internal API authorization", exc=frappe.AuthenticationError)
    payload = f"{timestamp}.{expires_at}.{method}.{path}.{request_id}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        frappe.throw("Invalid internal API authorization", exc=frappe.AuthenticationError)
    cache = cast(Any, frappe.cache)()
    replay_key = f"letron:internal-api:request:{request_id}"
    with cache.lock(f"{replay_key}:lock", timeout=5, blocking_timeout=5):
        if cache.get_value(replay_key):
            frappe.throw("Internal API request replayed", exc=frappe.AuthenticationError)
        cache.set_value(replay_key, "1", expires_in_sec=60)
    user = os.environ.get("LETRON_INTERNAL_API_USER", "leducanh@ledb.vn").strip().lower()
    if not user or not frappe.db.exists("User", {"name": user, "enabled": 1}):
        frappe.throw("Internal API user is not provisioned in ERP", exc=frappe.AuthenticationError)
    frappe.set_user(user)
    frappe.local.letron_authz_granted = True
    return user


def verify_jit_request() -> None:
    headers = frappe.local.request.headers
    secret = os.environ.get("LETRON_AUTH_TO_ERP_JIT_SECRET", "")
    timestamp = headers.get("X-Letron-JIT-Timestamp", "")
    expires_at = headers.get("X-Letron-JIT-Expires-At", "")
    request_id = headers.get("X-Letron-JIT-Request-Id", "")
    signature = headers.get("X-Letron-JIT-Signature", "")
    path = "/api/method/letron_api.auth.sso_identity.provision_identity"
    if not secret or not timestamp or not expires_at or not request_id or not signature:
        frappe.throw("ERP identity provisioning authorization required", exc=frappe.AuthenticationError)
    try:
        issued_at = int(timestamp)
        expiry = int(expires_at)
        age = abs(time.time() - issued_at)
    except ValueError:
        frappe.throw("Invalid identity provisioning timestamp", exc=frappe.AuthenticationError)
    if age > 60 or expiry < time.time() or expiry <= issued_at:
        frappe.throw("Expired identity provisioning authorization", exc=frappe.AuthenticationError)
    payload = f"{timestamp}.{expires_at}.POST.{path}.{request_id}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        frappe.throw("Invalid identity provisioning authorization", exc=frappe.AuthenticationError)
    if frappe.local.request.method != "POST" or frappe.local.request.path != path:
        frappe.throw("Invalid identity provisioning route", exc=frappe.AuthenticationError)
    frappe.local.letron_jit_authorized = True
    # JIT is a narrowly scoped Auth-to-ERP service operation. It is the only
    # place allowed to use the native installation principal to create the
    # identity; business Gateway requests never use this principal.
    frappe.set_user("Administrator")
    frappe.flags.ignore_permissions = True
    # This is a private service-to-service endpoint authenticated by the
    # expiring HMAC above; it is not a browser/session endpoint.
    frappe.local.flags.ignore_csrf = True


def enforce_gateway_ingress() -> None:
    path = frappe.local.request.path
    if path.startswith("/api/v1/"):
        if frappe.local.request.headers.get("X-Letron-Control-Signature"):
            verify_internal_api_request()
            return
        verify_gateway_request()
        return

    # Native business APIs are never an authorization path. Global Portal is
    # the only caller that may reach /api/v1/* with signed claims.
    native_api = path.startswith(("/api/resource/", "/api/method/"))
    if native_api and frappe.local.request.headers.get("X-Letron-Control-Signature"):
        verify_internal_api_request()
        return
    if path == "/api/method/letron_api.auth.sso_identity.provision_identity":
        verify_jit_request()
        return
    native_exemptions = {
        "/api/method/letron_api.control.api.health",
        "/api/method/letron_api.control.api.runtime_info",
        "/api/method/letron_api.control.api.runtime_snapshot",
        "/api/method/letron_api.auth.gateway.csrf_token",
    }
    if native_api and path not in native_exemptions:
        frappe.throw("Global Portal gateway required", exc=frappe.AuthenticationError)
